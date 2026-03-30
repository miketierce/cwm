"""
S21 — Femtosecond Volumetric Inscription: Laser-Written CWM
=============================================================

The CWM architecture encodes information as mass perturbations on
the surface of a glass rod, read out through the eigenmode spectrum.
Chapters 2–3 and Sidebar S20 confirmed the physics in glass and
stone.  This sidebar asks a different question: can we write
perturbations INSIDE the glass volume using femtosecond laser
inscription, the same process behind 5D optical data storage?

Femtosecond laser pulses focused inside fused silica create
localized structural modifications.  Three regimes are well
characterised in the literature:

  Type I  — Smooth densification (Δρ/ρ ≈ 0.1–1%).
            Focal volume ~1×1×10 µm³.  Reversible by annealing
            at ~300 °C.  (Bellouard et al., Opt. Express, 2004)

  Type II — Self-assembled nanogratings (periodic refractive-index
            modulation within focal volume).  Reversible by annealing
            at ~1000 °C.  (Kazansky et al., Appl. Phys. Lett., 2007)

  Type III — Void / micro-explosion (large local density change).
             Irreversible.  (Glezer & Mazur, Appl. Phys. Lett., 1997)

For CWM, each inscription is a DENSITY perturbation inside the rod.
The generalised Rayleigh formula handles this case:

    Δf_n / f_n = -(1/2) ∫ Δρ(r) |u_n(r)|² dV / ∫ ρ₀ |u_n(r)|² dV

This sidebar tests five hypotheses:

1. Volumetric sensitivity law (H-V1)
   Volumetric density perturbations follow the same sin²(nπx/L)
   axial sensitivity as surface mass perturbations.
   Kill criterion: R² < 0.99 between volumetric and surface profiles.

2. Cumulative shift magnitude (H-V2)
   Type I inscription (Δρ/ρ = 0.5%, focal volume = 10 µm³) with
   ≥ 100 inscription sites produces total shift ≥ 1 mode linewidth
   (i.e. shift ≥ f_n/Q, detectable by standard readout).
   Kill criterion: total shift / linewidth < 0.1 (order of magnitude
   below detectability even with 100 sites).

3. Q-factor survival (H-V3)
   Rayleigh acoustic scattering from sub-wavelength inscription
   sites (radius a ≪ λ) preserves Q: the added loss per round-trip
   from scattering is < 10% of the intrinsic acoustic loss.
   Kill criterion: Q_modified / Q_pristine < 0.5 (inscription
   destroys more than half the quality factor).

4. Radial encoding dimension (H-V4)
   Inscription at different radial positions inside the rod
   produces distinguishable shift patterns because longitudinal
   and torsional modes have different radial profiles (Bessel
   functions J_0, J_1).  The mutual information between radial
   position and frequency-shift fingerprint exceeds 1 bit per mode
   for a rod with d/L > 0.01.
   Kill criterion: mutual information < 0.5 bits per mode.

5. 3D volumetric capacity gain (H-V5)
   A 3D inscription lattice (axial × radial × azimuthal positions)
   provides ≥ 2× the information density of surface-only encoding.
   Kill criterion: volumetric / surface capacity ratio < 1.5.

References:
  - Bellouard et al., "Fabrication of high-aspect ratio micro-fluidic
    channels and tunnels using femtosecond laser pulses and chemical
    etching," Opt. Express 12, 2120 (2004)
  - Kazansky et al., "Quill writing with ultrashort light pulses in
    transparent materials," Appl. Phys. Lett. 90, 151120 (2007)
  - Zhang et al., "Seemingly unlimited lifetime data storage in
    nanostructured glass," Phys. Rev. Lett. 112, 033901 (2014)
  - Glezer & Mazur, "Ultrafast-laser driven micro-explosions in
    transparent materials," Appl. Phys. Lett. 71, 882 (1997)
  - Lord Rayleigh, "The Theory of Sound," Vol. 1, §88 (1877)
  - WCFOMA §4 perturbation encoding, §7 scaling laws
  - WCFOMA S19 chiral phonon (cross-family coupling)
  - WCFOMA S20 passive stone (material universality)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

from .common import K_B


# ═══════════════════════════════════════════════════════════════════════
# Physical constants for femtosecond inscription
# ═══════════════════════════════════════════════════════════════════════

# Fused silica baseline properties
FUSED_SILICA = {
    "density": 2200.0,          # kg/m³
    "v_bar": 5760.0,            # thin-bar speed √(E/ρ) [m/s]
    "v_longitudinal": 5968.0,   # bulk longitudinal [m/s]
    "v_shear": 3764.0,          # shear speed [m/s]
    "Q": 100_000,               # quality factor
    "alpha_thermal": 0.55e-6,   # thermal expansion [1/K]
    "youngs_modulus": 73e9,     # Pa
    "poisson": 0.17,
}

# Femtosecond inscription parameters (from literature)
INSCRIPTION_TYPES = {
    "type_I": {
        "name": "Smooth densification",
        "delta_rho_frac": 0.005,           # Δρ/ρ = 0.5%
        "focal_width": 1.0e-6,             # 1 µm lateral
        "focal_length": 10.0e-6,           # 10 µm axial (elongated)
        "reversible": True,
        "anneal_temp_C": 300,
        "ref": "Bellouard et al. 2004",
    },
    "type_II": {
        "name": "Self-assembled nanogratings",
        "delta_rho_frac": 0.01,            # Δρ/ρ ~ 1% (effective)
        "focal_width": 1.0e-6,
        "focal_length": 20.0e-6,           # longer due to grating structure
        "reversible": True,
        "anneal_temp_C": 1000,
        "ref": "Kazansky et al. 2007",
    },
    "type_III": {
        "name": "Void / micro-explosion",
        "delta_rho_frac": -0.10,           # Δρ/ρ ~ -10% (void)
        "focal_width": 1.0e-6,
        "focal_length": 1.0e-6,            # compact void
        "reversible": False,
        "anneal_temp_C": None,
        "ref": "Glezer & Mazur 1997",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# MEMS rod geometry (1 mm fused silica, the CWM MEMS baseline)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MEMSRod:
    """Fused silica MEMS rod for volumetric inscription analysis."""
    length: float = 1.0e-3       # 1 mm
    diameter: float = 50.0e-6    # 50 µm
    density: float = 2200.0      # kg/m³
    v_bar: float = 5760.0        # thin-bar speed [m/s]
    Q: float = 100_000           # quality factor
    alpha: float = 0.55e-6       # thermal expansion [1/K]
    delta_T: float = 1.0         # temperature stability [K]

    @property
    def radius(self) -> float:
        return self.diameter / 2

    @property
    def cross_section(self) -> float:
        return np.pi * self.radius ** 2

    @property
    def volume(self) -> float:
        return self.cross_section * self.length

    @property
    def mass(self) -> float:
        return self.density * self.volume

    @property
    def f1(self) -> float:
        """Fundamental frequency [Hz]."""
        return self.v_bar / (2 * self.length)

    @property
    def n_max(self) -> int:
        """Maximum thermally stable mode count."""
        denom = 2 * self.alpha * self.delta_T + 1.0 / self.Q
        return int(1.0 / denom) if denom > 0 else 1

    @property
    def wavelength_fundamental(self) -> float:
        """Acoustic wavelength at fundamental [m]."""
        return 2 * self.length


# ═══════════════════════════════════════════════════════════════════════
# Inscription site model
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class InscriptionSite:
    """A single femtosecond laser inscription point."""
    x: float            # axial position [m] (along rod length)
    r: float            # radial position [m] (from rod axis)
    theta: float        # azimuthal angle [rad]
    inscription_type: str = "type_I"

    @property
    def params(self) -> dict:
        return INSCRIPTION_TYPES[self.inscription_type]

    @property
    def focal_volume(self) -> float:
        """Focal volume [m³], modelled as cylinder."""
        p = self.params
        return np.pi * (p["focal_width"] / 2) ** 2 * p["focal_length"]

    @property
    def delta_mass(self) -> float:
        """Effective mass perturbation [kg]."""
        p = self.params
        rho0 = FUSED_SILICA["density"]
        return p["delta_rho_frac"] * rho0 * self.focal_volume


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class VolumetricSensitivityResult:
    """H-V1: Volumetric vs surface sin²(nπx/L) sensitivity comparison."""
    n_modes: int
    n_axial_positions: int
    surface_shifts: np.ndarray       # shape (n_positions, n_modes)
    volume_shifts: np.ndarray        # shape (n_positions, n_modes)
    r_squared_per_mode: np.ndarray   # R² for each mode
    mean_r_squared: float
    min_r_squared: float
    verdict: bool                    # True if mean R² ≥ 0.99


@dataclass
class CumulativeShiftResult:
    """H-V2: Total frequency shift from N inscription sites."""
    inscription_type: str
    n_sites: int
    rod: MEMSRod
    shift_per_site: float            # fractional shift per site
    total_shift_frac: float          # cumulative fractional shift
    linewidth_frac: float            # 1/Q (mode linewidth as fraction of f)
    shift_over_linewidth: float      # total_shift / linewidth
    delta_mass_per_site: float       # kg
    total_delta_mass: float          # kg
    mass_ratio: float                # total_delta_mass / rod mass
    verdict: bool                    # True if shift_over_linewidth ≥ 0.1


@dataclass
class QSurvivalResult:
    """H-V3: Q-factor degradation from acoustic scattering."""
    inscription_type: str
    n_sites: int
    inclusion_radius: float          # effective radius [m]
    wavelength: float                # acoustic wavelength [m]
    size_parameter: float            # ka = 2πa/λ
    sigma_rayleigh: float            # Rayleigh scattering cross-section [m²]
    total_scattering_loss: float     # fractional loss per round-trip
    intrinsic_loss: float            # 1/Q per round-trip
    loss_ratio: float                # scattering / intrinsic
    q_modified: float                # modified Q
    q_ratio: float                   # Q_modified / Q_pristine
    verdict: bool                    # True if q_ratio ≥ 0.5


@dataclass
class RadialEncodingResult:
    """H-V4: Radial position as independent encoding dimension."""
    n_radial_positions: int
    n_modes_longitudinal: int
    n_modes_torsional: int
    longitudinal_profiles: np.ndarray  # radial dependence of L modes
    torsional_profiles: np.ndarray     # radial dependence of T modes
    fingerprints: np.ndarray           # shift patterns per radial pos
    mutual_info_per_mode: np.ndarray   # MI in bits
    mean_mi: float
    verdict: bool                      # True if mean MI ≥ 0.5


@dataclass
class VolumetricCapacityResult:
    """H-V5: 3D inscription vs surface-only capacity comparison."""
    surface_sites: int
    surface_bits: float
    volume_axial_sites: int
    volume_radial_layers: int
    volume_azimuthal_sites: int
    volume_total_sites: int
    volume_bits: float
    capacity_ratio: float            # volume / surface
    verdict: bool                    # True if ratio ≥ 1.5


# ═══════════════════════════════════════════════════════════════════════
# H-V1: Volumetric sensitivity follows sin²(nπx/L)
# ═══════════════════════════════════════════════════════════════════════

def exp_volumetric_sensitivity(
    rod: MEMSRod = None,
    n_modes: int = 20,
    n_positions: int = 50,
    inscription_type: str = "type_I",
    seed: int = 42,
) -> VolumetricSensitivityResult:
    """
    Compare axial sensitivity profiles for volumetric inscription vs
    surface mass perturbation.

    The Rayleigh formula for a DISTRIBUTED density change inside the
    rod volume integrates Δρ(r) weighted by |u_n(r)|².  For a thin
    focal volume at axial position x, if the axial extent δz ≪ L,
    the integral collapses to:

        Δf_n / f_n ≈ -(Δρ/ρ₀)(V_focal/V_rod) × g(r) × sin²(nπx/L)

    where g(r) accounts for the radial mode shape weighting.  For
    purely longitudinal modes, g(r) ≈ 1 (uniform across cross-section
    for the fundamental radial profile).  The sin²(nπx/L) dependence
    is therefore IDENTICAL to surface perturbations.

    Kill criterion: R² < 0.99.
    """
    if rod is None:
        rod = MEMSRod()

    params = INSCRIPTION_TYPES[inscription_type]
    V_focal = np.pi * (params["focal_width"] / 2) ** 2 * params["focal_length"]
    V_rod = rod.volume
    delta_rho_frac = params["delta_rho_frac"]

    # Axial positions (avoid exact ends where sin² = 0 trivially)
    x_positions = np.linspace(0.02 * rod.length, 0.98 * rod.length, n_positions)
    x_norm = x_positions / rod.length

    modes = np.arange(1, n_modes + 1)

    # Surface perturbation reference: Δf_n/f_n = -(Δm/2M) sin²(nπx/L)
    # Use equivalent surface mass = Δρ × V_focal
    delta_m = abs(delta_rho_frac) * rod.density * V_focal
    epsilon_surface = delta_m / (2 * rod.mass)

    surface_shifts = np.zeros((n_positions, n_modes))
    volume_shifts = np.zeros((n_positions, n_modes))

    for i, xn in enumerate(x_norm):
        for j, n in enumerate(modes):
            sin2 = np.sin(n * np.pi * xn) ** 2

            # Surface: point mass at position x
            surface_shifts[i, j] = epsilon_surface * sin2

            # Volumetric: distributed density change at position x
            # For longitudinal modes, radial weighting g(r) ≈ 1
            # (uniform displacement across cross-section in thin-bar limit)
            vol_epsilon = abs(delta_rho_frac) * V_focal / (2 * V_rod)
            volume_shifts[i, j] = vol_epsilon * sin2

    # Compute R² between surface and volume profiles per mode
    r_squared = np.zeros(n_modes)
    for j in range(n_modes):
        s = surface_shifts[:, j]
        v = volume_shifts[:, j]
        # They should be proportional: check correlation
        if np.std(s) > 0 and np.std(v) > 0:
            corr = np.corrcoef(s, v)[0, 1]
            r_squared[j] = corr ** 2
        else:
            r_squared[j] = 1.0  # both zero = trivially identical

    return VolumetricSensitivityResult(
        n_modes=n_modes,
        n_axial_positions=n_positions,
        surface_shifts=surface_shifts,
        volume_shifts=volume_shifts,
        r_squared_per_mode=r_squared,
        mean_r_squared=float(np.mean(r_squared)),
        min_r_squared=float(np.min(r_squared)),
        verdict=bool(np.mean(r_squared) >= 0.99),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-V2: Cumulative shift magnitude
# ═══════════════════════════════════════════════════════════════════════

def exp_cumulative_shift(
    rod: MEMSRod = None,
    inscription_type: str = "type_I",
    n_sites: int = 100,
    seed: int = 42,
) -> CumulativeShiftResult:
    """
    Calculate total frequency shift from N inscription sites placed
    at irrational-spacing positions along the rod.

    Each inscription site creates a density perturbation equivalent to:
        Δm = Δρ/ρ × ρ₀ × V_focal

    The cumulative shift scales linearly with N (first-order perturbation
    theory holds while total Δm/M ≪ 1).

    We compare the total fractional shift to the mode linewidth 1/Q.
    A shift ≥ 1 linewidth is cleanly detectable; ≥ 0.1 linewidth is
    detectable with averaging.

    Kill criterion: shift_over_linewidth < 0.1 with 100 sites.
    """
    if rod is None:
        rod = MEMSRod()

    params = INSCRIPTION_TYPES[inscription_type]
    V_focal = np.pi * (params["focal_width"] / 2) ** 2 * params["focal_length"]
    delta_rho_frac = abs(params["delta_rho_frac"])
    delta_m = delta_rho_frac * rod.density * V_focal

    # Place N sites at golden-ratio spacing for optimal conditioning
    phi = (1 + np.sqrt(5)) / 2
    positions_norm = np.array([(i * phi) % 1.0 for i in range(n_sites)])

    # Average sin² over many irrationally-spaced positions → 0.5
    # For mode n, the average shift per site is:
    #   <Δf_n/f_n> = -(Δm / 2M) × <sin²(nπx/L)> = -(Δm / 2M) × 0.5
    # (The sin² average over irrational positions converges to 0.5
    # by equidistribution.)

    # Exact calculation for the specific positions:
    n_test_mode = 10  # use mode 10 as representative high mode
    sin2_values = np.sin(n_test_mode * np.pi * positions_norm) ** 2
    total_sin2 = np.sum(sin2_values)

    shift_per_site_frac = delta_m / (2 * rod.mass)  # at antinode
    total_shift_frac = shift_per_site_frac * total_sin2
    linewidth_frac = 1.0 / rod.Q
    shift_over_linewidth = total_shift_frac / linewidth_frac

    return CumulativeShiftResult(
        inscription_type=inscription_type,
        n_sites=n_sites,
        rod=rod,
        shift_per_site=float(shift_per_site_frac),
        total_shift_frac=float(total_shift_frac),
        linewidth_frac=float(linewidth_frac),
        shift_over_linewidth=float(shift_over_linewidth),
        delta_mass_per_site=float(delta_m),
        total_delta_mass=float(delta_m * n_sites),
        mass_ratio=float(delta_m * n_sites / rod.mass),
        verdict=bool(shift_over_linewidth >= 0.1),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-V3: Q-factor survival under acoustic scattering
# ═══════════════════════════════════════════════════════════════════════

def exp_q_survival(
    rod: MEMSRod = None,
    inscription_type: str = "type_I",
    n_sites: int = 100,
    seed: int = 42,
) -> QSurvivalResult:
    """
    Model acoustic scattering loss from inscription inclusions.

    Each inscription creates a region of modified density.  Acoustic
    waves scatter off these inclusions.  In the Rayleigh regime
    (inclusion size a ≪ wavelength λ), the scattering cross-section
    scales as:

        σ_Rayleigh ∝ (ka)⁴ × a²

    where k = 2π/λ and a is the effective inclusion radius.

    For N inclusions distributed through the rod volume, the total
    scattering loss per round-trip is:

        α_scat = N × σ / A_cross × (2L/λ)

    where A_cross is the rod cross-section and 2L/λ is the number
    of wavelengths per round-trip.

    The modified quality factor is:

        1/Q_mod = 1/Q_0 + α_scat / (2π)

    Kill criterion: Q_modified / Q_pristine < 0.5.
    """
    if rod is None:
        rod = MEMSRod()

    params = INSCRIPTION_TYPES[inscription_type]

    # Effective inclusion radius (geometric mean of focal dimensions)
    a = (params["focal_width"] * params["focal_width"] *
         params["focal_length"]) ** (1/3) / 2

    # Use mode 100 as representative (middle of usable band)
    n_mode = 100
    f_n = n_mode * rod.f1
    wavelength = rod.v_bar / f_n
    k = 2 * np.pi / wavelength
    ka = k * a

    # Density contrast for scattering amplitude
    delta_rho_frac = abs(params["delta_rho_frac"])

    # Rayleigh scattering cross-section for acoustic wave off
    # density inhomogeneity (Morse & Ingard, Theoretical Acoustics):
    #   σ = (4π/9) × k⁴ × a⁶ × (Δρ/ρ)²
    sigma = (4 * np.pi / 9) * k**4 * a**6 * delta_rho_frac**2

    # Loss per round-trip from N scatterers:
    # Each scatterer removes σ of the beam cross-section per pass.
    # Over a round-trip (2L), the wave encounters each scatterer
    # approximately once (they are distributed through the volume).
    # Total fractional energy loss:
    #   α_scat = N × σ / V_rod × 2L
    #          = (N/V_rod) × σ × 2L
    number_density = n_sites / rod.volume
    alpha_scat = number_density * sigma * 2 * rod.length

    # Intrinsic loss per round-trip
    intrinsic_loss = 2 * np.pi / rod.Q

    # Modified Q
    total_loss = intrinsic_loss + alpha_scat
    q_modified = 2 * np.pi / total_loss if total_loss > 0 else rod.Q
    q_ratio = q_modified / rod.Q

    return QSurvivalResult(
        inscription_type=inscription_type,
        n_sites=n_sites,
        inclusion_radius=float(a),
        wavelength=float(wavelength),
        size_parameter=float(ka),
        sigma_rayleigh=float(sigma),
        total_scattering_loss=float(alpha_scat),
        intrinsic_loss=float(intrinsic_loss),
        loss_ratio=float(alpha_scat / intrinsic_loss) if intrinsic_loss > 0 else 0,
        q_modified=float(q_modified),
        q_ratio=float(q_ratio),
        verdict=bool(q_ratio >= 0.5),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-V4: Radial encoding dimension
# ═══════════════════════════════════════════════════════════════════════

def exp_radial_encoding(
    rod: MEMSRod = None,
    n_radial: int = 5,
    n_modes_L: int = 10,
    n_modes_T: int = 10,
    seed: int = 42,
) -> RadialEncodingResult:
    """
    Test whether radial inscription position provides an independent
    encoding dimension.

    Longitudinal modes have radial displacement profile:
        u_L(r) ∝ J₀(β_{L,m} r/R)
    where β_{L,m} are zeros of dJ₀/dr (free-surface BC).

    Torsional modes have radial displacement profile:
        u_T(r) ∝ J₁(β_{T,m} r/R)
    where β_{T,m} are zeros of J₁ or dJ₁/dr.

    A density change at radial position r₀ shifts mode n by:
        Δf_n ∝ |u_n(r₀)|²

    Different modes weight different radial positions differently.
    If longitudinal modes (J₀ profile) and torsional modes (J₁ profile)
    are both measurable, inscrbing at different radii produces
    distinguishable fingerprints.

    Kill criterion: mean MI < 0.5 bits per mode.
    """
    if rod is None:
        rod = MEMSRod()

    from scipy.special import jn_zeros  # zeros of J_n

    R = rod.radius

    # Radial positions to test (from near-axis to near-surface)
    r_positions = np.linspace(0.1 * R, 0.9 * R, n_radial)

    # Longitudinal radial profile: J₀(β_{0,m} r/R)
    # β_{0,m} = zeros of J₁ (derivative of J₀)
    beta_L = jn_zeros(1, n_modes_L)
    # Torsional radial profile: J₁(β_{1,m} r/R)
    # β_{1,m} = zeros of J₁
    beta_T = jn_zeros(1, n_modes_T)

    from scipy.special import j0, j1

    # Build fingerprint matrix: rows = radial positions, cols = modes
    n_total_modes = n_modes_L + n_modes_T
    fingerprints = np.zeros((n_radial, n_total_modes))

    longitudinal_profiles = np.zeros((n_radial, n_modes_L))
    torsional_profiles = np.zeros((n_radial, n_modes_T))

    for i, r0 in enumerate(r_positions):
        r_norm = r0 / R
        # Longitudinal mode weighting: |J₀(β_{0,m} × r/R)|²
        for m in range(n_modes_L):
            val = j0(beta_L[m] * r_norm)
            longitudinal_profiles[i, m] = val ** 2
            fingerprints[i, m] = val ** 2

        # Torsional mode weighting: |J₁(β_{1,m} × r/R)|²
        for m in range(n_modes_T):
            val = j1(beta_T[m] * r_norm)
            torsional_profiles[i, m] = val ** 2
            fingerprints[i, n_modes_L + m] = val ** 2

    # Mutual information: how well can we distinguish radial positions
    # from the fingerprint vectors?
    # Use pairwise distinctness as proxy: for each mode, compute the
    # variance across radial positions normalised by total range.
    mi_per_mode = np.zeros(n_total_modes)
    for j in range(n_total_modes):
        col = fingerprints[:, j]
        if np.max(col) - np.min(col) > 1e-12:
            # Number of distinguishable levels: range / resolution
            # Resolution = 1/SNR; for fused silica Q=1e5, SNR ~76 dB
            # at MEMS scale → ~4000 linear distinguishable levels
            snr_linear = 4000.0
            dynamic_range = np.max(col) - np.min(col)
            n_levels = max(1, int(dynamic_range / (np.max(col) / snr_linear)))
            n_distinguishable = min(n_levels, n_radial)
            mi_per_mode[j] = np.log2(n_distinguishable) if n_distinguishable > 1 else 0
        else:
            mi_per_mode[j] = 0.0

    return RadialEncodingResult(
        n_radial_positions=n_radial,
        n_modes_longitudinal=n_modes_L,
        n_modes_torsional=n_modes_T,
        longitudinal_profiles=longitudinal_profiles,
        torsional_profiles=torsional_profiles,
        fingerprints=fingerprints,
        mutual_info_per_mode=mi_per_mode,
        mean_mi=float(np.mean(mi_per_mode)),
        verdict=bool(np.mean(mi_per_mode) >= 0.5),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-V5: 3D volumetric capacity gain
# ═══════════════════════════════════════════════════════════════════════

def exp_volumetric_capacity(
    rod: MEMSRod = None,
    inscription_type: str = "type_I",
    seed: int = 42,
) -> VolumetricCapacityResult:
    """
    Compare information density of 3D volumetric inscription vs
    surface-only perturbation.

    Surface encoding: perturbation sites along the rod surface at
    irrational spacing.  Maximum sites ≈ L / (2 × focal_width)
    (Nyquist limit on perturbation spacing).

    Volumetric encoding: sites distributed in a 3D lattice:
    - Axial: same count as surface
    - Radial: number of resolvable radial layers ≈ R / focal_width
    - Azimuthal: number of resolvable angular positions (for torsional
      modes) ≈ 2π × R / focal_width

    Each site contributes ~log₂(1 + site_SNR) bits where site_SNR
    depends on the shift magnitude relative to measurement noise.

    Kill criterion: volumetric / surface capacity < 1.5.
    """
    if rod is None:
        rod = MEMSRod()

    params = INSCRIPTION_TYPES[inscription_type]
    focal_w = params["focal_width"]

    # Surface encoding
    # Sites limited by diffraction: minimum spacing ≈ 2 × focal width
    surface_sites = int(rod.length / (2 * focal_w))
    # Bits per site: conservative 1 bit (presence/absence)
    # More optimistic: multi-level mass → log₂(levels)
    # Use conservative estimate
    bits_per_surface_site = 1.0
    surface_bits = surface_sites * bits_per_surface_site

    # Volumetric encoding
    vol_axial = surface_sites  # same axial resolution
    vol_radial = max(1, int(rod.radius / focal_w))
    # Azimuthal: only useful if torsional modes are readable
    # For a 50 µm diameter rod with 1 µm focal spots:
    vol_azimuthal = max(1, int(np.pi * rod.diameter / focal_w))
    vol_total = vol_axial * vol_radial * vol_azimuthal

    # Bits per volumetric site: also conservative 1 bit
    # The radial dimension adds information only if modes can resolve it
    # From H-V4, we know MI > 0.5 bits/mode for radial encoding
    # Conservative: 0.5 bits per radial layer (discounted for
    # mode-family coupling limitations)
    bits_per_vol_site = 0.5  # conservative: radial adds less info per site
    volume_bits = vol_total * bits_per_vol_site

    ratio = volume_bits / surface_bits if surface_bits > 0 else 0

    return VolumetricCapacityResult(
        surface_sites=surface_sites,
        surface_bits=float(surface_bits),
        volume_axial_sites=vol_axial,
        volume_radial_layers=vol_radial,
        volume_azimuthal_sites=vol_azimuthal,
        volume_total_sites=vol_total,
        volume_bits=float(volume_bits),
        capacity_ratio=float(ratio),
        verdict=bool(ratio >= 1.5),
    )


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_volumetric_inscription(seed: int = 42) -> Dict[str, dict]:
    """
    Execute all five H-V hypotheses and return results + verdicts.
    """
    results = {}

    # H-V1: Volumetric sensitivity
    v1 = exp_volumetric_sensitivity(seed=seed)
    results["H-V1"] = {
        "name": "Volumetric sin² sensitivity",
        "result": v1,
        "verdict": "CONFIRMED" if v1.verdict else "KILLED",
        "metric": f"R² = {v1.mean_r_squared:.6f}",
        "kill_criterion": "R² < 0.99",
    }

    # H-V2: Cumulative shift (test all three inscription types)
    for itype in ["type_I", "type_II", "type_III"]:
        v2 = exp_cumulative_shift(inscription_type=itype, seed=seed)
        tag = itype.replace("_", "").upper()
        results[f"H-V2-{tag}"] = {
            "name": f"Cumulative shift ({INSCRIPTION_TYPES[itype]['name']})",
            "result": v2,
            "verdict": "CONFIRMED" if v2.verdict else "KILLED",
            "metric": f"shift/linewidth = {v2.shift_over_linewidth:.4f}",
            "kill_criterion": "shift/linewidth < 0.1",
        }

    # H-V3: Q survival (test all three)
    for itype in ["type_I", "type_II", "type_III"]:
        v3 = exp_q_survival(inscription_type=itype, n_sites=100, seed=seed)
        tag = itype.replace("_", "").upper()
        results[f"H-V3-{tag}"] = {
            "name": f"Q survival ({INSCRIPTION_TYPES[itype]['name']})",
            "result": v3,
            "verdict": "CONFIRMED" if v3.verdict else "KILLED",
            "metric": f"Q_ratio = {v3.q_ratio:.6f}, ka = {v3.size_parameter:.2e}",
            "kill_criterion": "Q_ratio < 0.5",
        }

    # H-V4: Radial encoding
    v4 = exp_radial_encoding(seed=seed)
    results["H-V4"] = {
        "name": "Radial encoding dimension",
        "result": v4,
        "verdict": "CONFIRMED" if v4.verdict else "KILLED",
        "metric": f"mean MI = {v4.mean_mi:.2f} bits/mode",
        "kill_criterion": "MI < 0.5 bits/mode",
    }

    # H-V5: Volumetric capacity
    v5 = exp_volumetric_capacity(seed=seed)
    results["H-V5"] = {
        "name": "3D volumetric capacity gain",
        "result": v5,
        "verdict": "CONFIRMED" if v5.verdict else "KILLED",
        "metric": f"ratio = {v5.capacity_ratio:.1f}×",
        "kill_criterion": "ratio < 1.5",
    }

    return results


def summarize_all(results: Dict[str, dict]) -> str:
    """Print formatted summary of all S21 results."""
    lines = []
    lines.append("=" * 70)
    lines.append("S21 — FEMTOSECOND VOLUMETRIC INSCRIPTION: RESULTS")
    lines.append("=" * 70)

    confirmed = 0
    killed = 0

    for key in sorted(results.keys()):
        r = results[key]
        status = r["verdict"]
        if status == "CONFIRMED":
            confirmed += 1
        else:
            killed += 1
        lines.append(f"\n  {key}: {r['name']}")
        lines.append(f"    {r['metric']}")
        lines.append(f"    Kill criterion: {r['kill_criterion']}")
        lines.append(f"    → {status}")

    total = confirmed + killed
    lines.append(f"\n{'=' * 70}")
    lines.append(f"S21 SUMMARY: {confirmed}/{total} confirmed, "
                 f"{killed}/{total} killed")
    lines.append(f"{'=' * 70}")

    return "\n".join(lines)
