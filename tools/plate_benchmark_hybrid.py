#!/usr/bin/env python3
"""
Plate Reservoir Benchmark — Hybrid PicoScope TX + Kronos RX

Best-of-both-worlds approach:
  TX: PicoScope AWG → 2Vpp drive, clean DDS, direct to relay board
  RX: Kronos Input 1 → 24-bit ADC, unlimited capture, 192 kHz

Eliminates all three Kronos-only limitations:
  1. No USB loopback (TX and RX on separate devices)
  2. Full 2Vpp drive (PicoScope AWG vs ~0.5V headphone)
  3. 24-bit capture (Kronos ADC vs 8-bit PicoScope)

Physical wiring:
  PicoScope AWG OUT → BNC cable → relay board signal IN
  Plate pickup PZTs → relay board → Kronos Input 1 (rear)
  Arduino Nano → relay board control (IN1-IN8)

Reuses benchmark_parity / benchmark_nonlinear / benchmark_capacity
from plate_benchmark_kronos.py — only the capture functions change.

Usage:
    # Hardware mode — full benchmark on plate 4:
    python plate_benchmark_hybrid.py /dev/cu.usbserial-11310 \\
        --device KRONOS --census <census.json> --plate 4 --hardware

    # Simulate (no hardware needed):
    python plate_benchmark_hybrid.py --census <census.json> --simulate

    # Sequential-sine on hardware:
    python plate_benchmark_hybrid.py /dev/cu.usbserial-11310 \\
        --device KRONOS --census <census.json> --plate 4 --hardware \\
        --feature-mode sequential
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

# ── Ensure PicoScope dylib is findable on macOS ──
_MACOS_APP_PATHS = [
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources",
    "/Applications/PicoScope 7 T&M.app/Contents/Resources",
    "/Applications/PicoScope.app/Contents/Resources",
]
if sys.platform == "darwin":
    import os as _os
    _cur = _os.environ.get("DYLD_LIBRARY_PATH", "")
    for _p in _MACOS_APP_PATHS:
        if Path(_p).exists() and _p not in _cur:
            _os.environ["DYLD_LIBRARY_PATH"] = f"{_p}:{_cur}" if _cur else _p
            break

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab"
RESULTS_DIR = LAB_DIR / "plate_exps"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Import shared benchmark functions from the Kronos script
from plate_benchmark_kronos import (
    PLATE_NAMES, PLATE_RELAYS, PREFERRED_SAMPLE_RATES,
    FIXTURE_FREQ_HZ, FIXTURE_GUARD_HZ, N_AVG,
    POWER_ARDUINO_W, POWER_LAPTOP_READOUT_W,
    POWER_GPU_INFERENCE_W, AUDIO_DTYPE,
    find_audio_device, detect_sample_rate, load_census, get_plate_modes,
    simulated_capture, simulated_capture_squared, simulated_capture_sequential,
    benchmark_parity, benchmark_nonlinear, benchmark_capacity,
    bittensor_viability,
)

# ── Hybrid-specific config ──
SETTLE_RELAY_S = 0.10
AWG_SETTLE_S = 0.20          # wait for AWG tone to stabilise after start
RX_CAPTURE_S = 0.5           # Kronos capture duration per measurement
AWG_DRIVE_UVPP = 2_000_000   # 2 Vpp — PicoScope max

# Power estimate (PicoScope replaces Kronos TX, but Kronos still runs for RX)
POWER_PICOSCOPE_W = 0.5      # PicoScope 2204A USB bus power
POWER_KRONOS_RX_W = 2.5      # Kronos still powered for ADC input
POWER_PZT_DRIVE_W = 0.02
POWER_TOTAL_W = (POWER_PZT_DRIVE_W + POWER_PICOSCOPE_W
                 + POWER_KRONOS_RX_W + POWER_ARDUINO_W
                 + POWER_LAPTOP_READOUT_W)


# ══════════════════════════════════════════════════════════════════════
# PicoScope AWG control (TX side)
# ══════════════════════════════════════════════════════════════════════

_ps_handle = None
_ps_driver = None   # "ps2000" or "ps2000a"


def _open_picoscope():
    """Open PicoScope and detect driver. Leaves scope open for reuse."""
    global _ps_handle, _ps_driver

    if _ps_handle is not None:
        return

    # Try ps2000 first (macOS ARM64)
    try:
        from picosdk.ps2000 import ps2000
        handle = ps2000.ps2000_open_unit()
        if handle > 0:
            _ps_handle = handle
            _ps_driver = "ps2000"
            # We don't need Ch A for capture — just AWG output
            # But set channel anyway to keep hardware happy
            ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±500mV
            ps2000.ps2000_set_channel(handle, 1, False, 1, 6)  # Ch B off
            print(f"  PicoScope opened (ps2000 driver)", flush=True)
            return
    except Exception:
        pass

    # Try ps2000a
    try:
        import ctypes
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok

        handle = ctypes.c_int16()
        assert_pico_ok(ps2000a.ps2000aOpenUnit(ctypes.byref(handle), None))
        _ps_handle = handle
        _ps_driver = "ps2000a"
        assert_pico_ok(ps2000a.ps2000aSetChannel(handle, 0, 1, 1, 5, 0.0))
        print(f"  PicoScope opened (ps2000a driver)", flush=True)
        return
    except Exception:
        pass

    raise RuntimeError("No PicoScope detected. Check USB connection.")


def _close_picoscope():
    """Close PicoScope and turn off AWG."""
    global _ps_handle, _ps_driver

    if _ps_handle is None:
        return

    try:
        _set_awg_off()
    except Exception:
        pass

    if _ps_driver == "ps2000":
        from picosdk.ps2000 import ps2000
        ps2000.ps2000_stop(_ps_handle)
        ps2000.ps2000_close_unit(_ps_handle)
    elif _ps_driver == "ps2000a":
        from picosdk.ps2000a import ps2000a
        ps2000a.ps2000aStop(_ps_handle)
        ps2000a.ps2000aCloseUnit(_ps_handle)

    _ps_handle = None
    _ps_driver = None


def _set_awg_sine(freq_hz: float):
    """Start AWG at a single frequency, 2Vpp, continuous."""
    if _ps_driver == "ps2000":
        from picosdk.ps2000 import ps2000
        ps2000.ps2000_set_sig_gen_built_in(
            _ps_handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz),
            0.0, 0.0, 0, 0
        )
    elif _ps_driver == "ps2000a":
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok
        assert_pico_ok(ps2000a.ps2000aSetSigGenBuiltIn(
            _ps_handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz),
            0, 0, 0, 0, 0, 0, 0, 0
        ))


def _set_awg_multitone(freqs_hz: list[float]):
    """Start AWG with multitone arbitrary waveform, 2Vpp, continuous.

    Uses 4096-sample buffer at 10 Hz repetition rate.
    Each target freq becomes an integer harmonic of f_rep.
    """
    import ctypes

    arb_len = 4096
    # f_rep must be high enough that all target frequencies fit below
    # Nyquist = arb_len/2 * f_rep.  Census step is 25 Hz, so f_rep=25
    # gives Nyquist = 2048*25 = 51200 Hz — plenty for 22-24 kHz modes.
    f_rep = 25.0
    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    buf = np.zeros(arb_len, dtype=np.float64)
    for f in freqs_hz:
        if f <= 0:
            continue
        k = round(f / f_rep)
        if k < 1 or k > arb_len // 2:
            print(f"  WARNING: {f} Hz out of arb range (max {arb_len//2 * f_rep} Hz)")
            continue
        phase = 2 * np.pi * k * np.arange(arb_len) / arb_len
        buf += np.sin(phase)

    peak = np.max(np.abs(buf))
    if peak > 0:
        buf /= peak

    if _ps_driver == "ps2000":
        from picosdk.ps2000 import ps2000
        arb_u8 = ((buf * 127) + 128).clip(0, 255).astype(np.uint8)
        arb_c = (ctypes.c_uint8 * arb_len)(*arb_u8.tolist())
        ps2000.ps2000_set_sig_gen_arbitrary(
            _ps_handle, 0, AWG_DRIVE_UVPP,
            delta_phase, delta_phase,
            0, 0, arb_c, arb_len, 0, 0
        )
    elif _ps_driver == "ps2000a":
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok
        arb_i16 = (buf * 32767).astype(np.int16)
        arb_c = (ctypes.c_int16 * arb_len)(*arb_i16.tolist())
        assert_pico_ok(ps2000a.ps2000aSetSigGenArbitrary(
            _ps_handle, 0, AWG_DRIVE_UVPP,
            delta_phase, delta_phase,
            0, 0, arb_c, arb_len, 0, 0, 0, 0, 0, 0, 0, 0
        ))


def _set_awg_off():
    """Turn off AWG output."""
    if _ps_driver == "ps2000":
        from picosdk.ps2000 import ps2000
        ps2000.ps2000_set_sig_gen_built_in(
            _ps_handle, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0
        )
    elif _ps_driver == "ps2000a":
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok
        assert_pico_ok(ps2000a.ps2000aSetSigGenBuiltIn(
            _ps_handle, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0
        ))


# ══════════════════════════════════════════════════════════════════════
# Kronos RX capture (record-only, no playback)
# ══════════════════════════════════════════════════════════════════════

def kronos_record(sample_rate: int, device_idx: int,
                  duration_s: float = RX_CAPTURE_S,
                  n_averages: int = N_AVG) -> np.ndarray:
    """Record from Kronos Input 1 while PicoScope drives TX.

    Uses playrec with silence output — Kronos requires full-duplex
    (input+output) streams; input-only sd.rec() fails with PortAudio
    error -9986 on macOS AUHAL.

    Returns averaged raw waveform.
    """
    import sounddevice as sd

    n_samples = int(sample_rate * duration_s)
    silence = np.zeros((n_samples, 1), dtype=np.float32)
    accum = None

    for _ in range(n_averages):
        rx = sd.playrec(silence, samplerate=sample_rate,
                        input_mapping=[1], output_mapping=[1],
                        device=device_idx, dtype=AUDIO_DTYPE,
                        blocking=True)
        mono = rx[:, 0].astype(np.float64)
        if accum is None:
            accum = np.zeros_like(mono)
        accum += mono

    return accum / n_averages


def extract_mode_mags(waveform: np.ndarray, sample_rate: int,
                      mode_freqs: list[float]) -> np.ndarray:
    """FFT a waveform and extract magnitudes at specified frequencies."""
    windowed = waveform * np.hanning(len(waveform))
    nfft = len(waveform) * 4
    spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
    bin_hz = freq_axis[1] if len(freq_axis) > 1 else 1.0

    mags = np.zeros(len(mode_freqs))
    for j, f in enumerate(mode_freqs):
        tb = int(round(f / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(spectrum) - 1, tb + 3)
        mags[j] = float(np.max(spectrum[lo:hi + 1]))
    return mags


# ══════════════════════════════════════════════════════════════════════
# Hybrid capture functions (PicoScope TX → plate → Kronos RX)
# ══════════════════════════════════════════════════════════════════════

def hybrid_capture(mode_freqs: list[float], carrier_indices: list[int],
                   pattern: np.ndarray,
                   sample_rate: int, device_idx: int,
                   noise_ref: np.ndarray | None = None) -> np.ndarray:
    """Multitone drive via PicoScope AWG, capture on Kronos.

    Drives all active carriers simultaneously as a multitone arb waveform,
    then records on Kronos and extracts mode magnitudes.
    """
    active_freqs = [mode_freqs[carrier_indices[b]]
                    for b in range(len(carrier_indices))
                    if pattern[b] > 0]

    if active_freqs:
        _set_awg_multitone(active_freqs)
    else:
        _set_awg_off()
    time.sleep(AWG_SETTLE_S)

    # Record on Kronos
    waveform = kronos_record(sample_rate, device_idx)

    # Subtract noise reference if available
    if noise_ref is not None:
        min_len = min(len(waveform), len(noise_ref))
        waveform = waveform[:min_len] - noise_ref[:min_len]

    _set_awg_off()

    return extract_mode_mags(waveform, sample_rate, mode_freqs)


def hybrid_capture_sequential(mode_freqs: list[float],
                              carrier_indices: list[int],
                              pattern: np.ndarray,
                              sample_rate: int, device_idx: int,
                              noise_ref: np.ndarray | None = None
                              ) -> np.ndarray:
    """Sequential-sine via PicoScope AWG, capture on Kronos.

    Drives ONE carrier at a time at full 2Vpp, records response at all
    mode frequencies. Produces N_carriers × N_modes cross-coupling matrix.

    This replicates the protocol that achieved separation indices >3,000
    on the PicoScope-only setup, but with 24-bit Kronos ADC.
    """
    n_modes = len(mode_freqs)
    n_carriers = len(carrier_indices)
    cross_matrix = np.zeros((n_carriers, n_modes))

    for b in range(n_carriers):
        if pattern[b] > 0:
            freq = mode_freqs[carrier_indices[b]]
            _set_awg_sine(freq)
            state = f"ON @{freq:.0f}Hz"
        else:
            _set_awg_off()
            state = "OFF"
        time.sleep(AWG_SETTLE_S)

        waveform = kronos_record(sample_rate, device_idx)
        rms = float(np.sqrt(np.mean(waveform ** 2)))

        if noise_ref is not None:
            min_len = min(len(waveform), len(noise_ref))
            waveform = waveform[:min_len] - noise_ref[:min_len]

        cross_matrix[b, :] = extract_mode_mags(waveform, sample_rate,
                                                mode_freqs)
        print(f"        carrier {b+1}/{n_carriers} {state} RMS={rms:.6f}",
              flush=True)

    _set_awg_off()
    return cross_matrix.ravel()


def capture_noise_reference(sample_rate: int, device_idx: int) -> np.ndarray:
    """Capture ambient noise floor with AWG off.

    No relay switching needed — this captures whatever leaks through
    when PicoScope AWG is silent. Should be near-zero since there's
    no USB loopback in the hybrid setup.
    """
    _set_awg_off()
    time.sleep(SETTLE_RELAY_S)
    print("  Capturing noise reference (AWG off)...", flush=True)
    ref = kronos_record(sample_rate, device_idx, n_averages=N_AVG)
    rms = float(np.sqrt(np.mean(ref ** 2)))
    print(f"  Noise ref RMS = {rms:.6f}", flush=True)
    return ref


# ══════════════════════════════════════════════════════════════════════
# CLI + main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate Reservoir Benchmark — Hybrid PicoScope TX + Kronos RX")
    parser.add_argument("port", nargs="?", default=None,
                        help="Arduino serial port for relay mux")
    parser.add_argument("--device", "-d", default="KRONOS",
                        help="Kronos audio device name (for RX capture)")
    parser.add_argument("--census", "-c", required=True,
                        help="Census JSON path")
    parser.add_argument("--plate", "-p", default="4",
                        help="Plate ID (1-5)")
    parser.add_argument("--hardware", action="store_true",
                        help="Use real PicoScope + Kronos hardware")
    parser.add_argument("--simulate", action="store_true",
                        help="Simulate from census data (default)")
    parser.add_argument("--benchmarks", "-b", default="parity",
                        help="Comma-separated: parity,nonlinear,capacity,all")
    parser.add_argument("--n-bits", type=int, default=7,
                        help="Max carrier bits for parity")
    parser.add_argument("--feature-mode", default="linear",
                        choices=["linear", "squared", "combined", "poly",
                                 "sequential", "seqpoly"],
                        help="Feature extraction mode")

    args = parser.parse_args()
    if not args.hardware and not args.simulate:
        args.simulate = True

    # Load census
    census = load_census(args.census)
    pid = args.plate
    name = PLATE_NAMES.get(pid, f"?{pid}")

    relay_key = None
    for rch, rlabel in PLATE_RELAYS.get(pid, []):
        key = f"{pid}_{rlabel}" if rlabel else str(pid)
        if key in census.get("results", {}):
            relay_key = key
            break
    if relay_key is None:
        relay_key = str(pid)

    mode_freqs = get_plate_modes(census, pid, relay_key)
    n_modes = len(mode_freqs)
    if n_modes == 0:
        print(f"ERROR: No modes found for plate {pid} ({name})")
        sys.exit(1)

    n_bits = min(args.n_bits, n_modes)
    census_mags = np.array([
        next((p["magnitude"] for p in
              census["results"][relay_key]["peaks"]
              if abs(p["freq_hz"] - f) < 1.0), 0.0)
        for f in mode_freqs
    ])

    # Select carriers from STRONGEST peaks (by magnitude), not lowest freq.
    # This ensures we drive at actual mechanical resonances.
    ranked = np.argsort(census_mags)[::-1]  # descending magnitude
    carrier_indices = sorted(ranked[:n_bits].tolist())  # keep freq-sorted

    carrier_freqs = [mode_freqs[i] for i in carrier_indices]
    carrier_mags = [census_mags[i] for i in carrier_indices]

    print(f"\n{'=' * 70}")
    print(f"  PLATE RESERVOIR BENCHMARK — HYBRID (PicoScope TX + Kronos RX)")
    print(f"  Plate {name} ({n_modes} modes), {n_bits} carrier bits")
    print(f"  Mode: {'HARDWARE' if args.hardware else 'SIMULATION'}")
    print(f"  Carriers (strongest peaks):")
    for ci_idx, ci_val in enumerate(carrier_indices):
        print(f"    bit {ci_idx}: mode[{ci_val}] = {carrier_freqs[ci_idx]:.0f} Hz "
              f"(mag={carrier_mags[ci_idx]:.6f})")
    print(f"{'=' * 70}")

    # Set up capture function
    mux = None
    device_idx = None
    sample_rate = None

    if args.hardware:
        import sounddevice as sd
        from relay_mux import RelayMux

        if not args.port:
            print("ERROR: --port required for hardware mode")
            sys.exit(1)

        # Open Kronos for RX
        device_idx = find_audio_device(args.device)
        sample_rate = detect_sample_rate(device_idx)
        print(f"  Kronos RX: device={device_idx}, "
              f"rate={sample_rate} Hz", flush=True)

        # Open PicoScope for TX
        _open_picoscope()

        # Open relay mux
        mux = RelayMux(port=args.port)
        mux.open()

        relay_ch = PLATE_RELAYS[pid][0][0]

        # Capture noise reference with AWG off, relay off
        noise_ref = capture_noise_reference(sample_rate, device_idx)

        # Select plate relay
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        if args.feature_mode in ("sequential", "seqpoly"):
            def capture_fn(mf, ci, pat, _cm):
                return hybrid_capture_sequential(
                    mf, ci, pat, sample_rate, device_idx,
                    noise_ref=noise_ref)
        else:
            def capture_fn(mf, ci, pat, _cm):
                return hybrid_capture(
                    mf, ci, pat, sample_rate, device_idx,
                    noise_ref=noise_ref)
    else:
        # Simulation mode — same as Kronos-only
        if args.feature_mode in ("squared", "combined"):
            def capture_fn(mf, ci, pat, cm):
                return simulated_capture_squared(mf, ci, pat, cm)
        elif args.feature_mode in ("sequential", "seqpoly"):
            def capture_fn(mf, ci, pat, cm):
                return simulated_capture_sequential(mf, ci, pat, cm)
        else:
            def capture_fn(mf, ci, pat, cm):
                return simulated_capture(mf, ci, pat, cm)

    # Run benchmarks
    benchmarks = args.benchmarks.split(",")
    if "all" in benchmarks:
        benchmarks = ["parity", "nonlinear", "capacity"]

    all_results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        if "parity" in benchmarks:
            print(f"\n  ── Benchmark: Parity (XOR generalization) ──")
            print(f"  Feature mode: {args.feature_mode}")
            r = benchmark_parity(mode_freqs, carrier_indices, census_mags,
                                 capture_fn,
                                 n_bits_list=list(range(3, n_bits + 1)),
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

    finally:
        if mux:
            mux.off()
            mux.close()
        _close_picoscope()

    # ── Bittensor viability model ──
    print(f"\n{'=' * 70}")
    print(f"  BITTENSOR VIABILITY MODEL")
    print(f"{'=' * 70}")

    viability = bittensor_viability(all_results, n_modes)

    print(f"\n  Power: {POWER_TOTAL_W}W "
          f"({POWER_GPU_INFERENCE_W / POWER_TOTAL_W:.1f}× less than GPU)")
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
        "plate_id": pid,
        "n_modes": n_modes,
        "n_carrier_bits": n_bits,
        "mode": "hybrid_hardware" if args.hardware else "simulation",
        "tx_device": "PicoScope 2204A AWG (2Vpp)",
        "rx_device": "Kronos USB Input 1 (24-bit)",
        "benchmarks": all_results,
        "viability": viability,
    }

    save_path = RESULTS_DIR / f"benchmark_hybrid_{name}_{timestamp}.json"
    with open(save_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved: {save_path.name}")


if __name__ == "__main__":
    main()
