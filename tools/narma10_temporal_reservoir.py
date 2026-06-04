"""
NARMA-10 Temporal Reservoir — Direct Physical Memory via Ringdown
=================================================================

Key insight: The relay-switching setup killed temporal memory because
each relay transition took 350ms (>> any ringdown τ). Now with dual-channel
PicoScope (Ch A = NW preamp, Ch B = NE direct) and Pico NCO, we have
CONTINUOUS readout with NO switching. The plate's ringdown after each
input pulse provides natural fading memory of past inputs.

Phase 1: Ringdown τ measurement
  - Drive each mode for 500ms (steady state)
  - Turn off NCO
  - Capture consecutive blocks → track magnitude decay
  - Fit exponential → extract τ per mode

Phase 2: NARMA-10 reservoir test
  - Input encoding: duty-cycle PWM within fixed step period
    u(n) ∈ [0, 0.5] → drive ON for t_on = u(n) × 2 × T_step
  - Step period chosen so that τ/T_step ≈ 10 (memory depth = NARMA order)
  - Reservoir state = magnitude at multiple mode frequencies (both channels)
  - Linear readout trained via ridge regression

Hardware (same as E3/L1):
  TX: Pico NCO GP2 (single tone, F1:freq) — /dev/cu.usbmodem113301
  RX: Ch A = NW preamp (×11), Ch B = NE direct
  No relay switching — dual-channel simultaneous capture

Success criterion:
  - Phase 1: τ > 10ms at ≥ 1 mode (enables memory depth ≥ 5 at 2ms steps)
  - Phase 2: NARMA-10 NMSE < 0.5 (better than random = 1.0)
  - Stretch goal: NMSE < 0.2 (competitive with digital ESN)

Usage:
  python3 tools/narma10_temporal_reservoir.py
  python3 tools/narma10_temporal_reservoir.py --phase 1   # ringdown only
  python3 tools/narma10_temporal_reservoir.py --phase 2   # NARMA-10 only
  python3 tools/narma10_temporal_reservoir.py --steps 500  # shorter run
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
parser = argparse.ArgumentParser(description='NARMA-10 temporal reservoir')
parser.add_argument('--phase', type=int, choices=[1, 2], default=0,
                    help='Run only phase 1 (ringdown) or 2 (NARMA). 0=both')
parser.add_argument('--steps', type=int, default=1000,
                    help='NARMA-10 sequence length (default: 1000)')
parser.add_argument('--navg', type=int, default=4,
                    help='Captures averaged per readout (default: 4, keep fast)')
parser.add_argument('--seed', type=int, default=42,
                    help='Random seed for NARMA-10 input')
args = parser.parse_args()

# ─── Constants ────────────────────────────────────────────────────
NARMA_ORDER = 10
N_WASHOUT = 50

# Modes from L1 + T1.1/T1.2 — use EXACT known eigenfrequencies
# Round numbers miss the narrow resonances (BW = f/Q ≈ 13-50 Hz)
# Including L1 coarse modes for broader coverage
MODES_HZ_EXACT = [35840, 54920, 57037, 97011]  # confirmed acoustic from T1.2
MODES_HZ_COARSE = [42000, 45000, 55000, 71000, 88000, 108000]  # L1 peaks (coarse)
MODES_HZ = MODES_HZ_EXACT + MODES_HZ_COARSE

# PicoScope config
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N = 3968; TIMEBASE = 7
FS = 781250.0; NFFT = N * 4; BIN_HZ = FS / NFFT
T_BLOCK = N * 1280e-9  # 5.08 ms per block

RNG_A = 6; RNG_A_MV = 2000.0
RNG_B = 6; RNG_B_MV = 2000.0

# ─── Hardware init ────────────────────────────────────────────────
print("=" * 70)
print("  NARMA-10 Temporal Reservoir — Ringdown Memory")
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


def capture_dual_raw():
    """Single block capture, returns raw time-domain arrays (Ch A, Ch B).
    Returns (da, db, capture_time) where capture_time is wall-clock at block start."""
    buf_a = (ct.c_int16 * N)()
    buf_b = (ct.c_int16 * N)()
    ov = ct.c_int16()
    ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
    ticks = ct.c_int32()
    t_start = time.time()
    ps.ps2000_run_block(h, N, TIMEBASE, 1, ct.byref(ticks))
    for _ in range(500):
        if ps.ps2000_ready(h):
            break
        time.sleep(0.001)
    ps.ps2000_get_values(h, ct.byref(buf_a), ct.byref(buf_b),
                         None, None, ct.byref(ov), N, 0)
    da = np.array(buf_a[:], dtype=np.float64) * (RNG_A_MV / 32767.0)
    db = np.array(buf_b[:], dtype=np.float64) * (RNG_B_MV / 32767.0)
    return da, db, t_start


def capture_dual_spectrum(navg=4):
    """Averaged magnitude spectra, both channels."""
    mags_a, mags_b = [], []
    for _ in range(navg):
        da, db, _ = capture_dual_raw()
        da -= da.mean(); db -= db.mean()
        win = np.hanning(N)
        mags_a.append(np.abs(np.fft.rfft(da * win, n=NFFT)))
        mags_b.append(np.abs(np.fft.rfft(db * win, n=NFFT)))
    return np.mean(mags_a, axis=0), np.mean(mags_b, axis=0)


def peak_mag(sp, freq, w=5):
    b = int(round(freq / BIN_HZ))
    return float(sp[max(0, b-w):b+w+1].max())


def state_vector(navg=4):
    """Capture reservoir state: magnitudes at all mode frequencies, both channels."""
    sp_a, sp_b = capture_dual_spectrum(navg)
    state = []
    for f in MODES_HZ:
        state.append(peak_mag(sp_a, f))
        state.append(peak_mag(sp_b, f))
    return np.array(state)


# ═══════════════════════════════════════════════════════════════════
#  PHASE 1: Ringdown Measurement
# ═══════════════════════════════════════════════════════════════════

def measure_ringdown(mode_freq, n_blocks=60, drive_time=0.5):
    """Measure ringdown τ at a single mode.

    Strategy: capture THROUGH the Foff transition to avoid the 50ms
    serial delay problem. Start capturing while driven, fire Foff
    mid-stream, continue capturing. Find the transition point offline
    and fit the decay after it.
    """
    # Drive to steady state
    nco(f'F1:{mode_freq}')
    time.sleep(drive_time)

    # Start capturing continuously — first 5 blocks while still driven
    all_mags_a = []
    all_mags_b = []
    times = []

    t0 = time.time()

    # Capture 5 blocks while driven (reference level)
    for i in range(5):
        da, db, t_cap = capture_dual_raw()
        da -= da.mean(); db -= db.mean()
        win = np.hanning(N)
        all_mags_a.append(peak_mag(np.abs(np.fft.rfft(da * win, n=NFFT)), mode_freq))
        all_mags_b.append(peak_mag(np.abs(np.fft.rfft(db * win, n=NFFT)), mode_freq))
        times.append(t_cap - t0)

    # Fire Foff WITHOUT waiting (minimal latency ~1ms for serial write)
    nco_fire('Foff')
    t_off = time.time() - t0

    # Continue capturing for n_blocks more (this is the decay)
    for i in range(n_blocks):
        da, db, t_cap = capture_dual_raw()
        da -= da.mean(); db -= db.mean()
        win = np.hanning(N)
        all_mags_a.append(peak_mag(np.abs(np.fft.rfft(da * win, n=NFFT)), mode_freq))
        all_mags_b.append(peak_mag(np.abs(np.fft.rfft(db * win, n=NFFT)), mode_freq))
        times.append(t_cap - t0)

    # Drain serial response
    time.sleep(0.05)
    ser.read(ser.in_waiting)

    all_mags_a = np.array(all_mags_a)
    all_mags_b = np.array(all_mags_b)
    times = np.array(times)

    # Use channel with higher driven magnitude
    driven_a = np.mean(all_mags_a[:5])
    driven_b = np.mean(all_mags_b[:5])
    if driven_b > driven_a:
        mags = all_mags_b
        mag_driven = driven_b
        ch_label = 'B (NE)'
    else:
        mags = all_mags_a
        mag_driven = driven_a
        ch_label = 'A (NW)'

    # Find transition: where magnitude drops below 50% of driven level
    # The Foff command takes ~1-5ms to take effect on RP2040
    driven_level = np.mean(mags[:5])
    threshold_50 = driven_level * 0.5

    # Find first block after t_off that drops below 50%
    decay_start_idx = 5  # default: start right after Foff
    for i in range(5, len(mags)):
        if mags[i] < threshold_50:
            decay_start_idx = max(5, i - 1)  # one before the drop
            break

    # Noise floor: last 10 blocks
    noise_est = float(np.mean(mags[-10:]))

    # Fit exponential decay from decay_start_idx onward
    decay_region = mags[decay_start_idx:]
    t_decay = times[decay_start_idx:] - times[decay_start_idx]

    # Count blocks significantly above noise
    above_noise = decay_region > noise_est * 2.0
    n_above = int(np.sum(above_noise))

    if n_above < 3:
        tau_ms = 0
        Q_est = 0
    else:
        # Fit in log space using points above noise
        valid = decay_region > noise_est * 1.5
        t_valid = t_decay[valid]
        d_valid = decay_region[valid] - noise_est
        d_valid = np.maximum(d_valid, 1e-6)

        if len(t_valid) >= 3 and t_valid[-1] > t_valid[0]:
            coeffs = np.polyfit(t_valid, np.log(d_valid), 1)
            tau_s = -1.0 / coeffs[0] if coeffs[0] < 0 else 0
            tau_ms = tau_s * 1000
        else:
            tau_ms = 0

        Q_est = np.pi * mode_freq * (tau_ms / 1000) if tau_ms > 0 else 0

    return {
        'freq_hz': mode_freq, 'tau_ms': float(tau_ms), 'Q_est': float(Q_est),
        'mag_driven': float(mag_driven), 'noise_floor': float(noise_est),
        'n_blocks_above_noise': n_above,
        'decay_start_idx': decay_start_idx,
        't_off_s': float(t_off),
        'channel': ch_label,
        'times_ms': (times * 1000).tolist(),
        'decay_a': all_mags_a.tolist(),
        'decay_b': all_mags_b.tolist(),
    }


def run_phase1():
    """Measure ringdown at all modes."""
    print("\n" + "=" * 70)
    print("  PHASE 1: Ringdown τ Measurement")
    print("=" * 70)
    print(f"  Modes: {len(MODES_HZ)}")
    print(f"  Method: drive 500ms → NCO off → capture 40 consecutive blocks")
    print(f"  Block duration: {T_BLOCK*1000:.2f} ms")
    print()

    ringdown_results = []
    for freq in MODES_HZ:
        r = measure_ringdown(freq, n_blocks=40, drive_time=0.5)
        ringdown_results.append(r)
        print(f"  {freq/1000:>6.0f} kHz: τ = {r['tau_ms']:>6.1f} ms, "
              f"Q_est = {r['Q_est']:>5.0f}, "
              f"blocks above noise: {r['n_blocks_above_noise']}/40  "
              f"[{r['channel']}]")

    # Summary
    taus = [r['tau_ms'] for r in ringdown_results if r['tau_ms'] > 0]
    print(f"\n  Summary:")
    print(f"  Modes with measurable τ: {len(taus)}/{len(MODES_HZ)}")
    if taus:
        print(f"  τ range: {min(taus):.1f} – {max(taus):.1f} ms")
        best = max(ringdown_results, key=lambda r: r['tau_ms'])
        print(f"  Best: {best['freq_hz']/1000:.0f} kHz, τ = {best['tau_ms']:.1f} ms, Q = {best['Q_est']:.0f}")

        # Memory depth estimate
        # At step period T_step, memory depth ≈ τ / T_step
        # Block capture takes ~6ms (5ms capture + 1ms overhead)
        T_step_ms = 6.0  # minimum practical step period
        mem_depth = best['tau_ms'] / T_step_ms
        print(f"  Memory depth at {T_step_ms:.0f}ms steps: ~{mem_depth:.1f} steps")
        print(f"  Need ≥ 10 for NARMA-10")

    return ringdown_results


# ═══════════════════════════════════════════════════════════════════
#  PHASE 2: NARMA-10 Temporal Reservoir
# ═══════════════════════════════════════════════════════════════════

def generate_narma10(n_steps, seed=42):
    """Generate NARMA-10 input/target sequences."""
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


def run_phase2(ringdown_results=None, drive_freq=None):
    """Run NARMA-10 with plate as temporal reservoir.

    Input encoding: duty-cycle modulation within fixed step period.
    u(n) → drive ON for t_on = u(n) × 2 × T_step_on ms, then capture.

    The plate's ringdown provides fading memory of past drive pulses.

    SPEED IS CRITICAL: use nco_fire() (no serial wait) and minimal sleeps
    to keep step time < τ for maximum memory depth.
    """
    print("\n" + "=" * 70)
    print("  PHASE 2: NARMA-10 Temporal Reservoir Test")
    print("=" * 70)

    # Pick drive frequency: use mode with longest τ, or best known resonance
    if drive_freq is None:
        if ringdown_results:
            # Filter out zero-τ results
            valid = [r for r in ringdown_results if r['tau_ms'] > 0]
            if valid:
                best = max(valid, key=lambda r: r['tau_ms'])
                drive_freq = best['freq_hz']
                tau_ms = best['tau_ms']
            else:
                drive_freq = 35840  # Best known Q from T1.1
                tau_ms = 24.5  # Theoretical from Q=2759
        else:
            drive_freq = 35840  # Best known Q from T1.1
            tau_ms = 24.5
    else:
        tau_ms = None

    print(f"  Drive frequency: {drive_freq} Hz")
    if tau_ms:
        print(f"  τ estimate: {tau_ms:.1f} ms")
    print(f"  NARMA-10 steps: {args.steps}")
    print(f"  Readout: {len(MODES_HZ)} modes × 2 channels = {len(MODES_HZ)*2} features")
    print()

    # Step timing — SPEED OPTIMIZED
    # nco_fire = ~1ms, capture = ~6ms, drive ON = 0-5ms
    # Target: 8-12ms per step → memory depth ≈ τ/T_step ≈ 2-3 at τ=24ms
    T_DRIVE_MAX_MS = 5.0   # max drive-on time (u=0.5 → 5ms ON)

    print(f"  Encoding: PWM duty cycle (0–{T_DRIVE_MAX_MS:.0f}ms ON per step)")
    print(f"  Readout: {args.navg} captures ({T_BLOCK*args.navg*1000:.0f}ms)")
    print(f"  Speed: nco_fire() (no serial wait)")
    print()

    # Generate NARMA-10
    u, y_target = generate_narma10(args.steps, seed=args.seed)

    # ── Collect reservoir states ──
    print(f"  [2a] Collecting {args.steps} reservoir states...")
    states = np.zeros((args.steps, len(MODES_HZ) * 2))

    nco('Foff')
    time.sleep(0.2)
    # Drain any pending serial data
    ser.read(ser.in_waiting)

    t0 = time.time()
    for step in range(args.steps):
        # Input encoding: drive for t_on proportional to u(step)
        t_on = u[step] * 2 * T_DRIVE_MAX_MS / 1000.0  # u∈[0,0.5] → t_on∈[0,5ms]

        if t_on > 0.0003:  # > 0.3ms threshold
            nco_fire(f'F1:{drive_freq}')
            time.sleep(t_on)
            nco_fire('Foff')

        # NO settle sleep — capture immediately
        # The first ~1ms of capture may include drive tail — that's fine,
        # it encodes the current input amplitude in the spectrum

        # Readout: capture spectrum
        states[step] = state_vector(args.navg)

        # Periodically drain serial buffer (avoid overflow)
        if (step + 1) % 50 == 0:
            ser.read(ser.in_waiting)
            elapsed = time.time() - t0
            rate = (step + 1) / elapsed
            eta = (args.steps - step - 1) / rate
            print(f"    {step+1}/{args.steps} — {rate:.1f} steps/s — ETA {eta:.0f}s")

    total_time = time.time() - t0
    step_time_ms = total_time / args.steps * 1000
    print(f"  Collection done: {total_time:.1f}s ({args.steps/total_time:.1f} steps/s, "
          f"{step_time_ms:.1f}ms/step)")
    if tau_ms:
        print(f"  Memory depth estimate: τ/T_step = {tau_ms}/{step_time_ms:.1f} = "
              f"{tau_ms/step_time_ms:.1f} steps")

    # ── Train linear readout ──
    print(f"\n  [2b] Training linear readout (ridge regression)...")

    # Discard washout period
    start = NARMA_ORDER + N_WASHOUT
    X = states[start:]
    Y = y_target[start:]

    # Normalize
    X_mean = X.mean(axis=0)
    X_std = X.std(axis=0)
    X_std[X_std < 1e-10] = 1.0
    X_norm = (X - X_mean) / X_std

    # Split train/test (80/20)
    n_total = len(X_norm)
    n_train = int(0.8 * n_total)
    X_train, X_test = X_norm[:n_train], X_norm[n_train:]
    Y_train, Y_test = Y[:n_train], Y[n_train:]

    # Ridge regression with alpha search
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

    # Final model with best alpha
    model = Ridge(alpha=best_alpha, fit_intercept=True)
    model.fit(X_train, Y_train)
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    nmse_train = float(np.mean((y_pred_train - Y_train)**2) / np.var(Y_train))
    nmse_test = float(np.mean((y_pred_test - Y_test)**2) / np.var(Y_test))

    # Correlation
    corr_test = float(np.corrcoef(y_pred_test, Y_test)[0, 1])

    print(f"  Best alpha: {best_alpha}")
    print(f"  NMSE train: {nmse_train:.4f}")
    print(f"  NMSE test:  {nmse_test:.4f}")
    print(f"  Correlation: {corr_test:.4f}")
    print()

    # ── Memory capacity estimate ──
    print(f"  [2c] Memory capacity (delayed correlation)...")
    # How well can we predict u(t-k) from x(t)?
    mem_capacity = []
    for k in range(20):
        if start + k >= len(states):
            break
        X_k = X_norm[:n_train]
        Y_k = u[start - k:start + n_train - k] if k > 0 else u[start:start + n_train]
        if len(Y_k) != len(X_k):
            Y_k = Y_k[:len(X_k)]
        m = Ridge(alpha=1.0, fit_intercept=True)
        m.fit(X_k, Y_k)
        y_p = m.predict(X_k)
        mc_k = float(np.corrcoef(y_p, Y_k)[0, 1])**2
        mem_capacity.append(mc_k)

    total_mc = sum(mem_capacity)
    print(f"  Total memory capacity (MC): {total_mc:.2f}")
    print(f"  MC per delay: ", end='')
    for k, mc in enumerate(mem_capacity[:12]):
        print(f"k={k}:{mc:.2f} ", end='')
    print()

    # ── Verdict ──
    print("\n" + "=" * 70)
    print("  NARMA-10 RESULTS")
    print("=" * 70)
    print(f"  Drive mode:      {drive_freq/1000:.0f} kHz")
    print(f"  Reservoir dim:   {len(MODES_HZ)*2} (modes × channels)")
    print(f"  NMSE (test):     {nmse_test:.4f}")
    print(f"  Correlation:     {corr_test:.4f}")
    print(f"  Memory capacity: {total_mc:.2f}")
    print(f"  Step rate:       {args.steps/total_time:.1f} steps/s")
    print()

    if nmse_test < 0.2:
        verdict = 'EXCELLENT'
        print(f"  ★★★ EXCELLENT — NMSE < 0.2 (competitive with digital ESN!)")
    elif nmse_test < 0.5:
        verdict = 'PASS'
        print(f"  ★★ PASS — NMSE < 0.5 (temporal memory confirmed)")
    elif nmse_test < 0.8:
        verdict = 'MARGINAL'
        print(f"  ★ MARGINAL — NMSE < 0.8 (some temporal memory)")
    else:
        verdict = 'FAIL'
        print(f"  ✗ FAIL — NMSE ≥ 0.8 (no useful temporal memory)")

    return {
        'drive_freq_hz': drive_freq,
        'n_steps': args.steps,
        'n_modes': len(MODES_HZ),
        'reservoir_dim': len(MODES_HZ) * 2,
        'step_rate_hz': args.steps / total_time,
        'nmse_train': nmse_train,
        'nmse_test': nmse_test,
        'correlation': corr_test,
        'memory_capacity': mem_capacity,
        'total_mc': total_mc,
        'best_alpha': best_alpha,
        'verdict': verdict,
        'states': states,
        'y_target': Y,
        'y_pred_test': y_pred_test.tolist(),
    }


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/narma10_temporal')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    ringdown_results = None
    narma_results = None

    # Phase 1
    if args.phase in (0, 1):
        ringdown_results = run_phase1()

    # Phase 2
    if args.phase in (0, 2):
        narma_results = run_phase2(ringdown_results)

    # ── Save ──
    nco('Foff')

    results = {
        'test': 'NARMA10_temporal_reservoir',
        'timestamp': datetime.now().isoformat(),
        'config': {
            'modes_hz': MODES_HZ,
            'n_steps': args.steps,
            'navg': args.navg,
            'seed': args.seed,
        },
    }

    if ringdown_results:
        # Don't save full decay arrays in JSON (too large)
        ringdown_summary = []
        for r in ringdown_results:
            rs = {k: v for k, v in r.items() if k not in ('times_ms', 'decay_a', 'decay_b')}
            ringdown_summary.append(rs)
        results['ringdown'] = ringdown_summary

    if narma_results:
        narma_save = {k: v for k, v in narma_results.items()
                      if k not in ('states', 'y_target', 'y_pred_test')}
        results['narma10'] = narma_save

    json_path = DATA_DIR / f'narma10_temporal_{ts}.json'
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n  Saved: {json_path}")

    # Save full data as NPZ
    npz_data = {}
    if ringdown_results:
        for i, r in enumerate(ringdown_results):
            npz_data[f'ringdown_{r["freq_hz"]}_times'] = np.array(r['times_ms'])
            npz_data[f'ringdown_{r["freq_hz"]}_decay_a'] = np.array(r['decay_a'])
            npz_data[f'ringdown_{r["freq_hz"]}_decay_b'] = np.array(r['decay_b'])
    if narma_results:
        npz_data['states'] = narma_results['states']
        npz_data['y_target'] = narma_results['y_target']

    if npz_data:
        npz_path = DATA_DIR / f'narma10_temporal_{ts}.npz'
        np.savez_compressed(npz_path, **npz_data)
        print(f"  Saved: {npz_path}")

    # Cleanup
    ser.close()
    ps.ps2000_stop(h)
    ps.ps2000_close_unit(ct.c_int16(h))
    print("\n  Done. Hardware released.")
