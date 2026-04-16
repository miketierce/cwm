#!/usr/bin/env python3
"""
Plate Sequence ESN v3 — 8-bit Tokens on Plates G, D, F (dual-RX)

Key hypothesis: For 4-bit tokens, degree-4 polynomial is COMPLETE (16 basis
functions = 16 tokens) so software wins by definition. For 8-bit tokens,
degree-4 polynomial is INCOMPLETE (163 features for 256 tokens). The plate's
resonance physics might capture nonlinear structure that polynomial misses.

Plates 3 (G), 4 (D), 5 (F) — each has 8 modes, dual-RX (NE + NW) per plate.
  - Per-bit readout (primary): 8 binary classifiers per position
  - 256-class readout (secondary): full token prediction
  - Software baselines: degree-4 (163d, incomplete), degree-8 (256d, complete)

Usage:
  PYTHONPATH=. python tools/plate_sequence_esn_v3.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_sequence_esn_v3.py --dry-run
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

import cwm_picoscope
from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux

# ── Configuration ─────────────────────────────────────────────────────

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

PLATE_NAMES = {"1": "A", "2": "B", "3": "G", "4": "D", "5": "F"}

# Dual-RX plates: map plate ID → list of (relay_ch, rx_label)
# Plates 3, 4, 5 have NE-RX (diagonal path) + NW-RX (L-path)
PLATE_RELAYS = {
    "1": [(1, "NE")],
    "2": [(2, "NE")],
    "3": [(3, "NE"), (4, "NW")],
    "4": [(5, "NE"), (6, "NW")],
    "5": [(7, "NE"), (8, "NW")],
}

# Target plates for 8-bit calibration (dual-RX plates with new patterns)
TARGET_PLATES = ["3", "4", "5"]

# Experiment parameters
SEQ_LENGTH = 4
N_INPUT_BITS = 8
N_TOKENS = 256
N_SEQUENCES = 2000
N_CALIB_REPS = 8
N_AVG = 4
T_EXCITE_S = 0.30
SETTLE_RELAY_S = 0.10

# ESN parameters (tuned from v2 sweep)
ESN_HIDDEN = 200
ESN_SPECTRAL = 0.9
ESN_INPUT_SCALE = 0.1
ESN_LEAK = 0.9
RIDGE_ALPHA = 10.0


# ── Hardware helpers ──────────────────────────────────────────────────

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


# ── Interaction expansion ─────────────────────────────────────────────

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


def ridge_multiclass(H_tr, H_te, y_tr, y_te, n_classes, alpha=RIDGE_ALPHA):
    Hb_tr = np.column_stack([H_tr, np.ones(len(H_tr))])
    Hb_te = np.column_stack([H_te, np.ones(len(H_te))])
    d = Hb_tr.shape[1]
    Y_oh = np.zeros((len(y_tr), n_classes))
    for i, c in enumerate(y_tr):
        Y_oh[i, c] = 1.0
    W = np.linalg.solve(Hb_tr.T @ Hb_tr + alpha * np.eye(d), Hb_tr.T @ Y_oh)
    scores = Hb_te @ W
    te_acc = float(np.mean(np.argmax(scores, axis=1) == y_te))
    return te_acc, scores


def ridge_binary(H_tr, H_te, y_tr, y_te, alpha=RIDGE_ALPHA):
    """Binary ridge regression for per-bit prediction."""
    Hb_tr = np.column_stack([H_tr, np.ones(len(H_tr))])
    Hb_te = np.column_stack([H_te, np.ones(len(H_te))])
    d = Hb_tr.shape[1]
    w = np.linalg.solve(Hb_tr.T @ Hb_tr + alpha * np.eye(d),
                        Hb_tr.T @ y_tr.astype(np.float64))
    preds = (Hb_te @ w > 0.5).astype(int)
    acc = float(np.mean(preds == y_te))
    return acc, preds


def software_poly(token, n_bits=N_INPUT_BITS, degree=4):
    bits = np.array([(token >> b) & 1 for b in range(n_bits)], dtype=np.float64)
    return _interaction_expand(bits * 2 - 1, max_degree=degree)


# ── Per-plate calibration (8-bit) ────────────────────────────────────

def calibrate_8bit(handle, mux, all_modes, n_reps=N_CALIB_REPS):
    """
    Calibrate target plates with 8-bit tokens, dual-RX paths.
    Each plate has 8 modes → 8 carriers → 256 unique drive patterns.
    For dual-RX plates, captures from both NE and NW receivers per token.
    """
    per_plate_calib = {}
    total_captures = 0
    t0_total = time.time()

    for pid in TARGET_PLATES:
        pname = PLATE_NAMES[pid]
        plate_modes = all_modes.get(pid, [])
        n_modes = len(plate_modes)
        if n_modes < N_INPUT_BITS:
            print(f"  WARNING: Plate {pname} has {n_modes} modes < {N_INPUT_BITS}")
            continue

        relays = PLATE_RELAYS[pid]
        n_carriers = N_INPUT_BITS

        # ARB setup
        max_freq = max(plate_modes)
        arb_len = 4096
        fixed_f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))

        print(f"\n  Plate {pname}: {n_modes} modes, "
              f"{n_carriers} carriers, f_rep={fixed_f_rep:.0f} Hz")
        print(f"    Modes: {[f'{f:.0f}' for f in plate_modes]}")
        print(f"    RX paths: {[(ch, rx) for ch, rx in relays]}")

        plate_calib = {}
        t0_plate = time.time()

        for token in range(N_TOKENS):
            bits = [(token >> b) & 1 for b in range(N_INPUT_BITS)]

            # Build drive: turn ON carrier modes according to bits
            drive_freqs = []
            for b_idx in range(n_carriers):
                if bits[b_idx]:
                    drive_freqs.append(plate_modes[b_idx])
            amps = [1.0] * len(drive_freqs)

            # Collect reps across all RX paths
            per_rx_reps = {rx_label: [] for _, rx_label in relays}

            for rep in range(n_reps):
                # Drive the multitone (TX is shared across all plates)
                if drive_freqs:
                    _drive_multitone_arb(handle, drive_freqs, amps, fixed_f_rep)
                else:
                    _awg_off(handle)
                time.sleep(T_EXCITE_S)

                # Capture from each RX relay channel
                for relay_ch, rx_label in relays:
                    mux.select(relay_ch)
                    time.sleep(0.02)  # brief settle for relay switch
                    mag = _capture_spectrum(handle, plate_modes)
                    per_rx_reps[rx_label].append(mag.tolist())
                    total_captures += 1

            # Store per-RX means and raw reps
            token_data = {}
            combined_mean = []
            for _, rx_label in relays:
                reps = per_rx_reps[rx_label]
                mean_mag = np.mean(reps, axis=0).tolist()
                token_data[rx_label] = {"mean": mean_mag, "reps": reps}
                combined_mean.extend(mean_mag)

            # "mean" = concatenated NE+NW features for backward compat
            token_data["mean"] = combined_mean
            plate_calib[token] = token_data

            # Progress every 32 tokens
            if (token + 1) % 32 == 0 or token == N_TOKENS - 1:
                elapsed = time.time() - t0_plate
                n_done = (token + 1) * n_reps * len(relays)
                rate = n_done / elapsed if elapsed > 0 else 0
                remaining_caps = (N_TOKENS - token - 1) * n_reps * len(relays)
                remaining = remaining_caps / rate if rate > 0 else 0
                print(f"    [{pname} {token+1}/{N_TOKENS}] "
                      f"{total_captures} captures, {elapsed:.0f}s, "
                      f"~{remaining:.0f}s remaining")

        per_plate_calib[pid] = {
            "data": plate_calib,
            "modes": plate_modes,
            "n_carriers": n_carriers,
            "n_rx_paths": len(relays),
            "rx_labels": [rx for _, rx in relays],
            "f_rep": fixed_f_rep,
        }

    _awg_off(handle)
    elapsed = time.time() - t0_total
    print(f"\n  8-bit calibration done: {total_captures} captures, "
          f"{elapsed:.0f}s ({total_captures/elapsed:.1f} cap/s)")
    return per_plate_calib


# ── Feature extraction ────────────────────────────────────────────────

def build_token_cache(per_plate_calib):
    """
    Build normalized feature caches for all 256 tokens per plate.
    Returns: {pid: {"raw": [256 arrays], "poly": [256 arrays]}}
    """
    cache = {}

    for pid in TARGET_PLATES:
        if pid not in per_plate_calib:
            continue
        pname = PLATE_NAMES[pid]
        pdata = per_plate_calib[pid]
        n_modes = len(pdata["modes"])
        n_rx = pdata.get("n_rx_paths", 1)

        # Extract raw features: log-amplitude relative to baseline (token 0)
        # "mean" key contains concatenated NE+NW features if dual-RX
        baseline = np.array(pdata["data"][0]["mean"])
        raw_feats = []
        for t in range(N_TOKENS):
            spec = np.array(pdata["data"][t]["mean"])
            vals = np.log1p(np.maximum(spec - baseline, 0))
            raw_feats.append(vals)

        # Z-score normalize across all tokens
        arr = np.array(raw_feats)
        mu = arr.mean(axis=0)
        sigma = arr.std(axis=0) + 1e-8
        raw_norm = [(f - mu) / sigma for f in raw_feats]

        # Polynomial expansion — degree 2 only (36d) to avoid dim curse
        # (degree 3 → 92d, degree 4 → 163d — too large for ESN)
        poly_feats = [_interaction_expand(f, max_degree=2) for f in raw_norm]

        cache[pid] = {
            "raw": raw_norm,
            "poly": poly_feats,
            "n_modes": n_modes,
            "raw_dim": len(raw_norm[0]),
            "poly_dim": len(poly_feats[0]),
        }
        print(f"  {pname}: {n_modes} modes → raw {len(raw_norm[0])}d, "
              f"poly {len(poly_feats[0])}d")

    return cache


# ── Main experiment ───────────────────────────────────────────────────

def run_experiment(plate_cache, seed=42):
    rng = np.random.default_rng(seed)

    # Generate sequences of 8-bit tokens
    sequences = rng.integers(0, N_TOKENS, size=(N_SEQUENCES, SEQ_LENGTH))
    reversed_seqs = sequences[:, ::-1].copy()
    n_train = int(0.75 * N_SEQUENCES)
    n_test = N_SEQUENCES - n_train

    # Check token coverage
    unique_tokens = len(np.unique(sequences[:n_train]))
    print(f"\n  Sequences: {N_SEQUENCES} ({n_train} train, {n_test} test)")
    print(f"  Unique tokens in training: {unique_tokens}/{N_TOKENS}")
    print(f"  Task: reverse [{SEQ_LENGTH} × 8-bit tokens]")
    print(f"  ESN: hidden={ESN_HIDDEN}, spectral={ESN_SPECTRAL}, "
          f"leak={ESN_LEAK}, input_scale={ESN_INPUT_SCALE}")

    results = {}

    # ── Helper: run ESN with per-bit readout ──
    def run_perbit(token_feats, label):
        dim = len(token_feats[0])
        all_f = [[token_feats[int(t)] for t in seq] for seq in sequences]
        esn = ESN(input_dim=dim)
        H_tr = esn.collect_states(all_f[:n_train])
        H_te = esn.collect_states(all_f[n_train:])

        # Per-bit accuracy: predict each bit at each position independently
        bit_accs = np.zeros((SEQ_LENGTH, N_INPUT_BITS))
        bit_preds_all = np.zeros((n_test, SEQ_LENGTH, N_INPUT_BITS), dtype=int)

        for pos in range(SEQ_LENGTH):
            target_tokens = reversed_seqs[:, pos]
            for bit in range(N_INPUT_BITS):
                y_tr = (target_tokens[:n_train] >> bit) & 1
                y_te = (target_tokens[n_train:] >> bit) & 1
                acc, preds = ridge_binary(H_tr, H_te, y_tr, y_te)
                bit_accs[pos, bit] = acc
                bit_preds_all[:, pos, bit] = preds

        # Reconstruct tokens from predicted bits
        token_accs = []
        for pos in range(SEQ_LENGTH):
            predicted_tokens = np.zeros(n_test, dtype=int)
            for bit in range(N_INPUT_BITS):
                predicted_tokens |= (bit_preds_all[:, pos, bit] << bit)
            y_te = reversed_seqs[n_train:, pos]
            token_acc = float(np.mean(predicted_tokens == y_te))
            token_accs.append(token_acc)

        mean_bit = float(np.mean(bit_accs))
        mean_token = float(np.mean(token_accs))

        return {
            'label': label, 'dim': dim,
            'mean_bit_acc': mean_bit,
            'mean_token_acc': mean_token,
            'bit_accs': bit_accs.tolist(),       # [pos][bit]
            'token_accs': token_accs,             # [pos]
            'pos_mean_bit': [float(np.mean(bit_accs[p])) for p in range(SEQ_LENGTH)],
        }

    # ── Helper: run ESN with 256-class readout ──
    def run_256class(token_feats, label):
        dim = len(token_feats[0])
        all_f = [[token_feats[int(t)] for t in seq] for seq in sequences]
        esn = ESN(input_dim=dim)
        H_tr = esn.collect_states(all_f[:n_train])
        H_te = esn.collect_states(all_f[n_train:])
        pos_accs = []
        for pos in range(SEQ_LENGTH):
            y_tr = reversed_seqs[:n_train, pos]
            y_te = reversed_seqs[n_train:, pos]
            acc, _ = ridge_multiclass(H_tr, H_te, y_tr, y_te, n_classes=N_TOKENS)
            pos_accs.append(acc)
        mean_t = np.mean(pos_accs)
        return {'label': label, 'dim': dim, 'mean_256class': float(mean_t),
                'pos_256class': pos_accs}

    # ── Print helper ──
    def print_perbit(r):
        pb = r['pos_mean_bit']
        ta = r['token_accs']
        print(f"  {r['label']:>25s} {r['dim']:5d}  "
              f"bit: {pb[0]:5.1%} {pb[1]:5.1%} {pb[2]:5.1%} {pb[3]:5.1%} "
              f"→ {r['mean_bit_acc']:5.1%}  "
              f"tok: {ta[0]:5.1%} {ta[1]:5.1%} {ta[2]:5.1%} {ta[3]:5.1%} "
              f"→ {r['mean_token_acc']:5.1%}")

    # ══════════════════════════════════════════════════════════════════
    #  1. SOFTWARE BASELINES (per-bit readout)
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 100}")
    print("  SOFTWARE BASELINES (per-bit readout)")
    print(f"{'=' * 100}")
    print(f"  {'Feature Set':>25s} {'dim':>5s}  "
          f"{'--- per-bit accuracy by position ---':^40s}  "
          f"{'--- token accuracy by position ---':^40s}")
    print("-" * 100)

    # Raw 8 bits
    raw_bits = [np.array([(t >> b) & 1 for b in range(N_INPUT_BITS)],
                         dtype=np.float64) * 2 - 1 for t in range(N_TOKENS)]
    r = run_perbit(raw_bits, "sw_raw_bits")
    results['sw_raw_bits'] = r
    print_perbit(r)

    # Degree-4 polynomial (163d — INCOMPLETE for 256 tokens)
    sw_poly4 = [software_poly(t, degree=4) for t in range(N_TOKENS)]
    r = run_perbit(sw_poly4, "sw_poly4")
    results['sw_poly4'] = r
    print_perbit(r)

    # Degree-6 polynomial (219d)
    sw_poly6 = [software_poly(t, degree=6) for t in range(N_TOKENS)]
    r = run_perbit(sw_poly6, "sw_poly6")
    results['sw_poly6'] = r
    print_perbit(r)

    # Degree-8 polynomial (256d — COMPLETE, should be perfect)
    sw_poly8 = [software_poly(t, degree=8) for t in range(N_TOKENS)]
    r = run_perbit(sw_poly8, "sw_poly8")
    results['sw_poly8'] = r
    print_perbit(r)

    # ══════════════════════════════════════════════════════════════════
    #  2. PLATE FEATURES — INDIVIDUAL (per-bit readout)
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 100}")
    print("  PLATE FEATURES — INDIVIDUAL (per-bit readout)")
    print(f"{'=' * 100}")

    for pid in TARGET_PLATES:
        if pid not in plate_cache:
            continue
        pname = PLATE_NAMES[pid]
        for ftype in ['raw', 'poly']:
            label = f"{pname}_{ftype}"
            feats = plate_cache[pid][ftype]
            r = run_perbit(feats, label)
            results[label] = r
            print_perbit(r)

    # ══════════════════════════════════════════════════════════════════
    #  3. CONCATENATED PLATE FEATURES (D+E)
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 100}")
    print("  CONCATENATED PLATE FEATURES D+E (per-bit readout)")
    print(f"{'=' * 100}")

    # Raw concat (16d)
    de_raw = [np.concatenate([plate_cache[pid]['raw'][t]
                              for pid in TARGET_PLATES if pid in plate_cache])
              for t in range(N_TOKENS)]
    r = run_perbit(de_raw, "DE_raw")
    results['DE_raw'] = r
    print_perbit(r)

    # Poly concat
    de_poly = [np.concatenate([plate_cache[pid]['poly'][t]
                               for pid in TARGET_PLATES if pid in plate_cache])
               for t in range(N_TOKENS)]
    r = run_perbit(de_poly, "DE_poly")
    results['DE_poly'] = r
    print_perbit(r)

    # Plate raw + sw_poly4
    de_plus_sw4 = [np.concatenate([de_raw[t], sw_poly4[t]])
                   for t in range(N_TOKENS)]
    r = run_perbit(de_plus_sw4, "DE_raw+sw_poly4")
    results['DE_raw+sw_poly4'] = r
    print_perbit(r)

    # ══════════════════════════════════════════════════════════════════
    #  4. 256-CLASS READOUT (secondary)
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 100}")
    print("  256-CLASS READOUT (secondary — data-limited)")
    print(f"{'=' * 100}")
    print(f"  {'Feature Set':>25s} {'dim':>5s}  "
          f"{'last':>7s} {'t3':>7s} {'t2':>7s} {'first':>7s} {'mean':>7s}")
    print("-" * 100)

    for label, feats in [("sw_poly4", sw_poly4), ("sw_poly8", sw_poly8),
                         ("DE_raw", de_raw), ("DE_poly", de_poly)]:
        lbl = f"{label}_256c"
        r = run_256class(feats, lbl)
        results[lbl] = r
        p = r['pos_256class']
        print(f"  {lbl:>25s} {r['dim']:5d}  "
              f"{p[0]:6.1%} {p[1]:6.1%} {p[2]:6.1%} {p[3]:6.1%} "
              f"{r['mean_256class']:6.1%}")

    # ══════════════════════════════════════════════════════════════════
    #  5. MEMORYLESS BASELINES
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 100}")
    print("  MEMORYLESS BASELINES (per-bit, last token only)")
    print(f"{'=' * 100}")

    for ml_label, ml_feats in [("ml_sw_poly4", sw_poly4),
                                ("ml_DE_raw", de_raw)]:
        X_tr = np.array([ml_feats[int(seq[-1])] for seq in sequences[:n_train]])
        X_te = np.array([ml_feats[int(seq[-1])] for seq in sequences[n_train:]])

        bit_accs = np.zeros((SEQ_LENGTH, N_INPUT_BITS))
        for pos in range(SEQ_LENGTH):
            for bit in range(N_INPUT_BITS):
                y_tr = (reversed_seqs[:n_train, pos] >> bit) & 1
                y_te = (reversed_seqs[n_train:, pos] >> bit) & 1
                acc, _ = ridge_binary(X_tr, X_te, y_tr, y_te)
                bit_accs[pos, bit] = acc

        mean_bit = float(np.mean(bit_accs))
        pos_means = [float(np.mean(bit_accs[p])) for p in range(SEQ_LENGTH)]

        results[ml_label] = {'label': ml_label, 'mean_bit_acc': mean_bit,
                             'pos_mean_bit': pos_means}
        print(f"  {ml_label:>25s}        "
              f"bit: {pos_means[0]:5.1%} {pos_means[1]:5.1%} "
              f"{pos_means[2]:5.1%} {pos_means[3]:5.1%} → {mean_bit:5.1%}")

    # ══════════════════════════════════════════════════════════════════
    #  6. VERDICT
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'═' * 100}")
    print("  VERDICT: DO PLATES BEAT INCOMPLETE SOFTWARE POLYNOMIAL?")
    print(f"{'═' * 100}")

    sw4_bit = results['sw_poly4']['mean_bit_acc']
    sw4_tok = results['sw_poly4']['mean_token_acc']
    sw8_bit = results['sw_poly8']['mean_bit_acc']
    sw8_tok = results['sw_poly8']['mean_token_acc']

    # Best plate-only
    plate_keys = [k for k in results if k.startswith('D') or k.startswith('E')
                  and 'sw' not in k and 'ml_' not in k and '256c' not in k]
    if plate_keys:
        best_plate_key = max(plate_keys, key=lambda k: results[k].get('mean_bit_acc', 0))
        bp = results[best_plate_key]
        bp_bit = bp['mean_bit_acc']
        bp_tok = bp['mean_token_acc']
    else:
        best_plate_key = "(none)"
        bp_bit = bp_tok = 0

    print(f"\n  Per-bit accuracy (higher = better, 50% = random):")
    print(f"    sw_poly4 (163d, incomplete):  {sw4_bit:6.1%}")
    print(f"    sw_poly8 (256d, complete):    {sw8_bit:6.1%}")
    print(f"    Best plate-only:              {bp_bit:6.1%}  ({best_plate_key})")
    ml_bit = results.get('ml_sw_poly4', {}).get('mean_bit_acc', 0.5)
    print(f"    Memoryless baseline:          {ml_bit:6.1%}")

    print(f"\n  Token accuracy (all 8 bits correct):")
    print(f"    sw_poly4 (163d, incomplete):  {sw4_tok:6.1%}")
    print(f"    sw_poly8 (256d, complete):    {sw8_tok:6.1%}")
    print(f"    Best plate-only:              {bp_tok:6.1%}  ({best_plate_key})")

    diff = bp_bit - sw4_bit
    if diff > 0.02:
        print(f"\n  ★ PLATE BEATS INCOMPLETE POLYNOMIAL by {diff:+.1%} (per-bit)")
        print(f"    Glass resonance captures structure beyond degree-4!")
    elif diff > 0.005:
        print(f"\n  ≈ PLATE MARGINALLY BETTER by {diff:+.1%} (per-bit)")
    elif diff > -0.005:
        print(f"\n  ≈ TIED (Δ = {diff:+.1%})")
    else:
        print(f"\n  ✗ SOFTWARE POLY4 STILL WINS by {-diff:+.1%}")

    gap_to_complete = sw8_bit - bp_bit
    print(f"\n  Gap: plate → sw_poly8 (complete) = {gap_to_complete:+.1%}")
    print(f"  Gap: sw_poly4 → sw_poly8 = {sw8_bit - sw4_bit:+.1%} "
          f"(room for improvement)")

    return results


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Load modes
    all_modes = _load_all_modes()
    for pid in TARGET_PLATES:
        pname = PLATE_NAMES[pid]
        modes = all_modes.get(pid, [])
        print(f"  Plate {pname}: {len(modes)} modes at "
              f"{[f'{f:.0f}' for f in modes]}")
        if len(modes) < N_INPUT_BITS:
            print(f"  ERROR: Plate {pname} needs {N_INPUT_BITS} modes, "
                  f"has {len(modes)}")
            sys.exit(1)

    # Load or run calibration
    calib_files = sorted(LAB_DIR.glob("esn_v3_8bit_*.json"))
    per_plate_calib = None

    if args.dry_run and calib_files:
        latest = calib_files[-1]
        print(f"\n  Loading 8-bit calibration: {latest.name}")
        with open(latest) as f:
            saved = json.load(f)
        per_plate_calib = {}
        for pid_key, pdata in saved["per_plate"].items():
            per_plate_calib[pid_key] = {
                "data": {int(k): v for k, v in pdata["data"].items()},
                "modes": pdata["modes"],
                "n_carriers": pdata["n_carriers"],
                "f_rep": pdata["f_rep"],
            }
        print(f"  Loaded {len(per_plate_calib)} plates")
    elif not args.dry_run:
        handle = _open_scope()
        mux = RelayMux(args.port)
        mux.open()

        try:
            per_plate_calib = calibrate_8bit(handle, mux, all_modes)
        finally:
            _close_scope(handle)
            mux.close()

        # Save calibration
        save_path = LAB_DIR / f"esn_v3_8bit_{TIMESTAMP}.json"
        save_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "n_bits": N_INPUT_BITS,
            "n_tokens": N_TOKENS,
            "n_reps": N_CALIB_REPS,
            "target_plates": [PLATE_NAMES[p] for p in TARGET_PLATES],
            "per_plate": {},
        }
        for pid, pdata in per_plate_calib.items():
            save_data["per_plate"][pid] = {
                "data": {str(k): v for k, v in pdata["data"].items()},
                "modes": pdata["modes"],
                "n_carriers": pdata["n_carriers"],
                "f_rep": pdata["f_rep"],
            }
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump(save_data, f)
        print(f"\n  Saved: {save_path}")
    else:
        print("\n  No 8-bit calibration found. Run without --dry-run.")
        sys.exit(1)

    # Build feature caches
    print(f"\n{'═' * 100}")
    print("  PLATE SEQUENCE ESN v3 — 8-BIT TOKENS (D+E)")
    print(f"{'═' * 100}")
    print(f"\n  Building token caches...")

    plate_cache = build_token_cache(per_plate_calib)

    # Run experiment
    results = run_experiment(plate_cache)

    # Save results
    save_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_bits": N_INPUT_BITS,
        "n_tokens": N_TOKENS,
        "n_sequences": N_SEQUENCES,
        "seq_length": SEQ_LENGTH,
        "esn_params": {
            "hidden": ESN_HIDDEN, "spectral_radius": ESN_SPECTRAL,
            "input_scale": ESN_INPUT_SCALE, "leak": ESN_LEAK,
        },
        "results": {},
    }
    for k, v in results.items():
        entry = {"label": v.get("label", k)}
        for field in ["dim", "mean_bit_acc", "mean_token_acc", "bit_accs",
                      "token_accs", "pos_mean_bit", "mean_256class",
                      "pos_256class"]:
            if field in v:
                entry[field] = v[field]
        save_results["results"][k] = entry

    res_path = LAB_DIR / f"sequence_esn_v3_{TIMESTAMP}.json"
    with open(res_path, 'w') as f:
        json.dump(save_results, f, indent=2)
    print(f"\n  Saved: {res_path}")


if __name__ == "__main__":
    main()
