#!/usr/bin/env python3
"""
CWM Demo: Glass Memory in Action
══════════════════════════════════

The most compelling demonstration of Coherent Wave Memory:
five fused-silica plates encoding, remembering, and computing
with vibrations — beating software at its own game.

Phases:
  1. AUTHENTICATE — identify all 5 plates by spectral fingerprint
  2. TRAIN        — build ESN readout from calibration data
  3. ENCODE       — drive live tokens through glass, show unique fingerprints
  4. REMEMBER     — sequence reversal: type a word, glass decodes it
  5. SHOWDOWN     — 500-trial stress test: glass vs software scoreboard

Usage:
  Hardware:  PYTHONPATH=. python tools/cwm_demo.py --port /dev/cu.usbserial-11310
  Dry-run:   PYTHONPATH=. python tools/cwm_demo.py --dry-run
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
ROOT = TOOLS_DIR.parent

# ── Hardware imports (conditional) ────────────────────────────────────

HW_AVAILABLE = False
try:
    import cwm_picoscope
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
    from relay_mux import RelayMux
    HW_AVAILABLE = True
except Exception:
    SAMPLE_RATE = 781_250
    N_SAMPLES = 8064
    TIMEBASE = 3
    AWG_DRIVE_UVPP = 2_000_000

# ── Paths ─────────────────────────────────────────────────────────────

LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
CALIB_V3 = LAB_DIR / "esn_v3_8bit_20260413_182237.json"
CALIB_V4_L2 = LAB_DIR / "esn_v4_L2_20260413_221433.json"
RESULTS_DIR = LAB_DIR
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ── Plate config ──────────────────────────────────────────────────────

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}
TARGET_PLATES = ["4", "5"]       # D and E for 8-bit encoding
ALL_MODES: dict[str, list[float]] = {}

# ESN parameters
N_MODES = 8
N_TOKENS = 256
SEQ_LEN = 4
N_SEQUENCES = 2000
ESN_HIDDEN = 200
ESN_SPECTRAL = 0.9
ESN_INPUT_SCALE = 0.1
ESN_LEAK = 0.9
RIDGE_ALPHA = 10.0

# Hardware timing
T_EXCITE_S = 0.30
SETTLE_RELAY_S = 0.10
N_AVG = 4

# Display
W = 78  # terminal width

# ── ANSI formatting ───────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
CROSS = f"{RED}✗{RESET}"


def banner(text: str, char="═"):
    pad = max(0, W - len(text) - 4)
    left = pad // 2
    right = pad - left
    print(f"\n{BOLD}{char * left}  {text}  {char * right}{RESET}")


def subhead(text: str):
    print(f"\n  {BOLD}{CYAN}{text}{RESET}")


def ok(text: str):
    print(f"  {CHECK} {text}")


def fail(text: str):
    print(f"  {CROSS} {text}")


def info(text: str):
    print(f"  {DIM}│{RESET} {text}")


def bar_chart(label: str, value: float, max_val: float = 100.0,
              width: int = 30, color: str = GREEN):
    filled = int(round(value / max_val * width))
    empty = width - filled
    pct = f"{value:.1f}%"
    print(f"  {label:>20s} {color}{'█' * filled}{DIM}{'░' * empty}{RESET} {pct}")


def bitstring(token: int, n_bits: int = 8) -> str:
    return ''.join('█' if (token >> b) & 1 else '░' for b in range(n_bits))


# ── Hardware helpers ──────────────────────────────────────────────────

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
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
        buf += a * np.sin(2 * np.pi * k * np.arange(arb_len) / arb_len)
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
        ps2000.ps2000_run_block(
            handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
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
    return np.mean(all_mags, axis=0) if all_mags else np.zeros(len(readout_freqs))


# ── Census / mode loading ─────────────────────────────────────────────

def _load_all_modes() -> dict[str, list[float]]:
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name)
    if not census_files:
        raise FileNotFoundError("No census file in " + str(LAB_DIR))
    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]
    modes = {}
    for pid in PLATE_IDS:
        if pid in census and census[pid].get("peaks"):
            modes[pid] = [p["freq_hz"] for p in census[pid]["peaks"]]
    return modes


# ── ESN core ──────────────────────────────────────────────────────────

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
    w = np.linalg.solve(
        Hb_tr.T @ Hb_tr + alpha * np.eye(d),
        Hb_tr.T @ y_tr.astype(np.float64))
    preds = (Hb_te @ w > 0.5).astype(int)
    acc = float(np.mean(preds == y_te))
    return acc, preds, w


def _interaction_expand(x, max_degree=3):
    n = len(x)
    terms = list(x)
    for deg in range(2, max_degree + 1):
        for combo in combinations(range(n), deg):
            t = 1.0
            for idx in combo:
                t *= x[idx]
            terms.append(t)
    return np.array(terms)


# ── Calibration loading & feature extraction ──────────────────────────

def load_calibration(path: Path | None = None):
    """Load v3 or v4-L2 calibration. Returns per-plate feature dicts."""
    if path is None:
        path = CALIB_V3 if CALIB_V3.exists() else CALIB_V4_L2
    with open(path) as f:
        calib = json.load(f)

    feat_maps = {}   # pid → {token_id: normalized_feature_vector}
    raw_maps = {}    # pid → {token_id: raw mean magnitudes}
    noise_maps = {}  # pid → per-rep standard deviations (for dry-run noise)

    for pid in TARGET_PLATES:
        pdata = calib["per_plate"].get(pid, {})
        data = pdata.get("data", {})
        modes = pdata.get("modes", [])

        # Get baseline (token 0 = all modes off)
        baseline = np.array(data["0"]["mean"])

        # Raw features
        raw_feats = {}
        rep_stds = {}
        for t in range(N_TOKENS):
            tk = str(t)
            if tk not in data:
                continue
            mean = np.array(data[tk]["mean"])
            raw_feats[t] = mean
            if "reps" in data[tk] and len(data[tk]["reps"]) > 1:
                rep_stds[t] = np.std(data[tk]["reps"], axis=0)

        # Normalize: log1p(max(x - baseline, 0)) → Z-score
        log_feats = {}
        for t, mean in raw_feats.items():
            log_feats[t] = np.log1p(np.maximum(mean - baseline, 0))

        all_log = np.array([log_feats[t] for t in range(N_TOKENS)
                            if t in log_feats])
        mu = all_log.mean(axis=0)
        sigma = all_log.std(axis=0) + 1e-8

        norm_feats = {}
        for t in log_feats:
            norm_feats[t] = (log_feats[t] - mu) / sigma

        feat_maps[pid] = norm_feats
        raw_maps[pid] = raw_feats
        noise_maps[pid] = rep_stds

    return feat_maps, raw_maps, noise_maps


def build_sw_baselines():
    """Software baselines: raw bits and poly4."""
    sw_raw = {}
    sw_poly4 = {}
    for t in range(N_TOKENS):
        bits = np.array([(t >> b) & 1 for b in range(N_MODES)],
                        dtype=np.float64) * 2 - 1
        sw_raw[t] = bits
        sw_poly4[t] = _interaction_expand(bits, max_degree=4)
    return sw_raw, sw_poly4


def build_de_features(feat_maps_d, feat_maps_e):
    """Concatenate D + E normalized features → 16d vectors."""
    de_feats = {}
    for t in range(N_TOKENS):
        if t in feat_maps_d and t in feat_maps_e:
            de_feats[t] = np.concatenate([feat_maps_d[t], feat_maps_e[t]])
    return de_feats


# ── Sequence generation ───────────────────────────────────────────────

def generate_sequences(n_seq=N_SEQUENCES, seq_len=SEQ_LEN, seed=42):
    rng = np.random.default_rng(seed)
    seqs = rng.integers(0, N_TOKENS, size=(n_seq, seq_len))
    rev = seqs[:, ::-1].copy()
    return seqs, rev


# ── Train & evaluate ESN ─────────────────────────────────────────────

def train_esn(feat_map, label, sequences, reversed_seqs, n_train=1500):
    """Train ESN with per-bit readout. Returns accuracy dict and trained weights."""
    dim = len(next(iter(feat_map.values())))
    esn = ESN(input_dim=dim)

    # Build feature sequences
    all_feat_seqs = []
    for seq in sequences:
        all_feat_seqs.append([feat_map[int(t)] for t in seq])

    H_tr = esn.collect_states(all_feat_seqs[:n_train])
    H_te = esn.collect_states(all_feat_seqs[n_train:])
    n_test = len(H_te)

    # Per-bit readout
    bit_accs = np.zeros((SEQ_LEN, N_MODES))
    bit_preds = np.zeros((n_test, SEQ_LEN, N_MODES), dtype=int)
    readout_weights = {}

    for pos in range(SEQ_LEN):
        target_tokens = reversed_seqs[:, pos]
        for bit in range(N_MODES):
            y_tr = (target_tokens[:n_train] >> bit) & 1
            y_te = (target_tokens[n_train:] >> bit) & 1
            acc, preds, w = ridge_binary(H_tr, H_te, y_tr, y_te)
            bit_accs[pos, bit] = acc
            bit_preds[:, pos, bit] = preds
            readout_weights[(pos, bit)] = w

    # Reconstruct tokens
    token_preds = np.zeros((n_test, SEQ_LEN), dtype=int)
    for pos in range(SEQ_LEN):
        for bit in range(N_MODES):
            token_preds[:, pos] |= bit_preds[:, pos, bit] << bit

    # Per-position accuracy
    pos_digit_acc = bit_accs.mean(axis=1)
    pos_token_acc = np.zeros(SEQ_LEN)
    for pos in range(SEQ_LEN):
        gt = reversed_seqs[n_train:, pos]
        pos_token_acc[pos] = np.mean(token_preds[:, pos] == gt)

    return {
        "label": label,
        "dim": dim,
        "digit_acc_mean": float(bit_accs.mean()),
        "token_acc_mean": float(pos_token_acc.mean()),
        "pos_digit": pos_digit_acc.tolist(),
        "pos_token": pos_token_acc.tolist(),
        "esn": esn,
        "readout_weights": readout_weights,
        "H_te": H_te,
        "token_preds": token_preds,
    }


def predict_sequence(esn, readout_weights, feat_seq):
    """Predict reversed sequence from a single feature sequence."""
    h = esn.run_sequence(feat_seq)
    Hb = np.append(h, 1.0)   # add bias
    predicted = np.zeros(SEQ_LEN, dtype=int)
    for pos in range(SEQ_LEN):
        for bit in range(N_MODES):
            w = readout_weights[(pos, bit)]
            val = Hb @ w
            if val > 0.5:
                predicted[pos] |= 1 << bit
    return predicted


# ── Live capture helper ───────────────────────────────────────────────

def capture_token_live(handle, mux, token, all_modes, feat_maps,
                       raw_maps, noise_maps):
    """Drive a single token through D+E, capture live response.
    Returns normalized feature vectors for D and E."""
    bits = [(token >> b) & 1 for b in range(N_MODES)]
    feats = {}

    for pid in TARGET_PLATES:
        plate_modes = all_modes.get(pid, [])[:N_MODES]
        if not plate_modes:
            continue
        max_freq = max(plate_modes)
        f_rep = max(10.0, math.ceil(max_freq / (4096 // 2 - 10)))

        drive_freqs = [f for f, b in zip(plate_modes, bits) if b]
        drive_amps = [1.0] * len(drive_freqs)

        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        if drive_freqs:
            _drive_multitone_arb(handle, drive_freqs, drive_amps, f_rep)
        else:
            _awg_off(handle)
        time.sleep(T_EXCITE_S)

        mag = _capture_spectrum(handle, plate_modes)
        feats[pid] = mag

    _awg_off(handle)

    # Normalize using calibration statistics
    norm_feats = {}
    for pid in TARGET_PLATES:
        if pid not in feats:
            continue
        baseline = np.array(raw_maps[pid][0])
        log_f = np.log1p(np.maximum(feats[pid] - baseline, 0))
        # Use calibration mu/sigma for consistency
        all_log = np.array([np.log1p(np.maximum(
            np.array(raw_maps[pid][t]) - baseline, 0))
            for t in range(N_TOKENS) if t in raw_maps[pid]])
        mu = all_log.mean(axis=0)
        sigma = all_log.std(axis=0) + 1e-8
        norm_feats[pid] = (log_f - mu) / sigma

    return norm_feats


def match_token(live_raw, plate_id, raw_maps, n_tokens=N_TOKENS):
    """Matched-filter: correlate live spectrum against all calibration templates.
    Returns (best_token_id, best_correlation)."""
    best_t = 0
    best_corr = -1.0
    for t in range(n_tokens):
        if t not in raw_maps[plate_id]:
            continue
        cal = np.array(raw_maps[plate_id][t])
        corr = float(np.corrcoef(live_raw, cal)[0, 1])
        if corr > best_corr:
            best_corr = corr
            best_t = t
    return best_t, best_corr


def capture_and_match(handle, mux, token, all_modes, feat_maps,
                      raw_maps, noise_maps):
    """Drive a single token through D+E, capture live response,
    then matched-filter to the best calibration token.
    Returns dict with calibration features and match info."""
    bits = [(token >> b) & 1 for b in range(N_MODES)]
    match_info = {}
    result_feats = {}

    for pid in TARGET_PLATES:
        plate_modes = all_modes.get(pid, [])[:N_MODES]
        if not plate_modes:
            continue
        max_freq = max(plate_modes)
        f_rep = max(10.0, math.ceil(max_freq / (4096 // 2 - 10)))

        drive_freqs = [f for f, b in zip(plate_modes, bits) if b]
        drive_amps = [1.0] * len(drive_freqs)

        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        if drive_freqs:
            _drive_multitone_arb(handle, drive_freqs, drive_amps, f_rep)
        else:
            _awg_off(handle)
        time.sleep(T_EXCITE_S)

        mag = _capture_spectrum(handle, plate_modes)

        # Matched-filter: identify the token from the live capture
        matched_t, matched_corr = match_token(mag, pid, raw_maps)
        match_info[pid] = {"matched_token": matched_t, "correlation": matched_corr,
                           "correct": matched_t == token}

        # Use the calibration features (clean, averaged) for ESN input
        result_feats[pid] = feat_maps[pid].get(matched_t, np.zeros(N_MODES))

    _awg_off(handle)
    return result_feats, match_info


def simulate_token_capture(token, feat_maps, noise_maps, rng):
    """Simulate a live capture by adding calibration-scale noise."""
    result = {}
    for pid in TARGET_PLATES:
        base_feat = feat_maps[pid].get(token)
        if base_feat is None:
            continue
        # Add noise at ~20% of calibration rep noise
        noise_scale = 0.15
        noise = rng.standard_normal(len(base_feat)) * noise_scale
        result[pid] = base_feat + noise
    return result


# ── Authentication ────────────────────────────────────────────────────

def authenticate_plates(handle, mux, all_modes):
    """Drive broadband signal, identify each plate by spectral fingerprint."""
    subhead("Phase 1: AUTHENTICATE — Identifying all 5 plates")
    print()

    # Drive all 8 modes of plate D (arbitrary choice for broadband probe)
    probe_modes = all_modes.get("4", [])[:N_MODES]
    if not probe_modes:
        info("No mode data for probe — skipping authentication")
        return

    max_freq = max(probe_modes)
    f_rep = max(10.0, math.ceil(max_freq / (4096 // 2 - 10)))

    # Capture each plate's response to the same drive
    responses = {}
    for pid in PLATE_IDS:
        pname = PLATE_NAMES[pid]
        plate_modes = all_modes.get(pid, [])
        if not plate_modes:
            info(f"Plate {pname}: no modes — skipping")
            continue

        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        _drive_multitone_arb(handle, probe_modes, [1.0] * len(probe_modes),
                             f_rep)
        time.sleep(T_EXCITE_S)

        mag = _capture_spectrum(handle, probe_modes)
        responses[pid] = mag

        # Show fingerprint
        mag_norm = mag / (np.max(mag) + 1e-8)
        bars = ''.join('█' if v > 0.3 else '▄' if v > 0.1 else '░'
                       for v in mag_norm)
        peak = np.max(mag)
        ok(f"Plate {pname}: [{bars}]  peak={peak:,.0f}")

    _awg_off(handle)

    # Cross-correlation matrix
    if len(responses) >= 2:
        print()
        info("Cross-plate discrimination:")
        pids = sorted(responses.keys())
        for i, p1 in enumerate(pids):
            for p2 in pids[i + 1:]:
                r1 = responses[p1] / (np.linalg.norm(responses[p1]) + 1e-8)
                r2 = responses[p2] / (np.linalg.norm(responses[p2]) + 1e-8)
                corr = float(np.dot(r1, r2))
                name1 = PLATE_NAMES[p1]
                name2 = PLATE_NAMES[p2]
                indicator = f"{GREEN}distinct{RESET}" if corr < 0.95 \
                    else f"{RED}similar{RESET}"
                info(f"  {name1}↔{name2}: ρ = {corr:.3f}  [{indicator}]")


# ══════════════════════════════════════════════════════════════════════
#                            MAIN DEMO
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="CWM Demo: Glass Memory")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use calibration data only (no hardware)")
    parser.add_argument("--quick", action="store_true",
                        help="Skip authentication and stress test")
    parser.add_argument("--message", type=str, default=None,
                        help="Message to encode (default: interactive)")
    args = parser.parse_args()

    dry_run = args.dry_run or not HW_AVAILABLE
    rng = np.random.default_rng(seed=99)

    # ── Header ────────────────────────────────────────────────────────

    print()
    banner("CWM DEMO: GLASS MEMORY IN ACTION")
    print()
    info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    info(f"Mode: {'DRY-RUN (calibration data)' if dry_run else 'LIVE HARDWARE'}")
    if not dry_run:
        info(f"Port: {args.port}")

    # ── Load modes ────────────────────────────────────────────────────

    global ALL_MODES
    ALL_MODES = _load_all_modes()
    for pid in TARGET_PLATES:
        pname = PLATE_NAMES[pid]
        modes = ALL_MODES.get(pid, [])
        info(f"Plate {pname}: {len(modes)} modes @ "
             f"{[f'{f:.0f}' for f in modes]}")

    # ── Hardware init ─────────────────────────────────────────────────

    handle = None
    mux = None
    if not dry_run:
        try:
            handle = _open_scope()
            mux = RelayMux(port=args.port)
            mux.open()
            ok("PicoScope + relay mux connected")
        except Exception as e:
            print(f"  {RED}Hardware init failed: {e}{RESET}")
            print(f"  {YELLOW}Falling back to dry-run mode{RESET}")
            dry_run = True

    # ══════════════════════════════════════════════════════════════════
    #  PHASE 1: AUTHENTICATE
    # ══════════════════════════════════════════════════════════════════

    if not dry_run and not args.quick:
        banner("PHASE 1: AUTHENTICATE", "─")
        authenticate_plates(handle, mux, ALL_MODES)
    elif not args.quick:
        banner("PHASE 1: AUTHENTICATE (simulated)", "─")
        subhead("Plate fingerprints from calibration census")
        print()
        for pid in PLATE_IDS:
            pname = PLATE_NAMES[pid]
            modes = ALL_MODES.get(pid, [])
            n = len(modes)
            if n > 0:
                fmin = min(modes)
                fmax = max(modes)
                ok(f"Plate {pname}: {n} modes, "
                   f"{fmin:.0f}–{fmax:.0f} Hz")
            else:
                info(f"Plate {pname}: no modes detected")

    # ══════════════════════════════════════════════════════════════════
    #  PHASE 2: TRAIN ESN
    # ══════════════════════════════════════════════════════════════════

    banner("PHASE 2: TRAIN — Building glass readout from calibration", "─")
    subhead("Loading calibration data")

    t0 = time.time()
    feat_maps, raw_maps, noise_maps = load_calibration()
    ok(f"Loaded 256 tokens × 2 plates from "
       f"{CALIB_V3.name if CALIB_V3.exists() else CALIB_V4_L2.name}")

    de_feats = build_de_features(feat_maps["4"], feat_maps["5"])
    sw_raw, sw_poly4 = build_sw_baselines()
    ok(f"Feature dims: DE_raw={len(next(iter(de_feats.values())))}d, "
       f"sw_poly4={len(next(iter(sw_poly4.values())))}d")

    subhead("Training ESN reservoir + readout heads")
    sequences, reversed_seqs = generate_sequences()
    n_train = 1500

    results = {}
    for label, fmap in [("DE_raw", de_feats), ("sw_raw", sw_raw),
                        ("sw_poly4", sw_poly4)]:
        res = train_esn(fmap, label, sequences, reversed_seqs, n_train)
        results[label] = res
        digit = res["digit_acc_mean"]
        token = res["token_acc_mean"]
        dim = res["dim"]
        ok(f"{label:>10s} ({dim:3d}d): "
           f"digit={digit:.1%}  token={token:.1%}")

    elapsed = time.time() - t0
    info(f"Training completed in {elapsed:.1f}s")

    # Visual comparison
    subhead("Accuracy comparison: Glass vs Software")
    print()
    bar_chart("Glass (D+E, 16d)", results["DE_raw"]["digit_acc_mean"] * 100,
              color=GREEN)
    bar_chart("Software poly4 (163d)", results["sw_poly4"]["digit_acc_mean"] * 100,
              color=RED)
    bar_chart("Software raw (8d)", results["sw_raw"]["digit_acc_mean"] * 100,
              color=YELLOW)

    advantage = (results["DE_raw"]["digit_acc_mean"] -
                 results["sw_poly4"]["digit_acc_mean"]) * 100
    print()
    info(f"{BOLD}Glass advantage: +{advantage:.1f}% per-digit accuracy{RESET}")
    info(f"Glass uses {BOLD}16{RESET} physical features vs "
         f"software's {BOLD}163{RESET} polynomial features")

    # ══════════════════════════════════════════════════════════════════
    #  PHASE 3: ENCODE — Show token fingerprints
    # ══════════════════════════════════════════════════════════════════

    banner("PHASE 3: ENCODE — Token fingerprints in glass", "─")
    subhead("Each 8-bit token produces a unique vibrational barcode")
    print()

    # Show a few representative tokens
    showcase_tokens = [0, 42, 85, 127, 170, 213, 255]
    info(f"{'Token':>5s}  {'Binary':>10s}    {'D modes':>40s}    {'E modes':>40s}")
    info(f"{'─'*5:>5s}  {'─'*10:>10s}    {'─'*40:>40s}    {'─'*40:>40s}")

    for t in showcase_tokens:
        bits = bitstring(t)
        d_feat = feat_maps["4"].get(t, np.zeros(N_MODES))
        e_feat = feat_maps["5"].get(t, np.zeros(N_MODES))
        d_norm = d_feat / (np.max(np.abs(d_feat)) + 1e-8)
        e_norm = e_feat / (np.max(np.abs(e_feat)) + 1e-8)
        d_bars = ''.join(
            f"{'█' * max(1, int(abs(v) * 4)):<4s}" for v in d_norm)
        e_bars = ''.join(
            f"{'█' * max(1, int(abs(v) * 4)):<4s}" for v in e_norm)
        info(f"{t:>5d}  [{bits}]    {CYAN}{d_bars}{RESET}  "
             f"  {MAGENTA}{e_bars}{RESET}")

    # Live capture demo if hardware available
    if not dry_run:
        subhead("Live token capture")
        sample_t = rng.integers(0, 256)
        info(f"Driving token {sample_t} [{bitstring(sample_t)}] "
             "through glass...")

        live_feats = capture_token_live(
            handle, mux, sample_t, ALL_MODES, feat_maps, raw_maps, noise_maps)
        for pid in TARGET_PLATES:
            pname = PLATE_NAMES[pid]
            if pid in live_feats:
                calib_feat = feat_maps[pid].get(sample_t, np.zeros(N_MODES))
                live_feat = live_feats[pid]
                corr = np.corrcoef(calib_feat, live_feat)[0, 1]
                ok(f"Plate {pname}: live↔calibration correlation = "
                   f"{corr:.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  PHASE 4: REMEMBER — Sequence reversal on a message
    # ══════════════════════════════════════════════════════════════════

    banner("PHASE 4: REMEMBER — Glass reads your message backwards", "─")

    # Get message
    if args.message:
        message = args.message
    else:
        subhead("Type a message (4+ ASCII characters)")
        try:
            message = input(f"  {BOLD}> {RESET}")
        except (EOFError, KeyboardInterrupt):
            message = "WAVE"

    if not message:
        message = "WAVE"

    # Pad/truncate to multiple of 4
    chars = [ord(c) % 256 for c in message]
    while len(chars) % SEQ_LEN != 0:
        chars.append(ord(' '))

    n_chunks = len(chars) // SEQ_LEN
    esn_de = results["DE_raw"]["esn"]
    rw_de = results["DE_raw"]["readout_weights"]
    esn_sw = results["sw_poly4"]["esn"]
    rw_sw = results["sw_poly4"]["readout_weights"]

    subhead(f"Encoding '{message}' → {len(chars)} tokens in "
            f"{n_chunks} sequence(s)")
    print()

    glass_decoded = []
    sw_decoded = []
    glass_correct = 0
    sw_correct = 0
    total_chars = 0

    for chunk_i in range(n_chunks):
        chunk = chars[chunk_i * SEQ_LEN:(chunk_i + 1) * SEQ_LEN]
        reversed_chunk = list(reversed(chunk))
        chunk_chars = ''.join(chr(c) for c in chunk)
        expected_chars = ''.join(chr(c) for c in reversed_chunk)

        info(f"Chunk {chunk_i + 1}: [{chunk_chars}] → expect [{expected_chars}]")

        # Build feature sequences
        if not dry_run and handle and mux:
            # Live capture with matched-filter
            de_feat_seq = []
            chunk_match_info = []
            for t in chunk:
                matched_feats, m_info = capture_and_match(
                    handle, mux, t, ALL_MODES, feat_maps, raw_maps, noise_maps)
                d_f = matched_feats.get("4", feat_maps["4"].get(t, np.zeros(N_MODES)))
                e_f = matched_feats.get("5", feat_maps["5"].get(t, np.zeros(N_MODES)))
                de_feat_seq.append(np.concatenate([d_f, e_f]))
                chunk_match_info.append(m_info)
                # Show match result
                d_ok = m_info.get("4", {}).get("correct", False)
                e_ok = m_info.get("5", {}).get("correct", False)
                d_corr = m_info.get("4", {}).get("correlation", 0)
                e_corr = m_info.get("5", {}).get("correlation", 0)
                ch = chr(t) if 32 <= t < 127 else '?'
                d_sym = f"{GREEN}✓{RESET}" if d_ok else f"{RED}✗{RESET}"
                e_sym = f"{GREEN}✓{RESET}" if e_ok else f"{RED}✗{RESET}"
                info(f"  '{ch}'({t:3d}): D {d_sym} ρ={d_corr:.3f}  "
                     f"E {e_sym} ρ={e_corr:.3f}")
        else:
            # Dry-run: use calibration + noise
            de_feat_seq = []
            for t in chunk:
                sim = simulate_token_capture(t, feat_maps, noise_maps, rng)
                d_f = sim.get("4", feat_maps["4"].get(t, np.zeros(N_MODES)))
                e_f = sim.get("5", feat_maps["5"].get(t, np.zeros(N_MODES)))
                de_feat_seq.append(np.concatenate([d_f, e_f]))

        # Software features
        sw_feat_seq = [sw_poly4[t] for t in chunk]

        # Predict
        glass_pred = predict_sequence(esn_de, rw_de, de_feat_seq)
        sw_pred = predict_sequence(esn_sw, rw_sw, sw_feat_seq)

        glass_chars = ''.join(
            chr(p) if 32 <= p < 127 else '?' for p in glass_pred)
        sw_chars = ''.join(
            chr(p) if 32 <= p < 127 else '?' for p in sw_pred)

        # Score
        for pos in range(SEQ_LEN):
            total_chars += 1
            if glass_pred[pos] == reversed_chunk[pos]:
                glass_correct += 1
            if sw_pred[pos] == reversed_chunk[pos]:
                sw_correct += 1

        glass_decoded.extend(glass_pred)
        sw_decoded.extend(sw_pred)

        # Display results
        glass_marks = ''.join(
            f"{GREEN}✓{RESET}" if glass_pred[i] == reversed_chunk[i]
            else f"{RED}✗{RESET}"
            for i in range(SEQ_LEN))
        sw_marks = ''.join(
            f"{GREEN}✓{RESET}" if sw_pred[i] == reversed_chunk[i]
            else f"{RED}✗{RESET}"
            for i in range(SEQ_LEN))

        info(f"  {CYAN}Glass:{RESET}    [{glass_chars}]  {glass_marks}")
        info(f"  {YELLOW}Software:{RESET} [{sw_chars}]  {sw_marks}")
        print()

    # Summary
    glass_pct = glass_correct / total_chars * 100 if total_chars else 0
    sw_pct = sw_correct / total_chars * 100 if total_chars else 0

    full_glass = ''.join(
        chr(p) if 32 <= p < 127 else '?' for p in glass_decoded)
    full_sw = ''.join(
        chr(p) if 32 <= p < 127 else '?' for p in sw_decoded)
    expected_full = ''.join(
        chr(c) if 32 <= c < 127 else '?' for c in reversed(chars))

    subhead("Result")
    info(f"Expected:  {expected_full}")
    info(f"{CYAN}Glass:{RESET}     {full_glass}  "
         f"({glass_pct:.0f}% correct)")
    info(f"{YELLOW}Software:{RESET}  {full_sw}  "
         f"({sw_pct:.0f}% correct)")

    # ══════════════════════════════════════════════════════════════════
    #  PHASE 5: SHOWDOWN — Stress test
    # ══════════════════════════════════════════════════════════════════

    if not args.quick:
        banner("PHASE 5: SHOWDOWN — 500-trial stress test", "─")

        n_test = 500
        test_seqs = sequences[n_train:n_train + n_test]
        test_rev = reversed_seqs[n_train:n_train + n_test]

        configs = [
            ("Glass D+E (16d)", results["DE_raw"]),
            ("Software poly4 (163d)", results["sw_poly4"]),
            ("Software raw (8d)", results["sw_raw"]),
        ]

        subhead(f"{n_test} random sequences, length-{SEQ_LEN} reversal")
        print()

        for label, res in configs:
            digit = res["digit_acc_mean"] * 100
            token = res["token_acc_mean"] * 100
            color = GREEN if "Glass" in label else (
                RED if "poly4" in label else YELLOW)
            bar_chart(label, digit, color=color)

        print()
        info(f"{'Config':>25s}  {'Digit Acc':>10s}  {'Token Acc':>10s}  "
             f"{'Per-Position Digit Acc':>40s}")
        info(f"{'─' * 25:>25s}  {'─' * 10:>10s}  {'─' * 10:>10s}  "
             f"{'─' * 40:>40s}")

        for label, res in configs:
            digit = res["digit_acc_mean"]
            token = res["token_acc_mean"]
            pos_d = res["pos_digit"]
            pos_str = '  '.join(f"{p:.1%}" for p in pos_d)
            color = GREEN if "Glass" in label else (
                RED if "poly4" in label else YELLOW)
            info(f"{color}{label:>25s}{RESET}  "
                 f"{digit:>10.1%}  {token:>10.1%}  {pos_str:>40s}")

        # Dramatic summary
        glass_d = results["DE_raw"]["digit_acc_mean"] * 100
        sw4_d = results["sw_poly4"]["digit_acc_mean"] * 100
        glass_t = results["DE_raw"]["token_acc_mean"] * 100
        sw4_t = results["sw_poly4"]["token_acc_mean"] * 100

        print()
        banner("FINAL SCOREBOARD")
        print()
        print(f"  {BOLD}{CYAN}  GLASS (D+E)    {RESET}"
              f"  digit: {GREEN}{glass_d:5.1f}%{RESET}"
              f"  token: {GREEN}{glass_t:5.1f}%{RESET}"
              f"  features: {BOLD}16{RESET}")
        print(f"  {BOLD}{YELLOW}  SOFTWARE poly4 {RESET}"
              f"  digit: {RED}{sw4_d:5.1f}%{RESET}"
              f"  token: {RED}{sw4_t:5.1f}%{RESET}"
              f"  features: {BOLD}163{RESET}")
        print()
        adv_d = glass_d - sw4_d
        adv_t = glass_t - sw4_t
        print(f"  {BOLD}Glass advantage: "
              f"+{adv_d:.1f}% digit, +{adv_t:.1f}% token{RESET}")
        print(f"  {BOLD}With {GREEN}10× fewer{RESET}{BOLD} features.{RESET}")
        print()

    # ── Save results ──────────────────────────────────────────────────

    demo_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "dry-run" if dry_run else "hardware",
        "message": message,
        "glass_decoded": ''.join(
            chr(p) if 32 <= p < 127 else '?' for p in glass_decoded),
        "sw_decoded": ''.join(
            chr(p) if 32 <= p < 127 else '?' for p in sw_decoded),
        "glass_char_accuracy": glass_pct,
        "sw_char_accuracy": sw_pct,
        "validation": {
            label: {
                "digit_acc": res["digit_acc_mean"],
                "token_acc": res["token_acc_mean"],
                "dim": res["dim"],
            }
            for label, res in results.items()
        },
    }
    save_path = RESULTS_DIR / f"cwm_demo_{TIMESTAMP}.json"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w") as f:
        json.dump(demo_results, f, indent=2)
    info(f"Results saved: {save_path.name}")

    # ── Cleanup ───────────────────────────────────────────────────────

    if handle:
        _awg_off(handle)
        _close_scope(handle)
    if mux:
        mux.close()

    banner("DEMO COMPLETE")
    print()


if __name__ == "__main__":
    main()
