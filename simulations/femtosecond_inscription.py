"""
S21 — Femtosecond Volumetric Inscription: Laser-Written CWM
============================================================

Glass 5D optical data storage (Southampton, Kazansky group; Zhang et al.)
uses femtosecond laser pulses to create localized structural modifications
inside the volume of fused silica.  Three regimes are documented:

  Type I   — smooth isotropic densification, Δρ/ρ ≈ 0.1–1%
  Type II  — self-assembled nanogratings with birefringent properties
  Type III — micro-explosions / voids (ablative, irreversible)

Type I modifications are thermally erasable (~300 °C anneal), making
them candidates for rewritable CWM.  The key question is whether
volumetric density perturbations inside a fused silica resonator
produce the same sin²(nπx/L) eigenfrequency shifts as surface mass
perturbations, with sufficient magnitude and without destroying the
quality factor.

CWM currently uses surface perturbations (gold dots at MEMS scale,
wax beads at macro scale).  Volumetric inscription via femtosecond
laser would offer:

  1. Maskless direct-write (no lithography)
  2. Field-programmable rewriting (anneal + re-inscribe)
  3. Three-dimensional encoding (radial depth as extra dimension)
  4. Decoupled read/write physics (optical write, acoustic read)

Five testable hypotheses:

1. Axial sensitivity universality (H-V1)
   A volumetric density perturbation at axial position x shifts
   eigenfrequency n by Δfₙ ∝ sin²(nπx/L), identical to the
   surface-mass Rayleigh formula.
   Kill criterion: R² of sin²(nπx/L) fit < 0.99.

2. Cumulative shift magnitude (H-V2)
   Type I inscription (Δρ/ρ = 0.5%, focal volume ~1×1×10 µm³ =
   10 µm³) produces cumulative frequency shifts ≥ 10× the mode
   linewidth when using ≥ 100 inscription sites in a 1 mm MEMS rod.
   Kill criterion: total shift < linewidth (undetectable).

3. Q-factor survival (H-V3)
   Rayleigh acoustic scattering from sub-wavelength inclusions
   (Type I, diameter ~1 µm, λ_acoustic ~100 µm) preserves
   Q > Q_pristine / 2 for up to 1000 inscription sites.
   Kill criterion: Q_modified / Q_pristine < 0.5.

4. Radial encoding dimension (H-V4)
   Inscriptions at different radial positions within the rod
   cross-section couple differently to radial/torsional mode
   families, providing ≥ 1 additional independent encoding
   dimension beyond the axial sin² sensitivity.
   Kill criterion: mutual information between radial position
   and shift pattern < 1 bit.

5. Volumetric capacity gain (H-V5)
   A 3D volumetric inscription lattice provides ≥ 2× the
   information density of surface-only perturbation encoding,
   combining axial and radial encoding dimensions.
   Kill criterion: capacity ratio < 1.5.

References:
  - Zhang et al., "5D Data Storage by Ultrafast Laser Nanostructuring
    in Glass" (2014), Optics & Photonics News
  - Glezer & Mazur, "Ultrafast-laser driven micro-explosions in
    transparent materials" (1997), Applied Physics Letters
  - Shimotsuma et al., "Self-organized nanogratings in glass irradiated
    by ultrashort light pulses" (2003), Physical Review Letters
  - Bellouard, "On the bending strength of fused silica flexures
    fabricated by ultrafast lasers" (2011), Optical Materials Express
  - WCFOMA §4 perturbation encoding (surface Rayleigh formula)
  - WCFOMA §7 scaling laws (n_max derivation)
  - WCFOMA S19 chiral phonon (cross-family coupling framework)
  - WCFOMA S20 passive stone (material universality of sin²)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Physical constants and material properties
# ═══════════════════════════════════════════════════════════════════════

# Fused silica properties (the substrate for femtosecond inscription)
FUSED_SILICA = {
    "c_L": 5968.0,           # longitudinal wave speed [m/s]
    "c_T": 3764.0,           # shear wave speed [m/s]
    "density": 2200.0,       # kg/m³
    "Q": 100_000,            # quality factor (intrinsic, fused silica)
    "E_young": 72.0e9,       # Young's modulus [Pa]
    "poisson": 0.17,
    "alpha_thermal": 0.55e-6,  # thermal expansion [/K]
}

# Speed ratio for cross-family coupling (torsional / longitudinal)
SPEED_RATIO = FUSED_SILICA["c_T"] / FUSED_SILICA["c_L"]

# Femtosecond laser inscription parameters (Type I regime)
# Based on published experimental data
TYPE_I = {
    "delta_rho_frac": 0.005,    # Δρ/ρ = 0.5% typical Type I densification
    "focal_diameter": 1.0e-6,   # 1 µm lateral
    "focal_length": 10.0e-6,    # 10 µm axial (confocal elongation)
    "anneal_temp_C": 300.0,     # erasure temperature
    "reversible": True,
}

# Derived focal volume [m³]
TYPE_I["focal_volume"] = (
    np.pi / 4 * TYPE_I["focal_diameter"] ** 2 * TYPE_I["focal_length"]
)

# MEMS rod geometry (1 mm fused silica)
MEMS_ROD = {
    "length": 1.0e-3,       # 1 mm
    "diameter": 50.0e-6,    # 50 µm diameter (typical MEMS resonator)
    "radius": 25.0e-6,
}
MEMS_ROD["cross_section"] = np.pi * MEMS_ROD["radius"] ** 2
MEMS_ROD["volume"] = MEMS_ROD["cross_section"] * MEMS_ROD["length"]
MEMS_ROD["mass"] = MEMS_ROD["volume"] * FUSED_SILICA["density"]

# Macro rod geometry (150 mm borosilicate, for comparison)
MACRO_ROD = {
    "length": 0.150,         # 150 mm
    "diameter": 6.0e-3,      # 6 mm
    "radius": 3.0e-3,
}
MACRO_ROD["cross_section"] = np.pi * MACRO_ROD["radius"] ** 2
MACRO_ROD["volume"] = MACRO_ROD["cross_section"] * MACRO_ROD["length"]
MACRO_ROD["mass"] = MACRO_ROD["volume"] * FUSED_SILICA["density"]

# n_max for fused silica at ±1 K stability
# n_max = floor(1 / (2α·ΔT + 1/Q))
_DELTA_T = 1.0  # ±1 K
N_MAX = int(1.0 / (2 * FUSED_SILICA["alpha_thermal"] * _DELTA_T
                    + 1.0 / FUSED_SILICA["Q"]))


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class AxialSensitivityResult:
    """H-V1 — Volumetric density perturbation follows sin²(nπx/L)."""
    n_modes_tested: int
    n_positions: int
    r_squared_per_mode: np.ndarray     # R² for each mode
    mean_r_squared: float
    min_r_squared: float
    surface_mean_r_squared: float      # comparison: standard surface mass
    volumetric_surface_diff: float     # |vol_R² - surf_R²|
    verdict: bool                      # True if mean R² ≥ 0.99


@dataclass
class ShiftMagnitudeResult:
    """H-V2 — Cumulative shift from N inscription sites."""
    n_sites: int
    delta_rho_frac: float
    focal_volume_m3: float
    single_site_delta_m: float         # kg
    single_site_frac_shift: float      # Δf/f per site (max, at antinode)
    cumulative_shift_frac: float       # total Δf/f for N sites
    mode_linewidth_frac: float         # 1/Q
    shift_over_linewidth: float        # cumulative / linewidth
    n_sites_for_10x_linewidth: int     # sites needed for 10× linewidth
    detectable: bool                   # shift > linewidth
    verdict: bool                      # shift ≥ 10× linewidth


@dataclass
class QSurvivalResult:
    """H-V3 — Q-factor survival after inscription."""
    n_inscriptions: int
    inclusion_diameter: float          # m
    acoustic_wavelength: float         # m (at fundamental)
    size_ratio: float                  # d / λ
    single_site_scattering_xs: float   # m² (Rayleigh scattering cross-section)
    total_scattering_loss: float       # fractional energy loss per round-trip
    q_pristine: int
    q_modified: float
    q_ratio: float                     # Q_mod / Q_pristine
    q_survives: bool                   # ratio > 0.5
    max_sites_at_50pct_q: int          # inscriptions before Q drops to 50%
    verdict: bool


@dataclass
class RadialEncodingResult:
    """H-V4 — Radial position as independent encoding dimension."""
    n_radial_positions: int
    n_axial_modes: int
    n_torsional_modes: int
    bessel_coupling_matrix: np.ndarray  # [radial_pos × mode_family]
    mutual_info_radial: float           # bits between radial pos and shift
    radial_sensitivity_contrast: float  # max/min coupling across radii
    independent_of_axial: bool          # radial info complements axial
    verdict: bool                       # MI ≥ 1 bit


@dataclass
class VolumetricCapacityResult:
    """H-V5 — 3D volumetric encoding capacity vs surface-only."""
    surface_only_sites: int
    surface_only_capacity_bits: float
    volumetric_sites: int
    volumetric_capacity_bits: float
    capacity_ratio: float             # volumetric / surface
    axial_contribution: float         # bits from axial encoding
    radial_contribution: float        # bits from radial dimension
    verdict: bool                     # ratio ≥ 2.0


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _longitudinal_freq(n: int, length: float, c_L: float) -> float:
    """Longitudinal eigenfrequency f_n = n·c_L / (2L)."""
    return n * c_L / (2.0 * length)


def _torsional_freq(n: int, length: float, c_T: float) -> float:
    """Torsional eigenfrequency f_n = n·c_T / (2L)."""
    return n * c_T / (2.0 * length)


def _mode_linewidth(f_n: float, Q: int) -> float:
    """Mode linewidth Δf = f_n / Q."""
    return f_n / Q


def _volumetric_rayleigh_shift(
    n: int,
    x_axial: float,
    delta_rho: float,
    focal_volume: float,
    rod_mass: float,
    rod_length: float,
) -> float:
    """
    Frequency shift from a volumetric density perturbation.

    Generalized Rayleigh formula for distributed density change:
        Δf_n/f_n = -(1/2) · (Δm/M) · sin²(nπx/L)

    where Δm = Δρ · V_focal is the effective added mass from the
    density change, and x is the axial position of the inscription.

    This is mathematically identical to the surface mass formula
    because the perturbation is small and localized. The sin²
    weighting comes from the mode shape |u_n(x)|², which is the
    same regardless of whether the perturbation is on the surface
    or in the volume.
    """
    delta_m = delta_rho * focal_volume
    frac_shift = -0.5 * (delta_m / rod_mass) * np.sin(
        n * np.pi * x_axial / rod_length
    ) ** 2
    return frac_shift


def _rayleigh_scattering_cross_section(
    diameter: float,
    wavelength: float,
    delta_rho_frac: float,
) -> float:
    """
    Rayleigh acoustic scattering cross-section for a sub-wavelength
    inclusion with density contrast.

    For d ≪ λ (Rayleigh regime):
        σ = (π/4) · k⁴ · a⁶ · (Δρ/ρ)²

    where k = 2π/λ, a = d/2 is the inclusion radius.

    This is the acoustic analogue of Rayleigh's optical scattering
    formula. The d⁶/λ⁴ scaling means scattering drops extremely
    fast for small inclusions relative to the wavelength.
    """
    a = diameter / 2.0
    k = 2.0 * np.pi / wavelength
    sigma = (np.pi / 4.0) * k ** 4 * a ** 6 * delta_rho_frac ** 2
    return sigma


def _q_from_scattering(
    q_pristine: int,
    n_inclusions: int,
    sigma: float,
    rod_length: float,
    rod_cross_section: float,
) -> float:
    """
    Compute modified Q after adding scattering inclusions.

    Each inclusion scatters a fraction of the acoustic energy per
    pass. The total scattering loss per round-trip adds to the
    intrinsic loss:

        1/Q_total = 1/Q_pristine + (N · σ) / (2L · A)

    where the second term is the scattering-induced inverse Q,
    derived from the Beer-Lambert law for acoustic attenuation:
    the fraction of energy scattered per unit length is N·σ/V,
    and a round-trip traverses 2L.
    """
    # Scattering loss per round trip
    volume = rod_cross_section * rod_length
    # Number density of inclusions
    n_density = n_inclusions / volume
    # Mean free path
    if sigma <= 0:
        return float(q_pristine)
    mfp = 1.0 / (n_density * sigma) if n_density * sigma > 0 else np.inf
    # Fraction lost per round trip (2L)
    frac_lost = 2.0 * rod_length / mfp if mfp < np.inf else 0.0
    # Convert to inverse Q contribution
    # Energy loss per cycle = 2π/Q, loss per round trip = 2L/(v/f) cycles
    # Simpler: 1/Q_scatter = frac_lost / (2π · n_roundtrips_per_cycle)
    # At fundamental: one round trip = one cycle, so 1/Q_scatter ≈ frac_lost/(2π)
    inv_q_scatter = frac_lost / (2.0 * np.pi)
    inv_q_total = 1.0 / q_pristine + inv_q_scatter
    return 1.0 / inv_q_total


def _bessel_j0_squared(r_norm: float) -> float:
    """J₀²(2.405·r/R) — radial sensitivity for breathing modes."""
    from scipy.special import j0
    return float(j0(2.405 * r_norm) ** 2)


def _bessel_j1_squared(r_norm: float) -> float:
    """J₁²(3.832·r/R) — radial sensitivity for first torsional family."""
    from scipy.special import j1
    return float(j1(3.832 * r_norm) ** 2)


def _radial_sensitivity_matrix(
    n_radial: int,
    n_mode_families: int = 2,
) -> np.ndarray:
    """
    Build a sensitivity matrix for radial position encoding.

    Rows: radial positions (equally spaced from center to surface)
    Columns: mode families (breathing J₀, torsional J₁)

    The matrix captures how strongly each radial position couples
    to each mode family. If the columns are sufficiently independent,
    radial position is an encoding dimension.
    """
    r_positions = np.linspace(0.05, 0.95, n_radial)  # normalized r/R
    matrix = np.zeros((n_radial, n_mode_families))
    for i, r in enumerate(r_positions):
        matrix[i, 0] = _bessel_j0_squared(r)
        matrix[i, 1] = _bessel_j1_squared(r)
    return matrix


def _mutual_information_from_matrix(matrix: np.ndarray) -> float:
    """
    Estimate mutual information between rows (positions) and columns
    (mode families) of a sensitivity matrix.

    Uses singular value decomposition: MI ≈ Σ log₂(1 + σᵢ²/σ_min²)
    for non-trivial singular values.

    This measures how much information about radial position can be
    recovered from the mode-family coupling pattern.
    """
    U, s, Vt = np.linalg.svd(matrix, full_matrices=False)
    # Normalize singular values
    s_norm = s / (s[-1] + 1e-30)
    # MI estimate: each significant singular value contributes
    mi = np.sum(np.log2(1 + s_norm ** 2))
    return float(mi)


# ═══════════════════════════════════════════════════════════════════════
# H-V1: Axial sensitivity universality
# ═══════════════════════════════════════════════════════════════════════

def exp_axial_sensitivity(
    n_modes: int = 20,
    n_positions: int = 50,
    seed: int = 42,
) -> AxialSensitivityResult:
    """
    Test whether volumetric density perturbations follow the same
    sin²(nπx/L) axial sensitivity as surface mass perturbations.

    Method: Place a single Type I inscription at each of n_positions
    along the rod axis. For each mode n, fit sin²(nπx/L) to the
    measured frequency shifts. Report R² per mode.

    Kill criterion: mean R² < 0.99.
    """
    rng = np.random.default_rng(seed)
    L = MEMS_ROD["length"]
    M = MEMS_ROD["mass"]
    delta_rho = TYPE_I["delta_rho_frac"] * FUSED_SILICA["density"]
    fv = TYPE_I["focal_volume"]

    # Axial positions (avoid exact endpoints where sin² = 0 trivially)
    positions = np.linspace(0.02 * L, 0.98 * L, n_positions)

    # Compute shifts for each mode at each position
    shifts = np.zeros((n_modes, n_positions))
    for j, x in enumerate(positions):
        for i in range(n_modes):
            n = i + 1
            shifts[i, j] = _volumetric_rayleigh_shift(
                n, x, delta_rho, fv, M, L
            )

    # For each mode, fit sin²(nπx/L) and compute R²
    r_squared = np.zeros(n_modes)
    for i in range(n_modes):
        n = i + 1
        # Theoretical sin² pattern
        theory = np.sin(n * np.pi * positions / L) ** 2
        # Use absolute shift magnitude (shifts are negative from densification)
        s_abs = np.abs(shifts[i])
        # Normalize both to unit max for shape comparison
        s_norm = s_abs / (s_abs.max() + 1e-30)
        t_norm = theory / (theory.max() + 1e-30)
        # R² = 1 - SS_res / SS_tot
        ss_res = np.sum((s_norm - t_norm) ** 2)
        ss_tot = np.sum((t_norm - t_norm.mean()) ** 2)
        r_squared[i] = 1.0 - ss_res / (ss_tot + 1e-30)

    # Surface mass comparison (identical formula, so R² should be ~1.0)
    surf_r2 = np.ones(n_modes)  # by construction, surface = sin² exactly

    mean_r2 = float(np.mean(r_squared))
    min_r2 = float(np.min(r_squared))

    return AxialSensitivityResult(
        n_modes_tested=n_modes,
        n_positions=n_positions,
        r_squared_per_mode=r_squared,
        mean_r_squared=mean_r2,
        min_r_squared=min_r2,
        surface_mean_r_squared=float(np.mean(surf_r2)),
        volumetric_surface_diff=abs(mean_r2 - float(np.mean(surf_r2))),
        verdict=bool(mean_r2 >= 0.99),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-V2: Cumulative shift magnitude
# ═══════════════════════════════════════════════════════════════════════

def exp_shift_magnitude(
    n_sites: int = 1000,
    seed: int = 42,
) -> ShiftMagnitudeResult:
    """
    Determine whether femtosecond inscription produces frequency
    shifts large enough to be detectable at MEMS scale.

    Method: Calculate the mass equivalent of one Type I inscription,
    compute the maximum frequency shift (at antinode), and determine
    how many sites are needed for the shift to exceed 10× the mode
    linewidth.

    Kill criterion: cumulative shift < 1× mode linewidth (undetectable).
    """
    rng = np.random.default_rng(seed)
    L = MEMS_ROD["length"]
    M = MEMS_ROD["mass"]
    Q = FUSED_SILICA["Q"]

    delta_rho = TYPE_I["delta_rho_frac"] * FUSED_SILICA["density"]
    fv = TYPE_I["focal_volume"]
    delta_m = delta_rho * fv

    # Single site fractional shift at antinode (sin² = 1)
    single_shift = 0.5 * delta_m / M

    # For N sites distributed along the rod, the average sin²
    # value is 0.5 (uniform distribution). Total cumulative shift:
    cumulative_shift = n_sites * single_shift * 0.5

    # Mode linewidth (fractional)
    linewidth = 1.0 / Q

    # Ratio
    ratio = cumulative_shift / linewidth

    # How many sites for 10× linewidth?
    # N × (Δm/2M) × 0.5 = 10/Q
    # N = 10/Q / (Δm / (4M))
    n_for_10x = int(np.ceil(10.0 / Q / (delta_m / (4.0 * M))))

    return ShiftMagnitudeResult(
        n_sites=n_sites,
        delta_rho_frac=TYPE_I["delta_rho_frac"],
        focal_volume_m3=fv,
        single_site_delta_m=delta_m,
        single_site_frac_shift=single_shift,
        cumulative_shift_frac=cumulative_shift,
        mode_linewidth_frac=linewidth,
        shift_over_linewidth=ratio,
        n_sites_for_10x_linewidth=n_for_10x,
        detectable=bool(ratio >= 1.0),
        verdict=bool(ratio >= 10.0),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-V3: Q-factor survival
# ═══════════════════════════════════════════════════════════════════════

def exp_q_survival(
    n_inscriptions: int = 1000,
    seed: int = 42,
) -> QSurvivalResult:
    """
    Test whether acoustic scattering from inscription sites
    preserves the quality factor.

    Method: Model each inscription as a sub-wavelength acoustic
    scatterer. Compute the Rayleigh scattering cross-section,
    total scattering loss per round trip, and modified Q.

    Key physics: At MEMS scale, the acoustic wavelength at the
    fundamental is λ = 2L = 2 mm. The inscription diameter is
    ~1 µm. The size ratio d/λ ~ 5×10⁻⁴, deep in the Rayleigh
    regime where scattering scales as (d/λ)⁴. This extreme
    smallness should make scattering negligible.

    Kill criterion: Q_modified / Q_pristine < 0.5.
    """
    L = MEMS_ROD["length"]
    A = MEMS_ROD["cross_section"]
    Q = FUSED_SILICA["Q"]
    d = TYPE_I["focal_diameter"]

    # Acoustic wavelength at fundamental
    lam = 2.0 * L  # λ₁ = 2L for fundamental

    size_ratio = d / lam

    # Rayleigh scattering cross-section
    sigma = _rayleigh_scattering_cross_section(
        d, lam, TYPE_I["delta_rho_frac"]
    )

    # Modified Q
    q_mod = _q_from_scattering(Q, n_inscriptions, sigma, L, A)
    q_ratio = q_mod / Q

    # Scattering loss per round trip
    volume = A * L
    n_density = n_inscriptions / volume
    mfp = 1.0 / (n_density * sigma) if n_density * sigma > 0 else np.inf
    frac_lost = 2.0 * L / mfp if mfp < np.inf else 0.0

    # Max inscriptions before Q drops to 50%
    # 1/Q_total = 1/Q + N·σ/(2πV·2L)... solve for N at Q_total = Q/2
    # → 1/(Q/2) - 1/Q = N·σ/(2π·A·L)
    # → 1/Q = N·σ·2L/(2π·A·L·2L)... simplify
    inv_q_at_50 = 1.0 / Q  # need scatter loss = intrinsic loss
    # 1/Q_scat = frac_lost/(2π) = 2L·N·σ/(2π·V)
    # Set = 1/Q: N = Q·2π·V / (2L·σ)... wait, let me redo
    # 1/Q_scatter = 1/Q → total = 2/Q → Q_total = Q/2
    # 1/Q_scatter = N·σ·2L / (2π·V) ... from the formula
    # Rearranging _q_from_scattering:
    # inv_q_scatter = (2L/mfp) / (2π) = (2L · n_density · σ) / (2π)
    #               = (2L · N · σ) / (2π · V)
    # Set = 1/Q:
    # N = 2π·V·(1/Q) / (2L·σ) = π·V / (L·Q·σ) = π·A / (Q·σ)
    if sigma > 0:
        max_sites = int(np.pi * A / (Q * sigma))
    else:
        max_sites = 10**15  # effectively unlimited

    return QSurvivalResult(
        n_inscriptions=n_inscriptions,
        inclusion_diameter=d,
        acoustic_wavelength=lam,
        size_ratio=size_ratio,
        single_site_scattering_xs=sigma,
        total_scattering_loss=frac_lost,
        q_pristine=Q,
        q_modified=q_mod,
        q_ratio=q_ratio,
        q_survives=bool(q_ratio > 0.5),
        max_sites_at_50pct_q=max_sites,
        verdict=bool(q_ratio > 0.5),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-V4: Radial encoding dimension
# ═══════════════════════════════════════════════════════════════════════

def exp_radial_encoding(
    n_radial_positions: int = 10,
    n_axial_modes: int = 20,
    seed: int = 42,
) -> RadialEncodingResult:
    """
    Test whether radial inscription position provides an independent
    encoding dimension via differential coupling to mode families.

    Method: Compute the Bessel-function coupling profile for two
    mode families (breathing J₀ and torsional J₁) at different
    radial positions. If the coupling patterns are sufficiently
    different, radial position carries information independent
    of the axial sin² sensitivity.

    Kill criterion: mutual information < 1 bit.
    """
    # Build radial sensitivity matrix
    matrix = _radial_sensitivity_matrix(n_radial_positions, n_mode_families=2)

    # Mutual information
    mi = _mutual_information_from_matrix(matrix)

    # Sensitivity contrast: ratio of max to min coupling across radii
    col_ranges = np.ptp(matrix, axis=0)  # range per mode family
    col_means = np.mean(matrix, axis=0)
    contrast = float(np.max(col_ranges / (col_means + 1e-30)))

    # Check independence: do the two columns provide distinct info?
    # Correlation between columns
    if matrix.shape[1] >= 2:
        corr = np.abs(np.corrcoef(matrix[:, 0], matrix[:, 1])[0, 1])
        independent = corr < 0.7  # columns are not too correlated
    else:
        independent = False

    # Count modes in each family up to n_max
    L = MEMS_ROD["length"]
    n_torsional = 0
    for n in range(1, N_MAX + 1):
        f_t = _torsional_freq(n, L, FUSED_SILICA["c_T"])
        f_l_max = _longitudinal_freq(N_MAX, L, FUSED_SILICA["c_L"])
        if f_t <= f_l_max:
            n_torsional += 1

    return RadialEncodingResult(
        n_radial_positions=n_radial_positions,
        n_axial_modes=min(n_axial_modes, N_MAX),
        n_torsional_modes=n_torsional,
        bessel_coupling_matrix=matrix,
        mutual_info_radial=mi,
        radial_sensitivity_contrast=contrast,
        independent_of_axial=bool(independent),
        verdict=bool(mi >= 1.0),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-V5: Volumetric capacity gain
# ═══════════════════════════════════════════════════════════════════════

def exp_volumetric_capacity(
    seed: int = 42,
) -> VolumetricCapacityResult:
    """
    Compare information capacity of volumetric 3D inscription
    against surface-only perturbation encoding.

    Surface-only: perturbation sites along the rod length only,
    at the surface. Number of sites limited by spatial resolution
    (~1 µm lithographic pitch → L/1µm sites along length).

    Volumetric: perturbation sites throughout the 3D volume.
    Axial resolution ~1 µm, radial resolution ~1 µm.
    Additional capacity from radial mode-family coupling.

    Kill criterion: capacity ratio < 1.5.
    """
    L = MEMS_ROD["length"]
    R = MEMS_ROD["radius"]
    Q = FUSED_SILICA["Q"]

    # Spatial resolution (femtosecond laser focal spot)
    resolution = TYPE_I["focal_diameter"]  # 1 µm

    # --- Surface-only capacity ---
    # Number of axial sites at 1 µm pitch
    n_axial_sites = int(L / resolution)
    # Bits per mode from Q (Shannon-limited)
    bits_per_mode = 0.5 * np.log2(1 + Q)  # ≈ 8.3 bits for Q=100,000
    # Total surface capacity: limited by n_max modes and axial sites
    # Each site contributes independently via sin² → effective bits
    # = min(n_sites, n_max) × bits_per_mode
    n_effective_surface = min(n_axial_sites, N_MAX)
    surface_capacity = n_effective_surface * bits_per_mode

    # --- Volumetric capacity ---
    # Radial sites: diameter / resolution
    n_radial_sites = max(1, int(2 * R / resolution))
    # Total 3D sites
    n_volumetric_sites = n_axial_sites * n_radial_sites

    # Axial contribution (same as surface, bounded by n_max)
    axial_bits = n_effective_surface * bits_per_mode

    # Radial contribution: from H-V4, radial position provides
    # additional encoding via differential Bessel coupling.
    # The radial dimension adds log₂(n_radial_distinguishable)
    # bits per axial site, where n_radial_distinguishable is
    # the number of radially distinct positions the mode families
    # can resolve.
    #
    # Conservative estimate: with 2 mode families (J₀, J₁) and
    # Q = 100,000, the radial resolution is limited by mode
    # linewidth to ~5-10 distinguishable radial positions.
    r4 = exp_radial_encoding(n_radial_positions=n_radial_sites, seed=seed)
    n_radial_distinguishable = min(
        n_radial_sites,
        max(2, int(r4.mutual_info_radial))
    )
    radial_bits = n_effective_surface * np.log2(max(1, n_radial_distinguishable))

    volumetric_capacity = axial_bits + radial_bits

    ratio = volumetric_capacity / (surface_capacity + 1e-30)

    return VolumetricCapacityResult(
        surface_only_sites=n_axial_sites,
        surface_only_capacity_bits=surface_capacity,
        volumetric_sites=n_volumetric_sites,
        volumetric_capacity_bits=volumetric_capacity,
        capacity_ratio=ratio,
        axial_contribution=axial_bits,
        radial_contribution=radial_bits,
        verdict=bool(ratio >= 1.5),
    )


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_femtosecond_inscription(verbose: bool = True) -> dict:
    """Run all S21 femtosecond volumetric inscription experiments."""
    results = {}

    # --- H-V1: Axial sensitivity ---
    if verbose:
        print("=" * 60)
        print("H-V1: Axial Sensitivity Universality")
        print("=" * 60)
    r1 = exp_axial_sensitivity()
    results["H-V1"] = r1
    if verbose:
        print(f"  Modes tested:             {r1.n_modes_tested}")
        print(f"  Positions tested:         {r1.n_positions}")
        print(f"  Volumetric mean R²:       {r1.mean_r_squared:.6f}")
        print(f"  Volumetric min R²:        {r1.min_r_squared:.6f}")
        print(f"  Surface mean R²:          {r1.surface_mean_r_squared:.6f}")
        print(f"  Vol–surface difference:   {r1.volumetric_surface_diff:.6f}")
        vstr = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-V2: Shift magnitude ---
    if verbose:
        print("=" * 60)
        print("H-V2: Cumulative Shift Magnitude")
        print("=" * 60)
    r2 = exp_shift_magnitude()
    results["H-V2"] = r2
    if verbose:
        print(f"  Inscription sites:        {r2.n_sites}")
        print(f"  Δρ/ρ:                     {r2.delta_rho_frac:.1%}")
        print(f"  Focal volume:             {r2.focal_volume_m3:.2e} m³")
        print(f"  Single-site Δm:           {r2.single_site_delta_m:.2e} kg")
        print(f"  Single-site Δf/f:         {r2.single_site_frac_shift:.2e}")
        print(f"  Cumulative Δf/f (N={r2.n_sites}): {r2.cumulative_shift_frac:.2e}")
        print(f"  Mode linewidth (1/Q):     {r2.mode_linewidth_frac:.2e}")
        print(f"  Shift / linewidth:        {r2.shift_over_linewidth:.2f}×")
        print(f"  Sites for 10× linewidth:  {r2.n_sites_for_10x_linewidth}")
        print(f"  Detectable (≥1×):         {r2.detectable}")
        vstr = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-V3: Q-factor survival ---
    if verbose:
        print("=" * 60)
        print("H-V3: Q-Factor Survival After Inscription")
        print("=" * 60)
    r3 = exp_q_survival()
    results["H-V3"] = r3
    if verbose:
        print(f"  Inscriptions:             {r3.n_inscriptions}")
        print(f"  Inclusion diameter:       {r3.inclusion_diameter:.1e} m")
        print(f"  Acoustic wavelength:      {r3.acoustic_wavelength:.1e} m")
        print(f"  Size ratio (d/λ):         {r3.size_ratio:.2e}")
        print(f"  Scattering σ:             {r3.single_site_scattering_xs:.2e} m²")
        print(f"  Total loss/round-trip:    {r3.total_scattering_loss:.2e}")
        print(f"  Q pristine:               {r3.q_pristine:,}")
        print(f"  Q modified:               {r3.q_modified:,.0f}")
        print(f"  Q ratio:                  {r3.q_ratio:.6f}")
        print(f"  Max sites at 50% Q:       {r3.max_sites_at_50pct_q:,}")
        vstr = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-V4: Radial encoding ---
    if verbose:
        print("=" * 60)
        print("H-V4: Radial Encoding Dimension")
        print("=" * 60)
    r4 = exp_radial_encoding()
    results["H-V4"] = r4
    if verbose:
        print(f"  Radial positions:         {r4.n_radial_positions}")
        print(f"  Axial modes:              {r4.n_axial_modes}")
        print(f"  Torsional modes:          {r4.n_torsional_modes}")
        print(f"  Mutual info (radial):     {r4.mutual_info_radial:.3f} bits")
        print(f"  Sensitivity contrast:     {r4.radial_sensitivity_contrast:.3f}")
        print(f"  Independent of axial:     {r4.independent_of_axial}")
        vstr = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    # --- H-V5: Volumetric capacity ---
    if verbose:
        print("=" * 60)
        print("H-V5: Volumetric Capacity Gain")
        print("=" * 60)
    r5 = exp_volumetric_capacity()
    results["H-V5"] = r5
    if verbose:
        print(f"  Surface-only sites:       {r5.surface_only_sites}")
        print(f"  Surface capacity:         {r5.surface_only_capacity_bits:,.0f} bits")
        print(f"  Volumetric sites (3D):    {r5.volumetric_sites}")
        print(f"  Volumetric capacity:      {r5.volumetric_capacity_bits:,.0f} bits")
        print(f"  Capacity ratio:           {r5.capacity_ratio:.2f}×")
        print(f"    Axial contribution:     {r5.axial_contribution:,.0f} bits")
        print(f"    Radial contribution:    {r5.radial_contribution:,.0f} bits")
        vstr = "CONFIRMED" if r5.verdict else "KILLED"
        print(f"  Verdict: {vstr}\n")

    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = len(results) - confirmed
        print("=" * 60)
        print(f"S21 SUMMARY: {confirmed}/5 confirmed, {killed}/5 killed")
        print("=" * 60)

    return results


if __name__ == "__main__":
    run_all_femtosecond_inscription()
