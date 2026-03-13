"""Tests for simulations/shannon_capacity.py (Sidebar 15)."""

import numpy as np
import pytest

from simulations.shannon_capacity import (
    # Constants
    _L_DEFAULT,
    _N_MODES_DEFAULT,
    _Q_DEFAULT,
    _T_DEFAULT,
    _BW_DEFAULT,
    _TOTAL_POWER,
    # Helpers
    _snr_profile_db,
    _snr_profile_linear,
    _mode_dependent_snr,
    _waterfilling,
    _capacity_with_powers,
    _capacity_uniform,
    _mutual_info_per_mode,
    _reconstruction_error,
    # Dataclasses
    WaterfillingResult,
    NyquistMinimumResult,
    CapacityUtilisationResult,
    MutualInfoResult,
    ShannonCapacitySummary,
    # Experiments
    exp_waterfilling_gain,
    exp_nyquist_minimum,
    exp_capacity_utilisation,
    exp_mutual_info,
    run_all_shannon,
)
from simulations.noise_decoherence import NoiseParams


# =========================================================================
# Helper functions
# =========================================================================


class TestSNRProfile:
    """Tests for SNR profile helper functions."""

    def test_snr_profile_db_returns_array(self):
        p = NoiseParams()
        result = _snr_profile_db(5, p)
        assert isinstance(result, np.ndarray)
        assert len(result) == 5

    def test_snr_profile_linear_nonneg(self):
        p = NoiseParams()
        result = _snr_profile_linear(5, p)
        assert np.all(result >= 0)

    def test_snr_profile_linear_length(self):
        p = NoiseParams()
        result = _snr_profile_linear(10, p)
        assert len(result) == 10

    def test_mode_dependent_snr_shape(self):
        snr = _mode_dependent_snr(20, 1000.0, 1.0)
        assert snr.shape == (20,)

    def test_mode_dependent_snr_first_mode(self):
        snr = _mode_dependent_snr(10, 500.0, 1.0)
        assert snr[0] == pytest.approx(500.0)

    def test_mode_dependent_snr_decreasing(self):
        snr = _mode_dependent_snr(10, 1000.0, 1.0)
        assert np.all(np.diff(snr) < 0)

    def test_mode_dependent_snr_alpha_zero_flat(self):
        snr = _mode_dependent_snr(10, 100.0, 0.0)
        assert np.allclose(snr, 100.0)

    def test_mode_dependent_snr_alpha_two(self):
        snr = _mode_dependent_snr(5, 400.0, 2.0)
        assert snr[1] == pytest.approx(400.0 / 4.0)  # n=2, n^2=4
        assert snr[3] == pytest.approx(400.0 / 16.0)  # n=4, n^2=16

    def test_mode_dependent_snr_positive(self):
        snr = _mode_dependent_snr(50, 100.0, 1.5)
        assert np.all(snr > 0)


class TestWaterfilling:
    """Tests for waterfilling algorithm."""

    def test_uniform_noise_gives_uniform_power(self):
        noise = np.array([1.0, 1.0, 1.0, 1.0])
        powers = _waterfilling(noise, 4.0)
        assert np.allclose(powers, 1.0)

    def test_total_power_conserved(self):
        noise = np.array([0.5, 1.0, 2.0, 5.0])
        total = 3.0
        powers = _waterfilling(noise, total)
        assert np.sum(powers) == pytest.approx(total, rel=1e-10)

    def test_nonneg_allocation(self):
        noise = np.array([0.1, 1.0, 10.0, 100.0])
        powers = _waterfilling(noise, 1.0)
        assert np.all(powers >= 0)

    def test_high_noise_channels_cutoff(self):
        noise = np.array([0.01, 0.01, 100.0, 100.0])
        powers = _waterfilling(noise, 1.0)
        # High-noise channels should get zero or near-zero
        assert powers[2] < 0.01
        assert powers[3] < 0.01

    def test_waterfilling_beats_uniform(self):
        noise = np.array([0.1, 0.5, 1.0, 5.0, 10.0])
        snr = 1.0 / noise
        total = 5.0
        powers_wf = _waterfilling(noise, total)
        cap_wf = _capacity_with_powers(snr, powers_wf)
        cap_uni = _capacity_uniform(snr, total)
        assert cap_wf >= cap_uni - 1e-10

    def test_single_channel(self):
        noise = np.array([2.0])
        powers = _waterfilling(noise, 5.0)
        assert powers[0] == pytest.approx(5.0)

    def test_all_power_to_best_channel(self):
        # Very high noise on all but one → all power to good channel
        noise = np.array([0.01, 1e6, 1e6])
        powers = _waterfilling(noise, 0.1)
        assert powers[0] > 0.09
        assert powers[1] == pytest.approx(0.0, abs=1e-6)


class TestCapacity:
    """Tests for capacity computation helpers."""

    def test_capacity_with_powers_zero_snr(self):
        snr = np.array([0.0, 0.0])
        powers = np.array([1.0, 1.0])
        assert _capacity_with_powers(snr, powers) == 0.0

    def test_capacity_with_powers_positive(self):
        snr = np.array([100.0, 50.0])
        powers = np.array([1.0, 1.0])
        assert _capacity_with_powers(snr, powers) > 0

    def test_capacity_uniform_matches_manual(self):
        snr = np.array([10.0, 10.0])
        total = 2.0
        expected = 2 * 0.5 * np.log2(1 + 1.0 * 10.0)
        assert _capacity_uniform(snr, total) == pytest.approx(expected)

    def test_capacity_monotonic_in_snr(self):
        snr_low = np.array([10.0, 10.0])
        snr_high = np.array([100.0, 100.0])
        assert _capacity_uniform(snr_high, 1.0) > _capacity_uniform(snr_low, 1.0)

    def test_capacity_monotonic_in_power(self):
        snr = np.array([10.0, 10.0])
        assert _capacity_uniform(snr, 2.0) > _capacity_uniform(snr, 1.0)


class TestMutualInfo:
    """Tests for mutual information computation."""

    def test_mi_zero_snr(self):
        mi = _mutual_info_per_mode(np.array([0.0]))
        assert mi[0] == pytest.approx(0.0)

    def test_mi_known_value(self):
        # SNR = 1 → I = 0.5 * log2(2) = 0.5
        mi = _mutual_info_per_mode(np.array([1.0]))
        assert mi[0] == pytest.approx(0.5)

    def test_mi_high_snr(self):
        # SNR = 1023 → I = 0.5 * log2(1024) = 5.0
        mi = _mutual_info_per_mode(np.array([1023.0]))
        assert mi[0] == pytest.approx(5.0)

    def test_mi_array_shape(self):
        mi = _mutual_info_per_mode(np.array([1.0, 10.0, 100.0]))
        assert mi.shape == (3,)

    def test_mi_monotonic(self):
        snr = np.array([10.0, 5.0, 1.0, 0.5])
        mi = _mutual_info_per_mode(snr)
        assert np.all(np.diff(mi) <= 0)


class TestReconstruction:
    """Tests for reconstruction error."""

    def test_more_modes_reduces_error(self):
        snr = _mode_dependent_snr(40, 100.0, 1.0)
        err5 = _reconstruction_error(5, 5, snr)
        err10 = _reconstruction_error(5, 10, snr)
        assert err10 < err5

    def test_infinite_snr_k_modes(self):
        # At infinite SNR with K modes, still have aliasing from modes > K
        snr = np.full(40, 1e10)
        err_K = _reconstruction_error(5, 5, snr)
        err_2K = _reconstruction_error(5, 10, snr)
        assert err_2K < err_K

    def test_zero_snr_high_error(self):
        snr = np.full(20, 0.01)
        err = _reconstruction_error(3, 6, snr)
        assert err > 0

    def test_error_nonneg(self):
        snr = _mode_dependent_snr(30, 500.0, 1.0)
        assert _reconstruction_error(4, 8, snr) >= 0

    def test_all_modes_measured(self):
        snr = np.full(20, 1000.0)
        # Measure all 20 modes for K=5 → no aliasing
        err = _reconstruction_error(5, 20, snr)
        assert err < 0.001


# =========================================================================
# Experiment functions
# =========================================================================


class TestWaterfillingGain:
    """Tests for exp_waterfilling_gain (H-SN1)."""

    def test_returns_correct_type(self):
        r = exp_waterfilling_gain()
        assert isinstance(r, WaterfillingResult)

    def test_gain_nonneg(self):
        r = exp_waterfilling_gain()
        assert r.gain_percent >= 0

    def test_waterfill_geq_uniform(self):
        r = exp_waterfilling_gain()
        assert r.capacity_waterfill >= r.capacity_uniform - 1e-10

    def test_verdict_is_bool(self):
        r = exp_waterfilling_gain()
        assert isinstance(r.verdict, bool)

    def test_high_alpha_larger_gain(self):
        r_low = exp_waterfilling_gain(alpha=0.5)
        r_high = exp_waterfilling_gain(alpha=2.0)
        assert r_high.gain_percent > r_low.gain_percent

    def test_flat_snr_minimal_gain(self):
        r = exp_waterfilling_gain(alpha=0.0)
        # Flat SNR → no gain from waterfilling
        assert r.gain_percent < 0.01

    def test_cutoff_count_in_range(self):
        r = exp_waterfilling_gain()
        assert 0 <= r.n_cutoff <= r.n_modes

    def test_n_modes_stored(self):
        r = exp_waterfilling_gain(n_modes=15)
        assert r.n_modes == 15


class TestNyquistMinimum:
    """Tests for exp_nyquist_minimum (H-SN2)."""

    def test_returns_correct_type(self):
        r = exp_nyquist_minimum()
        assert isinstance(r, NyquistMinimumResult)

    def test_error_2k_less_than_k(self):
        r = exp_nyquist_minimum()
        assert r.error_2K < r.error_K

    def test_error_ratio_greater_than_one(self):
        r = exp_nyquist_minimum()
        assert r.error_ratio > 1.0

    def test_verdict_is_bool(self):
        r = exp_nyquist_minimum()
        assert isinstance(r.verdict, bool)

    def test_high_snr_k_may_suffice(self):
        # Even at very high SNR, aliasing from unmeasured modes K+1..2K
        # means K modes alone have higher error than 2K modes.
        r = exp_nyquist_minimum(snr_base=1e8, alpha=0.0)
        # 2K should still be much better
        assert r.error_2K < r.error_K

    def test_k_stored(self):
        r = exp_nyquist_minimum(K=7)
        assert r.K == 7

    def test_errors_positive(self):
        r = exp_nyquist_minimum()
        assert r.error_K >= 0
        assert r.error_2K >= 0


class TestCapacityUtilisation:
    """Tests for exp_capacity_utilisation (H-SN3)."""

    def test_returns_correct_type(self):
        r = exp_capacity_utilisation()
        assert isinstance(r, CapacityUtilisationResult)

    def test_utilisation_leq_one(self):
        r = exp_capacity_utilisation()
        assert r.utilisation <= 1.0 + 1e-10

    def test_utilisation_positive(self):
        r = exp_capacity_utilisation()
        assert r.utilisation > 0

    def test_verdict_is_bool(self):
        r = exp_capacity_utilisation()
        assert isinstance(r.verdict, bool)

    def test_flat_snr_perfect_utilisation(self):
        r = exp_capacity_utilisation(alpha=0.0)
        assert r.utilisation > 0.999

    def test_n_modes_stored(self):
        r = exp_capacity_utilisation(n_modes=25)
        assert r.n_modes == 25


class TestMutualInfoExperiment:
    """Tests for exp_mutual_info (H-SN4)."""

    def test_returns_correct_type(self):
        r = exp_mutual_info()
        assert isinstance(r, MutualInfoResult)

    def test_mi_array_length(self):
        r = exp_mutual_info(n_modes=15)
        assert len(r.mi_per_mode) == 15

    def test_mi_nonneg(self):
        r = exp_mutual_info()
        assert np.all(r.mi_per_mode >= 0)

    def test_n_max_nonneg(self):
        r = exp_mutual_info()
        assert r.n_max >= 0

    def test_verdict_is_bool(self):
        r = exp_mutual_info()
        assert isinstance(r.verdict, bool)

    def test_high_signal_increases_mi(self):
        p_low = NoiseParams(A_signal=0.1)
        p_high = NoiseParams(A_signal=10.0)
        r_low = exp_mutual_info(params=p_low)
        r_high = exp_mutual_info(params=p_high)
        assert r_high.mi_low_half_mean >= r_low.mi_low_half_mean


# =========================================================================
# Runner / Integration
# =========================================================================


class TestRunner:
    """Tests for run_all_shannon."""

    def test_returns_summary(self):
        s = run_all_shannon(verbose=False)
        assert isinstance(s, ShannonCapacitySummary)

    def test_counts_add_up(self):
        s = run_all_shannon(verbose=False)
        assert s.confirmed + s.killed == 4

    def test_all_sub_results_present(self):
        s = run_all_shannon(verbose=False)
        assert isinstance(s.waterfilling, WaterfillingResult)
        assert isinstance(s.nyquist, NyquistMinimumResult)
        assert isinstance(s.utilisation, CapacityUtilisationResult)
        assert isinstance(s.mutual_info, MutualInfoResult)

    def test_verbose_runs(self, capsys):
        run_all_shannon(verbose=True)
        captured = capsys.readouterr()
        assert "Shannon" in captured.out
        assert "H-SN1" in captured.out


class TestPhysics:
    """Cross-checks on physical consistency."""

    def test_shannon_formula(self):
        # Single mode: I = 0.5 * log2(1 + SNR)
        snr = 100.0
        mi = _mutual_info_per_mode(np.array([snr]))
        expected = 0.5 * np.log2(1 + snr)
        assert mi[0] == pytest.approx(expected)

    def test_waterfilling_is_optimal(self):
        # Waterfilling should always beat or match uniform
        for alpha in [0.0, 0.5, 1.0, 1.5, 2.0]:
            r = exp_waterfilling_gain(alpha=alpha)
            assert r.capacity_waterfill >= r.capacity_uniform - 1e-10

    def test_nyquist_consistent_with_sampling_theory(self):
        # 2K modes should always give lower error than K modes
        for K in [3, 5, 8]:
            r = exp_nyquist_minimum(K=K)
            assert r.error_2K < r.error_K

    def test_utilisation_inverse_of_gain(self):
        r_wf = exp_waterfilling_gain()
        r_ut = exp_capacity_utilisation()
        # Both use same defaults — utilisation ≈ 1/(1+gain)
        expected_util = 1.0 / (1.0 + r_wf.gain_percent / 100.0)
        assert r_ut.utilisation == pytest.approx(expected_util, rel=0.01)


class TestEdgeCases:
    """Edge-case parameter sweeps."""

    def test_single_mode(self):
        r = exp_waterfilling_gain(n_modes=1)
        assert r.gain_percent == pytest.approx(0.0, abs=1e-6)

    def test_many_modes(self):
        r = exp_waterfilling_gain(n_modes=100)
        assert r.capacity_waterfill > 0

    def test_very_low_snr_base(self):
        r = exp_waterfilling_gain(snr_base=0.1)
        assert r.capacity_uniform >= 0

    def test_very_high_snr_base(self):
        r = exp_waterfilling_gain(snr_base=1e6)
        assert r.capacity_uniform > 0

    def test_nyquist_k_one(self):
        r = exp_nyquist_minimum(K=1)
        assert r.error_2K <= r.error_K

    def test_nyquist_large_k(self):
        r = exp_nyquist_minimum(K=15, n_modes=60)
        assert isinstance(r.verdict, bool)
