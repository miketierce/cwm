#!/usr/bin/env python3
"""Mode fits to the overnight zoom sweeps (O4; exploratory, not preregistered).

Every cycle swept the distinct NCO frequencies within +-400 Hz of the 6 strongest S2 peaks per path,
once each. Per window and cycle this fits one resonance plus background:

    CH2 (complex H = zA/zB):  H(f) = a / (f0 - f + i*g) + b [+ c*(f - fc)]   (linear term with >= 10 points)
    CH1 (|zA| only):          |zA(f)| = |a / (f0 - f + i*g) + b|,  a real

with g = f0 / (2Q) the half width. CH1 has no drive reference in the start wiring, so only its magnitude
is fitted. The magnitude fixes f0 and Q but not the resonance amplitude: two (a, b) pairs give the same
|zA(f)|, so CH1 reports no peak height. Shifts are reported in ppm and in linewidths (f0/Q) against cycle 21, the undisturbed
reference, and across the bench events of the evening. The yardstick for each window is its median
change between consecutive undisturbed cycles (21-45).

    python3 data/results/k_eff/overnight_20261026/fit_zoom.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent

REF_CYCLE = 21
UNDISTURBED = range(21, 46)
EVENTS = {'16:41 TX2 lead restore': (2, 3), '17:53-18:13 60 kHz step': (6, 7),
          '19:32 step': (10, 11), '22:32 step': (19, 20)}
MAX_SE_F0_HZ = 20.0       # median over cycles; above this the window's f0 is not used
MAX_REL_RMS = 0.10        # median residual RMS / peak; above this the one-mode model is inadequate
MAX_SE_LNQ = 0.15         # median relative se of Q; above this the window's Q is not used


def windows(d) -> dict:
    """(ch, center) -> (f_act, value) sorted by frequency; CH2 complex zA/zB, CH1 |zA| in mV."""
    ok = (d['kind'] == 'zoom') & (d['ovf'] == 0) & (d['clipA'] == 0) & (d['clipB'] == 0)
    out = {}
    for ch in ('F2', 'F1'):
        for c in sorted(set(d['center'][ok & (d['ch'] == ch)].tolist())):
            m = ok & (d['ch'] == ch) & (d['center'] == c)
            o = np.argsort(d['f_act'][m])
            v = d['zA'][m] / d['zB'][m] if ch == 'F2' else np.abs(d['zA'][m])
            out[f'{ch}:{c}'] = (d['f_act'][m][o], v[o])
    return out


def model(p, f, fc, kind):
    f0, g = fc + p[0], np.exp(p[1])
    if kind == 'mag':
        return np.abs(p[2] / (f0 - f + 1j * g) + p[3] + 1j * p[4])
    h = (p[2] + 1j * p[3]) / (f0 - f + 1j * g) + p[4] + 1j * p[5]
    return h + (p[6] + 1j * p[7]) * (f - fc) if kind == 'lin' else h


def resid(p, f, v, fc, kind):
    r = model(p, f, fc, kind) - v
    return r if kind == 'mag' else np.concatenate([r.real, r.imag])


def starts(f, v, fc, kind):
    """Starting points over a range of widths and, for |zA|, background phases."""
    k = int(np.argmax(np.abs(v)))
    edge = (v[0] + v[-1]) / 2
    for g0 in (30.0, 80.0, 200.0, 500.0):
        if kind == 'mag':
            for ph in (0, np.pi / 2, np.pi, -np.pi / 2):
                b = abs(edge) / 2 * np.exp(1j * ph)
                yield np.array([f[k] - fc, np.log(g0), max(abs(v[k]) - abs(edge) / 2, 1e-6) * g0, b.real, b.imag])
        else:
            a = (v[k] - edge) * 1j * g0
            p = [f[k] - fc, np.log(g0), a.real, a.imag, edge.real, edge.imag]
            yield np.array(p + [0.0, 0.0] if kind == 'lin' else p)


def fit(f, v, fc: int, kind: str) -> dict:
    best = None
    for p0 in starts(f, v, fc, kind):
        try:
            r = least_squares(resid, p0, args=(f, v, fc, kind), method='lm', x_scale='jac', max_nfev=5000)
        except (ValueError, np.linalg.LinAlgError):
            continue
        if best is None or r.cost < best.cost:
            best = r
    n, p = best.fun.size, best.x.size
    cov = np.linalg.pinv(best.jac.T @ best.jac) * 2 * best.cost / (n - p)
    f0, g = fc + best.x[0], float(np.exp(best.x[1]))
    return {'f0': float(f0), 'se_f0': float(np.sqrt(cov[0, 0])), 'Q': float(f0 / (2 * g)),
            'se_lnQ': float(np.sqrt(cov[1, 1])),
            'peak': None if kind == 'mag' else float(abs(complex(best.x[2], best.x[3])) / g),
            'rel_rms': float(np.sqrt(np.mean(np.abs(model(best.x, f, fc, kind) - v) ** 2)) / np.max(np.abs(v))),
            'in_window': bool(f[0] <= f0 <= f[-1]), 'n_points': int(len(f)), 'model': kind}


def die_c(s: str) -> float:
    return float(s.split(':')[1].split('C')[0])


def change(a: dict, b: dict) -> dict:
    """b relative to a: frequency in ppm and in linewidths (of a), Q and peak height in percent."""
    ppm = 1e6 * (b['f0'] / a['f0'] - 1)
    return {'df0_ppm': ppm, 'df0_linewidths': ppm * 1e-6 * a['Q'], 'dQ_pct': 100 * (b['Q'] / a['Q'] - 1),
            'dpeak_pct': None if a['peak'] is None else 100 * (b['peak'] / a['peak'] - 1)}


def ols(x, y) -> dict:
    x, y = np.asarray(x, float), np.asarray(y, float)
    X = np.column_stack([np.ones_like(x), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ beta
    cov = np.linalg.inv(X.T @ X) * np.sum(r ** 2) / (len(y) - 2)
    return {'slope': float(beta[1]), 'se': float(np.sqrt(cov[1, 1])), 'r': float(np.corrcoef(x, y)[0, 1])}


def main():
    log = [json.loads(line) for line in (HERE / 'log.jsonl').read_text().splitlines()]
    cycles = {r['cycle']: r for r in log if r['event'] == 'cycle'}
    fits: dict[str, dict[int, dict]] = {}
    for n in cycles:
        for key, (f, v) in windows(np.load(HERE / f'cycle_{n:03d}.npz')).items():
            kind = 'mag' if key.startswith('F1') else ('lin' if len(f) >= 10 else 'const')
            fits.setdefault(key, {})[n] = fit(f, v, int(key.split(':')[1]), kind)
    die = {n: die_c(r['temp_start']) for n, r in cycles.items()}

    quality, usable_f0, usable_q = {}, [], []
    for key, per in fits.items():
        quiet = [n for n in UNDISTURBED if n in per and n - 1 in per and n - 1 in UNDISTURBED]
        steps = [change(per[n - 1], per[n]) for n in quiet]
        q = {'median_rel_rms': float(np.median([x['rel_rms'] for x in per.values()])),
             'median_se_f0_hz': float(np.median([x['se_f0'] for x in per.values()])),
             'median_se_Q_pct': float(100 * np.median([x['se_lnQ'] for x in per.values()])),
             'f0_in_window_all_cycles': all(x['in_window'] for x in per.values()),
             'ref_f0_hz': per[REF_CYCLE]['f0'], 'ref_Q': per[REF_CYCLE]['Q'],
             'ref_linewidth_hz': per[REF_CYCLE]['f0'] / per[REF_CYCLE]['Q'],
             'undisturbed_20min': {k: float(np.median([abs(s[k]) for s in steps]))
                                   for k in ('df0_ppm', 'df0_linewidths', 'dQ_pct')}}
        q['f0_usable'] = (q['f0_in_window_all_cycles'] and q['median_se_f0_hz'] <= MAX_SE_F0_HZ
                          and q['median_rel_rms'] <= MAX_REL_RMS)
        q['Q_usable'] = q['f0_usable'] and q['median_se_Q_pct'] <= 100 * MAX_SE_LNQ
        quality[key] = q
        if q['f0_usable']:
            usable_f0.append(key)
        if q['Q_usable']:
            usable_q.append(key)

    events = {}
    for name, (a, b) in EVENTS.items():
        per_win = {k: change(fits[k][a], fits[k][b]) for k in usable_f0}
        for k, c in per_win.items():
            y = quality[k]['undisturbed_20min']
            c['df0_vs_undisturbed'] = abs(c['df0_ppm']) / y['df0_ppm']
            c['dQ_vs_undisturbed'] = abs(c['dQ_pct']) / y['dQ_pct'] if k in usable_q else None
        events[name] = {'cycles': [a, b], 'per_window': per_win,
                        'median_abs_df0_ppm': float(np.median([abs(c['df0_ppm']) for c in per_win.values()])),
                        'median_abs_df0_linewidths': float(np.median([abs(c['df0_linewidths']) for c in per_win.values()])),
                        'median_abs_dQ_pct': float(np.median([abs(per_win[k]['dQ_pct']) for k in usable_q]))}

    night = [n for n in UNDISTURBED if n != REF_CYCLE]
    drift = {}
    y = np.array([[change(fits[k][REF_CYCLE], fits[k][n])['df0_ppm'] for n in night] for k in usable_f0])
    w = 1 / np.array([quality[k]['undisturbed_20min']['df0_ppm'] for k in usable_f0]) ** 2
    common = (w[:, None] * y).sum(0) / w.sum()
    spec = y - common
    for i, k in enumerate(usable_f0):
        ch = [change(fits[k][REF_CYCLE], fits[k][n]) for n in night]
        drift[k] = {'max_abs_df0_ppm': float(np.max(np.abs(y[i]))),
                    'max_abs_df0_linewidths': float(np.max([abs(c['df0_linewidths']) for c in ch])),
                    'dQ_pct_range': [float(min(c['dQ_pct'] for c in ch)), float(max(c['dQ_pct'] for c in ch))]
                    if k in usable_q else None,
                    'df0_ppm_per_C_die': ols([die[n] for n in night] + [die[REF_CYCLE]], list(y[i]) + [0.0]),
                    'dQ_pct_per_C_die': ols([die[n] for n in night] + [die[REF_CYCLE]], [c['dQ_pct'] for c in ch] + [0.0])
                    if k in usable_q else None,
                    'mode_specific_rms_ppm': float(np.sqrt(np.mean(spec[i] ** 2)))}
    common_fit = {'per_cycle_ppm': {n: float(c) for n, c in zip(night, common)},
                  'ppm_per_C_die': ols([die[n] for n in night] + [die[REF_CYCLE]], list(common) + [0.0]),
                  'weighted_variance_fraction': float(1 - np.sum(w[:, None] * spec ** 2) / np.sum(w[:, None] * y ** 2))}

    out = {'status': 'exploratory, not preregistered', 'reference_cycle': REF_CYCLE,
           'model': 'one resonance a/(f0 - f + i f0/2Q) + background; CH2 complex zA/zB, CH1 |zA|',
           'selection': {'max_median_se_f0_hz': MAX_SE_F0_HZ, 'max_median_rel_rms': MAX_REL_RMS,
                         'max_median_se_Q': MAX_SE_LNQ, 'f0_usable': usable_f0, 'Q_usable': usable_q},
           'die_temperature_C': die, 'quality': quality, 'events': events,
           'night_vs_ref': {'per_window': drift, 'common_shift': common_fit},
           'fits': {k: {str(n): v for n, v in per.items()} for k, per in fits.items()}}
    (HERE / 'zoom_fits.json').write_text(json.dumps(out, indent=1))

    print(f"{'window':>9} {'f0 (c21)':>10} {'Q':>5} {'lw Hz':>6} {'se f0':>6} {'rel':>5} {'20min ppm':>9} {'20min Q%':>8}  use")
    for k, q in quality.items():
        u = q['undisturbed_20min']
        print(f"{k:>9} {q['ref_f0_hz']:10.1f} {q['ref_Q']:5.0f} {q['ref_linewidth_hz']:6.0f} {q['median_se_f0_hz']:6.1f} "
              f"{100 * q['median_rel_rms']:4.1f}% {u['df0_ppm']:9.1f} {u['dQ_pct']:8.2f}  "
              f"{'f0' if q['f0_usable'] else '--'}{'+Q' if q['Q_usable'] else ''}")
    for name, e in events.items():
        print(f"\n{name} (cycles {e['cycles'][0]}->{e['cycles'][1]}): median |df0| {e['median_abs_df0_ppm']:.0f} ppm "
              f"= {e['median_abs_df0_linewidths']:.3f} linewidths, median |dQ| {e['median_abs_dQ_pct']:.1f}%")
        for k, c in e['per_window'].items():
            dq = f"{c['dQ_pct']:+6.1f}% (x{c['dQ_vs_undisturbed']:.1f})" if c['dQ_vs_undisturbed'] is not None else '      --'
            dp = f"  dpeak {c['dpeak_pct']:+5.1f}%" if c['dpeak_pct'] is not None else ''
            print(f"  {k:>9} df0 {c['df0_ppm']:+7.0f} ppm (x{c['df0_vs_undisturbed']:4.1f}) "
                  f"{c['df0_linewidths']:+.3f} lw  dQ {dq}{dp}")
    print('\nnight vs cycle 21 (cycles 22-45):')
    for k, d in drift.items():
        t = d['df0_ppm_per_C_die']
        qr = f"dQ {d['dQ_pct_range'][0]:+.1f}..{d['dQ_pct_range'][1]:+.1f}%" if d['dQ_pct_range'] else ''
        print(f"  {k:>9} max |df0| {d['max_abs_df0_ppm']:5.0f} ppm = {d['max_abs_df0_linewidths']:.3f} lw  "
              f"{t['slope']:+6.0f}±{t['se']:3.0f} ppm/C(die) r={t['r']:+.2f}  mode-specific rms "
              f"{d['mode_specific_rms_ppm']:4.0f} ppm  {qr}")
    c = common_fit
    print(f"  common shift {c['ppm_per_C_die']['slope']:+.0f}±{c['ppm_per_C_die']['se']:.0f} ppm/C(die), "
          f"range {min(common):+.0f}..{max(common):+.0f} ppm, weighted variance fraction {c['weighted_variance_fraction']:.2f}")


if __name__ == '__main__':
    main()
