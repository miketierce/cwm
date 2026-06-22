#!/usr/bin/env python3
"""
Phase Census (Ch B reference) — the PROVEN Za/Zb complex transfer, jitter-free
==============================================================================

This is the corrected phase capture. The single-channel different-frequency
reference (tools/phase_census.py) FAILED on the bench (σ≈1.5 rad) because the
phase between two DIFFERENT frequencies carries 2π(f_sig−f_ref)·t0, which wraps
over the random per-capture acquisition time t0. The fix — already proven in our
own PicoScope 2204A notes at 320× (σ 83° → 0.3°) — is a SAME-frequency reference
captured SIMULTANEOUSLY on a second channel:

    Ch A = plate response  Z_A = H_plate(f)·e^{i(φ_drive + 2π f t0)}
    Ch B = direct drive tap Z_B =            e^{i(φ_drive + 2π f t0)}
    Z_A / Z_B = H_plate(f)              ← t0 AND φ_drive cancel EXACTLY (same f, no wrap)

Both channels are digitized in the SAME ps2000_run_block, so they share the exact
same t0. The ratio is the complex (magnitude + PHASE) transfer function of the
glass, immune to trigger jitter — the thing the magnitude-only pipeline throws away.

WIRING REQUIRED (user, "not hard to rewire"):
    Tee the NCO drive bus → Ch B (a direct electrical copy of what drives the TX
    PZTs). Ch A stays on the RX PZT (plate response). Do NOT route the drive into
    Ch A — Ch A must see the plate. Ch B must carry EVERY driven tone (tee the
    whole drive bus, not just one "metronome" channel) so Z_A/Z_B is clean at
    every driven frequency in one capture.

HONEST scope: this yields the complex transfer at DRIVEN frequencies only (Ch B
has no reference tone at undriven modes — off-diagonal coupling phase stays
unreachable). Dual-channel shares the 8 kS buffer → 3072 samples/ch → ~63.6 Hz
bins (vs 24.2 Hz single-channel). Acceptable for amplitude-CAM, which drives and
reads at the same fixed per-axis frequencies. Phase here is CLASSICAL acoustic
phase (wave interference) — the right structure for a complex path-integral-style
sum, NOT quantum amplitude.

Usage:
  python3 tools/phase_census_chb.py --dry-run                 # validate Za/Zb cancellation in sim
  python3 tools/phase_census_chb.py --nco-port /dev/cu.usbmodem113401 --axes F4:48000,F5:89000,F1:57000
  python3 tools/phase_census_chb.py --nco-port ... --sweep F4 --start 40000 --stop 120000 --step 1000
"""
import ctypes as ct
import numpy as np
import json, time, argparse, sys
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='Ch B reference complex transfer (proven Za/Zb)')
ap.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
ap.add_argument('--axes', type=str, default='F4:48000,F5:89000,F1:57000,F2:82000',
                help='Fixed per-axis drive points CH:FREQ,... — measures complex transfer at each (the amplitude-CAM channels).')
ap.add_argument('--sweep', type=str, default=None, help='Optional: sweep ONE channel CH instead of fixed axes')
ap.add_argument('--start', type=int, default=40000)
ap.add_argument('--stop', type=int, default=120000)
ap.add_argument('--step', type=int, default=1000)
ap.add_argument('--navg', type=int, default=20, help='sub-captures (each an independent t0). σ of Za/Zb across these = the proof.')
ap.add_argument('--settle', type=float, default=0.04)
ap.add_argument('--chb-range', type=int, default=9,
                help='Ch B range INDEX. Drive tap is volts (3.3V square) — start HIGH (9=nominal ±10V) to avoid '
                     'clipping, the tool reports peak %FS so you can narrow it. Ch A stays at range 6.')
ap.add_argument('--selftest', action='store_true',
                help='CALIBRATION: assume the DRIVE is teed into BOTH Ch A and Ch B (no plate). Then |H|≈1 and '
                     'the Za/Zb phase scatter is the SCOPE inter-channel timing floor — the best Za/Zb can ever '
                     'do here, with plate SNR removed from the picture. Run this to find out if a residual σ is '
                     'the scope (floor) or the plate (fixable). Temporarily move the Ch A probe to the drive node.')
ap.add_argument('--dry-run', action='store_true')
args = ap.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
# Dual-channel: shared 8kS buffer → 3072/ch reliable (picoscope-2204a.md).
N_SAMPLES = 3072; TIMEBASE = 7; FS = 781250.0; NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT; RNG = 6; RNG_MV = 1000.0
# Nominal ps2000 full-scale mV by range index. NOTE: picoscope-2204a.md says the 2204A may be
# shifted ~1 step (index 6 ≈ ±500mV actual, not ±1V) — so treat mV as approximate; CLIP detection
# below uses raw ADC counts (unambiguous) not mV.
RANGE_MV = {1: 20, 2: 50, 3: 100, 4: 200, 5: 500, 6: 1000, 7: 2000, 8: 5000, 9: 10000, 10: 20000}
CHB_MV = RANGE_MV.get(args.chb_range, 10000)
OUT = Path('data/results/phase_census'); OUT.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')


def circ(theta):
    z = np.exp(1j * np.asarray(theta)); m = z.mean(); R = abs(m)
    return float(np.angle(m)), float(np.sqrt(max(0.0, -2.0 * np.log(R + 1e-12)))), float(R)


def bin_of(f):
    return int(round(f / BIN_HZ))


def peak_bin(mag, f, s=4):
    b = bin_of(f); lo = max(0, b - s); hi = min(len(mag), b + s + 1)
    return lo + int(np.argmax(mag[lo:hi]))


# build the list of (channel, freq) points to measure
if args.sweep:
    POINTS = [(args.sweep, f) for f in range(args.start, args.stop + 1, args.step)]
else:
    POINTS = [(p.split(':')[0], int(p.split(':')[1])) for p in args.axes.split(',') if p]

print("=" * 78)
print("  PHASE CENSUS (Ch B reference) — proven Za/Zb complex transfer, jitter-free")
print(f"  dual-channel N={N_SAMPLES}/ch  bin={BIN_HZ:.1f}Hz  navg={args.navg}  points={len(POINTS)}")
if args.selftest:
    print("  *** SELFTEST: expecting DRIVE on BOTH Ch A and Ch B → |H|≈1, σargH = scope inter-channel floor ***")
print("=" * 78)

# ─── Capture backends ────────────────────────────────────────────────────────
if args.dry_run:
    print("\n[dry-run] modeling Ch A = H_plate·e^{i(φ+2πf·t0)}, Ch B = e^{i(φ+2πf·t0)}.")
    print("          If Za/Zb cancels t0, its σ across captures → ~0 regardless of jitter.\n")
    _rng = np.random.default_rng(0)
    # a synthetic 'true' complex plate transfer per frequency (what we hope to recover)
    def H_true(f):
        a = 0.6 + 0.4 * np.cos(2 * np.pi * f / 30000.0)        # magnitude ripple
        ph = np.sin(2 * np.pi * f / 50000.0) * 1.2             # phase vs freq
        return a * np.exp(1j * ph)

    def capture_AB(navg, f):
        A = np.zeros((navg, NFFT // 2 + 1), complex)
        B = np.zeros((navg, NFFT // 2 + 1), complex)
        phi_drive = _rng.uniform(-np.pi, np.pi)
        b = bin_of(f)
        for k in range(navg):
            t0 = _rng.uniform(-5e-4, 5e-4)   # BIG uniform jitter (many periods) — the worst case
            common = np.exp(1j * (phi_drive + 2 * np.pi * f * t0))
            na = (_rng.standard_normal(NFFT // 2 + 1) + 1j * _rng.standard_normal(NFFT // 2 + 1)) * 0.4
            nb = (_rng.standard_normal(NFFT // 2 + 1) + 1j * _rng.standard_normal(NFFT // 2 + 1)) * 0.4
            A[k] = na; B[k] = nb
            A[k, b] += 30.0 * H_true(f) * common      # plate response
            B[k, b] += 30.0 * common                  # direct drive tap (no plate)
        return A, B, {'clipA': 0, 'clipB': 0, 'peakA': 0.30, 'peakB': 0.30}

    class FakeNCO:
        def set(self, ch, f, duty=500): pass
        def off(self): pass
    def open_hw(): return FakeNCO()
else:
    import serial
    ps = ct.CDLL(PICO_LIB); ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"ERROR: PicoScope open failed ({handle})"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)              # Ch A enabled, AC, ±1V (plate)
    ps.ps2000_set_channel(handle, 1, 1, 0, args.chb_range)   # Ch B enabled, AC (drive tap)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)             # free-run; Za/Zb makes the trigger irrelevant
    print(f"  PicoScope handle={handle}  Ch A ±{RNG_MV}mV (plate)  Ch B ≈±{CHB_MV}mV (drive tap)  free-run")

    _nco = serial.Serial(args.nco_port, 115200, timeout=2); time.sleep(0.5); _nco.reset_input_buffer()
    _nco.write(b'STATUS\n'); time.sleep(0.2)
    st = _nco.readline().decode(errors='replace').strip()
    if 'DUTY' not in st:
        print("ERROR: firmware lacks DUTY — flash tools/pico_nco/main.py"); sys.exit(1)
    print(f"  NCO: {st}")

    class NCO:
        def _c(self, c): _nco.reset_input_buffer(); _nco.write(f'{c}\n'.encode()); time.sleep(0.01)
        def set(self, ch, f, duty=500): self._c(f'{ch}:{f}'); self._c(f'A{ch[1]}:{duty}')
        def off(self): self._c('Foff'); time.sleep(0.02)
    def open_hw(): return NCO()

    def capture_AB(navg, f):
        bufA = (ct.c_int16 * N_SAMPLES)(); bufB = (ct.c_int16 * N_SAMPLES)(); ov = ct.c_int16()
        w = np.hanning(N_SAMPLES); A = []; B = []
        clipA = clipB = 0; peakA = peakB = 0.0
        for _ in range(navg):
            tk = ct.c_int32(); ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(tk))
            for _ in range(500):
                if ps.ps2000_ready(handle): break
                time.sleep(0.002)
            else:
                continue
            # both channels in ONE call → identical t0 (the crux of Za/Zb)
            ps.ps2000_get_values(handle, ct.byref(bufA), ct.byref(bufB), None, None, ct.byref(ov), N_SAMPLES)
            rawA = np.array(bufA[:], float); rawB = np.array(bufB[:], float)
            pa = np.abs(rawA).max() / 32767.0; pb = np.abs(rawB).max() / 32767.0
            peakA = max(peakA, pa); peakB = max(peakB, pb)
            o = ov.value
            if (o & 1) or pa > 0.999: clipA += 1      # bit0 = Ch A overflow; near-FS counts = clip
            if (o & 2) or pb > 0.999: clipB += 1      # bit1 = Ch B overflow
            da = rawA * (RNG_MV / 32767.0); da -= da.mean()
            db = rawB * (CHB_MV / 32767.0); db -= db.mean()
            A.append(np.fft.rfft(da * w, n=NFFT)); B.append(np.fft.rfft(db * w, n=NFFT))
        diag = {'clipA': clipA, 'clipB': clipB, 'peakA': peakA, 'peakB': peakB}
        return np.array(A), np.array(B), diag

# ─── Measure complex transfer at each point ──────────────────────────────────
nco = open_hw(); nco.off()
results = []
any_clipB = False
print(f"\n{'point':<14}{'|H| (Za/Zb)':>13}{'arg H °':>9}{'σargH':>8}{'rawA σφ':>9}{'ChB %FS':>9}{'clip':>6}")
print("-" * 78)
for ch, f in POINTS:
    nco.off(); nco.set(ch, f); time.sleep(args.settle)
    A, B, diag = capture_AB(args.navg, f)
    bm = peak_bin(np.abs(A).mean(0), f)
    Za = A[:, bm]; Zb = B[:, bm]
    H = Za / Zb                                  # the jitter-free complex transfer, per sub-capture
    magH = np.abs(H); argH = np.angle(H)
    _, raw_sigphi, _ = circ(np.angle(Za))        # raw Ch A phase scatter (what we'd get WITHOUT Ch B)
    Hmean_ph, sig_argH, R = circ(argH)
    clipB = diag['clipB'] > 0; any_clipB = any_clipB or clipB
    rec = {
        'channel': ch, 'freq': f, 'bin': int(bm),
        'H_mag_mean': float(magH.mean()), 'H_mag_cv': float(magH.std() / (magH.mean() + 1e-12)),
        'H_arg_mean_deg': float(np.degrees(Hmean_ph)), 'H_arg_circstd_rad': float(sig_argH),
        'H_coherence_R': float(R), 'rawA_phase_circstd_rad': float(raw_sigphi),
        'snrA': float(np.abs(Za).mean() / (np.abs(A).mean() + 1e-12)),
        'chB_peak_fs': float(diag['peakB']), 'chB_clip_n': int(diag['clipB']),
        'chA_peak_fs': float(diag['peakA']), 'chA_clip_n': int(diag['clipA']),
    }
    results.append(rec)
    flag = 'B!' if clipB else ('A!' if diag['clipA'] else 'ok')
    print(f"{ch}@{f/1e3:>6.1f}k {magH.mean():>12.3f}{np.degrees(Hmean_ph):>9.1f}"
          f"{sig_argH:>8.3f}{raw_sigphi:>9.3f}{100*diag['peakB']:>8.0f}%{flag:>6}")

if not args.dry_run:
    nco.off(); ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))

# ─── Verdict ─────────────────────────────────────────────────────────────────
arg_sig = np.array([r['H_arg_circstd_rad'] for r in results])
raw_sig = np.array([r['rawA_phase_circstd_rad'] for r in results])
chB_peaks = np.array([r['chB_peak_fs'] for r in results])
med_argH = float(np.median(arg_sig)); med_raw = float(np.median(raw_sig))
print("-" * 78)

# Ch B health first — a saturated or absent reference invalidates everything below it.
print(f"\n[Ch B reference health]")
print(f"  Ch B peak: median {100*np.median(chB_peaks):.0f}% FS, max {100*chB_peaks.max():.0f}% FS  (range ≈±{CHB_MV}mV)")
if any_clipB:
    print(f"  ✗ Ch B CLIPPING on {sum(r['chB_clip_n']>0 for r in results)}/{len(results)} points — raise --chb-range")
    print(f"    (the drive tap is volts; a clipped square wave still has a phase but |H| is wrong).")
elif chB_peaks.max() < 0.05:
    print(f"  ✗ Ch B almost SILENT (<5% FS) — the tee may not be carrying the drive. Check the jumper to Ch B,")
    print(f"    or LOWER --chb-range so the divided-down drive is visible.")
elif chB_peaks.max() < 0.20:
    print(f"  ~ Ch B low ({100*chB_peaks.max():.0f}% FS) — works, but LOWER --chb-range for better phase SNR.")
else:
    print(f"  ✓ Ch B level healthy (no clip, good amplitude). Reference tap looks correctly wired.")

print(f"\n[verdict] complex transfer H = Za/Zb across {len(results)} points:")
print(f"  raw Ch A phase scatter (NO reference):   median σ = {med_raw:.3f} rad")
print(f"  Za/Zb transfer phase (WITH Ch B ref):    median σ = {med_argH:.3f} rad")
if args.selftest:
    med_H = float(np.median([r['H_mag_mean'] for r in results]))
    print(f"  [SELFTEST] |H| median = {med_H:.3f} (expect ≈1 if drive is on both channels)")
    if med_argH < 0.05:
        print(f"  ✓✓ Scope inter-channel floor is TINY (σ={med_argH:.3f} rad). Za/Zb is limited only by")
        print(f"     PLATE SNR in the real run — drive harder / pick resonant modes / average more.")
    elif med_argH < 0.2:
        print(f"  ✓ Scope inter-channel floor σ={med_argH:.3f} rad — usable. Real-run residual above this is plate SNR.")
    else:
        print(f"  ✗ Scope inter-channel floor σ={med_argH:.3f} rad is the LIMIT — this 2-ch scope jitters between")
        print(f"     channels by ~{med_argH/(2*np.pi*np.median([r['freq'] for r in results]))*1e6:.2f}µs. Za/Zb can't beat this here.")
elif any_clipB:
    print(f"  ⚠ Ch B clipped — fix the range and re-run before trusting these numbers.")
elif med_argH < 0.1 and med_raw > 0.5:
    print(f"  ✓✓ Za/Zb CANCELS the jitter: {med_raw/max(med_argH,1e-6):.0f}× tighter. Complex phase is USABLE.")
    print(f"     The glass's complex (magnitude+phase) transfer is now measurable per driven axis.")
elif med_argH < 0.5:
    print(f"  ✓ Za/Zb phase stable (σ<0.5 rad). Reference working, but residual likely plate SNR or inter-channel")
    print(f"    jitter — run --selftest (drive on both channels) to find which.")
else:
    print(f"  ✗ Za/Zb phase NOT stable — check Ch B actually carries the drive at these freqs (tee wired?).")

print(f"\n[wiring note] cross-coupling check (does chaining the Ch B columns short the TX rows?):")
print(f"  This tool drives ONE axis at a time, so it cannot fully prove independence. If the Ch B")
print(f"  columns are chained DIRECTLY, all post-220Ω TX rows are tied together → every plate is")
print(f"  cross-driven AND the RP2040 pins fight through 220Ω pairs (weak, hot drive). Symptom to")
print(f"  watch: |H| much weaker than the single-plate census, or modes from other plates appearing.")
print(f"  Clean fix: a series R (~1–10kΩ) from EACH row into a common Ch B node = passive summing")
print(f"  that isolates the rows. The tap to Ch B should be the only shared point, via resistors.")

np.savez_compressed(OUT / f'phase_census_chb_data_{TS}.npz',
                    freq=np.array([r['freq'] for r in results]),
                    channel=np.array([r['channel'] for r in results]),
                    H_mag=np.array([r['H_mag_mean'] for r in results]),
                    H_arg_deg=np.array([r['H_arg_mean_deg'] for r in results]),
                    H_arg_circstd=arg_sig, rawA_circstd=raw_sig)
json.dump({'timestamp': TS, 'method': 'ChB same-frequency reference Za/Zb (proven 320x)',
           'n_samples_per_ch': N_SAMPLES, 'bin_hz': BIN_HZ, 'navg': args.navg,
           'dry_run': args.dry_run, 'points': results,
           'median_argH_circstd_rad': med_argH, 'median_rawA_circstd_rad': med_raw,
           'note': 'Complex transfer at DRIVEN freqs only. Classical acoustic phase, not quantum. '
                   'Ch A=plate (RX), Ch B=direct NCO drive tap, both in one run_block (shared t0).'},
          open(OUT / f'phase_census_chb_{TS}.json', 'w'), indent=2)
print(f"\n  Saved: {OUT / f'phase_census_chb_{TS}.json'}")
if args.dry_run:
    print("  (dry-run: confirms the ALGEBRA cancels t0. Wire the Ch B drive tee, then run on hardware.)")
print("=" * 78)
