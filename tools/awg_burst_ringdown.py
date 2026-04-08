#!/usr/bin/env python3
"""
AWG burst-and-ringdown: excite with AWG, then capture free decay.

Strategy:
  1. Drive AWG for 50-100ms to build up energy in the rod
  2. Turn AWG OFF (amplitude=0)
  3. Immediately capture the ringdown on Ch A
  4. The rod will ring at its natural frequencies with ZERO feedthrough

This combines AWG excitation with tap-like clean spectrum.
"""
import ctypes
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from picosdk.ps2000 import ps2000

USERS = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "users.json"
with open(USERS) as f:
    db = json.load(f)


def awg_on(handle, start_hz=1000.0, stop_hz=100000.0, sweep_s=0.5):
    """Start AWG in sweep mode."""
    increment = (stop_hz - start_hz) / (sweep_s / 0.001)
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        start_hz, stop_hz, increment, 0.001, 0, 0
    )


def awg_off(handle):
    """Turn AWG output to 0V."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )


def capture_block(handle, auto_ms=1):
    """Single auto-triggered capture on Ch A."""
    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, auto_ms)
    time_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(time_ms))
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 2:
            return None
    buf_a = (ctypes.c_int16 * N_SAMPLES)()
    buf_b = (ctypes.c_int16 * N_SAMPLES)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), N_SAMPLES
    )
    if n <= 0:
        return None
    return np.array(buf_a[:n], dtype=np.float64)


def fft_of(raw, pad=4):
    """Windowed FFT of raw ADC data, returns (freq_axis, magnitude)."""
    windowed = raw * np.hanning(len(raw))
    nfft = len(raw) * pad
    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
    return freq_axis, fft_mag


print("=== AWG BURST-AND-RINGDOWN TEST ===")
print()

handle = ps2000.ps2000_open_unit()
if handle <= 0:
    print(f"FATAL: handle={handle}")
    sys.exit(1)

print(f"Scope opened (handle={handle})")

try:
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B OFF

    # --- Test 1: Noise floor (AWG off) ---
    print("\n--- T1: NOISE FLOOR (AWG off) ---")
    awg_off(handle)
    time.sleep(0.3)
    raw = capture_block(handle, auto_ms=100)
    if raw is not None:
        freq, mag = fft_of(raw)
        bin_hz = freq[1]
        noise_rms = np.sqrt(np.mean(raw ** 2))
        min_bin = int(500 / bin_hz)
        noise_floor = np.median(mag[min_bin:])
        print(f"  Noise RMS={noise_rms:.1f} ADC, FFT median={noise_floor:.0f}")
    else:
        print("  FAILED")
        noise_floor = 1.0

    # --- Test 2: Sweep + immediate capture (AWG still on = feedthrough+resonance) ---
    print("\n--- T2: SWEEP (AWG ON during capture = feedthrough) ---")
    awg_on(handle, 1000, 100000, 0.5)
    time.sleep(0.5)  # let sweep run once
    mags = []
    for i in range(8):
        raw = capture_block(handle, auto_ms=10)
        if raw is not None:
            _, m = fft_of(raw)
            mags.append(m)
    if mags:
        avg_mag = np.mean(mags, axis=0)
        peak_idx = min_bin + np.argmax(avg_mag[min_bin:])
        peak = avg_mag[peak_idx]
        snr = peak / noise_floor
        print(f"  Peak={peak:.0f} @ {freq[peak_idx]:.0f} Hz, SNR={snr:.1f}x")
    awg_off(handle)

    # --- Test 3: BURST AND RINGDOWN ---
    print("\n--- T3: BURST-AND-RINGDOWN ---")
    drive_times_ms = [20, 50, 100, 200, 500]
    gap_times_ms = [1, 2, 5]

    for drive_ms in drive_times_ms:
        for gap_ms in gap_times_ms:
            label = f"  drive={drive_ms:3d}ms gap={gap_ms}ms"
            # Excite with sweep
            awg_on(handle, 1000, 100000, drive_ms / 1000.0)
            time.sleep(drive_ms / 1000.0)
            # Kill AWG
            awg_off(handle)
            # Small gap for electrical transient to die
            time.sleep(gap_ms / 1000.0)
            # Capture ringdown
            raw = capture_block(handle, auto_ms=1)
            if raw is None:
                print(f"{label} | FAILED")
                continue

            rms = np.sqrt(np.mean(raw ** 2))
            _, m = fft_of(raw)
            peak_idx = min_bin + np.argmax(m[min_bin:])
            peak = m[peak_idx]
            snr = peak / noise_floor

            # Check enrolled peaks
            rod1_hz = db["rods"]["1"]["perturbed_hz"][:10]
            matched = 0
            for rod_f in rod1_hz:
                target_bin = int(round(rod_f / bin_hz))
                lo = max(min_bin, target_bin - 3)
                hi = min(len(m) - 1, target_bin + 3)
                local_peak = np.max(m[lo:hi + 1])
                if local_peak > noise_floor * 5:
                    matched += 1

            print(f"{label} | RMS={rms:7.1f} SNR={snr:6.1f}x "
                  f"peak={freq[peak_idx]:7.0f}Hz "
                  f"enrolled={matched}/10")

    # --- Test 4: Best config — deep average ---
    print("\n--- T4: BEST BURST CONFIG — deep average (20 reps) ---")
    best_drive = 100
    best_gap = 2
    all_mags = []
    for rep in range(20):
        awg_on(handle, 1000, 100000, best_drive / 1000.0)
        time.sleep(best_drive / 1000.0)
        awg_off(handle)
        time.sleep(best_gap / 1000.0)
        raw = capture_block(handle, auto_ms=1)
        if raw is not None:
            _, m = fft_of(raw)
            all_mags.append(m)

    if all_mags:
        avg = np.mean(all_mags, axis=0)
        min_bin = int(500 / bin_hz)
        noise = np.median(avg[min_bin:])
        peak_idx = min_bin + np.argmax(avg[min_bin:])
        peak = avg[peak_idx]
        snr = peak / noise
        print(f"  Averaged {len(all_mags)} captures")
        print(f"  Peak={peak:.0f} @ {freq[peak_idx]:.0f} Hz, noise={noise:.0f}, SNR={snr:.1f}x")

        # Show top 15 peaks
        threshold = noise * 3
        from scipy.signal import find_peaks as _find_peaks
        try:
            peak_indices, _ = _find_peaks(avg[min_bin:], height=threshold,
                                           distance=int(50 / bin_hz))
            peak_indices += min_bin
            peak_indices = peak_indices[np.argsort(avg[peak_indices])[::-1]][:15]
            print(f"\n  Top peaks (>{threshold:.0f}):")
            rod1_hz = db["rods"]["1"]["perturbed_hz"][:10]
            for pi in peak_indices:
                pf = freq[pi]
                pm = avg[pi]
                ps = pm / noise
                # Check if near enrolled peak
                match = ""
                for j, rf in enumerate(rod1_hz):
                    if abs(pf - rf) / rf < 0.05:
                        match = f" << Rod1 f{j+1}={rf:.0f}"
                        break
                print(f"    {pf:8.1f} Hz | mag={pm:10.0f} | SNR={ps:5.1f}x{match}")
        except ImportError:
            print("  (scipy not available for peak finding)")

        # Score each enrolled peak
        print(f"\n  Enrolled peak check (Rod 1):")
        n_found = 0
        for j, rf in enumerate(rod1_hz):
            target_bin = int(round(rf / bin_hz))
            lo = max(min_bin, target_bin - 3)
            hi = min(len(avg) - 1, target_bin + 3)
            local_peak = np.max(avg[lo:hi + 1])
            local_snr = local_peak / noise
            found = "FOUND" if local_snr > 5 else "missing"
            if local_snr > 5:
                n_found += 1
            print(f"    f{j+1}={rf:8.1f} Hz | local_peak={local_peak:10.0f} | "
                  f"SNR={local_snr:5.1f}x | {found}")
        print(f"\n  Result: {n_found}/10 enrolled peaks found in ringdown")

    # --- Test 5: Single-frequency burst ---
    print("\n--- T5: SINGLE-FREQ BURST (dwell at each Rod 1 peak) ---")
    rod1_hz = db["rods"]["1"]["perturbed_hz"][:10]
    for j, rf in enumerate(rod1_hz):
        mags_at = []
        for rep in range(8):
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(rf), float(rf), 0.0, 0.0, 0, 0
            )
            time.sleep(0.1)
            awg_off(handle)
            time.sleep(0.002)
            raw = capture_block(handle, auto_ms=1)
            if raw is not None:
                _, m = fft_of(raw)
                target_bin = int(round(rf / bin_hz))
                lo = max(0, target_bin - 3)
                hi = min(len(m) - 1, target_bin + 3)
                mags_at.append(float(np.max(m[lo:hi + 1])))

        if mags_at:
            avg_m = np.mean(mags_at)
            snr = avg_m / noise_floor
            verdict = ">" if snr > 10 else "|" if snr > 5 else "."
            print(f"  f{j+1}={rf:8.1f} Hz | ringdown mag={avg_m:10.0f} | "
                  f"SNR={snr:6.1f}x {verdict}")

finally:
    try:
        awg_off(handle)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("\nScope closed.")
