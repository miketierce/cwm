#!/usr/bin/env python3
"""
E10: Q-Factor & Temporal Memory — Frequency-Domain Measurement

Measures Q factor (and hence decay time τ) for each resonant mode using
the frequency-domain bandwidth method:
  Q = f_center / Δf_3dB
  τ = Q / (π × f_center) = 1 / (π × Δf_3dB)

This avoids the timing problem of ringdown capture (serial latency > τ).
Instead we sweep the drive frequency in fine steps around each resonance
and measure the -3dB bandwidth directly.

Also calculates temporal memory capacity: τ × n_modes gives the total
information-time product.

Protocol:
  1. For each enrolled mode:
     a. Coarse: confirm peak at enrolled frequency
     b. Fine sweep: ±5% around peak in 20 Hz steps
     c. Find -3dB points → bandwidth → Q → τ
  2. Report per-mode and aggregate temporal capacity

Hardware: NCO (F1:freq), relay mux, PicoScope 2204A
"""
import ctypes as ct
import numpy as np
import serial
import time
import json
from datetime import datetime
from pathlib import Path


# ─── Hardware Constants ───────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N = 3968
TIMEBASE = 7
RNG = 6
RNG_MV = 2000
FS = 781250.0
NFFT = N * 4
BIN_HZ = FS / NFFT

RELAY_RX = 1  # Plate I NW
NAVG = 16
FINE_STEP_HZ = 20  # Fine sweep resolution
SWEEP_HALF_PCT = 3.0  # ±3% around resonance


def setup_hardware():
    ps = ct.CDLL(PICO_LIB)
    for h in range(1, 5):
        ps.ps2000_close_unit(ct.c_int16(h))
    time.sleep(0.3)

    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"PicoScope open failed: handle={handle}")
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)

    ser = serial.Serial('/dev/cu.usbmodem113301', 115200, timeout=2)
    time.sleep(0.5)
    ser.reset_input_buffer()

    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=2,
                        dsrdtr=False, rtscts=False)
    mux.dtr = False
    time.sleep(2.5)
    mux.reset_input_buffer()

    return ps, handle, ser, mux


def nco(ser, cmd):
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()


def set_relay(mux, r):
    mux.reset_input_buffer()
    mux.write(f'{r}\r\n'.encode())
    time.sleep(0.35)
    mux.read(mux.in_waiting)


def capture_spectrum(ps, handle, navg=NAVG):
    buf = (ct.c_int16 * N)()
    ov = ct.c_int16()
    mags = []
    for _ in range(navg):
        ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(handle, N, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(handle):
                break
            time.sleep(0.002)
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None,
                             ct.byref(ov), N, 0)
        d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
        d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d * np.hanning(N), n=NFFT)))
    return np.mean(mags, axis=0)


def peak_amplitude(spectrum, freq_hz, window_bins=5):
    b = int(round(freq_hz / BIN_HZ))
    return float(spectrum[max(0, b - window_bins):b + window_bins + 1].max())


def measure_at_freq(ps, handle, ser, freq_hz, navg=NAVG):
    """Drive at freq, measure response amplitude at that freq."""
    nco(ser, f'F1:{int(round(freq_hz))}')
    time.sleep(0.15)  # Let mode respond (ring-up time < Q/f cycles)
    spec = capture_spectrum(ps, handle, navg=navg)
    return peak_amplitude(spec, freq_hz)


def find_3db_bandwidth(freqs_swept, amplitudes):
    """
    Find -3dB bandwidth from a frequency sweep.
    Returns: (f_center, bw_3db, peak_amp, f_low, f_high)
    """
    peak_idx = np.argmax(amplitudes)
    peak_amp = amplitudes[peak_idx]
    f_center = freqs_swept[peak_idx]
    threshold = peak_amp / np.sqrt(2)  # -3dB

    # Find lower -3dB point
    f_low = None
    for i in range(peak_idx, -1, -1):
        if amplitudes[i] < threshold:
            # Interpolate
            if i < peak_idx:
                frac = (threshold - amplitudes[i]) / (amplitudes[i + 1] - amplitudes[i])
                f_low = freqs_swept[i] + frac * (freqs_swept[i + 1] - freqs_swept[i])
            break

    # Find upper -3dB point
    f_high = None
    for i in range(peak_idx, len(amplitudes)):
        if amplitudes[i] < threshold:
            if i > peak_idx:
                frac = (threshold - amplitudes[i]) / (amplitudes[i - 1] - amplitudes[i])
                f_high = freqs_swept[i] - frac * (freqs_swept[i] - freqs_swept[i - 1])
            break

    if f_low is None or f_high is None:
        # Couldn't find both -3dB points (peak too broad or too narrow)
        # Estimate from half-power width using interpolation
        half_power = amplitudes > threshold
        if np.any(half_power):
            hp_indices = np.where(half_power)[0]
            f_low = f_low or freqs_swept[hp_indices[0]]
            f_high = f_high or freqs_swept[hp_indices[-1]]

    if f_low is not None and f_high is not None:
        bw = f_high - f_low
    else:
        bw = 0

    return f_center, bw, peak_amp, f_low, f_high


def main():
    print("=" * 70)
    print("  E10: Q-Factor & Temporal Memory (Frequency-Domain Method)")
    print("=" * 70)
    print()
    print(f"  Method: Fine frequency sweep around each resonance")
    print(f"  Resolution: {FINE_STEP_HZ} Hz steps, ±{SWEEP_HALF_PCT}% window")
    print(f"  Q = f_center / bandwidth_3dB")
    print(f"  τ = Q / (π × f_center) = 1 / (π × Δf_3dB)")
    print()

    # Load enrolled modes
    h_path = Path('data/results/h_matrix/multi_plate_enrollment_20260603_171950.json')
    with open(h_path) as f:
        enrollment = json.load(f)
    all_freqs = enrollment['mode_frequencies_hz']

    # Select 10 modes spread across range
    if len(all_freqs) > 10:
        indices = np.linspace(0, len(all_freqs) - 1, 10, dtype=int)
        test_freqs = [all_freqs[i] for i in indices]
    else:
        test_freqs = all_freqs

    print(f"  Testing {len(test_freqs)} modes: {test_freqs[0]/1000:.1f}–{test_freqs[-1]/1000:.1f} kHz")
    print()

    ps, handle, ser, mux = setup_hardware()
    set_relay(mux, RELAY_RX)
    time.sleep(0.3)
    nco(ser, 'Foff')
    time.sleep(0.3)

    results = {}

    for mode_idx, freq in enumerate(test_freqs):
        freq_int = int(round(freq))
        print(f"  [{mode_idx+1}/{len(test_freqs)}] Mode: {freq_int} Hz ({freq/1000:.1f} kHz)")

        # Fine sweep around this mode
        half_span = freq * SWEEP_HALF_PCT / 100
        sweep_start = freq - half_span
        sweep_end = freq + half_span
        n_points = int((sweep_end - sweep_start) / FINE_STEP_HZ) + 1
        sweep_freqs = np.linspace(sweep_start, sweep_end, n_points)

        amplitudes = np.zeros(n_points)
        for i, f in enumerate(sweep_freqs):
            amplitudes[i] = measure_at_freq(ps, handle, ser, f, navg=8)

        # Find Q
        f_center, bw_3db, peak_amp, f_low, f_high = find_3db_bandwidth(
            sweep_freqs, amplitudes)

        if bw_3db > 0:
            Q = f_center / bw_3db
            tau = Q / (np.pi * f_center)  # = 1/(π × bw_3db)

            print(f"    Peak: {peak_amp:.0f} mV at {f_center:.0f} Hz")
            print(f"    -3dB: [{f_low:.0f}, {f_high:.0f}] Hz → BW = {bw_3db:.0f} Hz")
            print(f"    Q = {Q:.0f}")
            print(f"    τ = {tau*1000:.3f} ms")
        else:
            Q = 0
            tau = 0
            print(f"    ✗ Could not determine -3dB bandwidth")
            print(f"      (peak={peak_amp:.0f} mV, sweep may be too narrow)")

        results[str(freq_int)] = {
            'frequency_hz': float(freq),
            'peak_frequency_hz': float(f_center),
            'peak_amplitude_mV': float(peak_amp),
            'bandwidth_3dB_hz': float(bw_3db),
            'f_low_hz': float(f_low) if f_low else None,
            'f_high_hz': float(f_high) if f_high else None,
            'Q': float(Q),
            'tau_s': float(tau),
            'tau_ms': float(tau * 1000),
            'n_sweep_points': n_points,
        }
        print()

    # ── Cleanup ───────────────────────────────────────────────────
    nco(ser, 'Foff')

    # ── Summary ───────────────────────────────────────────────────
    print("=" * 70)
    print("  E10 RESULTS: Q-FACTOR & TEMPORAL MEMORY")
    print("=" * 70)
    print()

    valid_results = {k: v for k, v in results.items() if v['Q'] > 0}

    if valid_results:
        all_Qs = [v['Q'] for v in valid_results.values()]
        all_taus = [v['tau_s'] for v in valid_results.values()]
        all_bws = [v['bandwidth_3dB_hz'] for v in valid_results.values()]

        print(f"  Modes measured:    {len(valid_results)}/{len(results)}")
        print(f"  Q range:           {min(all_Qs):.0f} – {max(all_Qs):.0f}")
        print(f"  Q mean:            {np.mean(all_Qs):.0f} ± {np.std(all_Qs):.0f}")
        print(f"  τ range:           {min(all_taus)*1000:.3f} – {max(all_taus)*1000:.3f} ms")
        print(f"  τ mean:            {np.mean(all_taus)*1000:.3f} ± {np.std(all_taus)*1000:.3f} ms")
        print(f"  Bandwidth range:   {min(all_bws):.0f} – {max(all_bws):.0f} Hz")
        print()

        # Temporal memory capacity
        total_mode_ms = sum(v['tau_ms'] for v in valid_results.values())
        print(f"  Total temporal capacity: {total_mode_ms:.2f} mode·ms")
        print(f"  (= {len(valid_results)} modes × {np.mean(all_taus)*1000:.3f} ms avg)")
        print()

        # Memory depth at different step rates
        for step_rate_hz in [100, 1000, 10000]:
            step_period_ms = 1000 / step_rate_hz
            depth = np.mean(all_taus) * 1000 / step_period_ms
            print(f"  At {step_rate_hz} Hz step rate: memory depth = {depth:.1f} steps")
        print()

        if np.mean(all_Qs) > 500:
            verdict = "PASS"
            print(f"  ★ PASS — Q={np.mean(all_Qs):.0f}, τ={np.mean(all_taus)*1000:.2f} ms")
        elif np.mean(all_Qs) > 100:
            verdict = "PASS_MARGINAL"
            print(f"  △ PASS (marginal) — Q={np.mean(all_Qs):.0f}")
        else:
            verdict = "FAIL"
            print(f"  ✗ FAIL — Q too low ({np.mean(all_Qs):.0f})")
    else:
        verdict = "FAIL"
        total_mode_ms = 0
        all_Qs = [0]
        all_taus = [0]
        print("  ✗ FAIL — No valid Q measurements")

    print()

    # ── Save ──────────────────────────────────────────────────────
    DATA_DIR = Path('data/results/temporal')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = DATA_DIR / f'e10_qfactor_memory_{ts}.json'

    output = {
        'experiment': 'E10_qfactor_temporal_memory',
        'timestamp': datetime.now().isoformat(),
        'method': 'frequency_domain_bandwidth',
        'config': {
            'fine_step_hz': FINE_STEP_HZ,
            'sweep_half_pct': SWEEP_HALF_PCT,
            'n_avg': NAVG,
            'relay_rx': RELAY_RX,
        },
        'summary': {
            'n_modes_tested': len(results),
            'n_modes_valid': len(valid_results),
            'Q_mean': float(np.mean(all_Qs)),
            'Q_std': float(np.std(all_Qs)),
            'tau_mean_ms': float(np.mean(all_taus) * 1000),
            'tau_std_ms': float(np.std(all_taus) * 1000),
            'total_temporal_capacity_mode_ms': float(total_mode_ms),
        },
        'per_mode': results,
        'verdict': verdict,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {out_path}")

    # Cleanup
    ser.close()
    mux.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))
    print("  Done.")


if __name__ == '__main__':
    main()
