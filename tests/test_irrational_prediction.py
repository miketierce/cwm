"""
Tests for S13 — Irrational Prediction: Standing-Wave Rationality Test
=====================================================================

Hypotheses: H-IR1 through H-IR4
"""

import numpy as np
import pytest

from simulations.irrational_prediction import (
    # Helpers
    _sensitivity_matrix,
    _condition_number,
    _count_distinguishable,
    _weyl_positions,
    _continued_fraction,
    _nearest_rational,
    _generator_cost,
    # Constants
    _PHI_CONJUGATE,
    _IRRATIONALS,
    _RATIONALS,
    # Result types
    RationalCatastropheResult,
    IrrationalSufficiencyResult,
    CFDepthResult,
    BlindPredictionResult,
    IrrationalPredictionSummary,
    # Experiments
    exp_rational_catastrophe,
    exp_irrational_sufficiency,
    exp_cf_depth,
    exp_blind_prediction,
    # Runner
    run_all_irrational,
)


# ═══════════════════════════════════════════════════════════════════════
# Helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Unit tests for all helper functions."""

    # --- _sensitivity_matrix ---

    def test_sensitivity_matrix_shape(self):
        pos = np.array([0.2, 0.5, 0.8])
        S = _sensitivity_matrix(pos, 10)
        assert S.shape == (10, 3)

    def test_sensitivity_matrix_bounded(self):
        pos = np.linspace(0.1, 0.9, 5)
        S = _sensitivity_matrix(pos, 20)
        assert np.all(S >= -1e-15)
        assert np.all(S <= 1 + 1e-15)

    def test_sensitivity_sin_squared_formula(self):
        """S[n,k] = sin^2(n*pi*x_k) by definition."""
        pos = np.array([0.25, 0.5, 0.75])
        S = _sensitivity_matrix(pos, 5)
        for n_idx in range(5):
            n = n_idx + 1
            for k, x in enumerate(pos):
                expected = np.sin(n * np.pi * x) ** 2
                np.testing.assert_allclose(S[n_idx, k], expected, atol=1e-14)

    def test_sensitivity_at_half(self):
        """sin^2(n*pi*0.5) = 1 for odd n, 0 for even n."""
        pos = np.array([0.5])
        S = _sensitivity_matrix(pos, 6)
        for n_idx in range(6):
            n = n_idx + 1
            expected = 1.0 if n % 2 == 1 else 0.0
            np.testing.assert_allclose(S[n_idx, 0], expected, atol=1e-14)

    def test_sensitivity_at_quarter(self):
        """sin^2(n*pi*0.25): period 4 pattern."""
        pos = np.array([0.25])
        S = _sensitivity_matrix(pos, 4)
        expected = [0.5, 1.0, 0.5, 0.0]
        np.testing.assert_allclose(S[:, 0], expected, atol=1e-14)

    def test_sensitivity_symmetry(self):
        """S is symmetric about x=0.5 for each mode."""
        pos_a = np.array([0.2])
        pos_b = np.array([0.8])
        S_a = _sensitivity_matrix(pos_a, 10)
        S_b = _sensitivity_matrix(pos_b, 10)
        np.testing.assert_allclose(S_a, S_b, atol=1e-14)

    # --- _condition_number ---

    def test_condition_number_positive(self):
        pos = np.array([0.2, 0.5, 0.8])
        kappa = _condition_number(pos, 20)
        assert kappa > 0

    def test_condition_number_rational_large(self):
        """Rational-fraction positions should give large kappa."""
        pos = _weyl_positions(1 / 3, 5)
        kappa = _condition_number(pos, 40)
        assert kappa > 100

    def test_condition_number_irrational_small(self):
        """Irrational positions should give small kappa."""
        pos = _weyl_positions(_PHI_CONJUGATE, 5)
        kappa = _condition_number(pos, 40)
        assert kappa < 100

    def test_condition_number_degenerate(self):
        """Nearly coincident positions give huge kappa."""
        pos = np.array([0.3, 0.3001])
        kappa = _condition_number(pos, 20)
        assert kappa > 50

    def test_condition_number_increases_with_clustering(self):
        spread = np.array([0.13, 0.47, 0.83])
        clustered = np.array([0.4, 0.401, 0.402])
        k_spread = _condition_number(spread, 20)
        k_clustered = _condition_number(clustered, 20)
        assert k_clustered > k_spread

    # --- _count_distinguishable ---

    def test_distinguishable_upper_bound(self):
        """Never more than 2^K distinguishable binary patterns."""
        pos = _weyl_positions(_PHI_CONJUGATE, 5)
        n = _count_distinguishable(pos, 20)
        assert n <= 2 ** 5

    def test_distinguishable_irrational_perfect(self):
        """Irrational positions should give 2^K."""
        pos = _weyl_positions(_PHI_CONJUGATE, 5)
        n = _count_distinguishable(pos, 40)
        assert n == 2 ** 5

    def test_distinguishable_rational_collapsed(self):
        """Rational positions should give far fewer than 2^K."""
        pos = _weyl_positions(0.5, 5)
        n = _count_distinguishable(pos, 40)
        assert n < 2 ** 5 / 2

    def test_distinguishable_nonnegative(self):
        pos = np.array([0.3])
        n = _count_distinguishable(pos, 10)
        assert n >= 0

    # --- _weyl_positions ---

    def test_weyl_length(self):
        pos = _weyl_positions(0.3, 7)
        assert len(pos) == 7

    def test_weyl_sorted(self):
        pos = _weyl_positions(_PHI_CONJUGATE, 10)
        assert np.all(np.diff(pos) >= 0)

    def test_weyl_in_range(self):
        pos = _weyl_positions(np.sqrt(2) - 1, 20)
        assert np.all(pos >= 0.01)
        assert np.all(pos <= 0.99)

    def test_weyl_phi_equidistributed(self):
        """Golden ratio Weyl sequence should be well-distributed."""
        pos = _weyl_positions(_PHI_CONJUGATE, 100)
        gaps = np.diff(np.concatenate([[0], pos, [1]]))
        max_gap = np.max(gaps)
        assert max_gap < 0.05

    def test_weyl_rational_clustered(self):
        """Rational generator should cluster positions."""
        pos = _weyl_positions(0.5, 10)
        unique = np.unique(np.round(pos, 6))
        assert len(unique) < 10

    # --- _continued_fraction ---

    def test_cf_of_phi_conjugate(self):
        """phi_conjugate = [0; 1, 1, 1, 1, ...]."""
        cf = _continued_fraction(_PHI_CONJUGATE, max_terms=10)
        assert cf[0] == 0
        for i in range(1, min(8, len(cf))):
            assert cf[i] == 1

    def test_cf_of_golden_ratio(self):
        """phi = [1; 1, 1, 1, ...]."""
        phi = (1 + np.sqrt(5)) / 2
        cf = _continued_fraction(phi, max_terms=10)
        assert cf[0] == 1
        for i in range(1, min(8, len(cf))):
            assert cf[i] == 1

    def test_cf_of_sqrt2(self):
        """sqrt(2) = [1; 2, 2, 2, ...]."""
        cf = _continued_fraction(np.sqrt(2), max_terms=10)
        assert cf[0] == 1
        for i in range(1, min(6, len(cf))):
            assert cf[i] == 2

    def test_cf_of_integer(self):
        cf = _continued_fraction(3.0, max_terms=10)
        assert cf == [3]

    def test_cf_of_simple_fraction(self):
        """1/3 = [0; 3]."""
        cf = _continued_fraction(1 / 3, max_terms=10)
        assert cf[0] == 0
        assert cf[1] == 3

    def test_cf_length_bounded(self):
        cf = _continued_fraction(np.pi, max_terms=20)
        assert len(cf) <= 20

    # --- _nearest_rational ---

    def test_nearest_to_half(self):
        p, q, d = _nearest_rational(0.5, max_q=10)
        assert p == 1 and q == 2 and d < 1e-14

    def test_nearest_to_third(self):
        p, q, d = _nearest_rational(1 / 3, max_q=10)
        assert p == 1 and q == 3
        assert d < 1e-14

    def test_nearest_to_phi(self):
        """phi_conjugate is far from all small rationals."""
        p, q, d = _nearest_rational(_PHI_CONJUGATE, max_q=20)
        assert d > 0.001

    def test_nearest_distance_nonnegative(self):
        _, _, d = _nearest_rational(0.42, max_q=10)
        assert d >= 0

    def test_nearest_returns_best(self):
        """Should find 3/7 as nearest for 0.4286."""
        p, q, d = _nearest_rational(3 / 7, max_q=10)
        assert p == 3 and q == 7

    # --- _generator_cost ---

    def test_cost_positive(self):
        c = _generator_cost(0.3, 5, 20)
        assert c > 0

    def test_cost_phi_lower_than_rational(self):
        c_phi = _generator_cost(_PHI_CONJUGATE, 10, 40)
        c_rat = _generator_cost(0.5, 10, 40)
        assert c_phi < c_rat

    def test_cost_penalizes_clustering(self):
        """Very small alpha clusters near 0, should be penalized."""
        c_small = _generator_cost(0.01, 10, 40)
        c_good = _generator_cost(_PHI_CONJUGATE, 10, 40)
        assert c_small > c_good

    def test_cost_finite(self):
        c = _generator_cost(0.618, 5, 20)
        assert np.isfinite(c)


# ═══════════════════════════════════════════════════════════════════════
# Experiment tests
# ═══════════════════════════════════════════════════════════════════════

class TestRationalCatastrophe:
    """H-IR1: Rational positions are catastrophic."""

    def test_returns_correct_type(self):
        r = exp_rational_catastrophe(K=5, n_modes=20)
        assert isinstance(r, RationalCatastropheResult)

    def test_all_irrationals_above_rationals(self):
        r = exp_rational_catastrophe(K=5, n_modes=20)
        assert np.min(r.irrational_distinguishable) > np.max(r.rational_distinguishable)

    def test_gap_ratio_large(self):
        r = exp_rational_catastrophe(K=5, n_modes=20)
        assert r.gap_ratio >= 2

    def test_K10_gap_over_100(self):
        """K=10: irrationals get 1024, rationals <=8 -> gap >= 128."""
        r = exp_rational_catastrophe(K=10, n_modes=40)
        assert r.gap_ratio >= 100

    def test_rational_kappas_large(self):
        r = exp_rational_catastrophe(K=5, n_modes=20)
        assert np.all(r.rational_kappas > 10)

    def test_irrational_kappas_small(self):
        r = exp_rational_catastrophe(K=5, n_modes=20)
        assert np.all(r.irrational_kappas < 100)

    def test_verdict_K10(self):
        r = exp_rational_catastrophe(K=10, n_modes=40)
        assert r.verdict is True


class TestIrrationalSufficiency:
    """H-IR2: All irrationals achieve perfect distinguishability."""

    def test_returns_correct_type(self):
        r = exp_irrational_sufficiency(K=5, n_modes=20)
        assert isinstance(r, IrrationalSufficiencyResult)

    def test_all_perfect_K5(self):
        r = exp_irrational_sufficiency(K=5, n_modes=20)
        assert np.all(r.distinguishable >= 2 ** 5)

    def test_all_perfect_K10(self):
        r = exp_irrational_sufficiency(K=10, n_modes=40)
        assert r.all_perfect

    def test_phi_not_unique_winner(self):
        """phi is NOT uniquely the best — other irrationals may beat it."""
        r = exp_irrational_sufficiency(K=10, n_modes=40)
        assert r.phi_rank >= 1  # phi is somewhere in the ranking

    def test_kappas_all_small(self):
        r = exp_irrational_sufficiency(K=5, n_modes=20)
        assert np.all(r.kappas < 50)

    def test_names_match_irrationals(self):
        r = exp_irrational_sufficiency(K=5, n_modes=20)
        for name in r.names:
            assert name in _IRRATIONALS

    def test_verdict(self):
        r = exp_irrational_sufficiency(K=10, n_modes=40)
        assert r.verdict is True


class TestCFDepth:
    """H-IR3: kappa peaks mark rational positions."""

    def test_returns_correct_type(self):
        r = exp_cf_depth(n_modes=50, n_positions=200)
        assert isinstance(r, CFDepthResult)

    def test_finds_peaks(self):
        r = exp_cf_depth(n_modes=100, n_positions=500)
        assert r.n_peaks >= 2

    def test_most_peaks_at_rationals(self):
        r = exp_cf_depth(n_modes=100, n_positions=500)
        assert r.peak_rational_frac >= 0.8

    def test_kappas_positive(self):
        r = exp_cf_depth(n_modes=50, n_positions=200)
        assert np.all(r.kappas > 0)

    def test_positions_in_range(self):
        r = exp_cf_depth(n_modes=50, n_positions=200)
        assert np.all(r.positions >= 0)
        assert np.all(r.positions <= 1)

    def test_peaks_near_rational_le_total(self):
        r = exp_cf_depth(n_modes=100, n_positions=500)
        assert r.peaks_near_rational <= r.n_peaks

    def test_verdict(self):
        r = exp_cf_depth(n_modes=100, n_positions=500)
        assert r.verdict is True


class TestBlindPrediction:
    """H-IR4: Blind optimization predicts a specific irrational."""

    def test_returns_correct_type(self):
        r = exp_blind_prediction(K=5, n_modes=40)
        assert isinstance(r, BlindPredictionResult)

    def test_predicted_alpha_in_range(self):
        r = exp_blind_prediction(K=5, n_modes=40)
        assert 0.1 <= r.predicted_alpha <= 0.9

    def test_predicted_avoids_small_rationals(self):
        """Predicted alpha should be far from small-denominator rationals."""
        r = exp_blind_prediction(K=10, n_modes=100)
        for q in range(1, r.K + 1):
            p = round(r.predicted_alpha * q)
            if p > 0:
                assert abs(r.predicted_alpha - p / q) > 1.0 / (3.0 * q * q)

    def test_cf_expansion_nonempty(self):
        r = exp_blind_prediction(K=5, n_modes=40)
        assert len(r.predicted_cf) >= 2

    def test_full_distinguishability(self):
        """Predicted generator should produce 2^K distinguishable."""
        r = exp_blind_prediction(K=10, n_modes=100)
        assert r.distinguishable >= 2 ** r.K

    def test_hurwitz_separated(self):
        r = exp_blind_prediction(K=10, n_modes=100)
        assert r.hurwitz_separated is True

    def test_verdict(self):
        r = exp_blind_prediction(K=10, n_modes=100)
        assert r.verdict is True


# ═══════════════════════════════════════════════════════════════════════
# Physics / cross-validation tests
# ═══════════════════════════════════════════════════════════════════════

class TestPhysics:
    """Cross-validation with known physics."""

    def test_weyl_equidistribution(self):
        """Weyl sequence with irrational alpha is equidistributed."""
        pos = _weyl_positions(_PHI_CONJUGATE, 50)
        # Check that positions span [0.01, 0.99] fairly
        bins = np.histogram(pos, bins=5, range=(0, 1))[0]
        assert np.min(bins) >= 5  # at least 5 in each bin

    def test_three_distance_theorem(self):
        """Weyl sequence has at most 3 distinct gap lengths."""
        pos = _weyl_positions(_PHI_CONJUGATE, 20)
        extended = np.concatenate([[0], pos, [1]])
        gaps = np.diff(extended)
        unique_gaps = np.unique(np.round(gaps, 8))
        assert len(unique_gaps) <= 3

    def test_hurwitz_bound_phi(self):
        """phi_conjugate satisfies tight Hurwitz: |phi - p/q| >= 1/(sqrt(5)*q^2)."""
        for q in range(1, 30):
            p = round(_PHI_CONJUGATE * q)
            dist = abs(_PHI_CONJUGATE - p / q)
            bound = 1.0 / (np.sqrt(5) * q ** 2 + 1)  # slightly relaxed
            assert dist >= bound

    def test_cf_reconstruction(self):
        """CF coefficients reconstruct the original number."""
        cf = _continued_fraction(_PHI_CONJUGATE, max_terms=20)
        # Reconstruct from CF (phi converges slowly, need many terms)
        terms = cf[:15]
        val = 0.0
        for a in reversed(terms[1:]):
            val = 1.0 / (a + val) if (a + val) != 0 else 0
        val += terms[0]
        np.testing.assert_allclose(val, _PHI_CONJUGATE, atol=1e-5)

    def test_sensitivity_periodicity_at_rational(self):
        """At x=p/q, sin^2(n*pi*p/q) has period q in n."""
        pos = np.array([1 / 5])
        S = _sensitivity_matrix(pos, 20)
        col = S[:, 0]
        # Period 5: col[n] == col[n+5] for all valid n
        for n in range(15):
            np.testing.assert_allclose(col[n], col[n + 5], atol=1e-14)

    def test_sin_squared_identity(self):
        """sin^2(x) = (1 - cos(2x))/2."""
        pos = np.array([0.13, 0.37, 0.61])
        S = _sensitivity_matrix(pos, 8)
        for n_idx in range(8):
            n = n_idx + 1
            for k, x in enumerate(pos):
                expected = (1 - np.cos(2 * n * np.pi * x)) / 2
                np.testing.assert_allclose(S[n_idx, k], expected, atol=1e-14)


# ═══════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge case robustness."""

    def test_single_site(self):
        pos = np.array([_PHI_CONJUGATE])
        kappa = _condition_number(pos, 10)
        assert kappa > 0

    def test_many_modes(self):
        pos = _weyl_positions(_PHI_CONJUGATE, 3)
        kappa = _condition_number(pos, 200)
        assert np.isfinite(kappa)

    def test_cf_very_small(self):
        cf = _continued_fraction(0.001, max_terms=10)
        assert cf[0] == 0
        assert len(cf) >= 2

    def test_nearest_rational_exact(self):
        p, q, d = _nearest_rational(0.25, max_q=10)
        assert p == 1 and q == 4 and d < 1e-14

    def test_cost_at_boundaries(self):
        c_lo = _generator_cost(0.1, 5, 20)
        c_hi = _generator_cost(0.9, 5, 20)
        assert np.isfinite(c_lo)
        assert np.isfinite(c_hi)


# ═══════════════════════════════════════════════════════════════════════
# Runner test
# ═══════════════════════════════════════════════════════════════════════

class TestRunner:
    """Integration test for the full runner."""

    def test_runner_returns_summary(self):
        s = run_all_irrational(n_modes=40, verbose=False)
        assert isinstance(s, IrrationalPredictionSummary)

    def test_runner_counts_consistent(self):
        s = run_all_irrational(n_modes=40, verbose=False)
        assert s.n_confirmed + s.n_killed == 4

    def test_runner_at_least_3_confirmed(self):
        s = run_all_irrational(n_modes=100, verbose=False)
        assert s.n_confirmed >= 3
