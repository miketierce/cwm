"""
T5.2 CHSH — Dual-Channel Simultaneous Capture (no relay switching).

Hardware:
  SW TX PZT ← Pico NCO GP2+GP3 (column 23, separate board)
  NW RX PZT → preamp (×11) → PicoScope Ch A
  NE RX PZT → direct → PicoScope Ch B

Key advantage: both receivers captured in a SINGLE acquisition.
  - Zero phase jitter (same ADC clock, same timebase)
  - No relay switching delays
  - TX board physically isolated from RX paths

State matrix M[2×2] = amplitudes at [f1, f2] × [ChA(NW), ChB(NE)]
Non-separability → different spatial distributions for different modes.
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

# Channel ranges
RNG_A = 6; RNG_A_MV = 2000.0   # Ch A: preamp output, ±2V
RNG_B = 6; RNG_B_MV = 2000.0   # Ch B: direct PZT, ±2V (adjust if needed)

ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
assert h > 0, f"PicoScope open failed: {h}"

# Enable BOTH channels, AC coupled
ps.ps2000_set_channel(h, 0, 1, 0, RNG_A)  # Ch A
ps.ps2000_set_channel(h, 1, 1, 0, RNG_B)  # Ch B
print(f"PicoScope opened (handle={h}), dual channel enabled")

# ─── Pico NCO ─────────────────────────────────────────────────────
ser = serial.Serial('/dev/cu.usbmodem113301', 115200, timeout=2)
time.sleep(0.5)
ser.reset_input_buffer()

def nco(cmd):
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()

# ─── Dual-channel capture ─────────────────────────────────────────
def capture_dual(navg=16):
    """Capture Ch A and Ch B simultaneously, return averaged magnitude spectra."""
    buf_a = (ct.c_int16 * N)()
    buf_b = (ct.c_int16 * N)()
    ov = ct.c_int16()
    mags_a, mags_b = [], []

    for _ in range(navg):
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)  # No trigger (free run)
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
        mags_a.append(np.abs(np.fft.rfft(da * win, n=NFFT)))
        mags_b.append(np.abs(np.fft.rfft(db * win, n=NFFT)))

    return np.mean(mags_a, axis=0), np.mean(mags_b, axis=0)

def peak_mag(sp, freq, w=5):
    b = int(round(freq / BIN_HZ))
    return float(sp[max(0, b-w):b+w+1].max())

# ─── CHSH math ────────────────────────────────────────────────────
def S_chsh_real(M, params):
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

def optimize_S(M):
    def neg_S(p): return -S_chsh_real(M, p)
    r = differential_evolution(neg_S, [(0, np.pi)]*4,
                               maxiter=2000, seed=42, tol=1e-9, polish=True)
    return -r.fun, r.x

# ─── Config ───────────────────────────────────────────────────────
F1, F2 = 54920, 97011
NTRIALS = 200
NAVG = 20

print("\nT5.2 CHSH — Dual-Channel Simultaneous Capture")
print("=" * 60)
print(f"TX: SW PZT (Pico NCO GP2+GP3, separate board)")
print(f"RX: Ch A = NW (preamp ×11) | Ch B = NE (direct)")
print(f"Modes: {F1} + {F2} Hz (simultaneous)")
print(f"Trials: {NTRIALS}, {NAVG} averages each")
print(f"Key: ZERO relay switching, simultaneous capture")
print()

# ─── Start drive ─────────────────────────────────────────────────
print("[1] Starting continuous dual-mode drive...")
nco('Foff'); time.sleep(0.3)
nco(f'F1:{F1}'); nco(f'F2:{F2}')
time.sleep(3.0)  # Let plate ring up

# Quick signal check
sp_a, sp_b = capture_dual(20)
f1a = peak_mag(sp_a, F1); f2a = peak_mag(sp_a, F2)
f1b = peak_mag(sp_b, F1); f2b = peak_mag(sp_b, F2)
print(f"  Ch A (NW, preamp): f1={f1a:.0f}, f2={f2a:.0f}")
print(f"  Ch B (NE, direct): f1={f1b:.0f}, f2={f2b:.0f}")
print(f"  Ratio f1 (B/A): {f1b/f1a:.3f}")
print(f"  Ratio f2 (B/A): {f2b/f2a:.3f}")

if f1b < 10 and f2b < 10:
    print("\n  ⚠ Ch B signal very weak — may need lower range or check wiring")
if f1a < 10 and f2a < 10:
    print("\n  ⚠ Ch A signal very weak — check preamp connection")

# ─── Collect trials ──────────────────────────────────────────────
print(f"\n[2] Collecting {NTRIALS} simultaneous dual-channel measurements...")
trials = []  # Each: [f1_chA, f1_chB, f2_chA, f2_chB]

for trial in range(NTRIALS):
    sp_a, sp_b = capture_dual(NAVG)
    trials.append([
        peak_mag(sp_a, F1), peak_mag(sp_b, F1),
        peak_mag(sp_a, F2), peak_mag(sp_b, F2),
    ])

    if (trial+1) % 50 == 0:
        last = np.array(trials[-20:])
        cv_f1a = np.std(last[:,0]) / np.mean(last[:,0]) * 100
        cv_f1b = np.std(last[:,1]) / np.mean(last[:,1]) * 100
        print(f"  {trial+1}/{NTRIALS} — CV: f1_A={cv_f1a:.1f}%, f1_B={cv_f1b:.1f}%")

nco('Foff')
trials = np.array(trials)

# ─── Stability ────────────────────────────────────────────────────
print(f"\n[3] Signal stability...")
labels = ['f1@ChA(NW)', 'f1@ChB(NE)', 'f2@ChA(NW)', 'f2@ChB(NE)']
for i, lbl in enumerate(labels):
    m, s = np.mean(trials[:,i]), np.std(trials[:,i])
    print(f"  {lbl}: {m:.0f} ± {s:.0f} (CV={s/m*100:.1f}%)")

# Spatial ratios
r_f1 = trials[:,1] / trials[:,0]  # ChB/ChA for f1
r_f2 = trials[:,3] / trials[:,2]  # ChB/ChA for f2
print(f"\n  Spatial ratio f1 (NE/NW): {np.mean(r_f1):.4f} ± {np.std(r_f1):.4f}")
print(f"  Spatial ratio f2 (NE/NW): {np.mean(r_f2):.4f} ± {np.std(r_f2):.4f}")
ratio_diff = abs(np.mean(r_f1) - np.mean(r_f2))
print(f"  Ratio difference: {ratio_diff:.4f}", end="")
if ratio_diff > 0.05:
    print(" ← GOOD (spatial diversity!)")
else:
    print(" ← WARNING (may indicate crosstalk)")

# ─── State matrix ─────────────────────────────────────────────────
print(f"\n[4] State matrix construction...")
M_trials = []
for t in trials:
    M = np.array([[t[0], t[1]], [t[2], t[3]]])
    # Row normalize (spectral equalization)
    r1 = np.linalg.norm(M[0]); r2 = np.linalg.norm(M[1])
    if r1 > 0 and r2 > 0:
        Mn = np.array([[M[0,0]/r1, M[0,1]/r1], [M[1,0]/r2, M[1,1]/r2]])
        Mn = Mn / np.linalg.norm(Mn, 'fro')
        M_trials.append(Mn)

M_avg = np.mean(M_trials, axis=0)
M_avg = M_avg / np.linalg.norm(M_avg, 'fro')

U, sigma, Vh = np.linalg.svd(M_avg)
C = 2*sigma[0]*sigma[1] / (sigma[0]**2 + sigma[1]**2)
S_theory = 2*np.sqrt(1 + C**2)

print(f"  M_avg (row-norm, Frob-norm):")
print(f"    [[{M_avg[0,0]:.4f}, {M_avg[0,1]:.4f}],")
print(f"     [{M_avg[1,0]:.4f}, {M_avg[1,1]:.4f}]]")
print(f"  SVD: σ = [{sigma[0]:.4f}, {sigma[1]:.4f}]")
print(f"  Concurrence: C = {C:.4f}")
print(f"  S_max (theory): {S_theory:.4f}")

# ─── Optimize S ──────────────────────────────────────────────────
print(f"\n[5] Optimizing measurement angles...")
S_opt, params_opt = optimize_S(M_avg)
a1, a2, b1, b2 = params_opt
print(f"  Alice angles: [{np.degrees(a1):.1f}°, {np.degrees(a2):.1f}°]")
print(f"  Bob angles:   [{np.degrees(b1):.1f}°, {np.degrees(b2):.1f}°]")
print(f"  S (optimal) = {S_opt:.4f}")

def E_at(M, al, be):
    def I_p(a, b):
        av = np.array([np.cos(a), np.sin(a)])
        bv = np.array([np.cos(b), np.sin(b)])
        return (av @ M @ bv)**2
    i1=I_p(al,be); i2=I_p(al+np.pi/2,be+np.pi/2)
    i3=I_p(al,be+np.pi/2); i4=I_p(al+np.pi/2,be)
    d=i1+i2+i3+i4
    return (i1+i2-i3-i4)/d if d>0 else 0

print(f"  E(a1,b1)={E_at(M_avg,a1,b1):+.4f}  E(a1,b2)={E_at(M_avg,a1,b2):+.4f}")
print(f"  E(a2,b1)={E_at(M_avg,a2,b1):+.4f}  E(a2,b2)={E_at(M_avg,a2,b2):+.4f}")

# ─── Bootstrap ────────────────────────────────────────────────────
print(f"\n[6] Bootstrap CI (5000 resamples)...")
rng = np.random.default_rng(42)
S_boots, C_boots = [], []

for _ in range(5000):
    idx = rng.choice(len(M_trials), size=len(M_trials), replace=True)
    Mb = np.mean([M_trials[j] for j in idx], axis=0)
    Mb = Mb / np.linalg.norm(Mb, 'fro')
    S_boots.append(S_chsh_real(Mb, params_opt))
    _, sig_b, _ = np.linalg.svd(Mb)
    C_boots.append(2*sig_b[0]*sig_b[1] / (sig_b[0]**2 + sig_b[1]**2))

S_boots = np.array(S_boots)
C_boots = np.array(C_boots)
ci_S = [float(np.percentile(S_boots, 2.5)), float(np.percentile(S_boots, 97.5))]
ci_C = [float(np.percentile(C_boots, 2.5)), float(np.percentile(C_boots, 97.5))]
sig_above_2 = (np.mean(S_boots) - 2.0) / np.std(S_boots) if np.std(S_boots) > 0 else 0

print(f"  S = {np.mean(S_boots):.4f} ± {np.std(S_boots):.4f}")
print(f"  S 95% CI: [{ci_S[0]:.4f}, {ci_S[1]:.4f}]")
print(f"  σ above 2.0: {sig_above_2:.1f}")
print(f"  C = {np.mean(C_boots):.4f} [{ci_C[0]:.4f}, {ci_C[1]:.4f}]")

# ─── Block analysis ──────────────────────────────────────────────
print(f"\n[7] Block analysis (10 blocks of 20)...")
block_size = 20
n_blocks = len(M_trials) // block_size
S_blocks, C_blocks = [], []
for i in range(n_blocks):
    block = M_trials[i*block_size:(i+1)*block_size]
    Mb = np.mean(block, axis=0)
    Mb = Mb / np.linalg.norm(Mb, 'fro')
    S_blocks.append(S_chsh_real(Mb, params_opt))
    _, sig_b, _ = np.linalg.svd(Mb)
    C_blocks.append(2*sig_b[0]*sig_b[1] / (sig_b[0]**2 + sig_b[1]**2))

S_blocks = np.array(S_blocks); C_blocks = np.array(C_blocks)
print(f"  S per block: {np.round(S_blocks, 4)}")
print(f"  S mean ± SEM: {np.mean(S_blocks):.4f} ± {np.std(S_blocks)/np.sqrt(n_blocks):.4f}")
print(f"  Blocks with S > 2.0: {np.sum(S_blocks > 2.0)}/{n_blocks}")

# ─── Verdict ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  T5.2 CHSH — DUAL-CHANNEL RESULTS")
print("=" * 60)
print(f"  TX:  SW PZT (Pico NCO, separate board)")
print(f"  RX:  Ch A = NW (preamp) | Ch B = NE (direct)")
print(f"  Concurrence:  {C:.4f} [{ci_C[0]:.4f}, {ci_C[1]:.4f}]")
print(f"  S (point):    {S_opt:.4f}")
print(f"  S (boot):     {np.mean(S_boots):.4f} ± {np.std(S_boots):.4f}")
print(f"  S (95% CI):   [{ci_S[0]:.4f}, {ci_S[1]:.4f}]")
print(f"  σ above 2.0:  {sig_above_2:.1f}")
print(f"  Blocks > 2.0: {np.sum(S_blocks>2)}/{n_blocks}")
print()

if ci_S[0] > 2.0:
    verdict = 'PASS'
    print("  ★★ PASS — S > 2.0 at 95% confidence!")
    print("  The plate freq×space state is NON-SEPARABLE.")
elif np.mean(S_boots) > 2.0 and sig_above_2 > 2.0:
    verdict = 'PASS_2SIGMA'
    print(f"  ★ PASS (2σ) — S > 2.0 at {sig_above_2:.1f}σ")
elif np.mean(S_boots) > 2.0 and sig_above_2 > 1.0:
    verdict = 'MARGINAL_1SIGMA'
    print(f"  △ Marginal — S > 2.0 at {sig_above_2:.1f}σ (need more trials)")
elif S_opt > 2.0:
    verdict = 'MARGINAL'
    print("  △ Marginal — Point estimate > 2.0, CI includes 2.0")
else:
    verdict = 'FAIL'
    print("  ✗ FAIL — S ≤ 2.0")

# ─── Save ─────────────────────────────────────────────────────────
DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/quantum_bridge')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = DATA_DIR / f't5_2_chsh_dual_ch_{ts}.json'

results = {
    'test': 'T5.2_CHSH_dual_channel',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'modes': [F1, F2],
        'rx_channels': {'A': 'NW_preamp', 'B': 'NE_direct'},
        'n_trials': NTRIALS, 'n_avg': NAVG,
        'ch_a_range_mV': RNG_A_MV, 'ch_b_range_mV': RNG_B_MV,
        'drive': 'simultaneous_continuous',
        'relay_switching': False,
    },
    'state_matrix': M_avg.tolist(),
    'svd_sigma': [float(s) for s in sigma],
    'concurrence': float(C), 'concurrence_ci_95': ci_C,
    'S_optimal': float(S_opt), 'S_theory_max': float(S_theory),
    'optimal_angles_deg': {
        'alice': [float(np.degrees(a1)), float(np.degrees(a2))],
        'bob': [float(np.degrees(b1)), float(np.degrees(b2))],
    },
    'bootstrap': {
        'S_mean': float(np.mean(S_boots)), 'S_std': float(np.std(S_boots)),
        'S_ci_95': ci_S, 'sigma_above_2': float(sig_above_2),
    },
    'blocks': {
        'S_values': S_blocks.tolist(), 'C_values': C_blocks.tolist(),
        'S_mean': float(np.mean(S_blocks)),
        'S_sem': float(np.std(S_blocks) / np.sqrt(n_blocks)),
    },
    'signal_levels': {
        'f1_chA': float(np.mean(trials[:,0])),
        'f1_chB': float(np.mean(trials[:,1])),
        'f2_chA': float(np.mean(trials[:,2])),
        'f2_chB': float(np.mean(trials[:,3])),
    },
    'spatial_ratios': {
        'f1_NE_over_NW': float(np.mean(r_f1)),
        'f2_NE_over_NW': float(np.mean(r_f2)),
    },
    'verdict': verdict,
}
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\n  Saved: {out_path}")

# ─── Cleanup ──────────────────────────────────────────────────────
ser.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
print("  Hardware released.")
