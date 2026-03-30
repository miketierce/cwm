"""
Tests for S22 — Beads on a String
==================================

Validates the bead_string simulation module: material databases,
core physics functions, transfer-matrix eigenvalue solver, Q model,
and all five experimental hypotheses.
"""

import numpy as np
import pytest
from numpy.testing import assert_allclose

from simulations.bead_string import (
    # Constants / databases
    STRING_MATERIALS, BEAD_MATERIALS, CONTACT_TYPES,
    REF_STRING_LENGTH, REF_STRING_TENSION, REF_BEAD_DIAMETER,
    REF_STRING_MATERIAL, REF_BEAD_MATERIAL,
    KILL_Q_THRESHOLD, KILL_R2_THRESHOLD,
    KILL_DISTINGUISHABLE_MATERIALS, KILL_MI_THRESHOLD,
    KILL_SUPERPOSITION_ERROR,
    # Core physics
    bead_mass, string_linear_density, string_total_mass,
    wave_speed, unperturbed_frequencies, rayleigh_shift,
    # Transfer matrix
    _segment_matrix, _mass_matrix,
    loaded_string_characteristic, find_loaded_eigenfrequencies,
    # Q model
    effective_q, worst_case_q,
    # Experiments
    exp_q_loose_threading, exp_sin2_sensitivity,
    exp_multi_material_alphabet, exp_repositionability,
    exp_superposition, run_all_bead_string,
    # Result types
    QLooseThreadingResult, Sin2SensitivityResult,
    MultiMaterialResult, RepositionabilityResult,
    SuperpositionResult,
)


# ═══════════════════════════════════════════════════════════════════════
# Material database tests
# ═══════════════════════════════════════════════════════════════════════

class TestMaterialDatabases:
    """Check consistency and physical plausibility of material constants."""

    def test_string_materials_have_required_keys(self):
        for name, props in STRING_MATERIALS.items():
            assert "density" in props, f"{name} missing density"
            assert "youngs_modulus" in props, f"{name} missing youngs_modulus"
            assert "Q" in props, f"{name} missing Q"
            assert "diameter" in props, f"{name} missing diameter"

    def test_string_densities_positive(self):
        for name, props in STRING_MATERIALS.items():
            assert props["density"] > 0, f"{name} density non-positive"

    def test_string_q_factors_positive(self):
        for name, props in STRING_MATERIALS.items():
            assert props["Q"] > 10, f"{name} Q suspiciously low"

    def test_bead_materials_have_density(self):
        for name, props in BEAD_MATERIALS.items():
            assert "density" in props
            assert props["density"] > 0

    def test_bead_density_ordering(self):
        """Physical consistency: wood < bone < glass < stone < copper < gold."""
        d = {k: v["density"] for k, v in BEAD_MATERIALS.items()}
        assert d["wood"] < d["bone"] < d["glass"] < d["stone"] < d["copper"] < d["gold"]

    def test_contact_types_positive(self):
        for name, q in CONTACT_TYPES.items():
            assert q > 0
        # Loose < snug < knotted < bonded
        assert CONTACT_TYPES["loose"] < CONTACT_TYPES["snug"]
        assert CONTACT_TYPES["snug"] < CONTACT_TYPES["knotted"]
        assert CONTACT_TYPES["knotted"] < CONTACT_TYPES["bonded"]

    def test_six_string_materials(self):
        assert len(STRING_MATERIALS) == 6

    def test_seven_bead_materials(self):
        assert len(BEAD_MATERIALS) == 7


# ═══════════════════════════════════════════════════════════════════════
# Core physics function tests
# ═══════════════════════════════════════════════════════════════════════

class TestCorePhy:
    """Unit tests for basic physics functions."""

    def test_bead_mass_sphere(self):
        """Mass of a sphere: m = (π/6)d³ρ."""
        d = 0.003
        rho = 2500.0
        expected = (np.pi / 6) * d**3 * rho
        assert_allclose(bead_mass(d, "faience"), expected)

    def test_bead_mass_zero_diameter(self):
        assert bead_mass(0.0, "faience") == 0.0

    def test_bead_mass_increases_with_density(self):
        m_wood = bead_mass(0.003, "wood")
        m_gold = bead_mass(0.003, "gold")
        assert m_gold > m_wood

    def test_string_linear_density(self):
        """μ = ρ·π·r²."""
        props = STRING_MATERIALS["nylon"]
        r = props["diameter"] / 2
        expected = props["density"] * np.pi * r**2
        assert_allclose(string_linear_density("nylon"), expected)

    def test_string_total_mass(self):
        mu = string_linear_density("nylon")
        assert_allclose(string_total_mass("nylon", 0.5), mu * 0.5)

    def test_wave_speed_positive(self):
        c = wave_speed("nylon", 10.0)
        assert c > 0

    def test_wave_speed_formula(self):
        """c = √(T/μ)."""
        mu = string_linear_density("steel")
        T = 50.0
        expected = np.sqrt(T / mu)
        assert_allclose(wave_speed("steel", T), expected)

    def test_unperturbed_frequencies_harmonic(self):
        """f_n = n·f_1 (ideal string)."""
        freqs = unperturbed_frequencies("nylon", 10.0, 0.5, 5)
        ratios = freqs / freqs[0]
        assert_allclose(ratios, [1, 2, 3, 4, 5], rtol=1e-10)

    def test_unperturbed_frequency_count(self):
        freqs = unperturbed_frequencies("nylon", 10.0, 0.5, 20)
        assert len(freqs) == 20

    def test_rayleigh_shift_shape(self):
        pos = np.array([0.1, 0.2, 0.3])
        shifts = rayleigh_shift(0.01, pos, 0.5, 5)
        assert shifts.shape == (5, 3)

    def test_rayleigh_shift_negative(self):
        """Mass perturbation always lowers frequency."""
        pos = np.array([0.25])
        shifts = rayleigh_shift(0.01, pos, 0.5, 5)
        assert np.all(shifts <= 0)

    def test_rayleigh_shift_at_node(self):
        """No shift at node: sin²(nπx/L) = 0 when x = L/n."""
        # Mode 2 node at x = L/2
        pos = np.array([0.25])  # L/2 for L=0.5
        shifts = rayleigh_shift(0.01, pos, 0.5, 5)
        assert_allclose(shifts[1, 0], 0.0, atol=1e-15)

    def test_rayleigh_shift_at_antinode(self):
        """Maximum shift at antinode: sin²(nπx/L) = 1."""
        # Mode 1 antinode at x = L/2
        pos = np.array([0.25])  # L/2 for L=0.5
        shifts = rayleigh_shift(0.05, pos, 0.5, 3)
        assert_allclose(shifts[0, 0], -0.05, rtol=1e-10)

    def test_rayleigh_shift_zero_mass(self):
        pos = np.array([0.1, 0.3])
        shifts = rayleigh_shift(0.0, pos, 0.5, 5)
        assert_allclose(shifts, 0.0)


# ═══════════════════════════════════════════════════════════════════════
# Transfer-matrix solver tests
# ═══════════════════════════════════════════════════════════════════════

class TestTransferMatrix:
    """Tests for the transfer-matrix eigenvalue solver."""

    def test_segment_matrix_identity_at_zero_length(self):
        M = _segment_matrix(5.0, 0.0)
        assert_allclose(M, np.eye(2), atol=1e-14)

    def test_segment_matrix_determinant_one(self):
        """Segment matrix is symplectic (det = 1)."""
        M = _segment_matrix(3.7, 0.15)
        assert_allclose(np.linalg.det(M), 1.0, atol=1e-12)

    def test_mass_matrix_determinant_one(self):
        M = _mass_matrix(5.0, 100.0, 0.001, 10.0)
        assert_allclose(np.linalg.det(M), 1.0, atol=1e-12)

    def test_no_bead_matches_unperturbed(self):
        """Transfer matrix with no beads → unperturbed eigenfrequencies."""
        L, T = 0.5, 10.0
        mu = string_linear_density("nylon")
        f0 = unperturbed_frequencies("nylon", T, L, 5)
        f_tm = find_loaded_eigenfrequencies(
            T, mu, L, np.array([]), np.array([]), 5
        )
        assert_allclose(f_tm, f0, rtol=1e-4)

    def test_midpoint_mass_no_even_mode_shift(self):
        """A bead at L/2 should NOT shift even-numbered modes."""
        L, T = 0.5, 10.0
        mu = string_linear_density("nylon")
        M = mu * L
        m = M * 0.01  # small mass
        f0 = unperturbed_frequencies("nylon", T, L, 4)
        f_loaded = find_loaded_eigenfrequencies(
            T, mu, L, np.array([L / 2]), np.array([m]), 4
        )
        # Mode 2 (index 1) and mode 4 (index 3) should be unchanged
        assert_allclose(f_loaded[1], f0[1], rtol=1e-4)
        assert_allclose(f_loaded[3], f0[3], rtol=1e-4)

    def test_midpoint_mass_shifts_odd_modes(self):
        """A bead at L/2 SHOULD shift odd-numbered modes downward."""
        L, T = 0.5, 10.0
        mu = string_linear_density("nylon")
        M = mu * L
        m = M * 0.01
        f0 = unperturbed_frequencies("nylon", T, L, 3)
        f_loaded = find_loaded_eigenfrequencies(
            T, mu, L, np.array([L / 2]), np.array([m]), 3
        )
        assert f_loaded[0] < f0[0]  # mode 1 shifts down
        assert f_loaded[2] < f0[2]  # mode 3 shifts down

    def test_small_mass_matches_rayleigh(self):
        """Transfer matrix agrees with Rayleigh for small m/M."""
        L, T = 0.5, 10.0
        mu = string_linear_density("nylon")
        M = mu * L
        m = M * 0.001
        x0 = L / 3.0
        f0 = unperturbed_frequencies("nylon", T, L, 5)
        f_loaded = find_loaded_eigenfrequencies(
            T, mu, L, np.array([x0]), np.array([m]), 5
        )
        tm_shifts = (f_loaded - f0) / f0
        rayleigh_pred = rayleigh_shift(0.001, np.array([x0]), L, 5).flatten()
        # Should agree within ~1%
        mask = np.abs(rayleigh_pred) > 1e-10
        assert_allclose(tm_shifts[mask], rayleigh_pred[mask], rtol=0.02)

    def test_loaded_frequencies_decrease(self):
        """Adding mass always lowers eigenfrequencies."""
        L, T = 0.5, 10.0
        mu = string_linear_density("nylon")
        m = bead_mass(0.002, "faience")
        f0 = unperturbed_frequencies("nylon", T, L, 5)
        f_loaded = find_loaded_eigenfrequencies(
            T, mu, L, np.array([0.15]), np.array([m]), 5
        )
        assert np.all(f_loaded <= f0 + 1e-6)

    def test_heavier_bead_larger_shift(self):
        """Heavier bead → larger frequency shift."""
        L, T = 0.5, 10.0
        mu = string_linear_density("nylon")
        x0 = np.array([L / 4])
        m1 = bead_mass(0.002, "wood")
        m2 = bead_mass(0.002, "copper")
        f0 = unperturbed_frequencies("nylon", T, L, 3)
        f1 = find_loaded_eigenfrequencies(T, mu, L, x0, np.array([m1]), 3)
        f2 = find_loaded_eigenfrequencies(T, mu, L, x0, np.array([m2]), 3)
        # Copper (heavier) should shift mode 1 more than wood
        assert (f0[0] - f2[0]) > (f0[0] - f1[0])

    def test_two_beads_more_shift_than_one(self):
        """Two beads produce more total shift than one."""
        L, T = 0.5, 10.0
        mu = string_linear_density("nylon")
        m = bead_mass(0.002, "faience")
        f0 = unperturbed_frequencies("nylon", T, L, 3)
        f1 = find_loaded_eigenfrequencies(
            T, mu, L, np.array([L / 4]), np.array([m]), 3
        )
        f2 = find_loaded_eigenfrequencies(
            T, mu, L, np.array([L / 4, L * 0.4]), np.array([m, m]), 3
        )
        shift1 = np.abs(f0[0] - f1[0])
        shift2 = np.abs(f0[0] - f2[0])
        assert shift2 > shift1


# ═══════════════════════════════════════════════════════════════════════
# Q model tests
# ═══════════════════════════════════════════════════════════════════════

class TestQModel:
    """Tests for the Q-factor model."""

    def test_effective_q_at_node(self):
        """At a node, bead contributes no damping → Q = Q_mat."""
        # Mode 2 node at L/2
        q = effective_q("nylon", "loose", REF_STRING_LENGTH / 2,
                        REF_STRING_LENGTH, mode_number=2)
        assert_allclose(q, STRING_MATERIALS["nylon"]["Q"], rtol=1e-10)

    def test_effective_q_at_antinode(self):
        """At the antinode, Q = harmonic mean of Q_mat and Q_contact."""
        q_mat = STRING_MATERIALS["nylon"]["Q"]
        q_c = CONTACT_TYPES["loose"]
        expected = 1.0 / (1.0 / q_mat + 1.0 / q_c)
        q = effective_q("nylon", "loose", REF_STRING_LENGTH / 2,
                        REF_STRING_LENGTH, mode_number=1)
        assert_allclose(q, expected, rtol=1e-10)

    def test_bonded_q_approaches_material(self):
        """Bonded contact has very high Q_c, so Q_eff ≈ Q_mat."""
        q = effective_q("nylon", "bonded", REF_STRING_LENGTH / 2,
                        REF_STRING_LENGTH, mode_number=1)
        assert q > 0.95 * STRING_MATERIALS["nylon"]["Q"]

    def test_worst_case_is_mode1_midpoint(self):
        """worst_case_q uses mode 1 at midpoint."""
        q_wc = worst_case_q("nylon", "loose")
        q_manual = effective_q("nylon", "loose",
                               REF_STRING_LENGTH / 2,
                               REF_STRING_LENGTH, 1)
        assert_allclose(q_wc, q_manual)

    def test_steel_higher_q_than_nylon(self):
        q_s = worst_case_q("steel", "knotted")
        q_n = worst_case_q("nylon", "knotted")
        assert q_s > q_n

    def test_knotted_higher_q_than_loose(self):
        q_k = worst_case_q("nylon", "knotted")
        q_l = worst_case_q("nylon", "loose")
        assert q_k > q_l


# ═══════════════════════════════════════════════════════════════════════
# H-B1: Loose threading Q
# ═══════════════════════════════════════════════════════════════════════

class TestHB1:
    """H-B1: Loose-threaded bead Q < 50 for all materials."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_q_loose_threading()

    def test_verdict_confirmed(self, result):
        """Loose threading universally kills Q below 50."""
        assert result.verdict is True

    def test_all_below_threshold(self, result):
        assert result.all_below_threshold is True

    def test_no_material_passes(self, result):
        assert np.all(result.q_values < KILL_Q_THRESHOLD)

    def test_steel_is_best(self, result):
        """Steel has highest Q even with loose threading."""
        assert result.best_material in ("steel", "glass_fiber")

    def test_silk_or_gut_is_worst(self, result):
        assert result.worst_material in ("silk", "gut")

    def test_six_materials_tested(self, result):
        assert len(result.material_names) == 6


# ═══════════════════════════════════════════════════════════════════════
# H-B2: sin² sensitivity
# ═══════════════════════════════════════════════════════════════════════

class TestHB2:
    """H-B2: sin² sensitivity pattern at archaeological mass ratio."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_sin2_sensitivity()

    def test_verdict_killed(self, result):
        """sin² degrades at 8% mass ratio → KILLED."""
        assert result.verdict is False

    def test_mode1_high_r2(self, result):
        """Mode 1 should still have decent R² (>0.99)."""
        assert result.r_squared_per_mode[0] > 0.99

    def test_r2_degrades_with_mode(self, result):
        """R² should decrease for higher modes."""
        r2 = result.r_squared_per_mode
        # Mode 5 should be worse than mode 1
        assert r2[4] < r2[0]

    def test_min_r2_below_threshold(self, result):
        assert result.min_r_squared < KILL_R2_THRESHOLD

    def test_mass_ratio_correct(self, result):
        """Reference bead mass ratio matches expectations."""
        M = string_total_mass(REF_STRING_MATERIAL, REF_STRING_LENGTH)
        m = bead_mass(REF_BEAD_DIAMETER, REF_BEAD_MATERIAL)
        expected = m / M
        assert_allclose(result.mass_ratio, expected, rtol=1e-6)


class TestHB2Perturbative:
    """H-B2 supplemental: sin² IS exact in the perturbative limit."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_sin2_sensitivity(bead_diameter=0.001, n_modes=5)

    def test_small_bead_confirms(self, result):
        """1mm bead (m/M≈0.003) should have R² ≥ 0.999."""
        assert result.verdict is True

    def test_all_modes_above_threshold(self, result):
        assert np.all(result.r_squared_per_mode >= KILL_R2_THRESHOLD)

    def test_mass_ratio_small(self, result):
        assert result.mass_ratio < 0.01


# ═══════════════════════════════════════════════════════════════════════
# H-B3: Multi-material alphabet
# ═══════════════════════════════════════════════════════════════════════

class TestHB3:
    """H-B3: ≥ 3 bead materials distinguishable by ≥ 1 linewidth."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_multi_material_alphabet()

    def test_verdict_confirmed(self, result):
        assert result.verdict is True

    def test_at_least_three_distinguishable(self, result):
        assert result.n_distinguishable >= KILL_DISTINGUISHABLE_MATERIALS

    def test_wood_and_gold_most_different(self, result):
        """Extreme density difference → largest separation."""
        max_pair = max(result.pairwise_separations.items(),
                       key=lambda x: x[1])
        assert "wood" in max_pair[0] and "gold" in max_pair[0]

    def test_seven_materials_tested(self, result):
        assert len(result.material_names) == 7

    def test_shifts_are_negative(self, result):
        """All materials should produce negative (downward) shifts."""
        assert np.all(result.shifts_per_material <= 1e-10)

    def test_heavier_material_larger_shift(self, result):
        """Gold (heaviest) should shift more than wood (lightest)."""
        names = result.material_names
        wood_idx = names.index("wood")
        gold_idx = names.index("gold")
        wood_shift_mag = np.abs(result.shifts_per_material[wood_idx, 0])
        gold_shift_mag = np.abs(result.shifts_per_material[gold_idx, 0])
        assert gold_shift_mag > wood_shift_mag


# ═══════════════════════════════════════════════════════════════════════
# H-B4: Repositionability
# ═══════════════════════════════════════════════════════════════════════

class TestHB4:
    """H-B4: Bead-position mutual information ≥ 1 bit."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_repositionability()

    def test_verdict_confirmed(self, result):
        assert result.verdict is True

    def test_mi_above_threshold(self, result):
        assert result.mutual_information >= KILL_MI_THRESHOLD

    def test_fingerprints_shape(self, result):
        assert result.fingerprints.shape == (10, 10)

    def test_fingerprints_distinct(self, result):
        """No two positions should produce identical fingerprints."""
        fp = result.fingerprints
        for i in range(fp.shape[0]):
            for j in range(i + 1, fp.shape[0]):
                dist = np.sqrt(np.sum((fp[i] - fp[j])**2))
                assert dist > 1e-8, f"Positions {i} and {j} identical"


# ═══════════════════════════════════════════════════════════════════════
# H-B5: Multi-bead superposition
# ═══════════════════════════════════════════════════════════════════════

class TestHB5:
    """H-B5: Multi-bead superposition error < 10% at archaeological scale."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_superposition()

    def test_verdict_killed(self, result):
        """Archaeological beads break superposition → KILLED."""
        assert result.verdict is False

    def test_mean_error_above_threshold(self, result):
        assert result.mean_error > KILL_SUPERPOSITION_ERROR

    def test_three_beads(self, result):
        assert result.n_beads == 3

    def test_mass_ratio_substantial(self, result):
        """Total mass ratio should be > 10%."""
        assert result.total_mass_ratio > 0.10

    def test_exact_shifts_negative(self, result):
        """All exact shifts should be negative (frequency lowered)."""
        assert np.all(result.exact_shifts < 0)

    def test_linear_overestimates(self, result):
        """Linear superposition typically overestimates the shift magnitude."""
        # The linear sum is more negative than exact for most modes
        # (perturbation theory overestimates at large mass ratios)
        mag_lin = np.abs(result.summed_shifts)
        mag_exact = np.abs(result.exact_shifts)
        # At least some modes should show overestimation
        assert np.any(mag_lin > mag_exact)


class TestHB5Perturbative:
    """H-B5 supplemental: superposition works for tiny beads."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_superposition(bead_diameter=0.001, n_beads=3)

    def test_small_beads_confirm(self, result):
        """1mm beads should have much smaller superposition error."""
        assert result.mean_error < KILL_SUPERPOSITION_ERROR

    def test_mass_ratio_small(self, result):
        assert result.total_mass_ratio < 0.05


# ═══════════════════════════════════════════════════════════════════════
# Runner tests
# ═══════════════════════════════════════════════════════════════════════

class TestRunner:
    """Test the master runner function."""

    @pytest.fixture(scope="class")
    def results(self):
        return run_all_bead_string(verbose=False)

    def test_five_results(self, results):
        assert len(results) == 5

    def test_all_keys_present(self, results):
        for key in ["H-B1", "H-B2", "H-B3", "H-B4", "H-B5"]:
            assert key in results

    def test_result_types(self, results):
        assert isinstance(results["H-B1"], QLooseThreadingResult)
        assert isinstance(results["H-B2"], Sin2SensitivityResult)
        assert isinstance(results["H-B3"], MultiMaterialResult)
        assert isinstance(results["H-B4"], RepositionabilityResult)
        assert isinstance(results["H-B5"], SuperpositionResult)

    def test_three_confirmed_two_killed(self, results):
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = sum(1 for r in results.values() if not r.verdict)
        assert confirmed == 3
        assert killed == 2

    def test_verdicts_match_expectations(self, results):
        assert results["H-B1"].verdict is True   # loose threading kills Q
        assert results["H-B2"].verdict is False   # sin² breaks at 8% mass
        assert results["H-B3"].verdict is True    # multi-material alphabet
        assert results["H-B4"].verdict is True    # repositionability MI
        assert results["H-B5"].verdict is False   # superposition error

    def test_verbose_mode_runs(self):
        results = run_all_bead_string(verbose=True)
        assert len(results) == 5

    def test_all_verdicts_are_bool(self, results):
        for r in results.values():
            assert isinstance(r.verdict, bool)
