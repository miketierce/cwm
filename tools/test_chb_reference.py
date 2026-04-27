#!/usr/bin/env python3
"""Quick test: verify Ch B reference cancels DDS phase drift."""
import sys, ctypes, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cwm_picoscope
from picosdk.ps2000 import ps2000

TIMEBASE = 7
DT_NS = 1280
N_SAMPLES = 8064
FREQ = 29200.0  # plate B strongest mode

handle = ps2000.ps2000_open_unit()
print(f"handle={handle}")
assert handle > 0, "Scope open failed"

# Enable BOTH channels at ±1V DC
ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A (plate circuit)
ps2000.ps2000_set_channel(handle, 1, True, 1, 6)    # Ch B (AWG reference)

# Drive CW
ps2000.ps2000_set_sig_gen_built_in(
    handle, 0, 2_000_000, 0, FREQ, FREQ, 0.0, 0.0, 0, 0)
time.sleep(0.5)

# I/Q demod helper
t = np.arange(N_SAMPLES) * (DT_NS * 1e-9)
cos_ref = np.cos(2 * np.pi * FREQ * t)
sin_ref = np.sin(2 * np.pi * FREQ * t)

def capture_both():
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
    while ps2000.ps2000_ready(handle) == 0:
        pass
    ba = (ctypes.c_int16 * N_SAMPLES)()
    bb = (ctypes.c_int16 * N_SAMPLES)()
    ov = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(ba), ctypes.byref(bb),
        None, None, ctypes.byref(ov), N_SAMPLES)
    return np.array(ba[:n], dtype=np.float64), np.array(bb[:n], dtype=np.float64)

def demod(wf):
    I = 2.0 * np.mean(wf * cos_ref[:len(wf)])
    Q = 2.0 * np.mean(wf * sin_ref[:len(wf)])
    return complex(I, Q)

def circ_std(phases):
    R = np.hypot(np.mean(np.cos(phases)), np.mean(np.sin(phases)))
    return np.sqrt(-2.0 * np.log(min(R, 1.0)))

# Single capture sanity check
a, b = capture_both()
print(f"Ch A: rms={np.std(a):.1f}  peak={np.max(np.abs(a)):.0f}")
print(f"Ch B: rms={np.std(b):.1f}  peak={np.max(np.abs(b)):.0f}")
Za = demod(a); Zb = demod(b)
print(f"Za = {abs(Za):.1f} @ {np.degrees(np.angle(Za)):.1f}°")
print(f"Zb = {abs(Zb):.1f} @ {np.degrees(np.angle(Zb)):.1f}°")
ratio = Za / Zb
print(f"Za/Zb = {abs(ratio):.4f} @ {np.degrees(np.angle(ratio)):.1f}°")

# 30-capture stability test
N = 30
phases_a = []
phases_b = []
phases_ratio = []
mags_a = []
mags_b = []

for i in range(N):
    a, b = capture_both()
    Za = demod(a); Zb = demod(b)
    phases_a.append(np.angle(Za))
    phases_b.append(np.angle(Zb))
    phases_ratio.append(np.angle(Za / Zb))
    mags_a.append(abs(Za))
    mags_b.append(abs(Zb))

phases_a = np.array(phases_a)
phases_b = np.array(phases_b)
phases_ratio = np.array(phases_ratio)

sig_a = circ_std(phases_a)
sig_b = circ_std(phases_b)
sig_ratio = circ_std(phases_ratio)

print(f"\n{N}-capture phase stability test @ {FREQ:.0f} Hz:")
print(f"  Ch A raw:    σ = {np.degrees(sig_a):6.1f}° ({sig_a:.3f} rad)  mag = {np.mean(mags_a):.0f} ± {np.std(mags_a):.0f}")
print(f"  Ch B raw:    σ = {np.degrees(sig_b):6.1f}° ({sig_b:.3f} rad)  mag = {np.mean(mags_b):.0f} ± {np.std(mags_b):.0f}")
print(f"  A/B ratio:   σ = {np.degrees(sig_ratio):6.1f}° ({sig_ratio:.3f} rad)")
if sig_ratio < 0.5:
    print(f"  → STABLE (σ < 0.5 rad) — DDS phase cancellation WORKS")
else:
    print(f"  → Still unstable. Improvement: {sig_a/sig_ratio:.1f}×")

# Cleanup
ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps2000.ps2000_stop(handle)
ps2000.ps2000_close_unit(handle)
print("done")
