"""
L3d: Constrained-Input Train-Through-H — Three Novel Approaches
================================================================

The L3/L3c problem: learnable layers before H can always learn a rotation
that makes ANY rank-2 matrix work equally well. The fix isn't more modes
or more partitions — it's removing the rotation freedom.

This script tests THREE approaches that make physical H distinguishable
from random within the SAME 2-channel hardware:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

APPROACH 1: FIXED CODEBOOK (Constellation LM)
─────────────────────────────────────────────
Inspiration: QAM modulation / Hopfield content-addressable memory

Each token is mapped to a FIXED 26-dim binary code (not learnable).
H projects each code to a point in 2D "constellation space".
The decoder must learn which 2D point → which token.

WHY this differentiates physical from random:
• The 26-dim codes are FIXED — no rotation freedom before H
• Different H matrices produce different 2D constellations
• Physical H (non-uniform B/A ratios) creates an ASYMMETRIC constellation
  with some tokens well-separated and others clustered
• Random H creates a different (likely more uniform) constellation
• The LM's quality depends on HOW tokens cluster: do semantically
  related characters (vowels, consonants, digits) land near each other?
• Physical H may accidentally create useful clusters (or terrible ones)
  — the point is it will be DIFFERENT from random

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

APPROACH 2: NONLINEAR FEATURE EXPANSION (Simulated IM Products)
───────────────────────────────────────────────────────────────
Inspiration: Physical intermodulation / kernel trick / reservoir computing

The plate physically generates intermodulation products when driven hard
(8.3× at F1+F2 confirmed with NCO). We simulate this: the plate output
includes not just the linear H@x, but also pairwise products of mode
activations as seen through H.

Output = [H@x, (H@x)² element-wise, (H@(x⊙x)), cross terms]

WHY this differentiates physical from random:
• IM products depend on WHICH modes are physically coupled
• The plate's IM coupling structure ≠ random coupling structure
• Physical IM products reflect the plate's geometry (mode shapes)
• Effectively: physical H implies a specific KERNEL, random H a different one
• The nonlinear expansion creates ~50+ output dimensions from 2 channels
• Different kernels → different learning dynamics

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

APPROACH 3: DECAY-WEIGHTED TEMPORAL READOUT (Virtual Sensors via Q-diversity)
─────────────────────────────────────────────────────────────────────────────
Inspiration: Delay-line reservoirs (Appeltant 2011) / Sigi Cycle temporal mux

Different modes have different Q factors (34–296 measured). After pulsed
excitation, mode amplitudes decay as exp(-πf·t/Q). At time t after pulse,
the 2-channel measurement represents a DIFFERENT weighted sum of modes
than at t=0:

  H_effective(t) = H ⊙ diag(exp(-πf_i·t/Q_i))

Multiple time samples → multiple effective H matrices → multiple 2D readouts
— all from the SAME 2 physical sensors!

WHY this differentiates physical from random:
• The decay profile is PHYSICAL (determined by material loss, geometry)
• Random H has no meaningful temporal evolution
• Physical H + decay = family of related matrices parameterized by t
• The CORRELATION STRUCTURE between time samples encodes physics
• A random matrix has no such temporal family

Note: While actual temporal readout fails at current Q (τ too short for
step rates), we SIMULATE the effect here. The question is whether the
STRUCTURE helps — if yes, it motivates higher-Q substrates or faster capture.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Usage:
  python3 tools/l3d_constrained_approaches.py
  python3 tools/l3d_constrained_approaches.py --approach all --epochs 40
  python3 tools/l3d_constrained_approaches.py --approach codebook
  python3 tools/l3d_constrained_approaches.py --approach nonlinear
  python3 tools/l3d_constrained_approaches.py --approach temporal
"""
import argparse
import json
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from pathlib import Path
from datetime import datetime

# ─── Args ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='L3d: Constrained-Input Approaches')
parser.add_argument('--h-matrix', type=str,
                    default='data/results/h_matrix/l1_h_matrix_20260602_220004.json')
parser.add_argument('--approach', type=str, default='all',
                    choices=['all', 'codebook', 'nonlinear', 'temporal', 'cascaded'])
parser.add_argument('--epochs', type=int, default=40)
parser.add_argument('--batch-size', type=int, default=64)
parser.add_argument('--seq-len', type=int, default=64)
parser.add_argument('--d-model', type=int, default=128)
parser.add_argument('--lr', type=float, default=1e-3)
parser.add_argument('--n-random', type=int, default=5, help='Random baselines per approach')
parser.add_argument('--seed', type=int, default=42)
args = parser.parse_args()

torch.manual_seed(args.seed)
np.random.seed(args.seed)

# ─── Load H Matrix ───────────────────────────────────────────────
print("=" * 70)
print("  L3d: Constrained-Input — Novel Approaches to Plate Differentiation")
print("=" * 70)
print()

h_path = Path(args.h_matrix)
with open(h_path) as f:
    h_data = json.load(f)

H_raw = np.array(h_data['H_raw'])  # (26, 2)
n_modes, n_ch = H_raw.shape
ratios = np.array([m['ratio_b_over_a'] for m in h_data['modes']])
freqs = np.array([m['freq_hz'] for m in h_data['modes']])

# Normalize H
H_norm = H_raw / (np.linalg.norm(H_raw, 'fro') + 1e-10) * np.sqrt(n_modes)
H_tensor = torch.tensor(H_norm, dtype=torch.float32)

print(f"  H matrix: {n_modes}×{n_ch}, cond={h_data.get('condition_number', 'N/A')}")
print(f"  B/A ratios: {ratios.min():.2f} – {ratios.max():.2f}")
print(f"  Frequencies: {freqs[0]/1000:.0f} – {freqs[-1]/1000:.0f} kHz")
print()

# ─── Dataset ──────────────────────────────────────────────────────
DATA_DIR = Path('data')
SHAKESPEARE_PATH = DATA_DIR / 'tinyshakespeare.txt'
if not SHAKESPEARE_PATH.exists():
    import urllib.request
    url = 'https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt'
    urllib.request.urlretrieve(url, SHAKESPEARE_PATH)

with open(SHAKESPEARE_PATH, 'r') as f:
    text = f.read()

chars = sorted(set(text))
vocab_size = len(chars)
char_to_idx = {c: i for i, c in enumerate(chars)}
idx_to_char = {i: c for i, c in enumerate(chars)}

data = torch.tensor([char_to_idx[c] for c in text], dtype=torch.long)
n_total = len(data)
n_train = int(0.9 * n_total)
train_data = data[:n_train]
val_data = data[n_train:]

print(f"  Dataset: {n_total:,} chars, vocab={vocab_size}")
print()


def get_batch(split, batch_size, seq_len):
    d = train_data if split == 'train' else val_data
    ix = torch.randint(len(d) - seq_len - 1, (batch_size,))
    x = torch.stack([d[i:i + seq_len] for i in ix])
    y = torch.stack([d[i + 1:i + seq_len + 1] for i in ix])
    return x, y


# ─── Training utility ─────────────────────────────────────────────

def train_model(model, epochs, batch_size, seq_len, lr, verbose=True):
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    steps_per_epoch = max(1, n_train // (batch_size * seq_len))
    val_losses = []

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0
        n_batches = 0

        for _ in range(steps_per_epoch):
            x, y = get_batch('train', batch_size, seq_len)
            logits = model(x)
            loss = F.cross_entropy(logits.view(-1, vocab_size), y.view(-1))

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        scheduler.step()

        model.eval()
        with torch.no_grad():
            val_sum = 0
            for _ in range(20):
                x, y = get_batch('val', batch_size, seq_len)
                logits = model(x)
                val_sum += F.cross_entropy(logits.view(-1, vocab_size), y.view(-1)).item()
            val_losses.append(val_sum / 20)

        if verbose and ((epoch + 1) % 10 == 0 or epoch == 0):
            ppl = np.exp(val_losses[-1])
            print(f"    Epoch {epoch+1:>3}/{epochs}: val={val_losses[-1]:.4f}, ppl={ppl:.2f}")

    return val_losses


def count_params(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


# ═══════════════════════════════════════════════════════════════════
# APPROACH 1: FIXED CODEBOOK (Constellation LM)
# ═══════════════════════════════════════════════════════════════════

class CodebookPlateModel(nn.Module):
    """
    Fixed codebook maps tokens to 26-dim binary vectors.
    H projects these to 2D (non-learnable).
    Only the decoder is learnable.

    The codebook is a FIXED, deterministic mapping — no rotation freedom.
    """

    def __init__(self, vocab_size, d_model, H, codebook):
        super().__init__()
        # Fixed codebook: (vocab_size, 26) — NOT learnable
        self.register_buffer('codebook', codebook)
        # Fixed H: (26, 2) — NOT learnable
        self.register_buffer('H', H)

        # Precompute constellation: each token's fixed 2D position
        # constellation = codebook @ H : (vocab_size, 2)
        self.register_buffer('constellation', codebook @ H)

        # Learnable decoder: from 2D plate output to predictions
        # This is ALL the model can learn — how to decode the constellation
        self.decoder = nn.Sequential(
            nn.Linear(n_ch, d_model),
            nn.LayerNorm(d_model),
            nn.GELU(),
            nn.Linear(d_model, d_model),
            nn.LayerNorm(d_model),
            nn.GELU(),
            nn.Linear(d_model, vocab_size),
        )

    def forward(self, x):
        # x: (batch, seq) token indices
        # Look up each token's 2D constellation point
        plate_out = self.constellation[x]  # (batch, seq, 2)
        return self.decoder(plate_out)


def make_codebook(vocab_size, n_modes, strategy='hadamard'):
    """Create a fixed token→mode mapping (no learnable params)."""
    if strategy == 'hadamard':
        # Use Hadamard-like binary codes for maximum separation
        # Rows of a random binary matrix with good Hamming properties
        rng = np.random.default_rng(123)
        # Generate more candidates than needed, select max-distance subset
        n_candidates = 1000
        candidates = rng.integers(0, 2, size=(n_candidates, n_modes)).astype(np.float32)
        # Greedy max-min Hamming distance selection
        selected = [0]
        for _ in range(vocab_size - 1):
            best_idx = -1
            best_min_dist = -1
            for c in range(n_candidates):
                if c in selected:
                    continue
                min_dist = min(np.sum(candidates[c] != candidates[s])
                             for s in selected)
                if min_dist > best_min_dist:
                    best_min_dist = min_dist
                    best_idx = c
            selected.append(best_idx)
        codebook = candidates[selected]  # (vocab_size, 26)
        return torch.tensor(codebook, dtype=torch.float32)

    elif strategy == 'frequency_bands':
        # Map tokens to frequency sub-bands (physically motivated)
        # Each token activates a specific subset of modes
        rng = np.random.default_rng(456)
        codebook = np.zeros((vocab_size, n_modes), dtype=np.float32)
        # Each token activates ~5 modes (sparse, like physical excitation)
        for i in range(vocab_size):
            active = rng.choice(n_modes, size=5, replace=False)
            codebook[i, active] = 1.0
        return torch.tensor(codebook, dtype=torch.float32)

    elif strategy == 'thermometer':
        # Thermometer encoding: token i activates first i*(26/vocab) modes
        codebook = np.zeros((vocab_size, n_modes), dtype=np.float32)
        for i in range(vocab_size):
            n_active = max(1, int((i + 1) * n_modes / vocab_size))
            codebook[i, :n_active] = 1.0
        return torch.tensor(codebook, dtype=torch.float32)


# ═══════════════════════════════════════════════════════════════════
# APPROACH 2: NONLINEAR FEATURE EXPANSION
# ═══════════════════════════════════════════════════════════════════

class NonlinearPlateModel(nn.Module):
    """
    Simulates the plate's intermodulation physics:
    When modes are co-activated, the plate generates IM products
    that are nonlinear functions of input amplitudes.

    Output features:
    - Linear: H@x (2 dims) — standard plate response
    - Quadratic: (x_i * x_j) projected through H (IM2 products)
    - Self-interaction: x_i² projected through H (harmonic generation)

    The quadratic terms model physical IM: when modes i,j are both
    active, the plate produces energy at f_i±f_j with amplitude
    proportional to |A_i|·|A_j|·coupling(i,j).

    The coupling matrix C encodes WHICH mode pairs interact strongly.
    For physical H: C is derived from the plate's spatial overlap integrals.
    For random H: C is random → different nonlinear structure.
    """

    def __init__(self, vocab_size, d_model, H, coupling_matrix=None):
        super().__init__()
        n_modes, n_ch = H.shape
        self.n_modes = n_modes
        self.n_ch = n_ch

        # Fixed H (not learnable)
        self.register_buffer('H', H)

        # Coupling matrix for IM products: C[i,j] = coupling strength
        # Physical: derived from mode overlap (cos of angle between H rows)
        if coupling_matrix is None:
            # Default: use physical H to derive coupling
            H_rows = H / (torch.norm(H, dim=1, keepdim=True) + 1e-10)
            coupling_matrix = H_rows @ H_rows.T  # cosine similarity
        self.register_buffer('coupling', coupling_matrix)

        # Select top-K strongest IM pairs (don't need all 325)
        n_im_pairs = min(20, n_modes * (n_modes - 1) // 2)
        # Get top couplings (off-diagonal)
        coup_flat = coupling_matrix.clone()
        coup_flat.fill_diagonal_(0)
        _, top_idx = torch.topk(coup_flat.abs().flatten(), n_im_pairs)
        im_i = top_idx // n_modes
        im_j = top_idx % n_modes
        self.register_buffer('im_i', im_i)
        self.register_buffer('im_j', im_j)

        # Output dims: 2 (linear) + n_im_pairs * 2 (quadratic through H) = 2 + 40
        self.output_dim = n_ch + n_im_pairs * n_ch

        # Learnable embedding and decoder (but NOT the projection)
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.project_to_modes = nn.Linear(d_model, n_modes)

        # Fixed nonlinear projection (not learnable)
        # IM products projected through relevant H rows
        self.register_buffer('im_H_i', H[im_i])  # (n_im_pairs, 2)
        self.register_buffer('im_H_j', H[im_j])  # (n_im_pairs, 2)

        # Decoder
        self.decoder = nn.Sequential(
            nn.Linear(self.output_dim, d_model),
            nn.LayerNorm(d_model),
            nn.GELU(),
            nn.Linear(d_model, d_model),
            nn.LayerNorm(d_model),
            nn.GELU(),
            nn.Linear(d_model, vocab_size),
        )

    def forward(self, x):
        emb = self.embedding(x)
        modes = self.project_to_modes(emb)  # (batch, seq, 26)

        # Linear plate response
        linear_out = modes @ self.H  # (batch, seq, 2)

        # Nonlinear IM products: amplitude_i × amplitude_j × coupling
        # For each IM pair (i,j): product of mode activations
        mode_i = modes[:, :, self.im_i]  # (batch, seq, n_im_pairs)
        mode_j = modes[:, :, self.im_j]  # (batch, seq, n_im_pairs)
        im_amplitudes = mode_i * mode_j  # (batch, seq, n_im_pairs)

        # Project IM products through spatial channels
        # Each IM product appears at both receivers with relative amplitude
        # determined by the spatial overlap of the parent modes
        im_out = torch.stack([
            im_amplitudes * self.im_H_i[:, 0] * self.im_H_j[:, 0],  # Ch A
            im_amplitudes * self.im_H_i[:, 1] * self.im_H_j[:, 1],  # Ch B
        ], dim=-1)  # (batch, seq, n_im_pairs, 2)

        im_out = im_out.view(*im_out.shape[:2], -1)  # (batch, seq, n_im_pairs*2)

        # Concatenate linear + nonlinear
        full_out = torch.cat([linear_out, im_out], dim=-1)  # (batch, seq, output_dim)

        return self.decoder(full_out)


# ═══════════════════════════════════════════════════════════════════
# APPROACH 3: DECAY-WEIGHTED TEMPORAL READOUT
# ═══════════════════════════════════════════════════════════════════

class TemporalPlateModel(nn.Module):
    """
    Simulates reading the plate at multiple time points after excitation.

    Each mode decays as exp(-π·f·t/Q), with Q varying by mode (34–296).
    At each time sample t_k, the effective H changes:
        H_eff(t_k) = H ⊙ diag(exp(-π·f_i·t_k/Q_i))

    Multiple time samples → multiple 2D readouts from same 2 sensors.
    This is physically realizable with fast sequential captures.

    Inspiration: Appeltant et al. (2011) delay-based reservoir —
    a single nonlinear node with time-multiplexing creates virtual
    high dimensionality. Here: 2 sensors + Q-diversity = virtual sensors.
    """

    def __init__(self, vocab_size, d_model, H, freqs_hz, Q_values, n_time_samples=8):
        super().__init__()
        n_modes, n_ch = H.shape
        self.n_time_samples = n_time_samples

        # Compute decay profiles at each time sample
        # Time samples: logarithmically spaced from 0.1ms to 5ms
        # (within range where high-Q modes still ring but low-Q are gone)
        t_samples = np.logspace(-4, np.log10(5e-3), n_time_samples)

        # Decay matrix: (n_time_samples, n_modes)
        decay = np.zeros((n_time_samples, n_modes))
        for ti, t in enumerate(t_samples):
            for mi in range(n_modes):
                decay[ti, mi] = np.exp(-np.pi * freqs_hz[mi] * t / Q_values[mi])

        # Effective H at each time: H_eff[t] = diag(decay[t]) @ H
        # Shape: (n_time_samples, n_modes, n_ch)
        H_np = H.numpy() if isinstance(H, torch.Tensor) else np.array(H)
        H_temporal = np.zeros((n_time_samples, n_modes, n_ch))
        for ti in range(n_time_samples):
            H_temporal[ti] = np.diag(decay[ti]) @ H_np

        # Flatten to (n_modes, n_time_samples * n_ch) — full temporal readout
        # But keep as separate H matrices for clarity
        self.register_buffer('H_temporal',
                           torch.tensor(H_temporal, dtype=torch.float32))
        self.register_buffer('decay',
                           torch.tensor(decay, dtype=torch.float32))

        self.output_dim = n_time_samples * n_ch  # 8×2 = 16

        # Learnable parts
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.project_to_modes = nn.Linear(d_model, n_modes)

        # Decoder from temporal readout
        self.decoder = nn.Sequential(
            nn.Linear(self.output_dim, d_model),
            nn.LayerNorm(d_model),
            nn.GELU(),
            nn.Linear(d_model, d_model),
            nn.LayerNorm(d_model),
            nn.GELU(),
            nn.Linear(d_model, vocab_size),
        )

    def forward(self, x):
        emb = self.embedding(x)
        modes = self.project_to_modes(emb)  # (batch, seq, 26)

        # Apply each temporal H
        # modes: (B, S, 26), H_temporal: (T, 26, 2)
        # Result: (B, S, T, 2)
        temporal_outs = torch.einsum('bsm,tmn->bstn', modes, self.H_temporal)

        # Flatten temporal dimension
        temporal_flat = temporal_outs.view(*temporal_outs.shape[:2], -1)  # (B, S, T*2)

        return self.decoder(temporal_flat)


# ═══════════════════════════════════════════════════════════════════
# APPROACH 4: CASCADED H WITH NONLINEARITY (Optical NN)
# ═══════════════════════════════════════════════════════════════════

class CascadedPlateModel(nn.Module):
    """
    Multiple passes through the SAME fixed H with nonlinearities between.

    Inspiration: Shen et al. (2017) photonic deep learning, Wright et al. (2022)
    deep physical neural networks. A single linear multiply is absorbable.
    But: H ∘ σ ∘ L ∘ H ∘ σ ∘ L ∘ H creates a nonlinear function whose
    shape depends on H's specific geometry.

    Architecture (3 passes through H):
      embed → L1(d→26) → H(26→2) → tanh → L2(2→26) → H(26→2) → tanh
            → L3(2→26) → H(26→2) → Linear(2→d) → head

    WHY this differentiates physical from random:
    • After each tanh, the signal is in a H-DEPENDENT region of 2D space
    • The next learnable layer L_k maps this back to 26-dim mode-space
    • But the BOUNDARY where tanh saturates vs. is linear depends on H
    • Different H → different saturation boundaries → different effective functions
    • The composition of 3 H-shaped nonlinearities is NOT equivalent to
      any single linear transformation — algebraic simplification is blocked
    • Physical H (asymmetric B/A ratios) creates asymmetric saturation zones
      that encode mode-specific information about the plate's geometry
    """

    def __init__(self, vocab_size, d_model, H, n_passes=3):
        super().__init__()
        n_modes, n_ch = H.shape
        self.n_passes = n_passes

        # Fixed H applied at each pass (same physical plate, re-used)
        self.register_buffer('H', H)

        self.embedding = nn.Embedding(vocab_size, d_model)

        # First projection into mode-space
        self.project_in = nn.Linear(d_model, n_modes)

        # Intermediate projections: 2→26 (expand back to mode-space between passes)
        self.intermediates = nn.ModuleList([
            nn.Linear(n_ch, n_modes) for _ in range(n_passes - 1)
        ])

        # Final expansion from 2→d_model
        self.expand = nn.Linear(n_ch, d_model)
        self.norm = nn.LayerNorm(d_model)

        # Output head
        self.head = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.Linear(d_model, vocab_size),
        )

    def forward(self, x):
        emb = self.embedding(x)  # (B, S, d)
        modes = self.project_in(emb)  # (B, S, 26)

        # First pass through H
        z = modes @ self.H  # (B, S, 2)
        z = torch.tanh(z)   # Nonlinearity — creates H-dependent features

        # Additional passes: 2→26→H→2→tanh
        for intermediate in self.intermediates:
            modes = intermediate(z)     # (B, S, 26) — back to mode-space
            z = modes @ self.H          # (B, S, 2) — through plate again
            z = torch.tanh(z)           # Nonlinearity again

        # Decode
        out = self.norm(self.expand(z))
        return self.head(out)


# ═══════════════════════════════════════════════════════════════════
# EXPERIMENT RUNNER
# ═══════════════════════════════════════════════════════════════════

def run_approach(name, build_model_fn, H_physical, n_random=5):
    """Run one approach: physical H vs N random H matrices."""
    print(f"\n  [{name}]")
    print("  " + "─" * 60)

    # Physical H
    model_phys = build_model_fn(H_physical)
    n_p = count_params(model_phys)
    print(f"  Params: {n_p:,}")
    print(f"  Physical H:")
    val_phys = train_model(model_phys, args.epochs, args.batch_size, args.seq_len, args.lr)
    ppl_phys = np.exp(val_phys[-1])
    print(f"  → PPL = {ppl_phys:.2f}")

    # Random H (multiple draws)
    ppl_rands = []
    for ri in range(n_random):
        rng_r = np.random.default_rng(ri + 300)
        H_rand = rng_r.standard_normal(H_physical.shape).astype(np.float32)
        H_rand = H_rand * np.linalg.norm(H_physical.numpy()) / np.linalg.norm(H_rand)
        H_rand_t = torch.tensor(H_rand)

        model_rand = build_model_fn(H_rand_t)
        val_r = train_model(model_rand, args.epochs, args.batch_size, args.seq_len, args.lr, verbose=False)
        ppl_r = np.exp(val_r[-1])
        ppl_rands.append(ppl_r)
        print(f"    Random {ri+1}/{n_random}: ppl={ppl_r:.2f}")

    ppl_rand_mean = np.mean(ppl_rands)
    ppl_rand_std = np.std(ppl_rands)
    sigma = (ppl_rand_mean - ppl_phys) / ppl_rand_std if ppl_rand_std > 0 else 0

    print(f"  Random mean: {ppl_rand_mean:.2f} ± {ppl_rand_std:.2f}")
    print(f"  Physical advantage: {sigma:.1f}σ ({'YES' if sigma > 2 else 'marginal' if sigma > 1 else 'no'})")

    return {
        'ppl_physical': float(ppl_phys),
        'ppl_random_mean': float(ppl_rand_mean),
        'ppl_random_std': float(ppl_rand_std),
        'sigma_advantage': float(sigma),
        'params': n_p,
        'val_losses_physical': [float(v) for v in val_phys],
        'ppl_randoms': [float(p) for p in ppl_rands],
    }


# ─── Mode Q values (from lab measurements) ───────────────────────
# Measured Q values per frequency band (interpolated for all 26 modes)
# Data from lab_diary_20260418.md: Q ranges 34-296
# We interpolate for the 26 modes we actually use

Q_measured = {
    11400: 34, 19000: 156, 23900: 168, 29900: 218,
    45000: 108, 47800: 120, 68200: 296, 89400: 126,
}

# Interpolate Q for our 26 modes
Q_values = np.interp(
    freqs,
    sorted(Q_measured.keys()),
    [Q_measured[k] for k in sorted(Q_measured.keys())],
)
# Clip to measured range
Q_values = np.clip(Q_values, 34, 296)

print(f"  Q values (interpolated): {Q_values.min():.0f} – {Q_values.max():.0f}")
print(f"  Decay time range: {1/(np.pi*freqs.min()/Q_values[0])*1000:.2f} – "
      f"{1/(np.pi*freqs.max()/Q_values[-1])*1000:.2f} ms")
print()

# ═══════════════════════════════════════════════════════════════════
# RUN EXPERIMENTS
# ═══════════════════════════════════════════════════════════════════

results = {}
approaches_to_run = ['codebook', 'nonlinear', 'temporal', 'cascaded'] if args.approach == 'all' else [args.approach]

# ── Approach 1: Fixed Codebook ────────────────────────────────────
if 'codebook' in approaches_to_run:
    print("\n" + "=" * 70)
    print("  APPROACH 1: FIXED CODEBOOK (Constellation LM)")
    print("=" * 70)

    # Try multiple codebook strategies
    for strategy in ['hadamard', 'frequency_bands']:
        codebook = make_codebook(vocab_size, n_modes, strategy)

        def build_codebook_model(H, cb=codebook):
            return CodebookPlateModel(vocab_size, args.d_model, H, cb)

        result = run_approach(f"Codebook ({strategy})", build_codebook_model, H_tensor)
        results[f'codebook_{strategy}'] = result

# ── Approach 2: Nonlinear Feature Expansion ───────────────────────
if 'nonlinear' in approaches_to_run:
    print("\n" + "=" * 70)
    print("  APPROACH 2: NONLINEAR FEATURE EXPANSION (Simulated IM)")
    print("=" * 70)

    def build_nonlinear_model(H):
        # Derive coupling matrix from H
        H_rows = H / (torch.norm(H, dim=1, keepdim=True) + 1e-10)
        coupling = H_rows @ H_rows.T
        return NonlinearPlateModel(vocab_size, args.d_model, H, coupling)

    result = run_approach("Nonlinear IM", build_nonlinear_model, H_tensor)
    results['nonlinear_im'] = result

# ── Approach 3: Temporal Readout ──────────────────────────────────
if 'temporal' in approaches_to_run:
    print("\n" + "=" * 70)
    print("  APPROACH 3: DECAY-WEIGHTED TEMPORAL READOUT (Virtual Sensors)")
    print("=" * 70)

    def build_temporal_model(H):
        return TemporalPlateModel(vocab_size, args.d_model, H, freqs, Q_values, n_time_samples=8)

    result = run_approach("Temporal (8 samples)", build_temporal_model, H_tensor)
    results['temporal_decay'] = result

# ── Approach 4: Cascaded H (Optical NN) ──────────────────────────
if 'cascaded' in approaches_to_run:
    print("\n" + "=" * 70)
    print("  APPROACH 4: CASCADED H + NONLINEARITY (Optical NN)")
    print("=" * 70)

    for n_passes in [3, 5]:
        def build_cascaded_model(H, np_=n_passes):
            return CascadedPlateModel(vocab_size, args.d_model, H, n_passes=np_)

        result = run_approach(f"Cascaded ({n_passes} passes)", build_cascaded_model, H_tensor)
        results[f'cascaded_{n_passes}'] = result

# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  L3d SUMMARY: CONSTRAINED-INPUT APPROACHES")
print("=" * 70)
print()
print(f"  {'Approach':<30} {'Phys PPL':>9} {'Rand PPL':>12} {'σ Adv':>7} {'Verdict':>10}")
print(f"  {'─'*30} {'─'*9} {'─'*12} {'─'*7} {'─'*10}")

best_sigma = 0
best_approach = None

for name, r in results.items():
    sigma = r['sigma_advantage']
    if sigma > 2:
        verdict = '★★ YES'
    elif sigma > 1:
        verdict = '★ maybe'
    else:
        verdict = '○ no'

    print(f"  {name:<30} {r['ppl_physical']:>9.2f} {r['ppl_random_mean']:>8.2f}±{r['ppl_random_std']:.2f} {sigma:>7.1f} {verdict:>10}")

    if sigma > best_sigma:
        best_sigma = sigma
        best_approach = name

print()
if best_sigma > 2:
    print(f"  ★★ BREAKTHROUGH: {best_approach} shows physical H advantage at {best_sigma:.1f}σ!")
    print(f"     The plate's structure IS computationally useful when input freedom is constrained.")
elif best_sigma > 1:
    print(f"  ★ PROMISING: {best_approach} shows suggestive advantage ({best_sigma:.1f}σ)")
    print(f"     May need more epochs or refined approach.")
else:
    print(f"  ○ No approach differentiated physical from random.")
    print(f"     The 2-channel rank-2 constraint may be fundamental.")

# ─── Save ─────────────────────────────────────────────────────────
DATA_DIR = Path('data/results/l3_train_through_h')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')

out = {
    'test': 'L3d_constrained_approaches',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'h_matrix_path': str(h_path),
        'approaches': approaches_to_run,
        'd_model': args.d_model, 'epochs': args.epochs,
        'lr': args.lr, 'n_random': args.n_random,
        'vocab_size': vocab_size,
    },
    'results': results,
    'best_approach': best_approach,
    'best_sigma': float(best_sigma) if best_sigma else 0,
}

out_path = DATA_DIR / f'l3d_constrained_{ts}.json'
with open(out_path, 'w') as f:
    json.dump(out, f, indent=2)
print(f"\n  Saved: {out_path}")
