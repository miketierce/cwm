"""
Ferrofluid Material Model for WCFOMA Simulations

Provides realistic, literature-derived material properties for ferrofluid
media used in resonant cavities.  Bridges Phase 0 (ideal parameters) and
Phase 1 (multiphysics realism).

Key properties modelled:
  - Complex magnetic permeability µ(ω, H, T)
  - Sound velocity  v(T, φ)        — depends on temperature & particle fraction
  - Viscosity  η_visc(T, γ̇, H)     — shear-thinning + magneto-viscous effect
  - Effective damping rate  η_eff   — viscous + thermal + radiative
  - Q factor estimate               — from damping and mode frequency

Literature sources:
  [1] Rosensweig, "Ferrohydrodynamics", Dover 1997
  [2] Odenbach, "Colloidal Magnetic Fluids", Springer 2009
  [3] Pshenichnikov et al., JMMM 145 (1995) 319-326  — sound velocity
  [4] Pop & Odenbach, J. Phys.: Condens. Matter 18 (2006) S2785 — viscosity
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
MU_0 = 4e-7 * np.pi          # Vacuum permeability (H/m)
K_B = 1.380649e-23            # Boltzmann constant (J/K)


# ---------------------------------------------------------------------------
# Ferrofluid specification
# ---------------------------------------------------------------------------
@dataclass
class FerrofluidSpec:
    """Material specification for a commercial-grade ferrofluid."""
    # Particle properties
    d_particle: float = 10e-9           # Mean particle diameter (m)
    phi: float = 0.10                   # Volume fraction (10% typical)
    M_d: float = 4.46e5                 # Domain magnetization of Fe3O4 (A/m)

    # Carrier fluid
    carrier_density: float = 900.0      # Carrier density (kg/m³), hydrocarbon
    carrier_viscosity: float = 0.006    # Carrier viscosity (Pa·s), light oil
    carrier_sound_speed: float = 1300.0 # Speed of sound in carrier (m/s)

    # Thermal
    T: float = 300.0                    # Operating temperature (K)

    # Magnetic
    H_applied: float = 0.0             # Applied field (A/m)
    chi_0: float = 1.5                 # Initial susceptibility (low-field)

    # Derived
    @property
    def V_particle(self) -> float:
        """Single particle volume (m³)."""
        return np.pi / 6.0 * self.d_particle**3

    @property
    def m_particle(self) -> float:
        """Single particle magnetic moment (A·m²)."""
        return self.M_d * self.V_particle

    @property
    def langevin_alpha(self) -> float:
        """Langevin parameter α = µ₀ m H / (k_B T)."""
        if self.H_applied == 0:
            return 0.0
        return MU_0 * self.m_particle * self.H_applied / (K_B * self.T)

    @property
    def density(self) -> float:
        """Effective fluid density (kg/m³)."""
        rho_particle = 5200.0  # Fe3O4 density
        return (1 - self.phi) * self.carrier_density + self.phi * rho_particle


# ---------------------------------------------------------------------------
# Sound velocity model
# ---------------------------------------------------------------------------
def sound_velocity(spec: FerrofluidSpec, T: Optional[float] = None) -> float:
    """
    Effective speed of sound in ferrofluid.

    Uses Wood's equation for a two-phase mixture:
        1/v² = φ/v_p² + (1-φ)/v_c²

    with temperature correction:
        v_c(T) ≈ v_c(300)(1 - α_T·(T - 300))

    Parameters
    ----------
    spec : FerrofluidSpec
    T : float, optional
        Temperature override (K).

    Returns
    -------
    float : Speed of sound (m/s).
    """
    T = T if T is not None else spec.T
    alpha_T = 2.5e-3  # Typical thermal coefficient for hydrocarbon carrier

    v_carrier = spec.carrier_sound_speed * (1.0 - alpha_T * (T - 300.0))
    v_particle = 5900.0  # Speed of sound in magnetite (m/s)

    # Wood's equation
    inv_v2 = spec.phi / v_particle**2 + (1 - spec.phi) / v_carrier**2
    return 1.0 / np.sqrt(inv_v2)


def sound_velocity_sweep(
    spec: FerrofluidSpec,
    T_range: np.ndarray = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Sweep temperature and return (T_array, v_array)."""
    if T_range is None:
        T_range = np.linspace(280, 340, 50)
    v = np.array([sound_velocity(spec, T) for T in T_range])
    return T_range, v


# ---------------------------------------------------------------------------
# Viscosity model
# ---------------------------------------------------------------------------
def effective_viscosity(
    spec: FerrofluidSpec,
    shear_rate: float = 0.0,
    H: Optional[float] = None,
) -> float:
    """
    Effective dynamic viscosity of ferrofluid.

    Combines:
    1. Einstein correction:  η_eff = η₀(1 + 2.5φ + 6.2φ²)
    2. Magneto-viscous effect (Shliomis):
       Δη/η₀ = (3/2)φ · ξ²/(ξ·coth(ξ) - 1) · 1/(1 + (ωτ_B)²)
       where ξ = Langevin parameter, τ_B = Brownian relaxation time.
    3. Shear-thinning (Casson-like, optional).

    Parameters
    ----------
    spec : FerrofluidSpec
    shear_rate : float
        Applied shear rate (1/s).
    H : float, optional
        Applied magnetic field (A/m), overrides spec.

    Returns
    -------
    float : Dynamic viscosity (Pa·s).
    """
    phi = spec.phi
    eta_0 = spec.carrier_viscosity

    # Einstein + Batchelor correction for concentrated suspension
    eta_eff = eta_0 * (1.0 + 2.5 * phi + 6.2 * phi**2)

    # Magneto-viscous effect
    H_eff = H if H is not None else spec.H_applied
    if H_eff > 0:
        xi = MU_0 * spec.m_particle * H_eff / (K_B * spec.T)
        # Brownian relaxation time
        V_hydro = np.pi / 6.0 * (spec.d_particle * 1.2)**3  # hydrodynamic volume
        tau_B = 3.0 * eta_0 * V_hydro / (K_B * spec.T)

        if xi > 0.01:
            langevin_term = xi**2 / (xi / np.tanh(xi) - 1.0)
            # At zero frequency (quasi-static)
            delta_eta = eta_0 * 1.5 * phi * langevin_term
            eta_eff += delta_eta

    # Shear thinning (simplified Casson)
    if shear_rate > 1.0:
        gamma_crit = 100.0  # Characteristic shear rate
        eta_eff *= 1.0 / (1.0 + (shear_rate / gamma_crit)**0.3)

    return eta_eff


# ---------------------------------------------------------------------------
# Damping and Q factor
# ---------------------------------------------------------------------------
def acoustic_damping_rate(
    spec: FerrofluidSpec,
    freq: float = 1e6,
    mode_number: int = 1,
    L: float = 1e-5,
) -> float:
    """
    Effective acoustic damping rate η for a resonant mode.

    η = α_visc · ω² / (2ρv³)  (classical viscous absorption)

    where α_visc includes bulk + shear viscosity contributions.

    Returns
    -------
    float : Damping rate (1/s).
    """
    v = sound_velocity(spec)
    rho = spec.density
    eta_visc = effective_viscosity(spec)

    omega = 2.0 * np.pi * freq
    # Classical absorption coefficient (Nepers/m)
    # α = ω²/(2ρv³) · (4η/3 + η_bulk)
    # η_bulk ≈ η for simple fluids
    eta_bulk = eta_visc  # Approximation
    alpha_abs = omega**2 / (2.0 * rho * v**3) * (4.0 * eta_visc / 3.0 + eta_bulk)

    # Damping rate = α · v  (decay rate in time domain)
    return alpha_abs * v


def estimate_Q(
    spec: FerrofluidSpec,
    freq: float = 1e6,
    mode_number: int = 1,
    L: float = 1e-5,
) -> float:
    """
    Estimate quality factor Q = ω / (2η) for a resonant mode.

    Parameters
    ----------
    spec : FerrofluidSpec
    freq : float
        Mode frequency (Hz).
    mode_number : int
        Mode index.
    L : float
        Cavity length (m).

    Returns
    -------
    float : Quality factor Q.
    """
    eta = acoustic_damping_rate(spec, freq, mode_number, L)
    omega = 2.0 * np.pi * freq
    if eta < 1e-30:
        return np.inf
    return omega / (2.0 * eta)


# ---------------------------------------------------------------------------
# Comprehensive material characterization
# ---------------------------------------------------------------------------
@dataclass
class MaterialCharacterization:
    """Full material characterization for a ferrofluid spec."""
    spec: FerrofluidSpec
    v_sound: float                 # Speed of sound (m/s)
    rho: float                     # Effective density (kg/m³)
    eta_visc: float                # Dynamic viscosity (Pa·s)
    eta_visc_H: float              # Viscosity under field (Pa·s)
    damping_1MHz: float            # Damping rate at 1 MHz (1/s)
    Q_1MHz: float                  # Q at 1 MHz
    Q_10MHz: float                 # Q at 10 MHz
    Q_100MHz: float                # Q at 100 MHz
    v_vs_T: Tuple[np.ndarray, np.ndarray]  # Temperature sweep


def characterize(
    spec: FerrofluidSpec = None,
    H_field: float = 1e4,
) -> MaterialCharacterization:
    """
    Run full material characterization.

    Parameters
    ----------
    spec : FerrofluidSpec, optional
        Ferrofluid to characterize.  Defaults to EFH-1 proxy.
    H_field : float
        Applied magnetic field for viscosity measurement (A/m).

    Returns
    -------
    MaterialCharacterization
    """
    if spec is None:
        spec = FerrofluidSpec()

    v = sound_velocity(spec)
    rho = spec.density
    eta_visc = effective_viscosity(spec, shear_rate=0.0, H=0.0)
    eta_visc_H = effective_viscosity(spec, shear_rate=0.0, H=H_field)

    damping_1M = acoustic_damping_rate(spec, freq=1e6)
    Q_1M = estimate_Q(spec, freq=1e6)
    Q_10M = estimate_Q(spec, freq=10e6)
    Q_100M = estimate_Q(spec, freq=100e6)

    T_range, v_arr = sound_velocity_sweep(spec)

    return MaterialCharacterization(
        spec=spec,
        v_sound=v,
        rho=rho,
        eta_visc=eta_visc,
        eta_visc_H=eta_visc_H,
        damping_1MHz=damping_1M,
        Q_1MHz=Q_1M,
        Q_10MHz=Q_10M,
        Q_100MHz=Q_100M,
        v_vs_T=(T_range, v_arr),
    )


# ---------------------------------------------------------------------------
# Kill-criterion check
# ---------------------------------------------------------------------------
def check_kill_criteria(char: MaterialCharacterization) -> dict:
    """
    Evaluate ferrofluid against Phase 1 kill criteria.

    Returns dict of {criterion: (value, threshold, pass/fail)}.
    """
    results = {}

    # Kill: Q < 100 at operating frequency
    results["Q at 1 MHz"] = (
        char.Q_1MHz, "> 100",
        "PASS" if char.Q_1MHz > 100 else "FAIL"
    )
    results["Q at 10 MHz"] = (
        char.Q_10MHz, "> 100",
        "PASS" if char.Q_10MHz > 100 else "FAIL"
    )

    # Kill: v_sound unrealistic
    results["Sound velocity"] = (
        char.v_sound, "800–2000 m/s",
        "PASS" if 800 < char.v_sound < 2000 else "WARN"
    )

    # Kill: viscosity too high for wave propagation
    results["Viscosity (no field)"] = (
        char.eta_visc, "< 0.1 Pa·s",
        "PASS" if char.eta_visc < 0.1 else "WARN"
    )

    return results
