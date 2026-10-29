#!/usr/bin/env python3
"""Scores the O3 ringdown / ring-up runs (preregistered in docs/lab_diary_20261029.md §1).

Per capture, Ch A's complex envelope at the drive frequency: mix to baseband, then a 0.4 ms Hann low-pass.
    ringdown  z(t) = D exp(s (t - t_stop))            from t_stop + 0.3 ms
    ring-up   z(t) = C + D exp(s (t - t_0))           from t_0 + 0.3 ms
with s = -1/tau + 2 pi i df, fitted by complex least squares to 0.25 ms before the end of the block. The
ringdown fit also stops where the fitted envelope falls to the larger of 5x the envelope noise floor (the
run's QUIET captures) and 3 ADC steps, below which the 8-bit quantization (noise ~0.3 step) biases the tail.
R^2 compares |z| with the fitted magnitude over the fit window. Captures are re-classified from raw Ch B with
ring_capture.classify_*; clipped or overflowed captures are dropped.

Per window: medians over at least 5 captures. The run's zoom sweep is refitted with fit_zoom.fit:
tau_Q = Q / (pi f0), usable under the overnight cuts (f0 in window, se f0 <= 20 Hz, rel. rms <= 0.10,
se ln Q <= 0.15). A window passes when its median R^2 >= 0.9 and |tau / tau_Q - 1| <= 0.20.

    python3 data/results/k_eff/ringdown_20261029/score_ring.py             # every run in log.jsonl
    python3 data/results/k_eff/ringdown_20261029/score_ring.py --selftest  # planted decays, no bench data
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

OUT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('ring_capture', OUT / 'ring_capture.py')
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

ENV_WIN_S = 0.4e-3
SKIP_S = 0.3e-3
END_S = 0.25e-3
NOISE_K = 5.0
AMP_FLOOR_STEPS = 3
MIN_SPAN_S = 1.0e-3
DECIM = 8
MIN_CAPTURES = 5
R2_MIN = 0.9
TAU_TOL = 0.20
UPDOWN_TOL = 0.10
MIN_MODES = 5
MAX_BAD_FRACTION = 0.05


def envelope(x_mv: np.ndarray, f: float, fs: float) -> np.ndarray:
    """Complex peak-amplitude envelope at f: mix to baseband, normalized Hann low-pass of ENV_WIN_S."""
    x = np.asarray(x_mv, float)
    n = np.arange(len(x))
    mixed = (x - x.mean()) * np.exp(-2j * np.pi * f * n / fs)
    w = np.hanning(int(round(ENV_WIN_S * fs)) | 1)
    return 2 * np.convolve(mixed, w / w.sum(), mode='same')


def fit_exp(t: np.ndarray, z: np.ndarray, offset: bool) -> dict:
    """z(t) = [C +] D exp((-1/tau + 2 pi i df) t) by complex least squares; R^2 of |z| against the fit."""
    def model(p):
        m = (p[2] + 1j * p[3]) * np.exp((-np.exp(-p[0]) + 2j * np.pi * p[1]) * t)
        return m + (p[4] + 1j * p[5]) if offset else m

    def res(p):
        r = model(p) - z
        return np.concatenate([r.real, r.imag])

    c0 = z[-1] if offset else 0j
    y = z - c0
    a = np.abs(y)
    use = a > 0.05 * a.max()
    slope = np.polyfit(t[use], np.log(a[use]), 1, w=a[use])[0]
    tau0 = float(np.clip(-1 / slope if slope < 0 else 1e-3, 1e-4, 0.05))
    df0 = float(np.polyfit(t[use], np.unwrap(np.angle(y[use])), 1, w=a[use])[0] / (2 * np.pi))
    d0 = y[0] / np.exp((-1 / tau0 + 2j * np.pi * df0) * t[0])
    p0 = [np.log(tau0), df0, d0.real, d0.imag] + ([c0.real, c0.imag] if offset else [])
    r = least_squares(res, p0, method='lm', x_scale='jac', max_nfev=5000)
    az, am = np.abs(z), np.abs(model(r.x))
    cov = np.linalg.pinv(r.jac.T @ r.jac) * 2 * r.cost / max(r.fun.size - r.x.size, 1)
    return {'tau': float(np.exp(r.x[0])), 'se_lntau': float(np.sqrt(cov[0, 0])), 'df': float(r.x[1]),
            'D': complex(r.x[2], r.x[3]), 'C': complex(r.x[4], r.x[5]) if offset else None,
            'r2': float(1 - np.sum((az - am) ** 2) / np.sum((az - az.mean()) ** 2)), 'n': int(len(t))}


def score_down(xa_mv: np.ndarray, fa: float, fs: float, t_stop: float, floor_mv: float) -> dict:
    z = envelope(xa_mv, fa, fs)
    t = np.arange(len(z)) / fs - t_stop
    hi = len(z) / fs - END_S - t_stop
    sel = (t >= SKIP_S) & (t <= hi)
    first = fit_exp(t[sel][::DECIM], z[sel][::DECIM], False)
    d = abs(first['D'])
    hi = min(hi, first['tau'] * np.log(d / floor_mv) if d > floor_mv else 0.0)
    if hi - SKIP_S < MIN_SPAN_S:
        return {'status': 'short', 'span_s': float(hi - SKIP_S)}
    sel = (t >= SKIP_S) & (t <= hi)
    return {**fit_exp(t[sel][::DECIM], z[sel][::DECIM], False), 'status': 'ok', 'span_s': float(hi - SKIP_S)}


def score_up(xa_mv: np.ndarray, fa: float, fs: float, t0: float) -> dict:
    z = envelope(xa_mv, fa, fs)
    t = np.arange(len(z)) / fs - t0
    sel = (t >= SKIP_S) & (t <= len(z) / fs - END_S - t0)
    return {**fit_exp(t[sel][::DECIM], z[sel][::DECIM], True), 'status': 'ok', 'span_s': float(t[sel][-1] - SKIP_S)}


def noise_sigma(quiet_mv: np.ndarray, fa: float, fs: float) -> float:
    """RMS of the complex envelope at fa over the QUIET captures, edges excluded."""
    m = int(round(ENV_WIN_S * fs))
    return float(np.sqrt(np.mean([np.mean(np.abs(envelope(x, fa, fs)[m:-m]) ** 2) for x in quiet_mv])))


def summarize(vals: list[dict], tau_q: float | None) -> dict:
    out = {'n_scored': len(vals)}
    if not vals:
        return out
    tau = np.array([v['tau'] for v in vals])
    out.update({'tau_ms': float(1e3 * np.median(tau)),
                'tau_iqr_ms': [float(1e3 * np.percentile(tau, 25)), float(1e3 * np.percentile(tau, 75))],
                'r2': float(np.median([v['r2'] for v in vals])), 'df_hz': float(np.median([v['df'] for v in vals])),
                'span_ms': float(1e3 * np.median([v['span_s'] for v in vals]))})
    if tau_q:
        out['ratio_to_tau_Q'] = out['tau_ms'] / (1e3 * tau_q)
    out['pass'] = bool(len(vals) >= MIN_CAPTURES and out['r2'] >= R2_MIN and tau_q
                       and abs(out['ratio_to_tau_Q'] - 1) <= TAU_TOL)
    return out


def score_run(entry: dict) -> dict:
    repo = rc.REPO
    for key in ('raw', 'meta'):
        got = rc.sha256(repo / entry[f'{key}_file'])
        if got != entry[f'{key}_sha256']:
            raise SystemExit(f'{entry[f"{key}_file"]}: sha256 {got} differs from the capture-time {entry[f"{key}_sha256"]}')
    raw, meta = np.load(repo / entry['raw_file']), np.load(repo / entry['meta_file'])
    s = entry['settings']
    fs, thr = s['sample_rate_hz'], round(s['trigger_mV'] / s['range_mV'] * 32767)

    def counts(name):
        x = raw[name]
        return x.astype(np.int32) * (256 if x.dtype == np.int8 else 1)

    ka = float(raw['mv_per_count_A'])
    ring_a, ring_b, quiet_a = counts('ring_A') * ka, counts('ring_B'), counts('quiet_A') * ka
    step_mv = 256 * ka
    zc = meta['zoom_center']
    clean = (meta['zoom_ovf'] == 0) & (meta['zoom_clipA'] == 0) & (meta['zoom_clipB'] == 0)
    windows, mismatch = {}, 0
    for c in rc.WINDOWS[entry['path']]:
        key = f'{entry["path"]}:{c}'
        sel = (zc == c) & clean
        try:
            fit = rc.window_fit(meta['zoom_f_act'][sel], meta['zoom_zA'][sel] / meta['zoom_zB'][sel], c)
        except (AttributeError, ValueError, TypeError, np.linalg.LinAlgError):
            fit = {'usable_f0': False, 'usable_Q': False, 'n_points': int(sel.sum())}
        tau_q = fit['Q'] / (np.pi * fit['f0']) if fit['usable_Q'] else None
        res, n_short = {'up': [], 'down': []}, 0
        idx = np.flatnonzero(meta['target'] == key)
        floor = (max(NOISE_K * noise_sigma(quiet_a, float(meta['f_act'][idx[0]]), fs), AMP_FLOOR_STEPS * step_mv)
                 if len(idx) else None)
        n_bad = 0
        for i in idx:
            kind, fa = str(meta['kind'][i]), float(meta['f_act'][i])
            bad = bool(meta['ovf'][i] != 0 or meta['clipA'][i] or meta['clipB'][i])
            n_bad += bad
            if kind == 'up':
                st, i0 = rc.classify_up(ring_b[i], thr, fs, fa)
                edge = None if i0 is None else i0 / fs
            else:
                st, edge = rc.classify_down(ring_b[i], thr, fs, fa)
            mismatch += st != str(meta['status'][i])
            if st != 'ok' or bad:
                continue
            r = score_up(ring_a[i], fa, fs, edge) if kind == 'up' else score_down(ring_a[i], fa, fs, edge, floor)
            if r['status'] == 'ok':
                res[kind].append(r)
            else:
                n_short += 1
        fa = float(meta['f_act'][idx[0]]) if len(idx) else None
        down, up = summarize(res['down'], tau_q), summarize(res['up'], tau_q)
        w = {'path': entry['path'], 'run_id': entry['run_id'], 'drive_cmd': entry['zoom_fits'][key]['drive_cmd'],
             'f_act_hz': fa, 'zoom': {k: fit.get(k) for k in ('f0', 'se_f0', 'Q', 'se_lnQ', 'rel_rms', 'usable_f0',
                                                               'usable_Q', 'n_points')},
             'tau_Q_ms': None if tau_q is None else 1e3 * tau_q, 'down': down, 'up': up,
             'n_captures': int(len(idx)), 'n_bad': int(n_bad), 'n_down_too_short': int(n_short),
             'fit_floor_mV': floor}
        if 'df_hz' in down and fa and fit['usable_f0']:
            w['free_decay_hz'] = fa + down['df_hz']
            w['free_minus_f0_linewidths'] = (fa + down['df_hz'] - fit['f0']) / (fit['f0'] / fit['Q'])
        if down.get('pass') and up.get('pass'):
            w['up_over_down'] = up['tau_ms'] / down['tau_ms']
        windows[key] = w
    n_target = sum(w['n_captures'] for w in windows.values())
    valid = {kind: bool(sum(w[kind]['n_scored'] >= MIN_CAPTURES for w in windows.values()) >= len(windows) / 2
                        and sum(w['n_bad'] for w in windows.values()) <= MAX_BAD_FRACTION * n_target)
             for kind in ('down', 'up')}
    return {'windows': windows, 'valid': valid, 'status_mismatches': mismatch,
            'qualification': entry['qualification'], 'live_check': entry['live_check']}


def outcome(runs: dict) -> dict:
    wins = {k: w for r in runs.values() for k, w in r['windows'].items()}
    out = {}
    for kind, name in (('down', 'P1_ringdown'), ('up', 'P2_ring_up')):
        passed = sorted(k for k, w in wins.items() if w[kind].get('pass'))
        if not any(r['valid'][kind] for r in runs.values()):
            verdict = 'not captured'
        elif len(passed) >= MIN_MODES:
            verdict = 'confirmed'
        elif passed:
            verdict = 'partial'
        else:
            verdict = 'not confirmed'
        out[name] = {'verdict': verdict, 'passed': passed, 'n_passed': len(passed)}
    both = {k: w['up_over_down'] for k, w in wins.items() if 'up_over_down' in w}
    agree = sorted(k for k, v in both.items() if abs(v - 1) <= UPDOWN_TOL)
    out['P3_up_vs_down'] = {'verdict': 'n/a' if not both else ('confirmed' if len(agree) == len(both) else
                                                               ('partial' if agree else 'not confirmed')),
                            'agree': agree, 'compared': sorted(both)}
    if out['P1_ringdown']['verdict'] == 'not captured':
        out['O3_method_of_record'] = 'ring-up (ringdown not captured; preregistered fallback)'
    else:
        out['O3_method_of_record'] = 'ringdown'
    return out


def selftest() -> None:
    """Planted decays through the same classification and fits; exits non-zero on a failed recovery."""
    rng = np.random.default_rng(1)
    fs, n, ka = 781_250.0, rc.N_RING, rc.K
    thr = round(rc.TRIG_MV / rc.RANGE_MV * 32767)
    step = 256 * ka
    t = np.arange(n) / fs

    def quantize(x_mv):
        """mV -> 8-bit scope counts as ps2000 returns them (multiples of 256)."""
        return np.clip(np.round(x_mv / ka / 256) * 256, -32512, 32512)

    def pulses(fa, on):
        return quantize(np.where(on & (((t * fa) % 1.0) < 0.1), 3200.0, 0.0))

    def noise():
        return rng.normal(0, 0.3 * step, n)

    def ringdown(fa, modes, t_stop):
        """modes: (amp_mV, f_natural, tau, phase); steady state at fa before t_stop, free decay after.
        Returns Ch A in mV and Ch B in counts."""
        x = np.where(t < t_stop, 20 * np.cos(2 * np.pi * fa * t + 2.0), 0.0)
        for amp, fm, tau, ph in modes:
            ss = amp * np.cos(2 * np.pi * fa * t + ph)
            dec = amp * np.exp(-(t - t_stop) / tau) * np.cos(2 * np.pi * fm * (t - t_stop) + 2 * np.pi * fa * t_stop + ph)
            x += np.where(t < t_stop, ss, dec)
        return quantize(x + noise()) * ka, pulses(fa, t < t_stop)

    def ring_up(fa, modes, t0):
        x = np.where(t >= t0, 20 * np.cos(2 * np.pi * fa * t + 2.0), 0.0)
        tt = np.clip(t - t0, 0, None)
        for amp, fm, tau, ph in modes:
            z = amp * np.exp(1j * ph) * (1 - np.exp((-1 / tau + 2j * np.pi * (fm - fa)) * tt))
            x += np.where(t >= t0, np.real(z * np.exp(2j * np.pi * fa * t)), 0.0)
        return quantize(x + noise()) * ka, pulses(fa, t >= t0)

    fa = rc.pio_actual_freq(58_500)
    quiet = np.array([quantize(noise()) * ka for _ in range(5)])
    floor = max(NOISE_K * noise_sigma(quiet, fa, fs), AMP_FLOOR_STEPS * step)
    extra = [(50.0, fa + 3000, 1.5e-3, 1.1), (200.0, 2 * fa + 100, 1.0e-3, 0.3)]   # neighbour, 2f-driven mode
    ok = True
    print(f'selftest: fa {fa:.2f} Hz, ADC step {step:.1f} mV, fit floor {floor:.1f} mV')
    for amp, tau, df in ((600.0, 1.2e-3, 30.0), (1300.0, 2.5e-3, -15.0), (500.0, 1.0e-3, 0.0)):
        a, b = ringdown(fa, [(amp, fa + df, tau, 0.7)] + extra, 1.0e-3)
        st, ts = rc.classify_down(b, thr, fs, fa)
        r = score_down(a, fa, fs, ts, floor)
        good = (st == 'ok' and abs(ts - 1.0e-3) < 1.5 / fa and r['status'] == 'ok'
                and abs(r['tau'] / tau - 1) < 0.02 and abs(r['df'] - df) < 5 and r['r2'] > 0.98)
        ok &= good
        print(f'  ringdown {amp:.0f} mV tau {1e3 * tau:.2f} ms df {df:+.0f} Hz: {st}, t_stop {1e3 * ts:.4f} ms, '
              f'tau {1e3 * r["tau"]:.4f} ms ({100 * (r["tau"] / tau - 1):+.2f}%), df {r["df"]:+.2f} Hz, '
              f'R2 {r["r2"]:.4f}, span {1e3 * r["span_s"]:.2f} ms  {"PASS" if good else "FAIL"}')
        a, b = ring_up(fa, [(amp, fa + df, tau, 0.7)] + extra, round(rc.PRE_PCT / 100 * n) / fs)
        st, i0 = rc.classify_up(b, thr, fs, fa)
        r = score_up(a, fa, fs, i0 / fs)
        good = st == 'ok' and abs(r['tau'] / tau - 1) < 0.02 and abs(r['df'] - df) < 5 and r['r2'] > 0.98
        ok &= good
        print(f'  ring-up  {amp:.0f} mV tau {1e3 * tau:.2f} ms df {df:+.0f} Hz: {st}, '
              f'tau {1e3 * r["tau"]:.4f} ms ({100 * (r["tau"] / tau - 1):+.2f}%), df {r["df"]:+.2f} Hz, '
              f'R2 {r["r2"]:.4f}  {"PASS" if good else "FAIL"}')
    a, b = ringdown(fa, [(600.0, fa, 1.2e-3, 0.7), (600.0, fa + 300, 1.2e-3, 2.0)], 1.0e-3)
    st, ts = rc.classify_down(b, thr, fs, fa)
    r = score_down(a, fa, fs, ts, floor)
    caught = r['status'] != 'ok' or r['r2'] < R2_MIN
    print(f'  doublet 300 Hz apart (must not score as one clean mode): {r["status"]}, R2 {r.get("r2", np.nan):.3f}, '
          f'span {1e3 * r["span_s"]:.2f} ms  {"caught" if caught else "NOT CAUGHT"}')
    ok &= caught
    for d, want in ((20.0, 'late'), (-1.0, 'early'), (3.0, 'outside'), (1.2, 'ok')):
        st, _ = rc.classify_down(pulses(fa, t < d * 1e-3), thr, fs, fa)
        ok &= st == want
        print(f'  stop at {d:+.1f} ms: {st} (want {want})')
    raise SystemExit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    entries = [json.loads(x) for x in (OUT / 'log.jsonl').read_text().splitlines() if x.strip()]
    runs = {e['run_id']: score_run(e) for e in entries if e.get('event') == 'run'}
    result = {'status': 'exploratory, preregistered in docs/lab_diary_20261029.md §1',
              'scoring_sha256': rc.sha256(Path(__file__).resolve()),
              'capture_sha256': rc.sha256(OUT / 'ring_capture.py'), 'runs': runs, 'outcome': outcome(runs)}
    (OUT / 'ring_result.json').write_text(json.dumps(result, indent=1, default=str) + '\n')
    print(f'{"window":10s} {"drive Hz":>9s} {"tau_Q":>6s} {"down":>6s} {"n":>3s} {"R2":>6s} {"ratio":>6s} '
          f'{"up":>6s} {"n":>3s} {"R2":>6s} {"ratio":>6s}')
    for r in runs.values():
        for k, w in r['windows'].items():
            d, u = w['down'], w['up']
            f = lambda x, p=3: '-' if x is None else f'{x:.{p}f}'  # noqa: E731
            print(f'{k:10s} {w["drive_cmd"]:9d} {f(w["tau_Q_ms"], 2):>6s} {f(d.get("tau_ms"), 2):>6s} '
                  f'{d["n_scored"]:3d} {f(d.get("r2")):>6s} {f(d.get("ratio_to_tau_Q")):>6s} '
                  f'{f(u.get("tau_ms"), 2):>6s} {u["n_scored"]:3d} {f(u.get("r2")):>6s} {f(u.get("ratio_to_tau_Q")):>6s}')
    print(json.dumps(result['outcome'], indent=1))


if __name__ == '__main__':
    main()
