#!/usr/bin/env python3
"""Frequency Sweep — map plate mode spectrum.

Sweeps a frequency range, measuring received amplitude at each step to identify
plate resonances beyond the 4 known modes (35840, 54920, 57037, 97011 Hz).

Drive sources:
  --awg           Use PicoScope built-in sig gen (default, strongest signal)
  --dds           Use AD9833 DDS module instead

Usage:
    python tools/dds_freq_sweep.py --awg --start-hz 30000 --stop-hz 120000
    python tools/dds_freq_sweep.py --dds --channel 2 --start-hz 90000 --stop-hz 100000

Options:
    --start-hz      Start frequency (default: 30000)
    --stop-hz       Stop frequency (default: 120000)
    --step-hz       Frequency step (default: 200)
    --dwell-ms      Settle time per frequency (default: 200)
    --navg          Captures to average per frequency (default: 8)
    --amplitude-uv  AWG peak-to-peak amplitude in µV (default: 500000 = 0.5Vpp)
    --dds-port      DDS Arduino serial port
    --mux-port      Relay mux serial port
    --channel       DDS channel: 1 or 2 (default: 2)
    --output        Output JSON path
"""

import os
import sys
import ctypes as ct
import numpy as np
import time
import json
import argparse
from datetime import datetime

os.environ['DYLD_LIBRARY_PATH'] = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
from picosdk.ps2000 import ps2000 as ps
import serial


def parse_args():
    p = argparse.ArgumentParser(description="Frequency sweep (AWG or DDS)")
    # Drive source
    drive = p.add_mutually_exclusive_group()
    drive.add_argument('--awg', action='store_true', default=True,
                       help='Use PicoScope built-in sig gen (default)')
    drive.add_argument('--dds', action='store_true',
                       help='Use AD9833 DDS module')
    # Sweep params
    p.add_argument('--start-hz', type=float, default=30000)
    p.add_argument('--stop-hz', type=float, default=120000)
    p.add_argument('--step-hz', type=float, default=200)
    p.add_argument('--dwell-ms', type=float, default=200)
    p.add_argument('--navg', type=int, default=8)
    p.add_argument('--amplitude-uv', type=int, default=500000,
                   help='AWG pk-pk amplitude in µV (default 500000=0.5Vpp)')
    # Hardware
    p.add_argument('--dds-port', default='/dev/cu.usbserial-1120')
    p.add_argument('--mux-port', default='/dev/cu.usbserial-11310')
    p.add_argument('--channel', type=int, default=2, choices=[1, 2])
    p.add_argument('--output', default=None)
    args = p.parse_args()
    # If --dds is set, --awg becomes False
    if args.dds:
        args.awg = False
    return args


N_SAMPLES = 8064
TIMEBASE = 7  # 1.28 µs/sample → 781 kHz sample rate
SAMPLE_INTERVAL = 1.28e-6


def open_scope():
    h = ps.ps2000_open_unit()
    if h < 1:
        print(f"ERROR: PicoScope open failed (handle={h})")
        sys.exit(1)
    time.sleep(0.5)
    ps.ps2000_set_channel(h, 0, 1, 0, 7)  # ChA enabled, AC coupling, ±5V
    ps.ps2000_set_channel(h, 1, 0, 0, 7)  # ChB disabled
    return h


def capture_spectrum(h, navg=5):
    """Capture and return averaged FFT magnitude spectrum."""
    specs = []
    for _ in range(navg):
        buf = (ct.c_int16 * N_SAMPLES)()
        ov = ct.c_int16(0)
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)  # no trigger, auto-fill
        ps.ps2000_run_block(h, N_SAMPLES, TIMEBASE, 1, ct.byref(ct.c_int32()))
        time.sleep(0.015)
        for _ in range(200):
            if ps.ps2000_ready(h):
                break
            time.sleep(0.005)
        ps.ps2000_get_values(h, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES, 0)
        d = np.array(buf[:], dtype=float)
        d -= d.mean()
        specs.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES))))
    return np.mean(specs, axis=0)


def main():
    args = parse_args()

    freqs_fft = np.fft.rfftfreq(N_SAMPLES, d=SAMPLE_INTERVAL)
    freq_resolution = freqs_fft[1] - freqs_fft[0]  # ~97 Hz per bin

    # Generate sweep frequencies
    sweep_freqs = np.arange(args.start_hz, args.stop_hz + args.step_hz, args.step_hz)
    n_steps = len(sweep_freqs)
    drive_name = "AWG" if args.awg else f"DDS#{args.channel}"
    print(f"Frequency Sweep: {args.start_hz/1e3:.1f}–{args.stop_hz/1e3:.1f} kHz, "
          f"{args.step_hz} Hz steps, {n_steps} points")
    print(f"Drive: {drive_name}, {args.navg} averages, {args.dwell_ms} ms dwell")
    if args.awg:
        print(f"AWG amplitude: {args.amplitude_uv/1e6:.3f} Vpp")
    print(f"FFT resolution: {freq_resolution:.1f} Hz/bin")
    print()

    # Open hardware
    h = open_scope()
    print(f"PicoScope: handle={h}")

    mux = serial.Serial(args.mux_port, 9600, timeout=1)
    time.sleep(2.5)
    mux.reset_input_buffer()
    mux.write(b'8\n')
    time.sleep(0.1)
    mux_resp = mux.readline().decode().strip()
    print(f"Mux: {mux_resp}")

    dds = None
    if not args.awg:
        dds = serial.Serial(args.dds_port, 115200, timeout=2)
        time.sleep(2.5)
        dds.reset_input_buffer()
        print(f"DDS: connected on {args.dds_port}")

    # Baseline (nothing driving)
    spec_baseline = capture_spectrum(h, args.navg)
    noise_floor = np.median(spec_baseline[10:])
    print(f"Baseline noise floor: {noise_floor:.0f}")
    print()

    # Sweep
    results = []
    cmd_prefix = f"F{args.channel}:" if dds else None
    t_start = time.time()

    print(f"{'Freq (Hz)':>10} {'Peak Mag':>10} {'SNR':>6} {'Peak Bin Hz':>12} {'Bar'}")
    print("-" * 60)

    for i, freq in enumerate(sweep_freqs):
        # Set drive frequency
        if args.awg:
            ps.ps2000_set_sig_gen_built_in(
                h, 0, args.amplitude_uv, 0,  # offset=0, pk2pk, waveform=sine
                float(freq), float(freq),     # start_freq = stop_freq (fixed)
                0, 0, 0, 0)                   # no sweep
        else:
            cmd = f"{cmd_prefix}{int(freq)}\n".encode()
            dds.write(cmd)
            time.sleep(0.02)
            dds.reset_input_buffer()

        # Dwell
        time.sleep(args.dwell_ms / 1000.0)

        # Capture
        spec = capture_spectrum(h, args.navg)

        # Find peak near the driven frequency (±5 bins)
        idx_center = np.argmin(np.abs(freqs_fft - freq))
        search_lo = max(5, idx_center - 5)
        search_hi = min(len(spec) - 1, idx_center + 5)
        peak_mag = np.max(spec[search_lo:search_hi + 1])
        peak_idx = search_lo + np.argmax(spec[search_lo:search_hi + 1])
        peak_freq = freqs_fft[peak_idx]

        snr = peak_mag / noise_floor if noise_floor > 0 else 0
        results.append({
            'freq_hz': float(freq),
            'peak_mag': float(peak_mag),
            'peak_freq_hz': float(peak_freq),
            'snr': float(snr),
        })

        # Print every 10th step or if SNR > 3
        bar = '#' * min(50, int(snr))
        if snr > 3.0 or i % 20 == 0:
            print(f"{freq:>10.0f} {peak_mag:>10.0f} {snr:>6.1f} {peak_freq:>12.1f} {bar}")

        # Progress
        if i > 0 and i % 100 == 0:
            elapsed = time.time() - t_start
            eta = elapsed / i * (n_steps - i)
            print(f"  ... {i}/{n_steps} ({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)")

    # Turn off drive
    if args.awg:
        ps.ps2000_set_sig_gen_built_in(h, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    elif dds:
        dds.write(b'Foff\n')
        time.sleep(0.1)

    elapsed_total = time.time() - t_start
    print(f"\nSweep complete: {n_steps} points in {elapsed_total:.1f}s")

    # Find peaks (modes)
    snrs = np.array([r['snr'] for r in results])
    freqs_swept = np.array([r['freq_hz'] for r in results])

    # Peak detection: SNR > 3 and local maximum (higher than neighbors)
    modes = []
    for i in range(2, len(snrs) - 2):
        if snrs[i] > 3.0 and snrs[i] >= snrs[i-1] and snrs[i] >= snrs[i+1]:
            if snrs[i] >= snrs[i-2] and snrs[i] >= snrs[i+2]:
                modes.append({
                    'freq_hz': float(freqs_swept[i]),
                    'snr': float(snrs[i]),
                    'peak_mag': float(results[i]['peak_mag']),
                })

    # Merge modes within 500 Hz (keep strongest)
    merged = []
    for m in modes:
        if merged and abs(m['freq_hz'] - merged[-1]['freq_hz']) < 500:
            if m['snr'] > merged[-1]['snr']:
                merged[-1] = m
        else:
            merged.append(m)

    print(f"\nDetected {len(merged)} modes (SNR > 3×):")
    print(f"{'#':>3} {'Freq (Hz)':>10} {'SNR':>6}")
    print("-" * 25)
    for i, m in enumerate(merged):
        print(f"{i+1:>3} {m['freq_hz']:>10.0f} {m['snr']:>6.1f}")

    # Save results
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'params': {
            'start_hz': args.start_hz,
            'stop_hz': args.stop_hz,
            'step_hz': args.step_hz,
            'dwell_ms': args.dwell_ms,
            'navg': args.navg,
            'drive': 'awg' if args.awg else f'dds{args.channel}',
            'amplitude_uv': args.amplitude_uv if args.awg else None,
        },
        'noise_floor': float(noise_floor),
        'sweep': results,
        'modes_detected': merged,
        'n_modes': len(merged),
        'elapsed_s': elapsed_total,
    }

    if args.output is None:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        outdir = 'data/results/dds_sweep'
        os.makedirs(outdir, exist_ok=True)
        args.output = f'{outdir}/sweep_{ts}.json'

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)
    print(f"\nResults saved: {args.output}")

    # Cleanup
    ps.ps2000_stop(h)
    ps.ps2000_close_unit(h)
    if dds:
        dds.close()
    mux.close()


if __name__ == '__main__':
    main()
