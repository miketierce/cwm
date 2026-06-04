"""
E2: Full Complex State Tomography

Captures the complex FFT (not just magnitude) at each mode frequency on both
channels simultaneously. Builds a complex 2×2 state matrix and computes
concurrence from the SVD of the complex matrix.

Key question: Does phase information change the concurrence measurement?
If complex C ≈ magnitude C, the magnitude-only protocol is validated.
If complex C > magnitude C, we have bonus entanglement information.

Hardware (same as E1):
  SW TX PZT ← Pico NCO GP2+GP3 (column 23, separate board)
  NW RX PZT → preamp (×11) → PicoScope Ch A
  NE RX PZT → direct → PicoScope Ch B

The dual-channel simultaneous capture ensures both channels share the same
ADC clock — so the relative phase between Ch A and Ch B at each frequency
is physically meaningful (no timing jitter).

Success criterion:
  Complex-valued C within 5% of magnitude-only C (validates magnitude approach)
  OR complex C significantly higher (bonus information)
"""
import ctypes as ct
import numpy as np
import serial
import time
from scipy.optimize import differential_evolution
import json
from datetime import datetime
from pathlib import Path

# ─── PicoScope ────────────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
ps = ct.CDLL(PICO_LIB)
ps.ps2000_close_unit(ct.c_int16(1))
time.sleep(0.3)

N = 3968; TIMEBASE = 7
FS = 781250.0; NFFT = N * 4; BIN_HZ = FS / NFFT

RNG_A = 6; RNG_A_MV = 2000.0
RNG_B = 6; RNG_B_MV = 2000.0

ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
assert h > 0, f"PicoScope open failed: {h}"
ps.ps2000_set_channel(h, 0, 1, 0, RNG_A)
ps.ps2000_set_channel(h, 1, 1, 0, RNG_B)

# ─── Pico NCO ─────────────────────────────────────────────────────
ser = serial.Serial('/dev/cu.usbmodem113301', 115200, timeout=2)
time.sleep(0.5)
ser.reset_input_buffer()

def nco(cmd):
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()

# ─── Dual-channel capture (COMPLEX) ──────────────────────────────
def capture_dual_complex(navg=20):
    """Capture Ch A and Ch B, return COMPLEX FFT spectra (averaged)."""
    buf_a = (ct.c_int16 * N)()
    buf_b = (ct.c_int16 * N)()
    ov = ct.c_int16()
    specs_a, specs_b = [], []

    for _ in range(navg):
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(h, N, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(h):
                break
            time.sleep(0.002)
        ps.ps2000_get_values(h, ct.byref(buf_a), ct.byref(buf_b),
                             None, None, ct.byref(ov), N, 0)

        da = np.array(buf_a[:], dtype=np.float64) * (RNG_A_MV / 32767.0)
        db = np.array(buf_b[:], dtype=np.float64) * (RNG_B_MV / 32767.0)
        da -= da.mean(); db -= db.mean()
        win = np.hanning(N)
        specs_a.append(np.fft.rfft(da * win, n=NFFT))  # COMPLEX
        specs_b.append(np.fft.rfft(db * win, n=NFFT))  # COMPLEX

    return np.mean(specs_a, axis=0), np.mean(specs_b, axis=0)

def capture_dual_magnitude(navg=20):
    """Capture Ch A and Ch B, return magnitude spectra (for comparison)."""
    sp_a, sp_b = capture_dual_complex(navg)
    return np.abs(sp_a), np.abs(sp_b)

def peak_complex(sp, freq, w=5):
    """Get peak complex value near freq (at the bin with max magnitude)."""
    b = int(round(freq / BIN_HZ))
    region = sp[max(0, b-w):b+w+1]
    idx = np.argmax(np.abs(region))
    return complex(region[idx])

def peak_mag(sp, freq, w=5):
    b = int(round(freq / BIN_HZ))
    return float(np.abs(sp[max(0, b-w):b+w+1]).max())

# ─── CHSH math (works for complex matrix too) ────────────────────
def S_chsh_complex(M, params):
    """S for a complex matrix with real projectors (Qian & Eberly formalism)."""
    a1, a2, b1, b2 = params
    def I_p(al, be):
        a = np.array([np.cos(al), np.sin(al)])
        b = np.array([np.cos(be), np.sin(be)])
        return float(np.abs(a @ M @ b)**2)
    def E(al, be):
        i1 = I_p(al, be); i2 = I_p(al+np.pi/2, be+np.pi/2)
        i3 = I_p(al, be+np.pi/2); i4 = I_p(al+np.pi/2, be)
        d = i1 + i2 + i3 + i4
        return (i1 + i2 - i3 - i4) / d if d > 1e-15 else 0
    return abs(E(a1, b1) - E(a1, b2) + E(a2, b1) + E(a2, b2))

def S_chsh_real(M, params):
    """S for a real non-negative matrix."""
    a1, a2, b1, b2 = params
    def I_p(al, be):
        a = np.array([np.cos(al), np.sin(al)])
        b = np.array([np.cos(be), np.sin(be)])
        return float((a @ M @ b)**2)
    def E(al, be):
        i1 = I_p(al, be); i2 = I_p(al+np.pi/2, be+np.pi/2)
        i3 = I_p(al, be+np.pi/2); i4 = I_p(al+np.pi/2, be)
        d = i1 + i2 + i3 + i4
        return (i1 + i2 - i3 - i4) / d if d > 1e-15 else 0
    return abs(E(a1, b1) - E(a1, b2) + E(a2, b1) + E(a2, b2))

def optimize_S_complex(M):
    def neg_S(p): return -S_chsh_complex(M, p)
    r = differential_evolution(neg_S, [(0, np.pi)]*4,
                               maxiter=3000, seed=42, tol=1e-10, polish=True)
    return -r.fun, r.x

def optimize_S_real(M):
    def neg_S(p): return -S_chsh_real(M, p)
    r = differential_evolution(neg_S, [(0, np.pi)]*4,
                               maxiter=3000, seed=42, tol=1e-10, polish=True)
    return -r.fun, r.x

# ─── Config ───────────────────────────────────────────────────────
F1, F2 = 34000, 70000  # Best pair from E1
NTRIALS = 200
NAVG = 20

print("E2: Full Complex State Tomography")
print("=" * 60)
print(f"Modes: {F1} + {F2} Hz")
print(f"Trials: {NTRIALS}, {NAVG} averages each")
print(f"Captures: complex FFT (phase-preserving)")
print(f"Comparison: complex vs magnitude-only concurrence")
print()

# ─── Start drive ─────────────────────────────────────────────────
print("[1] Starting dual-mode drive...")
nco('Foff'); time.sleep(0.3)
nco(f'F1:{F1}'); nco(f'F2:{F2}')
time.sleep(3.0)

# Signal check
sp_a, sp_b = capture_dual_complex(20)
f1a = peak_complex(sp_a, F1); f2a = peak_complex(sp_a, F2)
f1b = peak_complex(sp_b, F1); f2b = peak_complex(sp_b, F2)
print(f"  Ch A (NW): f1={abs(f1a):.0f}∠{np.degrees(np.angle(f1a)):.1f}°, "
      f"f2={abs(f2a):.0f}∠{np.degrees(np.angle(f2a)):.1f}°")
print(f"  Ch B (NE): f1={abs(f1b):.0f}∠{np.degrees(np.angle(f1b)):.1f}°, "
      f"f2={abs(f2b):.0f}∠{np.degrees(np.angle(f2b)):.1f}°")
print(f"  Phase diff f1 (B-A): {np.degrees(np.angle(f1b) - np.angle(f1a)):.1f}°")
print(f"  Phase diff f2 (B-A): {np.degrees(np.angle(f2b) - np.angle(f2a)):.1f}°")

# ─── Collect trials (both complex and magnitude) ─────────────────
print(f"\n[2] Collecting {NTRIALS} simultaneous measurements...")
trials_complex = []  # Each: [f1_chA_complex, f1_chB_complex, f2_chA_complex, f2_chB_complex]
trials_mag = []      # Each: [f1_chA_mag, f1_chB_mag, f2_chA_mag, f2_chB_mag]
phase_diffs_f1 = []  # Phase(ChB) - Phase(ChA) at f1
phase_diffs_f2 = []  # Phase(ChB) - Phase(ChA) at f2

for trial in range(NTRIALS):
    sp_a, sp_b = capture_dual_complex(NAVG)

    c_f1a = peak_complex(sp_a, F1)
    c_f1b = peak_complex(sp_b, F1)
    c_f2a = peak_complex(sp_a, F2)
    c_f2b = peak_complex(sp_b, F2)

    trials_complex.append([c_f1a, c_f1b, c_f2a, c_f2b])
    trials_mag.append([abs(c_f1a), abs(c_f1b), abs(c_f2a), abs(c_f2b)])

    # Track inter-channel phase difference
    phase_diffs_f1.append(np.angle(c_f1b) - np.angle(c_f1a))
    phase_diffs_f2.append(np.angle(c_f2b) - np.angle(c_f2a))

    if (trial+1) % 50 == 0:
        last_mag = np.array(trials_mag[-20:])
        cv = np.std(last_mag[:,0]) / np.mean(last_mag[:,0]) * 100
        # Phase stability (circular std)
        pd1 = np.array(phase_diffs_f1[-20:])
        pd2 = np.array(phase_diffs_f2[-20:])
        ps1 = np.sqrt(-2*np.log(abs(np.mean(np.exp(1j*pd1)))))  # Circular std
        ps2 = np.sqrt(-2*np.log(abs(np.mean(np.exp(1j*pd2)))))
        print(f"  {trial+1}/{NTRIALS} — CV(mag)={cv:.1f}%, "
              f"phase_std: f1={np.degrees(ps1):.1f}°, f2={np.degrees(ps2):.1f}°")

nco('Foff')
trials_mag = np.array(trials_mag)
phase_diffs_f1 = np.array(phase_diffs_f1)
phase_diffs_f2 = np.array(phase_diffs_f2)

# ─── Phase analysis ──────────────────────────────────────────────
print(f"\n[3] Phase stability analysis...")
# Circular mean and std
def circ_stats(angles):
    z = np.exp(1j * angles)
    mean_dir = np.angle(np.mean(z))
    R = abs(np.mean(z))
    std = np.sqrt(-2*np.log(R)) if R > 0.01 else np.pi
    return mean_dir, std

mean_f1, std_f1 = circ_stats(phase_diffs_f1)
mean_f2, std_f2 = circ_stats(phase_diffs_f2)
print(f"  Phase diff f1 (B-A): mean={np.degrees(mean_f1):.1f}° ± {np.degrees(std_f1):.1f}° (circ)")
print(f"  Phase diff f2 (B-A): mean={np.degrees(mean_f2):.1f}° ± {np.degrees(std_f2):.1f}° (circ)")
print(f"  Relative phase (f2-f1): {np.degrees(mean_f2 - mean_f1):.1f}°")

phase_stable = std_f1 < np.radians(30) and std_f2 < np.radians(30)
print(f"  Phase stable (<30° std): {'YES' if phase_stable else 'NO'}")

# ─── MAGNITUDE-ONLY state matrix (baseline, same as E1) ──────────
print(f"\n[4] Magnitude-only state matrix (baseline)...")
M_mag_trials = []
for t in trials_mag:
    M = np.array([[t[0], t[1]], [t[2], t[3]]])
    r1 = np.linalg.norm(M[0]); r2 = np.linalg.norm(M[1])
    if r1 > 0 and r2 > 0:
        Mn = np.array([[M[0,0]/r1, M[0,1]/r1], [M[1,0]/r2, M[1,1]/r2]])
        Mn = Mn / np.linalg.norm(Mn, 'fro')
        M_mag_trials.append(Mn)

M_mag_avg = np.mean(M_mag_trials, axis=0)
M_mag_avg = M_mag_avg / np.linalg.norm(M_mag_avg, 'fro')

_, sigma_mag, _ = np.linalg.svd(M_mag_avg)
C_mag = 2*sigma_mag[0]*sigma_mag[1] / (sigma_mag[0]**2 + sigma_mag[1]**2)

S_mag, params_mag = optimize_S_real(M_mag_avg)
print(f"  M_mag:")
print(f"    [[{M_mag_avg[0,0]:.4f}, {M_mag_avg[0,1]:.4f}],")
print(f"     [{M_mag_avg[1,0]:.4f}, {M_mag_avg[1,1]:.4f}]]")
print(f"  C_mag = {C_mag:.6f}")
print(f"  S_mag = {S_mag:.6f}")

# ─── COMPLEX state matrix ────────────────────────────────────────
print(f"\n[5] Complex state matrix...")
M_complex_trials = []
for t in trials_complex:
    # t = [f1_A, f1_B, f2_A, f2_B] — all complex
    M = np.array([[t[0], t[1]], [t[2], t[3]]], dtype=complex)
    # Row normalize by magnitude of row vector
    r1 = np.linalg.norm(M[0]); r2 = np.linalg.norm(M[1])
    if r1 > 0 and r2 > 0:
        Mn = np.array([[M[0,0]/r1, M[0,1]/r1], [M[1,0]/r2, M[1,1]/r2]])
        Mn = Mn / np.linalg.norm(Mn, 'fro')
        M_complex_trials.append(Mn)

M_complex_avg = np.mean(M_complex_trials, axis=0)
M_complex_avg = M_complex_avg / np.linalg.norm(M_complex_avg, 'fro')

_, sigma_complex, _ = np.linalg.svd(M_complex_avg)
C_complex = 2*sigma_complex[0]*sigma_complex[1] / (sigma_complex[0]**2 + sigma_complex[1]**2)

S_complex, params_complex = optimize_S_complex(M_complex_avg)

print(f"  M_complex:")
print(f"    [[{M_complex_avg[0,0]:.4f}, {M_complex_avg[0,1]:.4f}],")
print(f"     [{M_complex_avg[1,0]:.4f}, {M_complex_avg[1,1]:.4f}]]")
print(f"  |M_complex| (magnitudes):")
print(f"    [[{abs(M_complex_avg[0,0]):.4f}, {abs(M_complex_avg[0,1]):.4f}],")
print(f"     [{abs(M_complex_avg[1,0]):.4f}, {abs(M_complex_avg[1,1]):.4f}]]")
print(f"  Phases:")
print(f"    [[{np.degrees(np.angle(M_complex_avg[0,0])):.1f}°, {np.degrees(np.angle(M_complex_avg[0,1])):.1f}°],")
print(f"     [{np.degrees(np.angle(M_complex_avg[1,0])):.1f}°, {np.degrees(np.angle(M_complex_avg[1,1])):.1f}°]]")
print(f"  C_complex = {C_complex:.6f}")
print(f"  S_complex = {S_complex:.6f}")

# ─── Comparison ──────────────────────────────────────────────────
print(f"\n[6] Complex vs Magnitude comparison...")
C_diff = C_complex - C_mag
C_pct = abs(C_diff) / C_mag * 100 if C_mag > 0 else 0
S_diff = S_complex - S_mag

print(f"  C_mag     = {C_mag:.6f}")
print(f"  C_complex = {C_complex:.6f}")
print(f"  Difference: {C_diff:+.6f} ({C_pct:.3f}%)")
print(f"  S_mag     = {S_mag:.6f}")
print(f"  S_complex = {S_complex:.6f}")
print(f"  Difference: {S_diff:+.6f}")

# ─── Bootstrap for both ──────────────────────────────────────────
print(f"\n[7] Bootstrap comparison (2000 resamples)...")
rng = np.random.default_rng(42)
S_mag_boots, C_mag_boots = [], []
S_cpx_boots, C_cpx_boots = [], []

for _ in range(2000):
    idx = rng.choice(len(M_mag_trials), size=len(M_mag_trials), replace=True)

    # Magnitude
    Mb = np.mean([M_mag_trials[j] for j in idx], axis=0)
    Mb = Mb / np.linalg.norm(Mb, 'fro')
    S_mag_boots.append(S_chsh_real(Mb, params_mag))
    _, sig_b, _ = np.linalg.svd(Mb)
    C_mag_boots.append(2*sig_b[0]*sig_b[1] / (sig_b[0]**2 + sig_b[1]**2))

    # Complex
    Mc = np.mean([M_complex_trials[j] for j in idx], axis=0)
    Mc = Mc / np.linalg.norm(Mc, 'fro')
    S_cpx_boots.append(S_chsh_complex(Mc, params_complex))
    _, sig_c, _ = np.linalg.svd(Mc)
    C_cpx_boots.append(2*sig_c[0]*sig_c[1] / (sig_c[0]**2 + sig_c[1]**2))

S_mag_boots = np.array(S_mag_boots); C_mag_boots = np.array(C_mag_boots)
S_cpx_boots = np.array(S_cpx_boots); C_cpx_boots = np.array(C_cpx_boots)

ci_S_mag = [float(np.percentile(S_mag_boots, 2.5)), float(np.percentile(S_mag_boots, 97.5))]
ci_S_cpx = [float(np.percentile(S_cpx_boots, 2.5)), float(np.percentile(S_cpx_boots, 97.5))]
ci_C_mag = [float(np.percentile(C_mag_boots, 2.5)), float(np.percentile(C_mag_boots, 97.5))]
ci_C_cpx = [float(np.percentile(C_cpx_boots, 2.5)), float(np.percentile(C_cpx_boots, 97.5))]

print(f"  Magnitude: S={np.mean(S_mag_boots):.6f}±{np.std(S_mag_boots):.6f} "
      f"C={np.mean(C_mag_boots):.6f}±{np.std(C_mag_boots):.6f}")
print(f"  Complex:   S={np.mean(S_cpx_boots):.6f}±{np.std(S_cpx_boots):.6f} "
      f"C={np.mean(C_cpx_boots):.6f}±{np.std(C_cpx_boots):.6f}")

# Paired difference
C_diff_boots = C_cpx_boots - C_mag_boots
S_diff_boots = S_cpx_boots - S_mag_boots
print(f"\n  Paired difference (complex - magnitude):")
print(f"    ΔC = {np.mean(C_diff_boots):+.6f} ± {np.std(C_diff_boots):.6f}")
print(f"    ΔS = {np.mean(S_diff_boots):+.6f} ± {np.std(S_diff_boots):.6f}")
print(f"    ΔC 95% CI: [{np.percentile(C_diff_boots, 2.5):+.6f}, {np.percentile(C_diff_boots, 97.5):+.6f}]")

# ─── Verdict ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  E2 COMPLEX STATE TOMOGRAPHY — RESULTS")
print("=" * 60)
print(f"  Phase stable:    {'YES' if phase_stable else 'NO'} "
      f"(f1: {np.degrees(std_f1):.1f}°, f2: {np.degrees(std_f2):.1f}°)")
print(f"  C_magnitude:     {C_mag:.6f} [{ci_C_mag[0]:.6f}, {ci_C_mag[1]:.6f}]")
print(f"  C_complex:       {C_complex:.6f} [{ci_C_cpx[0]:.6f}, {ci_C_cpx[1]:.6f}]")
print(f"  C difference:    {C_pct:.3f}%")
print(f"  S_magnitude:     {S_mag:.6f} [{ci_S_mag[0]:.6f}, {ci_S_mag[1]:.6f}]")
print(f"  S_complex:       {S_complex:.6f} [{ci_S_cpx[0]:.6f}, {ci_S_cpx[1]:.6f}]")
print()

if C_pct < 5.0:
    verdict = 'PASS_VALIDATES_MAGNITUDE'
    print("  ★★ PASS — Complex C within 5% of magnitude C!")
    print("  Magnitude-only protocol is VALIDATED.")
    print("  Phase information does not significantly affect non-separability measure.")
elif C_complex > C_mag:
    verdict = 'PASS_COMPLEX_BONUS'
    print(f"  ★ PASS — Complex C is {C_pct:.1f}% HIGHER than magnitude C!")
    print("  Phase carries additional entanglement information (bonus).")
else:
    verdict = 'INCONCLUSIVE'
    print(f"  △ Complex C is {C_pct:.1f}% different from magnitude C.")

# Both still violate?
if ci_S_mag[0] > 2.0 and ci_S_cpx[0] > 2.0:
    print("  Both magnitude and complex S > 2.0 at 95% CI.")

# ─── Save ─────────────────────────────────────────────────────────
DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/quantum_bridge')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = DATA_DIR / f'e2_complex_tomography_{ts}.json'

output = {
    'test': 'E2_complex_state_tomography',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'modes': [F1, F2],
        'n_trials': NTRIALS,
        'n_avg': NAVG,
        'rx_channels': {'A': 'NW_preamp_11x', 'B': 'NE_direct'},
        'tx': 'SW_PZT_PicoNCO',
    },
    'magnitude_only': {
        'state_matrix': M_mag_avg.tolist(),
        'svd_sigma': [float(s) for s in sigma_mag],
        'concurrence': float(C_mag),
        'concurrence_ci_95': ci_C_mag,
        'S_optimal': float(S_mag),
        'S_ci_95': ci_S_mag,
    },
    'complex': {
        'state_matrix_real': np.real(M_complex_avg).tolist(),
        'state_matrix_imag': np.imag(M_complex_avg).tolist(),
        'state_matrix_mag': np.abs(M_complex_avg).tolist(),
        'state_matrix_phase_deg': np.degrees(np.angle(M_complex_avg)).tolist(),
        'svd_sigma': [float(s) for s in sigma_complex],
        'concurrence': float(C_complex),
        'concurrence_ci_95': ci_C_cpx,
        'S_optimal': float(S_complex),
        'S_ci_95': ci_S_cpx,
    },
    'comparison': {
        'C_difference': float(C_diff),
        'C_difference_pct': float(C_pct),
        'S_difference': float(S_diff),
        'C_diff_bootstrap_mean': float(np.mean(C_diff_boots)),
        'C_diff_bootstrap_std': float(np.std(C_diff_boots)),
        'C_diff_ci_95': [float(np.percentile(C_diff_boots, 2.5)),
                         float(np.percentile(C_diff_boots, 97.5))],
    },
    'phase_analysis': {
        'f1_phase_diff_mean_deg': float(np.degrees(mean_f1)),
        'f1_phase_diff_std_deg': float(np.degrees(std_f1)),
        'f2_phase_diff_mean_deg': float(np.degrees(mean_f2)),
        'f2_phase_diff_std_deg': float(np.degrees(std_f2)),
        'phase_stable': bool(phase_stable),
    },
    'verdict': verdict,
}

with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\n  Saved: {out_path}")

# Cleanup
ser.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
print("  Done.")
