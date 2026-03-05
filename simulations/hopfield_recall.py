"""
Hopfield/Ising Associative Recall via Optical Interference.

This is the substrate-independent core idea from the original WCFOMA
corpus (Scale 1, Ch0 Academic): data stored as binary or trinary phase
states in an interference network, with recall governed by a Hopfield
energy function that physical interference computes in a single pass.

The module is intentionally decoupled from the ferrofluid substrate —
it works equally for:
  - Ferroelectric photonic MZI arrays (HZO on SiN)
  - Magnonic spin-wave interference (YIG)
  - Ferrofluid acoustic eigenmodes
  - Any coherent wave medium with controllable phase

Key physics:
  E = -½ Σᵢⱼ wᵢⱼ sᵢ sⱼ          (Hopfield energy)
  wᵢⱼ = (1/P) Σᵘ ξᵢᵘ ξⱼᵘ         (Hebbian weight matrix)
  I_out ∝ |Σ aₙ exp(iφₙ)|²        (interference readout)

Capabilities:
  - Store P binary (±1) or trinary (−1, 0, +1) patterns
  - Recall from noisy/partial queries via energy descent
  - Measure storage capacity (P_max) vs network size N
  - Compare binary Hopfield vs trinary Potts model
  - Compute basin of attraction width
  - Physical interference simulation (optical, acoustic, magnonic)

References:
  - Hopfield, "Neural networks and physical systems" (PNAS 1982)
  - Original WCFOMA Scale 1 Ch0 Academic Presentation
  - Shen et al., "Deep learning with coherent nanophotonic circuits" (2017)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
import numpy as np


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HopfieldNetwork:
    """A Hopfield network defined by its weight matrix and stored patterns."""
    weights: np.ndarray            # (N, N) symmetric, zero-diagonal
    patterns: np.ndarray           # (P, N) stored patterns
    N: int                         # network size (number of channels)
    P: int                         # number of stored patterns
    model: str = "binary"          # "binary" or "trinary"


@dataclass
class RecallResult:
    """Result of a single recall attempt."""
    query: np.ndarray              # input pattern (noisy/partial)
    recalled: np.ndarray           # output after convergence
    target_idx: int                # which stored pattern was targeted
    target_pattern: np.ndarray     # the target pattern itself
    overlap: float                 # cosine similarity with target
    converged: bool                # did the network converge?
    n_steps: int                   # steps to convergence
    energy_trajectory: np.ndarray  # energy at each step
    correct: bool                  # overlap > threshold?


@dataclass
class CapacityResult:
    """Result of a storage capacity experiment."""
    N: int                         # network size
    P_values: np.ndarray           # number of patterns tested
    recall_rates: np.ndarray       # fraction of correct recalls per P
    capacity_threshold: float      # P where recall drops below 90%
    model: str                     # "binary" or "trinary"
    noise_level: float             # corruption fraction used in test


@dataclass
class BasinResult:
    """Basin of attraction measurement."""
    corruption_fractions: np.ndarray   # fraction of bits flipped
    recall_accuracies: np.ndarray      # fraction correctly recalled
    basin_width: float                 # corruption where recall = 50%
    N: int
    P: int


@dataclass
class InterferenceRecallResult:
    """Physical interference-based recall result."""
    phases_in: np.ndarray          # input phase vector
    intensities_out: np.ndarray    # output intensities per channel
    recalled_pattern: np.ndarray   # thresholded output
    target_pattern: np.ndarray
    overlap: float
    total_intensity: float         # |Σ aₙ exp(iφₙ)|²
    snr_db: float                  # signal-to-noise ratio


# ---------------------------------------------------------------------------
# Network construction
# ---------------------------------------------------------------------------

def create_hopfield_network(
    patterns: np.ndarray,
    model: str = "binary",
) -> HopfieldNetwork:
    """
    Create a Hopfield network from stored patterns.

    Uses the Hebbian learning rule:
      wᵢⱼ = (1/N) Σᵘ ξᵢᵘ ξⱼᵘ     (i ≠ j, wᵢᵢ = 0)

    Parameters
    ----------
    patterns : ndarray of shape (P, N)
        P patterns, each of length N.
        Binary model: values in {-1, +1}.
        Trinary model: values in {-1, 0, +1}.
    model : str
        "binary" or "trinary".

    Returns
    -------
    HopfieldNetwork
    """
    patterns = np.array(patterns, dtype=float)
    P, N = patterns.shape

    # Hebbian weight matrix
    weights = np.zeros((N, N))
    for mu in range(P):
        weights += np.outer(patterns[mu], patterns[mu])
    weights /= N

    # Zero diagonal (no self-connections)
    np.fill_diagonal(weights, 0.0)

    return HopfieldNetwork(
        weights=weights,
        patterns=patterns,
        N=N,
        P=P,
        model=model,
    )


def generate_random_patterns(
    N: int,
    P: int,
    model: str = "binary",
    rng: Optional[np.random.RandomState] = None,
) -> np.ndarray:
    """
    Generate P random patterns of length N.

    Binary: each element ∈ {-1, +1} with equal probability.
    Trinary: each element ∈ {-1, 0, +1} with equal probability.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    if model == "binary":
        return rng.choice([-1, 1], size=(P, N)).astype(float)
    elif model == "trinary":
        return rng.choice([-1, 0, 1], size=(P, N)).astype(float)
    else:
        raise ValueError(f"Unknown model: {model}")


# ---------------------------------------------------------------------------
# Energy and dynamics
# ---------------------------------------------------------------------------

def hopfield_energy(state: np.ndarray, network: HopfieldNetwork) -> float:
    """
    Compute the Hopfield energy: E = -½ Σᵢⱼ wᵢⱼ sᵢ sⱼ.
    """
    return -0.5 * state @ network.weights @ state


def pattern_overlap(state: np.ndarray, pattern: np.ndarray) -> float:
    """
    Cosine similarity between state and pattern.
    Returns value in [-1, 1] for binary, [-1, 1] for trinary.
    """
    norm_s = np.linalg.norm(state)
    norm_p = np.linalg.norm(pattern)
    if norm_s < 1e-12 or norm_p < 1e-12:
        return 0.0
    return float(np.dot(state, pattern) / (norm_s * norm_p))


def sign_activation(x: float, model: str = "binary") -> float:
    """
    Activation function.
    Binary: sign(x), with 0→+1.
    Trinary: {-1 if x<-0.5, 0 if -0.5≤x≤0.5, +1 if x>0.5}
    """
    if model == "binary":
        return 1.0 if x >= 0 else -1.0
    else:  # trinary
        if x > 0.5:
            return 1.0
        elif x < -0.5:
            return -1.0
        else:
            return 0.0


def recall_pattern(
    network: HopfieldNetwork,
    query: np.ndarray,
    max_steps: int = 100,
    target_idx: int = 0,
    async_update: bool = True,
    rng: Optional[np.random.RandomState] = None,
) -> RecallResult:
    """
    Run associative recall: start from query, iterate until convergence.

    Uses asynchronous update (one neuron at a time, random order) which
    is guaranteed to converge to a local energy minimum.

    Parameters
    ----------
    network : HopfieldNetwork
        The network with stored patterns.
    query : ndarray
        Initial state (noisy/partial version of a stored pattern).
    max_steps : int
        Maximum number of full sweeps through all neurons.
    target_idx : int
        Index of the target pattern (for measuring recall accuracy).
    async_update : bool
        If True, update neurons one at a time (guarantees convergence).
        If False, synchronous update (may oscillate).

    Returns
    -------
    RecallResult
    """
    if rng is None:
        rng = np.random.RandomState(0)

    state = query.copy().astype(float)
    N = network.N
    energies = [hopfield_energy(state, network)]

    converged = False
    steps = 0

    for step in range(max_steps):
        old_state = state.copy()

        if async_update:
            order = rng.permutation(N)
            for i in order:
                h_i = network.weights[i] @ state
                state[i] = sign_activation(h_i, network.model)
        else:
            h = network.weights @ state
            state = np.array([sign_activation(h_i, network.model) for h_i in h])

        energies.append(hopfield_energy(state, network))
        steps = step + 1

        if np.array_equal(state, old_state):
            converged = True
            break

    target = network.patterns[target_idx]
    overlap = pattern_overlap(state, target)

    return RecallResult(
        query=query,
        recalled=state,
        target_idx=target_idx,
        target_pattern=target,
        overlap=overlap,
        converged=converged,
        n_steps=steps,
        energy_trajectory=np.array(energies),
        correct=overlap > 0.95,
    )


# ---------------------------------------------------------------------------
# Noise injection / partial query generation
# ---------------------------------------------------------------------------

def corrupt_pattern(
    pattern: np.ndarray,
    fraction: float,
    model: str = "binary",
    rng: Optional[np.random.RandomState] = None,
) -> np.ndarray:
    """
    Corrupt a pattern by flipping a fraction of its elements.

    Binary: flip sign of selected elements.
    Trinary: randomize selected elements to any of {-1, 0, +1}.
    """
    if rng is None:
        rng = np.random.RandomState(0)

    corrupted = pattern.copy()
    N = len(pattern)
    n_flip = int(fraction * N)
    flip_idx = rng.choice(N, size=n_flip, replace=False)

    if model == "binary":
        corrupted[flip_idx] *= -1
    else:
        corrupted[flip_idx] = rng.choice([-1, 0, 1], size=n_flip)

    return corrupted


def mask_pattern(
    pattern: np.ndarray,
    fraction: float,
    rng: Optional[np.random.RandomState] = None,
) -> np.ndarray:
    """
    Mask a fraction of elements to 0 (partial query).
    Useful for trinary model: 0 = "don't know".
    """
    if rng is None:
        rng = np.random.RandomState(0)

    masked = pattern.copy()
    N = len(pattern)
    n_mask = int(fraction * N)
    mask_idx = rng.choice(N, size=n_mask, replace=False)
    masked[mask_idx] = 0.0
    return masked


# ---------------------------------------------------------------------------
# Storage capacity analysis
# ---------------------------------------------------------------------------

def measure_capacity(
    N: int,
    P_values: np.ndarray = None,
    model: str = "binary",
    noise_fraction: float = 0.1,
    n_trials: int = 20,
    rng: Optional[np.random.RandomState] = None,
) -> CapacityResult:
    """
    Measure recall accuracy as a function of stored patterns P.

    For each P, store P random patterns, corrupt one by noise_fraction,
    attempt recall, measure success rate over n_trials.

    The theoretical Hopfield capacity is P_max ≈ 0.138N (binary).

    Parameters
    ----------
    N : int
        Network size.
    P_values : ndarray
        Number of patterns to test.
    model : str
        "binary" or "trinary".
    noise_fraction : float
        Fraction of bits corrupted in query.
    n_trials : int
        Trials per P value.

    Returns
    -------
    CapacityResult
    """
    if rng is None:
        rng = np.random.RandomState(42)

    if P_values is None:
        P_max_test = max(int(0.3 * N), 5)
        P_values = np.arange(1, P_max_test + 1)

    recall_rates = np.zeros(len(P_values))

    for ip, P in enumerate(P_values):
        n_correct = 0
        for trial in range(n_trials):
            seed = rng.randint(0, 100000)
            trial_rng = np.random.RandomState(seed)

            patterns = generate_random_patterns(N, P, model, trial_rng)
            network = create_hopfield_network(patterns, model)

            # Pick a random stored pattern, corrupt it, try to recall
            target_idx = trial_rng.randint(P)
            query = corrupt_pattern(
                patterns[target_idx], noise_fraction, model, trial_rng
            )
            result = recall_pattern(
                network, query, target_idx=target_idx, rng=trial_rng
            )
            if result.correct:
                n_correct += 1

        recall_rates[ip] = n_correct / n_trials

    # Find capacity threshold (where recall drops below 90%)
    above_90 = np.where(recall_rates >= 0.9)[0]
    capacity = float(P_values[above_90[-1]]) if len(above_90) > 0 else 0.0

    return CapacityResult(
        N=N,
        P_values=P_values,
        recall_rates=recall_rates,
        capacity_threshold=capacity,
        model=model,
        noise_level=noise_fraction,
    )


def measure_basin_of_attraction(
    N: int = 50,
    P: int = 5,
    corruption_fractions: np.ndarray = None,
    model: str = "binary",
    n_trials: int = 20,
    rng: Optional[np.random.RandomState] = None,
) -> BasinResult:
    """
    Measure recall accuracy as a function of input corruption.

    Determines how noisy a query can be while still recalling correctly.

    Returns
    -------
    BasinResult
    """
    if rng is None:
        rng = np.random.RandomState(42)

    if corruption_fractions is None:
        corruption_fractions = np.linspace(0, 0.5, 11)

    patterns = generate_random_patterns(N, P, model, rng)
    network = create_hopfield_network(patterns, model)

    accuracies = np.zeros(len(corruption_fractions))

    for ic, frac in enumerate(corruption_fractions):
        n_correct = 0
        for trial in range(n_trials):
            trial_rng = np.random.RandomState(rng.randint(100000))
            target_idx = trial_rng.randint(P)
            query = corrupt_pattern(
                patterns[target_idx], frac, model, trial_rng
            )
            result = recall_pattern(
                network, query, target_idx=target_idx, rng=trial_rng
            )
            if result.correct:
                n_correct += 1
        accuracies[ic] = n_correct / n_trials

    # Basin width: where accuracy crosses 50%
    below_50 = np.where(accuracies < 0.5)[0]
    if len(below_50) > 0:
        basin_width = float(corruption_fractions[below_50[0]])
    else:
        basin_width = float(corruption_fractions[-1])

    return BasinResult(
        corruption_fractions=corruption_fractions,
        recall_accuracies=accuracies,
        basin_width=basin_width,
        N=N,
        P=P,
    )


# ---------------------------------------------------------------------------
# Physical interference simulation
# ---------------------------------------------------------------------------

def interference_recall(
    network: HopfieldNetwork,
    query: np.ndarray,
    target_idx: int = 0,
    wavelength: float = 1.55e-6,
    noise_power: float = 0.0,
    rng: Optional[np.random.RandomState] = None,
) -> InterferenceRecallResult:
    """
    Simulate associative recall via physical optical interference.

    Each channel i has a phase shifter encoding state sᵢ:
      binary:  sᵢ = +1 → φᵢ = 0,  sᵢ = -1 → φᵢ = π
      trinary: sᵢ = +1 → φᵢ = 0,  sᵢ = 0 → φᵢ = π/2,  sᵢ = -1 → φᵢ = π

    The weight matrix W is programmed into a photonic crossbar.
    The output field at channel j is:

      E_j = Σᵢ wᵢⱼ exp(i φᵢ)

    The output intensity |E_j|² is thresholded to recover the pattern.

    This is one optical pass = one matrix-vector multiply = one recall step.

    Parameters
    ----------
    network : HopfieldNetwork
        Network with stored patterns.
    query : ndarray
        Input state (phase-encoded).
    target_idx : int
        Index of target pattern for scoring.
    wavelength : float
        Optical wavelength [m] (for noting physical regime).
    noise_power : float
        Added noise variance on output intensities.

    Returns
    -------
    InterferenceRecallResult
    """
    if rng is None:
        rng = np.random.RandomState(0)

    N = network.N
    model = network.model

    # Encode query as phases
    if model == "binary":
        phases_in = np.where(query >= 0, 0.0, np.pi)
    else:  # trinary
        phases_in = np.where(query > 0.5, 0.0,
                    np.where(query < -0.5, np.pi, np.pi / 2))

    # Complex field amplitudes
    E_in = np.exp(1j * phases_in)

    # Matrix-vector multiply through photonic crossbar
    E_out = network.weights @ E_in

    # Add noise
    if noise_power > 0:
        noise = rng.normal(0, np.sqrt(noise_power), N) + \
                1j * rng.normal(0, np.sqrt(noise_power), N)
        E_out += noise

    # Output intensities
    intensities = np.abs(E_out)**2
    total_intensity = np.sum(intensities)

    # Threshold to recover pattern
    if model == "binary":
        recalled = np.where(np.real(E_out) >= 0, 1.0, -1.0)
    else:
        real_out = np.real(E_out)
        max_abs = np.max(np.abs(real_out)) + 1e-30
        normalized = real_out / max_abs
        recalled = np.where(normalized > 0.33, 1.0,
                   np.where(normalized < -0.33, -1.0, 0.0))

    target = network.patterns[target_idx]
    overlap = pattern_overlap(recalled, target)

    # SNR
    signal = np.mean(intensities)
    noise_floor = noise_power if noise_power > 0 else 1e-30
    snr_db = 10 * np.log10(signal / noise_floor) if noise_floor > 0 else np.inf

    return InterferenceRecallResult(
        phases_in=phases_in,
        intensities_out=intensities,
        recalled_pattern=recalled,
        target_pattern=target,
        overlap=overlap,
        total_intensity=total_intensity,
        snr_db=snr_db,
    )


# ---------------------------------------------------------------------------
# Binary vs trinary comparison
# ---------------------------------------------------------------------------

def compare_binary_trinary(
    N: int = 50,
    P_values: np.ndarray = None,
    noise_fraction: float = 0.1,
    n_trials: int = 20,
    rng: Optional[np.random.RandomState] = None,
) -> Dict[str, CapacityResult]:
    """
    Compare binary Hopfield vs trinary Potts model capacity.

    Returns
    -------
    dict with keys "binary" and "trinary", each a CapacityResult.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    results = {}
    for model in ["binary", "trinary"]:
        results[model] = measure_capacity(
            N=N,
            P_values=P_values,
            model=model,
            noise_fraction=noise_fraction,
            n_trials=n_trials,
            rng=np.random.RandomState(rng.randint(100000)),
        )
    return results


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def hopfield_summary(
    N: int = 50,
    P: int = 5,
    noise_fraction: float = 0.1,
) -> str:
    """Generate a text summary of Hopfield recall performance."""
    rng = np.random.RandomState(42)

    # Store patterns and test recall
    patterns = generate_random_patterns(N, P, "binary", rng)
    network = create_hopfield_network(patterns, "binary")

    results = []
    for i in range(P):
        query = corrupt_pattern(patterns[i], noise_fraction, "binary",
                                np.random.RandomState(i))
        result = recall_pattern(network, query, target_idx=i,
                                rng=np.random.RandomState(i))
        results.append(result)

    n_correct = sum(1 for r in results if r.correct)
    avg_overlap = np.mean([r.overlap for r in results])
    avg_steps = np.mean([r.n_steps for r in results])

    # Theoretical capacity
    p_max_theory = 0.138 * N

    lines = [
        "=" * 60,
        "  HOPFIELD ASSOCIATIVE RECALL SUMMARY",
        "=" * 60,
        f"  Network size (N):        {N}",
        f"  Stored patterns (P):     {P}",
        f"  Theoretical capacity:    {p_max_theory:.1f} patterns",
        f"  Load factor (P/N):       {P/N:.3f} (max ~0.138)",
        f"  Noise fraction:          {noise_fraction:.0%}",
        "-" * 60,
        f"  Correct recalls:         {n_correct}/{P} ({100*n_correct/P:.0f}%)",
        f"  Average overlap:         {avg_overlap:.3f}",
        f"  Average steps:           {avg_steps:.1f}",
        "-" * 60,
        "  PER-PATTERN RESULTS",
        f"  {'#':<4} {'Overlap':<10} {'Steps':<8} {'Converged':<12} {'Correct':<8}",
    ]
    for i, r in enumerate(results):
        lines.append(
            f"  {i:<4} {r.overlap:<10.3f} {r.n_steps:<8} "
            f"{'Yes' if r.converged else 'No':<12} "
            f"{'✅' if r.correct else '❌':<8}"
        )
    lines.append("=" * 60)
    return "\n".join(lines)
