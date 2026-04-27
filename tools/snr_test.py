#!/usr/bin/env python3
"""Quick DDS SNR test after resistor removal."""
import ctypes, numpy as np, time, serial, sys, os

# PicoScope library
os.environ["DYLD_LIBRARY_PATH"] = "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources"
sys.path.insert(0, os.path.dirname(__file__))

DT = 1280e-9
TIMEBASE = 7
N_SAMPLES = 8064
CH_A_RANGE = 7

ps = ctypes.CDLL("/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
ps.ps2000_set_sig_gen_built_in.argtypes = [
    ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_int32, ctypes.c_int32]

# Try to close any stale handle
for h in range(1, 5):
    ps.ps2000_close_unit(h)
time.sleep(0.5)

handle = ps.ps2000_open_unit()
if handle <= 0:
    print(f"ERROR: PicoScope open failed (handle={handle})")
    sys.exit(1)
print(f"PicoScope handle: {handle}")
ps.ps2000_set_channel(handle, 0, 1, 1, CH_A_RANGE)  # Ch A on
ps.ps2000_set_channel(handle, 1, 0, 1, CH_A_RANGE)  # Ch B off

# Relay mux
mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
time.sleep(2)
mux.reset_input_buffer()
mux.write(b'5\n')
time.sleep(0.05)
print(f"Mux: {mux.readline().decode().strip()}")

# DDS controller
dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
time.sleep(2)
dds.reset_input_buffer()
# Verify DDS responds
dds.write(b'D?\n')
time.sleep(0.01)
resp = dds.readline().decode().strip()
print(f"DDS: {resp}")


def capture():
    buf_a = (ctypes.c_int16 * N_SAMPLES)()
    buf_b = (ctypes.c_int16 * N_SAMPLES)()
    ov = ctypes.c_int16(0)
    # source=5 (None) = free-running, no trigger needed
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    ms = ctypes.c_int32(0)
    ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(ms))
    for _ in range(5000):
        if ps.ps2000_ready(handle):
            break
        time.sleep(0.001)
    else:
        print("WARNING: capture timeout")
        ps.ps2000_stop(handle)
        return np.zeros(N_SAMPLES)
    ps.ps2000_get_values(handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                         None, None, ctypes.byref(ov), N_SAMPLES)
    return np.array(buf_a, dtype=np.float64)


def peak_energy(data, freq_hz):
    data = data - np.mean(data)
    w = data * np.hanning(len(data))
    nfft = len(data) * 4
    fft_c = np.fft.rfft(w, n=nfft)
    fa = np.fft.rfftfreq(nfft, d=DT)
    bh = fa[1] - fa[0]
    tb = int(round(freq_hz / bh))
    lo, hi = max(0, tb - 3), min(len(fft_c) - 1, tb + 3)
    pk = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
    return np.abs(fft_c[pk])


def lockin(data, freq_hz):
    t = np.arange(len(data)) * DT
    I = np.mean(data * np.sin(2 * np.pi * freq_hz * t))
    Q = np.mean(data * np.cos(2 * np.pi * freq_hz * t))
    return np.sqrt(I**2 + Q**2)


# ── AWG off, DDS off ──
dds.write(b'Foff\n')
time.sleep(0.1)
dds.readline()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
time.sleep(0.3)

FA, FB = 29300, 30000
N_AVG = 20

# Noise floor
na = np.mean([peak_energy(capture(), FA) for _ in range(N_AVG)])
nb = np.mean([peak_energy(capture(), FB) for _ in range(N_AVG)])
nla = np.mean([lockin(capture(), FA) for _ in range(N_AVG)])
nlb = np.mean([lockin(capture(), FB) for _ in range(N_AVG)])
print(f"\nNoise floor ({N_AVG}-avg):")
print(f"  Spectral: @{FA}Hz={na:.1f}, @{FB}Hz={nb:.1f}")
print(f"  Lock-in:  @{FA}Hz={nla:.1f}, @{FB}Hz={nlb:.1f}")

# ── DDS#1 ──
print(f"\n--- DDS#1 @ {FA} Hz (RESISTORS REMOVED) ---")
dds.write(f'F1:{FA}\n'.encode())
time.sleep(0.01)
dds.readline()
time.sleep(0.3)
sa = np.mean([peak_energy(capture(), FA) for _ in range(N_AVG)])
sla = np.mean([lockin(capture(), FA) for _ in range(N_AVG)])
print(f"  Spectral: {sa:.1f} -> SNR = {sa/na:.1f}x  (was 1.1x)")
print(f"  Lock-in:  {sla:.1f} -> SNR = {sla/nla:.1f}x  (was 4.5x)")

# ── DDS#2 ──
dds.write(b'Foff\n')
time.sleep(0.1)
dds.readline()
print(f"\n--- DDS#2 @ {FB} Hz (RESISTORS REMOVED) ---")
dds.write(f'F2:{FB}\n'.encode())
time.sleep(0.01)
dds.readline()
time.sleep(0.3)
sb = np.mean([peak_energy(capture(), FB) for _ in range(N_AVG)])
slb = np.mean([lockin(capture(), FB) for _ in range(N_AVG)])
print(f"  Spectral: {sb:.1f} -> SNR = {sb/nb:.1f}x")
print(f"  Lock-in:  {slb:.1f} -> SNR = {slb/nlb:.1f}x")

# ── Single capture variability ──
print(f"\n--- Single-capture (DDS#1 @ {FA} Hz, 30 frames) ---")
dds.write(b'Foff\n')
time.sleep(0.1)
dds.readline()
dds.write(f'F1:{FA}\n'.encode())
time.sleep(0.3)
dds.readline()
singles = [peak_energy(capture(), FA) for _ in range(30)]
sli = [lockin(capture(), FA) for _ in range(30)]
print(f"  Spectral: mean={np.mean(singles):.1f} +/- {np.std(singles):.1f}, min={min(singles):.1f}")
print(f"  Lock-in:  mean={np.mean(sli):.1f} +/- {np.std(sli):.1f}, min={min(sli):.1f}")
print(f"  Worst single SNR: spectral={min(singles)/na:.1f}x, lock-in={min(sli)/nla:.1f}x")
print(f"  Target: >=10x for temporal memory")

# Cleanup
dds.write(b'Foff\n')
dds.close()
mux.write(b'0\n')
mux.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("\nDone.")
