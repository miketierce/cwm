"""
Tests for Phase 5 — Glass Acoustic Resonator module.

Validates:
  - Glass material database
  - Mode spectrum computation
  - Thermal stability analysis
  - SNR (and comparison to ferrofluid numbers)
  - Rayleigh perturbation encoding
  - Information capacity
  - Associative recall via spectral correlation
  - Technology comparison
  - Bill of materials
  - Summary generation
"""
import numpy as np
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ============================================================
# Glass Material Database Tests
# ============================================================

class TestGlassDatabase:
    """Test glass material property database."""

    def test_database_has_four_types(self):
        from simulations.glass_resonator import glass_database
        db = glass_database()
        assert "soda_lime" in db
        assert "borosilicate" in db
        assert "fused_silica" in db
        assert "lead_glass" in db
        assert len(db) == 4

    def test_borosilicate_properties(self):
        from simulations.glass_resonator import glass_database
        g = glass_database()["borosilicate"]
        assert g.v_longitudinal == 5500.0
        assert g.density == 2230.0
        assert g.Q_acoustic == 10000.0
        assert g.alpha_thermal == pytest.approx(3.3e-6)
        assert g.youngs_modulus == 63e9

    def test_fused_silica_highest_Q(self):
        from simulations.glass_resonator import glass_database
        db = glass_database()
        Qs = {k: v.Q_acoustic for k, v in db.items()}
        assert max(Qs, key=Qs.get) == "fused_silica"
        assert Qs["fused_silica"] == 100000.0

    def test_fused_silica_lowest_thermal_expansion(self):
        from simulations.glass_resonator import glass_database
        db = glass_database()
        alphas = {k: v.alpha_thermal for k, v in db.items()}
        assert min(alphas, key=alphas.get) == "fused_silica"
        assert alphas["fused_silica"] == pytest.approx(0.55e-6)

    def test_lead_glass_lowest_velocity(self):
        from simulations.glass_resonator import glass_database
        db = glass_database()
        vs = {k: v.v_longitudinal for k, v in db.items()}
        assert min(vs, key=vs.get) == "lead_glass"
        assert vs["lead_glass"] == 3800.0

    def test_all_properties_positive(self):
        from simulations.glass_resonator import glass_database
        for name, g in glass_database().items():
            assert g.v_longitudinal > 0, f"{name} v"
            assert g.density > 0, f"{name} ρ"
            assert g.Q_acoustic > 0, f"{name} Q"
            assert g.alpha_thermal > 0, f"{name} α"
            assert g.youngs_modulus > 0, f"{name} E"
            assert 0 < g.poisson_ratio < 0.5, f"{name} ν"

    def test_all_have_cost_notes(self):
        from simulations.glass_resonator import glass_database
        for name, g in glass_database().items():
            assert len(g.cost_note) > 0, f"{name} missing cost"


# ============================================================
# Rod Geometry Tests
# ============================================================

class TestRodGeometry:
    """Test rod geometry calculations."""

    def test_default_rod(self):
        from simulations.glass_resonator import RodGeometry
        rod = RodGeometry()
        assert rod.length == 0.15
        assert rod.diameter == 6e-3
        assert rod.glass_type == "borosilicate"

    def test_cross_section(self):
        from simulations.glass_resonator import RodGeometry
        rod = RodGeometry(diameter=6e-3)
        expected = np.pi * (3e-3) ** 2
        assert rod.cross_section == pytest.approx(expected)

    def test_volume(self):
        from simulations.glass_resonator import RodGeometry
        rod = RodGeometry(length=0.15, diameter=6e-3)
        expected = np.pi * (3e-3) ** 2 * 0.15
        assert rod.volume == pytest.approx(expected)


# ============================================================
# Mode Spectrum Tests
# ============================================================

class TestModeSpectrum:
    """Test acoustic mode computation."""

    def test_fundamental_frequency_borosilicate(self):
        from simulations.glass_resonator import RodGeometry, compute_mode_spectrum
        rod = RodGeometry(length=0.15, glass_type="borosilicate")
        spec = compute_mode_spectrum(rod, n_modes=10)
        # FEM-corrected: v_bar = √(E/ρ) = √(63e9/2230) ≈ 5315 m/s
        # f1 = v_bar / (2L) = 5315.18 / 0.30 ≈ 17717 Hz
        assert spec.f_fundamental == pytest.approx(17717.3, rel=0.01)

    def test_modes_are_harmonics(self):
        from simulations.glass_resonator import compute_mode_spectrum, RodGeometry
        rod = RodGeometry()
        spec = compute_mode_spectrum(rod, n_modes=20)
        # f_n should equal n * f_1
        for i in range(20):
            assert spec.frequencies[i] == pytest.approx(
                (i + 1) * spec.f_fundamental, rel=1e-10
            )

    def test_mode_spacing_equals_fundamental(self):
        from simulations.glass_resonator import compute_mode_spectrum
        spec = compute_mode_spectrum()
        assert spec.mode_spacing == spec.f_fundamental

    def test_mass_calculation(self):
        from simulations.glass_resonator import compute_mode_spectrum, RodGeometry
        rod = RodGeometry(length=0.15, diameter=6e-3, glass_type="borosilicate")
        spec = compute_mode_spectrum(rod)
        # M = ρ * V = 2230 * π * (3e-3)² * 0.15
        expected_mass = 2230 * np.pi * (3e-3) ** 2 * 0.15
        assert spec.mass == pytest.approx(expected_mass, rel=1e-6)

    def test_linewidth(self):
        from simulations.glass_resonator import compute_mode_spectrum, RodGeometry
        rod = RodGeometry(glass_type="borosilicate")
        spec = compute_mode_spectrum(rod, n_modes=5)
        # linewidth = f / Q
        for i in range(5):
            assert spec.linewidths[i] == pytest.approx(
                spec.frequencies[i] / 10000.0, rel=1e-6
            )

    def test_coherence_time(self):
        from simulations.glass_resonator import compute_mode_spectrum, RodGeometry
        rod = RodGeometry(glass_type="borosilicate")
        spec = compute_mode_spectrum(rod, n_modes=1)
        # τ = Q / (π * f)
        expected = 10000.0 / (np.pi * spec.f_fundamental)
        assert spec.coherence_times[0] == pytest.approx(expected, rel=1e-6)
        # Should be ~0.17 seconds
        assert 0.1 < spec.coherence_times[0] < 0.3

    def test_fused_silica_higher_frequency(self):
        from simulations.glass_resonator import compute_mode_spectrum, RodGeometry
        rod_b = RodGeometry(glass_type="borosilicate")
        rod_s = RodGeometry(glass_type="fused_silica")
        spec_b = compute_mode_spectrum(rod_b, n_modes=1)
        spec_s = compute_mode_spectrum(rod_s, n_modes=1)
        # Fused silica has higher v → higher f
        assert spec_s.f_fundamental > spec_b.f_fundamental

    def test_longer_rod_lower_frequency(self):
        from simulations.glass_resonator import compute_mode_spectrum, RodGeometry
        rod_short = RodGeometry(length=0.10)
        rod_long = RodGeometry(length=0.20)
        spec_short = compute_mode_spectrum(rod_short, n_modes=1)
        spec_long = compute_mode_spectrum(rod_long, n_modes=1)
        assert spec_short.f_fundamental > spec_long.f_fundamental

    def test_default_rod_used(self):
        from simulations.glass_resonator import compute_mode_spectrum
        spec = compute_mode_spectrum()  # No args → default rod
        assert spec.f_fundamental > 0
        assert len(spec.frequencies) == 100  # default n_modes


# ============================================================
# Thermal Stability Tests
# ============================================================

class TestThermalStability:
    """Test thermal mode capacity calculations."""

    def test_borosilicate_modes_at_1K(self):
        from simulations.glass_resonator import thermal_stability, RodGeometry
        rod = RodGeometry(glass_type="borosilicate")
        result = thermal_stability(rod, delta_T=1.0)
        # n < 1 / (2*3.3e-6*1 + 1/10000) = 1/(6.6e-6 + 1e-4) ≈ 9380
        assert result.max_safe_modes == pytest.approx(9380, abs=50)

    def test_fused_silica_more_modes(self):
        from simulations.glass_resonator import thermal_stability, RodGeometry
        rod_b = RodGeometry(glass_type="borosilicate")
        rod_s = RodGeometry(glass_type="fused_silica")
        stab_b = thermal_stability(rod_b, delta_T=1.0)
        stab_s = thermal_stability(rod_s, delta_T=1.0)
        # Fused silica: lower α, higher Q → way more modes
        assert stab_s.max_safe_modes > stab_b.max_safe_modes
        assert stab_s.max_safe_modes > 50000

    def test_tighter_temp_means_fewer_modes(self):
        from simulations.glass_resonator import thermal_stability
        stab_1K = thermal_stability(delta_T=1.0)
        stab_5K = thermal_stability(delta_T=5.0)
        assert stab_1K.max_safe_modes > stab_5K.max_safe_modes

    def test_total_bits_positive(self):
        from simulations.glass_resonator import thermal_stability
        result = thermal_stability()
        assert result.total_bits > 0
        assert result.total_bytes == result.total_bits / 8

    def test_bits_per_mode_consistent_with_snr(self):
        from simulations.glass_resonator import thermal_stability, compute_snr
        rod_kwargs = dict(glass_type="borosilicate")
        from simulations.glass_resonator import RodGeometry
        rod = RodGeometry(**rod_kwargs)
        stab = thermal_stability(rod)
        snr = compute_snr(rod)
        assert stab.bits_per_mode == pytest.approx(snr.bits_per_mode, rel=0.01)

    def test_borosilicate_total_bits_over_100k(self):
        """This is the key result: >100k bits from a $8 glass rod."""
        from simulations.glass_resonator import thermal_stability, RodGeometry
        rod = RodGeometry(glass_type="borosilicate")
        result = thermal_stability(rod, delta_T=1.0)
        assert result.total_bits > 100000


# ============================================================
# SNR Tests
# ============================================================

class TestSNR:
    """Test signal-to-noise analysis."""

    def test_snr_borosilicate_at_1nm(self):
        from simulations.glass_resonator import compute_snr, RodGeometry
        rod = RodGeometry(glass_type="borosilicate")
        snr = compute_snr(rod, A_drive=1e-9)
        # Should be ~99 dB
        assert 90 < snr.SNR_dB < 110

    def test_phase_diffusion_always_zero(self):
        """This is why glass wins: no phase diffusion in a solid."""
        from simulations.glass_resonator import compute_snr, RodGeometry, glass_database
        for glass_type in glass_database():
            rod = RodGeometry(glass_type=glass_type)
            snr = compute_snr(rod)
            assert snr.phase_diffusion_fraction == 0.0

    def test_snr_increases_with_amplitude(self):
        from simulations.glass_resonator import compute_snr
        snr_low = compute_snr(A_drive=0.1e-9)
        snr_high = compute_snr(A_drive=10e-9)
        assert snr_high.SNR_dB > snr_low.SNR_dB

    def test_snr_scales_as_amplitude_squared(self):
        from simulations.glass_resonator import compute_snr
        snr1 = compute_snr(A_drive=1e-9)
        snr2 = compute_snr(A_drive=10e-9)
        # 10× amplitude → 100× SNR → +20 dB
        assert snr2.SNR_dB - snr1.SNR_dB == pytest.approx(20, abs=0.1)

    def test_thermal_amplitude_is_femtometers(self):
        from simulations.glass_resonator import compute_snr
        snr = compute_snr()
        # Thermal amplitude for macro glass rod should be in femtometer range
        assert snr.A_thermal < 1e-13  # sub-picometer
        assert snr.A_thermal > 1e-18  # above attometers

    def test_bits_per_mode_over_15(self):
        """Glass gives >15 bits/mode vs. ferrofluid's 2.28."""
        from simulations.glass_resonator import compute_snr
        snr = compute_snr(A_drive=1e-9)
        assert snr.bits_per_mode > 15

    def test_glass_beats_ferrofluid_by_100dB(self):
        """The fundamental result: glass SNR >> ferrofluid SNR."""
        from simulations.glass_resonator import compute_snr
        snr = compute_snr(A_drive=1e-9)
        ferrofluid_baseline_dB = -6.5
        advantage = snr.SNR_dB - ferrofluid_baseline_dB
        assert advantage > 95  # >95 dB improvement

    def test_effective_mass_half_rod_mass(self):
        from simulations.glass_resonator import compute_snr, compute_mode_spectrum
        spec = compute_mode_spectrum()
        snr = compute_snr()
        assert snr.m_eff == pytest.approx(spec.mass / 2, rel=1e-6)


# ============================================================
# Perturbation Encoding Tests
# ============================================================

class TestPerturbation:
    """Test Rayleigh perturbation model."""

    def test_single_mass_shifts_modes(self):
        from simulations.glass_resonator import (
            rayleigh_perturbation, Perturbation, RodGeometry
        )
        rod = RodGeometry()
        p = Perturbation(position=rod.length / 4, delta_mass=0.1e-3)
        result = rayleigh_perturbation(rod, [p], n_modes=10)
        # All shifts should be negative (added mass lowers frequency)
        assert np.all(result.shifts <= 0)
        # Some modes should be detectably shifted
        assert np.any(result.detectable)

    def test_mass_at_node_no_shift(self):
        """Mass at a node of mode n should not shift that mode."""
        from simulations.glass_resonator import (
            rayleigh_perturbation, Perturbation, RodGeometry
        )
        rod = RodGeometry()
        # Mode 2 has a node at L/2: sin(2πx/L) = sin(π) = 0
        p = Perturbation(position=rod.length / 2, delta_mass=0.1e-3)
        result = rayleigh_perturbation(rod, [p], n_modes=5)
        # Mode 2 (index 1) should have zero shift
        assert abs(result.shifts[1]) < 1e-15  # mode 2 at node
        # Mode 1 should still be shifted (not at its node)
        assert abs(result.shifts[0]) > 1e-10

    def test_mass_at_antinode_max_shift(self):
        """Mass at rod center (antinode of mode 1) maximally shifts mode 1."""
        from simulations.glass_resonator import (
            rayleigh_perturbation, Perturbation, RodGeometry
        )
        rod = RodGeometry()
        p_center = Perturbation(position=rod.length / 2, delta_mass=0.1e-3)
        p_quarter = Perturbation(position=rod.length / 4, delta_mass=0.1e-3)
        r_center = rayleigh_perturbation(rod, [p_center], n_modes=1)
        r_quarter = rayleigh_perturbation(rod, [p_quarter], n_modes=1)
        # Center is antinode of mode 1: sin(π/2) = 1
        assert abs(r_center.shifts[0]) >= abs(r_quarter.shifts[0])

    def test_shift_proportional_to_mass(self):
        from simulations.glass_resonator import (
            rayleigh_perturbation, Perturbation, RodGeometry
        )
        rod = RodGeometry()
        # Use position that avoids nodes: L/5 avoids integer multiples for modes 1-5
        p1 = Perturbation(position=rod.length * 0.2, delta_mass=0.1e-3)
        p2 = Perturbation(position=rod.length * 0.2, delta_mass=0.2e-3)
        r1 = rayleigh_perturbation(rod, [p1], n_modes=5)
        r2 = rayleigh_perturbation(rod, [p2], n_modes=5)
        # Double mass → double shift (only check modes with significant shift)
        significant = np.abs(r1.shifts) > 1e-12
        ratio = r2.shifts[significant] / r1.shifts[significant]
        assert np.allclose(ratio, 2.0, rtol=1e-6)

    def test_multiple_perturbations_superpose(self):
        from simulations.glass_resonator import (
            rayleigh_perturbation, Perturbation, RodGeometry
        )
        rod = RodGeometry()
        p1 = Perturbation(position=0.03, delta_mass=0.1e-3)
        p2 = Perturbation(position=0.10, delta_mass=0.2e-3)
        r_both = rayleigh_perturbation(rod, [p1, p2], n_modes=5)
        r1 = rayleigh_perturbation(rod, [p1], n_modes=5)
        r2 = rayleigh_perturbation(rod, [p2], n_modes=5)
        # Superposition: combined shift = sum of individual shifts
        assert np.allclose(r_both.shifts, r1.shifts + r2.shifts, atol=1e-15)

    def test_signature_normalized(self):
        from simulations.glass_resonator import rayleigh_perturbation
        result = rayleigh_perturbation()
        assert np.max(np.abs(result.signature)) == pytest.approx(1.0, abs=1e-10)

    def test_perturbed_freqs_lower(self):
        """Added mass always lowers frequencies."""
        from simulations.glass_resonator import (
            rayleigh_perturbation, Perturbation, RodGeometry
        )
        rod = RodGeometry()
        p = Perturbation(position=rod.length / 3, delta_mass=0.5e-3)
        result = rayleigh_perturbation(rod, [p], n_modes=10)
        # Perturbed frequencies should be <= unperturbed
        assert np.all(result.perturbed_freqs <= result.unperturbed_freqs + 1e-6)

    def test_different_positions_different_signatures(self):
        """Different perturbation positions create different spectral fingerprints."""
        from simulations.glass_resonator import (
            rayleigh_perturbation, Perturbation, RodGeometry
        )
        rod = RodGeometry()
        p_a = Perturbation(position=rod.length * 0.25, delta_mass=0.1e-3)
        p_b = Perturbation(position=rod.length * 0.33, delta_mass=0.1e-3)
        r_a = rayleigh_perturbation(rod, [p_a], n_modes=10)
        r_b = rayleigh_perturbation(rod, [p_b], n_modes=10)
        # Signatures should differ
        corr = np.dot(r_a.signature, r_b.signature) / (
            np.linalg.norm(r_a.signature) * np.linalg.norm(r_b.signature)
        )
        assert corr < 0.99  # Not identical

    def test_expected_shift_magnitude(self):
        """Check shift magnitude matches Rayleigh formula."""
        from simulations.glass_resonator import (
            rayleigh_perturbation, Perturbation, RodGeometry, compute_mode_spectrum
        )
        rod = RodGeometry()
        dm = 0.1e-3
        x = rod.length / 4
        p = Perturbation(position=x, delta_mass=dm)
        result = rayleigh_perturbation(rod, [p], n_modes=1)
        spec = compute_mode_spectrum(rod, n_modes=1)
        M = spec.mass
        # Rayleigh: Δf/f = -(dm/2M) * sin²(πx/L)
        expected = -(dm / (2 * M)) * np.sin(np.pi * x / rod.length) ** 2
        assert result.shifts[0] == pytest.approx(expected, rel=1e-6)


# ============================================================
# Information Capacity Tests
# ============================================================

class TestCapacity:
    """Test perturbation encoding capacity."""

    def test_ten_blobs_capacity(self):
        from simulations.glass_resonator import perturbation_capacity
        result = perturbation_capacity(
            n_perturbations=10,
            position_resolution=100,
            mass_levels=8,
        )
        # 10 × (log2(100) + log2(8)) = 10 × (6.64 + 3) = 96.4 bits
        assert result.total_bits == pytest.approx(96.4, abs=1)

    def test_fifty_blobs_capacity(self):
        from simulations.glass_resonator import perturbation_capacity
        result = perturbation_capacity(
            n_perturbations=50,
            position_resolution=100,
            mass_levels=8,
        )
        assert result.total_bits == pytest.approx(482.2, abs=1)

    def test_capacity_scales_with_perturbations(self):
        from simulations.glass_resonator import perturbation_capacity
        r1 = perturbation_capacity(n_perturbations=5)
        r2 = perturbation_capacity(n_perturbations=10)
        assert r2.total_bits == pytest.approx(r1.total_bits * 2, rel=1e-6)

    def test_bytes_correct(self):
        from simulations.glass_resonator import perturbation_capacity
        result = perturbation_capacity()
        assert result.total_bytes == result.total_bits / 8


# ============================================================
# Associative Recall Tests
# ============================================================

class TestAssociativeRecall:
    """Test spectral correlation recall."""

    def test_perfect_recall(self):
        from simulations.glass_resonator import associative_recall
        stored = [
            np.array([1, 0, -1, 0.5, -0.5]),
            np.array([-1, 0.5, 0, -0.5, 1]),
            np.array([0.5, 0.5, 0.5, 0.5, 0.5]),
        ]
        query = stored[1].copy()  # Exact match to pattern 1
        result = associative_recall(query, stored)
        assert result.best_match_index == 1
        assert result.best_match_correlation == pytest.approx(1.0, abs=1e-10)

    def test_noisy_recall(self):
        from simulations.glass_resonator import associative_recall
        rng = np.random.default_rng(42)
        stored = [rng.standard_normal(20) for _ in range(5)]
        query = stored[2] + 0.1 * rng.standard_normal(20)  # Noisy version
        result = associative_recall(query, stored)
        assert result.best_match_index == 2
        assert result.best_match_correlation > 0.9

    def test_orthogonal_patterns_low_correlation(self):
        from simulations.glass_resonator import associative_recall
        # Nearly orthogonal patterns
        stored = [
            np.array([1, 0, 0, 0]),
            np.array([0, 1, 0, 0]),
            np.array([0, 0, 1, 0]),
        ]
        query = np.array([1, 0, 0, 0])
        result = associative_recall(query, stored)
        assert result.best_match_index == 0
        assert result.best_match_correlation == pytest.approx(1.0, abs=1e-10)
        # Others should have 0 correlation
        assert result.correlations[1] == pytest.approx(0.0, abs=1e-10)
        assert result.correlations[2] == pytest.approx(0.0, abs=1e-10)

    def test_result_metadata(self):
        from simulations.glass_resonator import associative_recall
        stored = [np.ones(10), -np.ones(10)]
        query = np.ones(10)
        result = associative_recall(query, stored)
        assert result.n_rods == 2
        assert result.n_modes == 10


# ============================================================
# Technology Comparison Tests
# ============================================================

class TestTechComparison:
    """Test technology comparison output."""

    def test_returns_five_entries(self):
        from simulations.glass_resonator import technology_comparison
        entries = technology_comparison()
        assert len(entries) == 5

    def test_glass_beats_ferrofluid_snr(self):
        from simulations.glass_resonator import technology_comparison
        entries = technology_comparison()
        glass = entries[0]
        ff_base = entries[1]
        ff_mit = entries[2]
        assert glass.SNR_dB > ff_base.SNR_dB + 90  # >90 dB better
        assert glass.SNR_dB > ff_mit.SNR_dB + 80

    def test_glass_zero_phase_diffusion(self):
        from simulations.glass_resonator import technology_comparison
        entries = technology_comparison()
        glass = entries[0]
        assert glass.phase_diffusion_pct == 0.0

    def test_ferrofluid_has_phase_diffusion(self):
        from simulations.glass_resonator import technology_comparison
        entries = technology_comparison()
        ff_base = entries[1]
        assert ff_base.phase_diffusion_pct == 77.5

    def test_glass_is_non_volatile(self):
        from simulations.glass_resonator import technology_comparison
        entries = technology_comparison()
        glass = entries[0]
        assert glass.non_volatile is True

    def test_glass_has_cheapest_prototype(self):
        from simulations.glass_resonator import technology_comparison
        entries = technology_comparison()
        glass = entries[0]
        assert "$63" in glass.prototype_cost


# ============================================================
# Bill of Materials Tests
# ============================================================

class TestBOM:
    """Test bill of materials."""

    def test_bom_items_exist(self):
        from simulations.glass_resonator import bill_of_materials
        items, total = bill_of_materials()
        assert len(items) >= 8

    def test_bom_total_under_100(self):
        from simulations.glass_resonator import bill_of_materials
        items, total = bill_of_materials()
        assert total < 100.0

    def test_bom_total_is_sum(self):
        from simulations.glass_resonator import bill_of_materials
        items, total = bill_of_materials()
        assert total == pytest.approx(sum(i.cost_usd for i in items))

    def test_bom_all_have_sources(self):
        from simulations.glass_resonator import bill_of_materials
        items, _ = bill_of_materials()
        for item in items:
            assert len(item.source) > 0


# ============================================================
# Experiment Plan Tests
# ============================================================

class TestExperimentPlan:
    """Test experiment plan structure."""

    def test_five_experiments(self):
        from simulations.glass_resonator import experiment_plan
        plan = experiment_plan()
        assert len(plan) == 5

    def test_experiments_have_required_fields(self):
        from simulations.glass_resonator import experiment_plan
        required = {"id", "name", "description", "setup", "procedure",
                    "success_criterion", "predicted", "kill_criterion"}
        for exp in experiment_plan():
            for field in required:
                assert field in exp, f"Exp {exp.get('id')} missing {field}"

    def test_first_experiment_is_mode_spectrum(self):
        from simulations.glass_resonator import experiment_plan
        plan = experiment_plan()
        assert "mode spectrum" in plan[0]["name"].lower() or \
               "EXP-G01" == plan[0]["id"]


# ============================================================
# Summary Tests
# ============================================================

class TestSummary:
    """Test summary generation."""

    def test_summary_contains_key_info(self):
        from simulations.glass_resonator import glass_resonator_summary
        text = glass_resonator_summary()
        assert "Glass" in text or "glass" in text
        assert "SNR" in text
        assert "Phase diffusion" in text
        assert "0%" in text

    def test_summary_contains_cost(self):
        from simulations.glass_resonator import glass_resonator_summary
        text = glass_resonator_summary()
        assert "$" in text

    def test_summary_contains_comparison(self):
        from simulations.glass_resonator import glass_resonator_summary
        text = glass_resonator_summary()
        assert "ferrofluid" in text.lower()
