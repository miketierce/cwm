#!/usr/bin/env python3
"""
Plate Sequence ESN v4 — Multi-Level Amplitude Encoding: Find the Breakpoint

Goal: Determine the maximum number of distinguishable tokens per plate by
sweeping the number of amplitude levels per mode from 2 (binary, v3 baseline)
through 16 (max AWG resolution with 8 tones). For each level count L, sample
tokens from the L^8 alphabet, calibrate, and test ESN sequence reversal.

The breakpoint is the L where per-bit accuracy drops below a usefulness
threshold (e.g., 90% per-bit → ~43% token accuracy at 8 bits).

Design:
  - L levels per mode → L^8 total tokens in the full alphabet
  - Since L^8 grows fast (4^8=65536, 8^8=16M), we can't calibrate all tokens.
  - For L≤4 (≤65536 tokens): calibrate a representative sample (up to 1024).
  - For L>4: calibrate 512 tokens (randomly sampled from L^8 space).
  - ESN readout predicts the L-ary digit at each mode position (not binary bits).
  - Software baseline: raw L-ary digits (8d, one-hot or scalar).

Usage:
  PYTHONPATH=. python tools/plate_sequence_esn_v4.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_sequence_esn_v4.py --dry-run
  PYTHONPATH=. python tools/plate_sequence_esn_v4.py --dry-run --levels 2,3,4
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

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import cwm_picoscope
from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux

# ── Configuration ─────────────────────────────────────────────────────

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}
TARGET_PLATES = ["4", "5"]

N_MODES = 8                   # modes per plate (D and E both have 8)
DEFAULT_LEVELS = [2, 3, 4, 6, 8, 12, 16]

# Calibration limits
MAX_CALIB_TOKENS = 1024       # max tokens to calibrate per plate per level
MAX_CALIB_TOKENS_LARGE = 512  # for L>4 where L^8 is huge
N_CALIB_REPS = 6              # reps per token (slightly fewer than v3 to save time)
N_AVG = 4                     # FFT averages per capture

# ESN parameters (same as v3 tuned)
SEQ_LENGTH = 4
N_SEQUENCES = 2000
ESN_HIDDEN = 200
ESN_SPECTRAL = 0.9
ESN_INPUT_SCALE = 0.1
ESN_LEAK = 0.9
RIDGE_ALPHA = 10.0

T_EXCITE_S = 0.30
SETTLE_RELAY_S = 0.10


# ── Token encoding helpers ────────────────────────────────────────────

def encode_token_multilevel(token_digits, n_levels):
    """
    Convert a list of L-ary digits [d0, d1, ..., d7] into a single token ID.
    token_id = d0 + d1*L + d2*L^2 + ... + d7*L^7
    """
    token_id = 0
    for i, d in enumerate(token_digits):
        token_id += int(d) * (n_levels ** i)
    return token_id


def decode_token_multilevel(token_id, n_levels, n_modes=N_MODES):
    """
    Convert a token ID back to L-ary digits [d0, d1, ..., d7].
    """
    digits = []
    for _ in range(n_modes):
        digits.append(token_id % n_levels)
        token_id //= n_levels
    return digits


def amplitude_levels(n_levels):
    """
    Return n_levels evenly spaced amplitude values in [0.0, 1.0].
    Level 0 = 0.0 (OFF), Level (L-1) = 1.0 (max).
    For L=2: [0.0, 1.0] (binary, same as v3).
    For L=4: [0.0, 0.333, 0.667, 1.0].
    """
    if n_levels < 2:
        return [0.0, 1.0]
    return [i / (n_levels - 1) for i in range(n_levels)]


def sample_token_set(n_levels, max_tokens, seed=42):
    """
    Choose which tokens to calibrate.
    For small alphabets (L^8 <= max_tokens): all tokens.
    Otherwise: random sample + ensure all L^N_MODES corner cases are included.
    """
    total = n_levels ** N_MODES
    if total <= max_tokens:
        # Calibrate ALL tokens
        return list(range(total))

    rng = np.random.default_rng(seed)

    # Always include: all-zeros, all-max, single-mode-at-each-level
    required = set()
    required.add(0)  # all zeros
    required.add(total - 1)  # all max

    # Single mode active at each level
    for m in range(N_MODES):
        for lv in range(n_levels):
            digits = [0] * N_MODES
            digits[m] = lv
            required.add(encode_token_multilevel(digits, n_levels))

    # Fill remaining with random
    n_random = max_tokens - len(required)
    if n_random > 0:
        candidates = rng.integers(0, total, size=n_random * 3)
        candidates = set(int(c) for c in candidates) - required
        candidates = list(candidates)[:n_random]
        required.update(candidates)

    return sorted(required)


# ── Hardware helpers (same as v3) ─────────────────────────────────────

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    print("  PicoScope opened (Ch A ±1V DC)")
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
    print("  PicoScope closed")


def _awg_off(handle):
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)


def _drive_multitone_arb(handle, freqs_hz, amplitudes, fixed_f_rep,
                         drive_uvpp=AWG_DRIVE_UVPP):
    from picosdk.ps2000 import ps2000
    if not freqs_hz or all(a == 0 for a in amplitudes):
        _awg_off(handle)
        return
    arb_len = 4096
    delta_phase = int(fixed_f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1
    buf = np.zeros(arb_len, dtype=np.float64)
    for f, a in zip(freqs_hz, amplitudes):
        if a <= 0:
            continue
        k = round(f / fixed_f_rep)
        if k < 1 or k > arb_len // 2:
            continue
        phase = 2 * np.pi * k * np.arange(arb_len) / arb_len
        buf += a * np.sin(phase)
    peak = np.max(np.abs(buf))
    if peak > 0:
        buf /= peak
    arb_u8 = ((buf * 127) + 128).clip(0, 255).astype(np.uint8)
    arb_buf = (ctypes.c_uint8 * arb_len)(*arb_u8.tolist())
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, drive_uvpp,
        delta_phase, delta_phase, 0, 0,
        arb_buf, arb_len, 0, 0)


def _capture_spectrum(handle, readout_freqs, n_avg=N_AVG):
    from picosdk.ps2000 import ps2000
    all_mags = []
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
            for j, f in enumerate(readout_freqs):
                tb = int(round(f / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(fft_mag) - 1, tb + 3)
                mags[j] = float(np.max(fft_mag[lo:hi + 1]))
            all_mags.append(mags)
    if all_mags:
        return np.mean(all_mags, axis=0)
    return np.zeros(len(readout_freqs))


# ── Census / mode loading ─────────────────────────────────────────────

def _load_all_modes() -> dict[str, list[float]]:
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name)
    if not census_files:
        raise FileNotFoundError("No census file.")
    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]
    modes = {}
    for pid in PLATE_NAMES:
        if pid in census and census[pid].get("peaks"):
            modes[pid] = [p["freq_hz"] for p in census[pid]["peaks"]]
    return modes


# ── ESN ───────────────────────────────────────────────────────────────

class ESN:
    def __init__(self, input_dim, hidden_dim=ESN_HIDDEN,
                 spectral_radius=ESN_SPECTRAL, input_scale=ESN_INPUT_SCALE,
                 leak=ESN_LEAK, seed=42):
        rng = np.random.default_rng(seed)
        self.hidden_dim = hidden_dim
        self.leak = leak
        self.W_in = rng.standard_normal((hidden_dim, input_dim)) * input_scale
        W = rng.standard_normal((hidden_dim, hidden_dim))
        rho = np.max(np.abs(np.linalg.eigvals(W)))
        self.W_rec = W * (spectral_radius / rho) if rho > 0 else W

    def run_sequence(self, feat_seq):
        h = np.zeros(self.hidden_dim)
        for x in feat_seq:
            h = (1 - self.leak) * h + self.leak * np.tanh(
                self.W_in @ x + self.W_rec @ h)
        return h

    def collect_states(self, all_seqs):
        return np.array([self.run_sequence(s) for s in all_seqs])


def ridge_binary(H_tr, H_te, y_tr, y_te, alpha=RIDGE_ALPHA):
    Hb_tr = np.column_stack([H_tr, np.ones(len(H_tr))])
    Hb_te = np.column_stack([H_te, np.ones(len(H_te))])
    d = Hb_tr.shape[1]
    w = np.linalg.solve(Hb_tr.T @ Hb_tr + alpha * np.eye(d),
                        Hb_tr.T @ y_tr.astype(np.float64))
    preds = (Hb_te @ w > 0.5).astype(int)
    acc = float(np.mean(preds == y_te))
    return acc, preds


def ridge_multiclass(H_tr, H_te, y_tr, y_te, n_classes, alpha=RIDGE_ALPHA):
    Hb_tr = np.column_stack([H_tr, np.ones(len(H_tr))])
    Hb_te = np.column_stack([H_te, np.ones(len(H_te))])
    d = Hb_tr.shape[1]
    Y_oh = np.zeros((len(y_tr), n_classes))
    for i, c in enumerate(y_tr):
        Y_oh[i, c] = 1.0
    W = np.linalg.solve(Hb_tr.T @ Hb_tr + alpha * np.eye(d), Hb_tr.T @ Y_oh)
    scores = Hb_te @ W
    preds = np.argmax(scores, axis=1)
    acc = float(np.mean(preds == y_te))
    return acc, preds


# ── Multi-level calibration ──────────────────────────────────────────

def _save_checkpoint(per_plate_calib, n_levels, token_ids, tag=""):
    """Save incremental checkpoint so no data is lost on crash."""
    ckpt_path = LAB_DIR / f"esn_v4_L{n_levels}_{TIMESTAMP}_checkpoint.json"
    ckpt = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_levels": n_levels,
        "n_modes": N_MODES,
        "total_alphabet": n_levels ** N_MODES,
        "n_reps": N_CALIB_REPS,
        "target_plates": [PLATE_NAMES[p] for p in TARGET_PLATES],
        "checkpoint_tag": tag,
        "per_plate": {},
    }
    for pid, pdata in per_plate_calib.items():
        completed_ids = sorted(pdata["data"].keys())
        ckpt["per_plate"][pid] = {
            "data": {str(k): v for k, v in pdata["data"].items()},
            "modes": pdata["modes"],
            "n_levels": pdata["n_levels"],
            "amp_levels": pdata["amp_levels"],
            "f_rep": pdata["f_rep"],
            "token_ids": token_ids,
            "n_completed": len(completed_ids),
        }
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ckpt_path, 'w') as f:
        json.dump(ckpt, f)
    print(f"      [checkpoint] {ckpt_path.name} ({tag})")
    return ckpt_path


def calibrate_multilevel(handle, mux, all_modes, n_levels, token_ids,
                         n_reps=N_CALIB_REPS):
    """
    Calibrate plates D and E with L-level amplitude encoding.
    token_ids: list of token IDs to calibrate (may be a subset of L^8).
    Saves checkpoints every 128 tokens per plate so no data is lost on crash.
    """
    amp_levels = amplitude_levels(n_levels)
    per_plate_calib = {}
    total_captures = 0
    t0_total = time.time()

    for pid in TARGET_PLATES:
        pname = PLATE_NAMES[pid]
        plate_modes = all_modes.get(pid, [])
        n_modes = len(plate_modes)
        if n_modes < N_MODES:
            print(f"  WARNING: Plate {pname} has {n_modes} modes < {N_MODES}")
            continue

        max_freq = max(plate_modes)
        arb_len = 4096
        fixed_f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))

        print(f"\n  Plate {pname}: {n_modes} modes, {n_levels} levels, "
              f"f_rep={fixed_f_rep:.0f} Hz")
        print(f"    Modes: {[f'{f:.0f}' for f in plate_modes]}")
        print(f"    Amp levels: {[f'{a:.3f}' for a in amp_levels]}")
        print(f"    Tokens to calibrate: {len(token_ids)}")

        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        plate_calib = {}
        t0_plate = time.time()

        # Initialize this plate's entry so checkpoints include it
        per_plate_calib[pid] = {
            "data": plate_calib,
            "modes": plate_modes,
            "n_levels": n_levels,
            "amp_levels": amp_levels,
            "f_rep": fixed_f_rep,
            "token_ids": token_ids,
        }

        for ti, token_id in enumerate(token_ids):
            digits = decode_token_multilevel(token_id, n_levels)
            drive_freqs = plate_modes[:N_MODES]
            drive_amps = [amp_levels[d] for d in digits]

            reps_data = []
            for rep in range(n_reps):
                if any(a > 0 for a in drive_amps):
                    _drive_multitone_arb(handle, drive_freqs, drive_amps,
                                        fixed_f_rep)
                else:
                    _awg_off(handle)
                time.sleep(T_EXCITE_S)

                mag = _capture_spectrum(handle, plate_modes)
                reps_data.append(mag.tolist())
                total_captures += 1

            mean_mag = np.mean(reps_data, axis=0).tolist()
            plate_calib[token_id] = {
                "mean": mean_mag,
                "reps": reps_data,
                "digits": digits,
            }

            if (ti + 1) % 32 == 0 or ti == len(token_ids) - 1:
                elapsed = time.time() - t0_plate
                rate = (ti + 1) * n_reps / elapsed if elapsed > 0 else 0
                remaining = (len(token_ids) - ti - 1) * n_reps / rate \
                    if rate > 0 else 0
                print(f"    [{pname} {ti+1}/{len(token_ids)}] "
                      f"{total_captures} cap, {elapsed:.0f}s, "
                      f"~{remaining:.0f}s left")

            # Checkpoint every 128 tokens
            if (ti + 1) % 128 == 0:
                _save_checkpoint(per_plate_calib, n_levels, token_ids,
                                 tag=f"{pname}_{ti+1}of{len(token_ids)}")

        # Checkpoint after each plate completes
        _save_checkpoint(per_plate_calib, n_levels, token_ids,
                         tag=f"{pname}_done")

    _awg_off(handle)
    elapsed = time.time() - t0_total
    print(f"\n  L={n_levels} calibration done: {total_captures} captures, "
          f"{elapsed:.0f}s ({total_captures/elapsed:.1f} cap/s)")
    return per_plate_calib


# ── Feature extraction ────────────────────────────────────────────────

def build_feature_cache(per_plate_calib, n_levels):
    """
    Build normalized feature vectors for each calibrated token.
    Returns: {pid: {"raw": {token_id: array}, "token_ids": [...]}}
    """
    cache = {}

    for pid in TARGET_PLATES:
        if pid not in per_plate_calib:
            continue
        pname = PLATE_NAMES[pid]
        pdata = per_plate_calib[pid]
        token_ids = pdata["token_ids"]

        # Baseline: token where all digits = 0
        zero_id = 0
        if zero_id in pdata["data"]:
            baseline = np.array(pdata["data"][zero_id]["mean"])
        else:
            # Use minimum across all tokens as baseline
            all_means = [np.array(pdata["data"][t]["mean"]) for t in token_ids]
            baseline = np.min(all_means, axis=0)

        raw_feats = {}
        for t in token_ids:
            spec = np.array(pdata["data"][t]["mean"])
            vals = np.log1p(np.maximum(spec - baseline, 0))
            raw_feats[t] = vals

        # Z-score across calibrated tokens
        arr = np.array([raw_feats[t] for t in token_ids])
        mu = arr.mean(axis=0)
        sigma = arr.std(axis=0) + 1e-8
        raw_norm = {t: (raw_feats[t] - mu) / sigma for t in token_ids}

        cache[pid] = {
            "raw": raw_norm,
            "token_ids": token_ids,
            "n_modes": len(pdata["modes"]),
        }
        print(f"  {pname}: {len(token_ids)} tokens → {len(next(iter(raw_norm.values())))}d raw")

    return cache


# ── Discrimination analysis (no ESN — pure calibration quality) ──────

def discrimination_analysis(per_plate_calib, n_levels):
    """
    Analyze how well tokens are distinguishable at this level count.
    Returns metrics dict.
    """
    from scipy.spatial.distance import pdist

    results = {}

    for pid in TARGET_PLATES:
        if pid not in per_plate_calib:
            continue
        pname = PLATE_NAMES[pid]
        pdata = per_plate_calib[pid]
        token_ids = pdata["token_ids"]

        means = np.array([pdata["data"][t]["mean"] for t in token_ids])
        n_tokens = len(token_ids)

        # Pairwise distances
        if n_tokens > 1:
            dists = pdist(means, 'euclidean')
            min_dist = float(np.min(dists))
            median_dist = float(np.median(dists))
        else:
            min_dist = median_dist = 0.0

        # Rep-to-rep noise (measurement noise floor)
        rep_stds = []
        for t in token_ids:
            reps = np.array(pdata["data"][t]["reps"])
            rep_stds.append(float(reps.std(axis=0).mean()))
        noise_floor = float(np.mean(rep_stds))
        noise_l2 = noise_floor * np.sqrt(len(pdata["modes"]))

        # SNR: min_dist / noise_l2
        snr = min_dist / noise_l2 if noise_l2 > 0 else float('inf')

        # Per-digit discrimination: for each mode position, measure how well
        # the L levels are separated
        digit_sep = []
        for m in range(N_MODES):
            level_means = {}
            for t in token_ids:
                digits = pdata["data"][t]["digits"]
                lv = digits[m]
                if lv not in level_means:
                    level_means[lv] = []
                level_means[lv].append(means[token_ids.index(t), m])

            # Mean per level
            lv_centroids = {lv: np.mean(vals) for lv, vals in level_means.items()}
            lv_stds = {lv: np.std(vals) for lv, vals in level_means.items()
                       if len(vals) > 1}

            # Minimum gap between adjacent levels
            sorted_lvs = sorted(lv_centroids.keys())
            if len(sorted_lvs) >= 2:
                gaps = []
                for i in range(len(sorted_lvs) - 1):
                    gap = abs(lv_centroids[sorted_lvs[i+1]] -
                              lv_centroids[sorted_lvs[i]])
                    # Within-level spread
                    s1 = lv_stds.get(sorted_lvs[i], 0)
                    s2 = lv_stds.get(sorted_lvs[i+1], 0)
                    sep = gap / (s1 + s2 + 1e-10)
                    gaps.append(sep)
                min_gap_sep = float(np.min(gaps))
                mean_gap_sep = float(np.mean(gaps))
            else:
                min_gap_sep = mean_gap_sep = 0.0

            digit_sep.append({
                "mode": m,
                "n_levels_seen": len(sorted_lvs),
                "min_gap_sep": min_gap_sep,
                "mean_gap_sep": mean_gap_sep,
            })

        # Nearest-neighbor classification accuracy (leave-one-out proxy):
        # For each token, check if its nearest neighbor has the same digit
        # pattern. This is a quick discriminability test.
        if n_tokens > 2:
            from scipy.spatial.distance import cdist
            D_matrix = cdist(means, means, 'euclidean')
            np.fill_diagonal(D_matrix, np.inf)
            nn_idx = D_matrix.argmin(axis=1)
            # How many nearest neighbors have different digit patterns?
            n_confused = 0
            for i in range(n_tokens):
                d_i = tuple(pdata["data"][token_ids[i]]["digits"])
                d_nn = tuple(pdata["data"][token_ids[int(nn_idx[i])]]["digits"])
                if d_i == d_nn:
                    n_confused += 1  # same digits = collision (shouldn't happen)
            nn_unique_rate = 1.0 - n_confused / n_tokens
        else:
            nn_unique_rate = 1.0

        results[pid] = {
            "plate": pname,
            "n_levels": n_levels,
            "n_tokens_calibrated": n_tokens,
            "total_alphabet": n_levels ** N_MODES,
            "min_pair_dist": min_dist,
            "median_pair_dist": median_dist,
            "noise_floor_l2": noise_l2,
            "min_snr": snr,
            "nn_unique_rate": nn_unique_rate,
            "digit_separation": digit_sep,
        }

        # Print summary
        worst_mode = min(digit_sep, key=lambda x: x["min_gap_sep"])
        print(f"\n  Plate {pname} @ L={n_levels}:")
        print(f"    Tokens calibrated: {n_tokens} / {n_levels**N_MODES}")
        print(f"    Min pair L2: {min_dist:.0f}, Noise L2: {noise_l2:.0f}, "
              f"SNR: {snr:.1f}×")
        print(f"    NN unique rate: {nn_unique_rate:.1%}")
        print(f"    Worst mode: M{worst_mode['mode']} "
              f"(min_gap_sep={worst_mode['min_gap_sep']:.2f})")
        for ds in digit_sep:
            print(f"      M{ds['mode']}: min_gap_sep={ds['min_gap_sep']:.2f}, "
                  f"mean_gap_sep={ds['mean_gap_sep']:.2f}, "
                  f"levels_seen={ds['n_levels_seen']}")

    return results


# ── ESN sequence reversal at a given level ───────────────────────────

def run_esn_test(plate_cache, n_levels, token_ids, seed=42):
    """
    ESN sequence reversal test for L-level tokens.
    Per-digit readout: for each mode position, predict the L-ary digit.
    """
    rng = np.random.default_rng(seed)

    # Generate sequences using only calibrated tokens
    n_available = len(token_ids)
    seq_indices = rng.integers(0, n_available, size=(N_SEQUENCES, SEQ_LENGTH))
    sequences = np.array([[token_ids[i] for i in row] for row in seq_indices])
    reversed_seqs = sequences[:, ::-1].copy()

    n_train = int(0.75 * N_SEQUENCES)
    n_test = N_SEQUENCES - n_train

    print(f"\n  ESN test @ L={n_levels}: {N_SEQUENCES} sequences "
          f"({n_train} train, {n_test} test), "
          f"{n_available} unique tokens")

    results = {}

    def run_perdigit(feat_map, label):
        """Per-digit readout: predict each L-ary digit at each position."""
        dim = len(next(iter(feat_map.values())))
        all_f = [[feat_map[int(t)] for t in seq] for seq in sequences]
        esn = ESN(input_dim=dim)
        H_tr = esn.collect_states(all_f[:n_train])
        H_te = esn.collect_states(all_f[n_train:])

        digit_accs = np.zeros((SEQ_LENGTH, N_MODES))
        digit_preds_all = np.zeros((n_test, SEQ_LENGTH, N_MODES), dtype=int)

        for pos in range(SEQ_LENGTH):
            target_tokens = reversed_seqs[:, pos]
            for m in range(N_MODES):
                # Extract the L-ary digit at mode position m
                y_tr = np.array([decode_token_multilevel(
                    int(t), n_levels)[m] for t in target_tokens[:n_train]])
                y_te = np.array([decode_token_multilevel(
                    int(t), n_levels)[m] for t in target_tokens[n_train:]])

                if n_levels == 2:
                    # Binary — use ridge_binary
                    acc, preds = ridge_binary(H_tr, H_te, y_tr, y_te)
                else:
                    # L-class — use ridge_multiclass
                    acc, preds = ridge_multiclass(
                        H_tr, H_te, y_tr, y_te, n_classes=n_levels)
                digit_accs[pos, m] = acc
                digit_preds_all[:, pos, m] = preds

        # Reconstruct tokens from predicted digits
        token_accs = []
        for pos in range(SEQ_LENGTH):
            predicted_tokens = np.array([
                encode_token_multilevel(
                    digit_preds_all[i, pos].tolist(), n_levels)
                for i in range(n_test)])
            y_te = reversed_seqs[n_train:, pos]
            token_acc = float(np.mean(predicted_tokens == y_te))
            token_accs.append(token_acc)

        mean_digit = float(np.mean(digit_accs))
        mean_token = float(np.mean(token_accs))

        return {
            'label': label, 'dim': dim, 'n_levels': n_levels,
            'mean_digit_acc': mean_digit,
            'mean_token_acc': mean_token,
            'digit_accs': digit_accs.tolist(),
            'token_accs': token_accs,
            'pos_mean_digit': [float(np.mean(digit_accs[p]))
                               for p in range(SEQ_LENGTH)],
        }

    def print_result(r):
        pd = r['pos_mean_digit']
        ta = r['token_accs']
        print(f"    {r['label']:>20s} {r['dim']:4d}d  "
              f"digit: {pd[0]:5.1%} {pd[1]:5.1%} {pd[2]:5.1%} {pd[3]:5.1%} "
              f"→ {r['mean_digit_acc']:5.1%}  "
              f"tok: {ta[0]:5.1%} {ta[1]:5.1%} {ta[2]:5.1%} {ta[3]:5.1%} "
              f"→ {r['mean_token_acc']:5.1%}")

    # ── Software baseline: raw L-ary digits as ±1 features ──
    sw_feats = {}
    for t in token_ids:
        digits = decode_token_multilevel(t, n_levels)
        # Normalize each digit to [-1, +1] range
        if n_levels > 1:
            sw_feats[t] = np.array(
                [2 * d / (n_levels - 1) - 1 for d in digits],
                dtype=np.float64)
        else:
            sw_feats[t] = np.zeros(N_MODES, dtype=np.float64)

    r = run_perdigit(sw_feats, "sw_raw_digits")
    results['sw_raw_digits'] = r
    print_result(r)

    # ── Plate features: D raw, E raw, DE raw ──
    for pid in TARGET_PLATES:
        if pid not in plate_cache:
            continue
        pname = PLATE_NAMES[pid]
        r = run_perdigit(plate_cache[pid]['raw'], f"{pname}_raw")
        results[f'{pname}_raw'] = r
        print_result(r)

    # ── DE concat raw ──
    if all(pid in plate_cache for pid in TARGET_PLATES):
        de_feats = {}
        for t in token_ids:
            parts = [plate_cache[pid]['raw'][t] for pid in TARGET_PLATES]
            de_feats[t] = np.concatenate(parts)
        r = run_perdigit(de_feats, "DE_raw")
        results['DE_raw'] = r
        print_result(r)

    return results


# ── Offline analysis from v3 calibration data ────────────────────────

def synthesize_multilevel_from_v3(v3_calib, n_levels):
    """
    Synthesize L-level features from existing v3 binary calibration data.
    For L levels per mode, amplitude_levels = [0, 1/(L-1), ..., 1].
    We approximate intermediate levels by interpolating between the
    ON and OFF measurements weighted by the number of active modes.

    This is a ROUGH APPROXIMATION — the actual multi-tone interaction means
    intermediate levels won't be simple interpolations. But it gives a
    lower-bound estimate of discrimination quality.

    Returns None if n_levels > 2 (can't synthesize — need real hardware).
    """
    if n_levels == 2:
        # Binary — v3 data is exact
        return v3_calib
    # Can't synthesize multi-level from binary data
    return None


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use existing v3 calibration (L=2 only)")
    parser.add_argument("--levels", type=str, default=None,
                        help="Comma-separated level counts (default: 2,3,4,6,8,12,16)")
    args = parser.parse_args()

    levels_to_test = DEFAULT_LEVELS
    if args.levels:
        levels_to_test = [int(x.strip()) for x in args.levels.split(",")]

    all_modes = _load_all_modes()
    for pid in TARGET_PLATES:
        pname = PLATE_NAMES[pid]
        modes = all_modes.get(pid, [])
        print(f"  Plate {pname}: {len(modes)} modes at "
              f"{[f'{f:.0f}' for f in modes]}")
        if len(modes) < N_MODES:
            print(f"  ERROR: Plate {pname} needs {N_MODES} modes, "
                  f"has {len(modes)}")
            sys.exit(1)

    all_results = {}

    if args.dry_run:
        # Load v3 calibration for L=2 baseline
        calib_files = sorted(LAB_DIR.glob("esn_v3_8bit_*.json"))
        if not calib_files:
            print("  No v3 calibration found. Run v3 first or run v4 live.")
            sys.exit(1)
        latest = calib_files[-1]
        print(f"\n  Loading v3 calibration: {latest.name}")
        with open(latest) as f:
            saved = json.load(f)

        # Reformat v3 data to v4 structure for L=2
        v3_as_v4 = {}
        for pid_key, pdata in saved["per_plate"].items():
            token_ids = list(range(256))
            calib_data = {}
            for t in token_ids:
                tstr = str(t)
                calib_data[t] = {
                    "mean": pdata["data"][tstr]["mean"],
                    "reps": pdata["data"][tstr]["reps"],
                    "digits": [(t >> b) & 1 for b in range(N_MODES)],
                }
            v3_as_v4[pid_key] = {
                "data": calib_data,
                "modes": pdata["modes"],
                "n_levels": 2,
                "amp_levels": [0.0, 1.0],
                "f_rep": pdata["f_rep"],
                "token_ids": token_ids,
            }

        if 2 in levels_to_test:
            print(f"\n{'═' * 80}")
            print(f"  L=2 (BINARY) — from v3 calibration")
            print(f"{'═' * 80}")

            disc = discrimination_analysis(v3_as_v4, 2)
            cache = build_feature_cache(v3_as_v4, 2)
            esn_r = run_esn_test(cache, 2, list(range(256)))

            all_results[2] = {
                "discrimination": {k: v for k, v in disc.items()},
                "esn": esn_r,
            }

        non_binary = [L for L in levels_to_test if L > 2]
        if non_binary:
            print(f"\n  *** L>2 requires live hardware. "
                  f"Skipping {non_binary} in dry-run mode. ***")
            print(f"  Run without --dry-run to calibrate multi-level tokens.")

    else:
        # Live hardware calibration
        handle = _open_scope()
        mux = RelayMux(args.port)
        mux.open()

        try:
            for n_levels in levels_to_test:
                total_tokens = n_levels ** N_MODES
                if total_tokens <= MAX_CALIB_TOKENS:
                    max_t = total_tokens
                elif n_levels <= 4:
                    max_t = MAX_CALIB_TOKENS
                else:
                    max_t = MAX_CALIB_TOKENS_LARGE

                token_ids = sample_token_set(n_levels, max_t)
                n_calib = len(token_ids)
                est_time = n_calib * N_CALIB_REPS * len(TARGET_PLATES) * \
                    (T_EXCITE_S + 0.1)  # rough estimate

                print(f"\n{'═' * 80}")
                print(f"  L={n_levels}: {total_tokens} total tokens, "
                      f"calibrating {n_calib}, "
                      f"est ~{est_time/60:.0f} min")
                print(f"{'═' * 80}")

                calib = calibrate_multilevel(
                    handle, mux, all_modes, n_levels, token_ids)

                # Save calibration
                save_path = LAB_DIR / \
                    f"esn_v4_L{n_levels}_{TIMESTAMP}.json"
                save_data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "n_levels": n_levels,
                    "n_modes": N_MODES,
                    "total_alphabet": total_tokens,
                    "n_calibrated": n_calib,
                    "n_reps": N_CALIB_REPS,
                    "target_plates": [PLATE_NAMES[p] for p in TARGET_PLATES],
                    "per_plate": {},
                }
                for pid, pdata in calib.items():
                    save_data["per_plate"][pid] = {
                        "data": {
                            str(k): v for k, v in pdata["data"].items()
                        },
                        "modes": pdata["modes"],
                        "n_levels": pdata["n_levels"],
                        "amp_levels": pdata["amp_levels"],
                        "f_rep": pdata["f_rep"],
                        "token_ids": pdata["token_ids"],
                    }
                save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(save_path, 'w') as f:
                    json.dump(save_data, f)
                print(f"  Saved: {save_path}")

                # Analyze
                disc = discrimination_analysis(calib, n_levels)
                cache = build_feature_cache(calib, n_levels)
                esn_r = run_esn_test(cache, n_levels, token_ids)

                all_results[n_levels] = {
                    "discrimination": {
                        k: v for k, v in disc.items()
                    },
                    "esn": esn_r,
                }

                # Check breakpoint: if worst mode separation < 1.0, warn
                for pid in disc:
                    worst = min(disc[pid]["digit_separation"],
                                key=lambda x: x["min_gap_sep"])
                    if worst["min_gap_sep"] < 1.0:
                        print(f"\n  ⚠ BREAKPOINT CANDIDATE: Plate "
                              f"{disc[pid]['plate']} M{worst['mode']} "
                              f"min_gap_sep={worst['min_gap_sep']:.2f} < 1.0")
                    if disc[pid]["min_snr"] < 2.0:
                        print(f"\n  ⚠ SNR WARNING: Plate "
                              f"{disc[pid]['plate']} min_snr="
                              f"{disc[pid]['min_snr']:.1f}")

        finally:
            _close_scope(handle)
            mux.close()

    # ══════════════════════════════════════════════════════════════════
    #  SUMMARY TABLE
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'═' * 100}")
    print("  v4 MULTI-LEVEL SUMMARY")
    print(f"{'═' * 100}")
    print(f"  {'L':>3s} {'Tokens':>10s} {'Calib':>6s} "
          f"{'MinSNR_D':>9s} {'MinSNR_E':>9s} "
          f"{'SW_digit':>9s} {'DE_digit':>9s} "
          f"{'SW_token':>9s} {'DE_token':>9s} "
          f"{'WorstSep':>9s}")
    print("-" * 100)

    for L in sorted(all_results.keys()):
        r = all_results[L]
        disc = r["discrimination"]
        esn = r["esn"]

        snr_d = disc.get("4", {}).get("min_snr", 0)
        snr_e = disc.get("5", {}).get("min_snr", 0)
        n_calib = disc.get("4", disc.get("5", {})).get(
            "n_tokens_calibrated", 0)

        sw_d = esn.get("sw_raw_digits", {}).get("mean_digit_acc", 0)
        sw_t = esn.get("sw_raw_digits", {}).get("mean_token_acc", 0)
        de_d = esn.get("DE_raw", {}).get("mean_digit_acc", 0)
        de_t = esn.get("DE_raw", {}).get("mean_token_acc", 0)

        # Worst separation across both plates
        worst_sep = float('inf')
        for pid in disc:
            for ds in disc[pid].get("digit_separation", []):
                if ds["min_gap_sep"] < worst_sep:
                    worst_sep = ds["min_gap_sep"]
        if worst_sep == float('inf'):
            worst_sep = 0

        total_tok = L ** N_MODES
        tok_str = f"{total_tok:,}" if total_tok < 1_000_000 else \
            f"{total_tok:.1e}"

        print(f"  {L:3d} {tok_str:>10s} {n_calib:6d} "
              f"{snr_d:9.1f} {snr_e:9.1f} "
              f"{sw_d:8.1%} {de_d:8.1%} "
              f"{sw_t:8.1%} {de_t:8.1%} "
              f"{worst_sep:9.2f}")

    # Verdict
    print(f"\n  Interpretation:")
    print(f"    MinSNR = min pairwise token distance / noise floor "
          f"(>2 = clean)")
    print(f"    WorstSep = min adjacent-level separation at worst mode "
          f"(>1 = distinguishable)")
    print(f"    Breakpoint ≈ the L where WorstSep drops below ~1.0 "
          f"or DE_digit < 80%")

    # Save summary
    save_path = LAB_DIR / f"esn_v4_summary_{TIMESTAMP}.json"
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "levels_tested": sorted(all_results.keys()),
        "per_level": {},
    }
    for L in sorted(all_results.keys()):
        r = all_results[L]
        level_summary = {"n_levels": L, "total_alphabet": L ** N_MODES}
        for pid in r["discrimination"]:
            d = r["discrimination"][pid]
            level_summary[f"plate_{d['plate']}_min_snr"] = d["min_snr"]
            level_summary[f"plate_{d['plate']}_nn_unique"] = d["nn_unique_rate"]
        for key in ["sw_raw_digits", "DE_raw", "D_raw", "E_raw"]:
            if key in r["esn"]:
                e = r["esn"][key]
                level_summary[f"esn_{key}_digit"] = e.get("mean_digit_acc", 0)
                level_summary[f"esn_{key}_token"] = e.get("mean_token_acc", 0)
        summary["per_level"][str(L)] = level_summary

    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Summary saved: {save_path}")


if __name__ == "__main__":
    main()
