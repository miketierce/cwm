"""Focused tests for the existing-data quantum-transition analysis."""

import math

import numpy as np
import pytest

from tools.quantum_transition_preliminary import (
    _fit_harmonics,
    _thermal_row,
    analyze_h_matrix,
    analyze_intermodulation,
    analyze_phase_interference,
    simulate_rate_envelope,
)


def test_first_harmonic_fit_recovers_ideal_interference():
    phases = np.arange(0.0, 360.0, 15.0)
    energy = 4.0 + 2.0 * np.cos(np.deg2rad(phases - 35.0))

    result = _fit_harmonics(phases.tolist(), energy.tolist())

    assert result["r2_first_harmonic"] == 1.0
    assert result["r2_first_harmonic_loo"] == 1.0
    assert result["delta_r2_second_harmonic"] == pytest.approx(0.0, abs=1e-12)


def test_thermal_row_uses_frozen_rate_convention():
    row = _thermal_row(frequency_hz=10e6, q=1e4, temperature_k=300.0)

    assert row["gamma_m_over_2pi_hz"] == 1e3
    assert row["gamma_up_over_2pi_hz"] == row["gamma_m_over_2pi_hz"] * row["n_th"]
    assert row["gamma_sigma_over_2pi_hz"] == (
        row["gamma_m_over_2pi_hz"] * (2.0 * row["n_th"] + 1.0)
    )


def test_saved_data_bounds_are_reproducible():
    phase = analyze_phase_interference()
    intermod = analyze_intermodulation()
    h_matrix = analyze_h_matrix()

    assert phase["sweep_count"] == 18
    assert intermod["positive_products_ge_3_sigma"] == 0
    assert h_matrix["acquisition_channel_ceiling"] == 2


def test_rate_envelope_cq_one_coupling_is_self_consistent():
    envelope = simulate_rate_envelope()
    rows = [
        row
        for row in envelope["rows"]
        if row["temperature_k"] == 300.0 and row["frequency_hz"] == 10e6
    ]

    assert len(rows) == 3
    for row in rows:
        expected = 0.5 * math.sqrt(
            1e3 * row["gamma_sigma_over_2pi_hz"]
        )
        assert row["required_g_over_2pi_hz_for_cq_1"]["1000"] == expected