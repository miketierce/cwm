#!/usr/bin/env python3
"""Capture a live tap on Rod 1 and compare to enrolled data."""
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
TRIGGER_MV = 200; RANGE_MV = 500; ADC_MAX = 32767

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
print(f"\r  Triggered after {time.time()-t0:.2f}s           ")

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
print(f"  Pk-pk: {volts.max()-volts.min():.0f} mV, Q1 RMS: {q1:.0f} mV -> Q4: {q4:.0f} mV, decay: {q1/q4:.1f}x")

# FFT
n_fft = n * 4
padded = np.zeros(n_fft)
padded[:n] = raw * np.hanning(n)
spectrum = np.abs(np.fft.rfft(padded))
freqs = np.fft.rfftfreq(n_fft, d=DT)
bin_hz = freqs[1] - freqs[0]
noise_floor = np.median(spectrum)

peaks, _ = find_peaks(spectrum, height=noise_floor * 10, distance=max(1, int(200/bin_hz)))
if len(peaks) == 0:
    print("NO PEAKS FOUND")
    sys.exit(1)
heights = spectrum[peaks]
top_idx = np.argsort(heights)[::-1][:20]
top_peaks = peaks[top_idx]
top_peaks = top_peaks[np.argsort(freqs[top_peaks])]

live_hz = []
for p in top_peaks:
    if 0 < p < len(spectrum) - 1:
        a, b, c = spectrum[p-1], spectrum[p], spectrum[p+1]
        d = 2*b - a - c
        delta = 0.5*(a-c)/d if d != 0 else 0
        live_hz.append(freqs[p] + delta * bin_hz)
    else:
        live_hz.append(freqs[p])
while len(live_hz) < 20:
    live_hz.append(0.0)

# Load enrolled
db = json.loads(open("data/results/lab/users.json").read())
enrolled_hz = db["rods"]["1"]["perturbed_hz"]

header = f"{'Mode':>4}  {'Enrolled Hz':>12}  {'Live Hz':>12}  {'Delta Hz':>10}  {'Delta %':>8}"
print(f"\n{header}")
print("-" * len(header))
for i in range(20):
    e = enrolled_hz[i]
    l = live_hz[i]
    if e > 0 and l > 0:
        delta = l - e
        pct = (l - e) / e * 100
        print(f"{i+1:4d}  {e:12.1f}  {l:12.1f}  {delta:+10.1f}  {pct:+7.2f}%")
    else:
        print(f"{i+1:4d}  {e:12.1f}  {l:12.1f}         —        —")

# RMS on first 10 modes
ea = np.array(enrolled_hz[:10])
la = np.array(live_hz[:10])
valid = (ea > 0) & (la > 0)
if np.any(valid):
    frac = (la[valid] - ea[valid]) / ea[valid]
    rms = np.sqrt(np.mean(frac**2)) * 100
    print(f"\nRMS (modes 1-10): {rms:.2f}%  (threshold: 2.5%)")
    print(f"Auth result: {'PASS' if rms < 2.5 else 'FAIL'}")
