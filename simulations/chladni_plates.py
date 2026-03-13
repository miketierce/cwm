"""
Chladni-Informed 2D Plate Eigenmode Memory Experiments for WCFOMA.

Four testable engineering hypotheses derived from structural parallels
between Ernst Chladni's vibrating-plate experiments (1787) and Spectral
Eigenmode Memory (CWM) physics.

Chladni's core insight: sprinkle sand on a vibrating plate and it
migrates to the *nodal lines* — curves of zero displacement.  These
are the positions where a mass perturbation has zero effect on that
mode's eigenfrequency.  The anti-nodal regions (maximum displacement)
are where perturbations matter most.  Chladni figures are therefore
*sensitivity maps* — the 2D generalisation of the 1D sensitivity
function sin²(nπx/L) that drives CWM.

Extending CWM from 1D rods to 2D plates could unlock quadratically
more modes, because a rectangular plate has two independent mode
indices (n, m), giving mode count ~ n_max².

Parallel → Hypothesis → Experiment
═══════════════════════════════════════════════════════════════════════
1. Chladni figures ↔ 2D perturbation sensitivity maps
   H-C1: A 2D plate supports ≥ 4× the thermally-stable eigenmodes
         of a 1D rod of the same material and footprint, because
         2D mode indices (n,m) give mode count ~ n_max².

2. Nodal-line topology ↔ Symmetry-class readout partitioning
   H-C2: Plate eigenmodes cluster into symmetry families (by
         nodal-line topology) that can be decoded independently,
         enabling a 2D analogue of polysemic readout with ≥ 3
         independent channels.

3. 2D sensitivity function ↔ Optimal perturbation placement
   H-C3: Quasi-random perturbation placement on a 2D plate
         achieves ≥ 15% lower condition number than a regular
         grid, because the product sensitivity sin²(nπx)·sin²(mπy)
         creates nodal-line aliasing that periodic grids cannot avoid.

4. Degenerate (n,m)/(m,n) pairs ↔ 2D avoided-crossing bonus
   H-C4: Square plates have structural degeneracy — (n,m)/(m,n)
         pairs with identical eigenfrequencies — that splits under
         asymmetric perturbation, producing bonus resolvable modes.
         This geometric effect has no 1D analogue: 1D rods have
         uniform mode spacing, so perturbation cannot create
         near-degeneracies.

Each experiment returns a concise dataclass result with a boolean
verdict and numerical evidence.

References:
  - Chladni, "Entdeckungen über die Natur des Klanges" (1787)
  - Kirchhoff, plate vibration theory (1850)
  - Rayleigh, "Theory of Sound" vol. I, ch. IX–X (1877)
  - Leissa, "Vibration of Plates" (NASA SP-160, 1969)
"""

from dataclasses import dataclass
from typing import Optional, Tuple, List
import warnings
import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ModeCountResult:
    """H-C1 — 2D plate mode count vs 1D rod mode count."""
    rod_n_max: int              # 1D rod: floor(1/(2αΔT + 1/Q))
    plate_n_max_per_axis: int   # per-axis limit (same formula as 1D)
    rod_mode_count: int         # total usable 1D modes
    plate_mode_count: int       # total usable 2D modes (n²+n)/2 ≤ budget
    mode_ratio: float           # plate / rod
    plate_density_gain: float   # bits per unit footprint area, plate vs rod
    verdict: bool               # True if plate ≥ 4× rod mode count


@dataclass
class SymmetryPartitionResult:
    """H-C2 — Symmetry-family readout partitioning."""
    n_modes_total: int
    n_symmetry_classes: int     # SS, SA, AS, AA (or fewer if rectangular)
    modes_per_class: np.ndarray # count of modes in each class
    class_labels: list          # human-readable labels
    cross_correlation: float    # mean cross-correlation between classes
    independent_channels: int   # classes with mutual coherence < threshold
    polysemic_capacity_gain_pct: float  # capacity bonus from partitioning
    verdict: bool               # True if ≥ 3 independent channels


@dataclass
class PlacementComparisonResult:
    """H-C3 — 2D placement: quasi-random vs regular grid."""
    n_modes: int
    n_sites: int
    cond_grid: float            # condition number: regular grid
    cond_1d_ext: float          # condition number: 1D golden-ratio extension
    cond_r2_2d: float           # condition number: true 2D R₂ sequence
    rank_grid: int
    rank_1d_ext: int
    rank_r2_2d: int
    improvement_pct: float      # best quasi-random vs grid (cond reduction %)
    verdict: bool               # True if quasi-random beats grid by > 15%


@dataclass
class DegeneracySplittingResult:
    """H-C4 — 2D degeneracy splitting (avoided crossing) bonus."""
    n_degenerate_pairs: int     # (n,m)/(m,n) pairs in square plate
    splitting_magnitudes: np.ndarray  # Δf for each pair under perturbation
    mean_splitting_Hz: float
    n_bonus_modes_1d: int       # near-degenerate pairs at same scale (1D rod)
    n_bonus_modes_2d: int       # extra modes from 2D splitting
    bonus_1d_pct: float         # 1D bonus: computed at same n_max
    bonus_2d_pct: float         # 2D bonus: n_bonus/total × 100
    degeneracy_fraction: float  # fraction of 2D modes in degenerate pairs
    verdict: bool               # True if bonus_2d > 10% AND n_bonus_2d ≫ n_bonus_1d


# ═══════════════════════════════════════════════════════════════════════
# Plate physics helpers
# ═══════════════════════════════════════════════════════════════════════

def plate_eigenfrequency(n: int, m: int, a: float, b: float,
                          D: float, rho_h: float) -> float:
    """
    Eigenfrequency of a simply-supported rectangular plate.

    f_{nm} = (π/2) √(D / ρh) · [(n/a)² + (m/b)²]

    Parameters
    ----------
    n, m : int
        Mode indices (≥ 1).
    a, b : float
        Plate dimensions (m).
    D : float
        Flexural rigidity = E h³ / (12(1-ν²))  (N·m).
    rho_h : float
        Mass per unit area = ρ × h  (kg/m²).

    Returns
    -------
    float : eigenfrequency in Hz.
    """
    return (np.pi / 2.0) * np.sqrt(D / rho_h) * (
        (n / a) ** 2 + (m / b) ** 2
    )


def plate_mode_shape(n: int, m: int, x: np.ndarray, y: np.ndarray,
                      a: float, b: float) -> np.ndarray:
    """
    Mode shape of a simply-supported rectangular plate.

    φ_{nm}(x, y) = sin(nπx/a) · sin(mπy/b)

    Parameters
    ----------
    n, m : int
        Mode indices (≥ 1).
    x, y : ndarray
        Position arrays (can be meshgrid outputs).
    a, b : float
        Plate dimensions.

    Returns
    -------
    ndarray : mode shape values at (x, y).
    """
    return np.sin(n * np.pi * x / a) * np.sin(m * np.pi * y / b)


def plate_sensitivity_2d(n: int, m: int, x: np.ndarray, y: np.ndarray,
                          a: float, b: float) -> np.ndarray:
    """
    Rayleigh perturbation sensitivity for a 2D plate mode.

    The frequency shift of mode (n,m) due to a point mass at (x,y) is
    proportional to the mode shape squared:

        ∂f_{nm}/∂m(x,y) ∝ -sin²(nπx/a) · sin²(mπy/b)

    This is the 2D generalisation of the 1D sin²(nπx/L).
    Chladni's sand collects at the *zeros* of this function (nodal lines).

    Returns
    -------
    ndarray : sensitivity values at (x, y).
    """
    return np.sin(n * np.pi * x / a) ** 2 * np.sin(m * np.pi * y / b) ** 2


def n_max_formula(alpha: float, delta_T: float, Q: float) -> int:
    """
    Maximum resolvable mode index: n_max = floor(1 / (2α ΔT + 1/Q)).

    This formula is *per axis* — it applies to each mode index
    independently.  For a 2D plate, both n and m must satisfy n,m ≤ n_max.
    """
    denom = 2.0 * alpha * delta_T + 1.0 / Q
    if denom <= 0:
        return 0
    return int(1.0 / denom)


def enumerate_plate_modes(n_max: int) -> List[Tuple[int, int]]:
    """
    Enumerate all (n, m) mode pairs with 1 ≤ n, m ≤ n_max.

    Returns sorted list of (n, m) tuples ordered by ascending
    eigenfrequency proxy (n² + m²).
    """
    ns = np.arange(1, n_max + 1)
    nn, mm = np.meshgrid(ns, ns, indexing='ij')
    nn_flat = nn.ravel()
    mm_flat = mm.ravel()
    freq_proxy = nn_flat ** 2 + mm_flat ** 2
    order = np.argsort(freq_proxy)
    return list(zip(nn_flat[order].tolist(), mm_flat[order].tolist()))


def classify_symmetry(n: int, m: int) -> str:
    """
    Classify a plate mode (n,m) by nodal-line symmetry.

    Simply-supported rectangular plate modes have four symmetry classes
    based on the parity of each index:
      SS — both even (symmetric in both axes)
      SA — n even, m odd
      AS — n odd, m even
      AA — both odd (antisymmetric in both axes)

    These correspond to distinct Chladni figure topologies.
    """
    n_parity = "S" if n % 2 == 0 else "A"
    m_parity = "S" if m % 2 == 0 else "A"
    return n_parity + m_parity


def build_plate_sensitivity_matrix(
    modes: List[Tuple[int, int]],
    site_positions: np.ndarray,
    a: float = 1.0,
    b: float = 1.0,
) -> np.ndarray:
    """
    Build the 2D Rayleigh sensitivity matrix S[mode_idx, site_idx].

    S[i, k] = sin²(n_i π x_k / a) · sin²(m_i π y_k / b)

    Parameters
    ----------
    modes : list of (n, m) tuples
    site_positions : ndarray of shape (K, 2), positions (x, y)
    a, b : plate dimensions

    Returns
    -------
    S : ndarray of shape (len(modes), K)
    """
    n_modes = len(modes)
    K = site_positions.shape[0]
    S = np.zeros((n_modes, K))
    for i, (n, m) in enumerate(modes):
        for k in range(K):
            xk, yk = site_positions[k]
            S[i, k] = (np.sin(n * np.pi * xk / a) ** 2 *
                        np.sin(m * np.pi * yk / b) ** 2)
    return S


def _golden_ratio_positions_2d(K: int) -> np.ndarray:
    """
    Place K sites using the 2D Kronecker low-discrepancy sequence.

    Uses the generalised golden ratio for 2D:
        φ₁ ≈ 0.7548776662..., φ₂ ≈ 0.5698402910...
    (from the plastic constant: the real root of x³ = x + 1)

    This is the natural 2D generalisation of 1D golden-ratio spacing.
    """
    # Generalised golden ratios for d=2 (R₂ sequence, Roberts 2018)
    phi1 = 0.7548776662466927
    phi2 = 0.5698402909980532
    positions = np.zeros((K, 2))
    for k in range(K):
        positions[k, 0] = ((k + 1) * phi1) % 1.0
        positions[k, 1] = ((k + 1) * phi2) % 1.0
    # Clamp away from boundaries (simply-supported = zero at edges)
    positions = np.clip(positions, 0.05, 0.95)
    return positions


def _maximin_lhs_positions_2d(K: int, n_candidates: int = 200,
                                rng: np.random.RandomState = None) -> np.ndarray:
    """
    2D-optimised placement using maximin Latin Hypercube Sampling.

    Generates n_candidates random LHS layouts and selects the one
    with maximum minimum pairwise distance — ensuring sites are
    spread across the plate and don't cluster near nodal lines.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    best_positions = None
    best_min_dist = -1.0

    for _ in range(n_candidates):
        # Latin Hypercube: one point per row/column in K×K grid
        x_perm = rng.permutation(K)
        y_perm = rng.permutation(K)
        positions = np.column_stack([
            (x_perm + rng.rand(K)) / K,
            (y_perm + rng.rand(K)) / K,
        ])
        positions = np.clip(positions, 0.05, 0.95)

        # Compute minimum pairwise distance
        from scipy.spatial.distance import pdist
        dists = pdist(positions)
        min_dist = dists.min() if len(dists) > 0 else 0.0

        if min_dist > best_min_dist:
            best_min_dist = min_dist
            best_positions = positions.copy()

    return best_positions


# ═══════════════════════════════════════════════════════════════════════
# Experiment C1 — 2D Plate Mode Count vs 1D Rod
# ═══════════════════════════════════════════════════════════════════════

def exp_plate_mode_count(
    alpha: float = 3.3e-6,
    delta_T: float = 1.0,
    Q: float = 10_000.0,
    a: float = 1.0e-3,
    b: float = 1.0e-3,
    rod_length: float = 1.0e-3,
) -> ModeCountResult:
    """
    Chladni's plates have 2D mode indices (n, m).  For a simply-
    supported rectangular plate, the eigenfrequencies are:

        f_{nm} = (π/2) √(D/ρh) · [(n/a)² + (m/b)²]

    The thermal stability constraint applies *per axis*:
        n ≤ n_max and m ≤ n_max

    where n_max = floor(1 / (2αΔT + 1/Q)) — the same formula as
    for a 1D rod.  But the total number of usable 2D modes is the
    count of all (n,m) pairs with n,m ∈ [1, n_max], which is n_max².
    A 1D rod has only n_max modes.

    We also need to apply a second constraint: adjacent 2D modes
    must be resolvable.  For a square plate, many modes are closely
    spaced (e.g., (3,4) and (4,3) are degenerate).  We count only
    modes whose frequency separations exceed the linewidth f/Q.

    Procedure
    ---------
    1. Compute n_max from the per-axis thermal+linewidth formula.
    2. Enumerate all (n,m) pairs with n,m ∈ [1, n_max].
    3. Apply the resolvability filter: sort by frequency, discard
       modes whose gap to the nearest neighbour < f_n/Q.
    4. Compare against 1D rod mode count.
    """
    rod_n_max = n_max_formula(alpha, delta_T, Q)
    plate_nmax = rod_n_max  # same per-axis limit

    # 1D rod: all modes 1..n_max are resolvable by definition
    #   (uniform spacing Δf = v/(2L), linewidth = f_n/Q = n·f_1/Q,
    #    constraint already baked into n_max formula)
    rod_mode_count = rod_n_max

    # 2D plate: count resolvable modes without materializing the full
    # N×N frequency array (which can exceed available RAM for large N).
    # Instead, we compute the smallest n²+m² above each threshold
    # using vectorized numpy (O(K×N) where K ≈ count ≪ N²).
    n_sq = np.arange(1, plate_nmax + 1, dtype=np.int64) ** 2

    def _next_freq_above(threshold_val):
        """Smallest n²+m² strictly > threshold_val, or None."""
        remainder = threshold_val - n_sq
        sqrt_rem = np.floor(np.sqrt(np.maximum(remainder, 0.0)))
        m_min = np.where(remainder < 0, 1, sqrt_rem.astype(np.int64) + 1)
        valid = (m_min >= 1) & (m_min <= plate_nmax)
        if not np.any(valid):
            return None
        return int(np.min(n_sq[valid] + m_min[valid] ** 2))

    # Resolvability filter: freq[next] > freq[last] × Q/(Q − 1)
    factor = Q / (Q - 1.0)
    last_freq = float(n_sq[0] + n_sq[0])  # f_min = 1² + 1² = 2
    plate_mode_count = 1
    while True:
        threshold = last_freq * factor
        nf = _next_freq_above(threshold)
        if nf is None:
            break
        last_freq = float(nf)
        plate_mode_count += 1
    mode_ratio = plate_mode_count / max(rod_mode_count, 1)

    # Density gain: plate uses area a×b, rod uses length L
    # For fair comparison with same footprint: rod occupies 1D line
    # in the same area, plate uses full 2D surface.
    # Bits_plate / Area vs Bits_rod / Length
    # Since both use the same material and n_max formula,
    # the gain is simply the mode ratio.
    density_gain = mode_ratio

    return ModeCountResult(
        rod_n_max=rod_n_max,
        plate_n_max_per_axis=plate_nmax,
        rod_mode_count=rod_mode_count,
        plate_mode_count=plate_mode_count,
        mode_ratio=mode_ratio,
        plate_density_gain=density_gain,
        verdict=bool(plate_mode_count >= 4 * rod_mode_count),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment C2 — Symmetry-Class Readout Partitioning
# ═══════════════════════════════════════════════════════════════════════

def exp_symmetry_partition(
    alpha: float = 3.3e-6,
    delta_T: float = 1.0,
    Q: float = 10_000.0,
    n_modes_cap: int = 200,
    coherence_threshold: float = 0.3,
    rng: Optional[np.random.RandomState] = None,
) -> SymmetryPartitionResult:
    """
    Chladni figures have visually distinct topologies depending on
    nodal-line geometry.  For a rectangular plate, modes separate
    into four symmetry classes by the parity of (n, m):

        SS (both even), SA (n even, m odd),
        AS (n odd, m even), AA (both odd)

    Each class has a characteristic Chladni pattern topology.  If
    these classes produce statistically independent spectral
    fingerprints, they function as independent readout channels —
    the 2D analogue of polysemic readout (§11.5).

    Procedure
    ---------
    1. Enumerate modes up to n_max, classify by symmetry.
    2. For each class, build a sensitivity matrix at random sites.
    3. Measure cross-correlation between classes' fingerprints.
    4. Count classes with mutual coherence below threshold.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    nmax = n_max_formula(alpha, delta_T, Q)
    # Cap enumeration at √n_modes_cap per axis when n_max is large,
    # then take the lowest-frequency n_modes_cap modes.
    enum_nmax = min(nmax, max(int(np.ceil(np.sqrt(n_modes_cap))) + 2, 20))
    all_modes = enumerate_plate_modes(enum_nmax)
    if len(all_modes) > n_modes_cap:
        all_modes = all_modes[:n_modes_cap]

    # Classify modes
    class_map = {}
    for nm in all_modes:
        c = classify_symmetry(nm[0], nm[1])
        class_map.setdefault(c, []).append(nm)

    class_labels = sorted(class_map.keys())
    n_classes = len(class_labels)
    modes_per_class = np.array([len(class_map[c]) for c in class_labels])

    # Place test sites
    K = 12
    sites = _golden_ratio_positions_2d(K)

    # Build per-class sensitivity matrices and fingerprints
    n_patterns = 100
    class_fingerprints = {}
    for c in class_labels:
        modes_c = class_map[c]
        if len(modes_c) == 0:
            continue
        S_c = build_plate_sensitivity_matrix(modes_c, sites)
        # Generate random perturbation patterns
        patterns = rng.rand(n_patterns, K)
        # Fingerprint = S_c @ pattern^T → (n_modes_class, n_patterns)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fp = S_c @ patterns.T  # (n_modes_class, n_patterns)
        class_fingerprints[c] = fp.T  # (n_patterns, n_modes_class)

    # Compute cross-correlation between class fingerprint vectors
    # For each pattern, concatenate all class fingerprints into one long vector
    # Then measure correlation between different classes' sub-vectors
    cross_corrs = []
    labels_with_fp = [c for c in class_labels if c in class_fingerprints]
    for i in range(len(labels_with_fp)):
        for j in range(i + 1, len(labels_with_fp)):
            ci, cj = labels_with_fp[i], labels_with_fp[j]
            # Mean fingerprint magnitude for normalisation
            fp_i = class_fingerprints[ci]  # (n_patterns, n_modes_i)
            fp_j = class_fingerprints[cj]  # (n_patterns, n_modes_j)
            # Measure correlation of pattern-level norms
            norms_i = np.linalg.norm(fp_i, axis=1)
            norms_j = np.linalg.norm(fp_j, axis=1)
            if np.std(norms_i) > 1e-10 and np.std(norms_j) > 1e-10:
                corr = abs(np.corrcoef(norms_i, norms_j)[0, 1])
            else:
                corr = 0.0
            cross_corrs.append(corr)

    mean_cross_corr = float(np.mean(cross_corrs)) if cross_corrs else 0.0

    # Count independent channels: classes with low mutual coherence
    # A class is "independent" if its mean correlation with all others < threshold
    independent_count = 0
    for i, ci in enumerate(labels_with_fp):
        corrs_for_ci = []
        for j, cj in enumerate(labels_with_fp):
            if i == j:
                continue
            fp_i = class_fingerprints[ci]
            fp_j = class_fingerprints[cj]
            norms_i = np.linalg.norm(fp_i, axis=1)
            norms_j = np.linalg.norm(fp_j, axis=1)
            if np.std(norms_i) > 1e-10 and np.std(norms_j) > 1e-10:
                corrs_for_ci.append(abs(np.corrcoef(norms_i, norms_j)[0, 1]))
            else:
                corrs_for_ci.append(0.0)
        if len(corrs_for_ci) == 0 or np.mean(corrs_for_ci) < coherence_threshold:
            independent_count += 1

    # Polysemic capacity gain: each independent channel adds capacity
    # gain = (n_channels - 1) / 1 × 100%
    poly_gain = (independent_count - 1) * 100.0 if independent_count > 1 else 0.0

    return SymmetryPartitionResult(
        n_modes_total=len(all_modes),
        n_symmetry_classes=n_classes,
        modes_per_class=modes_per_class,
        class_labels=class_labels,
        cross_correlation=mean_cross_corr,
        independent_channels=independent_count,
        polysemic_capacity_gain_pct=poly_gain,
        verdict=bool(independent_count >= 3),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment C3 — 2D Placement: Quasi-Random vs Regular Grid
# ═══════════════════════════════════════════════════════════════════════

def exp_placement_comparison(
    n_max_cap: int = 15,
    K: int = 16,
    alpha: float = 3.3e-6,
    delta_T: float = 1.0,
    Q: float = 10_000.0,
    rng: Optional[np.random.RandomState] = None,
) -> PlacementComparisonResult:
    """
    How does placement strategy affect sensitivity-matrix conditioning
    on a 2D plate?

    A regular grid is prone to *nodal-line aliasing*: modes whose
    half-wavelength matches the grid spacing produce degenerate
    sensitivity columns, inflating the condition number κ(S).
    Quasi-random sequences break this with irrational spacings.

    We test three placement strategies:
    1. **Regular grid**: uniform √K × √K rectangular grid — the
       naïve baseline, prone to aliasing.
    2. **1D-extended**: Apply 1D golden-ratio to each axis —
       x_k = {kφ} mod 1, y_k = {kφ²} mod 1.
    3. **2D R₂ sequence**: True 2D generalised golden-ratio using
       the plastic constant (Roberts 2018) — designed specifically
       for 2D low-discrepancy sampling.

    Procedure
    ---------
    1. Enumerate plate modes up to a tractable cap.
    2. Build sensitivity matrices for all three placement strategies.
    3. Compare condition numbers and ranks.
    4. Verdict: quasi-random placement achieves ≥ 15% lower
       condition number than the regular grid.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    nmax = min(n_max_formula(alpha, delta_T, Q), n_max_cap)
    all_modes = enumerate_plate_modes(nmax)

    # Determine grid side length (nearest integer √K)
    grid_side = int(np.round(np.sqrt(K)))
    K_actual = grid_side * grid_side

    # Strategy 1: Regular grid — naïve baseline
    grid_coords = np.linspace(0.1, 0.9, grid_side)
    xx, yy = np.meshgrid(grid_coords, grid_coords)
    sites_grid = np.column_stack([xx.ravel(), yy.ravel()])

    # Strategy 2: 1D golden-ratio extended to 2D
    phi = (1.0 + np.sqrt(5)) / 2.0
    sites_1d = np.zeros((K_actual, 2))
    for k in range(K_actual):
        sites_1d[k, 0] = ((k + 1) / phi) % 1.0
        sites_1d[k, 1] = ((k + 1) / phi ** 2) % 1.0
    sites_1d = np.clip(sites_1d, 0.05, 0.95)

    # Strategy 3: True 2D R₂ sequence (Roberts 2018)
    sites_r2 = _golden_ratio_positions_2d(K_actual)

    # Build sensitivity matrices
    S_grid = build_plate_sensitivity_matrix(all_modes, sites_grid)
    S_1d = build_plate_sensitivity_matrix(all_modes, sites_1d)
    S_r2 = build_plate_sensitivity_matrix(all_modes, sites_r2)

    # Analyse via SVD
    def _analyse(S):
        U, sigma, Vt = np.linalg.svd(S, full_matrices=False)
        tol = max(S.shape) * sigma[0] * np.finfo(float).eps
        rank = int(np.sum(sigma > tol))
        cond = sigma[0] / sigma[-1] if sigma[-1] > tol else np.inf
        return rank, cond

    rank_grid, cond_grid = _analyse(S_grid)
    rank_1d, cond_1d = _analyse(S_1d)
    rank_r2, cond_r2 = _analyse(S_r2)

    # Best quasi-random condition number vs regular grid
    best_qr_cond = min(cond_1d, cond_r2)
    if cond_grid > 0 and np.isfinite(cond_grid):
        improvement = (cond_grid - best_qr_cond) / cond_grid * 100.0
    else:
        improvement = 100.0  # grid is degenerate → quasi-random infinitely better

    return PlacementComparisonResult(
        n_modes=len(all_modes),
        n_sites=K_actual,
        cond_grid=cond_grid,
        cond_1d_ext=cond_1d,
        cond_r2_2d=cond_r2,
        rank_grid=rank_grid,
        rank_1d_ext=rank_1d,
        rank_r2_2d=rank_r2,
        improvement_pct=improvement,
        verdict=bool(improvement > 15.0),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment C4 — 2D Degeneracy Splitting (Avoided Crossing)
# ═══════════════════════════════════════════════════════════════════════

def exp_degeneracy_splitting(
    n_max_cap: int = 20,
    alpha: float = 3.3e-6,
    delta_T: float = 1.0,
    Q: float = 10_000.0,
    perturbation_strength: float = 0.01,
    rng: Optional[np.random.RandomState] = None,
) -> DegeneracySplittingResult:
    """
    A square plate has degenerate mode pairs: modes (n,m) and (m,n)
    have identical eigenfrequencies when a = b.  Under an asymmetric
    perturbation (mass added at a non-symmetric position), this
    degeneracy splits — the two modes repel each other in frequency
    space (avoided crossing).

    Unlike 1D rods (where modes are uniformly spaced and perturbation
    cannot create near-degeneracies), 2D plates have *structural*
    degeneracy: every (n,m)/(m,n) pair is exactly degenerate.  This
    is a purely geometric effect with no 1D analogue.

    We compute the 1D bonus at the SAME n_max for fair comparison.
    In 1D, modes f_n = n·f₁ are uniformly spaced; a point-mass
    perturbation shifts them but cannot bring non-adjacent modes
    together because |f_n - f_m| >> linewidth for all n ≠ m.

    Procedure
    ---------
    1. Compute 2D bonus: enumerate (n,m)/(m,n) pairs, apply
       asymmetric perturbation, count resolvable splittings.
    2. Compute 1D bonus: for same n_max, apply same perturbation
       to 1D rod, count mode pairs brought within one linewidth.
    3. Compare: 2D should vastly exceed 1D because 2D degeneracy
       is structural (geometric) while 1D has none.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    nmax = min(n_max_formula(alpha, delta_T, Q), n_max_cap)

    # ── 2D bonus: degeneracy splitting ──
    pairs_2d = []
    for n in range(1, nmax + 1):
        for m in range(n + 1, nmax + 1):
            pairs_2d.append((n, m))

    if len(pairs_2d) == 0:
        return DegeneracySplittingResult(
            n_degenerate_pairs=0,
            splitting_magnitudes=np.array([]),
            mean_splitting_Hz=0.0,
            n_bonus_modes_1d=0,
            n_bonus_modes_2d=0,
            bonus_1d_pct=0.0,
            bonus_2d_pct=0.0,
            degeneracy_fraction=0.0,
            verdict=False,
        )

    # Perturbation position — deliberately non-symmetric
    x_p = 0.37  # not on any simple symmetry axis
    y_p = 0.61

    # Unperturbed eigenfrequency proxy: n² + m² (identical for (n,m) and (m,n))
    # Perturbed eigenfrequency: first-order Rayleigh correction
    # Δf_{nm} = -ε · f_{nm} · sin²(nπx_p) · sin²(mπy_p) / (∫φ² dA)
    # For normalised modes on unit plate, ∫φ² dA = 1/4
    # So Δf_{nm} = -4ε · f_{nm} · sin²(nπx_p) · sin²(mπy_p)
    #
    # The splitting between (n,m) and (m,n) is:
    # δf = |Δf_{nm} - Δf_{mn}| = 4ε · f · |sin²(nπx_p)sin²(mπy_p) - sin²(mπx_p)sin²(nπy_p)|

    splittings = []
    n_resolvable_2d = 0
    for n, m in pairs_2d:
        f_proxy = n ** 2 + m ** 2  # proportional to eigenfrequency
        sens_nm = (np.sin(n * np.pi * x_p) ** 2 *
                    np.sin(m * np.pi * y_p) ** 2)
        sens_mn = (np.sin(m * np.pi * x_p) ** 2 *
                    np.sin(n * np.pi * y_p) ** 2)
        splitting = 4.0 * perturbation_strength * f_proxy * abs(sens_nm - sens_mn)
        splittings.append(splitting)

        # Is the splitting resolvable? Compare to linewidth = f/Q
        linewidth = f_proxy / Q
        if splitting > linewidth:
            n_resolvable_2d += 1

    splittings = np.array(splittings)
    total_modes_2d = nmax * nmax

    # ── 1D bonus: near-degenerate pairs in rod at same n_max ──
    # 1D rod: f_n ∝ n (uniform spacing).  Perturbation at x_p shifts
    # f_n → f_n · (1 - ε·sin²(nπx_p)).  Count pairs (n,m) with n<m
    # whose perturbed frequencies come within one linewidth.
    n_near_degenerate_1d = 0
    for n in range(1, nmax + 1):
        for m in range(n + 1, nmax + 1):
            f_n = float(n)
            f_m = float(m)
            df_n = perturbation_strength * f_n * np.sin(n * np.pi * x_p) ** 2
            df_m = perturbation_strength * f_m * np.sin(m * np.pi * x_p) ** 2
            f_n_pert = f_n - df_n
            f_m_pert = f_m - df_m
            gap = abs(f_n_pert - f_m_pert)
            linewidth_1d = max(f_n_pert, f_m_pert) / Q
            if gap < linewidth_1d:
                n_near_degenerate_1d += 1

    bonus_2d_pct = n_resolvable_2d / max(total_modes_2d, 1) * 100.0
    bonus_1d_pct = n_near_degenerate_1d / max(nmax, 1) * 100.0
    degeneracy_fraction = 2.0 * len(pairs_2d) / max(total_modes_2d, 1)

    return DegeneracySplittingResult(
        n_degenerate_pairs=len(pairs_2d),
        splitting_magnitudes=splittings,
        mean_splitting_Hz=float(np.mean(splittings)) if len(splittings) > 0 else 0.0,
        n_bonus_modes_1d=n_near_degenerate_1d,
        n_bonus_modes_2d=n_resolvable_2d,
        bonus_1d_pct=bonus_1d_pct,
        bonus_2d_pct=bonus_2d_pct,
        degeneracy_fraction=degeneracy_fraction,
        verdict=bool(bonus_2d_pct > 10.0 and
                      n_resolvable_2d > 10 * max(n_near_degenerate_1d, 1)),
    )


# ═══════════════════════════════════════════════════════════════════════
# Run all four experiments
# ═══════════════════════════════════════════════════════════════════════

def run_all_chladni(verbose: bool = True) -> dict:
    """
    Execute all four Chladni-informed experiments and return results.

    Returns dict mapping experiment name to result dataclass.
    """
    results = {}
    rng = np.random.RandomState(42)

    if verbose:
        print("=" * 70)
        print("  CHLADNI-INFORMED EXPERIMENTS FOR CWM")
        print("=" * 70)

    # H-C1: Plate Mode Count
    if verbose:
        print("\n▸ H-C1: 2D Plate Mode Count vs 1D Rod...")
    r1 = exp_plate_mode_count()
    results["plate_mode_count"] = r1
    if verbose:
        v = "✅ CONFIRMED" if r1.verdict else "❌ NOT CONFIRMED"
        print(f"  1D rod modes:     {r1.rod_mode_count:,}")
        print(f"  2D plate modes:   {r1.plate_mode_count:,}")
        print(f"  Mode ratio:       {r1.mode_ratio:.1f}×")
        print(f"  Density gain:     {r1.plate_density_gain:.1f}×  → {v}")

    # H-C2: Symmetry Partition
    if verbose:
        print("\n▸ H-C2: Symmetry-Class Readout Partitioning...")
    r2 = exp_symmetry_partition(rng=np.random.RandomState(rng.randint(1e6)))
    results["symmetry_partition"] = r2
    if verbose:
        v = "✅ CONFIRMED" if r2.verdict else "❌ NOT CONFIRMED"
        print(f"  Total modes:       {r2.n_modes_total}")
        print(f"  Symmetry classes:  {r2.n_symmetry_classes}")
        for i, label in enumerate(r2.class_labels):
            print(f"    {label}: {r2.modes_per_class[i]} modes")
        print(f"  Cross-correlation: {r2.cross_correlation:.3f}")
        print(f"  Independent ch.:   {r2.independent_channels}")
        print(f"  Polysemic gain:    +{r2.polysemic_capacity_gain_pct:.0f}%  → {v}")

    # H-C3: Placement Comparison
    if verbose:
        print("\n▸ H-C3: 2D Placement — Grid vs Quasi-Random...")
    r3 = exp_placement_comparison(rng=np.random.RandomState(rng.randint(1e6)))
    results["placement_comparison"] = r3
    if verbose:
        v = "✅ CONFIRMED" if r3.verdict else "❌ NOT CONFIRMED"
        print(f"  Modes used:        {r3.n_modes}")
        print(f"  Sites:             {r3.n_sites}")
        print(f"  Grid κ(S):         {r3.cond_grid:.1f}")
        print(f"  1D-ext κ(S):       {r3.cond_1d_ext:.1f}")
        print(f"  R₂ 2D κ(S):       {r3.cond_r2_2d:.1f}")
        print(f"  Ranks (G/1D/R₂):  {r3.rank_grid}/{r3.rank_1d_ext}/{r3.rank_r2_2d}")
        print(f"  Improvement:       {r3.improvement_pct:+.1f}%  → {v}")

    # H-C4: Degeneracy Splitting
    if verbose:
        print("\n▸ H-C4: 2D Degeneracy Splitting (Avoided Crossing)...")
    r4 = exp_degeneracy_splitting(rng=np.random.RandomState(rng.randint(1e6)))
    results["degeneracy_splitting"] = r4
    if verbose:
        v = "✅ CONFIRMED" if r4.verdict else "❌ NOT CONFIRMED"
        print(f"  Degenerate pairs:  {r4.n_degenerate_pairs}")
        print(f"  2D resolvable:     {r4.n_bonus_modes_2d}")
        if r4.mean_splitting_Hz > 0:
            print(f"  Mean splitting:    {r4.mean_splitting_Hz:.4f} (proxy units)")
        print(f"  1D bonus modes:    {r4.n_bonus_modes_1d}  (+{r4.bonus_1d_pct:.1f}%)")
        print(f"  2D bonus:          +{r4.bonus_2d_pct:.1f}%")
        print(f"  Degeneracy frac.:  {r4.degeneracy_fraction:.1%}  → {v}")

    if verbose:
        print("\n" + "=" * 70)
        n_pass = sum(1 for r in results.values() if r.verdict)
        print(f"  TOTAL: {n_pass}/4 hypotheses confirmed")
        print("=" * 70)

    return results
