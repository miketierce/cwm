#!/usr/bin/env python3
"""
NARMA-10 Temporal Memory Demonstration — Time-Sliced Ringdown Capture

Goal: Show that the plate's physical ringdown carries useful information
      from the PREVIOUS step, demonstrating genuine temporal memory.

Architecture:
  Pre-arm PicoScope capture → change DDS → capture catches the transition.
  The ~10.3 ms capture window contains:
    - First ~3 ms: old drive still active (DDS update in progress)
    - Next ~3 ms: new drive + old mode ringdown (τ ≈ 2 ms)
    - Final ~4 ms: new drive steady state (old modes decayed)

  Split each capture into N_SLICES time windows, FFT each independently.
  Early slices encode the previous step's drive configuration.
  If early slices improve prediction → physical temporal memory demonstrated.

Carrier sets (from Volterra):
  Pass 1: 11 carriers (10u + y(t)) — baseline
  Pass 2: 12 carriers (10u + y(t) + y_sum@16kHz) — Volterra

Key demonstration:
  Compare NMSE(late_slices) vs NMSE(all_slices).
  If all < late, early slices contributed memory.

Usage:
  DYLD_LIBRARY_PATH="/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources" \\
  python tools/narma_hw_temporal.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_cross_20260418_142222.json \\
      [--steps 1000] [--all-open] [--n-slices 5]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import KFold

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
ROOT = TOOLS_DIR.parent
RESULTS_DIR = ROOT / "data" / "results" / "lab" / "plate_exps" / "narma10"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════

NARMA_ORDER = 10
N_WASHOUT = 50

AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096

RIDGE_ALPHAS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

# 10 input carriers (delay-line: carrier k = u(t-9+k))
INPUT_CARRIERS_HZ = [
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]
FEEDBACK_FREQ = 53_900
Y_HISTORY_FREQ = 16_000

CARRIERS_11 = INPUT_CARRIERS_HZ + [FEEDBACK_FREQ]
CARRIERS_12 = INPUT_CARRIERS_HZ + [FEEDBACK_FREQ, Y_HISTORY_FREQ]

# Readout bins: mode clusters + IM products
MODE_CLUSTERS_HZ = [
    11_425, 15_100, 16_000, 17_375, 19_000, 23_900, 29_200, 29_900,
    31_600, 33_225, 34_550, 36_000, 37_000, 42_300, 45_000, 47_800,
    49_600, 51_500, 53_900, 56_200, 58_500, 62_000, 65_075, 68_200,
    70_800, 73_500, 76_200, 78_800, 81_500, 84_200, 86_900, 89_400,
    95_000,
]
FEEDBACK_IM_HZ = [
    2_300, 4_300, 4_500, 4_600, 5_900, 6_100, 8_900,
    16_900, 20_100, 24_700,
    98_900, 103_500, 110_100, 112_400,
]
Y_HISTORY_IM_HZ = [
    3_000, 7_900, 13_200, 13_900, 18_550, 21_000,
    37_900,   # |53.9 - 16| → y(t) × y_sum
    39_900,
    69_900,   # |53.9 + 16| → y(t) × y_sum (sum tone)
    74_500,
]


def build_readout():
    freqs = set(MODE_CLUSTERS_HZ)
    freqs.update(FEEDBACK_IM_HZ)
    freqs.update(Y_HISTORY_IM_HZ)
    for f in range(100_000, 200_001, 5_000):
        freqs.add(f)
    return sorted(freqs)


RECEIVER_MAP = {
    "1":    (1, "A-NE"),
    "2":    (2, "B-NE"),
    "3_NE": (3, "G-NE"),
    "4_NE": (5, "D-NE"),
    "5_NE": (7, "H-NE"),
}


def log(msg):
    print(msg, flush=True)


# ═══════════════════════════════════════════════════════════════════════
#  NARMA-10 generator
# ═══════════════════════════════════════════════════════════════════════

def generate_narma10(n_steps, rng):
    u = rng.uniform(0, 0.5, n_steps)
    y = np.zeros(n_steps)
    for t in range(NARMA_ORDER, n_steps - 1):
        y_sum = np.sum(y[t - 9:t + 1])
        y[t + 1] = (0.3 * y[t]
                     + 0.05 * y[t] * y_sum
                     + 1.5 * u[t - 9] * u[t]
                     + 0.1)
    return u, y


# ═══════════════════════════════════════════════════════════════════════
#  Hardware — pre-arm ringdown capture
# ═══════════════════════════════════════════════════════════════════════

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed ({handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    log("  PicoScope opened (Ch A ±1V DC)")
    return handle


def build_arb_waveform(freqs_hz, amplitudes, f_rep):
    buf = np.zeros(ARB_LEN, dtype=np.float64)
    for f_target, amp in zip(freqs_hz, amplitudes):
        if amp <= 0:
            continue
        k = round(f_target / f_rep)
        if k < 1 or k > ARB_LEN // 2:
            continue
        phase = 2 * np.pi * k * np.arange(ARB_LEN) / ARB_LEN
        buf += amp * np.sin(phase)
    peak = np.max(np.abs(buf))
    if peak > 0:
        buf /= peak
    arb_u8 = ((buf * 127) + 128).clip(0, 255).astype(np.uint8)
    return (ctypes.c_uint8 * ARB_LEN)(*arb_u8.tolist())


def ringdown_capture(handle, freqs_hz, amplitudes, f_rep, n_samples, timebase):
    """Pre-arm capture THEN change drive — captures the transition.

    Returns raw time-domain samples (float64).
    The capture starts BEFORE the DDS changes:
      0 – ~3 ms: old drive (DDS update in progress over USB)
      ~3 – 10.3 ms: new drive buildup + old mode ringdown
    """
    from picosdk.ps2000 import ps2000

    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    # 1. ARM capture (auto-trigger, starts sampling immediately)
    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 0)
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, n_samples, timebase, 1, ctypes.byref(t_ms))

    # 2. IMMEDIATELY change drive (while ADC is sampling)
    arb_buf = build_arb_waveform(freqs_hz, amplitudes, f_rep)
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase,
        0, 0, arb_buf, ARB_LEN, 0, 0
    )

    # 3. Wait for capture to complete
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 2:
            break

    # 4. Read data
    buf_a = (ctypes.c_int16 * n_samples)()
    buf_b = (ctypes.c_int16 * n_samples)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), n_samples)

    if n <= 0:
        return np.zeros(n_samples, dtype=np.float64)
    return np.array(buf_a[:n], dtype=np.float64)


def extract_sliced_features(raw, readout_freqs, sample_rate, n_slices):
    """FFT each time slice + full window → (n_slices+1) × n_readout features."""
    n = len(raw)
    slice_len = n // n_slices
    features = []

    for s in range(n_slices):
        seg = raw[s * slice_len:(s + 1) * slice_len]
        windowed = seg * np.hanning(len(seg))
        nfft = len(seg) * 4  # zero-pad for interpolation
        fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
        bin_hz = freq_axis[1] - freq_axis[0]

        mags = np.zeros(len(readout_freqs))
        for j, rf in enumerate(readout_freqs):
            tb = int(round(rf / bin_hz))
            lo = max(0, tb - 2)
            hi = min(len(fft_mag) - 1, tb + 2)
            mags[j] = float(np.max(fft_mag[lo:hi + 1]))
        features.append(mags)

    # Full-window FFT (traditional steady-state approach)
    windowed = raw * np.hanning(n)
    nfft = n * 4
    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
    bin_hz = freq_axis[1] - freq_axis[0]
    mags_full = np.zeros(len(readout_freqs))
    for j, rf in enumerate(readout_freqs):
        tb = int(round(rf / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(fft_mag) - 1, tb + 3)
        mags_full[j] = float(np.max(fft_mag[lo:hi + 1]))
    features.append(mags_full)

    return np.concatenate(features)  # (n_slices+1) × n_readout


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation
# ═══════════════════════════════════════════════════════════════════════

def nmse(y_true, y_pred):
    var = np.var(y_true)
    return float(np.mean((y_true - y_pred) ** 2) / var) if var > 0 else float('inf')


def train_ridge(X_train, y_train):
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_train)
    best_alpha, best_cv = 1.0, float('inf')
    for alpha in RIDGE_ALPHAS:
        scores = []
        for tr, va in KFold(n_splits=5, shuffle=False).split(X_s):
            reg = Ridge(alpha=alpha).fit(X_s[tr], y_train[tr])
            scores.append(nmse(y_train[va], reg.predict(X_s[va])))
        m = np.mean(scores)
        if m < best_cv:
            best_cv, best_alpha = m, alpha
    reg = Ridge(alpha=best_alpha).fit(X_s, y_train)
    return reg, scaler, best_alpha


def eval_feat(X, y_tr, y_te, n_train, name):
    reg, sc, alpha = train_ridge(X[:n_train], y_tr)
    pred_te = reg.predict(sc.transform(X[n_train:]))
    te = nmse(y_te, pred_te)
    return {"name": name, "nmse_test": round(te, 6),
            "features": X.shape[1], "alpha": alpha}


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 Temporal Memory — Time-Sliced Ringdown")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--census", required=True)
    parser.add_argument("--plate", default="4_NE")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--all-open", action="store_true")
    parser.add_argument("--n-slices", type=int, default=5,
                        help="Time slices per capture (default 5 × ~2ms)")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    n_slices = args.n_slices
    readout = build_readout()
    n_ro = len(readout)

    log("╔══════════════════════════════════════════════════════════════╗")
    log("║   NARMA-10 Temporal Memory — Time-Sliced Ringdown          ║")
    log("╚══════════════════════════════════════════════════════════════╝")
    log(f"Steps: {args.steps}  Slices: {n_slices}  Seed: {args.seed}")
    log(f"Readout: {n_ro} bins × {n_slices+1} time windows "
        f"= {(n_slices+1)*n_ro} features/step")

    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE
    slice_ms = N_SAMPLES / n_slices / SAMPLE_RATE * 1000
    log(f"Capture: {N_SAMPLES/SAMPLE_RATE*1000:.1f} ms total, "
        f"{slice_ms:.2f} ms/slice")
    log(f"Plate strongest mode τ ≈ 2 ms → {slice_ms:.1f} ms slices "
        f"give e^(-{slice_ms:.1f}/2) = {np.exp(-slice_ms/2):.0%} "
        f"retention per slice")

    # ── NARMA data ──
    u, y = generate_narma10(args.steps, rng)
    start = NARMA_ORDER + N_WASHOUT
    total = args.steps - start - 1
    n_train = int(total * 0.7)
    n_test = total - n_train
    y_target = y[start + 1:start + total + 1]  # predict y(t+1)
    y_tr, y_te = y_target[:n_train], y_target[n_train:]
    win = np.array([u[start + i - 9:start + i + 1] for i in range(total)])
    y_state = np.column_stack([
        y[start:start + total],
        [np.mean(y[start + i - 9:start + i]) for i in range(total)],
    ])
    log(f"Data: {total} usable ({n_train} train / {n_test} test)")
    log(f"Target: y(t+1) — correct one-step-ahead prediction")

    # ── Hardware ──
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000

    handle = _open_scope()
    mux = RelayMux(args.port)
    mux.open()
    time.sleep(0.5)

    max_freq = max(CARRIERS_12)
    f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))
    log(f"  f_rep = {f_rep:.1f} Hz")

    if args.all_open:
        log("  All-open: all NE relays...")
        mux.all_ne()
    else:
        relay_ch, relay_name = RECEIVER_MAP[args.plate]
        log(f"  Plate: {relay_name} (relay {relay_ch})")
        mux.select(relay_ch)
    time.sleep(0.1)

    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    n_feat = (n_slices + 1) * n_ro

    # ══════════════════════════════════════════════════════════════════
    #  PASS 1: 11 carriers (10u + y(t)), ringdown capture
    # ══════════════════════════════════════════════════════════════════
    log(f"\n═══ PASS 1: 11 carriers, ringdown capture ({n_feat} feat) ═══")
    X_p1 = np.zeros((total, n_feat))
    t0 = time.time()

    # Prime with first step's drive
    prime_amps = list(u[start - 1 - 9:start] * 2.0) + [
        np.clip(y[start - 1], 0, 2) / 2.0]
    arb_prime = build_arb_waveform(CARRIERS_11, prime_amps, f_rep)
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase, 0, 0, arb_prime, ARB_LEN, 0, 0)
    time.sleep(0.015)

    for idx in range(total):
        t = start + idx
        amps = list(u[t - 9:t + 1] * 2.0) + [np.clip(y[t], 0, 2) / 2.0]

        raw = ringdown_capture(handle, CARRIERS_11, amps, f_rep,
                               N_SAMPLES, TIMEBASE)
        X_p1[idx] = extract_sliced_features(raw, readout, SAMPLE_RATE,
                                            n_slices)

        if (idx + 1) % 50 == 0:
            el = time.time() - t0
            rate = (idx + 1) / el
            log(f"  {idx+1}/{total} ({rate:.1f}/s, ETA {(total-idx-1)/rate:.0f}s)")

    t_p1 = time.time() - t0
    log(f"  Pass 1: {t_p1:.1f}s ({total/t_p1:.1f} steps/s)")

    # ══════════════════════════════════════════════════════════════════
    #  PASS 2: 12 carriers (10u + y(t) + y_sum), ringdown capture
    # ══════════════════════════════════════════════════════════════════
    log(f"\n═══ PASS 2: 12 carriers + y-history, ringdown ({n_feat} feat) ═══")
    X_p2 = np.zeros((total, n_feat))
    t0 = time.time()

    # Prime with y-history
    prime_amps2 = list(u[start - 1 - 9:start] * 2.0) + [
        np.clip(y[start - 1], 0, 2) / 2.0,
        np.clip(np.mean(y[start - 10:start - 1]), 0, 2) / 2.0]
    arb_prime2 = build_arb_waveform(CARRIERS_12, prime_amps2, f_rep)
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase, 0, 0, arb_prime2, ARB_LEN, 0, 0)
    time.sleep(0.015)

    for idx in range(total):
        t = start + idx
        y_fb = np.clip(y[t], 0, 2) / 2.0
        y_sum_amp = np.clip(np.mean(y[t - 9:t]), 0, 2) / 2.0
        amps = list(u[t - 9:t + 1] * 2.0) + [y_fb, y_sum_amp]

        raw = ringdown_capture(handle, CARRIERS_12, amps, f_rep,
                               N_SAMPLES, TIMEBASE)
        X_p2[idx] = extract_sliced_features(raw, readout, SAMPLE_RATE,
                                            n_slices)

        if (idx + 1) % 50 == 0:
            el = time.time() - t0
            rate = (idx + 1) / el
            log(f"  {idx+1}/{total} ({rate:.1f}/s, ETA {(total-idx-1)/rate:.0f}s)")

    t_p2 = time.time() - t0
    log(f"  Pass 2: {t_p2:.1f}s ({total/t_p2:.1f} steps/s)")

    # ── Save checkpoint ──
    np.savez(RESULTS_DIR / "hw_temporal_checkpoint.npz",
             X_p1=X_p1, X_p2=X_p2, u=u, y=y,
             readout=np.array(readout),
             start=start, n_train=n_train, total=total,
             n_slices=n_slices, sample_rate=SAMPLE_RATE)

    # ── Close hardware ──
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps2000.ps2000_close_unit(handle)
    mux.close()
    log("  Hardware closed.\n")

    # ══════════════════════════════════════════════════════════════════
    #  EVALUATION — Temporal Memory Demonstration
    # ══════════════════════════════════════════════════════════════════

    evaluate(X_p1, X_p2, u, y, readout, start, n_train, total,
             n_slices, win, y_state, y_tr, y_te, t_p1, t_p2, SAMPLE_RATE)


def evaluate(X_p1, X_p2, u, y, readout, start, n_train, total,
             n_slices, win, y_state, y_tr, y_te, t_p1, t_p2, sample_rate):
    """Full evaluation with temporal memory tests."""
    n_ro = len(readout)
    results = []

    def ev(X, name):
        r = eval_feat(X, y_tr, y_te, n_train, name)
        marker = " <<<" if r["nmse_test"] < 0.187 else ""
        log(f"  {name:<55s} {r['nmse_test']:.4f}  "
            f"({r['features']} f, α={r['alpha']}){marker}")
        results.append(r)
        return r

    # Separate time slices for both passes
    def split_slices(X):
        slices = [X[:, s*n_ro:(s+1)*n_ro] for s in range(n_slices)]
        full = X[:, n_slices*n_ro:]
        return slices, full

    p1_slices, p1_full = split_slices(X_p1)
    p2_slices, p2_full = split_slices(X_p2)

    from cwm_picoscope import N_SAMPLES
    slice_ms = N_SAMPLES / n_slices / sample_rate * 1000

    # ── Section 1: Baseline comparisons ──
    log("═" * 72)
    log("  TEMPORAL MEMORY EVALUATION")
    log("═" * 72)

    log("\n--- BASELINES ---")
    ev(win, "SW_only: u_window")
    ev(np.hstack([win, y_state]), "SW_only: u_window + y_state")

    # ── Section 2: Full-window FFT (traditional, no temporal info) ──
    log("\n--- FULL-WINDOW FFT (traditional, no temporal resolution) ---")
    ev(np.hstack([p1_full, win]), "P1_full_fft + u_win (11-car)")
    ev(np.hstack([p2_full, win]), "P2_full_fft + u_win (12-car)")

    # ── Section 3: Individual time slices ──
    log("\n--- INDIVIDUAL TIME SLICES (Pass 2, 12-car) ---")
    for s in range(n_slices):
        t_start = s * slice_ms
        t_end = (s + 1) * slice_ms
        ev(np.hstack([p2_slices[s], win]),
           f"P2_slice{s} ({t_start:.1f}-{t_end:.1f}ms) + u_win")

    # ══════════════════════════════════════════════════════════════════
    #  KEY TEST: early vs late slices
    # ══════════════════════════════════════════════════════════════════
    log("\n--- KEY TEST: EARLY vs LATE SLICES (Pass 2) ---")

    # "Early" = first 2 slices (0 to ~4ms, contains previous-step energy)
    # "Late"  = last 2 slices (~6 to 10ms, mostly current steady state)
    n_early = 2
    n_late = 2
    X_early = np.hstack(p2_slices[:n_early])
    X_late = np.hstack(p2_slices[-n_late:])

    r_late = ev(np.hstack([X_late, win]),
                f"P2_LATE_{n_late}slices + u_win")
    r_early = ev(np.hstack([X_early, win]),
                 f"P2_EARLY_{n_early}slices + u_win")
    r_all = ev(np.hstack([X_p2, win]),
               f"P2_ALL_slices + u_win")
    ev(np.hstack([X_early, X_late, win]),
       f"P2_EARLY+LATE + u_win")

    # Temporal difference: early minus late → pure memory signal
    X_mem = X_early[:, :n_ro] - X_late[:, :n_ro]  # first early - last late
    ev(np.hstack([X_mem, win]),
       f"P2_memory_signal (early-late) + u_win")

    # ── Section 5: Same tests for Pass 1 (11 carriers) ──
    log("\n--- EARLY vs LATE (Pass 1, 11-car) ---")
    X_early1 = np.hstack(p1_slices[:n_early])
    X_late1 = np.hstack(p1_slices[-n_late:])
    ev(np.hstack([X_late1, win]), f"P1_LATE_{n_late}slices + u_win")
    ev(np.hstack([X_early1, win]), f"P1_EARLY_{n_early}slices + u_win")
    ev(np.hstack([X_p1, win]), f"P1_ALL_slices + u_win")

    # ── Section 6: Without u_win (can temporal slicing replace SW?) ──
    log("\n--- WITHOUT u_win (plate temporal slicing alone) ---")
    ev(X_late, f"P2_LATE_only (no u_win)")
    ev(X_early, f"P2_EARLY_only (no u_win)")
    ev(X_p2, f"P2_ALL_slices_only (no u_win)")
    ev(p2_full, f"P2_full_fft_only (no u_win)")

    # ── Section 7: Hybrid (plate temporal + software y-state) ──
    log("\n--- HYBRID: plate temporal + SW y-state ---")
    ev(np.hstack([X_p2, win, y_state]),
       f"P2_ALL_slices + u_win + y_state")

    # ══════════════════════════════════════════════════════════════════
    #  Physical memory analysis
    # ══════════════════════════════════════════════════════════════════
    log("\n--- PHYSICAL MEMORY DIAGNOSTICS ---")

    # Correlation of each slice with PREVIOUS step's input u(t-1)
    u_prev = np.zeros(total)
    u_prev[1:] = u[start + 1:start + total]  # u at step t (= "previous" for t+1 target)
    # Actually we want u at step t-1 relative to current step
    u_prev_val = np.zeros(total)
    u_prev_val[1:] = u[start:start + total - 1]

    for s in range(n_slices):
        t_start = s * slice_ms
        t_end = (s + 1) * slice_ms
        corrs = []
        for col in range(n_ro):
            c = abs(np.corrcoef(p2_slices[s][:n_train, col],
                                u_prev_val[:n_train])[0, 1])
            if not np.isnan(c):
                corrs.append(c)
        mean_c = np.mean(corrs) if corrs else 0
        max_c = np.max(corrs) if corrs else 0
        log(f"  Slice {s} ({t_start:.1f}-{t_end:.1f}ms) corr with u(t-1): "
            f"mean={mean_c:.4f} max={max_c:.4f}")

    # Lag-1 autocorrelation per slice
    log("\n  Lag-1 autocorrelation (feature persistence across steps):")
    for s in range(n_slices):
        t_start = s * slice_ms
        autocorrs = []
        for col in range(n_ro):
            c = np.corrcoef(p2_slices[s][:-1, col],
                            p2_slices[s][1:, col])[0, 1]
            if not np.isnan(c):
                autocorrs.append(c)
        log(f"  Slice {s} ({t_start:.1f}ms): "
            f"mean={np.mean(autocorrs):.4f} max={np.max(autocorrs):.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  Summary
    # ══════════════════════════════════════════════════════════════════
    log("\n" + "═" * 72)
    log("  SUMMARY — sorted by NMSE")
    log("═" * 72)
    log(f"  {'Approach':<55s} {'NMSE':>8s}")
    log("  " + "─" * 65)
    for r in sorted(results, key=lambda x: x["nmse_test"]):
        marker = " <<<" if r["nmse_test"] < 0.187 else ""
        log(f"  {r['name']:<55s} {r['nmse_test']:.4f}{marker}")

    # Key comparisons
    log("\n" + "─" * 72)
    log("  KEY COMPARISONS:")
    nmse_late = r_late["nmse_test"]
    nmse_early = r_early["nmse_test"]
    nmse_all = r_all["nmse_test"]

    log(f"  Late slices only (current state):    {nmse_late:.4f}")
    log(f"  Early slices only (previous state):  {nmse_early:.4f}")
    log(f"  All slices (full temporal):           {nmse_all:.4f}")
    log(f"  Software ESN baseline:               0.187")

    if nmse_all < nmse_late:
        improve = (1 - nmse_all / nmse_late) * 100
        log(f"\n  ✓ ALL slices beat LATE-only by {improve:.1f}%")
        log(f"    → Early slices contributed information the late slices lack")
        log(f"    → This is PHYSICAL TEMPORAL MEMORY from plate ringdown")
    else:
        log(f"\n  ✗ All slices did NOT beat late-only")
        log(f"    → No detectable temporal memory at this step rate")

    if nmse_early < nmse_late:
        log(f"  ✓ Early slices ({nmse_early:.4f}) beat late ({nmse_late:.4f})")
        log(f"    → Previous-step info more valuable than current steady state")
    elif nmse_early > nmse_late * 1.1:
        log(f"  ✗ Late slices substantially better — current state dominates")
    else:
        log(f"  ≈ Early and late comparable — both contain useful info")

    # ── Save ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": "narma_hw_temporal.py",
        "concept": "Temporal memory demonstration via time-sliced ringdown",
        "steps": args.steps if 'args' in dir() else 1000,
        "seed": 42,
        "n_slices": n_slices,
        "n_readout": len(readout),
        "n_features_per_step": (n_slices + 1) * len(readout),
        "slice_ms": round(slice_ms, 2),
        "pass1_time_s": round(t_p1, 1),
        "pass2_time_s": round(t_p2, 1),
        "results": sorted(results, key=lambda x: x["nmse_test"]),
        "key_comparison": {
            "late_only": nmse_late,
            "early_only": nmse_early,
            "all_slices": nmse_all,
            "memory_detected": bool(nmse_all < nmse_late),
        },
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = RESULTS_DIR / f"narma10_temporal_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nSaved → {outfile}")


if __name__ == "__main__":
    main()
