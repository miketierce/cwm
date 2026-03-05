"""
Photothermal Viscosity Gating for Ferrofluid Memory.

Models localized photothermal heating as a viscosity-control mechanism
that directly attacks the dominant noise source in ferrofluid WCFOMA:
Brownian rotational phase diffusion (D_rot ∝ 1/η).

From the original corpus (Scale 1, Ch8 PhotothermalControl):
  - A light-sensitive polymer layer (azobenzene/PMMA) sits atop the
    ferrofluid memory cell.
  - Localized laser heating reduces viscosity in a targeted region,
    allowing nanoparticle realignment (WRITE).
  - When light is removed, the region re-gels, freezing the pattern
    and dramatically increasing effective viscosity (HOLD).
  - Broad illumination can homogenize the fluid for ERASE.

Physics:
  η(T) = η₀ · exp(E_a / (k_B T))      (Arrhenius viscosity)
  D_rot = k_B T / (π η d³)              (rotational diffusion)
  Phase noise PSD ∝ D_rot ∝ T/η(T)      (net effect of heating)
  Photothermal ΔT = α_abs · I · t / (ρ c_p V)  (temperature rise)

The key insight: heating DECREASES viscosity (enables write) but
INCREASES phase diffusion noise. The trick is to heat only during
write, then re-gel to freeze the pattern. The hold-state viscosity
determines retention, not the write-state viscosity.

Materials:
  - Azobenzene/PMMA: trans→cis photoisomerization, UV/vis switchable
  - Gold nanorods in ferrofluid: NIR photothermal conversion
  - Graphene oxide: broadband optical absorber
  - Thermo-reversible gels: agarose, PVA, methylcellulose

Capabilities:
  - Arrhenius viscosity vs temperature model
  - Photothermal temperature rise calculation
  - Write/hold/erase state noise analysis
  - Duty cycle optimization (write time vs hold time)
  - Spatially selective write/erase simulation
  - Comparison vs passive gel immobilization
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from .common import K_B, C_FERROFLUID


# ---------------------------------------------------------------------------
# Material properties
# ---------------------------------------------------------------------------

@dataclass
class PhotothermalMaterial:
    """Properties of a photothermal conversion layer."""
    name: str
    absorption_coefficient: float     # α [m⁻¹] at operating wavelength
    operating_wavelength_nm: float    # laser wavelength [nm]
    efficiency: float                 # optical-to-thermal conversion [0-1]
    damage_threshold_W_cm2: float     # max intensity before damage
    switching_mechanism: str          # e.g., "photothermal", "photoisomerization"
    notes: str = ""


def photothermal_materials() -> Dict[str, PhotothermalMaterial]:
    """Database of photothermal materials."""
    return {
        "gold_nanorods": PhotothermalMaterial(
            name="Gold nanorods in ferrofluid",
            absorption_coefficient=1e5,
            operating_wavelength_nm=808,
            efficiency=0.9,
            damage_threshold_W_cm2=1e4,
            switching_mechanism="photothermal",
            notes="Peak absorption tunable via aspect ratio; biocompatible",
        ),
        "graphene_oxide": PhotothermalMaterial(
            name="Graphene oxide",
            absorption_coefficient=5e4,
            operating_wavelength_nm=532,
            efficiency=0.8,
            damage_threshold_W_cm2=1e5,
            switching_mechanism="photothermal",
            notes="Broadband absorber; cheap; dispersible in ferrofluid",
        ),
        "azobenzene_PMMA": PhotothermalMaterial(
            name="Azobenzene/PMMA polymer",
            absorption_coefficient=2e4,
            operating_wavelength_nm=365,
            efficiency=0.3,
            damage_threshold_W_cm2=1e3,
            switching_mechanism="photoisomerization",
            notes="trans→cis shape change; reversible with visible light",
        ),
    }


@dataclass
class GelProperties:
    """Properties of the viscosity-modulating gel matrix."""
    name: str
    eta_cold: float               # viscosity at hold temperature [Pa·s]
    eta_hot: float                # viscosity at write temperature [Pa·s]
    T_gel: float                  # gelation temperature [K]
    T_sol: float                  # sol (liquid) temperature [K]
    activation_energy_eV: float   # Arrhenius activation energy
    reversible: bool              # can cycle gel↔sol?
    max_cycles: float             # cycling endurance
    notes: str = ""


def gel_database() -> Dict[str, GelProperties]:
    """Database of thermo-reversible gel candidates."""
    return {
        "agarose_2pct": GelProperties(
            name="2% agarose hydrogel",
            eta_cold=100.0,
            eta_hot=0.005,
            T_gel=308.0,    # ~35°C
            T_sol=358.0,    # ~85°C
            activation_energy_eV=0.5,
            reversible=True,
            max_cycles=1e6,
            notes="Food-grade; well-characterized; ~10⁴× viscosity range",
        ),
        "methylcellulose": GelProperties(
            name="Methylcellulose (inverse gel)",
            eta_cold=0.1,
            eta_hot=50.0,
            T_gel=333.0,    # ~60°C
            T_sol=298.0,    # ~25°C
            activation_energy_eV=0.4,
            reversible=True,
            max_cycles=1e5,
            notes="Inverse thermal gelation — gels on HEATING; liquid when cool",
        ),
        "PVA_borax": GelProperties(
            name="PVA/borax hydrogel",
            eta_cold=10.0,
            eta_hot=0.01,
            T_gel=298.0,
            T_sol=343.0,    # ~70°C
            activation_energy_eV=0.45,
            reversible=True,
            max_cycles=1e4,
            notes="Self-healing; tunable cross-link density",
        ),
        "silica_solgel": GelProperties(
            name="Silica sol-gel matrix",
            eta_cold=1e6,
            eta_hot=0.1,
            T_gel=298.0,
            T_sol=973.0,    # irreversible once set
            activation_energy_eV=2.0,
            reversible=False,
            max_cycles=1,
            notes="Permanent immobilization; highest viscosity ratio; one-time write",
        ),
    }


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class ViscosityProfile:
    """Viscosity vs temperature profile."""
    temperatures: np.ndarray      # [K]
    viscosities: np.ndarray       # [Pa·s]
    activation_energy_eV: float
    eta_ref: float                # reference viscosity [Pa·s]
    T_ref: float                  # reference temperature [K]


@dataclass
class PhotothermalState:
    """State of a photothermal-gated memory cell."""
    mode: str                     # "write", "hold", or "erase"
    temperature: float            # [K]
    viscosity: float              # [Pa·s]
    phase_diffusion_rate: float   # D_rot [rad²/s]
    snr_db: float                 # signal-to-noise ratio
    reliable_modes: int           # modes with SNR > 10 dB
    retention_time_s: float       # estimated retention in this state


@dataclass
class DutyCycleResult:
    """Optimization of write/hold duty cycle."""
    write_fractions: np.ndarray       # fraction of time in write state
    effective_snr_db: np.ndarray      # time-averaged SNR
    effective_modes: np.ndarray       # time-averaged reliable modes
    optimal_write_fraction: float     # best duty cycle
    optimal_snr_db: float
    optimal_modes: int
    write_state: PhotothermalState
    hold_state: PhotothermalState


@dataclass
class SpatialGatingResult:
    """Result of spatially-selective photothermal gating."""
    n_cells: int
    cell_positions: np.ndarray        # 1D positions [m]
    beam_center: float                # laser beam center [m]
    beam_width: float                 # 1/e² beam radius [m]
    temperature_profile: np.ndarray   # T(x) [K]
    viscosity_profile: np.ndarray     # η(x) [Pa·s]
    writable_cells: np.ndarray        # boolean mask — cells above T_sol
    frozen_cells: np.ndarray          # boolean mask — cells below T_gel
    selectivity: float                # fraction of cells correctly addressed


# ---------------------------------------------------------------------------
# Core physics
# ---------------------------------------------------------------------------

def arrhenius_viscosity(
    T: float,
    eta_ref: float = 0.01,
    T_ref: float = 300.0,
    E_a_eV: float = 0.5,
) -> float:
    """
    Arrhenius viscosity model.

    η(T) = η_ref · exp[E_a/k_B · (1/T - 1/T_ref)]

    Parameters
    ----------
    T : float
        Temperature [K].
    eta_ref : float
        Viscosity at reference temperature [Pa·s].
    T_ref : float
        Reference temperature [K].
    E_a_eV : float
        Activation energy [eV].

    Returns
    -------
    float
        Viscosity [Pa·s].
    """
    E_a_J = E_a_eV * 1.602e-19
    return eta_ref * np.exp(E_a_J / K_B * (1.0 / T - 1.0 / T_ref))


def compute_viscosity_profile(
    T_range: Tuple[float, float] = (280.0, 400.0),
    n_points: int = 100,
    eta_ref: float = 0.01,
    T_ref: float = 300.0,
    E_a_eV: float = 0.5,
) -> ViscosityProfile:
    """Compute viscosity vs temperature curve."""
    temps = np.linspace(T_range[0], T_range[1], n_points)
    visc = np.array([
        arrhenius_viscosity(T, eta_ref, T_ref, E_a_eV) for T in temps
    ])
    return ViscosityProfile(
        temperatures=temps,
        viscosities=visc,
        activation_energy_eV=E_a_eV,
        eta_ref=eta_ref,
        T_ref=T_ref,
    )


def photothermal_temperature_rise(
    intensity_W_cm2: float,
    absorption_coeff: float,
    efficiency: float,
    exposure_time_s: float,
    volume_m3: float = 1e-15,
    rho: float = 1200.0,          # density [kg/m³]
    c_p: float = 1500.0,          # specific heat [J/(kg·K)]
) -> float:
    """
    Temperature rise from photothermal absorption.

    ΔT = η_abs · α · I · t · A / (ρ · c_p · V)

    Simplified for thin-layer absorption where A ≈ V^(2/3).

    Parameters
    ----------
    intensity_W_cm2 : float
        Laser intensity [W/cm²].
    absorption_coeff : float
        Absorption coefficient [m⁻¹].
    efficiency : float
        Optical-to-thermal efficiency [0-1].
    exposure_time_s : float
        Exposure duration [s].
    volume_m3 : float
        Heated volume [m³].
    rho : float
        Material density [kg/m³].
    c_p : float
        Specific heat capacity [J/(kg·K)].

    Returns
    -------
    float
        Temperature rise ΔT [K].
    """
    I_W_m2 = intensity_W_cm2 * 1e4  # convert to W/m²
    # Absorption path length ~ volume^(1/3)
    path_length = volume_m3**(1/3)
    # Power absorbed
    P_abs = efficiency * I_W_m2 * (volume_m3**(2/3)) * (
        1 - np.exp(-absorption_coeff * path_length)
    )
    # Temperature rise (adiabatic, no heat loss)
    mass = rho * volume_m3
    return P_abs * exposure_time_s / (mass * c_p)


def rotational_diffusion_rate(
    T: float,
    viscosity: float,
    d_particle: float = 10e-9,
) -> float:
    """
    Rotational diffusion coefficient for nanoparticles.

    D_rot = k_B T / (π η d³)

    Returns D_rot [rad²/s].
    """
    return K_B * T / (np.pi * viscosity * d_particle**3)


def phase_noise_psd_from_viscosity(
    T: float,
    viscosity: float,
    d_particle: float = 10e-9,
    V_cavity: float = 1e-15,
    phi: float = 0.05,
) -> float:
    """
    Phase diffusion noise PSD as a function of viscosity and temperature.

    Combines rotational diffusion with coupling to acoustic modes.

    Returns phase noise PSD [rad²/s].
    """
    V_particle = (np.pi / 6) * d_particle**3
    N_particles = phi * V_cavity / V_particle
    D_rot = rotational_diffusion_rate(T, viscosity, d_particle)
    coupling = V_particle / V_cavity
    return coupling**2 * D_rot * N_particles


# ---------------------------------------------------------------------------
# State analysis
# ---------------------------------------------------------------------------

def analyze_state(
    mode: str,
    T: float,
    viscosity: float,
    d_particle: float = 10e-9,
    V_cavity: float = 1e-15,
    n_photons: float = 1e8,
    n_modes: int = 10,
    Q: float = 500.0,
    bandwidth: float = 1e6,
) -> PhotothermalState:
    """
    Analyze noise performance in a given photothermal state.

    Parameters
    ----------
    mode : str
        "write", "hold", or "erase".
    T : float
        Temperature [K].
    viscosity : float
        Effective viscosity [Pa·s].
    Other params match NoiseParams defaults.

    Returns
    -------
    PhotothermalState
    """
    D_rot = rotational_diffusion_rate(T, viscosity, d_particle)
    phase_noise = phase_noise_psd_from_viscosity(
        T, viscosity, d_particle, V_cavity
    )

    # Shot noise
    shot_noise = 1.0 / n_photons if n_photons > 0 else np.inf

    # Thermal noise
    Z_acoustic = 2e6
    thermal_noise = 4 * K_B * T / (Z_acoustic * V_cavity)

    total_noise = phase_noise + shot_noise + thermal_noise

    # SNR per mode (averaged)
    signal_power = 1.0  # normalized
    snr_linear = signal_power / max(total_noise * bandwidth, 1e-30)
    snr_db = 10 * np.log10(max(snr_linear, 1e-30))

    # Reliable modes (SNR > 10 dB, higher modes have more noise)
    reliable = 0
    for m in range(1, n_modes + 1):
        mode_noise = total_noise * m  # noise scales with mode index
        mode_snr = signal_power / max(mode_noise * bandwidth, 1e-30)
        if 10 * np.log10(max(mode_snr, 1e-30)) > 10.0:
            reliable += 1

    # Retention: time for SNR to drop below threshold
    omega = 2 * np.pi * C_FERROFLUID / (2 * 1e-5)  # fundamental
    tau_decay = 2 * Q / omega if omega > 0 else np.inf
    if snr_db > 10.0:
        snr_lin = 10**(snr_db / 10)
        retention = tau_decay * np.log(snr_lin / 10.0)
    else:
        retention = 0.0

    return PhotothermalState(
        mode=mode,
        temperature=T,
        viscosity=viscosity,
        phase_diffusion_rate=D_rot,
        snr_db=snr_db,
        reliable_modes=reliable,
        retention_time_s=retention,
    )


def analyze_write_hold_cycle(
    gel_name: str = "agarose_2pct",
    T_ambient: float = 300.0,
    laser_intensity_W_cm2: float = 100.0,
    exposure_time_s: float = 1e-6,
    photothermal_material: str = "gold_nanorods",
    n_photons: float = 1e8,
) -> Tuple[PhotothermalState, PhotothermalState]:
    """
    Analyze the write state (heated, low viscosity) and hold state
    (ambient, high viscosity) for a photothermal gating cycle.

    Returns
    -------
    (write_state, hold_state)
    """
    gels = gel_database()
    gel = gels[gel_name]
    pt_mats = photothermal_materials()
    pt = pt_mats[photothermal_material]

    # Temperature rise during write
    delta_T = photothermal_temperature_rise(
        laser_intensity_W_cm2,
        pt.absorption_coefficient,
        pt.efficiency,
        exposure_time_s,
    )
    T_write = T_ambient + delta_T

    # Viscosities
    eta_write = arrhenius_viscosity(
        T_write, gel.eta_cold, T_ambient, gel.activation_energy_eV
    )
    eta_hold = gel.eta_cold

    # Analyze both states
    write_state = analyze_state("write", T_write, eta_write, n_photons=n_photons)
    hold_state = analyze_state("hold", T_ambient, eta_hold, n_photons=n_photons)

    return write_state, hold_state


# ---------------------------------------------------------------------------
# Duty cycle optimization
# ---------------------------------------------------------------------------

def optimize_duty_cycle(
    gel_name: str = "agarose_2pct",
    T_ambient: float = 300.0,
    n_photons: float = 1e8,
    n_fractions: int = 20,
) -> DutyCycleResult:
    """
    Find the optimal write/hold duty cycle.

    The effective SNR is the time-weighted average:
      SNR_eff = f_write · SNR_write + (1 - f_write) · SNR_hold

    But for retention, what matters is the HOLD state SNR.
    For write throughput, we need enough time in write state.

    Returns
    -------
    DutyCycleResult
    """
    write_state, hold_state = analyze_write_hold_cycle(
        gel_name=gel_name, T_ambient=T_ambient, n_photons=n_photons
    )

    fractions = np.linspace(0.01, 0.99, n_fractions)
    snrs = np.zeros(n_fractions)
    modes = np.zeros(n_fractions)

    # For storage, the effective noise is dominated by the noisier state
    # weighted by time spent there
    for i, f_w in enumerate(fractions):
        # Time-weighted noise: mostly we care about hold-state noise
        # because that determines retention
        snr_lin_write = 10**(write_state.snr_db / 10) if write_state.snr_db > -30 else 1e-3
        snr_lin_hold = 10**(hold_state.snr_db / 10) if hold_state.snr_db > -30 else 1e-3

        # Effective SNR (harmonic mean weighted by duty cycle)
        snr_eff_lin = 1.0 / (f_w / max(snr_lin_write, 1e-30) +
                              (1 - f_w) / max(snr_lin_hold, 1e-30))
        snrs[i] = 10 * np.log10(max(snr_eff_lin, 1e-30))

        # Effective modes
        modes[i] = f_w * write_state.reliable_modes + \
                   (1 - f_w) * hold_state.reliable_modes

    best_idx = np.argmax(snrs)

    return DutyCycleResult(
        write_fractions=fractions,
        effective_snr_db=snrs,
        effective_modes=modes,
        optimal_write_fraction=float(fractions[best_idx]),
        optimal_snr_db=float(snrs[best_idx]),
        optimal_modes=int(round(modes[best_idx])),
        write_state=write_state,
        hold_state=hold_state,
    )


# ---------------------------------------------------------------------------
# Spatial selectivity
# ---------------------------------------------------------------------------

def simulate_spatial_gating(
    n_cells: int = 10,
    cell_pitch_m: float = 20e-6,
    beam_center_idx: int = 5,
    beam_width_m: float = 10e-6,
    laser_intensity_W_cm2: float = 100.0,
    gel_name: str = "agarose_2pct",
    T_ambient: float = 300.0,
) -> SpatialGatingResult:
    """
    Simulate spatially selective photothermal gating across a 1D cell array.

    A focused laser beam creates a Gaussian temperature profile.
    Cells above the sol temperature become writable; cells below
    the gel temperature remain frozen.

    Parameters
    ----------
    n_cells : int
        Number of cells in the 1D array.
    cell_pitch_m : float
        Center-to-center distance [m].
    beam_center_idx : int
        Index of the target cell.
    beam_width_m : float
        Laser beam 1/e² radius [m].
    laser_intensity_W_cm2 : float
        Peak intensity [W/cm²].
    gel_name : str
        Gel material.
    T_ambient : float
        Ambient temperature [K].

    Returns
    -------
    SpatialGatingResult
    """
    gels = gel_database()
    gel = gels[gel_name]
    pt = photothermal_materials()["gold_nanorods"]

    positions = np.arange(n_cells) * cell_pitch_m
    beam_center = positions[beam_center_idx]

    # Gaussian beam profile
    gaussian = np.exp(-2 * (positions - beam_center)**2 / beam_width_m**2)

    # Temperature rise at each cell
    delta_T_peak = photothermal_temperature_rise(
        laser_intensity_W_cm2,
        pt.absorption_coefficient,
        pt.efficiency,
        exposure_time_s=1e-6,
    )
    delta_T = delta_T_peak * gaussian
    T_profile = T_ambient + delta_T

    # Viscosity at each cell
    eta_profile = np.array([
        arrhenius_viscosity(T, gel.eta_cold, T_ambient, gel.activation_energy_eV)
        for T in T_profile
    ])

    # Classification
    writable = T_profile > gel.T_sol
    frozen = T_profile < gel.T_gel

    # Selectivity: ideally only the target cell is writable
    target_mask = np.zeros(n_cells, dtype=bool)
    target_mask[beam_center_idx] = True

    correct_write = np.sum(writable & target_mask)
    incorrect_write = np.sum(writable & ~target_mask)
    correct_hold = np.sum(frozen & ~target_mask)
    total_correct = correct_write + correct_hold
    selectivity = total_correct / n_cells

    return SpatialGatingResult(
        n_cells=n_cells,
        cell_positions=positions,
        beam_center=beam_center,
        beam_width=beam_width_m,
        temperature_profile=T_profile,
        viscosity_profile=eta_profile,
        writable_cells=writable,
        frozen_cells=frozen,
        selectivity=selectivity,
    )


# ---------------------------------------------------------------------------
# Comparison vs passive gel
# ---------------------------------------------------------------------------

def compare_gating_strategies(
    n_photons: float = 1e8,
) -> Dict[str, PhotothermalState]:
    """
    Compare photothermal gating vs passive gel immobilization.

    Returns dict of strategy_name → PhotothermalState (hold state).
    """
    strategies = {}

    # 1. Baseline (no gel)
    strategies["Baseline (no gel)"] = analyze_state(
        "hold", T=300.0, viscosity=0.01, n_photons=n_photons
    )

    # 2. Passive gel (always gelled)
    strategies["Passive gel (η×1000)"] = analyze_state(
        "hold", T=300.0, viscosity=10.0, n_photons=n_photons
    )

    # 3. Agarose photothermal — hold state
    _, hold = analyze_write_hold_cycle(
        "agarose_2pct", n_photons=n_photons
    )
    strategies["Agarose photothermal (hold)"] = hold

    # 4. Passive silica (permanent)
    strategies["Silica sol-gel (permanent)"] = analyze_state(
        "hold", T=300.0, viscosity=1e6, n_photons=n_photons
    )

    return strategies


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def photothermal_summary() -> str:
    """Generate a text summary of the photothermal gating analysis."""
    write_state, hold_state = analyze_write_hold_cycle()
    duty = optimize_duty_cycle()
    strategies = compare_gating_strategies()
    spatial = simulate_spatial_gating()

    lines = [
        "=" * 65,
        "  PHOTOTHERMAL VISCOSITY GATING ANALYSIS",
        "=" * 65,
        "",
        "  WRITE STATE (heated, low viscosity)",
        f"    Temperature:         {write_state.temperature:.0f} K",
        f"    Viscosity:           {write_state.viscosity:.4f} Pa·s",
        f"    D_rot:               {write_state.phase_diffusion_rate:.2e} rad²/s",
        f"    SNR:                 {write_state.snr_db:.1f} dB",
        f"    Reliable modes:      {write_state.reliable_modes}",
        "",
        "  HOLD STATE (ambient, high viscosity)",
        f"    Temperature:         {hold_state.temperature:.0f} K",
        f"    Viscosity:           {hold_state.viscosity:.1f} Pa·s",
        f"    D_rot:               {hold_state.phase_diffusion_rate:.2e} rad²/s",
        f"    SNR:                 {hold_state.snr_db:.1f} dB",
        f"    Reliable modes:      {hold_state.reliable_modes}",
        f"    Retention:           {hold_state.retention_time_s*1e6:.1f} µs",
        "",
        f"  Viscosity ratio (hold/write):  {hold_state.viscosity/max(write_state.viscosity, 1e-30):.0f}×",
        f"  SNR gain from gating:          {hold_state.snr_db - write_state.snr_db:+.1f} dB",
        "",
        "-" * 65,
        "  DUTY CYCLE OPTIMIZATION",
        f"    Optimal write fraction: {duty.optimal_write_fraction:.0%}",
        f"    Effective SNR:          {duty.optimal_snr_db:.1f} dB",
        f"    Effective modes:        {duty.optimal_modes}",
        "",
        "-" * 65,
        "  SPATIAL SELECTIVITY",
        f"    Array: {spatial.n_cells} cells, pitch {spatial.cell_positions[1]*1e6:.0f} µm",
        f"    Beam width: {spatial.beam_width*1e6:.0f} µm",
        f"    Writable cells: {np.sum(spatial.writable_cells)}",
        f"    Frozen cells: {np.sum(spatial.frozen_cells)}",
        f"    Selectivity: {spatial.selectivity:.0%}",
        "",
        "-" * 65,
        "  STRATEGY COMPARISON (hold-state performance)",
        f"  {'Strategy':<35} {'SNR [dB]':<10} {'Modes':<8} {'η [Pa·s]':<12}",
    ]
    for name, state in strategies.items():
        lines.append(
            f"  {name:<35} {state.snr_db:<10.1f} {state.reliable_modes:<8} "
            f"{state.viscosity:<12.2e}"
        )
    lines.append("=" * 65)
    return "\n".join(lines)
