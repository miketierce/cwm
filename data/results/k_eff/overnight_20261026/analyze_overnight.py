#!/usr/bin/env python3
"""Offline analysis of the Oct 26/27 overnight stability run (exploratory, not preregistered).

Per cycle: consecutive-cycle change on both paths, change against a reference cycle, and the gain + common
mode-shift decomposition of tools/k_eff_ft1_drift.py against that reference. CH2 uses complex H = zA/zB.
CH1 has no drive reference on Ch B in the start wiring, so it uses |zA| and a magnitude-only fit. The shift
is then regressed on the Pico die temperature over the undisturbed stretch.

    python3 data/results/k_eff/overnight_20261026/analyze_overnight.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
from tools.k_eff_ft1_capture import GRID_FILE, alias_flags  # noqa: E402
from tools.k_eff_ft1_drift import MIN_RX_SNR, STEP_HZ, between_session_points, fit_models  # noqa: E402

REF_CYCLE = 21            # first cycle after the last bench visit (22:35-22:37)
UNDISTURBED = range(21, 46)
STEPS = {'19:32 step': (10, 11), '22:32 step': (19, 20)}


def load_cycle(n: int, noise_a: float) -> dict:
    d = np.load(HERE / f'cycle_{n:03d}.npz')
    ok = (d['kind'] == 'grid') & (d['ovf'] == 0) & (d['clipA'] == 0) & (d['clipB'] == 0)
    out = {}
    for ch in ('F1', 'F2'):
        m = ok & (d['ch'] == ch)
        by_f: dict[int, list] = {}
        for f, za, zb in zip(d['f_cmd'][m], d['zA'][m], d['zB'][m]):
            by_f.setdefault(int(f), []).append((za, zb))
        out[ch] = {f: {'H': np.mean([za / zb for za, zb in v]) if ch == 'F2' else np.mean([abs(za) for za, _ in v]),
                       'snr': np.mean([abs(za) for za, _ in v]) / noise_a, 'se': (1.0, 1.0)}
                   for f, v in by_f.items()}
    return out


def median_change(a: dict, b: dict, cplx: bool) -> float:
    fs = [f for f in a if f in b]
    return float(100 * np.median([abs(b[f]['H'] / a[f]['H'] - 1) if cplx else abs(abs(b[f]['H']) / abs(a[f]['H']) - 1)
                                  for f in fs]))


def usable(a: dict, b: dict, freqs: list[int], flagged: set) -> list[int]:
    return [f for f in freqs if f not in flagged and f in a and f in b and min(a[f]['snr'], b[f]['snr']) >= MIN_RX_SNR]


def fit_ch2(a: dict, b: dict, freqs: list[int]) -> dict:
    g = fit_models(between_session_points(a, b, freqs), per='')
    gs = g['gain_plus_shift']
    return {'n_points': g['n_points'], 'g_mag_pct': gs['g_mag_pct'], 'g_phase_deg': gs['g_phase_deg'],
            'shift_ppm': gs['freq_drift_ppm'], 'shift_se': gs['freq_drift_se'],
            'variance_explained': g['weighted_variance_explained_gain_plus_shift']}


def fit_ch1(a: dict, b: dict, freqs: list[int]) -> dict:
    """Magnitude-only: ln(|A_b|/|A_a|) = g + c * f d ln|A|/df, shift = -c."""
    rows = []
    for f in freqs:
        lo, hi = f - STEP_HZ, f + STEP_HZ
        if any(x not in s for s in (a, b) for x in (lo, hi)):
            continue
        slope = np.mean([np.log(s[hi]['H'] / s[lo]['H']) for s in (a, b)]) * f / (2 * STEP_HZ)
        rows.append((np.log(b[f]['H'] / a[f]['H']), slope))
    y, p = np.array(rows).T
    x = np.column_stack([np.ones_like(p), p])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    cov = np.linalg.inv(x.T @ x) * np.sum(resid ** 2) / (len(y) - 2)
    return {'n_points': len(y), 'g_mag_pct': 100 * beta[0], 'shift_ppm': -1e6 * beta[1],
            'shift_se': 1e6 * np.sqrt(cov[1, 1]), 'variance_explained': 1 - np.sum(resid ** 2) / np.sum((y - y.mean()) ** 2)}


def die_c(s: str) -> float:
    return float(s.split(':')[1].split('C')[0])


def regress(x: list[float], y: list[float], se: list[float]) -> dict:
    x, y, w = np.array(x), np.array(y), 1 / np.array(se) ** 2
    xm, ym = np.average(x, weights=w), np.average(y, weights=w)
    slope = np.sum(w * (x - xm) * (y - ym)) / np.sum(w * (x - xm) ** 2)
    resid = y - ym - slope * (x - xm)
    scale = np.sum(w * resid ** 2) / (len(x) - 2)
    return {'slope_ppm_per_C': float(slope), 'slope_se': float(np.sqrt(scale / np.sum(w * (x - xm) ** 2))),
            'r': float(np.corrcoef(x, y)[0, 1]), 'n': len(x)}


def main():
    log = [json.loads(line) for line in (HERE / 'log.jsonl').read_text().splitlines()]
    cycles = {r['cycle']: r for r in log if r['event'] == 'cycle'}
    grid = json.loads(GRID_FILE.read_text())['freqs_hz']
    s2 = json.loads((REPO / 'data/results/k_eff/FT1-S2/manifest.json').read_text())
    flagged = set(alias_flags(grid, s2['acquisition']['sample_rate_hz'])[1])
    data = {n: load_cycle(n, r['quiet_noise_mV']['A']) for n, r in cycles.items()}
    ref = data[REF_CYCLE]

    per_cycle = []
    for n, r in cycles.items():
        d = data[n]
        prev = data.get(n - 1, d)
        entry = {'cycle': n, 'start': r['start'], 'die_start_C': die_c(r['temp_start']), 'die_end_C': die_c(r['temp_end']),
                 'h60': r['check_60k']['H'], 'ch2_change_vs_prev_pct': median_change(prev['F2'], d['F2'], True),
                 'ch1_level_change_vs_prev_pct': median_change(prev['F1'], d['F1'], False),
                 'ch2_change_vs_ref_pct': median_change(ref['F2'], d['F2'], True),
                 'ch1_level_change_vs_ref_pct': median_change(ref['F1'], d['F1'], False)}
        if n != REF_CYCLE:
            entry['ch2_fit_vs_ref'] = fit_ch2(ref['F2'], d['F2'], usable(ref['F2'], d['F2'], grid, flagged))
            entry['ch1_fit_vs_ref'] = fit_ch1(ref['F1'], d['F1'], usable(ref['F1'], d['F1'], grid, flagged))
        per_cycle.append(entry)

    quiet = [e for e in per_cycle if e['cycle'] in UNDISTURBED and e['cycle'] != REF_CYCLE]
    temp_fit = {}
    for ch in ('ch2', 'ch1'):
        xs = [e['die_start_C'] for e in quiet] + [next(e['die_start_C'] for e in per_cycle if e['cycle'] == REF_CYCLE)]
        ys = [e[f'{ch}_fit_vs_ref']['shift_ppm'] for e in quiet] + [0.0]
        ses = [e[f'{ch}_fit_vs_ref']['shift_se'] for e in quiet]
        temp_fit[ch] = regress(xs, ys, ses + [float(np.median(ses))])

    steps = {}
    for name, (a, b) in STEPS.items():
        da, db = data[a], data[b]
        steps[name] = {'cycles': [a, b],
                       'ch2': {**fit_ch2(da['F2'], db['F2'], usable(da['F2'], db['F2'], grid, flagged)),
                               'median_change_pct': median_change(da['F2'], db['F2'], True)},
                       'ch1': {**fit_ch1(da['F1'], db['F1'], usable(da['F1'], db['F1'], grid, flagged)),
                               'median_level_change_pct': median_change(da['F1'], db['F1'], False)}}

    out = {'status': 'exploratory, not preregistered', 'reference_cycle': REF_CYCLE,
           'undisturbed_cycles': [UNDISTURBED.start, UNDISTURBED.stop - 1],
           'model': 'ln(H / H_ref) = g + c * P(f), shift_ppm = -1e6 * c (CH1: magnitude only)',
           'selection': {'min_rx_snr': MIN_RX_SNR, 'excluded': 'alias-flagged (order 1) and grid edges',
                         'weights': 'uniform (2 repeats per point give unusable per-point errors)'},
           'shift_vs_die_temperature': temp_fit, 'steps': steps, 'per_cycle': per_cycle}
    (HERE / 'overnight_analysis.json').write_text(json.dumps(out, indent=1, default=float))

    print(f"{'cyc':>3} {'start':>5} {'die':>5} {'dCH2':>5} {'dCH1':>5} {'CH2 g%':>7} {'CH2 ppm':>12} {'CH1 ppm':>12}")
    for e in per_cycle:
        f2, f1 = e.get('ch2_fit_vs_ref'), e.get('ch1_fit_vs_ref')
        print(f"{e['cycle']:>3} {e['start'][11:16]} {e['die_start_C']:5.2f} {e['ch2_change_vs_prev_pct']:5.2f} "
              f"{e['ch1_level_change_vs_prev_pct']:5.2f} "
              + (f"{f2['g_mag_pct']:7.2f} {f2['shift_ppm']:6.1f}±{f2['shift_se']:4.1f} {f1['shift_ppm']:6.1f}±{f1['shift_se']:4.1f}"
                 if f2 else '    ref'))
    print('shift vs die temperature, cycles 21-45:', json.dumps(temp_fit, default=float))
    for name, s in steps.items():
        print(name, json.dumps(s, default=lambda v: round(float(v), 3)))


if __name__ == '__main__':
    main()
