#!/usr/bin/env python3
"""
Plate Reservoir Computing Demo — Physical Neural Forward Pass

Demonstrates that a fused-silica plate acts as a reservoir computer:
  1. Drive plate with multi-tone input patterns (encoding binary vectors)
  2. Capture spectral response at enrolled mode frequencies
  3. Train a linear readout layer (least-squares) on captured data
  4. Classify held-out patterns using physical plate response

This is the hardware companion to experiments/exp09_reservoir_classify.py.

Architecture:
  - Plate physics  = hidden layer (fixed, ~31 modes)
  - Readout weights = output layer (trainable, ~31 params)
  - Laptop/Python   = firmware emulator (what CMOS readout die does in MEMS)

Usage:
  PYTHONPATH=. python tools/plate_reservoir_demo.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_reservoir_demo.py --plate 5 --n-bits 4
  PYTHONPATH=. python tools/plate_reservoir_demo.py --dry-run
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

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import cwm_picoscope  # noqa: F401
from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux
from firestore_submit import firebase_anon_auth, submit_experiment, print_result

# ── Configuration ─────────────────────────────────────────────────────

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_FILE = LAB_DIR / f"reservoir_demo_{TIMESTAMP}.json"

PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

N_AVG = 8            # averages per measurement
SETTLE_S = 0.15      # settle time for AWG
SETTLE_RELAY_S = 0.10
DWELL_PER_TONE_S = 0.05  # dwell time per tone in multi-tone sequence


# ── Scope helpers ─────────────────────────────────────────────────────

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    print("  PicoScope opened (Ch A ±1V DC)")
    return handle


def _close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("  PicoScope closed")


def _measure_at(handle, freq_hz: float,
                drive_uvpp: int = AWG_DRIVE_UVPP) -> float:
    """Drive AWG at freq_hz, return magnitude."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, drive_uvpp, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)

    magnitudes = []
    for _ in range(N_AVG):
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
        t_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.002)
            if time.time() - t0 > 2:
                break
        buf_a = (ctypes.c_int16 * N_SAMPLES)()
        buf_b = (ctypes.c_int16 * N_SAMPLES)()
        overflow = ctypes.c_int16()
        n = ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES
        )
        if n > 0:
            raw = np.array(buf_a[:n], dtype=np.float64)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            tb = int(round(freq_hz / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft) - 1, tb + 3)
            magnitudes.append(float(np.max(fft[lo:hi + 1])))

    return float(np.mean(magnitudes)) if magnitudes else 0.0


# ── Enrollment loader ────────────────────────────────────────────────

def _load_plate_modes(plate_id: str) -> list[float]:
    """Load enrolled mode frequencies from latest census."""
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        raise FileNotFoundError("No census file. Run plate_mode_census.py first.")
    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]
    if plate_id not in census or not census[plate_id].get("peaks"):
        raise ValueError(f"Plate {plate_id} not found in census")
    return [p["freq_hz"] for p in census[plate_id]["peaks"]]


# ── Reservoir protocol ────────────────────────────────────────────────

def _encode_pattern(pattern: np.ndarray, mode_freqs: list[float],
                    n_input_bits: int) -> list[tuple[float, int]]:
    """Map binary pattern to (frequency, drive_amplitude) pairs.

    Each bit corresponds to a mode frequency.  Bit ON = drive at full
    amplitude, bit OFF = no drive.

    Returns list of (freq_hz, drive_uvpp) for active tones.
    """
    # Select input mode indices evenly spaced across available modes
    n_modes = len(mode_freqs)
    input_indices = np.linspace(0, n_modes - 1, n_input_bits, dtype=int)

    tones = []
    for bit_idx, mode_idx in enumerate(input_indices):
        if pattern[bit_idx] > 0:
            tones.append((mode_freqs[mode_idx], AWG_DRIVE_UVPP))
    return tones


def _capture_response(handle, tones: list[tuple[float, int]],
                      readout_freqs: list[float]) -> np.ndarray:
    """Drive plate with a pattern (sequential tone excitation) and
    measure the spectral response at all readout frequencies.

    The PicoScope AWG can only drive one frequency at a time, so we
    drive each tone sequentially and capture the response.  The plate's
    ringdown time (~ms) means previous tones still contribute to the
    response, simulating superposition.
    """
    # Drive each active tone
    for freq_hz, drive_uv in tones:
        from picosdk.ps2000 import ps2000
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, drive_uv, 0,
            float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
        )
        time.sleep(DWELL_PER_TONE_S)

    # Now capture response at all readout frequencies
    # AWG off — measure the ringdown/residual response
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    time.sleep(0.02)  # brief settle

    # Alternative: measure AT each readout frequency with CW drive
    # This captures the plate's transfer function response
    response = np.zeros(len(readout_freqs))
    for i, freq in enumerate(readout_freqs):
        response[i] = _measure_at(handle, freq)

    return response


def run_reservoir_demo(handle, mux, plate_id: str,
                       n_input_bits: int = 4,
                       n_train: int = 40,
                       n_test: int = 20,
                       seed: int = 42) -> dict:
    """Run the full reservoir computing demo on one plate.

    Task: parity classification (XOR generalization).
    """
    name = PLATE_NAMES.get(plate_id, plate_id)
    print(f"\n{'=' * 65}")
    print(f"  RESERVOIR COMPUTING DEMO — Plate {name}")
    print(f"  Task: {n_input_bits}-bit parity classification")
    print(f"  Train: {n_train}, Test: {n_test}")
    print(f"{'=' * 65}")

    # Load plate modes
    mode_freqs = _load_plate_modes(plate_id)
    n_modes = len(mode_freqs)
    print(f"  Plate {name}: {n_modes} enrolled modes")
    print(f"  Input bits: {n_input_bits} (mapped to {n_input_bits} mode frequencies)")
    print(f"  Readout dimension: {n_modes}")

    # Select relay
    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    # Generate all patterns
    rng = np.random.default_rng(seed)
    n_patterns = 2 ** n_input_bits
    all_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_input_bits)] for i in range(n_patterns)]
    )
    all_labels = np.sum(all_patterns, axis=1) % 2  # parity

    # Sample train + test sets
    total = n_train + n_test
    indices = rng.choice(n_patterns, total, replace=True)
    patterns = all_patterns[indices]
    labels = all_labels[indices]

    # ── Physical forward pass ──
    print(f"\n  Capturing {total} spectral responses...")
    X_features = np.zeros((total, n_modes))
    t0 = time.time()

    for i in range(total):
        tones = _encode_pattern(patterns[i], mode_freqs, n_input_bits)
        response = _capture_response(handle, tones, mode_freqs)
        X_features[i] = response

        if (i + 1) % 10 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (total - i - 1) / rate
            print(f"    [{i + 1}/{total}] {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

    capture_time = time.time() - t0
    print(f"  Captured {total} responses in {capture_time:.1f}s "
          f"({capture_time / total:.2f}s per pattern)")

    # Split
    X_train = X_features[:n_train]
    X_test = X_features[n_train:]
    y_train = labels[:n_train]
    y_test = labels[n_train:]

    # ── Train linear readout ──
    print(f"\n  Training linear readout ({n_modes + 1} weights)...")
    n_classes = 2
    Y_onehot = np.zeros((n_train, n_classes))
    for i, label in enumerate(y_train):
        Y_onehot[i, label] = 1.0

    X_bias = np.column_stack([X_train, np.ones(n_train)])
    W, residuals, rank, sv = np.linalg.lstsq(X_bias, Y_onehot, rcond=None)

    # ── Evaluate ──
    X_test_bias = np.column_stack([X_test, np.ones(n_test)])
    pred_train = np.argmax(X_bias @ W, axis=1)
    pred_test = np.argmax(X_test_bias @ W, axis=1)

    train_acc = float(np.mean(pred_train == y_train))
    test_acc = float(np.mean(pred_test == y_test))

    # Confusion matrix
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for true, pred in zip(y_test, pred_test):
        cm[true, pred] += 1

    print(f"\n  ── Results ──")
    print(f"  Train accuracy: {train_acc:.1%}")
    print(f"  Test accuracy:  {test_acc:.1%}")
    print(f"  Confusion matrix:")
    print(f"    Pred→   Even  Odd")
    print(f"    Even   {cm[0, 0]:5d}  {cm[0, 1]:4d}")
    print(f"    Odd    {cm[1, 0]:5d}  {cm[1, 1]:4d}")
    print(f"  Readout weights: {W.shape} matrix")
    print(f"  Trainable parameters: {W.size}")
    print(f"  Physics forward pass: plate does {n_modes}-dim feature extraction")

    mux.off()

    return {
        "plate_name": name,
        "plate_id": plate_id,
        "n_modes": n_modes,
        "n_input_bits": n_input_bits,
        "n_train": n_train,
        "n_test": n_test,
        "train_accuracy": round(train_acc, 4),
        "test_accuracy": round(test_acc, 4),
        "confusion_matrix": cm.tolist(),
        "readout_weights_shape": list(W.shape),
        "trainable_params": W.size,
        "capture_time_s": round(capture_time, 1),
        "mode_freqs_hz": mode_freqs[:10],  # top 10 for reference
    }


def main():
    parser = argparse.ArgumentParser(
        description="Plate reservoir computing demo"
    )
    parser.add_argument(
        "--plate", type=str, default="5",
        help="Plate relay ID (1-5, default: 5 = Plate E)"
    )
    parser.add_argument(
        "--n-bits", type=int, default=4,
        help="Number of input bits (default: 4)"
    )
    parser.add_argument(
        "--n-train", type=int, default=40,
        help="Training samples (default: 40)"
    )
    parser.add_argument(
        "--n-test", type=int, default=20,
        help="Test samples (default: 20)"
    )
    parser.add_argument(
        "--port", type=str, default="/dev/cu.usbserial-11310",
        help="Serial port for relay mux"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Don't submit to Firestore"
    )
    args = parser.parse_args()

    handle = _open_scope()
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {mux.port}")

    try:
        result = run_reservoir_demo(
            handle, mux, args.plate,
            n_input_bits=args.n_bits,
            n_train=args.n_train,
            n_test=args.n_test,
        )
    finally:
        _close_scope(handle)
        mux.close()

    # Submit to Firestore
    if not args.dry_run:
        print("\nSubmitting to Firestore...")
        try:
            token = firebase_anon_auth()
            data = {
                "plate_name": result["plate_name"],
                "n_modes": result["n_modes"],
                "n_input_bits": result["n_input_bits"],
                "n_train": result["n_train"],
                "n_test": result["n_test"],
                "train_accuracy": result["train_accuracy"],
                "test_accuracy": result["test_accuracy"],
                "trainable_params": result["trainable_params"],
                "capture_time_s": result["capture_time_s"],
            }
            notes = (
                f"Reservoir demo: Plate {result['plate_name']}, "
                f"{result['n_input_bits']}-bit parity, "
                f"test acc {result['test_accuracy']:.1%}, "
                f"{result['trainable_params']} trainable params."
            )
            r = submit_experiment(token, "exp-reservoir-demo", data, notes=notes)
            print_result(r)
        except Exception as e:
            print(f"  ✗ Submission failed: {e}")
    else:
        print("\n  [DRY RUN] Would submit reservoir demo result")

    # Save locally
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Saved: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
