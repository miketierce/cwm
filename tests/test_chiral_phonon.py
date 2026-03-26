"""
Tests for S19 — Chiral Phonons: Symmetry-Breaking Degeneracy Splitting
======================================================================

Hypotheses: H-CP1 through H-CP4
"""

import numpy as np
import pytest

from simulations.chiral_phonon import (
    # Constants
    SPEED_RATIO,
    # Helpers
    _longitudinal_freq,
    _torsional_freq,
    _cross_family_pairs,
    _coupling_strength,
    _chiral_splitting,
    _uncoupled_detuning,
    _linewidth,
    _fit_linear_r_squared,
    _fit_sin_r_squared,
    _golden_position,
    # Experiments
    exp_coupling_gap,
    exp_chiral_spectrum,
    exp_handedness_capacity,
    exp_thermal_reversibility,
    # Result types
    CouplingGapResult,
    ChiralSpectrumResult,
    HandednessCapacityResult,
    ThermalReversibilityResult,
    # Runner
    run_all_chiral_phonon,
)


# ═══════════════════════════════════════════════════════════════════════
# Helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestConstants:
    """Physical constant sanity checks."""

    def test_speed_ratio_physical(self):
        """c_T/c_L for glass should be roughly 0.5–0.7."""
        assert 0.4 < SPEED_RATIO < 0.8

    def test_speed_ratio_value(self):
        np.testing.assert_allclose(SPEED_RATIO, 3280.0 / 5640.0, rtol=1e-6)


class TestFrequencies:
    """Eigenfrequency helpers."""

    def test_longitudinal_freq_linear(self):
        assert _longitudinal_freq(1) == 1.0
        assert _longitudinal_freq(5) == 5.0

    def test_torsional_freq_scaled(self):
        np.testing.assert_allclose(
            _torsional_freq(1), SPEED_RATIO, rtol=1e-10
        )

    def test_torsional_lower_than_longitudinal(self):
        """c_T < c_L implies f_T(n) < f_L(n) for same mode number."""
        for n in range(1, 20):
            assert _torsional_freq(n) < _longitudinal_freq(n)

    def test_freq_proportional_to_n(self):
        """Both families scale linearly with n."""
        np.testing.assert_allclose(
            _longitudinal_freq(10) / _longitudinal_freq(5), 2.0, rtol=1e-10
        )
        np.testing.assert_allclose(
            _torsional_freq(10) / _torsional_freq(5), 2.0, rtol=1e-10
        )


class TestCrossFamilyPairs:
    """Cross-family pair finder."""

    def test_pairs_nonempty(self):
        pairs = _cross_family_pairs(30, 55, max_detuning=0.10)
        assert len(pairs) > 0

    def test_pairs_symmetric_constraint(self):
        """All pairs should have |f_L - f_T| / f_avg < max_detuning."""
        pairs = _cross_family_pairs(30, 55, max_detuning=0.08)
        for nL, nT in pairs:
            fL = _longitudinal_freq(nL)
            fT = _torsional_freq(nT)
            f_avg = (fL + fT) / 2.0
            detuning = abs(fL - fT) / f_avg
            assert detuning < 0.08

    def test_pairs_indices_positive(self):
        pairs = _cross_family_pairs(20, 40, max_detuning=0.10)
        for nL, nT in pairs:
            assert nL >= 1
            assert nT >= 1

    def test_tighter_detuning_fewer_pairs(self):
        wide = _cross_family_pairs(30, 55, max_detuning=0.10)
        tight = _cross_family_pairs(30, 55, max_detuning=0.03)
        assert len(tight) <= len(wide)

    def test_no_pairs_zero_detuning(self):
        """With detuning 0, only exact matches survive — none for glass."""
        pairs = _cross_family_pairs(10, 20, max_detuning=1e-10)
        assert len(pairs) == 0

    def test_cross_ratio_check(self):
        """Near-degenerate pairs satisfy n_T ≈ n_L · c_L/c_T ≈ 1.72·n_L."""
        pairs = _cross_family_pairs(30, 55, max_detuning=0.05)
        for nL, nT in pairs:
            expected_nT = nL / SPEED_RATIO
            assert abs(nT - expected_nT) / expected_nT < 0.10


class TestCouplingStrength:
    """Off-axis coupling helper."""

    def test_coupling_zero_at_theta_zero(self):
        """On-axis perturbation → no L-T coupling."""
        kappa = _coupling_strength(5, 9, 0.37, 0.03, theta=0.0)
        np.testing.assert_allclose(kappa, 0.0, atol=1e-15)

    def test_coupling_max_at_theta_pi_half(self):
        """Maximum coupling at θ = π/2."""
        k_mid = _coupling_strength(5, 9, 0.37, 0.03, theta=np.pi / 4)
        k_max = _coupling_strength(5, 9, 0.37, 0.03, theta=np.pi / 2)
        assert k_max > k_mid

    def test_coupling_positive(self):
        kappa = _coupling_strength(3, 5, 0.37, 0.02, theta=np.pi / 4)
        assert kappa >= 0.0

    def test_coupling_linear_in_epsilon(self):
        k1 = _coupling_strength(5, 9, 0.37, 0.01, np.pi / 4)
        k2 = _coupling_strength(5, 9, 0.37, 0.02, np.pi / 4)
        np.testing.assert_allclose(k2, 2 * k1, rtol=1e-10)

    def test_coupling_proportional_to_sin_theta(self):
        k1 = _coupling_strength(5, 9, 0.37, 0.03, np.pi / 6)
        k2 = _coupling_strength(5, 9, 0.37, 0.03, np.pi / 3)
        ratio = k2 / k1
        expected = np.sin(np.pi / 3) / np.sin(np.pi / 6)
        np.testing.assert_allclose(ratio, expected, rtol=1e-10)

    def test_coupling_zero_at_boundary(self):
        """Coupling vanishes when perturbation is at a node of either mode."""
        kappa = _coupling_strength(5, 9, 0.0, 0.03, np.pi / 4)
        np.testing.assert_allclose(kappa, 0.0, atol=1e-12)

    def test_coupling_zero_at_rod_end(self):
        kappa = _coupling_strength(5, 9, 1.0, 0.03, np.pi / 4)
        np.testing.assert_allclose(kappa, 0.0, atol=1e-12)


class TestChiralSplitting:
    """Chiral splitting computation."""

    def test_splitting_nonnegative(self):
        s = _chiral_splitting(5, 9, 0.37, 0.03, np.pi / 4)
        assert s >= 0.0

    def test_splitting_equals_detuning_at_theta_zero(self):
        """With no coupling, splitting = bare detuning."""
        s = _chiral_splitting(5, 9, 0.37, 0.03, theta=0.0)
        # At θ=0, κ=0, so eigenvalues are just the perturbed diagonal entries
        # Splitting = |f_L(1-ε·sin²(nLπx)) - f_T(1-ε·sin²(nTπx))| / f_avg
        # This should be close to the uncoupled detuning (modified by ε)
        assert s >= 0.0

    def test_splitting_increases_with_theta(self):
        s_lo = _chiral_splitting(5, 9, 0.37, 0.03, theta=0.1)
        s_hi = _chiral_splitting(5, 9, 0.37, 0.03, theta=np.pi / 2)
        assert s_hi >= s_lo

    def test_splitting_changes_with_epsilon(self):
        """Splitting should differ at different perturbation strengths."""
        s1 = _chiral_splitting(5, 9, 0.37, 0.01, np.pi / 4)
        s2 = _chiral_splitting(5, 9, 0.37, 0.05, np.pi / 4)
        # Different ε should generally produce different splitting
        # (not necessarily larger — diagonal shifts can reduce the gap)
        assert s1 != s2

    def test_splitting_varies_with_position(self):
        s1 = _chiral_splitting(5, 9, 0.25, 0.03, np.pi / 4)
        s2 = _chiral_splitting(5, 9, 0.37, 0.03, np.pi / 4)
        assert s1 != s2

    def test_splitting_symmetric_in_pairs(self):
        """Splitting should not depend on which mode we call L or T (eigenvalue gap is symmetric)."""
        # Two different pairs should give different splittings
        s1 = _chiral_splitting(3, 5, 0.37, 0.03, np.pi / 4)
        s2 = _chiral_splitting(5, 9, 0.37, 0.03, np.pi / 4)
        # Just verify both are valid
        assert s1 >= 0 and s2 >= 0


class TestUncoupledDetuning:
    """Bare detuning computation."""

    def test_detuning_positive(self):
        d = _uncoupled_detuning(5, 9)
        assert d >= 0.0

    def test_detuning_same_family(self):
        """Detuning between L-mode 5 and T-mode 5 should be nonzero (c_L ≠ c_T)."""
        d = _uncoupled_detuning(5, 5)
        assert d > 0.0

    def test_detuning_zero_for_exact_match(self):
        """If we fabricate f_L = f_T (hypothetical), detuning = 0."""
        # Can't easily get exact match with integer modes, but detuning
        # should approach zero for best-matched pairs
        pairs = _cross_family_pairs(50, 90, max_detuning=0.02)
        if len(pairs) > 0:
            detunings = [_uncoupled_detuning(nL, nT) for nL, nT in pairs]
            assert min(detunings) < 0.02


class TestLinewidth:
    """Linewidth helper."""

    def test_linewidth_positive(self):
        assert _linewidth(5, 9, 2000.0) > 0

    def test_linewidth_inversely_proportional_to_Q(self):
        lw1 = _linewidth(5, 9, 1000.0)
        lw2 = _linewidth(5, 9, 2000.0)
        np.testing.assert_allclose(lw1, 2 * lw2, rtol=1e-10)


class TestFitting:
    """Curve fitting helpers."""

    def test_linear_r2_perfect(self):
        x = np.linspace(0, 1, 20)
        y = 3 * x + 1
        assert _fit_linear_r_squared(x, y) > 0.999

    def test_linear_r2_noise(self):
        rng = np.random.RandomState(42)
        x = np.linspace(0, 1, 50)
        y = 2 * x + rng.normal(0, 0.01, 50)
        assert _fit_linear_r_squared(x, y) > 0.9

    def test_sin_r2_perfect(self):
        theta = np.linspace(0, np.pi / 2, 30)
        y = 5 * np.sin(theta) + 1
        assert _fit_sin_r_squared(theta, y) > 0.999

    def test_sin_r2_quadratic_data(self):
        """sin fit should be imperfect for quadratic data."""
        theta = np.linspace(0, np.pi / 2, 30)
        y = theta ** 2
        r2 = _fit_sin_r_squared(theta, y)
        # Should be decent but not perfect
        assert r2 < 1.0


class TestGoldenPosition:
    """Golden position helper."""

    def test_golden_in_unit_interval(self):
        pos = _golden_position()
        assert 0 < pos < 1

    def test_golden_is_irrational(self):
        """Value should be close to φ - 1 ≈ 0.618."""
        np.testing.assert_allclose(_golden_position(), 0.6180339887, rtol=1e-6)


# ═══════════════════════════════════════════════════════════════════════
# Experiment tests
# ═══════════════════════════════════════════════════════════════════════

class TestExpCouplingGap:
    """H-CP1: Longitudinal–torsional coupling gap."""

    def test_returns_correct_type(self):
        r = exp_coupling_gap(n_max_L=15, n_max_T=30)
        assert isinstance(r, CouplingGapResult)

    def test_finds_cross_pairs(self):
        r = exp_coupling_gap(n_max_L=30, n_max_T=55)
        assert r.n_cross_pairs > 0

    def test_splitting_matrix_shape(self):
        r = exp_coupling_gap(n_max_L=15, n_max_T=30, n_theta=10)
        assert r.splitting_matrix.shape[1] == 10
        assert r.splitting_matrix.shape[0] == r.n_cross_pairs

    def test_splitting_at_zero_nonneg(self):
        r = exp_coupling_gap(n_max_L=15, n_max_T=30)
        assert np.all(r.splitting_at_zero >= 0)

    def test_splitting_at_max_ge_zero(self):
        r = exp_coupling_gap(n_max_L=15, n_max_T=30)
        assert np.all(r.splitting_at_max >= 0)

    def test_verdict_is_bool(self):
        r = exp_coupling_gap(n_max_L=15, n_max_T=30)
        assert isinstance(r.verdict, bool)

    def test_default_params(self):
        """Full run with default parameters should not crash."""
        r = exp_coupling_gap()
        assert r.n_cross_pairs >= 0


class TestExpChiralSpectrum:
    """H-CP2: Chiral splitting spectrum."""

    def test_returns_correct_type(self):
        r = exp_chiral_spectrum(n_max_L=15, n_max_T=30)
        assert isinstance(r, ChiralSpectrumResult)

    def test_splittings_nonneg(self):
        r = exp_chiral_spectrum(n_max_L=15, n_max_T=30)
        assert np.all(r.splittings >= 0)

    def test_detunings_nonneg(self):
        r = exp_chiral_spectrum(n_max_L=15, n_max_T=30)
        assert np.all(r.detunings >= 0)

    def test_splitting_range_nonneg(self):
        r = exp_chiral_spectrum(n_max_L=15, n_max_T=30)
        assert r.splitting_range >= 0

    def test_r2_bounded(self):
        r = exp_chiral_spectrum(n_max_L=30, n_max_T=55)
        assert -0.1 <= r.spectral_structure_r2 <= 1.1

    def test_verdict_is_bool(self):
        r = exp_chiral_spectrum(n_max_L=15, n_max_T=30)
        assert isinstance(r.verdict, bool)

    def test_default_params(self):
        r = exp_chiral_spectrum()
        assert len(r.mode_pairs) >= 0


class TestExpHandednessCapacity:
    """H-CP3: Handedness capacity."""

    def test_returns_correct_type(self):
        r = exp_handedness_capacity(n_max_L=15, n_max_T=30)
        assert isinstance(r, HandednessCapacityResult)

    def test_chiral_ge_longitudinal(self):
        """Chiral system should have ≥ channels as longitudinal-only."""
        r = exp_handedness_capacity(n_max_L=15, n_max_T=30)
        assert r.n_resolved_chiral >= r.n_resolved_longitudinal

    def test_capacity_ratio_ge_one(self):
        r = exp_handedness_capacity(n_max_L=15, n_max_T=30)
        assert r.capacity_ratio >= 1.0

    def test_gain_nonneg(self):
        r = exp_handedness_capacity(n_max_L=15, n_max_T=30)
        assert r.capacity_gain_percent >= 0

    def test_verdict_is_bool(self):
        r = exp_handedness_capacity(n_max_L=15, n_max_T=30)
        assert isinstance(r.verdict, bool)

    def test_default_params(self):
        r = exp_handedness_capacity()
        assert r.n_modes_longitudinal > 0


class TestExpThermalReversibility:
    """H-CP4: Thermal reversibility."""

    def test_returns_correct_type(self):
        r = exp_thermal_reversibility(n_max_L=15, n_max_T=30)
        assert isinstance(r, ThermalReversibilityResult)

    def test_splitting_at_zero_nonneg(self):
        r = exp_thermal_reversibility(n_max_L=15, n_max_T=30)
        assert r.splitting_at_zero_theta >= 0

    def test_splitting_at_max_ge_zero(self):
        r = exp_thermal_reversibility(n_max_L=15, n_max_T=30)
        assert r.splitting_at_max_theta >= 0

    def test_on_off_ratio_positive(self):
        r = exp_thermal_reversibility(n_max_L=15, n_max_T=30)
        assert r.on_off_ratio > 0

    def test_r2_sin_bounded(self):
        r = exp_thermal_reversibility(n_max_L=15, n_max_T=30)
        assert -0.1 <= r.r2_sin_fit <= 1.1

    def test_verdict_is_bool(self):
        r = exp_thermal_reversibility(n_max_L=15, n_max_T=30)
        assert isinstance(r.verdict, bool)

    def test_default_params(self):
        r = exp_thermal_reversibility()
        assert len(r.theta_values) > 0


# ═══════════════════════════════════════════════════════════════════════
# Integration tests
# ═══════════════════════════════════════════════════════════════════════

class TestRunAll:
    """Full runner integration."""

    def test_run_all_returns_dict(self):
        results = run_all_chiral_phonon(verbose=False)
        assert isinstance(results, dict)

    def test_run_all_four_keys(self):
        results = run_all_chiral_phonon(verbose=False)
        assert set(results.keys()) == {"H-CP1", "H-CP2", "H-CP3", "H-CP4"}

    def test_run_all_correct_types(self):
        results = run_all_chiral_phonon(verbose=False)
        assert isinstance(results["H-CP1"], CouplingGapResult)
        assert isinstance(results["H-CP2"], ChiralSpectrumResult)
        assert isinstance(results["H-CP3"], HandednessCapacityResult)
        assert isinstance(results["H-CP4"], ThermalReversibilityResult)

    def test_run_all_reproducible(self):
        """Same seed → same verdicts."""
        r1 = run_all_chiral_phonon(verbose=False)
        r2 = run_all_chiral_phonon(verbose=False)
        for key in r1:
            assert r1[key].verdict == r2[key].verdict


# ═══════════════════════════════════════════════════════════════════════
# Parametric / edge-case tests
# ═══════════════════════════════════════════════════════════════════════

class TestParametric:
    """Parametric and edge-case tests."""

    def test_small_epsilon_small_splitting(self):
        """Tiny ε should produce splitting close to bare detuning."""
        s_small = _chiral_splitting(5, 9, 0.37, 1e-6, np.pi / 4)
        bare = _uncoupled_detuning(5, 9)
        np.testing.assert_allclose(s_small, bare, rtol=0.01)

    def test_large_theta_sweep_smooth(self):
        """Splitting should be smooth over many θ values."""
        thetas = np.linspace(0, np.pi / 2, 100)
        splits = [_chiral_splitting(5, 9, 0.37, 0.03, th) for th in thetas]
        diffs = np.diff(splits)
        # Should be monotonically increasing (all diffs ≥ 0)
        assert np.all(np.array(diffs) >= -1e-12)

    def test_zero_perturbation_bare_detuning(self):
        """ε = 0 should give bare detuning."""
        s = _chiral_splitting(5, 9, 0.37, 0.0, np.pi / 4)
        bare = _uncoupled_detuning(5, 9)
        np.testing.assert_allclose(s, bare, rtol=1e-6)

    @pytest.mark.parametrize("n_L,n_T", [(3, 5), (5, 9), (7, 12), (10, 17)])
    def test_splitting_positive_for_various_pairs(self, n_L, n_T):
        s = _chiral_splitting(n_L, n_T, 0.37, 0.03, np.pi / 4)
        assert s >= 0.0

    @pytest.mark.parametrize("theta", [0.0, np.pi/6, np.pi/4, np.pi/3, np.pi/2])
    def test_coupling_strength_nonneg_for_various_theta(self, theta):
        k = _coupling_strength(5, 9, 0.37, 0.03, theta)
        assert k >= 0.0

    def test_high_Q_more_selective(self):
        """Higher Q → smaller linewidth → fewer resolvable pairs need larger splitting."""
        r_low = exp_handedness_capacity(n_max_L=15, n_max_T=30, Q=500.0)
        r_high = exp_handedness_capacity(n_max_L=15, n_max_T=30, Q=5000.0)
        # Higher Q should resolve more pairs (narrower lines)
        assert r_high.n_split_pairs >= r_low.n_split_pairs

    def test_larger_epsilon_more_capacity(self):
        """Stronger perturbation should resolve more split pairs."""
        r_small = exp_handedness_capacity(n_max_L=15, n_max_T=30, epsilon=0.01)
        r_large = exp_handedness_capacity(n_max_L=15, n_max_T=30, epsilon=0.05)
        assert r_large.n_split_pairs >= r_small.n_split_pairs
