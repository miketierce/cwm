#!/usr/bin/env python3
"""
WL-B10 — Array Design Optimizer: max usable features from one NCO, one RX bus
=============================================================================

Completes the WL-B10 worklist item. Given the plates on hand and the MEASURED
hardware lessons of this project, find the array + drive topology that maximizes
the quality-weighted count of usable readout features on a single direct-wired RX
bus — and emit a concrete TX/RX + pin map to build.

THE THREE MEASURED LESSONS THAT DRIVE THE DESIGN (not assumptions):
  1. TX WIRE LENGTH DOMINATES SNR (2026-06-05): shortening TX leads raised mode
     amplitude 8–260× and turned invisible modes (321 kHz, Q≈40 at 0.2 mV) into
     clean high-Q resonances (Q=535 at 8.9 mV). The long wire radiates drive as
     EMI (parasitic C ~100 pF/m vs PZT ~1.25 nF). ⇒ every TX lead must be SHORT;
     the NCO sits central; we spend a tone only if its plate is close.
  2. COLLISIONS ON THE SHARED RX BUS KILL EFFICIENCY (2026-06-20): a census found
     87 raw modes but rejected 52 as collisions (<500 Hz apart across channels on
     the shared bus) → 24% efficiency. Overlapping bands are the killer. ⇒ spread
     plates across NON-OVERLAPPING bands set by plate SIZE (f ∝ h/L²).
  3. RECALL vs KERNEL want OPPOSITE geometries: recall (our shipping demos —
     amplitude position, heading, trajectory) wants ONE clean monotonic carrier
     per axis; kernel/classification wants MANY modes. ⇒ score both; report the
     array per task regime.

Plate band priors are MEASURED where we have them (Q-factor sweeps 2026-06-05,
censuses 2026-06-21) and physics-estimated (f ∝ h/L²) for the untested slides.
Once real per-plate solo censuses exist (data/results/array_design/catalogs/),
this tool ingests them and re-optimizes.

Usage:
  python3 tools/array_design.py                 # optimize on seeded + any catalog data
  python3 tools/array_design.py --collision-bw 500 --regime balanced
"""
import json, glob, argparse, itertools
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='WL-B10 array design optimizer')
ap.add_argument('--collision-bw', type=float, default=500.0, help='Hz; modes closer than this on the shared bus collide')
ap.add_argument('--iso-bw', type=float, default=3000.0, help='Hz; a "clean" mode has no neighbor within this')
ap.add_argument('--snr-clean', type=float, default=6.0, help='min SNR for a "clean" tracking-grade mode')
ap.add_argument('--tone-budget', type=int, default=8, help='independent tones available (8 PIO; 16 with PWM)')
ap.add_argument('--w-dim', type=float, default=1.0)
ap.add_argument('--w-clean', type=float, default=3.0, help='weight on clean isolated modes (recall/tracking value)')
ap.add_argument('--w-cost', type=float, default=2.0, help='penalty per tone (favors fewer, shorter-wire TX)')
ap.add_argument('--regime', choices=['tracking', 'classification', 'balanced', 'all'], default='all')
ap.add_argument('--catalogs', type=str, default='data/results/array_design/catalogs')
args = ap.parse_args()

OUT = Path('data/results/array_design'); OUT.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')

# ─── Plate catalogs (MEASURED where available, else physics-estimated) ───────
# Each plate: band (lo,hi) Hz, n_modes in band, clean modes [(freq, SNR)], the
# multipoint gain (extra distinct modes a 2nd TX position excites), and whether
# its TX pair can be phase-locked (needs both TX in one PIO block).
# Sources: 100mm/25mm from Q-factor sweep 2026-06-05 + censuses; slides estimated
# from f ∝ h/L² (75×25×1 soda-lime, 3:1 rectangular → asymmetric mid comb).
SEED = {
    'plate_100mm': dict(size='100x100x1 fused-silica', band=(40000, 100000), n_modes=14,
                        clean=[(47700, 9.0), (66150, 7.0), (96100, 8.0)], multipoint_gain=4,
                        Q_typ=500, note='LOW band, dense comb (MEASURED Q 410-743)'),
    'plate_25mm':  dict(size='25x25x1 fused-silica', band=(230000, 330000), n_modes=4,
                        clean=[(321200, 10.0), (232700, 6.0)], multipoint_gain=2,
                        Q_typ=520, note='HIGH band, sparse + ISOLATED (MEASURED Q 512-535 @321k). '
                                        '(also has a low 56-91k cluster that COLLIDES with 100mm — avoid)'),
    'slide_A':     dict(size='75x25x1 soda-lime', band=(100000, 175000), n_modes=10,
                        clean=[(120000, 6.0), (150000, 6.0)], multipoint_gain=5,
                        Q_typ=300, note='MID-LOW band (EST f∝h/L²; heaviest mass → lowest)'),
    'slide_B':     dict(size='75x25x1 soda-lime', band=(140000, 215000), n_modes=10,
                        clean=[(160000, 6.0), (195000, 6.0)], multipoint_gain=5,
                        Q_typ=300, note='MID band (EST; medium mass)'),
    'slide_C':     dict(size='75x25x1 soda-lime', band=(180000, 255000), n_modes=10,
                        clean=[(200000, 6.0), (240000, 6.0)], multipoint_gain=5,
                        Q_typ=300, note='MID-HIGH band (EST; lightest mass → highest)'),
}

# Ingest any real per-plate solo censuses (override the seed)
for fn in glob.glob(f'{args.catalogs}/*.json'):
    cj = json.load(open(fn)); pid = Path(fn).stem
    src = cj.get('all_modes') or cj.get('usable_modes') or []
    freqs = sorted(float(m.get('freq', m.get('freq_hz', 0))) for m in src if m.get('freq', m.get('freq_hz', 0)))
    snrs = [(float(m.get('freq', m.get('freq_hz', 0))), float(m.get('snr', m.get('snr_db', 0)))) for m in src]
    if freqs:
        SEED[pid] = dict(size='(measured)', band=(min(freqs), max(freqs)), n_modes=len(freqs),
                         clean=sorted([s for s in snrs if s[1] >= args.snr_clean], key=lambda z: -z[1])[:4],
                         multipoint_gain=0, Q_typ=0, note=f'MEASURED catalog {Path(fn).name}')
        print(f"  [catalog] loaded {pid}: {len(freqs)} modes {min(freqs)/1e3:.0f}-{max(freqs)/1e3:.0f} kHz")

print("=" * 78)
print("  WL-B10 ARRAY DESIGN — max usable features, one NCO, one RX bus")
print(f"  collision_bw={args.collision_bw:.0f}Hz  iso_bw={args.iso_bw:.0f}Hz  tone_budget={args.tone_budget}")
print("=" * 78)


# ─── Collision / score model ─────────────────────────────────────────────────
def band_overlap(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def evaluate(plate_ids, tx_per_plate):
    """plate_ids on the shared bus; tx_per_plate = {pid: 1 or 2}. Returns metrics.
    Models: a 2nd TX adds multipoint_gain distinct modes; overlapping bands lose
    modes to collisions proportional to the overlap fraction × mode density."""
    n_tones = sum(tx_per_plate[p] for p in plate_ids)
    if n_tones > args.tone_budget:
        return None
    # raw modes (with multipoint gain for 2-TX plates)
    raw = {}
    for p in plate_ids:
        g = SEED[p]['multipoint_gain'] if tx_per_plate[p] >= 2 else 0
        raw[p] = SEED[p]['n_modes'] + g
    # collision loss: for each overlapping band pair, both lose modes in the overlap
    # region at the bus collision density. Approximate: lost ≈ overlap_Hz / collision_bw,
    # capped at the smaller plate's modes in that region.
    lost = 0.0
    for a, b in itertools.combinations(plate_ids, 2):
        ov = band_overlap(SEED[a]['band'], SEED[b]['band'])
        if ov <= 0:
            continue
        dens_a = raw[a] / max(1, SEED[a]['band'][1] - SEED[a]['band'][0])
        dens_b = raw[b] / max(1, SEED[b]['band'][1] - SEED[b]['band'][0])
        # colliding modes ≈ overlap × combined density, each collision kills ~1 usable
        lost += ov * (dens_a + dens_b)
    n_usable = max(0, sum(raw.values()) - lost)
    # clean isolated high-SNR modes: a plate's clean modes survive only if no OTHER
    # plate's band covers them (else the bus neighbor spoils isolation)
    n_clean = 0
    for p in plate_ids:
        for (f, snr) in SEED[p]['clean']:
            if snr < args.snr_clean:
                continue
            spoiled = any(q != p and SEED[q]['band'][0] - args.iso_bw <= f <= SEED[q]['band'][1] + args.iso_bw
                          for q in plate_ids)
            if not spoiled:
                n_clean += 1
    score = args.w_dim * n_usable + args.w_clean * n_clean - args.w_cost * n_tones
    return dict(plates=plate_ids, tx=dict(tx_per_plate), n_tones=n_tones,
                n_usable=round(n_usable, 1), n_clean=n_clean, score=round(score, 1),
                bands=[(p, SEED[p]['band']) for p in plate_ids])


# ─── Search all plate subsets × TX counts ────────────────────────────────────
all_plates = list(SEED.keys())
results = []
for k in range(1, len(all_plates) + 1):
    for subset in itertools.combinations(all_plates, k):
        # try 2 TX on each (multipoint) down to 1 TX; enumerate a few sensible mixes
        for tx_choice in itertools.product([1, 2], repeat=len(subset)):
            txmap = {p: t for p, t in zip(subset, tx_choice)}
            r = evaluate(list(subset), txmap)
            if r:
                results.append(r)


def regime_weights(regime):
    return {'tracking': (1.0, 4.0, 1.5), 'classification': (2.0, 1.0, 1.0),
            'balanced': (1.0, 3.0, 2.0)}[regime]


def rescore(r, w):
    return round(w[0] * r['n_usable'] + w[1] * r['n_clean'] - w[2] * r['n_tones'], 1)


regimes = ['tracking', 'classification', 'balanced'] if args.regime == 'all' else [args.regime]
report = {}
for reg in regimes:
    w = regime_weights(reg)
    ranked = sorted(results, key=lambda r: -rescore(r, w))
    best = ranked[0]
    print(f"\n[{reg.upper()}]  (w_dim={w[0]}, w_clean={w[1]}, w_cost={w[2]})")
    print(f"  BEST: {[p.replace('plate_','').replace('slide_','sl') for p in best['plates']]}  "
          f"tones={best['n_tones']}  usable≈{best['n_usable']}  clean={best['n_clean']}  score={rescore(best,w)}")
    for p in best['plates']:
        b = SEED[p]['band']
        print(f"      {p:<12} {best['tx'][p]}TX  band {b[0]/1e3:.0f}-{b[1]/1e3:.0f} kHz  ({SEED[p]['note']})")
    report[reg] = best

# ─── Emit the concrete pin map for the balanced winner ──────────────────────
PIO0 = ['F1', 'F2', 'F3', 'F4']   # phase-locked group A (pins GP2,3,4,5 = 4,5,6,7)
PIO1 = ['F5', 'F6', 'F7', 'F8']   # phase-locked group B (pins GP6,7,8,9 = 9,10,11,12)
PIN = {'F1': 'GP2/pin4', 'F2': 'GP3/pin5', 'F3': 'GP4/pin6', 'F4': 'GP5/pin7',
       'F5': 'GP6/pin9', 'F6': 'GP7/pin10', 'F7': 'GP8/pin11', 'F8': 'GP9/pin12'}

print("\n" + "=" * 78)
print("  CONCRETE BUILD — pin map for the BALANCED winner (phase-locked pairs)")
print("=" * 78)
win = report['balanced']
# assign each 2-TX plate a phase-locked pair within one PIO block; 1-TX plates take a single channel
chans = PIO0 + PIO1
ci = 0
print(f"  {'plate':<12} {'TX role':<26} {'channel(s)':<22} interference?")
for p in win['plates']:
    ntx = win['tx'][p]
    # keep a 2-TX plate's pair inside one PIO block (phase-lock)
    if ntx == 2:
        # find a free aligned pair
        pair = None
        for blk in (PIO0, PIO1):
            free = [c for c in blk if c in chans[ci:]]
            if len(free) >= 2:
                pair = free[:2]; break
        if pair:
            for c in pair: chans.remove(c)
            locked = 'YES (phase-locked pair → heading/interference)' if (set(pair) <= set(PIO0) or set(pair) <= set(PIO1)) else 'no'
            print(f"  {p:<12} {'TX-a + TX-b (multipoint)':<26} {pair[0]+' + '+pair[1]:<22} {locked}")
            print(f"  {'':<12} {'':<26} {PIN[pair[0]]+', '+PIN[pair[1]]}")
    else:
        c = chans.pop(0)
        print(f"  {p:<12} {'single TX':<26} {c+' ('+PIN[c]+')':<22} no")
print(f"\n  RX: one pickup per plate → parallel → preamp → PicoScope Ch A")
print(f"  Ch B: tap the NCO drive bus (the 4K7-summed reference) → phase reference for interference")
print(f"  WIRE-LENGTH RULE: NCO central; every TX lead < a few cm; RX leads short + equal.")

json.dump({'timestamp': TS, 'collision_bw': args.collision_bw, 'tone_budget': args.tone_budget,
           'seed_plates': {k: {kk: vv for kk, vv in v.items() if kk != 'clean'} for k, v in SEED.items()},
           'winners': {reg: {'plates': r['plates'], 'tx': r['tx'], 'n_tones': r['n_tones'],
                             'n_usable': r['n_usable'], 'n_clean': r['n_clean']} for reg, r in report.items()}},
          open(OUT / f'array_design_{TS}.json', 'w'), indent=2)
print(f"\n  Saved: {OUT / f'array_design_{TS}.json'}")
print("=" * 78)
