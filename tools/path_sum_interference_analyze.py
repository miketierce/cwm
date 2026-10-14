#!/usr/bin/env python3
"""Analyze FT-3P coherent path-sum measurements.

Expected CSV fields:
    condition        A | B | AB
    phase_rad
    rx_real
    rx_imag
    target           optional binary label for FT-3P-B
    split            train | test (optional)

For FT-3P-A, the script estimates mean complex responses for A and B and tests
whether AB(phi) is predicted by coherent addition better than incoherent
magnitude addition.

This is a classical-wave analysis tool. It does not test a quantum path integral.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


def load_rows(path: Path):
    out = []
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            try:
                r["phase_rad"] = float(r["phase_rad"])
                r["rx"] = complex(float(r["rx_real"]), float(r["rx_imag"]))
            except (KeyError, ValueError):
                continue
            out.append(r)
    return out


def mean_complex(vals):
    return sum(vals) / len(vals)


def normalized_rmse(y, pred):
    y = np.asarray(y, dtype=complex)
    pred = np.asarray(pred, dtype=complex)
    rmse = float(np.sqrt(np.mean(np.abs(y - pred) ** 2)))
    scale = float(np.sqrt(np.mean(np.abs(y) ** 2)))
    return rmse / scale if scale > 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--json-output", type=Path)
    args = ap.parse_args()

    rows = load_rows(args.csv)
    a = [r["rx"] for r in rows if r["condition"] == "A"]
    b = [r["rx"] for r in rows if r["condition"] == "B"]
    ab = [r for r in rows if r["condition"] == "AB"]

    if not a or not b or not ab:
        raise SystemExit("Need A, B, and AB conditions")

    ya = mean_complex(a)
    yb = mean_complex(b)

    measured = []
    coherent = []
    incoherent_mag = []

    for r in ab:
        phi = r["phase_rad"]
        measured.append(r["rx"])
        coherent.append(ya + np.exp(1j * phi) * yb)
        incoherent_mag.append(math.sqrt(abs(ya) ** 2 + abs(yb) ** 2))

    coh_nrmse = normalized_rmse(measured, coherent)
    measured_mag = np.asarray([abs(x) for x in measured], dtype=float)
    incoh = np.asarray(incoherent_mag, dtype=float)
    incoh_rmse = float(np.sqrt(np.mean((measured_mag - incoh) ** 2)))
    mag_scale = float(np.sqrt(np.mean(measured_mag ** 2)))
    incoh_nrmse = incoh_rmse / mag_scale if mag_scale > 0 else None

    mags = [abs(x) for x in measured]
    result = {
        "status": "classical coherent path-sum diagnostic",
        "n_A": len(a),
        "n_B": len(b),
        "n_AB": len(ab),
        "Y_A": {"real": ya.real, "imag": ya.imag, "magnitude": abs(ya)},
        "Y_B": {"real": yb.real, "imag": yb.imag, "magnitude": abs(yb)},
        "coherent_complex_nrmse": coh_nrmse,
        "incoherent_magnitude_nrmse": incoh_nrmse,
        "coherent_model_better": (
            coh_nrmse is not None
            and incoh_nrmse is not None
            and coh_nrmse < incoh_nrmse
        ),
        "measured_constructive_to_destructive_ratio": (
            max(mags) / min(mags) if mags and min(mags) > 0 else None
        ),
        "claim_boundary": (
            "Tests classical complex-amplitude interference only; "
            "does not test a quantum Feynman path integral."
        ),
    }

    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n")


if __name__ == "__main__":
    main()
