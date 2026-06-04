#!/usr/bin/env python3
"""
T5.1 — DDS Alive/Dead Test
Tests both AD9833 modules for:
  1. Serial communication (Arduino responds to commands)
  2. Analog output (PicoScope sees signal at DDS-driven frequency)

Signal path tested:
  DDS OUT → 10kΩ sum resistor → Board D (×3.69) → TX PZT → plate → RX PZT → Board A (×11) → Ch A

If Ch A shows signal at the commanded frequency, the DDS is alive AND the
sum network is passing signal (even if attenuated).

Usage:
  python tools/test_dds_alive.py
  python tools/test_dds_alive.py --mux-port /dev/cu.usbserial-11310
  python tools/test_dds_alive.py --direct  # probe on sum node, no plate path
"""

import argparse
import ctypes
import os
import sys
import time

os.environ['DYLD_LIBRARY_PATH'] = (
    '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
)

import numpy as np
import serial

# ─── PicoScope ps2000 ───
from picosdk.ps2000 import ps2000 as ps

# ─── Constants ───
DDS_PORT = "/dev/cu.usbserial-11330"
MUX_PORT = "/dev/cu.usbserial-11310"
DDS_BAUD = 115200
MUX_BAUD = 9600

N_SAMPLES = 8064
TIMEBASE = 7        # → 1.28 µs/sample, 781.25 kHz
SAMPLE_RATE = 781250.0
CH_A_RANGE = 7      # ±5V

# Test frequencies — our known plate modes
TEST_FREQS = [35840, 54920, 57037, 97011]


def open_scope():
    """Open PicoScope and configure Ch A."""
    handle = ps.ps2000_open_unit() if hasattr(ps, 'ps2000_open_unit') else ps.ps2000_open_unit()
    if handle <= 0:
        print("ERROR: Cannot open PicoScope (handle=%d)" % handle)
        sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, CH_A_RANGE)  # Ch A, enabled, AC (dc=0), ±5V
    ps.ps2000_set_channel(handle, 1, 0, 0, CH_A_RANGE)  # Ch B disabled
    return handle


def close_scope(handle):
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(handle)


def capture(handle, n_avg=10):
    """Capture and return averaged magnitude spectrum."""
    spectra = []
    for _ in range(n_avg):
        buf_a = (ctypes.c_int16 * N_SAMPLES)()
        buf_b = (ctypes.c_int16 * N_SAMPLES)()
        ov = ctypes.c_int16(0)
        ps.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)  # ChA trigger, auto 100ms
        ms = ctypes.c_int32(0)
        ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(ms))
        time.sleep(0.015)
        for _w in range(500):
            if ps.ps2000_ready(handle):
                break
            time.sleep(0.005)
        ps.ps2000_get_values(handle, ctypes.byref(buf_a), None, None, None,
                             ctypes.byref(ov), N_SAMPLES, 0)
        data = np.array(buf_a[:], dtype=float)
        data -= np.mean(data)
        window = np.hanning(len(data))
        spectrum = np.abs(np.fft.rfft(data * window))
        spectra.append(spectrum)
    return np.mean(spectra, axis=0)


def measure_at_freq(handle, freq_hz):
    """Measure peak magnitude and SNR at a specific frequency."""
    spectrum = capture(handle, n_avg=10)
    freqs = np.fft.rfftfreq(N_SAMPLES, d=1.0 / SAMPLE_RATE)

    # Find bin closest to target frequency
    target_bin = np.argmin(np.abs(freqs - freq_hz))

    # Peak in ±5 bin window around target
    lo = max(1, target_bin - 5)
    hi = min(len(spectrum) - 1, target_bin + 5)
    peak_bin = lo + np.argmax(spectrum[lo:hi+1])
    peak_mag = spectrum[peak_bin]
    peak_freq = freqs[peak_bin]

    # Noise: median of spectrum excluding ±20 bins around target
    mask = np.ones(len(spectrum), dtype=bool)
    mask[max(0, target_bin-20):min(len(spectrum), target_bin+20)] = False
    mask[0] = False  # exclude DC
    noise = np.median(spectrum[mask])

    snr = peak_mag / noise if noise > 0 else 0
    return peak_freq, peak_mag, noise, snr


def main():
    parser = argparse.ArgumentParser(description="Test AD9833 DDS modules alive/dead")
    parser.add_argument("--dds-port", default=DDS_PORT, help="DDS Arduino serial port")
    parser.add_argument("--mux-port", default=MUX_PORT, help="Relay mux serial port")
    parser.add_argument("--direct", action="store_true",
                        help="Probe is on sum node directly (skip mux setup)")
    parser.add_argument("--relay", type=int, default=8,
                        help="Relay channel for RX PZT (default: 8 = NE)")
    args = parser.parse_args()

    print("=" * 60)
    print("T5.1 — DDS Alive/Dead Test")
    print("=" * 60)

    # ─── Open DDS serial ───
    print("\n[1] Opening DDS controller on %s @ %d baud..." % (args.dds_port, DDS_BAUD))
    try:
        dds = serial.Serial(args.dds_port, DDS_BAUD, timeout=2)
        time.sleep(2.5)  # Arduino boot
        dds.reset_input_buffer()
    except serial.SerialException as e:
        print("  ERROR: Cannot open DDS port: %s" % e)
        print("  Is Arduino 2 connected? Check: ls /dev/cu.usbserial-*")
        sys.exit(1)

    # Query DDS status
    dds.write(b'D?\n')
    time.sleep(0.05)
    resp = dds.readline().decode('ascii', errors='replace').strip()
    print("  DDS status: %s" % (resp if resp else "(no response)"))

    if not resp:
        print("  WARNING: No response from DDS controller!")
        print("  Firmware may not be loaded, or wrong port.")
        serial_alive = False
    else:
        serial_alive = True
        print("  Serial: ALIVE")

    # ─── Open PicoScope ───
    print("\n[2] Opening PicoScope...")
    handle = open_scope()
    print("  PicoScope ready (handle=%d)" % handle)

    # Stop PicoScope AWG to avoid interference
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    # ─── Setup relay mux ───
    if not args.direct:
        print("\n[3] Setting relay mux to ch %d..." % args.relay)
        try:
            mux = serial.Serial(args.mux_port, MUX_BAUD, timeout=1)
            time.sleep(2.5)
            mux.reset_input_buffer()
            mux.write(('%d\n' % args.relay).encode())
            time.sleep(0.05)
            mux_resp = mux.readline().decode().strip()
            print("  Mux: %s" % mux_resp)
        except serial.SerialException as e:
            print("  WARNING: Cannot open mux: %s" % e)
            print("  Continuing without mux (probe must be on sum node)")
    else:
        print("\n[3] Direct mode — skipping mux (probe on sum node)")

    # ─── Baseline (silence) ───
    print("\n[4] Measuring baseline (DDS off)...")
    dds.write(b'Foff\n')
    time.sleep(0.1)
    dds.readline()  # consume response
    time.sleep(0.3)

    baseline_spectrum = capture(handle, n_avg=10)
    freqs_arr = np.fft.rfftfreq(N_SAMPLES, d=1.0 / SAMPLE_RATE)
    baseline_noise = np.median(baseline_spectrum[10:])  # skip DC bins
    print("  Baseline noise floor: %.1f FFT units" % baseline_noise)

    # ─── Test each DDS at each frequency ───
    print("\n[5] Testing DDS modules...")
    print("-" * 60)

    results = {}
    for dds_ch in [1, 2]:
        results[dds_ch] = {'serial': [], 'analog': []}
        print("\n  ╔══ DDS #%d ══╗" % dds_ch)

        for freq in TEST_FREQS:
            # Send frequency command
            cmd = 'F%d:%d\n' % (dds_ch, freq)
            dds.reset_input_buffer()
            dds.write(cmd.encode())
            time.sleep(0.05)
            resp = dds.readline().decode('ascii', errors='replace').strip()

            # Check serial response
            serial_ok = ('DDS%d:%d' % (dds_ch, freq)) in resp or str(freq) in resp
            results[dds_ch]['serial'].append(serial_ok)

            # Wait for signal to stabilize
            time.sleep(0.3)

            # Measure at this frequency
            peak_freq, peak_mag, noise, snr = measure_at_freq(handle, freq)

            # Signal present if SNR > 3 (conservative threshold)
            analog_ok = snr > 3.0
            results[dds_ch]['analog'].append((analog_ok, snr, peak_mag, peak_freq))

            status = "ALIVE" if (serial_ok and analog_ok) else ("SERIAL-ONLY" if serial_ok else "DEAD")
            print("    %5d Hz │ serial: %s │ SNR: %5.1f× │ peak: %.0f Hz │ %s" %
                  (freq, "OK" if serial_ok else "NO", snr, peak_freq, status))

            # Silence this DDS before next test
            dds.write(('F%d:off\n' % dds_ch).encode())
            time.sleep(0.05)
            dds.readline()
            time.sleep(0.2)

    # ─── Summary ───
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for dds_ch in [1, 2]:
        serial_pass = sum(results[dds_ch]['serial'])
        analog_pass = sum(1 for ok, _, _, _ in results[dds_ch]['analog'] if ok)
        n = len(TEST_FREQS)

        if serial_pass == n and analog_pass == n:
            verdict = "FULLY ALIVE (serial + analog)"
        elif serial_pass == n and analog_pass > 0:
            verdict = "PARTIALLY ALIVE (serial OK, weak analog)"
        elif serial_pass == n:
            verdict = "SERIAL-ONLY (no analog output — module dead or sum network too lossy)"
        elif serial_pass > 0:
            verdict = "INTERMITTENT"
        else:
            verdict = "DEAD (no serial response)"

        avg_snr = np.mean([snr for _, snr, _, _ in results[dds_ch]['analog']])
        max_snr = max(snr for _, snr, _, _ in results[dds_ch]['analog'])

        print("\n  DDS #%d: %s" % (dds_ch, verdict))
        print("    Serial: %d/%d  │  Analog: %d/%d  │  Avg SNR: %.1f×  │  Max SNR: %.1f×" %
              (serial_pass, n, analog_pass, n, avg_snr, max_snr))

    # ─── Recommendation ───
    any_analog = any(
        ok for ch in [1, 2] for ok, _, _, _ in results[ch]['analog']
    )
    all_serial = all(
        all(results[ch]['serial']) for ch in [1, 2]
    )

    print("\n" + "-" * 60)
    print("RECOMMENDATION:")
    if any_analog and all_serial:
        print("  Both DDS respond and produce signal.")
        print("  → Swap 10kΩ sum resistors for 1kΩ to boost drive 10×")
        print("  → Expected: 670mVpp × (Zin/(1kΩ+Zin)) × 3.69 ≈ 1.85 Vpp at PZT")
    elif all_serial and not any_analog:
        print("  DDS modules accept commands but produce NO analog output.")
        print("  Possible causes:")
        print("    a) Module OUT pin dead (solder joint or IC failure)")
        print("    b) 10kΩ sum resistor attenuation below noise floor")
        print("  → Try: probe DDS OUT pin directly with scope (bypass sum network)")
        print("  → If still no signal: modules need replacement (~$5 each)")
    elif not all_serial:
        print("  Serial communication failed.")
        print("  → Check: ls /dev/cu.usbserial-* (is 11330 present?)")
        print("  → Check: Arduino 2 powered? USB connected?")
        print("  → Try: screen /dev/cu.usbserial-11330 115200, then type D?")

    # ─── Cleanup ───
    dds.write(b'Foff\n')
    time.sleep(0.05)
    dds.close()
    close_scope(handle)

    print("\nDone.")


if __name__ == "__main__":
    main()
