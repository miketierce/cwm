"""Focused tests for the Wheel-of-Fortune structural surrogate."""

from pathlib import Path

import numpy as np
import pytest

from tools.wheel_of_fortune_surrogate import (
    binary_auc,
    evaluate_completion,
    evaluate_sparse_vocabulary,
    feature_indices,
    load_capture,
)


SOURCE = Path("data/results/pong/recall_enroll_20260629_120542.npz")


@pytest.fixture(scope="module")
def dataset():
    return load_capture(SOURCE)


def test_capture_is_complete_cartesian_grid(dataset):
    assert dataset["features"].shape == (1280, 240)
    assert dataset["unique_states"].shape == (256, 4)
    assert dataset["level_counts"] == [8, 8, 2, 2]
    assert dataset["mode_count"] == 212


def test_all_hidden_glass_is_modes_only(dataset):
    hidden = (0, 1, 2, 3)
    glass = feature_indices(dataset, "glass_readout_masked", hidden)
    modes = feature_indices(dataset, "modes_only", hidden)
    wire = feature_indices(dataset, "wire_visible", hidden)

    np.testing.assert_array_equal(glass, modes)
    assert modes.size == 212
    assert wire.size == 0


def test_binary_auc_orders_known_above_unknown():
    assert binary_auc(np.array([0.8, 0.9]), np.array([0.1, 0.2])) == 1.0
    assert binary_auc(np.array([0.1, 0.2]), np.array([0.8, 0.9])) == 0.0
    assert binary_auc(np.array([0.5]), np.array([0.5])) == 0.5


def test_modes_reconstruct_all_hidden_attributes_above_chance(dataset):
    result = evaluate_completion(
        dataset,
        method="modes_only",
        hidden_attributes=(0, 1, 2, 3),
        noise_sigma=1.0,
        seed=7441,
    )

    assert result["hidden_tuple_accuracy"] == pytest.approx(0.32, abs=0.01)
    assert result["hidden_tuple_accuracy"] > 50 * result["hidden_tuple_chance"]


def test_modes_do_not_support_noisy_sparse_vocabulary_abstention(dataset):
    result = evaluate_sparse_vocabulary(
        dataset,
        method="modes_only",
        noise_sigma=1.0,
        seed=8201,
    )

    assert result["known_vs_unknown_auc"] == pytest.approx(0.509, abs=0.01)
    assert result["unknown_rejection_at_calibrated_95pct"] < 0.10