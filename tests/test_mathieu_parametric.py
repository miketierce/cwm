"""Tests for simulations/mathieu_parametric.py (Sidebar 16)."""

import numpy as np
import pytest

from simulations.mathieu_parametric import (
    # Constants
    _L_DEFAULT,
    _Q_DEFAULT,
    _T_DEFAULT,
    _F_FUND,
    _V_BAR,
    # Helpers
    _mode_frequency,
    _parametric_gain_rate,
    _epsilon_threshold,
    _parametric_gain_below_threshold,
    _parametric_gain_db,
    _instability_tongue_width,
    _fsr,
    _pump_power_per_mode,
    _time_domain_mathieu,
    _measure_gain_from_timeseries,
    _numerical_epsilon_threshold,
    # Dataclasses
    ParametricGainResult,
    ModeSelectivityResult,
    StabilityBoundaryResult,
    ParametricCWResult,
    MathieuParametricSummary,
    # Experiments
    exp_parametric_gain,
    exp_mode_selectivity,
    exp_stability_boundary,
    exp_parametric_cw_readout,
    run_all_mathieu,
)
from simulations.common import C_FERROFLUID, K_B


# =========================================================================
# Core physics helpers
# =========================================================================


class TestModeFrequency:
    """Tests for mode frequency computation."""

    def test_fundamental(self):
        f1 = _mode_frequency(1)
        expected = C_FERROFLUID / (2 * _L_DEFAULT)
        assert f1 == pytest.approx(expected)

    def test_harmonic_ratio(self):
        f1 = _mode_frequency(1)
        f5 = _mode_frequency(5)
        assert f5 == pytest.approx(5 * f1)

    def test_positive(self):
        assert _mode_frequency(1) > 0

    def test_custom_length(self):
        f = _mode_frequency(1, L=1e-4)
        assert f == pytest.approx(C_FERROFLUID / (2e-4))


class TestGainRate:
    """Tests for parametric gain rate γ."""

    def test_at_threshold(self):
        Q = 500.0
        eps = 2.0 / Q
        omega = 2 * np.pi * 1e6
        gamma = _parametric_gain_rate(eps, omega, Q)
        assert gamma == pytest.approx(0.0, abs=1e-6)

    def test_below_threshold_negative(self):
        Q = 500.0
        gamma = _parametric_gain_rate(0.001, 2 * np.pi * 1e6, Q)
        assert gamma < 0

    def test_above_threshold_positive(self):
        Q = 500.0
        gamma = _parametric_gain_rate(0.01, 2 * np.pi * 1e6, Q)
        assert gamma > 0

    def test_zero_epsilon(self):
        # Pure damping
        Q = 500.0
        omega = 2 * np.pi * 1e6
        gamma = _parametric_gain_rate(0.0, omega, Q)
        assert gamma == pytest.approx(-omega / (2 * Q))


class TestEpsilonThreshold:
    """Tests for critical modulation depth."""

    def test_formula(self):
        assert _epsilon_threshold(500.0) == pytest.approx(0.004)

    def test_high_Q_lower_threshold(self):
        assert _epsilon_threshold(10000.0) < _epsilon_threshold(500.0)

    def test_positive(self):
        assert _epsilon_threshold(100.0) > 0

    def test_inversely_proportional(self):
        ratio = _epsilon_threshold(200.0) / _epsilon_threshold(1000.0)
        assert ratio == pytest.approx(5.0)


class TestParametricGain:
    """Tests for parametric gain calculations."""

    def test_below_threshold_finite(self):
        G = _parametric_gain_below_threshold(0.001, 500.0)
        assert np.isfinite(G)
        assert G > 1.0

    def test_at_threshold_infinite(self):
        eps = _epsilon_threshold(500.0)
        G = _parametric_gain_below_threshold(eps, 500.0)
        assert np.isinf(G)

    def test_above_threshold_infinite(self):
        G = _parametric_gain_below_threshold(0.01, 500.0)
        assert np.isinf(G)

    def test_zero_epsilon_unity(self):
        G = _parametric_gain_below_threshold(0.0, 500.0)
        assert G == pytest.approx(1.0)

    def test_gain_db_positive(self):
        db = _parametric_gain_db(0.003, 500.0)
        assert db > 0

    def test_gain_db_zero_epsilon(self):
        db = _parametric_gain_db(0.0, 500.0)
        assert db == pytest.approx(0.0, abs=1e-6)

    def test_gain_increases_with_epsilon(self):
        g1 = _parametric_gain_db(0.001, 500.0)
        g2 = _parametric_gain_db(0.002, 500.0)
        g3 = _parametric_gain_db(0.003, 500.0)
        assert g3 > g2 > g1


class TestTongueWidth:
    """Tests for instability tongue width."""

    def test_formula(self):
        omega = 2 * np.pi * 1e6
        f = 1e6
        eps = 0.01
        expected = eps * f / 2
        assert _instability_tongue_width(eps, omega) == pytest.approx(expected)

    def test_proportional_to_epsilon(self):
        omega = 2 * np.pi * 1e6
        w1 = _instability_tongue_width(0.01, omega)
        w2 = _instability_tongue_width(0.02, omega)
        assert w2 == pytest.approx(2 * w1)

    def test_zero_epsilon(self):
        assert _instability_tongue_width(0.0, 1e6) == pytest.approx(0.0)


class TestFSR:
    """Tests for free spectral range."""

    def test_default(self):
        expected = C_FERROFLUID / (2 * _L_DEFAULT)
        assert _fsr() == pytest.approx(expected)

    def test_shorter_cavity_larger_fsr(self):
        assert _fsr(L=5e-6) > _fsr(L=1e-5)


class TestPumpPower:
    """Tests for pump power estimation."""

    def test_positive(self):
        omega = 2 * np.pi * 1e6
        assert _pump_power_per_mode(omega, 500.0) > 0

    def test_proportional_to_epsilon(self):
        omega = 2 * np.pi * 1e6
        p1 = _pump_power_per_mode(omega, 500.0, epsilon=0.01)
        p2 = _pump_power_per_mode(omega, 500.0, epsilon=0.02)
        assert p2 == pytest.approx(2 * p1)

    def test_femtowatt_scale(self):
        omega = 2 * np.pi * 350e6
        p = _pump_power_per_mode(omega, 500.0, epsilon=0.003)
        p_fW = p * 1e15
        assert 0.001 < p_fW < 100  # sub-100 fW range


class TestTimeDomain:
    """Tests for Mathieu equation integration."""

    def test_returns_tuple(self):
        omega = 2 * np.pi * 1e6
        t, x, v = _time_domain_mathieu(0.0, omega, 500.0, n_cycles=10)
        assert len(t) == len(x) == len(v)
        assert len(t) > 0

    def test_no_pump_decays(self):
        omega = 2 * np.pi * 1e6
        t, x, v = _time_domain_mathieu(0.0, omega, 500.0, n_cycles=200)
        # Without parametric drive, amplitude should decay
        assert abs(x[-1]) < abs(x[0])

    def test_above_threshold_grows(self):
        Q = 500.0
        omega = 2 * np.pi * 1e6
        eps = 0.01  # well above 2/Q = 0.004
        t, x, _ = _time_domain_mathieu(eps, omega, Q, n_cycles=50)
        dt = t[1] - t[0]
        gain = _measure_gain_from_timeseries(x, omega, dt)
        assert gain > 1.0

    def test_initial_conditions(self):
        omega = 2 * np.pi * 1e6
        t, x, v = _time_domain_mathieu(0.0, omega, 500.0, n_cycles=5)
        assert x[0] == pytest.approx(1.0)
        assert v[0] == pytest.approx(0.0)


class TestNumericalThreshold:
    """Tests for numerical threshold finder."""

    def test_close_to_analytic(self):
        Q = 500.0
        omega = 2 * np.pi * _mode_frequency(5)
        eps_num = _numerical_epsilon_threshold(omega, Q, n_cycles=500)
        eps_analytic = _epsilon_threshold(Q)
        # Should be within 30% (numerical has finite precision)
        assert abs(eps_num - eps_analytic) / eps_analytic < 0.30

    def test_positive(self):
        omega = 2 * np.pi * 1e6
        eps = _numerical_epsilon_threshold(omega, 500.0, n_cycles=200)
        assert eps > 0

    def test_lower_Q_higher_threshold(self):
        omega = 2 * np.pi * 1e6
        eps_lo_Q = _numerical_epsilon_threshold(omega, 200.0, n_cycles=200)
        eps_hi_Q = _numerical_epsilon_threshold(omega, 1000.0, n_cycles=200)
        assert eps_lo_Q > eps_hi_Q


# =========================================================================
# Experiment functions
# =========================================================================


class TestParametricGainExp:
    """Tests for exp_parametric_gain (H-PM1)."""

    def test_returns_correct_type(self):
        r = exp_parametric_gain()
        assert isinstance(r, ParametricGainResult)

    def test_gain_positive(self):
        r = exp_parametric_gain()
        assert r.gain_db > 0

    def test_gain_finite(self):
        r = exp_parametric_gain()
        assert np.isfinite(r.gain_db)

    def test_verdict_is_bool(self):
        r = exp_parametric_gain()
        assert isinstance(r.verdict, bool)

    def test_pump_power_less_than_bekesy(self):
        r = exp_parametric_gain()
        assert r.pump_power_fW < r.bekesy_power_fW

    def test_epsilon_stored(self):
        r = exp_parametric_gain(epsilon=0.002)
        assert r.epsilon == 0.002

    def test_higher_epsilon_higher_gain(self):
        r1 = exp_parametric_gain(epsilon=0.001)
        r2 = exp_parametric_gain(epsilon=0.003)
        assert r2.gain_db > r1.gain_db

    def test_freq_correct(self):
        r = exp_parametric_gain(n_mode=3)
        expected = _mode_frequency(3)
        assert r.freq_hz == pytest.approx(expected)


class TestModeSelectivityExp:
    """Tests for exp_mode_selectivity (H-PM2)."""

    def test_returns_correct_type(self):
        r = exp_mode_selectivity()
        assert isinstance(r, ModeSelectivityResult)

    def test_target_gain_exceeds_neighbour(self):
        r = exp_mode_selectivity()
        assert r.gain_target_db > r.gain_neighbour_max_db

    def test_verdict_is_bool(self):
        r = exp_mode_selectivity()
        assert isinstance(r.verdict, bool)

    def test_selectivity_ratio_positive(self):
        r = exp_mode_selectivity()
        assert r.selectivity_ratio > 1.0

    def test_tongue_narrower_than_fsr(self):
        r = exp_mode_selectivity()
        assert r.tongue_width_hz < r.fsr_hz

    def test_n_target_stored(self):
        r = exp_mode_selectivity(n_target=10)
        assert r.n_target == 10

    def test_higher_Q_better_selectivity(self):
        r_lo = exp_mode_selectivity(Q=200.0, epsilon=0.003)
        r_hi = exp_mode_selectivity(Q=2000.0, epsilon=0.0003)
        assert r_hi.selectivity_ratio > r_lo.selectivity_ratio


class TestStabilityBoundaryExp:
    """Tests for exp_stability_boundary (H-PM3)."""

    def test_returns_correct_type(self):
        r = exp_stability_boundary()
        assert isinstance(r, StabilityBoundaryResult)

    def test_predicted_positive(self):
        r = exp_stability_boundary()
        assert r.epsilon_predicted > 0

    def test_numerical_positive(self):
        r = exp_stability_boundary()
        assert r.epsilon_numerical > 0

    def test_deviation_finite(self):
        r = exp_stability_boundary()
        assert np.isfinite(r.deviation_percent)

    def test_verdict_is_bool(self):
        r = exp_stability_boundary()
        assert isinstance(r.verdict, bool)

    def test_Q_stored(self):
        r = exp_stability_boundary(Q=300.0)
        assert r.Q == 300.0

    def test_freq_stored(self):
        r = exp_stability_boundary()
        assert r.freq_hz > 0


class TestParametricCWExp:
    """Tests for exp_parametric_cw_readout (H-PM4)."""

    def test_returns_correct_type(self):
        r = exp_parametric_cw_readout()
        assert isinstance(r, ParametricCWResult)

    def test_combined_exceeds_cw(self):
        r = exp_parametric_cw_readout()
        assert r.snr_parametric_cw_db > r.snr_cw_only_db

    def test_improvement_equals_par_gain(self):
        r = exp_parametric_cw_readout()
        assert r.improvement_db == pytest.approx(r.parametric_gain_db)

    def test_verdict_is_bool(self):
        r = exp_parametric_cw_readout()
        assert isinstance(r.verdict, bool)

    def test_improvement_positive(self):
        r = exp_parametric_cw_readout()
        assert r.improvement_db > 0

    def test_t_integration_stored(self):
        r = exp_parametric_cw_readout(t_integration=5e-3)
        assert r.t_integration == 5e-3

    def test_finite_values(self):
        r = exp_parametric_cw_readout()
        assert np.isfinite(r.snr_cw_only_db)
        assert np.isfinite(r.snr_parametric_cw_db)
        assert np.isfinite(r.improvement_db)


# =========================================================================
# Runner / Integration
# =========================================================================


class TestRunner:
    """Tests for run_all_mathieu."""

    def test_returns_summary(self):
        s = run_all_mathieu(verbose=False)
        assert isinstance(s, MathieuParametricSummary)

    def test_counts_add_up(self):
        s = run_all_mathieu(verbose=False)
        assert s.confirmed + s.killed == 4

    def test_all_sub_results_present(self):
        s = run_all_mathieu(verbose=False)
        assert isinstance(s.gain, ParametricGainResult)
        assert isinstance(s.selectivity, ModeSelectivityResult)
        assert isinstance(s.stability, StabilityBoundaryResult)
        assert isinstance(s.parametric_cw, ParametricCWResult)

    def test_verbose_runs(self, capsys):
        run_all_mathieu(verbose=True)
        captured = capsys.readouterr()
        assert "Mathieu" in captured.out
        assert "H-PM1" in captured.out


class TestPhysics:
    """Cross-checks on physical consistency."""

    def test_threshold_formula(self):
        # ε_min = 2/Q exactly
        for Q in [100, 500, 1000, 5000]:
            assert _epsilon_threshold(Q) == pytest.approx(2.0 / Q)

    def test_gain_diverges_at_threshold(self):
        Q = 500.0
        eps = _epsilon_threshold(Q) - 1e-10
        G = _parametric_gain_below_threshold(eps, Q)
        assert G > 1000  # near-divergence

    def test_pump_below_bekesy(self):
        # Parametric pump should be cheaper than Békésy feedback
        r = exp_parametric_gain()
        assert r.pump_power_fW < r.bekesy_power_fW

    def test_selectivity_grows_with_Q(self):
        # Higher Q → narrower tongue relative to FSR → better selectivity
        r1 = exp_mode_selectivity(Q=200.0, epsilon=0.003)
        r2 = exp_mode_selectivity(Q=1000.0, epsilon=0.0006)
        assert r2.selectivity_ratio > r1.selectivity_ratio


class TestEdgeCases:
    """Edge-case parameter sweeps."""

    def test_mode_one(self):
        r = exp_parametric_gain(n_mode=1)
        assert np.isfinite(r.gain_db)

    def test_high_mode(self):
        r = exp_parametric_gain(n_mode=50)
        assert np.isfinite(r.gain_db)

    def test_very_high_Q(self):
        r = exp_parametric_gain(Q=10000.0, epsilon=0.0001)
        assert np.isfinite(r.gain_db)
        assert r.gain_db > 0

    def test_very_low_Q(self):
        r = exp_parametric_gain(Q=50.0, epsilon=0.01)
        assert np.isfinite(r.gain_db)

    def test_zero_epsilon_no_gain(self):
        r = exp_parametric_gain(epsilon=0.0)
        assert r.gain_db == pytest.approx(0.0, abs=0.01)

    def test_selectivity_mode_one(self):
        r = exp_mode_selectivity(n_target=1)
        assert r.gain_target_db > r.gain_neighbour_max_db
