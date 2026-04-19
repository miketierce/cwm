#!/usr/bin/env python3
"""Diagnostic: capture a few patterns and dump carrier-bin magnitudes.

Shows the ON/OFF contrast at carrier frequencies to understand
why polynomial features fail on hardware.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relay_mux import RelayMux

# Config
PORT = "/dev/cu.usbserial-11310"
DEVICE_HINT = "KRONOS"
CENSUS_PATH = "data/results/lab/plate_exps/plate_census_kronos_flash_20260415_211405.json"
PLATE_ID = "5"
N_AVG = 4
DRIVE_AMPLITUDE = 0.8
FIXTURE_FREQ_HZ = 6700.0
FIXTURE_GUARD_HZ = 200.0
USB_LATENCY_S = 0.25


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
    # Load census
    census = json.load(open(CENSUS_PATH))
    results = census["results"]["5_NE"]
    peaks = sorted(results["peaks"], key=lambda p: p["freq_hz"])
    lo = FIXTURE_FREQ_HZ - FIXTURE_GUARD_HZ
    hi = FIXTURE_FREQ_HZ + FIXTURE_GUARD_HZ
    mode_freqs = [p["freq_hz"] for p in peaks if not (lo <= p["freq_hz"] <= hi)]
    n_modes = len(mode_freqs)
    print(f"Modes: {n_modes}")

    # Carrier indices (7, evenly spaced)
    n_bits = 3  # just test 3-bit for speed
    carrier_indices = np.linspace(0, n_modes - 1, 7, dtype=int).tolist()
    ci = carrier_indices[:n_bits]
    print(f"Carrier indices: {ci}")
    print(f"Carrier freqs: {[mode_freqs[i] for i in ci]}")

    # Setup hardware
    device_idx = find_audio_device(DEVICE_HINT)
    sample_rate = detect_sample_rate(device_idx)
    print(f"Sample rate: {sample_rate}")

    mux = RelayMux(port=PORT)
    mux.open()
    mux.select(7)  # plate 5 relay
    time.sleep(0.1)

    # Test patterns for 3-bit
    patterns = np.array([[i >> b & 1 for b in range(n_bits)] for i in range(8)])
    labels = np.sum(patterns, axis=1) % 2

    rng = np.random.default_rng(42)

    print(f"\n{'Pattern':>10} {'Parity':>7} ", end="")
    for i in range(n_bits):
        print(f"  {'carrier'+str(i):>10}", end="")
    print(f"  {'all_modes_mean':>14}")
    print("-" * 80)

    all_carrier_mags = []
    for pat in patterns:
        total_dur = USB_LATENCY_S + 0.2
        n_samples = int(sample_rate * total_dur)
        t = np.arange(n_samples) / sample_rate
        sig = np.zeros(n_samples, dtype=np.float64)

        rng2 = np.random.default_rng(42)
        for b in range(n_bits):
            freq = mode_freqs[ci[b]]
            if pat[b] > 0:
                phi = rng2.uniform(0, 2 * np.pi)
                sig += np.sin(2 * np.pi * freq * t + phi)
            else:
                rng2.uniform(0, 2 * np.pi)

        peak = np.max(np.abs(sig))
        if peak > 0:
            sig *= DRIVE_AMPLITUDE / peak

        tx = sig.astype(np.float32).reshape(-1, 1)

        sum_mags = np.zeros(n_modes)
        for _ in range(N_AVG):
            rx = sd.playrec(tx, samplerate=sample_rate,
                            input_mapping=[1], output_mapping=[1],
                            device=device_idx, dtype="float32", blocking=True)
            rx_mono = rx[:, 0].astype(np.float64)
            settle = int(sample_rate * USB_LATENCY_S)
            rx_capture = rx_mono[settle:]
            windowed = rx_capture * np.hanning(len(rx_capture))
            nfft = len(rx_capture) * 4
            spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
            bin_hz = freq_axis[1]

            mags = np.zeros(n_modes)
            for j, f in enumerate(mode_freqs):
                tb = int(round(f / bin_hz))
                lob = max(0, tb - 3)
                hib = min(len(spectrum) - 1, tb + 3)
                mags[j] = float(np.max(spectrum[lob:hib + 1]))
            sum_mags += mags

        avg_mags = sum_mags / N_AVG
        carrier_mags = avg_mags[ci]
        all_carrier_mags.append(carrier_mags)

        pat_str = "".join(str(int(b)) for b in pat)
        parity = int(np.sum(pat) % 2)
        print(f"  {pat_str:>10} {parity:>7} ", end="")
        for m in carrier_mags:
            print(f"  {m:>10.2f}", end="")
        print(f"  {np.mean(avg_mags):>14.2f}")

    # Analyze ON/OFF contrast
    all_cm = np.array(all_carrier_mags)
    print(f"\n=== ON/OFF Contrast Analysis ===")
    for b in range(n_bits):
        on_vals = all_cm[patterns[:, b] == 1, b]
        off_vals = all_cm[patterns[:, b] == 0, b]
        on_mean = np.mean(on_vals)
        off_mean = np.mean(off_vals)
        ratio = on_mean / (off_mean + 1e-10)
        print(f"  Carrier {b} ({mode_freqs[ci[b]]:.0f} Hz): "
              f"ON={on_mean:.2f}, OFF={off_mean:.2f}, ratio={ratio:.1f}x")

    # Now check: after log1p + z-score, what do products look like?
    print(f"\n=== After log1p + z-score ===")
    X_log = np.log1p(all_cm)
    mu = X_log.mean(axis=0)
    sigma = X_log.std(axis=0) + 1e-8
    X_std = (X_log - mu) / sigma
    print("Normalized carrier magnitudes per pattern:")
    for i, pat in enumerate(patterns):
        pat_str = "".join(str(int(b)) for b in pat)
        vals = " ".join(f"{v:+6.2f}" for v in X_std[i])
        print(f"  {pat_str}: [{vals}]")

    # Products of normalized carriers
    print(f"\n=== Products of normalized carrier mags ===")
    for i in range(n_bits):
        for j in range(i + 1, n_bits):
            print(f"\n  carrier{i} * carrier{j}:")
            for k, pat in enumerate(patterns):
                prod = X_std[k, i] * X_std[k, j]
                target_and = pat[i] * pat[j]
                print(f"    {pat[i]},{pat[j]} -> product={prod:+6.2f}  (target AND={target_and})")

    mux.close()


if __name__ == "__main__":
    main()
