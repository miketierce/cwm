#!/usr/bin/env python3
"""Direct C library call to test AWG frequency output + measure sample rate."""
import ctypes, time, os, sys, platform
import numpy as np

# Load library directly
lib = None
search_paths = [
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib",
    "/Applications/PicoScope 7 T&M.app/Contents/Resources/libps2000.dylib",
    "/Applications/PicoScope.app/Contents/Resources/libps2000.dylib",
]
for p in search_paths:
    if os.path.exists(p):
        lib = ctypes.cdll.LoadLibrary(p)
        print(f"Loaded: {p}")
        break

if not lib:
    # set DYLD and use picosdk
    for p in [
        "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources",
        "/Applications/PicoScope 7 T&M.app/Contents/Resources",
        "/Applications/PicoScope.app/Contents/Resources",
    ]:
        if os.path.exists(p):
            os.environ["DYLD_LIBRARY_PATH"] = p
            break
    from picosdk.ps2000 import ps2000 as _mod
    lib = _mod._clib
    print("Using picosdk internal C library")

# Function signatures
lib.ps2000_open_unit.restype = ctypes.c_int16
lib.ps2000_close_unit.argtypes = [ctypes.c_int16]
lib.ps2000_close_unit.restype = ctypes.c_int16
lib.ps2000_stop.argtypes = [ctypes.c_int16]
lib.ps2000_stop.restype = ctypes.c_int16
lib.ps2000_set_channel.argtypes = [ctypes.c_int16] * 5
lib.ps2000_set_channel.restype = ctypes.c_int16
lib.ps2000_ready.argtypes = [ctypes.c_int16]
lib.ps2000_ready.restype = ctypes.c_int16
lib.ps2000_set_trigger.argtypes = [ctypes.c_int16] * 6
lib.ps2000_set_trigger.restype = ctypes.c_int16
lib.ps2000_run_block.argtypes = [ctypes.c_int16, ctypes.c_int32, ctypes.c_int16,
                                  ctypes.c_int16, ctypes.POINTER(ctypes.c_int32)]
lib.ps2000_run_block.restype = ctypes.c_int16
lib.ps2000_get_values.argtypes = [ctypes.c_int16, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_int32]
lib.ps2000_get_values.restype = ctypes.c_int32
lib.ps2000_get_timebase.argtypes = [ctypes.c_int16, ctypes.c_int16, ctypes.c_int32,
                                     ctypes.POINTER(ctypes.c_int32),
                                     ctypes.POINTER(ctypes.c_int16),
                                     ctypes.c_int16,
                                     ctypes.POINTER(ctypes.c_int32)]
lib.ps2000_get_timebase.restype = ctypes.c_int16
lib.ps2000_get_unit_info.argtypes = [ctypes.c_int16, ctypes.c_char_p, ctypes.c_int16, ctypes.c_int16]
lib.ps2000_get_unit_info.restype = ctypes.c_int16

lib.ps2000_set_sig_gen_built_in.argtypes = [
    ctypes.c_int16,   # handle
    ctypes.c_int32,   # offset
    ctypes.c_uint32,  # pkToPk
    ctypes.c_int16,   # waveType
    ctypes.c_float,   # startFreq
    ctypes.c_float,   # stopFreq
    ctypes.c_float,   # increment
    ctypes.c_float,   # dwellTime
    ctypes.c_int32,   # sweepType
    ctypes.c_uint32,  # sweeps
]
lib.ps2000_set_sig_gen_built_in.restype = ctypes.c_int16

handle = lib.ps2000_open_unit()
print(f"Handle: {handle}")

# Get unit info
info_buf = ctypes.create_string_buffer(80)
for line in range(10):
    r = lib.ps2000_get_unit_info(handle, info_buf, 80, line)
    if r > 0:
        print(f"  Info[{line}]: {info_buf.value.decode()}")

# Set up channel
lib.ps2000_set_channel(handle, 0, 1, 1, 6)  # Ch A, on, DC, ±500mV
lib.ps2000_set_channel(handle, 1, 0, 1, 6)  # Ch B off

# Get timebase info
for tb in range(8):
    ti = ctypes.c_int32()
    tu = ctypes.c_int16()
    mx = ctypes.c_int32()
    ret = lib.ps2000_get_timebase(handle, tb, 3968, ctypes.byref(ti), ctypes.byref(tu), 1, ctypes.byref(mx))
    if ret != 0:
        units = {0: "fs", 1: "ps", 2: "ns", 3: "us", 4: "ms", 5: "s"}
        unit_s = {0: 1e-15, 1: 1e-12, 2: 1e-9, 3: 1e-6, 4: 1e-3, 5: 1}
        dt = ti.value * unit_s.get(tu.value, 1e-6)
        fs = 1.0 / dt if dt > 0 else 0
        print(f"  Timebase {tb}: interval={ti.value} {units.get(tu.value, '?')}, "
              f"fs={fs/1e6:.3f} MHz, max_samples={mx.value}")

# Test AWG at multiple frequencies
print("\n=== AWG Frequency Test ===")
print(f"{'Request Hz':>12}  {'Pk-Pk mV':>10}  {'Peak Hz':>10}")
print("-" * 40)

for freq in [1000.0, 5000.0, 10000.0, 20000.0, 50000.0, 100000.0]:
    ret = lib.ps2000_set_sig_gen_built_in(
        handle,
        ctypes.c_int32(0),
        ctypes.c_uint32(2000000),
        ctypes.c_int16(0),  # sine
        ctypes.c_float(freq),
        ctypes.c_float(freq),
        ctypes.c_float(0.0),
        ctypes.c_float(0.0),
        ctypes.c_int32(0),
        ctypes.c_uint32(0),
    )

    time.sleep(0.15)

    # Auto-trigger
    lib.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)

    time_ms = ctypes.c_int32()
    lib.ps2000_run_block(handle, 3968, 3, 1, ctypes.byref(time_ms))

    t0 = time.time()
    while lib.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 5:
            break

    buf_a = (ctypes.c_int16 * 3968)()
    buf_b = (ctypes.c_int16 * 3968)()
    overflow = ctypes.c_int16()
    n = lib.ps2000_get_values(handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                               None, None, ctypes.byref(overflow), 3968)

    raw = np.array(buf_a[:n], dtype=np.float64)
    volts = raw / 32767 * 500
    pkpk = volts.max() - volts.min()

    # Use 1 µs/sample (timebase 3 for PS2204A ≈ 1 MHz)
    dt = 1e-6
    padded = np.zeros(n * 4)
    padded[:n] = raw * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(padded))
    freqs = np.fft.rfftfreq(len(padded), d=dt)
    peak_idx = np.argmax(spectrum[1:]) + 1
    measured = freqs[peak_idx]

    print(f"  {freq:>10.0f}  {pkpk:>10.1f}  {measured:>10.1f}")

    # For 10 kHz case, also count zero crossings for independent freq measurement
    if freq == 10000.0:
        crossings = 0
        for i in range(1, n):
            if (buf_a[i-1] < 0 and buf_a[i] >= 0):
                crossings += 1
        zc_freq = crossings / (n * dt)
        print(f"    Zero-crossing freq estimate: {zc_freq:.0f} Hz ({crossings} crossings in {n*dt*1000:.1f} ms)")

lib.ps2000_stop(handle)
lib.ps2000_close_unit(handle)
print("\nDone.")
