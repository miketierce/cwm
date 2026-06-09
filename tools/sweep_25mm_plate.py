"""
25mm Plate Mode Sweep — Multi-channel acquisition
==================================================
Sweeps F4 (GP5) from 50 kHz to 350 kHz, reading all 3 RX relay
channels (5=NW, 6=NE, 7=SE) at each frequency step.

Outputs:
  - CSV with columns: freq_hz, relay, magnitude_mV, phase_deg, pk_pk_mV
  - Summary of detected peaks with spatial analysis
  - Classification: ACOUSTIC (spatial variation) vs INTERFERENCE (uniform)

Usage:
    python tools/sweep_25mm_plate.py
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

FREQ_START = 50_000      # Hz
FREQ_STOP = 350_000      # Hz
FREQ_STEP = 2_000        # Hz (2 kHz steps → 151 points)

TIMEBASE = 7             # 1280 ns/sample → 781.25 kS/s
N_SAMPLES = 8064
SETTLE_MS = 30           # ms to wait after frequency change
RELAY_SETTLE_MS = 100    # ms to wait after relay switch

RELAY_CHANNELS = [(5, 'NW'), (6, 'NE'), (7, 'SE')]

# ─── Helpers ─────────────────────────────────────────────────────
def setup_picoscope():
    ps = ctypes.CDLL(PICO_LIB)
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"PicoScope open failed: {handle}")
    ps.ps2000_set_channel(handle, 0, 1, 1, 6)   # Ch A, DC, ±1V
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


def fft_magnitude_at(data_mv, target_freq, fs):
    """Return (peak_freq, peak_magnitude_mV, noise_floor_mV) near target."""
    window = np.hanning(len(data_mv))
    fft = np.fft.rfft(data_mv * window)
    freqs = np.fft.rfftfreq(len(data_mv), d=1.0/fs)
    mag = np.abs(fft) * 2.0 / (len(data_mv) * 0.5)  # hanning correction

    # Search ±5 bins around target
    target_idx = np.argmin(np.abs(freqs - target_freq))
    search = 5
    lo = max(0, target_idx - search)
    hi = min(len(mag), target_idx + search + 1)
    peak_idx = lo + np.argmax(mag[lo:hi])

    return freqs[peak_idx], mag[peak_idx]


def broadband_rms(data_mv):
    """RMS of signal (AC-coupled)."""
    dc = np.mean(data_mv)
    return np.sqrt(np.mean((data_mv - dc)**2))


# ─── Main ────────────────────────────────────────────────────────
def main():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = 'data/results/lab/25mm_plate'
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, f'sweep_{timestamp}.csv')
    json_path = os.path.join(outdir, f'sweep_{timestamp}_analysis.json')

    fs = 1e9 / 1280.0  # 781250 Hz

    freqs_hz = list(range(FREQ_START, FREQ_STOP + 1, FREQ_STEP))
    n_freqs = len(freqs_hz)
    print(f"25mm Plate Mode Sweep")
    print(f"  Range: {FREQ_START/1000:.0f} – {FREQ_STOP/1000:.0f} kHz, step {FREQ_STEP/1000:.0f} kHz")
    print(f"  Points: {n_freqs} × {len(RELAY_CHANNELS)} relays = {n_freqs * len(RELAY_CHANNELS)} acquisitions")
    print(f"  Est. time: {n_freqs * len(RELAY_CHANNELS) * 0.4 / 60:.1f} min")
    print(f"  Output: {csv_path}")
    print()

    # Setup hardware
    ps, handle = setup_picoscope()
    print(f"  PicoScope: handle={handle}")

    nco = serial.Serial(NCO_PORT, 115200, timeout=2)
    time.sleep(0.3)
    print(f"  NCO: {NCO_PORT}")

    mux = RelayMux(MUX_PORT)
    mux.open()
    print(f"  Relay mux: ready")
    print()

    # Storage: results[freq][relay_label] = magnitude_mV
    results = {}  # freq → {NW: mag, NE: mag, SE: mag}
    all_rows = []  # for CSV

    try:
        for i, freq in enumerate(freqs_hz):
            # Set NCO frequency
            nco.write(f'F4:{freq}\n'.encode())
            time.sleep(SETTLE_MS / 1000.0)
            # Drain response
            if nco.in_waiting:
                nco.read(nco.in_waiting)

            freq_data = {}
            for relay_ch, relay_label in RELAY_CHANNELS:
                mux.select(relay_ch)
                time.sleep(RELAY_SETTLE_MS / 1000.0)

                data_mv = acquire(ps, handle)
                if data_mv is None:
                    print(f"  TIMEOUT at {freq/1000:.0f} kHz relay {relay_label}")
                    freq_data[relay_label] = 0.0
                    all_rows.append((freq, relay_label, 0.0, 0.0))
                    continue

                _, peak_mag = fft_magnitude_at(data_mv, freq, fs)
                pk_pk = data_mv.max() - data_mv.min()
                freq_data[relay_label] = peak_mag
                all_rows.append((freq, relay_label, peak_mag, pk_pk))

            results[freq] = freq_data

            # Progress
            if (i + 1) % 10 == 0 or i == 0:
                nw = freq_data.get('NW', 0)
                ne = freq_data.get('NE', 0)
                se = freq_data.get('SE', 0)
                print(f"  [{i+1:3d}/{n_freqs}] {freq/1000:6.0f} kHz  NW={nw:.3f}  NE={ne:.3f}  SE={se:.3f} mV")

    finally:
        # Cleanup
        nco.write(b'Foff\n')
        time.sleep(0.1)
        nco.close()
        mux.off()
        mux.close()
        ps.ps2000_close_unit(handle)

    # ─── Save CSV ────────────────────────────────────────────────
    with open(csv_path, 'w') as f:
        f.write("freq_hz,relay,magnitude_mV,pk_pk_mV\n")
        for row in all_rows:
            f.write(f"{row[0]},{row[1]},{row[2]:.6f},{row[3]:.3f}\n")
    print(f"\n  CSV saved: {csv_path}")

    # ─── Analysis ────────────────────────────────────────────────
    print("\n=== MODE ANALYSIS ===\n")

    # Build arrays per relay
    freq_arr = np.array(freqs_hz)
    mag_nw = np.array([results[f].get('NW', 0) for f in freqs_hz])
    mag_ne = np.array([results[f].get('NE', 0) for f in freqs_hz])
    mag_se = np.array([results[f].get('SE', 0) for f in freqs_hz])

    # Find peaks (local maxima > 3× median noise)
    def find_peaks(mag, threshold_factor=3.0):
        noise = np.median(mag)
        threshold = noise * threshold_factor
        peaks = []
        for i in range(1, len(mag) - 1):
            if mag[i] > mag[i-1] and mag[i] > mag[i+1] and mag[i] > threshold:
                peaks.append(i)
        return peaks, noise

    peaks_nw, noise_nw = find_peaks(mag_nw)
    peaks_ne, noise_ne = find_peaks(mag_ne)
    peaks_se, noise_se = find_peaks(mag_se)

    print(f"  Noise floors: NW={noise_nw:.4f} mV  NE={noise_ne:.4f} mV  SE={noise_se:.4f} mV")
    print(f"  Peaks found:  NW={len(peaks_nw)}  NE={len(peaks_ne)}  SE={len(peaks_se)}")
    print()

    # Union of all peak frequencies (merge within ±1 step)
    all_peak_freqs = set()
    for idx_list in [peaks_nw, peaks_ne, peaks_se]:
        for idx in idx_list:
            all_peak_freqs.add(freq_arr[idx])

    # Merge nearby peaks
    merged = sorted(all_peak_freqs)
    final_peaks = []
    skip = set()
    for i, f in enumerate(merged):
        if f in skip:
            continue
        cluster = [f]
        for j in range(i+1, len(merged)):
            if merged[j] - f <= FREQ_STEP * 1.5:
                cluster.append(merged[j])
                skip.add(merged[j])
            else:
                break
        final_peaks.append(int(np.mean(cluster)))

    print(f"  Merged peak frequencies: {len(final_peaks)}")
    print()

    # Classify each peak
    classifications = []
    print(f"  {'Freq (kHz)':>10}  {'NW (mV)':>8}  {'NE (mV)':>8}  {'SE (mV)':>8}  {'Ratio':>6}  {'Class':>12}")
    print(f"  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*6}  {'─'*12}")

    for fp in final_peaks:
        # Get magnitude at this freq (or nearest)
        idx = np.argmin(np.abs(freq_arr - fp))
        nw_mag = mag_nw[idx]
        ne_mag = mag_ne[idx]
        se_mag = mag_se[idx]

        mags = [nw_mag, ne_mag, se_mag]
        max_mag = max(mags)
        min_mag = min(mags) if min(mags) > 0 else 0.001

        # Spatial variation ratio: max/min
        ratio = max_mag / min_mag

        # Classification logic:
        # - Acoustic modes: spatial variation (ratio > 2) due to mode shape
        # - Interference: uniform across all receivers (ratio < 1.5)
        # - Ambiguous: ratio 1.5–2.0
        if ratio > 2.0:
            classification = "ACOUSTIC"
        elif ratio < 1.5:
            classification = "INTERFERENCE"
        else:
            classification = "AMBIGUOUS"

        # Additional check: if all magnitudes are very low, it's noise
        avg_mag = np.mean(mags)
        overall_noise = np.mean([noise_nw, noise_ne, noise_se])
        if avg_mag < overall_noise * 2:
            classification = "NOISE"

        classifications.append({
            'freq_kHz': fp / 1000,
            'NW_mV': round(nw_mag, 4),
            'NE_mV': round(ne_mag, 4),
            'SE_mV': round(se_mag, 4),
            'ratio': round(ratio, 2),
            'classification': classification
        })

        marker = "◄" if classification == "ACOUSTIC" else ""
        print(f"  {fp/1000:10.0f}  {nw_mag:8.4f}  {ne_mag:8.4f}  {se_mag:8.4f}  {ratio:6.2f}  {classification:>12} {marker}")

    # Save analysis
    analysis = {
        'timestamp': timestamp,
        'config': {
            'freq_start': FREQ_START,
            'freq_stop': FREQ_STOP,
            'freq_step': FREQ_STEP,
            'timebase': TIMEBASE,
            'n_samples': N_SAMPLES,
            'sample_rate_hz': fs,
        },
        'noise_floors_mV': {
            'NW': round(noise_nw, 6),
            'NE': round(noise_ne, 6),
            'SE': round(noise_se, 6),
        },
        'peaks': classifications,
        'acoustic_modes': [p for p in classifications if p['classification'] == 'ACOUSTIC'],
        'interference_peaks': [p for p in classifications if p['classification'] == 'INTERFERENCE'],
    }

    with open(json_path, 'w') as f:
        json.dump(analysis, f, indent=2)

    # Summary
    n_acoustic = len(analysis['acoustic_modes'])
    n_interf = len(analysis['interference_peaks'])
    print(f"\n  ─── SUMMARY ───")
    print(f"  Acoustic modes:    {n_acoustic}")
    print(f"  Interference:      {n_interf}")
    print(f"  Ambiguous/noise:   {len(classifications) - n_acoustic - n_interf}")
    print(f"\n  Analysis saved: {json_path}")

    if n_acoustic > 0:
        print(f"\n  ★ Best acoustic modes for experiments:")
        sorted_modes = sorted(analysis['acoustic_modes'], key=lambda x: max(x['NW_mV'], x['NE_mV'], x['SE_mV']), reverse=True)
        for m in sorted_modes[:5]:
            print(f"    {m['freq_kHz']:.0f} kHz — max {max(m['NW_mV'], m['NE_mV'], m['SE_mV']):.3f} mV, ratio {m['ratio']:.1f}×")


if __name__ == '__main__':
    main()
