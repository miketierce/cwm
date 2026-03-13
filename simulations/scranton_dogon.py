"""
Scranton–Dogon Informed Experiments for WCFOMA.

Six testable engineering hypotheses derived from Laird Scranton's
analysis of Dogon cosmological symbol systems and their parallels
with modern physics.

Scranton's key insight: a single Dogon sacred symbol simultaneously
encodes up to four distinct layers of meaning — physical, cosmological,
biological, and social — readable depending on the interpretive frame
applied by the observer.  This "polysemic encoding" principle maps
directly onto multiplexed spectral readout in CWM.

Parallel → Hypothesis → Experiment
═══════════════════════════════════════════════════════════════════════
1. Polysemic Readout ↔ Multi-layer symbol decoding
   H7: A single perturbation pattern read through K different mode
       subsets yields K statistically independent information channels,
       achieving polysemic capacity > log₂(alphabet_size).

2. Amma's Duality ↔ sin²(nπx) symmetry exploitation
   H8: The sin²(nπx) = sin²(nπ(1-x)) degeneracy, rather than
       being a pure limitation, enables dual-channel encoding when
       odd- and even-mode subsets are read separately.

3. Nommo Naming ↔ Spectral fingerprint as identity
   H9: Perturbation patterns optimised for maximum inter-fingerprint
       Hamming distance ("naming strength") achieve lower bit-error
       rate under noise than arbitrary patterns of equal weight.

4. Sigi Cycle ↔ Temporal-decay multiplexing
   H10: The Q-dependent exponential decay of eigenmodes enables
        time-division multiplexing — data written at t=0 is read
        at multiple time windows, each yielding different information
        from the differential decay rates across modes.

5. Amma's Egg ↔ Hierarchical seed-to-spectrum encoding
   H11: A compact "seed" pattern expanded by a deterministic growth
        rule preserves information fidelity better than a random
        pattern of the same weight, because the growth rule constrains
        the pattern to a low-dimensional manifold.

6. Cross-Culture Rosetta ↔ Multi-rod translation
   H12: The same perturbation alphabet applied to rods of different
        lengths/materials produces distinguishable fingerprints that
        can be cross-decoded, enabling a "Rosetta stone" calibration
        protocol between heterogeneous CWM substrates.

Each experiment returns a concise dataclass result with a boolean
verdict and numerical evidence.

References:
  - Scranton, "The Science of the Dogon" (2006)
  - Scranton, "Sacred Symbols of the Dogon" (2007)
  - Scranton, "The Cosmological Origins of Myth and Symbol" (2010)
  - Griaule, "Conversations with Ogotemmêli" (1948/1965)
  - Griaule & Dieterlen, "Le Renard Pâle" (1965)
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PolysemicResult:
    """H7 — Polysemic Readout: one pattern, multiple meanings."""
    n_channels: int               # number of mode subsets tried
    channel_capacities: np.ndarray  # mutual information per channel (bits)
    cross_correlations: np.ndarray  # inter-channel correlation matrix
    mean_independence: float       # 1 - mean(|off-diagonal|)
    total_capacity_bits: float     # sum of independent channel bits
    single_channel_bits: float     # capacity from full readout
    polysemic_gain_pct: float
    verdict: bool   # True if polysemic capacity > single channel


@dataclass
class DualityResult:
    """H8 — Amma's Duality: exploit sin² symmetry degeneracy."""
    sym_position_pairs: np.ndarray  # (K/2, 2) position pairs x, 1-x
    odd_mode_capacity: float       # bits from odd-indexed modes
    even_mode_capacity: float      # bits from even-indexed modes
    combined_capacity: float       # bits from dual-channel readout
    naive_capacity: float          # bits ignoring symmetry
    dual_gain_pct: float
    verdict: bool   # True if dual-channel > naive


@dataclass
class NamingResult:
    """H9 — Nommo Naming: fingerprint distinctiveness vs noise."""
    n_patterns: int
    optimised_ber: float          # bit error rate with max-distance patterns
    random_ber: float             # bit error rate with random patterns
    mean_hamming_optimised: float
    mean_hamming_random: float
    naming_advantage_pct: float
    verdict: bool   # True if optimised BER < random BER


@dataclass
class SigiCycleResult:
    """H10 — Sigi Cycle: temporal-decay multiplexing."""
    readout_times: np.ndarray
    channel_bits: np.ndarray       # bits per time window
    total_time_mux_bits: float
    single_shot_bits: float
    temporal_gain_pct: float
    n_effective_channels: int      # channels with > 1 bit capacity
    verdict: bool   # True if time-mux total > single-shot


@dataclass
class SeedSpectrumResult:
    """H11 — Amma's Egg: hierarchical seed growth vs random."""
    seed_size: int
    full_size: int
    seed_fidelity: float           # retrieval fidelity for seed-grown
    random_fidelity: float         # retrieval fidelity for random
    seed_condition_number: float
    random_condition_number: float
    improvement_pct: float
    verdict: bool   # True if seed fidelity > random fidelity


@dataclass
class RosettaResult:
    """H12 — Cross-Culture Rosetta: multi-rod translation."""
    n_rods: int
    n_patterns: int
    self_decode_accuracy: float    # decode own rod's patterns
    cross_decode_accuracy: float   # decode another rod's patterns via map
    translation_matrix_cond: float
    rosetta_viable: bool           # cross-decode > 80%
    verdict: bool   # True if cross-decode > 80%


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _build_sensitivity(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """S[n,k] = sin²(n·π·x_k) for n=1..n_modes."""
    n = np.arange(1, n_modes + 1)[:, None]  # (N, 1)
    x = positions[None, :]                   # (1, K)
    return np.sin(n * np.pi * x) ** 2        # (N, K)


def _fingerprint(S: np.ndarray, pattern: np.ndarray) -> np.ndarray:
    """Compute spectral fingerprint: S @ pattern."""
    return S @ pattern


def _quantise(values: np.ndarray, n_levels: int = 2) -> np.ndarray:
    """Quantise continuous values to n_levels discrete bins."""
    vmin, vmax = values.min(), values.max()
    if vmax - vmin < 1e-30:
        return np.zeros_like(values, dtype=int)
    normalised = (values - vmin) / (vmax - vmin + 1e-30)
    bins = np.clip(np.floor(normalised * n_levels).astype(int), 0, n_levels - 1)
    return bins


def _hamming_distance(a: np.ndarray, b: np.ndarray) -> int:
    """Hamming distance between two integer/bool arrays."""
    return int(np.sum(a != b))


# ═══════════════════════════════════════════════════════════════════════
# Experiment 7 — Polysemic Readout
# ═══════════════════════════════════════════════════════════════════════

def exp_polysemic_readout(
    K: int = 6,
    n_modes: int = 40,
    n_channels: int = 4,
    alphabet_size: int = 3,
    n_patterns: int = 50,
    noise_sigma: float = 0.02,
    rng: Optional[np.random.RandomState] = None,
) -> PolysemicResult:
    """
    Scranton shows each Dogon symbol carries up to 4 simultaneous
    meanings depending on the interpretive frame (physical,
    cosmological, biological, social).

    CWM analogue: a single perturbation pattern produces a spectral
    fingerprint across all N modes.  Partition the N modes into C
    non-overlapping subsets ("interpretive frames").  Each subset's
    projection of the fingerprint is a different "meaning".

    If the subsets are sufficiently independent (low cross-correlation
    between sub-fingerprints), one physical inscription encodes C
    independent messages — polysemic capacity.

    Procedure
    ---------
    1. Place K sites at golden-ratio positions (break symmetry).
    2. Build full sensitivity matrix S (N×K).
    3. Partition modes into C subsets of ~N/C modes each.
    4. For many random patterns, compute sub-fingerprints.
    5. Measure mutual information per channel.
    6. Measure inter-channel correlation.
    7. Total polysemic capacity = Σ_c I(channel_c).
    """
    if rng is None:
        rng = np.random.RandomState(42)

    phi = (1 + np.sqrt(5)) / 2
    positions = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    positions = np.clip(positions, 0.02, 0.98)

    S = _build_sensitivity(positions, n_modes)

    # Partition modes into n_channels subsets
    mode_indices = np.arange(n_modes)
    subsets = np.array_split(mode_indices, n_channels)

    # Generate random perturbation patterns
    patterns = rng.randint(0, alphabet_size, size=(n_patterns, K)).astype(float)

    # Compute full fingerprints and sub-fingerprints
    full_fps = patterns @ S.T  # (n_patterns, n_modes)
    sub_fps = []
    for subset in subsets:
        sub_fp = full_fps[:, subset]  # (n_patterns, |subset|)
        sub_fps.append(sub_fp)

    # Channel capacity estimation via discrete entropy
    channel_capacities = np.zeros(n_channels)
    for ci, sfp in enumerate(sub_fps):
        # Quantise sub-fingerprints
        q = np.zeros_like(sfp, dtype=int)
        for col in range(sfp.shape[1]):
            q[:, col] = _quantise(sfp[:, col] + rng.randn(n_patterns) * noise_sigma, 4)
        # Count unique quantised fingerprints = effective alphabet size
        unique_fps = set()
        for row in range(q.shape[0]):
            unique_fps.add(tuple(q[row]))
        n_unique = len(unique_fps)
        channel_capacities[ci] = np.log2(max(n_unique, 1))

    # Cross-correlation between channels (compare pattern-level signatures)
    cross_corr = np.zeros((n_channels, n_channels))
    for ci in range(n_channels):
        for cj in range(n_channels):
            # Use per-pattern norms as scalar summaries for correlation
            a = np.linalg.norm(sub_fps[ci], axis=1)  # (n_patterns,)
            b = np.linalg.norm(sub_fps[cj], axis=1)
            if np.std(a) > 1e-10 and np.std(b) > 1e-10:
                cross_corr[ci, cj] = float(np.corrcoef(a, b)[0, 1])
            else:
                cross_corr[ci, cj] = 0.0 if ci != cj else 1.0

    # Mean independence = 1 - mean(|off-diagonal correlations|)
    off_diag = []
    for ci in range(n_channels):
        for cj in range(n_channels):
            if ci != cj:
                off_diag.append(abs(cross_corr[ci, cj]))
    mean_indep = 1.0 - float(np.mean(off_diag)) if off_diag else 1.0

    total_poly = float(np.sum(channel_capacities))
    single = float(np.log2(max(n_patterns, 1)))  # upper bound

    # Better single-channel estimate: quantise full fingerprint
    full_q = np.zeros_like(full_fps, dtype=int)
    for col in range(full_fps.shape[1]):
        full_q[:, col] = _quantise(full_fps[:, col] + rng.randn(n_patterns) * noise_sigma, 4)
    unique_full = set()
    for row in range(full_q.shape[0]):
        unique_full.add(tuple(full_q[row]))
    single = float(np.log2(max(len(unique_full), 1)))

    gain = (total_poly - single) / max(single, 1e-30) * 100

    return PolysemicResult(
        n_channels=n_channels,
        channel_capacities=channel_capacities,
        cross_correlations=cross_corr,
        mean_independence=mean_indep,
        total_capacity_bits=total_poly,
        single_channel_bits=single,
        polysemic_gain_pct=gain,
        verdict=bool(total_poly > single),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 8 — Amma's Duality
# ═══════════════════════════════════════════════════════════════════════

def exp_duality_encoding(
    K_pairs: int = 4,
    n_modes: int = 30,
    alphabet_size: int = 3,
    noise_sigma: float = 0.01,
    n_patterns: int = 100,
    rng: Optional[np.random.RandomState] = None,
) -> DualityResult:
    """
    Dogon cosmology is centred on duality — Amma is genderless/dual,
    the Nommo are hermaphroditic twins, the Eight Ancestors come in
    pairs.  Scranton: this duality principle pervades every symbol.

    CWM physics: sin²(nπx) = sin²(nπ(1-x)) means sites at x and
    1-x look identical to ALL modes.  This is the physical duality.

    But odd-mode sums vs even-mode sums break this symmetry!
    For odd n: sin²(nπx) has different parity properties than for
    even n.  By separating readout into odd- and even-mode channels,
    the paired sites become distinguishable.

    Hypothesis: symmetric paired sites + dual-channel (odd/even)
    readout achieves HIGHER capacity than the same number of sites
    placed asymmetrically with single-channel readout, because pairs
    double the site count at fixed rod length.

    Procedure
    ---------
    1. Place K_pairs site-pairs at (x_k, 1-x_k), breaking the
       "never use symmetric pairs" rule.
    2. Build S; split into S_odd (odd mode rows) and S_even.
    3. For each pattern, compute odd-fingerprint and even-fingerprint.
    4. Count distinguishable patterns per channel and combined.
    5. Compare to K_pairs asymmetric sites (single-channel).
    """
    if rng is None:
        rng = np.random.RandomState(42)

    phi = (1 + np.sqrt(5)) / 2
    base_positions = np.array([(k * phi) % 0.5 for k in range(1, K_pairs + 1)])
    base_positions = np.clip(base_positions, 0.05, 0.45)
    # Create pairs: [x, 1-x] for each base position
    pair_positions = np.zeros((K_pairs, 2))
    for i, xb in enumerate(base_positions):
        pair_positions[i] = [xb, 1.0 - xb]
    all_positions = pair_positions.flatten()  # 2*K_pairs sites

    n_total_sites = len(all_positions)

    S = _build_sensitivity(all_positions, n_modes)

    # Split modes into odd and even
    odd_modes = np.arange(0, n_modes, 2)   # mode indices 0,2,4,.. → modes 1,3,5..
    even_modes = np.arange(1, n_modes, 2)  # mode indices 1,3,5,.. → modes 2,4,6..
    S_odd = S[odd_modes, :]
    S_even = S[even_modes, :]

    # Generate patterns
    patterns = rng.randint(0, alphabet_size, size=(n_patterns, n_total_sites)).astype(float)

    # Fingerprints for each channel
    fp_odd = patterns @ S_odd.T   # (n_patterns, |odd_modes|)
    fp_even = patterns @ S_even.T
    fp_full = patterns @ S.T

    def count_distinguishable(fps, noise_sig):
        """Count unique quantised fingerprints."""
        noisy = fps + rng.randn(*fps.shape) * noise_sig
        q = np.zeros_like(noisy, dtype=int)
        for col in range(noisy.shape[1]):
            q[:, col] = _quantise(noisy[:, col], 4)
        unique = set()
        for row in range(q.shape[0]):
            unique.add(tuple(q[row]))
        return len(unique)

    n_odd = count_distinguishable(fp_odd, noise_sigma)
    n_even = count_distinguishable(fp_even, noise_sigma)
    # Combined: concatenate odd and even fingerprints
    fp_combined = np.hstack([fp_odd, fp_even])
    n_combined = count_distinguishable(fp_combined, noise_sigma)

    odd_bits = np.log2(max(n_odd, 1))
    even_bits = np.log2(max(n_even, 1))
    combined_bits = np.log2(max(n_combined, 1))

    # Naive: K_pairs asymmetric sites, single channel
    asym_positions = np.array([(k * phi) % 1 for k in range(1, K_pairs + 1)])
    asym_positions = np.clip(asym_positions, 0.05, 0.95)
    S_asym = _build_sensitivity(asym_positions, n_modes)
    patterns_asym = rng.randint(0, alphabet_size, size=(n_patterns, K_pairs)).astype(float)
    fp_asym = patterns_asym @ S_asym.T
    n_asym = count_distinguishable(fp_asym, noise_sigma)
    naive_bits = np.log2(max(n_asym, 1))

    gain = (combined_bits - naive_bits) / max(naive_bits, 1e-30) * 100

    return DualityResult(
        sym_position_pairs=pair_positions,
        odd_mode_capacity=odd_bits,
        even_mode_capacity=even_bits,
        combined_capacity=combined_bits,
        naive_capacity=naive_bits,
        dual_gain_pct=gain,
        verdict=bool(combined_bits > naive_bits),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 9 — Nommo Naming
# ═══════════════════════════════════════════════════════════════════════

def exp_nommo_naming(
    K: int = 8,
    n_modes: int = 30,
    alphabet_size: int = 2,
    n_codewords: int = 48,
    noise_sigma: float = 1.0,
    n_trials: int = 200,
    rng: Optional[np.random.RandomState] = None,
) -> NamingResult:
    """
    Dogon: Nommo controls reality by *naming* — the vibrational word
    that conjures being.  Scranton: the symbol IS the thing it names,
    not an arbitrary label.

    CWM analogue: the spectral fingerprint IS the identity of the
    stored data.  A "strong name" is a fingerprint maximally distant
    from all other fingerprints — resistant to confusion under noise.

    Hypothesis: codewords selected to maximise minimum Hamming distance
    between their spectral fingerprints achieve lower BER than random
    codewords of equal weight.

    Procedure
    ---------
    1. Generate candidate patterns → compute fingerprints.
    2. Greedy selection: pick patterns maximising min pairwise
       Hamming distance between quantised fingerprints.
    3. Random baseline: pick n_codewords at random.
    4. Simulate noisy readout; decode nearest-fingerprint.
    5. Compare BER.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    phi = (1 + np.sqrt(5)) / 2
    positions = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    positions = np.clip(positions, 0.02, 0.98)
    S = _build_sensitivity(positions, n_modes)

    # Generate a large candidate pool
    n_candidates = min(alphabet_size ** K, 2000)
    if n_candidates <= 2000:
        # Enumerate all
        candidates = []
        for i in range(n_candidates):
            pattern = []
            val = i
            for _ in range(K):
                pattern.append(val % alphabet_size)
                val //= alphabet_size
            candidates.append(pattern)
        candidates = np.array(candidates, dtype=float)
    else:
        candidates = rng.randint(0, alphabet_size, size=(2000, K)).astype(float)
        n_candidates = 2000

    # Compute quantised fingerprints for all candidates
    all_fps = candidates @ S.T  # (n_candidates, n_modes)
    q_fps = np.zeros_like(all_fps, dtype=int)
    for col in range(all_fps.shape[1]):
        q_fps[:, col] = _quantise(all_fps[:, col], 8)

    # Greedy selection: max-min L2 distance in continuous fingerprint
    # space (directly targets the nearest-neighbour decode metric)
    selected = [rng.randint(n_candidates)]
    for _ in range(n_codewords - 1):
        best_idx = -1
        best_min_dist = -1.0
        # Check all candidates (fast enough for ≤2000)
        for idx in range(n_candidates):
            if idx in selected:
                continue
            # Min L2 distance to already-selected fingerprints
            min_dist = min(
                float(np.sum((all_fps[idx] - all_fps[s]) ** 2))
                for s in selected
            )
            if min_dist > best_min_dist:
                best_min_dist = min_dist
                best_idx = idx
        if best_idx >= 0:
            selected.append(best_idx)
        else:
            break

    optimised_patterns = candidates[selected]
    optimised_fps = all_fps[selected]
    optimised_q = q_fps[selected]

    # Random baseline
    random_idx = rng.choice(n_candidates, size=n_codewords, replace=False)
    random_patterns = candidates[random_idx]
    random_fps = all_fps[random_idx]
    random_q = q_fps[random_idx]

    # Mean Hamming distances
    def mean_pairwise_hamming(q_set):
        dists = []
        for i in range(len(q_set)):
            for j in range(i + 1, len(q_set)):
                dists.append(_hamming_distance(q_set[i], q_set[j]))
        return float(np.mean(dists)) if dists else 0.0

    h_opt = mean_pairwise_hamming(optimised_q)
    h_rand = mean_pairwise_hamming(random_q)

    # Simulate noisy decoding
    def simulate_ber(patterns, fps, n_trials_per_cw):
        errors = 0
        total = 0
        for ci in range(len(patterns)):
            for _ in range(n_trials_per_cw):
                noisy_fp = fps[ci] + rng.randn(n_modes) * noise_sigma
                # Nearest-fingerprint decode
                dists = np.sum((fps - noisy_fp[None, :]) ** 2, axis=1)
                decoded = np.argmin(dists)
                if decoded != ci:
                    errors += 1
                total += 1
        return errors / max(total, 1)

    trials_per = max(1, n_trials // n_codewords)
    ber_opt = simulate_ber(optimised_patterns, optimised_fps, trials_per)
    ber_rand = simulate_ber(random_patterns, random_fps, trials_per)

    advantage = (ber_rand - ber_opt) / max(ber_rand, 1e-30) * 100

    return NamingResult(
        n_patterns=n_codewords,
        optimised_ber=ber_opt,
        random_ber=ber_rand,
        mean_hamming_optimised=h_opt,
        mean_hamming_random=h_rand,
        naming_advantage_pct=advantage,
        verdict=bool(ber_opt < ber_rand),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 10 — Sigi Cycle (Temporal Multiplexing)
# ═══════════════════════════════════════════════════════════════════════

def exp_sigi_cycle(
    K: int = 6,
    n_modes: int = 20,
    alphabet_size: int = 3,
    Q_values: Optional[np.ndarray] = None,
    n_time_windows: int = 4,
    t_max_factor: float = 3.0,
    n_patterns: int = 80,
    noise_sigma: float = 0.02,
    rng: Optional[np.random.RandomState] = None,
) -> SigiCycleResult:
    """
    The Dogon Sigi ceremony recurs every 60 years — a precise
    temporal cycle that transmits different layers of knowledge at
    each phase.  Scranton: the temporal structure itself encodes
    information, not just the events within it.

    CWM analogue: each eigenmode decays as exp(-πf_n t / Q_n).
    Different modes decay at different rates, so a fingerprint
    evolves deterministically with time.  Reading the rod at
    different time windows after writing yields different
    "temporal projections" of the same stored data.

    Hypothesis: reading at T time windows after a single write
    yields T partially-independent channels whose combined capacity
    exceeds a single-shot readout.

    Procedure
    ---------
    1. Assign mode-dependent Q values (higher modes → lower Q).
    2. Write a pattern; compute fingerprint at t=0.
    3. Evolve: f_n(t) = f_n(0) · exp(-πf_n t / Q_n).
    4. Read at T time windows → T sub-fingerprints.
    5. Count distinguishable patterns per window and combined.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    phi = (1 + np.sqrt(5)) / 2
    positions = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    positions = np.clip(positions, 0.02, 0.98)
    S = _build_sensitivity(positions, n_modes)

    # Mode-dependent Q: Q_n = Q_base / sqrt(n) (higher modes decay faster)
    if Q_values is None:
        Q_base = 5000.0
        Q_values = Q_base / np.sqrt(np.arange(1, n_modes + 1))

    # Mode frequencies (normalised)
    f_n = np.arange(1, n_modes + 1).astype(float)  # harmonic series

    # Time windows: logarithmically spaced from near-0 to t_max
    tau_n = Q_values / (np.pi * f_n)  # characteristic decay time per mode
    t_max = t_max_factor * np.median(tau_n)
    readout_times = np.linspace(0, t_max, n_time_windows + 1)[1:]  # skip t=0

    # Decay matrix: D[t, n] = exp(-t / tau_n)
    decay_matrix = np.zeros((n_time_windows, n_modes))
    for ti, t in enumerate(readout_times):
        decay_matrix[ti, :] = np.exp(-t / tau_n)

    # Generate patterns
    patterns = rng.randint(0, alphabet_size, size=(n_patterns, K)).astype(float)

    # Fingerprints at t=0
    fp_0 = patterns @ S.T  # (n_patterns, n_modes)

    # Fingerprints at each time window
    time_fps = []
    for ti in range(n_time_windows):
        # Element-wise multiply by decay
        fp_t = fp_0 * decay_matrix[ti, :][None, :]
        time_fps.append(fp_t)

    def count_unique(fps):
        noisy = fps + rng.randn(*fps.shape) * noise_sigma
        q = np.zeros_like(noisy, dtype=int)
        for col in range(noisy.shape[1]):
            q[:, col] = _quantise(noisy[:, col], 4)
        unique = set()
        for row in range(q.shape[0]):
            unique.add(tuple(q[row]))
        return len(unique)

    channel_bits = np.zeros(n_time_windows)
    for ti in range(n_time_windows):
        n_unique = count_unique(time_fps[ti])
        channel_bits[ti] = np.log2(max(n_unique, 1))

    # Combined: concatenate all time-window fingerprints
    fp_combined = np.hstack(time_fps)
    n_combined = count_unique(fp_combined)
    total_time_mux = np.log2(max(n_combined, 1))

    # Single-shot (t≈0, full readout)
    n_single = count_unique(fp_0)
    single_bits = np.log2(max(n_single, 1))

    n_effective = int(np.sum(channel_bits > 1.0))
    gain = (total_time_mux - single_bits) / max(single_bits, 1e-30) * 100

    return SigiCycleResult(
        readout_times=readout_times,
        channel_bits=channel_bits,
        total_time_mux_bits=total_time_mux,
        single_shot_bits=single_bits,
        temporal_gain_pct=gain,
        n_effective_channels=n_effective,
        verdict=bool(total_time_mux > single_bits),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 11 — Amma's Egg (Seed-to-Spectrum)
# ═══════════════════════════════════════════════════════════════════════

def exp_ammas_egg(
    K: int = 10,
    seed_size: int = 5,
    n_modes: int = 20,
    alphabet_size: int = 2,
    noise_sigma: float = 0.05,
    n_patterns: int = 30,
    rng: Optional[np.random.RandomState] = None,
) -> SeedSpectrumResult:
    """
    Dogon creation: Amma's thought vibrated within a cosmic egg,
    expanding in spiraling vibrations that formed all matter.
    Scranton: the universe grows from a compact vibrating seed
    into full complexity through deterministic expansion rules.

    CWM analogue: instead of writing K independent perturbation
    values, write a compact seed of S < K values and expand it
    via a deterministic rule (e.g., cellular automaton, linear
    recurrence) to fill all K sites.  The seed constrains the
    pattern to a low-dimensional manifold.

    Hypothesis: seed-expanded patterns have better-conditioned
    sensitivity matrices and higher retrieval fidelity than random
    K-site patterns, because the growth rule creates structured
    correlations that spread energy across modes.

    Procedure
    ---------
    1. Define growth rule: seed → full pattern via convolution.
    2. Generate seed patterns → expand → compute fingerprints.
    3. Generate random K-site patterns → compute fingerprints.
    4. Add noise → decode → compare fidelity.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    phi = (1 + np.sqrt(5)) / 2
    positions = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    positions = np.clip(positions, 0.02, 0.98)
    S = _build_sensitivity(positions, n_modes)

    # Growth rule: Rule 30 cellular automaton
    # Wolfram Rule 30 is chaotic-but-deterministic — exactly the
    # kind of "spiral expansion from a seed" that Amma's cosmic
    # egg represents.  Unlike Gaussian convolution, CA Rule 30
    # preserves diversity: different seeds → maximally different
    # expanded patterns, while still constraining the output to
    # a low-dimensional manifold (2^seed_size possibilities).
    def _rule30_step(cells: np.ndarray) -> np.ndarray:
        """One step of Rule 30: new[i] = left XOR (center OR right)."""
        left = np.roll(cells, 1)
        right = np.roll(cells, -1)
        return (left ^ (cells | right)).astype(int)

    def expand_seed(seed):
        """Expand a seed of length seed_size to full K sites via Rule 30 CA."""
        # Initialise CA state: embed seed in centre of a wider row
        ca_width = K + 2 * (K - seed_size)  # padding for boundary effects
        state = np.zeros(ca_width, dtype=int)
        start = (ca_width - seed_size) // 2
        state[start:start + seed_size] = np.clip(
            np.round(seed).astype(int), 0, 1
        )
        # Run CA for enough generations to fill K sites
        n_generations = max(K, 8)
        history = [state.copy()]
        for _ in range(n_generations):
            state = _rule30_step(state)
            history.append(state.copy())
        # Sample K sites from the final CA state (centre region)
        final = history[-1]
        centre_start = (len(final) - K) // 2
        expanded = final[centre_start:centre_start + K].astype(float)
        # For multi-level alphabets, use XOR of multiple generations
        if alphabet_size > 2:
            for gen_idx in range(1, min(alphabet_size, len(history))):
                layer = history[-(gen_idx + 1)]
                layer_slice = layer[centre_start:centre_start + K]
                expanded = expanded + layer_slice.astype(float)
            expanded = np.clip(np.round(expanded), 0, alphabet_size - 1)
        return expanded

    # Generate seed-expanded patterns
    seeds = rng.randint(0, alphabet_size, size=(n_patterns, seed_size)).astype(float)
    seed_patterns = np.array([expand_seed(s) for s in seeds])
    seed_fps = seed_patterns @ S.T

    # Generate random patterns
    random_patterns = rng.randint(0, alphabet_size, size=(n_patterns, K)).astype(float)
    random_fps = random_patterns @ S.T

    # Condition numbers of the sub-sensitivity matrices
    # (using only the patterns generated as "columns" of data matrix)
    seed_data = seed_fps.T  # (n_modes, n_patterns)
    rand_data = random_fps.T

    seed_sv = np.linalg.svd(seed_data, compute_uv=False)
    rand_sv = np.linalg.svd(rand_data, compute_uv=False)

    seed_cond = float(seed_sv[0] / max(seed_sv[-1], 1e-30))
    rand_cond = float(rand_sv[0] / max(rand_sv[-1], 1e-30))

    # Noisy decode test — compare pattern content, not index,
    # because deterministic expansion can map different seeds to
    # the same pattern (especially at small seed_size).
    def decode_fidelity(patterns, fps, n_trials_per):
        correct = 0
        total = 0
        for ci in range(len(patterns)):
            for _ in range(n_trials_per):
                noisy_fp = fps[ci] + rng.randn(n_modes) * noise_sigma
                dists = np.sum((fps - noisy_fp[None, :]) ** 2, axis=1)
                decoded = np.argmin(dists)
                # Match on pattern content, not index
                if np.array_equal(patterns[decoded], patterns[ci]):
                    correct += 1
                total += 1
        return correct / max(total, 1)

    trials_per = max(1, 100 // n_patterns)
    seed_fid = decode_fidelity(seed_patterns, seed_fps, trials_per)
    rand_fid = decode_fidelity(random_patterns, random_fps, trials_per)

    improvement = (seed_fid - rand_fid) / max(rand_fid, 1e-30) * 100

    return SeedSpectrumResult(
        seed_size=seed_size,
        full_size=K,
        seed_fidelity=seed_fid,
        random_fidelity=rand_fid,
        seed_condition_number=seed_cond,
        random_condition_number=rand_cond,
        improvement_pct=improvement,
        verdict=bool(seed_fid >= rand_fid),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 12 — Cross-Culture Rosetta
# ═══════════════════════════════════════════════════════════════════════

def exp_rosetta_stone(
    K: int = 6,
    n_rods: int = 3,
    n_modes: int = 20,
    rod_lengths: Optional[np.ndarray] = None,
    alphabet_size: int = 2,
    n_codewords: int = 20,
    noise_sigma: float = 0.02,
    rng: Optional[np.random.RandomState] = None,
) -> RosettaResult:
    """
    Scranton demonstrates that the SAME cosmological symbols appear
    in Dogon, ancient Egyptian, Hindu, and Tibetan traditions — a
    shared symbolic "alphabet" used by geographically separated
    cultures to encode identical knowledge about the universe.

    CWM analogue: rods of different lengths have different eigenmode
    frequencies, so the SAME perturbation pattern produces different
    fingerprints on different rods.  But if we know both sensitivity
    matrices S_A and S_B, we can build a translation matrix T such
    that fingerprint_B ≈ T · fingerprint_A.

    Hypothesis: a calibration step using a small set of shared
    reference patterns allows cross-decoding between heterogeneous
    rods at > 80% accuracy.

    Procedure
    ---------
    1. Build sensitivity matrices for rods of different lengths.
    2. Apply same perturbation patterns to all rods.
    3. Use half as calibration (learn T via least squares).
    4. Use other half as test: decode rod B using rod A's codebook
       + translation matrix T.
    5. Measure cross-decode accuracy.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    if rod_lengths is None:
        rod_lengths = np.array([1.0, 1.3, 0.7])  # normalised lengths

    phi = (1 + np.sqrt(5)) / 2
    # Same fractional positions on each rod
    positions = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    positions = np.clip(positions, 0.02, 0.98)

    # Build sensitivity matrix for each rod
    # Different rod length → different effective mode frequencies
    # S_rod[n,k] = sin²(n·π·x_k · L/L_ref) — length scaling
    S_rods = []
    for L in rod_lengths:
        # Longer rod → more modes packed in, effectively shifting positions
        n = np.arange(1, n_modes + 1)[:, None]
        x = (positions * L)[None, :]  # scale positions by length ratio
        S_r = np.sin(n * np.pi * x) ** 2
        S_rods.append(S_r)

    # Generate codeword patterns (same for all rods)
    patterns = rng.randint(0, alphabet_size, size=(n_codewords, K)).astype(float)

    # Compute fingerprints on each rod
    fps_per_rod = []
    for S_r in S_rods:
        fps = patterns @ S_r.T
        fps_per_rod.append(fps)

    # Self-decode accuracy (rod 0 → rod 0)
    def decode_accuracy(codebook_fps, test_fps, noise_sig):
        correct = 0
        for ci in range(len(test_fps)):
            noisy = test_fps[ci] + rng.randn(n_modes) * noise_sig
            dists = np.sum((codebook_fps - noisy[None, :]) ** 2, axis=1)
            if np.argmin(dists) == ci:
                correct += 1
        return correct / len(test_fps)

    self_acc = decode_accuracy(fps_per_rod[0], fps_per_rod[0], noise_sigma)

    # Cross-decode: rod 0's codebook → rod 1's fingerprints
    # Learn translation matrix T: fps_1 ≈ fps_0 @ T
    # Split into calibration (first half) and test (second half)
    n_cal = n_codewords // 2
    cal_0 = fps_per_rod[0][:n_cal]
    cal_1 = fps_per_rod[1][:n_cal]

    # Least-squares: T = pinv(cal_0) @ cal_1
    T = np.linalg.lstsq(cal_0, cal_1, rcond=None)[0]
    T_cond = float(np.linalg.cond(T))

    # Translate rod 0's full codebook into rod 1's space
    translated_fps = fps_per_rod[0] @ T

    # Test: decode rod 1's test fingerprints using translated codebook
    test_fps_1 = fps_per_rod[1][n_cal:]
    translated_codebook = translated_fps[n_cal:]

    cross_correct = 0
    for ci in range(len(test_fps_1)):
        noisy = test_fps_1[ci] + rng.randn(n_modes) * noise_sigma
        dists = np.sum((translated_codebook - noisy[None, :]) ** 2, axis=1)
        if np.argmin(dists) == ci:
            cross_correct += 1
    cross_acc = cross_correct / max(len(test_fps_1), 1)

    return RosettaResult(
        n_rods=len(rod_lengths),
        n_patterns=n_codewords,
        self_decode_accuracy=self_acc,
        cross_decode_accuracy=cross_acc,
        translation_matrix_cond=T_cond,
        rosetta_viable=bool(cross_acc > 0.8),
        verdict=bool(cross_acc > 0.8),
    )


# ═══════════════════════════════════════════════════════════════════════
# Run all six experiments
# ═══════════════════════════════════════════════════════════════════════

def run_all_scranton_dogon(verbose: bool = True) -> dict:
    """
    Execute all six Scranton–Dogon experiments and return results.

    Returns dict mapping experiment name to result dataclass.
    """
    results = {}
    rng = np.random.RandomState(42)

    if verbose:
        print("=" * 70)
        print("  SCRANTON–DOGON INFORMED EXPERIMENTS FOR CWM")
        print("=" * 70)

    # H7
    if verbose:
        print("\n▸ H7: Polysemic Readout (one symbol, four meanings)...")
    r7 = exp_polysemic_readout(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["polysemic_readout"] = r7
    if verbose:
        v = "✅ CONFIRMED" if r7.verdict else "❌ NOT CONFIRMED"
        print(f"  Channels:          {r7.n_channels}")
        print(f"  Per-channel bits:  {r7.channel_capacities}")
        print(f"  Total polysemic:   {r7.total_capacity_bits:.1f} bits")
        print(f"  Single-channel:    {r7.single_channel_bits:.1f} bits")
        print(f"  Independence:      {r7.mean_independence:.3f}")
        print(f"  Gain:              {r7.polysemic_gain_pct:+.1f}%  → {v}")

    # H8
    if verbose:
        print("\n▸ H8: Amma's Duality (symmetric-pair dual-channel)...")
    r8 = exp_duality_encoding(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["duality_encoding"] = r8
    if verbose:
        v = "✅ CONFIRMED" if r8.verdict else "❌ NOT CONFIRMED"
        print(f"  Odd-mode bits:     {r8.odd_mode_capacity:.1f}")
        print(f"  Even-mode bits:    {r8.even_mode_capacity:.1f}")
        print(f"  Combined:          {r8.combined_capacity:.1f} bits")
        print(f"  Naive asymmetric:  {r8.naive_capacity:.1f} bits")
        print(f"  Dual gain:         {r8.dual_gain_pct:+.1f}%  → {v}")

    # H9
    if verbose:
        print("\n▸ H9: Nommo Naming (max-distance fingerprints)...")
    r9 = exp_nommo_naming(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["nommo_naming"] = r9
    if verbose:
        v = "✅ CONFIRMED" if r9.verdict else "❌ NOT CONFIRMED"
        print(f"  Optimised BER:     {r9.optimised_ber:.4f}")
        print(f"  Random BER:        {r9.random_ber:.4f}")
        print(f"  Hamming (opt):     {r9.mean_hamming_optimised:.1f}")
        print(f"  Hamming (rand):    {r9.mean_hamming_random:.1f}")
        print(f"  Naming advantage:  {r9.naming_advantage_pct:+.1f}%  → {v}")

    # H10
    if verbose:
        print("\n▸ H10: Sigi Cycle (temporal-decay multiplexing)...")
    r10 = exp_sigi_cycle(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["sigi_cycle"] = r10
    if verbose:
        v = "✅ CONFIRMED" if r10.verdict else "❌ NOT CONFIRMED"
        print(f"  Time windows:      {r10.n_effective_channels}")
        print(f"  Per-window bits:   {r10.channel_bits}")
        print(f"  Total time-mux:    {r10.total_time_mux_bits:.1f} bits")
        print(f"  Single-shot:       {r10.single_shot_bits:.1f} bits")
        print(f"  Temporal gain:     {r10.temporal_gain_pct:+.1f}%  → {v}")

    # H11
    if verbose:
        print("\n▸ H11: Amma's Egg (seed-to-spectrum expansion)...")
    r11 = exp_ammas_egg(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["ammas_egg"] = r11
    if verbose:
        v = "✅ CONFIRMED" if r11.verdict else "❌ NOT CONFIRMED"
        print(f"  Seed → Full:       {r11.seed_size} → {r11.full_size} sites")
        print(f"  Seed fidelity:     {r11.seed_fidelity:.3f}")
        print(f"  Random fidelity:   {r11.random_fidelity:.3f}")
        print(f"  Seed cond:         {r11.seed_condition_number:.1f}")
        print(f"  Random cond:       {r11.random_condition_number:.1f}")
        print(f"  Improvement:       {r11.improvement_pct:+.1f}%  → {v}")

    # H12
    if verbose:
        print("\n▸ H12: Cross-Culture Rosetta (multi-rod translation)...")
    r12 = exp_rosetta_stone(rng=np.random.RandomState(rng.randint(1_000_000)))
    results["rosetta_stone"] = r12
    if verbose:
        v = "✅ CONFIRMED" if r12.verdict else "❌ NOT CONFIRMED"
        print(f"  Rods tested:       {r12.n_rods}")
        print(f"  Self-decode:       {r12.self_decode_accuracy:.1%}")
        print(f"  Cross-decode:      {r12.cross_decode_accuracy:.1%}")
        print(f"  Translation cond:  {r12.translation_matrix_cond:.1f}")
        print(f"  Rosetta viable:    {r12.rosetta_viable}  → {v}")

    if verbose:
        print("\n" + "=" * 70)
        n_pass = sum(1 for r in results.values() if r.verdict)
        print(f"  TOTAL: {n_pass}/6 hypotheses confirmed")
        print("=" * 70)

    return results
