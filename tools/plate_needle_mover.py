#!/usr/bin/env python3
"""
Move-The-Needle Hardware Test — Two Physics-Based Upgrades

EXPERIMENT A: 5-Plate Ensemble
  Each plate is a different random projection of the input.
  Concatenating 5 plates' spectral features = 5 independent reservoir computers.
  This is the #1 proven technique in reservoir computing literature.

EXPERIMENT B: Ring-Down Interference
  Instead of driving each carrier to steady state (150ms settle + capture),
  drive 2ms bursts in rapid succession. Each capture sees the current carrier
  PLUS ring-down tails from ALL previous carriers. The temporal overlap
  creates genuine physical cross-mode coupling that can't be replicated
  by polynomial expansion on sequential features.

Both experiments use walk-forward validation with 17bps friction.

Usage:
    python plate_needle_mover.py /dev/cu.usbserial-11310 \\
        --census data/results/lab/plate_exps/plate_census_20260412_180543.json
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
from plate_trading_backtest import (
    interaction_expand,
    ridge_classify,
    compute_metrics,
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


# ══════════════════════════════════════════════════════════════════
# Hardware capture
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


def awg_drive(handle, freq):
    """Start AWG at frequency (Hz). Pass 0 to turn off."""
    from picosdk.ps2000 import ps2000
    if freq <= 0:
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)
    else:
        from cwm_picoscope import AWG_DRIVE_UVPP
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq), float(freq), 0.0, 0.0, 0, 0)


def capture_spectrum(handle, readout_freqs, n_avg=1):
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
# Feature builders
# ══════════════════════════════════════════════════════════════════

def build_plate_features(patterns, carrier_responses, n_modes,
                         weight_matrix=None, poly_degree=4):
    """Build plate spectral features with polynomial expansion."""
    N, lookback = patterns.shape
    n_carriers = min(lookback, len(carrier_responses))

    X_raw = np.zeros((N, n_carriers * n_modes))
    poly_list = []

    for i in range(N):
        for b in range(n_carriers):
            if patterns[i, b] > 0:
                resp = carrier_responses[b].copy()
                if weight_matrix is not None:
                    resp = resp * abs(weight_matrix[i, b])
                X_raw[i, b * n_modes:(b + 1) * n_modes] = resp

        carrier_energies = np.array([
            X_raw[i, b * n_modes:(b + 1) * n_modes].sum()
            for b in range(n_carriers)
        ])
        poly_terms = interaction_expand(carrier_energies, poly_degree)
        poly_list.append(np.concatenate([X_raw[i], poly_terms]))

    return np.array(poly_list)


def build_ringdown_features(patterns, ringdown_cache, n_modes,
                            weight_matrix=None, poly_degree=4):
    """Build features from ring-down interference captures.

    ringdown_cache: dict[pattern_tuple] -> ndarray(7, n_modes)
        Each entry is 7 progressive captures for that pattern.
    """
    N, lookback = patterns.shape
    n_carriers = min(lookback, 7)

    X_list = []
    for i in range(N):
        pat = tuple(patterns[i])
        if pat in ringdown_cache:
            # 7 captures × n_modes = progressive ring-down features
            rd = ringdown_cache[pat]  # (7, n_modes)
            flat = rd.flatten()  # 7 × n_modes

            if weight_matrix is not None:
                # Weight each carrier's capture by its return magnitude
                for b in range(n_carriers):
                    flat[b * n_modes:(b + 1) * n_modes] *= abs(weight_matrix[i, b])

            # Carrier energies for polynomial
            carrier_energies = np.array([
                flat[b * n_modes:(b + 1) * n_modes].sum()
                for b in range(n_carriers)
            ])
            poly_terms = interaction_expand(carrier_energies, poly_degree)
            X_list.append(np.concatenate([flat, poly_terms]))
        else:
            # Pattern not captured — use zeros
            n_feat = n_carriers * n_modes
            poly_terms = interaction_expand(np.zeros(n_carriers), poly_degree)
            X_list.append(np.concatenate([np.zeros(n_feat), poly_terms]))

    return np.array(X_list)


def build_ensemble_features(patterns, all_plate_carriers, all_n_modes,
                            weight_matrix=None, poly_degree=3):
    """Build concatenated features from multiple plates.

    all_plate_carriers: list of dicts, one per plate
    all_n_modes: list of int, modes per plate
    poly_degree: reduced to limit dimensionality with more plates
    """
    N = patterns.shape[0]
    plate_features = []

    for carriers, n_modes in zip(all_plate_carriers, all_n_modes):
        n_carriers = min(patterns.shape[1], len(carriers))
        X = build_plate_features(
            patterns, carriers, n_modes,
            weight_matrix=weight_matrix,
            poly_degree=poly_degree)
        plate_features.append(X)

    return np.hstack(plate_features)


# ══════════════════════════════════════════════════════════════════
# Walk-forward with gating
# ══════════════════════════════════════════════════════════════════

def walk_forward_backtest(X, y, label_rets, train_window=120,
                          test_window=20, friction_bps=FRICTION_BPS,
                          hold_days=1):
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

    # Apply friction
    strat_ret = apply_friction(all_preds, label_rets, friction_bps)
    m = _metrics_from_strat_returns(strat_ret)

    n_changes = int(np.sum(np.abs(np.diff(all_preds)) > 0))
    m["n_position_changes"] = n_changes
    m["exposure_pct"] = np.mean(all_preds != 0) * 100

    return m, all_preds, strat_ret


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Move-the-needle hardware test — 5-plate ensemble + ring-down")
    parser.add_argument("port", help="Arduino serial port")
    parser.add_argument("--census", required=True)
    parser.add_argument("--cache-d", default=None,
                        help="Existing plate D carrier cache (skip re-capture)")
    parser.add_argument("--period", default="2y")
    args = parser.parse_args()

    from relay_mux import RelayMux

    census = load_census(args.census)

    print(f"\n{'═'*74}")
    print(f"  MOVE-THE-NEEDLE HARDWARE TEST")
    print(f"  Exp A: 5-plate ensemble reservoir")
    print(f"  Exp B: Ring-down interference drive")
    print(f"  All with walk-forward + 17 bps friction + 3-day hold")
    print(f"{'═'*74}")

    # ══════════════════════════════════════════════════════════════
    # PHASE 1: Capture carrier responses for ALL 5 plates
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  PHASE 1: 5-PLATE CARRIER CAPTURE")
    print(f"{'━'*74}")

    handle = open_scope()
    mux = RelayMux(port=args.port)
    mux.open()

    # Load plate D cache if available
    plate_d_cache = None
    if args.cache_d:
        cache_path = Path(args.cache_d)
        if cache_path.exists():
            with open(cache_path) as f:
                plate_d_cache = json.load(f)
            print(f"  Loaded plate D cache from {cache_path.name}")

    all_plate_carriers = {}  # pid -> {carrier_idx: response_array}
    all_plate_modes = {}     # pid -> list of mode freqs
    all_plate_n_modes = {}   # pid -> int

    t0_total = time.time()

    for pid in ["1", "2", "3", "4", "5"]:
        name = PLATE_NAMES[pid]
        relay_ch = PLATE_RELAYS[pid][0][0]
        rkey = f"{pid}_NE" if len(PLATE_RELAYS[pid]) > 1 else pid
        mode_freqs = get_plate_modes(census, pid, relay_key=rkey)
        n_modes = len(mode_freqs)

        if n_modes < 3:
            print(f"  Plate {name}: only {n_modes} modes — skipping")
            continue

        all_plate_modes[pid] = mode_freqs
        all_plate_n_modes[pid] = n_modes

        # Use cache for plate D if available
        if pid == "4" and plate_d_cache:
            n_c = len(plate_d_cache["responses"])
            carriers = {}
            for b in range(n_c):
                carriers[b] = np.array(plate_d_cache["responses"][str(b)])
            all_plate_carriers[pid] = carriers
            print(f"  Plate {name}: {n_modes} modes, {n_c} carriers (from cache)")
            continue

        # Capture carriers for this plate
        n_carriers = min(7, n_modes)
        carrier_indices = np.linspace(0, n_modes - 1, n_carriers, dtype=int).tolist()

        print(f"  Plate {name}: relay={relay_ch}, {n_modes} modes, "
              f"capturing {n_carriers} carriers...", end="", flush=True)

        mux.select(relay_ch)
        time.sleep(0.15)

        carriers = {}
        t0 = time.time()
        for b in range(n_carriers):
            ci = carrier_indices[b]
            drive_freq = mode_freqs[ci]
            awg_drive(handle, drive_freq)
            time.sleep(0.15)
            resp = capture_spectrum(handle, mode_freqs, n_avg=6)
            carriers[b] = resp

        awg_drive(handle, 0)
        dt = time.time() - t0
        all_plate_carriers[pid] = carriers

        # Quick summary
        on_vals = [carriers[b][carrier_indices[b]] for b in range(n_carriers)]
        print(f" {dt:.1f}s, on-res={np.mean(on_vals):.0f}")

    # ══════════════════════════════════════════════════════════════
    # PHASE 2: Ring-Down Interference Capture (Plate D only)
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  PHASE 2: RING-DOWN INTERFERENCE CAPTURE (Plate D)")
    print(f"{'━'*74}")

    pid_rd = "4"
    mode_freqs_d = all_plate_modes[pid_rd]
    n_modes_d = all_plate_n_modes[pid_rd]
    n_carriers_d = min(7, n_modes_d)
    carrier_indices_d = np.linspace(0, n_modes_d - 1, n_carriers_d, dtype=int).tolist()
    carrier_freqs_d = [mode_freqs_d[ci] for ci in carrier_indices_d]

    BURST_MS = 2  # ms per carrier burst
    N_AVG_RD = 4  # averages per pattern

    # Select plate D relay
    relay_ch_d = PLATE_RELAYS[pid_rd][0][0]
    mux.select(relay_ch_d)
    time.sleep(0.15)

    # Capture all 128 7-bit patterns
    ringdown_cache = {}  # pattern_tuple -> (7, n_modes)

    print(f"  Capturing 128 patterns × {n_carriers_d} bursts × {N_AVG_RD} avg...")
    print(f"  Burst: {BURST_MS}ms drive, immediate capture (no settle)")

    t0_rd = time.time()
    for pat_int in range(2**n_carriers_d):
        pattern = [(pat_int >> b) & 1 for b in range(n_carriers_d)]
        pat_tuple = tuple(pattern)

        captures_accum = np.zeros((n_carriers_d, n_modes_d))

        for avg in range(N_AVG_RD):
            # Ensure clean start: AWG off, brief pause
            awg_drive(handle, 0)
            time.sleep(0.005)

            captures = np.zeros((n_carriers_d, n_modes_d))

            for b in range(n_carriers_d):
                if pattern[b]:
                    # Drive this carrier for BURST_MS milliseconds
                    awg_drive(handle, carrier_freqs_d[b])
                    time.sleep(BURST_MS / 1000.0)
                else:
                    # No drive — but still wait for timing consistency
                    awg_drive(handle, 0)
                    time.sleep(BURST_MS / 1000.0)

                # Capture immediately (AWG still on if bit was 1)
                # This capture sees: current carrier + ring-down from all previous
                resp = capture_spectrum(handle, mode_freqs_d, n_avg=1)
                captures[b] = resp

            captures_accum += captures

        ringdown_cache[pat_tuple] = captures_accum / N_AVG_RD

        if (pat_int + 1) % 32 == 0:
            elapsed = time.time() - t0_rd
            eta = elapsed / (pat_int + 1) * (128 - pat_int - 1)
            print(f"    {pat_int+1}/128 patterns ({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)")

    dt_rd = time.time() - t0_rd
    awg_drive(handle, 0)

    print(f"  Done: {len(ringdown_cache)} patterns in {dt_rd:.1f}s "
          f"({dt_rd/128:.2f}s/pattern)")

    # Cleanup hardware
    mux.off()
    mux.close()
    close_scope(handle)

    total_hw = time.time() - t0_total
    print(f"\n  Total hardware time: {total_hw:.1f}s")

    # Quick ring-down analysis: check if captures differ from sequential
    # Compare pattern (1,1,1,1,1,1,1) capture 6 vs sequential carrier 6
    all_on = tuple([1] * n_carriers_d)
    if all_on in ringdown_cache:
        rd_c6 = ringdown_cache[all_on][6]  # last capture, all-on
        seq_c6 = all_plate_carriers["4"][6]  # sequential carrier 6
        print(f"\n  Ring-down vs Sequential (pattern=all-on, carrier 6):")
        for j in range(n_modes_d):
            r = rd_c6[j] / (seq_c6[j] + 1e-10)
            marker = "◄ DRIVEN" if j == carrier_indices_d[6] else ""
            print(f"    mode {j}: RD={rd_c6[j]:>10.0f}  "
                  f"SEQ={seq_c6[j]:>10.0f}  ratio={r:.3f}  {marker}")

    # ══════════════════════════════════════════════════════════════
    # PHASE 3: Download data + build features
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'━'*74}")
    print(f"  PHASE 3: FEATURE CONSTRUCTION + BACKTEST")
    print(f"{'━'*74}")

    warnings.filterwarnings("ignore")
    print(f"\n  Downloading BTC-USD ({args.period})...", end=" ", flush=True)
    df = download_prices("BTC-USD", period=args.period)
    close = df["Close"].values.flatten().astype(np.float64)
    open_ = df["Open"].values.flatten().astype(np.float64)
    print(f"{len(close)} days")

    lookback = 7
    patterns, labels, win_rets, label_rets = prepare_windows(close, open_, lookback)
    N = len(labels)
    print(f"  {N} windows")

    # ── Feature matrices ──

    # 1) Single plate D, sequential (baseline)
    print(f"  Building features...", flush=True)
    carriers_d = all_plate_carriers["4"]
    X_seq = build_plate_features(
        patterns, carriers_d, n_modes_d, weight_matrix=win_rets)

    # 2) Single plate D, ring-down interference
    X_rd = build_ringdown_features(
        patterns, ringdown_cache, n_modes_d, weight_matrix=win_rets)

    # 3) 5-plate ensemble (sequential carriers from all plates)
    # Use 7 carriers per plate, pad smaller plates
    ensemble_carriers = []
    ensemble_n_modes = []
    for pid in sorted(all_plate_carriers.keys()):
        ensemble_carriers.append(all_plate_carriers[pid])
        ensemble_n_modes.append(all_plate_n_modes[pid])

    n_plates = len(ensemble_carriers)

    X_ens = build_ensemble_features(
        patterns, ensemble_carriers, ensemble_n_modes,
        weight_matrix=win_rets, poly_degree=3)

    # 4) 5-plate ensemble + ring-down on plate D
    # Concatenate ensemble sequential features with ring-down features
    X_ens_rd = np.hstack([X_ens, X_rd])

    print(f"  Feature dimensions:")
    print(f"    Sequential (1 plate):    {X_seq.shape[1]}")
    print(f"    Ring-down (1 plate):     {X_rd.shape[1]}")
    print(f"    Ensemble ({n_plates} plates):     {X_ens.shape[1]}")
    print(f"    Ensemble + ring-down:    {X_ens_rd.shape[1]}")

    # Also build a pure binary baseline (no plate)
    X_bin = patterns.astype(float)
    X_bin_poly = np.array([
        np.concatenate([p, interaction_expand(p, POLY_DEGREE)])
        for p in X_bin
    ])

    # ── Run backtests ──
    print(f"\n  Running walk-forward backtests (120d train, 20d test, 17bps, 3d hold)...")

    strategies = [
        ("Binary+poly (no plate)", X_bin_poly),
        ("Seq plate D (rw+poly)", X_seq),
        ("Ring-down D (rw+poly)", X_rd),
        (f"Ensemble {n_plates}P (rw+poly)", X_ens),
        (f"Ensemble {n_plates}P + ringdown", X_ens_rd),
    ]

    # Also try different hold periods for the best model
    hold_days_sweep = [1, 3, 5]

    all_results = []
    for name, X in strategies:
        for hold in hold_days_sweep:
            m, preds, sret = walk_forward_backtest(
                X, labels, label_rets,
                friction_bps=FRICTION_BPS, hold_days=hold)
            tag = f"{name} hold={hold}d"
            all_results.append((tag, m))

    # ══════════════════════════════════════════════════════════════
    # PHASE 4: Results
    # ══════════════════════════════════════════════════════════════

    print(f"\n{'═'*74}")
    print(f"  RESULTS — ALL STRATEGIES (walk-forward + 17bps friction)")
    print(f"{'═'*74}")

    print(f"\n  {'Strategy':<40} {'Sharpe':>7} {'Ret%':>8} {'MaxDD%':>7} "
          f"{'WinR%':>6} {'Trades':>7}")
    print(f"  {'─'*78}")

    best_sharpe = -999
    best_name = ""
    for name, m in all_results:
        trades = m.get("n_position_changes", 0)
        tag = ""
        if m["sharpe"] > best_sharpe:
            best_sharpe = m["sharpe"]
            best_name = name
            tag = " ◄"
        print(f"  {name:<40} {m['sharpe']:>+6.2f} "
              f"{m['total_ret_pct']:>+7.1f}% {m['max_dd_pct']:>6.1f}% "
              f"{m['win_rate_pct']:>5.1f}% {trades:>7}{tag}")

    # Summary by strategy (best hold per strategy)
    print(f"\n  ── Best Hold Per Strategy ──")
    for sname, X in strategies:
        best_m = None
        best_h = 0
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

    # Improvement analysis
    print(f"\n  ── Improvement Over Baseline ──")
    base_sharpe = None
    for name, m in all_results:
        if "Binary" in name and "hold=3" in name:
            base_sharpe = m["sharpe"]
            break

    seq_sharpe = None
    for name, m in all_results:
        if "Seq plate D" in name and "hold=3" in name:
            seq_sharpe = m["sharpe"]
            break

    if base_sharpe is not None:
        for name, m in all_results:
            if "hold=3" in name:
                delta_b = m["sharpe"] - base_sharpe
                delta_s = m["sharpe"] - (seq_sharpe or 0)
                print(f"    {name:<40} vs binary: {delta_b:+.2f}  "
                      f"vs seq-D: {delta_s:+.2f}")

    # SN8 viability
    print(f"\n  ── SN8 Viability ──")
    viable = False
    for name, m in all_results:
        if m["sharpe"] > 0.5 and m["max_dd_pct"] < 15:
            print(f"  ✓ {name}: Sharpe={m['sharpe']:+.2f} DD={m['max_dd_pct']:.1f}%")
            viable = True
    if not viable:
        print(f"  No strategy passes Sharpe>0.5 AND DD<15%")
        # Show closest
        closest = max(all_results, key=lambda x: x[1]["sharpe"])
        print(f"  Closest: {closest[0]} Sharpe={closest[1]['sharpe']:+.2f} "
              f"DD={closest[1]['max_dd_pct']:.1f}%")

    # ── Save ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = LAB_DIR / f"needle_mover_{timestamp}.json"

    # Save carrier caches for all plates
    carrier_caches = {}
    for pid in all_plate_carriers:
        nm = PLATE_NAMES[pid]
        carrier_caches[nm] = {
            "mode_freqs_hz": all_plate_modes[pid],
            "n_modes": all_plate_n_modes[pid],
            "responses": {
                str(b): all_plate_carriers[pid][b].tolist()
                for b in all_plate_carriers[pid]
            }
        }

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plates_used": [PLATE_NAMES[pid] for pid in all_plate_carriers],
        "n_plates": n_plates,
        "ringdown_patterns": len(ringdown_cache),
        "burst_ms": BURST_MS,
        "n_avg_ringdown": N_AVG_RD,
        "hardware_time_s": total_hw,
        "results": {
            name: {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                   for k, v in m.items()}
            for name, m in all_results
        },
        "best": best_name,
        "best_sharpe": float(best_sharpe),
        "carrier_caches": carrier_caches,
    }
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {out_file.name}")

    # Save ring-down cache separately (large)
    rd_file = LAB_DIR / f"ringdown_cache_D_{timestamp}.json"
    rd_data = {
        "plate": "D",
        "mode_freqs_hz": mode_freqs_d,
        "carrier_freqs_hz": carrier_freqs_d,
        "burst_ms": BURST_MS,
        "n_avg": N_AVG_RD,
        "patterns": {
            str(list(k)): v.tolist()
            for k, v in ringdown_cache.items()
        }
    }
    with open(rd_file, "w") as f:
        json.dump(rd_data, f, indent=2)
    print(f"  Ring-down cache saved: {rd_file.name}")


if __name__ == "__main__":
    main()
