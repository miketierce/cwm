"""
NARMA-10 via Intermodulation Products (IM Temporal Memory)
==========================================================

Key insight: Keep a "carrier" tone F1 running continuously at resonance.
Encode input as presence/absence (or duty cycle) of a second tone F2.
The plate's nonlinearity generates intermodulation products (F1±F2, 2F1-F2,
etc.) that exist ONLY while both tones are present.

Why IM products might have longer memory:
1. IM products are proportional to product of mode amplitudes (quadratic)
   → they arise from energy stored in BOTH modes simultaneously
2. If the nonlinearity is in the putty/boundary (not the glass), the
   IM generation involves mechanical coupling with its OWN time constant
3. Even if IM decay matches fundamental τ, the continuous F1 carrier means
   the plate is ALWAYS energized — we're modulating a running oscillation
   rather than starting/stopping from cold

Phase 1: IM characterization
  - Drive F1 continuously, sweep F2 to find strongest IM products
  - Measure IM ringdown after F2 off (F1 still running)
  - Compare IM τ to fundamental τ

Phase 2: NARMA-10 with IM readout
  - Input encoding: F2 duty cycle ∝ u(n)
  - Readout: magnitude at multiple IM frequencies (F1±F2, 2F1-F2, etc.)
  - The IM products serve as nonlinear mixing of current + past inputs
  - F1 carrier provides continuous "memory pump" to sustain energy

Hardware (same as E3/L1):
  TX: Pico NCO GP2 (F1 continuous) + GP3 (F2 pulsed)
  RX: Ch A = NW preamp, Ch B = NE direct
  No relay switching

Usage:
  python3 tools/narma10_im_reservoir.py
  python3 tools/narma10_im_reservoir.py --phase 1   # IM characterization only
  python3 tools/narma10_im_reservoir.py --phase 2   # NARMA-10 only
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
parser = argparse.ArgumentParser(description='NARMA-10 via IM products')
parser.add_argument('--phase', type=int, choices=[1, 2], default=0,
                    help='Run only phase 1 (IM char) or 2 (NARMA). 0=both')
parser.add_argument('--steps', type=int, default=500,
                    help='NARMA-10 sequence length (default: 500)')
parser.add_argument('--navg', type=int, default=1,
                    help='Captures averaged per readout (default: 1)')
parser.add_argument('--seed', type=int, default=42,
                    help='Random seed for NARMA-10 input')
parser.add_argument('--f1', type=int, default=54920,
                    help='Carrier frequency F1 (default: 54920 Hz, strong mode)')
parser.add_argument('--f2', type=int, default=35840,
                    help='Input frequency F2 (default: 35840 Hz, high-Q mode)')
args = parser.parse_args()

# ─── Constants ────────────────────────────────────────────────────
NARMA_ORDER = 10
N_WASHOUT = 50
F1 = args.f1
F2 = args.f2

# Predicted IM frequencies (from nonlinear mixing)
IM_FREQS = sorted(set([
    abs(F1 - F2),           # difference
    F1 + F2,                # sum
    abs(2*F1 - F2),         # 3rd order
    abs(2*F2 - F1),         # 3rd order
    abs(3*F1 - 2*F2),       # 5th order
    abs(3*F2 - 2*F1),       # 5th order
    2*F1,                   # 2nd harmonic of carrier
    2*F2,                   # 2nd harmonic of input
]))

# Also include the fundamentals + some broadband monitors
READOUT_FREQS = sorted(set([F1, F2] + IM_FREQS))
# Filter to Nyquist (fs/2 = 390625 Hz)
READOUT_FREQS = [f for f in READOUT_FREQS if f < 350000]

# PicoScope config
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N = 3968; TIMEBASE = 7
FS = 781250.0; NFFT = N * 4; BIN_HZ = FS / NFFT
T_BLOCK = N * 1280e-9  # 5.08 ms per block

RNG_A = 6; RNG_A_MV = 2000.0
RNG_B = 6; RNG_B_MV = 2000.0

# ─── Hardware init ────────────────────────────────────────────────
print("=" * 70)
print("  NARMA-10 via Intermodulation Products")
print("=" * 70)
print(f"  F1 (carrier, continuous): {F1} Hz")
print(f"  F2 (input, pulsed):      {F2} Hz")
print(f"  IM frequencies monitored: {len(IM_FREQS)}")
for f in IM_FREQS:
    label = ''
    if f == abs(F1-F2): label = ' (F1-F2)'
    elif f == F1+F2: label = ' (F1+F2)'
    elif f == abs(2*F1-F2): label = ' (2F1-F2)'
    elif f == abs(2*F2-F1): label = ' (2F2-F1)'
    elif f == 2*F1: label = ' (2×F1)'
    elif f == 2*F2: label = ' (2×F2)'
    print(f"    {f:>8,} Hz{label}")
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
    """Single block capture, both channels."""
    buf_a = (ct.c_int16 * N)()
    buf_b = (ct.c_int16 * N)()
    ov = ct.c_int16()
    ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
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


def get_spectrum(navg=1):
    """Get averaged magnitude spectra, both channels."""
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
    """Readout: magnitudes at all monitored frequencies, both channels."""
    sp_a, sp_b = get_spectrum(navg)
    state = []
    for f in READOUT_FREQS:
        state.append(peak_mag(sp_a, f))
        state.append(peak_mag(sp_b, f))
    return np.array(state)


# ═══════════════════════════════════════════════════════════════════
#  PHASE 1: IM Characterization
# ═══════════════════════════════════════════════════════════════════

def run_phase1():
    """Characterize IM products and their ringdown (F2 off, F1 still running)."""
    print("\n" + "=" * 70)
    print("  PHASE 1: Intermodulation Product Characterization")
    print("=" * 70)

    # Step 1: Baseline with F1 only
    print("\n  [1a] Baseline: F1 only...")
    nco('Foff'); time.sleep(0.3)
    nco(f'F1:{F1}')
    time.sleep(1.0)  # Steady state
    sp_a_f1only, sp_b_f1only = get_spectrum(10)

    print(f"    F1 ({F1} Hz): A={peak_mag(sp_a_f1only, F1):.0f}, B={peak_mag(sp_b_f1only, F1):.0f}")
    for f in IM_FREQS:
        ma = peak_mag(sp_a_f1only, f)
        mb = peak_mag(sp_b_f1only, f)
        print(f"    {f:>8,} Hz: A={ma:.0f}, B={mb:.0f} (baseline)")

    # Step 2: Both tones → IM products appear
    print("\n  [1b] Both tones (F1 + F2)...")
    nco(f'F2:{F2}')
    time.sleep(1.0)  # Let IM products build up
    sp_a_both, sp_b_both = get_spectrum(10)

    print(f"    F1 ({F1} Hz): A={peak_mag(sp_a_both, F1):.0f}, B={peak_mag(sp_b_both, F1):.0f}")
    print(f"    F2 ({F2} Hz): A={peak_mag(sp_a_both, F2):.0f}, B={peak_mag(sp_b_both, F2):.0f}")

    im_results = []
    print(f"\n    IM products (both tones vs F1-only):")
    print(f"    {'Freq':>10} {'Both_A':>8} {'Base_A':>8} {'Ratio':>6}  {'Both_B':>8} {'Base_B':>8} {'Ratio':>6}")
    for f in IM_FREQS:
        ma_both = peak_mag(sp_a_both, f)
        ma_base = peak_mag(sp_a_f1only, f)
        mb_both = peak_mag(sp_b_both, f)
        mb_base = peak_mag(sp_b_f1only, f)
        ratio_a = ma_both / ma_base if ma_base > 0 else 0
        ratio_b = mb_both / mb_base if mb_base > 0 else 0
        im_results.append({
            'freq_hz': f,
            'mag_a_both': float(ma_both), 'mag_a_baseline': float(ma_base),
            'mag_b_both': float(mb_both), 'mag_b_baseline': float(mb_base),
            'ratio_a': float(ratio_a), 'ratio_b': float(ratio_b),
        })
        print(f"    {f:>10,} {ma_both:>8.0f} {ma_base:>8.0f} {ratio_a:>6.1f}× "
              f" {mb_both:>8.0f} {mb_base:>8.0f} {ratio_b:>6.1f}×")

    # Step 3: IM ringdown — turn F2 OFF, keep F1 running, track IM decay
    print(f"\n  [1c] IM ringdown (F2 off, F1 stays on)...")
    print(f"    Capturing through F2-off transition...")

    # Capture 5 blocks with both tones (reference)
    im_decay = {f: [] for f in IM_FREQS}
    im_times = []
    f2_mag_decay = []

    t0 = time.time()

    # 5 blocks with both tones
    for i in range(5):
        sp_a, sp_b = get_spectrum(1)
        im_times.append(time.time() - t0)
        for f in IM_FREQS:
            im_decay[f].append(peak_mag(sp_b, f))  # Ch B (NE) typically stronger
        f2_mag_decay.append(peak_mag(sp_b, F2))

    # Turn F2 off — set to 1 Hz (can't do F2:off, Foff kills both)
    nco_fire('F2:1')
    t_off = time.time() - t0

    # 50 blocks with F1 only — watch IM products decay
    for i in range(50):
        sp_a, sp_b = get_spectrum(1)
        im_times.append(time.time() - t0)
        for f in IM_FREQS:
            im_decay[f].append(peak_mag(sp_b, f))
        f2_mag_decay.append(peak_mag(sp_b, F2))

    # Drain serial
    time.sleep(0.05)
    ser.read(ser.in_waiting)

    im_times = np.array(im_times)

    # Fit decay for each IM frequency
    print(f"\n    IM ringdown results (F2 off at t={t_off*1000:.1f}ms):")
    print(f"    {'Freq':>10} {'Driven':>8} {'After 5blk':>10} {'After 10blk':>11} {'τ_fit (ms)':>10} {'Blocks>2×noise':>14}")

    im_tau_results = []
    for f in IM_FREQS:
        decay = np.array(im_decay[f])
        driven_level = np.mean(decay[:5])
        noise_level = np.mean(decay[-10:])

        # Count blocks above 2× noise after F2-off
        post_off = decay[5:]
        above = np.sum(post_off > noise_level * 2.0)

        after_5 = decay[10] if len(decay) > 10 else 0
        after_10 = decay[15] if len(decay) > 15 else 0

        # Fit τ
        tau_ms = 0
        if above >= 3:
            t_post = im_times[5:] - im_times[5]
            valid = post_off > noise_level * 1.5
            if np.sum(valid) >= 3:
                t_v = t_post[valid]
                d_v = post_off[valid] - noise_level
                d_v = np.maximum(d_v, 1e-6)
                if len(t_v) >= 3 and t_v[-1] > t_v[0]:
                    coeffs = np.polyfit(t_v, np.log(d_v), 1)
                    if coeffs[0] < 0:
                        tau_ms = -1000.0 / coeffs[0]

        im_tau_results.append({
            'freq_hz': f, 'tau_ms': float(tau_ms),
            'driven_level': float(driven_level),
            'noise_level': float(noise_level),
            'blocks_above_noise': int(above),
        })

        print(f"    {f:>10,} {driven_level:>8.0f} {after_5:>10.0f} {after_10:>11.0f} "
              f"{tau_ms:>10.1f} {above:>14}")

    # Also check F2 fundamental decay (for comparison)
    f2_decay = np.array(f2_mag_decay)
    f2_driven = np.mean(f2_decay[:5])
    f2_noise = np.mean(f2_decay[-10:])
    f2_above = int(np.sum(f2_decay[5:] > f2_noise * 2.0))
    print(f"\n    F2 fundamental ({F2} Hz) for comparison:")
    print(f"    Driven: {f2_driven:.0f}, Noise: {f2_noise:.0f}, Blocks above 2×noise: {f2_above}")

    nco('Foff')

    return im_results, im_tau_results, im_decay, im_times


# ═══════════════════════════════════════════════════════════════════
#  PHASE 2: NARMA-10 with IM Readout
# ═══════════════════════════════════════════════════════════════════

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


def run_phase2():
    """NARMA-10 with continuous carrier + pulsed input tone.

    Encoding: F1 runs continuously. F2 duty cycle ∝ u(n).
    Readout: magnitudes at IM frequencies (arise from nonlinear mixing).

    The IM products encode the PRODUCT of the two mode amplitudes —
    this is inherently nonlinear, which is exactly what a reservoir needs.
    Plus, the continuous F1 means the plate is always energized, so
    we're modulating around a steady state rather than cold-starting.
    """
    print("\n" + "=" * 70)
    print("  PHASE 2: NARMA-10 with IM Product Readout")
    print("=" * 70)

    print(f"  F1 (carrier): {F1} Hz — ALWAYS ON")
    print(f"  F2 (input):   {F2} Hz — duty cycle encodes u(n)")
    print(f"  Readout:      {len(READOUT_FREQS)} freqs × 2 ch = {len(READOUT_FREQS)*2} features")
    print(f"  Steps:        {args.steps}")
    print()

    T_DRIVE_MAX_MS = 5.0  # Max F2-on time per step

    # Generate NARMA-10
    u, y_target = generate_narma10(args.steps, seed=args.seed)

    # Start F1 carrier
    nco('Foff'); time.sleep(0.3)
    nco(f'F1:{F1}')
    time.sleep(1.0)  # Let carrier reach steady state
    print(f"  F1 carrier started. Letting plate reach steady state (1s)...")

    # Collect states
    print(f"  [2a] Collecting {args.steps} reservoir states...")
    states = np.zeros((args.steps, len(READOUT_FREQS) * 2))

    ser.read(ser.in_waiting)

    t0 = time.time()
    for step in range(args.steps):
        # Input encoding: F2 ON for t_on ∝ u(step), then OFF
        t_on = u[step] * 2 * T_DRIVE_MAX_MS / 1000.0  # [0, 5ms]

        if t_on > 0.0003:
            nco_fire(f'F2:{F2}')
            time.sleep(t_on)
            nco_fire('F2:1')  # "off" = set to 1 Hz (inaudible)

        # Readout immediately — IM products are decaying, F1 still running
        # The state captures: residual IM energy + F1 steady state + F2 ringdown
        states[step] = state_vector(args.navg)

        if (step + 1) % 50 == 0:
            ser.read(ser.in_waiting)
            elapsed = time.time() - t0
            rate = (step + 1) / elapsed
            eta = (args.steps - step - 1) / rate
            print(f"    {step+1}/{args.steps} — {rate:.1f} steps/s — ETA {eta:.0f}s")

    total_time = time.time() - t0
    step_time_ms = total_time / args.steps * 1000

    nco('Foff')

    print(f"  Collection done: {total_time:.1f}s ({args.steps/total_time:.1f} steps/s, "
          f"{step_time_ms:.1f}ms/step)")

    # ── Train linear readout ──
    print(f"\n  [2b] Training linear readout...")

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

    nmse_train = float(np.mean((y_pred_train - Y_train)**2) / np.var(Y_train))
    nmse_test = float(np.mean((y_pred_test - Y_test)**2) / np.var(Y_test))
    corr_test = float(np.corrcoef(y_pred_test, Y_test)[0, 1])

    print(f"  Best alpha: {best_alpha}")
    print(f"  NMSE train: {nmse_train:.4f}")
    print(f"  NMSE test:  {nmse_test:.4f}")
    print(f"  Correlation: {corr_test:.4f}")

    # ── Memory capacity ──
    print(f"\n  [2c] Memory capacity...")
    mem_capacity = []
    for k in range(20):
        X_k = X_norm[:n_train]
        y_k_start = start - k
        y_k_end = start + n_train - k
        if y_k_start < 0:
            break
        Y_k = u[y_k_start:y_k_end]
        if len(Y_k) != len(X_k):
            Y_k = Y_k[:len(X_k)]
        m = Ridge(alpha=1.0, fit_intercept=True)
        m.fit(X_k, Y_k)
        y_p = m.predict(X_k)
        mc_k = float(np.corrcoef(y_p, Y_k)[0, 1])**2
        mem_capacity.append(mc_k)

    total_mc = sum(mem_capacity)
    print(f"  Total MC: {total_mc:.2f}")
    print(f"  MC per delay: ", end='')
    for k, mc in enumerate(mem_capacity[:12]):
        print(f"k={k}:{mc:.2f} ", end='')
    print()

    # ── Feature importance (which frequencies carry memory?) ──
    print(f"\n  [2d] Feature importance (top contributors)...")
    weights = np.abs(model.coef_)
    feat_names = []
    for f in READOUT_FREQS:
        feat_names.append(f"{f}_A")
        feat_names.append(f"{f}_B")

    top_idx = np.argsort(weights)[::-1][:10]
    for i, idx in enumerate(top_idx):
        print(f"    {i+1}. {feat_names[idx]:>12} weight={weights[idx]:.4f}")

    # ── Verdict ──
    print("\n" + "=" * 70)
    print("  NARMA-10 (IM PRODUCT) RESULTS")
    print("=" * 70)
    print(f"  F1 carrier:      {F1} Hz (continuous)")
    print(f"  F2 input:        {F2} Hz (pulsed)")
    print(f"  Reservoir dim:   {len(READOUT_FREQS)*2}")
    print(f"  NMSE (test):     {nmse_test:.4f}")
    print(f"  Correlation:     {corr_test:.4f}")
    print(f"  Memory capacity: {total_mc:.2f}")
    print(f"  Step rate:       {args.steps/total_time:.1f} steps/s")
    print()

    if nmse_test < 0.2:
        verdict = 'EXCELLENT'
        print(f"  ★★★ EXCELLENT — NMSE < 0.2!")
    elif nmse_test < 0.5:
        verdict = 'PASS'
        print(f"  ★★ PASS — NMSE < 0.5 (temporal memory confirmed)")
    elif nmse_test < 0.8:
        verdict = 'MARGINAL'
        print(f"  ★ MARGINAL — NMSE < 0.8 (some temporal memory)")
    else:
        verdict = 'FAIL'
        print(f"  ✗ FAIL — NMSE ≥ 0.8")

    # Compare to fundamental-only approach
    print(f"\n  Comparison to fundamental ringdown approach:")
    print(f"    Fundamental only: NMSE=1.08, MC=1.86")
    print(f"    IM products:      NMSE={nmse_test:.4f}, MC={total_mc:.2f}")
    if total_mc > 1.86:
        print(f"    → IM products provide {total_mc/1.86:.1f}× more memory capacity!")

    return {
        'drive_f1_hz': F1, 'drive_f2_hz': F2,
        'n_steps': args.steps,
        'readout_freqs': READOUT_FREQS,
        'reservoir_dim': len(READOUT_FREQS) * 2,
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
    }


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/narma10_im')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    im_char_results = None
    im_tau_results = None
    narma_results = None

    # Phase 1
    if args.phase in (0, 1):
        im_char_results, im_tau_results, im_decay_data, im_times = run_phase1()

    # Phase 2
    if args.phase in (0, 2):
        narma_results = run_phase2()

    # ── Save ──
    nco('Foff')

    results = {
        'test': 'NARMA10_IM_reservoir',
        'timestamp': datetime.now().isoformat(),
        'config': {
            'f1_hz': F1, 'f2_hz': F2,
            'im_freqs': IM_FREQS,
            'readout_freqs': READOUT_FREQS,
            'n_steps': args.steps,
            'navg': args.navg,
            'seed': args.seed,
        },
    }

    if im_char_results:
        results['im_characterization'] = im_char_results
    if im_tau_results:
        results['im_ringdown'] = im_tau_results
    if narma_results:
        narma_save = {k: v for k, v in narma_results.items()
                      if k not in ('states', 'y_target')}
        results['narma10'] = narma_save

    json_path = DATA_DIR / f'narma10_im_{ts}.json'
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n  Saved: {json_path}")

    # NPZ
    npz_data = {}
    if narma_results:
        npz_data['states'] = narma_results['states']
        npz_data['y_target'] = narma_results['y_target']
    if 'im_decay_data' in dir() and im_decay_data:
        for f in IM_FREQS:
            npz_data[f'im_decay_{f}'] = np.array(im_decay_data[f])
        npz_data['im_times'] = np.array(im_times) if len(im_times) > 0 else np.array([])

    if npz_data:
        npz_path = DATA_DIR / f'narma10_im_{ts}.npz'
        np.savez_compressed(npz_path, **npz_data)
        print(f"  Saved: {npz_path}")

    # Cleanup
    ser.close()
    ps.ps2000_stop(h)
    ps.ps2000_close_unit(ct.c_int16(h))
    print("\n  Done. Hardware released.")
