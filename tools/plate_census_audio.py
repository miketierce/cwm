#!/usr/bin/env python3
"""
Hybrid Mode Census: PicoScope AWG (TX drive) + USB Audio Interface (RX capture).

Replaces the 8-bit PicoScope ADC readout with a 24-bit USB audio interface
(e.g. Korg Kronos, MAONO PS22, EBXYA 2×2) for dramatically improved dynamic
range (~100 dB vs 48 dB).

Hardware setup:
    PicoScope AWG → all TX PZTs (parallel, unchanged from baseline)
    Relay mux common → audio interface IN 1 (via 1/4" TRS cable)
    Arduino (USB serial) → relay switching (unchanged)

The PicoScope is NOT used for capture — only for signal generation.
Existing PicoScope-only scripts (plate_mode_census.py, etc.) are untouched.

Usage:
    python plate_census_audio.py <serial_port> [--device DEVICE_NAME]
    python plate_census_audio.py /dev/cu.usbserial-11310
    python plate_census_audio.py /dev/cu.usbserial-11310 --device "KRONOS"
    python plate_census_audio.py /dev/cu.usbserial-11310 --list-devices
    python plate_census_audio.py /dev/cu.usbserial-11310 --plates 5
    python plate_census_audio.py /dev/cu.usbserial-11310 --plates 3,4,5

Requires:
    pip install sounddevice pyserial picosdk numpy
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

# ── Paths ──
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import cwm_picoscope  # noqa: F401 — triggers _ensure_dyld_path()

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab"
RESULTS_DIR = LAB_DIR / "plate_exps"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ── Plate config (same as plate_mode_census.py) ──
PLATE_NAMES = {"1": "A", "2": "B", "3": "G", "4": "D", "5": "H"}

PLATE_RELAYS = {
    "1": [(1, "NE")],
    "2": [(2, "NE")],
    "3": [(3, "NE"), (4, "NW")],
    "4": [(5, "NE"), (6, "NW")],
    "5": [(7, "NE"), (8, "NW")],
}

# ── Audio capture config ──
# Kronos USB audio is 48 kHz; a 192 kHz interface would allow higher.
# The script auto-detects the device's max sample rate.
PREFERRED_SAMPLE_RATES = [192000, 96000, 48000, 44100]
AUDIO_CHANNELS = 1        # mono (relay mux feeds one channel)
AUDIO_INPUT_CH = 1        # which input channel to use (1-based for the device)
AUDIO_DTYPE = "float32"   # 24-bit interfaces deliver float32 via Core Audio

# ── Sweep config ──
F_START = 200             # Hz
F_STEP = 25               # Hz
N_AVG = 4                 # CW averages per frequency point
SETTLE_S = 0.05           # settle time after AWG frequency change
SETTLE_RELAY_S = 0.10     # settle time after relay switch
CAPTURE_S = 0.04          # recording duration per point (40 ms = ~25 Hz resolution)

# ── Peak detection ──
MIN_SNR_DB = 6.0
MIN_PROMINENCE_DB = 3.0


# ── Audio device helpers ──

def list_audio_devices():
    """Print all available audio input devices."""
    print("\nAvailable audio input devices:")
    print(f"  {'#':>3}  {'Name':<50}  {'Inputs':>6}  {'Rate':>8}")
    print(f"  {'─'*3}  {'─'*50}  {'─'*6}  {'─'*8}")
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            print(f"  {i:3d}  {dev['name']:<50}  "
                  f"{dev['max_input_channels']:>6}  "
                  f"{dev['default_samplerate']:>8.0f}")
    print()


def find_audio_device(name_hint: str | None = None) -> int:
    """Find the best audio input device.

    If name_hint is given, find a device whose name contains that string.
    Otherwise, use the system default input device.
    """
    if name_hint:
        hint_lower = name_hint.lower()
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0 and hint_lower in dev["name"].lower():
                return i
        raise RuntimeError(
            f"No audio input device matching '{name_hint}'. "
            f"Run with --list-devices to see available devices."
        )
    # Use system default
    default = sd.default.device[0]
    if default is None or default < 0:
        raise RuntimeError(
            "No default audio input device found. "
            "Run with --list-devices to see available devices."
        )
    return int(default)


def detect_sample_rate(device_idx: int) -> int:
    """Find the highest supported sample rate for a device."""
    for rate in PREFERRED_SAMPLE_RATES:
        try:
            sd.check_input_settings(
                device=device_idx,
                channels=AUDIO_CHANNELS,
                dtype=AUDIO_DTYPE,
                samplerate=rate,
            )
            return rate
        except sd.PortAudioError:
            continue
    # Fallback: use device's default
    dev_info = sd.query_devices(device_idx)
    return int(dev_info["default_samplerate"])


# ── PicoScope AWG-only helpers (no ADC capture) ──

def _open_scope_awg_only():
    """Open PicoScope just for the AWG — no ADC channel setup needed."""
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    print("  PicoScope opened (AWG only — ADC not used)")
    return handle


def _set_awg_freq(handle, freq_hz: float):
    """Set PicoScope AWG to a CW tone at the given frequency."""
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )


def _awg_off(handle):
    """Turn off the AWG."""
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
    except Exception:
        pass


def _close_scope(handle):
    """Clean shutdown of PicoScope."""
    from picosdk.ps2000 import ps2000
    _awg_off(handle)
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("  PicoScope closed")


# ── Audio capture ──

def capture_at_freq(handle, freq_hz: float, sample_rate: int,
                    device_idx: int) -> tuple[float, float]:
    """Drive AWG at freq_hz, record via audio interface, return (magnitude, phase).

    Records CAPTURE_S seconds, windows, FFTs, extracts the bin at freq_hz.
    """
    _set_awg_freq(handle, freq_hz)
    time.sleep(SETTLE_S)

    n_samples = int(sample_rate * CAPTURE_S)

    # Record
    recording = sd.rec(
        frames=n_samples,
        samplerate=sample_rate,
        channels=AUDIO_CHANNELS,
        dtype=AUDIO_DTYPE,
        device=device_idx,
        blocking=True,
    )

    # Extract mono signal
    sig = recording[:, 0].astype(np.float64)

    # Window + FFT
    windowed = sig * np.hanning(len(sig))
    nfft = len(sig) * 4  # 4× zero-pad for interpolation
    spectrum = np.fft.rfft(windowed, n=nfft)
    fft_mag = np.abs(spectrum)
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)

    # Find the bin closest to our drive frequency
    bin_hz = freq_axis[1] - freq_axis[0]
    target_bin = int(round(freq_hz / bin_hz))
    lo = max(0, target_bin - 3)
    hi = min(len(fft_mag) - 1, target_bin + 3)
    peak_bin = lo + int(np.argmax(fft_mag[lo:hi + 1]))

    magnitude = float(fft_mag[peak_bin])
    phase = float(np.angle(spectrum[peak_bin]))
    return magnitude, phase


# ── Sweep ──

def sweep_plate(handle, mux, plate_id: str, relay_ch: int,
                rx_label: str, sample_rate: int, device_idx: int,
                f_stop: int) -> list[dict]:
    """CW sweep for one plate/relay using audio interface capture."""
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    freqs = np.arange(F_START, f_stop + F_STEP, F_STEP)
    name = PLATE_NAMES[plate_id]
    n_pts = len(freqs)
    print(f"\n  Plate {name} (relay {relay_ch}, RX-{rx_label}): "
          f"sweep {F_START}–{f_stop} Hz, {F_STEP} Hz steps ({n_pts} pts)")

    sweep_data = []
    t0 = time.time()

    for i, freq in enumerate(freqs):
        mags = []
        phases = []
        for _ in range(N_AVG):
            mag, phase = capture_at_freq(handle, freq, sample_rate, device_idx)
            mags.append(mag)
            phases.append(phase)

        avg_mag = float(np.mean(mags))
        avg_phase = float(np.arctan2(
            np.mean(np.sin(phases)), np.mean(np.cos(phases))
        ))
        phase_std = float(np.std(np.unwrap(phases)))

        sweep_data.append({
            "freq_hz": round(float(freq), 1),
            "magnitude": round(avg_mag, 6),
            "phase_rad": round(avg_phase, 4),
            "phase_std": round(phase_std, 4),
        })

        if i % 40 == 0:
            elapsed = time.time() - t0
            pct = (i + 1) / n_pts * 100
            print(f"    {freq:7.0f} Hz: mag={avg_mag:12.6f}  "
                  f"[{pct:4.1f}% | {elapsed:.0f}s]", flush=True)

    elapsed = time.time() - t0
    print(f"    Sweep complete: {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    return sweep_data


# ── Peak detection (same algorithm as plate_mode_census.py) ──

def detect_modes(sweep_data: list[dict]) -> list[dict]:
    """Detect resonance peaks with SNR and local prominence."""
    mags = np.array([s["magnitude"] for s in sweep_data])
    freqs = np.array([s["freq_hz"] for s in sweep_data])
    phases = np.array([s["phase_rad"] for s in sweep_data])
    phase_stds = np.array([s["phase_std"] for s in sweep_data])

    noise_floor = float(np.median(mags))
    if noise_floor <= 0:
        noise_floor = 1e-10

    peaks = []
    for i in range(2, len(mags) - 2):
        if not (mags[i] > mags[i - 1] and mags[i] > mags[i + 1]):
            continue

        snr_db = 20 * math.log10(mags[i] / noise_floor) if mags[i] > 0 else 0
        if snr_db < MIN_SNR_DB:
            continue

        local_min = min(mags[i - 2], mags[i - 1], mags[i + 1], mags[i + 2])
        if local_min > 0:
            prominence_db = 20 * math.log10(mags[i] / local_min)
        else:
            prominence_db = snr_db
        if prominence_db < MIN_PROMINENCE_DB:
            continue

        peaks.append({
            "freq_hz": float(freqs[i]),
            "magnitude": float(mags[i]),
            "snr_db": round(snr_db, 1),
            "prominence_db": round(prominence_db, 1),
            "phase_rad": round(float(phases[i]), 4),
            "phase_std": round(float(phase_stds[i]), 4),
        })

    peaks.sort(key=lambda p: p["magnitude"], reverse=True)
    return peaks


def analyze_mode_spacing(peaks: list[dict]) -> dict:
    """Compute mode density and spacing statistics."""
    if len(peaks) < 2:
        return {"n_modes": len(peaks)}

    freqs_sorted = sorted([p["freq_hz"] for p in peaks])
    spacings = [freqs_sorted[i + 1] - freqs_sorted[i]
                for i in range(len(freqs_sorted) - 1)]

    return {
        "n_modes": len(peaks),
        "freq_min_hz": freqs_sorted[0],
        "freq_max_hz": freqs_sorted[-1],
        "bandwidth_hz": freqs_sorted[-1] - freqs_sorted[0],
        "mean_spacing_hz": round(float(np.mean(spacings)), 1),
        "median_spacing_hz": round(float(np.median(spacings)), 1),
        "min_spacing_hz": round(float(np.min(spacings)), 1),
        "max_spacing_hz": round(float(np.max(spacings)), 1),
        "modes_per_khz": round(
            len(peaks) / ((freqs_sorted[-1] - freqs_sorted[0]) / 1000), 2
        ),
    }


# ── Main ──

def run_census(args):
    from relay_mux import RelayMux

    # Resolve audio device
    device_idx = find_audio_device(args.device)
    dev_info = sd.query_devices(device_idx)
    sample_rate = detect_sample_rate(device_idx)
    f_stop = int(sample_rate / 2) - 1000  # stay 1 kHz below Nyquist

    print("\n" + "=" * 70)
    print("  HYBRID MODE CENSUS: PicoScope AWG + Audio Interface RX")
    print(f"  Audio device: {dev_info['name']}")
    print(f"  Sample rate: {sample_rate} Hz → Nyquist: {sample_rate // 2} Hz")
    print(f"  Sweep range: {F_START} – {f_stop} Hz, {F_STEP} Hz steps")
    print(f"  ADC depth: 24-bit (~100 dB dynamic range)")
    print("=" * 70)

    # Resolve which plates to sweep
    plate_ids = args.plates.split(",") if args.plates else list(PLATE_RELAYS.keys())
    for pid in plate_ids:
        if pid not in PLATE_RELAYS:
            print(f"ERROR: unknown plate ID '{pid}'. Valid: {list(PLATE_RELAYS.keys())}")
            sys.exit(1)

    handle = _open_scope_awg_only()
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {mux.port}")

    all_results = {}
    t_start = time.time()

    for pid in plate_ids:
        name = PLATE_NAMES[pid]
        relays = PLATE_RELAYS[pid]

        for relay_ch, rx_label in relays:
            rkey = pid if len(relays) == 1 else f"{pid}_{rx_label}"

            print(f"\n{'─' * 70}")
            print(f"  PLATE {name} — RX-{rx_label} (relay {relay_ch})")
            print(f"{'─' * 70}")

            sweep_data = sweep_plate(
                handle, mux, pid, relay_ch, rx_label,
                sample_rate, device_idx, f_stop,
            )
            peaks = detect_modes(sweep_data)
            stats = analyze_mode_spacing(peaks)

            print(f"  Detected {len(peaks)} modes (SNR > {MIN_SNR_DB} dB, "
                  f"prominence > {MIN_PROMINENCE_DB} dB)")
            if stats.get("modes_per_khz"):
                print(f"  Mode density: {stats['modes_per_khz']:.1f} modes/kHz "
                      f"({stats['freq_min_hz']:.0f}–{stats['freq_max_hz']:.0f} Hz)")

            # Print top 20 modes
            print(f"\n  Top 20 modes:")
            print(f"    {'#':>3}  {'Freq (Hz)':>10}  {'Magnitude':>12}  "
                  f"{'SNR (dB)':>8}  {'Prom (dB)':>9}  {'Phase':>11}")
            for i, p in enumerate(peaks[:20]):
                print(f"    {i+1:3d}  {p['freq_hz']:10.1f}  {p['magnitude']:12.6f}  "
                      f"{p['snr_db']:8.1f}  {p['prominence_db']:9.1f}  "
                      f"{p['phase_rad']:11.4f}")

            all_results[rkey] = {
                "plate_name": name,
                "plate_id": pid,
                "relay_ch": relay_ch,
                "rx_path": rx_label,
                "sweep_data": sweep_data,
                "peaks": peaks,
                "stats": stats,
            }

    # Cleanup
    mux.off()
    _close_scope(handle)

    elapsed = time.time() - t_start

    # Summary
    result_keys = sorted(all_results.keys())
    print(f"\n{'=' * 70}")
    print(f"  HYBRID CENSUS SUMMARY — {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"  Audio: {dev_info['name']} @ {sample_rate} Hz, 24-bit")
    print(f"{'=' * 70}")
    print(f"  {'Key':<8} {'Plate':<6} {'RX':<4} {'Modes':<7} {'Range (kHz)':<16} "
          f"{'Density (/kHz)':<15} {'Min Δf (Hz)':<12} {'Top Mode (kHz)'}")
    print(f"  {'─'*8} {'─'*6} {'─'*4} {'─'*7} {'─'*16} {'─'*15} {'─'*12} {'─'*15}")

    for rkey in result_keys:
        r = all_results[rkey]
        s = r["stats"]
        top = r["peaks"][0]["freq_hz"] / 1000 if r["peaks"] else 0
        n = s["n_modes"]
        flo = s.get("freq_min_hz", 0) / 1000
        fhi = s.get("freq_max_hz", 0) / 1000
        density = s.get("modes_per_khz", 0)
        min_df = s.get("min_spacing_hz", 0)
        print(f"  {rkey:<8} {r['plate_name']:<6} {r['rx_path']:<4} {n:<7} "
              f"{flo:5.1f}–{fhi:5.1f} kHz  "
              f"{density:<15.1f} {min_df:<12.0f} {top:5.1f}")

    # Save summary (same format as plate_mode_census.py for compatibility)
    out_path = RESULTS_DIR / f"plate_census_audio_{TIMESTAMP}.json"
    summary_results = {}
    for rkey, r in all_results.items():
        summary_results[rkey] = {
            "plate_name": r["plate_name"],
            "plate_id": r["plate_id"],
            "relay_ch": r["relay_ch"],
            "rx_path": r["rx_path"],
            "peaks": r["peaks"],
            "stats": r["stats"],
            "sweep_n_points": len(r["sweep_data"]),
        }

    save_data = {
        "experiment": "Hybrid Mode Census: PicoScope AWG + Audio Interface RX",
        "timestamp": TIMESTAMP,
        "elapsed_s": round(elapsed, 1),
        "config": {
            "f_start": F_START,
            "f_stop": f_stop,
            "f_step": F_STEP,
            "n_avg": N_AVG,
            "capture_s": CAPTURE_S,
            "min_snr_db": MIN_SNR_DB,
            "min_prominence_db": MIN_PROMINENCE_DB,
            "audio_device": dev_info["name"],
            "audio_sample_rate": sample_rate,
            "audio_bit_depth": 24,
            "plate_relays": {pid: [(ch, rx) for ch, rx in rl]
                             for pid, rl in PLATE_RELAYS.items()},
        },
        "results": summary_results,
    }
    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Summary saved: {out_path}")

    # Full sweep data
    sweep_path = RESULTS_DIR / f"plate_census_audio_sweeps_{TIMESTAMP}.json"
    sweep_save = {}
    for rkey, r in all_results.items():
        sweep_save[rkey] = {
            "plate_name": r["plate_name"],
            "plate_id": r["plate_id"],
            "relay_ch": r["relay_ch"],
            "rx_path": r["rx_path"],
            "sweep_data": r["sweep_data"],
        }
    with open(sweep_path, "w") as f:
        json.dump(sweep_save, f, indent=2, default=str)
    print(f"  Full sweep data: {sweep_path}")

    return save_data


def main():
    parser = argparse.ArgumentParser(
        description="Hybrid Mode Census: PicoScope AWG + USB Audio Interface RX"
    )
    parser.add_argument("port", nargs="?", default=None,
                        help="Arduino serial port (e.g. /dev/cu.usbserial-11310)")
    parser.add_argument("--device", "-d", default=None,
                        help="Audio device name substring (e.g. 'KRONOS', 'MAONO')")
    parser.add_argument("--list-devices", "-l", action="store_true",
                        help="List audio input devices and exit")
    parser.add_argument("--plates", "-p", default=None,
                        help="Comma-separated plate IDs (default: all)")
    args = parser.parse_args()

    if args.list_devices:
        list_audio_devices()
        sys.exit(0)

    if not args.port:
        print("Usage: python plate_census_audio.py <serial_port> [--device NAME]")
        print("       python plate_census_audio.py --list-devices")
        sys.exit(1)

    run_census(args)


if __name__ == "__main__":
    main()
