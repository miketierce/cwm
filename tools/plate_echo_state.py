#!/usr/bin/env python3
"""
Plate Echo State Network — Temporal Sequence Processing

Tests whether the plate's ringdown creates measurable temporal memory:
  1. Drive pattern₁ (multi-tone via ARB) for T_excite
  2. Switch to pattern₂ (new ARB waveform)
  3. After short delay Δt (< full ringdown), capture FFT
  4. The spectrum encodes BOTH current excitation AND residual echo from pattern₁
  5. Train readouts for three tasks:
     - "current":  classify pattern₂ (easy baseline — no memory needed)
     - "previous": classify pattern₁ from residual echo (pure memory test)
     - "xor_seq":  classify XOR(pattern₁, pattern₂) (requires memory + mixing)
  6. Sweep Δt to map the memory horizon

If "previous" accuracy > chance at short Δt, the plate has temporal memory.
If "xor_seq" > chance, the plate performs temporal computation.

This is the bridge between "plate does math" and "plate processes sequences."

Usage:
  PYTHONPATH=. python tools/plate_echo_state.py --all-plates --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_echo_state.py --plate 3 --delays 5,10,20,50,100
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

N_AVG = 4             # averages per measurement (lower for speed)
T_EXCITE_S = 0.20     # how long to drive pattern₁ before switching
SETTLE_RELAY_S = 0.10

# Delay values to sweep (ms) — from fast (strong echo) to slow (no echo)
DEFAULT_DELAYS_MS = [2, 5, 10, 20, 50, 100, 150]


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


def _capture_spectrum(handle, readout_freqs):
    """Capture N_AVG FFTs and return mean magnitudes at readout frequencies."""
    from picosdk.ps2000 import ps2000

    all_mags = []
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


# ── Enrollment loader ────────────────────────────────────────────────

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


# ── Echo State Protocol ──────────────────────────────────────────────

def _echo_capture(handle, pattern1, pattern2, mode_freqs, input_indices,
                  readout_freqs, fixed_f_rep, delay_ms):
    """Drive pattern₁ → switch to pattern₂ → wait Δt → capture.

    Returns feature vector from the spectral response during pattern₂ excitation,
    which contains both current (pattern₂) and echo (pattern₁) contributions.
    """
    n_input_bits = len(input_indices)

    # Build multi-tone waveforms for both patterns
    freqs1 = [mode_freqs[input_indices[b]]
              for b in range(n_input_bits) if pattern1[b] > 0]
    freqs2 = [mode_freqs[input_indices[b]]
              for b in range(n_input_bits) if pattern2[b] > 0]
    amps1 = [1.0] * len(freqs1)
    amps2 = [1.0] * len(freqs2)

    # Phase 1: Drive pattern₁ to build up resonance
    if freqs1:
        _drive_multitone_arb(handle, freqs1, amps1, fixed_f_rep)
    else:
        _awg_off(handle)
    time.sleep(T_EXCITE_S)

    # Phase 2: Switch to pattern₂
    if freqs2:
        _drive_multitone_arb(handle, freqs2, amps2, fixed_f_rep)
    else:
        _awg_off(handle)

    # Phase 3: Wait Δt then capture
    # Short delay = strong echo from pattern₁, long delay = no echo
    time.sleep(delay_ms / 1000.0)

    # Capture the spectrum (contains current + echo)
    response = _capture_spectrum(handle, readout_freqs)
    return response


def run_echo_state(handle, mux, plate_id: str,
                   delays_ms: list[int] = None,
                   n_input_bits: int = 4,
                   n_sequences: int = 60,
                   seed: int = 42) -> dict:
    """Run echo state experiment on one plate across multiple delays.

    For each delay Δt:
      1. Generate random 2-step sequences (pattern₁, pattern₂)
      2. Drive pattern₁ → switch → delay Δt → capture during pattern₂
      3. Train readouts for current, previous, and xor_seq tasks
      4. Report accuracy vs delay (the memory curve)
    """
    if delays_ms is None:
        delays_ms = DEFAULT_DELAYS_MS

    name = PLATE_NAMES.get(plate_id, plate_id)
    print(f"\n{'=' * 65}")
    print(f"  ECHO STATE — Plate {name}")
    print(f"  Delays: {delays_ms} ms")
    print(f"  Sequences per delay: {n_sequences}")
    print(f"{'=' * 65}")

    mode_freqs = _load_plate_modes(plate_id)
    n_modes = len(mode_freqs)
    n_input_bits = min(n_input_bits, n_modes)
    input_indices = np.linspace(0, n_modes - 1, n_input_bits, dtype=int)

    # Compute fixed f_rep
    arb_len = 4096
    max_freq = max(mode_freqs)
    fixed_f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))

    print(f"  Plate {name}: {n_modes} modes, {n_input_bits} input bits")
    print(f"  ARB f_rep: {fixed_f_rep:.0f} Hz")
    print(f"  T_excite: {T_EXCITE_S*1000:.0f} ms")

    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    # Readout at all enrolled mode frequencies
    readout_freqs = sorted(set(mode_freqs))
    n_readout = len(readout_freqs)

    # Map input mode indices to readout indices
    diag_in_readout = [readout_freqs.index(mode_freqs[idx]) for idx in input_indices]

    # Generate random sequence pairs (same for all delays)
    rng = np.random.default_rng(seed)
    n_patterns = 2 ** n_input_bits
    all_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_input_bits)] for i in range(n_patterns)])

    # Pick random (pattern₁, pattern₂) pairs — balanced
    # Ensure we see variety in both pattern₁ and pattern₂
    seq_idx1 = rng.choice(n_patterns, n_sequences)
    seq_idx2 = rng.choice(n_patterns, n_sequences)
    patterns1 = all_patterns[seq_idx1]
    patterns2 = all_patterns[seq_idx2]

    # Labels
    parity1 = np.sum(patterns1, axis=1) % 2  # parity of pattern₁
    parity2 = np.sum(patterns2, axis=1) % 2  # parity of pattern₂
    xor_seq = (parity1 + parity2) % 2        # XOR of parities

    # Train/test split
    n_train = int(0.75 * n_sequences)
    n_test = n_sequences - n_train

    delay_results = []

    for delay_idx, delay_ms in enumerate(delays_ms):
        print(f"\n  ── Delay: {delay_ms} ms ──")

        # Capture all sequences at this delay
        X_features = np.zeros((n_sequences, n_readout))
        t0 = time.time()

        for i in range(n_sequences):
            response = _echo_capture(
                handle, patterns1[i], patterns2[i],
                mode_freqs, input_indices,
                readout_freqs, fixed_f_rep, delay_ms
            )
            X_features[i] = response

            if (i + 1) % 15 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (n_sequences - i - 1) / rate
                print(f"    [{i+1}/{n_sequences}] {elapsed:.0f}s elapsed, "
                      f"~{eta:.0f}s remaining")

        capture_time = time.time() - t0
        print(f"    Captured {n_sequences} in {capture_time:.1f}s "
              f"({capture_time/n_sequences:.2f}s/seq)")

        # Silence the AWG between delays
        _awg_off(handle)
        time.sleep(0.1)

        # Log-scale and standardize
        X_log = np.log1p(X_features)
        X_train = X_log[:n_train]
        X_test = X_log[n_train:]
        mu = X_train.mean(axis=0)
        sigma = X_train.std(axis=0) + 1e-8
        X_train_std = (X_train - mu) / sigma
        X_test_std = (X_test - mu) / sigma

        # Extract diagonal features and build polynomial
        X_train_diag = X_train_std[:, diag_in_readout]
        X_test_diag = X_test_std[:, diag_in_readout]

        poly_degree = min(4, n_input_bits)
        X_train_poly = np.array([_interaction_expand(row, poly_degree)
                                 for row in X_train_diag])
        X_test_poly = np.array([_interaction_expand(row, poly_degree)
                                for row in X_test_diag])

        # Combined: raw + polynomial
        X_train_comb = np.column_stack([X_train_std, X_train_poly])
        X_test_comb = np.column_stack([X_test_std, X_test_poly])

        # Ridge regression for each task
        alpha = 1.0

        def _ridge_eval(X_tr, X_te, y_tr, y_te):
            Xb_tr = np.column_stack([X_tr, np.ones(len(y_tr))])
            Xb_te = np.column_stack([X_te, np.ones(len(y_te))])
            d = Xb_tr.shape[1]
            Y_oh = np.zeros((len(y_tr), 2))
            for ii, lbl in enumerate(y_tr):
                Y_oh[ii, lbl] = 1.0
            W = np.linalg.solve(Xb_tr.T @ Xb_tr + alpha * np.eye(d),
                                Xb_tr.T @ Y_oh)
            tr_acc = float(np.mean(np.argmax(Xb_tr @ W, axis=1) == y_tr))
            te_acc = float(np.mean(np.argmax(Xb_te @ W, axis=1) == y_te))
            return tr_acc, te_acc

        y_tr_cur = parity2[:n_train]
        y_te_cur = parity2[n_train:]
        y_tr_prev = parity1[:n_train]
        y_te_prev = parity1[n_train:]
        y_tr_xor = xor_seq[:n_train]
        y_te_xor = xor_seq[n_train:]

        tasks = {}
        for tname, X_tr, X_te, y_tr, y_te in [
            ("current_raw", X_train_std, X_test_std, y_tr_cur, y_te_cur),
            ("current_poly", X_train_comb, X_test_comb, y_tr_cur, y_te_cur),
            ("previous_raw", X_train_std, X_test_std, y_tr_prev, y_te_prev),
            ("previous_poly", X_train_comb, X_test_comb, y_tr_prev, y_te_prev),
            ("xor_seq_raw", X_train_std, X_test_std, y_tr_xor, y_te_xor),
            ("xor_seq_poly", X_train_comb, X_test_comb, y_tr_xor, y_te_xor),
        ]:
            tr, te = _ridge_eval(X_tr, X_te, y_tr, y_te)
            tasks[tname] = {"train": round(tr * 100, 1),
                            "test": round(te * 100, 1)}

        # Echo strength: are residual features from pattern₁ detectable?
        # Measure: for modes active in pattern₁ but NOT in pattern₂,
        # what's the mean magnitude vs noise floor?
        echo_signals = []
        noise_signals = []
        for i in range(n_sequences):
            for b in range(n_input_bits):
                ridx = diag_in_readout[b]
                if patterns1[i, b] > 0 and patterns2[i, b] == 0:
                    # Pattern₁ active, pattern₂ silent → any signal is echo
                    echo_signals.append(X_log[i, ridx])
                elif patterns1[i, b] == 0 and patterns2[i, b] == 0:
                    # Both silent → pure noise
                    noise_signals.append(X_log[i, ridx])

        echo_mean = float(np.mean(echo_signals)) if echo_signals else 0
        noise_mean = float(np.mean(noise_signals)) if noise_signals else 0
        echo_std = float(np.std(echo_signals)) if echo_signals else 1
        noise_std = float(np.std(noise_signals)) if noise_signals else 1
        echo_snr = (echo_mean - noise_mean) / (echo_std + noise_std + 1e-8)

        # Print
        print(f"    Echo SNR: {echo_snr:.2f} "
              f"(echo={echo_mean:.2f}±{echo_std:.2f}, "
              f"noise={noise_mean:.2f}±{noise_std:.2f})")
        print(f"    {'Task':<20} {'Train':>7} {'Test':>7}")
        print(f"    {'-' * 36}")
        for tname, info in tasks.items():
            marker = " ✓" if info["test"] > 60 else ""
            print(f"    {tname:<20} {info['train']:>6.1f}% "
                  f"{info['test']:>6.1f}%{marker}")
        print(f"    Capture: {capture_time:.1f}s")

        delay_results.append({
            "delay_ms": delay_ms,
            "tasks": tasks,
            "echo_snr": round(echo_snr, 4),
            "echo_mean": round(echo_mean, 3),
            "noise_mean": round(noise_mean, 3),
            "capture_time_s": round(capture_time, 1),
        })

    # ── Summary ──
    mux.off()

    print(f"\n  ── MEMORY CURVE: Plate {name} ──")
    print(f"  {'Δt(ms)':<8} {'Echo SNR':>9} {'current':>9} {'previous':>9} "
          f"{'xor_seq':>9}")
    print(f"  {'-' * 50}")
    for dr in delay_results:
        dt = dr["delay_ms"]
        cur = dr["tasks"]["current_poly"]["test"]
        prev = dr["tasks"]["previous_poly"]["test"]
        xor_s = dr["tasks"]["xor_seq_poly"]["test"]
        snr = dr["echo_snr"]
        print(f"  {dt:<8} {snr:>9.2f} {cur:>8.1f}% {prev:>8.1f}% {xor_s:>8.1f}%")

    # Find memory horizon (last delay where previous > 60%)
    memory_horizon_ms = 0
    for dr in delay_results:
        if dr["tasks"]["previous_poly"]["test"] > 60:
            memory_horizon_ms = dr["delay_ms"]

    best_prev = max(dr["tasks"]["previous_poly"]["test"] for dr in delay_results)
    best_xor = max(dr["tasks"]["xor_seq_poly"]["test"] for dr in delay_results)
    best_cur = max(dr["tasks"]["current_poly"]["test"] for dr in delay_results)

    has_memory = best_prev > 60
    has_computation = best_xor > 60

    print(f"\n  Memory horizon: {memory_horizon_ms} ms "
          f"({'detected' if has_memory else 'none'})")
    print(f"  Best previous: {best_prev:.1f}% "
          f"({'MEMORY' if has_memory else 'no memory'})")
    print(f"  Best xor_seq:  {best_xor:.1f}% "
          f"({'TEMPORAL COMPUTE' if has_computation else 'no temporal compute'})")

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate_name": name,
        "plate_id": plate_id,
        "n_modes": n_modes,
        "n_input_bits": n_input_bits,
        "n_sequences": n_sequences,
        "t_excite_ms": T_EXCITE_S * 1000,
        "delays_ms": delays_ms,
        "delay_results": delay_results,
        "memory_horizon_ms": memory_horizon_ms,
        "best_current_pct": best_cur,
        "best_previous_pct": best_prev,
        "best_xor_seq_pct": best_xor,
        "has_memory": has_memory,
        "has_temporal_compute": has_computation,
        "mode_freqs_hz": mode_freqs,
        "readout_freqs_hz": readout_freqs,
    }

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Plate echo state — temporal sequence processing"
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
        "--delays", type=str, default=None,
        help="Comma-separated delay values in ms (default: 2,5,10,20,50,100,150)"
    )
    parser.add_argument(
        "--n-seq", type=int, default=60,
        help="Number of sequences per delay (default: 60)"
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

    delays_ms = None
    if args.delays:
        delays_ms = [int(x.strip()) for x in args.delays.split(",")]

    plate_ids = sorted(PLATE_NAMES.keys()) if args.all_plates else [args.plate]

    handle = _open_scope()
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {mux.port}")

    results = []
    try:
        for pid in plate_ids:
            result = run_echo_state(
                handle, mux, pid,
                delays_ms=delays_ms,
                n_sequences=args.n_seq,
            )
            results.append(result)
    finally:
        _close_scope(handle)
        mux.close()

    # ── Save & submit ──
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    token = None

    for result in results:
        name = result["plate_name"]
        save_path = LAB_DIR / f"echo_state_{name}_{TIMESTAMP}.json"
        with open(save_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Saved: {save_path}")

        if not args.dry_run:
            print("  Submitting to Firestore...")
            try:
                if token is None:
                    token = firebase_anon_auth()
                data = {
                    "plate_name": name,
                    "n_modes": result["n_modes"],
                    "n_input_bits": result["n_input_bits"],
                    "memory_horizon_ms": result["memory_horizon_ms"],
                    "best_previous_pct": result["best_previous_pct"],
                    "best_xor_seq_pct": result["best_xor_seq_pct"],
                    "has_memory": result["has_memory"],
                    "has_temporal_compute": result["has_temporal_compute"],
                }
                notes = (
                    f"Echo state: Plate {name}, "
                    f"memory={'YES' if result['has_memory'] else 'NO'}, "
                    f"prev={result['best_previous_pct']:.1f}%, "
                    f"xor={result['best_xor_seq_pct']:.1f}%."
                )
                r = submit_experiment(token, "exp-echo-state", data, notes=notes)
                print_result(r)
            except Exception as e:
                print(f"  ✗ Submission failed: {e}")

    if len(results) > 1:
        print(f"\n{'=' * 65}")
        print(f"  SUMMARY — ECHO STATE")
        print(f"{'=' * 65}")
        print(f"  {'Plate':<8} {'Modes':>5} {'Horizon':>10} {'Prev':>8} "
              f"{'XOR':>8} {'Memory':>8}")
        print(f"  {'-' * 52}")
        for r in results:
            print(f"  {r['plate_name']:<8} {r['n_modes']:>5} "
                  f"{r['memory_horizon_ms']:>8} ms "
                  f"{r['best_previous_pct']:>7.1f}% "
                  f"{r['best_xor_seq_pct']:>7.1f}% "
                  f"{'YES' if r['has_memory'] else 'NO':>8}")

        combined_path = LAB_DIR / f"echo_state_all_{TIMESTAMP}.json"
        with open(combined_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"  Combined: {combined_path}")


if __name__ == "__main__":
    main()
