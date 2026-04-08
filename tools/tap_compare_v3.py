#!/usr/bin/env python3
"""Capture a live tap on Rod 1 and score against all rods using reference search."""
import ctypes, time, os, sys, json
import numpy as np
from scipy.signal import find_peaks

for p in [
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib",
    "/Applications/PicoScope 7 T&M.app/Contents/Resources/libps2000.dylib",
]:
    if os.path.exists(p):
        lib = ctypes.cdll.LoadLibrary(p)
        break

TIMEBASE = 7; DT = 1280e-9; N = 8064
TRIGGER_MV = 200; RANGE_MV = 500; ADC_MAX = 32767; SAMPLE_RATE = 781250

handle = lib.ps2000_open_unit()
print(f"Scope open. Trigger: {TRIGGER_MV} mV, 20s timeout")
lib.ps2000_set_channel(handle, 0, 1, 1, 6)
lib.ps2000_set_channel(handle, 1, 0, 1, 6)
threshold = int(TRIGGER_MV / RANGE_MV * ADC_MAX)
lib.ps2000_set_trigger(handle, 0, threshold, 0, 0, 20000)
time_ms = ctypes.c_int32()
lib.ps2000_run_block(handle, N, TIMEBASE, 1, ctypes.byref(time_ms))

print()
print(">>> FLICK ROD 1 with fingernail — quick bounce <<<")
print()

t0 = time.time()
while lib.ps2000_ready(handle) == 0:
    sys.stdout.write(f"\r  Waiting... {time.time()-t0:.1f}s ")
    sys.stdout.flush()
    time.sleep(0.05)
    if time.time() - t0 > 22:
        break
elapsed = time.time() - t0
print(f"\r  Triggered after {elapsed:.2f}s           ")

buf_a = (ctypes.c_int16 * N)()
buf_b = (ctypes.c_int16 * N)()
overflow = ctypes.c_int16()
n = lib.ps2000_get_values(handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                           None, None, ctypes.byref(overflow), N)
lib.ps2000_stop(handle)
lib.ps2000_close_unit(handle)

raw = np.array(buf_a[:n], dtype=np.float64)
volts = raw / ADC_MAX * RANGE_MV
q = n // 4
q1 = np.sqrt(np.mean(volts[:q]**2))
q4 = np.sqrt(np.mean(volts[3*q:]**2))
print(f"  Pk-pk: {volts.max()-volts.min():.0f} mV, Q1: {q1:.0f} mV -> Q4: {q4:.0f} mV, decay: {q1/max(q4,0.1):.1f}x")

# FFT (same as cwm_picoscope)
n_fft = n * 4
freq_axis = np.fft.rfftfreq(n_fft, d=1.0 / SAMPLE_RATE)
bin_hz = freq_axis[1] - freq_axis[0]
windowed = raw * np.hanning(n)
padded = np.zeros(n_fft)
padded[:n] = windowed
magnitude = np.abs(np.fft.rfft(padded))
noise_floor = np.median(magnitude)

print(f"  FFT: {n_fft} pts, {bin_hz:.1f} Hz/bin, noise floor: {noise_floor:.0f}")

# Load enrolled data
db = json.loads(open("data/results/lab/users.json").read())

# Score each rod: search ±5% around each enrolled peak
WINDOW_FRAC = 0.05
N_AUTH_MODES = 10
MIN_PEAK_HEIGHT = noise_floor * 3.0

def score_rod(enrolled_hz):
    enr = np.array(enrolled_hz, dtype=float)
    enr_valid = enr[enr > 0][:N_AUTH_MODES]
    results = []
    for ef in enr_valid:
        window = ef * WINDOW_FRAC
        mask = (freq_axis >= ef - window) & (freq_axis <= ef + window)
        if np.any(mask):
            idx_in = np.where(mask)[0]
            best = idx_in[np.argmax(magnitude[mask])]
            peak_mag = magnitude[best]
            # Parabolic interpolation
            if 0 < best < len(magnitude) - 1:
                a, b, c = magnitude[best-1], magnitude[best], magnitude[best+1]
                d = 2*b - a - c
                delta = 0.5*(a-c)/d if d != 0 else 0
                found_f = freq_axis[best] + delta * bin_hz
            else:
                found_f = freq_axis[best]
            frac = abs(found_f - ef) / ef
            is_peak = peak_mag >= MIN_PEAK_HEIGHT
            results.append((ef, found_f, frac, peak_mag / noise_floor, is_peak))
        else:
            results.append((ef, 0, 1.0, 0, False))
    return results

print(f"\n{'='*70}")
for rod_key in sorted(db["rods"].keys()):
    rod = db["rods"][rod_key]
    if not rod.get("enrolled"):
        continue
    results = score_rod(rod["perturbed_hz"])
    matched = [(e, l, f, s, p) for e, l, f, s, p in results if p and f < WINDOW_FRAC]

    if len(matched) >= 3:
        fracs = np.array([f for _, _, f, _, _ in matched])
        rms = np.sqrt(np.mean(fracs**2)) * 100
    else:
        rms = float("inf")

    tag = " <-- BEST" if rms < 5 else ""
    print(f"\n  Rod {rod_key}: {len(matched)}/{len(results)} peaks matched, RMS: {rms:.2f}%{tag}")
    for ef, lf, frac, snr, is_peak in results:
        status = "HIT" if (is_peak and frac < WINDOW_FRAC) else "miss"
        print(f"    enrolled {ef:8.1f} -> found {lf:8.1f}  ({frac*100:5.2f}%)  SNR {snr:5.0f}x  {status}")

print(f"\n{'='*70}")
print("Auth threshold: 2.5% RMS")
