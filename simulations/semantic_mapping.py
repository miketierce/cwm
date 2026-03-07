"""
Semantic Mapping for Spectral Eigenmode Memory.

This module bridges the gap between abstract data and physical
perturbation patterns on a glass rod. The hierarchy:

    Level 0 — Raw bits:
        Map bit strings → mass patterns → spectral fingerprints.
        No semantics; just storage and retrieval.

    Level 1 — Structured symbols:
        Map symbols (bytes, ASCII, codebook entries) to perturbation
        patterns via a fixed codebook. Nearest-neighbor search in
        spectral space corresponds to nearest-symbol lookup.

    Level 2 — Semantic embedding:
        Map meaning (word embeddings, feature vectors) to perturbation
        patterns such that semantic similarity is preserved as spectral
        similarity. Two "nearby" concepts produce similar spectral
        fingerprints, enabling content-addressable recall via wave
        interference.

    Level 3 — Compositional encoding:
        Multiple rods in an array encode a structured representation
        (e.g., subject–verb–object), where each rod encodes one
        semantic role and the array encodes a relational structure.

The key constraint: the mapping must be *invertible under noise*.
Given a measured spectral fingerprint (possibly corrupted by thermal
drift, readout noise, or partial mode overlap), we must reliably
recover the original symbol/embedding.

This module provides:
    - Codebook construction (Level 1)
    - Embedding-to-perturbation projection (Level 2)
    - Similarity preservation analysis
    - Capacity under semantic constraints
    - Decoding algorithms (maximum likelihood, threshold)

Dependencies:
    - site_optimization.py (sensitivity matrix, site layouts)
    - glass_resonator.py (Rayleigh perturbation, mode spectrum)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Codebook:
    """A mapping from symbols to mass patterns and spectral fingerprints."""
    symbols: List[Any]                 # the things being encoded
    mass_patterns: np.ndarray          # shape (n_symbols, n_sites)
    fingerprints: np.ndarray           # shape (n_symbols, n_modes)
    site_positions: np.ndarray         # fractional positions of sites
    alphabet_size: int                 # mass levels per site
    min_fingerprint_distance: float    # minimum L2 between any two fingerprints
    avg_fingerprint_distance: float    # average L2 between fingerprints
    codebook_rate: float               # log₂(n_symbols) / n_sites


@dataclass
class SemanticMapping:
    """A mapping from continuous embeddings to spectral fingerprints."""
    projection_matrix: np.ndarray      # maps embedding → mass pattern
    quantizer: str                     # "round", "lloyd", "dithered"
    embedding_dim: int
    n_sites: int
    n_modes: int
    alphabet_size: int
    similarity_preservation: float     # correlation(embedding_sim, spectral_sim)
    distortion: float                  # avg quantization error
    capacity_bits: float               # effective capacity after quantization


@dataclass
class DecodingResult:
    """Result of decoding a measured fingerprint back to a symbol."""
    decoded_symbol: Any
    decoded_pattern: np.ndarray
    confidence: float                  # distance ratio: 2nd-best / best
    residual: float                    # L2 norm of decoding residual
    n_candidates: int                  # how many symbols were considered


@dataclass
class SimilarityAnalysis:
    """How well spectral similarity tracks semantic similarity."""
    n_pairs: int
    embedding_similarities: np.ndarray  # cosine similarity in embedding space
    spectral_similarities: np.ndarray   # cosine similarity in fingerprint space
    rank_correlation: float             # Spearman ρ
    linear_correlation: float           # Pearson r
    monotonicity_violations: int        # pairs where order is swapped
    violation_rate: float               # violations / total pairs


# ═══════════════════════════════════════════════════════════════════════
# Level 0 — Raw bit encoding
# ═══════════════════════════════════════════════════════════════════════

def bits_to_pattern(
    bits: np.ndarray,
    n_sites: int,
    alphabet_size: int = 2,
) -> np.ndarray:
    """
    Convert a bit string to a mass pattern vector.

    For binary (alphabet_size=2): each site is 0 or 1.
    For trinary: pack ceil(log₂(3)) bits per site.

    Parameters
    ----------
    bits : array-like
        Binary input (0s and 1s).
    n_sites : int
        Number of perturbation sites.
    alphabet_size : int
        Mass levels per site.

    Returns
    -------
    pattern : ndarray of shape (n_sites,)
        Mass level at each site (0 to alphabet_size-1).
    """
    bits = np.asarray(bits, dtype=int)
    if alphabet_size == 2:
        # Direct: each bit maps to one site
        pattern = np.zeros(n_sites, dtype=int)
        n_use = min(len(bits), n_sites)
        pattern[:n_use] = bits[:n_use]
        return pattern

    # For alphabet_size > 2: pack bits into base-alphabet_size digits
    bits_per_site = int(np.ceil(np.log2(alphabet_size)))
    pattern = np.zeros(n_sites, dtype=int)
    for k in range(n_sites):
        start = k * bits_per_site
        end = min(start + bits_per_site, len(bits))
        if start >= len(bits):
            break
        val = 0
        for b in range(start, end):
            val = val * 2 + bits[b]
        pattern[k] = min(val, alphabet_size - 1)
    return pattern


def pattern_to_bits(
    pattern: np.ndarray,
    alphabet_size: int = 2,
) -> np.ndarray:
    """Inverse of bits_to_pattern."""
    pattern = np.asarray(pattern, dtype=int)
    if alphabet_size == 2:
        return pattern.copy()

    bits_per_site = int(np.ceil(np.log2(alphabet_size)))
    bits = []
    for val in pattern:
        site_bits = []
        v = int(val)
        for _ in range(bits_per_site):
            site_bits.append(v % 2)
            v //= 2
        bits.extend(reversed(site_bits))
    return np.array(bits, dtype=int)


# ═══════════════════════════════════════════════════════════════════════
# Level 1 — Symbol codebook
# ═══════════════════════════════════════════════════════════════════════

def build_codebook(
    symbols: List[Any],
    sensitivity_matrix: np.ndarray,
    alphabet_size: int = 2,
    strategy: str = "gray",
) -> Codebook:
    """
    Build a codebook mapping symbols to mass patterns.

    Strategies:
        "natural" : Sequential binary/trinary counting.
        "gray"    : Gray code to minimize Hamming distance between
                    adjacent symbols (reduces bit errors from off-by-one
                    mass level misreadings).
        "maxdist" : Greedy assignment maximizing minimum fingerprint
                    distance between used codewords.

    Parameters
    ----------
    symbols : list
        Symbols to encode (e.g., list of characters, integers, etc.).
    sensitivity_matrix : ndarray, shape (n_modes, n_sites)
        The S matrix from site_optimization.
    alphabet_size : int
        Mass levels per site.
    strategy : str
        Codeword assignment strategy.

    Returns
    -------
    Codebook
    """
    n_modes, n_sites = sensitivity_matrix.shape
    n_symbols = len(symbols)
    total_codewords = alphabet_size ** n_sites

    if n_symbols > total_codewords:
        raise ValueError(
            f"Cannot encode {n_symbols} symbols with {n_sites} sites "
            f"and alphabet size {alphabet_size} ({total_codewords} codewords)"
        )

    # Generate codewords based on strategy
    if strategy == "natural":
        patterns = _natural_codewords(n_symbols, n_sites, alphabet_size)
    elif strategy == "gray":
        patterns = _gray_codewords(n_symbols, n_sites, alphabet_size)
    elif strategy == "maxdist":
        patterns = _maxdist_codewords(
            n_symbols, n_sites, alphabet_size, sensitivity_matrix
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    # Compute fingerprints
    mass_values = np.arange(alphabet_size, dtype=float)
    fingerprints = np.array([
        sensitivity_matrix @ mass_values[p] for p in patterns
    ])

    # Compute pairwise distances
    dists = _pairwise_distances(fingerprints)
    min_dist = np.min(dists[dists > 0]) if np.any(dists > 0) else 0.0
    avg_dist = np.mean(dists[np.triu_indices_from(dists, k=1)])

    rate = np.log2(n_symbols) / n_sites if n_sites > 0 else 0.0

    return Codebook(
        symbols=list(symbols),
        mass_patterns=patterns,
        fingerprints=fingerprints,
        site_positions=np.array([]),  # filled by caller if needed
        alphabet_size=alphabet_size,
        min_fingerprint_distance=min_dist,
        avg_fingerprint_distance=avg_dist,
        codebook_rate=rate,
    )


def _natural_codewords(n_symbols, n_sites, alphabet_size):
    """Sequential counting in the given base."""
    patterns = np.zeros((n_symbols, n_sites), dtype=int)
    for i in range(n_symbols):
        val = i
        for k in range(n_sites - 1, -1, -1):
            patterns[i, k] = val % alphabet_size
            val //= alphabet_size
    return patterns


def _gray_codewords(n_symbols, n_sites, alphabet_size):
    """Gray code ordering (binary only; falls back to natural for trinary)."""
    if alphabet_size != 2:
        return _natural_codewords(n_symbols, n_sites, alphabet_size)

    patterns = np.zeros((n_symbols, n_sites), dtype=int)
    for i in range(n_symbols):
        gray = i ^ (i >> 1)
        for k in range(n_sites - 1, -1, -1):
            patterns[i, k] = gray & 1
            gray >>= 1
    return patterns


def _maxdist_codewords(n_symbols, n_sites, alphabet_size, S):
    """Greedy codeword selection maximizing minimum fingerprint distance."""
    # Generate all codewords (feasible for small K)
    total = alphabet_size ** n_sites
    if total > 100_000:
        # Fall back to random selection for large spaces
        rng = np.random.default_rng(42)
        all_patterns = rng.integers(0, alphabet_size, size=(min(total, 50_000), n_sites))
    else:
        all_patterns = np.zeros((total, n_sites), dtype=int)
        for i in range(total):
            val = i
            for k in range(n_sites - 1, -1, -1):
                all_patterns[i, k] = val % alphabet_size
                val //= alphabet_size

    mass_values = np.arange(alphabet_size, dtype=float)
    all_fps = np.array([S @ mass_values[p] for p in all_patterns])

    # Greedy selection: start with the all-zeros pattern, then add the
    # codeword that maximizes the minimum distance to all chosen codewords
    chosen = [0]  # start with all-zeros
    for _ in range(n_symbols - 1):
        chosen_fps = all_fps[chosen]
        best_idx = -1
        best_min_dist = -1.0

        for idx in range(len(all_patterns)):
            if idx in chosen:
                continue
            dists = np.linalg.norm(chosen_fps - all_fps[idx], axis=1)
            min_d = np.min(dists)
            if min_d > best_min_dist:
                best_min_dist = min_d
                best_idx = idx

        chosen.append(best_idx)

    return all_patterns[chosen]


def _pairwise_distances(fingerprints: np.ndarray) -> np.ndarray:
    """Compute pairwise L2 distance matrix."""
    n = len(fingerprints)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = np.linalg.norm(fingerprints[i] - fingerprints[j])
            D[i, j] = d
            D[j, i] = d
    return D


# ═══════════════════════════════════════════════════════════════════════
# Level 2 — Semantic embedding projection
# ═══════════════════════════════════════════════════════════════════════

def build_semantic_mapping(
    embeddings: np.ndarray,
    sensitivity_matrix: np.ndarray,
    alphabet_size: int = 2,
    quantizer: str = "round",
) -> SemanticMapping:
    """
    Build a mapping from continuous embedding vectors to mass patterns
    that preserves similarity structure.

    The idea: find a linear projection W such that
        m = quantize(W @ e)
    maps embedding vector e to a mass pattern m, and
        cos(S @ m₁, S @ m₂) ≈ cos(e₁, e₂)

    We solve for W via Procrustes alignment between the embedding
    Gram matrix and the spectral Gram matrix.

    Parameters
    ----------
    embeddings : ndarray, shape (n_items, embedding_dim)
        The embedding vectors to map.
    sensitivity_matrix : ndarray, shape (n_modes, n_sites)
        The S matrix.
    alphabet_size : int
        Mass levels per site.
    quantizer : str
        Quantization method: "round" (nearest integer),
        "lloyd" (iterative k-means), "dithered" (random dither).

    Returns
    -------
    SemanticMapping
    """
    n_items, d_emb = embeddings.shape
    n_modes, n_sites = sensitivity_matrix.shape

    # Step 1: Find the target mass patterns that best preserve
    # the embedding similarity structure.
    # Compute embedding Gram matrix (cosine similarity)
    E_normed = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-30)
    G_emb = E_normed @ E_normed.T  # cosine similarities

    # Step 2: SVD of embedding matrix → reduce to n_sites dimensions
    U, s, Vt = np.linalg.svd(E_normed, full_matrices=False)
    # Project to n_sites dimensions
    E_reduced = U[:, :n_sites] * s[:n_sites]  # (n_items, n_sites)

    # Step 3: Scale to [0, alphabet_size-1] and quantize
    E_min = E_reduced.min(axis=0)
    E_max = E_reduced.max(axis=0)
    E_range = E_max - E_min + 1e-30
    E_scaled = (E_reduced - E_min) / E_range * (alphabet_size - 1)

    if quantizer == "round":
        patterns = np.round(E_scaled).astype(int)
    elif quantizer == "dithered":
        rng = np.random.default_rng(42)
        dither = rng.uniform(-0.5, 0.5, size=E_scaled.shape)
        patterns = np.round(E_scaled + dither).astype(int)
    else:
        patterns = np.round(E_scaled).astype(int)

    patterns = np.clip(patterns, 0, alphabet_size - 1)

    # Step 4: Compute fingerprints and similarity preservation
    mass_values = np.arange(alphabet_size, dtype=float)
    fingerprints = np.array([
        sensitivity_matrix @ mass_values[p] for p in patterns
    ])
    F_normed = fingerprints / (np.linalg.norm(fingerprints, axis=1, keepdims=True) + 1e-30)
    G_spec = F_normed @ F_normed.T

    # Similarity preservation: how well does spectral sim track embedding sim?
    upper = np.triu_indices(n_items, k=1)
    sim_emb = G_emb[upper]
    sim_spec = G_spec[upper]

    pearson = np.corrcoef(sim_emb, sim_spec)[0, 1] if len(sim_emb) > 1 else 0.0

    # Quantization distortion
    distortion = np.mean(np.abs(E_scaled - patterns))

    # Build the projection matrix: embedding → scaled mass pattern
    # W = diag(scale) @ Vt[:n_sites, :] (from SVD truncation)
    scale = (alphabet_size - 1) / E_range
    W = np.diag(scale) @ Vt[:n_sites, :]  # (n_sites, d_emb)

    # Effective capacity: how many distinct patterns are actually used?
    unique_patterns = np.unique(patterns, axis=0)
    capacity = np.log2(max(len(unique_patterns), 1))

    return SemanticMapping(
        projection_matrix=W,
        quantizer=quantizer,
        embedding_dim=d_emb,
        n_sites=n_sites,
        n_modes=n_modes,
        alphabet_size=alphabet_size,
        similarity_preservation=float(pearson),
        distortion=float(distortion),
        capacity_bits=float(capacity),
    )


# ═══════════════════════════════════════════════════════════════════════
# Decoding — fingerprint → symbol
# ═══════════════════════════════════════════════════════════════════════

def decode_fingerprint(
    measured_fingerprint: np.ndarray,
    codebook: Codebook,
    sensitivity_matrix: np.ndarray,
) -> DecodingResult:
    """
    Decode a measured spectral fingerprint back to the nearest symbol.

    Uses maximum-likelihood decoding: find the codebook entry whose
    expected fingerprint is closest (in L2) to the measurement.

    Parameters
    ----------
    measured_fingerprint : ndarray, shape (n_modes,)
        Measured spectral shift vector.
    codebook : Codebook
        The codebook to decode against.
    sensitivity_matrix : ndarray, shape (n_modes, n_sites)
        The sensitivity matrix (used for residual computation).

    Returns
    -------
    DecodingResult
    """
    dists = np.linalg.norm(codebook.fingerprints - measured_fingerprint, axis=1)

    best_idx = np.argmin(dists)
    sorted_dists = np.sort(dists)
    confidence = sorted_dists[1] / (sorted_dists[0] + 1e-30) if len(sorted_dists) > 1 else np.inf

    # Residual: how well does the best match explain the measurement?
    mass_values = np.arange(codebook.alphabet_size, dtype=float)
    expected = sensitivity_matrix @ mass_values[codebook.mass_patterns[best_idx]]
    residual = np.linalg.norm(measured_fingerprint - expected)

    return DecodingResult(
        decoded_symbol=codebook.symbols[best_idx],
        decoded_pattern=codebook.mass_patterns[best_idx],
        confidence=float(confidence),
        residual=float(residual),
        n_candidates=len(codebook.symbols),
    )


# ═══════════════════════════════════════════════════════════════════════
# Similarity analysis
# ═══════════════════════════════════════════════════════════════════════

def analyze_similarity_preservation(
    embeddings: np.ndarray,
    fingerprints: np.ndarray,
) -> SimilarityAnalysis:
    """
    Analyze how well spectral similarity tracks semantic similarity.

    This is the critical metric for associative recall: if two concepts
    are semantically similar, their spectral fingerprints must also be
    similar, so that wave-interference recall naturally retrieves
    related concepts.

    Parameters
    ----------
    embeddings : ndarray, shape (n_items, d_emb)
        Embedding vectors.
    fingerprints : ndarray, shape (n_items, n_modes)
        Corresponding spectral fingerprints.

    Returns
    -------
    SimilarityAnalysis
    """
    n = len(embeddings)

    # Cosine similarities
    E_n = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-30)
    F_n = fingerprints / (np.linalg.norm(fingerprints, axis=1, keepdims=True) + 1e-30)

    upper = np.triu_indices(n, k=1)
    G_emb = (E_n @ E_n.T)[upper]
    G_spec = (F_n @ F_n.T)[upper]

    n_pairs = len(G_emb)

    # Pearson correlation
    pearson = float(np.corrcoef(G_emb, G_spec)[0, 1]) if n_pairs > 1 else 0.0

    # Spearman rank correlation
    from scipy.stats import spearmanr
    spearman, _ = spearmanr(G_emb, G_spec) if n_pairs > 1 else (0.0, 1.0)

    # Monotonicity violations: pairs where embedding order ≠ spectral order
    violations = 0
    # Sample pairs to check (full check is O(n_pairs²))
    n_check = min(n_pairs, 10_000)
    rng = np.random.default_rng(42)
    if n_pairs > n_check:
        idx = rng.choice(n_pairs, n_check, replace=False)
    else:
        idx = np.arange(n_pairs)

    for i in range(len(idx)):
        for j in range(i + 1, min(i + 50, len(idx))):
            ii, jj = idx[i], idx[j]
            emb_order = G_emb[ii] > G_emb[jj]
            spec_order = G_spec[ii] > G_spec[jj]
            if emb_order != spec_order:
                violations += 1

    total_checked = sum(min(50, len(idx) - i - 1) for i in range(len(idx) - 1))
    violation_rate = violations / max(total_checked, 1)

    return SimilarityAnalysis(
        n_pairs=n_pairs,
        embedding_similarities=G_emb,
        spectral_similarities=G_spec,
        rank_correlation=float(spearman),
        linear_correlation=pearson,
        monotonicity_violations=violations,
        violation_rate=violation_rate,
    )


# ═══════════════════════════════════════════════════════════════════════
# Level 3 — Compositional encoding (rod arrays)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class CompositionalEncoding:
    """Encoding of structured data across multiple rods."""
    n_rods: int
    roles: List[str]           # semantic roles (e.g., "subject", "verb", "object")
    patterns_per_rod: List[np.ndarray]  # mass pattern for each rod
    fingerprints_per_rod: List[np.ndarray]
    combined_fingerprint: np.ndarray    # concatenation of all rod fingerprints
    total_bits: float


def encode_compositional(
    role_embeddings: Dict[str, np.ndarray],
    sensitivity_matrix: np.ndarray,
    alphabet_size: int = 2,
) -> CompositionalEncoding:
    """
    Encode a structured representation across multiple rods.

    Each role (subject, verb, object, etc.) gets its own rod.
    The combined fingerprint is the concatenation.

    Parameters
    ----------
    role_embeddings : dict
        Maps role names to embedding vectors.
    sensitivity_matrix : ndarray
        Shared sensitivity matrix (same rod geometry).
    alphabet_size : int
        Mass levels per site.

    Returns
    -------
    CompositionalEncoding
    """
    roles = list(role_embeddings.keys())
    n_rods = len(roles)
    n_modes, n_sites = sensitivity_matrix.shape
    mass_values = np.arange(alphabet_size, dtype=float)

    patterns = []
    fingerprints = []

    for role in roles:
        emb = role_embeddings[role]
        # Simple projection: SVD truncation + quantization
        if len(emb) > n_sites:
            # Truncate to n_sites dimensions
            emb_trunc = emb[:n_sites]
        else:
            emb_trunc = np.pad(emb, (0, n_sites - len(emb)))

        # Scale to [0, alphabet_size-1]
        e_min, e_max = emb_trunc.min(), emb_trunc.max()
        e_range = e_max - e_min + 1e-30
        scaled = (emb_trunc - e_min) / e_range * (alphabet_size - 1)
        pattern = np.clip(np.round(scaled), 0, alphabet_size - 1).astype(int)

        fp = sensitivity_matrix @ mass_values[pattern]
        patterns.append(pattern)
        fingerprints.append(fp)

    combined = np.concatenate(fingerprints)
    total_bits = n_rods * np.log2(alphabet_size) * n_sites

    return CompositionalEncoding(
        n_rods=n_rods,
        roles=roles,
        patterns_per_rod=patterns,
        fingerprints_per_rod=fingerprints,
        combined_fingerprint=combined,
        total_bits=float(total_bits),
    )
