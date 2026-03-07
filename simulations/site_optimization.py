"""
Perturbation Site Placement Optimization for SEM.

Given a glass rod with n_max resolvable eigenmodes, this module answers:
    1. Where should K discrete mass-perturbation sites be placed?
    2. Binary (0/1) or trinary (0/m₁/m₂) — which encodes more?
    3. How many distinct data words can be reliably written and read back?
    4. What is the condition number of the resulting sensitivity matrix?

The core object is the *sensitivity matrix* S ∈ ℝ^{N×K}, where:
    S[n,k] = sin²(n π xₖ / L)

Each column is mode n's response to a unit mass at site k.
Each row is site k's "fingerprint" across all modes.

The quality of a site layout is determined by:
    - Rank of S (how many independent degrees of freedom)
    - Condition number of S (numerical robustness of inversion)
    - Minimum Hamming distance between distinct fingerprints
    - Mutual coherence μ(S) = max_{i≠j} |⟨s_i, s_j⟩| / (‖s_i‖‖s_j‖)

A well-conditioned S means every distinct mass pattern produces a
*distinguishable* spectral fingerprint, even under noise.

References:
    - Rayleigh, "Theory of Sound" (1877), §91 — perturbation formula
    - Donoho & Elad (2003) — mutual coherence and sparse recovery
    - Welch bound — lower bound on max cross-correlation
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SensitivityMatrix:
    """The N×K Rayleigh sensitivity matrix and its quality metrics."""
    S: np.ndarray               # shape (n_modes, n_sites)
    site_positions: np.ndarray  # fractional positions x_k / L ∈ (0, 1)
    mode_numbers: np.ndarray    # mode indices 1..N
    rank: int                   # numerical rank
    condition_number: float     # σ_max / σ_min (lower is better)
    mutual_coherence: float     # max |⟨s_i, s_j⟩| / norms (lower is better)
    welch_bound: float          # theoretical lower bound on coherence
    singular_values: np.ndarray # full SVD spectrum


@dataclass
class SiteLayout:
    """Optimized perturbation site layout."""
    positions: np.ndarray       # fractional positions ∈ (0, 1)
    n_sites: int
    n_modes: int
    alphabet_size: int          # 2 for binary, 3 for trinary
    sensitivity: SensitivityMatrix
    n_codewords: int            # total possible mass patterns
    distinguishable_words: int  # patterns with unique fingerprints above noise
    bits_encoded: float         # log₂(distinguishable_words)
    bits_per_site: float        # bits_encoded / n_sites
    method: str                 # optimization method used


@dataclass
class PlacementSweep:
    """Results from sweeping number of sites or alphabet size."""
    n_sites_range: np.ndarray
    alphabet_sizes: np.ndarray  # tested alphabet sizes
    bits_per_config: np.ndarray  # shape (len(n_sites), len(alphabets))
    cond_per_config: np.ndarray  # condition numbers
    best_n_sites: int
    best_alphabet: int
    best_bits: float


# ═══════════════════════════════════════════════════════════════════════
# Sensitivity matrix construction
# ═══════════════════════════════════════════════════════════════════════

def build_sensitivity_matrix(
    site_positions: np.ndarray,
    n_modes: int = 100,
) -> SensitivityMatrix:
    """
    Build the Rayleigh sensitivity matrix S[n, k] = sin²(n π x_k / L).

    Parameters
    ----------
    site_positions : array-like
        Fractional positions x_k / L ∈ (0, 1) for each perturbation site.
    n_modes : int
        Number of modes to include (1..n_modes).

    Returns
    -------
    SensitivityMatrix
    """
    positions = np.asarray(site_positions, dtype=float)
    K = len(positions)
    ns = np.arange(1, n_modes + 1)

    # S[n, k] = sin²(n π x_k)
    # Using broadcasting: ns is (N,1), positions is (1,K)
    S = np.sin(ns[:, None] * np.pi * positions[None, :]) ** 2

    # SVD analysis
    U, sigma, Vt = np.linalg.svd(S, full_matrices=False)
    tol = max(S.shape) * sigma[0] * np.finfo(float).eps
    rank = int(np.sum(sigma > tol))
    cond = sigma[0] / sigma[-1] if sigma[-1] > tol else np.inf

    # Mutual coherence: max normalized inner product between column pairs
    # (lower = better; columns are more independent)
    norms = np.linalg.norm(S, axis=0)
    S_normed = S / (norms[None, :] + 1e-30)
    gram = S_normed.T @ S_normed
    np.fill_diagonal(gram, 0.0)
    mu = np.max(np.abs(gram))

    # Welch bound: theoretical minimum coherence for N×K
    N, K = S.shape
    if K > 1:
        welch = np.sqrt((K - N) / (N * (K - 1))) if K > N else 0.0
    else:
        welch = 0.0

    return SensitivityMatrix(
        S=S,
        site_positions=positions,
        mode_numbers=ns,
        rank=rank,
        condition_number=cond,
        mutual_coherence=mu,
        welch_bound=welch,
        singular_values=sigma,
    )


# ═══════════════════════════════════════════════════════════════════════
# Site placement strategies
# ═══════════════════════════════════════════════════════════════════════

def uniform_placement(n_sites: int) -> np.ndarray:
    """
    Equally spaced sites, excluding endpoints (nodes of all modes).

    x_k = (k + 1) / (K + 1),  k = 0, ..., K-1

    This is the simplest layout and the baseline to beat.
    """
    return np.array([(k + 1) / (n_sites + 1) for k in range(n_sites)])


def golden_ratio_placement(n_sites: int) -> np.ndarray:
    """
    Sites at golden-ratio-spaced fractional positions.

    The golden ratio φ = (1+√5)/2 generates the most uniformly
    distributed sequence modulo 1 (Weyl's equidistribution theorem).
    This minimizes clustering and tends to reduce mutual coherence.
    """
    phi = (1 + np.sqrt(5)) / 2
    return np.array([(k * phi) % 1.0 for k in range(1, n_sites + 1)])


def jittered_placement(n_sites: int, jitter: float = 0.1, seed: int = 42) -> np.ndarray:
    """
    Uniform placement with random jitter to break symmetry.

    Jitter breaks the exact symmetry of sin²(nπx) at rational fractions,
    which can cause columns of S to be linearly dependent (e.g., x=0.5
    makes all odd-indexed columns of S identical to x=0.5 minus a sign).
    """
    rng = np.random.default_rng(seed)
    base = uniform_placement(n_sites)
    jit = rng.uniform(-jitter, jitter, size=n_sites) / (n_sites + 1)
    positions = np.clip(base + jit, 0.01, 0.99)
    return np.sort(positions)


def optimize_placement_greedy(
    n_sites: int,
    n_modes: int = 100,
    n_candidates: int = 1000,
    seed: int = 42,
) -> np.ndarray:
    """
    Greedy condition-number optimization.

    Start with a random pool of candidate positions. Add sites one at a
    time, each time choosing the candidate that most reduces the condition
    number of the resulting sensitivity matrix.

    This is a greedy approximation to the NP-hard column-subset selection
    problem, but it works well in practice because the sin² kernel is smooth.
    """
    rng = np.random.default_rng(seed)
    candidates = np.sort(rng.uniform(0.01, 0.99, size=n_candidates))
    ns = np.arange(1, n_modes + 1)

    chosen = []
    remaining = list(range(n_candidates))

    for _ in range(n_sites):
        best_cond = np.inf
        best_idx = remaining[0]

        for idx in remaining:
            trial = chosen + [idx]
            trial_pos = candidates[trial]
            S_trial = np.sin(ns[:, None] * np.pi * trial_pos[None, :]) ** 2
            _, sigma, _ = np.linalg.svd(S_trial, full_matrices=False)
            tol = max(S_trial.shape) * sigma[0] * np.finfo(float).eps
            c = sigma[0] / max(sigma[-1], tol)
            if c < best_cond:
                best_cond = c
                best_idx = idx

        chosen.append(best_idx)
        remaining.remove(best_idx)

    return np.sort(candidates[chosen])


def optimize_placement_gradient(
    n_sites: int,
    n_modes: int = 100,
    n_iters: int = 500,
    lr: float = 1e-3,
    seed: int = 42,
) -> np.ndarray:
    """
    Gradient descent on mutual coherence.

    Minimizes μ(S) = max_{i≠j} |⟨sᵢ, sⱼ⟩| / (‖sᵢ‖‖sⱼ‖)
    using smooth approximation via log-sum-exp of squared correlations.

    Falls back to numerical gradient (finite differences) for robustness.
    """
    rng = np.random.default_rng(seed)
    positions = np.sort(rng.uniform(0.05, 0.95, size=n_sites))
    ns = np.arange(1, n_modes + 1)

    def coherence_cost(pos):
        S = np.sin(ns[:, None] * np.pi * pos[None, :]) ** 2
        norms = np.linalg.norm(S, axis=0)
        S_n = S / (norms[None, :] + 1e-30)
        gram = S_n.T @ S_n
        np.fill_diagonal(gram, 0.0)
        # Smooth max via log-sum-exp
        flat = gram[np.triu_indices_from(gram, k=1)] ** 2
        return np.log(np.sum(np.exp(10.0 * flat))) / 10.0

    eps = 1e-6
    for iteration in range(n_iters):
        cost = coherence_cost(positions)
        grad = np.zeros(n_sites)
        for k in range(n_sites):
            pos_plus = positions.copy()
            pos_plus[k] += eps
            grad[k] = (coherence_cost(pos_plus) - cost) / eps

        positions -= lr * grad
        positions = np.clip(positions, 0.01, 0.99)
        positions = np.sort(positions)

    return positions


# ═══════════════════════════════════════════════════════════════════════
# Fingerprint distinguishability analysis
# ═══════════════════════════════════════════════════════════════════════

def count_distinguishable_words(
    sensitivity: SensitivityMatrix,
    alphabet_size: int = 2,
    noise_floor: float = 1e-3,
) -> Tuple[int, int, float]:
    """
    Enumerate all possible mass patterns and count how many produce
    spectral fingerprints distinguishable above the noise floor.

    Parameters
    ----------
    sensitivity : SensitivityMatrix
        The sensitivity matrix for the layout.
    alphabet_size : int
        Number of mass levels per site (2=binary, 3=trinary).
    noise_floor : float
        Minimum L2 distance between fingerprints to be "distinguishable".
        Expressed as a fraction of the maximum possible shift.

    Returns
    -------
    (total_codewords, distinguishable, bits_encoded)
    """
    K = sensitivity.S.shape[1]
    total = alphabet_size ** K

    if total > 100_000:
        # Too many to enumerate — use sampling estimate
        return _sample_distinguishable(sensitivity, alphabet_size, noise_floor)

    # Generate all codewords
    words = _generate_all_words(K, alphabet_size)

    # Compute fingerprints: F = S @ m (each row of words is a mass vector)
    mass_values = np.arange(alphabet_size, dtype=float)
    fingerprints = []
    for w in words:
        m = mass_values[w]
        fp = sensitivity.S @ m
        fingerprints.append(fp)
    fingerprints = np.array(fingerprints)

    # Normalize
    norms = np.linalg.norm(fingerprints, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-30)

    # Count distinguishable pairs using minimum L2 distance
    # Two words are "confusable" if their fingerprint distance < noise_floor
    n_distinguishable = _count_unique_clusters(fingerprints, noise_floor)

    bits = np.log2(max(n_distinguishable, 1))
    return total, n_distinguishable, bits


def _generate_all_words(K: int, alphabet_size: int) -> np.ndarray:
    """Generate all alphabet_size^K codewords as integer arrays."""
    total = alphabet_size ** K
    words = np.zeros((total, K), dtype=int)
    for i in range(total):
        val = i
        for k in range(K - 1, -1, -1):
            words[i, k] = val % alphabet_size
            val //= alphabet_size
    return words


def _count_unique_clusters(
    fingerprints: np.ndarray,
    threshold: float,
) -> int:
    """
    Count clusters of fingerprints separated by at least `threshold`.

    Uses a KD-tree-style approach: hash fingerprints into coarse bins,
    then only compare within/across adjacent bins.  Falls back to
    greedy scanning for small inputs.
    """
    if len(fingerprints) == 0:
        return 0

    # Normalize the threshold relative to the typical fingerprint magnitude
    scale = np.mean(np.linalg.norm(fingerprints, axis=1))
    abs_threshold = threshold * scale
    if abs_threshold < 1e-30:
        return len(fingerprints)

    # For small sets, direct comparison is fine
    if len(fingerprints) <= 5000:
        centers = [fingerprints[0]]
        for fp in fingerprints[1:]:
            dists = np.linalg.norm(np.array(centers) - fp, axis=1)
            if np.min(dists) > abs_threshold:
                centers.append(fp)
        return len(centers)

    # For large sets: round fingerprints to grid, count unique grid cells
    # This is O(N) instead of O(N²)
    grid = np.round(fingerprints / abs_threshold).astype(np.int32)
    unique_cells = np.unique(grid, axis=0)
    return len(unique_cells)


def _sample_distinguishable(
    sensitivity: SensitivityMatrix,
    alphabet_size: int,
    noise_floor: float,
    n_samples: int = 10_000,
    seed: int = 42,
) -> Tuple[int, int, float]:
    """Estimate distinguishability via random sampling when enumeration is infeasible."""
    K = sensitivity.S.shape[1]
    total = alphabet_size ** K
    rng = np.random.default_rng(seed)

    # Sample random codewords
    words = rng.integers(0, alphabet_size, size=(n_samples, K))
    mass_values = np.arange(alphabet_size, dtype=float)

    fingerprints = np.array([sensitivity.S @ mass_values[w] for w in words])

    n_clusters = _count_unique_clusters(fingerprints, noise_floor)

    # Extrapolate: if we found n_clusters in n_samples, estimate total
    # Using capture-recapture-style estimation
    coverage = n_clusters / n_samples
    estimated_total = int(n_clusters / max(coverage, 1e-6))
    estimated_total = min(estimated_total, total)

    bits = np.log2(max(estimated_total, 1))
    return total, estimated_total, bits


# ═══════════════════════════════════════════════════════════════════════
# Full layout optimizer
# ═══════════════════════════════════════════════════════════════════════

def optimize_layout(
    n_sites: int,
    n_modes: int = 100,
    alphabet_size: int = 2,
    noise_floor: float = 1e-3,
    method: str = "greedy",
) -> SiteLayout:
    """
    Find the best site placement for K perturbation sites.

    Parameters
    ----------
    n_sites : int
        Number of perturbation sites.
    n_modes : int
        Number of resolvable modes to use.
    alphabet_size : int
        Mass levels per site (2=binary, 3=trinary).
    noise_floor : float
        Minimum distinguishable fingerprint distance.
    method : str
        Placement strategy: "uniform", "golden", "jittered",
        "greedy", or "gradient".

    Returns
    -------
    SiteLayout
    """
    if method == "uniform":
        positions = uniform_placement(n_sites)
    elif method == "golden":
        positions = golden_ratio_placement(n_sites)
    elif method == "jittered":
        positions = jittered_placement(n_sites)
    elif method == "greedy":
        positions = optimize_placement_greedy(n_sites, n_modes)
    elif method == "gradient":
        positions = optimize_placement_gradient(n_sites, n_modes)
    else:
        raise ValueError(f"Unknown method: {method}")

    sens = build_sensitivity_matrix(positions, n_modes)
    total, distinguishable, bits = count_distinguishable_words(
        sens, alphabet_size, noise_floor
    )

    return SiteLayout(
        positions=positions,
        n_sites=n_sites,
        n_modes=n_modes,
        alphabet_size=alphabet_size,
        sensitivity=sens,
        n_codewords=total,
        distinguishable_words=distinguishable,
        bits_encoded=bits,
        bits_per_site=bits / n_sites if n_sites > 0 else 0.0,
        method=method,
    )


# ═══════════════════════════════════════════════════════════════════════
# Sweep: vary sites, alphabet, compare strategies
# ═══════════════════════════════════════════════════════════════════════

def sweep_configurations(
    site_range: np.ndarray = None,
    alphabet_sizes: np.ndarray = None,
    n_modes: int = 100,
    noise_floor: float = 1e-3,
    method: str = "greedy",
) -> PlacementSweep:
    """
    Sweep over number of sites and alphabet sizes.

    Parameters
    ----------
    site_range : array-like
        Number of sites to try.
    alphabet_sizes : array-like
        Alphabet sizes to try (e.g., [2, 3] for binary and trinary).
    n_modes : int
        Number of modes.
    noise_floor : float
        Distinguishability threshold.
    method : str
        Placement method.

    Returns
    -------
    PlacementSweep
    """
    if site_range is None:
        site_range = np.arange(2, 17)
    if alphabet_sizes is None:
        alphabet_sizes = np.array([2, 3])

    site_range = np.asarray(site_range, dtype=int)
    alphabet_sizes = np.asarray(alphabet_sizes, dtype=int)

    bits = np.zeros((len(site_range), len(alphabet_sizes)))
    conds = np.zeros_like(bits)

    for i, K in enumerate(site_range):
        for j, a in enumerate(alphabet_sizes):
            layout = optimize_layout(K, n_modes, a, noise_floor, method)
            bits[i, j] = layout.bits_encoded
            conds[i, j] = layout.sensitivity.condition_number

    # Find best overall
    best_idx = np.unravel_index(np.argmax(bits), bits.shape)
    best_k = int(site_range[best_idx[0]])
    best_a = int(alphabet_sizes[best_idx[1]])
    best_b = float(bits[best_idx])

    return PlacementSweep(
        n_sites_range=site_range,
        alphabet_sizes=alphabet_sizes,
        bits_per_config=bits,
        cond_per_config=conds,
        best_n_sites=best_k,
        best_alphabet=best_a,
        best_bits=best_b,
    )


# ═══════════════════════════════════════════════════════════════════════
# Comparative analysis: all strategies head-to-head
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class StrategyComparison:
    """Head-to-head comparison of placement strategies."""
    methods: List[str]
    n_sites: int
    n_modes: int
    alphabet_size: int
    layouts: List[SiteLayout]
    best_method: str
    best_bits: float
    condition_numbers: List[float]
    coherences: List[float]


def compare_strategies(
    n_sites: int = 10,
    n_modes: int = 100,
    alphabet_size: int = 2,
    noise_floor: float = 1e-3,
) -> StrategyComparison:
    """
    Compare all placement strategies head-to-head for a given configuration.

    Returns
    -------
    StrategyComparison
    """
    methods = ["uniform", "golden", "jittered", "greedy", "gradient"]
    layouts = []
    for m in methods:
        layout = optimize_layout(n_sites, n_modes, alphabet_size, noise_floor, m)
        layouts.append(layout)

    bits_list = [l.bits_encoded for l in layouts]
    conds = [l.sensitivity.condition_number for l in layouts]
    cohs = [l.sensitivity.mutual_coherence for l in layouts]

    best_idx = np.argmax(bits_list)

    return StrategyComparison(
        methods=methods,
        n_sites=n_sites,
        n_modes=n_modes,
        alphabet_size=alphabet_size,
        layouts=layouts,
        best_method=methods[best_idx],
        best_bits=bits_list[best_idx],
        condition_numbers=conds,
        coherences=cohs,
    )
