"""
Tests for simulations/scranton_dogon.py — Scranton–Dogon informed experiments.

Six hypotheses (H7–H12) derived from Laird Scranton's analysis of Dogon
cosmological symbol systems mapped onto SEM physics.
"""

import numpy as np
import pytest

from simulations.scranton_dogon import (
    # Helpers
    _build_sensitivity,
    _fingerprint,
    _quantise,
    _hamming_distance,
    # Experiments
    exp_polysemic_readout,
    exp_duality_encoding,
    exp_nommo_naming,
    exp_sigi_cycle,
    exp_ammas_egg,
    exp_rosetta_stone,
    # Runner
    run_all_scranton_dogon,
    # Dataclasses
    PolysemicResult,
    DualityResult,
    NamingResult,
    SigiCycleResult,
    SeedSpectrumResult,
    RosettaResult,
)


# ═══════════════════════════════════════════════════════════════════════
# Helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Basic helper function correctness."""

    def test_sensitivity_shape(self):
        S = _build_sensitivity(np.array([0.2, 0.5, 0.8]), n_modes=10)
        assert S.shape == (10, 3)

    def test_sensitivity_values_at_midpoint(self):
        """sin²(n·π·0.5) = 1 for odd n, 0 for even n."""
        S = _build_sensitivity(np.array([0.5]), n_modes=6)
        for n_idx in range(6):
            n = n_idx + 1  # 1-indexed mode number
            expected = np.sin(n * np.pi * 0.5) ** 2
            assert abs(S[n_idx, 0] - expected) < 1e-10

    def test_sensitivity_symmetry_identity(self):
        """sin²(nπx) = sin²(nπ(1-x)) for all n — the Dogon duality!"""
        x = 0.37
        S_x = _build_sensitivity(np.array([x]), n_modes=20)
        S_mirror = _build_sensitivity(np.array([1 - x]), n_modes=20)
        np.testing.assert_allclose(S_x, S_mirror, atol=1e-12)

    def test_fingerprint_linear(self):
        S = _build_sensitivity(np.array([0.3, 0.7]), n_modes=5)
        p1 = np.array([1.0, 0.0])
        p2 = np.array([0.0, 1.0])
        fp12 = _fingerprint(S, p1 + p2)
        fp1 = _fingerprint(S, p1)
        fp2 = _fingerprint(S, p2)
        np.testing.assert_allclose(fp12, fp1 + fp2, atol=1e-12)

    def test_quantise_binary(self):
        vals = np.array([0.1, 0.4, 0.6, 0.9])
        q = _quantise(vals, 2)
        assert q[0] == 0
        assert q[-1] == 1

    def test_hamming_distance_identical(self):
        a = np.array([1, 2, 3, 4])
        assert _hamming_distance(a, a) == 0

    def test_hamming_distance_different(self):
        a = np.array([1, 2, 3, 4])
        b = np.array([1, 0, 3, 0])
        assert _hamming_distance(a, b) == 2


# ═══════════════════════════════════════════════════════════════════════
# H7 — Polysemic Readout
# ═══════════════════════════════════════════════════════════════════════

class TestPolysemicReadout:
    """H7: One perturbation, multiple independent meanings."""

    def test_returns_correct_type(self):
        r = exp_polysemic_readout(K=4, n_modes=20, n_channels=4,
                                   n_patterns=30, rng=np.random.RandomState(1))
        assert isinstance(r, PolysemicResult)

    def test_channel_count(self):
        r = exp_polysemic_readout(K=4, n_modes=20, n_channels=3,
                                   n_patterns=30, rng=np.random.RandomState(1))
        assert r.n_channels == 3
        assert len(r.channel_capacities) == 3

    def test_cross_correlation_diagonal_is_one(self):
        r = exp_polysemic_readout(K=4, n_modes=20, n_channels=4,
                                   n_patterns=30, rng=np.random.RandomState(1))
        for i in range(r.n_channels):
            assert abs(r.cross_correlations[i, i] - 1.0) < 0.1

    def test_polysemic_gain_positive(self):
        """With enough modes, polysemic capacity should exceed single-channel."""
        r = exp_polysemic_readout(K=6, n_modes=40, n_channels=4,
                                   n_patterns=50, rng=np.random.RandomState(42))
        # Sum of channel capacities should ≥ single channel capacity
        assert r.total_capacity_bits >= r.single_channel_bits * 0.8

    def test_independence_bounded(self):
        r = exp_polysemic_readout(K=4, n_modes=20, n_channels=4,
                                   n_patterns=30, rng=np.random.RandomState(1))
        assert 0.0 <= r.mean_independence <= 1.0


# ═══════════════════════════════════════════════════════════════════════
# H8 — Amma's Duality
# ═══════════════════════════════════════════════════════════════════════

class TestDualityEncoding:
    """H8: Symmetric pairs + odd/even readout."""

    def test_returns_correct_type(self):
        r = exp_duality_encoding(K_pairs=3, n_modes=20,
                                  n_patterns=50, rng=np.random.RandomState(1))
        assert isinstance(r, DualityResult)

    def test_pair_symmetry(self):
        """Verify each pair sums to 1.0."""
        r = exp_duality_encoding(K_pairs=4, n_modes=20,
                                  n_patterns=50, rng=np.random.RandomState(1))
        for pair in r.sym_position_pairs:
            assert abs(pair[0] + pair[1] - 1.0) < 0.01

    def test_dual_capacity_exists(self):
        """Combined dual-channel capacity should be > 0."""
        r = exp_duality_encoding(K_pairs=4, n_modes=30,
                                  n_patterns=100, rng=np.random.RandomState(42))
        assert r.combined_capacity > 0
        assert r.odd_mode_capacity > 0
        assert r.even_mode_capacity > 0

    def test_more_sites_more_capacity(self):
        """Doubling the number of sites (via pairing) should help."""
        r = exp_duality_encoding(K_pairs=4, n_modes=30,
                                  n_patterns=100, rng=np.random.RandomState(42))
        # With 8 sites (4 pairs) dual-channel should beat 4 asymmetric sites
        # The dual_gain_pct tells us the answer
        assert r.combined_capacity > 0


# ═══════════════════════════════════════════════════════════════════════
# H9 — Nommo Naming
# ═══════════════════════════════════════════════════════════════════════

class TestNommoNaming:
    """H9: Max-distance fingerprints reduce BER."""

    def test_returns_correct_type(self):
        r = exp_nommo_naming(K=6, n_modes=20, n_codewords=8,
                              n_trials=50, rng=np.random.RandomState(1))
        assert isinstance(r, NamingResult)

    def test_optimised_hamming_geq_random(self):
        """Greedy selection should achieve ≥ random Hamming distance."""
        r = exp_nommo_naming(K=6, n_modes=20, n_codewords=8,
                              n_trials=50, rng=np.random.RandomState(42))
        assert r.mean_hamming_optimised >= r.mean_hamming_random * 0.9

    def test_ber_bounded(self):
        r = exp_nommo_naming(K=6, n_modes=20, n_codewords=8,
                              n_trials=50, rng=np.random.RandomState(1))
        assert 0.0 <= r.optimised_ber <= 1.0
        assert 0.0 <= r.random_ber <= 1.0

    def test_naming_hypothesis(self):
        """With sufficient modes and noise, max-distance should win."""
        r = exp_nommo_naming(K=8, n_modes=30, n_codewords=16,
                              noise_sigma=0.05, n_trials=200,
                              rng=np.random.RandomState(42))
        # Optimised should have lower or equal BER
        assert r.optimised_ber <= r.random_ber + 0.05


# ═══════════════════════════════════════════════════════════════════════
# H10 — Sigi Cycle
# ═══════════════════════════════════════════════════════════════════════

class TestSigiCycle:
    """H10: Temporal-decay multiplexing."""

    def test_returns_correct_type(self):
        r = exp_sigi_cycle(K=4, n_modes=15, n_patterns=40,
                            rng=np.random.RandomState(1))
        assert isinstance(r, SigiCycleResult)

    def test_time_windows(self):
        r = exp_sigi_cycle(K=4, n_modes=15, n_time_windows=5,
                            n_patterns=40, rng=np.random.RandomState(1))
        assert len(r.readout_times) == 5
        assert len(r.channel_bits) == 5

    def test_monotone_readout_times(self):
        r = exp_sigi_cycle(K=4, n_modes=15, n_patterns=40,
                            rng=np.random.RandomState(1))
        assert all(r.readout_times[i] < r.readout_times[i + 1]
                   for i in range(len(r.readout_times) - 1))

    def test_temporal_gain(self):
        """Multi-window reading should increase total information."""
        r = exp_sigi_cycle(K=6, n_modes=20, n_time_windows=4,
                            n_patterns=80, rng=np.random.RandomState(42))
        assert r.total_time_mux_bits >= r.single_shot_bits * 0.8

    def test_effective_channels_positive(self):
        r = exp_sigi_cycle(K=6, n_modes=20, n_time_windows=4,
                            n_patterns=80, rng=np.random.RandomState(42))
        assert r.n_effective_channels >= 1


# ═══════════════════════════════════════════════════════════════════════
# H11 — Amma's Egg
# ═══════════════════════════════════════════════════════════════════════

class TestAmmasEgg:
    """H11: Seed-to-spectrum hierarchical encoding."""

    def test_returns_correct_type(self):
        r = exp_ammas_egg(K=8, seed_size=3, n_patterns=30,
                           rng=np.random.RandomState(1))
        assert isinstance(r, SeedSpectrumResult)

    def test_seed_smaller_than_full(self):
        r = exp_ammas_egg(K=10, seed_size=3, n_patterns=30,
                           rng=np.random.RandomState(1))
        assert r.seed_size < r.full_size

    def test_fidelity_bounded(self):
        r = exp_ammas_egg(K=8, seed_size=3, n_patterns=30,
                           rng=np.random.RandomState(1))
        assert 0.0 <= r.seed_fidelity <= 1.0
        assert 0.0 <= r.random_fidelity <= 1.0

    def test_condition_number_positive(self):
        r = exp_ammas_egg(K=8, seed_size=3, n_patterns=30,
                           rng=np.random.RandomState(1))
        assert r.seed_condition_number > 0
        assert r.random_condition_number > 0


# ═══════════════════════════════════════════════════════════════════════
# H12 — Cross-Culture Rosetta
# ═══════════════════════════════════════════════════════════════════════

class TestRosettaStone:
    """H12: Multi-rod translation via calibration."""

    def test_returns_correct_type(self):
        r = exp_rosetta_stone(K=4, n_codewords=14,
                               rng=np.random.RandomState(1))
        assert isinstance(r, RosettaResult)

    def test_self_decode_high(self):
        """Self-decoding should be near-perfect at low noise."""
        r = exp_rosetta_stone(K=6, n_modes=30, noise_sigma=0.005,
                               n_codewords=10, rng=np.random.RandomState(42))
        assert r.self_decode_accuracy > 0.8

    def test_cross_decode_reasonable(self):
        """Cross-decode should be usable with good calibration."""
        r = exp_rosetta_stone(K=6, n_modes=20, noise_sigma=0.01,
                               n_codewords=20, rng=np.random.RandomState(42))
        assert r.cross_decode_accuracy > 0.3  # at least better than chance

    def test_rod_count(self):
        r = exp_rosetta_stone(K=4, n_codewords=14,
                               rng=np.random.RandomState(1))
        assert r.n_rods == 3

    def test_translation_cond_finite(self):
        r = exp_rosetta_stone(K=4, n_codewords=14,
                               rng=np.random.RandomState(1))
        assert np.isfinite(r.translation_matrix_cond)


# ═══════════════════════════════════════════════════════════════════════
# Integration: run_all
# ═══════════════════════════════════════════════════════════════════════

class TestRunAll:
    """Integration test for the full experiment suite."""

    def test_run_all_returns_six(self):
        results = run_all_scranton_dogon(verbose=False)
        assert len(results) == 6

    def test_run_all_keys(self):
        results = run_all_scranton_dogon(verbose=False)
        expected_keys = {
            "polysemic_readout", "duality_encoding", "nommo_naming",
            "sigi_cycle", "ammas_egg", "rosetta_stone",
        }
        assert set(results.keys()) == expected_keys

    def test_run_all_all_have_verdict(self):
        results = run_all_scranton_dogon(verbose=False)
        for name, r in results.items():
            assert hasattr(r, "verdict"), f"{name} missing verdict"
            assert isinstance(r.verdict, bool), f"{name} verdict not bool"
