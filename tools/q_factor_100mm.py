"""
100mm Plate Q-Factor Measurement — Plates I and H
==================================================
Phase 1: Coarse sweep (30–120 kHz, 1 kHz steps) on relays 1-4
Phase 2: Fine sweep (±3 kHz, 100 Hz steps) around strongest modes
Phase 3: Calculate Q = f_center / BW_-3dB

Drive: F1 (GP2) → Plate I SW TX
Read:  Relay 1 = Plate I NW, Relay 2 = Plate I NE
       Relay 3 = Plate H NW, Relay 4 = Plate H NE

Usage:
    python tools/q_factor_100mm.py
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

# Phase 1: Coarse sweep
FREQ_START = 30_000
FREQ_STOP = 120_000
FREQ_STEP = 1_000

# Phase 2: Fine sweep params
FINE_HALFWIDTH = 3_000   # ±3 kHz around each mode
FINE_STEP = 100          # 100 Hz steps

# Hardware
TIMEBASE = 7             # 1280 ns/sample → 781.25 kS/s (Nyquist 391 kHz)
N_SAMPLES = 8064
SETTLE_MS = 50           # ms after frequency change (longer for high-Q modes)
RELAY_SETTLE_MS = 100    # ms after relay switch

RELAY_CHANNELS = [
    (1, 'Plate I NW'),
    (2, 'Plate I NE'),
    (3, 'Plate H NW'),
    (4, 'Plate H NE'),
]

# Peak detection
NOISE_THRESHOLD_FACTOR = 5.0  # mode must be >5× median to count
TOP_N_MODES = 8               # measure Q on top N modes per plate

NCO_CMD = 'F1'  # Drive via channel 1 (GP2 → Plate I SW TX)

# ─── Helpers ─────────────────────────────────────────────────────
def setup_picoscope():
    ps = ctypes.CDLL(PICO_LIB)
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"PicoScope open failed: {handle}")
    ps.ps2000_set_channel(handle, 0, 1, 1, 6)   # Ch A on, DC, ±1V
    ps.ps2000_set_channel(handle, 1, 0, 1, 6)   # Ch B off
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0) # no trigger, free-run
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


def fft_magnitude_at(data_mv, target_freq, fs):
    """Return peak magnitude near target frequency."""
    window = np.hanning(len(data_mv))
    fft = np.fft.rfft(data_mv * window)
    freqs = np.fft.rfftfreq(len(data_mv), d=1.0/fs)
    mag = np.abs(fft) * 2.0 / (len(data_mv) * 0.5)  # hanning correction

    target_idx = np.argmin(np.abs(freqs - target_freq))
    search = 5
    lo = max(0, target_idx - search)
    hi = min(len(mag), target_idx + search + 1)
    peak_idx = lo + np.argmax(mag[lo:hi])
    return freqs[peak_idx], mag[peak_idx]


def set_freq(nco, freq):
    """Set NCO frequency via F1 command."""
    nco.write(f'{NCO_CMD}:{freq}\n'.encode())
    time.sleep(SETTLE_MS / 1000.0)
    if nco.in_waiting:
        nco.read(nco.in_waiting)


def find_peaks(freq_arr, mag_arr, threshold_factor=5.0, min_sep_hz=2000):
    """Find peaks using prominence (height above local minima on both sides).
    A peak must be >2× the average of its nearest local minima, OR
    >threshold_factor × global median (whichever is less restrictive)."""
    median = np.median(mag_arr)

    peaks = []
    for i in range(1, len(mag_arr) - 1):
        if mag_arr[i] > mag_arr[i-1] and mag_arr[i] > mag_arr[i+1]:
            # Find local minima on left and right (within ±5 steps)
            left_min = min(mag_arr[max(0, i-5):i])
            right_min = min(mag_arr[i+1:min(len(mag_arr), i+6)])
            local_floor = (left_min + right_min) / 2
            prominence = mag_arr[i] / max(local_floor, 0.01)

            # Accept if prominence > 2× local floor OR > threshold × global median
            if prominence > 2.0 or mag_arr[i] > median * threshold_factor:
                peaks.append((freq_arr[i], mag_arr[i], prominence))

    # Remove peaks too close together (keep stronger one)
    if not peaks:
        return [(f, m) for f, m, _ in peaks]
    peaks.sort(key=lambda x: x[2], reverse=True)  # sort by prominence
    filtered = []
    for freq, mag, prom in peaks:
        if all(abs(freq - f) >= min_sep_hz for f, _, _ in filtered):
            filtered.append((freq, mag, prom))
    filtered.sort(key=lambda x: x[0])
    return [(f, m) for f, m, _ in filtered]


def measure_q(ps, handle, nco, mux, relay_ch, center_freq, fs):
    """Fine sweep around center_freq, return (f0, Q, bw, peak_mag) or None."""
    start = int(center_freq - FINE_HALFWIDTH)
    stop = int(center_freq + FINE_HALFWIDTH)
    fine_freqs = list(range(start, stop + 1, FINE_STEP))

    magnitudes = []
    for freq in fine_freqs:
        set_freq(nco, freq)
        data = acquire(ps, handle)
        if data is None:
            magnitudes.append(0.0)
            continue
        _, mag = fft_magnitude_at(data, freq, fs)
        magnitudes.append(mag)

    mag_arr = np.array(magnitudes)
    freq_arr = np.array(fine_freqs, dtype=np.float64)

    # Find peak
    peak_idx = np.argmax(mag_arr)
    peak_mag = mag_arr[peak_idx]
    f0 = freq_arr[peak_idx]

    # -3dB level
    half_power = peak_mag / np.sqrt(2)

    # Find -3dB crossings
    above = mag_arr >= half_power
    if not np.any(above):
        return None

    # Left crossing
    left_idx = peak_idx
    while left_idx > 0 and mag_arr[left_idx] >= half_power:
        left_idx -= 1
    if left_idx == 0 and mag_arr[0] >= half_power:
        return None  # didn't cross on left (peak too wide for window)

    # Interpolate left
    if left_idx < peak_idx:
        f_left = freq_arr[left_idx] + (half_power - mag_arr[left_idx]) / \
                 (mag_arr[left_idx + 1] - mag_arr[left_idx]) * FINE_STEP
    else:
        f_left = freq_arr[0]

    # Right crossing
    right_idx = peak_idx
    while right_idx < len(mag_arr) - 1 and mag_arr[right_idx] >= half_power:
        right_idx += 1
    if right_idx == len(mag_arr) - 1 and mag_arr[-1] >= half_power:
        return None  # didn't cross on right

    # Interpolate right
    if right_idx > peak_idx:
        f_right = freq_arr[right_idx - 1] + (mag_arr[right_idx - 1] - half_power) / \
                  (mag_arr[right_idx - 1] - mag_arr[right_idx]) * FINE_STEP
    else:
        f_right = freq_arr[-1]

    bw = f_right - f_left
    if bw <= 0:
        return None

    Q = f0 / bw
    return f0, Q, bw, peak_mag


# ─── Main ────────────────────────────────────────────────────────
def main():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = 'data/results/lab/100mm_plates'
    os.makedirs(outdir, exist_ok=True)

    fs = 1e9 / 1280.0  # 781250 Hz

    coarse_freqs = list(range(FREQ_START, FREQ_STOP + 1, FREQ_STEP))
    n_freqs = len(coarse_freqs)

    print("=" * 60)
    print("100mm Plate Q-Factor Measurement — Plates I & H")
    print("=" * 60)
    print(f"  Drive: {NCO_CMD} (GP2 → Plate I SW TX)")
    print(f"  Relays: 1=I-NW, 2=I-NE, 3=H-NW, 4=H-NE")
    print(f"  Coarse: {FREQ_START/1000:.0f}–{FREQ_STOP/1000:.0f} kHz, {FREQ_STEP/1000:.0f} kHz steps ({n_freqs} pts)")
    print(f"  Fine: ±{FINE_HALFWIDTH/1000:.0f} kHz, {FINE_STEP} Hz steps")
    print(f"  Est. time: {n_freqs * len(RELAY_CHANNELS) * 0.25 / 60:.1f} min (coarse) + Q sweeps")
    print()

    # Setup hardware
    ps, handle = setup_picoscope()
    print(f"  PicoScope: handle={handle}")

    nco = serial.Serial(NCO_PORT, 115200, timeout=2)
    time.sleep(0.3)
    nco.write(b'Foff\n')
    time.sleep(0.1)
    if nco.in_waiting:
        nco.read(nco.in_waiting)
    print(f"  NCO: {NCO_PORT}")

    mux = RelayMux(MUX_PORT)
    mux.open()
    print(f"  Relay mux: ready")
    print()

    # ─── Phase 1: Coarse Sweep ─────────────────────────────────────
    print("PHASE 1: Coarse Mode Census")
    print("-" * 40)

    coarse_data = {}  # relay_label → list of (freq, mag)
    for relay_ch, relay_label in RELAY_CHANNELS:
        mux.select(relay_ch)
        time.sleep(RELAY_SETTLE_MS / 1000.0)

        mags = []
        for i, freq in enumerate(coarse_freqs):
            set_freq(nco, freq)
            data = acquire(ps, handle)
            if data is None:
                mags.append(0.0)
                continue
            _, mag = fft_magnitude_at(data, freq, fs)
            mags.append(mag)

        coarse_data[relay_label] = mags

        # Find peaks for this channel
        peaks = find_peaks(np.array(coarse_freqs), np.array(mags),
                          threshold_factor=NOISE_THRESHOLD_FACTOR)
        median_mag = np.median(mags)
        max_mag = max(mags)
        print(f"  {relay_label}: {len(peaks)} modes, median={median_mag:.2f} mV, max={max_mag:.2f} mV")
        for f, m in peaks[:5]:
            print(f"    {f/1000:.0f} kHz: {m:.2f} mV ({m/median_mag:.0f}× noise)")

    print()

    # ─── Decide if Plate H has signal ──────────────────────────────
    # Check if Plate H channels show ANY peaks (not just raw amplitude)
    plate_h_nw_peaks = find_peaks(np.array(coarse_freqs), np.array(coarse_data['Plate H NW']),
                                   threshold_factor=NOISE_THRESHOLD_FACTOR)
    plate_h_ne_peaks = find_peaks(np.array(coarse_freqs), np.array(coarse_data['Plate H NE']),
                                   threshold_factor=NOISE_THRESHOLD_FACTOR)
    plate_i_max = max(max(coarse_data['Plate I NW']), max(coarse_data['Plate I NE']))
    plate_h_max = max(max(coarse_data['Plate H NW']), max(coarse_data['Plate H NE']))

    if len(plate_h_nw_peaks) == 0 and len(plate_h_ne_peaks) == 0:
        print("WARNING: Plate H shows NO modes above threshold.")
        print("         Cascade wiring may be needed to drive Plate H.")
        print("         Proceeding with Plate I only.")
        active_relays = [(1, 'Plate I NW'), (2, 'Plate I NE')]
    else:
        print(f"  Plate I max: {plate_i_max:.2f} mV | Plate H max: {plate_h_max:.2f} mV")
        active_relays = RELAY_CHANNELS

    # ─── Phase 2: Select Top Modes Per Plate ────────────────────────
    print()
    print("PHASE 2: Selecting modes for Q measurement")
    print("-" * 40)

    # Combine channels per plate, pick strongest modes
    plate_modes = {}  # plate_name → [(freq, mag, relay_label)]

    for relay_ch, relay_label in active_relays:
        plate_name = 'Plate I' if 'I' in relay_label else 'Plate H'
        if plate_name not in plate_modes:
            plate_modes[plate_name] = []

        peaks = find_peaks(np.array(coarse_freqs), np.array(coarse_data[relay_label]),
                          threshold_factor=NOISE_THRESHOLD_FACTOR, min_sep_hz=2000)
        for f, m in peaks:
            plate_modes[plate_name].append((f, m, relay_label, relay_ch))

    # For each plate, pick top N unique frequencies
    q_targets = []  # (freq, relay_ch, relay_label, plate_name, coarse_mag)

    for plate_name, modes in plate_modes.items():
        # Sort by magnitude, deduplicate by frequency
        modes.sort(key=lambda x: x[1], reverse=True)
        seen_freqs = set()
        count = 0
        for freq, mag, label, ch in modes:
            if count >= TOP_N_MODES:
                break
            if all(abs(freq - f) >= 2000 for f in seen_freqs):
                q_targets.append((freq, ch, label, plate_name, mag))
                seen_freqs.add(freq)
                count += 1
        print(f"  {plate_name}: {count} modes selected for Q measurement")

    q_targets.sort(key=lambda x: x[0])
    print(f"  Total Q measurements: {len(q_targets)}")
    print()

    # ─── Phase 3: Fine Sweep Q Measurement ─────────────────────────
    print("PHASE 3: Q-Factor Fine Sweeps")
    print("-" * 40)

    q_results = []

    for freq, relay_ch, relay_label, plate_name, coarse_mag in q_targets:
        mux.select(relay_ch)
        time.sleep(RELAY_SETTLE_MS / 1000.0)

        result = measure_q(ps, handle, nco, mux, relay_ch, freq, fs)

        if result is None:
            print(f"  {freq/1000:.0f} kHz ({relay_label}): FAILED (peak too wide or not found)")
            q_results.append({
                'target_freq': freq,
                'relay': relay_ch,
                'channel': relay_label,
                'plate': plate_name,
                'status': 'failed'
            })
        else:
            f0, Q, bw, peak_mag = result
            print(f"  {freq/1000:.0f} kHz ({relay_label}): f₀={f0:.0f} Hz, Q={Q:.0f}, BW={bw:.0f} Hz, peak={peak_mag:.2f} mV")
            q_results.append({
                'target_freq': freq,
                'f0_hz': f0,
                'Q': round(Q),
                'bw_hz': round(bw, 1),
                'peak_mag_mV': round(peak_mag, 3),
                'relay': relay_ch,
                'channel': relay_label,
                'plate': plate_name,
                'status': 'ok'
            })

    # ─── Cleanup ───────────────────────────────────────────────────
    nco.write(b'Foff\n')
    nco.close()
    ps.ps2000_close_unit(handle)

    # ─── Summary ───────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    ok_results = [r for r in q_results if r['status'] == 'ok']

    if ok_results:
        # Group by plate
        for plate_name in sorted(set(r['plate'] for r in ok_results)):
            plate_q = [r for r in ok_results if r['plate'] == plate_name]
            plate_q.sort(key=lambda r: r['f0_hz'])

            print(f"\n  {plate_name}:")
            print(f"  {'Freq':>8} | {'Channel':>12} | {'Q':>6} | {'BW (Hz)':>8} | {'Peak mV':>8}")
            print(f"  {'-'*8}-+-{'-'*12}-+-{'-'*6}-+-{'-'*8}-+-{'-'*8}")

            qs = []
            for r in plate_q:
                print(f"  {r['f0_hz']/1000:7.2f}k | {r['channel']:>12} | {r['Q']:6d} | {r['bw_hz']:8.1f} | {r['peak_mag_mV']:8.3f}")
                qs.append(r['Q'])

            print(f"  → Median Q = {int(np.median(qs))}, Max Q = {max(qs)}, Min Q = {min(qs)}")
    else:
        print("  No successful Q measurements!")

    # ─── Save ──────────────────────────────────────────────────────
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'q_factor_100mm_plates',
        'config': {
            'drive': NCO_CMD,
            'coarse_range': [FREQ_START, FREQ_STOP, FREQ_STEP],
            'fine_halfwidth': FINE_HALFWIDTH,
            'fine_step': FINE_STEP,
            'timebase': TIMEBASE,
            'n_samples': N_SAMPLES,
        },
        'coarse_sweep': {label: list(map(float, mags))
                        for label, mags in coarse_data.items()},
        'coarse_freqs': coarse_freqs,
        'q_results': q_results,
    }

    json_path = os.path.join(outdir, f'q_factor_{timestamp}.json')
    with open(json_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n  Saved: {json_path}")


if __name__ == '__main__':
    main()
