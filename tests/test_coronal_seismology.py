"""Tests for simulations/coronal_seismology.py (Sidebar 17).

Target: comprehensive coverage of helpers, experiments, and integration
for the coronal seismology astrophysical validation module.
"""

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Imports — helpers, dataclasses, experiments, runner
# ---------------------------------------------------------------------------

from simulations.coronal_seismology import (
    # Constants
    _MU_0, _B_DEFAULT, _L_DEFAULT, _RHO_I_DEFAULT, _RHO_E_DEFAULT,
    _T_CORONA, _CS_DEFAULT, _PHI_CONJ,
    _P1_OVER_2P2_DATA,
    # Helpers
    _kink_frequency,
    _sausage_frequency,
    _longitudinal_frequency,
    _period_from_omega,
    _sensitivity_matrix,
    _condition_number,
    _weyl_positions,
    _golden_positions,
    _equispaced_positions,
    _random_positions,
    _spearman_correlation,
    _spearman_p_value,
    _stratified_density,
    _stratified_eigenfrequencies,
    _period_ratio_from_freqs,
    _finesse_from_reflectivity,
    _q_from_finesse,
    _q_from_damping,
    _quantise,
    _inversion_rms,
    _condition_number_for_loop,
    # Dataclasses
    RationalDegeneracyResult,
    ModeFamilyIndependenceResult,
    CapacityCeilingResult,
    PeriodRatioCorrelationResult,
    FootpointFinesseResult,
    PerturbationScalingResult,
    OptimalProbeSpacingResult,
    CoronalSeismologySummary,
    # Experiments
    exp_rational_degeneracy,
    exp_mode_family_independence,
    exp_capacity_ceiling,
    exp_period_ratio_correlation,
    exp_footpoint_finesse,
    exp_perturbation_scaling,
    exp_optimal_probe_spacing,
    # Runner
    run_all_coronal,
)


# ====================================================================
# Constants
# ====================================================================

class TestConstants:
    """Physical constants are physically reasonable."""

    def test_mu_0_value(self):
        assert pytest.approx(_MU_0, rel=1e-4) == 4e-7 * np.pi

    def test_default_magnetic_field_positive(self):
        assert _B_DEFAULT > 0

    def test_default_loop_length_positive(self):
        assert _L_DEFAULT > 0

    def test_density_ratio(self):
        assert _RHO_I_DEFAULT > _RHO_E_DEFAULT

    def test_corona_temperature(self):
        assert _T_CORONA > 1e5  # corona is > 100,000 K

    def test_p1_2p2_data_nonempty(self):
        assert len(_P1_OVER_2P2_DATA) >= 10

    def test_p1_2p2_ratios_below_unity(self):
        for ratio, _, _ in _P1_OVER_2P2_DATA:
            assert 0.5 < ratio < 1.05


# ====================================================================
# MHD frequency helpers
# ====================================================================

class TestKinkFrequency:
    """Kink mode frequency: ω_K = k_z √(2B²/μ₀(ρ_i + ρ_e))."""

    def test_positive(self):
        assert _kink_frequency(1) > 0

    def test_harmonic_scaling(self):
        w1 = _kink_frequency(1)
        w3 = _kink_frequency(3)
        assert pytest.approx(w3 / w1, rel=1e-10) == 3.0

    def test_stronger_field_higher_freq(self):
        w_low = _kink_frequency(1, B=1e-3)
        w_high = _kink_frequency(1, B=10e-3)
        assert w_high > w_low

    def test_shorter_loop_higher_freq(self):
        w_long = _kink_frequency(1, L=2e8)
        w_short = _kink_frequency(1, L=1e8)
        assert w_short > w_long

    def test_explicit_formula(self):
        B, L = 5e-3, 1e8
        rho_i, rho_e = 5e-12, 1e-12
        kz = np.pi / L
        v_k = np.sqrt(2.0 * B**2 / (_MU_0 * (rho_i + rho_e)))
        expected = kz * v_k
        assert pytest.approx(_kink_frequency(1, B, L, rho_i, rho_e)) == expected


class TestSausageFrequency:
    """Sausage mode frequency: ω_S = k_z √(B²/μ₀ρ_e)."""

    def test_positive(self):
        assert _sausage_frequency(1) > 0

    def test_harmonic_scaling(self):
        w1 = _sausage_frequency(1)
        w5 = _sausage_frequency(5)
        assert pytest.approx(w5 / w1, rel=1e-10) == 5.0

    def test_sausage_faster_than_kink(self):
        # v_ae > v_k when ρ_i > ρ_e (which is the default)
        wk = _kink_frequency(1)
        ws = _sausage_frequency(1)
        assert ws > wk


class TestLongitudinalFrequency:
    """Longitudinal mode: ω_L = nπc_s/L."""

    def test_positive(self):
        assert _longitudinal_frequency(1) > 0

    def test_formula(self):
        expected = 3 * np.pi * _CS_DEFAULT / _L_DEFAULT
        assert pytest.approx(_longitudinal_frequency(3)) == expected

    def test_slower_than_kink(self):
        # Sound speed << Alfvén speed typically
        wl = _longitudinal_frequency(1)
        wk = _kink_frequency(1)
        assert wl < wk


class TestPeriodFromOmega:
    """Period = 2π/ω."""

    def test_basic(self):
        assert pytest.approx(_period_from_omega(2 * np.pi)) == 1.0

    def test_zero_frequency(self):
        assert _period_from_omega(0) == np.inf


# ====================================================================
# Sensitivity matrix & condition number
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
        # sin²(nπ·0.5) = sin²(nπ/2) = 1 for odd n, 0 for even n
        S = _sensitivity_matrix(np.array([0.5]), 4)
        assert pytest.approx(S[0, 0]) == 1.0  # n=1
        assert pytest.approx(S[1, 0], abs=1e-10) == 0.0  # n=2

    def test_endpoint(self):
        # sin²(nπ·0) = 0 for all n
        S = _sensitivity_matrix(np.array([0.0]), 5)
        for n in range(5):
            assert pytest.approx(S[n, 0], abs=1e-10) == 0.0


class TestConditionNumber:
    """κ(S) = σ_max/σ_min."""

    def test_golden_well_conditioned(self):
        pos = _golden_positions(6)
        kappa = _condition_number(pos, 40)
        assert kappa < 100  # well-conditioned

    def test_rational_ill_conditioned(self):
        pos = _weyl_positions(0.5, 6)  # rational generator
        kappa = _condition_number(pos, 40)
        assert kappa > 1000  # ill-conditioned


# ====================================================================
# Position generators
# ====================================================================

class TestPositionGenerators:
    """Weyl, golden, equispaced, random positions."""

    def test_golden_in_unit_interval(self):
        pos = _golden_positions(10)
        assert np.all(pos >= 0.01) and np.all(pos <= 0.99)
        assert len(pos) == 10

    def test_golden_sorted(self):
        pos = _golden_positions(8)
        assert np.all(np.diff(pos) >= 0)

    def test_equispaced_symmetric(self):
        pos = _equispaced_positions(5)
        assert pytest.approx(pos[0] + pos[-1]) == 1.0

    def test_equispaced_count(self):
        assert len(_equispaced_positions(7)) == 7

    def test_random_deterministic(self):
        p1 = _random_positions(5, seed=42)
        p2 = _random_positions(5, seed=42)
        np.testing.assert_array_equal(p1, p2)

    def test_random_different_seeds(self):
        p1 = _random_positions(5, seed=1)
        p2 = _random_positions(5, seed=2)
        assert not np.allclose(p1, p2)

    def test_weyl_length(self):
        pos = _weyl_positions(np.sqrt(2) - 1, 12)
        assert len(pos) == 12


# ====================================================================
# Statistics
# ====================================================================

class TestSpearmanCorrelation:
    """Spearman rank correlation."""

    def test_perfect_positive(self):
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        assert pytest.approx(_spearman_correlation(x, x)) == 1.0

    def test_perfect_negative(self):
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        y = np.array([5, 4, 3, 2, 1], dtype=float)
        assert pytest.approx(_spearman_correlation(x, y)) == -1.0

    def test_p_value_zero_for_perfect(self):
        assert _spearman_p_value(1.0, 10) == 0.0

    def test_p_value_large_for_zero_rho(self):
        p = _spearman_p_value(0.0, 20)
        assert p > 0.9


# ====================================================================
# Stratification
# ====================================================================

class TestStratifiedDensity:
    """Density profiles for loop stratification."""

    def test_uniform_at_zero_epsilon(self):
        z = np.linspace(0, 1, 50)
        rho = _stratified_density(z, epsilon=0.0, profile="linear")
        np.testing.assert_allclose(rho, 1.0)

    def test_linear_at_midpoint(self):
        rho = _stratified_density(np.array([0.5]), 0.1, "linear")
        assert pytest.approx(rho[0]) == 1.0  # midpoint is neutral

    def test_sinusoidal_positive(self):
        z = np.linspace(0, 1, 100)
        rho = _stratified_density(z, 0.1, "sinusoidal")
        assert np.all(rho > 0)

    def test_exponential_positive(self):
        z = np.linspace(0, 1, 100)
        rho = _stratified_density(z, 0.3, "exponential")
        assert np.all(rho > 0)

    def test_gravity_positive(self):
        z = np.linspace(0, 1, 100)
        rho = _stratified_density(z, 0.5, "gravity")
        assert np.all(rho > 0)

    def test_gravity_footpoint_heavy(self):
        """Gravity profile has density max at footpoints, min at apex."""
        z = np.linspace(0, 1, 200)
        rho = _stratified_density(z, 1.0, "gravity")
        # Footpoints (z=0, z=1) should have higher density than apex (z=0.5)
        assert rho[0] > rho[100]
        assert rho[-1] > rho[100]


class TestStratifiedEigenfrequencies:
    """Rayleigh-Ritz eigenfrequencies for stratified loops."""

    def test_uniform_matches_analytic(self):
        v = 1e6
        L = 1e8
        freqs = _stratified_eigenfrequencies(3, L, v, epsilon=0.0)
        for n in range(1, 4):
            expected = n * np.pi * v / L
            assert pytest.approx(freqs[n - 1], rel=1e-3) == expected

    def test_stratification_shifts_frequencies(self):
        v, L = 1e6, 1e8
        f_uniform = _stratified_eigenfrequencies(2, L, v, 0.0)
        f_strat = _stratified_eigenfrequencies(2, L, v, 0.2, "sinusoidal")
        assert not np.allclose(f_uniform, f_strat)

    def test_all_positive(self):
        freqs = _stratified_eigenfrequencies(5, 1e8, 1e6, 0.1)
        assert np.all(freqs > 0)


class TestPeriodRatio:
    """P₁/(2P₂) from eigenfrequencies."""

    def test_uniform_loop_ratio_is_unity(self):
        v, L = 1e6, 1e8
        freqs = _stratified_eigenfrequencies(2, L, v, 0.0)
        ratio = _period_ratio_from_freqs(freqs)
        assert pytest.approx(ratio, rel=1e-3) == 1.0

    def test_stratified_ratio_deviates_from_unity(self):
        v, L = 1e6, 1e8
        freqs = _stratified_eigenfrequencies(2, L, v, 0.3, "sinusoidal")
        ratio = _period_ratio_from_freqs(freqs)
        assert abs(ratio - 1.0) > 0.01

    def test_gravity_ratio_below_unity(self):
        """Gravity profile produces P₁/2P₂ < 1.0 (matching observations)."""
        v, L = 1e6, 1e8
        freqs = _stratified_eigenfrequencies(2, L, v, 1.0, "gravity")
        ratio = _period_ratio_from_freqs(freqs)
        assert ratio < 1.0


# ====================================================================
# Fabry-Pérot helpers
# ====================================================================

class TestFinesseHelpers:
    """Finesse and Q-factor calculations."""

    def test_finesse_increases_with_R(self):
        F_low = _finesse_from_reflectivity(0.3)
        F_high = _finesse_from_reflectivity(0.9)
        assert F_high > F_low

    def test_finesse_perfect_mirror(self):
        assert _finesse_from_reflectivity(1.0) == np.inf

    def test_finesse_known_value(self):
        # R=0.9: F = π√0.9/(1-0.9) = π×0.9487/0.1 ≈ 29.80
        F = _finesse_from_reflectivity(0.9)
        assert pytest.approx(F, rel=0.01) == np.pi * np.sqrt(0.9) / 0.1

    def test_q_from_finesse(self):
        # Q = n·F
        F = 10.0
        assert pytest.approx(_q_from_finesse(F, 5)) == 50.0

    def test_q_from_damping(self):
        # Q = π·τ_d/P
        P, tau = 100.0, 500.0
        assert pytest.approx(_q_from_damping(P, tau)) == np.pi * 500 / 100


# ====================================================================
# Quantisation & inversion
# ====================================================================

class TestQuantise:
    """Uniform quantisation into n_levels bins."""

    def test_output_range(self):
        vals = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        q = _quantise(vals, 4)
        assert np.all(q >= 0) and np.all(q < 4)

    def test_constant_input(self):
        q = _quantise(np.ones(5), 4)
        np.testing.assert_array_equal(q, np.zeros(5, dtype=int))


class TestInversionRMS:
    """Least-squares inversion error."""

    def test_zero_noise_perfect_recovery(self):
        pos = _golden_positions(4)
        pattern = np.array([1.0, 0.0, 2.0, 1.0])
        rms = _inversion_rms(pos, 20, pattern, noise_sigma=0.0)
        assert rms < 0.01

    def test_noise_increases_error(self):
        pos = _golden_positions(4)
        pattern = np.array([1.0, 0.0, 2.0, 1.0])
        rms_lo = _inversion_rms(pos, 20, pattern, noise_sigma=0.01)
        rms_hi = _inversion_rms(pos, 20, pattern, noise_sigma=0.5)
        assert rms_hi > rms_lo


# ====================================================================
# Experiment H-CS1: Rational-position degeneracy
# ====================================================================

class TestExpRationalDegeneracy:
    """H-CS1 — κ peaks at rational fractions."""

    def test_returns_correct_type(self):
        r = exp_rational_degeneracy()
        assert isinstance(r, RationalDegeneracyResult)

    def test_kappa_ratio_large(self):
        r = exp_rational_degeneracy()
        assert r.kappa_ratio >= 10.0

    def test_rational_kappas_larger(self):
        r = exp_rational_degeneracy()
        assert r.rational_mean_kappa > r.irrational_mean_kappa

    def test_irrational_kappas_bounded(self):
        r = exp_rational_degeneracy()
        assert np.all(r.irrational_kappas < 1e6)

    def test_deterministic(self):
        r1 = exp_rational_degeneracy(seed=99)
        r2 = exp_rational_degeneracy(seed=99)
        assert r1.kappa_ratio == r2.kappa_ratio


# ====================================================================
# Experiment H-CS2: Mode-family independence
# ====================================================================

class TestExpModeFamilyIndependence:
    """H-CS2 — kink/sausage/longitudinal diagnostic independence."""

    def test_returns_correct_type(self):
        r = exp_mode_family_independence()
        assert isinstance(r, ModeFamilyIndependenceResult)

    def test_three_families(self):
        r = exp_mode_family_independence()
        assert r.n_families == 3

    def test_cross_corr_shape(self):
        r = exp_mode_family_independence()
        assert r.cross_correlations.shape == (3, 3)

    def test_diagonal_is_one(self):
        r = exp_mode_family_independence()
        for i in range(3):
            assert pytest.approx(r.cross_correlations[i, i], abs=0.05) == 1.0

    def test_channel_capacities_positive(self):
        r = exp_mode_family_independence()
        assert np.all(r.channel_capacities > 0)

    def test_polysemic_capacity_positive(self):
        r = exp_mode_family_independence()
        assert r.total_polysemic_capacity > 0

    def test_deterministic(self):
        r1 = exp_mode_family_independence(seed=7)
        r2 = exp_mode_family_independence(seed=7)
        assert r1.mean_cross_corr == r2.mean_cross_corr


# ====================================================================
# Experiment H-CS3: Logarithmic capacity ceiling
# ====================================================================

class TestExpCapacityCeiling:
    """H-CS3 — diagnostic info scales as C ≈ a·ln(N) + b."""

    def test_returns_correct_type(self):
        r = exp_capacity_ceiling()
        assert isinstance(r, CapacityCeilingResult)

    def test_log_fit_positive_coefficient(self):
        r = exp_capacity_ceiling()
        assert r.log_coefficient > 0

    def test_capacities_monotonically_increase(self):
        r = exp_capacity_ceiling()
        assert np.all(np.diff(r.capacities) >= 0)

    def test_n_values_powers_of_two(self):
        r = exp_capacity_ceiling()
        for n in r.n_values:
            assert n & (n - 1) == 0  # power of 2

    def test_r_squared_bounded(self):
        r = exp_capacity_ceiling()
        assert 0 <= r.log_r_squared <= 1.0
        assert 0 <= r.linear_r_squared <= 1.0

    def test_deterministic(self):
        r1 = exp_capacity_ceiling(seed=11)
        r2 = exp_capacity_ceiling(seed=11)
        assert r1.log_r_squared == r2.log_r_squared


# ====================================================================
# Experiment H-CS4: Period-ratio correlation
# ====================================================================

class TestExpPeriodRatioCorrelation:
    """H-CS4 — P₁/2P₂ anomalies vs conditioning."""

    def test_returns_correct_type(self):
        r = exp_period_ratio_correlation()
        assert isinstance(r, PeriodRatioCorrelationResult)

    def test_n_observations_matches_data(self):
        r = exp_period_ratio_correlation()
        assert r.n_observations == len(_P1_OVER_2P2_DATA)

    def test_spearman_bounded(self):
        r = exp_period_ratio_correlation()
        assert -1.0 <= r.spearman_rho <= 1.0

    def test_p_value_bounded(self):
        r = exp_period_ratio_correlation()
        assert 0 <= r.p_value <= 1.0

    def test_kappas_positive(self):
        r = exp_period_ratio_correlation()
        assert np.all(r.predicted_kappas > 0)

    def test_harmonic_counts_range(self):
        r = exp_period_ratio_correlation()
        assert np.all(r.harmonic_counts >= 2)
        assert np.all(r.harmonic_counts <= 5)

    def test_deterministic(self):
        r1 = exp_period_ratio_correlation(seed=42)
        r2 = exp_period_ratio_correlation(seed=42)
        assert r1.spearman_rho == r2.spearman_rho


# ====================================================================
# Experiment H-CS5: Footpoint Fabry-Pérot finesse
# ====================================================================

class TestExpFootpointFinesse:
    """H-CS5 — footpoint impedance maps to Fabry-Pérot finesse."""

    def test_returns_correct_type(self):
        r = exp_footpoint_finesse()
        assert isinstance(r, FootpointFinesseResult)

    def test_reflectivities_in_range(self):
        r = exp_footpoint_finesse()
        assert np.all(r.reflectivities > 0) and np.all(r.reflectivities < 1)

    def test_finesse_positive(self):
        r = exp_footpoint_finesse()
        assert np.all(r.finesse_values > 0)

    def test_q_values_positive(self):
        r = exp_footpoint_finesse()
        assert np.all(r.q_from_finesse > 0)
        assert np.all(r.q_from_damping > 0)

    def test_mean_ratio_finite(self):
        r = exp_footpoint_finesse()
        assert np.isfinite(r.mean_ratio)

    def test_deterministic(self):
        r1 = exp_footpoint_finesse(seed=5)
        r2 = exp_footpoint_finesse(seed=5)
        assert r1.mean_ratio == r2.mean_ratio


# ====================================================================
# Experiment H-CS6: Perturbation scaling
# ====================================================================

class TestExpPerturbationScaling:
    """H-CS6 — eigenfrequency shift scales linearly for small ε."""

    def test_returns_correct_type(self):
        r = exp_perturbation_scaling()
        assert isinstance(r, PerturbationScalingResult)

    def test_shifts_increase_with_epsilon(self):
        r = exp_perturbation_scaling()
        assert r.frequency_shifts[-1] > r.frequency_shifts[0]

    def test_r_squared_high(self):
        r = exp_perturbation_scaling()
        assert r.linear_r_squared > 0.99

    def test_max_epsilon(self):
        r = exp_perturbation_scaling()
        assert r.max_epsilon_tested == pytest.approx(0.1)

    def test_deterministic(self):
        r1 = exp_perturbation_scaling(seed=3)
        r2 = exp_perturbation_scaling(seed=3)
        assert r1.linear_r_squared == r2.linear_r_squared


# ====================================================================
# Experiment H-CS7: Optimal probe spacing
# ====================================================================

class TestExpOptimalProbeSpacing:
    """H-CS7 — golden-ratio spacing minimises inversion error."""

    def test_returns_correct_type(self):
        r = exp_optimal_probe_spacing()
        assert isinstance(r, OptimalProbeSpacingResult)

    def test_golden_rms_smallest(self):
        r = exp_optimal_probe_spacing()
        assert r.golden_rms < r.equispaced_rms
        assert r.golden_rms < r.random_rms

    def test_golden_kappa_smallest(self):
        r = exp_optimal_probe_spacing()
        assert r.golden_kappa < r.equispaced_kappa

    def test_all_rms_nonnegative(self):
        r = exp_optimal_probe_spacing()
        assert r.golden_rms >= 0
        assert r.equispaced_rms >= 0
        assert r.random_rms >= 0

    def test_deterministic(self):
        r1 = exp_optimal_probe_spacing(seed=10)
        r2 = exp_optimal_probe_spacing(seed=10)
        assert r1.golden_rms == r2.golden_rms


# ====================================================================
# Runner
# ====================================================================

class TestRunAllCoronal:
    """Integration test for run_all_coronal."""

    def test_returns_summary(self):
        s = run_all_coronal(verbose=False)
        assert isinstance(s, CoronalSeismologySummary)

    def test_confirmed_plus_killed_is_seven(self):
        s = run_all_coronal(verbose=False)
        assert s.confirmed + s.killed == 7

    def test_all_sub_results_present(self):
        s = run_all_coronal(verbose=False)
        assert isinstance(s.rational_degeneracy, RationalDegeneracyResult)
        assert isinstance(s.mode_family_independence, ModeFamilyIndependenceResult)
        assert isinstance(s.capacity_ceiling, CapacityCeilingResult)
        assert isinstance(s.period_ratio_correlation, PeriodRatioCorrelationResult)
        assert isinstance(s.footpoint_finesse, FootpointFinesseResult)
        assert isinstance(s.perturbation_scaling, PerturbationScalingResult)
        assert isinstance(s.optimal_probe_spacing, OptimalProbeSpacingResult)

    def test_verdicts_are_bool(self):
        s = run_all_coronal(verbose=False)
        for r in [s.rational_degeneracy, s.mode_family_independence,
                  s.capacity_ceiling, s.period_ratio_correlation,
                  s.footpoint_finesse, s.perturbation_scaling,
                  s.optimal_probe_spacing]:
            assert isinstance(r.verdict, (bool, np.bool_))


# ====================================================================
# Cross-physics consistency
# ====================================================================

class TestCrossPhysics:
    """Consistency checks between coronal and CWM physics."""

    def test_kink_faster_than_longitudinal(self):
        wk = _kink_frequency(1)
        wl = _longitudinal_frequency(1)
        assert wk > wl

    def test_sausage_faster_than_kink(self):
        wk = _kink_frequency(1)
        ws = _sausage_frequency(1)
        assert ws > wk

    def test_period_ratio_deviation_increases_with_stratification(self):
        v, L = 1e6, 1e8
        dev = []
        for eps in [0.01, 0.1, 0.3]:
            freqs = _stratified_eigenfrequencies(2, L, v, eps, "gravity")
            r = _period_ratio_from_freqs(freqs)
            dev.append(abs(1.0 - r))
        assert dev[1] > dev[0]
        assert dev[2] > dev[1]

    def test_golden_positions_lower_kappa_than_equispaced(self):
        kg = _condition_number(_golden_positions(6), 40)
        ke = _condition_number(_equispaced_positions(6), 40)
        assert kg < ke

    def test_sensitivity_matrix_at_nodes_is_zero(self):
        # A node of mode n is at x=0 and x=1
        S = _sensitivity_matrix(np.array([0.0, 1.0]), 5)
        assert np.allclose(S, 0, atol=1e-10)

    def test_condition_number_for_loop_finite(self):
        kappa = _condition_number_for_loop(0.1)
        assert np.isfinite(kappa) and kappa > 1
