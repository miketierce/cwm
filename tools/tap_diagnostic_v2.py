#!/usr/bin/env python3
"""
Tap diagnostic v2: corrected sample rate (timebase 7 = 781 kHz).
Arms trigger, waits for tap on rod, shows waveform + FFT.

Wiring: Ch A → BNC-to-alligator → PZT (red→red, black→black)
Tap the GLASS ROD body (not the PZT) with a fingernail — quick bounce.
"""
import ctypes, time, sys, os
import numpy as np

for p in [
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib",
    "/Applications/PicoScope 7 T&M.app/Contents/Resources/libps2000.dylib",
]:
    if os.path.exists(p):
        lib = ctypes.cdll.LoadLibrary(p)
        break

TIMEBASE = 7
DT = 1280e-9      # 1280 ns/sample
N = 8064
FS = 1.0 / DT     # 781250 Hz
TRIGGER_MV = 50
RANGE_MV = 500
ADC_MAX = 32767
TIMEOUT_MS = 15000

handle = lib.ps2000_open_unit()
print(f"PicoScope opened (handle {handle})")
print(f"  Timebase {TIMEBASE}: {FS/1000:.1f} kHz, {N} samples, {N*DT*1000:.1f} ms window")
print(f"  Trigger: {TRIGGER_MV} mV rising edge, {TIMEOUT_MS/1000:.0f}s timeout")
print(f"  FFT resolution (4× zeropad): {FS/N/4:.1f} Hz")
print()

lib.ps2000_set_channel(handle, 0, 1, 1, 6)
lib.ps2000_set_channel(handle, 1, 0, 1, 6)

threshold = int(TRIGGER_MV / RANGE_MV * ADC_MAX)
lib.ps2000_set_trigger(handle, 0, threshold, 0, 0, TIMEOUT_MS)

time_ms = ctypes.c_int32()
lib.ps2000_run_block(handle, N, TIMEBASE, 1, ctypes.byref(time_ms))
print(">>> TAP THE GLASS ROD with your fingernail — quick bounce-off <<<")
print(">>> Do NOT press or hold — the rod must ring freely <<<")
print()

t0 = time.time()
while lib.ps2000_ready(handle) == 0:
    elapsed = time.time() - t0
    print(f"\r  Waiting... {elapsed:.1f}s ", end="", flush=True)
    time.sleep(0.05)
    if elapsed > TIMEOUT_MS / 1000.0 + 2:
        print("\n\nTIMEOUT — no trigger. Check wiring / tap harder.")
        lib.ps2000_stop(handle)
        lib.ps2000_close_unit(handle)
        sys.exit(1)

elapsed = time.time() - t0
print(f"\r  Triggered after {elapsed:.2f}s                ")

buf_a = (ctypes.c_int16 * N)()
buf_b = (ctypes.c_int16 * N)()
overflow = ctypes.c_int16()
n = lib.ps2000_get_values(handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                           None, None, ctypes.byref(overflow), N)
lib.ps2000_stop(handle)
lib.ps2000_close_unit(handle)

raw = np.array(buf_a[:n], dtype=np.float64)
volts = raw / ADC_MAX * RANGE_MV

print(f"\n=== WAVEFORM ({n} samples, {n*DT*1000:.1f} ms) ===")
print(f"  Peak+: {volts.max():+.1f} mV   Peak-: {volts.min():+.1f} mV   Pk-pk: {volts.max()-volts.min():.1f} mV")
print(f"  RMS:   {np.sqrt(np.mean(volts**2)):.1f} mV")

# Quarter-by-quarter amplitude — shows if signal decays (ring-down) or stays flat (noise)
q = n // 4
print(f"\n  Ring-down check (RMS per quarter):")
for i in range(4):
    chunk = volts[i*q:(i+1)*q]
    print(f"    Q{i+1} ({i*q*DT*1000:.1f}-{(i+1)*q*DT*1000:.1f} ms): "
          f"RMS {np.sqrt(np.mean(chunk**2)):.1f} mV, peak {np.max(np.abs(chunk)):.1f} mV")

# FFT with correct sample rate
padded = np.zeros(n * 4)
padded[:n] = raw * np.hanning(n)
spectrum = np.abs(np.fft.rfft(padded))
freqs = np.fft.rfftfreq(len(padded), d=DT)
noise_floor = np.median(spectrum)

from scipy.signal import find_peaks
peaks, _ = find_peaks(spectrum, height=noise_floor * 5, distance=20)

print(f"\n=== FFT (4× zero-padded, {FS/n/4:.1f} Hz resolution) ===")
print(f"  Noise floor (median): {noise_floor:.0f}")

if len(peaks) > 0:
    heights = spectrum[peaks]
    top = np.argsort(heights)[::-1][:20]
    print(f"\n  Top {len(top)} peaks (SNR > 5×):")
    for i, idx in enumerate(top):
        p = peaks[idx]
        snr = spectrum[p] / noise_floor
        print(f"    #{i+1:2d}  {freqs[p]:9.1f} Hz  SNR {snr:7.1f}×")

    # Check if top peaks form a harmonic series
    top_freqs = sorted([freqs[peaks[idx]] for idx in top[:10]])
    if len(top_freqs) >= 3:
        f1_candidates = top_freqs[:3]
        print(f"\n  Harmonic check (looking for f1):")
        for f1 in f1_candidates:
            ratios = [f / f1 for f in top_freqs]
            near_int = [abs(r - round(r)) for r in ratios]
            avg_err = np.mean(near_int)
            print(f"    f1={f1:.0f} Hz → ratios: {', '.join(f'{r:.2f}' for r in ratios[:6])} "
                  f" avg harmonic err: {avg_err:.3f}")
else:
    print("  No peaks above 5× noise floor")

# Save for further analysis
np.save("data/results/lab/tap_v2_raw.npy", raw)
print(f"\nRaw data saved to data/results/lab/tap_v2_raw.npy")
print("Done.")
