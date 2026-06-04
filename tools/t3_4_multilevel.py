#!/usr/bin/env python3
"""
T3.4 — Multi-Level Amplitude Encoding (Capacity Measurement)

Directly validates the paper's §11.5 claim: a glass plate supports
multi-level encoding per mode, with capacity scaling as L^M where
L = discriminable levels per mode and M = number of modes.

T3.1 proved L=2 (binary: ON/OFF) × M=4 → 16 patterns (4 bits).
T3.4 pushes to L=4,8,16 per mode, determining the plate's actual
information capacity per capture.

Why this works:
  - T3.1 showed SNR > 200× per mode (noise 400 vs signal 112k–261k)
  - Dynamic range permits 200+ distinguishable levels in theory
  - T3.2 showed phase stability σ < 0.28 rad → 2nd encoding axis
  - Sequential capture (drive mode, capture, repeat) avoids ringdown issues

Protocol:
  Phase A — Per-mode resolution: Drive one mode at N levels (10–500 mVpp),
            20 captures per level, find max L where accuracy > 95%
  Phase B — Full encoding: All 4 modes × L levels, sequential capture,
            classify L^4 patterns from concatenated amplitude features

Success Metric:
  > 90% accuracy at ≥ 16 patterns from single observation (≥ 4 bits)
  Stretch goal: 64+ patterns (6+ bits)

Hardware:
  Same signal chain as T3.1/T3.3:
  - PicoScope AWG → Board D (×3.69) → TX PZT (SW)
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V, AC coupled)

Usage:
  python tools/t3_4_multilevel.py [--levels 8] [--reps 20]
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

MODES_HZ = [35_840, 54_920, 57_037, 97_011]
SETTLE_MS = 30            # drive settle before capture (steady-state at ~1.2τ)
MIN_UVPP = 50_000         # 50 mVpp minimum (above noise)
MAX_UVPP = 500_000        # 500 mVpp maximum (full range)

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
    ps2000.ps2000_set_channel(handle, 0, 1, 0, RANGE_INDEX)  # AC coupled
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
    time.sleep(0.005)
    for _ in range(500):
        if ps2000.ps2000_ready(handle):
            break
        time.sleep(0.005)
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16(0)
    ps2000.ps2000_get_values(
        handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES, 0
    )
    return np.array(buf, dtype=np.float64) * (RANGE_MV / 32767.0)


def extract_mode_features(mv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extract FFT amplitude and phase at all mode frequencies."""
    ac = mv - mv.mean()
    window = np.hanning(N_SAMPLES)
    fft_c = np.fft.rfft(ac * window, n=N_SAMPLES * N_FFT_PAD)
    bin_width = SAMPLE_RATE_HZ / (N_SAMPLES * N_FFT_PAD)

    amps = np.zeros(len(MODES_HZ))
    phases = np.zeros(len(MODES_HZ))
    for i, freq in enumerate(MODES_HZ):
        bin_idx = int(round(freq / bin_width))
        lo = max(0, bin_idx - 3)
        hi = min(len(fft_c) - 1, bin_idx + 3)
        peak_bin = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
        amps[i] = np.abs(fft_c[peak_bin])
        phases[i] = np.angle(fft_c[peak_bin])
    return amps, phases


# ---------------------------------------------------------------------------
# Phase A: Per-mode amplitude resolution
# ---------------------------------------------------------------------------

def measure_resolution(handle, ps2000, n_levels: int, n_reps: int):
    """Measure how many amplitude levels are discriminable per mode."""
    levels_uvpp = np.linspace(MIN_UVPP, MAX_UVPP, n_levels).astype(int)
    levels_vpp = levels_uvpp / 1e6

    print(f"\n  Phase A: Per-Mode Amplitude Resolution")
    print(f"  Levels: {n_levels} ({MIN_UVPP/1e3:.0f}–{MAX_UVPP/1e3:.0f} mVpp)")
    print(f"  Reps per level: {n_reps}")
    print(f"  Total captures per mode: {n_levels * n_reps}")

    mode_results = {}

    for m_idx, freq in enumerate(MODES_HZ):
        print(f"\n    Mode {m_idx} ({freq} Hz):")
        amplitudes = np.zeros((n_levels, n_reps))
        phases_arr = np.zeros((n_levels, n_reps))

        for lev in range(n_levels):
            set_awg(handle, ps2000, freq, int(levels_uvpp[lev]))
            time.sleep(SETTLE_MS / 1000.0)

            for rep in range(n_reps):
                mv = capture_triggered(handle, ps2000)
                amps, phs = extract_mode_features(mv)
                amplitudes[lev, rep] = amps[m_idx]
                phases_arr[lev, rep] = phs[m_idx]

        # Statistics per level
        means = amplitudes.mean(axis=1)
        stds = amplitudes.std(axis=1)

        # Discrimination: minimum separation between adjacent levels
        separations = []
        for i in range(n_levels - 1):
            gap = means[i + 1] - means[i]
            noise = max(stds[i], stds[i + 1])
            separations.append(gap / noise if noise > 0 else float('inf'))

        min_sep_sigma = min(separations) if separations else 0
        mean_sep_sigma = np.mean(separations) if separations else 0

        # Ridge classification accuracy
        X = amplitudes.reshape(-1, 1)
        y = np.repeat(np.arange(n_levels), n_reps)

        # For single-feature ordered classes, use nearest-centroid (optimal)
        acc = _nearest_centroid_cv(amplitudes, n_levels, n_reps)

        # Also test with phase as additional feature (ridge works with 2+ features)
        X_ap = np.column_stack([amplitudes.reshape(-1, 1),
                                phases_arr.reshape(-1, 1)])
        acc_ap = _kfold_accuracy(X_ap, y, k=5)

        print(f"      Amplitude range: {means[0]:.0f} – {means[-1]:.0f}")
        print(f"      Mean σ per level: {stds.mean():.0f}")
        print(f"      Min adjacent separation: {min_sep_sigma:.1f}σ")
        print(f"      Mean adjacent separation: {mean_sep_sigma:.1f}σ")
        print(f"      Classification (amp only): {acc*100:.1f}%")
        print(f"      Classification (amp+phase): {acc_ap*100:.1f}%")

        mode_results[freq] = {
            "means": means.tolist(),
            "stds": stds.tolist(),
            "separations_sigma": separations,
            "min_separation_sigma": float(min_sep_sigma),
            "accuracy_amp": float(acc),
            "accuracy_amp_phase": float(acc_ap),
            "levels_vpp": levels_vpp.tolist(),
        }

    return mode_results


# ---------------------------------------------------------------------------
# Phase B: Full multi-level classification
# ---------------------------------------------------------------------------

def test_full_encoding(handle, ps2000, n_levels: int, n_reps: int):
    """Drive all 4 modes at assigned levels, classify L^4 patterns."""
    levels_uvpp = np.linspace(MIN_UVPP, MAX_UVPP, n_levels).astype(int)
    n_patterns = n_levels ** len(MODES_HZ)

    print(f"\n  Phase B: Full Multi-Level Encoding")
    print(f"  Levels per mode: {n_levels}")
    print(f"  Modes: {len(MODES_HZ)}")
    print(f"  Total patterns: {n_patterns}")
    print(f"  Reps per pattern: {n_reps}")
    print(f"  Total captures: {n_patterns * n_reps * len(MODES_HZ)}")

    # Generate all level combinations
    # Pattern i → [level_mode0, level_mode1, level_mode2, level_mode3]
    patterns = []
    for i in range(n_patterns):
        p = []
        val = i
        for _ in range(len(MODES_HZ)):
            p.append(val % n_levels)
            val //= n_levels
        patterns.append(p)

    # Collect data: for each pattern, drive each mode at its level, capture
    n_features = len(MODES_HZ)  # amplitude per mode
    X = np.zeros((n_patterns * n_reps, n_features))
    y = np.zeros(n_patterns * n_reps, dtype=int)

    total = n_patterns * n_reps
    sample_idx = 0

    # Randomize order to avoid drift effects
    order = []
    for pat_idx in range(n_patterns):
        for rep in range(n_reps):
            order.append((pat_idx, rep))
    rng = np.random.default_rng(42)
    rng.shuffle(order)

    print(f"  Collecting {total} observations...")

    for obs_num, (pat_idx, rep) in enumerate(order):
        pattern = patterns[pat_idx]
        features = np.zeros(n_features)

        for m_idx, freq in enumerate(MODES_HZ):
            uvpp = int(levels_uvpp[pattern[m_idx]])
            set_awg(handle, ps2000, freq, uvpp)
            time.sleep(SETTLE_MS / 1000.0)
            mv = capture_triggered(handle, ps2000)
            amps, _ = extract_mode_features(mv)
            features[m_idx] = amps[m_idx]

        X[sample_idx] = features
        y[sample_idx] = pat_idx
        sample_idx += 1

        if (obs_num + 1) % 50 == 0:
            print(f"    [{obs_num+1}/{total}]")

    # Classification
    acc = _kfold_accuracy(X, y, k=5)
    bits = np.log2(n_patterns)

    print(f"\n    Patterns: {n_patterns} ({bits:.1f} bits)")
    print(f"    Accuracy: {acc*100:.1f}%")

    return {
        "n_levels": n_levels,
        "n_modes": len(MODES_HZ),
        "n_patterns": n_patterns,
        "bits": float(bits),
        "accuracy": float(acc),
        "n_reps": n_reps,
        "n_observations": total,
    }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _nearest_centroid_cv(amplitudes: np.ndarray, n_levels: int, n_reps: int):
    """Leave-one-out nearest-centroid for ordered single-feature classes."""
    correct = 0
    total = 0
    for lev in range(n_levels):
        for rep in range(n_reps):
            test_val = amplitudes[lev, rep]
            # Compute centroids from all OTHER reps
            centroids = np.zeros(n_levels)
            for l2 in range(n_levels):
                if l2 == lev:
                    mask = np.ones(n_reps, dtype=bool)
                    mask[rep] = False
                    centroids[l2] = amplitudes[l2, mask].mean()
                else:
                    centroids[l2] = amplitudes[l2].mean()
            pred = np.argmin(np.abs(centroids - test_val))
            if pred == lev:
                correct += 1
            total += 1
    return correct / total


def _kfold_accuracy(X, y, k=5, alpha=1.0):
    """K-fold stratified cross-validation with ridge regression."""
    n = len(y)
    n_classes = int(y.max()) + 1

    # Create stratified folds
    indices = np.arange(n)
    rng = np.random.default_rng(123)
    rng.shuffle(indices)

    fold_size = n // k
    correct = 0
    total = 0

    for fold in range(k):
        test_idx = indices[fold * fold_size:(fold + 1) * fold_size]
        train_idx = np.concatenate([indices[:fold * fold_size],
                                    indices[(fold + 1) * fold_size:]])

        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Ridge regression on one-hot targets
        Y_train = np.zeros((len(y_train), n_classes))
        for i, c in enumerate(y_train):
            Y_train[i, c] = 1.0

        # Normalize
        mu = X_train.mean(axis=0)
        sigma = X_train.std(axis=0) + 1e-10
        X_tr_n = (X_train - mu) / sigma
        X_te_n = (X_test - mu) / sigma

        # Solve
        XtX = X_tr_n.T @ X_tr_n + alpha * np.eye(X_tr_n.shape[1])
        W = np.linalg.solve(XtX, X_tr_n.T @ Y_train)

        # Predict
        preds = np.argmax(X_te_n @ W, axis=1)
        correct += np.sum(preds == y_test)
        total += len(y_test)

    return correct / total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_t3_4(n_levels: int = 8, n_reps: int = 20):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print("T3.4 — Multi-Level Amplitude Encoding (Capacity Measurement)")
    print("=" * 70)
    print(f"  Modes: {MODES_HZ}")
    print(f"  Amplitude range: {MIN_UVPP/1e3:.0f}–{MAX_UVPP/1e3:.0f} mVpp")
    print(f"  Levels: {n_levels}")
    print(f"  Patterns: {n_levels}^{len(MODES_HZ)} = {n_levels**len(MODES_HZ)}")
    print(f"  Bits: {np.log2(n_levels**len(MODES_HZ)):.1f}")
    print(f"  Reps per condition: {n_reps}")
    print(f"  Settle time: {SETTLE_MS} ms")
    print("=" * 70)

    handle, ps2000 = open_scope()
    mux = RelayMux(port="/dev/cu.usbserial-11310", boot_wait=3.5)
    mux.open()
    mux.select(RELAY_CH)
    time.sleep(0.2)

    # Phase A: Per-mode resolution
    resolution = measure_resolution(handle, ps2000, n_levels, n_reps)

    # Determine achievable levels from Phase A
    min_acc = min(r["accuracy_amp"] for r in resolution.values())
    print(f"\n  Phase A Summary:")
    print(f"    Worst-mode accuracy at {n_levels} levels: {min_acc*100:.1f}%")

    # Phase B: Full encoding test
    # Use fewer levels if needed for tractability (L^4 patterns × reps × 4 modes)
    # Cap at 4 levels for Phase B (256 patterns × 5 reps × 4 modes = 5120 captures)
    phase_b_levels = min(n_levels, 4)
    phase_b_reps = min(n_reps, 5)
    n_patterns_b = phase_b_levels ** len(MODES_HZ)

    # Only run Phase B if pattern count is tractable (< 500 patterns)
    if n_patterns_b <= 256:
        encoding = test_full_encoding(handle, ps2000, phase_b_levels, phase_b_reps)
    else:
        print(f"\n  Phase B skipped: {n_patterns_b} patterns too many for sequential capture")
        encoding = None

    # Cleanup
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # --- Final summary ---
    # Extrapolate capacity from per-mode results
    per_mode_levels = []
    for freq, res in resolution.items():
        # Find max levels where separation > 3σ (conservative)
        seps = res["separations_sigma"]
        usable = sum(1 for s in seps if s >= 3.0) + 1  # levels = gaps + 1
        per_mode_levels.append(usable)

    conservative_levels = min(per_mode_levels)
    conservative_capacity = conservative_levels ** len(MODES_HZ)
    conservative_bits = np.log2(conservative_capacity) if conservative_capacity > 1 else 0

    print("\n" + "=" * 70)
    print("RESULTS — T3.4 Multi-Level Encoding")
    print("=" * 70)
    print(f"\n  Per-Mode Resolution (Phase A, {n_levels} levels tested):")
    print(f"    {'Mode (Hz)':<12} {'Accuracy':<12} {'Min Sep (σ)':<14} {'Usable Levels'}")
    print(f"    {'─'*12} {'─'*12} {'─'*14} {'─'*14}")
    for freq, res in resolution.items():
        seps = res["separations_sigma"]
        usable = sum(1 for s in seps if s >= 3.0) + 1
        print(f"    {freq:<12} {res['accuracy_amp']*100:<12.1f} "
              f"{res['min_separation_sigma']:<14.1f} {usable}")

    print(f"\n  Conservative capacity (3σ separation):")
    print(f"    Usable levels per mode: {conservative_levels}")
    print(f"    Total patterns: {conservative_levels}^{len(MODES_HZ)} = {conservative_capacity}")
    print(f"    Capacity: {conservative_bits:.1f} bits")

    if encoding:
        print(f"\n  Full Encoding Test (Phase B):")
        print(f"    Levels: {encoding['n_levels']}, Patterns: {encoding['n_patterns']}")
        print(f"    Accuracy: {encoding['accuracy']*100:.1f}%")
        gate = "PASS" if encoding['accuracy'] >= 0.90 else "FAIL"
        print(f"\n  ★ T3.4 GATE: {gate} — {encoding['bits']:.1f} bits at "
              f"{encoding['accuracy']*100:.1f}% accuracy")
    else:
        gate = "PASS" if conservative_bits >= 4.0 else "FAIL"
        print(f"\n  ★ T3.4 GATE: {gate} — {conservative_bits:.1f} bits "
              f"(extrapolated from per-mode resolution)")

    # Save results
    out_dir = Path("data/results/multilevel")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"t3_4_multilevel_{ts}.json"
    results = {
        "experiment": "T3.4",
        "timestamp": ts,
        "gate_decision": gate,
        "n_levels_tested": n_levels,
        "n_reps": n_reps,
        "modes_hz": MODES_HZ,
        "min_uvpp": MIN_UVPP,
        "max_uvpp": MAX_UVPP,
        "settle_ms": SETTLE_MS,
        "per_mode_resolution": resolution,
        "conservative_levels_per_mode": conservative_levels,
        "conservative_capacity_patterns": conservative_capacity,
        "conservative_capacity_bits": float(conservative_bits),
        "phase_b": encoding,
    }
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="T3.4 Multi-Level Encoding")
    parser.add_argument("--levels", type=int, default=8,
                        help="Number of amplitude levels to test per mode (default: 8)")
    parser.add_argument("--reps", type=int, default=20,
                        help="Repetitions per level (default: 20)")
    args = parser.parse_args()
    run_t3_4(n_levels=args.levels, n_reps=args.reps)
