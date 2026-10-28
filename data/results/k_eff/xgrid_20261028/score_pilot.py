#!/usr/bin/env python3
"""Exact-harmonic grid pilot of Oct 28: within-session superposition (preregistered in docs/lab_diary_20261028.md
section 5, before any pilot data).

Scores each pilot session with the frozen FT-1 functions, unchanged (tools/k_eff_ft1_superposition.py:
session_inputs, estimate_h, score; alias_flags from the capture tool): same exclusions, same error definition.
Only the grid differs: xgrid_pilot.json (make_grid.py) instead of the FT-1 grid file. Writes pilot_result.json.

    python3 data/results/k_eff/xgrid_20261028/score_pilot.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
from tools import k_eff_ft1_superposition as sp  # noqa: E402
from tools.k_eff_ft1_capture import alias_flags  # noqa: E402

GRID_FILE = HERE / 'xgrid_pilot.json'
SESSIONS = ['XG-F2-A5', 'XG-F2-A2']
CHANNEL = 'F2'
P1_MEDIAN = 0.025      # all-point median e, every order and session
P2_P90 = 0.05          # 90th-percentile e, every order and session
NOT_CONFIRMED = 0.05   # any all-point median above this (the FT-1 within-session threshold)
MIN_VALID = 0.8
MAX_CLIP = 0.05


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    grid_doc = json.loads(GRID_FILE.read_text())
    grid = grid_doc['freqs_hz']
    out = {'status': 'preregistered pilot, docs/lab_diary_20261028.md section 5', 'grid_sha256': grid_doc['sha256'],
           'superposition_tool_sha256': sha(REPO / 'tools/k_eff_ft1_superposition.py'),
           'capture_tool_sha256': sha(REPO / 'tools/k_eff_ft1_capture.py'),
           'rules': {'p1_median_max': P1_MEDIAN, 'p2_p90_max': P2_P90, 'not_confirmed_median_above': NOT_CONFIRMED,
                     'min_valid_fraction': MIN_VALID, 'max_clip_fraction': MAX_CLIP},
           'sessions': {}}
    ok_p1 = ok_p2 = valid = True
    worst = 0.0
    for s in SESSIONS:
        manifest = json.loads((REPO / 'data/results/k_eff' / s / 'manifest.json').read_text())
        assert manifest['grid']['sha256'] == grid_doc['sha256'], f'{s} was not captured on the pilot grid'
        glass = [b for b in manifest['blocks'] if b['state'] == 'GLASS']
        clip = sum(b['n_clip'] + b['n_overflow'] for b in glass) / sum(b['n_trials'] for b in glass)
        inp = sp.session_inputs(s, grid)
        res = sp.score([inp], CHANNEL, sp.estimate_h([inp], CHANNEL), grid, alias_flags(grid, inp['fs']))
        out['sessions'][s] = {'clip_or_overflow_fraction': clip, 'result': res}
        valid &= clip <= MAX_CLIP
        for key, r in res.items():
            valid &= r['valid_fraction'] >= MIN_VALID
            ok_p1 &= r['e_median'] is not None and r['e_median'] <= P1_MEDIAN
            ok_p2 &= r['e_p90'] is not None and r['e_p90'] <= P2_P90
            worst = max(worst, r['e_median'] or 1.0)
            print(f"{s} {key}: valid {r['n_valid']}/{r['n_eligible']}, e median {r['e_median']:.4f}, p90 {r['e_p90']:.4f}, "
                  f"noise-limited {r['e_noise_median']:.4f}, clip/ovf {100 * clip:.1f}%")
    outcome = ('invalid' if not valid else 'confirmed' if ok_p1 and ok_p2
               else 'not confirmed' if worst > NOT_CONFIRMED else 'partial')
    out.update({'P1': ok_p1, 'P2': ok_p2, 'valid': valid, 'outcome': outcome})
    (HERE / 'pilot_result.json').write_text(json.dumps(out, indent=1) + '\n')
    print(f'P1 {ok_p1}, P2 {ok_p2}, valid {valid}: {outcome}')


if __name__ == '__main__':
    main()
