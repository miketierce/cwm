"""
NARMA-10 Temporal Reservoir — Ring-Up Approach
==============================================

Key insight: Instead of measuring RINGDOWN (signal after drive-off),
measure RING-UP (signal while plate is being driven). The plate amplitude
at any moment is a leaky integrator of recent drive history.

Method:
  - Continuous drive at resonant frequency (never fully off)
  - Each step: brief INTERRUPTION (gap) whose duration encodes u(n)
  - Capture DURING re-excitation after the gap
  - Amplitude at capture = (pre-gap level × e^{-gap/τ}) + ring-up contribution
  - This means: large signal (driven plate), and amplitude carries memory
    of ALL past steps through the exponential accumulation

Why this might help vs ringdown approach:
  1. MUCH higher SNR — reading at driven amplitude, not during decay
  2. Plate never goes to zero — always modulating around steady state
  3. The gap creates a "dip" whose depth encodes current input
  4. Recovery from dip depends on history (leaky integrator)
  5. Multi-mode readout: each mode has different τ → different memory depths

Physics:
  A(n) = A(n-1) × exp(-t_gap(n)/τ) × exp(t_drive(n)/τ_up)
  where t_gap(n) ∝ u(n), t_drive(n) = T_step - t_gap(n)
  The steady-state modulation depth depends on recent gap history.

Hardware: Same as E3/L1 — Pico NCO + dual-channel PicoScope

Usage:
  python3 tools/narma10_ringup_reservoir.py
  python3 tools/narma10_ringup_reservoir.py --steps 500
  python3 tools/narma10_ringup_reservoir.py --gap-max 3.0  # ms
"""
import ctypes as ct
import numpy as np
import serial
import time
import json
import argparse
from datetime import datetime
from pathlib import Path
from sklearn.linear_model import Ridge

# ─── Args ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='NARMA-10 ring-up reservoir')
parser.add_argument('--steps', type=int, default=1000,
                    help='NARMA-10 sequence length (default: 1000)')
parser.add_argument('--navg', type=int, default=1,
                    help='Captures per readout (default: 1, keep fast)')
parser.add_argument('--seed', type=int, default=42,
                    help='Random seed for NARMA-10 input')
parser.add_argument('--gap-max', type=float, default=4.0,
                    help='Max gap duration ms (default: 4.0)')
parser.add_argument('--drive-freq', type=int, default=35840,
                    help='Drive frequency Hz (default: 35840, highest Q)')
args = parser.parse_args()

# ─── Constants ────────────────────────────────────────────────────
NARMA_ORDER = 10
N_WASHOUT = 50

MODES_HZ = [35840, 54920, 57037, 97011, 42000, 45000, 71000, 88000, 108000]

# PicoScope config
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N = 3968; TIMEBASE = 7
FS = 781250.0; NFFT = N * 4; BIN_HZ = FS / NFFT
T_BLOCK = N * 1280e-9  # 5.08 ms per block

RNG_A = 6; RNG_A_MV = 2000.0
RNG_B = 6; RNG_B_MV = 2000.0

# ─── Hardware init ────────────────────────────────────────────────
print("=" * 70)
print("  NARMA-10 Temporal Reservoir — Ring-Up Approach")
print("=" * 70)
print()

ps = ct.CDLL(PICO_LIB)
ps.ps2000_close_unit(ct.c_int16(1))
time.sleep(0.3)

ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
if h <= 0:
    print(f"ERROR: PicoScope open failed (handle={h})")
    raise SystemExit(1)
ps.ps2000_set_channel(h, 0, 1, 0, RNG_A)
ps.ps2000_set_channel(h, 1, 1, 0, RNG_B)
print(f"  PicoScope handle: {h}")

ser = serial.Serial('/dev/cu.usbmodem113301', 115200, timeout=2)
time.sleep(0.5)
ser.reset_input_buffer()


def nco(cmd):
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()


def nco_fire(cmd):
    """Send NCO command without waiting for response (minimal latency)."""
    ser.write(f'{cmd}\n'.encode())


# ─── Capture ──────────────────────────────────────────────────────
buf_a = (ct.c_int16 * N)()
buf_b = (ct.c_int16 * N)()
ov = ct.c_int16()


def capture_dual_raw():
    ticks = ct.c_int32()
    ps.ps2000_run_block(h, N, TIMEBASE, 1, ct.byref(ticks))
    for _ in range(500):
        if ps.ps2000_ready(h):
            break
        time.sleep(0.001)
    ps.ps2000_get_values(h, ct.byref(buf_a), ct.byref(buf_b),
                         None, None, ct.byref(ov), N, 0)
    da = np.array(buf_a[:], dtype=np.float64) * (RNG_A_MV / 32767.0)
    db = np.array(buf_b[:], dtype=np.float64) * (RNG_B_MV / 32767.0)
    return da, db


def capture_dual_spectrum(navg=1):
    mags_a, mags_b = [], []
    for _ in range(navg):
        da, db = capture_dual_raw()
        da -= da.mean(); db -= db.mean()
        win = np.hanning(N)
        mags_a.append(np.abs(np.fft.rfft(da * win, n=NFFT)))
        mags_b.append(np.abs(np.fft.rfft(db * win, n=NFFT)))
    return np.mean(mags_a, axis=0), np.mean(mags_b, axis=0)


def peak_mag(sp, freq, w=5):
    b = int(round(freq / BIN_HZ))
    return float(sp[max(0, b-w):b+w+1].max())


def state_vector(navg=1):
    sp_a, sp_b = capture_dual_spectrum(navg)
    state = []
    for f in MODES_HZ:
        state.append(peak_mag(sp_a, f))
        state.append(peak_mag(sp_b, f))
    return np.array(state)


# ─── NARMA-10 ─────────────────────────────────────────────────────

def generate_narma10(n_steps, seed=42):
    rng = np.random.default_rng(seed)
    u = rng.uniform(0, 0.5, n_steps)
    y = np.zeros(n_steps)
    for t in range(NARMA_ORDER, n_steps - 1):
        y_sum = np.sum(y[t - 9:t + 1])
        y[t + 1] = (0.3 * y[t]
                    + 0.05 * y[t] * y_sum
                    + 1.5 * u[t - 9] * u[t]
                    + 0.1)
    return u, y


# ═══════════════════════════════════════════════════════════════════
#  RING-UP NARMA-10
# ═══════════════════════════════════════════════════════════════════

print(f"  Drive frequency: {args.drive_freq} Hz")
print(f"  Gap encoding: u(n) → gap of 0–{args.gap_max:.1f} ms")
print(f"  Readout: {len(MODES_HZ)} modes × 2 ch = {len(MODES_HZ)*2} features")
print(f"  NARMA-10 steps: {args.steps}")
print(f"  Method: continuous drive, gap encodes input, capture during ring-up")
print()

# Generate NARMA-10
u, y_target = generate_narma10(args.steps, seed=args.seed)

# Start continuous drive — let plate reach steady state
print("  [1] Starting continuous drive, reaching steady state (2s)...")
nco('Foff'); time.sleep(0.3)
nco(f'F1:{args.drive_freq}')
time.sleep(2.0)

# Verify: check amplitude at steady state
sp_a, sp_b = capture_dual_spectrum(4)
ss_a = peak_mag(sp_a, args.drive_freq)
ss_b = peak_mag(sp_b, args.drive_freq)
print(f"  Steady state: Ch A={ss_a:.0f}, Ch B={ss_b:.0f}")
print()

# ── Collect reservoir states ──
print(f"  [2] Collecting {args.steps} reservoir states (ring-up)...")
print(f"      Each step: F1 OFF for t_gap∝u(n) → F1 ON → capture during ring-up")
states = np.zeros((args.steps, len(MODES_HZ) * 2))

ser.read(ser.in_waiting)

t0 = time.time()
for step in range(args.steps):
    # Input encoding: INTERRUPT drive for t_gap proportional to u(n)
    # u ∈ [0, 0.5] → gap ∈ [0, gap_max ms]
    t_gap = u[step] * 2 * args.gap_max / 1000.0  # seconds

    if t_gap > 0.0003:  # > 0.3ms threshold
        nco_fire('Foff')
        time.sleep(t_gap)
        nco_fire(f'F1:{args.drive_freq}')
        # Brief ring-up before capture (~1ms for NCO to respond)

    # Capture DURING ring-up (drive is ON, plate recovering from gap)
    # The amplitude here reflects:
    #   - Current dip depth (from this gap) → encodes u(n)
    #   - Residual from past gaps → temporal memory
    states[step] = state_vector(args.navg)

    if (step + 1) % 50 == 0:
        ser.read(ser.in_waiting)
        elapsed = time.time() - t0
        rate = (step + 1) / elapsed
        eta = (args.steps - step - 1) / rate
        print(f"    {step+1}/{args.steps} — {rate:.1f} steps/s — ETA {eta:.0f}s")

total_time = time.time() - t0
step_time_ms = total_time / args.steps * 1000
rate = args.steps / total_time

nco('Foff')
print(f"  Collection done: {total_time:.1f}s ({rate:.1f} steps/s, {step_time_ms:.1f}ms/step)")
print(f"  Memory depth estimate: τ/T_step = 24.5/{step_time_ms:.1f} = {24.5/step_time_ms:.1f} steps")

# ── Verify signal modulation ──
print(f"\n  [3] Signal statistics...")
drive_idx = MODES_HZ.index(args.drive_freq)
# Ch B column for drive frequency
drive_states_b = states[:, drive_idx * 2 + 1]
print(f"  Drive freq (Ch B): mean={np.mean(drive_states_b):.0f}, "
      f"std={np.std(drive_states_b):.0f}, "
      f"CV={np.std(drive_states_b)/np.mean(drive_states_b)*100:.1f}%")
print(f"  Correlation with u(n): {np.corrcoef(u, drive_states_b)[0,1]:.3f}")
# Check if higher gaps → lower amplitude (expected)
high_u = u > 0.35
low_u = u < 0.15
if np.any(high_u) and np.any(low_u):
    print(f"  Mean amp (large gap, u>0.35): {np.mean(drive_states_b[high_u]):.0f}")
    print(f"  Mean amp (small gap, u<0.15): {np.mean(drive_states_b[low_u]):.0f}")
    contrast = np.mean(drive_states_b[low_u]) - np.mean(drive_states_b[high_u])
    print(f"  Contrast (small-large gap): {contrast:.0f} ({contrast/np.mean(drive_states_b)*100:.1f}%)")

# ── Train linear readout ──
print(f"\n  [4] Training linear readout (ridge regression)...")

start = NARMA_ORDER + N_WASHOUT
X = states[start:]
Y = y_target[start:]

X_mean = X.mean(axis=0)
X_std = X.std(axis=0)
X_std[X_std < 1e-10] = 1.0
X_norm = (X - X_mean) / X_std

n_total = len(X_norm)
n_train = int(0.8 * n_total)
X_train, X_test = X_norm[:n_train], X_norm[n_train:]
Y_train, Y_test = Y[:n_train], Y[n_train:]

best_nmse = np.inf
best_alpha = 1.0

for alpha in [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]:
    model = Ridge(alpha=alpha, fit_intercept=True)
    model.fit(X_train, Y_train)
    y_pred = model.predict(X_test)
    nmse = np.mean((y_pred - Y_test)**2) / np.var(Y_test)
    if nmse < best_nmse:
        best_nmse = nmse
        best_alpha = alpha

model = Ridge(alpha=best_alpha, fit_intercept=True)
model.fit(X_train, Y_train)
y_pred_train = model.predict(X_train)
y_pred_test = model.predict(X_test)

nmse_train = np.mean((y_pred_train - Y_train)**2) / np.var(Y_train)
nmse_test = np.mean((y_pred_test - Y_test)**2) / np.var(Y_test)
corr = float(np.corrcoef(y_pred_test, Y_test)[0, 1]) if len(Y_test) > 2 else 0

print(f"  Best alpha: {best_alpha}")
print(f"  NMSE train: {nmse_train:.4f}")
print(f"  NMSE test:  {nmse_test:.4f}")
print(f"  Correlation: {corr:.4f}")

# ── Memory capacity ──
print(f"\n  [5] Memory capacity...")
MC_total = 0
mc_per_delay = []
for k in range(12):
    if start + k >= len(u):
        mc_per_delay.append(0)
        continue
    u_delayed = u[start - k:len(u) - k] if k > 0 else u[start:]
    u_delayed = u_delayed[:len(X_norm)]
    if len(u_delayed) != len(X_norm):
        mc_per_delay.append(0)
        continue
    model_mc = Ridge(alpha=best_alpha, fit_intercept=True)
    model_mc.fit(X_train, u_delayed[:n_train])
    u_pred = model_mc.predict(X_test)
    u_test = u_delayed[n_train:]
    r2 = 1 - np.sum((u_pred - u_test)**2) / np.sum((u_test - u_test.mean())**2)
    mc_k = max(0, r2)
    mc_per_delay.append(mc_k)
    MC_total += mc_k

print(f"  Total MC: {MC_total:.2f}")
mc_str = ' '.join(f'k={i}:{mc_per_delay[i]:.2f}' for i in range(12))
print(f"  MC per delay: {mc_str}")

# ── Feature importance ──
print(f"\n  [6] Feature importance (top contributors)...")
weights = np.abs(model.coef_)
feature_names = []
for f in MODES_HZ:
    feature_names.append(f'{f}_A')
    feature_names.append(f'{f}_B')
top_idx = np.argsort(weights)[::-1][:10]
for rank, idx in enumerate(top_idx):
    print(f"    {rank+1}. {feature_names[idx]:>12} weight={weights[idx]:.4f}")

# ═══════════════════════════════════════════════════════════════════
#  Results
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  NARMA-10 (RING-UP) RESULTS")
print("=" * 70)
print(f"  Drive:           {args.drive_freq} Hz (continuous, gap-encoded)")
print(f"  Gap max:         {args.gap_max:.1f} ms")
print(f"  Reservoir dim:   {len(MODES_HZ)*2}")
print(f"  NMSE (test):     {nmse_test:.4f}")
print(f"  Correlation:     {corr:.4f}")
print(f"  Memory capacity: {MC_total:.2f}")
print(f"  Step rate:       {rate:.1f} steps/s")
print(f"  Step time:       {step_time_ms:.1f} ms")
print()

if nmse_test < 0.5:
    print("  ★★ PASS — NMSE < 0.5!")
elif nmse_test < 0.8:
    print("  ★ PARTIAL — NMSE < 0.8 (some prediction ability)")
else:
    print("  ✗ FAIL — NMSE ≥ 0.8")

print(f"\n  Comparison:")
print(f"    Ringdown (fundamental):  NMSE=1.08, MC=1.86")
print(f"    IM products:             NMSE=1.04, MC=1.04")
print(f"    Ring-up (this):          NMSE={nmse_test:.4f}, MC={MC_total:.2f}")

# ── Save ──
DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/narma10_ringup')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')

results = {
    'test': 'narma10_ringup_reservoir',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'drive_freq_hz': args.drive_freq,
        'gap_max_ms': args.gap_max,
        'n_steps': args.steps,
        'navg': args.navg,
        'seed': args.seed,
        'modes_hz': MODES_HZ,
        'method': 'continuous_drive_gap_encoded_ringup_readout',
    },
    'results': {
        'nmse_train': float(nmse_train),
        'nmse_test': float(nmse_test),
        'correlation': float(corr),
        'memory_capacity': float(MC_total),
        'mc_per_delay': mc_per_delay,
        'best_alpha': float(best_alpha),
        'step_rate_hz': float(rate),
        'step_time_ms': float(step_time_ms),
    },
    'signal_stats': {
        'drive_mean': float(np.mean(drive_states_b)),
        'drive_std': float(np.std(drive_states_b)),
        'drive_cv_pct': float(np.std(drive_states_b)/np.mean(drive_states_b)*100),
        'corr_u_vs_amp': float(np.corrcoef(u, drive_states_b)[0,1]),
        'steady_state_a': float(ss_a),
        'steady_state_b': float(ss_b),
    },
    'verdict': 'PASS' if nmse_test < 0.5 else ('PARTIAL' if nmse_test < 0.8 else 'FAIL'),
}

json_path = DATA_DIR / f'narma10_ringup_{ts}.json'
with open(json_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\n  Saved: {json_path}")

npz_path = DATA_DIR / f'narma10_ringup_{ts}.npz'
np.savez_compressed(npz_path, states=states, u=u, y_target=y_target,
                    y_pred_test=y_pred_test, Y_test=Y_test)
print(f"  Saved: {npz_path}")

# Cleanup
ser.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
print("\n  Done. Hardware released.")
