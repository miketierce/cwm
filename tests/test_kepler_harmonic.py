"""
Tests for S10 — Kepler: Harmonic Resonance Ratios
===================================================

Hypotheses: H-K1 through H-K4
"""

import numpy as np
import pytest

from simulations.kepler_harmonic import (
    # Helpers
    _golden_positions,
    _sensitivity_matrix,
    _consonance_rating,
    _partition_by_octaves,
    _quantise,
    _channel_crosstalk_matrix,
    _partition_capacity,
    _create_weighted_hopfield,
    _recall_with_weights,
    _corrupt_binary,
    _perturbed_frequencies,
    _sign_activation,
    # Experiments
    exp_diatonic_partition,
    exp_consonance_recall,
    exp_octave_equivalence,
    exp_harmonic_scaling,
    # Result types
    DiatonicPartitionResult,
    ConsonanceRecallResult,
    OctaveEquivalenceResult,
    HarmonicScalingResult,
    # Runner
    run_all_kepler,
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

    # --- _consonance_rating ---

    def test_consonance_unison(self):
        """C(1,1) = 1/(1+1) = 0.5."""
        assert _consonance_rating(1, 1) == 0.5

    def test_consonance_octave(self):
        """C(1,2) = 1/(1+2) = 1/3."""
        np.testing.assert_allclose(_consonance_rating(1, 2), 1.0 / 3)

    def test_consonance_fifth(self):
        """C(2,3) = 1/(2+3) = 0.2."""
        np.testing.assert_allclose(_consonance_rating(2, 3), 0.2)

    def test_consonance_reduces_ratio(self):
        """C(4,6) should equal C(2,3) since 4:6 reduces to 2:3."""
        assert _consonance_rating(4, 6) == _consonance_rating(2, 3)

    def test_consonance_symmetric(self):
        assert _consonance_rating(3, 5) == _consonance_rating(5, 3)

    def test_consonance_decreases_with_complexity(self):
        """More complex ratios → smaller consonance."""
        assert _consonance_rating(1, 2) > _consonance_rating(7, 11)

    # --- _partition_by_octaves ---

    def test_partition_covers_all_modes(self):
        groups = _partition_by_octaves(16)
        all_indices = sorted(idx for g in groups for idx in g)
        assert all_indices == list(range(16))

    def test_partition_groups_are_disjoint(self):
        groups = _partition_by_octaves(20)
        seen = set()
        for g in groups:
            for idx in g:
                assert idx not in seen
                seen.add(idx)

    def test_partition_first_group_is_powers_of_two(self):
        """Group containing mode 1 (idx 0) should be {0, 1, 3, 7, 15, ...}."""
        groups = _partition_by_octaves(32)
        g0 = None
        for g in groups:
            if 0 in g:
                g0 = g
                break
        # Modes 1,2,4,8,16,32 → indices 0,1,3,7,15,31
        expected = [0, 1, 3, 7, 15, 31]
        assert g0 == expected

    def test_partition_odd_kernels(self):
        """Group containing mode 3 (idx 2) should be {2,5,11,23}."""
        groups = _partition_by_octaves(24)
        g3 = None
        for g in groups:
            if 2 in g:
                g3 = g
                break
        # Modes 3,6,12,24 → indices 2,5,11,23
        assert g3 == [2, 5, 11, 23]

    def test_partition_small(self):
        groups = _partition_by_octaves(4)
        all_idx = sorted(idx for g in groups for idx in g)
        assert all_idx == [0, 1, 2, 3]

    # --- _quantise ---

    def test_quantise_range(self):
        vals = np.array([0.0, 0.5, 1.0])
        q = _quantise(vals, 4)
        assert np.all(q >= 0)
        assert np.all(q < 4)

    def test_quantise_constant(self):
        vals = np.array([5.0, 5.0, 5.0])
        q = _quantise(vals, 4)
        np.testing.assert_array_equal(q, 0)

    def test_quantise_monotone(self):
        vals = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        q = _quantise(vals, 4)
        # Non-decreasing
        assert np.all(np.diff(q) >= 0)

    # --- _create_weighted_hopfield ---

    def test_hopfield_weights_symmetric(self):
        patterns = np.array([[1, -1, 1], [-1, 1, -1]])
        W = _create_weighted_hopfield(patterns.astype(float))
        np.testing.assert_allclose(W, W.T)

    def test_hopfield_weights_zero_diagonal(self):
        patterns = np.array([[1, -1, 1], [-1, 1, -1]])
        W = _create_weighted_hopfield(patterns.astype(float))
        np.testing.assert_allclose(np.diag(W), 0.0)

    def test_hopfield_weights_with_mode_weights(self):
        patterns = np.array([[1, -1, 1]], dtype=float)
        weights = np.array([2.0, 1.0, 0.5])
        W = _create_weighted_hopfield(patterns, weights)
        # W_ij should be scaled by w_i * w_j
        W_unif = _create_weighted_hopfield(patterns)
        expected = W_unif * np.outer(weights, weights)
        np.testing.assert_allclose(W, expected)

    # --- _corrupt_binary ---

    def test_corrupt_changes_pattern(self):
        rng = np.random.RandomState(0)
        p = np.array([1, -1, 1, -1, 1, -1, 1, -1], dtype=float)
        c = _corrupt_binary(p, 0.5, rng)
        assert not np.array_equal(p, c)

    def test_corrupt_fraction(self):
        rng = np.random.RandomState(0)
        p = np.ones(100, dtype=float)
        c = _corrupt_binary(p, 0.1, rng)
        flipped = int(np.sum(p != c))
        assert flipped == 10

    # --- _recall_with_weights ---

    def test_recall_perfect_query(self):
        patterns = np.array([[1, -1, 1, -1]], dtype=float)
        W = _create_weighted_hopfield(patterns)
        overlap = _recall_with_weights(W, patterns[0], patterns[0])
        assert overlap > 0.95

    # --- _sign_activation ---

    def test_sign_activation_positive(self):
        assert _sign_activation(0.5, "binary") == 1.0

    def test_sign_activation_negative(self):
        assert _sign_activation(-0.5, "binary") == -1.0

    def test_sign_activation_zero(self):
        assert _sign_activation(0.0, "binary") == 1.0

    # --- _perturbed_frequencies ---

    def test_perturbed_freq_shape(self):
        pos = _golden_positions(4)
        masses = np.array([0.01, 0.01, 0.01, 0.01])
        f = _perturbed_frequencies(10, pos, masses)
        assert f.shape == (10,)

    def test_perturbed_freq_zero_mass(self):
        pos = _golden_positions(4)
        masses = np.zeros(4)
        f = _perturbed_frequencies(5, pos, masses)
        # With no perturbation, f_n = n
        np.testing.assert_allclose(f, np.arange(1, 6, dtype=float))

    # --- _channel_crosstalk_matrix ---

    def test_crosstalk_diagonal_is_one(self):
        rng = np.random.RandomState(0)
        fps = rng.randn(50, 10)
        subsets = [np.array([0, 1, 2]), np.array([3, 4, 5])]
        M = _channel_crosstalk_matrix(fps, subsets)
        np.testing.assert_allclose(np.diag(M), 1.0, atol=1e-10)

    def test_crosstalk_shape(self):
        rng = np.random.RandomState(0)
        fps = rng.randn(50, 12)
        subsets = [np.array([0, 1, 2]), np.array([3, 4, 5]),
                   np.array([6, 7, 8]), np.array([9, 10, 11])]
        M = _channel_crosstalk_matrix(fps, subsets)
        assert M.shape == (4, 4)


# ═══════════════════════════════════════════════════════════════════════
# H-K1: Diatonic Partitioning
# ═══════════════════════════════════════════════════════════════════════

class TestDiatonicPartition:
    """H-K1 — Consonant partitioning reduces crosstalk vs uniform."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_diatonic_partition(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, DiatonicPartitionResult)

    def test_verdict_is_bool(self, result):
        assert isinstance(result.verdict, bool)

    def test_n_modes(self, result):
        assert result.n_modes == 40

    def test_channel_counts_match(self, result):
        assert result.n_channels_consonant == result.n_channels_uniform

    def test_crosstalk_nonneg(self, result):
        assert result.consonant_mean_crosstalk >= 0
        assert result.uniform_mean_crosstalk >= 0

    def test_capacity_positive(self, result):
        assert result.consonant_capacity_bits > 0
        assert result.uniform_capacity_bits > 0

    def test_groups_cover_all_modes(self, result):
        all_idx = sorted(idx for g in result.consonant_groups for idx in g)
        assert all_idx == list(range(result.n_modes))

    def test_seed_reproducibility(self):
        r1 = exp_diatonic_partition(seed=99)
        r2 = exp_diatonic_partition(seed=99)
        assert r1.crosstalk_reduction_pct == r2.crosstalk_reduction_pct


# ═══════════════════════════════════════════════════════════════════════
# H-K2: Consonance-Weighted Recall
# ═══════════════════════════════════════════════════════════════════════

class TestConsonanceRecall:
    """H-K2 — Consonance weighting improves noise tolerance."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_consonance_recall(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, ConsonanceRecallResult)

    def test_verdict_is_bool(self, result):
        assert isinstance(result.verdict, bool)

    def test_network_size(self, result):
        assert result.network_size == 30

    def test_n_patterns(self, result):
        assert result.n_patterns == 4

    def test_accuracy_range(self, result):
        assert 0 <= result.baseline_accuracy <= 1
        assert 0 <= result.consonance_accuracy <= 1

    def test_noise_fractions_ordered(self, result):
        assert np.all(np.diff(result.noise_fractions) > 0)

    def test_curves_correct_shape(self, result):
        n = len(result.noise_fractions)
        assert result.baseline_curve.shape == (n,)
        assert result.consonance_curve.shape == (n,)

    def test_curves_in_valid_range(self, result):
        assert np.all(result.baseline_curve >= 0)
        assert np.all(result.baseline_curve <= 1)
        assert np.all(result.consonance_curve >= 0)
        assert np.all(result.consonance_curve <= 1)

    def test_seed_reproducibility(self):
        r1 = exp_consonance_recall(seed=99)
        r2 = exp_consonance_recall(seed=99)
        assert r1.improvement_pct == r2.improvement_pct


# ═══════════════════════════════════════════════════════════════════════
# H-K3: Octave Equivalence
# ═══════════════════════════════════════════════════════════════════════

class TestOctaveEquivalence:
    """H-K3 — Modes n and 2n carry partially redundant information."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_octave_equivalence(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, OctaveEquivalenceResult)

    def test_verdict_is_bool(self, result):
        assert isinstance(result.verdict, bool)

    def test_octave_pairs_positive(self, result):
        assert result.n_octave_pairs > 0

    def test_pairs_valid(self, result):
        for n, n2 in result.mode_pairs:
            assert n2 == 2 * n

    def test_correlations_shape(self, result):
        assert result.correlations.shape == (result.n_octave_pairs,)

    def test_correlations_in_range(self, result):
        assert np.all(result.correlations >= -1.0)
        assert np.all(result.correlations <= 1.0)

    def test_mean_between_min_max(self, result):
        assert result.min_correlation <= result.mean_correlation <= result.max_correlation

    def test_error_detection_in_range(self, result):
        assert 0 <= result.error_detection_rate <= 1

    def test_seed_reproducibility(self):
        r1 = exp_octave_equivalence(seed=77)
        r2 = exp_octave_equivalence(seed=77)
        assert r1.mean_correlation == r2.mean_correlation

    def test_n_pairs_matches_half_modes(self, result):
        """With 40 modes, pairs (n,2n) for n=1..20 → 20 pairs."""
        assert result.n_octave_pairs == 20


# ═══════════════════════════════════════════════════════════════════════
# H-K4: Harmonic Series Capacity Scaling
# ═══════════════════════════════════════════════════════════════════════

class TestHarmonicScaling:
    """H-K4 — Capacity scales as ~ln(N)."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_harmonic_scaling(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, HarmonicScalingResult)

    def test_verdict_is_bool(self, result):
        assert isinstance(result.verdict, bool)

    def test_n_values_powers_of_two(self, result):
        for n in result.n_values:
            assert n & (n - 1) == 0  # power of 2

    def test_capacity_monotonically_increases(self, result):
        assert np.all(np.diff(result.cumulative_capacity) >= 0)

    def test_r_squared_in_range(self, result):
        # R² can be negative for very bad fit, but usually in [-1, 1] range
        assert result.log_fit_r_squared <= 1.0
        assert result.linear_fit_r_squared <= 1.0

    def test_marginal_shape(self, result):
        assert result.marginal_capacity.shape == result.n_values.shape

    def test_first_marginal_equals_first_cumulative(self, result):
        np.testing.assert_allclose(
            result.marginal_capacity[0],
            result.cumulative_capacity[0],
        )

    def test_seed_reproducibility(self):
        r1 = exp_harmonic_scaling(seed=99)
        r2 = exp_harmonic_scaling(seed=99)
        assert r1.log_fit_r_squared == r2.log_fit_r_squared


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

class TestRunAllKepler:
    """Integration tests for the experiment runner."""

    @pytest.fixture(scope="class")
    def results(self):
        return run_all_kepler(verbose=False)

    def test_returns_dict(self, results):
        assert isinstance(results, dict)

    def test_all_four_keys(self, results):
        assert set(results.keys()) == {"H-K1", "H-K2", "H-K3", "H-K4"}

    def test_result_types(self, results):
        assert isinstance(results["H-K1"], DiatonicPartitionResult)
        assert isinstance(results["H-K2"], ConsonanceRecallResult)
        assert isinstance(results["H-K3"], OctaveEquivalenceResult)
        assert isinstance(results["H-K4"], HarmonicScalingResult)

    def test_all_have_verdict(self, results):
        for v in results.values():
            assert isinstance(v.verdict, bool)
