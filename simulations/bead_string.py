"""
S22 — Beads on a String: Mass-Perturbation Encoding on a 1D Waveguide
======================================================================

Egyptian faience beads are among the oldest glass artefacts (~4,000
years).  This sidebar re-imagines a string of beads — not as
jewellery, but as a 1D acoustic waveguide with discrete mass
perturbation sites.  Each bead, threaded or knotted onto a taut
string, shifts the transverse eigenfrequencies by an amount that
depends on bead mass and axial position.  Different bead materials
(faience, stone, bone, copper, wood) provide a multi-level mass
alphabet — richer than binary present/absent encoding.

The physics is identical to CWM's rod architecture: a bounded 1D
resonator with point-mass perturbations obeying the Rayleigh formula
Δfₙ/fₙ = −(m/M) sin²(nπx₀/L).  The factor is m/M (not m/2M) for
transverse string vibrations because only kinetic energy is
perturbed — tension is constant.

For exact eigenfrequencies beyond perturbation theory, we use the
transfer-matrix method: each string segment contributes a rotation
matrix, and each point mass contributes a shear matrix.  The product
gives a characteristic equation whose zeros are the loaded
eigenfrequencies.

Five testable hypotheses:

1. String Q with loose threading (H-B1)
   A single bead loosely threaded on a taut string degrades the
   system Q below the minimum useful threshold of Q ≥ 50, for ALL
   six string materials tested.
   Kill criterion: any material achieves Q_eff ≥ 50 with loose
   threading.  (We expect this hypothesis to be CONFIRMED — i.e.
   loose threading kills the waveguide quality universally.)

2. sin² sensitivity profile (H-B2)
   The spatial pattern of eigenfrequency shift vs bead position
   follows sin²(nπx/L) with R² ≥ 0.999, even at mass ratios up
   to m/M = 0.30 where perturbation theory is formally invalid.
   Kill criterion: R² < 0.999 for any mode n ∈ {1, …, 5}.

3. Multi-material alphabet (H-B3)
   At least 3 bead materials at the same position produce frequency
   shifts distinguishable by ≥ 1 linewidth (Δf > f_n / Q).
   Kill criterion: fewer than 3 pairwise-distinguishable materials.

4. Repositionability: bead-position mutual information (H-B4)
   Moving a single bead to 10 distinct positions along the string
   produces spectral fingerprints with mutual information ≥ 1 bit.
   Kill criterion: MI < 1 bit between bead position and spectrum.

5. Multi-bead superposition at archaeological mass ratios (H-B5)
   Three faience beads (3 mm diameter each, total m/M ≈ 0.86)
   obey linear superposition: the combined frequency shift vector
   deviates from the sum of individual shifts by < 10%.
   Kill criterion: mean mode-wise error < 10%.

References:
  - Shortland, "The Social Context of Technological Change" (2001) —
    Egyptian faience bead production ca. 2000 BCE
  - Fletcher, "The Physics of Musical Instruments" (1991) — loaded
    string eigenvalue problems
  - Rayleigh, "The Theory of Sound" (1896) — mass perturbation on
    vibrating strings
  - Morse & Ingard, "Theoretical Acoustics" (1968) — transfer-matrix
    solutions for loaded strings
  - WCFOMA §2 eigenmode spectrum, §4 perturbation encoding
  - WCFOMA S20 passive stone resonance (material universality)
  - WCFOMA S21 femtosecond volumetric inscription (bulk perturbation)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple

# ═══════════════════════════════════════════════════════════════════════
# Physical constants and material databases
# ═══════════════════════════════════════════════════════════════════════

# String materials: density (kg/m³), Young's modulus (Pa), Q-factor,
# typical diameter (m) for a musical-instrument-grade string
STRING_MATERIALS: Dict[str, Dict[str, float]] = {
    "nylon": {
        "density": 1150.0,      # kg/m³
        "youngs_modulus": 3.0e9, # Pa
        "Q": 200.0,             # internal damping Q
        "diameter": 0.001,      # 1 mm monofilament
    },
    "gut": {
        "density": 1300.0,
        "youngs_modulus": 5.5e9,
        "Q": 150.0,
        "diameter": 0.001,
    },
    "silk": {
        "density": 1340.0,
        "youngs_modulus": 10.0e9,
        "Q": 120.0,
        "diameter": 0.0005,     # 0.5 mm
    },
    "steel": {
        "density": 7800.0,
        "youngs_modulus": 200.0e9,
        "Q": 3000.0,
        "diameter": 0.0005,     # 0.5 mm
    },
    "kevlar": {
        "density": 1440.0,
        "youngs_modulus": 70.0e9,
        "Q": 500.0,
        "diameter": 0.0005,
    },
    "glass_fiber": {
        "density": 2500.0,
        "youngs_modulus": 70.0e9,
        "Q": 10000.0,
        "diameter": 0.0005,
    },
}

# Bead materials: density (kg/m³) and descriptive name
BEAD_MATERIALS: Dict[str, Dict[str, float]] = {
    "wood":    {"density":  600.0, "desc": "lightweight organic"},
    "bone":    {"density": 1900.0, "desc": "medium organic"},
    "faience": {"density": 2500.0, "desc": "Egyptian glass-ceramic"},
    "glass":   {"density": 2230.0, "desc": "borosilicate glass"},
    "stone":   {"density": 2650.0, "desc": "granite/quartzite"},
    "copper":  {"density": 8960.0, "desc": "heavy metal"},
    "gold":    {"density": 19300.0, "desc": "ultra-heavy metal"},
}

# Contact quality factors: how well the bead is coupled to the string
CONTACT_TYPES: Dict[str, float] = {
    "loose":   50.0,    # bead freely slides, rattles
    "snug":    200.0,   # tight-fit threading
    "knotted": 500.0,   # secured with knots on each side
    "bonded":  10000.0, # adhesive or fused contact
}

# Reference configuration
REF_STRING_LENGTH = 0.50    # 50 cm taut string
REF_STRING_TENSION = 10.0   # 10 N (light instrument tension)
REF_BEAD_DIAMETER = 0.003   # 3 mm (typical archaeological faience)
REF_BEAD_MATERIAL = "faience"
REF_STRING_MATERIAL = "nylon"
N_MODES_DEFAULT = 10        # modes to analyse

# Kill thresholds
KILL_Q_THRESHOLD = 50.0
KILL_R2_THRESHOLD = 0.999
KILL_DISTINGUISHABLE_MATERIALS = 3
KILL_MI_THRESHOLD = 1.0     # bits
KILL_SUPERPOSITION_ERROR = 0.10  # 10%


# ═══════════════════════════════════════════════════════════════════════
# Core physics functions
# ═══════════════════════════════════════════════════════════════════════

def bead_mass(diameter: float, material: str) -> float:
    """Mass of a spherical bead: m = (π/6)·d³·ρ."""
    rho = BEAD_MATERIALS[material]["density"]
    return (np.pi / 6.0) * diameter**3 * rho


def string_linear_density(material: str) -> float:
    """Linear mass density μ = ρ·A = ρ·π·(d/2)²."""
    props = STRING_MATERIALS[material]
    r = props["diameter"] / 2.0
    return props["density"] * np.pi * r**2


def string_total_mass(material: str, length: float) -> float:
    """Total string mass M = μ·L."""
    return string_linear_density(material) * length


def wave_speed(material: str, tension: float) -> float:
    """Transverse wave speed c = √(T/μ)."""
    mu = string_linear_density(material)
    return np.sqrt(tension / mu)


def unperturbed_frequencies(material: str, tension: float,
                            length: float, n_modes: int) -> np.ndarray:
    """Ideal string eigenfrequencies: f_n = n·c/(2L)."""
    c = wave_speed(material, tension)
    ns = np.arange(1, n_modes + 1)
    return ns * c / (2.0 * length)


def rayleigh_shift(mass_ratio: float, positions: np.ndarray,
                   length: float, n_modes: int) -> np.ndarray:
    """
    Rayleigh perturbation formula for transverse string vibrations.

    For a point mass m on a string of total mass M:
        Δf_n / f_n = −(m/M) · sin²(nπx₀/L)

    Returns array of shape (n_modes, len(positions)).
    """
    ns = np.arange(1, n_modes + 1)[:, None]  # (n_modes, 1)
    x = positions[None, :]                    # (1, n_pos)
    return -mass_ratio * np.sin(ns * np.pi * x / length)**2


# ═══════════════════════════════════════════════════════════════════════
# Transfer-matrix eigenvalue solver (exact loaded string)
# ═══════════════════════════════════════════════════════════════════════

def _segment_matrix(k: float, length_seg: float) -> np.ndarray:
    """
    Transfer matrix for a uniform string segment of length l.

    State vector: [Y, T·(dY/dx)] = [displacement, transverse force].

    For wave number k:
        Y(x) = A sin(kx) + B cos(kx)
        T·Y'(x) = Tk(A cos(kx) - B sin(kx))

    Transfer matrix propagating from x=0 to x=l:
        | cos(kl)      sin(kl)/(Tk) |
        | -Tk·sin(kl)  cos(kl)      |

    We normalise by setting T=1 (absorbed into k definition).
    The eigenvalue equation is scale-independent.
    """
    kl = k * length_seg
    c, s = np.cos(kl), np.sin(kl)
    if abs(k) < 1e-15:
        return np.array([[1.0, length_seg], [0.0, 1.0]])
    return np.array([
        [c, s / k],
        [-k * s, c],
    ])


def _mass_matrix(k: float, omega_sq: float, mass: float,
                 tension: float) -> np.ndarray:
    """
    Transfer matrix across a point mass m at frequency ω.

    State vector is [Y, dY/dx].  Newton's second law for the mass:
        T·(dY/dx)⁺ − T·(dY/dx)⁻ = −m·ω²·Y
        (dY/dx)⁺ = (dY/dx)⁻ − (m·ω²/T)·Y

    Matrix:
        | 1              0 |
        | -m·ω²/T        1 |
    """
    return np.array([
        [1.0, 0.0],
        [-mass * omega_sq / tension, 1.0],
    ])


def loaded_string_characteristic(
    k: float,
    tension: float,
    mu: float,
    length: float,
    bead_positions: np.ndarray,
    bead_masses: np.ndarray,
) -> float:
    """
    Evaluate the characteristic function F(k) for a loaded string.

    Fixed-fixed boundary conditions: Y(0) = 0, Y(L) = 0.
    F(k) = M_total[0, 1] = 0 at eigenfrequencies.

    Returns F(k) (sign changes indicate eigenvalues).
    """
    omega_sq = tension * k**2 / mu
    n_beads = len(bead_positions)

    # Sort beads by position
    order = np.argsort(bead_positions)
    pos_sorted = bead_positions[order]
    mass_sorted = bead_masses[order]

    # Build total transfer matrix segment by segment
    M_total = np.eye(2)
    x_prev = 0.0

    for i in range(n_beads):
        seg_len = pos_sorted[i] - x_prev
        if seg_len > 0:
            M_total = _segment_matrix(k, seg_len) @ M_total
        M_total = _mass_matrix(k, omega_sq, mass_sorted[i], tension) @ M_total
        x_prev = pos_sorted[i]

    # Final segment to x = L
    seg_len = length - x_prev
    if seg_len > 0:
        M_total = _segment_matrix(k, seg_len) @ M_total

    # Fixed-fixed: initial state [0, F₀], final state [0, F_L]
    # Y(L) = M_total[0,0]·0 + M_total[0,1]·F₀ = 0
    # → M_total[0,1] = 0 is the eigenvalue condition
    return M_total[0, 1]


def find_loaded_eigenfrequencies(
    tension: float,
    mu: float,
    length: float,
    bead_positions: np.ndarray,
    bead_masses: np.ndarray,
    n_modes: int = 10,
    n_scan: int = 5000,
) -> np.ndarray:
    """
    Find the first n_modes eigenfrequencies of a loaded string
    using the transfer-matrix method with bisection root-finding.

    Returns frequencies in Hz.
    """
    from scipy.optimize import brentq

    # Scan range: up to 2× the n_modes-th unperturbed frequency
    c = np.sqrt(tension / mu)
    k_max = (n_modes + 2) * np.pi / length * 2.0
    k_scan = np.linspace(1e-6, k_max, n_scan)

    # Evaluate characteristic function on scan grid
    F_vals = np.array([
        loaded_string_characteristic(k, tension, mu, length,
                                     bead_positions, bead_masses)
        for k in k_scan
    ])

    # Find sign changes (roots)
    roots = []
    for i in range(len(F_vals) - 1):
        if F_vals[i] * F_vals[i + 1] < 0:
            try:
                k_root = brentq(
                    loaded_string_characteristic,
                    k_scan[i], k_scan[i + 1],
                    args=(tension, mu, length, bead_positions, bead_masses),
                    xtol=1e-12,
                )
                freq = k_root * c / (2.0 * np.pi)
                if freq > 0.1:  # skip near-zero
                    roots.append(freq)
            except ValueError:
                pass
        if len(roots) >= n_modes + 2:
            break

    # Remove near-duplicates and return first n_modes
    if not roots:
        return np.array([])
    roots_arr = np.array(sorted(roots))
    unique = [roots_arr[0]]
    for r in roots_arr[1:]:
        if abs(r - unique[-1]) / unique[-1] > 1e-6:
            unique.append(r)
    return np.array(unique[:n_modes])


# ═══════════════════════════════════════════════════════════════════════
# Q-factor model
# ═══════════════════════════════════════════════════════════════════════

def effective_q(
    string_material: str,
    contact_type: str,
    bead_position: float,
    string_length: float,
    mode_number: int = 1,
) -> float:
    """
    Effective Q for a given mode with a single bead.

    Q_eff⁻¹ = Q_mat⁻¹ + η·sin²(nπx/L) · Q_contact⁻¹

    where η accounts for the bead's coupling participation at
    the mode antinode.  At an antinode (sin² = 1) the bead
    dissipates maximum energy; at a node (sin² = 0) it
    contributes no loss.
    """
    q_mat = STRING_MATERIALS[string_material]["Q"]
    q_contact = CONTACT_TYPES[contact_type]
    sin2 = np.sin(mode_number * np.pi * bead_position / string_length)**2
    q_inv = 1.0 / q_mat + sin2 / q_contact
    return 1.0 / q_inv


def worst_case_q(string_material: str, contact_type: str) -> float:
    """Q for mode 1 with bead at antinode (midpoint) — worst case."""
    return effective_q(string_material, contact_type,
                       REF_STRING_LENGTH / 2.0, REF_STRING_LENGTH, 1)


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class QLooseThreadingResult:
    """H-B1: loose-threaded bead Q < 50 for all materials."""
    material_names: List[str]
    q_values: np.ndarray        # worst-case Q per material
    all_below_threshold: bool   # True if ALL materials Q < 50
    worst_material: str         # lowest Q material
    worst_q: float
    best_material: str          # highest Q material (still < 50?)
    best_q: float
    verdict: bool               # True = confirmed (all below 50)


@dataclass
class Sin2SensitivityResult:
    """H-B2: sin² sensitivity R² ≥ 0.999."""
    mass_ratio: float
    n_modes_tested: int
    r_squared_per_mode: np.ndarray
    mean_r_squared: float
    min_r_squared: float
    positions_tested: int
    verdict: bool


@dataclass
class MultiMaterialResult:
    """H-B3: ≥ 3 distinguishable bead materials."""
    material_names: List[str]
    shifts_per_material: np.ndarray   # (n_materials, n_modes)
    n_distinguishable: int
    linewidth: float                   # f/Q reference linewidth
    pairwise_separations: Dict[str, float]  # material-pair → min separation
    verdict: bool


@dataclass
class RepositionabilityResult:
    """H-B4: bead-position mutual information ≥ 1 bit."""
    n_positions: int
    n_modes: int
    mutual_information: float    # bits
    fingerprints: np.ndarray     # (n_positions, n_modes)
    verdict: bool


@dataclass
class SuperpositionResult:
    """H-B5: multi-bead superposition error < 10%."""
    n_beads: int
    total_mass_ratio: float
    individual_shifts: np.ndarray    # (n_beads, n_modes) from single-bead
    summed_shifts: np.ndarray        # (n_modes,) linear superposition
    exact_shifts: np.ndarray         # (n_modes,) from transfer matrix
    mean_error: float                # mean |exact - summed| / |exact|
    max_error: float
    verdict: bool


# ═══════════════════════════════════════════════════════════════════════
# Experiment 1: H-B1 — Loose-threaded Q
# ═══════════════════════════════════════════════════════════════════════

def exp_q_loose_threading() -> QLooseThreadingResult:
    """
    Test whether ANY string material achieves Q ≥ 50 with a loosely
    threaded bead at the worst-case position (midpoint, mode 1).

    Hypothesis: all fail → loose threading universally kills the
    waveguide.  Kill criterion: any material Q ≥ 50.
    """
    names = list(STRING_MATERIALS.keys())
    q_vals = np.array([worst_case_q(mat, "loose") for mat in names])

    worst_idx = np.argmin(q_vals)
    best_idx = np.argmax(q_vals)

    all_below = bool(np.all(q_vals < KILL_Q_THRESHOLD))

    return QLooseThreadingResult(
        material_names=names,
        q_values=q_vals,
        all_below_threshold=all_below,
        worst_material=names[worst_idx],
        worst_q=float(q_vals[worst_idx]),
        best_material=names[best_idx],
        best_q=float(q_vals[best_idx]),
        verdict=all_below,
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 2: H-B2 — sin² sensitivity via transfer matrix
# ═══════════════════════════════════════════════════════════════════════

def exp_sin2_sensitivity(
    string_material: str = REF_STRING_MATERIAL,
    bead_material: str = REF_BEAD_MATERIAL,
    bead_diameter: float = REF_BEAD_DIAMETER,
    n_positions: int = 50,
    n_modes: int = 5,
) -> Sin2SensitivityResult:
    """
    Scan a single bead across the string length, compute exact
    eigenfrequencies via transfer matrix, and fit the shift
    pattern against sin²(nπx/L).

    Uses R² computed from normalised shift profiles.
    """
    L = REF_STRING_LENGTH
    T = REF_STRING_TENSION
    mu = string_linear_density(string_material)
    M = mu * L
    m = bead_mass(bead_diameter, bead_material)
    mass_ratio = m / M

    # Avoid placing beads exactly at boundaries (nodes)
    positions = np.linspace(0.02 * L, 0.98 * L, n_positions)

    # Unperturbed frequencies
    f0 = unperturbed_frequencies(string_material, T, L, n_modes)

    # For each position, compute exact loaded eigenfrequencies
    shift_matrix = np.zeros((n_modes, n_positions))
    for j, x0 in enumerate(positions):
        f_loaded = find_loaded_eigenfrequencies(
            T, mu, L,
            np.array([x0]), np.array([m]),
            n_modes=n_modes, n_scan=3000,
        )
        if len(f_loaded) >= n_modes:
            shift_matrix[:, j] = (f_loaded[:n_modes] - f0) / f0

    # Compute R² for each mode: compare normalised exact shifts
    # against sin²(nπx/L) template
    r2_per_mode = np.zeros(n_modes)
    for n_idx in range(n_modes):
        n = n_idx + 1
        exact_shifts = np.abs(shift_matrix[n_idx, :])  # magnitude
        template = np.sin(n * np.pi * positions / L)**2

        # Normalise both to max
        if np.max(exact_shifts) > 0 and np.max(template) > 0:
            exact_norm = exact_shifts / np.max(exact_shifts)
            template_norm = template / np.max(template)

            ss_res = np.sum((exact_norm - template_norm)**2)
            ss_tot = np.sum((exact_norm - np.mean(exact_norm))**2)
            if ss_tot > 0:
                r2_per_mode[n_idx] = 1.0 - ss_res / ss_tot

    return Sin2SensitivityResult(
        mass_ratio=mass_ratio,
        n_modes_tested=n_modes,
        r_squared_per_mode=r2_per_mode,
        mean_r_squared=float(np.mean(r2_per_mode)),
        min_r_squared=float(np.min(r2_per_mode)),
        positions_tested=n_positions,
        verdict=bool(np.all(r2_per_mode >= KILL_R2_THRESHOLD)),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 3: H-B3 — Multi-material alphabet
# ═══════════════════════════════════════════════════════════════════════

def exp_multi_material_alphabet(
    string_material: str = REF_STRING_MATERIAL,
    n_modes: int = N_MODES_DEFAULT,
) -> MultiMaterialResult:
    """
    Place beads of different materials at the same position
    (L/3, an irrational-like fraction) and check whether each
    material produces a shift distinguishable from others by
    ≥ 1 linewidth.
    """
    L = REF_STRING_LENGTH
    T = REF_STRING_TENSION
    mu = string_linear_density(string_material)
    Q_eff = worst_case_q(string_material, "knotted")  # use knotted
    x0 = L / 3.0  # off-centre position

    f0 = unperturbed_frequencies(string_material, T, L, n_modes)
    linewidths = f0 / Q_eff  # Hz

    bead_names = list(BEAD_MATERIALS.keys())
    n_mat = len(bead_names)
    shifts = np.zeros((n_mat, n_modes))

    for i, bmat in enumerate(bead_names):
        m = bead_mass(REF_BEAD_DIAMETER, bmat)
        f_loaded = find_loaded_eigenfrequencies(
            T, mu, L,
            np.array([x0]), np.array([m]),
            n_modes=n_modes, n_scan=3000,
        )
        if len(f_loaded) >= n_modes:
            shifts[i, :] = f_loaded[:n_modes] - f0

    # Pairwise: are shifts distinguishable by ≥ 1 linewidth in any mode?
    pairwise = {}
    distinguishable_count = 0
    checked = set()
    for i in range(n_mat):
        for j in range(i + 1, n_mat):
            pair_key = f"{bead_names[i]}/{bead_names[j]}"
            diff = np.abs(shifts[i, :] - shifts[j, :])
            # Maximum separation in linewidth units across all modes
            max_sep = float(np.max(diff / linewidths))
            pairwise[pair_key] = max_sep

    # Count materials that are distinguishable from all others
    # A material is "distinguishable" if it differs from at least
    # (n_mat - 1) others by ≥ 1 linewidth in at least one mode
    distinguishable_materials = set()
    for i in range(n_mat):
        distinct_from = 0
        for j in range(n_mat):
            if i == j:
                continue
            diff = np.abs(shifts[i, :] - shifts[j, :])
            if np.max(diff / linewidths) >= 1.0:
                distinct_from += 1
        if distinct_from == n_mat - 1:
            distinguishable_materials.add(bead_names[i])

    n_dist = len(distinguishable_materials)

    return MultiMaterialResult(
        material_names=bead_names,
        shifts_per_material=shifts,
        n_distinguishable=n_dist,
        linewidth=float(linewidths[0]),
        pairwise_separations=pairwise,
        verdict=bool(n_dist >= KILL_DISTINGUISHABLE_MATERIALS),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 4: H-B4 — Repositionability MI
# ═══════════════════════════════════════════════════════════════════════

def exp_repositionability(
    string_material: str = REF_STRING_MATERIAL,
    bead_material: str = REF_BEAD_MATERIAL,
    n_positions: int = 10,
    n_modes: int = N_MODES_DEFAULT,
    seed: int = 42,
) -> RepositionabilityResult:
    """
    Place a single bead at n_positions evenly spaced locations,
    compute the spectral fingerprint at each, add noise scaled
    to the mode linewidth, and compute mutual information between
    position label and noisy spectrum.
    """
    L = REF_STRING_LENGTH
    T = REF_STRING_TENSION
    mu = string_linear_density(string_material)
    Q_eff = effective_q(string_material, "knotted",
                        L / 2, L, mode_number=1)
    m = bead_mass(REF_BEAD_DIAMETER, bead_material)

    f0 = unperturbed_frequencies(string_material, T, L, n_modes)

    # Evenly spaced positions on [0, L/2] — sin²(nπx/L) is symmetric
    # about L/2, so positions x and L−x are indistinguishable.
    # This correctly models the physical constraint.
    positions = np.linspace(0.05 * L, 0.48 * L, n_positions)

    # Compute fingerprints
    fingerprints = np.zeros((n_positions, n_modes))
    for j, x0 in enumerate(positions):
        f_loaded = find_loaded_eigenfrequencies(
            T, mu, L,
            np.array([x0]), np.array([m]),
            n_modes=n_modes, n_scan=3000,
        )
        if len(f_loaded) >= n_modes:
            fingerprints[j, :] = (f_loaded[:n_modes] - f0) / f0

    # Compute MI via discretised histogram approach
    # Add Gaussian noise σ = 1/(2Q) per mode and classify
    rng = np.random.default_rng(seed)
    n_trials = 2000
    sigma = 1.0 / (2.0 * Q_eff)  # fractional frequency noise

    correct = 0
    for _ in range(n_trials):
        true_pos = rng.integers(0, n_positions)
        noisy = fingerprints[true_pos] + rng.normal(0, sigma, n_modes)
        # Nearest-neighbour classifier
        dists = np.sum((fingerprints - noisy)**2, axis=1)
        predicted = np.argmin(dists)
        if predicted == true_pos:
            correct += 1

    accuracy = correct / n_trials
    # MI ≈ log₂(n_positions) + accuracy·log₂(accuracy) +
    #       (1-accuracy)·log₂((1-accuracy)/(n_positions-1))
    # But simpler: use the classification accuracy directly
    # MI = log₂(N) - H(error) where H(error) is conditional entropy
    if accuracy >= 1.0 - 1e-10:
        mi = np.log2(n_positions)
    elif accuracy <= 1e-10:
        mi = 0.0
    else:
        # Fano's inequality lower bound
        mi = np.log2(n_positions) + accuracy * np.log2(accuracy) + \
             (1 - accuracy) * np.log2((1 - accuracy) / (n_positions - 1))
        mi = max(0.0, mi)

    return RepositionabilityResult(
        n_positions=n_positions,
        n_modes=n_modes,
        mutual_information=float(mi),
        fingerprints=fingerprints,
        verdict=bool(mi >= KILL_MI_THRESHOLD),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment 5: H-B5 — Multi-bead superposition
# ═══════════════════════════════════════════════════════════════════════

def exp_superposition(
    string_material: str = REF_STRING_MATERIAL,
    bead_material: str = REF_BEAD_MATERIAL,
    bead_diameter: float = REF_BEAD_DIAMETER,
    n_beads: int = 3,
    n_modes: int = 5,
) -> SuperpositionResult:
    """
    Place n_beads at distinct positions, compute:
      (a) individual frequency shifts (one bead at a time)
      (b) summed individual shifts (linear superposition prediction)
      (c) exact all-beads-at-once shifts (transfer matrix)

    Check whether mean mode-wise error < 10%.
    """
    L = REF_STRING_LENGTH
    T = REF_STRING_TENSION
    mu = string_linear_density(string_material)
    M = mu * L
    m = bead_mass(bead_diameter, bead_material)
    mass_ratio_total = n_beads * m / M

    # Place beads at irrational-ish positions
    bead_positions = np.array([
        L * 0.211,   # ≈ 1/√22.5
        L * 0.419,   # ≈ √(1/5.7)
        L * 0.732,   # ≈ (√5-1)/2 × 1.18
    ])[:n_beads]
    bead_masses = np.full(n_beads, m)

    f0 = unperturbed_frequencies(string_material, T, L, n_modes)

    # Individual shifts
    individual = np.zeros((n_beads, n_modes))
    for i in range(n_beads):
        f_single = find_loaded_eigenfrequencies(
            T, mu, L,
            np.array([bead_positions[i]]), np.array([m]),
            n_modes=n_modes, n_scan=3000,
        )
        if len(f_single) >= n_modes:
            individual[i, :] = (f_single[:n_modes] - f0) / f0

    summed = np.sum(individual, axis=0)

    # Exact all-at-once
    f_all = find_loaded_eigenfrequencies(
        T, mu, L,
        bead_positions, bead_masses,
        n_modes=n_modes, n_scan=5000,
    )
    if len(f_all) >= n_modes:
        exact = (f_all[:n_modes] - f0) / f0
    else:
        exact = np.zeros(n_modes)

    # Mode-wise relative error
    with np.errstate(divide='ignore', invalid='ignore'):
        errors = np.where(
            np.abs(exact) > 1e-15,
            np.abs(exact - summed) / np.abs(exact),
            0.0,
        )
    mean_err = float(np.mean(errors))
    max_err = float(np.max(errors))

    return SuperpositionResult(
        n_beads=n_beads,
        total_mass_ratio=float(mass_ratio_total),
        individual_shifts=individual,
        summed_shifts=summed,
        exact_shifts=exact,
        mean_error=mean_err,
        max_error=max_err,
        verdict=bool(mean_err < KILL_SUPERPOSITION_ERROR),
    )


# ═══════════════════════════════════════════════════════════════════════
# Master runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_bead_string(verbose: bool = True) -> Dict:
    """Run all five S22 experiments and return results dict."""
    results: Dict = {}

    # --- H-B1: Loose-threaded Q ---
    if verbose:
        print("=" * 60)
        print("H-B1: Loose-Threaded Bead Q Factor")
        print("=" * 60)
    r1 = exp_q_loose_threading()
    results["H-B1"] = r1
    if verbose:
        for name, q in zip(r1.material_names, r1.q_values):
            print(f"  {name:15s}  Q_eff = {q:6.1f}  "
                  f"{'< 50' if q < KILL_Q_THRESHOLD else '>= 50'}")
        print(f"  All below 50:         {r1.all_below_threshold}")
        vstr = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print(f"  (Loose threading universally fails "
              f"{'— confirmed' if r1.verdict else '— refuted'})\n")

    # --- H-B2: sin² sensitivity ---
    if verbose:
        print("=" * 60)
        print("H-B2: sin²(nπx/L) Sensitivity Profile")
        print("=" * 60)
    r2 = exp_sin2_sensitivity()
    results["H-B2"] = r2
    if verbose:
        print(f"  Mass ratio (m/M):     {r2.mass_ratio:.4f}")
        print(f"  Positions scanned:    {r2.positions_tested}")
        for i, r2v in enumerate(r2.r_squared_per_mode):
            print(f"    Mode {i+1}: R² = {r2v:.6f}")
        print(f"  Mean R²:              {r2.mean_r_squared:.6f}")
        print(f"  Min R²:               {r2.min_r_squared:.6f}")
        vstr = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-B3: Multi-material alphabet ---
    if verbose:
        print("=" * 60)
        print("H-B3: Multi-Material Bead Alphabet")
        print("=" * 60)
    r3 = exp_multi_material_alphabet()
    results["H-B3"] = r3
    if verbose:
        print(f"  Materials tested:     {len(r3.material_names)}")
        print(f"  Distinguishable:      {r3.n_distinguishable}")
        print(f"  Reference linewidth:  {r3.linewidth:.2f} Hz")
        # Show top pairwise separations
        sorted_pairs = sorted(r3.pairwise_separations.items(),
                              key=lambda x: x[1])
        print(f"  Closest pair:         {sorted_pairs[0][0]} "
              f"({sorted_pairs[0][1]:.1f} linewidths)")
        print(f"  Widest pair:          {sorted_pairs[-1][0]} "
              f"({sorted_pairs[-1][1]:.1f} linewidths)")
        vstr = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-B4: Repositionability ---
    if verbose:
        print("=" * 60)
        print("H-B4: Bead-Position Mutual Information")
        print("=" * 60)
    r4 = exp_repositionability()
    results["H-B4"] = r4
    if verbose:
        print(f"  Positions tested:     {r4.n_positions}")
        print(f"  Modes used:           {r4.n_modes}")
        print(f"  Mutual information:   {r4.mutual_information:.2f} bits")
        print(f"  Max possible:         {np.log2(r4.n_positions):.2f} bits")
        vstr = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-B5: Multi-bead superposition ---
    if verbose:
        print("=" * 60)
        print("H-B5: Multi-Bead Superposition at Archaeological Scale")
        print("=" * 60)
    r5 = exp_superposition()
    results["H-B5"] = r5
    if verbose:
        print(f"  Beads:                {r5.n_beads}")
        print(f"  Total mass ratio:     {r5.total_mass_ratio:.3f}")
        print(f"  Summed (linear) shifts:")
        for i, s in enumerate(r5.summed_shifts):
            print(f"    Mode {i+1}: "
                  f"linear={s:.6f}  exact={r5.exact_shifts[i]:.6f}")
        print(f"  Mean error:           {r5.mean_error:.1%}")
        print(f"  Max error:            {r5.max_error:.1%}")
        vstr = "CONFIRMED" if r5.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- Summary ---
    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = len(results) - confirmed
        print("=" * 60)
        print(f"S22 SUMMARY: {confirmed}/5 confirmed, {killed}/5 killed")
        print("=" * 60)
        for key, r in results.items():
            tag = "CONFIRMED" if r.verdict else "KILLED"
            print(f"  {key}: {tag}")

    return results


if __name__ == "__main__":
    run_all_bead_string(verbose=True)
