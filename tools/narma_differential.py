#!/usr/bin/env python3
"""
NARMA-10 Differential Capture — Ch B Crosstalk Cancellation
═══════════════════════════════════════════════════════════════

Uses a BNC-tee'd AWG reference on Ch B to cancel electrical feedthrough
and AWG DAC nonlinearity from the plate spectral features.

Wiring:
  AWG → BNC tee → plates (via relay mux) → Ch A (plate + crosstalk)
                └→ Ch B (AWG direct reference)

Method:
  1. Relay OFF: calibrate feedthrough α(f) = FFT_A(f) / FFT_B(f)
  2. Relay ON:  plate_spectrum(f) = FFT_A(f) - α(f) · FFT_B(f)

This strips out:
  - Electrical feedthrough (~5-11% of signal)
  - AWG DAC nonlinearity (spurious IM products from waveform generation)
  - Any common-mode interference

Evaluates three feature sets:
  ch_a:   Standard Ch A capture (reduced resolution: 4032 vs 8064 samples)
  diff:   Complex differential (crosstalk-cancelled)
  ratio:  |FFT_A / FFT_B| transfer function magnitude

Usage:
  DYLD_LIBRARY_PATH="..." python tools/narma_differential.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_cross_20260418_142222.json \\
      [--steps 1000] [--fast]
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

from picosdk.ps2000 import ps2000
import cwm_picoscope
from relay_mux import RelayMux

# ── PicoScope constants (dual-channel) ────────────────────────────────
TIMEBASE = 7
SAMPLE_RATE = 781_250
N_SAMPLES = 3072          # dual-channel max for ps2204A (shared 8kS buffer)
AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096

# ── NARMA-10 ──────────────────────────────────────────────────────────
NARMA_ORDER = 10
N_WASHOUT = 50
N_AVG = 8
SETTLE_S = 0.12
SETTLE_RELAY_S = 0.10
IM_TOL_PCT = 2.0
RIDGE_ALPHAS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]

# Carriers and modes (same as narma_ladder.py)
LADDER_CARRIERS_HZ = [
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]
MODE_CLUSTERS_HZ = [
    11_425, 15_100, 16_000, 17_375, 19_000, 23_900, 29_200, 29_900,
    31_600, 33_225, 34_550, 36_000, 37_000, 42_300, 45_000, 47_800,
    49_600, 51_500, 53_900, 56_200, 58_500, 62_000, 65_075, 68_200,
    70_800, 73_500, 76_200, 78_800, 81_500, 84_200, 86_900, 89_400,
    95_000,
]
RECEIVER_MAP = {
    "1": (1, "A-NE"), "2": (2, "B-NE"), "3_NE": (3, "G-NE"),
    "4_NE": (5, "D-NE"), "5_NE": (7, "H-NE"),
}

_log_lines: list[str] = []
def log(msg: str = "", also_print: bool = True) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    _log_lines.append(f"[{ts}] {msg}")
    if also_print:
        print(msg, flush=True)


# ═══════════════════════════════════════════════════════════════════════
#  NARMA-10 generation (same as narma_ladder)
# ═══════════════════════════════════════════════════════════════════════

def generate_narma10(n_steps, seed=42):
    rng = np.random.default_rng(seed)
    total = n_steps + NARMA_ORDER + N_WASHOUT
    u = rng.uniform(0, 0.5, total)
    y = np.zeros(total)
    for t in range(NARMA_ORDER, total - 1):
        y_sum = np.sum(y[t - NARMA_ORDER:t + 1])
        y[t + 1] = (0.3 * y[t] + 0.05 * y[t] * y_sum
                     + 1.5 * u[t - 9] * u[t] + 0.1)
        y[t + 1] = np.clip(y[t + 1], 0, 1e6)
    return u, y


# ═══════════════════════════════════════════════════════════════════════
#  IM frequency computation (reuse from narma_ladder)
# ═══════════════════════════════════════════════════════════════════════

def compute_readout_freqs(carriers, all_modes, nyquist=390_000):
    readout, labels, im_map = [], [], []
    for f in all_modes:
        readout.append(f)
        carrier_idx = None
        for ci, cf in enumerate(carriers):
            if abs(f - cf) / max(f, cf) < 0.02:
                carrier_idx = ci
                break
        if carrier_idx is not None:
            labels.append(f"carrier_{carrier_idx}")
            im_map.append((carrier_idx, carrier_idx, "self"))
        else:
            labels.append(f"mode_{f/1000:.1f}k")
            im_map.append((-1, -1, "ambient"))

    seen = set(readout)
    for i in range(len(carriers)):
        for j in range(i + 1, len(carriers)):
            fi, fj = carriers[i], carriers[j]
            for im_f, im_type in [(abs(fi - fj), "IM2d"), (fi + fj, "IM2s")]:
                if im_f < 1000 or im_f > nyquist:
                    continue
                for mf in all_modes:
                    if abs(im_f - mf) / max(im_f, mf) < IM_TOL_PCT / 100:
                        if im_f not in seen:
                            readout.append(im_f)
                            labels.append(f"{im_type}_{i}x{j}")
                            im_map.append((i, j, im_type))
                            seen.add(im_f)
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
                    if f3 not in seen:
                        readout.append(f3)
                        labels.append(f"IM3_{i}x{j}")
                        im_map.append((i, j, "IM3"))
                        seen.add(f3)
                    break

    return readout, labels, im_map


def aggregate_step_pairs(X_spec, im_map, n_carriers=10):
    pair_groups, ambient_cols = {}, []
    for col, (i, j, t) in enumerate(im_map):
        if col >= X_spec.shape[1]:
            break
        if t == "ambient":
            ambient_cols.append(col)
        elif t == "self":
            pair_groups[(i, i)] = pair_groups.get((i, i), []) + [col]
        else:
            key = (min(i, j), max(i, j))
            pair_groups[key] = pair_groups.get(key, []) + [col]

    labels, cols = [], []
    for key in sorted(pair_groups.keys()):
        group = pair_groups[key]
        cols.append(np.mean(X_spec[:, group], axis=1, keepdims=True))
        labels.append(f"carrier_{key[0]}" if key[0] == key[1]
                      else f"pair_{key[0]}x{key[1]}")
    if ambient_cols:
        cols.append(np.mean(X_spec[:, ambient_cols], axis=1, keepdims=True))
        labels.append("ambient_mean")
    return np.hstack(cols), labels


# ═══════════════════════════════════════════════════════════════════════
#  PicoScope helpers — DUAL CHANNEL
# ═══════════════════════════════════════════════════════════════════════

def _open_scope_dual():
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed ({handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V DC
    ps2000.ps2000_set_channel(handle, 1, True, 1, 6)    # Ch B ±1V DC
    log("  PicoScope opened (Ch A ±1V plate, Ch B ±1V AWG ref)")
    return handle


def _close_scope(handle):
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    log("  PicoScope closed")


def drive_multitone(handle, freqs_hz, amplitudes, f_rep):
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
        0, 0, arb_buf, ARB_LEN, 0, 0)
    time.sleep(SETTLE_S)


def capture_dual_spectrum(handle, readout_freqs):
    """Average N_AVG dual-channel FFT captures.

    Returns (mags_a, complex_fft_a, complex_fft_b) where:
      mags_a:        standard magnitude features (Ch A only)
      complex_fft_a: averaged complex FFT at readout freqs (Ch A)
      complex_fft_b: averaged complex FFT at readout freqs (Ch B)
    """
    nfft = N_SAMPLES * 4
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
    bin_hz = freq_axis[1] - freq_axis[0]

    sum_mags_a = np.zeros(len(readout_freqs))
    sum_complex_a = np.zeros(len(readout_freqs), dtype=complex)
    sum_complex_b = np.zeros(len(readout_freqs), dtype=complex)

    for _ in range(N_AVG):
        t_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1,
                                ctypes.byref(t_ms))
        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.0005)
            if time.time() - t0 > 2:
                break

        buf_a = (ctypes.c_int16 * N_SAMPLES)()
        buf_b = (ctypes.c_int16 * N_SAMPLES)()
        overflow = ctypes.c_int16()
        n = ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES)
        if n <= 0:
            log(f"    WARNING: ps2000_get_values returned n={n}")
            continue

        raw_a = np.array(buf_a[:n], dtype=np.float64)
        raw_b = np.array(buf_b[:n], dtype=np.float64)

        if np.max(np.abs(raw_a)) == 0 and np.max(np.abs(raw_b)) == 0:
            log(f"    WARNING: both channels returned zeros (n={n})")
            continue
        window = np.hanning(len(raw_a))

        fft_a = np.fft.rfft(raw_a * window, n=nfft)
        fft_b = np.fft.rfft(raw_b * window, n=nfft)

        for j, rf in enumerate(readout_freqs):
            tb = int(round(rf / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft_a) - 1, tb + 3)
            # For magnitude: peak search (standard approach)
            mag_slice = np.abs(fft_a[lo:hi + 1])
            sum_mags_a[j] += float(np.max(mag_slice))
            # For complex: use the bin closest to target
            sum_complex_a[j] += fft_a[tb]
            sum_complex_b[j] += fft_b[tb]

    mags_a = sum_mags_a / N_AVG
    avg_complex_a = sum_complex_a / N_AVG
    avg_complex_b = sum_complex_b / N_AVG

    return mags_a, avg_complex_a, avg_complex_b


# ═══════════════════════════════════════════════════════════════════════
#  Feedthrough calibration
# ═══════════════════════════════════════════════════════════════════════

def calibrate_feedthrough(handle, carriers, readout_freqs, f_rep,
                          n_calibration=5):
    """Relay OFF: measure α(f) = FFT_A(f) / FFT_B(f) at each readout freq.

    Returns complex array α(f) — the electrical feedthrough transfer function.
    Average over n_calibration multitone drives to stabilize.
    """
    log("  Calibrating feedthrough (relay OFF)...")

    # Drive the same multitone used in actual experiment (all amps = 0.5)
    amps_cal = np.full(len(carriers), 0.5)
    drive_multitone(handle, carriers, amps_cal, f_rep)
    time.sleep(0.2)  # extra settle for calibration

    alpha_sum = np.zeros(len(readout_freqs), dtype=complex)

    for cal_i in range(n_calibration):
        _, complex_a, complex_b = capture_dual_spectrum(handle, readout_freqs)
        # α(f) = FFT_A(f) / FFT_B(f) where B ≠ 0
        safe_b = np.where(np.abs(complex_b) > 1e-10, complex_b,
                          1e-10 + 0j)
        alpha_sum += complex_a / safe_b

    alpha = alpha_sum / n_calibration

    # Report feedthrough magnitude
    alpha_mag = np.abs(alpha)
    log(f"    |α| range: {np.min(alpha_mag):.4f} – {np.max(alpha_mag):.4f} "
        f"(mean {np.mean(alpha_mag):.4f})")
    log(f"    Feedthrough power: {np.mean(alpha_mag**2)*100:.1f}% of Ch B")

    return alpha


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation helpers
# ═══════════════════════════════════════════════════════════════════════

def nmse(y_true, y_pred):
    var = np.var(y_true)
    if var == 0:
        return float('inf')
    return float(np.mean((y_true - y_pred) ** 2) / var)


def evaluate_approach(X_train, y_train, X_test, y_test, name=""):
    best_cv_nmse = float('inf')
    best_alpha = 1.0
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_train)
    X_te = scaler.transform(X_test)
    kf = KFold(n_splits=5, shuffle=False)
    for alpha in RIDGE_ALPHAS:
        cv_scores = []
        for tr_idx, val_idx in kf.split(X_tr):
            reg = Ridge(alpha=alpha)
            reg.fit(X_tr[tr_idx], y_train[tr_idx])
            pred_val = reg.predict(X_tr[val_idx])
            cv_scores.append(nmse(y_train[val_idx], pred_val))
        if np.mean(cv_scores) < best_cv_nmse:
            best_cv_nmse = np.mean(cv_scores)
            best_alpha = alpha

    reg = Ridge(alpha=best_alpha)
    reg.fit(X_tr, y_train)
    nm_tr = nmse(y_train, reg.predict(X_tr))
    nm_te = nmse(y_test, reg.predict(X_te))
    return {"name": name, "nmse_train": round(nm_tr, 6),
            "nmse_test": round(nm_te, 6), "features": X_train.shape[1],
            "best_alpha": best_alpha}


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 Differential Capture (Ch B crosstalk cancel)")
    parser.add_argument("--census", required=True)
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--plate", default="4_NE")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--all-open", action="store_true")
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args()

    if args.fast:
        global SETTLE_S, N_AVG
        SETTLE_S = 0.005
        N_AVG = 2

    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    log("══════════════════════════════════════════════════════════════")
    log("  NARMA-10 DIFFERENTIAL — Ch B Crosstalk Cancellation")
    log("══════════════════════════════════════════════════════════════")
    log()

    # Load census
    with open(args.census) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    all_mode_freqs = set()
    for key, data in census.items():
        for p in data.get("peaks", []):
            all_mode_freqs.add(p["freq_hz"])
    mode_freqs = sorted(all_mode_freqs)

    # Readout frequencies
    readout_freqs, readout_labels, im_map = compute_readout_freqs(
        LADDER_CARRIERS_HZ, MODE_CLUSTERS_HZ)
    n_rf = len(readout_freqs)
    n_feats = n_rf + NARMA_ORDER
    log(f"  Readout frequencies: {n_rf}")
    log(f"  Dual-channel N_SAMPLES: {N_SAMPLES} (bin_hz = "
        f"{SAMPLE_RATE / (N_SAMPLES * 4):.1f} Hz)")
    log()

    # NARMA-10
    u, y = generate_narma10(args.steps, args.seed)
    start = NARMA_ORDER + N_WASHOUT
    total_usable = len(u) - start
    n_train = int(total_usable * 0.67)
    log(f"  Steps: {len(u)} total, {total_usable} usable "
        f"({n_train} train / {total_usable - n_train} test)")
    log()

    # ── Hardware setup ────────────────────────────────────────────────
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("  HARDWARE CAPTURE (DUAL-CHANNEL)")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    handle = _open_scope_dual()
    mux = RelayMux(args.port)
    mux.open()
    time.sleep(0.5)

    max_freq = max(LADDER_CARRIERS_HZ)
    f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))
    log(f"  f_rep = {f_rep:.1f} Hz")

    # Plate setup
    if args.all_open:
        mux.all_ne()
        time.sleep(SETTLE_RELAY_S)
        plate_key = "all_ne"
        log("  All-open mode: 5 NE relays active")
    else:
        relay_ch, rx_name = RECEIVER_MAP[args.plate]
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)
        plate_key = args.plate
        log(f"  Single plate: {rx_name} (relay {relay_ch})")

    # ── Phase 1: Feedthrough calibration (relay OFF) ──────────────────
    log()
    saved_relay = plate_key
    mux.off()
    time.sleep(0.3)

    alpha = calibrate_feedthrough(handle, LADDER_CARRIERS_HZ,
                                  readout_freqs, f_rep, n_calibration=8)

    # Also capture noise floor (AWG off, relay OFF)
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    time.sleep(SETTLE_S)
    nf_mags, _, _ = capture_dual_spectrum(handle, readout_freqs)
    log(f"  Noise floor max: {np.max(nf_mags):.0f}")

    # Restore relay
    if args.all_open:
        mux.all_ne()
    else:
        mux.select(RECEIVER_MAP[args.plate][0])
    time.sleep(SETTLE_RELAY_S)

    # ── Phase 2: Enrollment (solo carriers, with differential) ────────
    log("\n  Enrollment prescan...")
    enroll_t0 = time.time()
    solo_mags_a = {}
    solo_diff = {}
    for ci in range(len(LADDER_CARRIERS_HZ)):
        amps = np.zeros(len(LADDER_CARRIERS_HZ))
        amps[ci] = 1.0
        drive_multitone(handle, LADDER_CARRIERS_HZ, amps, f_rep)
        mags_a, cplx_a, cplx_b = capture_dual_spectrum(handle, readout_freqs)
        solo_mags_a[ci] = mags_a
        # Differential: subtract feedthrough
        diff_complex = cplx_a - alpha * cplx_b
        solo_diff[ci] = np.abs(diff_complex)

    log(f"  Enrollment done ({time.time() - enroll_t0:.1f}s)")
    log(f"    Solo Ch A range: "
        f"{np.min([np.max(s) for s in solo_mags_a.values()]):.0f}–"
        f"{np.max([np.max(s) for s in solo_mags_a.values()]):.0f}")
    log(f"    Solo diff range: "
        f"{np.min([np.max(s) for s in solo_diff.values()]):.0f}–"
        f"{np.max([np.max(s) for s in solo_diff.values()]):.0f}")

    # ── Phase 3: NARMA-10 capture (three feature sets) ────────────────
    log()
    log("  Capturing NARMA-10 steps (3 feature sets per step)...")

    X_cha = np.zeros((total_usable, n_feats))      # Ch A standard
    X_diff = np.zeros((total_usable, n_feats))      # differential
    X_ratio = np.zeros((total_usable, n_feats))     # transfer function

    t0_cap = time.time()
    for idx in range(total_usable):
        t = start + idx
        if t < NARMA_ORDER:
            continue

        window = u[t - 9:t + 1]
        amps = window * 2.0  # [0, 1]

        drive_multitone(handle, LADDER_CARRIERS_HZ, amps, f_rep)
        mags_a, cplx_a, cplx_b = capture_dual_spectrum(handle, readout_freqs)

        # Feature set 1: Standard Ch A magnitudes
        X_cha[idx] = np.concatenate([mags_a, window])

        # Feature set 2: Differential (crosstalk-cancelled)
        diff_complex = cplx_a - alpha * cplx_b
        diff_mags = np.abs(diff_complex)
        X_diff[idx] = np.concatenate([diff_mags, window])

        # Feature set 3: Transfer function |A/B|
        safe_b = np.where(np.abs(cplx_b) > 1e-10, cplx_b, 1e-10 + 0j)
        ratio_mags = np.abs(cplx_a / safe_b)
        X_ratio[idx] = np.concatenate([ratio_mags, window])

        if (idx + 1) % 10 == 0:
            elapsed = time.time() - t0_cap
            rate = (idx + 1) / elapsed
            eta = (total_usable - idx - 1) / rate
            log(f"    {idx+1}/{total_usable} steps "
                f"({rate:.2f}/s, ETA {eta:.0f}s)")

    log(f"  Capture complete ({time.time() - t0_cap:.1f}s)")

    # ── Phase 4: Evaluate all feature sets ────────────────────────────
    log()
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("  RESULTS")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    y_usable = y[start:start + total_usable]
    y_train, y_test = y_usable[:n_train], y_usable[n_train:]
    results = []

    # Mean baseline
    nm_mean = nmse(y_test, np.full_like(y_test, np.mean(y_train)))
    results.append({"name": "mean_baseline", "nmse_train": 1.0,
                     "nmse_test": round(nm_mean, 6), "features": 0})

    log(f"\n  {'Approach':<40s} {'Train':>10s} {'Test':>10s} {'Feats':>6s}")
    log(f"  {'─'*40} {'─'*10} {'─'*10} {'─'*6}")
    log(f"  {'mean_baseline':<40s} {'1.000':>10s} {nm_mean:>10.4f} {'0':>6s}")

    n_spec = n_rf
    input_cols = list(range(n_spec, n_feats))

    for label, X in [("ch_a", X_cha), ("diff", X_diff), ("ratio", X_ratio)]:
        X_tr, X_te = X[:n_train], X[n_train:]

        # Full (spectrum + input)
        r = evaluate_approach(X_tr, y_train, X_te, y_test,
                              f"{label}_full")
        results.append(r)
        log(f"  {r['name']:<40s} {r['nmse_train']:>10.4f} "
            f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

        # Spectrum only
        r = evaluate_approach(X_tr[:, :n_spec], y_train,
                              X_te[:, :n_spec], y_test,
                              f"{label}_spectrum_only")
        results.append(r)
        log(f"  {r['name']:<40s} {r['nmse_train']:>10.4f} "
            f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

        # Pair aggregation
        X_agg, _ = aggregate_step_pairs(X[:, :n_spec], im_map)
        X_agg_full = np.hstack([X_agg, X[:, n_spec:]])
        r = evaluate_approach(X_agg_full[:n_train], y_train,
                              X_agg_full[n_train:], y_test,
                              f"{label}_pair_agg")
        results.append(r)
        log(f"  {r['name']:<40s} {r['nmse_train']:>10.4f} "
            f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

        # Template residual + pair agg
        X_expected = np.zeros((total_usable, n_spec))
        solo = solo_mags_a if label == "ch_a" else solo_diff
        for idx2 in range(total_usable):
            t2 = start + idx2
            if t2 < NARMA_ORDER:
                continue
            w = u[t2 - 9:t2 + 1] * 2.0
            lp = nf_mags.copy()
            for k in range(len(LADDER_CARRIERS_HZ)):
                lp = lp + w[k] * (solo[k] - nf_mags)
            X_expected[idx2] = lp

        X_resid = X[:, :n_spec] - X_expected
        carrier_idx = [i for i, (_, _, t) in enumerate(im_map)
                       if t == "self"]
        im_idx_list = [i for i, (_, _, t) in enumerate(im_map)
                       if t.startswith("IM")]
        active_idx = sorted(carrier_idx + im_idx_list)
        census_plate = args.plate
        # Build census mags for normalization
        peaks = census.get(census_plate, {}).get("peaks", [])
        median_mag = np.median([p['magnitude'] for p in peaks]) if peaks else 1.0
        census_mags = np.full(n_spec, median_mag)
        for j, rf in enumerate(readout_freqs):
            for p in peaks:
                if abs(p['freq_hz'] - rf) < 500:
                    census_mags[j] = p['magnitude']
                    break

        census_active = census_mags[active_idx]
        resid_norm = X_resid[:, active_idx] / census_active[np.newaxis, :]
        X_ragg, _ = aggregate_step_pairs(
            resid_norm, [im_map[i] for i in active_idx])
        X_rc = np.hstack([X_ragg, X[:, n_spec:]])
        r = evaluate_approach(X_rc[:n_train], y_train,
                              X_rc[n_train:], y_test,
                              f"{label}_resid_agg")
        results.append(r)
        log(f"  {r['name']:<40s} {r['nmse_train']:>10.4f} "
            f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

    # Input-only baselines
    X_input_tr = X_cha[:n_train, n_spec:]
    X_input_te = X_cha[n_train:, n_spec:]
    r = evaluate_approach(X_input_tr, y_train, X_input_te, y_test,
                          "input_window_only")
    results.append(r)
    log(f"  {r['name']:<40s} {r['nmse_train']:>10.4f} "
        f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

    # Software ESN baseline
    log("\n  Running software ESN baseline...")
    esn_hidden = 64
    rng_esn = np.random.default_rng(args.seed + 2000)
    W_in = rng_esn.uniform(-0.1, 0.1, (esn_hidden, NARMA_ORDER))
    W_res = rng_esn.normal(0, 1, (esn_hidden, esn_hidden))
    W_res *= 0.9 / max(np.abs(np.linalg.eigvals(W_res)))
    leak = 0.5

    X_esn = np.zeros((total_usable, esn_hidden))
    state = np.zeros(esn_hidden)
    for idx in range(total_usable):
        t = start + idx
        inp = u[t - 9:t + 1]
        pre = np.tanh(W_in @ inp + W_res @ state)
        state = (1 - leak) * state + leak * pre
        X_esn[idx] = state

    r = evaluate_approach(X_esn[:n_train], y_train,
                          X_esn[n_train:], y_test, "software_esn")
    results.append(r)
    log(f"  {r['name']:<40s} {r['nmse_train']:>10.4f} "
        f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

    # Residual + ESN hybrid (for each feature set)
    log("\n  Running residual + ESN hybrids...")
    for label, X in [("ch_a", X_cha), ("diff", X_diff), ("ratio", X_ratio)]:
        # Build resid_combo (same as above)
        solo = solo_mags_a if label == "ch_a" else solo_diff
        X_expected = np.zeros((total_usable, n_spec))
        for idx2 in range(total_usable):
            t2 = start + idx2
            if t2 < NARMA_ORDER:
                continue
            w = u[t2 - 9:t2 + 1] * 2.0
            lp = nf_mags.copy()
            for k in range(len(LADDER_CARRIERS_HZ)):
                lp = lp + w[k] * (solo[k] - nf_mags)
            X_expected[idx2] = lp

        X_resid = X[:, :n_spec] - X_expected
        resid_norm = X_resid[:, active_idx] / census_active[np.newaxis, :]
        X_ragg, _ = aggregate_step_pairs(
            resid_norm, [im_map[i] for i in active_idx])
        X_rc = np.hstack([X_ragg, X[:, n_spec:]])

        W_in_r = rng_esn.uniform(-0.1, 0.1, (esn_hidden, X_rc.shape[1]))
        W_res_r = rng_esn.normal(0, 1, (esn_hidden, esn_hidden))
        W_res_r *= 0.9 / max(np.abs(np.linalg.eigvals(W_res_r)))
        X_resid_esn = np.zeros((total_usable, esn_hidden))
        st = np.zeros(esn_hidden)
        for idx2 in range(total_usable):
            pre = np.tanh(W_in_r @ X_rc[idx2] + W_res_r @ st)
            st = (1 - leak) * st + leak * pre
            X_resid_esn[idx2] = st

        r = evaluate_approach(X_resid_esn[:n_train], y_train,
                              X_resid_esn[n_train:], y_test,
                              f"{label}_resid_esn")
        results.append(r)
        log(f"  {r['name']:<40s} {r['nmse_train']:>10.4f} "
            f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

    # ── Crosstalk analysis ────────────────────────────────────────────
    log("\n  ── Crosstalk Analysis ──")
    # Compare Ch A vs differential magnitudes at carrier frequencies
    carrier_idx_list = [i for i, (_, _, t) in enumerate(im_map) if t == "self"]
    im_idx_for_analysis = [i for i, (_, _, t) in enumerate(im_map)
                           if t.startswith("IM")]

    mean_cha_carriers = np.mean(X_cha[:, carrier_idx_list], axis=0)
    mean_diff_carriers = np.mean(X_diff[:, carrier_idx_list], axis=0)
    mean_cha_im = np.mean(X_cha[:, im_idx_for_analysis], axis=0)
    mean_diff_im = np.mean(X_diff[:, im_idx_for_analysis], axis=0)

    ct_carrier = 1 - np.mean(mean_diff_carriers / (mean_cha_carriers + 1e-10))
    ct_im = 1 - np.mean(mean_diff_im / (mean_cha_im + 1e-10))
    log(f"  Carrier feedthrough removed: {ct_carrier*100:.1f}%")
    log(f"  IM feedthrough removed: {ct_im*100:.1f}%")
    log(f"  Mean |α|: {np.mean(np.abs(alpha)):.4f}")

    # ── Summary ───────────────────────────────────────────────────────
    log()
    best = min(results, key=lambda r: r["nmse_test"])
    log(f"  ★ BEST: {best['name']} — NMSE {best['nmse_test']:.4f}")

    # ── Save ──────────────────────────────────────────────────────────
    out = {
        "experiment": "narma10_differential",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_steps": args.steps,
        "seed": args.seed,
        "mode": "all_open" if args.all_open else "single_plate",
        "plate": args.plate,
        "n_samples": N_SAMPLES,
        "bin_hz": SAMPLE_RATE / (N_SAMPLES * 4),
        "n_readout_freqs": n_rf,
        "carriers_hz": LADDER_CARRIERS_HZ,
        "feedthrough_alpha_mag_mean": float(np.mean(np.abs(alpha))),
        "feedthrough_alpha_mag_range": [float(np.min(np.abs(alpha))),
                                         float(np.max(np.abs(alpha)))],
        "carrier_feedthrough_pct": float(ct_carrier * 100),
        "im_feedthrough_pct": float(ct_im * 100),
        "results": results,
        "best": best,
    }
    out_path = RESULTS_DIR / f"narma10_diff_{ts_str}.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log(f"\n  Saved: {out_path.name}")

    log("\n══════════════════════════════════════════════════════════════")

    mux.close()
    _close_scope(handle)


if __name__ == "__main__":
    main()
