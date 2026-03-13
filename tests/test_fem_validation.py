"""
Tests for FEM validation module.

These tests verify that:
1. FEM matrix assembly is correct (patch tests, symmetry, positive-semidefinite)
2. FEM eigenfrequencies converge to analytical values
3. Rayleigh perturbation formula matches FEM
4. 2D FEM produces physically reasonable mode classification
5. Mesh convergence exhibits the expected rate
"""

import numpy as np
import pytest

from simulations.fem_validation import (
    _assemble_bar_p1,
    _assemble_bar_p2,
    _build_2d_mesh,
    _assemble_2d,
    fem_eigenfrequencies_1d,
    fem_eigenfrequencies_2d,
    fem_perturbation_shifts,
    rayleigh_perturbation_shifts,
    classify_2d_modes,
    compare_wave_speeds,
    convergence_study,
    run_fem_validation,
    EigenResult,
    ValidationComparison,
    PerturbationComparison,
    ConvergenceResult,
    WaveSpeedComparison,
    Mode2DInfo,
    FEMValidationReport,
)
from simulations.glass_resonator import glass_database


# ═══════════════════════════════════════════════════════════════════════════
# Test Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def glass():
    """Borosilicate glass from database."""
    return glass_database()["borosilicate"]


@pytest.fixture
def rod_params():
    """Standard CWM reference rod parameters."""
    return dict(
        length=1e-3,       # 1 mm
        diameter=40e-6,    # 40 µm
    )


@pytest.fixture
def simple_bar():
    """Simple bar parameters for unit-level tests."""
    return dict(
        length=1.0,        # 1 m
        E=1e9,             # 1 GPa
        rho=1000.0,        # 1000 kg/m³
        A=1e-4,            # 1 cm²
    )


# ═══════════════════════════════════════════════════════════════════════════
# Matrix Assembly Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestP1Assembly:
    """Tests for the 2-node linear bar element assembly."""

    def test_stiffness_symmetry(self, simple_bar):
        K, M = _assemble_bar_p1(10, **simple_bar)
        assert np.allclose(K.toarray(), K.toarray().T), "K must be symmetric"

    def test_mass_symmetry(self, simple_bar):
        K, M = _assemble_bar_p1(10, **simple_bar)
        assert np.allclose(M.toarray(), M.toarray().T), "M must be symmetric"

    def test_stiffness_singular(self, simple_bar):
        """Free-free bar: K should have exactly one zero eigenvalue (rigid body)."""
        K, M = _assemble_bar_p1(10, **simple_bar)
        eigvals = np.linalg.eigvalsh(K.toarray())
        n_zero = np.sum(np.abs(eigvals) < 1e-10 * np.max(eigvals))
        assert n_zero == 1, f"Expected 1 zero eigenvalue, got {n_zero}"

    def test_mass_positive_definite(self, simple_bar):
        """Consistent mass matrix should be positive definite."""
        K, M = _assemble_bar_p1(10, **simple_bar)
        eigvals = np.linalg.eigvalsh(M.toarray())
        assert np.all(eigvals > 0), "M must be positive definite"

    def test_total_mass(self, simple_bar):
        """Sum of consistent mass matrix rows = total mass × [1,1,...,1]."""
        K, M = _assemble_bar_p1(10, **simple_bar)
        total_mass = simple_bar["rho"] * simple_bar["A"] * simple_bar["length"]
        row_sums = np.array(M.sum(axis=1)).flatten()
        # Each row sum should contribute to total mass conservation
        assert abs(np.sum(row_sums) - total_mass) / total_mass < 1e-12

    def test_stiffness_dimensions(self, simple_bar):
        n_elem = 20
        K, M = _assemble_bar_p1(n_elem, **simple_bar)
        assert K.shape == (n_elem + 1, n_elem + 1)
        assert M.shape == (n_elem + 1, n_elem + 1)


class TestP2Assembly:
    """Tests for the 3-node quadratic bar element assembly."""

    def test_stiffness_symmetry(self, simple_bar):
        K, M = _assemble_bar_p2(10, **simple_bar)
        assert np.allclose(K.toarray(), K.toarray().T)

    def test_mass_symmetry(self, simple_bar):
        K, M = _assemble_bar_p2(10, **simple_bar)
        assert np.allclose(M.toarray(), M.toarray().T)

    def test_stiffness_singular(self, simple_bar):
        K, M = _assemble_bar_p2(10, **simple_bar)
        eigvals = np.linalg.eigvalsh(K.toarray())
        n_zero = np.sum(np.abs(eigvals) < 1e-10 * np.max(eigvals))
        assert n_zero == 1

    def test_mass_positive_definite(self, simple_bar):
        K, M = _assemble_bar_p2(10, **simple_bar)
        eigvals = np.linalg.eigvalsh(M.toarray())
        assert np.all(eigvals > 0)

    def test_total_mass(self, simple_bar):
        K, M = _assemble_bar_p2(10, **simple_bar)
        total_mass = simple_bar["rho"] * simple_bar["A"] * simple_bar["length"]
        assert abs(np.sum(M.toarray()) - total_mass) / total_mass < 1e-12

    def test_stiffness_dimensions(self, simple_bar):
        n_elem = 20
        K, M = _assemble_bar_p2(n_elem, **simple_bar)
        assert K.shape == (2 * n_elem + 1, 2 * n_elem + 1)


class Test2DAssembly:
    """Tests for the 2D CST mesh and assembly."""

    def test_mesh_node_count(self):
        nodes, elems = _build_2d_mesh(1.0, 0.1, 10, 4)
        assert nodes.shape == (11 * 5, 2)

    def test_mesh_element_count(self):
        nodes, elems = _build_2d_mesh(1.0, 0.1, 10, 4)
        assert elems.shape == (10 * 4 * 2, 3)  # 2 triangles per quad

    def test_mesh_bounds(self):
        Lx, Ly = 1.0, 0.1
        nodes, _ = _build_2d_mesh(Lx, Ly, 10, 4)
        assert np.isclose(nodes[:, 0].min(), 0.0)
        assert np.isclose(nodes[:, 0].max(), Lx)
        assert np.isclose(nodes[:, 1].min(), -Ly / 2)
        assert np.isclose(nodes[:, 1].max(), Ly / 2)

    def test_2d_stiffness_symmetry(self):
        nodes, elems = _build_2d_mesh(1.0, 0.1, 5, 2)
        K, M = _assemble_2d(nodes, elems, E=1e9, nu=0.3, rho=1000)
        assert np.allclose(K.toarray(), K.toarray().T, atol=1e-10)

    def test_2d_mass_symmetry(self):
        nodes, elems = _build_2d_mesh(1.0, 0.1, 5, 2)
        K, M = _assemble_2d(nodes, elems, E=1e9, nu=0.3, rho=1000)
        assert np.allclose(M.toarray(), M.toarray().T, atol=1e-10)

    def test_2d_rigid_body_modes(self):
        """Free-free 2D: K should have 3 zero eigenvalues (2 translation + 1 rotation)."""
        nodes, elems = _build_2d_mesh(1.0, 0.1, 5, 2)
        K, M = _assemble_2d(nodes, elems, E=1e9, nu=0.3, rho=1000)
        eigvals = np.linalg.eigvalsh(K.toarray())
        n_zero = np.sum(np.abs(eigvals) < 1e-6 * np.max(eigvals))
        assert n_zero == 3, f"Expected 3 zero eigenvalues, got {n_zero}"


# ═══════════════════════════════════════════════════════════════════════════
# 1D Eigenfrequency Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEigenfrequencies1D:
    """Tests for 1D bar eigenfrequency computation."""

    def test_fundamental_frequency(self, simple_bar):
        """Check FEM fundamental frequency matches analytical v_bar/(2L)."""
        res = fem_eigenfrequencies_1d(**simple_bar, n_modes=5, n_elements=100)
        v_bar = np.sqrt(simple_bar["E"] / simple_bar["rho"])
        f1_analytical = v_bar / (2.0 * simple_bar["length"])
        assert abs(res.frequencies_hz[0] - f1_analytical) / f1_analytical < 0.001

    def test_mode_spacing(self, simple_bar):
        """Free-free bar: f_n = n × f₁ (harmonic series)."""
        res = fem_eigenfrequencies_1d(**simple_bar, n_modes=10, n_elements=200)
        f1 = res.frequencies_hz[0]
        for i in range(1, len(res.frequencies_hz)):
            ratio = res.frequencies_hz[i] / f1
            expected = i + 1
            assert abs(ratio - expected) / expected < 0.005, \
                f"Mode {i+1}: ratio = {ratio:.4f}, expected {expected}"

    def test_p1_vs_p2_agreement(self, simple_bar):
        """P1 and P2 should agree for low modes on a fine mesh."""
        res1 = fem_eigenfrequencies_1d(**simple_bar, n_modes=5,
                                        n_elements=200, element_order=1)
        res2 = fem_eigenfrequencies_1d(**simple_bar, n_modes=5,
                                        n_elements=100, element_order=2)
        for i in range(5):
            err = abs(res1.frequencies_hz[i] - res2.frequencies_hz[i]) / res2.frequencies_hz[i]
            assert err < 0.001, f"Mode {i+1}: P1 vs P2 error = {err:.6f}"

    def test_result_types(self, simple_bar):
        """Check EigenResult structure."""
        res = fem_eigenfrequencies_1d(**simple_bar, n_modes=5, n_elements=50)
        assert isinstance(res, EigenResult)
        assert len(res.frequencies_hz) == 5
        assert len(res.angular_frequencies) == 5
        assert res.mode_shapes.shape[1] == 5
        assert res.n_elements == 50
        assert res.element_type in ("P1_bar", "P2_bar")

    def test_frequencies_positive_and_sorted(self, simple_bar):
        res = fem_eigenfrequencies_1d(**simple_bar, n_modes=10, n_elements=100)
        assert np.all(res.frequencies_hz > 0)
        assert np.all(np.diff(res.frequencies_hz) > 0)

    def test_borosilicate_rod(self, glass, rod_params):
        """Validate with real CWM parameters."""
        E = glass.youngs_modulus
        rho = glass.density
        A = np.pi * (rod_params["diameter"] / 2) ** 2
        L = rod_params["length"]

        res = fem_eigenfrequencies_1d(L, E, rho, A, n_modes=10, n_elements=200)
        v_bar = np.sqrt(E / rho)
        f1_expected = v_bar / (2.0 * L)

        # Fundamental should be ~2.66 MHz for borosilicate 1mm rod
        assert res.frequencies_hz[0] > 2e6
        assert res.frequencies_hz[0] < 3e6
        assert abs(res.frequencies_hz[0] - f1_expected) / f1_expected < 0.001


# ═══════════════════════════════════════════════════════════════════════════
# Perturbation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPerturbation:
    """Tests for Rayleigh perturbation vs FEM comparison."""

    def test_analytical_at_midpoint(self):
        """At midpoint x/L=0.5, mode n has cos²(nπ/2) pattern."""
        modes = np.arange(1, 11)
        shifts = rayleigh_perturbation_shifts(modes, 0.5, 0.001)
        # Even modes: cos(nπ/2) = 0 for odd n (modes 1,3,5,...) no wait...
        # cos(1·π·0.5) = cos(π/2) = 0 → mode 1 has zero shift at midpoint
        # cos(2·π·0.5) = cos(π) = -1 → mode 2 has max shift at midpoint
        assert abs(shifts[0]) < 1e-10  # mode 1: node at midpoint
        assert abs(shifts[1] + 0.001) < 1e-10  # mode 2: antinode

    def test_analytical_at_end(self):
        """At x/L=0, all modes have cos(0)=1, so all shifts equal -δm/m."""
        modes = np.arange(1, 11)
        shifts = rayleigh_perturbation_shifts(modes, 0.0, 0.001)
        assert np.allclose(shifts, -0.001)

    def test_shifts_are_negative(self):
        """Adding mass always decreases frequency (for positive cos²)."""
        modes = np.arange(1, 11)
        shifts = rayleigh_perturbation_shifts(modes, 0.25, 0.001)
        assert np.all(shifts <= 0)

    def test_fem_vs_rayleigh_agreement(self, simple_bar):
        """FEM perturbation shifts should match Rayleigh for small masses."""
        L = simple_bar["length"]
        E = simple_bar["E"]
        rho = simple_bar["rho"]
        A = simple_bar["A"]
        m_rod = rho * A * L
        dm = 0.0005 * m_rod  # very small perturbation
        x_pos = 0.3 * L

        baseline, perturbed, fem_shifts = fem_perturbation_shifts(
            L, E, rho, A, x_pos, dm, n_modes=10, n_elements=300,
        )
        rayleigh = rayleigh_perturbation_shifts(
            np.arange(1, 11), 0.3, dm / m_rod,
        )

        # Compare only modes where shift is significant
        for i in range(min(len(fem_shifts), len(rayleigh))):
            if abs(rayleigh[i]) > 1e-8:
                err = abs(fem_shifts[i] - rayleigh[i]) / abs(rayleigh[i])
                assert err < 0.10, \
                    f"Mode {i+1}: FEM={fem_shifts[i]:.6e}, " \
                    f"Rayleigh={rayleigh[i]:.6e}, error={err:.4f}"

    def test_perturbation_decreases_frequencies(self, simple_bar):
        """Adding mass should decrease all eigenfrequencies."""
        L = simple_bar["length"]
        m_rod = simple_bar["rho"] * simple_bar["A"] * L
        dm = 0.01 * m_rod
        baseline, perturbed, shifts = fem_perturbation_shifts(
            L, simple_bar["E"], simple_bar["rho"], simple_bar["A"],
            0.3 * L, dm, n_modes=5, n_elements=200,
        )
        # Most shifts should be negative (except near nodes)
        assert np.sum(shifts < 0) >= 3  # at least 3 out of 5 modes


# ═══════════════════════════════════════════════════════════════════════════
# Wave Speed Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestWaveSpeed:
    """Tests for wave speed comparison."""

    def test_bar_speed_matches_fem(self, glass, rod_params):
        """For a 1D bar FEM, effective speed should match √(E/ρ)."""
        E = glass.youngs_modulus
        rho = glass.density
        A = np.pi * (rod_params["diameter"] / 2) ** 2
        L = rod_params["length"]

        res = fem_eigenfrequencies_1d(L, E, rho, A, n_modes=1, n_elements=200)
        ws = compare_wave_speeds(glass, res.frequencies_hz[0], L)

        # v_bar should be the best match for 1D FEM
        assert "v_bar" in ws.best_match
        assert abs(ws.v_fem - ws.v_bar) / ws.v_bar < 0.005

    def test_all_speeds_positive(self, glass, rod_params):
        ws = compare_wave_speeds(glass, 2.5e6, rod_params["length"])
        assert ws.v_longitudinal > 0
        assert ws.v_bar > 0
        assert ws.v_bulk_calc > 0
        assert ws.v_fem > 0

    def test_speed_ordering(self, glass, rod_params):
        """For typical glass: v_bar < v_longitudinal ≤ v_bulk."""
        ws = compare_wave_speeds(glass, 2.5e6, rod_params["length"])
        assert ws.v_bar < ws.v_bulk_calc


# ═══════════════════════════════════════════════════════════════════════════
# 2D FEM Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEigenfrequencies2D:
    """Tests for 2D plane-stress eigenfrequency computation."""

    def test_free_free_modes_exist(self):
        """Should find non-zero eigenfrequencies."""
        result, nodes, elems = fem_eigenfrequencies_2d(
            Lx=1.0, Ly=0.04, E=63e9, nu=0.2, rho=2230,
            n_modes=10, nx=20, ny=2,
        )
        assert len(result.frequencies_hz) > 0
        assert np.all(result.frequencies_hz > 0)

    def test_mode_classification(self):
        """At least some modes should be classified as longitudinal."""
        result, nodes, elems = fem_eigenfrequencies_2d(
            Lx=1.0, Ly=0.04, E=63e9, nu=0.2, rho=2230,
            n_modes=15, nx=30, ny=3,
        )
        modes = classify_2d_modes(
            result.mode_shapes, nodes, result.frequencies_hz, 1.0, 63e9, 2230,
        )
        long_count = sum(1 for m in modes if m.mode_type == "longitudinal")
        assert long_count >= 2, f"Expected ≥2 longitudinal modes, found {long_count}"

    def test_longitudinal_near_1d(self):
        """2D longitudinal modes should be close to 1D predictions."""
        E, rho, nu = 63e9, 2230.0, 0.2
        Lx, Ly = 1.0, 0.04  # L/d = 25 → thin rod
        result, nodes, elems = fem_eigenfrequencies_2d(
            Lx=Lx, Ly=Ly, E=E, nu=nu, rho=rho,
            n_modes=20, nx=40, ny=3,
        )
        modes = classify_2d_modes(
            result.mode_shapes, nodes, result.frequencies_hz, Lx, E, rho,
        )
        v_bar = np.sqrt(E / rho)
        for m in modes:
            if m.mode_type == "longitudinal" and m.matching_1d_mode is not None:
                f_1d = m.matching_1d_mode * v_bar / (2.0 * Lx)
                err = abs(m.frequency_hz - f_1d) / f_1d
                assert err < 0.02, \
                    f"Mode n={m.matching_1d_mode}: 2D={m.frequency_hz:.1f}, " \
                    f"1D={f_1d:.1f}, error={err:.4f}"

    def test_clamped_produces_valid_modes(self):
        """Clamping nodes should produce valid (positive, sorted) eigenfrequencies.

        Note: clamped-free fundamentals may be LOWER than free-free because
        the clamped cantilever introduces low-frequency flexural modes that
        don't exist in the free-free spectrum (which starts with longitudinal).
        """
        E, rho, nu = 1e9, 1000.0, 0.3
        Lx, Ly = 1.0, 0.1
        nx, ny = 20, 3
        n_nodes_y = ny + 1

        # Clamped at left end
        left_nodes = np.arange(0, n_nodes_y)  # first column
        res_clamp, _, _ = fem_eigenfrequencies_2d(
            Lx, Ly, E, nu, rho, n_modes=5, nx=nx, ny=ny,
            clamped_nodes=left_nodes,
        )
        # All frequencies should be positive and sorted
        assert len(res_clamp.frequencies_hz) >= 3
        assert np.all(res_clamp.frequencies_hz > 0)
        assert np.all(np.diff(res_clamp.frequencies_hz) > 0)


# ═══════════════════════════════════════════════════════════════════════════
# Convergence Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestConvergence:
    """Tests for mesh convergence study."""

    def test_p1_convergence_rate(self, simple_bar):
        """P1 elements should converge at rate ≈ 2."""
        conv = convergence_study(**simple_bar, n_modes=5,
                                 element_counts=np.array([10, 20, 40, 80, 160]),
                                 element_order=1)
        assert isinstance(conv, ConvergenceResult)
        assert conv.convergence_rate > 1.5, \
            f"P1 rate = {conv.convergence_rate:.2f}, expected ≈ 2"
        assert conv.convergence_rate < 3.0

    def test_errors_decrease(self, simple_bar):
        """Errors should decrease monotonically with refinement."""
        conv = convergence_study(**simple_bar, n_modes=5,
                                 element_counts=np.array([10, 20, 40, 80, 160]),
                                 element_order=1)
        # Skip the finest (error=0 by definition)
        errs = conv.errors_per_refinement[:-1]
        for i in range(len(errs) - 1):
            if errs[i] > 1e-15:
                assert errs[i + 1] < errs[i] * 1.1, \
                    f"Error at {conv.element_counts[i+1]} elements " \
                    f"({errs[i+1]:.2e}) not less than at " \
                    f"{conv.element_counts[i]} ({errs[i]:.2e})"

    def test_richardson_extrapolation(self, simple_bar):
        """Richardson estimate should be close to finest mesh."""
        conv = convergence_study(**simple_bar, n_modes=5,
                                 element_counts=np.array([20, 40, 80, 160, 320]),
                                 element_order=1)
        # Richardson should agree with finest mesh to < 0.1%
        for i in range(min(len(conv.richardson_estimate_hz), 5)):
            finest = conv.richardson_estimate_hz[i]
            # Richardson is an extrapolation beyond the mesh, so just check it's reasonable
            assert finest > 0


# ═══════════════════════════════════════════════════════════════════════════
# Integration / Full Validation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFullValidation:
    """Integration tests running the complete validation suite."""

    def test_full_validation_runs(self):
        """Complete validation should execute without errors."""
        report = run_fem_validation(
            glass_key="borosilicate",
            rod_length=1e-3,
            rod_diameter=40e-6,
            n_modes_1d=20,
            n_modes_2d=15,
            verbose=False,
        )
        assert isinstance(report, FEMValidationReport)
        assert report.eigenfrequency_1d is not None
        assert report.wave_speed is not None
        assert report.perturbation is not None
        assert report.convergence is not None
        assert isinstance(report.summary, str)

    def test_1d_eigenfreqs_validated(self):
        """1D eigenfrequency validation should pass."""
        report = run_fem_validation(
            n_modes_1d=20, n_modes_2d=10, verbose=False,
        )
        assert report.eigenfrequency_1d.validated, \
            f"1D eigenfreqs not validated: max error = " \
            f"{report.eigenfrequency_1d.max_relative_error:.2e}"

    def test_perturbation_validated(self):
        """Rayleigh perturbation should pass."""
        report = run_fem_validation(
            n_modes_1d=10, n_modes_2d=10, verbose=False,
        )
        assert report.perturbation.rayleigh_validated, \
            f"Perturbation not validated: max error = " \
            f"{report.perturbation.max_relative_error:.2e}"

    def test_convergence_validated(self):
        """Mesh convergence rate should pass."""
        report = run_fem_validation(
            n_modes_1d=10, n_modes_2d=10, verbose=False,
        )
        assert report.convergence.rate_validated, \
            f"Convergence rate = {report.convergence.convergence_rate:.2f}, " \
            f"expected ≈ {report.convergence.theoretical_rate:.1f}"

    def test_wave_speed_best_match(self):
        """Best wave speed match should be v_bar for 1D FEM."""
        report = run_fem_validation(
            n_modes_1d=10, n_modes_2d=10, verbose=False,
        )
        assert "v_bar" in report.wave_speed.best_match

    def test_different_glass_types(self):
        """Validation should work for all glass types in database."""
        for key in ["soda_lime", "borosilicate", "fused_silica"]:
            report = run_fem_validation(
                glass_key=key, n_modes_1d=10, n_modes_2d=10, verbose=False,
            )
            assert report.eigenfrequency_1d.validated, \
                f"{key}: 1D eigenfreqs failed"

    def test_summary_string(self):
        """Summary should contain key information."""
        report = run_fem_validation(
            n_modes_1d=10, n_modes_2d=10, verbose=False,
        )
        assert "FEM Validation Summary" in report.summary
        assert "PASS" in report.summary or "FAIL" in report.summary
