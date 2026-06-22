#!/usr/bin/env python3
"""
Pong on Glass — AMPLITUDE encoding (the proven T3.4 method)
===========================================================

Leverages the 2026-06-21 finding: encode each state variable as the AMPLITUDE
of a FIXED resonant mode (monotonic), not as a drive frequency (bumpy). The NCO
duty-cycle firmware (A<ch>:<permille>) gives the amplitude knob; F5@89kHz and
F4@48kHz were validated as clean monotonic channels (8.1x / 5.0x range).

  ball_y (0..7) -> amplitude of F5 @ 89 kHz  (the clean 8.1x channel)
  ball_x (0..7) -> amplitude of F4 @ 48 kHz  (5.0x channel)
Readout: drive-window around each mode + (optional) the full census mode pool.
Target: track ball_y. Compares to the 68% drive-window (frequency-encoding) best.

Honest CV: 64 unique (x,y) drives x R repeats; leave-whole-state-out folds (no
identical-drive leakage). Reports ridge intercept AND nearest-centroid ball_y
accuracy (the proven T3.4 classifier).

Usage:
  python3 tools/pong_train_amp.py --nco-port /dev/cu.usbmodem113401 --repeats 4
  python3 tools/pong_train_amp.py --dry-run
"""
import ctypes as ct
import numpy as np
import json, time, math, argparse, sys
from pathlib import Path
from datetime import datetime

parser = argparse.ArgumentParser(description='Pong amplitude-encoding training')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--census', type=str, default=None)
parser.add_argument('--repeats', type=int, default=4, help='captures per (x,y) state')
parser.add_argument('--navg', type=int, default=14)
parser.add_argument('--settle', type=float, default=0.05)
parser.add_argument('--feature-mode', type=str, default='window',
                    choices=['window', 'hybrid'],
                    help='window = drive-windows only; hybrid = + full census mode pool')
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
PADDLE_H = 3

# Amplitude-encoding channels (validated clean monotonic 2026-06-21)
CH_Y, FREQ_Y = 'F5', 89000   # ball_y -> amplitude of 89 kHz (8.1x)
CH_X, FREQ_X = 'F4', 48000   # ball_x -> amplitude of 48 kHz (5.0x)
WINDOW_OFFSETS = [-8, -4, -2, 0, 2, 4, 8]
N_WIN = len(WINDOW_OFFSETS)

# 8 duty levels so amplitude = sin(pi*duty) is evenly spaced
DUTY = [round(math.asin((L+1)/8.0)/math.pi*1000) for L in range(8)]   # level 0..7

OUT_DIR = Path('data/results/pong')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')

print("=" * 70)
print("  PONG ON GLASS — AMPLITUDE ENCODING (proven T3.4 method)")
print(f"  ball_y -> {CH_Y}@{FREQ_Y/1000:.0f}kHz amp | ball_x -> {CH_X}@{FREQ_X/1000:.0f}kHz amp")
print("=" * 70)

# states: 64 unique (x,y); track target = ball_y
states = [(x, y) for x in range(COURT_W) for y in range(COURT_H)]
N = len(states)
R = args.repeats
ball_y = np.array([y for (x, y) in states], dtype=float)
ball_x = np.array([x for (x, y) in states], dtype=float)

# census pool (optional)
all_mode_freqs = np.array([])
census_path = None
if args.feature_mode == 'hybrid':
    cp = Path(args.census) if args.census else (sorted(Path('data/results/direct_wire_census').glob('*.json')) or [None])[-1]
    if cp:
        census_path = cp
        cj = json.load(open(cp))
        src = cj.get('all_modes') or cj['usable_modes']
        all_mode_freqs = np.array(sorted({float(m.get('freq', m.get('freq_hz'))) for m in src}))
        print(f"  Mode pool: {len(all_mode_freqs)} candidates from {cp.name}")


def win(spec, f):
    out = np.zeros(N_WIN); base = int(round(f/BIN_HZ))
    for i, o in enumerate(WINDOW_OFFSETS):
        b = base + o
        out[i] = float(spec[max(0, b-1):b+2].max()) if 0 <= b < len(spec) else 0.0
    return out


def amp_at(spec, f, s=2):
    b = int(round(f/BIN_HZ)); return float(spec[max(0, b-s):min(len(spec), b+s+1)].max())


# ─── Collect ─────────────────────────────────────────────────────
n_mode = len(all_mode_freqs)
F = 2*N_WIN + n_mode
Xc = np.zeros((N*R, F))
yc = np.zeros(N*R)
xc_lab = np.zeros(N*R)
grp = np.zeros(N*R, dtype=int)

if args.dry_run:
    print("\n[collect] DRY RUN synthetic")
    rng = np.random.default_rng(0)
    row = 0
    for gi, (x, y) in enumerate(states):
        for r in range(R):
            f = rng.standard_normal(F)*0.1
            f[N_WIN//2] += y/7.0*2          # y-window center tracks ball_y (monotonic)
            f[N_WIN + N_WIN//2] += x/7.0*2  # x-window tracks ball_x
            Xc[row] = f; yc[row] = y; xc_lab[row] = x; grp[row] = gi; row += 1
else:
    import serial
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"ERROR PicoScope {handle}"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    nco = serial.Serial(args.nco_port, 115200, timeout=2)
    time.sleep(0.5); nco.reset_input_buffer()
    nco.write(b'STATUS\n'); time.sleep(0.2)
    st = nco.readline().decode(errors='replace').strip()
    print(f"  NCO: {st}")
    if 'DUTY' not in st:
        print("  ERROR: firmware lacks DUTY — flash tools/pico_nco/main.py first."); sys.exit(1)

    def send(c):
        nco.reset_input_buffer(); nco.write(f'{c}\n'.encode()); time.sleep(0.012)

    def capture():
        buf = (ct.c_int16*N_SAMPLES)(); ov = ct.c_int16(); mags = []
        for _ in range(args.navg):
            tk = ct.c_int32()
            ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(tk))
            for _ in range(500):
                if ps.ps2000_ready(handle): break
                time.sleep(0.002)
            else:
                continue
            ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
            d = np.array(buf[:], dtype=np.float64)*(RNG_MV/32767.0); d -= d.mean()
            mags.append(np.abs(np.fft.rfft(d*np.hanning(N_SAMPLES), n=NFFT)))
        return np.mean(mags, axis=0) if mags else np.zeros(NFFT//2+1)

    print(f"\n[collect] {N} states x {R} repeats (amplitude encoding)...")
    # set the two carrier frequencies once; vary only duty (amplitude)
    t0 = time.time(); row = 0
    for gi, (x, y) in enumerate(states):
        for r in range(R):
            send('Foff'); time.sleep(0.005)
            send(f'{CH_Y}:{FREQ_Y}'); send(f'A{CH_Y[1]}:{DUTY[y]}')
            send(f'{CH_X}:{FREQ_X}'); send(f'A{CH_X[1]}:{DUTY[x]}')
            time.sleep(args.settle)
            sp = capture()
            feat = np.concatenate([win(sp, FREQ_Y), win(sp, FREQ_X)])
            if n_mode:
                feat = np.concatenate([feat, [amp_at(sp, f) for f in all_mode_freqs]])
            Xc[row] = feat; yc[row] = y; xc_lab[row] = x; grp[row] = gi; row += 1
        if (gi+1) % 8 == 0 or gi+1 == N:
            el = time.time()-t0
            print(f"    {gi+1}/{N} states — ETA {el/(gi+1)*(N-gi-1):.0f}s")
    send('Foff'); nco.close()
    ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))
    print(f"  Collection: {time.time()-t0:.1f}s")


# ─── Evaluate: leave-whole-state-out CV (no identical-drive leakage) ─
targets = yc
tnorm = targets / (COURT_H - 1)
uniq_grp = np.unique(grp)


def select_topk(Xtr, ttr, K):
    cors = np.array([abs(np.corrcoef(Xtr[:, k], ttr)[0, 1]) if Xtr[:, k].std() > 1e-9 else 0.0
                     for k in range(Xtr.shape[1])])
    return np.argsort(-cors)[:K]


def cv_ridge(X, K, alpha, folds=4):
    rng = np.random.default_rng(42); g = uniq_grp.copy(); rng.shuffle(g)
    fs = len(g)//folds; ic = []
    for f in range(folds):
        tg = set(g[f*fs:(f+1)*fs].tolist())
        te = np.array([i for i in range(len(grp)) if grp[i] in tg])
        tr = np.array([i for i in range(len(grp)) if grp[i] not in tg])
        sel = select_topk(X[tr], tnorm[tr], K) if K > 0 else np.arange(X.shape[1])
        Xtr, Xte = X[tr][:, sel], X[te][:, sel]
        mu = Xtr.mean(0); sd = Xtr.std(0); sd[sd < 1e-10] = 1
        Xtr = (Xtr-mu)/sd; Xte = (Xte-mu)/sd
        I = np.eye(len(sel))
        w = np.linalg.solve(Xtr.T@Xtr+alpha*I, Xtr.T@tnorm[tr])
        b = tnorm[tr].mean()-Xtr.mean(0)@w
        pred = (Xte@w+b)*(COURT_H-1)
        ic.append(np.mean(np.abs(pred-targets[te]) <= PADDLE_H/2))
    return np.mean(ic)*100


def cv_centroid(X, folds=4):
    # nearest-centroid ball_y classifier (proven T3.4), grouped CV
    rng = np.random.default_rng(42); g = uniq_grp.copy(); rng.shuffle(g)
    fs = len(g)//folds; acc = []
    for f in range(folds):
        tg = set(g[f*fs:(f+1)*fs].tolist())
        te = np.array([i for i in range(len(grp)) if grp[i] in tg])
        tr = np.array([i for i in range(len(grp)) if grp[i] not in tg])
        mu = X[tr].mean(0); sd = X[tr].std(0); sd[sd < 1e-10] = 1
        Xtr = (X[tr]-mu)/sd; Xte = (X[te]-mu)/sd
        var = np.ones(X.shape[1])
        cents = {c: Xtr[targets[tr] == c].mean(0) for c in np.unique(targets[tr])}
        hit = 0
        for i in range(len(te)):
            best, bd = None, 1e18
            for c, ce in cents.items():
                dd = np.sum((Xte[i]-ce)**2/var)
                if dd < bd: bd, best = dd, c
            hit += abs(best - targets[te][i]) <= PADDLE_H/2
        acc.append(hit/len(te))
    return np.mean(acc)*100


# baselines
rng = np.random.default_rng(1); ri = []
for _ in range(40):
    rp = rng.integers(PADDLE_H//2, COURT_H-PADDLE_H//2+1, size=N*R)
    ri.append(np.mean(np.abs(targets-rp) <= PADDLE_H/2))
rand_pct = np.mean(ri)*100
stat_pct = np.mean(np.abs(targets-(COURT_H-1)/2) <= PADDLE_H/2)*100

print(f"\n[eval] track ball_y — leave-whole-state-out CV")
print(f"  {'method':<34} {'intercept':>10}")
print(f"  {'-'*34} {'-'*10}")
best = {'ic': -1, 'K': 0, 'alpha': 1.0, 'kind': 'ridge'}
for K in ([0, 8, 14] + ([20] if n_mode else [])):
    for a in [0.5, 1.0, 2.0, 5.0]:
        ic = cv_ridge(Xc, K, a)
        if ic > best['ic']:
            best = {'ic': ic, 'K': K, 'alpha': a, 'kind': 'ridge'}
        if a == 1.0:
            print(f"  {'ridge K='+(str(K) if K else 'all')+' a='+str(a):<34} {ic:>9.0f}%")
cen = cv_centroid(Xc)
print(f"  {'nearest-centroid (T3.4 method)':<34} {cen:>9.0f}%")
print(f"  {'-'*34} {'-'*10}")
print(f"  {'random baseline':<34} {rand_pct:>9.0f}%")
print(f"  {'stationary baseline':<34} {stat_pct:>9.0f}%")
print(f"  {'prior best (freq-encode drive-window)':<34} {'68%':>10}")

best_overall = max(best['ic'], cen)
print(f"\n[verdict] best amplitude-encoding intercept: {best_overall:.0f}%")
if best_overall > 68:
    print(f"  ✓✓✓ BEATS the 68% frequency-encoding best by {best_overall-68:.0f} pts!")
elif best_overall > stat_pct + 5:
    print(f"  ✓ Beats stationary (+{best_overall-stat_pct:.0f}); not yet past 68%.")
else:
    print(f"  ✗ No advantage — check encoding channels / monotonicity.")

# ── save model (ridge path, for the live game) ──
Kf = best['K']; af = best['alpha']
sel = select_topk(Xc, tnorm, Kf) if Kf > 0 else np.arange(F)
sel = np.sort(sel)
Xs = Xc[:, sel]; mu = Xs.mean(0); sd = Xs.std(0); sd[sd < 1e-10] = 1
Xn = (Xs-mu)/sd
w = np.linalg.solve(Xn.T@Xn+af*np.eye(len(sel)), Xn.T@tnorm)
bias = tnorm.mean()-Xn.mean(0)@w
# feature spec for live game
spec = []
for o in WINDOW_OFFSETS: spec.append({'kind': 'win', 'freq': FREQ_Y, 'off': int(o)})
for o in WINDOW_OFFSETS: spec.append({'kind': 'win', 'freq': FREQ_X, 'off': int(o)})
for f in all_mode_freqs: spec.append({'kind': 'mode', 'freq': float(f)})
sel_spec = [spec[i] for i in sel]
model = {
    'timestamp': TS, 'encoding': 'amplitude_v1',
    'census_file': str(census_path) if census_path else None,
    'config': {'ch_y': CH_Y, 'freq_y': FREQ_Y, 'ch_x': CH_X, 'freq_x': FREQ_X,
               'duty_levels': DUTY, 'window_offsets': WINDOW_OFFSETS,
               'court_w': COURT_W, 'court_h': COURT_H, 'alpha': af,
               'navg': args.navg, 'settle_s': args.settle, 'target': 'track'},
    'feature_spec': sel_spec,
    'normalization': {'mu': mu.tolist(), 'sd': sd.tolist()},
    'weights': w.tolist(), 'bias': float(bias),
    'metrics': {'best_intercept': float(best_overall), 'ridge': float(best['ic']),
                'centroid': float(cen), 'stationary_pct': float(stat_pct),
                'random_pct': float(rand_pct),
                'note': f'amplitude-encode ball_y={CH_Y}@{FREQ_Y//1000}k, ball_x={CH_X}@{FREQ_X//1000}k'},
}
mp = OUT_DIR / f'pong_model_amp_{TS}.json'
json.dump(model, open(mp, 'w'), indent=2)
np.savez(OUT_DIR / f'pong_amp_data_{TS}.npz', Xc=Xc, yc=yc, xc=xc_lab, grp=grp)
print(f"\n  Model: {mp}")
print(f"  Next: python3 tools/pong_live.py --model {mp} --nco-port {args.nco_port}")
print("=" * 70)
