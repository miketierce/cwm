"""Mathieu–Floquet parametric mode amplification (Sidebar 16).

Hypotheses
----------
H-PM1  Parametric gain ≥ 10 dB at ε < 0.1 in first Mathieu instability tongue.
H-PM2  Mode selectivity: < 1 dB gain at neighbouring modes f_{n±1}.
H-PM3  Mathieu stability chart predicts ε_max within ± 20 % of numerical threshold.
H-PM4  Parametric + CW readout achieves ≥ 6 dB SNR improvement over CW alone.

Each experiment returns a typed dataclass; ``run_all_mathieu`` collects and
summarises results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .common import C_FERROFLUID, K_B

# ---------------------------------------------------------------------------
# Physical constants & defaults
# ---------------------------------------------------------------------------

_L_DEFAULT: float = 1e-5       # cavity length [m] (10 µm)
_Q_DEFAULT: float = 500.0      # default quality factor
_T_DEFAULT: float = 300.0      # ambient temperature [K]
_F_FUND: float = C_FERROFLUID / (2.0 * _L_DEFAULT)   # fundamental freq [Hz]
_V_BAR: float = 5315.0        # borosilicate bar wave speed [m/s]

# ---------------------------------------------------------------------------
# Core physics helpers
# ---------------------------------------------------------------------------


def _mode_frequency(n: int, L: float = _L_DEFAULT,
                    c: float = C_FERROFLUID) -> float:
    """Eigenfrequency of mode n: f_n = n·c/(2L)."""
    return n * c / (2.0 * L)


def _parametric_gain_rate(epsilon: float, omega: float,
                          Q: float) -> float:
    """Exponential growth rate inside first Mathieu instability tongue.

    γ = ε·ω/(4) − ω/(2Q)

    Positive γ means amplification; negative means the intrinsic damping
    exceeds the parametric energy injection.
    """
    return epsilon * omega / 4.0 - omega / (2.0 * Q)


def _epsilon_threshold(Q: float) -> float:
    """Critical modulation depth for onset of parametric amplification.

    At the boundary γ = 0: ε_min = 2/Q.
    """
    return 2.0 / Q


def _parametric_gain_below_threshold(epsilon: float, Q: float) -> float:
    """Steady-state parametric gain factor below oscillation threshold.

    G = 1 / (1 − ε·Q/2)

    Valid for ε < 2/Q. At threshold G → ∞.
    """
    x = epsilon * Q / 2.0
    if x >= 1.0:
        return np.inf
    return 1.0 / (1.0 - x)


def _parametric_gain_db(epsilon: float, Q: float) -> float:
    """Parametric gain in dB (power gain = G²)."""
    G = _parametric_gain_below_threshold(epsilon, Q)
    if np.isinf(G):
        return np.inf
    return 20.0 * np.log10(max(G, 1e-30))


def _instability_tongue_width(epsilon: float, omega: float) -> float:
    """Half-width of first Mathieu instability tongue in frequency.

    Δω/ω_n ≈ ε/2  →  Δf = ε·f_n/2
    """
    f = omega / (2.0 * np.pi)
    return epsilon * f / 2.0


def _fsr(L: float = _L_DEFAULT, c: float = C_FERROFLUID) -> float:
    """Free spectral range: FSR = c/(2L)."""
    return c / (2.0 * L)


def _pump_power_per_mode(omega: float, Q: float, T: float = _T_DEFAULT,
                         epsilon: float = 0.01) -> float:
    """Estimated pump power for parametric amplification [W].

    The pump modulates the effective stiffness at 2ω.  The power required
    to maintain modulation depth ε is comparable to the stored energy times
    the modulation rate:

        P_pump ≈ ε · ω · E_stored / Q

    where E_stored = k_B T (thermal equilibrium per mode).
    """
    E_stored = K_B * T
    return epsilon * omega * E_stored / Q


def _time_domain_mathieu(epsilon: float, omega: float, Q: float,
                         n_cycles: int = 200) -> tuple:
    """Integrate damped Mathieu equation numerically.

    ẍ + (ω/Q)ẋ + ω²(1 + ε cos 2ωt) x = 0

    Uses RK4 for accuracy.

    Returns (t_array, x_array, v_array).
    """
    dt = 2.0 * np.pi / omega / 80.0  # 80 steps per period
    n_steps = int(n_cycles * 2.0 * np.pi / omega / dt)
    n_steps = max(n_steps, 100)

    t = np.zeros(n_steps)
    x = np.zeros(n_steps)
    v = np.zeros(n_steps)

    x[0] = 1.0
    v[0] = 0.0
    gamma_damp = omega / Q  # 2 * (ω/(2Q))

    def deriv(ti, xi, vi):
        omega_sq_eff = omega ** 2 * (1.0 + epsilon * np.cos(2.0 * omega * ti))
        ax = -omega_sq_eff * xi - gamma_damp * vi
        return vi, ax

    for i in range(n_steps - 1):
        ti = i * dt
        # RK4
        k1v, k1a = deriv(ti, x[i], v[i])
        k2v, k2a = deriv(ti + dt / 2, x[i] + k1v * dt / 2, v[i] + k1a * dt / 2)
        k3v, k3a = deriv(ti + dt / 2, x[i] + k2v * dt / 2, v[i] + k2a * dt / 2)
        k4v, k4a = deriv(ti + dt, x[i] + k3v * dt, v[i] + k3a * dt)

        x[i + 1] = x[i] + dt * (k1v + 2 * k2v + 2 * k3v + k4v) / 6
        v[i + 1] = v[i] + dt * (k1a + 2 * k2a + 2 * k3a + k4a) / 6
        t[i + 1] = ti + dt

    return t, x, v


def _measure_gain_from_timeseries(x: np.ndarray, omega: float,
                                  dt: float) -> float:
    """Extract effective gain by comparing envelope at end vs start.

    Computes the ratio of RMS amplitude in the last 10 cycles to the
    first 10 cycles.
    """
    period_samples = int(2.0 * np.pi / omega / dt)
    window = max(10 * period_samples, 1)

    if len(x) < 2 * window:
        return 1.0

    rms_start = np.sqrt(np.mean(x[:window] ** 2))
    rms_end = np.sqrt(np.mean(x[-window:] ** 2))

    if rms_start < 1e-30:
        return 0.0
    return rms_end / rms_start


def _numerical_epsilon_threshold(omega: float, Q: float,
                                 n_cycles: int = 1000,
                                 tol: float = 0.002) -> float:
    """Find ε_threshold numerically via bisection on Mathieu integration.

    The threshold is the smallest ε where the envelope grows (gain > 1).
    """
    eps_lo, eps_hi = 0.0, min(0.5, 10.0 / Q)

    for _ in range(40):
        eps_mid = (eps_lo + eps_hi) / 2.0
        t, x, v = _time_domain_mathieu(eps_mid, omega, Q, n_cycles)
        dt = t[1] - t[0] if len(t) > 1 else 1.0
        g = _measure_gain_from_timeseries(x, omega, dt)
        if g > 1.0 + tol:
            eps_hi = eps_mid
        else:
            eps_lo = eps_mid

    return (eps_lo + eps_hi) / 2.0


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ParametricGainResult:
    """H-PM1: Parametric gain at modulation depth ε."""
    epsilon: float               # modulation depth
    Q: float
    gain_db: float               # parametric gain [dB]
    gain_linear: float           # amplitude gain factor
    pump_power_fW: float         # pump power [fW]
    bekesy_power_fW: float       # Békésy feedback power [fW] for comparison
    n_mode: int
    freq_hz: float
    verdict: bool                # True → CONFIRMED (gain ≥ 10 dB)


@dataclass
class ModeSelectivityResult:
    """H-PM2: Mode selectivity of parametric drive."""
    n_target: int                # target mode
    gain_target_db: float        # gain at target mode
    gain_neighbour_max_db: float # max gain at n±1
    tongue_width_hz: float       # instability tongue half-width
    fsr_hz: float                # free spectral range
    selectivity_ratio: float     # FSR / tongue_width
    verdict: bool                # True → CONFIRMED (neighbour gain < 1 dB)


@dataclass
class StabilityBoundaryResult:
    """H-PM3: Stability boundary prediction accuracy."""
    epsilon_predicted: float     # analytic ε_min = 2/Q
    epsilon_numerical: float     # numerically determined threshold
    deviation_percent: float     # |predicted − numerical| / numerical × 100
    Q: float
    freq_hz: float
    verdict: bool                # True → CONFIRMED (deviation ≤ 20 %)


@dataclass
class ParametricCWResult:
    """H-PM4: Parametric + CW readout SNR improvement."""
    snr_cw_only_db: float        # CW lock-in SNR [dB]
    snr_parametric_cw_db: float  # CW + parametric [dB]
    improvement_db: float        # difference
    parametric_gain_db: float    # parametric gain alone
    t_integration: float         # CW integration time [s]
    verdict: bool                # True → CONFIRMED (improvement ≥ 6 dB)


@dataclass
class MathieuParametricSummary:
    """Aggregate results from all four experiments."""
    gain: ParametricGainResult
    selectivity: ModeSelectivityResult
    stability: StabilityBoundaryResult
    parametric_cw: ParametricCWResult
    confirmed: int
    killed: int


# ---------------------------------------------------------------------------
# Experiment functions
# ---------------------------------------------------------------------------


def exp_parametric_gain(
    n_mode: int = 5,
    epsilon: float = 0.003,
    Q: float = _Q_DEFAULT,
    L: float = _L_DEFAULT,
    T: float = _T_DEFAULT,
) -> ParametricGainResult:
    """H-PM1 — Parametric gain vs Békésy feedback.

    Compute the steady-state parametric gain for mode n at modulation
    depth ε, and compare the required pump power to Békésy's feedback
    power (H-B3).
    """
    f_n = _mode_frequency(n_mode, L)
    omega_n = 2.0 * np.pi * f_n

    # Parametric gain (analytic, below threshold)
    gain_linear = _parametric_gain_below_threshold(epsilon, Q)
    gain_db = _parametric_gain_db(epsilon, Q)

    # Pump power
    p_pump = _pump_power_per_mode(omega_n, Q, T, epsilon)
    p_pump_fW = p_pump * 1e15

    # Békésy comparison: feedback power for 2× Q-boost
    # P_bekesy ≈ ω · k_B·T · (1/Q − 1/(2Q)) = ω · k_B·T / (2Q)
    p_bekesy = omega_n * K_B * T / (2.0 * Q)
    p_bekesy_fW = p_bekesy * 1e15

    return ParametricGainResult(
        epsilon=epsilon,
        Q=Q,
        gain_db=gain_db,
        gain_linear=gain_linear,
        pump_power_fW=p_pump_fW,
        bekesy_power_fW=p_bekesy_fW,
        n_mode=n_mode,
        freq_hz=f_n,
        verdict=bool(gain_db >= 10.0),
    )


def exp_mode_selectivity(
    n_target: int = 5,
    epsilon: float = 0.003,
    Q: float = _Q_DEFAULT,
    L: float = _L_DEFAULT,
) -> ModeSelectivityResult:
    """H-PM2 — Selectivity of parametric drive at 2f_n.

    The instability tongue has width Δf ≈ ε·f_n/2.  For mode selectivity,
    we need Δf < FSR = c/(2L).  When the pump is tuned to 2f_n, the
    detuning to mode n±1 is FSR, so the gain at the neighbour is:

        G_neighbour = 1 / |1 − ε·Q/2 · sinc(π·FSR/Δf_tongue)|

    For FSR ≫ Δf_tongue, G_neighbour ≈ 1 (0 dB).
    """
    f_target = _mode_frequency(n_target, L)
    omega_target = 2.0 * np.pi * f_target
    fsr = _fsr(L)

    # Gain at target mode
    gain_target_db = _parametric_gain_db(epsilon, Q)

    # Tongue half-width
    tongue_hz = _instability_tongue_width(epsilon, omega_target)

    # Detuning of neighbouring modes from the pump resonance
    # Pump is at 2f_target; neighbour n±1 has 2f_{n±1} = 2(f_target ± fsr)
    # Detuning = 2·FSR from the pump frequency → Δω = 2π·fsr from ω_target
    # The parametric response rolls off as the detuning exceeds the tongue width.
    # Effective ε for neighbour: ε_eff = ε · tongue_hz² / (tongue_hz² + fsr²)
    # (Lorentzian roll-off of Mathieu tongue)
    eps_eff = epsilon * tongue_hz ** 2 / (tongue_hz ** 2 + fsr ** 2)
    gain_neighbour_db = _parametric_gain_db(eps_eff, Q)

    selectivity = fsr / max(tongue_hz, 1e-30)

    return ModeSelectivityResult(
        n_target=n_target,
        gain_target_db=gain_target_db,
        gain_neighbour_max_db=gain_neighbour_db,
        tongue_width_hz=tongue_hz,
        fsr_hz=fsr,
        selectivity_ratio=selectivity,
        verdict=bool(gain_neighbour_db < 1.0),
    )


def exp_stability_boundary(
    Q: float = _Q_DEFAULT,
    L: float = _L_DEFAULT,
    n_mode: int = 5,
    n_cycles: int = 500,
) -> StabilityBoundaryResult:
    """H-PM3 — Analytic vs numerical stability boundary.

    Compare the analytic threshold ε_min = 2/Q with the numerically
    determined threshold from direct Mathieu equation integration.
    """
    f_n = _mode_frequency(n_mode, L)
    omega_n = 2.0 * np.pi * f_n

    eps_predicted = _epsilon_threshold(Q)
    eps_numerical = _numerical_epsilon_threshold(omega_n, Q, n_cycles)

    deviation = abs(eps_predicted - eps_numerical) / max(eps_numerical, 1e-30) * 100.0

    return StabilityBoundaryResult(
        epsilon_predicted=eps_predicted,
        epsilon_numerical=eps_numerical,
        deviation_percent=deviation,
        Q=Q,
        freq_hz=f_n,
        verdict=bool(deviation <= 20.0),
    )


def exp_parametric_cw_readout(
    n_mode: int = 5,
    epsilon: float = 0.003,
    Q: float = _Q_DEFAULT,
    L: float = _L_DEFAULT,
    T: float = _T_DEFAULT,
    t_integration: float = 1e-3,
) -> ParametricCWResult:
    """H-PM4 — Parametric amplification combined with CW lock-in readout.

    CW readout alone gains SNR through coherent averaging over t_int.
    Adding parametric amplification pre-amplifies the mode amplitude before
    readout, giving a compound improvement.

    CW SNR gain (power) = t_eff / τ  where τ = Q/(πf_n)
    Parametric gain (power) = G² where G = 1/(1 − εQ/2)
    Combined improvement = 10·log10(G²) dB above CW-only baseline
    """
    f_n = _mode_frequency(n_mode, L)
    omega_n = 2.0 * np.pi * f_n
    tau = Q / (np.pi * f_n)

    # CW-only SNR: baseline from thermal noise
    # SNR_impulse = E_signal / E_thermal, both ≈ k_B·T → SNR_impulse ~ 1 (0 dB)
    # CW gain = t_int / τ (power)
    cw_gain_power = t_integration / tau
    snr_cw_db = 10.0 * np.log10(max(cw_gain_power, 1e-30))

    # Parametric pre-amplification gain
    G = _parametric_gain_below_threshold(epsilon, Q)
    par_gain_power = G ** 2
    par_gain_db = 10.0 * np.log10(max(par_gain_power, 1e-30))

    # Combined: parametric amplifies signal before CW averaging
    snr_combined_db = snr_cw_db + par_gain_db

    improvement = snr_combined_db - snr_cw_db  # = par_gain_db

    return ParametricCWResult(
        snr_cw_only_db=snr_cw_db,
        snr_parametric_cw_db=snr_combined_db,
        improvement_db=improvement,
        parametric_gain_db=par_gain_db,
        t_integration=t_integration,
        verdict=bool(improvement >= 6.0),
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_all_mathieu(verbose: bool = True) -> MathieuParametricSummary:
    """Execute all four Mathieu–Floquet experiments and summarise."""

    if verbose:
        print("=" * 72)
        print("  S16 — Mathieu & Floquet: Parametric Mode Amplification")
        print("=" * 72)

    # H-PM1 — Parametric gain
    r1 = exp_parametric_gain()
    if verbose:
        tag = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"\n[H-PM1] Parametric gain at ε = {r1.epsilon}:")
        print(f"  Gain: {r1.gain_db:.2f} dB (linear: {r1.gain_linear:.2f}×)")
        print(f"  Pump power:   {r1.pump_power_fW:.4f} fW/mode")
        print(f"  Békésy power: {r1.bekesy_power_fW:.4f} fW/mode")
        print(f"  Mode {r1.n_mode} at {r1.freq_hz/1e6:.3f} MHz")
        print(f"  → {tag}")

    # H-PM2 — Mode selectivity
    r2 = exp_mode_selectivity()
    if verbose:
        tag = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"\n[H-PM2] Mode selectivity (target mode {r2.n_target}):")
        print(f"  Target gain:    {r2.gain_target_db:.2f} dB")
        print(f"  Neighbour gain: {r2.gain_neighbour_max_db:.4f} dB")
        print(f"  Tongue width:   {r2.tongue_width_hz:.1f} Hz")
        print(f"  FSR:            {r2.fsr_hz:.1f} Hz")
        print(f"  Selectivity:    {r2.selectivity_ratio:.1f}×")
        print(f"  → {tag}")

    # H-PM3 — Stability boundary
    r3 = exp_stability_boundary()
    if verbose:
        tag = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"\n[H-PM3] Stability boundary prediction:")
        print(f"  ε_predicted (2/Q): {r3.epsilon_predicted:.6f}")
        print(f"  ε_numerical:       {r3.epsilon_numerical:.6f}")
        print(f"  Deviation:         {r3.deviation_percent:.1f}%")
        print(f"  → {tag}")

    # H-PM4 — Parametric + CW readout
    r4 = exp_parametric_cw_readout()
    if verbose:
        tag = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"\n[H-PM4] Parametric + CW readout:")
        print(f"  CW-only SNR:       {r4.snr_cw_only_db:.2f} dB")
        print(f"  Parametric + CW:   {r4.snr_parametric_cw_db:.2f} dB")
        print(f"  Improvement:       {r4.improvement_db:.2f} dB")
        print(f"  Parametric gain:   {r4.parametric_gain_db:.2f} dB")
        print(f"  → {tag}")

    # Summary
    verdicts = [r1.verdict, r2.verdict, r3.verdict, r4.verdict]
    confirmed = sum(verdicts)
    killed = len(verdicts) - confirmed

    if verbose:
        print("\n" + "-" * 72)
        print(f"  Summary: {confirmed} confirmed, {killed} killed")
        labels = ["H-PM1", "H-PM2", "H-PM3", "H-PM4"]
        for lbl, v in zip(labels, verdicts):
            print(f"    {lbl}: {'CONFIRMED' if v else 'KILLED'}")
        print("-" * 72)

    return MathieuParametricSummary(
        gain=r1,
        selectivity=r2,
        stability=r3,
        parametric_cw=r4,
        confirmed=confirmed,
        killed=killed,
    )


if __name__ == "__main__":
    run_all_mathieu()
