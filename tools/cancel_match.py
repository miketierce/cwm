#!/usr/bin/env python3
"""
Cancellation-Match (fully measured) — recall by interference null vs by amplitude
=================================================================================

The honest, no-modeled-noise version of phase_interference.py Section B. We now
have a real 99.5% interference null (two TX on one 100mm plate, F1+F2). The claim
to test: reading a stored pattern by DRIVING IT TO A NULL (cancellation) is more
robust to common-mode drive/gain noise than reading it by amplitude — because a
null (≈0) is immune to a multiplicative gain wobble (0·g ≈ 0) while a peak is not.

Everything here is MEASURED on glass. No simulated noise anywhere (that was the
Section-B caveat). Common-mode gain noise is injected PHYSICALLY by scaling BOTH
arms' drive duty by the same random factor each capture, then we let the glass
return whatever it returns.

Protocol (associative recall of a phase, K stored patterns φ_s = s·360/K):
  • Calibrate E(φ) live once → null phase φ_n, peak phase φ_p.
  • For a true query i and each candidate stored j, the relative drive is
    (φ_i − φ_j) + offset:
       CANCEL readout: offset = φ_n  → a TRUE match (i=j) lands on the NULL  → argmin E
       AMP    readout: offset = φ_p  → a TRUE match (i=j) lands on the PEAK  → argmax E
    Both use the SAME interference physics and the SAME measurement budget (one
    capture per candidate, same physical gain-noise process). Only argmin-null vs
    argmax-peak differs. Fair head-to-head.
  • Sweep common-mode gain-noise level; report recall accuracy for each method.

Classical acoustic interference (E9 mechanism). Path-integral STRUCTURE, not quantum.

Usage:
  python3 tools/cancel_match.py --nco-port /dev/cu.usbmodem113401 --freq 54920
  python3 tools/cancel_match.py --dry-run
"""
import ctypes as ct
import numpy as np
import json, time, math, argparse, sys
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='Fully-measured cancellation-match vs amplitude-match')
ap.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
ap.add_argument('--freq', type=int, default=54920, help='the deep-null mode (two TX on one plate)')
ap.add_argument('--patterns', type=int, default=5, help='K stored phase patterns')
ap.add_argument('--repeats', type=int, default=4, help='recall repeats per (true pattern, noise level)')
ap.add_argument('--navg', type=int, default=6)
ap.add_argument('--settle', type=float, default=0.04)
ap.add_argument('--base-duty', type=int, default=300, help='center duty for both arms (headroom to swing both ways)')
ap.add_argument('--noise-levels', type=str, default='0,0.3,0.6,1.0', help='common-mode gain-noise σ values')
ap.add_argument('--raw-cal', action='store_true',
                help='use raw argmin/argmax for null/peak (the old, unfair calibration). Default = cos-fit, '
                     'which forces null ≡ peak+180° so the amplitude baseline is NOT handicapped by a noisy peak pick.')
ap.add_argument('--gain-floor', type=float, default=0.55,
                help='clamp the common-mode gain to [floor, 2-floor] so cancel never collapses by being driven into '
                     'the noise floor (isolates COMMON-MODE rejection from a signal-into-noise artifact). 0.55 default.')
ap.add_argument('--dry-run', action='store_true')
args = ap.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064; TIMEBASE = 7; FS = 781250.0; NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT; RNG = 6; RNG_MV = 1000.0
FQ = args.freq
K = args.patterns
NOISE = [float(x) for x in args.noise_levels.split(',')]
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = Path('data/results/phase_interference'); OUT.mkdir(parents=True, exist_ok=True)
STORED = [round(s * 360.0 / K) for s in range(K)]


def energy_at(spec, f, half=3):
    b = int(round(f / BIN_HZ)); return float(spec[max(0, b - half):b + half + 1].sum())


def cos_fit_null_peak(phases_deg, E):
    """Fit E(φ) = c0 + c1·cos(φ − φ0) and return (null_deg, peak_deg) EXACTLY 180° apart.
    Peak = φ0 (E max), null = φ0+180 (E min). Using the fit instead of raw argmin/argmax
    removes the per-sample noise on the peak pick that handicapped the amplitude baseline."""
    ph = np.radians(np.asarray(phases_deg, float)); E = np.asarray(E, float)
    M = np.column_stack([np.ones_like(ph), np.cos(ph), np.sin(ph)])
    c0, a, b = np.linalg.lstsq(M, E, rcond=None)[0]
    phi0 = math.degrees(math.atan2(b, a)) % 360.0   # phase of the cosine peak
    return (phi0 + 180.0) % 360.0, phi0


print("=" * 78)
print("  CANCELLATION-MATCH (fully measured) — recall by null vs by amplitude")
print(f"  {K} stored phases {STORED}  @ {FQ} Hz   common-mode gain noise injected PHYSICALLY")
print("=" * 78)

# ─── Hardware ────────────────────────────────────────────────────────────────
if args.dry_run:
    print("\n[dry-run] synthetic cos law (null 110°, peak 290°) + PHYSICAL-style common-mode")
    print("          gain applied as a real multiplier on both arms. Validates the logic only.\n")
    _rng = np.random.default_rng(0)
    NULL_T, PEAK_T = 110.0, 290.0

    def drive_relphase(rel_deg, gain):
        # balanced two-arm sum: E = base·(1 + ρ cos(rel − peak)) with deep null (ρ≈0.99)
        rho = 0.990
        shape = 1.0 + rho * math.cos(math.radians((rel_deg - PEAK_T) % 360))
        E = gain * gain * (shape) * 1000.0
        return E * (1 + 0.01 * _rng.standard_normal()) + 0.5

    def calibrate():
        phs = list(range(0, 360, 10))
        E = np.array([drive_relphase(p, 1.0) for p in phs])
        if args.raw_cal:
            return float(phs[int(np.argmin(E))]), float(phs[int(np.argmax(E))])
        return cos_fit_null_peak(phs, E)

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
        nco.reset_input_buffer(); nco.write(f'{c}\n'.encode()); time.sleep(0.012)

    def capture():
        buf = (ct.c_int16 * N_SAMPLES)(); ov = ct.c_int16(); mags = []
        for _ in range(args.navg):
            tk = ct.c_int32(); ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(tk))
            for _ in range(500):
                if ps.ps2000_ready(handle): break
                time.sleep(0.002)
            else:
                continue
            ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
            d = np.array(buf[:], float) * (RNG_MV / 32767.0); d -= d.mean()
            mags.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES), n=NFFT)))
        return np.mean(mags, axis=0) if mags else np.zeros(NFFT // 2 + 1)

    def drive_relphase(rel_deg, gain):
        # PHYSICAL common-mode gain: scale BOTH arms' duty equally (balanced → null preserved,
        # only overall level changes). The glass returns whatever it returns — no modeled noise.
        duty = int(round(args.base_duty * gain))
        duty = max(10, min(500, duty))
        send('Foff'); time.sleep(0.004)
        send(f'F1:{FQ}'); send(f'A1:{duty}')
        send(f'F2:{FQ}'); send(f'A2:{duty}')
        send(f'PHASE:{rel_deg % 360}')
        time.sleep(args.settle)
        return energy_at(capture(), FQ)

    def calibrate():
        send('Foff'); time.sleep(0.004)
        phs = list(range(0, 360, 10))
        E = np.array([drive_relphase(p, 1.0) for p in phs])
        if args.raw_cal:
            return float(phs[int(np.argmin(E))]), float(phs[int(np.argmax(E))])
        return cos_fit_null_peak(phs, E)

    class W:
        def off(self): send('Foff'); time.sleep(0.02)
    def open_hw(): return W()

hw = open_hw()

# ─── Calibrate the live interference law ─────────────────────────────────────
print("\n[1] Calibrating E(φ) live (one sweep)...")
phi_null, phi_peak = calibrate()
print(f"    null φ = {phi_null:.0f}°   peak φ = {phi_peak:.0f}°   (separation {abs(phi_peak-phi_null):.0f}°)")

# ─── Recall trials (fully measured, physical gain noise) ─────────────────────
rng = np.random.default_rng(1)


def recall_once(true_i, offset, pick, gain_sigma):
    """Drive query i against each candidate j with the given offset (null or peak);
    each capture gets a fresh PHYSICAL common-mode gain. Return predicted j."""
    E = np.zeros(K)
    for j in range(K):
        # common-mode drive scale, clamped to [floor, 2-floor] so neither method is
        # driven into the noise floor (isolates common-mode REJECTION from a clamp artifact).
        g = 1.0 + gain_sigma * rng.standard_normal()
        g = float(np.clip(g, args.gain_floor, 2.0 - args.gain_floor))
        rel = (STORED[true_i] - STORED[j]) + offset
        E[j] = drive_relphase(rel, g)
    return int(pick(E))


print(f"\n[2] Recall: K={K} patterns, {args.repeats} repeats/pattern, physical gain noise.")
print(f"    {'noise σ':>8} {'CANCEL (null)':>14} {'AMPLITUDE (peak)':>17}")
results = []
t0 = time.time()
for gs in NOISE:
    cancel_hits = 0; amp_hits = 0; tot = 0
    for rep in range(args.repeats):
        for i in range(K):
            if recall_once(i, phi_null, np.argmin, gs) == i:
                cancel_hits += 1
            if recall_once(i, phi_peak, np.argmax, gs) == i:
                amp_hits += 1
            tot += 1
    ca = 100.0 * cancel_hits / tot; aa = 100.0 * amp_hits / tot
    results.append({'noise': gs, 'cancel': ca, 'amp': aa})
    print(f"    {gs:>8} {ca:>13.0f}% {aa:>16.0f}%")
hw.off()
if not args.dry_run:
    ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))

# ─── Verdict ─────────────────────────────────────────────────────────────────
noisy = [r for r in results if r['noise'] >= 0.3]
adv = float(np.mean([r['cancel'] - r['amp'] for r in noisy])) if noisy else 0.0
clean = next((r for r in results if r['noise'] == 0.0), None)
print(f"\n[3] Verdict:")
if clean:
    print(f"    clean (σ=0): cancel {clean['cancel']:.0f}%  amp {clean['amp']:.0f}%  "
          f"({'tied — both read the phase' if abs(clean['cancel']-clean['amp'])<10 else 'differ'})")
if adv > 8:
    print(f"    ✓ CANCELLATION-MATCH wins under real gain noise: +{adv:.0f} pts (σ≥0.3), FULLY MEASURED.")
    print(f"      A physical null is common-mode-noise-immune (0·g≈0); a peak is not. The glass's")
    print(f"      interference does the noise rejection — genuine compute a magnitude read can't match.")
elif adv > 2:
    print(f"    ~ Cancellation modestly ahead (+{adv:.0f} pts). Real but small at these noise levels.")
else:
    print(f"    ✗ No measured cancellation advantage ({adv:+.0f} pts). Honest null — the gain noise here")
    print(f"      doesn't separate null- from peak-reading on this mode/geometry.")

json.dump({'timestamp': TS, 'freq': FQ, 'patterns': STORED, 'repeats': args.repeats,
           'navg': args.navg, 'base_duty': args.base_duty, 'phi_null': phi_null, 'phi_peak': phi_peak,
           'noise_levels': NOISE, 'results': results, 'cancel_minus_amp_noisy': adv,
           'fully_measured': True, 'dry_run': args.dry_run,
           'note': 'physical common-mode gain via balanced duty scaling; no modeled noise; classical acoustic interference'},
          open(OUT / f'cancel_match_{TS}.json', 'w'), indent=2)
print(f"\n    elapsed {time.time()-t0:.0f}s   Saved: {OUT / f'cancel_match_{TS}.json'}")
print("=" * 78)
