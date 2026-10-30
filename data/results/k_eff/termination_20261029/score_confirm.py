#!/usr/bin/env python3
"""Scores the O5 confirmatory rerun (preregistered in docs/lab_diary_20261029.md §12, before its data).

Same capture (term_capture.py) and the same per-capture and per-window scoring as score_term.py, with the termination
check rescaled to the TX2 terminal capacitance measured in Part A (>= 4.1 nF, §11):
  - Ch B: median open/grounded post-stop ratio >= 1.3 (expected 1.8-2.6 at 4.1 nF; 1.0 if Fz left the pins driven)
  - discharge: >= 3 open ringdowns hold TX2 high after the stop and decay through Ch B's 1 MOhm with tau 3-6 ms,
    and no grounded ringdown does
Predictions (Part A as the prior): C1 median paired ratio < 1.2 ('small'); C1b no scored window above 1.5; C2 ring-up
paired ratios within +-10%; C4 free-decay frequency higher open in every scored window; C5 in every window scored in
both runs, the paired ratio within +-0.05 of Part A's.
Only runs logged after the §12 'prereg_confirm' event are scored; Part A is the reference.

    python3 data/results/k_eff/termination_20261029/score_confirm.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('score_term', OUT / 'score_term.py')
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)
rc = st.rc
st.CHB_CONFIRM = 1.3
R_SCOPE = 1e6
HELD_MV, FIT_MV = 1500, (300, 2600)
TAU_OK_S = (3e-3, 6e-3)
MIN_HELD = 3
REPLICATE_TOL = 0.05


def held_high(entry: dict) -> dict:
    """Ringdowns whose Ch B stays above HELD_MV more than 3 drive periods after the last pulse, by condition."""
    raw, meta = np.load(st.REPO / entry['raw_file']), np.load(st.REPO / entry['meta_file'])
    fs = entry['settings']['sample_rate_hz']
    thr = round(entry['settings']['trigger_mV'] / entry['settings']['range_mV'] * 32767)
    bc = raw['ring_B'].astype(np.int32) * (256 if raw['ring_B'].dtype == np.int8 else 1)
    b_mv = bc * float(raw['mv_per_count_B'])
    out = {'open': [], 'grounded': []}
    for i in np.flatnonzero(meta['kind'] == 'down'):
        edges = rc.rising_edges(bc[i], thr)
        if not len(edges):
            continue
        seg = b_mv[i][edges[-1]:]
        held = np.flatnonzero(seg > HELD_MV)
        if np.sum(held > 3 * fs / float(meta['f_act'][i])) < 5:
            continue
        t = np.arange(len(seg)) / fs
        sel = (seg > FIT_MV[0]) & (seg < FIT_MV[1])
        tau = -1 / np.polyfit(t[sel], np.log(seg[sel]), 1)[0] if sel.sum() > 10 else np.nan
        out[str(meta['cond'][i])].append(float(tau))
    return out


def confirm(entry: dict, ref: dict) -> dict:
    r = st.score_run(entry)
    hh = held_high(entry)
    discharging = [x for x in hh['open'] if TAU_OK_S[0] <= x <= TAU_OK_S[1]]
    discharge_ok = len(discharging) >= MIN_HELD and not any(TAU_OK_S[0] <= x <= TAU_OK_S[1] for x in hh['grounded'])
    v = r['outcome']
    out = {'run_id': entry['run_id'], 'setup': entry['setup'], 'windows': r['windows'],
           'held_high': {'open_tau_ms': [1e3 * x for x in hh['open']], 'grounded_tau_ms': [1e3 * x for x in hh['grounded']],
                         'open_discharging': len(discharging),
                         'terminal_C_nF': 1e9 * float(np.median(discharging)) / R_SCOPE if discharging else None},
           'discharge_ok': bool(discharge_ok), 'score_term_outcome': v}
    if 'P1_small_change' not in v:
        out['verdict'] = v['verdict']
        return out
    if not discharge_ok:
        out['verdict'] = f'open termination not confirmed (discharge check: {len(discharging)} open, need {MIN_HELD})'
        return out
    both = [k for k in v['scored'] if ref['windows'].get(k, {}).get('scored')]
    deltas = {k: r['windows'][k]['down']['paired_ratio'] - ref['windows'][k]['down']['paired_ratio'] for k in both}
    out.update({'verdict': v['verdict'], 'median_paired_ratio': v['median_paired_ratio'],
                'chb_open_over_grounded': v['chb_open_over_grounded'],
                'C1_small_change': v['P1_small_change'], 'C1b_no_window_above_1.5': v['P1b_no_window_above_1.5'],
                'C2_ring_up_control': v['P2_ring_up_control'], 'C4_f_shift_positive': v['P4_f_shift_positive'],
                'C5_replicates_part_a': bool(both and all(abs(d) <= REPLICATE_TOL for d in deltas.values())),
                'replication_delta': deltas, 'window_ratios': v['window_ratios'], 'f_shift_hz': v['f_shift_hz']})
    return out


def main():
    lines = [json.loads(x) for x in (OUT / 'log.jsonl').read_text().splitlines() if x.strip()]
    events = [e['event'] for e in lines]
    if 'prereg_confirm' not in events:
        raise SystemExit('no prereg_confirm event in log.jsonl')
    start = events.index('prereg_confirm')
    runs = [e for e in lines if e.get('event') == 'run']
    part_a = st.score_run(runs[0])
    result = {'status': 'confirmatory, preregistered in docs/lab_diary_20261029.md §12',
              'scoring_sha256': rc.sha256(Path(__file__).resolve()), 'reference': runs[0]['run_id'],
              'runs': [confirm(e, part_a) for e in lines[start:] if e.get('event') == 'run']}
    (OUT / 'confirm_result.json').write_text(json.dumps(result, indent=1, default=str) + '\n')
    for r in result['runs']:
        print(f'{r["run_id"]}: {r["verdict"]}')
        print(json.dumps({k: v for k, v in r.items() if k not in ('windows', 'score_term_outcome')}, indent=1, default=str))


if __name__ == '__main__':
    main()
