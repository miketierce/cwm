#!/usr/bin/env python3
"""
Quick diagnostic: run AWG chirp through T-adapter + PZT and check what Ch A sees.
Captures one block at timebase 7 (781 kHz, 8064 samples, ~10 ms).
"""
import ctypes, time, os, sys
import numpy as np

for p in [
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib",
    "/Applications/PicoScope 7 T&M.app/Contents/Resources/libps2000.dylib",
]:
    if os.path.exists(p):
        lib = ctypes.cdll.LoadLibrary(p)
        break

# Signatures
lib.ps2000_open_unit.restype = ctypes.c_int16
lib.ps2000_set_sig_gen_built_in.argtypes = [
    ctypes.c_int16, ctypes.c_int32, ctypes.c_uint32, ctypes.c_int16,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_int32, ctypes.c_uint32,
]
lib.ps2000_set_sig_gen_built_in.restype = ctypes.c_int16

TIMEBASE = 7
DT = 1280e-9    # 1280 ns per sample
N = 8064
FS = 1.0 / DT   # 781250 Hz

handle = lib.ps2000_open_unit()
print(f"Handle: {handle}")

lib.ps2000_set_channel(handle, 0, 1, 1, 6)  # Ch A, on, DC, ±500mV
lib.ps2000_set_channel(handle, 1, 0, 1, 6)  # Ch B off

# --- Baseline: no AWG, just noise ---
lib.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, ctypes.c_float(0), ctypes.c_float(0),
                                 ctypes.c_float(0), ctypes.c_float(0), 0, 0)
time.sleep(0.1)
lib.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
time_ms = ctypes.c_int32()
lib.ps2000_run_block(handle, N, TIMEBASE, 1, ctypes.byref(time_ms))
while lib.ps2000_ready(handle) == 0:
    time.sleep(0.001)
buf_a = (ctypes.c_int16 * N)()
buf_b = (ctypes.c_int16 * N)()
overflow = ctypes.c_int16()
n = lib.ps2000_get_values(handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                           None, None, ctypes.byref(overflow), N)
noise = np.array(buf_a[:n], dtype=np.float64)
noise_mv = noise / 32767 * 500
print(f"\n=== BASELINE (AWG OFF) — {n} samples ===")
print(f"  Pk-pk: {noise_mv.max()-noise_mv.min():.1f} mV,  RMS: {np.sqrt(np.mean(noise_mv**2)):.1f} mV")

# --- AWG chirp: sweep 1–100 kHz ---
ret = lib.ps2000_set_sig_gen_built_in(
    handle, 0, ctypes.c_uint32(2000000), ctypes.c_int16(0),
    ctypes.c_float(1000.0), ctypes.c_float(100000.0),
    ctypes.c_float(100.0), ctypes.c_float(0.0), 0, 0,
)
print(f"\nAWG chirp 1–100 kHz started (ret={ret})")
time.sleep(0.2)

lib.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
lib.ps2000_run_block(handle, N, TIMEBASE, 1, ctypes.byref(time_ms))
while lib.ps2000_ready(handle) == 0:
    time.sleep(0.001)
n = lib.ps2000_get_values(handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                           None, None, ctypes.byref(overflow), N)
signal = np.array(buf_a[:n], dtype=np.float64)
signal_mv = signal / 32767 * 500

print(f"\n=== WITH AWG CHIRP — {n} samples, {n*DT*1000:.1f} ms ===")
print(f"  Pk-pk: {signal_mv.max()-signal_mv.min():.1f} mV,  RMS: {np.sqrt(np.mean(signal_mv**2)):.1f} mV")

# FFT
padded = np.zeros(n * 4)
padded[:n] = signal * np.hanning(n)
spectrum = np.abs(np.fft.rfft(padded))
freqs = np.fft.rfftfreq(len(padded), d=DT)
noise_floor = np.median(spectrum)

from scipy.signal import find_peaks
peaks, _ = find_peaks(spectrum, height=noise_floor * 5, distance=20)
if len(peaks) > 0:
    heights = spectrum[peaks]
    top = np.argsort(heights)[::-1][:15]
    print(f"\n  Top {len(top)} peaks (SNR > 5×):")
    for i, idx in enumerate(top):
        p = peaks[idx]
        snr = spectrum[p] / noise_floor
        print(f"    #{i+1:2d}  {freqs[p]:9.1f} Hz  SNR {snr:6.1f}×")
    print(f"  Noise floor: {noise_floor:.0f}")
else:
    print(f"\n  No peaks above 5× noise floor ({noise_floor:.0f})")

# Signal-to-noise ratio vs baseline
signal_power = np.mean(signal_mv**2)
noise_power = np.mean(noise_mv**2)
print(f"\n  Signal/Noise power ratio: {signal_power/noise_power:.1f}×")

# Stop AWG
lib.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, ctypes.c_float(0), ctypes.c_float(0),
                                 ctypes.c_float(0), ctypes.c_float(0), 0, 0)
lib.ps2000_stop(handle)
lib.ps2000_close_unit(handle)
print("\nScope closed.")
