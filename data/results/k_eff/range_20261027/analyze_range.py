#!/usr/bin/env python3
"""Scope-range test of Oct 27 (preregistered in docs/lab_diary_20261027.md section 8) plus the drive-level sessions.

For every XR-/XD- session present: summarize, score the within-session superposition tier with the unchanged
FT-1 tool, then evaluate P1/P2 per path and the recorded-alongside checks (range calibration of H, H and e
against drive level, fundamental size in LSB). Writes range_analysis.json here.

    python3 data/results/k_eff/range_20261027/analyze_range.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
RES = REPO / 'data/results/k_eff'
RANGE_SESSIONS = {ch: {'A5': [f'XR-{ch}-A5-1', f'XR-{ch}-A5-2'], 'A2': [f'XR-{ch}-A2-1', f'XR-{ch}-A2-2']}
                  for ch in ('F2', 'F1')}
DUTY_SESSIONS = {50: 'XD-F2-D05-A5', 200: 'XD-F2-D20-A5'}
LSB_MV = {5000: 5000 / 128, 2000: 2000 / 128}


def ensure_scored(session: str) -> None:
    for args in (['tools/k_eff_ft1_capture.py', '--session', session, '--summarize'],
                 ['tools/k_eff_ft1_superposition.py', '--within', session]):
        subprocess.run([sys.executable, *args], cwd=REPO, check=True, capture_output=True)


def session_result(session: str) -> dict:
    m = json.loads((RES / session / 'manifest.json').read_text())
    glass = [b for b in m['blocks'] if b['state'] == 'GLASS']
    ch = glass[0]['channel']
    sup = json.loads((RES / session / 'derived/superposition_within.json').read_text())['channels'][ch]
    summ = json.loads((RES / session / 'derived/summary.json').read_text())['states'][f'GLASS:{ch}']['per_freq']
    n_trials = sum(b['n_trials'] for b in glass)
    n_clip = sum(b['n_clip'] for b in glass)
    rng = m['acquisition']['range_mV']['A']
    za = np.median([abs(complex(v['H_mean_re'], v['H_mean_im'])) for v in summ.values()])
    out = {'channel': ch, 'range_A_mV': rng, 'duty_permille': glass[0]['duty_permille'],
           'n_glass_trials': n_trials, 'n_clip_or_ovf_trials': n_clip + sum(b['n_overflow'] for b in glass),
           'clip_fraction': n_clip / n_trials, 'H_abs_median': float(za),
           'die_temp': [glass[0]['nco_die_temp_start'], glass[-1]['nco_die_temp_end']]}
    for n in ('2f', '3f'):
        r = sup['result'][n]
        out[n] = {'e_median': r['e_median'], 'e_p90': r['e_p90'], 'e_mag_median': r['e_mag_median'],
                  'e_noise_median': r['e_noise_median'], 'valid_fraction': r['valid_fraction'],
                  'n_valid': r['n_valid'], 'n_eligible': r['n_eligible']}
    out['H'] = {int(f): complex(v['H_mean_re'], v['H_mean_im']) for f, v in summ.items()}
    return out


def zA_fundamental_lsb(session: str, rng_mv: int) -> float:
    """Median fundamental amplitude at Ch A over GLASS trials, in LSB of the session's Ch A range."""
    import csv
    vals = [abs(complex(float(r['zA_re_mV']), float(r['zA_im_mV'])))
            for r in csv.DictReader((RES / session / 'trials.csv').open()) if r['state'] == 'GLASS']
    return float(np.median(vals) / LSB_MV[rng_mv])


def main():
    present = [s for ch in RANGE_SESSIONS for g in RANGE_SESSIONS[ch].values() for s in g] + list(DUTY_SESSIONS.values())
    present = [s for s in present if (RES / s / 'manifest.json').exists()]
    results = {}
    for s in present:
        ensure_scored(s)
        results[s] = session_result(s)
        results[s]['zA_fundamental_median_lsb'] = zA_fundamental_lsb(s, results[s]['range_A_mV'])

    out = {'status': 'exploratory; preregistered in docs/lab_diary_20261027.md section 8 (sha256 f7545135b2f0...)',
           'sessions': {s: {k: v for k, v in r.items() if k != 'H'} for s, r in results.items()}, 'paths': {}}
    for ch, groups in RANGE_SESSIONS.items():
        if not all(s in results for g in groups.values() for s in g):
            continue
        usable = {g: [s for s in ss if results[s]['clip_fraction'] <= 0.05] for g, ss in groups.items()}
        p = {'usable_sessions': usable}
        for n in ('3f', '2f'):
            e = {g: [results[s][n]['e_median'] for s in ss] for g, ss in usable.items()}
            p[n] = {'e_median_by_session': e,
                    'mean_A5': float(np.mean(e['A5'])) if e['A5'] else None,
                    'mean_A2': float(np.mean(e['A2'])) if e['A2'] else None}
            if e['A5'] and e['A2']:
                p[n]['ratio_A2_over_A5'] = p[n]['mean_A2'] / p[n]['mean_A5']
        e3 = p['3f']['e_median_by_session']
        valid = all(results[s][n]['valid_fraction'] >= 0.8 for ss in usable.values() for s in ss for n in ('2f', '3f'))
        if len(e3['A5']) == 2 and len(e3['A2']) == 2 and valid:
            p['P1'] = max(e3['A2']) < min(e3['A5'])
            p['P2'] = p['3f']['ratio_A2_over_A5'] <= 0.75
            p['not_confirmed'] = p['3f']['ratio_A2_over_A5'] >= 0.90
        else:
            p['P1'] = p['P2'] = p['not_confirmed'] = None
            p['note'] = 'a session is missing, over the 5% clip limit, or under 80% valid'
        # range calibration (recorded alongside): H on +-2V over H on +-5V, replicate means
        h5 = {f: np.mean([results[s]['H'][f] for s in groups['A5']]) for f in results[groups['A5'][0]]['H']}
        h2 = {f: np.mean([results[s]['H'][f] for s in groups['A2']]) for f in results[groups['A2'][0]]['H']}
        q = np.array([h2[f] / h5[f] for f in h5 if f in h2])
        p['range_calibration_H2_over_H5'] = {'abs_median': float(np.median(np.abs(q))),
                                             'abs_iqr': [float(np.percentile(np.abs(q), 25)), float(np.percentile(np.abs(q), 75))],
                                             'phase_deg_median': float(np.degrees(np.median(np.angle(q))))}
        out['paths'][ch] = p
    a5 = [s for s in RANGE_SESSIONS['F2']['A5'] if s in results]
    if a5:
        h10 = {f: np.mean([results[s]['H'][f] for s in a5]) for f in results[a5[0]]['H']}
        out['duty'] = {}
        for duty, s in DUTY_SESSIONS.items():
            if s not in results:
                continue
            q = np.array([results[s]['H'][f] / h10[f] for f in h10 if f in results[s]['H']])
            out['duty'][str(duty)] = {'session': s, 'H_over_duty100_abs_median': float(np.median(np.abs(q))),
                                      'H_over_duty100_abs_iqr': [float(np.percentile(np.abs(q), 25)), float(np.percentile(np.abs(q), 75))],
                                      'phase_deg_median': float(np.degrees(np.median(np.angle(q)))),
                                      'complex_change_median': float(np.median(np.abs(q - 1))),
                                      'e_2f': results[s]['2f']['e_median'], 'e_3f': results[s]['3f']['e_median'],
                                      'zA_fundamental_median_lsb': results[s]['zA_fundamental_median_lsb']}
    (OUT / 'range_analysis.json').write_text(json.dumps(out, indent=1) + '\n')
    for s, r in out['sessions'].items():
        print(f"{s:14s} A {r['range_A_mV']:4d} mV duty {r['duty_permille']:3d}: e2f {r['2f']['e_median']:.4f} "
              f"e3f {r['3f']['e_median']:.4f} (noise {r['3f']['e_noise_median']:.4f}) valid {r['2f']['n_valid']}/{r['2f']['n_eligible']}, "
              f"{r['3f']['n_valid']}/{r['3f']['n_eligible']} clip {100 * r['clip_fraction']:.1f}% |zA| {r['zA_fundamental_median_lsb']:.1f} LSB")
    for ch, p in out['paths'].items():
        print(ch, {k: p[k] for k in ('P1', 'P2', 'not_confirmed')}, '3f', p['3f'], '2f', p['2f'])
        print('  range calibration', p['range_calibration_H2_over_H5'])
    for d, v in out.get('duty', {}).items():
        print('duty', d, v)


if __name__ == '__main__':
    main()
