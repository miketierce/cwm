#!/usr/bin/env python3
"""Minimal held-session analyzer for the CWM phonon-symbol-gate protocol.

Input CSV must contain:
    session_id,path_state,query_id,valid,readout_value

The script intentionally uses a one-dimensional scalar readout. Training sessions
define per-query centroids; held-out trials are classified by nearest centroid.
This is not intended to be the best possible decoder. It is a low-complexity
baseline for asking whether a frozen physical mapping is already well separated.

Usage:
    python tools/phonon_gate_analyze.py trials.csv \
        --train session_001 session_002 \
        --test session_003 \
        --glass-state GLASS
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev


def load_rows(path: Path):
    rows = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if str(row.get("valid", "")).lower() not in {"1", "true", "yes"}:
                continue
            try:
                row["readout_value"] = float(row["readout_value"])
            except (KeyError, ValueError):
                continue
            rows.append(row)
    return rows


def centroids(rows, sessions, path_state):
    values = defaultdict(list)
    allowed = set(sessions)
    for r in rows:
        if r["session_id"] in allowed and r["path_state"] == path_state:
            values[r["query_id"]].append(r["readout_value"])
    return {q: mean(v) for q, v in values.items() if v}


def classify(x, refs):
    return min(refs, key=lambda q: abs(x - refs[q]))


def score(rows, sessions, path_state, refs):
    allowed = set(sessions)
    selected = [
        r for r in rows
        if r["session_id"] in allowed and r["path_state"] == path_state and r["query_id"] in refs
    ]
    confusion = Counter()
    correct = 0
    per_class = defaultdict(lambda: [0, 0])
    for r in selected:
        truth = r["query_id"]
        pred = classify(r["readout_value"], refs)
        confusion[(truth, pred)] += 1
        per_class[truth][1] += 1
        if pred == truth:
            correct += 1
            per_class[truth][0] += 1

    recalls = [ok / n for ok, n in per_class.values() if n]
    return {
        "n": len(selected),
        "accuracy": correct / len(selected) if selected else None,
        "balanced_accuracy": mean(recalls) if recalls else None,
        "confusion": {f"{a}->{b}": n for (a, b), n in sorted(confusion.items())},
    }


def binary_margin(rows, sessions, path_state, classes):
    allowed = set(sessions)
    vals = {q: [] for q in classes}
    for r in rows:
        if r["session_id"] in allowed and r["path_state"] == path_state and r["query_id"] in vals:
            vals[r["query_id"]].append(r["readout_value"])
    if any(len(vals[q]) < 2 for q in classes):
        return None
    a, b = classes
    ma, mb = mean(vals[a]), mean(vals[b])
    va, vb = pstdev(vals[a]) ** 2, pstdev(vals[b]) ** 2
    denom = math.sqrt((va + vb) / 2.0)
    return {
        "classes": classes,
        "mean": {a: ma, b: mb},
        "std": {a: math.sqrt(va), b: math.sqrt(vb)},
        "pooled_sigma_margin": abs(ma - mb) / denom if denom > 0 else math.inf,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--test", nargs="+", required=True)
    ap.add_argument("--glass-state", default="GLASS")
    ap.add_argument("--control-state", default="ELECTRICAL_ONLY")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    rows = load_rows(args.csv)
    refs = centroids(rows, args.train, args.glass_state)
    if len(refs) < 2:
        raise SystemExit("Need at least two query classes in training GLASS data")

    result = {
        "decoder": "nearest_scalar_training_centroid",
        "train_sessions": args.train,
        "test_sessions": args.test,
        "centroids": refs,
        "glass": score(rows, args.test, args.glass_state, refs),
        "electrical_only": score(rows, args.test, args.control_state, refs),
    }
    if len(refs) == 2:
        classes = sorted(refs)
        result["glass_binary_margin"] = binary_margin(
            rows, args.test, args.glass_state, classes
        )
        result["electrical_only_binary_margin"] = binary_margin(
            rows, args.test, args.control_state, classes
        )

    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")


if __name__ == "__main__":
    main()
