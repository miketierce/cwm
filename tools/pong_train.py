#!/usr/bin/env python3
"""
Pong on Glass — Training Pipeline
==================================

Collects physical kernel responses for all 256 Pong game states,
computes optimal paddle targets, and trains a ridge regression readout.

Prerequisites:
  - Direct-wire census completed (data/results/direct_wire_census/*.json)
  - 8 RX PZTs wired direct to preamp → PicoScope Ch A
  - NCO can drive at least 1 TX channel

Pipeline:
  1. Load census → get usable mode frequencies
  2. Define 256 game states (ball_x, ball_y, vx, vy)
  3. Encode each state as a drive frequency
  4. Collect physical responses (256 × 1 FFT = ~4 seconds)
  5. Compute optimal paddle targets (ball trajectory simulation)
  6. Train ridge regression: gradient → paddle_y
  7. Cross-validate and report accuracy
  8. Save weights for live game

Usage:
  python3 tools/pong_train.py --nco-port /dev/cu.usbmodem113401
  python3 tools/pong_train.py --census data/results/direct_wire_census/direct_wire_census_20260620_210434.json
"""

import ctypes as ct
import numpy as np
import json
import time
import argparse
import sys
from pathlib import Path
from datetime import datetime

# ─── Args ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Pong on Glass — Training Pipeline')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--census', type=str, default=None,
                    help='Path to census JSON (auto-detects latest if omitted)')
parser.add_argument('--tx', type=str, default='F1',
                    help='TX channel for state encoding (default: F1)')
parser.add_argument('--navg', type=int, default=8,
                    help='FFT captures averaged per state (default: 8)')
parser.add_argument('--settle', type=float, default=0.03,
                    help='Settle time after freq change (default: 0.03s)')
parser.add_argument('--alpha', type=float, default=0.1,
                    help='Ridge regression alpha (default: 0.1)')
parser.add_argument('--dry-run', action='store_true',
                    help='Skip physical capture, use synthetic data for testing')
args = parser.parse_args()

# ─── Constants ────────────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
RNG = 6
RNG_MV = 1000.0

# Pong game parameters
COURT_W, COURT_H = 8, 8
N_STATES = COURT_W * COURT_H * 2 * 2  # 8×8×2×2 = 256

# Frequency encoding range (must be within census bandwidth)
FREQ_START = 35000   # Hz — start of encoding range
FREQ_STOP = 140000   # Hz — end of encoding range

OUT_DIR = Path('data/results/pong')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')

# ─── Load Census ─────────────────────────────────────────────────
print("=" * 70)
print("  PONG ON GLASS — TRAINING PIPELINE")
print("=" * 70)

print("\n[1] Loading census data...")

if args.census:
    census_path = Path(args.census)
else:
    census_dir = Path('data/results/direct_wire_census')
    census_files = sorted(census_dir.glob('direct_wire_census_*.json'))
    if not census_files:
        print("  ERROR: No census files found. Run direct_wire_census.py first.")
        sys.exit(1)
    census_path = census_files[-1]  # latest

with open(census_path) as f:
    census = json.load(f)

usable_modes = census['usable_modes']
mode_freqs = np.array([m['freq_hz'] for m in usable_modes])
K = len(mode_freqs)

print(f"  Census: {census_path.name}")
print(f"  Usable modes: {K}")
print(f"  Frequency range: {mode_freqs[0]/1000:.1f} – {mode_freqs[-1]/1000:.1f} kHz")
print(f"  Kernel dimension: {K}")

if K < 8:
    print(f"  ERROR: Need at least 8 modes for Pong. Got {K}.")
    sys.exit(1)


# ─── Define Game States ──────────────────────────────────────────
print(f"\n[2] Defining {N_STATES} game states...")


def state_to_index(bx, by, vx, vy):
    """Encode (ball_x, ball_y, vx, vy) as a flat index 0–255."""
    vx_bit = 0 if vx == -1 else 1
    vy_bit = 0 if vy == -1 else 1
    return bx * 32 + by * 4 + vx_bit * 2 + vy_bit


def index_to_state(idx):
    """Decode flat index to (ball_x, ball_y, vx, vy)."""
    bx = idx // 32
    remainder = idx % 32
    by = remainder // 4
    remainder = remainder % 4
    vx_bit = remainder // 2
    vy_bit = remainder % 2
    vx = 1 if vx_bit else -1
    vy = 1 if vy_bit else -1
    return bx, by, vx, vy


# Verify encoding is bijective
assert all(state_to_index(*index_to_state(i)) == i for i in range(N_STATES))
print(f"  State encoding verified: {N_STATES} unique states ✓")


# ─── Encode States as Drive Frequencies ──────────────────────────
print(f"\n[3] Encoding states as drive frequencies...")

# Map 256 states to 256 evenly-spaced frequencies in the working band
state_freqs = np.linspace(FREQ_START, FREQ_STOP, N_STATES)

print(f"  Encoding: linear frequency mapping")
print(f"  Range: {FREQ_START/1000:.1f} – {FREQ_STOP/1000:.1f} kHz")
print(f"  Step: {(FREQ_STOP - FREQ_START) / (N_STATES - 1):.0f} Hz between states")
print(f"  State 0 (0,0,-1,-1) → {state_freqs[0]/1000:.1f} kHz")
print(f"  State 255 (7,7,+1,+1) → {state_freqs[-1]/1000:.1f} kHz")


# ─── Compute Optimal Paddle Targets ─────────────────────────────
print(f"\n[4] Computing optimal paddle positions (ball trajectory sim)...")


def compute_optimal_paddle(bx, by, vx, vy):
    """Simulate ball forward to right wall (x=7), return y-intercept.
    If ball is moving left, simulate bounce off left wall then to right."""
    x, y = float(bx), float(by)

    # Simulate until ball reaches right wall
    max_steps = 30  # prevent infinite loops
    steps = 0
    while steps < max_steps:
        x += vx
        y += vy
        # Bounce off top/bottom
        if y < 0:
            y = -y
            vy = -vy
        if y > COURT_H - 1:
            y = 2 * (COURT_H - 1) - y
            vy = -vy
        # Bounce off left wall (ball returns)
        if x < 0:
            x = -x
            vx = -vx
        # Reached right wall
        if x >= COURT_W - 1:
            return np.clip(y, 0, COURT_H - 1)
        steps += 1

    # Fallback: aim for center
    return (COURT_H - 1) / 2.0


targets = np.zeros(N_STATES)
for idx in range(N_STATES):
    bx, by, vx, vy = index_to_state(idx)
    targets[idx] = compute_optimal_paddle(bx, by, vx, vy)

# Normalize targets to [0, 1]
targets_norm = targets / (COURT_H - 1)

print(f"  Targets computed: min={targets.min():.1f}, max={targets.max():.1f}, "
      f"mean={targets.mean():.1f}")
print(f"  Sample: state(6,3,+1,+1) → paddle_y={targets[state_to_index(6,3,1,1)]:.1f}")
print(f"  Sample: state(0,7,-1,-1) → paddle_y={targets[state_to_index(0,7,-1,-1)]:.1f}")


# ─── Physical Data Collection ────────────────────────────────────
print(f"\n[5] Collecting physical kernel responses...")

if args.dry_run:
    print("  [DRY RUN] Using synthetic data (no hardware)")
    # Simulate: each mode responds based on proximity to drive frequency
    Y = np.zeros((N_STATES, K))
    for idx in range(N_STATES):
        drive_freq = state_freqs[idx]
        for m, mode_freq in enumerate(mode_freqs):
            # Simulated Lorentzian response
            delta = abs(drive_freq - mode_freq)
            Q_sim = 200
            bw = mode_freq / Q_sim
            Y[idx, m] = 1.0 / (1.0 + (2 * delta / bw) ** 2)
    Y += np.random.randn(*Y.shape) * 0.05  # noise
    print(f"  Synthetic Y: shape={Y.shape}")
else:
    import serial

    # Init PicoScope
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"  ERROR: PicoScope open failed (handle={handle})")
        sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)   # Ch A: AC, ±1V
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)   # Ch B: off
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)  # free-run
    print(f"  PicoScope: handle={handle}")

    # Init NCO
    nco_ser = serial.Serial(args.nco_port, 115200, timeout=2)
    time.sleep(0.5)
    nco_ser.reset_input_buffer()
    print(f"  NCO: {args.nco_port}")

    def nco_cmd(cmd):
        nco_ser.reset_input_buffer()
        nco_ser.write(f'{cmd}\n'.encode())
        time.sleep(0.02)

    def nco_off():
        nco_cmd('Foff')

    def capture_spectrum():
        """Capture averaged magnitude spectrum."""
        buf = (ct.c_int16 * N_SAMPLES)()
        ov = ct.c_int16()
        mags = []
        for _ in range(args.navg):
            ticks = ct.c_int32()
            ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ticks))
            for _ in range(500):
                if ps.ps2000_ready(handle):
                    break
                time.sleep(0.002)
            else:
                continue
            ps.ps2000_get_values(handle, ct.byref(buf), None, None, None,
                                 ct.byref(ov), N_SAMPLES)
            d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
            d -= d.mean()
            mags.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES), n=NFFT)))
        if not mags:
            return np.zeros(NFFT // 2 + 1)
        return np.mean(mags, axis=0)

    def extract_mode_amplitudes(spectrum):
        """Extract amplitude at each usable mode frequency from FFT."""
        amplitudes = np.zeros(K)
        for m, freq in enumerate(mode_freqs):
            bin_idx = int(round(freq / BIN_HZ))
            search = 3  # ±3 bins
            lo = max(0, bin_idx - search)
            hi = min(len(spectrum), bin_idx + search + 1)
            amplitudes[m] = float(spectrum[lo:hi].max())
        return amplitudes

    # Collect data
    Y = np.zeros((N_STATES, K))
    t0 = time.time()

    print(f"  Collecting {N_STATES} states × {args.navg} avg...")
    print(f"  Estimated time: {N_STATES * (args.settle + args.navg * 0.012):.0f}s")

    for idx in range(N_STATES):
        drive_freq = int(state_freqs[idx])
        nco_cmd(f'{args.tx}:{drive_freq}')
        time.sleep(args.settle)
        spectrum = capture_spectrum()
        Y[idx, :] = extract_mode_amplitudes(spectrum)

        if (idx + 1) % 32 == 0 or (idx + 1) == N_STATES:
            elapsed = time.time() - t0
            eta = elapsed / (idx + 1) * (N_STATES - idx - 1)
            print(f"    {idx+1}/{N_STATES} — "
                  f"freq={drive_freq/1000:.1f} kHz — "
                  f"max_response={Y[idx].max():.0f} — "
                  f"ETA {eta:.0f}s")

    nco_off()
    elapsed_total = time.time() - t0
    print(f"  Collection complete: {elapsed_total:.1f}s ({elapsed_total/60:.1f} min)")

    # Cleanup hardware
    nco_ser.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))

print(f"  Y shape: {Y.shape} ({N_STATES} states × {K} modes)")


# ─── Preprocess ──────────────────────────────────────────────────
print(f"\n[6] Preprocessing kernel responses...")

# Zero-mean, unit-variance per column (mode)
Y_mean = Y.mean(axis=0)
Y_std = Y.std(axis=0)
Y_std[Y_std < 1e-10] = 1.0  # prevent div by zero for dead modes
Y_norm = (Y - Y_mean) / Y_std

# Check effective rank via SVD
U, S, Vt = np.linalg.svd(Y_norm, full_matrices=False)
energy = np.cumsum(S**2) / np.sum(S**2)
rank_90 = int(np.searchsorted(energy, 0.90)) + 1
rank_99 = int(np.searchsorted(energy, 0.99)) + 1
effective_rank = int(np.sum(S > S[0] * 0.01))

print(f"  Normalization: zero-mean, unit-variance per mode")
print(f"  SVD: top 5 singular values = {S[:5].round(1)}")
print(f"  Effective rank (1% threshold): {effective_rank}")
print(f"  Rank for 90% energy: {rank_90}")
print(f"  Rank for 99% energy: {rank_99}")

if effective_rank < 4:
    print(f"  ⚠️  Low rank ({effective_rank}) — kernel may not resolve game states well")


# ─── Train Ridge Regression ──────────────────────────────────────
print(f"\n[7] Training ridge regression (alpha={args.alpha})...")

# Ridge regression: w = (Y'Y + αI)^-1 Y't
I = np.eye(K)
YtY = Y_norm.T @ Y_norm
Ytt = Y_norm.T @ targets_norm
w = np.linalg.solve(YtY + args.alpha * I, Ytt)
bias = targets_norm.mean() - Y_norm.mean(axis=0) @ w

# Training predictions
predictions = Y_norm @ w + bias
predictions_court = predictions * (COURT_H - 1)
targets_court = targets

# Metrics
residuals = predictions_court - targets_court
rmse = np.sqrt(np.mean(residuals**2))
mae = np.mean(np.abs(residuals))
max_err = np.max(np.abs(residuals))

# Accuracy: within ±1 cell (paddle covers 3 cells)
within_1 = np.mean(np.abs(residuals) <= 1.0) * 100
within_2 = np.mean(np.abs(residuals) <= 2.0) * 100

print(f"  Weight vector: shape=({K},), norm={np.linalg.norm(w):.2f}")
print(f"  Training RMSE: {rmse:.2f} cells")
print(f"  Training MAE: {mae:.2f} cells")
print(f"  Max error: {max_err:.2f} cells")
print(f"  Within ±1 cell: {within_1:.0f}%")
print(f"  Within ±2 cells: {within_2:.0f}%")


# ─── Cross-Validation ────────────────────────────────────────────
print(f"\n[8] Cross-validation (4-fold)...")

n_folds = 4
fold_size = N_STATES // n_folds
cv_rmses = []

indices = np.arange(N_STATES)
np.random.seed(42)
np.random.shuffle(indices)

for fold in range(n_folds):
    test_idx = indices[fold * fold_size:(fold + 1) * fold_size]
    train_idx = np.setdiff1d(indices, test_idx)

    Y_train = Y_norm[train_idx]
    t_train = targets_norm[train_idx]
    Y_test = Y_norm[test_idx]
    t_test = targets[test_idx]

    # Train
    w_fold = np.linalg.solve(Y_train.T @ Y_train + args.alpha * I,
                              Y_train.T @ t_train)
    bias_fold = t_train.mean() - Y_train.mean(axis=0) @ w_fold

    # Predict
    pred_fold = (Y_test @ w_fold + bias_fold) * (COURT_H - 1)
    fold_rmse = np.sqrt(np.mean((pred_fold - t_test)**2))
    cv_rmses.append(fold_rmse)

cv_mean = np.mean(cv_rmses)
cv_std = np.std(cv_rmses)

print(f"  Fold RMSEs: {[f'{r:.2f}' for r in cv_rmses]}")
print(f"  CV RMSE: {cv_mean:.2f} ± {cv_std:.2f} cells")

if cv_mean < 1.0:
    print(f"  ✓ PASS: CV RMSE < 1.0 (paddle within 1 cell of optimal)")
elif cv_mean < 1.5:
    print(f"  ~ MARGINAL: CV RMSE < 1.5 (acceptable — paddle mostly correct)")
else:
    print(f"  ⚠️  HIGH ERROR: CV RMSE > 1.5 — kernel may not resolve states well")
    print(f"      Try: lower alpha, add more modes, or use multi-tone encoding")


# ─── Summary ─────────────────────────────────────────────────────
print(f"\n{'='*70}")
print(f"  TRAINING SUMMARY")
print(f"{'='*70}")
print(f"  Kernel dimension: {K}")
print(f"  Training RMSE: {rmse:.2f} cells (target < 1.0)")
print(f"  CV RMSE: {cv_mean:.2f} ± {cv_std:.2f} cells")
print(f"  Within ±1 cell: {within_1:.0f}%")

if cv_mean < 1.5:
    print(f"\n  ┌────────────────────────────────────────┐")
    print(f"  │  GLASS AI READY FOR PONG  ✓            │")
    print(f"  │  Expected intercept rate: ~{within_1:.0f}%         │")
    print(f"  └────────────────────────────────────────┘")
else:
    print(f"\n  ┌────────────────────────────────────────┐")
    print(f"  │  NEEDS IMPROVEMENT                     │")
    print(f"  │  Try: fix F3, lower alpha, more avg    │")
    print(f"  └────────────────────────────────────────┘")


# ─── Save Model ──────────────────────────────────────────────────
print(f"\n[9] Saving model...")

model = {
    'timestamp': TIMESTAMP,
    'census_file': str(census_path),
    'config': {
        'tx_channel': args.tx,
        'navg': args.navg,
        'settle_s': args.settle,
        'alpha': args.alpha,
        'freq_start': FREQ_START,
        'freq_stop': FREQ_STOP,
        'n_states': N_STATES,
        'court_w': COURT_W,
        'court_h': COURT_H,
        'kernel_dim': K,
        'nco_port': args.nco_port,
        'dry_run': args.dry_run,
    },
    'mode_freqs_hz': mode_freqs.tolist(),
    'state_freqs_hz': state_freqs.tolist(),
    'normalization': {
        'y_mean': Y_mean.tolist(),
        'y_std': Y_std.tolist(),
    },
    'weights': w.tolist(),
    'bias': float(bias),
    'metrics': {
        'train_rmse': float(rmse),
        'train_mae': float(mae),
        'train_max_err': float(max_err),
        'within_1_cell_pct': float(within_1),
        'within_2_cells_pct': float(within_2),
        'cv_rmse_mean': float(cv_mean),
        'cv_rmse_std': float(cv_std),
        'effective_rank': effective_rank,
    },
}

model_path = OUT_DIR / f'pong_model_{TIMESTAMP}.json'
with open(model_path, 'w') as f:
    json.dump(model, f, indent=2)
print(f"  Model: {model_path}")

# Save raw data
data_path = OUT_DIR / f'pong_training_data_{TIMESTAMP}.npz'
np.savez(data_path,
         Y=Y, Y_norm=Y_norm, targets=targets, targets_norm=targets_norm,
         predictions=predictions_court, state_freqs=state_freqs,
         mode_freqs=mode_freqs, w=w, bias=np.array([bias]),
         Y_mean=Y_mean, Y_std=Y_std)
print(f"  Data: {data_path}")

print(f"\n  Next: python3 tools/pong_live.py --model {model_path}")
print(f"{'='*70}")
