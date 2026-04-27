#!/usr/bin/env python3
"""
Test effect of PicoScope voltage range on DDS SNR.
The 2204A has 8-bit ADC. At ±2V (range 7), 1 step = 15.6 mV.
Our DDS signal is ~2 mV — below quantization!
Try lower ranges to see if eigenmode SNR improves.
"""
import ctypes, numpy as np, time, serial, sys

ps = ctypes.CDLL("/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
ps.ps2000_set_sig_gen_built_in.argtypes = [
    ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_int32, ctypes.c_int32]

DT = 1280e-9
TIMEBASE = 7
N_SAMPLES = 8064

# ps2000 range enum:
# 0=±10mV, 1=±20mV, 2=±50mV, 3=±100mV, 4=±200mV, 5=±500mV, 6=±1V, 7=±2V, 8=±5V
RANGE_NAMES = {0: "±10mV", 1: "±20mV", 2: "±50mV", 3: "±100mV",
               4: "±200mV", 5: "±500mV", 6: "±1V", 7: "±2V", 8: "±5V"}
RANGE_MV = {0: 10, 1: 20, 2: 50, 3: 100, 4: 200, 5: 500, 6: 1000, 7: 2000, 8: 5000}

for h in range(1, 5):
    ps.ps2000_close_unit(h)
time.sleep(0.5)

handle = ps.ps2000_open_unit()
print(f"PicoScope handle: {handle}")
if handle <= 0:
    sys.exit(1)

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


def capture(ch_range):
    buf = (ctypes.c_int16 * N_SAMPLES)()
    ov = ctypes.c_int16(0)
    ps.ps2000_set_channel(handle, 0, 1, 1, ch_range)
    ps.ps2000_set_channel(handle, 1, 0, 1, ch_range)
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


def find_eigenmodes(freq, mag_on, mag_off, min_ratio=3.0, n_modes=10):
    ratio = np.where(mag_off > 10, mag_on / mag_off, 1.0)
    candidates = np.where((ratio > min_ratio) & (freq > 500))[0]
    candidates = candidates[np.argsort(ratio[candidates])[::-1]]
    selected = []
    for idx in candidates:
        too_close = any(abs(freq[si] - freq[idx]) < 500 for si in selected)
        if not too_close:
            selected.append(idx)
        if len(selected) >= n_modes:
            break
    return selected, ratio


# Test each range
RANGES_TO_TEST = [7, 6, 5, 4, 3, 2]  # ±2V down to ±50mV

print(f"\n{'='*80}")
print(f"Testing PicoScope voltage ranges for DDS eigenmode detection")
print(f"{'='*80}")

for rng in RANGES_TO_TEST:
    print(f"\n--- Range {rng}: {RANGE_NAMES[rng]} (1 ADC step = {RANGE_MV[rng]/128:.2f} mV) ---")

    # Noise floor (DDS off, 10-avg coherent)
    dds_cmd('Foff')
    time.sleep(0.2)
    off_waves = [capture(rng) for _ in range(10)]
    off_avg = np.mean(off_waves, axis=0)
    freq, mag_off = spectrum(off_avg)
    rms_off = np.sqrt(np.mean((off_avg - np.mean(off_avg))**2))
    print(f"  Noise: RMS={rms_off:.1f} counts, peak=[{off_avg.min():.0f}, {off_avg.max():.0f}]")

    # Check for clipping
    if off_avg.max() > 30000 or off_avg.min() < -30000:
        print(f"  *** CLIPPING — skipping this range ***")
        continue

    # DDS on (10-avg coherent)
    dds_cmd('F1:29300')
    time.sleep(0.3)
    on_waves = [capture(rng) for _ in range(10)]
    on_avg = np.mean(on_waves, axis=0)
    _, mag_on = spectrum(on_avg)
    rms_on = np.sqrt(np.mean((on_avg - np.mean(on_avg))**2))
    print(f"  DDS on: RMS={rms_on:.1f} counts, peak=[{on_avg.min():.0f}, {on_avg.max():.0f}]")

    if on_avg.max() > 30000 or on_avg.min() < -30000:
        print(f"  *** CLIPPING with DDS — skipping ***")
        dds_cmd('Foff')
        continue

    # Find eigenmodes
    modes, ratio = find_eigenmodes(freq, mag_on, mag_off)
    if modes:
        print(f"  Top eigenmodes (coherent 10-avg):")
        for i, idx in enumerate(modes[:5]):
            print(f"    {freq[idx]:>10.0f} Hz: ratio={ratio[idx]:>6.1f}x "
                  f"(off={mag_off[idx]:.0f}, on={mag_on[idx]:.0f})")

        # CRITICAL: Single-capture SNR at top eigenmodes
        print(f"  Single-capture SNR at top {min(5, len(modes))} modes:")
        dds_cmd('F1:29300')
        time.sleep(0.3)
        on_singles = []
        for _ in range(20):
            _, m = spectrum(capture(rng))
            on_singles.append([m[modes[j]] for j in range(min(5, len(modes)))])
        on_singles = np.array(on_singles)

        dds_cmd('Foff')
        time.sleep(0.2)
        off_singles = []
        for _ in range(20):
            _, m = spectrum(capture(rng))
            off_singles.append([m[modes[j]] for j in range(min(5, len(modes)))])
        off_singles = np.array(off_singles)

        for j in range(min(5, len(modes))):
            on_m, on_s = on_singles[:, j].mean(), on_singles[:, j].std()
            off_m, off_s = off_singles[:, j].mean(), off_singles[:, j].std()
            pooled = np.sqrt((on_s**2 + off_s**2) / 2)
            sep = (on_m - off_m) / max(pooled, 1)
            snr = on_m / max(off_m, 1)
            print(f"    {freq[modes[j]]:>10.0f} Hz: ON={on_m:.0f}±{on_s:.0f}, "
                  f"OFF={off_m:.0f}±{off_s:.0f}, SNR={snr:.1f}x, sep={sep:.1f}σ")

        # Composite
        on_comp = on_singles.sum(axis=1)
        off_comp = off_singles.sum(axis=1)
        p = np.sqrt((on_comp.std()**2 + off_comp.std()**2) / 2)
        cs = (on_comp.mean() - off_comp.mean()) / max(p, 1)
        print(f"    Composite: sep={cs:.1f}σ")
    else:
        print(f"  No eigenmodes found at this range")

    dds_cmd('Foff')

# Cleanup
dds.close()
mux.write(b'0\n'); mux.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("\nDone.")
