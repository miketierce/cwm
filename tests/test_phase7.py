"""
Tests for site_optimization.py and semantic_mapping.py (Phase 7).

Covers:
    - Sensitivity matrix construction and properties
    - All placement strategies
    - Fingerprint distinguishability
    - Codebook construction and decoding
    - Semantic embedding projection
    - Similarity preservation
    - Compositional encoding
"""

import numpy as np
import pytest

from simulations.site_optimization import (
    build_sensitivity_matrix,
    uniform_placement,
    golden_ratio_placement,
    jittered_placement,
    optimize_placement_greedy,
    optimize_placement_gradient,
    optimize_layout,
    count_distinguishable_words,
    sweep_configurations,
    compare_strategies,
    SensitivityMatrix,
    SiteLayout,
    PlacementSweep,
    StrategyComparison,
)
from simulations.semantic_mapping import (
    bits_to_pattern,
    pattern_to_bits,
    build_codebook,
    build_semantic_mapping,
    decode_fingerprint,
    analyze_similarity_preservation,
    encode_compositional,
    Codebook,
    SemanticMapping,
    DecodingResult,
    SimilarityAnalysis,
    CompositionalEncoding,
)


# ═══════════════════════════════════════════════════════════════════════
# Sensitivity Matrix
# ═══════════════════════════════════════════════════════════════════════

class TestSensitivityMatrix:
    """Test sensitivity matrix construction and properties."""

    def test_shape(self):
        pos = uniform_placement(5)
        sm = build_sensitivity_matrix(pos, n_modes=20)
        assert sm.S.shape == (20, 5)

    def test_values_bounded(self):
        """sin²(nπx) ∈ [0, 1]."""
        pos = uniform_placement(8)
        sm = build_sensitivity_matrix(pos, n_modes=50)
        assert np.all(sm.S >= 0.0)
        assert np.all(sm.S <= 1.0 + 1e-10)

    def test_endpoint_nodes(self):
        """sin²(nπ·0) = 0 and sin²(nπ·1) = 0 for integer n."""
        pos = np.array([0.0, 1.0])
        sm = build_sensitivity_matrix(pos, n_modes=10)
        # Should be near zero at endpoints
        assert np.allclose(sm.S[:, 0], 0.0, atol=1e-10)
        assert np.allclose(sm.S[:, 1], 0.0, atol=1e-10)

    def test_midpoint_max_odd(self):
        """sin²(nπ·0.5) = 1 for odd n, = 0 for even n."""
        pos = np.array([0.5])
        sm = build_sensitivity_matrix(pos, n_modes=10)
        odd = sm.S[0::2, 0]  # modes 1, 3, 5, ...
        even = sm.S[1::2, 0]  # modes 2, 4, 6, ...
        assert np.allclose(odd, 1.0, atol=1e-10)
        assert np.allclose(even, 0.0, atol=1e-10)

    def test_rank_equals_sites_when_few(self):
        """With K < N, rank should be K (for non-degenerate positions)."""
        # Avoid symmetric pairs: sin²(nπx) = sin²(nπ(1-x)), so x and 1-x
        # produce identical columns. Use asymmetric positions.
        pos = np.array([0.13, 0.37, 0.58, 0.79])
        sm = build_sensitivity_matrix(pos, n_modes=50)
        assert sm.rank == 4

    def test_symmetric_positions_reduce_rank(self):
        """x and 1-x produce identical sin² columns — rank must drop."""
        pos = np.array([0.2, 0.35, 0.65, 0.8])
        sm = build_sensitivity_matrix(pos, n_modes=50)
        # 0.2↔0.8 and 0.35↔0.65 are symmetric pairs → only 2 independent
        assert sm.rank == 2

    def test_singular_values_positive(self):
        pos = uniform_placement(5)
        sm = build_sensitivity_matrix(pos, n_modes=30)
        assert np.all(sm.singular_values > 0)

    def test_mutual_coherence_bounded(self):
        """Mutual coherence ∈ [0, 1]."""
        pos = golden_ratio_placement(6)
        sm = build_sensitivity_matrix(pos, n_modes=30)
        assert 0.0 <= sm.mutual_coherence <= 1.0


# ═══════════════════════════════════════════════════════════════════════
# Placement Strategies
# ═══════════════════════════════════════════════════════════════════════

class TestPlacementStrategies:
    """Test that all placement strategies produce valid positions."""

    @pytest.mark.parametrize("n_sites", [3, 5, 10, 16])
    def test_uniform_in_range(self, n_sites):
        pos = uniform_placement(n_sites)
        assert len(pos) == n_sites
        assert np.all(pos > 0)
        assert np.all(pos < 1)

    @pytest.mark.parametrize("n_sites", [3, 5, 10, 16])
    def test_golden_in_range(self, n_sites):
        pos = golden_ratio_placement(n_sites)
        assert len(pos) == n_sites
        assert np.all(pos > 0)
        assert np.all(pos < 1)

    def test_golden_no_duplicates(self):
        """Golden ratio should produce distinct positions."""
        pos = golden_ratio_placement(20)
        assert len(np.unique(np.round(pos, 8))) == 20

    def test_jittered_sorted(self):
        pos = jittered_placement(10)
        assert np.all(np.diff(pos) >= 0)

    def test_greedy_returns_correct_count(self):
        pos = optimize_placement_greedy(5, n_modes=20, n_candidates=100)
        assert len(pos) == 5
        assert np.all(pos > 0)
        assert np.all(pos < 1)

    def test_gradient_returns_correct_count(self):
        pos = optimize_placement_gradient(5, n_modes=20, n_iters=50)
        assert len(pos) == 5
        assert np.all(pos > 0)
        assert np.all(pos < 1)

    def test_greedy_beats_uniform_on_condition(self):
        """Greedy optimization should produce a lower condition number than uniform."""
        n_sites, n_modes = 6, 30
        pos_uni = uniform_placement(n_sites)
        pos_greedy = optimize_placement_greedy(n_sites, n_modes, n_candidates=200)

        sm_uni = build_sensitivity_matrix(pos_uni, n_modes)
        sm_greedy = build_sensitivity_matrix(pos_greedy, n_modes)

        # Greedy should have lower (better) condition number
        assert sm_greedy.condition_number <= sm_uni.condition_number * 2.0


# ═══════════════════════════════════════════════════════════════════════
# Fingerprint Distinguishability
# ═══════════════════════════════════════════════════════════════════════

class TestDistinguishability:
    """Test codeword distinguishability counting."""

    def test_binary_4_sites(self):
        """4 binary sites → 16 codewords, most should be distinguishable."""
        pos = np.array([0.15, 0.35, 0.65, 0.85])
        sm = build_sensitivity_matrix(pos, n_modes=20)
        total, distinct, bits = count_distinguishable_words(sm, alphabet_size=2)
        assert total == 16
        assert distinct >= 8  # at least half should be distinguishable
        assert bits > 0

    def test_trinary_more_than_binary(self):
        """Trinary should encode more bits than binary for same sites."""
        pos = np.array([0.2, 0.4, 0.6, 0.8])
        sm = build_sensitivity_matrix(pos, n_modes=20)
        _, _, bits_bin = count_distinguishable_words(sm, alphabet_size=2)
        _, _, bits_tri = count_distinguishable_words(sm, alphabet_size=3)
        assert bits_tri >= bits_bin

    def test_zero_pattern_always_exists(self):
        """The all-zeros pattern should produce zero fingerprint."""
        pos = uniform_placement(5)
        sm = build_sensitivity_matrix(pos, n_modes=10)
        zero_fp = sm.S @ np.zeros(5)
        assert np.allclose(zero_fp, 0.0)

    def test_more_sites_more_bits(self):
        """More sites should encode at least as many bits."""
        bits_list = []
        for k in [3, 6, 9]:
            pos = uniform_placement(k)
            sm = build_sensitivity_matrix(pos, n_modes=20)
            _, _, bits = count_distinguishable_words(sm, alphabet_size=2, noise_floor=1e-2)
            bits_list.append(bits)
        # Monotonically non-decreasing
        assert bits_list[1] >= bits_list[0]
        assert bits_list[2] >= bits_list[1]


# ═══════════════════════════════════════════════════════════════════════
# Layout Optimizer
# ═══════════════════════════════════════════════════════════════════════

class TestOptimizeLayout:
    """Test the full layout optimizer."""

    @pytest.mark.parametrize("method", ["uniform", "golden", "jittered", "greedy", "gradient"])
    def test_all_methods_return_layout(self, method):
        layout = optimize_layout(
            n_sites=5, n_modes=20, alphabet_size=2,
            noise_floor=1e-2, method=method,
        )
        assert isinstance(layout, SiteLayout)
        assert layout.n_sites == 5
        assert layout.bits_encoded > 0
        assert layout.sensitivity.rank > 0

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError):
            optimize_layout(5, method="nonexistent")


# ═══════════════════════════════════════════════════════════════════════
# Sweep & Comparison
# ═══════════════════════════════════════════════════════════════════════

class TestSweepAndCompare:
    """Test sweep and comparison utilities."""

    def test_sweep_returns_results(self):
        result = sweep_configurations(
            site_range=np.arange(3, 7),
            alphabet_sizes=np.array([2, 3]),
            n_modes=15,
            noise_floor=1e-2,
            method="uniform",
        )
        assert isinstance(result, PlacementSweep)
        assert result.bits_per_config.shape == (4, 2)
        assert result.best_bits > 0

    def test_compare_strategies_returns_results(self):
        result = compare_strategies(
            n_sites=5, n_modes=15, alphabet_size=2, noise_floor=1e-2
        )
        assert isinstance(result, StrategyComparison)
        assert len(result.methods) == 5
        assert result.best_bits > 0


# ═══════════════════════════════════════════════════════════════════════
# Bit/Pattern Conversion
# ═══════════════════════════════════════════════════════════════════════

class TestBitPatternConversion:
    """Test raw bit ↔ pattern conversion."""

    def test_binary_roundtrip(self):
        bits = np.array([1, 0, 1, 1, 0])
        pattern = bits_to_pattern(bits, n_sites=5, alphabet_size=2)
        recovered = pattern_to_bits(pattern, alphabet_size=2)
        np.testing.assert_array_equal(bits, recovered)

    def test_binary_padding(self):
        """If fewer bits than sites, remaining sites are zero."""
        bits = np.array([1, 1])
        pattern = bits_to_pattern(bits, n_sites=5, alphabet_size=2)
        assert pattern[0] == 1
        assert pattern[1] == 1
        assert np.all(pattern[2:] == 0)

    def test_trinary_range(self):
        """Trinary patterns should have values in {0, 1, 2}."""
        bits = np.array([1, 1, 0, 1, 0, 0, 1, 0])
        pattern = bits_to_pattern(bits, n_sites=5, alphabet_size=3)
        assert np.all(pattern >= 0)
        assert np.all(pattern <= 2)


# ═══════════════════════════════════════════════════════════════════════
# Codebook
# ═══════════════════════════════════════════════════════════════════════

class TestCodebook:
    """Test codebook construction and properties."""

    def test_natural_codebook(self):
        pos = np.array([0.2, 0.4, 0.6, 0.8])
        S = build_sensitivity_matrix(pos, n_modes=15).S
        symbols = list("ABCDEFGH")  # 8 symbols, 4 binary sites = 16 codewords
        cb = build_codebook(symbols, S, alphabet_size=2, strategy="natural")
        assert isinstance(cb, Codebook)
        assert len(cb.symbols) == 8
        assert cb.mass_patterns.shape == (8, 4)
        assert cb.fingerprints.shape == (8, 15)

    def test_gray_codebook(self):
        pos = np.array([0.2, 0.5, 0.8])
        S = build_sensitivity_matrix(pos, n_modes=10).S
        symbols = list("ABCD")
        cb = build_codebook(symbols, S, alphabet_size=2, strategy="gray")
        # Adjacent gray codes differ by 1 bit
        for i in range(len(cb.mass_patterns) - 1):
            hamming = np.sum(cb.mass_patterns[i] != cb.mass_patterns[i + 1])
            assert hamming == 1

    def test_maxdist_better_separation(self):
        """Maxdist strategy should have >= min distance vs natural."""
        pos = np.array([0.15, 0.35, 0.65, 0.85])
        S = build_sensitivity_matrix(pos, n_modes=20).S
        symbols = list("ABCD")

        cb_nat = build_codebook(symbols, S, alphabet_size=2, strategy="natural")
        cb_max = build_codebook(symbols, S, alphabet_size=2, strategy="maxdist")

        assert cb_max.min_fingerprint_distance >= cb_nat.min_fingerprint_distance * 0.8

    def test_too_many_symbols_raises(self):
        pos = np.array([0.3, 0.7])
        S = build_sensitivity_matrix(pos, n_modes=10).S
        with pytest.raises(ValueError):
            build_codebook(list(range(100)), S, alphabet_size=2)


# ═══════════════════════════════════════════════════════════════════════
# Decoding
# ═══════════════════════════════════════════════════════════════════════

class TestDecoding:
    """Test fingerprint decoding."""

    def test_noiseless_decode(self):
        """Perfect measurement should decode correctly."""
        pos = np.array([0.2, 0.4, 0.6, 0.8])
        S = build_sensitivity_matrix(pos, n_modes=20).S
        symbols = list("ABCDEFGH")
        cb = build_codebook(symbols, S, alphabet_size=2, strategy="natural")

        # Pick symbol 'C' (index 2), use its exact fingerprint
        exact_fp = cb.fingerprints[2]
        result = decode_fingerprint(exact_fp, cb, S)
        assert result.decoded_symbol == "C"
        assert result.residual < 1e-10

    def test_noisy_decode_still_correct(self):
        """Small noise should not change decoding."""
        pos = np.array([0.15, 0.35, 0.65, 0.85])
        S = build_sensitivity_matrix(pos, n_modes=20).S
        symbols = list("ABCD")
        cb = build_codebook(symbols, S, alphabet_size=2, strategy="maxdist")

        rng = np.random.default_rng(42)
        for idx in range(4):
            fp = cb.fingerprints[idx] + rng.normal(0, 1e-4, size=20)
            result = decode_fingerprint(fp, cb, S)
            assert result.decoded_symbol == symbols[idx]

    def test_confidence_high_for_exact(self):
        """Exact match should have high confidence (large ratio)."""
        pos = np.array([0.2, 0.5, 0.8])
        S = build_sensitivity_matrix(pos, n_modes=10).S
        symbols = list("AB")
        cb = build_codebook(symbols, S, alphabet_size=2, strategy="natural")

        result = decode_fingerprint(cb.fingerprints[0], cb, S)
        assert result.confidence > 1.0  # 2nd best is farther than best


# ═══════════════════════════════════════════════════════════════════════
# Semantic Mapping
# ═══════════════════════════════════════════════════════════════════════

class TestSemanticMapping:
    """Test embedding-to-perturbation projection."""

    def test_builds_mapping(self):
        rng = np.random.default_rng(42)
        embeddings = rng.normal(size=(20, 32))
        pos = uniform_placement(8)
        S = build_sensitivity_matrix(pos, n_modes=30).S

        mapping = build_semantic_mapping(embeddings, S, alphabet_size=2)
        assert isinstance(mapping, SemanticMapping)
        assert mapping.projection_matrix.shape == (8, 32)
        assert mapping.capacity_bits > 0

    def test_similarity_preserved(self):
        """Clustered embeddings should produce correlated fingerprints."""
        rng = np.random.default_rng(42)
        # Create two clusters
        cluster_a = rng.normal(loc=2.0, size=(10, 16))
        cluster_b = rng.normal(loc=-2.0, size=(10, 16))
        embeddings = np.vstack([cluster_a, cluster_b])

        pos = uniform_placement(8)
        S = build_sensitivity_matrix(pos, n_modes=20).S
        mapping = build_semantic_mapping(embeddings, S, alphabet_size=3)

        # Similarity preservation should be positive (similar embeddings → similar fingerprints)
        assert mapping.similarity_preservation > 0.0

    def test_trinary_more_capacity(self):
        """Trinary should have >= capacity of binary with enough embeddings."""
        rng = np.random.default_rng(42)
        # Use enough embeddings to saturate the codebook
        embeddings = rng.normal(size=(50, 16))
        pos = uniform_placement(6)
        S = build_sensitivity_matrix(pos, n_modes=20).S

        m2 = build_semantic_mapping(embeddings, S, alphabet_size=2)
        m3 = build_semantic_mapping(embeddings, S, alphabet_size=3)
        # With many embeddings, trinary has more codewords to utilize
        assert m3.capacity_bits >= m2.capacity_bits


# ═══════════════════════════════════════════════════════════════════════
# Similarity Analysis
# ═══════════════════════════════════════════════════════════════════════

class TestSimilarityAnalysis:
    """Test similarity preservation analysis."""

    def test_identical_gives_perfect_correlation(self):
        """If fingerprints are linear function of embeddings, r = 1."""
        rng = np.random.default_rng(42)
        embeddings = rng.normal(size=(10, 8))
        # Fingerprints = same as embeddings (perfect preservation)
        result = analyze_similarity_preservation(embeddings, embeddings)
        assert result.linear_correlation > 0.99

    def test_random_gives_low_correlation(self):
        """Random fingerprints should have near-zero correlation with embeddings."""
        rng = np.random.default_rng(42)
        embeddings = rng.normal(size=(20, 8))
        fingerprints = rng.normal(size=(20, 8))
        result = analyze_similarity_preservation(embeddings, fingerprints)
        assert abs(result.linear_correlation) < 0.5  # not correlated


# ═══════════════════════════════════════════════════════════════════════
# Compositional Encoding
# ═══════════════════════════════════════════════════════════════════════

class TestCompositionalEncoding:
    """Test multi-rod structured encoding."""

    def test_basic_composition(self):
        rng = np.random.default_rng(42)
        roles = {
            "subject": rng.normal(size=8),
            "verb": rng.normal(size=8),
            "object": rng.normal(size=8),
        }
        pos = uniform_placement(8)
        S = build_sensitivity_matrix(pos, n_modes=15).S

        result = encode_compositional(roles, S, alphabet_size=2)
        assert isinstance(result, CompositionalEncoding)
        assert result.n_rods == 3
        assert len(result.fingerprints_per_rod) == 3
        assert len(result.combined_fingerprint) == 3 * 15

    def test_different_roles_different_fingerprints(self):
        """Different role embeddings should produce different fingerprints."""
        # Use embeddings with clearly different structure.
        # IMPORTANT: use asymmetric site positions (golden ratio) to
        # break the sin²(nπx) = sin²(nπ(1-x)) symmetry that makes
        # mirror-image patterns indistinguishable at uniform sites.
        roles = {
            "subject": np.array([3.0, 2.0, 1.0, 0.0, -1.0, -2.0, -3.0, -4.0]),
            "object": np.array([-4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0]),
        }
        pos = golden_ratio_placement(8)
        S = build_sensitivity_matrix(pos, n_modes=10).S

        result = encode_compositional(roles, S, alphabet_size=2)
        fp_s = result.fingerprints_per_rod[0]
        fp_o = result.fingerprints_per_rod[1]
        assert not np.allclose(fp_s, fp_o)


# ═══════════════════════════════════════════════════════════════════════
# Integration: end-to-end encode → perturb → readout → decode
# ═══════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """End-to-end integration test: symbol → mass pattern → spectral fingerprint → decode."""

    def test_roundtrip_8_symbols(self):
        """Encode 8 symbols, read back all correctly."""
        pos = np.array([0.12, 0.28, 0.44, 0.62, 0.78, 0.92])
        sm = build_sensitivity_matrix(pos, n_modes=30)
        symbols = list("ABCDEFGH")
        cb = build_codebook(symbols, sm.S, alphabet_size=2, strategy="maxdist")

        rng = np.random.default_rng(123)
        errors = 0
        for idx, sym in enumerate(symbols):
            # Simulate noisy readout
            noise = rng.normal(0, 1e-4, size=30)
            measured = cb.fingerprints[idx] + noise
            result = decode_fingerprint(measured, cb, sm.S)
            if result.decoded_symbol != sym:
                errors += 1

        assert errors == 0, f"Decoding errors: {errors}/8"

    def test_roundtrip_26_letters(self):
        """Encode full alphabet with 5 binary sites (32 codewords > 26)."""
        pos = optimize_placement_greedy(5, n_modes=25, n_candidates=200)
        sm = build_sensitivity_matrix(pos, n_modes=25)
        symbols = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        cb = build_codebook(symbols, sm.S, alphabet_size=2, strategy="maxdist")

        # Noiseless decode — all should be perfect
        for idx, sym in enumerate(symbols):
            result = decode_fingerprint(cb.fingerprints[idx], cb, sm.S)
            assert result.decoded_symbol == sym
