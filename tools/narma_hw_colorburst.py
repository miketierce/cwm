#!/usr/bin/env python3
"""
NARMA-10 Hardware Colorburst — Phase-Encoded Virtual Rewrite

Inspired by the NTSC colorburst technique for color TV:

  NTSC PROBLEM:  Encode color into an existing monochrome signal
                 without extra bandwidth, on a channel with no memory
                 (each scan line is independent), when the carrier is
                 suppressed so the decoder has no phase reference.

  NTSC SOLUTION: (1) Frequency-interleave chroma between luma peaks
                 (2) Encode hue as PHASE of the subcarrier
                 (3) Embed a short reference burst (colorburst) on
                     every scan line for the decoder to PLL-lock to

  CWM PROBLEM:   Encode y(t) onto a plate that has no physical memory
                 between steps, where feedback-carrier IM products
                 overlap with input-carrier IM products, and capture-
                 to-capture timing jitter scrambles absolute FFT phase.

  CWM SOLUTION:  (1) Choose feedback freq for spectral interleaving
                 (2) Encode y(t) as PHASE of the feedback carrier
                     (plate phase stability σ=0.001 rad → 6000:1 SNR)
                 (3) Add a constant-phase REFERENCE carrier; measure
                     all phases relative to it (PLL-lock to the burst)

Architecture (12 carriers):
  - 10 input carriers: amplitude ∝ u(t-9)..u(t)     [same as v1]
  - 1 feedback carrier (53.9 kHz): PHASE ∝ y(t),     constant amplitude
  - 1 reference carrier (16.0 kHz): constant amp+phase ("colorburst")

Readout:
  - Complex FFT at each readout bin (magnitude + phase)
  - Phase referenced to the 16.0 kHz burst carrier
  - Features: Re, Im, Mag at each bin → 3× features vs magnitude-only

Usage:
  DYLD_LIBRARY_PATH="..." python tools/narma_hw_colorburst.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_cross_20260418_142222.json \\
      [--steps 1000] [--fast] [--all-open] [--reuse-baseline]
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

# 10 input carriers (amplitude-encode u(t-9)..u(t))
INPUT_CARRIERS_HZ = [
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]

# Feedback carrier: 53.9 kHz — best total IM coverage (26 mode hits)
# Phase encodes y(t); amplitude held constant
FEEDBACK_FREQ = 53_900

# Reference carrier: 16.0 kHz — mode cluster, not an input carrier,
# highest IM-on-modes count (12). Constant amp + phase = the "colorburst"
REFERENCE_FREQ = 16_000

# Phase encoding range: y(t) ∈ [0, ~1.5] → phase ∈ [0, π]
# Using [0, π] avoids wrapping ambiguity; y_max=2.0 clips safely
Y_MAX = 2.0
PHASE_RANGE = np.pi  # radians

# Plate mode clusters (readout targets)
MODE_CLUSTERS_HZ = [
    11_425, 15_100, 16_000, 17_375, 19_000, 23_900, 29_200, 29_900,
    31_600, 33_225, 34_550, 36_000, 37_000, 42_300, 45_000, 47_800,
    49_600, 51_500, 53_900, 56_200, 58_500, 62_000, 65_075, 68_200,
    70_800, 73_500, 76_200, 78_800, 81_500, 84_200, 86_900, 89_400,
    95_000,
]

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
    """Compute readout frequencies from carrier IM products landing on modes."""
    readout, labels, im_map = [], [], []
    seen = set()

    # Carrier fundamentals
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

    # IM2 products (fi ± fj)
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

    # IM3 products (2fi - fj)
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


def classify_readout_bins(readout_freqs, labels, im_map, carriers_12):
    """Classify each readout bin by which IM products land on it.

    Directly computes all IM products from each carrier subset and
    checks which readout bins they hit. This avoids the issue where
    bins added as fundamentals don't carry IM-map metadata.

    Returns dict of boolean masks over readout_freqs:
      'all'         — every bin
      'input_only'  — bins hit by input×input IM products
      'feedback_im' — bins hit by feedback×anything IM products
      'ref_im'      — bins hit by reference×anything IM products
      'interleaved' — feedback-IM bins NOT also hit by input-only IM
    """
    tol = IM_TOL_PCT / 100
    n = len(readout_freqs)
    rf = np.array(readout_freqs, dtype=float)

    def hits_bin(im_f, rf_arr):
        """Return boolean mask: which readout bins does im_f land on?"""
        if im_f < 1000 or im_f > 390_000:
            return np.zeros(len(rf_arr), dtype=bool)
        return np.abs(rf_arr - im_f) / np.maximum(rf_arr, im_f) < tol

    input_carriers = list(INPUT_CARRIERS_HZ)
    all_carriers = list(carriers_12)

    masks = {
        'all':         np.ones(n, dtype=bool),
        'input_only':  np.zeros(n, dtype=bool),
        'feedback_im': np.zeros(n, dtype=bool),
        'ref_im':      np.zeros(n, dtype=bool),
    }

    # Input×input IM products
    for i in range(len(input_carriers)):
        for j in range(len(input_carriers)):
            if i == j:
                continue
            fi, fj = input_carriers[i], input_carriers[j]
            for im_f in [abs(fi - fj), fi + fj, abs(2*fi - fj)]:
                masks['input_only'] |= hits_bin(im_f, rf)

    # Feedback × anything IM products
    for fi in all_carriers:
        if fi == FEEDBACK_FREQ:
            continue
        for im_f in [abs(FEEDBACK_FREQ - fi), FEEDBACK_FREQ + fi,
                      abs(2*FEEDBACK_FREQ - fi), abs(2*fi - FEEDBACK_FREQ)]:
            masks['feedback_im'] |= hits_bin(im_f, rf)

    # Reference × anything IM products
    for fi in all_carriers:
        if fi == REFERENCE_FREQ:
            continue
        for im_f in [abs(REFERENCE_FREQ - fi), REFERENCE_FREQ + fi,
                      abs(2*REFERENCE_FREQ - fi), abs(2*fi - REFERENCE_FREQ)]:
            masks['ref_im'] |= hits_bin(im_f, rf)

    # Interleaved = feedback IM bins that are NOT input-only
    masks['interleaved'] = masks['feedback_im'] & ~masks['input_only']
    return masks


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


def drive_multitone_phase(handle, freqs_hz, amplitudes, phases, f_rep):
    """Drive multiple frequencies with per-carrier amplitude AND phase.

    This is the key colorburst innovation: each carrier can have an
    independent phase offset, allowing y(t) to be encoded as the phase
    of the feedback carrier rather than its amplitude.

    Args:
        handle:     PicoScope handle
        freqs_hz:   list of carrier frequencies
        amplitudes: list of amplitudes (0–1 scale, 0 = off)
        phases:     list of phase offsets in radians
        f_rep:      ARB repetition frequency
    """
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
    for f_target, amp, phi in zip(freqs_hz, amplitudes, phases):
        if amp <= 0:
            continue
        k = round(f_target / f_rep)
        if k < 1 or k > ARB_LEN // 2:
            continue
        t = np.arange(ARB_LEN) / ARB_LEN
        buf += amp * np.sin(2 * np.pi * k * t + phi)

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


def capture_complex_spectrum(handle, readout_freqs, ref_bin_idx):
    """Capture FFT and return phase-referenced complex spectrum.

    For each capture:
      1. Compute complex FFT
      2. Find phase of the reference carrier bin
      3. Rotate all bins by -ref_phase (PLL lock to colorburst)
      4. Average rotated complex spectra across N_AVG captures

    Returns:
        mags:   magnitude at each readout frequency
        reals:  Re(phase-referenced) at each readout frequency
        imags:  Im(phase-referenced) at each readout frequency
    """
    import cwm_picoscope
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE

    complex_sum = np.zeros(len(readout_freqs), dtype=np.complex128)

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
        nfft = len(raw) * 4   # 4× zero-pad
        fft_c = np.fft.rfft(windowed, n=nfft)
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
        bin_hz = freq_axis[1] - freq_axis[0]

        # Extract complex values at readout frequencies
        vals = np.zeros(len(readout_freqs), dtype=np.complex128)
        for j, rf in enumerate(readout_freqs):
            tb = int(round(rf / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft_c) - 1, tb + 3)
            # Peak bin by magnitude
            peak_idx = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
            vals[j] = fft_c[peak_idx]

        # PLL lock: rotate all phases relative to reference carrier
        ref_val = vals[ref_bin_idx]
        if abs(ref_val) > 0:
            ref_phase = np.angle(ref_val)
            rotation = np.exp(-1j * ref_phase)
            vals *= rotation

        complex_sum += vals

    avg = complex_sum / N_AVG
    mags = np.abs(avg)
    reals = np.real(avg)
    imags = np.imag(avg)
    return mags, reals, imags


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation helpers
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


def eval_features(X, y_tr, y_te, n_train, name):
    """Train ridge on features and return result dict."""
    reg, sc, alpha = train_ridge(X[:n_train], y_tr)
    return eval_ridge(reg, sc, X[:n_train], y_tr, X[n_train:], y_te, name)


# ═══════════════════════════════════════════════════════════════════════
#  Main experiment
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 Hardware Colorburst — Phase-Encoded Virtual Rewrite")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--census", required=True)
    parser.add_argument("--plate", default="4_NE")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--all-open", action="store_true",
                        help="All NE relays open simultaneously")
    parser.add_argument("--fast", action="store_true",
                        help="5ms settle, 2 avg")
    parser.add_argument("--reuse-baseline", action="store_true",
                        help="Load Pass 1 from hw_vr_pass1_checkpoint.npz")
    args = parser.parse_args()

    if args.fast:
        global SETTLE_S, N_AVG
        SETTLE_S = 0.005
        N_AVG = 2

    rng = np.random.default_rng(args.seed)
    log("╔══════════════════════════════════════════════════════════════╗")
    log("║  NARMA-10 Hardware Colorburst — Phase-Encoded Virtual Rewrite  ║")
    log("╚══════════════════════════════════════════════════════════════╝")
    log(f"Steps: {args.steps}  Seed: {args.seed}  Fast: {args.fast}")
    log(f"Feedback carrier: {FEEDBACK_FREQ/1000:.1f} kHz (phase-encodes y(t))")
    log(f"Reference carrier: {REFERENCE_FREQ/1000:.1f} kHz (colorburst)")
    log(f"Phase range: [0, π] for y ∈ [0, {Y_MAX}]")

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

    # ── Carrier sets ──
    carriers_10 = list(INPUT_CARRIERS_HZ)
    carriers_12 = carriers_10 + [FEEDBACK_FREQ, REFERENCE_FREQ]
    log(f"Carriers: {len(carriers_10)} input + feedback + reference = {len(carriers_12)}")

    # ── Readout frequencies ──
    readout_12, labels_12, im_map_12 = compute_readout_freqs(
        carriers_12, MODE_CLUSTERS_HZ)
    n_readout = len(readout_12)

    # Find reference carrier's index in readout array
    ref_bin_idx = None
    for idx, rf in enumerate(readout_12):
        if abs(rf - REFERENCE_FREQ) / REFERENCE_FREQ < 0.02:
            ref_bin_idx = idx
            break
    if ref_bin_idx is None:
        log("WARNING: reference carrier not in readout! Adding it.")
        readout_12.append(REFERENCE_FREQ)
        labels_12.append("reference")
        im_map_12.append((len(carriers_12) - 1, len(carriers_12) - 1, "self"))
        ref_bin_idx = len(readout_12) - 1
        n_readout = len(readout_12)

    # Classify bins
    masks = classify_readout_bins(readout_12, labels_12, im_map_12, carriers_12)
    n_fb_im = int(masks['feedback_im'].sum())
    n_interleaved = int(masks['interleaved'].sum())
    log(f"Readout: {n_readout} bins total")
    log(f"  Feedback-IM bins: {n_fb_im}")
    log(f"  Interleaved (unique feedback): {n_interleaved}")
    log(f"  Reference bin index: {ref_bin_idx} ({readout_12[ref_bin_idx]/1000:.1f} kHz)")

    # ── NARMA data ──
    u, y = generate_narma10(args.steps, rng)
    start = NARMA_ORDER + N_WASHOUT
    total_usable = args.steps - start - 1
    n_train = int(total_usable * 0.7)
    n_test = total_usable - n_train
    y_all = y[start:start + total_usable]
    y_tr, y_te = y_all[:n_train], y_all[n_train:]
    win = np.array([u[start + i - 9:start + i + 1] for i in range(total_usable)])
    log(f"Data: {total_usable} usable ({n_train} train / {n_test} test)")

    # ── Open hardware ──
    from relay_mux import RelayMux
    handle = _open_scope()
    mux = RelayMux(args.port)
    mux.open()
    time.sleep(0.5)

    # Compute f_rep for ARB
    max_freq = max(carriers_12)
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
    #  PASS 1: Amplitude-only baseline (10 carriers, magnitude readout)
    # ══════════════════════════════════════════════════════════════════
    baseline_checkpoint = RESULTS_DIR / "hw_vr_pass1_checkpoint.npz"
    readout_10, labels_10, im_map_10 = compute_readout_freqs(
        carriers_10, MODE_CLUSTERS_HZ)

    if args.reuse_baseline and baseline_checkpoint.exists():
        log("\n═══ PASS 1: Loading baseline from checkpoint ═══")
        ckpt = np.load(baseline_checkpoint)
        X_baseline_mag = ckpt['X_nf']
        log(f"  Loaded {X_baseline_mag.shape} from {baseline_checkpoint.name}")
    else:
        log("\n═══ PASS 1: Amplitude-only baseline (10 carriers, mag readout) ═══")
        n_feats_10 = len(readout_10)
        X_baseline_mag = np.zeros((total_usable, n_feats_10))
        t0 = time.time()

        for idx in range(total_usable):
            t = start + idx
            window = u[t - 9:t + 1]
            amps = list(window * 2.0)
            phases = [0.0] * len(amps)
            drive_multitone_phase(handle, carriers_10, amps, phases, f_rep)
            # Use complex capture but only keep magnitude
            mags, _, _ = capture_complex_spectrum(handle, readout_10, 0)
            X_baseline_mag[idx] = mags

            if (idx + 1) % 20 == 0:
                elapsed = time.time() - t0
                rate = (idx + 1) / elapsed
                eta = (total_usable - idx - 1) / rate
                log(f"  {idx+1}/{total_usable} ({rate:.1f}/s, ETA {eta:.0f}s)")

        elapsed_p1 = time.time() - t0
        log(f"  Pass 1 done: {elapsed_p1:.1f}s ({total_usable/elapsed_p1:.1f} steps/s)")
        np.savez(RESULTS_DIR / "hw_colorburst_pass1.npz",
                 X_baseline_mag=X_baseline_mag, u=u, y=y,
                 readout_10=np.array(readout_10),
                 start=start, n_train=n_train, total_usable=total_usable)

    # ══════════════════════════════════════════════════════════════════
    #  PASS 2: Colorburst — phase-encoded feedback + reference carrier
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ PASS 2: Colorburst (phase-encoded feedback + reference) ═══")
    log(f"  12 carriers: 10 input + feedback@{FEEDBACK_FREQ/1000:.1f}k + ref@{REFERENCE_FREQ/1000:.1f}k")
    log(f"  y(t) → phase: y=0 → φ=0, y={Y_MAX} → φ=π")

    # Feature arrays: magnitude, real, imag (phase-referenced)
    X_mag = np.zeros((total_usable, n_readout))
    X_re  = np.zeros((total_usable, n_readout))
    X_im  = np.zeros((total_usable, n_readout))

    t0 = time.time()
    for idx in range(total_usable):
        t = start + idx

        # Input carrier amplitudes (encode u window)
        window = u[t - 9:t + 1]
        amps_input = list(window * 2.0)

        # Feedback carrier: constant amplitude, phase encodes y(t)
        fb_amp = 1.0
        fb_phase = np.clip(y[t], 0, Y_MAX) / Y_MAX * PHASE_RANGE

        # Reference carrier: constant amplitude AND phase (the burst)
        ref_amp = 1.0
        ref_phase = 0.0

        # Assemble: 10 inputs + feedback + reference
        all_amps = amps_input + [fb_amp, ref_amp]
        all_phases = [0.0] * len(amps_input) + [fb_phase, ref_phase]

        drive_multitone_phase(handle, carriers_12, all_amps, all_phases, f_rep)
        mags, reals, imags = capture_complex_spectrum(
            handle, readout_12, ref_bin_idx)

        X_mag[idx] = mags
        X_re[idx] = reals
        X_im[idx] = imags

        if (idx + 1) % 20 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total_usable - idx - 1) / rate
            log(f"  {idx+1}/{total_usable} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_p2 = time.time() - t0
    log(f"  Pass 2 done: {elapsed_p2:.1f}s ({total_usable/elapsed_p2:.1f} steps/s)")

    # Save checkpoint
    np.savez(RESULTS_DIR / "hw_colorburst_pass2.npz",
             X_mag=X_mag, X_re=X_re, X_im=X_im,
             u=u, y=y, readout_12=np.array(readout_12),
             masks_feedback=masks['feedback_im'],
             masks_interleaved=masks['interleaved'],
             ref_bin_idx=ref_bin_idx,
             start=start, n_train=n_train, total_usable=total_usable)

    # ══════════════════════════════════════════════════════════════════
    #  PASS 3: Amplitude-only feedback (12 carriers, v1-style comparison)
    # ══════════════════════════════════════════════════════════════════
    log("\n═══ PASS 3: Amplitude-only feedback (v1-style, magnitude readout) ═══")
    log(f"  y(t) encoded as AMPLITUDE of feedback carrier (like v1)")

    X_amp_fb = np.zeros((total_usable, n_readout))
    t0 = time.time()

    for idx in range(total_usable):
        t = start + idx
        window = u[t - 9:t + 1]
        amps_input = list(window * 2.0)

        # Feedback: amplitude encodes y(t), phase = 0 (v1 style)
        fb_amp = np.clip(y[t], 0, Y_MAX) / Y_MAX
        ref_amp = 1.0

        all_amps = amps_input + [fb_amp, ref_amp]
        all_phases = [0.0] * len(all_amps)

        drive_multitone_phase(handle, carriers_12, all_amps, all_phases, f_rep)
        mags, _, _ = capture_complex_spectrum(handle, readout_12, ref_bin_idx)
        X_amp_fb[idx] = mags

        if (idx + 1) % 20 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (total_usable - idx - 1) / rate
            log(f"  {idx+1}/{total_usable} ({rate:.1f}/s, ETA {eta:.0f}s)")

    elapsed_p3 = time.time() - t0
    log(f"  Pass 3 done: {elapsed_p3:.1f}s ({total_usable/elapsed_p3:.1f} steps/s)")

    np.savez(RESULTS_DIR / "hw_colorburst_pass3.npz",
             X_amp_fb=X_amp_fb, u=u, y=y,
             start=start, n_train=n_train, total_usable=total_usable)

    # ── Close hardware ──
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps2000.ps2000_close_unit(handle)
    mux.close()
    log("\n  Hardware closed.")

    # ══════════════════════════════════════════════════════════════════
    #  Evaluation — A/B comparison of all approaches
    # ══════════════════════════════════════════════════════════════════
    log("\n═══════════════════════════════════════════════════════════════")
    log("  EVALUATION")
    log("═══════════════════════════════════════════════════════════════")
    results = []

    # ── A: Baseline (no feedback, magnitude only) ──
    X_bw = np.hstack([X_baseline_mag, win])
    r = eval_features(X_bw, y_tr, y_te, n_train, "A1_baseline_mag+win")
    results.append(r)

    # ── B: Amplitude-feedback (v1 style, magnitude only) ──
    X_af_w = np.hstack([X_amp_fb, win])
    r = eval_features(X_af_w, y_tr, y_te, n_train, "B1_amp_fb_mag+win")
    results.append(r)

    # Amplitude-feedback, feedback-IM bins only
    X_af_fb = X_amp_fb[:, masks['feedback_im']]
    X_af_fb_w = np.hstack([X_af_fb, win])
    r = eval_features(X_af_fb_w, y_tr, y_te, n_train, "B2_amp_fb_fbIM+win")
    results.append(r)

    # ── C: Colorburst — magnitude only (to isolate phase benefit) ──
    X_cb_mag_w = np.hstack([X_mag, win])
    r = eval_features(X_cb_mag_w, y_tr, y_te, n_train, "C1_burst_mag+win")
    results.append(r)

    # ── D: Colorburst — complex (magnitude + phase-referenced Re/Im) ──
    X_complex = np.hstack([X_mag, X_re, X_im])
    X_complex_w = np.hstack([X_complex, win])
    r = eval_features(X_complex_w, y_tr, y_te, n_train, "D1_burst_complex+win")
    results.append(r)

    # Complex, ALL bins
    r = eval_features(X_complex, y_tr, y_te, n_train, "D2_burst_complex_nowin")
    results.append(r)

    # ── E: Colorburst — feedback-IM bins only, complex ──
    fb_mask = masks['feedback_im']
    X_fb_complex = np.hstack([
        X_mag[:, fb_mask], X_re[:, fb_mask], X_im[:, fb_mask]])
    X_fb_complex_w = np.hstack([X_fb_complex, win])
    r = eval_features(X_fb_complex_w, y_tr, y_te, n_train, "E1_burst_fbIM_cplx+win")
    results.append(r)

    # ── F: Colorburst — interleaved bins only (pure NTSC trick) ──
    il_mask = masks['interleaved']
    if il_mask.any():
        X_il_complex = np.hstack([
            X_mag[:, il_mask], X_re[:, il_mask], X_im[:, il_mask]])
        X_il_complex_w = np.hstack([X_il_complex, win])
        r = eval_features(X_il_complex_w, y_tr, y_te, n_train,
                          "F1_burst_interleaved+win")
        results.append(r)

    # ── G: Phase-only features (Re/Im without magnitude) ──
    X_phase_only = np.hstack([X_re, X_im])
    X_phase_only_w = np.hstack([X_phase_only, win])
    r = eval_features(X_phase_only_w, y_tr, y_te, n_train, "G1_phase_only+win")
    results.append(r)

    # ── H: Phase-only, feedback-IM bins ──
    X_fb_phase = np.hstack([X_re[:, fb_mask], X_im[:, fb_mask]])
    X_fb_phase_w = np.hstack([X_fb_phase, win])
    r = eval_features(X_fb_phase_w, y_tr, y_te, n_train, "H1_phase_fbIM+win")
    results.append(r)

    # ══════════════════════════════════════════════════════════════════
    #  Summary
    # ══════════════════════════════════════════════════════════════════
    log("\n" + "═" * 66)
    log("  RESULTS — Hardware Colorburst NARMA-10")
    log("═" * 66)
    log(f"  {'Approach':<35s} {'Feats':>5s} {'NMSE':>8s}")
    log("  " + "─" * 50)
    for r in sorted(results, key=lambda x: x['nmse_test']):
        log(f"  {r['name']:<35s} {r['features']:5d} {r['nmse_test']:.4f}")

    # Key comparisons
    log("\n  KEY COMPARISONS:")
    def find(prefix):
        return next((r for r in results if r['name'].startswith(prefix)), None)

    a1 = find("A1")
    b1 = find("B1")
    c1 = find("C1")
    d1 = find("D1")

    if a1 and b1:
        log(f"  Amplitude feedback vs baseline: "
            f"{a1['nmse_test']:.4f} → {b1['nmse_test']:.4f} "
            f"(Δ={a1['nmse_test'] - b1['nmse_test']:+.4f})")
    if b1 and c1:
        log(f"  Phase-encode vs amplitude-encode (mag only): "
            f"{b1['nmse_test']:.4f} → {c1['nmse_test']:.4f} "
            f"(Δ={b1['nmse_test'] - c1['nmse_test']:+.4f})")
    if c1 and d1:
        log(f"  Complex readout vs magnitude-only: "
            f"{c1['nmse_test']:.4f} → {d1['nmse_test']:.4f} "
            f"(Δ={c1['nmse_test'] - d1['nmse_test']:+.4f})")
    if a1 and d1:
        log(f"  ★ Full colorburst vs baseline: "
            f"{a1['nmse_test']:.4f} → {d1['nmse_test']:.4f} "
            f"(Δ={a1['nmse_test'] - d1['nmse_test']:+.4f})")

    # ── Save ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": "narma_hw_colorburst.py",
        "concept": "NTSC colorburst-inspired phase-encoded virtual rewrite",
        "ntsc_mapping": {
            "luminance": "10 input carriers (amplitude-encode u)",
            "chrominance_subcarrier": f"feedback carrier ({FEEDBACK_FREQ} Hz, phase-encode y(t))",
            "colorburst": f"reference carrier ({REFERENCE_FREQ} Hz, constant phase)",
            "frequency_interleaving": "feedback IM products in gaps between input IMs",
            "phase_encoding": f"y(t) → [0, π] on feedback carrier phase",
            "pll_lock": "all FFT phases referenced to reference carrier",
        },
        "steps": args.steps,
        "seed": args.seed,
        "fast": args.fast,
        "all_open": args.all_open,
        "plate": args.plate if not args.all_open else "all_NE",
        "feedback_freq_hz": FEEDBACK_FREQ,
        "reference_freq_hz": REFERENCE_FREQ,
        "carriers_12": carriers_12,
        "n_readout": n_readout,
        "n_feedback_im_bins": n_fb_im,
        "n_interleaved_bins": n_interleaved,
        "n_train": n_train,
        "n_test": n_test,
        "pass2_time_s": round(elapsed_p2, 1),
        "pass3_time_s": round(elapsed_p3, 1),
        "results": results,
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = RESULTS_DIR / f"narma10_hw_colorburst_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nSaved → {outfile}")


if __name__ == "__main__":
    main()
