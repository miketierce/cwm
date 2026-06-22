#!/usr/bin/env python3
"""
Collision-Value Test — do the discarded "collision" modes carry usable signal?
==============================================================================

The census throws away any mode that shares a bin (within collision_bw) with a
mode from another TX channel. On 2026-06-21 that discarded 120 of 160 modes —
and the discarded pile had HIGHER mean SNR than the kept pile (the strongest 11
of the top 12 modes were tossed). This script tests, on real glass, whether
those collision modes actually help a downstream task or are genuinely useless.

Method (one data collection, all comparisons offline):
  1. Load the latest census → all 160 modes, tagged collision / non-collision.
  2. For each of 256 ball states, drive the SAME 3 encoding tones the winning
     drive-window model uses, capture one spectrum, and extract:
       - drive-window features (the 68% winner's readout)
       - amplitude at all 160 census-mode frequencies
  3. Ridge + 4-fold CV on the proven "track ball_y" task, for feature sets:
       (a) drive-window        (winner baseline)
       (b) 40 non-collision census modes
       (c) 160 all census modes
       (d) collision modes only (120)
       (e) drive-window + all census modes (does the glass kernel ADD value?)
  4. Verdict: if (c) ≥ (b) or (e) > (a), the collision modes carry signal and
     discarding them is throwing away compute.

Usage:
  python3 tools/collision_value_test.py --nco-port /dev/cu.usbmodem113401 --navg 16
  python3 tools/collision_value_test.py --dry-run
"""

import ctypes as ct
import numpy as np
import json
import time
import argparse
import sys
from pathlib import Path
from datetime import datetime

parser = argparse.ArgumentParser(description='Collision-mode value test')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--census', type=str, default=None)
parser.add_argument('--navg', type=int, default=16)
parser.add_argument('--settle', type=float, default=0.04)
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

COURT_W, COURT_H = 8, 8
N_STATES = COURT_W * COURT_H * 2 * 2
F_X_LO, F_X_HI = 35000, 65000
F_Y_LO, F_Y_HI = 70000, 100000
F_V_LO, F_V_HI = 105000, 135000
WINDOW_OFFSETS = [-8, -4, -2, 0, 2, 4, 8]
N_WIN = len(WINDOW_OFFSETS)
CH_X, CH_Y, CH_V = 'F1', 'F2', 'F4'

OUT_DIR = Path('data/results/collision_value')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')

print("=" * 70)
print("  COLLISION-VALUE TEST — are discarded collision modes useful?")
print("=" * 70)

# ─── Census: get all modes + collision tags ──────────────────────
if args.census:
    census_path = Path(args.census)
else:
    cf = sorted(Path('data/results/direct_wire_census').glob('direct_wire_census_*.json'))
    census_path = cf[-1]
census = json.load(open(census_path))
all_modes = census['all_modes']
# field name differs across census versions: 'freq' in all_modes, 'freq_hz' in usable
all_freqs = np.array([m.get('freq', m.get('freq_hz')) for m in all_modes], dtype=float)
usable_set = {round(m.get('freq_hz', m.get('freq'))) for m in census['usable_modes']}
is_collision = np.array([round(f) not in usable_set for f in all_freqs])
print(f"\n[1] Census: {census_path.name}")
print(f"    all modes: {len(all_freqs)} | non-collision: {(~is_collision).sum()} | "
      f"collision: {is_collision.sum()}")


def index_to_state(idx):
    bx = idx // 32
    r = idx % 32
    by = r // 4
    r = r % 4
    return bx, by, (1 if r//2 else -1), (1 if r%2 else -1)


def encode_state(bx, by, vx, vy):
    f1 = F_X_LO + bx * (F_X_HI - F_X_LO) / (COURT_W - 1)
    f2 = F_Y_LO + by * (F_Y_HI - F_Y_LO) / (COURT_H - 1)
    vq = (1 if vx == 1 else 0)*2 + (1 if vy == 1 else 0)
    f3 = F_V_LO + vq * (F_V_HI - F_V_LO) / 3
    return f1, f2, f3


drive_freqs = np.array([encode_state(*index_to_state(i)) for i in range(N_STATES)])
ball_y = np.array([index_to_state(i)[1] for i in range(N_STATES)], dtype=float)
print(f"[2] {N_STATES} states encoded → 3 drive tones each (track target = ball_y)")


def amp_at(spectrum, freq, search=2):
    b = int(round(freq / BIN_HZ))
    return float(spectrum[max(0, b-search):min(len(spectrum), b+search+1)].max())


def extract_window(spectrum, f1, f2, f3):
    feats = np.zeros(3 * N_WIN)
    for di, fd in enumerate((f1, f2, f3)):
        base = int(round(fd / BIN_HZ))
        for wi, off in enumerate(WINDOW_OFFSETS):
            b = base + off
            feats[di*N_WIN + wi] = float(spectrum[max(0, b-1):b+2].max()) if 0 <= b < len(spectrum) else 0.0
    return feats


# ─── Collection ──────────────────────────────────────────────────
print(f"\n[3] Collecting (navg={args.navg})...")
Ywin = np.zeros((N_STATES, 3 * N_WIN))
Ymodes = np.zeros((N_STATES, len(all_freqs)))

if args.dry_run:
    print("    [DRY RUN] synthetic")
    rng = np.random.default_rng(0)
    for i in range(N_STATES):
        bx, by, vx, vy = index_to_state(i)
        Ywin[i] = rng.standard_normal(3*N_WIN)*0.1
        Ywin[i, N_WIN + N_WIN//2] += by/7.0*2          # f2 window tracks ball_y
        # Make SOME collision modes carry ball_y signal, some not
        for k, f in enumerate(all_freqs):
            base = rng.standard_normal()*0.1
            if 70000 <= f <= 100000:                    # modes in the ball_y band carry signal
                base += by/7.0 * (1.5 if not is_collision[k] else 1.2)
            Ymodes[i, k] = base
else:
    import serial
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"    ERROR: PicoScope (handle={handle})"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    nco = serial.Serial(args.nco_port, 115200, timeout=2)
    time.sleep(0.5); nco.reset_input_buffer()
    print(f"    PicoScope handle={handle}, NCO={args.nco_port}")

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
        nco_send(f'{CH_X}:{int(f1)}')
        nco_send(f'{CH_Y}:{int(f2)}')
        nco_send(f'{CH_V}:{int(f3)}')
        time.sleep(args.settle)
        sp = capture()
        Ywin[i] = extract_window(sp, f1, f2, f3)
        for k, f in enumerate(all_freqs):
            Ymodes[i, k] = amp_at(sp, f)
        if (i+1) % 32 == 0 or i+1 == N_STATES:
            el = time.time()-t0
            print(f"    {i+1}/{N_STATES} — ETA {el/(i+1)*(N_STATES-i-1):.0f}s")
    nco_send('Foff')
    nco.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))
    print(f"    Collection: {time.time()-t0:.1f}s")


# ─── Evaluate: ridge + 4-fold CV on track ball_y ─────────────────
PADDLE_H = 3
targets = ball_y
targets_norm = targets / (COURT_H - 1)


def add_quad(X):
    # light nonlinearity: per-column not needed; use top-energy cross products
    return X


def cv_eval(X, folds=4, alphas=(0.5, 1, 2, 5, 10, 20, 50, 100)):
    if X.shape[1] == 0:
        return 0.0, 99.0
    mu = X.mean(0); sd = X.std(0); sd[sd < 1e-10] = 1.0
    Xn = (X - mu) / sd
    n = len(targets); idx = np.arange(n)
    rng = np.random.default_rng(42); rng.shuffle(idx)
    fs = n // folds
    best_ic, best_a = -1, alphas[0]
    for a in alphas:
        I = np.eye(Xn.shape[1]); ics = []
        for fdi in range(folds):
            te = idx[fdi*fs:(fdi+1)*fs]; tr = np.setdiff1d(idx, te)
            w = np.linalg.solve(Xn[tr].T@Xn[tr] + a*I, Xn[tr].T@targets_norm[tr])
            b = targets_norm[tr].mean() - Xn[tr].mean(0)@w
            pred = (Xn[te]@w + b)*(COURT_H-1)
            ics.append(np.mean(np.abs(pred - targets[te]) <= PADDLE_H/2))
        ic = np.mean(ics)*100
        if ic > best_ic:
            best_ic, best_a = ic, a
    return best_a, best_ic


def cv_eval_select(pool, K, folds=4, alpha=5.0):
    """Leakage-free top-K feature selection from `pool` (columns), then ridge.
    Selection (rank by |corr with target|) is done on the TRAIN fold only.
    Returns (intercept%, mean # collision modes among the K selected)."""
    if pool.shape[1] == 0:
        return 0.0, 0.0
    n = len(targets); idx = np.arange(n)
    rng = np.random.default_rng(42); rng.shuffle(idx)
    fs = n // folds
    Kc = min(K, pool.shape[1])
    ics, ncoll = [], []
    for fdi in range(folds):
        te = idx[fdi*fs:(fdi+1)*fs]; tr = np.setdiff1d(idx, te)
        # rank columns by |corr with target| on TRAIN only
        tn = targets_norm[tr]
        cors = np.zeros(pool.shape[1])
        for k in range(pool.shape[1]):
            c = pool[tr, k]
            cors[k] = abs(np.corrcoef(c, tn)[0, 1]) if c.std() > 1e-9 else 0.0
        sel = np.argsort(-cors)[:Kc]
        ncoll.append(int(is_collision_pool[sel].sum()) if is_collision_pool is not None else 0)
        Xtr, Xte = pool[tr][:, sel], pool[te][:, sel]
        mu = Xtr.mean(0); sd = Xtr.std(0); sd[sd < 1e-10] = 1.0
        Xtr = (Xtr-mu)/sd; Xte = (Xte-mu)/sd
        I = np.eye(Kc)
        w = np.linalg.solve(Xtr.T@Xtr + alpha*I, Xtr.T@tn)
        b = tn.mean() - Xtr.mean(0)@w
        pred = (Xte@w + b)*(COURT_H-1)
        ics.append(np.mean(np.abs(pred - targets[te]) <= PADDLE_H/2))
    return np.mean(ics)*100, np.mean(ncoll)


# Feature sets — direct ridge (shows high-dim overfit without selection)
is_collision_pool = None
sets = {
    '(a) drive-window [winner]': Ywin,
    '(b) 40 non-collision (all)': Ymodes[:, ~is_collision],
    '(c) 160 all modes (all)': Ymodes,
    '(d) collision modes only': Ymodes[:, is_collision],
    '(e) drive-window + all modes': np.hstack([Ywin, Ymodes]),
}

# Baselines
rng = np.random.default_rng(1); ri = []
for _ in range(40):
    rp = rng.integers(PADDLE_H//2, COURT_H-PADDLE_H//2+1, size=N_STATES)
    ri.append(np.mean(np.abs(targets - rp) <= PADDLE_H/2))
rand_pct = np.mean(ri)*100
stat_pct = np.mean(np.abs(targets - (COURT_H-1)/2) <= PADDLE_H/2)*100

print(f"\n[4] Track ball_y — ridge 4-fold CV, ALL features (no selection)")
print(f"    {'feature set':<32} {'dim':>4} {'alpha':>6} {'intercept':>10}")
print(f"    {'-'*32} {'-'*4} {'-'*6} {'-'*10}")
report = {}
for name, X in sets.items():
    a, ic = cv_eval(X)
    report[name] = {'dim': int(X.shape[1]), 'alpha': float(a), 'intercept': float(ic)}
    print(f"    {name:<32} {X.shape[1]:>4} {a:>6.1f} {ic:>9.0f}%")
print(f"    (high-dim sets overfit at 256 samples — see selection test below)")

# Leakage-free top-K selection: the FAIR test of whether collisions carry signal
print(f"\n[4b] Top-K feature SELECTION (ranked by train-fold corr, no leakage):")
print(f"    {'pool':<34} {'K':>3} {'intercept':>10} {'#collision picked':>18}")
print(f"    {'-'*34} {'-'*3} {'-'*10} {'-'*18}")
report_sel = {}
for K in (10, 20):
    # pool = non-collision only
    is_collision_pool = np.zeros((~is_collision).sum(), dtype=bool)
    ic_nc, _ = cv_eval_select(Ymodes[:, ~is_collision], K)
    # pool = all modes (collisions allowed)
    is_collision_pool = is_collision.copy()
    ic_all, npick = cv_eval_select(Ymodes, K)
    report_sel[f'K={K}'] = {'noncollision_pool': float(ic_nc),
                            'all_pool': float(ic_all),
                            'collision_picked': float(npick)}
    print(f"    {'non-collision pool (40)':<34} {K:>3} {ic_nc:>9.0f}% {0:>18}")
    print(f"    {'all-modes pool (160)':<34} {K:>3} {ic_all:>9.0f}% {npick:>17.1f}")
is_collision_pool = None
print(f"    {'-'*34} {'-'*3} {'-'*10} {'-'*18}")
print(f"    {'random baseline':<34} {'':>3} {rand_pct:>9.0f}%")
print(f"    {'stationary baseline':<34} {'':>3} {stat_pct:>9.0f}%")

# Per-mode correlation with ball_y: collision vs non-collision
corr = np.array([abs(np.corrcoef(Ymodes[:, k], ball_y)[0, 1]) if Ymodes[:, k].std() > 1e-9 else 0.0
                 for k in range(len(all_freqs))])
print(f"\n[5] Per-mode |correlation with ball_y|:")
print(f"    non-collision modes: mean {corr[~is_collision].mean():.3f}, max {corr[~is_collision].max():.3f}")
print(f"    collision modes:     mean {corr[is_collision].mean():.3f}, max {corr[is_collision].max():.3f}")
# Best collision mode
if is_collision.any():
    ci = np.where(is_collision)[0]
    bestc = ci[np.argmax(corr[ci])]
    print(f"    best collision mode: {all_freqs[bestc]/1000:.1f} kHz, |corr|={corr[bestc]:.3f} "
          f"— would have been discarded")

# ─── Verdict ─────────────────────────────────────────────────────
print(f"\n[6] Verdict (based on leakage-free top-K selection):")
nc20 = report_sel['K=20']['noncollision_pool']
all20 = report_sel['K=20']['all_pool']
pick20 = report_sel['K=20']['collision_picked']
if pick20 >= 1 and all20 >= nc20 - 2:
    print(f"    ✓ Collision modes carry signal: with K=20, selection picked "
          f"~{pick20:.0f} collision modes,")
    print(f"      and the all-modes pool scored {all20:.0f}% vs {nc20:.0f}% from non-collision only.")
    print(f"      The 'collision' label is NOT a usefulness signal — discarding them loses real features.")
elif all20 < nc20 - 3:
    print(f"    ✗ Collision modes did not help this 1-D task ({all20:.0f}% vs {nc20:.0f}%).")
    print(f"      They may still help multi-class tasks — re-test with a classifier target.")
else:
    print(f"    ≈ Collision modes neutral for this task ({all20:.0f}% vs {nc20:.0f}%).")
cmean = corr[is_collision].mean() if is_collision.any() else 0
ncmean = corr[~is_collision].mean()
if cmean >= ncmean:
    print(f"    ✓ Collision modes correlate with the target AS WELL AS non-collision "
          f"(mean |corr| {cmean:.3f} vs {ncmean:.3f}).")

out = {
    'timestamp': TS, 'census_file': str(census_path),
    'n_states': N_STATES, 'navg': args.navg,
    'baselines': {'random_pct': rand_pct, 'stationary_pct': stat_pct},
    'feature_sets_allfeatures': report,
    'feature_selection': report_sel,
    'mode_corr': {
        'noncollision_mean': float(corr[~is_collision].mean()),
        'noncollision_max': float(corr[~is_collision].max()),
        'collision_mean': float(corr[is_collision].mean()) if is_collision.any() else None,
        'collision_max': float(corr[is_collision].max()) if is_collision.any() else None,
    },
}
json.dump(out, open(OUT_DIR / f'collision_value_{TS}.json', 'w'), indent=2)
np.savez(OUT_DIR / f'collision_value_data_{TS}.npz',
         Ywin=Ywin, Ymodes=Ymodes, is_collision=is_collision,
         all_freqs=all_freqs, ball_y=ball_y)
print(f"\n  Saved: {OUT_DIR / f'collision_value_{TS}.json'}")
print("=" * 70)
