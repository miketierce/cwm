"""Focused tests for the data-calibrated template-bank simulations."""

import numpy as np
import pytest

from tools.template_bank_hypothesis_sim import (
    PATTERNS,
    _layout_score,
    _query_matrix,
    _wilson_interval,
    direct_match_simulation,
    drift_corrected_e3,
    load_e3,
    multi_cell_confound_audit,
    rayleigh_model_audit,
    sample_size_simulation,
)


@pytest.fixture(scope="module")
def dataset():
    return load_e3()


@pytest.fixture(scope="module")
def audit(dataset):
    return drift_corrected_e3(dataset)


def test_drift_correction_uses_actual_acquisition_time(dataset, audit):
    assert dataset["times_s"] == {
        "bare": 0.0,
        "A": 344.0,
        "B": 972.0,
        "C": 1366.0,
        "bare2": 1620.0,
    }
    corrected = np.asarray(audit["linear_drift_corrected_shifts_hz"])
    assert corrected.shape == (3, 5)
    assert corrected[0, 0] == pytest.approx(-71.2345679)


def test_frequency_constrained_rayleigh_fits_respect_bound(dataset, audit):
    result = rayleigh_model_audit(dataset, audit)

    assert len(result["fitted_channels"]) == 5
    for channel in result["fitted_channels"]:
        fit = channel["best_frequency_constrained_fit"]
        assert abs(fit["frequency_relative_error"]) <= 0.30
        assert fit["scale_hz"] >= 0.0


def test_unsmoothed_measured_peak_query_matrix_is_diagonal(dataset):
    channel = "25mm NW"
    targets = [56000, 86000, 91000]
    records = dataset["records"]
    queries = np.asarray(
        [
            [records[pattern][(target, channel)]["f0_hz"] for target in targets]
            for pattern in PATTERNS
        ]
    )
    matrix = _query_matrix(
        records,
        channel,
        targets,
        queries,
        offsets_hz=np.array([0.0]),
        smooth_bins=0.0,
    )

    np.testing.assert_array_equal(np.argmax(matrix, axis=0), np.arange(3))
    np.testing.assert_array_equal(np.argmax(matrix, axis=1), np.arange(3))


def test_exact_peak_robustness_degrades_with_large_jitter(dataset):
    result = direct_match_simulation(dataset)
    rows = [
        row
        for row in result["robustness_grid"]
        if row["design"] == "exact_peak" and row["power_gain_cv"] == 0.25
    ]
    at_zero = next(row for row in rows if row["common_rewrite_sigma_hz"] == 0.0)
    at_100 = next(row for row in rows if row["common_rewrite_sigma_hz"] == 100.0)

    assert at_zero["gain_calibrated_bank_accuracy"] > 0.95
    assert at_100["gain_calibrated_bank_accuracy"] < 0.60


def test_symmetric_corner_layout_is_degenerate():
    assignments = [
        [(2, 3), (3, 2), (2, 4), (4, 2), (3, 3)],
    ]
    regular = np.array(
        [[0.25, 0.25], [0.25, 0.75], [0.75, 0.25], [0.75, 0.75]]
    )
    score = _layout_score(
        regular,
        assignments,
        mode_weights=np.ones(5),
        noise_sigma=np.ones(5),
    )

    assert score == pytest.approx(0.0, abs=1e-12)


def test_sample_size_gate_and_wilson_interval():
    lower, upper = _wilson_interval(80, 100)
    assert lower < 0.8 < upper

    result = sample_size_simulation()
    required = {
        row["assumed_true_accuracy"]: row[
            "minimum_independent_trials_for_wilson_lower_above_control"
        ]
        for row in result["wilson_gate_planning"]
    }
    assert required == {0.8: 40, 0.85: 25, 0.9: 17}


def test_historical_receiver_variation_is_not_smaller_than_cross_plate():
    result = multi_cell_confound_audit()

    assert len(result["channel_labels"]) == 4
    assert result["all_sweep_points"]["cross_mean_over_within_mean"] < 1.0
    assert result["detected_modes"]["cross_mean_over_within_mean"] < 1.0