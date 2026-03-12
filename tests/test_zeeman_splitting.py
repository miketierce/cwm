"""
Tests for S9 — Zeeman: Perturbation-Induced Level Splitting
============================================================

Hypotheses: H-Z1 through H-Z4
"""

import numpy as np
import pytest

from simulations.zeeman_splitting import (
    # Helpers
    _golden_positions,
    _sensitivity_matrix,
    _mode_pair_splitting,
    _g_eff_predicted,
    _near_degenerate_pairs,
    _all_mode_pairs,
    _fit_linear_r_squared,
    _fit_quadratic_r_squared,
    _linewidth,
    _multi_site_splitting,
    # Experiments
    exp_splitting_ratio,
    exp_selection_rule,
    exp_quadratic_zeeman,
    exp_multi_site,
    # Result types
    SplittingRatioResult,
    SelectionRuleResult,
    QuadraticZeemanResult,
    MultiSiteResult,
    # Runner
    run_all_zeeman,
)


# ═══════════════════════════════════════════════════════════════════════
# Helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Unit tests for all pure helper functions."""

    # --- _golden_positions ---

    def test_golden_positions_count(self):
        assert len(_golden_positions(6)) == 6

    def test_golden_positions_in_unit_interval(self):
        pos = _golden_positions(10)
        assert np.all(pos >= 0.02)
        assert np.all(pos <= 0.98)

    def test_golden_positions_unique(self):
        pos = _golden_positions(8)
        assert len(set(pos)) == 8

    def test_golden_positions_low_discrepancy(self):
        """Points should be reasonably spread out."""
        pos = np.sort(_golden_positions(10))
        gaps = np.diff(pos)
        assert np.std(gaps) < 0.15

    # --- _sensitivity_matrix ---

    def test_sensitivity_matrix_shape(self):
        pos = _golden_positions(4)
        S = _sensitivity_matrix(pos, 20)
        assert S.shape == (20, 4)

    def test_sensitivity_matrix_nonneg(self):
        pos = _golden_positions(5)
        S = _sensitivity_matrix(pos, 10)
        assert np.all(S >= 0.0)
        assert np.all(S <= 1.0)

    def test_sensitivity_matrix_sin_squared(self):
        pos = np.array([0.25])
        S = _sensitivity_matrix(pos, 3)
        expected = np.sin(np.array([[1], [2], [3]]) * np.pi * 0.25) ** 2
        np.testing.assert_allclose(S, expected, atol=1e-12)

    def test_sensitivity_matrix_boundary_zero(self):
        S0 = _sensitivity_matrix(np.array([0.0]), 5)
        S1 = _sensitivity_matrix(np.array([1.0]), 5)
        np.testing.assert_allclose(S0, 0.0, atol=1e-12)
        np.testing.assert_allclose(S1, 0.0, atol=1e-12)

    # --- _mode_pair_splitting ---

    def test_splitting_zero_at_zero_epsilon(self):
        assert _mode_pair_splitting(3, 4, 0.37, 0.0) == 0.0

    def test_splitting_positive(self):
        assert _mode_pair_splitting(3, 4, 0.37, 0.02) >= 0.0

    def test_splitting_linear_in_epsilon(self):
        """At first order, Δf/f₀ ∝ ε."""
        s1 = _mode_pair_splitting(5, 6, 0.37, 0.01)
        s2 = _mode_pair_splitting(5, 6, 0.37, 0.02)
        np.testing.assert_allclose(s2, 2 * s1, rtol=1e-10)

    def test_splitting_depends_on_position(self):
        s1 = _mode_pair_splitting(3, 4, 0.25, 0.02)
        s2 = _mode_pair_splitting(3, 4, 0.37, 0.02)
        assert s1 != s2

    def test_splitting_at_cavity_center(self):
        """At x_p = 0.5, sin²(nπ/2) has known symmetry."""
        s = _mode_pair_splitting(1, 2, 0.5, 0.01)
        assert s >= 0.0

    # --- _g_eff_predicted ---

    def test_g_eff_nonneg(self):
        assert _g_eff_predicted(3, 4, 0.37) >= 0.0

    def test_g_eff_consistent_with_splitting(self):
        """g_eff should equal splitting at ε = 1."""
        eps = 1.0
        g = _g_eff_predicted(5, 6, 0.37)
        s = _mode_pair_splitting(5, 6, 0.37, eps)
        np.testing.assert_allclose(s, g, rtol=1e-10)

    def test_g_eff_varies_with_mode(self):
        g1 = _g_eff_predicted(1, 2, 0.37)
        g2 = _g_eff_predicted(5, 6, 0.37)
        # Different pairs should generally have different g_eff
        # (not guaranteed, but very likely with these indices)
        assert g1 != g2

    # --- _near_degenerate_pairs ---

    def test_near_degenerate_pairs_count(self):
        pairs = _near_degenerate_pairs(10, max_delta_n=2)
        expected = 9 + 8  # |n-m|=1: 9 pairs; |n-m|=2: 8 pairs
        assert len(pairs) == expected

    def test_near_degenerate_pairs_constraint(self):
        pairs = _near_degenerate_pairs(10, max_delta_n=3)
        for n, m in pairs:
            assert 1 <= m - n <= 3

    def test_near_degenerate_pairs_ordered(self):
        pairs = _near_degenerate_pairs(10, max_delta_n=2)
        for n, m in pairs:
            assert n < m

    # --- _all_mode_pairs ---

    def test_all_mode_pairs_count(self):
        pairs = _all_mode_pairs(10)
        assert len(pairs) == 45  # C(10,2)

    def test_all_mode_pairs_ordered(self):
        for n, m in _all_mode_pairs(8):
            assert n < m

    # --- _fit_linear_r_squared ---

    def test_fit_linear_perfect(self):
        x = np.linspace(0, 1, 20)
        y = 3 * x + 1
        assert _fit_linear_r_squared(x, y) > 0.999

    def test_fit_linear_noise(self):
        rng = np.random.RandomState(42)
        x = np.linspace(0, 1, 50)
        y = 2 * x + rng.normal(0, 0.01, 50)
        assert _fit_linear_r_squared(x, y) > 0.9

    def test_fit_linear_constant(self):
        x = np.linspace(0, 1, 10)
        y = np.full(10, 5.0)
        assert _fit_linear_r_squared(x, y) == 1.0

    # --- _fit_quadratic_r_squared ---

    def test_fit_quadratic_perfect(self):
        x = np.linspace(0, 1, 20)
        y = 2 * x ** 2 + 3 * x + 1
        assert _fit_quadratic_r_squared(x, y) > 0.999

    def test_fit_quadratic_vs_linear(self):
        """Quadratic fit should be at least as good as linear for quadratic data."""
        x = np.linspace(0, 1, 30)
        y = x ** 2 + 0.5 * x + 1
        r2_lin = _fit_linear_r_squared(x, y)
        r2_quad = _fit_quadratic_r_squared(x, y)
        assert r2_quad >= r2_lin

    # --- _linewidth ---

    def test_linewidth_positive(self):
        assert _linewidth(3, 4, 2000.0) > 0

    def test_linewidth_inversely_proportional_to_Q(self):
        lw1 = _linewidth(5, 6, 1000.0)
        lw2 = _linewidth(5, 6, 2000.0)
        np.testing.assert_allclose(lw1, 2 * lw2, rtol=1e-10)

    # --- _multi_site_splitting ---

    def test_multi_site_single_equals_single(self):
        """One site should match _mode_pair_splitting."""
        pos = np.array([0.37])
        s_multi = _multi_site_splitting(5, 6, pos, 0.02)
        s_single = _mode_pair_splitting(5, 6, 0.37, 0.02)
        np.testing.assert_allclose(s_multi, s_single, rtol=1e-10)

    def test_multi_site_more_sites_different(self):
        pos1 = np.array([0.37])
        pos2 = np.array([0.37, 0.73])
        s1 = _multi_site_splitting(5, 6, pos1, 0.02)
        s2 = _multi_site_splitting(5, 6, pos2, 0.02)
        assert s1 != s2


# ═══════════════════════════════════════════════════════════════════════
# H-Z1: Anomalous Splitting Ratio
# ═══════════════════════════════════════════════════════════════════════

class TestSplittingRatio:
    """H-Z1 — Splitting follows linear g-factor in weak field."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_splitting_ratio(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, SplittingRatioResult)

    def test_verdict_is_bool(self, result):
        assert isinstance(result.verdict, bool)

    def test_mean_r_squared_high(self, result):
        assert result.mean_linear_r_squared > 0.9

    def test_g_eff_correlation_high(self, result):
        assert result.g_eff_correlation > 0.7

    def test_splitting_at_zero_is_zero(self, result):
        """First column (ε=0) should be all zeros."""
        np.testing.assert_allclose(result.splitting_matrix[:, 0], 0.0, atol=1e-15)

    def test_splitting_increases_with_epsilon(self, result):
        """Average splitting should increase with ε."""
        mean_per_eps = np.mean(result.splitting_matrix, axis=0)
        assert mean_per_eps[-1] > mean_per_eps[1]

    def test_n_mode_pairs_positive(self, result):
        assert result.n_mode_pairs > 0

    def test_g_eff_per_pair_nonneg(self, result):
        assert np.all(result.g_eff_per_pair >= 0)

    def test_g_eff_predicted_nonneg(self, result):
        assert np.all(result.g_eff_predicted >= 0)

    def test_epsilon_values_start_at_zero(self, result):
        assert result.epsilon_values[0] == 0.0

    def test_seed_reproducibility(self):
        r1 = exp_splitting_ratio(seed=99)
        r2 = exp_splitting_ratio(seed=99)
        assert r1.mean_linear_r_squared == r2.mean_linear_r_squared


# ═══════════════════════════════════════════════════════════════════════
# H-Z2: Selection-Rule Channel Count
# ═══════════════════════════════════════════════════════════════════════

class TestSelectionRule:
    """H-Z2 — Only a constrained subset of mode pairs split significantly."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_selection_rule(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, SelectionRuleResult)

    def test_verdict_is_bool(self, result):
        assert isinstance(result.verdict, bool)

    def test_fraction_bounded(self, result):
        assert 0.0 <= result.fraction_significant <= 1.0

    def test_fraction_below_threshold(self, result):
        assert result.fraction_significant < 0.8

    def test_n_pairs_total_correct(self, result):
        expected = result.n_modes * (result.n_modes - 1) // 2
        assert result.n_pairs_total == expected

    def test_significant_count_bounded(self, result):
        assert 0 <= result.n_pairs_significant <= result.n_pairs_total

    def test_delta_n_values_positive(self, result):
        assert np.all(result.delta_n_values >= 1)

    def test_delta_n_max_observed_positive(self, result):
        assert result.delta_n_max_observed >= 1

    def test_seed_reproducibility(self):
        r1 = exp_selection_rule(seed=77)
        r2 = exp_selection_rule(seed=77)
        assert r1.fraction_significant == r2.fraction_significant


# ═══════════════════════════════════════════════════════════════════════
# H-Z3: Quadratic Zeeman at Strong Perturbation
# ═══════════════════════════════════════════════════════════════════════

class TestQuadraticZeeman:
    """H-Z3 — Splitting deviates from linear at strong perturbation."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_quadratic_zeeman(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, QuadraticZeemanResult)

    def test_verdict_is_bool(self, result):
        assert isinstance(result.verdict, bool)

    def test_mean_linear_r2_below_threshold(self, result):
        assert result.mean_linear_r2_strong < 0.99

    def test_quadratic_improves_over_linear(self, result):
        assert result.mean_quadratic_r2_strong > result.mean_linear_r2_strong

    def test_alpha_coefficients_nonzero(self, result):
        assert np.any(np.abs(result.alpha_coefficients) > 1e-6)

    def test_n_mode_pairs_positive(self, result):
        assert result.n_mode_pairs > 0

    def test_splitting_at_zero_is_finite(self, result):
        """At ε=0, eigenvalue splitting comes from f_n - f_m."""
        assert np.all(np.isfinite(result.splitting_matrix[:, 0]))

    def test_epsilon_range(self, result):
        assert result.epsilon_values[0] == 0.0
        assert result.epsilon_values[-1] == 0.30

    def test_seed_reproducibility(self):
        r1 = exp_quadratic_zeeman(seed=88)
        r2 = exp_quadratic_zeeman(seed=88)
        assert r1.mean_linear_r2_strong == r2.mean_linear_r2_strong


# ═══════════════════════════════════════════════════════════════════════
# H-Z4: Multi-Site Field Geometry
# ═══════════════════════════════════════════════════════════════════════

class TestMultiSite:
    """H-Z4 — K sites resolve ≥ 2K split mode pairs."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_multi_site(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, MultiSiteResult)

    def test_verdict_is_bool(self, result):
        assert isinstance(result.verdict, bool)

    def test_site_counts_sequential(self, result):
        np.testing.assert_array_equal(result.site_counts, np.arange(1, 11))

    def test_n_split_pairs_positive(self, result):
        assert np.all(result.n_split_pairs > 0)

    def test_threshold_2k(self, result):
        np.testing.assert_array_equal(result.threshold_2k, 2 * result.site_counts)

    def test_exceeds_2k_dtype(self, result):
        assert result.exceeds_2k.dtype == bool

    def test_best_k_in_range(self, result):
        assert 1 <= result.best_k <= 10

    def test_best_ratio_positive(self, result):
        assert result.best_ratio > 0

    def test_majority_exceeds(self, result):
        """Majority of K values should exceed 2K threshold."""
        assert np.sum(result.exceeds_2k) > len(result.site_counts) / 2

    def test_seed_reproducibility(self):
        r1 = exp_multi_site(seed=55)
        r2 = exp_multi_site(seed=55)
        np.testing.assert_array_equal(r1.n_split_pairs, r2.n_split_pairs)


# ═══════════════════════════════════════════════════════════════════════
# Integration: run_all_zeeman
# ═══════════════════════════════════════════════════════════════════════

class TestRunAllZeeman:
    """Integration tests for the run_all_zeeman orchestrator."""

    @pytest.fixture(scope="class")
    def results(self):
        return run_all_zeeman(verbose=False)

    def test_returns_dict(self, results):
        assert isinstance(results, dict)

    def test_returns_four_results(self, results):
        assert len(results) == 4

    def test_keys_present(self, results):
        for key in ("H-Z1", "H-Z2", "H-Z3", "H-Z4"):
            assert key in results

    def test_result_types(self, results):
        assert isinstance(results["H-Z1"], SplittingRatioResult)
        assert isinstance(results["H-Z2"], SelectionRuleResult)
        assert isinstance(results["H-Z3"], QuadraticZeemanResult)
        assert isinstance(results["H-Z4"], MultiSiteResult)

    def test_verbose_mode_runs(self, capsys):
        run_all_zeeman(verbose=True)
        captured = capsys.readouterr()
        assert "H-Z1" in captured.out
        assert "S9 SUMMARY" in captured.out

    def test_all_verdicts_are_bool(self, results):
        for r in results.values():
            assert isinstance(r.verdict, bool)
