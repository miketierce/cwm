#!/usr/bin/env python3
"""Handling map of Oct 27 (exploratory): which bench actions move Plate D, measured with bench_sweeps.py.

Every sweep's zoom windows are fitted with the overnight model (overnight_20261026/fit_zoom.py): complex on the
referenced path, magnitude only on the other. The yardstick is the change between consecutive "baseline" sweeps
(nobody at the bench). An action is the first sweep labelled "after: <action>" against the sweep just before it;
a second "after" sweep shows whether the change persisted. Grid changes use the same pairs: median complex change
on the referenced path, median level change on the other. The undisturbed drift series compares every baseline
sweep with the first (grid change, and f0 in the usable windows). The windows whose f0 follows the die temperature
over the baseline form a mode thermometer: each event gets the common plate-temperature step that best explains
their shifts, and the residual it leaves (thermal changes leave almost none). Writes handling_analysis.json.

    python3 data/results/k_eff/handling_20261027/analyze_handling.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
THERMO_R2 = 0.5
_spec = importlib.util.spec_from_file_location('fit_zoom', HERE.parent / 'overnight_20261026' / 'fit_zoom.py')
fz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fz)


def die_c(s: str) -> float:
    return float(s.split(':')[1].split('C')[0])


def load(n: int, mag_only: bool = False):
    """mag_only reads Ch A's level on both paths, for comparisons across a move of Ch B."""
    d = np.load(HERE / f'sweep_{n:03d}.npz')
    ok = (d['ovf'] == 0) & (d['clipA'] == 0) & (d['clipB'] == 0)
    ref = str(d['ref'])
    wins, grid = {}, {}
    for ch in ('F2', 'F1'):
        cplx = ch == ref and not mag_only
        for c in sorted(set(d['center'][ok & (d['kind'] == 'zoom') & (d['ch'] == ch)].tolist())):
            m = ok & (d['kind'] == 'zoom') & (d['ch'] == ch) & (d['center'] == c)
            o = np.argsort(d['f_act'][m])
            v = d['zA'][m] / d['zB'][m] if cplx else np.abs(d['zA'][m])
            wins[f'{ch}:{c}'] = (d['f_act'][m][o], v[o])
        m = ok & (d['kind'] == 'grid') & (d['ch'] == ch)
        vals = {}
        for f, za, zb in zip(d['f_cmd'][m], d['zA'][m], d['zB'][m]):
            vals.setdefault(int(f), []).append(za / zb if cplx else abs(za))
        grid[ch] = {f: np.mean(v) for f, v in vals.items()}
    return ref, wins, grid


def grid_change(a: dict, b: dict, ref: str) -> dict:
    out = {}
    for ch in ('F2', 'F1'):
        fs = [f for f in a[ch] if f in b[ch]]
        x = np.array([b[ch][f] / a[ch][f] for f in fs])
        out[ch] = float(100 * np.median(np.abs(x - 1)))
    return out


def main():
    log = [json.loads(line) for line in (HERE / 'log.jsonl').read_text().splitlines()]
    sweeps = [r for r in log if r['event'] == 'sweep']
    data, fits = {}, {}
    for r in sweeps:
        n = r['sweep']
        ref, wins, grid = load(n)
        data[n] = {'ref': ref, 'grid': grid, 'label': r['label'], 'start': r['start'], 'die': die_c(r['temp_start'])}
        for key, (f, v) in wins.items():
            kind = ('lin' if len(f) >= 10 else 'const') if key.startswith(ref) else 'mag'
            fits.setdefault(key, {})[n] = fz.fit(f, v, int(key.split(':')[1]), kind)
    order = [r['sweep'] for r in sweeps]
    base = [n for n in order if data[n]['label'] == 'baseline']
    pairs = [(a, b) for a, b in zip(order, order[1:]) if a in base and b in base and data[a]['ref'] == data[b]['ref']]

    quality, yard = {}, {}
    for key, per in fits.items():
        q = {'median_rel_rms': float(np.median([x['rel_rms'] for x in per.values()])),
             'median_se_f0_hz': float(np.median([x['se_f0'] for x in per.values()])),
             'median_se_Q_pct': float(100 * np.median([x['se_lnQ'] for x in per.values()])),
             'f0_in_window_all': all(x['in_window'] for x in per.values())}
        q['f0_usable'] = q['f0_in_window_all'] and q['median_se_f0_hz'] <= fz.MAX_SE_F0_HZ and q['median_rel_rms'] <= fz.MAX_REL_RMS
        q['Q_usable'] = q['f0_usable'] and q['median_se_Q_pct'] <= 100 * fz.MAX_SE_LNQ
        quality[key] = q
        steps = [fz.change(per[a], per[b]) for a, b in pairs if a in per and b in per]
        if steps:
            yard[key] = {k: {'median': float(np.median([abs(s[k]) for s in steps])),
                             'p95': float(np.percentile([abs(s[k]) for s in steps], 95))}
                         for k in ('df0_ppm', 'df0_linewidths', 'dQ_pct')}
    gsteps = [grid_change(data[a]['grid'], data[b]['grid'], data[a]['ref']) for a, b in pairs]
    yard_grid = {ch: {'median': float(np.median([g[ch] for g in gsteps])), 'p95': float(np.percentile([g[ch] for g in gsteps], 95))}
                 for ch in ('F2', 'F1')} if gsteps else {}

    # undisturbed drift: every baseline sweep against the first one on the same reference
    drift = {}
    if base:
        series = [n for n in base if data[n]['ref'] == data[base[0]]['ref']]
        gd = [grid_change(data[base[0]]['grid'], data[n]['grid'], data[n]['ref']) for n in series]
        drift = {'from_sweep': base[0], 'sweeps': series, 'start': [data[n]['start'] for n in series],
                 'die': [data[n]['die'] for n in series],
                 'grid_change_pct': {ch: [g[ch] for g in gd] for ch in ('F2', 'F1')},
                 'f0_ppm': {key: [1e6 * (per[n]['f0'] / per[base[0]]['f0'] - 1) for n in series]
                            for key, per in fits.items() if quality[key]['f0_usable'] and all(n in per for n in series)}}

    # mode thermometer: each window's f0 against die temperature over the baseline; the windows that follow it
    # (R² >= THERMO_R2) give every event a common plate-temperature step and the residual temperature leaves
    tcf = {}
    if drift:
        x = np.array(drift['die'])
        for key, v in drift['f0_ppm'].items():
            v = np.array(v)
            p = np.polyfit(x, v, 1)
            tcf[key] = {'ppm_per_c': float(p[0]), 'r2': float(1 - np.sum((v - np.polyval(p, x)) ** 2) / np.sum((v - v.mean()) ** 2))}
    thermo = sorted(k for k, v in tcf.items() if v['r2'] >= THERMO_R2)

    def mag_fits(ns):
        loaded = {m: load(m, mag_only=True) for m in ns}
        return ({m: loaded[m][2] for m in ns},
                {key: {m: fz.fit(*loaded[m][1][key], int(key.split(':')[1]), 'mag') for m in ns if key in loaded[m][1]} for key in fits})

    yard_mag = {}
    events = {}
    for i, n in enumerate(order):
        lab = data[n]['label']
        if not lab.startswith('after:') or (i and data[order[i - 1]]['label'] == lab):
            continue
        before = order[i - 1]
        later = [m for m in order[i + 1:] if data[m]['label'] == lab]
        moved = data[before]['ref'] != data[n]['ref']
        if moved:
            # Ch B moved between the sweeps: compare Ch A's level on both paths, every window refitted as magnitude,
            # against a magnitude-only yardstick from the last 50 baseline pairs
            if not yard_mag:
                ps = pairs[-50:]
                g, f = mag_fits(sorted({m for p in ps for m in p}))
                gs = [grid_change(g[a], g[b], 'F2') for a, b in ps]
                yard_mag = {'n_pairs': len(ps),
                            'grid_change_pct': {ch: {'median': float(np.median([x[ch] for x in gs])),
                                                     'p95': float(np.percentile([x[ch] for x in gs], 95))} for ch in ('F2', 'F1')},
                            'df0_ppm_median': {key: float(np.median([abs(fz.change(per[a], per[b])['df0_ppm']) for a, b in ps]))
                                               for key, per in f.items()}}
            grids, efits = mag_fits([before, n] + later)
            ystick = yard_mag['df0_ppm_median']
        else:
            grids, efits = {m: data[m]['grid'] for m in [before, n] + later}, fits
            ystick = {key: v['df0_ppm']['median'] for key, v in yard.items()}
        ev = {'before_sweep': before, 'after_sweeps': [n] + later, 'ref_changed': moved,
              'comparison': 'Ch A level on both paths' if moved else 'complex H on the referenced path, Ch A level on the other',
              'die_change_c': data[n]['die'] - data[before]['die'],
              'grid_change_pct': grid_change(grids[before], grids[n], data[n]['ref']),
              'grid_change_pct_last_after': grid_change(grids[before], grids[later[-1]], data[n]['ref']) if later else None,
              'modes': {}}
        for key, per in efits.items():
            if not quality[key]['f0_usable'] or before not in per or n not in per:
                continue
            c = fz.change(per[before], per[n])
            if not quality[key]['Q_usable']:
                c['dQ_pct'] = None
            c['x_yardstick_df0'] = abs(c['df0_ppm']) / ystick[key] if key in ystick else None
            ev['modes'][key] = c
        ev['thermal_fit'] = []
        for m in [n] + later:
            ks = [k for k in thermo if before in efits[k] and m in efits[k]]
            obs = np.array([fz.change(efits[k][before], efits[k][m])['df0_ppm'] for k in ks])
            c = np.array([tcf[k]['ppm_per_c'] for k in ks])
            step = float(np.sum(c * obs) / np.sum(c * c))
            ev['thermal_fit'].append({'sweep': m, 'plate_step_c': step, 'obs_rms_ppm': float(np.sqrt(np.mean(obs ** 2))),
                                      'resid_rms_ppm': float(np.sqrt(np.mean((obs - c * step) ** 2)))})
        x = [m['x_yardstick_df0'] for m in ev['modes'].values() if m['x_yardstick_df0'] is not None]
        ev['median_abs_df0_ppm'] = float(np.median([abs(m['df0_ppm']) for m in ev['modes'].values()])) if ev['modes'] else None
        ev['median_x_yardstick'] = float(np.median(x)) if x else None
        events[lab[len('after:'):].strip()] = ev

    out = {'status': 'exploratory', 'sweeps': {n: {k: data[n][k] for k in ('label', 'start', 'die', 'ref')} for n in order},
           'quality': quality, 'yardstick_baseline_pairs': {'n_pairs': len(pairs), 'modes': yard, 'grid_change_pct': yard_grid,
                                                             'mag_only': yard_mag or None},
           'baseline_drift_from_first': drift, 'mode_thermometer': {'r2_min': THERMO_R2, 'windows': thermo, 'tcf_ppm_per_c': tcf},
           'events': events}
    (HERE / 'handling_analysis.json').write_text(json.dumps(out, indent=1) + '\n')
    print(f'{len(order)} sweeps, {len(pairs)} baseline pairs; grid yardstick (median / p95 %):',
          {ch: (round(v['median'], 2), round(v['p95'], 2)) for ch, v in yard_grid.items()})
    for key in sorted(yard):
        q = quality[key]
        print(f"  {key:9s} f0 usable {q['f0_usable']!s:5s} Q usable {q['Q_usable']!s:5s} rel_rms {q['median_rel_rms']:.3f} "
              f"se_f0 {q['median_se_f0_hz']:5.1f} Hz | yardstick |df0| {yard[key]['df0_ppm']['median']:5.1f} ppm "
              f"(p95 {yard[key]['df0_ppm']['p95']:5.1f}), |dQ| {yard[key]['dQ_pct']['median']:.2f}%")
    if drift:
        print(f"drift from sweep {drift['from_sweep']} over {len(drift['sweeps'])} baseline sweeps: largest grid change",
              {ch: round(max(v), 2) for ch, v in drift['grid_change_pct'].items()}, '%; f0 range (ppm)',
              {key: (round(min(v), 1), round(max(v), 1)) for key, v in sorted(drift['f0_ppm'].items())})
    print('mode thermometer:', {k: round(tcf[k]['ppm_per_c'], 1) for k in thermo}, 'ppm per C')
    for name, ev in events.items():
        print(f"{name}: sweeps {ev['before_sweep']} -> {ev['after_sweeps']}, grid "
              f"{ {ch: round(v, 2) for ch, v in ev['grid_change_pct'].items()} }, median |df0| {ev['median_abs_df0_ppm']:.1f} ppm "
              f"({ev['median_x_yardstick']:.1f}x yardstick)")
        for s in ev['thermal_fit']:
            print(f"    sweep {s['sweep']}: plate step {s['plate_step_c']:+.3f} C, residual {s['resid_rms_ppm']:.1f} of {s['obs_rms_ppm']:.1f} ppm rms")


if __name__ == '__main__':
    main()
