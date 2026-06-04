"""
L3f: Enrollment-Locked Attention — Plate as Fixed Attention Pattern
====================================================================

Key insight (from boolean compute breakthrough):
  L3-L3e all failed because learnable layers BEFORE H absorb its structure.
  Boolean compute succeeded when we stopped treating the plate generically
  and instead LOCKED measurements to enrolled mode frequencies.

  Same principle here: don't learn a projection INTO mode-space.
  Use the enrolled spatial patterns AS the embeddings directly.
  The plate's physical spatial overlaps determine the attention pattern.

Architecture:
  Token(i) → enrolled_mode[i] → 4D spatial signature (FIXED)
  Position(p) → enrolled_mode[p] → 4D spatial signature (FIXED)
  Combined embedding: concat(token_sig, pos_sig) → 8D (ALL FIXED)

  Self-attention:
    Attention weights = f(physical spatial overlap) — FIXED by enrollment
    Values = Linear(embedding) — LEARNABLE
    Output = attn @ values

  Decode: Linear(output) → vocab logits (LEARNABLE)

What's fixed (from physics):  WHO attends to WHOM
What's learned:              WHAT information flows, HOW to decode

Comparison:
  1. Physical: attention from real plate spatial patterns
  2. Random: attention from random 4D vectors (same shape)
  3. Learned: attention from learnable embeddings (upper bound)

Task: 8-digit sequence reversal (same as PDP-11 Attention-11 in transcript)
  Input:  [4, 7, 4, 9, 6, 3, 5, 8]
  Output: [8, 5, 3, 6, 9, 4, 7, 4]

  This requires POSITIONAL routing — position 0 must attend to position 7.
  If the plate's spatial patterns create the right attention landscape,
  physical will outperform random.

Usage:
  python3 tools/l3f_enrollment_locked.py
  python3 tools/l3f_enrollment_locked.py --h-matrix path/to/enrollment.json
  python3 tools/l3f_enrollment_locked.py --epochs 200 --n-train 10000
"""
import argparse
import json
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from pathlib import Path
from datetime import datetime
from itertools import combinations

# ─── Args ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='L3f: Enrollment-Locked Attention')
parser.add_argument('--h-matrix', type=str,
                    default='data/results/h_matrix/multi_plate_enrollment_20260603_171950.json',
                    help='Path to enrollment H matrix JSON')
parser.add_argument('--epochs', type=int, default=200)
parser.add_argument('--batch-size', type=int, default=128)
parser.add_argument('--n-train', type=int, default=50000,
                    help='Number of training examples')
parser.add_argument('--n-val', type=int, default=5000)
parser.add_argument('--d-value', type=int, default=32,
                    help='Value/output dimension (learnable capacity)')
parser.add_argument('--lr', type=float, default=1e-3)
parser.add_argument('--n-random', type=int, default=10,
                    help='Number of random baselines')
parser.add_argument('--seed', type=int, default=42)
parser.add_argument('--task', type=str, default='reversal',
                    choices=['reversal', 'sort', 'shakespeare'],
                    help='Task to solve')
args = parser.parse_args()

torch.manual_seed(args.seed)
np.random.seed(args.seed)

# ─── Load Enrollment Data ─────────────────────────────────────────
print("=" * 70)
print("  L3f: Enrollment-Locked Attention (Plate as Fixed Attention Pattern)")
print("=" * 70)
print()

h_path = Path(args.h_matrix)
with open(h_path) as f:
    h_data = json.load(f)

if 'h_matrix_normalized' in h_data:
    H_norm = np.array(h_data['h_matrix_normalized'])
elif 'H_raw' in h_data:
    H_raw = np.array(h_data['H_raw'])
    H_norm = H_raw / np.linalg.norm(H_raw, axis=1, keepdims=True)
else:
    raise KeyError("No H matrix found in enrollment data")

freqs = h_data.get('mode_frequencies_hz', list(range(H_norm.shape[0])))
n_modes, n_channels = H_norm.shape

print(f"  Enrollment: {n_modes} modes × {n_channels} spatial channels")
print(f"  Frequencies: {freqs[0]/1000:.0f}–{freqs[-1]/1000:.0f} kHz")
print(f"  Task: {args.task}")
print()

# ─── Create SIGNED spatial features from enrollment ───────────────
# Raw enrollment = amplitudes (all positive) → dot products all positive
# → softmax ≈ uniform → no useful routing!
#
# Fix: Build CONTRAST features that have both positive AND negative values.
# These capture the RELATIVE spatial structure (which channels are strong
# vs weak for each mode) — the physically meaningful information.
#
# Feature set per mode (8D):
#   [centered_ch0, centered_ch1, centered_ch2, centered_ch3,
#    ch0-ch1 (plate I contrast), ch2-ch3 (plate H contrast),
#    ch0-ch2 (NW cross-plate),   ch1-ch3 (NE cross-plate)]

def build_signed_features(H):
    """Convert positive amplitude patterns to signed contrast features."""
    n, c = H.shape
    # Center each pattern (zero mean per mode)
    centered = H - H.mean(axis=1, keepdims=True)
    # Inter-channel contrasts
    contrasts = np.column_stack([
        H[:, 0] - H[:, 1],  # Plate I: NW vs NE
        H[:, 2] - H[:, 3],  # Plate H: NW vs NE
        H[:, 0] - H[:, 2],  # Cross-plate: NW
        H[:, 1] - H[:, 3],  # Cross-plate: NE
    ])
    features = np.concatenate([centered, contrasts], axis=1)  # (n, 8)
    # Normalize to unit length
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    features = features / (norms + 1e-10)
    return features

H_signed = build_signed_features(H_norm)
n_feat = H_signed.shape[1]
print(f"  Signed features: {n_feat}D per mode (centered + contrasts)")

# Verify diversity improved
angles_raw = []
angles_signed = []
for i in range(min(10, n_modes)):
    for j in range(i+1, min(10, n_modes)):
        cos_raw = np.dot(H_norm[i], H_norm[j])
        cos_sig = np.dot(H_signed[i], H_signed[j])
        angles_raw.append(np.degrees(np.arccos(np.clip(cos_raw, -1, 1))))
        angles_signed.append(np.degrees(np.arccos(np.clip(cos_sig, -1, 1))))
print(f"  Angular diversity (first 10 modes):")
print(f"    Raw amplitudes: {np.mean(angles_raw):.1f}° mean, {np.max(angles_raw):.1f}° max")
print(f"    Signed features: {np.mean(angles_signed):.1f}° mean, {np.max(angles_signed):.1f}° max")
print()


# ─── Mode Assignment (maximize diversity) ──────────────────────────
def pairwise_angles(patterns):
    """Compute pairwise angles between spatial patterns (degrees)."""
    n = len(patterns)
    angles = np.zeros((n, n))
    for i in range(n):
        for j in range(i+1, n):
            cos_a = np.dot(patterns[i], patterns[j]) / (
                np.linalg.norm(patterns[i]) * np.linalg.norm(patterns[j]) + 1e-10)
            angles[i,j] = angles[j,i] = np.degrees(np.arccos(np.clip(cos_a, -1, 1)))
    return angles


def select_diverse_modes(H, n_select, exclude_indices=None):
    """Greedily select modes with maximum pairwise angular diversity."""
    available = list(range(len(H)))
    if exclude_indices:
        available = [i for i in available if i not in exclude_indices]

    if n_select > len(available):
        raise ValueError(f"Need {n_select} modes but only {len(available)} available")

    # Start with the two most different modes
    best_pair = None
    best_angle = -1
    for i, j in combinations(available, 2):
        cos_a = np.dot(H[i], H[j]) / (np.linalg.norm(H[i]) * np.linalg.norm(H[j]) + 1e-10)
        angle = np.degrees(np.arccos(np.clip(cos_a, -1, 1)))
        if angle > best_angle:
            best_angle = angle
            best_pair = (i, j)

    selected = list(best_pair)

    # Greedily add modes that maximize minimum angle to already-selected
    while len(selected) < n_select:
        best_idx = None
        best_min_angle = -1
        for i in available:
            if i in selected:
                continue
            min_angle = float('inf')
            for s in selected:
                cos_a = np.dot(H[i], H[s]) / (np.linalg.norm(H[i]) * np.linalg.norm(H[s]) + 1e-10)
                angle = np.degrees(np.arccos(np.clip(cos_a, -1, 1)))
                min_angle = min(min_angle, angle)
            if min_angle > best_min_angle:
                best_min_angle = min_angle
                best_idx = i
        selected.append(best_idx)

    return selected


# Need: 8 position modes + 10 token modes = 18 modes from 27 available
# Positions are most critical for reversal — assign the most diverse modes
# Use SIGNED features for diversity selection AND as embeddings
print("  [1] Mode assignment (maximize angular diversity on signed features)...")

pos_mode_indices = select_diverse_modes(H_signed, 8)
tok_mode_indices = select_diverse_modes(H_signed, 10, exclude_indices=pos_mode_indices)

pos_patterns = H_signed[pos_mode_indices]  # (8, 8) — signed features
tok_patterns = H_signed[tok_mode_indices]  # (10, 8) — signed features

print(f"  Position modes ({len(pos_mode_indices)}):")
for p, idx in enumerate(pos_mode_indices):
    pat = H_signed[idx]
    print(f"    pos[{p}] → mode {idx} ({freqs[idx]/1000:.0f} kHz) "
          f"feat=[{', '.join(f'{v:.2f}' for v in pat[:4])}...]")

pos_angles = pairwise_angles(pos_patterns)
print(f"  Position pairwise angles: min={pos_angles[pos_angles>0].min():.1f}°, "
      f"mean={pos_angles[pos_angles>0].mean():.1f}°, "
      f"max={pos_angles.max():.1f}°")

print(f"\n  Token modes ({len(tok_mode_indices)}):")
for t, idx in enumerate(tok_mode_indices):
    print(f"    tok[{t}] → mode {idx} ({freqs[idx]/1000:.0f} kHz)")

tok_angles = pairwise_angles(tok_patterns)
print(f"  Token pairwise angles: min={tok_angles[tok_angles>0].min():.1f}°, "
      f"mean={tok_angles[tok_angles>0].mean():.1f}°, "
      f"max={tok_angles.max():.1f}°")
print()


# ─── Generate Data ────────────────────────────────────────────────
SEQ_LEN = 8
VOCAB = 10

def generate_reversal_data(n_samples):
    """Generate digit reversal examples."""
    x = torch.randint(0, VOCAB, (n_samples, SEQ_LEN))
    y = x.flip(dims=[1])
    return x, y

def generate_sort_data(n_samples):
    """Generate digit sorting examples."""
    x = torch.randint(0, VOCAB, (n_samples, SEQ_LEN))
    y, _ = x.sort(dim=1)
    return x, y

print(f"  [2] Generating data ({args.task})...")
if args.task == 'reversal':
    train_x, train_y = generate_reversal_data(args.n_train)
    val_x, val_y = generate_reversal_data(args.n_val)
elif args.task == 'sort':
    train_x, train_y = generate_sort_data(args.n_train)
    val_x, val_y = generate_sort_data(args.n_val)
else:
    raise NotImplementedError(f"Task {args.task} not yet implemented in L3f")

print(f"  Train: {args.n_train}, Val: {args.n_val}")
print(f"  Example: {train_x[0].tolist()} → {train_y[0].tolist()}")
print()


# ─── Model ────────────────────────────────────────────────────────

class EnrollmentLockedAttention(nn.Module):
    """
    Attention model where the attention PATTERN is fixed by plate physics.

    The plate's enrolled spatial patterns (signed contrast features) determine
    WHO attends to WHOM. Only the value transform and output head are learnable.

    This breaks absorption because there is NO learnable layer between
    tokens and the attention weights. The optimizer cannot rotate inputs
    to make all H matrices equivalent.

    V2 fix: Uses SIGNED features (centered + contrasts) instead of raw
    amplitudes to create meaningful angular diversity for attention routing.
    """

    def __init__(self, vocab_size, seq_len, tok_patterns, pos_patterns, d_value):
        super().__init__()
        n_tok, n_feat = tok_patterns.shape
        n_pos, _ = pos_patterns.shape

        # FIXED embeddings from plate enrollment (not learnable!)
        self.register_buffer('tok_emb', torch.tensor(tok_patterns, dtype=torch.float32))
        self.register_buffer('pos_emb', torch.tensor(pos_patterns, dtype=torch.float32))

        # Combined embedding dimension: token features + position features
        d_emb = n_feat * 2  # concat(token_spatial, position_spatial) = 16D

        # Value projection: the ONLY learnable transform applied to the embedding
        self.value_proj = nn.Linear(d_emb, d_value)

        # Learnable temperature for attention (scalar — can't break structure)
        self.log_temperature = nn.Parameter(torch.tensor(0.0))

        # Output head (with LayerNorm for stability)
        self.layer_norm = nn.LayerNorm(d_value)
        self.output_head = nn.Sequential(
            nn.Linear(d_value, d_value * 4),
            nn.GELU(),
            nn.Linear(d_value * 4, vocab_size),
        )

        self.d_emb = d_emb
        self.n_feat = n_feat

    def forward(self, x):
        """
        x: (batch, seq_len) — token indices

        Returns: (batch, seq_len, vocab_size) logits
        """
        batch, seq_len = x.shape

        # Build combined embeddings: concat(token_spatial, position_spatial)
        # Token embeddings: lookup from FIXED enrollment table
        tok_e = self.tok_emb[x]  # (batch, seq, n_feat)

        # Position embeddings: FIXED for each position
        pos_e = self.pos_emb[:seq_len].unsqueeze(0).expand(batch, -1, -1)  # (batch, seq, n_feat)

        # Combined: (batch, seq, 2*n_feat = 16D)
        combined = torch.cat([tok_e, pos_e], dim=-1)

        # Attention from physical spatial overlap (enrollment-locked)
        # attn[i,j] = combined[i] · combined[j] — this IS the plate's physics
        temperature = torch.exp(self.log_temperature) + 0.1  # prevent collapse
        attn_logits = torch.bmm(combined, combined.transpose(1, 2)) / (
            self.d_emb ** 0.5 * temperature)
        attn_weights = F.softmax(attn_logits, dim=-1)  # (batch, seq, seq)

        # Values: learnable projection of fixed embeddings
        values = self.value_proj(combined)  # (batch, seq, d_value)

        # Attended output
        out = torch.bmm(attn_weights, values)  # (batch, seq, d_value)

        # Normalize and decode
        out = self.layer_norm(out)
        logits = self.output_head(out)  # (batch, seq, vocab_size)
        return logits


# ─── Training ─────────────────────────────────────────────────────

def train_model(model, train_x, train_y, val_x, val_y, epochs, batch_size, lr, verbose=True):
    """Train and return (final_accuracy, loss_history, acc_history)."""
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    n_train = len(train_x)
    best_acc = 0.0
    acc_history = []
    loss_history = []

    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(n_train)
        epoch_loss = 0
        n_batches = 0

        for i in range(0, n_train, batch_size):
            idx = perm[i:i+batch_size]
            bx, by = train_x[idx], train_y[idx]

            logits = model(bx)
            loss = F.cross_entropy(logits.view(-1, VOCAB), by.view(-1))

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        scheduler.step()
        train_loss = epoch_loss / n_batches
        loss_history.append(train_loss)

        # Validation accuracy
        model.eval()
        with torch.no_grad():
            logits = model(val_x)
            preds = logits.argmax(dim=-1)
            # Per-sequence accuracy (all 8 positions correct)
            seq_correct = (preds == val_y).all(dim=1).float().mean().item()
            # Per-token accuracy
            tok_correct = (preds == val_y).float().mean().item()
            acc_history.append(seq_correct)
            best_acc = max(best_acc, seq_correct)

        if verbose and ((epoch + 1) % 20 == 0 or epoch == 0 or seq_correct > 0.99):
            print(f"    Epoch {epoch+1:>3}/{epochs}: loss={train_loss:.4f}, "
                  f"seq_acc={seq_correct*100:.1f}%, tok_acc={tok_correct*100:.1f}%")
            if seq_correct > 0.99:
                break

    return best_acc, loss_history, acc_history


def count_params(model, trainable_only=True):
    if trainable_only:
        return sum(p.numel() for p in model.parameters() if p.requires_grad)
    return sum(p.numel() for p in model.parameters())


# ─── Run Experiments ──────────────────────────────────────────────

results = {}

# 1. Physical H model (attention locked to plate enrollment)
print("  [3] PHYSICAL ENROLLMENT-LOCKED MODEL")
print("  " + "-" * 50)
model_phys = EnrollmentLockedAttention(
    VOCAB, SEQ_LEN, tok_patterns, pos_patterns, args.d_value)
n_params = count_params(model_phys)
print(f"  Trainable params: {n_params:,}")
n_fixed = sum(b.numel() for b in model_phys.buffers())
print(f"  Fixed params: {n_fixed:,} (from enrollment)")

acc_phys, loss_phys, acchist_phys = train_model(
    model_phys, train_x, train_y, val_x, val_y,
    args.epochs, args.batch_size, args.lr)
print(f"  Best sequence accuracy: {acc_phys*100:.1f}%")
print()

# 2. Random baselines (same architecture, random spatial patterns)
print(f"  [4] RANDOM BASELINES ({args.n_random} random pattern sets)")
print("  " + "-" * 50)
acc_randoms = []
best_random_acc = 0
best_random_loss = None

for ri in range(args.n_random):
    # Generate random patterns with same shape and normalization (signed, unit-norm)
    rand_tok = np.random.randn(10, n_feat).astype(np.float32)
    rand_tok = rand_tok / (np.linalg.norm(rand_tok, axis=1, keepdims=True) + 1e-10)
    rand_pos = np.random.randn(8, n_feat).astype(np.float32)
    rand_pos = rand_pos / (np.linalg.norm(rand_pos, axis=1, keepdims=True) + 1e-10)

    model_rand = EnrollmentLockedAttention(
        VOCAB, SEQ_LEN, rand_tok, rand_pos, args.d_value)

    acc_r, loss_r, _ = train_model(
        model_rand, train_x, train_y, val_x, val_y,
        args.epochs, args.batch_size, args.lr, verbose=False)
    acc_randoms.append(acc_r)

    if acc_r > best_random_acc:
        best_random_acc = acc_r
        best_random_loss = loss_r

    if (ri + 1) % 5 == 0:
        print(f"    {ri+1}/{args.n_random}: acc={acc_r*100:.1f}% "
              f"(running mean={np.mean(acc_randoms)*100:.1f}%)")

acc_rand_mean = np.mean(acc_randoms)
acc_rand_std = np.std(acc_randoms)
print(f"  Random accuracies: {[f'{a*100:.1f}%' for a in acc_randoms]}")
print(f"  Mean: {acc_rand_mean*100:.1f}% ± {acc_rand_std*100:.1f}%")
print()

# 3. Fully learnable attention (upper bound — embeddings are trainable)
print("  [5] FULLY LEARNABLE BASELINE (upper bound)")
print("  " + "-" * 50)


class LearnableAttentionModel(nn.Module):
    """Same architecture but embeddings are LEARNABLE (not from plate)."""

    def __init__(self, vocab_size, seq_len, n_feat, d_value):
        super().__init__()
        # Learnable embeddings (NOT from plate)
        self.tok_emb = nn.Embedding(vocab_size, n_feat)
        self.pos_emb = nn.Parameter(torch.randn(seq_len, n_feat) * 0.1)
        d_emb = n_feat * 2

        self.value_proj = nn.Linear(d_emb, d_value)
        self.log_temperature = nn.Parameter(torch.tensor(0.0))
        self.layer_norm = nn.LayerNorm(d_value)
        self.output_head = nn.Sequential(
            nn.Linear(d_value, d_value * 4),
            nn.GELU(),
            nn.Linear(d_value * 4, vocab_size),
        )
        self.d_emb = d_emb

    def forward(self, x):
        batch, seq_len = x.shape
        tok_e = self.tok_emb(x)
        pos_e = self.pos_emb[:seq_len].unsqueeze(0).expand(batch, -1, -1)
        combined = torch.cat([tok_e, pos_e], dim=-1)

        temperature = torch.exp(self.log_temperature) + 0.1
        attn_logits = torch.bmm(combined, combined.transpose(1, 2)) / (
            self.d_emb ** 0.5 * temperature)
        attn_weights = F.softmax(attn_logits, dim=-1)

        values = self.value_proj(combined)
        out = torch.bmm(attn_weights, values)
        out = self.layer_norm(out)
        logits = self.output_head(out)
        return logits


model_learn = LearnableAttentionModel(VOCAB, SEQ_LEN, n_feat, args.d_value)
n_params_learn = count_params(model_learn)
print(f"  Trainable params: {n_params_learn:,}")

acc_learn, loss_learn, acchist_learn = train_model(
    model_learn, train_x, train_y, val_x, val_y,
    args.epochs, args.batch_size, args.lr)
print(f"  Best sequence accuracy: {acc_learn*100:.1f}%")
print()

# 4. Shuffled-H (same magnitudes, destroy spatial structure)
print("  [6] SHUFFLED ENROLLMENT (destroy spatial structure)")
print("  " + "-" * 50)
acc_shuffled = []
for si in range(5):
    # Shuffle columns independently per row (destroys spatial relationships)
    shuf_tok = tok_patterns.copy()
    shuf_pos = pos_patterns.copy()
    for row in range(len(shuf_tok)):
        np.random.shuffle(shuf_tok[row])
    for row in range(len(shuf_pos)):
        np.random.shuffle(shuf_pos[row])

    model_shuf = EnrollmentLockedAttention(
        VOCAB, SEQ_LEN, shuf_tok, shuf_pos, args.d_value)
    acc_s, _, _ = train_model(
        model_shuf, train_x, train_y, val_x, val_y,
        args.epochs, args.batch_size, args.lr, verbose=False)
    acc_shuffled.append(acc_s)

acc_shuf_mean = np.mean(acc_shuffled)
acc_shuf_std = np.std(acc_shuffled)
print(f"  Shuffled accuracies: {[f'{a*100:.1f}%' for a in acc_shuffled]}")
print(f"  Mean: {acc_shuf_mean*100:.1f}% ± {acc_shuf_std*100:.1f}%")
print()

# ─── Statistical Test ─────────────────────────────────────────────
print("  [7] Statistical comparison...")
sigma_vs_random = (acc_phys - acc_rand_mean) / (acc_rand_std + 1e-10)
sigma_vs_shuffled = (acc_phys - acc_shuf_mean) / (acc_shuf_std + 1e-10)
print(f"  Physical vs Random:   {acc_phys*100:.1f}% vs {acc_rand_mean*100:.1f}±{acc_rand_std*100:.1f}%  "
      f"(σ = {sigma_vs_random:+.1f})")
print(f"  Physical vs Shuffled: {acc_phys*100:.1f}% vs {acc_shuf_mean*100:.1f}±{acc_shuf_std*100:.1f}%  "
      f"(σ = {sigma_vs_shuffled:+.1f})")
print(f"  Learnable (ceiling):  {acc_learn*100:.1f}%")
print()

# ─── Attention Pattern Analysis ───────────────────────────────────
print("  [8] Attention pattern analysis (physical model)...")
model_phys.eval()
with torch.no_grad():
    # Use a sample input to see what the physical attention looks like
    sample_x = torch.arange(8).unsqueeze(0)  # [0,1,2,3,4,5,6,7]
    tok_e = model_phys.tok_emb[sample_x]
    pos_e = model_phys.pos_emb[:8].unsqueeze(0)
    combined = torch.cat([tok_e, pos_e], dim=-1)
    temp = torch.exp(model_phys.log_temperature) + 0.1
    attn_logits = torch.bmm(combined, combined.transpose(1, 2)) / (
        model_phys.d_emb ** 0.5 * temp)
    attn = F.softmax(attn_logits, dim=-1)[0]

    print(f"  Attention matrix for input [0,1,2,3,4,5,6,7]:")
    print(f"  (rows=query position, cols=key position)")
    print(f"  {'':>4}", end='')
    for j in range(8):
        print(f"  p{j:d}  ", end='')
    print()
    for i in range(8):
        print(f"  p{i}: ", end='')
        for j in range(8):
            v = attn[i, j].item()
            marker = '█' if v > 0.2 else '▓' if v > 0.1 else '░' if v > 0.05 else ' '
            print(f"{v:.2f}{marker}", end=' ')
        print()

    # For reversal: ideal attention is anti-diagonal
    anti_diag_strength = sum(attn[i, 7-i].item() for i in range(8)) / 8
    diag_strength = sum(attn[i, i].item() for i in range(8)) / 8
    print(f"\n  Anti-diagonal mean (ideal for reversal): {anti_diag_strength:.3f}")
    print(f"  Diagonal mean (self-attention): {diag_strength:.3f}")
print()

# ─── Final Results ────────────────────────────────────────────────
print("=" * 70)
print("  L3f RESULTS: ENROLLMENT-LOCKED ATTENTION")
print("=" * 70)
print()
print(f"  Task:           {args.task} (8 digits)")
print(f"  Architecture:   Fixed attention from plate enrollment")
print(f"  Learnable:      Value projection + output head only ({n_params:,} params)")
print(f"  Fixed:          Token/position embeddings from enrolled spatial patterns")
print()
print(f"  {'Model':<30} {'Accuracy':>10} {'vs Physical':>12}")
print(f"  {'-'*30} {'-'*10} {'-'*12}")
print(f"  {'Physical (enrolled)':<30} {acc_phys*100:>9.1f}% {'—':>12}")
print(f"  {'Random (mean±std)':<30} {acc_rand_mean*100:>9.1f}% {f'{sigma_vs_random:+.1f}σ':>12}")
print(f"  {'Shuffled (mean±std)':<30} {acc_shuf_mean*100:>9.1f}% {f'{sigma_vs_shuffled:+.1f}σ':>12}")
print(f"  {'Learnable (ceiling)':<30} {acc_learn*100:>9.1f}% {'':>12}")
print()

# Verdict
if sigma_vs_random > 2.0:
    verdict = 'PASS'
    print(f"  ★★ PASS — Physical enrollment outperforms random at {sigma_vs_random:.1f}σ!")
    print(f"  The plate's spatial structure provides a USEFUL attention pattern.")
    print(f"  Enrollment-locking prevents absorption — physics matters!")
elif sigma_vs_random > 1.0:
    verdict = 'MARGINAL'
    print(f"  △ MARGINAL — Physical > random at {sigma_vs_random:.1f}σ (need >2σ)")
elif acc_phys > acc_rand_mean:
    verdict = 'WEAK'
    print(f"  ○ WEAK — Physical slightly better but not significant ({sigma_vs_random:.1f}σ)")
else:
    verdict = 'FAIL'
    print(f"  ✗ FAIL — Physical ≤ random ({sigma_vs_random:.1f}σ)")

# ─── Save Results ─────────────────────────────────────────────────
DATA_DIR = Path('data/results/l3_train_through_h')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')

out = {
    'test': 'L3f_enrollment_locked_attention',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'h_matrix_path': str(h_path),
        'task': args.task,
        'seq_len': SEQ_LEN,
        'vocab_size': VOCAB,
        'd_value': args.d_value,
        'epochs': args.epochs,
        'batch_size': args.batch_size,
        'lr': args.lr,
        'n_train': args.n_train,
        'n_val': args.n_val,
        'n_random': args.n_random,
        'n_modes_total': n_modes,
        'n_channels': n_channels,
    },
    'mode_assignment': {
        'position_mode_indices': pos_mode_indices,
        'position_frequencies_hz': [freqs[i] for i in pos_mode_indices],
        'token_mode_indices': tok_mode_indices,
        'token_frequencies_hz': [freqs[i] for i in tok_mode_indices],
    },
    'results': {
        'physical': {
            'best_accuracy': float(acc_phys),
            'params': n_params,
            'loss_history': [float(x) for x in loss_phys],
            'acc_history': [float(x) for x in acchist_phys],
        },
        'random': {
            'accuracies': [float(a) for a in acc_randoms],
            'mean': float(acc_rand_mean),
            'std': float(acc_rand_std),
            'best': float(best_random_acc),
        },
        'shuffled': {
            'accuracies': [float(a) for a in acc_shuffled],
            'mean': float(acc_shuf_mean),
            'std': float(acc_shuf_std),
        },
        'learnable': {
            'best_accuracy': float(acc_learn),
            'params': n_params_learn,
        },
    },
    'statistics': {
        'sigma_vs_random': float(sigma_vs_random),
        'sigma_vs_shuffled': float(sigma_vs_shuffled),
    },
    'verdict': verdict,
}

out_path = DATA_DIR / f'l3f_enrollment_locked_{ts}.json'
with open(out_path, 'w') as f:
    json.dump(out, f, indent=2)
print(f"\n  Saved: {out_path}")
print("\n  Done.")
