#!/usr/bin/env python3
"""
Plate Trading Robustness Validation — Five Stress Tests

1. Rolling walk-forward validation (refit on moving window)
2. Friction model (slippage, fees, spread, execution lag)
3. Trade concentration analysis (are profits from 5 lucky trades?)
4. Parameter sensitivity (lookback, poly degree, alpha, encoding)
5. Regime stability (bull, bear, chop, high-vol, low-vol)

Uses cached carrier responses from plate_trading_backtest.py.
No hardware needed.

Usage:
    python plate_trading_validate.py \
        --cache data/results/lab/plate_exps/carrier_cache_D.json \
        --symbols BTC-USD
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

from plate_trading_backtest import (
    interaction_expand,
    build_feature_matrix,
    ridge_classify,
    compute_metrics,
    download_prices,
    prepare_windows,
    POLY_DEGREE,
)

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab" / "plate_exps"


# ══════════════════════════════════════════════════════════════════
# Friction model
# ══════════════════════════════════════════════════════════════════

# BTC-USD daily: Binance taker fee 0.10%, estimated slippage 0.05%,
# spread cost ~0.02%.  Conservative total: 17 bps round-trip.
# Execution lag: we trade at NEXT open, not this close.

FRICTION_BPS = 17           # one-way cost in basis points
EXECUTION_LAG_BARS = 1      # signal at close, execute at next open


def apply_friction(predictions, actual_returns, friction_bps=FRICTION_BPS):
    """Apply one-way friction to each trade (direction change costs more)."""
    cost_per_trade = friction_bps / 10_000
    n = len(predictions)
    adj_returns = np.zeros(n)
    prev_pos = 0.0
    for i in range(n):
        pos = predictions[i]
        # Cost proportional to position change
        turnover = abs(pos - prev_pos)  # 0 (hold), 1 (partial), 2 (full flip)
        cost = turnover * cost_per_trade
        adj_returns[i] = pos * actual_returns[i] - cost
        prev_pos = pos
    return adj_returns


def apply_execution_lag(label_rets, lag=EXECUTION_LAG_BARS):
    """Shift returns to simulate execution delay.
    Signal generated at bar t → trade executed at bar t+lag.
    So predictions[i] should multiply actual_returns[i+lag], not [i].
    We truncate the last `lag` predictions and first `lag` returns.
    """
    return lag  # caller handles the shift


# ══════════════════════════════════════════════════════════════════
# Walk-forward engine
# ══════════════════════════════════════════════════════════════════

def walk_forward(X, y, label_rets, train_window, test_window,
                 alpha_grid, friction_bps=0, exec_lag=0):
    """Rolling walk-forward: train on [i:i+train], test on [i+train:i+train+test].

    Returns per-fold results and the full concatenated OOS prediction series.
    """
    N = len(y)
    folds = []
    all_preds = []
    all_rets = []
    all_indices = []

    i = 0
    fold_id = 0
    while i + train_window + test_window <= N:
        tr_s, tr_e = i, i + train_window
        te_s, te_e = tr_e, min(tr_e + test_window, N)

        Xtr, ytr = X[tr_s:tr_e], y[tr_s:tr_e]
        Xte, yte = X[te_s:te_e], y[te_s:te_e]
        ret_te = label_rets[te_s:te_e]

        if exec_lag > 0 and te_e + exec_lag <= N:
            # Shift: prediction at te_s uses return at te_s+lag
            ret_te = label_rets[te_s + exec_lag:te_e + exec_lag]
            if len(ret_te) < len(yte):
                yte = yte[:len(ret_te)]
                Xte = Xte[:len(ret_te)]

        # Grid search alpha on this fold's training data
        best_alpha = 1.0
        best_acc = 0
        for a in alpha_grid:
            p_tr, _, _ = ridge_classify(Xtr, ytr, Xte, alpha=a)
            acc = np.mean(p_tr == ytr)
            if acc > best_acc:
                best_acc = acc
                best_alpha = a

        _, pred_te, conf = ridge_classify(Xtr, ytr, Xte, alpha=best_alpha)
        te_acc = float(np.mean(pred_te == yte) * 100)

        if friction_bps > 0:
            strat_ret = apply_friction(pred_te, ret_te, friction_bps)
        else:
            strat_ret = pred_te * ret_te

        m = compute_metrics(pred_te, ret_te)  # gross metrics
        if friction_bps > 0:
            m_net = _metrics_from_strat_returns(strat_ret)
        else:
            m_net = m

        folds.append({
            "fold": fold_id,
            "train": f"{tr_s}-{tr_e}",
            "test": f"{te_s}-{te_e}",
            "n_test": len(pred_te),
            "test_acc": te_acc,
            "alpha": best_alpha,
            "sharpe_gross": m["sharpe"],
            "sharpe_net": m_net["sharpe"],
            "ret_gross_pct": m["total_ret_pct"],
            "ret_net_pct": m_net["total_ret_pct"],
            "max_dd_pct": m_net["max_dd_pct"],
            "win_rate_pct": m_net["win_rate_pct"],
        })

        all_preds.extend(pred_te.tolist())
        all_rets.extend(ret_te.tolist())
        all_indices.extend(range(te_s, te_s + len(pred_te)))

        fold_id += 1
        i += test_window  # step by test_window (non-overlapping OOS)

    return folds, np.array(all_preds), np.array(all_rets), np.array(all_indices)


def _metrics_from_strat_returns(strat_ret):
    """Compute metrics from pre-computed strategy returns (after friction)."""
    n = len(strat_ret)
    cumulative = np.cumprod(1 + strat_ret)
    total_ret = cumulative[-1] - 1
    ann_factor = 252.0 / max(n, 1)
    ann_ret = (1 + total_ret) ** ann_factor - 1
    daily_std = np.std(strat_ret)
    sharpe = (np.mean(strat_ret) / daily_std * np.sqrt(252)
              if daily_std > 1e-10 else 0.0)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (running_max - cumulative) / np.maximum(running_max, 1e-10)
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
    wins = int(np.sum(strat_ret > 0))
    win_rate = wins / n if n > 0 else 0.0
    gross_profit = float(np.sum(strat_ret[strat_ret > 0]))
    gross_loss = abs(float(np.sum(strat_ret[strat_ret < 0])))
    pf = gross_profit / gross_loss if gross_loss > 1e-12 else 999.0
    return {
        "total_ret_pct": total_ret * 100,
        "annual_ret_pct": ann_ret * 100,
        "sharpe": sharpe,
        "max_dd_pct": max_dd * 100,
        "win_rate_pct": win_rate * 100,
        "profit_factor": min(pf, 999.0),
        "n_trades": n,
    }


# ══════════════════════════════════════════════════════════════════
# Trade concentration
# ══════════════════════════════════════════════════════════════════

def analyze_concentration(predictions, actual_returns):
    """Check whether profits are concentrated in a few trades."""
    strat_ret = predictions * actual_returns
    n = len(strat_ret)
    total_pnl = float(np.sum(strat_ret))

    # Sort trades by contribution
    sorted_idx = np.argsort(strat_ret)[::-1]
    sorted_rets = strat_ret[sorted_idx]
    cum_pnl = np.cumsum(sorted_rets)

    # How many top trades account for 50%, 80%, 100% of profit
    results = {"n_trades": n, "total_pnl": total_pnl}

    if total_pnl > 0:
        for threshold in [0.5, 0.8, 1.0]:
            target = total_pnl * threshold
            n_needed = int(np.searchsorted(cum_pnl, target)) + 1
            results[f"trades_for_{int(threshold*100)}pct"] = n_needed
            results[f"concentration_{int(threshold*100)}pct"] = n_needed / n

        # Top 5 trades
        results["top5_pnl"] = float(np.sum(sorted_rets[:5]))
        results["top5_pct_of_total"] = results["top5_pnl"] / total_pnl * 100

        # Bottom 5 trades (biggest losses)
        results["bottom5_pnl"] = float(np.sum(sorted_rets[-5:]))

        # Gini coefficient of absolute trade PnLs
        abs_pnl = np.abs(strat_ret)
        abs_sorted = np.sort(abs_pnl)
        cum = np.cumsum(abs_sorted)
        gini = 1 - 2 * np.sum(cum) / (n * cum[-1]) if cum[-1] > 0 else 0
        results["gini_coefficient"] = float(gini)

        # Longest winning/losing streaks
        wins = strat_ret > 0
        max_win_streak = max_streak(wins)
        max_loss_streak = max_streak(~wins)
        results["max_win_streak"] = max_win_streak
        results["max_loss_streak"] = max_loss_streak
    else:
        results["note"] = "Net negative PnL — concentration analysis not meaningful"

    return results


def max_streak(bool_arr):
    """Length of longest True streak."""
    best = 0
    cur = 0
    for b in bool_arr:
        if b:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


# ══════════════════════════════════════════════════════════════════
# Parameter sensitivity
# ══════════════════════════════════════════════════════════════════

def param_sensitivity(close, open_, carrier_responses_full, mode_freqs,
                      alpha_grid):
    """Sweep lookback, poly degree, alpha, encoding. Report test accuracy + Sharpe."""
    n_modes = len(mode_freqs)
    results = []

    lookbacks = [3, 5, 7, 9, 11]
    poly_degrees = [2, 3, 4]
    encodings = ["binary", "return_weighted"]
    fixed_alphas = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

    # We need carrier responses for each lookback.
    # Original cache has 7 carriers. For lookback > 7, reuse with wrap.
    # For lookback < 7, use first N.

    n_cached = len(carrier_responses_full)

    for lb in lookbacks:
        # Build carrier responses for this lookback
        n_carriers = min(lb, n_modes)
        carrier_indices = np.linspace(0, n_modes - 1, n_carriers, dtype=int).tolist()
        cr = {}
        for b in range(n_carriers):
            # Map to cached carrier index
            cache_key = b % n_cached
            cr[b] = carrier_responses_full[cache_key]

        patterns, labels, win_rets, label_rets = prepare_windows(
            close, open_, lb)
        N = len(labels)
        if N < 60:
            continue

        n_train = int(N * 0.70)

        for enc in encodings:
            ret_mat = win_rets if enc == "return_weighted" else None
            for pd in poly_degrees:
                # Build features with this poly degree
                X_raw = np.zeros((N, n_carriers * n_modes))
                poly_list = []
                for i in range(N):
                    for b_idx in range(n_carriers):
                        if patterns[i, b_idx] > 0:
                            resp = cr[b_idx].copy()
                            if enc == "return_weighted" and ret_mat is not None:
                                resp = resp * abs(ret_mat[i, b_idx])
                            X_raw[i, b_idx * n_modes:(b_idx + 1) * n_modes] = resp

                    carrier_energies = np.array([
                        X_raw[i, b_idx * n_modes:(b_idx + 1) * n_modes].sum()
                        for b_idx in range(n_carriers)
                    ])
                    poly_terms = interaction_expand(carrier_energies, pd)
                    poly_list.append(np.concatenate([X_raw[i], poly_terms]))

                X_poly = np.array(poly_list)

                y_tr = labels[:n_train]
                y_te = labels[n_train:]
                ret_te = label_rets[n_train:]
                Xtr = X_poly[:n_train]
                Xte = X_poly[n_train:]

                for alpha in fixed_alphas:
                    _, pred_te, _ = ridge_classify(Xtr, y_tr, Xte, alpha=alpha)
                    te_acc = float(np.mean(pred_te == y_te) * 100)
                    m = compute_metrics(pred_te, ret_te)

                    results.append({
                        "lookback": lb,
                        "poly_deg": pd,
                        "encoding": enc,
                        "alpha": alpha,
                        "dims": X_poly.shape[1],
                        "test_acc": te_acc,
                        "sharpe": m["sharpe"],
                        "annual_ret_pct": m["annual_ret_pct"],
                        "max_dd_pct": m["max_dd_pct"],
                    })

    return results


# ══════════════════════════════════════════════════════════════════
# Regime analysis
# ══════════════════════════════════════════════════════════════════

def regime_analysis(close, predictions, label_rets, oos_indices, lookback):
    """Classify OOS periods into regimes and report per-regime performance."""
    n = len(close)

    # Compute rolling 20-day metrics for regime classification
    window = 20
    regimes = []

    for idx, pred, ret in zip(oos_indices, predictions, label_rets):
        actual_idx = idx + lookback  # map back to close array index
        if actual_idx < window or actual_idx >= n:
            regimes.append("unknown")
            continue

        segment = close[actual_idx - window:actual_idx + 1]
        period_ret = (segment[-1] - segment[0]) / segment[0]
        daily_rets = np.diff(segment) / segment[:-1]
        vol = np.std(daily_rets) * np.sqrt(252)

        # Classify
        if period_ret > 0.10:
            regime = "bull"
        elif period_ret < -0.10:
            regime = "bear"
        else:
            regime = "chop"

        # Overlay volatility
        if vol > 0.80:
            regime += "+hivol"
        elif vol < 0.30:
            regime += "+lovol"

        regimes.append(regime)

    # Aggregate by regime
    regimes = np.array(regimes)
    predictions = np.array(predictions)
    label_rets = np.array(label_rets)

    results = {}
    for reg in sorted(set(regimes)):
        if reg == "unknown":
            continue
        mask = regimes == reg
        n_trades = int(mask.sum())
        if n_trades < 5:
            continue

        preds_r = predictions[mask]
        rets_r = label_rets[mask]
        strat_ret = preds_r * rets_r
        acc = float(np.mean(preds_r == np.sign(rets_r)) * 100)
        mean_ret = float(np.mean(strat_ret) * 100)
        tot_ret = float(np.sum(strat_ret) * 100)

        results[reg] = {
            "n_trades": n_trades,
            "accuracy": acc,
            "mean_daily_ret_pct": mean_ret,
            "total_ret_pct": tot_ret,
        }

    return results


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate trading robustness validation — 5 stress tests")
    parser.add_argument("--cache", required=True,
                        help="Carrier response cache from plate_trading_backtest.py")
    parser.add_argument("--symbols", default="BTC-USD")
    parser.add_argument("--period", default="2y",
                        help="yfinance download period (default 2y for more data)")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]

    # ── Load carrier cache ──
    with open(args.cache) as f:
        cached = json.load(f)

    mode_freqs = cached["mode_freqs_hz"]
    n_modes = cached["n_modes"]
    n_carriers = len(cached["responses"])
    carrier_responses = {}
    for b in range(n_carriers):
        carrier_responses[b] = np.array(cached["responses"][str(b)])

    plate_name = cached.get("plate_name", "?")
    lookback = n_carriers  # match original

    print(f"\n{'═'*74}")
    print(f"  PLATE TRADING ROBUSTNESS VALIDATION")
    print(f"  Plate {plate_name}, {n_modes} modes, {n_carriers} carriers (from cache)")
    print(f"  Symbols: {', '.join(symbols)}, period: {args.period}")
    print(f"{'═'*74}")

    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]

    for symbol in symbols:
        print(f"\n{'━'*74}")
        print(f"  {symbol}")
        print(f"{'━'*74}")

        # ── Download ──
        print(f"\n  Downloading {symbol} ({args.period})...", end=" ", flush=True)
        try:
            df = download_prices(symbol, period=args.period)
        except Exception as e:
            print(f"FAILED ({e})")
            continue

        close = df["Close"].values.flatten().astype(np.float64)
        open_ = df["Open"].values.flatten().astype(np.float64)
        print(f"{len(close)} daily candles")

        if len(close) < lookback + 60:
            print("  Insufficient data")
            continue

        # Build features for the full series (return-weighted + poly = best model)
        patterns, labels, win_rets, label_rets = prepare_windows(
            close, open_, lookback)
        N = len(labels)

        X_plate_rw_raw, X_plate_rw_poly = build_feature_matrix(
            patterns, carrier_responses, n_modes,
            returns_matrix=win_rets, encoding="return_weighted")

        # Also build binary+poly baseline for comparison
        X_bin = patterns.astype(float)
        X_bin_poly = np.array([
            np.concatenate([p, interaction_expand(p, POLY_DEGREE)])
            for p in X_bin
        ])

        print(f"  {N} windows, {X_plate_rw_poly.shape[1]} plate features, "
              f"{X_bin_poly.shape[1]} binary features")

        # ══════════════════════════════════════════════════════════
        # TEST 1: Walk-Forward Validation
        # ══════════════════════════════════════════════════════════

        print(f"\n  ┌─────────────────────────────────────────────────────────┐")
        print(f"  │  TEST 1: ROLLING WALK-FORWARD VALIDATION                │")
        print(f"  └─────────────────────────────────────────────────────────┘")

        train_window = 120  # ~6 months
        test_window = 20    # ~1 month

        for model_name, X in [
            ("Binary+poly", X_bin_poly),
            ("Plate(rw+poly)", X_plate_rw_poly),
        ]:
            folds, preds, rets, indices = walk_forward(
                X, labels, label_rets, train_window, test_window, alpha_grid)

            if not folds:
                print(f"    {model_name}: insufficient data for walk-forward")
                continue

            accs = [f["test_acc"] for f in folds]
            sharpes = [f["sharpe_gross"] for f in folds]
            n_folds = len(folds)

            print(f"\n    {model_name} — {n_folds} folds "
                  f"(train={train_window}, test={test_window})")
            print(f"    {'Fold':>6} {'Test':>10} {'Acc':>6} {'Sharpe':>7} "
                  f"{'Ret%':>7} {'MaxDD%':>7} {'Alpha':>6}")
            print(f"    {'─'*55}")
            for f in folds:
                print(f"    {f['fold']:>6} {f['test']:>10} "
                      f"{f['test_acc']:>5.1f}% {f['sharpe_gross']:>+6.2f} "
                      f"{f['ret_gross_pct']:>+6.1f}% "
                      f"{f['max_dd_pct']:>6.1f}% {f['alpha']:>6.0g}")

            mean_acc = np.mean(accs)
            std_acc = np.std(accs)
            pos_sharpe = sum(1 for s in sharpes if s > 0)
            oos_m = compute_metrics(preds, rets) if len(preds) > 0 else {}

            print(f"    {'─'*55}")
            print(f"    Mean acc: {mean_acc:.1f}% ± {std_acc:.1f}%  "
                  f"| Pos Sharpe: {pos_sharpe}/{n_folds}")
            if oos_m:
                print(f"    Full OOS: acc={np.mean(preds == np.sign(rets))*100:.1f}% "
                      f"Sharpe={oos_m['sharpe']:+.2f} "
                      f"ret={oos_m['total_ret_pct']:+.1f}% "
                      f"maxDD={oos_m['max_dd_pct']:.1f}%")

            # Save for later tests
            if "Plate" in model_name:
                plate_folds = folds
                plate_preds = preds
                plate_rets = rets
                plate_indices = indices
            else:
                bin_folds = folds

        # ══════════════════════════════════════════════════════════
        # TEST 2: FRICTION MODEL
        # ══════════════════════════════════════════════════════════

        print(f"\n  ┌─────────────────────────────────────────────────────────┐")
        print(f"  │  TEST 2: FRICTION MODEL (slippage + fees + spread)      │")
        print(f"  └─────────────────────────────────────────────────────────┘")

        friction_levels = [0, 5, 10, 17, 25, 50]  # bps one-way

        print(f"\n    Walk-forward OOS with friction + 1-bar execution lag:")
        print(f"    {'Friction':>10} {'Sharpe':>7} {'Ret%':>8} {'MaxDD%':>7} "
              f"{'WinR%':>6} {'PF':>6}")
        print(f"    {'─'*50}")

        for fbps in friction_levels:
            # Re-run walk-forward with friction and execution lag
            folds_f, preds_f, rets_f, _ = walk_forward(
                X_plate_rw_poly, labels, label_rets,
                train_window, test_window, alpha_grid,
                friction_bps=fbps, exec_lag=1)

            if len(preds_f) == 0:
                continue

            strat_ret_f = apply_friction(preds_f, rets_f, fbps) if fbps > 0 else preds_f * rets_f
            m_f = _metrics_from_strat_returns(strat_ret_f)

            tag = " ◄ realistic" if fbps == 17 else ""
            print(f"    {fbps:>7} bps {m_f['sharpe']:>+6.2f} "
                  f"{m_f['total_ret_pct']:>+7.1f}% {m_f['max_dd_pct']:>6.1f}% "
                  f"{m_f['win_rate_pct']:>5.1f}% {m_f['profit_factor']:>5.1f}{tag}")

        # ══════════════════════════════════════════════════════════
        # TEST 3: TRADE CONCENTRATION
        # ══════════════════════════════════════════════════════════

        print(f"\n  ┌─────────────────────────────────────────────────────────┐")
        print(f"  │  TEST 3: TRADE CONCENTRATION ANALYSIS                   │")
        print(f"  └─────────────────────────────────────────────────────────┘")

        if len(plate_preds) > 0:
            conc = analyze_concentration(plate_preds, plate_rets)
            n_t = conc["n_trades"]
            print(f"\n    Total OOS trades: {n_t}")
            print(f"    Total PnL (sum of daily strategy returns): "
                  f"{conc['total_pnl']*100:+.2f}%")

            if conc.get("total_pnl", 0) > 0:
                for pct in [50, 80, 100]:
                    key_n = f"trades_for_{pct}pct"
                    key_c = f"concentration_{pct}pct"
                    if key_n in conc:
                        print(f"    Trades for {pct}% of profit: "
                              f"{conc[key_n]}/{n_t} "
                              f"({conc[key_c]*100:.1f}% of all trades)")

                print(f"\n    Top 5 trades PnL:    {conc['top5_pnl']*100:+.2f}% "
                      f"({conc['top5_pct_of_total']:.1f}% of total)")
                print(f"    Bottom 5 trades PnL: {conc['bottom5_pnl']*100:+.2f}%")
                print(f"    Gini coefficient:    {conc['gini_coefficient']:.3f} "
                      f"(0=equal, 1=concentrated)")

                if conc.get("max_win_streak"):
                    print(f"    Max win streak:      {conc['max_win_streak']}")
                    print(f"    Max loss streak:     {conc['max_loss_streak']}")

                # Verdict
                top5_pct = conc.get("top5_pct_of_total", 0)
                if top5_pct > 80:
                    print(f"\n    ⚠ CONCENTRATED: Top 5 trades = {top5_pct:.0f}% of profit. "
                          f"Result is fragile.")
                elif top5_pct > 50:
                    print(f"\n    ⚠ MODERATELY CONCENTRATED: Top 5 = {top5_pct:.0f}%. "
                          f"Check if these are regime-clustered.")
                else:
                    print(f"\n    ✓ DISTRIBUTED: Top 5 = {top5_pct:.0f}%. "
                          f"Profit spread across many trades.")
            else:
                print(f"    Net PnL ≤ 0 — {conc.get('note', 'no profitable trades')}")

            # Monthly PnL breakdown
            print(f"\n    Monthly PnL breakdown (OOS):")
            strat_rets = plate_preds * plate_rets
            # Group by ~21 trading days
            chunk_size = 21
            n_chunks = len(strat_rets) // chunk_size
            if n_chunks > 0:
                pos_months = 0
                print(f"    {'Month':>6} {'PnL%':>7} {'WinR%':>7} {'Trades':>7}")
                print(f"    {'─'*32}")
                for c in range(n_chunks):
                    s = c * chunk_size
                    e = s + chunk_size
                    chunk = strat_rets[s:e]
                    pnl = np.sum(chunk) * 100
                    wr = np.mean(chunk > 0) * 100
                    pos_months += 1 if pnl > 0 else 0
                    print(f"    {c+1:>6} {pnl:>+6.2f}% {wr:>6.1f}% {len(chunk):>7}")
                print(f"    {'─'*32}")
                print(f"    Positive months: {pos_months}/{n_chunks} "
                      f"({pos_months/n_chunks*100:.0f}%)")

        # ══════════════════════════════════════════════════════════
        # TEST 4: PARAMETER SENSITIVITY
        # ══════════════════════════════════════════════════════════

        print(f"\n  ┌─────────────────────────────────────────────────────────┐")
        print(f"  │  TEST 4: PARAMETER SENSITIVITY                          │")
        print(f"  └─────────────────────────────────────────────────────────┘")

        sens = param_sensitivity(close, open_, carrier_responses, mode_freqs,
                                 alpha_grid)

        if sens:
            # Group by lookback
            print(f"\n    By lookback (best alpha/poly per lookback, return-wt):")
            print(f"    {'LB':>4} {'PolyD':>6} {'Alpha':>7} {'Dims':>5} "
                  f"{'Acc%':>6} {'Sharpe':>7} {'Ret%':>8}")
            print(f"    {'─'*50}")

            for lb in sorted(set(r["lookback"] for r in sens)):
                rw_results = [r for r in sens if r["lookback"] == lb
                              and r["encoding"] == "return_weighted"]
                if not rw_results:
                    continue
                best = max(rw_results, key=lambda r: r["sharpe"])
                print(f"    {lb:>4} {best['poly_deg']:>6} {best['alpha']:>7.0g} "
                      f"{best['dims']:>5} {best['test_acc']:>5.1f}% "
                      f"{best['sharpe']:>+6.2f} {best['annual_ret_pct']:>+7.1f}%")

            # By encoding
            print(f"\n    By encoding (best config per encoding):")
            for enc in ["binary", "return_weighted"]:
                enc_results = [r for r in sens if r["encoding"] == enc]
                if not enc_results:
                    continue
                best = max(enc_results, key=lambda r: r["sharpe"])
                print(f"    {enc:<20} lb={best['lookback']} pd={best['poly_deg']} "
                      f"α={best['alpha']:.0g} → "
                      f"acc={best['test_acc']:.1f}% "
                      f"Sharpe={best['sharpe']:+.2f}")

            # Count how many configs are profitable
            profitable = sum(1 for r in sens if r["sharpe"] > 0)
            total = len(sens)
            above_05 = sum(1 for r in sens if r["sharpe"] > 0.5)
            print(f"\n    Configs tested: {total}")
            print(f"    Sharpe > 0: {profitable}/{total} ({profitable/total*100:.0f}%)")
            print(f"    Sharpe > 0.5: {above_05}/{total} ({above_05/total*100:.0f}%)")

            if above_05 / total > 0.20:
                print(f"    ✓ ROBUST: >20% of param combos have Sharpe > 0.5")
            elif profitable / total > 0.30:
                print(f"    ~ MODERATE: signal exists across configs but is weak")
            else:
                print(f"    ⚠ BRITTLE: only {profitable/total*100:.0f}% of configs "
                      f"are profitable")

        # ══════════════════════════════════════════════════════════
        # TEST 5: REGIME STABILITY
        # ══════════════════════════════════════════════════════════

        print(f"\n  ┌─────────────────────────────────────────────────────────┐")
        print(f"  │  TEST 5: REGIME STABILITY                               │")
        print(f"  └─────────────────────────────────────────────────────────┘")

        if len(plate_preds) > 0 and len(plate_indices) > 0:
            reg = regime_analysis(close, plate_preds, plate_rets,
                                  plate_indices, lookback)

            if reg:
                print(f"\n    {'Regime':<16} {'Trades':>7} {'Acc%':>6} "
                      f"{'MeanDailyRet':>13} {'TotalRet':>10}")
                print(f"    {'─'*55}")
                for regime, m in sorted(reg.items()):
                    print(f"    {regime:<16} {m['n_trades']:>7} "
                          f"{m['accuracy']:>5.1f}% "
                          f"{m['mean_daily_ret_pct']:>+12.3f}% "
                          f"{m['total_ret_pct']:>+9.2f}%")

                # Count regimes where model is profitable
                profitable_regimes = sum(
                    1 for m in reg.values() if m["total_ret_pct"] > 0)
                total_regimes = len(reg)
                print(f"\n    Profitable regimes: {profitable_regimes}/{total_regimes}")

                if profitable_regimes == total_regimes:
                    print(f"    ✓ ALL REGIMES PROFITABLE")
                elif profitable_regimes >= total_regimes * 0.6:
                    print(f"    ~ MOSTLY STABLE but loses in some regimes")
                else:
                    print(f"    ⚠ REGIME-DEPENDENT: only profitable in "
                          f"{profitable_regimes}/{total_regimes} regimes")
            else:
                print(f"\n    Could not classify regimes (insufficient data)")

    # ══════════════════════════════════════════════════════════════
    # Final Verdict
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'═'*74}")
    print(f"  FINAL ROBUSTNESS VERDICT")
    print(f"{'═'*74}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = LAB_DIR / f"trading_validation_{plate_name}_{timestamp}.json"

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate": plate_name,
        "symbols": symbols,
        "period": args.period,
        "tests": {
            "walk_forward": {
                "train_window": train_window,
                "test_window": test_window,
            },
            "friction_levels_bps": friction_levels,
        },
    }
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {out_file.name}")


if __name__ == "__main__":
    main()
