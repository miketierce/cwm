"""Synthetic checks that the drift decomposition separates gain drift from mode-frequency drift."""

import numpy as np
import pytest

from tools.k_eff_ft1_drift import STEP_HZ, between_session_points, fit_models, per_frequency_drift, session_means

GRID = list(range(30_000, 120_001, STEP_HZ))
MODES = [(41_200, 25), (57_800, 30), (73_400, 40), (96_100, 45), (111_700, 50)]


def h0(f):
    return sum(1 / (1 + 2j * q * (f - f0) / f0) for f0, q in MODES) + 0.05


def rows(gain_per_min=0.0, shift_ppm_per_min=0.0, seed=0, gain=0.0, shift_ppm=0.0):
    rng = np.random.default_rng(seed)
    out = []
    for f in GRID:
        for t_min in np.sort(rng.uniform(0, 4, 20)):
            s = 1e-6 * (shift_ppm + shift_ppm_per_min * t_min)
            h = h0(f / (1 + s)) * (1 + gain) * (1 + gain_per_min * t_min) * (1 + 1e-5 * (rng.normal() + 1j * rng.normal()))
            zb = 500.0
            out.append({'freq_cmd_hz': str(f), 't_unix': str(1e9 + 60 * t_min),
                        'ovf_A': '0', 'ovf_B': '0', 'clip_A': '0', 'clip_B': '0',
                        'zA_re_mV': str((h * zb).real), 'zA_im_mV': str((h * zb).imag),
                        'zB_re_mV': str(zb), 'zB_im_mV': '0'})
    return out


def points(drift):
    pts = []
    for f in GRID[1:-1]:
        lo, hi = drift[f - STEP_HZ]['H'], drift[f + STEP_HZ]['H']
        dln = np.log(abs(hi) / abs(lo)) + 1j * np.angle(hi / lo)
        pts.append({'f': f, 'D': drift[f]['D'], 'se': drift[f]['se'], 'P': f * dln / (2 * STEP_HZ)})
    return pts


def test_uniform_gain_drift_is_attributed_to_gain():
    res = fit_models(points(per_frequency_drift(rows(gain_per_min=-0.001))))
    assert res['gain_plus_shift']['g_mag_pct_per_min'] == pytest.approx(-0.1, abs=0.005)
    assert abs(res['gain_plus_shift']['freq_drift_ppm_per_min']) < 0.5


def test_mode_frequency_shift_is_attributed_to_shift():
    res = fit_models(points(per_frequency_drift(rows(shift_ppm_per_min=20.0))))
    assert res['gain_plus_shift']['freq_drift_ppm_per_min'] == pytest.approx(20.0, rel=0.15)
    assert abs(res['gain_plus_shift']['g_mag_pct_per_min']) < 0.01
    assert res['chi2_reduction_by_shift_term'] > 0.5


def test_between_session_shift_and_gain_are_separated():
    a = session_means(rows(seed=1))
    b = session_means(rows(gain=-0.005, shift_ppm=30.0, seed=2))
    res = fit_models(between_session_points(a, b, GRID[1:-1]), per='')
    assert res['gain_plus_shift']['freq_drift_ppm'] == pytest.approx(30.0, rel=0.15)
    assert res['gain_plus_shift']['g_mag_pct'] == pytest.approx(-0.5, abs=0.05)


def test_between_session_gain_change_shows_no_false_shift():
    a = session_means(rows(seed=1))
    b = session_means(rows(gain=0.01, seed=2))
    res = fit_models(between_session_points(a, b, GRID[1:-1]), per='')
    assert res['gain_plus_shift']['g_mag_pct'] == pytest.approx(100 * np.log(1.01), abs=0.01)
    assert abs(res['gain_plus_shift']['freq_drift_ppm']) < 0.5
