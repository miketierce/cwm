"""
Tests for Phase 2b: Mitigation Analysis Module.

Tests cover:
  - Scenario construction (baseline, gel, cavity, photons, combined)
  - Parameter sweep functions (viscosity, photons, cavity size)
  - Viability map computation
  - Minimum viable configuration finder
  - Comparison table generation
"""

import sys
import numpy as np
import pytest

sys.path.insert(0, "/Users/Mike/Code/wcfoma")

from simulations.mitigations import (
    MitigationScenario,
    MitigationSweepResult,
    ViabilityMap,
    baseline_scenario,
    gel_immobilized_scenario,
    larger_cavity_scenario,
    high_photon_scenario,
    combined_scenario,
    evaluate_scenario,
    sweep_viscosity,
    sweep_photons,
    sweep_cavity_size,
    compute_viability_map,
    find_minimum_viable,
    scenario_comparison_table,
    mitigation_summary,
)
from simulations.noise_decoherence import NoiseParams


# ===========================================================================
# Scenario construction tests
# ===========================================================================

class TestScenarioConstruction:
    """Test that scenarios are built with correct parameters."""

    def test_baseline_is_default_params(self):
        sc = baseline_scenario()
        assert sc.params.viscosity == 0.01
        assert sc.params.n_photons == 1e6
        assert sc.params.V_cavity == 1e-15
        assert sc.cavity_length_m == 1e-5

    def test_gel_increases_viscosity(self):
        sc = gel_immobilized_scenario(1000)
        assert sc.params.viscosity == pytest.approx(10.0)
        assert sc.params.n_photons == 1e6  # unchanged

    def test_gel_default_multiplier(self):
        sc = gel_immobilized_scenario()
        assert sc.params.viscosity == pytest.approx(10.0)  # 0.01 * 1000

    def test_larger_cavity_volume(self):
        sc = larger_cavity_scenario(100)
        assert sc.params.V_cavity == pytest.approx(1e-12)  # (100 µm)³
        assert sc.cavity_length_m == pytest.approx(1e-4)

    def test_larger_cavity_energy_scales(self):
        sc = larger_cavity_scenario(100)
        # Energy scales as (L/10)³ = 1000×
        assert sc.energy_cost_fJ == pytest.approx(2600.0)

    def test_high_photon_readout(self):
        sc = high_photon_scenario(1e8)
        assert sc.params.n_photons == 1e8
        assert sc.readout_energy_fJ == pytest.approx(10000.0)

    def test_combined_sets_all_params(self):
        sc = combined_scenario(100, 50, 1e9, 2.0)
        assert sc.params.viscosity == pytest.approx(1.0)
        assert sc.params.V_cavity == pytest.approx((50e-6)**3)
        assert sc.params.n_photons == 1e9
        assert sc.params.A_signal == 2.0


# ===========================================================================
# Evaluation tests
# ===========================================================================

class TestEvaluation:
    """Test scenario evaluation produces correct results."""

    def test_baseline_not_viable(self):
        sc = baseline_scenario()
        ev = evaluate_scenario(sc)
        assert ev["viable"] is False
        assert ev["reliable_modes"] == 0
        assert ev["snr_db"] < 0

    def test_combined_viable(self):
        sc = combined_scenario(1000, 10, 1e8)
        ev = evaluate_scenario(sc)
        assert ev["viable"] is True
        assert ev["reliable_modes"] >= 5
        assert ev["snr_db"] > 10

    def test_gel_only_not_viable(self):
        """Gel alone doesn't overcome shot noise."""
        sc = gel_immobilized_scenario(10000)
        ev = evaluate_scenario(sc)
        assert ev["viable"] is False
        assert ev["snr_db"] < 1.0

    def test_photons_only_not_viable(self):
        """More photons alone doesn't overcome phase diffusion."""
        sc = high_photon_scenario(1e10)
        ev = evaluate_scenario(sc)
        assert ev["viable"] is False
        assert ev["snr_db"] < 0

    def test_evaluation_returns_required_keys(self):
        sc = baseline_scenario()
        ev = evaluate_scenario(sc)
        required_keys = [
            "name", "snr_db", "reliable_modes", "dominant_noise",
            "total_energy_fJ", "density_tb_cm3", "viable",
            "kill_snr", "kill_ber", "kill_lifetime",
        ]
        for key in required_keys:
            assert key in ev, f"Missing key: {key}"


# ===========================================================================
# Sweep tests
# ===========================================================================

class TestSweeps:
    """Test parameter sweep functions."""

    def test_viscosity_sweep_returns_correct_shape(self):
        mults = np.logspace(0, 4, 10)
        result = sweep_viscosity(mults)
        assert len(result.snr_values) == 10
        assert len(result.reliable_modes) == 10
        assert result.parameter_name == "viscosity_multiplier"

    def test_viscosity_sweep_snr_increases(self):
        """Higher viscosity should monotonically increase SNR."""
        mults = np.logspace(0, 4, 10)
        result = sweep_viscosity(mults)
        # SNR should generally increase (may plateau)
        assert result.snr_values[-1] >= result.snr_values[0]

    def test_photon_sweep_returns_correct_shape(self):
        counts = np.logspace(5, 10, 8)
        result = sweep_photons(counts)
        assert len(result.snr_values) == 8
        assert result.parameter_name == "n_photons"

    def test_cavity_sweep_returns_correct_shape(self):
        sizes = np.logspace(1, 3, 8)
        result = sweep_cavity_size(sizes)
        assert len(result.snr_values) == 8
        assert result.parameter_name == "cavity_length_um"

    def test_sweep_with_mitigated_base_finds_threshold(self):
        """With gel, photon sweep should find a viable threshold."""
        base = NoiseParams(viscosity=10.0)  # gel ×1000
        counts = np.logspace(6, 10, 20)
        result = sweep_photons(counts, base_params=base)
        assert result.threshold_value is not None
        assert result.threshold_value < 1e10


# ===========================================================================
# Viability map tests
# ===========================================================================

class TestViabilityMap:
    """Test 2D viability map computation."""

    def test_viability_map_shape(self):
        vm = compute_viability_map(
            viscosity_mults=np.logspace(0, 3, 5),
            photon_counts=np.logspace(6, 9, 5),
        )
        assert vm.snr_grid.shape == (5, 5)
        assert vm.modes_grid.shape == (5, 5)
        assert vm.viable_mask.shape == (5, 5)

    def test_viability_map_has_viable_region(self):
        """High viscosity + high photons should be viable."""
        vm = compute_viability_map(
            viscosity_mults=np.logspace(0, 4, 8),
            photon_counts=np.logspace(6, 10, 8),
        )
        assert np.any(vm.viable_mask), "No viable region found in map"

    def test_viability_map_baseline_corner_not_viable(self):
        """Low viscosity + low photons should not be viable."""
        vm = compute_viability_map(
            viscosity_mults=np.logspace(0, 4, 8),
            photon_counts=np.logspace(6, 10, 8),
        )
        # Bottom-left corner (low η, low photons)
        assert not vm.viable_mask[0, 0]


# ===========================================================================
# Minimum viable finder tests
# ===========================================================================

class TestMinimumViable:
    """Test minimum viable configuration finder."""

    def test_finds_gel_photons_path(self):
        mvp = find_minimum_viable()
        assert "gel_photons" in mvp
        assert mvp["gel_photons"]["modes"] >= 5
        assert mvp["gel_photons"]["snr_db"] > 10

    def test_finds_cavity_photons_path(self):
        mvp = find_minimum_viable()
        assert "cavity_photons" in mvp
        assert mvp["cavity_photons"]["modes"] >= 5

    def test_finds_combined_path(self):
        mvp = find_minimum_viable()
        assert "combined" in mvp
        assert mvp["combined"]["modes"] >= 5

    def test_minimum_viable_energy_reported(self):
        mvp = find_minimum_viable()
        for path, config in mvp.items():
            assert "total_energy_fJ" in config
            assert config["total_energy_fJ"] > 0


# ===========================================================================
# Table and summary tests
# ===========================================================================

class TestOutput:
    """Test formatted output functions."""

    def test_comparison_table_includes_all_scenarios(self):
        scenarios = [baseline_scenario(), gel_immobilized_scenario(1000)]
        table = scenario_comparison_table(scenarios)
        assert "Baseline" in table
        assert "Gel immobilized" in table

    def test_mitigation_summary_runs(self):
        summary = mitigation_summary()
        assert "MINIMUM VIABLE" in summary
        assert "KEY INSIGHT" in summary
        assert len(summary) > 200
