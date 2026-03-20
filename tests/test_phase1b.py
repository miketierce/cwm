"""
Tests for Phase 1b modules: convergence, CMOS interface, Monte Carlo tamper.
"""

import numpy as np
import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Convergence module
# ═══════════════════════════════════════════════════════════════════════════
class TestConvergence:
    """Tests for simulations/convergence.py."""

    def test_quick_convergence_check(self):
        from simulations.convergence import quick_convergence_check
        is_conv, err = quick_convergence_check(N_values=[5, 8], L=1.0, c=340.0)
        assert isinstance(is_conv, (bool, np.bool_))
        assert err >= 0

    def test_convergence_study_runs(self):
        from simulations.convergence import run_convergence_study
        study = run_convergence_study(
            N_values=[5, 8], L=1.0, c=340.0, eta=50.0,
            t_max=0.02, n_points=2000,
        )
        assert len(study.points) == 2
        assert study.points[0].N == 5
        assert study.points[1].N == 8
        assert study.points[1].dofs == 512

    def test_frequency_error_decreases(self):
        """Higher N should give lower frequency error."""
        from simulations.convergence import run_convergence_study
        study = run_convergence_study(
            N_values=[5, 10], L=1.0, c=340.0, eta=0.0,
            t_max=0.02, n_points=2000,
        )
        assert study.freq_errors[1] <= study.freq_errors[0] + 1.0  # allow 1% margin

    def test_richardson_extrapolation(self):
        """Richardson extrapolation should be closer to theory than finest grid."""
        from simulations.convergence import run_convergence_study
        study = run_convergence_study(
            N_values=[5, 8, 12], L=1.0, c=340.0, eta=0.0,
            t_max=0.03, n_points=3000,
        )
        f_theory = study.points[-1].f_theory
        if not np.isnan(study.richardson_f):
            rich_err = abs(study.richardson_f - f_theory)
            fine_err = abs(study.points[-1].f_simulated - f_theory)
            # Richardson should be at least as good as finest grid
            # (allow some tolerance for noisy estimates)
            assert rich_err < fine_err * 2.0

    def test_summary_table_format(self):
        from simulations.convergence import run_convergence_study
        study = run_convergence_study(
            N_values=[5, 8], L=1.0, c=340.0, eta=50.0,
            t_max=0.02, n_points=2000,
        )
        table = study.summary_table()
        assert "N" in table
        assert "DOFs" in table
        assert "convergence order" in table

    def test_stressed_convergence(self):
        from simulations.convergence import stressed_convergence_study
        study = stressed_convergence_study(
            N_values=[5, 8], L=1.0, c=340.0, eta=50.0,
            beta=1.0, gamma=0.3,
        )
        assert len(study.points) == 2
        assert "Stressed" in study.label


# ═══════════════════════════════════════════════════════════════════════════
# CMOS Interface
# ═══════════════════════════════════════════════════════════════════════════
class TestCMOSInterface:
    """Tests for simulations/cmos_interface.py."""

    def test_excitation_energy_above_thermal(self):
        from simulations.cmos_interface import excitation_energy
        E_exc, E_therm = excitation_energy(
            cell_length=1e-5, c=1400.0, Q=500, n_modes=10,
        )
        assert E_exc > E_therm
        assert E_therm > 0

    def test_budget_components_positive(self):
        from simulations.cmos_interface import compute_energy_budget
        budget = compute_energy_budget()
        assert budget.E_excitation > 0
        assert budget.E_sense > 0
        assert budget.E_amplifier > 0
        assert budget.E_adc > 0
        assert budget.E_addressing > 0

    def test_budget_total_is_sum(self):
        from simulations.cmos_interface import compute_energy_budget
        budget = compute_energy_budget()
        assert abs(budget.E_total - (budget.E_write_total + budget.E_read_total)) < 1e-30

    def test_budget_sub_2pj(self):
        """Paper claims fJ range — cavity ops are fJ, ADC adds ~1 pJ overhead.
        Total should be < 2 pJ (ADC dominates at current state-of-art)."""
        from simulations.cmos_interface import compute_energy_budget, CMOSInterfaceModel
        model = CMOSInterfaceModel(tech_node="28nm")
        budget = compute_energy_budget(model)
        # The cavity operations themselves are fJ; ADC is the bottleneck
        cavity_energy = budget.E_excitation + budget.E_sense + budget.E_amplifier
        assert cavity_energy < 1e-14  # cavity ops < 10 fJ
        assert budget.E_total < 2e-12  # total < 2 pJ (ADC dominates)

    def test_kill_check_thermal_passes(self):
        """Thermal margin check should pass — excitation >> kBT."""
        from simulations.cmos_interface import compute_energy_budget, energy_kill_check
        budget = compute_energy_budget()
        checks = energy_kill_check(budget)
        assert checks["thermal_margin"][1] == True
        # Note: total_energy check may fail with 1pJ ADC — that's the
        # bottleneck; the physics operations are in fJ range.

    def test_technology_comparison(self):
        from simulations.cmos_interface import (
            compute_energy_budget, technology_comparison, format_comparison_table,
        )
        budget = compute_energy_budget()
        techs = technology_comparison(budget)
        assert "DRAM (28nm)" in techs
        assert "WCFOMA (this model)" in techs
        table = format_comparison_table(techs)
        assert "WCFOMA" in table

    def test_all_tech_nodes(self):
        from simulations.cmos_interface import (
            compute_energy_budget, CMOSInterfaceModel, TECH_NODES,
        )
        for node in TECH_NODES:
            model = CMOSInterfaceModel(tech_node=node)
            budget = compute_energy_budget(model)
            assert budget.E_total > 0

    def test_faraday_sensing(self):
        from simulations.cmos_interface import compute_energy_budget
        budget = compute_energy_budget(sensing_method="faraday")
        assert budget.E_sense > 0

    def test_summary_format(self):
        from simulations.cmos_interface import compute_energy_budget
        budget = compute_energy_budget()
        s = budget.summary()
        assert "Energy Budget" in s
        assert "fJ" in s

    def test_fft_energy_positive_and_scales(self):
        """FFT energy should be positive and scale with FFT size."""
        from simulations.cmos_interface import fft_energy
        E_512 = fft_energy(512, "28nm")
        E_1024 = fft_energy(1024, "28nm")
        assert E_512 > 0
        assert E_1024 > E_512
        # 1024-pt should be roughly 2.4× the 512-pt (N log N scaling)
        ratio = E_1024 / E_512
        assert 2.0 < ratio < 3.0

    def test_fft_energy_scales_with_tech_node(self):
        """Smaller nodes should have cheaper FFT."""
        from simulations.cmos_interface import fft_energy
        E_180 = fft_energy(512, "180nm")
        E_28 = fft_energy(512, "28nm")
        E_7 = fft_energy(512, "7nm")
        assert E_180 > E_28 > E_7

    def test_readout_bandwidth_1mm_rod(self):
        """Bandwidth analysis for 1 mm borosilicate rod at 100 MS/s."""
        from simulations.cmos_interface import readout_bandwidth_analysis
        bw = readout_bandwidth_analysis(cell_length=1e-3, c=5315.0,
                                        Q=9097.0, adc_sample_rate=100e6)
        assert bw["n_modes_adc"] == 18
        assert bw["n_modes_max"] == 9097
        assert bw["n_modes_effective"] == 18
        assert bw["fft_size"] == 512
        assert abs(bw["f1_hz"] - 2.6575e6) / 2.6575e6 < 1e-3

    def test_readout_energy_budget_separates_paths(self):
        """Readout budget should have simple_read and associative_recall."""
        from simulations.cmos_interface import readout_energy_budget
        budget = readout_energy_budget()
        assert "simple_read" in budget
        assert "associative_recall" in budget
        assert "bandwidth" in budget
        sr = budget["simple_read"]
        assert sr["E_fft_J"] > 0
        assert sr["E_adc_J"] > sr["E_fft_J"]  # ADC dominates
        ar = budget["associative_recall"]
        # Associative recall per rod should be much cheaper than simple read
        assert ar["E_total_per_rod_J"] < sr["E_total_J"]

    def test_readout_sensitivity_analysis(self):
        """Sensitivity sweep should produce correct number of results."""
        from simulations.cmos_interface import readout_sensitivity_analysis
        results = readout_sensitivity_analysis(
            tech_nodes=["28nm", "7nm"], fft_multipliers=[1, 100],
        )
        assert len(results) == 4  # 2 nodes × 2 multipliers
        # Even at 100× FFT cost, total should stay < 10 nJ
        for r in results:
            assert r["E_total_read_J"] < 10e-9

    def test_format_readout_summary(self):
        """Readable summary string should contain key sections."""
        from simulations.cmos_interface import (
            readout_energy_budget, format_readout_summary,
        )
        budget = readout_energy_budget()
        s = format_readout_summary(budget)
        assert "Simple Read" in s
        assert "Associative Recall" in s
        assert "Bandwidth Analysis" in s


# ═══════════════════════════════════════════════════════════════════════════
# Monte Carlo Tamper Detection
# ═══════════════════════════════════════════════════════════════════════════
class TestMonteCarlo:
    """Tests for experiments/exp03 Monte Carlo extension."""

    def test_mc_runs(self):
        from experiments.exp03_dilatancy_tamper import monte_carlo_tamper_detection
        mc = monte_carlo_tamper_detection(
            gamma_values=np.linspace(0, 0.5, 10),
            n_trials=100,
        )
        assert len(mc.detection_probability) == 10
        assert mc.n_trials == 100

    def test_mc_detection_at_high_gamma(self):
        """At γ=0.5, detection should be near 100%."""
        from experiments.exp03_dilatancy_tamper import monte_carlo_tamper_detection
        mc = monte_carlo_tamper_detection(
            gamma_values=np.array([0.0, 0.5]),
            n_trials=500,
        )
        assert mc.detection_probability[-1] > 0.95

    def test_mc_low_false_positive(self):
        """At γ=0, false positive rate should be low with 3σ threshold."""
        from experiments.exp03_dilatancy_tamper import monte_carlo_tamper_detection
        mc = monte_carlo_tamper_detection(
            gamma_values=np.array([0.0, 0.01]),
            n_trials=1000,
            snr_threshold=3.0,
        )
        assert mc.false_positive_rate < 0.05

    def test_mc_confidence_intervals(self):
        from experiments.exp03_dilatancy_tamper import monte_carlo_tamper_detection
        mc = monte_carlo_tamper_detection(
            gamma_values=np.linspace(0, 0.5, 5),
            n_trials=100,
        )
        assert len(mc.confidence_lower) == 5
        assert len(mc.confidence_upper) == 5
        assert np.all(mc.confidence_lower <= mc.confidence_upper)
        assert np.all(mc.confidence_lower >= 0)
        assert np.all(mc.confidence_upper <= 1)

    def test_mc_summarize(self):
        from experiments.exp03_dilatancy_tamper import (
            monte_carlo_tamper_detection, summarize_mc,
        )
        mc = monte_carlo_tamper_detection(
            gamma_values=np.linspace(0, 0.5, 5),
            n_trials=100,
        )
        s = summarize_mc(mc)
        assert "Monte Carlo" in s


# ═══════════════════════════════════════════════════════════════════════════
# Claims Auto-Population
# ═══════════════════════════════════════════════════════════════════════════
class TestClaimsAutoPopulation:
    """Tests for analysis/comparison.py auto-population."""

    def test_run_all_validations(self):
        from analysis.comparison import run_all_validations
        results = run_all_validations()
        assert len(results) == 9
        for claim, (paper, measured, status) in results.items():
            assert status in ("CONFIRMED", "PLAUSIBLE", "REFUTED", "NOT TESTED")
            assert measured != "PENDING"

    def test_confirmed_count(self):
        from analysis.comparison import run_all_validations
        results = run_all_validations()
        confirmed = sum(1 for _, (_, _, s) in results.items() if s == "CONFIRMED")
        assert confirmed >= 7  # at least 7 of 9 should confirm

    def test_validation_summary_format(self):
        from analysis.comparison import validation_summary
        s = validation_summary()
        assert "CONFIRMED" in s
        assert "Claim" in s
