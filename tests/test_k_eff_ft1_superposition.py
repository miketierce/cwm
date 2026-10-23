"""Synthetic checks for the preregistered FT-1 superposition analysis."""

import numpy as np

from tools.k_eff_ft1_capture import alias_flags
from tools.k_eff_ft1_superposition import estimate_h, score, tier_check

FS = 781_250.0
GRID = list(range(30_000, 120_001, 500))


def h_true(f):
    return 0.3 * np.exp(1j * f / 7_000) * (1 + 0.5 * np.cos(f / 3_000))


def fmt(row, key, value):
    row[f'{key}_re_mV'] = str(value.real)
    row[f'{key}_im_mV'] = str(value.imag)


def session(distortion=0.0, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for f in GRID:
        for _ in range(3):
            zb, zb2, zb3 = (amp * np.exp(1j * rng.uniform(0, 2 * np.pi)) for amp in (500, 300, 250))
            za = h_true(f) * zb
            row = {'channel': 'F2', 'freq_cmd_hz': str(f), 'ovf_A': '0', 'ovf_B': '0', 'clip_A': '0', 'clip_B': '0'}
            fmt(row, 'zA', za)
            fmt(row, 'zB', zb)
            fmt(row, 'zA2', h_true(2 * f) * zb2 + distortion * abs(za) * np.exp(1j * 0.3))
            fmt(row, 'zB2', zb2)
            fmt(row, 'zA3', h_true(3 * f) * zb3)
            fmt(row, 'zB3', zb3)
            rows.append(row)
    noise = {f: 0.1 for f in GRID}
    return {'session': 'T', 'fs': FS, 'rows': rows, 'noise_a': noise, 'noise_b': dict(noise)}


def test_linear_system_predicts_harmonics_exactly():
    s = session()
    res = score([s], 'F2', estimate_h([s], 'F2'), GRID, alias_flags(GRID, FS))

    for key in ('2f', '3f'):
        assert res[key]['e_median'] < 1e-6
        assert res[key]['valid_fraction'] == 1.0
    assert tier_check(res, 0.05)['all_orders_meet']


def test_harmonic_distortion_is_detected():
    s = session(distortion=0.4)
    res = score([s], 'F2', estimate_h([s], 'F2'), GRID, alias_flags(GRID, FS))

    assert res['2f']['e_median'] > 0.2
    assert tier_check(res, 0.05)['per_order']['2f']['exceeds_reject_level']
    assert res['3f']['e_median'] < 1e-6


def test_alias_flagged_points_are_excluded_from_the_primary_score():
    s = session()
    flags = alias_flags(GRID, FS)
    res = score([s], 'F2', estimate_h([s], 'F2'), GRID, flags)

    assert res['2f']['n_points_in_range'] == 61
    assert res['3f']['n_points_in_range'] == 21
    for key, n in (('2f', 2), ('3f', 3)):
        excluded = [p for p in res[key]['points'] if p['excluded']]
        assert all(p['f_hz'] in flags[n] or p['nf_hz'] in flags[1] for p in excluded)
        assert res[key]['n_eligible'] == res[key]['n_points_in_range'] - len(excluded)


def test_heldout_h_from_other_sessions_is_used_without_refitting():
    train, test = session(seed=1), session(seed=2)
    res = score([test], 'F2', estimate_h([train], 'F2'), GRID, alias_flags(GRID, FS))
    assert res['2f']['e_median'] < 1e-6
