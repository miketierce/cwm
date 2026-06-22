#!/usr/bin/env python3
"""
Glass Resolution & Repeatability Diagnostic
============================================

Before adding more features, find the LIMITING FACTOR.

Tests:
  1. REPEATABILITY — drive the same state N times, measure feature noise.
     If repeats differ a lot, the kernel is too noisy to compute with.
  2. RESOLUTION — sweep one input dimension (e.g. ball_y 0..7),
     measure how many DISTINGUISHABLE levels the glass resolves.
  3. SNR — between-state signal vs within-state noise (true Fisher).

Output tells us:
  - Is the glass stable? (repeatability correlation)
  - How fine a grid can it resolve? (effective levels)
  - What navg do we need? (noise vs averaging)

Usage:
  python3 tools/glass_resolution_test.py --nco-port /dev/cu.usbmodem113401
"""

import ctypes as ct
import numpy as np
import json
import time
import argparse
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--census', type=str, default=None)
parser.add_argument('--navg', type=int, default=16)
parser.add_argument('--repeats', type=int, default=6)
parser.add_argument('--ch-x', type=str, default='F1')
parser.add_argument('--ch-y', type=str, default='F2')
parser.add_argument('--ch-v', type=str, default='F4')
args = parser.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
NYQUIST = FS / 2
RNG = 6
RNG_MV = 1000.0

COURT_W, COURT_H = 8, 8
F_X_LO, F_X_HI = 35000, 65000
F_Y_LO, F_Y_HI = 70000, 100000
F_V_LO, F_V_HI = 105000, 135000

print("=" * 70)
print("  GLASS RESOLUTION & REPEATABILITY DIAGNOSTIC")
print("=" * 70)

# Load census
if args.census:
    census_path = Path(args.census)
else:
    census_files = sorted(Path('data/results/direct_wire_census').glob('direct_wire_census_*.json'))
    census_path = census_files[-1]
with open(census_path) as f:
    census = json.load(f)
mode_freqs = np.array([m['freq_hz'] for m in census['usable_modes']])
K = len(mode_freqs)
print(f"\n  Census: {census_path.name}, {K} modes")

INTERMOD_LABELS = ['f1+f2', 'f1+f3', 'f2+f3', '|f1-f2|', '|f1-f3|', '|f2-f3|', '2f1', '2f2', '2f3']
N_FEATURES = K + 3 + len(INTERMOD_LABELS)


def encode_state(bx, by, vx, vy):
    f1 = F_X_LO + bx * (F_X_HI - F_X_LO) / (COURT_W - 1)
    f2 = F_Y_LO + by * (F_Y_HI - F_Y_LO) / (COURT_H - 1)
    v_quad = (1 if vx == 1 else 0) * 2 + (1 if vy == 1 else 0)
    f3 = F_V_LO + v_quad * (F_V_HI - F_V_LO) / 3
    return f1, f2, f3


def intermod_freqs(f1, f2, f3):
    products = [('f1+f2', f1+f2), ('f1+f3', f1+f3), ('f2+f3', f2+f3),
               ('|f1-f2|', abs(f1-f2)), ('|f1-f3|', abs(f1-f3)), ('|f2-f3|', abs(f2-f3)),
               ('2f1', 2*f1), ('2f2', 2*f2), ('2f3', 2*f3)]
    return {lbl: fr for lbl, fr in products if 2000 < fr < NYQUIST}


# ── Hardware ──
import serial
ps = ct.CDLL(PICO_LIB)
ps.ps2000_open_unit.restype = ct.c_int16
handle = ps.ps2000_open_unit()
if handle <= 0:
    print(f"  ERROR: PicoScope (handle={handle})")
    sys.exit(1)
ps.ps2000_set_channel(handle, 0, 1, 0, RNG)
ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
nco_ser = serial.Serial(args.nco_port, 115200, timeout=2)
time.sleep(0.5)
nco_ser.reset_input_buffer()
print(f"  PicoScope handle={handle}, NCO={args.nco_port}")


def nco_send(cmd):
    nco_ser.reset_input_buffer()
    nco_ser.write(f'{cmd}\n'.encode())
    time.sleep(0.015)


def read_amp(spectrum, freq, search=3):
    b = int(round(freq / BIN_HZ))
    return float(spectrum[max(0, b-search):min(len(spectrum), b+search+1)].max())


def capture():
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16()
    mags = []
    for _ in range(args.navg):
        ticks = ct.c_int32()
        ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(handle):
                break
            time.sleep(0.002)
        else:
            continue
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
        dd = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
        dd -= dd.mean()
        mags.append(np.abs(np.fft.rfft(dd * np.hanning(N_SAMPLES), n=NFFT)))
    return np.mean(mags, axis=0) if mags else np.zeros(NFFT//2+1)


def measure_state(bx, by, vx, vy):
    f1, f2, f3 = encode_state(bx, by, vx, vy)
    nco_send(f'{args.ch_x}:{int(f1)}')
    nco_send(f'{args.ch_y}:{int(f2)}')
    nco_send(f'{args.ch_v}:{int(f3)}')
    time.sleep(0.04)
    spec = capture()
    feats = np.zeros(N_FEATURES)
    for m, fr in enumerate(mode_freqs):
        feats[m] = read_amp(spec, fr)
    feats[K], feats[K+1], feats[K+2] = read_amp(spec, f1), read_amp(spec, f2), read_amp(spec, f3)
    im = intermod_freqs(f1, f2, f3)
    for j, lbl in enumerate(INTERMOD_LABELS):
        feats[K+3+j] = read_amp(spec, im[lbl]) if lbl in im else 0.0
    return feats


# ─── TEST 1: REPEATABILITY ───────────────────────────────────────
print(f"\n[1] REPEATABILITY — {args.repeats} repeats of 6 fixed states...")
test_states = [(0,0,1,1), (3,3,1,1), (7,7,-1,-1), (2,5,1,-1), (5,2,-1,1), (4,4,1,1)]
repeat_data = np.zeros((len(test_states), args.repeats, N_FEATURES))
for r in range(args.repeats):
    for s, st in enumerate(test_states):
        repeat_data[s, r] = measure_state(*st)
    print(f"    repeat {r+1}/{args.repeats} done")

# Within-state noise vs between-state signal
within_std = repeat_data.std(axis=1).mean(axis=0)   # per-feature noise (avg over states)
state_means = repeat_data.mean(axis=1)               # (states, features)
between_std = state_means.std(axis=0)                # per-feature signal across states
snr = between_std / (within_std + 1e-9)

# Repeatability correlation: correlate repeat r=0 vs r=1 feature vectors across states
print(f"\n  Feature SNR (between-state signal / within-state noise):")
print(f"    Modes:    mean SNR = {snr[:K].mean():.2f}  (max {snr[:K].max():.2f})")
print(f"    Drives:   mean SNR = {snr[K:K+3].mean():.2f}")
print(f"    Intermod: mean SNR = {snr[K+3:].mean():.2f}")
print(f"    Features with SNR > 2: {np.sum(snr > 2)}/{N_FEATURES}")
print(f"    Features with SNR > 5: {np.sum(snr > 5)}/{N_FEATURES}")

# Test-retest correlation per state
print(f"\n  Test-retest correlation (repeat 0 vs repeat -1, per state):")
for s, st in enumerate(test_states):
    c = np.corrcoef(repeat_data[s, 0], repeat_data[s, -1])[0, 1]
    print(f"    state{st}: r = {c:.3f}")
mean_retest = np.mean([np.corrcoef(repeat_data[s,0], repeat_data[s,-1])[0,1] for s in range(len(test_states))])
print(f"    Mean test-retest r = {mean_retest:.3f}")


# ─── TEST 2: RESOLUTION (ball_y sweep) ───────────────────────────
print(f"\n[2] RESOLUTION — sweep ball_y 0..7 (bx=4, vx=1, vy=1)...")
y_sweep = np.zeros((COURT_H, N_FEATURES))
for by in range(COURT_H):
    y_sweep[by] = measure_state(4, by, 1, 1)
print(f"    swept {COURT_H} levels")

# How distinguishable are adjacent levels? Use noise floor from repeatability
y_sweep_n = (y_sweep - y_sweep.mean(0)) / (y_sweep.std(0) + 1e-9)
adjacent_dist = [np.linalg.norm(y_sweep_n[i+1] - y_sweep_n[i]) for i in range(COURT_H-1)]
noise_floor = np.linalg.norm(within_std / (y_sweep.std(0) + 1e-9))
print(f"\n  Adjacent-level L2 distances (ball_y):")
for i, dd in enumerate(adjacent_dist):
    bar = '#' * int(dd * 3)
    print(f"    y={i}->{i+1}: {dd:.2f} {bar}")
print(f"  Noise floor (same-state L2): {noise_floor:.2f}")
distinguishable = np.sum(np.array(adjacent_dist) > noise_floor)
print(f"  Adjacent levels above noise: {distinguishable}/{COURT_H-1}")

# Effective resolution estimate
total_range = np.linalg.norm(y_sweep_n[-1] - y_sweep_n[0])
eff_levels = total_range / (noise_floor + 1e-9)
print(f"  Effective ball_y resolution: ~{eff_levels:.1f} distinguishable levels")


# ─── VERDICT ─────────────────────────────────────────────────────
print(f"\n[3] VERDICT...")
if mean_retest > 0.95:
    print(f"  ✓ STABLE: test-retest r={mean_retest:.3f} — glass is repeatable")
elif mean_retest > 0.85:
    print(f"  ~ MODERATELY STABLE: r={mean_retest:.3f} — some drift/noise")
else:
    print(f"  ✗ UNSTABLE: r={mean_retest:.3f} — too noisy, need more averaging")

if eff_levels >= 6:
    print(f"  ✓ HIGH RES: ~{eff_levels:.0f} levels — 8x8 grid OK")
    rec_grid = 8
elif eff_levels >= 4:
    print(f"  ~ MEDIUM RES: ~{eff_levels:.0f} levels — use {int(eff_levels)}x{int(eff_levels)} grid")
    rec_grid = int(eff_levels)
else:
    print(f"  ✗ LOW RES: ~{eff_levels:.0f} levels — coarsen to 4x4 grid")
    rec_grid = 4

print(f"\n  RECOMMENDATION:")
print(f"    - Grid size: {rec_grid}x{rec_grid}")
if snr[K+3:].mean() < 2:
    print(f"    - Intermod SNR low ({snr[K+3:].mean():.1f}) — drive 2 tones on SAME plate for real mixing")
if mean_retest < 0.95:
    print(f"    - Increase navg (currently {args.navg}) to reduce noise")

# Cleanup
nco_send('Foff')
nco_ser.close()
ps.ps2000_stop(handle)
ps.ps2000_close_unit(ct.c_int16(handle))

# Save
out = Path('data/results/pong')
np.savez(out / 'glass_resolution_test.npz',
         repeat_data=repeat_data, y_sweep=y_sweep, snr=snr,
         within_std=within_std, between_std=between_std)
print(f"\n  Saved: data/results/pong/glass_resolution_test.npz")
print("=" * 70)
