"""
Ferroelectric Photonic Memory Cell Model.

Models a Mach-Zehnder interferometer (MZI) or ring resonator on a
silicon photonic chip with one arm containing a ferroelectric phase
shifter — the most experimentally grounded WCFOMA variant from the
original corpus (Scale 1, Ch0 Academic Presentation).

Device stack:
  - SiN waveguide (n ≈ 2.0, low loss at 1550 nm)
  - HfₓZr₁₋ₓO₂ (HZO) ferroelectric film (30 nm), CMOS-compatible
  - Electrode pair for polarization switching

Physics:
  Δn ≈ 10⁻³ (HZO, Taki et al. 2024)
  Δφ = 2π L_fe Δn / λ            (phase shift from ferroelectric)
  I_out = I_in cos²(Δφ/2)         (MZI transfer function)

  Three states (trinary):
    P_up:   +Δn → φ₊ → I_up
    P_down: -Δn → φ₋ → I_down
    P_zero: 0   → 0  → I_mid

Key literature:
  - Taki et al. (2024): Non-volatile optical phase shifter, 30 nm HZO on SiN
  - Wen et al. (2025): Integrated optical memristors, PMN-PT
  - Abel et al. (2019): BaTiO₃ on silicon, large Pockels effect
  - Integrated Ce:YIG MO memory: 1 ns write, 143 fJ/bit, 2.4×10⁹ cycles

Capabilities:
  - MZI transfer function and contrast ratio
  - Trinary cell state discrimination
  - Switching energy and speed estimates
  - Array-level interference (crossbar architecture)
  - Hopfield network mapping onto MZI crossbar
  - Technology comparison vs ferrofluid and magnonic variants
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np


# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
C_LIGHT = 3.0e8              # speed of light [m/s]
H_PLANCK = 6.626e-34         # Planck constant [J·s]


# ---------------------------------------------------------------------------
# Material database
# ---------------------------------------------------------------------------

@dataclass
class FerroelectricMaterial:
    """Properties of a ferroelectric material for photonic phase shifting."""
    name: str
    delta_n: float            # refractive index change per polarization state
    n_eff: float              # effective waveguide index
    coercive_voltage: float   # switching voltage [V]
    film_thickness_nm: float  # ferroelectric film thickness [nm]
    switching_time_ns: float  # polarization switching time [ns]
    endurance_cycles: float   # write/erase cycling endurance
    retention_hours: float    # data retention time [hours]
    cmos_compatible: bool     # can be deposited in a CMOS fab?
    loss_dB_per_cm: float     # propagation loss [dB/cm]
    notes: str = ""


def material_database() -> Dict[str, FerroelectricMaterial]:
    """Return database of candidate ferroelectric materials."""
    return {
        "HZO": FerroelectricMaterial(
            name="Hf₀.₅Zr₀.₅O₂ (HZO)",
            delta_n=1e-3,
            n_eff=2.0,
            coercive_voltage=5.0,
            film_thickness_nm=30.0,
            switching_time_ns=100.0,
            endurance_cycles=1e5,
            retention_hours=12.0,
            cmos_compatible=True,
            loss_dB_per_cm=0.5,
            notes="Taki et al. 2024; demonstrated on SiN waveguide",
        ),
        "BaTiO3": FerroelectricMaterial(
            name="BaTiO₃",
            delta_n=5e-3,
            n_eff=2.3,
            coercive_voltage=3.0,
            film_thickness_nm=100.0,
            switching_time_ns=10.0,
            endurance_cycles=1e8,
            retention_hours=1e5,
            cmos_compatible=False,
            loss_dB_per_cm=2.0,
            notes="Abel et al. 2019; strong Pockels effect, epitaxial growth",
        ),
        "LiNbO3": FerroelectricMaterial(
            name="LiNbO₃",
            delta_n=2e-3,
            n_eff=2.2,
            coercive_voltage=20.0,
            film_thickness_nm=500.0,
            switching_time_ns=50.0,
            endurance_cycles=1e12,
            retention_hours=1e6,
            cmos_compatible=False,
            loss_dB_per_cm=0.3,
            notes="Thin-film LN on insulator; mature platform",
        ),
        "PMN-PT": FerroelectricMaterial(
            name="PMN-PT",
            delta_n=3e-3,
            n_eff=2.5,
            coercive_voltage=2.0,
            film_thickness_nm=200.0,
            switching_time_ns=50.0,
            endurance_cycles=1e6,
            retention_hours=100.0,
            cmos_compatible=False,
            loss_dB_per_cm=1.0,
            notes="Wen et al. 2025; transparent ferroelectric crystal",
        ),
    }


# ---------------------------------------------------------------------------
# MZI cell model
# ---------------------------------------------------------------------------

@dataclass
class MZICell:
    """A single Mach-Zehnder interferometer memory cell."""
    material: str = "HZO"
    L_fe: float = 100e-6          # ferroelectric interaction length [m]
    wavelength: float = 1.55e-6   # operating wavelength [m]
    splitting_ratio: float = 0.5  # 50:50 splitter (ideal)
    insertion_loss_dB: float = 1.0  # total insertion loss [dB]


@dataclass
class MZIState:
    """State of an MZI cell."""
    polarization: int             # -1, 0, or +1
    phase_shift: float            # Δφ [rad]
    output_intensity: float       # normalized (0–1)
    contrast_ratio_dB: float      # ratio between max and min states
    switching_energy_nJ: float    # energy to switch this state
    label: str = ""


@dataclass
class MZICellResult:
    """Complete characterization of an MZI cell."""
    material: FerroelectricMaterial
    cell: MZICell
    states: List[MZIState]           # trinary states
    max_contrast_dB: float           # best achievable contrast
    phase_per_state: np.ndarray      # phase shifts for each state
    intensity_per_state: np.ndarray  # output for each state
    # Performance metrics
    bits_per_cell: float             # log2 of distinguishable states
    write_energy_nJ: float           # energy per write
    write_time_ns: float             # time per write
    read_energy_fJ: float            # energy per read (optical)
    static_power_W: float            # power to hold state (should be 0)


@dataclass
class CrossbarResult:
    """Result of a photonic crossbar memory array simulation."""
    N: int                          # array size (N × N)
    weight_matrix: np.ndarray       # programmed weights
    input_phases: np.ndarray        # input phase vector
    output_fields: np.ndarray       # complex output fields
    output_intensities: np.ndarray  # |E|² at outputs
    cross_talk_dB: float            # worst-case cross-talk
    insertion_loss_dB: float        # total path loss
    total_energy_nJ: float          # energy for one MAC operation


# ---------------------------------------------------------------------------
# Core physics functions
# ---------------------------------------------------------------------------

def ferroelectric_phase_shift(
    delta_n: float,
    L_fe: float,
    wavelength: float,
) -> float:
    """
    Phase shift from ferroelectric index change.

    Δφ = 2π · L_fe · Δn / λ

    Parameters
    ----------
    delta_n : float
        Refractive index change.
    L_fe : float
        Interaction length [m].
    wavelength : float
        Operating wavelength [m].

    Returns
    -------
    float
        Phase shift [rad].
    """
    return 2 * np.pi * L_fe * delta_n / wavelength


def mzi_transfer(
    phase_shift: float,
    splitting_ratio: float = 0.5,
    insertion_loss_dB: float = 0.0,
) -> float:
    """
    MZI output intensity (normalized).

    I_out / I_in = η · [r(1-r)(1 + cos Δφ) + (1-2r)²/4 + ...]

    For ideal 50:50: I_out = cos²(Δφ/2) with loss η.

    Parameters
    ----------
    phase_shift : float
        Differential phase shift [rad].
    splitting_ratio : float
        Power splitting ratio (0.5 = ideal).
    insertion_loss_dB : float
        Total insertion loss [dB].

    Returns
    -------
    float
        Normalized output intensity [0, 1].
    """
    eta = 10**(-insertion_loss_dB / 10)
    r = splitting_ratio
    # General MZI: I = eta * [r*(1-r)*(1+cos(dphi)) + offset terms]
    # For r=0.5: I = eta * cos²(dphi/2)
    I_out = eta * (r * (1 - r) * (1 + np.cos(phase_shift)) +
                   0.25 * (1 - 2*r)**2)
    # Normalize so max = eta (for r=0.5)
    return float(np.clip(I_out, 0, 1))


def switching_energy(
    voltage: float,
    capacitance_per_area: float = 30e-6,   # F/m² for 30nm HZO
    area: float = 100e-6 * 1e-6,            # L_fe × waveguide width
) -> float:
    """
    Switching energy for ferroelectric polarization reversal.

    E = C · V²   (capacitive switching)

    Parameters
    ----------
    voltage : float
        Switching voltage [V].
    capacitance_per_area : float
        Capacitance per unit area [F/m²].
    area : float
        Active area [m²].

    Returns
    -------
    float
        Switching energy [J].
    """
    C = capacitance_per_area * area
    return C * voltage**2


# ---------------------------------------------------------------------------
# Cell characterization
# ---------------------------------------------------------------------------

def characterize_mzi_cell(
    material_name: str = "HZO",
    L_fe: float = 100e-6,
    wavelength: float = 1.55e-6,
    insertion_loss_dB: float = 1.0,
) -> MZICellResult:
    """
    Full characterization of a single MZI ferroelectric memory cell.

    Computes all three trinary states and performance metrics.

    Parameters
    ----------
    material_name : str
        Key into material_database().
    L_fe : float
        Ferroelectric interaction length [m].
    wavelength : float
        Operating wavelength [m].
    insertion_loss_dB : float
        Insertion loss [dB].

    Returns
    -------
    MZICellResult
    """
    db = material_database()
    mat = db[material_name]

    cell = MZICell(
        material=material_name,
        L_fe=L_fe,
        wavelength=wavelength,
        insertion_loss_dB=insertion_loss_dB,
    )

    # Phase shifts for three states
    dphi_pos = ferroelectric_phase_shift(mat.delta_n, L_fe, wavelength)
    dphi_neg = ferroelectric_phase_shift(-mat.delta_n, L_fe, wavelength)
    dphi_zero = 0.0

    phase_shifts = np.array([dphi_neg, dphi_zero, dphi_pos])
    intensities = np.array([
        mzi_transfer(dp, insertion_loss_dB=insertion_loss_dB)
        for dp in phase_shifts
    ])

    # Contrast ratio between extreme states
    I_max = max(intensities)
    I_min = min(intensities)
    contrast_dB = 10 * np.log10(I_max / max(I_min, 1e-30))

    # Switching energy
    E_switch = switching_energy(
        mat.coercive_voltage,
        area=L_fe * 1e-6,  # waveguide width ~1 µm
    )
    E_switch_nJ = E_switch * 1e9

    # Read energy (single photon detection at 1550 nm)
    E_photon = H_PLANCK * C_LIGHT / wavelength
    n_photons_read = 1000  # typical for balanced detection
    E_read_fJ = n_photons_read * E_photon * 1e15

    # Build state objects
    states = []
    for pol, dp, I_out, label in [
        (-1, dphi_neg, intensities[0], "P_down"),
        (0, dphi_zero, intensities[1], "P_zero"),
        (+1, dphi_pos, intensities[2], "P_up"),
    ]:
        states.append(MZIState(
            polarization=pol,
            phase_shift=dp,
            output_intensity=I_out,
            contrast_ratio_dB=contrast_dB,
            switching_energy_nJ=E_switch_nJ if pol != 0 else 0.0,
            label=label,
        ))

    # Bits per cell: trinary = log2(3) ≈ 1.58
    bits = np.log2(3) if contrast_dB > 3.0 else (1.0 if contrast_dB > 0.5 else 0.0)

    return MZICellResult(
        material=mat,
        cell=cell,
        states=states,
        max_contrast_dB=contrast_dB,
        phase_per_state=phase_shifts,
        intensity_per_state=intensities,
        bits_per_cell=bits,
        write_energy_nJ=E_switch_nJ,
        write_time_ns=mat.switching_time_ns,
        read_energy_fJ=E_read_fJ,
        static_power_W=0.0,  # Non-volatile → zero static power
    )


# ---------------------------------------------------------------------------
# Length optimization
# ---------------------------------------------------------------------------

def optimize_interaction_length(
    material_name: str = "HZO",
    wavelength: float = 1.55e-6,
    target_phase: float = np.pi,
) -> float:
    """
    Find the interaction length needed for a target phase shift.

    L = λ · Δφ_target / (2π · Δn)

    For a full π shift (binary), or π/2 (for maximum trinary discrimination).

    Returns
    -------
    float
        Required interaction length [m].
    """
    db = material_database()
    mat = db[material_name]
    return target_phase * wavelength / (2 * np.pi * mat.delta_n)


def length_sweep(
    material_name: str = "HZO",
    wavelength: float = 1.55e-6,
    L_values: np.ndarray = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Sweep interaction length and compute contrast and phase shift.

    Returns
    -------
    L_values : ndarray [m]
    phase_shifts : ndarray [rad]
    contrast_dB : ndarray [dB]
    """
    if L_values is None:
        L_values = np.linspace(10e-6, 2000e-6, 100)

    db = material_database()
    mat = db[material_name]

    phases = np.array([
        ferroelectric_phase_shift(mat.delta_n, L, wavelength)
        for L in L_values
    ])

    contrasts = np.zeros(len(L_values))
    for i, L in enumerate(L_values):
        I_pos = mzi_transfer(phases[i])
        I_neg = mzi_transfer(-phases[i])
        I_max = max(I_pos, I_neg)
        I_min = min(I_pos, I_neg)
        contrasts[i] = 10 * np.log10(I_max / max(I_min, 1e-30))

    return L_values, phases, contrasts


# ---------------------------------------------------------------------------
# Photonic crossbar array
# ---------------------------------------------------------------------------

def simulate_crossbar(
    weight_matrix: np.ndarray,
    input_pattern: np.ndarray,
    material_name: str = "HZO",
    wavelength: float = 1.55e-6,
    loss_per_element_dB: float = 0.1,
    noise_variance: float = 0.0,
) -> CrossbarResult:
    """
    Simulate a photonic crossbar memory/compute array.

    Each crossing point is an MZI with a programmable ferroelectric
    phase shifter. The weight matrix W is encoded as phase shifts:
      φᵢⱼ = arccos(wᵢⱼ)  (for |wᵢⱼ| ≤ 1)

    The input vector is encoded as optical phases.
    The output is the complex interference sum at each output port.

    Parameters
    ----------
    weight_matrix : ndarray of shape (N, N)
        Weight values in [-1, 1].
    input_pattern : ndarray of shape (N,)
        Input pattern (binary ±1 or trinary -1/0/+1).
    material_name : str
        Material for phase shifters.
    wavelength : float
        Operating wavelength [m].
    loss_per_element_dB : float
        Insertion loss per MZI element.
    noise_variance : float
        Additive noise variance on output fields.

    Returns
    -------
    CrossbarResult
    """
    N = len(input_pattern)
    assert weight_matrix.shape == (N, N)

    # Input phases: binary/trinary → phase encoding
    phases_in = np.where(input_pattern >= 0.5, 0.0,
                np.where(input_pattern <= -0.5, np.pi, np.pi / 2))
    E_in = np.exp(1j * phases_in)

    # Weight encoding as phase shifts on each MZI
    # w → amplitude transmission: t = |w|, phase = sign(w) * arccos(0)
    # Simplified: treat weight as direct complex transmission
    W_complex = weight_matrix.astype(complex)

    # Path loss (each signal passes through N elements)
    path_loss = 10**(-loss_per_element_dB * N / 10)

    # Matrix multiply
    E_out = path_loss * (W_complex @ E_in)

    # Add noise
    if noise_variance > 0:
        rng = np.random.RandomState(42)
        noise = rng.normal(0, np.sqrt(noise_variance), N) + \
                1j * rng.normal(0, np.sqrt(noise_variance), N)
        E_out += noise

    intensities = np.abs(E_out)**2

    # Cross-talk: ratio of desired to undesired signals
    desired_power = np.max(intensities)
    undesired_power = np.sum(intensities) - desired_power
    cross_talk_dB = 10 * np.log10(
        max(undesired_power, 1e-30) / max(desired_power, 1e-30)
    )

    # Energy: one photon per input waveguide
    E_photon = H_PLANCK * C_LIGHT / wavelength
    total_energy_nJ = N * 1000 * E_photon * 1e9  # 1000 photons per channel

    return CrossbarResult(
        N=N,
        weight_matrix=weight_matrix,
        input_phases=phases_in,
        output_fields=E_out,
        output_intensities=intensities,
        cross_talk_dB=cross_talk_dB,
        insertion_loss_dB=loss_per_element_dB * N,
        total_energy_nJ=total_energy_nJ,
    )


# ---------------------------------------------------------------------------
# Technology comparison
# ---------------------------------------------------------------------------

@dataclass
class PhotonicTechComparison:
    """Comparison of photonic memory technologies."""
    name: str
    bits_per_cell: float
    write_energy_nJ: float
    write_time_ns: float
    read_energy_fJ: float
    static_power_W: float
    endurance: float
    retention_hours: float
    cmos_compatible: bool
    density_estimate: str     # qualitative
    notes: str = ""


def technology_comparison() -> List[PhotonicTechComparison]:
    """
    Compare WCFOMA variants and conventional photonic memory.
    """
    comparisons = [
        PhotonicTechComparison(
            name="Ferroelectric MZI (HZO)",
            bits_per_cell=1.58,
            write_energy_nJ=0.1,
            write_time_ns=100.0,
            read_energy_fJ=0.13,
            static_power_W=0.0,
            endurance=1e5,
            retention_hours=12.0,
            cmos_compatible=True,
            density_estimate="~10⁸ cells/cm² (photonic pitch ~10 µm)",
            notes="Taki et al. 2024 demonstrated; trinary encoding",
        ),
        PhotonicTechComparison(
            name="Ferroelectric MZI (BaTiO₃)",
            bits_per_cell=1.58,
            write_energy_nJ=0.05,
            write_time_ns=10.0,
            read_energy_fJ=0.13,
            static_power_W=0.0,
            endurance=1e8,
            retention_hours=1e5,
            cmos_compatible=False,
            density_estimate="~10⁸ cells/cm² (photonic pitch ~10 µm)",
            notes="Strongest Pockels effect; needs epitaxial growth",
        ),
        PhotonicTechComparison(
            name="Ce:YIG MO ring (magnonic)",
            bits_per_cell=3.5,
            write_energy_nJ=0.143,
            write_time_ns=1.0,
            read_energy_fJ=10.0,
            static_power_W=0.0,
            endurance=2.4e9,
            retention_hours=1e4,
            cmos_compatible=False,
            density_estimate="~10⁷ cells/cm² (ring pitch ~30 µm)",
            notes="Yan et al.; 3.5 bits analog precision demonstrated",
        ),
        PhotonicTechComparison(
            name="Ferrofluid acoustic (mitigated)",
            bits_per_cell=2.28,
            write_energy_nJ=10.0,
            write_time_ns=14300.0,
            read_energy_fJ=100.0,
            static_power_W=0.0,
            endurance=1e15,
            retention_hours=0.001,
            cmos_compatible=False,
            density_estimate="~10⁹ cells/cm³ (3D, 10 µm pitch)",
            notes="Our Phase 0–3 model; gel + 10⁸ photons; volatile",
        ),
        PhotonicTechComparison(
            name="PCM (Ge₂Sb₂Te₅) photonic",
            bits_per_cell=3.0,
            write_energy_nJ=5.0,
            write_time_ns=50.0,
            read_energy_fJ=1.0,
            static_power_W=0.0,
            endurance=1e6,
            retention_hours=1e5,
            cmos_compatible=True,
            density_estimate="~10⁸ cells/cm²",
            notes="Well-established; amorphous/crystalline switching",
        ),
    ]
    return comparisons


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def ferroelectric_summary(material_name: str = "HZO") -> str:
    """Generate a text summary of the ferroelectric photonic cell."""
    result = characterize_mzi_cell(material_name)
    mat = result.material

    # Optimal length for π shift
    L_pi = optimize_interaction_length(material_name, target_phase=np.pi)

    lines = [
        "=" * 65,
        f"  FERROELECTRIC PHOTONIC CELL: {mat.name}",
        "=" * 65,
        f"  Δn:                   {mat.delta_n:.1e}",
        f"  Waveguide n_eff:      {mat.n_eff:.1f}",
        f"  Film thickness:       {mat.film_thickness_nm:.0f} nm",
        f"  Coercive voltage:     {mat.coercive_voltage:.1f} V",
        f"  CMOS compatible:      {'Yes ✅' if mat.cmos_compatible else 'No ❌'}",
        "-" * 65,
        f"  Interaction length:   {result.cell.L_fe*1e6:.0f} µm",
        f"  Length for π shift:   {L_pi*1e6:.0f} µm",
        f"  Wavelength:           {result.cell.wavelength*1e9:.0f} nm",
        "-" * 65,
        "  TRINARY STATES",
        f"  {'State':<12} {'Phase [rad]':<14} {'I_out':<10} {'Label':<10}",
    ]
    for s in result.states:
        lines.append(
            f"  {s.polarization:+d}{'':>9} {s.phase_shift:<14.4f} "
            f"{s.output_intensity:<10.4f} {s.label:<10}"
        )
    lines.extend([
        "-" * 65,
        f"  Contrast ratio:       {result.max_contrast_dB:.1f} dB",
        f"  Bits per cell:        {result.bits_per_cell:.2f}",
        f"  Write energy:         {result.write_energy_nJ:.3f} nJ",
        f"  Write time:           {result.write_time_ns:.0f} ns",
        f"  Read energy:          {result.read_energy_fJ:.2f} fJ",
        f"  Static power:         {result.static_power_W:.0f} W (non-volatile)",
        f"  Endurance:            {mat.endurance_cycles:.0e} cycles",
        f"  Retention:            {mat.retention_hours:.0f} hours",
        "=" * 65,
    ])
    return "\n".join(lines)
