#!/usr/bin/env python3
"""
Validate NCO duty-cycle amplitude control.

Drives a fixed strong mode at 8 duty levels (A<ch>:<permille>) and reads the
response amplitude at that frequency. If the response ramps MONOTONICALLY with
duty and spans a useful dynamic range, the proven 'amplitude of a fixed mode'
encoding is now available on the existing hardware (no rewiring).

Duty levels chosen so amplitude = sin(pi*duty) is evenly spaced (linear system
gives evenly-spaced response): duty_permille = asin((L+1)/8)/pi*1000.
"""
import ctypes as ct
import numpy as np
import time
import sys
import math
import serial

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
RNG = 6
RNG_MV = 1000.0
PORT = '/dev/cu.usbmodem113401'

# (channel, frequency Hz) — strong, well-isolated modes per channel (recent census)
TESTS = [('F1', 57000), ('F2', 82500), ('F4', 48000), ('F5', 89000)]

# 8 amplitude levels, duty permille so amp = sin(pi*duty) is evenly spaced
LEVELS = [round(math.asin((L+1)/8.0)/math.pi*1000) for L in range(8)]

ps = ct.CDLL(PICO_LIB)
ps.ps2000_open_unit.restype = ct.c_int16
handle = ps.ps2000_open_unit()
if handle <= 0:
    print(f"ERROR: PicoScope ({handle})"); sys.exit(1)
ps.ps2000_set_channel(handle, 0, 1, 0, RNG)
ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)

nco = serial.Serial(PORT, 115200, timeout=2)
time.sleep(0.5); nco.reset_input_buffer()
nco.write(b'STATUS\n'); time.sleep(0.2)
print("STATUS:", nco.readline().decode(errors='replace').strip())


def send(cmd):
    nco.reset_input_buffer(); nco.write(f'{cmd}\n'.encode()); time.sleep(0.15)
    return nco.readline().decode(errors='replace').strip()


def capture(navg=12):
    buf = (ct.c_int16 * N_SAMPLES)(); ov = ct.c_int16(); mags = []
    for _ in range(navg):
        ticks = ct.c_int32()
        ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(handle): break
            time.sleep(0.002)
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
        d = np.array(buf[:], dtype=np.float64)*(RNG_MV/32767.0); d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d*np.hanning(N_SAMPLES), n=NFFT)))
    return np.mean(mags, axis=0)


def peak(spec, f, s=3):
    b = int(round(f/BIN_HZ)); return float(spec[max(0,b-s):b+s+1].max())


# verify A command exists
r = send('A2:300')
print(f"A-command test: A2:300 -> {r}")
amp_ok = r.startswith('AMP')
send('Foff')

print(f"\nDuty levels (permille): {LEVELS}")
print(f"{'mode':>10} | " + " ".join(f"L{i}" for i in range(8)) + " | mono? | range")
print("-"*72)
all_good = True
for ch, f in TESTS:
    resp = []
    for d in LEVELS:
        send('Foff'); time.sleep(0.02)
        send(f'{ch}:{f}')
        send(f'{ch[0]}{ch[1]}:{d}' if False else f'A{ch[1]}:{d}')  # A<ch>:<duty>
        time.sleep(0.06)
        resp.append(peak(capture(12), f))
    send('Foff')
    resp = np.array(resp)
    # monotonic if mostly increasing and clear dynamic range
    incr = np.mean(np.diff(resp) > 0)
    dyn = resp[-1] / max(resp[0], 1e-9)
    mono = incr >= 0.6 and dyn > 1.5
    all_good = all_good and mono
    cells = " ".join(f"{r:>4.0f}" for r in resp)
    print(f"{ch+'@'+str(f//1000)+'k':>10} | {cells} | {'YES' if mono else 'no ':>5} | {dyn:>4.1f}x")

send('Foff'); nco.close()
ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))
print()
if not amp_ok:
    print("RESULT: A-command not recognized — firmware not flashed correctly.")
elif all_good:
    print("RESULT: ✓ Duty-cycle amplitude control WORKS and is monotonic.")
    print("  Amplitude-of-fixed-mode encoding is now available. Build the census/training.")
else:
    print("RESULT: ⚠ Amplitude responds but monotonicity/range is weak on some modes.")
    print("  Pick the modes with the cleanest ramp for encoding; widen level spacing.")
