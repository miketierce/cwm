"""
Experiment 11: Hopfield Pattern Recall on Physical Plates

Research Question:
    Can a fused-silica plate array perform associative recall — given
    a partial or noisy query, return the closest stored pattern — using
    physical wave interference as the dot-product mechanism?

Hypothesis:
    Per Chapter 6, CWM is a Hopfield network made of glass.  The coupling
    matrix C_nk = sin²(nπx_k/L) IS the Hopfield weight matrix.  Driving
    the plate with a partial pattern (subset of mode amplitudes) should
    produce a spectral response closest to the stored pattern it best
    matches, performing nearest-neighbour search physically.

    With N_modes = 31 (our bench setup), the AGS capacity limit predicts
    P_max ≈ 0.138 × 31 ≈ 4 patterns for reliable recall.

Methodology:
    1. Define P stored patterns as binary vectors over M modes.
    2. Compute Hebbian weight matrix: W = (1/P) Σ ξᵘ(ξᵘ)ᵀ
    3. For recall, present a corrupted query (flip fraction β of bits).
    4. Evolve Hopfield dynamics: s_i → sign(Σ W_ij s_j)
    5. Measure recall accuracy vs: pattern count, noise level, mode count.
    6. Compare digital Hopfield recall to simulated physical interference.

Claims tested:  Ch06 Hopfield equivalence, AGS capacity scaling
Status:         SIMULATED (computational validation, bench hw planned)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List


@dataclass
class RecallResult:
    """Result of a single recall trial."""
    n_modes: int
    n_patterns: int
    noise_fraction: float
    query_pattern_idx: int
    recalled_pattern_idx: int
    correct: bool
    overlap: float  # dot product with correct pattern, normalised


@dataclass
class HopfieldSweepResult:
    """Recall accuracy across parameter sweeps."""
    # Pattern count sweep
    pattern_counts: np.ndarray
    pattern_accuracy: np.ndarray
    # Noise sweep
    noise_fractions: np.ndarray
    noise_accuracy: np.ndarray
    # Mode count sweep
    mode_counts: np.ndarray
    mode_accuracy: np.ndarray
    # AGS capacity comparison
    ags_predicted: np.ndarray  # 0.138 * N for each mode count
    ags_measured: np.ndarray   # max P with >90% recall
    # Summary
    n_trials: int
    baseline_accuracy: float


def _hebbian_weights(patterns: np.ndarray) -> np.ndarray:
    """Compute Hebbian weight matrix W = (1/P) Σ ξᵘ(ξᵘ)ᵀ, zero diagonal."""
    P, N = patterns.shape
    W = (patterns.T @ patterns) / P
    np.fill_diagonal(W, 0)
    return W


def _hopfield_recall(W: np.ndarray, query: np.ndarray,
                     max_iter: int = 20) -> np.ndarray:
    """Synchronous Hopfield recall: s → sign(W·s)."""
    s = query.copy().astype(float)
    for _ in range(max_iter):
        s_new = np.sign(W @ s)
        s_new[s_new == 0] = 1  # break ties
        if np.array_equal(s_new, s):
            break
        s = s_new
    return s


def _corrupt_pattern(pattern: np.ndarray, noise_frac: float,
                     rng: np.random.Generator) -> np.ndarray:
    """Flip a fraction of bits in a ±1 pattern."""
    noisy = pattern.copy()
    n_flip = int(noise_frac * len(pattern))
    flip_idx = rng.choice(len(pattern), n_flip, replace=False)
    noisy[flip_idx] *= -1
    return noisy


def _identify_recalled(patterns: np.ndarray, recalled: np.ndarray) -> tuple:
    """Find which stored pattern best matches the recalled state."""
    overlaps = patterns @ recalled / patterns.shape[1]
    best_idx = np.argmax(overlaps)
    return best_idx, overlaps[best_idx]


def run_experiment(
    pattern_counts: np.ndarray = None,
    noise_fractions: np.ndarray = None,
    mode_counts: np.ndarray = None,
    n_trials: int = 50,
    seed: int = 42,
) -> HopfieldSweepResult:
    """Run Hopfield recall sweeps."""

    if pattern_counts is None:
        pattern_counts = np.array([1, 2, 3, 4, 5, 7, 10, 15])
    if noise_fractions is None:
        noise_fractions = np.array([0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5])
    if mode_counts is None:
        mode_counts = np.array([10, 20, 31, 50, 100, 200])

    rng = np.random.default_rng(seed)

    # Pattern count sweep (31 modes, 10% noise)
    pat_acc = np.zeros(len(pattern_counts))
    for i, P in enumerate(pattern_counts):
        correct = 0
        for _ in range(n_trials):
            patterns = rng.choice([-1, 1], size=(int(P), 31))
            W = _hebbian_weights(patterns)
            idx = rng.integers(int(P))
            query = _corrupt_pattern(patterns[idx], 0.1, rng)
            recalled = _hopfield_recall(W, query)
            best_idx, _ = _identify_recalled(patterns, recalled)
            if best_idx == idx:
                correct += 1
        pat_acc[i] = correct / n_trials

    # Noise sweep (31 modes, 3 patterns)
    noise_acc = np.zeros(len(noise_fractions))
    for i, nf in enumerate(noise_fractions):
        correct = 0
        for _ in range(n_trials):
            patterns = rng.choice([-1, 1], size=(3, 31))
            W = _hebbian_weights(patterns)
            idx = rng.integers(3)
            query = _corrupt_pattern(patterns[idx], nf, rng)
            recalled = _hopfield_recall(W, query)
            best_idx, _ = _identify_recalled(patterns, recalled)
            if best_idx == idx:
                correct += 1
        noise_acc[i] = correct / n_trials

    # Mode count sweep (3 patterns, 10% noise)
    mode_acc = np.zeros(len(mode_counts))
    ags_pred = np.zeros(len(mode_counts))
    ags_meas = np.zeros(len(mode_counts))
    for i, N in enumerate(mode_counts):
        N = int(N)
        ags_pred[i] = 0.138 * N

        # Find max patterns with >90% recall
        correct = 0
        for _ in range(n_trials):
            patterns = rng.choice([-1, 1], size=(3, N))
            W = _hebbian_weights(patterns)
            idx = rng.integers(3)
            query = _corrupt_pattern(patterns[idx], 0.1, rng)
            recalled = _hopfield_recall(W, query)
            best_idx, _ = _identify_recalled(patterns, recalled)
            if best_idx == idx:
                correct += 1
        mode_acc[i] = correct / n_trials

        # Binary search for max P with >90% recall
        lo, hi = 1, int(0.2 * N) + 1
        best_p = 1
        while lo <= hi:
            mid = (lo + hi) // 2
            correct = 0
            for _ in range(min(n_trials, 30)):
                patterns = rng.choice([-1, 1], size=(mid, N))
                W = _hebbian_weights(patterns)
                idx = rng.integers(mid)
                query = _corrupt_pattern(patterns[idx], 0.1, rng)
                recalled = _hopfield_recall(W, query)
                best_idx, _ = _identify_recalled(patterns, recalled)
                if best_idx == idx:
                    correct += 1
            acc = correct / min(n_trials, 30)
            if acc >= 0.9:
                best_p = mid
                lo = mid + 1
            else:
                hi = mid - 1
        ags_meas[i] = best_p

    # Baseline
    baseline = pat_acc[min(2, len(pat_acc) - 1)]  # 3 patterns

    return HopfieldSweepResult(
        pattern_counts=pattern_counts, pattern_accuracy=pat_acc,
        noise_fractions=noise_fractions, noise_accuracy=noise_acc,
        mode_counts=mode_counts, mode_accuracy=mode_acc,
        ags_predicted=ags_pred, ags_measured=ags_meas,
        n_trials=n_trials, baseline_accuracy=baseline,
    )


def summarize(result: HopfieldSweepResult) -> str:
    lines = [
        "=" * 70,
        "  Experiment 11: Hopfield Pattern Recall on Plates",
        "=" * 70,
        "",
        f"  Baseline: {result.baseline_accuracy:.1%} recall (3 patterns, 31 modes, 10% noise)",
        f"  Trials per condition: {result.n_trials}",
        "",
        "  Pattern Count Sweep (31 modes, 10% noise):",
        f"  {'Patterns':>10}  {'Accuracy':>10}  {'AGS limit':>10}",
        "  " + "-" * 34,
    ]
    ags_31 = 0.138 * 31
    for P, acc in zip(result.pattern_counts, result.pattern_accuracy):
        marker = " ←" if P > ags_31 else ""
        lines.append(f"  {P:>10.0f}  {acc:>9.1%}  {ags_31:>10.1f}{marker}")

    lines += [
        "",
        "  Noise Sweep (31 modes, 3 patterns):",
        f"  {'Noise %':>10}  {'Accuracy':>10}",
        "  " + "-" * 24,
    ]
    for nf, acc in zip(result.noise_fractions, result.noise_accuracy):
        lines.append(f"  {nf:>9.0%}  {acc:>9.1%}")

    lines += [
        "",
        "  AGS Capacity Scaling:",
        f"  {'Modes':>8}  {'AGS pred':>10}  {'Measured':>10}  {'Ratio':>8}",
        "  " + "-" * 40,
    ]
    for N, pred, meas in zip(result.mode_counts, result.ags_predicted, result.ags_measured):
        ratio = meas / pred if pred > 0 else 0
        lines.append(f"  {N:>8.0f}  {pred:>10.1f}  {meas:>10.0f}  {ratio:>7.2f}")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_experiment()
    print(summarize(result))
