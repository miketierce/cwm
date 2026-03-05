"""
Tests for MEMS Q-factor prediction model.

Validates:
  - Individual loss mechanism calculations (material, anchor, TED, surface, gas)
  - Total Q budget assembly and dominant-loss identification
  - Physical sanity (Q > 0, losses sum correctly, known regimes)
  - Parametric sweeps (tether width, pressure, rod length, mode number)
  - Design feasibility finder
  - Architecture impact calculations (n_max, bits, density)
  - Known limits and edge cases
"""
import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ============================================================
# Material Q Tests
# ============================================================

class TestMaterialQ:
    """Test intrinsic material Q computation."""

    def test_borosilicate_Q_value(self):
        from simulations.glass_resonator import glass_database
        from simulations.mems_q_model import compute_Q_material
        glass = glass_database()["borosilicate"]
        result = compute_Q_material(glass)
        assert result.Q_value == 10_000.0
        assert result.loss == pytest.approx(1e-4)

    def test_fused_silica_Q_highest(self):
        from simulations.glass_resonator import glass_database
        from simulations.mems_q_model import compute_Q_material
        db = glass_database()
        for name, glass in db.items():
            result = compute_Q_material(glass)
            if name == "fused_silica":
                assert result.Q_value == 100_000.0
            else:
                assert result.Q_value < 100_000.0

    def test_all_materials_positive_Q(self):
        from simulations.glass_resonator import glass_database
        from simulations.mems_q_model import compute_Q_material
        db = glass_database()
        for name, glass in db.items():
            result = compute_Q_material(glass)
            assert result.Q_value > 0
            assert result.loss > 0
            assert result.name == "Material (intrinsic)"

    def test_loss_is_inverse_Q(self):
        from simulations.glass_resonator import glass_database
        from simulations.mems_q_model import compute_Q_material
        glass = glass_database()["soda_lime"]
        result = compute_Q_material(glass)
        assert result.loss == pytest.approx(1.0 / result.Q_value)


# ============================================================
# Anchor Loss Tests
# ============================================================

class TestAnchorLoss:
    """Test anchor loss model for MEMS resonators."""

    def test_default_anchor_positive_Q(self):
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_anchor, AnchorDesign
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]
        anchor = AnchorDesign()
        result = compute_Q_anchor(rod, glass, anchor, mode_number=1)
        assert result.Q_value > 0
        assert result.loss > 0

    def test_wider_tether_lower_Q(self):
        """Wider tethers → more energy leakage → lower Q."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_anchor, AnchorDesign
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]

        thin = AnchorDesign(tether_width=2e-6, tether_thickness=2e-6)
        thick = AnchorDesign(tether_width=15e-6, tether_thickness=15e-6)

        Q_thin = compute_Q_anchor(rod, glass, thin).Q_value
        Q_thick = compute_Q_anchor(rod, glass, thick).Q_value
        assert Q_thin > Q_thick, "Thinner tethers should yield higher Q"

    def test_longer_tether_higher_Q(self):
        """Longer tethers → more acoustic isolation → higher Q."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_anchor, AnchorDesign
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]

        short = AnchorDesign(tether_length=10e-6)
        long = AnchorDesign(tether_length=200e-6)

        Q_short = compute_Q_anchor(rod, glass, short).Q_value
        Q_long = compute_Q_anchor(rod, glass, long).Q_value
        assert Q_long > Q_short, "Longer tethers should yield higher Q"

    def test_isolation_trenches_improve_Q(self):
        """Acoustic isolation trenches should increase Q_anchor."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_anchor, AnchorDesign
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]

        no_trench = AnchorDesign(isolation_trenches=False)
        trench = AnchorDesign(isolation_trenches=True)

        Q_no = compute_Q_anchor(rod, glass, no_trench).Q_value
        Q_yes = compute_Q_anchor(rod, glass, trench).Q_value
        assert Q_yes > Q_no, "Isolation trenches should improve Q"
        assert Q_yes >= 10 * Q_no * 0.9  # ~10× improvement

    def test_single_anchor_better_than_two(self):
        """One anchor leaks less energy than two."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_anchor, AnchorDesign
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]

        one = AnchorDesign(n_anchors=1)
        two = AnchorDesign(n_anchors=2)

        Q_one = compute_Q_anchor(rod, glass, one).Q_value
        Q_two = compute_Q_anchor(rod, glass, two).Q_value
        assert Q_one > Q_two

    def test_nodal_mounting_helps_even_modes(self):
        """Nodal mounting at midpoint: even modes see minimal anchor loss."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_anchor, AnchorDesign
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]

        nodal = AnchorDesign(attachment_position="nodal")

        Q_even = compute_Q_anchor(rod, glass, nodal, mode_number=2).Q_value
        Q_odd = compute_Q_anchor(rod, glass, nodal, mode_number=1).Q_value
        # Even modes at midpoint should see much higher Q_anchor
        assert Q_even > Q_odd * 10

    def test_large_tether_low_Q(self):
        """Very wide tethers should give low but positive Q_anchor."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_anchor, AnchorDesign
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]
        # Huge tether = lots of leakage
        huge = AnchorDesign(tether_width=18e-6, tether_thickness=18e-6,
                            tether_length=5e-6)
        result = compute_Q_anchor(rod, glass, huge)
        assert result.Q_value > 0
        # Should be much lower than thin-tether design
        thin = AnchorDesign(tether_width=2e-6, tether_thickness=2e-6,
                            tether_length=50e-6)
        result_thin = compute_Q_anchor(rod, glass, thin)
        assert result_thin.Q_value > result.Q_value * 10


# ============================================================
# Thermoelastic Damping (TED) Tests
# ============================================================

class TestThermoelasticDamping:
    """Test Zener/Lifshitz-Roukes thermoelastic damping model."""

    def test_TED_positive_Q(self):
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_TED
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]
        result = compute_Q_TED(rod, glass, frequency=2.75e6)
        assert result.Q_value > 0
        assert result.loss >= 0

    def test_TED_peaks_at_Debye(self):
        """TED loss should peak when ωτ ≈ 1 and decrease on both sides."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_TED, THERMAL_CONDUCTIVITY, SPECIFIC_HEAT
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]

        # Compute thermal relaxation time
        kappa = THERMAL_CONDUCTIVITY["borosilicate"]
        C_p = SPECIFIC_HEAT["borosilicate"]
        D_th = kappa / (glass.density * C_p)
        tau = rod.diameter**2 / (np.pi**2 * D_th)
        f_debye = 1.0 / (2 * np.pi * tau)  # frequency where ωτ = 1

        # Compute TED at three frequencies
        Q_low = compute_Q_TED(rod, glass, f_debye * 0.01).Q_value
        Q_peak = compute_Q_TED(rod, glass, f_debye).Q_value
        Q_high = compute_Q_TED(rod, glass, f_debye * 100).Q_value

        # At the peak, Q should be lowest (most loss)
        assert Q_peak < Q_low, "Q at Debye peak should be lower than at low freq"
        assert Q_peak < Q_high, "Q at Debye peak should be lower than at high freq"

    def test_fused_silica_TED_better_than_borosilicate(self):
        """Fused silica has lower α → lower TED loss."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_TED

        freq = 2.75e6
        rod_b = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        rod_f = RodGeometry(length=1e-3, diameter=40e-6, glass_type="fused_silica")
        glass_b = glass_database()["borosilicate"]
        glass_f = glass_database()["fused_silica"]

        Q_b = compute_Q_TED(rod_b, glass_b, freq).Q_value
        Q_f = compute_Q_TED(rod_f, glass_f, freq).Q_value
        assert Q_f > Q_b, "Fused silica should have higher Q_TED (lower α)"

    def test_TED_very_high_for_mems_glass(self):
        """At MEMS frequencies, glass should be in adiabatic regime → very high Q_TED."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_TED
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]
        result = compute_Q_TED(rod, glass, frequency=2.75e6)
        # TED should NOT be the limiting factor for MEMS glass
        assert result.Q_value > 50_000, f"Q_TED={result.Q_value:.0f} too low for glass MEMS"

    def test_larger_diameter_shifts_debye_peak(self):
        """Larger diameter → longer τ → Debye peak at lower frequency."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_TED, THERMAL_CONDUCTIVITY, SPECIFIC_HEAT
        glass = glass_database()["borosilicate"]
        kappa = THERMAL_CONDUCTIVITY["borosilicate"]
        C_p = SPECIFIC_HEAT["borosilicate"]
        D_th = kappa / (glass.density * C_p)

        for d in [20e-6, 40e-6, 100e-6]:
            tau = d**2 / (np.pi**2 * D_th)
            f_debye = 1.0 / (2 * np.pi * tau)
            rod = RodGeometry(length=1e-3, diameter=d, glass_type="borosilicate")
            # At f >> f_debye, Q should be high (adiabatic)
            Q_high_f = compute_Q_TED(rod, glass, f_debye * 100).Q_value
            assert Q_high_f > 100_000


# ============================================================
# Surface Loss Tests
# ============================================================

class TestSurfaceLoss:
    """Test surface loss from defect layer."""

    def test_surface_loss_positive(self):
        from simulations.glass_resonator import RodGeometry
        from simulations.mems_q_model import compute_Q_surface
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        result = compute_Q_surface(rod)
        assert result.Q_value > 0
        assert result.loss > 0

    def test_thinner_rod_more_surface_loss(self):
        """Smaller rods have higher S/V → more surface loss."""
        from simulations.glass_resonator import RodGeometry
        from simulations.mems_q_model import compute_Q_surface
        rod_big = RodGeometry(length=1e-3, diameter=100e-6)
        rod_small = RodGeometry(length=1e-3, diameter=10e-6)

        Q_big = compute_Q_surface(rod_big).Q_value
        Q_small = compute_Q_surface(rod_small).Q_value
        assert Q_big > Q_small, "Larger rod should have less surface loss"

    def test_thicker_defect_layer_more_loss(self):
        """Thicker defect layer → more volume fraction → more loss."""
        from simulations.glass_resonator import RodGeometry
        from simulations.mems_q_model import compute_Q_surface, SurfaceProperties
        rod = RodGeometry(length=1e-3, diameter=40e-6)

        thin_defect = SurfaceProperties(defect_layer_thickness=1e-9)
        thick_defect = SurfaceProperties(defect_layer_thickness=50e-9)

        Q_thin = compute_Q_surface(rod, thin_defect).Q_value
        Q_thick = compute_Q_surface(rod, thick_defect).Q_value
        assert Q_thin > Q_thick

    def test_surface_loss_not_dominant_at_40um(self):
        """For 40 µm diameter rods, surface loss should not dominate."""
        from simulations.glass_resonator import RodGeometry
        from simulations.mems_q_model import compute_Q_surface
        rod = RodGeometry(length=1e-3, diameter=40e-6)
        result = compute_Q_surface(rod)
        # Surface Q should be well above 10,000 for reasonable defect layers
        assert result.Q_value > 10_000


# ============================================================
# Gas Damping Tests
# ============================================================

class TestGasDamping:
    """Test gas damping model."""

    def test_vacuum_no_gas_loss(self):
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_gas, OperatingConditions
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]
        cond = OperatingConditions(gas_type="vacuum")
        result = compute_Q_gas(rod, glass, 2.75e6, cond)
        assert result.Q_value == np.inf
        assert result.loss == 0.0

    def test_low_pressure_very_high_Q(self):
        """At 1 Pa (~0.01 mbar), gas damping should be negligible."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_gas, OperatingConditions
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]
        cond = OperatingConditions(pressure=1.0)
        result = compute_Q_gas(rod, glass, 2.75e6, cond)
        assert result.Q_value > 100_000, f"Q_gas at 1 Pa should be very high, got {result.Q_value:.0f}"

    def test_atmospheric_pressure_low_Q(self):
        """At 1 atm, gas damping should severely limit Q."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_gas, OperatingConditions
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]
        cond = OperatingConditions(pressure=101325.0)  # 1 atm
        result = compute_Q_gas(rod, glass, 2.75e6, cond)
        # At atmospheric, gas damping is dominant for MEMS resonators
        # Q typically 100-10,000
        assert result.Q_value < 1e6

    def test_higher_pressure_lower_Q(self):
        """More gas → more damping → lower Q."""
        from simulations.glass_resonator import glass_database, RodGeometry
        from simulations.mems_q_model import compute_Q_gas, OperatingConditions
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        glass = glass_database()["borosilicate"]

        Q_low_P = compute_Q_gas(rod, glass, 2.75e6,
                                OperatingConditions(pressure=10.0)).Q_value
        Q_high_P = compute_Q_gas(rod, glass, 2.75e6,
                                 OperatingConditions(pressure=10000.0)).Q_value
        assert Q_low_P > Q_high_P


# ============================================================
# Total Q Budget Tests
# ============================================================

class TestQBudget:
    """Test complete Q budget assembly."""

    def test_default_budget_returns_valid(self):
        from simulations.mems_q_model import compute_Q_budget
        result = compute_Q_budget()
        assert result.Q_total > 0
        assert result.Q_total < result.Q_material
        assert result.dominant_loss != ""
        assert len(result.components) == 5
        assert len(result.loss_budget) == 5

    def test_total_Q_less_than_any_component(self):
        """Total Q must be less than or equal to the smallest component Q."""
        from simulations.mems_q_model import compute_Q_budget
        result = compute_Q_budget()
        min_component_Q = min(c.Q_value for c in result.components
                              if np.isfinite(c.Q_value))
        assert result.Q_total <= min_component_Q * 1.001  # small tolerance

    def test_loss_budget_sums_to_one(self):
        """Fractional loss contributions should sum to 1."""
        from simulations.mems_q_model import compute_Q_budget
        result = compute_Q_budget()
        total_frac = sum(result.loss_budget.values())
        assert total_frac == pytest.approx(1.0, abs=1e-10)

    def test_exactly_one_dominant(self):
        """Exactly one component should be marked dominant."""
        from simulations.mems_q_model import compute_Q_budget
        result = compute_Q_budget()
        n_dominant = sum(1 for c in result.components if c.is_dominant)
        assert n_dominant == 1

    def test_dominant_has_highest_loss(self):
        """The dominant component should have the highest loss."""
        from simulations.mems_q_model import compute_Q_budget
        result = compute_Q_budget()
        dominant = [c for c in result.components if c.is_dominant][0]
        for c in result.components:
            assert c.loss <= dominant.loss + 1e-15

    def test_vacuum_improves_Q(self):
        """Lower pressure should improve total Q."""
        from simulations.glass_resonator import RodGeometry
        from simulations.mems_q_model import compute_Q_budget, OperatingConditions
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")

        Q_atm = compute_Q_budget(rod=rod,
            conditions=OperatingConditions(pressure=101325.0)).Q_total
        Q_vac = compute_Q_budget(rod=rod,
            conditions=OperatingConditions(pressure=1.0)).Q_total
        assert Q_vac > Q_atm

    def test_architecture_impact_calculated(self):
        """Budget should compute n_max, bits, density."""
        from simulations.mems_q_model import compute_Q_budget
        result = compute_Q_budget()
        assert result.n_max_modes > 0
        assert result.bits_per_mode > 0
        assert result.total_bits > 0
        assert result.density_gbit_cm3 > 0
        assert result.frequency > 0

    def test_n_max_uses_Q_total_not_material(self):
        """n_max should use Q_total, which is lower than Q_material."""
        from simulations.mems_q_model import compute_Q_budget
        import math
        result = compute_Q_budget()
        # n_max with Q_total
        expected = int(1.0 / (2 * result.glass.alpha_thermal *
                              result.conditions.delta_T + 1.0 / result.Q_total))
        assert result.n_max_modes == expected

    def test_mode_number_changes_frequency(self):
        """Different mode numbers should analyze different frequencies."""
        from simulations.mems_q_model import compute_Q_budget
        r1 = compute_Q_budget(mode_number=1)
        r10 = compute_Q_budget(mode_number=10)
        assert r10.frequency == pytest.approx(10 * r1.frequency)


# ============================================================
# Parametric Sweep Tests
# ============================================================

class TestSweeps:
    """Test parametric sweep functions."""

    def test_tether_sweep_monotonic(self):
        """Wider tethers should generally lower total Q."""
        from simulations.mems_q_model import sweep_tether_width
        results = sweep_tether_width()
        Qs = [r.Q_total for r in results]
        # Should be generally decreasing (allow small non-monotonicities)
        assert Qs[0] > Qs[-1], "Q should decrease with tether width"

    def test_pressure_sweep_returns_results(self):
        from simulations.mems_q_model import sweep_pressure
        results = sweep_pressure()
        assert len(results) > 0
        # All should have positive Q
        for r in results:
            assert r.Q_total > 0

    def test_rod_length_sweep_returns_results(self):
        from simulations.mems_q_model import sweep_rod_length
        results = sweep_rod_length()
        assert len(results) > 0
        # All should have positive Q
        for r in results:
            assert r.Q_total > 0

    def test_mode_number_sweep(self):
        from simulations.mems_q_model import sweep_mode_number
        results = sweep_mode_number()
        assert len(results) > 0
        # Mode 1 frequency should be fundamental
        assert results[0].mode_number == 1


# ============================================================
# Design Feasibility Tests
# ============================================================

class TestDesignFeasibility:
    """Test the Q threshold finder."""

    def test_feasibility_borosilicate_Q5000(self):
        """Q > 5,000 should be feasible for borosilicate at 1mm."""
        from simulations.mems_q_model import find_Q_threshold_design
        result = find_Q_threshold_design(Q_target=5000, glass_type="borosilicate")
        assert result["feasible"], f"Q=5000 should be feasible: {result}"
        assert result["Q_material"] == 10_000
        assert result["min_tether_width_um"] is not None

    def test_feasibility_fused_silica_Q50000(self):
        """Q > 50,000 should be feasible for fused silica."""
        from simulations.mems_q_model import find_Q_threshold_design
        result = find_Q_threshold_design(Q_target=50000, glass_type="fused_silica")
        assert result["feasible"], f"Q=50000 should be feasible for fused silica"

    def test_infeasible_when_material_Q_too_low(self):
        """Can't exceed material Q — should report infeasible."""
        from simulations.mems_q_model import find_Q_threshold_design
        result = find_Q_threshold_design(Q_target=20000, glass_type="borosilicate")
        # Material Q = 10,000 < target 20,000 → infeasible
        assert not result["feasible"]

    def test_feasibility_reports_vacuum_requirement(self):
        """Should indicate whether vacuum packaging is needed."""
        from simulations.mems_q_model import find_Q_threshold_design
        result = find_Q_threshold_design(Q_target=5000, glass_type="borosilicate")
        assert "vacuum_required" in result


# ============================================================
# Physical Sanity Checks
# ============================================================

class TestPhysicalSanity:
    """Sanity checks against known MEMS resonator behavior."""

    def test_mems_Q_in_literature_range(self):
        """MEMS glass resonators achieve Q = 1,000-50,000 (Nguyen 2007).
        Our model should predict Q in this range for reasonable designs."""
        from simulations.glass_resonator import RodGeometry
        from simulations.mems_q_model import (compute_Q_budget, AnchorDesign,
                                               OperatingConditions)
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        anchor = AnchorDesign(tether_width=5e-6, tether_thickness=5e-6,
                              tether_length=50e-6)
        conditions = OperatingConditions(pressure=1.0)  # low vacuum
        result = compute_Q_budget(rod=rod, anchor=anchor, conditions=conditions)
        # Should be in reasonable MEMS range
        assert 500 < result.Q_total < 100_000, \
            f"Q_total={result.Q_total:.0f} outside expected MEMS range"

    def test_anchor_loss_dominates_with_wide_tethers(self):
        """With wide tethers (15µm), anchor loss should dominate over material
        loss in vacuum — the common MEMS pathology we're trying to avoid."""
        from simulations.glass_resonator import RodGeometry
        from simulations.mems_q_model import (compute_Q_budget, AnchorDesign,
                                               OperatingConditions)
        rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="borosilicate")
        # Wide tethers = poor isolation = anchor-loss dominated
        anchor = AnchorDesign(tether_width=15e-6, tether_thickness=15e-6,
                              tether_length=10e-6)
        conditions = OperatingConditions(pressure=1.0)
        result = compute_Q_budget(rod=rod, anchor=anchor, conditions=conditions)
        assert result.loss_budget["Anchor loss"] > 0.3, \
            f"Anchor loss fraction={result.loss_budget['Anchor loss']:.2f}, expected dominant with wide tethers"
        # But with thin tethers (5µm), anchor loss should NOT dominate
        thin_anchor = AnchorDesign(tether_width=5e-6, tether_thickness=5e-6)
        thin_result = compute_Q_budget(rod=rod, anchor=thin_anchor, conditions=conditions)
        assert thin_result.loss_budget["Anchor loss"] < 0.2, \
            f"Thin-tether anchor loss={thin_result.loss_budget['Anchor loss']:.2f}, expected small"

    def test_macro_rod_Q_near_material(self):
        """A 150mm rod (macro prototype) with small tethers should have Q
        approaching Q_material since L/w_eff is very large."""
        from simulations.glass_resonator import RodGeometry
        from simulations.mems_q_model import (compute_Q_budget, AnchorDesign,
                                               OperatingConditions)
        rod = RodGeometry(length=0.15, diameter=6e-3, glass_type="borosilicate")
        # Macro rod held by thin supports (like our prototype resting on foam)
        anchor = AnchorDesign(tether_width=0.5e-3, tether_thickness=0.5e-3,
                              tether_length=10e-3)
        conditions = OperatingConditions(pressure=1.0)  # in vacuum for clarity
        result = compute_Q_budget(rod=rod, anchor=anchor, conditions=conditions)
        # L/w_eff = 150mm/0.5mm = 300 → Q_anchor very high
        # Total Q should approach material Q (10,000)
        assert result.Q_total > 5000, f"Macro rod Q={result.Q_total:.0f}, expected >5000"
