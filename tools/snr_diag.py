#!/usr/bin/env python3
"""Quick diagnostic: verify DDS output + receive path independently."""
import ctypes, numpy as np, time, serial, sys, os

ps = ctypes.CDLL("/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
ps.ps2000_set_sig_gen_built_in.argtypes = [
    ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_int32, ctypes.c_int32]

DT = 1280e-9
TIMEBASE = 7
N_SAMPLES = 8064

# Close stale
for h in range(1, 5):
    ps.ps2000_close_unit(h)
time.sleep(0.5)

handle = ps.ps2000_open_unit()
print(f"PicoScope handle: {handle}")
if handle <= 0:
    sys.exit(1)

# Both channels ON so we can measure DDS directly on Ch B if needed
# But for now: Ch A = receive PZT, Ch B off
ps.ps2000_set_channel(handle, 0, 1, 1, 7)   # Ch A, on, DC, ±5V
ps.ps2000_set_channel(handle, 1, 0, 1, 7)   # Ch B off

# Mux
mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
time.sleep(2)
mux.reset_input_buffer()
mux.write(b'5\n')
time.sleep(0.05)
print(f"Mux: {mux.readline().decode().strip()}")

# DDS
dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
time.sleep(2)
dds.reset_input_buffer()
dds.write(b'D?\n')
time.sleep(0.01)
print(f"DDS: {dds.readline().decode().strip()}")


def capture():
    buf = (ctypes.c_int16 * N_SAMPLES)()
    ov = ctypes.c_int16(0)
    ps.ps2000_set_trigger(handle, 3, 0, 0, 0, 0)  # source=3 = NONE
    ms = ctypes.c_int32(0)
    ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(ms))
    for _ in range(5000):
        if ps.ps2000_ready(handle):
            break
        time.sleep(0.001)
    else:
        print("WARNING: timeout")
        ps.ps2000_stop(handle)
        return np.zeros(N_SAMPLES)
    ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                         ctypes.byref(ov), N_SAMPLES)
    return np.array(buf, dtype=np.float64)


def rms(data):
    d = data - np.mean(data)
    return np.sqrt(np.mean(d**2))


def spectrum_peak(data, freq_hz):
    d = data - np.mean(data)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    fft_c = np.fft.rfft(w, n=nfft)
    fa = np.fft.rfftfreq(nfft, d=DT)
    bh = fa[1] - fa[0]
    tb = int(round(freq_hz / bh))
    lo, hi = max(0, tb - 3), min(len(fft_c) - 1, tb + 3)
    pk = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
    return np.abs(fft_c[pk]), fa[pk]


# ── Test 1: Baseline noise (everything off) ──
print("\n=== TEST 1: Baseline noise (all off) ===")
dds.write(b'Foff\n'); time.sleep(0.1); dds.readline()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
time.sleep(0.3)
d = capture()
print(f"  RMS: {rms(d):.1f}")
print(f"  min/max: {d.min():.0f} / {d.max():.0f}")
for f in [5000, 10000, 20000, 29300, 30000, 50000]:
    pk, fp = spectrum_peak(d, f)
    print(f"  Spectrum @{f}Hz: {pk:.1f} (actual peak at {fp:.0f}Hz)")

# ── Test 2: DDS#1 on, check RMS change ──
print("\n=== TEST 2: DDS#1 @ 29300 Hz ===")
dds.write(b'F1:29300\n'); time.sleep(0.01); dds.readline()
time.sleep(0.5)
d = capture()
print(f"  RMS: {rms(d):.1f}")
print(f"  min/max: {d.min():.0f} / {d.max():.0f}")
for f in [5000, 10000, 20000, 29300, 30000, 50000]:
    pk, fp = spectrum_peak(d, f)
    print(f"  Spectrum @{f}Hz: {pk:.1f} (actual peak at {fp:.0f}Hz)")

# ── Test 3: DDS#1 on, try ALL receiver channels ──
print("\n=== TEST 3: DDS#1 @ 29300 Hz, all mux channels ===")
for ch in range(1, 9):
    mux.write(f'{ch}\n'.encode())
    time.sleep(0.1)
    resp = mux.readline().decode().strip()
    time.sleep(0.1)
    d = capture()
    pk29, _ = spectrum_peak(d, 29300)
    print(f"  Mux ch {ch} ({resp}): RMS={rms(d):.1f}, @29300={pk29:.1f}")

# ── Test 4: AWG @ 29300 Hz through PZTs ──
print("\n=== TEST 4: PicoScope AWG @ 29300 Hz (verify receive path) ===")
dds.write(b'Foff\n'); time.sleep(0.1); dds.readline()
mux.write(b'5\n'); time.sleep(0.1); mux.readline()
# AWG: 500mV pk-pk sine @ 29300 Hz
uv = 500000  # 500mV in uV
ps.ps2000_set_sig_gen_built_in(handle, 0, uv, 0,
    ctypes.c_float(29300.0), ctypes.c_float(29300.0),
    ctypes.c_float(0.0), ctypes.c_float(0.0), 0, 0)
time.sleep(0.5)
d = capture()
print(f"  RMS: {rms(d):.1f}")
pk29, fp29 = spectrum_peak(d, 29300)
print(f"  Spectrum @29300Hz: {pk29:.1f} (peak at {fp29:.0f}Hz)")

# AWG 2Vpp
ps.ps2000_set_sig_gen_built_in(handle, 0, 2000000, 0,
    ctypes.c_float(29300.0), ctypes.c_float(29300.0),
    ctypes.c_float(0.0), ctypes.c_float(0.0), 0, 0)
time.sleep(0.5)
d = capture()
pk29, fp29 = spectrum_peak(d, 29300)
print(f"  AWG 2Vpp: @29300Hz: {pk29:.1f} (peak at {fp29:.0f}Hz)")

# ── Test 5: Lower frequency (might be better coupled) ──
print("\n=== TEST 5: DDS#1 @ 5000 Hz (lower freq test) ===")
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
dds.write(b'F1:5000\n'); time.sleep(0.01); dds.readline()
time.sleep(0.5)
d = capture()
pk5, fp5 = spectrum_peak(d, 5000)
print(f"  Spectrum @5000Hz: {pk5:.1f} (peak at {fp5:.0f}Hz)")
print(f"  RMS: {rms(d):.1f}")

# Cleanup
dds.write(b'Foff\n'); dds.close()
mux.write(b'0\n'); mux.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("\nDone.")
