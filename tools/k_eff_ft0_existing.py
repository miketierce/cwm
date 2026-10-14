#!/usr/bin/env python3
"""FT-0 retrospective diagnostics for an existing CWM multitone NPZ.

Hypothesis-forming only. Measures:
- standardized covariance/effective-rank diagnostics;
- simple cross-validated recovery of simultaneously encoded drive variables.

It does NOT establish held-session K_eff because historical captures do not
contain the full later-session + Ch-B + electrical-only control structure.

Default input:
  data/results/pong/pong_multitone_data_20260620_225626.npz
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def rank_stats(X: np.ndarray) -> dict:
    X = np.asarray(X, dtype=float)
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-12] = 1.0
    Z = (X - mu) / sd
    ev = np.linalg.eigvalsh(np.cov(Z, rowvar=False))[::-1]
    ev = np.clip(ev, 0.0, None)
    total = float(ev.sum())
    if total <= 0:
        return {
            "entropy_effective_rank": 0.0,
            "stable_rank": 0.0,
            "rank90": 0,
            "rank95": 0,
            "rank99": 0,
            "top_eigenvalues": [],
        }

    p = ev[ev > 0] / total
    entropy_rank = float(np.exp(-(p * np.log(p)).sum()))
    stable_rank = float(total / ev[0])
    c = np.cumsum(ev) / total

    def rank_at(frac: float) -> int:
        return int(np.searchsorted(c, frac) + 1)

    return {
        "entropy_effective_rank": entropy_rank,
        "stable_rank": stable_rank,
        "rank90": rank_at(0.90),
        "rank95": rank_at(0.95),
        "rank99": rank_at(0.99),
        "top_eigenvalues": [float(v) for v in ev[:8]],
    }


def ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float = 1.0):
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-12] = 1.0
    Z = (X - mu) / sd

    ym = float(y.mean())
    ys = float(y.std())
    if ys < 1e-12:
        ys = 1.0
    yz = (y - ym) / ys

    A = Z.T @ Z + alpha * np.eye(Z.shape[1])
    w = np.linalg.solve(A, Z.T @ yz)
    b = float(yz.mean() - Z.mean(axis=0) @ w)
    return np.concatenate([w, [b]]), (mu, sd, ym, ys)


def ridge_predict(X: np.ndarray, model: np.ndarray, norm) -> np.ndarray:
    mu, sd, ym, ys = norm
    Z = (X - mu) / sd
    w, b = model[:-1], model[-1]
    return (Z @ w + b) * ys + ym


def cv_decode(X: np.ndarray, drives: np.ndarray, folds: int = 4, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    idx = np.arange(len(X))
    rng.shuffle(idx)
    splits = np.array_split(idx, folds)
    pred = np.full_like(drives, np.nan, dtype=float)

    for test_idx in splits:
        train_mask = np.ones(len(X), dtype=bool)
        train_mask[test_idx] = False
        train_idx = np.where(train_mask)[0]

        for k in range(drives.shape[1]):
            model, norm = ridge_fit(X[train_idx], drives[train_idx, k], alpha=1.0)
            pred[test_idx, k] = ridge_predict(X[test_idx], model, norm)

    per_input = []
    nearest = np.empty_like(pred)
    for k in range(drives.shape[1]):
        truth = drives[:, k]
        pk = pred[:, k]
        ss_tot = float(((truth - truth.mean()) ** 2).sum())
        ss_res = float(((truth - pk) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

        levels = np.unique(truth)
        nearest[:, k] = levels[
            np.argmin(np.abs(pk[:, None] - levels[None, :]), axis=1)
        ]
        acc = float(np.mean(nearest[:, k] == truth))

        per_input.append(
            {
                "levels": int(len(levels)),
                "r2": float(r2),
                "nearest_level_accuracy": acc,
                "naive_chance": float(1.0 / len(levels)),
            }
        )

    joint = float(np.mean(np.all(nearest == drives, axis=1)))
    joint_chance = float(
        np.prod(
            [1.0 / len(np.unique(drives[:, k])) for k in range(drives.shape[1])]
        )
    )

    return {
        "per_input": per_input,
        "joint_accuracy": joint,
        "joint_naive_chance": joint_chance,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "npz",
        nargs="?",
        type=Path,
        default=Path(
            "data/results/pong/pong_multitone_data_20260620_225626.npz"
        ),
    )
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    d = np.load(args.npz, allow_pickle=False)
    Y = np.asarray(d["Y"], dtype=float)
    drives = np.asarray(d["drive_freqs"], dtype=float)

    if Y.ndim != 2 or drives.ndim != 2:
        raise SystemExit("Expected 2-D Y and drive_freqs arrays")
    if len(Y) != len(drives):
        raise SystemExit("Y and drive_freqs must contain the same number of trials")

    n_intermod = 9
    n_drive_amp = drives.shape[1]
    n_modes = Y.shape[1] - n_drive_amp - n_intermod
    if n_modes <= 0:
        raise SystemExit("Could not infer historical feature layout")

    modes = Y[:, :n_modes]
    drive_amp = Y[:, n_modes : n_modes + n_drive_amp]
    intermod = Y[:, n_modes + n_drive_amp :]
    modes_plus_intermod = np.concatenate([modes, intermod], axis=1)

    result = {
        "source": str(args.npz),
        "status": "FT-0 hypothesis-forming retrospective diagnostic",
        "shape": {
            "trials": int(Y.shape[0]),
            "modes": int(n_modes),
            "drive_amplitude_features": int(n_drive_amp),
            "intermod_features": int(n_intermod),
            "total_features": int(Y.shape[1]),
            "simultaneous_encoded_inputs": int(drives.shape[1]),
        },
        "rank": {
            "modes_only": rank_stats(modes),
            "drive_amplitudes": rank_stats(drive_amp),
            "intermod_only": rank_stats(intermod),
            "all_features": rank_stats(Y),
        },
        "decode": {
            "modes_only": cv_decode(modes, drives),
            "intermod_only": cv_decode(intermod, drives),
            "modes_plus_intermod": cv_decode(modes_plus_intermod, drives),
            "all_features": cv_decode(Y, drives),
        },
        "limitations": [
            "same-session historical data",
            "no simultaneous Ch-B reference in this capture",
            "no electrical-only matched control",
            "state rows are averaged spectra rather than independent raw repeats",
            "rank is a representation upper bound, not held-session K_eff",
        ],
    }

    text_out = json.dumps(result, indent=2)
    print(text_out)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text_out + "\n")


if __name__ == "__main__":
    main()
