#!/usr/bin/env python3
"""
Targeted DDS path diagnostic.
Tests:
1. DDS response verification (is Arduino setting frequency?)
2. Full-spectrum sweep to find if DDS energy appears at ANY frequency
3. RMS comparison: DDS on vs off (broadband check)
4. DDS#1 only vs DDS#2 only vs both (isolation check)
5. Multiple receiver channels with DDS on
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

ps.ps2000_set_channel(handle, 0, 1, 1, 7)  # Ch A on, DC, ±5V
ps.ps2000_set_channel(handle, 1, 0, 1, 7)  # Ch B off
# AWG off
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


def capture(n_avg=1):
    frames = []
    for _ in range(n_avg):
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
            continue
        ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                             ctypes.byref(ov), N_SAMPLES)
        frames.append(np.array(buf, dtype=np.float64))
    if not frames:
        return np.zeros(N_SAMPLES)
    return np.mean(frames, axis=0)


def full_spectrum(data):
    d = data - np.mean(data)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    mag = np.abs(np.fft.rfft(w, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=DT)
    return freq, mag


# ── Test 1: DDS serial verification ──
print("\n=== TEST 1: DDS command verification ===")
print(f"  D? → {dds_cmd('D?')}")
print(f"  F1:29300 → {dds_cmd('F1:29300')}")
print(f"  D? → {dds_cmd('D?')}")
print(f"  F1:off → {dds_cmd('F1:off')}")
print(f"  F2:30000 → {dds_cmd('F2:30000')}")
print(f"  D? → {dds_cmd('D?')}")
dds_cmd('Foff')

# ── Test 2: Broadband RMS comparison ──
print("\n=== TEST 2: Broadband RMS (DDS on vs off) ===")
time.sleep(0.3)
d_off = capture(10)
rms_off = np.sqrt(np.mean((d_off - np.mean(d_off))**2))
print(f"  All off: RMS={rms_off:.1f}, pk={d_off.max():.0f}, min={d_off.min():.0f}")

dds_cmd('F1:29300')
time.sleep(0.5)
d_on1 = capture(10)
rms_on1 = np.sqrt(np.mean((d_on1 - np.mean(d_on1))**2))
print(f"  DDS#1 @29300: RMS={rms_on1:.1f}, pk={d_on1.max():.0f}, min={d_on1.min():.0f}")
print(f"  RMS ratio: {rms_on1/rms_off:.2f}x")

dds_cmd('Foff')
dds_cmd('F2:30000')
time.sleep(0.5)
d_on2 = capture(10)
rms_on2 = np.sqrt(np.mean((d_on2 - np.mean(d_on2))**2))
print(f"  DDS#2 @30000: RMS={rms_on2:.1f}, pk={d_on2.max():.0f}, min={d_on2.min():.0f}")
print(f"  RMS ratio: {rms_on2/rms_off:.2f}x")

dds_cmd('F1:29300')  # both on
time.sleep(0.5)
d_both = capture(10)
rms_both = np.sqrt(np.mean((d_both - np.mean(d_both))**2))
print(f"  Both DDS on: RMS={rms_both:.1f}, pk={d_both.max():.0f}, min={d_both.min():.0f}")
print(f"  RMS ratio: {rms_both/rms_off:.2f}x")

dds_cmd('Foff')

# ── Test 3: Full spectrum — find where DDS energy goes ──
print("\n=== TEST 3: Full spectrum comparison ===")
time.sleep(0.3)
freq, mag_off = full_spectrum(capture(20))
dds_cmd('F1:29300')
time.sleep(0.5)
_, mag_on = full_spectrum(capture(20))
dds_cmd('Foff')

# Find bins where DDS-on exceeds DDS-off by most
diff = mag_on - mag_off
ratio = np.where(mag_off > 10, mag_on / mag_off, 1.0)
top_diff_idx = np.argsort(diff)[-10:][::-1]
print("  Top 10 bins where DDS#1 on > off (by absolute difference):")
for i in top_diff_idx:
    print(f"    {freq[i]:.0f} Hz: off={mag_off[i]:.0f}, on={mag_on[i]:.0f}, "
          f"diff={diff[i]:.0f}, ratio={ratio[i]:.2f}x")

top_rat_idx = np.argsort(ratio)[-10:][::-1]
print("  Top 10 bins by ratio (DDS on / off):")
for i in top_rat_idx:
    if freq[i] > 100:  # skip DC
        print(f"    {freq[i]:.0f} Hz: off={mag_off[i]:.0f}, on={mag_on[i]:.0f}, "
              f"ratio={ratio[i]:.2f}x")

# Specific check around 29300 Hz
bin29 = np.argmin(np.abs(freq - 29300))
print(f"\n  At 29300 Hz (bin {bin29}): off={mag_off[bin29]:.0f}, on={mag_on[bin29]:.0f}, "
      f"ratio={ratio[bin29]:.2f}x")

# Check for energy at harmonics
for h in [1, 2, 3, 4]:
    target = 29300 * h
    bidx = np.argmin(np.abs(freq - target))
    print(f"  At {target} Hz (harmonic {h}): off={mag_off[bidx]:.0f}, "
          f"on={mag_on[bidx]:.0f}, ratio={ratio[bidx]:.2f}x")

# ── Test 4: Lower frequencies (better coupled?) ──
print("\n=== TEST 4: DDS#1 at lower frequencies ===")
for f_test in [1000, 3000, 5000, 10000, 15000, 20000, 25000, 29300]:
    dds_cmd(f'F1:{f_test}')
    time.sleep(0.3)
    d = capture(10)
    d = d - np.mean(d)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    fft_c = np.abs(np.fft.rfft(w, n=nfft))
    fa = np.fft.rfftfreq(nfft, d=DT)
    bh = fa[1] - fa[0]
    tb = int(round(f_test / bh))
    lo, hi = max(0, tb - 5), min(len(fft_c) - 1, tb + 5)
    pk_val = np.max(fft_c[lo:hi + 1])
    pk_freq = fa[lo + np.argmax(fft_c[lo:hi + 1])]
    rms_d = np.sqrt(np.mean(d**2))
    print(f"  {f_test:>6} Hz: peak={pk_val:.0f} @{pk_freq:.0f}Hz, RMS={rms_d:.1f}")

dds_cmd('Foff')

# ── Test 5: AWG comparison at same amplitude ──
print("\n=== TEST 5: AWG at 600mV (~DDS level) for comparison ===")
time.sleep(0.3)
# 600mVpp = 300000 uV
ps.ps2000_set_sig_gen_built_in(handle, 0, 300000, 0,
    ctypes.c_float(29300.0), ctypes.c_float(29300.0),
    ctypes.c_float(0.0), ctypes.c_float(0.0), 0, 0)
time.sleep(0.5)
d = capture(10)
_, mag_awg = full_spectrum(d)
bidx = np.argmin(np.abs(freq - 29300))
rms_awg = np.sqrt(np.mean((d - np.mean(d))**2))
print(f"  AWG 600mVpp @29300Hz: peak={mag_awg[bidx]:.0f}, RMS={rms_awg:.1f}")
print(f"  vs DDS#1 @29300Hz:    peak={mag_on[bidx]:.0f}, RMS={rms_on1:.1f}")
print(f"  AWG/DDS ratio: {mag_awg[bidx]/max(mag_on[bidx],1):.1f}x")

# ── Test 6: All mux channels, 20-avg, DDS#1 on ──
print("\n=== TEST 6: All mux channels (DDS#1 @29300, 20-avg) ===")
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
dds_cmd('F1:29300')
time.sleep(0.3)
for ch in range(1, 9):
    mux.write(f'{ch}\n'.encode())
    time.sleep(0.15)
    mux.readline()
    time.sleep(0.1)
    d = capture(20)
    d = d - np.mean(d)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    fft_c = np.abs(np.fft.rfft(w, n=nfft))
    fa = np.fft.rfftfreq(nfft, d=DT)
    bh = fa[1] - fa[0]
    tb = int(round(29300 / bh))
    lo, hi = max(0, tb - 5), min(len(fft_c) - 1, tb + 5)
    pk_val = np.max(fft_c[lo:hi + 1])
    rms_d = np.sqrt(np.mean(d**2))
    print(f"  Ch {ch}: @29300Hz={pk_val:.0f}, RMS={rms_d:.1f}")

# Cleanup
dds_cmd('Foff')
mux.write(b'0\n'); mux.close()
dds.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("\nDone.")
