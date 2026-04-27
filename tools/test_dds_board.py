#!/usr/bin/env python3
"""Quick smoke test for AD9833 DDS boards.

Tests one board at a time:
  1. Send frequency command via serial → verify firmware echo
  2. Capture with PicoScope → verify sine wave at expected frequency
  3. Measure amplitude → verify analog output is alive

Usage:
    # Serial-only test (no PicoScope needed):
    python3 tools/test_dds_board.py --port /dev/cu.usbserial-11310

    # Full test with PicoScope capture:
    DYLD_LIBRARY_PATH="/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources" \
    python3 tools/test_dds_board.py --port /dev/cu.usbserial-11310 --pico

Wire ONE AD9833 board to Arduino Nano:
    VCC  → 5V
    GND  → GND  (both DGND and AGND)
    DAT  → D11  (MOSI)
    CLK  → D13  (SCK)
    FSY  → D10  (CS)
    OUT  → PicoScope Ch A probe tip (for --pico mode)
"""

import argparse
import sys
import time
import serial
import numpy as np


def test_serial(ser, freq_hz=10000):
    """Send frequency command and check firmware response."""
    print(f"\n{'='*50}")
    print(f"SERIAL TEST: commanding {freq_hz} Hz")
    print(f"{'='*50}")

    # Flush
    ser.reset_input_buffer()
    time.sleep(0.1)

    # Set frequency
    cmd = f"F{freq_hz}\n"
    ser.write(cmd.encode("ascii"))
    time.sleep(0.05)
    resp = ser.readline().decode("ascii", errors="replace").strip()
    print(f"  Sent:     {cmd.strip()}")
    print(f"  Response: {resp}")

    if resp == f"DDS:{freq_hz}":
        print(f"  ✓ Firmware acknowledged {freq_hz} Hz")
    else:
        print(f"  ✗ Unexpected response (expected DDS:{freq_hz})")
        return False

    # Query
    ser.write(b"D?\n")
    time.sleep(0.05)
    resp2 = ser.readline().decode("ascii", errors="replace").strip()
    print(f"  Query:    {resp2}")

    # Accept both old format "DDS:<freq>" and new 3-ch "DDS:1=<freq>,2=0,3=0"
    if resp2 == f"DDS:{freq_hz}" or resp2 == f"DDS:1={freq_hz},2=0,3=0":
        print(f"  ✓ Query confirmed")
    else:
        print(f"  ✗ Query mismatch")
        return False

    return True


def test_pico(freq_hz=10000):
    """Capture with PicoScope and verify sine wave at freq_hz."""
    print(f"\n{'='*50}")
    print(f"PICOSCOPE TEST: looking for {freq_hz} Hz sine")
    print(f"{'='*50}")

    try:
        import ctypes
        ps = ctypes.CDLL("libps2000.dylib")
    except OSError as e:
        print(f"  ✗ Cannot load PicoScope driver: {e}")
        print(f"    Set DYLD_LIBRARY_PATH and retry.")
        return False

    # Open
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"  ✗ Cannot open PicoScope (handle={handle})")
        return False
    print(f"  PicoScope handle: {handle}")

    try:
        # Channel A: ±1V (range index 7), DC coupling
        ok = ps.ps2000_set_channel(handle, 0, 1, 1, 7)
        if ok == 0:
            print(f"  ✗ set_channel failed")
            return False

        # Channel B: disabled
        ps.ps2000_set_channel(handle, 1, 0, 1, 7)

        # Timebase 7 = 1280 ns/sample → 781.25 kHz
        n_samples = 8064
        timebase = 7

        # Trigger: none, auto=100ms
        ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 100)

        # Run block
        time_ms = ctypes.c_int32()
        ps.ps2000_run_block(
            handle, n_samples, timebase, 1, ctypes.byref(time_ms)
        )

        # Wait for ready (up to 5s)
        t0 = time.time()
        while ps.ps2000_ready(handle) == 0:
            time.sleep(0.001)
            if time.time() - t0 > 5:
                print(f"  ✗ Capture timed out")
                return False

        # Get values
        buf_a = (ctypes.c_int16 * n_samples)()
        buf_b = (ctypes.c_int16 * n_samples)()
        overflow = ctypes.c_int16()
        n_got = ps.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), n_samples
        )
        if n_got <= 0:
            print(f"  ✗ get_values returned {n_got}")
            return False

        data = np.array(buf_a[:n_got], dtype=np.float64)
        print(f"  Captured {n_got} samples")

        # FFT — remove DC offset before windowing
        dt = 1280e-9  # seconds per sample at timebase 7
        fs = 1.0 / dt
        data -= np.mean(data)  # remove DC bias (AD9833 outputs ~0.6V DC)
        window = np.hanning(len(data))
        spectrum = np.abs(np.fft.rfft(data * window))
        freqs = np.fft.rfftfreq(len(data), d=dt)

        # Find peak above 500 Hz (skip DC leakage bins)
        min_bin = int(500 / (fs / len(data))) + 1
        peak_idx = np.argmax(spectrum[min_bin:]) + min_bin
        peak_freq = freqs[peak_idx]
        peak_mag = spectrum[peak_idx]
        noise_floor = np.median(spectrum[1:])
        snr_ratio = peak_mag / noise_floor if noise_floor > 0 else 0

        print(f"  Peak frequency: {peak_freq:.0f} Hz")
        print(f"  Peak magnitude: {peak_mag:.0f}")
        print(f"  Noise floor:    {noise_floor:.1f}")
        print(f"  Peak/Noise:     {snr_ratio:.1f}×")

        # Check: peak should be within 5% of target
        freq_error = abs(peak_freq - freq_hz) / freq_hz
        if freq_error < 0.05 and snr_ratio > 5:
            print(f"  ✓ PASS — {peak_freq:.0f} Hz sine detected, {snr_ratio:.0f}× above noise")
            return True
        elif snr_ratio < 5:
            print(f"  ✗ FAIL — no clear signal above noise (ratio {snr_ratio:.1f}×)")
            # Check amplitude
            adc_pp = np.max(data) - np.min(data)
            mv_pp = adc_pp / 32767 * 1000  # ±1V range
            print(f"  ADC peak-to-peak: {adc_pp:.0f} counts ({mv_pp:.0f} mV)")
            if adc_pp < 10:
                print(f"  → No signal at all. Check wiring: OUT → Ch A probe tip")
            return False
        else:
            print(f"  ✗ FAIL — peak at {peak_freq:.0f} Hz, expected {freq_hz} Hz")
            return False
    finally:
        ps.ps2000_stop(handle)
        ps.ps2000_close_unit(handle)
        print(f"  PicoScope closed.")


def main():
    parser = argparse.ArgumentParser(description="Smoke-test AD9833 DDS board")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--freq", type=int, default=10000, help="Test frequency in Hz")
    parser.add_argument("--pico", action="store_true", help="Also capture with PicoScope")
    args = parser.parse_args()

    test_freqs = [1000, 10000, 50000]  # Test at three frequencies

    print("AD9833 DDS Board Smoke Test")
    print("=" * 50)
    print(f"Port: {args.port}")
    print(f"Test frequencies: {test_freqs}")

    # Open serial
    try:
        ser = serial.Serial(args.port, args.baud, timeout=2)
        time.sleep(2)  # Arduino reset
        boot = ser.readline().decode("ascii", errors="replace").strip()
        print(f"Boot message: {boot}")
        if "OK" in boot or "DDS:ready" in boot:
            print("✓ Arduino firmware responding")
        else:
            print(f"⚠ Unexpected boot: {boot!r}")
    except Exception as e:
        print(f"✗ Cannot open serial: {e}")
        sys.exit(1)

    serial_pass = 0
    pico_pass = 0

    for freq in test_freqs:
        if test_serial(ser, freq):
            serial_pass += 1

            if args.pico:
                time.sleep(0.2)  # Let DDS settle
                if test_pico(freq):
                    pico_pass += 1

    # Silence DDS
    ser.write(b"Foff\n")
    time.sleep(0.05)
    ser.readline()
    ser.close()

    # Summary
    print(f"\n{'='*50}")
    print(f"RESULTS")
    print(f"{'='*50}")
    print(f"  Serial: {serial_pass}/{len(test_freqs)} passed")
    if args.pico:
        print(f"  PicoScope: {pico_pass}/{len(test_freqs)} passed")

    if serial_pass == len(test_freqs):
        if args.pico and pico_pass == len(test_freqs):
            print(f"\n  ✓ BOARD GOOD — SPI + analog output verified")
        elif args.pico:
            print(f"\n  ⚠ SPI works but analog output issue — check OUT pin solder")
        else:
            print(f"\n  ✓ SPI communication OK (run with --pico to verify analog output)")
    else:
        print(f"\n  ✗ BOARD FAIL — check solder joints and wiring")

    sys.exit(0 if serial_pass == len(test_freqs) else 1)


if __name__ == "__main__":
    main()
