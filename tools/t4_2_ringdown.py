#!/usr/bin/env python3
"""T4.2 — Direct Ringdown Visibility.

Drive plate at 35,840 Hz via AWG, stop, capture ringdown sequence.
With >90% acoustic fraction (T4.1 PASS), exponential decay should be visible.

Success metric: visible exponential decay at 35,840 Hz after stop.
Expected: τ ≈ 24.5 ms from Q=2759.

Hardware:
  - PicoScope AWG → Board D (×3.69) → TX PZT (SW)
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (AC, ±5V)
  - DDS off (shared-PZT config, pre-rewire)
"""

import ctypes as ct
import numpy as np
import serial
import time
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ['DYLD_LIBRARY_PATH'] = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
ps = ct.CDLL('/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib')

NSAMPLES = 8064
TIMEBASE = 7  # 1280 ns/sample -> 781.25 kHz
BIN_HZ = 781250.0 / NSAMPLES  # ~96.9 Hz/bin
TARGET_FREQ = 35840
DRIVE_UVPP = 500_000  # 0.5 Vpp

MUX_PORT = '/dev/cu.usbserial-11310'


def open_scope():
    ps.ps2000_open_unit.restype = ct.c_int16
    h = ps.ps2000_open_unit()
    if h < 1:
        raise RuntimeError(f"PicoScope open failed (handle={h})")
    ps.ps2000_set_channel(h, 0, 1, 0, 7)  # ChA, enabled, AC, ±5V
    ps.ps2000_set_channel(h, 1, 0, 0, 7)  # ChB disabled
    return h


def open_mux():
    mux = serial.Serial(MUX_PORT, 9600, timeout=2, dsrdtr=False, rtscts=False)
    mux.dtr = False
    time.sleep(0.5)
    mux.reset_input_buffer()
    # Retry relay 8 command
    for attempt in range(4):
        mux.write(b'8\r\n')
        time.sleep(0.5)
        resp = mux.read(mux.in_waiting).decode(errors='replace').strip()
        if 'OK:8' in resp:
            return mux
        time.sleep(0.8)
    print(f"WARNING: Relay mux last response: {resp}")
    return mux


def capture_spectrum(h, navg=1):
    buf = (ct.c_int16 * NSAMPLES)()
    ov = ct.c_int16()
    specs = []
    for _ in range(navg):
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(h, NSAMPLES, TIMEBASE, 1, ct.byref(ticks))
        time.sleep(0.003)
        for _ in range(500):
            if ps.ps2000_ready(h):
                break
            time.sleep(0.002)
        ps.ps2000_get_values(h, ct.byref(buf), None, None, None, ct.byref(ov), NSAMPLES, 0)
        d = np.array(buf[:], dtype=float)
        d -= d.mean()
        sp = np.abs(np.fft.rfft(d * np.hanning(NSAMPLES)))
        specs.append(sp)
    return np.mean(specs, axis=0)


def peak_at(sp, freq, window=5):
    b = int(freq / BIN_HZ)
    return float(np.max(sp[max(0, b - window):b + window]))


def set_awg(h, freq_hz, uvpp):
    ps.ps2000_set_sig_gen_built_in(
        h, ct.c_int32(0), ct.c_int32(uvpp), ct.c_int16(0),
        ct.c_float(freq_hz), ct.c_float(freq_hz),
        ct.c_float(0), ct.c_float(0), ct.c_int16(0), ct.c_uint32(0)
    )


def stop_awg(h):
    ps.ps2000_set_sig_gen_built_in(
        h, ct.c_int32(0), ct.c_int32(0), ct.c_int16(0),
        ct.c_float(1000.0), ct.c_float(1000.0),
        ct.c_float(0), ct.c_float(0), ct.c_int16(0), ct.c_uint32(0)
    )


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 65)
    print("T4.2 — Direct Ringdown Visibility")
    print("=" * 65)
    print(f"  Target: {TARGET_FREQ} Hz")
    print(f"  Expected τ: 24.5 ms (Q=2759)")
    print(f"  Capture window: {NSAMPLES * 1.28e-3:.1f} ms per block")
    print(f"  Drive: {DRIVE_UVPP/1e6:.1f} Vpp via AWG")
    print()

    h = open_scope()
    print(f"  PicoScope: handle={h}")
    mux = open_mux()
    print(f"  Relay: 8 (NE RX)")

    buf = (ct.c_int16 * NSAMPLES)()
    ov = ct.c_int16()

    # 1) Baseline (AWG off)
    print("\n[1] Baseline (AWG off, 10 avg)...")
    stop_awg(h)
    time.sleep(0.5)
    sp_base = capture_spectrum(h, 10)
    noise = np.median(sp_base[10:])
    peak_base = peak_at(sp_base, TARGET_FREQ)
    print(f"    Noise floor: {noise:.0f}")
    print(f"    35840 Hz (no drive): {peak_base:.0f} ({peak_base/noise:.1f}x)")

    # 2) Steady state (AWG on)
    print("\n[2] Steady state: AWG @ 35840 Hz, 500 mVpp (20 avg)...")
    set_awg(h, TARGET_FREQ, DRIVE_UVPP)
    time.sleep(2.0)  # full ring-up (>>τ)
    sp_on = capture_spectrum(h, 20)
    peak_on = peak_at(sp_on, TARGET_FREQ)
    print(f"    35840 Hz peak (driving): {peak_on:.0f} ({peak_on/noise:.1f}x)")

    # 3) Ringdown: stop AWG, capture blocks as fast as possible
    print("\n[3] Ringdown: stopping AWG, rapid captures...")
    print(f"    {'Block':>6} {'t(ms)':>8} {'Peak':>8} {'Fraction':>9} {'SNR':>6}")
    print(f"    {'─'*6} {'─'*8} {'─'*8} {'─'*9} {'─'*6}")

    stop_awg(h)
    ringdown_peaks = []
    ringdown_times = []
    t0 = time.time()

    # Capture 12 blocks rapidly (covers ~120 ms, should see full decay)
    for i in range(12):
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(h, NSAMPLES, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(h):
                break
            time.sleep(0.001)
        t_capture = (time.time() - t0) * 1000  # ms since AWG stop
        ps.ps2000_get_values(h, ct.byref(buf), None, None, None, ct.byref(ov), NSAMPLES, 0)
        d = np.array(buf[:], dtype=float)
        d -= d.mean()
        sp = np.abs(np.fft.rfft(d * np.hanning(NSAMPLES)))
        pk = peak_at(sp, TARGET_FREQ)
        ringdown_peaks.append(pk)
        ringdown_times.append(t_capture)
        frac = pk / peak_on * 100 if peak_on > 0 else 0
        snr = pk / noise
        print(f"    {i+1:>6} {t_capture:>8.1f} {pk:>8.0f} {frac:>8.1f}% {snr:>6.1f}x")

    # 4) Second steady-state (confirm still working)
    print("\n[4] Recovery: AWG back on (10 avg)...")
    set_awg(h, TARGET_FREQ, DRIVE_UVPP)
    time.sleep(2.0)
    sp_recover = capture_spectrum(h, 10)
    peak_recover = peak_at(sp_recover, TARGET_FREQ)
    print(f"    35840 Hz peak (recovered): {peak_recover:.0f} ({peak_recover/noise:.1f}x)")

    # 5) Analysis
    print("\n" + "=" * 65)
    print("ANALYSIS")
    print("=" * 65)

    # Find points above noise for exponential fit
    above_noise = [(t, pk) for t, pk in zip(ringdown_times, ringdown_peaks)
                   if pk > noise * 2.0]

    if len(above_noise) >= 3:
        ts_arr = np.array([v[0] for v in above_noise])
        pks_arr = np.array([v[1] for v in above_noise])
        log_pks = np.log(pks_arr)
        # Linear fit: log(peak) = -t/τ + C
        coeffs = np.polyfit(ts_arr, log_pks, 1)
        tau_ms = -1.0 / coeffs[0] if coeffs[0] < 0 else float('inf')
        # R² of fit
        fit_vals = np.polyval(coeffs, ts_arr)
        ss_res = np.sum((log_pks - fit_vals)**2)
        ss_tot = np.sum((log_pks - log_pks.mean())**2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        print(f"  Points above 2× noise: {len(above_noise)}")
        print(f"  Exponential fit: τ = {tau_ms:.1f} ms")
        print(f"  Expected: τ = 24.5 ms (from Q=2759 at 35,840 Hz)")
        print(f"  Fit R²: {r_squared:.4f}")
        print(f"  First ringdown / steady-state: {ringdown_peaks[0]/peak_on*100:.1f}%")

        if tau_ms > 5 and tau_ms < 200 and r_squared > 0.7:
            gate = "PASS"
            print(f"\n  ★ T4.2 GATE: PASS — visible exponential decay (τ={tau_ms:.1f} ms, R²={r_squared:.3f})")
        elif len(above_noise) >= 2:
            gate = "MARGINAL"
            print(f"\n  ★ T4.2 GATE: MARGINAL — decay visible but fit quality low (R²={r_squared:.3f})")
        else:
            gate = "FAIL"
            print(f"\n  ★ T4.2 GATE: FAIL — insufficient exponential character")
    else:
        tau_ms = 0
        r_squared = 0
        gate = "FAIL"
        print(f"  Only {len(above_noise)} points above 2× noise — insufficient for fit")
        print(f"\n  ★ T4.2 GATE: FAIL — ringdown not visible above noise")

    # Save results
    stop_awg(h)
    ps.ps2000_stop(h)
    ps.ps2000_close_unit(ct.c_int16(h))
    mux.close()

    out_dir = Path("data/results/ringdown")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"t4_2_ringdown_{ts}.json"
    results = {
        "experiment": "T4.2",
        "timestamp": ts,
        "gate": gate,
        "target_freq_hz": TARGET_FREQ,
        "drive_uvpp": DRIVE_UVPP,
        "noise_floor": float(noise),
        "peak_steady_state": float(peak_on),
        "peak_recover": float(peak_recover),
        "ringdown_times_ms": ringdown_times,
        "ringdown_peaks": [float(p) for p in ringdown_peaks],
        "tau_fit_ms": float(tau_ms),
        "r_squared": float(r_squared),
        "n_above_noise": len(above_noise),
        "steady_state_snr": float(peak_on / noise),
    }
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved: {out_file}")
    print("Done.")


if __name__ == '__main__':
    main()
