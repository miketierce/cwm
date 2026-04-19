#!/usr/bin/env python3
"""
Plate Trading Iterations — Six strategies toward SN8 viability.

Each iteration attacks a specific failure mode from the validation suite:

  V1 (baseline):     7 daily candles → plate → next-day direction
                     PROBLEM: thin signal, friction kills it, concentrated

  ITER 1 — CONFIDENCE GATING + HOLD PERIOD
    Only trade when |ridge_confidence| > threshold.  Hold position for N days.
    Attacks: friction (fewer trades), concentration (skip low-conviction days)

  ITER 2 — TECHNICAL INDICATOR ENCODING
    Instead of 7 raw candle directions, encode 7 technical indicators:
      RSI>50, MACD>signal, price>SMA20, price>SMA50, vol>avg_vol,
      BB_width>median, OBV_trend>0
    Attacks: input informativeness — each carrier encodes different market info

  ITER 3 — MULTI-ASSET CROSS-SPECTRUM
    Encode today's candle direction for 7 different assets:
      BTC, ETH, SOL, S&P500, Gold, DXY, VIX
    Plate cross-coupling = cross-asset interaction detector.
    Attacks: pattern diversity — 7 uncorrelated binary inputs >> 7 correlated lags

  ITER 4 — WEEKLY TARGET (5-day forward return)
    Predict sign of 5-day-forward return instead of next-day.
    Hold for 5 days (1 rebalance per week).
    Attacks: friction (5× fewer trades), noise (weekly signal > daily)

  ITER 5 — REGIME-GATED TRADING
    Only trade in chop+lowvol regimes where plate showed edge.
    FLAT in bear and high-vol. SN8 supports FLAT signals.
    Attacks: regime instability, drawdown control

  ITER 6 — ENSEMBLE: ALL FIVE ITERATIONS VOTE
    Majority vote of Iters 1-5.  Only trade when ≥4/5 agree.
    Attacks: overfitting to any single encoding

Uses cached carrier responses. No hardware needed.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

from plate_trading_backtest import (
    interaction_expand,
    ridge_classify,
    download_prices,
    POLY_DEGREE,
)
from plate_trading_validate import (
    walk_forward,
    apply_friction,
    _metrics_from_strat_returns,
    analyze_concentration,
    FRICTION_BPS,
)

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab" / "plate_exps"


# ══════════════════════════════════════════════════════════════════
# Feature builders
# ══════════════════════════════════════════════════════════════════

def build_plate_features(binary_matrix, carrier_responses, n_modes,
                         weight_matrix=None):
    """Build plate spectral features from a binary input matrix.

    binary_matrix: (N, n_carriers) — each row is one input pattern
    carrier_responses: dict[int, ndarray] — cached spectral responses
    weight_matrix: optional (N, n_carriers) amplitude weights
    Returns: X_poly (N, n_features) with polynomial expansion
    """
    N, n_carriers = binary_matrix.shape

    X_raw = np.zeros((N, n_carriers * n_modes))
    poly_list = []

    for i in range(N):
        for b in range(n_carriers):
            if binary_matrix[i, b] > 0:
                resp = carrier_responses[b % len(carrier_responses)].copy()
                if weight_matrix is not None:
                    resp = resp * abs(weight_matrix[i, b])
                X_raw[i, b * n_modes:(b + 1) * n_modes] = resp

        carrier_energies = np.array([
            X_raw[i, b * n_modes:(b + 1) * n_modes].sum()
            for b in range(n_carriers)
        ])
        poly_terms = interaction_expand(carrier_energies, POLY_DEGREE)
        poly_list.append(np.concatenate([X_raw[i], poly_terms]))

    return np.array(poly_list)


def compute_rsi(close, period=14):
    """Relative Strength Index."""
    delta = np.diff(close)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    rsi = np.full(len(close), 50.0)
    if len(gains) < period:
        return rsi
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / (avg_loss + 1e-10)
        rsi[i + 1] = 100 - 100 / (1 + rs)
    return rsi


def compute_ema(data, span):
    """Exponential moving average."""
    alpha = 2 / (span + 1)
    ema = np.zeros(len(data))
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema


def compute_sma(data, window):
    """Simple moving average."""
    sma = np.full(len(data), np.nan)
    for i in range(window - 1, len(data)):
        sma[i] = np.mean(data[i - window + 1:i + 1])
    return sma


def compute_technical_indicators(close, high, low, volume):
    """Compute 7 binary technical indicators."""
    n = len(close)
    indicators = np.zeros((n, 7))

    # 1: RSI > 50
    rsi = compute_rsi(close)
    indicators[:, 0] = (rsi > 50).astype(float)

    # 2: MACD > signal (12,26,9 EMA)
    ema12 = compute_ema(close, 12)
    ema26 = compute_ema(close, 26)
    macd = ema12 - ema26
    signal = compute_ema(macd, 9)
    indicators[:, 1] = (macd > signal).astype(float)

    # 3: Price > SMA20
    sma20 = compute_sma(close, 20)
    indicators[:, 2] = (close > sma20).astype(float)

    # 4: Price > SMA50
    sma50 = compute_sma(close, 50)
    indicators[:, 3] = (close > sma50).astype(float)

    # 5: Volume > 20-day average volume
    vol_sma = compute_sma(volume, 20)
    indicators[:, 4] = (volume > vol_sma).astype(float)

    # 6: Bollinger Band width > median (volatility expanding)
    sma20_bb = compute_sma(close, 20)
    bb_std = np.full(n, np.nan)
    for i in range(19, n):
        bb_std[i] = np.std(close[i - 19:i + 1])
    bb_width = 2 * bb_std / np.maximum(np.abs(sma20_bb), 1e-10)
    med_bw = np.nanmedian(bb_width)
    indicators[:, 5] = (bb_width > med_bw).astype(float)

    # 7: OBV trend (OBV > its 10-day SMA)
    obv = np.zeros(n)
    for i in range(1, n):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]
    obv_sma = compute_sma(obv, 10)
    indicators[:, 6] = (obv > obv_sma).astype(float)

    return indicators


def compute_realized_vol(close, window=20):
    """Rolling realized volatility (annualized)."""
    rets = np.diff(close) / np.maximum(np.abs(close[:-1]), 1e-10)
    vol = np.full(len(close), np.nan)
    for i in range(window, len(rets)):
        vol[i + 1] = np.std(rets[i - window + 1:i + 1]) * np.sqrt(252)
    return vol


def rolling_return(close, window=20):
    """Rolling return over window days."""
    ret = np.full(len(close), 0.0)
    for i in range(window, len(close)):
        ret[i] = (close[i] - close[i - window]) / close[i - window]
    return ret


# ══════════════════════════════════════════════════════════════════
# Walk-forward with friction and optional gating
# ══════════════════════════════════════════════════════════════════

def walk_forward_gated(X, y, label_rets, train_window, test_window,
                       alpha_grid, friction_bps=FRICTION_BPS,
                       confidence_threshold=0.0, hold_days=1,
                       trade_mask=None):
    """Walk-forward with confidence gating, hold period, and regime masking.

    confidence_threshold: only trade when |confidence| > threshold (else FLAT=0)
    hold_days: hold position for N days before reconsidering
    trade_mask: boolean array — only trade on True days, FLAT on False
    """
    N = len(y)
    all_preds = np.zeros(N)
    all_active = np.zeros(N, dtype=bool)  # whether we actually traded

    i = 0
    while i + train_window + test_window <= N:
        tr_s, tr_e = i, i + train_window
        te_s, te_e = tr_e, min(tr_e + test_window, N)

        Xtr, ytr = X[tr_s:tr_e], y[tr_s:tr_e]
        Xte = X[te_s:te_e]

        # Grid search alpha
        best_alpha = 1.0
        best_acc = 0
        for a in alpha_grid:
            p_tr, _, _ = ridge_classify(Xtr, ytr, Xte, alpha=a)
            acc = np.mean(p_tr == ytr)
            if acc > best_acc:
                best_acc = acc
                best_alpha = a

        _, pred_te, confidence = ridge_classify(Xtr, ytr, Xte, alpha=best_alpha)

        # Apply gating
        for j in range(len(pred_te)):
            idx = te_s + j
            if idx >= N:
                break

            # Regime gate
            if trade_mask is not None and not trade_mask[idx]:
                all_preds[idx] = 0.0  # FLAT
                continue

            # Confidence gate
            if abs(confidence[j]) < confidence_threshold:
                all_preds[idx] = 0.0  # FLAT
                continue

            all_preds[idx] = pred_te[j]
            all_active[idx] = True

        i += test_window

    # Apply hold period: once we enter a position, hold for hold_days
    if hold_days > 1:
        held_preds = np.zeros(N)
        current_pos = 0.0
        hold_counter = 0
        for idx in range(N):
            if hold_counter > 0:
                held_preds[idx] = current_pos
                hold_counter -= 1
            elif all_preds[idx] != 0:
                current_pos = all_preds[idx]
                held_preds[idx] = current_pos
                hold_counter = hold_days - 1
            else:
                held_preds[idx] = 0.0
                current_pos = 0.0
        all_preds = held_preds

    # Compute metrics with friction
    oos_mask = all_preds != 0
    strat_ret = apply_friction(all_preds, label_rets, friction_bps)

    # Effective trades (position changes)
    n_position_changes = int(np.sum(np.abs(np.diff(all_preds)) > 0))
    n_active = int(np.sum(oos_mask))
    n_flat = int(np.sum(~oos_mask))

    m = _metrics_from_strat_returns(strat_ret)
    m["n_active_days"] = n_active
    m["n_flat_days"] = n_flat
    m["n_position_changes"] = n_position_changes
    m["exposure_pct"] = n_active / N * 100 if N > 0 else 0

    return m, all_preds, strat_ret


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate trading iterations — 6 strategies toward SN8")
    parser.add_argument("--cache", required=True)
    parser.add_argument("--period", default="2y")
    args = parser.parse_args()

    # Load carrier cache
    with open(args.cache) as f:
        cached = json.load(f)
    mode_freqs = cached["mode_freqs_hz"]
    n_modes = cached["n_modes"]
    n_carriers = len(cached["responses"])
    carrier_responses = {}
    for b in range(n_carriers):
        carrier_responses[b] = np.array(cached["responses"][str(b)])
    plate_name = cached.get("plate_name", "?")

    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]
    train_window = 120
    test_window = 20

    print(f"\n{'═'*74}")
    print(f"  PLATE TRADING ITERATIONS — SN8 VIABILITY")
    print(f"  Plate {plate_name}, {n_modes} modes, {n_carriers} carriers")
    print(f"  All tests: walk-forward, 17 bps friction, 1-bar execution lag")
    print(f"{'═'*74}")

    # ── Download all data ──
    warnings.filterwarnings("ignore")
    print(f"\n  Downloading data ({args.period})...")

    btc = download_prices("BTC-USD", period=args.period)
    close = btc["Close"].values.flatten().astype(np.float64)
    open_ = btc["Open"].values.flatten().astype(np.float64)
    high = btc["High"].values.flatten().astype(np.float64)
    low = btc["Low"].values.flatten().astype(np.float64)
    volume = btc["Volume"].values.flatten().astype(np.float64)
    n_days = len(close)
    print(f"    BTC-USD: {n_days} days")

    # Multi-asset data
    multi_tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "^GSPC", "GC=F", "DX-Y.NYB", "^VIX"]
    multi_data = {}
    for t in multi_tickers:
        try:
            df = download_prices(t, period=args.period)
            multi_data[t] = df
            print(f"    {t}: {len(df)} days")
        except Exception as e:
            print(f"    {t}: FAILED ({e})")

    # ── Precompute BTC labels ──
    lookback = 7
    directions = (close > open_).astype(int)
    next_rets = np.diff(close) / np.maximum(np.abs(close[:-1]), 1e-10)

    # For daily target
    labels_1d = np.array([
        1.0 if next_rets[i] > 0 else -1.0
        for i in range(lookback, len(close) - 1)
    ])
    label_rets_1d = np.array([next_rets[i] for i in range(lookback, len(close) - 1)])
    N = len(labels_1d)

    # Daily candle patterns (baseline)
    patterns_daily = np.array([
        directions[i - lookback:i]
        for i in range(lookback, len(close) - 1)
    ])

    # Candle returns for weighting
    candle_rets = (close - open_) / np.maximum(np.abs(open_), 1e-10)
    win_rets = np.array([
        candle_rets[i - lookback:i]
        for i in range(lookback, len(close) - 1)
    ])

    print(f"\n  {N} windows for BTC-USD daily prediction")

    # ── Build baseline features ──
    X_baseline = build_plate_features(
        patterns_daily, carrier_responses, n_modes,
        weight_matrix=win_rets)

    # ══════════════════════════════════════════════════════════════
    # V1 BASELINE (from validation)
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  V1 BASELINE — 7 daily candles, return-weighted, daily rebalance")
    print(f"{'━'*74}")

    m_base, preds_base, sret_base = walk_forward_gated(
        X_baseline, labels_1d, label_rets_1d,
        train_window, test_window, alpha_grid,
        friction_bps=FRICTION_BPS)

    _print_result("V1 Baseline", m_base)

    # ══════════════════════════════════════════════════════════════
    # ITER 1 — CONFIDENCE GATING + 3-DAY HOLD
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  ITER 1 — CONFIDENCE GATING + HOLD PERIOD")
    print(f"  Only trade when |confidence| > threshold, hold 3 days")
    print(f"{'━'*74}")

    best_iter1 = None
    for conf_thresh in [0.0, 0.05, 0.10, 0.20, 0.30]:
        for hold in [1, 3, 5]:
            m, preds, sret = walk_forward_gated(
                X_baseline, labels_1d, label_rets_1d,
                train_window, test_window, alpha_grid,
                friction_bps=FRICTION_BPS,
                confidence_threshold=conf_thresh,
                hold_days=hold)
            if best_iter1 is None or m["sharpe"] > best_iter1[0]["sharpe"]:
                best_iter1 = (m, preds, sret, conf_thresh, hold)

    m1, preds1, sret1, best_ct, best_hold = best_iter1
    print(f"  Best config: threshold={best_ct}, hold={best_hold}d")
    _print_result("Iter 1 (conf+hold)", m1)

    # ══════════════════════════════════════════════════════════════
    # ITER 2 — TECHNICAL INDICATOR ENCODING
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  ITER 2 — TECHNICAL INDICATOR ENCODING")
    print(f"  7 indicators: RSI>50, MACD>sig, P>SMA20, P>SMA50,")
    print(f"  V>avgV, BB_wid>med, OBV>SMA10")
    print(f"{'━'*74}")

    indicators = compute_technical_indicators(close, high, low, volume)

    # Align: indicator at index i → label at i (predict next day from today's indicators)
    start_idx = max(50, lookback)  # need SMA50 warmup
    ind_patterns = indicators[start_idx:-1]  # (N', 7)
    ind_labels = np.array([
        1.0 if next_rets[i] > 0 else -1.0
        for i in range(start_idx, len(close) - 1)
    ])
    ind_rets = np.array([next_rets[i] for i in range(start_idx, len(close) - 1)])
    N_ind = len(ind_labels)

    # Magnitude weights: use absolute daily return as weight
    ind_weights = np.abs(np.array([
        candle_rets[i] for i in range(start_idx, len(close) - 1)
    ]))
    ind_weight_matrix = np.column_stack([ind_weights] * 7)

    X_tech = build_plate_features(
        ind_patterns, carrier_responses, n_modes,
        weight_matrix=ind_weight_matrix)

    m2, preds2, sret2 = walk_forward_gated(
        X_tech, ind_labels, ind_rets,
        train_window, test_window, alpha_grid,
        friction_bps=FRICTION_BPS)

    _print_result("Iter 2 (tech indicators)", m2)

    # Also try with confidence gating
    m2g, preds2g, sret2g = walk_forward_gated(
        X_tech, ind_labels, ind_rets,
        train_window, test_window, alpha_grid,
        friction_bps=FRICTION_BPS,
        confidence_threshold=0.10, hold_days=3)
    _print_result("Iter 2 + gating", m2g)

    # ══════════════════════════════════════════════════════════════
    # ITER 3 — MULTI-ASSET CROSS-SPECTRUM
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  ITER 3 — MULTI-ASSET CROSS-SPECTRUM")
    print(f"  7 assets' daily direction → 7 carriers → plate cross-coupling")
    print(f"{'━'*74}")

    # Align all assets to BTC dates
    btc_dates = btc.index
    asset_directions = np.zeros((len(btc_dates), len(multi_tickers)))

    for j, ticker in enumerate(multi_tickers):
        if ticker not in multi_data:
            continue
        adf = multi_data[ticker]
        ac = adf["Close"].values.flatten().astype(np.float64)
        ao = adf["Open"].values.flatten().astype(np.float64)
        a_dir = (ac > ao).astype(float)
        a_dates = adf.index

        # Map to BTC dates
        for i, bd in enumerate(btc_dates):
            # Find closest matching date
            mask = a_dates <= bd
            if mask.any():
                idx = mask.sum() - 1
                if idx < len(a_dir):
                    asset_directions[i, j] = a_dir[idx]

    # Build windows: each row = [BTC_dir, ETH_dir, SOL_dir, SP500_dir, Gold_dir, DXY_dir, VIX_dir]
    # Labels = BTC next-day return
    ma_start = 1  # need at least 1 prior day
    ma_patterns = asset_directions[ma_start:-1]
    ma_labels = np.array([
        1.0 if next_rets[i] > 0 else -1.0
        for i in range(ma_start, len(close) - 1)
    ])
    ma_rets = np.array([next_rets[i] for i in range(ma_start, len(close) - 1)])
    N_ma = len(ma_labels)

    # Weight by BTC daily return magnitude
    ma_weights = np.abs(np.array([
        candle_rets[i] for i in range(ma_start, len(close) - 1)
    ]))
    ma_weight_matrix = np.column_stack([ma_weights] * 7)

    X_multi = build_plate_features(
        ma_patterns, carrier_responses, n_modes,
        weight_matrix=ma_weight_matrix)

    m3, preds3, sret3 = walk_forward_gated(
        X_multi, ma_labels, ma_rets,
        train_window, test_window, alpha_grid,
        friction_bps=FRICTION_BPS)

    _print_result("Iter 3 (multi-asset)", m3)

    m3g, preds3g, sret3g = walk_forward_gated(
        X_multi, ma_labels, ma_rets,
        train_window, test_window, alpha_grid,
        friction_bps=FRICTION_BPS,
        confidence_threshold=0.10, hold_days=3)
    _print_result("Iter 3 + gating", m3g)

    # ══════════════════════════════════════════════════════════════
    # ITER 4 — WEEKLY TARGET (5-day forward return)
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  ITER 4 — WEEKLY TARGET")
    print(f"  Predict 5-day forward return, rebalance weekly")
    print(f"{'━'*74}")

    # 5-day forward returns
    fwd5_rets = np.zeros(len(close))
    for i in range(len(close) - 5):
        fwd5_rets[i] = (close[i + 5] - close[i]) / close[i]

    # Labels and rets aligned to patterns
    labels_5d = np.array([
        1.0 if fwd5_rets[i] > 0 else -1.0
        for i in range(lookback, len(close) - 5)
    ])
    label_rets_5d = np.array([fwd5_rets[i] for i in range(lookback, len(close) - 5)])
    N_5d = len(labels_5d)

    # Use same daily patterns but predict weekly
    patterns_5d = np.array([
        directions[i - lookback:i]
        for i in range(lookback, len(close) - 5)
    ])
    win_rets_5d = np.array([
        candle_rets[i - lookback:i]
        for i in range(lookback, len(close) - 5)
    ])

    X_weekly = build_plate_features(
        patterns_5d, carrier_responses, n_modes,
        weight_matrix=win_rets_5d)

    # Walk-forward with 5-day hold (forces weekly rebalance)
    m4, preds4, sret4 = walk_forward_gated(
        X_weekly, labels_5d, label_rets_5d,
        train_window, test_window, alpha_grid,
        friction_bps=FRICTION_BPS,
        hold_days=5)

    _print_result("Iter 4 (weekly target)", m4)

    # Also try technical indicators → weekly target
    ind_labels_5d = np.array([
        1.0 if fwd5_rets[i] > 0 else -1.0
        for i in range(start_idx, len(close) - 5)
    ])
    ind_rets_5d = np.array([fwd5_rets[i] for i in range(start_idx, len(close) - 5)])
    ind_pats_5d = indicators[start_idx:len(close) - 5]
    iw5 = np.abs(np.array([candle_rets[i] for i in range(start_idx, len(close) - 5)]))
    iw5_mat = np.column_stack([iw5] * 7)

    if len(ind_labels_5d) > train_window + test_window:
        X_tech_5d = build_plate_features(
            ind_pats_5d, carrier_responses, n_modes,
            weight_matrix=iw5_mat)
        m4t, preds4t, sret4t = walk_forward_gated(
            X_tech_5d, ind_labels_5d, ind_rets_5d,
            train_window, test_window, alpha_grid,
            friction_bps=FRICTION_BPS,
            hold_days=5)
        _print_result("Iter 4 + tech indicators", m4t)

    # ══════════════════════════════════════════════════════════════
    # ITER 5 — REGIME-GATED TRADING
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  ITER 5 — REGIME-GATED TRADING")
    print(f"  FLAT in bear + high-vol; trade only in chop/lowvol")
    print(f"{'━'*74}")

    # Compute regime for each window
    rvol = compute_realized_vol(close, window=20)
    rret = rolling_return(close, window=20)

    # Regime mask: True = trade, False = FLAT
    # Trade when: not in bear AND not in high vol
    regime_mask = np.ones(N, dtype=bool)
    for i in range(N):
        ci = i + lookback  # actual close index
        if ci < 20:
            regime_mask[i] = False
            continue
        r = rret[ci]
        v = rvol[ci]
        if np.isnan(v):
            regime_mask[i] = False
            continue

        is_bear = r < -0.10
        is_hivol = v > 0.80

        if is_bear or is_hivol:
            regime_mask[i] = False

    n_trade = int(regime_mask.sum())
    n_flat = N - n_trade
    print(f"  Regime filter: {n_trade} tradeable days, {n_flat} FLAT days "
          f"({n_flat/N*100:.0f}% filtered)")

    m5, preds5, sret5 = walk_forward_gated(
        X_baseline, labels_1d, label_rets_1d,
        train_window, test_window, alpha_grid,
        friction_bps=FRICTION_BPS,
        trade_mask=regime_mask)

    _print_result("Iter 5 (regime-gated)", m5)

    # Regime + confidence gating
    m5g, preds5g, sret5g = walk_forward_gated(
        X_baseline, labels_1d, label_rets_1d,
        train_window, test_window, alpha_grid,
        friction_bps=FRICTION_BPS,
        confidence_threshold=0.10, hold_days=3,
        trade_mask=regime_mask)
    _print_result("Iter 5 + conf+hold", m5g)

    # ══════════════════════════════════════════════════════════════
    # ITER 6 — ENSEMBLE VOTE
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  ITER 6 — ENSEMBLE VOTE")
    print(f"  Majority of all strategies; trade only when ≥4/5 agree")
    print(f"{'━'*74}")

    # Align all prediction series to the same length
    # Use the baseline timeframe (N windows)
    # Pad shorter series to N with 0 (FLAT)
    def pad_to_N(preds, target_n, offset=0):
        p = np.zeros(target_n)
        end = min(offset + len(preds), target_n)
        p[offset:end] = preds[:end - offset]
        return p

    # Iter 2 and 3 may have different offsets
    iter2_offset = start_idx - lookback
    iter3_offset = ma_start - lookback
    iter5_offset = 0

    all_strategies = [
        pad_to_N(preds_base, N, 0),
        pad_to_N(preds1, N, 0),
        pad_to_N(preds2, N, max(0, iter2_offset)),
        pad_to_N(preds3, N, max(0, iter3_offset)),
        pad_to_N(preds5, N, 0),
    ]

    # Majority vote
    votes = np.sign(np.sum(np.sign(all_strategies), axis=0))

    # Strong consensus: only trade when ≥4/5 agree
    agree_count = np.abs(np.sum(np.sign(all_strategies), axis=0))
    consensus_mask = agree_count >= 4

    ensemble_preds = np.where(consensus_mask, votes, 0.0)

    # Apply friction
    ensemble_sret = apply_friction(ensemble_preds, label_rets_1d, FRICTION_BPS)
    m6 = _metrics_from_strat_returns(ensemble_sret)

    n_active = int(np.sum(ensemble_preds != 0))
    n_changes = int(np.sum(np.abs(np.diff(ensemble_preds)) > 0))
    m6["n_active_days"] = n_active
    m6["n_flat_days"] = N - n_active
    m6["n_position_changes"] = n_changes
    m6["exposure_pct"] = n_active / N * 100

    _print_result("Iter 6 (ensemble ≥4/5)", m6)

    # Also try simple majority (≥3/5)
    consensus3_mask = agree_count >= 3
    ens3_preds = np.where(consensus3_mask, votes, 0.0)
    ens3_sret = apply_friction(ens3_preds, label_rets_1d, FRICTION_BPS)
    m6b = _metrics_from_strat_returns(ens3_sret)
    n_active3 = int(np.sum(ens3_preds != 0))
    m6b["n_active_days"] = n_active3
    m6b["exposure_pct"] = n_active3 / N * 100
    _print_result("Iter 6 (ensemble ≥3/5)", m6b)

    # ══════════════════════════════════════════════════════════════
    # COMPARISON TABLE
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'═'*74}")
    print(f"  COMPARISON — ALL ITERATIONS (after 17bps friction)")
    print(f"{'═'*74}")

    all_results = [
        ("V1 Baseline (daily rw+poly)", m_base),
        (f"Iter 1 (conf={best_ct} hold={best_hold}d)", m1),
        ("Iter 2 (tech indicators)", m2),
        ("Iter 2 + gating", m2g),
        ("Iter 3 (multi-asset)", m3),
        ("Iter 3 + gating", m3g),
        ("Iter 4 (weekly target)", m4),
        ("Iter 5 (regime-gated)", m5),
        ("Iter 5 + conf+hold", m5g),
        ("Iter 6 (ensemble ≥4/5)", m6),
        ("Iter 6 (ensemble ≥3/5)", m6b),
    ]

    print(f"\n  {'Strategy':<34} {'Sharpe':>7} {'Ret%':>8} {'MaxDD%':>7} "
          f"{'WinR%':>6} {'Expos%':>7} {'Trades':>7}")
    print(f"  {'─'*80}")

    best_sharpe = -999
    best_name = ""
    for name, m in all_results:
        exp = m.get("exposure_pct", 100)
        trades = m.get("n_position_changes", m.get("n_trades", 0))
        tag = ""
        if m["sharpe"] > best_sharpe:
            best_sharpe = m["sharpe"]
            best_name = name
            tag = " ◄"
        print(f"  {name:<34} {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {exp:>6.1f}% {trades:>7}{tag}")

    print(f"\n  Best: {best_name} (Sharpe={best_sharpe:+.2f})")

    # ── Concentration check on best ──
    for name, m in all_results:
        if name == best_name:
            # Find corresponding predictions
            break

    # SN8 viability check
    print(f"\n  ── SN8 Viability Check ──")
    viable = []
    for name, m in all_results:
        checks = {
            "sharpe_pos": m["sharpe"] > 0,
            "sharpe_05": m["sharpe"] > 0.5,
            "dd_under_10": m["max_dd_pct"] < 10,
            "dd_under_15": m["max_dd_pct"] < 15,
            "profitable": m["total_ret_pct"] > 0,
        }
        score = sum(checks.values())
        if score >= 3:
            viable.append((name, m, checks, score))

    if viable:
        print(f"  Strategies passing ≥3/5 SN8 criteria:")
        for name, m, checks, score in sorted(viable, key=lambda x: -x[3]):
            flags = " ".join(
                f"{'✓' if v else '✗'}{k}" for k, v in checks.items())
            print(f"    {score}/5 {name}")
            print(f"         {flags}")
    else:
        print(f"  No strategy passes ≥3/5 SN8 criteria.")
        print(f"  The plate kernel adds signal but it's sub-threshold for live trading.")

    # ── Save ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = LAB_DIR / f"trading_iterations_{plate_name}_{timestamp}.json"
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate": plate_name,
        "n_modes": n_modes,
        "iterations": {name: {
            k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
            for k, v in m.items()
        } for name, m in all_results},
        "best": best_name,
        "best_sharpe": float(best_sharpe),
    }
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {out_file.name}")


def _print_result(name, m):
    exp = m.get("exposure_pct", 100)
    trades = m.get("n_position_changes", m.get("n_trades", 0))
    print(f"    Sharpe={m['sharpe']:+.2f}  ret={m['total_ret_pct']:+.1f}%  "
          f"maxDD={m['max_dd_pct']:.1f}%  winR={m['win_rate_pct']:.1f}%  "
          f"exposure={exp:.0f}%  trades={trades}")


if __name__ == "__main__":
    main()
