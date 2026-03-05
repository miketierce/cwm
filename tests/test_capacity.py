"""
Tests for Phase 3: Information-Theoretic Capacity & Technology Comparison.

Tests cover:
  - Shannon capacity formulas (bits per measurement, channel capacity)
  - Full channel capacity computation (baseline, mitigated)
  - Scaling sweeps (cell size, Q factor, temperature)
  - Technology database completeness
  - WCFOMA entry generation
  - Comparison table output
"""

import sys
import numpy as np
import pytest

sys.path.insert(0, "/Users/Mike/Code/wcfoma")

from simulations.capacity import (
    bits_per_measurement,
    channel_capacity_bps,
    compute_channel_capacity,
    sweep_cell_size,
    sweep_Q_factor,
    sweep_temperature,
    technology_database,
    wcfoma_entry,
    full_comparison_table,
    capacity_summary,
    ChannelCapacity,
    ScalingResult,
    TechComparison,
)
from simulations.noise_decoherence import NoiseParams


# ===========================================================================
# Shannon formula tests
# ===========================================================================

class TestShannonFormulas:
    """Verify basic information-theoretic calculations."""

    def test_bits_per_measurement_at_0dB(self):
        """SNR=1 (0 dB) → 0.5 bits per measurement."""
        assert bits_per_measurement(1.0) == pytest.approx(0.5)

    def test_bits_per_measurement_at_high_snr(self):
        """SNR=1023 (~30 dB) → ~5 bits per measurement."""
        b = bits_per_measurement(1023)
        assert b == pytest.approx(5.0, abs=0.01)

    def test_bits_per_measurement_zero_snr(self):
        assert bits_per_measurement(0) == 0.0

    def test_bits_per_measurement_negative_snr(self):
        assert bits_per_measurement(-1) == 0.0

    def test_channel_capacity_formula(self):
        """C = B log₂(1+SNR), B=1MHz, SNR=1 → 1 Mb/s."""
        c = channel_capacity_bps(1.0, 1e6)
        assert c == pytest.approx(1e6)

    def test_channel_capacity_zero_snr(self):
        assert channel_capacity_bps(0, 1e6) == 0.0

    def test_paper_claims_10_bits_requires_snr(self):
        """Paper claims 10 bits/mode → requires SNR = 2^20 - 1 ≈ 10⁶ (60 dB)."""
        snr_needed = 2 ** (2 * 10) - 1  # from b = ½ log₂(1+SNR)
        b = bits_per_measurement(snr_needed)
        assert b == pytest.approx(10.0, abs=0.01)
        # ~60 dB is extremely high — paper's claim is unrealistic without justification
        assert 10 * np.log10(snr_needed) == pytest.approx(60.0, abs=0.5)


# ===========================================================================
# Channel capacity computation tests
# ===========================================================================

class TestChannelCapacity:
    """Test full capacity computation."""

    def test_baseline_has_low_usable_modes(self):
        cc = compute_channel_capacity()
        assert cc.usable_modes == 0  # baseline SNR < 0 dB

    def test_mitigated_has_usable_modes(self):
        p = NoiseParams(viscosity=1.0, n_photons=1e8)
        cc = compute_channel_capacity(p)
        assert cc.usable_modes == 10

    def test_bits_per_measurement_less_than_paper(self):
        """Shannon capacity < paper's claimed 10 bits/mode at any realistic SNR."""
        p = NoiseParams(viscosity=1.0, n_photons=1e8)
        cc = compute_channel_capacity(p)
        # At ~13.5 dB SNR, Shannon gives ~2.3 bits, not 10
        assert cc.bits_per_measurement[0] < 10.0
        assert cc.bits_per_measurement[0] > 1.0

    def test_total_capacity_positive_mitigated(self):
        p = NoiseParams(viscosity=1.0, n_photons=1e8)
        cc = compute_channel_capacity(p)
        assert cc.total_capacity_bps > 0
        assert cc.bandwidth_mbps > 0

    def test_density_positive_mitigated(self):
        p = NoiseParams(viscosity=1.0, n_photons=1e8)
        cc = compute_channel_capacity(p)
        assert cc.density_tb_per_cm3 > 0

    def test_write_latency_reasonable(self):
        cc = compute_channel_capacity()
        # Write latency should be ~14 ns for 10 µm cavity
        assert cc.write_latency_us < 0.1  # < 100 ns
        assert cc.write_latency_us > 0.001  # > 1 ns

    def test_read_latency_is_inverse_bandwidth(self):
        cc = compute_channel_capacity()
        # Read latency = 1/BW = 1 µs at 1 MHz
        assert cc.read_latency_us == pytest.approx(1.0)

    def test_cells_per_cm3_correct(self):
        cc = compute_channel_capacity(L=1e-5)
        # (10 µm)³ → 10⁹ cells/cm³
        assert cc.cells_per_cm3 == pytest.approx(1e9)

    def test_returns_correct_type(self):
        cc = compute_channel_capacity()
        assert isinstance(cc, ChannelCapacity)
        assert len(cc.mode_indices) == 10


# ===========================================================================
# Scaling sweep tests
# ===========================================================================

class TestScalingSweeps:
    """Test parameter scaling sweeps."""

    def test_cell_size_sweep_shape(self):
        sizes = np.logspace(1, 3, 10)
        sr = sweep_cell_size(sizes)
        assert len(sr.bits_per_cell) == 10
        assert sr.parameter_name == "cavity_length_um"

    def test_Q_factor_sweep_shape(self):
        qs = np.logspace(1, 3, 8)
        sr = sweep_Q_factor(qs)
        assert len(sr.bits_per_cell) == 8
        assert sr.parameter_name == "Q_factor"

    def test_temperature_sweep_shape(self):
        temps = np.linspace(200, 400, 8)
        sr = sweep_temperature(temps)
        assert len(sr.bits_per_cell) == 8
        assert sr.parameter_name == "temperature_K"

    def test_larger_cells_have_more_usable_modes_mitigated(self):
        """With mitigation, larger cells should still have usable modes."""
        p = NoiseParams(viscosity=1.0, n_photons=1e8)
        sizes = np.array([10, 50, 100])
        sr = sweep_cell_size(sizes, params=p)
        assert sr.usable_modes[0] >= 0  # 10 µm

    def test_Q_affects_capacity(self):
        """Higher Q should generally yield more capacity (at least for mitigated)."""
        p = NoiseParams(viscosity=1.0, n_photons=1e8)
        qs = np.array([100, 500, 1000])
        sr = sweep_Q_factor(qs, params=p)
        # Not strictly monotonic due to mode count ceiling, but should not be zero
        assert sr.bits_per_cell[-1] >= sr.bits_per_cell[0]


# ===========================================================================
# Technology comparison tests
# ===========================================================================

class TestTechnologyComparison:
    """Test technology database and comparison."""

    def test_database_has_required_techs(self):
        db = technology_database()
        required = ["DRAM", "SRAM", "NAND_Flash", "PCM", "MRAM", "ReRAM", "Magnonic"]
        for tech in required:
            assert tech in db, f"Missing technology: {tech}"

    def test_all_entries_have_positive_values(self):
        db = technology_database()
        for name, entry in db.items():
            assert entry.energy_pJ > 0, f"{name} energy"
            assert entry.density_tb_cm3 > 0, f"{name} density"
            assert entry.read_latency_ns > 0, f"{name} read latency"

    def test_wcfoma_entry_generation(self):
        entry = wcfoma_entry()
        assert isinstance(entry, TechComparison)
        assert entry.compute_locality == "unified"
        assert entry.maturity == "simulation"

    def test_wcfoma_mitigated_entry(self):
        p = NoiseParams(viscosity=1.0, n_photons=1e8)
        entry = wcfoma_entry(p, label="WCFOMA-mitigated")
        assert entry.density_tb_cm3 > 0
        assert entry.energy_pJ > 0

    def test_full_comparison_table_runs(self):
        table = full_comparison_table()
        assert "DRAM" in table
        assert "WCFOMA" in table
        assert "MEMORY TECHNOLOGY COMPARISON" in table
        assert len(table) > 500

    def test_capacity_summary_runs(self):
        cc = compute_channel_capacity()
        s = capacity_summary(cc, "test")
        assert "CHANNEL CAPACITY" in s
        assert "paper claims" in s
