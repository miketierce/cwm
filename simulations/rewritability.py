"""
Rewritability Experiments for Spectral Eigenmode Memory.

Seven testable engineering hypotheses exploring paths from fixed-template
"sonic telescope" toward configurable "instrument" behavior, without
leaving the domain of established physics.

Three tracks:
═══════════════════════════════════════════════════════════════════════
Track A — Firmware-Defined Virtual Rewriting
  No physical changes to the rod.  Rewritability lives entirely in how
  we excite and listen to the same fixed resonator.

  H7: Multi-Projection Virtual Rewrite
      Partition the SVD basis of one rod's coupling matrix into K
      orthogonal subspaces.  Each subspace acts as an independent
      logical memory with zero cross-talk.

  H8: Mode-Subset Logical Devices
      Drive/read different contiguous mode ranges on the same rod.
      Each range is a separate logical device with independent
      recall capability.

  H9: Readout Mask Library
      Apply different spectral masks (pruning thresholds, frequency
      windows) to the same rod's readout.  Measure how many distinct
      effective devices one physical rod can support.

Track B — Binary Perturbation Sites (Discrete Rewrite Hardware)
  Pre-fabricate N docking sites on the rod.  Each site can be toggled
  between mass-coupled and decoupled (like RF MEMS switches).

  H10: Binary Site Fingerprint Capacity
       For N binary-toggle sites on one rod, how many spectrally
       distinguishable configurations exist?

  H11: Binary-Site Hopfield Capacity
       Feed binary-site fingerprints into associative recall.
       What is the minimum site count for reliable pattern matching?

Track C — Multi-Shell Resonator (Writable Perturbation Layer)
  High-Q glass core + thin writable shell.  The shell perturbs modes
  without killing Q.

  H12: Actuator Q Penalty
       Model the Q impact of adding MEMS switch structures
       (electrodes, air gaps) near the resonator surface.

  H13: Writable Shell Q Budget
       Parametric sweep: shell thickness × shell material loss →
       total Q.  Find the operating envelope where Q > 5,000.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np

from .hopfield_recall import (
    create_hopfield_network,
    generate_random_patterns,
    recall_pattern,
    corrupt_pattern,
    HopfieldNetwork,
)
from .interference import (
    encode_data,
    evolve_superposition,
    readout_modes,
    ModeEncoding,
)
from .mems_q_model import (
    compute_Q_material,
    compute_Q_anchor,
    compute_Q_TED,
    compute_Q_surface,
    compute_Q_gas,
    AnchorDesign,
    OperatingConditions,
    SurfaceProperties,
    QComponentResult,
)
from .glass_resonator import GlassProperties, RodGeometry, glass_database
from .common import K_B


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MultiProjectionResult:
    """H7 — Virtual rewrite via orthogonal projection subspaces."""
    n_modes: int
    n_perturbation_sites: int
    n_partitions: int             # K subspaces created
    dims_per_partition: List[int] # dimensionality of each subspace
    fidelity_per_partition: np.ndarray  # recall fidelity in each subspace
    crosstalk_matrix: np.ndarray  # (K×K) cross-talk between partitions
    max_crosstalk: float          # worst-case off-diagonal entry
    mean_fidelity: float
    effective_devices: int        # partitions with fidelity > 0.8
    verdict: bool                 # True if ≥2 devices with fidelity > 0.8


@dataclass
class ModeSubsetResult:
    """H8 — Mode-subset logical devices."""
    total_modes: int
    n_subsets: int
    modes_per_subset: int
    recall_per_subset: np.ndarray       # accuracy for each subset
    crosstalk_between_subsets: np.ndarray  # pairwise leakage
    mean_recall: float
    worst_recall: float
    independent_devices: int            # subsets with recall > 0.7
    verdict: bool                       # True if ≥2 independent devices


@dataclass
class ReadoutMaskResult:
    """H9 — Readout mask library."""
    n_masks: int
    mask_descriptions: List[str]
    recall_per_mask: np.ndarray
    pattern_discrimination: np.ndarray  # per-mask discrimination margin (dB)
    masks_above_threshold: int          # masks with recall > 0.7
    best_mask_idx: int
    best_recall: float
    verdict: bool                       # True if ≥3 masks produce useful devices


@dataclass
class BinaryFingerprintResult:
    """H10 — Binary perturbation site fingerprints."""
    n_sites: int
    n_modes: int
    n_configurations_tested: int
    n_distinguishable: int              # configs with pairwise distance > threshold
    min_pairwise_distance: float        # worst-case spectral separation
    mean_pairwise_distance: float
    bits_per_rod: float                 # log2(n_distinguishable)
    spectral_distance_matrix: np.ndarray
    verdict: bool                       # True if distinguishable > 2^(n_sites/2)


@dataclass
class BinaryHopfieldResult:
    """H11 — Binary-site Hopfield capacity."""
    site_counts: np.ndarray             # N_sites tested
    n_modes: int
    capacity_per_site_count: np.ndarray # max patterns recalled at each N_sites
    recall_accuracy: np.ndarray         # accuracy at capacity limit
    min_sites_for_recall: int           # smallest N_sites giving >80% recall
    capacity_scaling_exponent: float    # P_max ~ N_sites^α
    verdict: bool                       # True if min_sites ≤ 32


@dataclass
class ActuatorQResult:
    """H12 — Q penalty from actuator structures."""
    n_actuators: int
    actuator_area_fraction: float
    Q_no_actuator: float
    Q_with_actuator: float
    Q_penalty_pct: float                # fractional Q drop
    actuator_loss_fraction: float       # what % of total loss is actuator
    max_actuators_for_Q5000: int        # how many before Q < 5,000
    verdict: bool                       # True if Q > 5,000 with actuators


@dataclass
class WritableShellResult:
    """H13 — Writable shell Q budget."""
    shell_thicknesses_nm: np.ndarray
    shell_Q_values: np.ndarray          # Q_d of shell material
    total_Q_grid: np.ndarray            # (n_thick × n_Qd) grid
    Q_5000_boundary: List[Tuple[float, float]]  # (thickness, Q_d) at Q=5000
    max_shell_thickness_nm: float       # thickest shell keeping Q > 5,000
    frequency_shift_pct: float          # Rayleigh shift from max shell
    verdict: bool                       # True if useful rewrite window exists


# ═══════════════════════════════════════════════════════════════════════
# Track A — Firmware-Defined Virtual Rewriting
# ═══════════════════════════════════════════════════════════════════════

# ── H7: Multi-Projection Virtual Rewrite ─────────────────────────────

def exp_multi_projection(
    n_modes: int = 10,
    n_perturbations: int = 24,
    n_partitions: int = 4,
    n_test_patterns: int = 5,
    noise_level: float = 0.01,
    rng: Optional[np.random.RandomState] = None,
) -> MultiProjectionResult:
    """
    Partition one rod's coupling-matrix SVD into K orthogonal subspaces.
    Each subspace is a logically independent memory channel.

    This extends the null-space experiment (H6): instead of just
    column-space vs. null-space (2 channels), we split the full
    space into K equal-sized partitions, each spanned by a subset
    of the right-singular vectors.

    Procedure
    ---------
    1. Build coupling matrix C (n_modes × n_perturbations).
    2. SVD → full set of right-singular vectors.
    3. Partition the singular vectors into K groups.
    4. For each partition, encode test patterns in that subspace.
    5. Read back using that partition's projection basis.
    6. Measure fidelity within each partition and cross-talk between.

    If successful, one physical rod supports K virtual devices,
    switchable at firmware speed by loading different projection
    coefficients into the CMOS readout die.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    # Build sinusoidal coupling matrix (same physics as H6)
    C = np.zeros((n_modes, n_perturbations))
    for i in range(n_modes):
        for j in range(n_perturbations):
            C[i, j] = np.sin((i + 1) * np.pi * (j + 1) / (n_perturbations + 1))

    # Full SVD
    U, S, Vt = np.linalg.svd(C, full_matrices=True)
    rank = int(np.sum(S > 1e-10 * S[0]))

    # Use ALL right-singular vectors (including null-space)
    # Partition them into K groups of roughly equal size
    total_dims = n_perturbations
    base_size = total_dims // n_partitions
    remainder = total_dims % n_partitions

    partition_indices = []
    start = 0
    dims_per_part = []
    for k in range(n_partitions):
        size = base_size + (1 if k < remainder else 0)
        partition_indices.append(list(range(start, start + size)))
        dims_per_part.append(size)
        start += size

    # Build projection bases for each partition
    partition_bases = []
    for indices in partition_indices:
        basis = Vt[indices, :]  # shape (dim_k, n_perturbations)
        partition_bases.append(basis)

    # Test each partition: encode patterns, read back, measure fidelity
    fidelity_per_partition = np.zeros(n_partitions)
    all_encoded = []

    for k in range(n_partitions):
        basis = partition_bases[k]
        dim_k = dims_per_part[k]
        if dim_k == 0:
            fidelity_per_partition[k] = 0.0
            all_encoded.append(np.zeros((n_test_patterns, n_perturbations)))
            continue

        # Random test patterns in this subspace
        coeffs = rng.randn(n_test_patterns, dim_k)
        encoded = coeffs @ basis  # (n_test, n_perturbations)
        all_encoded.append(encoded)

        # Add noise and project back
        fids = []
        for p in range(n_test_patterns):
            noisy = encoded[p] + rng.randn(n_perturbations) * noise_level
            readout = noisy @ basis.T  # project onto this partition's basis
            truth = coeffs[p]
            n1 = np.linalg.norm(readout)
            n2 = np.linalg.norm(truth)
            if n1 > 1e-30 and n2 > 1e-30:
                fid = float(np.dot(readout, truth) / (n1 * n2))
            else:
                fid = 0.0
            fids.append(max(fid, 0.0))
        fidelity_per_partition[k] = float(np.mean(fids))

    # Cross-talk matrix: how much does partition j's signal leak into partition k?
    crosstalk = np.zeros((n_partitions, n_partitions))
    for j in range(n_partitions):
        for k in range(n_partitions):
            if dims_per_part[j] == 0 or dims_per_part[k] == 0:
                crosstalk[j, k] = 0.0
                continue
            # Encode in partition j, project onto partition k
            test_vec = all_encoded[j][0]  # first test pattern from j
            readout_in_k = test_vec @ partition_bases[k].T
            readout_in_j = test_vec @ partition_bases[j].T
            nk = np.linalg.norm(readout_in_k)
            nj = np.linalg.norm(readout_in_j)
            if j == k:
                crosstalk[j, k] = 1.0  # self-correlation
            else:
                crosstalk[j, k] = nk / (nj + 1e-30)

    max_xtalk = 0.0
    for j in range(n_partitions):
        for k in range(n_partitions):
            if j != k:
                max_xtalk = max(max_xtalk, crosstalk[j, k])

    effective = int(np.sum(fidelity_per_partition > 0.8))
    mean_fid = float(np.mean(fidelity_per_partition))

    return MultiProjectionResult(
        n_modes=n_modes,
        n_perturbation_sites=n_perturbations,
        n_partitions=n_partitions,
        dims_per_partition=dims_per_part,
        fidelity_per_partition=fidelity_per_partition,
        crosstalk_matrix=crosstalk,
        max_crosstalk=max_xtalk,
        mean_fidelity=mean_fid,
        effective_devices=effective,
        verdict=bool(effective >= 2 and max_xtalk < 0.05),
    )


# ── H8: Mode-Subset Logical Devices ──────────────────────────────────

def exp_mode_subset_devices(
    total_modes: int = 200,
    n_subsets: int = 4,
    P: int = 3,
    noise_fraction: float = 0.15,
    n_trials: int = 30,
    rng: Optional[np.random.RandomState] = None,
) -> ModeSubsetResult:
    """
    Divide a rod's mode spectrum into contiguous bands and use
    each band as an independent Hopfield associative memory.

    This is the simplest form of virtual rewriting: instead of
    querying the full 9,380-mode spectrum, you query modes 1-2345
    for application A and modes 2346-4690 for application B.
    The physical rod hasn't changed; you just changed which
    frequency range the excitation chirp covers.

    Procedure
    ---------
    1. Create a Hopfield network of size N = total_modes.
    2. Store P patterns in the full network.
    3. For each mode-subset (contiguous block of modes_per_subset):
       a. Extract the sub-network (rows/cols of W corresponding to
          this mode range).
       b. Recall from noisy queries using only the sub-network.
       c. Measure accuracy.
    4. Measure cross-talk: does a pattern stored in subset A
       produce spurious response in subset B?
    """
    if rng is None:
        rng = np.random.RandomState(42)

    modes_per_subset = total_modes // n_subsets

    # Generate full-network patterns and store
    patterns = generate_random_patterns(total_modes, P, "binary", rng)
    full_net = create_hopfield_network(patterns, "binary")

    # Test each subset
    recall_per_subset = np.zeros(n_subsets)
    for s in range(n_subsets):
        start = s * modes_per_subset
        end = start + modes_per_subset

        # Extract sub-patterns and sub-network
        sub_patterns = patterns[:, start:end]
        sub_net = create_hopfield_network(sub_patterns, "binary")

        n_correct = 0
        for trial in range(n_trials):
            trial_rng = np.random.RandomState(rng.randint(100000) + trial)
            target_idx = trial_rng.randint(P)
            query = corrupt_pattern(
                sub_patterns[target_idx], noise_fraction, "binary", trial_rng
            )
            result = recall_pattern(sub_net, query, target_idx=target_idx, rng=trial_rng)
            if result.correct:
                n_correct += 1
        recall_per_subset[s] = n_correct / n_trials

    # Cross-talk: pattern from subset A projected onto subset B's weight space
    crosstalk = np.zeros((n_subsets, n_subsets))
    for a in range(n_subsets):
        for b in range(n_subsets):
            start_a = a * modes_per_subset
            end_a = start_a + modes_per_subset
            start_b = b * modes_per_subset
            end_b = start_b + modes_per_subset

            if a == b:
                crosstalk[a, b] = 1.0
                continue

            # Take pattern 0 from subset A, project onto subset B's weight matrix
            sub_patterns_b = patterns[:, start_b:end_b]
            sub_net_b = create_hopfield_network(sub_patterns_b, "binary")

            # Measure: does a random query in B's space happen to match
            # something when A's pattern is used? (Should be low)
            pat_a = patterns[0, start_a:end_a]
            # Map pat_a into B's dimensionality (different modes → random-looking)
            # This is the key: modes from different ranges are physically independent
            overlap = float(np.abs(np.mean(pat_a @ sub_net_b.weights[:len(pat_a), :len(pat_a)])))
            crosstalk[a, b] = min(overlap, 1.0)

    mean_recall = float(np.mean(recall_per_subset))
    worst_recall = float(np.min(recall_per_subset))
    independent = int(np.sum(recall_per_subset > 0.7))

    return ModeSubsetResult(
        total_modes=total_modes,
        n_subsets=n_subsets,
        modes_per_subset=modes_per_subset,
        recall_per_subset=recall_per_subset,
        crosstalk_between_subsets=crosstalk,
        mean_recall=mean_recall,
        worst_recall=worst_recall,
        independent_devices=independent,
        verdict=bool(independent >= 2),
    )


# ── H9: Readout Mask Library ─────────────────────────────────────────

def exp_readout_mask_library(
    N: int = 100,
    P: int = 5,
    noise_fraction: float = 0.2,
    n_trials: int = 30,
    rng: Optional[np.random.RandomState] = None,
) -> ReadoutMaskResult:
    """
    Apply different spectral masks to the same rod's readout and
    measure how many distinct useful devices result.

    A "readout mask" is a vector of weights applied to the FFT output
    before computing the Hopfield correlation.  Different masks
    emphasize different mode ranges or threshold levels, producing
    different effective associative memories from the same stored data.

    Masks tested:
    1. Full spectrum (baseline — no mask)
    2. Low-mode emphasis (modes 1–N/3 weighted 3×)
    3. High-mode emphasis (modes 2N/3–N weighted 3×)
    4. Odd-mode only (even modes zeroed)
    5. Even-mode only (odd modes zeroed)
    6. Random sparse mask (50% of modes zeroed)
    7. Pruned (weights below median zeroed — like H3)

    If multiple masks produce recall > 0.7, the rod effectively
    hosts multiple logical devices selectable by firmware.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    patterns = generate_random_patterns(N, P, "binary", rng)
    base_net = create_hopfield_network(patterns, "binary")
    W = base_net.weights.copy()

    # Define masks
    mask_defs = []

    # 1. Full spectrum
    mask_defs.append(("Full spectrum", np.ones(N)))

    # 2. Low-mode emphasis
    low_mask = np.ones(N)
    low_mask[:N // 3] = 3.0
    mask_defs.append(("Low-mode 3×", low_mask))

    # 3. High-mode emphasis
    high_mask = np.ones(N)
    high_mask[2 * N // 3:] = 3.0
    mask_defs.append(("High-mode 3×", high_mask))

    # 4. Odd-mode only
    odd_mask = np.zeros(N)
    odd_mask[0::2] = 1.0
    mask_defs.append(("Odd modes", odd_mask))

    # 5. Even-mode only
    even_mask = np.zeros(N)
    even_mask[1::2] = 1.0
    mask_defs.append(("Even modes", even_mask))

    # 6. Random sparse 50%
    sparse_mask = np.zeros(N)
    active = rng.choice(N, size=N // 2, replace=False)
    sparse_mask[active] = 1.0
    mask_defs.append(("Random 50%", sparse_mask))

    # 7. Pruned (median threshold)
    abs_W = np.abs(W)
    median_w = np.median(abs_W[abs_W > 0]) if np.any(abs_W > 0) else 0.0
    pruned_mask_weights = W.copy()
    pruned_mask_weights[np.abs(pruned_mask_weights) < median_w] = 0.0
    mask_defs.append(("Pruned median", None))  # special handling below

    n_masks = len(mask_defs)
    recall_per_mask = np.zeros(n_masks)
    discrimination = np.zeros(n_masks)

    for mi, (name, mask) in enumerate(mask_defs):
        # Build masked network
        if name == "Pruned median":
            masked_W = pruned_mask_weights
        else:
            # Apply mask: W_masked[i,j] = W[i,j] * mask[i] * mask[j]
            mask_outer = np.outer(mask, mask)
            masked_W = W * mask_outer

        masked_net = HopfieldNetwork(
            weights=masked_W,
            patterns=patterns,
            N=N, P=P, model="binary",
        )

        n_correct = 0
        response_correct = []
        response_wrong = []

        for trial in range(n_trials):
            trial_rng = np.random.RandomState(rng.randint(100000) + trial)
            target_idx = trial_rng.randint(P)
            query = corrupt_pattern(
                patterns[target_idx], noise_fraction, "binary", trial_rng
            )
            result = recall_pattern(masked_net, query, target_idx=target_idx, rng=trial_rng)
            if result.correct:
                n_correct += 1

            # Discrimination: overlap with target vs best non-target
            overlaps = []
            for p in range(P):
                ov = float(np.dot(result.recalled, patterns[p]) / N)
                overlaps.append(ov)
            target_ov = overlaps[target_idx]
            other_ovs = [overlaps[p] for p in range(P) if p != target_idx]
            best_other = max(other_ovs) if other_ovs else 0.0
            margin = target_ov - best_other
            if result.correct:
                response_correct.append(margin)
            else:
                response_wrong.append(margin)

        recall_per_mask[mi] = n_correct / n_trials
        # Average discrimination margin (in overlap units, convert to ~dB)
        if response_correct:
            avg_margin = float(np.mean(response_correct))
            discrimination[mi] = 10 * np.log10(max(avg_margin + 1, 1e-6)) if avg_margin > 0 else 0.0
        else:
            discrimination[mi] = 0.0

    masks_above = int(np.sum(recall_per_mask > 0.7))
    best_idx = int(np.argmax(recall_per_mask))

    return ReadoutMaskResult(
        n_masks=n_masks,
        mask_descriptions=[name for name, _ in mask_defs],
        recall_per_mask=recall_per_mask,
        pattern_discrimination=discrimination,
        masks_above_threshold=masks_above,
        best_mask_idx=best_idx,
        best_recall=float(recall_per_mask[best_idx]),
        verdict=bool(masks_above >= 3),
    )


# ═══════════════════════════════════════════════════════════════════════
# Track B — Binary Perturbation Sites
# ═══════════════════════════════════════════════════════════════════════

# ── H10: Binary Site Fingerprint Capacity ─────────────────────────────

def _build_coupling_matrix(n_modes: int, n_sites: int) -> np.ndarray:
    """Build sinusoidal coupling matrix C (n_modes × n_sites).

    C_ij = sin((i+1) * pi * (j+1) / (n_sites+1)) models how each
    perturbation site affects each eigenmode, based on the standing-wave
    displacement pattern at that position.
    """
    C = np.zeros((n_modes, n_sites))
    for i in range(n_modes):
        for j in range(n_sites):
            C[i, j] = np.sin((i + 1) * np.pi * (j + 1) / (n_sites + 1))
    return C


def exp_binary_fingerprints(
    n_sites: int = 12,
    n_modes: int = 20,
    n_configs_to_test: int = 200,
    distinguishability_threshold: float = 0.1,
    rng: Optional[np.random.RandomState] = None,
) -> BinaryFingerprintResult:
    """
    Each of n_sites perturbation positions can be toggled ON (mass
    coupled) or OFF (mass decoupled).  There are 2^n_sites possible
    configurations.  Each configuration produces a spectral fingerprint
    via the coupling matrix C.

    We sample configurations and measure pairwise spectral distances
    to determine how many are reliably distinguishable.

    Procedure
    ---------
    1. Build coupling matrix C (n_modes × n_sites).
    2. Sample min(2^n_sites, n_configs_to_test) binary configurations.
    3. Compute spectral fingerprint for each: f = C @ config.
    4. Compute pairwise L2 distances between fingerprints.
    5. Count pairs with distance > threshold as "distinguishable."
    6. Report bits_per_rod = log2(n_distinguishable).
    """
    if rng is None:
        rng = np.random.RandomState(42)

    C = _build_coupling_matrix(n_modes, n_sites)

    # Sample binary configurations
    max_configs = min(2 ** n_sites, n_configs_to_test)
    if 2 ** n_sites <= n_configs_to_test:
        # Enumerate all
        configs = np.array([[int(b) for b in format(i, f'0{n_sites}b')]
                            for i in range(2 ** n_sites)], dtype=float)
    else:
        # Random sample (include all-zeros and all-ones)
        configs = rng.randint(0, 2, size=(n_configs_to_test, n_sites)).astype(float)
        configs[0] = np.zeros(n_sites)
        configs[1] = np.ones(n_sites)

    n_tested = len(configs)

    # Compute fingerprints
    fingerprints = configs @ C.T  # (n_tested, n_modes)

    # Pairwise distances
    n_pairs = n_tested * (n_tested - 1) // 2
    distances = np.zeros(n_pairs)
    dist_matrix = np.zeros((n_tested, n_tested))
    idx = 0
    for i in range(n_tested):
        for j in range(i + 1, n_tested):
            d = np.linalg.norm(fingerprints[i] - fingerprints[j])
            distances[idx] = d
            dist_matrix[i, j] = d
            dist_matrix[j, i] = d
            idx += 1

    # Normalize distances by the max for meaningful threshold comparison
    max_dist = np.max(distances) if len(distances) > 0 else 1.0
    norm_distances = distances / (max_dist + 1e-30)

    # Count distinguishable: all pairwise distances for a config must
    # exceed threshold.  Use a greedy approach: greedily select configs
    # that are all > threshold apart from each other.
    selected = [0]  # start with first config
    for i in range(1, n_tested):
        is_distinct = True
        for s in selected:
            if dist_matrix[i, s] / (max_dist + 1e-30) < distinguishability_threshold:
                is_distinct = False
                break
        if is_distinct:
            selected.append(i)

    n_distinguishable = len(selected)
    min_dist = float(np.min(distances)) if len(distances) > 0 else 0.0
    mean_dist = float(np.mean(distances)) if len(distances) > 0 else 0.0
    bits = float(np.log2(max(n_distinguishable, 1)))

    return BinaryFingerprintResult(
        n_sites=n_sites,
        n_modes=n_modes,
        n_configurations_tested=n_tested,
        n_distinguishable=n_distinguishable,
        min_pairwise_distance=min_dist,
        mean_pairwise_distance=mean_dist,
        bits_per_rod=bits,
        spectral_distance_matrix=dist_matrix,
        verdict=bool(n_distinguishable > 2 ** (n_sites / 2)),
    )


# ── H11: Binary-Site Hopfield Capacity ───────────────────────────────

def exp_binary_hopfield_capacity(
    site_counts: Optional[np.ndarray] = None,
    n_modes: int = 30,
    noise_fraction: float = 0.15,
    n_trials: int = 25,
    rng: Optional[np.random.RandomState] = None,
) -> BinaryHopfieldResult:
    """
    For each site count N_sites, determine the maximum number of
    binary-site configurations that can be reliably recalled via
    Hopfield associative memory.

    Procedure
    ---------
    1. For each N_sites in [4, 8, 12, 16, 20, 24, 32]:
       a. Build coupling matrix C (n_modes × N_sites).
       b. Generate candidate binary configs.
       c. Compute spectral fingerprints.
       d. Normalize and binarize fingerprints for Hopfield storage.
       e. Store increasing numbers of patterns; find capacity limit
          (where recall accuracy drops below 80%).
    2. Fit capacity scaling: P_max ~ N_sites^alpha.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    if site_counts is None:
        site_counts = np.array([4, 8, 12, 16, 20, 24, 32])

    capacity_per_count = np.zeros(len(site_counts))
    recall_at_capacity = np.zeros(len(site_counts))

    for si, n_sites in enumerate(site_counts):
        C = _build_coupling_matrix(n_modes, int(n_sites))

        # Generate a pool of binary configs
        max_pool = min(2 ** int(n_sites), 100)
        if 2 ** int(n_sites) <= 100:
            configs = np.array([[int(b) for b in format(i, f'0{int(n_sites)}b')]
                                for i in range(1, 2 ** int(n_sites))], dtype=float)
        else:
            configs = rng.randint(0, 2, size=(99, int(n_sites))).astype(float)
            # Ensure no all-zeros (trivial)
            configs = configs[np.any(configs > 0, axis=1)]

        # Compute spectral fingerprints
        fingerprints = configs @ C.T  # (n_configs, n_modes)

        # Binarize: threshold at median of each mode across fingerprints
        medians = np.median(fingerprints, axis=0)
        binary_fps = np.where(fingerprints > medians, 1.0, -1.0)

        # Find capacity: increase P until recall < 80%
        best_P = 0
        best_acc = 0.0
        max_P = min(len(binary_fps), int(0.138 * n_modes) + 2)

        for P in range(2, max_P + 1):
            # Select P patterns
            selected = binary_fps[:P]
            net = create_hopfield_network(selected, "binary")

            n_correct = 0
            for trial in range(n_trials):
                trial_rng = np.random.RandomState(rng.randint(100000) + trial + si * 1000)
                target_idx = trial_rng.randint(P)
                query = corrupt_pattern(
                    selected[target_idx], noise_fraction, "binary", trial_rng
                )
                result = recall_pattern(net, query, target_idx=target_idx, rng=trial_rng)
                if result.correct:
                    n_correct += 1

            acc = n_correct / n_trials
            if acc >= 0.8:
                best_P = P
                best_acc = acc
            else:
                # Past capacity
                break

        capacity_per_count[si] = best_P
        recall_at_capacity[si] = best_acc

    # Find minimum sites for any recall
    min_sites = int(site_counts[-1])  # default to max
    for si, n_sites in enumerate(site_counts):
        if capacity_per_count[si] >= 2:  # at least 2 patterns
            min_sites = int(n_sites)
            break

    # Fit scaling exponent: P_max ~ N_sites^alpha
    valid = capacity_per_count > 0
    if np.sum(valid) >= 2:
        log_sites = np.log(site_counts[valid].astype(float))
        log_cap = np.log(capacity_per_count[valid] + 1e-10)
        # Simple linear regression in log-log space
        coeffs = np.polyfit(log_sites, log_cap, 1)
        alpha = float(coeffs[0])
    else:
        alpha = 0.0

    return BinaryHopfieldResult(
        site_counts=site_counts,
        n_modes=n_modes,
        capacity_per_site_count=capacity_per_count,
        recall_accuracy=recall_at_capacity,
        min_sites_for_recall=min_sites,
        capacity_scaling_exponent=alpha,
        verdict=bool(min_sites <= 32),
    )


# ═══════════════════════════════════════════════════════════════════════
# Track C — Multi-Shell Resonator
# ═══════════════════════════════════════════════════════════════════════

# ── H12: Actuator Q Penalty ──────────────────────────────────────────

def exp_actuator_q_penalty(
    n_actuators_range: Optional[np.ndarray] = None,
    rod_length: float = 1e-3,
    rod_diameter: float = 40e-6,
    glass_key: str = "borosilicate",
    actuator_footprint_um2: float = 100.0,
    actuator_Q: float = 500.0,
    actuator_thickness_nm: float = 200.0,
) -> ActuatorQResult:
    """
    Model the Q penalty of adding MEMS electrostatic switch structures
    near the rod surface.  Each actuator adds:
    - A lossy surface contact (electrode + air gap + latch pad)
    - Additional surface area in the defect layer model

    We extend the surface-loss model: each actuator contributes a
    localized high-loss region with its own Q_d and area fraction.

    Procedure
    ---------
    1. Compute baseline Q (no actuators) using full mems_q_model.
    2. For each actuator count:
       a. Add actuator loss: 1/Q_act = (n * A_act * t_act) / (V_rod * Q_act_material)
       b. Combine with existing 5-mechanism budget.
       c. Report total Q and penalty.
    3. Find max actuators before Q drops below 5,000.
    """
    if n_actuators_range is None:
        n_actuators_range = np.array([0, 4, 8, 16, 32, 64, 128, 256])

    db = glass_database()
    glass = db[glass_key]
    rod = RodGeometry(length=rod_length, diameter=rod_diameter)

    # Baseline Q (no actuators)
    anchor = AnchorDesign(
        n_anchors=2, tether_width=2e-6, tether_thickness=2e-6,
        tether_length=20e-6, isolation_trenches=True,
    )
    conditions = OperatingConditions(temperature=300.0, pressure=0.1)
    surface = SurfaceProperties(defect_layer_thickness=5e-9, defect_layer_Q=100.0)

    f1 = glass.v_bar / (2 * rod_length)  # FEM-validated thin-bar speed
    mode_n = 1

    q_mat = compute_Q_material(glass)
    q_anc = compute_Q_anchor(rod, glass, anchor, mode_n)
    q_ted = compute_Q_TED(rod, glass, f1, conditions)
    q_surf = compute_Q_surface(rod, surface)
    q_gas = compute_Q_gas(rod, glass, f1, conditions)

    baseline_loss = (1 / q_mat.Q_value + 1 / q_anc.Q_value +
                     1 / q_ted.Q_value + 1 / q_surf.Q_value + 1 / q_gas.Q_value)
    Q_baseline = 1.0 / baseline_loss

    # Rod volume
    V_rod = np.pi * (rod_diameter / 2) ** 2 * rod_length

    # Actuator loss contribution
    actuator_area = actuator_footprint_um2 * 1e-12  # m²
    actuator_thick = actuator_thickness_nm * 1e-9    # m

    results_Q = []
    for n_act in n_actuators_range:
        if n_act == 0:
            results_Q.append(Q_baseline)
            continue

        # Volume fraction of actuator material on the rod surface
        V_actuator = n_act * actuator_area * actuator_thick
        volume_frac = V_actuator / V_rod

        # Loss from actuator: 1/Q_actuator_contribution = volume_frac / Q_act_material
        actuator_loss = volume_frac / actuator_Q
        total_loss = baseline_loss + actuator_loss
        Q_total = 1.0 / total_loss
        results_Q.append(Q_total)

    results_Q = np.array(results_Q)

    # Find max actuators for Q > 5000
    max_act_5k = 0
    for i, n_act in enumerate(n_actuators_range):
        if results_Q[i] >= 5000:
            max_act_5k = int(n_act)

    # Use a representative middle value for the single-result output
    ref_idx = min(3, len(n_actuators_range) - 1)  # ~16 actuators
    ref_n = int(n_actuators_range[ref_idx])

    Q_with = float(results_Q[ref_idx])
    penalty = (Q_baseline - Q_with) / Q_baseline * 100

    V_act_ref = ref_n * actuator_area * actuator_thick
    act_loss_ref = (V_act_ref / V_rod) / actuator_Q
    act_frac = act_loss_ref / (baseline_loss + act_loss_ref) * 100

    return ActuatorQResult(
        n_actuators=ref_n,
        actuator_area_fraction=float(ref_n * actuator_area / (np.pi * rod_diameter * rod_length)),
        Q_no_actuator=Q_baseline,
        Q_with_actuator=Q_with,
        Q_penalty_pct=penalty,
        actuator_loss_fraction=act_frac,
        max_actuators_for_Q5000=max_act_5k,
        verdict=bool(Q_with >= 5000),
    )


# ── H13: Writable Shell Q Budget ────────────────────────────────────

def exp_writable_shell_q(
    shell_thicknesses_nm: Optional[np.ndarray] = None,
    shell_Q_values: Optional[np.ndarray] = None,
    rod_length: float = 1e-3,
    rod_diameter: float = 40e-6,
    glass_key: str = "borosilicate",
) -> WritableShellResult:
    """
    Parametric study: coat the glass rod with a thin "writable" shell
    of varying thickness and material Q.  The shell acts as a tunable
    perturbation layer.

    Candidate shell materials (in order of increasing controllability):
    - Parylene C coating (Q_d ~ 200, controllable thickness)
    - Magnetostrictive thin film (Terfenol-D, Q_d ~ 50-200)
    - Phase-change material (GST/VO2, Q_d ~ 20-100)
    - Polymer (PDMS, Q_d ~ 10-50)

    The shell adds surface loss: 1/Q_shell = (4 * t_shell / d_rod) / Q_d
    We sweep t_shell × Q_d and map the total Q landscape.

    Also compute the Rayleigh frequency shift from the shell mass,
    quantifying how much "write range" the shell provides.
    """
    if shell_thicknesses_nm is None:
        shell_thicknesses_nm = np.array([1, 2, 5, 10, 20, 50, 100, 200, 500, 1000])

    if shell_Q_values is None:
        shell_Q_values = np.array([10, 20, 50, 100, 200, 500, 1000, 5000])

    db = glass_database()
    glass = db[glass_key]
    rod = RodGeometry(length=rod_length, diameter=rod_diameter)

    # Baseline Q without shell
    anchor = AnchorDesign(
        n_anchors=2, tether_width=2e-6, tether_thickness=2e-6,
        tether_length=20e-6, isolation_trenches=True,
    )
    conditions = OperatingConditions(temperature=300.0, pressure=0.1)
    surface_base = SurfaceProperties(defect_layer_thickness=5e-9, defect_layer_Q=100.0)

    f1 = glass.v_bar / (2 * rod_length)  # FEM-validated thin-bar speed

    q_mat = compute_Q_material(glass)
    q_anc = compute_Q_anchor(rod, glass, anchor, 1)
    q_ted = compute_Q_TED(rod, glass, f1, conditions)
    q_surf_base = compute_Q_surface(rod, surface_base)
    q_gas = compute_Q_gas(rod, glass, f1, conditions)

    baseline_loss = (1 / q_mat.Q_value + 1 / q_anc.Q_value +
                     1 / q_ted.Q_value + 1 / q_surf_base.Q_value + 1 / q_gas.Q_value)

    # Sweep shell parameters
    n_thick = len(shell_thicknesses_nm)
    n_qd = len(shell_Q_values)
    total_Q_grid = np.zeros((n_thick, n_qd))

    for ti, t_nm in enumerate(shell_thicknesses_nm):
        t_m = t_nm * 1e-9
        for qi, Q_d in enumerate(shell_Q_values):
            # Shell loss: thin cylindrical coating
            # Volume fraction = 4 * t_shell / d_rod (for t << d)
            vol_frac = 4 * t_m / rod_diameter
            shell_loss = vol_frac / Q_d
            total_loss = baseline_loss + shell_loss
            total_Q_grid[ti, qi] = 1.0 / total_loss

    # Find Q=5000 boundary
    boundary = []
    for ti, t_nm in enumerate(shell_thicknesses_nm):
        for qi, Q_d in enumerate(shell_Q_values):
            if total_Q_grid[ti, qi] >= 5000:
                # Check if next thickness would drop below
                if ti + 1 < n_thick and total_Q_grid[ti + 1, qi] < 5000:
                    boundary.append((float(t_nm), float(Q_d)))
                elif ti == n_thick - 1 and total_Q_grid[ti, qi] >= 5000:
                    boundary.append((float(t_nm), float(Q_d)))

    # Maximum shell thickness at Q_d=200 (parylene-like) keeping Q > 5000
    max_thick = 0.0
    for ti, t_nm in enumerate(shell_thicknesses_nm):
        # Find closest Q_d to 200
        qi_200 = int(np.argmin(np.abs(shell_Q_values - 200)))
        if total_Q_grid[ti, qi_200] >= 5000:
            max_thick = float(t_nm)

    # Rayleigh frequency shift from max shell thickness
    # Δf/f ≈ -½ × (m_shell / m_rod) for uniform coating
    r = rod_diameter / 2
    V_rod = np.pi * r ** 2 * rod_length
    m_rod = V_rod * glass.density
    # Shell density ~ 1500 kg/m³ (generic polymer/coating)
    shell_density = 1500.0
    t_max_m = max_thick * 1e-9
    V_shell = 2 * np.pi * r * rod_length * t_max_m  # lateral surface × thickness
    m_shell = V_shell * shell_density
    freq_shift_pct = 0.5 * m_shell / m_rod * 100  # approximate

    return WritableShellResult(
        shell_thicknesses_nm=shell_thicknesses_nm,
        shell_Q_values=shell_Q_values,
        total_Q_grid=total_Q_grid,
        Q_5000_boundary=boundary,
        max_shell_thickness_nm=max_thick,
        frequency_shift_pct=freq_shift_pct,
        verdict=bool(max_thick > 0 and freq_shift_pct > 0.001),
    )


# ═══════════════════════════════════════════════════════════════════════
# Run all rewritability experiments
# ═══════════════════════════════════════════════════════════════════════

def run_all_rewritability(verbose: bool = True) -> dict:
    """Execute all seven rewritability experiments and return results."""
    results = {}
    rng = np.random.RandomState(42)

    if verbose:
        print("=" * 70)
        print("  REWRITABILITY EXPERIMENTS FOR SEM")
        print("=" * 70)

    # ── Track A: Firmware Virtual Rewriting ───────────────────────────

    if verbose:
        print("\n━━━ Track A: Firmware-Defined Virtual Rewriting ━━━")

    if verbose:
        print("\n▸ H7: Multi-Projection Virtual Rewrite...")
    r7 = exp_multi_projection(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["multi_projection"] = r7
    if verbose:
        v = "✅ CONFIRMED" if r7.verdict else "❌ NOT CONFIRMED"
        print(f"  Partitions:        {r7.n_partitions}")
        print(f"  Dims per partition: {r7.dims_per_partition}")
        print(f"  Mean fidelity:     {r7.mean_fidelity:.3f}")
        print(f"  Max cross-talk:    {r7.max_crosstalk:.4f}")
        print(f"  Effective devices: {r7.effective_devices}  → {v}")

    if verbose:
        print("\n▸ H8: Mode-Subset Logical Devices...")
    r8 = exp_mode_subset_devices(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["mode_subsets"] = r8
    if verbose:
        v = "✅ CONFIRMED" if r8.verdict else "❌ NOT CONFIRMED"
        print(f"  Total modes:       {r8.total_modes}")
        print(f"  Subsets:           {r8.n_subsets} × {r8.modes_per_subset} modes")
        print(f"  Recall per subset: {np.array2string(r8.recall_per_subset, precision=3)}")
        print(f"  Independent devs:  {r8.independent_devices}  → {v}")

    if verbose:
        print("\n▸ H9: Readout Mask Library...")
    r9 = exp_readout_mask_library(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["readout_masks"] = r9
    if verbose:
        v = "✅ CONFIRMED" if r9.verdict else "❌ NOT CONFIRMED"
        for mi in range(r9.n_masks):
            flag = " ★" if r9.recall_per_mask[mi] > 0.7 else ""
            print(f"    {r9.mask_descriptions[mi]:20s}  recall={r9.recall_per_mask[mi]:.3f}{flag}")
        print(f"  Masks above 70%:   {r9.masks_above_threshold}  → {v}")

    # ── Track B: Binary Perturbation Sites ───────────────────────────

    if verbose:
        print("\n━━━ Track B: Binary Perturbation Sites ━━━")

    if verbose:
        print("\n▸ H10: Binary Site Fingerprint Capacity...")
    r10 = exp_binary_fingerprints(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["binary_fingerprints"] = r10
    if verbose:
        v = "✅ CONFIRMED" if r10.verdict else "❌ NOT CONFIRMED"
        print(f"  Sites:             {r10.n_sites}")
        print(f"  Configs tested:    {r10.n_configurations_tested}")
        print(f"  Distinguishable:   {r10.n_distinguishable}")
        print(f"  Bits per rod:      {r10.bits_per_rod:.1f}")
        print(f"  Threshold:         {r10.n_sites/2:.0f} bits (2^(N/2) = {2**(r10.n_sites//2)})")
        print(f"  → {v}")

    if verbose:
        print("\n▸ H11: Binary-Site Hopfield Capacity...")
    r11 = exp_binary_hopfield_capacity(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["binary_hopfield"] = r11
    if verbose:
        v = "✅ CONFIRMED" if r11.verdict else "❌ NOT CONFIRMED"
        print(f"  Site counts:       {r11.site_counts}")
        print(f"  Capacity:          {r11.capacity_per_site_count}")
        print(f"  Min sites (≥2P):   {r11.min_sites_for_recall}")
        print(f"  Scaling exponent:  {r11.capacity_scaling_exponent:.2f}")
        print(f"  → {v}")

    # ── Track C: Multi-Shell Resonator ───────────────────────────────

    if verbose:
        print("\n━━━ Track C: Multi-Shell Resonator ━━━")

    if verbose:
        print("\n▸ H12: Actuator Q Penalty...")
    r12 = exp_actuator_q_penalty()
    results["actuator_q"] = r12
    if verbose:
        v = "✅ CONFIRMED" if r12.verdict else "❌ NOT CONFIRMED"
        print(f"  Baseline Q:        {r12.Q_no_actuator:.0f}")
        print(f"  Q with {r12.n_actuators} acts:  {r12.Q_with_actuator:.0f}")
        print(f"  Q penalty:         {r12.Q_penalty_pct:.2f}%")
        print(f"  Actuator loss:     {r12.actuator_loss_fraction:.2f}% of total")
        print(f"  Max acts (Q>5k):   {r12.max_actuators_for_Q5000}")
        print(f"  → {v}")

    if verbose:
        print("\n▸ H13: Writable Shell Q Budget...")
    r13 = exp_writable_shell_q()
    results["writable_shell"] = r13
    if verbose:
        v = "✅ CONFIRMED" if r13.verdict else "❌ NOT CONFIRMED"
        print(f"  Max shell (Q>5k):  {r13.max_shell_thickness_nm:.0f} nm")
        print(f"  Freq shift range:  {r13.frequency_shift_pct:.4f}%")
        print(f"  Q=5000 boundary:   {len(r13.Q_5000_boundary)} points")
        if r13.Q_5000_boundary:
            for t, qd in r13.Q_5000_boundary[:5]:
                print(f"    t={t:.0f} nm, Q_d={qd:.0f}")
        print(f"  → {v}")

    # ── Summary ──────────────────────────────────────────────────────

    if verbose:
        print("\n" + "=" * 70)
        n_pass = sum(1 for r in results.values() if r.verdict)
        print(f"  TOTAL: {n_pass}/7 hypotheses confirmed")
        print("=" * 70)

        # Architecture recommendation
        print("\n  ARCHITECTURE IMPLICATIONS:")
        if r7.verdict:
            print(f"  ✦ Multi-projection: {r7.effective_devices} virtual devices")
            print(f"    from one rod (cross-talk < {r7.max_crosstalk:.1e})")
        if r8.verdict:
            print(f"  ✦ Mode subsets: {r8.independent_devices} independent bands")
        if r9.verdict:
            print(f"  ✦ Readout masks: {r9.masks_above_threshold} firmware-selectable configs")
        if r10.verdict:
            print(f"  ✦ Binary sites: {r10.bits_per_rod:.1f} bits rewritable state")
        if r12.verdict:
            print(f"  ✦ Actuators: up to {r12.max_actuators_for_Q5000} switches at Q > 5k")
        if r13.verdict:
            print(f"  ✦ Shell: up to {r13.max_shell_thickness_nm:.0f} nm writable layer")

    return results
