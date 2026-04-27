#!/usr/bin/env python3
"""
NARMA-10 Hardware Colorburst v2 — Refined Virtual Rewrite

Lessons from colorburst v1:
  - Phase encoding lost to nonlinear medium (plate distorts phase)
  - Reference carrier ate AWG headroom (12 carriers → diluted)
  - Interleaved bins DID beat baseline (frequency interleaving works)
  - Amplitude feedback (B1=0.597) still beats no-feedback (A1=0.628)

v2 refinements:
  1. DROP reference carrier → 11 carriers (more AWG headroom)
  2. Use 19 kHz INPUT carrier as implicit phase reference (free)
  3. Complex FFT readout phase-referenced to 19 kHz
  4. Expanded readout: 33 mode + 14 feedback-IM + broadband = 68 bins
  5. 4 averages, 50ms settle (better SNR than --fast)
  6. Feature ablation: mag, complex, feedback-IM, interleaved
  7. Reuse v1 Pass 1 baseline data

Usage:
  DYLD_LIBRARY_PATH="..." python tools/narma_hw_colorburst_v2.py \\
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

N_AVG = 4          # 4 averages (better than --fast's 2, not as slow as 8)
SETTLE_S = 0.050   # 50ms settle
SETTLE_RELAY_S = 0.10
AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096

RIDGE_ALPHAS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

# 10 input carriers
INPUT_CARRIERS_HZ = [
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]

# Feedback carrier: amplitude-encoded y(t)
FEEDBACK_FREQ = 53_900

# Phase reference: 19 kHz (INPUT carrier, always driven, zero cost)
PHASE_REF_FREQ = 19_000

# Plate mode clusters
MODE_CLUSTERS_HZ = [
    11_425, 15_100, 16_000, 17_375, 19_000, 23_900, 29_200, 29_900,
    31_600, 33_225, 34_550, 36_000, 37_000, 42_300, 45_000, 47_800,
    49_600, 51_500, 53_900, 56_200, 58_500, 62_000, 65_075, 68_200,
    70_800, 73_500, 76_200, 78_800, 81_500, 84_200, 86_900, 89_400,
    95_000,
]

# Feedback-specific IM bins NOT on mode clusters
FEEDBACK_IM_NEW_HZ = [
    2_300, 4_300, 4_500, 4_600, 5_900, 6_100, 8_900,
    16_900, 20_100, 24_700,
    98_900, 103_500, 110_100, 112_400,
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
#  Readout frequency computation (expanded: 68 bins)
# ═══════════════════════════════════════════════════════════════════════

def build_expanded_readout():
    """Build expanded readout: modes + feedback IM + broadband = ~68 bins."""
    freqs = set(MODE_CLUSTERS_HZ)
    freqs.update(FEEDBACK_IM_NEW_HZ)
    for f in range(100_000, 200_001, 5_000):
        freqs.add(f)
    return sorted(freqs)


def classify_bins(readout_freqs):
    """Classify bins into input-IM, feedback-IM, interleaved.

    Directly computes all IM products and checks which readout bins they hit.
    """
    tol = IM_TOL_PCT / 100
    rf = np.array(readout_freqs, dtype=float)
    n = len(rf)

    def hits(im_f):
        if im_f < 1000 or im_f > 390_000:
            return np.zeros(n, dtype=bool)
        return np.abs(rf - im_f) / np.maximum(rf, im_f) < tol

    masks = {
        'all':         np.ones(n, dtype=bool),
        'input_only':  np.zeros(n, dtype=bool),
        'feedback_im': np.zeros(n, dtype=bool),
    }

    # Input×input IM products
    inp = INPUT_CARRIERS_HZ
    for i in range(len(inp)):
        for j in range(len(inp)):
            if i == j:
                continue
            for im_f in [abs(inp[i] - inp[j]), inp[i] + inp[j],
                         abs(2*inp[i] - inp[j])]:
                masks['input_only'] |= hits(im_f)
    # Mark input carrier fundamentals too
    for f in inp:
        masks['input_only'] |= hits(f)

    # Feedback × input IM products
    fb = FEEDBACK_FREQ
    all_c = inp + [fb]
    for fi in all_c:
        if fi == fb:
            continue
        for im_f in [abs(fb - fi), fb + fi,
                     abs(2*fb - fi), abs(2*fi - fb)]:
            masks['feedback_im'] |= hits(im_f)
    # Feedback fundamental
    masks['feedback_im'] |= hits(fb)

    masks['interleaved'] = masks['feedback_im'] & ~masks['input_only']
    return masks


# ═══════════════════════════════════════════════════════════════════════
#  Hardware interface
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
    """Average N_AVG captures, return magnitude + phase-referenced Re/Im.

    Phase reference: 19 kHz input carrier (always driven).
    """
    import cwm_picoscope
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

        # Magnitude (capture-averaged separately for stability)
        mag_sum += np.abs(vals)

        # Phase-reference to 19 kHz carrier, then accumulate complex
        ref_val = vals[ref_bin_idx]
        if abs(ref_val) > 0:
            vals *= np.exp(-1j * np.angle(ref_val))
        complex_sum += vals

    mags = mag_sum / N_AVG
    avg_c = complex_sum / N_AVG
    reals = np.real(avg_c)
    imags = np.imag(avg_c)
    return mags, reals, imags


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
    pred_tr = reg.predict(sc.transform(X[:n_train]))
    pred_te = reg.predict(sc.transform(X[n_train:]))
    return {
        "name": name,
        "nmse_train": round(nmse(y_tr, pred_tr), 6),
        "nmse_test": round(nmse(y_te, pred_te), 6),
        "features": X.shape[1],
        "alpha": alpha,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 Hardware Colorburst v2 — Refined")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--census", required=True)
    parser.add_argument("--plate", default="4_NE")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--all-open", action="store_true")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    log("╔══════════════════════════════════════════════════════════════╗")
    log("║    NARMA-10 Colorburst v2 — Refined Virtual Rewrite        ║")
    log("╚══════════════════════════════════════════════════════════════╝")
    log(f"Steps: {args.steps}  Seed: {args.seed}")
    log(f"Settings: {N_AVG} avg, {SETTLE_S*1000:.0f}ms settle")
    log(f"Feedback: {FEEDBACK_FREQ/1000:.1f} kHz (amplitude-encoded y(t))")
    log(f"Phase ref: {PHASE_REF_FREQ/1000:.1f} kHz (input carrier, zero cost)")

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
    log(f"Census: {len(census_modes)} modes")

    # ── Readout setup ──
    carriers_11 = list(INPUT_CARRIERS_HZ) + [FEEDBACK_FREQ]
    readout = build_expanded_readout()
    n_readout = len(readout)

    # Find reference bin
    ref_bin_idx = None
    for idx, rf in enumerate(readout):
        if abs(rf - PHASE_REF_FREQ) / PHASE_REF_FREQ < 0.02:
            ref_bin_idx = idx
            break
    if ref_bin_idx is None:
        raise RuntimeError("19 kHz ref not in readout!")

    masks = classify_bins(readout)
    n_fb_im = int(masks['feedback_im'].sum())
    n_interleaved = int(masks['interleaved'].sum())
    n_input = int(masks['input_only'].sum())
    log(f"Readout: {n_readout} bins")
    log(f"  Input-only: {n_input}  Feedback-IM: {n_fb_im}  Interleaved: {n_interleaved}")
    log(f"  Phase ref bin: {ref_bin_idx} ({readout[ref_bin_idx]/1000:.1f} kHz)")

    # ── NARMA data ──
    u, y = generate_narma10(args.steps, rng)
    start = NARMA_ORDER + N_WASHOUT
    total_usable = args.steps - start - 1
    n_train = int(total_usable * 0.7)
    n_test = total_usable - n_train
    y_all = y[start + 1:start + total_usable + 1]   # predict y(t+1), not y(t)
    y_tr, y_te = y_all[:n_train], y_all[n_train:]
    win = np.array([u[start + i - 9:start + i + 1] for i in range(total_usable)])
    log(f"Data: {total_usable} usable ({n_train} train / {n_test} test)")

    # ── Open hardware ──
    from relay_mux import RelayMux
    handle = _open_scope()
    mux = RelayMux(args.port)
    mux.open()
    time.sleep(0.5)

    max_freq = max(carriers_11)
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
    #  PASS 1: No-feedback baseline (10 carriers)
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ PASS 1: No-feedback baseline (10 carriers, expanded readout) ═══")
    carriers_10 = list(INPUT_CARRIERS_HZ)

    X_nf_mag = np.zeros((total_usable, n_readout))
    X_nf_re  = np.zeros((total_usable, n_readout))
    X_nf_im  = np.zeros((total_usable, n_readout))
    t0 = time.time()

    for idx in range(total_usable):
        t = start + idx
        window = u[t - 9:t + 1]
        amps = list(window * 2.0)
        drive_multitone(handle, carriers_10, amps, f_rep)
        mags, reals, imags = capture_complex(handle, readout, ref_bin_idx)
        X_nf_mag[idx] = mags
        X_nf_re[idx] = reals
        X_nf_im[idx] = imags

        if (idx + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total_usable - idx - 1) / rate
            log(f"  {idx+1}/{total_usable} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_p1 = time.time() - t0
    log(f"  Pass 1 done: {elapsed_p1:.1f}s ({total_usable/elapsed_p1:.1f} steps/s)")

    np.savez(RESULTS_DIR / "hw_cbv2_pass1.npz",
             X_nf_mag=X_nf_mag, X_nf_re=X_nf_re, X_nf_im=X_nf_im,
             u=u, y=y, readout=np.array(readout),
             start=start, n_train=n_train, total_usable=total_usable)

    # ══════════════════════════════════════════════════════════════════
    #  PASS 2: Teacher-forced feedback (11 carriers, y(t) on amplitude)
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ PASS 2: Amplitude-feedback (11 carriers, teacher-forced) ═══")
    log(f"  y(t) → amplitude of {FEEDBACK_FREQ/1000:.1f} kHz")

    X_fb_mag = np.zeros((total_usable, n_readout))
    X_fb_re  = np.zeros((total_usable, n_readout))
    X_fb_im  = np.zeros((total_usable, n_readout))
    t0 = time.time()

    for idx in range(total_usable):
        t = start + idx
        window = u[t - 9:t + 1]
        amps_u = list(window * 2.0)
        y_fb = np.clip(y[t], 0, 2) / 2.0
        amps_all = amps_u + [y_fb]
        drive_multitone(handle, carriers_11, amps_all, f_rep)
        mags, reals, imags = capture_complex(handle, readout, ref_bin_idx)
        X_fb_mag[idx] = mags
        X_fb_re[idx] = reals
        X_fb_im[idx] = imags

        if (idx + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total_usable - idx - 1) / rate
            log(f"  {idx+1}/{total_usable} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_p2 = time.time() - t0
    log(f"  Pass 2 done: {elapsed_p2:.1f}s ({total_usable/elapsed_p2:.1f} steps/s)")

    np.savez(RESULTS_DIR / "hw_cbv2_pass2.npz",
             X_fb_mag=X_fb_mag, X_fb_re=X_fb_re, X_fb_im=X_fb_im,
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
    #  EVALUATION — Comprehensive ablation
    # ══════════════════════════════════════════════════════════════════
    log("\n═══════════════════════════════════════════════════════════════")
    log("  EVALUATION — Feature ablation")
    log("═══════════════════════════════════════════════════════════════")
    results = []

    fb_m = masks['feedback_im']
    il_m = masks['interleaved']
    inp_m = masks['input_only']

    # ── A: No-feedback baselines ──
    results.append(eval_features(
        np.hstack([X_nf_mag, win]), y_tr, y_te, n_train,
        "A1_nofb_mag+win"))

    results.append(eval_features(
        np.hstack([X_nf_mag, X_nf_re, X_nf_im, win]), y_tr, y_te, n_train,
        "A2_nofb_complex+win"))

    # ── B: Feedback, magnitude-only ──
    results.append(eval_features(
        np.hstack([X_fb_mag, win]), y_tr, y_te, n_train,
        "B1_fb_mag_all+win"))

    results.append(eval_features(
        np.hstack([X_fb_mag[:, fb_m], win]), y_tr, y_te, n_train,
        "B2_fb_mag_fbIM+win"))

    if il_m.any():
        results.append(eval_features(
            np.hstack([X_fb_mag[:, il_m], win]), y_tr, y_te, n_train,
            "B3_fb_mag_interl+win"))

    # ── C: Feedback, complex (mag + Re + Im) ──
    X_fb_cplx = np.hstack([X_fb_mag, X_fb_re, X_fb_im])
    results.append(eval_features(
        np.hstack([X_fb_cplx, win]), y_tr, y_te, n_train,
        "C1_fb_complex_all+win"))

    X_fb_cplx_fbim = np.hstack([
        X_fb_mag[:, fb_m], X_fb_re[:, fb_m], X_fb_im[:, fb_m]])
    results.append(eval_features(
        np.hstack([X_fb_cplx_fbim, win]), y_tr, y_te, n_train,
        "C2_fb_complex_fbIM+win"))

    if il_m.any():
        X_fb_cplx_il = np.hstack([
            X_fb_mag[:, il_m], X_fb_re[:, il_m], X_fb_im[:, il_m]])
        results.append(eval_features(
            np.hstack([X_fb_cplx_il, win]), y_tr, y_te, n_train,
            "C3_fb_complex_interl+win"))

    # ── D: Phase-only (Re + Im, no magnitude) ──
    results.append(eval_features(
        np.hstack([X_fb_re, X_fb_im, win]), y_tr, y_te, n_train,
        "D1_fb_phase_all+win"))

    results.append(eval_features(
        np.hstack([X_fb_re[:, fb_m], X_fb_im[:, fb_m], win]),
        y_tr, y_te, n_train,
        "D2_fb_phase_fbIM+win"))

    # ── E: Spectrum DIFFERENCE (feedback - no-feedback) ──
    X_diff_mag = X_fb_mag - X_nf_mag
    results.append(eval_features(
        np.hstack([X_diff_mag, win]), y_tr, y_te, n_train,
        "E1_diff_mag+win"))

    X_diff_re = X_fb_re - X_nf_re
    X_diff_im = X_fb_im - X_nf_im
    X_diff_cplx = np.hstack([X_diff_mag, X_diff_re, X_diff_im])
    results.append(eval_features(
        np.hstack([X_diff_cplx, win]), y_tr, y_te, n_train,
        "E2_diff_complex+win"))

    # Difference at feedback-IM bins only
    results.append(eval_features(
        np.hstack([X_diff_mag[:, fb_m], win]), y_tr, y_te, n_train,
        "E3_diff_mag_fbIM+win"))

    # ── F: Feedback + no-feedback concatenated ──
    results.append(eval_features(
        np.hstack([X_fb_mag, X_nf_mag, win]), y_tr, y_te, n_train,
        "F1_both_mag+win"))

    # ── G: Input-only bins from feedback pass (sanity) ──
    inp_only_mask = inp_m & ~fb_m
    if inp_only_mask.any():
        results.append(eval_features(
            np.hstack([X_fb_mag[:, inp_only_mask], win]),
            y_tr, y_te, n_train,
            "G1_fb_inputonly+win"))

    # ══════════════════════════════════════════════════════════════════
    #  Summary
    # ══════════════════════════════════════════════════════════════════
    log("\n" + "═" * 70)
    log("  RESULTS — Colorburst v2 NARMA-10")
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
    e1 = find("E1")
    c1 = find("C1")

    if a1 and b1:
        log(f"  No-feedback → feedback (mag):   "
            f"{a1['nmse_test']:.4f} → {b1['nmse_test']:.4f} "
            f"(Δ={a1['nmse_test'] - b1['nmse_test']:+.4f})")
    if a1 and e1:
        log(f"  Spectrum difference (fb-nofb):   "
            f"{a1['nmse_test']:.4f} → {e1['nmse_test']:.4f} "
            f"(Δ={a1['nmse_test'] - e1['nmse_test']:+.4f})")
    if b1 and c1:
        log(f"  Mag-only → complex:             "
            f"{b1['nmse_test']:.4f} → {c1['nmse_test']:.4f} "
            f"(Δ={b1['nmse_test'] - c1['nmse_test']:+.4f})")

    best = min(results, key=lambda x: x['nmse_test'])
    log(f"\n  ★ BEST: {best['name']} = {best['nmse_test']:.4f}")

    # ── Save ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": "narma_hw_colorburst_v2.py",
        "concept": "Refined virtual rewrite: amplitude-feedback, implicit phase ref, expanded readout",
        "steps": args.steps,
        "seed": args.seed,
        "all_open": args.all_open,
        "plate": args.plate if not args.all_open else "all_NE",
        "n_avg": N_AVG,
        "settle_ms": SETTLE_S * 1000,
        "feedback_freq_hz": FEEDBACK_FREQ,
        "phase_ref_freq_hz": PHASE_REF_FREQ,
        "n_readout": n_readout,
        "n_feedback_im_bins": n_fb_im,
        "n_interleaved_bins": n_interleaved,
        "n_train": n_train,
        "n_test": n_test,
        "pass1_time_s": round(elapsed_p1, 1),
        "pass2_time_s": round(elapsed_p2, 1),
        "results": results,
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = RESULTS_DIR / f"narma10_hw_cbv2_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nSaved → {outfile}")


if __name__ == "__main__":
    main()
