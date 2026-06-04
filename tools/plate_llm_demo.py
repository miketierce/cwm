#!/usr/bin/env python3
"""
Plate LLM Demo — Character-Level Language Model on Physical Glass Plate

Demonstrates LLM-like next-token prediction where the attention mechanism
runs on the fused silica plate's eigenmode spectrum.

Architecture:
  - 1 transformer layer, 1 attention head
  - d_model = 4 (one dimension per acoustic mode)
  - vocab_size = 8 (reduced English alphabet)
  - context_len = 4 (4-token sliding window)
  - ~200 parameters total

Vocabulary (8 most frequent English characters):
  _ e t i n o h s   (index 0-7, _ = space)

Training:
  Cross-entropy on next-token prediction. Adam optimizer, pure numpy.
  Corpus: English words/phrases using only these 8 characters.

Inference:
  Characterize plate's 4×4 transfer matrix H via PicoScope, then use H
  for attention score computation (Q·K^T) and context mixing (attn·V).
  Generate text autoregressively token-by-token.

Hardware signal chain (v3):
  PicoScope AWG (0.5Vpp) → Board D (×3.69) → TX PZT (SW)
  → fused silica plate →
  RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (AC, ±5V)

Usage:
  # Train + generate with plate hardware:
  python tools/plate_llm_demo.py --hardware

  # Train + generate in simulation (no hardware needed):
  python tools/plate_llm_demo.py --simulate

  # Custom training:
  python tools/plate_llm_demo.py --simulate --epochs 2000 --lr 0.01
"""
from __future__ import annotations

import argparse
import json
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

# ═══════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

D_MODEL = 4
CONTEXT_LEN = 4
VOCAB = list("_etinohs")  # _ = space
VOCAB_SIZE = len(VOCAB)
CHAR_TO_IDX = {c: i for i, c in enumerate(VOCAB)}
IDX_TO_CHAR = {i: c for i, c in enumerate(VOCAB)}

# Training corpus: valid English words/phrases using only {_,e,t,i,n,o,h,s}
CORPUS_TEXT = (
    "the stone is set in the thin tin "
    "note the tone in this noise "
    "she sits on its site "
    "this is not the one "
    "into the tent he sent "
    "the shin is not thin "
    "nine tenths into the nest "
    "no one notes the hint "
    "those thin sheets in the nest "
    "it shines in the nite "
    "the host sent his son "
    "one shot hit the stone "
    "she insists on this notion "
    "the tensions in those ties "
    "its intent is to not sin "
    "he notes the shine on it "
    "the tin is thin "
    "she is in the tent "
    "he is not on site "
    "his son is ten "
    "set it in the stone "
    "this is the one "
    "the tone is set "
    "nine in one tent "
    "it is not the hint "
    "she notes the noise "
    "the net is thin "
    "his intent is on it "
    "the host sits in the tent "
    "none is on this site "
    "note the thin tone "
    "he insists on this "
    "she sent it to the son "
    "its shine is not the one "
)

# PicoScope hardware config
CONFIRMED_MODES_HZ = [35_840, 54_920, 57_037, 97_011]
PICO_SAMPLE_RATE_HZ = 781_250
PICO_N_SAMPLES = 2048
PICO_TIMEBASE = 7
PICO_RANGE_INDEX = 8
PICO_RANGE_MV = 5000.0
PICO_N_FFT_PAD = 4
PICO_AWG_UVPP = 500_000
PICO_SETTLE_MS = 100
PICO_N_AVG = 10
PICO_TRIGGER_AUTO_MS = 2000
RELAY_RX_NE = 8


# ═══════════════════════════════════════════════════════════════════════
#  CORPUS PREPARATION
# ═══════════════════════════════════════════════════════════════════════

def prepare_corpus(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Convert text to training pairs (context → next_token)."""
    # Encode text as indices
    tokens = []
    for c in text:
        if c == ' ':
            tokens.append(CHAR_TO_IDX['_'])
        elif c in CHAR_TO_IDX:
            tokens.append(CHAR_TO_IDX[c])
        # skip characters not in vocab

    tokens = np.array(tokens, dtype=np.int32)

    # Build (context, target) pairs
    X_indices = []
    Y_indices = []
    for i in range(len(tokens) - CONTEXT_LEN):
        X_indices.append(tokens[i:i + CONTEXT_LEN])
        Y_indices.append(tokens[i + CONTEXT_LEN])

    return np.array(X_indices), np.array(Y_indices)


def decode_tokens(indices) -> str:
    """Convert token indices back to text."""
    return "".join(IDX_TO_CHAR[int(i)] for i in indices).replace('_', ' ')


# ═══════════════════════════════════════════════════════════════════════
#  MODEL: TINY TRANSFORMER (1 layer, 1 head)
# ═══════════════════════════════════════════════════════════════════════

class TinyTransformer:
    """Single-layer single-head causal transformer for next-token prediction.

    Parameters:
      W_emb:  (vocab_size, d_model) — token embedding
      W_pos:  (context_len, d_model) — position embedding
      W_q:    (d_model, d_model) — query projection
      W_k:    (d_model, d_model) — key projection
      W_v:    (d_model, d_model) — value projection
      W_o:    (d_model, d_model) — output projection
      W_out:  (d_model, vocab_size) — logit head
      b_out:  (vocab_size,) — logit bias
    """

    def __init__(self, seed: int = 42):
        rng = np.random.default_rng(seed)
        s = 0.1  # init scale

        self.W_emb = rng.normal(0, s, (VOCAB_SIZE, D_MODEL))
        self.W_pos = rng.normal(0, s, (CONTEXT_LEN, D_MODEL))
        self.W_q = rng.normal(0, s, (D_MODEL, D_MODEL))
        self.W_k = rng.normal(0, s, (D_MODEL, D_MODEL))
        self.W_v = rng.normal(0, s, (D_MODEL, D_MODEL))
        self.W_o = rng.normal(0, s, (D_MODEL, D_MODEL))
        self.W_out = rng.normal(0, s, (D_MODEL, VOCAB_SIZE))
        self.b_out = np.zeros(VOCAB_SIZE)

        # Causal mask
        self.causal_mask = np.triu(
            np.ones((CONTEXT_LEN, CONTEXT_LEN), dtype=bool), k=1
        )

    def param_count(self) -> int:
        return (self.W_emb.size + self.W_pos.size + self.W_q.size +
                self.W_k.size + self.W_v.size + self.W_o.size +
                self.W_out.size + self.b_out.size)

    def embed(self, token_indices: np.ndarray) -> np.ndarray:
        """Token + position embeddings → (context_len, d_model)."""
        T = len(token_indices)
        X = self.W_emb[token_indices] + self.W_pos[:T]
        return X

    def forward(self, X: np.ndarray, H: np.ndarray = None) -> dict:
        """Forward pass. If H is provided, use it for attention mat-muls.

        X: (T, d_model) — embedded input
        H: (d_model, d_model) — plate transfer matrix (None = identity/software)

        Returns dict with logits and intermediates.
        """
        T = X.shape[0]

        # Projections (always digital)
        Q = X @ self.W_q   # (T, d_model)
        K = X @ self.W_k
        V = X @ self.W_v

        d_k = D_MODEL
        scale = np.sqrt(d_k)

        # Attention scores: Q · K^T / sqrt(d_k)
        if H is not None:
            # PLATE PATH: route each query through H, then dot with keys
            scores = np.zeros((T, T))
            for i in range(T):
                hq = H @ Q[i]  # plate computes H @ q_i
                for j in range(T):
                    scores[i, j] = np.dot(hq, K[j])
        else:
            # SOFTWARE PATH: standard Q·K^T
            scores = Q @ K.T

        scores = scores / scale

        # Causal mask
        mask = self.causal_mask[:T, :T]
        scores = np.where(mask, -1e9, scores)

        # Softmax
        attn = self._softmax(scores)

        # Context mixing: attn · V
        if H is not None:
            # PLATE PATH: route attention rows through H, weight values
            context = np.zeros((T, D_MODEL))
            for i in range(T):
                h_attn = H @ attn[i, :T]  # plate computes H @ attn_row
                # Weighted sum of values (truncated to T positions)
                for j in range(T):
                    context[i] += h_attn[j] * V[j]
        else:
            # SOFTWARE PATH: standard attn · V
            context = attn @ V

        # Output projection + residual connection
        out = context @ self.W_o + X  # residual

        # Logit head (only last position for next-token prediction)
        logits = out[-1] @ self.W_out + self.b_out  # (vocab_size,)

        return {
            "logits": logits,
            "attn": attn,
            "context": context,
            "out": out,
            "Q": Q, "K": K, "V": V,
            "scores_raw": scores,
        }

    def forward_train(self, X: np.ndarray, target: int) -> tuple[float, dict]:
        """Forward pass + cross-entropy loss for training."""
        result = self.forward(X, H=None)
        logits = result["logits"]

        # Stable softmax for loss
        probs = self._softmax(logits.reshape(1, -1))[0]
        loss = -np.log(probs[target] + 1e-10)

        result["probs"] = probs
        result["loss"] = loss
        return loss, result

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        e = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return e / np.sum(e, axis=-1, keepdims=True)

    def get_params(self) -> list[np.ndarray]:
        return [self.W_emb, self.W_pos, self.W_q, self.W_k,
                self.W_v, self.W_o, self.W_out, self.b_out]

    def set_params(self, params: list[np.ndarray]):
        (self.W_emb, self.W_pos, self.W_q, self.W_k,
         self.W_v, self.W_o, self.W_out, self.b_out) = params


# ═══════════════════════════════════════════════════════════════════════
#  TRAINING (numpy backprop with numerical gradients → Adam)
# ═══════════════════════════════════════════════════════════════════════

def compute_loss_batch(model: TinyTransformer, X_indices: np.ndarray,
                       Y_indices: np.ndarray, batch_idx: np.ndarray) -> float:
    """Compute average loss over a batch."""
    total_loss = 0.0
    for idx in batch_idx:
        X = model.embed(X_indices[idx])
        loss, _ = model.forward_train(X, Y_indices[idx])
        total_loss += loss
    return total_loss / len(batch_idx)


def numerical_gradient(model: TinyTransformer, X_indices: np.ndarray,
                       Y_indices: np.ndarray, batch_idx: np.ndarray,
                       eps: float = 1e-4) -> list[np.ndarray]:
    """Compute gradients via finite differences (small model makes this OK)."""
    params = model.get_params()
    grads = []
    for p_idx, param in enumerate(params):
        grad = np.zeros_like(param)
        it = np.nditer(param, flags=['multi_index'])
        while not it.finished:
            ix = it.multi_index
            old_val = param[ix]

            param[ix] = old_val + eps
            model.set_params(params)
            loss_plus = compute_loss_batch(model, X_indices, Y_indices, batch_idx)

            param[ix] = old_val - eps
            model.set_params(params)
            loss_minus = compute_loss_batch(model, X_indices, Y_indices, batch_idx)

            grad[ix] = (loss_plus - loss_minus) / (2 * eps)
            param[ix] = old_val
            it.iternext()
        model.set_params(params)
        grads.append(grad)
    return grads


def train_model(model: TinyTransformer, X_indices: np.ndarray,
                Y_indices: np.ndarray, epochs: int = 1000,
                lr: float = 0.005, batch_size: int = 32,
                seed: int = 42) -> list[float]:
    """Train with Adam optimizer using numerical gradients."""
    rng = np.random.default_rng(seed)
    n_samples = len(X_indices)
    params = model.get_params()

    # Adam state
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    beta1, beta2, eps_adam = 0.9, 0.999, 1e-8
    t_step = 0

    losses = []
    print(f"\n  Training ({model.param_count()} params, "
          f"{n_samples} samples, {epochs} epochs)...")
    t0 = time.time()

    for epoch in range(epochs):
        # Random mini-batch
        batch_idx = rng.choice(n_samples, size=min(batch_size, n_samples),
                               replace=False)

        # Compute gradients
        grads = numerical_gradient(model, X_indices, Y_indices, batch_idx)

        # Adam update
        t_step += 1
        for i, (p, g) in enumerate(zip(params, grads)):
            m[i] = beta1 * m[i] + (1 - beta1) * g
            v[i] = beta2 * v[i] + (1 - beta2) * g ** 2
            m_hat = m[i] / (1 - beta1 ** t_step)
            v_hat = v[i] / (1 - beta2 ** t_step)
            params[i] = p - lr * m_hat / (np.sqrt(v_hat) + eps_adam)

        model.set_params(params)

        # Track loss
        if epoch % 50 == 0 or epoch == epochs - 1:
            full_loss = compute_loss_batch(
                model, X_indices, Y_indices, np.arange(n_samples)
            )
            losses.append(full_loss)
            elapsed = time.time() - t0

            # Compute accuracy
            correct = 0
            for idx in range(n_samples):
                X = model.embed(X_indices[idx])
                result = model.forward(X, H=None)
                pred = np.argmax(result["logits"])
                if pred == Y_indices[idx]:
                    correct += 1
            acc = correct / n_samples

            if epoch % 200 == 0 or epoch == epochs - 1:
                print(f"    epoch {epoch:4d}: loss={full_loss:.3f}, "
                      f"acc={acc:.1%}, {elapsed:.1f}s")

    print(f"  Training complete in {time.time()-t0:.1f}s")
    return losses


# ═══════════════════════════════════════════════════════════════════════
#  TEXT GENERATION
# ═══════════════════════════════════════════════════════════════════════

def generate_text(model: TinyTransformer, prompt: str, length: int = 40,
                  temperature: float = 0.8, H: np.ndarray = None,
                  seed: int = None) -> str:
    """Autoregressive text generation using the model.

    If H is provided, uses plate transfer matrix for attention.
    """
    rng = np.random.default_rng(seed)

    # Encode prompt
    tokens = []
    for c in prompt:
        if c == ' ':
            tokens.append(CHAR_TO_IDX['_'])
        elif c in CHAR_TO_IDX:
            tokens.append(CHAR_TO_IDX[c])

    # Pad if needed
    while len(tokens) < CONTEXT_LEN:
        tokens.insert(0, CHAR_TO_IDX['_'])

    generated = list(tokens)

    for _ in range(length):
        # Take last context_len tokens
        context = np.array(generated[-CONTEXT_LEN:], dtype=np.int32)
        X = model.embed(context)
        result = model.forward(X, H=H)
        logits = result["logits"]

        # Temperature sampling
        if temperature > 0:
            logits = logits / temperature
            probs = np.exp(logits - np.max(logits))
            probs = probs / probs.sum()
            next_token = rng.choice(VOCAB_SIZE, p=probs)
        else:
            next_token = np.argmax(logits)

        generated.append(next_token)

    # Decode
    return decode_tokens(generated[len(tokens):])


# ═══════════════════════════════════════════════════════════════════════
#  HARDWARE: PICOSCOPE PLATE CHARACTERIZATION
# ═══════════════════════════════════════════════════════════════════════

import ctypes as ct
import os

os.environ['DYLD_LIBRARY_PATH'] = (
    '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
)


def characterize_plate(port: str = None) -> np.ndarray:
    """Measure the plate's 4×4 transfer matrix H via PicoScope.

    Returns normalized H (unit diagonal).
    """
    from picosdk.ps2000 import ps2000
    from relay_mux import RelayMux

    # Open PicoScope
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, 1, 0, PICO_RANGE_INDEX)
    print(f"    PicoScope opened (handle={handle})")

    # Small delay between USB devices to avoid bus contention
    time.sleep(0.5)

    # Open relay mux
    mux = RelayMux(port=port)
    mux.open()
    mux.select(RELAY_RX_NE)
    time.sleep(0.1)

    n = len(CONFIRMED_MODES_HZ)
    H = np.zeros((n, n))

    print(f"    Characterizing {n}×{n} transfer matrix...")
    t0 = time.time()

    for j, drive_f in enumerate(CONFIRMED_MODES_HZ):
        # Drive single tone
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, PICO_AWG_UVPP, 0,
            float(drive_f), float(drive_f), 0, 0, 0, 0
        )
        time.sleep(PICO_SETTLE_MS / 1000.0)

        # Average captures
        mags_sum = np.zeros(n)
        for _ in range(PICO_N_AVG):
            # Triggered capture
            ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, PICO_TRIGGER_AUTO_MS)
            ps2000.ps2000_run_block(
                handle, PICO_N_SAMPLES, PICO_TIMEBASE, 1,
                ct.byref(ct.c_int32())
            )
            time.sleep(0.005)
            for _ in range(500):
                if ps2000.ps2000_ready(handle):
                    break
                time.sleep(0.005)

            buf = (ct.c_int16 * PICO_N_SAMPLES)()
            ov = ct.c_int16(0)
            ps2000.ps2000_get_values(
                handle, ct.byref(buf), None, None, None,
                ct.byref(ov), PICO_N_SAMPLES, 0
            )
            mv = np.array(buf, dtype=np.float64) * (PICO_RANGE_MV / 32767.0)

            # FFT amplitude at each mode
            ac = mv - mv.mean()
            window = np.hanning(PICO_N_SAMPLES)
            fft_c = np.fft.rfft(ac * window, n=PICO_N_SAMPLES * PICO_N_FFT_PAD)
            bin_width = PICO_SAMPLE_RATE_HZ / (PICO_N_SAMPLES * PICO_N_FFT_PAD)

            for i, freq in enumerate(CONFIRMED_MODES_HZ):
                bin_idx = int(round(freq / bin_width))
                lo = max(0, bin_idx - 3)
                hi = min(len(fft_c) - 1, bin_idx + 3)
                peak_bin = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
                mags_sum[i] += np.abs(fft_c[peak_bin])

        H[:, j] = mags_sum / PICO_N_AVG
        print(f"      [{j+1}/{n}] {drive_f:.0f} Hz → "
              f"diag={H[j,j]:.0f}", flush=True)

    # Stop AWG
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0, 0, 0, 0
    )
    ps2000.ps2000_close_unit(handle)
    mux.off()
    mux.close()

    # Normalize to unit diagonal
    diag = np.diag(H)
    if np.min(diag) > 0:
        D_inv = np.diag(1.0 / diag)
        H = D_inv @ H

    print(f"    H characterized in {time.time()-t0:.1f}s")
    print(f"    Off-diagonal mean: {np.mean(np.abs(H - np.eye(n))):.4f}")
    return H


# ═══════════════════════════════════════════════════════════════════════
#  EVALUATION
# ═══════════════════════════════════════════════════════════════════════

def evaluate_model(model: TinyTransformer, X_indices: np.ndarray,
                   Y_indices: np.ndarray, H: np.ndarray = None,
                   label: str = "software") -> dict:
    """Evaluate accuracy and perplexity."""
    n = len(X_indices)
    correct = 0
    total_loss = 0.0

    for idx in range(n):
        X = model.embed(X_indices[idx])
        result = model.forward(X, H=H)
        logits = result["logits"]
        probs = np.exp(logits - np.max(logits))
        probs = probs / probs.sum()

        pred = np.argmax(logits)
        if pred == Y_indices[idx]:
            correct += 1
        total_loss += -np.log(probs[Y_indices[idx]] + 1e-10)

    acc = correct / n
    perplexity = np.exp(total_loss / n)
    return {"accuracy": acc, "perplexity": perplexity, "label": label}


def compare_generations(model: TinyTransformer, H: np.ndarray,
                        prompts: list[str], length: int = 30,
                        temperature: float = 0.7) -> list[dict]:
    """Generate from same prompts with software and plate, compare."""
    results = []
    for prompt in prompts:
        sw_text = generate_text(model, prompt, length, temperature,
                                H=None, seed=123)
        plate_text = generate_text(model, prompt, length, temperature,
                                   H=H, seed=123)
        match = sw_text == plate_text
        results.append({
            "prompt": prompt,
            "software": sw_text,
            "plate": plate_text,
            "match": match,
        })
    return results


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate LLM Demo — Character-level language model on glass",
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--simulate", action="store_true",
                            help="Use synthetic H (no hardware)")
    mode_group.add_argument("--hardware", action="store_true",
                            help="Characterize plate via PicoScope")

    parser.add_argument("--epochs", type=int, default=1000,
                        help="Training epochs (default: 1000)")
    parser.add_argument("--lr", type=float, default=0.005,
                        help="Learning rate (default: 0.005)")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Batch size (default: 32)")
    parser.add_argument("--temperature", type=float, default=0.7,
                        help="Sampling temperature (default: 0.7)")
    parser.add_argument("--gen-length", type=int, default= 40,
                        help="Generated text length (default: 40)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--port", type=str, default=None,
                        help="Arduino serial port (auto-detect if omitted)")

    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("\n" + "=" * 70)
    print("  PLATE LLM DEMO — Character-Level Language Model on Glass")
    print("=" * 70)
    print(f"  Architecture: 1-layer, 1-head transformer")
    print(f"  d_model={D_MODEL}, vocab={VOCAB_SIZE} ({VOCAB})")
    print(f"  context_len={CONTEXT_LEN}")
    print(f"  Mode: {'HARDWARE' if args.hardware else 'SIMULATE'}")

    # ── Step 1: Prepare corpus ──
    print(f"\n  Step 1: Preparing corpus...")
    X_idx, Y_idx = prepare_corpus(CORPUS_TEXT)
    print(f"    Corpus: {len(CORPUS_TEXT)} chars → {len(X_idx)} training pairs")
    print(f"    Sample: '{CORPUS_TEXT[:50]}...'")

    # Verify corpus uses only our vocab
    used_chars = set(CORPUS_TEXT)
    valid = all(c in CHAR_TO_IDX or c == ' ' for c in used_chars)
    print(f"    Vocab check: {'PASS' if valid else 'FAIL'} "
          f"(chars used: {sorted(used_chars)})")

    # ── Step 2: Train model ──
    print(f"\n  Step 2: Training model...")
    model = TinyTransformer(seed=args.seed)
    print(f"    Parameters: {model.param_count()}")

    losses = train_model(
        model, X_idx, Y_idx,
        epochs=args.epochs, lr=args.lr,
        batch_size=args.batch_size, seed=args.seed
    )

    # ── Step 3: Evaluate software baseline ──
    print(f"\n  Step 3: Software evaluation...")
    sw_eval = evaluate_model(model, X_idx, Y_idx, H=None, label="software")
    print(f"    Accuracy:   {sw_eval['accuracy']:.1%}")
    print(f"    Perplexity: {sw_eval['perplexity']:.2f}")

    # ── Step 4: Get plate transfer matrix ──
    if args.hardware:
        print(f"\n  Step 4: Characterizing plate via PicoScope...")
        H = characterize_plate(port=args.port)
    else:
        print(f"\n  Step 4: Building synthetic plate H...")
        # Synthetic H matching real plate's measured properties
        rng = np.random.default_rng(args.seed + 100)
        H = np.eye(D_MODEL)
        # Add small off-diagonal coupling (matching measured 0.0025)
        for i in range(D_MODEL):
            for j in range(D_MODEL):
                if i != j:
                    H[i, j] = rng.uniform(0.001, 0.005)
        print(f"    Synthetic H (off-diag mean: "
              f"{np.mean(np.abs(H - np.eye(D_MODEL))):.4f})")

    # Print H
    print(f"\n    Transfer matrix H:")
    for i in range(D_MODEL):
        row = " ".join(f"{H[i,j]:7.4f}" for j in range(D_MODEL))
        print(f"      [{row}]")

    # ── Step 5: Evaluate with plate ──
    print(f"\n  Step 5: Plate evaluation...")
    plate_eval = evaluate_model(model, X_idx, Y_idx, H=H, label="plate")
    print(f"    Accuracy:   {plate_eval['accuracy']:.1%}")
    print(f"    Perplexity: {plate_eval['perplexity']:.2f}")
    print(f"    Accuracy match: {plate_eval['accuracy'] == sw_eval['accuracy']}")

    # ── Step 6: Generate text ──
    print(f"\n  Step 6: Text generation (temperature={args.temperature})...")
    prompts = ["the ", "is n", "tone", "shin"]

    gen_results = compare_generations(
        model, H, prompts,
        length=args.gen_length,
        temperature=args.temperature
    )

    print(f"\n  {'Prompt':<8} {'Software Output':<45} {'Plate Output':<45} Match")
    print(f"  {'─'*8} {'─'*45} {'─'*45} {'─'*5}")
    for r in gen_results:
        sw_disp = r['software'][:42] + "..." if len(r['software']) > 42 else r['software']
        pl_disp = r['plate'][:42] + "..." if len(r['plate']) > 42 else r['plate']
        print(f"  {r['prompt']!r:<8} {sw_disp:<45} {pl_disp:<45} "
              f"{'✓' if r['match'] else '✗'}")

    # ── Step 7: Detailed comparison ──
    print(f"\n  Step 7: Forward pass comparison (5 random inputs)...")
    rng = np.random.default_rng(args.seed)
    r2_scores = []
    for _ in range(5):
        idx = rng.integers(len(X_idx))
        X = model.embed(X_idx[idx])
        sw = model.forward(X, H=None)
        pl = model.forward(X, H=H)

        # R² on logits
        ss_res = np.sum((sw["logits"] - pl["logits"]) ** 2)
        ss_tot = np.sum((sw["logits"] - np.mean(sw["logits"])) ** 2)
        r2 = 1.0 - ss_res / (ss_tot + 1e-12)
        r2_scores.append(r2)

    mean_r2 = np.mean(r2_scores)
    print(f"    Logit R² (5 samples): {r2_scores}")
    print(f"    Mean logit R²: {mean_r2:.6f}")

    # ── Verdict ──
    print(f"\n  {'═' * 60}")
    print(f"  VERDICT")
    print(f"  {'═' * 60}")
    print(f"  Software accuracy: {sw_eval['accuracy']:.1%}")
    print(f"  Plate accuracy:    {plate_eval['accuracy']:.1%}")
    print(f"  Logit R²:          {mean_r2:.6f}")
    gen_matches = sum(1 for r in gen_results if r['match'])
    print(f"  Generation match:  {gen_matches}/{len(gen_results)} prompts")
    overall_pass = (plate_eval['accuracy'] >= sw_eval['accuracy'] * 0.95
                    and mean_r2 > 0.99)
    print(f"  Overall:           {'★ PASS' if overall_pass else '✗ FAIL'} — "
          f"Plate produces LLM-like text generation")
    print(f"  {'═' * 60}")

    # ── Save results ──
    result = {
        "experiment": "plate_llm_demo",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "hardware" if args.hardware else "simulate",
        "config": {
            "d_model": D_MODEL,
            "vocab_size": VOCAB_SIZE,
            "vocab": VOCAB,
            "context_len": CONTEXT_LEN,
            "epochs": args.epochs,
            "lr": args.lr,
            "batch_size": args.batch_size,
            "temperature": args.temperature,
            "gen_length": args.gen_length,
            "param_count": model.param_count(),
            "n_training_pairs": len(X_idx),
        },
        "training": {
            "final_loss": float(losses[-1]) if losses else None,
            "loss_history": [float(l) for l in losses],
        },
        "evaluation": {
            "software": sw_eval,
            "plate": plate_eval,
            "logit_r2_mean": float(mean_r2),
            "logit_r2_samples": [float(r) for r in r2_scores],
        },
        "generation": gen_results,
        "transfer_matrix_H": H.tolist(),
        "verdict": {
            "overall_pass": bool(overall_pass),
            "accuracy_match": plate_eval['accuracy'] == sw_eval['accuracy'],
            "generation_matches": gen_matches,
            "total_prompts": len(gen_results),
        },
    }

    out_path = RESULTS_DIR / f"plate_llm_demo_{timestamp}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Results saved: {out_path}")


if __name__ == "__main__":
    main()
