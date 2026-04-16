#!/usr/bin/env python3
"""
Kronos-Only Mode Census: USB audio interface for BOTH TX drive AND RX capture.

No PicoScope required.  Uses sd.playrec() for phase-coherent simultaneous
play + record through the same USB device (same crystal clock).

Supports two modes:
  - step:  CW sweep (one tone at a time), like plate_census_audio.py
  - flash: Multitone — drive ALL frequencies at once, single FFT.
           Entire transfer function in seconds instead of minutes.

Hardware setup:
    Kronos LEFT OUT  → TX PZTs (parallel, via 1/4" TRS cable + alligator clips)
    Relay mux common → Kronos LEFT IN  (existing cable)
    Arduino (USB serial) → relay switching (unchanged)

Usage:
    python plate_census_kronos.py <serial_port> --device KRONOS --plates 5
    python plate_census_kronos.py <serial_port> --device KRONOS --plates 5 --mode flash
    python plate_census_kronos.py <serial_port> --device KRONOS --mode flash --duration 2.0
    python plate_census_kronos.py --list-devices
"""
from __future__ import annotations

import argparse
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

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab"
RESULTS_DIR = LAB_DIR / "plate_exps"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Plate config (same as other census scripts) ──
PLATE_NAMES = {"1": "A", "2": "B", "3": "G", "4": "D", "5": "H"}

PLATE_RELAYS = {
    "1": [(1, "NE")],
    "2": [(2, "NE")],
    "3": [(3, "NE"), (4, "NW")],
    "4": [(5, "NE"), (6, "NW")],
    "5": [(7, "NE"), (8, "NW")],
}

# ── Audio config ──
PREFERRED_SAMPLE_RATES = [192000, 96000, 48000, 44100]
AUDIO_DTYPE = "float32"

# ── Step-sweep config ──
F_START = 200             # Hz
F_STEP = 25               # Hz
N_AVG = 4                 # averages per frequency point
SETTLE_S = 0.05           # settle time after freq change
SETTLE_RELAY_S = 0.10     # settle time after relay switch
CAPTURE_S = 0.04          # recording duration per point (40 ms)
DRIVE_AMPLITUDE = 0.8     # peak amplitude of TX signal (0–1.0, leave headroom)

# ── Flash census config ──
FLASH_DURATION_S = 1.0    # default recording length for flash mode
FLASH_AVERAGES = 8        # number of flash captures to average
FLASH_SETTLE_S = 0.2      # let plate reach steady state before recording

# ── Peak detection ──
MIN_SNR_DB = 6.0
MIN_PROMINENCE_DB = 3.0


# ── Audio device helpers (shared with plate_census_audio.py) ──

def list_audio_devices():
    """Print all available audio devices with I/O capability."""
    print("\nAvailable audio devices:")
    print(f"  {'#':>3}  {'Name':<50}  {'In':>3}  {'Out':>3}  {'Rate':>8}")
    print(f"  {'─'*3}  {'─'*50}  {'─'*3}  {'─'*3}  {'─'*8}")
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 or dev["max_output_channels"] > 0:
            print(f"  {i:3d}  {dev['name']:<50}  "
                  f"{dev['max_input_channels']:>3}  "
                  f"{dev['max_output_channels']:>3}  "
                  f"{dev['default_samplerate']:>8.0f}")
    print()


def find_audio_device(name_hint: str | None = None) -> int:
    """Find an audio device with BOTH input and output channels."""
    if name_hint:
        hint_lower = name_hint.lower()
        for i, dev in enumerate(sd.query_devices()):
            if (hint_lower in dev["name"].lower()
                    and dev["max_input_channels"] > 0
                    and dev["max_output_channels"] > 0):
                return i
        # Fallback: check if there's even one matching with just input
        for i, dev in enumerate(sd.query_devices()):
            if hint_lower in dev["name"].lower() and dev["max_input_channels"] > 0:
                raise RuntimeError(
                    f"Device '{dev['name']}' has inputs but NO outputs. "
                    f"Cannot use for TX+RX. Check --list-devices."
                )
        raise RuntimeError(
            f"No audio device matching '{name_hint}' with I/O. "
            f"Run with --list-devices to see available devices."
        )
    raise RuntimeError("--device is required for Kronos-only mode.")


def detect_sample_rate(device_idx: int) -> int:
    """Find the highest sample rate supported for both I/O."""
    dev = sd.query_devices(device_idx)
    for rate in PREFERRED_SAMPLE_RATES:
        try:
            sd.check_input_settings(
                device=device_idx, channels=1,
                dtype=AUDIO_DTYPE, samplerate=rate,
            )
            sd.check_output_settings(
                device=device_idx, channels=1,
                dtype=AUDIO_DTYPE, samplerate=rate,
            )
            return rate
        except sd.PortAudioError:
            continue
    return int(dev["default_samplerate"])


# ── Signal generation helpers ──

def make_tone(freq_hz: float, duration_s: float, sample_rate: int,
              amplitude: float = DRIVE_AMPLITUDE) -> np.ndarray:
    """Generate a single CW tone as float32 column vector."""
    t = np.arange(int(sample_rate * duration_s)) / sample_rate
    sig = (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)
    return sig.reshape(-1, 1)


def make_multitone(freqs_hz: np.ndarray, duration_s: float, sample_rate: int,
                   amplitude: float = DRIVE_AMPLITUDE) -> np.ndarray:
    """Generate a sum-of-sinusoids signal (multitone / comb).

    Each tone gets equal amplitude.  The total is normalized so the
    peak doesn't clip (stays within ±amplitude).
    """
    n_samples = int(sample_rate * duration_s)
    t = np.arange(n_samples) / sample_rate
    sig = np.zeros(n_samples, dtype=np.float64)

    for f in freqs_hz:
        # Random phase per tone to reduce crest factor
        phi = np.random.uniform(0, 2 * np.pi)
        sig += np.sin(2 * np.pi * f * t + phi)

    # Normalize so peak = amplitude (leave headroom)
    peak = np.max(np.abs(sig))
    if peak > 0:
        sig = sig * (amplitude / peak)

    return sig.astype(np.float32).reshape(-1, 1)


def make_chirp(f_start: float, f_stop: float, duration_s: float,
               sample_rate: int, amplitude: float = DRIVE_AMPLITUDE) -> np.ndarray:
    """Generate a linear chirp (swept sine)."""
    n_samples = int(sample_rate * duration_s)
    t = np.arange(n_samples) / sample_rate
    # Instantaneous frequency: f_start + (f_stop - f_start) * t / T
    phase = 2 * np.pi * (f_start * t + (f_stop - f_start) * t**2 / (2 * duration_s))
    sig = (amplitude * np.sin(phase)).astype(np.float32)
    return sig.reshape(-1, 1)


# ── Capture helpers ──

def playrec_capture(tx_signal: np.ndarray, sample_rate: int,
                    device_idx: int) -> np.ndarray:
    """Simultaneous play + record.  Returns mono RX signal (float64)."""
    rx = sd.playrec(
        tx_signal,
        samplerate=sample_rate,
        input_mapping=[1],     # record from input channel 1
        output_mapping=[1],    # play to output channel 1
        device=device_idx,
        dtype=AUDIO_DTYPE,
        blocking=True,
    )
    return rx[:, 0].astype(np.float64)


# ── Step-sweep census (CW tone per frequency) ──

def step_sweep(mux, plate_id: str, relay_ch: int, rx_label: str,
               sample_rate: int, device_idx: int, f_stop: int) -> list[dict]:
    """CW sweep: one tone at a time, record response, extract magnitude+phase."""
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    freqs = np.arange(F_START, f_stop + F_STEP, F_STEP)
    name = PLATE_NAMES[plate_id]
    n_pts = len(freqs)
    print(f"\n  Plate {name} (relay {relay_ch}, RX-{rx_label}): "
          f"step sweep {F_START}–{f_stop} Hz, {F_STEP} Hz steps ({n_pts} pts)")

    # Pre-generate a silence buffer for settling
    settle_samples = int(sample_rate * SETTLE_S)

    sweep_data = []
    t0 = time.time()

    for i, freq in enumerate(freqs):
        # Generate tone: settle + capture duration
        total_dur = SETTLE_S + CAPTURE_S
        tx = make_tone(float(freq), total_dur, sample_rate)

        mags = []
        phases = []
        for _ in range(N_AVG):
            rx = playrec_capture(tx, sample_rate, device_idx)

            # Discard the settle period, analyze only the capture window
            rx_capture = rx[settle_samples:]

            # Window + FFT
            windowed = rx_capture * np.hanning(len(rx_capture))
            nfft = len(rx_capture) * 4  # 4× zero-pad
            spectrum = np.fft.rfft(windowed, n=nfft)
            fft_mag = np.abs(spectrum)
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)

            # Find bin closest to drive frequency
            bin_hz = freq_axis[1]
            target_bin = int(round(freq / bin_hz))
            lo = max(0, target_bin - 3)
            hi = min(len(fft_mag) - 1, target_bin + 3)
            peak_bin = lo + int(np.argmax(fft_mag[lo:hi + 1]))

            mags.append(float(fft_mag[peak_bin]))
            phases.append(float(np.angle(spectrum[peak_bin])))

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


# ── Flash census (multitone — all frequencies at once) ──

def flash_census(mux, plate_id: str, relay_ch: int, rx_label: str,
                 sample_rate: int, device_idx: int, f_stop: int,
                 duration_s: float = FLASH_DURATION_S,
                 n_averages: int = FLASH_AVERAGES) -> list[dict]:
    """Drive all frequencies simultaneously, get full transfer function in one shot."""
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    name = PLATE_NAMES[plate_id]
    freqs = np.arange(F_START, f_stop + F_STEP, F_STEP, dtype=np.float64)
    n_tones = len(freqs)

    # Frequency resolution of our FFT
    fft_res = 1.0 / duration_s
    print(f"\n  Plate {name} (relay {relay_ch}, RX-{rx_label}): "
          f"FLASH — {n_tones} tones, {duration_s:.1f}s capture, "
          f"{fft_res:.1f} Hz resolution")

    # Snap frequencies to FFT bin centers so each tone lands exactly on a bin
    freqs_snapped = np.round(freqs / fft_res) * fft_res
    # Remove any duplicates from snapping
    freqs_snapped = np.unique(freqs_snapped)
    freqs_snapped = freqs_snapped[freqs_snapped >= F_START]
    n_tones = len(freqs_snapped)

    # Total TX duration = settle + capture
    total_dur = FLASH_SETTLE_S + duration_s

    # We need the same random phases for all averages to get coherent averaging
    rng = np.random.default_rng(42)
    tx_phases = rng.uniform(0, 2 * np.pi, size=n_tones)

    # Build TX signal
    n_total = int(sample_rate * total_dur)
    n_settle = int(sample_rate * FLASH_SETTLE_S)
    t = np.arange(n_total) / sample_rate
    tx_sig = np.zeros(n_total, dtype=np.float64)
    for j, f in enumerate(freqs_snapped):
        tx_sig += np.sin(2 * np.pi * f * t + tx_phases[j])

    # Normalize
    peak = np.max(np.abs(tx_sig))
    if peak > 0:
        tx_sig = tx_sig * (DRIVE_AMPLITUDE / peak)
    tx = tx_sig.astype(np.float32).reshape(-1, 1)

    # Capture and average
    print(f"    Averaging {n_averages} captures...", flush=True)
    mag_accum = None
    phase_accum_sin = None
    phase_accum_cos = None

    for avg_i in range(n_averages):
        rx = playrec_capture(tx, sample_rate, device_idx)

        # Discard settle period
        rx_capture = rx[n_settle:n_settle + int(sample_rate * duration_s)]

        # Window + FFT (no zero-pad needed — we snapped freqs to bin centers)
        windowed = rx_capture * np.hanning(len(rx_capture))
        spectrum = np.fft.rfft(windowed)
        fft_mag = np.abs(spectrum)
        fft_phase = np.angle(spectrum)
        freq_axis = np.fft.rfftfreq(len(rx_capture), d=1.0 / sample_rate)

        if mag_accum is None:
            mag_accum = np.zeros_like(fft_mag)
            phase_accum_sin = np.zeros_like(fft_mag)
            phase_accum_cos = np.zeros_like(fft_mag)

        mag_accum += fft_mag
        phase_accum_sin += np.sin(fft_phase)
        phase_accum_cos += np.cos(fft_phase)

        print(f"      [{avg_i+1}/{n_averages}] RMS={np.std(rx_capture):.6f}", flush=True)

    mag_avg = mag_accum / n_averages
    phase_avg = np.arctan2(phase_accum_sin, phase_accum_cos)

    # Extract magnitude at each drive frequency
    bin_hz = freq_axis[1] if len(freq_axis) > 1 else 1.0
    sweep_data = []
    for f in freqs_snapped:
        idx = int(round(f / bin_hz))
        if 0 <= idx < len(mag_avg):
            sweep_data.append({
                "freq_hz": round(float(f), 1),
                "magnitude": round(float(mag_avg[idx]), 6),
                "phase_rad": round(float(phase_avg[idx]), 4),
                "phase_std": 0.0,  # not computed for flash mode
            })

    print(f"    Flash census complete: {len(sweep_data)} frequency bins extracted")

    # Quick stats
    all_mags = np.array([s["magnitude"] for s in sweep_data])
    peak_idx = np.argmax(all_mags)
    peak_f = sweep_data[peak_idx]["freq_hz"]
    peak_m = sweep_data[peak_idx]["magnitude"]
    median_m = float(np.median(all_mags))
    print(f"    Peak: {peak_f:.0f} Hz (mag={peak_m:.6f}), "
          f"median={median_m:.6f}, "
          f"peak/median={peak_m/median_m:.1f}×" if median_m > 0 else "")

    return sweep_data


# ── Peak detection (same algorithm as plate_census_audio.py) ──

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


# ── Main census runner ──

def run_census(args):
    from relay_mux import RelayMux

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    device_idx = find_audio_device(args.device)
    dev_info = sd.query_devices(device_idx)
    sample_rate = detect_sample_rate(device_idx)
    f_stop = int(sample_rate / 2) - 1000  # stay 1 kHz below Nyquist

    mode_label = args.mode.upper()
    print("\n" + "=" * 70)
    print(f"  KRONOS-ONLY MODE CENSUS ({mode_label})")
    print(f"  Device: {dev_info['name']}")
    print(f"  Sample rate: {sample_rate} Hz → Nyquist: {sample_rate // 2} Hz")
    print(f"  Sweep range: {F_START} – {f_stop} Hz, {F_STEP} Hz steps")
    print(f"  TX+RX via same USB device (phase-coherent)")
    print("=" * 70)

    plate_ids = args.plates.split(",") if args.plates else list(PLATE_RELAYS.keys())
    for pid in plate_ids:
        if pid not in PLATE_RELAYS:
            print(f"ERROR: unknown plate ID '{pid}'. "
                  f"Valid: {list(PLATE_RELAYS.keys())}")
            sys.exit(1)

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

            if args.mode == "flash":
                sweep_data = flash_census(
                    mux, pid, relay_ch, rx_label,
                    sample_rate, device_idx, f_stop,
                    duration_s=args.duration,
                    n_averages=args.averages,
                )
            else:  # step
                sweep_data = step_sweep(
                    mux, pid, relay_ch, rx_label,
                    sample_rate, device_idx, f_stop,
                )

            peaks = detect_modes(sweep_data)
            stats = analyze_mode_spacing(peaks)

            print(f"  Detected {len(peaks)} modes (SNR > {MIN_SNR_DB} dB, "
                  f"prominence > {MIN_PROMINENCE_DB} dB)")
            if stats.get("modes_per_khz"):
                print(f"  Mode density: {stats['modes_per_khz']:.1f} modes/kHz "
                      f"({stats['freq_min_hz']:.0f}–{stats['freq_max_hz']:.0f} Hz)")

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
    mux.close()

    elapsed = time.time() - t_start

    # Summary
    result_keys = sorted(all_results.keys())
    print(f"\n{'=' * 70}")
    print(f"  KRONOS CENSUS SUMMARY ({mode_label}) — "
          f"{elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"  Device: {dev_info['name']} @ {sample_rate} Hz, 24-bit")
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

    # Save
    out_path = RESULTS_DIR / f"plate_census_kronos_{args.mode}_{timestamp}.json"
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
        "experiment": f"Kronos-Only Mode Census ({mode_label})",
        "timestamp": timestamp,
        "elapsed_s": round(elapsed, 1),
        "config": {
            "mode": args.mode,
            "f_start": F_START,
            "f_stop": f_stop,
            "f_step": F_STEP,
            "n_avg": N_AVG if args.mode == "step" else args.averages,
            "capture_s": CAPTURE_S if args.mode == "step" else args.duration,
            "min_snr_db": MIN_SNR_DB,
            "min_prominence_db": MIN_PROMINENCE_DB,
            "drive_amplitude": DRIVE_AMPLITUDE,
            "audio_device": dev_info["name"],
            "audio_sample_rate": sample_rate,
            "audio_bit_depth": 24,
        },
        "results": summary_results,
    }
    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Summary saved: {out_path}")

    # Full sweep data
    sweep_path = RESULTS_DIR / f"plate_census_kronos_{args.mode}_sweeps_{timestamp}.json"
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
        description="Kronos-Only Mode Census: USB audio TX+RX (no PicoScope)"
    )
    parser.add_argument("port", nargs="?", default=None,
                        help="Arduino serial port (e.g. /dev/cu.usbserial-11310)")
    parser.add_argument("--device", "-d", default=None,
                        help="Audio device name substring (e.g. 'KRONOS')")
    parser.add_argument("--list-devices", "-l", action="store_true",
                        help="List audio devices and exit")
    parser.add_argument("--plates", "-p", default=None,
                        help="Comma-separated plate IDs (default: all)")
    parser.add_argument("--mode", "-m", choices=["step", "flash"],
                        default="flash",
                        help="Census mode: step (CW sweep) or flash (multitone)")
    parser.add_argument("--duration", type=float, default=FLASH_DURATION_S,
                        help=f"Flash capture duration in seconds (default: {FLASH_DURATION_S})")
    parser.add_argument("--averages", type=int, default=FLASH_AVERAGES,
                        help=f"Flash averages (default: {FLASH_AVERAGES})")
    args = parser.parse_args()

    if args.list_devices:
        list_audio_devices()
        sys.exit(0)

    if not args.port:
        print("Usage: python plate_census_kronos.py <serial_port> --device KRONOS")
        print("       python plate_census_kronos.py --list-devices")
        sys.exit(1)

    run_census(args)


if __name__ == "__main__":
    main()
