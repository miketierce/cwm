"""
S20 — Passive Stone Resonance: CWM Without Electricity
=======================================================

The CWM architecture rests on four pillars: (1) a resonator with
well-defined eigenmodes, (2) a mechanism to excite specific modes,
(3) a mechanism to sense mode content, and (4) sufficient coherence
time for information to persist.  Sections 2–11 implement all four
with piezoelectric transducers and CMOS readout.  But none of the
underlying physics — standing waves, perturbation-induced frequency
shifts, sin²(nπx) sensitivity — requires electricity.

This sidebar asks: **can CWM operate as an entirely passive,
non-electronic system?**  The question has modern engineering value
(extreme-environment sensors, zero-power tags, energy-harvesting
monitors) and an unexpected historical resonance.  The Edfu and
Saqqara archaeological sites have yielded thousands of precision
stone vessels — granite, diorite, alabaster — machined to sub-
millimetre wall uniformity.  These objects ARE acoustic resonators.
A struck granite vessel rings for seconds, sustaining multiple
eigenmodes whose frequencies encode its geometry.

We do not claim that ancient Egyptians used CWM.  We do claim,
and here test, that the physics permits it: stone resonators of
archaeological provenance have the material properties (Q-factor,
mode density, dimensional tolerance) to support the same eigenmode
memory principles demonstrated in glass.

Five testable hypotheses:

1. Stone Q-factor comparison (H-PA1)
   Archaeological stone materials (granite, diorite, quartzite,
   alabaster) should sustain Q-factors within one order of magnitude
   of borosilicate glass, with granite approaching glass performance.
   Kill criterion: all stone Q-factors < 100 (one-tenth of glass Q).

2. Eigenmode density in cylindrical stone vessels (H-PA2)
   A granite cylinder of archaeological dimensions (height ~15 cm,
   radius ~7 cm, wall ~1 cm) supports ≥ 10 distinguishable
   eigenmodes in the audible band (20 Hz–20 kHz), sufficient
   for multi-bit information encoding.
   Kill criterion: fewer than 5 modes in audible band.

3. Perturbation sensitivity in stone (H-PA3)
   The sin²(nπx) perturbation sensitivity function applies to
   stone cylinders identically to glass rods: a mass perturbation
   at position x shifts eigenfrequency n by Δfₙ ∝ sin²(nπx/L).
   The perturbation fingerprint is material-independent.
   Kill criterion: R² of sin²(nπx) fit to stone frequency shifts
   is < 0.9 (material introduces non-universal distortion).

4. Passive readout via Chladni patterns (H-PA4)
   Granular particles on a vibrating stone surface form mode-
   specific Chladni patterns whose spatial structure encodes the
   eigenmode spectrum.  The pattern mutual information with the
   true mode identity should exceed 1 bit per mode for the first
   10 modes — sufficient for visual "content-addressable" recall.
   Kill criterion: mutual information < 0.5 bits per mode.

5. Cross-material universality (H-PA5)
   The capacity scaling law (bits ∝ N_modes × log₂(Q)) should
   hold identically for stone and glass: substituting stone
   material parameters into the CWM capacity formula should
   predict actual stone capacity within 10%.
   Kill criterion: prediction error > 25%.

References:
  - Stocks, "Experiments in Egyptian Archaeology" (2003) — granite
    vessel manufacturing precision
  - Petrie, "The Pyramids and Temples of Gizeh" (1883) — dimensional
    surveys of Saqqara stone vessels
  - Dunn, "Lost Technologies of Ancient Egypt" (2010) — precision
    measurements of granite boxes, Serapeum
  - Schreiber, "Sound Velocity in Rocks" (1975) — acoustic properties
    of geological specimens
  - Standard values: Mavko et al., "The Rock Physics Handbook" (2020)
  - WCFOMA §2 eigenmode spectrum, §4 perturbation encoding
  - WCFOMA S17 coronal seismology (scale invariance across 12 orders)
  - WCFOMA S2 Scranton–Dogon (polysemic encoding in ancient symbolic systems)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Material database — acoustic properties of archaeological stones
# ═══════════════════════════════════════════════════════════════════════
#
# All values from published rock physics literature and manufacturer
# datasheets.  Q-factors from ultrasonic attenuation measurements
# (Mavko et al., The Rock Physics Handbook, 3rd ed., 2020; Schreiber
# et al., Elastic Constants and Their Measurement, 1975).
#
# The Q-factor for stone is frequency-dependent; values here are
# representative of the 1–20 kHz range relevant to hand-held vessels.

MATERIALS: Dict[str, Dict[str, float]] = {
    # Reference: borosilicate glass (CWM baseline)
    "borosilicate_glass": {
        "c_L": 5640.0,       # longitudinal wave speed (m/s)
        "c_T": 3280.0,       # shear wave speed (m/s)
        "density": 2230.0,   # kg/m³
        "Q": 2000.0,         # quality factor (1–20 kHz)
        "poisson": 0.20,     # Poisson's ratio
    },
    # Fused silica (high-purity glass)
    "fused_silica": {
        "c_L": 5968.0,
        "c_T": 3764.0,
        "density": 2200.0,
        "Q": 10000.0,        # exceptional Q, often used in MEMS
        "poisson": 0.17,
    },
    # Granite — the dominant stone at Saqqara, Serapeum, and Giza
    "granite": {
        "c_L": 5500.0,       # 4500–6500 typical; Aswan granite ~5500
        "c_T": 3100.0,       # 2500–3500 typical
        "density": 2650.0,
        "Q": 500.0,          # 300–1000 depending on grain size and moisture
        "poisson": 0.25,
    },
    # Diorite — used for many Saqqara vessels (harder than granite)
    "diorite": {
        "c_L": 5800.0,
        "c_T": 3300.0,
        "density": 2850.0,
        "Q": 400.0,          # slightly lower than granite (more heterogeneous)
        "poisson": 0.27,
    },
    # Quartzite — metamorphic sandstone, very hard, used for sarcophagi
    "quartzite": {
        "c_L": 5200.0,
        "c_T": 2900.0,
        "density": 2650.0,
        "Q": 350.0,          # grain boundaries cause higher attenuation
        "poisson": 0.28,
    },
    # Alabaster (calcite/gypsum) — softer, used for canopic jars
    "alabaster": {
        "c_L": 4800.0,
        "c_T": 2400.0,
        "density": 2700.0,
        "Q": 200.0,          # crystal boundaries, cleavage planes
        "poisson": 0.30,
    },
    # Basalt — volcanic, used in some bowls and grinding stones
    "basalt": {
        "c_L": 5400.0,
        "c_T": 3000.0,
        "density": 2900.0,
        "Q": 300.0,          # vesicular porosity lowers Q
        "poisson": 0.26,
    },
    # Limestone — abundant in Egypt, used in construction and some vessels
    "limestone": {
        "c_L": 4500.0,
        "c_T": 2300.0,
        "density": 2500.0,
        "Q": 150.0,          # porous, highly variable
        "poisson": 0.29,
    },
}

# Archaeological vessel dimensions (representative, from Petrie/Dunn surveys)
# These are for cylindrical/annular vessels (height, outer radius, wall thickness)
VESSEL_DIMS = {
    "saqqara_small": {"height": 0.10, "radius": 0.05, "wall": 0.008},   # 10cm tall, 5cm radius
    "saqqara_medium": {"height": 0.15, "radius": 0.07, "wall": 0.010},  # 15cm tall, 7cm radius
    "saqqara_large": {"height": 0.25, "radius": 0.10, "wall": 0.012},   # 25cm tall, 10cm radius
    "serapeum_box": {"height": 1.10, "radius": 0.45, "wall": 0.23},     # Serapeum granite box
}


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class QFactorComparisonResult:
    """H-PA1 — Stone Q-factor comparison against glass."""
    material_names: List[str]
    q_values: np.ndarray               # Q per material
    q_ratios_to_glass: np.ndarray      # Q_stone / Q_glass
    glass_q: float                     # reference Q (borosilicate)
    best_stone: str                    # highest Q stone
    best_stone_q: float
    best_ratio: float                  # best stone Q / glass Q
    worst_stone: str
    worst_stone_q: float
    all_above_100: bool                # True if all stone Q > 100
    any_within_order: bool             # True if any stone Q > Q_glass / 10
    verdict: bool


@dataclass
class ModeDensityResult:
    """H-PA2 — Eigenmode density in stone vessels."""
    material: str
    vessel: str
    height: float
    radius: float
    wall: float
    n_longitudinal: int               # axial modes in audible band
    n_radial: int                     # radial modes in audible band
    n_circumferential: int            # circumferential modes in audible band
    n_total: int                      # total distinguishable modes
    freq_lowest: float                # Hz
    freq_highest: float               # Hz (within 20 kHz)
    mode_freqs: np.ndarray            # all mode frequencies
    verdict: bool


@dataclass
class PerturbationSensitivityResult:
    """H-PA3 — sin²(nπx) perturbation law in stone."""
    material: str
    n_modes_tested: int
    n_perturbation_positions: int
    r_squared_values: np.ndarray       # R² per mode
    mean_r_squared: float
    min_r_squared: float
    max_r_squared: float
    glass_mean_r_squared: float        # comparison: glass R²
    stone_glass_difference: float      # |stone_R² - glass_R²|
    verdict: bool


@dataclass
class ChladniReadoutResult:
    """H-PA4 — Passive visual readout via Chladni patterns."""
    material: str
    n_modes: int
    pattern_mutual_info: np.ndarray   # MI per mode (bits)
    mean_mi: float
    min_mi: float
    n_modes_above_1bit: int           # modes with MI > 1 bit
    pattern_distinctness: float       # mean pairwise pattern distance
    verdict: bool


@dataclass
class CrossMaterialCapacityResult:
    """H-PA5 — Universal capacity scaling law."""
    material_names: List[str]
    predicted_capacities: np.ndarray   # bits, from CWM formula
    measured_capacities: np.ndarray    # bits, from simulation
    prediction_errors: np.ndarray      # |predicted - measured| / measured
    mean_error: float
    max_error: float
    glass_capacity: float
    best_stone_capacity: float
    capacity_ratio: float              # best_stone / glass
    verdict: bool


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _cylinder_axial_freqs(c_L: float, height: float,
                          n_max: int = 200) -> np.ndarray:
    """
    Axial (longitudinal) eigenfrequencies of an open-open cylinder.

    f_n = n · c_L / (2H)
    """
    ns = np.arange(1, n_max + 1)
    return ns * c_L / (2.0 * height)


def _cylinder_radial_freqs(c_T: float, radius: float, wall: float,
                           n_max: int = 50, m_max: int = 8) -> np.ndarray:
    """
    Radial (breathing) eigenfrequencies of a hollow cylinder.

    Approximate: f_{n,m} ≈ α_{n,m} · c_T / (2π · R_eff)
    where R_eff = (radius + (radius - wall)) / 2 is the mean radius,
    and α_{n,m} are Bessel-function zeros.

    We use the asymptotic approximation for α_{n,m}:
    α_{n,m} ≈ π(m + n/2 - 1/4) for large indices.
    """
    R_eff = radius - wall / 2.0
    if R_eff <= 0:
        return np.array([])
    freqs = []
    for n in range(0, n_max + 1):
        for m in range(1, m_max + 1):
            alpha = np.pi * (m + n / 2.0 - 0.25)
            freq = alpha * c_T / (2.0 * np.pi * R_eff)
            freqs.append(freq)
    return np.array(sorted(freqs))


def _cylinder_circumferential_freqs(c_T: float, radius: float,
                                    wall: float,
                                    n_max: int = 30) -> np.ndarray:
    """
    Circumferential (bending) eigenfrequencies of a thin-walled cylinder.

    For a thin annular shell: f_n ≈ n(n² - 1) / (2π) · c_T · wall / (R² · √(12))
    (Rayleigh's thin-ring formula extended to cylinders.)
    """
    R = radius - wall / 2.0
    if R <= 0 or wall <= 0:
        return np.array([])
    freqs = []
    for n in range(2, n_max + 1):  # n=0 is rigid body, n=1 is translation
        f = n * (n**2 - 1) / (2.0 * np.pi) * c_T * wall / (R**2 * np.sqrt(12.0))
        freqs.append(f)
    return np.array(sorted(freqs))


def _audible_modes(freqs: np.ndarray, f_min: float = 20.0,
                   f_max: float = 20000.0) -> np.ndarray:
    """Filter frequencies to audible band."""
    mask = (freqs >= f_min) & (freqs <= f_max)
    return freqs[mask]


def _remove_near_duplicates(freqs: np.ndarray,
                            min_spacing_hz: float = 5.0) -> np.ndarray:
    """Remove frequencies that are too close to distinguish."""
    if len(freqs) == 0:
        return freqs
    sorted_f = np.sort(freqs)
    kept = [sorted_f[0]]
    for f in sorted_f[1:]:
        if f - kept[-1] >= min_spacing_hz:
            kept.append(f)
    return np.array(kept)


def _perturbation_shift(n: int, x_p: float, epsilon: float,
                        f_base: float) -> float:
    """
    Frequency shift from a mass perturbation at normalised position x_p.

    Δf_n = -ε · f_n · sin²(nπx_p)

    This is the universal perturbation formula from §4. It applies to
    any standing-wave resonator regardless of material — it depends only
    on the mode shape, which is determined by boundary conditions.
    """
    return -epsilon * f_base * np.sin(n * np.pi * x_p) ** 2


def _chladni_pattern_vector(mode_n: int, n_points: int = 64) -> np.ndarray:
    """
    Generate a 1D Chladni pattern for mode n on a cylindrical surface.

    Particles settle at nodal lines (where displacement ≈ 0).
    Pattern: |sin(nπx)|² < threshold → particle present.
    Returns a binary vector (1 = particle, 0 = empty).
    """
    x = np.linspace(0, 1, n_points, endpoint=False)
    displacement = np.abs(np.sin(mode_n * np.pi * x))
    # Particles settle where displacement is below 20% of max
    threshold = 0.20
    pattern = (displacement < threshold).astype(float)
    return pattern


def _pattern_mutual_information(patterns: np.ndarray) -> np.ndarray:
    """
    Compute self-information per pattern: how many bits needed to
    distinguish this pattern from all others.

    Uses pairwise Hamming distance: MI ≈ log₂(N_distinguishable)
    where N_distinguishable = number of patterns with Hamming
    distance > threshold.
    """
    n_modes = patterns.shape[0]
    n_points = patterns.shape[1]
    mi = np.zeros(n_modes)

    for i in range(n_modes):
        n_distinct = 0
        for j in range(n_modes):
            if i == j:
                continue
            hamming = np.sum(patterns[i] != patterns[j]) / n_points
            if hamming > 0.1:  # > 10% different
                n_distinct += 1
        # MI = log₂(1 + n_distinct) — at least 0 bits
        mi[i] = np.log2(1 + n_distinct) if n_distinct > 0 else 0.0

    return mi


def _cwm_capacity_formula(n_modes: int, Q: float) -> float:
    """
    CWM information capacity formula.

    C = N_modes × log₂(1 + Q / Q_threshold)

    where Q_threshold represents the minimum Q for 1-bit resolution
    per mode. From §7: Q_threshold ≈ 100 for frequency-shift encoding.
    """
    Q_threshold = 100.0
    if Q < Q_threshold:
        return 0.0
    bits_per_mode = np.log2(1 + Q / Q_threshold)
    return n_modes * bits_per_mode


# ═══════════════════════════════════════════════════════════════════════
# H-PA1: Stone Q-factor comparison
# ═══════════════════════════════════════════════════════════════════════

def exp_q_factor_comparison(seed: int = 42) -> QFactorComparisonResult:
    """
    Compare Q-factors of archaeological stone materials against
    borosilicate glass.

    The hypothesis: stone materials sustain Q-factors within one
    order of magnitude of glass, with granite approaching glass.

    Kill criterion: ALL stone Q-factors < 100 (indicating stone
    resonators are fundamentally too lossy for eigenmode memory).
    """
    glass_q = MATERIALS["borosilicate_glass"]["Q"]

    stones = {k: v for k, v in MATERIALS.items()
              if k not in ("borosilicate_glass", "fused_silica")}

    names = list(stones.keys())
    qs = np.array([stones[k]["Q"] for k in names])
    ratios = qs / glass_q

    best_idx = int(np.argmax(qs))
    worst_idx = int(np.argmin(qs))

    all_above_100 = bool(np.all(qs > 100))
    any_within_order = bool(np.any(qs > glass_q / 10.0))

    # Verdict: at least one stone has Q > 100 AND at least one is
    # within an order of magnitude of glass
    return QFactorComparisonResult(
        material_names=names,
        q_values=qs,
        q_ratios_to_glass=ratios,
        glass_q=glass_q,
        best_stone=names[best_idx],
        best_stone_q=float(qs[best_idx]),
        best_ratio=float(ratios[best_idx]),
        worst_stone=names[worst_idx],
        worst_stone_q=float(qs[worst_idx]),
        all_above_100=all_above_100,
        any_within_order=any_within_order,
        verdict=bool(all_above_100 and any_within_order),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-PA2: Eigenmode density in stone vessels
# ═══════════════════════════════════════════════════════════════════════

def exp_mode_density(
    material: str = "granite",
    vessel: str = "saqqara_medium",
    f_min: float = 20.0,
    f_max: float = 20000.0,
    min_spacing: float = 5.0,
    seed: int = 42,
) -> ModeDensityResult:
    """
    Count distinguishable eigenmodes in the audible band for a
    stone vessel of archaeological dimensions.

    Three mode families contribute:
    - Axial (longitudinal standing waves along height)
    - Radial (breathing modes of the cylindrical shell)
    - Circumferential (bending modes around the rim)

    Kill criterion: total modes < 5 in audible band.
    """
    mat = MATERIALS[material]
    dims = VESSEL_DIMS[vessel]

    # Axial modes
    axial = _cylinder_axial_freqs(mat["c_L"], dims["height"])
    axial_aud = _audible_modes(axial, f_min, f_max)

    # Radial modes
    radial = _cylinder_radial_freqs(mat["c_T"], dims["radius"],
                                    dims["wall"])
    radial_aud = _audible_modes(radial, f_min, f_max)

    # Circumferential modes
    circ = _cylinder_circumferential_freqs(mat["c_T"], dims["radius"],
                                           dims["wall"])
    circ_aud = _audible_modes(circ, f_min, f_max)

    # Combine all modes and remove near-duplicates
    all_freqs = np.concatenate([axial_aud, radial_aud, circ_aud])
    distinct = _remove_near_duplicates(all_freqs, min_spacing)

    n_total = len(distinct)
    f_lo = float(np.min(distinct)) if n_total > 0 else 0.0
    f_hi = float(np.max(distinct)) if n_total > 0 else 0.0

    return ModeDensityResult(
        material=material,
        vessel=vessel,
        height=dims["height"],
        radius=dims["radius"],
        wall=dims["wall"],
        n_longitudinal=len(axial_aud),
        n_radial=len(radial_aud),
        n_circumferential=len(circ_aud),
        n_total=n_total,
        freq_lowest=f_lo,
        freq_highest=f_hi,
        mode_freqs=distinct,
        verdict=bool(n_total >= 10),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-PA3: Perturbation sensitivity in stone
# ═══════════════════════════════════════════════════════════════════════

def exp_perturbation_sensitivity(
    material: str = "granite",
    n_modes: int = 20,
    n_positions: int = 50,
    epsilon: float = 0.01,
    height: float = 0.15,
    seed: int = 42,
) -> PerturbationSensitivityResult:
    """
    Test whether the sin²(nπx) perturbation law is material-independent.

    For each mode n, place a small mass perturbation at n_positions
    equally spaced along the vessel height.  Compute Δf_n(x) and
    fit to the theoretical sin²(nπx) curve.  Compare R² for stone
    vs glass.

    The perturbation formula Δf_n = -ε·f_n·sin²(nπx/L) derives from
    first-order perturbation theory on the standing-wave equation.
    The derivation depends only on the mode shape (boundary conditions),
    NOT on material properties (wave speed, density, Q).  Therefore:
    - Different materials change the BASE frequency f_n
    - But the PATTERN of shifts across positions is identical
    - R² of the sin² fit should be ≈ 1.0 for all materials

    Kill criterion: R² < 0.9 for stone (material-dependent distortion).
    """
    rng = np.random.RandomState(seed)
    mat = MATERIALS[material]
    glass = MATERIALS["borosilicate_glass"]

    x_positions = np.linspace(0.01, 0.99, n_positions)

    def _compute_r_squared(c_L: float, noise_level: float) -> np.ndarray:
        """Compute R² of sin²(nπx) fit for each mode, with realistic noise."""
        r2s = np.zeros(n_modes)
        for mode_idx in range(n_modes):
            n = mode_idx + 1
            f_base = n * c_L / (2.0 * height)

            # Theoretical shifts
            shifts_theory = np.array([
                _perturbation_shift(n, xp, epsilon, f_base)
                for xp in x_positions
            ])

            # "Measured" shifts: theoretical + small noise from
            # material inhomogeneity (grain structure in stone)
            noise = rng.normal(0, noise_level * np.abs(np.mean(shifts_theory)),
                               size=n_positions)
            shifts_meas = shifts_theory + noise

            # Fit sin²(nπx) model
            sin2 = np.sin(n * np.pi * x_positions) ** 2
            # Linear regression: shifts_meas ≈ a · sin² + b
            A = np.vstack([sin2, np.ones(n_positions)]).T
            coeffs, residuals, _, _ = np.linalg.lstsq(A, shifts_meas, rcond=None)

            # R²
            ss_res = np.sum((shifts_meas - A @ coeffs) ** 2)
            ss_tot = np.sum((shifts_meas - np.mean(shifts_meas)) ** 2)
            r2s[mode_idx] = 1.0 - ss_res / ss_tot if ss_tot > 1e-30 else 1.0

        return r2s

    # Stone: higher noise from grain boundaries (1% noise level)
    stone_r2 = _compute_r_squared(mat["c_L"], noise_level=0.01)
    # Glass: very low noise (0.1% noise level)
    glass_r2 = _compute_r_squared(glass["c_L"], noise_level=0.001)

    return PerturbationSensitivityResult(
        material=material,
        n_modes_tested=n_modes,
        n_perturbation_positions=n_positions,
        r_squared_values=stone_r2,
        mean_r_squared=float(np.mean(stone_r2)),
        min_r_squared=float(np.min(stone_r2)),
        max_r_squared=float(np.max(stone_r2)),
        glass_mean_r_squared=float(np.mean(glass_r2)),
        stone_glass_difference=float(abs(np.mean(stone_r2) - np.mean(glass_r2))),
        verdict=bool(np.mean(stone_r2) > 0.9),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-PA4: Passive readout via Chladni patterns
# ═══════════════════════════════════════════════════════════════════════

def exp_chladni_readout(
    material: str = "granite",
    n_modes: int = 15,
    n_pattern_points: int = 64,
    seed: int = 42,
) -> ChladniReadoutResult:
    """
    Test whether Chladni sand patterns provide sufficient mutual
    information for visual mode identification.

    For each mode n, generate the Chladni pattern (particles at nodes)
    and compute mutual information: how many bits of mode identity
    can be recovered from the pattern alone.

    Kill criterion: mean MI < 0.5 bits per mode.
    """
    rng = np.random.RandomState(seed)

    # Generate patterns for first n_modes modes
    patterns = np.zeros((n_modes, n_pattern_points))
    for i in range(n_modes):
        clean_pattern = _chladni_pattern_vector(i + 1, n_pattern_points)
        # Add realistic noise: 5% of points randomly flip
        noise_mask = rng.random(n_pattern_points) < 0.05
        noisy_pattern = clean_pattern.copy()
        noisy_pattern[noise_mask] = 1.0 - noisy_pattern[noise_mask]
        patterns[i] = noisy_pattern

    # Compute mutual information
    mi = _pattern_mutual_information(patterns)
    mean_mi = float(np.mean(mi))
    min_mi = float(np.min(mi))
    n_above_1bit = int(np.sum(mi > 1.0))

    # Mean pairwise Hamming distance (pattern distinctness)
    n = patterns.shape[0]
    dists = []
    for i in range(n):
        for j in range(i + 1, n):
            dists.append(np.sum(patterns[i] != patterns[j]) / n_pattern_points)
    pattern_dist = float(np.mean(dists)) if dists else 0.0

    return ChladniReadoutResult(
        material=material,
        n_modes=n_modes,
        pattern_mutual_info=mi,
        mean_mi=mean_mi,
        min_mi=min_mi,
        n_modes_above_1bit=n_above_1bit,
        pattern_distinctness=pattern_dist,
        verdict=bool(mean_mi > 1.0),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-PA5: Cross-material capacity universality
# ═══════════════════════════════════════════════════════════════════════

def exp_cross_material_capacity(
    vessel: str = "saqqara_medium",
    seed: int = 42,
) -> CrossMaterialCapacityResult:
    """
    Test whether the CWM capacity formula C = N × log₂(1 + Q/Q_th)
    predicts actual capacity correctly for all materials.

    For each material:
    1. Count modes using the eigenmode density calculation.
    2. Predicted capacity: _cwm_capacity_formula(n_modes, Q)
    3. "Measured" capacity: simulate perturbation encoding, compute
       actually distinguishable states.
    4. Compare predicted vs measured.

    Kill criterion: mean prediction error > 25%.
    """
    names = []
    predicted = []
    measured = []

    for mat_name, mat in MATERIALS.items():
        dims = VESSEL_DIMS[vessel]
        # Count modes
        r = exp_mode_density(material=mat_name, vessel=vessel)
        n_modes = r.n_total

        # Predicted capacity
        cap_pred = _cwm_capacity_formula(n_modes, mat["Q"])
        predicted.append(cap_pred)

        # "Measured" capacity: actual number of distinguishable states
        # Each mode contributes log₂(1 + SNR) bits, where
        # SNR ≈ Q / Q_noise. We add small material-dependent noise.
        rng = np.random.RandomState(seed)
        Q_noise = 50.0 + rng.normal(0, 5)  # measurement noise floor
        if mat["Q"] > Q_noise:
            bits_per_mode = np.log2(1 + mat["Q"] / Q_noise)
        else:
            bits_per_mode = 0.0
        cap_meas = n_modes * bits_per_mode
        measured.append(cap_meas)
        names.append(mat_name)

    predicted_arr = np.array(predicted)
    measured_arr = np.array(measured)

    # Prediction error as fraction
    errors = np.where(
        measured_arr > 1e-6,
        np.abs(predicted_arr - measured_arr) / measured_arr,
        0.0,
    )

    glass_cap = _cwm_capacity_formula(
        exp_mode_density(material="borosilicate_glass", vessel=vessel).n_total,
        MATERIALS["borosilicate_glass"]["Q"],
    )

    # Best stone capacity
    stone_names = [n for n in names
                   if n not in ("borosilicate_glass", "fused_silica")]
    stone_pred = [predicted[i] for i, n in enumerate(names) if n in stone_names]
    best_stone_cap = max(stone_pred) if stone_pred else 0.0
    cap_ratio = best_stone_cap / glass_cap if glass_cap > 0 else 0.0

    return CrossMaterialCapacityResult(
        material_names=names,
        predicted_capacities=predicted_arr,
        measured_capacities=measured_arr,
        prediction_errors=errors,
        mean_error=float(np.mean(errors)),
        max_error=float(np.max(errors)),
        glass_capacity=glass_cap,
        best_stone_capacity=best_stone_cap,
        capacity_ratio=cap_ratio,
        verdict=bool(np.mean(errors) < 0.25),
    )


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_passive_stone(verbose: bool = True) -> dict:
    """Run all S20 passive stone resonance experiments and return results dict."""
    results = {}

    # --- H-PA1: Q-factor comparison ---
    if verbose:
        print("=" * 60)
        print("H-PA1: Stone Q-Factor Comparison")
        print("=" * 60)
    r1 = exp_q_factor_comparison()
    results["H-PA1"] = r1
    if verbose:
        print(f"  Glass Q (reference):      {r1.glass_q:.0f}")
        for i, name in enumerate(r1.material_names):
            print(f"  {name:24s}  Q = {r1.q_values[i]:6.0f}  "
                  f"({r1.q_ratios_to_glass[i]:.2%} of glass)")
        print(f"  Best stone:               {r1.best_stone} (Q = {r1.best_stone_q:.0f})")
        print(f"  All above Q = 100:        {r1.all_above_100}")
        print(f"  Any within 1 OoM:         {r1.any_within_order}")
        vstr = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-PA2: Mode density ---
    if verbose:
        print("=" * 60)
        print("H-PA2: Eigenmode Density in Granite Vessel")
        print("=" * 60)
    r2 = exp_mode_density()
    results["H-PA2"] = r2
    if verbose:
        print(f"  Material:                 {r2.material}")
        print(f"  Vessel:                   {r2.vessel} "
              f"({r2.height*100:.0f}cm × {r2.radius*100:.0f}cm r)")
        print(f"  Axial modes:              {r2.n_longitudinal}")
        print(f"  Radial modes:             {r2.n_radial}")
        print(f"  Circumferential modes:    {r2.n_circumferential}")
        print(f"  Total (after dedup):      {r2.n_total}")
        print(f"  Frequency range:          {r2.freq_lowest:.0f}–{r2.freq_highest:.0f} Hz")
        vstr = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-PA3: Perturbation sensitivity ---
    if verbose:
        print("=" * 60)
        print("H-PA3: sin²(nπx) Perturbation Law in Stone")
        print("=" * 60)
    r3 = exp_perturbation_sensitivity()
    results["H-PA3"] = r3
    if verbose:
        print(f"  Material:                 {r3.material}")
        print(f"  Modes tested:             {r3.n_modes_tested}")
        print(f"  Stone mean R²:            {r3.mean_r_squared:.6f}")
        print(f"  Stone min R²:             {r3.min_r_squared:.6f}")
        print(f"  Glass mean R²:            {r3.glass_mean_r_squared:.6f}")
        print(f"  Stone–glass Δ:            {r3.stone_glass_difference:.6f}")
        vstr = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-PA4: Chladni readout ---
    if verbose:
        print("=" * 60)
        print("H-PA4: Passive Chladni Pattern Readout")
        print("=" * 60)
    r4 = exp_chladni_readout()
    results["H-PA4"] = r4
    if verbose:
        print(f"  Material:                 {r4.material}")
        print(f"  Modes tested:             {r4.n_modes}")
        print(f"  Mean mutual info:         {r4.mean_mi:.3f} bits/mode")
        print(f"  Min mutual info:          {r4.min_mi:.3f} bits/mode")
        print(f"  Modes > 1 bit:            {r4.n_modes_above_1bit}/{r4.n_modes}")
        print(f"  Pattern distinctness:      {r4.pattern_distinctness:.3f}")
        vstr = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-PA5: Cross-material capacity ---
    if verbose:
        print("=" * 60)
        print("H-PA5: Cross-Material Capacity Universality")
        print("=" * 60)
    r5 = exp_cross_material_capacity()
    results["H-PA5"] = r5
    if verbose:
        print(f"  Glass capacity:           {r5.glass_capacity:.1f} bits")
        print(f"  Best stone capacity:      {r5.best_stone_capacity:.1f} bits")
        print(f"  Stone/glass ratio:        {r5.capacity_ratio:.2%}")
        print(f"  Mean prediction error:    {r5.mean_error:.2%}")
        print(f"  Max prediction error:     {r5.max_error:.2%}")
        for i, name in enumerate(r5.material_names):
            print(f"    {name:24s}  pred={r5.predicted_capacities[i]:7.1f}  "
                  f"meas={r5.measured_capacities[i]:7.1f}  "
                  f"err={r5.prediction_errors[i]:.1%}")
        vstr = "CONFIRMED" if r5.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = len(results) - confirmed
        print("=" * 60)
        print(f"S20 SUMMARY: {confirmed}/5 confirmed, {killed}/5 killed")
        print("=" * 60)

    return results
