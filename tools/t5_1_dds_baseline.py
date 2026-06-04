#!/usr/bin/env python3
"""T5.1 — DDS Dual-Mode SNR Baseline.

Measures SNR of each DDS channel individually and simultaneously at all
confirmed plate eigenmodes. Gates T5.2–T5.5 experiments.

Pass criterion: Both DDS channels > 3× SNR at plate eigenmodes.
"""

import ctypes as ct
import numpy as np
import serial
import time
import json
import os
from datetime import datetime

os.environ['DYLD_LIBRARY_PATH'] = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
ps = ct.CDLL('/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib')

NSAMPLES = 8064
TIMEBASE = 7  # 1280 ns/sample -> 781 kHz
BIN_HZ = 781250.0 / NSAMPLES  # ~96.9 Hz/bin

# Confirmed plate eigenmodes
MODES = [35840, 54920, 57037, 97011]


def main():
    ps.ps2000_open_unit.restype = ct.c_int16
    h = ps.ps2000_open_unit()
    print(f'Handle: {h}')
    if h < 1:
        print('SCOPE FAILED')
        return

    # AC coupled, +/-5V
    ps.ps2000_set_channel(h, 0, 1, 0, 7)
    ps.ps2000_set_channel(h, 1, 0, 0, 7)

    # Mux relay 8 (RX PZT NE)
    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=2)
    time.sleep(0.5)
    mux.reset_input_buffer()
    mux.write(b'relay on 8\r\n')
    time.sleep(0.3)
    print(f'Mux: {mux.readline().decode().strip()}')

    # DDS controller
    dds = serial.Serial('/dev/cu.usbserial-1120', 115200, timeout=2)
    time.sleep(2.5)
    dds.reset_input_buffer()

    buf = (ct.c_int16 * NSAMPLES)()
    ov = ct.c_int16()

    def capture_spectrum(navg=10):
        specs = []
        for _ in range(navg):
            ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
            ticks = ct.c_int32()
            ps.ps2000_run_block(h, NSAMPLES, TIMEBASE, 1, ct.byref(ticks))
            time.sleep(0.005)
            for i in range(400):
                if ps.ps2000_ready(h):
                    break
                time.sleep(0.005)
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

    def dds_cmd(cmd):
        dds.write(f'{cmd}\n'.encode())
        time.sleep(0.1)
        dds.reset_input_buffer()

    print()
    print('=' * 60)
    print('T5.1 - DDS Dual-Mode SNR Baseline')
    print('=' * 60)

    # Ensure AWG is off (we're testing DDS only)
    ps.ps2000_set_sig_gen_built_in(h, 0, 0, 0,
                                    ct.c_float(1000.0), ct.c_float(1000.0),
                                    ct.c_float(0.0), ct.c_float(0.0), 0, 0)

    # 1) Baseline noise
    print()
    print('[1] Baseline (DDS off, 10 avg)...')
    dds_cmd('Foff')
    time.sleep(0.5)
    sp_base = capture_spectrum(10)
    noise = np.median(sp_base[10:])
    print(f'    Noise floor: {noise:.0f}')

    results = {
        'timestamp': datetime.now().isoformat(),
        'noise_floor': noise,
        'modes': MODES,
        'dds1_single': {},
        'dds2_single': {},
        'dds1_dds2_simultaneous': {},
    }

    # 2) DDS1 alone at each mode
    print()
    print('[2] DDS1 alone at each eigenmode...')
    print(f'    {"Freq":>8} {"Peak":>8} {"SNR":>6} {"Pass":>5}')
    for freq in MODES:
        dds_cmd('Foff')
        time.sleep(0.2)
        dds_cmd(f'F1:{freq}')
        time.sleep(0.5)
        sp = capture_spectrum(10)
        pk = peak_at(sp, freq)
        snr = pk / noise
        passed = bool(snr > 3.0)
        print(f'    {freq:>8} {pk:>8.0f} {snr:>6.1f}x {"PASS" if passed else "FAIL":>5}')
        results['dds1_single'][str(freq)] = {'peak': float(pk), 'snr': float(snr), 'pass': passed}

    # 3) DDS2 alone at each mode
    print()
    print('[3] DDS2 alone at each eigenmode...')
    print(f'    {"Freq":>8} {"Peak":>8} {"SNR":>6} {"Pass":>5}')
    for freq in MODES:
        dds_cmd('Foff')
        time.sleep(0.2)
        dds_cmd(f'F2:{freq}')
        time.sleep(0.5)
        sp = capture_spectrum(10)
        pk = peak_at(sp, freq)
        snr = pk / noise
        passed = bool(snr > 3.0)
        print(f'    {freq:>8} {pk:>8.0f} {snr:>6.1f}x {"PASS" if passed else "FAIL":>5}')
        results['dds2_single'][str(freq)] = {'peak': float(pk), 'snr': float(snr), 'pass': passed}

    # 4) Simultaneous dual-mode (best pairs for CHSH)
    print()
    print('[4] Simultaneous dual-mode (DDS1 + DDS2)...')
    pairs = [
        (35840, 97011),
        (54920, 97011),
        (35840, 54920),
    ]
    print(f'    {"DDS1":>8} {"DDS2":>8} {"SNR1":>6} {"SNR2":>6} {"Both>3x":>8}')
    for f1, f2 in pairs:
        dds_cmd('Foff')
        time.sleep(0.2)
        dds_cmd(f'F1:{f1}')
        dds_cmd(f'F2:{f2}')
        time.sleep(0.5)
        sp = capture_spectrum(10)
        pk1 = peak_at(sp, f1)
        pk2 = peak_at(sp, f2)
        snr1 = pk1 / noise
        snr2 = pk2 / noise
        both_pass = bool(snr1 > 3.0 and snr2 > 3.0)
        print(f'    {f1:>8} {f2:>8} {snr1:>6.1f}x {snr2:>6.1f}x {"PASS" if both_pass else "FAIL":>8}')
        results['dds1_dds2_simultaneous'][f'{f1}+{f2}'] = {
            'snr_f1': float(snr1), 'snr_f2': float(snr2), 'both_pass': both_pass
        }

    # 5) Summary
    print()
    print('=' * 60)
    print('SUMMARY')
    print('=' * 60)

    dds1_pass = all(v['pass'] for v in results['dds1_single'].values())
    dds2_pass = all(v['pass'] for v in results['dds2_single'].values())
    any_pair_pass = any(v['both_pass'] for v in results['dds1_dds2_simultaneous'].values())

    best_dds1 = max(results['dds1_single'].items(), key=lambda x: x[1]['snr'])
    best_dds2 = max(results['dds2_single'].items(), key=lambda x: x[1]['snr'])

    print(f'  DDS1 best: {best_dds1[0]} Hz @ {best_dds1[1]["snr"]:.1f}x')
    print(f'  DDS2 best: {best_dds2[0]} Hz @ {best_dds2[1]["snr"]:.1f}x')
    print(f'  DDS1 all modes > 3x: {"YES" if dds1_pass else "NO"}')
    print(f'  DDS2 all modes > 3x: {"YES" if dds2_pass else "NO"}')
    print(f'  Any dual-mode pair > 3x both: {"YES" if any_pair_pass else "NO"}')
    print()

    gate = any_pair_pass
    results['gate_decision'] = 'PASS' if gate else 'FAIL'

    if gate:
        # Find best pair
        best_pair = max(results['dds1_dds2_simultaneous'].items(),
                       key=lambda x: min(x[1]['snr_f1'], x[1]['snr_f2']))
        print(f'  GATE: PASS - proceed to T5.2 (CHSH)')
        print(f'  Recommended mode pair: {best_pair[0]}')
        print(f'    (min SNR in pair: {min(best_pair[1]["snr_f1"], best_pair[1]["snr_f2"]):.1f}x)')
        results['recommended_pair'] = best_pair[0]
    else:
        print('  GATE: FAIL - DDS SNR insufficient for T5.2-T5.5')
        print('  Need: bypass 10k attenuator or route DDS through Board D')

    # Save results
    os.makedirs('data/results/quantum_bridge', exist_ok=True)
    outpath = f'data/results/quantum_bridge/t5_1_dds_baseline_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(outpath, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved: {outpath}')

    # Cleanup
    dds_cmd('Foff')
    ps.ps2000_stop(h)
    ps.ps2000_close_unit(ct.c_int16(h))
    mux.write(b'relay off 8\r\n')
    time.sleep(0.1)
    mux.close()
    dds.close()
    print('\nDone.')


if __name__ == '__main__':
    main()
