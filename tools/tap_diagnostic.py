#!/usr/bin/env python3
"""
Quick diagnostic: arm scope, wait for tap, dump raw waveform stats.
Run standalone — no lab server needed.

Usage:
  python3 tools/tap_diagnostic.py

Wiring: Ch A BNC → alligator clips → PZT (red→red, black→black)
"""
import ctypes, time, sys, os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ---------- ensure DYLD_LIBRARY_PATH for macOS ----------
import platform
if platform.system() == "Darwin":
    from pathlib import Path
    _APP_PATHS = [
        "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources",
        "/Applications/PicoScope 7 T&M.app/Contents/Resources",
        "/Applications/PicoScope.app/Contents/Resources",
    ]
    current = os.environ.get("DYLD_LIBRARY_PATH", "")
    for p in _APP_PATHS:
        if Path(p).exists() and p not in current:
            os.environ["DYLD_LIBRARY_PATH"] = f"{p}:{current}" if current else p
            break

# ---------- open scope ----------
try:
    from picosdk.ps2000 import ps2000
except ImportError:
    print("ERROR: picosdk library not found. pip install picosdk")
    sys.exit(1)

TRIGGER_MV   = 200       # trigger threshold
RANGE_MV     = 500       # ±500 mV (range index 6)
TIMEOUT_MS   = 15000     # 15 s to tap
CAPTURE      = 3968      # max for ps2000 block mode
ADC_MAX      = 32767

handle = ps2000.ps2000_open_unit()
if handle <= 0:
    print(f"ERROR: ps2000_open_unit returned {handle}")
    sys.exit(1)

print(f"PicoScope opened (handle {handle})")
print(f"  Range:   ±{RANGE_MV} mV")
print(f"  Trigger: {TRIGGER_MV} mV rising edge on Ch A")
print(f"  Capture: {CAPTURE} samples @ ~1 MHz")
print()

try:
    # Channel A on, DC coupled, ±500 mV
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)

    # Rising-edge trigger
    threshold_counts = int(TRIGGER_MV / RANGE_MV * ADC_MAX)
    ps2000.ps2000_set_trigger(
        handle,
        0,                  # source = Ch A
        threshold_counts,   # threshold
        0,                  # rising
        0,                  # delay
        TIMEOUT_MS          # auto-trigger timeout
    )

    # Arm
    time_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, CAPTURE, 3, 1, ctypes.byref(time_ms))
    print(">>> Scope armed — TAP THE PZT NOW (15 s timeout) <<<")
    print()

    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        elapsed = time.time() - t0
        print(f"\r  Waiting... {elapsed:.1f}s ", end="", flush=True)
        time.sleep(0.05)
        if elapsed > (TIMEOUT_MS / 1000.0 + 2):
            print("\n\nTIMEOUT — no trigger detected. Check wiring.")
            sys.exit(1)

    elapsed = time.time() - t0
    print(f"\r  Triggered after {elapsed:.2f}s                ")
    print()

    # Read data
    buf_a = (ctypes.c_int16 * CAPTURE)()
    buf_b = (ctypes.c_int16 * CAPTURE)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), CAPTURE
    )

    if n <= 0:
        print(f"ERROR: get_values returned {n} samples")
        sys.exit(1)

    raw = np.array(buf_a[:n], dtype=np.float64)
    volts = raw / ADC_MAX * RANGE_MV  # in mV

    # ---------- waveform stats ----------
    print(f"=== RAW WAVEFORM ({n} samples, ~{n/1e6*1000:.1f} ms) ===")
    print(f"  Peak positive: {volts.max():+.1f} mV")
    print(f"  Peak negative: {volts.min():+.1f} mV")
    print(f"  Peak-to-peak:  {volts.max() - volts.min():.1f} mV")
    print(f"  RMS:           {np.sqrt(np.mean(volts**2)):.1f} mV")
    print(f"  Mean:          {volts.mean():+.2f} mV")
    print()

    # First 100 samples (around trigger)
    print("  First 20 samples (mV):")
    for i in range(0, min(20, n)):
        print(f"    [{i:4d}] {volts[i]:+7.1f} mV")
    print()

    # Check for ring-down: does amplitude decay?
    chunk_size = n // 4
    for c in range(4):
        chunk = volts[c*chunk_size:(c+1)*chunk_size]
        print(f"  Quarter {c+1} RMS: {np.sqrt(np.mean(chunk**2)):6.1f} mV  "
              f"peak: {np.max(np.abs(chunk)):6.1f} mV")
    print()

    # ---------- FFT ----------
    print("=== FFT (4× zero-padded) ===")
    padded = np.zeros(n * 4)
    padded[:n] = raw
    window = np.hanning(n)
    padded[:n] *= window
    spectrum = np.abs(np.fft.rfft(padded))
    freqs = np.fft.rfftfreq(len(padded), d=1e-6)  # 1 MHz sample rate

    # Find top 10 peaks
    from scipy.signal import find_peaks
    peaks, props = find_peaks(spectrum, height=np.max(spectrum) * 0.05, distance=20)
    if len(peaks) == 0:
        print("  No peaks found above 5% of max!")
    else:
        heights = spectrum[peaks]
        top_idx = np.argsort(heights)[::-1][:10]
        print(f"  Top {min(10, len(top_idx))} peaks:")
        noise_floor = np.median(spectrum)
        for rank, idx in enumerate(top_idx):
            p = peaks[idx]
            snr = spectrum[p] / noise_floor if noise_floor > 0 else 0
            print(f"    #{rank+1}  {freqs[p]:9.1f} Hz  magnitude {spectrum[p]:10.0f}  SNR {snr:.1f}×")
        print(f"  Noise floor (median): {noise_floor:.0f}")
    print()

    # ---------- ASCII waveform plot ----------
    print("=== WAVEFORM (ASCII, 80 cols × 20 rows) ===")
    rows = 20
    cols = 80
    # Downsample to cols points
    ds = np.interp(np.linspace(0, n-1, cols), np.arange(n), volts)
    vmin, vmax = ds.min(), ds.max()
    if vmax - vmin < 1:
        vmax = vmin + 1  # prevent div by zero
    for r in range(rows):
        threshold = vmax - (r / (rows - 1)) * (vmax - vmin)
        line = ""
        for c in range(cols):
            if abs(ds[c] - threshold) < (vmax - vmin) / (rows * 2):
                line += "█"
            elif (r == rows // 2):
                line += "─"
            else:
                line += " "
        label = f"{threshold:+6.0f}" if r % 5 == 0 else "      "
        print(f"  {label}│{line}│")
    print(f"        └{'─' * cols}┘")
    print(f"         0{'':>{cols//2-1}}~{n/1e6*1000:.1f}ms")

    # Save raw data for further analysis
    np.save("data/results/lab/tap_diagnostic_raw.npy", raw)
    print(f"\nRaw ADC data saved to data/results/lab/tap_diagnostic_raw.npy")

finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("Scope closed.")
