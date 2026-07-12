#!/usr/bin/env python3
"""
Simulated engineered band gaps for spectral page multiplexing.

The real plate has massive cross-talk: changing drive in band A affects ALL modes.
This script simulates what happens with *engineered isolation* — as if each
frequency band were a physically separate resonator array with no mechanical
coupling to other bands.

Simulation approaches:
1. DECORRELATED BANDS: orthogonalize features between bands (remove shared variance)
2. INDEPENDENT ENCODING: assign different state variables to different bands,
   test if each band can independently recall its assigned content
3. SYNTHETIC ISOLATED PAGES: generate idealized isolated-band features and
   test capacity/cross-talk bounds
4. PARTIAL ISOLATION: vary isolation strength from 0% (current plate) to
   100% (perfect band gaps) — find the threshold where pages become useful

Usage: python3 tools/simulate_band_gaps.py [npz]
"""
import numpy as np, json, sys, glob, time
from pathlib import Path
from sklearn.linear_model import RidgeClassifier, Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

p = sys.argv[1] if len(sys.argv) > 1 else sorted(
    glob.glob('data/results/pong/recall_enroll_*.npz'))[-1]
d = np.load(p)
X = d['X']; L = d['L']; R = int(d['repeats']); PADH = int(d['padh'])
driven = d['driven']; NW = int(d['nw']); naxes = int(d['naxes'])
xs = d['xs']; ys = d['ys']; vx = d['vx']; vy = d['vy']
freqs = d['freqs']
Fd = X.shape[1]; axis_block = naxes * NW
X_raw = X.copy()
X = X / (X.mean(1, keepdims=True) + 1e-9)
rng = np.random.default_rng(42)

mode_indices = np.arange(axis_block, Fd)
n_modes = len(mode_indices)
groups = np.arange(len(X)) % R

print(f"Loaded: X{X.shape}, {n_modes} modes ({freqs.min():.0f}-{freqs.max():.0f} Hz)")
results = {'source': str(p)}
t0 = time.time()

AXES = ['x', 'y', 'vx', 'vy']
state_vars = {'x': xs, 'y': ys, 'vx': (vx > 0).astype(int),
              'vy': (vy > 0).astype(int), 'landing': L}


def loro_acc(Xf, lab):
    """Leave-one-repeat-out Ridge classification accuracy."""
    sc = StandardScaler()
    preds = np.zeros(len(lab), dtype=int)
    for rt in range(R):
        te = [i for i in range(len(lab)) if i % R == rt]
        tr = [i for i in range(len(lab)) if i % R != rt]
        Xs = sc.fit_transform(Xf[tr])
        clf = RidgeClassifier(alpha=1.0).fit(Xs, lab[tr])
        preds[te] = clf.predict(sc.transform(Xf[te]))
    if len(np.unique(lab)) <= 2:
        return np.mean(preds == lab) * 100
    return np.mean(np.abs(preds - lab) <= PADH // 2) * 100


# ==============================================================
# 1. CURRENT STATE: cross-talk quantification
# ==============================================================
print("\n" + "=" * 65)
print("1. CURRENT PLATE: cross-talk between 4 frequency bands")
print("=" * 65)

n_pages = 4
page_size = n_modes // n_pages
pages = []
for p_idx in range(n_pages):
    start = p_idx * page_size
    end = (p_idx + 1) * page_size if p_idx < n_pages - 1 else n_modes
    pages.append(mode_indices[start:end])

# Cross-talk: variance shared between bands (via correlation)
X_modes = X[:, mode_indices]
band_feats = [X_modes[:, p - axis_block] for p in pages]

# Compute inter-band correlation matrix (mean |r| between all pairs of bands)
print("\n  Inter-band mean |correlation|:")
print(f"  {'':8s}" + "".join(f"  Band{j}" for j in range(n_pages)))
corr_matrix = np.zeros((n_pages, n_pages))
for i in range(n_pages):
    for j in range(n_pages):
        # Sample 50 features from each band for speed
        n_samp = min(50, band_feats[i].shape[1], band_feats[j].shape[1])
        idx_i = rng.choice(band_feats[i].shape[1], n_samp, replace=False)
        idx_j = rng.choice(band_feats[j].shape[1], n_samp, replace=False)
        corrs = []
        for fi in idx_i:
            for fj in idx_j:
                c = np.corrcoef(band_feats[i][:, fi], band_feats[j][:, fj])[0, 1]
                if np.isfinite(c):
                    corrs.append(abs(c))
        corr_matrix[i, j] = np.mean(corrs) if corrs else 0
    row = "  ".join(f"{corr_matrix[i, j]:.3f}" for j in range(n_pages))
    print(f"  Band{i}  {row}")

cross_talk_level = np.mean(corr_matrix[np.triu_indices(n_pages, k=1)])
print(f"\n  Mean off-diagonal |correlation|: {cross_talk_level:.3f}")
print(f"  Mean on-diagonal |correlation|:  {np.mean(np.diag(corr_matrix)):.3f}")
results['current_crosstalk'] = {
    'matrix': corr_matrix.tolist(),
    'off_diagonal_mean': round(float(cross_talk_level), 4),
}


# ==============================================================
# 2. SIMULATED BAND GAPS: decorrelate bands via orthogonalization
# ==============================================================
print("\n" + "=" * 65)
print("2. SIMULATED BAND GAPS: orthogonalized bands")
print("=" * 65)

# Strategy: for each band, project out the variance explained by other bands
# This simulates perfect mechanical isolation between resonator arrays

X_isolated = np.zeros_like(X_modes)
for p_idx in range(n_pages):
    target_cols = np.arange(p_idx * page_size,
                            min((p_idx + 1) * page_size, n_modes))
    other_cols = np.concatenate([np.arange(j * page_size,
                                           min((j + 1) * page_size, n_modes))
                                 for j in range(n_pages) if j != p_idx])

    # Project out variance from other bands
    X_other = X_modes[:, other_cols]
    X_target = X_modes[:, target_cols]

    # Orthogonalize: X_target_isolated = X_target - X_other @ (X_other+ @ X_target)
    # Use truncated SVD for stability
    U, s, Vt = np.linalg.svd(X_other, full_matrices=False)
    # Keep components explaining 95% of other-band variance
    cumvar = np.cumsum(s ** 2) / (s ** 2).sum()
    k = max(1, np.searchsorted(cumvar, 0.95) + 1)
    U_k = U[:, :k]
    # Project out
    projection = U_k @ (U_k.T @ X_target)
    X_isolated[:, target_cols] = X_target - projection

# Verify: reduced cross-talk
iso_band_feats = [X_isolated[:, p_idx * page_size:min((p_idx+1)*page_size, n_modes)]
                  for p_idx in range(n_pages)]

print("  After orthogonalization — inter-band |correlation|:")
print(f"  {'':8s}" + "".join(f"  Band{j}" for j in range(n_pages)))
iso_corr = np.zeros((n_pages, n_pages))
for i in range(n_pages):
    for j in range(n_pages):
        n_samp = min(50, iso_band_feats[i].shape[1], iso_band_feats[j].shape[1])
        idx_i = rng.choice(iso_band_feats[i].shape[1], n_samp, replace=False)
        idx_j = rng.choice(iso_band_feats[j].shape[1], n_samp, replace=False)
        corrs = []
        for fi in idx_i:
            for fj in idx_j:
                c = np.corrcoef(iso_band_feats[i][:, fi], iso_band_feats[j][:, fj])[0, 1]
                if np.isfinite(c):
                    corrs.append(abs(c))
        iso_corr[i, j] = np.mean(corrs) if corrs else 0
    row = "  ".join(f"{iso_corr[i, j]:.3f}" for j in range(n_pages))
    print(f"  Band{i}  {row}")

iso_xt = np.mean(iso_corr[np.triu_indices(n_pages, k=1)])
print(f"\n  Off-diagonal after isolation: {iso_xt:.3f} (was {cross_talk_level:.3f})")


# ==============================================================
# 3. PAGE CLASSIFICATION: before vs after isolation
# ==============================================================
print("\n" + "=" * 65)
print("3. PAGE CLASSIFICATION: current plate vs simulated band gaps")
print("=" * 65)

print(f"\n  {'Target':<10s} {'Band':<8s} {'Current':>8s} {'Isolated':>8s} {'Delta':>8s}")
print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

page_class_results = {}
for vname, vdata in state_vars.items():
    for p_idx in range(n_pages):
        target_cols = slice(p_idx * page_size, min((p_idx+1)*page_size, n_modes))
        acc_current = loro_acc(X_modes[:, target_cols], vdata)
        acc_isolated = loro_acc(X_isolated[:, target_cols], vdata)
        delta = acc_isolated - acc_current
        print(f"  {vname:<10s} Band{p_idx:<4d} {acc_current:>7.1f}% {acc_isolated:>7.1f}% {delta:>+7.1f}%")
        page_class_results[f'{vname}_band{p_idx}'] = {
            'current': round(acc_current, 1),
            'isolated': round(acc_isolated, 1),
        }

results['page_classification'] = page_class_results
print(f"  [{time.time() - t0:.0f}s elapsed]")


# ==============================================================
# 4. INDEPENDENT PAGE CONTENT: assign different info to each band
# ==============================================================
print("\n" + "=" * 65)
print("4. INDEPENDENT PAGE CONTENT (one state var per band)")
print("=" * 65)

# Assign: Band0→x, Band1→y, Band2→vx, Band3→vy
# Test if isolated bands can carry their assigned variable independently
assignments = [('x', xs), ('y', ys), ('vx', (vx>0).astype(int)), ('vy', (vy>0).astype(int))]
indep_results = {}

print(f"\n  {'Band':<12s} {'Assigned':>8s} {'Acc(cur)':>9s} {'Acc(iso)':>9s} "
      f"{'Leak-other(cur)':>15s} {'Leak-other(iso)':>15s}")
print(f"  {'-'*12} {'-'*8} {'-'*9} {'-'*9} {'-'*15} {'-'*15}")

for p_idx, (vname, vdata) in enumerate(assignments):
    target_cols = slice(p_idx * page_size, min((p_idx+1)*page_size, n_modes))

    # Accuracy on assigned variable
    acc_cur = loro_acc(X_modes[:, target_cols], vdata)
    acc_iso = loro_acc(X_isolated[:, target_cols], vdata)

    # "Leakage": can OTHER bands predict this band's assigned variable?
    other_accs_cur = []
    other_accs_iso = []
    for j in range(n_pages):
        if j == p_idx:
            continue
        other_cols = slice(j * page_size, min((j+1)*page_size, n_modes))
        other_accs_cur.append(loro_acc(X_modes[:, other_cols], vdata))
        other_accs_iso.append(loro_acc(X_isolated[:, other_cols], vdata))

    leak_cur = np.mean(other_accs_cur)
    leak_iso = np.mean(other_accs_iso)

    print(f"  Band{p_idx} → {vname:<5s} {acc_cur:>8.1f}% {acc_iso:>8.1f}% "
          f"{leak_cur:>14.1f}% {leak_iso:>14.1f}%")

    indep_results[f'band{p_idx}_{vname}'] = {
        'acc_current': round(acc_cur, 1),
        'acc_isolated': round(acc_iso, 1),
        'leak_current': round(leak_cur, 1),
        'leak_isolated': round(leak_iso, 1),
    }

results['independent_pages'] = indep_results


# ==============================================================
# 5. ISOLATION STRENGTH SWEEP
# ==============================================================
print("\n" + "=" * 65)
print("5. ISOLATION STRENGTH SWEEP (0%=current → 100%=perfect)")
print("=" * 65)

# Interpolate between current (coupled) and isolated (orthogonalized)
# X_interp = (1 - alpha) * X_modes + alpha * X_isolated
strengths = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
sweep_results = {}

# Test: can Band0 classify x WITHOUT leaking to Band1's classification of y?
print(f"\n  Isolation%  Band0→x  Band1→y  Band0→y(leak)  Band1→x(leak)  Isolation score")
print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*13} {'-'*13} {'-'*15}")

for alpha in strengths:
    X_mix = (1 - alpha) * X_modes + alpha * X_isolated
    b0 = X_mix[:, :page_size]
    b1 = X_mix[:, page_size:2*page_size]

    acc_b0_x = loro_acc(b0, xs)
    acc_b1_y = loro_acc(b1, ys)
    leak_b0_y = loro_acc(b0, ys)  # band0 shouldn't know y
    leak_b1_x = loro_acc(b1, xs)  # band1 shouldn't know x

    # Isolation score: how much more does each band know about its OWN var
    # vs the OTHER band's var?
    iso_score = ((acc_b0_x - leak_b0_y) + (acc_b1_y - leak_b1_x)) / 2

    print(f"  {int(alpha*100):>8d}%  {acc_b0_x:>6.1f}%  {acc_b1_y:>6.1f}%  "
          f"{leak_b0_y:>11.1f}%  {leak_b1_x:>11.1f}%  {iso_score:>+13.1f}%")

    sweep_results[f'{int(alpha*100)}pct'] = {
        'band0_x': round(acc_b0_x, 1),
        'band1_y': round(acc_b1_y, 1),
        'leak_b0_y': round(leak_b0_y, 1),
        'leak_b1_x': round(leak_b1_x, 1),
        'isolation_score': round(iso_score, 1),
    }

results['isolation_sweep'] = sweep_results


# ==============================================================
# 6. WHAT WOULD A 4-PAGE MEMS DEVICE NEED?
# ==============================================================
print("\n" + "=" * 65)
print("6. MEMS REQUIREMENTS: what isolation level enables 4 useful pages?")
print("=" * 65)

# At full isolation (alpha=1.0), test multi-page independent recall
# Each page stores a different state variable
# "Useful" = each page independently gets >80% on its assigned variable
# while leakage to other pages is <chance+10%

# Chance levels
chance = {'x': 100.0/8, 'y': 100.0/8, 'vx': 50.0, 'vy': 50.0}
useful_threshold = {k: v + 20 for k, v in chance.items()}  # 20% above chance

print(f"\n  Variable  Chance  Threshold(useful)  Best-band(iso)  Verdict")
print(f"  {'-'*8} {'-'*7} {'-'*17} {'-'*14} {'-'*7}")

mems_verdict = {}
for p_idx, (vname, vdata) in enumerate(assignments):
    target_cols = slice(p_idx * page_size, min((p_idx+1)*page_size, n_modes))
    acc = loro_acc(X_isolated[:, target_cols], vdata)
    ch = chance[vname]
    thr = useful_threshold[vname]
    verdict = "PASS" if acc > thr else "FAIL"
    print(f"  {vname:<8s} {ch:>6.1f}% {thr:>16.1f}% {acc:>13.1f}%  {verdict}")
    mems_verdict[vname] = {
        'chance': round(ch, 1), 'threshold': round(thr, 1),
        'acc_isolated': round(acc, 1), 'verdict': verdict,
    }

results['mems_requirements'] = mems_verdict
print(f"\n  [{time.time() - t0:.0f}s elapsed]")


# ==============================================================
# 7. CAPACITY ESTIMATE: how many isolated pages are theoretically useful?
# ==============================================================
print("\n" + "=" * 65)
print("7. CAPACITY ESTIMATE: pages vs features-per-page trade-off")
print("=" * 65)

# With N modes total, splitting into P pages gives N/P features per page.
# More pages = fewer features per page = less discriminating power per page.
# Find the sweet spot.

for n_pg in [2, 3, 4, 6, 8, 12, 16]:
    pg_size = n_modes // n_pg
    if pg_size < 4:
        continue

    # Use isolated features, test landing recall per page
    accs = []
    for pi in range(n_pg):
        cols = slice(pi * pg_size, min((pi + 1) * pg_size, n_modes))
        acc = loro_acc(X_isolated[:, cols], L)
        accs.append(acc)

    mean_acc = np.mean(accs)
    min_acc = np.min(accs)
    print(f"  {n_pg:2d} pages × {pg_size:3d} feats/page: "
          f"mean={mean_acc:.1f}% min={min_acc:.1f}% (landing recall)")
    results.setdefault('capacity_curve', {})[f'{n_pg}_pages'] = {
        'feats_per_page': pg_size,
        'mean_acc': round(mean_acc, 1),
        'min_acc': round(min_acc, 1),
    }


# ==============================================================
# Save
# ==============================================================
out = Path('data/results/band_gap_simulation.json')
json.dump(results, open(out, 'w'), indent=1)
print(f"\n{'=' * 65}")
print(f"Saved to {out}")
print(f"Total time: {time.time() - t0:.0f}s")
