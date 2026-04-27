#!/usr/bin/env python3
"""
Enrollment-Filtered Nonlinear Kernel Experiment

Principle (from V5 pre-scan success on April 8):
  The plate's best results come when excitation targets enrolled eigenmode
  frequencies and readout focuses on bins where the plate is KNOWN to respond.
  The NARMA experiments used carriers at arbitrary frequencies and read all 78
  bins, wasting most of the feature space on noise.

Design:
  Phase 0 — Enrollment:
    Load plate census data → select N_CARRIERS strongest eigenmodes as carrier
    frequencies. Compute all 2nd-order IM products (fi±fj). These are the ONLY
    readout bins used.

  Phase 1 — Pre-scan:
    Drive each carrier individually as CW, capture at 12 averages. Identify
    which enrolled-mode readout bins actually respond above noise. Build a
    mask of "live" bins. Also sweep pairs to verify which IM products are
    actually measurable.

  Phase 2 — Kernel measurement:
    Binary ON/OFF encoding: N carriers → 2^N input patterns (excluding all-off).
    For each pattern, drive the ON carriers at full amplitude, capture 20
    averages at live bins. Build the (2^N - 1) × M_live kernel matrix K.

  Phase 3 — Evaluation:
    1. Kernel rank: effective rank of K (how many independent features?)
    2. Kernel alignment: K vs RBF, polynomial, linear reference kernels
    3. Classification accuracy on naturally suited tasks (XOR, parity, product)
    4. Function approximation: nonlinear functions of binary inputs
    5. Comparison: plate kernel vs software random Fourier features with same dim

Usage:
  DYLD_LIBRARY_PATH="..." python tools/kernel_enrolled.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_cross_20260418_142222.json \\
      [--plate 4_NE] [--n-carriers 4] [--n-avg 20] [--dry-run]
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
from sklearn.linear_model import Ridge, RidgeClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import KFold

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
ROOT = TOOLS_DIR.parent
RESULTS_DIR = ROOT / "data" / "results" / "lab" / "plate_exps" / "kernel"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════

AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096
SETTLE_S = 0.080           # longer settle for cleaner IM products
SETTLE_RELAY_S = 0.10
PRESCAN_N_AVG = 24         # extra averaging for faint IM detection
PRESCAN_SETTLE = 0.200     # generous settle for pre-scan

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
#  Phase 0: Enrollment — select carriers from census peaks
# ═══════════════════════════════════════════════════════════════════════

def enroll_carriers(census_path, plate_id, n_carriers):
    """Select the N strongest eigenmode frequencies as carriers."""
    with open(census_path) as f:
        census = json.load(f)

    peaks = census["results"][plate_id]["peaks"]
    # Sort by magnitude descending
    peaks_sorted = sorted(peaks, key=lambda p: p["magnitude"], reverse=True)

    # Select top N, but ensure minimum spacing (500 Hz) to avoid beating
    selected = []
    for pk in peaks_sorted:
        freq = pk["freq_hz"]
        if all(abs(freq - s["freq_hz"]) > 500 for s in selected):
            selected.append(pk)
        if len(selected) >= n_carriers:
            break

    if len(selected) < n_carriers:
        log(f"  WARNING: only {len(selected)} peaks with >500 Hz spacing "
            f"(requested {n_carriers})")

    carrier_freqs = sorted(p["freq_hz"] for p in selected)
    log(f"  Enrolled {len(carrier_freqs)} carriers from plate {plate_id}:")
    for pk in selected:
        snr = pk.get("snr_db", 0)
        log(f"    {pk['freq_hz']:>8.0f} Hz  mag={pk['magnitude']:>12.0f}  "
            f"snr={snr:.1f} dB")

    return carrier_freqs


def compute_readout_freqs(carrier_freqs):
    """Compute readout bins: carriers + all 2nd-order IM products."""
    readout = set()

    # Carrier fundamentals
    for f in carrier_freqs:
        readout.add(round(f))

    # 2nd-order IM: fi ± fj, 2fi - fj
    n = len(carrier_freqs)
    im_products = {}
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            fi, fj = carrier_freqs[i], carrier_freqs[j]
            for label, imf in [
                (f"|f{i}-f{j}|", abs(fi - fj)),
                (f"f{i}+f{j}", fi + fj),
                (f"2f{i}-f{j}", abs(2 * fi - fj)),
            ]:
                imf_r = round(imf)
                if 1000 < imf_r < 350_000:
                    readout.add(imf_r)
                    im_products[imf_r] = label

    readout_sorted = sorted(readout)
    n_carriers_bins = len(carrier_freqs)
    n_im_bins = len(readout_sorted) - n_carriers_bins
    log(f"  Readout bins: {len(readout_sorted)} total "
        f"({n_carriers_bins} carriers + {n_im_bins} IM products)")
    return readout_sorted, im_products


# ═══════════════════════════════════════════════════════════════════════
#  Hardware interface (reused from narma_hw_volterra)
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


def _close_scope(handle):
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps2000.ps2000_close_unit(handle)
    log("  PicoScope closed")


def drive_cw(handle, freq_hz):
    """Drive a single CW tone at full amplitude."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0)


def drive_multitone(handle, carrier_freqs, amplitudes, f_rep):
    """Drive multiple carriers with given amplitudes via ARB waveform."""
    from picosdk.ps2000 import ps2000

    if not carrier_freqs or all(a == 0 for a in amplitudes):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
        time.sleep(SETTLE_S)
        return

    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    buf = np.zeros(ARB_LEN, dtype=np.float64)
    for f_target, amp in zip(carrier_freqs, amplitudes):
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


def capture_spectrum(handle, readout_freqs, n_avg):
    """Capture n_avg averages, return magnitude array at readout bins."""
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE

    mag_sum = np.zeros(len(readout_freqs))
    complex_sum = np.zeros(len(readout_freqs), dtype=np.complex128)

    for _ in range(n_avg):
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
        complex_sum += vals

    return mag_sum / n_avg, complex_sum / n_avg


def compute_f_rep(carrier_freqs):
    """Pick ARB repetition rate so all carriers fall on exact bins."""
    # f_rep = 48 MHz / (2^32 / delta_phase) ≈ carrier / k
    # Choose f_rep so all carriers are close to integer multiples
    # Start from lowest carrier, try sub-harmonics
    f_min = min(carrier_freqs)
    best_f_rep = f_min / round(f_min / (48_000_000 / (2**32 * ARB_LEN)))

    # Simple approach: f_rep = GCD-ish of carrier frequencies
    # Round all carriers to nearest 50 Hz, then find GCD
    rounded = [round(f / 50) * 50 for f in carrier_freqs]
    from math import gcd
    from functools import reduce
    g = reduce(gcd, [int(f) for f in rounded])
    # f_rep should be small enough that k values fit in ARB_LEN/2
    f_rep = g
    while max(carrier_freqs) / f_rep > ARB_LEN // 2:
        f_rep *= 2

    # Verify all carriers map to valid bins
    for f in carrier_freqs:
        k = round(f / f_rep)
        f_actual = k * f_rep
        err_pct = abs(f - f_actual) / f * 100
        if err_pct > 1.0:
            log(f"  WARNING: carrier {f:.0f} Hz maps to bin {k} "
                f"(actual {f_actual:.0f} Hz, err {err_pct:.2f}%)")

    log(f"  f_rep = {f_rep:.1f} Hz  (delta_phase = "
        f"{int(f_rep * 2**32 / 48_000_000)})")
    return f_rep


# ═══════════════════════════════════════════════════════════════════════
#  Phase 1: Pre-scan — identify live readout bins
# ═══════════════════════════════════════════════════════════════════════

def prescan(handle, carrier_freqs, readout_freqs, mux_idx):
    """Drive each carrier as CW, measure all readout bins.
    Returns: mask of bins that respond significantly above noise."""
    from relay_mux import RelayMux

    n_bins = len(readout_freqs)
    n_carriers = len(carrier_freqs)

    log("\n  ── Phase 1: Pre-scan ──")

    # 1a. Baseline (silence)
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    time.sleep(PRESCAN_SETTLE)
    baseline_mag, _ = capture_spectrum(handle, readout_freqs, PRESCAN_N_AVG)
    log(f"  Baseline captured (mean mag = {np.mean(baseline_mag):.0f})")

    # 1b. Drive each carrier individually
    single_mags = np.zeros((n_carriers, n_bins))
    for ci, freq in enumerate(carrier_freqs):
        drive_cw(handle, freq)
        time.sleep(PRESCAN_SETTLE)
        mags, _ = capture_spectrum(handle, readout_freqs, PRESCAN_N_AVG)
        single_mags[ci] = mags
        log(f"  Carrier {ci} ({freq:.0f} Hz): "
            f"max_mag={np.max(mags):.0f}  "
            f"mean_mag={np.mean(mags):.0f}")

    # 1c. Drive all carriers simultaneously
    f_rep = compute_f_rep(carrier_freqs)
    amps_all = [1.0] * n_carriers
    drive_multitone(handle, carrier_freqs, amps_all, f_rep)
    time.sleep(PRESCAN_SETTLE)
    all_on_mag, _ = capture_spectrum(handle, readout_freqs, PRESCAN_N_AVG)
    log(f"  All-on: max_mag={np.max(all_on_mag):.0f}  "
        f"mean_mag={np.mean(all_on_mag):.0f}")

    # 1d. Identify live bins with two-tier threshold:
    #   - Carrier bins: all-on SNR > 3.0 OR single-carrier SNR > 5.0
    #   - IM bins: excess above baseline > 1.3× AND not in any single
    #     carrier (present ONLY from multi-carrier nonlinear mixing)
    noise_floor = baseline_mag + 1  # avoid /0
    all_on_snr = all_on_mag / noise_floor
    single_max_snr = np.max(single_mags / noise_floor[np.newaxis, :], axis=0)

    carrier_mask = (all_on_snr > 3.0) | (single_max_snr > 5.0)

    # IM detection: bins where all-on shows excess but NO single carrier
    # does. This is the nonlinear mixing signature.
    im_mask = np.zeros(n_bins, dtype=bool)
    for j in range(n_bins):
        is_multi_only = (all_on_snr[j] > 1.3 and single_max_snr[j] < 1.5)
        if is_multi_only:
            im_mask[j] = True

    live_mask = carrier_mask | im_mask

    n_live = int(np.sum(live_mask))
    n_im = int(np.sum(im_mask))
    log(f"\n  Pre-scan summary:")
    log(f"    Live bins (SNR > 3): {n_live} of {n_bins}")
    log(f"    Pure IM bins (not in any single): {n_im}")
    log(f"    Carrier bins: {n_carriers}")
    log(f"    Live frequencies:")
    for j in np.where(live_mask)[0]:
        tag = " [IM]" if im_mask[j] else ""
        tag += " [carrier]" if readout_freqs[j] in [round(f) for f in carrier_freqs] else ""
        log(f"      {readout_freqs[j]:>8d} Hz  SNR_all={all_on_snr[j]:>6.1f}  "
            f"SNR_single={single_max_snr[j]:>6.1f}{tag}")

    # Silence
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    return {
        "live_mask": live_mask,
        "im_mask": im_mask,
        "baseline_mag": baseline_mag,
        "single_mags": single_mags,
        "all_on_mag": all_on_mag,
        "all_on_snr": all_on_snr,
        "single_max_snr": single_max_snr,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2: Kernel measurement — binary ON/OFF patterns
# ═══════════════════════════════════════════════════════════════════════

def measure_kernel(handle, carrier_freqs, readout_freqs, live_mask, n_avg,
                   n_reps=1):
    """Drive all 2^N - 1 binary patterns, capture at live bins.
    Returns: kernel matrix K (n_patterns × n_live_bins), pattern matrix."""
    n_carriers = len(carrier_freqs)
    n_patterns = (2 ** n_carriers) - 1  # exclude all-off
    live_idx = np.where(live_mask)[0]
    n_live = len(live_idx)
    live_freqs = [readout_freqs[j] for j in live_idx]

    log(f"\n  ── Phase 2: Kernel measurement ──")
    log(f"  Patterns: {n_patterns} ({n_carriers} carriers, binary ON/OFF)")
    log(f"  Live bins: {n_live}")
    log(f"  Averages per pattern: {n_avg}")
    log(f"  Repetitions: {n_reps}")
    est_time = n_patterns * n_reps * (SETTLE_S + n_avg * 0.015)
    log(f"  Estimated time: {est_time:.0f}s ({est_time/60:.1f} min)")

    f_rep = compute_f_rep(carrier_freqs)

    # Generate all binary patterns (1 to 2^N - 1)
    patterns = np.zeros((n_patterns, n_carriers), dtype=np.float64)
    for p in range(n_patterns):
        bits = p + 1  # skip 0 (all-off)
        for c in range(n_carriers):
            patterns[p, c] = 1.0 if (bits >> c) & 1 else 0.0

    # Measure each pattern (randomize order for robustness)
    K_all = np.zeros((n_reps, n_patterns, n_live))
    K_full = np.zeros((n_reps, n_patterns, len(readout_freqs)))

    for rep in range(n_reps):
        order = np.random.permutation(n_patterns)
        log(f"\n  Rep {rep + 1}/{n_reps}:")

        for step_i, pi in enumerate(order):
            amps = patterns[pi].tolist()
            drive_multitone(handle, carrier_freqs, amps, f_rep)
            mags, _ = capture_spectrum(handle, readout_freqs, n_avg)

            K_full[rep, pi] = mags
            K_all[rep, pi] = mags[live_idx]

            if (step_i + 1) % 5 == 0 or step_i == 0:
                pat_str = "".join(
                    str(int(patterns[pi, c])) for c in range(n_carriers))
                log(f"    [{step_i+1:>3d}/{n_patterns}] "
                    f"pattern={pat_str}  "
                    f"max_live={np.max(K_all[rep, pi]):.0f}")

    # Average over reps
    K = np.mean(K_all, axis=0)
    K_full_avg = np.mean(K_full, axis=0)

    # Silence
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    return K, patterns, K_full_avg, live_idx


# ═══════════════════════════════════════════════════════════════════════
#  Phase 3: Evaluation
# ═══════════════════════════════════════════════════════════════════════

def evaluate_kernel(K, patterns, carrier_freqs, readout_freqs, live_idx):
    """Evaluate kernel quality: rank, alignment, classification, approx."""
    n_patterns, n_features = K.shape
    n_carriers = patterns.shape[1]
    log(f"\n  ══════════════════════════════════════════════════")
    log(f"  Phase 3: EVALUATION")
    log(f"  Kernel matrix: {n_patterns} patterns × {n_features} live bins")
    log(f"  ══════════════════════════════════════════════════")

    results = {}

    # ── 3a. Effective rank ──
    sc = StandardScaler()
    K_s = sc.fit_transform(K)
    U, S, Vt = np.linalg.svd(K_s, full_matrices=False)
    S_norm = S / S[0] if S[0] > 0 else S
    eff_rank = int(np.sum(S_norm > 0.01))
    s_entropy = -np.sum(
        (S_norm[S_norm > 0]**2) * np.log(S_norm[S_norm > 0]**2 + 1e-12)
    )
    results["effective_rank"] = eff_rank
    results["sv_entropy"] = round(float(s_entropy), 4)
    results["top_svs"] = [round(float(s), 4) for s in S_norm[:min(10, len(S_norm))]]
    log(f"\n  3a. Effective rank: {eff_rank} / {min(n_patterns, n_features)}")
    log(f"      SV entropy: {s_entropy:.4f}")
    log(f"      Top SVs: {S_norm[:6].round(3)}")

    # ── 3b. Kernel alignment ──
    # Build Gram matrix from plate features
    K_plate = K_s @ K_s.T

    # Build reference kernels from binary inputs
    X_in = patterns  # binary
    K_lin = X_in @ X_in.T

    # RBF
    from scipy.spatial.distance import cdist
    dists = cdist(X_in, X_in, 'sqeuclidean')
    sigma = np.median(dists[dists > 0]) ** 0.5
    K_rbf = np.exp(-dists / (2 * sigma**2))

    # Polynomial d=2
    K_poly2 = (X_in @ X_in.T + 1) ** 2
    # Polynomial d=3
    K_poly3 = (X_in @ X_in.T + 1) ** 3

    def kernel_alignment(K1, K2):
        """Centered kernel alignment."""
        n = K1.shape[0]
        H = np.eye(n) - np.ones((n, n)) / n
        Kc1 = H @ K1 @ H
        Kc2 = H @ K2 @ H
        num = np.sum(Kc1 * Kc2)
        den = np.sqrt(np.sum(Kc1 * Kc1) * np.sum(Kc2 * Kc2))
        return float(num / den) if den > 0 else 0.0

    align_lin = kernel_alignment(K_plate, K_lin)
    align_rbf = kernel_alignment(K_plate, K_rbf)
    align_poly2 = kernel_alignment(K_plate, K_poly2)
    align_poly3 = kernel_alignment(K_plate, K_poly3)

    results["kernel_alignment"] = {
        "linear": round(align_lin, 4),
        "rbf": round(align_rbf, 4),
        "poly_d2": round(align_poly2, 4),
        "poly_d3": round(align_poly3, 4),
    }
    log(f"\n  3b. Kernel alignment (centered):")
    log(f"      Linear:  {align_lin:.4f}")
    log(f"      RBF:     {align_rbf:.4f}")
    log(f"      Poly d2: {align_poly2:.4f}")
    log(f"      Poly d3: {align_poly3:.4f}")

    # ── 3c. Classification tasks ──
    log(f"\n  3c. Classification (leave-one-out):")
    results["classification"] = {}

    def loo_classify(X, y, name):
        """Leave-one-out classification accuracy."""
        n = len(y)
        correct = 0
        for i in range(n):
            X_tr = np.delete(X, i, axis=0)
            y_tr = np.delete(y, i)
            X_te = X[i:i+1]
            y_te = y[i]
            sc_l = StandardScaler()
            X_tr_s = sc_l.fit_transform(X_tr)
            X_te_s = sc_l.transform(X_te)
            clf = RidgeClassifier(alpha=1.0)
            clf.fit(X_tr_s, y_tr)
            if clf.predict(X_te_s)[0] == y_te:
                correct += 1
        acc = correct / n
        results["classification"][name] = round(acc, 4)
        return acc

    # Task 1: Parity (XOR generalization)
    parity = np.array([int(np.sum(patterns[i]) % 2)
                        for i in range(n_patterns)])
    acc_par_plate = loo_classify(K_s, parity, "parity_plate")
    acc_par_lin = loo_classify(patterns, parity, "parity_linear")

    # Software reference: explicit parity features
    parity_feats = []
    for i in range(n_carriers):
        for j in range(i+1, n_carriers):
            parity_feats.append(patterns[:, i] * patterns[:, j])
    if parity_feats:
        X_parity_sw = np.column_stack(parity_feats)
        acc_par_quad = loo_classify(
            np.hstack([patterns, X_parity_sw]), parity, "parity_quadratic")
    else:
        acc_par_quad = acc_par_lin

    log(f"    Parity:    plate={acc_par_plate:.1%}  "
        f"linear={acc_par_lin:.1%}  quadratic={acc_par_quad:.1%}")

    # Task 2: Majority vote
    majority = np.array([int(np.sum(patterns[i]) > n_carriers / 2)
                          for i in range(n_patterns)])
    acc_maj_plate = loo_classify(K_s, majority, "majority_plate")
    acc_maj_lin = loo_classify(patterns, majority, "majority_linear")
    log(f"    Majority:  plate={acc_maj_plate:.1%}  "
        f"linear={acc_maj_lin:.1%}")

    # Task 3: Product of first two carriers
    if n_carriers >= 2:
        product_01 = np.array([int(patterns[i, 0] * patterns[i, 1])
                                for i in range(n_patterns)])
        acc_prod_plate = loo_classify(K_s, product_01, "product_plate")
        acc_prod_lin = loo_classify(patterns, product_01, "product_linear")
        log(f"    AND(0,1):  plate={acc_prod_plate:.1%}  "
            f"linear={acc_prod_lin:.1%}")

    # ── 3d. Function approximation ──
    log(f"\n  3d. Function approximation (LOO NMSE):")
    results["function_approx"] = {}

    def loo_nmse(X, y, name):
        """Leave-one-out NMSE."""
        n = len(y)
        preds = np.zeros(n)
        for i in range(n):
            X_tr = np.delete(X, i, axis=0)
            y_tr = np.delete(y, i)
            X_te = X[i:i+1]
            sc_l = StandardScaler()
            X_tr_s = sc_l.fit_transform(X_tr)
            X_te_s = sc_l.transform(X_te)
            reg = Ridge(alpha=1.0)
            reg.fit(X_tr_s, y_tr)
            preds[i] = reg.predict(X_te_s)[0]
        var = np.var(y)
        score = float(np.mean((y - preds)**2) / var) if var > 0 else float('inf')
        results["function_approx"][name] = round(score, 4)
        return score

    # Target 1: Sum of pairwise products
    y_pair = np.zeros(n_patterns)
    for i in range(n_carriers):
        for j in range(i + 1, n_carriers):
            y_pair += patterns[:, i] * patterns[:, j]

    nmse_pair_plate = loo_nmse(K_s, y_pair, "pairwise_plate")
    nmse_pair_lin = loo_nmse(patterns, y_pair, "pairwise_linear")
    log(f"    Pairwise:  plate={nmse_pair_plate:.4f}  "
        f"linear={nmse_pair_lin:.4f}")

    # Target 2: XOR-like (product of all carriers, mod-2 interaction)
    y_xor = np.prod(patterns, axis=1) if n_carriers <= 5 else parity.astype(float)
    nmse_xor_plate = loo_nmse(K_s, y_xor, "full_product_plate")
    nmse_xor_lin = loo_nmse(patterns, y_xor, "full_product_linear")
    log(f"    Full prod:  plate={nmse_xor_plate:.4f}  "
        f"linear={nmse_xor_lin:.4f}")

    # Target 3: Nonlinear combo sin(π·x0·x1) + cos(π·x2)
    if n_carriers >= 3:
        y_nl = (np.sin(np.pi * patterns[:, 0] * patterns[:, 1])
                + np.cos(np.pi * patterns[:, 2]))
        nmse_nl_plate = loo_nmse(K_s, y_nl, "nonlinear_plate")
        nmse_nl_lin = loo_nmse(patterns, y_nl, "nonlinear_linear")
        log(f"    sin·cos:   plate={nmse_nl_plate:.4f}  "
            f"linear={nmse_nl_lin:.4f}")

    # ── Software comparison: Random Fourier Features ──
    log(f"\n  3e. Software comparison (RFF with same dim={n_features}):")
    rng = np.random.default_rng(42)
    W = rng.normal(0, 2.0, (n_carriers, n_features))
    b = rng.uniform(0, 2 * np.pi, n_features)
    X_rff = np.sqrt(2 / n_features) * np.cos(patterns @ W + b)

    nmse_rff_pair = loo_nmse(X_rff, y_pair, "pairwise_rff")
    nmse_rff_xor = loo_nmse(X_rff, y_xor, "full_product_rff")
    acc_rff_par = loo_classify(X_rff, parity, "parity_rff")
    log(f"    RFF pairwise:  {nmse_rff_pair:.4f}  (plate: {nmse_pair_plate:.4f})")
    log(f"    RFF full prod: {nmse_rff_xor:.4f}  (plate: {nmse_xor_plate:.4f})")
    log(f"    RFF parity:    {acc_rff_par:.1%}   (plate: {acc_par_plate:.1%})")

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Dry-run: analyze existing data with enrollment filtering
# ═══════════════════════════════════════════════════════════════════════

def dry_run(census_path, plate_id, n_carriers, volterra_path=None):
    """Simulate the experiment using saved Volterra data with enrollment."""
    log("\n══════════════════════════════════════════════════════")
    log("  DRY RUN — Enrollment-Filtered Kernel (Simulated)")
    log("══════════════════════════════════════════════════════")

    # Enroll carriers
    carrier_freqs = enroll_carriers(census_path, plate_id, n_carriers)
    readout_all, im_products = compute_readout_freqs(carrier_freqs)

    if volterra_path is None:
        volterra_path = (ROOT / "data" / "results" / "lab" / "plate_exps"
                         / "narma10" / "hw_volterra_pass2.npz")

    d = np.load(volterra_path)
    saved_readout = d["readout"]
    X_mag = d["X_mag"]
    u = d["u"]

    log(f"\n  Loaded {volterra_path.name}: "
        f"{X_mag.shape[0]} steps × {X_mag.shape[1]} bins")

    # Map enrolled readout bins to saved data columns
    tol = 0.03
    enrolled_cols = []
    enrolled_freqs = []
    for rf in readout_all:
        dists = np.abs(saved_readout - rf) / np.maximum(saved_readout, rf)
        j = np.argmin(dists)
        if dists[j] < tol:
            enrolled_cols.append(j)
            enrolled_freqs.append(saved_readout[j])

    enrolled_cols = np.array(enrolled_cols)
    log(f"  Matched {len(enrolled_cols)} of {len(readout_all)} "
        f"enrolled bins in saved data")

    # Filter to high-variance (strong signal) bins
    var = np.var(X_mag[:, enrolled_cols], axis=0)
    var_threshold = np.median(var) * 2
    strong_mask = var > var_threshold
    strong_cols = enrolled_cols[strong_mask]
    log(f"  Strong enrolled bins (var > 2× median): {len(strong_cols)}")
    for j in strong_cols:
        log(f"    {saved_readout[j]:>8.0f} Hz  var={np.var(X_mag[:, j]):.2e}")

    # Build pseudo-kernel: use NARMA input patterns as excitation proxy
    # Group by unique input patterns (quantized)
    start = int(d["start"])
    total = int(d["total_usable"])
    n_train = int(total * 0.7)

    # For function approximation, use the actual input vectors
    X_in = np.array([u[start + i - 9:start + i + 1] for i in range(total)])

    log(f"\n  ── Evaluation: Enrolled-Filtered vs All Bins ──")

    # Targets
    y_pair = np.zeros(total)
    for i in range(10):
        for j in range(i + 1, 10):
            y_pair += X_in[:, i] * X_in[:, j]

    y_sin = np.zeros(total)
    for i in range(10):
        for j in range(i + 1, min(i + 3, 10)):
            y_sin += np.sin(np.pi * X_in[:, i] * X_in[:, j])

    y_tr_pair, y_te_pair = y_pair[:n_train], y_pair[n_train:]
    y_tr_sin, y_te_sin = y_sin[:n_train], y_sin[n_train:]

    def train_eval(X, y_tr, y_te):
        alphas = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
        sc = StandardScaler()
        Xs = sc.fit_transform(X[:n_train])
        Xt = sc.transform(X[n_train:])
        best_a, best_cv = 1.0, float('inf')
        kf = KFold(n_splits=5, shuffle=False)
        for a in alphas:
            scores = []
            for tr, va in kf.split(Xs):
                r = Ridge(alpha=a).fit(Xs[tr], y_tr[tr])
                pred = r.predict(Xs[va])
                v = np.var(y_tr[va])
                scores.append(float(np.mean((y_tr[va] - pred)**2) / v)
                              if v > 0 else float('inf'))
            m = np.mean(scores)
            if m < best_cv:
                best_cv, best_a = m, a
        r = Ridge(alpha=best_a).fit(Xs, y_tr)
        pred = r.predict(Xt)
        v = np.var(y_te)
        return float(np.mean((y_te - pred)**2) / v) if v > 0 else float('inf')

    configs = [
        ("All 78 bins", X_mag),
        (f"Enrolled ({len(enrolled_cols)} bins)", X_mag[:, enrolled_cols]),
        (f"Strong enrolled ({len(strong_cols)} bins)", X_mag[:, strong_cols]),
        ("Top-10 by variance", X_mag[:, np.argsort(np.var(X_mag[:n_train], axis=0))[-10:]]),
        ("Software linear (10)", X_in),
    ]

    # Quadratic features
    pairs = []
    for i in range(10):
        for j in range(i, 10):
            pairs.append(X_in[:, i] * X_in[:, j])
    X_quad = np.column_stack([X_in] + pairs)
    configs.append(("Software quadratic (65)", X_quad))

    # RFF with same dim as strong enrolled
    rng = np.random.default_rng(42)
    n_rff = max(len(strong_cols), 10)
    W = rng.normal(0, 2.0, (10, n_rff))
    b = rng.uniform(0, 2 * np.pi, n_rff)
    X_rff = np.sqrt(2 / n_rff) * np.cos(X_in @ W + b)
    configs.append((f"RFF ({n_rff}-dim)", X_rff))

    log(f"\n  {'Config':<35s}  {'Pairwise':>10s}  {'Sinusoidal':>10s}")
    log(f"  {'─'*35}  {'─'*10}  {'─'*10}")

    for name, X in configs:
        n1 = train_eval(X, y_tr_pair, y_te_pair)
        n2 = train_eval(X, y_tr_sin, y_te_sin)
        log(f"  {name:<35s}  {n1:>10.4f}  {n2:>10.4f}")

    # Kernel alignment from pseudo-Gram matrix
    log(f"\n  ── Kernel alignment ──")
    for name, cols in [
        ("All 78 bins", np.arange(X_mag.shape[1])),
        (f"Strong enrolled ({len(strong_cols)})", strong_cols),
    ]:
        Ks = StandardScaler().fit_transform(X_mag[:n_train, cols])
        K_plate = Ks @ Ks.T

        K_lin = X_in[:n_train] @ X_in[:n_train].T
        from scipy.spatial.distance import cdist
        dists = cdist(X_in[:n_train], X_in[:n_train], 'sqeuclidean')
        sigma = np.median(dists[dists > 0]) ** 0.5
        K_rbf = np.exp(-dists / (2 * sigma**2))
        K_poly2 = (X_in[:n_train] @ X_in[:n_train].T + 1) ** 2

        n = K_plate.shape[0]
        H = np.eye(n) - np.ones((n, n)) / n

        def ka(K1, K2):
            Kc1 = H @ K1 @ H
            Kc2 = H @ K2 @ H
            num = np.sum(Kc1 * Kc2)
            den = np.sqrt(np.sum(Kc1 * Kc1) * np.sum(Kc2 * Kc2))
            return float(num / den) if den > 0 else 0.0

        log(f"  {name}:")
        log(f"    Linear: {ka(K_plate, K_lin):.4f}  "
            f"RBF: {ka(K_plate, K_rbf):.4f}  "
            f"Poly2: {ka(K_plate, K_poly2):.4f}")


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Enrollment-Filtered Nonlinear Kernel Experiment")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--census", required=True,
                        help="Path to plate census JSON")
    parser.add_argument("--plate", default="4_NE",
                        help="Plate ID in census results")
    parser.add_argument("--n-carriers", type=int, default=4,
                        help="Number of strongest eigenmodes to use as carriers")
    parser.add_argument("--n-avg", type=int, default=20,
                        help="Averages per capture in kernel measurement")
    parser.add_argument("--n-reps", type=int, default=2,
                        help="Repetitions of full pattern set")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analyze existing Volterra data with enrollment "
                             "(no hardware needed)")
    parser.add_argument("--volterra",
                        help="Path to Volterra .npz for dry-run")
    args = parser.parse_args()

    if args.dry_run:
        vp = Path(args.volterra) if args.volterra else None
        dry_run(args.census, args.plate, args.n_carriers, vp)
        return

    # ── Live hardware experiment ──
    log("══════════════════════════════════════════════════════")
    log("  Enrollment-Filtered Nonlinear Kernel Experiment")
    log("══════════════════════════════════════════════════════")

    # Phase 0: Enrollment
    carrier_freqs = enroll_carriers(args.census, args.plate, args.n_carriers)
    readout_freqs, im_products = compute_readout_freqs(carrier_freqs)

    # Select relay for this plate
    if args.plate not in RECEIVER_MAP:
        log(f"  ERROR: plate {args.plate} not in RECEIVER_MAP")
        sys.exit(1)
    mux_idx, mux_label = RECEIVER_MAP[args.plate]

    from relay_mux import RelayMux
    mux = RelayMux(port=args.port)
    mux.open()
    mux.select(mux_idx)
    time.sleep(SETTLE_RELAY_S)
    log(f"  Relay mux: {mux_label} (index {mux_idx})")

    handle = _open_scope()

    try:
        # Phase 1: Pre-scan
        prescan_result = prescan(
            handle, carrier_freqs, readout_freqs, mux_idx)
        live_mask = prescan_result["live_mask"]

        if np.sum(live_mask) < 3:
            log("  WARNING: fewer than 3 live bins — experiment may not "
                "produce meaningful results")

        # Phase 2: Kernel measurement
        K, patterns, K_full, live_idx = measure_kernel(
            handle, carrier_freqs, readout_freqs, live_mask,
            args.n_avg, args.n_reps)

        # Phase 3: Evaluation
        results = evaluate_kernel(
            K, patterns, carrier_freqs, readout_freqs, live_idx)

    finally:
        _close_scope(handle)
        mux.off()
        mux.close()

    # Save results
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"kernel_enrolled_{ts}.npz"
    np.savez(out_path,
             K=K,
             patterns=patterns,
             K_full=K_full,
             carrier_freqs=np.array(carrier_freqs),
             readout_freqs=np.array(readout_freqs),
             live_mask=live_mask,
             live_idx=live_idx,
             prescan_baseline=prescan_result["baseline_mag"],
             prescan_all_on=prescan_result["all_on_mag"],
             prescan_single=prescan_result["single_mags"])

    results_json = RESULTS_DIR / f"kernel_enrolled_{ts}.json"
    # Convert numpy types for JSON
    def jsonify(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: jsonify(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [jsonify(v) for v in obj]
        return obj

    with open(results_json, "w") as f:
        json.dump({
            "timestamp": ts,
            "plate": args.plate,
            "n_carriers": args.n_carriers,
            "carrier_freqs": [round(f, 1) for f in carrier_freqs],
            "n_readout": len(readout_freqs),
            "n_live": int(np.sum(live_mask)),
            "n_avg": args.n_avg,
            "n_reps": args.n_reps,
            "results": jsonify(results),
        }, f, indent=2)

    log(f"\n  Saved: {out_path}")
    log(f"  Saved: {results_json}")
    log("  Done.")


if __name__ == "__main__":
    main()
