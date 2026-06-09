#!/usr/bin/env python3
"""
E9: Phase Cancellation — Electronic Write/Erase via DDS Interference

Tests whether two DDS channels driving the SAME frequency with a phase
offset can cancel (erase) a mode's response. If destructive interference
works, we have electronic write/erase without physical mass changes.

Physics: If DDS1 drives at freq f with phase 0, and DDS2 drives at the
same freq f with phase 180°, the plate sees zero net excitation at f.
The mode amplitude should drop to noise floor.

Protocol:
  1. For each of 5 test modes:
     a. Drive F1 only → measure "write" amplitude
     b. Drive F1 + F2 at same freq, sweep PHASE 0→360°
     c. Find phase giving minimum amplitude (best erase)
     d. Verify: erase depth relative to write amplitude
  2. Demonstrate write→erase→write cycle

Hardware: NCO (dual AD9833), relay mux, PicoScope 2204A
Commands: F1:freq, F2:freq, PHASE:deg, Foff
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

# Test modes (strong, well-separated from enrollment)
TEST_MODES = [35840, 54920, 70000, 85000, 97011]
RELAY_RX = 1  # Plate I NW (strongest signal)
PHASE_STEPS = 36  # 10° resolution
NAVG = 24  # Averaging passes


def setup_hardware():
    """Open PicoScope, NCO serial, relay mux."""
    ps = ct.CDLL(PICO_LIB)
    # Close any stale handles
    for h in range(1, 5):
        ps.ps2000_close_unit(ct.c_int16(h))
    time.sleep(0.3)

    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"PicoScope open failed: handle={handle}")
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)  # Ch A, DC, ±2V

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
    """Send command to NCO, return response."""
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()


def set_relay(mux, r):
    """Set relay mux channel."""
    mux.reset_input_buffer()
    mux.write(f'{r}\r\n'.encode())
    time.sleep(0.35)
    mux.read(mux.in_waiting)


def capture_spectrum(ps, handle, navg=NAVG):
    """Capture magnitude spectrum (averaged)."""
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
    """Get peak magnitude near target frequency."""
    b = int(round(freq_hz / BIN_HZ))
    return float(spectrum[max(0, b - window_bins):b + window_bins + 1].max())


def main():
    print("=" * 70)
    print("  E9: Phase Cancellation — Electronic Write/Erase")
    print("=" * 70)
    print()
    print(f"  DDS: dual AD9833, shared clock 126 MHz")
    print(f"  Protocol: F1 writes, F2 at same freq with PHASE offset erases")
    print(f"  Phase sweep: {PHASE_STEPS} steps (0° to 350°, {360/PHASE_STEPS:.0f}° resolution)")
    print(f"  Test modes: {len(TEST_MODES)} frequencies")
    print(f"  Receiver: relay {RELAY_RX} (Plate I NW)")
    print()

    ps, handle, ser, mux = setup_hardware()
    set_relay(mux, RELAY_RX)
    time.sleep(0.3)

    # Noise floor
    nco(ser, 'Foff')
    time.sleep(0.5)
    noise_spec = capture_spectrum(ps, handle)

    results = {}

    for mode_idx, freq in enumerate(TEST_MODES):
        print(f"\n  [{mode_idx+1}/{len(TEST_MODES)}] Mode: {freq} Hz")
        print(f"  {'─' * 50}")

        noise_amp = peak_amplitude(noise_spec, freq)

        # ── Step 1: F1 solo (WRITE) ──
        nco(ser, 'Foff')
        time.sleep(0.2)
        nco(ser, f'F1:{freq}')
        time.sleep(0.5)  # Let mode ring up
        write_spec = capture_spectrum(ps, handle)
        write_amp = peak_amplitude(write_spec, freq)
        snr = write_amp / noise_amp if noise_amp > 0 else 0

        print(f"    Write (F1 only):  {write_amp:.0f} mV  (SNR: {snr:.0f}×)")

        # ── Step 2: F2 solo at same freq ──
        nco(ser, 'Foff')
        time.sleep(0.2)
        nco(ser, f'F2:{freq}')
        nco(ser, 'PHASE:0')
        time.sleep(0.5)
        f2_spec = capture_spectrum(ps, handle)
        f2_amp = peak_amplitude(f2_spec, freq)
        print(f"    F2 solo:          {f2_amp:.0f} mV  (ratio to F1: {f2_amp/write_amp:.2f})")

        # ── Step 3: Both DDS, sweep phase ──
        print(f"    Sweeping phase (F1+F2 at {freq} Hz)...")
        nco(ser, 'Foff')
        time.sleep(0.2)
        nco(ser, f'F1:{freq}')
        nco(ser, f'F2:{freq}')
        time.sleep(0.3)

        phase_degrees = np.linspace(0, 360, PHASE_STEPS, endpoint=False)
        amplitudes = np.zeros(PHASE_STEPS)

        for i, phase in enumerate(phase_degrees):
            nco(ser, f'PHASE:{phase:.1f}')
            time.sleep(0.15)  # Let phase settle
            spec = capture_spectrum(ps, handle, navg=NAVG // 2)  # Faster sweep
            amplitudes[i] = peak_amplitude(spec, freq)

        # Find min/max
        min_idx = np.argmin(amplitudes)
        max_idx = np.argmax(amplitudes)
        min_phase = phase_degrees[min_idx]
        min_amp = amplitudes[min_idx]
        max_phase = phase_degrees[max_idx]
        max_amp = amplitudes[max_idx]

        erase_depth = (1 - min_amp / write_amp) * 100
        contrast = (max_amp - min_amp) / max_amp * 100 if max_amp > 0 else 0

        print(f"    Best erase:       phase={min_phase:.0f}°, amp={min_amp:.0f} mV")
        print(f"    Peak construct:   phase={max_phase:.0f}°, amp={max_amp:.0f} mV")
        print(f"    Erase depth:      {erase_depth:.1f}% (vs F1 solo)")
        print(f"    Contrast:         {contrast:.1f}% (max-min)/max")
        print(f"    Noise floor:      {noise_amp:.0f} mV")

        # ── Step 4: Verify write→erase→write cycle ──
        print(f"    Write→Erase→Write cycle at optimal phase {min_phase:.0f}°...")
        nco(ser, 'Foff')
        time.sleep(0.3)

        # Write
        nco(ser, f'F1:{freq}')
        time.sleep(0.4)
        cycle_write = peak_amplitude(capture_spectrum(ps, handle), freq)

        # Erase (add F2 at cancel phase)
        nco(ser, f'F2:{freq}')
        nco(ser, f'PHASE:{min_phase:.1f}')
        time.sleep(0.4)
        cycle_erase = peak_amplitude(capture_spectrum(ps, handle), freq)

        # Re-write (remove F2)
        nco(ser, f'F2:0')
        time.sleep(0.4)
        cycle_rewrite = peak_amplitude(capture_spectrum(ps, handle), freq)

        print(f"    Cycle: WRITE={cycle_write:.0f} → ERASE={cycle_erase:.0f} → REWRITE={cycle_rewrite:.0f}")
        recovery_pct = (cycle_rewrite / cycle_write) * 100 if cycle_write > 0 else 0
        print(f"    Recovery: {recovery_pct:.1f}%")

        # Verdict per mode
        if erase_depth > 80:
            mode_verdict = "STRONG_ERASE"
            print(f"    ★ STRONG ERASE — {erase_depth:.0f}% depth")
        elif erase_depth > 50:
            mode_verdict = "PARTIAL_ERASE"
            print(f"    △ PARTIAL ERASE — {erase_depth:.0f}% depth")
        elif erase_depth > 20:
            mode_verdict = "WEAK_ERASE"
            print(f"    ~ WEAK — {erase_depth:.0f}% depth")
        else:
            mode_verdict = "NO_ERASE"
            print(f"    ✗ NO ERASE — {erase_depth:.0f}% depth")

        results[str(freq)] = {
            'frequency_hz': freq,
            'write_amplitude': float(write_amp),
            'f2_solo_amplitude': float(f2_amp),
            'noise_amplitude': float(noise_amp),
            'snr': float(snr),
            'phase_sweep': {
                'degrees': phase_degrees.tolist(),
                'amplitudes': amplitudes.tolist(),
            },
            'optimal_erase_phase_deg': float(min_phase),
            'min_amplitude': float(min_amp),
            'max_amplitude': float(max_amp),
            'erase_depth_pct': float(erase_depth),
            'contrast_pct': float(contrast),
            'cycle': {
                'write': float(cycle_write),
                'erase': float(cycle_erase),
                'rewrite': float(cycle_rewrite),
                'recovery_pct': float(recovery_pct),
            },
            'verdict': mode_verdict,
        }

    # ── Cleanup ───────────────────────────────────────────────────
    nco(ser, 'Foff')

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  E9 RESULTS: PHASE CANCELLATION (ELECTRONIC ERASE)")
    print("=" * 70)
    print()

    erase_depths = [r['erase_depth_pct'] for r in results.values()]
    contrasts = [r['contrast_pct'] for r in results.values()]
    recoveries = [r['cycle']['recovery_pct'] for r in results.values()]

    print(f"  Modes tested:       {len(results)}")
    print(f"  Erase depth:        {np.mean(erase_depths):.1f}% ± {np.std(erase_depths):.1f}%")
    print(f"  Best erase:         {np.max(erase_depths):.1f}% at {TEST_MODES[np.argmax(erase_depths)]} Hz")
    print(f"  Contrast:           {np.mean(contrasts):.1f}% ± {np.std(contrasts):.1f}%")
    print(f"  Cycle recovery:     {np.mean(recoveries):.1f}% ± {np.std(recoveries):.1f}%")
    print()

    n_strong = sum(1 for d in erase_depths if d > 80)
    n_partial = sum(1 for d in erase_depths if 50 < d <= 80)

    if n_strong >= 3:
        verdict = "PASS"
        print("  ★ PASS — Electronic erase demonstrated (>80% depth, ≥3 modes)")
    elif n_strong >= 1 or n_partial >= 3:
        verdict = "PASS_MARGINAL"
        print("  △ PASS (marginal) — Partial electronic erase works")
    else:
        verdict = "FAIL"
        print(f"  ✗ FAIL — Erase depth insufficient ({np.max(erase_depths):.0f}% best)")

    print()

    # ── Save ──────────────────────────────────────────────────────
    DATA_DIR = Path('data/results/phase_cancellation')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = DATA_DIR / f'e9_phase_cancellation_{ts}.json'

    output = {
        'experiment': 'E9_phase_cancellation',
        'timestamp': datetime.now().isoformat(),
        'config': {
            'test_modes_hz': TEST_MODES,
            'phase_steps': PHASE_STEPS,
            'n_avg': NAVG,
            'relay_rx': RELAY_RX,
        },
        'summary': {
            'mean_erase_depth_pct': float(np.mean(erase_depths)),
            'max_erase_depth_pct': float(np.max(erase_depths)),
            'mean_contrast_pct': float(np.mean(contrasts)),
            'mean_recovery_pct': float(np.mean(recoveries)),
        },
        'per_mode': results,
        'verdict': verdict,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {out_path}")

    # Cleanup hardware
    ser.close()
    mux.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))
    print("  Done.")


if __name__ == '__main__':
    main()
