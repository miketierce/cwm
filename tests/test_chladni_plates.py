"""
Tests for Chladni-informed 2D plate eigenmode memory experiments.

Each test class exercises one of the four hypotheses derived from
structural parallels between Ernst Chladni's vibrating-plate experiments
(1787) and Spectral Eigenmode Memory (SEM) physics.

Tests verify that experiments run without error, that numerical results
are physically plausible (sign, range, monotonicity), and that results
are reproducible with a fixed RNG seed.
"""

import numpy as np
import pytest

from simulations.chladni_plates import (
    # Experiments
    exp_plate_mode_count,
    exp_symmetry_partition,
    exp_placement_comparison,
    exp_degeneracy_splitting,
    run_all_chladni,
    # Result types
    ModeCountResult,
    SymmetryPartitionResult,
    PlacementComparisonResult,
    DegeneracySplittingResult,
    # Helpers
    plate_eigenfrequency,
    plate_mode_shape,
    plate_sensitivity_2d,
    n_max_formula,
    enumerate_plate_modes,
    classify_symmetry,
    build_plate_sensitivity_matrix,
    _golden_ratio_positions_2d,
)


# ═══════════════════════════════════════════════════════════════════════
# Helper function tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Unit tests for plate physics helper functions."""

    def test_plate_eigenfrequency_positive(self):
        f = plate_eigenfrequency(1, 1, a=1.0, b=1.0, D=1.0, rho_h=1.0)
        assert f > 0

    def test_plate_eigenfrequency_increases_with_mode_index(self):
        f11 = plate_eigenfrequency(1, 1, a=1.0, b=1.0, D=1.0, rho_h=1.0)
        f21 = plate_eigenfrequency(2, 1, a=1.0, b=1.0, D=1.0, rho_h=1.0)
        f22 = plate_eigenfrequency(2, 2, a=1.0, b=1.0, D=1.0, rho_h=1.0)
        assert f21 > f11
        assert f22 > f21

    def test_plate_eigenfrequency_degenerate_square(self):
        """For a square plate, f(n,m) = f(m,n)."""
        f12 = plate_eigenfrequency(1, 2, a=1.0, b=1.0, D=1.0, rho_h=1.0)
        f21 = plate_eigenfrequency(2, 1, a=1.0, b=1.0, D=1.0, rho_h=1.0)
        assert f12 == pytest.approx(f21)

    def test_plate_eigenfrequency_non_degenerate_rect(self):
        """For a rectangular plate (a≠b), f(n,m) ≠ f(m,n)."""
        f12 = plate_eigenfrequency(1, 2, a=1.0, b=2.0, D=1.0, rho_h=1.0)
        f21 = plate_eigenfrequency(2, 1, a=1.0, b=2.0, D=1.0, rho_h=1.0)
        assert f12 != pytest.approx(f21, abs=1e-6)

    def test_plate_mode_shape_zero_at_edges(self):
        """Simply-supported: φ(0,y) = φ(a,y) = φ(x,0) = φ(x,b) = 0."""
        x = np.array([0.0, 1.0, 0.5, 0.5])
        y = np.array([0.5, 0.5, 0.0, 1.0])
        vals = plate_mode_shape(1, 1, x, y, a=1.0, b=1.0)
        np.testing.assert_allclose(vals, 0.0, atol=1e-15)

    def test_plate_mode_shape_max_at_center_11(self):
        """Mode (1,1) has maximum at plate center."""
        val = plate_mode_shape(1, 1, np.array([0.5]), np.array([0.5]),
                                a=1.0, b=1.0)
        assert val[0] == pytest.approx(1.0)

    def test_plate_sensitivity_non_negative(self):
        """sin²(…) · sin²(…) ≥ 0 always."""
        x = np.linspace(0.01, 0.99, 50)
        y = np.linspace(0.01, 0.99, 50)
        xx, yy = np.meshgrid(x, y)
        vals = plate_sensitivity_2d(3, 5, xx, yy, a=1.0, b=1.0)
        assert np.all(vals >= 0)

    def test_plate_sensitivity_max_one(self):
        """sin²(…) · sin²(…) ≤ 1 always."""
        x = np.linspace(0.01, 0.99, 100)
        y = np.linspace(0.01, 0.99, 100)
        xx, yy = np.meshgrid(x, y)
        vals = plate_sensitivity_2d(1, 1, xx, yy, a=1.0, b=1.0)
        assert np.all(vals <= 1.0 + 1e-15)

    def test_n_max_formula_paper_value(self):
        """Paper: n_max = 9,380 for α=3.3e-6, Q=10000, ΔT=1 K."""
        assert n_max_formula(3.3e-6, 1.0, 10_000.0) == 9380

    def test_n_max_formula_higher_alpha_fewer(self):
        assert n_max_formula(10e-6, 1.0, 10_000.0) < n_max_formula(3.3e-6, 1.0, 10_000.0)

    def test_n_max_formula_higher_Q_more(self):
        assert n_max_formula(3.3e-6, 1.0, 50_000.0) > n_max_formula(3.3e-6, 1.0, 10_000.0)

    def test_enumerate_plate_modes_count(self):
        modes = enumerate_plate_modes(5)
        assert len(modes) == 25  # 5 × 5

    def test_enumerate_plate_modes_sorted_by_frequency(self):
        modes = enumerate_plate_modes(10)
        freq = [n ** 2 + m ** 2 for n, m in modes]
        assert freq == sorted(freq)

    def test_enumerate_plate_modes_all_valid(self):
        modes = enumerate_plate_modes(4)
        for n, m in modes:
            assert 1 <= n <= 4
            assert 1 <= m <= 4

    def test_classify_symmetry_four_classes(self):
        assert classify_symmetry(1, 1) == "AA"
        assert classify_symmetry(1, 2) == "AS"
        assert classify_symmetry(2, 1) == "SA"
        assert classify_symmetry(2, 2) == "SS"

    def test_classify_symmetry_all_modes(self):
        classes = set()
        for n in range(1, 5):
            for m in range(1, 5):
                classes.add(classify_symmetry(n, m))
        assert classes == {"AA", "AS", "SA", "SS"}

    def test_build_sensitivity_matrix_shape(self):
        modes = [(1, 1), (1, 2), (2, 1)]
        sites = np.array([[0.3, 0.4], [0.7, 0.6]])
        S = build_plate_sensitivity_matrix(modes, sites)
        assert S.shape == (3, 2)

    def test_build_sensitivity_matrix_non_negative(self):
        modes = enumerate_plate_modes(4)
        sites = _golden_ratio_positions_2d(5)
        S = build_plate_sensitivity_matrix(modes, sites)
        assert np.all(S >= 0)

    def test_golden_ratio_positions_in_bounds(self):
        pos = _golden_ratio_positions_2d(20)
        assert pos.shape == (20, 2)
        assert np.all(pos >= 0.05)
        assert np.all(pos <= 0.95)

    def test_golden_ratio_positions_low_discrepancy(self):
        """No two points should be very close (quasi-random property)."""
        pos = _golden_ratio_positions_2d(50)
        from scipy.spatial.distance import pdist
        dists = pdist(pos)
        assert dists.min() > 0.01  # no two points within 1% of unit square


# ═══════════════════════════════════════════════════════════════════════
# H-C1 — 2D Plate Mode Count vs 1D Rod
# ═══════════════════════════════════════════════════════════════════════

class TestPlateModeCount:
    """2D plate should have ≥ 4× the modes of a 1D rod."""

    def test_runs_without_error(self):
        r = exp_plate_mode_count(Q=1000.0)
        assert isinstance(r, ModeCountResult)

    def test_rod_n_max_matches_formula(self):
        """n_max_formula is tested in TestHelpers; verify consistency."""
        r = exp_plate_mode_count(Q=1000.0)
        assert r.rod_n_max == n_max_formula(3.3e-6, 1.0, 1000.0)

    def test_plate_n_max_per_axis_matches_rod(self):
        r = exp_plate_mode_count(Q=1000.0)
        assert r.plate_n_max_per_axis == r.rod_n_max

    def test_plate_exceeds_rod_by_4x(self):
        r = exp_plate_mode_count(Q=1000.0)
        assert r.plate_mode_count >= 4 * r.rod_mode_count

    def test_mode_ratio_at_least_4(self):
        r = exp_plate_mode_count(Q=1000.0)
        assert r.mode_ratio >= 4.0

    def test_mode_ratio_range(self):
        """Theory: ratio ≈ 9× after resolvability filter."""
        r = exp_plate_mode_count(Q=1000.0)
        assert 5.0 < r.mode_ratio < 15.0

    def test_density_gain_positive(self):
        r = exp_plate_mode_count(Q=1000.0)
        assert r.plate_density_gain > 1.0

    def test_higher_Q_increases_both(self):
        r_low = exp_plate_mode_count(Q=500.0)
        r_high = exp_plate_mode_count(Q=2000.0)
        assert r_high.rod_mode_count > r_low.rod_mode_count
        assert r_high.plate_mode_count > r_low.plate_mode_count

    def test_higher_alpha_decreases_modes(self):
        r_low = exp_plate_mode_count(alpha=1e-6, Q=500.0)
        r_high = exp_plate_mode_count(alpha=50e-6, Q=500.0)
        assert r_low.plate_mode_count > r_high.plate_mode_count

    def test_verdict_confirmed(self):
        r = exp_plate_mode_count(Q=1000.0)
        assert r.verdict is True


# ═══════════════════════════════════════════════════════════════════════
# H-C2 — Symmetry-Class Readout Partitioning
# ═══════════════════════════════════════════════════════════════════════

class TestSymmetryPartition:
    """Plate modes should partition into ≥ 3 independent channels."""

    def test_runs_without_error(self):
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert isinstance(r, SymmetryPartitionResult)

    def test_four_symmetry_classes(self):
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert r.n_symmetry_classes == 4

    def test_class_labels_correct(self):
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert set(r.class_labels) == {"AA", "AS", "SA", "SS"}

    def test_modes_sum_to_total(self):
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert np.sum(r.modes_per_class) == r.n_modes_total

    def test_cross_correlation_bounded(self):
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert 0.0 <= r.cross_correlation <= 1.0

    def test_cross_correlation_low(self):
        """Independent classes should have low mutual correlation."""
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert r.cross_correlation < 0.3

    def test_at_least_3_channels(self):
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert r.independent_channels >= 3

    def test_polysemic_gain_positive(self):
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert r.polysemic_capacity_gain_pct > 0

    def test_polysemic_gain_matches_channels(self):
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        expected = (r.independent_channels - 1) * 100.0
        assert r.polysemic_capacity_gain_pct == pytest.approx(expected)

    def test_reproducible(self):
        r1 = exp_symmetry_partition(rng=np.random.RandomState(42))
        r2 = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert r1.cross_correlation == pytest.approx(r2.cross_correlation)
        assert r1.independent_channels == r2.independent_channels

    def test_verdict_confirmed(self):
        r = exp_symmetry_partition(rng=np.random.RandomState(42))
        assert r.verdict is True


# ═══════════════════════════════════════════════════════════════════════
# H-C3 — 2D Placement: Quasi-Random vs Regular Grid
# ═══════════════════════════════════════════════════════════════════════

class TestPlacementComparison:
    """Quasi-random placement should beat regular grid conditioning."""

    def test_runs_without_error(self):
        r = exp_placement_comparison(rng=np.random.RandomState(42))
        assert isinstance(r, PlacementComparisonResult)

    def test_n_sites_perfect_square(self):
        r = exp_placement_comparison(K=16)
        assert r.n_sites == 16  # 4×4
        r2 = exp_placement_comparison(K=25)
        assert r2.n_sites == 25  # 5×5

    def test_grid_condition_worse_than_qr(self):
        """Regular grid should have higher (worse) condition number."""
        r = exp_placement_comparison(rng=np.random.RandomState(42))
        assert r.cond_grid > r.cond_r2_2d
        assert r.cond_grid > r.cond_1d_ext

    def test_r2_condition_finite(self):
        r = exp_placement_comparison(rng=np.random.RandomState(42))
        assert np.isfinite(r.cond_r2_2d)
        assert r.cond_r2_2d > 0

    def test_grid_rank_deficient(self):
        """Regular grid should lose rank due to aliasing."""
        r = exp_placement_comparison(K=16, rng=np.random.RandomState(42))
        assert r.rank_grid < r.n_sites

    def test_qr_full_rank(self):
        """Quasi-random strategies should achieve full rank."""
        r = exp_placement_comparison(rng=np.random.RandomState(42))
        assert r.rank_1d_ext == r.n_sites
        assert r.rank_r2_2d == r.n_sites

    def test_improvement_positive(self):
        r = exp_placement_comparison(rng=np.random.RandomState(42))
        assert r.improvement_pct > 0

    def test_improvement_exceeds_15_pct(self):
        r = exp_placement_comparison(rng=np.random.RandomState(42))
        assert r.improvement_pct > 15.0

    def test_more_modes_keeps_advantage(self):
        r_small = exp_placement_comparison(n_max_cap=5)
        r_large = exp_placement_comparison(n_max_cap=15)
        assert r_large.n_modes >= r_small.n_modes
        # Both should still confirm
        assert r_large.verdict is True

    def test_verdict_confirmed(self):
        r = exp_placement_comparison(rng=np.random.RandomState(42))
        assert r.verdict is True


# ═══════════════════════════════════════════════════════════════════════
# H-C4 — 2D Degeneracy Splitting (Avoided Crossing)
# ═══════════════════════════════════════════════════════════════════════

class TestDegeneracySplitting:
    """2D structural degeneracy should vastly exceed 1D."""

    def test_runs_without_error(self):
        r = exp_degeneracy_splitting(rng=np.random.RandomState(42))
        assert isinstance(r, DegeneracySplittingResult)

    def test_degenerate_pairs_formula(self):
        """n_max=20 → n_max*(n_max-1)/2 = 190 degenerate pairs."""
        r = exp_degeneracy_splitting(n_max_cap=20)
        assert r.n_degenerate_pairs == 190

    def test_degenerate_pairs_small(self):
        r = exp_degeneracy_splitting(n_max_cap=5, Q=10.0)
        nmax = n_max_formula(3.3e-6, 1.0, 10.0)
        nmax = min(nmax, 5)
        expected = nmax * (nmax - 1) // 2
        assert r.n_degenerate_pairs == expected

    def test_splitting_magnitudes_non_negative(self):
        r = exp_degeneracy_splitting(rng=np.random.RandomState(42))
        assert np.all(r.splitting_magnitudes >= 0)

    def test_mean_splitting_positive(self):
        r = exp_degeneracy_splitting(rng=np.random.RandomState(42))
        assert r.mean_splitting_Hz > 0

    def test_1d_bonus_is_zero(self):
        """1D rods have uniform mode spacing — no near-degeneracy."""
        r = exp_degeneracy_splitting(rng=np.random.RandomState(42))
        assert r.n_bonus_modes_1d == 0
        assert r.bonus_1d_pct == pytest.approx(0.0)

    def test_2d_bonus_significant(self):
        """Most degenerate pairs should be resolvable."""
        r = exp_degeneracy_splitting(rng=np.random.RandomState(42))
        assert r.n_bonus_modes_2d > 100
        assert r.bonus_2d_pct > 10.0

    def test_2d_vastly_exceeds_1d(self):
        r = exp_degeneracy_splitting(rng=np.random.RandomState(42))
        assert r.n_bonus_modes_2d > 10 * max(r.n_bonus_modes_1d, 1)

    def test_degeneracy_fraction_high(self):
        """~95% of modes should be in degenerate pairs."""
        r = exp_degeneracy_splitting(n_max_cap=20)
        assert r.degeneracy_fraction > 0.9

    def test_stronger_perturbation_more_splits(self):
        r_weak = exp_degeneracy_splitting(perturbation_strength=0.001)
        r_strong = exp_degeneracy_splitting(perturbation_strength=0.05)
        assert r_strong.n_bonus_modes_2d >= r_weak.n_bonus_modes_2d

    def test_higher_Q_more_pairs_needed(self):
        """Higher Q → narrower linewidth → some pairs may not resolve."""
        r_low = exp_degeneracy_splitting(Q=1_000.0)
        r_high = exp_degeneracy_splitting(Q=100_000.0)
        # Low Q (wide linewidth) should resolve as many or more
        assert r_low.n_bonus_modes_2d >= r_high.n_bonus_modes_2d

    def test_reproducible(self):
        r1 = exp_degeneracy_splitting(rng=np.random.RandomState(42))
        r2 = exp_degeneracy_splitting(rng=np.random.RandomState(42))
        np.testing.assert_array_equal(r1.splitting_magnitudes,
                                       r2.splitting_magnitudes)
        assert r1.n_bonus_modes_2d == r2.n_bonus_modes_2d

    def test_verdict_confirmed(self):
        r = exp_degeneracy_splitting(rng=np.random.RandomState(42))
        assert r.verdict is True


# ═══════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════

class TestRunAllChladni:
    """Test the run_all_chladni orchestrator."""

    def test_returns_four_results(self):
        results = run_all_chladni(verbose=False)
        assert len(results) == 4

    def test_keys_present(self):
        results = run_all_chladni(verbose=False)
        assert "plate_mode_count" in results
        assert "symmetry_partition" in results
        assert "placement_comparison" in results
        assert "degeneracy_splitting" in results

    def test_result_types(self):
        results = run_all_chladni(verbose=False)
        assert isinstance(results["plate_mode_count"], ModeCountResult)
        assert isinstance(results["symmetry_partition"], SymmetryPartitionResult)
        assert isinstance(results["placement_comparison"], PlacementComparisonResult)
        assert isinstance(results["degeneracy_splitting"], DegeneracySplittingResult)

    def test_all_verdicts_true(self):
        results = run_all_chladni(verbose=False)
        for name, r in results.items():
            assert r.verdict is True, f"{name} failed"

    def test_verbose_mode_runs(self):
        """Verbose mode should not raise."""
        results = run_all_chladni(verbose=True)
        assert len(results) == 4
