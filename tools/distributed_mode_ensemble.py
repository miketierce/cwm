#!/usr/bin/env python3
"""Test distributed-mode ensemble recall using saved CWM enrollment data.

This is an offline readout-failure simulation. It asks whether overlapping,
random mode banks make better use of CWM's distributed spectral encoding than
one equally sized bank, contiguous frequency windows, or disjoint partitions.

The protocol is leakage-safe:
  - leave one repeat out;
  - normalize and standardize from the training fold only;
  - build one template per enrolled physical state from training repeats;
  - choose banks and missing-mode masks without looking at labels or test data.

Missing modes are omitted from the distance calculation rather than filled
with synthetic values. Natural repeat-to-repeat measurement variation remains
in the saved captures; no synthetic query noise is added.

Usage:
  python3 tools/distributed_mode_ensemble.py
  python3 tools/distributed_mode_ensemble.py --bank-sizes 32,64 --trials 10
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def parse_csv_numbers(value: str, cast):
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def score_predictions(y_true: np.ndarray, y_pred: np.ndarray, tolerance: int) -> dict:
    return {
        "exact": float(np.mean(y_true == y_pred) * 100.0),
        "tolerant": float(np.mean(np.abs(y_true - y_pred) <= tolerance) * 100.0),
    }


def summarize(values: list[float]) -> dict:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(array.mean()),
        "std": float(array.std()),
        "min": float(array.min()),
        "max": float(array.max()),
    }


def nearest_state_labels(
    queries: np.ndarray,
    templates: np.ndarray,
    state_labels: np.ndarray,
    features: np.ndarray,
) -> np.ndarray:
    """Return labels of nearest state templates on the selected features."""
    query_view = queries[:, features]
    template_view = templates[:, features]
    distances = (
        np.sum(query_view * query_view, axis=1)[:, None]
        + np.sum(template_view * template_view, axis=1)[None, :]
        - 2.0 * query_view @ template_view.T
    )
    return state_labels[np.argmin(distances, axis=1)]


def make_folds(
    features: np.ndarray,
    labels: np.ndarray,
    state_ids: np.ndarray,
    repeats: int,
) -> list[dict]:
    """Build train-only standardized state templates for each held-out repeat."""
    folds = []
    states = np.unique(state_ids)

    for held_out_repeat in range(repeats):
        test = np.arange(len(labels)) % repeats == held_out_repeat
        train = ~test

        mean = features[train].mean(axis=0)
        std = features[train].std(axis=0)
        std[std < 1e-9] = 1.0
        normalized = ((features - mean) / std).astype(np.float32)

        templates = np.empty((len(states), features.shape[1]), dtype=np.float32)
        state_labels = np.empty(len(states), dtype=int)
        for index, state in enumerate(states):
            state_train = train & (state_ids == state)
            templates[index] = normalized[state_train].mean(axis=0)
            state_labels[index] = int(np.median(labels[state_train]))

        folds.append(
            {
                "queries": normalized[test],
                "templates": templates,
                "state_labels": state_labels,
                "true_labels": labels[test].astype(int),
            }
        )

    return folds


def intersect_banks(
    banks: list[np.ndarray],
    available: np.ndarray,
    min_features: int,
) -> list[np.ndarray]:
    effective = []
    for bank in banks:
        retained = np.intersect1d(bank, available, assume_unique=True)
        if len(retained) >= min_features:
            effective.append(retained)
    return effective


def evaluate_banks(
    folds: list[dict],
    banks: list[np.ndarray],
    available: np.ndarray,
    tolerance: int,
    min_features: int,
) -> dict:
    effective = intersect_banks(banks, available, min_features)
    if not effective:
        return {"valid": False, "n_banks": 0}

    truths = []
    ensemble_predictions = []
    individual_predictions = [[] for _ in effective]

    for fold in folds:
        predictions = []
        for bank_index, bank in enumerate(effective):
            predicted = nearest_state_labels(
                fold["queries"],
                fold["templates"],
                fold["state_labels"],
                bank,
            )
            predictions.append(predicted)
            individual_predictions[bank_index].append(predicted)

        prediction_matrix = np.stack(predictions)
        # Landing is ordinal; median voting is deterministic and robust to outliers.
        ensemble = np.rint(np.median(prediction_matrix, axis=0)).astype(int)
        truths.append(fold["true_labels"])
        ensemble_predictions.append(ensemble)

    y_true = np.concatenate(truths)
    y_ensemble = np.concatenate(ensemble_predictions)
    individual_scores = []
    for predictions in individual_predictions:
        individual_scores.append(
            score_predictions(y_true, np.concatenate(predictions), tolerance)
        )

    feature_counts = np.array([len(bank) for bank in effective])
    covered = len(np.unique(np.concatenate(effective)))
    return {
        "valid": True,
        "n_banks": len(effective),
        "available_coverage": int(covered),
        "features_per_bank": {
            "min": int(feature_counts.min()),
            "median": float(np.median(feature_counts)),
            "max": int(feature_counts.max()),
        },
        "ensemble": score_predictions(y_true, y_ensemble, tolerance),
        "single_bank": {
            "exact": summarize([score["exact"] for score in individual_scores]),
            "tolerant": summarize([score["tolerant"] for score in individual_scores]),
        },
    }


def overlapping_random_banks(
    n_modes: int,
    bank_size: int,
    n_voters: int,
    rng: np.random.Generator,
) -> list[np.ndarray]:
    size = min(bank_size, n_modes)
    return [np.sort(rng.choice(n_modes, size=size, replace=False)) for _ in range(n_voters)]


def contiguous_banks(n_modes: int, bank_size: int, n_voters: int) -> list[np.ndarray]:
    size = min(bank_size, n_modes)
    if size == n_modes:
        return [np.arange(n_modes)]
    starts = np.rint(np.linspace(0, n_modes - size, n_voters)).astype(int)
    return [np.arange(start, start + size) for start in starts]


def disjoint_random_banks(
    n_modes: int,
    bank_size: int,
    rng: np.random.Generator,
) -> list[np.ndarray]:
    n_banks = max(1, int(np.ceil(n_modes / bank_size)))
    return [np.sort(bank) for bank in np.array_split(rng.permutation(n_modes), n_banks)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "npz",
        nargs="?",
        default="data/results/pong/recall_enroll_20260629_120542.npz",
    )
    parser.add_argument("--bank-sizes", default="32,64")
    parser.add_argument("--dropouts", default="0,0.5,0.75,0.9")
    parser.add_argument("--voters", type=int, default=11)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--min-features", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260711)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    bank_sizes = parse_csv_numbers(args.bank_sizes, int)
    dropouts = parse_csv_numbers(args.dropouts, float)
    if any(size <= 0 for size in bank_sizes):
        parser.error("bank sizes must be positive")
    if any(dropout < 0 or dropout >= 1 for dropout in dropouts):
        parser.error("dropouts must be in [0, 1)")

    data = np.load(args.npz)
    all_features = data["X"].astype(float)
    labels = data["L"].astype(int)
    state_ids = data["GI"].astype(int)
    repeats = int(data["repeats"])
    tolerance = int(data["padh"]) // 2
    axis_block = int(data["nw"]) * int(data["naxes"])

    # Per-capture normalization is the established drift correction. Only modal
    # features enter this experiment; directly driven axis windows are excluded.
    all_features /= all_features.mean(axis=1, keepdims=True) + 1e-9
    modes = all_features[:, axis_block:]
    n_modes = modes.shape[1]
    folds = make_folds(modes, labels, state_ids, repeats)

    constant_exact = max(np.mean(labels == label) for label in np.unique(labels)) * 100
    constant_tolerant = max(
        np.mean(np.abs(labels - label) <= tolerance) for label in np.unique(labels)
    ) * 100

    print(
        f"Loaded {args.npz}: {len(labels)} captures, {len(np.unique(state_ids))} states, "
        f"{n_modes} modal features, {repeats} repeats"
    )
    print(
        f"Constant-label baselines: exact={constant_exact:.1f}%, "
        f"tolerant={constant_tolerant:.1f}%"
    )

    result = {
        "source": args.npz,
        "protocol": {
            "decoder": "nearest training-state centroid; ordinal median vote",
            "validation": "leave-one-repeat-out",
            "features": "modes only; directly driven axis windows excluded",
            "dropout": "global random missing-mode mask; omitted from distance",
            "n_modes": n_modes,
            "n_states": int(len(np.unique(state_ids))),
            "repeats": repeats,
            "voters": args.voters,
            "trials": args.trials,
            "seed": args.seed,
            "tolerance": tolerance,
        },
        "constant_baseline": {
            "exact": float(constant_exact),
            "tolerant": float(constant_tolerant),
        },
        "bank_sizes": {},
    }

    all_mode_indices = np.arange(n_modes)
    seed_sequence = np.random.SeedSequence(args.seed)
    trial_seeds = seed_sequence.spawn(len(bank_sizes) * len(dropouts) * args.trials)
    seed_index = 0

    for bank_size in bank_sizes:
        print(f"\nBank size {bank_size}")
        size_result = {}
        for dropout in dropouts:
            trial_records = []
            for _ in range(args.trials):
                rng = np.random.default_rng(trial_seeds[seed_index])
                seed_index += 1
                n_available = max(args.min_features, int(round(n_modes * (1.0 - dropout))))
                available = np.sort(
                    rng.choice(n_modes, size=min(n_available, n_modes), replace=False)
                )

                overlapping = overlapping_random_banks(
                    n_modes, bank_size, args.voters, rng
                )
                contiguous = contiguous_banks(n_modes, bank_size, args.voters)
                disjoint = disjoint_random_banks(n_modes, bank_size, rng)

                trial_records.append(
                    {
                        "n_available": int(len(available)),
                        "full": evaluate_banks(
                            folds,
                            [all_mode_indices],
                            available,
                            tolerance,
                            args.min_features,
                        ),
                        "overlapping_random": evaluate_banks(
                            folds,
                            overlapping,
                            available,
                            tolerance,
                            args.min_features,
                        ),
                        "contiguous": evaluate_banks(
                            folds,
                            contiguous,
                            available,
                            tolerance,
                            args.min_features,
                        ),
                        "disjoint_random": evaluate_banks(
                            folds,
                            disjoint,
                            available,
                            tolerance,
                            args.min_features,
                        ),
                    }
                )

            methods = ["full", "overlapping_random", "contiguous", "disjoint_random"]
            summary = {"n_available": summarize([r["n_available"] for r in trial_records])}
            for method in methods:
                valid = [r[method] for r in trial_records if r[method].get("valid")]
                summary[method] = {
                    "exact": summarize([record["ensemble"]["exact"] for record in valid]),
                    "tolerant": summarize(
                        [record["ensemble"]["tolerant"] for record in valid]
                    ),
                    "n_banks": summarize([record["n_banks"] for record in valid]),
                    "coverage": summarize(
                        [record["available_coverage"] for record in valid]
                    ),
                }
                if method != "full":
                    summary[method]["single_bank_tolerant"] = summarize(
                        [record["single_bank"]["tolerant"]["mean"] for record in valid]
                    )

            overlap_gain = (
                summary["overlapping_random"]["tolerant"]["mean"]
                - summary["overlapping_random"]["single_bank_tolerant"]["mean"]
            )
            summary["overlap_vote_gain_vs_single_bank"] = float(overlap_gain)
            summary["trials"] = trial_records
            size_result[str(dropout)] = summary

            print(
                f"  drop={dropout:>4.0%} avail={summary['n_available']['mean']:5.1f} | "
                f"full {summary['full']['tolerant']['mean']:5.1f} | "
                f"single {summary['overlapping_random']['single_bank_tolerant']['mean']:5.1f} | "
                f"overlap {summary['overlapping_random']['tolerant']['mean']:5.1f} "
                f"({overlap_gain:+4.1f}) | "
                f"contig {summary['contiguous']['tolerant']['mean']:5.1f} | "
                f"disjoint {summary['disjoint_random']['tolerant']['mean']:5.1f}"
            )

        result["bank_sizes"][str(bank_size)] = size_result

    source_suffix = Path(args.npz).stem.split("_")[-1]
    output = Path(args.output) if args.output else Path(args.npz).with_name(
        f"distributed_mode_ensemble_{source_suffix}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as handle:
        json.dump(result, handle, indent=2)
    print(f"\nSaved {output}")


if __name__ == "__main__":
    main()