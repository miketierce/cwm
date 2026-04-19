#!/usr/bin/env python3
"""
Plate Multi-Tone Parity — Hardware Nonlinear Interference

WHY THIS EXISTS:
The cached single-carrier approach (plate_attention_glass.py) scores 50%
on parity because cache features are LINEAR in digit value (rank-7 collapse).
Software pairwise products only give degree-2 approximation.

But the plate PHYSICALLY computes higher-order nonlinear mixing when
multiple carriers are driven simultaneously. The PicoScope AWG can
synthesize multi-tone arbitrary waveforms via ps2000_set_sig_gen_arbitrary.

The hardware Boolean experiment got 100% XOR — but that was software XOR
from sequential single-frequency probes. THIS experiment drives ALL
carriers at once with digit-proportional amplitudes, letting the plate's
PHYSICS compute the multi-carrier interference spectrum.

PROTOCOL:
  1. Load Plate D modes from census (8 modes, 7 carriers)
  2. For each digit sequence [d₀, d₁, ..., d₆]:
     a. Build multi-tone AWG: sum(amp[c] × sin(2π × freq[c] × t))
        where amp[c] = d[c] / 9.0 (0 = silent, 9 = full drive)
     b. Drive ALL 7 carriers simultaneously → physical wave interference
     c. Capture FFT at all 8 readout modes → 8-dim feature vector
     d. The spectrum now contains cross-carrier interference products
        that NO linear combination of single-carrier responses can produce
  3. Ridge regression: 8-dim spectral features → parity output
  4. Compare vs sequential single-carrier features (the cached approach)

KEY PHYSICS:
  When carrier C₁ and C₃ are active simultaneously, the plate's response
  at mode M₅ includes:
    - Linear: a₁·H[5,1] + a₃·H[5,3]
    - Quadratic: a₁·a₃·coupling(C₁,C₃→M₅)
    - Higher order: a₁²·a₃·... etc.

  These higher-order terms are what ridge needs for parity (degree-7 for
  7-digit parity, but even partial nonlinearity beats linear).

TASKS:
  - parity: XOR of all digit values (most demanding of nonlinearity)
  - reverse: positional routing (baseline: should work regardless)

Usage:
  DYLD_LIBRARY_PATH="..." python tools/plate_multitone_parity.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260412_180543.json \\
      --n-samples 500

  # Simulation mode (Lorentzian model with nonlinear mixing):
  python tools/plate_multitone_parity.py --simulate --n-samples 2000
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

N_CARRIERS = 7
N_MODES = 8
N_DIGITS = 10
N_AVG = 8           # captures to average per stimulus
SETTLE_S = 0.15     # AWG settle
SETTLE_RELAY_S = 0.1
AWG_DRIVE_UVPP = 2_000_000
ARB_LEN = 4096
SEED = 42

CARRIER_INDICES = [0, 1, 2, 3, 4, 5, 7]  # Plate D: 7 carriers mapped to modes


# ══════════════════════════════════════════════════════════════════════
# Intermodulation readout frequencies
# ══════════════════════════════════════════════════════════════════════

def compute_intermod_freqs(carrier_freqs, mode_freqs, nyquist=390_500,
                          include_im3=False):
    """Compute intermod frequencies for all carrier pairs/triples.

    IM2: |fi ± fj| for all carrier pairs (2nd-order mixing).
    IM3: 2fi − fj, fi + fj − fk for all pairs/triples (3rd-order mixing).

    These are the physical nonlinear mixing products the plate generates
    when driven with multiple simultaneous tones. Reading them costs ZERO
    extra hardware time — the FFT is already computed, we just read more bins.

    Returns (wideband_freqs, labels) where wideband_freqs includes modes
    first, then IM2 diff/sum, then optionally IM3.
    """
    candidates = []  # (freq, label)
    mode_set = set(mode_freqs)

    # IM2: |fi - fj| and fi + fj
    for i, j in combinations(range(len(carrier_freqs)), 2):
        fi, fj = carrier_freqs[i], carrier_freqs[j]
        diff = abs(fi - fj)
        sumf = fi + fj
        if 1000 < diff < nyquist and diff not in mode_set:
            candidates.append((diff, f"IM2d_{fi//1000:.0f}k-{fj//1000:.0f}k"))
        if sumf < nyquist and sumf not in mode_set:
            candidates.append((sumf, f"IM2s_{fi//1000:.0f}k+{fj//1000:.0f}k"))

    # IM3: 2fi - fj for all ordered pairs
    if include_im3:
        for i in range(len(carrier_freqs)):
            for j in range(len(carrier_freqs)):
                if i == j:
                    continue
                fi, fj = carrier_freqs[i], carrier_freqs[j]
                f3 = abs(2 * fi - fj)
                if 1000 < f3 < nyquist and f3 not in mode_set:
                    candidates.append(
                        (f3, f"IM3a_2x{fi//1000:.0f}k-{fj//1000:.0f}k"))

        # IM3: fi + fj - fk for all triples
        for i, j, k in combinations(range(len(carrier_freqs)), 3):
            fi, fj, fk = carrier_freqs[i], carrier_freqs[j], carrier_freqs[k]
            for f3, lab in [
                (fi + fj - fk, f"IM3b_{fi//1000:.0f}+{fj//1000:.0f}-{fk//1000:.0f}k"),
                (fi + fk - fj, f"IM3b_{fi//1000:.0f}+{fk//1000:.0f}-{fj//1000:.0f}k"),
                (fj + fk - fi, f"IM3b_{fj//1000:.0f}+{fk//1000:.0f}-{fi//1000:.0f}k"),
            ]:
                f3 = abs(f3)
                if 1000 < f3 < nyquist and f3 not in mode_set:
                    candidates.append((f3, lab))

    # Deduplicate
    seen = set(mode_freqs)
    unique_im = []
    unique_labels = [f"mode_{i}" for i in range(len(mode_freqs))]
    for f, lab in candidates:
        if f not in seen:
            unique_im.append(f)
            unique_labels.append(lab)
            seen.add(f)

    wideband = list(mode_freqs) + unique_im
    return wideband, unique_labels


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


def drive_multitone(handle, freqs_hz, amplitudes, fixed_f_rep=None):
    """Drive multiple frequencies simultaneously via ARB waveform.

    Returns (peak_factor, actual_freqs) where actual_freqs are the
    quantized frequencies that actually land on the AWG grid.
    """
    from picosdk.ps2000 import ps2000

    if not freqs_hz or all(a == 0 for a in amplitudes):
        # All zeros → drive silence
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
        time.sleep(SETTLE_S)
        return 1.0, [0.0] * len(freqs_hz)

    if fixed_f_rep is not None:
        f_rep = fixed_f_rep
    else:
        max_freq = max(freqs_hz)
        f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))
    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    buf_signal = np.zeros(ARB_LEN, dtype=np.float64)
    actual_freqs = []
    for f_target, amp in zip(freqs_hz, amplitudes):
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


def capture_spectrum(handle, readout_freqs):
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
# Hardware capture loop
# ══════════════════════════════════════════════════════════════════════

def capture_multitone_features(handle, mux, plate_id, mode_freqs,
                                carrier_indices, sequences, fixed_f_rep=None,
                                wideband=False, include_im3=False):
    """Drive plate with multi-tone composites for each sequence.

    For each input sequence [d₀, ..., d₆]:
      - Build 7-carrier waveform with amplitudes d_c/9
      - Drive ALL carriers simultaneously
      - Capture spectrum at readout frequencies
      - If wideband: read modes + IM2 intermod frequencies (~49 dim)
      - Else: read 8 modes only (original behavior)
    """
    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    carrier_freqs = [mode_freqs[ci] for ci in carrier_indices]
    N = len(sequences)

    # Compute fixed f_rep for consistent frequency grid
    if fixed_f_rep is None:
        max_freq = max(mode_freqs)
        fixed_f_rep = max(10.0, math.ceil(max_freq / (ARB_LEN // 2 - 10)))
    print(f"  f_rep = {fixed_f_rep:.1f} Hz (all tones quantized to this grid)")

    # Determine readout frequencies
    if wideband:
        readout_freqs, readout_labels = compute_intermod_freqs(
            carrier_freqs, mode_freqs, include_im3=include_im3)
        n_im = len(readout_freqs) - len(mode_freqs)
        im_tag = "IM2+IM3" if include_im3 else "IM2"
        print(f"  WIDEBAND readout: {len(readout_freqs)} frequencies "
              f"({len(mode_freqs)} modes + {n_im} {im_tag} products)")
    else:
        readout_freqs = list(mode_freqs)
        readout_labels = [f"mode_{i}" for i in range(len(mode_freqs))]

    n_features = len(readout_freqs)
    X_multi = np.zeros((N, n_features))

    print(f"  Capturing {N} multi-tone stimuli...")
    t0 = time.time()
    for i in range(N):
        seq = sequences[i]
        amps = [float(seq[c]) / 9.0 for c in range(len(carrier_indices))]

        drive_multitone(handle, carrier_freqs, amps, fixed_f_rep=fixed_f_rep)
        X_multi[i] = capture_spectrum(handle, readout_freqs)

        if (i + 1) % 50 == 0 or i == N - 1:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (N - i - 1) / rate if rate > 0 else 0
            print(f"    {i+1}/{N}  ({rate:.1f} seq/s, ETA {eta:.0f}s)")

    awg_off(handle)
    return X_multi, fixed_f_rep, readout_labels


# ══════════════════════════════════════════════════════════════════════
# Simulation (Lorentzian plate model with nonlinear mixing)
# ══════════════════════════════════════════════════════════════════════

def simulate_plate_response(mode_freqs, carrier_indices, sequences,
                             nonlinearity=0.1, rng=None):
    """Simulate multi-tone plate response with Lorentzian modes + nonlinear mixing.

    The simulation includes:
      - Linear: H·a (transfer matrix × amplitude vector)
      - Quadratic: for each mode, sum of pairwise amp products weighted by coupling
      - Noise: measurement noise proportional to signal
    """
    if rng is None:
        rng = np.random.default_rng(SEED)

    n_modes = len(mode_freqs)
    n_carriers = len(carrier_indices)
    N = len(sequences)

    # Build transfer matrix H (Lorentzian)
    H = np.zeros((n_modes, n_carriers))
    for c, ci in enumerate(carrier_indices):
        drive = mode_freqs[ci]
        for m in range(n_modes):
            f0 = mode_freqs[m]
            Q = 300 + rng.uniform(-50, 50)
            gamma = f0 / (2 * Q)
            L = 1.0 / ((drive - f0)**2 + gamma**2)
            H[m, c] = L * gamma**2 * 1e10

    # Build coupling tensor for quadratic terms
    # K[m, c1, c2] = mode m's response to simultaneous c1, c2 drive
    K = np.zeros((n_modes, n_carriers, n_carriers))
    for m in range(n_modes):
        for c1 in range(n_carriers):
            for c2 in range(c1, n_carriers):
                # Coupling strength: geometric mean of linear responses × random sign
                coupling = np.sqrt(H[m, c1] * H[m, c2]) * rng.choice([-1, 1])
                K[m, c1, c2] = coupling * nonlinearity
                K[m, c2, c1] = K[m, c1, c2]

    # Multi-tone features (linear + quadratic + noise)
    X_multi = np.zeros((N, n_modes))
    for i in range(N):
        amps = sequences[i].astype(float) / 9.0
        # Linear term
        linear = H @ amps
        # Quadratic term: sum over carrier pairs
        quad = np.zeros(n_modes)
        for m in range(n_modes):
            quad[m] = amps @ K[m] @ amps
        # Combine + noise
        signal = linear + quad
        noise = rng.normal(0, 0.01 * np.mean(np.abs(signal)), size=n_modes)
        X_multi[i] = signal + noise

    return X_multi


# ══════════════════════════════════════════════════════════════════════
# Ridge regression
# ══════════════════════════════════════════════════════════════════════

def ridge_multiclass(X_train, Y_train, X_test, alpha=1.0):
    """Ridge for multi-position multi-class output."""
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
    """Expand raw spectral features with quadratic cross-mode terms.

    The raw 8-dim multi-tone spectrum contains the plate's nonlinear
    response. We add explicit quadratic mode products to help the
    ridge readout — the plate's physics provides the raw nonlinearity,
    and these products let the linear readout access it.
    """
    N, n_modes = X_raw.shape
    pairs = list(combinations(range(n_modes), 2))
    n_quad = len(pairs)
    X_exp = np.zeros((N, n_modes + n_quad + n_modes))
    X_exp[:, :n_modes] = X_raw
    for idx, (a, b) in enumerate(pairs):
        X_exp[:, n_modes + idx] = X_raw[:, a] * X_raw[:, b]
    # Add squared terms
    X_exp[:, n_modes + n_quad:] = X_raw ** 2
    return X_exp


# ══════════════════════════════════════════════════════════════════════
# Main experiment
# ══════════════════════════════════════════════════════════════════════

def run_experiment(X_multi, sequences, mode="hardware"):
    """Run parity + reverse + identity with multi-tone features."""
    rng = np.random.default_rng(SEED)
    N = len(sequences)
    n_raw = X_multi.shape[1]
    is_wideband = n_raw > N_MODES

    print(f"\n{'═'*72}")
    print(f"  MULTI-TONE PARITY — Physical Nonlinear Interference ({mode})")
    print(f"  N={N} sequences, {n_raw} multi-tone features"
          f"{' (WIDEBAND)' if is_wideband else ''}")
    print(f"  Digit range: 0–{int(sequences.max())}")
    print(f"{'═'*72}")

    # Feature rank analysis
    print(f"\n  Feature rank analysis:")
    print(f"    Multi-tone raw ({n_raw}-dim):  "
          f"rank={np.linalg.matrix_rank(X_multi, tol=1e-8)}")

    # Mode-only subset (first 8 columns)
    X_modes = X_multi[:, :N_MODES]

    # Software quadratic expansion of mode-only features
    X_modes_exp = expand_features(X_modes)
    print(f"    Mode-only expanded ({X_modes_exp.shape[1]}-dim): "
          f"rank={np.linalg.matrix_rank(X_modes_exp, tol=1e-8)}")

    if is_wideband:
        # IM2 features only (columns beyond the first 8)
        X_im2 = X_multi[:, N_MODES:]
        print(f"    IM2 bins only ({X_im2.shape[1]}-dim):  "
              f"rank={np.linalg.matrix_rank(X_im2, tol=1e-8)}")
        print(f"    Full wideband ({n_raw}-dim):  "
              f"rank={np.linalg.matrix_rank(X_multi, tol=1e-8)}")

    # One-hot baseline (for reference)
    n_carriers_actual = sequences.shape[1]
    n_digits_actual = int(sequences.max()) + 1
    X_onehot = np.zeros((N, n_carriers_actual * n_digits_actual))
    for i in range(N):
        for p in range(n_carriers_actual):
            X_onehot[i, p * n_digits_actual + sequences[i, p]] = 1.0

    all_results = {}
    alpha_grid = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]

    for task_name, task_fn in TASKS.items():
        print(f"\n{'━'*72}")
        print(f"  TASK: {task_name.upper()}")
        print(f"{'━'*72}")

        outputs = np.array([task_fn(s) for s in sequences])

        # 80/20 split
        n_train = int(0.8 * N)
        idx = rng.permutation(N)
        train_idx, test_idx = idx[:n_train], idx[n_train:]

        feature_sets = [
            (f"One-hot ({X_onehot.shape[1]}-dim)", X_onehot),
            (f"Modes only ({X_modes.shape[1]}-dim)", X_modes),
            (f"Modes exp ({X_modes_exp.shape[1]}-dim)", X_modes_exp),
        ]
        if is_wideband:
            feature_sets.append(
                (f"Wideband ({X_multi.shape[1]}-dim)", X_multi))
            # Also try wideband + software quadratic of IM2
            X_wb_exp = expand_features(X_multi)
            feature_sets.append(
                (f"Wideband exp ({X_wb_exp.shape[1]}-dim)", X_wb_exp))

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

            # Per-position + sequence accuracy
            n_pos = Y_te.shape[1]
            pos_acc = [np.mean(pred[:, p] == Y_te[:, p]) for p in range(n_pos)]
            seq_acc = np.mean(np.all(pred == Y_te, axis=1))

            pos_str = " ".join([f"{a:4.0%}" for a in pos_acc])
            tag = " ◄" if seq_acc > 0.55 else ""
            print(f"  {feat_name:<32} │ SeqAcc={seq_acc:5.1%} │ "
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
    print(f"  SUMMARY — THE NONLINEARITY TEST")
    print(f"{'═'*72}")
    print(f"\n  Does physical nonlinearity (intermod products) beat software features?")
    print()

    for task_name in TASKS:
        r = all_results[task_name]
        oh_key = [k for k in r if "One-hot" in k][0] if any("One-hot" in k for k in r) else None
        oh_acc = r.get(oh_key, {}).get("sequence_acc", 0) if oh_key else 0

        # Find the best plate feature set
        best_plate_name = None
        best_plate_acc = -1
        for k, v in r.items():
            if "One-hot" not in k:
                acc = v.get("sequence_acc", 0)
                if acc > best_plate_acc:
                    best_plate_acc = acc
                    best_plate_name = k

        delta = best_plate_acc - oh_acc
        verdict = "PLATE WINS" if delta > 0.05 else ("TIED" if abs(delta) < 0.05 else "ONE-HOT WINS")

        # Print all feature sets for this task
        for k, v in r.items():
            acc = v["sequence_acc"]
            tag = " ◄ BEST" if k == best_plate_name and "One-hot" not in k else ""
            print(f"    {task_name:<10} {k:<36} {acc:5.1%}{tag}")
        print(f"    {'':10} Δ(best plate − one-hot) = {delta:+5.1%}  [{verdict}]")
        print()

    # ── Save ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = LAB_DIR / f"multitone_parity_{ts}.json"

    save = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "multitone_parity",
        "mode": mode,
        "n_samples": N,
        "n_carriers": int(sequences.shape[1]),
        "n_modes": X_multi.shape[1],
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
        description="Multi-tone parity — physical nonlinear interference")
    parser.add_argument("--port", default=None, help="Arduino serial port")
    parser.add_argument("--census", default=None, help="Plate census JSON")
    parser.add_argument("--plate", type=int, default=4, help="Plate ID (default: 4=D)")
    parser.add_argument("--n-samples", type=int, default=500,
                        help="Total sequences to capture (default: 500)")
    parser.add_argument("--binary", action="store_true",
                        help="Use binary digits {0,1} only (direct Boolean XOR comparison)")
    parser.add_argument("--wideband", action="store_true",
                        help="Read IM2 intermod frequencies (modes + mixing products)")
    parser.add_argument("--im3", action="store_true",
                        help="Include IM3 (3rd-order) intermod products (requires --wideband)")
    parser.add_argument("--n-carriers", type=int, default=None,
                        help="Use only N carriers (for lower-order parity, e.g. 3 or 5)")
    parser.add_argument("--spread", action="store_true",
                        help="Select maximally-spread carriers (drop clustered modes)")
    parser.add_argument("--simulate", action="store_true",
                        help="Use Lorentzian simulation instead of hardware")
    parser.add_argument("--cache", default=None,
                        help="Carrier cache JSON (for sequential baseline only)")
    args = parser.parse_args()

    rng = np.random.default_rng(SEED)

    # ── Carrier selection logic ──
    all_carrier_indices = list(CARRIER_INDICES)  # default [0,1,2,3,4,5,7]
    mode_freqs_full = [29925, 45025, 49625, 78125, 89375, 90025, 90275, 94675]

    if args.spread:
        # Select maximally-spread carriers by greedy max-min-distance
        freqs_arr = np.array([mode_freqs_full[ci] for ci in all_carrier_indices])
        n_want = args.n_carriers if args.n_carriers else len(all_carrier_indices)
        # Start with the two most separated
        best_pair = max(combinations(range(len(all_carrier_indices)), 2),
                        key=lambda ij: abs(freqs_arr[ij[0]] - freqs_arr[ij[1]]))
        selected = list(best_pair)
        while len(selected) < n_want:
            best_idx, best_dist = -1, -1
            for k in range(len(all_carrier_indices)):
                if k in selected:
                    continue
                min_d = min(abs(freqs_arr[k] - freqs_arr[s]) for s in selected)
                if min_d > best_dist:
                    best_dist = min_d
                    best_idx = k
            if best_idx < 0:
                break
            selected.append(best_idx)
        selected.sort()
        active_carrier_indices = [all_carrier_indices[s] for s in selected]
        spread_freqs = [mode_freqs_full[ci] for ci in active_carrier_indices]
        print(f"  SPREAD MODE: selected {len(active_carrier_indices)} most-separated carriers")
        print(f"  Spread freqs: {[f'{f/1e3:.1f}k' for f in spread_freqs]}")
    elif args.n_carriers and args.n_carriers < len(all_carrier_indices):
        # Take first N carriers
        active_carrier_indices = all_carrier_indices[:args.n_carriers]
    else:
        active_carrier_indices = all_carrier_indices

    n_active = len(active_carrier_indices)
    n_digits = 2 if args.binary else N_DIGITS
    sequences = rng.integers(0, n_digits, size=(args.n_samples, n_active))

    if args.binary:
        print(f"  BINARY MODE: digits {{0,1}} — {n_active}-bit parity")
    if args.n_carriers:
        print(f"  CARRIER SUBSET: {n_active} of {len(all_carrier_indices)} carriers")

    # IM3 requires wideband
    if args.im3 and not args.wideband:
        print("  NOTE: --im3 implies --wideband, enabling wideband")
        args.wideband = True

    if args.simulate:
        # Simulation mode: Lorentzian model with nonlinear mixing
        mode_freqs = mode_freqs_full
        X_multi = simulate_plate_response(
            mode_freqs, active_carrier_indices, sequences, nonlinearity=0.15, rng=rng)
        print(f"  Simulated {args.n_samples} sequences with nonlinearity=0.15")
        run_experiment(X_multi, sequences, mode="simulation")

    elif args.port and args.census:
        # Hardware mode
        from relay_mux import RelayMux

        # Load census
        with open(args.census) as f:
            census = json.load(f)
        if "results" in census:
            census = census["results"]

        plate_id = str(args.plate)
        if plate_id not in census or not census[plate_id].get("peaks"):
            print(f"  ERROR: Plate {plate_id} not in census")
            sys.exit(1)

        peaks = census[plate_id]["peaks"]
        mode_freqs = [p["freq_hz"] for p in peaks[:N_MODES]]
        n_modes = len(mode_freqs)
        carrier_indices = active_carrier_indices[:min(n_active, n_modes)]
        if n_modes < N_MODES:
            carrier_indices = list(range(min(n_active, n_modes)))

        print(f"  Plate {plate_id} ({census[plate_id].get('plate_name', '?')})")
        print(f"  Modes: {[f'{f/1e3:.1f}k' for f in mode_freqs]}")
        print(f"  Carrier indices: {carrier_indices}")
        print(f"  Sequences: {args.n_samples}")

        # Open hardware
        handle = open_scope()
        mux = RelayMux(args.port)
        mux.open()
        time.sleep(0.5)

        try:
            X_multi, f_rep, readout_labels = capture_multitone_features(
                handle, mux, plate_id, mode_freqs, carrier_indices, sequences,
                wideband=args.wideband, include_im3=args.im3)

            # Save raw captures for reanalysis
            cap_path = LAB_DIR / f"multitone_captures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            cap_data = {
                "plate_id": plate_id,
                "mode_freqs_hz": mode_freqs,
                "carrier_indices": carrier_indices,
                "carrier_freqs_hz": [mode_freqs[ci] for ci in carrier_indices],
                "f_rep": f_rep,
                "n_samples": args.n_samples,
                "n_carriers": len(carrier_indices),
                "binary_mode": args.binary,
                "wideband": args.wideband,
                "im3": args.im3,
                "spread": args.spread,
                "readout_labels": readout_labels,
                "sequences": sequences.tolist(),
                "X_multi": X_multi.tolist(),
            }
            with open(cap_path, "w") as f:
                json.dump(cap_data, f)
            print(f"  Raw captures saved: {cap_path.name}")

            run_experiment(X_multi, sequences, mode="hardware")

        finally:
            close_scope(handle)
            mux.close()

    else:
        parser.print_help()
        print("\n  Need --simulate or (--port + --census)")
        sys.exit(1)


if __name__ == "__main__":
    main()
