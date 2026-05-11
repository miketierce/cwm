"""
MEMS Q-factor prediction for glass acoustic resonators.

Models all dominant loss mechanisms for a clamped glass rod resonator
at MEMS scale and predicts the achievable quality factor as a function
of geometry, material, clamping design, and operating conditions.

Loss mechanisms modeled:
    1. Material (intrinsic) loss — bulk viscous/structural damping
    2. Anchor loss — energy leakage through mechanical supports
    3. Thermoelastic damping (TED) — Zener/Lifshitz-Roukes model
    4. Surface loss — defect layer on free surfaces
    5. Gas damping — squeeze-film and molecular regime
    6. Rayleigh scattering — bulk acoustic ν⁴ attenuation (Festi 2026)

Total Q:
    1/Q_total = 1/Q_material + 1/Q_anchor + 1/Q_TED + 1/Q_surface + 1/Q_gas + 1/Q_rayleigh

References:
    - Hao, Erbil, Ayazi (2003): anchor loss in MEMS beam resonators
    - Judge, Photiadis, Hao (2007): anchor loss in flexural-mode MEMS
    - Lifshitz, Roukes (2000): thermoelastic damping in beams
    - Yasumura et al. (2000): surface losses in MEMS oscillators
    - Bao, Yang (2007): squeeze-film damping in MEMS
    - Nguyen (2007): MEMS resonator Q survey (IEEE TUFFC)
    - Candler et al. (2006): wafer-level packaging for high-Q MEMS
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .common import K_B
from .glass_resonator import GlassProperties, RodGeometry, glass_database


# ──────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class AnchorDesign:
    """
    Mechanical support / clamping geometry for a MEMS resonator.

    The rod is supported at one or both ends by thin tethers that
    connect it to the substrate. Anchor loss depends on the ratio
    of tether cross-section to rod cross-section, the attachment
    position, and the acoustic impedance mismatch.
    """
    n_anchors: int = 2                  # number of support points (1 or 2)
    tether_width: float = 5e-6          # tether width [m]
    tether_thickness: float = 5e-6      # tether height/thickness [m]
    tether_length: float = 50e-6        # tether length (rod to substrate) [m]
    attachment_position: str = "ends"   # "ends", "nodal", "quarter"
    substrate_material: str = "silicon" # substrate for impedance mismatch
    isolation_trenches: bool = False    # acoustic isolation trenches around anchors

    @property
    def tether_cross_section(self) -> float:
        """Cross-sectional area of one tether [m²]."""
        return self.tether_width * self.tether_thickness


@dataclass
class OperatingConditions:
    """Environmental and operating parameters."""
    temperature: float = 300.0          # temperature [K]
    pressure: float = 1.0               # gas pressure [Pa] (1 Pa ~ 0.01 mbar)
    gas_type: str = "air"               # "air", "nitrogen", "vacuum"
    drive_amplitude: float = 1e-9       # drive amplitude [m]
    delta_T: float = 1.0               # thermal stability window [K]


@dataclass
class SurfaceProperties:
    """Surface loss parameters."""
    roughness_rms: float = 1e-9         # RMS surface roughness [m]
    defect_layer_thickness: float = 5e-9  # damaged/defect surface layer [m]
    defect_layer_Q: float = 100.0       # Q factor of the defect layer


@dataclass
class QComponentResult:
    """Result from a single loss mechanism calculation."""
    name: str
    Q_value: float          # Q factor from this mechanism (inf if lossless)
    loss: float             # 1/Q (loss tangent contribution)
    description: str = ""
    is_dominant: bool = False


@dataclass
class QBudgetResult:
    """Complete Q-factor budget for a resonator design."""
    # Design parameters
    rod: RodGeometry
    glass: GlassProperties
    anchor: AnchorDesign
    conditions: OperatingConditions
    mode_number: int

    # Frequency
    frequency: float                    # mode frequency [Hz]

    # Individual Q components
    Q_material: float                   # intrinsic material Q
    Q_anchor: float                     # anchor/clamping loss
    Q_TED: float                        # thermoelastic damping
    Q_surface: float                    # surface loss
    Q_gas: float                        # gas damping

    # Total
    Q_total: float                      # combined Q
    dominant_loss: str                  # name of dominant mechanism
    loss_budget: Dict[str, float]       # {name: fractional contribution}

    # Architecture impact
    n_max_modes: int                    # max thermally stable modes at this Q
    bits_per_mode: float               # information capacity per mode
    total_bits: int                    # total information capacity
    density_gbit_cm3: float            # volumetric density [Gbit/cm³]

    # Component details
    components: List[QComponentResult] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# Substrate properties for impedance mismatch calculation
# ──────────────────────────────────────────────────────────────────────────

SUBSTRATE_PROPERTIES = {
    "silicon": {"density": 2330.0, "v_longitudinal": 8433.0, "name": "Silicon"},
    "glass": {"density": 2230.0, "v_longitudinal": 5500.0, "name": "Glass"},
    "alumina": {"density": 3900.0, "v_longitudinal": 10520.0, "name": "Alumina"},
    "steel": {"density": 7800.0, "v_longitudinal": 5900.0, "name": "Steel"},
}


# ──────────────────────────────────────────────────────────────────────────
# 1. Material (intrinsic) loss
# ──────────────────────────────────────────────────────────────────────────

def compute_Q_material(glass: GlassProperties) -> QComponentResult:
    """
    Intrinsic material Q — the bulk acoustic loss of the glass.

    This is a fundamental material property, measured experimentally
    and stored in the glass database. It represents viscous losses
    in the glass network (bond angle rearrangements, alkali ion hopping).

    For longitudinal modes at room temperature:
        - Soda-lime:     Q ~ 3,000
        - Borosilicate:  Q ~ 10,000
        - Fused silica:  Q ~ 100,000

    The intrinsic Q is frequency-independent in the 10 kHz - 100 MHz range
    relevant to MEMS (Bhatia 1967, Chapter 4).
    """
    return QComponentResult(
        name="Material (intrinsic)",
        Q_value=glass.Q_acoustic,
        loss=1.0 / glass.Q_acoustic,
        description=(
            f"{glass.name}: bulk Q = {glass.Q_acoustic:,.0f} "
            f"(viscous/structural loss in glass network)"
        ),
    )


# ──────────────────────────────────────────────────────────────────────────
# 2. Anchor loss
# ──────────────────────────────────────────────────────────────────────────

def compute_Q_anchor(
    rod: RodGeometry,
    glass: GlassProperties,
    anchor: AnchorDesign,
    mode_number: int = 1,
) -> QComponentResult:
    """
    Anchor loss for a clamped MEMS resonator.

    Energy leaks from the resonator into the substrate through the
    mechanical supports (anchors/tethers). This is typically the
    dominant loss mechanism in MEMS resonators.

    Model: Power balance approach following Hao, Erbil, Ayazi (2003)
    and Park & Park (2004) for extensional (longitudinal) bar modes.

    For a free-free longitudinal rod, mode n has displacement
    u(x) = A·cos(nπx/L). At the ends, |u| = A for all n.
    The velocity at the attachment point: v_end = ω_n × A.
    The stored energy: E = ½ × m_eff × ω_n² × A².

    The tether is much thinner than the acoustic wavelength
    (w_tether << λ = v/f), so it operates below waveguide cutoff.
    Power radiated into the substrate through one tether:

        P_rad = ½ × Z_sub × A_tether × v_end² × T(ω)

    where T(ω) is the power transmission coefficient of the
    sub-wavelength tether, approximately (Photiadis & Judge 2004):

        T ≈ (w_eff / λ)^2 = (w_eff × f / v_sub)^2

    This gives Q_anchor = ω × E / (n_a × P_rad), yielding:

        Q_anchor ≈ (π/2) × (Z_rod / Z_sub) × (L / w_eff)^2 / n_anchors

    where w_eff = √A_tether is the effective tether width.

    Mode dependence: For longitudinal modes, E ∝ ω² and P ∝ ω²,
    so Q_anchor ∝ ω ∝ n. Higher modes lose proportionally less
    energy per cycle because the stored energy grows faster than
    the radiation (both scale as ω², but Q = ωE/P ∝ ω).

    Tether length effect: Longer tethers provide additional
    acoustic isolation through evanescent decay:

        isolation ∝ exp(+κ × L_tether)  where κ ~ π/w_eff

    In practice, tethers longer than ~5× their width provide
    meaningful additional isolation, modeled as (1 + L_t/w_eff).

    Typical values (1 mm borosilicate rod, 5 µm tethers):
        Q_anchor ≈ 5,000-15,000 (end-mounted, vacuum)
        Q_anchor ≈ 50,000+ (with isolation trenches)

    Parameters
    ----------
    rod : RodGeometry
    glass : GlassProperties
    anchor : AnchorDesign
    mode_number : int
        The mode number being analyzed (affects anchor coupling)

    Returns
    -------
    QComponentResult
    """
    # Acoustic impedances [Pa·s/m]
    # Rod: 1D waveguide → use thin-bar speed v_bar = √(E/ρ)
    # Substrate: 3D bulk medium → use bulk v_longitudinal
    # (FEM-validated: see fem_validation.py §2)
    Z_rod = glass.density * glass.v_bar
    Z_sub_props = SUBSTRATE_PROPERTIES.get(anchor.substrate_material,
                                           SUBSTRATE_PROPERTIES["silicon"])
    Z_sub = Z_sub_props["density"] * Z_sub_props["v_longitudinal"]

    # Effective tether width [m]
    w_eff = np.sqrt(anchor.tether_cross_section)

    # Core formula: Q_anchor ∝ (Z_rod/Z_sub) × (L/w_eff)²
    # The prefactor π/2 comes from the power balance derivation
    impedance_ratio = Z_rod / Z_sub
    geometry_ratio = (rod.length / w_eff) ** 2

    Q_base = (np.pi / 2) * impedance_ratio * geometry_ratio

    # Number of anchors (each radiates independently)
    Q_base /= anchor.n_anchors

    # Tether length isolation: longer tether = more evanescent decay
    # Minimal effect for L_t ~ w_eff; grows linearly for L_t >> w_eff
    tether_isolation = 1.0 + anchor.tether_length / w_eff
    Q_base *= tether_isolation

    # Mode dependence for end-mounted longitudinal modes:
    # Q_anchor ∝ n (higher modes → more stored energy per cycle)
    # For nodal mounting, displacement at attachment varies with mode
    if anchor.attachment_position == "ends":
        # End-mounted: displacement always maximal, but Q ∝ n
        # (stored energy grows as n², radiated power grows as n¹, Q ∝ n)
        mode_factor = float(mode_number)
    elif anchor.attachment_position == "nodal":
        # Nodal mounting at midpoint (x = L/2):
        # Displacement: u(L/2) = A·cos(nπ/2)
        # Even n: cos(nπ/2) = ±1 or 0 depending on n mod 4
        # Mode 1: cos(π/2) = 0 → infinite Q (node!)
        # Mode 2: cos(π) = -1 → full coupling
        # Mode 3: cos(3π/2) = 0 → node again
        # Net: Q ∝ mode_number / sin²(nπ × x_attach / L)
        sin2 = np.sin(mode_number * np.pi * 0.5) ** 2
        sin2 = max(sin2, 1e-6)  # cap to avoid division by zero
        mode_factor = float(mode_number) / sin2
    elif anchor.attachment_position == "quarter":
        # Quarter-point mounting (x = L/4): optimal for mode 2
        sin2 = np.sin(mode_number * np.pi * 0.25) ** 2
        sin2 = max(sin2, 1e-6)
        mode_factor = float(mode_number) / sin2
    else:
        mode_factor = float(mode_number)

    Q_base *= mode_factor

    # Acoustic isolation trenches: reduce coupling by ~10×
    # (breaks acoustic path between tether base and substrate bulk)
    if anchor.isolation_trenches:
        Q_base *= 10.0

    Q_anchor = Q_base

    w_um = w_eff * 1e6
    desc = (
        f"Anchor loss: Z_rod/Z_sub={impedance_ratio:.2f}, "
        f"L/w_eff={rod.length/w_eff:.0f}, "
        f"w_eff={w_um:.1f} µm, "
        f"mode={mode_number}, "
        f"attachment={anchor.attachment_position}"
    )

    return QComponentResult(
        name="Anchor loss",
        Q_value=Q_anchor,
        loss=1.0 / Q_anchor,
        description=desc,
    )


# ──────────────────────────────────────────────────────────────────────────
# 3. Thermoelastic damping (TED) — Lifshitz-Roukes / Zener model
# ──────────────────────────────────────────────────────────────────────────

# Thermal properties needed for TED (not in GlassProperties)
THERMAL_CONDUCTIVITY = {
    "soda_lime": 1.0,        # W/(m·K)
    "borosilicate": 1.14,    # W/(m·K) — Pyrex
    "fused_silica": 1.38,    # W/(m·K)
    "lead_glass": 0.8,       # W/(m·K)
}

SPECIFIC_HEAT = {
    "soda_lime": 840.0,      # J/(kg·K)
    "borosilicate": 830.0,   # J/(kg·K) — Pyrex
    "fused_silica": 740.0,   # J/(kg·K)
    "lead_glass": 500.0,     # J/(kg·K)
}


def compute_Q_TED(
    rod: RodGeometry,
    glass: GlassProperties,
    frequency: float,
    conditions: OperatingConditions = None,
) -> QComponentResult:
    """
    Thermoelastic damping (TED) for a vibrating rod.

    When a rod vibrates, regions of compression heat up and regions of
    tension cool down. Irreversible heat flow between these regions
    dissipates energy — this is thermoelastic damping.

    Model: Zener (1938) / Lifshitz & Roukes (2000)

    For a rod of diameter d vibrating at frequency f:

        Q_TED⁻¹ = (E × α² × T) / (ρ × C_p) × (ω × τ) / (1 + (ω × τ)²)

    where:
        τ = d² / (π² × κ/ρC_p) = thermal relaxation time across diameter
        κ = thermal conductivity [W/(m·K)]
        C_p = specific heat [J/(kg·K)]
        α = thermal expansion coefficient [1/K]
        E = Young's modulus [Pa]
        T = temperature [K]

    The loss peaks when ωτ = 1 (Debye peak) and decreases on both sides.
    At very high frequencies (ωτ >> 1), TED becomes negligible — this is
    the adiabatic regime, where heat doesn't have time to flow.

    For MEMS glass resonators:
        - d = 10-100 µm → τ ~ 10⁻⁶ to 10⁻⁴ s
        - f = 1-30 MHz → ω ~ 10⁷ rad/s
        - ωτ >> 1 for most cases → TED is NOT dominant

    This is a key advantage of glass over silicon for MEMS resonators:
    glass has much lower α (especially fused silica, α = 0.55e-6/K),
    giving 100-1000× lower TED than silicon (α = 2.6e-6/K).
    """
    if conditions is None:
        conditions = OperatingConditions()

    T = conditions.temperature
    d = rod.diameter
    omega = 2 * np.pi * frequency

    # Get thermal properties
    glass_key = rod.glass_type
    kappa = THERMAL_CONDUCTIVITY.get(glass_key, 1.0)   # W/(m·K)
    C_p = SPECIFIC_HEAT.get(glass_key, 800.0)           # J/(kg·K)

    # Thermal diffusivity
    D_th = kappa / (glass.density * C_p)                 # m²/s

    # Thermal relaxation time (across rod diameter)
    tau = d**2 / (np.pi**2 * D_th)                       # s

    # Thermoelastic loss (Zener formula)
    delta_TED = (
        (glass.youngs_modulus * glass.alpha_thermal**2 * T)
        / (glass.density * C_p)
    )
    # Debye relaxation
    omega_tau = omega * tau
    loss_TED = delta_TED * omega_tau / (1 + omega_tau**2)

    Q_TED = 1.0 / loss_TED if loss_TED > 0 else np.inf

    desc = (
        f"TED: τ={tau:.2e} s, ωτ={omega_tau:.2f}, "
        f"Δ_TED={delta_TED:.2e}, "
        f"regime={'adiabatic (ωτ>>1)' if omega_tau > 10 else 'isothermal (ωτ<<1)' if omega_tau < 0.1 else 'Debye peak'}"
    )

    return QComponentResult(
        name="Thermoelastic (TED)",
        Q_value=Q_TED,
        loss=loss_TED,
        description=desc,
    )


# ──────────────────────────────────────────────────────────────────────────
# 4. Surface loss
# ──────────────────────────────────────────────────────────────────────────

def compute_Q_surface(
    rod: RodGeometry,
    surface: SurfaceProperties = None,
) -> QComponentResult:
    """
    Surface loss from the damaged/defect surface layer.

    The free surfaces of a MEMS resonator have a thin damaged layer
    (from etching, polishing, or native oxide) with much higher loss
    than the bulk material. The surface loss contribution scales with
    the surface-to-volume ratio.

    Model: Yasumura et al. (2000)

        Q_surface⁻¹ = (1/Q_defect) × (V_surface / V_total)
                     = (1/Q_defect) × (t_defect × S) / V

    where:
        t_defect = thickness of defect surface layer [m]
        Q_defect = Q factor of defect layer (~100 for amorphous layer)
        S = total surface area [m²]
        V = total volume [m³]

    For a cylinder:
        S/V = 2/r + 2/L ≈ 2/r (for long rods)

    At 40 µm diameter: S/V ~ 10⁵ /m → surface loss becomes measurable
    but not dominant for nanometer-thick defect layers.
    """
    if surface is None:
        surface = SurfaceProperties()

    r = rod.diameter / 2
    L = rod.length

    # Surface area of cylinder (ends + lateral)
    S = 2 * np.pi * r**2 + 2 * np.pi * r * L          # m²
    V = np.pi * r**2 * L                                # m³

    # Volume fraction of defect layer
    # Approximate: defect layer coats all surfaces
    V_defect = surface.defect_layer_thickness * S        # m³
    volume_fraction = V_defect / V

    # Surface contribution to loss
    loss_surface = volume_fraction / surface.defect_layer_Q

    Q_surface = 1.0 / loss_surface if loss_surface > 0 else np.inf

    desc = (
        f"Surface: S/V={S/V:.0f} /m, "
        f"V_defect/V={volume_fraction:.2e}, "
        f"t_defect={surface.defect_layer_thickness*1e9:.0f} nm, "
        f"Q_defect={surface.defect_layer_Q:.0f}"
    )

    return QComponentResult(
        name="Surface loss",
        Q_value=Q_surface,
        loss=loss_surface,
        description=desc,
    )


# ──────────────────────────────────────────────────────────────────────────
# 5. Gas damping
# ──────────────────────────────────────────────────────────────────────────

# Gas properties
GAS_PROPERTIES = {
    "air": {"viscosity": 1.81e-5, "molecular_mass": 29e-3, "gamma": 1.4},
    "nitrogen": {"viscosity": 1.76e-5, "molecular_mass": 28e-3, "gamma": 1.4},
    "vacuum": {"viscosity": 0.0, "molecular_mass": 29e-3, "gamma": 1.4},
}


def compute_Q_gas(
    rod: RodGeometry,
    glass: GlassProperties,
    frequency: float,
    conditions: OperatingConditions = None,
) -> QComponentResult:
    """
    Gas damping for a vibrating rod.

    At atmospheric pressure, viscous drag from surrounding gas is the
    dominant loss mechanism for MEMS resonators. At low pressures
    (< 1 mbar), gas damping becomes negligible.

    Two regimes:
    1. Viscous (continuum) regime: Kn << 1
       - Stokes drag on oscillating cylinder
       - Q_gas = (ρ_rod × d² × ω) / (32 × μ)
       - Dominant at atmospheric pressure for d > 10 µm

    2. Molecular (free-molecular) regime: Kn >> 1
       - Individual molecular impacts
       - Q_gas = (ρ_rod × d × ω) / (4 × P × sqrt(8/(π × R × T / M_gas)))
       - Relevant at < 1 mbar

    Knudsen number: Kn = λ / d
    Mean free path: λ = k_B × T / (√2 × π × d_mol² × P)
                      ≈ 66 nm at 1 atm, 6.6 µm at 0.01 atm

    For vacuum-packaged MEMS (P ~ 1 Pa):
        λ ~ 6.6 mm >> d = 40 µm → molecular regime
        Q_gas >> 10⁶ → negligible

    Parameters
    ----------
    rod : RodGeometry
    glass : GlassProperties
    frequency : float [Hz]
    conditions : OperatingConditions

    Returns
    -------
    QComponentResult
    """
    if conditions is None:
        conditions = OperatingConditions()

    d = rod.diameter
    omega = 2 * np.pi * frequency
    P = conditions.pressure
    T = conditions.temperature

    gas = GAS_PROPERTIES.get(conditions.gas_type, GAS_PROPERTIES["air"])
    mu = gas["viscosity"]       # Pa·s
    M_gas = gas["molecular_mass"]  # kg/mol

    if P < 1e-6 or conditions.gas_type == "vacuum":
        # Perfect vacuum
        return QComponentResult(
            name="Gas damping",
            Q_value=np.inf,
            loss=0.0,
            description="Vacuum: no gas damping",
        )

    # Mean free path (using effective molecular diameter ~3.7e-10 m for air)
    d_mol = 3.7e-10  # m
    mean_free_path = K_B * T / (np.sqrt(2) * np.pi * d_mol**2 * P)

    # Knudsen number
    Kn = mean_free_path / d

    if Kn < 0.01:
        # Continuum (viscous) regime — Stokes drag
        Q_gas = (glass.density * d**2 * omega) / (32 * mu)
        regime = "viscous (Kn<<1)"
    elif Kn > 10:
        # Free-molecular regime
        # Mean molecular speed
        R_gas = 8.314  # J/(mol·K)
        v_mean = np.sqrt(8 * R_gas * T / (np.pi * M_gas))
        # Energy loss per cycle from molecular impacts
        Q_gas = (glass.density * d * omega) / (4 * P / v_mean)
        regime = f"molecular (Kn={Kn:.0f})"
    else:
        # Transition regime — interpolate
        # Viscous
        Q_visc = (glass.density * d**2 * omega) / (32 * mu)
        # Molecular
        R_gas = 8.314
        v_mean = np.sqrt(8 * R_gas * T / (np.pi * M_gas))
        Q_mol = (glass.density * d * omega) / (4 * P / v_mean)
        # Weighted interpolation
        w = np.log10(Kn) / np.log10(10 / 0.01)  # 0→1 as Kn: 0.01→10
        Q_gas = Q_visc * (1 - w) + Q_mol * w
        regime = f"transition (Kn={Kn:.1f})"

    loss = 1.0 / Q_gas if Q_gas > 0 else 0.0

    desc = (
        f"Gas: P={P:.1f} Pa, λ={mean_free_path*1e6:.1f} µm, "
        f"Kn={Kn:.2f}, regime={regime}"
    )

    return QComponentResult(
        name="Gas damping",
        Q_value=Q_gas,
        loss=loss,
        description=desc,
    )


# ──────────────────────────────────────────────────────────────────────────
# Rayleigh scattering loss
# ──────────────────────────────────────────────────────────────────────────

def compute_Q_rayleigh(glass: GlassProperties, frequency: float) -> QComponentResult:
    """
    Rayleigh scattering Q limit from bulk acoustic attenuation.

    Sound attenuation in glasses follows Γ ~ A_R · ν⁴ at frequencies
    well below the Ioffe-Regel limit (Rayleigh scattering regime).
    This sets a fundamental physics ceiling on Q at high frequencies.

    Based on Festi et al., PRX 16, 021021 (2026); Baldi et al.,
    PRL 112, 125502 (2014); Wang et al., PRL 134, 196101 (2025).

    At the Ioffe-Regel frequency ν_IR, Γ ≈ ν_IR (modes become
    diffusive). We use this to calibrate A_R = ν_IR / ν_IR⁴ = 1/ν_IR³.

    Parameters
    ----------
    glass : GlassProperties
        Must have nu_ioffe_regel_hz set.
    frequency : float [Hz]

    Returns
    -------
    QComponentResult
    """
    nu_IR = glass.nu_ioffe_regel_hz
    if nu_IR <= 0:
        return QComponentResult(
            name="Rayleigh scattering",
            Q_value=np.inf,
            loss=0.0,
            description="Ioffe-Regel frequency not set; Rayleigh loss not computed",
        )

    # A_R calibrated from Ioffe-Regel crossover: Γ(ν_IR) ≈ ν_IR
    A_R = 1.0 / nu_IR**3
    Gamma = A_R * frequency**4  # Hz (half-width of attenuation)

    if Gamma <= 0:
        Q_ray = np.inf
        loss = 0.0
    else:
        Q_ray = np.pi * frequency / Gamma
        loss = 1.0 / Q_ray

    ratio = frequency / nu_IR

    desc = (
        f"Rayleigh: Γ={Gamma:.2e} Hz, ν/ν_IR={ratio:.2e}, "
        f"{'NEGLIGIBLE' if ratio < 1e-3 else 'RELEVANT' if ratio > 0.01 else 'small'}"
    )

    return QComponentResult(
        name="Rayleigh scattering",
        Q_value=Q_ray,
        loss=loss,
        description=desc,
    )


# ──────────────────────────────────────────────────────────────────────────
# Total Q budget
# ──────────────────────────────────────────────────────────────────────────

def compute_Q_budget(
    rod: RodGeometry = None,
    anchor: AnchorDesign = None,
    conditions: OperatingConditions = None,
    surface: SurfaceProperties = None,
    mode_number: int = 1,
) -> QBudgetResult:
    """
    Compute complete Q-factor budget for a MEMS resonator design.

    Combines all loss mechanisms and predicts the achievable Q,
    identifies the dominant loss, and computes the architecture impact
    (mode count, information capacity, density).

    Parameters
    ----------
    rod : RodGeometry
        Rod dimensions and material.
    anchor : AnchorDesign
        Clamping/support geometry.
    conditions : OperatingConditions
        Temperature, pressure, drive amplitude.
    surface : SurfaceProperties
        Surface defect parameters.
    mode_number : int
        Which mode to analyze (default: fundamental).

    Returns
    -------
    QBudgetResult
    """
    if rod is None:
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
    if anchor is None:
        anchor = AnchorDesign()
    if conditions is None:
        conditions = OperatingConditions()
    if surface is None:
        surface = SurfaceProperties()

    db = glass_database()
    glass = db[rod.glass_type]

    # Mode frequency (FEM-validated thin-bar speed)
    f1 = glass.v_bar / (2 * rod.length)
    freq = mode_number * f1

    # Compute each loss mechanism
    q_mat = compute_Q_material(glass)
    q_anc = compute_Q_anchor(rod, glass, anchor, mode_number)
    q_ted = compute_Q_TED(rod, glass, freq, conditions)
    q_sur = compute_Q_surface(rod, surface)
    q_gas = compute_Q_gas(rod, glass, freq, conditions)
    q_ray = compute_Q_rayleigh(glass, freq)

    components = [q_mat, q_anc, q_ted, q_sur, q_gas, q_ray]

    # Total loss
    total_loss = sum(c.loss for c in components)
    Q_total = 1.0 / total_loss if total_loss > 0 else np.inf

    # Loss budget (fractional contribution of each)
    loss_budget = {}
    for c in components:
        frac = c.loss / total_loss if total_loss > 0 else 0.0
        loss_budget[c.name] = frac
        c.is_dominant = False

    # Identify dominant
    dominant = max(components, key=lambda c: c.loss)
    dominant.is_dominant = True

    # Architecture impact
    alpha = glass.alpha_thermal
    dT = conditions.delta_T
    denominator = 2 * alpha * dT + 1.0 / Q_total
    n_max = int(1.0 / denominator) if denominator > 0 else 0

    # SNR and bits per mode (at mode 1 for representative value)
    mass = glass.density * rod.volume
    m_eff = mass / 2
    omega1 = 2 * np.pi * f1
    k_eff = m_eff * omega1**2
    A = conditions.drive_amplitude
    E_s = 0.5 * k_eff * A**2
    T = conditions.temperature
    SNR = E_s / (K_B * T)
    bits_per_mode = 0.5 * np.log2(1 + SNR) if SNR > 0 else 0.0
    total_bits = int(n_max * bits_per_mode)

    # Density
    V_cm3 = rod.volume * 1e6  # m³ → cm³
    density = total_bits / V_cm3 / 1e9 if V_cm3 > 0 else 0.0  # Gbit/cm³

    return QBudgetResult(
        rod=rod,
        glass=glass,
        anchor=anchor,
        conditions=conditions,
        mode_number=mode_number,
        frequency=freq,
        Q_material=q_mat.Q_value,
        Q_anchor=q_anc.Q_value,
        Q_TED=q_ted.Q_value,
        Q_surface=q_sur.Q_value,
        Q_gas=q_gas.Q_value,
        Q_total=Q_total,
        dominant_loss=dominant.name,
        loss_budget=loss_budget,
        n_max_modes=n_max,
        bits_per_mode=bits_per_mode,
        total_bits=total_bits,
        density_gbit_cm3=density,
        components=components,
    )


# ──────────────────────────────────────────────────────────────────────────
# Parametric sweeps
# ──────────────────────────────────────────────────────────────────────────

def sweep_tether_width(
    rod: RodGeometry = None,
    tether_widths: np.ndarray = None,
    tether_length: float = 50e-6,
    conditions: OperatingConditions = None,
) -> List[QBudgetResult]:
    """Sweep tether width to find optimal anchor design."""
    if rod is None:
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
    if tether_widths is None:
        tether_widths = np.logspace(-6.5, np.log10(rod.diameter * 0.5), 20)

    results = []
    for tw in tether_widths:
        anchor = AnchorDesign(tether_width=tw, tether_thickness=tw,
                              tether_length=tether_length)
        result = compute_Q_budget(rod=rod, anchor=anchor, conditions=conditions)
        results.append(result)
    return results


def sweep_pressure(
    rod: RodGeometry = None,
    pressures: np.ndarray = None,
    anchor: AnchorDesign = None,
) -> List[QBudgetResult]:
    """Sweep gas pressure from atmosphere to hard vacuum."""
    if rod is None:
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
    if pressures is None:
        pressures = np.logspace(-2, 5, 30)  # 0.01 Pa to 100 kPa

    results = []
    for P in pressures:
        conditions = OperatingConditions(pressure=P)
        result = compute_Q_budget(rod=rod, anchor=anchor, conditions=conditions)
        results.append(result)
    return results


def sweep_rod_length(
    lengths: np.ndarray = None,
    glass_type: str = "borosilicate",
    aspect_ratio: float = 25.0,
    conditions: OperatingConditions = None,
) -> List[QBudgetResult]:
    """Sweep rod length across MEMS scales."""
    if lengths is None:
        lengths = np.logspace(-4, -2, 30)  # 100 µm to 10 mm

    results = []
    for L in lengths:
        d = L / aspect_ratio
        rod = RodGeometry(length=L, diameter=d, glass_type=glass_type)
        # Scale tether proportionally
        tw = max(d * 0.1, 1e-6)  # tether = 10% of diameter, min 1 µm
        anchor = AnchorDesign(tether_width=tw, tether_thickness=tw,
                              tether_length=5 * tw)
        result = compute_Q_budget(rod=rod, anchor=anchor, conditions=conditions)
        results.append(result)
    return results


def sweep_mode_number(
    rod: RodGeometry = None,
    mode_numbers: np.ndarray = None,
    anchor: AnchorDesign = None,
    conditions: OperatingConditions = None,
) -> List[QBudgetResult]:
    """Sweep across mode numbers to see how Q varies with frequency."""
    if rod is None:
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
    if mode_numbers is None:
        mode_numbers = np.array([1, 10, 100, 500, 1000, 2000, 5000, 9380])

    results = []
    for n in mode_numbers:
        result = compute_Q_budget(rod=rod, anchor=anchor, conditions=conditions,
                                  mode_number=int(n))
        results.append(result)
    return results


def find_Q_threshold_design(
    Q_target: float = 5000.0,
    glass_type: str = "borosilicate",
    rod_length: float = 1e-3,
    aspect_ratio: float = 25.0,
) -> Dict:
    """
    Find the anchor design parameters needed to achieve a target Q.

    Searches over tether width and pressure to identify the design
    space where Q_total >= Q_target.

    Returns a dict with feasibility assessment and required parameters.
    """
    d = rod_length / aspect_ratio
    rod = RodGeometry(length=rod_length, diameter=d, glass_type=glass_type)
    db = glass_database()
    glass = db[glass_type]

    # If material Q is already below target, impossible
    if glass.Q_acoustic < Q_target:
        return {
            "feasible": False,
            "reason": f"Material Q ({glass.Q_acoustic:.0f}) < target ({Q_target:.0f})",
            "Q_material": glass.Q_acoustic,
        }

    # Sweep tether widths at vacuum (P=1 Pa) — find min tether for Q_target
    tether_widths = np.logspace(-6.5, np.log10(d * 0.5), 200)
    vacuum = OperatingConditions(pressure=1.0)

    best_anchor = None
    min_tether = None

    for tw in tether_widths:
        anchor = AnchorDesign(tether_width=tw, tether_thickness=tw,
                              tether_length=max(5*tw, 10e-6))
        budget = compute_Q_budget(rod=rod, anchor=anchor, conditions=vacuum)
        if budget.Q_total >= Q_target:
            if min_tether is None:
                min_tether = tw
                best_anchor = budget

    # Also check with isolation trenches
    best_with_trenches = None
    min_tether_trenches = None
    for tw in tether_widths:
        anchor = AnchorDesign(tether_width=tw, tether_thickness=tw,
                              tether_length=max(5*tw, 10e-6),
                              isolation_trenches=True)
        budget = compute_Q_budget(rod=rod, anchor=anchor, conditions=vacuum)
        if budget.Q_total >= Q_target:
            if min_tether_trenches is None:
                min_tether_trenches = tw
                best_with_trenches = budget

    # Also find max pressure at which Q_target is achievable
    max_pressure = None
    if best_anchor is not None:
        pressures = np.logspace(-1, 5, 200)
        for P in pressures:
            cond = OperatingConditions(pressure=P)
            budget = compute_Q_budget(
                rod=rod,
                anchor=AnchorDesign(tether_width=min_tether,
                                    tether_thickness=min_tether,
                                    tether_length=max(5*min_tether, 10e-6)),
                conditions=cond,
            )
            if budget.Q_total >= Q_target:
                max_pressure = P
            else:
                break

    return {
        "feasible": min_tether is not None,
        "Q_target": Q_target,
        "glass_type": glass_type,
        "rod_length_mm": rod_length * 1e3,
        "rod_diameter_um": d * 1e6,
        "Q_material": glass.Q_acoustic,
        "min_tether_width_um": min_tether * 1e6 if min_tether else None,
        "max_tether_width_um": (d * 0.5) * 1e6 if min_tether else None,
        "best_Q_at_vacuum": best_anchor.Q_total if best_anchor else None,
        "best_Q_budget": best_anchor,
        "with_isolation_trenches": {
            "min_tether_width_um": min_tether_trenches * 1e6 if min_tether_trenches else None,
            "best_Q": best_with_trenches.Q_total if best_with_trenches else None,
        },
        "max_pressure_Pa": max_pressure,
        "vacuum_required": max_pressure is not None and max_pressure < 101325,
    }
