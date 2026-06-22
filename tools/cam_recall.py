#!/usr/bin/env python3
"""
CAM Recall — per-axis resolution under the PROVEN method
========================================================

The proven CWM wins (T1.3 100%/193σ, T3.4 4096-state 100%, rod recall 100%)
used: SEQUENTIAL per-axis drive (one tone at a time) + REPEATS per value +
NEAREST-CENTROID (Mahalanobis) classification — NOT simultaneous multi-tone +
ridge regression (which failed at T3.4: 0.55%).

Our DOOM capture used the failing method. This tool measures how many LEVELS
per axis the glass can cleanly resolve when we do it the proven way:

  for each axis (x, y, angle) on its own band:
    for each level value:
      drive that ONE tone, settle, capture, read drive-window  (R repeats)
  build per-level centroid + pooled covariance → Mahalanobis nearest-centroid
  leave-one-out accuracy at L = 8, 6, 4, 3, 2 levels

The largest L with ~100% accuracy is the per-axis resolution → sets the maze
size for a CRISP associative-recall demo (state = product of factored axes).

Usage:
  python3 tools/cam_recall.py --nco-port /dev/cu.usbmodem113401 --repeats 6
  python3 tools/cam_recall.py --dry-run
"""

import ctypes as ct
import numpy as np
import json
import time
import argparse
import sys
from pathlib import Path
from datetime import datetime

parser = argparse.ArgumentParser(description='Per-axis resolution under proven CAM method')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--repeats', type=int, default=6, help='captures per level (for centroid+cov)')
parser.add_argument('--navg', type=int, default=12)
parser.add_argument('--settle', type=float, default=0.05)
parser.add_argument('--levels', type=int, default=8, help='levels per axis to test (then coarsen)')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
RNG = 6
RNG_MV = 1000.0
WINDOW_OFFSETS = [-8, -4, -2, 0, 2, 4, 8]
N_WIN = len(WINDOW_OFFSETS)

# One axis per channel/band (factored encoding)
AXES = [
    ('x',     'F1', 35000, 65000),
    ('y',     'F2', 70000, 100000),
    ('angle', 'F4', 105000, 135000),
]
L = args.levels
R = args.repeats

OUT = Path('data/results/cam_recall')
OUT.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')

print("=" * 70)
print("  CAM RECALL — per-axis resolution under the PROVEN method")
print(f"  Sequential per-axis drive + {R} repeats + nearest-centroid (Mahalanobis)")
print("=" * 70)


def axis_freq(lo, hi, level, nlev):
    return lo + level * (hi - lo) / (nlev - 1)


# ─── Hardware ────────────────────────────────────────────────────
if not args.dry_run:
    import serial
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"  ERROR: PicoScope (handle={handle})"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    nco = serial.Serial(args.nco_port, 115200, timeout=2)
    time.sleep(0.5); nco.reset_input_buffer()
    print(f"  PicoScope handle={handle}, NCO={args.nco_port}")

    def nco_send(cmd):
        nco.reset_input_buffer(); nco.write(f'{cmd}\n'.encode()); time.sleep(0.015)

    def capture():
        buf = (ct.c_int16 * N_SAMPLES)(); ov = ct.c_int16(); mags = []
        for _ in range(args.navg):
            ticks = ct.c_int32()
            ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ticks))
            for _ in range(500):
                if ps.ps2000_ready(handle): break
                time.sleep(0.002)
            else:
                continue
            ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
            dd = np.array(buf[:], dtype=np.float64)*(RNG_MV/32767.0); dd -= dd.mean()
            mags.append(np.abs(np.fft.rfft(dd*np.hanning(N_SAMPLES), n=NFFT)))
        return np.mean(mags, axis=0) if mags else np.zeros(NFFT//2+1)


def drive_window(spectrum, fd):
    feats = np.zeros(N_WIN)
    base = int(round(fd / BIN_HZ))
    for wi, off in enumerate(WINDOW_OFFSETS):
        b = base + off
        feats[wi] = float(spectrum[max(0, b-1):b+2].max()) if 0 <= b < len(spectrum) else 0.0
    return feats


# ─── Collect: per axis, per level, R repeats ─────────────────────
data = {}   # axis -> array (L, R, N_WIN)
print(f"\n[1] Collecting {len(AXES)} axes × {L} levels × {R} repeats "
      f"(sequential, one tone at a time)...")
for name, ch, lo, hi in AXES:
    arr = np.zeros((L, R, N_WIN))
    for lv in range(L):
        fd = axis_freq(lo, hi, lv, L)
        for r in range(R):
            if args.dry_run:
                # synthetic: feature center tracks level + noise (resolution ~ SNR)
                base = np.random.randn(N_WIN) * 0.4
                base[N_WIN//2] += lv * 0.9        # ~moderate separability
                arr[lv, r] = base
            else:
                nco_send('Foff'); time.sleep(0.01)
                nco_send(f'{ch}:{int(fd)}')
                time.sleep(args.settle)
                arr[lv, r] = drive_window(capture(), fd)
    data[name] = arr
    print(f"    {name} ({ch}) done")
if not args.dry_run:
    nco_send('Foff'); nco.close()
    ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))


# ─── Mahalanobis nearest-centroid, leave-one-out ────────────────
def maha_loo(arr, nlev):
    """arr: (L, R, D). Coarsen L→nlev. Leave-one-out nearest-centroid (Mahalanobis
    with pooled diagonal covariance). Returns accuracy %."""
    Lfull, Rr, D = arr.shape
    # map each original level to a coarse class
    cls = (np.arange(Lfull) / Lfull * nlev).astype(int)
    cls = np.clip(cls, 0, nlev-1)
    # flatten samples
    Xs = arr.reshape(Lfull*Rr, D)
    labels = np.repeat(cls, Rr)
    n = len(labels)
    # pooled per-feature variance (within-class)
    var = np.zeros(D)
    for c in np.unique(labels):
        v = Xs[labels == c]
        var += ((v - v.mean(0))**2).sum(0)
    var = var / max(n - len(np.unique(labels)), 1) + 1e-9
    correct = 0
    for i in range(n):
        tr = np.ones(n, bool); tr[i] = False
        cents = {}
        for c in np.unique(labels[tr]):
            cents[c] = Xs[tr][labels[tr] == c].mean(0)
        # Mahalanobis (diag cov) distance
        best, bestd = None, 1e18
        for c, ce in cents.items():
            dd = np.sum((Xs[i]-ce)**2 / var)
            if dd < bestd:
                bestd, best = dd, c
        correct += (best == labels[i])
    return correct / n * 100


def separation_sigma(arr):
    """Mean adjacent-level separation in σ along the most-informative feature."""
    Lf, Rr, D = arr.shape
    means = arr.mean(1)          # (L, D)
    stds = arr.std(1).mean(0) + 1e-9
    # most separable feature = largest spread of level-means / its noise
    spread = means.std(0) / stds
    j = int(np.argmax(spread))
    mj = means[:, j]; sj = stds[j]
    diffs = np.abs(np.diff(mj)) / sj
    return float(np.mean(diffs)), j


print("\n[2] Per-axis resolution — Mahalanobis nearest-centroid, leave-one-out")
print(f"  {'axis':<8} {'sep(σ)':>7} " + " ".join(f"L={n}" for n in (8, 6, 4, 3, 2)))
print(f"  {'-'*8} {'-'*7} " + " ".join("-----" for _ in range(5)))
summary = {}
for name, ch, lo, hi in AXES:
    arr = data[name]
    sep, _ = separation_sigma(arr)
    accs = []
    for nlev in (8, 6, 4, 3, 2):
        if nlev > L:
            accs.append(None); continue
        accs.append(maha_loo(arr, nlev))
    summary[name] = {'sep_sigma': sep, 'acc': {str(n): a for n, a in zip((8,6,4,3,2), accs)}}
    cells = " ".join(f"{a:>4.0f}%" if a is not None else "  -- " for a in accs)
    print(f"  {name:<8} {sep:>7.1f} {cells}")

print("\n[3] Verdict — max levels/axis at ≥90% (the crisp-demo resolution)")
maze_levels = {}
for name in summary:
    best = 1
    for nlev in (8, 6, 4, 3, 2):
        a = summary[name]['acc'].get(str(nlev))
        if a is not None and a >= 90:
            best = nlev; break
    maze_levels[name] = best
    print(f"  {name:<8} clean to ~{best} levels")
joint = maze_levels.get('x',1) * maze_levels.get('y',1) * maze_levels.get('angle',1)
print(f"\n  → Crisp factored state space ≈ {maze_levels.get('x',1)}×{maze_levels.get('y',1)}×"
      f"{maze_levels.get('angle',1)} = {joint} states at ≥90% per-axis")
print(f"    (vs the 8×8×8=512 we tried). This sets the wave-native maze size.")

json.dump({'timestamp': TS, 'repeats': R, 'levels': L, 'axes': summary,
           'maze_levels': maze_levels},
          open(OUT / f'cam_recall_{TS}.json', 'w'), indent=2)
print(f"\n  Saved: {OUT / f'cam_recall_{TS}.json'}")
print("=" * 70)
