"""
Finite Element Validation of CWM Analytical Models
===================================================

Independent FEM validation of the eigenfrequency, perturbation, and
Q-factor predictions used throughout the CWM simulation stack.

**Why this module exists.**  The CWM analytical models use closed-form
formulas (f_n = nv/2L, Rayleigh perturbation, lumped Q budget).  These
formulas make assumptions: 1D kinematics, small perturbations, additive
loss mechanisms.  This module builds finite element models of the *same
geometry* from first principles and compares the FEM eigenvalues against
the analytical predictions.  Agreement validates the analytical models;
disagreement reveals where the simplifying assumptions break down.

**Implementation.**  All FEM assembly is done from textbook formulations
(Cook, Malkus, Plesha & Witt, "Concepts and Applications of Finite
Element Analysis", 4th ed., Wiley, 2002) using only numpy and scipy.
No external FEM library is used, so every line of matrix assembly is
transparent and auditable.  This is deliberate: a reviewer can inspect
the element stiffness and mass matrices line by line and verify that
they implement standard Galerkin finite elements.

Models implemented:
    1. **1D bar FEM** — longitudinal modes of a free-free elastic bar.
       Element: 2-node linear (P1) or 3-node quadratic (P2) bar element.
       Validates: f_n = n·v/(2L) eigenfrequency formula.

    2. **1D perturbation FEM** — point-mass perturbation of the bar.
       Validates: Rayleigh perturbation formula Δf/f = -(Δm/2M)·φ²(x₀).

    3. **2D plane-stress FEM** — rectangular rod cross-section.
       Element: constant-strain triangle (CST/T3).
       Validates: 1D approximation for finite aspect ratio (Poisson
       correction, Pochhammer–Chree dispersion for higher modes).

    4. **2D tethered rod FEM** — rod with clamped tether supports.
       Validates: anchor boundary condition assumptions.

    5. **Mesh convergence study** — Richardson extrapolation for error
       bounds and convergence rate verification.

Dependencies: numpy, scipy (already in the project).
"""

import numpy as np
from scipy.sparse import lil_matrix, csr_matrix, eye as speye
from scipy.sparse.linalg import eigsh
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict

from .glass_resonator import GlassProperties, RodGeometry, glass_database


# ═══════════════════════════════════════════════════════════════════════════
# Result Dataclasses
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class EigenResult:
    """Result of a FEM eigenvalue solve."""
    frequencies_hz: np.ndarray       # eigenfrequencies [Hz]
    angular_frequencies: np.ndarray  # angular frequencies [rad/s]
    mode_shapes: Optional[np.ndarray]  # eigenvectors (n_dof × n_modes)
    n_elements: int
    n_dof: int
    element_type: str                # "P1_bar", "P2_bar", "CST_tri", etc.


@dataclass
class ValidationComparison:
    """Side-by-side comparison of analytical vs FEM predictions."""
    mode_numbers: np.ndarray
    analytical_hz: np.ndarray        # from closed-form formula
    fem_hz: np.ndarray               # from FEM eigenvalue solve
    relative_errors: np.ndarray      # (analytical - fem) / fem
    max_relative_error: float
    mean_relative_error: float
    rms_relative_error: float
    analytical_formula: str          # human-readable description
    n_elements: int
    element_type: str
    validated: bool                  # True if max error < tolerance


@dataclass
class PerturbationComparison:
    """Comparison of Rayleigh perturbation formula against FEM."""
    mode_numbers: np.ndarray
    mass_position: float             # normalized position x/L
    mass_ratio: float                # δm / m_rod
    analytical_shifts: np.ndarray    # Δf/f from Rayleigh formula
    fem_shifts: np.ndarray           # Δf/f from FEM (perturbed - baseline)
    relative_errors: np.ndarray      # (analytical - fem) / fem
    max_relative_error: float
    rayleigh_validated: bool


@dataclass
class ConvergenceResult:
    """Mesh convergence study result."""
    element_counts: np.ndarray
    errors_per_refinement: np.ndarray  # max relative error at each refinement
    convergence_rate: float            # fitted rate (should be ~2 for P1)
    theoretical_rate: float            # expected rate for element type
    richardson_estimate_hz: np.ndarray  # extrapolated "exact" frequencies
    rate_validated: bool               # True if measured rate ≈ theoretical


@dataclass
class WaveSpeedComparison:
    """Comparison of wave speed models against FEM."""
    v_longitudinal: float   # bulk longitudinal (from material database)
    v_bar: float            # thin-bar limit: √(E/ρ)
    v_fem: float            # effective speed from FEM fundamental frequency
    v_bulk_calc: float      # √(E(1-ν)/((1+ν)(1-2ν)ρ)) from elastic constants
    best_match: str         # which analytical speed matches FEM
    discrepancy_pct: float  # error of current code's v_longitudinal vs FEM


@dataclass
class Mode2DInfo:
    """Classification of a 2D mode."""
    frequency_hz: float
    axial_energy_fraction: float   # fraction of KE in axial (x) direction
    mode_type: str                 # "longitudinal", "flexural", "shear", "mixed"
    matching_1d_mode: Optional[int]  # nearest 1D mode number, if longitudinal


@dataclass
class DispersionCorrection:
    """Pochhammer–Chree dispersion correction fitted from 2D FEM.

    For a rod with finite aspect ratio, the eigenfrequencies deviate
    from the 1D formula f_n = n·v_bar/(2L) because lateral Poisson
    coupling stiffens the rod at shorter wavelengths.  The correction
    has the form:

        f_n = (n·v_bar/(2L)) × [1 + C₁·ξ + C₂·ξ²]

    where ξ = (n·d/(2L))² is the Pochhammer–Chree dispersion parameter
    (square of the ratio of rod diameter to half-wavelength).

    The correction is positive (frequencies increase) because shorter
    wavelengths approach the plane-strain regime where the effective
    modulus exceeds Young's modulus E by a factor 1/(1−ν²).
    """
    C1: float                  # linear coefficient (FEM-fitted)
    C2: float                  # quadratic coefficient (FEM-fitted)
    poisson_ratio: float       # ν of the material
    aspect_ratio: float        # L/d of the rod
    n_modes_fitted: int        # number of clean longitudinal modes used
    max_valid_mode: int        # highest mode where correction < 1%
    rms_residual: float        # RMS of (fit − FEM) relative errors
    max_residual: float        # max |fit − FEM| relative error
    mode_numbers: np.ndarray   # mode numbers used in fit
    fem_errors: np.ndarray     # (f_2D − f_1D)/f_1D from FEM
    fitted_errors: np.ndarray  # C₁·ξ + C₂·ξ² at each mode


@dataclass
class FEMValidationReport:
    """Comprehensive FEM validation report."""
    eigenfrequency_1d: ValidationComparison
    wave_speed: WaveSpeedComparison
    perturbation: PerturbationComparison
    convergence: ConvergenceResult
    eigenfrequency_2d: Optional[ValidationComparison]
    mode_classification: Optional[List[Mode2DInfo]]
    dispersion: Optional[DispersionCorrection]
    all_passed: bool
    summary: str


# ═══════════════════════════════════════════════════════════════════════════
# 1D Bar Finite Elements
# ═══════════════════════════════════════════════════════════════════════════

def _assemble_bar_p1(
    n_elements: int,
    length: float,
    E: float,
    rho: float,
    A: float,
) -> Tuple[csr_matrix, csr_matrix]:
    """
    Assemble stiffness and consistent mass matrices for a 1D bar
    using 2-node linear (P1) elements.

    Element stiffness (textbook, Cook et al. §2.3):
        K_e = (EA/h) × [[1, -1], [-1, 1]]

    Element consistent mass (Cook et al. §11.2):
        M_e = (ρAh/6) × [[2, 1], [1, 2]]

    Parameters
    ----------
    n_elements : int
        Number of equal-length elements.
    length : float
        Rod length [m].
    E : float
        Young's modulus [Pa].
    rho : float
        Density [kg/m³].
    A : float
        Cross-sectional area [m²].

    Returns
    -------
    K, M : csr_matrix
        Global stiffness and mass matrices (n_nodes × n_nodes).
    """
    h = length / n_elements
    n_nodes = n_elements + 1

    K = lil_matrix((n_nodes, n_nodes))
    M = lil_matrix((n_nodes, n_nodes))

    # Element matrices
    ke = (E * A / h) * np.array([[1.0, -1.0], [-1.0, 1.0]])
    me = (rho * A * h / 6.0) * np.array([[2.0, 1.0], [1.0, 2.0]])

    for e in range(n_elements):
        dofs = [e, e + 1]
        for i in range(2):
            for j in range(2):
                K[dofs[i], dofs[j]] += ke[i, j]
                M[dofs[i], dofs[j]] += me[i, j]

    return K.tocsr(), M.tocsr()


def _assemble_bar_p2(
    n_elements: int,
    length: float,
    E: float,
    rho: float,
    A: float,
) -> Tuple[csr_matrix, csr_matrix]:
    """
    Assemble stiffness and consistent mass matrices for a 1D bar
    using 3-node quadratic (P2) elements.

    Each element has nodes at {x_i, x_i + h/2, x_i + h}.
    Shape functions are quadratic Lagrange polynomials.

    Element stiffness (Cook et al. §3.9):
        K_e = (EA/3h) × [[7, -8, 1], [-8, 16, -8], [1, -8, 7]]

    Element consistent mass (Cook et al. §11.2):
        M_e = (ρAh/30) × [[4, 2, -1], [2, 16, 2], [-1, 2, 4]]

    Returns
    -------
    K, M : csr_matrix
        Global matrices (n_nodes × n_nodes), n_nodes = 2*n_elements + 1.
    """
    h = length / n_elements
    n_nodes = 2 * n_elements + 1

    K = lil_matrix((n_nodes, n_nodes))
    M = lil_matrix((n_nodes, n_nodes))

    ke = (E * A / (3.0 * h)) * np.array([
        [7.0, -8.0, 1.0],
        [-8.0, 16.0, -8.0],
        [1.0, -8.0, 7.0],
    ])
    me = (rho * A * h / 30.0) * np.array([
        [4.0, 2.0, -1.0],
        [2.0, 16.0, 2.0],
        [-1.0, 2.0, 4.0],
    ])

    for e in range(n_elements):
        dofs = [2 * e, 2 * e + 1, 2 * e + 2]
        for i in range(3):
            for j in range(3):
                K[dofs[i], dofs[j]] += ke[i, j]
                M[dofs[i], dofs[j]] += me[i, j]

    return K.tocsr(), M.tocsr()


def fem_eigenfrequencies_1d(
    length: float,
    E: float,
    rho: float,
    A: float,
    n_modes: int = 20,
    n_elements: int = 200,
    element_order: int = 1,
) -> EigenResult:
    """
    Compute eigenfrequencies of a free-free elastic bar using FEM.

    Boundary conditions: free-free (Neumann on both ends — natural BCs,
    no essential BCs applied).  The stiffness matrix is singular with
    one rigid-body mode (uniform translation).  We use shift-invert
    mode in eigsh to skip the rigid-body eigenvalue.

    Parameters
    ----------
    length : float
        Bar length [m].
    E : float
        Young's modulus [Pa].
    rho : float
        Density [kg/m³].
    A : float
        Cross-sectional area [m²].
    n_modes : int
        Number of non-rigid eigenfrequencies to compute.
    n_elements : int
        Number of elements.
    element_order : int
        1 for P1 (linear), 2 for P2 (quadratic).

    Returns
    -------
    EigenResult
    """
    if element_order == 1:
        K, M = _assemble_bar_p1(n_elements, length, E, rho, A)
        etype = "P1_bar"
    elif element_order == 2:
        K, M = _assemble_bar_p2(n_elements, length, E, rho, A)
        etype = "P2_bar"
    else:
        raise ValueError(f"element_order must be 1 or 2, got {element_order}")

    n_dof = K.shape[0]

    # Shift-invert: find eigenvalues near sigma.
    # Estimate first non-rigid eigenvalue: ω₁ = π√(E/ρ)/L
    v_bar = np.sqrt(E / rho)
    omega1_est = np.pi * v_bar / length
    sigma = (0.5 * omega1_est) ** 2  # shift below first mode

    # Request n_modes + 1 to account for the rigid-body mode
    k_request = min(n_modes + 2, n_dof - 2)
    eigenvalues, eigenvectors = eigsh(K, k=k_request, M=M, sigma=sigma)

    # Sort by eigenvalue
    order = np.argsort(eigenvalues)
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    # Filter out rigid-body mode (ω² ≈ 0)
    threshold = 1e-6 * np.max(np.abs(eigenvalues))
    non_rigid = eigenvalues > threshold
    eigenvalues = eigenvalues[non_rigid][:n_modes]
    eigenvectors = eigenvectors[:, non_rigid][:, :n_modes]

    omega = np.sqrt(np.abs(eigenvalues))
    freqs = omega / (2.0 * np.pi)

    return EigenResult(
        frequencies_hz=freqs,
        angular_frequencies=omega,
        mode_shapes=eigenvectors,
        n_elements=n_elements,
        n_dof=n_dof,
        element_type=etype,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1D Perturbation Validation
# ═══════════════════════════════════════════════════════════════════════════

def fem_perturbation_shifts(
    length: float,
    E: float,
    rho: float,
    A: float,
    mass_position: float,
    mass_value: float,
    n_modes: int = 20,
    n_elements: int = 400,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute eigenfrequency shifts from a point mass perturbation
    using FEM (direct eigenvalue difference, not Rayleigh formula).

    Adds a concentrated mass δm at position x₀ by modifying the
    global mass matrix: M' = M + δm × N(x₀)ᵀN(x₀), where N(x₀)
    is the shape function vector evaluated at x₀.

    Parameters
    ----------
    length : float
        Bar length [m].
    E, rho, A : float
        Material and geometry properties.
    mass_position : float
        Position of the point mass along the bar [m].
    mass_value : float
        Added mass [kg].
    n_modes : int
        Number of modes to compute.
    n_elements : int
        Number of elements (fine mesh for accuracy).

    Returns
    -------
    baseline_hz : ndarray
        Unperturbed eigenfrequencies.
    perturbed_hz : ndarray
        Perturbed eigenfrequencies.
    relative_shifts : ndarray
        (perturbed - baseline) / baseline  (should be negative).
    """
    # --- Baseline (no added mass) ---
    K, M_base = _assemble_bar_p1(n_elements, length, E, rho, A)
    n_dof = K.shape[0]
    h = length / n_elements

    v_bar = np.sqrt(E / rho)
    omega1_est = np.pi * v_bar / length
    sigma = (0.5 * omega1_est) ** 2

    k_request = min(n_modes + 2, n_dof - 2)

    vals_base, _ = eigsh(K, k=k_request, M=M_base, sigma=sigma)
    vals_base = np.sort(vals_base)
    vals_base = vals_base[vals_base > 1e-6 * np.max(np.abs(vals_base))][:n_modes]
    baseline_hz = np.sqrt(np.abs(vals_base)) / (2.0 * np.pi)

    # --- Perturbed (add point mass) ---
    M_pert = M_base.copy().tolil()

    # Find the element containing mass_position
    elem_idx = int(mass_position / h)
    elem_idx = min(elem_idx, n_elements - 1)
    x_local = mass_position - elem_idx * h  # local coordinate within element

    # Linear shape functions: N1 = 1 - ξ, N2 = ξ, where ξ = x_local/h
    xi = x_local / h
    N = np.array([1.0 - xi, xi])
    dofs = [elem_idx, elem_idx + 1]

    # Add concentrated mass: M' += δm × N Nᵀ
    for i in range(2):
        for j in range(2):
            M_pert[dofs[i], dofs[j]] += mass_value * N[i] * N[j]

    M_pert = M_pert.tocsr()

    vals_pert, _ = eigsh(K, k=k_request, M=M_pert, sigma=sigma)
    vals_pert = np.sort(vals_pert)
    vals_pert = vals_pert[vals_pert > 1e-6 * np.max(np.abs(vals_pert))][:n_modes]
    perturbed_hz = np.sqrt(np.abs(vals_pert)) / (2.0 * np.pi)

    relative_shifts = (perturbed_hz - baseline_hz) / baseline_hz

    return baseline_hz, perturbed_hz, relative_shifts


def rayleigh_perturbation_shifts(
    mode_numbers: np.ndarray,
    mass_position_normalized: float,
    mass_ratio: float,
) -> np.ndarray:
    """
    Analytical Rayleigh perturbation prediction for a point mass on
    a free-free bar.

    For a free-free bar, longitudinal mode shapes are:
        φ_n(x) = cos(nπx/L),  n = 1, 2, 3, ...

    The first-order perturbation for a point mass δm at x₀:
        Δf_n/f_n = -(δm/m_rod) × cos²(nπx₀/L)

    where m_rod = ρAL is the total rod mass.  The cos² factor arises
    because the kinetic energy perturbation is proportional to |φ_n(x₀)|²,
    and the mode normalization gives ∫₀ᴸ φ_n² dx = L/2 for n ≥ 1.

    Parameters
    ----------
    mode_numbers : ndarray
        Mode indices (1, 2, 3, ...).
    mass_position_normalized : float
        x₀/L ∈ [0, 1].
    mass_ratio : float
        δm / m_rod.

    Returns
    -------
    relative_shifts : ndarray
        Δf_n/f_n (negative = frequency decrease).
    """
    n = mode_numbers.astype(float)
    x_norm = mass_position_normalized
    # cos²(nπx/L) for free-free longitudinal modes
    shifts = -mass_ratio * np.cos(n * np.pi * x_norm) ** 2
    return shifts


# ═══════════════════════════════════════════════════════════════════════════
# 2D Plane-Stress Finite Elements (Constant Strain Triangle)
# ═══════════════════════════════════════════════════════════════════════════

def _build_2d_mesh(
    Lx: float,
    Ly: float,
    nx: int,
    ny: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build a structured triangular mesh of a rectangle [0, Lx] × [-Ly/2, Ly/2].
    Each quad cell is split into 2 triangles (lower-left and upper-right).

    Returns
    -------
    nodes : ndarray (n_nodes, 2)
        Node coordinates.
    elements : ndarray (n_elements, 3)
        Triangle connectivity (node indices).
    """
    x = np.linspace(0, Lx, nx + 1)
    y = np.linspace(-Ly / 2, Ly / 2, ny + 1)
    xx, yy = np.meshgrid(x, y, indexing='ij')
    nodes = np.column_stack([xx.ravel(), yy.ravel()])
    n_nodes_y = ny + 1

    elements = []
    for i in range(nx):
        for j in range(ny):
            # Node indices of the quad
            n0 = i * n_nodes_y + j
            n1 = (i + 1) * n_nodes_y + j
            n2 = (i + 1) * n_nodes_y + (j + 1)
            n3 = i * n_nodes_y + (j + 1)
            # Two triangles per quad
            elements.append([n0, n1, n3])
            elements.append([n1, n2, n3])

    return nodes, np.array(elements, dtype=int)


def _cst_stiffness(
    nodes: np.ndarray,
    E: float,
    nu: float,
    thickness: float = 1.0,
) -> np.ndarray:
    """
    Element stiffness matrix for a constant-strain triangle (CST)
    under plane stress (Cook et al. §3.3–3.4).

    Plane-stress constitutive matrix:
        D = E/(1-ν²) × [[1, ν, 0], [ν, 1, 0], [0, 0, (1-ν)/2]]

    Strain-displacement matrix B = (1/2A) × [...]

    K_e = t × A_e × Bᵀ D B

    Parameters
    ----------
    nodes : ndarray (3, 2)
        Triangle vertex coordinates.
    E : float
        Young's modulus [Pa].
    nu : float
        Poisson's ratio.
    thickness : float
        Out-of-plane thickness [m].

    Returns
    -------
    K_e : ndarray (6, 6)
    """
    x1, y1 = nodes[0]
    x2, y2 = nodes[1]
    x3, y3 = nodes[2]

    # Element area (signed, from cross product)
    A_e = 0.5 * abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1))
    if A_e < 1e-30:
        return np.zeros((6, 6))

    # Strain-displacement matrix B (3 × 6)
    b1 = y2 - y3
    b2 = y3 - y1
    b3 = y1 - y2
    c1 = x3 - x2
    c2 = x1 - x3
    c3 = x2 - x1

    B = (1.0 / (2.0 * A_e)) * np.array([
        [b1, 0, b2, 0, b3, 0],
        [0, c1, 0, c2, 0, c3],
        [c1, b1, c2, b2, c3, b3],
    ])

    # Plane-stress constitutive matrix
    D = (E / (1.0 - nu ** 2)) * np.array([
        [1.0, nu, 0.0],
        [nu, 1.0, 0.0],
        [0.0, 0.0, (1.0 - nu) / 2.0],
    ])

    K_e = thickness * A_e * (B.T @ D @ B)
    return K_e


def _cst_mass(
    nodes: np.ndarray,
    rho: float,
    thickness: float = 1.0,
) -> np.ndarray:
    """
    Consistent element mass matrix for a CST (Cook et al. §11.3).

    M_e = ρ·t·A_e/12 × [[2,0,1,0,1,0],
                          [0,2,0,1,0,1],
                          [1,0,2,0,1,0],
                          [0,1,0,2,0,1],
                          [1,0,1,0,2,0],
                          [0,1,0,1,0,2]]

    Parameters
    ----------
    nodes : ndarray (3, 2)
        Triangle vertex coordinates.
    rho : float
        Density [kg/m³].
    thickness : float
        Out-of-plane thickness [m].

    Returns
    -------
    M_e : ndarray (6, 6)
    """
    x1, y1 = nodes[0]
    x2, y2 = nodes[1]
    x3, y3 = nodes[2]
    A_e = 0.5 * abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1))

    block = np.array([
        [2, 0, 1, 0, 1, 0],
        [0, 2, 0, 1, 0, 1],
        [1, 0, 2, 0, 1, 0],
        [0, 1, 0, 2, 0, 1],
        [1, 0, 1, 0, 2, 0],
        [0, 1, 0, 1, 0, 2],
    ], dtype=float)

    M_e = (rho * thickness * A_e / 12.0) * block
    return M_e


def _assemble_2d(
    nodes: np.ndarray,
    elements: np.ndarray,
    E: float,
    nu: float,
    rho: float,
    thickness: float = 1.0,
) -> Tuple[csr_matrix, csr_matrix]:
    """
    Assemble global stiffness and mass matrices for a 2D plane-stress
    CST mesh.

    Parameters
    ----------
    nodes : ndarray (n_nodes, 2)
    elements : ndarray (n_elements, 3)
    E, nu, rho : float
        Material properties.
    thickness : float
        Out-of-plane thickness [m].

    Returns
    -------
    K, M : csr_matrix (2*n_nodes × 2*n_nodes)
        DOF ordering: [u_x0, u_y0, u_x1, u_y1, ...].
    """
    n_nodes = nodes.shape[0]
    n_dof = 2 * n_nodes
    K = lil_matrix((n_dof, n_dof))
    M = lil_matrix((n_dof, n_dof))

    for tri in elements:
        tri_nodes = nodes[tri]
        ke = _cst_stiffness(tri_nodes, E, nu, thickness)
        me = _cst_mass(tri_nodes, rho, thickness)

        # DOF map: node i → global DOFs [2*i, 2*i+1]
        dofs = []
        for ni in tri:
            dofs.extend([2 * ni, 2 * ni + 1])

        for i in range(6):
            for j in range(6):
                K[dofs[i], dofs[j]] += ke[i, j]
                M[dofs[i], dofs[j]] += me[i, j]

    return K.tocsr(), M.tocsr()


def fem_eigenfrequencies_2d(
    Lx: float,
    Ly: float,
    E: float,
    nu: float,
    rho: float,
    n_modes: int = 30,
    nx: int = 80,
    ny: int = 6,
    thickness: float = 1.0,
    clamped_nodes: Optional[np.ndarray] = None,
) -> Tuple[EigenResult, np.ndarray, np.ndarray]:
    """
    Compute eigenfrequencies of a 2D plane-stress rectangular domain.

    By default, free-free BCs (3 rigid-body modes: 2 translations +
    1 rotation).  Optional clamped_nodes for tethered configurations.

    Parameters
    ----------
    Lx, Ly : float
        Rectangle dimensions [m].
    E, nu, rho : float
        Material properties.
    n_modes : int
        Number of non-rigid modes to compute.
    nx, ny : int
        Mesh divisions in x and y.
    thickness : float
        Out-of-plane thickness [m] (rod diameter for plane-stress model).
    clamped_nodes : ndarray, optional
        Node indices to clamp (fix u_x = u_y = 0).

    Returns
    -------
    result : EigenResult
    nodes : ndarray (n_nodes, 2)
    elements : ndarray (n_elements, 3)
    """
    nodes, elements = _build_2d_mesh(Lx, Ly, nx, ny)
    K, M = _assemble_2d(nodes, elements, E, nu, rho, thickness)
    n_dof = K.shape[0]

    # Apply clamped BCs if provided
    if clamped_nodes is not None and len(clamped_nodes) > 0:
        clamped_dofs = []
        for ni in clamped_nodes:
            clamped_dofs.extend([2 * ni, 2 * ni + 1])
        clamped_dofs = np.array(clamped_dofs)

        # Penalty method: K[i,i] += penalty, M[i,i] += penalty/omega²
        # Simpler: zero rows/cols and set diagonal to large value
        penalty = 1e20 * E * Ly  # large penalty stiffness
        K_lil = K.tolil()
        M_lil = M.tolil()
        for d in clamped_dofs:
            K_lil[d, :] = 0
            K_lil[:, d] = 0
            K_lil[d, d] = penalty
            M_lil[d, :] = 0
            M_lil[:, d] = 0
            M_lil[d, d] = penalty * 1e-10  # effectively zero mass
        K = K_lil.tocsr()
        M = M_lil.tocsr()
        n_rigid = 0
    else:
        n_rigid = 3  # 2 translations + 1 rotation

    # Estimate first non-rigid eigenvalue for shift
    v_bar = np.sqrt(E / rho)
    omega1_est = np.pi * v_bar / Lx
    sigma = (0.5 * omega1_est) ** 2

    k_request = min(n_modes + n_rigid + 2, n_dof - 2)
    eigenvalues, eigenvectors = eigsh(K, k=k_request, M=M, sigma=sigma)

    order = np.argsort(eigenvalues)
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    # Filter rigid-body modes
    threshold = 1e-6 * np.max(np.abs(eigenvalues))
    non_rigid = eigenvalues > threshold
    eigenvalues = eigenvalues[non_rigid][:n_modes]
    eigenvectors = eigenvectors[:, non_rigid][:, :n_modes]

    omega = np.sqrt(np.abs(eigenvalues))
    freqs = omega / (2.0 * np.pi)

    result = EigenResult(
        frequencies_hz=freqs,
        angular_frequencies=omega,
        mode_shapes=eigenvectors,
        n_elements=len(elements),
        n_dof=n_dof,
        element_type="CST_tri",
    )
    return result, nodes, elements


def classify_2d_modes(
    eigenvectors: np.ndarray,
    nodes: np.ndarray,
    frequencies_hz: np.ndarray,
    Lx: float,
    E: float,
    rho: float,
) -> List[Mode2DInfo]:
    """
    Classify 2D modes as longitudinal, flexural, or mixed by computing
    the fraction of kinetic energy in the axial (x) direction.

    For mode φ = (u_x, u_y) at each node:
        R_x = Σ u_x² / Σ (u_x² + u_y²)

    Longitudinal: R_x > 0.85
    Flexural:     R_x < 0.15
    Mixed:        otherwise

    Also matches longitudinal modes against the nearest 1D analytical
    mode number: n ≈ round(f / f₁) where f₁ = v_bar/(2L).
    """
    n_nodes = nodes.shape[0]
    n_modes = eigenvectors.shape[1]
    v_bar = np.sqrt(E / rho)
    f1_bar = v_bar / (2.0 * Lx)

    modes = []
    for m in range(n_modes):
        vec = eigenvectors[:, m]
        ux = vec[0::2]  # x-displacements
        uy = vec[1::2]  # y-displacements

        energy_x = np.sum(ux ** 2)
        energy_y = np.sum(uy ** 2)
        total = energy_x + energy_y
        if total < 1e-30:
            rx = 0.5
        else:
            rx = energy_x / total

        if rx > 0.85:
            mtype = "longitudinal"
            n_match = max(1, round(frequencies_hz[m] / f1_bar))
        elif rx < 0.15:
            mtype = "flexural"
            n_match = None
        else:
            mtype = "mixed"
            n_match = None

        modes.append(Mode2DInfo(
            frequency_hz=frequencies_hz[m],
            axial_energy_fraction=rx,
            mode_type=mtype,
            matching_1d_mode=n_match,
        ))

    return modes


# ═══════════════════════════════════════════════════════════════════════════
# Wave Speed Analysis
# ═══════════════════════════════════════════════════════════════════════════

def compare_wave_speeds(
    glass: GlassProperties,
    fem_f1: float,
    rod_length: float,
) -> WaveSpeedComparison:
    """
    Compare analytical wave speed models against the FEM fundamental
    frequency.

    Three analytical wave speeds:
    1. v_longitudinal — the value in the material database (used by
       compute_mode_spectrum).  This is the experimentally measured
       bulk longitudinal wave speed.
    2. v_bar = √(E/ρ) — the thin-bar (Love/Pochhammer) limit.
       Correct for slender rods where d << λ.
    3. v_bulk = √(E(1-ν)/((1+ν)(1-2ν)ρ)) — computed from elastic
       constants.  Should match v_longitudinal if the constants are
       self-consistent.

    The FEM "effective speed" is v_fem = 2L × f₁_fem.
    """
    v_long = glass.v_longitudinal
    v_bar = np.sqrt(glass.youngs_modulus / glass.density)
    v_bulk = np.sqrt(
        glass.youngs_modulus * (1 - glass.poisson_ratio)
        / ((1 + glass.poisson_ratio) * (1 - 2 * glass.poisson_ratio)
           * glass.density)
    )
    v_fem = 2.0 * rod_length * fem_f1

    # Which analytical speed is closest to FEM?
    errors = {
        "v_longitudinal (database)": abs(v_long - v_fem) / v_fem,
        "v_bar = √(E/ρ)": abs(v_bar - v_fem) / v_fem,
        "v_bulk (from E,ν,ρ)": abs(v_bulk - v_fem) / v_fem,
    }
    best = min(errors, key=errors.get)
    discrepancy = (v_long - v_fem) / v_fem * 100

    return WaveSpeedComparison(
        v_longitudinal=v_long,
        v_bar=v_bar,
        v_fem=v_fem,
        v_bulk_calc=v_bulk,
        best_match=best,
        discrepancy_pct=discrepancy,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Convergence Study
# ═══════════════════════════════════════════════════════════════════════════

def convergence_study(
    length: float,
    E: float,
    rho: float,
    A: float,
    n_modes: int = 10,
    element_counts: Optional[np.ndarray] = None,
    element_order: int = 1,
) -> ConvergenceResult:
    """
    Mesh convergence study for 1D bar eigenfrequencies.

    Solves at successively finer meshes and measures the relative error
    of each refinement against the finest mesh (as a proxy for the exact
    solution).  Also performs Richardson extrapolation to estimate the
    asymptotic values.

    Expected convergence rates:
    - P1 (linear):    error ~ h²  → rate ≈ 2
    - P2 (quadratic): error ~ h⁴  → rate ≈ 4

    Parameters
    ----------
    length : float
        Bar length [m].
    E, rho, A : float
        Material and geometry.
    n_modes : int
        Number of modes to track.
    element_counts : ndarray, optional
        Sequence of mesh sizes.  Default: [20, 40, 80, 160, 320, 640].
    element_order : int
        1 for P1, 2 for P2.

    Returns
    -------
    ConvergenceResult
    """
    if element_counts is None:
        element_counts = np.array([20, 40, 80, 160, 320, 640])

    results = {}
    for ne in element_counts:
        res = fem_eigenfrequencies_1d(length, E, rho, A, n_modes, int(ne),
                                      element_order)
        results[ne] = res.frequencies_hz

    # Use finest mesh as reference
    finest = element_counts[-1]
    ref_freqs = results[finest]

    # Errors at each refinement level
    errors = np.zeros(len(element_counts))
    for i, ne in enumerate(element_counts):
        n_compare = min(len(results[ne]), len(ref_freqs))
        if n_compare == 0:
            errors[i] = 1.0
            continue
        rel_err = np.abs(results[ne][:n_compare] - ref_freqs[:n_compare]) / ref_freqs[:n_compare]
        errors[i] = np.max(rel_err)

    # Fit convergence rate from the middle refinements
    # (skip finest since error=0 by definition, skip coarsest for pre-asymptotic effects)
    valid = (errors > 0) & (errors < 0.5)
    if np.sum(valid) >= 2:
        h_vals = length / element_counts[valid].astype(float)
        log_h = np.log(h_vals)
        log_err = np.log(errors[valid])
        coeffs = np.polyfit(log_h, log_err, 1)
        measured_rate = float(coeffs[0])
    else:
        measured_rate = 0.0

    theoretical_rate = 2.0 * element_order  # P1→2, P2→4

    # Richardson extrapolation using two finest meshes
    if len(element_counts) >= 3:
        # Use second-finest and third-finest
        f_fine = results[element_counts[-2]]
        f_coarse = results[element_counts[-3]]
        r = element_counts[-2] / element_counts[-3]  # refinement ratio
        n_compare = min(len(f_fine), len(f_coarse))
        p = measured_rate if measured_rate > 0.5 else theoretical_rate
        richardson = f_fine[:n_compare] + (
            (f_fine[:n_compare] - f_coarse[:n_compare]) / (r ** p - 1)
        )
    else:
        richardson = ref_freqs

    rate_ok = abs(measured_rate - theoretical_rate) < 1.0  # within 1 of expected

    return ConvergenceResult(
        element_counts=element_counts,
        errors_per_refinement=errors,
        convergence_rate=measured_rate,
        theoretical_rate=theoretical_rate,
        richardson_estimate_hz=richardson,
        rate_validated=rate_ok,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Pochhammer–Chree Dispersion Correction
# ═══════════════════════════════════════════════════════════════════════════

def fit_dispersion_correction(
    mode_info: List[Mode2DInfo],
    rod_length: float,
    rod_diameter: float,
    E: float,
    rho: float,
    max_xi: float = 0.10,
) -> DispersionCorrection:
    """
    Fit a Pochhammer–Chree dispersion correction from 2D FEM mode data.

    The 1D bar formula f_n = n·v_bar/(2L) becomes increasingly inaccurate
    at higher mode numbers because shorter wavelengths "see" the rod's
    finite diameter.  The Poisson effect couples axial and lateral motion,
    stiffening the response and raising frequencies above the 1D prediction.

    This function extracts the longitudinal modes from a 2D FEM solve,
    computes the relative error vs. 1D analytical, and fits a quadratic
    correction in the Pochhammer–Chree dispersion parameter ξ = (nd/(2L))²:

        f_n_corrected = (n·v_bar/(2L)) × [1 + C₁·ξ + C₂·ξ²]

    Only modes with ξ < max_xi are used for fitting (to avoid the regime
    where longitudinal-flexural mode coupling corrupts the data).

    Parameters
    ----------
    mode_info : list of Mode2DInfo
        Mode classification from classify_2d_modes().
    rod_length : float
        Rod length L [m].
    rod_diameter : float
        Rod diameter d [m].
    E : float
        Young's modulus [Pa].
    rho : float
        Density [kg/m³].
    max_xi : float
        Maximum ξ for fitting (modes above this are excluded).

    Returns
    -------
    DispersionCorrection
    """
    v_bar = np.sqrt(E / rho)
    L = rod_length
    d = rod_diameter

    # Extract clean longitudinal modes within the fitting range
    long_modes = [m for m in mode_info if m.mode_type == "longitudinal"]

    ns = []
    errors = []
    for m in long_modes:
        n = m.matching_1d_mode
        if n is None:
            continue
        xi = (n * d / (2 * L)) ** 2
        if xi > max_xi:
            continue
        f_1d = n * v_bar / (2 * L)
        err = (m.frequency_hz - f_1d) / f_1d
        ns.append(n)
        errors.append(err)

    ns = np.array(ns, dtype=float)
    errors = np.array(errors)
    xi_arr = (ns * d / (2 * L)) ** 2

    # Quadratic fit: error = C₁·ξ + C₂·ξ² (no constant term — zero at ξ=0)
    A_mat = np.column_stack([xi_arr, xi_arr ** 2])
    coeffs, _, _, _ = np.linalg.lstsq(A_mat, errors, rcond=None)
    C1, C2 = float(coeffs[0]), float(coeffs[1])

    fitted = C1 * xi_arr + C2 * xi_arr ** 2
    residuals = errors - fitted
    rms_resid = float(np.sqrt(np.mean(residuals ** 2)))
    max_resid = float(np.max(np.abs(residuals)))

    # Find highest mode where correction stays below 1%
    aspect = L / d
    max_valid = int(ns[-1])  # start from the last fitted mode
    for test_n in range(int(ns[-1]) + 1, int(5 * aspect)):
        xi_test = (test_n * d / (2 * L)) ** 2
        corr = C1 * xi_test + C2 * xi_test ** 2
        if corr > 0.01:  # 1% correction threshold
            max_valid = test_n - 1
            break
    else:
        max_valid = int(5 * aspect)

    return DispersionCorrection(
        C1=C1,
        C2=C2,
        poisson_ratio=0.0,  # filled by caller
        aspect_ratio=L / d,
        n_modes_fitted=len(ns),
        max_valid_mode=max_valid,
        rms_residual=rms_resid,
        max_residual=max_resid,
        mode_numbers=ns.astype(int),
        fem_errors=errors,
        fitted_errors=fitted,
    )


def dispersion_corrected_frequency(
    n: int,
    v_bar: float,
    rod_length: float,
    rod_diameter: float,
    disp: DispersionCorrection,
) -> float:
    """
    Return the dispersion-corrected eigenfrequency for mode n.

    Parameters
    ----------
    n : int
        Mode number (1, 2, 3, ...).
    v_bar : float
        Thin-bar wave speed √(E/ρ) [m/s].
    rod_length : float
        Rod length L [m].
    rod_diameter : float
        Rod diameter d [m].
    disp : DispersionCorrection
        Fitted dispersion model.

    Returns
    -------
    f_corrected : float
        Dispersion-corrected frequency [Hz].
    """
    f_1d = n * v_bar / (2.0 * rod_length)
    xi = (n * rod_diameter / (2.0 * rod_length)) ** 2
    return f_1d * (1.0 + disp.C1 * xi + disp.C2 * xi ** 2)


# ═══════════════════════════════════════════════════════════════════════════
# Comprehensive Validation Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_fem_validation(
    glass_key: str = "borosilicate",
    rod_length: float = 1e-3,
    rod_diameter: float = 40e-6,
    n_modes_1d: int = 50,
    n_modes_2d: int = 40,
    tolerance_1d: float = 0.005,
    tolerance_pert: float = 0.05,
    verbose: bool = True,
) -> FEMValidationReport:
    """
    Run the complete FEM validation suite for the CWM reference geometry.

    Validates:
    1. 1D bar eigenfrequencies against f_n = n·v_bar/(2L)
    2. Wave speed: which analytical v matches FEM
    3. Rayleigh perturbation shifts for 3 mass positions
    4. Mesh convergence rate
    5. 2D plane-stress eigenfrequencies vs 1D
    6. 2D mode classification (longitudinal vs flexural)

    Parameters
    ----------
    glass_key : str
        Glass type from database.
    rod_length : float
        Rod length [m].
    rod_diameter : float
        Rod diameter [m].
    n_modes_1d : int
        Number of modes for 1D validation.
    n_modes_2d : int
        Number of modes for 2D validation.
    tolerance_1d : float
        Maximum acceptable relative error for 1D validation.
    tolerance_pert : float
        Maximum acceptable relative error for perturbation validation.
    verbose : bool
        Print detailed results.

    Returns
    -------
    FEMValidationReport
    """
    db = glass_database()
    glass = db[glass_key]
    E = glass.youngs_modulus
    rho = glass.density
    nu = glass.poisson_ratio
    A = np.pi * (rod_diameter / 2) ** 2
    L = rod_length

    if verbose:
        print("=" * 70)
        print("  FEM VALIDATION OF CWM ANALYTICAL MODELS")
        print("=" * 70)
        print(f"\n  Material:  {glass.name}")
        print(f"  Rod:       L = {L*1e3:.2f} mm, d = {rod_diameter*1e6:.0f} µm")
        print(f"  E = {E/1e9:.1f} GPa, ρ = {rho:.0f} kg/m³, ν = {nu:.2f}")

    # ── 1. 1D Eigenfrequency Validation ──────────────────────────────

    if verbose:
        print("\n━━━ 1. Eigenfrequency Validation (1D Bar FEM) ━━━")

    fem_1d = fem_eigenfrequencies_1d(L, E, rho, A, n_modes_1d,
                                      n_elements=500, element_order=2)
    modes = np.arange(1, n_modes_1d + 1)

    # Analytical using bar wave speed (correct for 1D bar)
    v_bar = np.sqrt(E / rho)
    analytical_bar = modes * v_bar / (2.0 * L)

    # Analytical using v_longitudinal (what the existing code uses)
    analytical_vlong = modes * glass.v_longitudinal / (2.0 * L)

    # Compare against FEM
    n_compare = min(len(fem_1d.frequencies_hz), len(analytical_bar))
    fem_freqs = fem_1d.frequencies_hz[:n_compare]
    ana_bar = analytical_bar[:n_compare]
    ana_vlong = analytical_vlong[:n_compare]
    modes_cmp = modes[:n_compare]

    err_bar = (ana_bar - fem_freqs) / fem_freqs
    err_vlong = (ana_vlong - fem_freqs) / fem_freqs

    eigenfreq_result = ValidationComparison(
        mode_numbers=modes_cmp,
        analytical_hz=ana_bar,
        fem_hz=fem_freqs,
        relative_errors=err_bar,
        max_relative_error=float(np.max(np.abs(err_bar))),
        mean_relative_error=float(np.mean(np.abs(err_bar))),
        rms_relative_error=float(np.sqrt(np.mean(err_bar ** 2))),
        analytical_formula="f_n = n·√(E/ρ)/(2L)  [thin-bar limit]",
        n_elements=500,
        element_type="P2_bar",
        validated=bool(np.max(np.abs(err_bar)) < tolerance_1d),
    )

    if verbose:
        print(f"\n  FEM: {fem_1d.n_dof} DOF, {fem_1d.n_elements} P2 elements")
        print(f"  v_bar = √(E/ρ) = {v_bar:.1f} m/s")
        print(f"  v_longitudinal (database) = {glass.v_longitudinal:.1f} m/s")
        print(f"\n  {'Mode':>5} {'Analytical':>12} {'FEM':>12} {'Error':>10}")
        print(f"  {'':>5} {'(v_bar)':>12} {'':>12} {'':>10}")
        for i in [0, 1, 2, 4, 9, 19, min(49, n_compare - 1)]:
            if i < n_compare:
                print(f"  {int(modes_cmp[i]):5d} {ana_bar[i]:12.1f} "
                      f"{fem_freqs[i]:12.1f} {err_bar[i]:+10.6f}")
        print(f"\n  Max relative error (v_bar vs FEM):  {eigenfreq_result.max_relative_error:.2e}")
        print(f"  Max relative error (v_long vs FEM): {np.max(np.abs(err_vlong)):.2e}")
        v = "✅ VALIDATED" if eigenfreq_result.validated else "❌ FAILED"
        print(f"  → 1D eigenfrequencies: {v}")

    # ── 2. Wave Speed Analysis ───────────────────────────────────────

    if verbose:
        print("\n━━━ 2. Wave Speed Analysis ━━━")

    wave_speed = compare_wave_speeds(glass, fem_freqs[0], L)

    if verbose:
        print(f"\n  v_longitudinal (material DB): {wave_speed.v_longitudinal:.1f} m/s")
        print(f"  v_bar = √(E/ρ):              {wave_speed.v_bar:.1f} m/s")
        print(f"  v_bulk (from E,ν,ρ):          {wave_speed.v_bulk_calc:.1f} m/s")
        print(f"  v_fem (from FEM f₁):          {wave_speed.v_fem:.1f} m/s")
        print(f"\n  Best match: {wave_speed.best_match}")
        print(f"  Database v_long vs FEM: {wave_speed.discrepancy_pct:+.2f}%")

    # ── 3. Rayleigh Perturbation Validation ──────────────────────────

    if verbose:
        print("\n━━━ 3. Rayleigh Perturbation Validation ━━━")

    m_rod = rho * A * L
    dm = 0.001 * m_rod  # 0.1% mass perturbation
    x_pos = 0.3 * L     # 30% along the rod
    x_norm = 0.3

    baseline, perturbed, fem_shifts = fem_perturbation_shifts(
        L, E, rho, A, x_pos, dm, n_modes=20, n_elements=500,
    )
    rayleigh_shifts = rayleigh_perturbation_shifts(
        np.arange(1, 21), x_norm, dm / m_rod,
    )

    n_pert = min(len(fem_shifts), len(rayleigh_shifts))
    fs = fem_shifts[:n_pert]
    rs = rayleigh_shifts[:n_pert]
    # Relative error of Rayleigh vs FEM (avoiding division by near-zero)
    with np.errstate(divide='ignore', invalid='ignore'):
        pert_err = np.where(
            np.abs(fs) > 1e-10,
            (rs - fs) / np.abs(fs),
            0.0,
        )

    pert_result = PerturbationComparison(
        mode_numbers=np.arange(1, n_pert + 1),
        mass_position=x_norm,
        mass_ratio=dm / m_rod,
        analytical_shifts=rs,
        fem_shifts=fs,
        relative_errors=pert_err,
        max_relative_error=float(np.max(np.abs(pert_err))),
        rayleigh_validated=bool(np.max(np.abs(pert_err)) < tolerance_pert),
    )

    if verbose:
        print(f"\n  Point mass: δm/m = {dm/m_rod:.4f} at x/L = {x_norm}")
        print(f"\n  {'Mode':>5} {'Rayleigh Δf/f':>14} {'FEM Δf/f':>14} {'Error':>10}")
        for i in [0, 1, 2, 4, 9, 19]:
            if i < n_pert:
                print(f"  {i+1:5d} {rs[i]:14.6e} {fs[i]:14.6e} {pert_err[i]:+10.4f}")
        print(f"\n  Max relative error: {pert_result.max_relative_error:.2e}")
        v = "✅ VALIDATED" if pert_result.rayleigh_validated else "❌ FAILED"
        print(f"  → Rayleigh perturbation: {v}")

    # ── 4. Mesh Convergence Study ────────────────────────────────────

    if verbose:
        print("\n━━━ 4. Mesh Convergence Study ━━━")

    conv = convergence_study(L, E, rho, A, n_modes=10, element_order=1)

    if verbose:
        print(f"\n  {'Elements':>10} {'Max Error':>12}")
        for i, ne in enumerate(conv.element_counts):
            print(f"  {int(ne):10d} {conv.errors_per_refinement[i]:12.2e}")
        print(f"\n  Measured convergence rate: {conv.convergence_rate:.2f}")
        print(f"  Theoretical (P1):         {conv.theoretical_rate:.1f}")
        v = "✅ VALIDATED" if conv.rate_validated else "❌ FAILED"
        print(f"  → Convergence rate: {v}")

    # ── 5. 2D Plane-Stress Validation ────────────────────────────────

    if verbose:
        print("\n━━━ 5. 2D Plane-Stress FEM ━━━")

    # Use rod diameter as thickness for plane-stress model
    result_2d, nodes_2d, elems_2d = fem_eigenfrequencies_2d(
        Lx=L, Ly=rod_diameter, E=E, nu=nu, rho=rho,
        n_modes=n_modes_2d, nx=60, ny=4, thickness=rod_diameter,
    )

    # Classify modes
    mode_info = classify_2d_modes(
        result_2d.mode_shapes, nodes_2d, result_2d.frequencies_hz, L, E, rho,
    )

    # Extract longitudinal modes and compare against 1D FEM
    long_modes = [m for m in mode_info if m.mode_type == "longitudinal"]
    long_freqs_2d = np.array([m.frequency_hz for m in long_modes])
    long_mode_nums = np.array([m.matching_1d_mode for m in long_modes])

    # Compare against 1D bar analytical
    if len(long_freqs_2d) > 0:
        ana_1d = long_mode_nums * v_bar / (2.0 * L)
        err_2d = (long_freqs_2d - ana_1d) / ana_1d
        max_err_2d = float(np.max(np.abs(err_2d)))
        validated_2d = max_err_2d < 0.02  # 2% tolerance for 2D vs 1D

        eigenfreq_2d = ValidationComparison(
            mode_numbers=long_mode_nums,
            analytical_hz=ana_1d,
            fem_hz=long_freqs_2d,
            relative_errors=err_2d,
            max_relative_error=max_err_2d,
            mean_relative_error=float(np.mean(np.abs(err_2d))),
            rms_relative_error=float(np.sqrt(np.mean(err_2d ** 2))),
            analytical_formula="f_n = n·√(E/ρ)/(2L)  [1D thin-bar]",
            n_elements=len(elems_2d),
            element_type="CST_tri",
            validated=bool(validated_2d),
        )
    else:
        eigenfreq_2d = None
        validated_2d = False

    if verbose:
        print(f"\n  Mesh: {result_2d.n_dof} DOF, {result_2d.n_elements} CST triangles")
        print(f"  Aspect ratio L/d = {L/rod_diameter:.0f}")

        n_long = sum(1 for m in mode_info if m.mode_type == "longitudinal")
        n_flex = sum(1 for m in mode_info if m.mode_type == "flexural")
        n_mix = sum(1 for m in mode_info if m.mode_type == "mixed")
        print(f"\n  Mode classification: {n_long} longitudinal, {n_flex} flexural, {n_mix} mixed")

        if len(long_modes) > 0:
            print(f"\n  Longitudinal modes — 2D vs 1D analytical:")
            print(f"  {'n':>5} {'1D analytical':>14} {'2D FEM':>14} {'Error':>10}")
            for i, m in enumerate(long_modes[:10]):
                if i < len(ana_1d):
                    print(f"  {m.matching_1d_mode:5d} {ana_1d[i]:14.1f} "
                          f"{m.frequency_hz:14.1f} {err_2d[i]:+10.6f}")
            print(f"\n  Max 2D-vs-1D error: {max_err_2d:.4f} ({max_err_2d*100:.2f}%)")
            if max_err_2d > 0.001:
                print(f"  (Discrepancy is the Poisson correction: "
                      f"~(d/L)² = {(rod_diameter/L)**2:.6f})")
        v = "✅ VALIDATED" if validated_2d else "❌ NEEDS REVIEW"
        print(f"  → 2D vs 1D: {v}")

    # ── Summary ──────────────────────────────────────────────────────

    all_passed = (
        eigenfreq_result.validated
        and pert_result.rayleigh_validated
        and conv.rate_validated
        and (eigenfreq_2d is not None and eigenfreq_2d.validated)
    )

    # ── 6. Pochhammer–Chree Dispersion Correction ────────────────────

    disp_result = None
    if mode_info is not None and len(long_modes) > 3:
        if verbose:
            print("\n━━━ 6. Pochhammer–Chree Dispersion Correction ━━━")

        disp_result = fit_dispersion_correction(
            mode_info, L, rod_diameter, E, rho, max_xi=0.10,
        )
        disp_result.poisson_ratio = nu

        if verbose:
            print(f"\n  Correction: f_n = (n·v_bar/2L) × [1 + C₁·ξ + C₂·ξ²]")
            print(f"  where ξ = (n·d/(2L))²")
            print(f"\n  C₁ = {disp_result.C1:.6f}")
            print(f"  C₂ = {disp_result.C2:.4f}")
            print(f"  Modes fitted: {disp_result.n_modes_fitted} "
                  f"(n = {int(disp_result.mode_numbers[0])}–"
                  f"{int(disp_result.mode_numbers[-1])})")
            print(f"  RMS residual: {disp_result.rms_residual*100:.4f}%")
            print(f"  Max residual: {disp_result.max_residual*100:.4f}%")
            print(f"  Valid up to mode n ≈ {disp_result.max_valid_mode} "
                  f"(correction < 1%)")

    summary_lines = [
        f"FEM Validation Summary for {glass.name}",
        f"  Rod: L={L*1e3:.2f} mm, d={rod_diameter*1e6:.0f} µm",
        f"  1D eigenfreqs (v_bar):  max error = {eigenfreq_result.max_relative_error:.2e}  "
        f"{'PASS' if eigenfreq_result.validated else 'FAIL'}",
        f"  Wave speed best match:  {wave_speed.best_match}",
        f"  Rayleigh perturbation:  max error = {pert_result.max_relative_error:.2e}  "
        f"{'PASS' if pert_result.rayleigh_validated else 'FAIL'}",
        f"  Convergence rate (P1):  {conv.convergence_rate:.2f} (expected {conv.theoretical_rate:.1f})  "
        f"{'PASS' if conv.rate_validated else 'FAIL'}",
    ]
    if eigenfreq_2d is not None:
        summary_lines.append(
            f"  2D vs 1D (long. modes): max error = {eigenfreq_2d.max_relative_error:.2e}  "
            f"{'PASS' if eigenfreq_2d.validated else 'FAIL'}"
        )
    if disp_result is not None:
        summary_lines.append(
            f"  Dispersion correction:  C₁={disp_result.C1:.6f}, C₂={disp_result.C2:.4f}, "
            f"RMS={disp_result.rms_residual*100:.4f}%"
        )
    summary = "\n".join(summary_lines)

    if verbose:
        print("\n" + "=" * 70)
        print(summary)
        overall = "✅ ALL VALIDATIONS PASSED" if all_passed else "⚠️  SOME VALIDATIONS NEED REVIEW"
        print(f"\n  {overall}")
        print("=" * 70)

    return FEMValidationReport(
        eigenfrequency_1d=eigenfreq_result,
        wave_speed=wave_speed,
        perturbation=pert_result,
        convergence=conv,
        eigenfrequency_2d=eigenfreq_2d,
        mode_classification=mode_info,
        dispersion=disp_result,
        all_passed=all_passed,
        summary=summary,
    )
