#!/usr/bin/env python3
"""
Final AWG diagnostic: verify AWG on/off timing and try everything.

Test A: Verify AWG turns off quickly (capture during → capture after)
Test B: Long continuous drive to build up resonance, then fast capture
Test C: Drive at known-high-transfer freq (35 kHz PZT self-res), ringdown
Test D: Arbitrary waveform with all enrolled frequencies (multitone via arb gen)
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

rod1_hz = db["rods"]["1"]["perturbed_hz"][:10]


def fft_analysis(raw, label=""):
    """Return (freq, mag, bin_hz, snr, peak_hz, peak_mag)."""
    rms = np.sqrt(np.mean(raw ** 2))
    windowed = raw * np.hanning(len(raw))
    nfft = len(raw) * 4
    mag = np.abs(np.fft.rfft(windowed, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
    bin_hz = freq[1]
    min_bin = int(500 / bin_hz)
    noise = np.median(mag[min_bin:])
    pk_idx = min_bin + np.argmax(mag[min_bin:])
    pk = mag[pk_idx]
    snr = pk / noise if noise > 0 else 0
    if label:
        print(f"  {label}: RMS={rms:.1f} peak={pk:.0f} @ {freq[pk_idx]:.0f} Hz "
              f"noise={noise:.0f} SNR={snr:.1f}x")
    return freq, mag, bin_hz, snr, freq[pk_idx], pk


handle = ps2000.ps2000_open_unit()
if handle <= 0:
    print(f"FATAL: handle={handle}")
    sys.exit(1)

print(f"=== FINAL AWG DIAGNOSTIC (handle={handle}) ===\n")

try:
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A, ±1V
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B OFF

    def cap(auto_ms=10):
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, auto_ms)
        t_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.001)
            if time.time() - t0 > 2:
                return None
        a = (ctypes.c_int16 * N_SAMPLES)()
        b = (ctypes.c_int16 * N_SAMPLES)()
        ov = ctypes.c_int16()
        n = ps2000.ps2000_get_values(handle, ctypes.byref(a), ctypes.byref(b),
                                      None, None, ctypes.byref(ov), N_SAMPLES)
        return np.array(a[:n], dtype=np.float64) if n > 0 else None

    # --- A: AWG on/off timing ---
    print("--- A: AWG TURN-OFF TIMING ---")
    # Drive at 1833 Hz (strongest transfer function)
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, AWG_DRIVE_UVPP, 0,
                                        1833.0, 1833.0, 0.0, 0.0, 0, 0)
    time.sleep(0.5)
    raw = cap()
    if raw is not None:
        fft_analysis(raw, "AWG ON @ 1833 Hz")

    # Rapid off + capture sequence at increasing delays
    for delay_ms in [0, 1, 2, 5, 10, 50]:
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, AWG_DRIVE_UVPP, 0,
                                            1833.0, 1833.0, 0.0, 0.0, 0, 0)
        time.sleep(0.2)
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0,
                                            1000.0, 1000.0, 0.0, 0.0, 0, 0)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        raw = cap(auto_ms=1)
        if raw is not None:
            fft_analysis(raw, f"OFF +{delay_ms}ms")

    # --- B: Very long drive (5s) then ringdown ---
    print("\n--- B: LONG DRIVE (5s sweep) -> RINGDOWN ---")
    inc = (100000.0 - 1000.0) / (5.0 / 0.001)
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, AWG_DRIVE_UVPP, 0,
                                        1000.0, 100000.0, inc, 0.001, 0, 0)
    time.sleep(5.0)
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0,
                                        1000.0, 1000.0, 0.0, 0.0, 0, 0)
    time.sleep(0.001)
    raw = cap(auto_ms=1)
    if raw is not None:
        fft_analysis(raw, "5s sweep -> ringdown")

    # --- C: Drive at 35 kHz (PZT self-res) then ringdown ---
    print("\n--- C: 35 kHz PZT RESONANCE DRIVE -> RINGDOWN ---")
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, AWG_DRIVE_UVPP, 0,
                                        35000.0, 35000.0, 0.0, 0.0, 0, 0)
    time.sleep(1.0)
    raw = cap()
    if raw is not None:
        fft_analysis(raw, "AWG ON @ 35kHz")

    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0,
                                        1000.0, 1000.0, 0.0, 0.0, 0, 0)
    time.sleep(0.002)
    raw = cap(auto_ms=1)
    if raw is not None:
        fft_analysis(raw, "35kHz ringdown")

    # --- D: Longer capture window (max samples) ---
    print("\n--- D: MAXIMUM CAPTURE WINDOW ---")
    max_samples = 32768  # ps2000 max for single block
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, AWG_DRIVE_UVPP, 0,
                                        1833.0, 1833.0, 0.0, 0.0, 0, 0)
    time.sleep(0.5)
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0,
                                        1000.0, 1000.0, 0.0, 0.0, 0, 0)
    time.sleep(0.001)
    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 1)
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, max_samples, TIMEBASE, 1, ctypes.byref(t_ms))
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 5:
            break
    a = (ctypes.c_int16 * max_samples)()
    b = (ctypes.c_int16 * max_samples)()
    ov = ctypes.c_int16()
    n = ps2000.ps2000_get_values(handle, ctypes.byref(a), ctypes.byref(b),
                                  None, None, ctypes.byref(ov), max_samples)
    if n > 0:
        raw = np.array(a[:n], dtype=np.float64)
        print(f"  Got {n} samples ({n/SAMPLE_RATE*1000:.1f} ms)")
        fft_analysis(raw, "Max-window ringdown (1833 Hz)")

    # --- E: Measure raw time-domain at 1833 Hz to see actual voltage levels ---
    print("\n--- E: RAW VOLTAGE MEASUREMENT ---")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 7)  # ±2V range
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, AWG_DRIVE_UVPP, 0,
                                        1833.0, 1833.0, 0.0, 0.0, 0, 0)
    time.sleep(0.5)
    raw = cap()
    if raw is not None:
        # ps2000 2204A: range 7 = ±2V, 16-bit signed → ±32767 = ±2V
        volts = raw * (2.0 / 32767.0)
        print(f"  AWG ON @ 1833 Hz: peak-peak = {np.ptp(volts)*1000:.1f} mV, "
              f"RMS = {np.sqrt(np.mean(volts**2))*1000:.1f} mV")

    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0,
                                        1000.0, 1000.0, 0.0, 0.0, 0, 0)
    time.sleep(0.003)
    raw = cap(auto_ms=1)
    if raw is not None:
        volts = raw * (2.0 / 32767.0)
        print(f"  AWG OFF ringdown: peak-peak = {np.ptp(volts)*1000:.1f} mV, "
              f"RMS = {np.sqrt(np.mean(volts**2))*1000:.1f} mV")

    # Reference: what does a TAP look like in voltage?
    print("\n  >>> FLICK Rod 1 NOW (you have 5 seconds)...")
    time.sleep(5)
    raw = cap(auto_ms=100)
    if raw is not None:
        volts = raw * (2.0 / 32767.0)
        print(f"  TAP: peak-peak = {np.ptp(volts)*1000:.1f} mV, "
              f"RMS = {np.sqrt(np.mean(volts**2))*1000:.1f} mV")
        _, mag, bin_hz, snr, pk_hz, _ = fft_analysis(raw, "TAP spectrum")

    # --- F: Noise floor in voltage ---
    time.sleep(2)
    raw = cap(auto_ms=100)
    if raw is not None:
        volts = raw * (2.0 / 32767.0)
        print(f"  Quiet: peak-peak = {np.ptp(volts)*1000:.1f} mV, "
              f"RMS = {np.sqrt(np.mean(volts**2))*1000:.1f} mV")

finally:
    try:
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0,
                                            1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("\nDone.")
