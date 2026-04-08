#!/usr/bin/env python3
"""Quick AWG frequency sweep to determine actual output frequencies."""
import ctypes, time, sys, os, platform
import numpy as np

if platform.system() == "Darwin":
    from pathlib import Path
    for p in [
        "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources",
        "/Applications/PicoScope 7 T&M.app/Contents/Resources",
        "/Applications/PicoScope.app/Contents/Resources",
    ]:
        if Path(p).exists():
            cur = os.environ.get("DYLD_LIBRARY_PATH", "")
            if p not in cur:
                os.environ["DYLD_LIBRARY_PATH"] = f"{p}:{cur}" if cur else p
            break

from picosdk.ps2000 import ps2000

RANGE_MV = 500
CAPTURE  = 3968
ADC_MAX  = 32767

handle = ps2000.ps2000_open_unit()
if handle <= 0:
    print(f"ERROR: handle={handle}")
    sys.exit(1)

ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
ps2000.ps2000_set_channel(handle, 1, False, 1, 6)

test_freqs = [100, 1000, 5000, 10000, 50000, 100000]

print(f"{'Requested':>10}  {'Measured':>10}  {'Pk-Pk mV':>10}  {'SNR':>8}")
print("-" * 48)

for freq in test_freqs:
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 2000000, 0, freq, freq, 0, 0, 0, 0
        )
    except Exception:
        # Try arbitrary waveform fallback
        n_awg = 4096
        t = np.linspace(0, 2 * np.pi, n_awg, endpoint=False)
        sine = (np.sin(t) * 127).astype(np.uint8) + 128
        buf = (ctypes.c_uint8 * n_awg)(*sine.tolist())
        delta_phase = int(freq * (2**32) / 48_000_000)
        ps2000.ps2000_set_sig_gen_arbitrary(
            handle, 0, 2000000, delta_phase, delta_phase, 0, 0, buf, n_awg, 0, 0
        )

    time.sleep(0.1)

    ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
    time_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, CAPTURE, 3, 1, ctypes.byref(time_ms))

    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 5:
            break

    buf_a = (ctypes.c_int16 * CAPTURE)()
    buf_b = (ctypes.c_int16 * CAPTURE)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), CAPTURE
    )

    if n <= 0:
        print(f"{freq:>10}  {'FAIL':>10}")
        continue

    raw = np.array(buf_a[:n], dtype=np.float64)
    volts = raw / ADC_MAX * RANGE_MV
    pkpk = volts.max() - volts.min()

    padded = np.zeros(n * 4)
    padded[:n] = raw * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(padded))
    freqs_arr = np.fft.rfftfreq(len(padded), d=1e-6)

    peak_idx = np.argmax(spectrum[1:]) + 1
    peak_freq = freqs_arr[peak_idx]
    noise_floor = np.median(spectrum)
    snr = spectrum[peak_idx] / noise_floor if noise_floor > 0 else 0

    ratio = peak_freq / freq if freq > 0 else 0
    print(f"{freq:>10}  {peak_freq:>10.1f}  {pkpk:>10.1f}  {snr:>8.0f}  ratio={ratio:.4f}")

ps2000.ps2000_stop(handle)
ps2000.ps2000_close_unit(handle)
print("\nDone.")
