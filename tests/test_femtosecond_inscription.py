"""
Tests for S21 — Femtosecond Volumetric Inscription
===================================================

Hypotheses: H-V1 through H-V5
"""

import numpy as np
import pytest

from simulations.femtosecond_inscription import (
    # Constants
    FUSED_SILICA,
    SPEED_RATIO,
    TYPE_I,
    MEMS_ROD,
    MACRO_ROD,
    N_MAX,
    # Helpers
    _longitudinal_freq,
    _torsional_freq,
    _mode_linewidth,
    _volumetric_rayleigh_shift,
    _rayleigh_scattering_cross_section,
    _q_from_scattering,
    _bessel_j0_squared,
    _bessel_j1_squared,
    _radial_sensitivity_matrix,
    _mutual_information_from_matrix,
    # Experiments
    exp_axial_sensitivity,
    exp_shift_magnitude,
    exp_q_survival,
    exp_radial_encoding,
    exp_volumetric_capacity,
    # Result types
    AxialSensitivityResult,
    ShiftMagnitudeResult,
    QSurvivalResult,
    RadialEncodingResult,
    VolumetricCapacityResult,
    # Runner
    run_all_femtosecond_inscription,
)


# ═══════════════════════════════════════════════════════════════════════
# Physical constant sanity checks
# ═══════════════════════════════════════════════════════════════════════

class TestConstants:
    """Verify material and laser parameters are in physical range."""

    def test_fused_silica_density(self):
        assert 2100 < FUSED_SILICA["density"] < 2300

    def test_fused_silica_q(self):
        assert FUSED_SILICA["Q"] >= 50_000

    def test_fused_silica_wave_speeds(self):
        assert FUSED_SILICA["c_L"] > FUSED_SILICA["c_T"]
        assert 5000 < FUSED_SILICA["c_L"] < 7000
        assert 3000 < FUSED_SILICA["c_T"] < 4500

    def test_speed_ratio_physical(self):
        assert 0.5 < SPEED_RATIO < 0.8

    def test_type_i_density_change(self):
        """Type I inscription: 0.1–1% density change."""
        assert 0.001 <= TYPE_I["delta_rho_frac"] <= 0.01

    def test_focal_volume_positive(self):
        assert TYPE_I["focal_volume"] > 0

    def test_focal_volume_order(self):
        """Focal volume should be ~10 µm³ = ~10e-18 m³."""
        assert 1e-19 < TYPE_I["focal_volume"] < 1e-16

    def test_mems_rod_dimensions(self):
        assert MEMS_ROD["length"] == 1.0e-3
        assert MEMS_ROD["radius"] > 0
        assert MEMS_ROD["mass"] > 0

    def test_n_max_reasonable(self):
        """n_max for fused silica should be very large (>10,000)."""
        assert N_MAX > 10_000


# ═══════════════════════════════════════════════════════════════════════
# Helper function tests
# ═══════════════════════════════════════════════════════════════════════

class TestFrequencies:
    """Eigenfrequency helpers."""

    def test_longitudinal_fundamental(self):
        f1 = _longitudinal_freq(1, MEMS_ROD["length"], FUSED_SILICA["c_L"])
        expected = FUSED_SILICA["c_L"] / (2 * MEMS_ROD["length"])
        np.testing.assert_allclose(f1, expected, rtol=1e-10)

    def test_longitudinal_proportional_to_n(self):
        L = MEMS_ROD["length"]
        c = FUSED_SILICA["c_L"]
        assert _longitudinal_freq(10, L, c) == 10 * _longitudinal_freq(1, L, c)

    def test_torsional_lower_than_longitudinal(self):
        L = MEMS_ROD["length"]
        for n in range(1, 20):
            assert _torsional_freq(n, L, FUSED_SILICA["c_T"]) < \
                   _longitudinal_freq(n, L, FUSED_SILICA["c_L"])

    def test_linewidth_positive(self):
        assert _mode_linewidth(17717.0, 100_000) > 0

    def test_linewidth_inversely_proportional_to_q(self):
        lw1 = _mode_linewidth(1000.0, 1000)
        lw2 = _mode_linewidth(1000.0, 10000)
        np.testing.assert_allclose(lw1 / lw2, 10.0, rtol=1e-10)


class TestVolumetricShift:
    """Rayleigh perturbation formula for volumetric density change."""

    def test_shift_negative_for_densification(self):
        """Positive Δρ (densification) should lower eigenfrequency."""
        shift = _volumetric_rayleigh_shift(
            n=1, x_axial=0.5e-3, delta_rho=11.0,
            focal_volume=TYPE_I["focal_volume"],
            rod_mass=MEMS_ROD["mass"], rod_length=MEMS_ROD["length"]
        )
        assert shift < 0

    def test_shift_zero_at_node(self):
        """Shift should be zero at a node (sin²(nπx/L) = 0)."""
        L = MEMS_ROD["length"]
        # Mode 2, position L/2 is an antinode, L/4 is also not a node
        # Mode 1, position 0 is a node
        shift = _volumetric_rayleigh_shift(
            n=2, x_axial=0.5 * L, delta_rho=11.0,
            focal_volume=TYPE_I["focal_volume"],
            rod_mass=MEMS_ROD["mass"], rod_length=L
        )
        np.testing.assert_allclose(shift, 0.0, atol=1e-20)

    def test_shift_max_at_antinode(self):
        """Shift should be maximum at an antinode (sin²=1)."""
        L = MEMS_ROD["length"]
        M = MEMS_ROD["mass"]
        delta_rho = 11.0
        fv = TYPE_I["focal_volume"]
        # Mode 1 antinode at L/2
        shift_anti = _volumetric_rayleigh_shift(1, L / 2, delta_rho, fv, M, L)
        shift_quarter = _volumetric_rayleigh_shift(1, L / 4, delta_rho, fv, M, L)
        assert abs(shift_anti) >= abs(shift_quarter)

    def test_shift_proportional_to_delta_rho(self):
        """Doubling density change should double the shift."""
        L = MEMS_ROD["length"]
        M = MEMS_ROD["mass"]
        fv = TYPE_I["focal_volume"]
        s1 = _volumetric_rayleigh_shift(1, L / 2, 5.0, fv, M, L)
        s2 = _volumetric_rayleigh_shift(1, L / 2, 10.0, fv, M, L)
        np.testing.assert_allclose(s2 / s1, 2.0, rtol=1e-10)

    def test_shift_proportional_to_focal_volume(self):
        """Doubling focal volume should double the shift."""
        L = MEMS_ROD["length"]
        M = MEMS_ROD["mass"]
        s1 = _volumetric_rayleigh_shift(1, L / 2, 11.0, 1e-18, M, L)
        s2 = _volumetric_rayleigh_shift(1, L / 2, 11.0, 2e-18, M, L)
        np.testing.assert_allclose(s2 / s1, 2.0, rtol=1e-10)

    def test_sin_squared_pattern(self):
        """Shifts across positions should follow sin²(nπx/L)."""
        L = MEMS_ROD["length"]
        M = MEMS_ROD["mass"]
        fv = TYPE_I["focal_volume"]
        n = 3
        positions = np.linspace(0.01 * L, 0.99 * L, 100)
        shifts = np.array([
            abs(_volumetric_rayleigh_shift(n, x, 11.0, fv, M, L))
            for x in positions
        ])
        theory = np.sin(n * np.pi * positions / L) ** 2
        # Normalize and compare
        shifts_n = shifts / shifts.max()
        theory_n = theory / theory.max()
        np.testing.assert_allclose(shifts_n, theory_n, atol=1e-10)


class TestScattering:
    """Rayleigh acoustic scattering model."""

    def test_cross_section_positive(self):
        sigma = _rayleigh_scattering_cross_section(1e-6, 2e-3, 0.005)
        assert sigma > 0

    def test_cross_section_scales_as_d6(self):
        """Rayleigh scattering σ ∝ d⁶."""
        s1 = _rayleigh_scattering_cross_section(1e-6, 2e-3, 0.005)
        s2 = _rayleigh_scattering_cross_section(2e-6, 2e-3, 0.005)
        np.testing.assert_allclose(s2 / s1, 64.0, rtol=1e-6)

    def test_cross_section_scales_as_lambda_minus4(self):
        """Rayleigh scattering σ ∝ λ⁻⁴."""
        s1 = _rayleigh_scattering_cross_section(1e-6, 2e-3, 0.005)
        s2 = _rayleigh_scattering_cross_section(1e-6, 4e-3, 0.005)
        np.testing.assert_allclose(s1 / s2, 16.0, rtol=1e-6)

    def test_cross_section_scales_as_drho_squared(self):
        """Rayleigh scattering σ ∝ (Δρ/ρ)²."""
        s1 = _rayleigh_scattering_cross_section(1e-6, 2e-3, 0.005)
        s2 = _rayleigh_scattering_cross_section(1e-6, 2e-3, 0.010)
        np.testing.assert_allclose(s2 / s1, 4.0, rtol=1e-6)

    def test_q_unchanged_with_zero_inclusions(self):
        q = _q_from_scattering(100_000, 0, 1e-20, 1e-3, 1e-9)
        np.testing.assert_allclose(q, 100_000.0, rtol=1e-10)

    def test_q_decreases_with_inclusions(self):
        q0 = 100_000
        q1 = _q_from_scattering(q0, 1000, 1e-20, 1e-3, 1e-9)
        assert q1 <= q0

    def test_q_never_negative(self):
        q = _q_from_scattering(100_000, 10**12, 1e-20, 1e-3, 1e-9)
        assert q > 0


class TestBesselFunctions:
    """Bessel-function radial sensitivity."""

    def test_j0_squared_max_at_center(self):
        """J₀ has maximum at r=0."""
        center = _bessel_j0_squared(0.0)
        edge = _bessel_j0_squared(0.9)
        assert center > edge

    def test_j1_squared_zero_at_center(self):
        """J₁(0) = 0."""
        np.testing.assert_allclose(_bessel_j1_squared(0.0), 0.0, atol=1e-10)

    def test_j0_j1_complementary(self):
        """J₀ and J₁ have different spatial profiles (not correlated)."""
        r_vals = np.linspace(0.1, 0.9, 20)
        j0_vals = [_bessel_j0_squared(r) for r in r_vals]
        j1_vals = [_bessel_j1_squared(r) for r in r_vals]
        corr = abs(np.corrcoef(j0_vals, j1_vals)[0, 1])
        assert corr < 0.9  # not perfectly correlated


class TestRadialMatrix:
    """Radial sensitivity matrix construction."""

    def test_matrix_shape(self):
        m = _radial_sensitivity_matrix(10, 2)
        assert m.shape == (10, 2)

    def test_matrix_non_negative(self):
        m = _radial_sensitivity_matrix(10, 2)
        assert np.all(m >= 0)

    def test_matrix_columns_different(self):
        m = _radial_sensitivity_matrix(10, 2)
        assert not np.allclose(m[:, 0], m[:, 1])

    def test_mutual_info_positive(self):
        m = _radial_sensitivity_matrix(10, 2)
        mi = _mutual_information_from_matrix(m)
        assert mi > 0


# ═══════════════════════════════════════════════════════════════════════
# Experiment verdict tests
# ═══════════════════════════════════════════════════════════════════════

class TestHV1AxialSensitivity:
    """H-V1: Volumetric perturbations follow sin²(nπx/L)."""

    @pytest.fixture
    def result(self):
        return exp_axial_sensitivity()

    def test_returns_correct_type(self, result):
        assert isinstance(result, AxialSensitivityResult)

    def test_high_r_squared(self, result):
        """Volumetric formula IS the same Rayleigh formula → R² = 1."""
        assert result.mean_r_squared >= 0.999

    def test_all_modes_high_r_squared(self, result):
        assert result.min_r_squared >= 0.999

    def test_matches_surface(self, result):
        assert result.volumetric_surface_diff < 1e-6

    def test_verdict_confirmed(self, result):
        assert result.verdict is True


class TestHV2ShiftMagnitude:
    """H-V2: Cumulative frequency shift from inscription sites."""

    @pytest.fixture
    def result(self):
        return exp_shift_magnitude()

    def test_returns_correct_type(self, result):
        assert isinstance(result, ShiftMagnitudeResult)

    def test_single_site_shift_tiny(self, result):
        """Single site shift should be ~10⁻⁸ (very small)."""
        assert result.single_site_frac_shift < 1e-6

    def test_delta_m_physical(self, result):
        """Added mass per site should be femtograms to attograms."""
        assert 1e-18 < result.single_site_delta_m < 1e-14

    def test_cumulative_sublinewidth(self, result):
        """1000 sites produces shift below linewidth for Q=100,000."""
        assert result.shift_over_linewidth < 1.0

    def test_sites_for_10x_reported(self, result):
        assert result.n_sites_for_10x_linewidth > 0

    def test_verdict_killed(self, result):
        """Kill: 1000 sites insufficient for 10× linewidth shift."""
        assert result.verdict is False


class TestHV3QSurvival:
    """H-V3: Q-factor survives inscription."""

    @pytest.fixture
    def result(self):
        return exp_q_survival()

    def test_returns_correct_type(self, result):
        assert isinstance(result, QSurvivalResult)

    def test_size_ratio_small(self, result):
        """d/λ should be ≪ 1 (deep Rayleigh regime)."""
        assert result.size_ratio < 0.01

    def test_scattering_negligible(self, result):
        """Loss per round trip should be negligible."""
        assert result.total_scattering_loss < 1e-10

    def test_q_essentially_unchanged(self, result):
        """Q should remain very close to pristine."""
        assert result.q_ratio > 0.999

    def test_max_sites_enormous(self, result):
        """Should tolerate astronomical number of inscriptions."""
        assert result.max_sites_at_50pct_q > 1e12

    def test_verdict_confirmed(self, result):
        assert result.verdict is True


class TestHV4RadialEncoding:
    """H-V4: Radial position as encoding dimension."""

    @pytest.fixture
    def result(self):
        return exp_radial_encoding()

    def test_returns_correct_type(self, result):
        assert isinstance(result, RadialEncodingResult)

    def test_mutual_info_above_threshold(self, result):
        assert result.mutual_info_radial >= 1.0

    def test_modes_counted(self, result):
        assert result.n_axial_modes > 0
        assert result.n_torsional_modes > 0

    def test_bessel_matrix_shape(self, result):
        assert result.bessel_coupling_matrix.shape[0] == result.n_radial_positions
        assert result.bessel_coupling_matrix.shape[1] == 2

    def test_independent_of_axial(self, result):
        assert result.independent_of_axial is True

    def test_verdict_confirmed(self, result):
        assert result.verdict is True


class TestHV5VolumetricCapacity:
    """H-V5: 3D volumetric capacity vs surface-only."""

    @pytest.fixture
    def result(self):
        return exp_volumetric_capacity()

    def test_returns_correct_type(self, result):
        assert isinstance(result, VolumetricCapacityResult)

    def test_volumetric_exceeds_surface(self, result):
        assert result.volumetric_capacity_bits > result.surface_only_capacity_bits

    def test_radial_contributes(self, result):
        assert result.radial_contribution > 0

    def test_ratio_above_unity(self, result):
        assert result.capacity_ratio > 1.0

    def test_verdict_killed(self, result):
        """Kill: ratio < 1.5 with only 2 mode families."""
        assert result.verdict is False


# ═══════════════════════════════════════════════════════════════════════
# Integration test
# ═══════════════════════════════════════════════════════════════════════

class TestRunner:
    """Full S21 execution."""

    def test_run_all_returns_dict(self):
        results = run_all_femtosecond_inscription(verbose=False)
        assert isinstance(results, dict)
        assert len(results) == 5

    def test_run_all_keys(self):
        results = run_all_femtosecond_inscription(verbose=False)
        expected_keys = {"H-V1", "H-V2", "H-V3", "H-V4", "H-V5"}
        assert set(results.keys()) == expected_keys

    def test_run_all_scoreboard(self):
        results = run_all_femtosecond_inscription(verbose=False)
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = sum(1 for r in results.values() if not r.verdict)
        assert confirmed == 3
        assert killed == 2

    def test_deterministic(self):
        """Same seed produces identical results."""
        r1 = run_all_femtosecond_inscription(verbose=False)
        r2 = run_all_femtosecond_inscription(verbose=False)
        for key in r1:
            assert r1[key].verdict == r2[key].verdict
