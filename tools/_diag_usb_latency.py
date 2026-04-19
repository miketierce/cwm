#!/usr/bin/env python3
"""Probe the exact USB round-trip latency by playing a long tone
and finding where energy first appears in the RX buffer."""
import json
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relay_mux import RelayMux

PORT = "/dev/cu.usbserial-11310"
DEVICE_HINT = "KRONOS"
CENSUS_PATH = "data/results/lab/plate_exps/plate_census_kronos_flash_20260415_211405.json"


def find_audio_device(name_hint):
    hint_lower = name_hint.lower()
    for i, dev in enumerate(sd.query_devices()):
        if (hint_lower in dev["name"].lower()
                and dev["max_input_channels"] > 0
                and dev["max_output_channels"] > 0):
            return i
    raise RuntimeError(f"No audio device matching '{name_hint}'")


def detect_sample_rate(device_idx):
    for rate in [192000, 96000, 48000, 44100]:
        try:
            sd.check_input_settings(device=device_idx, channels=1,
                                    dtype="float32", samplerate=rate)
            sd.check_output_settings(device=device_idx, channels=1,
                                     dtype="float32", samplerate=rate)
            return rate
        except Exception:
            continue
    return int(sd.query_devices(device_idx)["default_samplerate"])


def main():
    device_idx = find_audio_device(DEVICE_HINT)
    sample_rate = detect_sample_rate(device_idx)
    dev_info = sd.query_devices(device_idx)
    print(f"Device: {dev_info['name']}")
    print(f"Sample rate: {sample_rate}")
    print(f"Input latency (low/high): "
          f"{dev_info['default_low_input_latency']:.4f} / "
          f"{dev_info['default_high_input_latency']:.4f} s")
    print(f"Output latency (low/high): "
          f"{dev_info['default_low_output_latency']:.4f} / "
          f"{dev_info['default_high_output_latency']:.4f} s")

    # Select plate H via relay
    mux = RelayMux(port=PORT)
    mux.open()
    mux.select(7)
    time.sleep(0.3)

    # Play a 3-second 5000 Hz tone
    freq = 5000.0
    duration = 3.0
    print(f"\nPlaying {freq:.0f} Hz tone for {duration:.1f}s through plate H...")

    n_samples = int(sample_rate * duration)
    t = np.arange(n_samples) / sample_rate
    sig = 0.8 * np.sin(2 * np.pi * freq * t)
    tx = sig.astype(np.float32).reshape(-1, 1)

    rx = sd.playrec(tx, samplerate=sample_rate,
                    input_mapping=[1], output_mapping=[1],
                    device=device_idx, dtype="float32", blocking=True)
    rx_mono = rx[:, 0].astype(np.float64)

    # Analyze RX in 10ms chunks to find where energy appears
    chunk_ms = 10
    chunk_samples = int(sample_rate * chunk_ms / 1000)
    n_chunks = len(rx_mono) // chunk_samples

    print(f"\nRX energy in {chunk_ms}ms chunks (first 100 chunks = first {100*chunk_ms}ms):")
    print(f"  {'Chunk':>6} {'Time_ms':>10} {'RMS':>12} {'Peak':>12} {'dB_re_max':>12}")

    rms_vals = []
    for i in range(min(n_chunks, 300)):
        chunk = rx_mono[i*chunk_samples:(i+1)*chunk_samples]
        rms = np.sqrt(np.mean(chunk**2))
        peak = np.max(np.abs(chunk))
        rms_vals.append(rms)

    max_rms = max(rms_vals) if max(rms_vals) > 0 else 1e-10

    first_signal_chunk = None
    for i, rms in enumerate(rms_vals):
        time_ms = i * chunk_ms
        peak = np.max(np.abs(rx_mono[i*chunk_samples:(i+1)*chunk_samples]))
        db = 20 * np.log10(rms / max_rms + 1e-30)
        marker = ""
        if first_signal_chunk is None and rms > max_rms * 0.01:
            first_signal_chunk = i
            marker = " <-- SIGNAL STARTS"
        # Show first 50, then only significant ones, then around signal onset
        if i < 50 or abs(db) < 30 or (first_signal_chunk and abs(i - first_signal_chunk) < 10):
            print(f"  {i:>6} {time_ms:>10.0f} {rms:>12.8f} {peak:>12.8f} {db:>12.1f}{marker}")

    if first_signal_chunk is not None:
        latency_ms = first_signal_chunk * chunk_ms
        print(f"\n>>> USB round-trip latency ≈ {latency_ms} ms "
              f"(signal first appears at chunk {first_signal_chunk})")
    else:
        print(f"\n>>> NO SIGNAL DETECTED in {len(rms_vals)*chunk_ms}ms of recording!")
        print("  Possible issues: relay disconnected, audio routing broken, "
              "or plate not coupled")

    # Also try without relay (just Kronos self-noise)
    print(f"\n--- Control: record-only (no output) for 0.5s ---")
    rx2 = sd.rec(int(sample_rate * 0.5), samplerate=sample_rate,
                 channels=1, device=device_idx, dtype="float32", blocking=True)
    rx2_mono = rx2[:, 0].astype(np.float64)
    print(f"  RX max={np.max(np.abs(rx2_mono)):.8f}  "
          f"RMS={np.sqrt(np.mean(rx2_mono**2)):.8f}")

    # FFT of the full 3s response (skipping first 1s)
    if first_signal_chunk is not None:
        skip = first_signal_chunk * chunk_samples + int(sample_rate * 0.1)
        rx_steady = rx_mono[skip:]
        if len(rx_steady) > sample_rate:
            rx_steady = rx_steady[:int(sample_rate)]  # 1s window
        windowed = rx_steady * np.hanning(len(rx_steady))
        spectrum = np.abs(np.fft.rfft(windowed))
        freq_axis = np.fft.rfftfreq(len(rx_steady), d=1.0/sample_rate)
        # Find peak
        peak_idx = np.argmax(spectrum)
        print(f"\n--- FFT of steady-state response ---")
        print(f"  Peak at {freq_axis[peak_idx]:.1f} Hz, "
              f"magnitude={spectrum[peak_idx]:.2f}")
        # Show magnitudes around drive freq
        bin_hz = freq_axis[1]
        target_bin = int(round(freq / bin_hz))
        lo = max(0, target_bin - 10)
        hi = min(len(spectrum)-1, target_bin + 10)
        print(f"  Around {freq:.0f} Hz:")
        for b in range(lo, hi+1):
            marker = " <--" if b == target_bin else ""
            print(f"    {freq_axis[b]:>10.1f} Hz: {spectrum[b]:>10.2f}{marker}")

    mux.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
