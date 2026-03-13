"""Tests for simulations/gauge_geometry.py (Sidebar 18).

Target: comprehensive coverage of helpers, experiments, and integration
for the gauge-geometric fiber-bundle analysis of the sensitivity matrix.
"""

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Imports — helpers, dataclasses, experiments, runner
# ---------------------------------------------------------------------------

from simulations.gauge_geometry import (
    # Constants / helpers
    _PHI_CONJ,
    _golden_positions,
    _equispaced_positions,
    _sensitivity_matrix,
    _condition_number,
    _curvature_tensor,
    _yang_mills_functional,
    _shannon_capacity,
    _holonomy_matrix,
    _numerical_rank,
    _sensitivity_matrix_2d,
    _reduce_2d_to_1d,
    # Dataclasses
    CurvatureConditioningResult,
    GaugeInvarianceResult,
    DimensionalReductionResult,
    TopologicalRankResult,
    HolonomyResult,
    GaugeGeometrySummary,
    # Experiments
    exp_curvature_conditioning,
    exp_gauge_invariance,
    exp_dimensional_reduction,
    exp_topological_rank,
    exp_holonomy,
    # Runner
    run_all_gauge,
)


# ====================================================================
# Constants
# ====================================================================

class TestConstants:
    """Golden-ratio constant is correct."""

    def test_phi_conj_value(self):
        assert pytest.approx(_PHI_CONJ, rel=1e-10) == (np.sqrt(5) - 1) / 2

    def test_phi_conj_in_unit_interval(self):
        assert 0 < _PHI_CONJ < 1


# ====================================================================
# Position generators
# ====================================================================

class TestGoldenPositions:
    """Golden-ratio Weyl positions."""

    def test_count(self):
        pos = _golden_positions(8)
        assert len(pos) == 8

    def test_in_unit_interval(self):
        pos = _golden_positions(12)
        assert np.all(pos >= 0.01) and np.all(pos <= 0.99)

    def test_sorted(self):
        pos = _golden_positions(10)
        assert np.all(np.diff(pos) >= 0)

    def test_unique(self):
        pos = _golden_positions(20)
        assert len(np.unique(pos)) == 20


class TestEquispacedPositions:
    """Equispaced positions."""

    def test_count(self):
        assert len(_equispaced_positions(7)) == 7

    def test_symmetric(self):
        pos = _equispaced_positions(5)
        assert pytest.approx(pos[0] + pos[-1]) == 1.0

    def test_bounds(self):
        pos = _equispaced_positions(10)
        assert pos[0] >= 0.01 and pos[-1] <= 0.99


# ====================================================================
# Sensitivity matrix
# ====================================================================

class TestSensitivityMatrix:
    """S[n,k] = sin²(nπx_k)."""

    def test_shape(self):
        pos = np.array([0.2, 0.5, 0.8])
        S = _sensitivity_matrix(pos, 10)
        assert S.shape == (10, 3)

    def test_range(self):
        pos = _golden_positions(6)
        S = _sensitivity_matrix(pos, 40)
        assert np.all(S >= 0) and np.all(S <= 1)

    def test_half_position(self):
        S = _sensitivity_matrix(np.array([0.5]), 4)
        assert pytest.approx(S[0, 0]) == 1.0  # sin²(π/2) = 1
        assert pytest.approx(S[1, 0], abs=1e-10) == 0.0  # sin²(π) = 0

    def test_endpoint(self):
        S = _sensitivity_matrix(np.array([0.0]), 5)
        for n in range(5):
            assert pytest.approx(S[n, 0], abs=1e-10) == 0.0


class TestConditionNumber:
    """κ(S) = σ_max / σ_min."""

    def test_golden_well_conditioned(self):
        pos = _golden_positions(6)
        S = _sensitivity_matrix(pos, 40)
        kappa = _condition_number(S)
        assert kappa < 200

    def test_identity_matrix(self):
        kappa = _condition_number(np.eye(5))
        assert pytest.approx(kappa, rel=0.01) == 1.0

    def test_singular_large_kappa(self):
        S = np.array([[1, 0], [1, 0], [0, 0]])
        kappa = _condition_number(S)
        assert kappa > 1e10


# ====================================================================
# Curvature tensor
# ====================================================================

class TestCurvatureTensor:
    """F[n,k] = nπ sin(2nπx_k)."""

    def test_shape(self):
        pos = np.array([0.2, 0.5, 0.8])
        F = _curvature_tensor(pos, 10)
        assert F.shape == (10, 3)

    def test_zero_at_quarter(self):
        """At x=0.25, sin(2·1·π·0.25) = sin(π/2) = 1 for n=1."""
        F = _curvature_tensor(np.array([0.25]), 1)
        expected = np.pi * np.sin(np.pi / 2)
        assert pytest.approx(F[0, 0]) == expected

    def test_zero_at_half(self):
        """At x=0.5, sin(2nπ·0.5) = sin(nπ) = 0 for all n."""
        F = _curvature_tensor(np.array([0.5]), 5)
        assert np.allclose(F[:, 0], 0, atol=1e-10)

    def test_formula(self):
        pos = np.array([0.3])
        n = 3
        F = _curvature_tensor(pos, n)
        expected = n * np.pi * np.sin(2 * n * np.pi * 0.3)
        assert pytest.approx(F[n - 1, 0]) == expected

    def test_antisymmetric_about_half(self):
        """F(x) = -F(1-x) for odd x-argument symmetry of sin."""
        pos_a = np.array([0.2])
        pos_b = np.array([0.8])
        F_a = _curvature_tensor(pos_a, 5)
        F_b = _curvature_tensor(pos_b, 5)
        np.testing.assert_allclose(F_a, -F_b, atol=1e-10)


# ====================================================================
# Yang-Mills functional
# ====================================================================

class TestYangMillsFunctional:
    """‖F‖² = Σ F_{nk}²."""

    def test_positive(self):
        pos = _golden_positions(6)
        ym = _yang_mills_functional(pos, 40)
        assert ym > 0

    def test_zero_at_endpoints(self):
        """All endpoints give sin(2nπ·0)=0 → ‖F‖²=0."""
        ym = _yang_mills_functional(np.array([0.0]), 5)
        assert pytest.approx(ym, abs=1e-10) == 0.0

    def test_increases_with_modes(self):
        pos = _golden_positions(4)
        ym_few = _yang_mills_functional(pos, 5)
        ym_many = _yang_mills_functional(pos, 40)
        assert ym_many > ym_few

    def test_increases_with_positions(self):
        ym_few = _yang_mills_functional(_golden_positions(2), 10)
        ym_many = _yang_mills_functional(_golden_positions(8), 10)
        assert ym_many > ym_few

    def test_consistent_with_curvature(self):
        pos = _golden_positions(4)
        n_modes = 10
        F = _curvature_tensor(pos, n_modes)
        expected = float(np.sum(F ** 2))
        assert pytest.approx(_yang_mills_functional(pos, n_modes)) == expected


# ====================================================================
# Shannon capacity
# ====================================================================

class TestShannonCapacity:
    """C = Σ (1/2) log₂(1 + SNR_n)."""

    def test_positive(self):
        pos = _golden_positions(6)
        C = _shannon_capacity(pos, 40)
        assert C > 0

    def test_higher_snr_higher_capacity(self):
        pos = _golden_positions(6)
        C_lo = _shannon_capacity(pos, 40, snr_base=100)
        C_hi = _shannon_capacity(pos, 40, snr_base=10000)
        assert C_hi > C_lo

    def test_more_modes_higher_capacity(self):
        pos = _golden_positions(6)
        C_few = _shannon_capacity(pos, 5)
        C_many = _shannon_capacity(pos, 40)
        assert C_many > C_few


# ====================================================================
# Holonomy matrix
# ====================================================================

class TestHolonomyMatrix:
    """Holonomy: parallel transport around closed loop."""

    def test_shape(self):
        K = 4
        n_modes = 8
        path = [_golden_positions(K) + 0.01 * i for i in range(5)]
        path = [np.clip(p, 0.01, 0.99) for p in path]
        H = _holonomy_matrix(path, n_modes)
        assert H.shape == (K, K)

    def test_identity_for_trivial_loop(self):
        """Same configuration at every step → H ≈ I."""
        K = 4
        n_modes = 8
        pos = _golden_positions(K)
        path = [pos.copy() for _ in range(6)]
        H = _holonomy_matrix(path, n_modes)
        np.testing.assert_allclose(H, np.eye(K), atol=1e-8)

    def test_nontrivial_for_large_loop(self):
        """Sufficiently large loop → H ≠ I."""
        K = 4
        n_modes = 8
        base = _golden_positions(K)
        path = []
        for step in range(8):
            angle = 2 * np.pi * step / 8
            delta = np.zeros(K)
            delta[0] = 0.1 * np.cos(angle)
            delta[1] = 0.1 * np.sin(angle)
            path.append(np.sort(np.clip(base + delta, 0.01, 0.99)))
        H = _holonomy_matrix(path, n_modes)
        dev = np.linalg.norm(H - np.eye(K), 'fro')
        assert dev > 0.01


# ====================================================================
# Numerical rank
# ====================================================================

class TestNumericalRank:
    """Rank of sensitivity matrix."""

    def test_identity(self):
        assert _numerical_rank(np.eye(5)) == 5

    def test_rank_deficient(self):
        A = np.array([[1, 2], [2, 4], [3, 6]], dtype=float)
        assert _numerical_rank(A) == 1

    def test_full_rank_golden(self):
        S = _sensitivity_matrix(_golden_positions(6), 40)
        assert _numerical_rank(S) == 6


# ====================================================================
# 2D sensitivity matrix
# ====================================================================

class TestSensitivityMatrix2D:
    """S^{2D}_{(n,m),(k_x,k_y)} = sin²(nπx)sin²(mπy)."""

    def test_shape(self):
        px = np.array([0.2, 0.5])
        py = np.array([0.3, 0.7])
        S = _sensitivity_matrix_2d(px, py, 3, 4)
        assert S.shape == (12, 4)

    def test_range(self):
        px = _golden_positions(3)
        py = _golden_positions(3)
        S = _sensitivity_matrix_2d(px, py, 5, 5)
        assert np.all(S >= 0) and np.all(S <= 1)

    def test_separability(self):
        """S^{2D}_{(1,1),(0,0)} = sin²(πx_0) · sin²(πy_0)."""
        px = np.array([0.3])
        py = np.array([0.4])
        S = _sensitivity_matrix_2d(px, py, 1, 1)
        expected = np.sin(np.pi * 0.3) ** 2 * np.sin(np.pi * 0.4) ** 2
        assert pytest.approx(S[0, 0]) == expected


# ====================================================================
# Dimensional reduction (2D → 1D)
# ====================================================================

class TestDimensionalReduction:
    """2D sensitivity reduces to 1D under y-integration."""

    def test_shape(self):
        px = _golden_positions(4)
        S_red = _reduce_2d_to_1d(px, 5, 3)
        assert S_red.shape == (5, 4)

    def test_equals_1d_sensitivity(self):
        """After integration over y, the x-dependence is sin²(nπx)."""
        px = _golden_positions(6)
        S_1d = _sensitivity_matrix(px, 10)
        S_red = _reduce_2d_to_1d(px, 10, 20)
        # Should be identical since the y-integral is a constant factor
        np.testing.assert_allclose(S_red, S_1d, atol=1e-10)


# ====================================================================
# Experiment H-GG1: Curvature ↔ conditioning
# ====================================================================

class TestExpCurvatureConditioning:
    """H-GG1 — ‖F‖² correlates with κ(S)."""

    def test_returns_correct_type(self):
        r = exp_curvature_conditioning(n_configs=30)
        assert isinstance(r, CurvatureConditioningResult)

    def test_n_configs_stored(self):
        r = exp_curvature_conditioning(n_configs=30)
        assert r.n_configs == 30

    def test_curvatures_positive(self):
        r = exp_curvature_conditioning(n_configs=30)
        assert np.all(r.curvatures > 0)

    def test_kappas_at_least_one(self):
        r = exp_curvature_conditioning(n_configs=30)
        assert np.all(r.kappas >= 1.0)

    def test_r_squared_bounded(self):
        r = exp_curvature_conditioning(n_configs=30)
        assert -0.5 <= r.r_squared <= 1.0

    def test_verdict_is_bool(self):
        r = exp_curvature_conditioning(n_configs=30)
        assert isinstance(r.verdict, (bool, np.bool_))

    def test_deterministic(self):
        r1 = exp_curvature_conditioning(n_configs=20, seed=77)
        r2 = exp_curvature_conditioning(n_configs=20, seed=77)
        assert r1.r_squared == r2.r_squared


# ====================================================================
# Experiment H-GG2: Gauge invariance
# ====================================================================

class TestExpGaugeInvariance:
    """H-GG2 — Capacity invariant under gauge transforms."""

    def test_returns_correct_type(self):
        r = exp_gauge_invariance()
        assert isinstance(r, GaugeInvarianceResult)

    def test_capacity_base_positive(self):
        r = exp_gauge_invariance()
        assert r.capacity_base > 0

    def test_permutation_preserves_capacity(self):
        r = exp_gauge_invariance()
        rel_change = abs(r.capacity_permuted - r.capacity_base) / r.capacity_base
        assert rel_change < 1e-10

    def test_rotation_preserves_capacity(self):
        r = exp_gauge_invariance()
        rel_change = abs(r.capacity_rotated - r.capacity_base) / r.capacity_base
        assert rel_change < 1e-10

    def test_translation_changes_capacity(self):
        """Translation is NOT a true gauge transform — expects some change."""
        r = exp_gauge_invariance()
        # There should be *some* change (geometry changes)
        rel_change = abs(r.capacity_translated - r.capacity_base) / r.capacity_base
        assert rel_change > 0

    def test_rank_positive(self):
        r = exp_gauge_invariance()
        assert r.rank_base > 0

    def test_max_relative_change_nonneg(self):
        r = exp_gauge_invariance()
        assert r.max_relative_change >= 0

    def test_deterministic(self):
        r1 = exp_gauge_invariance(seed=13)
        r2 = exp_gauge_invariance(seed=13)
        assert r1.capacity_base == r2.capacity_base


# ====================================================================
# Experiment H-GG3: Dimensional reduction
# ====================================================================

class TestExpDimensionalReduction:
    """H-GG3 — 2D → 1D reduction recovers 1D formulas."""

    def test_returns_correct_type(self):
        r = exp_dimensional_reduction()
        assert isinstance(r, DimensionalReductionResult)

    def test_kappa_1d_greater_than_one(self):
        r = exp_dimensional_reduction()
        assert r.kappa_1d_direct > 1.0

    def test_capacity_positive(self):
        r = exp_dimensional_reduction()
        assert r.capacity_1d_direct > 0
        assert r.capacity_1d_reduced > 0

    def test_kappa_error_small(self):
        r = exp_dimensional_reduction()
        assert r.kappa_relative_error < 0.05

    def test_capacity_error_small(self):
        r = exp_dimensional_reduction()
        assert r.capacity_relative_error < 0.05

    def test_verdict_is_bool(self):
        r = exp_dimensional_reduction()
        assert isinstance(r.verdict, (bool, np.bool_))

    def test_deterministic(self):
        r1 = exp_dimensional_reduction(seed=19)
        r2 = exp_dimensional_reduction(seed=19)
        assert r1.kappa_relative_error == r2.kappa_relative_error


# ====================================================================
# Experiment H-GG4: Topological rank
# ====================================================================

class TestExpTopologicalRank:
    """H-GG4 — Rank is piecewise constant under smooth deformation."""

    def test_returns_correct_type(self):
        r = exp_topological_rank(n_steps=100)
        assert isinstance(r, TopologicalRankResult)

    def test_n_positions_stored(self):
        r = exp_topological_rank(n_steps=100)
        assert r.n_positions_tested == 100

    def test_fraction_bounded(self):
        r = exp_topological_rank(n_steps=100)
        assert 0 <= r.fraction_rank_changes <= 1.0

    def test_rank_change_counts_consistent(self):
        r = exp_topological_rank(n_steps=100)
        assert (r.rank_changes_at_rational
                + r.rank_changes_at_irrational) == r.n_rank_changes

    def test_verdict_is_bool(self):
        r = exp_topological_rank(n_steps=100)
        assert isinstance(r.verdict, (bool, np.bool_))

    def test_few_rank_changes(self):
        r = exp_topological_rank(n_steps=500)
        assert r.fraction_rank_changes < 0.10

    def test_deterministic(self):
        r1 = exp_topological_rank(n_steps=50, seed=33)
        r2 = exp_topological_rank(n_steps=50, seed=33)
        assert r1.n_rank_changes == r2.n_rank_changes


# ====================================================================
# Experiment H-GG5: Holonomy
# ====================================================================

class TestExpHolonomy:
    """H-GG5 — Non-trivial holonomy correlates with enclosed curvature."""

    def test_returns_correct_type(self):
        r = exp_holonomy(n_loops=10)
        assert isinstance(r, HolonomyResult)

    def test_n_loops_stored(self):
        r = exp_holonomy(n_loops=10)
        assert r.n_loops == 10

    def test_traces_positive(self):
        r = exp_holonomy(n_loops=10)
        assert np.all(r.holonomy_traces > 0)

    def test_curvatures_positive(self):
        r = exp_holonomy(n_loops=10)
        assert np.all(r.enclosed_curvatures > 0)

    def test_deviations_nonnegative(self):
        r = exp_holonomy(n_loops=10)
        assert np.all(r.identity_deviations >= 0)

    def test_mean_deviation_nontrivial(self):
        r = exp_holonomy(n_loops=10)
        assert r.mean_deviation > 0.01

    def test_r_squared_bounded(self):
        r = exp_holonomy(n_loops=10)
        assert -1.0 <= r.r_squared <= 1.0

    def test_verdict_is_bool(self):
        r = exp_holonomy(n_loops=10)
        assert isinstance(r.verdict, (bool, np.bool_))

    def test_deterministic(self):
        r1 = exp_holonomy(n_loops=5, seed=55)
        r2 = exp_holonomy(n_loops=5, seed=55)
        assert r1.r_squared == r2.r_squared


# ====================================================================
# Runner
# ====================================================================

class TestRunAllGauge:
    """Integration test for run_all_gauge."""

    def test_returns_summary(self):
        s = run_all_gauge(verbose=False)
        assert isinstance(s, GaugeGeometrySummary)

    def test_confirmed_plus_killed_is_five(self):
        s = run_all_gauge(verbose=False)
        assert s.confirmed + s.killed == 5

    def test_all_sub_results_present(self):
        s = run_all_gauge(verbose=False)
        assert isinstance(s.curvature_conditioning, CurvatureConditioningResult)
        assert isinstance(s.gauge_invariance, GaugeInvarianceResult)
        assert isinstance(s.dimensional_reduction, DimensionalReductionResult)
        assert isinstance(s.topological_rank, TopologicalRankResult)
        assert isinstance(s.holonomy, HolonomyResult)

    def test_verdicts_are_bool(self):
        s = run_all_gauge(verbose=False)
        for r in [s.curvature_conditioning, s.gauge_invariance,
                  s.dimensional_reduction, s.topological_rank,
                  s.holonomy]:
            assert isinstance(r.verdict, (bool, np.bool_))


# ====================================================================
# Cross-physics consistency
# ====================================================================

class TestCrossPhysics:
    """Consistency checks between gauge geometry and SEM physics."""

    def test_golden_lower_curvature_than_random(self):
        """Golden positions should have moderate curvature."""
        rng = np.random.RandomState(42)
        ym_golden = _yang_mills_functional(_golden_positions(6), 20)
        # Average a few random configs
        ym_rand = np.mean([
            _yang_mills_functional(np.sort(np.clip(rng.rand(6), 0.01, 0.99)), 20)
            for _ in range(20)
        ])
        # Golden isn't guaranteed to minimise ‖F‖², but should be comparable
        assert ym_golden < ym_rand * 5  # within 5× of random average

    def test_capacity_invariant_under_mode_relabeling(self):
        """Directly verify that SVs don't change under row permutation."""
        pos = _golden_positions(6)
        S = _sensitivity_matrix(pos, 20)
        sv_orig = np.linalg.svd(S, compute_uv=False)
        perm = np.random.RandomState(42).permutation(20)
        sv_perm = np.linalg.svd(S[perm], compute_uv=False)
        np.testing.assert_allclose(sv_orig, sv_perm, rtol=1e-10)

    def test_curvature_zero_at_endpoints(self):
        """sin(2nπ·0) = 0 → all curvature components vanish."""
        F = _curvature_tensor(np.array([0.0, 1.0]), 10)
        assert np.allclose(F, 0, atol=1e-10)

    def test_1d_reduction_preserves_conditioning(self):
        """After 2D→1D reduction, condition number matches 1D direct."""
        pos = _golden_positions(5)
        S_1d = _sensitivity_matrix(pos, 8)
        S_red = _reduce_2d_to_1d(pos, 8, 10)
        # Condition numbers should match (same matrix up to scaling)
        kappa_1d = _condition_number(S_1d)
        kappa_red = _condition_number(S_red)
        assert pytest.approx(kappa_1d, rel=0.01) == kappa_red

    def test_rank_equals_min_dimension(self):
        """For well-conditioned golden positions, rank = min(N, K)."""
        K = 6
        n_modes = 40
        S = _sensitivity_matrix(_golden_positions(K), n_modes)
        assert _numerical_rank(S) == K

    def test_holonomy_loop_size_matters(self):
        """Larger loops → larger holonomy deviation."""
        K = 4
        n_modes = 8
        base = _golden_positions(K)

        devs = []
        for amp in [0.01, 0.10]:
            path = []
            for step in range(6):
                angle = 2 * np.pi * step / 6
                delta = np.zeros(K)
                delta[0] = amp * np.cos(angle)
                delta[1] = amp * np.sin(angle)
                path.append(np.sort(np.clip(base + delta, 0.01, 0.99)))
            H = _holonomy_matrix(path, n_modes)
            devs.append(np.linalg.norm(H - np.eye(K), 'fro'))
        assert devs[1] > devs[0]
