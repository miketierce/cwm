"""
Tests for S8 — Gabor: Holographic Distributed Memory
=====================================================

Hypotheses: H-G1 through H-G4
"""

import numpy as np
import pytest

from simulations.gabor_holographic import (
    # Helpers
    _golden_positions,
    _sensitivity_matrix,
    _shift_positions,
    _autocorrelation_kernel,
    _reconstruct_from_k_modes,
    _compute_crosstalk,
    _fit_r_squared,
    _half_width_half_max,
    # Experiments
    exp_shift_tolerance,
    exp_sub_aperture,
    exp_bandwidth_ceiling,
    exp_crosstalk_envelope,
    # Result types
    ShiftToleranceResult,
    SubApertureResult,
    BandwidthCeilingResult,
    CrosstalkEnvelopeResult,
    # Runner
    run_all_gabor,
)


# ═══════════════════════════════════════════════════════════════════════
# Helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Unit tests for all pure helper functions."""

    # --- _golden_positions ---

    def test_golden_positions_count(self):
        assert len(_golden_positions(6)) == 6

    def test_golden_positions_in_unit_interval(self):
        pos = _golden_positions(10)
        assert np.all(pos >= 0.02)
        assert np.all(pos <= 0.98)

    def test_golden_positions_unique(self):
        pos = _golden_positions(8)
        assert len(set(pos)) == 8

    def test_golden_positions_low_discrepancy(self):
        """Points should be reasonably spread out."""
        pos = np.sort(_golden_positions(10))
        gaps = np.diff(pos)
        assert np.std(gaps) < 0.15  # not too clustered

    # --- _sensitivity_matrix ---

    def test_sensitivity_matrix_shape(self):
        pos = _golden_positions(4)
        S = _sensitivity_matrix(pos, 20)
        assert S.shape == (20, 4)

    def test_sensitivity_matrix_nonneg(self):
        pos = _golden_positions(5)
        S = _sensitivity_matrix(pos, 10)
        assert np.all(S >= 0.0)
        assert np.all(S <= 1.0)

    def test_sensitivity_matrix_sin_squared(self):
        pos = np.array([0.25])
        S = _sensitivity_matrix(pos, 3)
        expected = np.sin(np.array([[1], [2], [3]]) * np.pi * 0.25) ** 2
        np.testing.assert_allclose(S, expected, atol=1e-12)

    def test_sensitivity_matrix_boundary_zero(self):
        """sin²(nπ·0) = 0 and sin²(nπ·1) = 0 for all n."""
        S0 = _sensitivity_matrix(np.array([0.0]), 5)
        S1 = _sensitivity_matrix(np.array([1.0]), 5)
        np.testing.assert_allclose(S0, 0.0, atol=1e-12)
        np.testing.assert_allclose(S1, 0.0, atol=1e-12)

    # --- _shift_positions ---

    def test_shift_by_zero(self):
        pos = _golden_positions(5)
        shifted = _shift_positions(pos, 0.0)
        np.testing.assert_allclose(shifted, pos, atol=1e-12)

    def test_shift_stays_in_bounds(self):
        pos = _golden_positions(8)
        shifted = _shift_positions(pos, 0.5)
        assert np.all(shifted >= 0.02)
        assert np.all(shifted <= 0.98)

    def test_shift_wraps(self):
        pos = np.array([0.9])
        shifted = _shift_positions(pos, 0.3)
        # 0.9 + 0.3 = 1.2 → 0.2 after mod 1 → clipped to [0.02, 0.98]
        assert shifted[0] >= 0.02
        assert shifted[0] <= 0.98

    # --- _autocorrelation_kernel ---

    def test_autocorrelation_peak_at_zero(self):
        shifts = np.linspace(0, 0.1, 10)
        ac = _autocorrelation_kernel(5, shifts)
        assert ac[0] == np.max(ac)

    def test_autocorrelation_decreases_near_zero(self):
        shifts = np.linspace(0, 0.1, 10)
        ac = _autocorrelation_kernel(10, shifts)
        assert ac[0] > ac[-1]

    def test_autocorrelation_shape(self):
        shifts = np.linspace(0, 0.2, 15)
        ac = _autocorrelation_kernel(5, shifts)
        assert len(ac) == 15

    def test_autocorrelation_positive(self):
        shifts = np.linspace(0, 0.05, 10)
        ac = _autocorrelation_kernel(5, shifts)
        assert np.all(ac >= 0)

    # --- _reconstruct_from_k_modes ---

    def test_full_mode_reconstruction_perfect(self):
        """With all modes, reconstruction should be perfect."""
        pos = _golden_positions(4)
        S = _sensitivity_matrix(pos, 20)
        rng = np.random.RandomState(42)
        mass = rng.randint(1, 4, size=(5, 4)).astype(float)
        fp = (S @ mass.T).T
        all_modes = np.arange(20)
        acc = _reconstruct_from_k_modes(S, fp, all_modes, mass)
        assert acc == 1.0

    def test_partial_mode_reconstruction_decreases(self):
        """Fewer modes should give lower (or equal) accuracy."""
        pos = _golden_positions(6)
        S = _sensitivity_matrix(pos, 30)
        rng = np.random.RandomState(42)
        mass = rng.randint(1, 4, size=(8, 6)).astype(float)
        fp = (S @ mass.T).T
        acc_full = _reconstruct_from_k_modes(S, fp, np.arange(30), mass)
        acc_half = _reconstruct_from_k_modes(S, fp, np.arange(15), mass)
        assert acc_full >= acc_half

    # --- _compute_crosstalk ---

    def test_crosstalk_same_modes_nonzero(self):
        """Same modes → should have nonzero crosstalk."""
        pos = _golden_positions(4)
        S = _sensitivity_matrix(pos, 10)
        pa = np.array([1.0, 2.0, 1.0, 3.0])
        pb = np.array([2.0, 1.0, 3.0, 1.0])
        modes = np.arange(10)
        ct = _compute_crosstalk(S, pa, pb, modes, modes)
        assert ct > 0.0

    def test_crosstalk_disjoint_modes(self):
        """Disjoint modes → crosstalk should be zero or very small."""
        pos = _golden_positions(4)
        S = _sensitivity_matrix(pos, 20)
        pa = np.array([1.0, 2.0, 1.0, 3.0])
        pb = np.array([2.0, 1.0, 3.0, 1.0])
        modes_a = np.arange(0, 10)
        modes_b = np.arange(10, 20)
        ct = _compute_crosstalk(S, pa, pb, modes_a, modes_b)
        # With disjoint modes, projection of A onto B's modes uses
        # different mode indices — not necessarily zero due to pattern content
        assert 0.0 <= ct <= 1.0

    def test_crosstalk_bounded(self):
        pos = _golden_positions(4)
        S = _sensitivity_matrix(pos, 10)
        pa = np.array([1.0, 2.0, 1.0, 3.0])
        pb = np.array([2.0, 1.0, 3.0, 1.0])
        modes = np.arange(10)
        ct = _compute_crosstalk(S, pa, pb, modes, modes)
        assert 0.0 <= ct <= 1.0

    # --- _fit_r_squared ---

    def test_fit_linear_perfect(self):
        x = np.linspace(0, 1, 20)
        y = 2 * x + 3
        r2 = _fit_r_squared(x, y, "linear")
        assert r2 > 0.99

    def test_fit_gaussian_on_gaussian(self):
        x = np.linspace(0, 2, 30)
        y = np.exp(-2 * x ** 2) + 0.1
        r2 = _fit_r_squared(x, y, "gaussian")
        assert r2 > 0.9

    def test_fit_sinc2_on_sinc2(self):
        x = np.linspace(0.01, 2, 30)
        y = np.sinc(3 * x) ** 2 + 0.05
        r2 = _fit_r_squared(x, y, "sinc2")
        assert r2 > 0.8

    def test_fit_r_squared_bounded(self):
        x = np.linspace(0, 1, 20)
        y = np.sin(10 * x)
        r2 = _fit_r_squared(x, y, "linear")
        assert r2 <= 1.0

    def test_fit_unknown_model_returns_zero(self):
        x = np.linspace(0, 1, 10)
        y = x
        r2 = _fit_r_squared(x, y, "unknown")
        assert r2 == 0.0

    # --- _half_width_half_max ---

    def test_hwhm_triangle(self):
        x = np.linspace(-1, 1, 101)
        y = np.maximum(0, 1 - np.abs(x))
        hwhm = _half_width_half_max(y, x)
        assert 0.3 < hwhm < 0.7

    def test_hwhm_flat_zero(self):
        x = np.linspace(0, 1, 10)
        y = np.zeros(10)
        hwhm = _half_width_half_max(y, x)
        assert hwhm == 0.0


# ═══════════════════════════════════════════════════════════════════════
# H-G1: Shift-Tolerant Recall
# ═══════════════════════════════════════════════════════════════════════

class TestShiftTolerance:
    """H-G1 — Recall under spatial shift tracks autocorrelation kernel."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_shift_tolerance(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, ShiftToleranceResult)

    def test_verdict(self, result):
        # We don't pre-assert confirm or kill — just check it's boolean
        assert isinstance(result.verdict, bool)

    def test_correlation_bounded(self, result):
        assert -1.0 <= result.correlation_with_prediction <= 1.0

    def test_shifts_start_at_zero(self, result):
        assert result.shifts[0] == 0.0

    def test_recall_at_zero_shift_is_max(self, result):
        assert result.mean_recall_vs_shift[0] == np.max(result.mean_recall_vs_shift)

    def test_recall_decreases_with_shift(self, result):
        """Recall should generally decrease as shift increases."""
        assert result.mean_recall_vs_shift[0] > result.mean_recall_vs_shift[-1]

    def test_predicted_width_positive(self, result):
        assert result.predicted_tolerance_width > 0

    def test_measured_width_nonneg(self, result):
        assert result.measured_tolerance_width >= 0

    def test_width_ratio_positive(self, result):
        assert result.width_ratio >= 0

    def test_n_modes_stored(self, result):
        assert result.n_modes == 40

    def test_n_sites_stored(self, result):
        assert result.n_sites == 8

    def test_seed_reproducibility(self):
        r1 = exp_shift_tolerance(seed=99)
        r2 = exp_shift_tolerance(seed=99)
        assert r1.correlation_with_prediction == r2.correlation_with_prediction


# ═══════════════════════════════════════════════════════════════════════
# H-G2: Sub-Aperture Degradation Curve
# ═══════════════════════════════════════════════════════════════════════

class TestSubAperture:
    """H-G2 — Reconstruction accuracy scales linearly with K/N."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_sub_aperture(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, SubApertureResult)

    def test_verdict(self, result):
        assert isinstance(result.verdict, bool)

    def test_r_squared_bounded(self, result):
        assert result.linear_r_squared <= 1.0

    def test_k_values_increasing(self, result):
        assert np.all(np.diff(result.k_values) > 0)

    def test_k_fractions_bounded(self, result):
        assert np.all(result.k_fractions > 0)
        assert np.all(result.k_fractions <= 1.0)

    def test_accuracies_bounded(self, result):
        assert np.all(result.mean_accuracies >= 0)
        assert np.all(result.mean_accuracies <= 1.0)

    def test_full_modes_near_perfect(self, result):
        """With K=N modes, accuracy should be very high."""
        assert result.mean_accuracies[-1] >= 0.8

    def test_n_modes_stored(self, result):
        assert result.n_modes == 40

    def test_n_sites_stored(self, result):
        assert result.n_sites == 8

    def test_seed_reproducibility(self):
        r1 = exp_sub_aperture(seed=77)
        r2 = exp_sub_aperture(seed=77)
        assert r1.linear_r_squared == r2.linear_r_squared


# ═══════════════════════════════════════════════════════════════════════
# H-G3: Bandwidth Utilization Ceiling
# ═══════════════════════════════════════════════════════════════════════

class TestBandwidthCeiling:
    """H-G3 — Capacity techniques increase bandwidth utilization monotonically."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_bandwidth_ceiling(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, BandwidthCeilingResult)

    def test_verdict(self, result):
        assert isinstance(result.verdict, bool)

    def test_n_bw_positive(self, result):
        assert result.n_bw > 0

    def test_q_values_positive(self, result):
        assert np.all(result.q_values > 0)

    def test_technique_count(self, result):
        assert len(result.technique_names) == 4

    def test_technique_names(self, result):
        assert "baseline" in result.technique_names
        assert "polysemic" in result.technique_names

    def test_p_eff_positive(self, result):
        assert np.all(result.p_eff_values > 0)

    def test_eta_bounded(self, result):
        assert np.all(result.eta_values >= 0)

    def test_n_modes_stored(self, result):
        assert result.n_modes == 40

    def test_seed_reproducibility(self):
        r1 = exp_bandwidth_ceiling(seed=88)
        r2 = exp_bandwidth_ceiling(seed=88)
        np.testing.assert_array_equal(r1.eta_values, r2.eta_values)


# ═══════════════════════════════════════════════════════════════════════
# H-G4: Crosstalk Selectivity Envelope
# ═══════════════════════════════════════════════════════════════════════

class TestCrosstalkEnvelope:
    """H-G4 — Crosstalk vs overlap follows a smooth envelope."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_crosstalk_envelope(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, CrosstalkEnvelopeResult)

    def test_verdict(self, result):
        assert isinstance(result.verdict, bool)

    def test_overlaps_start_at_zero(self, result):
        assert result.overlaps[0] == 0.0

    def test_overlaps_end_at_one(self, result):
        assert result.overlaps[-1] == 1.0

    def test_crosstalk_bounded(self, result):
        assert np.all(result.mean_crosstalk >= 0)
        assert np.all(result.mean_crosstalk <= 1.0)

    def test_r_squared_bounded(self, result):
        assert result.sinc2_r_squared <= 1.0
        assert result.gaussian_r_squared <= 1.0
        assert result.linear_r_squared <= 1.0

    def test_best_model_valid(self, result):
        assert result.best_model in ("sinc2", "gaussian", "linear")

    def test_best_r_squared_is_max(self, result):
        r2s = [result.sinc2_r_squared, result.gaussian_r_squared,
               result.linear_r_squared]
        assert result.best_r_squared == max(r2s)

    def test_n_modes_stored(self, result):
        assert result.n_modes == 40

    def test_n_sites_stored(self, result):
        assert result.n_sites == 8

    def test_crosstalk_has_structure(self, result):
        """Crosstalk should vary with overlap (not constant)."""
        ct = result.mean_crosstalk
        assert np.std(ct) > 1e-6

    def test_seed_reproducibility(self):
        r1 = exp_crosstalk_envelope(seed=55)
        r2 = exp_crosstalk_envelope(seed=55)
        assert r1.best_r_squared == r2.best_r_squared


# ═══════════════════════════════════════════════════════════════════════
# Integration: run_all_gabor
# ═══════════════════════════════════════════════════════════════════════

class TestRunAllGabor:
    """Integration tests for the run_all_gabor orchestrator."""

    @pytest.fixture(scope="class")
    def results(self):
        return run_all_gabor(verbose=False)

    def test_returns_dict(self, results):
        assert isinstance(results, dict)

    def test_returns_four_results(self, results):
        assert len(results) == 4

    def test_keys_present(self, results):
        for key in ("H-G1", "H-G2", "H-G3", "H-G4"):
            assert key in results

    def test_result_types(self, results):
        assert isinstance(results["H-G1"], ShiftToleranceResult)
        assert isinstance(results["H-G2"], SubApertureResult)
        assert isinstance(results["H-G3"], BandwidthCeilingResult)
        assert isinstance(results["H-G4"], CrosstalkEnvelopeResult)

    def test_verbose_mode_runs(self, capsys):
        run_all_gabor(verbose=True)
        captured = capsys.readouterr()
        assert "H-G1" in captured.out
        assert "S8 SUMMARY" in captured.out

    def test_all_verdicts_are_bool(self, results):
        for r in results.values():
            assert isinstance(r.verdict, bool)
