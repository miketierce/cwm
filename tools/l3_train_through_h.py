"""
L3: Train-Through-H — End-to-End Language Model with Physical Transfer Matrix
==============================================================================

Demonstrates that the plate's measured transfer matrix H (26×2) is
computationally useful by incorporating it as a fixed (non-trainable)
layer in a small language model.

Architecture:
  Token → Embedding(vocab, d_model) → Linear(d_model, 26) → H_physical(26×2)
       → Linear(2, d_model) → LayerNorm → Linear(d_model, vocab) → Softmax

The plate H acts as an analog attention-like projection:
  - Input: 26-dim vector (one component per plate eigenmode)
  - Output: 2-dim vector (one per spatial receiver channel)
  - H encodes the plate's physical transfer function (mode → space mapping)
  - H is FIXED (non-trainable) — represents the physical hardware

Comparison:
  1. Physical model: H fixed from plate measurement
  2. Trainable baseline: same architecture, but the 26→2 layer is trainable
  3. Random baseline: H replaced with random matrix (same shape/norm)

Success criterion: Physical model converges and achieves perplexity within
2× of fully-trainable baseline (same architecture, same data).

Dataset: Shakespeare character-level (small, fits in memory, standard benchmark)

Usage:
  python3 tools/l3_train_through_h.py
  python3 tools/l3_train_through_h.py --epochs 50 --dataset tinyshakespeare
  python3 tools/l3_train_through_h.py --h-matrix path/to/h_matrix.json
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
parser = argparse.ArgumentParser(description='L3: Train-Through-H')
parser.add_argument('--h-matrix', type=str,
                    default='data/results/h_matrix/l1_h_matrix_20260602_220004.json',
                    help='Path to L1 H matrix JSON')
parser.add_argument('--epochs', type=int, default=30,
                    help='Training epochs (default: 30)')
parser.add_argument('--batch-size', type=int, default=64,
                    help='Batch size (default: 64)')
parser.add_argument('--seq-len', type=int, default=64,
                    help='Sequence length (default: 64)')
parser.add_argument('--d-model', type=int, default=64,
                    help='Model dimension (default: 64)')
parser.add_argument('--lr', type=float, default=3e-3,
                    help='Learning rate (default: 3e-3)')
parser.add_argument('--seed', type=int, default=42)
args = parser.parse_args()

torch.manual_seed(args.seed)
np.random.seed(args.seed)

# ─── Load H Matrix ───────────────────────────────────────────────
print("=" * 70)
print("  L3: Train-Through-H — Physical Transfer Matrix as Attention Layer")
print("=" * 70)
print()

h_path = Path(args.h_matrix)
with open(h_path) as f:
    h_data = json.load(f)

# Support both L1 format ('H_raw') and enrollment format ('h_matrix_raw')
if 'H_raw' in h_data:
    H_raw = np.array(h_data['H_raw'])
elif 'h_matrix_raw' in h_data:
    H_raw = np.array(h_data['h_matrix_raw'])
else:
    raise KeyError(f"H matrix not found in {h_path}. Expected 'H_raw' or 'h_matrix_raw' key.")

n_modes, n_channels = H_raw.shape
print(f"  H matrix: {n_modes}×{n_channels} (from {h_path.name})")
print(f"  Modes: {n_modes} ({h_data['config']['start_hz']/1000:.0f}–"
      f"{h_data['config']['stop_hz']/1000:.0f} kHz)")

# Normalize H: each row to unit norm (preserves relative spatial ratios)
H_norm = H_raw / np.linalg.norm(H_raw, axis=1, keepdims=True)
# Scale so Frobenius norm = sqrt(n_modes) (similar energy to random init)
H_norm = H_norm * np.sqrt(n_modes) / np.linalg.norm(H_norm, 'fro')

H_tensor = torch.tensor(H_norm, dtype=torch.float32)
print(f"  H Frobenius norm: {torch.norm(H_tensor):.3f}")
cond = h_data.get('condition_number') or h_data.get('svd', {}).get('condition_number', 'N/A')
print(f"  H condition number: {cond}")

# SVD of normalized H
U, S, Vh = torch.linalg.svd(H_tensor, full_matrices=False)
sv_str = ', '.join([f'{s:.3f}' for s in S])
print(f"  H SVD singular values: [{sv_str}]")
print(f"  H effective rank: {(S > S[0]*0.01).sum().item()}")
print(f"  Bottleneck: {n_modes}→{n_channels} (rank-{n_channels})")
print()

# ─── Dataset: Generate synthetic or load Shakespeare ──────────────
DATA_DIR = Path('data')

# Use a simple synthetic corpus if Shakespeare not available
SHAKESPEARE_PATH = DATA_DIR / 'tinyshakespeare.txt'
if not SHAKESPEARE_PATH.exists():
    print("  Downloading tiny Shakespeare...")
    import urllib.request
    url = 'https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt'
    urllib.request.urlretrieve(url, SHAKESPEARE_PATH)
    print(f"  Saved: {SHAKESPEARE_PATH}")

with open(SHAKESPEARE_PATH, 'r') as f:
    text = f.read()

# Character-level tokenization
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
print(f"  Train: {n_train:,}, Val: {n_total - n_train:,}")
print()


def get_batch(split, batch_size, seq_len):
    d = train_data if split == 'train' else val_data
    ix = torch.randint(len(d) - seq_len - 1, (batch_size,))
    x = torch.stack([d[i:i + seq_len] for i in ix])
    y = torch.stack([d[i + 1:i + seq_len + 1] for i in ix])
    return x, y


# ─── Model ────────────────────────────────────────────────────────

class PlateAttentionModel(nn.Module):
    """Language model where ALL information flows through the plate H.

    Architecture (NO residual bypass — H is the bottleneck):
      embed(token) → project_to_modes(d_model → 26) → H_plate(26 → 2)
      → expand(2 → d_model) → MLP → output_head(d_model → vocab)

    By removing the residual connection, the model MUST use H to pass
    information. If physical H outperforms random H, its structure is useful.
    """

    def __init__(self, vocab_size, d_model, H_fixed, trainable_H=False):
        super().__init__()
        n_modes, n_ch = H_fixed.shape

        self.embedding = nn.Embedding(vocab_size, d_model)
        self.project_to_modes = nn.Linear(d_model, n_modes)

        # The plate transfer matrix — fixed or trainable
        self.H = nn.Parameter(H_fixed.clone(), requires_grad=trainable_H)

        # Expand from channel-space back to model-space
        self.expand = nn.Linear(n_ch, d_model)
        self.norm = nn.LayerNorm(d_model)

        # MLP after plate (gives model capacity to learn around bottleneck)
        self.mlp = nn.Sequential(
            nn.Linear(d_model, d_model * 2),
            nn.GELU(),
            nn.Linear(d_model * 2, d_model),
        )
        self.norm2 = nn.LayerNorm(d_model)

        # Output head
        self.head = nn.Linear(d_model, vocab_size)

    def forward(self, x):
        # x: (batch, seq_len) token indices
        emb = self.embedding(x)  # (batch, seq, d_model)

        # Project to mode-space (input to plate)
        modes = self.project_to_modes(emb)  # (batch, seq, 26)

        # Physical plate computation: H × mode_vector
        # ALL information must pass through this 26→2 bottleneck
        plate_out = modes @ self.H  # (batch, seq, 2) — the plate output

        # Expand back to model dimension (NO residual — forced through H)
        expanded = self.norm(self.expand(plate_out))  # (batch, seq, d_model)

        # MLP for additional capacity
        out = self.norm2(expanded + self.mlp(expanded))

        # Predict next token
        logits = self.head(out)  # (batch, seq, vocab)
        return logits


# ─── Training ─────────────────────────────────────────────────────

def train_model(model, name, epochs, batch_size, seq_len, lr):
    """Train a model and return loss history."""
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    train_losses = []
    val_losses = []

    steps_per_epoch = max(1, n_train // (batch_size * seq_len))

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
        train_loss = epoch_loss / n_batches
        train_losses.append(train_loss)

        # Validation
        model.eval()
        with torch.no_grad():
            val_loss_sum = 0
            n_val = 0
            for _ in range(20):
                x, y = get_batch('val', batch_size, seq_len)
                logits = model(x)
                val_loss_sum += F.cross_entropy(logits.view(-1, vocab_size), y.view(-1)).item()
                n_val += 1
            val_loss = val_loss_sum / n_val
            val_losses.append(val_loss)

        if (epoch + 1) % 5 == 0 or epoch == 0:
            ppl = np.exp(val_loss)
            print(f"    Epoch {epoch+1:>3}/{epochs}: "
                  f"train={train_loss:.4f}, val={val_loss:.4f}, ppl={ppl:.1f}")

    return train_losses, val_losses


def count_params(model, trainable_only=True):
    if trainable_only:
        return sum(p.numel() for p in model.parameters() if p.requires_grad)
    return sum(p.numel() for p in model.parameters())


# ─── Run experiments ──────────────────────────────────────────────

results = {}

# 1. Physical H model (H fixed from plate measurement)
print("  [1] PHYSICAL H MODEL (H fixed, non-trainable)")
print("  " + "-" * 50)
model_phys = PlateAttentionModel(vocab_size, args.d_model, H_tensor, trainable_H=False)
n_params_phys = count_params(model_phys)
print(f"  Trainable params: {n_params_phys:,}")
train_l_phys, val_l_phys = train_model(
    model_phys, 'physical', args.epochs, args.batch_size, args.seq_len, args.lr)
ppl_phys = np.exp(val_l_phys[-1])
print(f"  Final perplexity: {ppl_phys:.2f}")
print()

# 2. Trainable baseline (same architecture, H is trainable)
print("  [2] TRAINABLE BASELINE (same architecture, H learnable)")
print("  " + "-" * 50)
model_train = PlateAttentionModel(vocab_size, args.d_model, H_tensor, trainable_H=True)
n_params_train = count_params(model_train)
print(f"  Trainable params: {n_params_train:,} (+{n_params_train - n_params_phys} from H)")
train_l_train, val_l_train = train_model(
    model_train, 'trainable', args.epochs, args.batch_size, args.seq_len, args.lr)
ppl_train = np.exp(val_l_train[-1])
print(f"  Final perplexity: {ppl_train:.2f}")
print()

# 3. Random H baselines (5 random matrices, average performance)
print("  [3] RANDOM H BASELINES (5 random fixed matrices, same shape)")
print("  " + "-" * 50)
ppl_rands = []
val_l_rand_best = None
for ri in range(5):
    H_random = torch.randn_like(H_tensor)
    H_random = H_random * torch.norm(H_tensor) / torch.norm(H_random)
    model_rand = PlateAttentionModel(vocab_size, args.d_model, H_random, trainable_H=False)
    if ri == 0:
        n_params_rand = count_params(model_rand)
        print(f"  Trainable params: {n_params_rand:,} (each)")
    _, val_l_r = train_model(
        model_rand, f'random_{ri}', args.epochs, args.batch_size, args.seq_len, args.lr)
    ppl_r = np.exp(val_l_r[-1])
    ppl_rands.append(ppl_r)
    if val_l_rand_best is None or val_l_r[-1] < val_l_rand_best[-1]:
        val_l_rand_best = val_l_r
        train_l_rand = _
ppl_rand = np.mean(ppl_rands)
ppl_rand_std = np.std(ppl_rands)
val_l_rand = val_l_rand_best
print(f"  Random H perplexities: {['%.2f' % p for p in ppl_rands]}")
print(f"  Mean: {ppl_rand:.2f} ± {ppl_rand_std:.2f}")
print()

# 4. No-H baseline (skip plate layer entirely, just embed→head)
print("  [4] NO-H BASELINE (skip plate layer, embed→MLP→vocab)")
print("  " + "-" * 50)


class DirectModel(nn.Module):
    """Baseline: same parameter budget, no plate layer."""
    def __init__(self, vocab_size, d_model):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.norm = nn.LayerNorm(d_model)
        self.head = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.Linear(d_model, vocab_size),
        )

    def forward(self, x):
        emb = self.embedding(x)
        out = self.norm(emb)
        return self.head(out)


model_direct = DirectModel(vocab_size, args.d_model)
n_params_direct = count_params(model_direct)
print(f"  Trainable params: {n_params_direct:,}")
train_l_direct, val_l_direct = train_model(
    model_direct, 'direct', args.epochs, args.batch_size, args.seq_len, args.lr)
ppl_direct = np.exp(val_l_direct[-1])
print(f"  Final perplexity: {ppl_direct:.2f}")
print()

# ─── Results ──────────────────────────────────────────────────────
print("=" * 70)
print("  L3 RESULTS: TRAIN-THROUGH-H")
print("=" * 70)
print()
print(f"  {'Model':<25} {'Params':>8} {'Val Loss':>10} {'Perplexity':>12} {'vs Trainable':>14}")
print(f"  {'-'*25} {'-'*8} {'-'*10} {'-'*12} {'-'*14}")

ratio_phys = ppl_phys / ppl_train
ratio_rand = ppl_rand / ppl_train
ratio_direct = ppl_direct / ppl_train

print(f"  {'Physical H (fixed)':<25} {n_params_phys:>8,} {val_l_phys[-1]:>10.4f} {ppl_phys:>12.2f} {ratio_phys:>13.2f}×")
print(f"  {'Trainable H':<25} {n_params_train:>8,} {val_l_train[-1]:>10.4f} {ppl_train:>12.2f} {'1.00×':>14}")
print(f"  {'Random H (mean±std)':<25} {n_params_rand:>8,} {val_l_rand[-1]:>10.4f} {ppl_rand:>12.2f} {ratio_rand:>13.2f}×")
print(f"  {'No-H (direct)':<25} {n_params_direct:>8,} {val_l_direct[-1]:>10.4f} {ppl_direct:>12.2f} {ratio_direct:>13.2f}×")
print()

# Pass/fail
if ratio_phys <= 2.0:
    verdict = 'PASS'
    print(f"  ★ PASS — Physical H within 2× of trainable baseline ({ratio_phys:.2f}×)")
elif ratio_phys <= 3.0:
    verdict = 'PARTIAL'
    print(f"  △ PARTIAL — Physical H within 3× ({ratio_phys:.2f}×), target was 2×")
else:
    verdict = 'FAIL'
    print(f"  ✗ FAIL — Physical H is {ratio_phys:.2f}× worse than trainable (target: ≤2×)")

# Physical vs Random comparison
phys_beats_random = ppl_phys < ppl_rand - ppl_rand_std
if phys_beats_random:
    print(f"  ★ Physical H outperforms random H ({ppl_phys:.2f} vs {ppl_rand:.2f}±{ppl_rand_std:.2f})")
    print(f"    → H has USEFUL structure (not just noise)")
elif ppl_phys < ppl_rand:
    print(f"  △ Physical H slightly better than random mean ({ppl_phys:.2f} vs {ppl_rand:.2f}±{ppl_rand_std:.2f})")
    print(f"    → Suggestive but within noise")
else:
    print(f"  ○ Physical H ≈ random ({ppl_phys:.2f} vs {ppl_rand:.2f}±{ppl_rand_std:.2f})")
    print(f"    → H structure indistinguishable from random at this bottleneck")

# ─── Generate sample text ─────────────────────────────────────────
print(f"\n  [5] Sample generation (physical H model)...")
model_phys.eval()
context = torch.tensor([[char_to_idx[c] for c in "ROMEO:\n"]], dtype=torch.long)
generated = list(context[0].numpy())

with torch.no_grad():
    for _ in range(200):
        x = torch.tensor([generated[-args.seq_len:]], dtype=torch.long)
        logits = model_phys(x)
        probs = F.softmax(logits[0, -1] / 0.8, dim=-1)
        next_idx = torch.multinomial(probs, 1).item()
        generated.append(next_idx)

sample = ''.join([idx_to_char[i] for i in generated[len(context[0]):]])
print(f"  Generated: {repr(sample[:100])}")

# ─── Save results ─────────────────────────────────────────────────
DATA_DIR = Path('data/results/l3_train_through_h')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')

out = {
    'test': 'L3_train_through_H',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'h_matrix_path': str(h_path),
        'n_modes': n_modes, 'n_channels': n_channels,
        'd_model': args.d_model, 'seq_len': args.seq_len,
        'batch_size': args.batch_size, 'epochs': args.epochs,
        'lr': args.lr, 'vocab_size': vocab_size,
        'dataset': 'tinyshakespeare', 'n_chars': n_total,
    },
    'results': {
        'physical_H': {
            'val_loss': float(val_l_phys[-1]),
            'perplexity': float(ppl_phys),
            'params': n_params_phys,
            'train_losses': [float(x) for x in train_l_phys],
            'val_losses': [float(x) for x in val_l_phys],
        },
        'trainable_H': {
            'val_loss': float(val_l_train[-1]),
            'perplexity': float(ppl_train),
            'params': n_params_train,
            'train_losses': [float(x) for x in train_l_train],
            'val_losses': [float(x) for x in val_l_train],
        },
        'random_H': {
            'val_loss': float(val_l_rand[-1]),
            'perplexity_mean': float(ppl_rand),
            'perplexity_std': float(ppl_rand_std),
            'perplexities': [float(p) for p in ppl_rands],
            'params': n_params_rand,
            'train_losses': [float(x) for x in train_l_rand],
            'val_losses': [float(x) for x in val_l_rand],
        },
        'no_H_direct': {
            'val_loss': float(val_l_direct[-1]),
            'perplexity': float(ppl_direct),
            'params': n_params_direct,
            'train_losses': [float(x) for x in train_l_direct],
            'val_losses': [float(x) for x in val_l_direct],
        },
    },
    'comparison': {
        'phys_vs_trainable_ratio': float(ratio_phys),
        'rand_vs_trainable_ratio': float(ratio_rand),
        'direct_vs_trainable_ratio': float(ratio_direct),
        'phys_better_than_random': bool(phys_beats_random),
        'phys_vs_random_delta': float(ppl_rand - ppl_phys),
    },
    'verdict': verdict,
    'sample_text': sample[:200],
}

out_path = DATA_DIR / f'l3_train_through_h_{ts}.json'
with open(out_path, 'w') as f:
    json.dump(out, f, indent=2)
print(f"\n  Saved: {out_path}")
print("\n  Done.")
