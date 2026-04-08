#!/usr/bin/env python3
"""
Repeat flick test 3 times to check if the same peaks appear consistently.
Arms trigger at 200 mV, waits 20s per attempt.
Between captures, re-arms automatically.
"""
import ctypes, time, os, sys
import numpy as np
from scipy.signal import find_peaks

for p in [
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib",
    "/Applications/PicoScope 7 T&M.app/Contents/Resources/libps2000.dylib",
]:
    if os.path.exists(p):
        lib = ctypes.cdll.LoadLibrary(p)
        break

TIMEBASE = 7
DT = 1280e-9
N = 8064
TRIGGER_MV = 200
RANGE_MV = 500
ADC_MAX = 32767
TIMEOUT_MS = 20000
N_RUNS = 3

handle = lib.ps2000_open_unit()
print(f"PicoScope opened (handle {handle})")
lib.ps2000_set_channel(handle, 0, 1, 1, 6)
lib.ps2000_set_channel(handle, 1, 0, 1, 6)

all_top_freqs = []

for run in range(N_RUNS):
    print(f"\n{'='*60}")
    print(f"  RUN {run+1}/{N_RUNS} — Flick the rod now!")
    print(f"{'='*60}")

    threshold = int(TRIGGER_MV / RANGE_MV * ADC_MAX)
    lib.ps2000_set_trigger(handle, 0, threshold, 0, 0, TIMEOUT_MS)
    time_ms = ctypes.c_int32()
    lib.ps2000_run_block(handle, N, TIMEBASE, 1, ctypes.byref(time_ms))

    t0 = time.time()
    while lib.ps2000_ready(handle) == 0:
        elapsed = time.time() - t0
        sys.stdout.write(f"\r  Waiting... {elapsed:.1f}s ")
        sys.stdout.flush()
        time.sleep(0.05)
        if elapsed > TIMEOUT_MS / 1000.0 + 2:
            break

    elapsed = time.time() - t0
    print(f"\r  Triggered after {elapsed:.2f}s           ")

    buf_a = (ctypes.c_int16 * N)()
    buf_b = (ctypes.c_int16 * N)()
    overflow = ctypes.c_int16()
    n = lib.ps2000_get_values(handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                               None, None, ctypes.byref(overflow), N)

    raw = np.array(buf_a[:n], dtype=np.float64)
    volts = raw / ADC_MAX * RANGE_MV

    q = n // 4
    q1_rms = np.sqrt(np.mean(volts[:q]**2))
    q4_rms = np.sqrt(np.mean(volts[3*q:]**2))
    decay_ratio = q1_rms / q4_rms if q4_rms > 0 else 0

    print(f"  Pk-pk: {volts.max()-volts.min():.0f} mV, "
          f"Q1 RMS: {q1_rms:.0f} mV → Q4 RMS: {q4_rms:.0f} mV, "
          f"decay: {decay_ratio:.1f}×")

    padded = np.zeros(n * 4)
    padded[:n] = raw * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(padded))
    freqs = np.fft.rfftfreq(len(padded), d=DT)
    noise_floor = np.median(spectrum)

    peaks, _ = find_peaks(spectrum, height=noise_floor * 10, distance=20)
    if len(peaks) > 0:
        heights = spectrum[peaks]
        top = np.argsort(heights)[::-1][:10]
        run_freqs = []
        print(f"  Top peaks (SNR > 10×):")
        for i, idx in enumerate(top):
            p = peaks[idx]
            snr = spectrum[p] / noise_floor
            print(f"    #{i+1:2d}  {freqs[p]:8.1f} Hz  SNR {snr:7.0f}×")
            run_freqs.append(freqs[p])
        all_top_freqs.append(run_freqs)
    else:
        print("  No peaks above 10× noise")
        all_top_freqs.append([])

    # Save raw
    np.save(f"data/results/lab/flick_run{run+1}_raw.npy", raw)

lib.ps2000_stop(handle)
lib.ps2000_close_unit(handle)

# ── Reproducibility analysis ──
print(f"\n{'='*60}")
print(f"  REPRODUCIBILITY ANALYSIS")
print(f"{'='*60}")

if len(all_top_freqs) >= 2 and all(len(f) > 0 for f in all_top_freqs):
    # For each top peak in run 1, find closest match in runs 2-3
    ref = all_top_freqs[0]
    print(f"\n  Run 1 peaks vs other runs (closest match):")
    print(f"  {'Run1 Hz':>10}  {'Run2 Hz':>10}  {'Δ2 Hz':>8}  {'Run3 Hz':>10}  {'Δ3 Hz':>8}")
    for f1 in ref[:8]:
        row = f"  {f1:>10.1f}"
        for other in all_top_freqs[1:]:
            if len(other) > 0:
                closest = min(other, key=lambda x: abs(x - f1))
                delta = closest - f1
                row += f"  {closest:>10.1f}  {delta:>+8.1f}"
            else:
                row += f"  {'N/A':>10}  {'N/A':>8}"
        print(row)

    # Overall: count how many peaks match within 100 Hz
    match_threshold = 100  # Hz
    total_matches = 0
    total_comparisons = 0
    for f1 in ref[:8]:
        for other in all_top_freqs[1:]:
            total_comparisons += 1
            if any(abs(f - f1) < match_threshold for f in other):
                total_matches += 1
    print(f"\n  Peaks matching within ±{match_threshold} Hz: {total_matches}/{total_comparisons}")
    print(f"  {'REPRODUCIBLE ✓' if total_matches > total_comparisons * 0.7 else 'NOT REPRODUCIBLE ✗'}")

print("\nDone.")
