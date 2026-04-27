#!/usr/bin/env python3
"""
NARMA-10 temporal memory experiment.

Encodes NARMA-10 input u(t) as DDS frequency, captures single-frame spectral
features at each timestep, then trains a ridge regressor to predict y(t).

The NARMA-10 target:
  y(t+1) = 0.3*y(t) + 0.05*y(t)*sum(y(t-i),i=0..9) + 1.5*u(t-9)*u(t) + 0.1

If the glass plate has temporal memory, its eigenmode response at time t will
carry information about u(t-1), u(t-2), etc. — making prediction possible
without explicit delay taps in software.

Modes:
  --mode collect    : Run hardware, save raw data to .npz
  --mode evaluate   : Load saved data, train/evaluate models
  --mode simulate   : Generate synthetic data for code debugging
  --mode full       : Collect + evaluate in one run

Usage:
  python tools/narma10_temporal.py --mode simulate        # Debug without hardware
  python tools/narma10_temporal.py --mode collect          # Run experiment
  python tools/narma10_temporal.py --mode evaluate         # Analyze saved data
  python tools/narma10_temporal.py --mode full             # Both
"""
import numpy as np, time, sys, argparse, os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['collect', 'evaluate', 'simulate', 'full'],
                    default='simulate')
parser.add_argument('--drive-lo', type=int, default=25000, help='Min DDS freq (Hz)')
parser.add_argument('--drive-hi', type=int, default=35000, help='Max DDS freq (Hz)')
parser.add_argument('--n-steps', type=int, default=500, help='Number of NARMA steps')
parser.add_argument('--mux', type=int, default=5, help='Mux channel')
parser.add_argument('--data-file', type=str, default='data/results/narma10_temporal.npz',
                    help='Path for saved data')
parser.add_argument('--multi-mux', action='store_true',
                    help='Collect from multiple mux channels (slower, richer features)')
args = parser.parse_args()

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'
DATA_DIR.mkdir(parents=True, exist_ok=True)
data_path = Path(__file__).parent.parent / args.data_file


# ────────────────────────────────────────
# NARMA-10 generation
# ────────────────────────────────────────
def generate_narma10(n_steps, seed=42):
    """Generate NARMA-10 input/target sequences."""
    rng = np.random.RandomState(seed)
    u = rng.uniform(0, 0.5, n_steps + 200)  # extra warmup
    y = np.zeros(n_steps + 200)
    for t in range(10, len(y) - 1):
        y[t + 1] = (0.3 * y[t]
                     + 0.05 * y[t] * np.sum(y[t - 9:t + 1])
                     + 1.5 * u[t - 9] * u[t]
                     + 0.1)
        # Clip to prevent divergence
        y[t + 1] = np.clip(y[t + 1], 0, 10)

    # Discard warmup
    warmup = 200
    return u[warmup:warmup + n_steps], y[warmup:warmup + n_steps]


def u_to_freq(u_val, lo, hi):
    """Map NARMA input u ∈ [0, 0.5] → DDS frequency ∈ [lo, hi]."""
    return int(lo + (u_val / 0.5) * (hi - lo))


# ────────────────────────────────────────
# Hardware collection
# ────────────────────────────────────────
def collect_data(u_seq, args):
    """Drive DDS with u(t) sequence, capture spectral features at each step."""
    import ctypes, serial

    ps = ctypes.CDLL(
        "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
    ps.ps2000_set_sig_gen_built_in.argtypes = [
        ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_int32, ctypes.c_int32]

    for h in range(1, 5):
        ps.ps2000_close_unit(h)
    time.sleep(0.5)

    handle = ps.ps2000_open_unit()
    print(f"PicoScope handle: {handle}")
    if handle <= 0:
        sys.exit(1)

    ps.ps2000_set_channel(handle, 0, 1, 1, 7)
    ps.ps2000_set_channel(handle, 1, 0, 1, 7)
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
    time.sleep(2)
    mux.reset_input_buffer()

    dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
    time.sleep(2)
    dds.reset_input_buffer()

    FAST_TB = 5
    FAST_N = 1024
    FAST_DT = 320e-9
    fast_nfft = FAST_N * 4

    def capture_fast():
        buf = (ctypes.c_int16 * FAST_N)()
        ov = ctypes.c_int16(0)
        ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
        ms_val = ctypes.c_int32(0)
        ps.ps2000_run_block(handle, FAST_N, FAST_TB, 1, ctypes.byref(ms_val))
        for _ in range(5000):
            if ps.ps2000_ready(handle):
                break
            time.sleep(0.0005)
        else:
            ps.ps2000_stop(handle)
            return np.zeros(FAST_N)
        ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                             ctypes.byref(ov), FAST_N)
        return np.array(buf, dtype=np.float64)

    def extract_features(data):
        """Full magnitude spectrum as feature vector."""
        d = data - np.mean(data)
        w = d * np.hanning(len(d))
        mag = np.abs(np.fft.rfft(w, n=fast_nfft))
        return mag

    # Determine mux channels
    if args.multi_mux:
        mux_channels = [1, 2, 3, 5, 7]  # 5 receivers
    else:
        mux_channels = [args.mux]

    n_features = fast_nfft // 2 + 1
    all_features = np.zeros((len(u_seq), len(mux_channels) * n_features))
    timestamps = np.zeros(len(u_seq))
    actual_freqs = np.zeros(len(u_seq), dtype=int)

    print(f"\nCollecting {len(u_seq)} steps, {len(mux_channels)} mux channel(s)...")
    print(f"DDS freq range: {args.drive_lo}–{args.drive_hi} Hz")
    print(f"Estimated time: {len(u_seq) * len(mux_channels) * 0.003:.0f}s")

    # Set initial mux channel
    mux.write(f'{mux_channels[0]}\n'.encode())
    time.sleep(0.15)
    mux.readline()

    t0 = time.time()
    for step, u_val in enumerate(u_seq):
        freq = u_to_freq(u_val, args.drive_lo, args.drive_hi)
        actual_freqs[step] = freq

        # Fire-and-forget DDS command (no readline, 0.02 ms)
        dds.write(f'F1:{freq}\n'.encode())

        # Capture from each mux channel
        for ch_idx, ch in enumerate(mux_channels):
            if len(mux_channels) > 1:
                mux.write(f'{ch}\n'.encode())
                time.sleep(0.001)  # minimal settle
                # Don't read response in tight loop
            data = capture_fast()
            features = extract_features(data)
            offset = ch_idx * n_features
            all_features[step, offset:offset + n_features] = features

        timestamps[step] = time.time() - t0

        if (step + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (step + 1) / elapsed
            eta = (len(u_seq) - step - 1) / rate
            print(f"  Step {step+1}/{len(u_seq)}: {rate:.0f} steps/s, "
                  f"ETA {eta:.0f}s, freq={freq} Hz")

    elapsed = time.time() - t0
    print(f"\nCollection done: {len(u_seq)} steps in {elapsed:.1f}s "
          f"({len(u_seq)/elapsed:.0f} steps/s)")

    # Cleanup
    dds.write(b'Foff\n')
    time.sleep(0.01)
    dds.readline()
    mux.write(b'0\n')
    mux.close()
    dds.close()
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(handle)

    return all_features, timestamps, actual_freqs


# ────────────────────────────────────────
# Simulate data (for code debugging)
# ────────────────────────────────────────
def simulate_data(u_seq, snr=0.5, tau_frames=3):
    """
    Generate synthetic spectral features that mimic a glass plate with
    temporal memory. Each timestep's features depend on current + past inputs.

    Key physics modeled:
    - Different drive frequencies excite different eigenmode patterns
    - Each eigenmode has its own amplitude response to drive frequency
    - Past inputs persist with exponential decay (temporal memory)
    - Eigenmodes interact nonlinearly (cross-modulation)

    snr: signal-to-noise ratio (0.5 = preamp-level, 0.02 = current no-preamp)
    tau_frames: memory decay in frames (3 = signal decays to 1/e in 3 steps)
    """
    rng = np.random.RandomState(123)
    n_features = 2049  # matches fast_nfft // 2 + 1 for FAST_N=1024, nfft=4096
    n_steps = len(u_seq)

    # Create 10 "eigenmode" centers — each responds differently to drive freq
    eigenmode_centers = [150, 320, 500, 680, 900, 1100, 1350, 1600, 1800, 2000]
    n_modes = len(eigenmode_centers)

    # Each eigenmode has a preferred drive frequency (normalized u value)
    # This creates input-dependent eigenmode patterns (like real glass)
    mode_preferred_u = rng.uniform(0, 0.5, n_modes)
    mode_bandwidth = rng.uniform(0.1, 0.3, n_modes)  # how sharply tuned
    # Cross-modulation coefficients between mode pairs
    cross_mod = rng.randn(n_modes, n_modes) * 0.3

    features = np.zeros((n_steps, n_features))

    for t in range(n_steps):
        # Compute effective drive: current input + exponentially decaying past
        u_effective = np.zeros(n_modes)
        for lag in range(min(t + 1, 20)):
            decay = np.exp(-lag / tau_frames)
            past_u = u_seq[t - lag]
            # Each mode responds to past inputs with its own sensitivity
            for m in range(n_modes):
                tuning = np.exp(-0.5 * ((past_u - mode_preferred_u[m])
                                        / mode_bandwidth[m]) ** 2)
                u_effective[m] += past_u * tuning * decay

        # Nonlinear cross-modulation between modes
        mode_amplitudes = u_effective.copy()
        mode_amplitudes += 0.3 * np.tanh(cross_mod @ u_effective)

        # Build spectral features
        signal = np.zeros(n_features)
        for m, ec in enumerate(eigenmode_centers):
            width = 10
            bins = np.arange(max(0, ec - width), min(n_features, ec + width))
            peak = np.exp(-0.5 * ((bins - ec) / 3.0) ** 2)
            signal[bins] += peak * mode_amplitudes[m] * 100

        # Add noise
        signal_power = np.mean(signal ** 2) ** 0.5
        noise = rng.randn(n_features) * max(signal_power / max(snr, 0.01), 1.0)
        features[t] = signal + noise

    timestamps = np.arange(n_steps) * 0.00235  # 425 Hz
    actual_freqs = np.array([u_to_freq(u, args.drive_lo, args.drive_hi)
                             for u in u_seq])

    return features, timestamps, actual_freqs


# ────────────────────────────────────────
# Evaluation
# ────────────────────────────────────────
def evaluate(features, u_seq, y_seq, timestamps):
    """Train and evaluate multiple models on the NARMA-10 task."""
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import cross_val_score, TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.pipeline import make_pipeline

    n = len(u_seq)
    print(f"\n{'='*60}")
    print("NARMA-10 EVALUATION")
    print(f"{'='*60}")
    print(f"  Steps: {n}")
    print(f"  Features per step: {features.shape[1]}")
    print(f"  Target range: [{y_seq.min():.3f}, {y_seq.max():.3f}]")

    # Train/test split (time-series: first 60% train, last 40% test)
    split = int(n * 0.6)
    X_train, X_test = features[:split], features[split:]
    y_train, y_test = y_seq[:split], y_seq[split:]
    u_train, u_test = u_seq[:split], u_seq[split:]

    # Dimensionality reduction: PCA to 50 components
    # (2049 raw spectral bins → 50 principal components)
    n_components = min(50, split - 1, features.shape[1])
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    pca = PCA(n_components=n_components)
    pca.fit(X_scaled)
    explained = pca.explained_variance_ratio_.sum()
    print(f"  PCA: {n_components} components explain {explained*100:.1f}% variance")

    X_pca_train = pca.transform(X_scaled)
    X_pca_test = pca.transform(scaler.transform(X_test))

    results = {}

    # ── Model 1: Plate-only (PCA features → ridge) ──
    print("\n--- Model 1: Plate-only (PCA features → ridge) ---")
    # Try multiple alpha values, pick best by CV
    best_alpha, best_nmse_cv = 1.0, 1e10
    for alpha in [0.1, 1.0, 10.0, 100.0, 1000.0]:
        pipe = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = cross_val_score(pipe,
                                    pca.transform(scaler.transform(features)),
                                    y_seq, cv=tscv,
                                    scoring='neg_mean_squared_error')
        cv_nmse = -cv_scores.mean() / max(np.var(y_seq), 1e-10)
        if cv_nmse < best_nmse_cv:
            best_alpha, best_nmse_cv = alpha, cv_nmse

    pipe = make_pipeline(StandardScaler(), Ridge(alpha=best_alpha))
    pipe.fit(X_pca_train, y_train)
    y_pred = pipe.predict(X_pca_test)
    mse = np.mean((y_pred - y_test) ** 2)
    var = np.var(y_test)
    nmse = mse / max(var, 1e-10)
    results['plate_only'] = nmse
    print(f"  NMSE: {nmse:.4f} (alpha={best_alpha})")
    print(f"  CV NMSE: {best_nmse_cv:.4f}")

    # ── Model 2a: u(t)-only baseline (NO delay taps — the key comparison) ──
    print("\n--- Model 2a: u(t)-only baseline (current input only, no history) ---")
    X_u_only = u_seq.reshape(-1, 1)
    X_u_train, X_u_test = X_u_only[:split], X_u_only[split:]
    pipe_u = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    pipe_u.fit(X_u_train, y_train)
    y_pred_u = pipe_u.predict(X_u_test)
    nmse_u = np.mean((y_pred_u - y_test) ** 2) / max(var, 1e-10)
    results['u_only'] = nmse_u
    print(f"  NMSE: {nmse_u:.4f}")
    print(f"  (This is the temporal memory baseline: no history, just current u(t))")

    # ── Model 2b: Input-only with 10 delay taps (software memory ceiling) ──
    print("\n--- Model 2b: Input + 10 delay taps (software memory ceiling) ---")
    n_taps = 10
    X_input = np.zeros((n, n_taps))
    for t in range(n):
        for tap in range(n_taps):
            if t - tap >= 0:
                X_input[t, tap] = u_seq[t - tap]
    X_in_train, X_in_test = X_input[:split], X_input[split:]
    pipe_in = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    pipe_in.fit(X_in_train, y_train)
    y_pred_in = pipe_in.predict(X_in_test)
    nmse_in = np.mean((y_pred_in - y_test) ** 2) / max(var, 1e-10)
    results['input_10taps'] = nmse_in
    print(f"  NMSE: {nmse_in:.4f}")

    # ── Model 3: Plate + input delay taps ──
    print("\n--- Model 3: Plate + input delay taps ---")
    X_combined = np.hstack([X_pca_train, X_in_train])
    X_c_test = np.hstack([X_pca_test, X_in_test])
    pipe_c = make_pipeline(StandardScaler(), Ridge(alpha=best_alpha))
    pipe_c.fit(X_combined, y_train)
    y_pred_c = pipe_c.predict(X_c_test)
    nmse_c = np.mean((y_pred_c - y_test) ** 2) / max(var, 1e-10)
    results['plate_plus_input'] = nmse_c
    print(f"  NMSE: {nmse_c:.4f}")

    # ── Model 4: Plate + software ESN ──
    print("\n--- Model 4: Plate + software ESN ---")
    try:
        rng = np.random.RandomState(42)
        N_res = 200
        spectral_radius = 0.9
        # ESN input: PCA features (not raw 2049 bins)
        X_pca_full = pca.transform(scaler.transform(features))
        n_esn_in = n_components + 1  # +1 for bias
        W_in = rng.randn(N_res, n_esn_in) * (0.1 / np.sqrt(n_esn_in))
        W_res = rng.randn(N_res, N_res)
        eigs = np.abs(np.linalg.eigvals(W_res))
        W_res *= spectral_radius / max(eigs)

        states = np.zeros((n, N_res))
        x = np.zeros(N_res)
        for t in range(n):
            inp = np.concatenate([[1.0], X_pca_full[t]])
            x = np.tanh(W_in @ inp + W_res @ x)
            states[t] = x

        X_esn = np.hstack([X_pca_full, states])
        X_e_train, X_e_test = X_esn[:split], X_esn[split:]
        pipe_e = make_pipeline(StandardScaler(), Ridge(alpha=100.0))
        pipe_e.fit(X_e_train, y_train)
        y_pred_e = pipe_e.predict(X_e_test)
        nmse_e = np.mean((y_pred_e - y_test) ** 2) / max(var, 1e-10)
        results['plate_plus_esn'] = nmse_e
        print(f"  NMSE: {nmse_e:.4f}")
    except Exception as e:
        print(f"  ESN failed: {e}")

    # ── Model 5: Pure software ESN baseline (input only, no plate) ──
    print("\n--- Model 5: Pure ESN baseline (u(t) only, no plate) ---")
    try:
        W_in_pure = rng.randn(N_res, 2) * 0.1  # bias + u(t)
        states_pure = np.zeros((n, N_res))
        x = np.zeros(N_res)
        for t in range(n):
            inp = np.array([1.0, u_seq[t]])
            x = np.tanh(W_in_pure @ inp + W_res @ x)
            states_pure[t] = x

        X_ep_train, X_ep_test = states_pure[:split], states_pure[split:]
        pipe_ep = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
        pipe_ep.fit(X_ep_train, y_train)
        y_pred_ep = pipe_ep.predict(X_ep_test)
        nmse_ep = np.mean((y_pred_ep - y_test) ** 2) / max(var, 1e-10)
        results['esn_only'] = nmse_ep
        print(f"  NMSE: {nmse_ep:.4f}")
    except Exception as e:
        print(f"  ESN failed: {e}")

    # ── Summary ──
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Model':<30} {'NMSE':>10} {'vs ESN':>10}")
    print(f"  {'-'*52}")
    esn_nmse = results.get('esn_only', 0.197)
    for name, nmse_val in sorted(results.items(), key=lambda x: x[1]):
        vs = f"{(nmse_val/esn_nmse - 1)*100:+.1f}%" if esn_nmse > 0 else "—"
        print(f"  {name:<30} {nmse_val:>10.4f} {vs:>10}")

    print(f"\n  Reference: April 19 plate+ESN = 0.171, ESN-only = 0.197")

    # Temporal memory diagnostic
    print(f"\n{'='*60}")
    print("TEMPORAL MEMORY DIAGNOSTIC")
    print(f"{'='*60}")
    plate_nmse = results.get('plate_only', 999)
    u_only_nmse = results.get('u_only', 999)
    taps_nmse = results.get('input_10taps', 999)
    plate_esn_nmse = results.get('plate_plus_esn', 999)
    esn_nmse_val = results.get('esn_only', 0.197)

    print(f"\n  KEY COMPARISON: plate-only vs u(t)-only")
    print(f"  u(t)-only (no history):    {u_only_nmse:.4f}")
    print(f"  Plate-only (with physics): {plate_nmse:.4f}")
    print(f"  10-tap software memory:    {taps_nmse:.4f}")

    if plate_nmse < u_only_nmse * 0.95:  # 5% margin to avoid noise
        improvement = (1 - plate_nmse / u_only_nmse) * 100
        print(f"\n  ✓ TEMPORAL MEMORY DETECTED")
        print(f"    Plate beats u(t)-only by {improvement:.1f}%")
        print(f"    → The plate encodes history from past inputs!")
        if plate_nmse < taps_nmse:
            print(f"    → Plate even beats 10-tap software memory!")
    elif plate_nmse < u_only_nmse:
        print(f"\n  ~ MARGINAL — plate slightly better than u(t)-only")
        print(f"    ({(1 - plate_nmse/u_only_nmse)*100:.1f}% improvement, need >5%)")
    elif plate_nmse < 1.0:
        print(f"\n  ✗ Plate does NOT beat u(t)-only")
        print(f"    But has some prediction ability ({plate_nmse:.4f} < 1.0)")
        print(f"    → May need more SNR or more data")
    else:
        print(f"\n  ✗ Plate at chance level ({plate_nmse:.4f} ≥ 1.0)")
        print(f"    → No temporal information detected")

    if plate_esn_nmse < esn_nmse_val * 0.95:
        print(f"\n  ✓ PLATE ENHANCES ESN")
        print(f"    plate+ESN ({plate_esn_nmse:.4f}) vs ESN-only ({esn_nmse_val:.4f})")
        print(f"    → {(1 - plate_esn_nmse/esn_nmse_val)*100:.1f}% improvement")

    return results


# ────────────────────────────────────────
# Main
# ────────────────────────────────────────
if __name__ == '__main__':
    print(f"NARMA-10 Temporal Memory Experiment")
    print(f"Mode: {args.mode}")

    # Generate NARMA-10 sequence
    u_seq, y_seq = generate_narma10(args.n_steps)
    print(f"NARMA-10: {args.n_steps} steps, u∈[{u_seq.min():.3f},{u_seq.max():.3f}], "
          f"y∈[{y_seq.min():.3f},{y_seq.max():.3f}]")

    if args.mode == 'simulate':
        # High SNR first to validate pipeline works
        print("\n--- HIGH SNR simulation (ideal preamp, SNR=5.0) ---")
        features_hi, timestamps, actual_freqs = simulate_data(u_seq, snr=5.0, tau_frames=3)
        print(f"Simulated features: {features_hi.shape}")
        results_hi = evaluate(features_hi, u_seq, y_seq, timestamps)

        # Realistic preamp SNR
        print(f"\n\n{'#'*60}")
        print("REALISTIC PREAMP SNR (SNR=0.5, τ=3 frames)")
        print(f"{'#'*60}")
        features_med, _, _ = simulate_data(u_seq, snr=0.5, tau_frames=3)
        results_med = evaluate(features_med, u_seq, y_seq, timestamps)

        # No-preamp SNR
        print(f"\n\n{'#'*60}")
        print("NO-PREAMP SNR (current hardware, SNR=0.02)")
        print(f"{'#'*60}")
        features_lo, _, _ = simulate_data(u_seq, snr=0.02, tau_frames=3)
        results_lo = evaluate(features_lo, u_seq, y_seq, timestamps)

    elif args.mode in ('collect', 'full'):
        features, timestamps, actual_freqs = collect_data(u_seq, args)

        # Save
        np.savez(data_path,
                 features=features, timestamps=timestamps,
                 actual_freqs=actual_freqs,
                 u_seq=u_seq, y_seq=y_seq,
                 drive_lo=args.drive_lo, drive_hi=args.drive_hi,
                 mux=args.mux, n_steps=args.n_steps)
        print(f"\nData saved to {data_path}")

        if args.mode == 'full':
            results = evaluate(features, u_seq, y_seq, timestamps)

    elif args.mode == 'evaluate':
        if not data_path.exists():
            print(f"ERROR: No data file at {data_path}")
            print("Run with --mode collect first")
            sys.exit(1)
        data = np.load(data_path)
        features = data['features']
        u_seq = data['u_seq']
        y_seq = data['y_seq']
        timestamps = data['timestamps']
        print(f"Loaded {features.shape[0]} steps, {features.shape[1]} features")
        results = evaluate(features, u_seq, y_seq, timestamps)

    print("\nDone.")
