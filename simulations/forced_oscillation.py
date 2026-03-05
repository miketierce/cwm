"""
Forced-Oscillation Selective Write / Erase for WCFOMA.

Extends the existing resonator_1d damped oscillator model with a
driving force term, enabling frequency-selective excitation and
thermalization of individual acoustic eigenmodes.

From the original corpus (Scale 1, Ch7 Resonant Architecture and
the CVE-2022-38392 / Rhythm Nation reference in Scale 3):
  - Sub-watt acoustic energy at the correct resonant frequency
    can displace µm-scale structures (CVE-2022-38392 demonstrated
    a laptop HDD failure from a specific musical frequency).
  - Each mode in a WCFOMA cell has a unique resonant frequency.
  - Selective excitation at f_n writes to mode n without disturbing
    other modes, provided Q is high enough for mode isolation.
  - Broad-spectrum noise or anti-phase driving thermalizes modes
    for erase.

Model equation (forced damped oscillator):
  ẍ + 2η ẋ + ω₀² x = F₀ cos(ω_d t)

Steady-state solution:
  A(ω_d) = F₀ / √[(ω₀² - ω_d²)² + (2η ω_d)²]
  At resonance (ω_d = ω₀):  A_res = F₀ / (2η ω₀)

Phase response:
  φ(ω_d) = arctan[2η ω_d / (ω₀² - ω_d²)]

Selectivity (cross-mode leakage):
  A(f_n, driving at f_m) / A(f_m, driving at f_m)
  For Q ≫ 1:  leakage ≈ 1 / (4Q² · |n-m|² / n² + 1)

Energy budget:
  Write energy:  E_write = A² · k_eff / 2  (energy to reach target amplitude)
  Erase energy:  E_erase ≈ k_B T per mode  (thermalize to noise floor)
  Total:         P = Σ E_n / t_cycle

Capabilities:
  - Forced oscillator frequency response and phase
  - Single-mode selective write at target amplitude
  - Multi-mode write with cross-talk analysis
  - Erase by broadband/anti-phase driving
  - Energy budget for write/erase cycles
  - Q-dependent selectivity optimization
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.integrate import odeint

from .common import K_B, C_FERROFLUID, MicroCellParams


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class FrequencyResponse:
    """Frequency response of a forced damped oscillator."""
    drive_freqs: np.ndarray       # driving frequency array [Hz]
    amplitudes: np.ndarray        # steady-state amplitude vs freq
    phases: np.ndarray            # phase lag vs freq [rad]
    resonant_freq: float          # natural frequency [Hz]
    Q: float                      # quality factor
    peak_amplitude: float         # amplitude at resonance
    bandwidth_3dB: float          # 3 dB bandwidth [Hz]


@dataclass
class SelectiveWriteResult:
    """Result of writing to a specific mode."""
    target_mode: int
    drive_freq: float             # [Hz]
    drive_amplitude: float        # F₀ normalized
    target_amplitude: float       # steady-state displacement at target
    write_energy_J: float         # energy deposited in target mode
    write_time_s: float           # time to reach steady state (~Q/f cycles)
    cross_talk: Dict[int, float]  # mode_n → amplitude ratio (leak / target)
    max_cross_talk: float         # worst-case cross-talk ratio
    selectivity_dB: float         # 10*log10(target / max_leak)


@dataclass
class MultiModeWriteResult:
    """Result of writing a pattern across multiple modes."""
    n_modes: int
    target_amplitudes: np.ndarray
    achieved_amplitudes: np.ndarray
    cross_talk_matrix: np.ndarray   # n_modes × n_modes
    total_energy_J: float
    total_time_s: float
    pattern_fidelity: float         # correlation between target and achieved
    bits_written: int               # log2 of distinguishable amplitude levels


@dataclass
class EraseResult:
    """Result of erasing one or more modes."""
    method: str                   # "broadband", "antiphase", "thermal"
    modes_erased: List[int]
    residual_amplitudes: np.ndarray  # after erase
    erase_energy_J: float
    erase_time_s: float
    thermal_floor: float          # expected thermal amplitude


@dataclass
class EnergyBudget:
    """Energy budget for a complete write/read/erase cycle."""
    n_modes: int
    bits_per_mode: int
    write_energy_per_mode_J: float
    erase_energy_per_mode_J: float
    read_energy_J: float           # optical readout energy
    total_write_J: float
    total_erase_J: float
    total_cycle_J: float
    energy_per_bit_J: float
    comparison: Dict[str, float]   # tech → J/bit


# ---------------------------------------------------------------------------
# Core physics
# ---------------------------------------------------------------------------

def mode_frequencies(
    n_modes: int = 10,
    L: float = 1e-5,
    c: float = C_FERROFLUID,
) -> np.ndarray:
    """
    Natural frequencies for modes 1..n_modes in a 1D cavity.

    f_n = n * c / (2L)

    Returns array of frequencies [Hz].
    """
    return np.array([n * c / (2 * L) for n in range(1, n_modes + 1)])


def mode_stiffness(
    f: float,
    m_eff: float = 1e-15,
) -> float:
    """
    Effective spring constant for a mode.

    k_eff = m_eff · (2π f)²
    """
    return m_eff * (2 * np.pi * f)**2


def thermal_amplitude(
    f: float,
    T: float = 300.0,
    m_eff: float = 1e-15,
) -> float:
    """
    Thermal noise amplitude for a mode.

    A_th = √(k_B T / k_eff)
    """
    k = mode_stiffness(f, m_eff)
    return np.sqrt(K_B * T / k)


def forced_oscillator_amplitude(
    omega_d: float,
    omega_0: float,
    eta: float,
    F0: float = 1.0,
) -> float:
    """
    Steady-state amplitude of forced damped oscillator.

    A = F₀ / √[(ω₀² - ω_d²)² + (2η ω_d)²]

    Parameters
    ----------
    omega_d : float
        Driving angular frequency [rad/s].
    omega_0 : float
        Natural angular frequency [rad/s].
    eta : float
        Damping coefficient [1/s].
    F0 : float
        Driving force amplitude (normalized).

    Returns
    -------
    float
        Steady-state amplitude.
    """
    denom = np.sqrt((omega_0**2 - omega_d**2)**2 + (2 * eta * omega_d)**2)
    return F0 / max(denom, 1e-30)


def forced_oscillator_phase(
    omega_d: float,
    omega_0: float,
    eta: float,
) -> float:
    """
    Phase lag of forced damped oscillator.

    φ = arctan(2η ω_d / (ω₀² - ω_d²))

    Returns phase in radians.
    """
    return np.arctan2(2 * eta * omega_d, omega_0**2 - omega_d**2)


def Q_factor(omega_0: float, eta: float) -> float:
    """Quality factor: Q = ω₀ / (2η)."""
    return omega_0 / (2 * max(eta, 1e-30))


# ---------------------------------------------------------------------------
# Frequency response
# ---------------------------------------------------------------------------

def compute_frequency_response(
    f_0: float,
    Q: float = 500.0,
    f_range_factor: float = 3.0,
    n_points: int = 1000,
    F0: float = 1.0,
) -> FrequencyResponse:
    """
    Compute full frequency response (Bode plot data) for a single mode.

    Parameters
    ----------
    f_0 : float
        Natural frequency [Hz].
    Q : float
        Quality factor.
    f_range_factor : float
        Sweep from f_0/factor to f_0*factor.
    n_points : int
        Number of frequency points.
    F0 : float
        Drive amplitude.

    Returns
    -------
    FrequencyResponse
    """
    omega_0 = 2 * np.pi * f_0
    eta = omega_0 / (2 * Q)

    freqs = np.linspace(f_0 / f_range_factor, f_0 * f_range_factor, n_points)
    amps = np.zeros(n_points)
    phases = np.zeros(n_points)

    for i, f in enumerate(freqs):
        omega_d = 2 * np.pi * f
        amps[i] = forced_oscillator_amplitude(omega_d, omega_0, eta, F0)
        phases[i] = forced_oscillator_phase(omega_d, omega_0, eta)

    peak_amp = F0 / (2 * eta * omega_0)
    bw_3dB = f_0 / Q

    return FrequencyResponse(
        drive_freqs=freqs,
        amplitudes=amps,
        phases=phases,
        resonant_freq=f_0,
        Q=Q,
        peak_amplitude=peak_amp,
        bandwidth_3dB=bw_3dB,
    )


# ---------------------------------------------------------------------------
# Selective write
# ---------------------------------------------------------------------------

def selective_write(
    target_mode: int,
    n_modes: int = 10,
    L: float = 1e-5,
    c: float = C_FERROFLUID,
    Q: float = 500.0,
    target_amplitude: float = 1e-9,
    m_eff: float = 1e-15,
    T: float = 300.0,
) -> SelectiveWriteResult:
    """
    Simulate writing to a single target mode and measure cross-talk
    into all other modes.

    Parameters
    ----------
    target_mode : int
        Mode number to excite (1-indexed).
    n_modes : int
        Total modes in the cavity.
    L, c : float
        Cavity length and sound speed.
    Q : float
        Quality factor (same for all modes; conservative).
    target_amplitude : float
        Desired amplitude at target mode [m].
    m_eff : float
        Effective mass per mode [kg].
    T : float
        Temperature [K].

    Returns
    -------
    SelectiveWriteResult
    """
    freqs = mode_frequencies(n_modes, L, c)
    f_target = freqs[target_mode - 1]
    omega_target = 2 * np.pi * f_target
    eta_target = omega_target / (2 * Q)

    # Required driving force to achieve target amplitude at resonance
    # A_res = F0 / (2η ω₀) → F0 = A_res · 2η ω₀
    F0 = target_amplitude * 2 * eta_target * omega_target

    # Cross-talk: amplitude at each other mode when driven at f_target
    cross_talk = {}
    omega_d = omega_target  # driving at target frequency

    for m in range(1, n_modes + 1):
        if m == target_mode:
            continue
        f_m = freqs[m - 1]
        omega_m = 2 * np.pi * f_m
        eta_m = omega_m / (2 * Q)
        amp_leak = forced_oscillator_amplitude(omega_d, omega_m, eta_m, F0)
        cross_talk[m] = amp_leak / target_amplitude

    max_leak = max(cross_talk.values()) if cross_talk else 0.0
    selectivity_dB = -10 * np.log10(max(max_leak, 1e-30))

    # Write energy
    k_eff = mode_stiffness(f_target, m_eff)
    write_energy = 0.5 * k_eff * target_amplitude**2

    # Write time (~Q cycles to build up)
    write_time = Q / f_target

    return SelectiveWriteResult(
        target_mode=target_mode,
        drive_freq=f_target,
        drive_amplitude=F0,
        target_amplitude=target_amplitude,
        write_energy_J=write_energy,
        write_time_s=write_time,
        cross_talk=cross_talk,
        max_cross_talk=max_leak,
        selectivity_dB=selectivity_dB,
    )


# ---------------------------------------------------------------------------
# Multi-mode write
# ---------------------------------------------------------------------------

def multi_mode_write(
    target_pattern: np.ndarray,
    n_modes: int = 10,
    L: float = 1e-5,
    c: float = C_FERROFLUID,
    Q: float = 500.0,
    max_amplitude: float = 1e-9,
    m_eff: float = 1e-15,
    T: float = 300.0,
) -> MultiModeWriteResult:
    """
    Write a pattern across all modes sequentially.

    target_pattern : array of shape (n_modes,)
        Normalized amplitudes [0, 1] for each mode.

    Returns
    -------
    MultiModeWriteResult
    """
    target_pattern = np.asarray(target_pattern, dtype=float)
    if len(target_pattern) != n_modes:
        raise ValueError(f"Pattern length {len(target_pattern)} ≠ n_modes {n_modes}")

    freqs = mode_frequencies(n_modes, L, c)

    # Build cross-talk matrix
    ct_matrix = np.zeros((n_modes, n_modes))
    for m in range(n_modes):
        if target_pattern[m] < 1e-12:
            continue
        result = selective_write(
            target_mode=m + 1,
            n_modes=n_modes,
            L=L, c=c, Q=Q,
            target_amplitude=max_amplitude * target_pattern[m],
            m_eff=m_eff, T=T,
        )
        ct_matrix[m, m] = 1.0  # self
        for k, leak in result.cross_talk.items():
            ct_matrix[m, k - 1] = leak

    # Achieved amplitudes: sum of contributions from all written modes
    achieved = np.zeros(n_modes)
    for m in range(n_modes):
        for k in range(n_modes):
            achieved[m] += target_pattern[k] * ct_matrix[k, m] * max_amplitude

    # Normalize for comparison
    target_abs = target_pattern * max_amplitude
    fidelity = float(np.corrcoef(target_abs, achieved)[0, 1]) if np.std(target_abs) > 0 else 1.0

    # Energy
    total_energy = 0.0
    total_time = 0.0
    for m in range(n_modes):
        if target_pattern[m] < 1e-12:
            continue
        k_eff = mode_stiffness(freqs[m], m_eff)
        total_energy += 0.5 * k_eff * (max_amplitude * target_pattern[m])**2
        total_time += Q / freqs[m]

    # Bits: determined by cross-talk floor
    max_ct = np.max(ct_matrix[ct_matrix < 0.999]) if np.any(ct_matrix < 0.999) else 1e-30
    if max_ct > 0:
        bits = max(1, int(np.floor(-np.log2(max(max_ct, 1e-30)))))
    else:
        bits = 20

    return MultiModeWriteResult(
        n_modes=n_modes,
        target_amplitudes=target_abs,
        achieved_amplitudes=achieved,
        cross_talk_matrix=ct_matrix,
        total_energy_J=total_energy,
        total_time_s=total_time,
        pattern_fidelity=fidelity,
        bits_written=bits,
    )


# ---------------------------------------------------------------------------
# Erase
# ---------------------------------------------------------------------------

def erase_modes(
    mode_indices: Optional[List[int]] = None,
    n_modes: int = 10,
    L: float = 1e-5,
    c: float = C_FERROFLUID,
    Q: float = 500.0,
    current_amplitudes: Optional[np.ndarray] = None,
    m_eff: float = 1e-15,
    T: float = 300.0,
    method: str = "broadband",
) -> EraseResult:
    """
    Erase specified modes (or all) to the thermal noise floor.

    Methods:
      "broadband" - Inject broadband noise to thermalize.
      "antiphase" - Drive at anti-phase to cancel specific modes.
      "thermal"   - Wait for natural thermal equilibration.

    Parameters
    ----------
    mode_indices : list of int or None
        1-indexed modes to erase. None → all modes.
    current_amplitudes : array or None
        Current amplitudes. None → assume max_amplitude = 1e-9.

    Returns
    -------
    EraseResult
    """
    freqs = mode_frequencies(n_modes, L, c)

    if mode_indices is None:
        mode_indices = list(range(1, n_modes + 1))
    if current_amplitudes is None:
        current_amplitudes = np.full(n_modes, 1e-9)

    thermal_floor_amps = np.array([
        thermal_amplitude(f, T, m_eff) for f in freqs
    ])

    # Residual after erase
    residual = current_amplitudes.copy()
    erase_energy = 0.0
    erase_time = 0.0

    for m in mode_indices:
        idx = m - 1
        k_eff = mode_stiffness(freqs[idx], m_eff)

        if method == "broadband":
            # Broadband noise thermalizes all modes simultaneously
            residual[idx] = thermal_floor_amps[idx]
            erase_energy += 0.5 * k_eff * current_amplitudes[idx]**2
            # Time: ~Q cycles for ring-down
            erase_time = max(erase_time, Q / freqs[idx])

        elif method == "antiphase":
            # Anti-phase driving cancels specific mode; ~Q cycles
            residual[idx] = thermal_floor_amps[idx]
            erase_energy += 0.5 * k_eff * current_amplitudes[idx]**2
            erase_time += Q / freqs[idx]  # sequential per mode

        elif method == "thermal":
            # Natural ring-down: t_decay = Q / (π f)
            t_decay = Q / (np.pi * freqs[idx])
            residual[idx] = current_amplitudes[idx] * np.exp(-1)
            erase_time = max(erase_time, 3 * t_decay)  # 3τ for ~95% decay
            erase_energy += 0.0  # passive

    return EraseResult(
        method=method,
        modes_erased=mode_indices,
        residual_amplitudes=residual,
        erase_energy_J=erase_energy,
        erase_time_s=erase_time,
        thermal_floor=float(np.mean(thermal_floor_amps)),
    )


# ---------------------------------------------------------------------------
# Time-domain forced oscillator simulation
# ---------------------------------------------------------------------------

def simulate_forced_oscillator(
    f_0: float,
    f_drive: float,
    Q: float = 500.0,
    F0: float = 1.0,
    t_max: Optional[float] = None,
    n_points: int = 10000,
    x0: float = 0.0,
    v0: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Time-domain simulation of a forced damped oscillator.

    Returns (t, x, v) arrays.
    """
    omega_0 = 2 * np.pi * f_0
    omega_d = 2 * np.pi * f_drive
    eta = omega_0 / (2 * Q)

    if t_max is None:
        t_max = 5 * Q / f_0  # enough for steady state

    def ode(y, t):
        return [
            y[1],
            -2 * eta * y[1] - omega_0**2 * y[0] + F0 * np.cos(omega_d * t),
        ]

    t = np.linspace(0, t_max, n_points)
    sol = odeint(ode, [x0, v0], t)
    return t, sol[:, 0], sol[:, 1]


# ---------------------------------------------------------------------------
# Q-dependent selectivity analysis
# ---------------------------------------------------------------------------

def selectivity_vs_Q(
    Q_values: Optional[np.ndarray] = None,
    n_modes: int = 10,
    L: float = 1e-5,
    c: float = C_FERROFLUID,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute selectivity (dB) and achievable bits/mode as a function of Q.

    Returns
    -------
    Q_values : array
    selectivities : array [dB]
    bits_per_mode : array
    """
    if Q_values is None:
        Q_values = np.logspace(1, 5, 50)

    selectivities = np.zeros(len(Q_values))
    bits = np.zeros(len(Q_values))

    for i, Q in enumerate(Q_values):
        result = selective_write(
            target_mode=1,
            n_modes=n_modes,
            L=L, c=c, Q=Q,
        )
        selectivities[i] = result.selectivity_dB
        # Bits limited by cross-talk floor
        if result.max_cross_talk > 0:
            bits[i] = max(1, int(-np.log2(max(result.max_cross_talk, 1e-30))))
        else:
            bits[i] = 20

    return Q_values, selectivities, bits


# ---------------------------------------------------------------------------
# Energy budget
# ---------------------------------------------------------------------------

def compute_energy_budget(
    n_modes: int = 10,
    bits_per_mode: int = 10,
    L: float = 1e-5,
    c: float = C_FERROFLUID,
    Q: float = 500.0,
    max_amplitude: float = 1e-9,
    m_eff: float = 1e-15,
    T: float = 300.0,
    read_photons: float = 1e8,
    read_wavelength: float = 633e-9,
) -> EnergyBudget:
    """
    Compute full energy budget for a write/read/erase cycle.

    Returns
    -------
    EnergyBudget
    """
    freqs = mode_frequencies(n_modes, L, c)
    h = 6.626e-34  # Planck constant

    # Write: sum over modes
    write_per_mode = []
    for f in freqs:
        k = mode_stiffness(f, m_eff)
        write_per_mode.append(0.5 * k * max_amplitude**2)

    avg_write = np.mean(write_per_mode)
    total_write = np.sum(write_per_mode)

    # Erase: thermal energy per mode
    erase_per_mode = K_B * T  # thermalize
    total_erase = erase_per_mode * n_modes

    # Read: photon energy
    read_energy = read_photons * h * 3e8 / read_wavelength

    total_cycle = total_write + total_erase + read_energy
    total_bits = n_modes * bits_per_mode
    energy_per_bit = total_cycle / max(total_bits, 1)

    # Comparison
    comparison = {
        "WCFOMA forced oscillation": energy_per_bit,
        "Flash NAND": 1e-15,                # ~1 fJ/bit
        "DRAM": 5e-15,                       # ~5 fJ/bit
        "Magnetic HDD": 1e-14,               # ~10 fJ/bit
        "Phase-change (PCM)": 1e-12,         # ~1 pJ/bit
        "Ce:YIG magnonic": 143e-15,          # 143 fJ/bit demonstrated
        "Ferroelectric photonic": 100e-15,   # ~100 fJ/bit estimated
    }

    return EnergyBudget(
        n_modes=n_modes,
        bits_per_mode=bits_per_mode,
        write_energy_per_mode_J=avg_write,
        erase_energy_per_mode_J=erase_per_mode,
        read_energy_J=read_energy,
        total_write_J=total_write,
        total_erase_J=total_erase,
        total_cycle_J=total_cycle,
        energy_per_bit_J=energy_per_bit,
        comparison=comparison,
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def forced_oscillation_summary() -> str:
    """Generate a text summary of the forced oscillation analysis."""
    freqs = mode_frequencies(10)
    resp = compute_frequency_response(freqs[0], Q=500.0)
    write1 = selective_write(1, n_modes=10, Q=500.0)
    write5 = selective_write(5, n_modes=10, Q=500.0)

    Qs, sel, bits = selectivity_vs_Q()
    budget = compute_energy_budget()

    # Multi-mode example: alternating pattern
    pattern = np.array([1, 0, 0.5, 0, 1, 0, 0.5, 0, 1, 0])
    multi = multi_mode_write(pattern)

    erase_broad = erase_modes(method="broadband")
    erase_anti = erase_modes(method="antiphase")

    lines = [
        "=" * 65,
        "  FORCED-OSCILLATION SELECTIVE WRITE/ERASE ANALYSIS",
        "=" * 65,
        "",
        "  CAVITY PARAMETERS",
        f"    Cell length:         10 µm",
        f"    Sound speed:         {C_FERROFLUID} m/s",
        f"    Mode 1 frequency:    {freqs[0]/1e6:.1f} MHz",
        f"    Mode 10 frequency:   {freqs[9]/1e6:.1f} MHz",
        f"    Mode spacing:        {(freqs[1]-freqs[0])/1e6:.1f} MHz",
        "",
        "-" * 65,
        "  FREQUENCY RESPONSE (mode 1)",
        f"    Resonant frequency:  {resp.resonant_freq/1e6:.1f} MHz",
        f"    Q factor:            {resp.Q:.0f}",
        f"    3 dB bandwidth:      {resp.bandwidth_3dB/1e3:.1f} kHz",
        f"    Peak amplitude:      {resp.peak_amplitude:.2e}",
        "",
        "-" * 65,
        "  SELECTIVE WRITE",
        f"    Mode 1 → selectivity: {write1.selectivity_dB:.1f} dB"
        f"  (max leak: {write1.max_cross_talk:.2e})",
        f"    Mode 5 → selectivity: {write5.selectivity_dB:.1f} dB"
        f"  (max leak: {write5.max_cross_talk:.2e})",
        f"    Write time (mode 1): {write1.write_time_s*1e6:.1f} µs",
        f"    Write energy (mode 1): {write1.write_energy_J:.2e} J",
        "",
        "-" * 65,
        "  MULTI-MODE WRITE (pattern: [1,0,½,0,1,0,½,0,1,0])",
        f"    Pattern fidelity:    {multi.pattern_fidelity:.4f}",
        f"    Bits per mode:       {multi.bits_written}",
        f"    Total energy:        {multi.total_energy_J:.2e} J",
        f"    Total time:          {multi.total_time_s*1e6:.1f} µs",
        "",
        "-" * 65,
        "  ERASE ANALYSIS",
        f"    Broadband: {erase_broad.erase_energy_J:.2e} J, "
        f"{erase_broad.erase_time_s*1e6:.1f} µs",
        f"    Anti-phase: {erase_anti.erase_energy_J:.2e} J, "
        f"{erase_anti.erase_time_s*1e6:.1f} µs",
        f"    Thermal floor: {erase_broad.thermal_floor:.2e} m",
        "",
        "-" * 65,
        "  Q-DEPENDENT SELECTIVITY",
        f"    Q=100:  ~{sel[np.argmin(np.abs(Qs-100))]:.0f} dB selectivity, "
        f"~{bits[np.argmin(np.abs(Qs-100))]:.0f} bits/mode",
        f"    Q=500:  ~{sel[np.argmin(np.abs(Qs-500))]:.0f} dB selectivity, "
        f"~{bits[np.argmin(np.abs(Qs-500))]:.0f} bits/mode",
        f"    Q=10k:  ~{sel[np.argmin(np.abs(Qs-1e4))]:.0f} dB selectivity, "
        f"~{bits[np.argmin(np.abs(Qs-1e4))]:.0f} bits/mode",
        "",
        "-" * 65,
        "  ENERGY BUDGET (10 modes × 10 bits)",
        f"    Write total:  {budget.total_write_J:.2e} J",
        f"    Erase total:  {budget.total_erase_J:.2e} J",
        f"    Read (optical):{budget.read_energy_J:.2e} J",
        f"    Total cycle:  {budget.total_cycle_J:.2e} J",
        f"    Energy/bit:   {budget.energy_per_bit_J:.2e} J/bit",
        "",
        "  COMPARISON",
    ]
    for tech, epb in budget.comparison.items():
        lines.append(f"    {tech:<35} {epb:.2e} J/bit")
    lines.append("=" * 65)

    return "\n".join(lines)
