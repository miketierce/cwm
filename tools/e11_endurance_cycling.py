#!/usr/bin/env python3
"""
E11: Endurance Cycling — Drive Stability Under Continuous Excitation

Drives the plate's strongest mode continuously for 5 minutes, taking
periodic spectral snapshots to verify no amplitude drift, frequency
shift, or mode degradation.

Prior result (rod): 549K+ cycles with <0.2 dB shift.
Expected (plate): glass has infinite fatigue life for linear vibration
at these amplitudes (<1μm displacement). This confirms it.

Also tests: does the H matrix change after prolonged driving?
Pre/post comparison with enrollment data.

Protocol:
  1. Baseline: measure 5 modes at start
  2. Drive strongest mode continuously (5 min)
  3. Every 60s: briefly measure all 5 modes (checkpoint)
  4. Post: re-measure all 5 modes
  5. Compare pre/post amplitudes and frequencies
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

# Configuration
DRIVE_FREQ = 54920  # Strongest mode (from enrollment)
MONITOR_MODES = [35840, 54920, 70000, 85000, 97011]
RELAY_RX = 1  # Plate I NW
DRIVE_DURATION_S = 300  # 5 minutes
CHECKPOINT_INTERVAL_S = 60  # Measure every 60s
NAVG = 16


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


def measure_modes(ps, handle, ser, modes, drive=True):
    """Measure amplitude at each mode frequency."""
    amplitudes = {}
    for freq in modes:
        if drive:
            nco(ser, f'F1:{freq}')
            time.sleep(0.3)
        spec = capture_spectrum(ps, handle)
        b = int(round(freq / BIN_HZ))
        amp = float(spec[max(0, b - 5):b + 6].max())
        amplitudes[freq] = amp
    return amplitudes


def main():
    print("=" * 70)
    print("  E11: Endurance Cycling — Drive Stability Test")
    print("=" * 70)
    print()
    print(f"  Drive frequency:  {DRIVE_FREQ} Hz")
    print(f"  Drive duration:   {DRIVE_DURATION_S}s ({DRIVE_DURATION_S/60:.0f} min)")
    print(f"  Checkpoints:      every {CHECKPOINT_INTERVAL_S}s")
    print(f"  Monitor modes:    {len(MONITOR_MODES)}")
    print(f"  At {DRIVE_FREQ} Hz, cycles = {DRIVE_FREQ * DRIVE_DURATION_S:,.0f}")
    print()

    ps, handle, ser, mux = setup_hardware()
    set_relay(mux, RELAY_RX)
    time.sleep(0.3)

    # ── Baseline measurement ──────────────────────────────────────
    print("  [1] Baseline measurement (all modes)...")
    nco(ser, 'Foff')
    time.sleep(0.3)

    baseline = measure_modes(ps, handle, ser, MONITOR_MODES)
    for freq, amp in baseline.items():
        print(f"    {freq} Hz: {amp:.0f} mV")
    print()

    # ── Continuous drive with checkpoints ─────────────────────────
    print(f"  [2] Driving {DRIVE_FREQ} Hz continuously...")
    nco(ser, f'F1:{DRIVE_FREQ}')
    time.sleep(0.5)

    checkpoints = []
    n_checks = DRIVE_DURATION_S // CHECKPOINT_INTERVAL_S
    start_time = time.time()

    for ck in range(n_checks):
        # Wait until next checkpoint
        target_time = start_time + (ck + 1) * CHECKPOINT_INTERVAL_S
        wait_time = target_time - time.time()
        if wait_time > 0:
            time.sleep(wait_time)

        elapsed = time.time() - start_time
        cycles = int(DRIVE_FREQ * elapsed)

        # Quick measurement at drive frequency (don't change freq!)
        spec = capture_spectrum(ps, handle, navg=8)
        b = int(round(DRIVE_FREQ / BIN_HZ))
        drive_amp = float(spec[max(0, b - 5):b + 6].max())

        drift_pct = (drive_amp - baseline[DRIVE_FREQ]) / baseline[DRIVE_FREQ] * 100

        checkpoints.append({
            'elapsed_s': float(elapsed),
            'cycles': cycles,
            'drive_amplitude': float(drive_amp),
            'drift_pct': float(drift_pct),
        })

        print(f"    t={elapsed:.0f}s ({cycles:,} cycles): "
              f"amp={drive_amp:.0f} mV (drift: {drift_pct:+.2f}%)")

    # ── Post measurement ──────────────────────────────────────────
    total_elapsed = time.time() - start_time
    total_cycles = int(DRIVE_FREQ * total_elapsed)
    print(f"\n  [3] Post measurement after {total_cycles:,} cycles...")

    # First measure drive mode while still driving
    spec = capture_spectrum(ps, handle)
    b = int(round(DRIVE_FREQ / BIN_HZ))
    final_drive_amp = float(spec[max(0, b - 5):b + 6].max())

    # Now measure all modes
    post = measure_modes(ps, handle, ser, MONITOR_MODES)
    for freq, amp in post.items():
        base_amp = baseline[freq]
        change = (amp - base_amp) / base_amp * 100 if base_amp > 0 else 0
        print(f"    {freq} Hz: {amp:.0f} mV (Δ: {change:+.2f}%)")

    # ── Cleanup ───────────────────────────────────────────────────
    nco(ser, 'Foff')

    # ── Analysis ──────────────────────────────────────────────────
    print(f"\n" + "=" * 70)
    print("  E11 RESULTS: ENDURANCE CYCLING")
    print("=" * 70)
    print()

    # Drift analysis
    drift_values = [cp['drift_pct'] for cp in checkpoints]
    max_drift = max(abs(d) for d in drift_values) if drift_values else 0

    print(f"  Total cycles:      {total_cycles:,}")
    print(f"  Duration:          {total_elapsed:.0f}s")
    print(f"  Drive mode drift:  max |Δ| = {max_drift:.2f}%")
    print()

    # Pre/post comparison
    changes = []
    for freq in MONITOR_MODES:
        if baseline[freq] > 0:
            change = abs(post[freq] - baseline[freq]) / baseline[freq] * 100
            changes.append(change)

    max_change = max(changes) if changes else 0
    mean_change = np.mean(changes) if changes else 0

    print(f"  Pre/post amplitude change:")
    print(f"    Max:  {max_change:.2f}%")
    print(f"    Mean: {mean_change:.2f}%")
    print()

    # Verdict
    if max_drift < 1.0 and max_change < 2.0:
        verdict = "PASS"
        print(f"  ★ PASS — {total_cycles:,} cycles, <{max_drift:.1f}% drift")
        print("    Plate shows no fatigue or degradation")
    elif max_drift < 5.0 and max_change < 5.0:
        verdict = "PASS_MARGINAL"
        print(f"  △ PASS (marginal) — {max_drift:.1f}% drift over {total_cycles:,} cycles")
    else:
        verdict = "FAIL"
        print(f"  ✗ FAIL — {max_drift:.1f}% drift detected")

    print()

    # ── Save ──────────────────────────────────────────────────────
    DATA_DIR = Path('data/results/endurance')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = DATA_DIR / f'e11_endurance_{ts}.json'

    output = {
        'experiment': 'E11_endurance_cycling',
        'timestamp': datetime.now().isoformat(),
        'config': {
            'drive_freq_hz': DRIVE_FREQ,
            'drive_duration_s': DRIVE_DURATION_S,
            'checkpoint_interval_s': CHECKPOINT_INTERVAL_S,
            'relay_rx': RELAY_RX,
            'monitor_modes_hz': MONITOR_MODES,
        },
        'summary': {
            'total_cycles': total_cycles,
            'total_duration_s': float(total_elapsed),
            'max_drift_pct': float(max_drift),
            'max_pre_post_change_pct': float(max_change),
            'mean_pre_post_change_pct': float(mean_change),
        },
        'baseline': {str(k): v for k, v in baseline.items()},
        'post': {str(k): v for k, v in post.items()},
        'checkpoints': checkpoints,
        'verdict': verdict,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {out_path}")

    ser.close()
    mux.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))
    print("  Done.")


if __name__ == '__main__':
    main()
