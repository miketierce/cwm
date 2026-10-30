#!/usr/bin/env python3
"""Post hoc (not preregistered): why O5 Part A read 'open termination not confirmed' (docs/lab_diary_20261029.md §11).

  1. Held-high stops: an open stop that releases TX2 while its pin is HIGH leaves the PZT charged, and it then
     discharges through Ch B's 1 MOhm. The decay gives the capacitance at the TX2 terminal (an upper bound on the
     parallel resistance makes it a lower bound on C), and its intercept with the held level gives the release time.
     Foff's held-high stops give the time it takes to drive the pin LOW.
  2. Ch B envelope after the stop, open and grounded, on a time grid (when the open state takes over).
  3. bvd_o3.py's estimate redone at the measured capacitance, against the run.

    python3 data/results/k_eff/termination_20261029/posthoc_term.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
R_SCOPE = 1e6
HELD_MV, HOLD_MV = 1500, 2800
FIT_MV = (300, 2600)
GRID_MS = (0.15, 0.3, 0.5, 1.0, 2.0)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


st = _load('score_term', OUT / 'score_term.py')
bvd = _load('bvd_o3', OUT / 'bvd_o3.py')
sr, rc = st.sr, st.rc


def main():
    entry = [json.loads(x) for x in (OUT / 'log.jsonl').read_text().splitlines() if '"run"' in x][-1]
    raw, meta = np.load(st.REPO / entry['raw_file']), np.load(st.REPO / entry['meta_file'])
    fs = entry['settings']['sample_rate_hz']
    thr = round(entry['settings']['trigger_mV'] / entry['settings']['range_mV'] * 32767)
    bc = raw['ring_B'].astype(np.int32) * (256 if raw['ring_B'].dtype == np.int8 else 1)
    b_mv = bc * float(raw['mv_per_count_B'])
    released, taus, holds = [], [], []
    env = {}
    for i in np.flatnonzero(meta['kind'] == 'down'):
        cond, key, fa = str(meta['cond'][i]), str(meta['target'][i]), float(meta['f_act'][i])
        edges = rc.rising_edges(bc[i], thr)
        if len(edges):
            seg = b_mv[i][edges[-1]:]
            t = np.arange(len(seg)) / fs
            held = np.flatnonzero(seg > HELD_MV)
            if np.sum(held > 3 * fs / fa) >= 5:
                if cond == 'open':
                    v0 = np.median(seg[(t < 0.1e-3) & (seg > 3000)])
                    sel = (seg > FIT_MV[0]) & (seg < FIT_MV[1])
                    slope, icpt = np.polyfit(t[sel], np.log(seg[sel]), 1)
                    taus.append(-1 / slope)
                    released.append(-(icpt - np.log(v0)) / slope)
                else:
                    holds.append(t[np.flatnonzero(seg > HOLD_MV)[-1]])
        status, ts = rc.classify_down(bc[i], thr, fs, fa)
        if status == 'ok' and key.startswith('F2:'):
            z = np.abs(sr.envelope(b_mv[i], fa, fs))
            tt = np.arange(len(z)) / fs - ts
            env.setdefault(key, {}).setdefault(cond, []).append([z[np.argmin(np.abs(tt - g / 1e3))] for g in GRID_MS])
    c_term = float(np.median(taus)) / R_SCOPE
    run = st.score_run(entry)
    bvd.C0_F = c_term
    o3 = [json.loads(x) for x in (bvd.O3 / 'log.jsonl').read_text().splitlines() if '"run"' in x and '"F2_' in x][0]
    est = bvd.estimate(o3)
    windows = {}
    for key, x in est.items():
        w = run['windows'][key]
        om = 2 * np.pi * x['f_drive_hz']
        z_ext = 220 / (1 + 1j * om * 220 * c_term)
        e = {c: np.median(v, axis=0) for c, v in env[key].items()}
        windows[key] = {'scored': w['scored'], 'paired_ratio': w['down']['paired_ratio'],
                        'paired_iqr': w['down']['paired_iqr'], 'tx2_alone_ratio_pred': x['ratio_open_alone'],
                        'f_shift_hz': w.get('f_shift_hz'), 'df_tx2_alone_pred_hz': x['df_open_alone_hz'],
                        'chb_open_over_grounded': w.get('chb_open_over_grounded'),
                        'chb_ratio_pred': 1 / (om * c_term) / abs(z_ext),
                        'chb_env_ratio_on_grid': dict(zip(map(str, GRID_MS), (e['open'] / e['grounded']).round(2).tolist()))}
    result = {'status': 'post hoc, not preregistered', 'script_sha256': rc.sha256(Path(__file__).resolve()),
              'run_id': entry['run_id'], 'held_high_open_n': len(taus),
              'tx2_terminal_C_nF': 1e9 * c_term, 'discharge_tau_ms': [1e3 * min(taus), 1e3 * max(taus)],
              'fz_release_ms': {'median': 1e3 * float(np.median(released)), 'min': 1e3 * min(released),
                                'max': 1e3 * max(released)},
              'foff_high_hold_ms': {'n': len(holds), 'median': 1e3 * float(np.median(holds)),
                                    'min': 1e3 * min(holds), 'max': 1e3 * max(holds)},
              'windows': windows}
    (OUT / 'posthoc_result.json').write_text(json.dumps(result, indent=1) + '\n')
    print(f'TX2 terminal: {result["tx2_terminal_C_nF"]:.2f} nF from {len(taus)} held-high open stops '
          f'(tau {result["discharge_tau_ms"][0]:.2f}-{result["discharge_tau_ms"][1]:.2f} ms at 1 MOhm); Fz releases '
          f'{result["fz_release_ms"]["median"]:.3f} ms ({result["fz_release_ms"]["min"]:.3f}-'
          f'{result["fz_release_ms"]["max"]:.3f}) after the last pulse; Foff holds a HIGH pin '
          f'{result["foff_high_hold_ms"]["median"]:.3f} ms (n {len(holds)})')
    for key, w in windows.items():
        print(f'  {key}: paired {w["paired_ratio"]:.3f} vs TX2 alone {w["tx2_alone_ratio_pred"]:.3f} | '
              f'f shift {w["f_shift_hz"]:.1f} vs {w["df_tx2_alone_pred_hz"]:.1f} Hz | Ch B o/g '
              f'{w["chb_open_over_grounded"]:.2f} vs {w["chb_ratio_pred"]:.2f} | Ch B env o/g at '
              f'{"/".join(map(str, GRID_MS))} ms: {"/".join(map(str, w["chb_env_ratio_on_grid"].values()))}'
              f'{"" if w["scored"] else " (not scored)"}')


if __name__ == '__main__':
    main()
