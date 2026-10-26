#!/usr/bin/env python3
"""Exploratory drift decomposition for FT-1 GLASS blocks, within a block or between sessions.

Within a block, for each grid frequency, fits ln H(t) = a + D*t over its time-stamped repeats (D complex,
per minute). Between sessions (O2), D = ln(H_other / H_ref) from the per-session mean H at each frequency.
Two models are then fitted across frequencies:

    gain-only:        D(f) = g
    gain + shift:     D(f) = g + c * P(f),   P(f) = f * d ln H / df

A common fractional shift s of all mode frequencies gives c = -s (per minute within a block), the same on
every TX path; a gain change gives the constant g. Not preregistered; reported as exploratory.

    python tools/k_eff_ft1_drift.py --session FT1-S1
    python tools/k_eff_ft1_drift.py --session FT1-S2 --compare FT1-S1
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.k_eff_ft1_capture import GRID_FILE, REPO, alias_flags  # noqa: E402

STEP_HZ = 500
MIN_RX_SNR = 30.0
MAX_NEIGHBOR_PHASE_RAD = 2.0


def per_frequency_drift(rows: list[dict]) -> dict:
    """Complex ln H slope per minute and its standard error, per grid frequency."""
    by_f: dict[int, list[tuple[float, complex]]] = {}
    for r in rows:
        if any(int(r[k]) for k in ('ovf_A', 'ovf_B', 'clip_A', 'clip_B')):
            continue
        za = complex(float(r['zA_re_mV']), float(r['zA_im_mV']))
        zb = complex(float(r['zB_re_mV']), float(r['zB_im_mV']))
        by_f.setdefault(int(r['freq_cmd_hz']), []).append((float(r['t_unix']), za / zb))
    t0 = min(t for v in by_f.values() for t, _ in v)
    out = {}
    for f, v in by_f.items():
        t = np.array([x[0] for x in v]) - t0
        h = np.array([x[1] for x in v])
        hm = h.mean()
        lh = np.log(np.abs(h)) + 1j * np.angle(h / hm)
        tm = t / 60.0
        X = np.vstack([np.ones_like(tm), tm]).T
        coef_re, res_re, *_ = np.linalg.lstsq(X, lh.real, rcond=None)
        coef_im, res_im, *_ = np.linalg.lstsq(X, lh.imag, rcond=None)
        dof = max(len(tm) - 2, 1)
        sxx = np.sum((tm - tm.mean()) ** 2)
        se_re = np.sqrt((res_re[0] if len(res_re) else 0.0) / dof / sxx)
        se_im = np.sqrt((res_im[0] if len(res_im) else 0.0) / dof / sxx)
        out[f] = {'H': hm, 'D': complex(coef_re[1], coef_im[1]), 'se': (se_re, se_im), 'n': len(h)}
    return out


def session_means(rows: list[dict]) -> dict:
    """Mean H per grid frequency, with standard errors of ln|H| and of the phase."""
    by_f: dict[int, list[complex]] = {}
    for r in rows:
        if any(int(r[k]) for k in ('ovf_A', 'ovf_B', 'clip_A', 'clip_B')):
            continue
        za = complex(float(r['zA_re_mV']), float(r['zA_im_mV']))
        zb = complex(float(r['zB_re_mV']), float(r['zB_im_mV']))
        by_f.setdefault(int(r['freq_cmd_hz']), []).append(za / zb)
    out = {}
    for f, v in by_f.items():
        h = np.array(v)
        hm = h.mean()
        n = len(h)
        se = (np.std(np.log(np.abs(h)), ddof=1) / np.sqrt(n), np.std(np.angle(h / hm), ddof=1) / np.sqrt(n))
        out[f] = {'H': hm, 'se': se, 'n': n}
    return out


def between_session_points(a: dict, b: dict, freqs: list[int]) -> list[dict]:
    """Fit points for D = ln(H_b / H_a); P(f) is the mean of the two sessions' local log-slopes."""
    points = []
    for f in freqs:
        lo, hi = f - STEP_HZ, f + STEP_HZ
        if any(x not in s for s in (a, b) for x in (lo, f, hi)):
            continue
        dphase = [np.angle(s[hi]['H'] / s[lo]['H']) for s in (a, b)]
        if max(abs(p) for p in dphase) > MAX_NEIGHBOR_PHASE_RAD:
            continue
        dln = np.mean([np.log(abs(s[hi]['H']) / abs(s[lo]['H'])) + 1j * p for s, p in zip((a, b), dphase)])
        ratio = b[f]['H'] / a[f]['H']
        points.append({'f': f, 'D': complex(np.log(abs(ratio)), np.angle(ratio)),
                       'se': (float(np.hypot(a[f]['se'][0], b[f]['se'][0])), float(np.hypot(a[f]['se'][1], b[f]['se'][1]))),
                       'P': f * dln / (2 * STEP_HZ)})
    return points


def fit_models(points: list[dict], per: str = '_per_min') -> dict:
    d = np.array([p['D'] for p in points])
    pr = np.array([p['P'] for p in points])
    w_re = 1 / np.array([p['se'][0] for p in points]) ** 2
    w_im = 1 / np.array([p['se'][1] for p in points]) ** 2
    y = np.concatenate([d.real, d.imag])
    w = np.concatenate([w_re, w_im])
    n = len(points)
    one, zero = np.ones(n), np.zeros(n)
    xa = np.vstack([np.concatenate([one, zero]), np.concatenate([zero, one])]).T
    xb = np.column_stack([xa, np.concatenate([pr.real, pr.imag])])

    def wls(x):
        sw = np.sqrt(w)
        beta, *_ = np.linalg.lstsq(x * sw[:, None], y * sw, rcond=None)
        resid = y - x @ beta
        chi2 = float(np.sum(w * resid ** 2))
        cov = np.linalg.inv((x * w[:, None]).T @ x) * chi2 / max(len(y) - x.shape[1], 1)
        return beta, np.sqrt(np.diag(cov)), chi2

    ba, sa, ca = wls(xa)
    bb, sb, cb = wls(xb)
    chi0 = float(np.sum(w * (y - np.average(y, weights=w)) ** 2))
    return {
        'n_points': n,
        'gain_only': {f'g_mag_pct{per}': 100 * ba[0], f'g_phase_deg{per}': float(np.degrees(ba[1])), 'chi2': ca},
        'gain_plus_shift': {f'g_mag_pct{per}': 100 * bb[0], 'g_mag_se': 100 * sb[0],
                            f'g_phase_deg{per}': float(np.degrees(bb[1])), 'g_phase_se': float(np.degrees(sb[1])),
                            f'freq_drift_ppm{per}': -1e6 * bb[2], 'freq_drift_se': 1e6 * sb[2], 'chi2': cb},
        'chi2_reduction_by_shift_term': 1 - cb / ca,
        'weighted_variance_explained_gain_only': 1 - ca / chi0,
        'weighted_variance_explained_gain_plus_shift': 1 - cb / chi0,
    }


def analyze(session: str) -> dict:
    sdir = REPO / 'data/results/k_eff' / session
    manifest = json.loads((sdir / 'manifest.json').read_text())
    grid = json.loads(GRID_FILE.read_text())['freqs_hz']
    summary = json.loads((sdir / 'derived' / 'summary.json').read_text())
    flagged = set(alias_flags(grid, manifest['acquisition']['sample_rate_hz'])[1])
    with (sdir / 'trials.csv').open() as fh:
        rows = [r for r in csv.DictReader(fh) if r['state'] == 'GLASS']
    out = {'session': session, 'status': 'exploratory, not preregistered',
           'selection': {'min_rx_snr': MIN_RX_SNR, 'max_neighbor_phase_step_rad': MAX_NEIGHBOR_PHASE_RAD,
                         'excluded': 'alias-flagged (order 1) and grid edges'},
           'channels': {}}
    for ch in sorted({r['channel'] for r in rows}):
        pf = summary['states'][f'GLASS:{ch}']['per_freq']
        drift = per_frequency_drift([r for r in rows if r['channel'] == ch])
        points = []
        for f in grid:
            lo, hi = f - STEP_HZ, f + STEP_HZ
            if f in flagged or lo not in drift or hi not in drift or f not in drift:
                continue
            if pf[str(f)]['rx_snr_median'] < MIN_RX_SNR:
                continue
            dphase = np.angle(drift[hi]['H'] / drift[lo]['H'])
            if abs(dphase) > MAX_NEIGHBOR_PHASE_RAD:
                continue
            dln = np.log(abs(drift[hi]['H']) / abs(drift[lo]['H'])) + 1j * dphase
            points.append({'f': f, 'D': drift[f]['D'], 'se': drift[f]['se'], 'P': f * dln / (2 * STEP_HZ)})
        res = fit_models(points)
        slope = np.array([p['P'].real for p in points])
        dmag = np.array([p['D'].real for p in points])
        res['corr_mag_drift_vs_log_slope'] = float(np.corrcoef(slope, dmag)[0, 1])
        out['channels'][ch] = res
    return out


def compare(ref: str, other: str) -> dict:
    """Between-session decomposition (O2) of ln(H_other / H_ref), per GLASS channel."""
    grid = json.loads(GRID_FILE.read_text())['freqs_hz']
    sessions = {}
    for s in (ref, other):
        sdir = REPO / 'data/results/k_eff' / s
        manifest = json.loads((sdir / 'manifest.json').read_text())
        summary = json.loads((sdir / 'derived' / 'summary.json').read_text())
        with (sdir / 'trials.csv').open() as fh:
            rows = [r for r in csv.DictReader(fh) if r['state'] == 'GLASS']
        temps = [b['ambient_temp_c'] for b in manifest['blocks'] if b['state'] == 'GLASS']
        sessions[s] = {'manifest': manifest, 'summary': summary, 'rows': rows, 'glass_air_temp_c': temps}
    flagged = set(alias_flags(grid, sessions[ref]['manifest']['acquisition']['sample_rate_hz'])[1])
    out = {'reference': ref, 'session': other, 'status': 'exploratory, not preregistered',
           'model': 'ln(H_other / H_ref) = g + c * P(f); freq_drift_ppm = -1e6 * c',
           'selection': {'min_rx_snr_both_sessions': MIN_RX_SNR, 'max_neighbor_phase_step_rad': MAX_NEIGHBOR_PHASE_RAD,
                         'excluded': 'alias-flagged (order 1) and grid edges'},
           'glass_air_temp_c': {s: sessions[s]['glass_air_temp_c'] for s in (ref, other)},
           'channels': {}}
    for ch in sorted({r['channel'] for r in sessions[ref]['rows']} & {r['channel'] for r in sessions[other]['rows']}):
        pfs = [sessions[s]['summary']['states'][f'GLASS:{ch}']['per_freq'] for s in (ref, other)]
        freqs = [f for f in grid if f not in flagged and min(pf[str(f)]['rx_snr_median'] for pf in pfs) >= MIN_RX_SNR]
        means = [session_means([r for r in sessions[s]['rows'] if r['channel'] == ch]) for s in (ref, other)]
        points = between_session_points(*means, freqs)
        res = fit_models(points, per='')
        g = res['gain_plus_shift']
        d = np.array([q['D'] for q in points])
        p = np.array([q['P'] for q in points])
        resid = d - (g['g_mag_pct'] / 100 + 1j * np.radians(g['g_phase_deg']) - 1e-6 * g['freq_drift_ppm'] * p)
        res['median_abs_change_pct'] = float(100 * np.median(np.abs(np.exp(d) - 1)))
        res['median_abs_residual_pct'] = float(100 * np.median(np.abs(np.exp(resid) - 1)))
        out['channels'][ch] = res
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--session', required=True)
    ap.add_argument('--compare', metavar='REF_SESSION', help='decompose ln(H_session / H_ref) between sessions')
    a = ap.parse_args()
    out = compare(a.compare, a.session) if a.compare else analyze(a.session)
    name = f'drift_vs_{a.compare}.json' if a.compare else 'drift_analysis.json'
    path = REPO / 'data/results/k_eff' / a.session / 'derived' / name
    path.write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
