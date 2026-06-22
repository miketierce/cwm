#!/usr/bin/env python3
"""
IN-MOTION DECK — every card is a (position + direction) state, not a point
==========================================================================

User's redirect (2026-06-21): don't rely on ringdown to carry the past — ADD CARDS
that explicitly represent in-motion states. "If freqA is present we're travelling
north→south; if freqB (or a phase) is present, south→north. Every state is analyzed
as an in-motion state."

Why this matters (the honest thesis, and it is correct):
  A POSITION-ONLY card (x=5) maps to MANY futures — the ball could be heading either
  way, so next position is x=4 OR x=6. The state→future map is NOT a function;
  prediction is fundamentally ambiguous.
  An IN-MOTION card (x=5, heading N→S) maps to ONE future (x=6). The map becomes
  single-valued. The deck can now PREDICT — exactly the user's "narrower range of
  possible futures." Cards must be motions for the future to be a function.

Encoding (all measured on glass):
  position  → amplitude of F4@48 kHz (proven monotonic, L levels)
  direction → which TAG tone is on:  F1@57 kHz = +1 (N→S)   F2@82 kHz = −1 (S→N)
  fingerprint = windows around the driven tones + census monitor modes (distributed)
  stored future = next position = reflect(p + d) on [0, L−1] (a wall flips direction —
                  a discontinuity the deck handles as just another card)

Three predictors of NEXT POSITION (leave-one-repeat-out nearest-centroid recall):
  (A) IN-MOTION deck  — full fingerprint (position + direction tag)  → future is a function
  (B) POSITION-ONLY   — position window ONLY (direction hidden)       → ambiguous control
  (C) glass vs wire under query noise — glass=full distributed fingerprint (pattern
      completion) vs wire=driven bins only. Where the glass earns its keep.

Classical, fully measured. Uses F-switching + duty amplitude (no phase needed).

Usage:
  python3 tools/in_motion_deck.py --nco-port /dev/cu.usbmodem113401 --levels 6 --repeats 6
  python3 tools/in_motion_deck.py --dry-run
"""
import ctypes as ct
import numpy as np
import json, time, math, argparse, sys, glob
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='In-motion deck: position+direction cards, predict the future')
ap.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
ap.add_argument('--census', type=str, default=None)
ap.add_argument('--levels', type=int, default=6, help='L positions (→ 2L in-motion cards)')
ap.add_argument('--repeats', type=int, default=6)
ap.add_argument('--navg', type=int, default=8)
ap.add_argument('--settle', type=float, default=0.04)
ap.add_argument('--pos-ch', type=str, default='F4'); ap.add_argument('--pos-freq', type=int, default=48000)
ap.add_argument('--dirA-ch', type=str, default='F1'); ap.add_argument('--dirA-freq', type=int, default=57000)
ap.add_argument('--dirB-ch', type=str, default='F2'); ap.add_argument('--dirB-freq', type=int, default=82000)
ap.add_argument('--monitors', type=int, default=20)
ap.add_argument('--dry-run', action='store_true')
args = ap.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064; TIMEBASE = 7; FS = 781250.0; NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT; RNG = 6; RNG_MV = 1000.0
L = args.levels
POS = (args.pos_ch, args.pos_freq)
DIRA = (args.dirA_ch, args.dirA_freq)   # +1  (N→S)
DIRB = (args.dirB_ch, args.dirB_freq)   # −1  (S→N)
WIN = [-8, -4, -2, 0, 2, 4, 8]; NW = len(WIN)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = Path('data/results/in_motion'); OUT.mkdir(parents=True, exist_ok=True)


def duty_levels(n):
    return [round(math.asin((i + 1) / n) / math.pi * 1000) for i in range(n)]
LVL = duty_levels(L)


def reflect_next(p, d):
    """One step with wall reflection on [0,L-1]; returns next position."""
    np_ = p + d
    if np_ < 0: np_ = 1
    if np_ > L - 1: np_ = L - 2
    return int(np.clip(np_, 0, L - 1))


# in-motion states: (position, direction) ; direction index 0=+1, 1=-1
states = [(p, d) for p in range(L) for d in (+1, -1)]
K = len(states)
R = args.repeats
future = np.array([reflect_next(p, d) for (p, d) in states])   # stored next-position per card

# census monitors
def load_monitors(n):
    cp = Path(args.census) if args.census else None
    if cp is None:
        c = sorted(glob.glob('data/results/direct_wire_census/*.json')); cp = Path(c[-1]) if c else None
    if cp is None: return np.array([]), None
    cj = json.load(open(cp)); src = cj.get('all_modes') or cj.get('usable_modes') or []
    fs = sorted({float(m.get('freq', m.get('freq_hz', 0))) for m in src if m.get('freq', m.get('freq_hz', 0))})
    chosen = []
    for f in sorted(fs, key=lambda z: -z):
        if all(abs(f - g) > 2 * BIN_HZ for g in chosen): chosen.append(f)
    return np.array(sorted(chosen[:n])), (str(cp) if cp else None)
MON, MON_SRC = load_monitors(args.monitors)

print("=" * 78)
print("  IN-MOTION DECK — (position + direction) cards; predict the FUTURE")
print(f"  {L} positions × 2 directions = {K} in-motion cards × {R} repeats")
print(f"  position→{POS[0]}@{POS[1]//1000}k amp   dir+1→{DIRA[0]}@{DIRA[1]//1000}k   dir−1→{DIRB[0]}@{DIRB[1]//1000}k   monitors {len(MON)}")
print("=" * 78)


def win(spec, f):
    out = np.zeros(NW); b = int(round(f / BIN_HZ))
    for i, o in enumerate(WIN):
        k = b + o; out[i] = float(spec[max(0, k - 1):k + 2].max()) if 0 <= k < len(spec) else 0.0
    return out
def amp_at(spec, f, s=2):
    b = int(round(f / BIN_HZ)); return float(spec[max(0, b - s):min(len(spec), b + s + 1)].max())


# feature layout: [pos window NW][dirA window NW][dirB window NW][monitors]
POS_COLS = list(range(0, NW))                          # position-only readout uses just these
DRV_COLS = list(range(0, 3 * NW))                      # all driven windows = the "wire"
F = 3 * NW + len(MON)

# ─── Capture ─────────────────────────────────────────────────────────────────
if args.dry_run:
    print("\n[dry-run] synthetic: position→pos-window amp; direction→which tag window is hot;")
    print("          census modes carry a distributed (nonlinear) mix of BOTH. + noise.\n")
    rng = np.random.default_rng(0)

    def fingerprint(p, di):
        d = (+1, -1)[di]
        f = rng.standard_normal(F) * 0.10
        f[NW // 2] += (p + 1) / L * 3.0                       # position amplitude
        if d == +1: f[NW + NW // 2] += 2.5                    # dirA tag hot
        else:       f[2 * NW + NW // 2] += 2.5                # dirB tag hot
        for k in range(len(MON)):                              # distributed mix (enables completion)
            f[3 * NW + k] += math.sin(0.6 * p + 1.3 * d + 0.05 * k)
        return f

    class FakeNCO:
        def off(self): pass
    def open_hw(): return FakeNCO()
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
    if 'DUTY' not in st: print("ERROR: firmware lacks DUTY. Flash pico_nco/main.py."); sys.exit(1)
    print(f"  NCO: {st}")
    def send(c): nco.reset_input_buffer(); nco.write(f'{c}\n'.encode()); time.sleep(0.01)
    def capture():
        buf = (ct.c_int16 * N_SAMPLES)(); ov = ct.c_int16(); mags = []
        for _ in range(args.navg):
            tk = ct.c_int32(); ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(tk))
            for _ in range(500):
                if ps.ps2000_ready(handle): break
                time.sleep(0.002)
            else: continue
            ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
            d = np.array(buf[:], float) * (RNG_MV / 32767.0); d -= d.mean()
            mags.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES), n=NFFT)))
        return np.mean(mags, axis=0) if mags else np.zeros(NFFT // 2 + 1)

    def fingerprint(p, di):
        d = (+1, -1)[di]
        send('Foff'); time.sleep(0.004)
        send(f'{POS[0]}:{POS[1]}'); send(f'A{POS[0][1]}:{LVL[p]}')      # position amplitude
        if d == +1:
            send(f'{DIRA[0]}:{DIRA[1]}'); send(f'A{DIRA[0][1]}:500')    # dir tag A ON
        else:
            send(f'{DIRB[0]}:{DIRB[1]}'); send(f'A{DIRB[0][1]}:500')    # dir tag B ON
        time.sleep(args.settle)
        sp = capture()
        return np.concatenate([win(sp, POS[1]), win(sp, DIRA[1]), win(sp, DIRB[1]),
                               [amp_at(sp, f) for f in MON]])

    class W:
        def off(self): send('Foff'); time.sleep(0.02)
    def open_hw(): return W()

hw = open_hw()

# ─── Enroll ──────────────────────────────────────────────────────────────────
X = np.zeros((K * R, F)); lab = np.zeros(K * R, int); row = 0
print(f"\n[1] Enrolling {K} in-motion cards × {R} repeats...")
t0 = time.time()
for gi, (p, d) in enumerate(states):
    di = 0 if d == +1 else 1
    for r in range(R):
        X[row] = fingerprint(p, di); lab[row] = gi; row += 1
    if not args.dry_run and (gi + 1) % 4 == 0:
        print(f"    {gi+1}/{K} ({time.time()-t0:.0f}s)")
hw.off()
if not args.dry_run:
    ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))
X = X / (X.mean(1, keepdims=True) + 1e-9)   # drift-normalize

# ─── Predict NEXT POSITION by recall (leave-one-repeat-out) ──────────────────
def predict_future(cols, noise=0.0):
    """Recall nearest card on the given feature columns → return its stored future (next pos).
    Accuracy = predicted next-pos == true next-pos. leave-one-repeat-out."""
    Xc = X[:, cols]; rng = np.random.default_rng(0); hit = 0; tot = 0
    for rte in range(R):
        te = [i for i in range(K * R) if i % R == rte]; tr = [i for i in range(K * R) if i % R != rte]
        mu = Xc[tr].mean(0); sd = Xc[tr].std(0); sd[sd < 1e-9] = 1
        A = (Xc[tr] - mu) / sd
        C = np.array([A[lab[tr] == c].mean(0) for c in range(K)])
        fut_of = {c: future[c] for c in range(K)}
        for i in te:
            q = (Xc[i] - mu) / sd + (rng.standard_normal(len(cols)) * noise if noise else 0)
            c = int(np.argmin(((C - q) ** 2).sum(1)))
            hit += int(fut_of[c] == future[lab[i]]); tot += 1
    return hit / tot * 100

# position-only future: best POSSIBLE is to know p but not d → must guess one direction.
# We measure it the same way but using only the position columns, so colliding (p,+)/(p,-)
# cards fall on one centroid and recall returns a single future = inherently ~50% wrong.
allcols = np.arange(F)
inmotion = predict_future(allcols)
posonly = predict_future(np.array(POS_COLS))
# baselines
stat = np.mean(future == np.bincount(future).argmax()) * 100   # always-guess-most-common-next
chance = 100.0 / L

print(f"\n[2] PREDICT next position (recall the card → read its stored future):")
print(f"    {'predictor':<46}{'accuracy':>10}")
print(f"    {'-'*46}{'-'*10}")
print(f"    {'(A) IN-MOTION deck (position + direction)':<46}{inmotion:>9.0f}%")
print(f"    {'(B) POSITION-ONLY deck (direction hidden)':<46}{posonly:>9.0f}%")
print(f"    {'most-common-next baseline':<46}{stat:>9.0f}%")
print(f"    {'-'*46}{'-'*10}")
print(f"    → in-motion encoding adds {inmotion-posonly:+.0f} pts: the future becomes a FUNCTION.")

print(f"\n[3] Glass vs WIRE under FAIR query noise (pattern completion):")
print(f"    {'noise σ':>8}{'glass (full)':>14}{'wire (driven)':>15}")
noise_rows = []
for nz in (0.0, 0.5, 1.0, 1.5):
    g = predict_future(allcols, noise=nz)
    w = predict_future(np.array(DRV_COLS), noise=nz)
    noise_rows.append((nz, g, w)); print(f"    {nz:>8}{g:>13.0f}%{w:>14.0f}%")

print(f"\n[4] Verdict:")
if inmotion > posonly + 20:
    print(f"  ✓✓ IN-MOTION CARDS MAKE THE FUTURE PREDICTABLE: {inmotion:.0f}% vs position-only {posonly:.0f}%.")
    print(f"     Encoding direction as a card feature turns the state→future map single-valued —")
    print(f"     the user's thesis, measured. The deck of MOTIONS predicts where a deck of points cannot.")
else:
    print(f"  ~ in-motion {inmotion:.0f}% vs position-only {posonly:.0f}% — gap smaller than expected; check tag coupling.")
gn = [g for (nz, g, w) in noise_rows if nz >= 1.0]; wn = [w for (nz, g, w) in noise_rows if nz >= 1.0]
if gn and np.mean(gn) > np.mean(wn) + 8:
    print(f"  ✓ Under noisy query the glass (full fingerprint) beats the wire (driven bins) by "
          f"{np.mean(gn)-np.mean(wn):+.0f} pts = pattern completion: the distributed modes recover a corrupted direction tag.")

json.dump({'timestamp': TS, 'levels': L, 'cards': K, 'repeats': R,
           'pos': list(POS), 'dirA': list(DIRA), 'dirB': list(DIRB), 'n_monitors': int(len(MON)),
           'inmotion_acc': float(inmotion), 'positiononly_acc': float(posonly),
           'most_common_baseline': float(stat),
           'noise': [{'sigma': nz, 'glass': g, 'wire': w} for (nz, g, w) in noise_rows],
           'census': MON_SRC, 'note': 'in-motion deck: direction encoded as tag tone; future single-valued; classical'},
          open(OUT / f'in_motion_deck_{TS}.json', 'w'), indent=2)
print(f"\n    Saved: {OUT / f'in_motion_deck_{TS}.json'}")
print("=" * 78)
