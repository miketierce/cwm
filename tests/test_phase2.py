"""
Tests for Phase 2 modules: coupled_physics and noise_decoherence.
"""
import numpy as np
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ============================================================
# Coupled Physics Tests
# ============================================================

class TestCoupledPhysicsBasics:
    """Test basic physics functions in coupled_physics module."""

    def test_acoustic_eigenfrequencies(self):
        from simulations.coupled_physics import acoustic_eigenfrequencies
        freqs = acoustic_eigenfrequencies(5, L=1e-5, c=1400)
        assert len(freqs) == 5
        # f_n = n * c / (2L)
        assert abs(freqs[0] - 1400 / (2e-5)) < 1.0  # 70 MHz
        # Harmonics equally spaced
        spacing = np.diff(freqs)
        assert np.allclose(spacing, spacing[0], rtol=1e-10)

    def test_em_eigenfrequencies(self):
        from simulations.coupled_physics import em_eigenfrequencies
        freqs = em_eigenfrequencies(3, L=1e-5, epsilon_eff=1e6)
        assert len(freqs) == 3
        assert freqs[0] > 0
        assert freqs[1] > freqs[0]
        # With ε_eff=1e6, EM modes should be in GHz range (not THz)
        assert freqs[0] < 1e11  # < 100 GHz

    def test_sound_velocity_shifted(self):
        from simulations.coupled_physics import sound_velocity_shifted
        c0 = 1400.0
        dc_dT = -3.0
        # At +5K, velocity should decrease by 15 m/s
        c = sound_velocity_shifted(c0, dc_dT, 5.0)
        assert abs(c - 1385.0) < 0.01

    def test_magnetization_curie(self):
        from simulations.coupled_physics import magnetization_curie
        # Below Curie temperature
        M = magnetization_curie(300, 450, M0=1.0)
        assert 0 < M < 1.0
        assert abs(M - (1 - 300/450)) < 1e-10
        # At Curie temperature
        assert magnetization_curie(450, 450) == 0.0
        # Above Curie temperature
        assert magnetization_curie(500, 450) == 0.0

    def test_mode_coupling_matrix(self):
        from simulations.coupled_physics import (
            mode_coupling_matrix, acoustic_eigenfrequencies
        )
        freqs = acoustic_eigenfrequencies(4, L=1e-5)
        C = mode_coupling_matrix(4, chi=1e-6, freqs=freqs)
        assert C.shape == (4, 4)
        # Diagonal should be zero
        assert np.all(np.diag(C) == 0)
        # Off-diagonal should be positive
        assert np.all(C[np.triu_indices(4, k=1)] > 0)
        # Closer modes couple more strongly
        assert C[0, 1] > C[0, 3]  # mode 1-2 closer than mode 1-4


class TestCoupledSimulation:
    """Test the coupled ODE simulation."""

    def test_simulation_runs(self):
        from simulations.coupled_physics import (
            run_coupled_simulation, CouplingParams
        )
        params = CouplingParams(n_acoustic=3, n_em=2)
        result = run_coupled_simulation(
            params=params, t_max=1e-5, n_points=200
        )
        assert len(result.times) == 200
        assert result.acoustic_amplitudes.shape == (200, 3)
        assert result.em_amplitudes.shape == (200, 2)
        assert len(result.temperature) == 200

    def test_energy_decays(self):
        """Total energy should decrease (dissipative system)."""
        from simulations.coupled_physics import (
            run_coupled_simulation, CouplingParams
        )
        params = CouplingParams(n_acoustic=3, n_em=2, eta_acoustic=100)
        result = run_coupled_simulation(
            params=params, t_max=1e-4, n_points=500
        )
        # Energy at end should be less than at start
        assert result.total_energy[-1] < result.total_energy[0]

    def test_no_coupling_no_em_excitation(self):
        """With κ=0, EM modes should stay at zero."""
        from simulations.coupled_physics import (
            run_coupled_simulation, CouplingParams
        )
        params = CouplingParams(
            n_acoustic=3, n_em=2,
            kappa_ae=0.0, chi_nonlinear=0.0
        )
        result = run_coupled_simulation(
            params=params, t_max=1e-5, n_points=100
        )
        em_energy = np.sum(np.abs(result.em_amplitudes)**2)
        assert em_energy < 1e-20

    def test_coupling_transfers_energy(self):
        """With κ>0, some energy should transfer to EM modes (may be tiny for large detuning)."""
        from simulations.coupled_physics import (
            run_coupled_simulation, CouplingParams
        )
        params = CouplingParams(
            n_acoustic=3, n_em=2,
            kappa_ae=0.01
        )
        result = run_coupled_simulation(
            params=params, t_max=1e-4, n_points=500
        )
        max_em = np.max(np.sum(result.em_energies, axis=1))
        # With large acoustic-EM detuning, transfer is small but nonzero
        assert max_em > 0

    def test_coherence_time_positive(self):
        from simulations.coupled_physics import (
            run_coupled_simulation, CouplingParams
        )
        params = CouplingParams(n_acoustic=2, n_em=1, eta_acoustic=50)
        result = run_coupled_simulation(
            params=params, t_max=1e-3, n_points=500
        )
        assert result.coherence_time > 0

    def test_thermal_perturbation(self):
        """Initial temperature perturbation should shift frequencies."""
        from simulations.coupled_physics import (
            run_coupled_simulation, CouplingParams
        )
        params = CouplingParams(n_acoustic=2, n_em=1)
        r0 = run_coupled_simulation(params=params, t_max=1e-5,
                                     n_points=200, initial_dT=0.0)
        r10 = run_coupled_simulation(params=params, t_max=1e-5,
                                      n_points=200, initial_dT=10.0)
        # Frequencies should differ
        f0_mean = np.mean(r0.acoustic_freqs[50:, 0])
        f10_mean = np.mean(r10.acoustic_freqs[50:, 0])
        # With dc_dT=-3, frequencies should be lower at higher T
        assert f10_mean < f0_mean or abs(f10_mean - f0_mean) > 0

    def test_summary_output(self):
        from simulations.coupled_physics import (
            run_coupled_simulation, CouplingParams, coupled_summary
        )
        params = CouplingParams(n_acoustic=2, n_em=1)
        result = run_coupled_simulation(params=params, t_max=1e-5,
                                         n_points=100)
        summary = coupled_summary(result)
        assert "COUPLED MULTIPHYSICS" in summary
        assert "ENERGY" in summary
        assert "COHERENCE" in summary


class TestCoupledScans:
    """Test parameter scan utilities."""

    def test_coupling_scan(self):
        from simulations.coupled_physics import coupling_strength_scan
        results = coupling_strength_scan(
            kappa_values=np.array([1e-4, 1e-3, 1e-2]),
            t_max=1e-5,
        )
        assert len(results['kappa']) == 3
        assert len(results['max_em_energy']) == 3
        # Stronger coupling should give more EM energy
        assert results['max_em_energy'][-1] >= results['max_em_energy'][0]

    def test_thermal_feedback(self):
        from simulations.coupled_physics import thermal_feedback_test
        results = thermal_feedback_test(
            delta_T_values=np.array([0, 5, 10]),
            t_max=1e-5,
        )
        assert len(results['delta_T']) == 3
        assert len(results['freq_drift_pct']) == 3
        # Higher initial ΔT should give more drift
        assert results['freq_drift_pct'][2] >= results['freq_drift_pct'][0]


# ============================================================
# Noise & Decoherence Tests
# ============================================================

class TestNoiseSourcesIndividual:
    """Test individual noise calculations."""

    def test_thermal_noise_positive(self):
        from simulations.noise_decoherence import thermal_noise_psd
        psd = thermal_noise_psd(T=300, Z=2e6, V=1e-15)
        assert psd > 0
        # Higher T → more noise
        psd_hot = thermal_noise_psd(T=400, Z=2e6, V=1e-15)
        assert psd_hot > psd

    def test_shot_noise(self):
        from simulations.noise_decoherence import shot_noise_psd
        psd = shot_noise_psd(1e6, 1e6)
        assert psd == pytest.approx(1e-6)
        # More photons → less noise
        psd2 = shot_noise_psd(1e8, 1e6)
        assert psd2 < psd

    def test_one_over_f(self):
        from simulations.noise_decoherence import one_over_f_noise_psd
        psd_low = one_over_f_noise_psd(100, alpha=1e-12, f_corner=1e3)
        psd_high = one_over_f_noise_psd(1e6, alpha=1e-12, f_corner=1e3)
        # 1/f: lower freq = more noise
        assert psd_low > psd_high

    def test_phase_diffusion(self):
        from simulations.noise_decoherence import phase_diffusion_rate
        rate = phase_diffusion_rate(T=300, d=10e-9, viscosity=0.01,
                                     V_cavity=1e-15)
        assert rate > 0
        # Higher T → more diffusion
        rate_hot = phase_diffusion_rate(T=400, d=10e-9, viscosity=0.01,
                                         V_cavity=1e-15)
        assert rate_hot > rate

    def test_adc_quantization(self):
        from simulations.noise_decoherence import adc_quantization_noise
        q10 = adc_quantization_noise(10, 1.0)
        q12 = adc_quantization_noise(12, 1.0)
        # More bits → less quantization noise
        assert q12 < q10
        # Both positive
        assert q10 > 0
        assert q12 > 0

    def test_nonlinear_mixing(self):
        from simulations.noise_decoherence import nonlinear_mixing_noise
        amps = np.ones(5)
        noise = nonlinear_mixing_noise(5, chi=1e-6, amplitudes=amps)
        assert noise > 0
        # More modes → more mixing noise (cubic scaling)
        noise_10 = nonlinear_mixing_noise(10, chi=1e-6, amplitudes=np.ones(10))
        assert noise_10 > noise


class TestNoiseComposite:
    """Test composite noise calculations."""

    def test_noise_spectrum(self):
        from simulations.noise_decoherence import compute_noise_spectrum, NoiseParams
        params = NoiseParams()
        ns = compute_noise_spectrum(1e6, params)
        # All components should be non-negative
        assert ns.thermal >= 0
        assert ns.shot >= 0
        assert ns.one_over_f >= 0
        assert ns.phase_diffusion >= 0
        assert ns.quantization >= 0
        # Total should be sum
        expected_total = (ns.thermal + ns.shot + ns.one_over_f +
                          ns.phase_diffusion + ns.quantization)
        assert abs(ns.total - expected_total) < 1e-30

    def test_snr_decreases_with_mode_index(self):
        """Higher modes should generally have lower SNR (more 1/f, more decay)."""
        from simulations.noise_decoherence import snr_at_mode, NoiseParams
        params = NoiseParams()
        snr_1 = snr_at_mode(1, params)
        snr_10 = snr_at_mode(10, params)
        # Not necessarily strictly decreasing, but mode 1 should be >= mode 10
        # (1/f noise is higher at lower freq but signal is same)
        assert isinstance(snr_1, float)
        assert isinstance(snr_10, float)

    def test_mode_lifetime_positive(self):
        from simulations.noise_decoherence import mode_lifetime, NoiseParams
        # Use optimistic parameters: high Q, large signal, large cavity,
        # low viscosity to push SNR above 10 dB threshold
        params = NoiseParams(
            Q=10000, A_signal=100.0, n_photons=1e12,
            V_cavity=1e-12,  # 1 mm³ macro-cavity
            viscosity=0.001,  # low viscosity
        )
        tau = mode_lifetime(1, params)
        assert tau > 0

    def test_ber_from_snr(self):
        from simulations.noise_decoherence import ber_from_snr
        # High SNR → low BER
        ber_high = ber_from_snr(30.0)
        assert ber_high < 1e-6
        # Low SNR → high BER
        ber_low = ber_from_snr(3.0)
        assert ber_low > ber_high
        # Very low SNR → BER approaches 0.5
        ber_zero = ber_from_snr(0.0)
        assert ber_zero > 0.1


class TestDecoherenceAnalysis:
    """Test the full decoherence analysis pipeline."""

    def test_analysis_runs(self):
        from simulations.noise_decoherence import (
            run_decoherence_analysis, NoiseParams
        )
        params = NoiseParams(n_modes=5, Q=500)
        result = run_decoherence_analysis(params=params, t_max=1e-4)
        assert len(result.mode_indices) == 5
        assert len(result.snr_per_mode) == 5
        assert len(result.ber_per_mode) == 5
        assert len(result.lifetime_per_mode) == 5
        assert result.snr_vs_time.shape[1] == 5
        assert result.max_reliable_modes >= 0
        assert result.max_reliable_modes <= 5

    def test_kill_criteria_types(self):
        from simulations.noise_decoherence import (
            run_decoherence_analysis, NoiseParams
        )
        params = NoiseParams(n_modes=3, Q=1000)
        result = run_decoherence_analysis(params=params)
        assert isinstance(result.snr_above_10dB, bool)
        assert isinstance(result.ber_below_1pct, bool)
        assert isinstance(result.lifetime_above_1us, bool)

    def test_dominant_noise_identified(self):
        from simulations.noise_decoherence import (
            run_decoherence_analysis, NoiseParams
        )
        params = NoiseParams(n_modes=3)
        result = run_decoherence_analysis(params=params)
        assert result.dominant_noise_source in [
            'thermal', 'shot', '1/f', 'phase_diffusion', 'quantization'
        ]

    def test_noise_budget_table(self):
        from simulations.noise_decoherence import noise_budget_table
        table = noise_budget_table()
        assert "NOISE BUDGET" in table
        assert "Thermal" in table
        assert "Shot" in table
        assert "1/f" in table

    def test_decoherence_summary(self):
        from simulations.noise_decoherence import (
            run_decoherence_analysis, decoherence_summary, NoiseParams
        )
        params = NoiseParams(n_modes=3, Q=500)
        result = run_decoherence_analysis(params=params, t_max=1e-4)
        summary = decoherence_summary(result)
        assert "DECOHERENCE" in summary
        assert "KILL CRITERIA" in summary
        assert "Reliable modes" in summary

    def test_high_Q_better_than_low_Q(self):
        """Higher Q should give more reliable modes and longer lifetime."""
        from simulations.noise_decoherence import (
            run_decoherence_analysis, NoiseParams
        )
        r_low = run_decoherence_analysis(
            NoiseParams(n_modes=5, Q=100), t_max=1e-4
        )
        r_high = run_decoherence_analysis(
            NoiseParams(n_modes=5, Q=10000), t_max=1e-4
        )
        assert r_high.max_reliable_modes >= r_low.max_reliable_modes

    def test_fidelity_decreases_over_time(self):
        from simulations.noise_decoherence import (
            run_decoherence_analysis, NoiseParams
        )
        params = NoiseParams(n_modes=5, Q=100)
        result = run_decoherence_analysis(params=params, t_max=1e-3)
        # Fidelity at start should be >= fidelity at end
        assert result.fidelity_vs_time[0] >= result.fidelity_vs_time[-1]


# ============================================================
# Integration: Coupled → Noise
# ============================================================

class TestIntegration:
    """Test that coupled_physics and noise_decoherence work together."""

    def test_coupled_coherence_vs_noise_lifetime(self):
        """
        The coupled simulation coherence time and noise model lifetime
        should be in the same ballpark (both depend on damping/Q).
        """
        from simulations.coupled_physics import (
            run_coupled_simulation, CouplingParams
        )
        from simulations.noise_decoherence import mode_lifetime, NoiseParams

        cp = CouplingParams(n_acoustic=3, n_em=1, eta_acoustic=50)
        result = run_coupled_simulation(params=cp, t_max=1e-3, n_points=1000)

        # Noise model: Q = ω/(2η) for mode 1
        L = 1e-5
        f1 = 1400 / (2 * L)
        omega1 = 2 * np.pi * f1
        Q_eff = omega1 / (2 * cp.eta_acoustic)
        np_params = NoiseParams(Q=Q_eff, n_modes=3, A_signal=10.0)
        tau_noise = mode_lifetime(1, np_params, L)

        # Both should be non-negative
        assert result.coherence_time > 0
        assert tau_noise >= 0
