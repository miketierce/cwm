#!/usr/bin/env python3
"""
PHASE-HEADING DECK — encode exact heading as relative phase; predict reflection
===============================================================================

User's idea (2026-06-21): use the phase degrees of freedom to encode an EXACT
heading angle (not a binary N/S tag), so that — combined with nearest-neighbour
recall — a boundary hit yields the EXACT reflection from the encoded angle.

This fuses the two validated results of the session:
  • in-motion deck (direction as a card feature makes the future single-valued, +17), and
  • interference cancellation (relative phase read as mode ENERGY, jitter-immune, 99.5% null).

ENCODING (all measured on glass, two co-driven TX on ONE 25mm plate: NW=F1, SW=F2):
  heading θ  →  relative phase PH2 between F1 and F2 (both at a shared mode).
  Read mode ENERGY E_k(θ) ∝ a₁²+a₂²+2a₁a₂·cos(θ − θ_k), where θ_k is that mode's
  modeshape phase between the two corners. **Both tones share t0, so jitter cancels —
  this is a magnitude readout, immune to the absolute-phase jitter problem.**

THE I/Q POINT (honest):
  One mode gives cos(θ−θ_k): SYMMETRIC, so θ and 2θ_k−θ are confused → heading is
  resolved only modulo reflection (≈180°). Reading the interference at SEVERAL modes
  with DIFFERENT θ_k recovers (cosθ, sinθ) and breaks the ambiguity → full 360°.
  Measured null phases on this plate: 91k@270°, 86k@180°, 56k@60° — well spread, a
  natural I/Q+ basis. We compare 1-mode vs multi-mode heading recall to SHOW the
  ambiguity and its fix.

PAYOFF — reflection prediction: store each heading's future = reflect across a wall
normal; recall the incoming heading; read the stored reflected heading. A deck of
HEADINGS predicts the exact bounce; a binary deck only flips a sign.

Classical acoustic interference. Path-integral STRUCTURE, not quantum.

Usage:
  python3 tools/phase_heading_deck.py --nco-port /dev/cu.usbmodem113401 --headings 12
  python3 tools/phase_heading_deck.py --dry-run
"""
import ctypes as ct
import numpy as np
import json, time, math, argparse, sys
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='Phase-encoded heading deck + reflection prediction')
ap.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
ap.add_argument('--headings', type=int, default=12, help='K headings around the full circle (360/K apart)')
ap.add_argument('--modes', type=str, default='91000,86000,56000', help='shared interference modes (different modeshape phases = I/Q)')
ap.add_argument('--repeats', type=int, default=6)
ap.add_argument('--navg', type=int, default=8)
ap.add_argument('--settle', type=float, default=0.04)
ap.add_argument('--wall-normal', type=float, default=90.0, help='wall normal angle (deg) for the reflection future')
ap.add_argument('--dry-run', action='store_true')
args = ap.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064; TIMEBASE = 7; FS = 781250.0; NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT; RNG = 6; RNG_MV = 1000.0
K = args.headings
MODES = [int(x) for x in args.modes.split(',')]
HEADINGS = [round(i * 360.0 / K) for i in range(K)]
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = Path('data/results/in_motion'); OUT.mkdir(parents=True, exist_ok=True)


def energy_at(spec, f, half=2):
    b = int(round(f / BIN_HZ)); return float(spec[max(0, b - half):b + half + 1].sum())


def reflect(theta, normal):
    """Reflect a heading across a wall whose normal points at `normal` degrees."""
    return (2 * normal - theta) % 360.0


print("=" * 78)
print("  PHASE-HEADING DECK — heading as relative phase; predict the exact bounce")
print(f"  {K} headings × {len(MODES)} interference modes {MODES}  (F1=NW, F2=SW @ each mode)")
print(f"  wall normal {args.wall_normal}° → future = reflected heading")
print("=" * 78)

# ─── Hardware ────────────────────────────────────────────────────────────────
if args.dry_run:
    print("\n[dry-run] synthetic: E_k(θ)=base(1+ρcos(θ−θ_k)); θ_k from measured nulls (270/180/60).\n")
    _rng = np.random.default_rng(0)
    THETA_K = {91000: 270.0, 86000: 180.0, 56000: 60.0}

    def read_mode(mode, theta, d1=500, d2=500):
        th_k = THETA_K.get(mode, 0.0)
        base = 1.0; rho = 0.95
        E = base * (1 + rho * math.cos(math.radians(theta - th_k))) * 4000.0
        return E * (1 + 0.02 * _rng.standard_normal()) + 50.0

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
    if 'PHA:' not in st: print("ERROR: firmware lacks PHA (per-channel phase). Flash pico_nco/main.py."); sys.exit(1)
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

    def read_mode(mode, theta, d1=500, d2=500):
        # heading = relative phase between the two corners co-driven at `mode`
        send('Foff'); time.sleep(0.003)
        send(f'F1:{mode}'); send(f'A1:{int(d1)}')
        send(f'F2:{mode}'); send(f'A2:{int(d2)}')
        send('PH1:0'); send(f'PH2:{theta % 360}')
        time.sleep(args.settle)
        return energy_at(capture(), mode)

    class W:
        def off(self): send('Foff'); time.sleep(0.02)
    def open_hw(): return W()

hw = open_hw()

# ─── Enroll: fingerprint per heading = interference energy at each mode ───────
R = args.repeats
M = len(MODES)
X = np.zeros((K * R, M)); lab = np.zeros(K * R, int); row = 0
print(f"\n[1] Enrolling {K} headings × {R} repeats ({M} modes each)...")
t0 = time.time()
for hi, theta in enumerate(HEADINGS):
    for r in range(R):
        X[row] = [read_mode(m, theta) for m in MODES]; lab[row] = hi; row += 1
    if not args.dry_run and (hi + 1) % 3 == 0:
        print(f"    {hi+1}/{K} ({time.time()-t0:.0f}s)")
hw.off()
if not args.dry_run:
    ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))

# normalize each mode column to unit scale (modes have different absolute energy)
Xn = (X - X.mean(0)) / (X.std(0) + 1e-9)
future = np.array([reflect(t, args.wall_normal) for t in HEADINGS])   # stored bounce per heading


def recall_predict(cols, target='heading', noise=0.0):
    """leave-one-repeat-out nearest-centroid. target='heading' → recover which heading;
    'reflection' → recall card, return its stored reflected heading, score vs true reflection."""
    Xc = Xn[:, cols]; rng = np.random.default_rng(0); hit = 0; tot = 0; ang_err = []
    for rte in range(R):
        te = [i for i in range(K * R) if i % R == rte]; tr = [i for i in range(K * R) if i % R != rte]
        C = np.array([Xc[[i for i in tr if lab[i] == c]].mean(0) for c in range(K)])
        for i in te:
            q = Xc[i] + (rng.standard_normal(len(cols)) * noise if noise else 0)
            c = int(np.argmin(((C - q) ** 2).sum(1)))
            if target == 'heading':
                hit += int(c == lab[i])
                de = abs(((HEADINGS[c] - HEADINGS[lab[i]] + 180) % 360) - 180); ang_err.append(de)
            else:  # reflection prediction
                hit += int(future[c] == future[lab[i]])
                de = abs(((future[c] - future[lab[i]] + 180) % 360) - 180); ang_err.append(de)
            tot += 1
    return hit / tot * 100, float(np.mean(ang_err))


print(f"\n[2] HEADING recall — 1 mode (ambiguous) vs all {M} modes (I/Q breaks it):")
print(f"    {'readout':<34}{'exact':>8}{'mean ang err':>14}")
print(f"    {'-'*34}{'-'*8}{'-'*14}")
acc1, err1 = recall_predict([0], 'heading')
print(f"    {'1 mode ('+str(MODES[0])+' Hz only)':<34}{acc1:>7.0f}%{err1:>12.0f}°")
if M >= 2:
    acc2, err2 = recall_predict([0, 1], 'heading')
    print(f"    {'2 modes (I/Q pair)':<34}{acc2:>7.0f}%{err2:>12.0f}°")
accA, errA = recall_predict(list(range(M)), 'heading')
print(f"    {'all '+str(M)+' modes':<34}{accA:>7.0f}%{errA:>12.0f}°")
chance = 100.0 / K
print(f"    {'chance':<34}{chance:>7.0f}%{'-':>13}")

print(f"\n[3] REFLECTION prediction (recall heading → read stored bounce), all {M} modes:")
accR, errR = recall_predict(list(range(M)), 'reflection')
print(f"    exact reflection recalled: {accR:.0f}%   mean angular error {errR:.0f}°")

print(f"\n[4] Robustness — heading recall under FAIR query noise (all modes):")
print(f"    {'noise σ':>8}{'exact':>8}{'ang err':>10}")
noise_rows = []
for nz in (0.0, 0.5, 1.0):
    a, e = recall_predict(list(range(M)), 'heading', noise=nz)
    noise_rows.append((nz, a, e)); print(f"    {nz:>8}{a:>7.0f}%{e:>9.0f}°")

print(f"\n[5] Verdict:")
iq_gain = (acc2 - acc1) if M >= 2 else 0
if accA > chance + 25 and (M < 2 or accA >= acc1):
    print(f"  ✓✓ PHASE ENCODES HEADING: {accA:.0f}% exact heading recall ({errA:.0f}° mean error) on {K} headings,")
    print(f"     read jitter-free as interference energy. The user's idea — heading as relative phase — measured.")
    if M >= 2 and iq_gain > 8:
        print(f"  ✓ I/Q CONFIRMED: 1 mode {acc1:.0f}% → multi-mode {accA:.0f}% (+{accA-acc1:.0f}). A second modeshape")
        print(f"     phase breaks the cos(θ) reflection ambiguity — full 360° heading, exactly as predicted.")
    elif M >= 2:
        print(f"  ~ multi-mode ≈ 1-mode here ({accA:.0f}% vs {acc1:.0f}%); modeshape phases may be too similar for clean I/Q.")
    print(f"  → reflection prediction {accR:.0f}%: a deck of HEADINGS yields the exact bounce, not just a sign flip.")
else:
    print(f"  ~ heading recall {accA:.0f}% (chance {chance:.0f}%) — phase carries heading but coarsely; check mode coupling/balance.")

json.dump({'timestamp': TS, 'headings': HEADINGS, 'modes': MODES, 'repeats': R, 'navg': args.navg,
           'wall_normal': args.wall_normal,
           'heading_acc_1mode': float(acc1), 'heading_acc_allmodes': float(accA),
           'heading_acc_2mode': float(acc2) if M >= 2 else None,
           'heading_ang_err_allmodes': float(errA),
           'reflection_acc': float(accR), 'reflection_ang_err': float(errR),
           'noise': [{'sigma': nz, 'acc': a, 'ang_err': e} for (nz, a, e) in noise_rows],
           'note': 'heading=relative phase read as interference energy (jitter-free); multi-mode=I/Q for 360; classical'},
          open(OUT / f'phase_heading_{TS}.json', 'w'), indent=2)
print(f"\n    Saved: {OUT / f'phase_heading_{TS}.json'}")
print("=" * 78)
