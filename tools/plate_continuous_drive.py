#!/usr/bin/env python3
"""
Continuous Amplitude Encoding — The Fix for Binary Information Loss

THE PROBLEM:
  7-bit binary candle encoding maps daily returns to {0, 1}.
  A +0.01% day and a +8% day both map to "1". Information destroyed.
  128 possible patterns → lossy shadow of market state.
  The plate computes perfectly on garbage inputs.

THE FIX:
  Drive each carrier at amplitude ∝ |daily return|, with ±Δf Hz
  frequency offset encoding return direction (up/down).
  This transforms 7 binary inputs into 7 continuous-valued inputs.
  The plate's nonlinear amplitude response (mode saturation, coupling)
  computes on the ACTUAL market data, not a binary shadow.

  8 amplitude levels × 2 directions × 7 carriers ≈ continuous space.
  128 binary patterns → effectively infinite continuous states.

Protocol:
  Phase 1: Calibrate plate D — 7 carriers × 8 amp levels × 2 dirs (~30s)
  Phase 2: Build features for 6 strategies (4 baselines + 2 amplitude)
  Phase 3: Walk-forward + 17bps friction + hold sweep
  Phase 4: Results — does amplitude encoding beat binary?

Usage:
    python plate_continuous_drive.py /dev/cu.usbserial-11310 \\
        --census data/results/lab/plate_exps/plate_census_20260412_180543.json \\
        --cache-d data/results/lab/plate_exps/carrier_cache_D.json
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
import warnings
from datetime import datetime, timezone
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
    download_prices,
    prepare_windows,
    POLY_DEGREE,
)
from plate_trading_validate import (
    apply_friction,
    _metrics_from_strat_returns,
    FRICTION_BPS,
)

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab" / "plate_exps"

# ── Configuration ──
AMP_LEVELS_UV = [
    0,          # level 0: off (|r| < noise threshold)
    200_000,    # level 1: tiny move
    400_000,    # level 2
    700_000,    # level 3
    1_000_000,  # level 4: moderate
    1_400_000,  # level 5
    1_700_000,  # level 6
    2_000_000,  # level 7: large move (full drive)
]
N_AMP_LEVELS = len(AMP_LEVELS_UV)
DETUNING_HZ = 50.0       # ±50 Hz from resonance center for sign encoding
RETURN_SCALE = 0.05       # |return| = 5% maps to full amplitude
N_AVG_CAL = 6             # captures per calibration point


# ══════════════════════════════════════════════════════════════════
# Hardware
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


def awg_drive_at(handle, freq, amp_uv):
    """Drive AWG at specific frequency and amplitude (µVpp)."""
    from picosdk.ps2000 import ps2000
    if amp_uv <= 0 or freq <= 0:
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)
    else:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, int(amp_uv), 0,
            float(freq), float(freq), 0.0, 0.0, 0, 0)


def capture_spectrum(handle, readout_freqs, n_avg=N_AVG_CAL):
    """Capture scope block and return FFT magnitudes at readout freqs."""
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE
    from picosdk.ps2000 import ps2000

    spectra = []
    for _ in range(n_avg):
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
        t_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
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
# Calibration
# ══════════════════════════════════════════════════════════════════

def calibrate(handle, carrier_freqs, mode_freqs):
    """Capture spectral response for each carrier × amplitude × direction.

    Returns dict: (carrier_idx, amp_level_idx, direction) -> ndarray(n_modes)
        direction: 0 = off, +1 = above resonance, -1 = below resonance
    """
    cal = {}
    n_carriers = len(carrier_freqs)
    total = n_carriers * (1 + (N_AMP_LEVELS - 1) * 2)
    done = 0

    for ci in range(n_carriers):
        cf = carrier_freqs[ci]

        # Level 0: AWG off
        awg_drive_at(handle, 0, 0)
        time.sleep(0.05)
        resp = capture_spectrum(handle, mode_freqs)
        cal[(ci, 0, 0)] = resp
        done += 1

        # Non-zero levels × 2 directions
        for ai in range(1, N_AMP_LEVELS):
            amp = AMP_LEVELS_UV[ai]
            for direction in [+1, -1]:
                freq = cf + direction * DETUNING_HZ
                awg_drive_at(handle, freq, amp)
                time.sleep(0.15)
                resp = capture_spectrum(handle, mode_freqs)
                cal[(ci, ai, direction)] = resp
                done += 1

        awg_drive_at(handle, 0, 0)

        print(f"    Carrier {ci+1}/{n_carriers}: "
              f"{done}/{total} captures", flush=True)

    return cal


# ══════════════════════════════════════════════════════════════════
# Return → amplitude level mapping
# ══════════════════════════════════════════════════════════════════

def return_to_level(r):
    """Map |return| to nearest calibration amplitude level index."""
    frac = min(abs(r) / RETURN_SCALE, 1.0)
    target_uv = frac * AMP_LEVELS_UV[-1]
    return int(np.argmin([abs(a - target_uv) for a in AMP_LEVELS_UV]))


# ══════════════════════════════════════════════════════════════════
# Feature builders
# ══════════════════════════════════════════════════════════════════

def build_amp_features(win_rets, calibration, n_modes, n_carriers,
                       use_detuning=True, poly_degree=POLY_DEGREE):
    """Build features from amplitude-encoded calibration lookup.

    Args:
        win_rets: (N, lookback) actual daily returns per window
        calibration: dict from calibrate()
        use_detuning: if True, use ±Δf for direction. If False, use
                      amplitude response only (sign encoded as ±1 × features)
    """
    N = win_rets.shape[0]
    n_c = min(n_carriers, win_rets.shape[1])
    features = []

    for i in range(N):
        day_feats = np.zeros(n_c * n_modes)

        for j in range(n_c):
            r = win_rets[i, j]
            level = return_to_level(r)

            if level == 0:
                resp = calibration.get((j, 0, 0), np.zeros(n_modes))
            elif use_detuning:
                d = +1 if r > 0 else -1
                resp = calibration.get((j, level, d), np.zeros(n_modes))
            else:
                # Amplitude only: average both directions, scale by sign
                rp = calibration.get((j, level, +1), np.zeros(n_modes))
                rn = calibration.get((j, level, -1), np.zeros(n_modes))
                resp = (rp + rn) / 2.0
                # Sign encoded as feature scaling
                if r < 0:
                    resp = resp * -1

            day_feats[j * n_modes:(j + 1) * n_modes] = resp

        # Carrier energies for polynomial expansion
        carrier_energies = np.array([
            day_feats[j * n_modes:(j + 1) * n_modes].sum()
            for j in range(n_c)
        ])
        poly = interaction_expand(carrier_energies, poly_degree)
        features.append(np.concatenate([day_feats, poly]))

    return np.array(features)


def build_binary_plate_features(patterns, carrier_responses, n_modes,
                                win_rets=None, poly_degree=POLY_DEGREE):
    """Build features from binary carrier lookup (existing approach)."""
    N, lookback = patterns.shape
    n_carriers = min(lookback, len(carrier_responses))
    features = []

    for i in range(N):
        row = np.zeros(n_carriers * n_modes)
        for b in range(n_carriers):
            if patterns[i, b] > 0:
                resp = carrier_responses[b].copy()
                if win_rets is not None:
                    resp = resp * abs(win_rets[i, b])
                row[b * n_modes:(b + 1) * n_modes] = resp

        carrier_energies = np.array([
            row[b * n_modes:(b + 1) * n_modes].sum()
            for b in range(n_carriers)
        ])
        poly = interaction_expand(carrier_energies, poly_degree)
        features.append(np.concatenate([row, poly]))

    return np.array(features)


# ══════════════════════════════════════════════════════════════════
# Walk-forward backtest
# ══════════════════════════════════════════════════════════════════

def walk_forward(X, y, label_rets, train_window=120, test_window=20,
                 friction_bps=FRICTION_BPS, hold_days=1):
    """Walk-forward backtest returning net-of-friction metrics."""
    N = len(y)
    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]
    all_preds = np.zeros(N)

    i = 0
    while i + train_window + test_window <= N:
        tr_s, tr_e = i, i + train_window
        te_s, te_e = tr_e, min(tr_e + test_window, N)
        Xtr, ytr = X[tr_s:tr_e], y[tr_s:tr_e]
        Xte = X[te_s:te_e]

        best_alpha, best_acc = 1.0, 0.0
        for a in alpha_grid:
            p_tr, _, _ = ridge_classify(Xtr, ytr, Xte, alpha=a)
            acc = float(np.mean(p_tr == ytr))
            if acc > best_acc:
                best_acc = acc
                best_alpha = a

        _, pred_te, _ = ridge_classify(Xtr, ytr, Xte, alpha=best_alpha)
        for j in range(len(pred_te)):
            if te_s + j < N:
                all_preds[te_s + j] = pred_te[j]
        i += test_window

    if hold_days > 1:
        held = np.zeros(N)
        cur_pos, hold_ctr = 0.0, 0
        for idx in range(N):
            if hold_ctr > 0:
                held[idx] = cur_pos
                hold_ctr -= 1
            elif all_preds[idx] != 0:
                cur_pos = all_preds[idx]
                held[idx] = cur_pos
                hold_ctr = hold_days - 1
        all_preds = held

    strat_ret = apply_friction(all_preds, label_rets, friction_bps)
    m = _metrics_from_strat_returns(strat_ret)
    m["n_trades"] = int(np.sum(np.abs(np.diff(all_preds)) > 0))
    return m


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Continuous amplitude encoding — fix for binary info loss")
    parser.add_argument("port", help="Arduino serial port")
    parser.add_argument("--census", required=True)
    parser.add_argument("--cache-d", default=None,
                        help="Existing binary carrier cache for plate D")
    parser.add_argument("--period", default="2y")
    args = parser.parse_args()

    from relay_mux import RelayMux

    census = load_census(args.census)

    print(f"\n{'═'*70}")
    print(f"  CONTINUOUS AMPLITUDE ENCODING")
    print(f"  The fix: drive amplitude ∝ |return|, ±{DETUNING_HZ}Hz = direction")
    print(f"  {N_AMP_LEVELS} levels: {[f'{a/1e6:.1f}V' for a in AMP_LEVELS_UV]}")
    print(f"  Walk-forward + {FRICTION_BPS}bps friction")
    print(f"{'═'*70}")

    # ── Plate D setup ──
    pid = "4"
    rkey = f"{pid}_NE"
    mode_freqs = get_plate_modes(census, pid, relay_key=rkey)
    n_modes = len(mode_freqs)
    n_carriers = min(7, n_modes)
    carrier_indices = np.linspace(0, n_modes - 1, n_carriers, dtype=int)
    carrier_freqs = [mode_freqs[ci] for ci in carrier_indices]

    print(f"\n  Plate D: {n_modes} modes, {n_carriers} carriers")
    print(f"  Carriers: {[int(f) for f in carrier_freqs]} Hz")
    print(f"  Detuning: ±{DETUNING_HZ} Hz from resonance (sign encoding)")

    # ── Load binary carrier cache ──
    binary_carriers = None
    if args.cache_d:
        cp = Path(args.cache_d)
        if cp.exists():
            with open(cp) as f:
                cd = json.load(f)
            binary_carriers = {
                b: np.array(cd["responses"][str(b)])
                for b in range(len(cd["responses"]))
            }
            print(f"  Binary carriers loaded from cache ({len(binary_carriers)})")

    # ══════════════════════════════════════════════════════════
    # PHASE 1: AMPLITUDE CALIBRATION
    # ══════════════════════════════════════════════════════════

    n_captures = n_carriers * (1 + (N_AMP_LEVELS - 1) * 2)
    print(f"\n{'━'*70}")
    print(f"  PHASE 1: AMPLITUDE CALIBRATION")
    print(f"  {n_carriers} carriers × {N_AMP_LEVELS} levels × 2 dirs = {n_captures} captures")
    print(f"{'━'*70}")

    handle = open_scope()
    mux = RelayMux(port=args.port)
    mux.open()

    relay_ch = PLATE_RELAYS[pid][0][0]
    mux.select(relay_ch)
    time.sleep(0.15)

    t0 = time.time()
    cal = calibrate(handle, carrier_freqs, mode_freqs)
    dt_cal = time.time() - t0

    awg_drive_at(handle, 0, 0)
    mux.off()
    mux.close()
    close_scope(handle)

    print(f"\n  Done: {len(cal)} captures in {dt_cal:.1f}s")

    # ── Amplitude response analysis ──
    print(f"\n  Amplitude response curve (carrier 0):")
    print(f"  {'Level':>5} {'Amp':>8} {'Mode0(+)':>10} {'Mode0(-)':>10} "
          f"{'Asym':>6} {'AllModes(+)':>12}")
    for ai in range(N_AMP_LEVELS):
        amp = AMP_LEVELS_UV[ai]
        amp_str = f"{amp/1e6:.2f}V"
        if ai == 0:
            r = cal.get((0, 0, 0), np.zeros(n_modes))
            print(f"  {ai:>5} {amp_str:>8} {r[0]:>10,.0f} {'--':>10} "
                  f"{'--':>6} {np.sum(r):>12,.0f}")
        else:
            rp = cal.get((0, ai, +1), np.zeros(n_modes))
            rn = cal.get((0, ai, -1), np.zeros(n_modes))
            asym = rp[0] / (rn[0] + 1e-10)
            print(f"  {ai:>5} {amp_str:>8} {rp[0]:>10,.0f} {rn[0]:>10,.0f} "
                  f"{asym:>6.3f} {np.sum(rp):>12,.0f}")

    # Nonlinearity check
    r1 = cal.get((0, 1, +1), np.zeros(n_modes))
    r7 = cal.get((0, N_AMP_LEVELS - 1, +1), np.zeros(n_modes))
    amp_ratio = AMP_LEVELS_UV[-1] / max(AMP_LEVELS_UV[1], 1)
    resp_ratio = np.mean(r7) / (np.mean(r1) + 1e-10)
    lin_ratio = resp_ratio / amp_ratio
    print(f"\n  Linearity: amp×{amp_ratio:.0f}, resp×{resp_ratio:.1f}, "
          f"ratio={lin_ratio:.2f}")
    if abs(lin_ratio - 1.0) > 0.15:
        print(f"  → NONLINEAR (plate adds {abs(lin_ratio-1)*100:.0f}% "
              f"{'compression' if lin_ratio < 1 else 'expansion'})")
    else:
        print(f"  → Nearly linear in amplitude")

    # Direction asymmetry check
    asym_scores = []
    for ci in range(n_carriers):
        for ai in range(1, N_AMP_LEVELS):
            rp = cal.get((ci, ai, +1), np.zeros(n_modes))
            rn = cal.get((ci, ai, -1), np.zeros(n_modes))
            if np.sum(rn) > 0:
                asym_scores.append(np.sum(rp) / np.sum(rn))
    mean_asym = np.mean(asym_scores)
    std_asym = np.std(asym_scores)
    print(f"  Direction asymmetry: mean={mean_asym:.3f} ±{std_asym:.3f}")
    if std_asym > 0.02:
        print(f"  → DIRECTION ENCODING WORKS (±{DETUNING_HZ}Hz produces "
              f"different responses)")
    else:
        print(f"  → Weak direction effect (detuning may not add value)")

    # ══════════════════════════════════════════════════════════
    # PHASE 2: DOWNLOAD + BUILD FEATURES
    # ══════════════════════════════════════════════════════════

    print(f"\n{'━'*70}")
    print(f"  PHASE 2: FEATURES + BACKTEST")
    print(f"{'━'*70}")

    warnings.filterwarnings("ignore")
    print(f"\n  Downloading BTC-USD ({args.period})...", end=" ", flush=True)
    df = download_prices("BTC-USD", period=args.period)
    close = df["Close"].values.flatten().astype(np.float64)
    open_ = df["Open"].values.flatten().astype(np.float64)
    print(f"{len(close)} days")

    lookback = 7
    patterns, labels, win_rets, label_rets = prepare_windows(
        close, open_, lookback)
    N = len(labels)
    print(f"  {N} windows, {N_AMP_LEVELS} amplitude levels")

    # Show return distribution vs amplitude levels
    all_abs_ret = np.abs(win_rets.flatten())
    print(f"\n  Return → amplitude level distribution:")
    for ai in range(N_AMP_LEVELS):
        lo = AMP_LEVELS_UV[ai]
        hi = AMP_LEVELS_UV[ai + 1] if ai + 1 < N_AMP_LEVELS else 999999999
        lo_r = lo / AMP_LEVELS_UV[-1] * RETURN_SCALE if ai > 0 else 0
        hi_r = hi / AMP_LEVELS_UV[-1] * RETURN_SCALE
        count = np.sum((all_abs_ret >= lo_r) & (all_abs_ret < hi_r))
        pct = count / len(all_abs_ret) * 100
        print(f"    Level {ai}: |r| ∈ [{lo_r*100:.1f}%, {hi_r*100:.1f}%) "
              f"→ {AMP_LEVELS_UV[ai]/1e6:.2f}V  ({pct:.1f}%)")

    # ── Build feature matrices ──
    print(f"\n  Building features...")

    # 1. Binary + polynomial (no plate)
    X_bin_poly = np.array([
        np.concatenate([p.astype(float),
                        interaction_expand(p.astype(float), POLY_DEGREE)])
        for p in patterns
    ])

    # 2. Raw returns + polynomial (no plate — tests if magnitude alone helps)
    X_raw_poly = np.array([
        np.concatenate([win_rets[i, :lookback],
                        interaction_expand(win_rets[i, :lookback], POLY_DEGREE)])
        for i in range(N)
    ])

    # 3. Binary plate D (return-weighted, current best)
    X_bin_plate = None
    if binary_carriers:
        X_bin_plate = build_binary_plate_features(
            patterns, binary_carriers, n_modes, win_rets=win_rets)

    # 4. Amplitude-encoded plate (no detuning — tests amplitude nonlinearity)
    X_amp = build_amp_features(
        win_rets, cal, n_modes, n_carriers, use_detuning=False)

    # 5. Amplitude + detuning plate (full physics encoding)
    X_amp_det = build_amp_features(
        win_rets, cal, n_modes, n_carriers, use_detuning=True)

    # 6. Combined: raw returns + amplitude-detuned plate
    X_combined = np.hstack([X_raw_poly, X_amp_det])

    print(f"  Feature dimensions:")
    print(f"    Binary + poly (no plate):    {X_bin_poly.shape[1]}")
    print(f"    Raw returns + poly:          {X_raw_poly.shape[1]}")
    if X_bin_plate is not None:
        print(f"    Binary plate D (rw+poly):    {X_bin_plate.shape[1]}")
    print(f"    Amp-encoded plate:           {X_amp.shape[1]}")
    print(f"    Amp + detuning plate:        {X_amp_det.shape[1]}")
    print(f"    Combined (raw + amp+det):    {X_combined.shape[1]}")

    # ── Walk-forward backtests ──
    strategies = [
        ("Binary+poly (no plate)", X_bin_poly),
        ("Raw returns+poly (no plate)", X_raw_poly),
    ]
    if X_bin_plate is not None:
        strategies.append(("Binary plate D (rw+poly)", X_bin_plate))
    strategies.extend([
        ("Amp-encoded plate D", X_amp),
        ("Amp+detuning plate D", X_amp_det),
        ("Combined raw+amp+det", X_combined),
    ])

    hold_sweep = [1, 3, 5]
    print(f"\n  Running walk-forward backtests "
          f"({len(strategies)} strategies × {len(hold_sweep)} holds)...")

    all_results = []
    for name, X in strategies:
        for hold in hold_sweep:
            m = walk_forward(X, labels, label_rets,
                             friction_bps=FRICTION_BPS, hold_days=hold)
            tag = f"{name} hold={hold}d"
            all_results.append((tag, m))
            print(f"    {tag:<45} Sharpe={m['sharpe']:+.2f}", flush=True)

    # ══════════════════════════════════════════════════════════
    # RESULTS
    # ══════════════════════════════════════════════════════════

    print(f"\n{'═'*70}")
    print(f"  RESULTS — CONTINUOUS vs BINARY ENCODING")
    print(f"  (walk-forward + {FRICTION_BPS}bps friction)")
    print(f"{'═'*70}")

    print(f"\n  {'Strategy':<45} {'Sharpe':>7} {'Ret%':>8} {'MaxDD%':>7}")
    print(f"  {'─'*70}")

    best_sharpe = -999
    best_name = ""
    for name, m in all_results:
        tag = ""
        if m["sharpe"] > best_sharpe:
            best_sharpe = m["sharpe"]
            best_name = name
            tag = " ◄"
        print(f"  {name:<45} {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}%{tag}")

    # Best per strategy
    print(f"\n  ── Best Hold Per Strategy ──")
    for sname, X in strategies:
        best_m, best_h = None, 0
        for name, m in all_results:
            if name.startswith(sname):
                if best_m is None or m["sharpe"] > best_m["sharpe"]:
                    best_m = m
                    best_h = int(name.split("hold=")[1].replace("d", ""))
        if best_m:
            print(f"  {sname:<40} hold={best_h}d  "
                  f"Sharpe={best_m['sharpe']:+.2f}  "
                  f"ret={best_m['total_ret_pct']:+.1f}%  "
                  f"maxDD={best_m['max_dd_pct']:.1f}%")

    print(f"\n  Overall best: {best_name} (Sharpe={best_sharpe:+.2f})")

    # ── Key comparisons at 3-day hold ──
    print(f"\n  ── Key Comparisons (3-day hold) ──")
    r3 = {n: m for n, m in all_results if "hold=3d" in n}

    def get_sharpe(prefix):
        for k, v in r3.items():
            if k.startswith(prefix):
                return v["sharpe"]
        return float("nan")

    s_bin = get_sharpe("Binary+poly")
    s_raw = get_sharpe("Raw returns")
    s_binp = get_sharpe("Binary plate")
    s_amp = get_sharpe("Amp-encoded")
    s_ampd = get_sharpe("Amp+detuning")
    s_comb = get_sharpe("Combined")

    comparisons = [
        ("Does magnitude info help?",
         f"Raw returns vs binary (no plate): {s_raw - s_bin:+.2f}"),
        ("Does the plate add value to binary?",
         f"Binary plate vs binary no-plate: {s_binp - s_bin:+.2f}"),
        ("Does amplitude encoding beat binary plate?",
         f"Amp plate vs binary plate: {s_amp - s_binp:+.2f}"),
        ("Does detuning (sign encoding) help?",
         f"Amp+det vs amp-only: {s_ampd - s_amp:+.2f}"),
        ("Does the plate add nonlinearity beyond raw returns?",
         f"Amp+det plate vs raw returns: {s_ampd - s_raw:+.2f}"),
        ("Does combining software + hardware help?",
         f"Combined vs amp+det alone: {s_comb - s_ampd:+.2f}"),
    ]
    for q, a in comparisons:
        print(f"  Q: {q}")
        print(f"  A: {a}")
        print()

    # ── Save ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = LAB_DIR / f"continuous_encoding_{timestamp}.json"

    cal_ser = {
        f"{ci}_{ai}_{d}": resp.tolist()
        for (ci, ai, d), resp in cal.items()
    }

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "continuous_amplitude_encoding",
        "amp_levels_uv": AMP_LEVELS_UV,
        "detuning_hz": DETUNING_HZ,
        "return_scale": RETURN_SCALE,
        "carrier_freqs_hz": [float(f) for f in carrier_freqs],
        "mode_freqs_hz": [float(f) for f in mode_freqs],
        "n_modes": n_modes,
        "n_carriers": n_carriers,
        "calibration_time_s": dt_cal,
        "n_calibration_points": len(cal),
        "linearity_ratio": float(lin_ratio),
        "direction_asymmetry_mean": float(mean_asym),
        "direction_asymmetry_std": float(std_asym),
        "calibration": cal_ser,
        "results": {
            name: {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                   for k, v in m.items()}
            for name, m in all_results
        },
        "best": best_name,
        "best_sharpe": float(best_sharpe),
    }
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved: {out_file.name}")


if __name__ == "__main__":
    main()
