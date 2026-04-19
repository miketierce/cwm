#!/usr/bin/env python3
"""
NARMA-10 Temporal Reservoir — Exploiting Q-Factor Memory

Unlike the harmonic ladder (spatial encoding at 0.82 Hz → zero memory),
this script drives the plate at ≥100 Hz step rate so that mode ringdowns
persist between steps, creating genuine temporal memory.

The plate becomes a physical reservoir with heterogeneous time constants
set by the Q factors of different modes:
  - 29.9 kHz: Q=218, τ=1.99ms → 19% retention at 300 Hz
  - 19.0 kHz: Q=156, τ=2.07ms → 20% retention at 300 Hz
  - 68.2 kHz: Q=296, τ=1.49ms →  7% retention at 300 Hz

Drive modes:
  --carrier 29900       Single carrier (built-in sine, fastest)
  --carrier multi3      Three high-Q carriers (ARB, ~same speed)
  --carrier multi10     All 10 ladder carriers (ARB, same as ladder but fast)

Feature extraction (all computed offline from stored waveforms):
  - demod:     I/Q demodulation at carrier frequency(s)
  - subsample: raw waveform subsampled (virtual nodes)
  - fft:       short FFT magnitudes at key frequencies

Usage:
  DYLD_LIBRARY_PATH="..." python tools/narma_temporal.py \\
      --port /dev/cu.usbserial-11310 --plate 4_NE --steps 3000
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

ROOT = TOOLS_DIR.parent
RESULTS_DIR = ROOT / "data" / "results" / "lab" / "plate_exps" / "narma10"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────

NARMA_ORDER = 10
N_WASHOUT = 50

# PicoScope capture
TIMEBASE = 7                    # 1280 ns/sample = 781.25 kHz
SAMPLE_RATE = 781_250
DT_NS = 1280

# Capture sizes (samples per step)
N_SAMPLES_FAST = 256            # 0.328 ms → target ≥250 Hz
N_SAMPLES_MED = 512             # 0.655 ms → target ≥150 Hz
N_SAMPLES_SLOW = 1024           # 1.310 ms → target ≥100 Hz

AWG_DRIVE_UVPP = 2_000_000     # 2 Vpp max
ARB_LEN = 4096

SETTLE_RELAY_S = 0.10

# Ridge regression
RIDGE_ALPHAS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]

# High-Q carriers (from Q-factor measurement 2026-04-18)
HIGH_Q_MODES = {
    19_000: {"Q": 156, "tau_ms": 2.07},
    23_900: {"Q": 168, "tau_ms": 1.85},
    29_900: {"Q": 218, "tau_ms": 1.99},
    47_800: {"Q": 120, "tau_ms": 0.80},
    68_200: {"Q": 296, "tau_ms": 1.49},
}

MULTI3_CARRIERS = [19_000, 29_900, 68_200]   # 3 highest-τ modes
MULTI10_CARRIERS = [                          # same as ladder
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]

# Plate receivers
RECEIVER_MAP = {
    "1":    (1, "A-NE"),
    "2":    (2, "B-NE"),
    "3_NE": (3, "G-NE"),
    "4_NE": (5, "D-NE"),
    "5_NE": (7, "H-NE"),
}

# ── Logging ───────────────────────────────────────────────────────────

_log_lines: list[str] = []

def log(msg: str = "", also_print: bool = True) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    _log_lines.append(f"[{ts}] {msg}")
    if also_print:
        print(msg, flush=True)


# ═══════════════════════════════════════════════════════════════════════
#  NARMA-10 generation
# ═══════════════════════════════════════════════════════════════════════

def generate_narma10(n_steps: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    total = n_steps + NARMA_ORDER + N_WASHOUT
    u = rng.uniform(0, 0.5, total)
    y = np.zeros(total)
    for t in range(NARMA_ORDER, total - 1):
        y_sum = np.sum(y[t - NARMA_ORDER:t + 1])
        y[t + 1] = (0.3 * y[t]
                     + 0.05 * y[t] * y_sum
                     + 1.5 * u[t - 9] * u[t]
                     + 0.1)
        y[t + 1] = np.clip(y[t + 1], 0, 1e6)
    return u, y


# ═══════════════════════════════════════════════════════════════════════
#  PicoScope helpers
# ═══════════════════════════════════════════════════════════════════════

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed ({handle})")
    # Channel A: ±1V DC coupled
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    return handle


def _close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)


def _set_sine(handle, freq_hz, pk_to_pk_uvpp):
    """Set built-in sine generator. Fastest way to change amplitude."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, int(pk_to_pk_uvpp), 0,
        float(freq_hz), float(freq_hz),
        0.0, 0.0, 0, 0)


def _set_arb(handle, arb_buf, delta_phase):
    """Load pre-computed ARB buffer. For multi-tone drive."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase,
        0, 0, arb_buf, ARB_LEN, 0, 0)


def _capture_raw(handle, n_samples):
    """Single fast capture, return raw int16 array. No FFT."""
    from picosdk.ps2000 import ps2000

    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, n_samples, TIMEBASE, 1, ctypes.byref(t_ms))

    # Busy-wait for ready (avoid time.sleep granularity)
    while ps2000.ps2000_ready(handle) == 0:
        pass

    buf_a = (ctypes.c_int16 * n_samples)()
    buf_b = (ctypes.c_int16 * n_samples)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), n_samples)

    if n <= 0:
        return np.zeros(n_samples, dtype=np.int16)
    return np.array(buf_a[:n], dtype=np.int16)


# ═══════════════════════════════════════════════════════════════════════
#  ARB pre-computation (for multi-tone modes)
# ═══════════════════════════════════════════════════════════════════════

def precompute_arb_buffers(carriers, amplitude_sequence, f_rep):
    """Pre-compute all ARB ctypes buffers for the entire input sequence.

    amplitude_sequence: (n_steps, n_carriers) array of amplitudes [0, 1]
    Returns: list of (ctypes.c_uint8 * ARB_LEN) buffers
    """
    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    n_steps = len(amplitude_sequence)

    # Pre-compute carrier waveforms (fixed sinusoids)
    carrier_waves = []
    for f in carriers:
        k = round(f / f_rep)
        if k < 1 or k > ARB_LEN // 2:
            raise ValueError(f"Carrier {f} Hz: k={k} out of range for f_rep={f_rep}")
        phase = 2 * np.pi * k * np.arange(ARB_LEN) / ARB_LEN
        carrier_waves.append(np.sin(phase))  # shape (ARB_LEN,)

    carrier_waves = np.array(carrier_waves)  # (n_carriers, ARB_LEN)

    log(f"  Pre-computing {n_steps} ARB buffers...")
    t0 = time.time()

    buffers = []
    for i in range(n_steps):
        amps = amplitude_sequence[i]  # (n_carriers,)
        buf = np.dot(amps, carrier_waves)  # (ARB_LEN,)

        peak = np.max(np.abs(buf))
        if peak > 0:
            buf /= peak

        arb_u8 = ((buf * 127) + 128).clip(0, 255).astype(np.uint8)
        arb_ctypes = (ctypes.c_uint8 * ARB_LEN)(*arb_u8.tolist())
        buffers.append(arb_ctypes)

    log(f"  ARB pre-computation: {time.time() - t0:.1f}s")
    return buffers, delta_phase


# ═══════════════════════════════════════════════════════════════════════
#  Feature extraction (offline, from stored waveforms)
# ═══════════════════════════════════════════════════════════════════════

def extract_demod(waveforms, carriers, sample_rate):
    """I/Q demodulation at each carrier frequency.

    Returns (n_steps, 2*n_carriers) array: [I₁, Q₁, I₂, Q₂, ...]
    The magnitude sqrt(I²+Q²) encodes drive strength + ringdown.
    The phase atan2(Q,I) encodes temporal state (ringdown vs new drive).
    """
    n_steps, n_samples = waveforms.shape
    n_carriers = len(carriers)
    features = np.zeros((n_steps, 2 * n_carriers))

    t = np.arange(n_samples) / sample_rate
    for ci, freq in enumerate(carriers):
        cos_ref = np.cos(2 * np.pi * freq * t)
        sin_ref = np.sin(2 * np.pi * freq * t)
        # Coherent demodulation: correlate with reference
        features[:, 2*ci]     = waveforms @ cos_ref / n_samples  # I
        features[:, 2*ci + 1] = waveforms @ sin_ref / n_samples  # Q

    return features


def extract_subsample(waveforms, stride=4):
    """Subsample raw waveform → virtual node features."""
    return waveforms[:, ::stride].astype(np.float64)


def extract_fft_bands(waveforms, sample_rate, n_bands=20):
    """Divide spectrum into n_bands equal bands, compute energy in each."""
    n_steps, n_samples = waveforms.shape
    nfft = n_samples * 2  # moderate zero-pad
    features = np.zeros((n_steps, n_bands))

    for i in range(n_steps):
        raw = waveforms[i].astype(np.float64)
        windowed = raw * np.hanning(n_samples)
        fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
        # Split into bands
        band_size = len(fft_mag) // n_bands
        for b in range(n_bands):
            lo = b * band_size
            hi = (b + 1) * band_size if b < n_bands - 1 else len(fft_mag)
            features[i, b] = np.mean(fft_mag[lo:hi])

    return features


def extract_envelope(waveforms, carriers, sample_rate):
    """Extract amplitude envelope at each carrier frequency.

    Uses analytic signal (Hilbert transform) bandpass-filtered
    around each carrier. Returns (n_steps, n_carriers).
    """
    from scipy.signal import hilbert

    n_steps, n_samples = waveforms.shape
    features = np.zeros((n_steps, len(carriers)))

    for i in range(n_steps):
        raw = waveforms[i].astype(np.float64)
        analytic = hilbert(raw)
        envelope = np.abs(analytic)
        features[i, 0] = np.mean(envelope)
        # For multiple carriers, the mean envelope is a coarse feature
        # Fine-grained: demod is better

    # For single carrier, envelope mean is sufficient
    # For multi-carrier, use demod instead
    if len(carriers) > 1:
        return extract_demod(waveforms, carriers, sample_rate)

    return features


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation
# ═══════════════════════════════════════════════════════════════════════

def evaluate_ridge(X_train, y_train, X_test, y_test, alphas=None):
    """Ridge regression with CV alpha selection. Returns dict with metrics."""
    if alphas is None:
        alphas = RIDGE_ALPHAS

    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_train)
    X_te = scaler.transform(X_test)

    y_var = np.var(y_test)
    if y_var < 1e-15:
        return {"train_nmse": 1.0, "test_nmse": 1.0, "alpha": 0, "features": X_train.shape[1]}

    best_alpha = alphas[0]
    best_cv = float("inf")
    n = len(X_tr)
    k = 5
    fold_size = n // k

    for alpha in alphas:
        cv_scores = []
        for f in range(k):
            val_start = f * fold_size
            val_end = val_start + fold_size
            X_cv_train = np.vstack([X_tr[:val_start], X_tr[val_end:]])
            y_cv_train = np.concatenate([y_train[:val_start], y_train[val_end:]])
            X_cv_val = X_tr[val_start:val_end]
            y_cv_val = y_train[val_start:val_end]

            model = Ridge(alpha=alpha, fit_intercept=True)
            model.fit(X_cv_train, y_cv_train)
            pred = model.predict(X_cv_val)
            nmse = np.mean((pred - y_cv_val) ** 2) / np.var(y_cv_val)
            cv_scores.append(nmse)
        mean_cv = np.mean(cv_scores)
        if mean_cv < best_cv:
            best_cv = mean_cv
            best_alpha = alpha

    # Final model with best alpha
    model = Ridge(alpha=best_alpha, fit_intercept=True)
    model.fit(X_tr, y_train)

    pred_train = model.predict(X_tr)
    pred_test = model.predict(X_te)

    nmse_train = np.mean((pred_train - y_train) ** 2) / np.var(y_train)
    nmse_test = np.mean((pred_test - y_test) ** 2) / np.var(y_test)

    return {
        "train_nmse": round(float(nmse_train), 6),
        "test_nmse": round(float(nmse_test), 6),
        "alpha": best_alpha,
        "features": int(X_train.shape[1]),
    }


def software_esn_baseline(u, y, start, n_train, total_usable, n_reservoir=64, seed=42):
    """Software echo state network baseline for comparison."""
    rng = np.random.default_rng(seed)
    W_in = rng.uniform(-1, 1, (n_reservoir, 1))
    W = rng.standard_normal((n_reservoir, n_reservoir)) * 0.1
    # Spectral radius 0.9
    eigvals = np.max(np.abs(np.linalg.eigvals(W)))
    if eigvals > 0:
        W = W * 0.9 / eigvals

    states = np.zeros((total_usable, n_reservoir))
    x = np.zeros(n_reservoir)
    for i in range(total_usable):
        t = start + i
        x = np.tanh(W_in.flatten() * u[t] + W @ x)
        states[i] = x

    X_train = states[:n_train]
    X_test = states[n_train:]
    y_train = y[start:start + n_train]
    y_test = y[start + n_train:start + total_usable]

    return evaluate_ridge(X_train, y_train, X_test, y_test)


# ═══════════════════════════════════════════════════════════════════════
#  Main capture + evaluation
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 Temporal Reservoir (Q-factor memory)")
    parser.add_argument("--port", type=str, default="/dev/cu.usbserial-11310",
                        help="Arduino serial port for relay MUX")
    parser.add_argument("--plate", type=str, default="4_NE",
                        help="Plate receiver key (default: 4_NE = D-NE)")
    parser.add_argument("--steps", type=int, default=3000,
                        help="Number of NARMA-10 steps")
    parser.add_argument("--carrier", type=str, default="29900",
                        help="Carrier mode: frequency in Hz, 'multi3', or 'multi10'")
    parser.add_argument("--samples", type=int, default=256,
                        help="Samples per capture (256/512/1024)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--simulate", action="store_true",
                        help="Simulate plate response (no hardware)")
    args = parser.parse_args()

    n_samples = args.samples
    n_steps = args.steps

    # Parse carrier mode
    if args.carrier == "multi3":
        carriers = MULTI3_CARRIERS
        mode_name = "multi3"
    elif args.carrier == "multi10":
        carriers = MULTI10_CARRIERS
        mode_name = "multi10"
    else:
        carriers = [int(args.carrier)]
        mode_name = f"single_{args.carrier}"

    print("=" * 62)
    print("  NARMA-10 TEMPORAL RESERVOIR — Q-Factor Memory")
    print("=" * 62)
    print()
    print(f"  Carriers: {[f/1000 for f in carriers]}k Hz")
    print(f"  Capture: {n_samples} samples = {n_samples * DT_NS / 1e6:.3f} ms")
    print(f"  Steps: {n_steps}")

    # Expected temporal retention
    print(f"\n  Expected temporal retention (per-step):")
    for freq in carriers:
        if freq in HIGH_Q_MODES:
            info = HIGH_Q_MODES[freq]
            # Estimate: assume ~4ms/step for now
            for step_rate in [100, 200, 300, 500]:
                dt = 1000 / step_rate  # ms
                retention = math.exp(-dt / info["tau_ms"])
                if step_rate == 300:
                    print(f"    {freq/1000:.1f}k: Q={info['Q']}, "
                          f"τ={info['tau_ms']:.2f}ms → "
                          f"{retention*100:.1f}% @ {step_rate} Hz")

    # ── Generate NARMA-10 ────────────────────────────────────────────
    total = n_steps + NARMA_ORDER + N_WASHOUT
    u, y = generate_narma10(n_steps, seed=args.seed)
    start = NARMA_ORDER + N_WASHOUT
    total_usable = n_steps
    n_train = int(total_usable * 0.67)
    n_test = total_usable - n_train

    print(f"\n  NARMA-10: {total_usable} usable ({n_train} train / {n_test} test)")

    # ── Pre-compute drive parameters ─────────────────────────────────
    use_arb = len(carriers) > 1

    if use_arb:
        # Multi-tone: pre-compute all ARB buffers
        max_freq = max(carriers)
        f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))
        print(f"  f_rep = {f_rep:.1f} Hz")

        # Build amplitude matrix: (n_usable, n_carriers)
        amp_matrix = np.zeros((total_usable, len(carriers)))
        for i in range(total_usable):
            t = start + i
            if t >= NARMA_ORDER:
                window = u[t - 9:t + 1]
                # For multi3: assign first 3 input lags to carriers
                # For multi10: same mapping as ladder
                if len(carriers) == 3:
                    # u(t-9) → carrier 0 (19k), u(t) → carrier 1 (29.9k),
                    # u(t-5) → carrier 2 (68.2k)
                    amp_matrix[i, 0] = window[0] * 2  # u(t-9)
                    amp_matrix[i, 1] = window[9] * 2  # u(t)
                    amp_matrix[i, 2] = window[4] * 2  # u(t-5)
                else:
                    amp_matrix[i] = window * 2  # [0,1] range

        arb_buffers, delta_phase = precompute_arb_buffers(
            carriers, amp_matrix, f_rep)
    else:
        # Single carrier: just need pk_to_pk values
        pk_to_pk_values = np.zeros(total_usable, dtype=np.int32)
        for i in range(total_usable):
            t = start + i
            # Drive amplitude proportional to u(t)
            amp = u[t] * 2.0  # scale [0, 0.5] → [0, 1]
            pk_to_pk_values[i] = int(amp * AWG_DRIVE_UVPP)

    # ── Hardware capture ─────────────────────────────────────────────
    if args.simulate:
        print("\n  [SIMULATION MODE — generating synthetic waveforms]")
        waveforms = _simulate_temporal(
            carriers, u, start, total_usable, n_samples)
    else:
        from relay_mux import RelayMux

        handle = _open_scope()
        log("  PicoScope opened (Ch A ±1V DC)")

        mux = RelayMux(args.port)
        mux.open()
        time.sleep(0.5)

        # Select plate
        relay_ch, rx_name = RECEIVER_MAP[args.plate]
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)
        log(f"  Relay {relay_ch} ({rx_name}) selected")

        from picosdk.ps2000 import ps2000

        # Set trigger once: auto-trigger with minimal delay
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 1)  # 1ms auto

        # Pre-allocate waveform storage
        waveforms = np.zeros((total_usable, n_samples), dtype=np.int16)

        # If single carrier, start driving at the carrier frequency first
        if not use_arb:
            _set_sine(handle, carriers[0], AWG_DRIVE_UVPP // 2)
            time.sleep(0.05)  # brief settle for initial drive

        print(f"\n{'━' * 42}")
        print(f"  FAST CAPTURE LOOP")
        print(f"{'━' * 42}")

        t0_capture = time.time()
        step_times = []

        for i in range(total_usable):
            t_step_start = time.time()

            if use_arb:
                _set_arb(handle, arb_buffers[i], delta_phase)
            else:
                _set_sine(handle, carriers[0], pk_to_pk_values[i])

            waveforms[i] = _capture_raw(handle, n_samples)

            step_times.append(time.time() - t_step_start)

            if (i + 1) % 100 == 0:
                elapsed = time.time() - t0_capture
                rate = (i + 1) / elapsed
                eta = (total_usable - i - 1) / rate
                mean_step_ms = np.mean(step_times[-100:]) * 1000
                print(f"    {i+1}/{total_usable} "
                      f"({rate:.1f}/s, {mean_step_ms:.1f}ms/step, "
                      f"ETA {eta:.0f}s)")

        capture_time = time.time() - t0_capture
        achieved_rate = total_usable / capture_time
        mean_step_ms = np.mean(step_times) * 1000

        print(f"\n  Capture complete: {total_usable} steps in {capture_time:.1f}s")
        print(f"  Step rate: {achieved_rate:.1f} Hz "
              f"({mean_step_ms:.2f} ms/step)")

        # Report temporal retention at achieved rate
        step_interval_ms = mean_step_ms
        print(f"\n  Temporal retention at {achieved_rate:.0f} Hz:")
        for freq in carriers:
            if freq in HIGH_Q_MODES:
                tau = HIGH_Q_MODES[freq]["tau_ms"]
                ret = math.exp(-step_interval_ms / tau)
                print(f"    {freq/1000:.1f}k (τ={tau:.2f}ms): "
                      f"{ret*100:.1f}% per step, "
                      f"{ret**2*100:.2f}% @ 2 steps")

        # Kill AWG and close
        _close_scope(handle)
        mux.close()
        log("  PicoScope closed")

    # ── Feature extraction ───────────────────────────────────────────
    print(f"\n{'━' * 42}")
    print(f"  FEATURE EXTRACTION & EVALUATION")
    print(f"{'━' * 42}")

    waveforms_f = waveforms.astype(np.float64)
    y_usable = y[start:start + total_usable]

    results = []

    def eval_approach(name, X):
        """Train/test and print result."""
        X_tr, X_te = X[:n_train], X[n_train:]
        y_tr, y_te = y_usable[:n_train], y_usable[n_train:]
        r = evaluate_ridge(X_tr, y_tr, X_te, y_te)
        r["name"] = name
        results.append(r)
        print(f"  {name:<40s} {r['train_nmse']:>8.4f} {r['test_nmse']:>8.4f} "
              f"{r['features']:>5d}")
        return r

    print(f"\n  {'Approach':<40s} {'Train':>8s} {'Test':>8s} {'Feats':>5s}")
    print(f"  {'─' * 40} {'─' * 8:>8s} {'─' * 8:>8s} {'─' * 5:>5s}")

    # 1. Input window only (baseline)
    X_input = np.zeros((total_usable, NARMA_ORDER))
    for i in range(total_usable):
        t = start + i
        if t >= NARMA_ORDER:
            X_input[i] = u[t - 9:t + 1]
    eval_approach("input_window_only", X_input)

    # 2. Demod features (I/Q at carrier frequencies)
    X_demod = extract_demod(waveforms_f, carriers, SAMPLE_RATE)
    eval_approach("temporal_demod", X_demod)

    # 3. Demod + input window
    X_demod_input = np.hstack([X_demod, X_input])
    eval_approach("temporal_demod+input", X_demod_input)

    # 4. Subsample features (virtual nodes)
    for stride in [4, 8, 16]:
        n_feats = n_samples // stride
        X_sub = extract_subsample(waveforms_f, stride=stride)
        eval_approach(f"temporal_subsample_s{stride} ({n_feats})", X_sub)

    # 5. Subsample + input window
    X_sub8 = extract_subsample(waveforms_f, stride=8)
    X_sub_input = np.hstack([X_sub8, X_input])
    eval_approach("temporal_subsample_s8+input", X_sub_input)

    # 6. FFT bands
    X_fft = extract_fft_bands(waveforms_f, SAMPLE_RATE, n_bands=20)
    eval_approach("temporal_fft_bands_20", X_fft)

    # 7. FFT bands + input
    X_fft_input = np.hstack([X_fft, X_input])
    eval_approach("temporal_fft_bands+input", X_fft_input)

    # 8. Software ESN baseline
    print(f"\n  Running software ESN baseline...")
    esn_result = software_esn_baseline(u, y, start, n_train, total_usable)
    esn_result["name"] = "software_esn"
    results.append(esn_result)
    print(f"  {'software_esn':<40s} {esn_result['train_nmse']:>8.4f} "
          f"{esn_result['test_nmse']:>8.4f} {esn_result['features']:>5d}")

    # 9. Temporal shuffle test: if plate has temporal memory,
    #    shuffling the step order should INCREASE NMSE
    print(f"\n  Temporal memory verification (shuffle test)...")
    rng_shuf = np.random.default_rng(123)
    perm = rng_shuf.permutation(total_usable)
    X_demod_shuf = X_demod[perm]
    # Also shuffle y to match
    y_shuf = y_usable[perm]
    # But we evaluate on unshuffled test set — this should give ~1.0 NMSE
    # Better test: shuffle waveforms, keep targets aligned → should degrade
    X_demod_temporal_shuffled = X_demod[perm]
    X_shuf_combined = np.hstack([X_demod_temporal_shuffled, X_input])
    r_shuf = eval_approach("temporal_demod_SHUFFLED+input", X_shuf_combined)

    # 10. Mean baseline
    mean_pred = np.mean(y_usable[:n_train])
    nmse_mean = np.mean((mean_pred - y_usable[n_train:]) ** 2) / np.var(y_usable[n_train:])
    results.append({
        "name": "mean_baseline",
        "train_nmse": 1.0,
        "test_nmse": round(float(nmse_mean), 6),
        "features": 0,
    })
    print(f"  {'mean_baseline':<40s} {'1.0000':>8s} {nmse_mean:>8.4f} {'0':>5s}")

    # ── Summary ──────────────────────────────────────────────────────
    results_sorted = sorted(results, key=lambda r: r["test_nmse"])
    best = results_sorted[0]

    # Find the shuffle vs unshuffled comparison
    demod_input_result = next(
        (r for r in results if r["name"] == "temporal_demod+input"), None)
    shuf_result = next(
        (r for r in results if r["name"] == "temporal_demod_SHUFFLED+input"), None)

    print(f"\n  ★ BEST: {best['name']} — NMSE {best['test_nmse']:.4f}")

    if demod_input_result and shuf_result:
        delta = shuf_result["test_nmse"] - demod_input_result["test_nmse"]
        if delta > 0.01:
            print(f"  ✓ TEMPORAL MEMORY DETECTED: shuffling degrades by "
                  f"{delta:.4f} NMSE ({delta/demod_input_result['test_nmse']*100:.1f}%)")
        else:
            print(f"  ✗ No temporal memory signal: shuffle delta = {delta:.4f}")

    # ── Save results ─────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "narma10_temporal",
        "mode": "simulation" if args.simulate else "hardware",
        "n_steps": n_steps,
        "n_train": n_train,
        "n_test": n_test,
        "seed": args.seed,
        "carriers_hz": carriers,
        "carrier_mode": mode_name,
        "n_samples_per_step": n_samples,
        "sample_rate": SAMPLE_RATE,
    }

    if not args.simulate:
        out["step_rate_hz"] = round(achieved_rate, 1)
        out["mean_step_ms"] = round(mean_step_ms, 2)
        out["retention_pct"] = {}
        for freq in carriers:
            if freq in HIGH_Q_MODES:
                tau = HIGH_Q_MODES[freq]["tau_ms"]
                out["retention_pct"][str(freq)] = round(
                    math.exp(-mean_step_ms / tau) * 100, 1)

    out["results"] = results_sorted

    out_path = RESULTS_DIR / f"narma10_temporal_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n  Saved: {out_path.name}")
    print()

    # Also save raw waveforms for future re-analysis
    waveform_path = RESULTS_DIR / f"narma10_temporal_waveforms_{ts}.npz"
    np.savez_compressed(waveform_path,
                        waveforms=waveforms,
                        u=u, y=y,
                        carriers=np.array(carriers),
                        start=start,
                        n_train=n_train)
    print(f"  Waveforms saved: {waveform_path.name} "
          f"({waveform_path.stat().st_size / 1024:.0f} KB)")

    print("\n" + "=" * 62)


def _simulate_temporal(carriers, u, start, total_usable, n_samples):
    """Generate synthetic waveforms with temporal memory for testing."""
    rng = np.random.default_rng(99)
    waveforms = np.zeros((total_usable, n_samples), dtype=np.int16)
    t_axis = np.arange(n_samples) / SAMPLE_RATE

    # Simulated mode state (carries over between steps)
    mode_states = {f: 0.0 for f in carriers}
    decay_rates = {}
    for f in carriers:
        if f in HIGH_Q_MODES:
            tau_s = HIGH_Q_MODES[f]["tau_ms"] / 1000
        else:
            tau_s = 0.001
        decay_rates[f] = math.exp(-1.0 / (SAMPLE_RATE * tau_s))
        # Per-sample decay within one capture window
        # But between steps, decay by exp(-T_step / tau)
        # Simulate ~3ms step interval
        decay_rates[f] = math.exp(-0.003 / tau_s)

    for i in range(total_usable):
        t = start + i
        amp = u[t] * 2.0
        sig = np.zeros(n_samples)
        for f in carriers:
            # New drive + ringdown from previous
            beta = decay_rates[f]
            mode_states[f] = amp + beta * mode_states[f]
            # Generate waveform at this frequency
            sig += mode_states[f] * np.sin(2 * np.pi * f * t_axis)

        # Add noise
        sig += rng.normal(0, 0.05, n_samples)
        # Scale to int16 range
        sig = (sig / (max(np.max(np.abs(sig)), 1e-10)) * 16000)
        waveforms[i] = sig.clip(-32768, 32767).astype(np.int16)

    return waveforms


if __name__ == "__main__":
    main()
