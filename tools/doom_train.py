#!/usr/bin/env python3
"""
DOOM on Glass — Raycaster Training (8-column render readout)
============================================================

The glass computes the RENDER. A first-person maze: each player state
(x, y, angle) is encoded as 3 drive tones; the plates' interference response
is read in one capture; a trained readout turns that response into 8 wall-
distance column heights — the same primitive a raycaster computes, done as a
kernel LOOKUP (the maze geometry lives in the state→render mapping, recalled
from the glass's spectral fingerprint).

This is the Pong drive-window pipeline with a MULTI-OUTPUT readout:
  Pong:  features → 1 paddle position
  DOOM:  features → 8 column heights   (W is n_features × 8)

Honesty: the glass does the high-dimensional feature transform (the kernel).
The laptop does FFT + the linear readout (w·y) + maze logic + raycast labels.

Usage:
  python3 tools/doom_train.py --nco-port /dev/cu.usbmodem113401 --navg 16
  python3 tools/doom_train.py --feature-mode hybrid --select-k 24
  python3 tools/doom_train.py --dry-run
"""

import ctypes as ct
import numpy as np
import json
import time
import math
import argparse
import sys
from pathlib import Path
from datetime import datetime

parser = argparse.ArgumentParser(description='DOOM on Glass — raycaster training')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--census', type=str, default=None)
parser.add_argument('--navg', type=int, default=16)
parser.add_argument('--settle', type=float, default=0.04)
parser.add_argument('--ch-x', type=str, default='F1')
parser.add_argument('--ch-y', type=str, default='F2')
parser.add_argument('--ch-a', type=str, default='F4')
parser.add_argument('--feature-mode', type=str, default='drivewindow',
                    choices=['drivewindow', 'modes', 'hybrid'],
                    help='drivewindow = 21 drive-window bins; modes = all census-mode amplitudes '
                         '(full pool incl collisions); hybrid = both')
parser.add_argument('--select-k', type=int, default=0,
                    help='leakage-free top-K feature selection per column (0 = use all)')
parser.add_argument('--render-mode', type=str, default='soft', choices=['soft', 'hard'],
                    help='soft = volumetric fog render (SMOOTH, glass-native, learnable); '
                         'hard = first-hit raycast (DISCONTINUOUS, silicon-style, R2~0 on glass). '
                         'Default soft — the wave computer renders smooth fields, not hard edges.')
parser.add_argument('--replay', type=str, default=None,
                    help='Retrain from a saved doom_data_*.npz capture instead of collecting on '
                         'hardware (recompute targets under the chosen --render-mode). No NCO/scope needed.')
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

# Encoding bands (match Pong so the same plates/modes are exercised)
F_X_LO, F_X_HI = 35000, 65000      # player x
F_Y_LO, F_Y_HI = 70000, 100000     # player y
F_A_LO, F_A_HI = 105000, 135000    # facing angle
WINDOW_OFFSETS = [-8, -4, -2, 0, 2, 4, 8]
N_WIN = len(WINDOW_OFFSETS)

N_COLS = 8         # screen columns
N_DIRS = 8         # facing directions (45° steps)
FOV = 60.0         # degrees

OUT_DIR = Path('data/results/doom')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')

# ─── Maze (1 = wall, 0 = open) — E1M1 of CWM-DOOM ────────────────
MAZE = [
    [1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 1, 1, 0, 1, 0, 1],
    [1, 0, 0, 0, 0, 1, 0, 1],
    [1, 0, 1, 0, 1, 1, 0, 1],
    [1, 0, 1, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 1, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1],
]
MZ_H, MZ_W = len(MAZE), len(MAZE[0])

print("=" * 70)
print("  DOOM ON GLASS — raycaster training (8-column render readout)")
print("=" * 70)


def cast_ray(px, py, ang_rad, max_dist=12.0, step=0.03):
    dx, dy = math.cos(ang_rad), math.sin(ang_rad)
    t = 0.0
    while t < max_dist:
        t += step
        mx, my = int(px + dx * t), int(py + dy * t)
        if my < 0 or my >= MZ_H or mx < 0 or mx >= MZ_W or MAZE[my][mx] == 1:
            return t
    return max_dist


# ── Smooth occupancy field (Gaussian-blurred maze, bilinear sampled) ──
# Removing the first-hit BRANCH is what makes the render smooth and therefore
# learnable by a smooth analog kernel. This is the volume-rendering integral
# (same reason NeRF uses it instead of hard ray-surface intersection).
_MZ = np.array(MAZE, dtype=float)


def _blur(a, passes=2):
    b = a.copy()
    for _ in range(passes):
        b = (b + np.roll(b, 1, 0) + np.roll(b, -1, 0)
             + np.roll(b, 1, 1) + np.roll(b, -1, 1)) / 5.0
    return b


_OCC = _blur(_MZ, 2)


def _occ(px, py):
    px = min(max(px, 0), MZ_W - 1.001); py = min(max(py, 0), MZ_H - 1.001)
    x0, y0 = int(px), int(py); fx, fy = px - x0, py - y0
    return (_OCC[y0, x0]*(1-fx)*(1-fy) + _OCC[y0, x0+1]*fx*(1-fy)
            + _OCC[y0+1, x0]*(1-fx)*fy + _OCC[y0+1, x0+1]*fx*fy)


def soft_columns(x, y, angle_idx, absorb=6.0, step=0.05):
    """Volumetric (fog) render: smooth expected-depth per column. SMOOTH in
    (x, y, angle) because it integrates soft occupancy instead of branching on
    first wall-hit. This is the glass-native render the validation confirmed."""
    px, py = x + 0.5, y + 0.5
    base = angle_idx * (360.0 / N_DIRS)
    cols = []
    for c in range(N_COLS):
        a = math.radians(base - FOV / 2 + c * FOV / (N_COLS - 1))
        dx, dy = math.cos(a), math.sin(a)
        T = 1.0; depth = 0.0; wsum = 0.0; t = 0.0
        while t < 10.0:
            t += step
            o = _occ(px + dx*t, py + dy*t)
            al = 1.0 - math.exp(-absorb * o * step)
            w = T * al
            depth += w * t; wsum += w; T *= (1.0 - al)
            if T < 0.01:
                break
        d = depth / wsum if wsum > 1e-6 else 10.0
        cols.append(1.0 / max(d, 0.3))
    return cols


def render_columns(x, y, angle_idx):
    """Render 8 columns under the chosen mode (soft volumetric default)."""
    if args.render_mode == 'hard':
        px, py = x + 0.5, y + 0.5
        base = angle_idx * (360.0 / N_DIRS)
        cols = []
        for c in range(N_COLS):
            a = base - FOV / 2 + c * FOV / (N_COLS - 1)
            d = cast_ray(px, py, math.radians(a))
            cols.append(1.0 / max(d, 0.3))
        return cols
    return soft_columns(x, y, angle_idx)


# Enumerate valid states (open cells × directions)
states = []
for y in range(MZ_H):
    for x in range(MZ_W):
        if MAZE[y][x] == 0:
            for a in range(N_DIRS):
                states.append((x, y, a))
N_STATES = len(states)
open_cells = sum(r.count(0) for r in MAZE)
print(f"\n[1] Maze {MZ_W}x{MZ_H}: {open_cells} open cells × {N_DIRS} dirs = {N_STATES} states")

# Ground-truth render targets
T = np.array([render_columns(*s) for s in states])   # (N_STATES, 8)
T_min, T_max = T.min(), T.max()
T_norm = (T - T_min) / (T_max - T_min + 1e-9)
print(f"[2] Raycast targets: {T.shape} column heights (range {T_min:.2f}–{T_max:.2f})")


def encode_state(x, y, a):
    f1 = F_X_LO + x * (F_X_HI - F_X_LO) / (MZ_W - 1)
    f2 = F_Y_LO + y * (F_Y_HI - F_Y_LO) / (MZ_H - 1)
    f3 = F_A_LO + a * (F_A_HI - F_A_LO) / (N_DIRS - 1)
    return f1, f2, f3


drive_freqs = np.array([encode_state(*s) for s in states])
print(f"[3] {N_STATES} states → 3 drive tones each (x={args.ch_x}, y={args.ch_y}, angle={args.ch_a})")

# ─── Census (full candidate mode pool) ───────────────────────────
if args.census:
    census_path = Path(args.census)
else:
    cf = sorted(Path('data/results/direct_wire_census').glob('direct_wire_census_*.json'))
    census_path = cf[-1] if cf else None
all_mode_freqs = np.array([])
if census_path and args.feature_mode in ('modes', 'hybrid'):
    census = json.load(open(census_path))
    src = census.get('all_modes') or census['usable_modes']
    all_mode_freqs = np.array(sorted({float(m.get('freq', m.get('freq_hz'))) for m in src}))
    print(f"[4] Mode pool: {len(all_mode_freqs)} candidates from {census_path.name}")
USE_MODES = args.feature_mode in ('modes', 'hybrid') and len(all_mode_freqs) > 0
USE_WINDOWS = args.feature_mode in ('drivewindow', 'hybrid')
N_PHYS = 3 * N_WIN


def extract_phys(spectrum, f1, f2, f3):
    feats = np.zeros(N_PHYS)
    for di, fd in enumerate((f1, f2, f3)):
        base = int(round(fd / BIN_HZ))
        for wi, off in enumerate(WINDOW_OFFSETS):
            b = base + off
            feats[di*N_WIN + wi] = float(spectrum[max(0, b-1):b+2].max()) if 0 <= b < len(spectrum) else 0.0
    return feats


def read_amp(spectrum, freq, search=2):
    b = int(round(freq / BIN_HZ))
    return float(spectrum[max(0, b-search):min(len(spectrum), b+search+1)].max())


# ─── Collection ──────────────────────────────────────────────────
print(f"\n[5] Collecting (navg={args.navg})...")
Yp = np.zeros((N_STATES, N_PHYS))
Ymodes = np.zeros((N_STATES, len(all_mode_freqs)))

if args.replay:
    print(f"  [REPLAY] reusing capture {args.replay} (no hardware)")
    rd = np.load(args.replay, allow_pickle=True)
    Yp = rd['Yp']
    Ymodes = rd['Ymodes'] if rd['Ymodes'].size else np.zeros((N_STATES, 0))
    rstates = rd['states']
    assert len(rstates) == N_STATES, f"replay states {len(rstates)} != {N_STATES} — maze changed?"
    # rebuild candidate flags from what was captured
    if Ymodes.shape[1] != len(all_mode_freqs):
        print(f"    note: replay has {Ymodes.shape[1]} mode cols, census has {len(all_mode_freqs)} — using replay's")
        USE_MODES = Ymodes.shape[1] > 0
    print(f"    Loaded Yp{Yp.shape}, Ymodes{Ymodes.shape}")
elif args.dry_run:
    print("  [DRY RUN] synthetic")
    rng = np.random.default_rng(0)
    for i, (x, y, a) in enumerate(states):
        Yp[i] = rng.standard_normal(N_PHYS) * 0.1
        Yp[i, N_WIN//2] += x / 7.0
        Yp[i, N_WIN + N_WIN//2] += y / 7.0
        Yp[i, 2*N_WIN + N_WIN//2] += a / 7.0
        if USE_MODES:
            for k, f in enumerate(all_mode_freqs):
                base = rng.standard_normal() * 0.1
                base += (T_norm[i].mean() if 70000 <= f <= 135000 else 0.0)
                Ymodes[i, k] = base
else:
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
        nco.reset_input_buffer()
        nco.write(f'{cmd}\n'.encode())
        time.sleep(0.015)

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
            d = np.array(buf[:], dtype=np.float64)*(RNG_MV/32767.0); d -= d.mean()
            mags.append(np.abs(np.fft.rfft(d*np.hanning(N_SAMPLES), n=NFFT)))
        return np.mean(mags, axis=0) if mags else np.zeros(NFFT//2+1)

    t0 = time.time()
    for i in range(N_STATES):
        f1, f2, f3 = drive_freqs[i]
        nco_send(f'{args.ch_x}:{int(f1)}')
        nco_send(f'{args.ch_y}:{int(f2)}')
        nco_send(f'{args.ch_a}:{int(f3)}')
        time.sleep(args.settle)
        sp = capture()
        Yp[i] = extract_phys(sp, f1, f2, f3)
        if USE_MODES:
            for k, f in enumerate(all_mode_freqs):
                Ymodes[i, k] = read_amp(sp, f)
        if (i+1) % 24 == 0 or i+1 == N_STATES:
            el = time.time()-t0
            print(f"    {i+1}/{N_STATES} — ETA {el/(i+1)*(N_STATES-i-1):.0f}s")
    nco_send('Foff')
    nco.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))
    print(f"  Collection: {time.time()-t0:.1f}s")

# ─── Candidate feature pool + specs ──────────────────────────────
feature_specs = []
cols = []
if USE_WINDOWS:
    for di in range(3):
        for wi, off in enumerate(WINDOW_OFFSETS):
            feature_specs.append({'kind': 'window', 'drive': di, 'offset': int(off)})
            cols.append(Yp[:, di*N_WIN + wi])
if USE_MODES:
    for k, f in enumerate(all_mode_freqs):
        feature_specs.append({'kind': 'mode', 'freq_hz': float(f)})
        cols.append(Ymodes[:, k])
Ycand = np.column_stack(cols)
n_cand = Ycand.shape[1]
print(f"\n[6] Candidate pool: {n_cand} features")

# ─── Multi-output ridge with leakage-free per-column selection ───
def fit_predict(Xtr, Ttr, Xte, alpha, K):
    """Train multi-output ridge; optional per-column top-K selection.
    Returns predictions (n_te, 8) and the per-column selected indices."""
    n_te = Xte.shape[0]
    preds = np.zeros((n_te, N_COLS))
    sel_cols = []
    for c in range(N_COLS):
        tn = Ttr[:, c]
        if K > 0 and K < Xtr.shape[1]:
            cors = np.array([abs(np.corrcoef(Xtr[:, k], tn)[0, 1]) if Xtr[:, k].std() > 1e-9 else 0.0
                             for k in range(Xtr.shape[1])])
            sel = np.argsort(-cors)[:K]
        else:
            sel = np.arange(Xtr.shape[1])
        sel_cols.append(sel)
        Xs, Xv = Xtr[:, sel], Xte[:, sel]
        mu = Xs.mean(0); sd = Xs.std(0); sd[sd < 1e-10] = 1.0
        Xs = (Xs-mu)/sd; Xv = (Xv-mu)/sd
        I = np.eye(len(sel))
        w = np.linalg.solve(Xs.T@Xs + alpha*I, Xs.T@tn)
        b = tn.mean() - Xs.mean(0)@w
        preds[:, c] = Xv@w + b
    return preds, sel_cols


def cv_render(pool, alpha, K, folds=4):
    n = N_STATES; idx = np.arange(n)
    rng = np.random.default_rng(42); rng.shuffle(idx)
    fs = n//folds; rmses = []; corrs = []
    for f in range(folds):
        te = idx[f*fs:(f+1)*fs]; tr = np.setdiff1d(idx, te)
        preds, _ = fit_predict(pool[tr], T_norm[tr], pool[te], alpha, K)
        rmses.append(np.sqrt(np.mean((preds - T_norm[te])**2)))
        # silhouette correlation: how well the 8-col shape matches per state
        cs = [np.corrcoef(preds[i], T_norm[te][i])[0, 1]
              for i in range(len(te)) if T_norm[te][i].std() > 1e-9 and preds[i].std() > 1e-9]
        corrs.append(np.mean(cs) if cs else 0.0)
    return np.mean(rmses), np.mean(corrs)


print(f"\n[7] Render cross-validation (alpha × K sweep)...")
print(f"  {'alpha':>6} {'K':>5} {'RMSE':>7} {'silhouette r':>13}")
print(f"  {'-'*6} {'-'*5} {'-'*7} {'-'*13}")
# baseline: predict the mean column profile
mean_prof = T_norm.mean(0)
base_rmse = np.sqrt(np.mean((T_norm - mean_prof)**2))
K_grid = [args.select_k] if args.select_k > 0 else ([0] if not USE_MODES else [12, 24, 0])
best = {'rmse': 1e9, 'r': -1, 'alpha': 1.0, 'K': K_grid[0]}
for K in K_grid:
    for a in [0.5, 1.0, 2.0, 5.0, 10.0]:
        rmse, r = cv_render(Ycand, a, K)
        if rmse < best['rmse']:
            best = {'rmse': rmse, 'r': r, 'alpha': a, 'K': K}
        klabel = 'all' if K == 0 else str(K)
        mark = '  <--' if (best['alpha'] == a and best['K'] == K and best['rmse'] == rmse) else ''
        print(f"  {a:>6.1f} {klabel:>5} {rmse:>7.3f} {r:>12.2f}{mark}")
print(f"  {'-'*6} {'-'*5} {'-'*7} {'-'*13}")
print(f"  {'mean-profile baseline':<19} {base_rmse:>7.3f}")

# ─── Verdict ─────────────────────────────────────────────────────
print(f"\n[8] Verdict...")
print(f"  Best: RMSE {best['rmse']:.3f}, silhouette r={best['r']:.2f} "
      f"(alpha={best['alpha']}, K={best['K'] or 'all'})")
improve = (base_rmse - best['rmse']) / base_rmse * 100
if best['r'] > 0.7 and best['rmse'] < base_rmse * 0.7:
    print(f"  ✓✓ GLASS RENDERS THE MAZE: {improve:.0f}% better than flat baseline, shapes match (r={best['r']:.2f})")
elif best['r'] > 0.4:
    print(f"  ✓ Glass captures maze structure (r={best['r']:.2f}), {improve:.0f}% better than baseline")
else:
    print(f"  ✗ Weak render — glass not resolving column structure (r={best['r']:.2f})")

# ─── Final fit on all data + save ────────────────────────────────
print(f"\n[9] Final model...")
Kf = best['K']
W = np.zeros((n_cand if Kf == 0 else Kf, N_COLS))  # placeholder; store per-column
col_models = []
for c in range(N_COLS):
    tn = T_norm[:, c]
    if Kf > 0 and Kf < n_cand:
        cors = np.array([abs(np.corrcoef(Ycand[:, k], tn)[0, 1]) if Ycand[:, k].std() > 1e-9 else 0.0
                         for k in range(n_cand)])
        sel = np.sort(np.argsort(-cors)[:Kf])
    else:
        sel = np.arange(n_cand)
    Xs = Ycand[:, sel]
    mu = Xs.mean(0); sd = Xs.std(0); sd[sd < 1e-10] = 1.0
    Xn = (Xs-mu)/sd
    I = np.eye(len(sel))
    w = np.linalg.solve(Xn.T@Xn + best['alpha']*I, Xn.T@tn)
    b = tn.mean() - Xn.mean(0)@w
    col_models.append({'sel': sel.tolist(), 'mu': mu.tolist(), 'sd': sd.tolist(),
                       'w': w.tolist(), 'b': float(b)})

model = {
    'timestamp': TS, 'encoding': 'doom_raycast_v1',
    'census_file': str(census_path) if census_path else None,
    'maze': MAZE, 'n_cols': N_COLS, 'n_dirs': N_DIRS, 'fov': FOV,
    'render_mode': args.render_mode,
    'config': {
        'ch_x': args.ch_x, 'ch_y': args.ch_y, 'ch_a': args.ch_a,
        'navg': args.navg, 'settle_s': args.settle, 'alpha': best['alpha'],
        'f_x_lo': F_X_LO, 'f_x_hi': F_X_HI, 'f_y_lo': F_Y_LO, 'f_y_hi': F_Y_HI,
        'f_a_lo': F_A_LO, 'f_a_hi': F_A_HI, 'window_offsets': WINDOW_OFFSETS,
        'feature_mode': args.feature_mode, 'select_k': int(Kf), 'render_mode': args.render_mode,
        'mz_w': MZ_W, 'mz_h': MZ_H, 'nco_port': args.nco_port, 'dry_run': args.dry_run,
    },
    'feature_spec': feature_specs,
    'target_norm': {'min': float(T_min), 'max': float(T_max)},
    'columns': col_models,
    'metrics': {'rmse': float(best['rmse']), 'silhouette_r': float(best['r']),
                'baseline_rmse': float(base_rmse), 'n_features': n_cand,
                'note': f'render r={best["r"]:.2f}, {improve:.0f}% better than flat'},
}
mp = OUT_DIR / f'doom_model_{TS}.json'
json.dump(model, open(mp, 'w'), indent=2)
print(f"  Model: {mp}")
np.savez(OUT_DIR / f'doom_data_{TS}.npz', Yp=Yp, Ymodes=Ymodes, T=T, states=np.array(states))
print(f"\n  Next: python3 tools/doom_live.py --model {mp}")
print("=" * 70)
