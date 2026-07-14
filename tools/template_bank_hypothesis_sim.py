#!/usr/bin/env python3
"""Data-calibrated hypothesis simulations for the written template bank.

The suite uses the June 5 E3 raw sweeps and comparison table. It does not
replace rewrite-cycle measurements. Its job is to identify which hypothesis is
worth carrying back to the repaired bench and which parameters are decisive.
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial.distance import pdist

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulations.chladni_plates import (
    build_plate_sensitivity_matrix,
    plate_eigenfrequency,
)


E3_ROOT = ROOT / "data" / "results" / "lab" / "25mm_plate" / "e3"
DEFAULT_OUTPUT = ROOT / "data" / "results" / "template_bank_simulation"
PATTERNS = ("A", "B", "C")
SITE_MM = np.array([[8.3, 8.3], [12.5, 12.5], [5.0, 12.5]], dtype=float)
PLATE_SIZE_MM = 25.0


def _load_condition(label: str) -> dict[str, Any]:
    matches = sorted(E3_ROOT.glob(f"e3_{label}_*.json"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one E3 {label} file, found {len(matches)}")
    return json.loads(matches[0].read_text())


def load_e3() -> dict[str, Any]:
    conditions = {
        label: _load_condition(label)
        for label in ("bare", *PATTERNS, "bare2")
    }
    comparison = json.loads((E3_ROOT / "e3_comparison_analysis.json").read_text())
    records = {
        label: {
            (int(row["target_hz"]), row["channel"]): row
            for row in payload["results"]
        }
        for label, payload in conditions.items()
    }
    stable_rows = [
        comparison["modes"][index]
        for index in comparison["stable_mode_indices"]
    ]
    stable_keys = [
        (int(row["target_hz"]), row["channel"])
        for row in stable_rows
    ]

    def timestamp_seconds(label: str) -> float:
        start = dt.datetime.strptime(conditions["bare"]["timestamp"], "%Y%m%d_%H%M%S")
        current = dt.datetime.strptime(conditions[label]["timestamp"], "%Y%m%d_%H%M%S")
        return (current - start).total_seconds()

    times = {label: timestamp_seconds(label) for label in conditions}
    return {
        "conditions": conditions,
        "comparison": comparison,
        "records": records,
        "stable_rows": stable_rows,
        "stable_keys": stable_keys,
        "times_s": times,
    }


def drift_corrected_e3(dataset: dict[str, Any]) -> dict[str, Any]:
    records = dataset["records"]
    times = dataset["times_s"]
    duration = times["bare2"]
    raw = np.zeros((len(PATTERNS), len(dataset["stable_keys"])))
    corrected = np.zeros_like(raw)
    drift = np.zeros(len(dataset["stable_keys"]))
    linewidth = np.zeros(len(dataset["stable_keys"]))

    channels = []
    for mode_index, key in enumerate(dataset["stable_keys"]):
        bare_start = float(records["bare"][key]["f0_hz"])
        bare_end = float(records["bare2"][key]["f0_hz"])
        drift[mode_index] = bare_end - bare_start
        row = dataset["stable_rows"][mode_index]
        linewidth[mode_index] = float(row["bw_bare"])
        channels.append(
            {
                "target_hz": key[0],
                "channel": key[1],
                "f0_bare_hz": bare_start,
                "linewidth_hz": linewidth[mode_index],
                "endpoint_drift_hz": drift[mode_index],
            }
        )
        for pattern_index, pattern in enumerate(PATTERNS):
            observed = float(records[pattern][key]["f0_hz"])
            raw[pattern_index, mode_index] = observed - bare_start
            fraction = times[pattern] / duration
            interpolated_bare = bare_start + fraction * drift[mode_index]
            corrected[pattern_index, mode_index] = observed - interpolated_bare

    tolerance_summary = {}
    for tolerance_hz in (0.0, 50.0, 100.0, 150.0):
        violations = corrected > tolerance_hz
        tolerance_summary[str(int(tolerance_hz))] = {
            "positive_violations": int(np.sum(violations)),
            "fraction_nonpositive_with_tolerance": float(np.mean(~violations)),
        }

    # One endpoint difference is not a variance estimate. This is an explicit
    # conservative scale used only for the feasibility envelope.
    first_record = records["bare"][dataset["stable_keys"][0]]
    sweep_step_hz = float(
        np.median(np.diff(np.asarray(first_record["sweep"]["freqs"], dtype=float)))
    )
    quantization_sigma = sweep_step_hz / math.sqrt(12.0)
    inferred_noise_sigma = np.maximum(np.abs(drift) / math.sqrt(2.0), quantization_sigma)

    return {
        "channels": channels,
        "patterns": list(PATTERNS),
        "sites_mm": SITE_MM.tolist(),
        "raw_shifts_hz": raw.tolist(),
        "linear_drift_corrected_shifts_hz": corrected.tolist(),
        "endpoint_drift_hz": drift.tolist(),
        "inferred_noise_sigma_hz": inferred_noise_sigma.tolist(),
        "sweep_step_hz": sweep_step_hz,
        "tolerance_summary": tolerance_summary,
        "warning": (
            "Linear interpolation between two bare captures is a sensitivity analysis, "
            "not a validated drift model. Inferred noise sigma is an explicit conservative "
            "proxy because E3 contains no independent rewrite or bare-repeat distribution."
        ),
    }


def _fit_nonnegative_scale(sensitivity: np.ndarray, shift_hz: np.ndarray) -> dict[str, float]:
    denominator = float(np.dot(sensitivity, sensitivity))
    scale = max(0.0, -float(np.dot(sensitivity, shift_hz)) / max(denominator, 1e-15))
    prediction = -scale * sensitivity
    residual = shift_hz - prediction
    signal_norm = float(np.linalg.norm(shift_hz))
    relative_rmse = float(np.linalg.norm(residual) / max(signal_norm, 1e-12))
    r2_zero = 1.0 - float(np.dot(residual, residual)) / max(float(np.dot(shift_hz, shift_hz)), 1e-12)
    return {
        "scale_hz": scale,
        "relative_rmse": relative_rmse,
        "r2_about_zero": r2_zero,
    }


def rayleigh_model_audit(dataset: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    corrected = np.asarray(audit["linear_drift_corrected_shifts_hz"], dtype=float)
    sites = SITE_MM / PLATE_SIZE_MM
    candidates = [(n, m) for n in range(1, 7) for m in range(1, 7)]
    fitted_channels = []

    young = 72e9
    poisson = 0.17
    thickness_m = 1e-3
    density = 2200.0
    side_m = 25e-3
    rigidity = young * thickness_m**3 / (12.0 * (1.0 - poisson**2))
    rho_h = density * thickness_m
    theory_frequency = {
        mode: plate_eigenfrequency(
            mode[0], mode[1], side_m, side_m, rigidity, rho_h
        )
        for mode in candidates
    }

    for channel_index, channel in enumerate(audit["channels"]):
        measured = corrected[:, channel_index]
        fits = []
        for mode in candidates:
            sensitivity = build_plate_sensitivity_matrix([mode], sites)[0]
            fit = _fit_nonnegative_scale(sensitivity, measured)
            frequency = theory_frequency[mode]
            fits.append(
                {
                    "mode": list(mode),
                    "theory_frequency_hz": frequency,
                    "frequency_relative_error": (
                        frequency - channel["target_hz"]
                    ) / channel["target_hz"],
                    "sensitivity_at_ABC": sensitivity.tolist(),
                    **fit,
                }
            )
        fits.sort(key=lambda row: row["relative_rmse"])
        plausible = [
            row for row in fits if abs(row["frequency_relative_error"]) <= 0.30
        ]
        if not plausible:
            raise ValueError("No frequency-plausible mode candidates")
        plausible.sort(key=lambda row: row["relative_rmse"])
        best_error = plausible[0]["relative_rmse"]
        ambiguity_count = sum(
            row["relative_rmse"] <= best_error * 1.10 + 1e-12
            for row in plausible
        )
        fitted_channels.append(
            {
                **channel,
                "measured_corrected_shifts_hz": measured.tolist(),
                "best_unconstrained_fit": fits[0],
                "best_frequency_constrained_fit": plausible[0],
                "top_five_frequency_constrained": plausible[:5],
                "frequency_constrained_candidates_within_10pct_error": ambiguity_count,
            }
        )

    # Independent frequency plausibility check for the simply-supported model.
    theory_modes = [(frequency, mode) for mode, frequency in theory_frequency.items()]

    frequency_matches = []
    for target in sorted({channel["target_hz"] for channel in audit["channels"]}):
        nearest = sorted(
            theory_modes, key=lambda row: abs(row[0] - target)
        )[:5]
        frequency_matches.append(
            {
                "measured_target_hz": target,
                "nearest_simply_supported_modes": [
                    {
                        "mode": list(mode),
                        "frequency_hz": frequency,
                        "relative_error": (frequency - target) / target,
                    }
                    for frequency, mode in nearest
                ],
            }
        )

    best_r2 = [
        row["best_frequency_constrained_fit"]["r2_about_zero"]
        for row in fitted_channels
    ]
    return {
        "model": "simply-supported 2D Rayleigh sensitivity sin^2(n*pi*x)*sin^2(m*pi*y)",
        "fitted_channels": fitted_channels,
        "frequency_matches": frequency_matches,
        "channels_with_frequency_constrained_r2_ge_0_5": int(
            np.sum(np.asarray(best_r2) >= 0.5)
        ),
        "median_frequency_constrained_r2": float(np.median(best_r2)),
        "interpretation": (
            "With only three mass sites, mode assignments are underdetermined. Poor or "
            "ambiguous fits mean site optimization must be treated as an ensemble projection, "
            "not as a calibrated plate map."
        ),
    }


def _power_curve(record: dict[str, Any], smooth_bins: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    frequencies = np.asarray(record["sweep"]["freqs"], dtype=float)
    power = np.asarray(record["sweep"]["mags"], dtype=float) ** 2
    if smooth_bins > 0:
        power = gaussian_filter1d(power, smooth_bins, mode="nearest")
    return frequencies, power


def _power_at(
    record: dict[str, Any],
    frequencies_hz: np.ndarray,
    curve_shift_hz: np.ndarray | float = 0.0,
    smooth_bins: float = 1.0,
) -> np.ndarray:
    frequencies, power = _power_curve(record, smooth_bins=smooth_bins)
    edge_count = max(3, min(10, power.size // 10))
    noise_power = float(
        np.median(np.concatenate([power[:edge_count], power[-edge_count:]]))
    )
    return np.interp(
        np.asarray(frequencies_hz) - np.asarray(curve_shift_hz),
        frequencies,
        power,
        left=noise_power,
        right=noise_power,
    )


def _query_matrix(
    records: dict[str, dict[tuple[int, str], dict[str, Any]]],
    channel: str,
    targets: list[int],
    query_frequencies: np.ndarray,
    offsets_hz: np.ndarray,
    smooth_bins: float = 1.0,
) -> np.ndarray:
    matrix = np.zeros((len(PATTERNS), len(PATTERNS)))
    for cell_index, cell in enumerate(PATTERNS):
        for query_index in range(len(PATTERNS)):
            total = 0.0
            for band_index, target in enumerate(targets):
                frequencies = query_frequencies[query_index, band_index] + offsets_hz
                total += float(
                    np.mean(
                        _power_at(
                            records[cell][(target, channel)],
                            frequencies,
                            smooth_bins=smooth_bins,
                        )
                    )
                )
            matrix[cell_index, query_index] = total
    return matrix


def _matrix_metrics(matrix: np.ndarray) -> dict[str, Any]:
    count = matrix.shape[0]
    row_winners = np.argmax(matrix, axis=1)
    column_winners = np.argmax(matrix, axis=0)
    row_margins = []
    column_margins = []
    for index in range(count):
        row_other = np.delete(matrix[index], index)
        col_other = np.delete(matrix[:, index], index)
        row_margins.append(float(matrix[index, index] - np.max(row_other)))
        column_margins.append(float(matrix[index, index] - np.max(col_other)))
    return {
        "row_top1_accuracy": float(np.mean(row_winners == np.arange(count))),
        "column_top1_accuracy": float(np.mean(column_winners == np.arange(count))),
        "row_winners": row_winners.tolist(),
        "column_winners": column_winners.tolist(),
        "minimum_row_margin": min(row_margins),
        "minimum_column_margin": min(column_margins),
        "diagonal_to_offdiagonal_mean_ratio": float(
            np.mean(np.diag(matrix))
            / max(np.mean(matrix[~np.eye(count, dtype=bool)]), 1e-12)
        ),
    }


def _optimize_query_frequencies(
    records: dict[str, dict[tuple[int, str], dict[str, Any]]],
    channel: str,
    targets: list[int],
    design_jitter_hz: float = 50.0,
    radius_hz: float = 1000.0,
) -> np.ndarray:
    output = np.zeros((len(PATTERNS), len(targets)))
    for query_index, query_pattern in enumerate(PATTERNS):
        band_differences = []
        band_frequencies = []
        competitors = [index for index in range(len(PATTERNS)) if index != query_index]
        for target in targets:
            reference = records[query_pattern][(target, channel)]
            frequency_grid = np.asarray(reference["sweep"]["freqs"], dtype=float)
            center = float(reference["f0_hz"])
            keep = np.abs(frequency_grid - center) <= radius_hz
            candidate_frequencies = frequency_grid[keep]
            if candidate_frequencies.size < 3:
                raise ValueError("Insufficient candidate frequencies for robust query optimization")

            step = float(np.median(np.diff(frequency_grid)))
            smoothing = math.sqrt(1.0 + (design_jitter_hz / max(step, 1e-12)) ** 2)
            expected = []
            for pattern in PATTERNS:
                expected.append(
                    _power_at(
                        records[pattern][(target, channel)],
                        candidate_frequencies,
                        smooth_bins=smoothing,
                    )
                )
            expected = np.asarray(expected)
            differences = np.vstack(
                [expected[query_index] - expected[competitor] for competitor in competitors]
            )
            band_frequencies.append(candidate_frequencies)
            band_differences.append(differences)

        if len(targets) != 3:
            raise ValueError("Robust optimizer currently expects three independent target bands")
        best_objective = -np.inf
        best_indices = (0, 0, 0)
        first, second, third = band_differences
        for index_a in range(first.shape[1]):
            for index_b in range(second.shape[1]):
                partial = first[:, index_a] + second[:, index_b]
                objective = np.min(partial[:, None] + third, axis=0)
                index_c = int(np.argmax(objective))
                if objective[index_c] > best_objective:
                    best_objective = float(objective[index_c])
                    best_indices = (index_a, index_b, index_c)
        output[query_index] = [
            band_frequencies[band][best_indices[band]]
            for band in range(3)
        ]
    return output


def _lognormal_gain(rng: np.random.Generator, cv: float, shape: tuple[int, ...]) -> np.ndarray:
    if cv <= 0:
        return np.ones(shape)
    variance = math.log1p(cv**2)
    return np.exp(rng.normal(-0.5 * variance, math.sqrt(variance), size=shape))


def monte_carlo_match(
    records: dict[str, dict[tuple[int, str], dict[str, Any]]],
    channel: str,
    targets: list[int],
    query_frequencies: np.ndarray,
    offsets_hz: np.ndarray,
    common_rewrite_sigma_hz: float,
    power_gain_cv: float,
    trials: int,
    seed: int,
    smooth_bins: float,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    common_shift = rng.normal(
        0.0, common_rewrite_sigma_hz, size=(trials, len(PATTERNS))
    )
    independent_shift = rng.normal(
        0.0,
        common_rewrite_sigma_hz / 2.0,
        size=(trials, len(PATTERNS), len(targets)),
    )
    gains = _lognormal_gain(rng, power_gain_cv, (trials, len(PATTERNS)))
    matrix = np.zeros((trials, len(PATTERNS), len(PATTERNS)))

    for cell_index, cell in enumerate(PATTERNS):
        for query_index in range(len(PATTERNS)):
            for band_index, target in enumerate(targets):
                for offset in offsets_hz:
                    frequency = query_frequencies[query_index, band_index] + offset
                    shifts = common_shift[:, cell_index] + independent_shift[:, cell_index, band_index]
                    matrix[:, cell_index, query_index] += _power_at(
                        records[cell][(target, channel)],
                        np.full(trials, frequency),
                        curve_shift_hz=shifts,
                        smooth_bins=smooth_bins,
                    ) / len(offsets_hz)
        matrix[:, cell_index, :] *= gains[:, cell_index, None]

    # A small capture-noise term prevents exact ties while remaining much smaller
    # than the observed between-frequency structure.
    # Independent 2% power-domain capture noise.
    matrix *= _lognormal_gain(rng, 0.02, matrix.shape)
    expected = np.arange(len(PATTERNS))
    bank_winners = np.argmax(matrix, axis=1)
    calibrated = matrix / (np.mean(matrix, axis=2, keepdims=True) + 1e-12)
    calibrated_winners = np.argmax(calibrated, axis=1)
    sequential_winners = np.argmax(matrix, axis=2)
    return {
        "raw_bank_accuracy": float(np.mean(bank_winners == expected[None, :])),
        "gain_calibrated_bank_accuracy": float(
            np.mean(calibrated_winners == expected[None, :])
        ),
        "sequential_cell_accuracy": float(
            np.mean(sequential_winners == expected[None, :])
        ),
    }


def direct_match_simulation(dataset: dict[str, Any]) -> dict[str, Any]:
    records = dataset["records"]
    channel = "25mm NW"
    targets = [56000, 86000, 91000]
    peak_queries = np.asarray(
        [
            [records[pattern][(target, channel)]["f0_hz"] for target in targets]
            for pattern in PATTERNS
        ],
        dtype=float,
    )
    optimized_queries = _optimize_query_frequencies(
        records, channel, targets, design_jitter_hz=50.0
    )
    designs = {
        "exact_peak": (peak_queries, np.array([0.0]), 0.0),
        "peak_comb_25hz": (peak_queries, np.array([-25.0, 0.0, 25.0]), 0.0),
        # The optimizer evaluates expected response under a 50 Hz design-jitter
        # blur. Its MC uses the same smoothing width.
        "robust_optimized_50hz": (
            optimized_queries,
            np.array([0.0]),
            math.sqrt(1.0 + (50.0 / 50.0) ** 2),
        ),
    }

    observed = {}
    for name, (query_frequencies, offsets, simulation_smoothing) in designs.items():
        measured_matrix = _query_matrix(
            records,
            channel,
            targets,
            query_frequencies,
            offsets,
            smooth_bins=0.0,
        )
        smoothed_matrix = _query_matrix(
            records,
            channel,
            targets,
            query_frequencies,
            offsets,
            smooth_bins=1.0,
        )
        observed[name] = {
            "query_frequencies_hz": query_frequencies.tolist(),
            "offsets_hz": offsets.tolist(),
            "simulation_smoothing_bins": simulation_smoothing,
            "measured_matrix_power": measured_matrix.tolist(),
            "measured_metrics": _matrix_metrics(measured_matrix),
            "smoothed_matrix_power": smoothed_matrix.tolist(),
            "smoothed_metrics": _matrix_metrics(smoothed_matrix),
        }

    bare_matrix = np.zeros((1, len(PATTERNS)))
    for query_index, pattern in enumerate(PATTERNS):
        for band_index, target in enumerate(targets):
            bare_matrix[0, query_index] += float(
                _power_at(
                    records["bare"][(target, channel)],
                    np.array([peak_queries[query_index, band_index]]),
                )[0]
            )
    exact_matrix = np.asarray(observed["exact_peak"]["measured_matrix_power"])
    bare_contrast = exact_matrix - bare_matrix

    robustness = []
    for design_index, (
        name,
        (query_frequencies, offsets, simulation_smoothing),
    ) in enumerate(designs.items()):
        for rewrite_sigma_hz in (0.0, 10.0, 25.0, 50.0, 75.0, 100.0, 150.0, 200.0):
            for gain_cv in (0.0, 0.25):
                metrics = monte_carlo_match(
                    records,
                    channel,
                    targets,
                    query_frequencies,
                    offsets,
                    rewrite_sigma_hz,
                    gain_cv,
                    trials=2000,
                    seed=4100 + design_index * 1000 + int(rewrite_sigma_hz) * 3 + int(gain_cv * 100),
                    smooth_bins=simulation_smoothing,
                )
                robustness.append(
                    {
                        "design": name,
                        "common_rewrite_sigma_hz": rewrite_sigma_hz,
                        "total_per_band_rewrite_sigma_hz": rewrite_sigma_hz
                        * math.sqrt(1.25),
                        "power_gain_cv": gain_cv,
                        "simulation_smoothing_bins": simulation_smoothing,
                        **metrics,
                    }
                )

    thresholds = {}
    for name in designs:
        selected = [
            row
            for row in robustness
            if row["design"] == name and row["power_gain_cv"] == 0.25
        ]
        passing = [
            row["total_per_band_rewrite_sigma_hz"]
            for row in selected
            if row["gain_calibrated_bank_accuracy"] >= 0.80
        ]
        thresholds[name] = max(passing) if passing else None

    return {
        "source_channel": channel,
        "target_bands_hz": targets,
        "observed_replay": observed,
        "exact_peak_bare_power": bare_matrix[0].tolist(),
        "exact_peak_bare_referenced_contrast": bare_contrast.tolist(),
        "robustness_grid": robustness,
        "max_total_per_band_rewrite_sigma_hz_at_80pct_calibrated_bank_accuracy_power_gain_cv_0_25": thresholds,
        "warning": (
            "Query frequencies and transfer curves come from the same one-pass E3 session. "
            "Observed diagonal replay is an optimistic mechanism check. Monte Carlo results "
            "depend on explicit jitter, smoothing, and power-gain assumptions and require "
            "independent rewrites."
        ),
    }


def _leave_one_out_accuracy(samples: np.ndarray, labels: np.ndarray) -> float:
    correct = 0
    for index in range(samples.shape[0]):
        keep = np.arange(samples.shape[0]) != index
        unique = np.unique(labels)
        centroids = np.asarray(
            [samples[keep & (labels == label)].mean(axis=0) for label in unique]
        )
        prediction = unique[np.argmin(np.sum((centroids - samples[index]) ** 2, axis=1))]
        correct += prediction == labels[index]
    return correct / samples.shape[0]


def rewrite_feasibility_simulation(audit: dict[str, Any]) -> dict[str, Any]:
    nominal = np.asarray(audit["linear_drift_corrected_shifts_hz"], dtype=float)
    sigma_base = np.asarray(audit["inferred_noise_sigma_hz"], dtype=float)
    rows = []
    rng = np.random.default_rng(5201)
    rewrites_per_pattern = 8
    campaigns = 500

    for mass_mg in (25.0, 50.0, 75.0, 100.0):
        mass_factor = mass_mg / 50.0
        for drift_factor in (0.10, 0.25, 0.5, 0.75, 1.0, 1.5):
            for response_cv in (0.01, 0.025, 0.05, 0.10, 0.20):
                accuracies = []
                ratios = []
                passes = []
                sigma = sigma_base * drift_factor
                for _ in range(campaigns):
                    sample_blocks = []
                    label_blocks = []
                    for pattern_index in range(len(PATTERNS)):
                        placement = rng.normal(
                            1.0,
                            response_cv,
                            size=(rewrites_per_pattern, nominal.shape[1]),
                        )
                        noise = rng.normal(
                            0.0,
                            sigma,
                            size=(rewrites_per_pattern, nominal.shape[1]),
                        )
                        values = mass_factor * nominal[pattern_index] * placement + noise
                        sample_blocks.append(values / sigma[None, :])
                        label_blocks.append(
                            np.full(rewrites_per_pattern, pattern_index, dtype=int)
                        )
                    samples = np.vstack(sample_blocks)
                    labels = np.concatenate(label_blocks)
                    intra = []
                    centroids = []
                    for pattern_index in range(len(PATTERNS)):
                        group = samples[labels == pattern_index]
                        intra.extend(pdist(group).tolist())
                        centroids.append(group.mean(axis=0))
                    intra95 = float(np.quantile(intra, 0.95))
                    inter_min = float(np.min(pdist(np.asarray(centroids))))
                    ratio = inter_min / max(intra95, 1e-12)
                    accuracy = _leave_one_out_accuracy(samples, labels)
                    ratios.append(ratio)
                    accuracies.append(accuracy)
                    passes.append(ratio >= 3.0 and accuracy >= 0.95)
                rows.append(
                    {
                        "mass_mg": mass_mg,
                        "drift_factor_vs_e3_proxy": drift_factor,
                        "rewrite_response_cv": response_cv,
                        "campaigns": campaigns,
                        "rewrites_per_pattern": rewrites_per_pattern,
                        "median_separation_ratio": float(np.median(ratios)),
                        "p10_separation_ratio": float(np.quantile(ratios, 0.10)),
                        "mean_leave_one_out_accuracy": float(np.mean(accuracies)),
                        "gate_pass_probability": float(np.mean(passes)),
                    }
                )

    best_by_drift_placement = []
    for drift_factor in (0.10, 0.25, 0.5, 0.75, 1.0, 1.5):
        for response_cv in (0.01, 0.025, 0.05, 0.10, 0.20):
            selected = [
                row
                for row in rows
                if row["drift_factor_vs_e3_proxy"] == drift_factor
                and row["rewrite_response_cv"] == response_cv
            ]
            passing = [row for row in selected if row["gate_pass_probability"] >= 0.80]
            best_by_drift_placement.append(
                {
                    "drift_factor_vs_e3_proxy": drift_factor,
                    "rewrite_response_cv": response_cv,
                    "minimum_mass_mg_for_80pct_gate_probability": (
                        min(row["mass_mg"] for row in passing) if passing else None
                    ),
                }
            )

    return {
        "noise_proxy_sigma_hz": sigma_base.tolist(),
        "grid": rows,
        "minimum_mass_summary": best_by_drift_placement,
        "warning": (
            "E3 has one capture per written pattern. Rewrite-response CV and noise are "
            "scenario parameters, not fitted distributions. `rewrite_response_cv` is an "
            "independent per-channel response variation, not a physical millimeter placement "
            "error; it ignores spatial correlation between modes. Gate probabilities are "
            "design sensitivities, not forecasts."
        ),
    }


def _equal_mass_binary_codewords(n_sites: int = 4, occupied: int = 2) -> np.ndarray:
    words = []
    for indices in itertools.combinations(range(n_sites), occupied):
        word = np.zeros(n_sites)
        word[list(indices)] = 1.0
        words.append(word)
    return np.asarray(words)


def _layout_score(
    positions: np.ndarray,
    assignments: list[list[tuple[int, int]]],
    mode_weights: np.ndarray,
    noise_sigma: np.ndarray,
) -> float:
    codewords = _equal_mass_binary_codewords(4, 2)
    worst = np.inf
    for modes in assignments:
        sensitivity = build_plate_sensitivity_matrix(modes, positions)
        fingerprints = codewords @ sensitivity.T
        fingerprints = fingerprints * mode_weights[None, :] / noise_sigma[None, :]
        worst = min(worst, float(np.min(pdist(fingerprints))))
    return worst


def site_layout_ensemble_simulation(audit: dict[str, Any], rayleigh: dict[str, Any]) -> dict[str, Any]:
    # Low-order assignments nearest the simply-supported 56/86/91 kHz bands.
    # Swaps represent unresolved members of each square-plate degenerate pair.
    assignments = []
    for swap_56 in (False, True):
        for swap_86 in (False, True):
            pair_56 = [(2, 3), (3, 2)]
            pair_86 = [(2, 4), (4, 2)]
            if swap_56:
                pair_56.reverse()
            if swap_86:
                pair_86.reverse()
            assignments.append([pair_56[0], pair_56[1], pair_86[0], pair_86[1], (3, 3)])

    corrected = np.asarray(audit["linear_drift_corrected_shifts_hz"], dtype=float)
    mode_weights = np.maximum(np.max(np.abs(corrected), axis=0), 50.0)
    noise_sigma = np.asarray(audit["inferred_noise_sigma_hz"], dtype=float)
    rng = np.random.default_rng(6301)
    candidates = []
    attempts = 0
    while len(candidates) < 5000 and attempts < 100000:
        attempts += 1
        positions = rng.uniform(0.08, 0.92, size=(4, 2))
        if np.min(pdist(positions)) < 0.15:
            continue
        score = _layout_score(positions, assignments, mode_weights, noise_sigma)
        candidates.append((score, positions))
    candidates.sort(key=lambda row: row[0], reverse=True)

    evaluated_layouts = []
    placement_sigma = 0.5 / PLATE_SIZE_MM
    for nominal_score, positions in candidates[:100]:
        jitter_scores = []
        for _ in range(100):
            jittered = np.clip(
                positions + rng.normal(0.0, placement_sigma, positions.shape),
                0.03,
                0.97,
            )
            jitter_scores.append(
                _layout_score(jittered, assignments, mode_weights, noise_sigma)
            )
        evaluated_layouts.append(
            {
                "positions_mm": (positions * PLATE_SIZE_MM).tolist(),
                "worst_assignment_nominal_min_distance_sigma": nominal_score,
                "placement_jitter_0_5mm_p10_min_distance_sigma": float(
                    np.quantile(jitter_scores, 0.10)
                ),
                "placement_jitter_0_5mm_median_min_distance_sigma": float(
                    np.median(jitter_scores)
                ),
            }
        )
    evaluated_layouts.sort(
        key=lambda row: row["placement_jitter_0_5mm_p10_min_distance_sigma"],
        reverse=True,
    )
    top_layouts = evaluated_layouts[:10]

    best_positions = np.asarray(top_layouts[0]["positions_mm"]) / PLATE_SIZE_MM
    placement_tolerance = []
    for jitter_mm in (0.10, 0.25, 0.50, 1.00):
        scores = []
        for _ in range(500):
            jittered = np.clip(
                best_positions
                + rng.normal(0.0, jitter_mm / PLATE_SIZE_MM, best_positions.shape),
                0.03,
                0.97,
            )
            scores.append(
                _layout_score(jittered, assignments, mode_weights, noise_sigma)
            )
        placement_tolerance.append(
            {
                "placement_sigma_mm": jitter_mm,
                "p10_min_distance_sigma": float(np.quantile(scores, 0.10)),
                "median_min_distance_sigma": float(np.median(scores)),
                "probability_distance_ge_3sigma": float(np.mean(np.asarray(scores) >= 3.0)),
            }
        )

    regular = np.array(
        [[0.25, 0.25], [0.25, 0.75], [0.75, 0.25], [0.75, 0.75]]
    )
    return {
        "mode_assignment_ensemble": [
            [list(mode) for mode in assignment] for assignment in assignments
        ],
        "patterns": _equal_mass_binary_codewords(4, 2).tolist(),
        "candidate_layouts_evaluated": len(candidates),
        "regular_grid_score_sigma": _layout_score(
            regular, assignments, mode_weights, noise_sigma
        ),
        "top_layouts": top_layouts,
        "best_layout_placement_tolerance": placement_tolerance,
        "model_adequacy_context": {
            "median_frequency_constrained_rayleigh_r2": rayleigh[
                "median_frequency_constrained_r2"
            ],
            "channels_with_frequency_constrained_r2_ge_0_5": rayleigh[
                "channels_with_frequency_constrained_r2_ge_0_5"
            ],
        },
        "warning": (
            "This is an uncertainty-ensemble site proposal, not a calibrated optimum. "
            "Simply-supported mode shapes are weakly constrained by three E3 sites. "
            "TB-11 must measure the proposed sites before any codebook claim."
        ),
    }


def multi_cell_confound_audit() -> dict[str, Any]:
    npz_path = ROOT / "data" / "results" / "h_matrix" / "multi_plate_enrollment_20260603_171950.npz"
    json_path = ROOT / "data" / "results" / "h_matrix" / "multi_plate_enrollment_20260603_171950.json"
    metadata = json.loads(json_path.read_text())
    relay_labels = metadata["config"]["relay_labels"]
    labels = [relay_labels[str(index)] for index in metadata["config"]["relays"]]
    with np.load(npz_path, allow_pickle=False) as payload:
        response = np.asarray(payload["response"], dtype=float)
        h_raw = np.asarray(payload["H_raw"], dtype=float)

    def metrics(values: np.ndarray) -> dict[str, Any]:
        transformed = np.log1p(values)
        correlation = np.corrcoef(transformed.T)
        standardized = (
            transformed - transformed.mean(axis=0, keepdims=True)
        ) / (transformed.std(axis=0, keepdims=True) + 1e-12)
        within_pairs = [(0, 1), (2, 3)]
        cross_pairs = [(left, right) for left in (0, 1) for right in (2, 3)]
        within = [
            float(np.linalg.norm(standardized[:, left] - standardized[:, right]))
            for left, right in within_pairs
        ]
        cross = [
            float(np.linalg.norm(standardized[:, left] - standardized[:, right]))
            for left, right in cross_pairs
        ]
        return {
            "log_response_correlation": correlation.tolist(),
            "within_plate_different_receiver_distances": within,
            "cross_plate_receiver_distances": cross,
            "cross_mean_over_within_mean": float(np.mean(cross) / np.mean(within)),
        }

    return {
        "source_npz": str(npz_path.relative_to(ROOT)),
        "source_json": str(json_path.relative_to(ROOT)),
        "channel_labels": labels,
        "all_sweep_points": metrics(response),
        "detected_modes": metrics(h_raw),
        "interpretation": (
            "In this historical four-channel capture, changing receiver position within a "
            "plate produces at least as much standardized spectral-shape difference as "
            "crossing between the two plates. It cannot estimate intrinsic plate identity "
            "separately from readout topology. Future pattern/cell swaps require identical "
            "PZT topology and each cell's own bare reference."
        ),
    }


def _wilson_interval(successes: float, trials: float, z: float = 1.96) -> tuple[float, float]:
    if trials <= 0:
        return (math.nan, math.nan)
    proportion = successes / trials
    denominator = 1.0 + z**2 / trials
    center = (proportion + z**2 / (2.0 * trials)) / denominator
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / trials + z**2 / (4.0 * trials**2)
    ) / denominator
    return center - radius, center + radius


def sample_size_simulation() -> dict[str, Any]:
    target_rows = []
    control_accuracy = 0.65
    for true_accuracy in (0.80, 0.85, 0.90):
        minimum = None
        for independent_trials in range(8, 501):
            expected_successes = math.floor(true_accuracy * independent_trials)
            lower, upper = _wilson_interval(expected_successes, independent_trials)
            if lower > control_accuracy:
                minimum = independent_trials
                break
        target_rows.append(
            {
                "assumed_true_accuracy": true_accuracy,
                "control_accuracy": control_accuracy,
                "minimum_independent_trials_for_wilson_lower_above_control": minimum,
            }
        )

    clustered = []
    captures_per_rewrite = 8
    for rewrite_count in (8, 12, 16, 24, 32, 48):
        total = rewrite_count * captures_per_rewrite
        for intraclass_correlation in (0.10, 0.25, 0.50, 0.75):
            effective = total / (
                1.0 + (captures_per_rewrite - 1.0) * intraclass_correlation
            )
            clustered.append(
                {
                    "rewrite_blocks": rewrite_count,
                    "captures_per_rewrite": captures_per_rewrite,
                    "intraclass_correlation": intraclass_correlation,
                    "total_captures": total,
                    "approximate_effective_independent_trials": effective,
                }
            )
    required_independent = next(
        row["minimum_independent_trials_for_wilson_lower_above_control"]
        for row in target_rows
        if row["assumed_true_accuracy"] == 0.80
    )
    adaptive_blocks = []
    for intraclass_correlation in (0.10, 0.25, 0.50, 0.75):
        design_effect = 1.0 + (captures_per_rewrite - 1.0) * intraclass_correlation
        required_blocks = math.ceil(
            required_independent * design_effect / captures_per_rewrite
        )
        adaptive_blocks.append(
            {
                "intraclass_correlation": intraclass_correlation,
                "captures_per_rewrite": captures_per_rewrite,
                "required_rewrite_blocks_for_80pct_gate": required_blocks,
            }
        )
    return {
        "wilson_gate_planning": target_rows,
        "clustered_capture_effective_size": clustered,
        "adaptive_rewrite_blocks": adaptive_blocks,
        "warning": (
            "The intraclass correlation is unknown until rewrite cycles are measured. "
            "Captures within one placement cannot be counted as independent rewrites."
        ),
    }


def _pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def render_report(results: dict[str, Any]) -> str:
    audit = results["e3_drift_audit"]
    rayleigh = results["rayleigh_model_audit"]
    direct = results["direct_match_simulation"]
    feasibility = results["rewrite_feasibility"]
    layouts = results["site_layout_ensemble"]
    confound = results["multi_cell_confound"]
    sizing = results["sample_size"]

    exact = direct["observed_replay"]["exact_peak"]
    robust = direct["observed_replay"]["robust_optimized_50hz"]
    thresholds = direct[
        "max_total_per_band_rewrite_sigma_hz_at_80pct_calibrated_bank_accuracy_power_gain_cv_0_25"
    ]

    current_rows = [
        row
        for row in feasibility["grid"]
        if row["mass_mg"] == 50.0
        and row["drift_factor_vs_e3_proxy"] == 1.0
        and row["rewrite_response_cv"] == 0.10
    ]
    improved_rows = [
        row
        for row in feasibility["grid"]
        if row["mass_mg"] == 75.0
        and row["drift_factor_vs_e3_proxy"] == 0.5
        and row["rewrite_response_cv"] == 0.10
    ]

    lines = [
        "# Written Template Bank: Informed Simulation Results",
        "",
        "**Status:** DATA-CALIBRATED SENSITIVITY STUDY. These are not rewrite-cycle measurements or template-bank evidence.",
        "",
        "## Stronger Hypothesis",
        "",
        "> The E3 mass patterns can support a direct multitone energy matcher, but exact-peak queries and rewrite states are stability-limited. A robustness-optimized query may tolerate about 100 Hz frequency jitter, while the strict rewrite gate still requires roughly 2.5% response variability and a 2-4x reduction of the E3 endpoint-drift proxy. Stability control matters more immediately than template count.",
        "",
        "The suite tests six parts of that hypothesis: E3/Rayleigh consistency, direct-energy replay, rewrite feasibility, uncertainty-robust site placement, multi-cell/readout confounding, and independent sample requirements.",
        "",
        "## 1. E3 Drift and Rayleigh Audit",
        "",
        f"After linear interpolation between the two bare captures, {audit['tolerance_summary']['50']['positive_violations']} of 15 stable-channel shifts remain more than +50 Hz, and {audit['tolerance_summary']['150']['positive_violations']} remain more than +150 Hz. Pure point-mass Rayleigh loading predicts non-positive shifts for an isolated correctly tracked mode.",
        "",
        f"After requiring the simply-supported mode frequency to lie within 30% of the measured channel, the best sin-squared fit has median R2 about zero of {rayleigh['median_frequency_constrained_r2']:.3f}; {rayleigh['channels_with_frequency_constrained_r2_ge_0_5']} of 5 channels exceed R2=0.5. Unconstrained fits are much more optimistic because they can select frequency-incompatible modes. With only three sites, several assignments remain ambiguous.",
        "",
        "**Interpretation:** E3 is compatible with low-order 2D Rayleigh sensitivity after a broad frequency constraint, but three sites cannot identify the mode map or test out-of-sample prediction. Mode tracking, fixture disturbance, and drift remain live alternatives. New sites must be treated as model-validation data, not merely more training points.",
        "",
        "## 2. Measured-Curve Direct Match",
        "",
        "The NW channel supplies three prospectively usable bands (56, 86, and 91 kHz). Using each E3 pattern's measured peak frequencies as its three-tone query gives:",
        "",
        "```text",
        np.array2string(np.asarray(exact["measured_matrix_power"]), precision=1),
        "```",
        "",
        f"The unsmoothed measured matrix is diagonal in the one-pass replay: row accuracy {_pct(exact['measured_metrics']['row_top1_accuracy'])}, column accuracy {_pct(exact['measured_metrics']['column_top1_accuracy'])}, and diagonal/off-diagonal mean ratio {exact['measured_metrics']['diagonal_to_offdiagonal_mean_ratio']:.2f}. Smoothed curves are used only for robustness simulation.",
        "",
        "This is optimistic because query frequencies and response curves came from the same capture. Monte Carlo replay with 25% power-gain CV gives these largest **total per-band** rewrite-jitter SD values that retain at least 80% gain-calibrated bank accuracy. The model decomposes each value into a common cell shift plus an independent per-band term at half that common SD:",
        "",
        "| Query design | Maximum total per-band jitter SD at >=80% |",
        "| --- | ---: |",
    ]
    for name, threshold in thresholds.items():
        lines.append(
            f"| {name} | {('none tested' if threshold is None else f'{threshold:.0f} Hz')} |"
        )
    lines.extend(
        [
            "",
            "Exact-peak and +/-25 Hz comb simulations use unsmoothed measured curves. The robustness-optimized design uses the same 1.41-bin Gaussian blur used during its 50 Hz design-jitter optimization. Its apparent advantage is therefore a proposal to validate on frozen independent rewrites, not a fair measured win over the other queries.",
            "",
            "The optimized query frequencies proposed for a 50 Hz design-jitter model are:",
            "",
            "```text",
            np.array2string(np.asarray(robust["query_frequencies_hz"]), precision=0),
            "```",
            "",
            "These frequencies are a preregistration candidate for independent rewrites, not a measured improvement.",
            "",
            "## 3. Rewrite Feasibility Envelope",
            "",
        ]
    )
    if current_rows:
        row = current_rows[0]
        lines.append(
            f"At the scenario labeled current proxy (50 mg, full E3 endpoint-drift proxy, 10% placement CV), median separation ratio is {row['median_separation_ratio']:.2f}, mean leave-one-out accuracy is {_pct(row['mean_leave_one_out_accuracy'])}, and TB-G2 pass probability is {_pct(row['gate_pass_probability'])}."
        )
    if improved_rows:
        row = improved_rows[0]
        lines.append(
            f"At 75 mg with the drift proxy halved and 10% placement CV, median ratio is {row['median_separation_ratio']:.2f}, mean accuracy is {_pct(row['mean_leave_one_out_accuracy'])}, and pass probability is {_pct(row['gate_pass_probability'])}."
        )
    lines.extend(
        [
            "",
            "Because E3 contains no rewrite repeats, these probabilities are sensitivity envelopes. The most useful output is which combination of mass, drift reduction, and placement CV crosses the gate, not the probability itself.",
            "",
            "Scenarios reaching at least 80% simulated TB-G2 pass probability:",
            "",
            "| Drift proxy retained | Response CV | Minimum mass |",
            "| ---: | ---: | ---: |",
        ]
    )
    passing_summary = [
        row
        for row in feasibility["minimum_mass_summary"]
        if row["minimum_mass_mg_for_80pct_gate_probability"] is not None
    ]
    for row in passing_summary:
        lines.append(
            f"| {_pct(row['drift_factor_vs_e3_proxy'])} | {_pct(row['rewrite_response_cv'])} | {row['minimum_mass_mg_for_80pct_gate_probability']:.0f} mg |"
        )
    lines.extend(
        [
            "",
            "No tested scenario with response CV of 5% or greater reaches an 80% gate probability, even at 100 mg. This response-CV parameter is independent per mode and is not a millimeter placement error; the separate site-layout model propagates spatially correlated position jitter. In this envelope, repeatable response is the harder constraint than mass.",
            "",
            "## 4. Site-Layout Ensemble",
            "",
            f"The theoretical search evaluated {layouts['candidate_layouts_evaluated']} four-site layouts against four unresolved low-order mode assignments and six equal-mass two-of-four codewords. The regular corner-grid score is {layouts['regular_grid_score_sigma']:.2f} noise-standardized distance.",
            "",
            "Top proposed layout:",
            "",
            "```text",
            json.dumps(layouts["top_layouts"][0], indent=2),
            "```",
            "",
            "Placement tolerance for that candidate:",
            "",
            "| Placement SD | P10 distance | Probability distance >=3 SD |",
            "| ---: | ---: | ---: |",
        ]
    )
    for row in layouts["best_layout_placement_tolerance"]:
        lines.append(
            f"| {row['placement_sigma_mm']:.2f} mm | {row['p10_min_distance_sigma']:.2f} | {_pct(row['probability_distance_ge_3sigma'])} |"
        )
    lines.extend(
        [
            "",
            "This layout is low-confidence because the simple Rayleigh model is weakly calibrated. Its role is to choose informative TB-11 measurement sites, not to define a final codebook.",
            "",
            "## 5. Multi-Cell and Receiver Confound",
            "",
            f"In the historical Plate I/H enrollment, the mean standardized cross-plate receiver distance divided by the within-plate different-receiver distance is {confound['all_sweep_points']['cross_mean_over_within_mean']:.3f} over all sweep points and {confound['detected_modes']['cross_mean_over_within_mean']:.3f} over detected modes.",
            "",
            "A ratio below one means receiver-position/topology differences were at least as large as cross-plate differences in that capture. The archive therefore cannot supply a clean intrinsic-cell variance model. TB-29/TB-32 must use matched PZT topology and each cell's own bare reference.",
            "",
            "## 6. Independent Rewrite Count",
            "",
            "| Assumed true accuracy | Minimum independent trials whose expected Wilson lower bound exceeds 65% |",
            "| ---: | ---: |",
        ]
    )
    for row in sizing["wilson_gate_planning"]:
        lines.append(
            f"| {_pct(row['assumed_true_accuracy'])} | {row['minimum_independent_trials_for_wilson_lower_above_control']} |"
        )
    lines.extend(
        [
            "",
            "If each rewrite has eight repeated captures, the approximate rewrite blocks needed for an 80% gate are:",
            "",
            "| Rewrite-level intraclass correlation | Required rewrite blocks |",
            "| ---: | ---: |",
        ]
    )
    for row in sizing["adaptive_rewrite_blocks"]:
        lines.append(
            f"| {row['intraclass_correlation']:.2f} | {row['required_rewrite_blocks_for_80pct_gate']} |"
        )
    lines.extend(
        [
            "",
            "Repeated captures within one mass placement are clustered. Estimate rewrite-level intraclass correlation during TB-10 and adapt later sample counts; eight rewrites are enough only if clustering is low.",
            "",
            "## Bench Predictions",
            "",
            "1. **Model audit:** touch-only and bare repeats will explain some apparent positive shifts; new sites will distinguish a real 2D sensitivity map from three-point overfitting.",
            "2. **Direct matching:** exact-peak three-tone queries will be diagonal immediately after calibration but likely fail beyond about 25 Hz rewrite jitter; the optimized query may extend that to about 100 Hz.",
            "3. **Primary bottleneck:** mass does not compensate for response CV above about 5% in the strict rewrite-separation model.",
            "4. **Best intervention:** reduce drift 2-4x and rewrite-response variation to about 2.5% before expanding from three patterns to four/eight templates.",
            "5. **Site design:** use the proposed robust sites as active-learning measurements; 0.5 mm placement error remains close to or below the 3 SD gate in the model.",
            "",
            "## What Would Falsify the Stronger Hypothesis",
            "",
            "- Independent rewrite SD remains above 50 Hz after temperature/fixture controls and no robust query reaches 80%.",
            "- The direct RMS/ringdown matrix loses its diagonal after using frozen frequencies on independently rebuilt patterns.",
            "- Touch-only trials reproduce the written-pattern separation.",
            "- TB-11 measurements disagree with every plausible 2D sensitivity assignment and no empirical site map is repeatable.",
            "- Drift reduction, not mass, fails to improve simulated and measured separation in the predicted direction.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python3 tools/template_bank_hypothesis_sim.py",
            "```",
            "",
            "Machine-readable details are in `data/results/template_bank_simulation/summary.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def run_suite() -> dict[str, Any]:
    dataset = load_e3()
    audit = drift_corrected_e3(dataset)
    rayleigh = rayleigh_model_audit(dataset, audit)
    return {
        "experiment": "template_bank_informed_hypothesis_simulation",
        "status": "DATA_CALIBRATED_SENSITIVITY_STUDY",
        "source_files": [
            str(path.relative_to(ROOT))
            for path in sorted(E3_ROOT.glob("e3_*.json"))
        ],
        "e3_drift_audit": audit,
        "rayleigh_model_audit": rayleigh,
        "direct_match_simulation": direct_match_simulation(dataset),
        "rewrite_feasibility": rewrite_feasibility_simulation(audit),
        "site_layout_ensemble": site_layout_ensemble_simulation(audit, rayleigh),
        "multi_cell_confound": multi_cell_confound_audit(),
        "sample_size": sample_size_simulation(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    results = run_suite()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "summary.json"
    report_path = args.output_dir / "report.md"
    summary_path.write_text(json.dumps(results, indent=2) + "\n")
    report_path.write_text(render_report(results))
    print(f"Wrote {summary_path.relative_to(ROOT)}")
    print(f"Wrote {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()