#!/usr/bin/env python3
"""Summarize a measured K_eff/readout-complexity frontier.

Input is a CSV with the fields documented in docs/K_EFF_FAST_TRACK.md.
This tool does not estimate K_eff from raw signals; it summarizes already
validated frontier points.

Example:
    python tools/k_eff_frontier.py data/results/k_eff/frontier.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean

COST_AXES = [
    "adc_conversions",
    "acquisition_window_s",
    "receive_channels",
    "digital_ops",
    "calibration_bytes",
    "calibration_trials",
    "system_energy_j",
]


def load(path: Path):
    rows = []
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            if str(r.get("valid", "")).lower() not in {"1", "true", "yes"}:
                continue
            try:
                r["k_eff_rank"] = float(r["k_eff_rank"])
                r["k_eff_task"] = float(r["k_eff_task"])
            except (KeyError, ValueError):
                continue
            for k in COST_AXES:
                v = r.get(k, "")
                try:
                    r[k] = float(v) if v not in {"", None} else None
                except ValueError:
                    r[k] = None
            rows.append(r)
    return rows


def loglog_alpha(points):
    pts = [(c, k) for c, k in points if c and c > 0 and k and k > 0]
    if len(pts) < 3:
        return None
    xs = [math.log(c) for c, _ in pts]
    ys = [math.log(k) for _, k in pts]
    xm, ym = mean(xs), mean(ys)
    denom = sum((x - xm) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / denom


def summarize_axis(rows, axis, kfield):
    pts = [(r[axis], r[kfield], r) for r in rows if r.get(axis) is not None]
    if not pts:
        return {"n": 0}

    pts.sort(key=lambda x: x[0])
    efficiencies = []
    marginals = []
    for c, k, r in pts:
        efficiencies.append({
            "cost": c,
            "k_eff": k,
            "k_per_cost": (k / c) if c > 0 else None,
            "experiment_id": r.get("experiment_id"),
        })

    for (c0, k0, _), (c1, k1, _) in zip(pts, pts[1:]):
        dc = c1 - c0
        if dc != 0:
            marginals.append({
                "cost_from": c0,
                "cost_to": c1,
                "delta_k_per_delta_cost": (k1 - k0) / dc,
            })

    unique_costs = len({c for c, _, _ in pts})
    return {
        "n": len(pts),
        "unique_costs": unique_costs,
        "cost_min": min(c for c, _, _ in pts),
        "cost_max": max(c for c, _, _ in pts),
        "k_min": min(k for _, k, _ in pts),
        "k_max": max(k for _, k, _ in pts),
        "alpha_loglog": loglog_alpha([(c, k) for c, k, _ in pts]),
        "best_efficiency": max(
            (e for e in efficiencies if e["k_per_cost"] is not None),
            key=lambda e: e["k_per_cost"],
            default=None,
        ),
        "marginals": marginals,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument(
        "--k-field",
        choices=["k_eff_rank", "k_eff_task"],
        default="k_eff_task",
    )
    ap.add_argument("--path-state", default="GLASS")
    ap.add_argument("--json-output", type=Path)
    args = ap.parse_args()

    rows = [
        r for r in load(args.csv)
        if r.get("path_state") == args.path_state
    ]
    if not rows:
        raise SystemExit("No valid rows for requested path state")

    result = {
        "k_field": args.k_field,
        "path_state": args.path_state,
        "n_points": len(rows),
        "axes": {
            axis: summarize_axis(rows, axis, args.k_field)
            for axis in COST_AXES
        },
        "interpretation": {
            "alpha_lt_1": "K_eff grows sublinearly with this cost axis over the measured range.",
            "alpha_near_1": "K_eff is approximately proportional to this cost axis over the measured range.",
            "alpha_gt_1": "K_eff grows superlinearly with this cost axis over the measured range; do not extrapolate beyond the measured range.",
            "constant_cost": "If cost is effectively constant while K_eff increases, report the fixed-cost multiplexing regime directly rather than fitting alpha."
        }
    }

    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n")


if __name__ == "__main__":
    main()
