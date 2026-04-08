#!/usr/bin/env python3
"""
Stepped-dwell resonance test: drive AWG at each enrolled frequency,
wait for steady-state, capture response on Ch A ONLY (Ch B breaks ps2000).

Key question: is the AWG->PZT->rod->PZT->ChA path producing rod
resonances, or just electrical feedthrough?
"""
import ctypes
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from picosdk.ps2000 import ps2000

USERS = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "users.json"
with open(USERS) as f:
    db = json.load(f)

rod1_hz = db["rods"]["1"]["perturbed_hz"][:10]
off_res = [(rod1_hz[i] + rod1_hz[i + 1]) / 2 for i in range(len(rod1_hz) - 1)]

print("=== STEPPED-DWELL RESONANCE TEST ===")
print(f"Rod 1 peaks: {[round(f, 1) for f in rod1_hz]}")
print(f"Off-resonance: {[round(f, 1) for f in off_res]}")
print()

handle = ps2000.ps2000_open_unit()
if handle <= 0:
    print(f"FATAL: handle={handle}")
    sys.exit(1)

print(f"Scope opened (handle={handle})")

try:
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B OFF

    def capture_at_freq(freq_hz, n_avg=8, settle_s=0.3):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
        )
        time.sleep(settle_s)

        magnitudes = []
        rms_vals = []
        for _ in range(n_avg):
            ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
            time_ms = ctypes.c_int32()
            ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(time_ms))
            t0 = time.time()
            while ps2000.ps2000_ready(handle) == 0:
                time.sleep(0.002)
                if time.time() - t0 > 2:
                    break
            buf_a = (ctypes.c_int16 * N_SAMPLES)()
            buf_b = (ctypes.c_int16 * N_SAMPLES)()
            overflow = ctypes.c_int16()
            n = ps2000.ps2000_get_values(
                handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                None, None, ctypes.byref(overflow), N_SAMPLES
            )
            if n > 0:
                raw = np.array(buf_a[:n], dtype=np.float64)
                rms_vals.append(np.sqrt(np.mean(raw ** 2)))
                windowed = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                target_bin = int(round(freq_hz / bin_hz))
                lo_bin = max(0, target_bin - 3)
                hi_bin = min(len(fft) - 1, target_bin + 3)
                peak_mag = float(np.max(fft[lo_bin:hi_bin + 1]))
                magnitudes.append(peak_mag)

        if not magnitudes:
            return 0.0, 0.0, 0.0
        return float(np.mean(magnitudes)), float(np.std(magnitudes)), float(np.mean(rms_vals))

    print("ON-RESONANCE (Rod 1 enrolled peaks):")
    on_results = []
    for f in rod1_hz:
        mag, std, rms = capture_at_freq(f, n_avg=8, settle_s=0.3)
        on_results.append(mag)
        print(f"  {f:8.1f} Hz | mag={mag:10.0f} +/- {std:6.0f} | RMS={rms:6.1f}")

    print("\nOFF-RESONANCE (midpoints):")
    off_results = []
    for f in off_res:
        mag, std, rms = capture_at_freq(f, n_avg=8, settle_s=0.3)
        off_results.append(mag)
        print(f"  {f:8.1f} Hz | mag={mag:10.0f} +/- {std:6.0f} | RMS={rms:6.1f}")

    print("\nRESONANCE RATIO (on / nearest off):")
    for i, (f_on, mag_on) in enumerate(zip(rod1_hz, on_results)):
        nearest_off_idx = min(range(len(off_res)),
                              key=lambda j: abs(off_res[j] - f_on))
        mag_off = off_results[nearest_off_idx]
        ratio = mag_on / mag_off if mag_off > 0 else float("inf")
        bar = "#" * int(min(ratio * 5, 40))
        verdict = "RESONANCE" if ratio > 2 else "feedthrough"
        print(f"  {f_on:8.1f} Hz | on={mag_on:8.0f} off={mag_off:8.0f} | "
              f"ratio={ratio:5.2f} | {verdict} {bar}")

    print("\nREFERENCE:")
    mag_35k, _, rms_35k = capture_at_freq(35000, n_avg=4, settle_s=0.2)
    print(f"  35000 Hz (PZT res): mag={mag_35k:.0f}, RMS={rms_35k:.1f}")

    # AWG off
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    time.sleep(0.3)
    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
    time_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(time_ms))
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.002)
        if time.time() - t0 > 2:
            break
    buf_a = (ctypes.c_int16 * N_SAMPLES)()
    buf_b = (ctypes.c_int16 * N_SAMPLES)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                                  None, None, ctypes.byref(overflow), N_SAMPLES)
    if n > 0:
        raw = np.array(buf_a[:n], dtype=np.float64)
        print(f"  AWG off noise: RMS={np.sqrt(np.mean(raw ** 2)):.1f} ADC")

    avg_on = np.mean(on_results)
    avg_off = np.mean(off_results)
    print(f"\n  Mean on-resonance:  {avg_on:.0f}")
    print(f"  Mean off-resonance: {avg_off:.0f}")
    print(f"  Overall ratio:      {avg_on / avg_off:.2f}")

    if avg_on / avg_off > 1.5:
        print("\n  >>> ROD IS RESONATING — on-resonance exceeds feedthrough")
    else:
        print("\n  >>> NO CLEAR RESONANCE — mostly electrical feedthrough")

finally:
    try:
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
