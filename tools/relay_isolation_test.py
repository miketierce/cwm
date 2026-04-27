#!/usr/bin/env python3
"""Quick test: does the relay actually matter for the CW signal?

Compares CW magnitude at plate A's mode frequency with relay ON vs OFF.
If the relay makes no difference, the signal is pure electrical crosstalk.
"""
import ctypes, sys, time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from picosdk.ps2000 import ps2000
from relay_mux import RelayMux

TIMEBASE = 7
N = 8064
DT_NS = 1280
FREQ = 55000  # Plate A strongest mode

port = sys.argv[1] if len(sys.argv) > 1 else '/dev/cu.usbserial-11310'

def set_cw(h, freq):
    ps2000.ps2000_set_sig_gen_built_in(h, 0, 2_000_000, 0, freq, freq, 0, 0, 0, 0)

def stop_awg(h):
    ps2000.ps2000_set_sig_gen_built_in(h, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)

def capture(h):
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(h, N, TIMEBASE, 1, ctypes.byref(t_ms))
    while ps2000.ps2000_ready(h) == 0:
        pass
    buf_a = (ctypes.c_int16 * N)()
    buf_b = (ctypes.c_int16 * N)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        h, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), N)
    return np.array(buf_a[:n], dtype=np.float64)

def demod(wf, freq):
    t = np.arange(len(wf)) * DT_NS * 1e-9
    I = np.mean(wf * np.cos(2 * np.pi * freq * t))
    Q = np.mean(wf * np.sin(2 * np.pi * freq * t))
    return np.sqrt(I**2 + Q**2)

# Open hardware
handle = ctypes.c_int16()
status = ps2000.ps2000_open_unit(ctypes.byref(handle))
print(f"ps2000_open_unit returned status={status}, handle={handle.value}")
ps2000.ps2000_set_channel(handle, 0, True, 1, 10)  # Ch A, DC, ±1V
print(f"PicoScope opened, handle={handle.value}")

mux = RelayMux(port=port)
mux.open()
print(f"Relay mux on {port}")

results = {}

# Test 1: CW + relay 1 ON (plate A connected)
print("\n--- Test 1: CW at 55 kHz, relay 1 ON (plate A) ---")
mux.select(1)
time.sleep(0.5)
set_cw(handle, FREQ)
time.sleep(0.5)
mags = [demod(capture(handle), FREQ) for _ in range(5)]
results['cw_relay_on'] = np.mean(mags)
print(f"  Mag = {np.mean(mags):.1f} ± {np.std(mags):.1f}")

# Test 2: CW + all relays OFF (no plate)
print("\n--- Test 2: CW at 55 kHz, ALL relays OFF ---")
mux.off()
time.sleep(0.5)
mags = [demod(capture(handle), FREQ) for _ in range(5)]
results['cw_relay_off'] = np.mean(mags)
print(f"  Mag = {np.mean(mags):.1f} ± {np.std(mags):.1f}")

# Test 3: AWG off + relay 1 ON (acoustic residual only)
print("\n--- Test 3: AWG OFF, relay 1 ON (residual acoustic) ---")
mux.select(1)
time.sleep(0.3)
set_cw(handle, FREQ)
time.sleep(0.5)
stop_awg(handle)
time.sleep(0.005)  # brief settle
mags = [demod(capture(handle), FREQ) for _ in range(5)]
results['awg_off_relay_on'] = np.mean(mags)
print(f"  Mag = {np.mean(mags):.1f} ± {np.std(mags):.1f}")

# Test 4: AWG off + all relays OFF (noise floor)
print("\n--- Test 4: AWG OFF, ALL relays OFF (noise floor) ---")
mux.off()
time.sleep(0.3)
mags = [demod(capture(handle), FREQ) for _ in range(5)]
results['awg_off_relay_off'] = np.mean(mags)
print(f"  Mag = {np.mean(mags):.1f} ± {np.std(mags):.1f}")

# Test 5: CW at OFF-RESONANCE freq + relay ON
OFF_FREQ = 50000  # well away from 55 kHz mode
print(f"\n--- Test 5: CW at {OFF_FREQ} Hz (off-resonance), relay 1 ON ---")
mux.select(1)
time.sleep(0.3)
set_cw(handle, OFF_FREQ)
time.sleep(0.5)
mags = [demod(capture(handle), OFF_FREQ) for _ in range(5)]
results['cw_offres_relay_on'] = np.mean(mags)
print(f"  Mag = {np.mean(mags):.1f} ± {np.std(mags):.1f}")

# Test 6: CW at OFF-RESONANCE + relay OFF
print(f"\n--- Test 6: CW at {OFF_FREQ} Hz (off-resonance), ALL relays OFF ---")
mux.off()
time.sleep(0.3)
mags = [demod(capture(handle), OFF_FREQ) for _ in range(5)]
results['cw_offres_relay_off'] = np.mean(mags)
print(f"  Mag = {np.mean(mags):.1f} ± {np.std(mags):.1f}")

# Cleanup
stop_awg(handle)
mux.off()
mux.close()
ps2000.ps2000_close_unit(handle)

# Summary
print("\n" + "=" * 60)
print("  RELAY ISOLATION SUMMARY")
print("=" * 60)
on = results['cw_relay_on']
off = results['cw_relay_off']
diff = on - off
pct = diff / on * 100 if on > 0 else 0
print(f"  CW @ mode freq:")
print(f"    Relay ON:  {on:.1f}")
print(f"    Relay OFF: {off:.1f}")
print(f"    Diff:      {diff:.1f}  ({pct:.2f}%)")
print()
print(f"  AWG off:")
print(f"    Relay ON:  {results['awg_off_relay_on']:.1f}")
print(f"    Relay OFF: {results['awg_off_relay_off']:.1f}")
print()
on2 = results['cw_offres_relay_on']
off2 = results['cw_offres_relay_off']
diff2 = on2 - off2
pct2 = diff2 / on2 * 100 if on2 > 0 else 0
print(f"  CW @ off-resonance:")
print(f"    Relay ON:  {on2:.1f}")
print(f"    Relay OFF: {off2:.1f}")
print(f"    Diff:      {diff2:.1f}  ({pct2:.2f}%)")
print()

if abs(pct) < 1 and abs(pct2) < 1:
    print("  ⚠️  RELAY MAKES NO DIFFERENCE — signal is pure electrical crosstalk")
elif abs(pct) > 5:
    print(f"  ✓  Relay contributes {pct:.1f}% at resonance — acoustic signal present")
else:
    print(f"  ~  Relay contributes {pct:.1f}% at resonance — mostly crosstalk")
