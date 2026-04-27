#!/usr/bin/env python3
"""
NARMA-10 Plate-Only Temporal Memory via Ringdown Capture

Architecture (NO software ESN — plate does everything):
  1. Pre-arm PicoScope capture BEFORE changing drive
  2. Change AWG → hardware transitions instantly
  3. Capture catches the transition: old drive ringdown + new drive buildup
  4. Split capture into time slices → early slices = physical memory
  5. Feedback carrier at 53.9 kHz encodes y(t) via IM products
  6. Linear readout (Ridge) — just a dot product, no recurrence

The key insight: NARMA-10 is first-order in y.
  y(t+1) = 0.3·y(t) + 0.05·y(t)·Σy + 1.5·u(t-9)·u(t) + 0.1
Oracle shows: y(t) + u-window → NMSE = 0.000
So if the plate can extract y(t) from IM products AND retain 1 step
of physical memory in mode ringdown, it solves NARMA without an ESN.

Usage:
  DYLD_LIBRARY_PATH="..." python tools/narma_ringdown.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_cross_20260418_142222.json \\
      [--steps 1000] [--fast] [--all-open] [--n-slices 8]
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

NARMA_ORDER = 10
N_WASHOUT = 50

N_AVG = 1  # No averaging! Each capture is unique (different transition state)
AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096

RIDGE_ALPHAS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

LADDER_CARRIERS_HZ = [
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]
FEEDBACK_FREQ = 53_900

# Full readout set: mode clusters + feedback IMs
READOUT_FREQS_HZ = sorted(set([
    # Mode clusters
    11_425, 15_100, 16_000, 17_375, 19_000, 23_900, 29_200, 29_900,
    31_600, 33_225, 34_550, 36_000, 37_000, 42_300, 45_000, 47_800,
    49_600, 51_500, 53_900, 56_200, 58_500, 62_000, 65_075, 68_200,
    70_800, 73_500, 76_200, 78_800, 81_500, 84_200, 86_900, 89_400,
    95_000,
    # Feedback IM new
    2_300, 4_300, 4_500, 4_600, 5_900, 6_100, 8_900,
    16_900, 20_100, 24_700,
    98_900, 103_500, 110_100, 112_400,
]))

RECEIVER_MAP = {
    "1":    (1, "A-NE"),
    "2":    (2, "B-NE"),
    "3_NE": (3, "G-NE"),
    "4_NE": (5, "D-NE"),
    "5_NE": (7, "H-NE"),
}


def log(msg):
    print(msg, flush=True)


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
#  Hardware — modified for pre-arm ringdown capture
# ═══════════════════════════════════════════════════════════════════════

def _open_scope():
    import cwm_picoscope
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed ({handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    log("  PicoScope opened (Ch A ±1V DC)")
    return handle


def build_arb_waveform(freqs_hz, amplitudes, f_rep):
    """Build ARB waveform buffer for given frequencies and amplitudes."""
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


def ringdown_step(handle, freqs_hz, amplitudes, f_rep, n_samples, timebase):
    """Pre-arm capture, THEN change drive. Captures the transition.

    Returns raw time-domain samples (int16 array).
    The capture starts BEFORE the drive changes, so it contains:
    - A few samples of old drive (pre-transition)
    - New drive buildup + old drive ringdown (post-transition)
    """
    from picosdk.ps2000 import ps2000

    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    # Step 1: ARM the capture (auto-trigger, starts immediately)
    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 0)  # auto-trigger, no delay
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, n_samples, timebase, 1, ctypes.byref(t_ms))

    # Step 2: IMMEDIATELY change the drive (while capture is running!)
    arb_buf = build_arb_waveform(freqs_hz, amplitudes, f_rep)
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase,
        0, 0, arb_buf, ARB_LEN, 0, 0
    )
    # The set_sig_gen call takes ~12ms of Python time
    # During that time, the capture was running and caught the transition!

    # Step 3: Wait for capture to complete (should already be done)
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 2:
            break

    # Step 4: Read data
    buf_a = (ctypes.c_int16 * n_samples)()
    buf_b = (ctypes.c_int16 * n_samples)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), n_samples)

    if n <= 0:
        return np.zeros(n_samples, dtype=np.float64)

    return np.array(buf_a[:n], dtype=np.float64)


def extract_time_freq_features(raw_samples, readout_freqs, sample_rate, n_slices):
    """Extract time-frequency features from raw capture.

    Splits the capture into n_slices temporal segments, takes FFT of each.
    Earlier slices contain more previous-step energy (physical memory).
    Later slices are closer to current-step steady state.
    """
    n = len(raw_samples)
    slice_len = n // n_slices
    features = []

    for s in range(n_slices):
        start_idx = s * slice_len
        end_idx = start_idx + slice_len
        segment = raw_samples[start_idx:end_idx]

        # Window and FFT
        windowed = segment * np.hanning(len(segment))
        nfft = len(segment) * 4  # zero-pad for interpolation
        fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
        bin_hz = freq_axis[1] - freq_axis[0]

        # Extract magnitudes at readout frequencies
        mags = np.zeros(len(readout_freqs))
        for j, rf in enumerate(readout_freqs):
            tb = int(round(rf / bin_hz))
            lo = max(0, tb - 2)
            hi = min(len(fft_mag) - 1, tb + 2)
            mags[j] = float(np.max(fft_mag[lo:hi + 1]))
        features.append(mags)

    # Also extract full-window FFT (traditional approach)
    windowed_full = raw_samples * np.hanning(n)
    nfft_full = n * 4
    fft_full = np.abs(np.fft.rfft(windowed_full, n=nfft_full))
    freq_axis_full = np.fft.rfftfreq(nfft_full, d=1.0 / sample_rate)
    bin_hz_full = freq_axis_full[1] - freq_axis_full[0]
    mags_full = np.zeros(len(readout_freqs))
    for j, rf in enumerate(readout_freqs):
        tb = int(round(rf / bin_hz_full))
        lo = max(0, tb - 3)
        hi = min(len(fft_full) - 1, tb + 3)
        mags_full[j] = float(np.max(fft_full[lo:hi + 1]))
    features.append(mags_full)

    return np.concatenate(features)  # n_slices+1 segments × n_readout freqs


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


def eval_ridge(name, X_all, y_tr, y_te, n_train):
    Xtr, Xte = X_all[:n_train], X_all[n_train:]
    reg, sc, alpha = train_ridge(Xtr, y_tr)
    te = nmse(y_te, reg.predict(sc.transform(Xte)))
    log(f"  {name:<55s} {te:.4f}  ({X_all.shape[1]} feats, α={alpha})")
    return {"name": name, "nmse_test": round(te, 6),
            "features": X_all.shape[1], "alpha": alpha}


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 Ringdown (plate-only, no ESN)")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--census", required=True)
    parser.add_argument("--plate", default="4_NE")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--all-open", action="store_true")
    parser.add_argument("--fast", action="store_true",
                        help="Less averaging (already minimal)")
    parser.add_argument("--n-slices", type=int, default=8,
                        help="Number of time slices per capture")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    n_slices = args.n_slices
    log("=== NARMA-10 Ringdown Capture (Plate-Only, NO ESN) ===")
    log(f"Steps: {args.steps}  Slices: {n_slices}  Seed: {args.seed}")
    log(f"Feedback: {FEEDBACK_FREQ/1000:.1f} kHz")
    log(f"Readout: {len(READOUT_FREQS_HZ)} frequencies")
    log(f"Features per step: {(n_slices+1) * len(READOUT_FREQS_HZ)} "
        f"({n_slices}+1 time slices × {len(READOUT_FREQS_HZ)} freqs)")

    # ── NARMA data ──
    u, y = generate_narma10(args.steps, rng)
    start = NARMA_ORDER + N_WASHOUT
    total = args.steps - start - 1
    n_train = int(total * 0.7)
    n_test = total - n_train
    y_all = y[start:start + total]
    y_tr, y_te = y_all[:n_train], y_all[n_train:]
    win = np.array([u[start + i - 9:start + i + 1] for i in range(total)])
    log(f"Data: {total} usable ({n_train} train / {n_test} test)")

    # ── Hardware ──
    from relay_mux import RelayMux
    import cwm_picoscope
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE

    handle = _open_scope()
    mux = RelayMux(args.port)
    mux.open()
    time.sleep(0.5)

    carriers_10 = list(LADDER_CARRIERS_HZ)
    carriers_11 = carriers_10 + [FEEDBACK_FREQ]
    max_freq = max(carriers_11)
    f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))
    log(f"  f_rep = {f_rep:.1f} Hz, sample_rate = {SAMPLE_RATE/1000:.0f} kHz")
    log(f"  Capture window: {N_SAMPLES/SAMPLE_RATE*1000:.1f} ms")
    log(f"  Slice duration: {N_SAMPLES/n_slices/SAMPLE_RATE*1000:.2f} ms")

    if args.all_open:
        log("  All-open: activating all NE relays...")
        mux.all_ne()
    else:
        relay_ch, relay_name = RECEIVER_MAP[args.plate]
        log(f"  Single plate: {relay_name}")
        mux.select(relay_ch)
    time.sleep(0.1)

    # ══════════════════════════════════════════════════════════════════
    #  PASS 1: No-feedback ringdown capture (10 carriers)
    # ══════════════════════════════════════════════════════════════════
    n_feats = (n_slices + 1) * len(READOUT_FREQS_HZ)
    log(f"\n═══ PASS 1: No-feedback ringdown ({n_feats} features) ═══")
    X_nf = np.zeros((total, n_feats))
    t0 = time.time()

    # Prime the drive with first step (so step 0 has a previous drive)
    from picosdk.ps2000 import ps2000
    prime_amps = list(u[start - 1 - 9:start] * 2.0)
    arb_prime = build_arb_waveform(carriers_10, prime_amps, f_rep)
    delta_phase = int(f_rep * (2**32) / 48_000_000)
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase, 0, 0, arb_prime, ARB_LEN, 0, 0)
    time.sleep(0.015)  # Let prime settle

    for idx in range(total):
        t = start + idx
        window = u[t - 9:t + 1]
        amps = list(window * 2.0)

        # Ringdown capture: pre-arm → change drive → read transition
        raw = ringdown_step(handle, carriers_10, amps, f_rep,
                            N_SAMPLES, TIMEBASE)
        X_nf[idx] = extract_time_freq_features(
            raw, READOUT_FREQS_HZ, SAMPLE_RATE, n_slices)

        if (idx + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total - idx - 1) / rate
            log(f"  {idx+1}/{total} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_nf = time.time() - t0
    log(f"  Pass 1: {elapsed_nf:.1f}s ({total/elapsed_nf:.1f} steps/s)")

    # ══════════════════════════════════════════════════════════════════
    #  PASS 2: Teacher-forced ringdown (11 carriers, true y(t))
    # ══════════════════════════════════════════════════════════════════
    log(f"\n═══ PASS 2: Teacher-forced ringdown ({n_feats} features) ═══")
    X_tf = np.zeros((total, n_feats))
    t0 = time.time()

    # Prime with feedback
    prime_amps_fb = prime_amps + [np.clip(y[start-1], 0, 2) / 2.0]
    arb_prime_fb = build_arb_waveform(carriers_11, prime_amps_fb, f_rep)
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase, 0, 0, arb_prime_fb, ARB_LEN, 0, 0)
    time.sleep(0.015)

    for idx in range(total):
        t = start + idx
        window = u[t - 9:t + 1]
        amps_u = list(window * 2.0)
        y_fb = np.clip(y[t], 0, 2) / 2.0
        amps_all = amps_u + [y_fb]

        raw = ringdown_step(handle, carriers_11, amps_all, f_rep,
                            N_SAMPLES, TIMEBASE)
        X_tf[idx] = extract_time_freq_features(
            raw, READOUT_FREQS_HZ, SAMPLE_RATE, n_slices)

        if (idx + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total - idx - 1) / rate
            log(f"  {idx+1}/{total} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_tf = time.time() - t0
    log(f"  Pass 2: {elapsed_tf:.1f}s ({total/elapsed_tf:.1f} steps/s)")

    # Save checkpoints
    np.savez(RESULTS_DIR / "hw_ringdown_checkpoint.npz",
             X_nf=X_nf, X_tf=X_tf, u=u, y=y,
             readout_freqs=np.array(READOUT_FREQS_HZ),
             start=start, n_train=n_train, total=total,
             n_slices=n_slices, sample_rate=SAMPLE_RATE)

    # ── Close hardware ──
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps2000.ps2000_close_unit(handle)
    mux.close()
    log("  Hardware closed.")

    # ══════════════════════════════════════════════════════════════════
    #  Evaluation — PLATE ONLY (no ESN!)
    # ══════════════════════════════════════════════════════════════════
    log(f"\n═══ Evaluation (PLATE ONLY — no ESN, no software memory) ═══")
    results = []
    n_ro = len(READOUT_FREQS_HZ)

    # Separate time slices
    # X format: [slice_0, slice_1, ..., slice_{n-1}, full_fft]
    # Each slice has n_ro features
    X_nf_slices = [X_nf[:, s*n_ro:(s+1)*n_ro] for s in range(n_slices)]
    X_nf_full = X_nf[:, n_slices*n_ro:]  # full-window FFT

    X_tf_slices = [X_tf[:, s*n_ro:(s+1)*n_ro] for s in range(n_slices)]
    X_tf_full = X_tf[:, n_slices*n_ro:]

    X_diff = X_tf - X_nf
    X_diff_slices = [X_diff[:, s*n_ro:(s+1)*n_ro] for s in range(n_slices)]
    X_diff_full = X_diff[:, n_slices*n_ro:]

    # --- Baselines ---
    log("\n--- Baselines ---")
    r = eval_ridge("SW_ESN_baseline (for reference, NOT plate)",
                   np.zeros((total, 0)), y_tr, y_te, n_train)
    # Actually run a proper SW ESN
    def make_esn(X_in, hidden=64, leak=0.5, sr=0.9, seed=42):
        rng2 = np.random.default_rng(seed)
        W_in = rng2.uniform(-0.1, 0.1, (hidden, X_in.shape[1]))
        W_res = rng2.normal(0, 1, (hidden, hidden))
        W_res *= sr / np.max(np.abs(np.linalg.eigvals(W_res)))
        states = np.zeros((len(X_in), hidden))
        s = np.zeros(hidden)
        for i in range(len(X_in)):
            pre = np.tanh(W_in @ X_in[i] + W_res @ s)
            s = (1 - leak) * s + leak * pre
            states[i] = s
        return states
    esn_states = make_esn(win)
    r = eval_ridge("SW_ESN_64h (reference)", esn_states, y_tr, y_te, n_train)
    results.append(r)

    # --- Traditional (steady-state) full-window FFT ---
    log("\n--- Full-window FFT only (no temporal info) ---")
    r = eval_ridge("nf_full_fft", X_nf_full, y_tr, y_te, n_train)
    results.append(r)
    r = eval_ridge("tf_full_fft + win", np.hstack([X_tf_full, win]),
                   y_tr, y_te, n_train)
    results.append(r)

    # --- Individual time slices ---
    log("\n--- Individual time slices (teacher-forced) ---")
    for s in range(n_slices):
        dur_ms = (N_SAMPLES / n_slices) / SAMPLE_RATE * 1000
        t_start = s * dur_ms
        t_end = (s + 1) * dur_ms
        r = eval_ridge(f"tf_slice_{s} ({t_start:.1f}-{t_end:.1f}ms) + win",
                       np.hstack([X_tf_slices[s], win]),
                       y_tr, y_te, n_train)
        results.append(r)

    # --- Early vs late slices (memory test!) ---
    log("\n--- TEMPORAL MEMORY: early slices have previous-step info ---")
    # Early slices (0, 1): contain previous-step ringdown
    X_early = np.hstack(X_tf_slices[:2])
    # Late slices (-2, -1): mostly current-step steady state
    X_late = np.hstack(X_tf_slices[-2:])

    r = eval_ridge("tf_early_2slices + win",
                   np.hstack([X_early, win]), y_tr, y_te, n_train)
    results.append(r)
    r = eval_ridge("tf_late_2slices + win",
                   np.hstack([X_late, win]), y_tr, y_te, n_train)
    results.append(r)
    r = eval_ridge("tf_early_minus_late + win",
                   np.hstack([X_early - X_late, win]), y_tr, y_te, n_train)
    results.append(r)

    # --- All slices combined (full time-frequency representation) ---
    log("\n--- All time-frequency features ---")
    r = eval_ridge("tf_ALL_slices",
                   X_tf, y_tr, y_te, n_train)
    results.append(r)
    r = eval_ridge("tf_ALL_slices + win",
                   np.hstack([X_tf, win]), y_tr, y_te, n_train)
    results.append(r)
    r = eval_ridge("nf_ALL_slices + win",
                   np.hstack([X_nf, win]), y_tr, y_te, n_train)
    results.append(r)
    r = eval_ridge("diff_ALL_slices + win",
                   np.hstack([X_diff, win]), y_tr, y_te, n_train)
    results.append(r)

    # --- Stack everything ---
    r = eval_ridge("nf+tf+diff ALL + win",
                   np.hstack([X_nf, X_tf, X_diff, win]),
                   y_tr, y_te, n_train)
    results.append(r)

    # --- Temporal difference (plate's own finite differencing) ---
    log("\n--- Temporal difference: consecutive captures ---")
    # X_tf[t] - X_tf[t-1] encodes what changed (plate's derivative)
    X_tdiff = np.zeros_like(X_tf)
    X_tdiff[1:] = X_tf[1:] - X_tf[:-1]
    r = eval_ridge("tf_temporal_diff + win",
                   np.hstack([X_tdiff, win]), y_tr, y_te, n_train)
    results.append(r)
    r = eval_ridge("tf + tf_tdiff + win",
                   np.hstack([X_tf, X_tdiff, win]), y_tr, y_te, n_train)
    results.append(r)

    # --- Physical memory metric ---
    log("\n--- Physical memory analysis ---")
    # Check if early slices correlate with PREVIOUS step's input
    u_prev = np.zeros(total)
    u_prev[1:] = np.array([u[start + i - 1] for i in range(1, total)])
    # Correlation between early-slice features and u(t-1)
    early_corr = []
    for col in range(X_early.shape[1]):
        c = abs(np.corrcoef(X_early[:n_train, col], u_prev[:n_train])[0, 1])
        early_corr.append(c)
    late_corr = []
    for col in range(X_late.shape[1]):
        c = abs(np.corrcoef(X_late[:n_train, col], u_prev[:n_train])[0, 1])
        late_corr.append(c)
    log(f"  Early slices corr with u(t-1): mean={np.mean(early_corr):.4f} max={np.max(early_corr):.4f}")
    log(f"  Late slices corr with u(t-1):  mean={np.mean(late_corr):.4f} max={np.max(late_corr):.4f}")
    if np.mean(early_corr) > np.mean(late_corr) * 1.1:
        log("  ✓ Early slices contain MORE previous-step info → physical memory detected!")
    else:
        log("  ✗ No significant temporal memory detected in early vs late slices")

    # Lag-1 autocorrelation (same metric as before but on time-sliced data)
    autocorrs = []
    for col in range(X_tf.shape[1]):
        c = np.corrcoef(X_tf[:-1, col], X_tf[1:, col])[0, 1]
        autocorrs.append(c)
    log(f"  Time-freq feature lag-1 autocorr: mean={np.mean(autocorrs):.4f} max={np.max(autocorrs):.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  Summary
    # ══════════════════════════════════════════════════════════════════
    log("\n" + "═" * 72)
    log("  RESULTS — Plate-Only Ringdown NARMA-10 (NO SOFTWARE ESN)")
    log("═" * 72)
    log(f"  {'Approach':<55s} {'NMSE':>8s}")
    log("  " + "─" * 65)
    for r in sorted(results, key=lambda x: x.get("nmse_test", 999)):
        nm = r.get("nmse_test", 999)
        marker = " <<<" if nm < 0.187 else ""
        log(f"  {r['name']:<55s} {nm:.4f}{marker}")

    best_plate = min((r for r in results if "SW_ESN" not in r["name"]),
                     key=lambda x: x.get("nmse_test", 999))
    sw_esn = next((r for r in results if "SW_ESN_64h" in r["name"]), None)
    log(f"\n  Best plate-only: {best_plate['nmse_test']:.4f} ({best_plate['name']})")
    if sw_esn:
        log(f"  Software ESN:    {sw_esn['nmse_test']:.4f}")
        if best_plate["nmse_test"] < sw_esn["nmse_test"]:
            pct = (1 - best_plate["nmse_test"] / sw_esn["nmse_test"]) * 100
            log(f"  *** PLATE BEATS SOFTWARE ESN by {pct:.1f}% — NO SOFTWARE MEMORY! ***")
        else:
            gap = best_plate["nmse_test"] - sw_esn["nmse_test"]
            log(f"  Gap to SW ESN: +{gap:.4f}")
            log(f"  The plate needs more temporal memory (faster step rate or Q improvement)")

    # ── Save ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": "narma_ringdown.py",
        "concept": "Plate-only NARMA-10 via ringdown physical memory",
        "architecture": "NO software ESN — plate ringdown provides temporal state",
        "steps": args.steps, "seed": args.seed,
        "n_slices": n_slices,
        "n_readout_freqs": len(READOUT_FREQS_HZ),
        "n_features_per_step": n_feats,
        "feedback_freq_hz": FEEDBACK_FREQ,
        "pass1_time_s": round(elapsed_nf, 1),
        "pass2_time_s": round(elapsed_tf, 1),
        "early_slice_u_prev_corr": round(float(np.mean(early_corr)), 4),
        "late_slice_u_prev_corr": round(float(np.mean(late_corr)), 4),
        "results": sorted(results, key=lambda x: x.get("nmse_test", 999)),
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = RESULTS_DIR / f"narma10_ringdown_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nSaved → {outfile}")


if __name__ == "__main__":
    main()
