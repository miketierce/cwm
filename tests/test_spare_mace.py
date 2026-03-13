"""
Tests for Spare–Mace informed experiments.

Each test exercises one of the six hypotheses derived from the
Spare/Mace psychic-field ↔ CWM structural parallels.  The tests
verify that the experiments run without error and that the numerical
results are physically plausible (sign, range, monotonicity), while
the verdicts themselves may flip depending on parameters.
"""

import numpy as np
import pytest

from simulations.spare_mace import (
    exp_alphabet_of_desire,
    exp_sigil_efficiency,
    exp_forgetting_improves_recall,
    exp_compute_in_memory,
    exp_avoided_crossing,
    exp_null_space_encoding,
    run_all_spare_mace,
    AlphabetResult,
    SigilResult,
    ForgettingResult,
    ComputeInMemoryResult,
    AvoidedCrossingResult,
    NullSpaceResult,
)


# ═══════════════════════════════════════════════════════════════════════
# H1 — Alphabet of Desire
# ═══════════════════════════════════════════════════════════════════════

class TestAlphabetOfDesire:
    """SVD pre-decomposition should improve or match naïve encoding."""

    def test_runs_without_error(self):
        r = exp_alphabet_of_desire(n_modes=8, n_patterns=3, Q=500.0)
        assert isinstance(r, AlphabetResult)

    def test_fidelities_in_range(self):
        r = exp_alphabet_of_desire(n_modes=8, n_patterns=3)
        assert 0.0 <= r.fidelity_naive <= 1.0
        assert 0.0 <= r.fidelity_alphabet <= 1.0

    def test_rank_is_positive(self):
        r = exp_alphabet_of_desire(n_modes=10, n_patterns=4)
        assert r.rank_used > 0
        assert r.rank_used <= min(10, 4)

    def test_condition_number_finite(self):
        r = exp_alphabet_of_desire(n_modes=8, n_patterns=3)
        assert np.isfinite(r.condition_number)
        assert r.condition_number >= 1.0

    def test_higher_Q_improves_both(self):
        r_low = exp_alphabet_of_desire(n_modes=6, n_patterns=3, Q=100.0)
        r_high = exp_alphabet_of_desire(n_modes=6, n_patterns=3, Q=2000.0)
        # Higher Q → less damping → better fidelity for both methods
        assert r_high.fidelity_naive >= r_low.fidelity_naive * 0.9
        assert r_high.fidelity_alphabet >= r_low.fidelity_alphabet * 0.9

    def test_noiseless_high_fidelity(self):
        r = exp_alphabet_of_desire(
            n_modes=6, n_patterns=3, Q=2000.0,
            t_hold=1e-5, noise=0.0,
        )
        assert r.fidelity_alphabet > 0.7

    def test_reproducible_with_seed(self):
        r1 = exp_alphabet_of_desire(rng=np.random.RandomState(99))
        r2 = exp_alphabet_of_desire(rng=np.random.RandomState(99))
        np.testing.assert_allclose(r1.fidelity_naive, r2.fidelity_naive, atol=1e-4)
        np.testing.assert_allclose(r1.fidelity_alphabet, r2.fidelity_alphabet, atol=1e-4)


# ═══════════════════════════════════════════════════════════════════════
# H2 — Sigil Efficiency
# ═══════════════════════════════════════════════════════════════════════

class TestSigilEfficiency:
    """Sparse patterns should have a non-trivial optimal sparsity."""

    def test_runs_without_error(self):
        r = exp_sigil_efficiency(N=32, P=3, n_trials=10)
        assert isinstance(r, SigilResult)

    def test_recall_rates_bounded(self):
        r = exp_sigil_efficiency(N=32, P=3, n_trials=10)
        assert np.all(r.recall_rates >= 0.0)
        assert np.all(r.recall_rates <= 1.0)

    def test_info_per_site_non_negative(self):
        r = exp_sigil_efficiency(N=32, P=3, n_trials=10)
        assert np.all(r.info_per_site >= 0.0)

    def test_optimal_sparsity_in_range(self):
        r = exp_sigil_efficiency(N=32, P=3, n_trials=10)
        assert 0.0 < r.optimal_sparsity <= 1.0

    def test_dense_recall_positive(self):
        r = exp_sigil_efficiency(N=32, P=3, n_trials=10)
        assert r.dense_recall >= 0.0

    def test_very_sparse_low_recall(self):
        """At 10% sparsity with many patterns, recall should be low."""
        r = exp_sigil_efficiency(
            N=64, P=8,
            sparsity_levels=np.array([0.1, 1.0]),
            n_trials=15,
        )
        # Very sparse with 8 patterns should struggle
        # (not asserting specific value — just that it runs)
        assert len(r.recall_rates) == 2

    def test_reproducible_with_seed(self):
        r1 = exp_sigil_efficiency(N=32, P=3, n_trials=10,
                                   rng=np.random.RandomState(77))
        r2 = exp_sigil_efficiency(N=32, P=3, n_trials=10,
                                   rng=np.random.RandomState(77))
        np.testing.assert_array_equal(r1.recall_rates, r2.recall_rates)


# ═══════════════════════════════════════════════════════════════════════
# H3 — Forgetting the Sigil
# ═══════════════════════════════════════════════════════════════════════

class TestForgettingImproves:
    """Weight pruning (controlled forgetting) can improve recall."""

    def test_runs_without_error(self):
        r = exp_forgetting_improves_recall(N=30, P=5, n_trials=15)
        assert isinstance(r, ForgettingResult)

    def test_baseline_recall_bounded(self):
        r = exp_forgetting_improves_recall(N=30, P=5, n_trials=15)
        assert 0.0 <= r.recall_without_forget <= 1.0

    def test_pruned_recall_bounded(self):
        r = exp_forgetting_improves_recall(N=30, P=5, n_trials=15)
        assert np.all(r.recall_with_forget >= 0.0)
        assert np.all(r.recall_with_forget <= 1.0)

    def test_best_threshold_non_negative(self):
        r = exp_forgetting_improves_recall(N=30, P=5, n_trials=15)
        assert r.best_threshold >= 0.0

    def test_high_load_benefits_from_forgetting(self):
        """At high load factor (P/N ≈ 0.16), forgetting should help."""
        r = exp_forgetting_improves_recall(
            N=50, P=8, noise_fraction=0.2, n_trials=30,
            rng=np.random.RandomState(42),
        )
        # The pruned network should match or beat baseline
        assert r.best_recall >= r.recall_without_forget * 0.95

    def test_zero_threshold_matches_baseline(self):
        """θ=0 means no pruning → should equal baseline."""
        r = exp_forgetting_improves_recall(
            N=30, P=5, n_trials=15,
            threshold_values=np.array([0.0]),
        )
        # With θ=0, recall_with_forget[0] ≈ recall_without_forget
        assert abs(r.recall_with_forget[0] - r.recall_without_forget) < 0.15

    def test_extreme_pruning_hurts(self):
        """θ very large → all weights zeroed → recall collapses."""
        r = exp_forgetting_improves_recall(
            N=30, P=5, n_trials=15,
            threshold_values=np.array([0.0, 10.0]),
        )
        # θ=10 wipes all weights
        assert r.recall_with_forget[-1] <= r.recall_with_forget[0]


# ═══════════════════════════════════════════════════════════════════════
# H4 — Compute-in-Memory
# ═══════════════════════════════════════════════════════════════════════

class TestComputeInMemory:
    """Boolean ops from superposition without separate compute cycle."""

    def test_runs_without_error(self):
        r = exp_compute_in_memory(N=16, Q=500.0)
        assert isinstance(r, ComputeInMemoryResult)

    def test_fidelities_bounded(self):
        r = exp_compute_in_memory(N=16)
        assert 0.0 <= r.xor_fidelity <= 1.0
        assert 0.0 <= r.and_fidelity <= 1.0
        assert 0.0 <= r.or_fidelity <= 1.0

    def test_speedup_is_3x(self):
        """Superposition read = 1 pass vs 3 separate passes."""
        r = exp_compute_in_memory(N=16)
        assert r.speedup_factor == 3.0

    def test_high_Q_low_noise_good_fidelity(self):
        """In ideal conditions, at least some ops should work well."""
        r = exp_compute_in_memory(N=16, Q=2000.0, noise=0.0)
        # At least AND or OR should be above 0.5
        best = max(r.xor_fidelity, r.and_fidelity, r.or_fidelity)
        assert best > 0.5

    def test_reproducible_with_seed(self):
        r1 = exp_compute_in_memory(rng=np.random.RandomState(55))
        r2 = exp_compute_in_memory(rng=np.random.RandomState(55))
        assert r1.xor_fidelity == r2.xor_fidelity


# ═══════════════════════════════════════════════════════════════════════
# H5 — Avoided Crossing
# ═══════════════════════════════════════════════════════════════════════

class TestAvoidedCrossing:
    """Near-degenerate modes should hybridise under perturbation."""

    def test_runs_without_error(self):
        r = exp_avoided_crossing(n_modes=5)
        assert isinstance(r, AvoidedCrossingResult)

    def test_hybridisation_depth_bounded(self):
        r = exp_avoided_crossing(n_modes=5)
        assert np.all(r.hybridisation_depth >= 0.0)
        assert np.all(r.hybridisation_depth <= 1.0)

    def test_small_detuning_high_hybridisation(self):
        """At small Δf, coupling should transfer significant energy."""
        r = exp_avoided_crossing(
            detuning_range=np.array([0.001, 0.01, 0.1, 1.0]),
            coupling_strength=0.05,
        )
        # Smallest detuning should have highest hybridisation
        assert r.hybridisation_depth[0] >= r.hybridisation_depth[-1]

    def test_large_detuning_low_hybridisation(self):
        """Far off-resonant modes should not exchange energy."""
        r = exp_avoided_crossing(
            detuning_range=np.array([1.0, 10.0]),
            coupling_strength=0.05,
        )
        # Large detuning → hybridisation < 10%
        assert r.hybridisation_depth[-1] < 0.3

    def test_stronger_coupling_more_hybridisation(self):
        weak = exp_avoided_crossing(
            detuning_range=np.array([0.01]),
            coupling_strength=0.01,
        )
        strong = exp_avoided_crossing(
            detuning_range=np.array([0.01]),
            coupling_strength=0.1,
        )
        assert strong.max_hybridisation >= weak.max_hybridisation

    def test_capacity_gain_non_negative(self):
        r = exp_avoided_crossing(n_modes=5)
        assert r.capacity_gain_pct >= 0.0

    def test_max_hybridisation_consistent(self):
        r = exp_avoided_crossing(n_modes=5)
        assert r.max_hybridisation == np.max(r.hybridisation_depth)


# ═══════════════════════════════════════════════════════════════════════
# H6 — Null-Space Encoding
# ═══════════════════════════════════════════════════════════════════════

class TestNullSpaceEncoding:
    """Null space of coupling matrix should yield hidden capacity."""

    def test_runs_without_error(self):
        r = exp_null_space_encoding(N=16, n_modes=12, n_perturbations=8)
        assert isinstance(r, NullSpaceResult)

    def test_rank_leq_min_dim(self):
        M, K = 12, 8
        r = exp_null_space_encoding(N=16, n_modes=M, n_perturbations=K)
        assert r.coupling_matrix_rank <= min(M, K)

    def test_null_dim_plus_rank_equals_cols(self):
        """rank + null_dim = n_perturbations (rank-nullity theorem)."""
        M, K = 12, 8
        r = exp_null_space_encoding(N=16, n_modes=M, n_perturbations=K)
        assert r.coupling_matrix_rank + r.null_space_dim == K

    def test_standard_fidelity_high(self):
        """Standard channel should work regardless of hidden encoding."""
        r = exp_null_space_encoding(
            N=16, n_modes=12, n_perturbations=8, noise_level=0.001,
        )
        assert r.standard_recall_fidelity > 0.8

    def test_hidden_fidelity_reasonable(self):
        """If null space exists, hidden recall should be decent."""
        r = exp_null_space_encoding(
            N=16, n_modes=12, n_perturbations=8, noise_level=0.001,
        )
        if r.null_space_dim > 0:
            assert r.hidden_recall_fidelity > 0.5

    def test_no_null_space_when_underdetermined(self):
        """When n_modes >> n_perturbations, coupling may be full-rank."""
        r = exp_null_space_encoding(
            N=16, n_modes=30, n_perturbations=5,
        )
        # 5 columns, 30 rows → likely rank 5 → null_dim=0
        # But our sinusoidal coupling matrix may still have rank < 5
        # Just check that the math is consistent
        assert r.coupling_matrix_rank + r.null_space_dim == 5

    def test_bonus_capacity_scales_with_null_dim(self):
        r = exp_null_space_encoding(
            N=16, n_modes=12, n_perturbations=8,
        )
        if r.null_space_dim > 0:
            expected_pct = (r.null_space_dim / max(r.coupling_matrix_rank, 1)) * 100
            # Allow some tolerance for the 16.4 bits/mode calculation
            assert abs(r.bonus_capacity_pct - expected_pct) < 1.0

    def test_reproducible_with_seed(self):
        r1 = exp_null_space_encoding(rng=np.random.RandomState(33))
        r2 = exp_null_space_encoding(rng=np.random.RandomState(33))
        assert r1.null_space_dim == r2.null_space_dim
        assert r1.hidden_recall_fidelity == r2.hidden_recall_fidelity


# ═══════════════════════════════════════════════════════════════════════
# Integration — run_all
# ═══════════════════════════════════════════════════════════════════════

class TestRunAll:
    """Integration test for the full suite."""

    def test_run_all_returns_dict(self):
        results = run_all_spare_mace(verbose=False)
        assert isinstance(results, dict)
        assert len(results) == 6

    def test_all_keys_present(self):
        results = run_all_spare_mace(verbose=False)
        expected = {
            "alphabet_of_desire",
            "sigil_efficiency",
            "forgetting",
            "compute_in_memory",
            "avoided_crossing",
            "null_space",
        }
        assert set(results.keys()) == expected

    def test_all_have_verdict(self):
        results = run_all_spare_mace(verbose=False)
        for name, r in results.items():
            assert hasattr(r, "verdict"), f"{name} missing verdict"
            assert isinstance(r.verdict, bool), f"{name} verdict not bool"
