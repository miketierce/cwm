"""
Coupled Multiphysics Simulator for WCFOMA.

Models the interaction between three physical domains:
  1. Acoustic (resonant eigenmodes in ferrofluid)
  2. Electromagnetic (magnon-phonon coupling, ZIM effects)
  3. Thermal (temperature-dependent sound velocity, viscosity)

The coupling is bidirectional:
  - Acoustic ↔ EM:  Magnetostrictive coupling coefficient κ_ae
  - Acoustic ↔ Thermal: Sound velocity shift c(T), viscosity η(T)
  - EM ↔ Thermal: Curie-law magnetization M(T)

This module implements a reduced-order model (ROM) that captures the
essential coupling physics without requiring a full 3D FEM solve.
Each domain is represented by its dominant mode amplitudes, and the
coupling enters as perturbative interaction terms.

References:
  - Paper v9, Section 2.2 (ferrofluid medium)
  - Paper v9, Section 3.3 (multiphysics coupling)
  - Rosensweig, "Ferrohydrodynamics" (1985)
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict
import numpy as np
from scipy.integrate import solve_ivp

from .common import K_B, C_FERROFLUID, CavityParams, ThermalParams


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CouplingParams:
    """Parameters governing inter-domain coupling strengths."""
    # Magnetostrictive coupling (acoustic ↔ EM)
    kappa_ae: float = 1e-3        # dimensionless coupling coefficient
    # Magnon-phonon relaxation time [s]
    tau_mp: float = 1e-7
    # Thermal expansion coefficient of ferrofluid [1/K]
    beta_thermal: float = 4e-4
    # Curie temperature [K] (typical ferrofluid: ~350-600 K)
    T_curie: float = 450.0
    # Ambient temperature [K]
    T_ambient: float = 300.0
    # Thermal diffusivity [m²/s] (ferrofluid ~ water)
    alpha_thermal: float = 1.5e-7
    # Nonlinear mode coupling coefficient
    chi_nonlinear: float = 1e-6
    # Number of acoustic modes
    n_acoustic: int = 5
    # Number of EM modes
    n_em: int = 3
    # Base damping rate [1/s]
    eta_acoustic: float = 50.0
    eta_em: float = 100.0
    # Sound velocity temperature coefficient [m/s/K]
    dc_dT: float = -3.0           # ferrofluid: c decreases with T


@dataclass
class CoupledState:
    """State vector for the coupled system."""
    # Acoustic mode amplitudes (complex)
    a_acoustic: np.ndarray
    # EM mode amplitudes (complex)
    a_em: np.ndarray
    # Temperature perturbation [K] (scalar, uniform cavity approx.)
    delta_T: float
    # Time [s]
    t: float = 0.0


@dataclass
class CoupledResult:
    """Results from a coupled simulation run."""
    times: np.ndarray
    # Shape: (n_times, n_acoustic)
    acoustic_amplitudes: np.ndarray
    # Shape: (n_times, n_em)
    em_amplitudes: np.ndarray
    # Shape: (n_times,)
    temperature: np.ndarray
    # Derived quantities
    acoustic_energies: np.ndarray
    em_energies: np.ndarray
    total_energy: np.ndarray
    # Mode frequencies over time (shifted by temperature)
    acoustic_freqs: np.ndarray
    # Coupling diagnostics
    energy_transfer_acoustic_to_em: np.ndarray
    max_mode_crosstalk: float
    coherence_time: float
    # Parameters used
    params: CouplingParams = field(default_factory=CouplingParams)


# ---------------------------------------------------------------------------
# Core physics
# ---------------------------------------------------------------------------

def acoustic_eigenfrequencies(n_modes: int, L: float = 1e-5,
                               c: float = C_FERROFLUID) -> np.ndarray:
    """
    Eigenfrequencies of a 1D cavity: f_n = n * c / (2L).

    Parameters
    ----------
    n_modes : int
        Number of modes (n = 1, 2, ..., n_modes).
    L : float
        Cavity length [m].
    c : float
        Sound velocity [m/s].

    Returns
    -------
    np.ndarray
        Frequencies in Hz.
    """
    ns = np.arange(1, n_modes + 1)
    return ns * c / (2 * L)


def em_eigenfrequencies(n_modes: int, L: float = 1e-5,
                         c_em: float = 3e8,
                         epsilon_eff: float = 1e6) -> np.ndarray:
    """
    EM (magnon/spin-wave) eigenfrequencies in a ferrofluid cavity.

    f_n = n * c / (2L * sqrt(ε_eff))

    For ferrofluid magnons, the effective permittivity is very large
    (ε_eff ~ 10⁶), which brings EM modes into the GHz-MHz range
    where magnon-phonon coupling is relevant.
    """
    ns = np.arange(1, n_modes + 1)
    return ns * c_em / (2 * L * np.sqrt(epsilon_eff))


def sound_velocity_shifted(c0: float, dc_dT: float, delta_T: float) -> float:
    """Temperature-shifted sound velocity: c(T) = c0 + dc_dT * ΔT."""
    return c0 + dc_dT * delta_T


def magnetization_curie(T: float, T_curie: float, M0: float = 1.0) -> float:
    """
    Simple Curie-law magnetization: M(T) = M0 * (1 - T/T_c) for T < T_c.

    Parameters
    ----------
    T : float
        Current temperature [K].
    T_curie : float
        Curie temperature [K].
    M0 : float
        Saturation magnetization (normalized).

    Returns
    -------
    float
        Normalized magnetization.
    """
    if T >= T_curie:
        return 0.0
    return M0 * (1.0 - T / T_curie)


def mode_coupling_matrix(n_modes: int, chi: float,
                          freqs: np.ndarray) -> np.ndarray:
    """
    Nonlinear mode-mode coupling matrix.

    C_ij = χ / |f_i - f_j| for i ≠ j, 0 on diagonal.
    This represents four-wave mixing style coupling where
    modes interact more strongly when spectrally close.

    Parameters
    ----------
    n_modes : int
        Number of modes.
    chi : float
        Nonlinear coupling strength.
    freqs : np.ndarray
        Mode frequencies [Hz].

    Returns
    -------
    np.ndarray
        Shape (n_modes, n_modes) coupling matrix.
    """
    C = np.zeros((n_modes, n_modes))
    for i in range(n_modes):
        for j in range(n_modes):
            if i != j:
                df = abs(freqs[i] - freqs[j])
                if df > 0:
                    C[i, j] = chi / df
    return C


# ---------------------------------------------------------------------------
# ODE system — Slowly-Varying Envelope Approximation (SVEA)
# ---------------------------------------------------------------------------

def coupled_ode_svea(t: float, y: np.ndarray,
                     params: CouplingParams,
                     L: float,
                     omega_a0: np.ndarray,
                     omega_em0: np.ndarray,
                     excitation: Optional[callable] = None) -> np.ndarray:
    """
    Slowly-varying envelope equations for the coupled system.

    We write each mode as:
      a_n(t) = ã_n(t) * exp(i ω_n t)

    Substituting into the full equations and dropping fast-oscillating
    terms (rotating wave approximation), the envelope ã_n evolves as:

      dã_n/dt = -η_a * ã_n
                + i*κ*M * Σ_m g_nm * b̃_m * exp(i(ω_m^em - ω_n^a)t)
                + i*χ * Σ_j C_nj * |ã_j|² * ã_n
                + F̃_n(t)

    For near-resonant coupling (|ω_m^em - ω_n^a| small), the exponential
    is slowly varying and retained. For far off-resonant modes, the
    coupling averages to zero (secular approximation).

    The temperature perturbation couples through frequency shifts:
      Δω_n = ω_n0 * (dc_dT * ΔT / c0)

    State vector y:
      [Re(ã_acoustic), Im(ã_acoustic), Re(b̃_em), Im(b̃_em), delta_T]
    """
    na = params.n_acoustic
    ne = params.n_em
    total = 2 * na + 2 * ne + 1

    # Unpack state
    a_re = y[:na]
    a_im = y[na:2*na]
    b_re = y[2*na:2*na+ne]
    b_im = y[2*na+ne:2*na+2*ne]
    dT = y[-1]

    a = a_re + 1j * a_im   # Slowly-varying acoustic envelopes
    b = b_re + 1j * b_im   # Slowly-varying EM envelopes

    # Temperature-dependent frequency shift
    delta_omega_frac = params.dc_dT * dT / C_FERROFLUID  # fractional shift

    # Magnetization
    T_current = params.T_ambient + dT
    M = magnetization_curie(T_current, params.T_curie)

    # Overlap integrals (precomputed would be better, but simple here)
    g = np.zeros((na, ne))
    for n in range(na):
        for m in range(ne):
            g[n, m] = 1.0 / np.sqrt((n + 1) * (m + 1))

    # Nonlinear mode coupling (use base frequencies)
    freqs_a = omega_a0 / (2 * np.pi)
    C_nl = mode_coupling_matrix(na, params.chi_nonlinear, freqs_a)

    # Detunings: Δ_nm = ω_m^em - ω_n^a
    # In SVEA, these appear as exp(iΔt) phases
    detunings = np.zeros((na, ne))
    for n in range(na):
        for m in range(ne):
            detunings[n, m] = omega_em0[m] - omega_a0[n]

    # Acoustic envelope evolution
    da = np.zeros(na, dtype=complex)
    for n in range(na):
        # Damping + frequency shift from temperature
        da[n] = (-params.eta_acoustic + 1j * omega_a0[n] * delta_omega_frac) * a[n]
        # Coupling to EM (with detuning phase)
        for m in range(ne):
            phase = np.exp(1j * detunings[n, m] * t)
            da[n] += 1j * params.kappa_ae * M * g[n, m] * b[m] * phase
        # Nonlinear self-modulation
        for j in range(na):
            da[n] += 1j * C_nl[n, j] * abs(a[j])**2 * a[n]

    # External excitation (slowly-varying envelope)
    if excitation is not None:
        da += excitation(t, na)

    # EM envelope evolution
    db = np.zeros(ne, dtype=complex)
    for m in range(ne):
        db[m] = -params.eta_em * b[m]
        for n in range(na):
            phase = np.exp(-1j * detunings[n, m] * t)
            db[m] += 1j * params.kappa_ae * M * g[n, m] * a[n] * phase

    # Thermal evolution (lumped model)
    P_dissipated = params.eta_acoustic * np.sum(np.abs(a)**2)
    tau_thermal = L**2 / params.alpha_thermal
    dT_dt = -dT / tau_thermal + params.beta_thermal * P_dissipated

    # Pack derivatives
    dy = np.zeros(total)
    dy[:na] = da.real
    dy[na:2*na] = da.imag
    dy[2*na:2*na+ne] = db.real
    dy[2*na+ne:2*na+2*ne] = db.imag
    dy[-1] = dT_dt

    return dy


# ---------------------------------------------------------------------------
# High-level simulation runner
# ---------------------------------------------------------------------------

def run_coupled_simulation(
    params: CouplingParams = None,
    L: float = 1e-5,
    t_max: float = 1e-4,
    n_points: int = 2000,
    initial_acoustic: Optional[np.ndarray] = None,
    initial_em: Optional[np.ndarray] = None,
    initial_dT: float = 0.0,
    excitation: Optional[callable] = None,
) -> CoupledResult:
    """
    Run a coupled multiphysics simulation.

    Parameters
    ----------
    params : CouplingParams
        Coupling parameters. Uses defaults if None.
    L : float
        Cavity length [m].
    t_max : float
        Simulation duration [s].
    n_points : int
        Number of output time points.
    initial_acoustic : np.ndarray, optional
        Initial acoustic mode amplitudes (complex). Default: mode 1 excited.
    initial_em : np.ndarray, optional
        Initial EM mode amplitudes (complex). Default: zero.
    initial_dT : float
        Initial temperature perturbation [K].
    excitation : callable, optional
        Function excitation(t, n_modes) -> np.ndarray of complex forces.

    Returns
    -------
    CoupledResult
        Full simulation results with diagnostics.
    """
    if params is None:
        params = CouplingParams()

    na = params.n_acoustic
    ne = params.n_em

    # Eigenfrequencies
    omega_a0 = 2 * np.pi * acoustic_eigenfrequencies(na, L)
    omega_em0 = 2 * np.pi * em_eigenfrequencies(ne, L)

    # Initial conditions
    if initial_acoustic is None:
        initial_acoustic = np.zeros(na, dtype=complex)
        initial_acoustic[0] = 1.0  # Excite fundamental
    if initial_em is None:
        initial_em = np.zeros(ne, dtype=complex)

    # Pack into state vector
    y0 = np.zeros(2 * na + 2 * ne + 1)
    y0[:na] = initial_acoustic.real
    y0[na:2*na] = initial_acoustic.imag
    y0[2*na:2*na+ne] = initial_em.real
    y0[2*na+ne:2*na+2*ne] = initial_em.imag
    y0[-1] = initial_dT

    # Time span
    t_eval = np.linspace(0, t_max, n_points)

    # Solve (SVEA eliminates fast oscillations, so RK45 is fine)
    sol = solve_ivp(
        coupled_ode_svea,
        [0, t_max],
        y0,
        method='RK45',
        t_eval=t_eval,
        args=(params, L, omega_a0, omega_em0, excitation),
        rtol=1e-8,
        atol=1e-10,
    )

    if not sol.success:
        raise RuntimeError(f"ODE solver failed: {sol.message}")

    # Unpack
    times = sol.t
    nt = len(times)
    a_re = sol.y[:na, :].T
    a_im = sol.y[na:2*na, :].T
    b_re = sol.y[2*na:2*na+ne, :].T
    b_im = sol.y[2*na+ne:2*na+2*ne, :].T
    dT = sol.y[-1, :]

    acoustic_amps = a_re + 1j * a_im   # (nt, na)
    em_amps = b_re + 1j * b_im         # (nt, ne)

    # Energies (proportional to |a|²)
    acoustic_E = np.abs(acoustic_amps)**2   # (nt, na)
    em_E = np.abs(em_amps)**2               # (nt, ne)
    total_E = np.sum(acoustic_E, axis=1) + np.sum(em_E, axis=1)

    # Frequency tracking: base freq + envelope phase evolution
    base_freqs = acoustic_eigenfrequencies(na, L)
    acoustic_freqs = np.zeros((nt, na))
    for n in range(na):
        phase = np.unwrap(np.angle(acoustic_amps[:, n]))
        dt_arr = np.diff(times)
        dphi = np.diff(phase)
        # Envelope frequency shift (on top of carrier)
        inst_shift = dphi / (dt_arr * 2 * np.pi)
        acoustic_freqs[1:, n] = base_freqs[n] + inst_shift
        acoustic_freqs[0, n] = base_freqs[n]

    # Energy transfer: power flowing from acoustic to EM
    # Estimated as d/dt of EM energy
    em_total = np.sum(em_E, axis=1)
    energy_transfer = np.gradient(em_total, times)

    # Mode crosstalk: max off-diagonal correlation between acoustic modes
    if na > 1:
        # Normalize amplitudes
        norms = np.abs(acoustic_amps)
        norms[norms < 1e-30] = 1e-30
        normed = acoustic_amps / norms
        # Cross-correlation matrix at final time
        final_amps = normed[-1, :]
        cross = np.abs(np.outer(final_amps, np.conj(final_amps)))
        np.fill_diagonal(cross, 0)
        max_crosstalk = float(np.max(cross))
    else:
        max_crosstalk = 0.0

    # Coherence time: 1/e decay of total acoustic energy
    a_total = np.sum(acoustic_E, axis=1)
    if a_total[0] > 0:
        threshold = a_total[0] / np.e
        decay_idx = np.where(a_total < threshold)[0]
        if len(decay_idx) > 0:
            coherence_time = float(times[decay_idx[0]])
        else:
            coherence_time = float(t_max)  # Didn't decay in window
    else:
        coherence_time = 0.0

    return CoupledResult(
        times=times,
        acoustic_amplitudes=acoustic_amps,
        em_amplitudes=em_amps,
        temperature=dT,
        acoustic_energies=acoustic_E,
        em_energies=em_E,
        total_energy=total_E,
        acoustic_freqs=acoustic_freqs,
        energy_transfer_acoustic_to_em=energy_transfer,
        max_mode_crosstalk=max_crosstalk,
        coherence_time=coherence_time,
        params=params,
    )


# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------

def coupling_strength_scan(
    kappa_values: np.ndarray = None,
    L: float = 1e-5,
    t_max: float = 1e-4,
) -> Dict[str, np.ndarray]:
    """
    Scan coupling strength κ_ae and measure energy transfer.

    Returns
    -------
    dict with 'kappa', 'max_em_energy', 'coherence_time', 'max_crosstalk'
    """
    if kappa_values is None:
        kappa_values = np.logspace(-5, -1, 20)

    results = {
        'kappa': kappa_values,
        'max_em_energy': np.zeros(len(kappa_values)),
        'coherence_time': np.zeros(len(kappa_values)),
        'max_crosstalk': np.zeros(len(kappa_values)),
    }

    for i, kappa in enumerate(kappa_values):
        p = CouplingParams(kappa_ae=kappa)
        try:
            r = run_coupled_simulation(params=p, L=L, t_max=t_max,
                                        n_points=500)
            results['max_em_energy'][i] = np.max(np.sum(r.em_energies, axis=1))
            results['coherence_time'][i] = r.coherence_time
            results['max_crosstalk'][i] = r.max_mode_crosstalk
        except RuntimeError:
            results['max_em_energy'][i] = np.nan
            results['coherence_time'][i] = np.nan
            results['max_crosstalk'][i] = np.nan

    return results


def thermal_feedback_test(
    delta_T_values: np.ndarray = None,
    L: float = 1e-5,
    t_max: float = 1e-4,
) -> Dict[str, np.ndarray]:
    """
    Test thermal feedback: run simulations with varying initial ΔT.

    Returns frequency drift and coherence time vs initial temperature.
    """
    if delta_T_values is None:
        delta_T_values = np.array([0, 1, 2, 5, 10, 20])

    results = {
        'delta_T': delta_T_values,
        'freq_drift_pct': np.zeros(len(delta_T_values)),
        'coherence_time': np.zeros(len(delta_T_values)),
        'final_temperature': np.zeros(len(delta_T_values)),
    }

    # Reference frequency at ΔT=0
    f0 = acoustic_eigenfrequencies(1, L)[0]

    for i, dT in enumerate(delta_T_values):
        p = CouplingParams()
        r = run_coupled_simulation(params=p, L=L, t_max=t_max,
                                    n_points=500, initial_dT=float(dT))
        # Average frequency of mode 1 over last 10% of simulation
        f_late = np.mean(r.acoustic_freqs[int(0.9 * len(r.times)):, 0])
        results['freq_drift_pct'][i] = abs(f_late - f0) / f0 * 100
        results['coherence_time'][i] = r.coherence_time
        results['final_temperature'][i] = float(r.temperature[-1])

    return results


def coupled_summary(result: CoupledResult) -> str:
    """Generate a text summary of coupled simulation results."""
    lines = [
        "=" * 60,
        "  COUPLED MULTIPHYSICS SIMULATION SUMMARY",
        "=" * 60,
        f"  Acoustic modes:  {result.params.n_acoustic}",
        f"  EM modes:        {result.params.n_em}",
        f"  κ_ae coupling:   {result.params.kappa_ae:.1e}",
        f"  χ_nonlinear:     {result.params.chi_nonlinear:.1e}",
        f"  Duration:        {result.times[-1]*1e6:.1f} µs",
        "-" * 60,
        "  ENERGY",
        f"    Initial total:       {result.total_energy[0]:.4e}",
        f"    Final total:         {result.total_energy[-1]:.4e}",
        f"    Energy retained:     {result.total_energy[-1]/max(result.total_energy[0], 1e-30)*100:.1f}%",
        f"    Max EM energy:       {np.max(np.sum(result.em_energies, axis=1)):.4e}",
        f"    Peak transfer rate:  {np.max(np.abs(result.energy_transfer_acoustic_to_em)):.4e} /s",
        "-" * 60,
        "  COHERENCE",
        f"    Coherence time (1/e): {result.coherence_time*1e6:.1f} µs",
        f"    Mode crosstalk (max): {result.max_mode_crosstalk:.4f}",
        "-" * 60,
        "  THERMAL",
        f"    Initial ΔT:   {result.temperature[0]:.2f} K",
        f"    Final ΔT:     {result.temperature[-1]:.4f} K",
        f"    Max ΔT:       {np.max(np.abs(result.temperature)):.4f} K",
        "=" * 60,
    ]
    return "\n".join(lines)
