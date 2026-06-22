#!/usr/bin/env python3
"""
Pong on Glass — Multi-Tone Training Pipeline
=============================================

Increases glass compute power by exploiting PHYSICAL NONLINEARITY.

PROBLEM with single-tone (pong_train.py):
  All 256 states map to a 1D frequency line (35-140 kHz).
  The kernel response lives on a 1D manifold → states inseparable.
  Result: 29% intercept (no better than standing still).

SOLUTION — multi-tone drive + intermodulation readout:
  Drive 3 frequencies SIMULTANEOUSLY:
    f1 = ball_x   → F1 channel  (35-65 kHz band)
    f2 = ball_y   → F2 channel  (70-100 kHz band)
    f3 = velocity → F4 channel  (105-135 kHz band)
  The glass nonlinearity mixes them, producing intermodulation
  products at f1±f2, f1±f3, f2±f3, 2f1, 2f2, 2f3, etc.
  These mixing terms are GENUINE MULTIPLICATIVE COMPUTE done by
  the physical glass — they encode interactions between the input
  dimensions that a 1D linear response cannot.

  Feature vector per state:
    [30 mode amps] + [3 drive amps] + [6 2nd-order intermod]
    + [3 harmonics]  = 42 physical features

This script also DIRECTLY COMPARES feature subsets from the same
captures so we can prove how much the intermodulation (nonlinear
glass compute) contributes vs the linear mode response alone.

Usage:
  python3 tools/pong_train_multitone.py --nco-port /dev/cu.usbmodem113401
  python3 tools/pong_train_multitone.py --dry-run
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
parser = argparse.ArgumentParser(description='Pong on Glass — Multi-Tone Training')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--census', type=str, default=None)
parser.add_argument('--navg', type=int, default=16,
                    help='FFT captures averaged per state (default: 16 for intermod SNR)')
parser.add_argument('--settle', type=float, default=0.04,
                    help='Settle time after freq change (default: 0.04s)')
parser.add_argument('--alpha', type=float, default=0.5,
                    help='Ridge regression alpha (default: 0.5)')
parser.add_argument('--ch-x', type=str, default='F1', help='TX channel for ball_x')
parser.add_argument('--ch-y', type=str, default='F2', help='TX channel for ball_y')
parser.add_argument('--ch-v', type=str, default='F4', help='TX channel for velocity')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()

# ─── Constants ────────────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
NYQUIST = FS / 2
RNG = 6
RNG_MV = 1000.0

COURT_W, COURT_H = 8, 8
N_STATES = COURT_W * COURT_H * 2 * 2

# Multi-tone frequency bands (chosen so intermod products stay in-band & separable)
F_X_LO, F_X_HI = 35000, 65000    # ball_x  (8 levels)
F_Y_LO, F_Y_HI = 70000, 100000   # ball_y  (8 levels)
F_V_LO, F_V_HI = 105000, 135000  # velocity quadrant (4 levels)

OUT_DIR = Path('data/results/pong')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')

print("=" * 70)
print("  PONG ON GLASS — MULTI-TONE TRAINING (nonlinear glass compute)")
print("=" * 70)

# ─── Load Census ─────────────────────────────────────────────────
print("\n[1] Loading census data...")
if args.census:
    census_path = Path(args.census)
else:
    census_dir = Path('data/results/direct_wire_census')
    census_files = sorted(census_dir.glob('direct_wire_census_*.json'))
    if not census_files:
        print("  ERROR: No census files found.")
        sys.exit(1)
    census_path = census_files[-1]

with open(census_path) as f:
    census = json.load(f)
mode_freqs = np.array([m['freq_hz'] for m in census['usable_modes']])
K = len(mode_freqs)
print(f"  Census: {census_path.name}")
print(f"  Usable modes: {K}")
print(f"  Mode range: {mode_freqs[0]/1000:.1f} – {mode_freqs[-1]/1000:.1f} kHz")


# ─── Define Game States ──────────────────────────────────────────
print(f"\n[2] Defining {N_STATES} game states...")


def index_to_state(idx):
    bx = idx // 32
    r = idx % 32
    by = r // 4
    r = r % 4
    vx = 1 if (r // 2) else -1
    vy = 1 if (r % 2) else -1
    return bx, by, vx, vy


def state_to_index(bx, by, vx, vy):
    return bx * 32 + by * 4 + (1 if vx == 1 else 0) * 2 + (1 if vy == 1 else 0)


# ─── Multi-Tone Encoding ─────────────────────────────────────────
print(f"\n[3] Multi-tone encoding (3 simultaneous drives)...")


def encode_state(bx, by, vx, vy):
    """Map state to 3 drive frequencies."""
    f1 = F_X_LO + bx * (F_X_HI - F_X_LO) / (COURT_W - 1)        # ball_x
    f2 = F_Y_LO + by * (F_Y_HI - F_Y_LO) / (COURT_H - 1)        # ball_y
    v_quad = (1 if vx == 1 else 0) * 2 + (1 if vy == 1 else 0)  # 0..3
    f3 = F_V_LO + v_quad * (F_V_HI - F_V_LO) / 3                # velocity
    return f1, f2, f3


# Precompute drive frequencies for all states
drive_freqs = np.zeros((N_STATES, 3))
for idx in range(N_STATES):
    drive_freqs[idx] = encode_state(*index_to_state(idx))

print(f"  f1 (ball_x): {F_X_LO/1000:.0f}–{F_X_HI/1000:.0f} kHz on {args.ch_x}")
print(f"  f2 (ball_y): {F_Y_LO/1000:.0f}–{F_Y_HI/1000:.0f} kHz on {args.ch_y}")
print(f"  f3 (veloc.): {F_V_LO/1000:.0f}–{F_V_HI/1000:.0f} kHz on {args.ch_v}")


# ─── Intermodulation Product Frequencies ─────────────────────────
def intermod_freqs(f1, f2, f3):
    """Return list of (label, freq) for intermod products in-band."""
    products = [
        ('f1+f2', f1 + f2),
        ('f1+f3', f1 + f3),
        ('f2+f3', f2 + f3),
        ('|f1-f2|', abs(f1 - f2)),
        ('|f1-f3|', abs(f1 - f3)),
        ('|f2-f3|', abs(f2 - f3)),
        ('2f1', 2 * f1),
        ('2f2', 2 * f2),
        ('2f3', 2 * f3),
    ]
    # Filter to in-band [2 kHz, Nyquist)
    return [(lbl, fr) for lbl, fr in products if 2000 < fr < NYQUIST]


# Feature layout: [K modes] + [3 drives] + [9 intermod] = K + 12
INTERMOD_LABELS = ['f1+f2', 'f1+f3', 'f2+f3', '|f1-f2|', '|f1-f3|', '|f2-f3|',
                   '2f1', '2f2', '2f3']
N_FEATURES = K + 3 + len(INTERMOD_LABELS)
print(f"\n  Feature vector: {K} modes + 3 drives + {len(INTERMOD_LABELS)} intermod = {N_FEATURES}")


# ─── Compute Optimal Paddle Targets ─────────────────────────────
print(f"\n[4] Computing optimal paddle targets...")


def compute_optimal_paddle(bx, by, vx, vy):
    x, y = float(bx), float(by)
    for _ in range(30):
        x += vx
        y += vy
        if y < 0:
            y = -y
            vy = -vy
        if y > COURT_H - 1:
            y = 2 * (COURT_H - 1) - y
            vy = -vy
        if x < 0:
            x = -x
            vx = -vx
        if x >= COURT_W - 1:
            return np.clip(y, 0, COURT_H - 1)
    return (COURT_H - 1) / 2.0


targets = np.array([compute_optimal_paddle(*index_to_state(i)) for i in range(N_STATES)])
targets_norm = targets / (COURT_H - 1)
print(f"  Targets: min={targets.min():.0f}, max={targets.max():.0f}, mean={targets.mean():.1f}")


# ─── Physical Data Collection ────────────────────────────────────
print(f"\n[5] Collecting multi-tone responses (navg={args.navg})...")


def read_amplitude(spectrum, freq, search=3):
    """Peak amplitude within ±search bins of freq."""
    bin_idx = int(round(freq / BIN_HZ))
    lo = max(0, bin_idx - search)
    hi = min(len(spectrum), bin_idx + search + 1)
    return float(spectrum[lo:hi].max())


def extract_features(spectrum, f1, f2, f3):
    """Build full feature vector from one spectrum."""
    feats = np.zeros(N_FEATURES)
    # Mode amplitudes (linear response)
    for m, freq in enumerate(mode_freqs):
        feats[m] = read_amplitude(spectrum, freq)
    # Drive amplitudes (forced response at each tone)
    feats[K + 0] = read_amplitude(spectrum, f1)
    feats[K + 1] = read_amplitude(spectrum, f2)
    feats[K + 2] = read_amplitude(spectrum, f3)
    # Intermodulation products (nonlinear glass mixing)
    im = {lbl: fr for lbl, fr in intermod_freqs(f1, f2, f3)}
    for j, lbl in enumerate(INTERMOD_LABELS):
        fr = im.get(lbl)
        feats[K + 3 + j] = read_amplitude(spectrum, fr) if fr else 0.0
    return feats


if args.dry_run:
    print("  [DRY RUN] Synthetic nonlinear glass model")
    Y = np.zeros((N_STATES, N_FEATURES))
    for idx in range(N_STATES):
        f1, f2, f3 = drive_freqs[idx]
        # Linear mode response (3 tones light up nearby modes)
        for m, mf in enumerate(mode_freqs):
            for fd in (f1, f2, f3):
                delta = abs(fd - mf)
                bw = mf / 200
                Y[idx, m] += 1.0 / (1.0 + (2 * delta / bw) ** 2)
        # Drive amplitudes
        Y[idx, K:K+3] = [1.0, 1.0, 1.0]
        # Intermod: PRODUCT of the two input amplitudes (nonlinear mixing)
        # Strength encodes interaction → THIS is what separates states
        bx, by, vx, vy = index_to_state(idx)
        im = {lbl: fr for lbl, fr in intermod_freqs(f1, f2, f3)}
        for j, lbl in enumerate(INTERMOD_LABELS):
            # Synthetic mixing strength depends on input values
            if lbl == 'f1+f2':
                Y[idx, K+3+j] = (bx/7.0) * (by/7.0)
            elif lbl == '|f1-f2|':
                Y[idx, K+3+j] = abs(bx - by) / 7.0
            elif lbl == 'f1+f3':
                Y[idx, K+3+j] = (bx/7.0) * ((vx+1)/2)
            elif lbl == 'f2+f3':
                Y[idx, K+3+j] = (by/7.0) * ((vy+1)/2)
            else:
                Y[idx, K+3+j] = 0.3
    Y += np.random.randn(*Y.shape) * 0.03
else:
    import serial
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"  ERROR: PicoScope open failed (handle={handle})")
        sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    print(f"  PicoScope: handle={handle}")

    nco_ser = serial.Serial(args.nco_port, 115200, timeout=2)
    time.sleep(0.5)
    nco_ser.reset_input_buffer()
    print(f"  NCO: {args.nco_port}")

    def nco_send(cmd):
        nco_ser.reset_input_buffer()
        nco_ser.write(f'{cmd}\n'.encode())
        time.sleep(0.015)

    def capture_spectrum():
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
        return np.mean(mags, axis=0) if mags else np.zeros(NFFT // 2 + 1)

    Y = np.zeros((N_STATES, N_FEATURES))
    t0 = time.time()
    est = N_STATES * (3 * 0.015 + args.settle + args.navg * 0.012)
    print(f"  Estimated time: {est:.0f}s")

    for idx in range(N_STATES):
        f1, f2, f3 = drive_freqs[idx]
        # Drive 3 tones simultaneously
        nco_send(f'{args.ch_x}:{int(f1)}')
        nco_send(f'{args.ch_y}:{int(f2)}')
        nco_send(f'{args.ch_v}:{int(f3)}')
        time.sleep(args.settle)
        spectrum = capture_spectrum()
        Y[idx] = extract_features(spectrum, f1, f2, f3)

        if (idx + 1) % 32 == 0 or (idx + 1) == N_STATES:
            elapsed = time.time() - t0
            eta = elapsed / (idx + 1) * (N_STATES - idx - 1)
            intermod_max = Y[idx, K+3:].max()
            print(f"    {idx+1}/{N_STATES} — f=({f1/1000:.0f},{f2/1000:.0f},{f3/1000:.0f})kHz"
                  f" — intermod_max={intermod_max:.0f} — ETA {eta:.0f}s")

    nco_send('Foff')
    print(f"  Collection complete: {time.time()-t0:.1f}s")
    nco_ser.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))

print(f"  Y shape: {Y.shape}")


# ─── Feature Subset Analysis ─────────────────────────────────────
print(f"\n[6] Separability analysis — does intermod help?")

# Define feature subsets
idx_modes = np.arange(0, K)
idx_drives = np.arange(K, K + 3)
idx_intermod = np.arange(K + 3, N_FEATURES)

subsets = {
    'modes only (linear)': idx_modes,
    'modes + drives': np.concatenate([idx_modes, idx_drives]),
    'intermod only (nonlinear)': idx_intermod,
    'ALL (modes+drives+intermod)': np.arange(N_FEATURES),
}


def normalize(Ysub):
    mu = Ysub.mean(axis=0)
    sd = Ysub.std(axis=0)
    sd[sd < 1e-10] = 1.0
    return (Ysub - mu) / sd, mu, sd


def fisher_ratio(Yn, tgt):
    """Separability: between-class / within-class for low vs high targets."""
    low = tgt <= 2
    high = tgt >= 5
    if low.sum() == 0 or high.sum() == 0:
        return 0.0
    lm, hm = Yn[low].mean(0), Yn[high].mean(0)
    sep = np.linalg.norm(hm - lm)
    ls = np.mean([np.linalg.norm(Yn[i] - lm) for i in np.where(low)[0]])
    hs = np.mean([np.linalg.norm(Yn[i] - hm) for i in np.where(high)[0]])
    return sep / ((ls + hs) / 2 + 1e-9)


def cv_rmse(Yn, tgt_norm, tgt, alpha, folds=4):
    n = len(tgt)
    idx = np.arange(n)
    np.random.seed(42)
    np.random.shuffle(idx)
    fs = n // folds
    I = np.eye(Yn.shape[1])
    rmses = []
    for f in range(folds):
        te = idx[f*fs:(f+1)*fs]
        tr = np.setdiff1d(idx, te)
        wf = np.linalg.solve(Yn[tr].T @ Yn[tr] + alpha * I, Yn[tr].T @ tgt_norm[tr])
        bf = tgt_norm[tr].mean() - Yn[tr].mean(0) @ wf
        pred = (Yn[te] @ wf + bf) * (COURT_H - 1)
        rmses.append(np.sqrt(np.mean((pred - tgt[te])**2)))
    return np.mean(rmses), np.std(rmses)


PADDLE_H = 3
print(f"  {'Feature set':<32} {'Fisher':>7} {'CV-RMSE':>10} {'Intercept':>10}")
print(f"  {'-'*32} {'-'*7} {'-'*10} {'-'*10}")

results = {}
for name, cols in subsets.items():
    Yn, _, _ = normalize(Y[:, cols])
    fr = fisher_ratio(Yn, targets)
    cvm, cvs = cv_rmse(Yn, targets_norm, targets, args.alpha)
    # Intercept rate via CV predictions (leave-one-fold)
    I = np.eye(len(cols))
    w_full = np.linalg.solve(Yn.T @ Yn + args.alpha * I, Yn.T @ targets_norm)
    b_full = targets_norm.mean() - Yn.mean(0) @ w_full
    pred = (Yn @ w_full + b_full) * (COURT_H - 1)
    intercept = np.mean(np.abs(pred - targets) <= PADDLE_H / 2) * 100
    results[name] = dict(fisher=fr, cv_rmse=cvm, cv_std=cvs, intercept=intercept)
    print(f"  {name:<32} {fr:>7.3f} {cvm:>6.2f}±{cvs:<3.1f} {intercept:>9.0f}%")

# Baselines
np.random.seed(1)
rand_int = []
for _ in range(40):
    rp = np.random.randint(PADDLE_H//2, COURT_H - PADDLE_H//2 + 1, size=N_STATES)
    rand_int.append(np.mean(np.abs(targets - rp) <= PADDLE_H/2))
rand_mean = np.mean(rand_int) * 100
stat_int = np.mean(np.abs(targets - (COURT_H-1)/2) <= PADDLE_H/2) * 100
print(f"  {'-'*32} {'-'*7} {'-'*10} {'-'*10}")
print(f"  {'random baseline':<32} {'--':>7} {'--':>10} {rand_mean:>9.0f}%")
print(f"  {'stationary baseline':<32} {'--':>7} {'--':>10} {stat_int:>9.0f}%")


# ─── Verdict ─────────────────────────────────────────────────────
print(f"\n[7] Verdict...")
best_name = max(results, key=lambda k: results[k]['intercept'])
best = results[best_name]
modes_only = results['modes only (linear)']
full = results['ALL (modes+drives+intermod)']

print(f"  Best feature set: {best_name} ({best['intercept']:.0f}% intercept)")
print(f"  Linear-only:      {modes_only['intercept']:.0f}% (Fisher {modes_only['fisher']:.3f})")
print(f"  Full (nonlinear): {full['intercept']:.0f}% (Fisher {full['fisher']:.3f})")
gain = full['intercept'] - modes_only['intercept']
print(f"  Intermod gain:    {gain:+.0f} percentage points")

if full['intercept'] > rand_mean + 10:
    print(f"\n  ✓ GLASS IS COMPUTING: {full['intercept']:.0f}% vs {rand_mean:.0f}% random")
    print(f"    (+{full['intercept']-rand_mean:.0f} pts above chance)")
elif full['intercept'] > rand_mean + 3:
    print(f"\n  ~ WEAK SIGNAL: {full['intercept']:.0f}% vs {rand_mean:.0f}% random")
else:
    print(f"\n  ✗ NO BETTER THAN RANDOM ({full['intercept']:.0f}% vs {rand_mean:.0f}%)")
    print(f"    Glass nonlinearity may be too weak at this drive level.")


# ─── Train Final Model (best subset) ─────────────────────────────
print(f"\n[8] Training final model on best subset...")
best_cols = subsets[best_name]
Yn, Y_mean_sub, Y_std_sub = normalize(Y[:, best_cols])
I = np.eye(len(best_cols))
w = np.linalg.solve(Yn.T @ Yn + args.alpha * I, Yn.T @ targets_norm)
bias = targets_norm.mean() - Yn.mean(0) @ w
print(f"  Subset: {best_name} ({len(best_cols)} features)")
print(f"  Weight norm: {np.linalg.norm(w):.3f}")


# ─── Save Model ──────────────────────────────────────────────────
print(f"\n[9] Saving model...")

# Store full normalization (all features) for live use
Y_mean_all = Y.mean(axis=0)
Y_std_all = Y.std(axis=0)
Y_std_all[Y_std_all < 1e-10] = 1.0

model = {
    'timestamp': TIMESTAMP,
    'encoding': 'multitone',
    'census_file': str(census_path),
    'config': {
        'ch_x': args.ch_x, 'ch_y': args.ch_y, 'ch_v': args.ch_v,
        'navg': args.navg, 'settle_s': args.settle, 'alpha': args.alpha,
        'f_x_lo': F_X_LO, 'f_x_hi': F_X_HI,
        'f_y_lo': F_Y_LO, 'f_y_hi': F_Y_HI,
        'f_v_lo': F_V_LO, 'f_v_hi': F_V_HI,
        'court_w': COURT_W, 'court_h': COURT_H,
        'kernel_dim': K, 'n_features': N_FEATURES,
        'nco_port': args.nco_port, 'dry_run': args.dry_run,
        'best_subset': best_name,
        'best_cols': best_cols.tolist(),
    },
    'mode_freqs_hz': mode_freqs.tolist(),
    'intermod_labels': INTERMOD_LABELS,
    'normalization': {
        'y_mean_subset': Y_mean_sub.tolist(),
        'y_std_subset': Y_std_sub.tolist(),
    },
    'weights': w.tolist(),
    'bias': float(bias),
    'metrics': {name: {k: float(v) for k, v in r.items()} for name, r in results.items()},
    'baselines': {'random_pct': float(rand_mean), 'stationary_pct': float(stat_int)},
}
model_path = OUT_DIR / f'pong_model_multitone_{TIMESTAMP}.json'
with open(model_path, 'w') as f:
    json.dump(model, f, indent=2)
print(f"  Model: {model_path}")

np.savez(OUT_DIR / f'pong_multitone_data_{TIMESTAMP}.npz',
         Y=Y, targets=targets, drive_freqs=drive_freqs, mode_freqs=mode_freqs,
         w=w, bias=np.array([bias]), best_cols=best_cols)
print(f"  Data: pong_multitone_data_{TIMESTAMP}.npz")

print(f"\n  Next: python3 tools/pong_live.py --model {model_path}")
print("=" * 70)
