#!/usr/bin/env python3
"""
Pong on Glass — V2 Training (drive-window readout)
===================================================

Diagnostic (glass_resolution_test.py) revealed:
  - Drive-frequency response: SNR 5.3, tracks input (corr 0.64)  ← SIGNAL
  - Census-mode response:     SNR 0.6                            ← NOISE
  - Intermod (separate plates): SNR 1.0                          ← NOISE

So V1 failed because it drowned 3 good features among 39 noisy ones.

V2 fix:
  1. Read a WINDOW around each drive frequency (high-SNR transfer
     function shape), not the fixed census modes.
  2. Add SOFTWARE cross-products (resp_i * resp_j) to emulate the
     nonlinear mixing the glass can't do across separate plates.
     (Clearly labeled: physical features vs software readout layer.)
  3. Honest cross-validation against random AND stationary baselines.
  4. Report both PREDICTION target (bounce physics) and TRACKING
     target (move toward ball) — the glass can track even if it
     can't predict.

Usage:
  python3 tools/pong_train_v2.py --nco-port /dev/cu.usbmodem113401
  python3 tools/pong_train_v2.py --dry-run
"""

import ctypes as ct
import numpy as np
import json
import time
import argparse
import sys
from pathlib import Path
from datetime import datetime

parser = argparse.ArgumentParser(description='Pong on Glass — V2 drive-window training')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--census', type=str, default=None)
parser.add_argument('--navg', type=int, default=24,
                    help='FFT averages per state (default: 24 — more = less noise)')
parser.add_argument('--settle', type=float, default=0.04)
parser.add_argument('--alpha', type=float, default=1.0)
parser.add_argument('--ch-x', type=str, default='F1')
parser.add_argument('--ch-y', type=str, default='F2')
parser.add_argument('--ch-v', type=str, default='F4')
parser.add_argument('--target', type=str, default='predict',
                    choices=['predict', 'track'], help='paddle target type')
parser.add_argument('--quadratic', action='store_true', default=True,
                    help='add software cross-product features')
parser.add_argument('--feature-mode', type=str, default='drivewindow',
                    choices=['drivewindow', 'modes', 'hybrid'],
                    help='Feature source: drivewindow = 21 drive-window bins (default, the 68%% '
                         'winner); modes = amplitude at every census mode (full pool incl '
                         'collisions); hybrid = both.')
parser.add_argument('--select-k', type=int, default=0,
                    help='If >0, leakage-free top-K feature selection from the candidate pool '
                         '(rank by train-fold |corr|). The principled way to draw from the full '
                         'mode pool without overfitting. 0 = use all features (legacy).')
parser.add_argument('--dry-run', action='store_true')
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
N_STATES = COURT_W * COURT_H * 2 * 2

# Drive bands — chosen to cross sharp resonances (high contrast)
F_X_LO, F_X_HI = 35000, 65000
F_Y_LO, F_Y_HI = 70000, 100000
F_V_LO, F_V_HI = 105000, 135000

# Drive-window readout: read these bin offsets around each drive freq
WINDOW_OFFSETS = [-8, -4, -2, 0, 2, 4, 8]  # in FFT bins → captures local |H(f)| shape
N_WIN = len(WINDOW_OFFSETS)

OUT_DIR = Path('data/results/pong')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')

print("=" * 70)
print("  PONG ON GLASS — V2 TRAINING (drive-window readout)")
print("=" * 70)

# ─── Census ──────────────────────────────────────────────────────
if args.census:
    census_path = Path(args.census)
else:
    census_files = sorted(Path('data/results/direct_wire_census').glob('direct_wire_census_*.json'))
    census_path = census_files[-1]
with open(census_path) as f:
    census = json.load(f)
mode_freqs = np.array([m['freq_hz'] for m in census['usable_modes']])
K = len(mode_freqs)
print(f"\n[1] Census: {census_path.name}, {K} modes")

# Full candidate mode pool — includes collision modes when census ran --keep-collisions.
# 'all_modes' uses key 'freq'; 'usable_modes' uses 'freq_hz'. Handle both.
_pool_src = census.get('all_modes') or census['usable_modes']
all_mode_freqs = np.array(sorted({float(m.get('freq', m.get('freq_hz'))) for m in _pool_src}))
USE_MODES = args.feature_mode in ('modes', 'hybrid')
USE_WINDOWS = args.feature_mode in ('drivewindow', 'hybrid')
if USE_MODES:
    print(f"    Full mode pool: {len(all_mode_freqs)} candidate frequencies "
          f"(feature-mode={args.feature_mode}, includes collisions if --keep-collisions census)")


# ─── States ──────────────────────────────────────────────────────
def index_to_state(idx):
    bx = idx // 32
    r = idx % 32
    by = r // 4
    r = r % 4
    return bx, by, (1 if r//2 else -1), (1 if r%2 else -1)


def state_to_index(bx, by, vx, vy):
    return bx*32 + by*4 + (1 if vx==1 else 0)*2 + (1 if vy==1 else 0)


def encode_state(bx, by, vx, vy):
    f1 = F_X_LO + bx * (F_X_HI - F_X_LO) / (COURT_W - 1)
    f2 = F_Y_LO + by * (F_Y_HI - F_Y_LO) / (COURT_H - 1)
    vq = (1 if vx==1 else 0)*2 + (1 if vy==1 else 0)
    f3 = F_V_LO + vq * (F_V_HI - F_V_LO) / 3
    return f1, f2, f3


drive_freqs = np.array([encode_state(*index_to_state(i)) for i in range(N_STATES)])
print(f"[2] {N_STATES} states encoded → 3 drive tones each")

# Physical feature layout: 3 drives × N_WIN window bins = 3*N_WIN
N_PHYS = 3 * N_WIN
print(f"[3] Drive-window readout: {N_WIN} bins × 3 drives = {N_PHYS} physical features")


# ─── Targets ─────────────────────────────────────────────────────
def compute_optimal_paddle(bx, by, vx, vy):
    x, y = float(bx), float(by)
    for _ in range(30):
        x += vx; y += vy
        if y < 0: y = -y; vy = -vy
        if y > COURT_H-1: y = 2*(COURT_H-1)-y; vy = -vy
        if x < 0: x = -x; vx = -vx
        if x >= COURT_W-1: return np.clip(y, 0, COURT_H-1)
    return (COURT_H-1)/2.0


if args.target == 'predict':
    targets = np.array([compute_optimal_paddle(*index_to_state(i)) for i in range(N_STATES)])
else:  # track current ball_y
    targets = np.array([index_to_state(i)[1] for i in range(N_STATES)], dtype=float)
targets_norm = targets / (COURT_H - 1)
print(f"[4] Target: {args.target} (min={targets.min():.0f}, max={targets.max():.0f})")


# ─── Collection ──────────────────────────────────────────────────
print(f"\n[5] Collecting (navg={args.navg})...")


def read_amp(spectrum, freq, search=2):
    b = int(round(freq / BIN_HZ))
    return float(spectrum[max(0,b-search):min(len(spectrum),b+search+1)].max())


def extract_phys(spectrum, f1, f2, f3):
    feats = np.zeros(N_PHYS)
    for di, fd in enumerate((f1, f2, f3)):
        base = int(round(fd / BIN_HZ))
        for wi, off in enumerate(WINDOW_OFFSETS):
            b = base + off
            feats[di*N_WIN + wi] = float(spectrum[max(0,b-1):b+2].max()) if 0 <= b < len(spectrum) else 0.0
    return feats


if args.dry_run:
    print("  [DRY RUN] synthetic")
    Yp = np.random.rand(N_STATES, N_PHYS)
    Ymodes = np.zeros((N_STATES, len(all_mode_freqs)))
    for idx in range(N_STATES):
        bx, by, vx, vy = index_to_state(idx)
        Yp[idx, N_WIN//2] += bx/7.0*2          # f1 window center tracks bx
        Yp[idx, N_WIN + N_WIN//2] += by/7.0*2  # f2 tracks by
        Yp[idx, 2*N_WIN + N_WIN//2] += ((vx+1)+(vy+1))/4
        if USE_MODES:
            for k, f in enumerate(all_mode_freqs):
                base = np.random.randn()*0.1
                if 70000 <= f <= 100000:       # modes in ball_y band carry signal
                    base += by/7.0 * 1.4
                Ymodes[idx, k] = base
    Yp += np.random.randn(*Yp.shape)*0.1
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
    nco_ser = serial.Serial(args.nco_port, 115200, timeout=2)
    time.sleep(0.5); nco_ser.reset_input_buffer()
    print(f"  PicoScope handle={handle}, NCO={args.nco_port}")

    def nco_send(cmd):
        nco_ser.reset_input_buffer()
        nco_ser.write(f'{cmd}\n'.encode())
        time.sleep(0.015)

    def capture():
        buf = (ct.c_int16 * N_SAMPLES)()
        ov = ct.c_int16()
        mags = []
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

    Yp = np.zeros((N_STATES, N_PHYS))
    Ymodes = np.zeros((N_STATES, len(all_mode_freqs)))
    t0 = time.time()
    for idx in range(N_STATES):
        f1, f2, f3 = drive_freqs[idx]
        nco_send(f'{args.ch_x}:{int(f1)}')
        nco_send(f'{args.ch_y}:{int(f2)}')
        nco_send(f'{args.ch_v}:{int(f3)}')
        time.sleep(args.settle)
        sp = capture()
        Yp[idx] = extract_phys(sp, f1, f2, f3)
        if USE_MODES:
            for k, f in enumerate(all_mode_freqs):
                Ymodes[idx, k] = read_amp(sp, f)
        if (idx+1) % 32 == 0 or idx+1 == N_STATES:
            el = time.time()-t0
            print(f"    {idx+1}/{N_STATES} — ETA {el/(idx+1)*(N_STATES-idx-1):.0f}s")
    nco_send('Foff')
    print(f"  Collection: {time.time()-t0:.1f}s")
    nco_ser.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))

print(f"  Physical features Y: {Yp.shape}")


# ═══════════════════════════════════════════════════════════════
#  FEATURE-SELECTION PATH (draws from the full mode pool)
#  Active when --feature-mode != drivewindow OR --select-k > 0.
#  Self-contained: builds candidate pool, leakage-free top-K select,
#  trains, and saves a 'multitone_v2_selected' model — then exits.
#  Leaves the legacy 68%% drive-window path below fully intact.
# ═══════════════════════════════════════════════════════════════
if USE_MODES or args.select_k > 0:
    PADDLE_H = 3

    # ── Build candidate pool + declarative feature specs ──
    feature_specs = []   # one dict per candidate column (window | mode)
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
    print(f"\n[6] Candidate pool: {n_cand} features "
          f"({'windows+' if USE_WINDOWS else ''}{len(all_mode_freqs) if USE_MODES else 0} modes)")

    # ── Baselines ──
    np.random.seed(1); ri = []
    for _ in range(40):
        rp = np.random.randint(PADDLE_H//2, COURT_H-PADDLE_H//2+1, size=N_STATES)
        ri.append(np.mean(np.abs(targets-rp) <= PADDLE_H/2))
    rand_mean = np.mean(ri)*100
    stat_int = np.mean(np.abs(targets-(COURT_H-1)/2) <= PADDLE_H/2)*100

    # ── Leakage-free top-K selection inside CV (rank by train-fold corr) ──
    def cv_select(pool, K, alpha, folds=4):
        n = len(targets); idx = np.arange(n)
        rng = np.random.default_rng(42); rng.shuffle(idx)
        fs = n//folds; ics = []
        Kc = min(K, pool.shape[1]) if K > 0 else pool.shape[1]
        for fdi in range(folds):
            te = idx[fdi*fs:(fdi+1)*fs]; tr = np.setdiff1d(idx, te)
            tn = targets_norm[tr]
            if K > 0:
                cors = np.array([abs(np.corrcoef(pool[tr, k], tn)[0, 1])
                                 if pool[tr, k].std() > 1e-9 else 0.0
                                 for k in range(pool.shape[1])])
                sel = np.argsort(-cors)[:Kc]
            else:
                sel = np.arange(pool.shape[1])
            Xtr, Xte = pool[tr][:, sel], pool[te][:, sel]
            mu = Xtr.mean(0); sd = Xtr.std(0); sd[sd < 1e-10] = 1.0
            Xtr = (Xtr-mu)/sd; Xte = (Xte-mu)/sd
            I = np.eye(len(sel))
            w = np.linalg.solve(Xtr.T@Xtr + alpha*I, Xtr.T@tn)
            b = tn.mean() - Xtr.mean(0)@w
            pred = (Xte@w + b)*(COURT_H-1)
            ics.append(np.mean(np.abs(pred - targets[te]) <= PADDLE_H/2))
        return np.mean(ics)*100

    K_grid = [args.select_k] if args.select_k > 0 else [10, 20, 30, 0]
    alpha_grid = [0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
    print(f"\n[7] Leakage-free selection (K × alpha sweep)...")
    print(f"  {'K':>5} {'alpha':>6} {'intercept':>10}")
    print(f"  {'-'*5} {'-'*6} {'-'*10}")
    best = {'ic': -1, 'k': K_grid[0], 'alpha': alpha_grid[0]}
    for K in K_grid:
        for a in alpha_grid:
            ic = cv_select(Ycand, K, a)
            if ic > best['ic']:
                best = {'ic': ic, 'k': K, 'alpha': a}
            klabel = 'all' if K == 0 else str(K)
            mark = '  <--' if (best['k'] == K and best['alpha'] == a and best['ic'] == ic) else ''
            print(f"  {klabel:>5} {a:>6.1f} {ic:>9.0f}%{mark}")
    print(f"  {'-'*5} {'-'*6} {'-'*10}")
    print(f"  {'random':>5} {'':>6} {rand_mean:>9.0f}%")
    print(f"  {'stat':>5} {'':>6} {stat_int:>9.0f}%")

    # ── Verdict ──
    print(f"\n[8] Verdict (target={args.target}, feature-mode={args.feature_mode})...")
    print(f"  Best: {best['ic']:.0f}% at K={best['k'] or 'all'}, alpha={best['alpha']}")
    if best['ic'] > stat_int + 5:
        print(f"  ✓✓ GLASS BEATS STATIONARY (+{best['ic']-stat_int:.0f} pts)")
    elif best['ic'] > rand_mean + 10:
        print(f"  ✓ Beats random (+{best['ic']-rand_mean:.0f}) but not stationary")
    else:
        print(f"  ✗ No usable advantage")

    # ── Final: select top-K on ALL data, train, save ──
    Kf = best['k']
    if Kf > 0:
        cors_all = np.array([abs(np.corrcoef(Ycand[:, k], targets_norm)[0, 1])
                             if Ycand[:, k].std() > 1e-9 else 0.0
                             for k in range(n_cand)])
        sel = np.argsort(-cors_all)[:min(Kf, n_cand)]
        sel = np.sort(sel)
    else:
        sel = np.arange(n_cand)
    Xsel = Ycand[:, sel]
    mu = Xsel.mean(0); sd = Xsel.std(0); sd[sd < 1e-10] = 1.0
    Xn = (Xsel-mu)/sd
    I = np.eye(len(sel))
    w = np.linalg.solve(Xn.T@Xn + best['alpha']*I, Xn.T@targets_norm)
    bias = targets_norm.mean() - Xn.mean(0)@w
    sel_specs = [feature_specs[i] for i in sel]
    n_mode_sel = sum(1 for s in sel_specs if s['kind'] == 'mode')
    n_win_sel = sum(1 for s in sel_specs if s['kind'] == 'window')
    print(f"\n[9] Final model: {len(sel)} features selected "
          f"({n_win_sel} windows, {n_mode_sel} modes), alpha={best['alpha']}")

    model = {
        'timestamp': TIMESTAMP, 'encoding': 'multitone_v2_selected',
        'census_file': str(census_path),
        'config': {
            'ch_x': args.ch_x, 'ch_y': args.ch_y, 'ch_v': args.ch_v,
            'navg': args.navg, 'settle_s': args.settle, 'alpha': best['alpha'],
            'f_x_lo': F_X_LO, 'f_x_hi': F_X_HI, 'f_y_lo': F_Y_LO, 'f_y_hi': F_Y_HI,
            'f_v_lo': F_V_LO, 'f_v_hi': F_V_HI, 'court_w': COURT_W, 'court_h': COURT_H,
            'window_offsets': WINDOW_OFFSETS, 'feature_mode': args.feature_mode,
            'select_k': int(Kf), 'target': args.target,
            'nco_port': args.nco_port, 'dry_run': args.dry_run,
        },
        'feature_spec': sel_specs,
        'normalization': {'mu': mu.tolist(), 'sd': sd.tolist()},
        'weights': w.tolist(), 'bias': float(bias),
        'metrics': {'best_intercept': float(best['ic']), 'random_pct': float(rand_mean),
                    'stationary_pct': float(stat_int), 'n_features': len(sel),
                    'n_modes': n_mode_sel, 'n_windows': n_win_sel,
                    'note': f'select-{Kf} from {n_cand} pool, {args.feature_mode}'},
    }
    mp = OUT_DIR / f'pong_model_v2_selected_{args.target}_{TIMESTAMP}.json'
    with open(mp, 'w') as f:
        json.dump(model, f, indent=2)
    print(f"  Model: {mp}")
    np.savez(OUT_DIR / f'pong_v2_selected_data_{TIMESTAMP}.npz',
             Ycand=Ycand, targets=targets, all_mode_freqs=all_mode_freqs)
    print(f"\n  Next: python3 tools/pong_live.py --model {mp}")
    print("=" * 70)
    sys.exit(0)


# ─── Build full feature matrix (+ software quadratic) ────────────
def normalize_fit(X):
    mu = X.mean(0); sd = X.std(0); sd[sd<1e-10] = 1.0
    return (X-mu)/sd, mu, sd


# Reduce physical features to per-drive summary for clean cross-products:
# use the max (resonance hit strength) per drive window
drive_strength = np.zeros((N_STATES, 3))
for di in range(3):
    drive_strength[:, di] = Yp[:, di*N_WIN:(di+1)*N_WIN].max(axis=1)

if args.quadratic:
    # Software readout layer: cross-products emulate intermodulation
    cross = np.column_stack([
        drive_strength[:,0]*drive_strength[:,1],
        drive_strength[:,0]*drive_strength[:,2],
        drive_strength[:,1]*drive_strength[:,2],
        drive_strength[:,0]**2, drive_strength[:,1]**2, drive_strength[:,2]**2,
    ])
    Yfull = np.hstack([Yp, cross])
    print(f"[6] + software quadratic readout: {cross.shape[1]} cross-products → {Yfull.shape[1]} total")
else:
    Yfull = Yp
    print(f"[6] linear readout only: {Yfull.shape[1]} features")


# ─── Evaluate ────────────────────────────────────────────────────
PADDLE_H = 3


def cv_eval(X, alpha, folds=4):
    Xn, _, _ = normalize_fit(X)
    n = len(targets); idx = np.arange(n); np.random.seed(42); np.random.shuffle(idx)
    fs = n//folds; I = np.eye(Xn.shape[1]); rm = []; ic = []
    for f in range(folds):
        te = idx[f*fs:(f+1)*fs]; tr = np.setdiff1d(idx, te)
        w = np.linalg.solve(Xn[tr].T@Xn[tr]+alpha*I, Xn[tr].T@targets_norm[tr])
        b = targets_norm[tr].mean() - Xn[tr].mean(0)@w
        pred = (Xn[te]@w+b)*(COURT_H-1)
        rm.append(np.sqrt(np.mean((pred-targets[te])**2)))
        ic.append(np.mean(np.abs(pred-targets[te]) <= PADDLE_H/2))
    return np.mean(rm), np.mean(ic)*100


print(f"\n[7] Honest cross-validation (alpha sweep)...")
print(f"  {'config':<28} {'CV-RMSE':>9} {'Intercept':>10}")
print(f"  {'-'*28} {'-'*9} {'-'*10}")
best_alpha, best_ic, best_rmse = args.alpha, 0, 99
for a in [0.5, 1.0, 2.0, 5.0, 10.0]:
    r, i = cv_eval(Yp, a)
    print(f"  {'physical only, a='+str(a):<28} {r:>9.2f} {i:>9.0f}%")
for a in [0.5, 1.0, 2.0, 5.0, 10.0]:
    r, i = cv_eval(Yfull, a)
    marker = ''
    if i > best_ic:
        best_ic, best_rmse, best_alpha = i, r, a
        marker = '  <-- best'
    print(f"  {'+quadratic, a='+str(a):<28} {r:>9.2f} {i:>9.0f}%{marker}")

# Baselines
np.random.seed(1); ri = []
for _ in range(40):
    rp = np.random.randint(PADDLE_H//2, COURT_H-PADDLE_H//2+1, size=N_STATES)
    ri.append(np.mean(np.abs(targets-rp) <= PADDLE_H/2))
rand_mean = np.mean(ri)*100
stat_int = np.mean(np.abs(targets-(COURT_H-1)/2) <= PADDLE_H/2)*100
print(f"  {'-'*28} {'-'*9} {'-'*10}")
print(f"  {'random baseline':<28} {'--':>9} {rand_mean:>9.0f}%")
print(f"  {'stationary baseline':<28} {'--':>9} {stat_int:>9.0f}%")


# ─── Verdict ─────────────────────────────────────────────────────
print(f"\n[8] Verdict (target={args.target})...")
print(f"  Best: {best_ic:.0f}% intercept (CV-RMSE {best_rmse:.2f}, alpha {best_alpha})")
print(f"  vs random {rand_mean:.0f}%, vs stationary {stat_int:.0f}%")
if best_ic > stat_int + 5:
    print(f"  ✓✓ GLASS BEATS STATIONARY (+{best_ic-stat_int:.0f} pts) — real play!")
elif best_ic > rand_mean + 10:
    print(f"  ✓ Glass beats random (+{best_ic-rand_mean:.0f}) but not stationary")
else:
    print(f"  ✗ No usable advantage")


# ─── Train + save final ──────────────────────────────────────────
print(f"\n[9] Saving final model...")
Xn, mu, sd = normalize_fit(Yfull)
I = np.eye(Xn.shape[1])
w = np.linalg.solve(Xn.T@Xn + best_alpha*I, Xn.T@targets_norm)
bias = targets_norm.mean() - Xn.mean(0)@w

model = {
    'timestamp': TIMESTAMP, 'encoding': 'multitone_v2_drivewindow',
    'census_file': str(census_path),
    'config': {
        'ch_x': args.ch_x, 'ch_y': args.ch_y, 'ch_v': args.ch_v,
        'navg': args.navg, 'settle_s': args.settle, 'alpha': best_alpha,
        'f_x_lo': F_X_LO, 'f_x_hi': F_X_HI, 'f_y_lo': F_Y_LO, 'f_y_hi': F_Y_HI,
        'f_v_lo': F_V_LO, 'f_v_hi': F_V_HI, 'court_w': COURT_W, 'court_h': COURT_H,
        'window_offsets': WINDOW_OFFSETS, 'n_phys': N_PHYS, 'quadratic': args.quadratic,
        'target': args.target, 'nco_port': args.nco_port, 'dry_run': args.dry_run,
    },
    'normalization': {'mu': mu.tolist(), 'sd': sd.tolist()},
    'weights': w.tolist(), 'bias': float(bias),
    'metrics': {'best_intercept': float(best_ic), 'best_rmse': float(best_rmse),
                'random_pct': float(rand_mean), 'stationary_pct': float(stat_int)},
}
mp = OUT_DIR / f'pong_model_v2_{args.target}_{TIMESTAMP}.json'
with open(mp, 'w') as f:
    json.dump(model, f, indent=2)
print(f"  Model: {mp}")
np.savez(OUT_DIR / f'pong_v2_data_{TIMESTAMP}.npz', Yp=Yp, Yfull=Yfull, targets=targets, drive_freqs=drive_freqs)
print(f"\n  Next: python3 tools/pong_live.py --model {mp}")
print("=" * 70)
