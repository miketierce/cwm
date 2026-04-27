#!/usr/bin/env python3
"""
Eigenmode-based ringdown test v2.
Uses manual peak finding from ratio spectrum instead of scipy find_peaks.
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
    """Average raw waveforms first, then compute spectrum (coherent averaging)."""
    frames = []
    for _ in range(n):
        frames.append(capture())
    avg_wave = np.mean(frames, axis=0)
    return spectrum(avg_wave)


# ──────────────────────────────────────────────
# PHASE 1: Eigenmode discovery
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

# Compute ratio, filter to > 500 Hz (skip DC/low-freq artifacts)
ratio = np.where(mag_off > 10, mag_on / mag_off, 1.0)

# Find top eigenmode bins: ratio > 5, at least 500 Hz apart
# Manual peak selection: sort by ratio, greedily pick if not too close
min_freq = 500  # Hz, skip DC area
min_sep = 500   # Hz between selected modes
candidates = np.where((ratio > 3.0) & (freq > min_freq))[0]
candidates = candidates[np.argsort(ratio[candidates])[::-1]]

selected = []
for idx in candidates:
    f = freq[idx]
    too_close = False
    for si in selected:
        if abs(freq[si] - f) < min_sep:
            too_close = True
            break
    if not too_close:
        selected.append(idx)
    if len(selected) >= 15:
        break

selected.sort(key=lambda i: ratio[i], reverse=True)

print(f"\nTop {len(selected)} eigenmodes excited by DDS#1 @29300 Hz:")
print(f"{'Freq (Hz)':>12} {'Off':>8} {'On':>8} {'Ratio':>8}")
print("-" * 44)
for idx in selected:
    print(f"{freq[idx]:>12.0f} {mag_off[idx]:>8.0f} {mag_on[idx]:>8.0f} {ratio[idx]:>8.1f}x")

top10_idx = selected[:10]

# ──────────────────────────────────────────────
# PHASE 2: Single-capture SNR at eigenmodes
# ──────────────────────────────────────────────
print(f"\n=== PHASE 2: Single-capture SNR at top {len(top10_idx)} eigenmodes ===")

dds_cmd('F1:29300')
time.sleep(0.5)
on_features = []
for _ in range(30):
    _, m = spectrum(capture())
    on_features.append([m[i] for i in top10_idx])
on_features = np.array(on_features)

dds_cmd('Foff')
time.sleep(0.3)
off_features = []
for _ in range(30):
    _, m = spectrum(capture())
    off_features.append([m[i] for i in top10_idx])
off_features = np.array(off_features)

print(f"\n{'Freq (Hz)':>12} {'ON mean':>10} {'ON std':>10} {'OFF mean':>10} "
      f"{'OFF std':>10} {'SNR':>8} {'Sep σ':>8}")
print("-" * 80)
for i, idx in enumerate(top10_idx):
    on_m, on_s = on_features[:, i].mean(), on_features[:, i].std()
    off_m, off_s = off_features[:, i].mean(), off_features[:, i].std()
    snr_val = on_m / max(off_m, 1)
    pooled_std = np.sqrt((on_s**2 + off_s**2) / 2)
    sep = (on_m - off_m) / max(pooled_std, 1)
    print(f"{freq[idx]:>12.0f} {on_m:>10.0f} {on_s:>10.0f} {off_m:>10.0f} "
          f"{off_s:>10.0f} {snr_val:>8.1f}x {sep:>8.1f}σ")

# Composite
on_sum = on_features.sum(axis=1)
off_sum = off_features.sum(axis=1)
pooled = np.sqrt((on_sum.std()**2 + off_sum.std()**2) / 2)
sep_sum = (on_sum.mean() - off_sum.mean()) / max(pooled, 1)
print(f"\n  Composite (sum of {len(top10_idx)}): ON={on_sum.mean():.0f}±{on_sum.std():.0f}, "
      f"OFF={off_sum.mean():.0f}±{off_sum.std():.0f}, sep={sep_sum:.1f}σ")

# ──────────────────────────────────────────────
# PHASE 3: Ringdown at eigenmodes
# ──────────────────────────────────────────────
print("\n=== PHASE 3: Eigenmode ringdown after DDS-off ===")

# Steady-state baseline
print("Steady-state (DDS on, 20-avg)...")
dds_cmd('F1:29300')
time.sleep(0.5)
bl = []
for _ in range(20):
    _, m = spectrum(capture())
    bl.append([m[i] for i in top10_idx])
baseline_mean = np.mean(bl, axis=0)
baseline_composite = baseline_mean.sum()

# Ringdown: turn off and capture immediately
print("Capturing ringdown (30 frames after DDS-off)...")
dds_cmd('Foff')
t0 = time.time()

rd_times = []
rd_features = []
for _ in range(30):
    _, m = spectrum(capture())
    rd_times.append(time.time() - t0)
    rd_features.append([m[i] for i in top10_idx])
rd_features = np.array(rd_features)
rd_times = np.array(rd_times)

# Late noise baseline
time.sleep(0.5)
noise_bl = []
for _ in range(20):
    _, m = spectrum(capture())
    noise_bl.append([m[i] for i in top10_idx])
noise_mean = np.mean(noise_bl, axis=0)
noise_composite = noise_mean.sum()

print(f"\n  Baseline composite: {baseline_composite:.0f}")
print(f"  Noise composite:   {noise_composite:.0f}")
print(f"  Baseline/Noise:    {baseline_composite/max(noise_composite,1):.1f}x")

print(f"\n{'Frame':>6} {'Time(ms)':>10} {'Composite':>12} {'%baseline':>10} {'%noise':>10}")
print("-" * 55)
for i in range(min(25, len(rd_times))):
    comp = rd_features[i].sum()
    pct_bl = comp / max(baseline_composite, 1) * 100
    pct_n = comp / max(noise_composite, 1) * 100
    marker = " <<<" if pct_n > 120 else ""
    print(f"{i:>6} {rd_times[i]*1000:>10.1f} {comp:>12.0f} {pct_bl:>9.1f}% {pct_n:>9.1f}%{marker}")

# How many frames above 1.2× noise?
above = np.sum(rd_features.sum(axis=1) > noise_composite * 1.2)
print(f"\n  Frames > 1.2× noise: {above}/{len(rd_times)}")
if above > 0:
    last_above = np.where(rd_features.sum(axis=1) > noise_composite * 1.2)[0][-1]
    print(f"  Last frame above threshold: #{last_above} at {rd_times[last_above]*1000:.1f} ms")

# ──────────────────────────────────────────────
# PHASE 4: Different DDS freqs → different patterns
# ──────────────────────────────────────────────
print("\n=== PHASE 4: Eigenmode pattern vs drive frequency ===")
drive_freqs = [10000, 20000, 29300, 40000, 50000, 60000]
for df in drive_freqs:
    dds_cmd(f'F1:{df}')
    time.sleep(0.5)
    _, mag = avg_spectrum(10)
    r = np.where(mag_off > 10, mag / mag_off, 1.0)
    # Top 5 by ratio
    cands = np.where((r > 3.0) & (freq > 500))[0]
    cands = cands[np.argsort(r[cands])[::-1]]
    top5 = []
    for c in cands:
        close = False
        for t in top5:
            if abs(freq[c] - freq[t]) < 500:
                close = True
                break
        if not close:
            top5.append(c)
        if len(top5) >= 5:
            break
    modes_str = ", ".join(f"{freq[i]/1000:.1f}k({r[i]:.0f}×)" for i in top5)
    print(f"  DDS @{df:>5} Hz → {modes_str}")

dds_cmd('Foff')

# Cleanup
dds.close()
mux.write(b'0\n'); mux.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("\nDone.")
