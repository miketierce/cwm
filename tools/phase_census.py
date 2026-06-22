#!/usr/bin/env python3
"""
Phase Census — full-spectrum COMPLEX capture with coherent dual reference
=========================================================================

Why this exists (2026-06-21): our recall/CAM pipeline matches on the MAGNITUDE
spectrum |FFT| and throws away np.angle. Two earlier results say that is leaving
information on the table:
  • T3.2 (2026-05-26): with a TRIGGERED AC capture, per-mode phase is stable to
    σ_phase ≈ 0.12–0.28 rad (free-running gives ~1.9 rad = uniform random — the
    20× difference is the trigger, an OS/AWG artifact, NOT the glass).
  • E9 (2026-06-03): two coherent NCO tones (shared 126 MHz clock) at 180° cancel
    a mode by 98.9% — real wave-native phase interference on this bench.

This tool records the data needed to USE phase, honestly and reproducibly:

  1. TRIGGERED capture (Ch A rising, AC) — the proven jitter reducer (default).
  2. TWO coherent reference tones driven continuously on separate channels while a
     third channel is swept across the full band. Trigger jitter t0 shifts every
     tone's phase by 2π·f·t0; a single reference only removes that at HARMONICS of
     the reference, but TWO references at different frequencies pin t0 by vernier
     (unambiguous over 1/gcd(f_r1,f_r2)) — so the discarded phase can be recovered
     for ANY swept frequency, offline.
  3. PER-SUB-CAPTURE complex values stored (driven bin, both refs, monitor modes),
     NOT just an average. Each sub-capture has an independent t0, so every phase-
     correction scheme (raw / single-ref / dual-ref vernier / triggered) can be
     evaluated later WITHOUT re-running hardware. This is the "any other bits
     useful for later simulations" payload: complex transfer at the driven bin
     (the diagonal H(f)) + complex coupling to monitor modes (off-diagonal, with
     phase) + lineshape windows + noise floor + full provenance.

HONEST scope: the glass is classical. Phase here is classical acoustic phase
(wave interference), the right STRUCTURE for a path-integral-style complex sum but
NOT quantum amplitude. This capture proves where phase is STABLE/usable; it makes
no quantum claim.

Usage:
  python3 tools/phase_census.py --full                 # all 5 channels, 2 passes
  python3 tools/phase_census.py --ref1 F2:85000 --ref2 F1:57000 --sweep F3,F4,F5
  python3 tools/phase_census.py --dry-run              # synthetic plumbing test
"""
import ctypes as ct
import numpy as np
import json, time, argparse, sys, glob
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='Full-spectrum complex phase census with dual coherent reference')
ap.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
ap.add_argument('--start', type=int, default=30000)
ap.add_argument('--stop', type=int, default=350000)
ap.add_argument('--step', type=int, default=500)
ap.add_argument('--navg', type=int, default=8, help='sub-captures per point (each an independent t0 = a phase sample)')
ap.add_argument('--settle', type=float, default=0.04)
ap.add_argument('--ref1', type=str, default='F2:85000', help='coherent reference 1  CH:FREQ')
ap.add_argument('--ref2', type=str, default='F1:57000', help='coherent reference 2  CH:FREQ (vernier)')
ap.add_argument('--sweep', type=str, default='F3,F4,F5', help='channels to sweep (must exclude ref channels)')
ap.add_argument('--full', action='store_true', help='run a 2-pass plan covering ALL of F1..F5')
ap.add_argument('--guard', type=int, default=2000, help='skip swept points within ±guard Hz of a reference')
ap.add_argument('--monitors', type=int, default=16, help='strongest census modes to record complex coupling to')
ap.add_argument('--census', type=str, default=None)
ap.add_argument('--trigger', choices=['chA', 'free'], default='free',
                help='free = free-run (reliable; what our pipeline uses). chA = Ch A hardware trigger, '
                     'which does NOT lock phase here: T3.2 locked because it drove with the scope INTERNAL '
                     'AWG (synchronous); our external NCO is async, so chA just auto-fires. Use free.')
ap.add_argument('--win-bins', type=int, default=64, help='± bins of magnitude lineshape stored per point')
ap.add_argument('--single-tone', action='store_true',
                help='DIAGNOSTIC: drive ONLY the swept tone (no references). Tests whether triggered '
                     'capture reproduces T3.2 single-mode phase stability (σ≈0.2 rad). Isolates '
                     'trigger-locks-on-one-tone from multi-tone composite breaking the trigger.')
ap.add_argument('--dry-run', action='store_true')
args = ap.parse_args()

# ─── Constants (match direct_wire_census.py exactly) ─────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064; TIMEBASE = 7; FS = 781250.0; NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT; RNG = 6; RNG_MV = 1000.0
NYQ = FS / 2.0
CLOCK_HZ = 126_000_000
CHAN_GPIO = {'F1': 'GP2/pin4', 'F2': 'GP3/pin5', 'F3': 'GP4/pin6', 'F4': 'GP5/pin7', 'F5': 'GP6/pin9'}

OUT = Path('data/results/phase_census'); OUT.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')


def parse_ref(s):
    ch, f = s.split(':'); return ch.strip(), int(f)


def wrap(x):
    return (x + np.pi) % (2 * np.pi) - np.pi


def circ_stats(theta):
    """theta: 1D angles → (circular mean, circular std, resultant length R∈[0,1])."""
    z = np.exp(1j * np.asarray(theta)); m = z.mean(); R = abs(m)
    return float(np.angle(m)), float(np.sqrt(max(0.0, -2.0 * np.log(R + 1e-12)))), float(R)


# ─── Monitor modes (strongest from census) for complex coupling matrix ───────
def load_monitors(n):
    cp = Path(args.census) if args.census else None
    if cp is None:
        cands = sorted(glob.glob('data/results/direct_wire_census/*.json'))
        cp = Path(cands[-1]) if cands else None
    if cp is None:
        return [], None
    cj = json.load(open(cp))
    src = cj.get('all_modes') or cj.get('usable_modes') or []
    modes = []
    for m in src:
        f = float(m.get('freq', m.get('freq_hz', 0)))
        s = float(m.get('snr', m.get('snr_db', 0)))
        if f > 0:
            modes.append((f, s))
    modes.sort(key=lambda t: -t[1])
    # de-duplicate within 1 bin, keep strongest, cap at n
    chosen = []
    for f, s in modes:
        if all(abs(f - g) > 2 * BIN_HZ for g, _ in chosen):
            chosen.append((f, s))
        if len(chosen) >= n:
            break
    return [f for f, _ in chosen], (str(cp) if cp else None)


MON_FREQS, MON_SRC = load_monitors(args.monitors)
MON_FREQS = np.array(MON_FREQS, float)

print("=" * 76)
print("  PHASE CENSUS — full-spectrum COMPLEX capture with coherent dual reference")
print(f"  trigger={args.trigger}   step={args.step}Hz   navg={args.navg}   band {args.start/1e3:.0f}-{args.stop/1e3:.0f}kHz")
print(f"  monitors: {len(MON_FREQS)} strongest modes from {Path(MON_SRC).name if MON_SRC else 'none'}")
print("=" * 76)


# ─── Build pass plan ─────────────────────────────────────────────────────────
def make_passes():
    if args.full:
        # cover all of F1..F5: pass A refs F2,F1 sweep F3,F4,F5 ; pass B refs F4,F5 sweep F1,F2
        return [(('F2', 85000), ('F1', 57000), ['F3', 'F4', 'F5']),
                (('F4', 48000), ('F5', 89000), ['F1', 'F2'])]
    r1 = parse_ref(args.ref1); r2 = parse_ref(args.ref2)
    sweep = [c.strip() for c in args.sweep.split(',') if c.strip()]
    sweep = [c for c in sweep if c not in (r1[0], r2[0])]
    return [(r1, r2, sweep)]


PASSES = make_passes()

# ─── Bin helpers ─────────────────────────────────────────────────────────────
def bin_of(f):
    return int(round(f / BIN_HZ))


def peak_bin(spec_mag, f, search=5):
    b = bin_of(f); lo = max(0, b - search); hi = min(len(spec_mag), b + search + 1)
    return lo + int(np.argmax(spec_mag[lo:hi]))


# ─── Capture backends ────────────────────────────────────────────────────────
if args.dry_run:
    print("\n[dry-run] synthesizing complex captures (small t0 jitter to mimic triggered)\n")
    _rng = np.random.default_rng(0)

    class FakeNCO:
        def set(self, ch, f, duty=500): pass
        def off(self): pass
    _true_phase = {}

    def open_hw():
        return FakeNCO()

    def capture_complex(navg, active):
        """active: dict {freq: amplitude} of tones present. Returns (navg, NFFT//2+1) complex.
        Synthetic: a strong coherent tone (amp 40) per active freq + small noise, with a per-
        sub-capture trigger jitter t0 (~0.3µs). Demonstrates that the reference-relative phase
        removes the t0 term while the raw phase carries it."""
        out = np.zeros((navg, NFFT // 2 + 1), complex)
        freqs = np.fft.rfftfreq(NFFT, 1 / FS)
        for k in range(navg):
            t0 = _rng.normal(0, 3e-7)  # ~0.3µs triggered jitter (shared by all tones in a capture)
            spec = (_rng.standard_normal(len(freqs)) + 1j * _rng.standard_normal(len(freqs))) * 0.5
            for f, amp in active.items():
                b = bin_of(f)
                ph0 = _true_phase.setdefault(round(f), _rng.uniform(-np.pi, np.pi))
                spec[b] += 40.0 * np.exp(1j * (ph0 + 2 * np.pi * f * t0))
            out[k] = spec
        return out
else:
    import serial
    ps = ct.CDLL(PICO_LIB); ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"ERROR: PicoScope open failed ({handle})"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)   # Ch A enabled, AC, ±1V
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)   # Ch B off
    if args.trigger == 'chA':
        # source=0 (Ch A), threshold=0 ADC (AC zero-crossing), direction=0 rising,
        # delay=0, auto_trigger_ms=2000 (T3.2 working value). RE-ARMED per block below —
        # arming once then free-running the poll makes the scope auto-fire = random phase.
        TRIG = (0, 0, 0, 0, 2000)
    else:
        TRIG = (5, 0, 0, 0, 0)  # free-run
    ps.ps2000_set_trigger(handle, *TRIG)
    print(f"  PicoScope handle={handle}, Ch A AC ±{RNG_MV}mV, trigger={args.trigger}")

    _nco = serial.Serial(args.nco_port, 115200, timeout=2); time.sleep(0.5); _nco.reset_input_buffer()
    _nco.write(b'STATUS\n'); time.sleep(0.2)
    st = _nco.readline().decode(errors='replace').strip()
    if 'DUTY' not in st:
        print("ERROR: firmware lacks DUTY (amplitude) — flash tools/pico_nco/main.py"); sys.exit(1)
    print(f"  NCO: {st}")

    class NCO:
        def _cmd(self, c):
            _nco.reset_input_buffer(); _nco.write(f'{c}\n'.encode()); time.sleep(0.01)
        def set(self, ch, f, duty=500):
            self._cmd(f'{ch}:{f}'); self._cmd(f'A{ch[1]}:{duty}')
        def off(self):
            self._cmd('Foff'); time.sleep(0.02)

    def open_hw():
        return NCO()

    _triggered = (args.trigger == 'chA')

    def capture_complex(navg, active=None):
        buf = (ct.c_int16 * N_SAMPLES)(); ov = ct.c_int16()
        w = np.hanning(N_SAMPLES); out = []
        for _ in range(navg):
            if _triggered:
                ps.ps2000_set_trigger(handle, *TRIG)    # re-arm each block (T3.2-style)
            tk = ct.c_int32(); ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(tk))
            if _triggered:
                time.sleep(0.005)
            for _ in range(500):
                if ps.ps2000_ready(handle): break
                time.sleep(0.002)
            else:
                continue
            ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
            d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0); d -= d.mean()
            out.append(np.fft.rfft(d * w, n=NFFT))
        return np.array(out) if out else np.zeros((1, NFFT // 2 + 1), complex)


# ─── Noise floor (all drives off) ────────────────────────────────────────────
nco = open_hw()
nco.off()
nf_specs = capture_complex(max(4, args.navg), active={})
noise_floor = np.abs(nf_specs).mean(0)
print(f"\n[0] Noise floor captured (median {np.median(noise_floor):.3g} mV/bin)")

# ─── Sweep ───────────────────────────────────────────────────────────────────
W = args.win_bins
rec = {  # parallel arrays, appended per swept point
    'freq': [], 'channel': [], 'driven_bin': [], 'mag_mean': [], 'mag_std': [], 'snr': [],
    'phase_raw_circstd': [], 'phase_raw_mean': [],
    'phase_ref1_relstd': [], 'phase_ref1_coh': [],     # single-ref (ref1) relative phase stability
    'pass_idx': [],
}
driven_c = []      # (P, navg) complex at driven bin
ref1_c = []        # (P, navg) complex at ref1 bin
ref2_c = []        # (P, navg) complex at ref2 bin
mon_c = []         # (P, n_mon, navg) complex at monitor bins
mon_couple = []    # (P, n_mon) complex coupling, de-rotated by ref1 (reproducible)
win_mag = []       # (P, 2W+1) magnitude lineshape around driven bin
ref_meta = []      # per-pass reference info

t_start = time.time(); total_pts = 0
freqs_full = list(range(args.start, args.stop + 1, args.step))

for pi, ((r1c, r1f), (r2c, r2f), sweep_chs) in enumerate(PASSES):
    print(f"\n[pass {pi+1}/{len(PASSES)}] refs: {r1c}@{r1f/1e3:.1f}k & {r2c}@{r2f/1e3:.1f}k  |  sweep {sweep_chs}")
    ref_meta.append({'ref1': [r1c, r1f], 'ref2': [r2c, r2f], 'sweep': sweep_chs})
    # set both references once for the pass (continuous, coherent)
    nco.off()
    if not args.single_tone:
        nco.set(r1c, r1f); nco.set(r2c, r2f)
    rb1, rb2 = bin_of(r1f), bin_of(r2f)
    mon_bins = [bin_of(f) for f in MON_FREQS]
    for ch in sweep_chs:
        pts = [f for f in freqs_full if abs(f - r1f) > args.guard and abs(f - r2f) > args.guard
               and f < NYQ - 2000]
        if args.single_tone:                            # diagnostic: no refs, no guard skips
            pts = [f for f in freqs_full if f < NYQ - 2000]
        for f in pts:
            if args.single_tone:
                nco.off(); nco.set(ch, f)
            else:
                nco.set(ch, f)
            time.sleep(args.settle)
            specs = capture_complex(args.navg, active={f: 1} if args.single_tone else {r1f: 1, r2f: 1, f: 1})
            mag = np.abs(specs)
            db = peak_bin(mag.mean(0), f)               # driven peak bin
            dvals = specs[:, db]                        # (navg,) complex at driven
            r1v = specs[:, rb1]; r2v = specs[:, rb2]
            mvals = specs[:, mon_bins] if len(mon_bins) else np.zeros((len(specs), 0), complex)
            # magnitudes / SNR
            mmean = float(np.abs(dvals).mean()); mstd = float(np.abs(dvals).std())
            nf = max(noise_floor[db], 1e-12); snr = mmean / nf
            # raw phase stability (with trigger this should already be small at real modes)
            pr_mean, pr_std, _ = circ_stats(np.angle(dvals))
            # single-reference relative phase: φ_driven − (f/f_ref1)·φ_ref1  (jitter-immune at harmonics)
            rel1 = wrap(np.angle(dvals) - (f / r1f) * np.angle(r1v))
            _, rel1_std, rel1_R = circ_stats(rel1)
            # de-rotated complex coupling to monitors (align by ref1 per sub-capture, then average)
            if len(mon_bins):
                derot = mvals * np.exp(-1j * (MON_FREQS / r1f)[None, :] * np.angle(r1v)[:, None])
                couple = derot.mean(0)
            else:
                couple = np.zeros(0, complex)
            # store
            rec['freq'].append(f); rec['channel'].append(ch); rec['driven_bin'].append(db)
            rec['mag_mean'].append(mmean); rec['mag_std'].append(mstd); rec['snr'].append(snr)
            rec['phase_raw_circstd'].append(pr_std); rec['phase_raw_mean'].append(pr_mean)
            rec['phase_ref1_relstd'].append(rel1_std); rec['phase_ref1_coh'].append(rel1_R)
            rec['pass_idx'].append(pi)
            driven_c.append(dvals); ref1_c.append(r1v); ref2_c.append(r2v)
            mon_c.append(mvals.T if mvals.size else np.zeros((len(MON_FREQS), len(specs)), complex))
            mon_couple.append(couple)
            lo = db - W; hi = db + W + 1
            wm = np.zeros(2 * W + 1)
            a, b = max(0, lo), min(mag.shape[1], hi)
            wm[a - lo:b - lo] = mag.mean(0)[a:b]
            win_mag.append(wm)
            total_pts += 1
        el = time.time() - t_start
        done = total_pts
        print(f"    {ch}: {len(pts)} pts | total {done} | {el:.0f}s elapsed")

if not args.dry_run:
    nco.off(); ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))

# ─── Summarize: does phase look usable? (the headline) ───────────────────────
freq = np.array(rec['freq']); snr = np.array(rec['snr'])
praw = np.array(rec['phase_raw_circstd']); prel = np.array(rec['phase_ref1_relstd'])
coh = np.array(rec['phase_ref1_coh'])
strong = snr >= 3.0
print(f"\n[summary] {total_pts} points captured in {time.time()-t_start:.0f}s")
print(f"  strong modes (SNR≥3): {int(strong.sum())}")
if strong.any():
    print(f"  phase σ at strong modes — RAW (triggered):     median {np.median(praw[strong]):.3f} rad")
    print(f"  phase σ at strong modes — single-ref relative: median {np.median(prel[strong]):.3f} rad")
    print(f"  ref1 coherence R at strong modes:              median {np.median(coh[strong]):.3f}  (1=perfectly coherent)")
    usable = strong & (praw < 0.5)
    print(f"  modes with σ_raw < 0.5 rad (phase-usable):     {int(usable.sum())} / {int(strong.sum())}")
    if usable.sum() <= 0.3 * strong.sum():
        print("  → phase is NOT coherent capture-to-capture (expected in free-run with async NCO).")
        print("    Absolute AND cross-frequency phase carry the random acquisition time t0; the")
        print("    reference trick cancels t0 only without wrapping, which fails over a uniform t0.")
        print("    FIX = a shared drive↔capture time reference: NCO sync GPIO → PicoScope EXT trigger,")
        print("    or drive from the scope internal AWG (T3.2, synchronous). Magnitude data below is good.")
    else:
        print("  → phase looks USABLE at this setting (σ_raw < 0.5 rad on most strong modes).")

# ─── Save: npz (heavy arrays) + json (metadata + per-point summary) ──────────
def stack(lst):
    return np.array(lst) if lst else np.zeros(0)

np.savez_compressed(
    OUT / f'phase_census_data_{TS}.npz',
    freq=stack(rec['freq']), channel=np.array(rec['channel']), driven_bin=stack(rec['driven_bin']),
    pass_idx=stack(rec['pass_idx']),
    driven_c=stack(driven_c), ref1_c=stack(ref1_c), ref2_c=stack(ref2_c),
    mon_c=np.array(mon_c) if mon_c else np.zeros(0), mon_couple=np.array(mon_couple) if mon_couple else np.zeros(0),
    mon_freqs=MON_FREQS, win_mag=stack(win_mag), noise_floor=noise_floor,
    mag_mean=stack(rec['mag_mean']), snr=stack(rec['snr']),
    phase_raw_circstd=praw, phase_ref1_relstd=prel, phase_ref1_coh=coh,
)
meta = {
    'timestamp': TS, 'trigger': args.trigger, 'fs': FS, 'timebase': TIMEBASE, 'n_samples': N_SAMPLES,
    'nfft': NFFT, 'bin_hz': BIN_HZ, 'rng_mv': RNG_MV, 'clock_hz': CLOCK_HZ, 'nyquist': NYQ,
    'start': args.start, 'stop': args.stop, 'step': args.step, 'navg': args.navg, 'settle': args.settle,
    'guard': args.guard, 'win_bins': W, 'chan_gpio': CHAN_GPIO,
    'passes': ref_meta, 'monitor_freqs': MON_FREQS.tolist(), 'monitor_src': MON_SRC,
    'n_points': int(total_pts),
    'phase_model_note': 'CLASSICAL acoustic phase (wave interference). Right structure for a complex '
                        'path-integral-style sum, NOT quantum amplitude. Per-sub-capture complex values '
                        'stored so raw/single-ref/dual-ref-vernier/triggered corrections can all be '
                        'evaluated offline without re-running hardware.',
    'arrays_in_npz': 'driven_c,ref1_c,ref2_c (P,navg) complex; mon_c (P,n_mon,navg); mon_couple (P,n_mon) '
                     'de-rotated complex coupling; win_mag (P,2W+1) lineshape; noise_floor; per-point summary.',
    'summary': {
        'strong_modes': int(strong.sum()),
        'phase_raw_circstd_median_strong': float(np.median(praw[strong])) if strong.any() else None,
        'phase_ref1_relstd_median_strong': float(np.median(prel[strong])) if strong.any() else None,
        'ref1_coherence_median_strong': float(np.median(coh[strong])) if strong.any() else None,
        'phase_usable_modes': int(((snr >= 3.0) & (praw < 0.5)).sum()),
    },
}
json.dump(meta, open(OUT / f'phase_census_{TS}.json', 'w'), indent=2)
print(f"\n  Saved: {OUT / f'phase_census_{TS}.json'}")
print(f"         {OUT / f'phase_census_data_{TS}.npz'}")
if not args.full and len(PASSES) == 1:
    swept = {c for *_x, s in PASSES for c in s}
    missing = [c for c in ['F1', 'F2', 'F3', 'F4', 'F5'] if c not in swept]
    if missing:
        print(f"\n  NOTE: channels {missing} were references (not swept). For full coverage run --full, "
              f"or a second pass with those as --sweep.")
print("=" * 76)
