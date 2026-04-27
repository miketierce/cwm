#!/usr/bin/env python3
"""
NARMA-10 Hardware Volterra — Delay-Line + y-History Encoding

Key insight from colorburst v2 (0.293 NMSE):
  - The plate already gets the full u-history via delay-line encoding
    (carrier k = u(t-9+k)), giving input×input IM products
  - It also gets y(t) via feedback carrier, giving input×y(t) IM
  - MISSING: the NARMA term 0.05·y(t)·Σy(t-i) requires y-HISTORY
  - Solution: add a 12th carrier encoding mean(y[t-1:t-9])
  - IM product between y(t)@53.9kHz and y_sum@16kHz gives y(t)×Σy(t-i)
  - This is the EXACT term NARMA-10 needs that we couldn't compute before

Architecture:
  10 carriers: u(t-9)..u(t) at INPUT_CARRIERS_HZ (same as v2)
  Carrier 11: y(t) @ 53.9 kHz (amplitude-encoded, same as v2)
  Carrier 12: mean(y[t-1]..y[t-9]) @ 16 kHz (NEW — y-history summary)

  IM products this unlocks:
    |53.9 - 16| = 37.9 kHz → y(t) × y_sum  [the missing NARMA term!]
    |16 - 19| = 3.0 kHz → y_sum × u(t-9)
    |16 - 58.5| = 42.5 kHz → y_sum × u(t)
    16 + 53.9 = 69.9 kHz → y(t) × y_sum (sum)
    etc.

Design:
  Pass 1: 11 carriers (10u + y(t)) — reproduce v2 within same session
  Pass 2: 12 carriers (10u + y(t) + y_sum) — the Volterra test

Usage:
  DYLD_LIBRARY_PATH="..." python tools/narma_hw_volterra.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_cross_20260418_142222.json \\
      [--steps 1000] [--all-open]
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

N_AVG = 4
SETTLE_S = 0.050
SETTLE_RELAY_S = 0.10
AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096

RIDGE_ALPHAS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

# 10 input carriers (delay-line: carrier k = u(t-9+k))
INPUT_CARRIERS_HZ = [
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]

# Feedback carrier: y(t) amplitude-encoded
FEEDBACK_FREQ = 53_900

# NEW: y-history carrier: mean(y[t-1]..y[t-9])
Y_HISTORY_FREQ = 16_000

# Phase reference: 19 kHz (always driven)
PHASE_REF_FREQ = 19_000

# Carrier sets
CARRIERS_11 = INPUT_CARRIERS_HZ + [FEEDBACK_FREQ]         # v2 reproduction
CARRIERS_12 = INPUT_CARRIERS_HZ + [FEEDBACK_FREQ, Y_HISTORY_FREQ]  # Volterra

# Readout bins: mode clusters + feedback IM + y-history IM + broadband
MODE_CLUSTERS_HZ = [
    11_425, 15_100, 16_000, 17_375, 19_000, 23_900, 29_200, 29_900,
    31_600, 33_225, 34_550, 36_000, 37_000, 42_300, 45_000, 47_800,
    49_600, 51_500, 53_900, 56_200, 58_500, 62_000, 65_075, 68_200,
    70_800, 73_500, 76_200, 78_800, 81_500, 84_200, 86_900, 89_400,
    95_000,
]

# Feedback IM bins (from v2)
FEEDBACK_IM_HZ = [
    2_300, 4_300, 4_500, 4_600, 5_900, 6_100, 8_900,
    16_900, 20_100, 24_700,
    98_900, 103_500, 110_100, 112_400,
]

# NEW y-history IM bins: 16 kHz × feedback and inputs
Y_HISTORY_IM_HZ = [
    3_000,   # |19 - 16|
    7_900,   # |23.9 - 16|
    13_200,  # |29.2 - 16|
    13_900,  # |29.9 - 16|
    18_550,  # |34.55 - 16|
    21_000,  # |37 - 16|
    37_900,  # |53.9 - 16| ← THE KEY PRODUCT: y(t) × y_sum
    39_900,  # |23.9 + 16|
    69_900,  # |53.9 + 16| ← y(t) × y_sum (sum tone)
    74_500,  # |58.5 + 16|
]

IM_TOL_PCT = 2.0

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

def build_readout():
    """Build readout: modes + feedback IM + y-history IM + broadband."""
    freqs = set(MODE_CLUSTERS_HZ)
    freqs.update(FEEDBACK_IM_HZ)
    freqs.update(Y_HISTORY_IM_HZ)
    # Broadband 100-200 kHz
    for f in range(100_000, 200_001, 5_000):
        freqs.add(f)
    return sorted(freqs)


def classify_bins(readout_freqs):
    """Classify bins into categories for ablation studies."""
    tol = IM_TOL_PCT / 100
    rf = np.array(readout_freqs, dtype=float)
    n = len(rf)

    def hits(im_f):
        if im_f < 1000 or im_f > 390_000:
            return np.zeros(n, dtype=bool)
        return np.abs(rf - im_f) / np.maximum(rf, im_f) < tol

    masks = {
        'all': np.ones(n, dtype=bool),
        'input_only': np.zeros(n, dtype=bool),
        'feedback_im': np.zeros(n, dtype=bool),
        'yhistory_im': np.zeros(n, dtype=bool),
    }

    inp = INPUT_CARRIERS_HZ

    # Input×input IM products
    for i in range(len(inp)):
        for j in range(len(inp)):
            if i == j:
                continue
            for im_f in [abs(inp[i] - inp[j]), inp[i] + inp[j],
                         abs(2*inp[i] - inp[j])]:
                masks['input_only'] |= hits(im_f)
    for f in inp:
        masks['input_only'] |= hits(f)

    # Feedback × input IM products (y(t) × u(t-k))
    fb = FEEDBACK_FREQ
    for fi in inp:
        for im_f in [abs(fb - fi), fb + fi, abs(2*fb - fi), abs(2*fi - fb)]:
            masks['feedback_im'] |= hits(im_f)
    masks['feedback_im'] |= hits(fb)

    # Y-history × everything IM products (y_sum × u(t-k), y_sum × y(t))
    yh = Y_HISTORY_FREQ
    for fi in inp + [fb]:
        for im_f in [abs(yh - fi), yh + fi, abs(2*yh - fi), abs(2*fi - yh)]:
            masks['yhistory_im'] |= hits(im_f)
    masks['yhistory_im'] |= hits(yh)

    # Key product: y(t) × y_sum
    masks['volterra_key'] = hits(abs(fb - yh)) | hits(fb + yh)

    # Interleaved: bins hit by feedback or y-history IM but NOT input-only
    masks['new_info'] = (masks['feedback_im'] | masks['yhistory_im']) & ~masks['input_only']
    return masks


# ═══════════════════════════════════════════════════════════════════════
#  Hardware interface
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


def drive_multitone(handle, freqs_hz, amplitudes, f_rep):
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


def capture_complex(handle, readout_freqs, ref_bin_idx):
    """Average N_AVG captures, return magnitude + phase-referenced Re/Im."""
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE

    complex_sum = np.zeros(len(readout_freqs), dtype=np.complex128)
    mag_sum = np.zeros(len(readout_freqs))

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
            continue

        raw = np.array(buf_a[:n], dtype=np.float64)
        windowed = raw * np.hanning(len(raw))
        nfft = len(raw) * 4
        fft_c = np.fft.rfft(windowed, n=nfft)
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
        bin_hz = freq_axis[1] - freq_axis[0]

        vals = np.zeros(len(readout_freqs), dtype=np.complex128)
        for j, rf in enumerate(readout_freqs):
            tb = int(round(rf / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft_c) - 1, tb + 3)
            pk = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
            vals[j] = fft_c[pk]

        mag_sum += np.abs(vals)
        ref_val = vals[ref_bin_idx]
        if abs(ref_val) > 0:
            vals *= np.exp(-1j * np.angle(ref_val))
        complex_sum += vals

    mags = mag_sum / N_AVG
    avg_c = complex_sum / N_AVG
    return mags, np.real(avg_c), np.imag(avg_c)


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


def eval_features(X, y_tr, y_te, n_train, name):
    """Train ridge on features and return result dict."""
    reg, sc, alpha = train_ridge(X[:n_train], y_tr)
    pred_te = reg.predict(sc.transform(X[n_train:]))
    return {
        "name": name,
        "nmse_test": round(nmse(y_te, pred_te), 6),
        "features": X.shape[1],
        "alpha": alpha,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 Hardware Volterra — y-History Encoding")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--census", required=True)
    parser.add_argument("--plate", default="4_NE")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--all-open", action="store_true")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    log("╔══════════════════════════════════════════════════════════════╗")
    log("║   NARMA-10 Volterra — y-History Delay-Line Encoding        ║")
    log("╚══════════════════════════════════════════════════════════════╝")
    log(f"Steps: {args.steps}  Seed: {args.seed}")
    log(f"Settings: {N_AVG} avg, {SETTLE_S*1000:.0f}ms settle")
    log(f"Feedback: {FEEDBACK_FREQ/1000:.1f} kHz (y(t))")
    log(f"Y-history: {Y_HISTORY_FREQ/1000:.1f} kHz (mean(y[t-1:t-9]))")
    log(f"Key IM product: |{FEEDBACK_FREQ/1000:.1f} - {Y_HISTORY_FREQ/1000:.1f}| = "
        f"{abs(FEEDBACK_FREQ - Y_HISTORY_FREQ)/1000:.1f} kHz → y(t)×Σy(past)")

    # ── Readout setup ──
    readout = build_readout()
    n_readout = len(readout)

    ref_bin_idx = None
    for idx, rf in enumerate(readout):
        if abs(rf - PHASE_REF_FREQ) / PHASE_REF_FREQ < 0.02:
            ref_bin_idx = idx
            break
    if ref_bin_idx is None:
        raise RuntimeError("19 kHz ref not in readout!")

    masks = classify_bins(readout)
    n_fb_im = int(masks['feedback_im'].sum())
    n_yh_im = int(masks['yhistory_im'].sum())
    n_new = int(masks['new_info'].sum())
    n_volterra_key = int(masks['volterra_key'].sum())
    log(f"Readout: {n_readout} bins")
    log(f"  Feedback-IM: {n_fb_im}  Y-history-IM: {n_yh_im}")
    log(f"  New-info (not input-only): {n_new}")
    log(f"  Volterra key bins (y×y_sum): {n_volterra_key}")

    # ── NARMA data ──
    u, y = generate_narma10(args.steps, rng)
    start = NARMA_ORDER + N_WASHOUT
    total_usable = args.steps - start - 1
    n_train = int(total_usable * 0.7)
    n_test = total_usable - n_train
    y_target = y[start + 1:start + total_usable + 1]  # predict y(t+1)
    y_tr, y_te = y_target[:n_train], y_target[n_train:]
    # Input window features (u delay-line values — matches what carriers encode)
    win = np.array([u[start + i - 9:start + i + 1] for i in range(total_usable)])
    # y-state features for software ablation
    y_state = np.column_stack([
        y[start:start + total_usable],  # y(t)
        [np.mean(y[start + i - 9:start + i]) for i in range(total_usable)],  # mean(y_past)
    ])
    log(f"Data: {total_usable} usable ({n_train} train / {n_test} test)")

    # ── Open hardware ──
    from relay_mux import RelayMux
    handle = _open_scope()
    mux = RelayMux(args.port)
    mux.open()
    time.sleep(0.5)

    max_freq = max(CARRIERS_12)
    f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))
    log(f"  f_rep = {f_rep:.1f} Hz")

    if args.all_open:
        log("  All-open mode: all NE relays...")
        mux.all_ne()
        time.sleep(SETTLE_RELAY_S)
    else:
        relay_ch, relay_name = RECEIVER_MAP[args.plate]
        log(f"  Plate: {relay_name} (relay {relay_ch})")
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

    # ══════════════════════════════════════════════════════════════════
    #  PASS 1: 11 carriers (v2 reproduction: 10u + y(t))
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ PASS 1: 11 carriers (10u + y(t)) — v2 reproduction ═══")

    X_p1_mag = np.zeros((total_usable, n_readout))
    X_p1_re = np.zeros((total_usable, n_readout))
    X_p1_im = np.zeros((total_usable, n_readout))
    t0 = time.time()

    for idx in range(total_usable):
        t = start + idx
        u_window = u[t - 9:t + 1]
        amps_u = list(u_window * 2.0)
        y_fb = np.clip(y[t], 0, 2) / 2.0
        amps = amps_u + [y_fb]

        drive_multitone(handle, CARRIERS_11, amps, f_rep)
        mags, reals, imags = capture_complex(handle, readout, ref_bin_idx)
        X_p1_mag[idx] = mags
        X_p1_re[idx] = reals
        X_p1_im[idx] = imags

        if (idx + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total_usable - idx - 1) / rate
            log(f"  {idx+1}/{total_usable} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_p1 = time.time() - t0
    log(f"  Pass 1 done: {elapsed_p1:.1f}s ({total_usable/elapsed_p1:.1f} steps/s)")

    np.savez(RESULTS_DIR / "hw_volterra_pass1.npz",
             X_mag=X_p1_mag, X_re=X_p1_re, X_im=X_p1_im,
             u=u, y=y, readout=np.array(readout),
             start=start, n_train=n_train, total_usable=total_usable)

    # ══════════════════════════════════════════════════════════════════
    #  PASS 2: 12 carriers (10u + y(t) + y_sum) — Volterra
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ PASS 2: 12 carriers (10u + y(t) + y_sum) — Volterra ═══")
    log(f"  y(t) → {FEEDBACK_FREQ/1000:.1f} kHz amplitude")
    log(f"  mean(y_past) → {Y_HISTORY_FREQ/1000:.1f} kHz amplitude")

    X_p2_mag = np.zeros((total_usable, n_readout))
    X_p2_re = np.zeros((total_usable, n_readout))
    X_p2_im = np.zeros((total_usable, n_readout))
    t0 = time.time()

    for idx in range(total_usable):
        t = start + idx
        u_window = u[t - 9:t + 1]
        amps_u = list(u_window * 2.0)
        y_fb = np.clip(y[t], 0, 2) / 2.0
        # y-history: mean of past 9 y-values (t-9 to t-1)
        y_past = y[t - 9:t]  # 9 values
        y_sum_amp = np.clip(np.mean(y_past), 0, 2) / 2.0
        amps = amps_u + [y_fb, y_sum_amp]

        drive_multitone(handle, CARRIERS_12, amps, f_rep)
        mags, reals, imags = capture_complex(handle, readout, ref_bin_idx)
        X_p2_mag[idx] = mags
        X_p2_re[idx] = reals
        X_p2_im[idx] = imags

        if (idx + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total_usable - idx - 1) / rate
            log(f"  {idx+1}/{total_usable} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_p2 = time.time() - t0
    log(f"  Pass 2 done: {elapsed_p2:.1f}s ({total_usable/elapsed_p2:.1f} steps/s)")

    np.savez(RESULTS_DIR / "hw_volterra_pass2.npz",
             X_mag=X_p2_mag, X_re=X_p2_re, X_im=X_p2_im,
             u=u, y=y, readout=np.array(readout),
             start=start, n_train=n_train, total_usable=total_usable)

    # ── Close hardware ──
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps2000.ps2000_close_unit(handle)
    mux.close()
    log("\n  Hardware closed.")

    # ══════════════════════════════════════════════════════════════════
    #  EVALUATION
    # ══════════════════════════════════════════════════════════════════
    log("\n═══════════════════════════════════════════════════════════════")
    log("  EVALUATION — Volterra ablation")
    log("═══════════════════════════════════════════════════════════════")
    results = []

    fb_m = masks['feedback_im']
    yh_m = masks['yhistory_im']
    new_m = masks['new_info']
    vk_m = masks['volterra_key']

    # ── Pass 1 (11 carriers, v2 reproduction) ──
    # A: plate mag + u_window (same as v2 B1)
    results.append(eval_features(
        np.hstack([X_p1_mag, win]), y_tr, y_te, n_train,
        "A1_p1_mag+uwin"))

    # B: plate mag + u_window + y_state (software y-history)
    results.append(eval_features(
        np.hstack([X_p1_mag, win, y_state]), y_tr, y_te, n_train,
        "A2_p1_mag+uwin+ystate"))

    # C: feedback-IM bins only + u_window
    results.append(eval_features(
        np.hstack([X_p1_mag[:, fb_m], win]), y_tr, y_te, n_train,
        "A3_p1_fbIM+uwin"))

    # ── Pass 2 (12 carriers, Volterra) ──
    # D: plate mag + u_window (same evaluation as v2 B1, but 12 carriers)
    results.append(eval_features(
        np.hstack([X_p2_mag, win]), y_tr, y_te, n_train,
        "B1_p2_mag+uwin"))

    # E: plate mag + u_window + y_state
    results.append(eval_features(
        np.hstack([X_p2_mag, win, y_state]), y_tr, y_te, n_train,
        "B2_p2_mag+uwin+ystate"))

    # F: feedback-IM + y-history-IM bins + u_window
    results.append(eval_features(
        np.hstack([X_p2_mag[:, fb_m | yh_m], win]), y_tr, y_te, n_train,
        "B3_p2_fb+yh_IM+uwin"))

    # G: y-history IM bins only + u_window
    results.append(eval_features(
        np.hstack([X_p2_mag[:, yh_m], win]), y_tr, y_te, n_train,
        "B4_p2_yhIM_only+uwin"))

    # H: Volterra key bins only (y(t)×y_sum product) + u_window
    if vk_m.any():
        results.append(eval_features(
            np.hstack([X_p2_mag[:, vk_m], win]), y_tr, y_te, n_train,
            "B5_p2_volterra_key+uwin"))

    # I: new-info bins (not input-only) + u_window
    results.append(eval_features(
        np.hstack([X_p2_mag[:, new_m], win]), y_tr, y_te, n_train,
        "B6_p2_new_info+uwin"))

    # J: Spectrum difference Pass2 - Pass1 (isolates y_sum contribution)
    X_diff = X_p2_mag - X_p1_mag
    results.append(eval_features(
        np.hstack([X_diff, win]), y_tr, y_te, n_train,
        "C1_diff_p2-p1+uwin"))

    # K: Diff at y-history IM bins
    results.append(eval_features(
        np.hstack([X_diff[:, yh_m], win]), y_tr, y_te, n_train,
        "C2_diff_yhIM+uwin"))

    # L: Concat Pass1 + Pass2 (all info)
    results.append(eval_features(
        np.hstack([X_p1_mag, X_p2_mag, win]), y_tr, y_te, n_train,
        "D1_concat_p1+p2+uwin"))

    # M: Pass2 all + y_state + u_window (max info)
    results.append(eval_features(
        np.hstack([X_p2_mag, win, y_state]), y_tr, y_te, n_train,
        "D2_p2_all+ystate+uwin"))

    # N: Software-only baseline (just u_window + y_state, no plate)
    results.append(eval_features(
        np.hstack([win, y_state]), y_tr, y_te, n_train,
        "E1_software_only"))

    # O: Software-only with polynomial features
    poly_feats = np.column_stack([
        y_state[:, 0] * y_state[:, 1],       # y(t) × y_sum
        u[start:start + total_usable] * u[start - 9:start + total_usable - 9],  # u(t)×u(t-9)
        y_state[:, 0] ** 2,                   # y(t)²
    ])
    results.append(eval_features(
        np.hstack([win, y_state, poly_feats]), y_tr, y_te, n_train,
        "E2_sw_poly"))

    # ══════════════════════════════════════════════════════════════════
    #  Summary
    # ══════════════════════════════════════════════════════════════════
    log("\n" + "═" * 70)
    log("  RESULTS — Volterra NARMA-10")
    log("═" * 70)
    log(f"  {'Approach':<35s} {'Feats':>5s} {'NMSE':>8s} {'α':>8s}")
    log("  " + "─" * 58)
    for r in sorted(results, key=lambda x: x['nmse_test']):
        log(f"  {r['name']:<35s} {r['features']:5d} "
            f"{r['nmse_test']:.4f} {r.get('alpha', ''):>8}")

    # Key comparisons
    log("\n  KEY COMPARISONS:")
    def find(prefix):
        return next((r for r in results if r['name'].startswith(prefix)), None)

    a1 = find("A1")
    b1 = find("B1")
    a2 = find("A2")
    b2 = find("B2")

    if a1 and b1:
        log(f"  11-carrier → 12-carrier (mag+uwin): "
            f"{a1['nmse_test']:.4f} → {b1['nmse_test']:.4f} "
            f"(Δ={a1['nmse_test'] - b1['nmse_test']:+.4f})")
    if a2 and b2:
        log(f"  11-carrier → 12-carrier (+ystate):  "
            f"{a2['nmse_test']:.4f} → {b2['nmse_test']:.4f} "
            f"(Δ={a2['nmse_test'] - b2['nmse_test']:+.4f})")
    if a1 and a2:
        log(f"  Without → with y_state (11-car):    "
            f"{a1['nmse_test']:.4f} → {a2['nmse_test']:.4f} "
            f"(Δ={a1['nmse_test'] - a2['nmse_test']:+.4f})")

    e1 = find("E1")
    if e1 and b1:
        log(f"  Software-only → plate+12car:        "
            f"{e1['nmse_test']:.4f} → {b1['nmse_test']:.4f} "
            f"(Δ={e1['nmse_test'] - b1['nmse_test']:+.4f})")

    best = min(results, key=lambda x: x['nmse_test'])
    log(f"\n  ★ BEST: {best['name']} = {best['nmse_test']:.4f}")
    log(f"  (v2 best was 0.2926)")

    # ── Save ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": "narma_hw_volterra.py",
        "concept": "Volterra: 12 carriers with y-history summary for y(t)×Σy(past) product",
        "steps": args.steps,
        "seed": args.seed,
        "all_open": args.all_open,
        "plate": args.plate if not args.all_open else "all_NE",
        "n_avg": N_AVG,
        "settle_ms": SETTLE_S * 1000,
        "feedback_freq_hz": FEEDBACK_FREQ,
        "y_history_freq_hz": Y_HISTORY_FREQ,
        "n_readout": n_readout,
        "n_feedback_im": n_fb_im,
        "n_yhistory_im": n_yh_im,
        "n_new_info": n_new,
        "n_volterra_key": n_volterra_key,
        "n_train": n_train,
        "n_test": n_test,
        "pass1_time_s": round(elapsed_p1, 1),
        "pass2_time_s": round(elapsed_p2, 1),
        "results": results,
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = RESULTS_DIR / f"narma10_hw_volterra_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nSaved → {outfile}")


if __name__ == "__main__":
    main()
