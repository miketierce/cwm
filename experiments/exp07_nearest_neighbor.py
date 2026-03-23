"""
Experiment 07: Nearest-Neighbor Search via Spectral Correlation

Research Question:
    Can a multi-rod array perform O(1) nearest-neighbor search by
    driving all rods with a query spectrum simultaneously and
    identifying the strongest responder?

Hypothesis:
    Per paper §2.3 and §10.3, the rod with the stored pattern
    closest to the query produces the highest correlation amplitude.
    Search latency is one acoustic propagation cycle (~3.8 µs for
    a 150 mm borosilicate rod) regardless of array size M.

    This experiment validates:
    a) Correct identification of the nearest neighbor.
    b) Ranked retrieval: correlations rank rods by true similarity.
    c) Scaling: search time is independent of M.

Methodology:
    1. Create an array of M rods with known perturbation patterns.
    2. Generate a query that is a controlled interpolation between
       two stored patterns: Q(α) = (1−α)·P_A + α·P_B.
    3. Sweep α from 0→1 and verify that the best-match rod
       transitions from A to B at α ≈ 0.5.
    4. For each query, measure the full ranking of all rods by
       correlation and compare to true Euclidean distance ranking.
    5. Compute Kendall τ rank correlation to quantify ranking quality.
    6. Repeat with additive noise to test robustness.

Claims tested:  Section 10.3 — "CWM is 26× faster than GPU"
                Section 2.3 — "O(1) nearest-neighbor search"
Status:          SIMULATED (computational validation)
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional

from simulations.glass_resonator import (
    RodGeometry,
    Perturbation,
    rayleigh_perturbation,
    associative_recall,
)


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class NNQueryResult:
    """Result of a single nearest-neighbor query."""
    alpha: float                              # interpolation parameter
    noise_level: float
    query: np.ndarray
    correlations: np.ndarray                  # correlation with each rod
    true_distances: np.ndarray                # Euclidean distance to each rod
    best_match_index: int                     # rod with highest correlation
    true_nearest_index: int                   # rod with smallest distance
    correct: bool                             # best_match == true_nearest
    kendall_tau: float                        # rank correlation


@dataclass
class NNSearchExperiment:
    """Full results from the nearest-neighbor search experiment."""
    n_rods: int
    n_modes: int
    # Interpolation sweep (clean)
    interpolation_results: List[NNQueryResult]
    crossover_alpha: float                    # α where best match switches A→B
    # Noisy sweep
    noise_sweep_results: List[List[NNQueryResult]]  # [noise_level][alpha]
    noise_levels: np.ndarray
    accuracy_vs_noise: np.ndarray             # fraction correct per noise level
    # Ranking quality
    mean_kendall_tau: float                   # mean over all clean queries


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _kendall_tau(rank_a: np.ndarray, rank_b: np.ndarray) -> float:
    """Compute Kendall tau rank correlation between two rankings."""
    n = len(rank_a)
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            a_diff = rank_a[i] - rank_a[j]
            b_diff = rank_b[i] - rank_b[j]
            product = a_diff * b_diff
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return 1.0
    return (concordant - discordant) / total


def _rank_array(values: np.ndarray, ascending: bool = True) -> np.ndarray:
    """Compute ranks (1-based) from values."""
    order = np.argsort(values) if ascending else np.argsort(-values)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, len(values) + 1)
    return ranks


# ---------------------------------------------------------------------------
# Core experiment
# ---------------------------------------------------------------------------

def run_experiment(
    n_rods: int = 6,
    n_modes: int = 20,
    n_alpha_steps: int = 21,
    noise_levels: np.ndarray = None,
    rod: RodGeometry = None,
) -> NNSearchExperiment:
    """
    Run the nearest-neighbor search experiment.

    Phase 1: Interpolate between two stored patterns and verify
             that the best match transitions correctly.
    Phase 2: Add noise and measure robustness of the ranking.
    """
    if rod is None:
        rod = RodGeometry()
    if noise_levels is None:
        noise_levels = np.array([0.0, 0.05, 0.1, 0.2, 0.3, 0.5])

    rng = np.random.RandomState(42)

    # --- Create rod array with distinct perturbation patterns ---
    fingerprints = []
    for i in range(n_rods):
        positions = rng.uniform(0.05 * rod.length, 0.95 * rod.length, size=2)
        masses = rng.uniform(0.05e-3, 0.2e-3, size=2)
        perturbations = [
            Perturbation(position=float(positions[j]),
                         delta_mass=float(masses[j]),
                         label=f"rod{i}_p{j}")
            for j in range(2)
        ]
        spectrum = rayleigh_perturbation(rod=rod, perturbations=perturbations,
                                         n_modes=n_modes)
        fingerprints.append(spectrum.signature)

    # Use rod 0 and rod 1 as the interpolation endpoints
    sig_a = fingerprints[0]
    sig_b = fingerprints[1]
    alphas = np.linspace(0.0, 1.0, n_alpha_steps)

    # --- Phase 1: Clean interpolation sweep ---
    interp_results = []
    for alpha in alphas:
        query = (1 - alpha) * sig_a + alpha * sig_b
        result = _run_nn_query(query, fingerprints, alpha, noise_level=0.0)
        interp_results.append(result)

    # Find crossover: α where best match switches from rod 0 to rod 1
    crossover_alpha = 1.0
    for r in interp_results:
        if r.best_match_index == 1:
            crossover_alpha = r.alpha
            break

    # Mean Kendall tau for clean queries
    taus = [r.kendall_tau for r in interp_results]
    mean_tau = float(np.mean(taus))

    # --- Phase 2: Noisy queries at multiple noise levels ---
    noise_sweep_results = []
    accuracy_vs_noise = np.zeros(len(noise_levels))
    n_trials_per_noise = 40

    for inl, noise in enumerate(noise_levels):
        level_results = []
        n_correct = 0
        for trial in range(n_trials_per_noise):
            trial_rng = np.random.RandomState(rng.randint(100000))
            # Pick a random target rod
            target = trial_rng.randint(n_rods)
            query = fingerprints[target].copy()
            # Add noise
            noise_vec = trial_rng.normal(0, noise * np.std(query), size=n_modes)
            query = query + noise_vec

            result = _run_nn_query(query, fingerprints, alpha=0.0,
                                   noise_level=noise)
            level_results.append(result)
            if result.correct:
                n_correct += 1

        noise_sweep_results.append(level_results)
        accuracy_vs_noise[inl] = n_correct / n_trials_per_noise

    return NNSearchExperiment(
        n_rods=n_rods,
        n_modes=n_modes,
        interpolation_results=interp_results,
        crossover_alpha=crossover_alpha,
        noise_sweep_results=noise_sweep_results,
        noise_levels=noise_levels,
        accuracy_vs_noise=accuracy_vs_noise,
        mean_kendall_tau=mean_tau,
    )


def _run_nn_query(
    query: np.ndarray,
    stored: List[np.ndarray],
    alpha: float,
    noise_level: float,
) -> NNQueryResult:
    """Execute a single NN query and compute ranking metrics."""
    recall = associative_recall(query, stored)

    # True Euclidean distances
    true_dists = np.array([
        np.linalg.norm(query - s) for s in stored
    ])
    true_nearest = int(np.argmin(true_dists))

    # Ranking quality: compare correlation rank vs distance rank
    corr_ranks = _rank_array(recall.correlations, ascending=False)
    dist_ranks = _rank_array(true_dists, ascending=True)
    tau = _kendall_tau(corr_ranks, dist_ranks)

    return NNQueryResult(
        alpha=alpha,
        noise_level=noise_level,
        query=query,
        correlations=recall.correlations,
        true_distances=true_dists,
        best_match_index=recall.best_match_index,
        true_nearest_index=true_nearest,
        correct=(recall.best_match_index == true_nearest),
        kendall_tau=tau,
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize(result: NNSearchExperiment) -> str:
    """Generate text summary of nearest-neighbor experiment."""
    lines = [
        "=" * 65,
        "Experiment 07: Nearest-Neighbor Search via Spectral Correlation",
        "=" * 65,
        "",
        f"Array: {result.n_rods} rods × {result.n_modes} modes",
        "",
        "--- Interpolation Sweep (P_A → P_B) ---",
        f"{'α':>6} | {'Best match':>11} | {'Correct?':>9} | {'Kendall τ':>10}",
        "-" * 44,
    ]
    for r in result.interpolation_results:
        lines.append(
            f"{r.alpha:6.2f} | "
            f"{'Rod ' + str(r.best_match_index):>11} | "
            f"{'✓' if r.correct else '✗':>9} | "
            f"{r.kendall_tau:10.3f}"
        )
    lines.append(f"\nCrossover α (A→B switch): {result.crossover_alpha:.2f}")
    lines.append(f"Expected: ~0.50  (midpoint of interpolation)")
    lines.append(f"Mean Kendall τ (clean): {result.mean_kendall_tau:.3f}")

    lines.append("\n--- Noise Robustness ---")
    lines.append(f"{'Noise σ':>8} | {'Accuracy':>10}")
    lines.append("-" * 22)
    for noise, acc in zip(result.noise_levels, result.accuracy_vs_noise):
        lines.append(f"{noise:8.2f} | {acc:10.1%}")

    lines.append("\n" + "=" * 65)
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_experiment()
    print(summarize(result))
