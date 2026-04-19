#!/usr/bin/env python3
"""
Hybrid Census: PicoScope AWG sweep (TX) + Kronos 24-bit ADC (RX).

Drives plates with PicoScope's built-in frequency sweep at 2Vpp,
records on Kronos Input 1, detects resonance peaks.

Physical wiring:
  PicoScope AWG OUT → relay board signal IN → TX PZTs
  RX PZTs → relay board → Kronos Input 1 (rear)

Usage:
    python plate_census_hybrid.py /dev/cu.usbserial-11310 --device KRONOS
    python plate_census_hybrid.py /dev/cu.usbserial-11310 --device KRONOS --plates 4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

# Ensure PicoScope dylib findable on macOS
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

# Reuse constants and helpers from Kronos census
from plate_census_kronos import (
    PLATE_NAMES, PLATE_RELAYS, PREFERRED_SAMPLE_RATES, AUDIO_DTYPE,
    F_START, F_STEP, MIN_SNR_DB, MIN_PROMINENCE_DB,
    detect_modes, analyze_mode_spacing,
)

# ── Hybrid config ──
AWG_DRIVE_UVPP = 2_000_000    # 2Vpp
SWEEP_DURATION_S = 1.0         # chirp duration
SWEEP_START_HZ = 200
SWEEP_STOP_HZ = 96000          # up to Kronos Nyquist at 192 kHz
AWG_SETTLE_S = 0.3             # let sweep reach steady state
CAPTURE_DURATION_S = 1.0       # Kronos recording per sweep
N_AVERAGES = 8
SETTLE_RELAY_S = 0.10

# ── PicoScope AWG ──
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
    _awg_off()
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


def _awg_sweep(start_hz: float, stop_hz: float):
    """Start continuous frequency sweep."""
    dwell = 0.001
    sweep_time = SWEEP_DURATION_S
    increment = (stop_hz - start_hz) * dwell / sweep_time

    if _ps_driver == "ps2000":
        from picosdk.ps2000 import ps2000
        ps2000.ps2000_set_sig_gen_built_in(
            _ps_handle, 0, AWG_DRIVE_UVPP, 0,
            float(start_hz), float(stop_hz),
            float(increment), float(dwell),
            0, 0  # sweep up, continuous
        )
    elif _ps_driver == "ps2000a":
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok
        assert_pico_ok(ps2000a.ps2000aSetSigGenBuiltIn(
            _ps_handle, 0, AWG_DRIVE_UVPP, 0,
            float(start_hz), float(stop_hz),
            float(increment), float(dwell),
            0, 0, 0, 0, 0, 0
        ))


def _awg_sine(freq_hz: float):
    """Set AWG to single frequency."""
    if _ps_driver == "ps2000":
        from picosdk.ps2000 import ps2000
        ps2000.ps2000_set_sig_gen_built_in(
            _ps_handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
        )
    elif _ps_driver == "ps2000a":
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok
        assert_pico_ok(ps2000a.ps2000aSetSigGenBuiltIn(
            _ps_handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz), 0, 0, 0, 0, 0, 0, 0, 0
        ))


def _awg_off():
    """Turn off AWG."""
    try:
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
    except Exception:
        pass


def kronos_record(sample_rate: int, device_idx: int,
                  duration_s: float, n_averages: int = 1) -> np.ndarray:
    """Record from Kronos (playrec with silence — full-duplex required)."""
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


def flash_census_hybrid(mux, plate_id: str, relay_ch: int, rx_label: str,
                        sample_rate: int, device_idx: int,
                        f_stop: int) -> list[dict]:
    """Drive plate with PicoScope multitone (all census frequencies),
    record on Kronos, extract transfer function."""
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    name = PLATE_NAMES[plate_id]
    fft_res = 1.0 / CAPTURE_DURATION_S
    freqs = np.arange(F_START, f_stop + F_STEP, F_STEP, dtype=np.float64)
    freqs_snapped = np.unique(np.round(freqs / fft_res) * fft_res)
    freqs_snapped = freqs_snapped[freqs_snapped >= F_START]
    n_tones = len(freqs_snapped)

    print(f"\n  Plate {name} (relay {relay_ch}, RX-{rx_label}): "
          f"HYBRID FLASH — {n_tones} tones, {CAPTURE_DURATION_S:.1f}s, "
          f"2Vpp PicoScope AWG drive")

    # Use PicoScope sweep to excite all frequencies
    # Sweep continuously while we record on Kronos
    _awg_sweep(float(freqs_snapped[0]), float(freqs_snapped[-1]))
    time.sleep(AWG_SETTLE_S)

    # Record multiple sweeps and average the spectra
    print(f"    Averaging {N_AVERAGES} captures...", flush=True)
    mag_accum = None
    phase_sin = None
    phase_cos = None

    for avg_i in range(N_AVERAGES):
        rx = kronos_record(sample_rate, device_idx, CAPTURE_DURATION_S)

        windowed = rx * np.hanning(len(rx))
        spectrum = np.fft.rfft(windowed)
        fft_mag = np.abs(spectrum)
        fft_phase = np.angle(spectrum)
        freq_axis = np.fft.rfftfreq(len(rx), d=1.0 / sample_rate)

        if mag_accum is None:
            mag_accum = np.zeros_like(fft_mag)
            phase_sin = np.zeros_like(fft_mag)
            phase_cos = np.zeros_like(fft_mag)

        mag_accum += fft_mag
        phase_sin += np.sin(fft_phase)
        phase_cos += np.cos(fft_phase)

        rms = float(np.sqrt(np.mean(rx ** 2)))
        print(f"      [{avg_i+1}/{N_AVERAGES}] RMS={rms:.6f}", flush=True)

    _awg_off()

    mag_avg = mag_accum / N_AVERAGES
    phase_avg = np.arctan2(phase_sin, phase_cos)

    # Extract magnitudes at census frequencies
    bin_hz = freq_axis[1] if len(freq_axis) > 1 else 1.0
    sweep_data = []
    for f in freqs_snapped:
        idx = int(round(f / bin_hz))
        if 0 <= idx < len(mag_avg):
            sweep_data.append({
                "freq_hz": round(float(f), 1),
                "magnitude": round(float(mag_avg[idx]), 6),
                "phase_rad": round(float(phase_avg[idx]), 4),
                "phase_std": 0.0,
            })

    print(f"    Flash census: {len(sweep_data)} bins extracted")
    all_mags = np.array([s["magnitude"] for s in sweep_data])
    if len(all_mags) > 0:
        peak_idx = np.argmax(all_mags)
        peak_f = sweep_data[peak_idx]["freq_hz"]
        peak_m = sweep_data[peak_idx]["magnitude"]
        median_m = float(np.median(all_mags))
        if median_m > 0:
            print(f"    Peak: {peak_f:.0f} Hz (mag={peak_m:.6f}), "
                  f"median={median_m:.6f}, "
                  f"peak/median={peak_m/median_m:.1f}×")

    return sweep_data


def main():
    parser = argparse.ArgumentParser(
        description="Hybrid Census: PicoScope AWG + Kronos RX")
    parser.add_argument("port", help="Arduino serial port")
    parser.add_argument("--device", "-d", default="KRONOS",
                        help="Kronos audio device name")
    parser.add_argument("--plates", "-p", default="1,2,3,4,5",
                        help="Comma-separated plate IDs")

    args = parser.parse_args()

    import sounddevice as sd
    from relay_mux import RelayMux

    # Find Kronos
    hint = args.device.lower()
    device_idx = None
    for i, dev in enumerate(sd.query_devices()):
        if (hint in dev["name"].lower()
                and dev["max_input_channels"] > 0
                and dev["max_output_channels"] > 0):
            device_idx = i
            break
    if device_idx is None:
        print(f"ERROR: No audio device matching '{args.device}'")
        sys.exit(1)

    # Detect sample rate
    sample_rate = None
    for rate in PREFERRED_SAMPLE_RATES:
        try:
            sd.check_input_settings(device=device_idx, channels=1,
                                    dtype=AUDIO_DTYPE, samplerate=rate)
            sd.check_output_settings(device=device_idx, channels=1,
                                     dtype=AUDIO_DTYPE, samplerate=rate)
            sample_rate = rate
            break
        except Exception:
            continue
    if sample_rate is None:
        dev = sd.query_devices(device_idx)
        sample_rate = int(dev["default_samplerate"])

    f_stop = int(sample_rate / 2 - 1000)
    print(f"\n{'='*60}")
    print(f"  HYBRID CENSUS — PicoScope AWG (2Vpp) + Kronos RX (24-bit)")
    print(f"  Kronos: device={device_idx}, rate={sample_rate} Hz")
    print(f"  Frequency range: {F_START}–{f_stop} Hz (step {F_STEP} Hz)")
    print(f"{'='*60}")

    # Open PicoScope
    _open_picoscope()

    # Open relay mux
    mux = RelayMux(port=args.port)
    mux.open()

    plate_ids = [p.strip() for p in args.plates.split(",")]
    results = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        for pid in plate_ids:
            if pid not in PLATE_RELAYS:
                print(f"  Skipping unknown plate {pid}")
                continue
            for relay_ch, rx_label in PLATE_RELAYS[pid]:
                key = f"{pid}_{rx_label}" if rx_label else str(pid)

                sweep_data = flash_census_hybrid(
                    mux, pid, relay_ch, rx_label,
                    sample_rate, device_idx, f_stop)

                peaks = detect_modes(sweep_data)
                spacing = analyze_mode_spacing(peaks)

                results[key] = {
                    "plate_name": PLATE_NAMES[pid],
                    "plate_id": pid,
                    "relay_ch": relay_ch,
                    "rx_path": rx_label,
                    "sweep_data": sweep_data,
                    "peaks": peaks,
                    "mode_stats": spacing,
                }

                n_strong = len([p for p in peaks if p["snr_db"] > 20])
                print(f"    => {len(peaks)} peaks detected, "
                      f"{n_strong} with SNR > 20 dB")

    finally:
        mux.off()
        mux.close()
        _close_picoscope()

    # Save
    output = {
        "experiment": "hybrid_flash_census",
        "timestamp": timestamp,
        "config": {
            "tx_device": "PicoScope 2204A AWG (2Vpp sweep)",
            "rx_device": "Kronos USB Input 1 (24-bit)",
            "sample_rate": sample_rate,
            "f_start": F_START,
            "f_stop": f_stop,
            "f_step": F_STEP,
            "sweep_duration_s": SWEEP_DURATION_S,
            "capture_duration_s": CAPTURE_DURATION_S,
            "n_averages": N_AVERAGES,
            "awg_drive_uvpp": AWG_DRIVE_UVPP,
        },
        "results": results,
    }

    save_path = RESULTS_DIR / f"plate_census_hybrid_flash_{timestamp}.json"
    with open(save_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved: {save_path}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  CENSUS SUMMARY")
    print(f"{'='*60}")
    for key, info in results.items():
        peaks = info["peaks"]
        strong = [p for p in peaks if p["snr_db"] > 20]
        print(f"  {key}: {PLATE_NAMES[info['plate_id']]} "
              f"({info['rx_path']}) — {len(peaks)} peaks, "
              f"{len(strong)} strong (>20dB SNR)")


if __name__ == "__main__":
    main()
