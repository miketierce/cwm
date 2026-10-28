#!/usr/bin/env python3
"""Bench sweeps for the Oct 27 handling map and its undisturbed baseline (exploratory, not an FT-1 session).

One sweep, at the FT-1 settings (+-5V, 10% duty, 40 ms settle):
  - NCO die temperature and a live-plate check on the referenced path
  - QUIET, 10 captures
  - CH2 and CH1 over the frozen 181-point grid, 1 repeat, random order
  - zoom windows: every distinct NCO frequency within +-400 Hz of the overnight run's 6 centres per path
    (the windows fit_zoom.py fits), 2 repeats, random order
  - every WIDE_EVERY-th sweep of a timed run, and on request: every distinct NCO frequency within
    +-1500 Hz of the 10 strongest S3 peaks per path, 1 repeat (O4 doublets)
  - NCO die temperature

Ch B sits on the TX junction named by --ref, so that path gives complex H = zA/zB and the other path
is read from Ch A alone. Each sweep writes sweep_NNN.npz here (demodulated), sweep_NNN.npz under
data/raw/k_eff/<this folder>/ (int8 captures) and one line of log.jsonl, labelled with --label.

    caffeinate -i python3 data/results/k_eff/handling_20261027/bench_sweeps.py --label baseline --interval-min 5 --end 19:00
    python3 data/results/k_eff/handling_20261027/bench_sweeps.py --label "after: RX swap" --sweeps 2

A timed run stops at --end or when STOP exists in this folder; --sweeps N runs N sweeps back to back.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
sys.path.insert(0, str(REPO))
from tools.k_eff_ft1_capture import (CLIP_FRACTION, GRID_FILE, Bench, alias_flags, demod,  # noqa: E402
                                     pack_raw, pio_actual_freq)

RAW = REPO / 'data/raw/k_eff' / OUT.name
S3_SUMMARY = REPO / 'data/results/k_eff/FT1-S3/derived/summary.json'
PORT = '/dev/cu.usbmodem113401'
RANGE_MV = 5000
K = RANGE_MV / 32767
DUTY = 100
SETTLE = 0.04
GRID_REPEATS = 1
ZOOM_REPEATS = 2
N_QUIET = 10
ZOOM_HZ = 400
ZOOM_CENTRES = {'F2': (73500, 90500, 97000, 105000, 106000, 116500),
                'F1': (45000, 58500, 90500, 97000, 99500, 103000)}
WIDE_HZ = 1500
WIDE_MODES = 10
WIDE_EVERY = 6
CHECKS = {'F2': (60_000, 0.04, 0.2), 'F1': (58_500, 0.5, 5.0)}


def log(entry: dict) -> None:
    entry = {'time': datetime.now().isoformat(timespec='seconds'), **entry}
    with (OUT / 'log.jsonl').open('a') as fh:
        fh.write(json.dumps(entry) + '\n')
    print(json.dumps(entry), flush=True)


def distinct_freqs(lo: int, hi: int) -> list[int]:
    """One command per distinct NCO frequency in [lo, hi]."""
    cmds = {}
    for f in range(lo, hi + 1):
        cmds.setdefault(pio_actual_freq(f), f)
    return [cmds[k] for k in sorted(cmds)]


def wide_plan(grid: list[int]) -> dict:
    """Distinct NCO frequencies within +-WIDE_HZ of the WIDE_MODES strongest S3 GLASS peaks per path."""
    states = json.loads(S3_SUMMARY.read_text())['states']
    flagged = set(alias_flags(grid, 781_250.0)[1])
    plan = {}
    for ch in ('F2', 'F1'):
        a = {int(f): v['H_abs_median'] for f, v in states[f'GLASS:{ch}']['per_freq'].items()}
        peaks = [f for f in grid[1:-1] if a[f] > a[f - 500] and a[f] > a[f + 500] and f not in flagged]
        centres = sorted(sorted(peaks, key=lambda f: -a[f])[:WIDE_MODES])
        plan[ch] = {'centres': centres,
                    'freqs': sorted({f for c in centres for f in distinct_freqs(c - WIDE_HZ, c + WIDE_HZ)})}
    return plan


def start_channel(bench, ch: str) -> None:
    bench.query('Foff')
    bench.query(f'A{ch[1:]}:{DUTY}')
    time.sleep(0.2)


def measure(bench, ch: str | None, f_cmd: int) -> dict:
    if ch:
        reply = bench.query(f'{ch}:{f_cmd}')
        if not reply.startswith('DDS'):
            raise RuntimeError(f'NCO rejected {ch}:{f_cmd}: {reply!r}')
    time.sleep(SETTLE)
    ca, cb, ov = bench.capture()
    fa = pio_actual_freq(f_cmd) if ch else 0.0
    za, zb = (demod(ca * K, fa, bench.fs), demod(cb * K, fa, bench.fs)) if ch else (0j, 0j)
    clip = CLIP_FRACTION * 32512
    return {'t': time.time(), 'f_cmd': f_cmd, 'f_act': fa, 'zA': za, 'zB': zb, 'ovf': int(ov),
            'clipA': int(np.abs(ca).max() >= clip), 'clipB': int(np.abs(cb).max() >= clip),
            'A': pack_raw(ca), 'B': pack_raw(cb)}


def live_check(bench, ref: str) -> dict:
    f, lo, hi = CHECKS[ref]
    start_channel(bench, ref)
    m = measure(bench, ref, f)
    bench.query('Foff')
    h = m['zA'] / m['zB'] if abs(m['zB']) > 0 else 0j
    return {'ch': ref, 'f_hz': f, 'chA_mV': round(abs(m['zA']), 2), 'chB_mV': round(abs(m['zB']), 2),
            'H': round(abs(h), 4), 'phase_deg': round(float(np.degrees(np.angle(h))), 1),
            'ok': bool(lo < abs(h) < hi and abs(m['zB']) > 100)}


def shutdown(bench) -> None:
    try:
        bench.query('A2:500')
    finally:
        bench.close('F1')


def stack_raw(arrays: list[np.ndarray]) -> np.ndarray:
    """int8 when every capture packed losslessly, otherwise int16 counts throughout."""
    if all(x.dtype == np.int8 for x in arrays):
        return np.stack(arrays)
    return np.stack([x.astype(np.int16) * (256 if x.dtype == np.int8 else 1) for x in arrays])


def next_index() -> int:
    done = [int(p.stem.split('_')[1]) for p in OUT.glob('sweep_*.npz')]
    return max(done, default=0) + 1


def run_sweep(bench, n: int, label: str, ref: str, grid: list[int], wide: dict | None, rng) -> dict:
    started = datetime.now()
    temp_start = bench.query('TEMP')
    check = live_check(bench, ref)
    recs = [{**measure(bench, None, 0), 'kind': 'quiet', 'ch': '', 'center': 0} for _ in range(N_QUIET)]
    for ch in ('F2', 'F1'):
        start_channel(bench, ch)
        for f in rng.permutation(np.repeat(grid, GRID_REPEATS)):
            recs.append({**measure(bench, ch, int(f)), 'kind': 'grid', 'ch': ch, 'center': 0})
        zoom = [(c, f) for c in ZOOM_CENTRES[ch] for f in distinct_freqs(c - ZOOM_HZ, c + ZOOM_HZ)] * ZOOM_REPEATS
        for i in rng.permutation(len(zoom)):
            c, f = zoom[i]
            recs.append({**measure(bench, ch, int(f)), 'kind': 'zoom', 'ch': ch, 'center': c})
        if wide:
            for f in rng.permutation(wide[ch]['freqs']):
                recs.append({**measure(bench, ch, int(f)), 'kind': 'wide', 'ch': ch, 'center': 0})
        bench.query('Foff')
    temp_end = bench.query('TEMP')

    name = f'sweep_{n:03d}.npz'
    RAW.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(RAW / name, A=stack_raw([r['A'] for r in recs]), B=stack_raw([r['B'] for r in recs]),
                        mv_per_count_A=K, mv_per_count_B=K)
    cols = ('t', 'f_cmd', 'f_act', 'ovf', 'clipA', 'clipB', 'center')
    np.savez_compressed(OUT / name, kind=np.array([r['kind'] for r in recs]), ch=np.array([r['ch'] for r in recs]),
                        zA=np.array([r['zA'] for r in recs]), zB=np.array([r['zB'] for r in recs]),
                        label=np.array(label), ref=np.array(ref), **{c: np.array([r[c] for r in recs]) for c in cols})
    peaks = {}
    for ch in ZOOM_CENTRES:
        for c in ZOOM_CENTRES[ch]:
            z = [r for r in recs if r['kind'] == 'zoom' and r['ch'] == ch and r['center'] == c]
            amp = [abs(r['zA'] / r['zB']) if ch == ref else abs(r['zA']) for r in z]
            peaks[f'{ch}:{c}'] = round(z[int(np.argmax(amp))]['f_act'], 2)
    noise = {}
    for key in ('A', 'B'):
        x = [np.asarray(r[key], float) * (256 if r[key].dtype == np.int8 else 1) * K for r in recs if r['kind'] == 'quiet']
        noise[key] = round(float(np.median([[abs(demod(xi, pio_actual_freq(f), bench.fs)) for f in grid[::5]] for xi in x])), 3)
    return {'sweep': n, 'label': label, 'ref': ref, 'wide': bool(wide),
            'start': started.isoformat(timespec='seconds'), 'end': datetime.now().isoformat(timespec='seconds'),
            'temp_start': temp_start, 'temp_end': temp_end, 'live_check': check, 'n_captures': len(recs),
            'n_ovf': sum(r['ovf'] for r in recs), 'n_clip': sum(r['clipA'] or r['clipB'] for r in recs),
            'quiet_noise_mV': noise, 'zoom_peak_hz': peaks}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--label', required=True)
    ap.add_argument('--ref', default='F2', choices=['F2', 'F1'], help='TX junction Ch B is on')
    ap.add_argument('--sweeps', type=int, help='run this many sweeps back to back, then stop')
    ap.add_argument('--interval-min', type=float, default=5.0, help='timed run: minutes between sweep starts')
    ap.add_argument('--end', help='timed run: local stop time HH:MM')
    ap.add_argument('--wide', action='store_true', help='include the wide sweeps in every sweep')
    a = ap.parse_args()
    if not a.sweeps and not a.end:
        ap.error('give --sweeps or --end')
    end = None
    if a.end:
        hh, mm = map(int, a.end.split(':'))
        end = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
        if end <= datetime.now():
            end += timedelta(days=1)
    grid = json.loads(GRID_FILE.read_text())['freqs_hz']
    wide = wide_plan(grid)
    log({'event': 'start', 'label': a.label, 'ref': a.ref, 'sweeps': a.sweeps, 'end': a.end,
         'interval_min': a.interval_min, 'wide_centres': {ch: p['centres'] for ch, p in wide.items()},
         'wide_points': {ch: len(p['freqs']) for ch, p in wide.items()}})
    rng = np.random.default_rng()
    done, fails, next_start = 0, 0, datetime.now()
    while True:
        if a.sweeps and done >= a.sweeps:
            break
        if end and datetime.now() >= end:
            break
        if (OUT / 'STOP').exists():
            log({'event': 'stop_file'})
            break
        if datetime.now() < next_start:
            time.sleep(min(10.0, (next_start - datetime.now()).total_seconds()))
            continue
        n = next_index()
        use_wide = a.wide or (not a.sweeps and done % WIDE_EVERY == 0)
        try:
            bench = Bench(PORT, RANGE_MV, RANGE_MV)
        except BaseException as e:  # Bench raises SystemExit when the scope does not open
            log({'event': 'bench_open_failed', 'error': repr(e)})
            fails += 1
            if fails >= 3:
                break
            next_start = datetime.now() + timedelta(minutes=1)
            continue
        try:
            summary = run_sweep(bench, n, a.label, a.ref, grid, wide if use_wide else None, rng)
            log({'event': 'sweep', **summary})
            done += 1
            fails = 0 if summary['live_check']['ok'] else fails + 1
        except Exception:
            log({'event': 'sweep_error', 'sweep': n, 'error': traceback.format_exc(limit=3)})
            fails += 1
        finally:
            shutdown(bench)
        if fails >= 3:
            log({'event': 'stopped_after_3_failures'})
            break
        next_start = datetime.now() if a.sweeps else max(next_start + timedelta(minutes=a.interval_min), datetime.now())
    log({'event': 'end', 'label': a.label, 'sweeps_done': done})


if __name__ == '__main__':
    main()
