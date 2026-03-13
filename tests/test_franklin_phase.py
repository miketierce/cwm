"""
Tests for S6 — Franklin phase-retrieval experiments.

Covers all four hypotheses (H-F1 through H-F4) with helper tests,
experiment-level tests, and integration tests.  All four hypotheses
are expected to be KILLED: crystallographic phase-retrieval algorithms
do not transfer directly to CWM's sin²(nπx) encoding because it is
fundamentally different from Fourier-based diffraction.

Test count target: ≥ 40 tests.
"""

import numpy as np
import pytest

from simulations.franklin_phase import (
    # Helpers
    _golden_positions,
    _sensitivity_matrix,
    _phase_sensitivity_matrix,
    _complex_fingerprint,
    _tangent_formula_phases,
    _patterson_map,
    _find_patterson_peaks,
    _gerchberg_saxton,
    # Experiments
    exp_direct_methods,
    exp_patterson_function,
    exp_gerchberg_saxton,
    exp_molecular_replacement,
    # Result types
    DirectMethodResult,
    PattersonResult,
    GerchbergSaxtonResult,
    MolecularReplacementResult,
    # Run all
    run_all_franklin,
)


# ═══════════════════════════════════════════════════════════════════════
# Helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Tests for helper functions."""

    def test_golden_positions_count(self):
        pos = _golden_positions(8)
        assert len(pos) == 8

    def test_golden_positions_in_range(self):
        pos = _golden_positions(12)
        assert np.all(pos >= 0.02)
        assert np.all(pos <= 0.98)

    def test_golden_positions_unique(self):
        pos = _golden_positions(10)
        # All positions distinct
        diffs = np.diff(np.sort(pos))
        assert np.all(diffs > 0.01)

    def test_golden_positions_low_discrepancy(self):
        """Golden-ratio positions should fill the interval fairly evenly."""
        pos = _golden_positions(20)
        sorted_pos = np.sort(pos)
        gaps = np.diff(sorted_pos)
        assert np.max(gaps) < 0.15  # no huge gap

    def test_sensitivity_matrix_shape(self):
        S = _sensitivity_matrix(np.array([0.25, 0.5, 0.75]), n_modes=10)
        assert S.shape == (10, 3)

    def test_sensitivity_matrix_range(self):
        S = _sensitivity_matrix(_golden_positions(5), n_modes=20)
        assert np.all(S >= 0)
        assert np.all(S <= 1)

    def test_sensitivity_sin_squared(self):
        """S[n,k] = sin²(nπx_k) at known positions."""
        x = np.array([0.5])
        S = _sensitivity_matrix(x, n_modes=3)
        # sin²(1π·0.5) = sin²(π/2) = 1
        assert abs(S[0, 0] - 1.0) < 1e-10
        # sin²(2π·0.5) = sin²(π) = 0
        assert abs(S[1, 0] - 0.0) < 1e-10
        # sin²(3π·0.5) = sin²(3π/2) = 1
        assert abs(S[2, 0] - 1.0) < 1e-10

    def test_phase_sensitivity_matrix_shape(self):
        P = _phase_sensitivity_matrix(np.array([0.3, 0.6]), n_modes=15)
        assert P.shape == (15, 2)

    def test_phase_sensitivity_range(self):
        P = _phase_sensitivity_matrix(_golden_positions(8), n_modes=20)
        assert np.all(P >= -1)
        assert np.all(P <= 1)

    def test_phase_sensitivity_sin2(self):
        """P[n,k] = sin(2nπx_k) at x=0.25."""
        x = np.array([0.25])
        P = _phase_sensitivity_matrix(x, n_modes=2)
        # sin(2·1·π·0.25) = sin(π/2) = 1
        assert abs(P[0, 0] - 1.0) < 1e-10
        # sin(2·2·π·0.25) = sin(π) = 0
        assert abs(P[1, 0]) < 1e-10

    def test_sensitivity_orthogonality(self):
        """sin²(nπx) and sin(2nπx) are orthogonal over [0,1]."""
        from scipy.integrate import quad
        for n in [1, 3, 5]:
            val, _ = quad(lambda x: np.sin(n*np.pi*x)**2 * np.sin(2*n*np.pi*x),
                          0, 1)
            assert abs(val) < 1e-12

    def test_complex_fingerprint_dtype(self):
        S_f = _sensitivity_matrix(_golden_positions(4), 10)
        S_p = _phase_sensitivity_matrix(_golden_positions(4), 10)
        pattern = np.array([1.0, 0.0, 2.0, 1.0])
        fp = _complex_fingerprint(S_f, S_p, pattern)
        assert fp.dtype == np.complex128

    def test_complex_fingerprint_length(self):
        S_f = _sensitivity_matrix(_golden_positions(4), 10)
        S_p = _phase_sensitivity_matrix(_golden_positions(4), 10)
        fp = _complex_fingerprint(S_f, S_p, np.ones(4))
        assert len(fp) == 10

    def test_tangent_formula_returns_phases(self):
        amps = np.array([1.0, 2.0, 0.5, 1.5, 3.0])
        phases = _tangent_formula_phases(amps, n_iter=10)
        assert len(phases) == 5
        assert np.all(np.isfinite(phases))

    def test_tangent_formula_deterministic(self):
        amps = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        p1 = _tangent_formula_phases(amps, rng=np.random.RandomState(99))
        p2 = _tangent_formula_phases(amps, rng=np.random.RandomState(99))
        np.testing.assert_array_equal(p1, p2)


# ═══════════════════════════════════════════════════════════════════════
# Patterson function tests
# ═══════════════════════════════════════════════════════════════════════

class TestPattersonHelpers:
    """Tests for Patterson map and peak finder."""

    def test_patterson_map_shape(self):
        amps = np.ones(10)
        u, P = _patterson_map(amps, 10)
        assert len(u) == 1000
        assert len(P) == 1000

    def test_patterson_map_origin_peak(self):
        """P(0) should be the sum of amplitudes squared — largest value."""
        amps = np.array([1.0, 2.0, 3.0, 1.0, 2.0])
        u, P = _patterson_map(amps, 5)
        # At u=0, cos(2πn·0) = 1 for all n, so P(0) = sum(a²)
        assert abs(P[0] - np.sum(amps**2)) < 1e-6

    def test_find_peaks_returns_array(self):
        u = np.linspace(0, 1, 500)
        P = np.cos(2 * np.pi * 5 * u) + 0.5 * np.cos(2 * np.pi * 3 * u)
        peaks = _find_patterson_peaks(u, P, height_frac=0.1)
        assert isinstance(peaks, np.ndarray)

    def test_find_peaks_excludes_boundaries(self):
        u = np.linspace(0, 1, 500)
        P = np.ones_like(u) * 2.0  # constant high signal
        peaks = _find_patterson_peaks(u, P, height_frac=0.1, min_sep=0.02)
        # Constant function has no local maxima
        assert len(peaks) == 0


# ═══════════════════════════════════════════════════════════════════════
# GS/HIO tests
# ═══════════════════════════════════════════════════════════════════════

class TestGerchbergSaxtonHelper:
    """Tests for the Gerchberg-Saxton core algorithm."""

    def test_returns_pattern_and_history(self):
        K = 4
        n_modes = 10
        positions = _golden_positions(K)
        S = _sensitivity_matrix(positions, n_modes)
        target_amps = np.abs(S @ np.ones(K))
        pattern, errors, n_iter = _gerchberg_saxton(target_amps, S, K, max_iter=20)
        assert len(pattern) == K
        assert len(errors) > 0
        assert n_iter <= 20

    def test_error_history_non_negative(self):
        K = 4
        n_modes = 10
        S = _sensitivity_matrix(_golden_positions(K), n_modes)
        amps = np.abs(S @ np.array([1, 0, 2, 1], dtype=float))
        _, errors, _ = _gerchberg_saxton(amps, S, K, max_iter=30)
        assert np.all(errors >= 0)

    def test_deterministic_with_seed(self):
        K = 4
        n_modes = 10
        S = _sensitivity_matrix(_golden_positions(K), n_modes)
        amps = np.abs(S @ np.array([1, 2, 0, 1], dtype=float))
        p1, _, _ = _gerchberg_saxton(amps, S, K, rng=np.random.RandomState(7))
        p2, _, _ = _gerchberg_saxton(amps, S, K, rng=np.random.RandomState(7))
        np.testing.assert_array_almost_equal(p1, p2)


# ═══════════════════════════════════════════════════════════════════════
# Experiment H-F1 (Direct Methods) tests
# ═══════════════════════════════════════════════════════════════════════

class TestDirectMethods:
    """Tests for exp_direct_methods (H-F1)."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_direct_methods(rng=np.random.RandomState(42))

    def test_returns_correct_type(self, result):
        assert isinstance(result, DirectMethodResult)

    def test_n_modes_stored(self, result):
        assert result.n_modes == 30

    def test_n_sites_stored(self, result):
        assert result.n_sites == 8

    def test_reconstruction_bounded(self, result):
        assert 0.0 <= result.reconstruction_accuracy <= 1.0

    def test_amplitude_baseline_bounded(self, result):
        assert 0.0 <= result.amplitude_only_baseline <= 1.0

    def test_dm_accuracy_bounded(self, result):
        assert 0.0 <= result.direct_method_accuracy <= 1.0

    def test_phase_error_positive(self, result):
        assert result.phase_error_deg >= 0

    def test_verdict_is_kill(self, result):
        """H-F1 KILLED: tangent formula does not transfer to CWM encoding."""
        assert result.verdict is False

    def test_reconstruction_below_80(self, result):
        """Kill criterion: reconstruction < 80%."""
        assert result.reconstruction_accuracy < 0.80

    def test_seed_reproducibility(self):
        r1 = exp_direct_methods(rng=np.random.RandomState(123))
        r2 = exp_direct_methods(rng=np.random.RandomState(123))
        assert r1.reconstruction_accuracy == r2.reconstruction_accuracy
        assert r1.direct_method_accuracy == r2.direct_method_accuracy


# ═══════════════════════════════════════════════════════════════════════
# Experiment H-F2 (Patterson) tests
# ═══════════════════════════════════════════════════════════════════════

class TestPattersonFunction:
    """Tests for exp_patterson_function (H-F2)."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_patterson_function(rng=np.random.RandomState(42))

    def test_returns_correct_type(self, result):
        assert isinstance(result, PattersonResult)

    def test_n_sites_stored(self, result):
        assert result.n_sites == 6

    def test_n_true_distances_is_K_choose_2(self, result):
        K = result.n_sites
        assert result.n_true_distances == K * (K - 1) // 2

    def test_recovery_fraction_bounded(self, result):
        assert 0.0 <= result.distance_recovery_fraction <= 1.0

    def test_distance_error_non_negative(self, result):
        assert result.mean_distance_error >= 0

    def test_true_distances_sorted(self, result):
        d = result.true_distances
        assert np.all(d[:-1] <= d[1:])

    def test_verdict_is_kill(self, result):
        """H-F2 KILLED: Patterson function doesn't transfer to sin²-based CWM."""
        assert result.verdict is False

    def test_fewer_than_K_recovered(self, result):
        """Kill criterion: fewer than K independent distances recovered."""
        assert result.n_recovered_distances < result.n_sites

    def test_seed_reproducibility(self):
        r1 = exp_patterson_function(rng=np.random.RandomState(77))
        r2 = exp_patterson_function(rng=np.random.RandomState(77))
        assert r1.distance_recovery_fraction == r2.distance_recovery_fraction


# ═══════════════════════════════════════════════════════════════════════
# Experiment H-F3 (Gerchberg-Saxton) tests
# ═══════════════════════════════════════════════════════════════════════

class TestGerchbergSaxton:
    """Tests for exp_gerchberg_saxton (H-F3)."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_gerchberg_saxton(rng=np.random.RandomState(42))

    def test_returns_correct_type(self, result):
        assert isinstance(result, GerchbergSaxtonResult)

    def test_n_modes_stored(self, result):
        assert result.n_modes == 30

    def test_n_sites_stored(self, result):
        assert result.n_sites == 8

    def test_max_iterations_stored(self, result):
        assert result.max_iterations == 200

    def test_final_error_non_negative(self, result):
        assert result.final_error >= 0

    def test_reconstruction_bounded(self, result):
        assert 0.0 <= result.reconstruction_accuracy <= 1.0

    def test_error_history_exists(self, result):
        assert len(result.error_history) > 0

    def test_error_history_non_negative(self, result):
        assert np.all(result.error_history >= 0)

    def test_verdict_is_kill(self, result):
        """H-F3 KILLED: GS/HIO does not converge within 100 iterations."""
        assert result.verdict is False

    def test_did_not_converge_within_100(self, result):
        """Kill: n_iterations > 100 (convergence_threshold)."""
        assert result.n_iterations > 100 or result.final_error > 1e-4

    def test_seed_reproducibility(self):
        r1 = exp_gerchberg_saxton(rng=np.random.RandomState(55))
        r2 = exp_gerchberg_saxton(rng=np.random.RandomState(55))
        assert r1.final_error == r2.final_error
        assert r1.n_iterations == r2.n_iterations


# ═══════════════════════════════════════════════════════════════════════
# Experiment H-F4 (Molecular Replacement) tests
# ═══════════════════════════════════════════════════════════════════════

class TestMolecularReplacement:
    """Tests for exp_molecular_replacement (H-F4)."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_molecular_replacement(rng=np.random.RandomState(42))

    def test_returns_correct_type(self, result):
        assert isinstance(result, MolecularReplacementResult)

    def test_n_modes_stored(self, result):
        assert result.n_modes == 30

    def test_n_patterns_stored(self, result):
        assert result.n_patterns_stored == 8

    def test_n_trials_stored(self, result):
        assert result.n_trials == 200

    def test_amp_accuracy_bounded(self, result):
        assert 0.0 <= result.amplitude_only_accuracy <= 1.0

    def test_complex_accuracy_bounded(self, result):
        assert 0.0 <= result.complex_recall_accuracy <= 1.0

    def test_mr_accuracy_bounded(self, result):
        assert 0.0 <= result.mr_recall_accuracy <= 1.0

    def test_mr_margin_non_negative(self, result):
        assert result.mean_mr_margin >= 0

    def test_verdict_is_kill(self, result):
        """H-F4 KILLED: MR recall does not beat complex recall."""
        assert result.verdict is False

    def test_mr_does_not_beat_complex(self, result):
        """Kill criterion: MR accuracy ≤ complex recall."""
        assert result.mr_recall_accuracy <= result.complex_recall_accuracy

    def test_seed_reproducibility(self):
        r1 = exp_molecular_replacement(rng=np.random.RandomState(88))
        r2 = exp_molecular_replacement(rng=np.random.RandomState(88))
        assert r1.mr_recall_accuracy == r2.mr_recall_accuracy
        assert r1.amplitude_only_accuracy == r2.amplitude_only_accuracy


# ═══════════════════════════════════════════════════════════════════════
# Integration tests (run_all_franklin)
# ═══════════════════════════════════════════════════════════════════════

class TestRunAllFranklin:
    """Integration tests for the full run_all_franklin pipeline."""

    @pytest.fixture(scope="class")
    def results(self):
        return run_all_franklin(verbose=False)

    def test_returns_dict(self, results):
        assert isinstance(results, dict)

    def test_four_results(self, results):
        assert len(results) == 4

    def test_keys_present(self, results):
        assert set(results.keys()) == {"H-F1", "H-F2", "H-F3", "H-F4"}

    def test_result_types(self, results):
        assert isinstance(results["H-F1"], DirectMethodResult)
        assert isinstance(results["H-F2"], PattersonResult)
        assert isinstance(results["H-F3"], GerchbergSaxtonResult)
        assert isinstance(results["H-F4"], MolecularReplacementResult)

    def test_all_verdicts_are_kills(self, results):
        """All four hypotheses should be honestly KILLED."""
        for key, r in results.items():
            assert r.verdict is False, f"{key} was not KILLED"

    def test_verbose_mode_runs(self):
        """Verbose mode should run without error."""
        results = run_all_franklin(verbose=True)
        assert len(results) == 4
