#!/usr/bin/env python3
"""T4.1 — Post-Separation Acoustic Fraction Measurement.

Measures steady-state signal at 35,840 Hz, then stops AWG and captures
ringdown to quantify the acoustic fraction after Board D/A separation.

Previous measurement (May 26): 12% acoustic, 88% electrical.
"""

import ctypes as ct
import numpy as np
import serial
import time
import os

os.environ['DYLD_LIBRARY_PATH'] = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
ps = ct.CDLL('/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib')

NSAMPLES = 8064
TIMEBASE = 7  # 1280 ns/sample -> 781 kHz sample rate
BIN_HZ = 781250.0 / NSAMPLES  # ~96.9 Hz/bin
TARGET_FREQ = 35840


def main():
    ps.ps2000_open_unit.restype = ct.c_int16
    h = ps.ps2000_open_unit()
    print(f'Handle: {h}')
    if h < 1:
        print('SCOPE FAILED')
        return

    # AC coupled, +/-5V range
    ps.ps2000_set_channel(h, 0, 1, 0, 7)
    ps.ps2000_set_channel(h, 1, 0, 0, 7)

    # Mux to relay 8 (RX PZT NE)
    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=2)
    time.sleep(0.5)
    mux.reset_input_buffer()
    mux.write(b'relay on 8\r\n')
    time.sleep(0.3)
    resp = mux.readline().decode().strip()
    print(f'Mux: {resp}')

    buf = (ct.c_int16 * NSAMPLES)()
    ov = ct.c_int16()

    def capture_spectrum(navg=1):
        specs = []
        for _ in range(navg):
            ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)  # auto trigger
            ticks = ct.c_int32()
            ps.ps2000_run_block(h, NSAMPLES, TIMEBASE, 1, ct.byref(ticks))
            time.sleep(0.002)
            for i in range(500):
                if ps.ps2000_ready(h):
                    break
                time.sleep(0.001)
            ps.ps2000_get_values(h, ct.byref(buf), None, None, None,
                                 ct.byref(ov), NSAMPLES, 0)
            d = np.array(buf[:], dtype=float)
            d -= d.mean()
            sp = np.abs(np.fft.rfft(d * np.hanning(NSAMPLES)))
            specs.append(sp)
        return np.mean(specs, axis=0)

    def peak_at(sp, freq, window=5):
        b = int(freq / BIN_HZ)
        return float(np.max(sp[max(0, b - window):b + window]))

    print()
    print('=' * 60)
    print('T4.1 - Post-Separation Acoustic Fraction Measurement')
    print('=' * 60)

    # 1) Baseline (AWG off)
    print()
    print('[1] Baseline (AWG off, 10 avg)...')
    ps.ps2000_set_sig_gen_built_in(h, 0, 0, 0,
                                    ct.c_float(1000.0), ct.c_float(1000.0),
                                    ct.c_float(0.0), ct.c_float(0.0), 0, 0)
    time.sleep(0.5)
    sp_base = capture_spectrum(10)
    noise = np.median(sp_base[10:])
    peak_base = peak_at(sp_base, TARGET_FREQ)
    print(f'    Noise floor: {noise:.0f}')
    print(f'    35840 Hz peak (should be ~noise): {peak_base:.0f} ({peak_base/noise:.1f}x)')

    # 2) Steady state (AWG on at 35840 Hz, 0.5 Vpp)
    print()
    print('[2] Steady state: AWG @ 35840 Hz, 500 mVpp (10 avg)...')
    ps.ps2000_set_sig_gen_built_in(h, 0, 500000, 0,
                                    ct.c_float(35840.0), ct.c_float(35840.0),
                                    ct.c_float(0.0), ct.c_float(0.0), 0, 0)
    time.sleep(1.0)  # let plate ring up
    sp_on = capture_spectrum(10)
    peak_on = peak_at(sp_on, TARGET_FREQ)
    print(f'    35840 Hz peak (during drive): {peak_on:.0f} ({peak_on/noise:.1f}x SNR)')

    # 3) Stop AWG and capture IMMEDIATELY (ringdown sequence)
    print()
    print('[3] Ringdown: stopping AWG, capturing as fast as possible...')
    ps.ps2000_set_sig_gen_built_in(h, 0, 0, 0,
                                    ct.c_float(1000.0), ct.c_float(1000.0),
                                    ct.c_float(0.0), ct.c_float(0.0), 0, 0)
    # Capture sequence: each block is ~10.3 ms of data
    ringdown_peaks = []
    ringdown_times = []
    t0 = time.time()
    for i in range(8):
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(h, NSAMPLES, TIMEBASE, 1, ct.byref(ticks))
        for j in range(500):
            if ps.ps2000_ready(h):
                break
            time.sleep(0.001)
        t_capture = time.time() - t0
        ps.ps2000_get_values(h, ct.byref(buf), None, None, None,
                             ct.byref(ov), NSAMPLES, 0)
        d = np.array(buf[:], dtype=float)
        d -= d.mean()
        sp = np.abs(np.fft.rfft(d * np.hanning(NSAMPLES)))
        pk = peak_at(sp, TARGET_FREQ)
        ringdown_peaks.append(pk)
        ringdown_times.append(t_capture * 1000)  # ms

    header = f'    {"Capture":>8} {"Time(ms)":>10} {"Peak":>8} {"Fraction":>10} {"SNR":>6}'
    print(header)
    for i, (t, pk) in enumerate(zip(ringdown_times, ringdown_peaks)):
        frac = pk / peak_on * 100
        snr = pk / noise
        print(f'    {i+1:>8} {t:>10.1f} {pk:>8.0f} {frac:>9.1f}% {snr:>6.1f}x')

    # 4) Summary
    print()
    print('=' * 60)
    print('SUMMARY')
    print('=' * 60)
    first_ringdown = ringdown_peaks[0]
    acoustic_frac = first_ringdown / peak_on * 100
    print(f'  Steady-state peak:     {peak_on:.0f} ({peak_on/noise:.0f}x noise)')
    print(f'  First ringdown peak:   {first_ringdown:.0f} ({first_ringdown/noise:.1f}x noise)')
    print(f'  Acoustic fraction:     {acoustic_frac:.1f}%')
    print(f'  (Previous measurement: 12%)')
    print()
    if acoustic_frac > 40:
        print('  >>> GOOD - temporal memory tests (T4.2/T4.3) should be feasible')
    elif acoustic_frac > 20:
        print('  >>> IMPROVED - ringdown may be visible but NARMA-10 still marginal')
    elif acoustic_frac > 5:
        print('  >>> MODEST improvement - some coupling paths remain')
    else:
        print('  >>> NO CHANGE - dominant coupling path not addressed')

    # Check if we can see exponential decay
    if len(ringdown_peaks) >= 4 and ringdown_peaks[0] > 2 * noise:
        valid = [(t, pk) for t, pk in zip(ringdown_times, ringdown_peaks)
                 if pk > noise * 1.5]
        if len(valid) >= 3:
            ts = np.array([v[0] for v in valid])
            pks = np.array([v[1] for v in valid])
            log_pks = np.log(pks)
            coeffs = np.polyfit(ts, log_pks, 1)
            tau_ms = -1.0 / coeffs[0]
            print(f'  Decay time constant:   tau = {tau_ms:.1f} ms (expected ~24.5 ms from Q=2759)')
        else:
            print('  (Not enough above-noise points to fit decay)')

    ps.ps2000_stop(h)
    ps.ps2000_close_unit(ct.c_int16(h))
    mux.write(b'relay off 8\r\n')
    time.sleep(0.1)
    mux.close()
    print()
    print('Done.')


if __name__ == '__main__':
    main()
