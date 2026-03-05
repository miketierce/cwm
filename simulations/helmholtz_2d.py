"""
2D Helmholtz Eigenvalue Solver for Geometry-Invariant Resonant Cavities

Implements the geometry-invariant extension from WCFOMA paper v9, Section 5.3.

Solves:  -∇·((1/ε) ∇u) = k² u

with Neumann boundary conditions (∂u/∂n = 0), modeling ZIM/ENZ host media
with dielectric particle inclusions.

Key features:
  - ENZ (epsilon-near-zero) host with controllable loss
  - Dielectric particle inclusion (configurable position/radius)
  - Geometry stretching to simulate dilatancy deformation
  - Eigenvalue extraction via sparse solver

Reference: Nature Communications 6, 10989 (2016) — geometry-invariant cavities
"""

import numpy as np
from scipy.sparse import lil_matrix, eye
from scipy.sparse.linalg import eigs
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class HelmholtzResult:
    """Result container for 2D Helmholtz eigenvalue analysis."""
    eigenvalues_k2: np.ndarray    # k² values (real parts)
    frequencies: np.ndarray        # Derived frequencies (Hz)
    eps_grid: np.ndarray           # Permittivity map used
    Lx: float
    Ly: float
    Nx: int
    Ny: int
    label: str = ""


@dataclass
class CavityGeometry:
    """Geometry specification for a 2D cavity with inclusions."""
    Lx: float = 1.0               # Cavity width (m)
    Ly: float = 1.0               # Cavity height (m)
    eps_host: complex = 0.01 + 0.001j   # ENZ host permittivity (lossy)
    eps_particle: float = 11.7     # Dielectric particle permittivity
    particle_center: Tuple[float, float] = (0.5, 0.5)
    particle_radius: float = 0.2   # Particle radius (m)


def build_epsilon_grid(
    geom: CavityGeometry,
    Nx: int = 10,
    Ny: int = 10,
) -> Tuple[np.ndarray, float, float]:
    """
    Build a 2D permittivity grid with ENZ host and dielectric inclusion.

    Returns
    -------
    eps_grid : ndarray (Nx, Ny), complex
    dx, dy : float
    """
    dx = geom.Lx / (Nx - 1) if Nx > 1 else geom.Lx
    dy = geom.Ly / (Ny - 1) if Ny > 1 else geom.Ly

    eps_grid = np.full((Nx, Ny), geom.eps_host, dtype=complex)

    cx, cy = geom.particle_center
    for i in range(Nx):
        for j in range(Ny):
            x = i * dx
            y = j * dy
            if (x - cx)**2 + (y - cy)**2 < geom.particle_radius**2:
                eps_grid[i, j] = geom.eps_particle

    return eps_grid, dx, dy


def build_helmholtz_operator(
    Nx: int,
    Ny: int,
    dx: float,
    dy: float,
    eps_grid: np.ndarray,
):
    """
    Build the Helmholtz operator  A = -∇·((1/ε) ∇)
    using finite differences with Neumann boundary conditions.

    Returns sparse matrix (Nx*Ny × Nx*Ny).
    """
    size = Nx * Ny
    eps_flat = eps_grid.flatten()
    inv_eps = 1.0 / eps_flat

    A = lil_matrix((size, size), dtype=complex)

    for j in range(Ny):
        for i in range(Nx):
            idx = i + j * Nx

            # x-direction coupling
            if i > 0:
                inv_eps_left = (inv_eps[idx] + inv_eps[idx - 1]) / 2.0
                A[idx, idx - 1] -= inv_eps_left / dx**2
                A[idx, idx] += inv_eps_left / dx**2
            if i < Nx - 1:
                inv_eps_right = (inv_eps[idx] + inv_eps[idx + 1]) / 2.0
                A[idx, idx + 1] -= inv_eps_right / dx**2
                A[idx, idx] += inv_eps_right / dx**2

            # y-direction coupling
            if j > 0:
                idx_below = idx - Nx
                inv_eps_below = (inv_eps[idx] + inv_eps[idx_below]) / 2.0
                A[idx, idx_below] -= inv_eps_below / dy**2
                A[idx, idx] += inv_eps_below / dy**2
            if j < Ny - 1:
                idx_above = idx + Nx
                inv_eps_above = (inv_eps[idx] + inv_eps[idx_above]) / 2.0
                A[idx, idx_above] -= inv_eps_above / dy**2
                A[idx, idx] += inv_eps_above / dy**2

    return A.tocsr()


def solve_eigenvalues(
    geom: CavityGeometry,
    Nx: int = 10,
    Ny: int = 10,
    n_modes: int = 6,
    c: float = 340.0,
    label: str = "",
) -> HelmholtzResult:
    """
    Solve for lowest non-trivial eigenvalues of the Helmholtz problem.

    Parameters
    ----------
    geom : CavityGeometry
        Cavity and inclusion specifications.
    Nx, Ny : int
        Grid resolution.
    n_modes : int
        Number of eigenvalues to compute.
    c : float
        Wave speed for frequency conversion.
    label : str
        Run identifier.

    Returns
    -------
    HelmholtzResult
    """
    eps_grid, dx, dy = build_epsilon_grid(geom, Nx, Ny)
    A = build_helmholtz_operator(Nx, Ny, dx, dy, eps_grid)

    # Shift to avoid singular zero mode
    shift = 1e-6
    A_shifted = A + shift * eye(A.shape[0], format='csr', dtype=complex)

    vals, _ = eigs(A_shifted, k=n_modes, which='SM')
    k2_real = np.sort(np.real(vals - shift))

    # Skip the ~0 constant mode, take positive eigenvalues
    k2_positive = k2_real[k2_real > 0.1]
    frequencies = c * np.sqrt(np.abs(k2_positive)) / (2.0 * np.pi)

    return HelmholtzResult(
        eigenvalues_k2=k2_positive,
        frequencies=frequencies,
        eps_grid=eps_grid,
        Lx=geom.Lx, Ly=geom.Ly,
        Nx=Nx, Ny=Ny,
        label=label,
    )


def compare_geometry_invariance(
    gamma: float = 0.3,
    beta: float = 1.0,
    Nx: int = 10,
    c: float = 340.0,
) -> dict:
    """
    Compare eigenvalues of a square cavity vs a stretched cavity
    to validate geometry-invariant behavior of ZIM/ENZ host.

    Returns dict of label -> HelmholtzResult.
    """
    # Square cavity
    geom_square = CavityGeometry(Lx=1.0, Ly=1.0)
    result_square = solve_eigenvalues(
        geom_square, Nx=Nx, Ny=Nx, c=c, label="Square (1×1 m)")

    # Stretched cavity (dilatancy in y-direction)
    Ly_stretch = 1.0 * (1.0 + beta * gamma)
    Ny_stretch = int(Nx * Ly_stretch)  # Scale grid proportionally
    geom_stretch = CavityGeometry(
        Lx=1.0, Ly=Ly_stretch,
        particle_center=(0.5, Ly_stretch / 2.0),
    )
    result_stretch = solve_eigenvalues(
        geom_stretch, Nx=Nx, Ny=Ny_stretch, c=c,
        label=f"Stretched (1×{Ly_stretch:.1f} m)")

    return {
        "square": result_square,
        "stretched": result_stretch,
    }
