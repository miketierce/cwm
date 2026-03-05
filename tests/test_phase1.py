"""
Extended tests for Phase 1 simulation modules:
  - Sensitivity analysis
  - Ferrofluid material model
  - Multi-mode interference
  - Grid convergence (FD-based)

Run with: pytest tests/ -v
"""

import numpy as np
import pytest

from simulations.sensitivity import (
    run_full_sensitivity,
    sweep_damping_vs_coherence,
    sweep_zim_factor_vs_coherence,
    sweep_Q_vs_modes,
    sweep_deltaT_vs_modes,
    sweep_alpha_vs_modes,
    sweep_gamma_vs_drift,
    sweep_cavity_length_vs_density,
    compute_elasticity,
    SweepResult,
)

from simulations.ferrofluid import (
    FerrofluidSpec, characterize, check_kill_criteria,
    sound_velocity, effective_viscosity, acoustic_damping_rate, estimate_Q,
)

from simulations.interference import (
    encode_data, evolve_superposition, readout_modes,
    write_read_verify, associative_recall, generate_mode_spectrum,
    ModeEncoding,
)

from simulations.meep_fdtd import fd_convergence_study


# ===================================================================
# Sensitivity Analysis Tests
# ===================================================================
class TestSensitivity:
    """Tests for parameter sensitivity sweeps."""

    def test_damping_vs_coherence_inverse(self):
        """τ = 1/(2η) — strictly inverse."""
        sw = sweep_damping_vs_coherence()
        # Check a few values
        for eta, tau in zip(sw.param_values[:5], sw.metric_values[:5]):
            assert tau == pytest.approx(1.0 / (2.0 * eta), rel=1e-10)

    def test_zim_factor_reciprocal(self):
        """Coherence ratio = 1/factor."""
        sw = sweep_zim_factor_vs_coherence()
        for f, r in zip(sw.param_values, sw.metric_values):
            assert r == pytest.approx(1.0 / f, rel=1e-10)

    def test_Q_modes_monotonic(self):
        """Higher Q → more modes (or same)."""
        sw = sweep_Q_vs_modes(use_zim=True)
        for i in range(len(sw.metric_values) - 1):
            assert sw.metric_values[i + 1] >= sw.metric_values[i]

    def test_deltaT_modes_monotonic_decreasing(self):
        """Higher ΔT → fewer modes."""
        sw = sweep_deltaT_vs_modes(use_zim=True)
        for i in range(len(sw.metric_values) - 1):
            assert sw.metric_values[i + 1] <= sw.metric_values[i]

    def test_gamma_drift_monotonic(self):
        """Higher γ → more drift."""
        sw = sweep_gamma_vs_drift()
        for i in range(len(sw.metric_values) - 1):
            assert sw.metric_values[i + 1] >= sw.metric_values[i] - 1e-10

    def test_full_sensitivity_report(self):
        """Full report completes and has all sweeps."""
        report = run_full_sensitivity()
        assert len(report.sweeps) == 8
        assert len(report.elasticity) == 8
        # Elasticity values should be finite
        for name, e in report.elasticity.items():
            assert np.isfinite(e), f"Non-finite elasticity for {name}"

    def test_elasticity_damping_is_minus_one(self):
        """τ = 1/(2η) → elasticity = -1 (pure inverse)."""
        sw = sweep_damping_vs_coherence()
        e = compute_elasticity(
            sw.param_values, sw.metric_values,
            sw.baseline_value, sw.baseline_metric,
        )
        assert e == pytest.approx(-1.0, abs=0.25)


# ===================================================================
# Ferrofluid Material Model Tests
# ===================================================================
class TestFerrofluid:
    """Tests for ferrofluid material property models."""

    def test_sound_velocity_range(self):
        """Sound velocity should be in 800-2000 m/s range."""
        spec = FerrofluidSpec()
        v = sound_velocity(spec)
        assert 800 < v < 2000

    def test_sound_velocity_temperature_dependence(self):
        """Higher T → lower sound velocity (thermal expansion)."""
        spec = FerrofluidSpec()
        v_cold = sound_velocity(spec, T=280)
        v_hot = sound_velocity(spec, T=340)
        assert v_cold > v_hot

    def test_viscosity_positive(self):
        """Viscosity should always be positive."""
        spec = FerrofluidSpec()
        eta = effective_viscosity(spec)
        assert eta > 0

    def test_viscosity_increases_with_field(self):
        """Magneto-viscous effect: η increases with H."""
        spec = FerrofluidSpec()
        eta_0 = effective_viscosity(spec, H=0)
        eta_H = effective_viscosity(spec, H=1e5)
        assert eta_H >= eta_0

    def test_viscosity_einstein_correction(self):
        """At H=0, viscosity should follow Einstein correction."""
        spec = FerrofluidSpec(phi=0.01)  # Dilute
        eta = effective_viscosity(spec, H=0)
        expected = spec.carrier_viscosity * (1 + 2.5 * 0.01 + 6.2 * 0.01**2)
        assert eta == pytest.approx(expected, rel=0.01)

    def test_Q_decreases_with_frequency(self):
        """Q should decrease at higher frequencies (more absorption)."""
        spec = FerrofluidSpec()
        Q_1M = estimate_Q(spec, freq=1e6)
        Q_100M = estimate_Q(spec, freq=100e6)
        assert Q_1M > Q_100M

    def test_characterize_returns_valid(self):
        """characterize() should return finite, positive values."""
        char = characterize()
        assert char.v_sound > 0
        assert char.rho > 0
        assert char.eta_visc > 0
        assert char.Q_1MHz > 0
        assert np.isfinite(char.Q_1MHz)

    def test_kill_criteria_structure(self):
        """check_kill_criteria returns proper format."""
        char = characterize()
        criteria = check_kill_criteria(char)
        assert "Q at 1 MHz" in criteria
        for name, (value, threshold, status) in criteria.items():
            assert status in ("PASS", "FAIL", "WARN")

    def test_density_physical(self):
        """Effective density should be between carrier and magnetite."""
        spec = FerrofluidSpec(phi=0.10)
        assert 900 < spec.density < 5200

    def test_particle_moment(self):
        """Magnetic moment should be reasonable for 10nm magnetite."""
        spec = FerrofluidSpec()
        m = spec.m_particle
        assert 1e-22 < m < 1e-18  # Typical range for nanoscale magnetite


# ===================================================================
# Multi-Mode Interference Tests
# ===================================================================
class TestInterference:
    """Tests for multi-mode superposition and recall."""

    def test_mode_spectrum_harmonic(self):
        """Mode frequencies should be harmonics of fundamental."""
        freqs, damping = generate_mode_spectrum(n_modes=5, f_fundamental=100.0)
        expected = np.array([100, 200, 300, 400, 500], dtype=float)
        np.testing.assert_allclose(freqs, expected)

    def test_encode_amplitude(self):
        """Amplitude encoding: data → amplitudes, phases = 0."""
        data = np.array([1.0, 2.0, 3.0])
        enc = encode_data(data, encoding="amplitude")
        np.testing.assert_allclose(enc.amplitudes, [1.0, 2.0, 3.0])
        np.testing.assert_allclose(enc.phases, [0.0, 0.0, 0.0])

    def test_encode_phase(self):
        """Phase encoding: amplitudes = 1, data → phases."""
        data = np.array([1.0, 2.0, 3.0])
        enc = encode_data(data, encoding="phase")
        np.testing.assert_allclose(enc.amplitudes, [1.0, 1.0, 1.0])
        assert np.all(enc.phases >= 0)

    def test_evolve_preserves_shape(self):
        """Evolution should produce time array of correct length."""
        data = np.array([1.0, 0.5])
        enc = encode_data(data)
        result = evolve_superposition(enc, t_end=0.01, n_points=1000)
        assert result.time.shape == (1000,)
        assert result.signal.shape == (1000,)
        assert result.mode_signals.shape == (2, 1000)

    def test_noiseless_perfect_recovery(self):
        """With Q=∞ and no noise, fidelity should be ~1."""
        data = np.array([1.0, 0.5, 0.8])
        r = write_read_verify(data, Q=1e6, t_hold=1e-5, noise=0.0)
        assert r["fidelity"] > 0.90

    def test_noise_degrades_fidelity(self):
        """Adding heavy noise should reduce fidelity on average."""
        np.random.seed(99)
        data = np.array([1.0, 0.5, 0.8, 0.3, 0.7])
        r_clean = write_read_verify(data, Q=500, t_hold=1e-4, noise=0.0)
        # Average over several noisy runs to avoid flaky single-run comparisons
        fid_noisy = np.mean([
            write_read_verify(data, Q=500, t_hold=1e-4, noise=10.0)["fidelity"]
            for _ in range(5)
        ])
        assert r_clean["fidelity"] >= fid_noisy

    def test_associative_recall_correct(self):
        """Associative recall should find the correct pattern."""
        np.random.seed(42)
        n_modes = 8

        patterns = [np.random.rand(n_modes) for _ in range(5)]
        stored = [encode_data(d, n_modes=n_modes, Q=500) for d in patterns]

        # Query is exact copy of pattern 3
        query = patterns[3].copy()
        best_idx, overlap, _ = associative_recall(stored, query, n_modes=n_modes, Q=500)
        assert best_idx == 3
        assert overlap > 0.9

    def test_associative_recall_noisy(self):
        """Associative recall should work with moderate noise."""
        np.random.seed(123)
        n_modes = 10

        patterns = [np.random.rand(n_modes) * 5 for _ in range(3)]
        stored = [encode_data(d, n_modes=n_modes, Q=500) for d in patterns]

        # Add small noise to pattern 1
        query = patterns[1] + np.random.normal(0, 0.1, n_modes)
        query = np.abs(query)
        best_idx, _, _ = associative_recall(stored, query, n_modes=n_modes, Q=500)
        assert best_idx == 1

    def test_complex_amplitudes(self):
        """complex_amplitudes() should have correct magnitude."""
        enc = ModeEncoding(
            amplitudes=np.array([1.0, 2.0]),
            phases=np.array([0.0, np.pi/4]),
            frequencies=np.array([100.0, 200.0]),
            damping_rates=np.array([1.0, 1.0]),
        )
        c = enc.complex_amplitudes()
        np.testing.assert_allclose(np.abs(c), [1.0, 2.0])


# ===================================================================
# Grid Convergence Tests (FD-based, no Meep required)
# ===================================================================
class TestGridConvergence:
    """Tests for finite-difference grid convergence."""

    def test_fd_convergence_normal_media(self):
        """FD solver should converge for normal media (ε=1)."""
        result = fd_convergence_study(
            Nx_values=[10, 15, 20, 30],
            eps_host=1.0 + 0j,
            n_modes=3,
        )
        errors = result['relative_errors']
        # Error should decrease with resolution
        assert errors[-1] < errors[0] or errors[-1] < 0.01

    def test_fd_convergence_returns_eigenvalues(self):
        """Should return eigenvalues for each resolution."""
        result = fd_convergence_study(
            Nx_values=[10, 15],
            eps_host=1.0 + 0j,
            n_modes=3,
        )
        assert len(result['eigenvalues']) == 2
        assert len(result['Nx_values']) == 2

    def test_fd_finest_eigenvalues_positive(self):
        """Finest grid eigenvalues should be positive."""
        result = fd_convergence_study(
            Nx_values=[15, 20],
            eps_host=1.0 + 0j,
            n_modes=3,
        )
        assert np.all(result['finest_k2'] > 0)
