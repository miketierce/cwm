#!/usr/bin/env python3
"""
IN-MOTION test — does the glass's RINGDOWN make the present contain the past?
=============================================================================

User's idea (2026-06-21): a deck card should encode an *in-motion* state, not an
*arrived* position — "like motion blur on a paused TV, every slice of the present
contains a piece of the past." The physical hook: a high-Q plate has memory. Once
you excite mode A it keeps ringing (τ = Q/πf) even after you stop driving it. So
if we drive an ORIGIN mode, then switch to drive a DESTINATION mode and capture
immediately, the single capture contains:
      DESTINATION (driven, strong)  +  ORIGIN (free ringdown, decaying tail).
The tail reveals WHERE THE STATE CAME FROM — its history / direction — from one
instantaneous read. A static snapshot (drive destination only) cannot.

THE TEST: K trajectories share the SAME destination mode but different origins.
  • STATIC  fingerprint: drive destination only  → identical for every origin →
    origin is UNRECOVERABLE (the control; should sit at chance).
  • IN-MOTION fingerprint: drive origin, switch to destination, capture → the
    origin's ringdown tail is present → origin should be RECOVERABLE.
Classify the origin (= the recent past / direction) by nearest-centroid,
leave-one-repeat-out. If in-motion >> static, the ringdown-as-motion-blur claim
is validated: the glass turns one present capture into a short history.

Also measures the TAIL PERSISTENCE: energy at the origin bin / destination bin as
a function of the dwell→capture gap = how long the past survives in the present.

Classical, fully measured. Uses existing firmware (F-switching only; no phase).

Usage:
  python3 tools/in_motion_test.py --nco-port /dev/cu.usbmodem113401
  python3 tools/in_motion_test.py --dry-run
"""
import ctypes as ct
import numpy as np
import json, time, argparse, sys
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='In-motion (ringdown-carries-history) recall test')
ap.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
ap.add_argument('--dest', type=int, default=91000, help='destination mode (shared by all trajectories)')
ap.add_argument('--origins', type=str, default='56000,86000,232000', help='origin modes (the "past" to recover)')
ap.add_argument('--tx', type=str, default='F1', help='NCO channel driving the 25mm plate (single TX is fine here)')
ap.add_argument('--repeats', type=int, default=8)
ap.add_argument('--navg', type=int, default=4, help='captures averaged (keep low — we want the FAST transient, not steady state)')
ap.add_argument('--dwell-origin', type=float, default=0.06, help='seconds to excite the origin mode before switching')
ap.add_argument('--switch-gap', type=float, default=0.0, help='extra seconds between switching to dest and capturing')
ap.add_argument('--dry-run', action='store_true')
args = ap.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064; TIMEBASE = 7; FS = 781250.0; NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT; RNG = 6; RNG_MV = 1000.0
DEST = args.dest
ORIGINS = [int(x) for x in args.origins.split(',')]
CH = args.tx
BINS = [DEST] + ORIGINS                       # feature bins: destination + each origin
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = Path('data/results/in_motion'); OUT.mkdir(parents=True, exist_ok=True)


def energy_at(spec, f, half=2):
    b = int(round(f / BIN_HZ)); return float(spec[max(0, b - half):b + half + 1].sum())


print("=" * 78)
print("  IN-MOTION TEST — does ringdown make the present contain the past?")
print(f"  destination {DEST} Hz   origins {ORIGINS}   (recover the ORIGIN = the recent past)")
print("=" * 78)

# ─── Hardware ────────────────────────────────────────────────────────────────
if args.dry_run:
    print("\n[dry-run] synthetic: dest always present; origin tail present ONLY in-motion,")
    print("          decaying with the dwell→capture gap. Validates the discriminator.\n")
    _rng = np.random.default_rng(0)
    Q = {56000: 60, 86000: 200, 91000: 150, 232000: 400}   # rough Qs (25mm notes)

    def fingerprint(origin, in_motion):
        feat = {}
        for f in BINS:
            feat[f] = 0.05 * abs(_rng.standard_normal())     # noise floor
        feat[DEST] += 1.0                                    # destination always driven
        if in_motion and origin is not None:
            tau = Q[origin] / (np.pi * origin)               # ringdown time
            gap = args.switch_gap + 0.006                    # ~capture latency
            feat[origin] += 0.9 * np.exp(-gap / tau)         # decaying origin tail
        return np.array([feat[f] * (1 + 0.03 * _rng.standard_normal()) for f in BINS])

    class FakeNCO:
        def off(self): pass
    def open_hw(): return FakeNCO()
else:
    import serial
    ps = ct.CDLL(PICO_LIB); ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"ERROR: PicoScope open failed ({handle})"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG); ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    nco = serial.Serial(args.nco_port, 115200, timeout=2); time.sleep(0.5); nco.reset_input_buffer()
    nco.write(b'STATUS\n'); time.sleep(0.2)
    print(f"  NCO: {nco.readline().decode(errors='replace').strip()}")

    def send(c):
        nco.reset_input_buffer(); nco.write(f'{c}\n'.encode()); time.sleep(0.008)

    def capture():
        buf = (ct.c_int16 * N_SAMPLES)(); ov = ct.c_int16(); mags = []
        for _ in range(args.navg):
            tk = ct.c_int32(); ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(tk))
            for _ in range(500):
                if ps.ps2000_ready(handle): break
                time.sleep(0.001)
            else:
                continue
            ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
            d = np.array(buf[:], float) * (RNG_MV / 32767.0); d -= d.mean()
            mags.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES), n=NFFT)))
        return np.mean(mags, axis=0) if mags else np.zeros(NFFT // 2 + 1)

    def fingerprint(origin, in_motion):
        if in_motion and origin is not None:
            send('Foff'); send(f'{CH}:{origin}')        # excite the ORIGIN mode
            time.sleep(args.dwell_origin)                 # let it build + start ringing
            send(f'{CH}:{DEST}')                          # switch drive to DESTINATION
            if args.switch_gap > 0:
                time.sleep(args.switch_gap)
            sp = capture()                                # capture: dest driven + origin ringing down
        else:
            send('Foff'); send(f'{CH}:{DEST}')           # STATIC: destination only
            time.sleep(args.dwell_origin)                 # same total dwell (fair)
            sp = capture()
        return np.array([energy_at(sp, f) for f in BINS])

    class W:
        def off(self): send('Foff'); time.sleep(0.02)
    def open_hw(): return W()

hw = open_hw()

# ─── Collect ─────────────────────────────────────────────────────────────────
K = len(ORIGINS); R = args.repeats
Xs = []; Xm = []; lab = []
print(f"\n[1] Enrolling {K} origins × {R} repeats, STATIC and IN-MOTION...")
t0 = time.time()
for oi, origin in enumerate(ORIGINS):
    for r in range(R):
        Xs.append(fingerprint(origin, in_motion=False))
        Xm.append(fingerprint(origin, in_motion=True))
        lab.append(oi)
    if not args.dry_run:
        print(f"    origin {origin} Hz done ({time.time()-t0:.0f}s)")
hw.off()
if not args.dry_run:
    ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))
Xs = np.array(Xs); Xm = np.array(Xm); lab = np.array(lab)

# per-capture mean normalize (drift cancel)
Xs = Xs / (Xs.mean(1, keepdims=True) + 1e-9)
Xm = Xm / (Xm.mean(1, keepdims=True) + 1e-9)


def loro_ncc(X):
    hits = 0; tot = 0
    for rte in range(R):
        te = np.array([i for i in range(len(lab)) if i % R == rte])
        tr = np.array([i for i in range(len(lab)) if i % R != rte])
        mu = X[tr].mean(0); sd = X[tr].std(0); sd[sd < 1e-9] = 1
        A = (X[tr] - mu) / sd
        C = np.array([A[lab[tr] == c].mean(0) for c in range(K)])
        for i in te:
            q = (X[i] - mu) / sd
            hits += int(np.argmin(((C - q) ** 2).sum(1)) == lab[i]); tot += 1
    return hits / tot * 100


acc_static = loro_ncc(Xs)
acc_motion = loro_ncc(Xm)
chance = 100.0 / K

# tail persistence: mean origin-bin energy fraction, in-motion vs static
def tail_frac(X):
    # for each row, energy at its OWN origin bin / energy at dest bin
    fr = []
    for i in range(len(lab)):
        o_bin = 1 + lab[i]   # BINS = [DEST, origin0, origin1, ...]
        fr.append(X[i, o_bin] / (X[i, 0] + 1e-9))
    return float(np.mean(fr))


print(f"\n[2] RECOVER THE ORIGIN (the recent past) — nearest-centroid, leave-one-repeat-out:")
print(f"    {'method':<34}{'origin recall':>14}")
print(f"    {'-'*34}{'-'*14}")
print(f"    {'STATIC (drive destination only)':<34}{acc_static:>13.0f}%")
print(f"    {'IN-MOTION (origin→dest, ringdown)':<34}{acc_motion:>13.0f}%")
print(f"    {'chance':<34}{chance:>13.0f}%")
print(f"\n    origin-tail/destination energy ratio:  static {tail_frac(Xs):.3f}   in-motion {tail_frac(Xm):.3f}")

print(f"\n[3] Verdict:")
if acc_motion > acc_static + 20 and acc_motion > chance + 20:
    print(f"  ✓✓ THE PRESENT CONTAINS THE PAST: in-motion recovers the origin at {acc_motion:.0f}% vs")
    print(f"     static {acc_static:.0f}% (≈chance {chance:.0f}%). The plate's RINGDOWN carries the trajectory's")
    print(f"     history into a single instantaneous capture — the user's motion-blur idea, measured.")
    print(f"     Cards SHOULD be motions: one read already encodes where the state came from.")
elif acc_motion > acc_static + 8:
    print(f"  ✓ In-motion beats static ({acc_motion:.0f}% vs {acc_static:.0f}%) — ringdown carries SOME history,")
    print(f"    but weakly. Tune --dwell-origin / --switch-gap / pick higher-Q origins to lengthen the tail.")
else:
    print(f"  ✗ No in-motion advantage ({acc_motion:.0f}% vs static {acc_static:.0f}%). Ringdown tail too short at")
    print(f"    these modes/timing, OR command latency outlasts τ. Honest null — needs higher-Q modes or faster switching.")

json.dump({'timestamp': TS, 'dest': DEST, 'origins': ORIGINS, 'tx': CH, 'repeats': R, 'navg': args.navg,
           'dwell_origin': args.dwell_origin, 'switch_gap': args.switch_gap,
           'acc_static': float(acc_static), 'acc_motion': float(acc_motion), 'chance': float(chance),
           'tail_frac_static': tail_frac(Xs), 'tail_frac_motion': tail_frac(Xm),
           'note': 'ringdown-as-motion-blur; classical; tests whether one capture encodes trajectory history'},
          open(OUT / f'in_motion_{TS}.json', 'w'), indent=2)
print(f"\n    Saved: {OUT / f'in_motion_{TS}.json'}")
print("=" * 78)
