#!/usr/bin/env python3
"""
T3.3b — NARMA-10 Reservoir Computing via Re-Excitation Interference

Uses the T2.1 re-excitation interference mechanism as a nonlinear
computational element. By driving slightly off-resonance, phase
accumulates between time steps, making the captured amplitude a
nonlinear function of input history — exactly what NARMA-10 requires.

Physics:
  At exact resonance, the plate mode is a linear filter (first-order IIR).
  Slightly off-resonance (Δf ≠ 0), phase rotates by Δφ = 2π×Δf×T_step
  between steps. The captured amplitude becomes:

    x(t) = |u(t)×G + Σ_k residual_k × α^k × e^{j·k·Δφ}|

  The absolute value (envelope detection at the FFT peak) introduces
  the multiplicative nonlinearity: terms like u(t)×u(t-k)×cos(k·Δφ)
  appear in |x|², providing the cross-products NARMA-10 needs.

  T2.1 demonstrated 13.2% contrast from this interference mechanism.
  T3.2 showed phase is stable (σ < 0.28 rad) with AC-coupled trigger.

NARMA-10 equation:
  y(t+1) = 0.3·y(t) + 0.05·y(t)·Σ_{i=0}^{9} y(t-i) + 1.5·u(t-9)·u(t) + 0.1

Success Metric:
  NRMSE < 0.4 (acceptable), < 0.2 (good), state-of-art ~ 0.1-0.3

Hardware:
  - PicoScope AWG → Board D (×3.69) → TX PZT (SW)
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V, AC coupled)
  - Mode: 35,840 Hz (Q≈2759, τ≈24.5ms)
  - Drive: slightly off-resonance for phase rotation

Usage:
  python tools/t3_3b_narma10.py [--steps 300] [--offset-hz 5]
"""
from __future__ import annotations

import argparse
import ctypes as ct
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SAMPLE_RATE_HZ = 781_250
N_SAMPLES = 2048
TIMEBASE = 7
RANGE_INDEX = 8        # ±5V
RANGE_MV = 5000.0
RELAY_CH = 8
N_FFT_PAD = 4

MODE_FREQ = 35_840.0   # target resonant mode
AWG_BASE_UVPP = 500_000  # max drive amplitude (0.5 Vpp)
AWG_MIN_SCALE = 0.1     # minimum input scaling (avoid zero drive)
T_STEP_MS = 12          # time per NARMA step (must be < τ for memory)

TRIGGER_SOURCE = 0
TRIGGER_THRESH = 0
TRIGGER_DIR = 0
TRIGGER_DELAY = 0
TRIGGER_AUTO_MS = 2000

os.environ['DYLD_LIBRARY_PATH'] = (
    '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relay_mux import RelayMux  # noqa: E402

# ---------------------------------------------------------------------------
# NARMA-10 target generation
# ---------------------------------------------------------------------------

def generate_narma10(u: np.ndarray) -> np.ndarray:
    """Generate NARMA-10 target from input sequence u ∈ [0, 0.5]."""
    N = len(u)
    y = np.zeros(N)
    for t in range(9, N - 1):
        y[t + 1] = (0.3 * y[t]
                    + 0.05 * y[t] * np.sum(y[t-9:t+1])
                    + 1.5 * u[t-9] * u[t]
                    + 0.1)
        # Clip to prevent divergence
        y[t + 1] = np.clip(y[t + 1], -1e6, 1e6)
    return y


# ---------------------------------------------------------------------------
# Hardware helpers
# ---------------------------------------------------------------------------

def open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle})")
    # AC coupling removes Board A DC offset
    ps2000.ps2000_set_channel(handle, 0, 1, 0, RANGE_INDEX)
    return handle, ps2000


def set_awg(handle, ps2000, freq_hz: float, uvpp: int):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, uvpp, 0,
        float(freq_hz), float(freq_hz), 0, 0, 0, 0
    )


def stop_awg(handle, ps2000):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0, 0, 0, 0
    )


def capture_triggered(handle, ps2000):
    """Single triggered capture → mV array."""
    ps2000.ps2000_set_trigger(
        handle, TRIGGER_SOURCE, TRIGGER_THRESH, TRIGGER_DIR,
        TRIGGER_DELAY, TRIGGER_AUTO_MS
    )
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ct.c_int32()))
    time.sleep(0.003)
    for _ in range(500):
        if ps2000.ps2000_ready(handle):
            break
        time.sleep(0.003)
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16(0)
    ps2000.ps2000_get_values(
        handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES, 0
    )
    return np.array(buf, dtype=np.float64) * (RANGE_MV / 32767.0)


def extract_amplitude_phase(mv: np.ndarray, freq_hz: float):
    """Extract FFT amplitude and phase at the target frequency."""
    ac = mv - mv.mean()
    window = np.hanning(N_SAMPLES)
    fft_c = np.fft.rfft(ac * window, n=N_SAMPLES * N_FFT_PAD)
    bin_width = SAMPLE_RATE_HZ / (N_SAMPLES * N_FFT_PAD)
    bin_idx = int(round(freq_hz / bin_width))
    lo = max(0, bin_idx - 3)
    hi = min(len(fft_c) - 1, bin_idx + 3)
    peak_bin = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
    amp = np.abs(fft_c[peak_bin])
    phase = np.angle(fft_c[peak_bin])
    return amp, phase


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run_narma10(n_steps: int = 300, offset_hz: float = 5.0):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    drive_freq = MODE_FREQ + offset_hz

    # Theoretical predictions
    tau_ms = 24.5  # from T1.1 Q measurement
    alpha = np.exp(-T_STEP_MS / tau_ms)
    delta_phi_deg = 360.0 * offset_hz * T_STEP_MS / 1000.0
    memory_10 = alpha ** 10

    print("=" * 70)
    print("T3.3b — NARMA-10 Reservoir Computing (Re-Excitation Interference)")
    print("=" * 70)
    print(f"  Mode: {MODE_FREQ:.0f} Hz (Q≈2759, τ≈{tau_ms:.1f} ms)")
    print(f"  Drive: {drive_freq:.0f} Hz (Δf = {offset_hz:+.1f} Hz off-resonance)")
    print(f"  Step time: {T_STEP_MS} ms")
    print(f"  Decay/step: α = {alpha:.3f}")
    print(f"  Phase rotation/step: Δφ = {delta_phi_deg:.1f}°")
    print(f"  10-step memory: α¹⁰ = {memory_10:.4f} ({memory_10*100:.2f}%)")
    print(f"  Steps: {n_steps} (train: first 60%, test: last 40%)")
    print(f"  Nonlinear mechanism: |A_drive + A_residual·e^{{jφ}}| envelope")
    print("=" * 70)

    # Generate NARMA-10 input/target
    np.random.seed(42)
    u = np.random.uniform(0, 0.5, size=n_steps)
    y_target = generate_narma10(u)

    # Open hardware
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(RELAY_CH)
    time.sleep(0.2)

    # Pre-excite to reach steady state
    set_awg(handle, ps2000, drive_freq, AWG_BASE_UVPP)
    time.sleep(0.5)

    # --- Collect reservoir states ---
    print("\n  Collecting reservoir states...")
    amplitudes = np.zeros(n_steps)
    phases = np.zeros(n_steps)

    for t in range(n_steps):
        # Set amplitude proportional to input u(t)
        scale = AWG_MIN_SCALE + (1.0 - AWG_MIN_SCALE) * (u[t] / 0.5)
        uvpp = int(AWG_BASE_UVPP * scale)
        set_awg(handle, ps2000, drive_freq, uvpp)

        # Wait for mode to respond (partial settling within one time step)
        time.sleep(T_STEP_MS / 1000.0)

        # Capture while driving
        mv = capture_triggered(handle, ps2000)
        amp, ph = extract_amplitude_phase(mv, drive_freq)
        amplitudes[t] = amp
        phases[t] = ph

        if (t + 1) % 50 == 0:
            print(f"    [{t+1}/{n_steps}] amp={amp:.0f}, phase={ph:.2f} rad")

    # Cleanup hardware
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # --- Build feature matrix ---
    print("\n  Building feature matrix...")
    K = 20  # history depth (covers >10 NARMA steps)

    # Features: amplitude and phase at current + K past steps
    n_valid = n_steps - K
    X = np.zeros((n_valid, 2 * (K + 1)))
    for t in range(K, n_steps):
        row = t - K
        for k in range(K + 1):
            X[row, 2 * k] = amplitudes[t - k]
            X[row, 2 * k + 1] = phases[t - k]

    y_valid = y_target[K:n_steps]
    u_valid = u[K:n_steps]

    # Normalize features
    X_mean = X.mean(axis=0)
    X_std = X.std(axis=0) + 1e-10
    X_norm = (X - X_mean) / X_std

    # Add polynomial cross-terms (degree 2 on amplitudes only)
    amp_cols = X_norm[:, ::2]  # even columns = amplitudes
    n_amp = amp_cols.shape[1]
    cross_terms = []
    for i in range(min(n_amp, 5)):  # limit to first 5 for tractability
        for j in range(i, min(n_amp, 5)):
            cross_terms.append((amp_cols[:, i] * amp_cols[:, j]).reshape(-1, 1))
    X_poly = np.hstack([X_norm] + cross_terms)

    # --- Train/test split ---
    split = int(0.6 * n_valid)
    X_train, X_test = X_norm[:split], X_norm[split:]
    X_train_poly, X_test_poly = X_poly[:split], X_poly[split:]
    y_train, y_test = y_valid[:split], y_valid[split:]

    print(f"  Train: {split} samples, Test: {n_valid - split} samples")
    print(f"  Linear features: {X_norm.shape[1]}, Poly features: {X_poly.shape[1]}")

    # --- Ridge regression ---
    def ridge_fit_predict(X_tr, y_tr, X_te, alpha=1.0):
        XtX = X_tr.T @ X_tr + alpha * np.eye(X_tr.shape[1])
        w = np.linalg.solve(XtX, X_tr.T @ y_tr)
        y_pred_train = X_tr @ w
        y_pred_test = X_te @ w
        return y_pred_train, y_pred_test, w

    # Linear readout
    y_hat_train_lin, y_hat_test_lin, w_lin = ridge_fit_predict(X_train, y_train, X_test)
    # Polynomial readout
    y_hat_train_poly, y_hat_test_poly, w_poly = ridge_fit_predict(X_train_poly, y_train, X_test_poly)

    # --- Baseline: direct input passthrough (no reservoir) ---
    # Use just the input history as features
    X_input = np.zeros((n_valid, K + 1))
    for t in range(K, n_steps):
        row = t - K
        for k in range(K + 1):
            X_input[row, k] = u[t - k]
    X_in_train, X_in_test = X_input[:split], X_input[split:]
    # Add polynomial terms to input baseline
    in_cross = []
    for i in range(min(K + 1, 11)):
        for j in range(i, min(K + 1, 11)):
            in_cross.append((X_input[:, i] * X_input[:, j]).reshape(-1, 1))
    X_input_poly = np.hstack([X_input] + in_cross)
    X_in_train_p, X_in_test_p = X_input_poly[:split], X_input_poly[split:]

    _, y_hat_test_input, _ = ridge_fit_predict(X_in_train, y_train, X_in_test)
    _, y_hat_test_input_poly, _ = ridge_fit_predict(X_in_train_p, y_train, X_in_test_p)

    # --- NRMSE computation ---
    def nrmse(y_true, y_pred):
        return np.sqrt(np.mean((y_true - y_pred) ** 2)) / np.std(y_true)

    nrmse_lin = nrmse(y_test, y_hat_test_lin)
    nrmse_poly = nrmse(y_test, y_hat_test_poly)
    nrmse_input = nrmse(y_test, y_hat_test_input)
    nrmse_input_poly = nrmse(y_test, y_hat_test_input_poly)

    # Train NRMSE for reference
    nrmse_train_lin = nrmse(y_train, y_hat_train_lin)
    nrmse_train_poly = nrmse(y_train, y_hat_train_poly)

    # --- Results ---
    print("\n" + "=" * 70)
    print("RESULTS — NARMA-10")
    print("=" * 70)
    print(f"\n     Model                    Train NRMSE   Test NRMSE   Status")
    print(f"  ─────────────────────────  ───────────   ──────────   ────────")
    print(f"     Plate (linear readout)     {nrmse_train_lin:.4f}        {nrmse_lin:.4f}       "
          f"{'PASS' if nrmse_lin < 0.4 else 'FAIL'}")
    print(f"     Plate (poly readout)       {nrmse_train_poly:.4f}        {nrmse_poly:.4f}       "
          f"{'PASS' if nrmse_poly < 0.4 else 'FAIL'}")
    print(f"     Input only (linear)           —          {nrmse_input:.4f}       baseline")
    print(f"     Input only (poly)             —          {nrmse_input_poly:.4f}       baseline")

    best_nrmse = min(nrmse_lin, nrmse_poly)
    best_baseline = min(nrmse_input, nrmse_input_poly)
    improvement = (best_baseline - best_nrmse) / best_baseline * 100

    print(f"\n  Best plate NRMSE: {best_nrmse:.4f}")
    print(f"  Best input-only baseline: {best_baseline:.4f}")
    if best_nrmse < best_baseline:
        print(f"  Reservoir improvement: {improvement:.1f}% over baseline")
    else:
        print(f"  No reservoir improvement (plate ≈ linear passthrough)")

    print(f"\n  Amplitude statistics:")
    print(f"    Mean: {amplitudes.mean():.0f}, Std: {amplitudes.std():.0f}")
    print(f"    Min: {amplitudes.min():.0f}, Max: {amplitudes.max():.0f}")
    print(f"    Input correlation: {np.corrcoef(u, amplitudes)[0,1]:.3f}")

    # Check for nonlinear contribution
    # If plate adds value beyond input passthrough, it's doing computation
    gate = "PASS" if best_nrmse < 0.4 else "FAIL"
    print(f"\n  ★ NARMA-10 GATE: {gate} — NRMSE = {best_nrmse:.4f}")
    if gate == "PASS":
        print("    Plate reservoir computes NARMA-10 with acceptable accuracy.")
    else:
        print("    Plate reservoir insufficient for NARMA-10 benchmark.")

    # Save results
    out_dir = Path("data/results/reservoir_classify")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"t3_3b_narma10_{ts}.json"
    results = {
        "experiment": "T3.3b",
        "timestamp": ts,
        "gate_decision": gate,
        "mode_hz": MODE_FREQ,
        "offset_hz": offset_hz,
        "drive_freq_hz": drive_freq,
        "t_step_ms": T_STEP_MS,
        "n_steps": n_steps,
        "nrmse_linear": float(nrmse_lin),
        "nrmse_poly": float(nrmse_poly),
        "nrmse_input_baseline": float(nrmse_input),
        "nrmse_input_poly_baseline": float(nrmse_input_poly),
        "best_nrmse": float(best_nrmse),
        "improvement_pct": float(improvement) if best_nrmse < best_baseline else 0.0,
        "alpha_per_step": float(alpha),
        "delta_phi_per_step_deg": float(delta_phi_deg),
        "amplitude_mean": float(amplitudes.mean()),
        "amplitude_std": float(amplitudes.std()),
        "input_correlation": float(np.corrcoef(u, amplitudes)[0, 1]),
    }
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved: {out_file}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="T3.3b NARMA-10 Reservoir")
    parser.add_argument("--steps", type=int, default=300,
                        help="NARMA-10 sequence length (default: 300)")
    parser.add_argument("--offset-hz", type=float, default=5.0,
                        help="Frequency offset from resonance (default: 5 Hz)")
    args = parser.parse_args()
    run_narma10(n_steps=args.steps, offset_hz=args.offset_hz)
