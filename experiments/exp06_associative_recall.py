"""
Experiment 06: Associative Recall in a Packed Array

Research Question:
    Can a multi-rod packed array recover stored perturbation patterns
    from noisy or partial queries via spectral correlation — and does
    recall accuracy match Hopfield capacity theory?

Hypothesis:
    Per paper §2.3, driving all rods simultaneously with a query
    spectrum produces a response amplitude R_j = Σ A_n^(j) Q_n at
    each rod j.  The rod with the largest |R_j| is the best match.
    Recall should succeed when the number of stored patterns P is
    below the AGS capacity limit P_max ≈ 0.138 N (N = number of
    modes), and degrade gracefully above it.

Methodology:
    1. Create M virtual rods, each with a unique perturbation pattern
       (distinct mass positions → distinct spectral fingerprints).
    2. Build a query from one rod's fingerprint, corrupt it with noise.
    3. Compute spectral correlation of the query against all M rods.
    4. Determine whether the best-match rod is the correct target.
    5. Sweep noise level (0–50% of bits flipped) to map the basin of
       attraction: how noisy can the query be and still recall?
    6. Sweep array size M to find empirical capacity threshold.

    Parallel track: run the same patterns through a Hopfield network
    (hopfield_recall.py) to confirm rod-correlation recall matches
    Hopfield energy-descent recall.

Claims tested:  Section 2.3 — "Associative recall via wave interference"
                Section 10.3 — "CWM: ~3.8 µs, all patterns in parallel"
Status:          SIMULATED (computational validation)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

from simulations.glass_resonator import (
    RodGeometry,
    Perturbation,
    rayleigh_perturbation,
    associative_recall,
    RecallResult as GlassRecallResult,
)
from simulations.hopfield_recall import (
    create_hopfield_network,
    generate_random_patterns,
    recall_pattern,
    corrupt_pattern,
    measure_capacity,
    measure_basin_of_attraction,
    CapacityResult,
    BasinResult,
)


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class RodFingerprint:
    """A rod's perturbation layout and its resulting spectral signature."""
    rod_index: int
    perturbation_positions: List[float]      # [m]
    perturbation_masses: List[float]          # [kg]
    signature: np.ndarray                     # normalized spectral fingerprint


@dataclass
class ArrayRecallResult:
    """Recall result across a multi-rod array."""
    n_rods: int
    n_modes: int
    noise_fraction: float
    n_trials: int
    recall_accuracy: float                    # fraction of correct identifications
    mean_discrimination_db: float             # mean dB gap between best and 2nd-best
    individual_results: List[GlassRecallResult]


@dataclass
class AssociativeRecallExperiment:
    """Full results from the associative recall experiment."""
    # Physical rod array
    fingerprints: List[RodFingerprint]
    noise_sweep: List[ArrayRecallResult]      # accuracy vs noise
    array_size_sweep: List[ArrayRecallResult]  # accuracy vs M (number of rods)
    # Hopfield comparison
    hopfield_capacity: CapacityResult
    hopfield_basin: BasinResult
    # Summary
    rod_basin_width: float                    # noise where rod recall = 50%
    rod_capacity_threshold: int               # max M at >90% accuracy


# ---------------------------------------------------------------------------
# Rod array creation
# ---------------------------------------------------------------------------

def create_rod_array(
    n_rods: int,
    n_modes: int = 20,
    rod: RodGeometry = None,
    n_perturbations: int = 2,
    rng: Optional[np.random.RandomState] = None,
) -> List[RodFingerprint]:
    """
    Create n_rods virtual rods with distinct random perturbation patterns.

    Each rod gets n_perturbations masses at random positions along the rod,
    producing a unique spectral fingerprint via Rayleigh perturbation.
    """
    if rod is None:
        rod = RodGeometry()
    if rng is None:
        rng = np.random.RandomState(42)

    fingerprints = []
    for i in range(n_rods):
        positions = rng.uniform(0.05 * rod.length, 0.95 * rod.length,
                                size=n_perturbations)
        masses = rng.uniform(0.05e-3, 0.2e-3, size=n_perturbations)

        perturbations = [
            Perturbation(position=float(positions[j]),
                         delta_mass=float(masses[j]),
                         label=f"rod{i}_p{j}")
            for j in range(n_perturbations)
        ]

        spectrum = rayleigh_perturbation(rod=rod, perturbations=perturbations,
                                         n_modes=n_modes)

        fingerprints.append(RodFingerprint(
            rod_index=i,
            perturbation_positions=positions.tolist(),
            perturbation_masses=masses.tolist(),
            signature=spectrum.signature,
        ))

    return fingerprints


# ---------------------------------------------------------------------------
# Noisy query + array-wide recall
# ---------------------------------------------------------------------------

def corrupt_signature(
    signature: np.ndarray,
    noise_fraction: float,
    rng: Optional[np.random.RandomState] = None,
) -> np.ndarray:
    """
    Add noise to a spectral signature by perturbing a fraction of its values.

    Unlike binary bit-flipping, spectral signatures are continuous.
    We add Gaussian noise scaled to the signature's magnitude, then
    zero out a fraction of components (simulating missing mode data).
    """
    if rng is None:
        rng = np.random.RandomState(0)

    noisy = signature.copy()
    n = len(noisy)
    n_corrupt = int(noise_fraction * n)

    if n_corrupt > 0:
        # Zero out random components (partial query)
        mask_idx = rng.choice(n, size=n_corrupt, replace=False)
        noisy[mask_idx] = 0.0

        # Add Gaussian noise to remaining components
        noise = rng.normal(0, noise_fraction * np.std(signature), size=n)
        noisy += noise

    return noisy


def run_array_recall(
    fingerprints: List[RodFingerprint],
    noise_fraction: float = 0.1,
    n_trials: int = 20,
    rng: Optional[np.random.RandomState] = None,
) -> ArrayRecallResult:
    """
    Test recall across a rod array at a given noise level.

    For each trial, pick a random rod, corrupt its signature, and
    check whether spectral correlation identifies it correctly.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    n_rods = len(fingerprints)
    n_modes = len(fingerprints[0].signature)
    stored = [fp.signature for fp in fingerprints]
    n_correct = 0
    discrimination_dbs = []
    results = []

    for trial in range(n_trials):
        target_idx = rng.randint(n_rods)
        query = corrupt_signature(stored[target_idx], noise_fraction,
                                  rng=np.random.RandomState(rng.randint(100000)))

        result = associative_recall(query, stored)
        results.append(result)

        if result.best_match_index == target_idx:
            n_correct += 1

        # Discrimination: gap between best and 2nd-best correlation
        sorted_corr = np.sort(result.correlations)[::-1]
        if len(sorted_corr) >= 2 and sorted_corr[1] > 0:
            ratio = sorted_corr[0] / (sorted_corr[1] + 1e-30)
            discrimination_dbs.append(20 * np.log10(ratio))
        else:
            discrimination_dbs.append(np.inf)

    return ArrayRecallResult(
        n_rods=n_rods,
        n_modes=n_modes,
        noise_fraction=noise_fraction,
        n_trials=n_trials,
        recall_accuracy=n_correct / n_trials,
        mean_discrimination_db=float(np.mean(
            [d for d in discrimination_dbs if np.isfinite(d)]
        )) if discrimination_dbs else 0.0,
        individual_results=results,
    )


# ---------------------------------------------------------------------------
# Main experiment runner
# ---------------------------------------------------------------------------

def run_experiment(
    n_modes: int = 20,
    max_rods: int = 12,
    noise_levels: np.ndarray = None,
    array_sizes: np.ndarray = None,
    n_trials: int = 40,
    rod: RodGeometry = None,
) -> AssociativeRecallExperiment:
    """
    Run the full associative recall experiment.

    Phase 1: Fixed array size, sweep noise level (basin of attraction).
    Phase 2: Fixed noise, sweep array size (capacity curve).
    Phase 3: Run equivalent Hopfield network for comparison.
    """
    if rod is None:
        rod = RodGeometry()
    if noise_levels is None:
        noise_levels = np.linspace(0, 0.5, 11)
    if array_sizes is None:
        array_sizes = np.array([2, 3, 4, 6, 8, 10, 12])

    rng = np.random.RandomState(42)

    # Phase 1: Create the largest array, then subset for sweeps
    all_fingerprints = create_rod_array(max_rods, n_modes, rod,
                                        n_perturbations=2, rng=rng)

    # --- Noise sweep (fixed array size = max_rods) ---
    noise_sweep = []
    for noise in noise_levels:
        result = run_array_recall(all_fingerprints, noise_fraction=noise,
                                  n_trials=n_trials,
                                  rng=np.random.RandomState(rng.randint(100000)))
        noise_sweep.append(result)

    # Basin width: noise where accuracy first drops below 50%
    accuracies_vs_noise = [r.recall_accuracy for r in noise_sweep]
    below_50 = [i for i, a in enumerate(accuracies_vs_noise) if a < 0.5]
    basin_width = float(noise_levels[below_50[0]]) if below_50 else float(noise_levels[-1])

    # --- Array size sweep (fixed noise = 10%) ---
    array_sweep = []
    for m in array_sizes:
        subset = all_fingerprints[:m]
        result = run_array_recall(subset, noise_fraction=0.1,
                                  n_trials=n_trials,
                                  rng=np.random.RandomState(rng.randint(100000)))
        array_sweep.append(result)

    # Capacity: largest M where accuracy >= 90%
    accuracies_vs_size = [r.recall_accuracy for r in array_sweep]
    above_90 = [i for i, a in enumerate(accuracies_vs_size) if a >= 0.9]
    capacity_threshold = int(array_sizes[above_90[-1]]) if above_90 else 0

    # --- Hopfield comparison ---
    hopfield_cap = measure_capacity(N=n_modes, noise_fraction=0.1,
                                    n_trials=n_trials,
                                    rng=np.random.RandomState(42))
    hopfield_basin = measure_basin_of_attraction(N=n_modes, P=5,
                                                  n_trials=n_trials,
                                                  rng=np.random.RandomState(42))

    return AssociativeRecallExperiment(
        fingerprints=all_fingerprints,
        noise_sweep=noise_sweep,
        array_size_sweep=array_sweep,
        hopfield_capacity=hopfield_cap,
        hopfield_basin=hopfield_basin,
        rod_basin_width=basin_width,
        rod_capacity_threshold=capacity_threshold,
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize(result: AssociativeRecallExperiment) -> str:
    """Generate text summary of associative recall experiment."""
    lines = [
        "=" * 65,
        "Experiment 06: Associative Recall in a Packed Array",
        "=" * 65,
        "",
        f"Array: {len(result.fingerprints)} rods × "
        f"{len(result.fingerprints[0].signature)} modes",
        "",
        "--- Noise Sweep (basin of attraction) ---",
        f"{'Noise %':>8} | {'Accuracy':>10} | {'Discrim. (dB)':>14}",
        "-" * 38,
    ]
    for r in result.noise_sweep:
        lines.append(
            f"{r.noise_fraction * 100:7.1f}% | "
            f"{r.recall_accuracy:10.1%} | "
            f"{r.mean_discrimination_db:13.1f}"
        )
    lines.append(f"\nBasin width: {result.rod_basin_width * 100:.0f}% noise")

    lines.append("\n--- Array Size Sweep (capacity) ---")
    lines.append(f"{'# Rods':>8} | {'Accuracy':>10}")
    lines.append("-" * 22)
    for r in result.array_size_sweep:
        lines.append(f"{r.n_rods:8d} | {r.recall_accuracy:10.1%}")
    lines.append(f"\nCapacity threshold (≥90%): {result.rod_capacity_threshold} rods")

    lines.append("\n--- Hopfield Comparison ---")
    lines.append(f"Hopfield capacity (N={result.hopfield_capacity.N}): "
                 f"{result.hopfield_capacity.capacity_threshold:.0f} patterns")
    lines.append(f"Hopfield basin width: "
                 f"{result.hopfield_basin.basin_width * 100:.0f}% corruption")

    lines.append("\n" + "=" * 65)
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_experiment()
    print(summarize(result))
