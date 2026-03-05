"""
Experiment 01: Mode Persistence Validation

Research Question:
    How long do resonant eigenmodes persist in 1D and 3D cavities
    under varying damping conditions? Do simulated coherence times
    match theoretical predictions?

Hypothesis:
    Undamped modes persist indefinitely. Under damping η, coherence
    time τ ≈ 1/(2η) for the 1D oscillator. ZIM extends τ by reducing
    effective η.

Methodology:
    1. Sweep damping coefficient η from 0 to 200 (1/s)
    2. For each η, run 1D simulation and measure coherence time
    3. Compare measured τ vs theoretical τ = 1/(2η)
    4. Repeat for ZIM (η reduced by factor 0.5)
    5. Report R² fit and residuals

Claims tested:  Section 5.3 — "ZIM extends coherence by ~2×"
Status:          SIMULATED (computational validation)
"""

import numpy as np
from dataclasses import dataclass
from typing import List

from simulations.resonator_1d import run_1d_simulation, Resonator1DResult
from simulations.common import CavityParams


@dataclass
class ModePeristenceResult:
    """Results from a mode persistence sweep."""
    eta_values: np.ndarray
    coherence_times_normal: np.ndarray
    coherence_times_zim: np.ndarray
    theoretical_times: np.ndarray
    individual_runs: List[Resonator1DResult]


def run_experiment(
    eta_values: np.ndarray = None,
    L: float = 1.0,
    c: float = 340.0,
    c_zim: float = 3.4e4,
    zim_damping_factor: float = 0.5,
    t_max: float = 0.2,
) -> ModePeristenceResult:
    """
    Run mode persistence experiment across a range of damping values.

    Parameters
    ----------
    eta_values : array-like
        Damping coefficients to test. Default: logspace from 1 to 200.
    """
    if eta_values is None:
        eta_values = np.logspace(0, np.log10(200), 20)

    coherence_normal = np.zeros_like(eta_values)
    coherence_zim = np.zeros_like(eta_values)
    theoretical = np.zeros_like(eta_values)
    runs = []

    for i, eta in enumerate(eta_values):
        gamma = eta / 333.333  # Back-derive gamma from eta

        # Normal medium
        r_normal = run_1d_simulation(
            L=L, c=c, gamma=gamma, eta_coefficient=333.333,
            zim=False, t_max=t_max,
            label=f"Normal η={eta:.1f}",
        )
        coherence_normal[i] = r_normal.coherence_time
        runs.append(r_normal)

        # ZIM medium
        r_zim = run_1d_simulation(
            L=L, c=c_zim, gamma=gamma, eta_coefficient=333.333,
            zim=True, zim_damping_factor=zim_damping_factor,
            t_max=t_max,
            label=f"ZIM η={eta:.1f}",
        )
        coherence_zim[i] = r_zim.coherence_time
        runs.append(r_zim)

        # Theory
        theoretical[i] = 1.0 / (2.0 * eta) if eta > 0 else np.inf

    return ModePeristenceResult(
        eta_values=eta_values,
        coherence_times_normal=coherence_normal,
        coherence_times_zim=coherence_zim,
        theoretical_times=theoretical,
        individual_runs=runs,
    )


def summarize(result: ModePeristenceResult) -> str:
    """Generate a text summary of the experiment."""
    lines = [
        "=" * 60,
        "Experiment 01: Mode Persistence Validation",
        "=" * 60,
        f"{'η (1/s)':>10} | {'τ theory':>10} | {'τ normal':>10} | {'τ ZIM':>10} | {'ZIM/Normal':>10}",
        "-" * 60,
    ]
    for i in range(len(result.eta_values)):
        eta = result.eta_values[i]
        t_th = result.theoretical_times[i]
        t_n = result.coherence_times_normal[i]
        t_z = result.coherence_times_zim[i]
        ratio = t_z / t_n if t_n > 0 and not np.isnan(t_n) and not np.isnan(t_z) else np.nan
        lines.append(
            f"{eta:10.1f} | {t_th:10.4f} | {t_n:10.4f} | {t_z:10.4f} | {ratio:10.2f}x"
        )
    lines.append("-" * 60)
    lines.append("PASS criterion: ZIM/Normal ratio ≈ 2.0 (paper claims ~2×)")
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_experiment()
    print(summarize(result))
