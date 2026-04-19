#!/usr/bin/env python3
"""
Plate Trading Signal Backtest — Bittensor SN8 (Vanta) Viability Test

Tests whether a fused-silica plate reservoir computer can generate
profitable trading signals for Bittensor Subnet 8 (Vanta Network).

Architecture:
  Historical OHLCV → encode as binary candle patterns →
  drive plate carriers (one per lookback candle) →
  capture spectral response (N modes per carrier) →
  polynomial feature expansion → ridge readout →
  LONG/SHORT prediction → backtest with trading metrics

The plate acts as a nonlinear kernel (reservoir computer).
Nobody on the other end sees "glass" — they see an API that
takes data and returns predictions.

Usage:
    # Hardware backtest on plate D:
    python plate_trading_backtest.py /dev/cu.usbserial-11310 \\
        --census data/results/lab/plate_exps/plate_census_20260412_180543.json

    # Dry-run (simulated plate) to test pipeline:
    python plate_trading_backtest.py --dry-run \\
        --census data/results/lab/plate_exps/plate_census_20260412_180543.json

    # Reuse cached carrier responses:
    python plate_trading_backtest.py --dry-run \\
        --census <census.json> --cache carrier_cache_D.json
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
    FIXTURE_FREQ_HZ, FIXTURE_GUARD_HZ,
)

# ── Configuration ─────────────────────────────────────────────────
N_AVG = 8               # averages per spectral capture
SETTLE_S = 0.15         # AWG settle time
SETTLE_RELAY_S = 0.10   # relay settle time
LOOKBACK = 7            # candles in lookback window (= carrier count)
TRAIN_RATIO = 0.70      # chronological train/test split
POLY_DEGREE = 4         # polynomial interaction degree

DEFAULT_SYMBOLS = ["EURUSD=X", "BTC-USD"]

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab" / "plate_exps"
LAB_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# PicoScope capture
# ══════════════════════════════════════════════════════════════════

def open_scope():
    """Open PicoScope and configure Ch A."""
    import cwm_picoscope  # noqa — sets DYLD_LIBRARY_PATH
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V DC
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B off
    return handle


def close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)


def awg_off(handle):
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)


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
# Feature construction
# ══════════════════════════════════════════════════════════════════

def interaction_expand(x, max_degree=4):
    """Polynomial interaction expansion (same as reservoir demo)."""
    n = len(x)
    terms = list(x)  # degree 1
    for d in range(2, min(max_degree + 1, n + 1)):
        for combo in combinations(range(n), d):
            t = 1.0
            for idx in combo:
                t *= x[idx]
            terms.append(t)
    return np.array(terms)


def build_feature_matrix(patterns, carrier_responses, n_modes,
                         returns_matrix=None, encoding="binary"):
    """Build feature matrices for all windows.

    Args:
        patterns: (N, lookback) binary 0/1 arrays
        carrier_responses: dict[int, ndarray(n_modes)]
        n_modes: number of readout modes
        returns_matrix: (N, lookback) candle returns (for weighted encoding)
        encoding: "binary" or "return_weighted"

    Returns:
        X_raw: (N, lookback × n_modes)  cross-matrix features
        X_poly: (N, lookback × n_modes + poly_terms)  with polynomial
    """
    N, lookback = patterns.shape
    n_carriers = lookback

    X_raw = np.zeros((N, n_carriers * n_modes))
    poly_list = []

    for i in range(N):
        # Cross-matrix: carrier b active → row b = spectral response
        for b in range(n_carriers):
            if patterns[i, b] > 0:
                resp = carrier_responses[b]
                if encoding == "return_weighted" and returns_matrix is not None:
                    resp = resp * abs(returns_matrix[i, b])
                X_raw[i, b * n_modes:(b + 1) * n_modes] = resp

        # Carrier energies → polynomial expansion
        carrier_energies = np.array([
            X_raw[i, b * n_modes:(b + 1) * n_modes].sum()
            for b in range(n_carriers)
        ])
        poly_terms = interaction_expand(carrier_energies, POLY_DEGREE)
        poly_list.append(np.concatenate([X_raw[i], poly_terms]))

    X_poly = np.array(poly_list)
    return X_raw, X_poly


# ══════════════════════════════════════════════════════════════════
# Ridge classifier
# ══════════════════════════════════════════════════════════════════

def ridge_classify(X_train, y_train, X_test, alpha=1.0):
    """Ridge regression as classifier (targets ±1)."""
    n_feat = X_train.shape[1]

    # Standardize
    mu = X_train.mean(axis=0)
    std = X_train.std(axis=0)
    std[std < 1e-12] = 1.0
    Xtr = (X_train - mu) / std
    Xte = (X_test - mu) / std

    # Solve normal equations with L2
    XtX = Xtr.T @ Xtr + alpha * np.eye(n_feat)
    Xty = Xtr.T @ y_train
    w = np.linalg.solve(XtX, Xty)

    pred_train = np.sign(Xtr @ w)
    pred_test = np.sign(Xte @ w)
    pred_train[pred_train == 0] = 1
    pred_test[pred_test == 0] = 1

    confidence = Xte @ w
    return pred_train, pred_test, confidence


# ══════════════════════════════════════════════════════════════════
# Trading metrics
# ══════════════════════════════════════════════════════════════════

def compute_metrics(predictions, actual_returns):
    """Compute SN8-relevant trading performance metrics."""
    strat_ret = predictions * actual_returns
    cumulative = np.cumprod(1 + strat_ret)
    total_ret = cumulative[-1] - 1
    n = len(predictions)
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
# Data & encoding
# ══════════════════════════════════════════════════════════════════

def download_prices(symbol, period="1y"):
    """Download daily OHLCV via yfinance."""
    import yfinance as yf
    warnings.filterwarnings("ignore")
    df = yf.download(symbol, period=period, interval="1d", progress=False)
    if df.empty:
        raise ValueError(f"No data for {symbol}")
    # Flatten MultiIndex columns
    if hasattr(df.columns, "levels"):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def prepare_windows(close, open_, lookback):
    """Create binary patterns, labels, and returns from price arrays."""
    directions = (close > open_).astype(int)
    candle_rets = (close - open_) / np.maximum(np.abs(open_), 1e-10)
    next_rets = np.diff(close) / np.maximum(np.abs(close[:-1]), 1e-10)

    patterns, win_rets, labels, label_rets = [], [], [], []
    for i in range(lookback, len(close) - 1):
        patterns.append(directions[i - lookback:i])
        win_rets.append(candle_rets[i - lookback:i])
        labels.append(1.0 if next_rets[i] > 0 else -1.0)
        label_rets.append(next_rets[i])

    return (np.array(patterns), np.array(labels),
            np.array(win_rets), np.array(label_rets))


# ══════════════════════════════════════════════════════════════════
# Backtest one symbol
# ══════════════════════════════════════════════════════════════════

def backtest_symbol(symbol, carrier_responses, mode_freqs, lookback):
    """Full backtest for one trading symbol."""
    n_modes = len(mode_freqs)
    n_carriers = len(carrier_responses)

    # ── Download ──
    print(f"\n  Downloading {symbol} ...", end=" ", flush=True)
    try:
        df = download_prices(symbol)
    except Exception as e:
        print(f"FAILED ({e})")
        return None

    close = df["Close"].values.flatten().astype(np.float64)
    open_ = df["Open"].values.flatten().astype(np.float64)
    print(f"{len(close)} daily candles")

    if len(close) < lookback + 30:
        print(f"    Insufficient data")
        return None

    # ── Build windows ──
    patterns, labels, win_rets, label_rets = prepare_windows(
        close, open_, lookback)
    N = len(labels)
    n_train = int(N * TRAIN_RATIO)
    n_test = N - n_train

    unique_pats = len(set(tuple(p) for p in patterns))
    up_pct = 100 * np.mean(labels == 1)
    print(f"    {N} windows → {n_train} train / {n_test} test")
    print(f"    Unique patterns: {unique_pats}/{2**lookback} | "
          f"Up: {up_pct:.1f}% Down: {100-up_pct:.1f}%")

    # ── Feature matrices ──
    # Binary baseline (raw candle directions, no plate)
    X_bin = patterns.astype(float)
    X_bin_poly = np.array([
        np.concatenate([p, interaction_expand(p, POLY_DEGREE)])
        for p in X_bin
    ])

    # Plate: binary encoding
    X_plate_raw, X_plate_poly = build_feature_matrix(
        patterns, carrier_responses, n_modes)

    # Plate: return-weighted encoding
    X_plate_rw_raw, X_plate_rw_poly = build_feature_matrix(
        patterns, carrier_responses, n_modes,
        returns_matrix=win_rets, encoding="return_weighted")

    # ── Split ──
    y_tr, y_te = labels[:n_train], labels[n_train:]
    ret_te = label_rets[n_train:]

    # ── Run models ──
    models = [
        ("Random (coin flip)",    None),
        ("Buy & hold",            None),
        ("Momentum (last candle)", None),
        ("Ridge (binary 7-dim)",  (X_bin, 10.0)),
        ("Ridge (binary+poly)",   (X_bin_poly, 10.0)),
        ("Plate (raw spectral)",  (X_plate_raw, 1.0)),
        ("Plate (spectral+poly)", (X_plate_poly, 1.0)),
        ("Plate (return-wt raw)", (X_plate_rw_raw, 1.0)),
        ("Plate (return-wt+poly)",(X_plate_rw_poly, 1.0)),
    ]

    # Try multiple alpha values for plate models, pick best on train
    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]

    print(f"\n  {'Model':<26} {'Dims':>5} {'TrAcc':>6} {'TeAcc':>6} "
          f"{'AnnRet':>8} {'Sharpe':>7} {'MaxDD':>6} {'WinR':>6}")
    print(f"  {'─'*79}")

    results = {}
    for name, params in models:
        if name == "Random (coin flip)":
            np.random.seed(42)
            pred_te = np.random.choice([-1.0, 1.0], size=n_test)
            tr_acc = 50.0
            te_acc = 50.0
            dims = 0
        elif name == "Buy & hold":
            pred_te = np.ones(n_test)
            tr_acc = np.mean(y_tr == 1) * 100
            te_acc = np.mean(y_te == 1) * 100
            dims = 0
        elif name == "Momentum (last candle)":
            # Predict same direction as the most recent candle
            pred_te = np.array([
                patterns[n_train + i, -1] * 2 - 1  # map 0/1 → -1/+1
                for i in range(n_test)
            ], dtype=float)
            pred_tr = np.array([
                patterns[i, -1] * 2 - 1 for i in range(n_train)
            ], dtype=float)
            tr_acc = np.mean(pred_tr == y_tr) * 100
            te_acc = np.mean(pred_te == y_te) * 100
            dims = 1
        else:
            X_full, default_alpha = params
            Xtr = X_full[:n_train]
            Xte = X_full[n_train:]
            dims = Xtr.shape[1]

            # Grid search alpha on training accuracy
            best_alpha = default_alpha
            best_train_acc = 0
            for a in alpha_grid:
                p_tr, p_te, _ = ridge_classify(Xtr, y_tr, Xte, alpha=a)
                acc = np.mean(p_tr == y_tr) * 100
                if acc > best_train_acc:
                    best_train_acc = acc
                    best_alpha = a

            pred_tr, pred_te, confidence = ridge_classify(
                Xtr, y_tr, Xte, alpha=best_alpha)
            tr_acc = np.mean(pred_tr == y_tr) * 100
            te_acc = np.mean(pred_te == y_te) * 100

        m = compute_metrics(pred_te, ret_te)
        m["train_acc"] = tr_acc
        m["test_acc"] = te_acc
        m["dims"] = dims
        results[name] = m

        # Highlight plate models
        tag = " ◄" if "Plate" in name and te_acc >= max(
            r.get("test_acc", 0) for r in results.values()) else ""
        print(f"  {name:<26} {dims:>5} {tr_acc:>5.1f}% {te_acc:>5.1f}% "
              f"{m['annual_ret_pct']:>+7.1f}% {m['sharpe']:>+6.2f} "
              f"{m['max_dd_pct']:>5.1f}% {m['win_rate_pct']:>5.1f}%{tag}")

    # ── Pattern analysis ──
    print(f"\n  ── Pattern Analysis ──")
    # Most common patterns
    pat_tuples = [tuple(p) for p in patterns]
    from collections import Counter
    pat_counts = Counter(pat_tuples)
    top5 = pat_counts.most_common(5)
    print(f"  Top 5 patterns (of {unique_pats} unique):")
    for pat, count in top5:
        pat_str = "".join("↑" if b else "↓" for b in pat)
        # What label does this pattern most often predict?
        mask = np.array([tuple(p) == pat for p in patterns])
        up_frac = np.mean(labels[mask] == 1) * 100
        print(f"    {pat_str}  n={count:>3}  "
              f"next-up={up_frac:.0f}%  next-down={100-up_frac:.0f}%")

    # Entropy of pattern distribution
    probs = np.array(list(pat_counts.values())) / N
    entropy = -np.sum(probs * np.log2(probs + 1e-12))
    max_entropy = np.log2(2 ** lookback)
    print(f"  Pattern entropy: {entropy:.2f} / {max_entropy:.1f} bits "
          f"({entropy/max_entropy*100:.0f}% of uniform)")

    return results


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate trading signal backtest — SN8 viability")
    parser.add_argument("port", nargs="?", default=None,
                        help="Arduino serial port (omit for --dry-run)")
    parser.add_argument("--census", required=True)
    parser.add_argument("--plate", default="4")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate plate response (no hardware)")
    parser.add_argument("--cache", default=None,
                        help="Path to save/load carrier response cache")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--lookback", type=int, default=LOOKBACK)
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    lookback = args.lookback
    plate_id = args.plate
    name = PLATE_NAMES.get(plate_id, plate_id)

    # ── Load census ──
    census = load_census(args.census)
    rkey = (f"{plate_id}_NE"
            if len(PLATE_RELAYS.get(plate_id, [])) > 1
            else plate_id)
    mode_freqs = get_plate_modes(census, plate_id, relay_key=rkey)
    n_modes = len(mode_freqs)

    if not mode_freqs:
        print(f"ERROR: No modes for plate {plate_id}")
        sys.exit(1)

    # Census magnitudes (for dry-run simulation)
    results_dict = census.get("results", {})
    centry = results_dict.get(rkey, results_dict.get(plate_id, {}))
    peaks = sorted(centry.get("peaks", []), key=lambda p: p["freq_hz"])
    lo_fix = FIXTURE_FREQ_HZ - FIXTURE_GUARD_HZ
    hi_fix = FIXTURE_FREQ_HZ + FIXTURE_GUARD_HZ
    peaks = [p for p in peaks if not (lo_fix <= p["freq_hz"] <= hi_fix)]
    census_mags = np.array([p.get("magnitude", 100.0) for p in peaks[:n_modes]])
    if len(census_mags) < n_modes:
        census_mags = np.concatenate([
            census_mags, np.ones(n_modes - len(census_mags)) * 100])

    n_carriers = min(lookback, n_modes)
    carrier_indices = np.linspace(0, n_modes - 1, n_carriers, dtype=int).tolist()

    mode_tag = "HARDWARE" if not args.dry_run else "DRY-RUN (simulated plate)"

    print(f"\n{'═'*70}")
    print(f"  PLATE TRADING BACKTEST — SN8 (Vanta Network) Viability")
    print(f"  Plate {name} ({n_modes} modes), {lookback}-candle lookback")
    print(f"  Carriers: {n_carriers} @ {[int(mode_freqs[ci]) for ci in carrier_indices]} Hz")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Mode: {mode_tag}")
    print(f"{'═'*70}")

    # ══════════════════════════════════════════════════════════════
    # Step 1: Get carrier spectral responses
    # ══════════════════════════════════════════════════════════════

    carrier_responses = {}
    cache_path = Path(args.cache) if args.cache else None

    if cache_path and cache_path.exists():
        # Load from cache
        print(f"\n  Loading cached responses: {cache_path}")
        with open(cache_path) as f:
            cached = json.load(f)
        for b in range(n_carriers):
            carrier_responses[b] = np.array(cached["responses"][str(b)])
        print(f"    {n_carriers} carriers × {n_modes} modes loaded")

    elif args.dry_run:
        # Simulate plate response
        print(f"\n  Simulating carrier responses (dry-run)...")
        np.random.seed(2026)
        for b in range(n_carriers):
            ci = carrier_indices[b]
            resp = np.zeros(n_modes)
            for j in range(n_modes):
                if j == ci:
                    resp[j] = census_mags[j] * (1 + 0.02 * np.random.randn())
                else:
                    df = abs(mode_freqs[j] - mode_freqs[ci])
                    coupling = 0.08 * np.exp(-df / 25000)
                    resp[j] = (census_mags[j] * coupling
                               * (1 + 0.05 * np.random.randn()))
            carrier_responses[b] = np.abs(resp)
        print(f"    {n_carriers} simulated responses generated")

    else:
        # Hardware capture
        if not args.port:
            print("ERROR: --port required for hardware (or use --dry-run)")
            sys.exit(1)

        from relay_mux import RelayMux

        print(f"\n  Step 1: Pre-capturing {n_carriers} carrier responses...")
        handle = open_scope()
        mux = RelayMux(port=args.port)
        mux.open()

        relay_ch = PLATE_RELAYS[plate_id][0][0]
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        t0 = time.time()
        for b in range(n_carriers):
            ci = carrier_indices[b]
            drive_freq = mode_freqs[ci]
            print(f"    Carrier {b+1}/{n_carriers}: "
                  f"{drive_freq:.0f} Hz ...", end="", flush=True)
            resp = capture_carrier_response(handle, drive_freq, mode_freqs)
            carrier_responses[b] = resp
            on_res = resp[ci]
            off_vals = [resp[j] for j in range(n_modes) if j != ci]
            off_max = max(off_vals) if off_vals else 0
            print(f" on={on_res:.0f}, off-max={off_max:.0f}, "
                  f"ratio={on_res / (off_max + 1e-10):.1f}×")

        capture_s = time.time() - t0
        awg_off(handle)
        mux.off()
        mux.close()
        close_scope(handle)
        print(f"    Done: {capture_s:.1f}s")

    # Save cache if requested
    if cache_path and not cache_path.exists():
        cache_data = {
            "plate": plate_id,
            "plate_name": name,
            "mode_freqs_hz": mode_freqs,
            "carrier_indices": carrier_indices,
            "n_modes": n_modes,
            "responses": {
                str(b): carrier_responses[b].tolist()
                for b in range(n_carriers)
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "hardware" if not args.dry_run else "simulated",
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
        print(f"    Cache saved: {cache_path}")

    # Print carrier response summary
    print(f"\n  Carrier response matrix ({n_carriers}×{n_modes}):")
    print(f"  {'':>8}", end="")
    for j in range(n_modes):
        print(f"  {mode_freqs[j]/1000:>6.1f}k", end="")
    print()
    for b in range(n_carriers):
        ci = carrier_indices[b]
        print(f"  C{b} {mode_freqs[ci]/1000:>5.1f}k", end="")
        for j in range(n_modes):
            v = carrier_responses[b][j]
            marker = "■" if j == ci else " "
            print(f"  {v:>6.0f}{marker}", end="")
        print()

    # ══════════════════════════════════════════════════════════════
    # Step 2: Backtest each symbol
    # ══════════════════════════════════════════════════════════════

    print(f"\n  Step 2: Downloading price data & backtesting...")
    all_results = {}

    for symbol in symbols:
        print(f"\n{'─'*70}")
        print(f"  {symbol}")
        print(f"{'─'*70}")

        res = backtest_symbol(
            symbol, carrier_responses, mode_freqs, lookback)
        if res:
            all_results[symbol] = res

    # ══════════════════════════════════════════════════════════════
    # Summary
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'═'*70}")
    print(f"  SUMMARY — SN8 VIABILITY ASSESSMENT")
    print(f"{'═'*70}")

    if not all_results:
        print("  No results to summarize.")
        return

    # Per-symbol comparison
    for sym, res in all_results.items():
        binary_acc = res.get("Ridge (binary 7-dim)", {}).get("test_acc", 50)
        plate_accs = {n: m["test_acc"] for n, m in res.items() if "Plate" in n}
        best_plate_name = max(plate_accs, key=plate_accs.get) if plate_accs else "—"
        best_plate_acc = plate_accs.get(best_plate_name, 50)
        delta = best_plate_acc - binary_acc

        bh_ret = res.get("Buy & hold", {}).get("annual_ret_pct", 0)
        plate_ret = res.get(best_plate_name, {}).get("annual_ret_pct", 0)

        print(f"\n  {sym}:")
        print(f"    Binary baseline test acc: {binary_acc:.1f}%")
        print(f"    Best plate test acc:      {best_plate_acc:.1f}% "
              f"({best_plate_name})")
        print(f"    Plate edge over binary:   {delta:+.1f}%")
        print(f"    Buy&hold annual return:   {bh_ret:+.1f}%")
        print(f"    Plate annual return:      {plate_ret:+.1f}%")

    # Global bests
    best_test = 50.0
    best_model = ""
    best_symbol = ""
    best_sharpe = -999
    best_ret = -999
    worst_dd = 0

    for sym, res in all_results.items():
        for mdl, m in res.items():
            if "Plate" in mdl:
                if m["test_acc"] > best_test:
                    best_test = m["test_acc"]
                    best_model = mdl
                    best_symbol = sym
                best_sharpe = max(best_sharpe, m["sharpe"])
                best_ret = max(best_ret, m["annual_ret_pct"])
                worst_dd = max(worst_dd, m["max_dd_pct"])

    print(f"\n  Best plate model: {best_model} on {best_symbol}")
    print(f"  ├─ Test accuracy:   {best_test:.1f}%")
    print(f"  ├─ Best Sharpe:     {best_sharpe:+.2f}")
    print(f"  ├─ Best annual ret: {best_ret:+.1f}%")
    print(f"  ├─ Worst drawdown:  {worst_dd:.1f}%")
    print(f"  └─ SN8 max DD 10%: {'PASS' if worst_dd < 10 else 'FAIL'}")

    # Verdict
    if best_test >= 55:
        verdict = ("PROMISING — plate kernel shows meaningful edge. "
                   "Worth testnet trial on SN8.")
    elif best_test >= 52:
        verdict = ("MARGINAL — small plate edge detected. "
                   "Needs more data, tuning, or richer encoding.")
    else:
        verdict = ("NOT YET VIABLE — plate kernel doesn't improve "
                   "on binary features for this task.")

    sharpe_note = ""
    if best_sharpe > 0.5:
        sharpe_note = ("Sharpe > 0.5 → potentially tradeable. "
                       "Consider SN8 testnet registration (~0.1 TAO).")
    elif best_sharpe > 0:
        sharpe_note = ("Positive Sharpe but < 0.5. "
                       "Signal exists but too weak for live trading yet.")
    else:
        sharpe_note = "Negative Sharpe. Not tradeable in current form."

    print(f"\n  Verdict:  {verdict}")
    print(f"  Trading:  {sharpe_note}")

    # ── Save ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = LAB_DIR / f"trading_backtest_{name}_{timestamp}.json"

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate": name,
        "plate_id": plate_id,
        "n_modes": n_modes,
        "lookback": lookback,
        "carrier_indices": carrier_indices,
        "mode_freqs_hz": mode_freqs,
        "mode": "hardware" if not args.dry_run else "dry_run",
        "symbols": symbols,
        "results": {},
        "verdict": verdict,
        "sharpe_note": sharpe_note,
    }
    for sym, res in all_results.items():
        output["results"][sym] = {}
        for mdl, m in res.items():
            output["results"][sym][mdl] = {
                k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                for k, v in m.items()
            }
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {out_file.name}")


if __name__ == "__main__":
    main()
