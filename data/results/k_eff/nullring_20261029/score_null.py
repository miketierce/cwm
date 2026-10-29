#!/usr/bin/env python3
"""Scores the two-TX null ringdown run (preregistered in docs/lab_diary_20261029.md §5).

Per kept capture (S2 and N: stop located on Ch B, 0.5-2.0 ms in; S1: stop placed at its delay plus the run's
median scope offset), with z(t) = score_ring.envelope of Ch A at the drive frequency:
  - steady state before the stop: Hann DFT of both channels from the block start to 0.05 ms before the stop;
    H = zA/zB against the TX2 drive for S2 and N, |zA| for S1
  - free decay: z(t_stop + t) for t = 0.30-2.50 ms, rotated by the TX2 drive phase (S2, N) so captures add
    coherently; S1 has no TX2 reference and is averaged in magnitude
Per target:
  rho_drive = |mean H_N| / |mean H_S2|                      how deep the receiver null is while driving
  rho_free  = rms|Z_N| / rms|Z_S2| over t = 0.30-1.50 ms    how much the plate rings after the null drive
  modal null   if rho_free <= max(2 rho_drive, 0.04)
  still rings  if rho_free >= max(3 rho_drive, 0.08); indeterminate in between
  superposition: rms(|Z_N - Z_S2| - |Z_S1|) / rms|Z_S1| over the same window, within 0.10
A target is valid if every condition keeps >= 5 captures and rho_drive <= 0.05.

    python3 data/results/k_eff/nullring_20261029/score_null.py
    python3 data/results/k_eff/nullring_20261029/score_null.py --selftest
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
nc = _load('null_capture', OUT / 'null_capture.py')

T_GRID = np.arange(0.30e-3, 2.50e-3 + 1e-9, 0.01e-3)
WIN = (0.30e-3, 1.50e-3)
PRE_END_S = 0.05e-3
MIN_KEPT = 5
RHO_DRIVE_MAX = 0.05
NULL_FLOOR, RING_FLOOR = 0.04, 0.08
SUPER_TOL = 0.10
EXPECTED = {'58510': 'modal null', '90615': 'still rings'}


def capture_metrics(cap: dict, fs: float, fa: float) -> tuple[complex, complex, np.ndarray]:
    """Steady-state zA, zB before the stop and the complex envelope at t_stop + T_GRID."""
    a, b, ts = cap['a_mv'], cap['b_mv'], cap['edge_s']
    m = int((ts - PRE_END_S) * fs)
    z = sr.envelope(a, fa, fs)
    t = np.arange(len(z)) / fs
    free = np.interp(ts + T_GRID, t, z.real) + 1j * np.interp(ts + T_GRID, t, z.imag)
    return rc.demod(a[:m], fa, fs), rc.demod(b[:m], fa, fs), free


def classify(rho_free: float, rho_drive: float) -> str:
    if rho_free <= max(2 * rho_drive, NULL_FLOOR):
        return 'modal null'
    if rho_free >= max(3 * rho_drive, RING_FLOOR):
        return 'still rings'
    return 'indeterminate'


def score_target(caps: list[dict], fs: float, fa: float, sigma_env: float) -> dict:
    by = {c: [x for x in caps if x['cond'] == c and x['kept']] for c in nc.CONDS}
    out = {'kept': {c: len(v) for c, v in by.items()}}
    if min(out['kept'].values()) < MIN_KEPT:
        return {**out, 'valid': False, 'verdict': 'invalid: fewer than 5 captures in a condition'}
    h, z, zb_abs = {}, {}, []
    for c in ('S2', 'N'):
        hs, zs = [], []
        for x in by[c]:
            za, zb, free = capture_metrics(x, fs, fa)
            hs.append(za / zb)
            zs.append(free * np.exp(-1j * np.angle(zb)))
            if c == 'S2':
                zb_abs.append(abs(zb))
        h[c], z[c] = complex(np.mean(hs)), np.mean(zs, axis=0)
    s1 = [capture_metrics(x, fs, fa) for x in by['S1']]
    m1 = np.mean([np.abs(free) for _, _, free in s1], axis=0)
    w = (T_GRID >= WIN[0] - 1e-9) & (T_GRID <= WIN[1] + 1e-9)

    def rms(v):
        return float(np.sqrt(np.mean(np.abs(v[w]) ** 2)))

    rho_drive = abs(h['N']) / abs(h['S2'])
    rho_free = rms(z['N']) / rms(z['S2'])
    sup = rms(np.abs(z['N'] - z['S2']) - m1) / rms(m1)
    at = {f'{t:.1f}': float(abs(z['N'][i]) / abs(z['S2'][i]))
          for t in (0.3, 0.6, 1.0, 1.5, 2.0) for i in [int(np.argmin(np.abs(T_GRID - t * 1e-3)))]}
    return {**out, 'valid': bool(rho_drive <= RHO_DRIVE_MAX), 'rho_drive': rho_drive, 'rho_free': rho_free,
            'verdict': classify(rho_free, rho_drive), 'N_over_S2_at_ms': at,
            'superposition_rel': sup, 'superposition_ok': bool(sup <= SUPER_TOL),
            'noise_floor_rho': sigma_env / np.sqrt(len(by['N'])) / rms(z['S2']),
            'H_S2': [h['S2'].real, h['S2'].imag], 'H_N': [h['N'].real, h['N'].imag],
            'S1_over_S2_steady': float(np.median([abs(za) for za, _, _ in s1]) / (abs(h['S2']) * np.median(zb_abs))),
            'S2_free_rms_mV': rms(z['S2'])}


def score_run(entry: dict) -> dict:
    for key in ('raw', 'meta'):
        got = rc.sha256(REPO / entry[f'{key}_file'])
        if got != entry[f'{key}_sha256']:
            raise SystemExit(f'{entry[f"{key}_file"]}: sha256 differs from the capture-time hash')
    raw, meta = np.load(REPO / entry['raw_file']), np.load(REPO / entry['meta_file'])
    s = entry['settings']
    fs, thr = s['sample_rate_hz'], round(s['trigger_mV'] / s['range_B_mV'] * 32767)

    def counts(name):
        x = raw[name]
        return x.astype(np.int32) * (256 if x.dtype == np.int8 else 1)

    ka, kb = float(raw['mv_per_count_A']), float(raw['mv_per_count_B'])
    ring_a, ring_bc, quiet_a = counts('ring_A') * ka, counts('ring_B'), counts('quiet_A') * ka
    status, offsets = {}, []
    for i, cond in enumerate(meta['cond']):
        if cond != 'S1':
            st, edge = rc.classify_down(ring_bc[i], thr, fs, float(meta['f_act'][i]))
            status[i] = (st, edge)
            if st in ('ok', 'outside', 'gappy'):
                offsets.append(edge - float(meta['delay_s'][i]))
    off = float(np.median(offsets))
    lo, hi = rc.STOP_WINDOW_MS
    targets = {}
    for key in (str(f) for f in nc.TARGETS):
        idx = np.flatnonzero(meta['target'] == key)
        fa = float(meta['f_act'][idx[0]])
        caps = []
        for i in idx:
            bad = bool(meta['ovf'][i] != 0 or meta['clipA'][i] or meta['clipB'][i])
            if meta['cond'][i] == 'S1':
                edge = float(meta['delay_s'][i]) + off
                kept = not bad and lo <= 1e3 * edge <= hi
            else:
                st, edge = status[i]
                kept = st == 'ok' and not bad
            caps.append({'cond': str(meta['cond'][i]), 'a_mv': ring_a[i], 'b_mv': ring_bc[i] * kb,
                         'edge_s': edge, 'kept': kept})
        targets[key] = {**score_target(caps, fs, fa, sr.noise_sigma(quiet_a, fa, fs)), 'f_act_hz': fa,
                        'expected': EXPECTED[key], 'calibration': entry['calibration'][key]}
    return {'targets': targets, 'offset_ms_median': 1e3 * off, 'n_located': len(offsets)}


def selftest() -> None:
    """A planted single mode and a planted doublet through the same code; exits non-zero if either is misread."""
    rng = np.random.default_rng(3)
    fs, n = 781_250.0, rc.N_RING
    t = np.arange(n) / fs
    thr = round(rc.TRIG_MV / nc.RANGE_B_MV * 32767)
    ka, kb = nc.KA, nc.KB

    def quant(x_mv, k):
        return np.clip(np.round(x_mv / k / 256) * 256, -32512, 32512)

    def capture(fd, modes, u, ts, psi, tx2_on):
        x = np.zeros(n)
        for fk, tau, c1, c2 in modes:
            g = 1 / (2 * np.pi * tau)
            amp = (c1 * u[0] + c2 * u[1]) * 1j * g / (fk - fd + 1j * g) * np.exp(1j * psi)
            ss = np.real(amp * np.exp(2j * np.pi * fd * t))
            dec = np.real(amp * np.exp(2j * np.pi * fd * ts) * np.exp((-1 / tau + 2j * np.pi * fk) * (t - ts)))
            x += np.where(t < ts, ss, dec)
        a = quant(x + rng.normal(0, 10.0, n), ka) * ka
        on = (t < ts) & tx2_on
        b = quant(np.where(on & (((t * fd + psi / (2 * np.pi)) % 1.0) < 0.1), 3200.0, 0.0), kb)
        return a, b

    fd = rc.pio_actual_freq(58_510)
    quiet = np.array([quant(rng.normal(0, 10.0, n), ka) * ka for _ in range(5)])
    sigma = sr.noise_sigma(quiet, fd, fs)
    cases = {'single mode': ([(fd - 10, 1.0e-3, 900.0, 400.0), (fd + 3000, 1.5e-3, 45.0, 70.0)], 'modal null'),
             'doublet 60 Hz': ([(fd - 45, 1.6e-3, 260.0, 870.0), (fd + 15, 1.6e-3, 870.0, 260.0)], 'still rings')}
    ok = True
    for name, (modes, want) in cases.items():
        resp = [(c1 * 1j * g / (fk - fd + 1j * g), c2 * 1j * g / (fk - fd + 1j * g))
                for fk, tau, c1, c2 in modes for g in [1 / (2 * np.pi * tau)]]
        u1 = -sum(r[1] for r in resp) / sum(r[0] for r in resp) * (1 + 0.015 * np.exp(1.1j))
        caps = []
        for cond, u in (('S1', (u1, 0)), ('S2', (0, 1)), ('N', (u1, 1))):
            for _ in range(8):
                ts = 1.25e-3 + rng.normal(0, 0.03e-3)
                a, b = capture(fd, modes, u, ts, rng.uniform(0, 2 * np.pi), cond != 'S1')
                if cond == 'S1':
                    edge, kept = ts, True
                else:
                    st, edge = rc.classify_down(b, thr, fs, fd)
                    kept = st == 'ok'
                caps.append({'cond': cond, 'a_mv': a, 'b_mv': b * kb, 'edge_s': edge, 'kept': kept})
        r = score_target(caps, fs, fd, sigma)
        good = r['valid'] and r['verdict'] == want and r['superposition_ok']
        ok &= good
        print(f'  {name}: kept {r["kept"]}, rho_drive {r["rho_drive"]:.4f}, rho_free {r["rho_free"]:.4f} -> '
              f'{r["verdict"]} (want {want}); N/S2 at ms {({k: round(v, 3) for k, v in r["N_over_S2_at_ms"].items()})}; '
              f'superposition {r["superposition_rel"]:.3f}; noise floor {r["noise_floor_rho"]:.4f}  '
              f'{"PASS" if good else "FAIL"}')
    raise SystemExit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    entries = [json.loads(x) for x in (OUT / 'log.jsonl').read_text().splitlines() if x.strip()]
    runs = {e['run_id']: score_run(e) for e in entries if e.get('event') == 'run'}
    result = {'status': 'exploratory, preregistered in docs/lab_diary_20261029.md §5',
              'scoring_sha256': rc.sha256(Path(__file__).resolve()),
              'capture_sha256': rc.sha256(OUT / 'null_capture.py'), 'runs': runs}
    (OUT / 'null_result.json').write_text(json.dumps(result, indent=1, default=str) + '\n')
    for rid, r in runs.items():
        print(f'{rid}: scope offset {r["offset_ms_median"]:.3f} ms over {r["n_located"]} located stops')
        for key, w in r['targets'].items():
            if 'rho_free' not in w:
                print(f'  {key}: {w["verdict"]}  kept {w["kept"]}')
                continue
            print(f'  {key} ({w["f_act_hz"]:.1f} Hz): kept {w["kept"]}, rho_drive {w["rho_drive"]:.4f}, '
                  f'rho_free {w["rho_free"]:.4f} -> {w["verdict"]} (predicted {w["expected"]}), valid {w["valid"]}; '
                  f'N/S2 at ms {({k: round(v, 3) for k, v in w["N_over_S2_at_ms"].items()})}; '
                  f'superposition {w["superposition_rel"]:.3f}; S1/S2 steady {w["S1_over_S2_steady"]:.3f}; '
                  f'noise floor {w["noise_floor_rho"]:.4f}')


if __name__ == '__main__':
    main()
