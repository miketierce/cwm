#!/usr/bin/env python3
"""
Plate Attention Head — Physical Self-Attention via CWM Plates

Demonstrates a single-head self-attention forward pass where the expensive
matrix-vector multiplies (Q·K^T and attn_weights·V) are offloaded to the
physical plate, which computes y = H · x via wave interference.

Architecture (mirrors llm-from-scratch / Attention-11):
  1. Token + position embeddings (digital, random init or loaded)
  2. Q, K, V linear projections (digital)
  3. Q·K^T attention scores (PLATE — one mat-vec per query position)
  4. Softmax (digital)
  5. attn_weights · V context mixing (PLATE — one mat-vec per query position)
  6. Output projection (digital)
  7. Compare to pure-software ground truth → R², correlation

The plate acts as a physical matrix multiplier for steps 3 and 5.
Everything else stays digital (laptop CPU).

Two modes:
  --simulate   Use census-derived synthetic transfer matrix (no hardware)
  --hardware   Drive real plate via Kronos, characterize H, then use it

The sequence reversal task from Dave's PDP-11 video is used as the test
problem: input [4,7,4,9,6,3,5,X] → predict reversed output.

Usage:
  # Software validation (no hardware needed):
  python tools/plate_attention_head.py --simulate

  # Full hardware run:
  python tools/plate_attention_head.py --hardware --device KRONOS \\
      --port /dev/cu.usbserial-11310 --plate 5

  # Custom sequence length and embedding dim:
  python tools/plate_attention_head.py --simulate --seq-len 4 --d-model 8
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

RESULTS_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Plate config ──
PLATE_NAMES = {"1": "A", "2": "B", "3": "G", "4": "D", "5": "H"}
PLATE_RELAYS = {
    "1": [(1, "NE")],
    "2": [(2, "NE")],
    "3": [(3, "NE"), (4, "NW")],
    "4": [(5, "NE"), (6, "NW")],
    "5": [(7, "NE"), (8, "NW")],
}

# Audio config
DRIVE_AMPLITUDE = 0.8
SETTLE_RELAY_S = 0.10
USB_LATENCY_S = 0.25
AUDIO_DTYPE = "float32"
PREFERRED_SAMPLE_RATES = [192000, 96000, 48000, 44100]
FIXTURE_FREQ_HZ = 6700.0
FIXTURE_GUARD_HZ = 200.0
N_AVG = 4


# ═══════════════════════════════════════════════════════════════════════
#  SOFTWARE ATTENTION (ground truth)
# ═══════════════════════════════════════════════════════════════════════

def softmax(x: np.ndarray) -> np.ndarray:
    """Numerically stable softmax along last axis."""
    e = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return e / np.sum(e, axis=-1, keepdims=True)


def software_attention_head(X: np.ndarray, W_q: np.ndarray, W_k: np.ndarray,
                            W_v: np.ndarray, W_o: np.ndarray,
                            causal: bool = True) -> dict:
    """Pure-software single-head self-attention.

    X:   (T, d_model) — input embeddings (token + position)
    W_q: (d_model, d_k) — query projection
    W_k: (d_model, d_k) — key projection
    W_v: (d_model, d_v) — value projection
    W_o: (d_v, d_model)  — output projection

    Returns dict with all intermediates for comparison.
    """
    T, d_model = X.shape
    Q = X @ W_q          # (T, d_k)
    K = X @ W_k          # (T, d_k)
    V = X @ W_v          # (T, d_v)

    d_k = Q.shape[1]

    # Attention scores: Q · K^T / sqrt(d_k)
    scores = (Q @ K.T) / math.sqrt(d_k)   # (T, T)

    if causal:
        mask = np.triu(np.ones((T, T), dtype=bool), k=1)
        scores = np.where(mask, -1e9, scores)

    attn_weights = softmax(scores)           # (T, T)

    # Context: attn_weights · V
    context = attn_weights @ V               # (T, d_v)

    # Output projection
    output = context @ W_o                   # (T, d_model)

    return {
        "Q": Q, "K": K, "V": V,
        "scores": scores,
        "attn_weights": attn_weights,
        "context": context,
        "output": output,
    }


# ═══════════════════════════════════════════════════════════════════════
#  PLATE-HYBRID ATTENTION (mat-vec via plate transfer matrix)
# ═══════════════════════════════════════════════════════════════════════

def plate_matvec(H: np.ndarray, x: np.ndarray, d_target: int) -> np.ndarray:
    """Use plate transfer matrix H to compute a matrix-vector product.

    H is (N_modes, N_modes) from the physical plate.
    x is a vector of length d_target.

    Strategy: embed x into the plate's mode space (zero-pad or truncate),
    multiply by H, then extract the first d_target components.
    """
    n_modes = H.shape[0]

    if len(x) <= n_modes:
        # Pad x to plate dimension
        x_padded = np.zeros(n_modes)
        x_padded[:len(x)] = x
    else:
        # Truncate (should not happen in well-designed experiment)
        x_padded = x[:n_modes]

    # Physical multiply
    y_full = H @ x_padded

    # Extract result
    return y_full[:d_target]


def plate_matmul(H: np.ndarray, A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Compute A @ B using plate for each column of B (i.e., each mat-vec).

    A: (M, N)  — treated as the "weight matrix" encoded in plate H
    B: (N, P)  — each column is a vector to multiply

    In practice: we can't load A into the plate dynamically.
    Instead, we use H as the fixed weight matrix and compute H @ b_j
    for each column b_j of B.

    For attention: we need Q @ K^T where rows of Q are queries.
    We compute this as: for each query q_i, compute H @ q_i
    where H encodes the key matrix.

    Returns: (M, P) result matrix.
    """
    M, N = A.shape
    N2, P = B.shape
    n_modes = H.shape[0]

    result = np.zeros((M, P))
    for j in range(P):
        result[:, j] = plate_matvec(H, B[:, j], M)

    return result


def plate_attention_head(X: np.ndarray, W_q: np.ndarray, W_k: np.ndarray,
                         W_v: np.ndarray, W_o: np.ndarray,
                         H_attn: np.ndarray, H_context: np.ndarray,
                         causal: bool = True,
                         hardware_fn=None) -> dict:
    """Single-head attention with plate-accelerated mat-mul.

    Steps done digitally: Q/K/V projections, softmax, output projection
    Steps done on plate:  Q·K^T scores, attn_weights·V context

    H_attn:    plate transfer matrix used for Q·K^T
    H_context: plate transfer matrix used for attn·V (can be same plate)
    hardware_fn: if provided, called as hardware_fn(x_vec) for each mat-vec
                 instead of using H directly. This is the live plate path.
    """
    T, d_model = X.shape

    # ── Digital: Q, K, V projections ──
    Q = X @ W_q   # (T, d_k)
    K = X @ W_k   # (T, d_k)
    V = X @ W_v   # (T, d_v)

    d_k = Q.shape[1]

    # ── PLATE: Q · K^T / sqrt(d_k) ──
    # For each query position i, compute q_i · k_j for all j
    # This is T mat-vecs: score_row_i = K^T @ q_i (plate computes K^T @ q_i)
    #
    # BUT: the plate's H is fixed. We can't load K^T into the plate.
    # So we use H as an approximation of K^T (or compute K^T @ q_i digitally
    # for the projection and use the plate for the heavy multiply).
    #
    # Practical approach: use the plate's transfer matrix as the attention
    # kernel itself. The plate modes naturally "attend to" different frequency
    # positions — this IS a physical attention mechanism.
    #
    # Alternative (what we implement): compute Q·K^T column-by-column
    # through the plate, where H serves as the multiply engine.

    n_modes = H_attn.shape[0]

    if hardware_fn is not None:
        # Live hardware path: drive each key vector, measure response
        scores = np.zeros((T, T))
        for i in range(T):
            # Each query q_i needs dot products with all keys
            # We encode the query as drive amplitudes, plate computes H @ q
            # Then correlate with each key
            plate_response = hardware_fn(Q[i])
            for j in range(T):
                # Approximate q_i · k_j via plate response correlation
                scores[i, j] = np.dot(plate_response[:d_k], K[j])
        scores = scores / math.sqrt(d_k)
    else:
        # Simulated plate path: use H for the multiply
        scores = np.zeros((T, T))
        for i in range(T):
            # Route q_i through plate → H @ q_i, then dot with each k_j
            hq = plate_matvec(H_attn, Q[i], d_k)
            for j in range(T):
                scores[i, j] = np.dot(hq, K[j])
        scores = scores / math.sqrt(d_k)

    if causal:
        mask = np.triu(np.ones((T, T), dtype=bool), k=1)
        scores = np.where(mask, -1e9, scores)

    # ── Digital: softmax ──
    attn_weights = softmax(scores)

    # ── PLATE: attn_weights · V ──
    # For each position i, compute sum_j(attn_ij * v_j)
    # This is a weighted sum — plate computes H @ attn_row_i,
    # and we interpret the output as the context vector.
    d_v = V.shape[1]

    if hardware_fn is not None:
        context = np.zeros((T, d_v))
        for i in range(T):
            # Encode attn weights as drive amplitudes
            plate_response = hardware_fn(attn_weights[i])
            # Weight the value vectors
            weighted_v = np.zeros(d_v)
            for j in range(T):
                weighted_v += plate_response[j] * V[j] if j < len(plate_response) else 0
            context[i] = weighted_v
    else:
        context = np.zeros((T, d_v))
        for i in range(T):
            # Route attention weights through plate
            h_attn = plate_matvec(H_context, attn_weights[i], T)
            # Weighted sum of value vectors
            for j in range(T):
                if j < len(h_attn):
                    context[i] += h_attn[j] * V[j]

    # ── Digital: output projection ──
    output = context @ W_o

    return {
        "Q": Q, "K": K, "V": V,
        "scores": scores,
        "attn_weights": attn_weights,
        "context": context,
        "output": output,
    }


# ═══════════════════════════════════════════════════════════════════════
#  TRANSFER MATRIX CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════

def load_census_modes(census_path: str, plate_key: str) -> list[float]:
    """Load mode frequencies from census JSON."""
    with open(census_path) as f:
        data = json.load(f)
    results = data.get("results", {})
    for key in [plate_key, f"{plate_key}_NE", f"{plate_key}_NW"]:
        if key in results:
            peaks = results[key].get("peaks", [])
            if peaks:
                freqs = sorted([p["freq_hz"] for p in peaks])
                lo = FIXTURE_FREQ_HZ - FIXTURE_GUARD_HZ
                hi = FIXTURE_FREQ_HZ + FIXTURE_GUARD_HZ
                return [f for f in freqs if not (lo <= f <= hi)]
    raise ValueError(f"No modes for plate key '{plate_key}' in {census_path}")


def synthetic_transfer_matrix(n_modes: int, seed: int = 42,
                              coupling_strength: float = 0.05) -> np.ndarray:
    """Build a synthetic plate transfer matrix for simulation.

    Models the physical plate's measured transfer matrix H from E10:
    - Strong diagonal (self-response) with R² = 0.96–1.00
    - Weak off-diagonal coupling (cross-mode leakage)
    - The coupling_strength parameter controls off-diagonal magnitude
      (0.05 matches the E10 dense-regime R² ≈ 0.97)

    The sin²(nπx/L) sensitivity gives the coupling pattern; we scale
    it down to match measured plate behavior.
    """
    rng = np.random.default_rng(seed)
    H = np.eye(n_modes)
    for i in range(n_modes):
        for j in range(n_modes):
            if i != j:
                # Cross-mode coupling: small sin² leakage
                coupling = np.sin(np.pi * (i + 1) * (j + 1) / (n_modes + 1)) ** 2
                H[i, j] = coupling_strength * coupling
    # Add measurement noise (matches real plate FFT noise floor)
    H += rng.normal(0, 0.002, H.shape)
    # Ensure positive (physical magnitudes)
    H = np.abs(H)
    return H


def identity_like_transfer_matrix(n: int) -> np.ndarray:
    """Perfect identity — plate that passes signals unchanged.
    Useful as a sanity check: plate attention should match software exactly.
    """
    return np.eye(n)


# ═══════════════════════════════════════════════════════════════════════
#  HARDWARE INTERFACE (Kronos)
# ═══════════════════════════════════════════════════════════════════════

def find_audio_device(name_hint: str) -> int:
    import sounddevice as sd
    for i, dev in enumerate(sd.query_devices()):
        if (name_hint.lower() in dev["name"].lower()
                and dev["max_input_channels"] > 0
                and dev["max_output_channels"] > 0):
            return i
    raise RuntimeError(f"No audio device matching '{name_hint}' with I/O.")


def detect_sample_rate(device_idx: int) -> int:
    import sounddevice as sd
    for rate in PREFERRED_SAMPLE_RATES:
        try:
            sd.check_input_settings(device=device_idx, channels=1,
                                    dtype=AUDIO_DTYPE, samplerate=rate)
            sd.check_output_settings(device=device_idx, channels=1,
                                     dtype=AUDIO_DTYPE, samplerate=rate)
            return rate
        except Exception:
            continue
    return int(sd.query_devices(device_idx)["default_samplerate"])


def characterize_plate_H(mode_freqs: list[float], sample_rate: int,
                         device_idx: int, mux, relay_ch: int,
                         n_avg: int = N_AVG) -> np.ndarray:
    """Measure the plate's transfer matrix H via Kronos.

    Drive each mode frequency solo, measure response at all mode frequencies.
    H[i,j] = response at mode_freq[i] when driving mode_freq[j].
    """
    import sounddevice as sd

    n = len(mode_freqs)
    H = np.zeros((n, n))

    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    print(f"  Characterizing {n}×{n} transfer matrix H...")
    t0 = time.time()

    for j, drive_f in enumerate(mode_freqs):
        # Build single-tone TX signal
        total_dur = USB_LATENCY_S + 0.2
        n_samples = int(sample_rate * total_dur)
        t = np.arange(n_samples) / sample_rate
        sig = DRIVE_AMPLITUDE * np.sin(2 * np.pi * drive_f * t)
        tx = sig.astype(np.float32).reshape(-1, 1)

        mags_sum = np.zeros(n)
        for _ in range(n_avg):
            rx = sd.playrec(tx, samplerate=sample_rate,
                            input_mapping=[1], output_mapping=[1],
                            device=device_idx, dtype=AUDIO_DTYPE, blocking=True)
            rx_mono = rx[:, 0].astype(np.float64)
            settle = int(sample_rate * USB_LATENCY_S)
            rx_capture = rx_mono[settle:]

            windowed = rx_capture * np.hanning(len(rx_capture))
            nfft = len(rx_capture) * 4
            spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
            bin_hz = freq_axis[1]

            for i, read_f in enumerate(mode_freqs):
                tb = int(round(read_f / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(spectrum) - 1, tb + 3)
                mags_sum[i] += float(np.max(spectrum[lo:hi + 1]))

        H[:, j] = mags_sum / n_avg

        if (j + 1) % 10 == 0 or j == n - 1:
            elapsed = time.time() - t0
            print(f"    [{j+1}/{n}] {elapsed:.0f}s", flush=True)

    print(f"  H characterized in {time.time()-t0:.1f}s")
    return H


def make_hardware_fn(mode_freqs: list[float], sample_rate: int,
                     device_idx: int) -> callable:
    """Create a function that drives the plate with an amplitude vector
    and returns the measured response vector."""
    import sounddevice as sd

    def hw_fn(x_vec: np.ndarray) -> np.ndarray:
        n = len(mode_freqs)
        # Truncate or pad
        amps = np.zeros(n)
        amps[:min(len(x_vec), n)] = x_vec[:min(len(x_vec), n)]

        # Build multitone TX
        total_dur = USB_LATENCY_S + 0.2
        n_samples = int(sample_rate * total_dur)
        t = np.arange(n_samples) / sample_rate
        sig = np.zeros(n_samples, dtype=np.float64)
        for i, (f, a) in enumerate(zip(mode_freqs, amps)):
            if abs(a) > 0.001:
                sig += a * np.sin(2 * np.pi * f * t)
        peak = np.max(np.abs(sig))
        if peak > 0:
            sig *= DRIVE_AMPLITUDE / peak
        tx = sig.astype(np.float32).reshape(-1, 1)

        mags_sum = np.zeros(n)
        for _ in range(N_AVG):
            rx = sd.playrec(tx, samplerate=sample_rate,
                            input_mapping=[1], output_mapping=[1],
                            device=device_idx, dtype=AUDIO_DTYPE, blocking=True)
            rx_mono = rx[:, 0].astype(np.float64)
            settle = int(sample_rate * USB_LATENCY_S)
            rx_capture = rx_mono[settle:]

            windowed = rx_capture * np.hanning(len(rx_capture))
            nfft = len(rx_capture) * 4
            spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
            bin_hz = freq_axis[1]

            for i, read_f in enumerate(mode_freqs):
                tb = int(round(read_f / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(spectrum) - 1, tb + 3)
                mags_sum[i] += float(np.max(spectrum[lo:hi + 1]))

        return mags_sum / N_AVG

    return hw_fn


# ═══════════════════════════════════════════════════════════════════════
#  EXPERIMENT: SEQUENCE REVERSAL (Dave's PDP-11 task)
# ═══════════════════════════════════════════════════════════════════════

def build_reversal_problem(seq_len: int = 8, vocab_size: int = 10,
                           d_model: int = 16, seed: int = 42) -> dict:
    """Build a sequence reversal problem matching Attention-11.

    Returns embeddings and weight matrices for a single-head transformer.
    """
    rng = np.random.default_rng(seed)

    # Random input sequence (digits 0-9)
    input_seq = rng.integers(0, vocab_size, size=seq_len)
    target_seq = input_seq[::-1]

    # Learned embeddings (random init — we're testing the forward pass,
    # not training)
    W_tok = rng.normal(0, 0.1, (vocab_size, d_model))   # token embedding
    W_pos = rng.normal(0, 0.1, (seq_len, d_model))      # position embedding

    # Input embeddings: token + position
    X = np.zeros((seq_len, d_model))
    for t in range(seq_len):
        X[t] = W_tok[input_seq[t]] + W_pos[t]

    # Projection matrices
    d_k = d_model  # single head: d_k = d_v = d_model
    d_v = d_model
    W_q = rng.normal(0, 0.1, (d_model, d_k))
    W_k = rng.normal(0, 0.1, (d_model, d_k))
    W_v = rng.normal(0, 0.1, (d_model, d_v))
    W_o = rng.normal(0, 0.1, (d_v, d_model))

    return {
        "input_seq": input_seq,
        "target_seq": target_seq,
        "X": X,
        "W_q": W_q, "W_k": W_k, "W_v": W_v, "W_o": W_o,
        "d_model": d_model, "d_k": d_k, "d_v": d_v,
        "seq_len": seq_len, "vocab_size": vocab_size,
    }


# ═══════════════════════════════════════════════════════════════════════
#  COMPARISON METRICS
# ═══════════════════════════════════════════════════════════════════════

def compare_outputs(sw: dict, plate: dict, label: str = "") -> dict:
    """Compare software vs plate attention outputs."""
    metrics = {}
    for key in ["scores", "attn_weights", "context", "output"]:
        sw_val = sw[key]
        pl_val = plate[key]

        # R²
        ss_res = np.sum((sw_val - pl_val) ** 2)
        ss_tot = np.sum((sw_val - np.mean(sw_val)) ** 2)
        r2 = 1.0 - ss_res / (ss_tot + 1e-12)

        # Correlation
        if sw_val.size > 1 and np.std(sw_val) > 0 and np.std(pl_val) > 0:
            corr = float(np.corrcoef(sw_val.ravel(), pl_val.ravel())[0, 1])
        else:
            corr = 0.0

        # RMSE
        rmse = float(np.sqrt(np.mean((sw_val - pl_val) ** 2)))

        # Max abs error
        max_err = float(np.max(np.abs(sw_val - pl_val)))

        metrics[key] = {
            "r_squared": round(r2, 6),
            "correlation": round(corr, 6),
            "rmse": round(rmse, 6),
            "max_error": round(max_err, 6),
        }

    return metrics


# ═══════════════════════════════════════════════════════════════════════
#  MAIN EXPERIMENT RUNNER
# ═══════════════════════════════════════════════════════════════════════

def run_experiment(args):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "hardware" if args.hardware else "simulate"
    seq_len = args.seq_len
    d_model = args.d_model

    print("\n" + "=" * 70)
    print(f"  PLATE ATTENTION HEAD EXPERIMENT")
    print(f"  Mode: {mode.upper()}")
    print(f"  Sequence length: {seq_len}")
    print(f"  Model dimension: {d_model}")
    print(f"  Task: {seq_len}-digit reversal (Attention-11 style)")
    print("=" * 70)

    # ── Step 1: Build the reversal problem ──
    print(f"\n  Step 1: Building reversal problem...")
    problem = build_reversal_problem(
        seq_len=seq_len, vocab_size=10, d_model=d_model, seed=args.seed
    )
    print(f"    Input:  {list(problem['input_seq'])}")
    print(f"    Target: {list(problem['target_seq'])}")
    print(f"    X shape: {problem['X'].shape}")

    # ── Step 2: Software ground truth ──
    print(f"\n  Step 2: Software attention (ground truth)...")
    t0 = time.time()
    sw_result = software_attention_head(
        problem["X"], problem["W_q"], problem["W_k"],
        problem["W_v"], problem["W_o"], causal=not args.no_causal
    )
    sw_time = time.time() - t0
    print(f"    Done in {sw_time*1000:.1f} ms")
    print(f"    Attention weights (row 0): "
          f"{np.round(sw_result['attn_weights'][0], 3)}")
    print(f"    Output norm: {np.linalg.norm(sw_result['output']):.4f}")

    # ── Step 3: Build or measure plate transfer matrix ──
    H_attn = None
    H_context = None
    hardware_fn = None

    if args.hardware:
        print(f"\n  Step 3: Characterizing real plate via Kronos...")
        from relay_mux import RelayMux

        device_idx = find_audio_device(args.device)
        sample_rate = detect_sample_rate(device_idx)
        print(f"    Audio device: {args.device}, {sample_rate} Hz")

        # Load census modes
        census_path = args.census
        if census_path is None:
            # Find latest census
            census_files = sorted(RESULTS_DIR.glob("plate_census_2*.json"))
            if not census_files:
                print("ERROR: No census file found. Run plate_census_kronos.py first.")
                sys.exit(1)
            census_path = str(census_files[-1])
        plate_key = args.plate
        mode_freqs = load_census_modes(census_path, plate_key)

        # Limit modes to d_model (we need at least d_model modes)
        if len(mode_freqs) < d_model:
            print(f"  WARNING: plate has {len(mode_freqs)} modes but "
                  f"d_model={d_model}. Reducing d_model.")
            d_model = len(mode_freqs)
            # Rebuild problem with reduced d_model
            problem = build_reversal_problem(
                seq_len=seq_len, vocab_size=10, d_model=d_model, seed=args.seed
            )
            sw_result = software_attention_head(
                problem["X"], problem["W_q"], problem["W_k"],
                problem["W_v"], problem["W_o"], causal=not args.no_causal
            )

        mode_freqs = mode_freqs[:d_model]
        print(f"    Using {len(mode_freqs)} modes (d_model={d_model})")
        print(f"    Freq range: {mode_freqs[0]/1000:.1f} – "
              f"{mode_freqs[-1]/1000:.1f} kHz")

        relay_ch = PLATE_RELAYS[plate_key][0][0]
        mux = RelayMux(port=args.port)
        mux.open()

        # Characterize transfer matrix
        H_attn = characterize_plate_H(
            mode_freqs, sample_rate, device_idx, mux, relay_ch
        )
        H_context = H_attn  # Same plate for both operations

        if args.live:
            hardware_fn = make_hardware_fn(mode_freqs, sample_rate, device_idx)
            print(f"    Live hardware mode: each mat-vec drives the plate")

        # Normalize H to have unit diagonal (so it approximates identity)
        diag = np.diag(H_attn)
        if np.min(diag) > 0:
            D_inv = np.diag(1.0 / diag)
            H_attn = D_inv @ H_attn
            H_context = D_inv @ H_context
            print(f"    H normalized (diag→1, off-diag mean: "
                  f"{np.mean(np.abs(H_attn - np.eye(d_model))):.4f})")
    else:
        print(f"\n  Step 3: Building synthetic plate transfer matrix...")

        if args.identity:
            H_attn = identity_like_transfer_matrix(d_model)
            H_context = H_attn
            print(f"    Using IDENTITY matrix (sanity check)")
        else:
            H_attn = synthetic_transfer_matrix(d_model, seed=args.seed + 100)
            H_context = H_attn

            # Normalize to unit diagonal
            diag = np.diag(H_attn)
            if np.min(diag) > 0:
                D_inv = np.diag(1.0 / diag)
                H_attn = D_inv @ H_attn
                H_context = D_inv @ H_context

            print(f"    Synthetic sin² matrix ({d_model}×{d_model})")
            print(f"    Off-diagonal mean: "
                  f"{np.mean(np.abs(H_attn - np.eye(d_model))):.4f}")

    # ── Step 4: Plate attention forward pass ──
    print(f"\n  Step 4: Plate attention forward pass...")
    t0 = time.time()
    plate_result = plate_attention_head(
        problem["X"], problem["W_q"], problem["W_k"],
        problem["W_v"], problem["W_o"],
        H_attn, H_context,
        causal=not args.no_causal,
        hardware_fn=hardware_fn,
    )
    plate_time = time.time() - t0
    print(f"    Done in {plate_time*1000:.1f} ms")
    print(f"    Attention weights (row 0): "
          f"{np.round(plate_result['attn_weights'][0], 3)}")
    print(f"    Output norm: {np.linalg.norm(plate_result['output']):.4f}")

    # ── Step 5: Compare ──
    print(f"\n  Step 5: Comparing software vs plate...")
    metrics = compare_outputs(sw_result, plate_result)

    print(f"\n  {'Component':<20} {'R²':>10} {'Correlation':>12} "
          f"{'RMSE':>10} {'Max Error':>10}")
    print(f"  {'─'*20} {'─'*10} {'─'*12} {'─'*10} {'─'*10}")
    for key, m in metrics.items():
        verdict = "✓" if m["r_squared"] > 0.90 else \
                  "~" if m["r_squared"] > 0.70 else "✗"
        print(f"  {key:<20} {m['r_squared']:>10.4f} {m['correlation']:>12.4f} "
              f"{m['rmse']:>10.4f} {m['max_error']:>10.4f}  {verdict}")

    # Overall verdict
    output_r2 = metrics["output"]["r_squared"]
    attn_r2 = metrics["attn_weights"]["r_squared"]
    print(f"\n  ── VERDICT ──")
    print(f"  Attention weights R²: {attn_r2:.4f}", end="")
    print(f"  {'PASS' if attn_r2 > 0.90 else 'MARGINAL' if attn_r2 > 0.70 else 'FAIL'}")
    print(f"  Output R²:            {output_r2:.4f}", end="")
    print(f"  {'PASS' if output_r2 > 0.90 else 'MARGINAL' if output_r2 > 0.70 else 'FAIL'}")

    if args.identity:
        print(f"\n  IDENTITY CHECK: output R² should be ≈1.0000")
        if output_r2 < 0.9999:
            print(f"  WARNING: identity matrix did not reproduce software! Bug?")

    # ── Step 6: Attention pattern analysis ──
    print(f"\n  Step 6: Attention pattern analysis...")
    print(f"\n  Software attention matrix:")
    for i in range(seq_len):
        row = sw_result["attn_weights"][i]
        bars = "".join([f"{v:5.2f}" for v in row])
        print(f"    pos {i} → [{bars}]")

    print(f"\n  Plate attention matrix:")
    for i in range(seq_len):
        row = plate_result["attn_weights"][i]
        bars = "".join([f"{v:5.2f}" for v in row])
        print(f"    pos {i} → [{bars}]")

    # ── Save results ──
    result = {
        "experiment": "plate_attention_head",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "config": {
            "seq_len": seq_len,
            "d_model": d_model,
            "vocab_size": 10,
            "causal": not args.no_causal,
            "seed": args.seed,
            "identity_check": args.identity,
        },
        "problem": {
            "input_seq": problem["input_seq"].tolist(),
            "target_seq": problem["target_seq"].tolist(),
        },
        "timing": {
            "software_ms": round(sw_time * 1000, 2),
            "plate_ms": round(plate_time * 1000, 2),
        },
        "metrics": metrics,
        "verdict": {
            "attn_weights_r2": attn_r2,
            "output_r2": output_r2,
            "attn_pass": bool(attn_r2 > 0.90),
            "output_pass": bool(output_r2 > 0.90),
        },
        "sw_attn_matrix": sw_result["attn_weights"].tolist(),
        "plate_attn_matrix": plate_result["attn_weights"].tolist(),
    }

    out_path = RESULTS_DIR / f"plate_attention_{timestamp}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Results saved: {out_path}")

    # Cleanup
    if args.hardware:
        mux.off()
        mux.close()

    return result


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate Attention Head — Physical Self-Attention via CWM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--simulate", action="store_true",
                            help="Use synthetic transfer matrix (no hardware)")
    mode_group.add_argument("--hardware", action="store_true",
                            help="Drive real plate via Kronos")

    # Model config
    parser.add_argument("--seq-len", type=int, default=8,
                        help="Sequence length (default: 8, matching Attention-11)")
    parser.add_argument("--d-model", type=int, default=16,
                        help="Model/embedding dimension (default: 16)")
    parser.add_argument("--no-causal", action="store_true",
                        help="Disable causal masking (bidirectional attention)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")

    # Simulation options
    parser.add_argument("--identity", action="store_true",
                        help="Use identity transfer matrix (sanity check)")

    # Hardware options
    parser.add_argument("--device", type=str, default="KRONOS",
                        help="Audio device name hint")
    parser.add_argument("--port", type=str, default=None,
                        help="Arduino serial port (auto-detect if omitted)")
    parser.add_argument("--plate", type=str, default="5",
                        help="Plate ID (1-5)")
    parser.add_argument("--census", type=str, default=None,
                        help="Path to census JSON (auto-detect if omitted)")
    parser.add_argument("--live", action="store_true",
                        help="Use live plate for every mat-vec (slow, "
                             "highest fidelity)")

    args = parser.parse_args()

    # Run the experiment
    run_experiment(args)


if __name__ == "__main__":
    main()
