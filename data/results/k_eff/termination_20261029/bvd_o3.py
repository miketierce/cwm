#!/usr/bin/env python3
"""O5 prediction basis: each TX's share of Plate D's mode loss, from the O3 junction captures
(docs/lab_diary_20261029.md §9, pre-data amendment; written before any O5 data).

Butterworth-Van Dyke picture: near a mode, a TX PZT is C0 in parallel with a motional branch (R_m, L_m, C_m), where
R_m holds every loss except this TX's own load. During the drive the junction carries V_drive at fa, so the motional
current is V_drive / R_m. After Foff that current keeps ringing through Z_ext = 220 ohm || C0, and the junction shows
V_post(0) = |i_m| |Z_ext|. Hence R_m = V_drive |Z_ext| / V_post(0), and this TX's 220 ohm carries the share
f = Re Z_ext / (R_m + Re Z_ext) of the mode's loss. Opened alone, the TX leaves only C0's dielectric loss,
Re Z_open = tan_d / (omega C0), so tau_open / tau_grounded = (R_m + Re Z_ext) / (R_m + Re Z_open), and the free
frequency rises by f0 / (2 omega^2 L_m C0), with L_m = tau (R_m + Re Z_ext) / 2.
O3 drove each path's own TX with Ch B on its junction: F2 gives TX2's share of the F2 modes and F1 gives TX1's share
of the F1 modes. TX1's share of the F2 modes is not measured.

    python3 data/results/k_eff/termination_20261029/bvd_o3.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
O3 = REPO / 'data/results/k_eff/ringdown_20261029'

_spec = importlib.util.spec_from_file_location('score_ring', O3 / 'score_ring.py')
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)
rc = sr.rc

C0_F = 1.2e-9                   # free capacitance of a 10 mm x 1 mm PZT-5A disc (eps_r ~1750); f barely depends on it
R_SERIES = 220.0
TAN_D = 0.02                    # PZT-5A dielectric loss tangent
DRIVE_S = (-0.6e-3, -0.25e-3)   # Ch B envelope before the stop: drive only
POST_S = (0.3e-3, 1.8e-3)       # Ch B ringdown fit after the stop
AGREE = 0.15                    # Ch B and Ch A decays within 15%: Ch B sees the same single mode


def estimate(entry: dict) -> dict:
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
    out = {}
    for c in rc.WINDOWS[entry['path']]:
        key = f'{entry["path"]}:{c}'
        idx = [i for i in np.flatnonzero(meta['target'] == key) if meta['kind'][i] == 'down']
        if not idx:
            continue
        fa = float(meta['f_act'][idx[0]])
        floor = max(sr.NOISE_K * sr.noise_sigma(quiet_a, fa, fs), sr.AMP_FLOOR_STEPS * 256 * ka)
        rows = []
        for i in idx:
            st, ts = rc.classify_down(ring_bc[i], thr, fs, fa)
            if st != 'ok':
                continue
            zb = sr.envelope(ring_bc[i] * kb, fa, fs)
            t = np.arange(len(zb)) / fs - ts
            drive = float(np.median(np.abs(zb[(t >= DRIVE_S[0]) & (t <= DRIVE_S[1])])))
            sel = (t >= POST_S[0]) & (t <= POST_S[1])
            fb = sr.fit_exp(t[sel][::sr.DECIM], zb[sel][::sr.DECIM], False)
            down = sr.score_down(ring_a[i], fa, fs, ts, floor)
            rows.append((drive, abs(fb['D']), fb['tau'], fb['r2'], down['tau'] if down['status'] == 'ok' else np.nan))
        if not rows:
            continue
        v_drive, v_post, tau_b, r2_b, tau_a = (float(np.nanmedian([r[k] for r in rows])) for k in range(5))
        w = 2 * np.pi * fa
        z_ext = R_SERIES / (1 + 1j * w * R_SERIES * C0_F)
        x_c0 = 1 / (w * C0_F)
        re_open = TAN_D * x_c0 / (1 + TAN_D ** 2)
        r_m = v_drive * abs(z_ext) / v_post
        l_m = tau_a * (r_m + z_ext.real) / 2
        out[key] = {'f_drive_hz': fa, 'n': len(rows), 'v_drive_mV': v_drive, 'v_post0_mV': v_post,
                    'tau_chB_ms': 1e3 * tau_b, 'r2_chB': r2_b, 'tau_chA_ms': 1e3 * tau_a,
                    'decays_agree': bool(abs(tau_b / tau_a - 1) <= AGREE),
                    'r_m_ohm': r_m, 're_zext_ohm': z_ext.real, 'share': z_ext.real / (r_m + z_ext.real),
                    'ratio_open_alone_lossless': (r_m + z_ext.real) / r_m,
                    'ratio_open_alone': (r_m + z_ext.real) / (r_m + re_open),
                    'df_open_alone_hz': fa / (2 * w ** 2 * l_m * C0_F),
                    'v_open0_mV': v_post * x_c0 / abs(z_ext)}
    return out


def main():
    entries = [json.loads(x) for x in (O3 / 'log.jsonl').read_text().splitlines() if x.strip()]
    runs = {e['path']: estimate(e) for e in entries if e.get('event') == 'run'}
    result = {'status': 'O5 prediction basis, written before any O5 data (docs/lab_diary_20261029.md §9 amendment)',
              'script_sha256': rc.sha256(Path(__file__).resolve()), 'c0_F': C0_F, 'r_series_ohm': R_SERIES,
              'tan_d': TAN_D, 'runs': runs}
    (OUT / 'bvd_o3.json').write_text(json.dumps(result, indent=1) + '\n')
    for path, windows in runs.items():
        print(f'{path}: share of each mode loss in this TX\'s 220 ohm (Ch B on its junction in O3)')
        for key, x in windows.items():
            print(f'  {key}: V drive/post {x["v_drive_mV"]:.0f}/{x["v_post0_mV"]:.1f} mV, tau Ch B/A '
                  f'{x["tau_chB_ms"]:.2f}/{x["tau_chA_ms"]:.2f} ms ({"agree" if x["decays_agree"] else "differ"}), '
                  f'R_m {x["r_m_ohm"]:.0f} ohm, share {100 * x["share"]:.1f}%, open alone {x["ratio_open_alone"]:.3f} '
                  f'({x["ratio_open_alone_lossless"]:.3f} lossless), df +{x["df_open_alone_hz"]:.0f} Hz, '
                  f'open junction {x["v_open0_mV"]:.0f} mV')


if __name__ == '__main__':
    main()
