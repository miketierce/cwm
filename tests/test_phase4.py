"""
Tests for Phase 4 modules:
  - hopfield_recall: Hopfield/Ising associative recall
  - ferroelectric_photonic: Ferroelectric MZI photonic cell
  - photothermal_gating: Photothermal viscosity gating
  - forced_oscillation: Forced-oscillation selective write/erase
"""
import numpy as np
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ============================================================
# Hopfield Recall Tests
# ============================================================

class TestHopfieldBasics:
    """Test Hopfield network creation and pattern storage."""

    def test_create_network(self):
        from simulations.hopfield_recall import (
            create_hopfield_network, generate_random_patterns
        )
        patterns = generate_random_patterns(50, 5)  # N=50, P=5
        net = create_hopfield_network(patterns)
        assert net.weights.shape == (50, 50)
        assert net.N == 50
        assert net.P == 5
        # Diagonal should be zero (no self-connections)
        assert np.all(np.diag(net.weights) == 0)
        # Weights should be symmetric
        assert np.allclose(net.weights, net.weights.T)

    def test_generate_random_patterns(self):
        from simulations.hopfield_recall import generate_random_patterns
        pats = generate_random_patterns(100, 3)  # N=100, P=3
        assert pats.shape == (3, 100)
        # Binary: all +1 or -1
        assert np.all(np.isin(pats, [-1, 1]))

    def test_hopfield_energy(self):
        from simulations.hopfield_recall import (
            create_hopfield_network, generate_random_patterns, hopfield_energy
        )
        pats = generate_random_patterns(20, 2)
        net = create_hopfield_network(pats)
        # Stored patterns should be low energy
        e0 = hopfield_energy(pats[0], net)
        # Energy is negative for stored patterns
        assert e0 < 0

    def test_recall_stored_pattern(self):
        from simulations.hopfield_recall import (
            create_hopfield_network, generate_random_patterns,
            recall_pattern, corrupt_pattern
        )
        pats = generate_random_patterns(50, 3)
        net = create_hopfield_network(pats)
        # Corrupt pattern 0 with 10% noise
        corrupted = corrupt_pattern(pats[0], 0.1)
        result = recall_pattern(net, corrupted, target_idx=0)
        # Should recall original
        assert result.overlap > 0.8, f"Overlap {result.overlap} too low"
        assert result.converged

    def test_corrupt_pattern(self):
        from simulations.hopfield_recall import corrupt_pattern
        pat = np.ones(100)
        noisy = corrupt_pattern(pat, 0.2)
        n_flipped = np.sum(noisy != pat)
        assert 10 <= n_flipped <= 30  # ~20 flips expected

    def test_mask_pattern(self):
        from simulations.hopfield_recall import mask_pattern
        pat = np.ones(100)
        masked = mask_pattern(pat, 0.3)
        n_zero = np.sum(masked == 0)
        assert 20 <= n_zero <= 40  # ~30 zeros expected


class TestHopfieldCapacity:
    """Test storage capacity measurement."""

    def test_capacity_scaling(self):
        from simulations.hopfield_recall import measure_capacity
        cap = measure_capacity(N=50, noise_fraction=0.1, n_trials=10)
        assert cap.N == 50
        assert cap.capacity_threshold > 0


class TestHopfieldInterference:
    """Test physical interference-based recall."""

    def test_interference_recall(self):
        from simulations.hopfield_recall import (
            generate_random_patterns, create_hopfield_network,
            interference_recall
        )
        pats = generate_random_patterns(20, 3)
        net = create_hopfield_network(pats)
        result = interference_recall(net, pats[0], target_idx=0)
        # Perfect probe should have high overlap
        assert result.overlap > 0.3

    def test_binary_vs_trinary_comparison(self):
        from simulations.hopfield_recall import compare_binary_trinary
        comp = compare_binary_trinary(N=30, n_trials=10)
        assert "binary" in comp
        assert "trinary" in comp
        assert comp["binary"].capacity_threshold >= 0


class TestHopfieldSummary:
    """Test summary generation."""

    def test_summary_runs(self):
        from simulations.hopfield_recall import hopfield_summary
        text = hopfield_summary()
        assert len(text) > 100
        assert "Hopfield" in text or "HOPFIELD" in text


# ============================================================
# Ferroelectric Photonic Tests
# ============================================================

class TestFerroelectricMaterials:
    """Test material database and physics."""

    def test_material_database(self):
        from simulations.ferroelectric_photonic import material_database
        db = material_database()
        assert "HZO" in db
        assert "BaTiO3" in db
        assert db["HZO"].delta_n > 0
        assert db["HZO"].cmos_compatible

    def test_phase_shift(self):
        from simulations.ferroelectric_photonic import (
            material_database, ferroelectric_phase_shift
        )
        db = material_database()
        hzo = db["HZO"]
        dphi = ferroelectric_phase_shift(
            delta_n=hzo.delta_n, L_fe=100e-6, wavelength=1550e-9
        )
        assert dphi > 0
        # For HZO: Δφ = 2π × 100µm × 1e-3 / 1550nm ≈ 0.4 rad
        assert 0.1 < dphi < 2.0

    def test_mzi_transfer_at_pi(self):
        from simulations.ferroelectric_photonic import mzi_transfer
        # At Δφ = π, MZI output should be near zero for ideal 50:50
        assert mzi_transfer(np.pi) < 0.05
        # Symmetry
        assert abs(mzi_transfer(0.5) - mzi_transfer(-0.5)) < 1e-10

    def test_mzi_transfer_range(self):
        from simulations.ferroelectric_photonic import mzi_transfer
        # Output should be between 0 and 1
        for phi in np.linspace(-np.pi, np.pi, 50):
            val = mzi_transfer(phi)
            assert 0 <= val <= 1.0

    def test_switching_energy(self):
        from simulations.ferroelectric_photonic import switching_energy
        E = switching_energy(voltage=5.0)
        assert E > 0
        assert E < 1e-6  # should be sub-µJ

    def test_mzi_cell_characterization(self):
        from simulations.ferroelectric_photonic import characterize_mzi_cell
        result = characterize_mzi_cell("HZO")
        assert result.material.name.startswith("Hf")
        assert len(result.states) == 3  # trinary
        # Should have distinct phase shifts
        phases = [s.phase_shift for s in result.states]
        assert phases[0] != phases[2]  # P_down ≠ P_up


class TestFerroelectricOptimization:
    """Test interaction length and crossbar."""

    def test_optimize_length(self):
        from simulations.ferroelectric_photonic import optimize_interaction_length
        L_opt = optimize_interaction_length("HZO")
        assert L_opt > 0
        assert L_opt < 1e-2  # < 1 cm

    def test_length_sweep(self):
        from simulations.ferroelectric_photonic import length_sweep
        lengths, phases, contrasts = length_sweep("HZO")
        assert len(lengths) > 0
        assert len(contrasts) == len(lengths)
        assert len(phases) == len(lengths)

    def test_crossbar_simulation(self):
        from simulations.ferroelectric_photonic import simulate_crossbar
        W = np.random.RandomState(42).randn(4, 4)
        W = W / np.max(np.abs(W))  # normalize to [-1, 1]
        x = np.array([1, -1, 1, -1], dtype=float)
        result = simulate_crossbar(W, x, material_name="HZO")
        assert result.N == 4
        assert result.output_intensities.shape == (4,)
        assert result.total_energy_nJ > 0

    def test_technology_comparison(self):
        from simulations.ferroelectric_photonic import technology_comparison
        comp = technology_comparison()
        assert len(comp) >= 4
        names = [c.name for c in comp]
        assert any("HZO" in n for n in names)

    def test_ferroelectric_summary(self):
        from simulations.ferroelectric_photonic import ferroelectric_summary
        text = ferroelectric_summary()
        assert len(text) > 100
        assert "MZI" in text or "ferroelectric" in text.lower()


# ============================================================
# Photothermal Gating Tests
# ============================================================

class TestPhotothermalPhysics:
    """Test Arrhenius viscosity and photothermal heating."""

    def test_arrhenius_viscosity_reference(self):
        from simulations.photothermal_gating import arrhenius_viscosity
        # At reference temperature, should return reference viscosity
        eta = arrhenius_viscosity(300.0, eta_ref=0.01, T_ref=300.0)
        assert abs(eta - 0.01) < 1e-6

    def test_arrhenius_viscosity_decreases_with_T(self):
        from simulations.photothermal_gating import arrhenius_viscosity
        eta_cold = arrhenius_viscosity(280.0)
        eta_hot = arrhenius_viscosity(350.0)
        assert eta_cold > eta_hot

    def test_photothermal_temperature_rise(self):
        from simulations.photothermal_gating import photothermal_temperature_rise
        dT = photothermal_temperature_rise(
            intensity_W_cm2=100.0,
            absorption_coeff=1e5,
            efficiency=0.9,
            exposure_time_s=1e-6,
        )
        assert dT > 0
        assert dT < 1e6  # sanity check: not absurd

    def test_temperature_rise_scales_with_intensity(self):
        from simulations.photothermal_gating import photothermal_temperature_rise
        dT1 = photothermal_temperature_rise(100.0, 1e5, 0.9, 1e-6)
        dT2 = photothermal_temperature_rise(200.0, 1e5, 0.9, 1e-6)
        assert abs(dT2 / dT1 - 2.0) < 0.01

    def test_rotational_diffusion_rate(self):
        from simulations.photothermal_gating import rotational_diffusion_rate
        D = rotational_diffusion_rate(300.0, 0.01)
        assert D > 0
        # Higher viscosity → lower diffusion
        D_high = rotational_diffusion_rate(300.0, 10.0)
        assert D_high < D


class TestPhotothermalMaterials:
    """Test material and gel databases."""

    def test_photothermal_materials(self):
        from simulations.photothermal_gating import photothermal_materials
        mats = photothermal_materials()
        assert "gold_nanorods" in mats
        assert mats["gold_nanorods"].efficiency > 0

    def test_gel_database(self):
        from simulations.photothermal_gating import gel_database
        gels = gel_database()
        assert "agarose_2pct" in gels
        # Agarose: cold is gelled (high η), hot is liquid (low η)
        ag = gels["agarose_2pct"]
        assert ag.eta_cold > ag.eta_hot

    def test_viscosity_profile(self):
        from simulations.photothermal_gating import compute_viscosity_profile
        prof = compute_viscosity_profile()
        assert len(prof.temperatures) == 100
        assert len(prof.viscosities) == 100
        # Viscosity should decrease with temperature
        assert prof.viscosities[0] > prof.viscosities[-1]


class TestPhotothermalStates:
    """Test state analysis and write/hold cycle."""

    def test_analyze_state(self):
        from simulations.photothermal_gating import analyze_state
        state = analyze_state("hold", 300.0, 100.0)
        assert state.mode == "hold"
        assert state.viscosity == 100.0
        assert state.snr_db > -100  # not -inf

    def test_write_hold_cycle(self):
        from simulations.photothermal_gating import analyze_write_hold_cycle
        write, hold = analyze_write_hold_cycle()
        # Hold state should have higher viscosity than write state
        assert hold.viscosity > write.viscosity
        # Hold state should have better SNR (lower noise)
        assert hold.snr_db >= write.snr_db

    def test_duty_cycle_optimization(self):
        from simulations.photothermal_gating import optimize_duty_cycle
        result = optimize_duty_cycle()
        assert 0 < result.optimal_write_fraction < 1
        assert result.optimal_snr_db > -100

    def test_spatial_gating(self):
        from simulations.photothermal_gating import simulate_spatial_gating
        result = simulate_spatial_gating(n_cells=10)
        assert result.n_cells == 10
        assert len(result.temperature_profile) == 10
        assert len(result.viscosity_profile) == 10
        # At least the target cell should be warm
        assert np.max(result.temperature_profile) > 300.0

    def test_compare_strategies(self):
        from simulations.photothermal_gating import compare_gating_strategies
        strategies = compare_gating_strategies()
        assert len(strategies) >= 3
        # Silica should have highest SNR (highest viscosity)
        silica = strategies["Silica sol-gel (permanent)"]
        baseline = strategies["Baseline (no gel)"]
        assert silica.snr_db >= baseline.snr_db

    def test_photothermal_summary(self):
        from simulations.photothermal_gating import photothermal_summary
        text = photothermal_summary()
        assert len(text) > 100
        assert "WRITE" in text or "write" in text
        assert "HOLD" in text or "hold" in text


# ============================================================
# Forced Oscillation Tests
# ============================================================

class TestForcedOscillatorPhysics:
    """Test core forced oscillator functions."""

    def test_mode_frequencies(self):
        from simulations.forced_oscillation import mode_frequencies
        freqs = mode_frequencies(5, L=1e-5, c=1400)
        assert len(freqs) == 5
        # f_n = n * 1400 / (2e-5) = n * 70 MHz
        assert abs(freqs[0] - 70e6) < 1.0
        # Harmonics
        assert abs(freqs[4] / freqs[0] - 5) < 1e-10

    def test_forced_amplitude_at_resonance(self):
        from simulations.forced_oscillation import (
            forced_oscillator_amplitude, Q_factor
        )
        omega_0 = 2 * np.pi * 70e6
        Q = 500.0
        eta = omega_0 / (2 * Q)
        F0 = 1.0
        # At resonance
        A_res = forced_oscillator_amplitude(omega_0, omega_0, eta, F0)
        # Expected: F0 / (2η ω₀)
        expected = F0 / (2 * eta * omega_0)
        assert abs(A_res - expected) / expected < 0.01

    def test_forced_amplitude_off_resonance(self):
        from simulations.forced_oscillation import forced_oscillator_amplitude
        omega_0 = 2 * np.pi * 70e6
        eta = omega_0 / 1000
        # Far off resonance
        omega_d = 2 * omega_0
        A_off = forced_oscillator_amplitude(omega_d, omega_0, eta)
        A_on = forced_oscillator_amplitude(omega_0, omega_0, eta)
        # Off-resonance should be much smaller
        assert A_off < A_on * 0.1

    def test_phase_at_resonance(self):
        from simulations.forced_oscillation import forced_oscillator_phase
        omega_0 = 2 * np.pi * 70e6
        eta = omega_0 / 1000
        # At resonance, phase should be ~π/2
        phase = forced_oscillator_phase(omega_0, omega_0, eta)
        assert abs(phase - np.pi / 2) < 0.1

    def test_Q_factor(self):
        from simulations.forced_oscillation import Q_factor
        omega_0 = 2 * np.pi * 70e6
        eta = omega_0 / 1000
        Q = Q_factor(omega_0, eta)
        assert abs(Q - 500) < 1.0

    def test_thermal_amplitude(self):
        from simulations.forced_oscillation import thermal_amplitude
        A_th = thermal_amplitude(70e6, T=300.0)
        assert A_th > 0
        # At higher T, more thermal noise
        A_hot = thermal_amplitude(70e6, T=600.0)
        assert A_hot > A_th


class TestFrequencyResponse:
    """Test frequency response computation."""

    def test_frequency_response_shape(self):
        from simulations.forced_oscillation import compute_frequency_response
        resp = compute_frequency_response(70e6, Q=500.0)
        assert len(resp.drive_freqs) == 1000
        assert len(resp.amplitudes) == 1000
        assert len(resp.phases) == 1000

    def test_frequency_response_peak(self):
        from simulations.forced_oscillation import compute_frequency_response
        resp = compute_frequency_response(70e6, Q=500.0)
        # Peak should be near resonant frequency
        peak_idx = np.argmax(resp.amplitudes)
        f_peak = resp.drive_freqs[peak_idx]
        assert abs(f_peak - 70e6) / 70e6 < 0.01

    def test_bandwidth(self):
        from simulations.forced_oscillation import compute_frequency_response
        resp = compute_frequency_response(70e6, Q=500.0)
        # 3 dB bandwidth should be ~f/Q = 70e6/500 = 140 kHz
        expected_bw = 70e6 / 500
        assert abs(resp.bandwidth_3dB - expected_bw) / expected_bw < 0.01


class TestSelectiveWrite:
    """Test selective write operations."""

    def test_selective_write_basic(self):
        from simulations.forced_oscillation import selective_write
        result = selective_write(1, n_modes=10, Q=500.0)
        assert result.target_mode == 1
        assert result.selectivity_dB > 0
        assert result.write_energy_J > 0
        assert result.write_time_s > 0

    def test_selectivity_improves_with_Q(self):
        from simulations.forced_oscillation import selective_write
        r_low = selective_write(1, n_modes=10, Q=100.0)
        r_high = selective_write(1, n_modes=10, Q=5000.0)
        assert r_high.selectivity_dB > r_low.selectivity_dB

    def test_cross_talk_present(self):
        from simulations.forced_oscillation import selective_write
        result = selective_write(5, n_modes=10, Q=500.0)
        # Should have cross-talk into all other modes
        assert len(result.cross_talk) == 9  # all other modes
        # Nearest neighbor should have most cross-talk
        assert result.cross_talk[4] > result.cross_talk[1]

    def test_multi_mode_write(self):
        from simulations.forced_oscillation import multi_mode_write
        pattern = np.array([1, 0, 0.5, 0, 1, 0, 0.5, 0, 1, 0])
        result = multi_mode_write(pattern)
        assert result.n_modes == 10
        assert result.pattern_fidelity > 0.5
        assert result.total_energy_J > 0


class TestErase:
    """Test erase operations."""

    def test_broadband_erase(self):
        from simulations.forced_oscillation import erase_modes
        result = erase_modes(method="broadband")
        assert result.method == "broadband"
        assert len(result.modes_erased) == 10
        assert result.erase_time_s > 0

    def test_antiphase_erase(self):
        from simulations.forced_oscillation import erase_modes
        result = erase_modes(method="antiphase")
        assert result.method == "antiphase"
        assert result.erase_time_s > 0

    def test_thermal_erase_is_passive(self):
        from simulations.forced_oscillation import erase_modes
        result = erase_modes(method="thermal")
        assert result.erase_energy_J == 0.0  # passive

    def test_selective_erase(self):
        from simulations.forced_oscillation import erase_modes
        result = erase_modes(mode_indices=[3, 7], method="antiphase")
        assert result.modes_erased == [3, 7]


class TestForcedOscillationAnalysis:
    """Test analysis and summary functions."""

    def test_selectivity_vs_Q(self):
        from simulations.forced_oscillation import selectivity_vs_Q
        Qs, sels, bits = selectivity_vs_Q(Q_values=np.array([100, 500, 1000]))
        assert len(Qs) == 3
        assert len(sels) == 3
        # Higher Q → better selectivity
        assert sels[2] > sels[0]

    def test_energy_budget(self):
        from simulations.forced_oscillation import compute_energy_budget
        budget = compute_energy_budget()
        assert budget.energy_per_bit_J > 0
        assert budget.total_cycle_J > 0
        assert len(budget.comparison) >= 5

    def test_time_domain_simulation(self):
        from simulations.forced_oscillation import simulate_forced_oscillator
        t, x, v = simulate_forced_oscillator(
            f_0=1000.0, f_drive=1000.0, Q=50.0, t_max=0.5
        )
        assert len(t) > 0
        assert len(x) == len(t)
        # Should build up to steady state
        amp_early = np.max(np.abs(x[:len(x)//10]))
        amp_late = np.max(np.abs(x[-len(x)//10:]))
        assert amp_late > amp_early

    def test_forced_oscillation_summary(self):
        from simulations.forced_oscillation import forced_oscillation_summary
        text = forced_oscillation_summary()
        assert len(text) > 100
        assert "FORCED" in text or "forced" in text
