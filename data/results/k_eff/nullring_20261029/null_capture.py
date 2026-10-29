#!/usr/bin/env python3
"""Two-TX null with ringdown on Plate D: does an antiphase "erase" empty the mode, or only cancel it at the
receiver? Exploratory; preregistered in docs/lab_diary_20261029.md §5 before any data.

Ch B stays on the TX2 junction (the start wiring). Ch A, on the preamp output, runs at +-2 V so that a small
residual ringdown is not lost in the 8-bit ADC's dead zone (QUIET noise is ~0.3 step at +-5 V). TX1 and TX2
are NCO CH1 and CH2, phase-locked in Block A. Per target frequency:
  1. null calibration, FT-1 captures (3072 samples, 40 ms settle), H = zA/zB against the TX2 drive:
     TX2 alone, then both; TX1's duty and phase are solved, then refined up to 5 times, to cancel TX2 at the
     receiver. TX2 runs at 100 permille, or 200 when TX1 would otherwise need less than 70.
  2. ringdown cycles, 10 per condition, the three conditions in random order within each cycle:
       S1  TX1 alone at the null setting   (no TX2 pulses: the stop is placed from the measured scope offset)
       S2  TX2 alone
       N   both, at the null setting
     Each cycle: Foff, 120 ms of silence, start, 150 ms of drive, a free-running block, and Foff after the
     delay that puts the stop 1.25 ms in (adapted from Ch B, as in ringdown_20261029/ring_capture.py).
A TX2-only qualification at 65 kHz (10 cycles, not scored) sets that delay first.

Raw int8 captures go to data/raw/k_eff/<this folder>/<run>.npz (gitignored), metadata to <run>.npz here,
and one line per run to log.jsonl. Scoring: score_null.py.

    python3 data/results/k_eff/nullring_20261029/null_capture.py
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
sys.path.insert(0, str(REPO))
from tools.k_eff_ft1_capture import (CLIP_FRACTION, TIMEBASE, Bench, demod, git_state, pack_raw,  # noqa: E402
                                     pio_actual_freq, rel, sha256)

RING = REPO / 'data/results/k_eff/ringdown_20261029/ring_capture.py'
_spec = importlib.util.spec_from_file_location('ring_capture', RING)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

RAW = REPO / 'data/raw/k_eff' / OUT.name
RANGE_A_MV, RANGE_B_MV = 2000, 5000
KA, KB = RANGE_A_MV / 32767, RANGE_B_MV / 32767
TARGETS = (58510, 90615)    # O3's drive commands: the 58.5 kHz single mode and the 90.6 kHz suspected doublet
QUAL_HZ = 65_000
N_QUAL = 10
N_CYCLES = 10
CONDS = ('S1', 'S2', 'N')
D2, D2_HIGH, D1_MIN = 100, 200, 70
CAL_REPEATS = 3
CAL_STEPS = 5
NULL_GOAL = 0.015
SETTLE = 0.04


def log(entry: dict) -> None:
    with (OUT / 'log.jsonl').open('a') as fh:
        fh.write(json.dumps(entry) + '\n')


def nco(bench, cmd: str, expect: str) -> str:
    reply = bench.query(cmd)
    if not reply.startswith(expect):
        raise RuntimeError(f'NCO rejected {cmd}: {reply!r}')
    return reply


def setup(bench, d1: int, th: float, d2: int) -> None:
    """Duties and phases, set while every channel is off (A and PH then only store the value)."""
    nco(bench, 'Foff', 'DDS')
    nco(bench, f'A1:{d1}', 'AMP1')
    nco(bench, f'A2:{d2}', 'AMP2')
    nco(bench, f'PH1:{th:.2f}', 'PH1')
    nco(bench, 'PH2:0', 'PH2')


def start(bench, cond: str, f: int) -> None:
    """S1: TX1, S2: TX2, N: both; the second F command restarts both channels together, phase-locked."""
    if cond in ('S1', 'N'):
        nco(bench, f'F1:{f}', 'DDS')
    if cond in ('S2', 'N'):
        nco(bench, f'F2:{f}', 'DDS')


def tx1_factor(d: int) -> complex:
    """TX1's fundamental at duty d permille relative to 100: amplitude sin(pi d), pulse-centre delay pi d."""
    return np.sin(np.pi * d / 1000) / np.sin(np.pi * 0.1) * np.exp(-1j * np.pi * (d / 1000 - 0.1))


def solve(c1: complex, g2: complex) -> tuple[int, float]:
    """TX1 duty and phase (deg) that make its contribution -g2, given c1 = its contribution at 100, 0 deg."""
    s = np.sin(np.pi * 0.1) * abs(g2) / abs(c1)
    d = int(np.clip(round(1000 * np.arcsin(min(s, 1.0)) / np.pi), 10, 500))
    return d, float(np.degrees(np.angle(c1 * tx1_factor(d)) - np.angle(-g2)) % 360)


class Run:
    def __init__(self, bench, fs: float, delay_s: float):
        self.bench, self.fs, self.delay = bench, fs, delay_s
        self.thr = round(rc.TRIG_MV / RANGE_B_MV * 32767)
        self.clip = CLIP_FRACTION * 32512
        self.offsets, self.meta, self.A, self.B, self.calA, self.calB = [], [], [], [], [], []

    def h(self, f: int) -> tuple[complex, bool]:
        """Mean H = zA/zB over CAL_REPEATS captures of the running drive; True if any clipped or overflowed."""
        fa = pio_actual_freq(f)
        time.sleep(SETTLE)
        hs, bad = [], False
        for _ in range(CAL_REPEATS):
            ca, cb, ov = self.bench.capture()
            self.calA.append(ca)
            self.calB.append(cb)
            bad |= bool(ov or np.abs(ca).max() >= self.clip or np.abs(cb).max() >= self.clip)
            hs.append(demod(ca * KA, fa, self.fs) / demod(cb * KB, fa, self.fs))
        return complex(np.mean(hs)), bad

    def calibrate(self, f: int) -> dict:
        d2, out = D2, {'steps': []}
        while True:
            setup(self.bench, 100, 0.0, d2)
            start(self.bench, 'S2', f)
            g2, bad2 = self.h(f)
            th0 = 0.0
            setup(self.bench, 100, th0, d2)
            start(self.bench, 'N', f)
            gb, bad = self.h(f)
            if bad:
                th0 = 180.0
                setup(self.bench, 100, th0, d2)
                start(self.bench, 'N', f)
                gb, bad = self.h(f)
            c1 = (gb - g2) / np.exp(-1j * np.radians(th0))
            d1, th = solve(c1, g2)
            if d1 >= D1_MIN or d2 == D2_HIGH:
                break
            d2 = D2_HIGH
        best = None
        for k in range(CAL_STEPS):
            setup(self.bench, d1, th, d2)
            start(self.bench, 'N', f)
            gn, bad = self.h(f)
            rho = abs(gn) / abs(g2)
            out['steps'].append({'d1': d1, 'phase1_deg': round(th, 2), 'rho': round(rho, 5), 'clip': bad})
            if best is None or rho < best[2]:
                best = (d1, th, rho)
            if rho <= NULL_GOAL:
                break
            c1 = (gn - g2) / (tx1_factor(d1) * np.exp(-1j * np.radians(th)))
            d1, th = solve(c1, g2)
        self.bench.query('Foff')
        out.update({'d1': best[0], 'phase1_deg': round(best[1], 2), 'd2': d2, 'rho_cal': round(best[2], 5),
                    'H_S2': [round(g2.real, 5), round(g2.imag, 5)], 'S2_clip': bad2})
        return out

    def cycle(self, cond: str, f: int):
        nco(self.bench, 'Foff', 'DDS')
        time.sleep(rc.SILENCE_S)
        start(self.bench, cond, f)
        time.sleep(rc.HOLD_S)
        self.bench.nco.reset_input_buffer()
        delay = self.delay
        cap = rc.ring_block(self.bench, action=lambda: self.bench.nco.write(b'Foff\n'), delay=delay)
        reply = self.bench.nco.readline().decode(errors='replace').strip()
        if reply != 'DDS:0':
            raise RuntimeError(f'NCO did not confirm Foff: {reply!r}')
        return cap, delay

    def record(self, cond: str, target: str, f: int, k: int, cap, delay: float) -> str:
        fa = pio_actual_freq(f)
        if cap is None:
            ca = cb = np.zeros(rc.N_RING, np.int16)
            ov, status, edge = -1, 'timeout', None
        else:
            ca, cb, ov = cap
            if cond == 'S1':
                status = 'predicted'
                edge = delay + float(np.median(self.offsets[-9:])) if self.offsets else None
            else:
                status, edge = rc.classify_down(cb, self.thr, self.fs, fa)
                if status in ('ok', 'outside', 'gappy'):
                    self.offsets.append(edge - delay)
                    self.delay = float(np.clip(rc.STOP_TARGET_MS / 1e3 - np.median(self.offsets[-9:]), -0.05, 0.2))
                elif status == 'early':
                    self.delay += rc.EDGE_STEP_S
                elif status == 'late':
                    self.delay -= rc.EDGE_STEP_S
        self.A.append(ca)
        self.B.append(cb)
        self.meta.append({'cond': cond, 'target': target, 'f_cmd': f, 'f_act': fa, 'cycle': k, 'status': status,
                          'edge_s': np.nan if edge is None else float(edge), 'delay_s': delay, 'ovf': int(ov),
                          'clipA': int(np.abs(ca).max() >= self.clip), 'clipB': int(np.abs(cb).max() >= self.clip),
                          't': time.time()})
        return status


def run(a) -> None:
    rng = np.random.default_rng(a.seed)
    run_id = f'null_{datetime.now():%Y%m%d_%H%M%S}'
    script = Path(__file__).resolve()
    bench = Bench(a.nco_port, RANGE_A_MV, RANGE_B_MV)
    ct = bench.ct
    bench.ps.ps2000_set_trigger.argtypes = [ct.c_int16] * 6
    bench.ps.ps2000_set_trigger.restype = ct.c_int16
    ti, tu, ms = ct.c_int32(), ct.c_int16(), ct.c_int32()
    if not bench.ps.ps2000_get_timebase(bench.h, TIMEBASE, rc.N_RING, ct.byref(ti), ct.byref(tu), 0, ct.byref(ms)):
        bench.close('F2')
        raise SystemExit(f'The scope rejects {rc.N_RING}-sample blocks at timebase {TIMEBASE}')
    fs = 1e9 / ti.value
    r = Run(bench, fs, a.delay_ms / 1e3)
    started = datetime.now(timezone.utc).isoformat()
    quiet, cal, counts = [], {}, {}
    try:
        temp_start = bench.query('TEMP')
        status = bench.query('STATUS')
        f, lo, hi = rc.CHECKS['F2']
        setup(bench, 100, 0.0, D2)
        start(bench, 'S2', f)
        h, bad = r.h(f)
        check = {'f_hz': f, 'H': round(abs(h), 4), 'clip': bad, 'ok': bool(lo < abs(h) < hi and not bad)}
        bench.query('Foff')
        print(f'live check (TX2): {check}', flush=True)
        if not check['ok']:
            raise SystemExit(f'Live check failed: is Ch B on the TX2 junction? {check}')
        time.sleep(0.2)
        for _ in range(rc.N_QUIET):
            q = rc.ring_block(bench)
            if q is None:
                raise RuntimeError('the scope timed out on a QUIET block')
            quiet.append(q)
        setup(bench, 100, 0.0, D2)
        qs = [r.record('S2', f'qual:{QUAL_HZ}', QUAL_HZ, k, *r.cycle('S2', QUAL_HZ)) for k in range(N_QUAL)]
        print(f'qualification at 65 kHz (not scored): {qs.count("ok")}/{N_QUAL} kept, '
              f'delay {1e3 * r.delay:.3f} ms', flush=True)
        for f in TARGETS:
            key = f'{f}'
            cal[key] = r.calibrate(f)
            c = cal[key]
            print(f'{key}: null at TX1 {c["d1"]} permille, {c["phase1_deg"]} deg (TX2 {c["d2"]}): '
                  f'rho {c["rho_cal"]:.4f} after {len(c["steps"])} steps', flush=True)
            setup(bench, c['d1'], c['phase1_deg'], c['d2'])
            st = []
            for k in range(N_CYCLES):
                for cond in rng.permutation(CONDS):
                    st.append((cond, r.record(cond, key, f, k, *r.cycle(cond, f))))
            counts[key] = {cond: {s: sum(1 for c_, s_ in st if c_ == cond and s_ == s)
                                  for s in sorted({s_ for c_, s_ in st if c_ == cond})} for cond in CONDS}
            print(f'  {key}: {counts[key]}, delay {1e3 * r.delay:.3f} ms', flush=True)
        temp_end = bench.query('TEMP')
    finally:
        try:
            setup(bench, 500, 0.0, 500)
        finally:
            bench.close('F2')

    RAW.mkdir(parents=True, exist_ok=True)
    raw_file = RAW / f'{run_id}.npz'
    np.savez_compressed(raw_file, ring_A=pack_raw(np.stack(r.A)), ring_B=pack_raw(np.stack(r.B)),
                        quiet_A=pack_raw(np.stack([q[0] for q in quiet])),
                        quiet_B=pack_raw(np.stack([q[1] for q in quiet])),
                        cal_A=pack_raw(np.stack(r.calA)), cal_B=pack_raw(np.stack(r.calB)),
                        mv_per_count_A=KA, mv_per_count_B=KB, packed_scale=256)
    meta_file = OUT / f'{run_id}.npz'
    cols = ('cond', 'target', 'f_cmd', 'f_act', 'cycle', 'status', 'edge_s', 'delay_s', 'ovf', 'clipA', 'clipB', 't')
    np.savez_compressed(meta_file, **{c: np.array([m[c] for m in r.meta]) for c in cols},
                        quiet_ovf=np.array([q[2] for q in quiet]))
    offs = 1e3 * np.array(r.offsets)
    entry = {'event': 'run', 'run_id': run_id, 'started_utc': started,
             'ended_utc': datetime.now(timezone.utc).isoformat(),
             'wiring': {'chA': 'preamp output', 'chB': 'TX2 junction (PZT terminal, after 220 ohm)'},
             'settings': {'range_A_mV': RANGE_A_MV, 'range_B_mV': RANGE_B_MV, 'sample_rate_hz': fs,
                          'n_ring': rc.N_RING, 'trigger_mV': rc.TRIG_MV, 'silence_s': rc.SILENCE_S,
                          'hold_s': rc.HOLD_S, 'stop_window_ms': rc.STOP_WINDOW_MS, 'off_state': 'pins LOW (Foff)'},
             'live_check': check, 'nco_status_start': status, 'nco_temp_start': temp_start, 'nco_temp_end': temp_end,
             'calibration': cal, 'counts': counts, 'seed': a.seed,
             'offset_ms': ({'median': round(float(np.median(offs)), 4), 'p10': round(float(np.percentile(offs, 10)), 4),
                            'p90': round(float(np.percentile(offs, 90)), 4), 'n': int(len(offs))} if len(offs) else None),
             'raw_file': rel(raw_file), 'raw_sha256': sha256(raw_file),
             'meta_file': rel(meta_file), 'meta_sha256': sha256(meta_file),
             'script': rel(script), 'script_sha256': sha256(script), 'ring_capture_sha256': sha256(RING),
             'capture_tool_sha256': sha256(REPO / 'tools/k_eff_ft1_capture.py'), 'git': git_state(),
             'notes': a.notes}
    log(entry)
    print(f'{run_id}: {len(r.meta)} ring captures -> {rel(raw_file)}', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--seed', type=int, default=20261029)
    ap.add_argument('--delay-ms', type=float, default=9.05, help='starting Foff delay (O3 settled at 9.05 ms)')
    ap.add_argument('--notes', default='')
    ap.add_argument('--nco-port', default=rc.PORT)
    run(ap.parse_args())


if __name__ == '__main__':
    main()
