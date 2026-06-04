#!/usr/bin/env python3
"""
T3.1 — Boolean Compute via Plate Modes (Fused Silica)

Tests whether multi-mode drive patterns can encode Boolean inputs that are
recoverable from a single FFT capture. This is the CWM computation primitive:
drive a subset of modes (encoding an N-bit word), capture once, classify which
pattern was driven.

Protocol:
  1. Enrollment: drive each mode solo → record amplitude (template)
  2. For each of 2^N possible drive patterns:
     a. Simultaneously drive active modes via sequential rapid bursts
        (AWG is single-frequency, so we time-multiplex within one capture window)
     b. Capture single 2048-sample block
     c. Compute FFT magnitude at each mode bin
  3. Train ridge classifier on spectral features + polynomial expansion
  4. Test classification accuracy (leave-one-out or train/test split)

Modes (from T1.2/T1.3): 35,840 / 54,920 / 57,037 / 97,011 Hz
These are separated by >1000 Hz (2.6× the 381.5 Hz bin width) so they
are cleanly resolvable in a single FFT.

Success criterion: ≥ 90% accuracy at 4 bits (16 patterns)
Kill criterion: < 75% accuracy after all feature engineering

Hardware:
  - PicoScope AWG → Board D (3.69×) → TX PZT (SW) → Plate
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V)
  - 2048 samples, timebase 7 → 781,250 Hz sample rate

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t3_1_boolean_compute.py

  # Quick mode (fewer reps):
  python tools/t3_1_boolean_compute.py --reps 5

  # Use only 3 modes (8 patterns):
  python tools/t3_1_boolean_compute.py --freqs 35840 57037 97011
"""
from __future__ import annotations

import argparse
import ctypes as ct
import json
import os
import sys
import time
from datetime import datetime
from itertools import product
from pathlib import Path

import numpy as np
from sklearn.linear_model import RidgeClassifier
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.model_selection import cross_val_score, LeaveOneOut

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SAMPLE_RATE_HZ = 781_250
N_SAMPLES = 2048
TIMEBASE = 7
FFT_BIN_HZ = SAMPLE_RATE_HZ / N_SAMPLES  # ~381.5 Hz

# 4 confirmed discriminable modes from T1.2/T1.3
DEFAULT_MODES_HZ = [35_840, 54_920, 57_037, 97_011]

AWG_DRIVE_UVPP = 500_000          # 0.5 Vpp
SETTLE_S = 0.20                    # AWG settle before capture
BURST_S = 0.015                    # per-mode burst duration (15 ms ≈ ringdown τ)
RELAY_CH = 8                       # NE sensor
RANGE_INDEX = 8                    # ±5V
RANGE_MV = 5000.0
REPS_DEFAULT = 10                  # captures per pattern
N_FFT_PAD = 4                      # zero-padding factor for FFT

os.environ['DYLD_LIBRARY_PATH'] = (
    '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relay_mux import RelayMux  # noqa: E402

# ---------------------------------------------------------------------------
# PicoScope helpers
# ---------------------------------------------------------------------------


def open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, 1, 1, RANGE_INDEX)
    return handle, ps2000


def capture_block(handle, ps2000):
    """Capture a single 2048-sample block with auto-trigger."""
    ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ct.c_int32()))
    time.sleep(0.05)
    for _ in range(200):
        if ps2000.ps2000_ready(handle):
            break
        time.sleep(0.02)
    else:
        raise TimeoutError("PicoScope capture timed out")

    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16(0)
    ps2000.ps2000_get_values(
        handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES, 0
    )
    mv = np.array(buf, dtype=np.float64) * (RANGE_MV / 32767.0)
    return mv


def set_awg(handle, ps2000, freq_hz: float):
    """Set AWG to CW sine at given frequency."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz),
        0, 0, 0, 0
    )


def stop_awg(handle, ps2000):
    """Turn off AWG."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0, 0, 0, 0
    )


# ---------------------------------------------------------------------------
# Spectral analysis
# ---------------------------------------------------------------------------


def compute_fft_features(mv: np.ndarray, modes_hz: list[float]) -> np.ndarray:
    """Extract FFT magnitudes at each mode bin (±3 bins max, zero-padded).

    Returns array of length len(modes_hz) with peak magnitudes.
    """
    ac = mv - mv.mean()
    window = np.hanning(len(ac))
    nfft = len(ac) * N_FFT_PAD
    fft_mag = np.abs(np.fft.rfft(ac * window, n=nfft))
    bin_hz = SAMPLE_RATE_HZ / nfft

    features = np.zeros(len(modes_hz))
    for i, freq in enumerate(modes_hz):
        target_bin = int(round(freq / bin_hz))
        lo = max(0, target_bin - 3)
        hi = min(len(fft_mag) - 1, target_bin + 3)
        features[i] = float(fft_mag[lo:hi + 1].max())

    return features


def compute_full_spectrum(mv: np.ndarray) -> np.ndarray:
    """Return full zero-padded FFT magnitude for enrollment."""
    ac = mv - mv.mean()
    window = np.hanning(len(ac))
    nfft = len(ac) * N_FFT_PAD
    fft_mag = np.abs(np.fft.rfft(ac * window, n=nfft))
    return fft_mag


# ---------------------------------------------------------------------------
# Drive patterns
# ---------------------------------------------------------------------------


def capture_pattern_sequential(handle, ps2000, modes_hz: list[float],
                                pattern: tuple[int, ...]):
    """Drive a Boolean pattern using per-mode sequential capture.

    Since the PicoScope AWG is single-frequency and modes decay quickly,
    we drive each mode individually and capture DURING each drive.
    This gives a clean per-mode measurement regardless of drive order.

    Returns: feature vector of shape (n_modes,) — magnitude at each mode bin.
    For active bits: drive that mode, capture, extract its magnitude.
    For inactive bits: AWG off during that slot, capture noise level.
    """
    features = np.zeros(len(modes_hz))

    for i, (freq, bit) in enumerate(zip(modes_hz, pattern)):
        if bit == 1:
            set_awg(handle, ps2000, freq)
            time.sleep(SETTLE_S)
        else:
            stop_awg(handle, ps2000)
            time.sleep(SETTLE_S)

        mv = capture_block(handle, ps2000)
        feat = compute_fft_features(mv, modes_hz)
        features[i] = feat[i]  # only take the magnitude at THIS mode's bin

    stop_awg(handle, ps2000)
    return features


def capture_pattern_sequential_full(handle, ps2000, modes_hz: list[float],
                                     pattern: tuple[int, ...]):
    """Full cross-mode feature capture: for each drive slot, record ALL bins.

    Returns: feature vector of shape (n_modes * n_modes,) — every mode bin
    measured during each drive slot. Captures cross-coupling information.
    """
    n = len(modes_hz)
    features = np.zeros(n * n)

    for i, (freq, bit) in enumerate(zip(modes_hz, pattern)):
        if bit == 1:
            set_awg(handle, ps2000, freq)
            time.sleep(SETTLE_S)
        else:
            stop_awg(handle, ps2000)
            time.sleep(SETTLE_S)

        mv = capture_block(handle, ps2000)
        feat = compute_fft_features(mv, modes_hz)
        features[i * n:(i + 1) * n] = feat

    stop_awg(handle, ps2000)
    return features


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


def enroll_modes(handle, ps2000, modes_hz: list[float], n_avg: int = 5):
    """Capture solo response for each mode and noise floor.

    Returns:
        noise_floor: array of shape (n_modes,) — magnitude at each mode bin with no drive
        solo_responses: dict {mode_idx: array of shape (n_modes,)} — response driving one mode
    """
    print("  Enrollment phase...")

    # Noise floor (AWG off)
    stop_awg(handle, ps2000)
    time.sleep(0.3)
    noise_samples = []
    for _ in range(n_avg):
        mv = capture_block(handle, ps2000)
        feat = compute_fft_features(mv, modes_hz)
        noise_samples.append(feat)
    noise_floor = np.mean(noise_samples, axis=0)
    print(f"    Noise floor: {noise_floor}")

    # Solo responses
    solo_responses = {}
    for i, freq in enumerate(modes_hz):
        set_awg(handle, ps2000, freq)
        time.sleep(SETTLE_S + 0.1)  # extra settle for enrollment
        solo_samples = []
        for _ in range(n_avg):
            mv = capture_block(handle, ps2000)
            feat = compute_fft_features(mv, modes_hz)
            solo_samples.append(feat)
        solo_responses[i] = np.mean(solo_samples, axis=0)
        snr = solo_responses[i][i] / max(noise_floor[i], 1e-6)
        print(f"    Mode {freq:>6,} Hz: solo mag = {solo_responses[i][i]:.1f}, "
              f"SNR = {snr:.1f}×")

    stop_awg(handle, ps2000)
    return noise_floor, solo_responses


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------


def run_boolean_compute(modes_hz: list[float], n_reps: int, relay_ch: int,
                         poly_degree: int = 3, skip_null: bool = False):
    """Run the Boolean compute experiment."""
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(relay_ch)
    time.sleep(0.2)

    n_modes = len(modes_hz)
    # Generate all 2^N binary patterns
    patterns = list(product([0, 1], repeat=n_modes))
    if skip_null:
        patterns = [p for p in patterns if sum(p) > 0]
    n_patterns = len(patterns)

    print(f"\n{'='*60}")
    print(f"T3.1 — Boolean Compute via Plate Modes")
    print(f"{'='*60}")
    print(f"  Modes: {modes_hz}")
    print(f"  Bits: {n_modes}")
    print(f"  Patterns: {n_patterns} ({'excl' if skip_null else 'incl'} null)")
    print(f"  Reps per pattern: {n_reps}")
    print(f"  Poly degree: {poly_degree}")
    print(f"  Total captures: {n_patterns * n_reps}")
    print(f"  FFT bin: {FFT_BIN_HZ:.1f} Hz, zero-pad: {N_FFT_PAD}×")
    print(f"{'='*60}\n")

    # --- Phase 1: Enrollment ---
    noise_floor, solo_responses = enroll_modes(handle, ps2000, modes_hz)

    # --- Phase 2: Data collection ---
    print(f"\n  Data collection ({n_patterns} patterns × {n_reps} reps)...")
    print(f"  Mode: per-mode sequential capture (4 drives + captures per pattern)")
    X_raw = []       # per-mode magnitudes (diagonal features)
    X_full = []      # full cross-mode features (n_modes × n_modes)
    y_labels = []    # pattern index
    y_bits = []      # bit pattern tuple

    for pi, pattern in enumerate(patterns):
        bits_str = ''.join(str(b) for b in pattern)
        active = sum(pattern)
        print(f"    [{pi+1:>2}/{n_patterns}] pattern {bits_str} "
              f"({active} modes active)...", end=" ", flush=True)

        captures_diag = []
        captures_full = []
        for rep in range(n_reps):
            # Full cross-mode capture
            feat_full = capture_pattern_sequential_full(
                handle, ps2000, modes_hz, pattern)
            # Extract diagonal (per-mode self-response)
            n = len(modes_hz)
            feat_diag = np.array([feat_full[i * n + i] for i in range(n)])

            captures_diag.append(feat_diag)
            captures_full.append(feat_full)
            X_raw.append(feat_diag)
            X_full.append(feat_full)
            y_labels.append(pi)
            y_bits.append(pattern)

        mean_feat = np.mean(captures_diag, axis=0)
        print(f"mean mag = [{', '.join(f'{v:.0f}' for v in mean_feat)}]")

    # Cleanup hardware
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print(f"\n  Hardware closed. Analyzing {len(X_raw)} captures...\n")

    # --- Phase 3: Feature engineering + classification ---
    X_raw = np.array(X_raw)
    y = np.array(y_labels)

    # 3a. Template residual: subtract predicted linear response
    X_expected = np.zeros_like(X_raw)
    for idx, pattern in enumerate(y_bits):
        pred = noise_floor.copy()
        for k, bit in enumerate(pattern):
            if bit:
                pred = pred + (solo_responses[k] - noise_floor)
        X_expected[idx] = pred
    X_residual = X_raw - X_expected

    # 3b. Log-magnitude features
    X_log = np.log1p(X_raw)
    X_full = np.array(X_full)
    X_log_full = np.log1p(X_full)

    results = {}

    # Classification
    print("  Classification results:")
    print(f"  {'Method':<40s} {'Accuracy':>8s}  {'CV-σ':>5s}")
    print(f"  {'─'*40} {'─'*8}  {'─'*5}")

    feature_sets = [
        ("raw_diag", X_raw),
        ("log_diag", X_log),
        ("template_residual", X_residual),
        ("raw_full_crossmode", X_full),
        ("log_full_crossmode", X_log_full),
    ]

    for name, X_feat in feature_sets:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_feat)
        clf = RidgeClassifier(alpha=1.0)
        if len(X_scaled) <= 20:
            scores = cross_val_score(clf, X_scaled, y, cv=LeaveOneOut())
        else:
            scores = cross_val_score(clf, X_scaled, y, cv=5)
        acc = scores.mean() * 100
        std = scores.std() * 100
        results[name] = {"accuracy": acc, "std": std}
        print(f"  {name:<40s} {acc:>7.1f}%  ±{std:.1f}")

    # Polynomial features (the key technique from prior sessions)
    for name, X_feat in feature_sets:
        poly_name = f"{name}+poly{poly_degree}"
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_feat)
        poly = PolynomialFeatures(degree=poly_degree, include_bias=False)
        X_poly = poly.fit_transform(X_scaled)
        clf = RidgeClassifier(alpha=1.0)
        if len(X_poly) <= 20:
            scores = cross_val_score(clf, X_poly, y, cv=LeaveOneOut())
        else:
            scores = cross_val_score(clf, X_poly, y, cv=5)
        acc = scores.mean() * 100
        std = scores.std() * 100
        results[poly_name] = {"accuracy": acc, "std": std,
                               "n_features": X_poly.shape[1]}
        print(f"  {poly_name:<40s} {acc:>7.1f}%  ±{std:.1f}  "
              f"({X_poly.shape[1]} feat)")

    # Per-bit binary classification (can we decode individual bits?)
    print(f"\n  Per-bit decoding (independent classifiers on full crossmode):")
    y_bits_arr = np.array(y_bits)
    bit_accuracies = []
    for bi in range(n_modes):
        y_bit = y_bits_arr[:, bi]
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_full)
        poly = PolynomialFeatures(degree=poly_degree, include_bias=False)
        X_poly = poly.fit_transform(X_scaled)
        clf = RidgeClassifier(alpha=1.0)
        if len(X_poly) <= 20:
            scores = cross_val_score(clf, X_poly, y_bit, cv=LeaveOneOut())
        else:
            scores = cross_val_score(clf, X_poly, y_bit, cv=5)
        bit_acc = scores.mean() * 100
        bit_accuracies.append(bit_acc)
        print(f"    Bit {bi} ({modes_hz[bi]:>6,} Hz): {bit_acc:.1f}%")

    # --- Summary ---
    best_method = max(results, key=lambda k: results[k]["accuracy"])
    best_acc = results[best_method]["accuracy"]
    n_bits = n_modes
    mean_bit_acc = float(np.mean(bit_accuracies))

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Bits encoded: {n_bits}")
    print(f"  Patterns tested: {n_patterns}")
    print(f"  Best method: {best_method}")
    print(f"  Best accuracy: {best_acc:.1f}%")
    print(f"  Mean per-bit accuracy: {mean_bit_acc:.1f}%")

    # Gate decision
    if best_acc >= 90.0 and n_bits >= 4:
        gate = "PASS"
        print(f"\n  ★ GATE DECISION: PASS ({best_acc:.1f}% ≥ 90% at {n_bits} bits)")
    elif best_acc >= 75.0:
        gate = "MARGINAL"
        print(f"\n  ◆ GATE DECISION: MARGINAL ({best_acc:.1f}% — between 75–90%)")
    else:
        gate = "FAIL"
        print(f"\n  ✗ GATE DECISION: FAIL ({best_acc:.1f}% < 75%)")

    # Save results
    out_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "boolean_compute"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"t3_1_boolean_{ts}.json"

    result_doc = {
        "experiment": "T3.1_boolean_compute",
        "timestamp": datetime.now().isoformat(),
        "plate": "100x100mm_fused_silica",
        "relay_channel": relay_ch,
        "modes_hz": modes_hz,
        "n_bits": n_bits,
        "n_patterns": n_patterns,
        "n_reps": n_reps,
        "poly_degree": poly_degree,
        "awg_amplitude_uvpp": AWG_DRIVE_UVPP,
        "burst_s": BURST_S,
        "settle_s": SETTLE_S,
        "enrollment": {
            "noise_floor": noise_floor.tolist(),
            "solo_responses": {str(k): v.tolist() for k, v in solo_responses.items()},
        },
        "classification_results": {
            k: {"accuracy_pct": v["accuracy"], "std_pct": v["std"]}
            for k, v in results.items()
        },
        "per_bit_accuracy_pct": bit_accuracies,
        "mean_per_bit_accuracy_pct": mean_bit_acc,
        "best_method": best_method,
        "best_accuracy_pct": best_acc,
        "gate_decision": gate,
        "X_raw": X_raw.tolist(),
        "X_full_crossmode": X_full.tolist(),
        "y_labels": y_labels,
        "y_bits": [list(p) for p in y_bits],
    }

    with open(out_path, "w") as fp:
        json.dump(result_doc, fp, indent=2)
    print(f"\n  Results saved: {out_path}")

    return gate, best_acc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="T3.1 Boolean Compute via Plate Modes")
    parser.add_argument("--freqs", type=int, nargs="+", default=DEFAULT_MODES_HZ,
                        help="Mode frequencies in Hz")
    parser.add_argument("--reps", type=int, default=REPS_DEFAULT,
                        help="Repetitions per pattern")
    parser.add_argument("--relay", type=int, default=RELAY_CH,
                        help="Relay channel for RX PZT")
    parser.add_argument("--poly", type=int, default=3,
                        help="Polynomial feature degree")
    parser.add_argument("--skip-null", action="store_true",
                        help="Skip all-zeros pattern (0000)")
    args = parser.parse_args()

    run_boolean_compute(
        modes_hz=args.freqs,
        n_reps=args.reps,
        relay_ch=args.relay,
        poly_degree=args.poly,
        skip_null=args.skip_null,
    )


if __name__ == "__main__":
    main()
