"""
Tests for S20 — Passive Stone Resonance: CWM Without Electricity
================================================================

Hypotheses: H-PA1 through H-PA5
"""

import numpy as np
import pytest

from simulations.passive_stone import (
    # Material database
    MATERIALS,
    VESSEL_DIMS,
    # Helpers
    _cylinder_axial_freqs,
    _cylinder_radial_freqs,
    _cylinder_circumferential_freqs,
    _audible_modes,
    _remove_near_duplicates,
    _perturbation_shift,
    _chladni_pattern_vector,
    _pattern_mutual_information,
    _cwm_capacity_formula,
    # Experiments
    exp_q_factor_comparison,
    exp_mode_density,
    exp_perturbation_sensitivity,
    exp_chladni_readout,
    exp_cross_material_capacity,
    # Result types
    QFactorComparisonResult,
    ModeDensityResult,
    PerturbationSensitivityResult,
    ChladniReadoutResult,
    CrossMaterialCapacityResult,
    # Runner
    run_all_passive_stone,
)


# ═══════════════════════════════════════════════════════════════════════
# Material database tests
# ═══════════════════════════════════════════════════════════════════════

class TestMaterialDatabase:
    """Sanity checks on material property values."""

    def test_all_materials_have_required_keys(self):
        required = {"c_L", "c_T", "density", "Q", "poisson"}
        for name, mat in MATERIALS.items():
            assert required.issubset(mat.keys()), f"{name} missing keys"

    def test_wave_speeds_positive(self):
        for name, mat in MATERIALS.items():
            assert mat["c_L"] > 0, f"{name} c_L <= 0"
            assert mat["c_T"] > 0, f"{name} c_T <= 0"

    def test_longitudinal_faster_than_shear(self):
        """c_L > c_T for all isotropic solids."""
        for name, mat in MATERIALS.items():
            assert mat["c_L"] > mat["c_T"], f"{name}: c_L not > c_T"

    def test_q_factors_positive(self):
        for name, mat in MATERIALS.items():
            assert mat["Q"] > 0, f"{name} Q <= 0"

    def test_density_physical_range(self):
        for name, mat in MATERIALS.items():
            assert 1000 < mat["density"] < 5000, f"{name} density out of range"

    def test_poisson_physical_range(self):
        """Poisson's ratio for solids: 0 < ν < 0.5."""
        for name, mat in MATERIALS.items():
            assert 0 < mat["poisson"] < 0.5, f"{name} Poisson out of range"

    def test_glass_baseline_present(self):
        assert "borosilicate_glass" in MATERIALS
        assert "fused_silica" in MATERIALS

    def test_stone_materials_present(self):
        stones = {"granite", "diorite", "quartzite", "alabaster", "basalt", "limestone"}
        for s in stones:
            assert s in MATERIALS, f"{s} missing"

    def test_fused_silica_highest_q(self):
        """Fused silica should have highest Q in the database."""
        max_q_name = max(MATERIALS, key=lambda k: MATERIALS[k]["Q"])
        assert max_q_name == "fused_silica"

    def test_glass_q_higher_than_stones(self):
        glass_q = MATERIALS["borosilicate_glass"]["Q"]
        for name, mat in MATERIALS.items():
            if name in ("borosilicate_glass", "fused_silica"):
                continue
            assert mat["Q"] < glass_q, f"{name} Q >= glass Q"

    def test_granite_wave_speed_range(self):
        """Published granite c_L: 4500–6500 m/s."""
        assert 4500 <= MATERIALS["granite"]["c_L"] <= 6500

    def test_granite_shear_speed_range(self):
        """Published granite c_T: 2500–3500 m/s."""
        assert 2500 <= MATERIALS["granite"]["c_T"] <= 3500


class TestVesselDimensions:
    """Archaeological vessel dimension checks."""

    def test_all_vessels_have_required_keys(self):
        required = {"height", "radius", "wall"}
        for name, dims in VESSEL_DIMS.items():
            assert required.issubset(dims.keys()), f"{name} missing keys"

    def test_dimensions_positive(self):
        for name, dims in VESSEL_DIMS.items():
            assert dims["height"] > 0
            assert dims["radius"] > 0
            assert dims["wall"] > 0

    def test_wall_thinner_than_radius(self):
        for name, dims in VESSEL_DIMS.items():
            assert dims["wall"] < dims["radius"], f"{name}: wall >= radius"

    def test_serapeum_box_dimensions(self):
        """Serapeum boxes are ~1.1m tall, ~0.45m radius."""
        box = VESSEL_DIMS["serapeum_box"]
        assert 1.0 <= box["height"] <= 1.3
        assert 0.3 <= box["radius"] <= 0.6


# ═══════════════════════════════════════════════════════════════════════
# Helper function tests
# ═══════════════════════════════════════════════════════════════════════

class TestAxialFreqs:
    """Cylinder axial eigenfrequency tests."""

    def test_first_mode(self):
        """f_1 = c_L / (2H)."""
        f = _cylinder_axial_freqs(5500.0, 0.15, n_max=1)
        np.testing.assert_allclose(f[0], 5500.0 / 0.30, rtol=1e-10)

    def test_linear_spacing(self):
        """Modes are harmonically spaced: f_n = n · f_1."""
        freqs = _cylinder_axial_freqs(5500.0, 0.15, n_max=10)
        for n in range(1, 11):
            np.testing.assert_allclose(freqs[n - 1], n * freqs[0], rtol=1e-10)

    def test_mode_count(self):
        freqs = _cylinder_axial_freqs(5500.0, 0.15, n_max=50)
        assert len(freqs) == 50

    def test_higher_speed_higher_freq(self):
        """Higher c_L → higher frequencies (same geometry)."""
        f1 = _cylinder_axial_freqs(5500.0, 0.15, n_max=1)[0]
        f2 = _cylinder_axial_freqs(5968.0, 0.15, n_max=1)[0]
        assert f2 > f1

    def test_taller_vessel_lower_freq(self):
        """Taller vessel → lower fundamental (same material)."""
        f1 = _cylinder_axial_freqs(5500.0, 0.10, n_max=1)[0]
        f2 = _cylinder_axial_freqs(5500.0, 0.25, n_max=1)[0]
        assert f2 < f1


class TestRadialFreqs:
    """Cylinder radial mode tests."""

    def test_returns_sorted(self):
        freqs = _cylinder_radial_freqs(3100.0, 0.07, 0.01)
        np.testing.assert_array_equal(freqs, np.sort(freqs))

    def test_positive_frequencies(self):
        freqs = _cylinder_radial_freqs(3100.0, 0.07, 0.01)
        assert np.all(freqs > 0)

    def test_zero_radius_empty(self):
        freqs = _cylinder_radial_freqs(3100.0, 0.01, 0.02)
        assert len(freqs) == 0


class TestCircumferentialFreqs:
    """Circumferential bending mode tests."""

    def test_starts_at_n2(self):
        """n=0 and n=1 are rigid-body modes, so first mode is n=2."""
        freqs = _cylinder_circumferential_freqs(3100.0, 0.07, 0.01, n_max=5)
        assert len(freqs) == 4  # n=2,3,4,5

    def test_increasing_with_n(self):
        freqs = _cylinder_circumferential_freqs(3100.0, 0.07, 0.01, n_max=10)
        diffs = np.diff(freqs)
        assert np.all(diffs > 0)

    def test_positive(self):
        freqs = _cylinder_circumferential_freqs(3100.0, 0.07, 0.01)
        assert np.all(freqs > 0)


class TestAudibleModes:
    """Audible band filtering."""

    def test_filters_below_20(self):
        freqs = np.array([5.0, 15.0, 100.0, 1000.0, 25000.0])
        aud = _audible_modes(freqs)
        assert 5.0 not in aud
        assert 15.0 not in aud
        assert 100.0 in aud

    def test_filters_above_20k(self):
        freqs = np.array([100.0, 1000.0, 19999.0, 20001.0])
        aud = _audible_modes(freqs)
        assert 20001.0 not in aud
        assert 19999.0 in aud

    def test_empty_input(self):
        aud = _audible_modes(np.array([]))
        assert len(aud) == 0

    def test_custom_range(self):
        freqs = np.array([50.0, 500.0, 5000.0])
        aud = _audible_modes(freqs, f_min=100.0, f_max=1000.0)
        assert len(aud) == 1
        assert aud[0] == 500.0


class TestRemoveNearDuplicates:
    """Duplicate frequency removal."""

    def test_removes_close_freqs(self):
        freqs = np.array([100.0, 102.0, 200.0, 203.0, 300.0])
        result = _remove_near_duplicates(freqs, min_spacing_hz=5.0)
        assert len(result) == 3

    def test_keeps_spaced_freqs(self):
        freqs = np.array([100.0, 200.0, 300.0])
        result = _remove_near_duplicates(freqs, min_spacing_hz=5.0)
        assert len(result) == 3

    def test_empty(self):
        result = _remove_near_duplicates(np.array([]))
        assert len(result) == 0

    def test_single(self):
        result = _remove_near_duplicates(np.array([100.0]))
        assert len(result) == 1


class TestPerturbationShift:
    """Universal perturbation formula tests."""

    def test_zero_at_endpoints(self):
        """sin²(nπ·0) = 0 and sin²(nπ·1) = 0 → no shift."""
        for n in range(1, 10):
            assert abs(_perturbation_shift(n, 0.0, 0.01, 1000.0)) < 1e-10
            assert abs(_perturbation_shift(n, 1.0, 0.01, 1000.0)) < 1e-10

    def test_maximum_at_midpoint_mode1(self):
        """Mode 1: max sensitivity at x = 0.5."""
        shift = _perturbation_shift(1, 0.5, 0.01, 1000.0)
        np.testing.assert_allclose(shift, -0.01 * 1000.0, rtol=1e-10)

    def test_negative_shift(self):
        """Mass addition always lowers frequency."""
        for n in range(1, 5):
            shift = _perturbation_shift(n, 0.3, 0.01, 1000.0)
            assert shift <= 0

    def test_proportional_to_epsilon(self):
        s1 = _perturbation_shift(3, 0.4, 0.01, 1000.0)
        s2 = _perturbation_shift(3, 0.4, 0.02, 1000.0)
        np.testing.assert_allclose(s2, 2 * s1, rtol=1e-10)

    def test_proportional_to_f_base(self):
        s1 = _perturbation_shift(3, 0.4, 0.01, 1000.0)
        s2 = _perturbation_shift(3, 0.4, 0.01, 2000.0)
        np.testing.assert_allclose(s2, 2 * s1, rtol=1e-10)

    def test_material_independent(self):
        """Same mode, same position → same RELATIVE shift regardless of f_base."""
        for f_base in [500.0, 1000.0, 5000.0, 18000.0]:
            shift = _perturbation_shift(3, 0.4, 0.01, f_base)
            relative = shift / f_base
            np.testing.assert_allclose(
                relative, -0.01 * np.sin(3 * np.pi * 0.4) ** 2, rtol=1e-10
            )


class TestChladniPattern:
    """Chladni pattern generation tests."""

    def test_output_binary(self):
        pat = _chladni_pattern_vector(3, 64)
        assert set(np.unique(pat)).issubset({0.0, 1.0})

    def test_mode1_has_nodes_at_edges(self):
        """Mode 1: nodes at x=0 and x=1 (close to edges)."""
        pat = _chladni_pattern_vector(1, 100)
        assert pat[0] == 1.0  # near node at x=0
        assert pat[-1] == 1.0  # near node at x≈1

    def test_higher_modes_more_nodes(self):
        """Higher mode number → more nodal lines → more particles."""
        n_particles_3 = np.sum(_chladni_pattern_vector(3, 128))
        n_particles_10 = np.sum(_chladni_pattern_vector(10, 128))
        assert n_particles_10 > n_particles_3

    def test_different_modes_different_patterns(self):
        p1 = _chladni_pattern_vector(2, 64)
        p2 = _chladni_pattern_vector(5, 64)
        assert not np.array_equal(p1, p2)


class TestPatternMutualInfo:
    """Mutual information computation tests."""

    def test_identical_patterns_zero_mi(self):
        """All-identical patterns have no discriminability."""
        patterns = np.ones((5, 32))
        mi = _pattern_mutual_information(patterns)
        assert np.all(mi == 0.0)

    def test_distinct_patterns_positive_mi(self):
        patterns = np.zeros((5, 32))
        for i in range(5):
            patterns[i, i * 6:(i + 1) * 6] = 1.0
        mi = _pattern_mutual_information(patterns)
        assert np.all(mi > 0)

    def test_output_shape(self):
        patterns = np.random.RandomState(42).randint(0, 2, (8, 32)).astype(float)
        mi = _pattern_mutual_information(patterns)
        assert mi.shape == (8,)


class TestCapacityFormula:
    """CWM capacity formula tests."""

    def test_zero_modes_zero_capacity(self):
        assert _cwm_capacity_formula(0, 2000.0) == 0.0

    def test_low_q_zero_capacity(self):
        assert _cwm_capacity_formula(10, 50.0) == 0.0

    def test_increases_with_modes(self):
        c1 = _cwm_capacity_formula(10, 2000.0)
        c2 = _cwm_capacity_formula(20, 2000.0)
        np.testing.assert_allclose(c2, 2 * c1, rtol=1e-10)

    def test_increases_with_q(self):
        c1 = _cwm_capacity_formula(10, 500.0)
        c2 = _cwm_capacity_formula(10, 2000.0)
        assert c2 > c1

    def test_known_value(self):
        """10 modes at Q=2000: 10 × log₂(1 + 2000/100) = 10 × log₂(21) ≈ 43.9."""
        cap = _cwm_capacity_formula(10, 2000.0)
        np.testing.assert_allclose(cap, 10 * np.log2(21.0), rtol=1e-10)


# ═══════════════════════════════════════════════════════════════════════
# H-PA1: Q-factor comparison
# ═══════════════════════════════════════════════════════════════════════

class TestQFactorComparison:
    """H-PA1 experiment tests."""

    @pytest.fixture
    def result(self):
        return exp_q_factor_comparison()

    def test_returns_correct_type(self, result):
        assert isinstance(result, QFactorComparisonResult)

    def test_has_verdict(self, result):
        assert isinstance(result.verdict, bool)

    def test_glass_q_matches_database(self, result):
        assert result.glass_q == MATERIALS["borosilicate_glass"]["Q"]

    def test_all_stones_present(self, result):
        expected = {"granite", "diorite", "quartzite", "alabaster", "basalt", "limestone"}
        assert expected.issubset(set(result.material_names))

    def test_ratios_less_than_one(self, result):
        """All stones should have Q < glass Q."""
        assert np.all(result.q_ratios_to_glass < 1.0)

    def test_ratios_positive(self, result):
        assert np.all(result.q_ratios_to_glass > 0)

    def test_best_stone_is_granite(self, result):
        assert result.best_stone == "granite"

    def test_granite_q_500(self, result):
        np.testing.assert_allclose(result.best_stone_q, 500.0)

    def test_worst_stone_q_positive(self, result):
        assert result.worst_stone_q > 0

    def test_all_above_100(self, result):
        """All stone Q > 100 (none fundamentally too lossy)."""
        assert result.all_above_100 is True

    def test_granite_within_order_of_magnitude(self, result):
        """Granite Q (500) > glass Q / 10 (200)."""
        assert result.any_within_order is True

    def test_verdict_confirmed(self, result):
        assert result.verdict is True

    def test_reproducibility(self):
        r1 = exp_q_factor_comparison(seed=42)
        r2 = exp_q_factor_comparison(seed=42)
        np.testing.assert_array_equal(r1.q_values, r2.q_values)


# ═══════════════════════════════════════════════════════════════════════
# H-PA2: Mode density
# ═══════════════════════════════════════════════════════════════════════

class TestModeDensity:
    """H-PA2 experiment tests."""

    @pytest.fixture
    def result_medium(self):
        return exp_mode_density(material="granite", vessel="saqqara_medium")

    @pytest.fixture
    def result_large(self):
        return exp_mode_density(material="granite", vessel="saqqara_large")

    @pytest.fixture
    def result_serapeum(self):
        return exp_mode_density(material="granite", vessel="serapeum_box")

    def test_returns_correct_type(self, result_medium):
        assert isinstance(result_medium, ModeDensityResult)

    def test_has_verdict(self, result_medium):
        assert isinstance(result_medium.verdict, bool)

    def test_medium_vessel_killed(self, result_medium):
        """Small vessel has too few modes — this kill is informative."""
        assert result_medium.verdict is False
        assert result_medium.n_total < 10

    def test_medium_vessel_nonzero_modes(self, result_medium):
        """Even small vessels have SOME modes."""
        assert result_medium.n_total > 0

    def test_large_vessel_more_modes(self, result_medium, result_large):
        """Larger vessel → more modes."""
        assert result_large.n_total >= result_medium.n_total

    def test_serapeum_many_modes(self, result_serapeum):
        """The Serapeum boxes (1.1m) should have many modes."""
        assert result_serapeum.n_total > 10

    def test_serapeum_would_confirm(self, result_serapeum):
        """Serapeum-scale resonators confirm the hypothesis."""
        assert result_serapeum.verdict is True

    def test_freq_range_in_audible(self, result_medium):
        if result_medium.n_total > 0:
            assert result_medium.freq_lowest >= 20.0
            assert result_medium.freq_highest <= 20000.0

    def test_mode_freqs_sorted(self, result_medium):
        np.testing.assert_array_equal(
            result_medium.mode_freqs, np.sort(result_medium.mode_freqs)
        )

    def test_all_materials(self):
        """All materials produce non-negative mode counts."""
        for mat_name in MATERIALS:
            r = exp_mode_density(material=mat_name, vessel="saqqara_medium")
            assert r.n_total >= 0

    def test_all_vessels(self):
        """All vessel sizes run without error."""
        for vessel in VESSEL_DIMS:
            r = exp_mode_density(material="granite", vessel=vessel)
            assert isinstance(r.n_total, int)

    def test_reproducibility(self):
        r1 = exp_mode_density(seed=42)
        r2 = exp_mode_density(seed=42)
        assert r1.n_total == r2.n_total


# ═══════════════════════════════════════════════════════════════════════
# H-PA3: Perturbation sensitivity
# ═══════════════════════════════════════════════════════════════════════

class TestPerturbationSensitivity:
    """H-PA3 experiment tests."""

    @pytest.fixture
    def result(self):
        return exp_perturbation_sensitivity()

    def test_returns_correct_type(self, result):
        assert isinstance(result, PerturbationSensitivityResult)

    def test_has_verdict(self, result):
        assert isinstance(result.verdict, bool)

    def test_verdict_confirmed(self, result):
        """sin²(nπx) law holds for stone."""
        assert result.verdict is True

    def test_r_squared_above_threshold(self, result):
        assert result.mean_r_squared > 0.9

    def test_min_r_squared_above_0_99(self, result):
        """Even the worst mode should fit well."""
        assert result.min_r_squared > 0.99

    def test_glass_r_squared_higher(self, result):
        """Glass (less granular) should have slightly higher R²."""
        assert result.glass_mean_r_squared >= result.mean_r_squared

    def test_difference_small(self, result):
        """Stone–glass R² difference should be tiny."""
        assert result.stone_glass_difference < 0.01

    def test_all_materials_high_r2(self):
        """sin² law should hold for all materials."""
        for mat_name in MATERIALS:
            r = exp_perturbation_sensitivity(material=mat_name)
            assert r.mean_r_squared > 0.9, f"{mat_name} R² too low"

    def test_reproducibility(self):
        r1 = exp_perturbation_sensitivity(seed=42)
        r2 = exp_perturbation_sensitivity(seed=42)
        np.testing.assert_allclose(r1.mean_r_squared, r2.mean_r_squared)


# ═══════════════════════════════════════════════════════════════════════
# H-PA4: Chladni readout
# ═══════════════════════════════════════════════════════════════════════

class TestChladniReadout:
    """H-PA4 experiment tests."""

    @pytest.fixture
    def result(self):
        return exp_chladni_readout()

    def test_returns_correct_type(self, result):
        assert isinstance(result, ChladniReadoutResult)

    def test_has_verdict(self, result):
        assert isinstance(result.verdict, bool)

    def test_verdict_confirmed(self, result):
        """Chladni patterns give > 1 bit/mode."""
        assert result.verdict is True

    def test_mean_mi_above_1bit(self, result):
        assert result.mean_mi > 1.0

    def test_all_modes_above_1bit(self, result):
        assert result.n_modes_above_1bit == result.n_modes

    def test_pattern_distinctness_positive(self, result):
        assert result.pattern_distinctness > 0

    def test_mi_array_shape(self, result):
        assert result.pattern_mutual_info.shape == (result.n_modes,)

    def test_reproducibility(self):
        r1 = exp_chladni_readout(seed=42)
        r2 = exp_chladni_readout(seed=42)
        np.testing.assert_allclose(r1.mean_mi, r2.mean_mi)


# ═══════════════════════════════════════════════════════════════════════
# H-PA5: Cross-material capacity
# ═══════════════════════════════════════════════════════════════════════

class TestCrossMaterialCapacity:
    """H-PA5 experiment tests."""

    @pytest.fixture
    def result(self):
        return exp_cross_material_capacity()

    def test_returns_correct_type(self, result):
        assert isinstance(result, CrossMaterialCapacityResult)

    def test_has_verdict(self, result):
        assert isinstance(result.verdict, bool)

    def test_verdict_confirmed(self, result):
        """Mean prediction error < 25%."""
        assert result.verdict is True

    def test_mean_error_below_25pct(self, result):
        assert result.mean_error < 0.25

    def test_glass_capacity_positive(self, result):
        assert result.glass_capacity > 0

    def test_best_stone_positive(self, result):
        assert result.best_stone_capacity > 0

    def test_stone_less_than_glass(self, result):
        """Stone capacity should be less than glass (lower Q)."""
        assert result.capacity_ratio < 1.0

    def test_stone_nontrivial(self, result):
        """Stone capacity should be meaningful (> 20% of glass)."""
        assert result.capacity_ratio > 0.2

    def test_all_materials_present(self, result):
        assert len(result.material_names) == len(MATERIALS)

    def test_arrays_same_length(self, result):
        n = len(result.material_names)
        assert len(result.predicted_capacities) == n
        assert len(result.measured_capacities) == n
        assert len(result.prediction_errors) == n

    def test_errors_non_negative(self, result):
        assert np.all(result.prediction_errors >= 0)

    def test_reproducibility(self):
        r1 = exp_cross_material_capacity(seed=42)
        r2 = exp_cross_material_capacity(seed=42)
        np.testing.assert_allclose(r1.mean_error, r2.mean_error)


# ═══════════════════════════════════════════════════════════════════════
# Runner tests
# ═══════════════════════════════════════════════════════════════════════

class TestRunner:
    """Integration tests for the full S20 runner."""

    def test_runner_returns_dict(self):
        results = run_all_passive_stone(verbose=False)
        assert isinstance(results, dict)

    def test_runner_all_keys_present(self):
        results = run_all_passive_stone(verbose=False)
        expected = {"H-PA1", "H-PA2", "H-PA3", "H-PA4", "H-PA5"}
        assert expected == set(results.keys())

    def test_runner_verdict_count(self):
        """4 confirmed, 1 killed."""
        results = run_all_passive_stone(verbose=False)
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = sum(1 for r in results.values() if not r.verdict)
        assert confirmed == 4
        assert killed == 1

    def test_runner_pa2_killed(self):
        """H-PA2 (mode density for medium vessel) should be killed."""
        results = run_all_passive_stone(verbose=False)
        assert results["H-PA2"].verdict is False

    def test_runner_reproducibility(self):
        r1 = run_all_passive_stone(verbose=False)
        r2 = run_all_passive_stone(verbose=False)
        for key in r1:
            assert r1[key].verdict == r2[key].verdict

    def test_runner_verbose_no_error(self, capsys):
        """Verbose mode should print without errors."""
        run_all_passive_stone(verbose=True)
        captured = capsys.readouterr()
        assert "S20 SUMMARY" in captured.out
        assert "CONFIRMED" in captured.out
        assert "KILLED" in captured.out
