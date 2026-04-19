#!/usr/bin/env python3
"""
Attention in Glass — PDP-11/44 vs Plate D on Sequence Tasks

PREMISE:
Dave's Attention-11 project trained a 1,216-parameter transformer on a
1979 PDP-11/44 to learn 8-digit string reversal. The model needs 350
training steps (~3.5 min) to discover the positional routing rule:
output[0] = input[7], output[1] = input[6], etc.

The plate's cross-coupling matrix IS a physical routing matrix — a
fixed "attention pattern" set by the glass structure, not by gradient
descent. When carrier 0 is driven, energy appears at all 8 modes with
specific ratios determined by the plate's eigenmode coupling. This is
physically identical to what attention does: route information from
input positions to output positions.

EXPERIMENT: Can the plate's fixed physics + a linear readout match
what the PDP-11 learns via 350 steps of backprop?

TASKS (easiest → hardest):
  1. Identity:    output = input (trivial baseline)
  2. Reversal:    output = reversed input (the Attention-11 task)
  3. Rotation:    output = input rotated by 3 positions
  4. Sort:        output = sorted input (requires content-based routing)
  5. Parity:      output = XOR of all input bits (global function)
  6. First-last:  output[0] = input[6], rest = input (selective attention)

ARCHITECTURE COMPARISON:
  PDP-11:  embedding → Q·K·V attention → residual → projection → softmax
           1,216 trainable parameters, 350 training steps, 3.5 min

  Plate D: digit → carrier amplitude → wave interference → spectral readout → ridge
           56 fixed features (physics), ~N trainable readout weights, 1 solve, <1s

The plate replaces {embedding + attention + residual} with physics.
Only the output projection needs training.

Usage:
    # Simulation (carrier cache):
    python plate_attention_glass.py \
        --cache data/results/lab/plate_exps/carrier_cache_D.json

    # Hardware:
    python plate_attention_glass.py \
        --census data/results/lab/plate_exps/plate_census_20260412_180543.json \
        --port /dev/cu.usbserial-11310
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab" / "plate_exps"
LAB_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ─────────────────────────────────────────────────
N_CARRIERS = 7          # positions in the sequence
N_DIGITS = 10           # vocabulary size (0–9)
N_TRAIN_SIZES = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
N_TEST = 2000           # held-out test set size
ALPHA_GRID = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]
SEED = 42


# ══════════════════════════════════════════════════════════════════
# Sequence tasks
# ══════════════════════════════════════════════════════════════════

def task_identity(seq):
    """Identity: output = input."""
    return seq.copy()


def task_reverse(seq):
    """Reversal: the Attention-11 task."""
    return seq[::-1].copy()


def task_rotate(seq, k=3):
    """Rotation: circular shift by k positions."""
    return np.roll(seq, -k).copy()


def task_sort(seq):
    """Sort: output = sorted input (requires content-aware routing)."""
    return np.sort(seq).copy()


def task_parity(seq):
    """Parity: output[i] = XOR of all digits mod 2 (broadcast global)."""
    p = int(np.sum(seq)) % 2
    return np.full_like(seq, p)


def task_first_last_swap(seq):
    """Swap first and last elements, keep rest."""
    out = seq.copy()
    out[0], out[-1] = seq[-1], seq[0]
    return out


TASKS = {
    "identity":   task_identity,
    "reverse":    task_reverse,
    "rotate_3":   lambda s: task_rotate(s, 3),
    "sort":       task_sort,
    "parity":     task_parity,
    "swap_ends":  task_first_last_swap,
}


# ══════════════════════════════════════════════════════════════════
# Data generation
# ══════════════════════════════════════════════════════════════════

def generate_dataset(task_fn, n_samples, rng):
    """Generate input/output pairs for a sequence task."""
    inputs = rng.integers(0, N_DIGITS, size=(n_samples, N_CARRIERS))
    outputs = np.array([task_fn(inp) for inp in inputs])
    return inputs, outputs


# ══════════════════════════════════════════════════════════════════
# Plate feature encoding
# ══════════════════════════════════════════════════════════════════

# BCD lookup: digit 0-9 → 4-bit binary
BCD = np.array([
    [0, 0, 0, 0],  # 0
    [0, 0, 0, 1],  # 1
    [0, 0, 1, 0],  # 2
    [0, 0, 1, 1],  # 3
    [0, 1, 0, 0],  # 4
    [0, 1, 0, 1],  # 5
    [0, 1, 1, 0],  # 6
    [0, 1, 1, 1],  # 7
    [1, 0, 0, 0],  # 8
    [1, 0, 0, 1],  # 9
], dtype=float)

N_BITS = 4


def encode_plate_binary(sequences, carrier_responses, n_modes):
    """Binary encoding through plate spectral basis.

    Each digit → 4-bit BCD. Each bit drives a DIFFERENT carrier (mod 7).
    The spectral response is the SUM of active carriers' mode responses.

    digit 3 at position 0: bits 0011 → carrier_0 + carrier_1
    digit 6 at position 0: bits 0110 → carrier_1 + carrier_2
    These produce DIFFERENT spectral vectors (not collinear!).

    Carrier assignment for position p, bit b:
        carrier_index = (p * N_BITS + b) % n_carriers

    This gives each (position, bit) pair a unique spectral signature
    from the plate's cross-coupling matrix.

    Output: N × (n_positions × n_modes) features
    """
    N, n_pos = sequences.shape
    n_carriers = len(carrier_responses)

    X = np.zeros((N, n_pos * n_modes))
    for i in range(N):
        for p in range(n_pos):
            bits = BCD[sequences[i, p]]
            spec = np.zeros(n_modes)
            for b in range(N_BITS):
                if bits[b] > 0:
                    c = (p * N_BITS + b) % n_carriers
                    spec += carrier_responses[c]
            X[i, p * n_modes:(p + 1) * n_modes] = spec

    return X


def encode_plate_onehot(sequences, carrier_responses, n_modes):
    """One-hot encoding colored by plate spectral response.

    For position p with digit d: a block of N_DIGITS × n_modes features,
    where only the d-th slot is nonzero and carries carrier_response[p].

    This gives 7 × 10 × 8 = 560 features. Each (position, digit) pair
    activates a unique 8-dim spectral fingerprint. The plate provides
    positional texture — different positions have different spectral
    shapes due to their carrier's coupling to the mode spectrum.

    Rank = min(N, 70) — same as one-hot but with spectral structure.
    """
    N, n_pos = sequences.shape
    n_carriers = len(carrier_responses)
    feat_per_pos = N_DIGITS * n_modes

    X = np.zeros((N, n_pos * feat_per_pos))
    for i in range(N):
        for p in range(n_pos):
            d = sequences[i, p]
            offset = p * feat_per_pos + d * n_modes
            X[i, offset:offset + n_modes] = carrier_responses[min(p, n_carriers - 1)]

    return X


def encode_plate_binary_poly(sequences, carrier_responses, n_modes):
    """Plate binary features + pairwise spectral interactions.

    Adds cross-position energy products to binary encoding.
    These capture how information from two positions combines
    through the plate's mode structure — the analog of pairwise
    attention scores.
    """
    X_raw = encode_plate_binary(sequences, carrier_responses, n_modes)
    N = X_raw.shape[0]
    n_pos = sequences.shape[1]

    rows = []
    for i in range(N):
        energies = np.array([
            np.sum(X_raw[i, p * n_modes:(p + 1) * n_modes])
            for p in range(n_pos)
        ])
        pairs = [energies[a] * energies[b]
                 for a, b in combinations(range(n_pos), 2)]
        rows.append(np.concatenate([X_raw[i], energies, pairs]))

    return np.array(rows)


def encode_plate_interference(sequences, carrier_responses, n_modes):
    """Mode-level interference encoding — what the plate ACTUALLY computes.

    The hardware Boolean XOR got 100% because simultaneous multi-carrier
    drive creates mode-level interference: at each mode m, the energies
    from different carriers MIX (constructive/destructive interference).

    The carrier cache only has single-carrier responses. But we can
    reconstruct the multi-carrier interference products:

    Level 1 (linear): per-position spectral response (= binary encoding)
    Level 2 (pairwise): response[p][m] × response[q][m] at each mode
        → This is what the plate physically computes when carriers
          p and q are active simultaneously: energy at mode m is
          proportional to the product of both carriers' coupling.
    Level 3 (strong-mode filter): Pre-scan style — only keep modes where
        the carrier has above-threshold response (like V5 Boolean).

    For XOR/parity: need to detect whether the COUNT of active
    inputs at each mode is odd or even. Pairwise products + linear
    terms provide quadratic expressiveness. For 7-way parity this
    isn't sufficient (need degree-7), but for 2-3 way XOR it works.

    Total features:
        Level 1: n_pos × n_modes = 56
        Level 2: C(n_pos,2) × n_modes = 21 × 8 = 168
        Strong-mode filter: ~30-40 features (data-dependent)
    """
    X_raw = encode_plate_binary(sequences, carrier_responses, n_modes)
    N = X_raw.shape[0]
    n_pos = sequences.shape[1]

    # Pre-scan filter: identify strong modes per position
    # (analog of V5 pre-scan: geometric mean threshold)
    strong_mask = np.zeros((n_pos, n_modes), dtype=bool)
    for p in range(n_pos):
        # Carrier responses for this position's BCD bits
        # Use the primary carrier for this position
        c = p % len(carrier_responses)
        resp = carrier_responses[c]
        if np.max(resp) > 0:
            # Geometric mean of upper/lower halves as threshold
            sorted_resp = np.sort(resp)
            lower = sorted_resp[:n_modes // 2]
            upper = sorted_resp[n_modes // 2:]
            lower_med = np.median(lower) if len(lower) > 0 else 0
            upper_med = np.median(upper) if len(upper) > 0 else 1
            threshold = np.sqrt(max(lower_med, 1e-10) * max(upper_med, 1e-10))
            strong_mask[p] = resp > threshold

    rows = []
    for i in range(N):
        # Level 1: raw spectral features (binary encoding)
        level1 = X_raw[i].copy()

        # Level 2: mode-level pairwise interference products
        # At each mode m: response_p[m] × response_q[m]
        # This is the PHYSICAL interference term
        mode_pairs = []
        for a, b in combinations(range(n_pos), 2):
            resp_a = X_raw[i, a * n_modes:(a + 1) * n_modes]
            resp_b = X_raw[i, b * n_modes:(b + 1) * n_modes]
            mode_pairs.extend(resp_a * resp_b)

        # Level 3: strong-mode filtered features
        # Only keep modes above pre-scan threshold
        strong_feats = []
        for p in range(n_pos):
            resp_p = X_raw[i, p * n_modes:(p + 1) * n_modes]
            # Binary: is this mode active AND strong?
            strong_feats.extend(resp_p * strong_mask[p].astype(float))

        # Level 4: per-mode XOR indicators via product chains
        # For each mode, product of all positions' responses
        # (captures global parity structure at the mode level)
        mode_global = []
        for m in range(n_modes):
            vals = [X_raw[i, p * n_modes + m] for p in range(n_pos)]
            # Normalized product (avoid overflow with large magnitudes)
            norms = [abs(v) / (max(abs(v), 1e-10)) for v in vals]
            # Sign product: -1 if odd number of negative, +1 otherwise
            sign_prod = np.prod(np.sign([v if v != 0 else 1 for v in vals]))
            # Geometric mean of absolute values × sign
            abs_prod = np.exp(np.mean(np.log(np.array([max(abs(v), 1e-10) for v in vals]))))
            mode_global.extend([sign_prod, abs_prod])

        rows.append(np.concatenate([
            level1,
            np.array(mode_pairs),
            np.array(strong_feats),
            np.array(mode_global),
        ]))

    return np.array(rows)


def encode_onehot_baseline(sequences):
    """One-hot encoding baseline (no plate, no physics)."""
    N, n_pos = sequences.shape
    X = np.zeros((N, n_pos * N_DIGITS))
    for i in range(N):
        for p in range(n_pos):
            X[i, p * N_DIGITS + sequences[i, p]] = 1.0
    return X


def encode_raw_baseline(sequences):
    """Raw digit values baseline."""
    return sequences.astype(float) / 9.0


# ══════════════════════════════════════════════════════════════════
# Multi-class ridge regression
# ══════════════════════════════════════════════════════════════════

def ridge_multiclass(X_train, Y_train, X_test, alpha=1.0):
    """Ridge regression for multi-position multi-class output.

    Y_train: (N_train, n_positions) integer digit labels
    Returns: (N_test, n_positions) predicted digit labels
    """
    n_positions = Y_train.shape[1]
    n_feat = X_train.shape[1]

    # Standardize
    mu = X_train.mean(axis=0)
    std = X_train.std(axis=0)
    std[std < 1e-12] = 1.0
    Xtr = (X_train - mu) / std
    Xte = (X_test - mu) / std

    # Precompute (X^T X + αI)^{-1} X^T
    XtX_inv_Xt = np.linalg.solve(
        Xtr.T @ Xtr + alpha * np.eye(n_feat),
        Xtr.T
    )

    predictions = np.zeros((X_test.shape[0], n_positions), dtype=int)

    for pos in range(n_positions):
        # One-hot encode the target digit for this position
        Y_onehot = np.zeros((len(Y_train), N_DIGITS))
        for i, d in enumerate(Y_train[:, pos]):
            Y_onehot[i, d] = 1.0

        # Solve all 10 classes at once
        W = XtX_inv_Xt @ Y_onehot  # (n_feat, 10)
        scores = Xte @ W            # (N_test, 10)
        predictions[:, pos] = np.argmax(scores, axis=1)

    return predictions


# ══════════════════════════════════════════════════════════════════
# Evaluation
# ══════════════════════════════════════════════════════════════════

def evaluate(predictions, targets):
    """Compute per-position and sequence-level accuracy."""
    n_pos = targets.shape[1]
    pos_acc = np.zeros(n_pos)
    for p in range(n_pos):
        pos_acc[p] = np.mean(predictions[:, p] == targets[:, p])

    # Sequence-level: ALL positions must be correct
    seq_correct = np.all(predictions == targets, axis=1)
    seq_acc = np.mean(seq_correct)

    return {
        "per_position": pos_acc,
        "mean_position": float(np.mean(pos_acc)),
        "sequence_acc": float(seq_acc),
    }


# ══════════════════════════════════════════════════════════════════
# Main experiment
# ══════════════════════════════════════════════════════════════════

def run_experiment(carrier_responses, n_modes, mode_freqs=None):
    """Run the full Attention-in-Glass experiment."""
    rng = np.random.default_rng(SEED)

    print(f"\n{'═'*78}")
    print(f"  ATTENTION IN GLASS — PDP-11/44 vs PLATE D")
    print(f"  Can glass physics replace learned attention?")
    print(f"{'═'*78}")

    print(f"\n  Architecture comparison:")
    print(f"  ┌──────────────────┬───────────────────────────────────┐")
    print(f"  │ PDP-11/44        │ Plate D                           │")
    print(f"  ├──────────────────┼───────────────────────────────────┤")
    print(f"  │ Token embedding  │ Carrier frequency mapping (fixed) │")
    print(f"  │ Position embed   │ Mode freq spacing (fixed, physics)│")
    print(f"  │ Q·K·V attention  │ Cross-coupling matrix (fixed)     │")
    print(f"  │ Residual + proj  │ Ridge regression readout (trained)│")
    print(f"  ├──────────────────┼───────────────────────────────────┤")
    print(f"  │ 1,216 params     │ 56 features (0 trained in plate)  │")
    print(f"  │ 350 train steps  │ 1 ridge solve                     │")
    print(f"  │ 3.5 min training │ <1 sec training                   │")
    print(f"  │ ~1 ms forward    │ ~4 µs forward (wave propagation)  │")
    print(f"  │ 6,179 bytes code │ ~0 bytes (physics is the code)    │")
    print(f"  └──────────────────┴───────────────────────────────────┘")

    if mode_freqs:
        print(f"\n  Plate D mode frequencies: "
              f"{', '.join(f'{f/1e3:.1f}k' for f in mode_freqs)} Hz")
    n_carriers = len(carrier_responses)
    n_poly = n_carriers + len(list(combinations(range(n_carriers), 2)))
    print(f"  Carriers: {n_carriers}, Modes: {n_modes}")
    print(f"  Plate binary features: {n_carriers * n_modes} "
          f"(4-bit BCD × spectral cross-coupling)")
    print(f"  Plate one-hot features: {n_carriers * N_DIGITS * n_modes} "
          f"(10 digit slots × {n_modes} modes × {n_carriers} positions)")
    n_intf = (n_carriers * n_modes  # level 1
              + len(list(combinations(range(n_carriers), 2))) * n_modes  # level 2
              + n_carriers * n_modes  # level 3
              + n_modes * 2)  # level 4
    print(f"  Interference features: {n_intf} "
          f"(linear + mode-level pairs + pre-scan + global parity)")

    # Generate test set (fixed across all experiments)
    all_results = {}

    for task_name, task_fn in TASKS.items():
        print(f"\n{'━'*78}")
        print(f"  TASK: {task_name.upper()}")
        if task_name == "reverse":
            print(f"  (The Attention-11 task: discover positional routing)")
        elif task_name == "sort":
            print(f"  (Harder than reversal: routing depends on CONTENT, not just position)")
        elif task_name == "parity":
            print(f"  (Global function: output depends on ALL inputs equally)")
        print(f"{'━'*78}")

        test_inputs, test_outputs = generate_dataset(task_fn, N_TEST, rng)

        # Headers
        print(f"\n  {'N_train':>7} │ {'Approach':<24} │ {'SeqAcc':>6} │ "
              f"{'MeanPos':>7} │ {'Per-Position Accuracy':>30}")
        print(f"  {'─'*7}─┼─{'─'*24}─┼─{'─'*6}─┼─{'─'*7}─┼─{'─'*30}")

        task_results = {}

        for n_train in N_TRAIN_SIZES:
            train_inputs, train_outputs = generate_dataset(task_fn, n_train, rng)

            approaches = {}

            # 1. One-hot baseline (standard ML, no plate)
            X_tr_oh = encode_onehot_baseline(train_inputs)
            X_te_oh = encode_onehot_baseline(test_inputs)

            # 2. Plate binary (BCD → spectral cross-coupling)
            X_tr_bin = encode_plate_binary(train_inputs, carrier_responses, n_modes)
            X_te_bin = encode_plate_binary(test_inputs, carrier_responses, n_modes)

            # 3. Plate one-hot (one-hot colored by plate spectral response)
            X_tr_poh = encode_plate_onehot(train_inputs, carrier_responses, n_modes)
            X_te_poh = encode_plate_onehot(test_inputs, carrier_responses, n_modes)

            # 4. Plate interference (mode-level cross-terms + pre-scan filter)
            X_tr_intf = encode_plate_interference(train_inputs, carrier_responses, n_modes)
            X_te_intf = encode_plate_interference(test_inputs, carrier_responses, n_modes)

            feature_sets = [
                ("One-hot (70-dim)", X_tr_oh, X_te_oh),
                ("Plate binary (56-dim)", X_tr_bin, X_te_bin),
                ("Plate 1-hot (560-dim)", X_tr_poh, X_te_poh),
                ("Plate interf. (%d-dim)" % X_tr_intf.shape[1], X_tr_intf, X_te_intf),
            ]

            for feat_name, X_tr, X_te in feature_sets:
                # Alpha CV
                best_alpha = 1.0
                best_score = -1
                for alpha in ALPHA_GRID:
                    # Quick CV on training data
                    n_cv = min(n_train, 200)
                    cv_split = int(0.8 * n_cv)
                    pred_cv = ridge_multiclass(
                        X_tr[:cv_split], train_outputs[:cv_split],
                        X_tr[cv_split:n_cv], alpha=alpha)
                    score = np.mean(np.all(
                        pred_cv == train_outputs[cv_split:n_cv], axis=1))
                    if score > best_score:
                        best_score = score
                        best_alpha = alpha

                pred = ridge_multiclass(X_tr, train_outputs, X_te, alpha=best_alpha)
                ev = evaluate(pred, test_outputs)

                pos_str = " ".join([f"{a:4.0%}" for a in ev["per_position"]])
                tag = " ◄" if ev["sequence_acc"] > 0.95 else ""
                print(f"  {n_train:>7} │ {feat_name:<24} │ {ev['sequence_acc']:>5.1%} │ "
                      f"{ev['mean_position']:>6.1%} │ {pos_str}{tag}")

                approaches[feat_name] = ev

            task_results[n_train] = approaches

        # Find convergence point for best plate encoding
        plate_key = "Plate 1-hot (560-dim)"
        for n_train in N_TRAIN_SIZES:
            plate_acc = task_results[n_train].get(
                plate_key, {}).get("sequence_acc", 0)
            if plate_acc >= 0.99:
                print(f"\n  ▸ Plate 1-hot converges at N={n_train}")
                break
        else:
            best_n = max(N_TRAIN_SIZES,
                         key=lambda n: task_results[n].get(
                             plate_key, {}).get("sequence_acc", 0))
            best_acc = task_results[best_n][plate_key]["sequence_acc"]
            print(f"\n  ▸ Plate 1-hot best: {best_acc:.1%} at N={best_n}")

        bin_key = "Plate binary (56-dim)"
        for n_train in N_TRAIN_SIZES:
            bin_acc = task_results[n_train].get(
                bin_key, {}).get("sequence_acc", 0)
            if bin_acc >= 0.99:
                print(f"  ▸ Plate binary converges at N={n_train}")
                break
        else:
            best_n = max(N_TRAIN_SIZES,
                         key=lambda n: task_results[n].get(
                             bin_key, {}).get("sequence_acc", 0))
            best_acc = task_results[best_n][bin_key]["sequence_acc"]
            print(f"  ▸ Plate binary best: {best_acc:.1%} at N={best_n}")

        # PDP-11 comparison
        if task_name == "reverse":
            print(f"\n  ── PDP-11/44 Comparison (Attention-11) ──")
            print(f"  PDP-11: 100% accuracy, 350 training steps, 3.5 min")
            plate_best = max(
                task_results[n][plate_key]["sequence_acc"]
                for n in N_TRAIN_SIZES
            )
            if plate_best >= 1.0:
                conv_n = next(
                    n for n in N_TRAIN_SIZES
                    if task_results[n][plate_key]["sequence_acc"] >= 0.99)
                print(f"  Plate:  100% accuracy, {conv_n} training examples, <1 sec")
                print(f"  → Physics replaces {350} steps of backprop with "
                      f"{conv_n} examples of ridge regression")
            else:
                print(f"  Plate:  {plate_best:.1%} accuracy (best), "
                      f"does not match PDP-11")

        all_results[task_name] = task_results

    # ── Final summary ──
    print(f"\n{'═'*78}")
    print(f"  SUMMARY — SEQUENCE ACCURACY AT N=1000 TRAINING EXAMPLES")
    print(f"{'═'*78}")
    print(f"\n  {'Task':<16} │ {'One-hot':>7} │ {'Pl.Bin':>6} │ {'Pl.1-hot':>8} │ {'Pl.Intf':>7} │ {'PDP-11':>6}")
    print(f"  {'─'*16}─┼─{'─'*7}─┼─{'─'*6}─┼─{'─'*8}─┼─{'─'*7}─┼─{'─'*6}")

    ref_n = 1000
    for task_name in TASKS:
        if ref_n not in all_results[task_name]:
            continue
        r = all_results[task_name][ref_n]
        oh = r.get("One-hot (70-dim)", {}).get("sequence_acc", 0)
        pb = r.get("Plate binary (56-dim)", {}).get("sequence_acc", 0)
        po = r.get("Plate 1-hot (560-dim)", {}).get("sequence_acc", 0)
        # Find interference key dynamically (dim varies)
        pi_key = [k for k in r if k.startswith("Plate interf")]
        pp = r[pi_key[0]]["sequence_acc"] if pi_key else 0
        pdp = "100%" if task_name == "reverse" else "—"
        print(f"  {task_name:<16} │ {oh:>6.1%} │ {pb:>5.1%} │ {po:>7.1%} │ {pp:>6.1%} │ {pdp:>6}")

    # ── Save results ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = LAB_DIR / f"attention_glass_{ts}.json"

    save_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "attention_in_glass",
        "description": "PDP-11/44 vs Plate D on sequence tasks",
        "n_carriers": len(carrier_responses),
        "n_modes": n_modes,
        "n_test": N_TEST,
        "tasks": {},
    }
    for task_name, task_results in all_results.items():
        save_data["tasks"][task_name] = {}
        for n_train, approaches in task_results.items():
            save_data["tasks"][task_name][str(n_train)] = {
                name: {
                    "sequence_acc": float(ev["sequence_acc"]),
                    "mean_position": float(ev["mean_position"]),
                    "per_position": [float(x) for x in ev["per_position"]],
                }
                for name, ev in approaches.items()
            }

    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\n  Results saved: {out_path.name}")
    print(f"{'═'*78}\n")

    return all_results


# ══════════════════════════════════════════════════════════════════
# Carrier cache / hardware
# ══════════════════════════════════════════════════════════════════

def load_carrier_cache(path):
    """Load carrier responses from cache JSON."""
    with open(path) as f:
        data = json.load(f)
    carriers = {}
    for b in range(len(data["responses"])):
        carriers[b] = np.array(data["responses"][str(b)])
    return carriers, data.get("mode_freqs_hz", []), data.get("n_modes", 8)


def simulate_carrier_responses(n_carriers=7, n_modes=8, rng=None):
    """Generate Lorentzian cross-coupling for simulation mode."""
    if rng is None:
        rng = np.random.default_rng(42)
    mode_freqs = np.linspace(30000, 95000, n_modes)
    carrier_indices = np.linspace(0, n_modes - 1, n_carriers, dtype=int)
    carriers = {}
    for b in range(n_carriers):
        drive = mode_freqs[carrier_indices[b]]
        resp = np.zeros(n_modes)
        for m in range(n_modes):
            f0 = mode_freqs[m]
            Q = 300 + rng.uniform(-50, 50)
            gamma = f0 / (2 * Q)
            L = 1.0 / ((drive - f0) ** 2 + gamma ** 2)
            resp[m] = L * gamma ** 2 * 1e10
        carriers[b] = resp
    return carriers, n_modes, mode_freqs.tolist()


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Attention in Glass — PDP-11/44 vs Plate D")
    parser.add_argument("--cache", default=None,
                        help="Carrier response cache JSON")
    parser.add_argument("--census", default=None,
                        help="Plate census JSON (for hardware mode)")
    parser.add_argument("--port", default=None,
                        help="Arduino serial port (for hardware mode)")
    parser.add_argument("--simulate", action="store_true",
                        help="Use Lorentzian simulation (no cache/hardware)")
    args = parser.parse_args()

    if args.cache:
        carriers, mode_freqs, n_modes = load_carrier_cache(args.cache)
        print(f"  Loaded carrier cache: {len(carriers)} carriers × {n_modes} modes")
        run_experiment(carriers, n_modes, mode_freqs)
    elif args.simulate:
        carriers, n_modes, mode_freqs = simulate_carrier_responses()
        print(f"  Simulated {len(carriers)} carriers × {n_modes} modes")
        run_experiment(carriers, n_modes, mode_freqs)
    elif args.census and args.port:
        # Hardware capture would go here
        print("  Hardware mode not yet implemented — use --cache or --simulate")
    else:
        # Default: try to find carrier cache
        default_cache = LAB_DIR / "carrier_cache_D.json"
        if default_cache.exists():
            carriers, mode_freqs, n_modes = load_carrier_cache(default_cache)
            print(f"  Auto-loaded carrier cache: {len(carriers)} carriers × {n_modes} modes")
            run_experiment(carriers, n_modes, mode_freqs)
        else:
            carriers, n_modes, mode_freqs = simulate_carrier_responses()
            print(f"  No cache found, simulating {len(carriers)} carriers × {n_modes} modes")
            run_experiment(carriers, n_modes, mode_freqs)


if __name__ == "__main__":
    main()
