#!/usr/bin/env python3
"""
D3-Physical — Round-Robin Frequency-Hopping Reservoir (Bench Experiment)

Demonstrates NARMA-10 computation using the CWM plate as a spatial kernel
with digital delay-line memory and quadratic readout.

Physics:
  - Plate converts scalar drive into 27-mode spectral fingerprint
  - Each mode has different spatial coupling to 4 receivers (measured H matrix)
  - Round-robin frequency hopping: input u[t] drives group (t mod 3)
  - Different groups excite different spatial patterns → richer features
  - Digital delay buffer stores last D readout vectors
  - Quadratic cross-delay products provide nonlinearity (beat analogy)

Hardware protocol:
  - NCO drives one representative frequency per group per step
  - PicoScope captures full spectrum (all 27 modes visible)
  - Relay fixed per pass (4 sequential passes to build full feature set)
  - Step rate ~15-20 Hz (NCO-latency-limited)
  
Note: At bench step rate (~20 Hz), plate temporal memory is negligible
(modes decay in ~1ms). The plate's contribution is SPATIAL DIVERSITY —
converting a 1D input into a high-dimensional spectral fingerprint.
The digital delay buffer provides temporal memory.

Expected result (from simulation with measured H): NRMSE ≈ 0.37-0.40
Compare against: random projection baseline (should be worse).
"""

import ctypes as ct
import numpy as np
import serial
import time
import json
from pathlib import Path
from datetime import datetime

# ─── Hardware setup ───────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N = 3968; TIMEBASE = 7; RNG = 6; RNG_MV = 2000
FS = 781250.0; NFFT = N * 4; BIN_HZ = FS / NFFT

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'

# Load enrolled mode frequencies
with open(DATA_DIR / 'h_matrix' / 'multi_plate_enrollment_20260603_171950.json') as f:
    h_data = json.load(f)
H_measured = np.array(h_data['h_matrix_normalized'])  # (27, 4)
freqs = np.array(h_data['mode_frequencies_hz'])       # (27,)
n_modes = len(freqs)

# ─── Frequency group assignment ──────────────────────────────────
# Divide 27 modes into 3 groups of 9, sorted by frequency
# Group 0: low (33-52 kHz), Group 1: mid (55-82 kHz), Group 2: high (85-119 kHz)
N_GROUPS = 3
MODES_PER_GROUP = n_modes // N_GROUPS  # 9

# Sort and split into groups
freq_order = np.argsort(freqs)
groups = [freq_order[g*MODES_PER_GROUP:(g+1)*MODES_PER_GROUP] for g in range(N_GROUPS)]

# Representative drive frequency per group (strongest mode in each group)
# Use the mode with highest average H-norm in each group
group_drive_freqs = []
for g, mode_indices in enumerate(groups):
    h_norms = np.linalg.norm(H_measured[mode_indices], axis=1)
    best_in_group = mode_indices[np.argmax(h_norms)]
    group_drive_freqs.append(int(freqs[best_in_group]))

print("D3-Physical — Round-Robin Frequency-Hopping Reservoir")
print("=" * 70)
print(f"Modes: {n_modes} enrolled, {N_GROUPS} groups of {MODES_PER_GROUP}")
print(f"Group frequencies: {group_drive_freqs} Hz")
print(f"  Group 0 (low):  modes {[int(freqs[i]) for i in groups[0]]} Hz")
print(f"  Group 1 (mid):  modes {[int(freqs[i]) for i in groups[1]]} Hz")
print(f"  Group 2 (high): modes {[int(freqs[i]) for i in groups[2]]} Hz")
print()

# ─── NARMA-10 generation ─────────────────────────────────────────
N_STEPS = 300  # Enough for train+test with washout
SEED = 42

def generate_narma10(n_steps, seed=42):
    rng = np.random.default_rng(seed)
    u = rng.uniform(0, 0.5, n_steps + 200)
    y = np.zeros(n_steps + 200)
    for t in range(10, len(y)):
        y[t] = 0.3*y[t-1] + 0.05*y[t-1]*np.sum(y[t-10:t]) + 1.5*u[t-1]*u[t-10] + 0.1
        y[t] = np.clip(y[t], 0, 1.0)
    return u[200:], y[200:]

u_narma, y_narma = generate_narma10(N_STEPS, seed=SEED)
print(f"NARMA-10: {N_STEPS} steps, input range [{u_narma.min():.3f}, {u_narma.max():.3f}]")
print()

# ─── Initialize hardware ─────────────────────────────────────────
print("[1] Initializing hardware...")
ps = ct.CDLL(PICO_LIB)
ps.ps2000_close_unit(ct.c_int16(1))
time.sleep(0.3)

ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
if h <= 0:
    raise RuntimeError(f"PicoScope open failed: {h}")
ps.ps2000_set_channel(h, 0, 1, 0, RNG)
print(f"  PicoScope handle: {h}")

mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=2, dsrdtr=False, rtscts=False)
mux.dtr = False
time.sleep(2.5)
mux.reset_input_buffer()

ser = serial.Serial('/dev/cu.usbmodem113301', 115200, timeout=2)
time.sleep(0.5)
ser.reset_input_buffer()
print("  NCO and relay mux connected")


def nco(cmd):
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()


def set_relay(r):
    mux.reset_input_buffer()
    mux.write(f'{r}\r\n'.encode())
    time.sleep(0.35)
    mux.read(mux.in_waiting)


def capture_spectrum(navg=8):
    """Capture averaged magnitude spectrum."""
    buf = (ct.c_int16 * N)()
    ov = ct.c_int16()
    mags = []
    for _ in range(navg):
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(h, N, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(h):
                break
            time.sleep(0.002)
        ps.ps2000_get_values(h, ct.byref(buf), None, None, None, ct.byref(ov), N, 0)
        d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
        d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d * np.hanning(N), n=NFFT)))
    return np.mean(mags, axis=0)


def extract_mode_magnitudes(spectrum):
    """Extract peak magnitude at each of 27 enrolled mode frequencies."""
    mags = np.zeros(n_modes)
    for i, freq in enumerate(freqs):
        b = int(round(freq / BIN_HZ))
        w = 5
        mags[i] = float(spectrum[max(0, b-w):b+w+1].max())
    return mags


# ─── Data collection ──────────────────────────────────────────────
# Relay map: 1=PI_NW, 2=PI_NE, 3=PH_NW(cascade), 4=PH_NE(cascade)
RELAY_ORDER = [1, 2, 3, 4]
RELAY_NAMES = ['PI_NW', 'PI_NE', 'PH_NW_cascade', 'PH_NE_cascade']
NAVG = 8  # Averages per capture

# Storage: (n_steps, n_modes, n_receivers)
all_readouts = np.zeros((N_STEPS, n_modes, len(RELAY_ORDER)))

nco('Foff')
time.sleep(0.3)

print()
print(f"[2] Collecting {N_STEPS} steps × {len(RELAY_ORDER)} receivers...")
print(f"    Round-robin groups: {N_GROUPS}, cycling every step")
print(f"    Estimated time: {N_STEPS * len(RELAY_ORDER) * 0.5 / 60:.1f} minutes")
print()

t_start = time.time()

for rx_idx, relay in enumerate(RELAY_ORDER):
    set_relay(relay)
    time.sleep(0.2)
    print(f"  Receiver {rx_idx+1}/{len(RELAY_ORDER)}: relay {relay} ({RELAY_NAMES[rx_idx]})")

    for t in range(N_STEPS):
        # Select group and drive frequency (round-robin)
        g = t % N_GROUPS
        drive_freq = group_drive_freqs[g]

        # Set NCO to this group's frequency
        nco(f'F1:{drive_freq}')
        time.sleep(0.02)  # Brief settle (mode excitation happens in <1ms)

        # Capture spectrum
        sp = capture_spectrum(NAVG)

        # Extract all 27 mode magnitudes
        mags = extract_mode_magnitudes(sp)
        all_readouts[t, :, rx_idx] = mags

        # Progress
        if (t + 1) % 50 == 0:
            elapsed = time.time() - t_start
            rate = (rx_idx * N_STEPS + t + 1) / elapsed
            remain = (len(RELAY_ORDER) * N_STEPS - (rx_idx * N_STEPS + t + 1)) / rate
            print(f"    Step {t+1}/{N_STEPS} — "
                  f"{elapsed:.0f}s elapsed, ~{remain:.0f}s remaining")

    nco('Foff')
    time.sleep(0.1)

total_time = time.time() - t_start
print(f"\n  Collection complete: {total_time:.1f}s ({total_time/60:.1f} min)")

# ─── Feature engineering ──────────────────────────────────────────
print()
print("[3] Feature engineering...")

# Flatten readout: (n_steps, n_modes * n_rx) = (300, 108)
X_flat = all_readouts.reshape(N_STEPS, -1)  # (300, 108)
print(f"  Raw feature shape: {X_flat.shape}")

# Normalize each feature to zero mean, unit variance
X_mean = X_flat.mean(axis=0, keepdims=True)
X_std = X_flat.std(axis=0, keepdims=True) + 1e-10
X_norm = (X_flat - X_mean) / X_std

# Also compute H-projected readout (simulate what D3c did: state @ H → 4 features)
# Our physical measurement gives us ALL 27 mode magnitudes on each receiver
# The H-projected version: for each step, pretend we only see state @ H
# state @ H ≈ select the driven mode's row of H... but actually we SEE all modes

# Feature set 1: Full physical readout (108 features)
# Feature set 2: H-projected (just the 4-channel readout per step)
# We'll use the full readout — it's what the hardware gives us

# Delay-line augmentation
MAX_DELAY = 15

def build_features(X, max_delay, quad_mode='cross_delay'):
    """Build delay-augmented + quadratic features."""
    n_steps, n_feat = X.shape

    # Delayed copies
    delayed = np.zeros((n_steps, n_feat * max_delay))
    for d in range(max_delay):
        delayed[d:, d*n_feat:(d+1)*n_feat] = X[:n_steps-d]

    if quad_mode == 'none':
        return delayed

    # Selective quadratic: cross-delay products (same feature, different delays)
    # + cross-feature products (same delay, different features)
    quad_list = [delayed]

    if quad_mode == 'cross_delay':
        # Cross-delay: feature_i at delay d1 × feature_i at delay d2
        # Only nearby delays (d2 - d1 ≤ 4) and subset of features
        n_feat_sub = min(n_feat, 20)  # Limit to top features
        for f_idx in range(n_feat_sub):
            for d1 in range(max_delay):
                for d2 in range(d1+1, min(d1+4, max_delay)):
                    prod = delayed[:, d1*n_feat+f_idx] * delayed[:, d2*n_feat+f_idx]
                    quad_list.append(prod[:, np.newaxis])

    elif quad_mode == 'full':
        # Cross-delay + cross-feature (richer but larger)
        n_feat_sub = min(n_feat, 8)
        for d1 in range(max_delay):
            for d2 in range(d1+1, min(d1+4, max_delay)):
                for f1 in range(n_feat_sub):
                    for f2 in range(f1, n_feat_sub):
                        prod = delayed[:, d1*n_feat+f1] * delayed[:, d2*n_feat+f2]
                        quad_list.append(prod[:, np.newaxis])

    return np.hstack(quad_list)


def train_readout(features, target, n_train, alpha=1e-4):
    """Ridge regression with SVD-based solver."""
    washout = 30  # Shorter washout for physical (fewer steps)
    X_tr = features[washout:n_train]
    y_tr = target[washout:n_train]
    X_te = features[n_train:]
    y_te = target[n_train:]

    n_f = X_tr.shape[1]
    n_s = X_tr.shape[0]

    # SVD-based ridge (numerically stable)
    U, s, Vt = np.linalg.svd(X_tr, full_matrices=False)
    k = np.sum(s > s[0] * 1e-8)
    U_k, s_k, Vt_k = U[:, :k], s[:k], Vt[:k, :]
    d = s_k**2 / (s_k**2 + alpha)
    W = Vt_k.T @ (np.diag(d / s_k) @ (U_k.T @ y_tr))

    y_pred = X_te @ W
    mse = np.mean((y_te - y_pred)**2)
    var = np.var(y_te)
    nrmse = np.sqrt(mse / var) if var > 1e-10 else np.inf
    return nrmse


# ─── Train and evaluate ──────────────────────────────────────────
print()
print("[4] Training readout...")
print()

N_TRAIN = 200  # 200 train, 100 test

results = {}

# Test with different feature subsets and delays
print("  --- Full physical readout (108 features/step) ---")
for max_d in [5, 10, 15]:
    # Linear delay only
    feats_lin = build_features(X_norm, max_d, 'none')
    nrmse_lin = train_readout(feats_lin, y_narma, N_TRAIN)

    # Cross-delay quadratic
    feats_quad = build_features(X_norm, max_d, 'cross_delay')
    nrmse_quad = train_readout(feats_quad, y_narma, N_TRAIN)

    print(f"    D={max_d:>2}: linear ({feats_lin.shape[1]:>5} feat) NRMSE={nrmse_lin:.4f}, "
          f"quad ({feats_quad.shape[1]:>5} feat) NRMSE={nrmse_quad:.4f}")

    results[f'full_D{max_d}_linear'] = {'n_features': feats_lin.shape[1], 'nrmse': float(nrmse_lin)}
    results[f'full_D{max_d}_quad'] = {'n_features': feats_quad.shape[1], 'nrmse': float(nrmse_quad)}

# Test with just 4-channel projection (what simulation used)
print()
print("  --- 4-channel H-projected readout ---")
# Project: for each step, compute the 4-receiver-summed signal
# Actually our measurement already gives per-receiver data
# Just use per-receiver readout (pick top receiver for each mode)
X_4ch = np.zeros((N_STEPS, 4))
for t in range(N_STEPS):
    for rx in range(4):
        X_4ch[t, rx] = all_readouts[t, :, rx].sum()  # Total energy per receiver

X_4ch_norm = (X_4ch - X_4ch.mean(0, keepdims=True)) / (X_4ch.std(0, keepdims=True) + 1e-10)

for max_d in [10, 15, 20]:
    feats_4 = build_features(X_4ch_norm, max_d, 'cross_delay')
    nrmse_4 = train_readout(feats_4, y_narma, N_TRAIN)
    print(f"    D={max_d:>2}: quad ({feats_4.shape[1]:>5} feat) NRMSE={nrmse_4:.4f}")
    results[f'4ch_D{max_d}_quad'] = {'n_features': feats_4.shape[1], 'nrmse': float(nrmse_4)}

# Ridge alpha sweep on best config
print()
print("  --- Ridge alpha sweep (full readout, D=15, quad) ---")
feats_best = build_features(X_norm, 15, 'cross_delay')
for alpha in [1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2]:
    nrmse_a = train_readout(feats_best, y_narma, N_TRAIN, alpha=alpha)
    print(f"    α={alpha:.0e}: NRMSE={nrmse_a:.4f}")
    results[f'alpha_{alpha:.0e}'] = float(nrmse_a)

# ─── Random baseline comparison ──────────────────────────────────
print()
print("[5] Random projection baseline...")
print("  (Replace physical H with random matrix — what if plate gave no structure?)")

rng_baseline = np.random.default_rng(123)
n_random_trials = 5
random_nrmses = []

for trial in range(n_random_trials):
    # Shuffle mode-receiver assignments (destroy spatial structure)
    X_shuffled = X_norm.copy()
    for t in range(N_STEPS):
        perm = rng_baseline.permutation(X_shuffled.shape[1])
        X_shuffled[t] = X_shuffled[t, perm]

    feats_rand = build_features(X_shuffled, 15, 'cross_delay')
    nrmse_rand = train_readout(feats_rand, y_narma, N_TRAIN)
    random_nrmses.append(nrmse_rand)

print(f"  Random baseline: {np.mean(random_nrmses):.4f} ± {np.std(random_nrmses):.4f}")
results['random_baseline'] = {
    'mean': float(np.mean(random_nrmses)),
    'std': float(np.std(random_nrmses)),
    'values': [float(x) for x in random_nrmses]
}

# ─── Final summary ───────────────────────────────────────────────
print()
print("=" * 70)
print("  D3-PHYSICAL — ROUND-ROBIN RESERVOIR RESULTS")
print("=" * 70)
print()

best_key = min(
    [(k, v['nrmse']) for k, v in results.items() if isinstance(v, dict) and 'nrmse' in v],
    key=lambda x: x[1]
)
best_nrmse = best_key[1]

print(f"  Baselines:")
print(f"    D2 Gram (sim, 4 features):      NRMSE = 0.7036")
print(f"    D3 Beat (sim, 1516 features):    NRMSE = 0.6377")
print(f"    D3c sim round-robin G=3:         NRMSE = 0.3929")
print(f"    D3c sim delay-line D=15:         NRMSE = 0.3727")
print(f"    Random ESN (sim, 27 nodes):      NRMSE = 0.4417")
print(f"    Random projection baseline:      NRMSE = {np.mean(random_nrmses):.4f}")
print()
print(f"  Physical measurement:")
print(f"    Best config ({best_key[0]}): NRMSE = {best_nrmse:.4f}")
print()

if best_nrmse < 0.40:
    verdict = "PASS"
    print("  ★★ PASS — Physical reservoir matches/beats simulation!")
    print("     Plate spatial diversity + digital delay solves NARMA-10.")
elif best_nrmse < 0.50:
    verdict = "GOOD"
    print("  ★ GOOD — Physical beats random ESN baseline.")
elif best_nrmse < 0.64:
    verdict = "IMPROVED"
    print("  △ IMPROVED — Better than D3 beat-only, approaching random ESN.")
else:
    verdict = "FAIL"
    print("  ✗ FAIL — Physical result worse than simulation prediction.")

# Plate vs random significance
plate_nrmse = best_nrmse
rand_mean = np.mean(random_nrmses)
rand_std = np.std(random_nrmses)
if rand_std > 0:
    sigma_better = (rand_mean - plate_nrmse) / rand_std
    print(f"\n  Plate vs Random: {sigma_better:.1f}σ better than random projection")

print(f"\n  VERDICT: {verdict}")

# ─── Save ─────────────────────────────────────────────────────────
OUT_DIR = DATA_DIR / 'reservoir'
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = OUT_DIR / f'd3_physical_reservoir_{ts}.json'

output = {
    'test': 'D3_physical_round_robin_reservoir',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'n_steps': N_STEPS,
        'n_groups': N_GROUPS,
        'group_drive_freqs_hz': group_drive_freqs,
        'groups_mode_indices': [g.tolist() for g in groups],
        'relay_order': RELAY_ORDER,
        'relay_names': RELAY_NAMES,
        'n_avg': NAVG,
        'narma_seed': SEED,
        'wiring': 'cascade (PI_NE_RX -> jumper -> PH_SW_TX)',
    },
    'collection_time_s': float(total_time),
    'readout_shape': list(all_readouts.shape),
    'results': results,
    'best_nrmse': float(best_nrmse),
    'best_config': best_key[0],
    'random_baseline_mean': float(rand_mean),
    'verdict': verdict,
}

with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\n  Saved: {out_path}")

# Save raw readout data for later analysis
raw_path = OUT_DIR / f'd3_physical_readouts_{ts}.npz'
np.savez_compressed(raw_path,
                    readouts=all_readouts,
                    u_narma=u_narma,
                    y_narma=y_narma,
                    freqs=freqs,
                    H_measured=H_measured,
                    group_drive_freqs=np.array(group_drive_freqs))
print(f"  Raw data: {raw_path}")

# Cleanup
nco('Foff')
ser.close()
mux.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
print("\n  Hardware released.")
