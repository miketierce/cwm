"""
L3c: Polysemic Train-Through-H — K=8 Sub-band Readout
======================================================

Reworks L3 using polysemic readout: instead of a single 26→2 projection,
partition the 26 modes into K=8 subsets. Each subset projects through its
own slice of H, giving K×2 = 16 output dimensions.

The key insight from L3b:
  - Single 26→2: rank-2, indistinguishable from random (learnable rotation)
  - K=8 polysemic: 15.4 effective dims, 96% independence between subsets
  - Physical H has 3.9σ advantage over random (B/A ratio diversity)

Architecture:
  Token → Embed(vocab, d_model) → Linear(d_model, 26) → [K=8 sub-H projections]
       → Concat(K×2 = 16 dims) → Linear(16, d_model) → LN → MLP → LN → Head

Each sub-H is a (3-4)×2 slice of the MEASURED plate H. The physical plate's
spatial diversity (B/A 1.3–11.2×) means each subset provides a genuinely
different projection — this is NOT available from random matrices.

Comparison:
  1. Physical H polysemic (K=8): measured plate, 8 independent sub-readouts
  2. Trainable polysemic: same structure, sub-H matrices learnable
  3. Random H polysemic (×5): random matrices, same block structure
  4. Shuffled H polysemic: physical H rows randomly permuted across subsets
  5. Single-H baseline: original L3 architecture (26→2)

If physical polysemic beats random polysemic AND shuffled, the plate's
mode-frequency-to-spatial-coupling structure is computationally useful.

Usage:
  python3 tools/l3c_polysemic_train.py
  python3 tools/l3c_polysemic_train.py --K 4 --epochs 30
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
parser = argparse.ArgumentParser(description='L3c: Polysemic Train-Through-H')
parser.add_argument('--h-matrix', type=str,
                    default='data/results/h_matrix/l1_h_matrix_20260602_220004.json')
parser.add_argument('--K', type=int, default=8, help='Number of polysemic subsets')
parser.add_argument('--partition', type=str, default='max_diversity',
                    choices=['max_diversity', 'interleave', 'contiguous'],
                    help='Mode partition strategy')
parser.add_argument('--epochs', type=int, default=30)
parser.add_argument('--batch-size', type=int, default=64)
parser.add_argument('--seq-len', type=int, default=64)
parser.add_argument('--d-model', type=int, default=128)
parser.add_argument('--lr', type=float, default=1e-3)
parser.add_argument('--seed', type=int, default=42)
args = parser.parse_args()

torch.manual_seed(args.seed)
np.random.seed(args.seed)

# ─── Load H Matrix ───────────────────────────────────────────────
print("=" * 70)
print("  L3c: Polysemic Train-Through-H (K=%d Sub-band Readout)" % args.K)
print("=" * 70)
print()

h_path = Path(args.h_matrix)
with open(h_path) as f:
    h_data = json.load(f)

H_raw = np.array(h_data['H_raw'])  # (26, 2)
n_modes, n_ch = H_raw.shape
ratios = np.array([m['ratio_b_over_a'] for m in h_data['modes']])
freqs = np.array([m['freq_hz'] for m in h_data['modes']])

print(f"  H matrix: {n_modes}×{n_ch}")
print(f"  B/A ratio range: {ratios.min():.2f} – {ratios.max():.2f}")
print(f"  Modes: {freqs[0]/1000:.0f} – {freqs[-1]/1000:.0f} kHz")

# ─── Partition modes into K subsets ───────────────────────────────
angles = np.arctan2(H_raw[:, 1], H_raw[:, 0])  # spatial angle per mode

if args.partition == 'max_diversity':
    # Sort by angle, split into K blocks (each block = similar angles)
    # This MAXIMIZES between-subset diversity
    sorted_idx = np.argsort(angles)
    partition = [list(sorted_idx[i::args.K]) for i in range(args.K)]
elif args.partition == 'interleave':
    partition = [list(range(i, n_modes, args.K)) for i in range(args.K)]
elif args.partition == 'contiguous':
    size = n_modes // args.K
    partition = [list(range(i * size, min((i + 1) * size, n_modes)))
                 for i in range(args.K)]

# Remove empty subsets
partition = [p for p in partition if len(p) > 0]
K_actual = len(partition)
output_dim = K_actual * n_ch  # K×2

print(f"\n  Partition strategy: {args.partition}")
print(f"  K={K_actual} subsets, output dim = {K_actual}×{n_ch} = {output_dim}")
print(f"  Subset sizes: {[len(p) for p in partition]}")
print(f"  Subset angle ranges:")
for i, p in enumerate(partition):
    a = angles[p]
    r = ratios[p]
    print(f"    Subset {i}: modes {len(p)}, angle {np.degrees(a.min()):.1f}–{np.degrees(a.max()):.1f}°, "
          f"B/A {r.min():.1f}–{r.max():.1f}")
print()

# Build sub-H tensors (list of (subset_size, 2) matrices)
# Normalize each sub-H to preserve relative energy across subsets
H_subs = []
for p in partition:
    H_sub = H_raw[p, :]
    # Normalize: unit Frobenius norm per subset
    H_sub = H_sub / (np.linalg.norm(H_sub, 'fro') + 1e-10)
    H_subs.append(torch.tensor(H_sub, dtype=torch.float32))

# ─── Dataset ──────────────────────────────────────────────────────
DATA_DIR = Path('data')
SHAKESPEARE_PATH = DATA_DIR / 'tinyshakespeare.txt'
if not SHAKESPEARE_PATH.exists():
    print("  Downloading tiny Shakespeare...")
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
print(f"  Train: {n_train:,}, Val: {n_total - n_train:,}")
print()


def get_batch(split, batch_size, seq_len):
    d = train_data if split == 'train' else val_data
    ix = torch.randint(len(d) - seq_len - 1, (batch_size,))
    x = torch.stack([d[i:i + seq_len] for i in ix])
    y = torch.stack([d[i + 1:i + seq_len + 1] for i in ix])
    return x, y


# ─── Model ────────────────────────────────────────────────────────

class PolysemicPlateModel(nn.Module):
    """Language model with K-subset polysemic readout through plate H.

    Each subset of modes provides an independent 2D projection.
    Concatenated output = K×2 dims — much richer than single 26→2.

    The plate's spatial diversity ensures subsets carry different info.
    """

    def __init__(self, vocab_size, d_model, H_subs, partition, trainable_H=False):
        super().__init__()
        self.partition = partition
        self.K = len(partition)
        n_modes_total = sum(len(p) for p in partition)
        n_ch = H_subs[0].shape[1]
        self.output_dim = self.K * n_ch  # K×2

        self.embedding = nn.Embedding(vocab_size, d_model)
        self.project_to_modes = nn.Linear(d_model, n_modes_total)

        # Register each sub-H as a buffer or parameter
        self.H_subs = nn.ParameterList([
            nn.Parameter(h.clone(), requires_grad=trainable_H)
            for h in H_subs
        ])

        # Expand from concatenated polysemic output to model space
        self.expand = nn.Linear(self.output_dim, d_model)
        self.norm = nn.LayerNorm(d_model)

        # MLP
        self.mlp = nn.Sequential(
            nn.Linear(d_model, d_model * 2),
            nn.GELU(),
            nn.Linear(d_model * 2, d_model),
        )
        self.norm2 = nn.LayerNorm(d_model)

        # Output head
        self.head = nn.Linear(d_model, vocab_size)

    def forward(self, x):
        emb = self.embedding(x)  # (batch, seq, d_model)
        modes = self.project_to_modes(emb)  # (batch, seq, 26)

        # Polysemic readout: each subset projects through its own H slice
        sub_outputs = []
        for i, (p, H_sub) in enumerate(zip(self.partition, self.H_subs)):
            # Extract this subset's mode activations
            mode_subset = modes[:, :, p]  # (batch, seq, |subset_i|)
            # Project through sub-H: (batch, seq, |subset_i|) @ (|subset_i|, 2)
            out_i = mode_subset @ H_sub  # (batch, seq, 2)
            sub_outputs.append(out_i)

        # Concatenate all subset outputs → (batch, seq, K×2)
        poly_out = torch.cat(sub_outputs, dim=-1)  # (batch, seq, 16)

        # Expand back to d_model
        expanded = self.norm(self.expand(poly_out))

        # MLP
        out = self.norm2(expanded + self.mlp(expanded))

        # Predict
        logits = self.head(out)
        return logits


class SingleHModel(nn.Module):
    """Original L3 baseline: single 26→2 projection."""

    def __init__(self, vocab_size, d_model, H_full, trainable_H=False):
        super().__init__()
        n_modes, n_ch = H_full.shape

        self.embedding = nn.Embedding(vocab_size, d_model)
        self.project_to_modes = nn.Linear(d_model, n_modes)
        self.H = nn.Parameter(H_full.clone(), requires_grad=trainable_H)
        self.expand = nn.Linear(n_ch, d_model)
        self.norm = nn.LayerNorm(d_model)
        self.mlp = nn.Sequential(
            nn.Linear(d_model, d_model * 2),
            nn.GELU(),
            nn.Linear(d_model * 2, d_model),
        )
        self.norm2 = nn.LayerNorm(d_model)
        self.head = nn.Linear(d_model, vocab_size)

    def forward(self, x):
        emb = self.embedding(x)
        modes = self.project_to_modes(emb)
        plate_out = modes @ self.H  # (batch, seq, 2)
        expanded = self.norm(self.expand(plate_out))
        out = self.norm2(expanded + self.mlp(expanded))
        return self.head(out)


# ─── Training ─────────────────────────────────────────────────────

def train_model(model, name, epochs, batch_size, seq_len, lr, verbose=True):
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
        train_losses.append(epoch_loss / n_batches)

        model.eval()
        with torch.no_grad():
            val_sum = 0
            for _ in range(20):
                x, y = get_batch('val', batch_size, seq_len)
                logits = model(x)
                val_sum += F.cross_entropy(logits.view(-1, vocab_size), y.view(-1)).item()
            val_losses.append(val_sum / 20)

        if verbose and ((epoch + 1) % 5 == 0 or epoch == 0):
            ppl = np.exp(val_losses[-1])
            print(f"    Epoch {epoch+1:>3}/{epochs}: "
                  f"train={train_losses[-1]:.4f}, val={val_losses[-1]:.4f}, ppl={ppl:.2f}")

    return train_losses, val_losses


def count_params(model, trainable_only=True):
    if trainable_only:
        return sum(p.numel() for p in model.parameters() if p.requires_grad)
    return sum(p.numel() for p in model.parameters())


# ─── Run experiments ──────────────────────────────────────────────

results = {}

# Normalize full H for single-H baseline (same as original L3)
H_full_norm = H_raw / np.linalg.norm(H_raw, axis=1, keepdims=True)
H_full_norm = H_full_norm * np.sqrt(n_modes) / np.linalg.norm(H_full_norm, 'fro')
H_full_tensor = torch.tensor(H_full_norm, dtype=torch.float32)

# ── 1. Physical H polysemic (K=8) ────────────────────────────────
print("  [1] PHYSICAL H POLYSEMIC (K=%d, H fixed)" % K_actual)
print("  " + "-" * 50)
model_poly = PolysemicPlateModel(vocab_size, args.d_model, H_subs, partition, trainable_H=False)
n_params = count_params(model_poly)
print(f"  Trainable params: {n_params:,}")
print(f"  Output dim through plate: {output_dim} (vs 2 in original L3)")
train_l_poly, val_l_poly = train_model(
    model_poly, 'physical_poly', args.epochs, args.batch_size, args.seq_len, args.lr)
ppl_poly = np.exp(val_l_poly[-1])
print(f"  Final perplexity: {ppl_poly:.2f}")
print()

# ── 2. Trainable polysemic (K=8, sub-H learnable) ────────────────
print("  [2] TRAINABLE POLYSEMIC (K=%d, sub-H learnable)" % K_actual)
print("  " + "-" * 50)
model_poly_train = PolysemicPlateModel(vocab_size, args.d_model, H_subs, partition, trainable_H=True)
n_params_t = count_params(model_poly_train)
print(f"  Trainable params: {n_params_t:,} (+{n_params_t - n_params} from H)")
train_l_poly_t, val_l_poly_t = train_model(
    model_poly_train, 'trainable_poly', args.epochs, args.batch_size, args.seq_len, args.lr)
ppl_poly_train = np.exp(val_l_poly_t[-1])
print(f"  Final perplexity: {ppl_poly_train:.2f}")
print()

# ── 3. Random H polysemic (×5) ───────────────────────────────────
print("  [3] RANDOM H POLYSEMIC (×5, same block structure)")
print("  " + "-" * 50)
ppl_rands = []
for ri in range(5):
    rng = np.random.default_rng(ri + 100)
    H_rand_subs = []
    for p in partition:
        Hr = rng.standard_normal((len(p), n_ch)).astype(np.float32)
        Hr = Hr / (np.linalg.norm(Hr, 'fro') + 1e-10)
        H_rand_subs.append(torch.tensor(Hr))

    model_rand = PolysemicPlateModel(vocab_size, args.d_model, H_rand_subs, partition, trainable_H=False)
    _, val_l_r = train_model(
        model_rand, f'random_{ri}', args.epochs, args.batch_size, args.seq_len, args.lr, verbose=False)
    ppl_r = np.exp(val_l_r[-1])
    ppl_rands.append(ppl_r)
    print(f"    Random {ri+1}/5: ppl={ppl_r:.2f}")

ppl_rand_mean = np.mean(ppl_rands)
ppl_rand_std = np.std(ppl_rands)
print(f"  Mean: {ppl_rand_mean:.2f} ± {ppl_rand_std:.2f}")
print()

# ── 4. Shuffled H polysemic (physical rows, wrong subsets) ───────
print("  [4] SHUFFLED H POLYSEMIC (physical H rows, random assignment)")
print("  " + "-" * 50)
ppl_shuffs = []
for si in range(5):
    rng = np.random.default_rng(si + 200)
    # Shuffle row indices across subsets (destroys spatial structure)
    all_idx = np.arange(n_modes)
    rng.shuffle(all_idx)
    shuf_partition = [list(all_idx[i::K_actual]) for i in range(K_actual)]

    H_shuf_subs = []
    for p in shuf_partition:
        H_sub = H_raw[p, :]
        H_sub = H_sub / (np.linalg.norm(H_sub, 'fro') + 1e-10)
        H_shuf_subs.append(torch.tensor(H_sub.astype(np.float32)))

    model_shuf = PolysemicPlateModel(vocab_size, args.d_model, H_shuf_subs, shuf_partition, trainable_H=False)
    _, val_l_s = train_model(
        model_shuf, f'shuffled_{si}', args.epochs, args.batch_size, args.seq_len, args.lr, verbose=False)
    ppl_s = np.exp(val_l_s[-1])
    ppl_shuffs.append(ppl_s)
    print(f"    Shuffled {si+1}/5: ppl={ppl_s:.2f}")

ppl_shuf_mean = np.mean(ppl_shuffs)
ppl_shuf_std = np.std(ppl_shuffs)
print(f"  Mean: {ppl_shuf_mean:.2f} ± {ppl_shuf_std:.2f}")
print()

# ── 5. Single-H baseline (original L3 architecture) ──────────────
print("  [5] SINGLE-H BASELINE (original L3: 26→2)")
print("  " + "-" * 50)
model_single = SingleHModel(vocab_size, args.d_model, H_full_tensor, trainable_H=False)
n_params_s = count_params(model_single)
print(f"  Trainable params: {n_params_s:,}")
train_l_single, val_l_single = train_model(
    model_single, 'single_H', args.epochs, args.batch_size, args.seq_len, args.lr)
ppl_single = np.exp(val_l_single[-1])
print(f"  Final perplexity: {ppl_single:.2f}")
print()

# ─── Results ──────────────────────────────────────────────────────
print("=" * 70)
print("  L3c RESULTS: POLYSEMIC TRAIN-THROUGH-H (K=%d)" % K_actual)
print("=" * 70)
print()
print(f"  {'Model':<35} {'Params':>8} {'Val Loss':>10} {'PPL':>8} {'vs Train':>10}")
print(f"  {'-'*35} {'-'*8} {'-'*10} {'-'*8} {'-'*10}")

r_poly = ppl_poly / ppl_poly_train
r_rand = ppl_rand_mean / ppl_poly_train
r_shuf = ppl_shuf_mean / ppl_poly_train
r_single = ppl_single / ppl_poly_train

print(f"  {'Physical H poly (K=%d)' % K_actual:<35} {n_params:>8,} {val_l_poly[-1]:>10.4f} {ppl_poly:>8.2f} {r_poly:>9.2f}×")
print(f"  {'Trainable poly (K=%d)' % K_actual:<35} {n_params_t:>8,} {val_l_poly_t[-1]:>10.4f} {ppl_poly_train:>8.2f} {'1.00×':>10}")
print(f"  {'Random H poly (mean±std)':<35} {n_params:>8,} {'—':>10} {ppl_rand_mean:>8.2f} {r_rand:>9.2f}×")
print(f"  {'Shuffled H poly (mean±std)':<35} {n_params:>8,} {'—':>10} {ppl_shuf_mean:>8.2f} {r_shuf:>9.2f}×")
print(f"  {'Single H (26→2, original L3)':<35} {n_params_s:>8,} {val_l_single[-1]:>10.4f} {ppl_single:>8.2f} {r_single:>9.2f}×")
print()

# ── Verdicts ──────────────────────────────────────────────────────
print("  ── Diagnostic Tests ──")
print()

# Test A: Does polysemic help vs single-H?
improvement = (ppl_single - ppl_poly) / ppl_single * 100
print(f"  A) Polysemic vs Single-H:")
print(f"     PPL: {ppl_poly:.2f} vs {ppl_single:.2f} ({improvement:+.1f}%)")
if ppl_poly < ppl_single:
    print(f"     → Polysemic readout HELPS ({output_dim} dims > 2 dims)")
else:
    print(f"     → No improvement from polysemic (unexpected)")
print()

# Test B: Physical H vs Random H (structure test)
phys_vs_rand = (ppl_rand_mean - ppl_poly) / ppl_rand_std if ppl_rand_std > 0 else 0
print(f"  B) Physical vs Random H (polysemic):")
print(f"     Physical: {ppl_poly:.2f}, Random: {ppl_rand_mean:.2f}±{ppl_rand_std:.2f}")
print(f"     Separation: {phys_vs_rand:.1f}σ")
if phys_vs_rand > 2:
    print(f"     ★ Physical H has USEFUL structure (>2σ from random)")
elif phys_vs_rand > 1:
    print(f"     △ Suggestive advantage (1-2σ)")
else:
    print(f"     ○ Indistinguishable from random")
print()

# Test C: Physical H vs Shuffled H (partition structure test)
phys_vs_shuf = (ppl_shuf_mean - ppl_poly) / ppl_shuf_std if ppl_shuf_std > 0 else 0
print(f"  C) Physical vs Shuffled H (partition structure):")
print(f"     Physical: {ppl_poly:.2f}, Shuffled: {ppl_shuf_mean:.2f}±{ppl_shuf_std:.2f}")
print(f"     Separation: {phys_vs_shuf:.1f}σ")
if phys_vs_shuf > 2:
    print(f"     ★ Partition by spatial angle IS beneficial")
elif phys_vs_shuf > 1:
    print(f"     △ Suggestive (correct partition slightly better)")
else:
    print(f"     ○ Partition order doesn't matter much")
print()

# Test D: Physical polysemic vs trainable (how much is left on table)
gap = (ppl_poly - ppl_poly_train) / ppl_poly_train * 100
print(f"  D) Physical vs Trainable (gap to optimal):")
print(f"     Physical: {ppl_poly:.2f}, Trainable: {ppl_poly_train:.2f} (gap: {gap:+.1f}%)")
if gap < 5:
    print(f"     ★ Near-optimal — physical H captures most structure")
elif gap < 20:
    print(f"     △ Some gap — physical H is good but not optimal")
else:
    print(f"     ○ Large gap — learnable H significantly outperforms")
print()

# Overall verdict
print("  ── OVERALL VERDICT ──")
if ppl_poly < ppl_single and phys_vs_rand > 1:
    verdict = 'PASS'
    print(f"  ★★ PASS — Polysemic readout makes physical H useful!")
    print(f"     K={K_actual} gives {output_dim} output dims (vs 2 in original L3)")
    print(f"     Physical H outperforms random at {phys_vs_rand:.1f}σ")
elif ppl_poly < ppl_single:
    verdict = 'PARTIAL'
    print(f"  ★ PARTIAL — Polysemic helps ({improvement:+.1f}%) but physical ≈ random")
else:
    verdict = 'FAIL'
    print(f"  ✗ FAIL — Polysemic readout did not improve over single-H")

# ─── Generate sample ──────────────────────────────────────────────
print(f"\n  [6] Sample generation (polysemic model)...")
model_poly.eval()
context = torch.tensor([[char_to_idx[c] for c in "ROMEO:\n"]], dtype=torch.long)
generated = list(context[0].numpy())

with torch.no_grad():
    for _ in range(200):
        x = torch.tensor([generated[-args.seq_len:]], dtype=torch.long)
        logits = model_poly(x)
        probs = F.softmax(logits[0, -1] / 0.8, dim=-1)
        next_idx = torch.multinomial(probs, 1).item()
        generated.append(next_idx)

sample = ''.join([idx_to_char[i] for i in generated[len(context[0]):]])
print(f"  Generated: {repr(sample[:120])}")

# ─── Save ─────────────────────────────────────────────────────────
DATA_DIR = Path('data/results/l3_train_through_h')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')

out = {
    'test': 'L3c_polysemic_train_through_H',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'h_matrix_path': str(h_path),
        'K': K_actual,
        'partition_strategy': args.partition,
        'output_dim': output_dim,
        'partition_sizes': [len(p) for p in partition],
        'd_model': args.d_model, 'seq_len': args.seq_len,
        'batch_size': args.batch_size, 'epochs': args.epochs,
        'lr': args.lr, 'vocab_size': vocab_size,
    },
    'results': {
        'physical_poly': {'ppl': float(ppl_poly), 'val_loss': float(val_l_poly[-1]), 'params': n_params},
        'trainable_poly': {'ppl': float(ppl_poly_train), 'val_loss': float(val_l_poly_t[-1]), 'params': n_params_t},
        'random_poly': {'ppl_mean': float(ppl_rand_mean), 'ppl_std': float(ppl_rand_std), 'ppls': [float(p) for p in ppl_rands]},
        'shuffled_poly': {'ppl_mean': float(ppl_shuf_mean), 'ppl_std': float(ppl_shuf_std), 'ppls': [float(p) for p in ppl_shuffs]},
        'single_H': {'ppl': float(ppl_single), 'val_loss': float(val_l_single[-1]), 'params': n_params_s},
    },
    'diagnostics': {
        'A_polysemic_vs_single': {'improvement_pct': float(improvement), 'helps': bool(ppl_poly < ppl_single)},
        'B_physical_vs_random': {'sigma': float(phys_vs_rand), 'useful_structure': bool(phys_vs_rand > 1)},
        'C_physical_vs_shuffled': {'sigma': float(phys_vs_shuf), 'partition_matters': bool(phys_vs_shuf > 1)},
        'D_gap_to_optimal': {'gap_pct': float(gap)},
    },
    'verdict': verdict,
}

out_path = DATA_DIR / f'l3c_polysemic_K{K_actual}_{ts}.json'
with open(out_path, 'w') as f:
    json.dump(out, f, indent=2)
print(f"\n  Saved: {out_path}")
