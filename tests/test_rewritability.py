"""
Tests for simulations/rewritability.py — seven rewritability experiments.

Track A — Firmware-Defined Virtual Rewriting
    H7:  Multi-Projection Virtual Rewrite
    H8:  Mode-Subset Logical Devices
    H9:  Readout Mask Library

Track B — Binary Perturbation Sites
    H10: Binary Site Fingerprint Capacity
    H11: Binary-Site Hopfield Capacity

Track C — Multi-Shell Resonator
    H12: Actuator Q Penalty
    H13: Writable Shell Q Budget
"""

import numpy as np
import pytest

from simulations.rewritability import (
    MultiProjectionResult,
    ModeSubsetResult,
    ReadoutMaskResult,
    BinaryFingerprintResult,
    BinaryHopfieldResult,
    ActuatorQResult,
    WritableShellResult,
    exp_multi_projection,
    exp_mode_subset_devices,
    exp_readout_mask_library,
    exp_binary_fingerprints,
    exp_binary_hopfield_capacity,
    exp_actuator_q_penalty,
    exp_writable_shell_q,
    run_all_rewritability,
    _build_coupling_matrix,
)


# ═══════════════════════════════════════════════════════════════════════
# H7: Multi-Projection Virtual Rewrite
# ═══════════════════════════════════════════════════════════════════════

class TestMultiProjection:
    """Tests for exp_multi_projection (H7)."""

    def test_runs_without_error(self):
        r = exp_multi_projection()
        assert isinstance(r, MultiProjectionResult)

    def test_returns_correct_partitions(self):
        r = exp_multi_projection(n_partitions=4)
        assert r.n_partitions == 4
        assert len(r.dims_per_partition) == 4
        assert sum(r.dims_per_partition) == r.n_perturbation_sites

    def test_fidelity_bounded(self):
        r = exp_multi_projection()
        assert np.all(r.fidelity_per_partition >= 0.0)
        assert np.all(r.fidelity_per_partition <= 1.0)

    def test_crosstalk_matrix_shape(self):
        r = exp_multi_projection(n_partitions=3)
        assert r.crosstalk_matrix.shape == (3, 3)
        # Diagonal should be 1.0 (self-correlation)
        for i in range(3):
            assert r.crosstalk_matrix[i, i] == pytest.approx(1.0)

    def test_crosstalk_low_for_orthogonal(self):
        """Orthogonal SVD partitions should have near-zero cross-talk."""
        r = exp_multi_projection(n_modes=10, n_perturbations=24, noise_level=0.0)
        assert r.max_crosstalk < 0.1

    def test_effective_devices_at_least_two(self):
        """With 24 perturbation sites and 4 partitions, expect ≥2 devices."""
        r = exp_multi_projection(n_perturbations=24, n_partitions=4)
        assert r.effective_devices >= 2

    def test_deterministic_with_seed(self):
        r1 = exp_multi_projection(rng=np.random.RandomState(123))
        r2 = exp_multi_projection(rng=np.random.RandomState(123))
        assert r1.mean_fidelity == pytest.approx(r2.mean_fidelity)

    def test_more_partitions_smaller_dims(self):
        r2 = exp_multi_projection(n_partitions=2)
        r8 = exp_multi_projection(n_partitions=8)
        assert max(r2.dims_per_partition) > max(r8.dims_per_partition)

    def test_verdict_logic(self):
        r = exp_multi_projection()
        expected = r.effective_devices >= 2 and r.max_crosstalk < 0.05
        assert r.verdict == expected


# ═══════════════════════════════════════════════════════════════════════
# H8: Mode-Subset Logical Devices
# ═══════════════════════════════════════════════════════════════════════

class TestModeSubsets:
    """Tests for exp_mode_subset_devices (H8)."""

    def test_runs_without_error(self):
        r = exp_mode_subset_devices()
        assert isinstance(r, ModeSubsetResult)

    def test_subset_geometry(self):
        r = exp_mode_subset_devices(total_modes=60, n_subsets=4)
        assert r.total_modes == 60
        assert r.n_subsets == 4
        assert r.modes_per_subset == 15

    def test_recall_bounded(self):
        r = exp_mode_subset_devices()
        assert np.all(r.recall_per_subset >= 0.0)
        assert np.all(r.recall_per_subset <= 1.0)

    def test_crosstalk_shape(self):
        r = exp_mode_subset_devices(n_subsets=3)
        assert r.crosstalk_between_subsets.shape == (3, 3)

    def test_diagonal_crosstalk_is_one(self):
        r = exp_mode_subset_devices(n_subsets=3)
        for i in range(3):
            assert r.crosstalk_between_subsets[i, i] == pytest.approx(1.0)

    def test_independent_devices_positive(self):
        r = exp_mode_subset_devices(total_modes=80, n_subsets=4, P=3)
        assert r.independent_devices >= 0

    def test_deterministic_with_seed(self):
        r1 = exp_mode_subset_devices(rng=np.random.RandomState(77))
        r2 = exp_mode_subset_devices(rng=np.random.RandomState(77))
        assert r1.mean_recall == pytest.approx(r2.mean_recall)

    def test_worst_recall_leq_mean(self):
        r = exp_mode_subset_devices()
        assert r.worst_recall <= r.mean_recall + 1e-10

    def test_verdict_logic(self):
        r = exp_mode_subset_devices()
        expected = r.independent_devices >= 2
        assert r.verdict == expected


# ═══════════════════════════════════════════════════════════════════════
# H9: Readout Mask Library
# ═══════════════════════════════════════════════════════════════════════

class TestReadoutMasks:
    """Tests for exp_readout_mask_library (H9)."""

    def test_runs_without_error(self):
        r = exp_readout_mask_library()
        assert isinstance(r, ReadoutMaskResult)

    def test_seven_masks(self):
        r = exp_readout_mask_library()
        assert r.n_masks == 7
        assert len(r.mask_descriptions) == 7
        assert len(r.recall_per_mask) == 7

    def test_recall_bounded(self):
        r = exp_readout_mask_library()
        assert np.all(r.recall_per_mask >= 0.0)
        assert np.all(r.recall_per_mask <= 1.0)

    def test_best_mask_valid_index(self):
        r = exp_readout_mask_library()
        assert 0 <= r.best_mask_idx < r.n_masks
        assert r.best_recall == pytest.approx(r.recall_per_mask[r.best_mask_idx])

    def test_full_spectrum_usually_good(self):
        """Full spectrum (no mask) should have decent recall."""
        r = exp_readout_mask_library(N=100, P=4)
        # Full spectrum is mask index 0
        assert r.recall_per_mask[0] > 0.3

    def test_deterministic_with_seed(self):
        r1 = exp_readout_mask_library(rng=np.random.RandomState(99))
        r2 = exp_readout_mask_library(rng=np.random.RandomState(99))
        np.testing.assert_array_equal(r1.recall_per_mask, r2.recall_per_mask)

    def test_discrimination_array(self):
        r = exp_readout_mask_library()
        assert len(r.pattern_discrimination) == r.n_masks

    def test_verdict_logic(self):
        r = exp_readout_mask_library()
        expected = r.masks_above_threshold >= 3
        assert r.verdict == expected


# ═══════════════════════════════════════════════════════════════════════
# H10: Binary Site Fingerprint Capacity
# ═══════════════════════════════════════════════════════════════════════

class TestBinaryFingerprints:
    """Tests for exp_binary_fingerprints (H10)."""

    def test_runs_without_error(self):
        r = exp_binary_fingerprints()
        assert isinstance(r, BinaryFingerprintResult)

    def test_coupling_matrix_shape(self):
        C = _build_coupling_matrix(20, 12)
        assert C.shape == (20, 12)

    def test_coupling_matrix_values(self):
        C = _build_coupling_matrix(5, 3)
        # C[0,0] = sin(pi * 1 / 4) = sin(pi/4) ≈ 0.707
        assert C[0, 0] == pytest.approx(np.sin(np.pi / 4), rel=1e-6)

    def test_full_enumeration_small(self):
        """With 6 sites, enumerate all 2^6=64 configs."""
        r = exp_binary_fingerprints(n_sites=6, n_modes=10, n_configs_to_test=100)
        assert r.n_configurations_tested == 64

    def test_sampling_large(self):
        """With 16 sites, should sample n_configs_to_test."""
        r = exp_binary_fingerprints(n_sites=16, n_modes=10, n_configs_to_test=50)
        assert r.n_configurations_tested == 50

    def test_distinguishable_positive(self):
        r = exp_binary_fingerprints(n_sites=8, n_modes=15)
        assert r.n_distinguishable > 1

    def test_bits_per_rod(self):
        r = exp_binary_fingerprints()
        assert r.bits_per_rod == pytest.approx(np.log2(r.n_distinguishable))

    def test_distance_matrix_symmetric(self):
        r = exp_binary_fingerprints(n_sites=6, n_modes=10, n_configs_to_test=20)
        np.testing.assert_array_almost_equal(
            r.spectral_distance_matrix,
            r.spectral_distance_matrix.T,
        )

    def test_deterministic_with_seed(self):
        r1 = exp_binary_fingerprints(rng=np.random.RandomState(55))
        r2 = exp_binary_fingerprints(rng=np.random.RandomState(55))
        assert r1.n_distinguishable == r2.n_distinguishable

    def test_more_sites_more_fingerprints(self):
        r6 = exp_binary_fingerprints(n_sites=6, n_modes=20)
        r10 = exp_binary_fingerprints(n_sites=10, n_modes=20)
        assert r10.n_distinguishable >= r6.n_distinguishable

    def test_verdict_logic(self):
        r = exp_binary_fingerprints()
        threshold = 2 ** (r.n_sites / 2)
        expected = r.n_distinguishable > threshold
        assert r.verdict == expected


# ═══════════════════════════════════════════════════════════════════════
# H11: Binary-Site Hopfield Capacity
# ═══════════════════════════════════════════════════════════════════════

class TestBinaryHopfield:
    """Tests for exp_binary_hopfield_capacity (H11)."""

    def test_runs_without_error(self):
        r = exp_binary_hopfield_capacity()
        assert isinstance(r, BinaryHopfieldResult)

    def test_site_counts_default(self):
        r = exp_binary_hopfield_capacity()
        expected = np.array([4, 8, 12, 16, 20, 24, 32])
        np.testing.assert_array_equal(r.site_counts, expected)

    def test_capacity_non_negative(self):
        r = exp_binary_hopfield_capacity()
        assert np.all(r.capacity_per_site_count >= 0)

    def test_recall_bounded(self):
        r = exp_binary_hopfield_capacity()
        assert np.all(r.recall_accuracy >= 0.0)
        assert np.all(r.recall_accuracy <= 1.0)

    def test_capacity_monotone_increasing(self):
        """More sites should give at least as much capacity."""
        r = exp_binary_hopfield_capacity()
        for i in range(1, len(r.capacity_per_site_count)):
            assert r.capacity_per_site_count[i] >= r.capacity_per_site_count[i - 1] - 1

    def test_min_sites_in_range(self):
        r = exp_binary_hopfield_capacity()
        assert r.min_sites_for_recall >= 4
        assert r.min_sites_for_recall <= 32

    def test_custom_site_counts(self):
        sites = np.array([8, 16, 32])
        r = exp_binary_hopfield_capacity(site_counts=sites)
        assert len(r.capacity_per_site_count) == 3

    def test_deterministic_with_seed(self):
        r1 = exp_binary_hopfield_capacity(rng=np.random.RandomState(42))
        r2 = exp_binary_hopfield_capacity(rng=np.random.RandomState(42))
        np.testing.assert_array_equal(r1.capacity_per_site_count, r2.capacity_per_site_count)

    def test_verdict_logic(self):
        r = exp_binary_hopfield_capacity()
        expected = r.min_sites_for_recall <= 32
        assert r.verdict == expected


# ═══════════════════════════════════════════════════════════════════════
# H12: Actuator Q Penalty
# ═══════════════════════════════════════════════════════════════════════

class TestActuatorQ:
    """Tests for exp_actuator_q_penalty (H12)."""

    def test_runs_without_error(self):
        r = exp_actuator_q_penalty()
        assert isinstance(r, ActuatorQResult)

    def test_baseline_Q_reasonable(self):
        """Glass rod baseline Q should be in expected range."""
        r = exp_actuator_q_penalty()
        assert 1000 < r.Q_no_actuator < 50000

    def test_Q_drops_with_actuators(self):
        r = exp_actuator_q_penalty()
        assert r.Q_with_actuator <= r.Q_no_actuator

    def test_penalty_positive(self):
        r = exp_actuator_q_penalty()
        assert r.Q_penalty_pct >= 0

    def test_actuator_loss_fraction_bounded(self):
        r = exp_actuator_q_penalty()
        assert 0 <= r.actuator_loss_fraction <= 100

    def test_max_actuators_non_negative(self):
        r = exp_actuator_q_penalty()
        assert r.max_actuators_for_Q5000 >= 0

    def test_area_fraction_bounded(self):
        r = exp_actuator_q_penalty()
        assert 0 <= r.actuator_area_fraction <= 1.0

    def test_larger_actuator_more_penalty(self):
        """Bigger actuator footprint → more Q penalty."""
        r1 = exp_actuator_q_penalty(actuator_footprint_um2=50.0)
        r2 = exp_actuator_q_penalty(actuator_footprint_um2=500.0)
        assert r2.Q_with_actuator <= r1.Q_with_actuator

    def test_verdict_logic(self):
        r = exp_actuator_q_penalty()
        expected = r.Q_with_actuator >= 5000
        assert r.verdict == expected


# ═══════════════════════════════════════════════════════════════════════
# H13: Writable Shell Q Budget
# ═══════════════════════════════════════════════════════════════════════

class TestWritableShell:
    """Tests for exp_writable_shell_q (H13)."""

    def test_runs_without_error(self):
        r = exp_writable_shell_q()
        assert isinstance(r, WritableShellResult)

    def test_Q_grid_shape(self):
        r = exp_writable_shell_q()
        expected_shape = (len(r.shell_thicknesses_nm), len(r.shell_Q_values))
        assert r.total_Q_grid.shape == expected_shape

    def test_Q_decreases_with_thickness(self):
        """Thicker shell → lower total Q (at fixed Q_d)."""
        r = exp_writable_shell_q()
        for qi in range(len(r.shell_Q_values)):
            col = r.total_Q_grid[:, qi]
            for i in range(1, len(col)):
                assert col[i] <= col[i - 1] + 1e-6

    def test_Q_increases_with_shell_Q(self):
        """Higher shell Q_d → higher total Q (at fixed thickness)."""
        r = exp_writable_shell_q()
        for ti in range(len(r.shell_thicknesses_nm)):
            row = r.total_Q_grid[ti, :]
            for i in range(1, len(row)):
                assert row[i] >= row[i - 1] - 1e-6

    def test_thin_shell_high_Q(self):
        """1 nm shell with Q_d=5000 should barely affect total Q."""
        r = exp_writable_shell_q(
            shell_thicknesses_nm=np.array([1.0]),
            shell_Q_values=np.array([5000.0]),
        )
        assert r.total_Q_grid[0, 0] > 5000

    def test_max_shell_thickness_non_negative(self):
        r = exp_writable_shell_q()
        assert r.max_shell_thickness_nm >= 0

    def test_frequency_shift_non_negative(self):
        r = exp_writable_shell_q()
        assert r.frequency_shift_pct >= 0

    def test_boundary_points_at_Q5000(self):
        """Each boundary point should be near Q=5000."""
        r = exp_writable_shell_q()
        for t_nm, Q_d in r.Q_5000_boundary:
            # Find indices
            ti = int(np.argmin(np.abs(r.shell_thicknesses_nm - t_nm)))
            qi = int(np.argmin(np.abs(r.shell_Q_values - Q_d)))
            assert r.total_Q_grid[ti, qi] >= 5000

    def test_custom_parameters(self):
        r = exp_writable_shell_q(
            shell_thicknesses_nm=np.array([5, 10, 50]),
            shell_Q_values=np.array([100, 500]),
        )
        assert r.total_Q_grid.shape == (3, 2)

    def test_verdict_logic(self):
        r = exp_writable_shell_q()
        expected = r.max_shell_thickness_nm > 0 and r.frequency_shift_pct > 0.001
        assert r.verdict == expected


# ═══════════════════════════════════════════════════════════════════════
# Integration: run_all_rewritability
# ═══════════════════════════════════════════════════════════════════════

class TestRunAllRewritability:
    """Tests for run_all_rewritability()."""

    def test_returns_dict_with_all_keys(self):
        results = run_all_rewritability(verbose=False)
        expected_keys = {
            "multi_projection", "mode_subsets", "readout_masks",
            "binary_fingerprints", "binary_hopfield",
            "actuator_q", "writable_shell",
        }
        assert set(results.keys()) == expected_keys

    def test_all_results_have_verdict(self):
        results = run_all_rewritability(verbose=False)
        for key, result in results.items():
            assert hasattr(result, "verdict"), f"{key} missing verdict"

    def test_verbose_output(self, capsys):
        run_all_rewritability(verbose=True)
        captured = capsys.readouterr()
        assert "REWRITABILITY EXPERIMENTS" in captured.out
        assert "Track A" in captured.out
        assert "Track B" in captured.out
        assert "Track C" in captured.out
        assert "TOTAL:" in captured.out
