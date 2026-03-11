"""
S7 — Gottfried Wilhelm Leibniz (1646–1716): Binary Encoding and Monadic Compression
=====================================================================================

Leibniz invented binary arithmetic (1679) after studying the I Ching's 64
hexagrams — 6-bit binary codes used for 3,000+ years.  His monadology (1714)
proposed that each indivisible "monad" reflects the entire universe from its
own perspective — a philosophical eigenmode (each mode encodes the full cavity
geometry).

This sidebar asks four questions about SEM encoding:

1. Binary quantization (H-L1)
   Does binarising eigenmode readout retain associative recall accuracy?
   Hopfield networks are binary by design; the question is whether the
   continuous SEM fingerprint can be coarsened to 1-bit per mode.

2. Gray coding (H-L2)
   Does Gray code quantisation improve noise tolerance over natural binary?
   Adjacent codewords differ by exactly 1 bit, so single-level mass errors
   map to minimum-distance perturbations.

3. Monadic reconstruction (H-L3)
   Each eigenmode "sees" the entire perturbation pattern (the monad property).
   Can any N/2 modes reconstruct the full pattern via least-squares inversion?

4. Hexagram codebook (H-L4)
   An I Ching–inspired sparse 6-bit codebook for small-payload applications.
   Does binary encoding (more sites, fewer levels) beat dense multi-level
   encoding (fewer sites, more levels) for noise tolerance?

References:
  - Leibniz, "Explication de l'arithmétique binaire" (1703)
  - Amit, Gutfreund & Sompolinsky, Phys. Rev. A 32, 1007 (1985)
  - Gray, "Pulse code communication" US Patent 2,632,058 (1953)
  - Reed & Solomon, J. SIAM 8, 300 (1960)
"""

from __future__ import annotations

import warnings
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class BinaryQuantizationResult:
    """H-L1 — Binary quantisation vs continuous recall."""
    N: int                                # network size (number of modes)
    P: int                                # stored patterns
    n_trials: int                         # independent trial count
    noise_fraction: float                 # noise σ as fraction of fp std
    continuous_recall_accuracy: float     # baseline: L2 nearest-neighbour
    binary_recall_accuracy: float         # binarised fingerprint Hamming NN
    retention_ratio: float                # binary / continuous
    verdict: bool                         # True if retention ≥ 0.70


@dataclass
class GrayCodingResult:
    """H-L2 — Gray code vs natural binary under noise."""
    n_sites: int                          # perturbation sites
    n_modes: int                          # readout modes
    n_symbols: int                        # codebook size
    n_trials: int                         # noise trials per noise level
    noise_levels: np.ndarray              # sigma/fp_std values tested
    natural_error_rates: np.ndarray       # decoding error rate (natural)
    gray_error_rates: np.ndarray          # decoding error rate (Gray)
    mean_natural_error: float             # avg across noise levels
    mean_gray_error: float                # avg across noise levels
    improvement_pct: float                # (natural - gray) / natural * 100
    same_fingerprint_set: bool            # True if codebook sets identical
    verdict: bool                         # True if improvement ≥ 20%


@dataclass
class MonadicReconstructionResult:
    """H-L3 — Reconstruction from N/2 modes (monadic redundancy)."""
    n_modes: int                          # total modes
    n_sites: int                          # perturbation sites
    n_trials: int                         # patterns tested
    full_accuracy: float                  # reconstruction with all modes
    half_accuracy: float                  # reconstruction with N/2 modes
    quarter_accuracy: float               # reconstruction with N/4 modes
    min_modes_for_50pct: int              # fewest modes giving ≥ 50% accuracy
    verdict: bool                         # True if half_accuracy ≥ 0.50


@dataclass
class HexagramCodebookResult:
    """H-L4 — I Ching hexagram codebook vs dense multi-level code."""
    n_hexagram_symbols: int               # 64 (= 2^6)
    n_dense_symbols: int                  # 64 (= 4^3)
    hex_sites: int                        # 6 (binary: more sites, fewer levels)
    dense_sites: int                      # 3 (multi-level: fewer sites, more levels)
    n_modes: int                          # readout modes
    n_trials: int                         # noise trials
    noise_levels: np.ndarray              # sigma/fp_std values tested
    hexagram_error_rates: np.ndarray      # error rate per noise level
    dense_error_rates: np.ndarray         # error rate per noise level
    mean_hexagram_error: float
    mean_dense_error: float
    verdict: bool                         # True if hexagram < dense at same SNR


# ═══════════════════════════════════════════════════════════════════════
# Helpers (reuse SEM physics from other modules)
# ═══════════════════════════════════════════════════════════════════════

def _golden_positions(K: int) -> np.ndarray:
    """Golden-ratio low-discrepancy positions in (0, 1)."""
    phi = (1 + np.sqrt(5)) / 2
    pos = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    return np.clip(pos, 0.02, 0.98)


def _sensitivity_matrix(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """S[n,k] = sin²(nπx_k) — frequency-shift sensitivity."""
    n = np.arange(1, n_modes + 1)[:, None]
    x = positions[None, :]
    return np.sin(n * np.pi * x) ** 2


def _to_binary(value: int, n_bits: int) -> np.ndarray:
    """Convert integer to binary array of length n_bits (MSB first)."""
    bits = np.zeros(n_bits, dtype=int)
    for i in range(n_bits - 1, -1, -1):
        bits[i] = value & 1
        value >>= 1
    return bits


def _gray_encode(n: int) -> int:
    """Standard reflected binary Gray code."""
    return n ^ (n >> 1)


def _gray_decode(g: int) -> int:
    """Decode Gray code to natural binary."""
    n = g
    mask = g >> 1
    while mask:
        n ^= mask
        mask >>= 1
    return n


def _build_natural_codebook(n_symbols: int, n_bits: int) -> np.ndarray:
    """Natural binary codebook: shape (n_symbols, n_bits)."""
    return np.array([_to_binary(i, n_bits) for i in range(n_symbols)])


def _build_gray_codebook(n_symbols: int, n_bits: int) -> np.ndarray:
    """Gray code codebook: shape (n_symbols, n_bits)."""
    return np.array([_to_binary(_gray_encode(i), n_bits)
                     for i in range(n_symbols)])


def _build_hexagram_codebook() -> np.ndarray:
    """
    I Ching hexagram codebook: 64 codewords of 6 bits each.

    Each hexagram is a stack of 6 lines, each yin (0) or yang (1).
    We use natural binary order for unambiguous reproducibility.
    """
    return _build_natural_codebook(64, 6)


def _build_multilevel_codebook(n_symbols: int, n_sites: int,
                                n_levels: int) -> np.ndarray:
    """Multi-level codebook: n_levels^n_sites >= n_symbols."""
    patterns = np.zeros((n_symbols, n_sites), dtype=float)
    for i in range(n_symbols):
        val = i
        for k in range(n_sites - 1, -1, -1):
            patterns[i, k] = val % n_levels
            val //= n_levels
    return patterns


def _nearest_codeword(
    fingerprint: np.ndarray,
    codebook_fingerprints: np.ndarray,
) -> int:
    """Return index of nearest codebook entry (L2 distance)."""
    dists = np.linalg.norm(codebook_fingerprints - fingerprint, axis=1)
    return int(np.argmin(dists))


# ═══════════════════════════════════════════════════════════════════════
# H-L1: Binary quantisation of recall
# ═══════════════════════════════════════════════════════════════════════

def exp_binary_quantization(
    N: int = 50,
    P: int = 8,
    noise_fraction: float = 0.2,
    n_trials: int = 40,
    seed: int = 42,
) -> BinaryQuantizationResult:
    """
    Test whether binarising SEM fingerprints retains recall accuracy.

    Continuous recall: store SEM spectral fingerprints (continuous floats),
    recall via L2 nearest-neighbour in fingerprint space.

    Binary recall: binarise each fingerprint component to {-1, +1} via
    sign(x - median), then recall via Hamming nearest-neighbour.

    Both use the same noisy measurement: continuous fingerprint + Gaussian
    noise.  The binary path binarises the noisy measurement before decoding.

    Kill criterion: binary recall < 50% of continuous recall.
    Confirm criterion: retention >= 70%.
    """
    rng = np.random.RandomState(seed)
    K = 8                     # perturbation sites
    n_modes = N               # modes = encoding dimensionality
    positions = _golden_positions(K)
    S = _sensitivity_matrix(positions, n_modes)

    continuous_correct = 0
    binary_correct = 0

    for trial in range(n_trials):
        trial_seed = rng.randint(int(1e6))
        trial_rng = np.random.RandomState(trial_seed)

        # Generate P random mass patterns and their SEM fingerprints
        mass_patterns = trial_rng.randint(1, 4, size=(P, K)).astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fingerprints = (S @ mass_patterns.T).T  # (P, n_modes)

        # Add noise to measurement
        target_idx = trial_rng.randint(P)
        query_fp = fingerprints[target_idx].copy()
        sigma = noise_fraction * np.std(fingerprints)
        noisy_query = query_fp + trial_rng.randn(n_modes) * sigma

        # --- Continuous recall: L2 nearest-neighbour ---
        dists = np.linalg.norm(fingerprints - noisy_query, axis=1)
        if np.argmin(dists) == target_idx:
            continuous_correct += 1

        # --- Binary recall: binarise then Hamming nearest-neighbour ---
        medians = np.median(fingerprints, axis=0)
        binary_stored = np.where(fingerprints > medians, 1.0, -1.0)
        binary_query = np.where(noisy_query > medians, 1.0, -1.0)
        hamming_dists = np.sum(binary_stored != binary_query, axis=1)
        if np.argmin(hamming_dists) == target_idx:
            binary_correct += 1

    continuous_acc = continuous_correct / n_trials
    binary_acc = binary_correct / n_trials
    retention = binary_acc / max(continuous_acc, 1e-10)

    return BinaryQuantizationResult(
        N=N,
        P=P,
        n_trials=n_trials,
        noise_fraction=noise_fraction,
        continuous_recall_accuracy=continuous_acc,
        binary_recall_accuracy=binary_acc,
        retention_ratio=retention,
        verdict=retention >= 0.70,
    )


# ═══════════════════════════════════════════════════════════════════════
# H-L2: Gray code vs natural binary under noise
# ═══════════════════════════════════════════════════════════════════════

def exp_gray_coding(
    n_sites: int = 6,
    n_modes: int = 8,
    n_symbols: int = 32,
    n_trials: int = 100,
    seed: int = 42,
) -> GrayCodingResult:
    """
    Compare Gray code vs natural binary for SEM codeword decoding under noise.

    Both natural and Gray codebooks enumerate the same *set* of mass patterns
    (Gray code is a bijection on {0,...,n-1}), producing the same *set* of
    spectral fingerprints — just with different symbol-to-codeword mappings.
    Since the ML decoder operates in fingerprint space (L2 nearest-neighbour),
    the symbol-to-codeword mapping is invisible: both give identical average
    error rates.

    Uses deliberately few modes (n_modes ~ n_sites) to create enough stress
    for nonzero errors.

    Kill criterion: Gray-coded noise tolerance <= natural binary.
    Confirm criterion: >= 20% improvement.
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(n_sites)
    S = _sensitivity_matrix(positions, n_modes)

    natural_cb = _build_natural_codebook(n_symbols, n_sites).astype(float)
    gray_cb = _build_gray_codebook(n_symbols, n_sites).astype(float)

    # Verify the two codebooks are the same set of mass patterns
    nat_set = set(tuple(r) for r in natural_cb)
    gray_set = set(tuple(r) for r in gray_cb)
    same_set = (nat_set == gray_set)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        natural_fp = (S @ natural_cb.T).T
        gray_fp = (S @ gray_cb.T).T

    noise_levels = np.array([0.3, 0.5, 0.7, 1.0, 1.5, 2.0])
    fp_std = np.std(natural_fp)

    natural_errors = np.zeros(len(noise_levels))
    gray_errors = np.zeros(len(noise_levels))

    for ni, noise_frac in enumerate(noise_levels):
        sigma = noise_frac * fp_std
        nat_err_count = 0
        gray_err_count = 0

        for trial in range(n_trials):
            trial_seed = rng.randint(int(1e6))
            trial_rng = np.random.RandomState(trial_seed)
            sym_idx = trial_rng.randint(n_symbols)

            # Natural binary: encode, add noise, decode
            noisy_nat = natural_fp[sym_idx] + trial_rng.randn(n_modes) * sigma
            if _nearest_codeword(noisy_nat, natural_fp) != sym_idx:
                nat_err_count += 1

            # Gray code: encode, add noise, decode (fresh noise draw)
            noisy_gray = gray_fp[sym_idx] + trial_rng.randn(n_modes) * sigma
            if _nearest_codeword(noisy_gray, gray_fp) != sym_idx:
                gray_err_count += 1

        natural_errors[ni] = nat_err_count / n_trials
        gray_errors[ni] = gray_err_count / n_trials

    mean_nat = float(np.mean(natural_errors))
    mean_gray = float(np.mean(gray_errors))
    improvement = (mean_nat - mean_gray) / max(mean_nat, 1e-10) * 100.0

    return GrayCodingResult(
        n_sites=n_sites,
        n_modes=n_modes,
        n_symbols=n_symbols,
        n_trials=n_trials,
        noise_levels=noise_levels,
        natural_error_rates=natural_errors,
        gray_error_rates=gray_errors,
        mean_natural_error=mean_nat,
        mean_gray_error=mean_gray,
        improvement_pct=improvement,
        same_fingerprint_set=same_set,
        verdict=improvement >= 20.0,
    )


# ═══════════════════════════════════════════════════════════════════════
# H-L3: Monadic reconstruction from partial mode subsets
# ═══════════════════════════════════════════════════════════════════════

def exp_monadic_reconstruction(
    n_modes: int = 40,
    n_sites: int = 8,
    n_trials: int = 30,
    seed: int = 42,
) -> MonadicReconstructionResult:
    """
    Test whether N/2 modes suffice to reconstruct the full perturbation pattern.

    The "monadic property" says each mode encodes information about the entire
    pattern.  If the sensitivity matrix S has rank >= K (number of sites), then
    any K linearly independent rows (modes) can recover the K-length pattern
    via least-squares.  We test with N/2 and N/4 randomly selected modes.

    Kill criterion: half-mode accuracy < 50%.
    Confirm criterion: N/2 modes reconstruct with >= 50% accuracy.
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(n_sites)
    S_full = _sensitivity_matrix(positions, n_modes)

    mode_counts = np.arange(n_sites, n_modes + 1)
    mode_accuracies = np.zeros(len(mode_counts))

    for mi, m in enumerate(mode_counts):
        trial_correct = 0
        for trial in range(n_trials):
            trial_seed = rng.randint(int(1e6))
            trial_rng = np.random.RandomState(trial_seed)

            pattern = trial_rng.randint(0, 4, size=n_sites).astype(float)
            fp_full = S_full @ pattern

            mode_idx = trial_rng.choice(n_modes, size=m, replace=False)
            mode_idx.sort()
            S_sub = S_full[mode_idx]
            fp_sub = fp_full[mode_idx]

            reconstructed, _, _, _ = np.linalg.lstsq(S_sub, fp_sub, rcond=None)
            reconstructed_q = np.clip(np.round(reconstructed), 0, 3)
            if np.allclose(reconstructed_q, pattern):
                trial_correct += 1

        mode_accuracies[mi] = trial_correct / n_trials

    half_idx = n_modes // 2 - n_sites
    quarter_idx = n_modes // 4 - n_sites
    full_idx = n_modes - n_sites

    full_acc = mode_accuracies[full_idx] if full_idx < len(mode_accuracies) else 0.0
    half_acc = mode_accuracies[max(half_idx, 0)] if half_idx < len(mode_accuracies) else 0.0
    quarter_acc = mode_accuracies[max(quarter_idx, 0)] if quarter_idx < len(mode_accuracies) else 0.0

    above_50 = np.where(mode_accuracies >= 0.50)[0]
    min_modes_50 = int(mode_counts[above_50[0]]) if len(above_50) > 0 else n_modes + 1

    return MonadicReconstructionResult(
        n_modes=n_modes,
        n_sites=n_sites,
        n_trials=n_trials,
        full_accuracy=float(full_acc),
        half_accuracy=float(half_acc),
        quarter_accuracy=float(quarter_acc),
        min_modes_for_50pct=min_modes_50,
        verdict=bool(half_acc >= 0.50),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-L4: I Ching hexagram codebook vs dense multi-level encoding
# ═══════════════════════════════════════════════════════════════════════

def exp_hexagram_codebook(
    n_modes: int = 8,
    n_trials: int = 100,
    seed: int = 42,
) -> HexagramCodebookResult:
    """
    Compare hexagram binary encoding vs dense multi-level encoding for SEM.

    Both encode 64 symbols (6 bits of payload):
        Hexagram: 6 sites x 2 mass levels (binary: 0 or 1)
        Dense:    3 sites x 4 mass levels (quaternary: 0, 1, 2, 3)

    The hexagram uses more physical sites but fewer mass levels.  More sites
    means higher-rank sensitivity matrix -> fingerprints live in 6-D subspace
    (vs 3-D for dense), providing better codeword separation.

    Uses deliberately few readout modes (n_modes ~ n_sites) to stress both
    codes and produce measurable error rates.

    Kill criterion: hexagram error rate >= dense at same per-codebook-sigma noise.
    Confirm criterion: hexagram strictly lower error rate.
    """
    rng = np.random.RandomState(seed)
    n_symbols = 64

    # --- Hexagram: 6 sites x 2 levels ---
    hex_sites = 6
    hex_pos = _golden_positions(hex_sites)
    S_hex = _sensitivity_matrix(hex_pos, n_modes)
    hex_cb = _build_hexagram_codebook().astype(float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        hex_fp = (S_hex @ hex_cb.T).T          # (64, n_modes)

    # --- Dense: 3 sites x 4 levels ---
    dense_sites = 3
    dense_pos = _golden_positions(dense_sites)
    S_dense = _sensitivity_matrix(dense_pos, n_modes)
    dense_cb = _build_multilevel_codebook(n_symbols, dense_sites, 4)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        dense_fp = (S_dense @ dense_cb.T).T    # (64, n_modes)

    noise_levels = np.array([0.3, 0.5, 0.7, 1.0, 1.5, 2.0])

    hex_errors = np.zeros(len(noise_levels))
    dense_errors = np.zeros(len(noise_levels))

    for ni, noise_frac in enumerate(noise_levels):
        hex_sigma = noise_frac * np.std(hex_fp)
        dense_sigma = noise_frac * np.std(dense_fp)
        hex_err = 0
        dense_err = 0

        for trial in range(n_trials):
            trial_seed = rng.randint(int(1e6))
            trial_rng = np.random.RandomState(trial_seed)
            sym_idx = trial_rng.randint(n_symbols)

            # Hexagram
            noisy_hex = hex_fp[sym_idx] + trial_rng.randn(n_modes) * hex_sigma
            if _nearest_codeword(noisy_hex, hex_fp) != sym_idx:
                hex_err += 1

            # Dense
            noisy_dense = dense_fp[sym_idx] + trial_rng.randn(n_modes) * dense_sigma
            if _nearest_codeword(noisy_dense, dense_fp) != sym_idx:
                dense_err += 1

        hex_errors[ni] = hex_err / n_trials
        dense_errors[ni] = dense_err / n_trials

    mean_hex = float(np.mean(hex_errors))
    mean_dense = float(np.mean(dense_errors))

    return HexagramCodebookResult(
        n_hexagram_symbols=n_symbols,
        n_dense_symbols=n_symbols,
        hex_sites=hex_sites,
        dense_sites=dense_sites,
        n_modes=n_modes,
        n_trials=n_trials,
        noise_levels=noise_levels,
        hexagram_error_rates=hex_errors,
        dense_error_rates=dense_errors,
        mean_hexagram_error=mean_hex,
        mean_dense_error=mean_dense,
        verdict=mean_hex < mean_dense,
    )


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_leibniz(verbose: bool = True) -> dict:
    """Run all S7 Leibniz experiments and return results dict."""
    results = {}

    # --- H-L1: Binary quantisation ---
    r1 = exp_binary_quantization()
    results["H-L1"] = r1
    if verbose:
        print("=" * 60)
        print("H-L1: Binary Quantisation of Recall")
        print("=" * 60)
        print(f"  Network size N={r1.N}, stored patterns P={r1.P}")
        print(f"  Noise: {r1.noise_fraction:.0%} of fingerprint sigma")
        print(f"  Continuous L2 recall:     {r1.continuous_recall_accuracy:.1%}")
        print(f"  Binary Hamming recall:    {r1.binary_recall_accuracy:.1%}")
        print(f"  Retention ratio:          {r1.retention_ratio:.1%}")
        vstr = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-L2: Gray coding ---
    r2 = exp_gray_coding()
    results["H-L2"] = r2
    if verbose:
        print("=" * 60)
        print("H-L2: Gray Code vs Natural Binary Under Noise")
        print("=" * 60)
        print(f"  Sites={r2.n_sites}, modes={r2.n_modes}, symbols={r2.n_symbols}")
        print(f"  Same fingerprint set: {r2.same_fingerprint_set}")
        print(f"  Mean natural error rate: {r2.mean_natural_error:.3f}")
        print(f"  Mean Gray error rate:    {r2.mean_gray_error:.3f}")
        print(f"  Improvement:             {r2.improvement_pct:+.1f}%")
        vstr = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-L3: Monadic reconstruction ---
    r3 = exp_monadic_reconstruction()
    results["H-L3"] = r3
    if verbose:
        print("=" * 60)
        print("H-L3: Monadic Reconstruction from Partial Modes")
        print("=" * 60)
        print(f"  Modes={r3.n_modes}, sites={r3.n_sites}")
        print(f"  Full-mode accuracy:    {r3.full_accuracy:.1%}")
        print(f"  Half-mode (N/2={r3.n_modes//2}) accuracy: {r3.half_accuracy:.1%}")
        print(f"  Quarter-mode (N/4={r3.n_modes//4}) accuracy: {r3.quarter_accuracy:.1%}")
        print(f"  Min modes for >=50%:   {r3.min_modes_for_50pct}")
        vstr = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-L4: Hexagram codebook ---
    r4 = exp_hexagram_codebook()
    results["H-L4"] = r4
    if verbose:
        print("=" * 60)
        print("H-L4: I Ching Hexagram Codebook vs Dense Multi-Level")
        print("=" * 60)
        print(f"  Hexagram: {r4.hex_sites} sites x 2 levels"
              f"  |  Dense: {r4.dense_sites} sites x 4 levels")
        print(f"  Symbols={r4.n_hexagram_symbols}, modes={r4.n_modes}")
        print(f"  Mean hexagram error rate: {r4.mean_hexagram_error:.3f}")
        print(f"  Mean dense error rate:    {r4.mean_dense_error:.3f}")
        vstr = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = len(results) - confirmed
        print("=" * 60)
        print(f"S7 SUMMARY: {confirmed}/4 confirmed, {killed}/4 killed")
        print("=" * 60)

    return results
