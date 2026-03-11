"""
S5 — Békésy Cochlear Eigenmode Memory: 4 hypotheses (1 confirmed, 3 killed).

Tests for simulations/bekesy_cochlea.py.  This sidebar investigates whether
cochlear parallels (tonotopic taper, log spacing, active Q-boosting, critical-
band windowing) transfer to SEM.  Honest result: only active Q-boosting (H-B3)
survives; the other three are killed by clean physics arguments.
"""

import numpy as np
import pytest

from simulations.bekesy_cochlea import (
    # Experiment functions
    exp_tapered_mode_density,
    exp_log_spacing_recall,
    exp_active_q_boost,
    exp_cochlear_window,
    run_all_bekesy,
    # Result types
    TaperedModeResult,
    LogSpacingRecallResult,
    ActiveQBoostResult,
    CochlearWindowResult,
    # Helpers
    greenwood_frequency,
    tapered_rod_eigenfrequencies,
    _uniform_eigenfrequencies,
    _log_spaced_frequencies,
    _linear_spaced_frequencies,
    _sensitivity_matrix,
    _hopfield_recall,
    _golden_ratio_positions,
    _cochlear_window,
    _compute_windowed_snr,
)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Unit tests for pure helper functions."""

    def test_greenwood_base_high_frequency(self):
        """Base of cochlea (x=0) should give highest frequency."""
        f_base = greenwood_frequency(0.0)
        f_apex = greenwood_frequency(1.0)
        assert f_base > f_apex

    def test_greenwood_apex_low_frequency(self):
        """Apex of cochlea (x=1) should give lowest frequency, near 20 Hz."""
        f = greenwood_frequency(1.0)
        assert 10.0 < f < 100.0

    def test_greenwood_base_near_20khz(self):
        """Base (x=0) should be near 20 kHz for human cochlea."""
        f = greenwood_frequency(0.0)
        assert 15000 < f < 25000

    def test_greenwood_monotonically_decreasing(self):
        """Frequency should decrease monotonically from base to apex."""
        xs = np.linspace(0, 1, 20)
        fs = [greenwood_frequency(x) for x in xs]
        for i in range(len(fs) - 1):
            assert fs[i] > fs[i + 1]

    def test_tapered_rod_uniform_limit(self):
        """When taper_ratio ≈ 1, tapered rod matches uniform rod."""
        L, v, d = 0.15, 5315.0, 6e-3
        n = 100
        f_tapered = tapered_rod_eigenfrequencies(L, v, d, d * 0.9999, n)
        f_uniform = _uniform_eigenfrequencies(L, v, n)
        np.testing.assert_allclose(f_tapered, f_uniform, rtol=1e-3)

    def test_tapered_rod_eigenfrequencies_positive(self):
        """All eigenfrequencies must be positive."""
        f = tapered_rod_eigenfrequencies(0.15, 5315.0, 6e-3, 2.4e-3, 50)
        assert np.all(f > 0)

    def test_tapered_rod_eigenfrequencies_monotonic(self):
        """Eigenfrequencies must increase with mode index."""
        f = tapered_rod_eigenfrequencies(0.15, 5315.0, 6e-3, 2.4e-3, 50)
        assert np.all(np.diff(f) > 0)

    def test_uniform_eigenfrequencies_formula(self):
        """f_n = n * v / (2L) for a uniform rod."""
        L, v = 0.15, 5315.0
        f = _uniform_eigenfrequencies(L, v, 5)
        expected = np.arange(1, 6) * v / (2 * L)
        np.testing.assert_allclose(f, expected)

    def test_log_spaced_frequencies_endpoints(self):
        """Log-spaced must hit exact endpoints."""
        f = _log_spaced_frequencies(100.0, 10000.0, 20)
        assert f[0] == pytest.approx(100.0)
        assert f[-1] == pytest.approx(10000.0)

    def test_log_spaced_frequencies_ratio_constant(self):
        """Adjacent frequency ratios should be constant."""
        f = _log_spaced_frequencies(100.0, 10000.0, 20)
        ratios = f[1:] / f[:-1]
        np.testing.assert_allclose(ratios, ratios[0], rtol=1e-12)

    def test_sensitivity_matrix_shape(self):
        """S should have shape (n_modes, K)."""
        S = _sensitivity_matrix(np.array([0.2, 0.5, 0.8]), 10)
        assert S.shape == (10, 3)

    def test_sensitivity_matrix_non_negative(self):
        """sin²(nπx) is always ≥ 0."""
        S = _sensitivity_matrix(_golden_ratio_positions(8), 30)
        assert np.all(S >= 0)

    def test_sensitivity_matrix_max_one(self):
        """sin²(nπx) ≤ 1."""
        S = _sensitivity_matrix(_golden_ratio_positions(8), 30)
        assert np.all(S <= 1.0 + 1e-15)

    def test_sensitivity_matrix_zero_at_boundary(self):
        """sin²(nπ·0) = 0 and sin²(nπ·1) = 0 for all n."""
        S = _sensitivity_matrix(np.array([0.0, 1.0]), 10)
        np.testing.assert_allclose(S, 0.0, atol=1e-15)

    def test_hopfield_recall_exact_match(self):
        """Perfect match should return overlap ≈ 1."""
        patterns = np.array([[1, 0, 1, 0], [0, 1, 0, 1]], dtype=float)
        idx, overlap, _ = _hopfield_recall(patterns, patterns[0])
        assert idx == 0
        assert overlap == pytest.approx(1.0)

    def test_hopfield_recall_distinguishes_patterns(self):
        """Recall should identify the correct pattern under mild noise."""
        rng = np.random.RandomState(42)
        patterns = rng.randn(5, 20)
        query = patterns[3] + rng.randn(20) * 0.1
        idx, _, _ = _hopfield_recall(patterns, query)
        assert idx == 3

    def test_golden_ratio_positions_in_unit_interval(self):
        """All positions must be in (0, 1)."""
        p = _golden_ratio_positions(16)
        assert np.all(p > 0)
        assert np.all(p < 1)

    def test_golden_ratio_positions_unique(self):
        """All positions must be distinct."""
        p = _golden_ratio_positions(16)
        assert len(np.unique(p)) == 16

    def test_cochlear_window_unit_energy(self):
        """Cochlear window should be normalised to unit energy."""
        w = _cochlear_window(1024)
        assert np.sum(w ** 2) == pytest.approx(1.0, abs=1e-10)

    def test_cochlear_window_positive(self):
        """All window values should be non-negative."""
        w = _cochlear_window(1024)
        assert np.all(w >= 0)

    def test_cochlear_window_length(self):
        """Window length should match input N."""
        w = _cochlear_window(512)
        assert len(w) == 512


# ═══════════════════════════════════════════════════════════════════════
# H-B1 — Tapered Rod Mode Density (KILLED)
# ═══════════════════════════════════════════════════════════════════════

class TestTaperedModeDensity:
    """H-B1: Tapered rod does NOT achieve more resolvable modes than uniform.

    WKB approximation for a 1D standing-wave rod gives f_n = n × constant
    regardless of taper profile.  The taper shifts all frequencies by the
    same multiplicative factor, preserving the gap/linewidth ratio.  Result:
    identical resolvable mode count.  This is an honest negative result —
    cochlear tonotopy arises from traveling-wave physics (basilar membrane
    stiffness gradient), not from geometric taper of a standing-wave cavity.
    """

    def test_runs_without_error(self):
        r = exp_tapered_mode_density()
        assert isinstance(r, TaperedModeResult)

    def test_uniform_n_max_paper_value(self):
        """n_max = 9380 with default parameters (§2.1)."""
        r = exp_tapered_mode_density()
        assert r.uniform_n_max == 9380

    def test_mode_counts_equal(self):
        """Tapered and uniform yield the same resolvable mode count."""
        r = exp_tapered_mode_density()
        assert r.tapered_mode_count == r.uniform_mode_count

    def test_frequencies_all_positive(self):
        r = exp_tapered_mode_density()
        assert np.all(r.uniform_frequencies > 0)
        assert np.all(r.tapered_frequencies > 0)

    def test_tapered_frequencies_monotonic(self):
        r = exp_tapered_mode_density()
        assert np.all(np.diff(r.tapered_frequencies) > 0)

    def test_taper_ratio_stored(self):
        r = exp_tapered_mode_density(taper_ratio=0.3)
        assert r.taper_ratio == pytest.approx(0.3)

    def test_density_improvement_positive(self):
        """Mode density (modes/bandwidth) is higher for tapered rod."""
        r = exp_tapered_mode_density()
        assert r.density_improvement_pct > 0

    def test_stronger_taper_higher_density(self):
        """Stronger taper compresses bandwidth more → higher density."""
        r_mild = exp_tapered_mode_density(taper_ratio=0.7)
        r_strong = exp_tapered_mode_density(taper_ratio=0.3)
        assert r_strong.density_improvement_pct > r_mild.density_improvement_pct

    def test_higher_Q_more_modes(self):
        """Higher Q → more resolvable modes (narrower linewidths)."""
        r_low = exp_tapered_mode_density(Q=5000.0)
        r_high = exp_tapered_mode_density(Q=50000.0)
        assert r_high.uniform_mode_count > r_low.uniform_mode_count

    def test_verdict_killed(self):
        """H-B1 is KILLED: taper does not increase mode count."""
        r = exp_tapered_mode_density()
        assert r.verdict is False


# ═══════════════════════════════════════════════════════════════════════
# H-B2 — Log-Spaced Mode Recall (KILLED)
# ═══════════════════════════════════════════════════════════════════════

class TestLogSpacingRecall:
    """H-B2: Log spacing does NOT systematically improve recall accuracy.

    Under the tested regime (30 modes, 8 sites, 10 patterns, moderate noise),
    both linear and log spacing achieve perfect recall.  Under extreme stress
    (40+ patterns, high noise), the advantage is inconsistent — sometimes
    linear wins, sometimes log.  This kills the hypothesis that cochlear
    log mapping transfers to SEM's associative recall.
    """

    def test_runs_without_error(self):
        r = exp_log_spacing_recall(rng=np.random.RandomState(42))
        assert isinstance(r, LogSpacingRecallResult)

    def test_linear_accuracy_high(self):
        """Both spacings should achieve high accuracy at default difficulty."""
        r = exp_log_spacing_recall(rng=np.random.RandomState(42))
        assert r.linear_accuracy >= 0.95

    def test_log_accuracy_high(self):
        r = exp_log_spacing_recall(rng=np.random.RandomState(42))
        assert r.log_accuracy >= 0.95

    def test_both_accuracies_equal(self):
        """At default difficulty, both achieve 100% — no advantage."""
        r = exp_log_spacing_recall(rng=np.random.RandomState(42))
        assert r.linear_accuracy == r.log_accuracy

    def test_margin_values_positive(self):
        r = exp_log_spacing_recall(rng=np.random.RandomState(42))
        assert r.linear_mean_margin > 0
        assert r.log_mean_margin > 0

    def test_n_modes_and_patterns_stored(self):
        r = exp_log_spacing_recall(n_modes=20, n_stored=5,
                                   rng=np.random.RandomState(42))
        assert r.n_modes == 20
        assert r.n_patterns_stored == 5

    def test_noise_sigma_stored(self):
        r = exp_log_spacing_recall(noise_sigma=0.25,
                                   rng=np.random.RandomState(42))
        assert r.noise_sigma == pytest.approx(0.25)

    def test_reproducible_with_seed(self):
        r1 = exp_log_spacing_recall(rng=np.random.RandomState(77))
        r2 = exp_log_spacing_recall(rng=np.random.RandomState(77))
        assert r1.linear_accuracy == r2.linear_accuracy
        assert r1.log_accuracy == r2.log_accuracy
        assert r1.linear_mean_margin == pytest.approx(r2.linear_mean_margin)

    def test_verdict_killed(self):
        """H-B2 is KILLED: log spacing provides no accuracy advantage."""
        r = exp_log_spacing_recall(rng=np.random.RandomState(42))
        assert r.verdict is False


# ═══════════════════════════════════════════════════════════════════════
# H-B3 — Active Q-Boosting (CONFIRMED)
# ═══════════════════════════════════════════════════════════════════════

class TestActiveQBoost:
    """H-B3: Active feedback raises effective Q above passive limit.

    The cochlear outer hair cell analogy maps cleanly onto SEM: a feedback
    circuit senses mode amplitude and injects compensating energy.  The
    power budget is femtowatts per mode (thermal equilibrium energy k_B·T
    per mode × ω × loss differential).  2× Q boost confirmed.
    """

    def test_runs_without_error(self):
        r = exp_active_q_boost()
        assert isinstance(r, ActiveQBoostResult)

    def test_passive_q_five_mechanism(self):
        """5-mechanism Q should combine as 1/Q = Σ(1/Q_i)."""
        r = exp_active_q_boost()
        Q_inv = 1/10000 + 1/50000 + 1/200000 + 1/100000 + 1/500000
        assert r.Q_passive == pytest.approx(1.0 / Q_inv, rel=1e-6)

    def test_boost_ratio_matches_multiplier(self):
        """boost_ratio should equal Q_target_multiplier."""
        r = exp_active_q_boost(Q_target_multiplier=3.0)
        assert r.boost_ratio == pytest.approx(3.0)

    def test_boost_ratio_above_threshold(self):
        """Default 2× boost exceeds 1.5× kill threshold."""
        r = exp_active_q_boost()
        assert r.boost_ratio >= 1.5

    def test_power_per_mode_femtowatts(self):
        """Drive power should be sub-femtowatt per mode at room temperature."""
        r = exp_active_q_boost()
        assert 0 < r.drive_power_per_mode_fW < 1.0

    def test_total_power_scales_with_modes(self):
        """Total power = power_per_mode × n_modes."""
        r = exp_active_q_boost(n_modes_to_boost=100)
        assert r.total_power_n_modes_fW == pytest.approx(
            r.drive_power_per_mode_fW * 100)

    def test_n_max_boosted_exceeds_passive(self):
        """More modes with higher Q."""
        r = exp_active_q_boost()
        assert r.n_max_boosted > r.n_max_passive

    def test_mode_gain_positive(self):
        r = exp_active_q_boost()
        assert r.mode_gain_from_boost > 0

    def test_n_max_passive_paper_value(self):
        """Passive n_max should be ~6963 with default 5-mechanism Q."""
        r = exp_active_q_boost()
        assert 6000 < r.n_max_passive < 8000

    def test_higher_multiplier_more_modes(self):
        r_2x = exp_active_q_boost(Q_target_multiplier=2.0)
        r_5x = exp_active_q_boost(Q_target_multiplier=5.0)
        assert r_5x.n_max_boosted > r_2x.n_max_boosted

    def test_higher_multiplier_more_power(self):
        r_2x = exp_active_q_boost(Q_target_multiplier=2.0)
        r_5x = exp_active_q_boost(Q_target_multiplier=5.0)
        assert r_5x.drive_power_per_mode_fW > r_2x.drive_power_per_mode_fW

    def test_q_effective_equals_target(self):
        """Active feedback achieves target Q by construction."""
        r = exp_active_q_boost()
        assert r.Q_effective == pytest.approx(r.Q_target)

    def test_verdict_confirmed(self):
        """H-B3 is CONFIRMED: active Q-boosting works."""
        r = exp_active_q_boost()
        assert r.verdict is True


# ═══════════════════════════════════════════════════════════════════════
# H-B4 — Cochlear-Inspired FFT Window (KILLED)
# ═══════════════════════════════════════════════════════════════════════

class TestCochlearWindow:
    """H-B4: Cochlear window does NOT beat rectangular for SEM readout SNR.

    The rectangular window preserves all signal energy (no tapering),
    which is optimal for SNR when spectral leakage between modes is not
    the dominant error source.  The cochlear window trades SNR for sidelobe
    suppression — a trade-off that only helps when modes are densely packed
    near the resolution limit, which SEM's well-separated modes are not.
    """

    def test_runs_without_error(self):
        r = exp_cochlear_window(rng=np.random.RandomState(42))
        assert isinstance(r, CochlearWindowResult)

    def test_all_snr_positive(self):
        r = exp_cochlear_window(rng=np.random.RandomState(42))
        assert r.snr_rectangular_dB > 0
        assert r.snr_cochlear_dB > 0
        assert r.snr_hann_dB > 0

    def test_rectangular_beats_cochlear(self):
        """Rectangular window has higher SNR — no tapering loss."""
        r = exp_cochlear_window(rng=np.random.RandomState(42))
        assert r.snr_rectangular_dB > r.snr_cochlear_dB

    def test_cochlear_beats_hann(self):
        """Cochlear window should outperform Hann (milder taper)."""
        r = exp_cochlear_window(rng=np.random.RandomState(42))
        assert r.snr_cochlear_dB > r.snr_hann_dB

    def test_gain_vs_rect_negative(self):
        """SNR gain vs rectangular should be negative."""
        r = exp_cochlear_window(rng=np.random.RandomState(42))
        assert r.snr_gain_vs_rect_dB < 0

    def test_gain_vs_hann_positive(self):
        """SNR gain vs Hann should be positive."""
        r = exp_cochlear_window(rng=np.random.RandomState(42))
        assert r.snr_gain_vs_hann_dB > 0

    def test_snr_gain_below_1dB(self):
        """Gain vs rectangular < 1 dB → kills the hypothesis."""
        r = exp_cochlear_window(rng=np.random.RandomState(42))
        assert r.snr_gain_vs_rect_dB < 1.0

    def test_n_modes_stored(self):
        r = exp_cochlear_window(n_modes=15, rng=np.random.RandomState(42))
        assert r.n_modes == 15

    def test_reproducible_with_seed(self):
        r1 = exp_cochlear_window(rng=np.random.RandomState(77))
        r2 = exp_cochlear_window(rng=np.random.RandomState(77))
        assert r1.snr_cochlear_dB == pytest.approx(r2.snr_cochlear_dB)
        assert r1.snr_rectangular_dB == pytest.approx(r2.snr_rectangular_dB)

    def test_verdict_killed(self):
        """H-B4 is KILLED: cochlear window does not beat rectangular."""
        r = exp_cochlear_window(rng=np.random.RandomState(42))
        assert r.verdict is False


# ═══════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════

class TestRunAllBekesy:
    """Integration tests for the run_all_bekesy orchestrator."""

    def test_returns_four_results(self):
        results = run_all_bekesy(verbose=False)
        assert len(results) == 4

    def test_keys_present(self):
        results = run_all_bekesy(verbose=False)
        assert "H-B1" in results
        assert "H-B2" in results
        assert "H-B3" in results
        assert "H-B4" in results

    def test_result_types(self):
        results = run_all_bekesy(verbose=False)
        assert isinstance(results["H-B1"], TaperedModeResult)
        assert isinstance(results["H-B2"], LogSpacingRecallResult)
        assert isinstance(results["H-B3"], ActiveQBoostResult)
        assert isinstance(results["H-B4"], CochlearWindowResult)

    def test_one_of_four_confirmed(self):
        """Only H-B3 should be confirmed; H-B1, H-B2, H-B4 are killed."""
        results = run_all_bekesy(verbose=False)
        assert results["H-B1"].verdict is False, "H-B1 should be killed"
        assert results["H-B2"].verdict is False, "H-B2 should be killed"
        assert results["H-B3"].verdict is True, "H-B3 should be confirmed"
        assert results["H-B4"].verdict is False, "H-B4 should be killed"

    def test_verbose_mode_runs(self):
        results = run_all_bekesy(verbose=True)
        assert len(results) == 4
