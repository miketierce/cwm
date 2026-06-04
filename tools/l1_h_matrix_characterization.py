"""
L1: H Matrix Characterization (Full Transfer Matrix)
=====================================================

Sweep a single tone across 30–120 kHz in fine steps. At each frequency,
measure magnitude response at both spatial channels (NW preamp, NE direct).
Build N×2 transfer matrix H where rows = modes, columns = spatial positions.

Compute SVD, effective rank, condition number, concurrence per mode pair.

Hardware (same as E3):
  TX: Pico NCO GP2 (single tone, F1:freq)
  RX: Ch A = NW preamp (×11), Ch B = NE direct
  No relay switching — dual-channel simultaneous capture.

Success criteria (from worklist):
  - ≥ 8 modes with SNR > 10× above noise
  - Effective rank > 2
  - Condition number < 100

Output:
  - data/results/h_matrix/l1_h_matrix_TIMESTAMP.json (full results)
  - data/results/h_matrix/l1_h_matrix_TIMESTAMP.npz (spectra for reanalysis)
  - Console summary with mode table, SVD, rank

Usage:
  python3 tools/l1_h_matrix_characterization.py
  python3 tools/l1_h_matrix_characterization.py --start 20000 --stop 150000 --step 500
  python3 tools/l1_h_matrix_characterization.py --fine  # 200 Hz steps around known modes
"""
import ctypes as ct
import numpy as np
import serial
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

# ─── Args ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='L1: H matrix characterization')
parser.add_argument('--start', type=int, default=30000,
                    help='Start frequency Hz (default: 30000)')
parser.add_argument('--stop', type=int, default=120000,
                    help='Stop frequency Hz (default: 120000)')
parser.add_argument('--step', type=int, default=1000,
                    help='Frequency step Hz (default: 1000)')
parser.add_argument('--navg', type=int, default=20,
                    help='Captures averaged per point (default: 20)')
parser.add_argument('--settle', type=float, default=0.3,
                    help='Settle time (s) after freq change (default: 0.3)')
parser.add_argument('--snr-threshold', type=float, default=10.0,
                    help='SNR (linear) threshold for mode detection (default: 10)')
parser.add_argument('--fine', action='store_true',
                    help='Fine sweep: 200 Hz steps, 30-120 kHz')
args = parser.parse_args()

if args.fine:
    args.step = 200

FREQS = list(range(args.start, args.stop + 1, args.step))
N_FREQS = len(FREQS)

print("=" * 70)
print("  L1: H Matrix Characterization — Full Mode Sweep")
print("=" * 70)
print(f"  Range: {args.start/1000:.1f} – {args.stop/1000:.1f} kHz")
print(f"  Step: {args.step} Hz ({N_FREQS} frequencies)")
print(f"  Averaging: {args.navg} captures/point")
print(f"  Settle: {args.settle}s per freq")
est_time = N_FREQS * (args.navg * 0.012 + args.settle + 0.1)
print(f"  Estimated time: {est_time:.0f}s ({est_time/60:.1f} min)")
print()

# ─── PicoScope ────────────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
ps = ct.CDLL(PICO_LIB)
ps.ps2000_close_unit(ct.c_int16(1))
time.sleep(0.3)

N = 3968; TIMEBASE = 7
FS = 781250.0; NFFT = N * 4; BIN_HZ = FS / NFFT

RNG_A = 6; RNG_A_MV = 2000.0   # Ch A: ±2V (preamp)
RNG_B = 6; RNG_B_MV = 2000.0   # Ch B: ±2V (direct)

ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
if h <= 0:
    print(f"ERROR: PicoScope open failed (handle={h})")
    raise SystemExit(1)
print(f"  PicoScope handle: {h}")

ps.ps2000_set_channel(h, 0, 1, 0, RNG_A)   # Ch A: NW preamp (AC coupled)
ps.ps2000_set_channel(h, 1, 1, 0, RNG_B)   # Ch B: NE direct (AC coupled)

# ─── Pico NCO ─────────────────────────────────────────────────────
ser = serial.Serial('/dev/cu.usbmodem113301', 115200, timeout=2)
time.sleep(0.5)
ser.reset_input_buffer()


def nco(cmd):
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()


def nco_temp():
    resp = nco('TEMP')
    try:
        parts = resp.split()
        return float(parts[0].split(':')[1].rstrip('C'))
    except (IndexError, ValueError):
        return None


# ─── Capture ──────────────────────────────────────────────────────
def capture_dual(navg):
    """Capture dual-channel magnitude spectra (averaged)."""
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
    """Get peak magnitude near target frequency."""
    b = int(round(freq / BIN_HZ))
    return float(sp[max(0, b-w):b+w+1].max())


# ─── Step 1: Noise baseline ──────────────────────────────────────
print("[1] Measuring noise baseline (NCO off)...")
nco('Foff')
time.sleep(0.5)
noise_a, noise_b = capture_dual(args.navg)
noise_floor_a = float(np.median(noise_a))
noise_floor_b = float(np.median(noise_b))
print(f"  Ch A (NW preamp) noise floor: {noise_floor_a:.1f}")
print(f"  Ch B (NE direct) noise floor: {noise_floor_b:.1f}")

# ─── Step 2: Frequency sweep ─────────────────────────────────────
print(f"\n[2] Sweeping {N_FREQS} frequencies...")
results_a = np.zeros(N_FREQS)  # Peak magnitude at driven freq, Ch A
results_b = np.zeros(N_FREQS)  # Peak magnitude at driven freq, Ch B
all_spectra_a = []  # Full spectra for reanalysis
all_spectra_b = []

t0 = time.time()
for i, freq in enumerate(FREQS):
    nco(f'F1:{freq}')
    time.sleep(args.settle)

    sp_a, sp_b = capture_dual(args.navg)
    results_a[i] = peak_mag(sp_a, freq)
    results_b[i] = peak_mag(sp_b, freq)
    all_spectra_a.append(sp_a)
    all_spectra_b.append(sp_b)

    if (i + 1) % 10 == 0 or (i + 1) == N_FREQS:
        elapsed = time.time() - t0
        eta = elapsed / (i + 1) * (N_FREQS - i - 1)
        snr_a = results_a[i] / noise_floor_a if noise_floor_a > 0 else 0
        snr_b = results_b[i] / noise_floor_b if noise_floor_b > 0 else 0
        print(f"  {i+1}/{N_FREQS} — {freq/1000:.1f} kHz — "
              f"SNR(A)={snr_a:.1f}×, SNR(B)={snr_b:.1f}× — "
              f"ETA {eta:.0f}s")

nco('Foff')
elapsed_total = time.time() - t0
print(f"  Sweep complete in {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)")

# ─── Step 3: Mode detection ──────────────────────────────────────
print(f"\n[3] Detecting modes (SNR > {args.snr_threshold}× on either channel)...")

snr_a = results_a / noise_floor_a
snr_b = results_b / noise_floor_b
snr_max = np.maximum(snr_a, snr_b)

# Find peaks: local maxima above threshold
from scipy.signal import find_peaks

# Detect peaks on combined SNR
peaks_idx, peak_props = find_peaks(snr_max,
                                   height=args.snr_threshold,
                                   distance=max(1, 2000 // args.step),
                                   prominence=3.0)

modes = []
for idx in peaks_idx:
    freq = FREQS[idx]
    mag_a = results_a[idx]
    mag_b = results_b[idx]
    sa = snr_a[idx]
    sb = snr_b[idx]
    modes.append({
        'freq_hz': freq,
        'mag_a': float(mag_a),
        'mag_b': float(mag_b),
        'snr_a': float(sa),
        'snr_b': float(sb),
        'snr_max': float(max(sa, sb)),
        'ratio_b_over_a': float(mag_b / mag_a) if mag_a > 0 else 0,
    })

# Sort by frequency
modes.sort(key=lambda m: m['freq_hz'])
n_modes = len(modes)

print(f"\n  Detected {n_modes} modes above {args.snr_threshold}× threshold:")
print(f"  {'Freq (Hz)':>10} {'SNR_A':>7} {'SNR_B':>7} {'B/A ratio':>9} {'Spatial':>10}")
print(f"  {'-'*10} {'-'*7} {'-'*7} {'-'*9} {'-'*10}")
for m in modes:
    r = m['ratio_b_over_a']
    spatial = 'NW-dom' if r < 0.5 else ('NE-dom' if r > 2.0 else 'balanced')
    print(f"  {m['freq_hz']:>10,} {m['snr_a']:>7.1f} {m['snr_b']:>7.1f} "
          f"{r:>9.3f} {spatial:>10}")

# ─── Step 4: Build H matrix ──────────────────────────────────────
print(f"\n[4] Building H matrix ({n_modes} × 2)...")

if n_modes < 2:
    print("  ERROR: Need at least 2 modes for H matrix. Aborting.")
    ser.close()
    ps.ps2000_stop(h)
    ps.ps2000_close_unit(ct.c_int16(h))
    raise SystemExit(1)

# H[i, 0] = magnitude at Ch A (NW) for mode i
# H[i, 1] = magnitude at Ch B (NE) for mode i
H_raw = np.array([[m['mag_a'], m['mag_b']] for m in modes])

# Normalize: each row by its L2 norm (unit spatial vector per mode)
row_norms = np.linalg.norm(H_raw, axis=1, keepdims=True)
H_norm = H_raw / row_norms

# Also compute Frobenius-normalized version
H_frob = H_raw / np.linalg.norm(H_raw, 'fro')

print(f"  H_raw shape: {H_raw.shape}")
print(f"  H_norm (row-normalized):")
for i, m in enumerate(modes):
    print(f"    mode {i} ({m['freq_hz']/1000:.1f} kHz): "
          f"[{H_norm[i,0]:.4f}, {H_norm[i,1]:.4f}]")

# ─── Step 5: SVD analysis ────────────────────────────────────────
print(f"\n[5] SVD analysis...")

U, sigma, Vh = np.linalg.svd(H_raw, full_matrices=False)
sigma_norm = sigma / sigma[0]  # Normalized singular values

# Effective rank (number of singular values > 1% of max)
eff_rank_01 = int(np.sum(sigma > 0.01 * sigma[0]))
# Effective rank via entropy
sigma_sq = sigma**2 / np.sum(sigma**2)
entropy = -np.sum(sigma_sq * np.log2(sigma_sq + 1e-15))
eff_rank_entropy = 2**entropy

# Condition number
cond_number = sigma[0] / sigma[-1] if sigma[-1] > 0 else np.inf

print(f"  Singular values: {sigma}")
print(f"  Normalized: {sigma_norm}")
print(f"  Effective rank (1% threshold): {eff_rank_01}")
print(f"  Effective rank (entropy): {eff_rank_entropy:.2f}")
print(f"  Condition number: {cond_number:.2f}")

# For Nx2 matrix, max rank is 2
print(f"  (Note: max rank for Nx2 matrix is 2)")

# ─── Step 6: Pairwise concurrence ────────────────────────────────
print(f"\n[6] Pairwise concurrence (all 2×2 submatrices)...")

pair_results = []
for i in range(n_modes):
    for j in range(i+1, n_modes):
        # 2×2 submatrix from modes i and j
        M = H_raw[[i, j], :]
        M_n = M / np.linalg.norm(M, 'fro')
        _, sig2, _ = np.linalg.svd(M_n)
        C = 2 * sig2[0] * sig2[1] / (sig2[0]**2 + sig2[1]**2)
        S_max = 2 * np.sqrt(1 + C**2)
        pair_results.append({
            'mode_i': i, 'mode_j': j,
            'freq_i': modes[i]['freq_hz'],
            'freq_j': modes[j]['freq_hz'],
            'concurrence': float(C),
            'S_max': float(S_max),
        })

pair_results.sort(key=lambda p: -p['concurrence'])

print(f"  Top 10 mode pairs by concurrence:")
print(f"  {'Mode i':>8} {'Mode j':>8} {'Freq i':>8} {'Freq j':>8} {'C':>6} {'S_max':>6}")
for p in pair_results[:10]:
    print(f"  {p['mode_i']:>8} {p['mode_j']:>8} "
          f"{p['freq_i']:>8,} {p['freq_j']:>8,} "
          f"{p['concurrence']:>6.4f} {p['S_max']:>6.4f}")

# Best pair for downstream use
best_pair = pair_results[0]
print(f"\n  ★ Best pair: {best_pair['freq_i']/1000:.1f} + {best_pair['freq_j']/1000:.1f} kHz")
print(f"    Concurrence: {best_pair['concurrence']:.4f}")
print(f"    S_max (theoretical): {best_pair['S_max']:.4f}")

# ─── Step 7: Temperature ─────────────────────────────────────────
temp = nco_temp()
print(f"\n[7] NCO temperature: {temp}°C" if temp else "\n[7] Temperature: N/A")

# ─── Results summary ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("  L1 RESULTS SUMMARY")
print("=" * 70)
print(f"  Modes detected:     {n_modes} (criterion: ≥ 8)")
print(f"  Effective rank:     {eff_rank_01} (criterion: > 2) [max=2 for N×2]")
print(f"  Condition number:   {cond_number:.2f} (criterion: < 100)")
print(f"  Best concurrence:   {best_pair['concurrence']:.4f}")
print(f"  Best S_max:         {best_pair['S_max']:.4f}")
print()

# Verdict
pass_modes = n_modes >= 8
pass_rank = eff_rank_01 >= 2
pass_cond = cond_number < 100
all_pass = pass_modes and pass_rank and pass_cond

verdict = "PASS" if all_pass else "PARTIAL"
print(f"  Modes ≥ 8:   {'PASS' if pass_modes else 'FAIL'} ({n_modes})")
print(f"  Rank > 2:    {'PASS' if pass_rank else f'N/A (Nx2 max=2, got {eff_rank_01}'}")
print(f"  Cond < 100:  {'PASS' if pass_cond else 'FAIL'} ({cond_number:.1f})")
print(f"\n  VERDICT: {verdict}")

# ─── Save results ────────────────────────────────────────────────
DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/h_matrix')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')

# JSON results
json_path = DATA_DIR / f'l1_h_matrix_{ts}.json'
json_results = {
    'test': 'L1_H_Matrix_Characterization',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'start_hz': args.start, 'stop_hz': args.stop, 'step_hz': args.step,
        'n_avg': args.navg, 'settle_s': args.settle,
        'snr_threshold': args.snr_threshold,
        'n_frequencies_swept': N_FREQS,
    },
    'noise_floor': {'ch_a': noise_floor_a, 'ch_b': noise_floor_b},
    'modes': modes,
    'n_modes': n_modes,
    'H_raw': H_raw.tolist(),
    'H_norm': H_norm.tolist(),
    'svd': {
        'sigma': [float(s) for s in sigma],
        'sigma_normalized': [float(s) for s in sigma_norm],
        'effective_rank_01pct': eff_rank_01,
        'effective_rank_entropy': float(eff_rank_entropy),
        'condition_number': float(cond_number),
        'U': U.tolist(),
        'Vh': Vh.tolist(),
    },
    'pairwise_concurrence': pair_results[:20],  # Top 20
    'best_pair': best_pair,
    'temperature_c': temp,
    'elapsed_s': elapsed_total,
    'verdict': verdict,
}
with open(json_path, 'w') as f:
    json.dump(json_results, f, indent=2)
print(f"\n  Saved: {json_path}")

# NPZ for reanalysis (full spectra)
npz_path = DATA_DIR / f'l1_h_matrix_{ts}.npz'
np.savez_compressed(npz_path,
                    freqs=np.array(FREQS),
                    results_a=results_a, results_b=results_b,
                    noise_a=noise_a, noise_b=noise_b,
                    spectra_a=np.array(all_spectra_a),
                    spectra_b=np.array(all_spectra_b),
                    H_raw=H_raw, H_norm=H_norm,
                    sigma=sigma)
print(f"  Saved: {npz_path}")

# ─── Cleanup ─────────────────────────────────────────────────────
ser.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
print("\n  Done. Hardware released.")
