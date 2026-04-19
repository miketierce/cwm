#!/usr/bin/env python3
"""
Plate Options Volatility Trading — Variance Risk Premium Harvester

STRATEGY: Classify vol regime to time short-premium trades.

Key insight: implied vol overprices realized vol ~80% of the time (the
"variance risk premium"). Selling options collects this premium. The
remaining ~20% are vol blowups that wipe gains. If the plate can
classify market states into "vol-will-contract" vs "vol-will-expand"
using its spatial nonlinear mixing, we only sell premium when safe.

This is a PATTERN CLASSIFICATION task — exactly what the plate excels
at (100% Boolean, parity, CIM) — NOT a temporal prediction task
(where the plate failed at NARMA-10).

FEATURES (7 binary bits → 7 plate carriers):
  bit 0: RV5 > RV20  (short-term vol accelerating)
  bit 1: RV20 > RV_median  (elevated vol regime)
  bit 2: Return skew 10d > 0  (positive skew)
  bit 3: 5d return > 0  (recent direction)
  bit 4: |5d return| > 1 stdev  (recent magnitude large)
  bit 5: RV5/RV20 > 1.2  (vol term structure inverted)
  bit 6: |today return| > 2 stdev  (gap/shock day)

TARGET: Will next 5 realized vol < current RV20?  (vol contracts → safe to sell)

TRADE:
  Predict "vol contracts" → short straddle (collect theta, risk gamma)
  Predict "vol expands"  → flat (avoid losses)

P&L MODEL (synthetic options, no chain data needed):
  Short straddle P&L ≈ theta_earned - gamma_loss
  theta_earned = IV² × DTE / 365  (annualized daily theta)
  gamma_loss   = (realized_move / strike)² / 2
  Net P&L = short_vol_edge × notional

We approximate: daily short-premium P&L = (IV² - RV²) / 365
where IV ≈ RV20 × 1.15 (median VRP markup) and RV = actual 1d move.

Usage:
    # Dry-run (simulated plate):
    python plate_options_vol.py --dry-run \
        --census data/results/lab/plate_exps/plate_census_20260412_180543.json

    # Hardware on plate D:
    python plate_options_vol.py /dev/cu.usbserial-11310 \
        --census data/results/lab/plate_exps/plate_census_20260412_180543.json

    # Reuse carrier cache:
    python plate_options_vol.py --dry-run \
        --census data/results/lab/plate_exps/plate_census_20260412_180543.json \
        --cache data/results/lab/plate_exps/carrier_cache_D.json
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
import warnings
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

from plate_benchmark_kronos import (
    PLATE_NAMES, PLATE_RELAYS,
    load_census, get_plate_modes,
)
from plate_trading_backtest import (
    interaction_expand,
    ridge_classify,
    compute_metrics,
    download_prices,
    POLY_DEGREE,
)
from plate_trading_validate import (
    apply_friction,
    _metrics_from_strat_returns,
    FRICTION_BPS,
)

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab" / "plate_exps"
LAB_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ─────────────────────────────────────────────────
N_AVG = 8
SETTLE_S = 0.15
VOL_LOOKBACK_SHORT = 5      # short realized vol window
VOL_LOOKBACK_LONG = 20      # long realized vol window
VOL_FORWARD = 5             # forward vol measurement window
VRP_MARKUP = 1.15           # IV ≈ RV20 × 1.15 (variance risk premium)
DTE = 5                     # synthetic option DTE in days
HOLD_DAYS = [1, 3, 5]       # hold period sweep
TRAIN_WINDOW = 120
TEST_WINDOW = 20
FRICTION_OPTIONS_BPS = 30   # options wider spreads than spot
DEFAULT_SYMBOLS = ["BTC-USD", "SPY", "QQQ"]


# ══════════════════════════════════════════════════════════════════
# PicoScope capture (reused from plate_trading_backtest)
# ══════════════════════════════════════════════════════════════════

def open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed ({handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    return handle


def close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)


def capture_carrier_response(handle, drive_freq, readout_freqs):
    """Drive AWG at one frequency, return FFT magnitudes at readout freqs."""
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
    from picosdk.ps2000 import ps2000

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(drive_freq), float(drive_freq), 0.0, 0.0, 0, 0)
    time.sleep(SETTLE_S)

    spectra = []
    for _ in range(N_AVG):
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
        t_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(
            handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.002)
            if time.time() - t0 > 2:
                break
        buf_a = (ctypes.c_int16 * N_SAMPLES)()
        buf_b = (ctypes.c_int16 * N_SAMPLES)()
        overflow = ctypes.c_int16()
        n = ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES)
        if n > 0:
            raw = np.array(buf_a[:n], dtype=np.float64)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            mags = np.zeros(len(readout_freqs))
            for j, rf in enumerate(readout_freqs):
                tb = int(round(rf / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(fft_mag) - 1, tb + 3)
                mags[j] = float(np.max(fft_mag[lo:hi + 1]))
            spectra.append(mags)

    return np.mean(spectra, axis=0) if spectra else np.zeros(len(readout_freqs))


# ══════════════════════════════════════════════════════════════════
# Volatility feature engineering
# ══════════════════════════════════════════════════════════════════

def compute_realized_vol(returns, window):
    """Rolling annualized realized volatility."""
    rv = np.full(len(returns), np.nan)
    for i in range(window, len(returns)):
        rv[i] = np.std(returns[i - window:i]) * np.sqrt(252)
    return rv


def compute_return_skew(returns, window=10):
    """Rolling return skewness."""
    skew = np.full(len(returns), np.nan)
    for i in range(window, len(returns)):
        chunk = returns[i - window:i]
        mu = np.mean(chunk)
        std = np.std(chunk)
        if std > 1e-12:
            skew[i] = np.mean(((chunk - mu) / std) ** 3)
        else:
            skew[i] = 0.0
    return skew


def compute_forward_vol(returns, window):
    """Forward-looking realized vol (for label construction)."""
    fv = np.full(len(returns), np.nan)
    for i in range(len(returns) - window):
        fv[i] = np.std(returns[i:i + window]) * np.sqrt(252)
    return fv


def build_vol_features(close):
    """Build volatility regime features from close prices.

    Returns:
        patterns: (N, 7) binary feature matrix
        labels:   (N,) +1 = vol contracts (safe to sell), -1 = vol expands
        daily_returns: (N,) for P&L computation
        rv20:     (N,) 20d realized vol for IV proxy
        valid_mask: (N,) bool, True where all features computable
    """
    # Daily log returns
    log_ret = np.diff(np.log(close))
    N = len(log_ret)

    # Realized vol windows
    rv5 = compute_realized_vol(log_ret, VOL_LOOKBACK_SHORT)
    rv20 = compute_realized_vol(log_ret, VOL_LOOKBACK_LONG)

    # Forward vol for labels
    fwd_vol = compute_forward_vol(log_ret, VOL_FORWARD)

    # Return skewness
    skew10 = compute_return_skew(log_ret, 10)

    # 5-day cumulative return
    cum5 = np.full(N, np.nan)
    for i in range(5, N):
        cum5[i] = np.sum(log_ret[i - 5:i])

    # Historical vol median (expanding window, min 60 days)
    rv_median = np.full(N, np.nan)
    for i in range(60, N):
        rv_median[i] = np.median(rv20[VOL_LOOKBACK_LONG:i + 1][
            ~np.isnan(rv20[VOL_LOOKBACK_LONG:i + 1])])

    # Overall stdev of returns (expanding window, min 60 days)
    ret_std = np.full(N, np.nan)
    for i in range(60, N):
        ret_std[i] = np.std(log_ret[:i + 1])

    # ── Build 7-bit binary pattern ──
    patterns = np.zeros((N, 7), dtype=int)
    valid_mask = np.zeros(N, dtype=bool)

    for i in range(N):
        if any(np.isnan([rv5[i], rv20[i], skew10[i], cum5[i],
                         rv_median[i], ret_std[i]])):
            continue
        if np.isnan(fwd_vol[i]):
            continue

        valid_mask[i] = True

        # Bit 0: RV5 > RV20 (short-term vol accelerating)
        patterns[i, 0] = int(rv5[i] > rv20[i])

        # Bit 1: RV20 > historical median (elevated regime)
        patterns[i, 1] = int(rv20[i] > rv_median[i])

        # Bit 2: 10d return skew > 0
        patterns[i, 2] = int(skew10[i] > 0)

        # Bit 3: 5d return > 0
        patterns[i, 3] = int(cum5[i] > 0)

        # Bit 4: |5d return| > 1 stdev of returns
        patterns[i, 4] = int(abs(cum5[i]) > ret_std[i] * np.sqrt(5))

        # Bit 5: RV5/RV20 > 1.2 (vol term structure inverted)
        ratio = rv5[i] / max(rv20[i], 1e-10)
        patterns[i, 5] = int(ratio > 1.2)

        # Bit 6: |today's return| > 2 stdev (gap/shock)
        patterns[i, 6] = int(abs(log_ret[i]) > 2 * ret_std[i])

    # Labels: forward vol < current RV20 → +1 (vol contracts, safe to sell)
    labels = np.zeros(N)
    for i in range(N):
        if valid_mask[i]:
            labels[i] = 1.0 if fwd_vol[i] < rv20[i] else -1.0

    return patterns, labels, log_ret, rv20, valid_mask


def compute_options_pnl(positions, daily_returns, rv20, friction_bps):
    """Compute synthetic delta-hedged short-straddle P&L.

    Model: variance swap approximation.
    Daily P&L = position × (IV²/252 - r²)
    where IV ≈ RV20 × VRP_MARKUP, r = daily log return.

    position > 0: short vol (collect theta, pay gamma)
    position = 0: flat
    position < 0: long vol (pay theta, collect gamma)
    """
    cost_per_trade = friction_bps / 10_000
    N = len(positions)
    pnl = np.zeros(N)
    prev_pos = 0.0

    for i in range(N):
        pos = positions[i]
        if abs(pos) > 1e-10:
            iv = rv20[i] * VRP_MARKUP if not np.isnan(rv20[i]) else 0.3
            iv_daily_var = (iv ** 2) / 252.0
            realized_var = daily_returns[i] ** 2
            pnl[i] = pos * (iv_daily_var - realized_var)

        turnover = abs(pos - prev_pos)
        pnl[i] -= turnover * cost_per_trade
        prev_pos = pos

    return pnl


def compute_options_metrics(pnl):
    """Compute metrics from options P&L stream."""
    cumulative = np.cumprod(1 + pnl)
    total_ret = cumulative[-1] - 1
    n = len(pnl)
    ann_factor = 252.0 / max(n, 1)
    ann_ret = (1 + total_ret) ** ann_factor - 1

    daily_std = np.std(pnl)
    sharpe = (np.mean(pnl) / daily_std * np.sqrt(252)
              if daily_std > 1e-10 else 0.0)

    running_max = np.maximum.accumulate(cumulative)
    drawdown = (running_max - cumulative) / np.maximum(running_max, 1e-10)
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

    wins = int(np.sum(pnl > 0))
    win_rate = wins / n if n > 0 else 0.0

    gross_profit = float(np.sum(pnl[pnl > 0]))
    gross_loss = abs(float(np.sum(pnl[pnl < 0])))
    pf = gross_profit / gross_loss if gross_loss > 1e-12 else 999.0

    exposure = np.mean(pnl != 0) * 100

    return {
        "total_ret_pct": total_ret * 100,
        "annual_ret_pct": ann_ret * 100,
        "sharpe": sharpe,
        "max_dd_pct": max_dd * 100,
        "win_rate_pct": win_rate * 100,
        "profit_factor": min(pf, 999.0),
        "n_days": n,
        "exposure_pct": exposure,
    }


# ══════════════════════════════════════════════════════════════════
# Plate feature builders
# ══════════════════════════════════════════════════════════════════

def build_plate_vol_features(patterns, carrier_responses, n_modes,
                             rv20=None, poly_degree=4):
    """Build plate spectral features from vol-regime binary patterns.

    Same as binary trading: pattern selects which carriers are active,
    cross-coupling spectrum = nonlinear feature mixing. Optionally
    weight by current vol level (rv20) for vol-proportional encoding.
    """
    N, n_bits = patterns.shape
    n_carriers = min(n_bits, len(carrier_responses))

    X_list = []
    for i in range(N):
        raw = np.zeros(n_carriers * n_modes)
        for b in range(n_carriers):
            if patterns[i, b] > 0:
                resp = carrier_responses[b].copy()
                if rv20 is not None and not np.isnan(rv20[i]):
                    resp = resp * rv20[i]  # vol-proportional weighting
                raw[b * n_modes:(b + 1) * n_modes] = resp

        carrier_energies = np.array([
            raw[b * n_modes:(b + 1) * n_modes].sum()
            for b in range(n_carriers)
        ])
        poly_terms = interaction_expand(carrier_energies, poly_degree)
        X_list.append(np.concatenate([raw, poly_terms]))

    return np.array(X_list)


# ══════════════════════════════════════════════════════════════════
# Walk-forward (options variant)
# ══════════════════════════════════════════════════════════════════

def walk_forward_options(X, labels, daily_returns, rv20,
                         train_window=TRAIN_WINDOW,
                         test_window=TEST_WINDOW,
                         friction_bps=FRICTION_OPTIONS_BPS,
                         hold_days=1):
    """Walk-forward backtest for vol classification → options P&L."""
    N = len(labels)
    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]
    all_preds = np.zeros(N)

    i = 0
    while i + train_window + test_window <= N:
        tr_s, tr_e = i, i + train_window
        te_s, te_e = tr_e, min(tr_e + test_window, N)

        Xtr, ytr = X[tr_s:tr_e], labels[tr_s:tr_e]
        Xte = X[te_s:te_e]

        # Alpha CV on training accuracy
        best_alpha = 1.0
        best_acc = 0
        for a in alpha_grid:
            p_tr, _, _ = ridge_classify(Xtr, ytr, Xte, alpha=a)
            acc = np.mean(p_tr == ytr)
            if acc > best_acc:
                best_acc = acc
                best_alpha = a

        _, pred_te, _ = ridge_classify(Xtr, ytr, Xte, alpha=best_alpha)

        for j in range(len(pred_te)):
            idx = te_s + j
            if idx < N:
                all_preds[idx] = pred_te[j]

        i += test_window

    # Apply hold period
    if hold_days > 1:
        held = np.zeros(N)
        cur_pos = 0.0
        hold_ctr = 0
        for idx in range(N):
            if hold_ctr > 0:
                held[idx] = cur_pos
                hold_ctr -= 1
            elif all_preds[idx] != 0:
                cur_pos = all_preds[idx]
                held[idx] = cur_pos
                hold_ctr = hold_days - 1
        all_preds = held

    # Map predictions: +1 → sell premium, -1 → flat
    # We only trade when classifier says "vol contracts" (+1)
    positions = np.where(all_preds > 0, 1.0, 0.0)

    pnl = compute_options_pnl(positions, daily_returns, rv20, friction_bps)
    return pnl, positions, all_preds


def walk_forward_sizing(X, labels, daily_returns, rv20,
                        train_window=TRAIN_WINDOW,
                        test_window=TEST_WINDOW,
                        friction_bps=FRICTION_OPTIONS_BPS,
                        hold_days=1):
    """Walk-forward: always short vol, but SIZE position using confidence.

    Instead of binary gate (sell/don't sell), use the ridge regression
    confidence score to scale position: high confidence vol-contracts → 1.5×,
    high confidence vol-expands → 0.5×. Always short vol (VRP edge).
    """
    N = len(labels)
    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]
    all_confidence = np.zeros(N)

    i = 0
    while i + train_window + test_window <= N:
        tr_s, tr_e = i, i + train_window
        te_s, te_e = tr_e, min(tr_e + test_window, N)

        Xtr, ytr = X[tr_s:tr_e], labels[tr_s:tr_e]
        Xte = X[te_s:te_e]

        best_alpha = 1.0
        best_acc = 0
        for a in alpha_grid:
            p_tr, _, _ = ridge_classify(Xtr, ytr, Xte, alpha=a)
            acc = np.mean(p_tr == ytr)
            if acc > best_acc:
                best_acc = acc
                best_alpha = a

        _, _, conf = ridge_classify(Xtr, ytr, Xte, alpha=best_alpha)

        for j in range(len(conf)):
            idx = te_s + j
            if idx < N:
                all_confidence[idx] = conf[j]

        i += test_window

    # Map confidence → position size
    # confidence > 0 → vol contracts predicted → larger short
    # confidence < 0 → vol expands predicted → smaller short
    # Clip to [0.25, 1.75] to stay always short but modulate
    positions = np.clip(0.5 + all_confidence * 0.5, 0.25, 1.75)

    if hold_days > 1:
        held = np.zeros(N)
        cur_pos = 1.0
        hold_ctr = 0
        for idx in range(N):
            if hold_ctr > 0:
                held[idx] = cur_pos
                hold_ctr -= 1
            else:
                cur_pos = positions[idx]
                held[idx] = cur_pos
                hold_ctr = hold_days - 1
        positions = held

    pnl = compute_options_pnl(positions, daily_returns, rv20, friction_bps)
    return pnl, positions


def walk_forward_long_short_vol(X, labels, daily_returns, rv20,
                                train_window=TRAIN_WINDOW,
                                test_window=TEST_WINDOW,
                                friction_bps=FRICTION_OPTIONS_BPS,
                                hold_days=1):
    """Walk-forward: LONG vol when expansion predicted, SHORT when contraction.

    This is the aggressive version: uses ±1 positions in vol space.
    +1 = short straddle (collect premium)
    -1 = long straddle (pay premium, profit from large moves)
    """
    N = len(labels)
    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]
    all_preds = np.zeros(N)

    i = 0
    while i + train_window + test_window <= N:
        tr_s, tr_e = i, i + train_window
        te_s, te_e = tr_e, min(tr_e + test_window, N)

        Xtr, ytr = X[tr_s:tr_e], labels[tr_s:tr_e]
        Xte = X[te_s:te_e]

        best_alpha = 1.0
        best_acc = 0
        for a in alpha_grid:
            p_tr, _, _ = ridge_classify(Xtr, ytr, Xte, alpha=a)
            acc = np.mean(p_tr == ytr)
            if acc > best_acc:
                best_acc = acc
                best_alpha = a

        _, pred_te, _ = ridge_classify(Xtr, ytr, Xte, alpha=best_alpha)

        for j in range(len(pred_te)):
            idx = te_s + j
            if idx < N:
                all_preds[idx] = pred_te[j]

        i += test_window

    if hold_days > 1:
        held = np.zeros(N)
        cur_pos = 0.0
        hold_ctr = 0
        for idx in range(N):
            if hold_ctr > 0:
                held[idx] = cur_pos
                hold_ctr -= 1
            elif all_preds[idx] != 0:
                cur_pos = all_preds[idx]
                held[idx] = cur_pos
                hold_ctr = hold_days - 1
        all_preds = held

    # +1 stays +1 (short vol), -1 stays -1 (long vol)
    pnl = compute_options_pnl(all_preds, daily_returns, rv20, friction_bps)
    return pnl, all_preds


# ══════════════════════════════════════════════════════════════════
# Always-sell baseline
# ══════════════════════════════════════════════════════════════════

def always_sell_baseline(daily_returns, rv20, friction_bps):
    """Baseline: sell premium every day (no classifier)."""
    positions = np.ones(len(daily_returns))
    pnl = compute_options_pnl(positions, daily_returns, rv20, friction_bps)
    return pnl, positions


# ══════════════════════════════════════════════════════════════════
# Main backtest
# ══════════════════════════════════════════════════════════════════

def backtest_symbol(symbol, carrier_responses, n_modes, period="2y"):
    """Full options vol-trading backtest for one symbol."""
    print(f"\n  Downloading {symbol} ...", end=" ", flush=True)
    try:
        df = download_prices(symbol, period=period)
    except Exception as e:
        print(f"FAILED ({e})")
        return None

    close = df["Close"].values.flatten().astype(np.float64)
    print(f"{len(close)} daily candles")

    if len(close) < 120:
        print(f"    Insufficient data (need ≥120)")
        return None

    # ── Build vol features ──
    patterns, labels, log_ret, rv20, valid = build_vol_features(close)
    n_valid = int(np.sum(valid))
    print(f"    Valid windows: {n_valid}/{len(log_ret)}")

    # Filter to valid rows
    idx = np.where(valid)[0]
    if len(idx) < TRAIN_WINDOW + TEST_WINDOW + 20:
        print(f"    Not enough valid windows for walk-forward")
        return None

    pat_v = patterns[idx]
    lab_v = labels[idx]
    ret_v = log_ret[idx]
    rv20_v = rv20[idx]

    up_pct = 100 * np.mean(lab_v == 1)
    unique_pats = len(set(tuple(p) for p in pat_v))
    print(f"    Vol contracts: {up_pct:.1f}% | Expands: {100-up_pct:.1f}%")
    print(f"    Unique patterns: {unique_pats}/128")
    print(f"    RV20 mean: {np.nanmean(rv20_v)*100:.1f}%  "
          f"median: {np.nanmedian(rv20_v)*100:.1f}%")

    # ── Build feature matrices ──
    # 1. Binary baseline (raw bits, no plate)
    X_bin = pat_v.astype(float)
    X_bin_poly = np.array([
        np.concatenate([p, interaction_expand(p, POLY_DEGREE)])
        for p in X_bin
    ])

    # 2. Plate: binary encoding
    X_plate = build_plate_vol_features(
        pat_v, carrier_responses, n_modes)

    # 3. Plate: vol-weighted encoding
    X_plate_vw = build_plate_vol_features(
        pat_v, carrier_responses, n_modes, rv20=rv20_v)

    # ── Run strategies ──
    strategies = {}

    print(f"\n  {'Strategy':<32} {'Hold':>4} {'Sharpe':>7} {'Return':>8} "
          f"{'MaxDD':>7} {'WinR':>6} {'Exp':>5}")
    print(f"  {'─'*76}")

    # Always-sell baseline (the variance risk premium itself)
    for hd in HOLD_DAYS:
        pnl_base, pos_base = always_sell_baseline(
            ret_v, rv20_v, FRICTION_OPTIONS_BPS)
        m = compute_options_metrics(pnl_base)
        m["hold_days"] = hd
        label = f"Always sell (VRP baseline)"
        strategies[f"always_sell_{hd}d"] = m
        print(f"  {label:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%")

    # Binary classifier (no plate)
    for hd in HOLD_DAYS:
        pnl, pos, raw_preds = walk_forward_options(
            X_bin_poly, lab_v, ret_v, rv20_v,
            hold_days=hd, friction_bps=FRICTION_OPTIONS_BPS)
        m = compute_options_metrics(pnl)
        m["hold_days"] = hd
        label = f"Binary classifier"
        key = f"binary_{hd}d"
        strategies[key] = m
        print(f"  {label:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%")

    # Binary sizing (no plate — fair control for plate sizing)
    for hd in HOLD_DAYS:
        pnl, pos = walk_forward_sizing(
            X_bin_poly, lab_v, ret_v, rv20_v,
            hold_days=hd, friction_bps=FRICTION_OPTIONS_BPS)
        m = compute_options_metrics(pnl)
        m["hold_days"] = hd
        label = f"Binary sizing"
        key = f"binary_sizing_{hd}d"
        strategies[key] = m
        tag = " ◄" if m["sharpe"] > 0.5 and m["max_dd_pct"] < 15 else ""
        print(f"  {label:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%{tag}")

    # Plate binary
    for hd in HOLD_DAYS:
        pnl, pos, raw_preds = walk_forward_options(
            X_plate, lab_v, ret_v, rv20_v,
            hold_days=hd, friction_bps=FRICTION_OPTIONS_BPS)
        m = compute_options_metrics(pnl)
        m["hold_days"] = hd
        label = f"Plate binary"
        key = f"plate_binary_{hd}d"
        strategies[key] = m
        tag = " ◄" if m["sharpe"] > 0.5 and m["max_dd_pct"] < 15 else ""
        print(f"  {label:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%{tag}")

    # Plate vol-weighted
    for hd in HOLD_DAYS:
        pnl, pos, raw_preds = walk_forward_options(
            X_plate_vw, lab_v, ret_v, rv20_v,
            hold_days=hd, friction_bps=FRICTION_OPTIONS_BPS)
        m = compute_options_metrics(pnl)
        m["hold_days"] = hd
        label = f"Plate vol-weighted"
        key = f"plate_vw_{hd}d"
        strategies[key] = m
        tag = " ◄" if m["sharpe"] > 0.5 and m["max_dd_pct"] < 15 else ""
        print(f"  {label:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%{tag}")

    # Plate position sizing (always short, modulate size)
    for hd in HOLD_DAYS:
        pnl, pos = walk_forward_sizing(
            X_plate, lab_v, ret_v, rv20_v,
            hold_days=hd, friction_bps=FRICTION_OPTIONS_BPS)
        m = compute_options_metrics(pnl)
        m["hold_days"] = hd
        label = f"Plate sizing"
        key = f"plate_sizing_{hd}d"
        strategies[key] = m
        tag = " ◄" if m["sharpe"] > 0.5 and m["max_dd_pct"] < 15 else ""
        print(f"  {label:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%{tag}")

    # Plate long/short vol (±1 positions in vol space)
    for hd in HOLD_DAYS:
        pnl, pos = walk_forward_long_short_vol(
            X_plate, lab_v, ret_v, rv20_v,
            hold_days=hd, friction_bps=FRICTION_OPTIONS_BPS)
        m = compute_options_metrics(pnl)
        m["hold_days"] = hd
        label = f"Plate long/short vol"
        key = f"plate_ls_vol_{hd}d"
        strategies[key] = m
        tag = " ◄" if m["sharpe"] > 0.5 and m["max_dd_pct"] < 15 else ""
        print(f"  {label:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%{tag}")

    # Plate vol-weighted long/short vol
    for hd in HOLD_DAYS:
        pnl, pos = walk_forward_long_short_vol(
            X_plate_vw, lab_v, ret_v, rv20_v,
            hold_days=hd, friction_bps=FRICTION_OPTIONS_BPS)
        m = compute_options_metrics(pnl)
        m["hold_days"] = hd
        label = f"Plate vw long/short vol"
        key = f"plate_vw_ls_vol_{hd}d"
        strategies[key] = m
        tag = " ◄" if m["sharpe"] > 0.5 and m["max_dd_pct"] < 15 else ""
        print(f"  {label:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%{tag}")

    # ── Direction strategy (reuse plate for direction too) ──
    # Same features but target = next-day return direction
    dir_labels = np.sign(ret_v)
    dir_labels[dir_labels == 0] = 1.0

    for approach_name, X_feat in [("Plate direction", X_plate),
                                   ("Plate dir+vol-wt", X_plate_vw)]:
        for hd in HOLD_DAYS:
            pnl_dir, pos_dir, _ = walk_forward_direction(
                X_feat, dir_labels, ret_v,
                hold_days=hd, friction_bps=FRICTION_BPS)
            m = compute_options_metrics(pnl_dir)
            m["hold_days"] = hd
            key = f"{approach_name.lower().replace(' ', '_')}_{hd}d"
            strategies[key] = m
            print(f"  {approach_name:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
                  f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
                  f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%")

    # ── Hybrid: plate vol filter + direction ──
    # Only trade direction when plate predicts vol will contract (calm market)
    for hd in HOLD_DAYS:
        pnl_hyb, pos_hyb = walk_forward_hybrid(
            X_plate, X_plate_vw, lab_v, dir_labels, ret_v, rv20_v,
            hold_days=hd)
        m = compute_options_metrics(pnl_hyb)
        m["hold_days"] = hd
        label = "Hybrid (vol filter + dir)"
        key = f"hybrid_{hd}d"
        strategies[key] = m
        tag = " ◄" if m["sharpe"] > 0.5 and m["max_dd_pct"] < 15 else ""
        print(f"  {label:<32} {hd:>3}d {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {m['exposure_pct']:>4.0f}%{tag}")

    # ── Summary ──
    best_key = max(strategies, key=lambda k: strategies[k]["sharpe"])
    best = strategies[best_key]
    print(f"\n  ▸ Best: {best_key}  Sharpe={best['sharpe']:+.2f}  "
          f"DD={best['max_dd_pct']:.1f}%  Return={best['total_ret_pct']:+.1f}%")

    sn8_pass = best["sharpe"] > 0.5 and best["max_dd_pct"] < 15
    print(f"  ▸ SN8 criteria: {'PASS ✓' if sn8_pass else 'FAIL ✗'}  "
          f"(Sharpe>{0.5}, DD<{15}%)")

    return strategies


def walk_forward_direction(X, labels, returns,
                           train_window=TRAIN_WINDOW,
                           test_window=TEST_WINDOW,
                           friction_bps=FRICTION_BPS,
                           hold_days=1):
    """Walk-forward for direction prediction (reused from needle_mover)."""
    N = len(labels)
    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]
    all_preds = np.zeros(N)

    i = 0
    while i + train_window + test_window <= N:
        tr_s, tr_e = i, i + train_window
        te_s, te_e = tr_e, min(tr_e + test_window, N)

        Xtr, ytr = X[tr_s:tr_e], labels[tr_s:tr_e]
        Xte = X[te_s:te_e]

        best_alpha = 1.0
        best_acc = 0
        for a in alpha_grid:
            p_tr, _, _ = ridge_classify(Xtr, ytr, Xte, alpha=a)
            acc = np.mean(p_tr == ytr)
            if acc > best_acc:
                best_acc = acc
                best_alpha = a

        _, pred_te, _ = ridge_classify(Xtr, ytr, Xte, alpha=best_alpha)

        for j in range(len(pred_te)):
            idx = te_s + j
            if idx < N:
                all_preds[idx] = pred_te[j]

        i += test_window

    if hold_days > 1:
        held = np.zeros(N)
        cur_pos = 0.0
        hold_ctr = 0
        for idx in range(N):
            if hold_ctr > 0:
                held[idx] = cur_pos
                hold_ctr -= 1
            elif all_preds[idx] != 0:
                cur_pos = all_preds[idx]
                held[idx] = cur_pos
                hold_ctr = hold_days - 1
        all_preds = held

    strat_ret = apply_friction(all_preds, returns, friction_bps)
    return strat_ret, all_preds, all_preds


def walk_forward_hybrid(X_vol, X_dir, vol_labels, dir_labels,
                        returns, rv20,
                        train_window=TRAIN_WINDOW,
                        test_window=TEST_WINDOW,
                        hold_days=1):
    """Hybrid: use vol classifier as a gate, direction classifier for signal.

    - Step 1: Vol classifier predicts "safe to trade" (+1) vs "stay flat" (-1)
    - Step 2: Direction classifier predicts LONG (+1) vs SHORT (-1)
    - Final position: direction × (vol_safe indicator)
    - When vol is predicted to expand, we go flat regardless of direction.
    """
    N = len(vol_labels)
    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]
    vol_preds = np.zeros(N)
    dir_preds = np.zeros(N)

    i = 0
    while i + train_window + test_window <= N:
        tr_s, tr_e = i, i + train_window
        te_s, te_e = tr_e, min(tr_e + test_window, N)

        # Vol classifier
        Xtr_v, ytr_v = X_vol[tr_s:tr_e], vol_labels[tr_s:tr_e]
        Xte_v = X_vol[te_s:te_e]

        best_alpha_v = 1.0
        best_acc_v = 0
        for a in alpha_grid:
            p_tr, _, _ = ridge_classify(Xtr_v, ytr_v, Xte_v, alpha=a)
            acc = np.mean(p_tr == ytr_v)
            if acc > best_acc_v:
                best_acc_v = acc
                best_alpha_v = a
        _, pred_v, _ = ridge_classify(Xtr_v, ytr_v, Xte_v, alpha=best_alpha_v)

        # Direction classifier
        Xtr_d, ytr_d = X_dir[tr_s:tr_e], dir_labels[tr_s:tr_e]
        Xte_d = X_dir[te_s:te_e]

        best_alpha_d = 1.0
        best_acc_d = 0
        for a in alpha_grid:
            p_tr, _, _ = ridge_classify(Xtr_d, ytr_d, Xte_d, alpha=a)
            acc = np.mean(p_tr == ytr_d)
            if acc > best_acc_d:
                best_acc_d = acc
                best_alpha_d = a
        _, pred_d, _ = ridge_classify(Xtr_d, ytr_d, Xte_d, alpha=best_alpha_d)

        for j in range(len(pred_v)):
            idx = te_s + j
            if idx < N:
                vol_preds[idx] = pred_v[j]
                dir_preds[idx] = pred_d[j]

        i += test_window

    # Combine: direction × vol_safe
    positions = np.where(vol_preds > 0, dir_preds, 0.0)

    if hold_days > 1:
        held = np.zeros(N)
        cur_pos = 0.0
        hold_ctr = 0
        for idx in range(N):
            if hold_ctr > 0:
                held[idx] = cur_pos
                hold_ctr -= 1
            elif positions[idx] != 0:
                cur_pos = positions[idx]
                held[idx] = cur_pos
                hold_ctr = hold_days - 1
        positions = held

    strat_ret = apply_friction(positions, returns, FRICTION_BPS)
    return strat_ret, positions


# ══════════════════════════════════════════════════════════════════
# Hardware capture + carrier cache
# ══════════════════════════════════════════════════════════════════

def capture_plate_carriers(handle, mux, mode_freqs, plate_id):
    """Capture 7-carrier cross-coupling matrix for one plate."""
    n_modes = len(mode_freqs)
    n_carriers = min(7, n_modes)
    carrier_indices = np.linspace(0, n_modes - 1, n_carriers, dtype=int).tolist()

    mux.select(int(plate_id))
    time.sleep(0.15)

    carriers = {}
    for b in range(n_carriers):
        ci = carrier_indices[b]
        drive_freq = mode_freqs[ci]
        resp = capture_carrier_response(handle, drive_freq, mode_freqs)
        carriers[b] = resp

    # AWG off
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)

    return carriers, carrier_indices


def load_carrier_cache(cache_path):
    """Load carrier response cache from JSON."""
    with open(cache_path) as f:
        data = json.load(f)
    carriers = {}
    for b in range(len(data["responses"])):
        carriers[b] = np.array(data["responses"][str(b)])
    return carriers, data.get("mode_freqs_hz", []), data.get("n_modes", 8)


def save_carrier_cache(path, carriers, mode_freqs, carrier_indices, plate_id):
    """Save carrier response cache."""
    data = {
        "plate": plate_id,
        "plate_name": PLATE_NAMES.get(plate_id, plate_id),
        "mode_freqs_hz": [float(f) for f in mode_freqs],
        "carrier_indices": carrier_indices,
        "n_modes": len(mode_freqs),
        "responses": {str(b): carriers[b].tolist() for b in carriers},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "hardware",
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ══════════════════════════════════════════════════════════════════
# Simulated plate (for dry-run)
# ══════════════════════════════════════════════════════════════════

def simulate_carrier_responses(mode_freqs, n_carriers=7, rng=None):
    """Generate realistic cross-coupling matrix via Lorentzian transfer."""
    if rng is None:
        rng = np.random.default_rng(42)

    n_modes = len(mode_freqs)
    carrier_indices = np.linspace(0, n_modes - 1, n_carriers, dtype=int).tolist()
    carriers = {}

    for b in range(n_carriers):
        drive_freq = mode_freqs[carrier_indices[b]]
        resp = np.zeros(n_modes)
        for m in range(n_modes):
            f0 = mode_freqs[m]
            Q = 300 + rng.uniform(-50, 50)
            gamma = f0 / (2 * Q)
            L = 1.0 / ((drive_freq - f0) ** 2 + gamma ** 2)
            resp[m] = L * gamma ** 2 * 1e10  # scale to realistic range
        carriers[b] = resp

    return carriers, carrier_indices


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate options vol-trading — variance risk premium harvester")
    parser.add_argument("port", nargs="?", default=None,
                        help="Arduino serial port (omit for --dry-run)")
    parser.add_argument("--census", required=True)
    parser.add_argument("--plate", default="4")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate plate response (no hardware)")
    parser.add_argument("--cache", default=None,
                        help="Path to carrier response cache JSON")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--period", default="2y")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    plate_id = args.plate
    name = PLATE_NAMES.get(plate_id, plate_id)

    # ── Load census ──
    census = load_census(args.census)
    rkey = (f"{plate_id}_NE"
            if len(PLATE_RELAYS.get(plate_id, [])) > 1
            else plate_id)
    mode_freqs = get_plate_modes(census, plate_id, relay_key=rkey)
    n_modes = len(mode_freqs)
    n_carriers = min(7, n_modes)

    print(f"\n{'═'*74}")
    print(f"  PLATE OPTIONS VOL-TRADING — VARIANCE RISK PREMIUM HARVESTER")
    print(f"  Plate {name}: {n_modes} modes, {n_carriers} carriers")
    print(f"  Strategy: classify vol regime → time short-premium trades")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"{'═'*74}")

    # ── Get carrier responses ──
    if args.cache:
        carriers, cached_freqs, cached_n_modes = load_carrier_cache(args.cache)
        if cached_freqs:
            mode_freqs = cached_freqs
            n_modes = cached_n_modes
        print(f"\n  Loaded carrier cache: {len(carriers)} carriers × {n_modes} modes")
    elif args.dry_run:
        carriers, carrier_indices = simulate_carrier_responses(
            mode_freqs, n_carriers)
        print(f"\n  Simulated {n_carriers} carriers × {n_modes} modes (Lorentzian)")
    else:
        if not args.port:
            parser.error("Hardware mode requires port argument or --dry-run")
        from relay_mux import RelayMux
        handle = open_scope()
        mux = RelayMux(port=args.port)
        mux.open()

        print(f"\n  Capturing plate {name} carriers...", flush=True)
        t0 = time.time()
        carriers, carrier_indices = capture_plate_carriers(
            handle, mux, mode_freqs, plate_id)
        dt = time.time() - t0
        print(f"  Captured {n_carriers} carriers in {dt:.1f}s")

        # Save cache
        cache_path = LAB_DIR / f"carrier_cache_{name}_vol.json"
        save_carrier_cache(cache_path, carriers, mode_freqs,
                           carrier_indices, plate_id)
        print(f"  Saved cache: {cache_path.name}")

        close_scope(handle)
        mux.close()

    # ── Backtest each symbol ──
    all_results = {}
    for sym in symbols:
        results = backtest_symbol(sym, carriers, n_modes, period=args.period)
        if results:
            all_results[sym] = results

    # ── Save results ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = LAB_DIR / f"options_vol_{ts}.json"

    save_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate": plate_id,
        "plate_name": name,
        "n_modes": n_modes,
        "n_carriers": len(carriers),
        "strategy": "variance_risk_premium_classifier",
        "vol_lookback_short": VOL_LOOKBACK_SHORT,
        "vol_lookback_long": VOL_LOOKBACK_LONG,
        "vol_forward": VOL_FORWARD,
        "vrp_markup": VRP_MARKUP,
        "friction_bps": FRICTION_OPTIONS_BPS,
        "train_window": TRAIN_WINDOW,
        "test_window": TEST_WINDOW,
        "symbols": {},
    }
    for sym, res in all_results.items():
        save_data["symbols"][sym] = {
            k: {kk: (float(vv) if isinstance(vv, (np.floating, float)) else vv)
                for kk, vv in v.items()}
            for k, v in res.items()
        }

    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\n  Results saved: {out_path.name}")

    # ── Final summary ──
    print(f"\n{'═'*74}")
    print(f"  SUMMARY — SN8 VIABILITY CHECK")
    print(f"{'═'*74}")
    for sym, res in all_results.items():
        best_key = max(res, key=lambda k: res[k]["sharpe"])
        best = res[best_key]
        sn8 = best["sharpe"] > 0.5 and best["max_dd_pct"] < 15
        print(f"  {sym:>8}  {best_key:<28} Sharpe={best['sharpe']:+.2f}  "
              f"DD={best['max_dd_pct']:.1f}%  {'PASS' if sn8 else 'FAIL'}")

    print(f"{'═'*74}\n")


if __name__ == "__main__":
    main()
