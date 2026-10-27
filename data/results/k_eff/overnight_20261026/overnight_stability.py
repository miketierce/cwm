#!/usr/bin/env python3
"""Overnight stability run between FT1-S2 and FT1-S3 (2026-10-26/27). Exploratory, not an FT-1 session.

Wiring as left after S2: Ch A -> preamp output, Ch B -> TX2 junction, live RX in.
Waits for the NCO and a live-plate check (CH2 at 60 kHz, |zA/zB| between 0.04 and 0.2; S2: 0.083),
then every INTERVAL_MIN minutes until --end runs one cycle:

  - NCO die temperature and the live-plate check
  - QUIET, 5 captures
  - CH2 and CH1 over the frozen 181-point grid, 2 repeats each, random order. Ch B is the TX2
    reference; on CH1 it only sees leakage, so CH1 is read from Ch A alone.
  - zoom sweeps over the distinct NCO frequencies within +-400 Hz of the 6 strongest S2 peaks
    per path (O4); later cycles track the mode frequencies
  - NCO die temperature

Scope ranges (+-5V), duty (10%) and settle (40 ms) are the FT-1 session settings. Each cycle writes
cycle_NNN.npz here (demodulated), cycle_NNN.npz under data/raw/k_eff/<this folder>/ (int8 captures)
and one line of log.jsonl. Stops at --end, when STOP exists in this folder, or when the NCO is
unplugged after the first cycle.

    caffeinate -i python3 data/results/k_eff/overnight_20261026/overnight_stability.py --end 07:00
"""
from __future__ import annotations

import argparse
import glob
import json
import os
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
S2_SUMMARY = REPO / 'data/results/k_eff/FT1-S2/derived/summary.json'
PORT = '/dev/cu.usbmodem113401'
RANGE_MV = 5000
K = RANGE_MV / 32767
DUTY = 100
SETTLE = 0.04
INTERVAL_MIN = 20
REPEATS = 2
N_QUIET = 5
N_MODES = 6
ZOOM_HZ = 400
ZOOM_MAX_POINTS = 61
CHECK = ('F2', 60_000, 0.04, 0.2)


def find_port() -> str | None:
    """The usual NCO port, or the only USB modem present if the NCO was plugged in elsewhere."""
    if os.path.exists(PORT):
        return PORT
    found = glob.glob('/dev/cu.usbmodem*')
    return found[0] if len(found) == 1 else None


def log(entry: dict) -> None:
    entry = {'time': datetime.now().isoformat(timespec='seconds'), **entry}
    with (OUT / 'log.jsonl').open('a') as fh:
        fh.write(json.dumps(entry) + '\n')
    print(json.dumps(entry), flush=True)


def zoom_freqs(center: int) -> list[int]:
    """One command per distinct NCO frequency within +-ZOOM_HZ, thinned to ZOOM_MAX_POINTS."""
    cmds = {}
    for f in range(center - ZOOM_HZ, center + ZOOM_HZ + 1):
        cmds.setdefault(pio_actual_freq(f), f)
    out = [cmds[k] for k in sorted(cmds)]
    return out[::-(-len(out) // ZOOM_MAX_POINTS)]


def zoom_plan(grid: list[int]) -> dict:
    """The N_MODES strongest S2 GLASS peaks per path, skipping alias-flagged points."""
    states = json.loads(S2_SUMMARY.read_text())['states']
    flagged = set(alias_flags(grid, 781_250.0)[1])
    plan = {}
    for ch in ('F2', 'F1'):
        a = {int(f): v['H_abs_median'] for f, v in states[f'GLASS:{ch}']['per_freq'].items()}
        peaks = [f for f in grid[1:-1] if a[f] > a[f - 500] and a[f] > a[f + 500] and f not in flagged]
        plan[ch] = {f: zoom_freqs(f) for f in sorted(sorted(peaks, key=lambda f: -a[f])[:N_MODES])}
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


def live_check(bench) -> dict:
    ch, f, lo, hi = CHECK
    start_channel(bench, ch)
    m = measure(bench, ch, f)
    bench.query('Foff')
    h = m['zA'] / m['zB'] if abs(m['zB']) > 0 else 0j
    return {'chA_mV': round(abs(m['zA']), 2), 'chB_mV': round(abs(m['zB']), 2), 'H': round(abs(h), 4),
            'phase_deg': round(float(np.degrees(np.angle(h))), 1), 'ok': bool(lo < abs(h) < hi and abs(m['zB']) > 100)}


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


def per_freq(recs: list[dict], ch: str, value) -> dict:
    out = {}
    for r in recs:
        if r['kind'] == 'grid' and r['ch'] == ch and not (r['ovf'] or r['clipA'] or r['clipB']):
            out.setdefault(r['f_cmd'], []).append(value(r))
    return {f: np.mean(v) for f, v in out.items()}


def run_cycle(bench, n: int, grid: list[int], plan: dict, rng, ref: dict | None, h_s2: dict) -> tuple[dict, dict]:
    started = datetime.now()
    temp_start = bench.query('TEMP')
    check = live_check(bench)
    recs = [{**measure(bench, None, 0), 'kind': 'quiet', 'ch': '', 'center': 0} for _ in range(N_QUIET)]
    for ch in ('F2', 'F1'):
        start_channel(bench, ch)
        for f in rng.permutation(np.repeat(grid, REPEATS)):
            recs.append({**measure(bench, ch, int(f)), 'kind': 'grid', 'ch': ch, 'center': 0})
        for center, freqs in plan[ch].items():
            for f in rng.permutation(freqs):
                recs.append({**measure(bench, ch, int(f)), 'kind': 'zoom', 'ch': ch, 'center': center})
        bench.query('Foff')
    temp_end = bench.query('TEMP')

    name = f'cycle_{n:03d}.npz'
    RAW.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(RAW / name, A=stack_raw([r['A'] for r in recs]), B=stack_raw([r['B'] for r in recs]),
                        mv_per_count_A=K, mv_per_count_B=K)
    cols = ('t', 'f_cmd', 'f_act', 'ovf', 'clipA', 'clipB', 'center')
    np.savez_compressed(OUT / name, kind=np.array([r['kind'] for r in recs]), ch=np.array([r['ch'] for r in recs]),
                        zA=np.array([r['zA'] for r in recs]), zB=np.array([r['zB'] for r in recs]),
                        **{c: np.array([r[c] for r in recs]) for c in cols})

    h2 = per_freq(recs, 'F2', lambda r: r['zA'] / r['zB'])
    a1 = per_freq(recs, 'F1', lambda r: abs(r['zA']))
    ref = ref or {'h2': h2, 'a1': a1}
    peaks = {}
    for ch in plan:
        for center in plan[ch]:
            z = [r for r in recs if r['kind'] == 'zoom' and r['ch'] == ch and r['center'] == center]
            amp = [abs(r['zA'] / r['zB']) if ch == 'F2' else abs(r['zA']) for r in z]
            peaks[f'{ch}:{center}'] = round(z[int(np.argmax(amp))]['f_act'], 2)
    noise = {}
    for key in ('A', 'B'):
        x = [np.asarray(r[key], float) * (256 if r[key].dtype == np.int8 else 1) * K for r in recs if r['kind'] == 'quiet']
        noise[key] = round(float(np.median([[abs(demod(xi, pio_actual_freq(f), bench.fs)) for f in grid[::5]] for xi in x])), 3)
    c1 = [f for f in h2 if f in ref['h2']]
    c1a = [f for f in a1 if f in ref['a1']]
    cs2 = [f for f in h2 if f in h_s2]
    summary = {
        'cycle': n, 'start': started.isoformat(timespec='seconds'), 'end': datetime.now().isoformat(timespec='seconds'),
        'temp_start': temp_start, 'temp_end': temp_end, 'check_60k': check, 'n_captures': len(recs),
        'n_ovf': sum(r['ovf'] for r in recs), 'n_clip': sum(r['clipA'] or r['clipB'] for r in recs),
        'quiet_noise_mV': noise,
        'ch2_H_abs_median': round(float(np.median(np.abs(list(h2.values())))), 4),
        'ch2_vs_cycle1': {'ratio_median': round(float(np.median([abs(h2[f] / ref['h2'][f]) for f in c1])), 4),
                          'change_median_pct': round(float(100 * np.median([abs(h2[f] / ref['h2'][f] - 1) for f in c1])), 2)},
        'ch2_vs_S2': {'ratio_median': round(float(np.median([abs(h2[f] / h_s2[f]) for f in cs2])), 4),
                      'change_median_pct': round(float(100 * np.median([abs(h2[f] / h_s2[f] - 1) for f in cs2])), 2)},
        'ch1_zA_vs_cycle1_ratio_median': round(float(np.median([a1[f] / ref['a1'][f] for f in c1a])), 4),
        'zoom_peak_hz': peaks}
    return summary, ref


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--end', default='07:00', help='local stop time HH:MM (next occurrence)')
    a = ap.parse_args()
    now = datetime.now()
    hh, mm = map(int, a.end.split(':'))
    end = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if end <= now:
        end += timedelta(days=1)
    grid = json.loads(GRID_FILE.read_text())['freqs_hz']
    plan = zoom_plan(grid)
    s2 = json.loads(S2_SUMMARY.read_text())['states']['GLASS:F2']['per_freq']
    h_s2 = {int(f): complex(v['H_mean_re'], v['H_mean_im']) for f, v in s2.items()}
    log({'event': 'start', 'end': end.isoformat(timespec='minutes'), 'interval_min': INTERVAL_MIN,
         'zoom_points': {ch: {str(c): len(v) for c, v in p.items()} for ch, p in plan.items()}})
    rng = np.random.default_rng(20261026)
    n, fails, ref, next_start = 0, 0, None, datetime.now()
    while datetime.now() < end:
        if (OUT / 'STOP').exists():
            log({'event': 'stop_file'})
            break
        port = find_port()
        if not port:
            if n:
                log({'event': 'nco_unplugged'})
                break
            time.sleep(60)
            continue
        if datetime.now() < next_start:
            time.sleep(min(30.0, (next_start - datetime.now()).total_seconds()))
            continue
        try:
            bench = Bench(port, RANGE_MV, RANGE_MV)
        except BaseException as e:  # Bench raises SystemExit when the scope does not open
            log({'event': 'bench_open_failed', 'error': repr(e)})
            next_start = datetime.now() + timedelta(minutes=2)
            continue
        try:
            if n == 0:
                check = live_check(bench)
                if not check['ok']:
                    log({'event': 'waiting_for_live_plate', **check})
                    next_start = datetime.now() + timedelta(minutes=2)
                    continue
            n += 1
            summary, ref = run_cycle(bench, n, grid, plan, rng, ref, h_s2)
            log({'event': 'cycle', **summary})
            fails = 0 if summary['check_60k']['ok'] else fails + 1
        except Exception:
            log({'event': 'cycle_error', 'cycle': n, 'error': traceback.format_exc(limit=3)})
            fails += 1
        finally:
            shutdown(bench)
        if fails >= 3:
            log({'event': 'stopped_after_3_failed_cycles'})
            break
        next_start = max(next_start + timedelta(minutes=INTERVAL_MIN), datetime.now())
    log({'event': 'end', 'cycles': n})


if __name__ == '__main__':
    main()
