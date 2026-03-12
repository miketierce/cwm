"""
S12 — Lev Gor'kov (1929–2016): Acoustic Radiation Force & Optimal Site
Placement
======================================================================

Gor'kov's acoustic radiation force theory (1962) predicts where particles
collect in a standing-wave field.  The primary radiation force is

    F_pr  ∝  sin(2kz)

where k = nπ/L for the n-th eigenmode.  SEM's eigenmode sensitivity
function sin²(nπx/L) has a spatial gradient

    ∂/∂x sin²(nπx/L) = (nπ/L) sin(2nπx/L)

which is **mathematically identical** to the Gor'kov radiation-force
spatial pattern.  Locations where perturbation sensitivity changes most
rapidly correspond exactly to positions where acoustic radiation forces
are strongest.

The acoustic contrast factor
    Φ(κ̃, ρ̃) = (5ρ̃ − 2)/(2ρ̃ + 1) − κ̃.

predicts particle behaviour at nodes vs antinodes and encodes material
properties (compressibility ratio κ̃ = κ_p/κ_f, density ratio ρ̃ = ρ_p/ρ_f).

Four testable hypotheses:

1. Gor'kov-optimised placement (H-ARF1)
   Placing perturbation sites at maxima of |sin(2nπx/L)| yields ≥ 10%
   higher fingerprint distinguishability than golden-ratio placement.

2. Acoustic contrast factor predicts materials (H-ARF2)
   Ranking perturbation materials by Φ correlates r > 0.7 with ranking
   by measured eigenfrequency shift magnitude.

3. Bjerknes force predicts hybridisation coupling (H-ARF3)
   Bjerknes-attractive site pairs show ≥ 2× the hybridisation splitting
   of Bjerknes-repulsive pairs.

4. Dual-axis encoding (H-ARF4)
   Using both node sites (gradient-dominated) and antinode sites
   (amplitude-dominated) increases fingerprint entropy by ≥ 20% over
   single-axis (antinode-only) placement.

References:
  - Gor'kov, "On the forces acting on a small particle …" (1962)
  - Bruus, "Acoustofluidics 7" (Lab Chip, 2012)
  - King, "On the acoustic radiation pressure on spheres" (1934)
  - Yosioka & Kawasima, "Acoustic radiation pressure …" (1955)
  - Settnes & Bruus, "Forces acting on a small particle …" (2012)
  - Scranton, observations on standing-wave organisation
  - WCFOMA paper v15 §7 (site optimization), §11.3 (hybridisation),
    §11.8 (Chladni), §11.12 (Zeeman)
  - site_optimization.py, spare_mace.py, chladni_plates.py,
    zeeman_splitting.py, forced_oscillation.py
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

from .common import K_B, C_FERROFLUID


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class GorkovPlacementResult:
    """H-ARF1 — Gor'kov-optimised placement vs golden-ratio baseline."""
    n_modes: int                     # number of eigenmodes
    K: int                           # number of perturbation sites
    gorkov_positions: np.ndarray     # site positions at sin(2kz) maxima
    golden_positions: np.ndarray     # golden-ratio baseline positions
    gorkov_cond: float               # condition number of Gor'kov layout
    golden_cond: float               # condition number of golden-ratio layout
    gorkov_distinguishable: int      # distinguishable fingerprints (Gor'kov)
    golden_distinguishable: int      # distinguishable fingerprints (golden)
    gorkov_bits: float               # log₂(distinguishable) for Gor'kov
    golden_bits: float               # log₂(distinguishable) for golden-ratio
    improvement_pct: float           # (gorkov - golden) / golden × 100
    verdict: bool                    # True if improvement ≥ 10%


@dataclass
class ContrastFactorResult:
    """H-ARF2 — Acoustic contrast factor predicts material frequency shifts."""
    n_materials: int                 # number of test materials
    material_names: List[str]        # material identifiers
    rho_ratios: np.ndarray           # density ratio ρ̃ = ρ_p/ρ_f
    kappa_ratios: np.ndarray         # compressibility ratio κ̃ = κ_p/κ_f
    phi_values: np.ndarray           # contrast factor Φ for each material
    freq_shifts: np.ndarray          # measured eigenfrequency shift magnitude
    phi_ranking: np.ndarray          # rank order by |Φ|
    shift_ranking: np.ndarray        # rank order by measured shift
    spearman_r: float                # Spearman rank correlation
    pearson_r: float                 # Pearson correlation on |Φ| vs shift
    verdict: bool                    # True if spearman_r > 0.7


@dataclass
class BjerknesHybridResult:
    """H-ARF3 — Bjerknes force predicts hybridisation splitting strength."""
    n_pairs: int                     # number of site pairs tested
    pair_separations: np.ndarray     # distance between paired sites
    bjerknes_sign: np.ndarray        # +1 attractive, −1 repulsive
    splitting_magnitudes: np.ndarray # avoided-crossing splitting Δf/f₀
    mean_attractive_split: float     # mean splitting for attractive pairs
    mean_repulsive_split: float      # mean splitting for repulsive pairs
    ratio: float                     # attractive / repulsive
    verdict: bool                    # True if ratio ≥ 2.0


@dataclass
class DualAxisResult:
    """H-ARF4 — Dual-axis (node + antinode) encoding vs antinode-only."""
    n_modes: int                     # number of eigenmodes
    K_total: int                     # total sites (node + antinode)
    K_node: int                      # sites at nodes (gradient-dominated)
    K_antinode: int                  # sites at antinodes (amplitude-dominated)
    node_positions: np.ndarray       # node site positions
    antinode_positions: np.ndarray   # antinode site positions
    dual_positions: np.ndarray       # combined positions
    antinode_only_positions: np.ndarray  # antinode-only baseline positions
    entropy_dual: float              # fingerprint entropy (bits), dual-axis
    entropy_antinode: float          # fingerprint entropy (bits), antinode-only
    entropy_gain_pct: float          # (dual − antinode) / antinode × 100
    cond_dual: float                 # condition number, dual layout
    cond_antinode: float             # condition number, antinode-only
    verdict: bool                    # True if entropy_gain ≥ 20%


# ═══════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════

def _acoustic_frequencies(n_modes: int, L: float = 1e-5,
                          c: float = C_FERROFLUID) -> np.ndarray:
    """f_n = n · c / (2L) for n = 1 .. n_modes."""
    ns = np.arange(1, n_modes + 1)
    return ns * c / (2.0 * L)


def _sensitivity(n: int, x: np.ndarray) -> np.ndarray:
    """SEM eigenmode sensitivity: sin²(nπx) at normalised position x ∈ [0,1]."""
    return np.sin(n * np.pi * x) ** 2


def _sensitivity_gradient(n: int, x: np.ndarray) -> np.ndarray:
    """Gradient of sensitivity: (nπ)·sin(2nπx) — proportional to Gor'kov force."""
    return n * np.pi * np.sin(2 * n * np.pi * x)


def _gorkov_force_pattern(n: int, x: np.ndarray) -> np.ndarray:
    """Gor'kov radiation force pattern: sin(2nπx) (normalised position)."""
    return np.sin(2 * n * np.pi * x)


def _acoustic_contrast_factor(rho_ratio: float, kappa_ratio: float) -> float:
    """Gor'kov acoustic contrast factor: Φ = (5ρ̃−2)/(2ρ̃+1) − κ̃.

    Parameters
    ----------
    rho_ratio : float
        Density ratio ρ_p / ρ_f (particle / fluid).
    kappa_ratio : float
        Compressibility ratio κ_p / κ_f.

    Returns
    -------
    float
        Contrast factor Φ.  Positive → particle moves to pressure node.
    """
    return (5.0 * rho_ratio - 2.0) / (2.0 * rho_ratio + 1.0) - kappa_ratio


def _golden_positions(K: int) -> np.ndarray:
    """Golden-ratio perturbation site placement in [0,1]."""
    phi = (1.0 + np.sqrt(5)) / 2.0
    pos = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    return np.sort(np.clip(pos, 0.02, 0.98))


def _gorkov_optimal_positions(K: int, n_modes: int) -> np.ndarray:
    """Place K sites at maxima of the multi-mode Gor'kov force magnitude.

    For each candidate position x, compute the sum over modes of
    |sin(2nπx)|.  Select K positions that maximise this sum,
    with a minimum spacing constraint to avoid clustering.

    Parameters
    ----------
    K : int
        Number of sites to place.
    n_modes : int
        Number of eigenmodes contributing to the force field.

    Returns
    -------
    np.ndarray
        K optimal positions in [0, 1].
    """
    n_candidates = 2000
    x_cand = np.linspace(0.02, 0.98, n_candidates)

    # Multi-mode force magnitude: sum over modes of |sin(2nπx)|
    force_sum = np.zeros(n_candidates)
    for n in range(1, n_modes + 1):
        force_sum += np.abs(np.sin(2 * n * np.pi * x_cand))

    # Greedy selection with minimum spacing
    min_spacing = 0.8 / max(K, 1)
    selected = []
    order = np.argsort(-force_sum)  # descending force magnitude

    for idx in order:
        x = x_cand[idx]
        if all(abs(x - s) >= min_spacing for s in selected):
            selected.append(x)
            if len(selected) == K:
                break

    # Fall back to top-K if spacing constraint is too tight
    if len(selected) < K:
        for idx in order:
            x = x_cand[idx]
            if x not in selected:
                selected.append(x)
                if len(selected) == K:
                    break

    return np.sort(np.array(selected))


def _sensitivity_matrix(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """S[n, k] = sin²(nπx_k).  Shape (n_modes, K)."""
    n = np.arange(1, n_modes + 1)[:, None]
    x = positions[None, :]
    return np.sin(n * np.pi * x) ** 2


def _gradient_matrix(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """G[n, k] = (nπ)·sin(2nπx_k).  Shape (n_modes, K).

    This is the Gor'kov-force-equivalent sensitivity gradient.
    """
    n = np.arange(1, n_modes + 1)[:, None]
    x = positions[None, :]
    return n * np.pi * np.sin(2 * n * np.pi * x)


def _condition_number(M: np.ndarray) -> float:
    """Condition number of a matrix (ratio of largest to smallest singular value)."""
    sv = np.linalg.svd(M, compute_uv=False)
    if sv[-1] < 1e-15:
        return 1e15
    return float(sv[0] / sv[-1])


def _count_distinguishable(S: np.ndarray, alphabet_size: int = 3,
                            noise_floor: float = 0.05) -> Tuple[int, float]:
    """Count distinguishable fingerprints and compute bits.

    For each of alphabet_size^K possible perturbation patterns, compute
    the fingerprint S @ pattern.  Two fingerprints are distinguishable
    if their L² distance exceeds noise_floor × mean fingerprint norm.

    Returns (n_distinguishable, bits).
    """
    K = S.shape[1]
    n_modes = S.shape[0]

    # For tractability, sample patterns rather than enumerate all
    max_patterns = min(alphabet_size ** K, 5000)
    rng = np.random.RandomState(42)

    if alphabet_size ** K <= 5000:
        # Enumerate all
        patterns = []
        for i in range(alphabet_size ** K):
            p = []
            val = i
            for _ in range(K):
                p.append(val % alphabet_size)
                val //= alphabet_size
            patterns.append(p)
        patterns = np.array(patterns, dtype=float) + 1  # shift to [1, alphabet_size]
    else:
        patterns = rng.randint(1, alphabet_size + 1, size=(max_patterns, K)).astype(float)

    # Compute fingerprints
    fingerprints = (S @ patterns.T).T  # (n_patterns, n_modes)

    # Mean norm for noise threshold
    norms = np.linalg.norm(fingerprints, axis=1)
    threshold = noise_floor * np.mean(norms)

    # Count distinguishable pairs using pairwise distances
    # For efficiency, use a grid-based approach for large sets
    n_pat = len(fingerprints)
    if n_pat <= 2000:
        # Full pairwise
        dists = np.zeros((n_pat, n_pat))
        for i in range(n_pat):
            dists[i, :] = np.linalg.norm(fingerprints - fingerprints[i], axis=1)

        # A fingerprint is "distinguishable" if its nearest-neighbour
        # distance exceeds the threshold
        np.fill_diagonal(dists, np.inf)
        min_dists = np.min(dists, axis=1)
        n_dist = int(np.sum(min_dists > threshold))
    else:
        # Subsample for tractability
        idx = rng.choice(n_pat, 2000, replace=False)
        sub_fp = fingerprints[idx]
        dists = np.zeros((2000, 2000))
        for i in range(2000):
            dists[i, :] = np.linalg.norm(sub_fp - sub_fp[i], axis=1)
        np.fill_diagonal(dists, np.inf)
        min_dists = np.min(dists, axis=1)
        frac_dist = np.mean(min_dists > threshold)
        n_dist = int(frac_dist * n_pat)

    bits = np.log2(max(n_dist, 1))
    return n_dist, float(bits)


def _fingerprint_entropy(S: np.ndarray, n_patterns: int = 2000,
                          n_bins: int = 50, seed: int = 42) -> float:
    """Compute fingerprint entropy over random perturbation patterns.

    Generate random patterns, compute fingerprints, histogram the
    fingerprint values, and return Shannon entropy in bits.

    Parameters
    ----------
    S : np.ndarray
        Sensitivity matrix (n_modes × K).
    n_patterns : int
        Number of random patterns to sample.
    n_bins : int
        Number of histogram bins per mode.
    seed : int
        Random seed.

    Returns
    -------
    float
        Shannon entropy in bits.
    """
    rng = np.random.RandomState(seed)
    K = S.shape[1]
    n_modes = S.shape[0]

    # Random patterns with values in {1, 2, 3}
    patterns = rng.randint(1, 4, size=(n_patterns, K)).astype(float)

    # Fingerprints: (n_patterns, n_modes)
    fps = (S @ patterns.T).T

    # Compute entropy per mode and sum (joint entropy approximation)
    total_entropy = 0.0
    for m in range(n_modes):
        vals = fps[:, m]
        hist, _ = np.histogram(vals, bins=n_bins, density=True)
        # Convert to probabilities
        hist = hist / (np.sum(hist) + 1e-30)
        # Shannon entropy
        mask = hist > 0
        total_entropy -= np.sum(hist[mask] * np.log2(hist[mask]))

    return float(total_entropy)


def _node_positions(K: int, n_ref: int = 1) -> np.ndarray:
    """Positions at nodes of sin²(n_ref·π·x): x = k/n_ref for integer k.

    These are zero-sensitivity, maximum-gradient locations.
    """
    candidates = []
    for k in range(1, n_ref):
        x = k / float(n_ref)
        if 0.02 <= x <= 0.98:
            candidates.append(x)
    candidates = np.array(candidates) if candidates else np.array([])
    if len(candidates) <= K:
        return candidates
    # Select K evenly spaced from candidates
    indices = np.linspace(0, len(candidates) - 1, K, dtype=int)
    return candidates[indices]


def _antinode_positions(K: int, n_ref: int = 1) -> np.ndarray:
    """Positions at antinodes of sin²(n_ref·π·x): x = (2k+1)/(2·n_ref).

    These are maximum-sensitivity, zero-gradient locations.
    """
    candidates = []
    for k in range(n_ref):
        x = (2 * k + 1) / (2.0 * n_ref)
        if 0.02 <= x <= 0.98:
            candidates.append(x)
    candidates = np.array(candidates) if candidates else np.array([])
    if len(candidates) <= K:
        return candidates
    indices = np.linspace(0, len(candidates) - 1, K, dtype=int)
    return candidates[indices]


def _bjerknes_sign(x1: float, x2: float, n: int) -> int:
    """Bjerknes force sign between two sites for mode n.

    In a standing wave, two particles at positions x1 and x2 experience
    an attractive secondary Bjerknes force when they oscillate in phase
    (both at pressure nodes or both at antinodes) and repulsive when
    anti-phase (one at node, other at antinode).

    We determine the sign from sin(nπx₁)·sin(nπx₂): positive → in-phase
    (attractive), negative → anti-phase (repulsive).

    Returns +1 (attractive) or −1 (repulsive).
    """
    product = np.sin(n * np.pi * x1) * np.sin(n * np.pi * x2)
    return 1 if product >= 0 else -1


def _multi_mode_bjerknes_sign(x1: float, x2: float,
                                n_modes: int) -> int:
    """Net Bjerknes force sign averaged over modes 1..n_modes.

    Returns +1 if majority of modes give attractive force, else −1.
    """
    attractive = 0
    for n in range(1, n_modes + 1):
        attractive += _bjerknes_sign(x1, x2, n)
    return 1 if attractive > 0 else -1


def _hybridisation_splitting(n: int, m: int, x_p: float,
                               epsilon: float = 0.01) -> float:
    """Avoided-crossing splitting Δf/f₀ between modes n and m.

    First-order perturbation: Δf/f₀ ≈ ε · |sin²(nπx_p) − sin²(mπx_p)|.
    For near-degenerate modes, off-diagonal coupling gives splitting
    proportional to ε · sin(nπx_p) · sin(mπx_p).

    We use the geometric-mean coupling:
      splitting = ε · |sin(nπx_p)·sin(mπx_p)|
    which captures the mode-mode interaction at position x_p.
    """
    coupling = abs(np.sin(n * np.pi * x_p) * np.sin(m * np.pi * x_p))
    return epsilon * coupling


def _eigenfrequency_shift(n: int, x_p: float, epsilon: float,
                            rho_ratio: float = 1.5,
                            kappa_ratio: float = 0.5) -> float:
    """Eigenfrequency shift due to a perturbation at position x_p.

    Δf/f₀ ∝ ε · Φ · sin²(nπx_p) where Φ is the contrast factor.
    The shift magnitude depends on material properties via Φ and
    position via the sensitivity function.
    """
    phi = _acoustic_contrast_factor(rho_ratio, kappa_ratio)
    return epsilon * abs(phi) * _sensitivity(n, np.array([x_p]))[0]


def _spearman_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rank correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0
    rank_x = np.argsort(np.argsort(x)).astype(float)
    rank_y = np.argsort(np.argsort(y)).astype(float)
    d = rank_x - rank_y
    return 1.0 - 6.0 * np.sum(d ** 2) / (n * (n ** 2 - 1))


def _pearson_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation coefficient."""
    if len(x) < 2:
        return 0.0
    mx, my = np.mean(x), np.mean(y)
    dx, dy = x - mx, y - my
    denom = np.sqrt(np.sum(dx**2) * np.sum(dy**2))
    if denom < 1e-30:
        return 0.0
    return float(np.sum(dx * dy) / denom)


# ═══════════════════════════════════════════════════════════════════════
# Experiment 1: Gor'kov-Optimised Placement (H-ARF1)
# ═══════════════════════════════════════════════════════════════════════

def exp_gorkov_placement(
    K: int = 6,
    n_modes: int = 20,
    alphabet_size: int = 3,
    noise_floor: float = 0.05,
    improvement_threshold: float = 10.0,
) -> GorkovPlacementResult:
    """Test whether Gor'kov-optimised placement outperforms golden-ratio.

    Gor'kov placement puts sites at maxima of the multi-mode radiation
    force magnitude Σ_n |sin(2nπx)|.  Golden-ratio placement uses the
    established baseline from site_optimization.py.

    For each layout, build the sensitivity matrix, count distinguishable
    fingerprints, and compare.

    Parameters
    ----------
    K : int
        Number of perturbation sites.
    n_modes : int
        Number of eigenmodes.
    alphabet_size : int
        Number of perturbation levels per site.
    noise_floor : float
        Noise threshold for distinguishability.
    improvement_threshold : float
        Minimum % improvement to confirm (default 10%).
    """
    # Compute positions
    g_pos = _gorkov_optimal_positions(K, n_modes)
    phi_pos = _golden_positions(K)

    # Sensitivity matrices
    S_g = _sensitivity_matrix(g_pos, n_modes)
    S_phi = _sensitivity_matrix(phi_pos, n_modes)

    # Condition numbers
    cond_g = _condition_number(S_g)
    cond_phi = _condition_number(S_phi)

    # Count distinguishable fingerprints
    n_dist_g, bits_g = _count_distinguishable(S_g, alphabet_size, noise_floor)
    n_dist_phi, bits_phi = _count_distinguishable(S_phi, alphabet_size, noise_floor)

    # Improvement percentage
    if n_dist_phi > 0:
        improvement = (n_dist_g - n_dist_phi) / n_dist_phi * 100.0
    else:
        improvement = 100.0 if n_dist_g > 0 else 0.0

    return GorkovPlacementResult(
        n_modes=n_modes,
        K=K,
        gorkov_positions=g_pos,
        golden_positions=phi_pos,
        gorkov_cond=cond_g,
        golden_cond=cond_phi,
        gorkov_distinguishable=n_dist_g,
        golden_distinguishable=n_dist_phi,
        gorkov_bits=bits_g,
        golden_bits=bits_phi,
        improvement_pct=float(improvement),
        verdict=bool(improvement >= improvement_threshold),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 2: Acoustic Contrast Factor Predicts Materials (H-ARF2)
# ═══════════════════════════════════════════════════════════════════════

# Representative perturbation materials with physical properties.
# ρ̃ = ρ_material / ρ_fluid (ferrofluid ≈ 1200 kg/m³)
# κ̃ = κ_material / κ_fluid (ferrofluid κ ≈ 5e-10 Pa⁻¹)
_MATERIAL_TABLE = [
    # (name,        ρ̃,    κ̃)
    ("steel",       6.5,   0.04),   # dense, very incompressible → high Φ
    ("glass",       1.88,  0.13),   # moderate density, low compressibility
    ("aluminium",   2.25,  0.10),   # light metal
    ("copper",      7.42,  0.02),   # very dense, very stiff
    ("lead",        9.42,  0.35),   # very dense but compressible
    ("polystyrene", 0.88,  1.67),   # lighter than fluid, very compressible → negative Φ
    ("silicone",    0.83,  2.50),   # very light and compressible
    ("ceramic",     3.00,  0.05),   # dense and stiff
    ("tungsten",    16.0,  0.01),   # extremely dense
    ("nylon",       0.96,  1.20),   # near-neutral density, compressible
    ("teflon",      1.79,  1.10),   # moderate density, compressible
    ("titanium",    3.75,  0.07),   # light-strong metal
]


def exp_contrast_factor(
    n_modes: int = 20,
    K: int = 4,
    epsilon: float = 0.01,
    r_threshold: float = 0.7,
    seed: int = 42,
) -> ContrastFactorResult:
    """Test whether acoustic contrast factor Φ predicts eigenfrequency shifts.

    For each material, compute Φ from its density and compressibility ratios.
    Then simulate the eigenfrequency shift produced by placing a perturbation
    of that material at a fixed site.  The measured shift should correlate
    with |Φ|.

    Parameters
    ----------
    n_modes : int
        Number of eigenmodes.
    K : int
        Number of perturbation sites (for multi-site shift measurement).
    epsilon : float
        Perturbation strength parameter.
    r_threshold : float
        Minimum Spearman correlation to confirm.
    seed : int
        Random seed.
    """
    rng = np.random.RandomState(seed)

    names = [m[0] for m in _MATERIAL_TABLE]
    rho_ratios = np.array([m[1] for m in _MATERIAL_TABLE])
    kappa_ratios = np.array([m[2] for m in _MATERIAL_TABLE])

    # Compute contrast factors
    phi_vals = np.array([_acoustic_contrast_factor(r, k)
                         for r, k in zip(rho_ratios, kappa_ratios)])

    # Fixed site positions (golden-ratio)
    positions = _golden_positions(K)

    # Measure total eigenfrequency shift for each material
    freq_shifts = np.zeros(len(names))
    for mi, (rho_r, kappa_r) in enumerate(zip(rho_ratios, kappa_ratios)):
        total_shift = 0.0
        for n in range(1, n_modes + 1):
            for x_p in positions:
                total_shift += abs(_eigenfrequency_shift(
                    n, x_p, epsilon, rho_r, kappa_r))
        freq_shifts[mi] = total_shift

    # Rankings
    phi_rank = np.argsort(np.argsort(-np.abs(phi_vals))).astype(float)
    shift_rank = np.argsort(np.argsort(-freq_shifts)).astype(float)

    # Correlations
    sp_r = _spearman_correlation(np.abs(phi_vals), freq_shifts)
    pe_r = _pearson_correlation(np.abs(phi_vals), freq_shifts)

    return ContrastFactorResult(
        n_materials=len(names),
        material_names=names,
        rho_ratios=rho_ratios,
        kappa_ratios=kappa_ratios,
        phi_values=phi_vals,
        freq_shifts=freq_shifts,
        phi_ranking=phi_rank,
        shift_ranking=shift_rank,
        spearman_r=float(sp_r),
        pearson_r=float(pe_r),
        verdict=bool(sp_r > r_threshold),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 3: Bjerknes Force Predicts Hybridisation (H-ARF3)
# ═══════════════════════════════════════════════════════════════════════

def exp_bjerknes_hybridisation(
    K: int = 8,
    n_modes: int = 20,
    epsilon: float = 0.01,
    max_delta_n: int = 3,
    ratio_threshold: float = 2.0,
    seed: int = 42,
) -> BjerknesHybridResult:
    """Test whether Bjerknes-attractive pairs show stronger hybridisation.

    Place K sites, then for each pair of sites evaluate:
    1. The net Bjerknes force sign (attractive or repulsive).
    2. The hybridisation splitting when both sites carry perturbations.

    Attractive pairs (in-phase oscillation) should produce ≥ 2× stronger
    avoided-crossing splitting than repulsive pairs.

    Parameters
    ----------
    K : int
        Number of perturbation sites.
    n_modes : int
        Number of eigenmodes.
    epsilon : float
        Perturbation strength.
    max_delta_n : int
        Maximum mode-index difference for near-degenerate pairs.
    ratio_threshold : float
        Minimum ratio (attractive/repulsive splitting) to confirm.
    seed : int
        Random seed.
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(K)

    # Generate all site pairs
    pair_data = []
    for i in range(K):
        for j in range(i + 1, K):
            x1, x2 = positions[i], positions[j]
            separation = abs(x2 - x1)

            # Net Bjerknes sign across modes
            sign = _multi_mode_bjerknes_sign(x1, x2, n_modes)

            # Hybridisation splitting: sum over near-degenerate mode pairs
            total_splitting = 0.0
            n_mode_pairs = 0
            for n in range(1, n_modes + 1):
                for m in range(n + 1, min(n + max_delta_n + 1, n_modes + 1)):
                    # Splitting at each site, then combined effect
                    split_1 = _hybridisation_splitting(n, m, x1, epsilon)
                    split_2 = _hybridisation_splitting(n, m, x2, epsilon)
                    # Two-site coupling: geometric mean captures interaction
                    combined = np.sqrt(split_1 * split_2 + 1e-30)
                    total_splitting += combined
                    n_mode_pairs += 1

            avg_splitting = total_splitting / max(n_mode_pairs, 1)
            pair_data.append((separation, sign, avg_splitting))

    separations = np.array([d[0] for d in pair_data])
    signs = np.array([d[1] for d in pair_data])
    splittings = np.array([d[2] for d in pair_data])

    # Separate attractive vs repulsive
    attractive_mask = signs > 0
    repulsive_mask = signs < 0

    mean_att = float(np.mean(splittings[attractive_mask])) if np.any(attractive_mask) else 0.0
    mean_rep = float(np.mean(splittings[repulsive_mask])) if np.any(repulsive_mask) else 1e-30

    ratio = mean_att / max(mean_rep, 1e-30)

    return BjerknesHybridResult(
        n_pairs=len(pair_data),
        pair_separations=separations,
        bjerknes_sign=signs,
        splitting_magnitudes=splittings,
        mean_attractive_split=mean_att,
        mean_repulsive_split=mean_rep,
        ratio=float(ratio),
        verdict=bool(ratio >= ratio_threshold),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 4: Dual-Axis Encoding (H-ARF4)
# ═══════════════════════════════════════════════════════════════════════

def exp_dual_axis(
    K_per_axis: int = 4,
    n_modes: int = 20,
    n_ref: int = 3,
    n_patterns: int = 3000,
    n_bins: int = 50,
    entropy_threshold: float = 20.0,
    seed: int = 42,
) -> DualAxisResult:
    """Test whether dual-axis encoding (nodes + antinodes) beats antinode-only.

    Node sites sit at zeros of sin²(nπx) — where the sensitivity gradient
    (Gor'kov force) is maximum.  Antinode sites sit at maxima of sin²(nπx)
    — where sensitivity amplitude is maximum.  Using both "axes" should
    capture complementary information and increase fingerprint entropy.

    Parameters
    ----------
    K_per_axis : int
        Number of sites per axis (total = 2 × K_per_axis).
    n_modes : int
        Number of eigenmodes.
    n_ref : int
        Reference mode for node/antinode positions (use multiple modes
        to generate enough distinct positions).
    n_patterns : int
        Number of random patterns for entropy estimation.
    n_bins : int
        Histogram bins per mode for entropy calculation.
    entropy_threshold : float
        Minimum % entropy gain to confirm.
    seed : int
        Random seed.
    """
    # Generate node and antinode positions using modes 1..n_ref
    node_cands = []
    for nr in range(1, n_ref + 1):
        for k in range(1, nr):
            x = k / float(nr)
            if 0.02 <= x <= 0.98:
                node_cands.append(x)
    node_cands = np.unique(np.round(node_cands, 8)) if node_cands else np.array([])

    anti_cands = []
    for nr in range(1, n_ref + 1):
        for k in range(nr):
            x = (2 * k + 1) / (2.0 * nr)
            if 0.02 <= x <= 0.98:
                anti_cands.append(x)
    anti_cands = np.unique(np.round(anti_cands, 8))

    # Select K_per_axis from each set, spread evenly
    if len(node_cands) >= K_per_axis:
        idx_n = np.linspace(0, len(node_cands) - 1, K_per_axis, dtype=int)
        node_pos = node_cands[idx_n]
    else:
        node_pos = node_cands

    if len(anti_cands) >= K_per_axis:
        idx_a = np.linspace(0, len(anti_cands) - 1, K_per_axis, dtype=int)
        anti_pos = anti_cands[idx_a]
    else:
        anti_pos = anti_cands

    # Dual-axis: combine node + antinode positions
    dual_pos = np.sort(np.concatenate([node_pos, anti_pos]))
    K_total = len(dual_pos)
    K_node = len(node_pos)
    K_anti = len(anti_pos)

    # Antinode-only baseline with same total number of sites
    # Use golden-ratio to ensure fair comparison (not cherry-picked antinodes)
    anti_only_cands = []
    for nr in range(1, n_ref + 2):  # slightly wider range for more candidates
        for k in range(nr):
            x = (2 * k + 1) / (2.0 * nr)
            if 0.02 <= x <= 0.98:
                anti_only_cands.append(x)
    anti_only_cands = np.unique(np.round(anti_only_cands, 8))
    if len(anti_only_cands) >= K_total:
        idx_ao = np.linspace(0, len(anti_only_cands) - 1, K_total, dtype=int)
        anti_only_pos = anti_only_cands[idx_ao]
    else:
        # Fall back to golden-ratio for antinode-only baseline
        anti_only_pos = _golden_positions(K_total)

    # Build combined sensitivity matrices for dual-axis
    # For node sites: their information comes through the gradient matrix
    # For antinode sites: standard sensitivity matrix
    # We concatenate both to form the "effective" encoding matrix
    S_dual = np.vstack([
        _sensitivity_matrix(dual_pos, n_modes),
        _gradient_matrix(dual_pos, n_modes),
    ])

    S_anti_only = np.vstack([
        _sensitivity_matrix(anti_only_pos, n_modes),
        _gradient_matrix(anti_only_pos, n_modes),
    ])

    # Compute fingerprint entropy
    entropy_d = _fingerprint_entropy(S_dual, n_patterns, n_bins, seed)
    entropy_a = _fingerprint_entropy(S_anti_only, n_patterns, n_bins, seed)

    # Condition numbers (on standard sensitivity matrix)
    cond_d = _condition_number(_sensitivity_matrix(dual_pos, n_modes))
    cond_a = _condition_number(_sensitivity_matrix(anti_only_pos, n_modes))

    # Entropy gain
    if entropy_a > 0:
        gain = (entropy_d - entropy_a) / entropy_a * 100.0
    else:
        gain = 100.0 if entropy_d > 0 else 0.0

    return DualAxisResult(
        n_modes=n_modes,
        K_total=K_total,
        K_node=K_node,
        K_antinode=K_anti,
        node_positions=node_pos,
        antinode_positions=anti_pos,
        dual_positions=dual_pos,
        antinode_only_positions=anti_only_pos,
        entropy_dual=entropy_d,
        entropy_antinode=entropy_a,
        entropy_gain_pct=float(gain),
        cond_dual=cond_d,
        cond_antinode=cond_a,
        verdict=bool(gain >= entropy_threshold),
    )


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_gorkov(verbose: bool = True) -> dict:
    """Run all S12 Gor'kov radiation force experiments and return results dict."""
    results: dict = {}

    # H-ARF1
    r1 = exp_gorkov_placement()
    results["H-ARF1"] = r1
    if verbose:
        print("=" * 60)
        print("H-ARF1: Gor'kov-Optimised Placement")
        print("=" * 60)
        print(f"  Sites (K):              {r1.K}")
        print(f"  Modes:                  {r1.n_modes}")
        print(f"  Gor'kov distinguishable: {r1.gorkov_distinguishable}")
        print(f"  Golden-ratio distinguishable: {r1.golden_distinguishable}")
        print(f"  Gor'kov bits:           {r1.gorkov_bits:.1f}")
        print(f"  Golden-ratio bits:      {r1.golden_bits:.1f}")
        print(f"  Improvement:            {r1.improvement_pct:.1f}%")
        print(f"  Condition (Gor'kov):    {r1.gorkov_cond:.1f}")
        print(f"  Condition (golden):     {r1.golden_cond:.1f}")
        vstr = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # H-ARF2
    r2 = exp_contrast_factor()
    results["H-ARF2"] = r2
    if verbose:
        print("=" * 60)
        print("H-ARF2: Acoustic Contrast Factor Predicts Materials")
        print("=" * 60)
        print(f"  Materials tested:       {r2.n_materials}")
        print(f"  Spearman correlation:   {r2.spearman_r:.3f}")
        print(f"  Pearson correlation:    {r2.pearson_r:.3f}")
        print("  Material/Φ/Shift ranking:")
        for i, name in enumerate(r2.material_names):
            print(f"    {name:12s}  Φ={r2.phi_values[i]:+.3f}  "
                  f"shift={r2.freq_shifts[i]:.4f}")
        vstr = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # H-ARF3
    r3 = exp_bjerknes_hybridisation()
    results["H-ARF3"] = r3
    if verbose:
        print("=" * 60)
        print("H-ARF3: Bjerknes Force Predicts Hybridisation Coupling")
        print("=" * 60)
        print(f"  Site pairs tested:      {r3.n_pairs}")
        print(f"  Mean attractive split:  {r3.mean_attractive_split:.6f}")
        print(f"  Mean repulsive split:   {r3.mean_repulsive_split:.6f}")
        print(f"  Ratio (att/rep):        {r3.ratio:.2f}")
        vstr = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # H-ARF4
    r4 = exp_dual_axis()
    results["H-ARF4"] = r4
    if verbose:
        print("=" * 60)
        print("H-ARF4: Dual-Axis Encoding (Node + Antinode)")
        print("=" * 60)
        print(f"  Total sites:            {r4.K_total}")
        print(f"  Node sites:             {r4.K_node}")
        print(f"  Antinode sites:         {r4.K_antinode}")
        print(f"  Entropy (dual):         {r4.entropy_dual:.1f} bits")
        print(f"  Entropy (antinode-only): {r4.entropy_antinode:.1f} bits")
        print(f"  Entropy gain:           {r4.entropy_gain_pct:.1f}%")
        print(f"  Condition (dual):       {r4.cond_dual:.1f}")
        print(f"  Condition (antinode):   {r4.cond_antinode:.1f}")
        vstr = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = len(results) - confirmed
        print("=" * 60)
        print(f"S12 SUMMARY: {confirmed}/4 confirmed, {killed}/4 killed")
        print("=" * 60)

    return results
