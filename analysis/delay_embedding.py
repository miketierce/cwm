#!/usr/bin/env python3
"""
Delay-Embedding Analysis — Offline temporal depth from captured plate features.

Tests whether augmenting the plate's spectral feature vector with lagged
copies X(t-1), X(t-2), ... improves NARMA-10 prediction. This is a pure
software analysis that reuses the same simulation model as narma_ladder.py.

Key question: If a fast temporal reservoir could provide past-step plate
features (via AD9833 or similar), how much would NMSE improve?

Usage:
    python analysis/delay_embedding.py --census <census.json> [--steps 3000] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

# Import from narma_ladder
from narma_ladder import (
    LADDER_CARRIERS_HZ,
    MODE_CLUSTERS_HZ,
    NARMA_ORDER,
    N_WASHOUT,
    RIDGE_ALPHAS,
    compute_readout_freqs,
    generate_narma10,
    simulate_plate_response,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "plate_exps" / "narma10"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def nmse(y_true, y_pred):
    var = np.var(y_true)
    if var == 0:
        return float("inf")
    return float(np.mean((y_true - y_pred) ** 2) / var)


def evaluate_ridge(X_train, y_train, X_test, y_test):
    """Ridge with 5-fold CV alpha selection."""
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_train)
    X_te = scaler.transform(X_test)

    best_cv, best_alpha = float("inf"), 1.0
    kf = KFold(n_splits=5, shuffle=False)
    for alpha in RIDGE_ALPHAS:
        scores = []
        for tr_idx, val_idx in kf.split(X_tr):
            reg = Ridge(alpha=alpha)
            reg.fit(X_tr[tr_idx], y_train[tr_idx])
            scores.append(nmse(y_train[val_idx], reg.predict(X_tr[val_idx])))
        cv = np.mean(scores)
        if cv < best_cv:
            best_cv, best_alpha = cv, alpha

    reg = Ridge(alpha=best_alpha)
    reg.fit(X_tr, y_train)
    return {
        "nmse_train": round(nmse(y_train, reg.predict(X_tr)), 6),
        "nmse_test": round(nmse(y_test, reg.predict(X_te)), 6),
        "alpha": best_alpha,
        "n_features": X_train.shape[1],
    }


def build_delay_embedded(X, depth):
    """Augment X[t] with X[t-1], ..., X[t-depth].

    Returns (X_aug, valid_start) where valid_start is the number of
    rows trimmed from the top to avoid negative indexing.
    """
    if depth == 0:
        return X, 0
    n, d = X.shape
    X_aug = np.zeros((n - depth, d * (depth + 1)))
    for i in range(depth, n):
        for lag in range(depth + 1):
            X_aug[i - depth, lag * d:(lag + 1) * d] = X[i - lag]
    return X_aug, depth


def run_esn(X_input, total_usable, hidden=64, leak=0.5, seed=2000):
    """ESN on arbitrary input features."""
    rng = np.random.default_rng(seed)
    W_in = rng.uniform(-0.1, 0.1, (hidden, X_input.shape[1]))
    W_res = rng.normal(0, 1, (hidden, hidden))
    eigvals = np.abs(np.linalg.eigvals(W_res))
    W_res *= 0.9 / max(eigvals)

    X_esn = np.zeros((total_usable, hidden))
    state = np.zeros(hidden)
    for idx in range(total_usable):
        pre = np.tanh(W_in @ X_input[idx] + W_res @ state)
        state = (1 - leak) * state + leak * pre
        X_esn[idx] = state
    return X_esn


def simulate_plate_vectorized(carriers, readout_freqs, mode_freqs,
                               all_amps, nl_strength=0.15, seed=1000):
    """Vectorized Lorentzian simulation for ALL steps at once.

    all_amps: (n_steps, n_carriers) array of amplitudes [0,1]
    Returns: (n_steps, n_readout) spectrum matrix
    """
    rng = np.random.default_rng(seed)
    n_steps = all_amps.shape[0]
    n_carriers = len(carriers)
    n_readout = len(readout_freqs)
    n_modes = len(mode_freqs)

    mode_Qs = np.full(n_modes, 500.0)
    carriers = np.array(carriers, dtype=np.float64)
    readout = np.array(readout_freqs, dtype=np.float64)
    modes = np.array(mode_freqs, dtype=np.float64)
    bw = modes / (2 * mode_Qs)  # (n_modes,)

    # Precompute Lorentzian gains: drive_gain[c, m] and read_gain[r, m]
    # drive_gain[c, m] = bw[m]^2 / ((carrier[c] - mode[m])^2 + bw[m]^2)
    delta_drive = carriers[:, None] - modes[None, :]  # (n_c, n_m)
    drive_gain = bw[None, :] ** 2 / (delta_drive ** 2 + bw[None, :] ** 2)  # (n_c, n_m)

    delta_read = readout[:, None] - modes[None, :]  # (n_r, n_m)
    read_gain = bw[None, :] ** 2 / (delta_read ** 2 + bw[None, :] ** 2)  # (n_r, n_m)

    # Linear response: for each readout freq, sum over carriers × modes
    # mags[step, r] = sum_c sum_m amp[step,c] * drive_gain[c,m] * read_gain[r,m] * Q[m] * 1000
    # = sum_m read_gain[r,m]*Q[m]*1000 * sum_c amp[step,c]*drive_gain[c,m]
    # Reshape for broadcasting:
    # driven[step, m] = sum_c amp[step,c] * drive_gain[c,m]
    driven = all_amps @ drive_gain  # (n_steps, n_modes)
    # transfer[m] = Q[m] * 1000
    transfer = mode_Qs * 1000  # (n_modes,)
    # linear[step, r] = sum_m driven[step,m] * read_gain[r,m] * transfer[m]
    linear = (driven * transfer[None, :]) @ read_gain.T  # (n_steps, n_readout)

    # Nonlinear IM products: quadratic mixing
    # For each pair (i,k), compute IM frequencies fi+fk and |fi-fk|
    # Then check Lorentzian coupling through modes
    nl_mags = np.zeros((n_steps, n_readout))
    for i in range(n_carriers):
        for k in range(i + 1, n_carriers):
            ai = all_amps[:, i]  # (n_steps,)
            ak = all_amps[:, k]  # (n_steps,)
            prod = ai * ak  # (n_steps,)
            # Skip if all products are zero
            if np.max(prod) < 1e-12:
                continue
            fi, fk = carriers[i], carriers[k]
            for im_f in [fi + fk, abs(fi - fk)]:
                # Lorentzian at IM freq through each mode
                delta_im = im_f - modes  # (n_modes,)
                im_gain = bw ** 2 / (delta_im ** 2 + bw ** 2)  # (n_modes,)
                # im_contribution[r] = sum_m im_gain[m] * read_gain[r,m] * Q[m] * 1000
                im_transfer = im_gain * transfer  # (n_modes,)
                im_to_readout = im_transfer @ read_gain.T  # (n_readout,)
                # nl_mags[step, r] += nl_strength * prod[step] * im_to_readout[r]
                nl_mags += nl_strength * prod[:, None] * im_to_readout[None, :]

    mags = linear + nl_mags
    # Add noise
    noise = rng.normal(0, 50.0, mags.shape)
    return np.abs(mags + noise)


def main():
    parser = argparse.ArgumentParser(
        description="Delay-Embedding Analysis for NARMA-10 Harmonic Ladder")
    parser.add_argument("--census", required=True)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-depth", type=int, default=5,
                        help="Maximum delay embedding depth")
    args = parser.parse_args()

    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 65)
    print("  DELAY-EMBEDDING ANALYSIS — Temporal Depth from Plate Features")
    print("=" * 65)
    print()

    # Load census
    with open(args.census) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    all_mode_freqs = set()
    for key, data in census.items():
        for p in data.get("peaks", []):
            all_mode_freqs.add(p["freq_hz"])
    mode_freqs = sorted(all_mode_freqs)

    # Compute readout frequencies
    readout_freqs, readout_labels, im_map = compute_readout_freqs(
        LADDER_CARRIERS_HZ, MODE_CLUSTERS_HZ)
    n_spec = len(readout_freqs)
    print(f"  Readout freqs: {n_spec}")
    print(f"  Carriers: {[f/1000 for f in LADDER_CARRIERS_HZ]}k")

    # Generate NARMA-10
    u, y = generate_narma10(args.steps, args.seed)
    start = NARMA_ORDER + N_WASHOUT
    total_usable = len(u) - start
    n_train = int(total_usable * 0.67)

    print(f"  Steps: {args.steps}, usable: {total_usable} "
          f"({n_train} train / {total_usable - n_train} test)")

    # Build simulation feature matrix (vectorized Lorentzian)
    print("\n  Building simulated plate features (vectorized)...")
    import time as _time
    t0 = _time.time()

    # Build amplitude matrix for all steps
    all_amps = np.zeros((total_usable, len(LADDER_CARRIERS_HZ)))
    all_windows = np.zeros((total_usable, NARMA_ORDER))
    for idx in range(total_usable):
        t = start + idx
        if t < NARMA_ORDER:
            continue
        window = u[t - 9:t + 1]
        all_amps[idx] = window * 2.0
        all_windows[idx] = window

    # Vectorized simulation
    spectra = simulate_plate_vectorized(
        LADDER_CARRIERS_HZ, readout_freqs, mode_freqs,
        all_amps, nl_strength=0.15, seed=args.seed + 1000)

    # Combine: spectrum + input window
    X = np.hstack([spectra, all_windows])
    print(f"  Feature matrix: {X.shape} ({_time.time() - t0:.1f}s)")

    y_usable = y[start:start + total_usable]

    # ── Baseline evaluations ──────────────────────────────────────────

    print("\n" + "━" * 65)
    print("  BASELINES (no delay embedding)")
    print("━" * 65)

    hdr = f"  {'Approach':<40s} {'Train':>8s} {'Test':>8s} {'Feats':>6s}"
    print(hdr)
    print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*6}")

    results = []

    # Full features (spectrum + input)
    r = evaluate_ridge(X[:n_train], y_usable[:n_train],
                       X[n_train:], y_usable[n_train:])
    r["name"] = "ladder_full_d0"
    results.append(r)
    print(f"  {'ladder_full (depth=0)':<40s} {r['nmse_train']:>8.4f} "
          f"{r['nmse_test']:>8.4f} {r['n_features']:>6d}")

    # Spectrum only
    X_spec = X[:, :n_spec]
    r = evaluate_ridge(X_spec[:n_train], y_usable[:n_train],
                       X_spec[n_train:], y_usable[n_train:])
    r["name"] = "spectrum_only_d0"
    results.append(r)
    print(f"  {'spectrum_only (depth=0)':<40s} {r['nmse_train']:>8.4f} "
          f"{r['nmse_test']:>8.4f} {r['n_features']:>6d}")

    # Input window only
    X_input = X[:, n_spec:]
    r = evaluate_ridge(X_input[:n_train], y_usable[:n_train],
                       X_input[n_train:], y_usable[n_train:])
    r["name"] = "input_only_d0"
    results.append(r)
    print(f"  {'input_only (depth=0)':<40s} {r['nmse_train']:>8.4f} "
          f"{r['nmse_test']:>8.4f} {r['n_features']:>6d}")

    # Software ESN baseline
    X_esn_input = np.zeros((total_usable, NARMA_ORDER))
    for idx in range(total_usable):
        t = start + idx
        X_esn_input[idx] = u[t - 9:t + 1]
    X_esn = run_esn(X_esn_input, total_usable, seed=args.seed + 2000)
    r = evaluate_ridge(X_esn[:n_train], y_usable[:n_train],
                       X_esn[n_train:], y_usable[n_train:])
    r["name"] = "software_esn"
    results.append(r)
    print(f"  {'software_esn (64 hidden)':<40s} {r['nmse_train']:>8.4f} "
          f"{r['nmse_test']:>8.4f} {r['n_features']:>6d}")

    # Ladder + ESN (plate features through ESN)
    X_ladder_esn = run_esn(X, total_usable, seed=args.seed + 3000)
    r = evaluate_ridge(X_ladder_esn[:n_train], y_usable[:n_train],
                       X_ladder_esn[n_train:], y_usable[n_train:])
    r["name"] = "ladder_esn_d0"
    results.append(r)
    print(f"  {'ladder_esn (depth=0)':<40s} {r['nmse_train']:>8.4f} "
          f"{r['nmse_test']:>8.4f} {r['n_features']:>6d}")

    # ── Delay embedding sweep ─────────────────────────────────────────

    print(f"\n{'━' * 65}")
    print(f"  DELAY EMBEDDING: depth 1–{args.max_depth}")
    print(f"{'━' * 65}")

    # Test: full features with delay
    print(f"\n  A. Full features (spectrum + input) with delay embedding:")
    print(hdr)
    print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*6}")

    for depth in range(1, args.max_depth + 1):
        X_aug, trim = build_delay_embedded(X, depth)
        y_aug = y_usable[trim:]
        n_tr = n_train - trim
        if n_tr < 50:
            print(f"  depth={depth}: insufficient training data after trim")
            continue
        r = evaluate_ridge(X_aug[:n_tr], y_aug[:n_tr],
                           X_aug[n_tr:], y_aug[n_tr:])
        r["name"] = f"ladder_full_d{depth}"
        r["depth"] = depth
        results.append(r)
        print(f"  {'ladder_full (depth=' + str(depth) + ')':<40s} "
              f"{r['nmse_train']:>8.4f} {r['nmse_test']:>8.4f} "
              f"{r['n_features']:>6d}")

    # Test: spectrum only with delay
    print(f"\n  B. Spectrum only (no raw input) with delay embedding:")
    print(hdr)
    print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*6}")

    for depth in range(1, args.max_depth + 1):
        X_aug, trim = build_delay_embedded(X_spec, depth)
        y_aug = y_usable[trim:]
        n_tr = n_train - trim
        if n_tr < 50:
            continue
        r = evaluate_ridge(X_aug[:n_tr], y_aug[:n_tr],
                           X_aug[n_tr:], y_aug[n_tr:])
        r["name"] = f"spectrum_only_d{depth}"
        r["depth"] = depth
        results.append(r)
        print(f"  {'spectrum_only (depth=' + str(depth) + ')':<40s} "
              f"{r['nmse_train']:>8.4f} {r['nmse_test']:>8.4f} "
              f"{r['n_features']:>6d}")

    # Test: delay-embedded features through ESN
    print(f"\n  C. Delay-embedded full features → ESN:")
    print(hdr)
    print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*6}")

    for depth in range(1, args.max_depth + 1):
        X_aug, trim = build_delay_embedded(X, depth)
        y_aug = y_usable[trim:]
        n_tr = n_train - trim
        if n_tr < 50:
            continue
        X_aug_esn = run_esn(X_aug, X_aug.shape[0],
                            seed=args.seed + 4000 + depth)
        r = evaluate_ridge(X_aug_esn[:n_tr], y_aug[:n_tr],
                           X_aug_esn[n_tr:], y_aug[n_tr:])
        r["name"] = f"ladder_delay_esn_d{depth}"
        r["depth"] = depth
        results.append(r)
        print(f"  {'ladder_delay_esn (depth=' + str(depth) + ')':<40s} "
              f"{r['nmse_train']:>8.4f} {r['nmse_test']:>8.4f} "
              f"{r['n_features']:>6d}")

    # Test: concat delay-embedded + ESN state
    print(f"\n  D. Delay-embedded full + ESN concat (best of both):")
    print(hdr)
    print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*6}")

    for depth in range(1, args.max_depth + 1):
        X_aug, trim = build_delay_embedded(X, depth)
        y_aug = y_usable[trim:]
        n_tr = n_train - trim
        if n_tr < 50:
            continue
        # ESN on the delay-embedded features
        X_aug_esn = run_esn(X_aug, X_aug.shape[0],
                            seed=args.seed + 5000 + depth)
        # Concat raw delay-embedded + ESN state
        X_combo = np.hstack([X_aug, X_aug_esn])
        r = evaluate_ridge(X_combo[:n_tr], y_aug[:n_tr],
                           X_combo[n_tr:], y_aug[n_tr:])
        r["name"] = f"ladder_delay_combo_d{depth}"
        r["depth"] = depth
        results.append(r)
        print(f"  {'ladder_delay_combo (depth=' + str(depth) + ')':<40s} "
              f"{r['nmse_train']:>8.4f} {r['nmse_test']:>8.4f} "
              f"{r['n_features']:>6d}")

    # ── Summary ───────────────────────────────────────────────────────

    print(f"\n{'━' * 65}")
    print("  SUMMARY — Best NMSE by category")
    print(f"{'━' * 65}")

    # Group by prefix
    categories = {}
    for r in results:
        name = r["name"]
        # Extract category (everything before _d\d)
        base = name.rsplit("_d", 1)[0] if "_d" in name else name
        depth = r.get("depth", 0)
        if base not in categories:
            categories[base] = []
        categories[base].append((depth, r["nmse_test"], r["n_features"]))

    print(f"\n  {'Category':<30s} {'d=0':>8s} {'d=1':>8s} {'d=2':>8s} "
          f"{'d=3':>8s} {'d=4':>8s} {'d=5':>8s} {'Best':>8s}")
    print(f"  {'─'*30} " + " ".join(["─" * 8] * 7))

    for cat in sorted(categories.keys()):
        entries = {d: nm for d, nm, _ in categories[cat]}
        best = min(entries.values())
        row = f"  {cat:<30s}"
        for d in range(6):
            if d in entries:
                val = entries[d]
                marker = " *" if val == best and len(entries) > 1 else ""
                row += f" {val:>7.4f}{marker}"
            else:
                row += f" {'—':>8s}"
        row += f" {best:>8.4f}"
        print(row)

    # Overall best
    best_r = min(results, key=lambda r: r["nmse_test"])
    depth_0_best = min(
        (r for r in results if r.get("depth", 0) == 0),
        key=lambda r: r["nmse_test"])

    print(f"\n  ★ Overall best: {best_r['name']} — NMSE {best_r['nmse_test']:.4f}")
    print(f"  ★ Depth=0 best: {depth_0_best['name']} — NMSE {depth_0_best['nmse_test']:.4f}")

    if best_r["nmse_test"] < depth_0_best["nmse_test"]:
        impr = (depth_0_best["nmse_test"] - best_r["nmse_test"]) / depth_0_best["nmse_test"] * 100
        print(f"  ▲ Delay embedding improves best by {impr:.1f}%")
        print(f"    → Temporal context HELPS — AD9833 upgrade justified")
    else:
        print(f"  ▬ No improvement from delay embedding")
        print(f"    → Spatial encoding already captures sufficient structure")

    # ── Save ──────────────────────────────────────────────────────────

    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "delay_embedding_analysis",
        "n_steps": args.steps,
        "seed": args.seed,
        "max_depth": args.max_depth,
        "n_readout_freqs": n_spec,
        "results": results,
        "best_overall": best_r,
        "best_depth0": depth_0_best,
    }
    out_path = OUT_DIR / f"delay_embedding_{ts_str}.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Saved: {out_path.name}")
    print("=" * 65)


if __name__ == "__main__":
    main()
