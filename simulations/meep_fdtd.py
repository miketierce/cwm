"""
Meep FDTD Integration Scaffolding for WCFOMA

Provides wrappers around MIT Meep for full-wave electromagnetic simulation
of ferrofluid/ZIM resonant cavities.  This bridges the gap between the
simple Helmholtz eigenvalue solver (simulations/helmholtz_2d.py) and a
realistic multiphysics model.

Requirements:
  pip install meep  (or conda install -c conda-forge pymeep)

Usage:
  from simulations.meep_fdtd import MeepCavity, run_eigenmode_analysis
  cavity = MeepCavity(Lx=1.0, Ly=1.0, eps_host=0.01, eps_particle=11.7)
  results = run_eigenmode_analysis(cavity, n_modes=10)

NOTE: Meep is an optional dependency. All functions gracefully degrade
with informative error messages if Meep is not installed.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import warnings

# Check for Meep availability
try:
    import meep as mp
    MEEP_AVAILABLE = True
except ImportError:
    MEEP_AVAILABLE = False
    warnings.warn(
        "Meep not installed. Install with: conda install -c conda-forge pymeep\n"
        "Falling back to analytical/FD methods.",
        ImportWarning,
    )


@dataclass
class MeepCavity:
    """Cavity specification for Meep simulation."""
    Lx: float = 1.0               # Cavity width (m) — scaled to Meep units
    Ly: float = 1.0               # Cavity height (m)
    eps_host: complex = 0.01 + 0.001j   # ENZ host permittivity
    eps_particle: float = 11.7     # Dielectric particle permittivity
    particle_center: Tuple[float, float] = (0.0, 0.0)
    particle_radius: float = 0.2   # Particle radius (m)
    resolution: int = 50           # Grid points per unit length
    pml_thickness: float = 0.0     # PML thickness (0 for closed cavity)


@dataclass
class MeepResult:
    """Result from a Meep eigenmode simulation."""
    frequencies: np.ndarray        # Eigenfrequencies (Meep units)
    Q_factors: np.ndarray          # Quality factors
    decay_rates: np.ndarray        # Modal decay rates
    field_patterns: Optional[List[np.ndarray]] = None
    eigenvalues_k2: Optional[np.ndarray] = None
    label: str = ""
    resolution: int = 0
    converged: bool = False


def build_meep_geometry(cavity: MeepCavity) -> dict:
    """
    Build Meep geometry objects for a cavity with dielectric inclusion.

    Returns dict with keys: 'cell_size', 'geometry', 'sources', 'resolution'.
    """
    if not MEEP_AVAILABLE:
        raise RuntimeError(
            "Meep is not installed. Install with:\n"
            "  conda install -c conda-forge pymeep\n"
            "Or use the FD solver: simulations/helmholtz_2d.py"
        )

    cell = mp.Vector3(cavity.Lx, cavity.Ly, 0)

    geometry = []

    # Host medium (background)
    # Meep handles complex ε via conductivity: ε = ε_r + iσ/(ωε₀)
    eps_real = np.real(cavity.eps_host)
    eps_imag = np.imag(cavity.eps_host)

    # Dielectric particle
    cx, cy = cavity.particle_center
    geometry.append(
        mp.Cylinder(
            radius=cavity.particle_radius,
            center=mp.Vector3(cx, cy),
            material=mp.Medium(epsilon=cavity.eps_particle),
        )
    )

    return {
        'cell_size': cell,
        'geometry': geometry,
        'resolution': cavity.resolution,
        'default_material': mp.Medium(
            epsilon=max(eps_real, 1e-6),
            D_conductivity=2 * np.pi * eps_imag / max(eps_real, 1e-6) if eps_real > 0 else 0,
        ),
    }


def run_eigenmode_analysis(
    cavity: MeepCavity,
    n_modes: int = 10,
    fcen: float = 0.5,
    df: float = 1.0,
    run_time: float = 200,
    label: str = "",
) -> MeepResult:
    """
    Run Meep eigenmode analysis using Harminv.

    Parameters
    ----------
    cavity : MeepCavity
        Cavity specification.
    n_modes : int
        Maximum number of modes to extract.
    fcen : float
        Center frequency for source/Harminv (Meep units).
    df : float
        Frequency bandwidth.
    run_time : float
        Simulation run time (Meep units).
    label : str
        Run identifier.

    Returns
    -------
    MeepResult
    """
    if not MEEP_AVAILABLE:
        raise RuntimeError("Meep is not installed.")

    geo = build_meep_geometry(cavity)

    # Point source to excite modes
    sources = [
        mp.Source(
            mp.GaussianSource(frequency=fcen, fwidth=df),
            component=mp.Ez,
            center=mp.Vector3(0.1, 0.1),
        )
    ]

    sim = mp.Simulation(
        cell_size=geo['cell_size'],
        geometry=geo['geometry'],
        sources=sources,
        resolution=geo['resolution'],
        default_material=geo['default_material'],
        boundary_layers=[] if cavity.pml_thickness == 0 else [
            mp.PML(cavity.pml_thickness)
        ],
    )

    # Harminv for eigenmode extraction
    h = mp.Harminv(mp.Ez, mp.Vector3(0.05, 0.05), fcen, df)
    sim.run(mp.after_sources(h), until_after_sources=run_time)

    # Extract results
    modes = h.modes
    if len(modes) == 0:
        return MeepResult(
            frequencies=np.array([]),
            Q_factors=np.array([]),
            decay_rates=np.array([]),
            label=label,
            resolution=cavity.resolution,
            converged=False,
        )

    freqs = np.array([m.freq for m in modes[:n_modes]])
    Qs = np.array([m.Q for m in modes[:n_modes]])
    decays = np.array([m.decay_rate for m in modes[:n_modes]])

    # Convert to k² (eigenvalues)
    k2 = (2 * np.pi * freqs)**2

    return MeepResult(
        frequencies=freqs,
        Q_factors=Qs,
        decay_rates=decays,
        eigenvalues_k2=k2,
        label=label,
        resolution=cavity.resolution,
        converged=True,
    )


def convergence_study(
    cavity: MeepCavity,
    resolutions: List[int] = None,
    n_modes: int = 5,
) -> dict:
    """
    Run eigenmode analysis at multiple resolutions to check convergence.

    Returns dict with:
      'resolutions' : list of int
      'frequencies' : list of ndarray  (one per resolution)
      'Q_factors'   : list of ndarray
      'converged'   : bool  (True if highest two resolutions agree within 1%)
    """
    if resolutions is None:
        resolutions = [20, 30, 50, 75, 100]

    results = []
    for res in resolutions:
        cav = MeepCavity(
            Lx=cavity.Lx, Ly=cavity.Ly,
            eps_host=cavity.eps_host,
            eps_particle=cavity.eps_particle,
            particle_center=cavity.particle_center,
            particle_radius=cavity.particle_radius,
            resolution=res,
        )
        r = run_eigenmode_analysis(cav, n_modes=n_modes, label=f"res={res}")
        results.append(r)

    # Check convergence
    converged = False
    if len(results) >= 2 and results[-1].converged and results[-2].converged:
        f_hi = results[-1].frequencies
        f_lo = results[-2].frequencies
        n_cmp = min(len(f_hi), len(f_lo), n_modes)
        if n_cmp > 0:
            rel_diff = np.abs(f_hi[:n_cmp] - f_lo[:n_cmp]) / np.abs(f_lo[:n_cmp])
            converged = np.all(rel_diff < 0.01)

    return {
        'resolutions': resolutions,
        'results': results,
        'converged': converged,
    }


# ---------------------------------------------------------------------------
# Fallback: FD-based grid convergence (works without Meep)
# ---------------------------------------------------------------------------
def fd_convergence_study(
    Nx_values: List[int] = None,
    eps_host: complex = 1.0 + 0j,
    n_modes: int = 5,
) -> dict:
    """
    Run the finite-difference Helmholtz solver at increasing resolution
    to quantify discretization error.

    This works without Meep — uses helmholtz_2d.py.

    Returns dict with:
      'Nx_values' : list of int
      'eigenvalues' : list of ndarray (k² values)
      'relative_errors' : ndarray (error vs finest grid)
    """
    from .helmholtz_2d import solve_eigenvalues, CavityGeometry

    if Nx_values is None:
        Nx_values = [10, 15, 20, 30, 40, 50]

    geom = CavityGeometry(Lx=1.0, Ly=1.0, eps_host=eps_host,
                          eps_particle=11.7,
                          particle_center=(0.5, 0.5),
                          particle_radius=0.2)

    results = []
    for Nx in Nx_values:
        r = solve_eigenvalues(geom, Nx=Nx, Ny=Nx, n_modes=n_modes + 2,
                             label=f"Nx={Nx}")
        results.append(r.eigenvalues_k2)

    # Relative error vs finest grid
    finest = results[-1]
    errors = []
    for i, k2 in enumerate(results):
        n_cmp = min(len(k2), len(finest), n_modes)
        if n_cmp > 0:
            err = np.mean(np.abs(k2[:n_cmp] - finest[:n_cmp]) / np.abs(finest[:n_cmp]))
        else:
            err = np.nan
        errors.append(err)

    return {
        'Nx_values': Nx_values,
        'eigenvalues': results,
        'relative_errors': np.array(errors),
        'finest_k2': finest,
    }
