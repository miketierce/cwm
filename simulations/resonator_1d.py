"""
1D Damped Oscillator Model of a ZIM-Packed Resonant Chamber

Implements the simulation from WCFOMA paper v9, Section 5.3 and Appendix D.

Model equation:  ẍ + 2η ẋ + ω² x = 0

Under dilatancy (shear strain γ):
  - Cavity length dilates:  L' = L(1 + β·γ)
  - Viscous damping:        η = 333.333·γ  (ZIM halves η)
  - Frequency shifts:       f = n·c / (2·L')

Key findings from paper:
  - Frequency drops ~33% under max shear (γ=0.5)
  - ZIM extends coherence by ~2× under stress
  - Frequency drift provides tamper detection signal
"""

import numpy as np
from scipy.integrate import odeint
from scipy.signal import hilbert
from numpy.fft import fft, fftfreq
from dataclasses import dataclass
from typing import Tuple, Optional

from .common import CavityParams, DilatancyParams


@dataclass
class Resonator1DResult:
    """Result container for a 1D resonator simulation."""
    t: np.ndarray
    x: np.ndarray
    v: np.ndarray
    f_theory: float
    f_simulated: float
    eta_input: float
    eta_measured: float
    coherence_time: float   # 1/e decay time (s); inf if undamped
    label: str = ""


def damped_oscillator(y, t, omega, eta):
    """
    ODE system for damped harmonic oscillator.
    y = [x, dx/dt]
    dy/dt = [dx/dt, -2η·dx/dt - ω²·x]
    """
    return [y[1], -2.0 * eta * y[1] - omega**2 * y[0]]


def compute_frequency(L: float, c: float, gamma: float = 0.0,
                      beta: float = 1.0, n: int = 1) -> float:
    """
    Resonant frequency for mode n in a dilated cavity.
    f = n * c / (2 * L'), where L' = L(1 + β·γ)
    """
    L_prime = L * (1.0 + beta * gamma)
    return n * c / (2.0 * L_prime)


def run_1d_simulation(
    L: float = 1.0,
    c: float = 340.0,
    gamma: float = 0.0,
    beta: float = 1.0,
    eta_coefficient: float = 333.333,
    zim: bool = False,
    zim_damping_factor: float = 0.5,
    n_mode: int = 1,
    t_max: float = 0.1,
    n_points: int = 10000,
    x0: float = 1.0,
    v0: float = 0.0,
    label: str = "",
) -> Resonator1DResult:
    """
    Run a single 1D damped oscillator simulation.

    Parameters
    ----------
    L : float
        Base cavity length (m).
    c : float
        Wave speed (m/s). Use c_zim for ZIM simulations.
    gamma : float
        Applied shear strain.
    beta : float
        Dilation coefficient.
    eta_coefficient : float
        Damping rate per unit shear.
    zim : bool
        If True, apply ZIM damping reduction.
    zim_damping_factor : float
        Factor by which ZIM reduces damping.
    n_mode : int
        Mode number to excite.
    t_max : float
        Simulation duration (s).
    n_points : int
        Number of time steps.
    x0, v0 : float
        Initial displacement and velocity.
    label : str
        Human-readable label for this run.

    Returns
    -------
    Resonator1DResult
    """
    # Compute parameters
    eta = eta_coefficient * gamma
    if zim:
        eta *= zim_damping_factor

    f_theory = compute_frequency(L, c, gamma, beta, n_mode)
    omega = 2.0 * np.pi * f_theory

    # Time integration
    t = np.linspace(0, t_max, n_points)
    y0 = [x0, v0]
    sol = odeint(damped_oscillator, y0, t, args=(omega, eta))
    x = sol[:, 0]
    v = sol[:, 1]

    # Measure simulated frequency via FFT
    spectrum = fft(x)
    freqs = fftfreq(len(t), t[1] - t[0])
    pos_mask = freqs > 0
    if pos_mask.any():
        f_sim = freqs[pos_mask][np.argmax(np.abs(spectrum[pos_mask]))]
    else:
        f_sim = np.nan

    # Measure damping via Hilbert envelope
    if eta > 0:
        analytic_signal = hilbert(x - x.mean())
        envelope = np.abs(analytic_signal)
        log_env = np.log(envelope + 1e-30)
        mask = envelope > envelope.max() * 0.1
        if mask.sum() > 10:
            slope = np.polyfit(t[mask], log_env[mask], 1)[0]
            eta_measured = -slope
            coherence_time = 1.0 / eta_measured if eta_measured > 0 else np.inf
        else:
            eta_measured = np.nan
            coherence_time = np.nan
    else:
        eta_measured = 0.0
        coherence_time = np.inf

    return Resonator1DResult(
        t=t, x=x, v=v,
        f_theory=f_theory, f_simulated=f_sim,
        eta_input=eta, eta_measured=eta_measured,
        coherence_time=coherence_time,
        label=label,
    )


def run_standard_comparison(
    params: Optional[CavityParams] = None,
    t_max: float = 0.1,
) -> dict:
    """
    Run the four standard comparison cases from the paper:
      1. Normal, no stress
      2. Normal, stressed (γ=0.3)
      3. ZIM, no stress
      4. ZIM, stressed (γ=0.3)

    Returns dict of label -> Resonator1DResult.
    """
    if params is None:
        params = CavityParams()

    d = params.dilatancy
    cases = {
        "Normal (no stress)": dict(
            c=params.c_normal, gamma=0.0, zim=False),
        "Normal (stressed)": dict(
            c=params.c_normal, gamma=d.gamma, zim=False),
        "ZIM (no stress)": dict(
            c=params.c_zim, gamma=0.0, zim=True),
        "ZIM (stressed)": dict(
            c=params.c_zim, gamma=d.gamma, zim=True),
    }

    results = {}
    for label, kwargs in cases.items():
        results[label] = run_1d_simulation(
            L=params.L,
            beta=d.beta,
            eta_coefficient=d.eta_coefficient,
            zim_damping_factor=d.zim_damping_factor,
            t_max=t_max,
            label=label,
            **kwargs,
        )
    return results
