#!/usr/bin/env python3
"""
AWG amplitude-scaling hardware check.

Question: is the PicoScope AWG output physically driving a TX PZT right now,
and does the captured response at a fixed mode scale MONOTONICALLY with AWG
amplitude? If yes → amplitude-of-fixed-mode encoding (the proven T3.4 method)
is available with zero rewiring beyond what's already there.

Drives the AWG at a few candidate strong modes, sweeps amplitude, reports the
Ch A response at the drive bin. NCO is turned off so only the AWG drives.
"""
import ctypes as ct
import numpy as np
import time
import sys
import glob

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
RNG = 6
RNG_MV = 1000.0

# candidate strong modes (Hz) from history + recent census
TEST_FREQS = [35840, 48000, 54920, 57037, 85000, 97011]
AMPS_UVPP = [200_000, 500_000, 1_000_000, 1_500_000, 2_000_000]  # 0.2–2.0 Vpp

ps = ct.CDLL(PICO_LIB)
ps.ps2000_open_unit.restype = ct.c_int16
ps.ps2000_set_sig_gen_built_in.argtypes = [
    ct.c_int16, ct.c_int32, ct.c_uint32, ct.c_int32,
    ct.c_float, ct.c_float, ct.c_float, ct.c_float, ct.c_int32, ct.c_uint32]
ps.ps2000_set_sig_gen_built_in.restype = ct.c_int16

handle = ps.ps2000_open_unit()
if handle <= 0:
    print(f"ERROR: PicoScope open failed ({handle})"); sys.exit(1)
ps.ps2000_set_channel(handle, 0, 1, 0, RNG)   # Ch A on, AC, ±1V
ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
print(f"PicoScope handle={handle}")

# turn the NCO OFF so only the AWG drives
try:
    import serial
    port = sorted(glob.glob('/dev/cu.usbmodem*'))
    if port:
        nco = serial.Serial(port[0], 115200, timeout=2)
        time.sleep(0.5); nco.reset_input_buffer()
        nco.write(b'Foff\n'); time.sleep(0.2)
        print(f"NCO off ({port[0]})")
        nco.close()
except Exception as e:
    print(f"(NCO off skipped: {e})")


def awg(freq, amp_uvpp):
    ps.ps2000_set_sig_gen_built_in(
        handle, 0, int(amp_uvpp), 0,
        ct.c_float(float(freq)), ct.c_float(float(freq)),
        ct.c_float(0.0), ct.c_float(0.0), 0, 0)


def awg_off():
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0,
        ct.c_float(1000.0), ct.c_float(1000.0), ct.c_float(0.0), ct.c_float(0.0), 0, 0)


def capture(navg=10):
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16()
    mags = []
    for _ in range(navg):
        ticks = ct.c_int32()
        ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(handle):
                break
            time.sleep(0.002)
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
        d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
        d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES), n=NFFT)))
    return np.mean(mags, axis=0)


def peak(spec, f, s=4):
    b = int(round(f / BIN_HZ))
    return float(spec[max(0, b-s):b+s+1].max())


# noise floor
awg_off(); time.sleep(0.1)
nf = float(np.median(capture(10)))
print(f"Noise floor (median bin): {nf:.1f}\n")

print(f"{'freq kHz':>9} | " + " | ".join(f"{a//1000:>4}mV" for a in AMPS_UVPP) + " | monotonic? | maxSNR")
print("-" * 78)
any_alive = False
for f in TEST_FREQS:
    resp = []
    for a in AMPS_UVPP:
        awg_off(); time.sleep(0.02)
        awg(f, a); time.sleep(0.08)
        resp.append(peak(capture(10), f))
    awg_off()
    snr = [r / nf for r in resp]
    mono = all(resp[i] <= resp[i+1] * 1.25 for i in range(len(resp)-1)) and resp[-1] > resp[0] * 1.3
    alive = max(snr) > 2.0
    any_alive = any_alive or alive
    cells = " | ".join(f"{r:>6.0f}" for r in resp)
    print(f"{f/1000:>9.1f} | {cells} | {'YES' if mono else 'no ':>10} | {max(snr):>5.1f}{'  <-- alive' if alive else ''}")

awg_off()
ps.ps2000_stop(handle)
ps.ps2000_close_unit(ct.c_int16(handle))
print()
if any_alive:
    print("RESULT: AWG IS driving a TX PZT — amplitude encoding is AVAILABLE.")
    print("  Use the freq with the cleanest monotonic amplitude ramp + highest SNR.")
else:
    print("RESULT: No acoustic response to AWG. The AWG BNC is NOT wired to a TX PZT.")
    print("  To use amplitude encoding, connect AWG OUT -> (220 ohm) -> a TX PZT,")
    print("  or drive an existing TX PZT from the AWG instead of the NCO pin.")
