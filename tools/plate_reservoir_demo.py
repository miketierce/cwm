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
from itertools import combinations
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


def _measure_cross_spectrum(handle, drive_freq_hz: float,
                            readout_freqs: list[float],
                            drive_uvpp: int = AWG_DRIVE_UVPP,
                            wave_type: int = 0) -> np.ndarray:
    """Drive AWG at drive_freq_hz, return magnitudes at all readout frequencies.

    Single drive frequency, broadband FFT readout — the cross-frequency
    coupling IS the reservoir's nonlinear feature map.
    wave_type: 0=sine, 1=square (adds odd harmonics), 2=triangle
    """
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, drive_uvpp, wave_type,
        float(drive_freq_hz), float(drive_freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)

    spectra = []
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

            mags = np.zeros(len(readout_freqs))
            for j, rf in enumerate(readout_freqs):
                tb = int(round(rf / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(fft) - 1, tb + 3)
                mags[j] = float(np.max(fft[lo:hi + 1]))
            spectra.append(mags)

    if spectra:
        return np.mean(spectra, axis=0)
    return np.zeros(len(readout_freqs))


def _interaction_expand(x, max_degree=4):
    """Interaction-only polynomial expansion up to max_degree.

    For n features: sum_{d=1}^{max_degree} C(n,d) terms.
    For n=4, max_degree=4: 4+6+4+1 = 15 terms.
    The degree-4 term x0*x1*x2*x3 is exactly the parity indicator.
    """
    n = len(x)
    terms = list(x)  # degree 1
    for d in range(2, max_degree + 1):
        for combo in combinations(range(n), d):
            t = 1.0
            for idx in combo:
                t *= x[idx]
            terms.append(t)
    return np.array(terms)


def _drive_multitone_capture(handle, active_freqs_hz, readout_freqs_hz,
                             drive_uvpp=AWG_DRIVE_UVPP):
    """Drive multiple frequencies simultaneously via ARB waveform.

    Builds an arbitrary waveform summing all active frequencies, uploads
    to the PicoScope AWG, captures broadband FFT, and returns magnitudes
    at each readout frequency.  Simultaneous multi-tone drive creates
    genuine intermodulation products at the PZT transducer.
    """
    from picosdk.ps2000 import ps2000

    if not active_freqs_hz:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
        time.sleep(SETTLE_S)
    else:
        arb_len = 4096
        max_freq = max(active_freqs_hz)
        f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))
        delta_phase = int(f_rep * (2**32) / 48_000_000)
        if delta_phase < 1:
            delta_phase = 1

        buf_signal = np.zeros(arb_len, dtype=np.float64)
        for f_target in active_freqs_hz:
            k = round(f_target / f_rep)
            if k < 1 or k > arb_len // 2:
                continue
            phase = 2 * np.pi * k * np.arange(arb_len) / arb_len
            buf_signal += np.sin(phase)

        peak = np.max(np.abs(buf_signal))
        if peak > 0:
            buf_signal /= peak
        arb_u8 = ((buf_signal * 127) + 128).clip(0, 255).astype(np.uint8)
        arb_buf = (ctypes.c_uint8 * arb_len)(*arb_u8.tolist())

        ps2000.ps2000_set_sig_gen_arbitrary(
            handle, 0, drive_uvpp,
            delta_phase, delta_phase,
            0, 0,
            arb_buf, arb_len, 0, 0
        )
        time.sleep(SETTLE_S)

    spectra = []
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
            mags = np.zeros(len(readout_freqs_hz))
            for j, rf in enumerate(readout_freqs_hz):
                tb = int(round(rf / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(fft) - 1, tb + 3)
                mags[j] = float(np.max(fft[lo:hi + 1]))
            spectra.append(mags)

    if spectra:
        return np.mean(spectra, axis=0)
    return np.zeros(len(readout_freqs_hz))


def _build_readout_grid(mode_freqs, input_indices):
    """Build extended readout frequency grid with intermod frequencies.

    Returns (readout_freqs, diag_indices) where diag_indices maps each
    input bit to its position in the readout grid.
    """
    nyquist = SAMPLE_RATE / 2
    readout_set = set()

    for f in mode_freqs:
        readout_set.add(f)

    input_freqs = [mode_freqs[i] for i in input_indices]
    for f in input_freqs:
        h2 = 2 * f
        if h2 < nyquist * 0.9:
            readout_set.add(h2)

    for i in range(len(input_freqs)):
        for j in range(i + 1, len(input_freqs)):
            s = input_freqs[i] + input_freqs[j]
            d = abs(input_freqs[i] - input_freqs[j])
            if s < nyquist * 0.9:
                readout_set.add(s)
            if d > 100:
                readout_set.add(d)

    readout_freqs = sorted(readout_set)
    diag_indices = [readout_freqs.index(mode_freqs[idx]) for idx in input_indices]
    return readout_freqs, diag_indices


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

def _capture_response(handle, pattern: np.ndarray,
                      mode_freqs: list[float],
                      n_input_bits: int,
                      readout_freqs: list[float] = None,
                      capture_mode: str = "sequential",
                      wave_type: int = 0) -> np.ndarray:
    """Reservoir feature capture with multiple drive strategies.

    capture_mode:
      "sequential" — drive each active bit separately, capture cross-spectrum
      "multitone"  — drive all active bits simultaneously via ARB waveform
    wave_type: 0=sine, 1=square (sequential mode only)

    Returns flat feature vector.
    """
    n_modes = len(mode_freqs)
    input_indices = np.linspace(0, n_modes - 1, n_input_bits, dtype=int)
    rf = readout_freqs if readout_freqs is not None else mode_freqs
    n_readout = len(rf)

    if capture_mode == "multitone":
        active_freqs = [mode_freqs[input_indices[b]]
                        for b in range(n_input_bits) if pattern[b] > 0]
        features = _drive_multitone_capture(handle, active_freqs, rf)
        return features
    else:
        features = np.zeros(n_input_bits * n_readout)
        for bit_idx in range(n_input_bits):
            if pattern[bit_idx] > 0:
                mode_idx = input_indices[bit_idx]
                drive_freq = mode_freqs[mode_idx]
                cross = _measure_cross_spectrum(handle, drive_freq, rf,
                                                wave_type=wave_type)
                features[bit_idx * n_readout:(bit_idx + 1) * n_readout] = cross
        return features


def run_reservoir_demo(handle, mux, plate_id: str,
                       n_input_bits: int = 4,
                       n_train: int = 40,
                       n_test: int = 20,
                       seed: int = 42,
                       capture_mode: str = "sequential",
                       wave_type: int = 0) -> dict:
    """Run the full reservoir computing demo on one plate.

    Evaluates multiple tasks and feature strategies:
      - Parity classification with raw, polynomial, and combined features
      - Majority classification for comparison
    """
    name = PLATE_NAMES.get(plate_id, plate_id)
    mode_label = capture_mode if capture_mode == "multitone" else \
        f"{'square' if wave_type == 1 else 'sine'}"
    print(f"\n{'=' * 65}")
    print(f"  RESERVOIR DEMO v4 — Plate {name} ({mode_label})")
    print(f"  Task: {n_input_bits}-bit parity + majority")
    print(f"  Train: {n_train}, Test: {n_test}")
    print(f"{'=' * 65}")

    mode_freqs = _load_plate_modes(plate_id)
    n_modes = len(mode_freqs)
    n_input_bits = min(n_input_bits, n_modes)
    input_indices = np.linspace(0, n_modes - 1, n_input_bits, dtype=int)
    print(f"  Plate {name}: {n_modes} enrolled modes")

    # Build extended readout grid (enrolled + harmonics + intermod)
    readout_freqs, diag_in_readout = _build_readout_grid(
        mode_freqs, input_indices)
    n_readout = len(readout_freqs)

    if capture_mode == "multitone":
        feature_dim = n_readout
        dim_desc = f"{n_readout} readout freqs"
    else:
        feature_dim = n_input_bits * n_readout
        dim_desc = f"{n_input_bits} drives × {n_readout} readouts"

    print(f"  Input bits: {n_input_bits} | Readout grid: {n_readout} frequencies")
    print(f"  Raw feature dim: {feature_dim} ({dim_desc})")
    print(f"  Readout includes harmonics & intermod products")

    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    # Generate exhaustive balanced patterns
    rng = np.random.default_rng(seed)
    n_patterns = 2 ** n_input_bits
    all_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_input_bits)] for i in range(n_patterns)])
    all_parity = np.sum(all_patterns, axis=1) % 2
    all_majority = (np.sum(all_patterns, axis=1) > n_input_bits / 2).astype(int)

    n_per_train = max(1, n_train // n_patterns)
    n_per_test = max(1, n_test // n_patterns)
    train_indices = np.repeat(np.arange(n_patterns), n_per_train)
    test_indices = np.repeat(np.arange(n_patterns), n_per_test)
    rng.shuffle(train_indices)
    rng.shuffle(test_indices)
    n_train = len(train_indices)
    n_test = len(test_indices)
    total = n_train + n_test
    patterns = np.concatenate([all_patterns[train_indices],
                               all_patterns[test_indices]])
    y_parity = np.concatenate([all_parity[train_indices],
                               all_parity[test_indices]])
    y_majority = np.concatenate([all_majority[train_indices],
                                 all_majority[test_indices]])
    print(f"  Balanced: {n_per_train}× train + {n_per_test}× test per pattern")

    # ── Physical forward pass ──
    print(f"\n  Capturing {total} responses ({mode_label})...")
    X_features = np.zeros((total, feature_dim))
    t0 = time.time()

    for i in range(total):
        response = _capture_response(handle, patterns[i], mode_freqs,
                                     n_input_bits, readout_freqs,
                                     capture_mode, wave_type)
        X_features[i] = response

        if (i + 1) % 10 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (total - i - 1) / rate
            print(f"    [{i + 1}/{total}] {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

    capture_time = time.time() - t0
    print(f"  Captured {total} in {capture_time:.1f}s "
          f"({capture_time / total:.2f}s/pattern)")

    X_features = np.log1p(X_features)

    # Split
    X_train_raw = X_features[:n_train]
    X_test_raw = X_features[n_train:]

    # Standardize raw features
    mu = X_train_raw.mean(axis=0)
    sigma = X_train_raw.std(axis=0) + 1e-8
    X_train_raw = (X_train_raw - mu) / sigma
    X_test_raw = (X_test_raw - mu) / sigma

    # ── Diagonal features (encode "is bit on?") ──
    if capture_mode == "multitone":
        diag_idx = diag_in_readout
    else:
        diag_idx = [bit_idx * n_readout + diag_in_readout[bit_idx]
                    for bit_idx in range(n_input_bits)]

    X_train_diag = X_train_raw[:, diag_idx]
    X_test_diag = X_test_raw[:, diag_idx]

    # Diagnostic: ON vs OFF separation
    on_vals, off_vals = [], []
    for i in range(n_train):
        for b in range(n_input_bits):
            if patterns[i, b] > 0:
                on_vals.append(X_train_diag[i, b])
            else:
                off_vals.append(X_train_diag[i, b])
    if on_vals and off_vals:
        on_m, off_m = np.mean(on_vals), np.mean(off_vals)
        on_s, off_s = np.std(on_vals), np.std(off_vals)
        sep = abs(on_m - off_m) / (on_s + off_s + 1e-8)
        print(f"\n  Diagonal ON/OFF: ON={on_m:.2f}±{on_s:.2f}, "
              f"OFF={off_m:.2f}±{off_s:.2f}")
        print(f"  Separation index: {sep:.2f} (>1 good, >2 excellent)")

    # ── Polynomial expansion of diagonal features ──
    poly_degree = min(4, n_input_bits)
    X_train_poly = np.array([_interaction_expand(row, poly_degree)
                             for row in X_train_diag])
    X_test_poly = np.array([_interaction_expand(row, poly_degree)
                            for row in X_test_diag])
    poly_dim = X_train_poly.shape[1]
    print(f"  Polynomial: degree-{poly_degree} on {n_input_bits} diag "
          f"→ {poly_dim} terms")

    # Combined: raw + polynomial
    X_train_comb = np.column_stack([X_train_raw, X_train_poly])
    X_test_comb = np.column_stack([X_test_raw, X_test_poly])

    # ── Multi-task Ridge regression ──
    alpha = 1.0
    print(f"\n  Training Ridge readouts (α={alpha})...")

    def _ridge_eval(X_tr, X_te, y_tr, y_te, n_classes=2):
        Xb_tr = np.column_stack([X_tr, np.ones(len(y_tr))])
        Xb_te = np.column_stack([X_te, np.ones(len(y_te))])
        d = Xb_tr.shape[1]
        Y_oh = np.zeros((len(y_tr), n_classes))
        for i, lbl in enumerate(y_tr):
            Y_oh[i, lbl] = 1.0
        W = np.linalg.solve(Xb_tr.T @ Xb_tr + alpha * np.eye(d),
                            Xb_tr.T @ Y_oh)
        tr_acc = float(np.mean(np.argmax(Xb_tr @ W, axis=1) == y_tr))
        te_acc = float(np.mean(np.argmax(Xb_te @ W, axis=1) == y_te))
        return tr_acc, te_acc, W.size

    y_tr_p = y_parity[:n_train]
    y_te_p = y_parity[n_train:]
    y_tr_m = y_majority[:n_train]
    y_te_m = y_majority[n_train:]

    tasks = {}
    task_list = [
        ("parity_raw", X_train_raw, X_test_raw, y_tr_p, y_te_p),
        ("parity_poly", X_train_poly, X_test_poly, y_tr_p, y_te_p),
        ("parity_combined", X_train_comb, X_test_comb, y_tr_p, y_te_p),
        ("majority_raw", X_train_raw, X_test_raw, y_tr_m, y_te_m),
        ("majority_poly", X_train_poly, X_test_poly, y_tr_m, y_te_m),
    ]

    for tname, X_tr, X_te, y_tr, y_te in task_list:
        tr, te, nw = _ridge_eval(X_tr, X_te, y_tr, y_te)
        tasks[tname] = {"train": tr, "test": te, "n_weights": nw}

    # ── Print results ──
    feat_sizes = {"raw": feature_dim, "poly": poly_dim,
                  "combined": feature_dim + poly_dim}
    print(f"\n  ── Results: Plate {name} ({mode_label}) ──")
    print(f"  {'Task':<22} {'Feat':>5} {'Train':>7} {'Test':>7}")
    print(f"  {'-' * 44}")
    for tname, info in tasks.items():
        feat_key = tname.split("_", 1)[1]
        nf = feat_sizes.get(feat_key, "?")
        print(f"  {tname:<22} {nf:>5} {info['train']:>6.1%} {info['test']:>6.1%}")
    print(f"  Capture time: {capture_time:.1f}s")

    mux.off()

    best_parity = max(tasks[k]["test"] for k in tasks if k.startswith("parity"))
    best_majority = max(tasks[k]["test"] for k in tasks if k.startswith("majority"))

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate_name": name,
        "plate_id": plate_id,
        "capture_mode": mode_label,
        "n_modes": n_modes,
        "n_input_bits": n_input_bits,
        "n_readout_freqs": n_readout,
        "n_train": n_train,
        "n_test": n_test,
        "tasks": {k: {"train_pct": round(v["train"] * 100, 1),
                       "test_pct": round(v["test"] * 100, 1),
                       "n_weights": v["n_weights"]}
                  for k, v in tasks.items()},
        "best_parity_test_pct": round(best_parity * 100, 1),
        "best_majority_test_pct": round(best_majority * 100, 1),
        "train_accuracy_pct": round(tasks["parity_combined"]["train"] * 100, 1),
        "test_accuracy_pct": round(best_parity * 100, 1),
        "trainable_params": tasks["parity_combined"]["n_weights"],
        "capture_time_s": round(capture_time, 1),
        "mode_freqs_hz": mode_freqs[:10],
        "readout_freqs_hz": readout_freqs[:20],
        "feature_dim_raw": feature_dim,
        "poly_dim": poly_dim,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Plate reservoir computing demo (v4 — polynomial + multitone)"
    )
    parser.add_argument(
        "--plate", type=str, default="5",
        help="Plate relay ID (1-5, default: 5 = Plate E)"
    )
    parser.add_argument(
        "--all-plates", action="store_true",
        help="Run on all 5 plates sequentially"
    )
    parser.add_argument(
        "--n-bits", type=int, default=4,
        help="Number of input bits (default: 4)"
    )
    parser.add_argument(
        "--n-train", type=int, default=80,
        help="Training samples (default: 80)"
    )
    parser.add_argument(
        "--n-test", type=int, default=20,
        help="Test samples (default: 20)"
    )
    parser.add_argument(
        "--mode", type=str, default="sequential",
        choices=["sequential", "multitone"],
        help="Capture mode: sequential (one tone at a time) or multitone (ARB)"
    )
    parser.add_argument(
        "--wave", type=int, default=0, choices=[0, 1, 2],
        help="Wave type for sequential mode: 0=sine, 1=square, 2=triangle"
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

    plate_ids = sorted(PLATE_NAMES.keys()) if args.all_plates else [args.plate]

    handle = _open_scope()
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {mux.port}")

    results = []
    try:
        for pid in plate_ids:
            result = run_reservoir_demo(
                handle, mux, pid,
                n_input_bits=args.n_bits,
                n_train=args.n_train,
                n_test=args.n_test,
                capture_mode=args.mode,
                wave_type=args.wave,
            )
            results.append(result)
    finally:
        _close_scope(handle)
        mux.close()

    LAB_DIR.mkdir(parents=True, exist_ok=True)
    token = None

    for result in results:
        name = result["plate_name"]
        mode_label = result["capture_mode"]

        save_path = LAB_DIR / f"reservoir_demo_{name}_{TIMESTAMP}.json"
        with open(save_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Saved: {save_path}")

        if not args.dry_run:
            print("  Submitting to Firestore...")
            try:
                if token is None:
                    token = firebase_anon_auth()
                data = {
                    "plate_name": result["plate_name"],
                    "n_modes": result["n_modes"],
                    "n_input_bits": result["n_input_bits"],
                    "n_train": result["n_train"],
                    "n_test": result["n_test"],
                    "train_accuracy": result["train_accuracy_pct"],
                    "test_accuracy": result["test_accuracy_pct"],
                    "trainable_params": result["trainable_params"],
                    "capture_time_s": result["capture_time_s"],
                }
                notes = (
                    f"Reservoir v4 ({mode_label}+poly): Plate {name}, "
                    f"best parity {result['best_parity_test_pct']:.1f}%, "
                    f"majority {result['best_majority_test_pct']:.1f}%."
                )
                r = submit_experiment(token, "exp-reservoir-demo", data, notes=notes)
                print_result(r)
            except Exception as e:
                print(f"  ✗ Submission failed: {e}")

    if len(results) > 1:
        print(f"\n{'=' * 65}")
        print(f"  SUMMARY — RESERVOIR DEMO v4")
        print(f"{'=' * 65}")
        print(f"  {'Plate':<8} {'Mode':<12} {'Parity':>8} {'Majority':>10}")
        print(f"  {'-' * 40}")
        for r in results:
            print(f"  {r['plate_name']:<8} {r['capture_mode']:<12} "
                  f"{r['best_parity_test_pct']:>7.1f}% "
                  f"{r['best_majority_test_pct']:>9.1f}%")
        par_accs = [r['best_parity_test_pct'] for r in results]
        maj_accs = [r['best_majority_test_pct'] for r in results]
        print(f"  {'Mean':<8} {'':<12} "
              f"{sum(par_accs)/len(par_accs):>7.1f}% "
              f"{sum(maj_accs)/len(maj_accs):>9.1f}%")

        combined_path = LAB_DIR / f"reservoir_demo_all_{TIMESTAMP}.json"
        with open(combined_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"  Combined: {combined_path}")


if __name__ == "__main__":
    main()
