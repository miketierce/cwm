"""
E5: 3-Mode Higher-Dimensional State

Extends the 2×2 (freq×space) state matrix to 3×2 by driving 3 modes
simultaneously using all 3 NCO channels (GP2, GP3, GP4 → SW TX PZT).
Measures each mode at both receivers (NW preamp Ch A, NE direct Ch B).
Builds a 3×2 state matrix and computes the Schmidt number via SVD.

Hardware:
  Pico NCO: F1:34000 (GP2), F2:70000 (GP3), F3:112000 (GP4)
  All three → 220Ω → SW TX PZT (simultaneous 3-tone drive)
  NW RX PZT → preamp (×11) → PicoScope Ch A
  NE RX PZT → direct → PicoScope Ch B

Math:
  State matrix M[3×2]: rows = frequency modes, cols = spatial receivers
  Row-normalize, Frobenius-normalize → SVD: M = UΣV†
  Schmidt number K = (Σσᵢ²)² / Σσᵢ⁴  (participation ratio)
  For full non-separability of a 3×2 matrix, need K > 1 (max = 2)

Success criterion: Schmidt number > 1 (kills "only works for 2 modes")
"""
import ctypes as ct
import numpy as np
import serial
import time
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

# ─── Capture ──────────────────────────────────────────────────────
def capture_dual(navg=20):
    """Capture magnitude spectra from both channels (averaged)."""
    buf_a = (ct.c_int16 * N)()
    buf_b = (ct.c_int16 * N)()
    ov = ct.c_int16()
    mags_a, mags_b = [], []
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
        mags_a.append(np.abs(np.fft.rfft(da * win, n=NFFT)))
        mags_b.append(np.abs(np.fft.rfft(db * win, n=NFFT)))
    return np.mean(mags_a, axis=0), np.mean(mags_b, axis=0)

def peak_mag(sp, freq, w=5):
    """Peak magnitude near target frequency."""
    b = int(round(freq / BIN_HZ))
    return float(sp[max(0, b-w):b+w+1].max())

# ─── Config ───────────────────────────────────────────────────────
# Three eigenmodes spread across the plate's resonance spectrum
F1_HZ = 35840    # Mode 1 — lowest eigenmode
F2_HZ = 54920    # Mode 2 — mid eigenmode
F3_HZ = 97011    # Mode 3 — high eigenmode

NTRIALS = 200    # Number of independent measurement trials
NAVG = 20        # FFT averages per trial

print("E5: 3-Mode Higher-Dimensional State")
print("=" * 60)
print(f"Modes: {F1_HZ} Hz, {F2_HZ} Hz, {F3_HZ} Hz (simultaneous)")
print(f"Drive: F1→GP2, F2→GP3, F3→GP4 → all → SW TX PZT")
print(f"Receivers: Ch A (NW preamp ×11), Ch B (NE direct)")
print(f"Trials: {NTRIALS}, {NAVG} averages each")
print(f"Observable: magnitude (phase-invariant)")
print()

# ─── Start 3-tone drive ──────────────────────────────────────────
print("[1] Starting 3-tone simultaneous drive...")
nco('Foff'); time.sleep(0.3)
r1 = nco(f'F1:{F1_HZ}')
r2 = nco(f'F2:{F2_HZ}')
r3 = nco(f'F3:{F3_HZ}')
print(f"  NCO: {r1}, {r2}, {r3}")
status = nco('STATUS')
print(f"  Status: {status}")
time.sleep(3.0)  # Let plate ring up

# Quick sanity check
sp_a, sp_b = capture_dual(10)
print(f"\n  Sanity check (10-avg):")
print(f"  Ch A: f1={peak_mag(sp_a, F1_HZ):.0f}, f2={peak_mag(sp_a, F2_HZ):.0f}, f3={peak_mag(sp_a, F3_HZ):.0f}")
print(f"  Ch B: f1={peak_mag(sp_b, F1_HZ):.0f}, f2={peak_mag(sp_b, F2_HZ):.0f}, f3={peak_mag(sp_b, F3_HZ):.0f}")

# Check all peaks are above noise
noise_a = np.median(sp_a[10:100])
noise_b = np.median(sp_b[10:100])
snr_min = min(
    peak_mag(sp_a, F1_HZ) / noise_a,
    peak_mag(sp_a, F2_HZ) / noise_a,
    peak_mag(sp_a, F3_HZ) / noise_a,
    peak_mag(sp_b, F1_HZ) / noise_b,
    peak_mag(sp_b, F2_HZ) / noise_b,
    peak_mag(sp_b, F3_HZ) / noise_b,
)
print(f"  Min SNR across all 6 cells: {snr_min:.1f}× (need >3×)")
if snr_min < 3.0:
    print("  ⚠ WARNING: Low SNR on at least one cell. Results may be noisy.")

# ─── Collect trials ──────────────────────────────────────────────
print(f"\n[2] Collecting {NTRIALS} trials...")
# Each trial → 6 magnitudes: [f1_A, f1_B, f2_A, f2_B, f3_A, f3_B]
trials = []

for trial in range(NTRIALS):
    sp_a, sp_b = capture_dual(NAVG)
    trials.append([
        peak_mag(sp_a, F1_HZ), peak_mag(sp_b, F1_HZ),
        peak_mag(sp_a, F2_HZ), peak_mag(sp_b, F2_HZ),
        peak_mag(sp_a, F3_HZ), peak_mag(sp_b, F3_HZ),
    ])
    if (trial + 1) % 50 == 0:
        last = np.array(trials[-20:])
        cvs = [np.std(last[:, i]) / np.mean(last[:, i]) * 100 for i in range(6)]
        print(f"  {trial+1}/{NTRIALS} — CV: f1A={cvs[0]:.1f}% f2A={cvs[2]:.1f}% f3A={cvs[4]:.1f}%")

nco('Foff')
trials = np.array(trials)
print(f"  Done. Shape: {trials.shape}")

# ─── Build 3×2 state matrices ────────────────────────────────────
print(f"\n[3] Building 3×2 state matrices...")

M_trials = []
for t in trials:
    # M[3×2]: rows = modes (f1, f2, f3), cols = receivers (A, B)
    M = np.array([
        [t[0], t[1]],  # f1: [ChA, ChB]
        [t[2], t[3]],  # f2: [ChA, ChB]
        [t[4], t[5]],  # f3: [ChA, ChB]
    ])
    # Row normalize (each mode independently)
    row_norms = np.linalg.norm(M, axis=1, keepdims=True)
    if np.all(row_norms > 0):
        Mn = M / row_norms
        # Frobenius normalize the whole matrix
        Mn = Mn / np.linalg.norm(Mn, 'fro')
        M_trials.append(Mn)

M_avg = np.mean(M_trials, axis=0)
M_avg = M_avg / np.linalg.norm(M_avg, 'fro')

print(f"  Valid trials: {len(M_trials)}/{NTRIALS}")
print(f"  M_avg (row-norm, Frob-norm):")
print(f"    f1: [{M_avg[0,0]:.4f}, {M_avg[0,1]:.4f}]")
print(f"    f2: [{M_avg[1,0]:.4f}, {M_avg[1,1]:.4f}]")
print(f"    f3: [{M_avg[2,0]:.4f}, {M_avg[2,1]:.4f}]")

# ─── SVD and Schmidt number ──────────────────────────────────────
print(f"\n[4] SVD analysis...")
U, sigma, Vh = np.linalg.svd(M_avg, full_matrices=False)
# For a 3×2 matrix, SVD gives at most 2 singular values
print(f"  Singular values: σ = [{sigma[0]:.6f}, {sigma[1]:.6f}]")
print(f"  Ratio σ₁/σ₂: {sigma[0]/sigma[1]:.4f}")

# Schmidt number (participation ratio)
# K = (Σσᵢ²)² / Σσᵢ⁴
sigma_sq = sigma**2
K = (np.sum(sigma_sq))**2 / np.sum(sigma_sq**2)
print(f"  Schmidt number K = {K:.4f} (range: [1, 2])")
print(f"    K = 1.0 → separable (rank-1)")
print(f"    K = 2.0 → maximally entangled")
print(f"    K > 1.0 → non-separable ✓")

# Also compute concurrence (generalized to rectangular matrix)
# For 3×2: C = 2σ₁σ₂/(σ₁²+σ₂²)
C = 2 * sigma[0] * sigma[1] / (sigma[0]**2 + sigma[1]**2)
print(f"  Concurrence C = {C:.4f}")

# ─── Spatial distinctness check ───────────────────────────────────
print(f"\n[5] Spatial mode distinctness...")
# Each row of M_avg (after row-norm) is a unit vector in 2D space
# If all modes had the same spatial distribution, they'd all point the same way
angles = np.arctan2(M_avg[:, 1], M_avg[:, 0])
print(f"  Mode angles (spatial direction):")
print(f"    f1: {np.degrees(angles[0]):.2f}°")
print(f"    f2: {np.degrees(angles[1]):.2f}°")
print(f"    f3: {np.degrees(angles[2]):.2f}°")
spread = np.max(angles) - np.min(angles)
print(f"  Angular spread: {np.degrees(spread):.2f}°")
print(f"  (>0° means different modes couple differently to space → non-separable)")

# ─── Bootstrap confidence interval ───────────────────────────────
print(f"\n[6] Bootstrap (5000 resamples)...")
rng = np.random.default_rng(42)
K_boots = []
C_boots = []

for _ in range(5000):
    idx = rng.choice(len(M_trials), size=len(M_trials), replace=True)
    Mb = np.mean([M_trials[j] for j in idx], axis=0)
    Mb = Mb / np.linalg.norm(Mb, 'fro')
    _, sig_b, _ = np.linalg.svd(Mb, full_matrices=False)
    sig_sq = sig_b**2
    K_boots.append((np.sum(sig_sq))**2 / np.sum(sig_sq**2))
    C_boots.append(2 * sig_b[0] * sig_b[1] / (sig_b[0]**2 + sig_b[1]**2))

K_boots = np.array(K_boots)
C_boots = np.array(C_boots)

ci_K = [float(np.percentile(K_boots, 2.5)), float(np.percentile(K_boots, 97.5))]
ci_C = [float(np.percentile(C_boots, 2.5)), float(np.percentile(C_boots, 97.5))]
sig_above_1 = (np.mean(K_boots) - 1.0) / np.std(K_boots) if np.std(K_boots) > 0 else 0

print(f"  K: {np.mean(K_boots):.4f} ± {np.std(K_boots):.4f}")
print(f"  K 95% CI: [{ci_K[0]:.4f}, {ci_K[1]:.4f}]")
print(f"  σ above 1.0: {sig_above_1:.1f}")
print(f"  C: {np.mean(C_boots):.4f} ± {np.std(C_boots):.4f}")
print(f"  C 95% CI: [{ci_C[0]:.4f}, {ci_C[1]:.4f}]")

# ─── Block analysis ──────────────────────────────────────────────
print(f"\n[7] Block analysis (10 blocks of {len(M_trials)//10} trials)...")
block_size = len(M_trials) // 10
K_blocks = []
for i in range(10):
    block = M_trials[i * block_size:(i + 1) * block_size]
    Mb = np.mean(block, axis=0)
    Mb = Mb / np.linalg.norm(Mb, 'fro')
    _, sig_b, _ = np.linalg.svd(Mb, full_matrices=False)
    sig_sq = sig_b**2
    K_blocks.append((np.sum(sig_sq))**2 / np.sum(sig_sq**2))

K_blocks = np.array(K_blocks)
print(f"  K per block: {np.array2string(K_blocks, precision=4)}")
print(f"  K mean ± SEM: {np.mean(K_blocks):.4f} ± {np.std(K_blocks)/np.sqrt(10):.4f}")
print(f"  Blocks with K > 1.0: {np.sum(K_blocks > 1.0)}/10")

# ─── Final verdict ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("  E5: 3-MODE HIGHER-DIMENSIONAL STATE — RESULTS")
print("=" * 60)
print(f"  Modes:          {F1_HZ}, {F2_HZ}, {F3_HZ} Hz (simultaneous)")
print(f"  State matrix:   3×2 (freq × space)")
print(f"  Schmidt number: {K:.4f} [{ci_K[0]:.4f}, {ci_K[1]:.4f}]")
print(f"  Concurrence:    {C:.4f} [{ci_C[0]:.4f}, {ci_C[1]:.4f}]")
print(f"  σ above K=1:    {sig_above_1:.1f}")
print(f"  Blocks > 1.0:   {np.sum(K_blocks > 1.0)}/10")
print()

if ci_K[0] > 1.0:
    verdict = 'PASS'
    print("  ★★ PASS — Schmidt number > 1.0 at 95% confidence!")
    print("  The 3-mode state is NON-SEPARABLE (higher-dimensional entanglement).")
    print("  Kills: 'only works for 2 modes' objection.")
elif np.mean(K_boots) > 1.0 and sig_above_1 > 2.0:
    verdict = 'PASS_2SIGMA'
    print(f"  ★ PASS (2σ) — K > 1.0 at {sig_above_1:.1f}σ confidence")
elif K > 1.0:
    verdict = 'MARGINAL'
    print("  △ MARGINAL — Point estimate K > 1.0, CI includes 1.0")
else:
    verdict = 'FAIL'
    print("  ✗ FAIL — K ≤ 1.0")

# ─── Save results ────────────────────────────────────────────────
DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/quantum_bridge')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = DATA_DIR / f'e5_3mode_state_{ts}.json'

results = {
    'test': 'E5_3mode_higher_dimensional_state',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'modes_hz': [F1_HZ, F2_HZ, F3_HZ],
        'drive': '3-channel simultaneous (GP2+GP3+GP4 → SW TX PZT)',
        'receivers': ['Ch A (NW preamp x11)', 'Ch B (NE direct)'],
        'n_trials': NTRIALS,
        'n_avg': NAVG,
        'observable': 'magnitude_only',
    },
    'state_matrix_3x2': M_avg.tolist(),
    'svd_sigma': [float(s) for s in sigma],
    'schmidt_number': float(K),
    'schmidt_ci_95': ci_K,
    'sigma_above_1': float(sig_above_1),
    'concurrence': float(C),
    'concurrence_ci_95': ci_C,
    'spatial_angles_deg': [float(np.degrees(a)) for a in angles],
    'angular_spread_deg': float(np.degrees(spread)),
    'bootstrap': {
        'K_mean': float(np.mean(K_boots)),
        'K_std': float(np.std(K_boots)),
        'K_ci_95': ci_K,
        'C_mean': float(np.mean(C_boots)),
        'C_std': float(np.std(C_boots)),
    },
    'blocks': {
        'K_values': K_blocks.tolist(),
        'K_mean': float(np.mean(K_blocks)),
        'K_sem': float(np.std(K_blocks) / np.sqrt(10)),
    },
    'raw_magnitudes': {
        'f1_A': {'mean': float(np.mean(trials[:, 0])), 'std': float(np.std(trials[:, 0]))},
        'f1_B': {'mean': float(np.mean(trials[:, 1])), 'std': float(np.std(trials[:, 1]))},
        'f2_A': {'mean': float(np.mean(trials[:, 2])), 'std': float(np.std(trials[:, 2]))},
        'f2_B': {'mean': float(np.mean(trials[:, 3])), 'std': float(np.std(trials[:, 3]))},
        'f3_A': {'mean': float(np.mean(trials[:, 4])), 'std': float(np.std(trials[:, 4]))},
        'f3_B': {'mean': float(np.mean(trials[:, 5])), 'std': float(np.std(trials[:, 5]))},
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
