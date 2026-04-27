#!/usr/bin/env python3
"""
Eigenmode-based ringdown test.
The DDS excites glass eigenmodes, not the drive frequency.
We detect ringdown at the strongest eigenmode frequencies.
"""
import ctypes, numpy as np, time, serial, sys, os

ps = ctypes.CDLL("/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
ps.ps2000_set_sig_gen_built_in.argtypes = [
    ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_int32, ctypes.c_int32]

DT = 1280e-9
TIMEBASE = 7
N_SAMPLES = 8064

for h in range(1, 5):
    ps.ps2000_close_unit(h)
time.sleep(0.5)

handle = ps.ps2000_open_unit()
print(f"PicoScope handle: {handle}")
if handle <= 0:
    sys.exit(1)

ps.ps2000_set_channel(handle, 0, 1, 1, 7)
ps.ps2000_set_channel(handle, 1, 0, 1, 7)
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
time.sleep(2)
mux.reset_input_buffer()
mux.write(b'5\n'); time.sleep(0.05)
print(f"Mux: {mux.readline().decode().strip()}")

dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
time.sleep(2)
dds.reset_input_buffer()


def dds_cmd(cmd):
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.01)
    return dds.readline().decode().strip()


def capture():
    buf = (ctypes.c_int16 * N_SAMPLES)()
    ov = ctypes.c_int16(0)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    ms = ctypes.c_int32(0)
    ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(ms))
    for _ in range(5000):
        if ps.ps2000_ready(handle):
            break
        time.sleep(0.001)
    else:
        ps.ps2000_stop(handle)
        return np.zeros(N_SAMPLES)
    ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                         ctypes.byref(ov), N_SAMPLES)
    return np.array(buf, dtype=np.float64)


def spectrum(data):
    d = data - np.mean(data)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    mag = np.abs(np.fft.rfft(w, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=DT)
    return freq, mag


def avg_spectrum(n=20):
    mags = []
    for _ in range(n):
        f, m = spectrum(capture())
        mags.append(m)
    return f, np.mean(mags, axis=0)


# ──────────────────────────────────────────────
# PHASE 1: Identify strongest eigenmodes
# ──────────────────────────────────────────────
print("\n=== PHASE 1: Eigenmode discovery ===")
print("Measuring noise floor (20-avg)...")
dds_cmd('Foff')
time.sleep(0.3)
freq, mag_off = avg_spectrum(20)

print("Measuring DDS#1 @29300 Hz (20-avg)...")
dds_cmd('F1:29300')
time.sleep(0.5)
_, mag_on = avg_spectrum(20)
dds_cmd('Foff')

# Find eigenmodes: bins where DDS-on significantly exceeds DDS-off
ratio = np.where(mag_off > 1, mag_on / mag_off, 1.0)
snr = mag_on / (mag_off + 1)  # add 1 to avoid div-by-zero

# Find peaks in the ratio spectrum (local maxima with high ratio)
from scipy.signal import find_peaks
peaks_idx, props = find_peaks(ratio, height=5.0, distance=20, prominence=2.0)

# Sort by ratio
sorted_peaks = peaks_idx[np.argsort(ratio[peaks_idx])[::-1]]
top_modes = sorted_peaks[:20]

print(f"\nTop {len(top_modes)} eigenmodes excited by DDS#1 @29300 Hz:")
print(f"{'Freq (Hz)':>12} {'Off':>8} {'On':>8} {'Ratio':>8} {'SNR':>8}")
print("-" * 52)
eigenmode_freqs = []
for idx in top_modes:
    f = freq[idx]
    eigenmode_freqs.append(f)
    print(f"{f:>12.0f} {mag_off[idx]:>8.0f} {mag_on[idx]:>8.0f} "
          f"{ratio[idx]:>8.1f}x {snr[idx]:>8.1f}")

# ──────────────────────────────────────────────
# PHASE 2: Single-capture SNR at eigenmodes
# ──────────────────────────────────────────────
print("\n=== PHASE 2: Single-capture SNR at top eigenmodes ===")
# Use the top 10 eigenmodes as feature vector
top10 = eigenmode_freqs[:10]
top10_idx = [np.argmin(np.abs(freq - f)) for f in top10]

# 30 single captures with DDS ON
dds_cmd('F1:29300')
time.sleep(0.5)
on_features = []
for _ in range(30):
    _, m = spectrum(capture())
    on_features.append([m[i] for i in top10_idx])
on_features = np.array(on_features)

# 30 single captures with DDS OFF
dds_cmd('Foff')
time.sleep(0.3)
off_features = []
for _ in range(30):
    _, m = spectrum(capture())
    off_features.append([m[i] for i in top10_idx])
off_features = np.array(off_features)

print(f"\n{'Freq (Hz)':>12} {'ON mean':>10} {'ON std':>10} {'OFF mean':>10} "
      f"{'OFF std':>10} {'SNR':>8} {'Sep':>8}")
print("-" * 80)
for i, f in enumerate(top10):
    on_m, on_s = on_features[:, i].mean(), on_features[:, i].std()
    off_m, off_s = off_features[:, i].mean(), off_features[:, i].std()
    snr_val = on_m / (off_m + 1)
    # Separation = (mean_on - mean_off) / pooled_std
    pooled_std = np.sqrt((on_s**2 + off_s**2) / 2)
    sep = (on_m - off_m) / (pooled_std + 1)
    print(f"{f:>12.0f} {on_m:>10.0f} {on_s:>10.0f} {off_m:>10.0f} "
          f"{off_s:>10.0f} {snr_val:>8.1f}x {sep:>8.1f}σ")

# Composite feature: sum of top 10
on_sum = on_features.sum(axis=1)
off_sum = off_features.sum(axis=1)
sep_sum = (on_sum.mean() - off_sum.mean()) / np.sqrt((on_sum.std()**2 + off_sum.std()**2) / 2)
print(f"\n  Composite (sum of top 10): ON={on_sum.mean():.0f}±{on_sum.std():.0f}, "
      f"OFF={off_sum.mean():.0f}±{off_sum.std():.0f}, sep={sep_sum:.1f}σ")

# ──────────────────────────────────────────────
# PHASE 3: Ringdown at eigenmodes
# ──────────────────────────────────────────────
print("\n=== PHASE 3: Eigenmode ringdown after DDS-off ===")
print("Steady-state baseline (DDS on, 20-avg)...")
dds_cmd('F1:29300')
time.sleep(0.5)
baseline_features = []
for _ in range(20):
    _, m = spectrum(capture())
    baseline_features.append([m[i] for i in top10_idx])
baseline_mean = np.mean(baseline_features, axis=0)

print("Capturing ringdown frames after DDS-off...")
# Turn DDS off and immediately start capturing
dds_cmd('Foff')
t_start = time.time()

ringdown_times = []
ringdown_features = []
for frame in range(30):
    _, m = spectrum(capture())
    t = time.time() - t_start
    ringdown_times.append(t)
    ringdown_features.append([m[i] for i in top10_idx])

ringdown_features = np.array(ringdown_features)
ringdown_times = np.array(ringdown_times)

# Also capture noise baseline
time.sleep(0.5)
noise_features = []
for _ in range(20):
    _, m = spectrum(capture())
    noise_features.append([m[i] for i in top10_idx])
noise_mean = np.mean(noise_features, axis=0)

print(f"\n{'Frame':>6} {'Time(ms)':>10}", end="")
for i, f in enumerate(top10[:5]):
    print(f" {f/1000:>7.1f}k", end="")
print(f" {'Composite':>12} {'%baseline':>10}")
print("-" * 90)

for frame in range(min(20, len(ringdown_times))):
    t_ms = ringdown_times[frame] * 1000
    print(f"{frame:>6} {t_ms:>10.1f}", end="")
    for i in range(min(5, len(top10))):
        val = ringdown_features[frame, i]
        print(f" {val:>7.0f}", end="")
    composite = ringdown_features[frame].sum()
    pct = composite / baseline_mean.sum() * 100
    print(f" {composite:>12.0f} {pct:>9.1f}%")

# Noise floor comparison
noise_composite = noise_mean.sum()
baseline_composite = baseline_mean.sum()
print(f"\n  Baseline composite: {baseline_composite:.0f}")
print(f"  Noise composite:   {noise_composite:.0f}")
print(f"  Noise/Baseline:    {noise_composite/baseline_composite*100:.1f}%")

# Find how many frames stay above noise
threshold = noise_composite * 1.5  # 50% above noise
above = np.sum(ringdown_features.sum(axis=1) > threshold)
print(f"  Frames above 1.5× noise: {above}/{len(ringdown_times)}")

# ──────────────────────────────────────────────
# PHASE 4: Different drive frequencies → different eigenmodes?
# ──────────────────────────────────────────────
print("\n=== PHASE 4: Different DDS frequencies excite different eigenmodes ===")
drive_freqs = [10000, 20000, 29300, 35000, 45000, 60000]
all_patterns = {}

for df in drive_freqs:
    dds_cmd(f'F1:{df}')
    time.sleep(0.5)
    _, mag = avg_spectrum(10)
    r = np.where(mag_off > 1, mag / mag_off, 1.0)
    # Top 5 eigenmodes for this drive
    p_idx, _ = find_peaks(r, height=3.0, distance=20)
    if len(p_idx) > 0:
        p_sorted = p_idx[np.argsort(r[p_idx])[::-1]][:5]
        modes = [(freq[i], r[i]) for i in p_sorted]
    else:
        modes = []
    all_patterns[df] = modes
    top_str = ", ".join(f"{f/1000:.1f}k({rat:.0f}×)" for f, rat in modes[:5])
    print(f"  DDS @{df:>5} Hz → {top_str}")

dds_cmd('Foff')

# Cleanup
dds.close()
mux.write(b'0\n'); mux.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("\nDone.")
