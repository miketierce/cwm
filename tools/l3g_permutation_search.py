"""
L3g: Permutation Search — Find Mode Assignments That Match Task Routing
========================================================================

L3f proved enrollment-locking prevents absorption but imposed the WRONG
attention pattern (self-attention dominated, reversal needs anti-diagonal).

Key insight: the problem was mode ASSIGNMENT, not the architecture.
We selected modes for maximum angular diversity, but reversal needs
specific anti-correlated pairs (pos[0]↔pos[7], pos[1]↔pos[6]...).

L3g approach:
  1. Enumerate candidate mode→position assignments (combinatorial)
  2. For each, compute the resulting attention matrix from physics
  3. Score each against the IDEAL attention for the task
  4. Train only the top-K candidates and the worst-K (negative control)
  5. Compare: does alignment with task-optimal attention predict success?

This is NOT differentiable optimization — it's a discrete search over
the physics. The plate either HAS a useful assignment or it doesn't.
If it does, this proves the physical geometry is computationally relevant.

The comparison is:
  - Best physical assignment vs random assignment (same model capacity)
  - Best physical assignment vs best random-pattern assignment
  - Any physical assignment that beats random → physics helps

Usage:
  python3 tools/l3g_permutation_search.py
  python3 tools/l3g_permutation_search.py --n-candidates 5000 --top-k 5
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
parser = argparse.ArgumentParser(description='L3g: Permutation Search')
parser.add_argument('--h-matrix', type=str,
                    default='data/results/h_matrix/multi_plate_enrollment_20260603_171950.json')
parser.add_argument('--n-candidates', type=int, default=5000,
                    help='Number of random permutations to evaluate')
parser.add_argument('--top-k', type=int, default=5,
                    help='Train the top-K and bottom-K assignments')
parser.add_argument('--epochs', type=int, default=100)
parser.add_argument('--batch-size', type=int, default=128)
parser.add_argument('--n-train', type=int, default=20000)
parser.add_argument('--n-val', type=int, default=2000)
parser.add_argument('--d-value', type=int, default=64)
parser.add_argument('--lr', type=float, default=1e-3)
parser.add_argument('--n-random', type=int, default=10,
                    help='Number of random pattern baselines')
parser.add_argument('--seed', type=int, default=42)
args = parser.parse_args()

torch.manual_seed(args.seed)
np.random.seed(args.seed)

# ─── Load Enrollment Data ─────────────────────────────────────────
print("=" * 70)
print("  L3g: Permutation Search (Find Physics-Optimal Mode Assignment)")
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
    raise KeyError("No H matrix found")

freqs = h_data.get('mode_frequencies_hz', list(range(H_norm.shape[0])))
n_modes, n_channels = H_norm.shape

print(f"  Enrollment: {n_modes} modes × {n_channels} channels")
print(f"  Frequencies: {freqs[0]/1000:.0f}–{freqs[-1]/1000:.0f} kHz")
print()

# ─── Build signed features ────────────────────────────────────────
def build_signed_features(H):
    """Convert positive amplitudes to signed contrast features (8D)."""
    centered = H - H.mean(axis=1, keepdims=True)
    contrasts = np.column_stack([
        H[:, 0] - H[:, 1],
        H[:, 2] - H[:, 3],
        H[:, 0] - H[:, 2],
        H[:, 1] - H[:, 3],
    ])
    features = np.concatenate([centered, contrasts], axis=1)
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    return features / (norms + 1e-10)

H_signed = build_signed_features(H_norm)
n_feat = H_signed.shape[1]  # 8

# ─── Task definition ──────────────────────────────────────────────
SEQ_LEN = 8
VOCAB = 10

# For reversal: ideal attention matrix is anti-diagonal
# pos[i] should attend to pos[SEQ_LEN-1-i] with weight 1.0
IDEAL_ATTN = np.zeros((SEQ_LEN, SEQ_LEN))
for i in range(SEQ_LEN):
    IDEAL_ATTN[i, SEQ_LEN - 1 - i] = 1.0

print(f"  Task: reversal (8 digits)")
print(f"  Ideal attention: anti-diagonal (pos[i] → pos[7-i])")
print(f"  Feature dimension: {n_feat}D signed contrast features")
print()


# ─── Score function: how well does an assignment match the ideal? ──
def compute_attention_alignment(pos_indices, tok_indices, temperature=1.0):
    """
    Given mode assignments, compute the attention matrix and its
    alignment with the ideal reversal attention.

    Returns: (alignment_score, attention_matrix)
      alignment = mean attention weight on anti-diagonal positions
                  minus mean attention weight on diagonal (self-attention)
    """
    pos_patterns = H_signed[pos_indices]  # (8, n_feat)
    tok_patterns = H_signed[tok_indices]  # (10, n_feat)

    # For scoring, use a "representative" input: digits 0-7 at positions 0-7
    # Combined embedding = concat(tok_sig, pos_sig)
    # tok[digit] at pos[p] → concat(H_signed[tok_indices[digit]], H_signed[pos_indices[p]])
    combined = np.zeros((SEQ_LEN, 2 * n_feat))
    for p in range(SEQ_LEN):
        combined[p] = np.concatenate([tok_patterns[p], pos_patterns[p]])

    # Attention logits = combined @ combined.T / sqrt(d)
    d = combined.shape[1]
    logits = combined @ combined.T / (np.sqrt(d) * temperature)

    # Softmax
    logits -= logits.max(axis=1, keepdims=True)
    exp_l = np.exp(logits)
    attn = exp_l / exp_l.sum(axis=1, keepdims=True)

    # Alignment metrics
    anti_diag = np.mean([attn[i, SEQ_LEN-1-i] for i in range(SEQ_LEN)])
    diagonal = np.mean([attn[i, i] for i in range(SEQ_LEN)])

    # Score: anti-diagonal strength relative to uniform (1/8 = 0.125)
    # Higher is better for reversal
    alignment = anti_diag - diagonal

    return alignment, attn


# ─── Combinatorial search ─────────────────────────────────────────
print(f"  [1] Searching {args.n_candidates:,} random mode assignments...")
print(f"  (Need 8 position modes + 10 token modes from {n_modes} available)")
print()

candidates = []
all_indices = list(range(n_modes))

for i in range(args.n_candidates):
    # Random permutation: pick 18 modes, assign first 8 to positions, next 10 to tokens
    perm = np.random.permutation(n_modes)[:18]
    pos_idx = perm[:8].tolist()
    tok_idx = perm[8:18].tolist()

    # Try multiple temperatures to find best alignment
    best_align = -float('inf')
    best_temp = 1.0
    for temp in [0.1, 0.3, 0.5, 1.0, 2.0, 5.0]:
        align, _ = compute_attention_alignment(pos_idx, tok_idx, temp)
        if align > best_align:
            best_align = align
            best_temp = temp

    candidates.append({
        'pos_indices': pos_idx,
        'tok_indices': tok_idx,
        'alignment': best_align,
        'temperature': best_temp,
    })

# Sort by alignment score
candidates.sort(key=lambda c: c['alignment'], reverse=True)

print(f"  Alignment scores:")
print(f"    Best:   {candidates[0]['alignment']:.4f} (temp={candidates[0]['temperature']:.1f})")
print(f"    Median: {candidates[len(candidates)//2]['alignment']:.4f}")
print(f"    Worst:  {candidates[-1]['alignment']:.4f}")
print(f"    Mean:   {np.mean([c['alignment'] for c in candidates]):.4f}")
print(f"    Std:    {np.std([c['alignment'] for c in candidates]):.4f}")
print()

# Show top-K attention matrices
print(f"  Top-{args.top_k} assignments:")
for rank, c in enumerate(candidates[:args.top_k]):
    _, attn = compute_attention_alignment(c['pos_indices'], c['tok_indices'], c['temperature'])
    anti_d = np.mean([attn[i, 7-i] for i in range(8)])
    diag = np.mean([attn[i, i] for i in range(8)])
    print(f"    #{rank+1}: align={c['alignment']:.4f}, anti-diag={anti_d:.3f}, "
          f"self={diag:.3f}, temp={c['temperature']:.1f}")
    print(f"         pos modes: {[freqs[j]//1000 for j in c['pos_indices']]} kHz")

print(f"\n  Worst-{args.top_k} assignments:")
for rank, c in enumerate(candidates[-args.top_k:]):
    _, attn = compute_attention_alignment(c['pos_indices'], c['tok_indices'], c['temperature'])
    anti_d = np.mean([attn[i, 7-i] for i in range(8)])
    diag = np.mean([attn[i, i] for i in range(8)])
    print(f"    #{len(candidates)-args.top_k+rank+1}: align={c['alignment']:.4f}, "
          f"anti-diag={anti_d:.3f}, self={diag:.3f}")
print()


# ─── Model ────────────────────────────────────────────────────────

class EnrollmentLockedAttention(nn.Module):
    """Fixed-embedding attention with configurable temperature."""

    def __init__(self, vocab_size, seq_len, tok_patterns, pos_patterns, d_value, init_temp=0.0):
        super().__init__()
        self.register_buffer('tok_emb', torch.tensor(tok_patterns, dtype=torch.float32))
        self.register_buffer('pos_emb', torch.tensor(pos_patterns, dtype=torch.float32))
        d_emb = tok_patterns.shape[1] + pos_patterns.shape[1]

        self.value_proj = nn.Linear(d_emb, d_value)
        self.log_temperature = nn.Parameter(torch.tensor(init_temp))
        self.layer_norm = nn.LayerNorm(d_value)
        self.output_head = nn.Sequential(
            nn.Linear(d_value, d_value * 4),
            nn.GELU(),
            nn.Linear(d_value * 4, vocab_size),
        )
        self.d_emb = d_emb

    def forward(self, x):
        batch, seq_len = x.shape
        tok_e = self.tok_emb[x]
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


# ─── Data ─────────────────────────────────────────────────────────
print(f"  [2] Generating data...")
train_x = torch.randint(0, VOCAB, (args.n_train, SEQ_LEN))
train_y = train_x.flip(dims=[1])
val_x = torch.randint(0, VOCAB, (args.n_val, SEQ_LEN))
val_y = val_x.flip(dims=[1])
print(f"  Train: {args.n_train}, Val: {args.n_val}")
print()


# ─── Training function ────────────────────────────────────────────
def train_model(model, epochs, verbose=False, label=''):
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    best_acc = 0.0

    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(args.n_train)
        epoch_loss = 0
        n_batches = 0

        for i in range(0, args.n_train, args.batch_size):
            idx = perm[i:i+args.batch_size]
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

        model.eval()
        with torch.no_grad():
            logits = model(val_x)
            preds = logits.argmax(dim=-1)
            seq_acc = (preds == val_y).all(dim=1).float().mean().item()
            tok_acc = (preds == val_y).float().mean().item()
            best_acc = max(best_acc, seq_acc)

        if verbose and ((epoch+1) % 20 == 0 or epoch == 0 or seq_acc > 0.99):
            print(f"    {label} Ep {epoch+1:>3}: loss={epoch_loss/n_batches:.4f}, "
                  f"seq={seq_acc*100:.1f}%, tok={tok_acc*100:.1f}%")
            if seq_acc > 0.99:
                break

    return best_acc


# ─── Train top-K and bottom-K physical assignments ────────────────
print(f"  [3] Training top-{args.top_k} physical assignments...")
print("  " + "-" * 55)

top_accs = []
for rank, c in enumerate(candidates[:args.top_k]):
    pos_pat = H_signed[c['pos_indices']]
    tok_pat = H_signed[c['tok_indices']]
    # Initialize temperature near the alignment-optimal value
    init_temp = np.log(max(c['temperature'] - 0.1, 0.01))

    torch.manual_seed(args.seed)
    model = EnrollmentLockedAttention(VOCAB, SEQ_LEN, tok_pat, pos_pat, args.d_value, init_temp)
    acc = train_model(model, args.epochs, verbose=True, label=f'Top#{rank+1}')
    top_accs.append(acc)
    print(f"    Top#{rank+1} best seq accuracy: {acc*100:.1f}%")
    print()

print(f"  [4] Training bottom-{args.top_k} physical assignments...")
print("  " + "-" * 55)

bot_accs = []
for rank, c in enumerate(candidates[-args.top_k:]):
    pos_pat = H_signed[c['pos_indices']]
    tok_pat = H_signed[c['tok_indices']]
    init_temp = np.log(max(c['temperature'] - 0.1, 0.01))

    torch.manual_seed(args.seed)
    model = EnrollmentLockedAttention(VOCAB, SEQ_LEN, tok_pat, pos_pat, args.d_value, init_temp)
    acc = train_model(model, args.epochs, verbose=False, label=f'Bot#{rank+1}')
    bot_accs.append(acc)

print(f"  Bottom-{args.top_k} accuracies: {[f'{a*100:.1f}%' for a in bot_accs]}")
print()

# ─── Random pattern baselines ─────────────────────────────────────
print(f"  [5] Random pattern baselines ({args.n_random} random vectors)...")
print("  " + "-" * 55)

rand_accs = []
for ri in range(args.n_random):
    rand_tok = np.random.randn(10, n_feat).astype(np.float32)
    rand_tok = rand_tok / (np.linalg.norm(rand_tok, axis=1, keepdims=True) + 1e-10)
    rand_pos = np.random.randn(8, n_feat).astype(np.float32)
    rand_pos = rand_pos / (np.linalg.norm(rand_pos, axis=1, keepdims=True) + 1e-10)

    torch.manual_seed(args.seed)
    model = EnrollmentLockedAttention(VOCAB, SEQ_LEN, rand_tok, rand_pos, args.d_value)
    acc = train_model(model, args.epochs, verbose=False)
    rand_accs.append(acc)

    if (ri+1) % 5 == 0:
        print(f"    {ri+1}/{args.n_random}: acc={acc*100:.1f}% "
              f"(running mean={np.mean(rand_accs)*100:.1f}%)")

rand_mean = np.mean(rand_accs)
rand_std = np.std(rand_accs)
print(f"  Random: {rand_mean*100:.1f}% ± {rand_std*100:.1f}%")
print()

# ─── Learnable baseline ──────────────────────────────────────────
print(f"  [6] Learnable baseline (upper bound)...")
print("  " + "-" * 55)


class LearnableModel(nn.Module):
    def __init__(self, vocab_size, seq_len, n_feat, d_value):
        super().__init__()
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


torch.manual_seed(args.seed)
model_learn = LearnableModel(VOCAB, SEQ_LEN, n_feat, args.d_value)
acc_learn = train_model(model_learn, args.epochs, verbose=True, label='Learn')
print(f"  Learnable: {acc_learn*100:.1f}%")
print()

# ─── Correlation analysis ─────────────────────────────────────────
print(f"  [7] Correlation: alignment score vs training accuracy...")

# Sample ~20 assignments across the alignment range for correlation
n_sample = 20
sample_indices = np.linspace(0, len(candidates)-1, n_sample, dtype=int)
sample_accs = []
sample_aligns = []

for si in sample_indices:
    c = candidates[si]
    pos_pat = H_signed[c['pos_indices']]
    tok_pat = H_signed[c['tok_indices']]
    init_temp = np.log(max(c['temperature'] - 0.1, 0.01))

    torch.manual_seed(args.seed)
    model = EnrollmentLockedAttention(VOCAB, SEQ_LEN, tok_pat, pos_pat, args.d_value, init_temp)
    acc = train_model(model, args.epochs, verbose=False)
    sample_accs.append(acc)
    sample_aligns.append(c['alignment'])

# Pearson correlation
corr = np.corrcoef(sample_aligns, sample_accs)[0, 1]
print(f"  Sampled {n_sample} assignments across alignment range")
print(f"  Alignment range: [{min(sample_aligns):.4f}, {max(sample_aligns):.4f}]")
print(f"  Accuracy range:  [{min(sample_accs)*100:.1f}%, {max(sample_accs)*100:.1f}%]")
print(f"  Pearson r (alignment vs accuracy): {corr:.3f}")
print()

# ─── Final Results ────────────────────────────────────────────────
best_phys = max(top_accs)
worst_phys = min(bot_accs)
sigma_top_vs_rand = (np.mean(top_accs) - rand_mean) / (rand_std + 1e-10)
sigma_best_vs_rand = (best_phys - rand_mean) / (rand_std + 1e-10)

print("=" * 70)
print("  L3g RESULTS: PERMUTATION SEARCH")
print("=" * 70)
print()
print(f"  Candidates searched: {args.n_candidates:,}")
print(f"  Alignment metric: anti_diag_weight - self_attention_weight")
print()
print(f"  {'Model':<35} {'Accuracy':>10} {'vs Random':>10}")
print(f"  {'-'*35} {'-'*10} {'-'*10}")
print(f"  {'Best physical (top-1)':<35} {best_phys*100:>9.1f}% {f'{sigma_best_vs_rand:+.1f}σ':>10}")
print(f"  {'Top-K physical (mean)':<35} {np.mean(top_accs)*100:>9.1f}% {f'{sigma_top_vs_rand:+.1f}σ':>10}")
print(f"  {'Bottom-K physical (mean)':<35} {np.mean(bot_accs)*100:>9.1f}% {'':>10}")
print(f"  {'Random patterns (mean±std)':<35} {rand_mean*100:>9.1f}% {'—':>10}")
print(f"  {'Learnable (ceiling)':<35} {acc_learn*100:>9.1f}% {'':>10}")
print()
print(f"  Correlation (alignment→accuracy): r = {corr:.3f}")
print(f"    {'→ Mode assignment MATTERS' if abs(corr) > 0.3 else '→ Mode assignment does NOT predict accuracy'}")
print()

# Verdict
if sigma_best_vs_rand > 2.0:
    verdict = 'PASS'
    print(f"  ★★ PASS — Best physical assignment outperforms random at {sigma_best_vs_rand:.1f}σ!")
    print(f"  The plate HAS mode assignments that provide useful attention routing.")
    print(f"  Discrete search over physics (not gradient descent) breaks absorption.")
elif sigma_best_vs_rand > 1.0:
    verdict = 'MARGINAL'
    print(f"  △ MARGINAL — Best physical > random at {sigma_best_vs_rand:.1f}σ")
elif best_phys > rand_mean:
    verdict = 'WEAK'
    print(f"  ○ WEAK — Best physical slightly better ({sigma_best_vs_rand:.1f}σ)")
else:
    verdict = 'FAIL'
    print(f"  ✗ FAIL — No physical assignment beats random ({sigma_best_vs_rand:.1f}σ)")

if abs(corr) > 0.3:
    print(f"\n  Key finding: alignment score PREDICTS accuracy (r={corr:.3f})")
    print(f"  → The plate's spatial geometry creates a GRADIENT of computational utility")
    print(f"  → Some mode configurations are genuinely better than others for this task")

# ─── Save ─────────────────────────────────────────────────────────
DATA_DIR = Path('data/results/l3_train_through_h')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')

out = {
    'test': 'L3g_permutation_search',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'h_matrix_path': str(h_path),
        'n_candidates': args.n_candidates,
        'top_k': args.top_k,
        'epochs': args.epochs,
        'd_value': args.d_value,
        'n_train': args.n_train,
        'n_val': args.n_val,
        'n_random': args.n_random,
        'n_feat': n_feat,
    },
    'search': {
        'best_alignment': candidates[0]['alignment'],
        'median_alignment': candidates[len(candidates)//2]['alignment'],
        'worst_alignment': candidates[-1]['alignment'],
        'best_pos_modes': [freqs[i] for i in candidates[0]['pos_indices']],
        'best_tok_modes': [freqs[i] for i in candidates[0]['tok_indices']],
        'best_temperature': candidates[0]['temperature'],
    },
    'results': {
        'top_k_accuracies': top_accs,
        'bottom_k_accuracies': bot_accs,
        'random_accuracies': rand_accs,
        'learnable_accuracy': acc_learn,
        'correlation_r': float(corr),
        'sample_alignments': sample_aligns,
        'sample_accuracies': sample_accs,
    },
    'statistics': {
        'best_phys_vs_random_sigma': float(sigma_best_vs_rand),
        'topk_mean_vs_random_sigma': float(sigma_top_vs_rand),
    },
    'verdict': verdict,
}

out_path = DATA_DIR / f'l3g_permutation_search_{ts}.json'
with open(out_path, 'w') as f:
    json.dump(out, f, indent=2)
print(f"\n  Saved: {out_path}")
print("\n  Done.")
