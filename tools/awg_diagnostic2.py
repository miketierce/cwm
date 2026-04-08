#!/usr/bin/env python3
"""
AWG diagnostic v2 — single scope session, channel isolation tests.
Diagnose why AWG captures return 0 data when Ch B is enabled.
"""
import ctypes
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwm_picoscope import (
    TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP,
    AWG_CHIRP_LO, AWG_CHIRP_HI,
)

import json

USERS_FILE = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "users.json"
with open(USERS_FILE) as f:
    _db = json.load(f)
ROD1_PEAKS = _db["rods"]["1"]["perturbed_hz"][:10]
ROD1_F1 = ROD1_PEAKS[0]

from picosdk.ps2000 import ps2000


def fft_analyze(captures, label, enrolled_hz=None):
    """FFT and print analysis."""
    if not captures:
        print(f"  {label}: NO DATA")
        return None
    cap_len = len(captures[0])
    n_fft = cap_len * 4
    freq = np.fft.rfftfreq(n_fft, d=1.0 / SAMPLE_RATE)
    bin_hz = freq[1] - freq[0]
    mag = np.zeros(n_fft // 2 + 1, dtype=np.float64)
    for raw in captures:
        windowed = raw[:cap_len] * np.hanning(cap_len)
        mag += np.abs(np.fft.rfft(windowed, n=n_fft))
    mag /= len(captures)

    min_bin = int(500 / bin_hz)
    noise = np.median(mag[min_bin:])
    peak_mag = np.max(mag[min_bin:])
    peak_bin = min_bin + np.argmax(mag[min_bin:])
    peak_hz = freq[peak_bin]
    snr = peak_mag / noise if noise > 0 else 0

    print(f"  {label}: peak={peak_mag:.0f} @ {peak_hz:.0f} Hz, "
          f"noise={noise:.0f}, SNR={snr:.1f}× ({20*np.log10(max(snr,1)):.1f} dB)")

    if enrolled_hz:
        hits = 0
        for f_enr in enrolled_hz:
            window = f_enr * 0.05
            mask = (freq >= f_enr - window) & (freq <= f_enr + window)
            if np.any(mask):
                idx = np.where(mask)[0]
                if np.max(mag[idx]) > noise * 3:
                    hits += 1
        print(f"         Enrolled peaks found: {hits}/{len(enrolled_hz)}")

    return {"freq": freq, "mag": mag, "peak_hz": peak_hz, "snr": snr}


def run_block_capture(handle, n_captures=4, read_ch_b=False):
    """Run block captures with auto-trigger. Returns (ch_a_list, ch_b_list)."""
    ch_a_all = []
    ch_b_all = []
    for i in range(n_captures):
        # Use trigger source=0 (Ch A), threshold=0, auto_trigger_ms=100
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)

        time_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(
            handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(time_ms)
        )
        t0 = time.time()
        ready = False
        while not ready:
            time.sleep(0.005)
            if ps2000.ps2000_ready(handle) != 0:
                ready = True
                break
            if time.time() - t0 > 2:
                break

        buf_a = (ctypes.c_int16 * N_SAMPLES)()
        buf_b = (ctypes.c_int16 * N_SAMPLES)()
        overflow = ctypes.c_int16()
        n = ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES
        )
        if n > 0:
            ch_a_all.append(np.array(buf_a[:n], dtype=np.float64))
            if read_ch_b:
                ch_b_all.append(np.array(buf_b[:n], dtype=np.float64))
        else:
            if not ready:
                print(f"    [cap {i+1}: TIMEOUT]")
            else:
                print(f"    [cap {i+1}: ready but n={n}]")

    return ch_a_all, ch_b_all


# ══════════════════════════════════════════════════════════════════════════
print(f"Rod 1 f1 = {ROD1_F1:.1f} Hz")
print(f"Rod 1 first 5 peaks: {[round(f,1) for f in ROD1_PEAKS[:5]]}")
print()

handle = ps2000.ps2000_open_unit()
if handle <= 0:
    print(f"FATAL: ps2000_open_unit failed (handle={handle})")
    sys.exit(1)

print(f"Scope opened (handle={handle})")

try:
    # ─────────────────────────────────────────────────────────────────────
    #  PHASE A: Test with Ch A ONLY (known working config)
    # ─────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE A: Ch A ONLY (Ch B disabled) — baseline")
    print("=" * 60)

    # Ch A on, Ch B off, ±1V range (index 6)
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)

    # A1: AWG off — baseline noise
    print("\n  A1: Noise floor (AWG off)")
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    time.sleep(0.1)
    ch_a, _ = run_block_capture(handle, n_captures=4)
    fft_analyze(ch_a, "Ch A noise")
    if ch_a:
        print(f"  Time-domain: RMS={np.sqrt(np.mean(ch_a[0]**2)):.1f} ADC, "
              f"peak={np.max(np.abs(ch_a[0])):.0f} ADC")

    # A2: AWG sine at Rod 1 f1
    print(f"\n  A2: AWG sine @ {ROD1_F1:.0f} Hz (Rod 1 f1)")
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(ROD1_F1), float(ROD1_F1), 0.0, 0.0, 0, 0
    )
    time.sleep(0.3)
    ch_a, _ = run_block_capture(handle, n_captures=4)
    fft_analyze(ch_a, "Ch A at f1", ROD1_PEAKS[:3])
    if ch_a:
        print(f"  Time-domain: RMS={np.sqrt(np.mean(ch_a[0]**2)):.1f} ADC, "
              f"peak={np.max(np.abs(ch_a[0])):.0f} ADC")

    # A3: AWG sine at 10 kHz (reference — well within PZT bandwidth)
    print(f"\n  A3: AWG sine @ 10000 Hz")
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        10000.0, 10000.0, 0.0, 0.0, 0, 0
    )
    time.sleep(0.3)
    ch_a, _ = run_block_capture(handle, n_captures=4)
    fft_analyze(ch_a, "Ch A at 10k")
    if ch_a:
        print(f"  Time-domain: RMS={np.sqrt(np.mean(ch_a[0]**2)):.1f} ADC, "
              f"peak={np.max(np.abs(ch_a[0])):.0f} ADC")

    # A4: AWG sine at 35 kHz (where we saw peaks before — PZT resonance?)
    print(f"\n  A4: AWG sine @ 35000 Hz (suspected PZT self-resonance)")
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        35000.0, 35000.0, 0.0, 0.0, 0, 0
    )
    time.sleep(0.3)
    ch_a, _ = run_block_capture(handle, n_captures=4)
    fft_analyze(ch_a, "Ch A at 35k")
    if ch_a:
        print(f"  Time-domain: RMS={np.sqrt(np.mean(ch_a[0]**2)):.1f} ADC, "
              f"peak={np.max(np.abs(ch_a[0])):.0f} ADC")

    # A5: Full sweep 1-100 kHz (reproducing the original failed run)
    print(f"\n  A5: AWG sweep 1-100 kHz (0.5 s, 8 captures)")
    dwell = 0.001
    sweep_time = 0.5
    increment = (AWG_CHIRP_HI - AWG_CHIRP_LO) * dwell / sweep_time
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(AWG_CHIRP_LO), float(AWG_CHIRP_HI),
        float(increment), float(dwell),
        0, 0
    )
    time.sleep(0.5)
    ch_a, _ = run_block_capture(handle, n_captures=8)
    fft_analyze(ch_a, "Ch A sweep", ROD1_PEAKS)

    # A6: Slow sweep (5 s, 16 captures — more averaging)
    print(f"\n  A6: AWG sweep 1-100 kHz (5 s, 16 captures)")
    sweep_time = 5.0
    increment = (AWG_CHIRP_HI - AWG_CHIRP_LO) * dwell / sweep_time
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(AWG_CHIRP_LO), float(AWG_CHIRP_HI),
        float(increment), float(dwell),
        0, 0
    )
    time.sleep(0.5)
    ch_a, _ = run_block_capture(handle, n_captures=16)
    fft_analyze(ch_a, "Ch A slow sweep", ROD1_PEAKS)

    # ─────────────────────────────────────────────────────────────────────
    #  PHASE B: Enable Ch B and repeat key tests
    # ─────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE B: Ch A + Ch B both enabled")
    print("=" * 60)

    # Re-configure with both channels
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V
    ps2000.ps2000_set_channel(handle, 1, True, 1, 6)    # Ch B ±1V

    # B1: AWG sine at Rod 1 f1 — compare Ch A vs Ch B
    print(f"\n  B1: AWG sine @ {ROD1_F1:.0f} Hz, both channels")
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(ROD1_F1), float(ROD1_F1), 0.0, 0.0, 0, 0
    )
    time.sleep(0.3)
    ch_a, ch_b = run_block_capture(handle, n_captures=4, read_ch_b=True)
    fft_analyze(ch_a, "Ch A (R2,3,4) at f1", ROD1_PEAKS[:3])
    fft_analyze(ch_b, "Ch B (Rod 1) at f1", ROD1_PEAKS[:3])
    if ch_a:
        print(f"  Ch A time: RMS={np.sqrt(np.mean(ch_a[0]**2)):.1f}, "
              f"peak={np.max(np.abs(ch_a[0])):.0f}")
    if ch_b:
        print(f"  Ch B time: RMS={np.sqrt(np.mean(ch_b[0]**2)):.1f}, "
              f"peak={np.max(np.abs(ch_b[0])):.0f}")

    # B2: Full sweep, both channels
    print(f"\n  B2: AWG sweep 1-100 kHz, both channels (8 caps)")
    dwell = 0.001
    sweep_time = 0.5
    increment = (AWG_CHIRP_HI - AWG_CHIRP_LO) * dwell / sweep_time
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(AWG_CHIRP_LO), float(AWG_CHIRP_HI),
        float(increment), float(dwell),
        0, 0
    )
    time.sleep(0.5)
    ch_a, ch_b = run_block_capture(handle, n_captures=8, read_ch_b=True)
    fft_analyze(ch_a, "Ch A sweep", ROD1_PEAKS)
    fft_analyze(ch_b, "Ch B sweep", ROD1_PEAKS)

    # B3: Drive at each of Rod 1's first 5 enrolled peaks, measure Ch B response
    print(f"\n  B3: Step through Rod 1 enrolled peaks (Ch B)")
    for i, f_peak in enumerate(ROD1_PEAKS[:5]):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(f_peak), float(f_peak), 0.0, 0.0, 0, 0
        )
        time.sleep(0.5)  # longer settle for single freq
        ch_a, ch_b = run_block_capture(handle, n_captures=4, read_ch_b=True)
        a_res = fft_analyze(ch_a, f"  Ch A @ {f_peak:.0f} Hz")
        b_res = fft_analyze(ch_b, f"  Ch B @ {f_peak:.0f} Hz")
        if b_res and a_res:
            ratio = b_res["snr"] / max(a_res["snr"], 0.01)
            print(f"         B/A SNR ratio: {ratio:.2f}")

    # ─────────────────────────────────────────────────────────────────────
    #  PHASE C: Sensitivity test — higher gain ranges
    # ─────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE C: Higher sensitivity ranges")
    print("=" * 60)

    for range_mv, range_idx in [(500, 5), (200, 4), (100, 3)]:
        print(f"\n  ±{range_mv} mV range:")
        ps2000.ps2000_set_channel(handle, 0, True, 1, range_idx)
        ps2000.ps2000_set_channel(handle, 1, True, 1, range_idx)

        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(ROD1_F1), float(ROD1_F1), 0.0, 0.0, 0, 0
        )
        time.sleep(0.3)
        ch_a, ch_b = run_block_capture(handle, n_captures=4, read_ch_b=True)
        fft_analyze(ch_a, f"Ch A (±{range_mv}mV)")
        fft_analyze(ch_b, f"Ch B (±{range_mv}mV)")
        if ch_a:
            adc_max = max(np.max(np.abs(c)) for c in ch_a)
            sat = "SATURATED" if adc_max > 30000 else "OK"
            print(f"  Ch A ADC max: {adc_max:.0f}/32767 {sat}")
        if ch_b:
            adc_max = max(np.max(np.abs(c)) for c in ch_b)
            sat = "SATURATED" if adc_max > 30000 else "OK"
            print(f"  Ch B ADC max: {adc_max:.0f}/32767 {sat}")

    # ─────────────────────────────────────────────────────────────────────
    #  PHASE D: Tap reference on Ch B (Rod 1)
    # ─────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE D: Tap reference (Rod 1 on Ch B)")
    print("=" * 60)

    # Turn off AWG
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )

    # Reset channels to ±500 mV
    ps2000.ps2000_set_channel(handle, 0, True, 1, 5)
    ps2000.ps2000_set_channel(handle, 1, True, 1, 5)

    # Trigger on Ch B (Rod 1 sense)
    threshold_counts = int(200 / 500 * 32767)
    ps2000.ps2000_set_trigger(handle, 1, threshold_counts, 0, 0, 20000)

    print("  >>> FLICK Rod 1 now (20 s timeout) <<<")

    time_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(
        handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(time_ms)
    )
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 22:
            break

    buf_a = (ctypes.c_int16 * N_SAMPLES)()
    buf_b = (ctypes.c_int16 * N_SAMPLES)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), N_SAMPLES
    )
    if n > 0:
        tap_a = [np.array(buf_a[:n], dtype=np.float64)]
        tap_b = [np.array(buf_b[:n], dtype=np.float64)]
        fft_analyze(tap_a, "Ch A (tap spillover)", ROD1_PEAKS)
        fft_analyze(tap_b, "Ch B (Rod 1 tap)", ROD1_PEAKS)
        print(f"  Ch A time: RMS={np.sqrt(np.mean(tap_a[0]**2)):.1f}, "
              f"peak={np.max(np.abs(tap_a[0])):.0f}")
        print(f"  Ch B time: RMS={np.sqrt(np.mean(tap_b[0]**2)):.1f}, "
              f"peak={np.max(np.abs(tap_b[0])):.0f}")
    else:
        print("  No capture (timeout or no flick)")

finally:
    # AWG off
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
