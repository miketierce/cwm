#!/usr/bin/env python3
"""Superposition errors at matched and mismatched harmonic frequencies (Oct 27; exploratory, post hoc).

The FT-1 analysis predicts the n-th harmonic of a drive at f from H measured at the grid point n*f. NCO periods
are whole 126 MHz clock cycles, so the harmonic n*f_act(f) and the grid point's own frequency f_act(n*f) agree
only when the period divides evenly; otherwise they differ by up to about 50 Hz. A point is "matched" when they
agree within 0.5 Hz. The split depends only on NCO arithmetic, not on any measured value.

Reads the unchanged superposition outputs (derived/superposition_*.json) and trials; writes matched_points.json.

    python3 data/results/k_eff/range_20261027/matched_points.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
sys.path.insert(0, str(REPO))
from tools.k_eff_ft1_capture import pio_actual_freq  # noqa: E402

RES = REPO / 'data/results/k_eff'
ORDERS = {'2f': 2, '3f': 3}
MATCH_HZ = 0.5
WITHIN = ['FT1-S1', 'FT1-S2', 'FT1-S3', 'XR-F2-A5-1', 'XR-F2-A5-2', 'XR-F2-A2-1', 'XR-F2-A2-2',
          'XD-F2-D05-A5', 'XD-F2-D20-A5', 'XR-F1-A5-1', 'XR-F1-A5-2', 'XR-F1-A2-1', 'XR-F1-A2-2']
RANGE_PAIRS = {ch: (f'XR-{ch}-A5-1', f'XR-{ch}-A5-2', f'XR-{ch}-A2-1', f'XR-{ch}-A2-2') for ch in ('F2', 'F1')}


def mismatch_hz(f: int, n: int) -> float:
    return n * pio_actual_freq(f) - pio_actual_freq(n * f)


def points(session: str, tier: str, ch: str, order: str) -> dict:
    path = RES / session / 'derived' / f'superposition_{tier}.json'
    chans = json.loads(path.read_text())['channels']
    if ch not in chans:
        return {}
    return {p['f_hz']: p for p in chans[ch]['result'][order]['points'] if not p['excluded'] and p.get('e') is not None}


def split(pts: dict, n: int) -> dict:
    m = {True: [], False: []}
    for f, p in pts.items():
        m[abs(mismatch_hz(f, n)) < MATCH_HZ].append(p)
    out = {}
    for key, group in (('matched', m[True]), ('mismatched', m[False])):
        e = [p['e'] for p in group]
        out[key] = {'n': len(e), 'e_median': float(np.median(e)) if e else None,
                    'e_p90': float(np.percentile(e, 90)) if e else None,
                    'mag_bias_median': float(np.median([p['mag_bias'] for p in group])) if e else None,
                    'phase_bias_deg_median': float(np.median([p['phase_bias_deg'] for p in group])) if e else None}
    out['all'] = {'n': len(pts), 'e_median': float(np.median([p['e'] for p in pts.values()]))}
    return out


def loopback(session: str) -> dict:
    """Same superposition error on LOOPBACK trials (scope only, flat H), split the same way."""
    z = lambda r, k: complex(float(r[f'{k}_re_mV']), float(r[f'{k}_im_mV']))  # noqa: E731
    rows = [r for r in csv.DictReader((RES / session / 'trials.csv').open())
            if r['state'] == 'LOOPBACK' and not any(int(r[x]) for x in ('ovf_A', 'ovf_B', 'clip_A', 'clip_B'))]
    out = {}
    for ch in ('F1', 'F2'):
        rr = [r for r in rows if r['channel'] == ch]
        hs = {}
        for r in rr:
            hs.setdefault(int(r['freq_cmd_hz']), []).append(z(r, 'zA') / z(r, 'zB'))
        h = {f: np.mean(v) for f, v in hs.items()}
        out[ch] = {}
        for order, n in ORDERS.items():
            top = 60_000 if n == 2 else 40_000
            byf = {}
            for r in rr:
                f = int(r['freq_cmd_hz'])
                if 30_000 <= f <= top and n * f in h:
                    byf.setdefault(f, []).append((z(r, f'zA{n}'), z(r, f'zB{n}')))
            e = {True: [], False: []}
            for f, v in byf.items():
                a, b = np.array([x[0] for x in v]), np.array([x[1] for x in v])
                e[abs(mismatch_hz(f, n)) < MATCH_HZ].append(
                    float(np.sqrt(np.mean(np.abs(a - h[n * f] * b) ** 2)) / np.sqrt(np.mean(np.abs(a) ** 2))))
            out[ch][order] = {'matched_e_median': float(np.median(e[True])), 'n_matched': len(e[True]),
                              'mismatched_e_median': float(np.median(e[False])), 'n_mismatched': len(e[False])}
    return out


def main():
    grid = {order: [f for f in range(30_000, (60_000 if n == 2 else 40_000) + 1, 500)] for order, n in ORDERS.items()}
    out = {'status': 'exploratory, post hoc; does not change any preregistered outcome',
           'match_rule_hz': MATCH_HZ,
           'mismatch_by_drive_hz': {order: {f: round(mismatch_hz(f, n), 2) for f in grid[order]} for order, n in ORDERS.items()},
           'within': {}, 'heldout': {}, 'loopback': {}, 'range_matched': {}}
    for s in WITHIN:
        if not (RES / s / 'derived' / 'superposition_within.json').exists():
            continue
        out['within'][s] = {ch: {order: split(points(s, 'within', ch, order), n) for order, n in ORDERS.items()}
                            for ch in ('F1', 'F2') if points(s, 'within', ch, '2f')}
    out['heldout']['FT1-S1+FT1-S2->FT1-S3'] = {ch: {order: split(points('FT1-S3', 'heldout', ch, order), n)
                                                    for order, n in ORDERS.items()} for ch in ('F1', 'F2')}
    for s in ('FT1-S1', 'FT1-S2', 'FT1-S3'):
        out['loopback'][s] = loopback(s)
    for ch, (a5a, a5b, a2a, a2b) in RANGE_PAIRS.items():
        if not all((RES / s / 'derived' / 'superposition_within.json').exists() for s in (a5a, a5b, a2a, a2b)):
            continue
        out['range_matched'][ch] = {}
        for order, n in ORDERS.items():
            p = [points(s, 'within', ch, order) for s in (a5a, a5b, a2a, a2b)]
            fs = [f for f in p[0] if abs(mismatch_hz(f, n)) < MATCH_HZ and all(f in x for x in p)]
            e5 = np.array([np.mean([p[0][f]['e'], p[1][f]['e']]) for f in fs])
            e2 = np.array([np.mean([p[2][f]['e'], p[3][f]['e']]) for f in fs])
            out['range_matched'][ch][order] = {'n': len(fs), 'e_median_A5': float(np.median(e5)),
                                               'e_median_A2': float(np.median(e2)),
                                               'A2_better_at': int(np.sum(e2 < e5)),
                                               'per_point_ratio_median': float(np.median(e2 / e5))}
    (OUT / 'matched_points.json').write_text(json.dumps(out, indent=1) + '\n')

    for s, chs in out['within'].items():
        print(s, ' | '.join(f"{ch} {o} {v['matched']['e_median']:.4f} (n {v['matched']['n']}) / "
                            f"{v['mismatched']['e_median']:.3f} (n {v['mismatched']['n']})"
                            for ch, d in chs.items() for o, v in d.items()))
    for ch, d in out['heldout']['FT1-S1+FT1-S2->FT1-S3'].items():
        print('held out', ch, {o: (round(v['matched']['e_median'], 4), round(v['all']['e_median'], 4)) for o, v in d.items()})
    for s, d in out['loopback'].items():
        print('loopback', s, {ch: {o: (round(v['matched_e_median'], 4), round(v['mismatched_e_median'], 4))
                                   for o, v in x.items()} for ch, x in d.items()})
    for ch, d in out['range_matched'].items():
        print('range, matched', ch, d)


if __name__ == '__main__':
    main()
