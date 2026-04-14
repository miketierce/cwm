#!/usr/bin/env python3
"""
Plate Sequence ESN v2 — Per-Plate Calibration + Ensemble

Key differences from v1:
  - Each plate is driven ON-RESONANCE with its OWN modes (not just D's)
  - Each plate's features are extracted independently → 5 diverse projections
  - Ensemble: run separate ESN per plate, combine predictions
  - Baseline subtraction using silence (token 0) capture
  - Hyperparameter tuning from v1 analysis incorporated

Architecture insight: 5 independently-driven plates give UNCORRELATED errors.
One sw_poly ESN = one viewpoint. Five per-plate ESNs = five diverse viewpoints.
Ensemble of diverse views beats any single view.

Usage:
  PYTHONPATH=. python tools/plate_sequence_esn_v2.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_sequence_esn_v2.py --dry-run  # existing calibration
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

PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}
PLATE_IDS = sorted(PLATE_NAMES.keys())

# Experiment parameters
SEQ_LENGTH = 4
N_INPUT_BITS = 4
N_TOKENS = 16
N_SEQUENCES = 300
N_CALIB_REPS = 8
N_AVG = 4
T_EXCITE_S = 0.30
SETTLE_RELAY_S = 0.10

# ESN parameters (tuned from v1 sweep)
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


def ridge_multiclass(H_tr, H_te, y_tr, y_te, n_classes=N_TOKENS,
                     alpha=RIDGE_ALPHA):
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


def software_poly(token, n_bits=N_INPUT_BITS):
    bits = np.array([(token >> b) & 1 for b in range(n_bits)], dtype=np.float64)
    return _interaction_expand(bits * 2 - 1, max_degree=4)


# ── Per-plate calibration ────────────────────────────────────────────

def calibrate_per_plate(handle, mux, all_modes, readout_freqs,
                        n_reps=N_CALIB_REPS):
    """
    Per-plate calibration: drive each plate with ITS OWN modes.
    For each plate P:
      - Select min(4, N_modes) of P's modes as bit carriers
      - For each token (0-15), set AWG to P's mode subset
      - Read ONLY plate P (on-resonance, clean signal)

    Returns: {pid: {token_int: {"mean": array, "reps": [array, ...]}}}
    """
    per_plate_calib = {}
    total_captures = 0
    t0_total = time.time()

    for pid in PLATE_IDS:
        pname = PLATE_NAMES[pid]
        plate_modes = all_modes.get(pid, [])
        n_modes = len(plate_modes)
        if n_modes == 0:
            continue

        # Select bit-carrier modes (up to 4, evenly spaced across modes)
        n_carriers = min(N_INPUT_BITS, n_modes)
        carrier_indices = np.linspace(0, n_modes - 1, n_carriers, dtype=int)

        # ARB setup for this plate's frequency range
        max_freq = max(plate_modes)
        arb_len = 4096
        fixed_f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))

        print(f"\n  Plate {pname}: {n_modes} modes, "
              f"{n_carriers} carriers, f_rep={fixed_f_rep:.0f} Hz")

        # Switch mux to this plate ONCE (stays for all tokens)
        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        plate_calib = {}
        for token in range(N_TOKENS):
            bits = [(token >> b) & 1 for b in range(N_INPUT_BITS)]

            # Build drive pattern: turn ON carrier modes according to bits
            drive_freqs = []
            for b_idx in range(n_carriers):
                if bits[b_idx]:
                    mode_idx = carrier_indices[b_idx]
                    drive_freqs.append(plate_modes[mode_idx])
            amps = [1.0] * len(drive_freqs)

            reps_data = []
            for rep in range(n_reps):
                # Set AWG
                if drive_freqs:
                    _drive_multitone_arb(handle, drive_freqs, amps, fixed_f_rep)
                else:
                    _awg_off(handle)
                time.sleep(T_EXCITE_S)

                # Capture this plate's response
                mag = _capture_spectrum(handle, readout_freqs)
                reps_data.append(mag.tolist())
                total_captures += 1

            mean_mag = np.mean(reps_data, axis=0).tolist()
            plate_calib[token] = {"mean": mean_mag, "reps": reps_data}

            done = (token + 1) * n_reps
            total_for_plate = N_TOKENS * n_reps
            if done % (8 * n_reps) == 0 or done == total_for_plate:
                elapsed = time.time() - t0_total
                print(f"    [{PLATE_NAMES[pid]} {token+1}/{N_TOKENS}] "
                      f"total {total_captures} captures, {elapsed:.0f}s")

        per_plate_calib[pid] = {
            "data": plate_calib,
            "modes": plate_modes,
            "n_carriers": n_carriers,
            "carrier_indices": carrier_indices.tolist(),
            "f_rep": fixed_f_rep,
        }

    _awg_off(handle)
    elapsed = time.time() - t0_total
    print(f"\n  Per-plate calibration done: {total_captures} captures, "
          f"{elapsed:.0f}s")
    return per_plate_calib


# ── Feature extraction (per-plate) ───────────────────────────────────

def build_plate_readout_indices(all_modes, readout_freqs):
    """For each plate, map its modes to nearest readout frequency indices."""
    plate_idx = {}
    for pid in PLATE_IDS:
        pm = all_modes.get(pid, [])
        idxs = []
        for mf in pm:
            dists = [abs(mf - rf) for rf in readout_freqs]
            idxs.append(int(np.argmin(dists)))
        plate_idx[pid] = idxs
    return plate_idx


def extract_perplate_features(per_plate_calib, token, pid, plate_idx,
                               baseline=None, use_log=True):
    """
    Extract one plate's diagonal features for a token.
    Returns normalized mode amplitudes.
    """
    spec = np.array(per_plate_calib[pid]["data"][token]["mean"])
    idxs = plate_idx[pid]
    vals = spec[idxs]
    if baseline is not None:
        vals = vals - baseline[pid][idxs]
    if use_log:
        vals = np.log1p(np.maximum(vals, 0))
    return vals


def build_perplate_token_cache(per_plate_calib, all_modes, readout_freqs):
    """
    Build normalized per-plate feature caches for all 16 tokens.
    Returns: {pid: {"raw": [16 arrays], "poly": [16 arrays], "n_bits": int}}
    """
    plate_idx = build_plate_readout_indices(all_modes, readout_freqs)

    # Baseline: token 0 (no modes driven)
    baselines = {}
    for pid in PLATE_IDS:
        if pid in per_plate_calib:
            baselines[pid] = np.array(per_plate_calib[pid]["data"][0]["mean"])

    cache = {}
    for pid in PLATE_IDS:
        if pid not in per_plate_calib:
            continue

        pname = PLATE_NAMES[pid]
        n_modes = len(all_modes.get(pid, []))
        n_carriers = per_plate_calib[pid]["n_carriers"]

        # Extract raw features for all 16 tokens
        raw_feats = []
        for t in range(N_TOKENS):
            spec = np.array(per_plate_calib[pid]["data"][t]["mean"])
            vals = spec[plate_idx[pid]]
            base = baselines[pid][plate_idx[pid]]
            vals = np.log1p(np.maximum(vals - base, 0))
            raw_feats.append(vals)

        # Normalize
        arr = np.array(raw_feats)
        mu = arr.mean(axis=0)
        sigma = arr.std(axis=0) + 1e-8
        raw_norm = [(f - mu) / sigma for f in raw_feats]

        # Polynomial expansion
        deg = 4 if n_modes <= 4 else 3 if n_modes <= 6 else 2
        poly_feats = [_interaction_expand(f, max_degree=deg) for f in raw_norm]

        cache[pid] = {
            "raw": raw_norm,
            "poly": poly_feats,
            "n_carriers": n_carriers,
            "n_modes": n_modes,
            "raw_dim": len(raw_norm[0]),
            "poly_dim": len(poly_feats[0]),
        }
        print(f"  {pname}: {n_modes} modes, {n_carriers} carriers → "
              f"raw {len(raw_norm[0])}d, poly {len(poly_feats[0])}d")

    return cache


# ── Main experiment ───────────────────────────────────────────────────

def run_experiment(plate_cache, seed=42):
    """
    Run ESN sequence reversal with per-plate features.
    Tests: individual plates, concat, ensemble, and sw_poly baseline.
    """
    rng = np.random.default_rng(seed)

    # Generate sequences
    sequences = rng.integers(0, N_TOKENS, size=(N_SEQUENCES, SEQ_LENGTH))
    reversed_seqs = sequences[:, ::-1].copy()
    n_train = int(0.75 * N_SEQUENCES)

    print(f"\n  Sequences: {N_SEQUENCES} ({n_train} train, "
          f"{N_SEQUENCES - n_train} test)")
    print(f"  Task: reverse [{SEQ_LENGTH} tokens] → [{SEQ_LENGTH} tokens]")
    print(f"  ESN: hidden={ESN_HIDDEN}, spectral={ESN_SPECTRAL}, "
          f"leak={ESN_LEAK}, input_scale={ESN_INPUT_SCALE}")

    # ── Helper to run one ESN experiment ──
    def run_one(token_feats, label):
        dim = len(token_feats[0])
        all_f = [[token_feats[int(t)] for t in seq] for seq in sequences]
        esn = ESN(input_dim=dim)
        H_tr = esn.collect_states(all_f[:n_train])
        H_te = esn.collect_states(all_f[n_train:])
        pos_test = []
        all_scores = []
        for pos in range(SEQ_LENGTH):
            y_tr = reversed_seqs[:n_train, pos]
            y_te = reversed_seqs[n_train:, pos]
            te_acc, scores = ridge_multiclass(H_tr, H_te, y_tr, y_te)
            pos_test.append(te_acc)
            all_scores.append(scores)
        mean_t = np.mean(pos_test)
        return {'mean': mean_t, 'pos': pos_test, 'scores': all_scores,
                'dim': dim, 'label': label}

    results = {}

    # ── 1. Individual per-plate ESN ──
    print(f"\n{'=' * 80}")
    print("  INDIVIDUAL PER-PLATE ESN")
    print(f"{'=' * 80}")
    print(f"  {'Feature Set':>25s} {'dim':>5s} {'last':>7s} "
          f"{'t3':>7s} {'t2':>7s} {'first':>7s} {'mean':>7s}")
    print("-" * 80)

    for pid in PLATE_IDS:
        if pid not in plate_cache:
            continue
        pname = PLATE_NAMES[pid]
        for ftype in ['raw', 'poly']:
            label = f"{pname}_{ftype}"
            feats = plate_cache[pid][ftype]
            r = run_one(feats, label)
            results[label] = r
            p = r['pos']
            print(f"  {label:>25s} {r['dim']:5d} {p[0]:6.1%} "
                  f"{p[1]:6.1%} {p[2]:6.1%} {p[3]:6.1%} {r['mean']:6.1%}")

    # ── 2. Software baselines ──
    sw_feats = [software_poly(t) for t in range(N_TOKENS)]
    sw_result = run_one(sw_feats, "sw_poly")
    results['sw_poly'] = sw_result
    print(f"  {'sw_poly':>25s} {sw_result['dim']:5d} "
          f"{sw_result['pos'][0]:6.1%} {sw_result['pos'][1]:6.1%} "
          f"{sw_result['pos'][2]:6.1%} {sw_result['pos'][3]:6.1%} "
          f"{sw_result['mean']:6.1%} ◀SW")

    raw_bits = [np.array([(t >> b) & 1 for b in range(N_INPUT_BITS)],
                          dtype=np.float64) for t in range(N_TOKENS)]
    rb_result = run_one(raw_bits, "raw_bits")
    results['raw_bits'] = rb_result
    print(f"  {'raw_bits':>25s} {rb_result['dim']:5d} "
          f"{rb_result['pos'][0]:6.1%} {rb_result['pos'][1]:6.1%} "
          f"{rb_result['pos'][2]:6.1%} {rb_result['pos'][3]:6.1%} "
          f"{rb_result['mean']:6.1%}")

    # ── 3. Concatenated features ──
    print(f"\n{'=' * 80}")
    print("  CONCATENATED FEATURES")
    print(f"{'=' * 80}")

    # All plates raw concat
    all_raw = [np.concatenate([plate_cache[pid]['raw'][t]
                                for pid in PLATE_IDS if pid in plate_cache])
               for t in range(N_TOKENS)]
    r = run_one(all_raw, "concat_raw")
    results['concat_raw'] = r
    print(f"  {'concat_raw':>25s} {r['dim']:5d} {r['pos'][0]:6.1%} "
          f"{r['pos'][1]:6.1%} {r['pos'][2]:6.1%} {r['pos'][3]:6.1%} "
          f"{r['mean']:6.1%}")

    # All plates poly concat
    all_poly = [np.concatenate([plate_cache[pid]['poly'][t]
                                 for pid in PLATE_IDS if pid in plate_cache])
                for t in range(N_TOKENS)]
    r = run_one(all_poly, "concat_poly")
    results['concat_poly'] = r
    print(f"  {'concat_poly':>25s} {r['dim']:5d} {r['pos'][0]:6.1%} "
          f"{r['pos'][1]:6.1%} {r['pos'][2]:6.1%} {r['pos'][3]:6.1%} "
          f"{r['mean']:6.1%}")

    # Plates + sw_poly concat
    plates_plus_sw = [np.concatenate([all_raw[t], sw_feats[t]])
                      for t in range(N_TOKENS)]
    r = run_one(plates_plus_sw, "plates_raw+sw")
    results['plates_raw+sw'] = r
    print(f"  {'plates_raw+sw':>25s} {r['dim']:5d} {r['pos'][0]:6.1%} "
          f"{r['pos'][1]:6.1%} {r['pos'][2]:6.1%} {r['pos'][3]:6.1%} "
          f"{r['mean']:6.1%}")

    # ── 4. ENSEMBLE (average raw scores from per-plate ESNs) ──
    print(f"\n{'=' * 80}")
    print("  ENSEMBLE (averaged per-plate ESN scores)")
    print(f"{'=' * 80}")

    def ensemble_accuracy(score_dicts, label):
        pos_accs = []
        for pos in range(SEQ_LENGTH):
            y_te = reversed_seqs[n_train:, pos]
            combined = np.zeros_like(score_dicts[0][pos])
            for sd in score_dicts:
                s = sd[pos]
                s_norm = s - s.mean(axis=1, keepdims=True)
                s_std = s.std(axis=1, keepdims=True) + 1e-8
                combined += s_norm / s_std
            preds = np.argmax(combined, axis=1)
            pos_accs.append(float(np.mean(preds == y_te)))
        mean_t = np.mean(pos_accs)
        return {'mean': mean_t, 'pos': pos_accs, 'label': label}

    # All plates poly ensemble
    plate_poly_scores = [results[f'{PLATE_NAMES[pid]}_poly']['scores']
                         for pid in PLATE_IDS
                         if f'{PLATE_NAMES[pid]}_poly' in results]
    if plate_poly_scores:
        r = ensemble_accuracy(plate_poly_scores, "ens_all_poly")
        results['ens_all_poly'] = r
        print(f"  {'ens_all_poly':>25s}       {r['pos'][0]:6.1%} "
              f"{r['pos'][1]:6.1%} {r['pos'][2]:6.1%} {r['pos'][3]:6.1%} "
              f"{r['mean']:6.1%}")

    # All plates raw ensemble
    plate_raw_scores = [results[f'{PLATE_NAMES[pid]}_raw']['scores']
                        for pid in PLATE_IDS
                        if f'{PLATE_NAMES[pid]}_raw' in results]
    if plate_raw_scores:
        r = ensemble_accuracy(plate_raw_scores, "ens_all_raw")
        results['ens_all_raw'] = r
        print(f"  {'ens_all_raw':>25s}       {r['pos'][0]:6.1%} "
              f"{r['pos'][1]:6.1%} {r['pos'][2]:6.1%} {r['pos'][3]:6.1%} "
              f"{r['mean']:6.1%}")

    # Plates + sw_poly ensemble
    all_scores = plate_poly_scores + [sw_result['scores']]
    r = ensemble_accuracy(all_scores, "ens_poly+sw")
    results['ens_poly+sw'] = r
    print(f"  {'ens_poly+sw':>25s}       {r['pos'][0]:6.1%} "
          f"{r['pos'][1]:6.1%} {r['pos'][2]:6.1%} {r['pos'][3]:6.1%} "
          f"{r['mean']:6.1%}")

    # Top-N plate ensembles
    plate_means = [(pid, results.get(f'{PLATE_NAMES[pid]}_poly', {}).get('mean', 0))
                   for pid in PLATE_IDS if pid in plate_cache]
    plate_means.sort(key=lambda x: -x[1])
    for n_top in [2, 3]:
        top_pids = [pm[0] for pm in plate_means[:n_top]]
        top_names = [PLATE_NAMES[p] for p in top_pids]
        top_scores = [results[f'{PLATE_NAMES[p]}_poly']['scores'] for p in top_pids]
        label = f"ens_top{n_top}_poly"
        r = ensemble_accuracy(top_scores, label)
        results[label] = r
        print(f"  {label:>25s}       {r['pos'][0]:6.1%} "
              f"{r['pos'][1]:6.1%} {r['pos'][2]:6.1%} {r['pos'][3]:6.1%} "
              f"{r['mean']:6.1%}  ({','.join(top_names)})")

        # With sw_poly
        label2 = f"ens_top{n_top}+sw"
        r2 = ensemble_accuracy(top_scores + [sw_result['scores']], label2)
        results[label2] = r2
        print(f"  {label2:>25s}       {r2['pos'][0]:6.1%} "
              f"{r2['pos'][1]:6.1%} {r2['pos'][2]:6.1%} {r2['pos'][3]:6.1%} "
              f"{r2['mean']:6.1%}")

    # ── 5. Memoryless baseline ──
    print(f"\n{'=' * 80}")
    print("  MEMORYLESS BASELINES")
    print(f"{'=' * 80}")

    for base_label, base_feats in [("ml_sw_poly", sw_feats),
                                    ("ml_concat_raw", all_raw)]:
        X_tr = np.array([base_feats[int(seq[-1])] for seq in sequences[:n_train]])
        X_te = np.array([base_feats[int(seq[-1])] for seq in sequences[n_train:]])
        pos_accs = []
        for pos in range(SEQ_LENGTH):
            y_tr = reversed_seqs[:n_train, pos]
            y_te = reversed_seqs[n_train:, pos]
            te_acc, _ = ridge_multiclass(
                np.column_stack([X_tr, np.zeros((len(X_tr), 1))]),
                np.column_stack([X_te, np.zeros((len(X_te), 1))]),
                y_tr, y_te)
            pos_accs.append(te_acc)
        mean_t = np.mean(pos_accs)
        results[base_label] = {'mean': mean_t, 'pos': pos_accs}
        print(f"  {base_label:>25s}       {pos_accs[0]:6.1%} "
              f"{pos_accs[1]:6.1%} {pos_accs[2]:6.1%} {pos_accs[3]:6.1%} "
              f"{mean_t:6.1%}")

    # ── 6. VERDICT ──
    print(f"\n{'═' * 80}")
    print("  VERDICT: DOES THE PLATE BEAT SOFTWARE?")
    print(f"{'═' * 80}")

    sw_mean = results['sw_poly']['mean']

    # Find best plate-only result
    plate_only = {k: v for k, v in results.items()
                  if k not in ('sw_poly', 'raw_bits') and 'sw' not in k and 'ml_' not in k}
    best_plate_label = max(plate_only, key=lambda k: plate_only[k]['mean'])
    best_plate_mean = plate_only[best_plate_label]['mean']

    # Find best plate+sw ensemble
    plate_plus_sw = {k: v for k, v in results.items()
                     if '+sw' in k and 'ml_' not in k}
    best_combo_label = max(plate_plus_sw, key=lambda k: plate_plus_sw[k]['mean'])
    best_combo_mean = plate_plus_sw[best_combo_label]['mean']

    print(f"\n  sw_poly alone:          {sw_mean:6.1%}")
    print(f"  Best plate-only:        {best_plate_mean:6.1%} ({best_plate_label})")
    print(f"  Best plate+sw ensemble: {best_combo_mean:6.1%} ({best_combo_label})")

    diff_plate = best_plate_mean - sw_mean
    diff_combo = best_combo_mean - sw_mean

    if diff_plate > 0.05:
        print(f"\n  ★ PLATE BEATS SOFTWARE by {diff_plate:+.1%}")
        print(f"    The glass plates provide unique computational value!")
    elif diff_combo > 0.05:
        print(f"\n  ★ PLATE + SOFTWARE BEATS SOFTWARE ALONE by {diff_combo:+.1%}")
        print(f"    The plates ADD genuine value when combined with software!")
    elif diff_plate > 0.01:
        print(f"\n  ≈ PLATE MARGINALLY BETTER by {diff_plate:+.1%}")
        print(f"    Small advantage — may not be statistically significant")
    elif diff_combo > 0.01:
        print(f"\n  ≈ PLATE+SW MARGINALLY BETTER by {diff_combo:+.1%}")
        print(f"    Plates add small ensemble benefit")
    else:
        print(f"\n  ✗ SOFTWARE WINS or TIES")
        print(f"    Plate-only gap: {diff_plate:+.1%}")
        print(f"    Plate+sw gap:   {diff_combo:+.1%}")

    # Memoryless check
    ml_mean = results.get('ml_sw_poly', {}).get('mean', 0)
    esn_gain = sw_mean - ml_mean
    print(f"\n  Sequence processing: ESN +{esn_gain:.1%} over memoryless "
          f"({'YES' if esn_gain > 0.05 else 'MARGINAL' if esn_gain > 0.01 else 'NO'})")

    return results


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load existing per-plate calibration")
    args = parser.parse_args()

    # Load mode census
    all_modes = _load_all_modes()
    total_modes = sum(len(v) for v in all_modes.values())
    print(f"  Modes: {total_modes} across {len(all_modes)} plates")

    # Build readout frequency grid (union of all modes)
    all_freqs = sorted(set(f for fm in all_modes.values() for f in fm))
    readout_freqs = all_freqs
    print(f"  Readout grid: {len(readout_freqs)} frequencies")

    # Try to load existing per-plate calibration
    calib_files = sorted(LAB_DIR.glob("esn_v2_perplate_*.json"))
    per_plate_calib = None

    if args.dry_run and calib_files:
        latest = calib_files[-1]
        print(f"\n  Loading per-plate calibration: {latest.name}")
        with open(latest) as f:
            saved = json.load(f)
        per_plate_calib = {}
        for pid_key, pdata in saved["per_plate"].items():
            # Reconstruct: token keys were str, convert data
            reconstructed = {
                "data": {int(k): v for k, v in pdata["data"].items()},
                "modes": pdata["modes"],
                "n_carriers": pdata["n_carriers"],
                "carrier_indices": pdata["carrier_indices"],
                "f_rep": pdata["f_rep"],
            }
            per_plate_calib[pid_key] = reconstructed
        print(f"  Loaded {len(per_plate_calib)} plates")
    elif not args.dry_run:
        # Hardware calibration
        handle = _open_scope()
        mux = RelayMux(args.port)
        mux.open()

        try:
            per_plate_calib = calibrate_per_plate(
                handle, mux, all_modes, readout_freqs)
        finally:
            _close_scope(handle)
            mux.close()

        # Save calibration
        save_path = LAB_DIR / f"esn_v2_perplate_{TIMESTAMP}.json"
        save_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "n_reps": N_CALIB_REPS,
            "readout_freqs_hz": readout_freqs,
            "plate_modes": {PLATE_NAMES.get(pid, pid): modes
                            for pid, modes in all_modes.items()},
            "per_plate": {},
        }
        for pid, pdata in per_plate_calib.items():
            save_data["per_plate"][pid] = {
                "data": {str(k): v for k, v in pdata["data"].items()},
                "modes": pdata["modes"],
                "n_carriers": pdata["n_carriers"],
                "carrier_indices": pdata["carrier_indices"],
                "f_rep": pdata["f_rep"],
            }
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump(save_data, f)
        print(f"\n  Saved: {save_path}")
    else:
        print("\n  No per-plate calibration found. Run without --dry-run.")
        sys.exit(1)

    # Build feature caches
    print(f"\n{'═' * 80}")
    print("  PLATE SEQUENCE ESN v2 — PER-PLATE CALIBRATION + ENSEMBLE")
    print(f"{'═' * 80}")
    print(f"\n  Building per-plate feature caches...")

    plate_cache = build_perplate_token_cache(
        per_plate_calib, all_modes, readout_freqs)

    # Run experiment
    results = run_experiment(plate_cache)

    # Save results
    save_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "esn_params": {
            "hidden": ESN_HIDDEN, "spectral_radius": ESN_SPECTRAL,
            "input_scale": ESN_INPUT_SCALE, "leak": ESN_LEAK,
        },
        "ridge_alpha": RIDGE_ALPHA,
        "n_sequences": N_SEQUENCES,
        "seq_length": SEQ_LENGTH,
        "results": {k: {"mean": v["mean"],
                         "pos_test": v.get("pos", []),
                         "dim": v.get("dim", 0)}
                    for k, v in results.items()},
    }
    res_path = LAB_DIR / f"sequence_esn_v2_{TIMESTAMP}.json"
    with open(res_path, 'w') as f:
        json.dump(save_results, f, indent=2)
    print(f"\n  Saved: {res_path}")


if __name__ == "__main__":
    main()
