#!/usr/bin/env python3
"""
Multi-Plate Chained Parity Experiment

Chains plates B, G, D, H together: drives all plates simultaneously with
the same multi-tone AWG waveform, then reads each plate sequentially via
MUX, concatenating spectra into one wide feature vector.

WHY THIS WORKS:
  - AWG broadcasts to ALL plates in parallel (existing wiring)
  - Each plate has a different mass-loading pattern → different transfer
    function → different nonlinear mixing products from the same input
  - The same carrier frequency excites resonances on multiple plates,
    but each responds differently — independent nonlinear processing
  - Concatenated features give the regressor 4× richer representation

PLATE INVENTORY (post-change census 2026-04-17):
  B (relay 2, NE):  7 modes   — unchanged control
  G (relay 3, NE):  8 modes   — pattern H-inv, putty removed
  D (relay 4, NE):  9 modes   — pattern I, putty removed
  H (relay 5, NE):  7 modes   — unchanged
  TOTAL NE:         31 readout dimensions

  With NW receivers (relays 4,6,8):
  G-NW: 8, D-NW: 11, H-NW: 10 → TOTAL NE+NW: 60 dimensions

CARRIER SELECTION:
  Union of all plate modes, deduplicated (±200 Hz), then select up to
  N carriers using greedy max-min-distance spread.

Usage:
  DYLD_LIBRARY_PATH="..." python tools/plate_chain_parity.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260417_200041.json \\
      --n-carriers 10 --n-samples 500 --wideband

  # Simulation mode:
  python tools/plate_chain_parity.py --simulate --n-carriers 10 --n-samples 2000
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
LAB_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────

N_DIGITS = 10
N_AVG = 8
SETTLE_S = 0.15
SETTLE_RELAY_S = 0.10
AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096
SEED = 42

# Plate chain configuration: plates to read (relay channels)
# Each entry: (census_key, relay_channel, label)
CHAIN_PLATES_NE = [
    ("2",    2, "B-NE"),
    ("3_NE", 3, "G-NE"),
    ("4_NE", 5, "D-NE"),   # relay 5 = plate 4 NE
    ("5_NE", 7, "H-NE"),   # relay 7 = plate 5 NE
]

CHAIN_PLATES_NW = [
    ("3_NW", 4, "G-NW"),
    ("4_NW", 6, "D-NW"),
    ("5_NW", 8, "H-NW"),
]


# ══════════════════════════════════════════════════════════════════════
# Carrier selection from union of plate modes
# ══════════════════════════════════════════════════════════════════════

def build_carrier_pool(census_results, plate_keys, dedup_hz=200):
    """Build deduplicated frequency pool from all plate modes."""
    all_freqs = []
    for key in plate_keys:
        if key in census_results and census_results[key].get("peaks"):
            for p in census_results[key]["peaks"]:
                all_freqs.append(p["freq_hz"])

    # Sort and deduplicate within ±dedup_hz
    all_freqs.sort()
    pool = []
    for f in all_freqs:
        if not pool or abs(f - pool[-1]) > dedup_hz:
            pool.append(f)
        else:
            # Keep average of cluster
            pool[-1] = (pool[-1] + f) / 2.0

    return pool


def select_spread_carriers(pool, n_want):
    """Greedy max-min-distance carrier selection."""
    if n_want >= len(pool):
        return list(pool)

    freqs = np.array(pool)
    # Start with two most separated
    best_pair = max(combinations(range(len(freqs)), 2),
                    key=lambda ij: abs(freqs[ij[0]] - freqs[ij[1]]))
    selected = list(best_pair)

    while len(selected) < n_want:
        best_idx, best_dist = -1, -1
        for k in range(len(freqs)):
            if k in selected:
                continue
            min_d = min(abs(freqs[k] - freqs[s]) for s in selected)
            if min_d > best_dist:
                best_dist = min_d
                best_idx = k
        if best_idx < 0:
            break
        selected.append(best_idx)

    selected.sort()
    return [pool[i] for i in selected]


# ══════════════════════════════════════════════════════════════════════
# Intermod frequency computation
# ══════════════════════════════════════════════════════════════════════

def compute_intermod_freqs(carrier_freqs, readout_base_freqs, nyquist=390_500,
                           include_im3=False):
    """Compute IM2 (and optionally IM3) intermod frequencies."""
    candidates = []
    base_set = set(readout_base_freqs)

    for i, j in combinations(range(len(carrier_freqs)), 2):
        fi, fj = carrier_freqs[i], carrier_freqs[j]
        diff = abs(fi - fj)
        sumf = fi + fj
        if 1000 < diff < nyquist and diff not in base_set:
            candidates.append((diff, f"IM2d_{fi/1000:.0f}k-{fj/1000:.0f}k"))
        if sumf < nyquist and sumf not in base_set:
            candidates.append((sumf, f"IM2s_{fi/1000:.0f}k+{fj/1000:.0f}k"))

    if include_im3:
        for i in range(len(carrier_freqs)):
            for j in range(len(carrier_freqs)):
                if i == j:
                    continue
                fi, fj = carrier_freqs[i], carrier_freqs[j]
                f3 = abs(2 * fi - fj)
                if 1000 < f3 < nyquist and f3 not in base_set:
                    candidates.append((f3, f"IM3a_2x{fi/1000:.0f}k-{fj/1000:.0f}k"))

    # Deduplicate
    seen = set(readout_base_freqs)
    unique = []
    labels = [f"mode_{i}" for i in range(len(readout_base_freqs))]
    for f, lab in candidates:
        if f not in seen:
            unique.append(f)
            labels.append(lab)
            seen.add(f)

    return list(readout_base_freqs) + unique, labels


# ══════════════════════════════════════════════════════════════════════
# Tasks
# ══════════════════════════════════════════════════════════════════════

def task_parity(seq):
    p = int(np.sum(seq)) % 2
    return np.full_like(seq, p)

def task_reverse(seq):
    return seq[::-1].copy()

def task_identity(seq):
    return seq.copy()

TASKS = {
    "parity": task_parity,
    "reverse": task_reverse,
    "identity": task_identity,
}


# ══════════════════════════════════════════════════════════════════════
# PicoScope Hardware
# ══════════════════════════════════════════════════════════════════════

def open_scope():
    import cwm_picoscope  # noqa: F401
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    print("  PicoScope opened (Ch A ±1V DC)")
    return handle


def close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("  PicoScope closed")


def drive_multitone(handle, carrier_freqs, amplitudes, fixed_f_rep):
    """Drive multiple frequencies simultaneously via ARB waveform."""
    from picosdk.ps2000 import ps2000

    if not carrier_freqs or all(a == 0 for a in amplitudes):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
        time.sleep(SETTLE_S)
        return 1.0, [0.0] * len(carrier_freqs)

    f_rep = fixed_f_rep
    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    buf_signal = np.zeros(ARB_LEN, dtype=np.float64)
    actual_freqs = []
    for f_target, amp in zip(carrier_freqs, amplitudes):
        k = round(f_target / f_rep)
        if k < 1 or k > ARB_LEN // 2:
            actual_freqs.append(0.0)
            continue
        actual_freqs.append(k * f_rep)
        phase = 2 * np.pi * k * np.arange(ARB_LEN) / ARB_LEN
        buf_signal += amp * np.sin(phase)

    peak_factor = np.max(np.abs(buf_signal))
    if peak_factor > 0:
        buf_signal /= peak_factor
    else:
        peak_factor = 1.0

    arb_u8 = ((buf_signal * 127) + 128).clip(0, 255).astype(np.uint8)
    arb_buf = (ctypes.c_uint8 * ARB_LEN)(*arb_u8.tolist())

    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase,
        0, 0,
        arb_buf, ARB_LEN, 0, 0
    )
    time.sleep(SETTLE_S)
    return peak_factor, actual_freqs


def capture_spectrum_at_freqs(handle, readout_freqs):
    """Average N_AVG FFT captures, return magnitudes at readout freqs."""
    import cwm_picoscope  # noqa: F401
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
        if n > 0:
            raw = np.array(buf_a[:n], dtype=np.float64)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]

            mags = np.zeros(len(readout_freqs))
            for j, rf in enumerate(readout_freqs):
                tb = int(round(rf / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(fft_mag) - 1, tb + 3)
                mags[j] = float(np.max(fft_mag[lo:hi + 1]))
            spectra.append(mags)

    if spectra:
        return np.mean(spectra, axis=0)
    return np.zeros(len(readout_freqs))


def awg_off(handle):
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)


# ══════════════════════════════════════════════════════════════════════
# Chained multi-plate capture
# ══════════════════════════════════════════════════════════════════════

def capture_chain_features(handle, mux, plate_configs, carrier_freqs,
                           sequences, fixed_f_rep, wideband=False,
                           include_im3=False):
    """Drive multi-tone AWG, read each plate sequentially, concatenate.

    For each input sequence:
      1. Build multi-tone waveform from carrier amplitudes
      2. Drive AWG (broadcasts to all plates)
      3. For each plate in chain:
         a. Switch MUX to that plate's relay
         b. Capture spectrum at that plate's readout frequencies
      4. Concatenate all plate spectra into one feature vector

    plate_configs: list of dicts with keys:
      - relay: relay channel number
      - label: plate label
      - mode_freqs: list of mode frequencies for this plate
      - readout_freqs: full readout frequencies (modes + IM if wideband)
      - readout_labels: labels for each readout frequency
    """
    N = len(sequences)
    n_carriers = len(carrier_freqs)

    # Compute total feature dimension
    total_dim = sum(len(pc["readout_freqs"]) for pc in plate_configs)
    X_chain = np.zeros((N, total_dim))

    # Build per-plate column slices
    col_offset = 0
    plate_slices = []
    for pc in plate_configs:
        n = len(pc["readout_freqs"])
        plate_slices.append((col_offset, col_offset + n))
        col_offset += n

    print(f"  Chain: {len(plate_configs)} plates, {total_dim} total features")
    for pc, (c0, c1) in zip(plate_configs, plate_slices):
        print(f"    {pc['label']:6s}: relay {pc['relay']}, "
              f"{len(pc['readout_freqs'])} readout freqs (cols {c0}–{c1-1})")

    print(f"  Capturing {N} sequences × {len(plate_configs)} plates...")
    t0 = time.time()

    for i in range(N):
        seq = sequences[i]
        amps = [float(seq[c]) / 9.0 for c in range(n_carriers)]

        # Drive the multi-tone waveform (same for all plates)
        drive_multitone(handle, carrier_freqs, amps, fixed_f_rep)

        # Read each plate
        for plate_idx, pc in enumerate(plate_configs):
            mux.select(pc["relay"])
            time.sleep(SETTLE_RELAY_S)
            mags = capture_spectrum_at_freqs(handle, pc["readout_freqs"])
            c0, c1 = plate_slices[plate_idx]
            X_chain[i, c0:c1] = mags

        if (i + 1) % 25 == 0 or i == N - 1:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (N - i - 1) / rate if rate > 0 else 0
            print(f"    {i+1}/{N}  ({rate:.2f} seq/s, ETA {eta:.0f}s)")

    awg_off(handle)
    elapsed = time.time() - t0
    print(f"  Capture complete: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    return X_chain


# ══════════════════════════════════════════════════════════════════════
# Simulation
# ══════════════════════════════════════════════════════════════════════

def simulate_chain_response(plate_configs, carrier_freqs, sequences,
                            nonlinearity=0.15, rng=None):
    """Simulate multi-plate chain with independent Lorentzian models."""
    if rng is None:
        rng = np.random.default_rng(SEED)

    N = len(sequences)
    n_carriers = len(carrier_freqs)
    total_dim = sum(len(pc["readout_freqs"]) for pc in plate_configs)
    X_chain = np.zeros((N, total_dim))

    col_offset = 0
    for pc in plate_configs:
        n_readout = len(pc["readout_freqs"])
        readout_freqs = pc["readout_freqs"]

        # Build transfer matrix H for this plate
        H = np.zeros((n_readout, n_carriers))
        for c in range(n_carriers):
            drive = carrier_freqs[c]
            for m in range(n_readout):
                f0 = readout_freqs[m]
                Q = 300 + rng.uniform(-50, 50)
                gamma = f0 / (2 * Q)
                L = 1.0 / ((drive - f0)**2 + gamma**2)
                H[m, c] = L * gamma**2 * 1e10

        # Build quadratic coupling tensor
        K = np.zeros((n_readout, n_carriers, n_carriers))
        for m in range(n_readout):
            for c1 in range(n_carriers):
                for c2 in range(c1, n_carriers):
                    coupling = np.sqrt(abs(H[m, c1] * H[m, c2])) * rng.choice([-1, 1])
                    K[m, c1, c2] = coupling * nonlinearity
                    K[m, c2, c1] = K[m, c1, c2]

        for i in range(N):
            amps = sequences[i].astype(float) / 9.0
            linear = H @ amps
            quad = np.array([amps @ K[m] @ amps for m in range(n_readout)])
            signal = linear + quad
            noise = rng.normal(0, 0.01 * np.mean(np.abs(signal)), size=n_readout)
            X_chain[i, col_offset:col_offset + n_readout] = signal + noise

        col_offset += n_readout

    return X_chain


# ══════════════════════════════════════════════════════════════════════
# Ridge regression (same approach as single-plate)
# ══════════════════════════════════════════════════════════════════════

def ridge_multiclass(X_train, Y_train, X_test, alpha=1.0):
    n_pos = Y_train.shape[1]
    n_feat = X_train.shape[1]

    mu = X_train.mean(axis=0)
    std = X_train.std(axis=0)
    std[std < 1e-12] = 1.0
    Xtr = (X_train - mu) / std
    Xte = (X_test - mu) / std

    XtX_inv_Xt = np.linalg.solve(
        Xtr.T @ Xtr + alpha * np.eye(n_feat), Xtr.T)

    preds = np.zeros((len(X_test), n_pos), dtype=int)
    for pos in range(n_pos):
        Y_oh = np.zeros((len(Y_train), N_DIGITS))
        for i, d in enumerate(Y_train[:, pos]):
            Y_oh[i, d] = 1.0
        W = XtX_inv_Xt @ Y_oh
        scores = Xte @ W
        preds[:, pos] = np.argmax(scores, axis=1)
    return preds


def expand_features(X_raw):
    """Quadratic expansion: original + pairwise products + squares."""
    N, n = X_raw.shape
    pairs = list(combinations(range(n), 2))
    X_exp = np.zeros((N, n + len(pairs) + n))
    X_exp[:, :n] = X_raw
    for idx, (a, b) in enumerate(pairs):
        X_exp[:, n + idx] = X_raw[:, a] * X_raw[:, b]
    X_exp[:, n + len(pairs):] = X_raw ** 2
    return X_exp


# ══════════════════════════════════════════════════════════════════════
# Experiment runner
# ══════════════════════════════════════════════════════════════════════

def run_experiment(X_chain, sequences, plate_configs, carrier_freqs,
                   mode="hardware"):
    """Run parity/reverse/identity on chained multi-plate features."""
    rng = np.random.default_rng(SEED)
    N = len(sequences)
    n_feat = X_chain.shape[1]
    n_carriers = len(carrier_freqs)
    n_plates = len(plate_configs)

    print(f"\n{'═'*72}")
    print(f"  CHAINED MULTI-PLATE PARITY ({mode})")
    print(f"  {n_plates} plates, {n_carriers} carriers, "
          f"{n_feat} features, N={N}")
    print(f"  Digit range: 0–{int(sequences.max())}")
    print(f"{'═'*72}")

    # Feature rank
    rank = np.linalg.matrix_rank(X_chain, tol=1e-8)
    print(f"\n  Feature rank: {rank} / {n_feat}")

    # Also build per-plate feature subsets for comparison
    col_offset = 0
    plate_feature_sets = {}
    for pc in plate_configs:
        n = len(pc["readout_freqs"])
        plate_feature_sets[pc["label"]] = X_chain[:, col_offset:col_offset + n]
        col_offset += n

    # One-hot baseline
    n_digits = int(sequences.max()) + 1
    X_onehot = np.zeros((N, n_carriers * n_digits))
    for i in range(N):
        for p in range(n_carriers):
            X_onehot[i, p * n_digits + sequences[i, p]] = 1.0

    alpha_grid = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]
    all_results = {}

    for task_name, task_fn in TASKS.items():
        print(f"\n{'━'*72}")
        print(f"  TASK: {task_name.upper()}")
        print(f"{'━'*72}")

        outputs = np.array([task_fn(s) for s in sequences])

        n_train = int(0.8 * N)
        idx = rng.permutation(N)
        train_idx, test_idx = idx[:n_train], idx[n_train:]

        # Build feature set list
        feature_sets = [
            (f"One-hot ({X_onehot.shape[1]}d)", X_onehot),
        ]

        # Individual plate features
        for label, X_plate in plate_feature_sets.items():
            feature_sets.append((f"{label} only ({X_plate.shape[1]}d)", X_plate))

        # Full chain
        feature_sets.append((f"Chain raw ({n_feat}d)", X_chain))

        # Chain + quadratic expansion (only if not too large)
        if n_feat <= 80:
            X_chain_exp = expand_features(X_chain)
            feature_sets.append(
                (f"Chain exp ({X_chain_exp.shape[1]}d)", X_chain_exp))

        task_results = {}
        for feat_name, X in feature_sets:
            X_tr = X[train_idx]
            X_te = X[test_idx]
            Y_tr = outputs[train_idx]
            Y_te = outputs[test_idx]

            # Alpha CV
            best_alpha = 1.0
            best_score = -1
            n_cv = min(n_train, 200)
            cv_split = int(0.8 * n_cv)
            for alpha in alpha_grid:
                pred_cv = ridge_multiclass(X_tr[:cv_split], Y_tr[:cv_split],
                                           X_tr[cv_split:n_cv], alpha=alpha)
                score = np.mean(np.all(pred_cv == Y_tr[cv_split:n_cv], axis=1))
                if score > best_score:
                    best_score = score
                    best_alpha = alpha

            pred = ridge_multiclass(X_tr, Y_tr, X_te, alpha=best_alpha)

            n_pos = Y_te.shape[1]
            pos_acc = [np.mean(pred[:, p] == Y_te[:, p]) for p in range(n_pos)]
            seq_acc = np.mean(np.all(pred == Y_te, axis=1))

            pos_str = " ".join([f"{a:4.0%}" for a in pos_acc])
            tag = " ◄" if seq_acc > 0.55 else ""
            print(f"  {feat_name:<36} │ SeqAcc={seq_acc:5.1%} │ "
                  f"MeanPos={np.mean(pos_acc):5.1%} │ {pos_str}{tag}")

            task_results[feat_name] = {
                "sequence_acc": float(seq_acc),
                "mean_position": float(np.mean(pos_acc)),
                "per_position": [float(a) for a in pos_acc],
                "best_alpha": best_alpha,
            }

        all_results[task_name] = task_results

    # ── Summary ──
    print(f"\n{'═'*72}")
    print(f"  SUMMARY — CHAINED MULTI-PLATE RESULTS")
    print(f"{'═'*72}")

    for task_name in TASKS:
        r = all_results[task_name]
        oh_key = [k for k in r if "One-hot" in k][0]
        oh_acc = r[oh_key]["sequence_acc"]

        # Best single plate
        best_single_name, best_single_acc = None, -1
        for k, v in r.items():
            if "only" in k:
                if v["sequence_acc"] > best_single_acc:
                    best_single_acc = v["sequence_acc"]
                    best_single_name = k

        # Best chain
        best_chain_name, best_chain_acc = None, -1
        for k, v in r.items():
            if "Chain" in k:
                if v["sequence_acc"] > best_chain_acc:
                    best_chain_acc = v["sequence_acc"]
                    best_chain_name = k

        print(f"\n  {task_name.upper()}:")
        print(f"    One-hot:           {oh_acc:5.1%}")
        if best_single_name:
            print(f"    Best single plate: {best_single_acc:5.1%} ({best_single_name})")
        print(f"    Best chain:        {best_chain_acc:5.1%} ({best_chain_name})")
        if best_single_name:
            delta = best_chain_acc - best_single_acc
            print(f"    Chain vs single:   {delta:+5.1%}")
        delta_oh = best_chain_acc - oh_acc
        print(f"    Chain vs one-hot:  {delta_oh:+5.1%}")

    # ── Save ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = LAB_DIR / f"chain_parity_{ts}.json"

    save = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "chain_parity",
        "mode": mode,
        "n_samples": N,
        "n_carriers": n_carriers,
        "n_plates": n_plates,
        "n_features": n_feat,
        "carrier_freqs_hz": carrier_freqs,
        "plates": [pc["label"] for pc in plate_configs],
        "tasks": all_results,
    }
    with open(out_path, "w") as f:
        json.dump(save, f, indent=2)
    print(f"\n  Results saved: {out_path.name}")
    print(f"{'═'*72}\n")

    return all_results


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Multi-plate chained parity — physical nonlinear interference")
    parser.add_argument("--port", default=None, help="Arduino serial port")
    parser.add_argument("--census", default=None, help="Plate census JSON")
    parser.add_argument("--n-carriers", type=int, default=10,
                        help="Number of carrier tones (default: 10)")
    parser.add_argument("--n-samples", type=int, default=500,
                        help="Total sequences to capture (default: 500)")
    parser.add_argument("--binary", action="store_true",
                        help="Use binary digits {0,1}")
    parser.add_argument("--wideband", action="store_true",
                        help="Include IM2 intermod readout frequencies")
    parser.add_argument("--im3", action="store_true",
                        help="Include IM3 products (requires --wideband)")
    parser.add_argument("--include-nw", action="store_true",
                        help="Also read NW receivers (3 extra channels)")
    parser.add_argument("--simulate", action="store_true",
                        help="Use Lorentzian simulation instead of hardware")
    args = parser.parse_args()

    rng = np.random.default_rng(SEED)

    if args.im3 and not args.wideband:
        print("  NOTE: --im3 implies --wideband")
        args.wideband = True

    # ── Determine plates in chain ──
    chain_plates = list(CHAIN_PLATES_NE)
    if args.include_nw:
        chain_plates.extend(CHAIN_PLATES_NW)
    plate_keys = [cp[0] for cp in chain_plates]

    if args.simulate:
        # ── Simulation ──
        # Generate synthetic mode frequencies
        sim_modes = {
            "B-NE":  [15100, 17400, 18950, 28825, 29200, 49625, 89350],
            "G-NE":  [18950, 29250, 34550, 34900, 44950, 51525, 68025, 78850],
            "D-NE":  [11425, 18975, 28900, 29300, 33250, 47325, 47800, 48525, 68175],
            "H-NE":  [16000, 18975, 33225, 34575, 51525, 61775, 68050],
        }
        if args.include_nw:
            sim_modes["G-NW"] = [11375, 29250, 34525, 34875, 47225, 51525, 62000, 68050]
            sim_modes["D-NW"] = [11450, 19000, 28900, 29300, 30025, 34925, 37050, 47725, 47850, 48525, 60975]
            sim_modes["H-NW"] = [16000, 29275, 29950, 34550, 47750, 51550, 58525, 61725, 62125, 86875]

        # Build carrier pool
        all_mode_freqs = []
        for v in sim_modes.values():
            all_mode_freqs.extend(v)
        pool = sorted(set(all_mode_freqs))
        # Deduplicate
        deduped = [pool[0]]
        for f in pool[1:]:
            if abs(f - deduped[-1]) > 200:
                deduped.append(f)

        carrier_freqs = select_spread_carriers(deduped, args.n_carriers)

        print(f"\n  SIMULATION MODE")
        print(f"  Plates: {list(sim_modes.keys())}")
        print(f"  Carrier pool: {len(deduped)} unique frequencies")
        print(f"  Selected {len(carrier_freqs)} carriers: "
              f"{[f'{f/1000:.1f}k' for f in carrier_freqs]}")

        # Build plate configs
        plate_configs = []
        for label, modes in sim_modes.items():
            if args.wideband:
                readout_freqs, readout_labels = compute_intermod_freqs(
                    carrier_freqs, modes, include_im3=args.im3)
            else:
                readout_freqs = list(modes)
                readout_labels = [f"mode_{i}" for i in range(len(modes))]
            plate_configs.append({
                "relay": 0,
                "label": label,
                "mode_freqs": modes,
                "readout_freqs": readout_freqs,
                "readout_labels": readout_labels,
            })

        # Generate sequences
        n_digits = 2 if args.binary else N_DIGITS
        sequences = rng.integers(0, n_digits, size=(args.n_samples, len(carrier_freqs)))
        print(f"  Sequences: {args.n_samples} × {len(carrier_freqs)}-digit "
              f"({'binary' if args.binary else 'decimal'})")

        X_chain = simulate_chain_response(
            plate_configs, carrier_freqs, sequences,
            nonlinearity=0.15, rng=rng)
        print(f"  Simulated chain features: {X_chain.shape}")

        run_experiment(X_chain, sequences, plate_configs, carrier_freqs,
                       mode="simulation")

    elif args.port and args.census:
        # ── Hardware ──
        from relay_mux import RelayMux

        with open(args.census) as f:
            census = json.load(f)
        if "results" in census:
            census = census["results"]

        # Build carrier pool from census
        pool = build_carrier_pool(census, plate_keys)
        carrier_freqs = select_spread_carriers(pool, args.n_carriers)

        # Compute f_rep for AWG
        max_freq = max(carrier_freqs)
        fixed_f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))

        print(f"\n  HARDWARE MODE")
        print(f"  Census: {args.census}")
        print(f"  Carrier pool: {len(pool)} unique frequencies")
        print(f"  Selected {len(carrier_freqs)} carriers: "
              f"{[f'{f/1000:.1f}k' for f in carrier_freqs]}")
        print(f"  f_rep = {fixed_f_rep:.1f} Hz")

        # Build plate configs
        plate_configs = []
        for census_key, relay, label in chain_plates:
            if census_key not in census or not census[census_key].get("peaks"):
                print(f"  WARNING: {census_key} not in census, skipping")
                continue
            modes = [p["freq_hz"] for p in census[census_key]["peaks"]]
            if args.wideband:
                readout_freqs, readout_labels = compute_intermod_freqs(
                    carrier_freqs, modes, include_im3=args.im3)
            else:
                readout_freqs = list(modes)
                readout_labels = [f"mode_{i}" for i in range(len(modes))]
            plate_configs.append({
                "relay": relay,
                "label": label,
                "mode_freqs": modes,
                "readout_freqs": readout_freqs,
                "readout_labels": readout_labels,
            })

        if not plate_configs:
            print("  ERROR: No plates available")
            sys.exit(1)

        total_dim = sum(len(pc["readout_freqs"]) for pc in plate_configs)
        print(f"  Chain: {len(plate_configs)} plates, {total_dim} features")

        # Generate sequences
        n_digits = 2 if args.binary else N_DIGITS
        sequences = rng.integers(0, n_digits,
                                 size=(args.n_samples, len(carrier_freqs)))
        print(f"  Sequences: {args.n_samples} × {len(carrier_freqs)}-digit "
              f"({'binary' if args.binary else 'decimal'})")

        # Open hardware
        handle = open_scope()
        mux = RelayMux(args.port)
        mux.open()
        time.sleep(0.5)

        try:
            X_chain = capture_chain_features(
                handle, mux, plate_configs, carrier_freqs, sequences,
                fixed_f_rep, wideband=args.wideband, include_im3=args.im3)

            # Save raw captures
            cap_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            cap_path = LAB_DIR / f"chain_captures_{cap_ts}.json"
            cap_data = {
                "carrier_freqs_hz": carrier_freqs,
                "f_rep": fixed_f_rep,
                "n_samples": args.n_samples,
                "n_carriers": len(carrier_freqs),
                "binary_mode": args.binary,
                "wideband": args.wideband,
                "im3": args.im3,
                "plates": [{
                    "label": pc["label"],
                    "relay": pc["relay"],
                    "mode_freqs_hz": pc["mode_freqs"],
                    "readout_freqs_hz": pc["readout_freqs"],
                    "readout_labels": pc["readout_labels"],
                } for pc in plate_configs],
                "sequences": sequences.tolist(),
                "X_chain": X_chain.tolist(),
            }
            with open(cap_path, "w") as f:
                json.dump(cap_data, f)
            print(f"  Raw captures saved: {cap_path.name}")

            run_experiment(X_chain, sequences, plate_configs, carrier_freqs,
                           mode="hardware")

        finally:
            close_scope(handle)
            mux.close()

    else:
        parser.print_help()
        print("\n  Need --simulate or (--port + --census)")
        sys.exit(1)


if __name__ == "__main__":
    main()
