#!/usr/bin/env python3
"""
NARMA-10 Harmonic Ladder — Spatial Encoding of Temporal Memory

The standard NARMA-10 reservoir approach fails on glass plates because
ringdown τ (1.7–5.3ms) decays before the next capture. This script
replaces temporal memory with SPATIAL intermodulation:

  Instead of sequential single-tone drives (where each step's
  response decays before the next), we present ALL 10 past inputs
  SIMULTANEOUSLY as amplitudes on 10 carrier frequencies chosen to
  sit on harmonic ladders.

  The plate's nonlinear mode coupling physically computes
  u(t-i) × u(t-j) as intermodulation products at fi ± fj.
  We READ these IM products from the same FFT capture — zero
  extra hardware time.

The "ladder" insight:
  If f₁₀ = 2 × f₅ (harmonic relationship), then driving both
  simultaneously creates energy at f₁₀ + f₅ and f₁₀ - f₅ = f₅.
  The mode at f₅ now contains information about BOTH step 5 and
  step 10 — the glass "knows" their relationship structurally,
  not temporally.

NARMA-10 critical term:
  y(t+1) = 0.3·y(t) + 0.05·y(t)·Σy(t-i) + 1.5·u(t-9)·u(t) + 0.1

  The u(t-9)·u(t) product is encoded as IM between f₀ and f₉.
  The y(t)·Σy(t-i) sum is encoded via output feedback on an 11th carrier.

Usage:
  DYLD_LIBRARY_PATH="..." python tools/narma_ladder.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_cross_20260418_142222.json \\
      [--simulate] [--steps 300] [--plate 4]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
RESULTS_DIR = LAB_DIR / "narma10"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ─────────────────────────────────────────────────────

NARMA_ORDER = 10
N_STEPS = 300
N_WASHOUT = 50          # discard first N steps

# Hardware
N_AVG = 8
SETTLE_S = 0.12
SETTLE_RELAY_S = 0.10
AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096

# Readout
IM_TOL_PCT = 2.0        # IM product landing tolerance

# Ridge regression
RIDGE_ALPHAS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]

# ── 10-Tone Carrier Selection ────────────────────────────────────────
# Best IM coverage set from ladder analysis (52% hit rate on strong modes)
LADDER_CARRIERS_HZ = [
    19_000,    # step 0  (u(t-9)) — 2 rx, 3.1M
    23_900,    # step 1  (u(t-8)) — 4 rx, 2.7M, 2× = 47.8k
    29_200,    # step 2  (u(t-7)) — 1 rx, 7.0M, 2× = 58.5k
    29_900,    # step 3  (u(t-6)) — 5 rx, 4.9M, 2× = 58.5k
    34_550,    # step 4  (u(t-5)) — 2 rx, 7.5M, = 17.4k × 2
    37_000,    # step 5  (u(t-4)) — 5 rx, 2.2M, = 19.0k × 2
    45_000,    # step 6  (u(t-3)) — 3 rx, 3.0M, = 15.1k × 3
    49_600,    # step 7  (u(t-2)) — 5 rx, 5.8M
    56_200,    # step 8  (u(t-1)) — 2 rx, 4.2M, = 19.0k × 3
    58_500,    # step 9  (u(t))   — 5 rx, 2.8M, = 29.2k × 2
]

# All mode cluster frequencies (for IM readout landing pads)
MODE_CLUSTERS_HZ = [
    11_425, 15_100, 16_000, 17_375, 19_000, 23_900, 29_200, 29_900,
    31_600, 33_225, 34_550, 36_000, 37_000, 42_300, 45_000, 47_800,
    49_600, 51_500, 53_900, 56_200, 58_500, 62_000, 65_075, 68_200,
    70_800, 73_500, 76_200, 78_800, 81_500, 84_200, 86_900, 89_400,
    95_000,
]

# Plate receivers for multi-plate readout
RECEIVER_MAP = {
    "1":    (1, "A-NE"),
    "2":    (2, "B-NE"),
    "3_NE": (3, "G-NE"),
    "4_NE": (5, "D-NE"),
    "5_NE": (7, "H-NE"),
}

# ── Logging ───────────────────────────────────────────────────────────

_log_lines: list[str] = []

def log(msg: str = "", also_print: bool = True) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    _log_lines.append(f"[{ts}] {msg}")
    if also_print:
        print(msg, flush=True)


# ═══════════════════════════════════════════════════════════════════════
#  NARMA-10 generation
# ═══════════════════════════════════════════════════════════════════════

def generate_narma10(n_steps: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    total = n_steps + NARMA_ORDER + N_WASHOUT
    u = rng.uniform(0, 0.5, total)
    y = np.zeros(total)
    for t in range(NARMA_ORDER, total - 1):
        y_sum = np.sum(y[t - NARMA_ORDER:t + 1])
        y[t + 1] = (0.3 * y[t]
                     + 0.05 * y[t] * y_sum
                     + 1.5 * u[t - 9] * u[t]
                     + 0.1)
        y[t + 1] = np.clip(y[t + 1], 0, 1e6)
    return u, y


# ═══════════════════════════════════════════════════════════════════════
#  IM frequency computation
# ═══════════════════════════════════════════════════════════════════════

def compute_readout_freqs(carriers, all_modes, nyquist=390_000):
    """Compute carrier + IM2 + IM3 readout frequencies.

    Returns (readout_freqs, labels, im_map) where im_map records
    which input steps each IM product encodes.
    """
    readout = []
    labels = []
    im_map = []  # (step_i, step_j, type) for each readout freq

    # 1. All mode cluster frequencies (carriers + non-carriers)
    for f in all_modes:
        readout.append(f)
        # Check if it's a carrier
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

    # 2. IM2: |fi - fj| and fi + fj
    for i in range(len(carriers)):
        for j in range(i + 1, len(carriers)):
            fi, fj = carriers[i], carriers[j]
            for im_f, im_type in [(abs(fi - fj), "IM2d"), (fi + fj, "IM2s")]:
                if im_f < 1000 or im_f > nyquist:
                    continue
                # Check if it lands on a mode
                landed = False
                for mf in all_modes:
                    if abs(im_f - mf) / max(im_f, mf) < IM_TOL_PCT / 100:
                        landed = True
                        if mf not in seen:
                            # Already in readout from step 1
                            pass
                        break
                if landed and im_f not in seen:
                    readout.append(im_f)
                    labels.append(f"{im_type}_{i}x{j}")
                    im_map.append((i, j, im_type))
                    seen.add(im_f)

    # 3. IM3: 2fi - fj (important for NARMA cross-products)
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


def build_census_mag_vector(readout_freqs, census_data, plate_key, tol_hz=500):
    """Build vector of census magnitudes at each readout frequency.

    Returns magnitude at the closest census peak within tol_hz,
    or the median census magnitude for unlisted frequencies.
    """
    peaks = census_data[plate_key]['peaks']
    median_mag = np.median([p['magnitude'] for p in peaks]) if peaks else 1.0
    census_mags = np.full(len(readout_freqs), median_mag)
    for j, rf in enumerate(readout_freqs):
        best_dist = tol_hz + 1
        for p in peaks:
            dist = abs(p['freq_hz'] - rf)
            if dist < best_dist:
                best_dist = dist
                census_mags[j] = p['magnitude']
    return census_mags


def aggregate_step_pairs(X_spec, im_map, n_carriers=10):
    """Aggregate spectral features by step pair.

    Multiple IM products may encode the same (i, j) pair.
    Average them into a single feature per pair, plus one feature
    per carrier (self) and one for all ambient modes.

    Returns (X_agg, pair_labels).
    """
    # Group feature indices by their step pair
    pair_groups = {}  # (i, j) -> [col_indices]
    ambient_cols = []
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

    # Build aggregated matrix
    labels = []
    cols = []
    for key in sorted(pair_groups.keys()):
        group = pair_groups[key]
        cols.append(np.mean(X_spec[:, group], axis=1, keepdims=True))
        if key[0] == key[1]:
            labels.append(f"carrier_{key[0]}")
        else:
            labels.append(f"pair_{key[0]}x{key[1]}")

    # One ambient feature (mean of all ambient modes)
    if ambient_cols:
        cols.append(np.mean(X_spec[:, ambient_cols], axis=1, keepdims=True))
        labels.append("ambient_mean")

    return np.hstack(cols), labels


def capture_enrollment(handle, carriers, readout_freqs, f_rep, mux,
                       plate_key, plate_keys_map):
    """Prescan: capture noise floor + per-carrier solo responses.

    Returns (noise_floor, solo_responses) where:
      noise_floor: shape (n_readout,) — spectrum with no drive
      solo_responses: dict {carrier_idx: shape (n_readout,)} — spectrum
                      when driving carrier_i alone at full amplitude
    """
    relay_ch, rx_name = plate_keys_map[plate_key]
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    from picosdk.ps2000 import ps2000

    # 1. Noise floor: stop AWG, capture
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    time.sleep(SETTLE_S)
    noise_floor = capture_spectrum(handle, readout_freqs)

    # 2. Per-carrier solo responses
    solo = {}
    for i in range(len(carriers)):
        amps = np.zeros(len(carriers))
        amps[i] = 1.0
        drive_multitone(handle, carriers, amps, f_rep)
        solo[i] = capture_spectrum(handle, readout_freqs)

    return noise_floor, solo


# ═══════════════════════════════════════════════════════════════════════
#  PicoScope helpers
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


def _close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    log("  PicoScope closed")


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
#  Simulation (Lorentzian model with nonlinear mixing)
# ═══════════════════════════════════════════════════════════════════════

def simulate_plate_response(carriers, readout_freqs, amplitudes,
                            mode_freqs, mode_Qs=None, nl_strength=0.05,
                            rng=None):
    """Simulate plate response with intermodulation products.

    Uses Lorentzian transfer + quadratic mixing to approximate
    the plate's nonlinear mode coupling.
    """
    if mode_Qs is None:
        mode_Qs = [500] * len(mode_freqs)
    if rng is None:
        rng = np.random.default_rng()

    mags = np.zeros(len(readout_freqs))

    # Linear response: each carrier drives nearby modes
    for ci, (freq, amp) in enumerate(zip(carriers, amplitudes)):
        if amp <= 0:
            continue
        for j, rf in enumerate(readout_freqs):
            for mf, mQ in zip(mode_freqs, mode_Qs):
                # Lorentzian at readout freq when driven at carrier freq
                delta_drive = freq - mf
                delta_read = rf - mf
                bw = mf / (2 * mQ)
                drive_gain = bw**2 / (delta_drive**2 + bw**2)
                read_gain = bw**2 / (delta_read**2 + bw**2)
                mags[j] += amp * drive_gain * read_gain * mQ * 1000

    # Nonlinear IM products: quadratic mixing
    for i in range(len(carriers)):
        for k in range(i + 1, len(carriers)):
            ai, ak = amplitudes[i], amplitudes[k]
            if ai <= 0 or ak <= 0:
                continue
            fi, fk = carriers[i], carriers[k]
            for im_f in [fi + fk, abs(fi - fk)]:
                for j, rf in enumerate(readout_freqs):
                    for mf, mQ in zip(mode_freqs, mode_Qs):
                        delta = im_f - mf
                        bw = mf / (2 * mQ)
                        gain = bw**2 / (delta**2 + bw**2)
                        read_delta = rf - mf
                        read_gain = bw**2 / (read_delta**2 + bw**2)
                        mags[j] += nl_strength * ai * ak * gain * read_gain * mQ * 1000

    # Add realistic noise
    noise_floor = 50.0
    mags += rng.normal(0, noise_floor, len(mags))
    return np.abs(mags)


# ═══════════════════════════════════════════════════════════════════════
#  Feature construction
# ═══════════════════════════════════════════════════════════════════════

def build_features_window(u, y, t, carriers, readout_freqs, im_map,
                          mode_freqs, handle=None, mux=None,
                          plate_keys=None, f_rep=None,
                          simulate=True, rng=None, all_open=False):
    """Build feature vector for NARMA step t.

    Encodes u(t-9)..u(t) as amplitudes on 10 carriers,
    drives simultaneously, reads spectrum including IM products.

    NOTE: No y(t) output feedback — standard NARMA-10 protocol.
    The reservoir must compute temporal products from u(t) only.
    """
    if t < NARMA_ORDER:
        return np.zeros(len(readout_freqs) + NARMA_ORDER)

    # Window of 10 past inputs: u(t-9), u(t-8), ..., u(t)
    window = u[t - 9:t + 1]  # [u(t-9), ..., u(t)]
    assert len(window) == 10

    # Scale to [0, 1] (from [0, 0.5])
    amps = window * 2.0  # now in [0, 1]

    if simulate:
        spectrum = simulate_plate_response(
            carriers, readout_freqs, amps,
            mode_freqs, nl_strength=0.15, rng=rng)
    elif all_open:
        # All-open: all NE relays already closed, single capture
        drive_multitone(handle, carriers, amps, f_rep)
        spectrum = capture_spectrum(handle, readout_freqs)
    else:
        # Hardware: drive all carriers, read from each receiver
        # For single-plate: select relay once, drive+capture
        # For multi-plate: drive once, switch receivers to capture each
        drive_multitone(handle, carriers, amps, f_rep)
        features_all = []
        for key in plate_keys:
            relay_ch, rx_name = RECEIVER_MAP[key]
            if not hasattr(mux, '_last_ch') or mux._last_ch != relay_ch:
                mux.select(relay_ch)
                mux._last_ch = relay_ch
                time.sleep(SETTLE_RELAY_S)
            spec = capture_spectrum(handle, readout_freqs)
            features_all.append(spec)
        spectrum = np.concatenate(features_all)

    # Append raw input window (no y feedback — fair NARMA benchmark)
    return np.concatenate([spectrum, window])


def run_closed_loop(u, y_true, carriers, readout_freqs, im_map,
                    mode_freqs, n_train, start, total_usable,
                    simulate=True, handle=None, mux=None,
                    plate_keys=None, f_rep=None, rng=None,
                    all_open=False):
    """Two-pass closed-loop evaluation with output feedback.

    Pass 1 (open-loop): Capture features using TRUE y(t) as 11th carrier.
                         Train ridge readout.
    Pass 2 (closed-loop): Re-capture using PREDICTED ŷ(t) as 11th carrier.
                           The plate physically computes ŷ(t) × u(t-i).

    The 11th carrier at 11,425 Hz (lowest census mode, well-separated)
    encodes ŷ(t) scaled to [0, 1]. IM products of carrier_11 × carrier_i
    encode ŷ(t) × u(t-i) — exactly the terms NARMA-10 needs.

    In simulation, we run both passes. In hardware, pass 2 requires
    re-driving the AWG for each step (already the normal protocol).
    """
    FEEDBACK_FREQ = 11_425  # 11th carrier for y-feedback

    # Augmented carriers: 10 input + 1 feedback
    carriers_fb = list(carriers) + [FEEDBACK_FREQ]

    # Recompute readout with 11 carriers (more IM products)
    readout_fb, labels_fb, im_map_fb = compute_readout_freqs(
        carriers_fb, MODE_CLUSTERS_HZ)
    n_feats_fb = len(readout_fb) + NARMA_ORDER + 1  # +1 for y_fb scalar

    log(f"  Closed-loop: {len(readout_fb)} readout freqs "
        f"(was {len(readout_freqs)} without feedback carrier)")

    # ── Pass 1: Open-loop with true y(t) ──
    log("  Pass 1: Open-loop capture (teacher forcing)...")
    X_ol = np.zeros((total_usable, n_feats_fb))
    t0 = time.time()

    for idx in range(total_usable):
        t = start + idx
        if t < NARMA_ORDER:
            continue
        window = u[t - 9:t + 1]
        amps_u = window * 2.0  # [0, 1]

        # Encode true y(t) as 11th carrier amplitude
        y_fb = np.clip(y_true[t], 0, 2) / 2.0  # normalize to [0, 1]
        amps_all = list(amps_u) + [y_fb]

        if simulate:
            spectrum = simulate_plate_response(
                carriers_fb, readout_fb, amps_all,
                mode_freqs, nl_strength=0.15, rng=rng)
        elif all_open:
            drive_multitone(handle, carriers_fb, amps_all, f_rep)
            spectrum = capture_spectrum(handle, readout_fb)
        else:
            features_all = []
            for key in plate_keys:
                relay_ch, _ = RECEIVER_MAP[key]
                mux.select(relay_ch)
                time.sleep(SETTLE_RELAY_S)
                drive_multitone(handle, carriers_fb, amps_all, f_rep)
                features_all.append(capture_spectrum(handle, readout_fb))
            spectrum = np.concatenate(features_all)

        X_ol[idx] = np.concatenate([spectrum, window, [y_fb]])

        if (idx + 1) % 50 == 0:
            log(f"    {idx+1}/{total_usable} ({time.time()-t0:.1f}s)")

    # Train readout on pass 1
    y_usable = y_true[start:start + total_usable]
    X_ol_tr = X_ol[:n_train]
    y_ol_tr = y_usable[:n_train]

    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_ol_tr)

    best_alpha, best_val = 1.0, float('inf')
    n_val = n_train // 5
    for alpha in RIDGE_ALPHAS:
        reg = Ridge(alpha=alpha)
        reg.fit(X_s[:n_train - n_val], y_ol_tr[:n_train - n_val])
        pred = reg.predict(X_s[n_train - n_val:])
        v = nmse(y_ol_tr[n_train - n_val:], pred)
        if v < best_val:
            best_val = v
            best_alpha = alpha

    reg = Ridge(alpha=best_alpha)
    reg.fit(X_s, y_ol_tr)
    log(f"  Pass 1 ridge α={best_alpha}")

    # ── Pass 2: Closed-loop with predicted ŷ(t) ──
    log("  Pass 2: Closed-loop capture (predicted feedback)...")
    X_cl = np.zeros((total_usable, n_feats_fb))
    y_pred_cl = np.zeros(total_usable)

    # Warm up with teacher forcing for first n_train steps
    X_cl[:n_train] = X_ol[:n_train]
    y_pred_cl[:n_train] = reg.predict(scaler.transform(X_ol[:n_train]))

    t0 = time.time()
    for idx in range(n_train, total_usable):
        t = start + idx
        window = u[t - 9:t + 1]
        amps_u = window * 2.0

        # Use PREDICTED y from previous step
        y_fb = np.clip(y_pred_cl[idx - 1], 0, 2) / 2.0
        amps_all = list(amps_u) + [y_fb]

        if simulate:
            spectrum = simulate_plate_response(
                carriers_fb, readout_fb, amps_all,
                mode_freqs, nl_strength=0.15, rng=rng)
        elif all_open:
            drive_multitone(handle, carriers_fb, amps_all, f_rep)
            spectrum = capture_spectrum(handle, readout_fb)
        else:
            features_all = []
            for key in plate_keys:
                relay_ch, _ = RECEIVER_MAP[key]
                mux.select(relay_ch)
                time.sleep(SETTLE_RELAY_S)
                drive_multitone(handle, carriers_fb, amps_all, f_rep)
                features_all.append(capture_spectrum(handle, readout_fb))
            spectrum = np.concatenate(features_all)

        feat = np.concatenate([spectrum, window, [y_fb]])
        X_cl[idx] = feat
        y_pred_cl[idx] = reg.predict(scaler.transform(feat.reshape(1, -1)))[0]

        if (idx + 1) % 20 == 0:
            log(f"    {idx+1}/{total_usable} ({time.time()-t0:.1f}s)")

    # Evaluate
    y_test = y_usable[n_train:]
    y_pred_test = y_pred_cl[n_train:]
    y_pred_tr = reg.predict(scaler.transform(X_ol[:n_train]))
    nm_train = nmse(y_ol_tr, y_pred_tr)
    nm_test_ol = nmse(y_test, reg.predict(
        scaler.transform(X_ol[n_train:])))  # open-loop test
    nm_test_cl = nmse(y_test, y_pred_test)  # closed-loop test

    return {
        "open_loop": {
            "name": "ladder_feedback_openloop",
            "nmse_train": round(nm_train, 6),
            "nmse_test": round(nm_test_ol, 6),
            "features": n_feats_fb,
            "best_alpha": best_alpha,
        },
        "closed_loop": {
            "name": "ladder_feedback_closedloop",
            "nmse_train": round(nm_train, 6),
            "nmse_test": round(nm_test_cl, 6),
            "features": n_feats_fb,
            "best_alpha": best_alpha,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
#  NMSE metric
# ═══════════════════════════════════════════════════════════════════════

def nmse(y_true, y_pred):
    var = np.var(y_true)
    if var == 0:
        return float('inf')
    return float(np.mean((y_true - y_pred) ** 2) / var)


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation
# ═══════════════════════════════════════════════════════════════════════

def evaluate_approach(X_train, y_train, X_test, y_test, name=""):
    """Train ridge on (X_train, y_train), evaluate on test.

    Alpha selected via 5-fold CV on training set (no test leakage).
    """
    from sklearn.model_selection import KFold

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
        cv_mean = np.mean(cv_scores)
        if cv_mean < best_cv_nmse:
            best_cv_nmse = cv_mean
            best_alpha = alpha

    # Re-fit with best alpha for final results
    reg = Ridge(alpha=best_alpha)
    reg.fit(X_tr, y_train)
    pred_tr = reg.predict(X_tr)
    pred_te = reg.predict(X_te)
    nm_tr = nmse(y_train, pred_tr)
    nm_te = nmse(y_test, pred_te)

    return {
        "name": name,
        "nmse_train": round(nm_tr, 6),
        "nmse_test": round(nm_te, 6),
        "features": X_train.shape[1],
        "best_alpha": best_alpha,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="NARMA-10 Harmonic Ladder")
    parser.add_argument("--census", required=True)
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--plate", default="4_NE",
                        help="Primary plate key for single-plate mode")
    parser.add_argument("--simulate", action="store_true",
                        help="Use simulation instead of hardware")
    parser.add_argument("--steps", type=int, default=N_STEPS)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--multi-plate", action="store_true",
                        help="Read from 5 NE receivers instead of 1")
    parser.add_argument("--all-open", action="store_true",
                        help="Open all 5 NE relays simultaneously — "
                             "single capture per step, ~5× faster")
    parser.add_argument("--fast", action="store_true",
                        help="Reduce settle/averages for rapid capture "
                             "(5ms settle, 2 avg → ~30ms/step)")
    args = parser.parse_args()

    if args.multi_plate and args.all_open:
        parser.error("--multi-plate and --all-open are mutually exclusive")

    if args.fast:
        global SETTLE_S, N_AVG
        SETTLE_S = 0.005   # 5ms settle (modes ring up in <5ms for Q>50)
        N_AVG = 2          # 2 averages instead of 8

    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    log("══════════════════════════════════════════════════════════════")
    log("  NARMA-10 HARMONIC LADDER — Spatial Encoding of Temporal Memory")
    log("══════════════════════════════════════════════════════════════")
    log()

    # Load census for mode frequencies
    with open(args.census) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    # Collect all mode frequencies
    all_mode_freqs = set()
    for key, data in census.items():
        for p in data.get("peaks", []):
            all_mode_freqs.add(p["freq_hz"])

    mode_freqs = sorted(all_mode_freqs)
    log(f"  Census modes: {len(mode_freqs)}")
    log(f"  Carriers: {[f/1000 for f in LADDER_CARRIERS_HZ]}k")

    # Compute readout frequencies (carriers + IM2 + IM3 landing pads)
    readout_freqs, readout_labels, im_map = compute_readout_freqs(
        LADDER_CARRIERS_HZ, MODE_CLUSTERS_HZ)

    n_carrier = sum(1 for _, _, t in im_map if t == "self")
    n_ambient = sum(1 for _, _, t in im_map if t == "ambient")
    n_im2 = sum(1 for _, _, t in im_map if t.startswith("IM2"))
    n_im3 = sum(1 for _, _, t in im_map if t == "IM3")
    log(f"  Readout frequencies: {len(readout_freqs)}")
    log(f"    Carriers: {n_carrier}, Ambient modes: {n_ambient}, "
        f"IM2: {n_im2}, IM3: {n_im3}")

    # Check which IM products encode which step pairs
    step_pairs = set()
    for i, j, t in im_map:
        if t.startswith("IM") and i >= 0 and j >= 0 and i != j:
            step_pairs.add((min(i, j), max(i, j)))
    log(f"  Step pairs with IM coverage: {len(step_pairs)}/45")

    # The critical pair for NARMA-10: steps 0 and 9 (u(t-9) × u(t))
    critical_pair = (0, 9)
    has_critical = critical_pair in step_pairs
    log(f"  Critical u(t-9)×u(t) pair: {'✓ COVERED' if has_critical else '✗ MISSING'}")
    log()

    # Generate NARMA-10
    log("  Generating NARMA-10 time series...")
    u, y = generate_narma10(args.steps, args.seed)

    # Effective indices after warmup
    start = NARMA_ORDER + N_WASHOUT
    total_usable = len(u) - start
    n_train = int(total_usable * 0.67)
    n_test = total_usable - n_train

    log(f"  Steps: {len(u)} total, {total_usable} usable "
        f"({n_train} train / {n_test} test)")
    log()

    # ── Feature matrix construction ───────────────────────────────────

    if args.simulate:
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("  SIMULATION MODE")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        plate_keys = None
        handle = None
        mux = None
        f_rep = None
        noise_floor = None
        solo_responses = None
        rng = np.random.default_rng(args.seed + 1000)

        # Simulate enrollment: noise floor and solo responses
        noise_floor_sim = simulate_plate_response(
            LADDER_CARRIERS_HZ, readout_freqs,
            np.zeros(len(LADDER_CARRIERS_HZ)),
            mode_freqs, nl_strength=0.15,
            rng=np.random.default_rng(args.seed + 5000))
        solo_responses_sim = {}
        for ci in range(len(LADDER_CARRIERS_HZ)):
            amps = np.zeros(len(LADDER_CARRIERS_HZ))
            amps[ci] = 1.0
            solo_responses_sim[ci] = simulate_plate_response(
                LADDER_CARRIERS_HZ, readout_freqs, amps,
                mode_freqs, nl_strength=0.15,
                rng=np.random.default_rng(args.seed + 5001 + ci))
        noise_floor = noise_floor_sim
        solo_responses = solo_responses_sim

        n_feats = len(readout_freqs) + NARMA_ORDER
        X = np.zeros((total_usable, n_feats))

        t0 = time.time()
        for idx in range(total_usable):
            t = start + idx
            X[idx] = build_features_window(
                u, y, t, LADDER_CARRIERS_HZ, readout_freqs, im_map,
                mode_freqs, simulate=True, rng=rng)
            if (idx + 1) % 50 == 0:
                elapsed = time.time() - t0
                log(f"    {idx+1}/{total_usable} steps ({elapsed:.1f}s)")

    else:
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("  HARDWARE CAPTURE")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        from relay_mux import RelayMux
        handle = _open_scope()
        mux = RelayMux(args.port)
        mux.open()
        time.sleep(0.5)

        # Compute f_rep for ARB waveform
        max_freq = max(LADDER_CARRIERS_HZ)
        f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))
        log(f"  f_rep = {f_rep:.1f} Hz")

        if args.all_open:
            # All-open: close all 5 NE relays once, single capture per step
            log("  All-open mode: activating all NE relays...")
            mux.all_ne()
            time.sleep(SETTLE_RELAY_S)
            plate_keys = ["all_ne"]
            n_feats = len(readout_freqs) + NARMA_ORDER
            log(f"  All-open: 5 plates summed → {len(readout_freqs)} spectral + "
                f"{NARMA_ORDER} input = {n_feats} features")
            log(f"  Expected speed: ~3 steps/s (no relay switching)")
        elif args.multi_plate:
            plate_keys = list(RECEIVER_MAP.keys())
            n_feats = len(readout_freqs) * len(plate_keys) + NARMA_ORDER
            log(f"  Multi-plate: {len(plate_keys)} receivers × "
                f"{len(readout_freqs)} freqs = {n_feats - NARMA_ORDER} spectral + "
                f"{NARMA_ORDER} input features")
        else:
            plate_keys = [args.plate]
            n_feats = len(readout_freqs) + NARMA_ORDER

        # ── Enrollment prescan ────────────────────────────────────
        enroll_t0 = time.time()
        if args.all_open:
            log("  Enrollment prescan (per-plate solo + all-open combined)...")
            # Capture per-plate solo responses for diagnostics,
            # then all-open combined for the main enrollment
            per_plate_enrollment = {}
            for pk, (rch, rxn) in RECEIVER_MAP.items():
                if not rxn.endswith("NE"):
                    continue
                mux.select(rch)
                time.sleep(SETTLE_RELAY_S)
                nf, sr = capture_enrollment(
                    handle, LADDER_CARRIERS_HZ, readout_freqs, f_rep,
                    mux, pk, RECEIVER_MAP)
                per_plate_enrollment[pk] = {"noise_floor": nf, "solo": sr}
                log(f"    {rxn}: nf_max={np.max(nf):.0f}, "
                    f"solo_max={np.max([np.max(s) for s in sr.values()]):.0f}")

            # Now capture all-open combined enrollment
            mux.all_ne()
            time.sleep(SETTLE_RELAY_S)
            from picosdk.ps2000 import ps2000
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
            time.sleep(SETTLE_S)
            noise_floor = capture_spectrum(handle, readout_freqs)
            solo_responses = {}
            for ci in range(len(LADDER_CARRIERS_HZ)):
                amps = np.zeros(len(LADDER_CARRIERS_HZ))
                amps[ci] = 1.0
                drive_multitone(handle, LADDER_CARRIERS_HZ, amps, f_rep)
                solo_responses[ci] = capture_spectrum(handle, readout_freqs)
            log(f"  All-open enrollment done ({time.time() - enroll_t0:.1f}s, "
                f"noise_floor max={np.max(noise_floor):.0f}, "
                f"solo range={np.min([np.max(s) for s in solo_responses.values()]):.0f}"
                f"–{np.max([np.max(s) for s in solo_responses.values()]):.0f})")
        else:
            log("  Enrollment prescan (noise floor + solo carriers)...")
            noise_floor, solo_responses = capture_enrollment(
                handle, LADDER_CARRIERS_HZ, readout_freqs, f_rep,
                mux, plate_keys[0], RECEIVER_MAP)
            log(f"  Enrollment done ({time.time() - enroll_t0:.1f}s, "
                f"noise_floor max={np.max(noise_floor):.0f}, "
                f"solo range={np.min([np.max(s) for s in solo_responses.values()]):.0f}"
                f"–{np.max([np.max(s) for s in solo_responses.values()]):.0f})")

        # Checkpoint path for crash recovery
        ckpt_path = RESULTS_DIR / f"narma10_checkpoint_{ts_str}.npz"

        X = np.zeros((total_usable, n_feats))
        t0 = time.time()
        for idx in range(total_usable):
            t = start + idx
            X[idx] = build_features_window(
                u, y, t, LADDER_CARRIERS_HZ, readout_freqs, im_map,
                mode_freqs, handle=handle, mux=mux,
                plate_keys=plate_keys, f_rep=f_rep,
                simulate=False, all_open=args.all_open)
            if (idx + 1) % 10 == 0:
                elapsed = time.time() - t0
                rate = (idx + 1) / elapsed
                eta = (total_usable - idx - 1) / rate
                log(f"    {idx+1}/{total_usable} steps "
                    f"({rate:.2f}/s, ETA {eta:.0f}s)")
            # Save checkpoint every 100 steps
            if (idx + 1) % 100 == 0 or idx == total_usable - 1:
                ckpt_data = dict(
                    X=X[:idx+1],
                    u=u, y=y,
                    noise_floor=noise_floor if noise_floor is not None else np.array([]),
                    readout_freqs=np.array(readout_freqs),
                    carriers=np.array(LADDER_CARRIERS_HZ),
                    n_completed=idx+1,
                    start=start, n_train=n_train,
                    total_usable=total_usable)
                if solo_responses is not None:
                    for k, v in solo_responses.items():
                        ckpt_data[f"solo_{k}"] = v
                np.savez_compressed(ckpt_path, **ckpt_data)

        # Scope/mux stay open for closed-loop pass later
        log(f"  Open-loop capture complete ({idx+1} steps saved to checkpoint)")

    log(f"\n  Feature matrix: {X.shape}")

    # ── Train/test split ──────────────────────────────────────────────

    y_usable = y[start:start + total_usable]

    X_train, X_test = X[:n_train], X[n_train:]
    y_train, y_test = y_usable[:n_train], y_usable[n_train:]

    # ── Evaluate approaches ───────────────────────────────────────────

    log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("  RESULTS")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    results = []

    # 0. Mean baseline
    nm_mean = nmse(y_test, np.full_like(y_test, np.mean(y_train)))
    results.append({"name": "mean_baseline", "nmse_train": 1.0,
                     "nmse_test": round(nm_mean, 6), "features": 0})
    log(f"\n  {'Approach':<35s} {'Train':>10s} {'Test':>10s} {'Feats':>6s}")
    log(f"  {'─'*35} {'─'*10} {'─'*10} {'─'*6}")
    log(f"  {'mean_baseline':<35s} {'1.000':>10s} {nm_mean:>10.4f} {'0':>6s}")

    # 1. Ladder full (spectrum + input + output feedback)
    r = evaluate_approach(X_train, y_train, X_test, y_test, "ladder_full")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 2. Spectrum only (no raw input append)
    n_spec = len(readout_freqs) if (args.simulate or args.all_open) else (
        len(readout_freqs) * (len(plate_keys) if args.multi_plate and not args.simulate else 1))
    X_spec_tr = X_train[:, :n_spec]
    X_spec_te = X_test[:, :n_spec]
    r = evaluate_approach(X_spec_tr, y_train, X_spec_te, y_test, "ladder_spectrum_only")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 3. Input window only (no plate, just raw u(t-9)..u(t) + y(t))
    X_input_tr = X_train[:, n_spec:]
    X_input_te = X_test[:, n_spec:]
    r = evaluate_approach(X_input_tr, y_train, X_input_te, y_test, "input_window_only")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 4. Input window + polynomial features (software baseline)
    from sklearn.preprocessing import PolynomialFeatures
    poly = PolynomialFeatures(degree=2, include_bias=False)
    X_poly_tr = poly.fit_transform(X_input_tr)
    X_poly_te = poly.transform(X_input_te)
    r = evaluate_approach(X_poly_tr, y_train, X_poly_te, y_test,
                          "input_poly2")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 5. Ladder spectrum + polynomial features
    poly2 = PolynomialFeatures(degree=2, include_bias=False,
                                interaction_only=True)
    # Only do interactions on top-K spectral features to avoid explosion
    top_k = min(20, n_spec)
    # Pick highest-variance spectral features
    var_idx = np.argsort(-np.var(X_spec_tr, axis=0))[:top_k]
    X_topk_tr = X_train[:, var_idx]
    X_topk_te = X_test[:, var_idx]
    X_topk_input_tr = np.hstack([X_topk_tr, X_input_tr])
    X_topk_input_te = np.hstack([X_topk_te, X_input_te])
    X_int_tr = poly2.fit_transform(X_topk_input_tr)
    X_int_te = poly2.transform(X_topk_input_te)
    r = evaluate_approach(X_int_tr, y_train, X_int_te, y_test,
                          "ladder_top20_poly_interact")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 6. Software ESN baseline (same as original NARMA-10)
    log("\n  Running software ESN baseline...")
    esn_hidden = 64
    rng_esn = np.random.default_rng(args.seed + 2000)
    W_in = rng_esn.uniform(-0.1, 0.1, (esn_hidden, NARMA_ORDER))
    W_res = rng_esn.normal(0, 1, (esn_hidden, esn_hidden))
    # Scale to spectral radius 0.9
    eigvals = np.abs(np.linalg.eigvals(W_res))
    W_res *= 0.9 / max(eigvals)
    leak = 0.5

    X_esn = np.zeros((total_usable, esn_hidden))
    state = np.zeros(esn_hidden)
    for idx in range(total_usable):
        t = start + idx
        inp = u[t - 9:t + 1]
        pre = np.tanh(W_in @ inp + W_res @ state)
        state = (1 - leak) * state + leak * pre
        X_esn[idx] = state

    X_esn_tr, X_esn_te = X_esn[:n_train], X_esn[n_train:]
    r = evaluate_approach(X_esn_tr, y_train, X_esn_te, y_test, "software_esn")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 7. Ladder + ESN (plate features through ESN for temporal depth)
    W_in_plate = rng_esn.uniform(-0.1, 0.1, (esn_hidden, X.shape[1]))
    W_res2 = rng_esn.normal(0, 1, (esn_hidden, esn_hidden))
    eigvals2 = np.abs(np.linalg.eigvals(W_res2))
    W_res2 *= 0.9 / max(eigvals2)

    X_ladder_esn = np.zeros((total_usable, esn_hidden))
    state2 = np.zeros(esn_hidden)
    for idx in range(total_usable):
        pre = np.tanh(W_in_plate @ X[idx] + W_res2 @ state2)
        state2 = (1 - leak) * state2 + leak * pre
        X_ladder_esn[idx] = state2

    X_le_tr, X_le_te = X_ladder_esn[:n_train], X_ladder_esn[n_train:]
    r = evaluate_approach(X_le_tr, y_train, X_le_te, y_test, "ladder_esn")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 8. Combined: ladder features + ESN state
    X_combo_tr = np.hstack([X_train, X_le_tr])
    X_combo_te = np.hstack([X_test, X_le_te])
    r = evaluate_approach(X_combo_tr, y_train, X_combo_te, y_test,
                          "ladder_plus_esn_concat")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # ── Enrollment-based denoising approaches ─────────────────────────
    log("\n  Running enrollment-based denoising approaches...")

    # Build census magnitude vector for normalization
    census_plate = args.plate if args.all_open else (
        plate_keys[0] if plate_keys else args.plate)
    census_mags_1p = build_census_mag_vector(readout_freqs, census, census_plate)

    # In multi-plate mode, tile single-plate vectors to match n_spec
    n_plates = len(plate_keys) if args.multi_plate and not args.simulate and not args.all_open else 1
    n_rf = len(readout_freqs)
    census_mags = np.tile(census_mags_1p, n_plates)

    # Feature type indices from im_map (per single plate)
    carrier_idx_1p = [i for i, (_, _, t) in enumerate(im_map) if t == "self"]
    im_idx_1p = [i for i, (_, _, t) in enumerate(im_map) if t.startswith("IM")]
    active_idx_1p = sorted(carrier_idx_1p + im_idx_1p)

    # Expand indices across all plates
    carrier_idx = [i + p * n_rf for p in range(n_plates) for i in carrier_idx_1p]
    im_idx = [i + p * n_rf for p in range(n_plates) for i in im_idx_1p]
    active_idx = sorted(carrier_idx + im_idx)
    input_cols = list(range(n_spec, X.shape[1]))

    # Build tiled im_map for multi-plate aggregate_step_pairs calls
    if n_plates > 1:
        n_carriers = len(LADDER_CARRIERS_HZ)
        im_map_full = []
        for p in range(n_plates):
            offset = p * n_carriers
            for (i, j, t) in im_map:
                im_map_full.append((i + offset, j + offset, t))
    else:
        im_map_full = im_map

    # 9. Census-normalized spectrum + inputs
    X_cnorm = X.copy()
    X_cnorm[:, :n_spec] = X_cnorm[:, :n_spec] / census_mags[np.newaxis, :]
    r = evaluate_approach(X_cnorm[:n_train], y_train,
                          X_cnorm[n_train:], y_test, "ladder_census_norm")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 10. IM-only features (drop ambient modes)
    active_cols = active_idx + input_cols
    X_active_tr = X_train[:, active_cols]
    X_active_te = X_test[:, active_cols]
    r = evaluate_approach(X_active_tr, y_train, X_active_te, y_test,
                          "ladder_im_only")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 11. Log-magnitude + census normalization
    X_logc = X.copy()
    X_logc[:, :n_spec] = np.log1p(X_logc[:, :n_spec] / census_mags[np.newaxis, :])
    r = evaluate_approach(X_logc[:n_train], y_train,
                          X_logc[n_train:], y_test, "ladder_log_census")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 12. Step-pair aggregation (117 spectral → ~55 pair features)
    X_agg, agg_labels = aggregate_step_pairs(X[:, :n_spec], im_map_full)
    X_agg_full = np.hstack([X_agg, X[:, n_spec:]])
    r = evaluate_approach(X_agg_full[:n_train], y_train,
                          X_agg_full[n_train:], y_test, "ladder_pair_agg")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 13. Denoised combo: IM-only + census-norm + log + pair aggregation
    X_spec_active = X[:, active_idx]
    census_mags_active = census_mags[active_idx]
    X_spec_clean = np.log1p(X_spec_active / census_mags_active[np.newaxis, :])
    X_agg_clean, _ = aggregate_step_pairs(X_spec_clean,
                                           [im_map_full[i] for i in active_idx])
    X_denoised = np.hstack([X_agg_clean, X[:, n_spec:]])
    r = evaluate_approach(X_denoised[:n_train], y_train,
                          X_denoised[n_train:], y_test, "ladder_denoised")
    results.append(r)
    log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
        f"{r['features']:>6d}")

    # 14-15. Template residual (enrollment-based)
    if noise_floor is not None and solo_responses is not None:
        log("  Computing template residuals from enrollment...")
        # Build expected linear response for each step
        # In multi-plate mode, tile single-plate enrollment across plates
        nf_full = np.tile(noise_floor, n_plates)
        solo_full = {k: np.tile(v, n_plates) for k, v in solo_responses.items()}
        X_expected = np.zeros((total_usable, n_spec))
        for idx in range(total_usable):
            t = start + idx
            if t < NARMA_ORDER:
                continue
            window = u[t - 9:t + 1] * 2.0  # amplitudes [0,1]
            linear_pred = nf_full.copy()
            for k in range(len(LADDER_CARRIERS_HZ)):
                linear_pred = linear_pred + window[k] * (
                    solo_full[k] - nf_full)
            X_expected[idx] = linear_pred

        # Raw residual + inputs
        X_resid = X[:, :n_spec] - X_expected
        X_resid_full = np.hstack([X_resid, X[:, n_spec:]])
        r = evaluate_approach(X_resid_full[:n_train], y_train,
                              X_resid_full[n_train:], y_test,
                              "ladder_template_resid")
        results.append(r)
        log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} "
            f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

        # Residual + census-norm + log + pair aggregation
        resid_active = X_resid[:, active_idx]
        # Shift residual to positive for log: use abs + sign preservation
        resid_norm = resid_active / census_mags_active[np.newaxis, :]
        X_resid_agg, _ = aggregate_step_pairs(
            resid_norm, [im_map_full[i] for i in active_idx])
        X_resid_combo = np.hstack([X_resid_agg, X[:, n_spec:]])
        r = evaluate_approach(X_resid_combo[:n_train], y_train,
                              X_resid_combo[n_train:], y_test,
                              "ladder_resid_agg")
        results.append(r)
        log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} "
            f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

        # Template residual + denoised combo through ESN
        W_in_resid = rng_esn.uniform(-0.1, 0.1,
                                      (esn_hidden, X_resid_combo.shape[1]))
        W_res3 = rng_esn.normal(0, 1, (esn_hidden, esn_hidden))
        eigvals3 = np.abs(np.linalg.eigvals(W_res3))
        W_res3 *= 0.9 / max(eigvals3)
        X_resid_esn = np.zeros((total_usable, esn_hidden))
        state3 = np.zeros(esn_hidden)
        for idx in range(total_usable):
            pre = np.tanh(W_in_resid @ X_resid_combo[idx] + W_res3 @ state3)
            state3 = (1 - leak) * state3 + leak * pre
            X_resid_esn[idx] = state3
        r = evaluate_approach(X_resid_esn[:n_train], y_train,
                              X_resid_esn[n_train:], y_test,
                              "ladder_resid_esn")
        results.append(r)
        log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} "
            f"{r['nmse_test']:>10.4f} {r['features']:>6d}")

    # 16. Closed-loop with output feedback on 11th carrier
    log("\n  Running closed-loop (output feedback on 11th carrier)...")
    rng_cl = np.random.default_rng(args.seed + 3000) if args.simulate else None
    cl_results = run_closed_loop(
        u, y, LADDER_CARRIERS_HZ, readout_freqs, im_map,
        mode_freqs, n_train, start, total_usable,
        simulate=args.simulate, handle=None if args.simulate else handle,
        mux=None if args.simulate else mux,
        plate_keys=plate_keys if not args.simulate else None,
        f_rep=f_rep if not args.simulate else None,
        rng=rng_cl,
        all_open=args.all_open if not args.simulate else False)
    for key in ["open_loop", "closed_loop"]:
        r = cl_results[key]
        results.append(r)
        log(f"  {r['name']:<35s} {r['nmse_train']:>10.4f} {r['nmse_test']:>10.4f} "
            f"{r['features']:>6d}")

    # ── Summary ───────────────────────────────────────────────────────

    best = min(results, key=lambda r: r["nmse_test"])
    log(f"\n  ★ BEST: {best['name']} — NMSE {best['nmse_test']:.4f}")

    # Quality assessment
    nm = best["nmse_test"]
    if nm < 0.1:
        quality = "EXCELLENT"
    elif nm < 0.3:
        quality = "GOOD"
    elif nm < 0.5:
        quality = "MARGINAL"
    elif nm < 1.0:
        quality = "WEAK (but better than mean)"
    else:
        quality = "NO BETTER THAN MEAN"
    log(f"  Quality: {quality}")

    prev_best = 0.666  # software ESN from Run 3
    if nm < prev_best:
        log(f"  ▲ BEATS previous best ({prev_best:.3f}) by {(prev_best-nm)/prev_best*100:.1f}%")
    else:
        log(f"  ▼ Previous best: {prev_best:.3f} (software ESN)")

    # ── Save ──────────────────────────────────────────────────────────

    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "narma10_harmonic_ladder",
        "mode": "simulate" if args.simulate else (
            "hardware_all_open" if args.all_open else (
                "hardware_multi_plate" if args.multi_plate else "hardware")),
        "all_open": args.all_open,
        "n_steps": args.steps,
        "seed": args.seed,
        "carriers_hz": LADDER_CARRIERS_HZ,
        "n_readout_freqs": len(readout_freqs),
        "n_im_pairs": len(step_pairs),
        "has_critical_pair": has_critical,
        "readout_labels": readout_labels[:20],  # first 20 for reference
        "results": results,
        "best": best,
    }
    out_path = RESULTS_DIR / f"narma10_ladder_{ts_str}.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log(f"\n  Saved: {out_path.name}")

    log_path = RESULTS_DIR / f"narma10_ladder_{ts_str}.log"
    with open(log_path, "w") as f:
        f.write("\n".join(_log_lines) + "\n")

    log("\n══════════════════════════════════════════════════════════════")

    # ── Cleanup hardware ──────────────────────────────────────────────
    if not args.simulate:
        try:
            mux.close()
        except Exception:
            pass
        _close_scope(handle)


if __name__ == "__main__":
    main()
