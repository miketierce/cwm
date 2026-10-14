#!/usr/bin/env python3
"""FT-0 held-token binary multiplexing diagnostic.

Uses the historical L=2 calibration containing all 256 eight-bit patterns with
six physical repetitions per token. Thresholds are fit on training token
combinations and evaluated on repetitions from unseen token combinations.

This is hypothesis-forming only. Ch B was disabled in the historical capture,
so high accuracy demonstrates multiplexed distinguishability, not a glass-vs-
electrical computational advantage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def split_tokens(ids: np.ndarray, folds: int, seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    ids = np.asarray(ids, dtype=int).copy()
    rng.shuffle(ids)
    return [ids[i::folds] for i in range(folds)]


def evaluate_plate(pdata: dict, folds: int = 4, seed: int = 42) -> dict:
    data = pdata["data"]
    token_ids = np.array(sorted(int(k) for k in data.keys()), dtype=int)
    fold_ids = split_tokens(token_ids, folds, seed)

    bit_correct = np.zeros(8, dtype=int)
    bit_total = np.zeros(8, dtype=int)
    exact_correct = 0
    exact_total = 0

    for held in fold_ids:
        held_set = set(int(x) for x in held)
        train_ids = [t for t in token_ids if int(t) not in held_set]

        rules = []
        for m in range(8):
            class0 = []
            class1 = []
            for tid in train_ids:
                rec = data[str(int(tid))]
                dst = class1 if int(rec["digits"][m]) else class0
                dst.extend(float(rep[m]) for rep in rec["reps"])

            m0 = float(np.mean(class0))
            m1 = float(np.mean(class1))
            rules.append(
                {
                    "threshold": 0.5 * (m0 + m1),
                    "one_is_high": bool(m1 > m0),
                    "mean0": m0,
                    "mean1": m1,
                }
            )

        for tid in held:
            rec = data[str(int(tid))]
            truth = np.asarray(rec["digits"], dtype=int)
            for rep in rec["reps"]:
                rep = np.asarray(rep, dtype=float)
                pred = np.zeros(8, dtype=int)
                for m, rule in enumerate(rules):
                    high = rep[m] >= rule["threshold"]
                    pred[m] = int(high if rule["one_is_high"] else not high)
                    bit_total[m] += 1
                    bit_correct[m] += int(pred[m] == truth[m])

                exact_total += 1
                exact_correct += int(np.all(pred == truth))

    per_bit = bit_correct / bit_total
    return {
        "n_tokens": int(len(token_ids)),
        "n_reps_per_token": int(len(data[str(int(token_ids[0]))]["reps"])),
        "per_bit_accuracy": [float(v) for v in per_bit],
        "mean_bit_accuracy": float(per_bit.mean()),
        "exact_8bit_token_accuracy": float(exact_correct / exact_total),
        "held_physical_rep_predictions": int(exact_total),
        "folds": int(folds),
        "seed": int(seed),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "json_file",
        nargs="?",
        type=Path,
        default=Path(
            "data/results/lab/plate_exps/esn_v4_L2_20260413_221433.json"
        ),
    )
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json-output", type=Path)
    args = ap.parse_args()

    d = json.loads(args.json_file.read_text())
    out = {
        "source": str(args.json_file),
        "status": "FT-0 hypothesis-forming retrospective diagnostic",
        "acquisition": {
            "simultaneous_encoded_bits": int(d["n_modes"]),
            "alphabet_size": int(d["total_alphabet"]),
            "n_calibrated_tokens": int(d["n_calibrated"]),
            "n_reps": int(d["n_reps"]),
            "historical_scope_note": (
                "one Ch-A receive path; Ch B disabled in plate_sequence_esn_v4.py"
            ),
        },
        "plates": {},
        "limitations": [
            "same-session historical data",
            "no simultaneous Ch-B electrical reference",
            "no matched electrical-only control",
            "input bit identity is directly present in the driven tone set",
            "therefore accuracy demonstrates multiplexed distinguishability, not glass computational advantage",
        ],
    }

    for pid, pdata in d["per_plate"].items():
        out["plates"][pid] = evaluate_plate(
            pdata, folds=args.folds, seed=args.seed
        )

    text = json.dumps(out, indent=2)
    print(text)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n")


if __name__ == "__main__":
    main()
