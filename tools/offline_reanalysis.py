#!/usr/bin/env python3
"""
Comprehensive offline reanalysis suite for saved CWM enrollment data.
Covers tasks from PR #2 (Offline Reanalysis Plan):
  - Partial-query grid: every axis-hiding combination
  - Structured mode dropout with per-band ablation
  - Small-readout stress test (feature subsets of decreasing size)
  - Software-kernel baselines (random, PCA, permuted)
  - Cross-validation abuse check (permutation test)

Usage: python3 tools/offline_reanalysis.py [npz]
"""
import numpy as np, json, sys, glob, itertools, time
from pathlib import Path

p = sys.argv[1] if len(sys.argv) > 1 else sorted(
    glob.glob('data/results/pong/recall_enroll_*.npz'))[-1]
d = np.load(p)
X = d['X']; L = d['L']; R = int(d['repeats']); PADH = int(d['padh'])
driven = d['driven']; NW = int(d['nw']); naxes = int(d['naxes'])
Fd = X.shape[1]; axis_block = naxes * NW
X = X / (X.mean(1, keepdims=True) + 1e-9)
rng = np.random.default_rng(42)

AXES = ['x', 'y', 'vx', 'vy']
print(f"Loaded {p}: X{X.shape}, Fd={Fd}, axis_block={axis_block}, "
      f"modes={Fd - axis_block}, repeats={R}")
results = {'source': str(p), 'Fd': Fd, 'n_modes': Fd - axis_block}
t0 = time.time()


def loro(Xf, lab, sig, k=3, mask=None):
    """Leave-one-repeat-out KNN recall."""
    hit = tot = 0
    rr = np.random.default_rng(1)
    for rt in range(R):
        te = [i for i in range(len(lab)) if i % R == rt]
        tr = [i for i in range(len(lab)) if i % R != rt]
        mu = Xf[tr].mean(0); sd = Xf[tr].std(0); sd[sd < 1e-9] = 1
        A = (Xf[tr] - mu) / sd; dl = lab[tr]
        for i in te:
            q = (Xf[i] - mu) / sd
            if mask is not None:
                q = q * mask
            q = q + rr.standard_normal(Xf.shape[1]) * sig
            nn = np.argsort(((A - q) ** 2).sum(1))[:k]
            pr = int(round(np.median(dl[nn])))
            hit += abs(pr - lab[i]) <= PADH // 2
            tot += 1
    return hit / tot * 100


# ============================================================
# 1. PARTIAL-QUERY GRID: hide every combination of axes
# ============================================================
print("\n" + "=" * 60)
print("1. PARTIAL-QUERY GRID (all axis-hiding combos, sigma=1.0)")
print("=" * 60)
sig_pq = 1.0
pq_results = {}

# All 2^4 - 1 non-empty subsets of axes to KEEP visible
for nhide in range(5):
    for hidden in itertools.combinations(range(naxes), nhide):
        visible = [i for i in range(naxes) if i not in hidden]
        hidden_names = [AXES[i] for i in hidden] if hidden else ['none']
        visible_names = [AXES[i] for i in visible] if visible else ['none']
        key = f"hide_{'_'.join(hidden_names)}"

        # Build mask: zero hidden axis windows, keep modes
        mask_glass = np.ones(Fd)
        for h in hidden:
            mask_glass[h * NW:(h + 1) * NW] = 0

        # Wire mask: 4 dims, one per axis
        mask_wire = np.ones(len(driven))
        for h in hidden:
            mask_wire[h] = 0

        acc_glass = loro(X, L, sig_pq, mask=mask_glass)
        acc_wire = loro(X[:, driven], L, sig_pq, mask=mask_wire)

        pq_results[key] = {
            'hidden': list(hidden_names),
            'visible': list(visible_names),
            'glass': round(acc_glass, 2),
            'wire': round(acc_wire, 2),
            'advantage': round(acc_glass - acc_wire, 2),
        }
        print(f"  {key:30s}  glass={acc_glass:5.1f}  wire={acc_wire:5.1f}  "
              f"adv={acc_glass - acc_wire:+5.1f}")

results['partial_query_grid'] = pq_results
print(f"  [{time.time() - t0:.0f}s elapsed]")

# ============================================================
# 2. STRUCTURED MODE DROPOUT / ABLATION (per-band)
# ============================================================
print("\n" + "=" * 60)
print("2. STRUCTURED MODE DROPOUT (sigma=1.0)")
print("=" * 60)
modes_idx = np.arange(axis_block, Fd)
n_modes = len(modes_idx)

# 2a. Random dropout at finer granularity
drop_fracs = [0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
dropout_random = {}
for fr in drop_fracs:
    Xd = X.copy()
    if fr > 0:
        z = rng.choice(modes_idx, int(fr * n_modes), replace=False)
        Xd[:, z] = 0
    acc = loro(Xd, L, 1.0)
    dropout_random[f'{int(fr*100)}pct'] = round(acc, 2)
    print(f"  random drop {int(fr*100):3d}%: {acc:5.1f}")

# 2b. Band ablation: split modes into frequency bands, kill one band at a time
freqs = d['freqs'] if 'freqs' in d else None
n_bands = 4
band_size = n_modes // n_bands
dropout_band = {}
for b in range(n_bands):
    Xd = X.copy()
    start = axis_block + b * band_size
    end = axis_block + (b + 1) * band_size if b < n_bands - 1 else Fd
    Xd[:, start:end] = 0
    acc = loro(Xd, L, 1.0)
    label = f'band_{b}_({start - axis_block}:{end - axis_block})'
    dropout_band[label] = round(acc, 2)
    print(f"  kill {label}: {acc:5.1f}")

# 2c. Kill ALL modes, keep only axis windows
Xd = X.copy(); Xd[:, axis_block:] = 0
acc_axis_only = loro(Xd, L, 1.0)
print(f"  axis windows only (no modes): {acc_axis_only:5.1f}")

results['mode_dropout'] = {
    'random': dropout_random,
    'band_ablation': dropout_band,
    'axis_only': round(acc_axis_only, 2),
}
print(f"  [{time.time() - t0:.0f}s elapsed]")

# ============================================================
# 3. SMALL-READOUT STRESS TEST
# ============================================================
print("\n" + "=" * 60)
print("3. SMALL-READOUT STRESS TEST (sigma=1.0)")
print("=" * 60)
readout_sizes = [4, 8, 16, 32, 64, 128, Fd]
readout_results = {}

# Rank modes by Fisher discriminant ratio
Xn = (X - X.mean(0)) / (X.std(0) + 1e-9)
gm = Xn.mean(0)
bw = np.zeros(Fd); wi = np.zeros(Fd)
for c in np.unique(L):
    v = Xn[L == c]
    bw += len(v) * (v.mean(0) - gm) ** 2
    wi += ((v - v.mean(0)) ** 2).sum(0)
fisher = bw / (wi + 1e-9)
ranked = np.argsort(-fisher)

for k in readout_sizes:
    idx = ranked[:k]
    acc = loro(X[:, idx], L, 1.0)
    readout_results[f'top{k}'] = round(acc, 2)
    print(f"  top-{k:4d} features: {acc:5.1f}")

# Also test random subsets for comparison
for k in [8, 16, 32, 64]:
    idx = rng.choice(Fd, k, replace=False)
    acc = loro(X[:, idx], L, 1.0)
    readout_results[f'rand{k}'] = round(acc, 2)
    print(f"  rand-{k:4d} features: {acc:5.1f}")

results['small_readout'] = readout_results
print(f"  [{time.time() - t0:.0f}s elapsed]")

# ============================================================
# 4. SOFTWARE-KERNEL BASELINES
# ============================================================
print("\n" + "=" * 60)
print("4. SOFTWARE-KERNEL BASELINES (sigma=1.0)")
print("=" * 60)
baseline_results = {}

# 4a. Random projection of wire features to various dims
for dim in [32, 64, 128, 240]:
    RP = rng.standard_normal((len(driven), dim)) / np.sqrt(len(driven))
    Xrp = X[:, driven] @ RP
    acc = loro(Xrp, L, 1.0)
    baseline_results[f'wire_rp{dim}'] = round(acc, 2)
    print(f"  wire -> RP({dim:3d}): {acc:5.1f}")

# 4b. Random matrix (no physics at all)
for dim in [32, 64, 128, 240]:
    Xrand = rng.standard_normal((X.shape[0], dim))
    acc = loro(Xrand, L, 1.0)
    baseline_results[f'pure_rand{dim}'] = round(acc, 2)
    print(f"  pure random({dim:3d}): {acc:5.1f}")

# 4c. Permuted glass: shuffle features within each sample (breaks physics structure)
Xperm = X.copy()
for i in range(Xperm.shape[0]):
    Xperm[i] = rng.permutation(Xperm[i])
acc_perm = loro(Xperm, L, 1.0)
baseline_results['glass_permuted'] = round(acc_perm, 2)
print(f"  glass (permuted per-sample): {acc_perm:5.1f}")

# 4d. Glass features but with shuffled labels (null model)
L_shuf = rng.permutation(L)
acc_null = loro(X, L_shuf, 1.0)
baseline_results['glass_null_labels'] = round(acc_null, 2)
print(f"  glass (null/shuffled labels): {acc_null:5.1f}")

results['software_baselines'] = baseline_results
print(f"  [{time.time() - t0:.0f}s elapsed]")

# ============================================================
# 5. CROSS-VALIDATION ABUSE CHECK (permutation test)
# ============================================================
print("\n" + "=" * 60)
print("5. CROSS-VALIDATION ABUSE CHECK")
print("=" * 60)
n_perms = 20
perm_accs = []
for i in range(n_perms):
    Lp = rng.permutation(L)
    acc = loro(X, Lp, 1.0)
    perm_accs.append(round(acc, 2))
    if i < 5 or i == n_perms - 1:
        print(f"  perm {i+1:2d}/{n_perms}: {acc:5.1f}")
    elif i == 5:
        print(f"  ...")

real_acc = loro(X, L, 1.0)
perm_mean = np.mean(perm_accs)
perm_std = np.std(perm_accs)
p_value = np.mean([pa >= real_acc for pa in perm_accs])
print(f"\n  Real accuracy:     {real_acc:5.1f}")
print(f"  Permutation mean:  {perm_mean:5.1f} +/- {perm_std:4.1f}")
print(f"  p-value (1-sided): {p_value:.3f}")
print(f"  z-score:           {(real_acc - perm_mean) / (perm_std + 1e-9):.1f}")

results['cv_abuse_check'] = {
    'real_acc': round(real_acc, 2),
    'perm_accs': perm_accs,
    'perm_mean': round(perm_mean, 2),
    'perm_std': round(perm_std, 2),
    'p_value': round(p_value, 4),
    'n_perms': n_perms,
}
print(f"  [{time.time() - t0:.0f}s elapsed]")

# ============================================================
# Save
# ============================================================
out = Path(p).with_name(
    'offline_reanalysis_' + Path(p).stem.split('_')[-1] + '.json')
json.dump(results, open(out, 'w'), indent=1)
print(f"\nAll results saved to {out}")
print(f"Total time: {time.time() - t0:.0f}s")
