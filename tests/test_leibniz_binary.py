"""
Tests for S7 — Leibniz: Binary Encoding and Monadic Compression
================================================================

Hypotheses: H-L1 through H-L4
Expected verdicts: 3/4 confirmed (L1, L3, L4), 1/4 killed (L2)
"""

import numpy as np
import pytest

from simulations.leibniz_binary import (
    # Helpers
    _golden_positions,
    _sensitivity_matrix,
    _to_binary,
    _gray_encode,
    _gray_decode,
    _build_natural_codebook,
    _build_gray_codebook,
    _build_hexagram_codebook,
    _build_multilevel_codebook,
    _nearest_codeword,
    # Experiments
    exp_binary_quantization,
    exp_gray_coding,
    exp_monadic_reconstruction,
    exp_hexagram_codebook,
    # Result types
    BinaryQuantizationResult,
    GrayCodingResult,
    MonadicReconstructionResult,
    HexagramCodebookResult,
    # Runner
    run_all_leibniz,
)


# ═══════════════════════════════════════════════════════════════════════
# Helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Unit tests for all pure helper functions."""

    def test_golden_positions_count(self):
        assert len(_golden_positions(6)) == 6

    def test_golden_positions_in_unit_interval(self):
        pos = _golden_positions(10)
        assert np.all(pos >= 0.02)
        assert np.all(pos <= 0.98)

    def test_golden_positions_unique(self):
        pos = _golden_positions(8)
        assert len(set(pos)) == 8

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

    def test_to_binary_zero(self):
        np.testing.assert_array_equal(_to_binary(0, 4), [0, 0, 0, 0])

    def test_to_binary_value(self):
        np.testing.assert_array_equal(_to_binary(5, 4), [0, 1, 0, 1])

    def test_to_binary_max(self):
        np.testing.assert_array_equal(_to_binary(15, 4), [1, 1, 1, 1])

    def test_gray_encode_first_values(self):
        assert _gray_encode(0) == 0
        assert _gray_encode(1) == 1
        assert _gray_encode(2) == 3
        assert _gray_encode(3) == 2

    def test_gray_decode_roundtrip(self):
        for i in range(64):
            assert _gray_decode(_gray_encode(i)) == i

    def test_gray_adjacent_hamming_one(self):
        """Adjacent Gray codes differ by exactly 1 bit."""
        for i in range(63):
            g1 = _gray_encode(i)
            g2 = _gray_encode(i + 1)
            diff = bin(g1 ^ g2).count("1")
            assert diff == 1

    def test_natural_codebook_shape(self):
        cb = _build_natural_codebook(16, 4)
        assert cb.shape == (16, 4)

    def test_natural_codebook_first_last(self):
        cb = _build_natural_codebook(8, 3)
        np.testing.assert_array_equal(cb[0], [0, 0, 0])
        np.testing.assert_array_equal(cb[7], [1, 1, 1])

    def test_gray_codebook_shape(self):
        cb = _build_gray_codebook(32, 6)
        assert cb.shape == (32, 6)

    def test_gray_codebook_is_bijection(self):
        """Gray code enumerates the same codeword SET as natural."""
        nat = set(tuple(r) for r in _build_natural_codebook(32, 6))
        gray = set(tuple(r) for r in _build_gray_codebook(32, 6))
        assert nat == gray

    def test_hexagram_codebook_shape(self):
        cb = _build_hexagram_codebook()
        assert cb.shape == (64, 6)

    def test_hexagram_codebook_all_unique(self):
        cb = _build_hexagram_codebook()
        rows = set(tuple(r) for r in cb)
        assert len(rows) == 64

    def test_multilevel_codebook_shape(self):
        cb = _build_multilevel_codebook(64, 3, 4)
        assert cb.shape == (64, 3)

    def test_multilevel_codebook_levels(self):
        cb = _build_multilevel_codebook(64, 3, 4)
        assert np.all(cb >= 0)
        assert np.all(cb <= 3)

    def test_multilevel_codebook_unique(self):
        cb = _build_multilevel_codebook(64, 3, 4)
        rows = set(tuple(r) for r in cb)
        assert len(rows) == 64

    def test_nearest_codeword_exact(self):
        """Exact fingerprint matches index 0."""
        fps = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        assert _nearest_codeword(np.array([1.0, 0.0]), fps) == 0

    def test_nearest_codeword_noisy(self):
        fps = np.array([[1.0, 0.0], [0.0, 1.0]])
        query = np.array([0.9, 0.1])
        assert _nearest_codeword(query, fps) == 0


# ═══════════════════════════════════════════════════════════════════════
# H-L1: Binary Quantisation
# ═══════════════════════════════════════════════════════════════════════

class TestBinaryQuantization:
    """H-L1 — Binary quantisation retains recall accuracy. Expected: CONFIRMED."""

    @pytest.fixture(scope="class")
    def result(self):
        return exp_binary_quantization(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, BinaryQuantizationResult)

    def test_verdict_is_confirm(self, result):
        assert result.verdict is True

    def test_retention_above_70(self, result):
        assert result.retention_ratio >= 0.70

    def test_continuous_accuracy_bounded(self, result):
        assert 0.0 <= result.continuous_recall_accuracy <= 1.0

    def test_binary_accuracy_bounded(self, result):
        assert 0.0 <= result.binary_recall_accuracy <= 1.0

    def test_continuous_near_perfect(self, result):
        assert result.continuous_recall_accuracy >= 0.90

    def test_binary_above_chance(self, result):
        assert result.binary_recall_accuracy > 1.0 / result.P

    def test_N_stored(self, result):
        assert result.N == 50

    def test_P_stored(self, result):
        assert result.P == 8

    def test_seed_reproducibility(self):
        r1 = exp_binary_quantization(seed=99)
        r2 = exp_binary_quantization(seed=99)
        assert r1.retention_ratio == r2.retention_ratio


# ═══════════════════════════════════════════════════════════════════════
# H-L2: Gray Coding
# ═══════════════════════════════════════════════════════════════════════

class TestGrayCoding:
    """
    H-L2 — Gray coding vs natural binary. Expected: KILLED.

    Gray and natural codebooks produce the same set of mass patterns
    (Gray code is a bijection), so the fingerprint sets are identical.
    The ML decoder in fingerprint space gives the same average error rate
    regardless of the symbol-to-codeword mapping.
    """

    @pytest.fixture(scope="class")
    def result(self):
        return exp_gray_coding(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, GrayCodingResult)

    def test_verdict_is_kill(self, result):
        assert result.verdict is False

    def test_same_fingerprint_set(self, result):
        assert result.same_fingerprint_set is True

    def test_improvement_below_20(self, result):
        assert result.improvement_pct < 20.0

    def test_error_rates_similar(self, result):
        """Average error rates should be close (same codebook set)."""
        assert abs(result.mean_natural_error - result.mean_gray_error) < 0.10

    def test_mean_natural_error_bounded(self, result):
        assert 0.0 <= result.mean_natural_error <= 1.0

    def test_mean_gray_error_bounded(self, result):
        assert 0.0 <= result.mean_gray_error <= 1.0

    def test_nonzero_errors_at_high_noise(self, result):
        """At high noise, both should show some errors."""
        assert result.natural_error_rates[-1] > 0.0
        assert result.gray_error_rates[-1] > 0.0

    def test_noise_levels_stored(self, result):
        assert len(result.noise_levels) == 6

    def test_n_sites_stored(self, result):
        assert result.n_sites == 6

    def test_n_modes_stored(self, result):
        assert result.n_modes == 8

    def test_seed_reproducibility(self):
        r1 = exp_gray_coding(seed=77)
        r2 = exp_gray_coding(seed=77)
        assert r1.mean_natural_error == r2.mean_natural_error
        assert r1.mean_gray_error == r2.mean_gray_error


# ═══════════════════════════════════════════════════════════════════════
# H-L3: Monadic Reconstruction
# ═══════════════════════════════════════════════════════════════════════

class TestMonadicReconstruction:
    """
    H-L3 — Monadic reconstruction from partial modes. Expected: CONFIRMED.

    With n_modes >> n_sites, the sensitivity matrix is hugely overdetermined.
    Any K (= n_sites) linearly independent modes reconstruct the pattern
    exactly via least-squares.
    """

    @pytest.fixture(scope="class")
    def result(self):
        return exp_monadic_reconstruction(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, MonadicReconstructionResult)

    def test_verdict_is_confirm(self, result):
        assert result.verdict is True

    def test_half_accuracy_above_50(self, result):
        assert result.half_accuracy >= 0.50

    def test_full_accuracy_perfect(self, result):
        assert result.full_accuracy == 1.0

    def test_half_accuracy_perfect(self, result):
        assert result.half_accuracy == 1.0

    def test_quarter_accuracy_perfect(self, result):
        assert result.quarter_accuracy == 1.0

    def test_min_modes_equals_sites(self, result):
        """Minimum modes for 50% accuracy should equal n_sites (K=8)."""
        assert result.min_modes_for_50pct == result.n_sites

    def test_n_modes_stored(self, result):
        assert result.n_modes == 40

    def test_n_sites_stored(self, result):
        assert result.n_sites == 8

    def test_seed_reproducibility(self):
        r1 = exp_monadic_reconstruction(seed=88)
        r2 = exp_monadic_reconstruction(seed=88)
        assert r1.half_accuracy == r2.half_accuracy


# ═══════════════════════════════════════════════════════════════════════
# H-L4: Hexagram Codebook
# ═══════════════════════════════════════════════════════════════════════

class TestHexagramCodebook:
    """
    H-L4 — Hexagram codebook vs dense multi-level. Expected: CONFIRMED.

    Binary encoding (6 sites x 2 levels) outperforms dense multi-level
    (3 sites x 4 levels) because the sensitivity matrix has rank 6 vs 3,
    spreading 64 fingerprints across a higher-dimensional subspace.
    """

    @pytest.fixture(scope="class")
    def result(self):
        return exp_hexagram_codebook(seed=42)

    def test_result_type(self, result):
        assert isinstance(result, HexagramCodebookResult)

    def test_verdict_is_confirm(self, result):
        assert result.verdict is True

    def test_hexagram_better_than_dense(self, result):
        assert result.mean_hexagram_error < result.mean_dense_error

    def test_hex_sites_stored(self, result):
        assert result.hex_sites == 6

    def test_dense_sites_stored(self, result):
        assert result.dense_sites == 3

    def test_n_modes_stored(self, result):
        assert result.n_modes == 8

    def test_symbols_stored(self, result):
        assert result.n_hexagram_symbols == 64
        assert result.n_dense_symbols == 64

    def test_hex_error_bounded(self, result):
        assert 0.0 <= result.mean_hexagram_error <= 1.0

    def test_dense_error_bounded(self, result):
        assert 0.0 <= result.mean_dense_error <= 1.0

    def test_noise_levels_count(self, result):
        assert len(result.noise_levels) == 6

    def test_error_rates_increase_with_noise(self, result):
        """Error rates should generally increase with noise level."""
        assert result.hexagram_error_rates[-1] >= result.hexagram_error_rates[0]

    def test_seed_reproducibility(self):
        r1 = exp_hexagram_codebook(seed=55)
        r2 = exp_hexagram_codebook(seed=55)
        assert r1.mean_hexagram_error == r2.mean_hexagram_error
        assert r1.mean_dense_error == r2.mean_dense_error


# ═══════════════════════════════════════════════════════════════════════
# Integration: run_all_leibniz
# ═══════════════════════════════════════════════════════════════════════

class TestRunAllLeibniz:
    """Integration tests for the run_all_leibniz orchestrator."""

    @pytest.fixture(scope="class")
    def results(self):
        return run_all_leibniz(verbose=False)

    def test_returns_dict(self, results):
        assert isinstance(results, dict)

    def test_returns_four_results(self, results):
        assert len(results) == 4

    def test_keys_present(self, results):
        for key in ("H-L1", "H-L2", "H-L3", "H-L4"):
            assert key in results

    def test_result_types(self, results):
        assert isinstance(results["H-L1"], BinaryQuantizationResult)
        assert isinstance(results["H-L2"], GrayCodingResult)
        assert isinstance(results["H-L3"], MonadicReconstructionResult)
        assert isinstance(results["H-L4"], HexagramCodebookResult)

    def test_three_confirmed_one_killed(self, results):
        verdicts = [r.verdict for r in results.values()]
        assert sum(verdicts) == 3
        assert results["H-L2"].verdict is False

    def test_verbose_mode_runs(self, capsys):
        run_all_leibniz(verbose=True)
        captured = capsys.readouterr()
        assert "H-L1" in captured.out
        assert "S7 SUMMARY" in captured.out
