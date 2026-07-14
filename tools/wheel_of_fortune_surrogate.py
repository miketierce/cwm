#!/usr/bin/env python3
"""Explore CWM as a structural Wheel-of-Fortune surrogate.

The saved Pong captures contain a complete four-attribute physical state grid.
This script measures hidden-attribute reconstruction and sparse-vocabulary
abstention. It does not map Pong attributes to letters and does not claim that
the existing captures are physical missing-symbol queries: every modal response
was acquired while all four state variables were still present in the drive.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "results" / "wheel_of_fortune_surrogate"
ATTRIBUTE_NAMES = ("x", "y", "vx", "vy")
METHODS = (
    "glass_readout_masked",
    "modes_only",
    "visible_axis_windows_only",
    "wire_visible",
)


def _latest_capture() -> Path:
    captures = sorted((ROOT / "data" / "results" / "pong").glob("recall_enroll_*.npz"))
    if not captures:
        raise FileNotFoundError("No data/results/pong/recall_enroll_*.npz capture found")
    return captures[-1]


def load_capture(path: Path) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as payload:
        raw_features = np.asarray(payload["X"], dtype=float)
        states = np.column_stack(
            [np.asarray(payload[key], dtype=int) for key in ("xs", "ys", "vx", "vy")]
        )
        repeats = int(payload["repeats"])
        window_width = int(payload["nw"])
        axis_count = int(payload["naxes"])
        driven = np.asarray(payload["driven"], dtype=int)

    if axis_count != len(ATTRIBUTE_NAMES):
        raise ValueError(f"Expected four state attributes, found {axis_count}")
    if driven.size != axis_count:
        raise ValueError("Driven-feature indices do not match the state attribute count")

    unique_states, state_ids = np.unique(states, axis=0, return_inverse=True)
    counts = np.bincount(state_ids)
    if not np.all(counts == repeats):
        raise ValueError("Every state must have exactly the declared number of repeats")

    level_counts = [int(np.unique(states[:, index]).size) for index in range(axis_count)]
    cartesian_size = math.prod(level_counts)
    if unique_states.shape[0] != cartesian_size:
        raise ValueError("The structural surrogate requires a complete Cartesian state grid")

    # Preserve the normalization used by the July 11 offline reanalysis.
    features = raw_features / (raw_features.mean(axis=1, keepdims=True) + 1e-9)
    repeat_ids = np.arange(features.shape[0]) % repeats
    axis_block = axis_count * window_width

    return {
        "source": path,
        "features": features,
        "states": states,
        "unique_states": unique_states,
        "state_ids": state_ids,
        "repeat_ids": repeat_ids,
        "repeats": repeats,
        "window_width": window_width,
        "axis_count": axis_count,
        "axis_block": axis_block,
        "driven": driven,
        "level_counts": level_counts,
        "mode_count": int(features.shape[1] - axis_block),
    }


def feature_indices(
    dataset: dict[str, Any], method: str, hidden_attributes: tuple[int, ...]
) -> np.ndarray:
    hidden = set(hidden_attributes)
    visible = [index for index in range(dataset["axis_count"]) if index not in hidden]
    window_width = dataset["window_width"]
    axis_block = dataset["axis_block"]
    feature_count = dataset["features"].shape[1]

    visible_windows = [
        np.arange(index * window_width, (index + 1) * window_width)
        for index in visible
    ]
    visible_window_indices = (
        np.concatenate(visible_windows) if visible_windows else np.array([], dtype=int)
    )
    modes = np.arange(axis_block, feature_count)

    if method == "glass_readout_masked":
        return np.concatenate([visible_window_indices, modes])
    if method == "modes_only":
        return modes
    if method == "visible_axis_windows_only":
        return visible_window_indices
    if method == "wire_visible":
        return dataset["driven"][visible]
    raise ValueError(f"Unknown method: {method}")


def _standardize(
    train: np.ndarray, *others: np.ndarray
) -> tuple[np.ndarray, ...]:
    mean = train.mean(axis=0)
    std = train.std(axis=0)
    std[std < 1e-9] = 1.0
    return tuple((array - mean) / std for array in (train, *others))


def _centroids(
    features: np.ndarray, state_ids: np.ndarray, state_count: int
) -> np.ndarray:
    output = np.zeros((state_count, features.shape[1]), dtype=float)
    counts = np.zeros(state_count, dtype=float)
    np.add.at(output, state_ids, features)
    np.add.at(counts, state_ids, 1.0)
    if np.any(counts == 0):
        raise ValueError("A fold is missing one or more state templates")
    return output / counts[:, None]


def _squared_distances(queries: np.ndarray, templates: np.ndarray) -> np.ndarray:
    distances = (
        np.sum(queries * queries, axis=1, keepdims=True)
        + np.sum(templates * templates, axis=1)[None, :]
        - 2.0 * queries @ templates.T
    )
    return np.maximum(distances, 0.0) / max(1, queries.shape[1])


def binary_auc(positive_scores: np.ndarray, negative_scores: np.ndarray) -> float:
    if positive_scores.size == 0 or negative_scores.size == 0:
        return math.nan
    comparisons = positive_scores[:, None] - negative_scores[None, :]
    return float(np.mean(comparisons > 0) + 0.5 * np.mean(comparisons == 0))


def evaluate_completion(
    dataset: dict[str, Any],
    method: str,
    hidden_attributes: tuple[int, ...],
    noise_sigma: float,
    seed: int,
) -> dict[str, Any]:
    indices = feature_indices(dataset, method, hidden_attributes)
    completion_chance = 1.0 / math.prod(
        dataset["level_counts"][index] for index in hidden_attributes
    )
    if indices.size == 0:
        return {
            "status": "NO_VISIBLE_FEATURES",
            "feature_count": 0,
            "hidden_tuple_chance": completion_chance,
        }

    features = dataset["features"][:, indices]
    state_ids = dataset["state_ids"]
    repeat_ids = dataset["repeat_ids"]
    unique_states = dataset["unique_states"]
    rng = np.random.default_rng(seed)

    predicted_ids: list[np.ndarray] = []
    true_ids: list[np.ndarray] = []
    top3_hits: list[np.ndarray] = []
    margins: list[np.ndarray] = []

    for fold in range(dataset["repeats"]):
        train_mask = repeat_ids != fold
        test_mask = repeat_ids == fold
        train, test = _standardize(features[train_mask], features[test_mask])
        templates = _centroids(
            train, state_ids[train_mask], unique_states.shape[0]
        )
        if noise_sigma:
            test = test + rng.standard_normal(test.shape) * noise_sigma
        distances = _squared_distances(test, templates)
        nearest = np.argmin(distances, axis=1)
        first_two = np.partition(distances, 1, axis=1)[:, :2]
        first_two.sort(axis=1)
        margin = (first_two[:, 1] - first_two[:, 0]) / (first_two[:, 1] + 1e-12)
        top3 = np.argpartition(distances, 2, axis=1)[:, :3]

        fold_true = state_ids[test_mask]
        predicted_ids.append(nearest)
        true_ids.append(fold_true)
        top3_hits.append(np.any(top3 == fold_true[:, None], axis=1))
        margins.append(margin)

    predicted = np.concatenate(predicted_ids)
    truth = np.concatenate(true_ids)
    top3 = np.concatenate(top3_hits)
    margin = np.concatenate(margins)
    predicted_states = unique_states[predicted]
    true_states = unique_states[truth]
    exact = predicted == truth
    hidden_equal = predicted_states[:, hidden_attributes] == true_states[:, hidden_attributes]
    visible_attributes = tuple(
        index for index in range(dataset["axis_count"]) if index not in hidden_attributes
    )
    visible_equal = (
        predicted_states[:, visible_attributes] == true_states[:, visible_attributes]
        if visible_attributes
        else np.ones((truth.size, 1), dtype=bool)
    )

    correct_margin = margin[exact]
    incorrect_margin = margin[~exact]
    per_axis = {
        ATTRIBUTE_NAMES[index]: float(np.mean(predicted_states[:, index] == true_states[:, index]))
        for index in hidden_attributes
    }

    return {
        "status": "OK",
        "feature_count": int(indices.size),
        "sample_count": int(truth.size),
        "exact_state_accuracy": float(np.mean(exact)),
        "top3_state_accuracy": float(np.mean(top3)),
        "hidden_tuple_accuracy": float(np.mean(np.all(hidden_equal, axis=1))),
        "hidden_symbol_accuracy": float(np.mean(hidden_equal)),
        "visible_tuple_consistency": float(np.mean(np.all(visible_equal, axis=1))),
        "hidden_tuple_chance": completion_chance,
        "hidden_axis_accuracy": per_axis,
        "confidence_margin_auc_for_exact_state": binary_auc(
            correct_margin, incorrect_margin
        ),
        "mean_margin_correct": (
            float(np.mean(correct_margin)) if correct_margin.size else None
        ),
        "mean_margin_incorrect": (
            float(np.mean(incorrect_margin)) if incorrect_margin.size else None
        ),
    }


def _known_state_mask(unique_states: np.ndarray) -> np.ndarray:
    velocity_bits = (unique_states[:, 2:] > 0).astype(int)
    parity = (
        unique_states[:, 0]
        + unique_states[:, 1]
        + velocity_bits[:, 0]
        + velocity_bits[:, 1]
    ) % 2
    return parity == 0


def evaluate_sparse_vocabulary(
    dataset: dict[str, Any], method: str, noise_sigma: float, seed: int
) -> dict[str, Any]:
    indices = feature_indices(dataset, method, ())
    if indices.size == 0:
        raise ValueError("Sparse-vocabulary evaluation requires visible features")

    features = dataset["features"][:, indices]
    state_ids = dataset["state_ids"]
    repeat_ids = dataset["repeat_ids"]
    unique_states = dataset["unique_states"]
    known_states = _known_state_mask(unique_states)
    rng = np.random.default_rng(seed)

    fold_results = []
    all_known_scores: list[np.ndarray] = []
    all_unknown_scores: list[np.ndarray] = []

    for fold in range(dataset["repeats"]):
        calibration_fold = (fold + 1) % dataset["repeats"]
        template_mask = (
            (repeat_ids != fold)
            & (repeat_ids != calibration_fold)
            & known_states[state_ids]
        )
        calibration_mask = (repeat_ids == calibration_fold) & known_states[state_ids]
        test_mask = repeat_ids == fold

        template_train, calibration, test = _standardize(
            features[template_mask], features[calibration_mask], features[test_mask]
        )
        template_state_ids = state_ids[template_mask]
        known_ids = np.flatnonzero(known_states)
        id_to_position = np.full(unique_states.shape[0], -1, dtype=int)
        id_to_position[known_ids] = np.arange(known_ids.size)
        compact_template_ids = id_to_position[template_state_ids]
        templates = _centroids(
            template_train, compact_template_ids, known_ids.size
        )

        if noise_sigma:
            calibration = calibration + rng.standard_normal(calibration.shape) * noise_sigma
            test = test + rng.standard_normal(test.shape) * noise_sigma

        calibration_distance = np.min(
            _squared_distances(calibration, templates), axis=1
        )
        threshold = float(np.quantile(calibration_distance, 0.95))
        test_distances = _squared_distances(test, templates)
        minimum_distance = np.min(test_distances, axis=1)
        nearest_compact = np.argmin(test_distances, axis=1)
        predicted_state_ids = known_ids[nearest_compact]
        test_state_ids = state_ids[test_mask]
        test_known = known_states[test_state_ids]

        known_scores = -minimum_distance[test_known]
        unknown_scores = -minimum_distance[~test_known]
        all_known_scores.append(known_scores)
        all_unknown_scores.append(unknown_scores)
        accepted = minimum_distance <= threshold

        fold_results.append(
            {
                "fold": fold,
                "calibration_repeat": calibration_fold,
                "threshold": threshold,
                "known_exact_retrieval": float(
                    np.mean(predicted_state_ids[test_known] == test_state_ids[test_known])
                ),
                "known_acceptance": float(np.mean(accepted[test_known])),
                "unknown_rejection": float(np.mean(~accepted[~test_known])),
                "known_vs_unknown_auc": binary_auc(known_scores, unknown_scores),
            }
        )

    def mean_metric(name: str) -> float:
        return float(np.mean([row[name] for row in fold_results]))

    return {
        "status": "OK",
        "feature_count": int(indices.size),
        "known_state_count": int(np.sum(known_states)),
        "unknown_state_count": int(np.sum(~known_states)),
        "split_rule": "(x + y + I[vx>0] + I[vy>0]) mod 2 == 0 is enrolled",
        "known_exact_retrieval": mean_metric("known_exact_retrieval"),
        "known_acceptance_at_calibrated_95pct": mean_metric("known_acceptance"),
        "unknown_rejection_at_calibrated_95pct": mean_metric("unknown_rejection"),
        "known_vs_unknown_auc": binary_auc(
            np.concatenate(all_known_scores), np.concatenate(all_unknown_scores)
        ),
        "folds": fold_results,
        "interpretation": (
            "This tests geometric known-state versus held-out-state rejection. The parity "
            "split is not a semantic vocabulary and cannot establish word validity."
        ),
    }


def _aggregate_completion(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for noise_sigma in sorted({row["noise_sigma"] for row in rows}):
        for method in METHODS:
            for hidden_count in range(1, 5):
                selected = [
                    row
                    for row in rows
                    if row["noise_sigma"] == noise_sigma
                    and row["method"] == method
                    and row["hidden_count"] == hidden_count
                    and row["metrics"]["status"] == "OK"
                ]
                if not selected:
                    continue
                output.append(
                    {
                        "noise_sigma": noise_sigma,
                        "method": method,
                        "hidden_count": hidden_count,
                        "combination_count": len(selected),
                        "mean_hidden_tuple_accuracy": float(
                            np.mean(
                                [row["metrics"]["hidden_tuple_accuracy"] for row in selected]
                            )
                        ),
                        "mean_hidden_symbol_accuracy": float(
                            np.mean(
                                [row["metrics"]["hidden_symbol_accuracy"] for row in selected]
                            )
                        ),
                        "mean_exact_state_accuracy": float(
                            np.mean(
                                [row["metrics"]["exact_state_accuracy"] for row in selected]
                            )
                        ),
                        "mean_chance": float(
                            np.mean(
                                [row["metrics"]["hidden_tuple_chance"] for row in selected]
                            )
                        ),
                    }
                )
    return output


def run_analysis(source: Path) -> dict[str, Any]:
    dataset = load_capture(source)
    completion_rows = []
    for noise_sigma in (0.0, 1.0):
        for hidden_count in range(1, dataset["axis_count"] + 1):
            for hidden in itertools.combinations(range(dataset["axis_count"]), hidden_count):
                for method_index, method in enumerate(METHODS):
                    metrics = evaluate_completion(
                        dataset,
                        method,
                        hidden,
                        noise_sigma,
                        seed=7300 + int(noise_sigma * 100) + hidden_count * 10 + method_index,
                    )
                    completion_rows.append(
                        {
                            "noise_sigma": noise_sigma,
                            "method": method,
                            "hidden_attributes": [ATTRIBUTE_NAMES[index] for index in hidden],
                            "hidden_count": hidden_count,
                            "metrics": metrics,
                        }
                    )

    sparse_vocabulary = []
    for noise_sigma in (0.0, 1.0):
        for method_index, method in enumerate(
            ("glass_readout_masked", "modes_only", "wire_visible")
        ):
            sparse_vocabulary.append(
                {
                    "noise_sigma": noise_sigma,
                    "method": method,
                    "metrics": evaluate_sparse_vocabulary(
                        dataset,
                        method,
                        noise_sigma,
                        seed=8100 + int(noise_sigma * 100) + method_index,
                    ),
                }
            )

    return {
        "experiment": "wheel_of_fortune_structural_surrogate",
        "status": "PRELIMINARY_OFFLINE_STRUCTURAL_SURROGATE",
        "source": str(source.relative_to(ROOT)),
        "dataset": {
            "samples": int(dataset["features"].shape[0]),
            "features": int(dataset["features"].shape[1]),
            "modes": dataset["mode_count"],
            "states": int(dataset["unique_states"].shape[0]),
            "repeats": dataset["repeats"],
            "attribute_names": list(ATTRIBUTE_NAMES),
            "attribute_level_counts": dataset["level_counts"],
            "complete_cartesian_grid": True,
        },
        "scope": {
            "supports": [
                "latent physical-state reconstruction from saved modal features",
                "readout-masking sensitivity",
                "geometric known-versus-held-out-state abstention",
            ],
            "does_not_support": [
                "physical missing-symbol queries",
                "word semantics or language modeling",
                "valid unseen-word composition",
                "generation of novel physical states",
            ],
            "critical_caveat": (
                "All four state variables were present during every saved physical capture. "
                "Offline masking removes decoder features, not the corresponding physical drive."
            ),
        },
        "completion": completion_rows,
        "completion_aggregate": _aggregate_completion(completion_rows),
        "sparse_vocabulary_abstention": sparse_vocabulary,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:.1f}%"


def render_report(results: dict[str, Any]) -> str:
    aggregate = results["completion_aggregate"]
    clean = [row for row in aggregate if row["noise_sigma"] == 0.0]
    noisy = [row for row in aggregate if row["noise_sigma"] == 1.0]
    abstention = results["sparse_vocabulary_abstention"]

    lines = [
        "# CWM Wheel of Fortune: Existing-Data Structural Surrogate",
        "",
        "**Status:** PRELIMINARY OFFLINE STRUCTURAL SURROGATE. This is not a symbolic-language or physical missing-letter experiment.",
        "",
        "## Critical Distinction",
        "",
        results["scope"]["critical_caveat"],
        "",
        "A real Wheel-of-Fortune query would omit unknown symbols from the physical input and recapture the response. This archive can only hide decoder-visible feature blocks after a full-state capture. Its honest question is: **how much latent state remains recoverable from the distributed modal response?**",
        "",
        "## Dataset",
        "",
        f"- Source: `{results['source']}`",
        f"- {results['dataset']['samples']} captures, {results['dataset']['states']} states, {results['dataset']['repeats']} repeats",
        f"- {results['dataset']['features']} features, including {results['dataset']['modes']} modal features",
        f"- Complete state grid: 8 x 8 x 2 x 2 = {results['dataset']['states']} states",
        "",
        "Because the grid is complete, it has no dictionary of valid versus invalid words and no held-out compositional state. Pong attributes must not be relabeled as letters.",
        "",
        "## Hidden-Attribute Reconstruction",
        "",
        "Each result uses leave-one-repeat-out state centroids. `glass_readout_masked` removes the selected direct axis-window blocks but retains all modal features. `modes_only` uses only the 212 modal measurements. Noise sigma is measured in training-standardized feature units.",
        "",
        "For `modes_only`, the physical feature vector and predicted state are identical across mask labels; only the subset scored as hidden changes. The aggregate chance column averages attributes with different cardinalities (12.5% for x/y and 50% for vx/vy); use the per-attribute table in the exploration document for the detailed baseline.",
        "",
        "### No added synthetic noise",
        "",
        "| Method | Hidden attributes | Hidden tuple | Hidden symbols | Chance |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in clean:
        lines.append(
            f"| {row['method']} | {row['hidden_count']} | "
            f"{_pct(row['mean_hidden_tuple_accuracy'])} | "
            f"{_pct(row['mean_hidden_symbol_accuracy'])} | "
            f"{_pct(row['mean_chance'])} |"
        )
    lines.extend(
        [
            "",
            "### Sigma = 1 synthetic feature noise",
            "",
            "| Method | Hidden attributes | Hidden tuple | Hidden symbols | Chance |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in noisy:
        lines.append(
            f"| {row['method']} | {row['hidden_count']} | "
            f"{_pct(row['mean_hidden_tuple_accuracy'])} | "
            f"{_pct(row['mean_hidden_symbol_accuracy'])} | "
            f"{_pct(row['mean_chance'])} |"
        )

    lines.extend(
        [
            "",
            "## Sparse-Vocabulary Abstention Proxy",
            "",
            "A deterministic parity split enrolls 128 states and treats the other 128 as unknown. This tests physical-feature geometry and confidence only; parity is not a semantic vocabulary.",
            "",
            "| Method | Sigma | Known exact retrieval | Known accepted | Unknown rejected | Known-vs-unknown AUC |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in abstention:
        metrics = row["metrics"]
        lines.append(
            f"| {row['method']} | {row['noise_sigma']:.1f} | "
            f"{_pct(metrics['known_exact_retrieval'])} | "
            f"{_pct(metrics['known_acceptance_at_calibrated_95pct'])} | "
            f"{_pct(metrics['unknown_rejection_at_calibrated_95pct'])} | "
            f"{metrics['known_vs_unknown_auc']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## What This Settles",
            "",
            "1. It quantifies the Wheel analogy's existing-data core: reconstruction of an enrolled physical state from a restricted decoder view.",
            "2. It measures whether distance can support abstention when half the physical state grid is excluded from enrollment.",
            "3. It does not test physical query completion, symbolic composition, interpolation, or generation.",
            "",
            "## Required Physical Wheel Experiment",
            "",
            "1. Choose a constrained bank of 8 four-symbol codewords, including easy, minimal-pair, and deliberately ambiguous clues.",
            "2. Encode the four symbol positions on four independently controlled tones. Randomize symbol-to-amplitude mapping across sessions so scalar order cannot masquerade as spelling structure.",
            "3. Capture full codewords for enrollment. For each clue, physically turn unknown-position drives off and recapture; do not merely hide FFT bins afterward.",
            "4. Compare CWM with direct wire, Hamming lookup, identical software random projection, and a no-glass electrical path using the same decoder.",
            "5. Score unique-clue top-1 accuracy, ambiguous-clue set recall, invalid-clue abstention, calibration, cross-session transfer, energy, and latency.",
            "",
            "**Initial pass gate:** at least 80% unique-clue completion with one or two positions physically omitted, at least 10 percentage points above direct wire under matched analog noise, unknown-state AUC at least 0.90, and less than 10-point cross-session loss.",
            "",
            "**Kill / reframe:** stop calling it physical completion if the advantage exists only under post-capture readout masking, if direct wire or Hamming lookup matches it, or if every invalid clue is confidently forced to an enrolled codeword.",
            "",
            "## Relationship to PRs #6 and #7",
            "",
            "- PR #7 defines Wheel of Fortune as the retrieval-versus-generation separator. This analysis addresses only the enrolled-state retrieval/abstention edge of that protocol.",
            "- PR #6's Kaprekar benchmark is the next transition-memory stage: a controller repeatedly queries stored successor cards. It does not become acoustic arithmetic, and the current 4-8 robust-slot ceiling requires a reduced graph.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python3 tools/wheel_of_fortune_surrogate.py",
            "```",
            "",
            "Machine-readable details are in `data/results/wheel_of_fortune_surrogate/summary.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source = args.source.resolve() if args.source else _latest_capture()
    results = run_analysis(source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "summary.json"
    report_path = args.output_dir / "report.md"
    summary_path.write_text(json.dumps(results, indent=2) + "\n")
    report_path.write_text(render_report(results))
    print(f"Wrote {summary_path.relative_to(ROOT)}")
    print(f"Wrote {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()