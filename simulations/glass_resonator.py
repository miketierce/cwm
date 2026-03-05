"""
Glass acoustic resonator simulation for garage-scale WCFOMA prototyping.

This module models acoustic eigenmodes in solid glass rods/tubes as a
WCFOMA memory and computation substrate. Glass eliminates the phase
diffusion problem that killed the ferrofluid approach (77.5% of noise
budget) because it is a solid — no Brownian motion, no nanoparticle
rotational diffusion.

Key physics:
    - Longitudinal acoustic modes: f_n = n * v / (2L)
    - Q factors: 1,000–100,000+ (well-characterized, unlike ferrofluid)
    - Perturbation encoding: attached masses shift mode frequencies
      via Rayleigh perturbation: Δf_n/f_n = -(Δm/2M) sin²(nπx/L)
    - Non-volatile storage via permanent perturbations (wax, notch, thermal)
    - Dynamic working memory via driven mode amplitudes
    - Associative recall via multi-mode interference (Hopfield-compatible)

Historical precedent:
    - Mercury delay line memory (UNIVAC I, 1951): acoustic pulses in liquid
    - Quartz crystal oscillators (billions/year): single-mode in quartz
    - WCFOMA glass: multi-mode spectral encoding + interference computation

Reference materials:
    - Soda-lime glass: hardware store, $2/rod
    - Borosilicate (Pyrex): Amazon, $8/10-pack
    - Fused silica: optics supplier, $15/rod
    - PZT piezo discs: Amazon, $5/10-pack

Prototype cost: ~$63 (see bill_of_materials())
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from .common import K_B


# ---------------------------------------------------------------------------
# Glass material database
# ---------------------------------------------------------------------------

@dataclass
class GlassProperties:
    """Acoustic and thermal properties of a glass type."""
    name: str
    v_longitudinal: float     # longitudinal wave speed [m/s]
    v_shear: float            # shear wave speed [m/s]
    density: float            # density [kg/m³]
    Q_acoustic: float         # quality factor (longitudinal, room temp)
    alpha_thermal: float      # thermal expansion coefficient [1/K] (affects v)
    youngs_modulus: float     # Young's modulus [Pa]
    poisson_ratio: float      # Poisson's ratio
    T_anneal: float           # annealing point [K]
    T_strain: float           # strain point [K]
    T_softening: float        # softening point [K]
    cost_note: str = ""
    source_note: str = ""


def glass_database() -> Dict[str, GlassProperties]:
    """
    Reference data for common glass types.

    Values from ASM International, Corning datasheets, Schott catalogs,
    and acoustic measurement literature (Bhatia 1967, Krautkramer 1990).
    """
    return {
        "soda_lime": GlassProperties(
            name="Soda-lime (window/bottle glass)",
            v_longitudinal=5500.0,
            v_shear=3300.0,
            density=2500.0,
            Q_acoustic=3000.0,
            alpha_thermal=9.0e-6,
            youngs_modulus=72e9,
            poisson_ratio=0.22,
            T_anneal=818.0,
            T_strain=773.0,
            T_softening=999.0,
            cost_note="$2/rod, hardware store",
            source_note="Most common glass; bottles, windows",
        ),
        "borosilicate": GlassProperties(
            name="Borosilicate (Pyrex/Duran)",
            v_longitudinal=5500.0,
            v_shear=3400.0,
            density=2230.0,
            Q_acoustic=10000.0,
            alpha_thermal=3.3e-6,
            youngs_modulus=63e9,
            poisson_ratio=0.20,
            T_anneal=838.0,
            T_strain=783.0,
            T_softening=1053.0,
            cost_note="$8/10-pack, Amazon",
            source_note="Lab glass; low thermal expansion; best price/performance",
        ),
        "fused_silica": GlassProperties(
            name="Fused silica (pure SiO₂)",
            v_longitudinal=5960.0,
            v_shear=3760.0,
            density=2200.0,
            Q_acoustic=100000.0,
            alpha_thermal=0.55e-6,
            youngs_modulus=73e9,
            poisson_ratio=0.17,
            T_anneal=1413.0,
            T_strain=1353.0,
            T_softening=1938.0,
            cost_note="$15/rod, optics supplier",
            source_note="Highest Q; used in quartz oscillators",
        ),
        "lead_glass": GlassProperties(
            name="Lead glass (crystal)",
            v_longitudinal=3800.0,
            v_shear=2100.0,
            density=3800.0,
            Q_acoustic=1500.0,
            alpha_thermal=10.0e-6,
            youngs_modulus=50e9,
            poisson_ratio=0.27,
            T_anneal=708.0,
            T_strain=673.0,
            T_softening=903.0,
            cost_note="$5 (wine glass)",
            source_note="Lower v → denser modes; wine glass demonstrates Q",
        ),
    }


# ---------------------------------------------------------------------------
# Rod geometry and mode structure
# ---------------------------------------------------------------------------

@dataclass
class RodGeometry:
    """Geometry of a glass rod resonator."""
    length: float = 0.15       # rod length [m]
    diameter: float = 6e-3     # rod diameter [m]
    glass_type: str = "borosilicate"

    @property
    def cross_section(self) -> float:
        """Cross-sectional area [m²]."""
        return np.pi * (self.diameter / 2) ** 2

    @property
    def volume(self) -> float:
        """Volume [m³]."""
        return self.cross_section * self.length


@dataclass
class ModeSpectrum:
    """Acoustic mode spectrum of a glass rod."""
    glass: GlassProperties
    rod: RodGeometry
    frequencies: np.ndarray    # mode frequencies [Hz]
    mode_numbers: np.ndarray   # mode indices
    linewidths: np.ndarray     # linewidths [Hz]
    coherence_times: np.ndarray  # per-mode coherence [s]
    mass: float                # rod mass [kg]
    f_fundamental: float       # fundamental frequency [Hz]
    mode_spacing: float        # frequency spacing [Hz]


def compute_mode_spectrum(
    rod: RodGeometry = None,
    n_modes: int = 100,
) -> ModeSpectrum:
    """
    Compute longitudinal acoustic mode spectrum of a glass rod.

    Uses f_n = n * v / (2L) for a free-free rod with longitudinal modes.

    Parameters
    ----------
    rod : RodGeometry
        Rod dimensions and glass type.
    n_modes : int
        Number of modes to compute.

    Returns
    -------
    ModeSpectrum
    """
    if rod is None:
        rod = RodGeometry()

    db = glass_database()
    glass = db[rod.glass_type]

    mass = glass.density * rod.volume
    f1 = glass.v_longitudinal / (2 * rod.length)
    ns = np.arange(1, n_modes + 1)
    freqs = ns * f1
    linewidths = freqs / glass.Q_acoustic
    coherence = glass.Q_acoustic / (np.pi * freqs)

    return ModeSpectrum(
        glass=glass,
        rod=rod,
        frequencies=freqs,
        mode_numbers=ns,
        linewidths=linewidths,
        coherence_times=coherence,
        mass=mass,
        f_fundamental=f1,
        mode_spacing=f1,
    )


# ---------------------------------------------------------------------------
# Thermal stability
# ---------------------------------------------------------------------------

@dataclass
class ThermalStabilityResult:
    """Thermal mode stability analysis."""
    glass_type: str
    Q: float
    alpha: float               # thermal drift coefficient [1/K]
    delta_T: float             # temperature variation [K]
    max_safe_modes: int
    bits_per_mode: float
    total_bits: float
    total_bytes: float
    thermal_shift_per_K: float  # absolute shift at f1 [Hz/K]


def thermal_stability(
    rod: RodGeometry = None,
    delta_T: float = 1.0,
    A_drive: float = 1e-9,
    T: float = 300.0,
) -> ThermalStabilityResult:
    """
    Compute maximum usable modes under thermal drift.

    Criterion: 2 * f_n * alpha * dT < delta_f - f_n / Q
    Simplified: n < 1 / (2*alpha*dT + 1/Q)

    Parameters
    ----------
    rod : RodGeometry
        Rod geometry.
    delta_T : float
        Temperature stability [K].
    A_drive : float
        Drive amplitude [m] for SNR calculation.
    T : float
        Temperature [K].

    Returns
    -------
    ThermalStabilityResult
    """
    if rod is None:
        rod = RodGeometry()

    spectrum = compute_mode_spectrum(rod, n_modes=1)
    glass = spectrum.glass

    # Mode capacity limited by thermal drift
    denom = 2 * glass.alpha_thermal * delta_T + 1.0 / glass.Q_acoustic
    n_max = int(1.0 / denom) if denom > 0 else 999999

    # SNR for bits/mode
    m_eff = spectrum.mass / 2
    omega = 2 * np.pi * spectrum.f_fundamental
    k_eff = m_eff * omega ** 2
    E_signal = 0.5 * k_eff * A_drive ** 2
    snr_linear = E_signal / (K_B * T)
    bits_per_mode = 0.5 * np.log2(1 + snr_linear)

    total_bits = n_max * bits_per_mode
    shift_hz = glass.alpha_thermal * spectrum.f_fundamental

    return ThermalStabilityResult(
        glass_type=rod.glass_type,
        Q=glass.Q_acoustic,
        alpha=glass.alpha_thermal,
        delta_T=delta_T,
        max_safe_modes=n_max,
        bits_per_mode=bits_per_mode,
        total_bits=total_bits,
        total_bytes=total_bits / 8,
        thermal_shift_per_K=shift_hz,
    )


# ---------------------------------------------------------------------------
# SNR analysis (the ferrofluid killer comparison)
# ---------------------------------------------------------------------------

@dataclass
class SNRResult:
    """Signal-to-noise analysis for a glass rod resonator."""
    glass_type: str
    A_drive: float             # drive amplitude [m]
    A_thermal: float           # thermal noise amplitude [m]
    E_signal: float            # signal energy [J]
    E_thermal: float           # thermal energy [J]
    SNR_linear: float
    SNR_dB: float
    bits_per_mode: float
    k_eff: float               # effective spring constant [N/m]
    m_eff: float               # effective mass [kg]
    phase_diffusion_fraction: float  # always 0 for glass


def compute_snr(
    rod: RodGeometry = None,
    A_drive: float = 1e-9,
    T: float = 300.0,
) -> SNRResult:
    """
    SNR for acoustic modes in a glass rod.

    The dominant noise source is thermal (Johnson-Nyquist) phonon noise.
    Phase diffusion = 0 because glass is a solid.

    Parameters
    ----------
    rod : RodGeometry
        Rod geometry.
    A_drive : float
        Drive amplitude [m]. 1 nm is trivially achievable with PZT.
    T : float
        Temperature [K].

    Returns
    -------
    SNRResult
    """
    if rod is None:
        rod = RodGeometry()

    spectrum = compute_mode_spectrum(rod, n_modes=1)
    glass = spectrum.glass

    m_eff = spectrum.mass / 2
    omega = 2 * np.pi * spectrum.f_fundamental
    k_eff = m_eff * omega ** 2

    E_signal = 0.5 * k_eff * A_drive ** 2
    E_thermal = K_B * T
    A_thermal = np.sqrt(K_B * T / k_eff)

    snr_linear = E_signal / E_thermal
    snr_dB = 10 * np.log10(snr_linear)
    bits = 0.5 * np.log2(1 + snr_linear)

    return SNRResult(
        glass_type=rod.glass_type,
        A_drive=A_drive,
        A_thermal=A_thermal,
        E_signal=E_signal,
        E_thermal=E_thermal,
        SNR_linear=snr_linear,
        SNR_dB=snr_dB,
        bits_per_mode=bits,
        k_eff=k_eff,
        m_eff=m_eff,
        phase_diffusion_fraction=0.0,
    )


# ---------------------------------------------------------------------------
# Perturbation encoding (writing data into glass)
# ---------------------------------------------------------------------------

@dataclass
class Perturbation:
    """A localized perturbation on a glass rod."""
    position: float            # position along rod [m]
    delta_mass: float          # added mass [kg] (positive = mass, negative = notch)
    label: str = ""


@dataclass
class PerturbationSpectrum:
    """Mode frequency shifts from a set of perturbations."""
    perturbations: List[Perturbation]
    mode_numbers: np.ndarray
    unperturbed_freqs: np.ndarray   # [Hz]
    perturbed_freqs: np.ndarray     # [Hz]
    shifts: np.ndarray              # fractional shifts Δf/f
    shift_hz: np.ndarray            # absolute shifts [Hz]
    detectable: np.ndarray          # bool: shift > linewidth/10
    signature: np.ndarray           # normalized spectral fingerprint


def rayleigh_perturbation(
    rod: RodGeometry = None,
    perturbations: List[Perturbation] = None,
    n_modes: int = 20,
) -> PerturbationSpectrum:
    """
    Compute mode frequency shifts from localized mass perturbations.

    Uses the Rayleigh perturbation formula for longitudinal modes:
        Δf_n / f_n = -(Δm / 2M) * sin²(nπx/L)

    Each perturbation shifts modes differently depending on position,
    creating a unique spectral fingerprint — this IS the stored data.

    Parameters
    ----------
    rod : RodGeometry
        Rod geometry.
    perturbations : list of Perturbation
        Mass perturbations along the rod.
    n_modes : int
        Number of modes to compute.

    Returns
    -------
    PerturbationSpectrum
    """
    if rod is None:
        rod = RodGeometry()
    if perturbations is None:
        perturbations = [Perturbation(position=rod.length / 4, delta_mass=0.1e-3)]

    spectrum = compute_mode_spectrum(rod, n_modes)
    glass = spectrum.glass
    M = spectrum.mass
    L = rod.length

    ns = np.arange(1, n_modes + 1)
    freqs = spectrum.frequencies.copy()

    total_shift = np.zeros(n_modes)
    for p in perturbations:
        for i, n in enumerate(ns):
            frac = -(p.delta_mass / (2 * M)) * np.sin(n * np.pi * p.position / L) ** 2
            total_shift[i] += frac

    shift_hz = total_shift * freqs
    perturbed = freqs + shift_hz
    linewidths = freqs / glass.Q_acoustic
    detectable = np.abs(shift_hz) > linewidths / 10

    # Normalized signature for pattern matching
    sig = total_shift / (np.abs(total_shift).max() + 1e-30)

    return PerturbationSpectrum(
        perturbations=perturbations,
        mode_numbers=ns,
        unperturbed_freqs=freqs,
        perturbed_freqs=perturbed,
        shifts=total_shift,
        shift_hz=shift_hz,
        detectable=detectable,
        signature=sig,
    )


# ---------------------------------------------------------------------------
# Information encoding capacity
# ---------------------------------------------------------------------------

@dataclass
class EncodingCapacity:
    """Information capacity of perturbation encoding."""
    n_perturbations: int
    position_resolution: int
    mass_levels: int
    bits_per_perturbation: float
    total_bits: float
    total_bytes: float
    method: str


def perturbation_capacity(
    n_perturbations: int = 10,
    position_resolution: int = 100,
    mass_levels: int = 8,
) -> EncodingCapacity:
    """
    Estimate information capacity of perturbation-encoded glass rod.

    Each perturbation blob encodes:
        - Position: log2(position_resolution) bits
        - Mass: log2(mass_levels) bits

    Parameters
    ----------
    n_perturbations : int
        Number of discrete perturbation points.
    position_resolution : int
        Number of distinguishable positions along rod.
    mass_levels : int
        Number of distinguishable mass values.

    Returns
    -------
    EncodingCapacity
    """
    bits_per = np.log2(position_resolution) + np.log2(mass_levels)
    total = n_perturbations * bits_per

    return EncodingCapacity(
        n_perturbations=n_perturbations,
        position_resolution=position_resolution,
        mass_levels=mass_levels,
        bits_per_perturbation=bits_per,
        total_bits=total,
        total_bytes=total / 8,
        method="perturbation (wax/tape/notch)",
    )


# ---------------------------------------------------------------------------
# Associative recall via mode interference
# ---------------------------------------------------------------------------

@dataclass
class RecallResult:
    """Result of associative recall across a rod array."""
    query_signature: np.ndarray
    stored_signatures: List[np.ndarray]
    correlations: np.ndarray       # correlation of query with each stored
    best_match_index: int
    best_match_correlation: float
    n_rods: int
    n_modes: int


def associative_recall(
    query: np.ndarray,
    stored: List[np.ndarray],
) -> RecallResult:
    """
    Associative recall via spectral correlation.

    In the physical system, this happens via interference: driving all rods
    with the query spectrum and measuring which resonates most strongly.
    Mathematically, this is a normalized correlation.

    Parameters
    ----------
    query : np.ndarray
        Query spectral signature (normalized).
    stored : list of np.ndarray
        Stored spectral signatures (normalized).

    Returns
    -------
    RecallResult
    """
    n_modes = len(query)
    correlations = np.array([
        np.dot(query, s) / (np.linalg.norm(query) * np.linalg.norm(s) + 1e-30)
        for s in stored
    ])
    best_idx = int(np.argmax(correlations))

    return RecallResult(
        query_signature=query,
        stored_signatures=stored,
        correlations=correlations,
        best_match_index=best_idx,
        best_match_correlation=correlations[best_idx],
        n_rods=len(stored),
        n_modes=n_modes,
    )


# ---------------------------------------------------------------------------
# Technology comparison
# ---------------------------------------------------------------------------

@dataclass
class GlassTechComparison:
    """Comparison entry for glass resonator vs. other technologies."""
    name: str
    SNR_dB: float
    bits_per_mode: float
    modes_at_1K: int
    total_bits: float
    Q_factor: float
    coherence_s: float
    phase_diffusion_pct: float
    prototype_cost: str
    non_volatile: bool
    fab_complexity: str
    notes: str = ""


def technology_comparison(
    rod: RodGeometry = None,
    A_drive: float = 1e-9,
) -> List[GlassTechComparison]:
    """
    Compare glass resonator WCFOMA to ferrofluid and other approaches.

    Returns
    -------
    list of GlassTechComparison
    """
    if rod is None:
        rod = RodGeometry()

    snr = compute_snr(rod, A_drive)
    stab = thermal_stability(rod, delta_T=1.0, A_drive=A_drive)
    spectrum = compute_mode_spectrum(rod, n_modes=1)

    comparisons = [
        GlassTechComparison(
            name=f"Glass rod ({rod.glass_type})",
            SNR_dB=snr.SNR_dB,
            bits_per_mode=snr.bits_per_mode,
            modes_at_1K=stab.max_safe_modes,
            total_bits=stab.total_bits,
            Q_factor=spectrum.glass.Q_acoustic,
            coherence_s=spectrum.coherence_times[0],
            phase_diffusion_pct=0.0,
            prototype_cost="~$63",
            non_volatile=True,
            fab_complexity="Epoxy piezo to rod",
            notes="No exotic materials; all from Amazon/hardware store",
        ),
        GlassTechComparison(
            name="Ferrofluid acoustic (baseline)",
            SNR_dB=-6.5,
            bits_per_mode=0.0,
            modes_at_1K=0,
            total_bits=0.0,
            Q_factor=500.0,
            coherence_s=0.0,
            phase_diffusion_pct=77.5,
            prototype_cost="~$500-1000",
            non_volatile=False,
            fab_complexity="Coils + cavity + seals + ferrofluid",
            notes="Phase diffusion kills SNR; 0 usable modes",
        ),
        GlassTechComparison(
            name="Ferrofluid acoustic (mitigated)",
            SNR_dB=13.5,
            bits_per_mode=2.28,
            modes_at_1K=10,
            total_bits=22.8,
            Q_factor=500.0,
            coherence_s=0.0,
            phase_diffusion_pct=77.5,
            prototype_cost="~$500-1000",
            non_volatile=False,
            fab_complexity="+ gel + 10⁸ photon laser",
            notes="Requires gel immobilization + expensive optics",
        ),
        GlassTechComparison(
            name="Ferroelectric MZI (HZO/SiN)",
            SNR_dB=30.0,
            bits_per_mode=1.58,
            modes_at_1K=1,
            total_bits=1.58,
            Q_factor=0.0,
            coherence_s=float("inf"),
            phase_diffusion_pct=0.0,
            prototype_cost="~$50k+ (fab access)",
            non_volatile=True,
            fab_complexity="Cleanroom lithography",
            notes="Best density but requires university/foundry fab",
        ),
        GlassTechComparison(
            name="Mercury delay line (1951)",
            SNR_dB=40.0,
            bits_per_mode=1.0,
            modes_at_1K=1000,
            total_bits=1000.0,
            Q_factor=100.0,
            coherence_s=0.001,
            phase_diffusion_pct=0.0,
            prototype_cost="historical",
            non_volatile=False,
            fab_complexity="Mercury tube + piezo",
            notes="UNIVAC I; serial delay, not spectral encoding",
        ),
    ]
    return comparisons


# ---------------------------------------------------------------------------
# Bill of materials
# ---------------------------------------------------------------------------

@dataclass
class BOMItem:
    """Bill of materials entry."""
    item: str
    cost_usd: float
    source: str
    notes: str = ""


def bill_of_materials() -> Tuple[List[BOMItem], float]:
    """
    Bill of materials for a garage glass rod WCFOMA prototype.

    Returns
    -------
    items : list of BOMItem
    total_cost : float
        Total cost in USD.
    """
    items = [
        BOMItem("Borosilicate glass rods 6mm x 150mm (10-pack)", 8.0,
                "Amazon", "Pyrex stirring rods; 10 experiments"),
        BOMItem("PZT piezo discs 27mm with leads (10-pack)", 5.0,
                "Amazon", "Drive + sense transducers"),
        BOMItem("5-minute epoxy", 6.0,
                "Hardware store", "Bond piezo to glass; removable with heat"),
        BOMItem("Arduino Nano + USB cable", 5.0,
                "Amazon (clone)", "Signal generation + ADC"),
        BOMItem("Breadboard + jumper wire kit", 10.0,
                "Amazon", "Prototyping circuit"),
        BOMItem("LM358 dual op-amp", 1.0,
                "Amazon/DigiKey", "Transimpedance amplifier for piezo"),
        BOMItem("Resistor + capacitor assortment", 5.0,
                "Amazon", "RC filtering, gain setting"),
        BOMItem("Foam/rubber isolation mat", 5.0,
                "Hardware store", "Vibration decoupling from bench"),
        BOMItem("Beeswax or modeling clay (100g)", 3.0,
                "Craft store", "Removable perturbation masses"),
        BOMItem("Digital scale 0.01g resolution", 15.0,
                "Amazon", "Weigh perturbation masses"),
    ]
    total = sum(i.cost_usd for i in items)
    return items, total


# ---------------------------------------------------------------------------
# Prototype experiment plan
# ---------------------------------------------------------------------------

def experiment_plan() -> List[Dict]:
    """
    Structured experiment plan for the garage prototype.

    Returns a list of experiments with description, setup, measurement,
    and success criteria.
    """
    return [
        {
            "id": "EXP-G01",
            "name": "Mode spectrum measurement",
            "description": "Measure longitudinal acoustic modes of a bare glass rod",
            "setup": "Epoxy one piezo (drive) at one end, one piezo (sense) at other end. "
                     "Rod on foam mat. Connect drive to function generator or Arduino tone output. "
                     "Connect sense to oscilloscope or Arduino ADC.",
            "procedure": "Frequency sweep 1 kHz to 500 kHz. Record amplitude at sense piezo. "
                         "Alternatively: impulse excitation (tap rod) and FFT of ring-down.",
            "success_criterion": "Observe at least 5 distinct resonant peaks matching f_n = n * v / (2L) "
                                 "within 5% of predicted frequencies.",
            "predicted": "f1 ~ 18.3 kHz for 15cm borosilicate rod",
            "kill_criterion": "If no clear peaks above noise floor, check coupling (try different epoxy, "
                              "clamp force, or direct piezo-to-rod contact).",
        },
        {
            "id": "EXP-G02",
            "name": "Q factor measurement",
            "description": "Measure quality factor via ring-down decay",
            "setup": "Same as EXP-G01. Use impulse excitation.",
            "procedure": "Tap rod or pulse drive piezo. Record decay at sense piezo. "
                         "Measure envelope decay time tau. Q = pi * f * tau.",
            "success_criterion": "Q > 1,000 for borosilicate. Q > 500 for soda-lime.",
            "predicted": "Q ~ 5,000-10,000 for borosilicate",
            "kill_criterion": "Q < 100 would indicate severe coupling losses. "
                              "Try: thinner epoxy layer, contact at rod center (node), better isolation.",
        },
        {
            "id": "EXP-G03",
            "name": "Perturbation detection",
            "description": "Detect mode frequency shifts from attached masses",
            "setup": "Same as EXP-G01/02. Pre-measure bare rod spectrum.",
            "procedure": "Attach 0.1g beeswax blob at L/4. Re-measure spectrum. "
                         "Compare peak frequencies to bare rod. "
                         "Move blob to L/3, repeat. Remove blob, verify return to bare spectrum.",
            "success_criterion": "Detect >1 Hz shift in at least 3 modes. "
                                 "Different positions produce different shift patterns.",
            "predicted": "~48 Hz shift in mode 1 for 0.1g at L/4 on borosilicate rod",
            "kill_criterion": "If shifts are smaller than linewidth, try larger mass (0.5g) "
                              "or more sensitive readout (oscilloscope instead of Arduino ADC).",
        },
        {
            "id": "EXP-G04",
            "name": "Pattern discrimination",
            "description": "Distinguish two different perturbation patterns by spectrum",
            "setup": "Two identical rods. Pattern A: wax at L/4 + L/2. Pattern B: wax at L/3 + 2L/3.",
            "procedure": "Measure spectra of both rods. Compute spectral correlation. "
                         "Verify patterns A and B produce distinct fingerprints.",
            "success_criterion": "Correlation between same pattern > 0.95. "
                                 "Correlation between different patterns < 0.5.",
            "predicted": "Different positions create orthogonal shift patterns",
            "kill_criterion": "If patterns are indistinguishable, increase number of measured modes "
                              "or use larger/different mass values.",
        },
        {
            "id": "EXP-G05",
            "name": "Associative recall",
            "description": "Demonstrate content-addressable memory with rod array",
            "setup": "3+ rods with different perturbation patterns. All connected to shared drive.",
            "procedure": "Drive with query frequency pattern. Measure which rod resonates most strongly. "
                         "Query should match one stored pattern. Verify correct rod is selected.",
            "success_criterion": "Correct rod identified with >90% accuracy across 10 trials.",
            "predicted": "Mode interference creates measurable amplitude differences at sense piezos",
            "kill_criterion": "If cross-talk between rods prevents discrimination, "
                              "add acoustic isolation (foam) or use electrical multiplexing.",
        },
    ]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def glass_resonator_summary(rod: RodGeometry = None) -> str:
    """Generate a text summary of the glass resonator analysis."""
    if rod is None:
        rod = RodGeometry()

    snr = compute_snr(rod)
    stab = thermal_stability(rod, delta_T=1.0)
    bom_items, bom_total = bill_of_materials()
    spectrum = compute_mode_spectrum(rod, n_modes=1)

    lines = [
        "=" * 60,
        "GLASS ACOUSTIC RESONATOR — WCFOMA GARAGE PROTOTYPE",
        "=" * 60,
        "",
        f"Glass: {spectrum.glass.name}",
        f"Rod: {rod.diameter*1000:.0f}mm x {rod.length*1000:.0f}mm",
        f"Mass: {spectrum.mass*1000:.2f} g",
        "",
        f"Fundamental: {spectrum.f_fundamental:.0f} Hz "
        f"({spectrum.f_fundamental/1000:.2f} kHz)",
        f"Mode spacing: {spectrum.mode_spacing:.0f} Hz",
        f"Q factor: {spectrum.glass.Q_acoustic:,.0f}",
        f"Coherence: {spectrum.coherence_times[0]:.3f} s",
        "",
        f"SNR (1nm drive): {snr.SNR_dB:.1f} dB",
        f"Bits/mode: {snr.bits_per_mode:.1f}",
        f"Phase diffusion: {snr.phase_diffusion_fraction:.0f}%",
        "",
        f"Thermal stability (+/-1K): {stab.max_safe_modes:,} modes",
        f"Total capacity: {stab.total_bits:,.0f} bits "
        f"({stab.total_bytes:,.0f} bytes)",
        "",
        f"Prototype cost: ${bom_total:.0f}",
        "",
        "Key advantage over ferrofluid:",
        "  Phase diffusion = 0% (vs. 77.5%)",
        f"  SNR = {snr.SNR_dB:.0f} dB (vs. -6.5 dB baseline)",
        f"  Modes = {stab.max_safe_modes:,} (vs. 0 baseline, 10 mitigated)",
        "  Cost = $63 (vs. $500-1000)",
        "  Materials = hardware store (vs. specialty ferrofluid)",
    ]
    return "\n".join(lines)
