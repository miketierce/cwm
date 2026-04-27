#!/usr/bin/env python3
"""
NARMA-10 CMOS-Fair Re-evaluation

Re-evaluates saved Volterra/colorburst plate spectral data using ONLY
features that the integrated CMOS chip would have access to.

The CMOS chip pipeline (per the architecture spec):
  1. Shift register: holds u(t-9)..u(t) → feeds 10 DDS amplitude registers
  2. DDS cores: generate carriers at eigenmode frequencies
  3. Resonator (MEMS glass): eigenmodes mix → intermod products
  4. PZT pickup → per-rod amplifier → SAR ADC
  5. On-chip FFT engine (512-pt radix-2, 6.8 fJ/butterfly)
  6. Pattern-matching correlator: dot product of FFT bins × stored weights
  7. Output register: y_hat(t+1) → feedback to DDS amplitude

What the chip HAS (fair for bench):
  - FFT spectral bins of the plate response (magnitude, real, imag)
  - Feedback y(t) encoded as a carrier amplitude (physically present in plate)
  - Fixed-weight linear readout (Ridge regression, weights trained offline)
  - Shift register for delay-line input encoding (~160 flip-flops)

What the chip does NOT have (NOT fair for bench):
  - Raw u(t-9)..u(t) values as a parallel feature path (u_window bypass)
  - Per-step software retraining
  - Any computation beyond FFT + dot product

This script loads saved .npz data and evaluates:
  A) Plate spectral bins only (magnitude) — no u_window
  B) Plate spectral bins (mag + re + im) — no u_window
  C) Plate spectral bins + u_window (unfair reference, current best)
  D) Software-only baseline: just u_window (no plate at all)
  E) Specific IM-product bins only (what the correlator would target)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import KFold

NARMA_ORDER = 10
N_WASHOUT = 50


def nmse(y_true, y_pred):
    var = np.var(y_true)
    return float(np.mean((y_true - y_pred) ** 2) / var) if var > 0 else float('inf')


def train_ridge(X_train, y_train, alphas=None):
    if alphas is None:
        alphas = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_train)
    best_alpha, best_cv = 1.0, float('inf')
    kf = KFold(n_splits=5, shuffle=False)
    for alpha in alphas:
        scores = []
        for tr, va in kf.split(X_s):
            reg = Ridge(alpha=alpha)
            reg.fit(X_s[tr], y_train[tr])
            scores.append(nmse(y_train[va], reg.predict(X_s[va])))
        m = np.mean(scores)
        if m < best_cv:
            best_cv, best_alpha = m, alpha
    reg = Ridge(alpha=best_alpha)
    reg.fit(X_s, y_train)
    return reg, scaler, best_alpha, best_cv


def eval_config(X, y_tr, y_te, n_train, name):
    reg, sc, alpha, cv = train_ridge(X[:n_train], y_tr)
    pred_te = reg.predict(sc.transform(X[n_train:]))
    test_nmse = nmse(y_te, pred_te)
    return {
        "name": name,
        "nmse_test": round(test_nmse, 4),
        "nmse_cv": round(cv, 4),
        "features": X.shape[1],
        "alpha": alpha,
    }


def load_and_eval(npz_path, label):
    """Load a saved .npz and run the full CMOS-fair evaluation."""
    d = np.load(npz_path)
    X_mag = d['X_mag']
    X_re = d.get('X_re')
    X_im = d.get('X_im')
    u = d['u']
    y = d['y']
    readout = d.get('readout')
    start = int(d['start'])
    n_train = int(d['n_train'])
    total_usable = int(d['total_usable'])

    y_target = y[start + 1:start + total_usable + 1]
    y_tr = y_target[:n_train]
    y_te = y_target[n_train:]

    # Software delay-line window (what the shift register encodes)
    win = np.array([u[start + i - 9:start + i + 1] for i in range(total_usable)])

    # y-state (feedback value — the chip has this via the feedback carrier)
    y_state = np.column_stack([
        y[start:start + total_usable],
        [np.mean(y[start + i - 9:start + i]) for i in range(total_usable)],
    ])

    results = []

    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"  {npz_path}")
    print(f"  {total_usable} steps ({n_train} train / {total_usable - n_train} test)")
    print(f"  {X_mag.shape[1]} spectral bins")
    print(f"{'='*70}")

    # ── CMOS-FAIR evaluations (no u_window bypass) ──
    print("\n  --- CMOS-FAIR (plate spectral features only) ---")

    # A1: Magnitude bins only
    results.append(eval_config(X_mag, y_tr, y_te, n_train,
                               "CMOS_A1_mag_only"))

    # A2: Complex features (mag + re + im)
    if X_re is not None and X_im is not None:
        X_complex = np.hstack([X_mag, X_re, X_im])
        results.append(eval_config(X_complex, y_tr, y_te, n_train,
                                   "CMOS_A2_mag+re+im"))

    # A3: Top-K bins by variance (chip would focus correlator on strongest bins)
    var_per_bin = np.var(X_mag[:n_train], axis=0)
    for k in [10, 20, 50]:
        top_k_idx = np.argsort(var_per_bin)[-k:]
        results.append(eval_config(X_mag[:, top_k_idx], y_tr, y_te, n_train,
                                   f"CMOS_A3_top{k}_var_bins"))

    # ── UNFAIR references (for comparison) ──
    print("\n  --- UNFAIR REFERENCES (software bypass features) ---")

    # B1: Plate mag + u_window (current best approach — NOT CMOS-fair)
    results.append(eval_config(np.hstack([X_mag, win]), y_tr, y_te, n_train,
                               "UNFAIR_B1_mag+uwin"))

    # B2: Full plate + u_window + y_state
    results.append(eval_config(np.hstack([X_mag, win, y_state]), y_tr, y_te, n_train,
                               "UNFAIR_B2_mag+uwin+ystate"))

    # B3: Complex plate + u_window
    if X_re is not None and X_im is not None:
        results.append(eval_config(
            np.hstack([X_mag, X_re, X_im, win]), y_tr, y_te, n_train,
            "UNFAIR_B3_complex+uwin"))

    # ── SOFTWARE-ONLY baselines (no plate at all) ──
    print("\n  --- SOFTWARE-ONLY BASELINES (no plate) ---")

    # C1: Just u_window (raw delay-line values, linear regression)
    results.append(eval_config(win, y_tr, y_te, n_train,
                               "SOFTWARE_C1_uwin_only"))

    # C2: u_window + quadratic features (u_i * u_j for all pairs)
    n_in = win.shape[1]
    quad_features = []
    for i in range(n_in):
        for j in range(i, n_in):
            quad_features.append(win[:, i] * win[:, j])
    X_quad = np.column_stack([win] + quad_features)
    results.append(eval_config(X_quad, y_tr, y_te, n_train,
                               "SOFTWARE_C2_uwin+quadratic"))

    # C3: u_window + y_state (what a trivial digital system could do)
    results.append(eval_config(np.hstack([win, y_state]), y_tr, y_te, n_train,
                               "SOFTWARE_C3_uwin+ystate"))

    # C4: u_window + quadratic + y_state (full software Volterra)
    results.append(eval_config(np.hstack([X_quad, y_state]), y_tr, y_te, n_train,
                               "SOFTWARE_C4_full_sw_volterra"))

    # ── Print results ──
    print(f"\n  {'Config':<40s} {'NMSE':>8s} {'CV':>8s} {'Feat':>6s} {'α':>8s}")
    print(f"  {'-'*40} {'-'*8} {'-'*8} {'-'*6} {'-'*8}")

    for r in results:
        tag = ""
        if "CMOS" in r['name']:
            tag = " ◄ CHIP"
        elif "UNFAIR" in r['name']:
            tag = " (bypass)"
        elif "SOFTWARE" in r['name']:
            tag = " (no plate)"
        print(f"  {r['name']:<40s} {r['nmse_test']:>8.4f} {r['nmse_cv']:>8.4f} "
              f"{r['features']:>6d} {r['alpha']:>8.3f}{tag}")

    # ── Key comparisons ──
    cmos_best = min((r for r in results if 'CMOS' in r['name']),
                    key=lambda r: r['nmse_test'])
    unfair_best = min((r for r in results if 'UNFAIR' in r['name']),
                      key=lambda r: r['nmse_test'])
    sw_best = min((r for r in results if 'SOFTWARE' in r['name']),
                  key=lambda r: r['nmse_test'])

    print(f"\n  ┌─────────────────────────────────────────────────────────┐")
    print(f"  │ KEY COMPARISONS                                         │")
    print(f"  ├─────────────────────────────────────────────────────────┤")
    print(f"  │ CMOS-fair best:     {cmos_best['nmse_test']:>7.4f}  ({cmos_best['name']}) │")
    print(f"  │ Unfair best:        {unfair_best['nmse_test']:>7.4f}  ({unfair_best['name']}) │")
    print(f"  │ Software-only best: {sw_best['nmse_test']:>7.4f}  ({sw_best['name']}) │")
    print(f"  │ ESN benchmark:       0.1870                            │")
    print(f"  ├─────────────────────────────────────────────────────────┤")

    # The critical question: does the plate add value BEYOND what software can do?
    plate_advantage = sw_best['nmse_test'] - cmos_best['nmse_test']
    bypass_advantage = cmos_best['nmse_test'] - unfair_best['nmse_test']
    print(f"  │ Plate adds (vs software):  {plate_advantage:>+7.4f}                     │")
    print(f"  │ u_window bypass adds:      {bypass_advantage:>+7.4f}                     │")
    if cmos_best['nmse_test'] < sw_best['nmse_test']:
        print(f"  │ ✓ Plate computes something software alone can't        │")
    else:
        print(f"  │ ✗ Plate doesn't beat software-only — bypass is doing   │")
        print(f"  │   the real work, not the physics                       │")
    if cmos_best['nmse_test'] < 0.187:
        print(f"  │ ✓ CMOS-fair result beats ESN benchmark!                │")
    else:
        print(f"  │ ✗ CMOS-fair result does NOT beat ESN benchmark         │")
    print(f"  └─────────────────────────────────────────────────────────┘")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 CMOS-Fair Re-evaluation")
    parser.add_argument("--npz", type=str, help="Specific .npz file to evaluate")
    parser.add_argument("--all", action="store_true", help="Evaluate all saved data")
    args = parser.parse_args()

    npz_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "plate_exps" / "narma10"

    if args.npz:
        load_and_eval(Path(args.npz), "User-specified")
    elif args.all:
        # Evaluate all Volterra/colorburst data
        for npz in sorted(npz_dir.glob("hw_volterra_*.npz")):
            load_and_eval(npz, f"Volterra: {npz.stem}")
        for npz in sorted(npz_dir.glob("hw_cbv2_*.npz")):
            load_and_eval(npz, f"Colorburst v2: {npz.stem}")
    else:
        # Default: evaluate the best data (Volterra pass 2 = 12 carriers)
        best = npz_dir / "hw_volterra_pass2.npz"
        if best.exists():
            load_and_eval(best, "Volterra Pass 2 (12-carrier, y-history)")
        best1 = npz_dir / "hw_volterra_pass1.npz"
        if best1.exists():
            load_and_eval(best1, "Volterra Pass 1 (11-carrier, no y-history)")


if __name__ == "__main__":
    main()
