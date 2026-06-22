#!/usr/bin/env python3
"""
CAM phase test — does MEASURED glass phase add separability over magnitude?
===========================================================================

First use of the Ch B reference (Za/Zb, proven ~10° after the 4K7 rework) inside
the recall pipeline. We enroll amplitude-encoded states, capture the COMPLEX
transfer H = Za/Zb at each driven bin (clean phase) plus magnitude at census
monitor modes, and ask one honest question:

    Does adding the measured PHASE to the fingerprint improve state separability
    /recall over MAGNITUDE alone?

Three feature sets, identical states, leave-one-repeat-out nearest-centroid:
  (M)  magnitude only  — |H| at driven bins + |Za| at monitor modes (current pipeline)
  (P)  phase only      — (cos,sin) of arg(H) at driven bins (circular-safe)
  (M+P) both

We ALSO report per-feature Fisher separability so we can SEE whether any phase
feature carries state information, independent of the classifier.

HONEST PRIOR (stated before the run, not tuned away): for a LINEAR plate with
amplitude encoding at separated frequencies, arg(H) at a driven bin is the
plate's transfer phase — fixed by geometry, INDEPENDENT of drive amplitude. So
phase should add little UNLESS cross-coupling (other plates' off-resonance tails
summing on the shared RX bus) or nonlinearity makes a bin's phase depend on the
amplitude state. To give phase a fair chance we drive EXTRA fixed-amplitude tones
(F1,F2) whose magnitude is constant across states — so any state-dependence in
THEIR phase is pure cross-coupling = phase-only information, the cleanest possible
test. Phase here is CLASSICAL acoustic phase, not quantum.

Usage:
  python3 tools/cam_phase_test.py --nco-port /dev/cu.usbmodem113401 --levels 4 --repeats 6
  python3 tools/cam_phase_test.py --dry-run
"""
import ctypes as ct
import numpy as np
import json, time, math, argparse, sys, glob
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='Does measured glass phase add CAM separability?')
ap.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
ap.add_argument('--census', type=str, default=None)
ap.add_argument('--levels', type=int, default=4, help='amplitude levels per varied axis (x,y) → levels^2 states')
ap.add_argument('--repeats', type=int, default=6, help='enrollment captures per state (leave-one-repeat-out)')
ap.add_argument('--navg', type=int, default=16, help='sub-captures averaged into one complex fingerprint')
ap.add_argument('--settle', type=float, default=0.045)
ap.add_argument('--chb-range', type=int, default=8, help='Ch B range index (drive tap). 4 summed tones → use 8 (±5V) or 9.')
ap.add_argument('--monitors', type=int, default=24, help='strongest census modes for magnitude features')
ap.add_argument('--dry-run', action='store_true')
args = ap.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 3072; TIMEBASE = 7; FS = 781250.0; NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT; RNG = 6; RNG_MV = 1000.0
RANGE_MV = {1: 20, 2: 50, 3: 100, 4: 200, 5: 500, 6: 1000, 7: 2000, 8: 5000, 9: 10000, 10: 20000}
CHB_MV = RANGE_MV.get(args.chb_range, 1000)

# Varied axes (carry state in amplitude) + fixed axes (constant amplitude → phase-only probe)
VARIED = [('x', 'F4', 48000), ('y', 'F5', 89000)]
FIXED = [('p', 'F1', 57000), ('q', 'F2', 82000)]   # driven at constant amplitude; their phase tests cross-coupling
ALL_DRIVEN = VARIED + FIXED
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = Path('data/results/cam_phase'); OUT.mkdir(parents=True, exist_ok=True)


def duty_levels(n):
    return [round(math.asin((L + 1) / n) / math.pi * 1000) for L in range(n)]


def bin_of(f):
    return int(round(f / BIN_HZ))


def peak_bin(mag, f, s=4):
    b = bin_of(f); lo = max(0, b - s); hi = min(len(mag), b + s + 1)
    return lo + int(np.argmax(mag[lo:hi]))


L = args.levels
LVL = duty_levels(L)
FIXED_DUTY = 500
states = [(x, y) for x in range(L) for y in range(L)]
N = len(states); R = args.repeats

# monitor modes (magnitude features) from census
def load_monitors(n):
    cp = Path(args.census) if args.census else None
    if cp is None:
        c = sorted(glob.glob('data/results/direct_wire_census/*.json'))
        cp = Path(c[-1]) if c else None
    if cp is None:
        return np.array([]), None
    cj = json.load(open(cp)); src = cj.get('all_modes') or cj.get('usable_modes') or []
    modes = sorted({float(m.get('freq', m.get('freq_hz', 0))) for m in src if m.get('freq', m.get('freq_hz', 0))})
    chosen = []
    for f in sorted(modes, key=lambda z: -z):  # spread; de-dup within 2 bins
        if all(abs(f - g) > 2 * BIN_HZ for g in chosen):
            chosen.append(f)
    return np.array(sorted(chosen[:n])), (str(cp) if cp else None)


MON, MON_SRC = load_monitors(args.monitors)

print("=" * 76)
print("  CAM PHASE TEST — does measured glass phase add separability over magnitude?")
print(f"  {N} states ({L}×{L} amplitude grid) × {R} repeats   driven: "
      f"{[d[1] for d in ALL_DRIVEN]}   monitors: {len(MON)}")
print(f"  varied(amp→state): {[d[1] for d in VARIED]}   fixed(phase-only probe): {[d[1] for d in FIXED]}")
print("=" * 76)

# Feature index bookkeeping
n_dr = len(ALL_DRIVEN)
# magnitude features: |H| at each driven bin + |Za| at each monitor mode
# phase features:     cos,sin of arg(H) at each driven bin
IDX = {}


# ─── Capture ─────────────────────────────────────────────────────────────────
if args.dry_run:
    print("\n[dry-run] synthetic: linear plates (phase state-independent) + a SMALL cross-coupling")
    print("          term so F1/F2 phase carries a little state — to verify the test can detect it.\n")
    _rng = np.random.default_rng(0)
    # fixed 'true' transfer phase per driven freq (geometry); magnitude ∝ amplitude
    _argH = {d[2]: _rng.uniform(-np.pi, np.pi) for d in ALL_DRIVEN}

    def capture_state(x, y):
        amps = {VARIED[0][2]: (x + 1) / L, VARIED[1][2]: (y + 1) / L,
                FIXED[0][2]: 1.0, FIXED[1][2]: 1.0}
        zamag = []; argH = []
        for d in ALL_DRIVEN:
            f = d[2]
            # |Za| (plate response) ∝ this tone's amplitude = the STATE
            za = amps[f] * (1.0 + 0.05 * _rng.standard_normal())
            # arg(Za/Zb) = geometry phase (state-independent) + SMALL cross-coupling from varied tones
            ph = _argH[f]
            for v in VARIED:
                if v[2] != f:
                    ph += 0.30 * amps[v[2]]    # cross-coupling shifts phase a little with state
            zamag.append(za); argH.append(ph + 0.04 * _rng.standard_normal())
        monmag = np.array([0.5 + 0.4 * math.sin(0.6 * x + 1.1 * y + 0.05 * k) for k in range(len(MON))])
        return np.array(zamag), np.array(argH), monmag, {'chB_peak': 0.4, 'clipB': 0}

    def open_hw():
        class F:
            def set(self, *a): pass
            def off(self): pass
        return F()
else:
    import serial
    ps = ct.CDLL(PICO_LIB); ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"ERROR: PicoScope open failed ({handle})"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)              # Ch A plate (RX)
    ps.ps2000_set_channel(handle, 1, 1, 0, args.chb_range)   # Ch B drive tap
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)             # free-run; Za/Zb removes jitter
    print(f"  PicoScope handle={handle}  Ch A ±{RNG_MV}mV (plate)  Ch B ≈±{CHB_MV}mV (drive tap)")

    _nco = serial.Serial(args.nco_port, 115200, timeout=2); time.sleep(0.5); _nco.reset_input_buffer()
    _nco.write(b'STATUS\n'); time.sleep(0.2)
    st = _nco.readline().decode(errors='replace').strip()
    if 'DUTY' not in st:
        print("ERROR: firmware lacks DUTY — flash tools/pico_nco/main.py"); sys.exit(1)
    print(f"  NCO: {st}")

    def send(c):
        _nco.reset_input_buffer(); _nco.write(f'{c}\n'.encode()); time.sleep(0.012)

    def capture_AB(navg):
        bufA = (ct.c_int16 * N_SAMPLES)(); bufB = (ct.c_int16 * N_SAMPLES)(); ov = ct.c_int16()
        w = np.hanning(N_SAMPLES); A = []; B = []; clipB = 0; peakB = 0.0
        for _ in range(navg):
            tk = ct.c_int32(); ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(tk))
            for _ in range(500):
                if ps.ps2000_ready(handle): break
                time.sleep(0.002)
            else:
                continue
            ps.ps2000_get_values(handle, ct.byref(bufA), ct.byref(bufB), None, None, ct.byref(ov), N_SAMPLES)
            ra = np.array(bufA[:], float); rb = np.array(bufB[:], float)
            pk = np.abs(rb).max() / 32767.0; peakB = max(peakB, pk)
            if (ov.value & 2) or pk > 0.999: clipB += 1
            da = ra * (RNG_MV / 32767.0); da -= da.mean()
            db = rb * (CHB_MV / 32767.0); db -= db.mean()
            A.append(np.fft.rfft(da * w, n=NFFT)); B.append(np.fft.rfft(db * w, n=NFFT))
        return np.array(A), np.array(B), {'chB_peak': peakB, 'clipB': clipB}

    def capture_state(x, y):
        send('Foff'); time.sleep(0.005)
        # varied axes carry state in amplitude; fixed axes at constant amplitude
        send(f'{VARIED[0][1]}:{VARIED[0][2]}'); send(f'A{VARIED[0][1][1]}:{LVL[x]}')
        send(f'{VARIED[1][1]}:{VARIED[1][2]}'); send(f'A{VARIED[1][1][1]}:{LVL[y]}')
        for d in FIXED:
            send(f'{d[1]}:{d[2]}'); send(f'A{d[1][1]}:{FIXED_DUTY}')
        time.sleep(args.settle)
        A, B, diag = capture_AB(args.navg)
        magA = np.abs(A).mean(0)
        zamag = []; argH = []
        for d in ALL_DRIVEN:
            bm = peak_bin(magA, d[2]); Za = A[:, bm]; Zb = B[:, bm]
            zamag.append(float(np.abs(Za).mean()))     # |Za| = plate response ∝ drive amplitude = STATE
            argH.append(float(np.angle((Za / Zb).mean())))  # arg(Za/Zb) = jitter-free phase
        monmag = np.array([float(magA[max(0, bin_of(f) - 2):bin_of(f) + 3].max()) for f in MON])
        return np.array(zamag), np.array(argH), monmag, diag

    def open_hw():
        class W:
            def off(self): send('Foff'); time.sleep(0.02)
        return W()

# ─── Enroll ──────────────────────────────────────────────────────────────────
hw = open_hw(); hw.off()
mag_feats = []; pha_feats = []; labels = []; grp = []
chB_peaks = []; clipB_total = 0
t0 = time.time()
print(f"\n[enroll] {N} states × {R} repeats (complex Za/Zb)...")
for gi, (x, y) in enumerate(states):
    for r in range(R):
        zamag, argH, monmag, diag = capture_state(x, y)
        chB_peaks.append(diag['chB_peak']); clipB_total += diag['clipB']
        mag_feats.append(np.concatenate([zamag, monmag]))          # |Za| driven + |Za| monitors (carries amp state)
        pha_feats.append(np.concatenate([np.cos(argH), np.sin(argH)]))  # circular-safe jitter-free phase
        labels.append(gi); grp.append(gi)
    if not args.dry_run and ((gi + 1) % 4 == 0 or gi + 1 == N):
        el = time.time() - t0; print(f"    {gi+1}/{N} — ETA {el/(gi+1)*(N-gi-1):.0f}s")
hw.off()
if not args.dry_run:
    ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))

Mag = np.array(mag_feats); Pha = np.array(pha_feats)
labels = np.array(labels); grp = np.array(grp)
# per-capture mean normalization on magnitude (drift cancel, the proven trick); phase already drift-free via Za/Zb
Mag = Mag / (Mag.mean(1, keepdims=True) + 1e-9)
n_magdriven = len(ALL_DRIVEN)

print(f"\n[Ch B health] peak median {100*np.median(chB_peaks):.0f}% FS, clipB {clipB_total} "
      f"{'(RAISE --chb-range!)' if clipB_total else 'ok'}")

# ─── Evaluation: leave-one-repeat-out nearest-centroid ──────────────────────
def loro_ncc(Xf):
    if Xf.shape[1] == 0:
        return 0.0
    hits = 0; tot = 0
    for rte in range(R):
        te = np.array([i for i in range(len(grp)) if i % R == rte])
        tr = np.array([i for i in range(len(grp)) if i % R != rte])
        mu = Xf[tr].mean(0); sd = Xf[tr].std(0); sd[sd < 1e-9] = 1
        A = (Xf[tr] - mu) / sd
        C = np.array([A[labels[tr] == c].mean(0) for c in range(N)])
        for i in te:
            q = (Xf[i] - mu) / sd
            hits += int(np.argmin(((C - q) ** 2).sum(1)) == labels[i]); tot += 1
    return hits / tot * 100


def fisher(col):
    gm = col.mean(); b = 0.0; w = 0.0
    for c in range(N):
        v = col[labels == c]
        b += len(v) * (v.mean() - gm) ** 2; w += ((v - v.mean()) ** 2).sum()
    return b / (w + 1e-12)


acc_M = loro_ncc(Mag)
acc_P = loro_ncc(Pha)
acc_MP = loro_ncc(np.hstack([Mag, Pha]))
chance = 100.0 / N

print(f"\n[recall] leave-one-repeat-out nearest-centroid ({N} states, chance {chance:.1f}%):")
print(f"  (M)   magnitude only          {acc_M:5.1f}%")
print(f"  (P)   phase only              {acc_P:5.1f}%")
print(f"  (M+P) magnitude + phase       {acc_MP:5.1f}%   Δ vs M = {acc_MP-acc_M:+.1f}")

# Per-driven-bin phase separability — does ANY bin's phase carry state?
print(f"\n[phase separability] Fisher ratio of each driven bin's phase (cos,sin) vs |H|:")
print(f"  {'bin':<10}{'|H| Fisher':>12}{'phase Fisher':>14}{'role':>14}")
argH_all = np.array([[np.angle(0)] for _ in range(0)])  # placeholder
for j, d in enumerate(ALL_DRIVEN):
    fmag = fisher(Mag[:, j])
    fcos = fisher(Pha[:, j]); fsin = fisher(Pha[:, n_dr + j])
    fpha = max(fcos, fsin)
    role = 'varied(amp)' if d in VARIED else 'fixed(probe)'
    print(f"  {d[1]}@{d[2]//1000}k{'':<3}{fmag:>12.3f}{fpha:>14.3f}{role:>14}")

print(f"\n[verdict]")
if acc_MP > acc_M + 3:
    print(f"  ✓ PHASE ADDS separability: M+P {acc_MP:.0f}% vs M {acc_M:.0f}% (+{acc_MP-acc_M:.0f}).")
    print(f"    Measured glass phase is a genuine extra feature (cross-coupling/nonlinearity carries it).")
elif acc_P > chance * 1.5:
    print(f"  ~ Phase CARRIES some state ({acc_P:.0f}% > chance {chance:.0f}%) but doesn't beat magnitude when added.")
    print(f"    Consistent with linear transfer: phase mostly redundant with magnitude for amplitude encoding.")
else:
    print(f"  ✗ Phase adds nothing here (M+P {acc_MP:.0f}% ≈ M {acc_M:.0f}%, phase-only {acc_P:.0f}% ≈ chance).")
    print(f"    HONEST: for a linear plate + amplitude encoding, arg(H) is geometry not state. Expected.")
    print(f"    Phase's real home is INTERFERENCE matching (E9-style), not amplitude-state recall.")

json.dump({'timestamp': TS, 'n_states': int(N), 'levels': L, 'repeats': R,
           'driven': [[d[0], d[1], d[2]] for d in ALL_DRIVEN], 'n_monitors': int(len(MON)),
           'acc_magnitude': float(acc_M), 'acc_phase': float(acc_P), 'acc_both': float(acc_MP),
           'delta_phase': float(acc_MP - acc_M), 'chance': float(chance),
           'chB_peak_median': float(np.median(chB_peaks)), 'chB_clip': int(clipB_total),
           'census': MON_SRC, 'note': 'classical acoustic phase via Za/Zb; not quantum'},
          open(OUT / f'cam_phase_test_{TS}.json', 'w'), indent=2)
print(f"\n  Saved: {OUT / f'cam_phase_test_{TS}.json'}")
print("=" * 76)
