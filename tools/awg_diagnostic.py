#!/usr/bin/env python3
"""
AWG coupling diagnostic — systematic tests to identify why AWG drive
is not exciting rod resonances.

Setup (as user describes):
  AWG OUT → drive PZTs (all rods in parallel)
  Ch A    → sense PZTs for Rods 2, 3, 4 (chained)
  Ch B    → sense PZT for Rod 1 only
  Rod 1 has putty reapplied.

Tests:
  1. Baseline noise (AWG off) on both channels
  2. Fixed-freq sine at several frequencies (check feedthrough)
  3. Slow sweep with longer captures
  4. Single-frequency dwell at Rod 1's known f1 (listen on Ch B)
  5. Amplitude sweep (check if PZTs need more/less drive)
  6. Multitone at Rod 1's enrolled peaks
"""
import ctypes
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import constants from cwm_picoscope
from cwm_picoscope import (
    TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP,
    AWG_CHIRP_LO, AWG_CHIRP_HI, VOLTAGE_RANGE_MV, N_MODES,
)

import json

# Load Rod 1 enrolled peaks
USERS_FILE = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "users.json"
with open(USERS_FILE) as f:
    _db = json.load(f)
ROD1_PEAKS = _db["rods"]["1"]["perturbed_hz"][:10]
ROD1_F1 = ROD1_PEAKS[0]  # fundamental

print(f"Rod 1 enrolled peaks (first 10): {[round(f,1) for f in ROD1_PEAKS]}")
print(f"Rod 1 f1 = {ROD1_F1:.1f} Hz")
print(f"AWG amplitude = {AWG_DRIVE_UVPP} µVpp = {AWG_DRIVE_UVPP/1e6:.1f} Vpp")
print(f"Sample rate = {SAMPLE_RATE} Hz, {N_SAMPLES} samples, "
      f"{N_SAMPLES/SAMPLE_RATE*1000:.1f} ms per capture")
print(f"Freq resolution = {SAMPLE_RATE/(N_SAMPLES*4):.1f} Hz (with 4× zero-pad)")
print()


def open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    return handle, ps2000


def setup_channels(handle, ps2000, range_mv=500, ch_b_on=True):
    """Enable Ch A and optionally Ch B, both DC coupled."""
    range_idx = {50: 2, 100: 3, 200: 4, 500: 5, 1000: 6, 2000: 7}[range_mv]
    ps2000.ps2000_set_channel(handle, 0, True, 1, range_idx)   # Ch A
    ps2000.ps2000_set_channel(handle, 1, ch_b_on, 1, range_idx)  # Ch B
    return range_idx


def awg_off(handle, ps2000):
    """Turn off signal generator."""
    try:
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass


def awg_sine(handle, ps2000, freq_hz, uvpp=AWG_DRIVE_UVPP):
    """Fixed sine wave."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, uvpp, 0,   # offset=0, amplitude, waveType=0 (sine)
        float(freq_hz), float(freq_hz),
        0.0, 0.0, 0, 0
    )


def awg_sweep(handle, ps2000, lo_hz, hi_hz, sweep_time_s=0.5, uvpp=AWG_DRIVE_UVPP):
    """Frequency sweep."""
    dwell = 0.001
    increment = (hi_hz - lo_hz) * dwell / sweep_time_s
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, uvpp, 0,
        float(lo_hz), float(hi_hz),
        float(increment), float(dwell),
        0, 0  # sweep up, continuous
    )


def capture_both(handle, ps2000, n_captures=1, settle_s=0.15):
    """Capture from both Ch A and Ch B. Returns (ch_a_list, ch_b_list)."""
    time.sleep(settle_s)

    ch_a_all = []
    ch_b_all = []
    for i in range(n_captures):
        # Auto-trigger: source=0 (Ch A), threshold=0, auto_trigger_ms=10
        # With threshold=0 and auto=10ms, it triggers immediately on any signal
        # or auto-fires after 10ms if there's no signal.
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 10)

        time_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(
            handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(time_ms)
        )
        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.001)
            if time.time() - t0 > 5:
                print(f"    [capture {i+1}: timeout]")
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
            ch_b_all.append(np.array(buf_b[:n], dtype=np.float64))
        else:
            print(f"    [capture {i+1}: n={n}, no data]")

    return ch_a_all, ch_b_all


def fft_avg(captures, sample_rate=SAMPLE_RATE):
    """Average FFT magnitude across captures. Returns (freq, mag, bin_hz)."""
    if not captures:
        return None, None, None
    cap_len = len(captures[0])
    n_fft = cap_len * 4
    freq = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    bin_hz = freq[1] - freq[0]
    mag = np.zeros(n_fft // 2 + 1, dtype=np.float64)
    for raw in captures:
        windowed = raw[:cap_len] * np.hanning(cap_len)
        spectrum = np.fft.rfft(windowed, n=n_fft)
        mag += np.abs(spectrum)
    mag /= len(captures)
    return freq, mag, bin_hz


def analyze_spectrum(freq, mag, label="", enrolled_hz=None):
    """Print spectrum stats and check for peaks near enrolled frequencies."""
    if freq is None:
        print(f"  {label}: No data")
        return

    min_bin = int(500 / (freq[1] - freq[0]))  # skip below 500 Hz
    noise = np.median(mag[min_bin:])
    peak_mag = np.max(mag[min_bin:])
    peak_bin = min_bin + np.argmax(mag[min_bin:])
    peak_hz = freq[peak_bin]
    snr_linear = peak_mag / noise if noise > 0 else 0
    snr_db = 20 * np.log10(snr_linear) if snr_linear > 1 else 0

    print(f"  {label}: peak={peak_mag:.0f} @ {peak_hz:.0f} Hz, "
          f"noise={noise:.0f}, SNR={snr_linear:.1f}× ({snr_db:.1f} dB)")

    # Check for peaks at enrolled frequencies
    if enrolled_hz:
        bin_hz = freq[1] - freq[0]
        hits = 0
        for f_enr in enrolled_hz:
            window = f_enr * 0.05  # ±5%
            mask = (freq >= f_enr - window) & (freq <= f_enr + window)
            if np.any(mask):
                idx = np.where(mask)[0]
                best_mag = np.max(mag[idx])
                if best_mag > noise * 3:
                    hits += 1
        print(f"         Enrolled peaks detected (>3× noise): {hits}/{len(enrolled_hz)}")

    return {"peak_hz": peak_hz, "peak_mag": peak_mag, "noise": noise,
            "snr_linear": snr_linear, "snr_db": snr_db}


# ══════════════════════════════════════════════════════════════════════════
#  TEST 1: Baseline noise (AWG off)
# ══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 1: Baseline noise (AWG off)")
print("=" * 60)

handle, ps2000 = open_scope()
try:
    setup_channels(handle, ps2000, range_mv=500, ch_b_on=True)
    awg_off(handle, ps2000)
    ch_a, ch_b = capture_both(handle, ps2000, n_captures=4, settle_s=0.5)
    freq_a, mag_a, _ = fft_avg(ch_a)
    freq_b, mag_b, _ = fft_avg(ch_b)
    analyze_spectrum(freq_a, mag_a, "Ch A (Rods 2,3,4 sense)", ROD1_PEAKS)
    analyze_spectrum(freq_b, mag_b, "Ch B (Rod 1 sense)", ROD1_PEAKS)
    # Save raw time-domain stats
    if ch_a:
        print(f"  Ch A time-domain: min={min(c.min() for c in ch_a):.0f}, "
              f"max={max(c.max() for c in ch_a):.0f} ADC counts")
    if ch_b:
        print(f"  Ch B time-domain: min={min(c.min() for c in ch_b):.0f}, "
              f"max={max(c.max() for c in ch_b):.0f} ADC counts")
finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

print()

# ══════════════════════════════════════════════════════════════════════════
#  TEST 2: Fixed-frequency sine at several frequencies
# ══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 2: Fixed-frequency sine at specific frequencies")
print("=" * 60)

test_freqs = [
    1000, 2000, 5000, 10000, 20000, 35000, 50000, 80000,
    round(ROD1_F1),  # Rod 1's fundamental
]
# Sort and deduplicate
test_freqs = sorted(set(test_freqs))

handle, ps2000 = open_scope()
try:
    setup_channels(handle, ps2000, range_mv=500, ch_b_on=True)
    for f in test_freqs:
        tag = f" ← Rod 1 f1" if abs(f - ROD1_F1) < 50 else ""
        print(f"\n  Sine @ {f} Hz{tag}:")
        awg_sine(handle, ps2000, f)
        ch_a, ch_b = capture_both(handle, ps2000, n_captures=4, settle_s=0.2)
        freq_a, mag_a, _ = fft_avg(ch_a)
        freq_b, mag_b, _ = fft_avg(ch_b)
        analyze_spectrum(freq_a, mag_a, "Ch A")
        analyze_spectrum(freq_b, mag_b, "Ch B")
    awg_off(handle, ps2000)
finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

print()

# ══════════════════════════════════════════════════════════════════════════
#  TEST 3: Standard sweep (as used in capture_awg_driven) — both channels
# ══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 3: Standard AWG sweep 1–100 kHz (original parameters)")
print("=" * 60)

handle, ps2000 = open_scope()
try:
    setup_channels(handle, ps2000, range_mv=500, ch_b_on=True)
    awg_sweep(handle, ps2000, AWG_CHIRP_LO, AWG_CHIRP_HI, sweep_time_s=0.5)
    ch_a, ch_b = capture_both(handle, ps2000, n_captures=8, settle_s=0.3)
    freq_a, mag_a, _ = fft_avg(ch_a)
    freq_b, mag_b, _ = fft_avg(ch_b)
    analyze_spectrum(freq_a, mag_a, "Ch A (Rods 2,3,4)", ROD1_PEAKS)
    analyze_spectrum(freq_b, mag_b, "Ch B (Rod 1)", ROD1_PEAKS)
    awg_off(handle, ps2000)
finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

print()

# ══════════════════════════════════════════════════════════════════════════
#  TEST 4: Slow sweep — 10× longer dwell, more captures
# ══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 4: Slow sweep 1–100 kHz (5 s period, 16 captures)")
print("=" * 60)

handle, ps2000 = open_scope()
try:
    setup_channels(handle, ps2000, range_mv=500, ch_b_on=True)
    awg_sweep(handle, ps2000, AWG_CHIRP_LO, AWG_CHIRP_HI, sweep_time_s=5.0)
    ch_a, ch_b = capture_both(handle, ps2000, n_captures=16, settle_s=0.5)
    freq_a, mag_a, _ = fft_avg(ch_a)
    freq_b, mag_b, _ = fft_avg(ch_b)
    analyze_spectrum(freq_a, mag_a, "Ch A (Rods 2,3,4)", ROD1_PEAKS)
    analyze_spectrum(freq_b, mag_b, "Ch B (Rod 1)", ROD1_PEAKS)
    awg_off(handle, ps2000)
finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

print()

# ══════════════════════════════════════════════════════════════════════════
#  TEST 5: Narrow sweep around Rod 1's first 3 modes
# ══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 5: Narrow sweep around Rod 1 modes (f1-500 to f3+500 Hz)")
print("=" * 60)

lo = max(500, ROD1_PEAKS[0] - 500)
hi = ROD1_PEAKS[2] + 500 if len(ROD1_PEAKS) > 2 else ROD1_PEAKS[0] + 2000

handle, ps2000 = open_scope()
try:
    setup_channels(handle, ps2000, range_mv=500, ch_b_on=True)
    awg_sweep(handle, ps2000, lo, hi, sweep_time_s=2.0)
    ch_a, ch_b = capture_both(handle, ps2000, n_captures=16, settle_s=0.5)
    freq_a, mag_a, _ = fft_avg(ch_a)
    freq_b, mag_b, _ = fft_avg(ch_b)
    print(f"  Sweep range: {lo:.0f} – {hi:.0f} Hz")
    analyze_spectrum(freq_a, mag_a, "Ch A", ROD1_PEAKS[:3])
    analyze_spectrum(freq_b, mag_b, "Ch B", ROD1_PEAKS[:3])
    awg_off(handle, ps2000)
finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

print()

# ══════════════════════════════════════════════════════════════════════════
#  TEST 6: Amplitude sweep — does more/less voltage help?
# ══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 6: Amplitude sweep (sine at Rod 1 f1)")
print("=" * 60)

amps_uvpp = [100_000, 500_000, 1_000_000, 2_000_000]  # 0.1 to 2 Vpp

handle, ps2000 = open_scope()
try:
    setup_channels(handle, ps2000, range_mv=500, ch_b_on=True)
    for uvpp in amps_uvpp:
        print(f"\n  {uvpp/1e6:.1f} Vpp sine @ {ROD1_F1:.0f} Hz:")
        awg_sine(handle, ps2000, ROD1_F1, uvpp=uvpp)
        ch_a, ch_b = capture_both(handle, ps2000, n_captures=4, settle_s=0.3)
        freq_a, mag_a, _ = fft_avg(ch_a)
        freq_b, mag_b, _ = fft_avg(ch_b)
        analyze_spectrum(freq_a, mag_a, "Ch A")
        analyze_spectrum(freq_b, mag_b, "Ch B")
    awg_off(handle, ps2000)
finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

print()

# ══════════════════════════════════════════════════════════════════════════
#  TEST 7: Higher input sensitivity (±200 mV or ±100 mV range)
# ══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 7: Higher sensitivity (±200 mV range) with sweep")
print("=" * 60)

handle, ps2000 = open_scope()
try:
    setup_channels(handle, ps2000, range_mv=200, ch_b_on=True)
    awg_sweep(handle, ps2000, AWG_CHIRP_LO, AWG_CHIRP_HI, sweep_time_s=2.0)
    ch_a, ch_b = capture_both(handle, ps2000, n_captures=8, settle_s=0.5)
    freq_a, mag_a, _ = fft_avg(ch_a)
    freq_b, mag_b, _ = fft_avg(ch_b)
    analyze_spectrum(freq_a, mag_a, "Ch A (±200mV)", ROD1_PEAKS)
    analyze_spectrum(freq_b, mag_b, "Ch B (±200mV)", ROD1_PEAKS)
    # Check for saturation
    if ch_a:
        adc_max = max(abs(c).max() for c in ch_a)
        print(f"  Ch A ADC max: {adc_max:.0f} / 32767 "
              f"({'SATURATED!' if adc_max > 30000 else 'OK'})")
    if ch_b:
        adc_max = max(abs(c).max() for c in ch_b)
        print(f"  Ch B ADC max: {adc_max:.0f} / 32767 "
              f"({'SATURATED!' if adc_max > 30000 else 'OK'})")
    awg_off(handle, ps2000)
finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

print()

# ══════════════════════════════════════════════════════════════════════════
#  TEST 8: Electrical feedthrough test — disconnect drive PZTs, AWG still on
# ══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 8: Comparison tap on Rod 1 (Ch B) — reference")
print("  This captures one tap for comparison with AWG results.")
print("=" * 60)

handle, ps2000 = open_scope()
try:
    setup_channels(handle, ps2000, range_mv=500, ch_b_on=True)
    awg_off(handle, ps2000)

    # Trigger on Ch B (Rod 1 sense) for tap
    threshold_counts = int(200 / 500 * 32767)
    ps2000.ps2000_set_trigger(
        handle, 1, threshold_counts, 0, 0, 20000  # source=Ch B, 20s timeout
    )

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
        freq_a, mag_a, _ = fft_avg(tap_a)
        freq_b, mag_b, _ = fft_avg(tap_b)
        analyze_spectrum(freq_a, mag_a, "Ch A (tap spillover)", ROD1_PEAKS)
        analyze_spectrum(freq_b, mag_b, "Ch B (Rod 1 tap)", ROD1_PEAKS)
    else:
        print("  No capture (timeout?)")

finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

print()
print("=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
print()
print("Key questions answered:")
print("  1. Is there ANY signal on Ch B when AWG drives? (Tests 2-6)")
print("  2. Does the signal scale with AWG amplitude? (Test 6)")
print("  3. Is 35 kHz peak PZT self-resonance or rod? (Test 2)")
print("  4. Does narrow sweep near known modes help? (Test 5)")
print("  5. Is the signal just below noise floor? (Test 7)")
print("  6. How does AWG SNR compare to tap SNR? (Test 3 vs 8)")
