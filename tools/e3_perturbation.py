"""
E3 Perturbation Experiment — 25mm Plate
========================================
Fine sweep around known mode frequencies, measure peak f₀ and amplitude.
Run once per putty configuration (bare, position A, B, C, bare-again).

Drive: F4 (GP5, pin 7) → 25mm plate SW TX (short wire)
Read:  Relay 5 = 25mm NW RX, Relay 6 = 25mm NE RX

Usage:
    python tools/e3_perturbation.py [label]
    
    label = bare | A | B | C | bare2 (default: bare)
"""

import ctypes
import time
import serial
import numpy as np
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from relay_mux import RelayMux

# ─── Configuration ───────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
NCO_PORT = '/dev/cu.usbmodem113301'
MUX_PORT = '/dev/cu.usbserial-11310'

# Known 25mm plate modes from bare baseline (Jun 5, short wire)
TARGET_MODES = [56_000, 86_000, 91_000, 232_000, 321_000]

# Fine sweep params
FINE_HALFWIDTH = 3_000   # ±3 kHz around each mode
FINE_STEP = 50           # 50 Hz steps (finer than Q-factor script for precision)
N_AVG = 8               # averages per frequency point

# Hardware
TIMEBASE = 7             # 1280 ns/sample → 781.25 kS/s
N_SAMPLES = 8064
SETTLE_MS = 50
RELAY_SETTLE_MS = 100

NCO_CMD = 'F4'  # Drive via channel 4 (GP5 → 25mm plate SW TX)

RELAY_CHANNELS = [
    (5, '25mm NW'),
    (6, '25mm NE'),
]

# ─── Helpers ─────────────────────────────────────────────────────
def setup_picoscope():
    ps = ctypes.CDLL(PICO_LIB)
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"PicoScope open failed: {handle}")
    ps.ps2000_set_channel(handle, 0, 1, 1, 6)   # Ch A on, DC, ±1V
    ps.ps2000_set_channel(handle, 1, 0, 1, 6)   # Ch B off
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0) # no trigger
    return ps, handle


def acquire(ps, handle):
    """Capture one block, return array in mV."""
    t_ms = ctypes.c_int32()
    ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
    count = 0
    while not ps.ps2000_ready(handle):
        time.sleep(0.003)
        count += 1
        if count > 600:
            return None
    buf = (ctypes.c_int16 * N_SAMPLES)()
    overflow = ctypes.c_int16()
    ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                         ctypes.byref(overflow), N_SAMPLES)
    data = np.array(buf, dtype=np.float64)
    return data * 1000.0 / 32767.0  # mV (±1V range)


def acquire_averaged(ps, handle, n_avg):
    """Acquire n_avg blocks and return mean."""
    acc = None
    for _ in range(n_avg):
        d = acquire(ps, handle)
        if d is None:
            continue
        if acc is None:
            acc = d.copy()
        else:
            acc += d
    if acc is None:
        return None
    return acc / n_avg


def fft_magnitude_at(data_mv, target_freq, fs):
    """Return peak magnitude near target frequency."""
    window = np.hanning(len(data_mv))
    fft = np.fft.rfft(data_mv * window)
    freqs = np.fft.rfftfreq(len(data_mv), d=1.0/fs)
    mag = np.abs(fft) * 2.0 / (len(data_mv) * 0.5)

    target_idx = np.argmin(np.abs(freqs - target_freq))
    search = 5
    lo = max(0, target_idx - search)
    hi = min(len(mag), target_idx + search + 1)
    peak_idx = lo + np.argmax(mag[lo:hi])
    return freqs[peak_idx], mag[peak_idx]


def set_freq(nco, freq):
    """Set NCO frequency."""
    nco.write(f'{NCO_CMD}:{freq}\n'.encode())
    time.sleep(SETTLE_MS / 1000.0)
    if nco.in_waiting:
        nco.read(nco.in_waiting)


def measure_mode(ps, handle, nco, center_freq, fs):
    """Fine sweep around center_freq, return dict with f0, Q, peak_mV, bw."""
    start = int(center_freq - FINE_HALFWIDTH)
    stop = int(center_freq + FINE_HALFWIDTH)
    fine_freqs = list(range(start, stop + 1, FINE_STEP))

    magnitudes = []
    for freq in fine_freqs:
        set_freq(nco, freq)
        data = acquire_averaged(ps, handle, N_AVG)
        if data is None:
            magnitudes.append(0.0)
            continue
        _, mag = fft_magnitude_at(data, freq, fs)
        magnitudes.append(mag)

    mag_arr = np.array(magnitudes)
    freq_arr = np.array(fine_freqs, dtype=np.float64)

    # Find peak
    peak_idx = int(np.argmax(mag_arr))
    peak_mag = float(mag_arr[peak_idx])
    f0 = float(freq_arr[peak_idx])

    # -3dB bandwidth
    half_power = peak_mag / np.sqrt(2)
    above = mag_arr >= half_power

    Q = None
    bw = None
    status = 'ok'

    if not np.any(above) or peak_mag < 0.5:
        status = 'no_peak'
    else:
        # Left crossing
        left_idx = peak_idx
        while left_idx > 0 and mag_arr[left_idx] >= half_power:
            left_idx -= 1
        # Right crossing
        right_idx = peak_idx
        while right_idx < len(mag_arr) - 1 and mag_arr[right_idx] >= half_power:
            right_idx += 1

        if left_idx == 0 and mag_arr[0] >= half_power:
            status = 'too_wide'
        elif right_idx == len(mag_arr) - 1 and mag_arr[-1] >= half_power:
            status = 'too_wide'
        else:
            # Interpolate
            f_left = freq_arr[left_idx] + (half_power - mag_arr[left_idx]) / \
                     max(mag_arr[left_idx + 1] - mag_arr[left_idx], 0.001) * FINE_STEP
            f_right = freq_arr[right_idx - 1] + (mag_arr[right_idx - 1] - half_power) / \
                      max(mag_arr[right_idx - 1] - mag_arr[right_idx], 0.001) * FINE_STEP
            bw = float(f_right - f_left)
            if bw > 0:
                Q = int(f0 / bw)
            else:
                status = 'bw_error'

    return {
        'target_hz': int(center_freq),
        'f0_hz': f0,
        'Q': Q,
        'bw_hz': bw,
        'peak_mV': round(peak_mag, 3),
        'status': status,
        'sweep': {'freqs': [int(f) for f in fine_freqs],
                  'mags': [round(m, 4) for m in magnitudes]},
    }


# ─── Main ────────────────────────────────────────────────────────
def main():
    label = sys.argv[1] if len(sys.argv) > 1 else 'bare'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = 'data/results/lab/25mm_plate/e3'
    os.makedirs(outdir, exist_ok=True)

    fs = 1e9 / 1280.0  # 781250 Hz

    print("=" * 60)
    print(f"E3 Perturbation — 25mm Plate — Config: {label.upper()}")
    print("=" * 60)
    print(f"  Drive: {NCO_CMD} (GP5 → 25mm plate SW TX)")
    print(f"  Relays: 5=NW, 6=NE")
    print(f"  Modes: {[f'{f/1000:.0f} kHz' for f in TARGET_MODES]}")
    print(f"  Fine sweep: ±{FINE_HALFWIDTH/1000:.0f} kHz, {FINE_STEP} Hz, {N_AVG}-avg")
    print()

    # Open hardware
    print("Opening PicoScope...", end=' ', flush=True)
    ps, handle = setup_picoscope()
    print("OK")

    print("Opening NCO...", end=' ', flush=True)
    nco = serial.Serial(NCO_PORT, 115200, timeout=1)
    time.sleep(0.5)
    if nco.in_waiting:
        nco.read(nco.in_waiting)
    print("OK")

    print("Opening relay mux...", end=' ', flush=True)
    mux = RelayMux(MUX_PORT)
    mux.open()
    print("OK")
    print()

    results = []

    for relay_num, channel_name in RELAY_CHANNELS:
        print(f"─── Channel: {channel_name} (relay {relay_num}) ───")
        mux.select(relay_num)
        time.sleep(RELAY_SETTLE_MS / 1000.0)

        for mode_freq in TARGET_MODES:
            print(f"  {mode_freq/1000:.0f} kHz ... ", end='', flush=True)
            result = measure_mode(ps, handle, nco, mode_freq, fs)
            result['channel'] = channel_name

            if result['status'] == 'ok':
                print(f"f₀={result['f0_hz']:,.0f} Hz  Q={result['Q']}  "
                      f"BW={result['bw_hz']:.0f} Hz  Amp={result['peak_mV']:.2f} mV")
            else:
                print(f"f₀={result['f0_hz']:,.0f} Hz  Amp={result['peak_mV']:.2f} mV  "
                      f"[{result['status']}]")

            results.append(result)

        print()

    # Turn off NCO
    nco.write(b'Foff\n')
    time.sleep(0.1)

    # Save results
    output = {
        'timestamp': timestamp,
        'experiment': 'E3_perturbation',
        'label': label,
        'plate': '25mm fused silica',
        'drive': f'{NCO_CMD} (GP5, pin 7, short wire)',
        'config': {
            'fine_halfwidth_hz': FINE_HALFWIDTH,
            'fine_step_hz': FINE_STEP,
            'n_avg': N_AVG,
            'timebase': TIMEBASE,
            'n_samples': N_SAMPLES,
        },
        'results': results,
    }

    outfile = os.path.join(outdir, f'e3_{label}_{timestamp}.json')
    with open(outfile, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Saved: {outfile}")
    print()

    # Summary table
    print(f"{'Mode':>8} {'Channel':>8} {'f₀ (Hz)':>10} {'Q':>5} {'BW':>8} {'Amp mV':>7} {'Status':>9}")
    print("─" * 62)
    for r in results:
        q_str = str(r['Q']) if r['Q'] else '—'
        bw_str = f"{r['bw_hz']:.0f}" if r['bw_hz'] else '—'
        print(f"{r['target_hz']:>8,} {r['channel']:>8} {r['f0_hz']:>10,.0f} "
              f"{q_str:>5} {bw_str:>8} {r['peak_mV']:>7.2f} {r['status']:>9}")

    # Cleanup
    ps.ps2000_close_unit(handle)
    nco.close()
    mux.close()
    print("\nDone — hardware closed.")


if __name__ == '__main__':
    main()
