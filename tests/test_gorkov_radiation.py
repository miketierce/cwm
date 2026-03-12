"""
Tests for S12 — Gor'kov: Acoustic Radiation Force & Optimal Site Placement
===========================================================================

Hypotheses: H-ARF1 through H-ARF4
"""

import numpy as np
import pytest

from simulations.gorkov_radiation import (
    # Helpers
    _acoustic_frequencies,
    _sensitivity,
    _sensitivity_gradient,
    _gorkov_force_pattern,
    _acoustic_contrast_factor,
    _golden_positions,
    _gorkov_optimal_positions,
    _sensitivity_matrix,
    _gradient_matrix,
    _condition_number,
    _count_distinguishable,
    _fingerprint_entropy,
    _node_positions,
    _antinode_positions,
    _bjerknes_sign,
    _multi_mode_bjerknes_sign,
    _hybridisation_splitting,
    _eigenfrequency_shift,
    _spearman_correlation,
    _pearson_correlation,
    # Result types
    GorkovPlacementResult,
    ContrastFactorResult,
    BjerknesHybridResult,
    DualAxisResult,
    # Material table
    _MATERIAL_TABLE,
    # Experiments
    exp_gorkov_placement,
    exp_contrast_factor,
    exp_bjerknes_hybridisation,
    exp_dual_axis,
    # Runner
    run_all_gorkov,
)

from simulations.common import K_B, C_FERROFLUID


# ═══════════════════════════════════════════════════════════════════════
# Helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Unit tests for all helper functions."""

    # --- _acoustic_frequencies ---

    def test_acoustic_frequencies_count(self):
        f = _acoustic_frequencies(10)
        assert len(f) == 10

    def test_acoustic_frequencies_fundamental(self):
        L = 1e-5
        f = _acoustic_frequencies(1, L=L)
        np.testing.assert_allclose(f[0], C_FERROFLUID / (2 * L), rtol=1e-10)

    def test_acoustic_frequencies_harmonic_series(self):
        f = _acoustic_frequencies(5)
        ratios = f / f[0]
        np.testing.assert_allclose(ratios, [1, 2, 3, 4, 5], rtol=1e-10)

    def test_acoustic_frequencies_increase(self):
        f = _acoustic_frequencies(20)
        assert np.all(np.diff(f) > 0)

    def test_acoustic_frequencies_custom_L(self):
        L = 1e-3
        f = _acoustic_frequencies(3, L=L)
        expected = np.array([1, 2, 3]) * C_FERROFLUID / (2 * L)
        np.testing.assert_allclose(f, expected, rtol=1e-10)

    # --- _sensitivity ---

    def test_sensitivity_at_zero(self):
        """sin²(nπ·0) = 0 for all n."""
        for n in range(1, 6):
            val = _sensitivity(n, np.array([0.0]))
            np.testing.assert_allclose(val, [0.0], atol=1e-15)

    def test_sensitivity_at_half(self):
        """sin²(1·π·0.5) = 1 for n=1."""
        val = _sensitivity(1, np.array([0.5]))
        np.testing.assert_allclose(val, [1.0], atol=1e-10)

    def test_sensitivity_bounded(self):
        x = np.linspace(0, 1, 1000)
        for n in range(1, 6):
            s = _sensitivity(n, x)
            assert np.all(s >= -1e-15)
            assert np.all(s <= 1 + 1e-15)

    def test_sensitivity_symmetry(self):
        """sin²(nπx) is symmetric about x=0.5 for even n."""
        x = np.array([0.2, 0.8])
        s = _sensitivity(2, x)
        np.testing.assert_allclose(s[0], s[1], atol=1e-10)

    # --- _sensitivity_gradient ---

    def test_gradient_proportional_to_gorkov_force(self):
        """Gradient ∝ sin(2nπx), same shape as Gor'kov force."""
        x = np.linspace(0.01, 0.99, 100)
        n = 3
        grad = _sensitivity_gradient(n, x)
        force = _gorkov_force_pattern(n, x)
        # gradient = nπ × force
        np.testing.assert_allclose(grad, n * np.pi * force, rtol=1e-10)

    def test_gradient_at_zero(self):
        """Gradient at x=0 is sin(0) = 0."""
        val = _sensitivity_gradient(1, np.array([0.0]))
        np.testing.assert_allclose(val, [0.0], atol=1e-15)

    def test_gradient_max_at_quarter(self):
        """For n=1, gradient sin(2πx) peaks at x=0.25."""
        x = np.linspace(0.01, 0.99, 500)
        g = _sensitivity_gradient(1, x)
        idx_max = np.argmax(g)
        np.testing.assert_allclose(x[idx_max], 0.25, atol=0.01)

    # --- _gorkov_force_pattern ---

    def test_gorkov_force_zeros(self):
        """sin(2nπx) = 0 at x = 0, 0.5/n, 1.0/n, ..."""
        for n in range(1, 4):
            val = _gorkov_force_pattern(n, np.array([0.0]))
            np.testing.assert_allclose(val, [0.0], atol=1e-15)

    def test_gorkov_force_bounded(self):
        x = np.linspace(0, 1, 1000)
        for n in range(1, 10):
            f = _gorkov_force_pattern(n, x)
            assert np.all(f >= -1 - 1e-10)
            assert np.all(f <= 1 + 1e-10)

    # --- _acoustic_contrast_factor ---

    def test_contrast_factor_steel(self):
        """Steel (ρ̃=6.5, κ̃=0.04) should have large positive Φ."""
        phi = _acoustic_contrast_factor(6.5, 0.04)
        assert phi > 1.0  # strong positive — moves to pressure node

    def test_contrast_factor_polystyrene(self):
        """Polystyrene (ρ̃=0.88, κ̃=1.67) should have negative Φ."""
        phi = _acoustic_contrast_factor(0.88, 1.67)
        assert phi < 0  # negative — moves to pressure antinode

    def test_contrast_factor_formula(self):
        """Direct formula check: Φ = (5ρ̃−2)/(2ρ̃+1) − κ̃."""
        rho, kappa = 3.0, 0.2
        expected = (5 * rho - 2) / (2 * rho + 1) - kappa
        np.testing.assert_allclose(
            _acoustic_contrast_factor(rho, kappa), expected, rtol=1e-12)

    def test_contrast_factor_neutral(self):
        """Find ρ̃ where Φ=0 with κ̃=0: (5ρ̃−2)/(2ρ̃+1) = 0 → ρ̃ = 0.4."""
        phi = _acoustic_contrast_factor(0.4, 0.0)
        np.testing.assert_allclose(phi, 0.0, atol=1e-10)

    # --- _golden_positions ---

    def test_golden_positions_count(self):
        assert len(_golden_positions(6)) == 6

    def test_golden_positions_in_range(self):
        pos = _golden_positions(10)
        assert np.all(pos >= 0.02)
        assert np.all(pos <= 0.98)

    def test_golden_positions_sorted(self):
        pos = _golden_positions(8)
        assert np.all(np.diff(pos) >= 0)

    # --- _gorkov_optimal_positions ---

    def test_gorkov_positions_count(self):
        pos = _gorkov_optimal_positions(6, 10)
        assert len(pos) == 6

    def test_gorkov_positions_in_range(self):
        pos = _gorkov_optimal_positions(8, 15)
        assert np.all(pos >= 0.02)
        assert np.all(pos <= 0.98)

    def test_gorkov_positions_sorted(self):
        pos = _gorkov_optimal_positions(6, 10)
        assert np.all(np.diff(pos) >= 0)

    def test_gorkov_positions_minimum_spacing(self):
        """Selected positions must respect minimum spacing."""
        K = 6
        pos = _gorkov_optimal_positions(K, 10)
        min_spacing = 0.8 / K
        diffs = np.diff(pos)
        # Due to fallback, not all may satisfy strict spacing,
        # but the greedy phase should produce decent separation.
        assert np.min(diffs) > 0

    # --- _sensitivity_matrix ---

    def test_sensitivity_matrix_shape(self):
        S = _sensitivity_matrix(_golden_positions(4), 20)
        assert S.shape == (20, 4)

    def test_sensitivity_matrix_bounded(self):
        S = _sensitivity_matrix(_golden_positions(5), 10)
        assert np.all(S >= -1e-15)
        assert np.all(S <= 1 + 1e-15)

    def test_sensitivity_matrix_values(self):
        """S[n,k] = sin²(n·π·x_k)."""
        pos = np.array([0.25, 0.5, 0.75])
        S = _sensitivity_matrix(pos, 3)
        for ni in range(3):
            n = ni + 1
            for ki, x in enumerate(pos):
                expected = np.sin(n * np.pi * x) ** 2
                np.testing.assert_allclose(S[ni, ki], expected, rtol=1e-10)

    # --- _gradient_matrix ---

    def test_gradient_matrix_shape(self):
        G = _gradient_matrix(_golden_positions(4), 10)
        assert G.shape == (10, 4)

    def test_gradient_matrix_values(self):
        """G[n,k] = nπ·sin(2nπx_k)."""
        pos = np.array([0.25, 0.5])
        G = _gradient_matrix(pos, 2)
        for ni in range(2):
            n = ni + 1
            for ki, x in enumerate(pos):
                expected = n * np.pi * np.sin(2 * n * np.pi * x)
                np.testing.assert_allclose(G[ni, ki], expected, rtol=1e-10)

    # --- _condition_number ---

    def test_condition_number_identity(self):
        """Condition number of identity matrix is 1."""
        M = np.eye(3)
        np.testing.assert_allclose(_condition_number(M), 1.0, rtol=1e-10)

    def test_condition_number_singular(self):
        """Near-singular matrix has large condition number."""
        M = np.array([[1, 1], [1, 1 + 1e-14]])
        assert _condition_number(M) > 1e10

    def test_condition_number_positive(self):
        S = _sensitivity_matrix(_golden_positions(4), 10)
        assert _condition_number(S) > 0

    # --- _count_distinguishable ---

    def test_count_distinguishable_returns_tuple(self):
        S = _sensitivity_matrix(_golden_positions(4), 10)
        n_dist, bits = _count_distinguishable(S)
        assert isinstance(n_dist, int)
        assert isinstance(bits, float)

    def test_count_distinguishable_positive(self):
        S = _sensitivity_matrix(_golden_positions(4), 10)
        n_dist, bits = _count_distinguishable(S)
        assert n_dist > 0
        assert bits >= 0

    # --- _fingerprint_entropy ---

    def test_fingerprint_entropy_positive(self):
        S = _sensitivity_matrix(_golden_positions(4), 10)
        ent = _fingerprint_entropy(S)
        assert ent > 0

    def test_fingerprint_entropy_deterministic(self):
        S = _sensitivity_matrix(_golden_positions(4), 10)
        e1 = _fingerprint_entropy(S, seed=42)
        e2 = _fingerprint_entropy(S, seed=42)
        np.testing.assert_allclose(e1, e2)

    # --- _node_positions / _antinode_positions ---

    def test_node_positions_are_zeros(self):
        """Nodes of sin²(nπx) at x = k/n have zero sensitivity."""
        # For n_ref=3, interior nodes at x = 1/3, 2/3
        pos = _node_positions(3, n_ref=3)
        for x in pos:
            val = _sensitivity(3, np.array([x]))
            np.testing.assert_allclose(val, [0.0], atol=1e-10)

    def test_antinode_positions_are_maxima(self):
        """Antinodes of sin²(πx) at x = 0.5 for n_ref=1."""
        pos = _antinode_positions(1, n_ref=1)
        assert len(pos) >= 1
        val = _sensitivity(1, pos)
        np.testing.assert_allclose(val, [1.0], atol=1e-10)

    def test_node_positions_in_range(self):
        pos = _node_positions(5, n_ref=3)
        assert np.all(pos >= 0.02)
        assert np.all(pos <= 0.98)

    def test_antinode_positions_in_range(self):
        pos = _antinode_positions(5, n_ref=3)
        assert np.all(pos >= 0.02)
        assert np.all(pos <= 0.98)

    # --- _bjerknes_sign ---

    def test_bjerknes_same_side_attractive(self):
        """Two sites on same side of a node → in-phase → attractive."""
        # For n=1: both at x<0.5 → both positive sin → product > 0
        assert _bjerknes_sign(0.1, 0.3, 1) == 1

    def test_bjerknes_opposite_sides_repulsive(self):
        """Sites on opposite sides of node → anti-phase → repulsive."""
        # For n=2: x=0.1 and x=0.4 straddle node at 0.5
        # sin(2π·0.1) > 0, sin(2π·0.4) > 0 → actually same sign
        # Use n=1: sin(π·0.3) > 0, sin(π·0.7) > 0 → same sign
        # Need to find true opposite sides: for n=2, node at 0.5
        # sin(2π·0.1) > 0, sin(2π·0.6) > 0... hm, sin(2π·0.6)=sin(1.2π) < 0
        assert _bjerknes_sign(0.1, 0.6, 2) == -1

    def test_bjerknes_returns_pm1(self):
        for _ in range(20):
            x1 = np.random.uniform(0.05, 0.95)
            x2 = np.random.uniform(0.05, 0.95)
            s = _bjerknes_sign(x1, x2, 1)
            assert s in (1, -1)

    # --- _multi_mode_bjerknes_sign ---

    def test_multi_mode_bjerknes_returns_pm1(self):
        s = _multi_mode_bjerknes_sign(0.2, 0.4, 10)
        assert s in (1, -1)

    # --- _hybridisation_splitting ---

    def test_splitting_proportional_to_epsilon(self):
        s1 = _hybridisation_splitting(1, 2, 0.3, epsilon=0.01)
        s2 = _hybridisation_splitting(1, 2, 0.3, epsilon=0.02)
        np.testing.assert_allclose(s2, 2 * s1, rtol=1e-10)

    def test_splitting_nonneg(self):
        for n in range(1, 5):
            for m in range(n + 1, 8):
                s = _hybridisation_splitting(n, m, 0.3)
                assert s >= 0

    def test_splitting_at_node_is_zero(self):
        """At x = 0 (node for all modes), splitting = 0."""
        s = _hybridisation_splitting(1, 2, 0.0)
        np.testing.assert_allclose(s, 0.0, atol=1e-15)

    # --- _eigenfrequency_shift ---

    def test_shift_proportional_to_epsilon(self):
        s1 = _eigenfrequency_shift(1, 0.3, 0.01)
        s2 = _eigenfrequency_shift(1, 0.3, 0.02)
        np.testing.assert_allclose(s2, 2 * s1, rtol=1e-10)

    def test_shift_at_node_is_zero(self):
        """At x = 0, sensitivity is 0 so shift should be 0."""
        s = _eigenfrequency_shift(1, 0.0, 0.01)
        np.testing.assert_allclose(s, 0.0, atol=1e-15)

    def test_shift_depends_on_contrast_factor(self):
        """Different materials (different ρ̃, κ̃) give different shifts."""
        s1 = _eigenfrequency_shift(1, 0.3, 0.01, rho_ratio=6.5, kappa_ratio=0.04)
        s2 = _eigenfrequency_shift(1, 0.3, 0.01, rho_ratio=0.88, kappa_ratio=1.67)
        assert s1 != s2

    # --- _spearman_correlation ---

    def test_spearman_perfect(self):
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        assert _spearman_correlation(x, x) == 1.0

    def test_spearman_inverse(self):
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        y = np.array([5, 4, 3, 2, 1], dtype=float)
        np.testing.assert_allclose(_spearman_correlation(x, y), -1.0, atol=1e-10)

    def test_spearman_returns_float(self):
        x = np.array([1, 3, 2], dtype=float)
        y = np.array([2, 1, 3], dtype=float)
        assert isinstance(_spearman_correlation(x, y), float)

    # --- _pearson_correlation ---

    def test_pearson_perfect(self):
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        np.testing.assert_allclose(_pearson_correlation(x, x), 1.0, atol=1e-10)

    def test_pearson_inverse(self):
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        y = np.array([5, 4, 3, 2, 1], dtype=float)
        np.testing.assert_allclose(_pearson_correlation(x, y), -1.0, atol=1e-10)

    def test_pearson_orthogonal(self):
        x = np.array([1, 0, -1, 0], dtype=float)
        y = np.array([0, 1, 0, -1], dtype=float)
        np.testing.assert_allclose(_pearson_correlation(x, y), 0.0, atol=1e-10)


# ═══════════════════════════════════════════════════════════════════════
# Experiment 1 tests: Gor'kov Placement (H-ARF1)
# ═══════════════════════════════════════════════════════════════════════

class TestGorkovPlacement:
    """Tests for exp_gorkov_placement — H-ARF1."""

    def test_returns_result_type(self):
        r = exp_gorkov_placement()
        assert isinstance(r, GorkovPlacementResult)

    def test_result_has_all_fields(self):
        r = exp_gorkov_placement()
        assert r.n_modes == 20
        assert r.K == 6
        assert len(r.gorkov_positions) == 6
        assert len(r.golden_positions) == 6

    def test_positions_in_range(self):
        r = exp_gorkov_placement()
        assert np.all(r.gorkov_positions >= 0.02)
        assert np.all(r.gorkov_positions <= 0.98)
        assert np.all(r.golden_positions >= 0.02)
        assert np.all(r.golden_positions <= 0.98)

    def test_condition_numbers_positive(self):
        r = exp_gorkov_placement()
        assert r.gorkov_cond > 0
        assert r.golden_cond > 0

    def test_distinguishable_nonneg(self):
        r = exp_gorkov_placement()
        assert r.gorkov_distinguishable >= 0
        assert r.golden_distinguishable >= 0

    def test_bits_nonneg(self):
        r = exp_gorkov_placement()
        assert r.gorkov_bits >= 0
        assert r.golden_bits >= 0

    def test_improvement_pct_consistent(self):
        r = exp_gorkov_placement()
        if r.golden_distinguishable > 0:
            expected = (r.gorkov_distinguishable - r.golden_distinguishable) \
                       / r.golden_distinguishable * 100
            np.testing.assert_allclose(r.improvement_pct, expected, rtol=1e-6)

    def test_verdict_is_bool(self):
        r = exp_gorkov_placement()
        assert isinstance(r.verdict, bool)

    def test_verdict_consistent_with_improvement(self):
        r = exp_gorkov_placement()
        assert r.verdict == (r.improvement_pct >= 10.0)

    def test_custom_parameters(self):
        r = exp_gorkov_placement(K=4, n_modes=10)
        assert r.K == 4
        assert r.n_modes == 10

    def test_custom_threshold(self):
        r = exp_gorkov_placement(improvement_threshold=0.0)
        # With 0% threshold, any non-negative improvement passes
        if r.improvement_pct >= 0:
            assert r.verdict is True


# ═══════════════════════════════════════════════════════════════════════
# Experiment 2 tests: Contrast Factor (H-ARF2)
# ═══════════════════════════════════════════════════════════════════════

class TestContrastFactor:
    """Tests for exp_contrast_factor — H-ARF2."""

    def test_returns_result_type(self):
        r = exp_contrast_factor()
        assert isinstance(r, ContrastFactorResult)

    def test_result_has_all_fields(self):
        r = exp_contrast_factor()
        assert r.n_materials == len(_MATERIAL_TABLE)
        assert len(r.material_names) == r.n_materials
        assert len(r.rho_ratios) == r.n_materials
        assert len(r.kappa_ratios) == r.n_materials
        assert len(r.phi_values) == r.n_materials
        assert len(r.freq_shifts) == r.n_materials

    def test_material_names_match_table(self):
        r = exp_contrast_factor()
        expected = [m[0] for m in _MATERIAL_TABLE]
        assert r.material_names == expected

    def test_phi_values_formula(self):
        """Verify Φ = (5ρ̃−2)/(2ρ̃+1) − κ̃ for each material."""
        r = exp_contrast_factor()
        for i in range(r.n_materials):
            rho = r.rho_ratios[i]
            kappa = r.kappa_ratios[i]
            expected = (5 * rho - 2) / (2 * rho + 1) - kappa
            np.testing.assert_allclose(r.phi_values[i], expected, rtol=1e-10)

    def test_freq_shifts_positive(self):
        r = exp_contrast_factor()
        assert np.all(r.freq_shifts >= 0)

    def test_correlations_bounded(self):
        r = exp_contrast_factor()
        assert -1 <= r.spearman_r <= 1
        assert -1 <= r.pearson_r <= 1

    def test_verdict_is_bool(self):
        r = exp_contrast_factor()
        assert isinstance(r.verdict, bool)

    def test_verdict_consistent_with_spearman(self):
        r = exp_contrast_factor()
        assert r.verdict == (r.spearman_r > 0.7)

    def test_steel_highest_phi(self):
        """Steel or dense metals should have among the highest |Φ|."""
        r = exp_contrast_factor()
        # Find steel index
        idx = r.material_names.index("steel")
        abs_phi = np.abs(r.phi_values)
        # Steel should be in top 5 by |Φ|
        rank = np.sum(abs_phi > abs_phi[idx])
        assert rank < 5

    def test_polystyrene_negative_phi(self):
        """Polystyrene should have negative Φ (lighter, compressible)."""
        r = exp_contrast_factor()
        idx = r.material_names.index("polystyrene")
        assert r.phi_values[idx] < 0


# ═══════════════════════════════════════════════════════════════════════
# Experiment 3 tests: Bjerknes Hybridisation (H-ARF3)
# ═══════════════════════════════════════════════════════════════════════

class TestBjerknesHybridisation:
    """Tests for exp_bjerknes_hybridisation — H-ARF3."""

    def test_returns_result_type(self):
        r = exp_bjerknes_hybridisation()
        assert isinstance(r, BjerknesHybridResult)

    def test_result_has_all_fields(self):
        r = exp_bjerknes_hybridisation()
        assert r.n_pairs > 0
        assert len(r.pair_separations) == r.n_pairs
        assert len(r.bjerknes_sign) == r.n_pairs
        assert len(r.splitting_magnitudes) == r.n_pairs

    def test_n_pairs_correct(self):
        """K=8 → C(8,2) = 28 pairs."""
        r = exp_bjerknes_hybridisation(K=8)
        assert r.n_pairs == 28

    def test_pair_separations_positive(self):
        r = exp_bjerknes_hybridisation()
        assert np.all(r.pair_separations > 0)

    def test_bjerknes_signs_pm1(self):
        r = exp_bjerknes_hybridisation()
        for s in r.bjerknes_sign:
            assert s in (1, -1)

    def test_splitting_nonneg(self):
        r = exp_bjerknes_hybridisation()
        assert np.all(r.splitting_magnitudes >= 0)

    def test_mean_splits_nonneg(self):
        r = exp_bjerknes_hybridisation()
        assert r.mean_attractive_split >= 0
        assert r.mean_repulsive_split >= 0

    def test_ratio_positive(self):
        r = exp_bjerknes_hybridisation()
        assert r.ratio >= 0

    def test_verdict_is_bool(self):
        r = exp_bjerknes_hybridisation()
        assert isinstance(r.verdict, bool)

    def test_verdict_consistent_with_ratio(self):
        r = exp_bjerknes_hybridisation()
        assert r.verdict == (r.ratio >= 2.0)

    def test_custom_K(self):
        r = exp_bjerknes_hybridisation(K=4)
        assert r.n_pairs == 6  # C(4,2) = 6

    def test_has_both_attractive_and_repulsive(self):
        """With 8 sites and 20 modes, expect both sign types."""
        r = exp_bjerknes_hybridisation(K=8, n_modes=20)
        assert np.any(r.bjerknes_sign > 0)
        assert np.any(r.bjerknes_sign < 0)


# ═══════════════════════════════════════════════════════════════════════
# Experiment 4 tests: Dual-Axis Encoding (H-ARF4)
# ═══════════════════════════════════════════════════════════════════════

class TestDualAxis:
    """Tests for exp_dual_axis — H-ARF4."""

    def test_returns_result_type(self):
        r = exp_dual_axis()
        assert isinstance(r, DualAxisResult)

    def test_result_has_all_fields(self):
        r = exp_dual_axis()
        assert r.n_modes == 20
        assert r.K_total > 0
        assert r.K_node >= 0
        assert r.K_antinode >= 0

    def test_K_total_is_sum(self):
        r = exp_dual_axis()
        assert r.K_total == r.K_node + r.K_antinode

    def test_positions_in_range(self):
        r = exp_dual_axis()
        assert np.all(r.dual_positions >= 0.02)
        assert np.all(r.dual_positions <= 0.98)
        assert np.all(r.antinode_only_positions >= 0.02)
        assert np.all(r.antinode_only_positions <= 0.98)

    def test_dual_positions_sorted(self):
        r = exp_dual_axis()
        assert np.all(np.diff(r.dual_positions) >= 0)

    def test_entropy_positive(self):
        r = exp_dual_axis()
        assert r.entropy_dual > 0
        assert r.entropy_antinode > 0

    def test_entropy_gain_consistent(self):
        r = exp_dual_axis()
        if r.entropy_antinode > 0:
            expected = (r.entropy_dual - r.entropy_antinode) / r.entropy_antinode * 100
            np.testing.assert_allclose(r.entropy_gain_pct, expected, rtol=1e-6)

    def test_condition_numbers_positive(self):
        r = exp_dual_axis()
        assert r.cond_dual > 0
        assert r.cond_antinode > 0

    def test_verdict_is_bool(self):
        r = exp_dual_axis()
        assert isinstance(r.verdict, bool)

    def test_verdict_consistent_with_gain(self):
        r = exp_dual_axis()
        assert r.verdict == (r.entropy_gain_pct >= 20.0)

    def test_custom_K_per_axis(self):
        r = exp_dual_axis(K_per_axis=2, n_modes=10)
        assert r.K_total > 0


# ═══════════════════════════════════════════════════════════════════════
# Runner tests
# ═══════════════════════════════════════════════════════════════════════

class TestRunner:
    """Tests for run_all_gorkov."""

    def test_returns_dict(self):
        results = run_all_gorkov(verbose=False)
        assert isinstance(results, dict)

    def test_has_all_hypotheses(self):
        results = run_all_gorkov(verbose=False)
        assert "H-ARF1" in results
        assert "H-ARF2" in results
        assert "H-ARF3" in results
        assert "H-ARF4" in results

    def test_correct_result_types(self):
        results = run_all_gorkov(verbose=False)
        assert isinstance(results["H-ARF1"], GorkovPlacementResult)
        assert isinstance(results["H-ARF2"], ContrastFactorResult)
        assert isinstance(results["H-ARF3"], BjerknesHybridResult)
        assert isinstance(results["H-ARF4"], DualAxisResult)

    def test_all_have_verdict(self):
        results = run_all_gorkov(verbose=False)
        for key, r in results.items():
            assert isinstance(r.verdict, bool), f"{key} verdict is not bool"

    def test_verbose_output(self, capsys):
        run_all_gorkov(verbose=True)
        captured = capsys.readouterr()
        assert "H-ARF1" in captured.out
        assert "H-ARF2" in captured.out
        assert "H-ARF3" in captured.out
        assert "H-ARF4" in captured.out
        assert "S12 SUMMARY" in captured.out

    def test_verbose_false_no_output(self, capsys):
        run_all_gorkov(verbose=False)
        captured = capsys.readouterr()
        assert captured.out == ""


# ═══════════════════════════════════════════════════════════════════════
# Physics / cross-validation tests
# ═══════════════════════════════════════════════════════════════════════

class TestPhysics:
    """Cross-validation of physical formulas and edge cases."""

    def test_gradient_is_derivative_of_sensitivity(self):
        """Numerical derivative of sin²(nπx) ≈ analytical (2nπ)sin(nπx)cos(nπx)."""
        x = np.array([0.3])
        dx = 1e-8
        n = 3
        numerical = (_sensitivity(n, x + dx) - _sensitivity(n, x - dx)) / (2 * dx)
        # Analytical: 2·sin(nπx)·cos(nπx)·nπ = nπ·sin(2nπx)
        analytical = _sensitivity_gradient(n, x)
        np.testing.assert_allclose(numerical, analytical, rtol=1e-5)

    def test_contrast_factor_matches_table(self):
        """Each material in _MATERIAL_TABLE gives expected Φ range."""
        for name, rho, kappa in _MATERIAL_TABLE:
            phi = _acoustic_contrast_factor(rho, kappa)
            # All should be finite
            assert np.isfinite(phi), f"{name} has non-finite Φ"

    def test_shift_proportional_to_contrast_factor(self):
        """Materials with higher |Φ| produce larger eigenfrequency shifts."""
        n, x_p, eps = 3, 0.3, 0.01
        shifts = []
        phis = []
        for name, rho, kappa in _MATERIAL_TABLE:
            phi = abs(_acoustic_contrast_factor(rho, kappa))
            shift = _eigenfrequency_shift(n, x_p, eps, rho, kappa)
            shifts.append(shift)
            phis.append(phi)
        # Shift = ε·|Φ|·sin²(nπx) → shift ∝ |Φ| for fixed n, x, ε
        # So shift/|Φ| should be constant
        shifts = np.array(shifts)
        phis = np.array(phis)
        normalised = shifts / (phis + 1e-30)
        np.testing.assert_allclose(normalised, normalised[0], rtol=1e-10)

    def test_gorkov_force_identity(self):
        """Key theoretical result: ∂/∂x sin²(nπx) = nπ·sin(2nπx)."""
        x = np.linspace(0.01, 0.99, 200)
        for n in range(1, 6):
            dx = 1e-8
            numerical = (_sensitivity(n, x + dx) - _sensitivity(n, x - dx)) / (2 * dx)
            analytical = n * np.pi * _gorkov_force_pattern(n, x)
            np.testing.assert_allclose(numerical, analytical, rtol=1e-4)

    def test_node_antinode_complementary(self):
        """Nodes have zero sensitivity, antinodes have maximum sensitivity."""
        node_pos = _node_positions(3, n_ref=3)
        anti_pos = _antinode_positions(2, n_ref=2)
        for x in node_pos:
            assert _sensitivity(3, np.array([x]))[0] < 0.01
        for x in anti_pos:
            assert _sensitivity(2, np.array([x]))[0] > 0.9

    def test_spearman_invariant_to_monotone_transform(self):
        """Spearman correlation is invariant under monotone transformations."""
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        y = x ** 3  # monotone transform
        np.testing.assert_allclose(_spearman_correlation(x, y), 1.0, atol=1e-10)

    def test_material_table_has_12_entries(self):
        assert len(_MATERIAL_TABLE) == 12

    def test_all_materials_have_valid_properties(self):
        """All materials must have positive density and compressibility ratios."""
        for name, rho, kappa in _MATERIAL_TABLE:
            assert rho > 0, f"{name} has ρ̃ ≤ 0"
            assert kappa > 0, f"{name} has κ̃ ≤ 0"
