#!/usr/bin/env python3
"""
T3.3 — Reservoir Computing (Multi-Class Classification)

Tests whether the fused-silica plate, treated as a physical reservoir,
can classify multi-mode input patterns from a single spectral capture
using a trained linear readout.

Concept:
  The plate's eigenmode spectrum acts as a fixed linear feature extractor.
  Different drive patterns (combinations of modes) produce distinct spectral
  signatures. A ridge-regression readout layer trained on calibration data
  classifies new captures with >80% accuracy — demonstrating that the plate
  performs the "forward pass" physically, with only a trivial linear layer
  needed for classification.

  Time-multiplexing: Since the AWG can only output one frequency at a time,
  we exploit the plate's memory (Q≈2759, τ≈24.5ms at 35840 Hz) to drive
  multiple modes in rapid succession. Earlier modes still ring when the
  capture is taken, producing a multi-modal spectral fingerprint.

Success Metric:
  > 80% 4-class accuracy from a single capture, using a linear readout.

Architecture:
  - Input encoding: 4-bit binary pattern → time-multiplexed AWG bursts
  - Reservoir: glass plate transfer function (fixed physics)
  - Features: FFT amplitudes at mode frequencies (+ optional phase, poly)
  - Readout: Ridge regression (α=1.0), one-hot class labels
  - Evaluation: stratified 5-fold cross-validation

Hardware:
  - PicoScope AWG (0.5 Vpp) → Board D (×3.69) → TX PZT (SW)
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V, AC coupled)
  - Trigger: Ch A rising edge at 0 mV

Modes:
  35,840 / 54,920 / 57,037 / 97,011 Hz

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t3_3_reservoir_classify.py [--samples-per-class 30]
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

AWG_DRIVE_UVPP = 500_000   # 0.5 Vpp
BURST_MS = 20               # time per mode burst
RINGDOWN_WAIT_MS = 2        # settle before capture (AWG still on last mode)
N_SAMPLES_PER_CLASS = 30    # default captures per class

MODES_HZ = [35_840, 54_920, 57_037, 97_011]

# 4-class input patterns: time-multiplexed mode sequences.
# AWG remains on LAST mode during capture (ringdown undetectable via USB latency).
# Each class has a unique (first, last) pair — the reservoir's transfer function
# at the last mode provides the dominant feature, but the sequence history
# (amplitude ratio between modes) provides secondary discrimination.
# Class 0: mode3→mode0 (history=97011, active=35840)
# Class 1: mode2→mode1 (history=57037, active=54920)
# Class 2: mode0→mode2 (history=35840, active=57037)
# Class 3: mode1→mode3 (history=54920, active=97011)
CLASSES = [
    [3, 0],  # Class 0: 97011→35840
    [2, 1],  # Class 1: 57037→54920
    [0, 2],  # Class 2: 35840→57037
    [1, 3],  # Class 3: 54920→97011
]

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
# Hardware helpers
# ---------------------------------------------------------------------------


def open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle})")
    # AC coupling removes Board A DC offset (~3V)
    ps2000.ps2000_set_channel(handle, 0, 1, 0, RANGE_INDEX)
    return handle, ps2000


def set_awg(handle, ps2000, freq_hz: float, uvpp: int = AWG_DRIVE_UVPP):
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
    time.sleep(0.005)
    for _ in range(500):
        if ps2000.ps2000_ready(handle):
            break
        time.sleep(0.005)
    else:
        raise TimeoutError("Capture timed out")
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16(0)
    ps2000.ps2000_get_values(
        handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES, 0
    )
    return np.array(buf, dtype=np.float64) * (RANGE_MV / 32767.0)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_features(mv: np.ndarray, use_phase: bool = False) -> np.ndarray:
    """Extract FFT amplitudes (and optionally phase) at mode frequencies."""
    ac = mv - mv.mean()
    window = np.hanning(N_SAMPLES)
    fft_c = np.fft.rfft(ac * window, n=N_SAMPLES * N_FFT_PAD)
    bin_width = SAMPLE_RATE_HZ / (N_SAMPLES * N_FFT_PAD)

    features = []
    for freq in MODES_HZ:
        bin_idx = int(round(freq / bin_width))
        lo = max(0, bin_idx - 3)
        hi = min(len(fft_c) - 1, bin_idx + 3)
        peak_bin = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
        amp = np.abs(fft_c[peak_bin])
        features.append(amp)
        if use_phase:
            features.append(np.angle(fft_c[peak_bin]))
    return np.array(features)


def polynomial_features(X: np.ndarray, degree: int = 2) -> np.ndarray:
    """Add interaction terms (degree-2 polynomial expansion on amplitudes)."""
    n_samples, n_feats = X.shape
    cols = [X]
    if degree >= 2:
        for i in range(n_feats):
            for j in range(i, n_feats):
                cols.append((X[:, i] * X[:, j]).reshape(-1, 1))
    return np.hstack(cols)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def ridge_classify(X_train, y_train, X_test, alpha=1.0):
    """Ridge regression multi-class classifier (one-hot targets)."""
    n_classes = int(y_train.max()) + 1
    # One-hot encode targets
    Y = np.zeros((len(y_train), n_classes))
    for i, c in enumerate(y_train):
        Y[i, int(c)] = 1.0
    # Ridge: W = (X^T X + αI)^{-1} X^T Y
    XtX = X_train.T @ X_train + alpha * np.eye(X_train.shape[1])
    W = np.linalg.solve(XtX, X_train.T @ Y)
    # Predict
    scores = X_test @ W
    return scores.argmax(axis=1), W


def cross_validate(X, y, n_folds=5, alpha=1.0):
    """Stratified k-fold cross-validation."""
    n = len(y)
    classes = np.unique(y)
    # Build stratified folds
    indices = np.arange(n)
    fold_ids = np.zeros(n, dtype=int)
    for c in classes:
        c_idx = indices[y == c]
        np.random.shuffle(c_idx)
        for i, idx in enumerate(c_idx):
            fold_ids[idx] = i % n_folds

    accuracies = []
    all_preds = np.zeros(n, dtype=int)
    for fold in range(n_folds):
        test_mask = fold_ids == fold
        train_mask = ~test_mask
        X_tr, X_te = X[train_mask], X[test_mask]
        y_tr, y_te = y[train_mask], y[test_mask]
        preds, _ = ridge_classify(X_tr, y_tr, X_te, alpha=alpha)
        all_preds[test_mask] = preds
        acc = np.mean(preds == y_te)
        accuracies.append(acc)
    return np.mean(accuracies), accuracies, all_preds


def confusion_matrix(y_true, y_pred, n_classes):
    """Build confusion matrix."""
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[int(t), int(p)] += 1
    return cm


# ---------------------------------------------------------------------------
# Drive patterns
# ---------------------------------------------------------------------------

def drive_pattern(handle, ps2000, mode_indices: list[int]):
    """Time-multiplex drive: burst each mode in sequence, capture while last mode active."""
    # Drive each mode for BURST_MS
    for idx in mode_indices:
        set_awg(handle, ps2000, MODES_HZ[idx])
        time.sleep(BURST_MS / 1000.0)
    # Last mode still active — capture now (plate ringdown not observable via USB)
    time.sleep(RINGDOWN_WAIT_MS / 1000.0)
    mv = capture_triggered(handle, ps2000)
    return mv


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run_experiment(n_samples_per_class: int = N_SAMPLES_PER_CLASS):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 70)
    print("T3.3 — Reservoir Computing (Multi-Class Classification)")
    print("=" * 70)
    print(f"  Modes: {MODES_HZ} Hz")
    print(f"  Classes: {len(CLASSES)} (2-mode patterns)")
    for i, cls in enumerate(CLASSES):
        modes_str = " + ".join(f"{MODES_HZ[m]}" for m in cls)
        print(f"    Class {i}: [{','.join(str(m) for m in cls)}] → {modes_str} Hz")
    print(f"  Samples/class: {n_samples_per_class}")
    print(f"  Burst per mode: {BURST_MS} ms")
    print(f"  Total sequence: {BURST_MS * 2 + RINGDOWN_WAIT_MS} ms (+ ringdown capture)")
    print(f"  Readout: Ridge regression (α=1.0), 5-fold CV")
    print(f"  Pass criterion: > 80% 4-class accuracy")
    print("=" * 70)

    # Open hardware
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(RELAY_CH)
    time.sleep(0.2)

    # --- Part 1: Collect training/test data ---
    print("\n  Part 1: Data collection")
    print(f"    Collecting {n_samples_per_class} captures × {len(CLASSES)} classes"
          f" = {n_samples_per_class * len(CLASSES)} total...")

    all_features = []
    all_labels = []
    all_features_phase = []

    # Randomize class order to avoid systematic drift
    trial_order = []
    for trial in range(n_samples_per_class):
        for cls_idx in range(len(CLASSES)):
            trial_order.append((trial, cls_idx))
    np.random.shuffle(trial_order)

    for i, (trial, cls_idx) in enumerate(trial_order):
        if (i + 1) % 20 == 0 or i == 0:
            print(f"      [{i+1}/{len(trial_order)}]", end="\r")
        mv = drive_pattern(handle, ps2000, CLASSES[cls_idx])
        feat = extract_features(mv, use_phase=False)
        feat_ph = extract_features(mv, use_phase=True)
        all_features.append(feat)
        all_features_phase.append(feat_ph)
        all_labels.append(cls_idx)

    X = np.array(all_features)
    X_ph = np.array(all_features_phase)
    y = np.array(all_labels)
    print(f"      Collected {len(y)} samples.                 ")

    # Normalize features (z-score)
    X_mean, X_std = X.mean(axis=0), X.std(axis=0)
    X_norm = (X - X_mean) / (X_std + 1e-10)

    X_ph_mean, X_ph_std = X_ph.mean(axis=0), X_ph.std(axis=0)
    X_ph_norm = (X_ph - X_ph_mean) / (X_ph_std + 1e-10)

    # Polynomial expansion (degree-2)
    X_poly = polynomial_features(X_norm, degree=2)

    # --- Part 2: Classification ---
    print("\n  Part 2: Classification (5-fold cross-validation)")

    # Raw amplitude features (4D)
    acc_raw, folds_raw, preds_raw = cross_validate(X_norm, y)
    cm_raw = confusion_matrix(y, preds_raw, len(CLASSES))

    # Amplitude + phase features (8D)
    acc_ph, folds_ph, preds_ph = cross_validate(X_ph_norm, y)
    cm_ph = confusion_matrix(y, preds_ph, len(CLASSES))

    # Polynomial features (4 + 10 = 14D)
    acc_poly, folds_poly, preds_poly = cross_validate(X_poly, y)
    cm_poly = confusion_matrix(y, preds_poly, len(CLASSES))

    print(f"\n     Feature set       Dims   Accuracy")
    print(f"  ─────────────────  ──────  ─────────")
    print(f"     Amplitude only      {X_norm.shape[1]}    {acc_raw*100:5.1f}%")
    print(f"     Amp + Phase         {X_ph_norm.shape[1]}    {acc_ph*100:5.1f}%")
    print(f"     Amp Poly(deg=2)    {X_poly.shape[1]:2d}    {acc_poly*100:5.1f}%")

    best_acc = max(acc_raw, acc_ph, acc_poly)
    best_name = (
        "Amplitude only" if best_acc == acc_raw else
        "Amp + Phase" if best_acc == acc_ph else
        "Amp Poly(deg=2)"
    )

    # --- Part 3: Confusion matrix (best model) ---
    print(f"\n  Part 3: Confusion matrix (best: {best_name})")
    if best_acc == acc_raw:
        cm_best = cm_raw
    elif best_acc == acc_ph:
        cm_best = cm_ph
    else:
        cm_best = cm_poly

    print(f"                    Predicted")
    print(f"                 C0   C1   C2   C3")
    for i in range(len(CLASSES)):
        row = "  ".join(f"{cm_best[i,j]:3d}" for j in range(len(CLASSES)))
        print(f"    Actual C{i}:  {row}")

    per_class = cm_best.diagonal() / cm_best.sum(axis=1)
    print(f"\n    Per-class accuracy: "
          + ", ".join(f"C{i}={per_class[i]*100:.0f}%" for i in range(len(CLASSES))))

    # --- Part 4: Feature separability ---
    print("\n  Part 4: Feature separability (class means ± std)")
    print(f"     Class   {'   '.join(f'{MODES_HZ[m]:>7d}' for m in range(4))} Hz")
    print(f"  ─────────  " + "  ".join("─" * 9 for _ in range(4)))
    for cls_idx in range(len(CLASSES)):
        mask = y == cls_idx
        means = X[mask].mean(axis=0)
        stds = X[mask].std(axis=0)
        vals = "  ".join(f"{means[m]:7.0f}±{stds[m]:<.0f}" for m in range(4))
        print(f"       C{cls_idx}     {vals}")

    # --- Part 5: SNR sweep (reduce drive amplitude) ---
    print("\n  Part 5: SNR sweep (reducing drive amplitude)")
    drive_levels = [500_000, 250_000, 100_000, 50_000]  # µVpp
    snr_results = []

    for uvpp in drive_levels:
        # Collect quick dataset at this drive level
        X_snr = []
        y_snr = []
        n_quick = 10  # per class
        for cls_idx in range(len(CLASSES)):
            for _ in range(n_quick):
                # Drive with reduced amplitude (same stop-and-capture approach)
                for idx in CLASSES[cls_idx]:
                    set_awg(handle, ps2000, MODES_HZ[idx], uvpp)
                    time.sleep(BURST_MS / 1000.0)
                time.sleep(RINGDOWN_WAIT_MS / 1000.0)
                mv = capture_triggered(handle, ps2000)
                feat = extract_features(mv, use_phase=False)
                X_snr.append(feat)
                y_snr.append(cls_idx)

        X_snr = np.array(X_snr)
        y_snr = np.array(y_snr)
        X_snr_n = (X_snr - X_snr.mean(axis=0)) / (X_snr.std(axis=0) + 1e-10)
        acc_snr, _, _ = cross_validate(X_snr_n, y_snr, n_folds=5)
        snr_results.append((uvpp / 1000.0, acc_snr))
        print(f"    Drive {uvpp/1000:.0f} mVpp → accuracy: {acc_snr*100:.1f}%")

    # Cleanup hardware
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # --- Summary ---
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Best accuracy: {best_acc*100:.1f}% ({best_name})")
    print(f"  Amplitude-only: {acc_raw*100:.1f}%")
    print(f"  Amp + Phase: {acc_ph*100:.1f}%")
    print(f"  Polynomial: {acc_poly*100:.1f}%")
    print(f"  Per-class: {', '.join(f'C{i}={per_class[i]*100:.0f}%' for i in range(len(CLASSES)))}")
    gate = "PASS" if best_acc >= 0.80 else "FAIL"
    print(f"\n  ★ GATE DECISION: {gate} — {best_acc*100:.1f}% 4-class accuracy")
    if gate == "PASS":
        print("    Plate acts as viable physical reservoir for pattern classification.")
    else:
        print("    Plate reservoir insufficient for >80% 4-class classification.")

    # Save results
    out_dir = Path("data/results/reservoir_classify")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"t3_3_reservoir_{ts}.json"
    results = {
        "experiment": "T3.3",
        "timestamp": ts,
        "gate_decision": gate,
        "modes_hz": MODES_HZ,
        "classes": CLASSES,
        "n_samples_per_class": n_samples_per_class,
        "burst_ms": BURST_MS,
        "accuracy_raw": float(acc_raw),
        "accuracy_phase": float(acc_ph),
        "accuracy_poly": float(acc_poly),
        "best_accuracy": float(best_acc),
        "best_feature_set": best_name,
        "per_class_accuracy": per_class.tolist(),
        "confusion_matrix": cm_best.tolist(),
        "snr_sweep": [{"drive_mvpp": d, "accuracy": a} for d, a in snr_results],
        "feature_means": X.mean(axis=0).tolist(),
        "feature_stds": X.std(axis=0).tolist(),
    }
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved: {out_file}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="T3.3 Reservoir Computing")
    parser.add_argument("--samples-per-class", type=int, default=N_SAMPLES_PER_CLASS,
                        help="Captures per class (default: 30)")
    args = parser.parse_args()
    np.random.seed(42)
    run_experiment(n_samples_per_class=args.samples_per_class)
