#!/usr/bin/env python3
"""Diagnostic v2: Check raw audio levels through plate.

Determines whether ANY signal is getting through the hardware path.
"""
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
DRIVE_AMPLITUDE = 0.8


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


def test_signal(device_idx, sample_rate, freq, amplitude, duration=0.2):
    """Play a single tone and measure response."""
    n_samples = int(sample_rate * duration)
    t = np.arange(n_samples) / sample_rate
    sig = amplitude * np.sin(2 * np.pi * freq * t)
    tx = sig.astype(np.float32).reshape(-1, 1)

    rx = sd.playrec(tx, samplerate=sample_rate,
                    input_mapping=[1], output_mapping=[1],
                    device=device_idx, dtype="float32", blocking=True)
    rx_mono = rx[:, 0].astype(np.float64)
    return rx_mono, tx[:, 0]


def main():
    # Load census
    census = json.load(open(CENSUS_PATH))
    peaks = sorted(census["results"]["5_NE"]["peaks"], key=lambda p: p["freq_hz"])
    mode_freqs = [p["freq_hz"] for p in peaks
                  if not (6500 <= p["freq_hz"] <= 6900)]
    print(f"Plate H: {len(mode_freqs)} modes, range {mode_freqs[0]:.0f}-{mode_freqs[-1]:.0f} Hz")

    device_idx = find_audio_device(DEVICE_HINT)
    sample_rate = detect_sample_rate(device_idx)
    print(f"Kronos: device {device_idx}, sample rate {sample_rate}")
    print(f"Device info: {sd.query_devices(device_idx)['name']}")

    mux = RelayMux(port=PORT)
    mux.open()

    # ── Test 1: Silence (no relay) ──
    print("\n=== Test 1: Silence (record only, no output) ===")
    n = int(sample_rate * 0.2)
    rx = sd.rec(n, samplerate=sample_rate, channels=1,
                device=device_idx, dtype="float32", blocking=True)
    rx_mono = rx[:, 0].astype(np.float64)
    print(f"  RX max={np.max(np.abs(rx_mono)):.8f}  std={np.std(rx_mono):.8f}  mean={np.mean(rx_mono):.8f}")

    # ── Test 2: Play silence through plate (relay 7 = plate 5) ──
    print("\n=== Test 2: Play silence through plate H (relay 7) ===")
    mux.select(7)
    time.sleep(0.2)
    tx_silence = np.zeros((n, 1), dtype=np.float32)
    rx = sd.playrec(tx_silence, samplerate=sample_rate,
                    input_mapping=[1], output_mapping=[1],
                    device=device_idx, dtype="float32", blocking=True)
    rx_mono = rx[:, 0].astype(np.float64)
    print(f"  RX max={np.max(np.abs(rx_mono)):.8f}  std={np.std(rx_mono):.8f}")

    # ── Test 3: Single carrier frequencies through plate ──
    print("\n=== Test 3: Single tones through plate H ===")
    test_freqs = [250, 1000, 3275, 5000, 7500, 11425, 15575, 19100, 23200]
    for freq in test_freqs:
        rx_mono, tx_mono = test_signal(device_idx, sample_rate, freq, DRIVE_AMPLITUDE)
        tx_max = np.max(np.abs(tx_mono))
        rx_max = np.max(np.abs(rx_mono))
        rx_std = np.std(rx_mono)
        # FFT peak
        settle = int(len(rx_mono) * 0.1)
        windowed = rx_mono[settle:] * np.hanning(len(rx_mono[settle:]))
        nfft = len(windowed) * 4
        spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0/sample_rate)
        bin_hz = freq_axis[1]
        target_bin = int(round(freq / bin_hz))
        lo = max(0, target_bin - 5)
        hi = min(len(spectrum)-1, target_bin + 5)
        fft_peak = float(np.max(spectrum[lo:hi+1]))
        fft_peak_freq = float(freq_axis[lo + np.argmax(spectrum[lo:hi+1])])
        print(f"  {freq:>6.0f} Hz: TX_max={tx_max:.4f}  RX_max={rx_max:.8f}  "
              f"RX_std={rx_std:.8f}  FFT_peak={fft_peak:.2f} @ {fft_peak_freq:.1f} Hz")

    # ── Test 4: Same tones with NO relay (loopback) ──
    print("\n=== Test 4: Loopback (relay bypassed - select 0) ===")
    mux.select(0)
    time.sleep(0.2)
    for freq in [1000, 5000, 11425]:
        rx_mono, tx_mono = test_signal(device_idx, sample_rate, freq, DRIVE_AMPLITUDE)
        rx_max = np.max(np.abs(rx_mono))
        settle = int(len(rx_mono) * 0.1)
        windowed = rx_mono[settle:] * np.hanning(len(rx_mono[settle:]))
        nfft = len(windowed) * 4
        spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0/sample_rate)
        bin_hz = freq_axis[1]
        target_bin = int(round(freq / bin_hz))
        lo = max(0, target_bin - 5)
        hi = min(len(spectrum)-1, target_bin + 5)
        fft_peak = float(np.max(spectrum[lo:hi+1]))
        print(f"  {freq:>6.0f} Hz: RX_max={rx_max:.8f}  FFT_peak={fft_peak:.2f}")

    # ── Test 5: Other relays/plates ──
    print("\n=== Test 5: Other plates at 5000 Hz ===")
    for relay, name in [(3, "Plate A(3)"), (4, "Plate B(4)"),
                         (5, "Plate G(5)"), (6, "Plate D(6)"),
                         (7, "Plate H(7)")]:
        mux.select(relay)
        time.sleep(0.2)
        rx_mono, _ = test_signal(device_idx, sample_rate, 5000, DRIVE_AMPLITUDE)
        rx_max = np.max(np.abs(rx_mono))
        rx_std = np.std(rx_mono)
        settle = int(len(rx_mono) * 0.1)
        windowed = rx_mono[settle:] * np.hanning(len(rx_mono[settle:]))
        nfft = len(windowed) * 4
        spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0/sample_rate)
        bin_hz = freq_axis[1]
        target_bin = int(round(5000 / bin_hz))
        lo = max(0, target_bin - 5)
        hi = min(len(spectrum)-1, target_bin + 5)
        fft_peak = float(np.max(spectrum[lo:hi+1]))
        print(f"  {name}: RX_max={rx_max:.8f}  RX_std={rx_std:.8f}  FFT_peak@5kHz={fft_peak:.2f}")

    mux.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
