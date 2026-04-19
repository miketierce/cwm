#!/usr/bin/env python3
"""
Plate Pre-Scan — Hybrid (PicoScope TX + Kronos RX)

Measures ON/OFF separation index for each candidate carrier frequency
by driving individual sine tones through the full hybrid signal path.

For each candidate mode:
  1. Drive PicoScope AWG at freq_hz, 2Vpp  →  record Kronos  →  FFT mag (ON)
  2. AWG off  →  record Kronos  →  FFT mag (OFF)
  3. Separation index = (mean_ON - mean_OFF) / (std_OFF + 1e-12)

Outputs a ranked table and JSON with strong modes (separation > threshold).
The benchmark can then use only verified strong carriers.

This implements the V5 "filter first, then threshold" insight from the
Boolean XOR experiment (lab diary 8 Apr 2026).

Usage:
    python plate_prescan_hybrid.py /dev/cu.usbserial-11310 \\
        --device KRONOS --census <census.json> --plate 4
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

from plate_benchmark_kronos import (
    PLATE_NAMES, PLATE_RELAYS, AUDIO_DTYPE,
    find_audio_device, detect_sample_rate, load_census, get_plate_modes,
)

# ── Config ──
AWG_DRIVE_UVPP = 2_000_000   # 2 Vpp
AWG_SETTLE_S = 0.25           # wait after AWG change
RX_CAPTURE_S = 0.5            # Kronos recording per measurement
N_REPS = 6                    # ON/OFF repetitions per frequency
SETTLE_RELAY_S = 0.10
TOP_N_CANDIDATES = 30         # scan top-N census modes by magnitude
SEP_THRESHOLD = 3.0           # minimum separation index to be "strong"

# ── PicoScope ──
_ps_handle = None
_ps_driver = None


def _open_picoscope():
    global _ps_handle, _ps_driver
    if _ps_handle is not None:
        return
    try:
        from picosdk.ps2000 import ps2000
        handle = ps2000.ps2000_open_unit()
        if handle > 0:
            _ps_handle = handle
            _ps_driver = "ps2000"
            ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
            ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
            print(f"  PicoScope opened (ps2000)", flush=True)
            return
    except Exception:
        pass
    try:
        import ctypes
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok
        handle = ctypes.c_int16()
        assert_pico_ok(ps2000a.ps2000aOpenUnit(ctypes.byref(handle), None))
        _ps_handle = handle
        _ps_driver = "ps2000a"
        assert_pico_ok(ps2000a.ps2000aSetChannel(handle, 0, 1, 1, 5, 0.0))
        print(f"  PicoScope opened (ps2000a)", flush=True)
        return
    except Exception:
        pass
    raise RuntimeError("No PicoScope detected")


def _close_picoscope():
    global _ps_handle, _ps_driver
    if _ps_handle is None:
        return
    _set_awg_off()
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
    if _ps_driver == "ps2000":
        from picosdk.ps2000 import ps2000
        ps2000.ps2000_set_sig_gen_built_in(
            _ps_handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0)
    elif _ps_driver == "ps2000a":
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok
        assert_pico_ok(ps2000a.ps2000aSetSigGenBuiltIn(
            _ps_handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz), 0, 0, 0, 0, 0, 0, 0, 0))


def _set_awg_off():
    if _ps_driver == "ps2000":
        from picosdk.ps2000 import ps2000
        ps2000.ps2000_set_sig_gen_built_in(
            _ps_handle, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0)
    elif _ps_driver == "ps2000a":
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok
        assert_pico_ok(ps2000a.ps2000aSetSigGenBuiltIn(
            _ps_handle, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0))


def kronos_record(sample_rate: int, device_idx: int) -> np.ndarray:
    """Record from Kronos Input 1 (full-duplex playrec with silence)."""
    import sounddevice as sd

    n_samples = int(sample_rate * RX_CAPTURE_S)
    silence = np.zeros((n_samples, 1), dtype=np.float32)
    rx = sd.playrec(silence, samplerate=sample_rate,
                    input_mapping=[1], output_mapping=[1],
                    device=device_idx, dtype=AUDIO_DTYPE,
                    blocking=True)
    return rx[:, 0].astype(np.float64)


def fft_mag_at_freq(waveform: np.ndarray, sample_rate: int,
                    target_hz: float) -> float:
    """Compute FFT magnitude at a specific frequency.

    Uses 4× zero-padded Hanning-windowed FFT, takes max of ±3 bins
    around the target bin (same protocol as plate_reservoir_demo).
    """
    windowed = waveform * np.hanning(len(waveform))
    nfft = len(waveform) * 4
    spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
    bin_hz = freq_axis[1] if len(freq_axis) > 1 else 1.0

    tb = int(round(target_hz / bin_hz))
    lo = max(0, tb - 3)
    hi = min(len(spectrum) - 1, tb + 3)
    return float(np.max(spectrum[lo:hi + 1]))


def prescan_single_freq(freq_hz: float, sample_rate: int, device_idx: int,
                        n_reps: int = N_REPS
                        ) -> dict:
    """Measure ON/OFF FFT magnitude at a single frequency.

    Returns dict with on_mags, off_mags, separation_index, etc.
    """
    on_mags = []
    off_mags = []

    for rep in range(n_reps):
        # ON: drive AWG at freq
        _set_awg_sine(freq_hz)
        time.sleep(AWG_SETTLE_S)
        wav_on = kronos_record(sample_rate, device_idx)
        mag_on = fft_mag_at_freq(wav_on, sample_rate, freq_hz)
        on_mags.append(mag_on)

        # OFF: AWG silent
        _set_awg_off()
        time.sleep(AWG_SETTLE_S)
        wav_off = kronos_record(sample_rate, device_idx)
        mag_off = fft_mag_at_freq(wav_off, sample_rate, freq_hz)
        off_mags.append(mag_off)

    on_arr = np.array(on_mags)
    off_arr = np.array(off_mags)

    on_mean = float(np.mean(on_arr))
    off_mean = float(np.mean(off_arr))
    on_std = float(np.std(on_arr))
    off_std = float(np.std(off_arr))

    # Separation index (Cohen's d variant)
    sep = (on_mean - off_mean) / (off_std + 1e-12)

    # Also compute ratio
    ratio = on_mean / (off_mean + 1e-12)

    return {
        "freq_hz": freq_hz,
        "on_mean": on_mean,
        "off_mean": off_mean,
        "on_std": on_std,
        "off_std": off_std,
        "separation_index": sep,
        "on_off_ratio": ratio,
        "on_mags": on_mags,
        "off_mags": off_mags,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Plate Pre-Scan — Hybrid (PicoScope TX + Kronos RX)")
    parser.add_argument("port", help="Arduino serial port for relay mux")
    parser.add_argument("--device", "-d", default="KRONOS",
                        help="Kronos audio device name")
    parser.add_argument("--census", "-c", required=True,
                        help="Census JSON path (hybrid or Kronos)")
    parser.add_argument("--plate", "-p", default="4",
                        help="Plate ID (1-5)")
    parser.add_argument("--top-n", type=int, default=TOP_N_CANDIDATES,
                        help=f"Number of candidate modes to scan (default {TOP_N_CANDIDATES})")
    parser.add_argument("--reps", type=int, default=N_REPS,
                        help=f"ON/OFF repetitions per freq (default {N_REPS})")
    parser.add_argument("--threshold", type=float, default=SEP_THRESHOLD,
                        help=f"Separation index threshold (default {SEP_THRESHOLD})")

    args = parser.parse_args()

    # Load census
    census = load_census(args.census)
    pid = args.plate

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
        print(f"ERROR: No modes for plate {pid}")
        sys.exit(1)

    # Get census magnitudes
    census_mags = np.array([
        next((p["magnitude"] for p in census["results"][relay_key]["peaks"]
              if abs(p["freq_hz"] - f) < 1.0), 0.0)
        for f in mode_freqs
    ])

    # Select top-N candidates by census magnitude
    n_candidates = min(args.top_n, n_modes)
    ranked = np.argsort(census_mags)[::-1]
    candidate_indices = ranked[:n_candidates]

    name = PLATE_NAMES.get(pid, f"?{pid}")

    print(f"\n{'=' * 70}")
    print(f"  PLATE PRE-SCAN — HYBRID (PicoScope TX + Kronos RX)")
    print(f"  Plate {name} ({n_modes} modes), scanning top {n_candidates}")
    print(f"  {args.reps} ON/OFF reps per frequency")
    print(f"{'=' * 70}\n")

    # Open hardware
    import sounddevice as sd
    from relay_mux import RelayMux

    device_idx = find_audio_device(args.device)
    sample_rate = detect_sample_rate(device_idx)
    print(f"  Kronos: device={device_idx}, rate={sample_rate} Hz", flush=True)

    _open_picoscope()

    mux = RelayMux(port=args.port)
    mux.open()

    relay_ch = PLATE_RELAYS[pid][0][0]
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)
    print(f"  Relay {relay_ch} selected for plate {pid}", flush=True)

    # Run pre-scan
    results = []
    t0 = time.time()

    try:
        for scan_idx, mode_idx in enumerate(candidate_indices):
            freq = mode_freqs[mode_idx]
            cmag = census_mags[mode_idx]
            elapsed = time.time() - t0
            eta = (elapsed / (scan_idx + 1)) * (n_candidates - scan_idx - 1) if scan_idx > 0 else 0

            print(f"\n  [{scan_idx+1}/{n_candidates}] {freq:.0f} Hz "
                  f"(census mag={cmag:.6f}) "
                  f"[{elapsed:.0f}s elapsed, ETA {eta:.0f}s]", flush=True)

            r = prescan_single_freq(freq, sample_rate, device_idx,
                                    n_reps=args.reps)
            r["mode_index"] = int(mode_idx)
            r["census_magnitude"] = float(cmag)
            results.append(r)

            # Live feedback
            sep = r["separation_index"]
            tag = "STRONG" if sep >= args.threshold else "weak"
            print(f"    ON={r['on_mean']:.6f} ± {r['on_std']:.6f}  "
                  f"OFF={r['off_mean']:.6f} ± {r['off_std']:.6f}  "
                  f"sep={sep:.1f}  ratio={r['on_off_ratio']:.2f}  [{tag}]",
                  flush=True)

    finally:
        _set_awg_off()
        mux.off()
        mux.close()
        _close_picoscope()

    total_time = time.time() - t0

    # Sort by separation index descending
    results.sort(key=lambda r: r["separation_index"], reverse=True)

    # Report
    strong = [r for r in results if r["separation_index"] >= args.threshold]
    weak = [r for r in results if r["separation_index"] < args.threshold]

    print(f"\n{'=' * 70}")
    print(f"  PRE-SCAN RESULTS — Plate {name}")
    print(f"  {len(strong)} strong / {len(results)} scanned "
          f"(threshold: sep ≥ {args.threshold})")
    print(f"  Total time: {total_time:.0f}s")
    print(f"{'=' * 70}")

    print(f"\n  {'Rank':<5} {'Freq Hz':<10} {'ON mag':<12} {'OFF mag':<12} "
          f"{'Sep Index':<12} {'ON/OFF':<10} {'Status'}")
    print(f"  {'-' * 75}")
    for i, r in enumerate(results):
        tag = "STRONG" if r["separation_index"] >= args.threshold else "weak"
        print(f"  {i+1:<5} {r['freq_hz']:<10.0f} "
              f"{r['on_mean']:<12.6f} {r['off_mean']:<12.6f} "
              f"{r['separation_index']:<12.1f} "
              f"{r['on_off_ratio']:<10.2f} {tag}")

    if strong:
        print(f"\n  Strong carriers ({len(strong)}):")
        for r in strong:
            print(f"    {r['freq_hz']:.0f} Hz  sep={r['separation_index']:.1f}")
    else:
        print(f"\n  WARNING: No modes above separation threshold {args.threshold}!")
        print(f"  Best mode: {results[0]['freq_hz']:.0f} Hz "
              f"sep={results[0]['separation_index']:.1f}")

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "experiment": "plate_prescan_hybrid",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate_id": pid,
        "plate_name": name,
        "config": {
            "n_candidates": n_candidates,
            "n_reps": args.reps,
            "awg_drive_uvpp": AWG_DRIVE_UVPP,
            "awg_settle_s": AWG_SETTLE_S,
            "rx_capture_s": RX_CAPTURE_S,
            "sample_rate": sample_rate,
            "separation_threshold": args.threshold,
        },
        "total_time_s": total_time,
        "n_strong": len(strong),
        "n_scanned": len(results),
        "strong_freqs_hz": [r["freq_hz"] for r in strong],
        "results": results,
    }

    save_path = RESULTS_DIR / f"prescan_hybrid_{name}_{timestamp}.json"
    with open(save_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved: {save_path.name}")


if __name__ == "__main__":
    main()
