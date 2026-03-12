"""
S10 — Johannes Kepler (1571–1630): Harmonic Resonance Ratios
=============================================================

Kepler's *Harmonices Mundi* (1619) described planetary orbital ratios as
musical consonances — harmonic relationships between oscillation frequencies
that form small-integer ratios.  SEM's eigenmode spectrum f_n = n c/(2L) is
inherently harmonic: all modes are exact integer multiples of the fundamental.

Kepler's insight suggests these harmonic relationships can be *exploited*:
consonant mode pairs (simple ratios like 2:1, 3:2, 5:3) may provide
superior sub-channel partitioning for polysemic readout, and the octave
structure (factor-of-2 redundancy) may enable error detection.

Four testable hypotheses:

1. Diatonic partitioning (H-K1)
   Partitioning eigenmodes into consonant groups (based on octave
   relationships: 2:1) produces polysemic sub-channels with >= 30%
   lower inter-channel crosstalk than uniformly-spaced partitioning.

2. Consonance-weighted recall (H-K2)
   Weighting recall contributions by consonance (w_nm = 1/(n+m) for
   ratio n:m) improves noise tolerance by >= 15% vs uniform weighting.

3. Octave equivalence (H-K3)
   Modes separated by factor 2 in frequency carry partially redundant
   spatial information; octave-paired fingerprints correlate with r > 0.5.

4. Harmonic series capacity scaling (H-K4)
   Information per additional mode decreases as ~1/n for the n-th
   harmonic, so total capacity from N harmonics scales as ~ln(N).

References:
  - Kepler, *Harmonices Mundi* (1619)
  - Helmholtz, *On the Sensations of Tone* (1863) — consonance theory
  - Plomp & Levelt, "Tonal Consonance and Critical Bandwidth" (JASA, 1965)
  - Scranton, observations on "harmonic resonance" in creational energetics
  - WCFOMA scranton_dogon §11.5 polysemic readout (+297% capacity)
  - WCFOMA gabor_holographic §11.12 bandwidth ceiling
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DiatonicPartitionResult:
    """H-K1 — Consonant partitioning reduces inter-channel crosstalk."""
    n_modes: int
    n_channels_consonant: int             # number of consonant groups
    n_channels_uniform: int               # matched uniform partition count
    consonant_mean_crosstalk: float       # mean off-diagonal |corr|
    uniform_mean_crosstalk: float
    crosstalk_reduction_pct: float        # (uniform - consonant) / uniform * 100
    consonant_capacity_bits: float        # total polysemic capacity
    uniform_capacity_bits: float
    consonant_groups: List[List[int]]     # mode indices per group
    verdict: bool                         # True if reduction >= 30%


@dataclass
class ConsonanceRecallResult:
    """H-K2 — Consonance-weighted Hopfield recall improves noise tolerance."""
    network_size: int                     # N (number of modes used)
    n_patterns: int                       # P stored patterns
    baseline_accuracy: float              # uniform-weighted recall accuracy
    consonance_accuracy: float            # consonance-weighted recall accuracy
    improvement_pct: float                # (consonance - baseline) / baseline * 100
    noise_fractions: np.ndarray           # noise levels tested
    baseline_curve: np.ndarray            # accuracy at each noise level
    consonance_curve: np.ndarray          # accuracy at each noise level
    mean_noise_improvement_pct: float     # mean improvement across noise levels
    verdict: bool                         # True if mean_noise_improvement >= 15%


@dataclass
class OctaveEquivalenceResult:
    """H-K3 — Octave-paired modes carry partially redundant information."""
    n_octave_pairs: int                   # number of (n, 2n) pairs tested
    mode_pairs: List[Tuple[int, int]]     # the (n, 2n) pairs
    correlations: np.ndarray              # Pearson r for each pair
    mean_correlation: float
    min_correlation: float
    max_correlation: float
    error_detection_rate: float           # fraction of single errors caught
    verdict: bool                         # True if mean_correlation > 0.5


@dataclass
class HarmonicScalingResult:
    """H-K4 — Capacity from N harmonics scales as ~ln(N)."""
    n_values: np.ndarray                  # number of modes: 2, 4, 8, ...
    cumulative_capacity: np.ndarray       # total capacity at each N
    log_fit_r_squared: float              # R² of ln(N) fit
    linear_fit_r_squared: float           # R² of linear fit
    log_coefficient: float                # c in C = c * ln(N) + d
    log_intercept: float
    marginal_capacity: np.ndarray         # bits added by each mode
    marginal_inverse_fit_r_squared: float # R² of 1/n fit to marginals
    verdict: bool                         # True if log R² > linear R²


# ═══════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════

def _golden_positions(K: int) -> np.ndarray:
    """Golden-ratio perturbation site placement, clipped to (0.02, 0.98)."""
    phi = (1 + np.sqrt(5)) / 2
    pos = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    return np.clip(pos, 0.02, 0.98)


def _sensitivity_matrix(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """S[n, k] = sin²(nπx_k).  Shape (n_modes, K)."""
    n = np.arange(1, n_modes + 1)[:, None]   # (N, 1)
    x = positions[None, :]                     # (1, K)
    return np.sin(n * np.pi * x) ** 2          # (N, K)


def _consonance_rating(n: int, m: int) -> float:
    """Consonance between modes n and m: 1/(n+m) for reduced ratio.

    Higher values = more consonant (simpler ratio).
    """
    from math import gcd
    g = gcd(n, m)
    nr, mr = n // g, m // g
    return 1.0 / (nr + mr)


def _partition_by_octaves(n_modes: int) -> List[List[int]]:
    """Group modes by octave equivalence classes.

    Two modes belong to the same group if one is a power-of-2 multiple
    of the other's odd kernel.  E.g. {1,2,4,8,16,32}, {3,6,12,24},
    {5,10,20,40}, {7,14,28}, {9,18,36}, ...

    Returns a list of groups (each group is sorted mode indices, 0-based).
    """
    assigned = set()
    groups: List[List[int]] = []

    for mode_1based in range(1, n_modes + 1):
        if mode_1based in assigned:
            continue
        # Find the odd kernel
        kernel = mode_1based
        while kernel % 2 == 0:
            kernel //= 2
        # Build the group: kernel * 2^k for k = 0, 1, 2, ...
        group = []
        val = kernel
        while val <= n_modes:
            group.append(val - 1)  # 0-based index
            assigned.add(val)
            val *= 2
        groups.append(sorted(group))

    return groups


def _quantise(values: np.ndarray, n_levels: int = 4) -> np.ndarray:
    """Quantise continuous values into n_levels bins."""
    vmin, vmax = values.min(), values.max()
    span = vmax - vmin
    if span < 1e-30:
        return np.zeros(len(values), dtype=int)
    normalised = (values - vmin) / span
    bins = np.clip(np.floor(normalised * n_levels).astype(int), 0, n_levels - 1)
    return bins


def _channel_crosstalk_matrix(
    full_fps: np.ndarray, subsets: List[np.ndarray],
) -> np.ndarray:
    """Compute cross-correlation matrix between channel sub-fingerprints.

    Parameters
    ----------
    full_fps : (n_patterns, n_modes)
    subsets  : list of mode-index arrays

    Returns
    -------
    corr_matrix : (n_ch, n_ch) absolute Pearson r between channel norms
    """
    n_ch = len(subsets)
    # Per-pattern scalar summary per channel: L2 norm of sub-fingerprint
    norms = []
    for subset in subsets:
        sub_fp = full_fps[:, subset]
        norms.append(np.linalg.norm(sub_fp, axis=1))

    corr = np.zeros((n_ch, n_ch))
    for i in range(n_ch):
        for j in range(n_ch):
            if np.std(norms[i]) < 1e-10 or np.std(norms[j]) < 1e-10:
                corr[i, j] = 0.0 if i != j else 1.0
            else:
                corr[i, j] = float(np.abs(np.corrcoef(norms[i], norms[j])[0, 1]))
    return corr


def _partition_capacity(
    full_fps: np.ndarray,
    subsets: List[np.ndarray],
    noise_sigma: float,
    rng: np.random.RandomState,
) -> float:
    """Total polysemic capacity (bits) across channels."""
    total = 0.0
    n_patterns = full_fps.shape[0]
    for subset in subsets:
        sub_fp = full_fps[:, subset]
        q = np.zeros_like(sub_fp, dtype=int)
        for col in range(sub_fp.shape[1]):
            q[:, col] = _quantise(
                sub_fp[:, col] + rng.randn(n_patterns) * noise_sigma, 4
            )
        unique = set()
        for row in range(q.shape[0]):
            unique.add(tuple(q[row]))
        total += np.log2(max(len(unique), 1))
    return total


def _sign_activation(h: float, model: str = "binary") -> float:
    """Hopfield activation function."""
    if model == "binary":
        return 1.0 if h >= 0 else -1.0
    else:
        if h > 0.5:
            return 1.0
        elif h < -0.5:
            return -1.0
        return 0.0


def _create_weighted_hopfield(
    patterns: np.ndarray,
    mode_weights: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Create Hopfield weight matrix with optional per-mode weighting.

    W_ij = (1/N) * Σ_μ patterns[μ,i] * patterns[μ,j] * w_i * w_j
    """
    P, N = patterns.shape
    W = np.zeros((N, N))
    for mu in range(P):
        W += np.outer(patterns[mu], patterns[mu])
    W /= N
    np.fill_diagonal(W, 0.0)

    if mode_weights is not None:
        w_outer = np.outer(mode_weights, mode_weights)
        W *= w_outer

    return W


def _recall_with_weights(
    W: np.ndarray,
    query: np.ndarray,
    target: np.ndarray,
    max_steps: int = 100,
    rng: Optional[np.random.RandomState] = None,
) -> float:
    """Run asynchronous Hopfield recall; return overlap with target."""
    if rng is None:
        rng = np.random.RandomState(0)
    N = len(query)
    state = query.copy().astype(float)

    for _step in range(max_steps):
        old = state.copy()
        order = rng.permutation(N)
        for i in order:
            h_i = W[i] @ state
            state[i] = 1.0 if h_i >= 0 else -1.0
        if np.array_equal(state, old):
            break

    # Overlap = fraction of matching elements
    return float(np.mean(state == target))


def _corrupt_binary(
    pattern: np.ndarray, fraction: float,
    rng: np.random.RandomState,
) -> np.ndarray:
    """Flip a fraction of binary pattern elements."""
    corrupted = pattern.copy()
    N = len(pattern)
    n_flip = max(1, int(fraction * N))
    flip_idx = rng.choice(N, size=n_flip, replace=False)
    corrupted[flip_idx] *= -1
    return corrupted


def _perturbed_frequencies(
    n_modes: int, positions: np.ndarray, masses: np.ndarray,
) -> np.ndarray:
    """Eigenfrequencies of a 1D cavity with mass perturbations.

    f_n(pert) = f_n * (1 - Σ_k m_k * sin²(nπx_k))

    Returns array of shape (n_modes,).
    """
    modes = np.arange(1, n_modes + 1)
    S = _sensitivity_matrix(positions, n_modes)  # (n_modes, K)
    shifts = S @ masses                           # (n_modes,)
    return modes.astype(float) * (1.0 - shifts)


# ═══════════════════════════════════════════════════════════════════════
# H-K1: Diatonic Partitioning
# ═══════════════════════════════════════════════════════════════════════

def exp_diatonic_partition(
    K: int = 8,
    n_modes: int = 40,
    alphabet_size: int = 3,
    n_patterns: int = 50,
    noise_sigma: float = 0.02,
    seed: int = 42,
) -> DiatonicPartitionResult:
    """H-K1: Consonant (octave) partitioning vs uniform partitioning.

    Procedure:
    1. Partition modes into octave-equivalence groups (same odd kernel).
    2. Create a matched uniform partition with the same number of channels.
    3. For random perturbation patterns, compute fingerprints.
    4. Measure mean inter-channel crosstalk (off-diagonal |correlation|).
    5. Measure total polysemic capacity per partition scheme.

    Kill: consonant crosstalk >= uniform (no reduction, or reduction < 30%).
    Confirm: consonant crosstalk < uniform by >= 30%.
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(K)
    S = _sensitivity_matrix(positions, n_modes)

    # Consonant partition: octave equivalence classes
    consonant_groups = _partition_by_octaves(n_modes)

    # Filter out very small groups (< 2 modes) by merging into nearest
    # Keep all groups as-is for purity — even singletons are valid channels
    n_ch = len(consonant_groups)

    # Uniform partition with same channel count
    uniform_subsets = [
        np.array(s) for s in np.array_split(np.arange(n_modes), n_ch)
    ]
    consonant_subsets = [np.array(g) for g in consonant_groups]

    # Generate random patterns and fingerprints
    patterns = rng.randint(0, alphabet_size, size=(n_patterns, K)).astype(float)
    full_fps = patterns @ S.T  # (n_patterns, n_modes)

    # Cross-correlation matrices
    cons_corr = _channel_crosstalk_matrix(full_fps, consonant_subsets)
    unif_corr = _channel_crosstalk_matrix(full_fps, uniform_subsets)

    # Mean off-diagonal |correlation|
    def _mean_offdiag(M: np.ndarray) -> float:
        n = M.shape[0]
        vals = []
        for i in range(n):
            for j in range(n):
                if i != j:
                    vals.append(abs(M[i, j]))
        return float(np.mean(vals)) if vals else 0.0

    cons_xt = _mean_offdiag(cons_corr)
    unif_xt = _mean_offdiag(unif_corr)

    reduction = (
        (unif_xt - cons_xt) / max(unif_xt, 1e-30) * 100
    )

    # Capacity
    rng_cap = np.random.RandomState(seed + 1)
    cons_cap = _partition_capacity(full_fps, consonant_subsets, noise_sigma, rng_cap)
    rng_cap2 = np.random.RandomState(seed + 1)
    unif_cap = _partition_capacity(full_fps, uniform_subsets, noise_sigma, rng_cap2)

    return DiatonicPartitionResult(
        n_modes=n_modes,
        n_channels_consonant=n_ch,
        n_channels_uniform=n_ch,
        consonant_mean_crosstalk=cons_xt,
        uniform_mean_crosstalk=unif_xt,
        crosstalk_reduction_pct=reduction,
        consonant_capacity_bits=cons_cap,
        uniform_capacity_bits=unif_cap,
        consonant_groups=[list(g) for g in consonant_groups],
        verdict=bool(reduction >= 30.0),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-K2: Consonance-Weighted Recall
# ═══════════════════════════════════════════════════════════════════════

def exp_consonance_recall(
    N: int = 30,
    P: int = 4,
    noise_fractions: Optional[np.ndarray] = None,
    n_trials: int = 20,
    seed: int = 42,
) -> ConsonanceRecallResult:
    """H-K2: Consonance-weighted Hopfield recall vs uniform.

    Procedure:
    1. Generate P random binary patterns of length N.
    2. Build uniform-weighted Hopfield network.
    3. Build consonance-weighted network: w_nm = 1/(n'+m') for
       reduced ratio of mode indices n:m.
    4. For each noise level, corrupt a stored pattern, attempt recall,
       measure accuracy for both networks.
    5. Compare mean noise tolerance.

    Kill: consonance weighting degrades recall (improvement < 0%).
    Confirm: mean improvement >= 15%.
    """
    if noise_fractions is None:
        noise_fractions = np.array([0.05, 0.10, 0.15, 0.20, 0.25, 0.30])

    rng = np.random.RandomState(seed)

    # Generate random binary patterns
    patterns = rng.choice([-1, 1], size=(P, N)).astype(float)

    # Uniform Hopfield weights
    W_uniform = _create_weighted_hopfield(patterns)

    # Consonance weights: mode i corresponds to mode index (i+1)
    # w_i = sum of consonance ratings with all other modes
    cons_weights = np.ones(N)
    for i in range(N):
        total_cons = 0.0
        for j in range(N):
            if i != j:
                total_cons += _consonance_rating(i + 1, j + 1)
        cons_weights[i] = total_cons
    # Normalise so mean = 1
    cons_weights /= cons_weights.mean()

    W_consonance = _create_weighted_hopfield(patterns, cons_weights)

    baseline_curve = np.zeros(len(noise_fractions))
    consonance_curve = np.zeros(len(noise_fractions))

    for ni, nf in enumerate(noise_fractions):
        base_correct = 0
        cons_correct = 0
        for trial in range(n_trials):
            trial_rng = np.random.RandomState(seed + 1000 * ni + trial)
            target_idx = trial_rng.randint(P)
            query = _corrupt_binary(patterns[target_idx], nf, trial_rng)

            ov_base = _recall_with_weights(
                W_uniform, query, patterns[target_idx],
                rng=np.random.RandomState(seed + 2000 * ni + trial),
            )
            ov_cons = _recall_with_weights(
                W_consonance, query, patterns[target_idx],
                rng=np.random.RandomState(seed + 2000 * ni + trial),
            )
            if ov_base > 0.95:
                base_correct += 1
            if ov_cons > 0.95:
                cons_correct += 1

        baseline_curve[ni] = base_correct / n_trials
        consonance_curve[ni] = cons_correct / n_trials

    mean_base = float(np.mean(baseline_curve))
    mean_cons = float(np.mean(consonance_curve))
    improvement = (
        (mean_cons - mean_base) / max(mean_base, 1e-30) * 100
    )

    return ConsonanceRecallResult(
        network_size=N,
        n_patterns=P,
        baseline_accuracy=mean_base,
        consonance_accuracy=mean_cons,
        improvement_pct=improvement,
        noise_fractions=noise_fractions,
        baseline_curve=baseline_curve,
        consonance_curve=consonance_curve,
        mean_noise_improvement_pct=improvement,
        verdict=bool(improvement >= 15.0),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-K3: Octave Equivalence
# ═══════════════════════════════════════════════════════════════════════

def exp_octave_equivalence(
    K: int = 8,
    n_modes: int = 40,
    n_patterns: int = 200,
    alphabet_size: int = 3,
    seed: int = 42,
) -> OctaveEquivalenceResult:
    """H-K3: Modes n and 2n carry partially redundant spatial information.

    Procedure:
    1. Place K perturbation sites at golden-ratio positions.
    2. Build sensitivity matrix for n_modes modes.
    3. Generate many random perturbation patterns.
    4. For each (n, 2n) pair, compute mode-n response and mode-2n response
       across all patterns, measure Pearson correlation.
    5. Test error detection: for each pattern, flip one site, check if
       octave-pair discrepancy flags the error.

    Kill: mean octave-pair correlation < 0.3.
    Confirm: mean correlation > 0.5.
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(K)
    S = _sensitivity_matrix(positions, n_modes)  # (n_modes, K)

    # Identify octave pairs: (n, 2n) where 2n <= n_modes
    pairs = []
    for n in range(1, n_modes + 1):
        if 2 * n <= n_modes:
            pairs.append((n, 2 * n))

    # Generate random patterns
    patterns = rng.randint(0, alphabet_size, size=(n_patterns, K)).astype(float)
    full_fps = patterns @ S.T  # (n_patterns, n_modes)

    # Compute correlations for each octave pair
    correlations = np.zeros(len(pairs))
    for pi, (n, n2) in enumerate(pairs):
        resp_n = full_fps[:, n - 1]     # 0-indexed
        resp_2n = full_fps[:, n2 - 1]
        if np.std(resp_n) < 1e-10 or np.std(resp_2n) < 1e-10:
            correlations[pi] = 0.0
        else:
            correlations[pi] = float(np.corrcoef(resp_n, resp_2n)[0, 1])

    # Error detection test
    n_detect_trials = min(n_patterns, 100)
    n_detected = 0
    n_total_errors = 0

    for trial in range(n_detect_trials):
        orig = patterns[trial].copy()
        fp_orig = orig @ S.T  # (n_modes,)

        # Flip one random site
        flip_site = rng.randint(K)
        corrupted = orig.copy()
        corrupted[flip_site] = (corrupted[flip_site] + 1) % alphabet_size
        fp_corr = corrupted @ S.T

        # For each octave pair, check if the pair detects the error
        for n, n2 in pairs:
            n_total_errors += 1
            delta_n = abs(fp_orig[n - 1] - fp_corr[n - 1])
            delta_2n = abs(fp_orig[n2 - 1] - fp_corr[n2 - 1])
            # If both change by similar amount → consistent → no error flagged
            # If one changes much more → inconsistent → error flagged
            if delta_n > 1e-10 or delta_2n > 1e-10:
                ratio = min(delta_n, delta_2n) / max(delta_n, delta_2n, 1e-30)
                # If ratio is low, the pair shows asymmetric change → flag
                if ratio < 0.5:
                    n_detected += 1

    error_rate = n_detected / max(n_total_errors, 1)

    return OctaveEquivalenceResult(
        n_octave_pairs=len(pairs),
        mode_pairs=pairs,
        correlations=correlations,
        mean_correlation=float(np.mean(correlations)),
        min_correlation=float(np.min(correlations)),
        max_correlation=float(np.max(correlations)),
        error_detection_rate=error_rate,
        verdict=bool(np.mean(correlations) > 0.5),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-K4: Harmonic Series Capacity Scaling
# ═══════════════════════════════════════════════════════════════════════

def exp_harmonic_scaling(
    K: int = 8,
    max_modes: int = 64,
    alphabet_size: int = 3,
    n_patterns: int = 200,
    noise_sigma: float = 0.02,
    seed: int = 42,
) -> HarmonicScalingResult:
    """H-K4: Total capacity scales as ~ln(N) for N harmonic modes.

    Procedure:
    1. For N = 2, 4, 8, 16, 32, 64, build sensitivity matrix.
    2. Generate fixed pattern set, compute fingerprints using N modes.
    3. Measure total capacity (log2 of unique quantised fingerprints).
    4. Fit C(N) to both c*ln(N)+d (logarithmic) and a*N+b (linear).
    5. Compare R² values.
    6. Compute marginal capacity per mode and fit to ~1/n.

    Kill: capacity scales linearly (linear R² > log R² by margin),
          indicating no diminishing returns.
    Confirm: log fit R² > linear fit R².
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(K)

    # Powers of 2 up to max_modes
    n_values = []
    n = 2
    while n <= max_modes:
        n_values.append(n)
        n *= 2
    n_values = np.array(n_values)

    # Generate patterns once (using max K sites)
    patterns = rng.randint(0, alphabet_size, size=(n_patterns, K)).astype(float)

    cumulative_cap = np.zeros(len(n_values))

    for idx, nm in enumerate(n_values):
        S = _sensitivity_matrix(positions, nm)
        full_fps = patterns @ S.T  # (n_patterns, nm)

        # Quantise each mode's response
        q = np.zeros_like(full_fps, dtype=int)
        rng_q = np.random.RandomState(seed + 100 + idx)
        for col in range(full_fps.shape[1]):
            q[:, col] = _quantise(
                full_fps[:, col] + rng_q.randn(n_patterns) * noise_sigma, 4
            )

        # Count unique quantised fingerprints
        unique = set()
        for row in range(q.shape[0]):
            unique.add(tuple(q[row]))
        cumulative_cap[idx] = np.log2(max(len(unique), 1))

    # Fit logarithmic: C = c * ln(N) + d
    log_n = np.log(n_values.astype(float))
    A_log = np.column_stack([log_n, np.ones(len(n_values))])
    coeffs_log, _, _, _ = np.linalg.lstsq(A_log, cumulative_cap, rcond=None)
    pred_log = A_log @ coeffs_log
    ss_res_log = np.sum((cumulative_cap - pred_log) ** 2)
    ss_tot = np.sum((cumulative_cap - np.mean(cumulative_cap)) ** 2)
    r2_log = 1 - ss_res_log / max(ss_tot, 1e-30)

    # Fit linear: C = a * N + b
    A_lin = np.column_stack([n_values.astype(float), np.ones(len(n_values))])
    coeffs_lin, _, _, _ = np.linalg.lstsq(A_lin, cumulative_cap, rcond=None)
    pred_lin = A_lin @ coeffs_lin
    ss_res_lin = np.sum((cumulative_cap - pred_lin) ** 2)
    r2_lin = 1 - ss_res_lin / max(ss_tot, 1e-30)

    # Marginal capacity: Δ bits when adding modes N_{i-1}+1 through N_i
    marginal = np.zeros(len(n_values))
    marginal[0] = cumulative_cap[0]
    for i in range(1, len(n_values)):
        marginal[i] = cumulative_cap[i] - cumulative_cap[i - 1]

    # Fit marginals to ~1/n (using midpoint of each interval)
    mid_n = np.zeros(len(n_values))
    mid_n[0] = n_values[0] / 2.0
    for i in range(1, len(n_values)):
        mid_n[i] = (n_values[i - 1] + n_values[i]) / 2.0
    inv_n = 1.0 / mid_n

    A_inv = np.column_stack([inv_n, np.ones(len(n_values))])
    coeffs_inv, _, _, _ = np.linalg.lstsq(A_inv, marginal, rcond=None)
    pred_inv = A_inv @ coeffs_inv
    ss_res_inv = np.sum((marginal - pred_inv) ** 2)
    ss_tot_m = np.sum((marginal - np.mean(marginal)) ** 2)
    r2_inv = 1 - ss_res_inv / max(ss_tot_m, 1e-30)

    return HarmonicScalingResult(
        n_values=n_values,
        cumulative_capacity=cumulative_cap,
        log_fit_r_squared=float(r2_log),
        linear_fit_r_squared=float(r2_lin),
        log_coefficient=float(coeffs_log[0]),
        log_intercept=float(coeffs_log[1]),
        marginal_capacity=marginal,
        marginal_inverse_fit_r_squared=float(r2_inv),
        verdict=bool(r2_log > r2_lin),
    )


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_kepler(verbose: bool = True) -> dict:
    """Run all S10 Kepler experiments and return results dict."""
    results: dict = {}

    # H-K1
    r1 = exp_diatonic_partition()
    results["H-K1"] = r1
    if verbose:
        print("=" * 60)
        print("H-K1: Diatonic (Octave) Partitioning vs Uniform")
        print("=" * 60)
        print(f"  Consonant channels:     {r1.n_channels_consonant}")
        print(f"  Consonant crosstalk:    {r1.consonant_mean_crosstalk:.4f}")
        print(f"  Uniform crosstalk:      {r1.uniform_mean_crosstalk:.4f}")
        print(f"  Reduction:              {r1.crosstalk_reduction_pct:.1f}%")
        print(f"  Consonant capacity:     {r1.consonant_capacity_bits:.2f} bits")
        print(f"  Uniform capacity:       {r1.uniform_capacity_bits:.2f} bits")
        vstr = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # H-K2
    r2 = exp_consonance_recall()
    results["H-K2"] = r2
    if verbose:
        print("=" * 60)
        print("H-K2: Consonance-Weighted Hopfield Recall")
        print("=" * 60)
        print(f"  Network size:           {r2.network_size}")
        print(f"  Stored patterns:        {r2.n_patterns}")
        print(f"  Baseline accuracy:      {r2.baseline_accuracy:.3f}")
        print(f"  Consonance accuracy:    {r2.consonance_accuracy:.3f}")
        print(f"  Mean improvement:       {r2.mean_noise_improvement_pct:.1f}%")
        vstr = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # H-K3
    r3 = exp_octave_equivalence()
    results["H-K3"] = r3
    if verbose:
        print("=" * 60)
        print("H-K3: Octave Equivalence — Mode n vs 2n Correlation")
        print("=" * 60)
        print(f"  Octave pairs tested:    {r3.n_octave_pairs}")
        print(f"  Mean correlation:       {r3.mean_correlation:.4f}")
        print(f"  Min correlation:        {r3.min_correlation:.4f}")
        print(f"  Max correlation:        {r3.max_correlation:.4f}")
        print(f"  Error detection rate:   {r3.error_detection_rate:.3f}")
        vstr = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # H-K4
    r4 = exp_harmonic_scaling()
    results["H-K4"] = r4
    if verbose:
        print("=" * 60)
        print("H-K4: Harmonic Series Capacity Scaling")
        print("=" * 60)
        print(f"  N values:               {list(r4.n_values)}")
        print(f"  Cumulative capacity:    {[f'{c:.2f}' for c in r4.cumulative_capacity]}")
        print(f"  Log fit R²:             {r4.log_fit_r_squared:.4f}")
        print(f"  Linear fit R²:          {r4.linear_fit_r_squared:.4f}")
        print(f"  Log coefficient:        {r4.log_coefficient:.4f}")
        print(f"  Marginal 1/n fit R²:    {r4.marginal_inverse_fit_r_squared:.4f}")
        vstr = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = len(results) - confirmed
        print("=" * 60)
        print(f"S10 SUMMARY: {confirmed}/4 confirmed, {killed}/4 killed")
        print("=" * 60)

    return results
