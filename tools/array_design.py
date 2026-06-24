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
ap.add_argument('--max-tx', type=int, default=4, help='max TX PZTs per plate (multipoint). 100mm easily supports 4+')
ap.add_argument('--regime', choices=['tracking', 'classification', 'balanced', 'kernel', 'all'], default='all')
ap.add_argument('--catalogs', type=str, default='data/results/array_design/catalogs')
args = ap.parse_args()

OUT = Path('data/results/array_design'); OUT.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')

# ─── Plate catalogs (MEASURED where available, else physics-estimated) ───────
# Each plate: band (lo,hi) Hz, n_modes (CLEAN attribution modes), clean modes
# [(freq, SNR)], cand (KEEP-COLLISIONS candidate bins per SINGLE TX — MEASURED
# 2026-06-21: F1=35, F2=29, F4=48, F5=52; this is the pool a LEARNED readout
# selects from, ~4-5× the clean count), multipoint_gain (extra modes a 2nd TX
# excites), Q_typ. Sources: 100mm/25mm from Q-factor sweep 2026-06-05 + censuses;
# slides estimated from f ∝ h/L² (75×25×1 soda-lime, 3:1 rect → asymmetric comb).
SEED = {
    'plate_100mm': dict(size='100x100x1 fused-silica', band=(40000, 100000), n_modes=14, cand=35,
                        clean=[(47700, 9.0), (66150, 7.0), (96100, 8.0)], multipoint_gain=4,
                        Q_typ=500, note='LOW band, dense comb (MEASURED Q 410-743; keep-coll F1=35,F2=29,F5=52)'),
    'plate_25mm':  dict(size='25x25x1 fused-silica', band=(230000, 330000), n_modes=4, cand=48,
                        clean=[(321200, 10.0), (232700, 6.0)], multipoint_gain=2,
                        Q_typ=520, note='HIGH band, sparse CLEAN but keep-coll F4=48 (low 56-91k + main). '
                                        '(low 56-91k cluster COLLIDES with 100mm — a FEATURE in kernel regime)'),
    'slide_A':     dict(size='75x25x1 soda-lime', band=(100000, 175000), n_modes=10, cand=24,
                        clean=[(120000, 6.0), (150000, 6.0)], multipoint_gain=5,
                        Q_typ=300, note='MID-LOW band (EST f∝h/L²; heaviest mass → lowest; cand EST ~2.4× clean)'),
    'slide_B':     dict(size='75x25x1 soda-lime', band=(140000, 215000), n_modes=10, cand=24,
                        clean=[(160000, 6.0), (195000, 6.0)], multipoint_gain=5,
                        Q_typ=300, note='MID band (EST; medium mass)'),
    'slide_C':     dict(size='75x25x1 soda-lime', band=(180000, 255000), n_modes=10, cand=24,
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


def raw_modes(p, m, use_cand=False):
    """Modes excited by m TX positions on plate p.
    CLEAN path (attribution): start from n_modes, ADD multipoint_gain per extra TX
    (decay 0.6), cap 2.5×. CANDIDATE path (kernel/keep-collisions, use_cand=True):
    start from the MEASURED keep-collisions candidate count (cand) and scale it
    MULTIPLICATIVELY — each well-placed extra TX is a new excitation pattern that
    reveals proportionally more repeatable bins (2TX→×1.5, 3→×1.8, 4→×1.98),
    saturating at 2.5× (the band's modal-density ceiling, not the PZT count).
    This fixes the 'feature pool looks low' undercount: features scale with
    TX-per-plate; the measured single-TX count was only the floor."""
    if use_cand:
        base = SEED[p].get('cand', SEED[p]['n_modes'])
        if m <= 1:
            return float(base)
        extra = 0.5 * sum(0.6 ** j for j in range(m - 1))   # multiplicative, saturating
        return base * min(1.0 + extra, 2.5)
    base = SEED[p]['n_modes']
    if m <= 1:
        return float(base)
    g = SEED[p]['multipoint_gain']
    extra = g * sum(0.6 ** j for j in range(m - 1))   # m=2 → +g (back-compatible)
    return min(base + extra, 2.5 * base)


def evaluate(plate_ids, tx_per_plate):
    """plate_ids on the shared bus; tx_per_plate = {pid: m TX}. Returns RAW modes
    and the COLLISION LOSS separately, so each regime decides what a collision is
    worth: attribution (a collision is a lost mode) vs kernel/learned readout (a
    collision bin is a repeatable coherent-sum FEATURE — MEASURED 2026-06-21, the
    discarded collision pile had HIGHER mean SNR than the kept pile)."""
    n_tones = sum(tx_per_plate[p] for p in plate_ids)
    if n_tones > args.tone_budget:
        return None
    raw = {p: raw_modes(p, tx_per_plate[p]) for p in plate_ids}
    cand = {p: raw_modes(p, tx_per_plate[p], use_cand=True) for p in plate_ids}
    lost = 0.0
    for a, b in itertools.combinations(plate_ids, 2):
        ov = band_overlap(SEED[a]['band'], SEED[b]['band'])
        if ov <= 0:
            continue
        dens_a = raw[a] / max(1, SEED[a]['band'][1] - SEED[a]['band'][0])
        dens_b = raw[b] / max(1, SEED[b]['band'][1] - SEED[b]['band'][0])
        lost += ov * (dens_a + dens_b)
    total_raw = sum(raw.values())
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
    return dict(plates=plate_ids, tx=dict(tx_per_plate), n_tones=n_tones,
                total_raw=round(total_raw, 1), total_cand=round(sum(cand.values()), 1),
                lost=round(lost, 1), n_clean=n_clean,
                bands=[(p, SEED[p]['band']) for p in plate_ids])


# ─── Search all plate subsets × TX counts ────────────────────────────────────
all_plates = list(SEED.keys())
results = []
for k in range(1, len(all_plates) + 1):
    for subset in itertools.combinations(all_plates, k):
        # try 2 TX on each (multipoint) down to 1 TX; enumerate a few sensible mixes
        for tx_choice in itertools.product(range(1, args.max_tx + 1), repeat=len(subset)):
            txmap = {p: t for p, t in zip(subset, tx_choice)}
            r = evaluate(list(subset), txmap)
            if r:
                results.append(r)


def regime_weights(regime):
    # (w_dim, w_clean, w_cost, collision_value)
    #   collision_value 0 = ATTRIBUTION (a collision is a lost mode)
    #   collision_value 1 = KERNEL/learned readout (a collision bin is a usable feature)
    return {'tracking':       (1.0, 4.0, 1.5, 0.0),
            'classification':  (2.0, 1.0, 1.0, 0.3),
            'balanced':        (1.0, 3.0, 2.0, 0.0),
            'kernel':          (1.5, 1.0, 0.3, 1.0)}[regime]


def usable(r, cv):
    """usable features given how much a collision is worth (cv∈[0,1]).
    cv=0 ATTRIBUTION: clean modes minus collision loss. cv=1 KERNEL: the full
    keep-collisions CANDIDATE pool (collisions kept — MEASURED equal SNR/corr,
    2026-06-21). Interpolated so classification (cv=0.3) blends the two."""
    clean = r['total_raw'] - r['lost']
    return max(0.0, (1.0 - cv) * clean + cv * r.get('total_cand', r['total_raw']))


def rescore(r, w):
    return round(w[0] * usable(r, w[3]) + w[1] * r['n_clean'] - w[2] * r['n_tones'], 1)


regimes = ['tracking', 'classification', 'balanced', 'kernel'] if args.regime == 'all' else [args.regime]
report = {}
for reg in regimes:
    w = regime_weights(reg)
    ranked = sorted(results, key=lambda r: -rescore(r, w))
    best = ranked[0]
    nu = round(usable(best, w[3]), 1)
    print(f"\n[{reg.upper()}]  (w_dim={w[0]}, w_clean={w[1]}, w_cost={w[2]}, collision_value={w[3]})")
    print(f"  BEST: {[p.replace('plate_','').replace('slide_','sl') for p in best['plates']]}  "
          f"tones={best['n_tones']}  usable≈{nu}  clean={best['n_clean']}  (raw {best['total_raw']}, collisions {best['lost']})")
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
print("  CONCRETE BUILD — pin map for the KERNEL winner (max-hardware, collisions = features)")
print("=" * 78)
win = report['kernel']
avail = PIO0 + PIO1   # channels not yet assigned
print(f"  {'plate':<12} {'TX (multipoint)':<14} {'channels':<28} phase-locked?")
for p in win['plates']:
    ntx = int(win['tx'][p])
    # prefer ntx channels all inside ONE PIO block so they phase-lock (heading/interference)
    chosen = None
    for blk in (PIO0, PIO1):
        free = [c for c in blk if c in avail]
        if len(free) >= ntx:
            chosen = free[:ntx]; break
    if chosen is None:                       # spill across blocks (not all phase-locked)
        chosen = list(avail)[:ntx]
    for c in chosen:
        avail.remove(c)
    locked = ('YES (one PIO block → heading/interference)'
              if (set(chosen) <= set(PIO0) or set(chosen) <= set(PIO1))
              else 'partial (spans PIO blocks)')
    print(f"  {p:<12} {str(ntx)+' TX':<14} {' + '.join(chosen):<28} {locked}")
    print(f"  {'':<12} {'':<14} {', '.join(PIN[c] for c in chosen)}")
print(f"\n  RX: one pickup per plate → parallel → preamp → PicoScope Ch A")
print(f"  Ch B: tap the NCO drive bus (the 4K7-summed reference) → phase reference for interference")
print(f"  WIRE-LENGTH RULE: NCO central; every TX lead < a few cm; RX leads short + equal.")

# ─── ARRAY FEATURE POOL — SPLIT (no relay) vs RELAY fan-out (2026-06-22) ──────
# Models keep-collisions candidate pool × multipoint, with TWO corrections that
# decide the relay question: (1) BAND SATURATION — N copies of one plate-type
# share that band's modal capacity (identical plates ring at the SAME freqs, so
# extra copies add only diversity×ceiling unless mass/thickness-spread); (2) a TX
# LEAD-LENGTH EMI derate (the relay's only real cost). The 4 LARGE plates (where
# phase compute lives, 99.5% null) fit the 4 PIO coherent 2-TX slots on DEDICATED
# channels — firmware-muted (Foff/A:0), no relay, no added length.
print("\n" + "=" * 78)
print("  ARRAY FEATURE POOL — split (no relay)  vs  relay fan-out")
print("=" * 78)
CEIL = {'plate_100mm': 14, 'plate_25mm': 6, 'slide_A': 8}   # modal-independence ceilings (per band)


def mp_factor(m):
    return min(1.0 + 0.5 * sum(0.6 ** j for j in range(max(0, m - 1))), 2.5)


def lead_emi_factor(added_cm, twisted=True):
    """SNR-retention from TX leads radiating EMI into the RX bus. ANCHOR
    (2026-06-05 MEASURED): ~100 cm UNTWISTED leads cost ~8× SNR (worst high-freq
    modes up to 260×); ~3 cm recovered it. Twisted-pair/coax cancels the
    differential field ~30 dB (≈32×) = the dominant lever. retention =
    1/(1+(cm/100)·7·c), c=1 untwisted / 1/32 twisted. Check: 100cm untwisted→0.13
    (=the measured 8×). ESTIMATE — confirm with a relay-in-path census."""
    c = 1.0 if not twisted else 1.0 / 32.0
    return 1.0 / (1.0 + (max(0.0, added_cm) / 100.0) * 7.0 * c)


def array_pool(groups, lead_factor=1.0, diversity=0.2):
    """groups: (label, pid, n_copies, tx). Independent dim SATURATES per band: N
    copies of one plate-type share its modal ceiling; extra copies add only
    diversity×ceiling (identical plates ring alike) unless mass/thickness-spread
    raises diversity toward 1. Candidate pool scales copies × multipoint × lead-EMI."""
    cand = indep = plates = txp = 0.0
    rows = []
    for label, pid, n, tx in groups:
        cpp = SEED[pid].get('cand', SEED[pid]['n_modes']) * mp_factor(tx) * lead_factor
        itype = min(cpp, CEIL[pid]) * (1.0 + diversity * (n - 1))
        cand += n * cpp; indep += itype; plates += n; txp += n * tx
        rows.append((label, int(n), int(tx), cpp, itype))
    return dict(cand=cand, indep=indep, plates=int(plates), tx=int(txp), rows=rows)


# SPLIT (NO relay): 4 large plates on the 4 PIO coherent 2-TX slots (deep 99.5%
# nulls + phase compute, firmware-muted, leads < a few cm) + 7 small plates one-
# per-PWM-channel. 11 plates, 15 tones, ZERO added lead length.
SPLIT = [('100mm', 'plate_100mm', 4, 2), ('25x25', 'plate_25mm', 4, 1), ('25x76', 'slide_A', 3, 1)]
# RELAY-16: max-plate fan-out — a TX relay selects/mutes plates that SHARE a
# channel, but adds lead length → radiated-EMI derate on the whole TX bus.
RELAY = [('100mm', 'plate_100mm', 2, 4), ('25x25', 'plate_25mm', 7, 2), ('25x76', 'slide_A', 7, 2)]

lf_short = lead_emi_factor(3, twisted=True)
lf_relayT = lead_emi_factor(20, twisted=True)
lf_relayU = lead_emi_factor(20, twisted=False)
split = array_pool(SPLIT, lf_short)
relayT = array_pool(RELAY, lf_relayT)
relayU = array_pool(RELAY, lf_relayU)

print(f"  lead-EMI retention: 3cm twisted={lf_short:.2f}  20cm twisted={lf_relayT:.2f}  "
      f"20cm UNtwisted={lf_relayU:.2f}  (anchor: 100cm untwisted=0.13 = measured 8×)")
print(f"\n  {'scenario':<27} {'relay?':<6} {'plates':>6} {'tones':>6} {'cand':>6} {'indep':>6}")
print(f"  {'SPLIT large→PIO small→PWM':<27} {'no':<6} {split['plates']:>6} {'15':>6} {split['cand']:>6.0f} {split['indep']:>6.0f}")
print(f"  {'RELAY-16 (20cm twisted)':<27} {'yes':<6} {relayT['plates']:>6} {'15':>6} {relayT['cand']:>6.0f} {relayT['indep']:>6.0f}")
print(f"  {'RELAY-16 (20cm untwisted)':<27} {'yes':<6} {relayU['plates']:>6} {'15':>6} {relayU['cand']:>6.0f} {relayU['indep']:>6.0f}")
print(f"\n  SPLIT large plates: 4 × (2-TX, 99.5% null, phase compute) on PIO slots 4/5,6/7,9/10,11/12")
print(f"  RELAY adds {relayT['plates']-split['plates']} plates for {relayT['indep']-split['indep']:+.0f} independent dim (twisted) — small, because")
print(f"  identical-band copies SATURATE (7 same 25×25 share one band's ~6 modes, not 7×6).")
print(f"  Untwisted relay craters the candidate pool {relayT['cand']:.0f}→{relayU['cand']:.0f} "
      f"(−{100*(1-relayU['cand']/relayT['cand']):.0f}%) = the measured EMI hit; the weakest")
print(f"  high-freq modes (321k etc.) vanish first.")
print(f"  NOTE: stacking large plates only pays if you SPREAD them (mass/thickness → diversity↑);")
print(f"        identical copies saturate. Candidates ≠ free dims (2026-06-20; sample count bounds fit).")
print(f"  → VERDICT: SPLIT, no relay. Mute via firmware on dedicated channels. The +{relayT['plates']-split['plates']} relay")
print(f"     plates buy ~{relayT['indep']-split['indep']:+.0f} dim and risk the one thing you measured an 8× penalty on.")
tot_cand, tot_indep, tot_plates, tot_tx_pzt = relayT['cand'], relayT['indep'], relayT['plates'], relayT['tx']

# ─── PATH-INTEGRAL + CANCELLATION CONFIG (2026-06-22) ─────────────────────────
# Goal: parallel access to future-states-of-future-states (sum-over-histories)
# + interference cancellation. BOTH live in the phase-coherent PIO domain. A
# config spends the 8 PIO SMs over coherent plates; phase coherence holds WITHIN
# a 4-SM block (so N≤4 per plate with no firmware change). For a coherent plate
# with N same-freq phase-locked TX the readout is the N-path sum |Σ a_k e^{iφ_k}|²:
#   cross-terms  = C(N,2)   pairwise history-interference (MEASURED: 7-term fit at
#                           N=3, R²=0.92, 2026-06-21 three_path.py)
#   phase dims   = N-1      continuous control axes (the "future" inputs)
#   capacity     ≈ K^(N-1)  phase-encoded associative-memory states (cancel-match K=5)
# Cancellation DEPTH scales with plate size (MEASURED 100mm 99.5% vs 25mm ~96%).
# "Parallel access" = # independent coherent propagators readable at once.
from math import comb
print("\n" + "=" * 78)
print("  PATH-INTEGRAL + CANCELLATION — best coherent PIO config")
print("=" * 78)
K_PHI = 10          # distinguishable phase states / control axis (cancel-match used K=5; 10-30 feasible)
NULL = {'plate_100mm': 0.995, 'plate_25mm': 0.96, 'slide_A': 0.95}   # MEASURED null depth (size effect)


def coh_score(config):
    """config: list of (pid, N) coherent plates (N same-freq phase-locked TX)."""
    sms = sum(N for _, N in config)
    return dict(sms=sms, parallel=len(config),
                depth=sum(comb(N, 2) for _, N in config),         # Σ pairwise cross-terms
                phase_dim=sum(N - 1 for _, N in config),          # Σ continuous phase axes
                capacity=sum(K_PHI ** (N - 1) for _, N in config),  # phase-memory states
                cancel=round(sum(NULL.get(p, 0.95) for p, _ in config), 2))   # parallel null channels


L = 'plate_100mm'   # large plate: deepest null AND densest comb (parallel forward projections)
CONFIGS = {
    '2×4TX (1 per block)':     [(L, 4), (L, 4)],
    '1×4TX + 2×2TX':           [(L, 4), (L, 2), (L, 2)],
    '4×2TX':                   [(L, 2), (L, 2), (L, 2), (L, 2)],
    '6TX* + 2TX':              [(L, 6), (L, 2)],   # *needs PIO0/PIO1 start-sync (calib offset)
    '8TX* (one plate)':        [(L, 8)],           # *cross-block sync; N>~6 hits modal ceiling
}
print(f"  {'config':<22} {'SMs':>3} {'parallel':>8} {'cross-terms':>11} {'phaseDim':>8} {'capacity':>9} {'cancelCh':>8}")
for name, cfg in CONFIGS.items():
    s = coh_score(cfg)
    star = '*' if s['sms'] > 4 and any(N > 4 for _, N in cfg) else ' '
    print(f"  {name:<22} {s['sms']:>3} {s['parallel']:>8} {s['depth']:>11} {s['phase_dim']:>8} {s['capacity']:>9} {s['cancel']:>8.2f}")
print(f"\n  capacity ≈ K^(phaseDim), K≈{K_PHI} phase states/axis (MEASURED cancel-match K=5).")
print(f"  cross-terms = ΣC(N,2) = the MEASURED 7-term N=3 fit (R²=0.92) generalized.")
print(f"  * = needs cross-block PIO0/PIO1 start-sync (calibrated fixed offset) + N>~6 is past")
print(f"      the ~6 modal-independence ceiling (extra paths redundant).")
print(f"  RECOMMEND: 2×4TX — max coherent DEPTH (12 cross-terms, capacity ~2000) that KEEPS")
print(f"  2 parallel propagators + 2 deep (99.5%) null channels, NO firmware change (each")
print(f"  plate's 4 TX live in one PIO block). Read the FULL comb: each mode evolves at its")
print(f"  own rate = parallel forward projections. Keep the Ch B 4K7 tap (cancellation = complex).")

json.dump({'timestamp': TS, 'collision_bw': args.collision_bw, 'tone_budget': args.tone_budget, 'max_tx': args.max_tx,
           'seed_plates': {k: {kk: vv for kk, vv in v.items() if kk != 'clean'} for k, v in SEED.items()},
           'split_no_relay': {'plates': split['plates'], 'candidate_pool': round(split['cand']),
                              'independent_dim': round(split['indep'])},
           'relay_fanout': {'plates': relayT['plates'], 'tx_pzts': relayT['tx'],
                            'candidate_pool': round(relayT['cand']), 'independent_dim': round(relayT['indep']),
                            'lead_factor_20cm_twisted': round(lf_relayT, 3),
                            'cand_untwisted': round(relayU['cand'])},
           'coherent_configs': {name: coh_score(cfg) for name, cfg in CONFIGS.items()},
           'winners': {reg: {'plates': r['plates'], 'tx': r['tx'], 'n_tones': r['n_tones'],
                             'n_usable': round(usable(r, regime_weights(reg)[3]), 1),
                             'total_raw': r['total_raw'], 'total_cand': r.get('total_cand'),
                             'collisions': r['lost'], 'n_clean': r['n_clean']}
                       for reg, r in report.items()}},
          open(OUT / f'array_design_{TS}.json', 'w'), indent=2)
print(f"\n  Saved: {OUT / f'array_design_{TS}.json'}")
print("=" * 78)
