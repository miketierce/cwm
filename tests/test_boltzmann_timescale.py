"""
Tests for S11 — Boltzmann: Timescale Hierarchy & Mode Populations
==================================================================

Hypotheses: H-Bt1 through H-Bt4
"""

import numpy as np
import pytest

from simulations.boltzmann_timescale import (
    # Helpers
    _acoustic_frequencies,
    _ringdown_time,
    _thermal_drift_period,
    _boltzmann_weights,
    _partition_function,
    _r_squared,
    _mode_coupling_matrix,
    _snr_at_mode,
    _mode_capacity_bits,
    _golden_positions,
    _sensitivity_matrix,
    # Result types
    DecadeSpacingResult,
    SpectralReddeningResult,
    OptimalReadoutResult,
    PartitionCapacityResult,
    # Experiments
    exp_decade_spacing,
    exp_spectral_reddening,
    exp_optimal_readout,
    exp_partition_capacity,
    # Constants
    H_PLANCK,
    # Runner
    run_all_boltzmann,
)

from simulations.common import K_B, C_FERROFLUID


# ═══════════════════════════════════════════════════════════════════════
# Helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Unit tests for all helper functions."""

    # --- _acoustic_frequencies ---

    def test_acoustic_frequencies_count(self):
        f = _acoustic_frequencies(10)
        assert len(f) == 10

    def test_acoustic_frequencies_fundamental(self):
        L = 1e-5
        f = _acoustic_frequencies(1, L=L)
        np.testing.assert_allclose(f[0], C_FERROFLUID / (2 * L), rtol=1e-10)

    def test_acoustic_frequencies_harmonic_series(self):
        f = _acoustic_frequencies(5)
        ratios = f / f[0]
        np.testing.assert_allclose(ratios, [1, 2, 3, 4, 5], rtol=1e-10)

    def test_acoustic_frequencies_increase(self):
        f = _acoustic_frequencies(20)
        assert np.all(np.diff(f) > 0)

    def test_acoustic_frequencies_custom_L(self):
        L = 1e-3
        f = _acoustic_frequencies(3, L=L)
        expected = np.array([1, 2, 3]) * C_FERROFLUID / (2 * L)
        np.testing.assert_allclose(f, expected, rtol=1e-10)

    # --- _ringdown_time ---

    def test_ringdown_time_formula(self):
        Q, f = 500, 1e7
        tau = _ringdown_time(Q, f)
        np.testing.assert_allclose(tau, Q / (np.pi * f), rtol=1e-10)

    def test_ringdown_time_proportional_to_Q(self):
        f = 1e7
        assert _ringdown_time(1000, f) == 2.0 * _ringdown_time(500, f)

    def test_ringdown_time_inversely_proportional_to_f(self):
        Q = 500
        assert _ringdown_time(Q, 1e7) == 2.0 * _ringdown_time(Q, 2e7)

    def test_ringdown_time_positive(self):
        assert _ringdown_time(100, 1e6) > 0

    # --- _thermal_drift_period ---

    def test_thermal_drift_period_formula(self):
        Q, f, alpha, dT_dt = 500, 1e7, 0.0022, 0.1
        T_th = _thermal_drift_period(Q, f, alpha, dT_dt)
        expected = 1.0 / (Q * alpha * abs(dT_dt))
        np.testing.assert_allclose(T_th, expected, rtol=1e-10)

    def test_thermal_drift_period_independent_of_f(self):
        """T_th = 1/(Q·α·|dT/dt|) does not depend on frequency."""
        T1 = _thermal_drift_period(500, 1e6, 0.0022, 0.1)
        T2 = _thermal_drift_period(500, 1e8, 0.0022, 0.1)
        np.testing.assert_allclose(T1, T2, rtol=1e-10)

    def test_thermal_drift_period_decreases_with_alpha(self):
        T1 = _thermal_drift_period(500, 1e7, 0.001, 0.1)
        T2 = _thermal_drift_period(500, 1e7, 0.01, 0.1)
        assert T2 < T1

    def test_thermal_drift_period_zero_dT_dt(self):
        T = _thermal_drift_period(500, 1e7, 0.0022, 0.0)
        assert T == np.inf

    # --- _boltzmann_weights ---

    def test_boltzmann_weights_sum_to_one(self):
        freqs = np.array([1e7, 2e7, 3e7, 4e7])
        w = _boltzmann_weights(freqs, 300.0)
        np.testing.assert_allclose(np.sum(w), 1.0, rtol=1e-10)

    def test_boltzmann_weights_nonneg(self):
        freqs = _acoustic_frequencies(10)
        w = _boltzmann_weights(freqs, 300.0)
        assert np.all(w >= 0)

    def test_boltzmann_weights_decrease_with_frequency(self):
        """Higher frequency modes get less weight (lower Boltzmann factor)."""
        freqs = _acoustic_frequencies(5)
        w = _boltzmann_weights(freqs, 300.0)
        # At room temperature, hf << k_B T for MHz modes, so weights nearly uniform
        # But at very low T_eff, ordering should be clear
        w_cold = _boltzmann_weights(freqs, 0.001)
        # First mode should dominate
        assert w_cold[0] > w_cold[-1]

    def test_boltzmann_weights_high_T_approx_uniform(self):
        """At very high T, all weights ≈ 1/N."""
        freqs = _acoustic_frequencies(5)
        w = _boltzmann_weights(freqs, 1e10)
        expected = np.ones(5) / 5
        np.testing.assert_allclose(w, expected, atol=1e-6)

    def test_boltzmann_weights_single_mode(self):
        w = _boltzmann_weights(np.array([1e7]), 300.0)
        np.testing.assert_allclose(w, [1.0], rtol=1e-10)

    # --- _partition_function ---

    def test_partition_function_positive(self):
        freqs = _acoustic_frequencies(10)
        Z = _partition_function(freqs, 300.0)
        assert Z > 0

    def test_partition_function_high_T_equals_N(self):
        """At very high T, Z → N (all Boltzmann factors → 1)."""
        freqs = _acoustic_frequencies(5)
        Z = _partition_function(freqs, 1e10)
        np.testing.assert_allclose(Z, 5.0, rtol=1e-4)

    def test_partition_function_single_mode(self):
        Z = _partition_function(np.array([1e7]), 300.0)
        assert Z > 0

    # --- _r_squared ---

    def test_r_squared_perfect(self):
        y = np.array([1, 2, 3, 4, 5], dtype=float)
        assert _r_squared(y, y) == 1.0

    def test_r_squared_mean_prediction(self):
        y = np.array([1, 2, 3, 4, 5], dtype=float)
        y_pred = np.full(5, np.mean(y))
        np.testing.assert_allclose(_r_squared(y, y_pred), 0.0, atol=1e-10)

    def test_r_squared_negative_for_bad_fit(self):
        y = np.array([1, 2, 3, 4, 5], dtype=float)
        y_pred = np.array([5, 4, 3, 2, 1], dtype=float)
        assert _r_squared(y, y_pred) < 0

    def test_r_squared_constant_true(self):
        y = np.array([3.0, 3.0, 3.0])
        y_pred = np.array([3.0, 3.0, 3.0])
        assert _r_squared(y, y_pred) == 1.0

    # --- _mode_coupling_matrix ---

    def test_coupling_matrix_shape(self):
        freqs = _acoustic_frequencies(5)
        C = _mode_coupling_matrix(5, 1e-6, freqs)
        assert C.shape == (5, 5)

    def test_coupling_matrix_zero_diagonal(self):
        freqs = _acoustic_frequencies(5)
        C = _mode_coupling_matrix(5, 1e-6, freqs)
        np.testing.assert_allclose(np.diag(C), 0.0, atol=1e-15)

    def test_coupling_matrix_nonneg(self):
        freqs = _acoustic_frequencies(5)
        C = _mode_coupling_matrix(5, 1e-6, freqs)
        assert np.all(C >= 0)

    def test_coupling_matrix_symmetric(self):
        freqs = _acoustic_frequencies(5)
        C = _mode_coupling_matrix(5, 1e-6, freqs)
        np.testing.assert_allclose(C, C.T, atol=1e-15)

    def test_coupling_matrix_stronger_for_close_modes(self):
        """Spectrally closer modes should have stronger coupling."""
        freqs = _acoustic_frequencies(5)
        C = _mode_coupling_matrix(5, 1e-6, freqs)
        # Mode 1-2 coupling > Mode 1-5 coupling
        assert C[0, 1] > C[0, 4]

    # --- _snr_at_mode ---

    def test_snr_at_mode_returns_float(self):
        snr = _snr_at_mode(1, 500, 10)
        assert isinstance(snr, float)

    def test_snr_decreases_with_mode_number(self):
        """Higher modes have lower SNR (wider bandwidth → more noise)."""
        snr1 = _snr_at_mode(1, 500, 10)
        snr10 = _snr_at_mode(10, 500, 10)
        assert snr1 > snr10

    def test_snr_increases_with_Q(self):
        """Higher Q → narrower bandwidth → less noise → higher SNR."""
        snr_low = _snr_at_mode(5, 100, 10)
        snr_high = _snr_at_mode(5, 10000, 10)
        assert snr_high > snr_low

    # --- _mode_capacity_bits ---

    def test_capacity_positive_for_good_snr(self):
        assert _mode_capacity_bits(20.0) > 0

    def test_capacity_increases_with_snr(self):
        assert _mode_capacity_bits(30.0) > _mode_capacity_bits(10.0)

    def test_capacity_zero_or_positive(self):
        assert _mode_capacity_bits(-10.0) >= 0

    def test_capacity_shannon_limit(self):
        """At SNR=0 dB (linear=1), b = 0.5·log₂(2) = 0.5."""
        np.testing.assert_allclose(_mode_capacity_bits(0.0), 0.5, rtol=1e-10)

    # --- _golden_positions ---

    def test_golden_positions_count(self):
        assert len(_golden_positions(6)) == 6

    def test_golden_positions_in_range(self):
        pos = _golden_positions(10)
        assert np.all(pos >= 0.02)
        assert np.all(pos <= 0.98)

    # --- _sensitivity_matrix ---

    def test_sensitivity_matrix_shape(self):
        S = _sensitivity_matrix(_golden_positions(4), 20)
        assert S.shape == (20, 4)

    def test_sensitivity_matrix_bounded(self):
        S = _sensitivity_matrix(_golden_positions(5), 10)
        assert np.all(S >= 0)
        assert np.all(S <= 1)


# ═══════════════════════════════════════════════════════════════════════
# Experiment 1 tests: Decade Spacing (H-Bt1)
# ═══════════════════════════════════════════════════════════════════════

class TestDecadeSpacing:
    """Tests for exp_decade_spacing — H-Bt1."""

    def test_returns_result_type(self):
        r = exp_decade_spacing()
        assert isinstance(r, DecadeSpacingResult)

    def test_result_has_all_fields(self):
        r = exp_decade_spacing()
        assert r.n_conditions > 0
        assert len(r.Q_values) == r.n_conditions
        assert len(r.f_values) == r.n_conditions
        assert len(r.t_osc) == r.n_conditions
        assert len(r.tau_ringdown) == r.n_conditions
        assert len(r.t_thermal) == r.n_conditions

    def test_timescale_ordering(self):
        """T_osc < τ < T_th for moderate Q (hierarchy holds)."""
        r = exp_decade_spacing(
            Q_values=np.array([500.0]),
            f_values=np.array([1e7]),
        )
        assert r.t_osc[0] < r.tau_ringdown[0]
        assert r.tau_ringdown[0] < r.t_thermal[0]

    def test_tau_equals_Q_over_pi_f(self):
        Q, f = 500.0, 1e7
        r = exp_decade_spacing(
            Q_values=np.array([Q]),
            f_values=np.array([f]),
        )
        expected = Q / (np.pi * f)
        np.testing.assert_allclose(r.tau_ringdown[0], expected, rtol=1e-10)

    def test_ratio_tau_to_osc_equals_Q_over_pi(self):
        Q = 500.0
        r = exp_decade_spacing(
            Q_values=np.array([Q]),
            f_values=np.array([1e7]),
        )
        expected = Q / np.pi
        np.testing.assert_allclose(r.ratio_tau_to_osc[0], expected, rtol=1e-10)

    def test_decade_fraction_bounded(self):
        r = exp_decade_spacing()
        assert 0.0 <= r.decade_frac_within_3x <= 1.0

    def test_verdict_is_bool(self):
        r = exp_decade_spacing()
        assert isinstance(r.verdict, bool)

    def test_custom_threshold(self):
        r = exp_decade_spacing(threshold_fraction=0.0)
        assert r.verdict is True  # trivially passes with 0% threshold

    def test_multiple_Q_values(self):
        Qs = np.array([100, 1000, 10000], dtype=float)
        r = exp_decade_spacing(Q_values=Qs, f_values=np.array([1e7]))
        assert r.n_conditions == 3

    def test_t_osc_is_inverse_frequency(self):
        f = 2e7
        r = exp_decade_spacing(
            Q_values=np.array([500.0]),
            f_values=np.array([f]),
        )
        np.testing.assert_allclose(r.t_osc[0], 1.0 / f, rtol=1e-10)


# ═══════════════════════════════════════════════════════════════════════
# Experiment 2 tests: Spectral Reddening (H-Bt2)
# ═══════════════════════════════════════════════════════════════════════

class TestSpectralReddening:
    """Tests for exp_spectral_reddening — H-Bt2."""

    def test_returns_result_type(self):
        r = exp_spectral_reddening(n_modes=10, n_steps=500)
        assert isinstance(r, SpectralReddeningResult)

    def test_result_has_fields(self):
        r = exp_spectral_reddening(n_modes=10, n_steps=500)
        assert r.n_modes == 10
        assert len(r.final_spectrum) == 10
        assert len(r.mode_frequencies) == 10

    def test_initial_mode_default_is_highest(self):
        r = exp_spectral_reddening(n_modes=10, n_steps=100)
        assert r.initial_mode == 10

    def test_custom_initial_mode(self):
        r = exp_spectral_reddening(n_modes=10, initial_mode=5, n_steps=100)
        assert r.initial_mode == 5

    def test_energy_nonneg(self):
        r = exp_spectral_reddening(n_modes=10, n_steps=500)
        assert np.all(r.final_spectrum >= 0)

    def test_energy_transfer_bounded(self):
        r = exp_spectral_reddening(n_modes=10, n_steps=500)
        assert 0.0 <= r.energy_transferred_frac <= 1.0

    def test_beta_is_finite(self):
        r = exp_spectral_reddening(n_modes=10, n_steps=500)
        assert np.isfinite(r.beta_fit)

    def test_r_squared_bounded(self):
        r = exp_spectral_reddening(n_modes=10, n_steps=500)
        assert r.beta_r_squared <= 1.0

    def test_verdict_is_bool(self):
        r = exp_spectral_reddening(n_modes=10, n_steps=500)
        assert isinstance(r.verdict, bool)

    def test_stronger_coupling_transfers_more(self):
        r_weak = exp_spectral_reddening(n_modes=10, chi=1e-8, n_steps=500)
        r_strong = exp_spectral_reddening(n_modes=10, chi=1e-4, n_steps=500)
        assert r_strong.energy_transferred_frac >= r_weak.energy_transferred_frac


# ═══════════════════════════════════════════════════════════════════════
# Experiment 3 tests: Optimal Readout Window (H-Bt3)
# ═══════════════════════════════════════════════════════════════════════

class TestOptimalReadout:
    """Tests for exp_optimal_readout — H-Bt3."""

    def test_returns_result_type(self):
        r = exp_optimal_readout(n_modes=10, n_time_points=50)
        assert isinstance(r, OptimalReadoutResult)

    def test_tau_formula(self):
        Q, L = 500.0, 1e-5
        f0 = C_FERROFLUID / (2 * L)
        r = exp_optimal_readout(Q=Q, L=L, n_modes=10, n_time_points=50)
        np.testing.assert_allclose(r.tau, Q / (np.pi * f0), rtol=1e-10)

    def test_predicted_t_star_formula(self):
        Q = 500.0
        r = exp_optimal_readout(Q=Q, n_modes=10, n_time_points=50)
        expected = r.tau * np.log(Q / np.pi)
        np.testing.assert_allclose(r.predicted_t_star, expected, rtol=1e-10)

    def test_accuracy_bounded(self):
        r = exp_optimal_readout(n_modes=10, n_time_points=50)
        assert 0.0 <= r.peak_accuracy <= 1.0
        assert 0.0 <= r.early_accuracy <= 1.0
        assert 0.0 <= r.late_accuracy <= 1.0

    def test_accuracy_curve_length(self):
        n_pts = 50
        r = exp_optimal_readout(n_modes=10, n_time_points=n_pts)
        assert len(r.accuracy_curve) == n_pts
        assert len(r.times) == n_pts

    def test_measured_t_star_positive(self):
        r = exp_optimal_readout(n_modes=10, n_time_points=50)
        assert r.measured_t_star > 0

    def test_verdict_is_bool(self):
        r = exp_optimal_readout(n_modes=10, n_time_points=50)
        assert isinstance(r.verdict, bool)

    def test_has_optimum_reflects_accuracy_shape(self):
        """If has_optimum is True, peak should exceed early and late."""
        r = exp_optimal_readout(n_modes=15, n_time_points=100, n_patterns=10)
        if r.has_optimum:
            assert r.peak_accuracy > r.early_accuracy
            assert r.peak_accuracy > r.late_accuracy

    def test_times_increasing(self):
        r = exp_optimal_readout(n_modes=10, n_time_points=50)
        assert np.all(np.diff(r.times) > 0)

    def test_different_seeds(self):
        r1 = exp_optimal_readout(n_modes=10, n_time_points=50, seed=1)
        r2 = exp_optimal_readout(n_modes=10, n_time_points=50, seed=2)
        # Different seeds may produce different measured t*
        # but both should return valid results
        assert isinstance(r1.verdict, bool)
        assert isinstance(r2.verdict, bool)


# ═══════════════════════════════════════════════════════════════════════
# Experiment 4 tests: Partition Function Capacity (H-Bt4)
# ═══════════════════════════════════════════════════════════════════════

class TestPartitionCapacity:
    """Tests for exp_partition_capacity — H-Bt4."""

    def test_returns_result_type(self):
        r = exp_partition_capacity(n_modes=10)
        assert isinstance(r, PartitionCapacityResult)

    def test_weights_sum_to_one(self):
        r = exp_partition_capacity(n_modes=10)
        np.testing.assert_allclose(np.sum(r.boltzmann_weights), 1.0, rtol=1e-10)
        np.testing.assert_allclose(np.sum(r.uniform_weights), 1.0, rtol=1e-10)
        np.testing.assert_allclose(np.sum(r.q_weights), 1.0, rtol=1e-10)

    def test_true_capacity_nonneg(self):
        r = exp_partition_capacity(n_modes=10)
        assert np.all(r.true_capacity >= 0)

    def test_r_squared_bounded(self):
        r = exp_partition_capacity(n_modes=10)
        assert r.r2_boltzmann <= 1.0
        assert r.r2_uniform <= 1.0
        assert r.r2_q_only <= 1.0

    def test_verdict_is_bool(self):
        r = exp_partition_capacity(n_modes=10)
        assert isinstance(r.verdict, bool)

    def test_n_modes_stored(self):
        r = exp_partition_capacity(n_modes=15)
        assert r.n_modes == 15

    def test_T_eff_stored(self):
        r = exp_partition_capacity(T_eff=500.0)
        np.testing.assert_allclose(r.T_eff, 500.0)

    def test_predicted_capacity_nonneg(self):
        r = exp_partition_capacity(n_modes=10)
        assert np.all(r.boltzmann_predicted >= 0)
        assert np.all(r.uniform_predicted >= 0)
        assert np.all(r.q_predicted >= 0)

    def test_uniform_weights_equal(self):
        r = exp_partition_capacity(n_modes=10)
        expected = np.ones(10) / 10
        np.testing.assert_allclose(r.uniform_weights, expected, rtol=1e-10)

    def test_q_weights_favor_low_frequency(self):
        """Q/f weighting should give more weight to lower modes."""
        r = exp_partition_capacity(n_modes=10)
        assert r.q_weights[0] > r.q_weights[-1]

    def test_boltzmann_vs_uniform_r2(self):
        """Boltzmann or Q weighting should beat uniform for non-flat SNR profile."""
        r = exp_partition_capacity(n_modes=20)
        # At least one non-uniform weighting should beat uniform
        assert r.r2_boltzmann > r.r2_uniform or r.r2_q_only > r.r2_uniform


# ═══════════════════════════════════════════════════════════════════════
# Runner tests
# ═══════════════════════════════════════════════════════════════════════

class TestRunner:
    """Tests for run_all_boltzmann."""

    def test_returns_dict(self):
        results = run_all_boltzmann(verbose=False)
        assert isinstance(results, dict)

    def test_has_all_hypotheses(self):
        results = run_all_boltzmann(verbose=False)
        assert "H-Bt1" in results
        assert "H-Bt2" in results
        assert "H-Bt3" in results
        assert "H-Bt4" in results

    def test_correct_result_types(self):
        results = run_all_boltzmann(verbose=False)
        assert isinstance(results["H-Bt1"], DecadeSpacingResult)
        assert isinstance(results["H-Bt2"], SpectralReddeningResult)
        assert isinstance(results["H-Bt3"], OptimalReadoutResult)
        assert isinstance(results["H-Bt4"], PartitionCapacityResult)

    def test_all_have_verdict(self):
        results = run_all_boltzmann(verbose=False)
        for key, r in results.items():
            assert isinstance(r.verdict, bool), f"{key} verdict is not bool"

    def test_verbose_output(self, capsys):
        run_all_boltzmann(verbose=True)
        captured = capsys.readouterr()
        assert "H-Bt1" in captured.out
        assert "H-Bt2" in captured.out
        assert "H-Bt3" in captured.out
        assert "H-Bt4" in captured.out
        assert "S11 SUMMARY" in captured.out

    def test_verbose_false_no_output(self, capsys):
        run_all_boltzmann(verbose=False)
        captured = capsys.readouterr()
        assert captured.out == ""


# ═══════════════════════════════════════════════════════════════════════
# Physics / cross-validation tests
# ═══════════════════════════════════════════════════════════════════════

class TestPhysics:
    """Cross-validation of physical formulas and edge cases."""

    def test_timescale_hierarchy_low_Q(self):
        """At Q=10, τ/T_osc = Q/π ≈ 3.2 (less than a decade)."""
        Q = 10.0
        ratio = Q / np.pi
        assert 3.0 < ratio < 4.0

    def test_timescale_hierarchy_high_Q(self):
        """At Q=1000, τ/T_osc = Q/π ≈ 318 (multiple decades)."""
        Q = 1000.0
        ratio = Q / np.pi
        assert ratio > 100

    def test_boltzmann_weights_at_room_temp_nearly_uniform(self):
        """At 300 K, hf/k_BT << 1 for MHz modes → nearly uniform weights."""
        freqs = _acoustic_frequencies(5, L=1e-5)  # ~70 MHz range
        w = _boltzmann_weights(freqs, 300.0)
        # All weights should be close to 1/5
        np.testing.assert_allclose(w, np.ones(5) / 5, atol=0.01)

    def test_planck_constant_correct(self):
        np.testing.assert_allclose(H_PLANCK, 6.62607015e-34, rtol=1e-8)

    def test_ringdown_realistic_values(self):
        """For Q=500, f=70 MHz: τ ≈ 2.3 µs."""
        Q = 500
        f = 70e6
        tau = _ringdown_time(Q, f)
        assert 1e-6 < tau < 1e-5

    def test_thermal_drift_realistic_values(self):
        """For Q=500, α=0.0022, dT/dt=0.1 K/s: T_th ≈ 9 s."""
        T_th = _thermal_drift_period(500, 1e7, 0.0022, 0.1)
        assert 1.0 < T_th < 100.0

    def test_cascade_no_coupling(self):
        """With chi=0, no energy should transfer."""
        r = exp_spectral_reddening(n_modes=10, chi=0.0, n_steps=100)
        # All energy should remain in initial mode (or decay)
        assert r.n_modes_excited <= 1

    def test_partition_high_T_uniform(self):
        """At very high T_eff, Boltzmann weighting ≈ uniform."""
        r = exp_partition_capacity(n_modes=10, T_eff=1e10)
        # R² of Boltzmann should ≈ R² of uniform
        np.testing.assert_allclose(r.r2_boltzmann, r.r2_uniform, atol=0.05)
