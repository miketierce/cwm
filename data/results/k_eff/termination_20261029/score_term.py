#!/usr/bin/env python3
"""Scores the O5 TX-termination runs (preregistered in docs/lab_diary_20261029.md §9).

Each capture is scored exactly as in O3 (ringdown_20261029/score_ring.py): 0.4 ms Hann envelope at the drive
frequency, ringdown z = D exp(s (t - t_stop)) and ring-up z = C + D exp(s (t - t_0)) from 0.3 ms after the edge,
ringdown fit ending at the larger of 5x QUIET noise and 3 ADC steps. Captures are re-classified from raw Ch B;
clipped or overflowed ones are dropped. Per window and run:
  - paired ratio: in each cycle where both conditions scored, tau_open / tau_grounded; the window value is the median
  - ring-up control: the same paired ratio for the ring-ups (the drive is identical in both conditions)
  - free-decay frequency, open minus grounded (drive frequency + fitted df), in Hz and ppm
  - termination check: rms of the Ch B envelope 0.3-1.5 ms after the stop, open / grounded. An open TX2 PZT
    carries the plate's ringing; a grounded one is shunted by 220 ohm.
A window is scored when both conditions have >= 5 scored ringdowns with median R^2 >= 0.9 and >= 5 cycle pairs.
Verdict over the scored windows (at least 3 needed): median paired ratio < 1.2 'small', 1.2-2 'moderate', >= 2 'large',
given only if the median Ch B open/grounded ratio is >= 3 (otherwise 'open termination not confirmed').
Added before any data (§9 amendment, basis bvd_o3.py): P3, no scored window below 1.05 and the median within
1.08-1.40; P4, the free-decay frequency higher when open in every scored window. shift_per_loss =
2 pi f_shift / (1/tau_g - 1/tau_o) is reported as a diagnostic (the transducer circuit expects about 6-10).
Runs with other --setup labels are compared with the first run on grounded ringdown tau, window by window.

    python3 data/results/k_eff/termination_20261029/score_term.py
    python3 data/results/k_eff/termination_20261029/score_term.py --selftest
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sr = _load('score_ring', REPO / 'data/results/k_eff/ringdown_20261029/score_ring.py')
rc = sr.rc
CONDS = ('grounded', 'open')
CHB_WIN = (0.3e-3, 1.5e-3)
MIN_N, R2_MIN, MIN_WINDOWS = 5, 0.9, 3
SMALL, LARGE, P1B_MAX, P2_TOL = 1.2, 2.0, 1.5, 0.10
CHB_CONFIRM = 3.0          # median Ch B post-stop open/grounded needed to confirm Fz really opened TX2
P3_MIN, P3_BAND = 1.05, (1.08, 1.40)


def score_capture(kind: str, a_mv: np.ndarray, b_mv: np.ndarray, b_counts: np.ndarray, fa: float, fs: float,
                  thr: int, floor: float) -> dict:
    if kind == 'up':
        st, i0 = rc.classify_up(b_counts, thr, fs, fa)
        edge = None if i0 is None else i0 / fs
    else:
        st, edge = rc.classify_down(b_counts, thr, fs, fa)
    if st != 'ok':
        return {'status': st}
    r = sr.score_up(a_mv, fa, fs, edge) if kind == 'up' else sr.score_down(a_mv, fa, fs, edge, floor)
    if kind == 'down' and r['status'] == 'ok':
        zb = np.abs(sr.envelope(b_mv, fa, fs))
        t = np.arange(len(zb)) / fs - edge
        sel = (t >= CHB_WIN[0]) & (t <= CHB_WIN[1])
        r['chb_post_mV'] = float(np.sqrt(np.mean(zb[sel] ** 2)))
    return {**r, 'f_free_hz': fa + r['df'] if r['status'] == 'ok' else None}


def window_summary(rows: list[dict]) -> dict:
    """rows: one dict per capture with cond, kind, cycle and score_capture's result."""
    out = {}
    for kind in ('down', 'up'):
        per = {c: {x['cycle']: x for x in rows if x['kind'] == kind and x['cond'] == c and x.get('status') == 'ok'}
               for c in CONDS}
        stats = {c: ({'n': len(v), 'tau_ms': float(1e3 * np.median([x['tau'] for x in v.values()])),
                      'r2': float(np.median([x['r2'] for x in v.values()])),
                      'f_free_hz': float(np.median([x['f_free_hz'] for x in v.values()]))} if v else {'n': 0})
                 for c, v in per.items()}
        pairs = [per['open'][k]['tau'] / per['grounded'][k]['tau'] for k in per['open'] if k in per['grounded']]
        out[kind] = {**stats, 'n_pairs': len(pairs),
                     'paired_ratio': float(np.median(pairs)) if pairs else None,
                     'paired_iqr': [float(np.percentile(pairs, 25)), float(np.percentile(pairs, 75))] if pairs else None}
    d = out['down']
    if d['grounded']['n'] and d['open']['n']:
        shift = d['open']['f_free_hz'] - d['grounded']['f_free_hz']
        out['f_shift_hz'], out['f_shift_ppm'] = shift, 1e6 * shift / d['grounded']['f_free_hz']
        dalpha = 1e3 / d['grounded']['tau_ms'] - 1e3 / d['open']['tau_ms']
        out['shift_per_loss'] = 2 * np.pi * shift / dalpha if dalpha else None
        chb = {c: [x['chb_post_mV'] for x in rows if x['kind'] == 'down' and x['cond'] == c and 'chb_post_mV' in x]
               for c in CONDS}
        out['chb_post_mV'] = {c: float(np.median(v)) if v else float('nan') for c, v in chb.items()}
        o, g = out['chb_post_mV']['open'], out['chb_post_mV']['grounded']
        out['chb_open_over_grounded'] = o / g if g > 0 else (float('inf') if o > 0 else float('nan'))
    out['scored'] = bool(all(d[c]['n'] >= MIN_N and d[c].get('r2', 0) >= R2_MIN for c in CONDS)
                         and d['n_pairs'] >= MIN_N)
    return out


def verdict(windows: dict) -> dict:
    scored = {k: w for k, w in windows.items() if w['scored']}
    ratios = [w['down']['paired_ratio'] for w in scored.values()]
    ups = [w['up']['paired_ratio'] for w in scored.values() if w['up']['paired_ratio'] is not None]
    if len(scored) < MIN_WINDOWS:
        return {'verdict': f'invalid: {len(scored)} scored windows (need {MIN_WINDOWS})', 'scored': sorted(scored)}
    med = float(np.median(ratios))
    chb = float(np.median([w['chb_open_over_grounded'] for w in scored.values()]))
    if not chb >= CHB_CONFIRM:
        return {'verdict': f'open termination not confirmed (Ch B open/grounded {chb:.2f} < {CHB_CONFIRM})',
                'scored': sorted(scored), 'median_paired_ratio': med, 'chb_open_over_grounded': chb}
    return {'scored': sorted(scored), 'median_paired_ratio': med, 'chb_open_over_grounded': chb,
            'verdict': 'small' if med < SMALL else ('moderate' if med < LARGE else 'large'),
            'P1_small_change': bool(med < SMALL), 'P1b_no_window_above_1.5': bool(max(ratios) < P1B_MAX),
            'P2_ring_up_control': bool(len(ups) == len(scored) and all(abs(u - 1) <= P2_TOL for u in ups)),
            'P3_no_window_below_1.05': bool(min(ratios) >= P3_MIN),
            'P3_median_1.08_to_1.40': bool(P3_BAND[0] <= med <= P3_BAND[1]),
            'P4_f_shift_positive': bool(all(w.get('f_shift_hz', 0) > 0 for w in scored.values())),
            'window_ratios': {k: w['down']['paired_ratio'] for k, w in scored.items()},
            'f_shift_hz': {k: w.get('f_shift_hz') for k, w in scored.items()},
            'shift_per_loss': {k: w.get('shift_per_loss') for k, w in scored.items()}}


def score_run(entry: dict) -> dict:
    for key in ('raw', 'meta'):
        if rc.sha256(REPO / entry[f'{key}_file']) != entry[f'{key}_sha256']:
            raise SystemExit(f'{entry[f"{key}_file"]}: sha256 differs from the capture-time hash')
    raw, meta = np.load(REPO / entry['raw_file']), np.load(REPO / entry['meta_file'])
    s = entry['settings']
    fs, thr = s['sample_rate_hz'], round(s['trigger_mV'] / s['range_mV'] * 32767)

    def counts(name):
        x = raw[name]
        return x.astype(np.int32) * (256 if x.dtype == np.int8 else 1)

    ka, kb = float(raw['mv_per_count_A']), float(raw['mv_per_count_B'])
    ring_a, ring_bc, quiet_a = counts('ring_A') * ka, counts('ring_B'), counts('quiet_A') * ka
    windows = {}
    for c in rc.WINDOWS[entry['path']]:
        key = f'{entry["path"]}:{c}'
        idx = np.flatnonzero(meta['target'] == key)
        if not len(idx):
            continue
        fa = float(meta['f_act'][idx[0]])
        floor = max(sr.NOISE_K * sr.noise_sigma(quiet_a, fa, fs), sr.AMP_FLOOR_STEPS * 256 * ka)
        rows = []
        for i in idx:
            row = {'cond': str(meta['cond'][i]), 'kind': str(meta['kind'][i]), 'cycle': int(meta['cycle'][i])}
            if meta['ovf'][i] != 0 or meta['clipA'][i] or meta['clipB'][i]:
                rows.append({**row, 'status': 'clip_or_ovf'})
                continue
            rows.append({**row, **score_capture(row['kind'], ring_a[i], ring_bc[i] * kb, ring_bc[i], fa, fs, thr, floor)})
        windows[key] = {**window_summary(rows), 'drive_hz': fa,
                        'zoom': {k: entry['zoom_fits'][key].get(k) for k in ('f0', 'Q', 'usable_Q')}}
    return {'setup': entry['setup'], 'path': entry['path'], 'windows': windows, 'outcome': verdict(windows),
            'offset_ms': entry.get('offset_ms'), 'counts': entry.get('counts')}


def compare_setups(runs: dict) -> dict:
    """Grounded ringdown tau of each later run over the first run's, window by window (Parts B and C)."""
    ids = list(runs)
    if len(ids) < 2:
        return {}
    ref = runs[ids[0]]
    out = {}
    for rid in ids[1:]:
        r = runs[rid]
        ratio = {k: w['down']['grounded']['tau_ms'] / ref['windows'][k]['down']['grounded']['tau_ms']
                 for k, w in r['windows'].items()
                 if k in ref['windows'] and w['down']['grounded']['n'] >= MIN_N and ref['windows'][k]['down']['grounded']['n'] >= MIN_N}
        out[rid] = {'setup': r['setup'], 'vs': ref['setup'], 'grounded_tau_ratio': ratio,
                    'median': float(np.median(list(ratio.values()))) if ratio else None}
    return out


def selftest() -> None:
    """Planted open/grounded decays through the same scoring; exits non-zero if the ratio is misread."""
    rng = np.random.default_rng(5)
    fs, n, k = 781_250.0, rc.N_RING, rc.K
    thr = round(rc.TRIG_MV / rc.RANGE_MV * 32767)
    t = np.arange(n) / fs
    fa = rc.pio_actual_freq(73_706)
    fm = fa + 20.0

    def quant(x_mv):
        return np.clip(np.round(x_mv / k / 256) * 256, -32512, 32512)

    def pulses(on, extra=0.0):
        return quant(np.where(on & (((t * fa) % 1.0) < 0.1), 3200.0, 0.0) + extra)

    def ringdown(tau, chb_amp, ts, f_free):
        x = np.where(t < ts, 1000 * np.cos(2 * np.pi * fa * t),
                     1000 * np.exp(-(t - ts) / tau) * np.cos(2 * np.pi * f_free * (t - ts) + 2 * np.pi * fa * ts))
        ring_b = np.where(t >= ts, chb_amp * np.exp(-(t - ts) / tau) * np.cos(2 * np.pi * f_free * (t - ts)), 0.0)
        return quant(x + rng.normal(0, 12, n)) * k, pulses(t < ts, ring_b + rng.normal(0, 12, n))

    def ring_up(tau, t0):
        tt = np.clip(t - t0, 0, None)
        z = 1000 * (1 - np.exp((-1 / tau + 2j * np.pi * (fm - fa)) * tt))
        return quant(np.where(t >= t0, np.real(z * np.exp(2j * np.pi * fa * t)), 0) + rng.normal(0, 12, n)) * k, \
            pulses(t >= t0)

    floor = sr.AMP_FLOOR_STEPS * 256 * k
    rows = []
    for cyc in range(8):
        for cond, tau_down, chb, f_free in (('grounded', 1.2e-3, 3.0, fm), ('open', 1.5e-3, 40.0, fm + 80.0)):
            a, b = ringdown(tau_down, chb, 1.25e-3 + rng.normal(0, 0.03e-3), f_free)
            rows.append({'cond': cond, 'kind': 'down', 'cycle': cyc, **score_capture('down', a, b * k, b, fa, fs, thr, floor)})
            a, b = ring_up(1.2e-3, round(rc.PRE_PCT / 100 * n) / fs)
            rows.append({'cond': cond, 'kind': 'up', 'cycle': cyc, **score_capture('up', a, b * k, b, fa, fs, thr, floor)})
    w = window_summary(rows)
    d, u = w['down'], w['up']
    ok = (w['scored'] and abs(d['paired_ratio'] / 1.25 - 1) < 0.03 and abs(u['paired_ratio'] - 1) < 0.05
          and w['chb_open_over_grounded'] > 3 and abs(w['f_shift_hz'] - 80) < 5)
    print(f'selftest: ringdown paired ratio {d["paired_ratio"]:.4f} (planted 1.25), ring-up control '
          f'{u["paired_ratio"]:.4f} (planted 1.00), tau grounded/open {d["grounded"]["tau_ms"]:.3f}/'
          f'{d["open"]["tau_ms"]:.3f} ms, R2 {d["grounded"]["r2"]:.3f}/{d["open"]["r2"]:.3f}, Ch B open/grounded '
          f'{w["chb_open_over_grounded"]:.1f}, f shift {w["f_shift_hz"]:.1f} Hz (planted 80), shift_per_loss '
          f'{w["shift_per_loss"]:.2f} (planted {2 * np.pi * 80 / (1 / 1.2e-3 - 1 / 1.5e-3):.2f}), scored {w["scored"]}  '
          f'{"PASS" if ok else "FAIL"}')
    raise SystemExit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    entries = [json.loads(x) for x in (OUT / 'log.jsonl').read_text().splitlines() if x.strip()]
    runs = {e['run_id']: score_run(e) for e in entries if e.get('event') == 'run'}
    result = {'status': 'exploratory, preregistered in docs/lab_diary_20261029.md §9',
              'scoring_sha256': rc.sha256(Path(__file__).resolve()),
              'capture_sha256': rc.sha256(OUT / 'term_capture.py'), 'runs': runs, 'setups': compare_setups(runs)}
    (OUT / 'term_result.json').write_text(json.dumps(result, indent=1, default=str) + '\n')
    for rid, r in runs.items():
        print(f'{rid} ({r["setup"]}): {r["outcome"]}')
        for key, w in r['windows'].items():
            d, u = w['down'], w['up']
            fmt = lambda v, p=3: '-' if v is None else f'{v:.{p}f}'  # noqa: E731
            print(f'  {key}: tau g/o {fmt(d["grounded"].get("tau_ms"))}/{fmt(d["open"].get("tau_ms"))} ms '
                  f'(R2 {fmt(d["grounded"].get("r2"))}/{fmt(d["open"].get("r2"))}, n {d["grounded"]["n"]}/{d["open"]["n"]}) '
                  f'paired {fmt(d["paired_ratio"])} | ring-up paired {fmt(u["paired_ratio"])} | '
                  f'f shift {fmt(w.get("f_shift_hz"), 1)} Hz | Ch B o/g {fmt(w.get("chb_open_over_grounded"), 1)} | '
                  f'scored {w["scored"]}')
    if result['setups']:
        print(json.dumps(result['setups'], indent=1))


if __name__ == '__main__':
    main()
