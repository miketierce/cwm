#!/usr/bin/env python3
"""
Plate Reservoir Benchmark — PicoScope TX+RX (Full Bandwidth)

Uses PicoScope 2204A for both drive (AWG) and capture (Ch A).
100 MHz analog bandwidth → sees all modes (26-95 kHz).

Physical wiring:
  PicoScope AWG OUT → relay board signal IN → plate TX PZT
  Plate RX PZT → relay board → PicoScope Ch A

Reuses benchmark functions from plate_benchmark_kronos.py, but
replaces the capture path with PicoScope hardware.

Usage:
    # Hardware on plate 4, all benchmarks:
    python plate_benchmark_picoscope.py /dev/cu.usbserial-11310 \\
        --census <census.json> --plate 4 --benchmarks all

    # All 5 plates:
    python plate_benchmark_picoscope.py /dev/cu.usbserial-11310 \\
        --census <census.json> --all-plates --benchmarks all
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import cwm_picoscope  # noqa: F401  — sets DYLD_LIBRARY_PATH
from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux
from firestore_submit import firebase_anon_auth, submit_experiment, print_result

from plate_benchmark_kronos import (
    PLATE_NAMES, PLATE_RELAYS,
    FIXTURE_FREQ_HZ, FIXTURE_GUARD_HZ,
    POWER_ARDUINO_W, POWER_LAPTOP_READOUT_W,
    POWER_GPU_INFERENCE_W,
    load_census, get_plate_modes,
    benchmark_parity, benchmark_nonlinear, benchmark_capacity,
    bittensor_viability,
)

# ── PicoScope-specific config ──
N_AVG = 8             # averages per measurement (matches reservoir demo)
SETTLE_S = 0.15       # AWG settle
SETTLE_RELAY_S = 0.10

# Power: PicoScope replaces Kronos — simpler, lower power
POWER_PZT_DRIVE_W = 0.02
POWER_PICOSCOPE_W = 0.5      # PicoScope 2204A USB bus power
POWER_TOTAL_W = (POWER_PZT_DRIVE_W + POWER_PICOSCOPE_W
                 + POWER_ARDUINO_W + POWER_LAPTOP_READOUT_W)

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab" / "plate_exps"
LAB_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════
# PicoScope helpers
# ══════════════════════════════════════════════════════════════════════

def open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V DC
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B off
    print("  PicoScope opened (Ch A ±1V DC)")
    return handle


def close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("  PicoScope closed")


def _capture_spectrum(handle, drive_freq_hz: float,
                      readout_freqs: list[float],
                      drive_uvpp: int = AWG_DRIVE_UVPP) -> np.ndarray:
    """Drive AWG at drive_freq_hz, return magnitudes at readout freqs."""
    from picosdk.ps2000 import ps2000

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, drive_uvpp, 0,
        float(drive_freq_hz), float(drive_freq_hz), 0.0, 0.0, 0, 0)
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
            None, None, ctypes.byref(overflow), N_SAMPLES)
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


def _awg_off(handle):
    """Turn AWG off."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)


# ══════════════════════════════════════════════════════════════════════
# Capture functions matching kronos benchmark interface
# ══════════════════════════════════════════════════════════════════════

def make_picoscope_capture_sequential(handle, mode_freqs):
    """Return a capture_fn for sequential (one-carrier-at-a-time) mode.

    Signature: capture_fn(mode_freqs, carrier_indices, pattern, census_mags)
    Returns: flat array (n_carriers × n_modes)
    """
    def capture_fn(mf, carrier_indices, pattern, _census_mags):
        n_carriers = len(carrier_indices)
        n_modes = len(mf)
        cross_matrix = np.zeros((n_carriers, n_modes))

        for b in range(n_carriers):
            if pattern[b] > 0:
                ci = carrier_indices[b]
                drive_freq = mf[ci]
                mags = _capture_spectrum(handle, drive_freq, mf)
                cross_matrix[b, :] = mags
            # else: leave row as zeros (carrier OFF)

        _awg_off(handle)
        return cross_matrix.ravel()

    return capture_fn


def make_picoscope_capture_linear(handle, mode_freqs):
    """Return a capture_fn for linear (multitone simultaneous) mode.

    Drives all active carriers simultaneously, returns FFT magnitudes
    at all mode frequencies.

    Signature: capture_fn(mode_freqs, carrier_indices, pattern, census_mags)
    Returns: flat array (n_modes,)
    """
    import math
    from picosdk.ps2000 import ps2000

    def capture_fn(mf, carrier_indices, pattern, _census_mags):
        n_modes = len(mf)
        active_freqs = [mf[carrier_indices[b]]
                        for b in range(len(carrier_indices)) if pattern[b] > 0]

        if not active_freqs:
            _awg_off(handle)
            time.sleep(SETTLE_S)
            return np.zeros(n_modes)

        # Build ARB waveform
        arb_len = 4096
        max_freq = max(active_freqs)
        f_rep = max(25.0, math.ceil(max_freq / (arb_len // 2 - 10)))
        delta_phase = int(f_rep * (2**32) / 48_000_000)

        t = np.arange(arb_len) / (arb_len * f_rep)
        waveform = np.zeros(arb_len, dtype=np.float64)
        for freq in active_freqs:
            waveform += np.sin(2 * np.pi * freq * t)

        if np.max(np.abs(waveform)) > 0:
            waveform /= np.max(np.abs(waveform))

        arb_data = (ctypes.c_uint8 * arb_len)(
            *[max(0, min(255, int(127.5 + 127.5 * v))) for v in waveform])

        ps2000.ps2000_set_sig_gen_arbitrary(
            handle, 0, AWG_DRIVE_UVPP, delta_phase, delta_phase, 0, 0,
            arb_data, arb_len, 0, 0)
        time.sleep(SETTLE_S)

        mags = _capture_spectrum(handle, active_freqs[0], mf)

        _awg_off(handle)
        return mags

    return capture_fn


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def run_plate(args, plate_id, handle, mux):
    """Run full benchmark suite on one plate."""
    census = load_census(args.census)
    rkey = f"{plate_id}_NE" if len(PLATE_RELAYS[plate_id]) > 1 else plate_id
    mode_freqs = get_plate_modes(census, plate_id, relay_key=rkey)
    n_modes = len(mode_freqs)

    if not mode_freqs:
        print(f"ERROR: No modes found for plate {plate_id}")
        return None

    n_bits = min(args.n_bits, n_modes)
    carrier_indices = np.linspace(0, n_modes - 1, n_bits, dtype=int).tolist()

    # Census magnitudes (for bittensor viability model, not used in capture)
    results_dict = census.get("results", {})
    census_entry = results_dict.get(rkey, results_dict.get(plate_id, {}))
    peaks = census_entry.get("peaks", [])
    peaks_sorted = sorted(peaks, key=lambda p: p["freq_hz"])
    lo_fix = FIXTURE_FREQ_HZ - FIXTURE_GUARD_HZ
    hi_fix = FIXTURE_FREQ_HZ + FIXTURE_GUARD_HZ
    peaks_sorted = [p for p in peaks_sorted
                    if not (lo_fix <= p["freq_hz"] <= hi_fix)]
    census_mags = np.array([p.get("magnitude", 0.1) for p in peaks_sorted])
    if len(census_mags) != n_modes:
        census_mags = np.ones(n_modes) * 0.1

    name = PLATE_NAMES.get(plate_id, plate_id)
    print(f"\n{'=' * 70}")
    print(f"  PLATE RESERVOIR BENCHMARK — PicoScope TX+RX")
    print(f"  Plate {name} ({n_modes} modes), {n_bits} carrier bits")
    print(f"  Feature mode: {args.feature_mode}")
    print(f"  Mode range: {mode_freqs[0]:.0f} – {mode_freqs[-1]:.0f} Hz")
    print(f"{'=' * 70}")

    # Select relay
    relay_ch = PLATE_RELAYS[plate_id][0][0]
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    # Create capture function
    if args.feature_mode in ("sequential", "seqpoly"):
        capture_fn = make_picoscope_capture_sequential(handle, mode_freqs)
    else:
        capture_fn = make_picoscope_capture_linear(handle, mode_freqs)

    # Run benchmarks
    benchmarks = args.benchmarks.split(",")
    if "all" in benchmarks:
        benchmarks = ["parity", "nonlinear", "capacity"]

    all_results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if "parity" in benchmarks:
        print(f"\n  ── Benchmark: Parity (XOR generalization) ──")
        print(f"  Feature mode: {args.feature_mode}")
        r = benchmark_parity(mode_freqs, carrier_indices, census_mags,
                             capture_fn,
                             n_bits_list=[3, 4, 5, 6, 7],
                             feature_mode=args.feature_mode)
        all_results.extend(r)

    if "nonlinear" in benchmarks:
        print(f"\n  ── Benchmark: Nonlinear function approximation ──")
        r = benchmark_nonlinear(mode_freqs, carrier_indices, census_mags,
                                capture_fn)
        all_results.extend(r)

    if "capacity" in benchmarks:
        print(f"\n  ── Benchmark: Classification capacity ──")
        r = benchmark_capacity(mode_freqs, carrier_indices, census_mags,
                               capture_fn)
        all_results.extend(r)

    # Turn AWG off after benchmarks
    _awg_off(handle)

    # ── Bittensor viability model ──
    # Monkey-patch the module-level POWER_TOTAL_W for accurate power calc
    import plate_benchmark_kronos as _bk
    _orig_power = _bk.POWER_TOTAL_W
    _bk.POWER_TOTAL_W = POWER_TOTAL_W
    try:
        viability = bittensor_viability(all_results, n_modes)
    finally:
        _bk.POWER_TOTAL_W = _orig_power

    print(f"\n{'=' * 70}")
    print(f"  BITTENSOR VIABILITY MODEL (PicoScope)")
    print(f"{'=' * 70}")

    print(f"\n  Power: {viability['power_watts']}W "
          f"({viability['power_ratio_vs_gpu']}× less than GPU)")
    print(f"  Throughput: {viability['queries_per_second']:.1f} queries/sec "
          f"({viability['queries_per_day']:,} /day)")
    print(f"  Latency: {viability['avg_latency_ms']:.0f}ms per inference")
    print(f"  Best accuracy: {viability['best_accuracy_pct']:.1f}%")

    print(f"\n  {'Scenario':<14} {'Daily TAO':>10} {'Daily USD':>10} "
          f"{'Cost':>8} {'Profit':>10} {'Annual':>10}")
    print(f"  {'-' * 65}")
    for label, s in viability["scenarios"].items():
        tag = "OK" if s["profitable"] else "LOSS"
        print(f"  {label:<14} {s['daily_tao']:>10.4f} "
              f"${s['daily_usd']:>9.2f} "
              f"${s['daily_total_cost']:>7.2f} "
              f"${s['daily_profit']:>9.2f} "
              f"${s['annual_profit']:>9.0f} [{tag}]")

    print(f"\n  {viability['breakeven_note']}")

    # ── Save ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate_name": name,
        "plate_id": plate_id,
        "n_modes": n_modes,
        "n_carrier_bits": n_bits,
        "feature_mode": args.feature_mode,
        "capture_device": "picoscope_2204a",
        "tx": "picoscope_awg",
        "rx": "picoscope_ch_a",
        "sample_rate_hz": SAMPLE_RATE,
        "n_avg": N_AVG,
        "awg_drive_uvpp": AWG_DRIVE_UVPP,
        "mode_freqs_hz": mode_freqs,
        "carrier_indices": carrier_indices,
        "benchmarks": all_results,
        "bittensor_viability": viability,
    }

    out_file = LAB_DIR / f"benchmark_picoscope_{name}_{timestamp}.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved: {out_file.name}")

    # Submit to Firestore
    try:
        token = firebase_anon_auth()
        parity_results = [r for r in all_results
                          if r.get("benchmark") == "parity"]
        best_parity = max((r.get("parity_poly_test", r.get("parity_test", 0))
                           for r in parity_results), default=0)

        payload = {
            "experiment_type": "plate-benchmark-picoscope",
            "plate_name": name,
            "plate_id": plate_id,
            "n_modes": n_modes,
            "feature_mode": args.feature_mode,
            "capture_device": "picoscope_2204a",
            "best_parity_pct": best_parity,
            "power_watts": POWER_TOTAL_W,
            "bittensor_viable": viability["scenarios"]["pessimistic"]["profitable"],
            "bittensor_annual_realistic_usd": viability["scenarios"]["realistic"]["annual_profit"],
            "benchmarks": all_results,
            "viability": viability,
        }
        doc_id = submit_experiment(token, payload)
        print_result(doc_id, payload)
    except Exception as e:
        print(f"  Firestore submit failed: {e}")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Plate reservoir benchmark — PicoScope TX+RX")
    parser.add_argument("port", help="Arduino serial port")
    parser.add_argument("--census", required=True, help="Census JSON path")
    parser.add_argument("--plate", default="4", help="Plate ID (1-5)")
    parser.add_argument("--all-plates", action="store_true",
                        help="Run on all 5 plates")
    parser.add_argument("--benchmarks", default="all",
                        help="Comma-separated: parity,nonlinear,capacity,all")
    parser.add_argument("--n-bits", type=int, default=7)
    parser.add_argument("--feature-mode", default="seqpoly",
                        choices=["linear", "poly", "sequential", "seqpoly"],
                        help="Feature extraction mode (default: seqpoly)")
    args = parser.parse_args()

    plates = list(PLATE_NAMES.keys()) if args.all_plates else [args.plate]

    handle = open_scope()
    mux = RelayMux(port=args.port)
    mux.open()

    try:
        for pid in plates:
            run_plate(args, pid, handle, mux)
    finally:
        _awg_off(handle)
        mux.off()
        mux.close()
        close_scope(handle)


if __name__ == "__main__":
    main()
