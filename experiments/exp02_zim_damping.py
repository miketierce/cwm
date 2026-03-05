"""
Experiment 02: ZIM Damping Reduction Quantification

Research Question:
    Does ZIM integration reduce damping under mechanical stress
    by the claimed factor of 2×? What is the actual relationship
    between ZIM properties and effective damping?

Hypothesis:
    ZIM reduces effective damping by flattening phase profiles
    and minimizing boundary-induced losses. The paper assumes a
    factor of 0.5 — this experiment measures the actual ratio
    across stress levels.

Methodology:
    1. Sweep shear strain γ from 0 to 0.5
    2. For each γ, run paired Normal/ZIM 1D simulations
    3. Measure coherence time ratio τ_ZIM / τ_Normal
    4. Repeat with 3D solver to check dimensionality effects
    5. Test sensitivity to assumed ZIM damping factor (0.3–0.7)

Claims tested:  Section 5.3 — "50% reduced loss" / "~2× coherence"
Status:          SIMULATED (needs experimental validation)
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict

from simulations.resonator_1d import run_1d_simulation
from simulations.resonator_3d import run_3d_simulation


@dataclass
class ZIMDampingResult:
    """Results from ZIM damping experiment."""
    gamma_values: np.ndarray
    coherence_ratio_1d: np.ndarray
    coherence_ratio_3d: np.ndarray
    freq_drift_normal: np.ndarray
    freq_drift_zim: np.ndarray


def run_experiment(
    gamma_values: np.ndarray = None,
    L: float = 1.0,
    c_normal: float = 340.0,
    c_zim: float = 3.4e4,
    zim_damping_factor: float = 0.5,
    run_3d: bool = True,
    N_3d: int = 5,
) -> ZIMDampingResult:
    """Run ZIM damping reduction experiment."""
    if gamma_values is None:
        gamma_values = np.linspace(0.05, 0.5, 10)

    n_pts = len(gamma_values)
    ratio_1d = np.zeros(n_pts)
    ratio_3d = np.zeros(n_pts)
    drift_normal = np.zeros(n_pts)
    drift_zim = np.zeros(n_pts)

    # Baseline frequencies (no stress)
    f0_normal = c_normal / (2.0 * L)
    f0_zim = c_zim / (2.0 * L)

    for i, gamma in enumerate(gamma_values):
        # 1D comparison
        r_n = run_1d_simulation(
            L=L, c=c_normal, gamma=gamma,
            zim=False, t_max=0.1,
        )
        r_z = run_1d_simulation(
            L=L, c=c_zim, gamma=gamma,
            zim=True, zim_damping_factor=zim_damping_factor,
            t_max=0.1,
        )

        if r_n.coherence_time > 0 and not np.isnan(r_n.coherence_time):
            ratio_1d[i] = r_z.coherence_time / r_n.coherence_time
        else:
            ratio_1d[i] = np.nan

        drift_normal[i] = abs(r_n.f_theory - f0_normal) / f0_normal * 100
        drift_zim[i] = abs(r_z.f_theory - f0_zim) / f0_zim * 100

        # 3D comparison (optional, slow)
        if run_3d:
            beta = 1.0
            Lz_s = L * (1.0 + beta * gamma)
            eta_base = 333.333 * gamma

            r3_n = run_3d_simulation(
                Lx=L, Ly=L, Lz=Lz_s, c=c_normal,
                eta=eta_base, N=N_3d, t_max=0.02,
            )
            r3_z = run_3d_simulation(
                Lx=L, Ly=L, Lz=Lz_s, c=c_zim,
                eta=eta_base * zim_damping_factor,
                N=N_3d, t_max=0.02,
            )

            if (r3_n.coherence_time > 0 and not np.isnan(r3_n.coherence_time)):
                ratio_3d[i] = r3_z.coherence_time / r3_n.coherence_time
            else:
                ratio_3d[i] = np.nan

    return ZIMDampingResult(
        gamma_values=gamma_values,
        coherence_ratio_1d=ratio_1d,
        coherence_ratio_3d=ratio_3d,
        freq_drift_normal=drift_normal,
        freq_drift_zim=drift_zim,
    )


def summarize(result: ZIMDampingResult) -> str:
    """Generate text summary."""
    lines = [
        "=" * 70,
        "Experiment 02: ZIM Damping Reduction",
        "=" * 70,
        f"{'γ':>8} | {'τ_ZIM/τ_N (1D)':>15} | {'τ_ZIM/τ_N (3D)':>15} | "
        f"{'Drift_N (%)':>12} | {'Drift_Z (%)':>12}",
        "-" * 70,
    ]
    for i in range(len(result.gamma_values)):
        lines.append(
            f"{result.gamma_values[i]:8.3f} | "
            f"{result.coherence_ratio_1d[i]:15.2f} | "
            f"{result.coherence_ratio_3d[i]:15.2f} | "
            f"{result.freq_drift_normal[i]:12.1f} | "
            f"{result.freq_drift_zim[i]:12.1f}"
        )
    lines.append("-" * 70)
    mean_ratio = np.nanmean(result.coherence_ratio_1d)
    lines.append(f"Mean 1D coherence ratio: {mean_ratio:.2f}× (paper claims ~2×)")
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_experiment(run_3d=False)  # Fast mode
    print(summarize(result))
