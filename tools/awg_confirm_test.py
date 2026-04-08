#!/usr/bin/env python3
"""Confirm corrected sample rate and check AWG frequencies."""
import ctypes, time, os, sys, platform
import numpy as np

# Load library
for p in [
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib",
    "/Applications/PicoScope 7 T&M.app/Contents/Resources/libps2000.dylib",
    "/Applications/PicoScope.app/Contents/Resources/libps2000.dylib",
]:
    if os.path.exists(p):
        lib = ctypes.cdll.LoadLibrary(p)
        break

lib.ps2000_open_unit.restype = ctypes.c_int16
lib.ps2000_set_sig_gen_built_in.argtypes = [
    ctypes.c_int16, ctypes.c_int32, ctypes.c_uint32, ctypes.c_int16,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_int32, ctypes.c_uint32,
]
lib.ps2000_set_sig_gen_built_in.restype = ctypes.c_int16

handle = lib.ps2000_open_unit()
lib.ps2000_set_channel(handle, 0, 1, 1, 6)
lib.ps2000_set_channel(handle, 1, 0, 1, 6)

# Timebase 3: actually 80 ns/sample = 12.5 MHz
# Timebase 7: 1280 ns/sample = 781.25 kHz (better freq resolution, still >Nyquist for 350 kHz)
# Let's test both

for tb, dt_ns, max_samp in [(3, 80, 8064), (7, 1280, 8064)]:
    dt = dt_ns * 1e-9
    fs = 1.0 / dt
    print(f"\n=== Timebase {tb}: {fs/1e6:.3f} MHz, {max_samp} samples, "
          f"duration = {max_samp*dt*1000:.2f} ms ===")
    print(f"  Nyquist: {fs/2/1000:.1f} kHz, FFT res (4x zeropad): {fs/max_samp/4:.1f} Hz")

    for freq in [10000.0, 50000.0, 100000.0, 200000.0]:
        lib.ps2000_set_sig_gen_built_in(
            handle, ctypes.c_int32(0), ctypes.c_uint32(2000000),
            ctypes.c_int16(0), ctypes.c_float(freq), ctypes.c_float(freq),
            ctypes.c_float(0), ctypes.c_float(0), ctypes.c_int32(0), ctypes.c_uint32(0),
        )
        time.sleep(0.15)
        lib.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
        time_ms = ctypes.c_int32()
        lib.ps2000_run_block(handle, max_samp, tb, 1, ctypes.byref(time_ms))
        t0 = time.time()
        while lib.ps2000_ready(handle) == 0:
            time.sleep(0.001)
            if time.time() - t0 > 5:
                break
        buf_a = (ctypes.c_int16 * max_samp)()
        buf_b = (ctypes.c_int16 * max_samp)()
        overflow = ctypes.c_int16()
        n = lib.ps2000_get_values(handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                                   None, None, ctypes.byref(overflow), max_samp)
        if n <= 0:
            print(f"  {freq:>9.0f} Hz → FAIL (n={n})")
            continue
        raw = np.array(buf_a[:n], dtype=np.float64)
        volts = raw / 32767 * 500
        pkpk = volts.max() - volts.min()

        padded = np.zeros(n * 4)
        padded[:n] = raw * np.hanning(n)
        spectrum = np.abs(np.fft.rfft(padded))
        freqs_arr = np.fft.rfftfreq(len(padded), d=dt)
        peak_idx = np.argmax(spectrum[1:]) + 1
        measured = freqs_arr[peak_idx]
        err_pct = (measured - freq) / freq * 100
        print(f"  {freq:>9.0f} Hz → measured {measured:>10.1f} Hz  error {err_pct:>+5.1f}%  pkpk {pkpk:.0f} mV")

lib.ps2000_stop(handle)
lib.ps2000_close_unit(handle)
print("\nDone.")
