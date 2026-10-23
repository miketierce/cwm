#!/usr/bin/env python3
"""Preregistered FT-1 harmonic-superposition analysis.

Rules: docs/lab_diary_20261023.md section 6, committed in 964204b before any S1 data.
Each GLASS trial's 2f/3f Ch A response is predicted as H(n*f) * zB_n, where H is measured at the
grid point n*f in separate trials. Alias-flagged points are excluded; the score is the complex
normalized RMS error per (f, n) point.

    python tools/k_eff_ft1_superposition.py --within FT1-S1                      # tier (i), per TX
    python tools/k_eff_ft1_superposition.py --train FT1-S1 FT1-S2 --test FT1-S3  # tier (ii), held out

Implementation definitions fixed before the first run: a point is valid when at least one trial
survives every exclusion and H(n*f) exists; the noise-limited error uses the QUIET median demod
magnitudes as noise scales plus the standard error of H.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.k_eff_ft1_capture import GRID_FILE, REF_SNR_MIN, REPO, alias_flags, demod, git_state, pio_actual_freq  # noqa: E402

ORDERS = (2, 3)
F_MAX = 120_000
E_WITHIN = 0.05
E_HELDOUT = 0.10
E_REJECT = 0.20
MIN_VALID_FRACTION = 0.8


def z(r: dict, key: str) -> complex:
    return complex(float(r[f'{key}_re_mV']), float(r[f'{key}_im_mV']))


def clean(r: dict) -> bool:
    return not any(int(r[k]) for k in ('ovf_A', 'ovf_B', 'clip_A', 'clip_B'))


def quiet_noise(manifest: dict, grid: list[int], fs: float) -> tuple[dict, dict]:
    qa, qb = [], []
    for b in manifest['blocks']:
        if b['state'] != 'QUIET':
            continue
        raw = np.load(REPO / b['raw_file'])
        sa = float(raw['mv_per_count_A']) * (256 if raw['A'].dtype == np.int8 else 1)
        sb = float(raw['mv_per_count_B']) * (256 if raw['B'].dtype == np.int8 else 1)
        for xa, xb in zip(raw['A'].astype(float) * sa, raw['B'].astype(float) * sb):
            qa.append([abs(demod(xa, pio_actual_freq(f), fs)) for f in grid])
            qb.append([abs(demod(xb, pio_actual_freq(f), fs)) for f in grid])
    if not qa:
        raise SystemExit('session has no QUIET block')
    return dict(zip(grid, np.median(qa, 0))), dict(zip(grid, np.median(qb, 0)))


def session_inputs(session: str, grid: list[int]) -> dict:
    sdir = REPO / 'data/results/k_eff' / session
    manifest = json.loads((sdir / 'manifest.json').read_text())
    fs = manifest['acquisition']['sample_rate_hz']
    with (sdir / 'trials.csv').open() as fh:
        rows = [r for r in csv.DictReader(fh) if r['state'] == 'GLASS']
    noise_a, noise_b = quiet_noise(manifest, grid, fs)
    return {'session': session, 'fs': fs, 'rows': rows, 'noise_a': noise_a, 'noise_b': noise_b}


def estimate_h(inputs: list[dict], channel: str) -> dict:
    """H(g) = mean of zA/zB over clean trials with a valid fundamental reference; with its standard error."""
    samples: dict[int, list[complex]] = {}
    for inp in inputs:
        for r in inp['rows']:
            if r['channel'] != channel or not clean(r):
                continue
            f = int(r['freq_cmd_hz'])
            zb = z(r, 'zB')
            if abs(zb) >= REF_SNR_MIN * inp['noise_b'][f]:
                samples.setdefault(f, []).append(z(r, 'zA') / zb)
    return {f: (complex(np.mean(v)), float(np.std(v) / np.sqrt(len(v))), len(v)) for f, v in samples.items()}


def score(test: list[dict], channel: str, h: dict, grid: list[int], flags: dict) -> dict:
    gridset = set(grid)
    result = {}
    for n in ORDERS:
        points = []
        for f in grid:
            nf = n * f
            if nf > F_MAX or nf not in gridset:
                continue
            excluded = f in flags[n] or nf in flags[1]
            meas, pred, noise2 = [], [], []
            for inp in test:
                for r in inp['rows']:
                    if r['channel'] != channel or int(r['freq_cmd_hz']) != f or not clean(r):
                        continue
                    zbn = z(r, f'zB{n}')
                    if abs(zbn) < REF_SNR_MIN * inp['noise_b'][nf] or nf not in h:
                        continue
                    hn, se, _ = h[nf]
                    meas.append(z(r, f'zA{n}'))
                    pred.append(hn * zbn)
                    noise2.append(inp['noise_a'][nf] ** 2 + abs(hn) ** 2 * inp['noise_b'][nf] ** 2 + abs(zbn) ** 2 * se ** 2)
            point = {'f_hz': f, 'n': n, 'nf_hz': nf, 'excluded': excluded, 'n_valid': len(meas)}
            if meas:
                m, p = np.array(meas), np.array(pred)
                scale = np.sqrt(np.mean(np.abs(m) ** 2))
                point.update({'e': float(np.sqrt(np.mean(np.abs(m - p) ** 2)) / scale),
                              'e_mag': float(np.sqrt(np.mean((np.abs(m) - np.abs(p)) ** 2)) / scale),
                              'e_noise': float(np.sqrt(np.mean(noise2)) / scale),
                              'mag_bias': float(np.median(np.abs(m) / np.abs(p)) - 1),
                              'phase_bias_deg': float(np.degrees(np.median(np.angle(m / p))))})
            points.append(point)
        eligible = [p for p in points if not p['excluded']]
        valid = [p for p in eligible if 'e' in p]
        flagged = [p for p in points if p['excluded'] and 'e' in p]

        def med(key, ps):
            return float(np.median([p[key] for p in ps])) if ps else None

        result[f'{n}f'] = {
            'n_points_in_range': len(points), 'n_eligible': len(eligible), 'n_valid': len(valid),
            'valid_fraction': len(valid) / len(eligible) if eligible else 0.0,
            'e_median': med('e', valid),
            'e_p90': float(np.percentile([p['e'] for p in valid], 90)) if valid else None,
            'e_mag_median': med('e_mag', valid), 'e_noise_median': med('e_noise', valid),
            'mag_bias_median': med('mag_bias', valid), 'phase_bias_deg_median': med('phase_bias_deg', valid),
            'exploratory_alias_flagged_e_median': med('e', flagged),
            'points': points}
    return result


def tier_check(result: dict, threshold: float) -> dict:
    per = {}
    for key, s in result.items():
        e = s['e_median']
        per[key] = {'meets': e is not None and e <= threshold and s['valid_fraction'] >= MIN_VALID_FRACTION,
                    'exceeds_reject_level': e is not None and e > E_REJECT}
    return {'threshold': threshold, 'all_orders_meet': all(v['meets'] for v in per.values()), 'per_order': per}


def run(train: list[str], test: list[str], tier: str) -> dict:
    grid = json.loads(GRID_FILE.read_text())['freqs_hz']
    cache = {}

    def inputs(names):
        for s in names:
            if s not in cache:
                cache[s] = session_inputs(s, grid)
        return [cache[s] for s in names]

    tr, te = inputs(train), inputs(test)
    flags = alias_flags(grid, te[0]['fs'])
    channels = sorted({r['channel'] for inp in te for r in inp['rows']})
    script = Path(__file__).resolve()
    out = {'tier': tier, 'train_sessions': train, 'test_sessions': test,
           'rules': {'orders': list(ORDERS), 'f_max_hz': F_MAX, 'ref_snr_min': REF_SNR_MIN,
                     'within_threshold': E_WITHIN, 'heldout_threshold': E_HELDOUT,
                     'reject_level': E_REJECT, 'min_valid_fraction': MIN_VALID_FRACTION,
                     'preregistration': 'docs/lab_diary_20261023.md section 6 (commit 964204b)'},
           'alias_flagged_grid_hz': {f'{n}f': v for n, v in flags.items()},
           'quiet_noise_mV': {inp['session']: {'A': inp['noise_a'], 'B': inp['noise_b']} for inp in te},
           'git': git_state(), 'script_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
           'channels': {}}
    threshold = E_WITHIN if tier == 'within' else E_HELDOUT
    for ch in channels:
        res = score(te, ch, estimate_h(tr, ch), grid, flags)
        out['channels'][ch] = {'result': res, 'check': tier_check(res, threshold)}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--within', nargs='+', help='sessions scored against their own H')
    ap.add_argument('--train', nargs='+')
    ap.add_argument('--test', nargs='+')
    a = ap.parse_args()
    jobs = []
    if a.within:
        jobs += [([s], [s], 'within', s) for s in a.within]
    if a.train and a.test:
        jobs.append((a.train, a.test, 'heldout', a.test[0]))
    if not jobs:
        ap.error('give --within, or --train and --test')
    for train, test, tier, home in jobs:
        out = run(train, test, tier)
        path = REPO / 'data/results/k_eff' / home / 'derived' / f'superposition_{tier}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=1) + '\n')
        print(f'{tier} {"+".join(train)} -> {"+".join(test)}: {path.relative_to(REPO)}')
        for ch, d in out['channels'].items():
            for key, s in d['result'].items():
                print(f'  {ch} {key}: valid {s["n_valid"]}/{s["n_eligible"]} eligible '
                      f'(of {s["n_points_in_range"]}), e median {s["e_median"]}, p90 {s["e_p90"]}, '
                      f'e_mag median {s["e_mag_median"]}, noise-limited {s["e_noise_median"]}, '
                      f'meets {d["check"]["per_order"][key]["meets"]}')


if __name__ == '__main__':
    main()
