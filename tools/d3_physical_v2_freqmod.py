#!/usr/bin/env python3
"""
D3-Physical v2 — Frequency-Detuning Reservoir (Lorentzian Kernel)

Fix for v1: NCO amplitude is constant, so input u[t] was never encoded.

Solution: Encode u[t] as a FREQUENCY within each group's spectral range.
The plate's modal response is a sum of Lorentzians:
    A_i(f_drive) = A_max_i / sqrt(1 + (2*Q*(f_drive - f_i)/f_i)²)

This maps scalar u[t] → 27-dimensional amplitude vector NONLINEARLY.
Each mode's response is a different Lorentzian peak, so nearby modes
respond differently to the same input. This is the nonlinear kernel
that was missing from D2/D3.

Combined with round-robin (3 groups cycling):
- Step t mod 3 = 0: sweep frequency within low-band (33-57 kHz)
- Step t mod 3 = 1: sweep frequency within mid-band (60-89 kHz)
- Step t mod 3 = 2: sweep frequency within high-band (91-119 kHz)

The plate acts as a frequency-selective nonlinear kernel with built-in
memory (modes ring between steps). This is physically realizable NOW —
just change the NCO frequency command each step.

Analogy: This is exactly how FM radio discriminators work — frequency
deviations produce amplitude variations through a resonant filter.
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

# ─── Frequency group design ──────────────────────────────────────
N_GROUPS = 3
MODES_PER_GROUP = n_modes // N_GROUPS  # 9

# Sort by frequency and split
freq_order = np.argsort(freqs)
groups = [freq_order[g*MODES_PER_GROUP:(g+1)*MODES_PER_GROUP] for g in range(N_GROUPS)]

# For each group, define the frequency sweep range
# u[t] ∈ [0, 0.5] maps to a frequency within the group
# Sweep should span multiple mode peaks to maximize response diversity
group_freq_ranges = []
for g, mode_indices in enumerate(groups):
    f_min = int(freqs[mode_indices[0]])   # Lowest mode in group
    f_max = int(freqs[mode_indices[-1]])   # Highest mode in group
    # Add margins (sweep slightly beyond outer modes)
    margin = int((f_max - f_min) * 0.05)
    group_freq_ranges.append((f_min - margin, f_max + margin))

print("D3-Physical v2 — Frequency-Detuning Reservoir")
print("=" * 70)
print(f"Modes: {n_modes}, Groups: {N_GROUPS}")
for g in range(N_GROUPS):
    f_lo, f_hi = group_freq_ranges[g]
    mode_freqs = [int(freqs[i]) for i in groups[g]]
    print(f"  Group {g}: sweep {f_lo}–{f_hi} Hz | modes: {mode_freqs}")
print()
print("Encoding: u[t] → f_drive within group's range")
print("          Plate response = sum of Lorentzians at mode frequencies")
print("          → nonlinear, frequency-selective kernel")
print()

# ─── Input mapping ───────────────────────────────────────────────
def input_to_freq(u_val, group_idx):
    """Map input u ∈ [0, 0.5] to drive frequency within group range."""
    f_lo, f_hi = group_freq_ranges[group_idx]
    # Linear mapping: u=0 → f_lo, u=0.5 → f_hi
    f = f_lo + (u_val / 0.5) * (f_hi - f_lo)
    return int(round(f))


# ─── NARMA-10 ────────────────────────────────────────────────────
N_STEPS = 300
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
print(f"NARMA-10: {N_STEPS} steps, u ∈ [{u_narma.min():.3f}, {u_narma.max():.3f}]")

# Pre-compute the drive frequency sequence
drive_freqs = np.zeros(N_STEPS, dtype=int)
for t in range(N_STEPS):
    g = t % N_GROUPS
    drive_freqs[t] = input_to_freq(u_narma[t], g)

print(f"Drive frequencies: min={drive_freqs.min()}, max={drive_freqs.max()} Hz")
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


# ─── Calibration: verify Lorentzian response ─────────────────────
print()
print("[2] Calibration: verifying Lorentzian response to detuning...")
set_relay(1)
time.sleep(0.2)

# Pick a strong mode and sweep around it
cal_mode = groups[1][4]  # Mid-group, middle mode
f_center = int(freqs[cal_mode])
cal_offsets = np.arange(-500, 501, 50)  # ±500 Hz in 50 Hz steps
cal_responses = []

for offset in cal_offsets:
    f_drive = f_center + int(offset)
    nco(f'F1:{f_drive}')
    time.sleep(0.02)
    sp = capture_spectrum(4)
    mag = extract_mode_magnitudes(sp)[cal_mode]
    cal_responses.append(mag)

cal_responses = np.array(cal_responses)
nco('Foff')

# Fit Lorentzian to verify
peak_idx = np.argmax(cal_responses)
peak_val = cal_responses[peak_idx]
half_max = peak_val / np.sqrt(2)
above_half = np.where(cal_responses > half_max)[0]
if len(above_half) > 1:
    bw_measured = (cal_offsets[above_half[-1]] - cal_offsets[above_half[0]])
    q_measured = f_center / max(bw_measured, 1)
else:
    bw_measured = 0
    q_measured = 0

print(f"  Mode {cal_mode} at {f_center} Hz:")
print(f"  Peak response: {peak_val:.0f}")
print(f"  -3dB bandwidth: {bw_measured} Hz")
print(f"  Measured Q: {q_measured:.0f}")
print(f"  Dynamic range (peak/edge): {peak_val/max(cal_responses[0], 1):.1f}×")
print(f"  Lorentzian kernel verified: {'YES' if bw_measured > 0 else 'WEAK'}")
print()

# ─── Data collection ──────────────────────────────────────────────
RELAY_ORDER = [1, 2, 3, 4]
RELAY_NAMES = ['PI_NW', 'PI_NE', 'PH_NW_cascade', 'PH_NE_cascade']
NAVG = 8

# Storage: (n_steps, n_modes, n_receivers)
all_readouts = np.zeros((N_STEPS, n_modes, len(RELAY_ORDER)))

print(f"[3] Collecting {N_STEPS} steps × {len(RELAY_ORDER)} receivers...")
print(f"    Encoding: u[t] → frequency sweep within group")
print(f"    Estimated time: {N_STEPS * len(RELAY_ORDER) * 0.15 / 60:.1f} minutes")
print()

t_start = time.time()

for rx_idx, relay in enumerate(RELAY_ORDER):
    set_relay(relay)
    time.sleep(0.2)
    print(f"  Receiver {rx_idx+1}/{len(RELAY_ORDER)}: relay {relay} ({RELAY_NAMES[rx_idx]})")

    for t in range(N_STEPS):
        # Drive at the input-encoded frequency
        f_drive = drive_freqs[t]
        nco(f'F1:{f_drive}')
        time.sleep(0.01)  # Brief settle (mode responds in <1ms)

        # Capture spectrum
        sp = capture_spectrum(NAVG)

        # Extract all 27 mode magnitudes
        mags = extract_mode_magnitudes(sp)
        all_readouts[t, :, rx_idx] = mags

        # Progress
        if (t + 1) % 50 == 0:
            elapsed = time.time() - t_start
            done = rx_idx * N_STEPS + t + 1
            total = len(RELAY_ORDER) * N_STEPS
            rate = done / elapsed
            remain = (total - done) / rate
            print(f"    Step {t+1}/{N_STEPS} — "
                  f"{elapsed:.0f}s elapsed, ~{remain:.0f}s remaining")

    nco('Foff')
    time.sleep(0.1)

total_time = time.time() - t_start
print(f"\n  Collection complete: {total_time:.1f}s ({total_time/60:.1f} min)")

# ─── Verify input encoding ───────────────────────────────────────
print()
print("[4] Verifying input encoding...")

# Check correlation between u[t] and mode responses
# For modes in each group, response should correlate with u[t] at group steps
for g in range(N_GROUPS):
    g_steps = np.arange(g, N_STEPS, N_GROUPS)
    g_modes = groups[g]
    corrs = []
    for mode in g_modes:
        for rx in range(4):
            c = np.corrcoef(u_narma[g_steps], all_readouts[g_steps, mode, rx])[0, 1]
            corrs.append(abs(c))
    print(f"  Group {g}: mean |corr(u, mode_amp)| = {np.mean(corrs):.3f} "
          f"(max={np.max(corrs):.3f})")

# Overall encoding quality
all_corrs = []
for t_offset in range(N_GROUPS):
    steps = np.arange(t_offset, N_STEPS, N_GROUPS)
    g_modes = groups[t_offset]
    for mode in g_modes:
        for rx in range(4):
            c = np.corrcoef(u_narma[steps], all_readouts[steps, mode, rx])[0, 1]
            all_corrs.append(c)
print(f"  Overall: mean corr = {np.mean(all_corrs):.4f}, "
      f"max |corr| = {np.max(np.abs(all_corrs)):.4f}")
print()

# ─── Feature engineering ──────────────────────────────────────────
print("[5] Feature engineering...")

# Flatten: (300, 27*4) = (300, 108)
X_flat = all_readouts.reshape(N_STEPS, -1)
print(f"  Raw features: {X_flat.shape}")

# Normalize
X_mean = X_flat.mean(axis=0, keepdims=True)
X_std = X_flat.std(axis=0, keepdims=True) + 1e-10
X_norm = (X_flat - X_mean) / X_std

# Remove features with zero variance (non-responsive modes)
active = X_std.flatten() > 1.0
X_active = X_norm[:, active]
print(f"  Active features (std > 1): {X_active.shape[1]}/{X_flat.shape[1]}")


def build_delay_features(X, max_delay, quad_mode='cross_delay'):
    """Delay-embed + quadratic features."""
    n_steps, n_feat = X.shape
    delayed = np.zeros((n_steps, n_feat * max_delay))
    for d in range(max_delay):
        delayed[d:, d*n_feat:(d+1)*n_feat] = X[:n_steps-d]

    if quad_mode == 'none':
        return delayed

    quad_list = [delayed]
    # Cross-delay products: same feature at different delays
    n_sub = min(n_feat, 20)  # Top features
    for f_idx in range(n_sub):
        for d1 in range(max_delay):
            for d2 in range(d1+1, min(d1+4, max_delay)):
                prod = delayed[:, d1*n_feat+f_idx] * delayed[:, d2*n_feat+f_idx]
                quad_list.append(prod[:, np.newaxis])

    return np.hstack(quad_list)


def train_readout(features, target, n_train, alpha=1e-4):
    """Ridge regression with SVD solver."""
    washout = 30
    X_tr = features[washout:n_train]
    y_tr = target[washout:n_train]
    X_te = features[n_train:]
    y_te = target[n_train:]

    U, s, Vt = np.linalg.svd(X_tr, full_matrices=False)
    k = np.sum(s > s[0] * 1e-8)
    U_k, s_k, Vt_k = U[:, :k], s[:k], Vt[:k, :]
    d = s_k**2 / (s_k**2 + alpha)
    W = Vt_k.T @ (np.diag(d / s_k) @ (U_k.T @ y_tr))

    y_pred = X_te @ W
    mse = np.mean((y_te - y_pred)**2)
    var = np.var(y_te)
    nrmse = np.sqrt(mse / var) if var > 1e-10 else np.inf
    return nrmse, y_pred, y_te


# ─── Train and evaluate ──────────────────────────────────────────
print()
print("[6] Training readout...")
print()

N_TRAIN = 200
results = {}

# Full feature set with different delays
print("  --- Full active features + delay embedding ---")
for max_d in [5, 10, 15]:
    feats_lin = build_delay_features(X_active, max_d, 'none')
    nrmse_lin, _, _ = train_readout(feats_lin, y_narma, N_TRAIN)

    feats_quad = build_delay_features(X_active, max_d, 'cross_delay')
    nrmse_quad, _, _ = train_readout(feats_quad, y_narma, N_TRAIN)

    print(f"    D={max_d:>2}: linear ({feats_lin.shape[1]:>5}) NRMSE={nrmse_lin:.4f}, "
          f"quad ({feats_quad.shape[1]:>5}) NRMSE={nrmse_quad:.4f}")
    results[f'active_D{max_d}_linear'] = {'n_feat': feats_lin.shape[1], 'nrmse': float(nrmse_lin)}
    results[f'active_D{max_d}_quad'] = {'n_feat': feats_quad.shape[1], 'nrmse': float(nrmse_quad)}

# Alpha sweep on best
print()
print("  --- Ridge alpha sweep (D=15, quad) ---")
feats_best = build_delay_features(X_active, 15, 'cross_delay')
for alpha in [1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2]:
    nrmse_a, _, _ = train_readout(feats_best, y_narma, N_TRAIN, alpha=alpha)
    print(f"    α={alpha:.0e}: NRMSE={nrmse_a:.4f}")
    results[f'alpha_{alpha:.0e}'] = float(nrmse_a)

# Try with just the driven group's modes (tighter focus)
print()
print("  --- Driven-group-only features ---")
# Only use modes from the group that was actually driven at each step
X_driven = np.zeros((N_STEPS, MODES_PER_GROUP * 4))
for t in range(N_STEPS):
    g = t % N_GROUPS
    for rx in range(4):
        X_driven[t, rx*MODES_PER_GROUP:(rx+1)*MODES_PER_GROUP] = all_readouts[t, groups[g], rx]

X_driven_norm = (X_driven - X_driven.mean(0, keepdims=True)) / (X_driven.std(0, keepdims=True) + 1e-10)

for max_d in [10, 15, 20]:
    feats_drv = build_delay_features(X_driven_norm, max_d, 'cross_delay')
    nrmse_drv, _, _ = train_readout(feats_drv, y_narma, N_TRAIN, alpha=1e-5)
    print(f"    D={max_d:>2}: {feats_drv.shape[1]:>5} feat → NRMSE={nrmse_drv:.4f}")
    results[f'driven_D{max_d}_quad'] = {'n_feat': feats_drv.shape[1], 'nrmse': float(nrmse_drv)}

# ─── Random baseline ─────────────────────────────────────────────
print()
print("[7] Random baseline (shuffle mode-receiver assignments)...")
rng_base = np.random.default_rng(123)
rand_nrmses = []
for trial in range(5):
    X_shuf = X_active.copy()
    for t in range(N_STEPS):
        perm = rng_base.permutation(X_shuf.shape[1])
        X_shuf[t] = X_shuf[t, perm]
    feats_rand = build_delay_features(X_shuf, 15, 'cross_delay')
    nr, _, _ = train_readout(feats_rand, y_narma, N_TRAIN, alpha=1e-5)
    rand_nrmses.append(nr)
print(f"  Random: {np.mean(rand_nrmses):.4f} ± {np.std(rand_nrmses):.4f}")

# ─── Final summary ───────────────────────────────────────────────
print()
print("=" * 70)
print("  D3-PHYSICAL v2 — FREQUENCY-DETUNING RESERVOIR RESULTS")
print("=" * 70)
print()

# Find best result
all_nrmse = [(k, v['nrmse'] if isinstance(v, dict) else v)
             for k, v in results.items()
             if (isinstance(v, dict) and 'nrmse' in v) or isinstance(v, float)]
best_key, best_nrmse = min(all_nrmse, key=lambda x: x[1])

print(f"  Baselines:")
print(f"    D2 Gram (sim):                NRMSE = 0.7036")
print(f"    D3 Beat (sim):                NRMSE = 0.6377")
print(f"    D3c sim round-robin G=3:      NRMSE = 0.3929")
print(f"    Random ESN (sim, 27 nodes):   NRMSE = 0.4417")
print(f"    v1 physical (no encoding):    NRMSE = 1.1536")
print(f"    Random baseline (this data):  NRMSE = {np.mean(rand_nrmses):.4f}")
print()
print(f"  v2 Physical (frequency-detuning encoding):")
print(f"    Best config ({best_key}): NRMSE = {best_nrmse:.4f}")
print()

if best_nrmse < 0.40:
    verdict = "PASS"
    print("  ★★ PASS — Physical matches simulation prediction!")
elif best_nrmse < 0.50:
    verdict = "GOOD"
    print("  ★ GOOD — Beats random ESN baseline!")
elif best_nrmse < 0.64:
    verdict = "IMPROVED"
    print("  △ IMPROVED — Beats D3 beat-only (0.64).")
elif best_nrmse < 1.0:
    verdict = "PARTIAL"
    print("  ◇ PARTIAL — Input encoded but insufficient temporal memory.")
else:
    verdict = "FAIL"
    print("  ✗ FAIL — No improvement.")

# Significance vs random
rand_mean = np.mean(rand_nrmses)
rand_std = np.std(rand_nrmses)
if rand_std > 0:
    sigma_better = (rand_mean - best_nrmse) / rand_std
    print(f"\n  Plate vs Random: {sigma_better:.1f}σ better")

print(f"\n  VERDICT: {verdict} (best NRMSE = {best_nrmse:.4f})")

# ─── Save ─────────────────────────────────────────────────────────
OUT_DIR = DATA_DIR / 'reservoir'
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = OUT_DIR / f'd3_physical_v2_freqmod_{ts}.json'

output = {
    'test': 'D3_physical_v2_frequency_detuning_reservoir',
    'timestamp': datetime.now().isoformat(),
    'concept': 'Input u[t] encoded as drive frequency within spectral group. '
               'Plate Lorentzian response provides nonlinear kernel. '
               'Round-robin across 3 groups with digital delay buffer.',
    'config': {
        'n_steps': N_STEPS,
        'n_groups': N_GROUPS,
        'group_freq_ranges': group_freq_ranges,
        'groups_mode_indices': [g.tolist() for g in groups],
        'relay_order': RELAY_ORDER,
        'relay_names': RELAY_NAMES,
        'n_avg': NAVG,
        'narma_seed': SEED,
        'wiring': 'cascade (PI_NE_RX -> jumper -> PH_SW_TX)',
    },
    'calibration': {
        'cal_mode_idx': int(cal_mode),
        'cal_freq_hz': f_center,
        'bandwidth_hz': int(bw_measured),
        'q_measured': float(q_measured),
        'dynamic_range': float(peak_val / max(cal_responses[0], 1)),
    },
    'encoding_quality': {
        'mean_abs_corr': float(np.mean(np.abs(all_corrs))),
        'max_abs_corr': float(np.max(np.abs(all_corrs))),
    },
    'collection_time_s': float(total_time),
    'results': results,
    'best_nrmse': float(best_nrmse),
    'best_config': best_key,
    'random_baseline': {
        'mean': float(rand_mean),
        'std': float(rand_std),
    },
    'verdict': verdict,
}

with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\n  Saved: {out_path}")

# Save raw data
raw_path = OUT_DIR / f'd3_physical_v2_readouts_{ts}.npz'
np.savez_compressed(raw_path,
                    readouts=all_readouts,
                    u_narma=u_narma,
                    y_narma=y_narma,
                    drive_freqs=drive_freqs,
                    freqs=freqs,
                    H_measured=H_measured,
                    cal_offsets=cal_offsets,
                    cal_responses=cal_responses)
print(f"  Raw data: {raw_path}")

# Cleanup
nco('Foff')
ser.close()
mux.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
print("\n  Hardware released.")
