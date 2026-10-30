#!/usr/bin/env python3
"""O5: does the TX termination after the stop change Plate D's ringdown? (exploratory; preregistered in
docs/lab_diary_20261029.md §9 before any data). Needs NCO firmware v2.1 (Fz).

Same capture as ringdown_20261029/ring_capture.py, with one change: each cycle is run twice, in random order,
differing only in the stop command:
    grounded   Foff  every drive pin driven LOW, so each TX PZT sits across 220 ohm to ground (as in O3)
    open       Fz    every drive pin high-impedance, so each TX PZT is open-circuit
During the drive both conditions are identical (the pins are driven), so the ring-ups are a built-in control.
One run covers one TX path, with Ch B on that path's TX junction:
  1. live check, QUIET x10, zoom sweep of the path's 6 overnight windows (drive at the fitted f0), as in O3
  2. timing qualification at 65 kHz, 15 grounded cycles, not scored
  3. per window, in random order: 10 cycles x {grounded, open}, the two in random order within each cycle
--setup names the physical state (as built; spare PZTs shorted; out of the foam ...) so runs can be compared.

Raw int8 captures go to data/raw/k_eff/<this folder>/<run>.npz (gitignored), metadata to <run>.npz here,
one line per run to log.jsonl. Scoring: score_term.py.

    python3 data/results/k_eff/termination_20261029/term_capture.py --path F2 --setup "as built"
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
from tools.k_eff_ft1_capture import CLIP_FRACTION, TIMEBASE, Bench, git_state, pack_raw, pio_actual_freq, rel, sha256  # noqa: E402

RING = REPO / 'data/results/k_eff/ringdown_20261029/ring_capture.py'
_spec = importlib.util.spec_from_file_location('ring_capture', RING)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

FIRMWARE = REPO / 'tools/pico_nco/main.py'
RAW = REPO / 'data/raw/k_eff' / OUT.name
STOPS = {'grounded': ('Foff', 'DDS:0'), 'open': ('Fz', 'DDS:Z')}
N_CYCLES = 10


def log(entry: dict) -> None:
    with (OUT / 'log.jsonl').open('a') as fh:
        fh.write(json.dumps(entry) + '\n')


def cycle(bench, ch: str, f_cmd: int, thr: int, delay: float, arm: float, stop: str) -> tuple:
    """rc.cycle with the stop command as a parameter: ring-up on the first drive pulse, then the ringdown."""
    cmd, ack = STOPS[stop]
    bench.query('Foff')
    time.sleep(rc.SILENCE_S)
    t_on = []

    def start():
        t_on.append(time.perf_counter())
        bench.nco.write(f'{ch}:{f_cmd}\n'.encode())

    bench.nco.reset_input_buffer()
    up = rc.ring_block(bench, trigger=thr, action=start, delay=arm)
    reply = bench.nco.readline().decode(errors='replace').strip()
    if not reply.startswith('DDS'):
        raise RuntimeError(f'NCO rejected {ch}:{f_cmd}: {reply!r}')
    left = rc.HOLD_S - (time.perf_counter() - t_on[0])
    if left > 0:
        time.sleep(left)
    bench.nco.reset_input_buffer()
    down = rc.ring_block(bench, action=lambda: bench.nco.write(f'{cmd}\n'.encode()), delay=delay)
    reply = bench.nco.readline().decode(errors='replace').strip()
    if reply != ack:
        raise RuntimeError(f'NCO did not confirm {cmd}: {reply!r}')
    return up, down


class Run:
    """Cycles with the Foff/Fz delay and arming time adapted from Ch B, as in rc.Rings."""

    def __init__(self, bench, ch: str, fs: float, thr: int, delay_s: float):
        self.bench, self.ch, self.fs, self.thr = bench, ch, fs, thr
        self.delay, self.arm, self.offsets = delay_s, rc.ARM_S, []
        self.meta, self.A, self.B = [], [], []
        self.clip = CLIP_FRACTION * 32512

    def record(self, cond: str, kind: str, key: str, f_cmd: int, k: int, cap, status: str, edge_s, extra: dict):
        if cap is None:
            ca = cb = np.zeros(rc.N_RING, np.int16)
            ov, status = -1, 'timeout'
        else:
            ca, cb, ov = cap
        self.A.append(ca)
        self.B.append(cb)
        self.meta.append({'cond': cond, 'kind': kind, 'target': key, 'f_cmd': f_cmd, 'f_act': pio_actual_freq(f_cmd),
                          'cycle': k, 'status': status, 'edge_s': np.nan if edge_s is None else float(edge_s),
                          'ovf': int(ov), 'clipA': int(np.abs(ca).max() >= self.clip),
                          'clipB': int(np.abs(cb).max() >= self.clip), 't': time.time(),
                          'arm_s': extra.get('arm_s', np.nan), 'delay_s': extra.get('delay_s', np.nan)})
        return status

    def one(self, cond: str, key: str, f_cmd: int, k: int) -> str:
        fa = pio_actual_freq(f_cmd)
        arm, delay = self.arm, self.delay
        up, down = cycle(self.bench, self.ch, f_cmd, self.thr, delay, arm, cond)
        su, i0 = rc.classify_up(up[1], self.thr, self.fs, fa) if up else ('timeout', None)
        sd, ts = rc.classify_down(down[1], self.thr, self.fs, fa) if down else ('timeout', None)
        self.record(cond, 'up', key, f_cmd, k, up, su, None if i0 is None else i0 / self.fs, {'arm_s': arm})
        self.record(cond, 'down', key, f_cmd, k, down, sd, ts, {'delay_s': delay})
        if su == 'pre_pulse':
            self.arm = min(self.arm + 0.02, 0.3)
        if sd in ('ok', 'outside', 'gappy'):
            self.offsets.append(ts - delay)
            self.delay = float(np.clip(rc.STOP_TARGET_MS / 1e3 - np.median(self.offsets[-9:]), -0.05, 0.2))
        elif sd == 'early':
            self.delay += rc.EDGE_STEP_S
        elif sd == 'late':
            self.delay -= rc.EDGE_STEP_S
        return sd


def run(a) -> None:
    ch = a.path
    rng = np.random.default_rng(a.seed)
    run_id = f'{ch}_{datetime.now():%Y%m%d_%H%M%S}'
    script = Path(__file__).resolve()
    bench = Bench(a.nco_port, rc.RANGE_MV, rc.RANGE_MV)
    ct = bench.ct
    bench.ps.ps2000_set_trigger.argtypes = [ct.c_int16] * 6
    bench.ps.ps2000_set_trigger.restype = ct.c_int16
    ti, tu, ms = ct.c_int32(), ct.c_int16(), ct.c_int32()
    if not bench.ps.ps2000_get_timebase(bench.h, TIMEBASE, rc.N_RING, ct.byref(ti), ct.byref(tu), 0, ct.byref(ms)):
        bench.close(ch)
        raise SystemExit(f'The scope rejects {rc.N_RING}-sample blocks at timebase {TIMEBASE}')
    fs = 1e9 / ti.value
    thr = round(rc.TRIG_MV / rc.RANGE_MV * 32767)
    started = datetime.now(timezone.utc).isoformat()
    quiet, zoom, fits, counts = [], [], {}, {}
    r = Run(bench, ch, fs, thr, a.delay_ms / 1e3)
    try:
        temp_start = bench.query('TEMP')
        status = bench.query('STATUS')
        if 'IDLE:' not in status:
            raise SystemExit(f'NCO firmware has no Fz (STATUS lacks IDLE): flash tools/pico_nco/main.py v2.1. {status}')
        check = rc.live_check(bench, ch)
        print(f'live check: {check}', flush=True)
        if not check['ok']:
            raise SystemExit(f'Live check failed: is Ch B on the {ch} TX junction? {check}')
        time.sleep(0.2)
        for _ in range(rc.N_QUIET):
            q = rc.ring_block(bench)
            if q is None:
                raise RuntimeError('the scope timed out on a QUIET block')
            quiet.append(q)
        rc.start_channel(bench, ch)
        plan = [(c, f) for c in rc.WINDOWS[ch] for f in rc.distinct_freqs(c - rc.ZOOM_HZ, c + rc.ZOOM_HZ)] * rc.ZOOM_REPEATS
        for i in rng.permutation(len(plan)):
            c, f = plan[i]
            zoom.append({**rc.measure(bench, ch, f), 'center': c})
        bench.query('Foff')
        for c in rc.WINDOWS[ch]:
            z = [x for x in zoom if x['center'] == c and not (x['ovf'] or x['clipA'] or x['clipB'])]
            f = np.array([x['f_act'] for x in z])
            h = np.array([x['zA'] / x['zB'] for x in z])
            try:
                fit = rc.window_fit(f, h, c)
            except (AttributeError, ValueError, np.linalg.LinAlgError) as e:
                fit = {'usable_f0': False, 'usable_Q': False, 'fit_error': repr(e)}
            fit['drive_cmd'] = rc.nearest_cmd(fit['f0']) if fit['usable_f0'] else int(z[int(np.argmax(np.abs(h)))]['f_cmd'])
            fit['drive_basis'] = 'fitted f0' if fit['usable_f0'] else 'zoom peak'
            fits[f'{ch}:{c}'] = fit
            print(f'  {ch}:{c}: f0 {fit.get("f0", np.nan):.1f} Hz, Q {fit.get("Q", np.nan):.0f}, drive {fit["drive_cmd"]} '
                  f'({fit["drive_basis"]})', flush=True)
        rc.start_channel(bench, ch)
        qual = [r.one('grounded', f'qual:{rc.QUAL_HZ}', rc.QUAL_HZ, k) for k in range(rc.N_QUAL)]
        print(f'qualification (not scored): {qual.count("ok")}/{rc.N_QUAL} kept, delay {1e3 * r.delay:.3f} ms', flush=True)
        for i in rng.permutation(len(rc.WINDOWS[ch])):
            key = f'{ch}:{rc.WINDOWS[ch][i]}'
            f_cmd = fits[key]['drive_cmd']
            rc.start_channel(bench, ch)
            got = {c: [] for c in STOPS}
            for k in range(N_CYCLES):
                for cond in rng.permutation(list(STOPS)):
                    got[str(cond)].append(r.one(str(cond), key, f_cmd, k))
            bench.query('Foff')
            counts[key] = {c: {s: v.count(s) for s in sorted(set(v))} for c, v in got.items()}
            print(f'  {key}: {f_cmd} Hz, ringdowns {counts[key]}, delay {1e3 * r.delay:.3f} ms', flush=True)
        temp_end = bench.query('TEMP')
        status_end = bench.query('STATUS')
    finally:
        bench.close(ch)

    RAW.mkdir(parents=True, exist_ok=True)
    raw_file = RAW / f'{run_id}.npz'
    np.savez_compressed(raw_file, ring_A=pack_raw(np.stack(r.A)), ring_B=pack_raw(np.stack(r.B)),
                        quiet_A=pack_raw(np.stack([q[0] for q in quiet])),
                        quiet_B=pack_raw(np.stack([q[1] for q in quiet])),
                        zoom_A=pack_raw(np.stack([x['A'] for x in zoom])),
                        zoom_B=pack_raw(np.stack([x['B'] for x in zoom])),
                        mv_per_count_A=rc.K, mv_per_count_B=rc.K, packed_scale=256)
    meta_file = OUT / f'{run_id}.npz'
    cols = ('cond', 'kind', 'target', 'f_cmd', 'f_act', 'cycle', 'status', 'edge_s', 'ovf', 'clipA', 'clipB', 't',
            'arm_s', 'delay_s')
    zcols = ('center', 'f_cmd', 'f_act', 'zA', 'zB', 'ovf', 'clipA', 'clipB', 't')
    np.savez_compressed(meta_file, **{c: np.array([m[c] for m in r.meta]) for c in cols},
                        **{f'zoom_{c}': np.array([x[c] for x in zoom]) for c in zcols},
                        quiet_ovf=np.array([q[2] for q in quiet]))
    offs = 1e3 * np.array(r.offsets)
    entry = {'event': 'run', 'run_id': run_id, 'path': ch, 'setup': a.setup, 'started_utc': started,
             'ended_utc': datetime.now(timezone.utc).isoformat(),
             'wiring': {'chA': 'preamp output', 'chB': f'{ch} TX junction (PZT terminal, after 220 ohm)'},
             'settings': {'range_mV': rc.RANGE_MV, 'duty_permille': rc.DUTY, 'sample_rate_hz': fs, 'n_ring': rc.N_RING,
                          'trigger_mV': rc.TRIG_MV, 'pre_trigger_pct': rc.PRE_PCT, 'silence_s': rc.SILENCE_S,
                          'hold_s': rc.HOLD_S, 'stop_window_ms': rc.STOP_WINDOW_MS,
                          'stops': {c: v[0] for c, v in STOPS.items()}, 'n_cycles': N_CYCLES},
             'live_check': check, 'nco_status_start': status, 'nco_status_end': status_end,
             'nco_temp_start': temp_start, 'nco_temp_end': temp_end, 'zoom_fits': fits, 'counts': counts,
             'qualification_kept': qual.count('ok'), 'seed': a.seed,
             'offset_ms': ({'median': round(float(np.median(offs)), 4), 'p10': round(float(np.percentile(offs, 10)), 4),
                            'p90': round(float(np.percentile(offs, 90)), 4), 'n': int(len(offs))} if len(offs) else None),
             'raw_file': rel(raw_file), 'raw_sha256': sha256(raw_file),
             'meta_file': rel(meta_file), 'meta_sha256': sha256(meta_file),
             'script': rel(script), 'script_sha256': sha256(script), 'ring_capture_sha256': sha256(RING),
             'firmware': rel(FIRMWARE), 'firmware_sha256': sha256(FIRMWARE),
             'capture_tool_sha256': sha256(REPO / 'tools/k_eff_ft1_capture.py'), 'git': git_state(), 'notes': a.notes}
    log(entry)
    print(f'{run_id}: {len(r.meta)} ring captures -> {rel(raw_file)}', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--path', default='F2', choices=sorted(rc.WINDOWS), help='driven TX path; Ch B on its junction')
    ap.add_argument('--setup', required=True, help='physical state, e.g. "as built: spare PZTs open, in foam"')
    ap.add_argument('--seed', type=int, default=20261029)
    ap.add_argument('--delay-ms', type=float, default=9.05, help='starting stop delay (O3 settled at 9.05 ms)')
    ap.add_argument('--notes', default='')
    ap.add_argument('--nco-port', default=rc.PORT)
    run(ap.parse_args())


if __name__ == '__main__':
    main()
