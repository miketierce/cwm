#!/usr/bin/env python3
"""RH Gate A — Pooled multi-census analysis to break rank ceiling."""

import json, numpy as np
from scipy.spatial.distance import pdist, squareform, cdist
from scipy.stats import spearmanr

# ---- Load four census files (3 old + 1 fresh PicoScope CW) ----
census_files = [
    ('run1', 'data/results/lab/plate_exps/plate_census_kronos_flash_20260415_211405.json'),
    ('run2', 'data/results/lab/plate_exps/plate_census_kronos_flash_20260416_144549.json'),
    ('run3', 'data/results/lab/plate_exps/plate_census_hybrid_flash_20260416_204546.json'),
    ('run4', 'data/results/lab/plate_exps/plate_census_20260418_221958.json'),
]

def normalize_key(k):
    if k in ('1_NE', '1'): return '1'
    if k in ('2_NE', '2'): return '2'
    return k

PLATE_NAMES = {'1': 'A', '2': 'B', '3_NE': 'G_NE', '3_NW': 'G_NW',
               '4_NE': 'D_NE', '4_NW': 'D_NW', '5_NE': 'H_NE', '5_NW': 'H_NW'}

FREQ_MIN, FREQ_MAX, N_BINS = 200, 96000, 500
bin_edges = np.linspace(FREQ_MIN, FREQ_MAX, N_BINS + 1)

samples = []
for run_name, path in census_files:
    with open(path) as f:
        d = json.load(f)
    results = d.get('results', d)
    for raw_key, val in results.items():
        if not isinstance(val, dict) or 'peaks' not in val:
            continue
        key = normalize_key(raw_key)
        plate = PLATE_NAMES.get(key, key)
        peaks = val['peaks']

        mag_vec = np.zeros(N_BINS)
        phase_vec = np.zeros(N_BINS)
        count_vec = np.zeros(N_BINS)
        for pk in peaks:
            f = pk['freq_hz']
            idx = np.searchsorted(bin_edges, f) - 1
            if 0 <= idx < N_BINS:
                mag_vec[idx] += pk['magnitude']
                phase_vec[idx] += pk.get('phase_rad', 0)
                count_vec[idx] += 1
        mask = count_vec > 0
        phase_vec[mask] /= count_vec[mask]

        samples.append((run_name, key, plate, mag_vec, phase_vec))

print(f'Loaded {len(samples)} samples from {len(census_files)} runs')
for run, key, plate, m, p in samples:
    nz = np.count_nonzero(m)
    print(f'  {run}/{key} -> {plate}: {nz} non-zero bins')

# Build feature matrix
run_labels = [s[0] for s in samples]
key_labels = [s[1] for s in samples]
plate_labels = [s[2] for s in samples]
plate_base = [p.split('_')[0] for p in plate_labels]

mag_mat = np.array([s[3] for s in samples])
phase_mat = np.array([s[4] for s in samples])
X = np.hstack([mag_mat, phase_mat])
n_samples, n_features = X.shape

X_c = X - X.mean(axis=0)
stds = X_c.std(axis=0)
stds[stds==0] = 1.0
X_norm = X_c / stds

print(f'\nFeature matrix: {n_samples} samples x {n_features} features')

# ---- PCA ----
U, S, Vt = np.linalg.svd(X_norm, full_matrices=False)
ev = S**2 / (n_samples - 1)
total = ev.sum()
var_cum = np.cumsum(ev) / total

d90 = int(np.searchsorted(var_cum, 0.90) + 1)
d95 = int(np.searchsorted(var_cum, 0.95) + 1)
d99 = int(np.searchsorted(var_cum, 0.99) + 1)
pr = (ev.sum()**2) / (ev**2).sum()

print(f'\n{"="*70}')
print(f'PCA RESULTS (POOLED, {n_samples} samples)')
print(f'{"="*70}')
print(f'N_features: {n_features}')
print(f'Max possible rank: {min(n_samples, n_features) - 1}')
n_nonzero = np.sum(ev > 1e-10)
print(f'Non-zero components: {n_nonzero}')
print(f'd_eff(90%): {d90}')
print(f'd_eff(95%): {d95}')
print(f'd_eff(99%): {d99}')
print(f'Participation ratio: {pr:.2f}')
print(f'd95/N_feat: {d95/n_features:.4f}')
print()

for i in range(min(20, len(ev))):
    bar = '#' * int(50 * ev[i] / ev[0]) if ev[0] > 0 else ''
    print(f'  PC{i+1:2d}: {ev[i]/total:6.1%} (cum {var_cum[i]:6.1%}) {bar}')

# ---- NN Identity ----
print(f'\n{"="*70}')
print(f'NEAREST-NEIGHBOR IDENTITY')
print(f'{"="*70}')
D = squareform(pdist(X_norm))
np.fill_diagonal(D, np.inf)
nn = np.argmin(D, axis=1)

same_key_nn = 0
same_plate_nn = 0
for i in range(n_samples):
    j = nn[i]
    if key_labels[j] == key_labels[i] and run_labels[j] != run_labels[i]:
        same_key_nn += 1
    if plate_base[j] == plate_base[i]:
        same_plate_nn += 1

print(f'NN is same relay (diff run): {same_key_nn}/{n_samples} = {same_key_nn/n_samples:.1%}')
print(f'NN is same plate (any):      {same_plate_nn}/{n_samples} = {same_plate_nn/n_samples:.1%}')

print(f'\nAll NN pairs:')
for i in range(n_samples):
    j = nn[i]
    match = 'RELAY' if key_labels[j]==key_labels[i] and run_labels[j]!=run_labels[i] else ''
    plate_match = 'PLATE' if plate_base[j]==plate_base[i] else ''
    print(f'  {run_labels[i]}/{plate_labels[i]:>4s} -> {run_labels[j]}/{plate_labels[j]:>4s} (d={D[i,j]:.2f}) {match} {plate_match}')

# ---- Shuffle test ----
print(f'\n{"="*70}')
print(f'SHUFFLE MODE LABELS')
print(f'{"="*70}')
n_mag = mag_mat.shape[1]
preserved = []
for trial in range(200):
    rng = np.random.default_rng(trial)
    pm = rng.permutation(n_mag)
    pp = rng.permutation(n_features - n_mag)
    Xs = np.hstack([X_norm[:,:n_mag][:,pm], X_norm[:,n_mag:][:,pp]])
    Ds = squareform(pdist(Xs))
    np.fill_diagonal(Ds, np.inf)
    ns = np.argmin(Ds, axis=1)
    preserved.append(np.mean(nn == ns))
print(f'Shuffled NN preserved: {np.mean(preserved):.1%} +/- {np.std(preserved):.1%}')

# Plate-level shuffle preservation
plate_preserved = []
for trial in range(200):
    rng = np.random.default_rng(trial)
    pm = rng.permutation(n_mag)
    pp = rng.permutation(n_features - n_mag)
    Xs = np.hstack([X_norm[:,:n_mag][:,pm], X_norm[:,n_mag:][:,pp]])
    Ds = squareform(pdist(Xs))
    np.fill_diagonal(Ds, np.inf)
    ns = np.argmin(Ds, axis=1)
    plate_preserved.append(np.mean([plate_base[ns[i]]==plate_base[i] for i in range(n_samples)]))
print(f'Shuffled plate preserved: {np.mean(plate_preserved):.1%} +/- {np.std(plate_preserved):.1%}')

# ---- Subspace stability ----
print(f'\n{"="*70}')
print(f'SUBSPACE PROJECTION STABILITY')
print(f'{"="*70}')
for frac in [0.5, 0.3, 0.2, 0.1]:
    n_keep = max(1, int(n_features * frac))
    pres = []
    for trial in range(100):
        rng = np.random.default_rng(trial)
        cols = rng.choice(n_features, size=n_keep, replace=False)
        Xs = X_norm[:, cols]
        Ds = squareform(pdist(Xs))
        np.fill_diagonal(Ds, np.inf)
        ns = np.argmin(Ds, axis=1)
        pres.append(np.mean(nn == ns))
    print(f'  {frac:.0%} retention ({n_keep} feats): NN preserved = {np.mean(pres):.1%} +/- {np.std(pres):.1%}')

# ---- Cross-run transfer ----
print(f'\n{"="*70}')
print(f'CROSS-RUN TRANSFER (enroll/test)')
print(f'{"="*70}')
for enroll_run, test_run in [('run1','run2'), ('run1','run3'), ('run2','run3'),
                                ('run1','run4'), ('run2','run4'), ('run3','run4')]:
    enroll_idx = [i for i in range(n_samples) if run_labels[i] == enroll_run]
    test_idx = [i for i in range(n_samples) if run_labels[i] == test_run]

    X_enroll = X_norm[enroll_idx]
    X_test = X_norm[test_idx]

    D_cross = cdist(X_test, X_enroll)
    nn_cross = np.argmin(D_cross, axis=1)

    correct_key = 0
    correct_plate = 0
    for ti, t in enumerate(test_idx):
        ei = enroll_idx[nn_cross[ti]]
        if key_labels[ei] == key_labels[t]:
            correct_key += 1
        if plate_base[ei] == plate_base[t]:
            correct_plate += 1
    print(f'  {enroll_run} -> {test_run}: relay={correct_key}/{len(test_idx)} ({correct_key/len(test_idx):.0%}), plate={correct_plate}/{len(test_idx)} ({correct_plate/len(test_idx):.0%})')

# ---- Contiguous vs Random Dropout ----
print(f'\n{"="*70}')
print(f'CONTIGUOUS VS RANDOM DROPOUT')
print(f'{"="*70}')
for frac in [0.2, 0.4, 0.6]:
    n_drop = int(n_mag * frac)
    rand_pres = []
    for trial in range(100):
        rng = np.random.default_rng(trial)
        keep = np.ones(n_features, dtype=bool)
        drop_idx = rng.choice(n_mag, size=n_drop, replace=False)
        keep[drop_idx] = False
        keep[drop_idx + n_mag] = False
        Xs = X_norm[:, keep]
        Ds = squareform(pdist(Xs))
        np.fill_diagonal(Ds, np.inf)
        ns = np.argmin(Ds, axis=1)
        rand_pres.append(np.mean(nn == ns))

    contig_pres = []
    for trial in range(100):
        rng = np.random.default_rng(trial + 5000)
        start = rng.integers(0, n_mag - n_drop + 1)
        keep = np.ones(n_features, dtype=bool)
        keep[start:start+n_drop] = False
        keep[start+n_mag:start+n_mag+n_drop] = False
        Xs = X_norm[:, keep]
        Ds = squareform(pdist(Xs))
        np.fill_diagonal(Ds, np.inf)
        ns = np.argmin(Ds, axis=1)
        contig_pres.append(np.mean(nn == ns))

    rm, cm = np.mean(rand_pres), np.mean(contig_pres)
    diff = rm - cm
    marker = ''
    if cm < rm - 0.05: marker = ' <- contiguous hurts more (GEOMETRY)'
    elif abs(diff) <= 0.05: marker = ' <- similar (REDUNDANCY)'
    print(f'  {frac:.0%} dropout: random={rm:.1%}, contig={cm:.1%}, delta={diff:+.1%}{marker}')

# ---- Distance matrix (PCA projected) ----
print(f'\n{"="*70}')
print(f'PCA DISTANCE MATRIX (d={d95})')
print(f'{"="*70}')
X_pca = X_norm @ Vt[:d95].T
D_pca = squareform(pdist(X_pca))

# Print condensed: average intra-relay distance (same key, diff run) vs inter-relay
intra_dists = []
inter_dists = []
for i in range(n_samples):
    for j in range(i+1, n_samples):
        if key_labels[i] == key_labels[j]:
            intra_dists.append(D_pca[i,j])
        else:
            inter_dists.append(D_pca[i,j])

print(f'  Intra-relay (same key, diff run) distances: n={len(intra_dists)}')
if intra_dists:
    print(f'    mean={np.mean(intra_dists):.2f}, std={np.std(intra_dists):.2f}, range=[{np.min(intra_dists):.2f}, {np.max(intra_dists):.2f}]')
print(f'  Inter-relay distances: n={len(inter_dists)}')
if inter_dists:
    print(f'    mean={np.mean(inter_dists):.2f}, std={np.std(inter_dists):.2f}, range=[{np.min(inter_dists):.2f}, {np.max(inter_dists):.2f}]')

if intra_dists and inter_dists:
    separation = np.mean(inter_dists) / np.mean(intra_dists)
    print(f'  Separation ratio (inter/intra): {separation:.2f}')
    if separation > 2:
        print(f'  -> STRONG: Relay paths form tight clusters, well separated')
    elif separation > 1.2:
        print(f'  -> MODERATE: Some clustering')
    else:
        print(f'  -> WEAK: No clear clustering by relay identity')

# Same plate (NE vs NW) vs different plate
intra_plate = []
inter_plate = []
for i in range(n_samples):
    for j in range(i+1, n_samples):
        if plate_base[i] == plate_base[j]:
            intra_plate.append(D_pca[i,j])
        else:
            inter_plate.append(D_pca[i,j])
print(f'\n  Intra-plate distances: n={len(intra_plate)}')
if intra_plate:
    print(f'    mean={np.mean(intra_plate):.2f}, std={np.std(intra_plate):.2f}')
print(f'  Inter-plate distances: n={len(inter_plate)}')
if inter_plate:
    print(f'    mean={np.mean(inter_plate):.2f}, std={np.std(inter_plate):.2f}')
if intra_plate and inter_plate:
    plate_sep = np.mean(inter_plate) / np.mean(intra_plate)
    print(f'  Plate separation ratio: {plate_sep:.2f}')

# ---- GATE A DECISION ----
print(f'\n{"="*70}')
print(f'GATE A DECISION (POOLED)')
print(f'{"="*70}')
print(f'  d_eff(95%) / N_features = {d95}/{n_features} = {d95/n_features:.4f}')
print(f'  Non-zero PCs: {n_nonzero} (rank ceiling: {min(n_samples, n_features)-1})')
print(f'  PR: {pr:.2f} (out of {n_nonzero} possible)')
print(f'  Shuffled NN preserved: {np.mean(preserved):.1%}')
print(f'  Cross-run relay identification: see above')

if d95/n_features < 0.3 and np.mean(preserved) < 0.7:
    print(f'\n  GATE A: PROCEED')
elif d95/n_features > 0.8 and np.mean(preserved) > 0.8:
    print(f'\n  GATE A: ABANDON')
else:
    print(f'\n  GATE A: MIXED')

# Key question: does the eigenvalue spectrum show concentration?
top3_var = var_cum[2] if len(var_cum) > 2 else var_cum[-1]
print(f'\n  Top 3 PCs explain: {top3_var:.1%} of variance')
if top3_var > 0.8:
    print(f'  -> Variance concentrated in few dimensions: MANIFOLD EVIDENCE')
elif top3_var > 0.5:
    print(f'  -> Moderate concentration')
else:
    print(f'  -> Variance spread: no strong manifold')
