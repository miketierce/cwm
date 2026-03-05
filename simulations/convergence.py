"""
Grid Convergence Study for 3D FDTD Wave Solver

Systematically increases grid resolution (N) and measures:
  1. Frequency error vs analytical solution
  2. Damping-rate error vs input η
  3. Wall-clock time scaling (O(N³) DOFs, O(N⁶) per step)

Richardson extrapolation is used to estimate the continuum-limit
values and confirm second-order convergence of the FD scheme.

This addresses ROADMAP Phase 1 item: "Scale grid to N≥20".
"""

import numpy as np
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .resonator_3d import run_3d_simulation, Resonator3DResult


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------
@dataclass
class ConvergencePoint:
    """Single resolution data point."""
    N: int
    dofs: int                       # N³
    f_theory: float
    f_simulated: float
    freq_error_pct: float
    eta_input: float
    eta_measured: float
    eta_error_pct: float
    wall_time_s: float


@dataclass
class ConvergenceStudy:
    """Full convergence study across multiple resolutions."""
    points: List[ConvergencePoint] = field(default_factory=list)
    estimated_order: float = np.nan
    richardson_f: float = np.nan     # Richardson-extrapolated frequency
    label: str = ""

    @property
    def N_values(self) -> np.ndarray:
        return np.array([p.N for p in self.points])

    @property
    def freq_errors(self) -> np.ndarray:
        return np.array([p.freq_error_pct for p in self.points])

    @property
    def eta_errors(self) -> np.ndarray:
        return np.array([p.eta_error_pct for p in self.points])

    @property
    def wall_times(self) -> np.ndarray:
        return np.array([p.wall_time_s for p in self.points])

    @property
    def dofs_array(self) -> np.ndarray:
        return np.array([p.dofs for p in self.points])

    def summary_table(self) -> str:
        lines = [
            f"{'N':>4} {'DOFs':>8} {'f_theory':>12} {'f_sim':>12} "
            f"{'f_err%':>8} {'η_in':>8} {'η_meas':>8} "
            f"{'η_err%':>8} {'time(s)':>8}"
        ]
        lines.append("-" * 88)
        for p in self.points:
            lines.append(
                f"{p.N:>4d} {p.dofs:>8d} {p.f_theory:>12.4f} "
                f"{p.f_simulated:>12.4f} {p.freq_error_pct:>8.3f} "
                f"{p.eta_input:>8.2f} {p.eta_measured:>8.2f} "
                f"{p.eta_error_pct:>8.3f} {p.wall_time_s:>8.2f}"
            )
        lines.append(f"\nEstimated convergence order: {self.estimated_order:.2f}")
        if not np.isnan(self.richardson_f):
            lines.append(f"Richardson-extrapolated frequency: {self.richardson_f:.6f} Hz")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core convergence sweep
# ---------------------------------------------------------------------------
def run_convergence_study(
    N_values: Optional[List[int]] = None,
    L: float = 1.0,
    c: float = 340.0,
    eta: float = 50.0,
    t_max: float = 0.04,
    n_points: int = 4000,
    nx: int = 1, ny: int = 1, nz: int = 1,
    label: str = "3D FD convergence",
) -> ConvergenceStudy:
    """
    Run the 3D FDTD solver at increasing resolutions and measure error.

    Parameters
    ----------
    N_values : list of int
        Interior grid points per dimension. Default [5, 8, 10, 15, 20].
    L : float
        Cubic cavity side length (m).
    c : float
        Wave speed (m/s).
    eta : float
        Damping coefficient (1/s). Set > 0 to also test damping convergence.
    t_max : float
        Simulation duration (s). Must be long enough for FFT resolution.
    n_points : int
        Number of output time steps.
    nx, ny, nz : int
        Mode numbers to excite.

    Returns
    -------
    ConvergenceStudy
    """
    if N_values is None:
        N_values = [5, 8, 10, 15, 20]

    study = ConvergenceStudy(label=label)

    for N in N_values:
        t0 = time.perf_counter()
        result = run_3d_simulation(
            Lx=L, Ly=L, Lz=L, c=c, eta=eta,
            N=N, t_max=t_max, n_points=n_points,
            nx=nx, ny=ny, nz=nz,
            label=f"N={N}",
        )
        wall = time.perf_counter() - t0

        f_err = (abs(result.f_simulated - result.f_theory)
                 / result.f_theory * 100) if result.f_theory > 0 else np.nan

        eta_err = (abs(result.eta_measured - eta)
                   / eta * 100) if eta > 0 else 0.0

        point = ConvergencePoint(
            N=N, dofs=N**3,
            f_theory=result.f_theory, f_simulated=result.f_simulated,
            freq_error_pct=f_err,
            eta_input=eta, eta_measured=result.eta_measured,
            eta_error_pct=eta_err,
            wall_time_s=wall,
        )
        study.points.append(point)

    # Richardson extrapolation using the last two points (assuming order p)
    if len(study.points) >= 2:
        study.estimated_order = _estimate_order(study)
        study.richardson_f = _richardson_extrapolate(study)

    return study


def _estimate_order(study: ConvergenceStudy) -> float:
    """
    Estimate convergence order from three consecutive points using:
      p = log( (e1 - e2) / (e2 - e3) ) / log(h1/h2)

    where e_i is the simulated frequency at resolution i.
    Falls back to two-point log-log slope if only two points.
    """
    pts = study.points
    if len(pts) >= 3:
        # Use last three
        f1, f2, f3 = pts[-3].f_simulated, pts[-2].f_simulated, pts[-1].f_simulated
        h1, h2, h3 = 1.0 / pts[-3].N, 1.0 / pts[-2].N, 1.0 / pts[-1].N

        # Cauchy convergence test
        num = f1 - f2
        den = f2 - f3
        if abs(den) > 1e-12 and abs(num) > 1e-12:
            r = h1 / h2
            p = np.log(abs(num / den)) / np.log(r)
            return max(0.5, min(p, 4.0))  # clamp to reasonable range

    # Two-point fallback: log-log slope of frequency error
    if len(pts) >= 2:
        e1 = abs(pts[-2].f_simulated - pts[-2].f_theory)
        e2 = abs(pts[-1].f_simulated - pts[-1].f_theory)
        h1, h2 = 1.0 / pts[-2].N, 1.0 / pts[-1].N
        if e1 > 1e-12 and e2 > 1e-12 and h1 != h2:
            return np.log(e1 / e2) / np.log(h1 / h2)

    return np.nan


def _richardson_extrapolate(study: ConvergenceStudy) -> float:
    """
    Richardson extrapolation to h→0 using the two finest grids.
    f_exact ≈ f_fine + (f_fine - f_coarse) / (r^p - 1)
    """
    pts = study.points
    if len(pts) < 2:
        return np.nan

    f_coarse = pts[-2].f_simulated
    f_fine = pts[-1].f_simulated
    r = pts[-1].N / pts[-2].N  # refinement ratio
    p = study.estimated_order

    if np.isnan(p) or abs(r**p - 1) < 1e-12:
        return f_fine

    return f_fine + (f_fine - f_coarse) / (r**p - 1)


# ---------------------------------------------------------------------------
# Quick convergence check (lightweight, for tests)
# ---------------------------------------------------------------------------
def quick_convergence_check(
    N_values: List[int] = None,
    L: float = 1.0,
    c: float = 340.0,
    eta: float = 0.0,
) -> Tuple[bool, float]:
    """
    Quick check: does frequency error decrease with N?

    Returns
    -------
    (is_converging, final_error_pct)
    """
    if N_values is None:
        N_values = [5, 8, 12]

    study = run_convergence_study(
        N_values=N_values, L=L, c=c, eta=eta,
        t_max=0.02, n_points=2000,
    )

    errors = study.freq_errors
    is_converging = all(errors[i] >= errors[i + 1] for i in range(len(errors) - 1))
    return is_converging, errors[-1]


# ---------------------------------------------------------------------------
# Anisotropic convergence (stressed cavity)
# ---------------------------------------------------------------------------
def stressed_convergence_study(
    N_values: Optional[List[int]] = None,
    L: float = 1.0,
    c: float = 340.0,
    eta: float = 50.0,
    beta: float = 1.0,
    gamma: float = 0.3,
) -> ConvergenceStudy:
    """
    Convergence study on a stressed (dilated) cavity.
    Lz = L(1 + β·γ), so the grid is anisotropic.
    """
    if N_values is None:
        N_values = [5, 8, 10, 15, 20]

    Lz = L * (1.0 + beta * gamma)

    study = ConvergenceStudy(label=f"Stressed convergence (γ={gamma})")

    for N in N_values:
        t0 = time.perf_counter()
        result = run_3d_simulation(
            Lx=L, Ly=L, Lz=Lz, c=c, eta=eta,
            N=N, t_max=0.04, n_points=4000,
            nx=1, ny=1, nz=1,
            label=f"Stressed N={N}",
        )
        wall = time.perf_counter() - t0

        f_err = (abs(result.f_simulated - result.f_theory)
                 / result.f_theory * 100) if result.f_theory > 0 else np.nan

        eta_err = (abs(result.eta_measured - eta)
                   / eta * 100) if eta > 0 else 0.0

        study.points.append(ConvergencePoint(
            N=N, dofs=N**3,
            f_theory=result.f_theory, f_simulated=result.f_simulated,
            freq_error_pct=f_err,
            eta_input=eta, eta_measured=result.eta_measured,
            eta_error_pct=eta_err,
            wall_time_s=wall,
        ))

    if len(study.points) >= 2:
        study.estimated_order = _estimate_order(study)
        study.richardson_f = _richardson_extrapolate(study)

    return study
