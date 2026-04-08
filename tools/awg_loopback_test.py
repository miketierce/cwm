#!/usr/bin/env python3
"""
AWG loopback test: output a 10 kHz sine from AWG, read it on Ch A.
Confirms the improvised BNC cable actually carries signal.

Wiring for this test ONLY:
  AWG OUT → clipped BNC pair → Ch A IN
  (No T-adapter, no PZT — just the two cables clipped together)
"""
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

TEST_FREQ = 10000   # 10 kHz sine from AWG
RANGE_MV  = 500     # ±500 mV
CAPTURE   = 3968
ADC_MAX   = 32767

handle = ps2000.ps2000_open_unit()
if handle <= 0:
    print(f"ERROR: ps2000_open_unit returned {handle}")
    sys.exit(1)

print(f"PicoScope opened (handle {handle})")

try:
    # Channel A on, DC coupled, ±500 mV (range 6)
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)

    # ------ Start AWG: 10 kHz sine ------
    # Built-in signal generator for ps2000:
    # ps2000_set_sig_gen_built_in(handle, offsetVoltage, pkToPk, waveType, startFreq, stopFreq,
    #                              increment, dwellTime, sweepType, sweeps)
    # waveType: 0=sine, 1=square, 2=triangle, 3=dc
    # For a fixed 10 kHz sine: start=stop=10000, increment=0
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle,
            0,              # offset (µV) — 0
            2000000,        # pk-to-pk (µV) — 2 Vpp = 2,000,000 µV (max for 2204A)
            0,              # sine
            TEST_FREQ,      # start freq
            TEST_FREQ,      # stop freq (same = fixed)
            0,              # increment
            0,              # dwell time
            0,              # sweep type (up)
            0               # sweeps (0 = continuous)
        )
        print(f"  AWG: {TEST_FREQ} Hz sine, 2 Vpp")
    except Exception as e:
        print(f"  AWG built-in failed: {e}")
        print("  Trying arbitrary waveform...")
        # Fallback: arbitrary waveform
        n_awg = 4096
        t = np.linspace(0, 2 * np.pi, n_awg, endpoint=False)
        sine = (np.sin(t) * 127).astype(np.uint8) + 128
        buf = (ctypes.c_uint8 * n_awg)(*sine.tolist())
        # delta_phase for desired frequency:
        # freq = delta_phase * awg_clock / 2^32
        # For ps2000: awg_clock = 48 MHz? Let's try a few
        awg_clock = 48_000_000
        delta_phase = int(TEST_FREQ * (2**32) / awg_clock)
        print(f"  AWG arb: delta_phase={delta_phase}")
        ps2000.ps2000_set_sig_gen_arbitrary(
            handle, 0, 2000000, delta_phase, delta_phase, 0, 0, buf, n_awg, 0, 0
        )

    time.sleep(0.1)  # let AWG stabilize

    # ------ Capture without trigger (auto-trigger immediately) ------
    # No trigger — just grab whatever's on Ch A
    ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)  # source=5 (none), auto=1ms

    time_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, CAPTURE, 3, 1, ctypes.byref(time_ms))

    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 5:
            print("TIMEOUT waiting for capture")
            sys.exit(1)

    buf_a = (ctypes.c_int16 * CAPTURE)()
    buf_b = (ctypes.c_int16 * CAPTURE)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), CAPTURE
    )

    if n <= 0:
        print(f"ERROR: got {n} samples")
        sys.exit(1)

    raw = np.array(buf_a[:n], dtype=np.float64)
    volts = raw / ADC_MAX * RANGE_MV  # mV

    print(f"\n=== Ch A WAVEFORM ({n} samples, ~{n/1e6*1000:.1f} ms) ===")
    print(f"  Peak-to-peak:  {volts.max() - volts.min():.1f} mV")
    print(f"  RMS:           {np.sqrt(np.mean(volts**2)):.1f} mV")

    # FFT
    padded = np.zeros(n * 4)
    padded[:n] = raw * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(padded))
    freqs = np.fft.rfftfreq(len(padded), d=1e-6)

    peak_idx = np.argmax(spectrum[1:]) + 1  # skip DC
    peak_freq = freqs[peak_idx]
    noise_floor = np.median(spectrum)
    snr = spectrum[peak_idx] / noise_floor if noise_floor > 0 else 0

    print(f"\n=== FFT ===")
    print(f"  Dominant frequency: {peak_freq:.1f} Hz")
    print(f"  Expected:          {TEST_FREQ} Hz")
    print(f"  SNR:               {snr:.1f}×")
    print(f"  Noise floor:       {noise_floor:.0f}")

    if abs(peak_freq - TEST_FREQ) < 500 and snr > 10:
        print(f"\n✅ SUCCESS — AWG signal is reaching Ch A!")
        print(f"   The improvised cable works. You can proceed with T-adapter + PZT.")
    elif snr > 10:
        print(f"\n⚠️  Strong signal at {peak_freq:.1f} Hz (not {TEST_FREQ} Hz) — AWG may be at wrong freq")
    else:
        print(f"\n❌ FAIL — No clear signal from AWG on Ch A (SNR {snr:.1f}×)")
        print(f"   Check cable connections: red-to-red, black-to-black at the alligator junction")

    # Show top 5 peaks
    from scipy.signal import find_peaks
    peaks, _ = find_peaks(spectrum, height=noise_floor * 3, distance=20)
    if len(peaks) > 0:
        heights = spectrum[peaks]
        top = np.argsort(heights)[::-1][:5]
        print(f"\n  Top peaks:")
        for i, idx in enumerate(top):
            p = peaks[idx]
            print(f"    #{i+1}  {freqs[p]:9.1f} Hz  SNR {spectrum[p]/noise_floor:.1f}×")

finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("\nScope closed.")
