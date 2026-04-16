#!/usr/bin/env python3
"""
Multitone Experiments: intermodulation, write-read, chirp impulse response.

Uses Kronos for coherent TX+RX via sd.playrec().  No PicoScope.

Experiments:
  intermod  — Drive 2 modes, look for intermodulation products (nonlinearity test)
  writeread — Drive "write" tones, probe "read" tones, check cross-talk
  chirp     — Linear chirp → cross-correlate → impulse response + Q factors

Requires a prior census JSON to know which frequencies are plate eigenmodes.

Hardware setup (same as plate_census_kronos.py):
    Kronos LEFT OUT  → TX PZTs (parallel)
    Relay mux common → Kronos LEFT IN
    Arduino (USB serial) → relay switching

Usage:
    python plate_multitone_kronos.py intermod <serial_port> --device KRONOS \\
        --census <census_json> --plate 5 --modes 0,1

    python plate_multitone_kronos.py writeread <serial_port> --device KRONOS \\
        --census <census_json> --plate 5 --write-modes 0,1,2 --read-modes 3,4,5

    python plate_multitone_kronos.py chirp <serial_port> --device KRONOS \\
        --plate 5 --relay 7 --duration 2.0
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

# ── Plate config ──
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
DRIVE_AMPLITUDE = 0.8
SETTLE_RELAY_S = 0.10


def find_audio_device(name_hint: str) -> int:
    hint_lower = name_hint.lower()
    for i, dev in enumerate(sd.query_devices()):
        if (hint_lower in dev["name"].lower()
                and dev["max_input_channels"] > 0
                and dev["max_output_channels"] > 0):
            return i
    raise RuntimeError(f"No audio device matching '{name_hint}' with I/O.")


def detect_sample_rate(device_idx: int) -> int:
    for rate in PREFERRED_SAMPLE_RATES:
        try:
            sd.check_input_settings(device=device_idx, channels=1,
                                    dtype=AUDIO_DTYPE, samplerate=rate)
            sd.check_output_settings(device=device_idx, channels=1,
                                     dtype=AUDIO_DTYPE, samplerate=rate)
            return rate
        except sd.PortAudioError:
            continue
    dev = sd.query_devices(device_idx)
    return int(dev["default_samplerate"])


def playrec_capture(tx: np.ndarray, sr: int, dev: int) -> np.ndarray:
    rx = sd.playrec(
        tx, samplerate=sr,
        input_mapping=[1], output_mapping=[1],
        device=dev, dtype=AUDIO_DTYPE, blocking=True,
    )
    return rx[:, 0].astype(np.float64)


def load_census_modes(census_path: str, plate_id: str, relay_key: str | None = None):
    """Load mode frequencies from a census JSON file."""
    with open(census_path) as f:
        data = json.load(f)

    results = data.get("results", {})

    # Try direct plate_id key, then plate_id_NE, plate_id_NW
    candidates = [plate_id, f"{plate_id}_NE", f"{plate_id}_NW"]
    if relay_key:
        candidates = [relay_key] + candidates

    for key in candidates:
        if key in results:
            peaks = results[key].get("peaks", [])
            if peaks:
                return sorted(peaks, key=lambda p: p["freq_hz"])

    available = list(results.keys())
    raise RuntimeError(
        f"No modes found for plate {plate_id} in {census_path}. "
        f"Available keys: {available}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# EXPERIMENT 1: INTERMODULATION
# ═══════════════════════════════════════════════════════════════════════════

def run_intermod(args):
    """Drive two modes simultaneously, look for intermodulation products.

    If modes are truly orthogonal (linear system), energy stays at f1 and f2.
    Nonlinear coupling produces energy at: f1±f2, 2f1-f2, 2f2-f1, 2f1, 2f2, etc.
    """
    from relay_mux import RelayMux

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    device_idx = find_audio_device(args.device)
    dev_info = sd.query_devices(device_idx)
    sample_rate = detect_sample_rate(device_idx)

    # Load modes from census
    modes = load_census_modes(args.census, args.plate, args.relay_key)
    mode_indices = [int(x) for x in args.modes.split(",")]
    if len(mode_indices) < 2:
        print("ERROR: need at least 2 modes for intermod test")
        sys.exit(1)

    drive_modes = [modes[i] for i in mode_indices if i < len(modes)]
    drive_freqs = [m["freq_hz"] for m in drive_modes]

    print("\n" + "=" * 70)
    print("  INTERMODULATION TEST")
    print(f"  Device: {dev_info['name']} @ {sample_rate} Hz")
    print(f"  Drive modes: {[f'{f:.0f} Hz' for f in drive_freqs]}")
    print("=" * 70)

    # Compute expected intermod products
    f1, f2 = drive_freqs[0], drive_freqs[1]
    intermod_freqs = {
        "f1": f1,
        "f2": f2,
        "f1+f2": f1 + f2,
        "f2-f1": abs(f2 - f1),
        "2f1-f2": abs(2*f1 - f2),
        "2f2-f1": abs(2*f2 - f1),
        "2f1": 2*f1,
        "2f2": 2*f2,
        "3f1-2f2": abs(3*f1 - 2*f2),
        "3f2-2f1": abs(3*f2 - 2*f1),
    }

    # Filter to within Nyquist
    nyquist = sample_rate / 2
    intermod_freqs = {k: v for k, v in intermod_freqs.items() if 0 < v < nyquist}

    print(f"\n  Expected intermod products:")
    for label, freq in sorted(intermod_freqs.items(), key=lambda x: x[1]):
        tag = " (drive)" if label in ("f1", "f2") else ""
        print(f"    {label:>10}: {freq:8.1f} Hz{tag}")

    # Build TX: sum of two tones
    duration = args.duration
    settle = 0.3  # let plate ring up
    total_dur = settle + duration
    n_total = int(sample_rate * total_dur)
    n_settle = int(sample_rate * settle)
    t = np.arange(n_total) / sample_rate

    tx_sig = np.zeros(n_total, dtype=np.float64)
    for f in drive_freqs:
        tx_sig += np.sin(2 * np.pi * f * t)
    peak = np.max(np.abs(tx_sig))
    if peak > 0:
        tx_sig *= DRIVE_AMPLITUDE / peak
    tx = tx_sig.astype(np.float32).reshape(-1, 1)

    # Setup relay
    relay_ch = int(args.relay) if args.relay else PLATE_RELAYS[args.plate][0][0]
    mux = RelayMux(port=args.port)
    mux.open()
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    print(f"\n  Capturing {args.averages} averages × {duration:.1f}s...")

    # Capture and average FFT magnitudes
    mag_accum = None
    for i in range(args.averages):
        rx = playrec_capture(tx, sample_rate, device_idx)
        rx_capture = rx[n_settle:n_settle + int(sample_rate * duration)]

        windowed = rx_capture * np.hanning(len(rx_capture))
        spectrum = np.fft.rfft(windowed)
        fft_mag = np.abs(spectrum)
        freq_axis = np.fft.rfftfreq(len(rx_capture), d=1.0 / sample_rate)

        if mag_accum is None:
            mag_accum = np.zeros_like(fft_mag)
        mag_accum += fft_mag
        print(f"    [{i+1}/{args.averages}] RMS={np.std(rx_capture):.6f}", flush=True)

    mag_avg = mag_accum / args.averages

    # Extract levels at each intermod frequency
    bin_hz = freq_axis[1]

    # Compute noise floor from bins far from any expected signal.
    # Exclude guard bands of ±50 Hz around every expected intermod product,
    # every drive harmonic up to 5th order, and DC.
    guard_hz = 50.0
    guard_bins = int(guard_hz / bin_hz) + 1
    signal_freqs = list(intermod_freqs.values())
    # Also exclude higher harmonics of the drives
    for n in range(3, 6):
        for fd in drive_freqs:
            hf = n * fd
            if 0 < hf < nyquist:
                signal_freqs.append(hf)

    exclude_mask = np.zeros(len(mag_avg), dtype=bool)
    exclude_mask[:max(1, int(20 / bin_hz))] = True  # exclude DC + sub-20 Hz
    for sf in signal_freqs:
        center = int(round(sf / bin_hz))
        lo = max(0, center - guard_bins)
        hi = min(len(mag_avg) - 1, center + guard_bins)
        exclude_mask[lo:hi+1] = True

    noise_bins = mag_avg[~exclude_mask]
    if len(noise_bins) > 10:
        noise_floor = float(np.median(noise_bins))
    else:
        noise_floor = float(np.median(mag_avg))

    # Also compute noise std for detection threshold
    noise_std = float(np.std(noise_bins)) if len(noise_bins) > 10 else noise_floor
    detect_threshold = noise_floor + 3 * noise_std  # 3-sigma above noise

    n_noise_bins = int(np.sum(~exclude_mask))
    n_excluded = int(np.sum(exclude_mask))
    print(f"\n  Noise floor: {noise_floor:.6f} (median of {n_noise_bins} bins, "
          f"{n_excluded} excluded)")
    print(f"  Noise σ: {noise_std:.6f}, detection threshold (3σ): "
          f"{detect_threshold:.6f}")

    print(f"\n    {'Product':>12}  {'Freq (Hz)':>10}  {'Magnitude':>12}  "
          f"{'dB re noise':>12}  {'σ above':>8}  {'Status'}")
    print(f"    {'─'*12}  {'─'*10}  {'─'*12}  {'─'*12}  {'─'*8}  {'─'*10}")

    results = {}
    for label, freq in sorted(intermod_freqs.items(), key=lambda x: x[1]):
        idx = int(round(freq / bin_hz))
        # Take peak within ±3 bins
        lo = max(0, idx - 3)
        hi = min(len(mag_avg) - 1, idx + 3)
        peak_idx = lo + int(np.argmax(mag_avg[lo:hi+1]))
        mag = float(mag_avg[peak_idx])
        actual_freq = float(freq_axis[peak_idx])

        snr_db = 20 * math.log10(mag / noise_floor) if mag > 0 and noise_floor > 0 else 0
        sigma_above = (mag - noise_floor) / noise_std if noise_std > 0 else 0
        is_drive = label in ("f1", "f2")
        detected = (not is_drive) and (mag > detect_threshold)
        status = "DRIVE" if is_drive else ("DETECTED" if detected else "—")

        print(f"    {label:>12}  {actual_freq:10.1f}  {mag:12.6f}  "
              f"{snr_db:12.1f}  {sigma_above:8.1f}  {status}")

        results[label] = {
            "expected_freq_hz": freq,
            "actual_freq_hz": actual_freq,
            "magnitude": mag,
            "snr_db": round(snr_db, 1),
            "sigma_above_noise": round(sigma_above, 1),
            "is_drive": is_drive,
            "detected": detected,
        }

    # Cleanup
    mux.off()
    mux.close()

    # Verdict
    intermod_detected = [k for k, v in results.items()
                         if v["detected"] and not v["is_drive"]]
    if intermod_detected:
        print(f"\n  ⚠ INTERMOD PRODUCTS DETECTED: {intermod_detected}")
        print(f"    → Nonlinear mode coupling present")
    else:
        print(f"\n  ✓ No intermodulation products above noise floor")
        print(f"    → Modes appear orthogonal (linear) at this drive level")

    # Save
    out_path = RESULTS_DIR / f"intermod_{timestamp}.json"
    save_data = {
        "experiment": "Intermodulation Test",
        "timestamp": timestamp,
        "drive_freqs_hz": drive_freqs,
        "drive_amplitude": DRIVE_AMPLITUDE,
        "duration_s": duration,
        "averages": args.averages,
        "sample_rate": sample_rate,
        "device": dev_info["name"],
        "plate": args.plate,
        "relay": relay_ch,
        "noise_floor": noise_floor,
        "noise_std": noise_std,
        "detect_threshold_3sigma": detect_threshold,
        "noise_bins_used": n_noise_bins,
        "noise_bins_excluded": n_excluded,
        "guard_band_hz": guard_hz,
        "results": results,
        "intermod_detected": intermod_detected,
    }
    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\n  Saved: {out_path}")


# ═══════════════════════════════════════════════════════════════════════════
# EXPERIMENT 2: WRITE-READ CROSS-TALK
# ═══════════════════════════════════════════════════════════════════════════

def run_writeread(args):
    """Drive "write" modes, probe "read" modes, measure cross-contamination.

    Protocol:
      1. Measure "read" mode levels with NO write drive (baseline)
      2. Drive "write" modes AND "read" probe tones simultaneously
      3. Compare read levels — any change = cross-talk between modes
    """
    from relay_mux import RelayMux

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    device_idx = find_audio_device(args.device)
    dev_info = sd.query_devices(device_idx)
    sample_rate = detect_sample_rate(device_idx)

    modes = load_census_modes(args.census, args.plate, args.relay_key)
    write_indices = [int(x) for x in args.write_modes.split(",")]
    read_indices = [int(x) for x in args.read_modes.split(",")]

    write_freqs = [modes[i]["freq_hz"] for i in write_indices if i < len(modes)]
    read_freqs = [modes[i]["freq_hz"] for i in read_indices if i < len(modes)]

    print("\n" + "=" * 70)
    print("  WRITE-READ CROSS-TALK TEST")
    print(f"  Device: {dev_info['name']} @ {sample_rate} Hz")
    print(f"  Write modes: {[f'{f:.0f} Hz' for f in write_freqs]}")
    print(f"  Read  modes: {[f'{f:.0f} Hz' for f in read_freqs]}")
    print("=" * 70)

    duration = args.duration
    settle = 0.3
    total_dur = settle + duration
    n_total = int(sample_rate * total_dur)
    n_settle = int(sample_rate * settle)
    t = np.arange(n_total) / sample_rate

    relay_ch = int(args.relay) if args.relay else PLATE_RELAYS[args.plate][0][0]
    mux = RelayMux(port=args.port)
    mux.open()
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    def measure_at_freqs(tx: np.ndarray, target_freqs: list[float],
                         label: str) -> dict[float, float]:
        """Capture and extract magnitudes at specific frequencies."""
        print(f"\n  Phase: {label} ({args.averages} averages)...")
        mag_accum = {}
        for f in target_freqs:
            mag_accum[f] = 0.0

        for i in range(args.averages):
            rx = playrec_capture(tx, sample_rate, device_idx)
            rx_cap = rx[n_settle:n_settle + int(sample_rate * duration)]
            windowed = rx_cap * np.hanning(len(rx_cap))
            spectrum = np.fft.rfft(windowed)
            fft_mag = np.abs(spectrum)
            freq_axis = np.fft.rfftfreq(len(rx_cap), d=1.0 / sample_rate)
            bin_hz = freq_axis[1]

            for f in target_freqs:
                idx = int(round(f / bin_hz))
                lo = max(0, idx - 3)
                hi = min(len(fft_mag) - 1, idx + 3)
                peak_idx = lo + int(np.argmax(fft_mag[lo:hi+1]))
                mag_accum[f] += float(fft_mag[peak_idx])
            print(f"    [{i+1}/{args.averages}]", flush=True)

        return {f: v / args.averages for f, v in mag_accum.items()}

    # Phase 1: Read-only baseline (drive read tones only, no write tones)
    tx_read_only = np.zeros(n_total, dtype=np.float64)
    probe_amp = DRIVE_AMPLITUDE * 0.1  # probe at -20 dB below full scale
    for f in read_freqs:
        tx_read_only += probe_amp * np.sin(2 * np.pi * f * t)
    peak = np.max(np.abs(tx_read_only))
    if peak > 0:
        tx_read_only *= (probe_amp / peak)
    tx_baseline = tx_read_only.astype(np.float32).reshape(-1, 1)

    baseline_mags = measure_at_freqs(tx_baseline, read_freqs, "BASELINE (read only)")

    # Phase 2: Write + Read (drive write tones at full power + probe read tones)
    tx_combined = np.zeros(n_total, dtype=np.float64)
    for f in write_freqs:
        tx_combined += np.sin(2 * np.pi * f * t)  # full amplitude writes
    for f in read_freqs:
        tx_combined += probe_amp * np.sin(2 * np.pi * f * t)  # low-level probes
    peak = np.max(np.abs(tx_combined))
    if peak > 0:
        tx_combined *= (DRIVE_AMPLITUDE / peak)
    tx_wr = tx_combined.astype(np.float32).reshape(-1, 1)

    writeread_mags = measure_at_freqs(tx_wr, read_freqs, "WRITE+READ")

    # Compare
    print(f"\n  {'─' * 70}")
    print(f"  CROSS-TALK ANALYSIS:")
    print(f"  {'Mode (Hz)':>12}  {'Baseline':>12}  {'With Write':>12}  "
          f"{'Change (dB)':>12}  {'Status'}")
    print(f"  {'─'*12}  {'─'*12}  {'─'*12}  {'─'*12}  {'─'*10}")

    results = {}
    crosstalk_detected = False
    for f in read_freqs:
        b = baseline_mags[f]
        w = writeread_mags[f]
        if b > 0 and w > 0:
            change_db = 20 * math.log10(w / b)
        else:
            change_db = 0.0

        status = "OK" if abs(change_db) < 3.0 else "CROSSTALK"
        if abs(change_db) >= 3.0:
            crosstalk_detected = True

        print(f"  {f:12.1f}  {b:12.6f}  {w:12.6f}  {change_db:+12.1f}  {status}")

        results[str(f)] = {
            "freq_hz": f,
            "baseline_mag": b,
            "writeread_mag": w,
            "change_db": round(change_db, 2),
            "crosstalk": abs(change_db) >= 3.0,
        }

    if crosstalk_detected:
        print(f"\n  ⚠ CROSS-TALK DETECTED — writing to some modes disturbs others")
    else:
        print(f"\n  ✓ No cross-talk > 3 dB — modes appear independent")
        print(f"    → CWM multi-mode storage is viable at this drive level")

    mux.off()
    mux.close()

    # Save
    out_path = RESULTS_DIR / f"writeread_{timestamp}.json"
    save_data = {
        "experiment": "Write-Read Cross-Talk Test",
        "timestamp": timestamp,
        "write_freqs_hz": write_freqs,
        "read_freqs_hz": read_freqs,
        "drive_amplitude": DRIVE_AMPLITUDE,
        "probe_amplitude_relative": 0.1,
        "duration_s": duration,
        "averages": args.averages,
        "sample_rate": sample_rate,
        "device": dev_info["name"],
        "plate": args.plate,
        "relay": relay_ch,
        "results": results,
        "crosstalk_detected": crosstalk_detected,
    }
    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\n  Saved: {out_path}")


# ═══════════════════════════════════════════════════════════════════════════
# EXPERIMENT 3: CHIRP IMPULSE RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

def run_chirp(args):
    """Linear chirp → cross-correlate TX/RX → impulse response.

    Gives mode frequencies AND damping rates (Q factors) in one shot.
    Phase-coherent because TX and RX share the same USB clock.
    """
    from relay_mux import RelayMux

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    device_idx = find_audio_device(args.device)
    dev_info = sd.query_devices(device_idx)
    sample_rate = detect_sample_rate(device_idx)
    nyquist = sample_rate // 2

    f_start = 200.0
    f_stop = min(float(args.f_stop or nyquist - 1000), nyquist - 1000)
    duration = args.duration

    print("\n" + "=" * 70)
    print("  CHIRP IMPULSE RESPONSE")
    print(f"  Device: {dev_info['name']} @ {sample_rate} Hz")
    print(f"  Chirp: {f_start:.0f} → {f_stop:.0f} Hz, {duration:.1f}s")
    print("=" * 70)

    # Build chirp
    settle = 0.1
    total_dur = settle + duration + 0.2  # extra tail for ringing
    n_total = int(sample_rate * total_dur)
    n_settle = int(sample_rate * settle)
    n_chirp = int(sample_rate * duration)

    t_chirp = np.arange(n_chirp) / sample_rate
    phase = 2 * np.pi * (f_start * t_chirp
                          + (f_stop - f_start) * t_chirp**2 / (2 * duration))
    chirp_sig = DRIVE_AMPLITUDE * np.sin(phase)

    # Embed in full-length buffer (silence before chirp, tail after)
    tx_sig = np.zeros(n_total, dtype=np.float64)
    tx_sig[n_settle:n_settle + n_chirp] = chirp_sig
    tx = tx_sig.astype(np.float32).reshape(-1, 1)

    relay_ch = int(args.relay) if args.relay else PLATE_RELAYS[args.plate][0][0]
    mux = RelayMux(port=args.port)
    mux.open()
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    print(f"\n  Capturing {args.averages} chirp responses...")

    # Average the cross-correlation
    xcorr_accum = None
    for i in range(args.averages):
        rx = playrec_capture(tx, sample_rate, device_idx)
        rx_sig = rx.astype(np.float64)

        # Cross-correlate TX and RX in frequency domain
        TX = np.fft.rfft(tx_sig)
        RX = np.fft.rfft(rx_sig, n=len(tx_sig))
        # Transfer function H(f) = RX(f) / TX(f)
        # Impulse response h(t) = ifft(H(f))
        # Use cross-correlation instead for robustness: xcorr = ifft(RX * conj(TX))
        xcorr_spectrum = RX * np.conj(TX)

        if xcorr_accum is None:
            xcorr_accum = np.zeros_like(xcorr_spectrum)
        xcorr_accum += xcorr_spectrum

        rms = float(np.std(rx_sig[n_settle:n_settle + n_chirp]))
        print(f"    [{i+1}/{args.averages}] RMS={rms:.6f}", flush=True)

    xcorr_avg = xcorr_accum / args.averages

    # Transfer function (deconvolution with regularization)
    TX = np.fft.rfft(tx_sig)
    tx_power = np.abs(TX)**2
    reg = np.max(tx_power) * 1e-6  # Wiener regularization
    H = xcorr_avg / (tx_power + reg)

    freq_axis = np.fft.rfftfreq(len(tx_sig), d=1.0 / sample_rate)
    H_mag = np.abs(H)
    H_phase = np.angle(H)

    # Impulse response
    h = np.fft.irfft(H)

    # Find peaks in transfer function magnitude
    from plate_census_kronos import detect_modes as _detect

    sweep_data = []
    bin_hz = freq_axis[1]
    for idx in range(len(freq_axis)):
        if freq_axis[idx] < f_start or freq_axis[idx] > f_stop:
            continue
        sweep_data.append({
            "freq_hz": float(freq_axis[idx]),
            "magnitude": float(H_mag[idx]),
            "phase_rad": float(H_phase[idx]),
            "phase_std": 0.0,
        })

    peaks = _detect(sweep_data)

    print(f"\n  Detected {len(peaks)} modes from chirp transfer function")
    print(f"\n  Top 20 modes:")
    print(f"    {'#':>3}  {'Freq (Hz)':>10}  {'|H(f)|':>12}  {'SNR (dB)':>8}")
    for i, p in enumerate(peaks[:20]):
        print(f"    {i+1:3d}  {p['freq_hz']:10.1f}  {p['magnitude']:12.6f}  "
              f"{p['snr_db']:8.1f}")

    mux.off()
    mux.close()

    # Save
    out_path = RESULTS_DIR / f"chirp_ir_{timestamp}.json"
    # Don't save gigantic arrays — just peaks and metadata
    save_data = {
        "experiment": "Chirp Impulse Response",
        "timestamp": timestamp,
        "chirp_f_start": f_start,
        "chirp_f_stop": f_stop,
        "duration_s": duration,
        "averages": args.averages,
        "sample_rate": sample_rate,
        "device": dev_info["name"],
        "plate": args.plate,
        "relay": relay_ch,
        "n_modes_detected": len(peaks),
        "peaks": peaks[:50],  # top 50
        "transfer_function_bins": len(freq_axis),
    }
    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\n  Saved: {out_path}")

    # Also save full transfer function as numpy
    tf_path = RESULTS_DIR / f"chirp_ir_tf_{timestamp}.npz"
    np.savez_compressed(
        tf_path,
        freq_axis=freq_axis,
        H_mag=H_mag,
        H_phase=H_phase,
        impulse_response=h[:sample_rate],  # first 1 second of IR
    )
    print(f"  Transfer function: {tf_path}")


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Multitone experiments: intermod, write-read, chirp"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Common args helper
    def add_common(p):
        p.add_argument("port", help="Arduino serial port")
        p.add_argument("--device", "-d", required=True, help="Audio device name")
        p.add_argument("--plate", "-p", required=True, help="Plate ID (1-5)")
        p.add_argument("--relay", "-r", default=None, help="Relay channel override")
        p.add_argument("--duration", type=float, default=2.0, help="Capture duration (s)")
        p.add_argument("--averages", type=int, default=8, help="Number of averages")

    # intermod
    p_im = sub.add_parser("intermod", help="Intermodulation test")
    add_common(p_im)
    p_im.add_argument("--census", required=True, help="Path to census JSON")
    p_im.add_argument("--modes", required=True,
                       help="Mode indices to drive (e.g. '0,1' for top two)")
    p_im.add_argument("--relay-key", default=None, help="Census result key override")

    # writeread
    p_wr = sub.add_parser("writeread", help="Write-read cross-talk test")
    add_common(p_wr)
    p_wr.add_argument("--census", required=True, help="Path to census JSON")
    p_wr.add_argument("--write-modes", required=True,
                       help="Mode indices to write (e.g. '0,1,2')")
    p_wr.add_argument("--read-modes", required=True,
                       help="Mode indices to read/probe (e.g. '3,4,5')")
    p_wr.add_argument("--relay-key", default=None, help="Census result key override")

    # chirp
    p_ch = sub.add_parser("chirp", help="Chirp impulse response")
    add_common(p_ch)
    p_ch.add_argument("--f-stop", type=float, default=None,
                       help="Chirp stop frequency (default: Nyquist - 1 kHz)")

    args = parser.parse_args()

    if args.command == "intermod":
        run_intermod(args)
    elif args.command == "writeread":
        run_writeread(args)
    elif args.command == "chirp":
        run_chirp(args)


if __name__ == "__main__":
    main()
