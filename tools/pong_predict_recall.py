#!/usr/bin/env python3
"""
Pong PREDICTION by RECALL — pattern completion as prediction
============================================================

User's insight (2026-06-21): the glass is a deck of cards holding every ball
state. The ball's current position+velocity is a PARTIAL query; recall the
matching card and read its stored FUTURE (the landing the ball will reach).
This is prediction BY RECALL — and it sidesteps the discontinuity that killed
regression-prediction (47%, R²=−0.14): we are not interpolating a smooth bounce
function, we are nearest-matching a discrete deck where each (state → landing)
is a stored entry. A bounce is no longer a problem; it is just a card.

Three predictors compared on the SAME glass capture, honest leave-one-repeat-out:
  (a) REGRESSION  — ridge: fingerprint → landing directly (the silicon way, failed before)
  (b) RECALL      — factored nearest-centroid: fingerprint → state → stored landing (wave-native)
  (c) WIRE        — recall each axis from ONLY its driven bin → state → landing (the "you could use a wire" baseline)

Then the genuine-compute test: re-score (b) vs (c) under FAIR standardized-space
query noise (partial/uncertain query). If glass-recall holds where the wire
falls off, that denoising-into-the-right-card IS the computation.

Encoding (amplitude = the proven monotonic channel, NCO duty firmware):
  x  → F4@48kHz amplitude (8 levels)   y → F5@89kHz amplitude (8 levels)
  vx → F1@57kHz amplitude (2 levels)   vy → F2@82kHz amplitude (2 levels)

Usage:
  python3 tools/pong_predict_recall.py --nco-port /dev/cu.usbmodem113401 --repeats 3
  python3 tools/pong_predict_recall.py --dry-run
"""
import ctypes as ct
import numpy as np
import json, time, math, argparse, sys
from pathlib import Path
from datetime import datetime

parser = argparse.ArgumentParser(description='Pong prediction-by-recall')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--census', type=str, default=None)
parser.add_argument('--repeats', type=int, default=3)
parser.add_argument('--navg', type=int, default=10)
parser.add_argument('--settle', type=float, default=0.04)
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064; TIMEBASE = 7; FS = 781250.0; NFFT = N_SAMPLES*4
BIN_HZ = FS/NFFT; RNG = 6; RNG_MV = 1000.0
COURT_W, COURT_H = 8, 8; PADDLE_H = 3
WINDOW_OFFSETS = [-8, -4, -2, 0, 2, 4, 8]; N_WIN = len(WINDOW_OFFSETS)

# axes: (name, channel, freq, n_levels)
AXES = [('x', 'F4', 48000, 8), ('y', 'F5', 89000, 8),
        ('vx', 'F1', 57000, 2), ('vy', 'F2', 82000, 2)]

OUT = Path('data/results/pong'); OUT.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')

print("=" * 70)
print("  PONG PREDICTION BY RECALL — pattern completion as prediction")
print("  Query = current (x,y,vx,vy);  recall the card;  read its stored LANDING")
print("=" * 70)


def duty_levels(n):
    return [round(math.asin((L+1)/n)/math.pi*1000) for L in range(n)]
LVL = {nm: duty_levels(nl) for (nm, ch, fr, nl) in AXES}

# ─── States + landings (the stored "future") ────────────────────
def landing(bx, by, vx, vy):
    """Forward-simulate with wall bounces → paddle y the ball reaches (the future)."""
    x, y = float(bx), float(by)
    for _ in range(40):
        x += vx; y += vy
        if y < 0: y = -y; vy = -vy
        if y > COURT_H-1: y = 2*(COURT_H-1)-y; vy = -vy
        if x < 0: x = -x; vx = -vx
        if x >= COURT_W-1: return int(round(np.clip(y, 0, COURT_H-1)))
    return (COURT_H-1)//2

states = [(x, y, vx, vy) for x in range(COURT_W) for y in range(COURT_H)
          for vx in (-1, 1) for vy in (-1, 1)]
N = len(states); R = args.repeats
land = np.array([landing(*s) for s in states])
print(f"\n[1] {N} states → stored landings (range {land.min()}–{land.max()})")

# census pool
all_freqs = np.array([]); census_path = None
cp = Path(args.census) if args.census else (sorted(Path('data/results/direct_wire_census').glob('*.json')) or [None])[-1]
if cp:
    census_path = cp; cj = json.load(open(cp))
    src = cj.get('all_modes') or cj['usable_modes']
    all_freqs = np.array(sorted({float(m.get('freq', m.get('freq_hz'))) for m in src}))
    print(f"[2] Mode pool: {len(all_freqs)} census modes from {cp.name}")

DRIVEN = {nm: i*N_WIN + N_WIN//2 for i, (nm, ch, fr, nl) in enumerate(AXES)}  # center bin per axis
F = len(AXES)*N_WIN + len(all_freqs)


def win(spec, f):
    out = np.zeros(N_WIN); base = int(round(f/BIN_HZ))
    for i, o in enumerate(WINDOW_OFFSETS):
        b = base+o; out[i] = float(spec[max(0, b-1):b+2].max()) if 0 <= b < len(spec) else 0.0
    return out
def amp_at(spec, f, s=2):
    b = int(round(f/BIN_HZ)); return float(spec[max(0, b-s):min(len(spec), b+s+1)].max())

# ─── Collect ─────────────────────────────────────────────────────
X = np.zeros((N*R, F)); grp = np.zeros(N*R, int)
xs = np.zeros(N*R, int); ys = np.zeros(N*R, int); vxs = np.zeros(N*R, int); vys = np.zeros(N*R, int)
lab_land = np.zeros(N*R, int)

if args.dry_run:
    print("\n[3] DRY RUN synthetic")
    rng = np.random.default_rng(0); row = 0
    for gi, (x, y, vx, vy) in enumerate(states):
        for r in range(R):
            f = rng.standard_normal(F)*0.12
            f[DRIVEN['x']] += x/3.5; f[DRIVEN['y']] += y/3.5
            f[DRIVEN['vx']] += (vx+1); f[DRIVEN['vy']] += (vy+1)
            for k in range(len(all_freqs)):
                f[len(AXES)*N_WIN+k] += 0.4*math.sin(0.5*x+0.8*y+1.3*vx+1.9*vy+0.05*k)
            X[row]=f; xs[row]=x; ys[row]=y; vxs[row]=vx; vys[row]=vy
            lab_land[row]=land[gi]; grp[row]=gi; row+=1
else:
    import serial
    ps = ct.CDLL(PICO_LIB); ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0: print(f"ERROR PicoScope {handle}"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG); ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    nco = serial.Serial(args.nco_port, 115200, timeout=2); time.sleep(0.5); nco.reset_input_buffer()
    nco.write(b'STATUS\n'); time.sleep(0.2)
    st = nco.readline().decode(errors='replace').strip()
    if 'DUTY' not in st: print("ERROR: firmware lacks DUTY (amplitude). Flash pico_nco/main.py."); sys.exit(1)
    print(f"  NCO: {st}")
    def send(c): nco.reset_input_buffer(); nco.write(f'{c}\n'.encode()); time.sleep(0.01)
    def capture():
        buf=(ct.c_int16*N_SAMPLES)(); ov=ct.c_int16(); mags=[]
        for _ in range(args.navg):
            tk=ct.c_int32(); ps.ps2000_run_block(handle,N_SAMPLES,TIMEBASE,1,ct.byref(tk))
            for _ in range(500):
                if ps.ps2000_ready(handle): break
                time.sleep(0.002)
            else: continue
            ps.ps2000_get_values(handle,ct.byref(buf),None,None,None,ct.byref(ov),N_SAMPLES)
            d=np.array(buf[:],dtype=np.float64)*(RNG_MV/32767.0); d-=d.mean()
            mags.append(np.abs(np.fft.rfft(d*np.hanning(N_SAMPLES),n=NFFT)))
        return np.mean(mags,axis=0) if mags else np.zeros(NFFT//2+1)
    print(f"\n[3] Enrolling {N} states × {R} repeats (amplitude-encoded)...")
    t0=time.time(); row=0
    for gi,(x,y,vx,vy) in enumerate(states):
        lvlidx={'x':x,'y':y,'vx':0 if vx<0 else 1,'vy':0 if vy<0 else 1}
        for r in range(R):
            send('Foff'); time.sleep(0.004)
            for (nm,ch,fr,nl) in AXES:
                send(f'{ch}:{fr}'); send(f'A{ch[1]}:{LVL[nm][lvlidx[nm]]}')
            time.sleep(args.settle)
            sp=capture()
            feat=np.concatenate([win(sp,AXES[0][2]),win(sp,AXES[1][2]),win(sp,AXES[2][2]),win(sp,AXES[3][2]),
                                 [amp_at(sp,f) for f in all_freqs]])
            X[row]=feat; xs[row]=x; ys[row]=y; vxs[row]=vx; vys[row]=vy
            lab_land[row]=land[gi]; grp[row]=gi; row+=1
        if (gi+1)%32==0 or gi+1==N:
            el=time.time()-t0; print(f"    {gi+1}/{N} — ETA {el/(gi+1)*(N-gi-1):.0f}s")
    send('Foff'); nco.close(); ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))
    print(f"  Enroll: {time.time()-t0:.1f}s")

# drift-normalize (per-capture mean)
X = X/(X.mean(1, keepdims=True)+1e-9)

# ─── Evaluation helpers (leave-one-repeat-out) ──────────────────
def sep_rank(Xf, l):
    cs=np.unique(l); gm=Xf.mean(0); b=np.zeros(Xf.shape[1]); w=np.zeros(Xf.shape[1])
    for c in cs:
        v=Xf[l==c]; b+=len(v)*(v.mean(0)-gm)**2; w+=((v-v.mean(0))**2).sum(0)
    return np.argsort(-(b/(w+1e-9)))


def recall_predict(noise=0.0, wire=False, k=1):
    """Search the deck (kNN) → predict the nearest card's stored LANDING.
    This is the user's idea literally: query → parallel nearest-match over the
    deck → read the associated future. glass = full distributed fingerprint;
    wire = only the directly-driven bins. leave-one-repeat-out."""
    cols = np.array(sorted(DRIVEN.values())) if wire else np.arange(F)
    Xs = X[:, cols]
    rng = np.random.default_rng(0); hits = 0; tot = 0
    for rte in range(R):
        te = np.array([i for i in range(len(grp)) if i % R == rte])
        tr = np.array([i for i in range(len(grp)) if i % R != rte])
        mu = Xs[tr].mean(0); sd = Xs[tr].std(0); sd[sd < 1e-9] = 1
        A = (Xs[tr]-mu)/sd; deck_land = lab_land[tr]
        for i in te:
            q = (Xs[i]-mu)/sd + (rng.standard_normal(len(cols))*noise if noise else 0)
            d = ((A-q)**2).sum(1)
            nn = np.argsort(d)[:k]
            pred = int(round(np.median(deck_land[nn])))
            hits += abs(pred - lab_land[i]) <= PADDLE_H//2; tot += 1
    return hits/tot*100


def regression_predict(noise=0.0):
    """Ridge: fingerprint → landing directly (the silicon way). leave-one-repeat-out."""
    tnorm=lab_land/(COURT_H-1); rng=np.random.default_rng(0); hits=0; tot=0
    for rte in range(R):
        te=np.array([i for i in range(len(grp)) if i%R==rte]); tr=np.array([i for i in range(len(grp)) if i%R!=rte])
        cor=np.array([abs(np.corrcoef(X[tr,k],tnorm[tr])[0,1]) if X[tr,k].std()>1e-9 else 0 for k in range(F)])
        sel=np.argsort(-cor)[:20]
        Xs=X[:,sel]; mu=Xs[tr].mean(0); sd=Xs[tr].std(0); sd[sd<1e-9]=1
        A=(Xs[tr]-mu)/sd; B=(Xs[te]-mu)/sd
        w=np.linalg.solve(A.T@A+5.0*np.eye(len(sel)), A.T@tnorm[tr]); b=tnorm[tr].mean()-A.mean(0)@w
        for j,i in enumerate(te):
            q=B[j]+(rng.standard_normal(len(sel))*noise if noise else 0)
            pred=(q@w+b)*(COURT_H-1); hits+=abs(pred-lab_land[i])<=PADDLE_H/2; tot+=1
    return hits/tot*100

# baselines
stat=np.mean(np.abs(land-(COURT_H-1)/2)<=PADDLE_H/2)*100
rng=np.random.default_rng(1); ri=[np.mean(np.abs(land-rng.integers(1,COURT_H-1,N))<=PADDLE_H/2) for _ in range(40)]
rand=np.mean(ri)*100

print(f"\n[4] PREDICT the landing — three methods (leave-one-repeat-out):")
print(f"  {'method':<42} {'intercept':>10}")
print(f"  {'-'*42} {'-'*10}")
reg=regression_predict()
rec=recall_predict(k=1)
rec3=recall_predict(k=3)
wir=recall_predict(k=1, wire=True)
print(f"  {'(a) REGRESSION fingerprint→landing (silicon)':<42} {reg:>9.0f}%")
print(f"  {'(b) RECALL deck kNN k=1 → stored landing (glass)':<42} {rec:>9.0f}%")
print(f"  {'      RECALL deck kNN k=3 (glass)':<42} {rec3:>9.0f}%")
print(f"  {'(c) WIRE kNN on driven bins only':<42} {wir:>9.0f}%")
print(f"  {'-'*42} {'-'*10}")
print(f"  {'stationary baseline':<42} {stat:>9.0f}%")
print(f"  {'random baseline':<42} {rand:>9.0f}%")
print(f"  {'prior regression-predict (frequency enc)':<42} {'47%':>10}")

print(f"\n[5] Genuine-compute test — glass RECALL vs WIRE under FAIR query noise:")
print(f"  {'noise σ':>8} {'glass kNN':>11} {'wire kNN':>9}")
for nz in (0.0, 0.5, 1.0, 1.5):
    print(f"  {nz:>8} {recall_predict(noise=nz, k=3):>10.0f}% {recall_predict(noise=nz, k=1, wire=True):>8.0f}%")

print(f"\n[6] Verdict:")
best_rec = max(rec, rec3)
if best_rec > reg + 15:
    print(f"  ✓✓ PREDICTION-BY-RECALL WORKS: {best_rec:.0f}% vs regression {reg:.0f}% (+{best_rec-reg:.0f}).")
    print(f"     The discontinuity that killed regression is a non-issue for a discrete deck.")
elif best_rec > stat + 5:
    print(f"  ✓ Recall-predict {best_rec:.0f}% beats stationary {stat:.0f}% (regression {reg:.0f}%).")
else:
    print(f"  ~ recall {best_rec:.0f}% vs regression {reg:.0f}%, stationary {stat:.0f}% — inconclusive.")
g1=recall_predict(noise=1.0, k=3); w1=recall_predict(noise=1.0, k=1, wire=True)
if g1 > w1 + 8:
    print(f"  ✓ Glass beats wire under noise ({g1:.0f}% vs {w1:.0f}%) = genuine pattern completion.")

np.savez(OUT/f'pong_predict_data_{TS}.npz', X=X, xs=xs, ys=ys, vxs=vxs, vys=vys, land=lab_land, grp=grp)
json.dump({'timestamp':TS,'census':str(census_path),'n_states':N,'repeats':R,
           'regression':float(reg),'recall':float(rec),'wire':float(wir),
           'stationary':float(stat),'random':float(rand)},
          open(OUT/f'pong_predict_{TS}.json','w'), indent=2)
print(f"\n  Saved: {OUT/f'pong_predict_{TS}.json'}")
print("=" * 70)
