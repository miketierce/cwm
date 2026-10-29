#!/usr/bin/env python3
"""O3 direct ringdown, with ring-up alongside, on Plate D (exploratory; preregistered in
docs/lab_diary_20261029.md §1 before any data).

One run covers one TX path, with Ch B on that path's TX junction:
  1. live check at the path's check frequency (Ch B sees the drive, |H| in the expected range)
  2. QUIET: 10 ring-length captures with the drive off (envelope noise floor)
  3. zoom sweep: every distinct NCO frequency within +-400 Hz of the path's 6 overnight windows, 2 repeats,
     random order, at the FT-1 settings (3072 samples, 40 ms settle). Each window is fitted with
     overnight_20261026/fit_zoom.py (complex H = zA/zB). The drive frequency is the NCO command nearest the
     fitted f0, or the zoom peak when the fit misses the overnight cuts.
  4. timing qualification at 65 kHz (not scored): the cycles below, which set the Foff delay
  5. per window, in random order, cycles of
       ring-up    the scope is armed on Ch B rising through 1 V with 10% pre-trigger, then the drive starts
       ringdown   after >= 150 ms of drive a free-running block starts and Foff follows after an adapted
                  delay; the stop is located on Ch B, and the capture is kept if it lies 0.5-2.0 ms in
     until 10 ringdowns are kept or 60 cycles have run.

Ring captures are 3968 samples (5.08 ms at 781.25 kS/s), the 2204A's limit with both channels on: its 8k
buffer is shared between channels. Every capture is saved: raw int8 under
data/raw/k_eff/<this folder>/<run>.npz (gitignored), capture metadata and zoom coefficients in <run>.npz
here, and one line per run in log.jsonl. Scoring: score_ring.py.

    python3 data/results/k_eff/ringdown_20261029/ring_capture.py --path F1 --label "TX1 path"
    python3 data/results/k_eff/ringdown_20261029/ring_capture.py --path F2 --label "TX2 path"
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

FIT_ZOOM = REPO / 'data/results/k_eff/overnight_20261026/fit_zoom.py'
_spec = importlib.util.spec_from_file_location('fit_zoom', FIT_ZOOM)
fz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fz)

RAW = REPO / 'data/raw/k_eff' / OUT.name
PORT = '/dev/cu.usbmodem113401'
RANGE_MV = 5000
K = RANGE_MV / 32767
DUTY = 100
SETTLE = 0.04
N_QUIET = 10
ZOOM_HZ = 400
ZOOM_REPEATS = 2
WINDOWS = {'F2': (73500, 90500, 97000, 105000, 106000, 116500),
           'F1': (45000, 58500, 90500, 97000, 99500, 103000)}
CHECKS = {'F2': (60_000, 0.04, 0.2), 'F1': (58_500, 0.5, 5.0)}
N_RING = 3968             # per channel with both channels on (ps2000_get_timebase max at timebase 7)
TRIG_MV = 1000
PRE_PCT = 10
AUTO_MS = 500
UP_TOL_S = 0.1e-3
SILENCE_S = 0.12
HOLD_S = 0.15
ARM_S = 0.05
STOP_WINDOW_MS = (0.5, 2.0)
STOP_TARGET_MS = 1.25
EDGE_STEP_S = 0.002       # delay step when the stop falls before or after the block
QUAL_HZ = 65_000
N_QUAL = 15
N_DOWN = 10
MAX_CYCLES = 60


def log(entry: dict) -> None:
    with (OUT / 'log.jsonl').open('a') as fh:
        fh.write(json.dumps(entry) + '\n')


def distinct_freqs(lo: int, hi: int) -> list[int]:
    """One command per distinct NCO frequency in [lo, hi]."""
    cmds = {}
    for f in range(lo, hi + 1):
        cmds.setdefault(pio_actual_freq(f), f)
    return [cmds[k] for k in sorted(cmds)]


def nearest_cmd(f0: float) -> int:
    """The NCO command whose actual frequency is closest to f0."""
    return min(range(int(f0) - 150, int(f0) + 151), key=lambda c: abs(pio_actual_freq(c) - f0))


def rising_edges(b: np.ndarray, thr: int) -> np.ndarray:
    """Sample indices where Ch B rises through thr: one per detected drive pulse."""
    above = np.asarray(b) >= thr
    return np.flatnonzero(above[1:] & ~above[:-1]) + 1


def classify_up(b: np.ndarray, thr: int, fs: float, fa: float) -> tuple[str, int | None]:
    """Ring-up: no pulse before the trigger point, the first one at it, steady pulses after. Returns (status, i0)."""
    n, per = len(b), fs / fa
    e = rising_edges(b, thr)
    if not len(e):
        return 'no_drive', None
    i0 = int(e[0])
    if np.any(np.asarray(b[:i0]) >= thr):
        return 'pre_pulse', i0
    if abs(i0 - round(PRE_PCT / 100 * n)) > UP_TOL_S * fs:
        return 'off_trigger', i0
    if len(e) < 0.5 * (n - i0) / per:
        return 'gappy', i0
    return 'ok', i0


def classify_down(b: np.ndarray, thr: int, fs: float, fa: float) -> tuple[str, float | None]:
    """Ringdown: pulses from the block start to a stop inside it. Returns (status, t_stop in s).

    t_stop is the last detected pulse plus half a drive period. 'early': the stop came before the block,
    'late': still driving at its end, 'outside': located but not within STOP_WINDOW_MS.
    """
    n, per = len(b), fs / fa
    e = rising_edges(b, thr)
    if not len(e):
        return 'early', None
    if e[-1] > n - 2 * per:
        return 'late', None
    t_stop = (e[-1] + 0.5 * per) / fs
    if e[0] > 3 * per or len(e) < 0.5 * e[-1] / per:
        return 'gappy', t_stop
    lo, hi = STOP_WINDOW_MS
    return ('ok' if lo <= 1e3 * t_stop <= hi else 'outside'), t_stop


def window_fit(f: np.ndarray, h: np.ndarray, centre: int) -> dict:
    """fit_zoom.fit on one zoom window of complex H, with the overnight usability cuts."""
    o = np.argsort(f)
    fit = fz.fit(f[o], h[o], centre, 'lin' if len(f) >= 10 else 'const')
    fit['usable_f0'] = bool(fit['in_window'] and fit['se_f0'] <= fz.MAX_SE_F0_HZ and fit['rel_rms'] <= fz.MAX_REL_RMS)
    fit['usable_Q'] = bool(fit['usable_f0'] and fit['se_lnQ'] <= fz.MAX_SE_LNQ)
    return fit


def wait(s: float) -> None:
    """Busy-wait: time.sleep is too coarse for millisecond scheduling."""
    end = time.perf_counter() + s
    while time.perf_counter() < end:
        pass


def ring_block(bench, trigger: int | None = None, action=None, delay: float = 0.0):
    """One N_RING-sample block on both channels, or None if the scope never finished.

    trigger: Ch B threshold in counts (rising, PRE_PCT pre-trigger, AUTO_MS fallback); None = free-running.
    action runs delay s after the block is started, or -delay s before it when delay < 0.
    """
    ps, ct, h = bench.ps, bench.ct, bench.h
    args = (5, 0, 0, 0, 0) if trigger is None else (1, trigger, 0, -PRE_PCT, AUTO_MS)
    if not ps.ps2000_set_trigger(h, *args):
        raise RuntimeError(f'ps2000_set_trigger rejected {args}')
    ba, bb, ov, tk = (ct.c_int16 * N_RING)(), (ct.c_int16 * N_RING)(), ct.c_int16(), ct.c_int32()
    if action and delay < 0:
        action()
        wait(-delay)
    ps.ps2000_run_block(h, N_RING, TIMEBASE, 1, ct.byref(tk))
    if action and delay >= 0:
        wait(delay)
        action()
    end = time.perf_counter() + 2.0
    while not ps.ps2000_ready(h):
        if time.perf_counter() > end:
            ps.ps2000_stop(h)
            return None
        time.sleep(0.0005)
    got = ps.ps2000_get_values(h, ct.byref(ba), ct.byref(bb), None, None, ct.byref(ov), N_RING)
    if got != N_RING:
        raise RuntimeError(f'scope returned {got} samples, expected {N_RING}')
    return np.array(ba[:], np.int16), np.array(bb[:], np.int16), int(ov.value)


def start_channel(bench, ch: str) -> None:
    bench.query('Foff')
    bench.query(f'A{ch[1:]}:{DUTY}')
    time.sleep(0.2)


def measure(bench, ch: str, f_cmd: int) -> dict:
    """One FT-1-style capture (3072 samples) at f_cmd after the settle time."""
    reply = bench.query(f'{ch}:{f_cmd}')
    if not reply.startswith('DDS'):
        raise RuntimeError(f'NCO rejected {ch}:{f_cmd}: {reply!r}')
    time.sleep(SETTLE)
    ca, cb, ov = bench.capture()
    fa = pio_actual_freq(f_cmd)
    clip = CLIP_FRACTION * 32512
    return {'t': time.time(), 'f_cmd': f_cmd, 'f_act': fa, 'zA': demod(ca * K, fa, bench.fs),
            'zB': demod(cb * K, fa, bench.fs), 'ovf': int(ov), 'clipA': int(np.abs(ca).max() >= clip),
            'clipB': int(np.abs(cb).max() >= clip), 'A': ca, 'B': cb}


def live_check(bench, ch: str) -> dict:
    f, lo, hi = CHECKS[ch]
    start_channel(bench, ch)
    m = measure(bench, ch, f)
    bench.query('Foff')
    h = m['zA'] / m['zB'] if abs(m['zB']) > 0 else 0j
    return {'ch': ch, 'f_hz': f, 'chA_mV': round(abs(m['zA']), 2), 'chB_mV': round(abs(m['zB']), 2),
            'H': round(abs(h), 4), 'phase_deg': round(float(np.degrees(np.angle(h))), 1),
            'ok': bool(lo < abs(h) < hi and abs(m['zB']) > 100)}


def cycle(bench, ch: str, f_cmd: int, thr: int, delay: float, arm: float) -> tuple:
    """Ring-up (scope armed, then the drive starts) and ringdown (free-running block, Foff after delay)."""
    bench.query('Foff')
    time.sleep(SILENCE_S)
    t_on = []

    def start():
        t_on.append(time.perf_counter())
        bench.nco.write(f'{ch}:{f_cmd}\n'.encode())

    bench.nco.reset_input_buffer()
    up = ring_block(bench, trigger=thr, action=start, delay=arm)
    reply = bench.nco.readline().decode(errors='replace').strip()
    if not reply.startswith('DDS'):
        raise RuntimeError(f'NCO rejected {ch}:{f_cmd}: {reply!r}')
    left = HOLD_S - (time.perf_counter() - t_on[0])
    if left > 0:
        time.sleep(left)
    bench.nco.reset_input_buffer()
    down = ring_block(bench, action=lambda: bench.nco.write(b'Foff\n'), delay=delay)
    reply = bench.nco.readline().decode(errors='replace').strip()
    if reply != 'DDS:0':
        raise RuntimeError(f'NCO did not confirm Foff: {reply!r}')
    return up, down


class Rings:
    """Ring-up/ringdown cycles with the Foff delay and arming time adapted from Ch B."""

    def __init__(self, bench, ch: str, fs: float, thr: int, delay_s: float):
        self.bench, self.ch, self.fs, self.thr = bench, ch, fs, thr
        self.delay, self.arm, self.offsets = delay_s, ARM_S, []
        self.meta, self.A, self.B = [], [], []
        self.clip = CLIP_FRACTION * 32512

    def record(self, kind: str, key: str, f_cmd: int, k: int, cap, status: str, edge_s, extra: dict) -> bool:
        if cap is None:
            ca = cb = np.zeros(N_RING, np.int16)
            ov, status = -1, 'timeout'
        else:
            ca, cb, ov = cap
        bad = bool(ov != 0 or np.abs(ca).max() >= self.clip or np.abs(cb).max() >= self.clip)
        self.A.append(ca)
        self.B.append(cb)
        self.meta.append({'kind': kind, 'target': key, 'f_cmd': f_cmd, 'f_act': pio_actual_freq(f_cmd), 'cycle': k,
                          'status': status, 'edge_s': np.nan if edge_s is None else float(edge_s),
                          'ovf': int(ov), 'clipA': int(np.abs(ca).max() >= self.clip),
                          'clipB': int(np.abs(cb).max() >= self.clip), 't': time.time(),
                          'arm_s': extra.get('arm_s', np.nan), 'delay_s': extra.get('delay_s', np.nan)})
        return status == 'ok' and not bad

    def run(self, key: str, f_cmd: int, n_max: int, keep: int | None, prefix: str = '') -> dict:
        fa = pio_actual_freq(f_cmd)
        start_channel(self.bench, self.ch)
        kept = good_up = 0
        sd_all, su_all = [], []
        for k in range(n_max):
            arm, delay = self.arm, self.delay
            up, down = cycle(self.bench, self.ch, f_cmd, self.thr, delay, arm)
            su, i0 = classify_up(up[1], self.thr, self.fs, fa) if up else ('timeout', None)
            sd, ts = classify_down(down[1], self.thr, self.fs, fa) if down else ('timeout', None)
            good_up += self.record(f'{prefix}up', key, f_cmd, k, up, su, None if i0 is None else i0 / self.fs,
                                   {'arm_s': arm})
            kept += self.record(f'{prefix}down', key, f_cmd, k, down, sd, ts, {'delay_s': delay})
            su_all.append(su)
            sd_all.append(sd)
            if su == 'pre_pulse':
                self.arm = min(self.arm + 0.02, 0.3)
            if sd in ('ok', 'outside', 'gappy'):
                self.offsets.append(ts - delay)
                self.delay = float(np.clip(STOP_TARGET_MS / 1e3 - np.median(self.offsets[-9:]), -0.05, 0.2))
            elif sd == 'early':
                self.delay += EDGE_STEP_S
            elif sd == 'late':
                self.delay -= EDGE_STEP_S
            if keep and kept >= keep:
                break
        self.bench.query('Foff')
        count = lambda s: {x: s.count(x) for x in sorted(set(s))}  # noqa: E731
        out = {'f_cmd': f_cmd, 'f_act': round(fa, 3), 'cycles': len(sd_all), 'kept_down': kept, 'ok_up': good_up,
               'down': count(sd_all), 'up': count(su_all), 'delay_end_ms': round(1e3 * self.delay, 3),
               'arm_end_s': round(self.arm, 3)}
        print(f'  {key}: {f_cmd} Hz, {out["cycles"]} cycles, {kept} ringdowns kept, {good_up} ring-ups ok, '
              f'down {out["down"]}, delay {out["delay_end_ms"]} ms', flush=True)
        return out


def run(a) -> None:
    ch = a.path
    rng = np.random.default_rng(a.seed)
    run_id = f'{ch}_{datetime.now():%Y%m%d_%H%M%S}'
    script = Path(__file__).resolve()
    bench = Bench(a.nco_port, RANGE_MV, RANGE_MV)
    ct = bench.ct
    bench.ps.ps2000_set_trigger.argtypes = [ct.c_int16] * 6
    bench.ps.ps2000_set_trigger.restype = ct.c_int16
    ti, tu, ms = ct.c_int32(), ct.c_int16(), ct.c_int32()
    if not bench.ps.ps2000_get_timebase(bench.h, TIMEBASE, N_RING, ct.byref(ti), ct.byref(tu), 0, ct.byref(ms)):
        bench.close(ch)
        raise SystemExit(f'The scope rejects {N_RING}-sample blocks at timebase {TIMEBASE}')
    fs = 1e9 / ti.value
    thr = round(TRIG_MV / RANGE_MV * 32767)
    started = datetime.now(timezone.utc).isoformat()
    quiet, zoom = [], []
    rings = Rings(bench, ch, fs, thr, a.delay_ms / 1e3)
    try:
        temp_start = bench.query('TEMP')
        status = bench.query('STATUS')
        check = live_check(bench, ch)
        print(f'live check: {check}', flush=True)
        if not check['ok']:
            raise SystemExit(f'Live check failed: is Ch B on the {ch} TX junction? {check}')
        time.sleep(0.2)
        for _ in range(N_QUIET):
            q = ring_block(bench)
            if q is None:
                raise RuntimeError('the scope timed out on a QUIET block')
            quiet.append(q)
        start_channel(bench, ch)
        plan = [(c, f) for c in WINDOWS[ch] for f in distinct_freqs(c - ZOOM_HZ, c + ZOOM_HZ)] * ZOOM_REPEATS
        for i in rng.permutation(len(plan)):
            c, f = plan[i]
            zoom.append({**measure(bench, ch, f), 'center': c})
        bench.query('Foff')
        print(f'zoom: {len(zoom)} captures', flush=True)

        fits = {}
        for c in WINDOWS[ch]:
            z = [r for r in zoom if r['center'] == c and not (r['ovf'] or r['clipA'] or r['clipB'])]
            if len(z) < 5:
                fits[f'{ch}:{c}'] = {'usable_f0': False, 'usable_Q': False, 'drive_cmd': c,
                                     'drive_basis': f'window centre ({len(z)} clean zoom points)'}
                continue
            f = np.array([r['f_act'] for r in z])
            h = np.array([r['zA'] / r['zB'] for r in z])
            try:
                fit = window_fit(f, h, c)
            except (AttributeError, ValueError, np.linalg.LinAlgError) as e:
                fit = {'usable_f0': False, 'usable_Q': False, 'fit_error': repr(e)}
            peak = z[int(np.argmax(np.abs(h)))]['f_cmd']
            fit['drive_cmd'] = nearest_cmd(fit['f0']) if fit['usable_f0'] else int(peak)
            fit['drive_basis'] = 'fitted f0' if fit['usable_f0'] else 'zoom peak'
            fits[f'{ch}:{c}'] = fit
            print(f'  {ch}:{c}: f0 {fit.get("f0", np.nan):.1f} Hz, Q {fit.get("Q", np.nan):.0f}, '
                  f'usable f0/Q {fit["usable_f0"]}/'
                  f'{fit["usable_Q"]}, drive {fit["drive_cmd"]} ({fit["drive_basis"]})', flush=True)

        print('qualification at 65 kHz (not scored):', flush=True)
        qual = rings.run(f'qual:{QUAL_HZ}', QUAL_HZ, N_QUAL, None, prefix='qual_')
        offsets_ms = 1e3 * np.array(rings.offsets)
        qual['offset_ms'] = ({'median': round(float(np.median(offsets_ms)), 3),
                              'p10': round(float(np.percentile(offsets_ms, 10)), 3),
                              'p90': round(float(np.percentile(offsets_ms, 90)), 3)} if len(offsets_ms) else None)
        print('targets:', flush=True)
        targets = {}
        for i in rng.permutation(len(WINDOWS[ch])):
            key = f'{ch}:{WINDOWS[ch][i]}'
            targets[key] = rings.run(key, fits[key]['drive_cmd'], MAX_CYCLES, N_DOWN)
        temp_end = bench.query('TEMP')
    finally:
        bench.close(ch)

    RAW.mkdir(parents=True, exist_ok=True)
    raw_file = RAW / f'{run_id}.npz'
    np.savez_compressed(raw_file, ring_A=pack_raw(np.stack(rings.A)), ring_B=pack_raw(np.stack(rings.B)),
                        quiet_A=pack_raw(np.stack([q[0] for q in quiet])),
                        quiet_B=pack_raw(np.stack([q[1] for q in quiet])),
                        zoom_A=pack_raw(np.stack([r['A'] for r in zoom])),
                        zoom_B=pack_raw(np.stack([r['B'] for r in zoom])),
                        mv_per_count_A=K, mv_per_count_B=K, packed_scale=256)
    meta_file = OUT / f'{run_id}.npz'
    cols = ('kind', 'target', 'f_cmd', 'f_act', 'cycle', 'status', 'edge_s', 'ovf', 'clipA', 'clipB', 't',
            'arm_s', 'delay_s')
    zcols = ('center', 'f_cmd', 'f_act', 'zA', 'zB', 'ovf', 'clipA', 'clipB', 't')
    np.savez_compressed(meta_file, **{c: np.array([m[c] for m in rings.meta]) for c in cols},
                        **{f'zoom_{c}': np.array([r[c] for r in zoom]) for c in zcols},
                        quiet_ovf=np.array([q[2] for q in quiet]))
    entry = {'event': 'run', 'run_id': run_id, 'path': ch, 'label': a.label, 'started_utc': started,
             'ended_utc': datetime.now(timezone.utc).isoformat(),
             'wiring': {'chA': 'preamp output', 'chB': f'{ch} TX junction (PZT terminal, after 220 ohm)'},
             'settings': {'range_mV': RANGE_MV, 'duty_permille': DUTY, 'sample_rate_hz': fs, 'n_ring': N_RING,
                          'trigger_mV': TRIG_MV, 'pre_trigger_pct': PRE_PCT, 'silence_s': SILENCE_S,
                          'hold_s': HOLD_S, 'stop_window_ms': STOP_WINDOW_MS, 'off_state': 'pins LOW (Foff)'},
             'live_check': check, 'nco_status_start': status, 'nco_temp_start': temp_start, 'nco_temp_end': temp_end,
             'zoom_fits': fits, 'qualification': qual, 'targets': targets, 'seed': a.seed,
             'raw_file': rel(raw_file), 'raw_sha256': sha256(raw_file),
             'meta_file': rel(meta_file), 'meta_sha256': sha256(meta_file),
             'script': rel(script), 'script_sha256': sha256(script), 'fit_zoom_sha256': sha256(FIT_ZOOM),
             'capture_tool_sha256': sha256(REPO / 'tools/k_eff_ft1_capture.py'), 'git': git_state(),
             'ambient_temp_c': a.ambient_temp_c, 'rails_v': a.rails, 'notes': a.notes}
    log(entry)
    print(f'{run_id}: {len(rings.meta)} ring captures -> {rel(raw_file)}', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--path', required=True, choices=sorted(WINDOWS), help='driven TX path; Ch B on its junction')
    ap.add_argument('--label', required=True)
    ap.add_argument('--seed', type=int, default=20261029)
    ap.add_argument('--delay-ms', type=float, default=5.0, help='starting Foff delay after the block starts')
    ap.add_argument('--ambient-temp-c', type=float, help='manual air temperature next to the plate')
    ap.add_argument('--rails', help='measured rails, e.g. "+9.4/-9.4"')
    ap.add_argument('--notes', default='')
    ap.add_argument('--nco-port', default=PORT)
    run(ap.parse_args())


if __name__ == '__main__':
    main()
