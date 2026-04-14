#!/usr/bin/env python3
"""
Plate Pulsed Memory — Ringdown-Based Temporal Encoding

CRITICAL HARDWARE FACT: The AWG drives ALL 5 plates in parallel.
The relay mux only selects which plate's SENSE PZT connects to Ch A.
This means every plate accumulates every drive pattern — we just
choose which one to listen to.

Three test modes:

  Test A — Same-plate pulsed ringdown:
    Drive pattern → AWG off → read same plate's free ringdown.
    The decaying spectrum encodes the pattern without CW interference.

  Test B — Cross-plate ringdown:
    Drive pattern (all plates excited) → AWG off → switch mux → read
    DIFFERENT plate's ringdown. That plate was "silently" accumulating
    the drive through its own mode structure the whole time.

  Test C — Cross-plate live (known-sequence inference):
    Drive pattern (all plates excited), read Plate X → keep driving,
    switch mux to Plate Y → Y's spectrum = same drive filtered through
    different modes. Transient encodes when mux switched (history).

If Test A succeeds: ringdown IS memory (same plate).
If Test B succeeds: plates can "remember for each other" — multi-plate
    temporal pipeline becomes possible.
If Test C succeeds: plate identity encodes routing history — the
    "if I'm Plate 2, I must have come from Plate 3" idea.

Usage:
  PYTHONPATH=. python tools/plate_pulsed_memory.py --test A --all-plates
  PYTHONPATH=. python tools/plate_pulsed_memory.py --test B --drive-plate 3 --read-plate 4
  PYTHONPATH=. python tools/plate_pulsed_memory.py --test C --all-plates
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

PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

N_AVG = 4             # FFT averages per capture
T_EXCITE_S = 0.30     # drive time before cut/switch (let modes build up)
SETTLE_RELAY_S = 0.10 # relay settle after mux switch
N_PATTERNS = 60       # patterns per test

# Ringdown capture delays (ms after AWG off) for Test A/B
RINGDOWN_DELAYS_MS = [1, 5, 10, 20, 50]


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


def _awg_off(handle):
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )


def _drive_multitone_arb(handle, freqs_hz, amplitudes, fixed_f_rep,
                         drive_uvpp=AWG_DRIVE_UVPP):
    """Drive multiple frequencies via ARB with fixed frequency grid."""
    from picosdk.ps2000 import ps2000

    if not freqs_hz:
        _awg_off(handle)
        return

    arb_len = 4096
    delta_phase = int(fixed_f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    buf_signal = np.zeros(arb_len, dtype=np.float64)
    for f_target, amp in zip(freqs_hz, amplitudes):
        k = round(f_target / fixed_f_rep)
        if k < 1 or k > arb_len // 2:
            continue
        phase = 2 * np.pi * k * np.arange(arb_len) / arb_len
        buf_signal += amp * np.sin(phase)

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


def _capture_spectrum(handle, readout_freqs, n_avg=N_AVG):
    """Capture n_avg FFTs and return mean magnitudes at readout frequencies."""
    from picosdk.ps2000 import ps2000

    all_mags = []
    for _ in range(n_avg):
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
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]

            mags = np.zeros(len(readout_freqs))
            for j, f in enumerate(readout_freqs):
                tb = int(round(f / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(fft_mag) - 1, tb + 3)
                mags[j] = float(np.max(fft_mag[lo:hi + 1]))
            all_mags.append(mags)

    if all_mags:
        return np.mean(all_mags, axis=0)
    return np.zeros(len(readout_freqs))


def _interaction_expand(x, max_degree=4):
    """Interaction-only polynomial expansion."""
    n = len(x)
    terms = list(x)
    for d in range(2, max_degree + 1):
        for combo in combinations(range(n), d):
            t = 1.0
            for idx in combo:
                t *= x[idx]
            terms.append(t)
    return np.array(terms)


# ── Census loader ─────────────────────────────────────────────────────

def _load_plate_modes(plate_id: str) -> list[float]:
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        raise FileNotFoundError("No census file.")
    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]
    if plate_id not in census or not census[plate_id].get("peaks"):
        raise ValueError(f"Plate {plate_id} not found in census")
    return [p["freq_hz"] for p in census[plate_id]["peaks"]]


def _load_all_modes() -> dict[str, list[float]]:
    """Load modes for all 5 plates."""
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        raise FileNotFoundError("No census file.")
    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]
    modes = {}
    for pid in PLATE_NAMES:
        if pid in census and census[pid].get("peaks"):
            modes[pid] = [p["freq_hz"] for p in census[pid]["peaks"]]
    return modes


def _build_union_readout(all_modes: dict[str, list[float]]) -> list[float]:
    """Build a unified readout grid covering all plates' modes."""
    all_freqs = set()
    for freqs in all_modes.values():
        all_freqs.update(freqs)
    return sorted(all_freqs)


def _ridge_eval(X_tr, X_te, y_tr, y_te, alpha=1.0):
    """Ridge regression with one-hot encoding, return (train_acc, test_acc)."""
    n_classes = max(max(y_tr), max(y_te)) + 1
    Xb_tr = np.column_stack([X_tr, np.ones(len(y_tr))])
    Xb_te = np.column_stack([X_te, np.ones(len(y_te))])
    d = Xb_tr.shape[1]
    Y_oh = np.zeros((len(y_tr), n_classes))
    for ii, lbl in enumerate(y_tr):
        Y_oh[ii, lbl] = 1.0
    W = np.linalg.solve(Xb_tr.T @ Xb_tr + alpha * np.eye(d),
                        Xb_tr.T @ Y_oh)
    tr_acc = float(np.mean(np.argmax(Xb_tr @ W, axis=1) == y_tr))
    te_acc = float(np.mean(np.argmax(Xb_te @ W, axis=1) == y_te))
    return tr_acc, te_acc


# ═══════════════════════════════════════════════════════════════════════
# TEST A — Same-plate pulsed ringdown
# ═══════════════════════════════════════════════════════════════════════

def run_test_a(handle, mux, plate_id: str, n_patterns=N_PATTERNS,
               delays_ms=None, seed=42) -> dict:
    """
    Drive pattern on plate → AWG off → capture ringdown on SAME plate.

    No mux switch needed. The ringdown spectrum encodes what was driven.
    Since there's no competing CW signal, the ONLY spectral energy
    present is from the decaying modes — pure memory signal.
    """
    if delays_ms is None:
        delays_ms = RINGDOWN_DELAYS_MS

    name = PLATE_NAMES.get(plate_id, plate_id)
    mode_freqs = _load_plate_modes(plate_id)
    n_modes = len(mode_freqs)
    n_input_bits = min(4, n_modes)
    input_indices = np.linspace(0, n_modes - 1, n_input_bits, dtype=int)

    # Fixed f_rep for ARB consistency
    arb_len = 4096
    max_freq = max(mode_freqs)
    fixed_f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))

    print(f"\n{'=' * 65}")
    print(f"  TEST A — Same-plate pulsed ringdown — Plate {name}")
    print(f"  {n_modes} modes, {n_input_bits} input bits, f_rep={fixed_f_rep:.0f} Hz")
    print(f"  Delays: {delays_ms} ms, Patterns: {n_patterns}")
    print(f"{'=' * 65}")

    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    # Readout at all mode frequencies
    readout_freqs = sorted(set(mode_freqs))
    diag_in_readout = [readout_freqs.index(mode_freqs[idx]) for idx in input_indices]

    # Generate random patterns
    rng = np.random.default_rng(seed)
    n_total_patterns = 2 ** n_input_bits
    all_bit_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_input_bits)] for i in range(n_total_patterns)])
    pattern_indices = rng.choice(n_total_patterns, n_patterns)
    patterns = all_bit_patterns[pattern_indices]
    parities = np.sum(patterns, axis=1) % 2

    # Train/test split
    n_train = int(0.75 * n_patterns)

    delay_results = []

    for delay_ms in delays_ms:
        print(f"\n  ── Delay: {delay_ms} ms ──")
        X_features = np.zeros((n_patterns, len(readout_freqs)))
        t0 = time.time()

        for i in range(n_patterns):
            # Build drive frequencies for this pattern
            drive_freqs = [mode_freqs[input_indices[b]]
                           for b in range(n_input_bits) if patterns[i, b] > 0]
            drive_amps = [1.0] * len(drive_freqs)

            # 1) Drive the pattern (all plates excited)
            if drive_freqs:
                _drive_multitone_arb(handle, drive_freqs, drive_amps, fixed_f_rep)
            else:
                _awg_off(handle)
            time.sleep(T_EXCITE_S)

            # 2) Cut AWG — modes begin free ringdown
            _awg_off(handle)

            # 3) Wait Δt then capture ringdown spectrum
            time.sleep(delay_ms / 1000.0)
            response = _capture_spectrum(handle, readout_freqs)
            X_features[i] = response

            if (i + 1) % 15 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (n_patterns - i - 1) / rate
                print(f"    [{i+1}/{n_patterns}] {elapsed:.0f}s, ~{eta:.0f}s left")

        capture_time = time.time() - t0
        print(f"    Done: {capture_time:.1f}s ({capture_time/n_patterns:.2f}s/pat)")

        # ── Classify ──
        X_log = np.log1p(X_features)
        X_tr = X_log[:n_train]
        X_te = X_log[n_train:]
        mu = X_tr.mean(axis=0)
        sigma = X_tr.std(axis=0) + 1e-8
        X_tr_std = (X_tr - mu) / sigma
        X_te_std = (X_te - mu) / sigma

        # Diagonal features + poly
        X_tr_diag = X_tr_std[:, diag_in_readout]
        X_te_diag = X_te_std[:, diag_in_readout]
        poly_deg = min(4, n_input_bits)
        X_tr_poly = np.array([_interaction_expand(row, poly_deg) for row in X_tr_diag])
        X_te_poly = np.array([_interaction_expand(row, poly_deg) for row in X_te_diag])
        X_tr_comb = np.column_stack([X_tr_std, X_tr_poly])
        X_te_comb = np.column_stack([X_te_std, X_te_poly])

        # Parity classification (the hard task)
        y_tr = parities[:n_train]
        y_te = parities[n_train:]

        # Also: pattern identity (multi-class — which of the 2^n patterns?)
        pid_tr = pattern_indices[:n_train]
        pid_te = pattern_indices[n_train:]

        tasks = {}
        for tname, Xtr, Xte, ytr, yte in [
            ("parity_raw", X_tr_std, X_te_std, y_tr, y_te),
            ("parity_poly", X_tr_comb, X_te_comb, y_tr, y_te),
            ("pattern_raw", X_tr_std, X_te_std, pid_tr, pid_te),
            ("pattern_poly", X_tr_comb, X_te_comb, pid_tr, pid_te),
        ]:
            tr, te = _ridge_eval(Xtr, Xte, ytr, yte)
            tasks[tname] = {"train": round(tr * 100, 1), "test": round(te * 100, 1)}

        # Signal analysis: ringdown magnitude vs noise
        driven_mags = []
        silent_mags = []
        for i in range(n_patterns):
            for b in range(n_input_bits):
                ridx = diag_in_readout[b]
                if patterns[i, b] > 0:
                    driven_mags.append(X_log[i, ridx])
                else:
                    silent_mags.append(X_log[i, ridx])

        d_mean = float(np.mean(driven_mags)) if driven_mags else 0
        s_mean = float(np.mean(silent_mags)) if silent_mags else 0
        d_std = float(np.std(driven_mags)) if driven_mags else 1
        s_std = float(np.std(silent_mags)) if silent_mags else 1
        ringdown_snr = (d_mean - s_mean) / (d_std + s_std + 1e-8)

        print(f"    Ringdown SNR: {ringdown_snr:.2f} "
              f"(driven={d_mean:.2f}±{d_std:.2f}, silent={s_mean:.2f}±{s_std:.2f})")
        print(f"    {'Task':<20} {'Train':>7} {'Test':>7}")
        print(f"    {'-' * 36}")
        for tname, info in tasks.items():
            marker = " ✓" if info["test"] > 60 else ""
            print(f"    {tname:<20} {info['train']:>6.1f}% {info['test']:>6.1f}%{marker}")

        delay_results.append({
            "delay_ms": delay_ms,
            "tasks": tasks,
            "ringdown_snr": round(ringdown_snr, 4),
            "driven_mean": round(d_mean, 3),
            "silent_mean": round(s_mean, 3),
            "capture_time_s": round(capture_time, 1),
        })

    # Summary
    best_parity = max(dr["tasks"]["parity_poly"]["test"] for dr in delay_results)
    best_pattern = max(dr["tasks"]["pattern_poly"]["test"] for dr in delay_results)
    best_snr = max(dr["ringdown_snr"] for dr in delay_results)

    print(f"\n  ── SUMMARY: Plate {name} (Test A — same-plate ringdown) ──")
    print(f"  {'Δt(ms)':<8} {'SNR':>6} {'parity':>8} {'pattern':>9}")
    print(f"  {'-' * 35}")
    for dr in delay_results:
        dt = dr["delay_ms"]
        snr = dr["ringdown_snr"]
        par = dr["tasks"]["parity_poly"]["test"]
        pat = dr["tasks"]["pattern_poly"]["test"]
        print(f"  {dt:<8} {snr:>6.2f} {par:>7.1f}% {pat:>8.1f}%")

    has_memory = best_parity > 70
    print(f"\n  Best parity: {best_parity:.1f}% "
          f"({'RINGDOWN MEMORY' if has_memory else 'no memory'})")
    print(f"  Best pattern ID: {best_pattern:.1f}%")
    print(f"  Best ringdown SNR: {best_snr:.2f}")

    return {
        "test": "A",
        "test_name": "same_plate_pulsed_ringdown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate_name": name,
        "plate_id": plate_id,
        "n_modes": n_modes,
        "n_input_bits": n_input_bits,
        "n_patterns": n_patterns,
        "t_excite_ms": T_EXCITE_S * 1000,
        "delays_ms": delays_ms,
        "delay_results": delay_results,
        "best_parity_pct": best_parity,
        "best_pattern_pct": best_pattern,
        "best_ringdown_snr": best_snr,
        "has_memory": has_memory,
        "mode_freqs_hz": mode_freqs,
    }


# ═══════════════════════════════════════════════════════════════════════
# TEST B — Cross-plate ringdown
# ═══════════════════════════════════════════════════════════════════════

def run_test_b(handle, mux, drive_plate_id: str, read_plate_id: str,
               n_patterns=N_PATTERNS, delays_ms=None, seed=42) -> dict:
    """
    Drive pattern (via drive_plate's modes) → AWG off → switch mux to
    read_plate → capture read_plate's ringdown.

    Hardware: AWG drives ALL plates simultaneously.
    So read_plate has been excited the whole time by the same freqs.
    Its ringdown encodes the pattern, filtered through its OWN modes.

    This tests: "Can Plate Y remember what was driven while I was
    listening to Plate X?"
    """
    if delays_ms is None:
        delays_ms = RINGDOWN_DELAYS_MS

    d_name = PLATE_NAMES.get(drive_plate_id, drive_plate_id)
    r_name = PLATE_NAMES.get(read_plate_id, read_plate_id)

    # Load modes for the DRIVE plate (determines what frequencies we drive)
    drive_modes = _load_plate_modes(drive_plate_id)
    # Load modes for the READ plate (determines what frequencies we listen at)
    read_modes = _load_plate_modes(read_plate_id)

    n_drive_modes = len(drive_modes)
    n_input_bits = min(4, n_drive_modes)
    input_indices = np.linspace(0, n_drive_modes - 1, n_input_bits, dtype=int)

    # Fixed f_rep from drive plate's mode range
    arb_len = 4096
    max_freq = max(drive_modes)
    fixed_f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))

    # Readout at the READ plate's modes (what it naturally resonates at)
    readout_freqs = sorted(set(read_modes))

    # Also add the DRIVE plate's mode frequencies to readout
    # (the read plate may ring at these freqs too, even if they're not
    #  exact resonances — nearby modes will pick up energy)
    drive_freqs_set = sorted(set(drive_modes))
    for f in drive_freqs_set:
        if f not in readout_freqs:
            readout_freqs.append(f)
    readout_freqs = sorted(readout_freqs)
    n_readout = len(readout_freqs)

    print(f"\n{'=' * 65}")
    print(f"  TEST B — Cross-plate ringdown")
    print(f"  Drive plate: {d_name} ({n_drive_modes} modes)")
    print(f"  Read plate:  {r_name} ({len(read_modes)} modes)")
    print(f"  Readout grid: {n_readout} freqs (union of both plates)")
    print(f"  Input bits: {n_input_bits}, f_rep={fixed_f_rep:.0f} Hz")
    print(f"  Delays: {delays_ms} ms, Patterns: {n_patterns}")
    print(f"{'=' * 65}")

    # Generate patterns (using drive plate's modes)
    rng = np.random.default_rng(seed)
    n_total = 2 ** n_input_bits
    all_bit_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_input_bits)] for i in range(n_total)])
    pattern_indices = rng.choice(n_total, n_patterns)
    patterns = all_bit_patterns[pattern_indices]
    parities = np.sum(patterns, axis=1) % 2

    n_train = int(0.75 * n_patterns)

    delay_results = []

    for delay_ms in delays_ms:
        print(f"\n  ── Delay: {delay_ms} ms ──")
        X_features = np.zeros((n_patterns, n_readout))
        t0 = time.time()

        for i in range(n_patterns):
            # Build drive freqs from DRIVE plate's modes
            d_freqs = [drive_modes[input_indices[b]]
                       for b in range(n_input_bits) if patterns[i, b] > 0]
            d_amps = [1.0] * len(d_freqs)

            # 1) Select drive plate for monitoring (but all plates are driven)
            mux.select(int(drive_plate_id))
            time.sleep(0.02)  # brief settle

            # 2) Drive the pattern (all plates excited simultaneously)
            if d_freqs:
                _drive_multitone_arb(handle, d_freqs, d_amps, fixed_f_rep)
            else:
                _awg_off(handle)
            time.sleep(T_EXCITE_S)

            # 3) Cut AWG — all plates begin free ringdown
            _awg_off(handle)

            # 4) Switch mux to READ plate
            mux.select(int(read_plate_id))
            # Relay settle overlaps with initial ringdown decay
            time.sleep(SETTLE_RELAY_S)

            # 5) Wait remaining Δt after relay settle, then capture
            remaining_ms = max(0, delay_ms - 100)  # 100ms already in relay settle
            if remaining_ms > 0:
                time.sleep(remaining_ms / 1000.0)

            response = _capture_spectrum(handle, readout_freqs)
            X_features[i] = response

            if (i + 1) % 15 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (n_patterns - i - 1) / rate
                print(f"    [{i+1}/{n_patterns}] {elapsed:.0f}s, ~{eta:.0f}s left")

        capture_time = time.time() - t0
        print(f"    Done: {capture_time:.1f}s ({capture_time/n_patterns:.2f}s/pat)")

        # Silence AWG between delays
        _awg_off(handle)
        time.sleep(0.1)

        # ── Classify ──
        X_log = np.log1p(X_features)
        X_tr = X_log[:n_train]
        X_te = X_log[n_train:]
        mu = X_tr.mean(axis=0)
        sigma = X_tr.std(axis=0) + 1e-8
        X_tr_std = (X_tr - mu) / sigma
        X_te_std = (X_te - mu) / sigma

        # Poly on first n_input_bits features
        n_use = min(n_input_bits, n_readout)
        X_tr_diag = X_tr_std[:, :n_use]
        X_te_diag = X_te_std[:, :n_use]
        poly_deg = min(4, n_use)
        X_tr_poly = np.array([_interaction_expand(row, poly_deg) for row in X_tr_diag])
        X_te_poly = np.array([_interaction_expand(row, poly_deg) for row in X_te_diag])
        X_tr_comb = np.column_stack([X_tr_std, X_tr_poly])
        X_te_comb = np.column_stack([X_te_std, X_te_poly])

        y_tr = parities[:n_train]
        y_te = parities[n_train:]
        pid_tr = pattern_indices[:n_train]
        pid_te = pattern_indices[n_train:]

        tasks = {}
        for tname, Xtr, Xte, ytr, yte in [
            ("parity_raw", X_tr_std, X_te_std, y_tr, y_te),
            ("parity_poly", X_tr_comb, X_te_comb, y_tr, y_te),
            ("pattern_raw", X_tr_std, X_te_std, pid_tr, pid_te),
            ("pattern_poly", X_tr_comb, X_te_comb, pid_tr, pid_te),
        ]:
            tr, te = _ridge_eval(Xtr, Xte, ytr, yte)
            tasks[tname] = {"train": round(tr * 100, 1), "test": round(te * 100, 1)}

        print(f"    {'Task':<20} {'Train':>7} {'Test':>7}")
        print(f"    {'-' * 36}")
        for tname, info in tasks.items():
            marker = " ✓" if info["test"] > 60 else ""
            print(f"    {tname:<20} {info['train']:>6.1f}% {info['test']:>6.1f}%{marker}")

        delay_results.append({
            "delay_ms": delay_ms,
            "tasks": tasks,
            "capture_time_s": round(capture_time, 1),
        })

    best_parity = max(dr["tasks"]["parity_poly"]["test"] for dr in delay_results)
    best_pattern = max(dr["tasks"]["pattern_poly"]["test"] for dr in delay_results)

    print(f"\n  ── SUMMARY: {d_name}→{r_name} (Test B — cross-plate ringdown) ──")
    print(f"  {'Δt(ms)':<8} {'parity':>8} {'pattern':>9}")
    print(f"  {'-' * 28}")
    for dr in delay_results:
        dt = dr["delay_ms"]
        par = dr["tasks"]["parity_poly"]["test"]
        pat = dr["tasks"]["pattern_poly"]["test"]
        print(f"  {dt:<8} {par:>7.1f}% {pat:>8.1f}%")

    has_memory = best_parity > 70
    print(f"\n  Best parity: {best_parity:.1f}% "
          f"({'CROSS-PLATE MEMORY' if has_memory else 'no cross-plate memory'})")

    return {
        "test": "B",
        "test_name": "cross_plate_ringdown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "drive_plate": d_name,
        "read_plate": r_name,
        "n_drive_modes": n_drive_modes,
        "n_read_modes": len(read_modes),
        "n_readout": n_readout,
        "n_input_bits": n_input_bits,
        "n_patterns": n_patterns,
        "t_excite_ms": T_EXCITE_S * 1000,
        "delays_ms": delays_ms,
        "delay_results": delay_results,
        "best_parity_pct": best_parity,
        "best_pattern_pct": best_pattern,
        "has_memory": has_memory,
        "drive_modes_hz": drive_modes,
        "read_modes_hz": read_modes,
    }


# ═══════════════════════════════════════════════════════════════════════
# TEST C — Cross-plate live (known-sequence / routing inference)
# ═══════════════════════════════════════════════════════════════════════

def run_test_c(handle, mux, plate_ids: list[str],
               n_patterns=N_PATTERNS, seed=42) -> dict:
    """
    Drive a pattern → while still driving, read different plates.
    Each plate produces a different spectral fingerprint of the SAME drive
    because each has different mode frequencies/shapes.

    Task: from Plate Y's spectrum alone, classify the pattern AND
    identify which plate was previously being read (routing history).

    This tests: "If I'm Plate B, can my spectrum tell you what was
    driven AND that Plate A was the last one read?"
    """
    # Use all modes from all plates to build drive patterns
    all_modes = _load_all_modes()
    plate_names = [PLATE_NAMES[pid] for pid in plate_ids]

    # Use whichever plate has the most modes as driver (best coverage)
    # Search ALL plates, not just the read set
    best_pid = max(all_modes.keys(), key=lambda p: len(all_modes.get(p, [])))
    drive_modes = all_modes[best_pid]
    n_drive_modes = len(drive_modes)
    n_input_bits = min(4, n_drive_modes)
    input_indices = np.linspace(0, n_drive_modes - 1, n_input_bits, dtype=int)

    arb_len = 4096
    max_freq = max(drive_modes)
    fixed_f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))

    # Union readout covers all plates' modes
    readout_freqs = _build_union_readout(all_modes)
    n_readout = len(readout_freqs)

    print(f"\n{'=' * 65}")
    print(f"  TEST C — Cross-plate live (routing inference)")
    print(f"  Drive using Plate {PLATE_NAMES[best_pid]}'s modes ({n_drive_modes})")
    print(f"  Reading plates: {plate_names}")
    print(f"  Union readout: {n_readout} freqs")
    print(f"  Input bits: {n_input_bits}, Patterns: {n_patterns}")
    print(f"{'=' * 65}")

    # Generate patterns
    rng = np.random.default_rng(seed)
    n_total = 2 ** n_input_bits
    all_bit_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_input_bits)] for i in range(n_total)])
    pattern_indices = rng.choice(n_total, n_patterns)
    patterns = all_bit_patterns[pattern_indices]
    parities = np.sum(patterns, axis=1) % 2

    # For each pattern, we read ALL plates → get one spectrum per plate
    # Then classify: (a) what pattern? (b) which plate am I reading?
    n_plates = len(plate_ids)
    total_samples = n_patterns * n_plates

    X_all = np.zeros((total_samples, n_readout))
    y_parity = np.zeros(total_samples, dtype=int)
    y_plate = np.zeros(total_samples, dtype=int)
    y_pattern = np.zeros(total_samples, dtype=int)

    t0 = time.time()
    idx = 0

    for i in range(n_patterns):
        # Build drive freqs
        d_freqs = [drive_modes[input_indices[b]]
                   for b in range(n_input_bits) if patterns[i, b] > 0]
        d_amps = [1.0] * len(d_freqs)

        # Drive pattern (all plates get it)
        if d_freqs:
            _drive_multitone_arb(handle, d_freqs, d_amps, fixed_f_rep)
        else:
            _awg_off(handle)
        time.sleep(T_EXCITE_S)

        # Read each plate's response to this pattern (drive stays on)
        for p_idx, pid in enumerate(plate_ids):
            mux.select(int(pid))
            time.sleep(SETTLE_RELAY_S)
            response = _capture_spectrum(handle, readout_freqs)

            X_all[idx] = response
            y_parity[idx] = parities[i]
            y_plate[idx] = p_idx
            y_pattern[idx] = pattern_indices[i]
            idx += 1

        if (i + 1) % 10 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (n_patterns - i - 1) / rate
            print(f"  [{i+1}/{n_patterns}] {elapsed:.0f}s, ~{eta:.0f}s left")

    capture_time = time.time() - t0
    _awg_off(handle)
    print(f"  Done: {capture_time:.1f}s ({capture_time/total_samples:.2f}s/sample)")

    # ── Classify ──
    X_log = np.log1p(X_all[:idx])
    n_train = int(0.75 * idx)

    X_tr = X_log[:n_train]
    X_te = X_log[n_train:]
    mu = X_tr.mean(axis=0)
    sigma = X_tr.std(axis=0) + 1e-8
    X_tr_std = (X_tr - mu) / sigma
    X_te_std = (X_te - mu) / sigma

    tasks = {}

    # ── Task 1: raw parity (pooled, no poly — baseline) ──
    tr, te = _ridge_eval(X_tr_std, X_te_std,
                         y_parity[:n_train], y_parity[n_train:idx])
    tasks["parity_raw_pooled"] = {"train": round(tr*100,1), "test": round(te*100,1)}

    # ── Task 2: plate identity (raw) ──
    tr, te = _ridge_eval(X_tr_std, X_te_std,
                         y_plate[:n_train], y_plate[n_train:idx])
    tasks["plate_identity_raw"] = {"train": round(tr*100,1), "test": round(te*100,1)}

    # ── Task 3: PER-PLATE parity (the key test) ──
    # Each plate gets its own classifier with polynomial expansion.
    # This mirrors E09's approach: plate-specific weights.
    per_plate_parity = {}
    for p_idx, pid in enumerate(plate_ids):
        p_name = PLATE_NAMES[pid]
        mask_tr = y_plate[:n_train] == p_idx
        mask_te = y_plate[n_train:idx] == p_idx
        if mask_tr.sum() < 5 or mask_te.sum() < 3:
            per_plate_parity[p_name] = {"train": 0.0, "test": 0.0, "n_test": 0}
            continue

        plate_modes = all_modes.get(pid, [])
        diag_idx = []
        for mf in plate_modes:
            dists = [abs(mf - rf) for rf in readout_freqs]
            diag_idx.append(int(np.argmin(dists)))

        Xp_tr = X_log[:n_train][mask_tr][:, diag_idx] if diag_idx else X_tr[mask_tr]
        Xp_te = X_log[n_train:idx][mask_te][:, diag_idx] if diag_idx else X_te[mask_te]
        mu_p = Xp_tr.mean(axis=0)
        sig_p = Xp_tr.std(axis=0) + 1e-8
        Xp_tr_s = (Xp_tr - mu_p) / sig_p
        Xp_te_s = (Xp_te - mu_p) / sig_p
        Xp_tr_poly = np.array([_interaction_expand(x, max_degree=3) for x in Xp_tr_s])
        Xp_te_poly = np.array([_interaction_expand(x, max_degree=3) for x in Xp_te_s])

        tr_p, te_p = _ridge_eval(
            Xp_tr_poly, Xp_te_poly,
            y_parity[:n_train][mask_tr], y_parity[n_train:idx][mask_te])
        per_plate_parity[p_name] = {
            "train": round(tr_p*100, 1),
            "test": round(te_p*100, 1),
            "n_train": int(mask_tr.sum()),
            "n_test": int(mask_te.sum()),
            "n_diag_modes": len(diag_idx),
        }

    # Oracle per-plate parity
    oracle_parity_sum, oracle_parity_n = 0, 0
    for p_name, info in per_plate_parity.items():
        nt = info.get("n_test", 0)
        oracle_parity_sum += info["test"] * nt
        oracle_parity_n += nt
    oracle_parity = oracle_parity_sum / oracle_parity_n if oracle_parity_n else 0

    tasks["per_plate_parity"] = {
        "detail": per_plate_parity,
        "oracle_parity": round(oracle_parity, 1),
    }

    # ── Task 4: multi-head concatenation ──
    # For each PATTERN, concatenate each plate's diagonal mode responses
    n_train_pat = int(0.75 * n_patterns)
    concat_cols = []
    for p_idx, pid in enumerate(plate_ids):
        pm = all_modes.get(pid, [])
        for mf in pm:
            dists = [abs(mf - rf) for rf in readout_freqs]
            ridx = int(np.argmin(dists))
            col = np.zeros(n_patterns)
            for i in range(n_patterns):
                row = i * n_plates + p_idx
                if row < idx:
                    col[i] = X_log[row, ridx]
            concat_cols.append(col)

    X_mh = np.column_stack(concat_cols)  # n_patterns × (sum of all plates' modes)
    n_mh_features = X_mh.shape[1]
    X_mh_tr = X_mh[:n_train_pat]
    X_mh_te = X_mh[n_train_pat:]
    mu_mh = X_mh_tr.mean(axis=0)
    sig_mh = X_mh_tr.std(axis=0) + 1e-8
    X_mh_tr_s = (X_mh_tr - mu_mh) / sig_mh
    X_mh_te_s = (X_mh_te - mu_mh) / sig_mh

    # Raw multi-head
    tr, te = _ridge_eval(X_mh_tr_s, X_mh_te_s,
                         parities[:n_train_pat], parities[n_train_pat:])
    tasks["multihead_parity_raw"] = {"train": round(tr*100,1), "test": round(te*100,1)}

    # Multi-head with polynomial (degree 3 fine for ~15 features)
    X_mh_tr_p = np.array([_interaction_expand(x, max_degree=3) for x in X_mh_tr_s])
    X_mh_te_p = np.array([_interaction_expand(x, max_degree=3) for x in X_mh_te_s])
    tr, te = _ridge_eval(X_mh_tr_p, X_mh_te_p,
                         parities[:n_train_pat], parities[n_train_pat:])
    tasks["multihead_parity_poly"] = {"train": round(tr*100,1), "test": round(te*100,1)}

    # ── Print results ──
    print(f"\n  ── RESULTS: Test C (enhanced) ──")
    print(f"  {'Task':<30} {'Train':>7} {'Test':>7}")
    print(f"  {'-' * 46}")
    for tname, info in tasks.items():
        if tname == "per_plate_parity":
            print(f"  per_plate_parity (oracle):")
            for pn, pi in info["detail"].items():
                marker = " ✓" if pi["test"] > 60 else ""
                print(f"    Plate {pn}: {pi['train']:.1f}% / {pi['test']:.1f}%"
                      f" (n={pi.get('n_test',0)}, modes={pi.get('n_diag_modes',0)}){marker}")
            print(f"    → Oracle gated: {info['oracle_parity']:.1f}%")
            continue
        marker = " ✓" if info.get("test", 0) > 60 else ""
        print(f"  {tname:<30} {info['train']:>6.1f}% {info['test']:>6.1f}%{marker}")

    plate_id_acc = tasks["plate_identity_raw"]["test"]
    multihead = tasks.get("multihead_parity_poly", tasks["multihead_parity_raw"])["test"]

    print(f"\n  Plate identity: {plate_id_acc:.1f}%"
          f" ({'DISTINGUISHABLE' if plate_id_acc > 80 else 'partial' if plate_id_acc > 60 else 'weak'})")
    print(f"  Multi-head parity: {multihead:.1f}%")
    print(f"  Oracle per-plate parity: {oracle_parity:.1f}%")
    print(f"  Multi-head features: {n_mh_features} (from {n_plates} plates)")

    # ── Store raw data for reanalysis ──
    samples = []
    for i in range(idx):
        samples.append({
            "spectrum": X_all[i].tolist(),
            "parity": int(y_parity[i]),
            "plate_idx": int(y_plate[i]),
            "pattern_idx": int(y_pattern[i]),
        })

    return {
        "test": "C",
        "test_name": "cross_plate_live_routing",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate_names": plate_names,
        "n_plates": n_plates,
        "drive_plate": PLATE_NAMES[best_pid],
        "n_drive_modes": n_drive_modes,
        "n_input_bits": n_input_bits,
        "n_readout": n_readout,
        "readout_freqs_hz": readout_freqs,
        "n_patterns": n_patterns,
        "total_samples": idx,
        "tasks": {k: v for k, v in tasks.items() if k != "per_plate_parity"},
        "per_plate_parity": per_plate_parity,
        "oracle_parity_pct": oracle_parity,
        "plate_identity_pct": plate_id_acc,
        "multihead_parity_pct": multihead,
        "n_multihead_features": n_mh_features,
        "samples": samples,
    }


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate pulsed memory — ringdown & cross-plate temporal encoding"
    )
    parser.add_argument(
        "--test", type=str, default="A",
        choices=["A", "B", "C", "all"],
        help="Which test to run (A=same-plate ringdown, B=cross-plate ringdown, "
             "C=cross-plate live, all=A+B+C)"
    )
    parser.add_argument(
        "--plate", type=str, default="3",
        help="Plate ID for Test A (default: 3 = Plate C)"
    )
    parser.add_argument(
        "--all-plates", action="store_true",
        help="Run Test A on all 5 plates"
    )
    parser.add_argument(
        "--drive-plate", type=str, default="3",
        help="Drive plate for Test B (default: 3)"
    )
    parser.add_argument(
        "--read-plate", type=str, default="4",
        help="Read plate for Test B (default: 4)"
    )
    parser.add_argument(
        "--n-patterns", type=int, default=60,
        help="Patterns per test (default: 60)"
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

    tests_to_run = [args.test] if args.test != "all" else ["A", "B", "C"]

    handle = _open_scope()
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {mux.port}")

    results = []
    try:
        if "A" in tests_to_run:
            plate_ids = sorted(PLATE_NAMES.keys()) if args.all_plates else [args.plate]
            for pid in plate_ids:
                r = run_test_a(handle, mux, pid, n_patterns=args.n_patterns)
                results.append(r)

        if "B" in tests_to_run:
            # Run a few interesting cross-plate pairs
            if args.all_plates:
                # C→D and B→E have most mode overlap
                pairs = [("3", "4"), ("2", "5"), ("1", "3")]
            else:
                pairs = [(args.drive_plate, args.read_plate)]
            for dp, rp in pairs:
                r = run_test_b(handle, mux, dp, rp, n_patterns=args.n_patterns)
                results.append(r)

        if "C" in tests_to_run:
            plate_ids = sorted(PLATE_NAMES.keys()) if args.all_plates else [args.plate, args.read_plate]
            r = run_test_c(handle, mux, plate_ids, n_patterns=args.n_patterns)
            results.append(r)

    finally:
        mux.off()
        _close_scope(handle)

    # ── Save ──
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    for r in results:
        test_label = r["test"]
        if test_label == "A":
            fname = f"pulsed_memory_A_{r['plate_name']}_{TIMESTAMP}.json"
        elif test_label == "B":
            fname = f"pulsed_memory_B_{r['drive_plate']}{r['read_plate']}_{TIMESTAMP}.json"
        else:
            fname = f"pulsed_memory_C_{TIMESTAMP}.json"
        save_path = LAB_DIR / fname
        with open(save_path, "w") as f:
            json.dump(r, f, indent=2, default=str)
        print(f"\n  Saved: {save_path}")

    if len(results) > 1:
        combined = LAB_DIR / f"pulsed_memory_all_{TIMESTAMP}.json"
        with open(combined, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"  Combined: {combined}")


if __name__ == "__main__":
    main()
