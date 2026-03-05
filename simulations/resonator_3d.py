"""
3D Finite-Difference Wave Solver for ZIM-Packed Resonant Chamber

Implements the 3D FDTD extension from WCFOMA paper v9, Section 5.3 / Appendix D.1.

Solves the damped wave equation on a cubic grid:
    ∂²u/∂t² = c² ∇²u - 2η ∂u/∂t

with Dirichlet boundary conditions and finite-difference Laplacian.

Key features:
  - Anisotropic dilatancy (z-direction expansion under x-y shear)
  - Kronecker-product sparse Laplacian for efficiency
  - FFT frequency extraction and Hilbert-envelope damping measurement
  - Comparison of normal vs ZIM media under stress

Limitations (from paper):
  - Coarse grids (N=5) introduce 1-10% discretization errors
  - Scale to N≥20 for convergence; use Meep for full multiphysics
"""

import numpy as np
from scipy.sparse import diags, kron, eye
from scipy.integrate import solve_ivp
from scipy.signal import hilbert
from numpy.fft import fft, fftfreq
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class Resonator3DResult:
    """Result container for a 3D resonator simulation."""
    t: np.ndarray
    u_center: np.ndarray
    f_theory: float
    f_simulated: float
    eta_input: float
    eta_measured: float
    coherence_time: float
    Lx: float
    Ly: float
    Lz: float
    c: float
    N: int
    label: str = ""


def build_laplacian_3d(N: int, dx: float, dy: float, dz: float):
    """
    Build the 3D Laplacian operator via Kronecker products of 1D operators.

    Parameters
    ----------
    N : int
        Number of interior grid points per dimension.
    dx, dy, dz : float
        Grid spacings.

    Returns
    -------
    scipy.sparse matrix (N³ × N³)
    """
    lap1x = diags([1, -2, 1], [-1, 0, 1], shape=(N, N), format='csr') / dx**2
    lap1y = diags([1, -2, 1], [-1, 0, 1], shape=(N, N), format='csr') / dy**2
    lap1z = diags([1, -2, 1], [-1, 0, 1], shape=(N, N), format='csr') / dz**2
    I = eye(N, format='csr')
    lap_x = kron(kron(I, I), lap1x)
    lap_y = kron(kron(I, lap1y), I)
    lap_z = kron(lap1z, kron(I, I))
    return lap_x + lap_y + lap_z


def run_3d_simulation(
    Lx: float = 1.0,
    Ly: float = 1.0,
    Lz: float = 1.0,
    c: float = 340.0,
    eta: float = 0.0,
    N: int = 5,
    t_max: float = 0.02,
    n_points: int = 2000,
    nx: int = 1,
    ny: int = 1,
    nz: int = 1,
    label: str = "",
) -> Resonator3DResult:
    """
    Run a 3D damped wave simulation on a rectangular cavity.

    Parameters
    ----------
    Lx, Ly, Lz : float
        Cavity dimensions (m). Lz is expanded under anisotropic shear.
    c : float
        Wave speed (m/s).
    eta : float
        Damping coefficient (1/s).
    N : int
        Interior grid points per dimension (total DOFs = N³).
    t_max : float
        Simulation time (s).
    n_points : int
        Time steps for output.
    nx, ny, nz : int
        Mode numbers to excite.
    label : str
        Run identifier.

    Returns
    -------
    Resonator3DResult
    """
    dx = Lx / (N + 1)
    dy = Ly / (N + 1)
    dz = Lz / (N + 1)
    lap = build_laplacian_3d(N, dx, dy, dz)
    size = N**3

    # Initial condition: standing wave mode (nx, ny, nz)
    ii, jj, kk = np.mgrid[1:N+1, 1:N+1, 1:N+1]
    x = ii * dx
    y = jj * dy
    z = kk * dz
    u0 = (np.sin(np.pi * nx * x / Lx) *
           np.sin(np.pi * ny * y / Ly) *
           np.sin(np.pi * nz * z / Lz))
    u0 = u0.flatten()
    v0 = np.zeros(size)
    y0 = np.concatenate((u0, v0))

    # ODE: dy/dt = [v, c²·Lap·u - 2η·v]
    def ode(t, y):
        u = y[:size]
        v = y[size:]
        du = v
        dv = c**2 * lap.dot(u) - 2.0 * eta * v
        return np.concatenate((du, dv))

    t_eval = np.linspace(0, t_max, n_points)
    sol = solve_ivp(ode, (0, t_max), y0, method='RK45',
                    t_eval=t_eval, rtol=1e-5)

    # Extract center-point displacement
    ic = N // 2
    idx = ic * N**2 + ic * N + ic
    u_center = sol.y[idx]

    # Theoretical frequency
    f_theory = (c / 2.0) * np.sqrt(
        (nx / Lx)**2 + (ny / Ly)**2 + (nz / Lz)**2
    )

    # Simulated frequency via FFT
    spec = fft(u_center)
    freqs = fftfreq(len(t_eval), t_eval[1] - t_eval[0])
    pos_mask = freqs > 0
    if pos_mask.any():
        f_sim = freqs[pos_mask][np.argmax(np.abs(spec[pos_mask]))]
    else:
        f_sim = np.nan

    # Damping measurement via Hilbert envelope
    if eta > 0:
        analytic_signal = hilbert(u_center - u_center.mean())
        env = np.abs(analytic_signal)
        log_env = np.log(env + 1e-30)
        mask = env > env.max() * 0.1
        if mask.sum() > 10:
            slope = np.polyfit(sol.t[mask], log_env[mask], 1)[0]
            eta_meas = -slope
            coh_time = 1.0 / eta_meas if eta_meas > 0 else np.inf
        else:
            eta_meas = np.nan
            coh_time = np.nan
    else:
        eta_meas = 0.0
        coh_time = np.inf

    return Resonator3DResult(
        t=sol.t, u_center=u_center,
        f_theory=f_theory, f_simulated=f_sim,
        eta_input=eta, eta_measured=eta_meas,
        coherence_time=coh_time,
        Lx=Lx, Ly=Ly, Lz=Lz, c=c, N=N,
        label=label,
    )


def run_standard_3d_comparison(
    L: float = 1.0,
    c_normal: float = 340.0,
    c_zim: float = 3.4e4,
    beta: float = 1.0,
    gamma: float = 0.3,
    eta_base: float = 100.0,
    N: int = 5,
    t_max: float = 0.02,
) -> dict:
    """
    Run the four standard 3D comparison cases from the paper.
    Returns dict of label -> Resonator3DResult.
    """
    Lz_stressed = L * (1.0 + beta * gamma)

    cases = {
        "Normal (no stress)":  dict(Lz=L, c=c_normal, eta=0.0),
        "Normal (stressed)":   dict(Lz=Lz_stressed, c=c_normal, eta=eta_base),
        "ZIM (no stress)":     dict(Lz=L, c=c_zim, eta=0.0),
        "ZIM (stressed)":      dict(Lz=Lz_stressed, c=c_zim, eta=eta_base / 2.0),
    }

    results = {}
    for label, kwargs in cases.items():
        results[label] = run_3d_simulation(
            Lx=L, Ly=L, N=N, t_max=t_max, label=label, **kwargs,
        )
    return results
