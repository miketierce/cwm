#!/usr/bin/env python3
"""
NARMA-10 Hardware Virtual Rewrite — Track A on Glass Plates

Tests the virtual rewrite feedback concept on real hardware.
Based on narma_ladder.py's proven hardware path, modified to:

  1. Add an 11th carrier at 53.9 kHz encoding y(t) or ŷ(t)
  2. NEVER expose raw y value as a feature — force IM extraction
  3. Run teacher-forced (open-loop) first, then closed-loop

The plate's IM products between the feedback carrier and input
carriers physically compute ŷ(t) × u(t-i) — the NARMA cross-terms.

Usage:
  DYLD_LIBRARY_PATH="..." python tools/narma_hw_virtual_rewrite.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_cross_20260418_142222.json \\
      [--steps 1000] [--fast] [--all-open]
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

# Hardware (overridden by --fast)
N_AVG = 8
SETTLE_S = 0.12
SETTLE_RELAY_S = 0.10
AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096

# Ridge
RIDGE_ALPHAS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]

# 10 input carriers (from narma_ladder.py)
LADDER_CARRIERS_HZ = [
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]

# 11th feedback carrier: 53.9 kHz — best IM coverage
# 26 IM products landing on 19 unique plate modes
FEEDBACK_FREQ = 53_900

# Plate mode clusters (landing pads for IM products)
MODE_CLUSTERS_HZ = [
    11_425, 15_100, 16_000, 17_375, 19_000, 23_900, 29_200, 29_900,
    31_600, 33_225, 34_550, 36_000, 37_000, 42_300, 45_000, 47_800,
    49_600, 51_500, 53_900, 56_200, 58_500, 62_000, 65_075, 68_200,
    70_800, 73_500, 76_200, 78_800, 81_500, 84_200, 86_900, 89_400,
    95_000,
]

# Readout
IM_TOL_PCT = 2.0

# Plate receivers
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
#  Readout frequency computation
# ═══════════════════════════════════════════════════════════════════════

def compute_readout_freqs(carriers, all_modes, nyquist=390_000):
    readout, labels, im_map = [], [], []
    seen = set()

    for f in all_modes:
        readout.append(f)
        ci = None
        for idx, cf in enumerate(carriers):
            if abs(f - cf) / max(f, cf) < 0.02:
                ci = idx
                break
        labels.append(f"carrier_{ci}" if ci is not None else f"mode_{f/1000:.1f}k")
        im_map.append((ci if ci is not None else -1,
                        ci if ci is not None else -1,
                        "self" if ci is not None else "ambient"))
        seen.add(f)

    for i in range(len(carriers)):
        for j in range(i + 1, len(carriers)):
            fi, fj = carriers[i], carriers[j]
            for im_f, im_type in [(abs(fi - fj), "IM2d"), (fi + fj, "IM2s")]:
                if im_f < 1000 or im_f > nyquist:
                    continue
                for mf in all_modes:
                    if abs(im_f - mf) / max(im_f, mf) < IM_TOL_PCT / 100:
                        if mf not in seen:
                            readout.append(mf)
                            labels.append(f"{im_type}_{i}x{j}")
                            im_map.append((i, j, im_type))
                            seen.add(mf)
                        break

    for i in range(len(carriers)):
        for j in range(len(carriers)):
            if i == j:
                continue
            f3 = abs(2 * carriers[i] - carriers[j])
            if f3 < 1000 or f3 > nyquist:
                continue
            for mf in all_modes:
                if abs(f3 - mf) / max(f3, mf) < IM_TOL_PCT / 100:
                    if mf not in seen:
                        readout.append(mf)
                        labels.append(f"IM3_{i}x{j}")
                        im_map.append((i, j, "IM3"))
                        seen.add(mf)
                    break

    return readout, labels, im_map


# ═══════════════════════════════════════════════════════════════════════
#  Hardware interface
# ═══════════════════════════════════════════════════════════════════════

def _open_scope():
    """Open PicoScope 2204A, Ch A only."""
    import cwm_picoscope
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed ({handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V DC
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B off
    log("  PicoScope opened (Ch A ±1V DC)")
    return handle


def drive_multitone(handle, freqs_hz, amplitudes, f_rep):
    """Drive multiple frequencies simultaneously via ARB waveform."""
    from picosdk.ps2000 import ps2000

    if not freqs_hz or all(a == 0 for a in amplitudes):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
        time.sleep(SETTLE_S)
        return

    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

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
    arb_buf = (ctypes.c_uint8 * ARB_LEN)(*arb_u8.tolist())
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase,
        0, 0, arb_buf, ARB_LEN, 0, 0
    )
    time.sleep(SETTLE_S)


def capture_spectrum(handle, readout_freqs):
    """Average N_AVG FFT captures, return magnitudes at readout freqs."""
    import cwm_picoscope
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE

    spectra = []
    for _ in range(N_AVG):
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
        if n <= 0:
            spectra.append(np.zeros(len(readout_freqs)))
            continue
        raw = np.array(buf_a[:n], dtype=np.float64)
        windowed = raw * np.hanning(len(raw))
        nfft = len(raw) * 4
        fft = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
        bin_hz = freq_axis[1] - freq_axis[0]
        mags = np.zeros(len(readout_freqs))
        for j, rf in enumerate(readout_freqs):
            tb = int(round(rf / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft) - 1, tb + 3)
            mags[j] = float(np.max(fft[lo:hi + 1]))
        spectra.append(mags)

    return np.mean(spectra, axis=0)


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation
# ═══════════════════════════════════════════════════════════════════════

def nmse(y_true, y_pred):
    var = np.var(y_true)
    return float(np.mean((y_true - y_pred) ** 2) / var) if var > 0 else float('inf')


def train_ridge(X_train, y_train):
    from sklearn.model_selection import KFold
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_train)
    best_alpha, best_cv = 1.0, float('inf')
    kf = KFold(n_splits=5, shuffle=False)
    for alpha in RIDGE_ALPHAS:
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
    return reg, scaler, best_alpha


def eval_ridge(reg, scaler, X_train, y_train, X_test, y_test, name):
    return {
        "name": name,
        "nmse_train": round(nmse(y_train, reg.predict(scaler.transform(X_train))), 6),
        "nmse_test": round(nmse(y_test, reg.predict(scaler.transform(X_test))), 6),
        "features": X_train.shape[1],
    }


def run_esn(X_input, y_train, y_test, n_train, name, rng, hidden=64):
    W_in = rng.uniform(-0.1, 0.1, (hidden, X_input.shape[1]))
    W_res = rng.normal(0, 1, (hidden, hidden))
    W_res *= 0.9 / np.max(np.abs(np.linalg.eigvals(W_res)))
    leak = 0.5
    X_esn = np.zeros((len(X_input), hidden))
    state = np.zeros(hidden)
    for i in range(len(X_input)):
        pre = np.tanh(W_in @ X_input[i] + W_res @ state)
        state = (1 - leak) * state + leak * pre
        X_esn[i] = state
    reg, sc, alpha = train_ridge(X_esn[:n_train], y_train)
    return eval_ridge(reg, sc, X_esn[:n_train], y_train,
                      X_esn[n_train:], y_test, name)


# ═══════════════════════════════════════════════════════════════════════
#  Main experiment
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 Hardware Virtual Rewrite")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--census", required=True)
    parser.add_argument("--plate", default="4_NE")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--all-open", action="store_true",
                        help="All NE relays open simultaneously")
    parser.add_argument("--fast", action="store_true",
                        help="5ms settle, 2 avg")
    args = parser.parse_args()

    if args.fast:
        global SETTLE_S, N_AVG
        SETTLE_S = 0.005
        N_AVG = 2

    rng = np.random.default_rng(args.seed)
    log("=== NARMA-10 Hardware Virtual Rewrite ===")
    log(f"Steps: {args.steps}  Seed: {args.seed}  Fast: {args.fast}")
    log(f"Feedback carrier: {FEEDBACK_FREQ/1000:.1f} kHz")

    # ── Load census ──
    census = json.load(open(args.census))
    census_modes = []
    results_data = census.get("results", {})
    if isinstance(results_data, dict):
        for plate_key, plate_data in results_data.items():
            if isinstance(plate_data, dict):
                for peak in plate_data.get("peaks", plate_data.get("modes", [])):
                    f = peak.get("freq_hz", peak.get("frequency_hz", 0))
                    if f > 0:
                        census_modes.append(f)
    elif isinstance(results_data, list):
        for plate_data in results_data:
            for peak in plate_data.get("peaks", plate_data.get("modes", [])):
                f = peak.get("freq_hz", peak.get("frequency_hz", 0))
                if f > 0:
                    census_modes.append(f)
    log(f"Census: {len(census_modes)} modes from {args.census}")

    # ── Readout frequencies ──
    # Compute for 10-carrier (no feedback) and 11-carrier (with feedback)
    carriers_10 = list(LADDER_CARRIERS_HZ)
    carriers_11 = carriers_10 + [FEEDBACK_FREQ]

    readout_10, labels_10, im_map_10 = compute_readout_freqs(
        carriers_10, MODE_CLUSTERS_HZ)
    readout_11, labels_11, im_map_11 = compute_readout_freqs(
        carriers_11, MODE_CLUSTERS_HZ)

    n_new_im = len(readout_11) - len(readout_10)
    log(f"Readout: {len(readout_10)} (10-carrier), {len(readout_11)} (11-carrier)")
    log(f"Feedback adds {n_new_im} new IM readout channels")

    # ── NARMA data ──
    u, y = generate_narma10(args.steps, rng)
    start = NARMA_ORDER + N_WASHOUT
    total_usable = args.steps - start - 1
    n_train = int(total_usable * 0.7)
    n_test = total_usable - n_train
    y_all = y[start:start + total_usable]
    y_tr, y_te = y_all[:n_train], y_all[n_train:]
    log(f"Data: {total_usable} usable ({n_train} train / {n_test} test)")

    # ── Open hardware ──
    from relay_mux import RelayMux
    handle = _open_scope()
    mux = RelayMux(args.port)
    mux.open()
    time.sleep(0.5)

    # Compute f_rep for ARB (must cover all 11 carriers)
    max_freq = max(carriers_11)
    f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))
    log(f"  f_rep = {f_rep:.1f} Hz")

    # Set up plate
    if args.all_open:
        log("  All-open mode: activating all NE relays...")
        mux.all_ne()
        time.sleep(SETTLE_RELAY_S)
    else:
        relay_ch, relay_name = RECEIVER_MAP[args.plate]
        log(f"  Single plate: {relay_name} (relay {relay_ch})")
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

    # ══════════════════════════════════════════════════════════════════
    #  PASS 1: No-feedback baseline (10 carriers)
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ PASS 1: No-feedback baseline (10 carriers) ═══")
    n_feats_10 = len(readout_10)
    X_nf = np.zeros((total_usable, n_feats_10))
    t0 = time.time()

    for idx in range(total_usable):
        t = start + idx
        if t < NARMA_ORDER:
            continue
        window = u[t - 9:t + 1]
        amps = list(window * 2.0)  # [0, 1] scale
        drive_multitone(handle, carriers_10, amps, f_rep)
        X_nf[idx] = capture_spectrum(handle, readout_10)

        if (idx + 1) % 20 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total_usable - idx - 1) / rate
            log(f"  {idx+1}/{total_usable} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_nf = time.time() - t0
    log(f"  Pass 1 done: {total_usable} steps in {elapsed_nf:.1f}s "
        f"({total_usable/elapsed_nf:.1f} steps/s)")

    # Save checkpoint
    np.savez(RESULTS_DIR / "hw_vr_pass1_checkpoint.npz",
             X_nf=X_nf, u=u, y=y, readout_10=np.array(readout_10),
             start=start, n_train=n_train, total_usable=total_usable)

    # ══════════════════════════════════════════════════════════════════
    #  PASS 2: Teacher-forced feedback (11 carriers, true y(t))
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ PASS 2: Teacher-forced feedback (11 carriers) ═══")
    log(f"  Encoding true y(t) on {FEEDBACK_FREQ/1000:.1f} kHz carrier")
    n_feats_11 = len(readout_11)
    X_tf = np.zeros((total_usable, n_feats_11))
    t0 = time.time()

    for idx in range(total_usable):
        t = start + idx
        if t < NARMA_ORDER:
            continue
        window = u[t - 9:t + 1]
        amps_u = list(window * 2.0)
        y_fb = np.clip(y[t], 0, 2) / 2.0  # true y(t) → [0, 1]
        amps_all = amps_u + [y_fb]
        drive_multitone(handle, carriers_11, amps_all, f_rep)
        X_tf[idx] = capture_spectrum(handle, readout_11)

        if (idx + 1) % 20 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total_usable - idx - 1) / rate
            log(f"  {idx+1}/{total_usable} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_tf = time.time() - t0
    log(f"  Pass 2 done: {total_usable} steps in {elapsed_tf:.1f}s "
        f"({total_usable/elapsed_tf:.1f} steps/s)")

    # Save checkpoint
    np.savez(RESULTS_DIR / "hw_vr_pass2_checkpoint.npz",
             X_tf=X_tf, u=u, y=y, readout_11=np.array(readout_11),
             start=start, n_train=n_train, total_usable=total_usable)

    # ══════════════════════════════════════════════════════════════════
    #  PASS 3: Closed-loop feedback (11 carriers, predicted ŷ(t))
    #  Train model on Pass 2, then re-drive with predictions.
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ PASS 3: Closed-loop feedback (predicted ŷ) ═══")

    # Train readout on teacher-forced data (spectrum + window, NO raw y)
    win = np.array([u[start + i - 9:start + i + 1] for i in range(total_usable)])
    X_tf_win = np.hstack([X_tf, win])
    reg_cl, sc_cl, alpha_cl = train_ridge(X_tf_win[:n_train], y_tr)
    log(f"  Ridge α = {alpha_cl}")

    # Teacher-forced open-loop score (sanity check)
    r_ol = eval_ridge(reg_cl, sc_cl, X_tf_win[:n_train], y_tr,
                      X_tf_win[n_train:], y_te, "CL_openloop_check")
    log(f"  Open-loop (teacher): test NMSE = {r_ol['nmse_test']:.4f}")

    # Closed-loop: first n_train steps use teacher predictions,
    # test steps re-drive with predicted ŷ
    X_cl = np.zeros((n_test, n_feats_11))
    y_pred = np.zeros(total_usable)
    y_pred[:n_train] = reg_cl.predict(sc_cl.transform(X_tf_win[:n_train]))

    t0 = time.time()
    for idx in range(n_test):
        t = start + n_train + idx
        window = u[t - 9:t + 1]
        amps_u = list(window * 2.0)

        # Use PREDICTED y from previous step
        prev_idx = n_train + idx - 1
        y_fb = np.clip(y_pred[prev_idx], 0, 2) / 2.0
        amps_all = amps_u + [y_fb]

        drive_multitone(handle, carriers_11, amps_all, f_rep)
        spec = capture_spectrum(handle, readout_11)
        X_cl[idx] = spec

        feat = np.concatenate([spec, window])
        y_pred[n_train + idx] = reg_cl.predict(
            sc_cl.transform(feat.reshape(1, -1)))[0]

        if (idx + 1) % 20 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (n_test - idx - 1) / rate
            log(f"  {idx+1}/{n_test} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_cl = time.time() - t0
    log(f"  Pass 3 done: {n_test} steps in {elapsed_cl:.1f}s")

    # ── Close hardware ──
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps2000.ps2000_close_unit(handle)
    mux.close()
    log("  Hardware closed.")

    # ══════════════════════════════════════════════════════════════════
    #  Evaluation
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ Evaluation ═══")
    results = []

    # -- No-feedback approaches --
    X_nf_win = np.hstack([X_nf, win])

    # A1: no-feedback spectrum only
    reg, sc, al = train_ridge(X_nf[:n_train], y_tr)
    r = eval_ridge(reg, sc, X_nf[:n_train], y_tr, X_nf[n_train:], y_te,
                   "A1_no_fb_spectrum")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_test']:.4f}")

    # A2: no-feedback spectrum + window
    reg, sc, al = train_ridge(X_nf_win[:n_train], y_tr)
    r = eval_ridge(reg, sc, X_nf_win[:n_train], y_tr, X_nf_win[n_train:], y_te,
                   "A2_no_fb_spec_window")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_test']:.4f}")

    # A3: software ESN
    r = run_esn(win, y_tr, y_te, n_train, "A3_software_esn", rng)
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_test']:.4f}")

    # A4: no-feedback plate → ESN (resid combo like narma_ladder)
    n_bins = 10
    u_current = np.array([u[start + i] for i in range(total_usable)])
    bin_edges = np.linspace(0, 0.5, n_bins + 1)
    bin_idx = np.digitize(u_current, bin_edges) - 1
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)
    templates_nf = np.zeros((n_bins, X_nf.shape[1]))
    for b in range(n_bins):
        mask = (bin_idx[:n_train] == b)
        if mask.any():
            templates_nf[b] = X_nf[:n_train][mask].mean(axis=0)
    X_resid_nf = X_nf - templates_nf[bin_idx]
    r = run_esn(X_resid_nf, y_tr, y_te, n_train, "A4_resid_nofb_esn", rng)
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_test']:.4f}")

    # -- Teacher-forced feedback approaches --
    # C1: teacher IM spectrum + window (THE key test)
    r_c1 = eval_ridge(reg_cl, sc_cl, X_tf_win[:n_train], y_tr,
                       X_tf_win[n_train:], y_te, "C1_teacher_im_openloop")
    results.append(r_c1)
    log(f"  {r_c1['name']:<35s} {r_c1['nmse_test']:.4f}")

    # C2: teacher IM → ESN
    r = run_esn(X_tf, y_tr, y_te, n_train, "C2_teacher_im_esn", rng)
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_test']:.4f}")

    # C3: teacher IM residual → ESN
    templates_tf = np.zeros((n_bins, X_tf.shape[1]))
    for b in range(n_bins):
        mask = (bin_idx[:n_train] == b)
        if mask.any():
            templates_tf[b] = X_tf[:n_train][mask].mean(axis=0)
    X_resid_tf = X_tf - templates_tf[bin_idx]
    r = run_esn(X_resid_tf, y_tr, y_te, n_train, "C3_teacher_resid_esn", rng)
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_test']:.4f}")

    # -- Closed-loop result --
    nm_cl = nmse(y_te, y_pred[n_train:])
    results.append({"name": "D1_closedloop_im",
                    "nmse_test": round(nm_cl, 6),
                    "features": n_feats_11 + NARMA_ORDER})
    log(f"  {'D1_closedloop_im':<35s} {nm_cl:.4f}")

    # -- Comparison: spectrum difference (feedback - no-feedback) --
    # The DIFFERENCE isolates what the feedback carrier contributed
    if n_feats_11 == n_feats_10:
        X_diff = X_tf - X_nf  # pure feedback contribution
        X_diff_win = np.hstack([X_diff, win])
        reg, sc, al = train_ridge(X_diff_win[:n_train], y_tr)
        r = eval_ridge(reg, sc, X_diff_win[:n_train], y_tr,
                       X_diff_win[n_train:], y_te, "E1_feedback_diff")
        results.append(r)
        log(f"  {r['name']:<35s} {r['nmse_test']:.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  Summary
    # ══════════════════════════════════════════════════════════════════
    log("\n" + "═" * 62)
    log("  RESULTS — Hardware Virtual Rewrite NARMA-10")
    log("═" * 62)
    log(f"  {'Approach':<35s} {'NMSE':>8s}")
    log("  " + "─" * 45)
    for r in results:
        log(f"  {r['name']:<35s} {r.get('nmse_test', 999):.4f}")

    key_delta = ""
    nf = next((r for r in results if "A1" in r["name"]), None)
    c1 = next((r for r in results if "C1" in r["name"]), None)
    if nf and c1:
        d = nf["nmse_test"] - c1["nmse_test"]
        key_delta = f"IM feedback vs no-feedback: {nf['nmse_test']:.4f} → {c1['nmse_test']:.4f} (Δ={d:+.4f})"
        log(f"\n  {key_delta}")

    # ── Save ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": "narma_hw_virtual_rewrite.py",
        "concept": "Track A virtual rewrite on hardware",
        "steps": args.steps, "seed": args.seed,
        "fast": args.fast, "all_open": args.all_open,
        "plate": args.plate if not args.all_open else "all_NE",
        "feedback_freq_hz": FEEDBACK_FREQ,
        "carriers_10": carriers_10, "carriers_11": carriers_11,
        "n_readout_10": len(readout_10), "n_readout_11": len(readout_11),
        "n_train": n_train, "n_test": n_test,
        "pass1_time_s": round(elapsed_nf, 1),
        "pass2_time_s": round(elapsed_tf, 1),
        "pass3_time_s": round(elapsed_cl, 1),
        "results": results,
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = RESULTS_DIR / f"narma10_hw_virtual_rewrite_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nSaved → {outfile}")


if __name__ == "__main__":
    main()
