#!/usr/bin/env python3
"""
Plate Sequence ESN — Sequence Reversal via Glass Plate Reservoir

Parallels Attention-11 (1,216 parameters on a PDP-11/44): instead of
self-attention learning digit reversal, we use 5 fused silica plates
as a nonlinear reservoir with an Echo State Network.

Architecture:
  - At each time step t (1..4), drive a 4-bit token as mode subset
  - All 5 plates respond (via parallel AWG wiring)
  - Read all 5 plates at their resonant modes → feature vector r_t
  - ESN hidden state: h_t = (1-α)h_{t-1} + α·tanh(W_in·r_t + W_rec·h_{t-1})
  - After T=4 steps, decode: y = W_out · h_T
  - Only W_out is trained (ridge regression)

Task: SEQUENCE REVERSAL
  Input:  [t1, t2, t3, t4] (4 random tokens, each 0-15)
  Output: [t4, t3, t2, t1] (reversed sequence)

Controls (same ESN, different features at each step):
  1. plate_poly:   Plate mode magnitudes + polynomial expansion
  2. plate_raw:    Plate mode magnitudes (no polynomial)
  3. sw_poly:      Software polynomial of input bits (no hardware)
  4. sw_random:    Fixed random projection of input bits
  5. raw_bits:     Raw 4-bit input (no nonlinearity)
  6. memoryless:   Only the last step's plate features (no ESN state)

The CHEATING verdict:
  plate_poly ≈ sw_poly      → plate is replaceable (software does same thing)
  plate_poly >> sw_poly      → plate adds unique physics-based features
  plate_poly ≈ memoryless    → ESN state is useless; no sequence processing
  plate_poly >> raw_bits     → nonlinear expansion matters
  all ≈ memoryless           → task doesn't require memory

Usage:
  PYTHONPATH=. python tools/plate_sequence_esn.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_sequence_esn.py --dry-run  # use existing calibration
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

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import cwm_picoscope  # noqa: F401
from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux

# ── Configuration ─────────────────────────────────────────────────────

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}
PLATE_IDS = sorted(PLATE_NAMES.keys())

# Experiment parameters
SEQ_LENGTH = 4          # tokens per sequence
N_INPUT_BITS = 4        # bits per token
N_TOKENS = 2 ** N_INPUT_BITS  # 16
N_SEQUENCES = 300       # total sequences (75% train, 25% test)
N_CALIB_REPS = 8        # repeats per token during calibration
N_AVG = 4               # FFT averages per capture
T_EXCITE_S = 0.30       # mode build-up time
SETTLE_RELAY_S = 0.10   # relay settle time

# ESN parameters
ESN_HIDDEN = 100        # hidden state dimension
ESN_SPECTRAL = 0.9      # spectral radius of recurrent weights
ESN_INPUT_SCALE = 0.3   # input weight scaling
ESN_LEAK = 0.5          # leaky integrator rate
RIDGE_ALPHA = 10.0      # ridge regression regularization


# ── Hardware helpers (adapted from plate_pulsed_memory.py) ────────────

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
    if not freqs_hz:
        _awg_off(handle)
        return
    arb_len = 4096
    delta_phase = int(fixed_f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1
    buf = np.zeros(arb_len, dtype=np.float64)
    for f, a in zip(freqs_hz, amplitudes):
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


def _interaction_expand(x, max_degree=3):
    n = len(x)
    terms = list(x)
    for d in range(2, max_degree + 1):
        for combo in combinations(range(n), d):
            t = 1.0
            for idx in combo:
                t *= x[idx]
            terms.append(t)
    return np.array(terms)


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
    """Echo State Network with fixed random reservoir."""

    def __init__(self, input_dim, hidden_dim=ESN_HIDDEN,
                 spectral_radius=ESN_SPECTRAL, input_scale=ESN_INPUT_SCALE,
                 leak=ESN_LEAK, seed=42):
        rng = np.random.default_rng(seed)
        self.hidden_dim = hidden_dim
        self.leak = leak

        # Fixed random input weights
        self.W_in = rng.standard_normal((hidden_dim, input_dim)) * input_scale

        # Fixed random recurrent weights (scaled to spectral radius)
        W = rng.standard_normal((hidden_dim, hidden_dim))
        eigvals = np.linalg.eigvals(W)
        rho = np.max(np.abs(eigvals))
        if rho > 0:
            self.W_rec = W * (spectral_radius / rho)
        else:
            self.W_rec = W

    def run_sequence(self, feature_seq):
        """Process a sequence of feature vectors, return final hidden state."""
        h = np.zeros(self.hidden_dim)
        for x in feature_seq:
            h = (1 - self.leak) * h + self.leak * np.tanh(
                self.W_in @ x + self.W_rec @ h)
        return h

    def collect_states(self, all_seq_features):
        """Collect final hidden states for multiple sequences."""
        return np.array([self.run_sequence(sf) for sf in all_seq_features])


def ridge_multiclass(H_tr, H_te, y_tr, y_te, n_classes, alpha=RIDGE_ALPHA):
    """Ridge regression for multi-class classification."""
    Hb_tr = np.column_stack([H_tr, np.ones(len(H_tr))])
    Hb_te = np.column_stack([H_te, np.ones(len(H_te))])
    d = Hb_tr.shape[1]
    Y_oh = np.zeros((len(y_tr), n_classes))
    for i, c in enumerate(y_tr):
        Y_oh[i, c] = 1.0
    W = np.linalg.solve(Hb_tr.T @ Hb_tr + alpha * np.eye(d), Hb_tr.T @ Y_oh)
    tr_acc = float(np.mean(np.argmax(Hb_tr @ W, axis=1) == y_tr))
    te_acc = float(np.mean(np.argmax(Hb_te @ W, axis=1) == y_te))
    return tr_acc, te_acc


# ── Feature extraction ────────────────────────────────────────────────

def build_per_plate_diag(all_modes, readout_freqs):
    """Map each plate's modes to readout frequency indices."""
    plate_diag = {}
    for pid in PLATE_IDS:
        pm = all_modes.get(pid, [])
        idxs = []
        for mf in pm:
            dists = [abs(mf - rf) for rf in readout_freqs]
            idxs.append(int(np.argmin(dists)))
        plate_diag[pid] = idxs
    return plate_diag


def extract_plate_features(calib_data, token, plate_diag, rep_idx=None):
    """
    Extract per-plate diagonal features for a given token.
    If rep_idx is None, use mean across reps. Else use specific rep.
    Returns concatenated diagonal features from all 5 plates.
    """
    if rep_idx is not None:
        spectra = calib_data[token]["reps"][rep_idx]  # dict: pid -> mag array
    else:
        spectra = calib_data[token]["mean"]  # dict: pid -> mag array

    features = []
    for pid in PLATE_IDS:
        idxs = plate_diag[pid]
        if pid in spectra:
            spec = np.array(spectra[pid])
            features.extend(spec[idxs].tolist())
        else:
            features.extend([0.0] * len(idxs))
    return np.array(features)


def extract_plate_poly(calib_data, token, plate_diag, all_modes, rep_idx=None):
    """Per-plate polynomial expansion of diagonal features, concatenated."""
    if rep_idx is not None:
        spectra = calib_data[token]["reps"][rep_idx]
    else:
        spectra = calib_data[token]["mean"]

    all_terms = []
    for pid in PLATE_IDS:
        idxs = plate_diag[pid]
        n_modes = len(idxs)
        if pid in spectra and n_modes > 0:
            spec = np.array(spectra[pid])
            diag_vals = np.log1p(spec[idxs])
            mu = np.mean(diag_vals) if len(diag_vals) > 1 else 0
            sigma = np.std(diag_vals) + 1e-8 if len(diag_vals) > 1 else 1
            diag_std = (diag_vals - mu) / sigma
            # Polynomial degree 3 for plates with ≤6 modes, degree 2 for more
            deg = 3 if n_modes <= 6 else 2
            poly = _interaction_expand(diag_std, max_degree=deg)
            all_terms.extend(poly.tolist())
        else:
            all_terms.extend([0.0] * n_modes)
    return np.array(all_terms)


def software_poly(token, n_bits=N_INPUT_BITS):
    """Software polynomial expansion of input bits (no hardware)."""
    bits = np.array([(token >> b) & 1 for b in range(n_bits)], dtype=np.float64)
    # Standardize to [-1, 1]
    bits_std = bits * 2 - 1
    return _interaction_expand(bits_std, max_degree=4)


def software_random_projection(token, proj_matrix, n_bits=N_INPUT_BITS):
    """Fixed random projection of input bits."""
    bits = np.array([(token >> b) & 1 for b in range(n_bits)], dtype=np.float64)
    return np.tanh(proj_matrix @ bits)


def raw_bits_feature(token, n_bits=N_INPUT_BITS):
    """Raw input bits, no expansion."""
    return np.array([(token >> b) & 1 for b in range(n_bits)], dtype=np.float64)


# ── Hardware calibration ──────────────────────────────────────────────

def calibrate(handle, mux, all_modes, readout_freqs, n_reps=N_CALIB_REPS):
    """
    Drive each of 16 tokens, read all 5 plates, n_reps times.
    Returns calibration data: {token_int: {"mean": {pid: array}, "reps": [...]}}
    """
    # Use Plate D's modes (8 modes, best coverage) as drive vocabulary
    drive_pid = max(all_modes.keys(), key=lambda p: len(all_modes[p]))
    drive_modes = all_modes[drive_pid]
    n_drive = len(drive_modes)
    input_indices = np.linspace(0, n_drive - 1, N_INPUT_BITS, dtype=int)

    arb_len = 4096
    max_freq = max(drive_modes)
    fixed_f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))

    print(f"\n  Calibrating: drive {PLATE_NAMES[drive_pid]}'s modes "
          f"({n_drive}), f_rep={fixed_f_rep:.0f} Hz")
    print(f"  {N_TOKENS} tokens × {n_reps} reps × {len(PLATE_IDS)} plates "
          f"= {N_TOKENS * n_reps * len(PLATE_IDS)} captures")

    calib = {}
    total = N_TOKENS * n_reps
    t0 = time.time()

    for token in range(N_TOKENS):
        bits = [(token >> b) & 1 for b in range(N_INPUT_BITS)]
        freqs = [drive_modes[input_indices[b]]
                 for b in range(N_INPUT_BITS) if bits[b]]
        amps = [1.0] * len(freqs)

        reps_data = []
        for rep in range(n_reps):
            # Drive pattern
            if freqs:
                _drive_multitone_arb(handle, freqs, amps, fixed_f_rep)
            else:
                _awg_off(handle)
            time.sleep(T_EXCITE_S)

            # Read all plates
            plate_spectra = {}
            for pid in PLATE_IDS:
                mux.select(int(pid))
                time.sleep(SETTLE_RELAY_S)
                mag = _capture_spectrum(handle, readout_freqs)
                plate_spectra[pid] = mag.tolist()

            reps_data.append(plate_spectra)

            done = token * n_reps + rep + 1
            if done % 16 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (total - done) / rate
                print(f"  [{done}/{total}] {elapsed:.0f}s, ~{eta:.0f}s left")

        # Compute mean across reps
        mean_spectra = {}
        for pid in PLATE_IDS:
            all_reps = np.array([r[pid] for r in reps_data])
            mean_spectra[pid] = all_reps.mean(axis=0).tolist()

        calib[token] = {"mean": mean_spectra, "reps": reps_data}

    _awg_off(handle)
    elapsed = time.time() - t0
    print(f"  Calibration done: {elapsed:.0f}s")

    return calib, drive_pid, input_indices.tolist(), fixed_f_rep


# ── Main experiment ───────────────────────────────────────────────────

def run_experiment(calib_data, all_modes, readout_freqs, seed=42):
    """
    Generate random sequences, run ESN with multiple feature sets,
    compare performance.
    """
    rng = np.random.default_rng(seed)

    # Build plate feature mappings
    plate_diag = build_per_plate_diag(all_modes, readout_freqs)

    # Pre-compute feature dimensions
    sample_plate_raw = extract_plate_features(calib_data, 0, plate_diag)
    sample_plate_poly = extract_plate_poly(calib_data, 0, plate_diag, all_modes)
    sample_sw_poly = software_poly(0)
    n_random_dim = 50
    random_proj = rng.standard_normal((n_random_dim, N_INPUT_BITS)) * 0.5

    dims = {
        "plate_poly": len(sample_plate_poly),
        "plate_raw": len(sample_plate_raw),
        "sw_poly": len(sample_sw_poly),
        "sw_random": n_random_dim,
        "raw_bits": N_INPUT_BITS,
    }

    print(f"\n  Feature dimensions:")
    for name, d in dims.items():
        print(f"    {name}: {d}")

    # Generate random sequences
    sequences = rng.integers(0, N_TOKENS, size=(N_SEQUENCES, SEQ_LENGTH))
    reversed_seqs = sequences[:, ::-1].copy()

    n_train = int(0.75 * N_SEQUENCES)
    train_seqs = sequences[:n_train]
    test_seqs = sequences[n_train:]
    train_rev = reversed_seqs[:n_train]
    test_rev = reversed_seqs[n_train:]

    print(f"\n  Sequences: {N_SEQUENCES} ({n_train} train, "
          f"{N_SEQUENCES - n_train} test)")
    print(f"  Sequence length: {SEQ_LENGTH}, Tokens: 0-{N_TOKENS-1}")
    print(f"  Task: reverse [{SEQ_LENGTH} tokens] → [{SEQ_LENGTH} tokens]")

    # ── Build feature sequences for each feature set ──
    feature_sets = {}

    # 1. Plate poly (mean calibration, deterministic)
    print("\n  Building features...")
    for fs_name in ["plate_poly", "plate_raw", "sw_poly", "sw_random", "raw_bits"]:
        all_feats = []
        for seq in sequences:
            seq_feats = []
            for token in seq:
                if fs_name == "plate_poly":
                    f = extract_plate_poly(calib_data, int(token),
                                           plate_diag, all_modes)
                elif fs_name == "plate_raw":
                    f = extract_plate_features(calib_data, int(token), plate_diag)
                elif fs_name == "sw_poly":
                    f = software_poly(int(token))
                elif fs_name == "sw_random":
                    f = software_random_projection(int(token), random_proj)
                elif fs_name == "raw_bits":
                    f = raw_bits_feature(int(token))
                seq_feats.append(f)
            all_feats.append(seq_feats)
        feature_sets[fs_name] = all_feats
        print(f"    {fs_name}: {len(all_feats[0][0])} dims ✓")

    # 2. Plate poly with noise (use random reps instead of mean)
    all_feats_noisy = []
    for seq in sequences:
        seq_feats = []
        for token in seq:
            rep = rng.integers(0, N_CALIB_REPS)
            f = extract_plate_poly(calib_data, int(token),
                                   plate_diag, all_modes, rep_idx=int(rep))
            seq_feats.append(f)
        all_feats_noisy.append(seq_feats)
    feature_sets["plate_noisy"] = all_feats_noisy
    dims["plate_noisy"] = len(all_feats_noisy[0][0])
    print(f"    plate_noisy: {dims['plate_noisy']} dims ✓")

    # ── Run ESN for each feature set ──
    results = {}

    for fs_name, fs_data in feature_sets.items():
        input_dim = len(fs_data[0][0])
        esn = ESN(input_dim, seed=42)

        # Collect final hidden states
        train_features = fs_data[:n_train]
        test_features = fs_data[n_train:]

        H_train = esn.collect_states(train_features)
        H_test = esn.collect_states(test_features)

        # Decode each position of the reversed sequence independently
        position_accs_train = []
        position_accs_test = []

        for pos in range(SEQ_LENGTH):
            y_tr = train_rev[:, pos]
            y_te = test_rev[:, pos]
            tr_acc, te_acc = ridge_multiclass(
                H_train, H_test, y_tr, y_te, N_TOKENS)
            position_accs_train.append(tr_acc)
            position_accs_test.append(te_acc)

        # Per-position labels (for sequence reversal):
        # pos 0 = "last token" (easiest — most recent input)
        # pos 3 = "first token" (hardest — most distant in sequence)
        pos_labels = ["last(t4)", "t3", "t2", "first(t1)"]

        # Overall sequence accuracy (all 4 positions correct)
        all_correct_train = np.ones(n_train, dtype=bool)
        all_correct_test = np.ones(N_SEQUENCES - n_train, dtype=bool)
        for pos in range(SEQ_LENGTH):
            y_tr = train_rev[:, pos]
            y_te = test_rev[:, pos]
            Hb_tr = np.column_stack([H_train, np.ones(n_train)])
            Hb_te = np.column_stack([H_test, np.ones(len(H_test))])
            d = Hb_tr.shape[1]
            Y_oh = np.zeros((n_train, N_TOKENS))
            for i, c in enumerate(y_tr):
                Y_oh[i, c] = 1.0
            W = np.linalg.solve(Hb_tr.T @ Hb_tr + RIDGE_ALPHA * np.eye(d),
                                Hb_tr.T @ Y_oh)
            pred_tr = np.argmax(Hb_tr @ W, axis=1)
            pred_te = np.argmax(Hb_te @ W, axis=1)
            all_correct_train &= (pred_tr == y_tr)
            all_correct_test &= (pred_te == y_te)

        full_seq_train = float(np.mean(all_correct_train))
        full_seq_test = float(np.mean(all_correct_test))

        results[fs_name] = {
            "position_train": [round(a * 100, 1) for a in position_accs_train],
            "position_test": [round(a * 100, 1) for a in position_accs_test],
            "full_seq_train": round(full_seq_train * 100, 1),
            "full_seq_test": round(full_seq_test * 100, 1),
            "mean_pos_train": round(np.mean(position_accs_train) * 100, 1),
            "mean_pos_test": round(np.mean(position_accs_test) * 100, 1),
            "input_dim": input_dim,
        }

    # ── Memoryless baseline: predict from LAST step's features only ──
    for fs_base in ["plate_poly", "sw_poly"]:
        ml_name = f"memoryless_{fs_base}"
        X_tr = np.array([fs_data[-1] for fs_data
                         in feature_sets[fs_base][:n_train]])
        X_te = np.array([fs_data[-1] for fs_data
                         in feature_sets[fs_base][n_train:]])

        pos_train, pos_test = [], []
        for pos in range(SEQ_LENGTH):
            y_tr = train_rev[:, pos]
            y_te = test_rev[:, pos]
            tr_acc, te_acc = ridge_multiclass(X_tr, X_te, y_tr, y_te, N_TOKENS)
            pos_train.append(tr_acc)
            pos_test.append(te_acc)

        results[ml_name] = {
            "position_train": [round(a * 100, 1) for a in pos_train],
            "position_test": [round(a * 100, 1) for a in pos_test],
            "full_seq_train": 0.0,  # not computed
            "full_seq_test": 0.0,
            "mean_pos_train": round(np.mean(pos_train) * 100, 1),
            "mean_pos_test": round(np.mean(pos_test) * 100, 1),
            "input_dim": len(feature_sets[fs_base][0][0]),
        }

    # ── Oracle ceiling: SOFTWARE has direct access to all 4 tokens ──
    # Concatenate all 4 raw-bit inputs → 16-dim feature
    X_oracle_tr = np.array([
        np.concatenate([raw_bits_feature(int(t)) for t in seq])
        for seq in train_seqs])
    X_oracle_te = np.array([
        np.concatenate([raw_bits_feature(int(t)) for t in seq])
        for seq in test_seqs])
    pos_train, pos_test = [], []
    for pos in range(SEQ_LENGTH):
        y_tr = train_rev[:, pos]
        y_te = test_rev[:, pos]
        tr_acc, te_acc = ridge_multiclass(
            X_oracle_tr, X_oracle_te, y_tr, y_te, N_TOKENS)
        pos_train.append(tr_acc)
        pos_test.append(te_acc)
    results["oracle_all_bits"] = {
        "position_train": [round(a * 100, 1) for a in pos_train],
        "position_test": [round(a * 100, 1) for a in pos_test],
        "full_seq_train": 0.0,
        "full_seq_test": 0.0,
        "mean_pos_train": round(np.mean(pos_train) * 100, 1),
        "mean_pos_test": round(np.mean(pos_test) * 100, 1),
        "input_dim": SEQ_LENGTH * N_INPUT_BITS,
    }

    return results


def print_results(results):
    """Print formatted comparison table."""
    pos_labels = ["last(t4)", "t3", "t2", "first(t1)"]

    print(f"\n{'=' * 90}")
    print(f"  SEQUENCE REVERSAL — ESN vs Controls")
    print(f"  (chance = {100/N_TOKENS:.1f}% per position)")
    print(f"{'=' * 90}")

    # Header
    print(f"\n  {'Feature Set':<22} {'dim':>4}"
          f"  {'last':>6} {'t3':>6} {'t2':>6} {'first':>6}"
          f"  {'mean':>6} {'full':>6}")
    print(f"  {'-' * 82}")

    # Order: plate first, then software, then baselines
    order = ["plate_poly", "plate_noisy", "plate_raw",
             "sw_poly", "sw_random", "raw_bits",
             "memoryless_plate_poly", "memoryless_sw_poly",
             "oracle_all_bits"]

    for name in order:
        if name not in results:
            continue
        r = results[name]
        pos_te = r["position_test"]
        mean_te = r["mean_pos_test"]
        full_te = r["full_seq_test"]
        dim = r["input_dim"]

        # Highlight rows
        if name in ("plate_poly", "sw_poly"):
            marker = " ◀"
        elif name == "oracle_all_bits":
            marker = " ★"
        else:
            marker = ""

        print(f"  {name:<22} {dim:>4}"
              f"  {pos_te[0]:>5.1f}% {pos_te[1]:>5.1f}%"
              f" {pos_te[2]:>5.1f}% {pos_te[3]:>5.1f}%"
              f"  {mean_te:>5.1f}% {full_te:>5.1f}%{marker}")

    # ── Cheating analysis ──
    pp = results.get("plate_poly", {})
    sp = results.get("sw_poly", {})
    ml = results.get("memoryless_plate_poly", {})
    rb = results.get("raw_bits", {})
    oracle = results.get("oracle_all_bits", {})

    print(f"\n{'=' * 90}")
    print(f"  CHEATING ANALYSIS")
    print(f"{'=' * 90}")

    pp_mean = pp.get("mean_pos_test", 0)
    sp_mean = sp.get("mean_pos_test", 0)
    ml_mean = ml.get("mean_pos_test", 0)
    rb_mean = rb.get("mean_pos_test", 0)
    or_mean = oracle.get("mean_pos_test", 0)
    chance = 100.0 / N_TOKENS

    print(f"\n  plate_poly ESN:     {pp_mean:.1f}%")
    print(f"  sw_poly ESN:        {sp_mean:.1f}%")
    print(f"  memoryless:         {ml_mean:.1f}%")
    print(f"  raw_bits ESN:       {rb_mean:.1f}%")
    print(f"  oracle (all bits):  {or_mean:.1f}%")
    print(f"  chance:             {chance:.1f}%")

    delta_plate_sw = pp_mean - sp_mean
    delta_esn_memory = pp_mean - ml_mean
    delta_poly_raw = pp_mean - rb_mean

    print(f"\n  plate vs sw_poly:     {delta_plate_sw:+.1f}%"
          f"  {'PLATE ADDS VALUE' if delta_plate_sw > 5 else 'PLATE ≈ SOFTWARE (replaceable)'}")
    print(f"  ESN vs memoryless:    {delta_esn_memory:+.1f}%"
          f"  {'SEQUENCE PROCESSING' if delta_esn_memory > 10 else 'NO TEMPORAL BENEFIT'}")
    print(f"  poly vs raw bits:     {delta_poly_raw:+.1f}%"
          f"  {'NONLINEARITY HELPS' if delta_poly_raw > 5 else 'NONLINEARITY OPTIONAL'}")

    # First token (hardest — earliest in sequence, most dependent on ESN memory)
    pp_first = pp.get("position_test", [0, 0, 0, 0])[3]
    sp_first = sp.get("position_test", [0, 0, 0, 0])[3]
    ml_first = ml.get("position_test", [0, 0, 0, 0])[3]

    print(f"\n  FIRST TOKEN (max memory demand):")
    print(f"    plate_poly ESN: {pp_first:.1f}%")
    print(f"    sw_poly ESN:    {sp_first:.1f}%")
    print(f"    memoryless:     {ml_first:.1f}%")
    print(f"    chance:         {chance:.1f}%")

    # Verdict
    print(f"\n  ═══ VERDICT ═══")
    if delta_esn_memory < 5:
        print(f"  The ESN state adds no value. This is NOT sequence processing.")
        print(f"  The system is just classifying the last input (memoryless).")
        verdict = "NOT_SEQUENCE_PROCESSING"
    elif abs(delta_plate_sw) < 5:
        print(f"  The ESN performs genuine sequence processing (memory works).")
        print(f"  But the plate is REPLACEABLE — software poly matches it.")
        print(f"  The plate provides polynomial expansion at zero compute cost,")
        print(f"  but doesn't capture unique physics. Judgment: PLATE IS OPTIONAL.")
        verdict = "GENUINE_BUT_REPLACEABLE"
    elif delta_plate_sw > 5:
        print(f"  The ESN performs genuine sequence processing.")
        print(f"  The plate provides features SOFTWARE CANNOT REPLICATE.")
        print(f"  The glass plate adds unique nonlinear computation.")
        print(f"  Judgment: PLATE ADDS GENUINE VALUE.")
        verdict = "PLATE_ADDS_VALUE"
    else:
        print(f"  Inconclusive. Need more data or different task.")
        verdict = "INCONCLUSIVE"

    return verdict


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate Sequence ESN — sequence reversal on glass")
    parser.add_argument("--port", type=str, default="/dev/cu.usbserial-11310")
    parser.add_argument("--n-sequences", type=int, default=N_SEQUENCES)
    parser.add_argument("--n-reps", type=int, default=N_CALIB_REPS)
    parser.add_argument("--dry-run", action="store_true",
                        help="Use existing calibration data if available")
    parser.add_argument("--calib-file", type=str, default=None,
                        help="Path to existing calibration JSON")
    args = parser.parse_args()

    all_modes = _load_all_modes()
    readout_freqs = sorted(set(
        f for freqs in all_modes.values() for f in freqs))
    print(f"  Modes: {sum(len(v) for v in all_modes.values())} across "
          f"{len(all_modes)} plates")
    print(f"  Readout grid: {len(readout_freqs)} frequencies")

    # Try to load existing calibration
    calib_data = None
    calib_path = args.calib_file
    if calib_path and Path(calib_path).exists():
        print(f"\n  Loading calibration: {calib_path}")
        with open(calib_path) as f:
            saved = json.load(f)
        calib_data = {int(k): v for k, v in saved["calibration"].items()}
        print(f"  Loaded {len(calib_data)} tokens")
    elif not args.dry_run or not calib_path:
        # Look for most recent calibration
        calib_files = sorted(LAB_DIR.glob("esn_calibration_*.json"))
        if calib_files and args.dry_run:
            print(f"\n  Loading calibration: {calib_files[-1].name}")
            with open(calib_files[-1]) as f:
                saved = json.load(f)
            calib_data = {int(k): v for k, v in saved["calibration"].items()}
            print(f"  Loaded {len(calib_data)} tokens")

    if calib_data is None:
        # Run hardware calibration
        handle = _open_scope()
        mux = RelayMux(args.port)
        mux.open()
        print(f"  Relay mux connected on {args.port}")
        try:
            calib_data, drive_pid, input_indices, f_rep = calibrate(
                handle, mux, all_modes, readout_freqs, n_reps=args.n_reps)
        finally:
            mux.off()
            _close_scope(handle)

        # Save calibration
        LAB_DIR.mkdir(parents=True, exist_ok=True)
        calib_save = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "drive_plate": PLATE_NAMES[drive_pid],
            "input_indices": input_indices,
            "f_rep": f_rep,
            "n_reps": args.n_reps,
            "readout_freqs_hz": readout_freqs,
            "plate_modes": {PLATE_NAMES[k]: v for k, v in all_modes.items()},
            "calibration": {str(k): v for k, v in calib_data.items()},
        }
        calib_path = LAB_DIR / f"esn_calibration_{TIMESTAMP}.json"
        with open(calib_path, "w") as fp:
            json.dump(calib_save, fp, indent=2, default=str)
        print(f"\n  Saved calibration: {calib_path}")

    # ── Run the experiment ──
    print(f"\n{'═' * 70}")
    print(f"  PLATE SEQUENCE ESN — SEQUENCE REVERSAL")
    print(f"  Parallels Attention-11 (PDP-11/44 transformer)")
    print(f"{'═' * 70}")

    results = run_experiment(calib_data, all_modes, readout_freqs)
    verdict = print_results(results)

    # Save results
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    save_data = {
        "experiment": "plate_sequence_esn",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": "sequence_reversal",
        "seq_length": SEQ_LENGTH,
        "n_tokens": N_TOKENS,
        "n_sequences": N_SEQUENCES,
        "esn_hidden": ESN_HIDDEN,
        "esn_spectral_radius": ESN_SPECTRAL,
        "esn_leak": ESN_LEAK,
        "ridge_alpha": RIDGE_ALPHA,
        "results": results,
        "verdict": verdict,
    }
    save_path = LAB_DIR / f"sequence_esn_{TIMESTAMP}.json"
    with open(save_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Saved: {save_path}")


if __name__ == "__main__":
    main()
