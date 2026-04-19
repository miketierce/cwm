#!/usr/bin/env python3
"""
RH Gate A Experiments — Representation Hypothesis, computational tier.

Runs on existing census data (no hardware required).
  RH-02: Intrinsic Dimensionality
  RH-05: Redundancy vs. Invariance
  RH-01: Cross-Measure Transfer
  RH-03: Cross-Object Generalization

Usage:
  python tools/rh_gate_a.py --census <census.json> --sweeps <sweeps.json>
"""

import argparse, json, sys, os, warnings
from pathlib import Path
from datetime import datetime

import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Data loading: build feature matrices from census + sweep files
# ---------------------------------------------------------------------------

def load_census(path):
    """Load census JSON, return dict of relay_key -> peak list."""
    with open(path) as f:
        d = json.load(f)
    results = d.get("results", d)
    plates = {}
    for key, val in results.items():
        if isinstance(val, dict) and "peaks" in val:
            plates[key] = val
    return plates


def load_sweeps(path):
    """Load sweep JSON, return dict of relay_key -> sweep_data list."""
    with open(path) as f:
        d = json.load(f)
    # Sweeps file may have top-level keys as relay IDs directly
    sweeps = {}
    for key, val in d.items():
        if isinstance(val, dict) and "sweep_data" in val:
            sweeps[key] = val
    return sweeps


def build_spectral_vectors(sweeps):
    """
    Build aligned spectral feature matrices from raw sweep data.
    Returns: freq_axis (N,), mag_matrix (n_plates, N), phase_matrix (n_plates, N), labels
    """
    keys = sorted(sweeps.keys())
    # Use first sweep to establish freq axis
    ref = sweeps[keys[0]]["sweep_data"]
    freq_axis = np.array([p["freq_hz"] for p in ref])

    mag_matrix = []
    phase_matrix = []
    labels = []

    for key in keys:
        sd = sweeps[key]["sweep_data"]
        freqs = np.array([p["freq_hz"] for p in sd])
        mags = np.array([p["magnitude"] for p in sd])
        phases = np.array([p["phase_rad"] for p in sd])

        # Verify frequency alignment
        if len(freqs) != len(freq_axis) or not np.allclose(freqs, freq_axis, atol=1.0):
            print(f"  WARNING: {key} freq axis mismatch, interpolating...")
            mags = np.interp(freq_axis, freqs, mags)
            phases = np.interp(freq_axis, freqs, phases)

        mag_matrix.append(mags)
        phase_matrix.append(phases)
        labels.append(key)

    return freq_axis, np.array(mag_matrix), np.array(phase_matrix), labels


def build_peak_vectors(census, freq_min=200, freq_max=96000, n_bins=500):
    """
    Build binned peak-magnitude vectors from census peak lists.
    Each plate gets a vector of length n_bins where each bin accumulates
    the magnitude of detected peaks in that frequency range.
    Returns: bin_centers, mag_matrix, phase_matrix, labels
    """
    keys = sorted(census.keys())
    bin_edges = np.linspace(freq_min, freq_max, n_bins + 1)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

    mag_matrix = []
    phase_matrix = []
    labels = []

    for key in keys:
        peaks = census[key]["peaks"]
        mag_vec = np.zeros(n_bins)
        phase_vec = np.zeros(n_bins)
        count_vec = np.zeros(n_bins)

        for pk in peaks:
            f = pk["freq_hz"]
            idx = np.searchsorted(bin_edges, f) - 1
            if 0 <= idx < n_bins:
                mag_vec[idx] += pk["magnitude"]
                phase_vec[idx] += pk["phase_rad"]
                count_vec[idx] += 1

        # Average phase where multiple peaks land in same bin
        mask = count_vec > 0
        phase_vec[mask] /= count_vec[mask]

        mag_matrix.append(mag_vec)
        phase_matrix.append(phase_vec)
        labels.append(key)

    return bin_centers, np.array(mag_matrix), np.array(phase_matrix), labels


def plate_name_from_key(census, key):
    """Extract plate name from census entry."""
    entry = census.get(key, {})
    return entry.get("plate_name", key)


# ---------------------------------------------------------------------------
# RH-02: Intrinsic Dimensionality
# ---------------------------------------------------------------------------

def rh02_intrinsic_dimensionality(mag_matrix, phase_matrix, labels, census):
    """
    Compute intrinsic dimensionality metrics:
    - PCA variance explained curve
    - Participation ratio
    - Effective dimension at 90%, 95%, 99% thresholds
    - Subspace projection stability (random 50% features, 100 trials)
    """
    print("\n" + "=" * 70)
    print("RH-02: INTRINSIC DIMENSIONALITY")
    print("=" * 70)

    # Combine mag + phase into full feature vector
    X = np.hstack([mag_matrix, phase_matrix])
    n_samples, n_features = X.shape
    print(f"\nData: {n_samples} samples × {n_features} features (mag + phase)")
    print(f"Plates: {[plate_name_from_key(census, l) for l in labels]}")

    # Normalize columns to zero mean, unit variance
    X_centered = X - X.mean(axis=0)
    stds = X_centered.std(axis=0)
    stds[stds == 0] = 1.0
    X_norm = X_centered / stds

    # PCA via SVD
    U, S, Vt = np.linalg.svd(X_norm, full_matrices=False)
    eigenvalues = S ** 2 / (n_samples - 1)
    total_var = eigenvalues.sum()

    if total_var == 0:
        print("ERROR: Zero total variance — data may be constant")
        return {"error": "zero_variance"}

    var_explained = np.cumsum(eigenvalues) / total_var

    # Effective dimensions at thresholds
    d90 = int(np.searchsorted(var_explained, 0.90) + 1)
    d95 = int(np.searchsorted(var_explained, 0.95) + 1)
    d99 = int(np.searchsorted(var_explained, 0.99) + 1)

    # Participation ratio: PR = (Σλ)² / Σ(λ²)
    pr = (eigenvalues.sum() ** 2) / (eigenvalues ** 2).sum()

    print(f"\n--- PCA Results ---")
    print(f"Total features (N_features):     {n_features}")
    print(f"Non-zero components:             {len(eigenvalues[eigenvalues > 1e-10])}")
    n_nonzero = len(eigenvalues[eigenvalues > 1e-10])
    if n_nonzero <= n_samples:
        print(f"  ⚠ RANK-LIMITED: max rank = min(N_samples, N_features)-1 = {n_samples - 1}")
        print(f"    d_eff is bounded by sample count, not by intrinsic structure.")
        print(f"    Need more repeated measurements to distinguish d_eff from rank ceiling.")
    print(f"Variance explained by PC1:       {eigenvalues[0]/total_var:.1%}")
    print(f"Variance explained by PC1-2:     {var_explained[1]:.1%}" if len(var_explained) > 1 else "")
    print(f"d_eff (90% variance):            {d90}")
    print(f"d_eff (95% variance):            {d95}")
    print(f"d_eff (99% variance):            {d99}")
    print(f"Participation ratio (PR):        {pr:.2f}")
    print(f"PR / N_samples:                  {pr/n_samples:.2f}")

    # Print eigenvalue spectrum
    print(f"\n--- Eigenvalue Spectrum (top 10) ---")
    for i in range(min(10, len(eigenvalues))):
        bar = "█" * int(50 * eigenvalues[i] / eigenvalues[0])
        print(f"  PC{i+1:2d}: {eigenvalues[i]/total_var:6.1%} (cum: {var_explained[i]:6.1%}) {bar}")

    # --- Subspace projection stability ---
    print(f"\n--- Subspace Projection Stability ---")
    n_trials = 100
    n_keep = n_features // 2  # 50% of features

    # Build pairwise distance matrix in full space
    from scipy.spatial.distance import pdist, squareform
    full_dists = pdist(X_norm, metric="euclidean")
    full_nn = np.array([np.argsort(squareform(full_dists)[i])[1] for i in range(n_samples)])

    # Nearest-neighbor identity preservation under random subspace
    nn_preserved = []
    for trial in range(n_trials):
        rng = np.random.default_rng(trial)
        cols = rng.choice(n_features, size=n_keep, replace=False)
        X_sub = X_norm[:, cols]
        sub_dists = pdist(X_sub, metric="euclidean")
        sub_nn = np.array([np.argsort(squareform(sub_dists)[i])[1] for i in range(n_samples)])
        nn_preserved.append(np.mean(full_nn == sub_nn))

    nn_stability = np.mean(nn_preserved)
    nn_std = np.std(nn_preserved)

    print(f"Random 50% feature retention, {n_trials} trials:")
    print(f"  NN identity preservation:      {nn_stability:.1%} ± {nn_std:.1%}")

    # Also test at 30%, 20%, 10%
    for frac in [0.3, 0.2, 0.1]:
        n_k = max(1, int(n_features * frac))
        preserved = []
        for trial in range(n_trials):
            rng = np.random.default_rng(trial + 1000)
            cols = rng.choice(n_features, size=n_k, replace=False)
            X_sub = X_norm[:, cols]
            sub_dists = pdist(X_sub, metric="euclidean")
            sub_nn = np.array([np.argsort(squareform(sub_dists)[i])[1] for i in range(n_samples)])
            preserved.append(np.mean(full_nn == sub_nn))
        print(f"  {frac:.0%} retention ({n_k} feats): NN preserved = {np.mean(preserved):.1%} ± {np.std(preserved):.1%}")

    # --- Nonlinear check: Isomap vs PCA neighborhood preservation ---
    print(f"\n--- Nonlinear Structure Check ---")
    if n_samples < 6:
        print(f"  Skipping — need ≥6 samples for meaningful Isomap (have {n_samples})")
    else:
        try:
            from sklearn.manifold import Isomap
            k_neighbors = min(3, n_samples - 2)

            # PCA embedding at d_eff dimensions
            d_embed = min(d95, n_samples - 2, 3)
            if d_embed < 1:
                d_embed = 1
            X_pca = U[:, :d_embed] * S[:d_embed]

            # Isomap embedding at same dimension
            try:
                iso = Isomap(n_neighbors=k_neighbors, n_components=d_embed)
                X_iso = iso.fit_transform(X_norm)

                # Neighborhood preservation: k NN overlap
                def nn_overlap(X_full, X_embed, k=3):
                    from scipy.spatial.distance import cdist
                    D_full = cdist(X_full, X_full)
                    D_embed = cdist(X_embed, X_embed)
                    overlaps = []
                    for i in range(len(X_full)):
                        nn_full = set(np.argsort(D_full[i])[1:k+1])
                        nn_embed = set(np.argsort(D_embed[i])[1:k+1])
                        overlaps.append(len(nn_full & nn_embed) / k)
                    return np.mean(overlaps)

                pca_nn = nn_overlap(X_norm, X_pca, k=k_neighbors)
                iso_nn = nn_overlap(X_norm, X_iso, k=k_neighbors)

                print(f"  Embedding dimension: {d_embed}")
                print(f"  PCA k={k_neighbors} NN preservation:    {pca_nn:.1%}")
                print(f"  Isomap k={k_neighbors} NN preservation: {iso_nn:.1%}")
                if iso_nn > pca_nn + 0.05:
                    print(f"  → Isomap significantly better: suggests CURVED manifold")
                elif abs(iso_nn - pca_nn) <= 0.05:
                    print(f"  → PCA ≈ Isomap: manifold is approximately FLAT")
                else:
                    print(f"  → PCA better (Isomap may be overfitting with few samples)")
            except (ValueError, np.linalg.LinAlgError) as e:
                print(f"  Isomap failed ({e.__class__.__name__}): too few samples for geodesic embedding")
        except ImportError:
            print("  sklearn not available — skipping Isomap comparison")

    # Interpretation
    print(f"\n--- RH-02 Interpretation ---")
    ratio = d95 / n_features if n_features > 0 else 1.0
    print(f"d_eff(95%) / N_features = {d95} / {n_features} = {ratio:.3f}")

    if ratio < 0.3:
        print(f"→ STRONG SUPPORT: d_eff ≪ N_features. Modes are redundant projections")
        print(f"  of a lower-dimensional manifold.")
    elif ratio < 0.8:
        print(f"→ MODERATE: Some dimensionality reduction possible, but not dramatic.")
    else:
        print(f"→ WEAK/REFUTE: d_eff ≈ N_features. System is simply high-dimensional.")

    if nn_stability > 0.9:
        print(f"NN stability {nn_stability:.0%} > 90%: STRONG holographic-like redundancy.")
    elif nn_stability > 0.5:
        print(f"NN stability {nn_stability:.0%}: MODERATE redundancy.")
    else:
        print(f"NN stability {nn_stability:.0%} < 50%: WEAK — identity distributed uniformly.")

    return {
        "n_samples": n_samples,
        "n_features": n_features,
        "d90": d90,
        "d95": d95,
        "d99": d99,
        "participation_ratio": float(pr),
        "eigenvalues": eigenvalues.tolist(),
        "var_explained_cumulative": var_explained.tolist(),
        "nn_stability_50pct": float(nn_stability),
        "nn_stability_50pct_std": float(nn_std),
    }


# ---------------------------------------------------------------------------
# RH-05: Redundancy vs. Invariance Discrimination
# ---------------------------------------------------------------------------

def rh05_redundancy_vs_invariance(mag_matrix, phase_matrix, labels, census):
    """
    Test 1: Shuffle mode labels → re-run NN identity. If accuracy holds, redundancy.
    Test 2: Contiguous band removal vs random dropout.
    Test 3: Synthetic manifold probe.
    """
    print("\n" + "=" * 70)
    print("RH-05: REDUNDANCY VS. INVARIANCE DISCRIMINATION")
    print("=" * 70)

    X = np.hstack([mag_matrix, phase_matrix])
    n_samples, n_features = X.shape
    n_mag = mag_matrix.shape[1]

    X_centered = X - X.mean(axis=0)
    stds = X_centered.std(axis=0)
    stds[stds == 0] = 1.0
    X_norm = X_centered / stds

    from scipy.spatial.distance import pdist, squareform

    # Ground truth: NN in full space
    D_full = squareform(pdist(X_norm))
    np.fill_diagonal(D_full, np.inf)
    gt_nn = np.argmin(D_full, axis=1)
    plate_labels = [plate_name_from_key(census, l) for l in labels]

    print(f"\nData: {n_samples} samples × {n_features} features")
    print(f"Plate labels: {plate_labels}")
    print(f"Ground truth NN pairs:")
    for i in range(n_samples):
        print(f"  {labels[i]} ({plate_labels[i]}) → NN: {labels[gt_nn[i]]} ({plate_labels[gt_nn[i]]})")

    # --- Test 1: Shuffle mode labels ---
    print(f"\n--- Test 1: Shuffled Mode Labels ---")
    n_trials = 200
    shuffle_preserved = []
    for trial in range(n_trials):
        rng = np.random.default_rng(trial)
        # Shuffle columns independently for mag and phase halves
        perm_mag = rng.permutation(n_mag)
        perm_phase = rng.permutation(n_features - n_mag)
        X_shuf = np.hstack([X_norm[:, :n_mag][:, perm_mag],
                            X_norm[:, n_mag:][:, perm_phase]])
        D_shuf = squareform(pdist(X_shuf))
        np.fill_diagonal(D_shuf, np.inf)
        shuf_nn = np.argmin(D_shuf, axis=1)
        shuffle_preserved.append(np.mean(gt_nn == shuf_nn))

    shuf_mean = np.mean(shuffle_preserved)
    shuf_std = np.std(shuffle_preserved)
    print(f"  {n_trials} shuffle trials:")
    print(f"  NN identity preserved: {shuf_mean:.1%} ± {shuf_std:.1%}")

    # Also check: does shuffling preserve plate-level identity?
    # (same plate_name should be NN even if relay differs)
    shuffle_plate_preserved = []
    for trial in range(n_trials):
        rng = np.random.default_rng(trial)
        perm_mag = rng.permutation(n_mag)
        perm_phase = rng.permutation(n_features - n_mag)
        X_shuf = np.hstack([X_norm[:, :n_mag][:, perm_mag],
                            X_norm[:, n_mag:][:, perm_phase]])
        D_shuf = squareform(pdist(X_shuf))
        np.fill_diagonal(D_shuf, np.inf)
        shuf_nn = np.argmin(D_shuf, axis=1)
        # Check if NN is same plate
        matches = 0
        for i in range(n_samples):
            if plate_labels[shuf_nn[i]] == plate_labels[i]:
                matches += 1
        shuffle_plate_preserved.append(matches / n_samples)

    shuf_plate_mean = np.mean(shuffle_plate_preserved)
    print(f"  Same-plate NN after shuffle: {shuf_plate_mean:.1%}")

    if shuf_mean > 0.8:
        print(f"  → SUPPORTS REDUNDANCY: Shuffled modes still identify. Identity in aggregate stats.")
    elif shuf_mean < 0.5:
        print(f"  → SUPPORTS GEOMETRY: Shuffling destroys NN identity. Frequency-space structure matters.")
    else:
        print(f"  → AMBIGUOUS: Partial degradation from shuffling.")

    # --- Test 2: Contiguous vs. random band dropout ---
    print(f"\n--- Test 2: Contiguous vs. Random Dropout ---")
    dropout_fracs = [0.2, 0.4, 0.6]

    for frac in dropout_fracs:
        n_drop = int(n_mag * frac)  # Drop from magnitude half

        # Random dropout
        random_preserved = []
        for trial in range(100):
            rng = np.random.default_rng(trial)
            keep = np.ones(n_features, dtype=bool)
            drop_idx = rng.choice(n_mag, size=n_drop, replace=False)
            keep[drop_idx] = False
            # Also drop corresponding phase bins
            keep[drop_idx + n_mag] = False
            X_drop = X_norm[:, keep]
            D_drop = squareform(pdist(X_drop))
            np.fill_diagonal(D_drop, np.inf)
            drop_nn = np.argmin(D_drop, axis=1)
            random_preserved.append(np.mean(gt_nn == drop_nn))
        rand_mean = np.mean(random_preserved)

        # Contiguous dropout: remove a contiguous band of freq bins
        contig_preserved = []
        for trial in range(100):
            rng = np.random.default_rng(trial + 5000)
            start = rng.integers(0, n_mag - n_drop + 1)
            keep = np.ones(n_features, dtype=bool)
            keep[start:start + n_drop] = False
            keep[start + n_mag:start + n_mag + n_drop] = False
            X_drop = X_norm[:, keep]
            D_drop = squareform(pdist(X_drop))
            np.fill_diagonal(D_drop, np.inf)
            drop_nn = np.argmin(D_drop, axis=1)
            contig_preserved.append(np.mean(gt_nn == drop_nn))
        contig_mean = np.mean(contig_preserved)

        diff = rand_mean - contig_mean
        marker = ""
        if contig_mean < rand_mean - 0.05:
            marker = " ← contiguous hurts more (GEOMETRY)"
        elif abs(diff) <= 0.05:
            marker = " ← similar (REDUNDANCY)"
        print(f"  {frac:.0%} dropout: random NN={rand_mean:.1%}, contiguous NN={contig_mean:.1%}, Δ={diff:+.1%}{marker}")

    # --- Test 3: Synthetic manifold probe ---
    print(f"\n--- Test 3: Synthetic Manifold Probe ---")
    # PCA to find the subspace
    U, S, Vt = np.linalg.svd(X_norm, full_matrices=False)
    eigenvalues = S ** 2 / (n_samples - 1)
    total_var = eigenvalues.sum()
    var_explained = np.cumsum(eigenvalues) / total_var
    d_sub = int(np.searchsorted(var_explained, 0.95) + 1)
    d_sub = min(d_sub, n_samples - 1)

    # Project real data into PCA subspace
    X_pca = X_norm @ Vt[:d_sub].T  # (n_samples, d_sub)

    # Generate synthetic points in same subspace
    rng = np.random.default_rng(42)
    n_synth = 20
    # Sample within the convex hull (random convex combinations)
    synth_pca = []
    for _ in range(n_synth):
        weights = rng.dirichlet(np.ones(n_samples))
        synth_pca.append(weights @ X_pca)
    synth_pca = np.array(synth_pca)

    # Also generate random points outside the subspace
    synth_random = rng.standard_normal((n_synth, d_sub)) * np.std(X_pca, axis=0)

    # Test: are synthetic in-manifold points discriminable from each other?
    D_synth = squareform(pdist(synth_pca))
    D_real = squareform(pdist(X_pca))
    D_random = squareform(pdist(synth_random))

    real_spread = np.mean(D_real[np.triu_indices(n_samples, k=1)])
    synth_spread = np.mean(D_synth[np.triu_indices(n_synth, k=1)])
    random_spread = np.mean(D_random[np.triu_indices(n_synth, k=1)])

    print(f"  PCA subspace dimension: {d_sub}")
    print(f"  Real inter-plate distance (mean): {real_spread:.3f}")
    print(f"  Synthetic in-manifold distance:    {synth_spread:.3f}")
    print(f"  Random subspace distance:          {random_spread:.3f}")
    print(f"  Synth/Real ratio:                  {synth_spread/real_spread:.2f}")

    return {
        "shuffle_nn_preserved": float(shuf_mean),
        "shuffle_nn_std": float(shuf_std),
        "shuffle_plate_preserved": float(shuf_plate_mean),
        "dropout_results": {},  # filled below if needed
    }


# ---------------------------------------------------------------------------
# RH-01: Cross-Measure Transfer
# ---------------------------------------------------------------------------

def rh01_cross_measure_transfer(mag_matrix, phase_matrix, labels, census):
    """
    Enroll on magnitude-only, test on phase-only, and vice versa.
    Enroll on NE positions, test on NW positions.
    """
    print("\n" + "=" * 70)
    print("RH-01: CROSS-MEASURE TRANSFER")
    print("=" * 70)

    from scipy.spatial.distance import cdist

    plate_labels = [plate_name_from_key(census, l) for l in labels]

    # Normalize each modality separately
    def normalize(X):
        X_c = X - X.mean(axis=0)
        s = X_c.std(axis=0)
        s[s == 0] = 1.0
        return X_c / s

    mag_norm = normalize(mag_matrix)
    phase_norm = normalize(phase_matrix)

    # --- Test 1: Mag-only vs Phase-only ---
    print(f"\n--- Test 1: Magnitude ↔ Phase Transfer ---")

    # NN in mag-only space
    D_mag = cdist(mag_norm, mag_norm)
    np.fill_diagonal(D_mag, np.inf)
    nn_mag = np.argmin(D_mag, axis=1)

    # NN in phase-only space
    D_phase = cdist(phase_norm, phase_norm)
    np.fill_diagonal(D_phase, np.inf)
    nn_phase = np.argmin(D_phase, axis=1)

    # NN in combined space
    X_both = np.hstack([mag_norm, phase_norm])
    D_both = cdist(X_both, X_both)
    np.fill_diagonal(D_both, np.inf)
    nn_both = np.argmin(D_both, axis=1)

    # Cross-channel: enroll in mag space, query in phase space
    # For each sample, find its NN in phase space; check if it matches mag-space NN
    mag_to_phase = np.mean(nn_mag == nn_phase)

    # Same-plate matching
    mag_plate_acc = np.mean([plate_labels[nn_mag[i]] == plate_labels[i] for i in range(len(labels))])
    phase_plate_acc = np.mean([plate_labels[nn_phase[i]] == plate_labels[i] for i in range(len(labels))])
    cross_plate_acc = np.mean([plate_labels[nn_phase[i]] == plate_labels[nn_mag[i]] for i in range(len(labels))])

    print(f"  Mag-only NN → same plate:   {mag_plate_acc:.1%}")
    print(f"  Phase-only NN → same plate: {phase_plate_acc:.1%}")
    print(f"  Mag NN == Phase NN:         {mag_to_phase:.1%}")
    print(f"  Cross-channel plate match:  {cross_plate_acc:.1%}")

    # --- Test 2: NE ↔ NW Position Transfer ---
    print(f"\n--- Test 2: NE ↔ NW Position Transfer ---")

    # Find plates that have both NE and NW
    ne_keys = [k for k in labels if "NE" in k or not ("_" in k)]
    nw_keys = [k for k in labels if "NW" in k]

    # Match plates with both positions
    paired = []
    for ne in ne_keys:
        plate = plate_name_from_key(census, ne)
        for nw in nw_keys:
            if plate_name_from_key(census, nw) == plate:
                ne_idx = labels.index(ne)
                nw_idx = labels.index(nw)
                paired.append((plate, ne_idx, nw_idx))

    if not paired:
        print("  No NE/NW paired plates found.")
    else:
        print(f"  Paired plates: {[p[0] for p in paired]}")
        X_combined = np.hstack([mag_norm, phase_norm])

        for plate, ne_idx, nw_idx in paired:
            dist_ne_nw = np.linalg.norm(X_combined[ne_idx] - X_combined[nw_idx])
            # Find distance to all other plates' same-position
            other_dists = []
            for plate2, ne2, nw2 in paired:
                if plate2 != plate:
                    other_dists.append(np.linalg.norm(X_combined[ne_idx] - X_combined[ne2]))
                    other_dists.append(np.linalg.norm(X_combined[ne_idx] - X_combined[nw2]))
            if other_dists:
                nearest_other = min(other_dists)
                mean_other = np.mean(other_dists)
                margin = (nearest_other - dist_ne_nw) / nearest_other if nearest_other > 0 else 0
                print(f"  {plate}: NE↔NW dist={dist_ne_nw:.2f}, nearest_other={nearest_other:.2f}, margin={margin:.1%}")

        # Cross-position NN test: for each NE, is the NW of same plate the NN?
        if len(paired) > 1:
            all_paired_idx = []
            all_paired_plates = []
            for plate, ne_idx, nw_idx in paired:
                all_paired_idx.extend([ne_idx, nw_idx])
                all_paired_plates.extend([plate, plate])

            X_paired = X_combined[all_paired_idx]
            D_paired = cdist(X_paired, X_paired)
            np.fill_diagonal(D_paired, np.inf)
            nn_paired = np.argmin(D_paired, axis=1)

            # Check if NN is same plate
            correct = 0
            for i in range(len(all_paired_idx)):
                if all_paired_plates[nn_paired[i]] == all_paired_plates[i]:
                    correct += 1
            cross_pos_acc = correct / len(all_paired_idx)
            print(f"\n  Cross-position NN → same plate: {cross_pos_acc:.1%}")
        else:
            cross_pos_acc = float('nan')

    # --- Interpretation ---
    print(f"\n--- RH-01 Interpretation ---")
    if mag_plate_acc > 0.8 and phase_plate_acc > 0.8:
        print(f"→ Both channels independently discriminate: identity is NOT channel-bound.")
    elif mag_plate_acc > 0.8 or phase_plate_acc > 0.8:
        print(f"→ One channel dominates. Identity partially channel-bound.")
    else:
        print(f"→ Neither channel alone discriminates well. Combination required.")

    if cross_plate_acc > 0.8:
        print(f"→ STRONG: Mag and Phase agree on identity — shared latent geometry likely.")
    elif cross_plate_acc > 0.4:
        print(f"→ MODERATE: Some cross-channel agreement.")
    else:
        print(f"→ WEAK: Channels see different structure.")

    return {
        "mag_plate_accuracy": float(mag_plate_acc),
        "phase_plate_accuracy": float(phase_plate_acc),
        "mag_phase_nn_agreement": float(mag_to_phase),
        "cross_channel_plate_match": float(cross_plate_acc),
    }


# ---------------------------------------------------------------------------
# RH-03: Cross-Object Generalization Geometry
# ---------------------------------------------------------------------------

def rh03_cross_object_generalization(mag_matrix, phase_matrix, labels, census):
    """
    Leave-one-out: learn PCA basis from N-1 plates, project held-out plate.
    Measure reconstruction error and distance-rank preservation.
    """
    print("\n" + "=" * 70)
    print("RH-03: CROSS-OBJECT GENERALIZATION GEOMETRY")
    print("=" * 70)

    from scipy.spatial.distance import pdist, squareform
    from scipy.stats import spearmanr

    X = np.hstack([mag_matrix, phase_matrix])
    n_samples, n_features = X.shape
    plate_labels = [plate_name_from_key(census, l) for l in labels]

    X_centered = X - X.mean(axis=0)
    stds = X_centered.std(axis=0)
    stds[stds == 0] = 1.0
    X_norm = X_centered / stds

    # Full-space pairwise distances
    D_full = squareform(pdist(X_norm))

    print(f"\nData: {n_samples} samples × {n_features} features")
    print(f"Plates: {plate_labels}")

    # Determine PCA dimension from full dataset
    U, S, Vt = np.linalg.svd(X_norm, full_matrices=False)
    eigenvalues = S ** 2 / max(1, n_samples - 1)
    total_var = eigenvalues.sum()
    var_explained = np.cumsum(eigenvalues) / total_var if total_var > 0 else np.ones_like(eigenvalues)
    d_pca = min(int(np.searchsorted(var_explained, 0.95) + 1), n_samples - 2)
    d_pca = max(d_pca, 1)

    print(f"PCA dimension (95% var): {d_pca}")

    # Leave-one-out
    print(f"\n--- Leave-One-Out Reconstruction ---")
    reconstruction_ratios = []

    for hold_idx in range(n_samples):
        # Train set: all except held out
        train_idx = [i for i in range(n_samples) if i != hold_idx]
        X_train = X_norm[train_idx]
        X_held = X_norm[hold_idx:hold_idx+1]

        # PCA on train set
        train_mean = X_train.mean(axis=0)
        X_train_c = X_train - train_mean
        X_held_c = X_held - train_mean

        Ut, St, Vtt = np.linalg.svd(X_train_c, full_matrices=False)
        d = min(d_pca, len(St))
        basis = Vtt[:d]  # (d, n_features)

        # Reconstruct held-out
        proj = X_held_c @ basis.T  # (1, d)
        recon = proj @ basis  # (1, n_features)
        held_error = np.linalg.norm(X_held_c - recon)

        # Average reconstruction error of training points
        train_projs = X_train_c @ basis.T
        train_recons = train_projs @ basis
        train_errors = np.linalg.norm(X_train_c - train_recons, axis=1)
        avg_train_error = np.mean(train_errors)

        ratio = held_error / avg_train_error if avg_train_error > 0 else float('inf')
        reconstruction_ratios.append(ratio)

        print(f"  Hold out {labels[hold_idx]} ({plate_labels[hold_idx]}): "
              f"error={held_error:.3f}, train_avg={avg_train_error:.3f}, ratio={ratio:.2f}×")

    mean_ratio = np.mean(reconstruction_ratios)
    print(f"\n  Mean reconstruction ratio: {mean_ratio:.2f}×")

    # --- Distance rank preservation ---
    print(f"\n--- Distance Rank Preservation ---")

    # Full PCA on all data
    d_full = min(d_pca, n_samples - 1)
    X_pca = X_norm @ Vt[:d_full].T

    D_pca = squareform(pdist(X_pca))

    # Extract upper triangle (pairwise distances)
    triu_idx = np.triu_indices(n_samples, k=1)
    d_full_vec = D_full[triu_idx]
    d_pca_vec = D_pca[triu_idx]

    if len(d_full_vec) > 2:
        rho, p_val = spearmanr(d_full_vec, d_pca_vec)
    else:
        rho, p_val = float('nan'), float('nan')

    print(f"  Spearman ρ (full vs PCA distances): {rho:.4f}  (p={p_val:.4e})")

    # Print distance matrix for inspection
    print(f"\n--- Pairwise Distance Matrix (PCA space) ---")
    header = "         " + "  ".join(f"{l:>8s}" for l in labels)
    print(header)
    for i in range(n_samples):
        row = f"{labels[i]:>8s} "
        for j in range(n_samples):
            if i == j:
                row += "    ---  "
            else:
                row += f"  {D_pca[i,j]:7.2f}"
        print(row)

    # --- Interpretation ---
    print(f"\n--- RH-03 Interpretation ---")
    if mean_ratio < 2.0:
        print(f"→ STRONG: Held-out objects reconstruct well ({mean_ratio:.1f}×). Shared representational subspace.")
    elif mean_ratio < 5.0:
        print(f"→ MODERATE: Reconstruction ratio {mean_ratio:.1f}× — subspace partly generalizes.")
    else:
        print(f"→ WEAK/REFUTE: Reconstruction ratio {mean_ratio:.1f}× — each object is idiosyncratic.")

    if rho > 0.9:
        print(f"→ STRONG MANIFOLD: Rank correlation {rho:.3f} — true manifold geometry preserved.")
    elif rho > 0.5:
        print(f"→ MODERATE: Some geometric preservation (ρ={rho:.3f}).")
    else:
        print(f"→ WEAK: Poor rank preservation (ρ={rho:.3f}).")

    return {
        "reconstruction_ratios": [float(r) for r in reconstruction_ratios],
        "mean_reconstruction_ratio": float(mean_ratio),
        "spearman_rho": float(rho),
        "spearman_p": float(p_val),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="RH Gate A Experiments")
    parser.add_argument("--census", required=True, help="Census JSON file")
    parser.add_argument("--sweeps", default=None, help="Sweeps JSON file (optional, for full spectral data)")
    parser.add_argument("--out", default=None, help="Output JSON file for results")
    args = parser.parse_args()

    print("=" * 70)
    print("REPRESENTATION HYPOTHESIS — GATE A EXPERIMENTS")
    print(f"Census: {args.census}")
    print(f"Sweeps: {args.sweeps or '(not provided — using peak vectors)'}")
    print(f"Time:   {datetime.now().isoformat()}")
    print("=" * 70)

    # Load data
    census = load_census(args.census)
    print(f"\nLoaded {len(census)} relay paths from census")
    for k in sorted(census.keys()):
        n = len(census[k].get("peaks", []))
        name = plate_name_from_key(census, k)
        print(f"  {k}: plate {name}, {n} peaks")

    # Build feature matrices
    if args.sweeps:
        print("\nUsing full sweep spectral data...")
        sweeps = load_sweeps(args.sweeps)
        freq_axis, mag_matrix, phase_matrix, labels = build_spectral_vectors(sweeps)
        print(f"Spectral vectors: {mag_matrix.shape[0]} plates × {mag_matrix.shape[1]} freq bins")
    else:
        print("\nUsing binned peak vectors from census...")
        freq_axis, mag_matrix, phase_matrix, labels = build_peak_vectors(census)
        print(f"Peak vectors: {mag_matrix.shape[0]} plates × {mag_matrix.shape[1]} bins")

    # Run experiments
    results = {}

    results["rh02"] = rh02_intrinsic_dimensionality(mag_matrix, phase_matrix, labels, census)
    results["rh05"] = rh05_redundancy_vs_invariance(mag_matrix, phase_matrix, labels, census)
    results["rh01"] = rh01_cross_measure_transfer(mag_matrix, phase_matrix, labels, census)
    results["rh03"] = rh03_cross_object_generalization(mag_matrix, phase_matrix, labels, census)

    # --- GATE A DECISION ---
    print("\n" + "=" * 70)
    print("GATE A DECISION")
    print("=" * 70)

    rh02 = results["rh02"]
    rh05 = results["rh05"]

    if "error" in rh02:
        print("\nRH-02 failed — cannot evaluate Gate A.")
    else:
        d_eff = rh02["d95"]
        n_feat = rh02["n_features"]
        ratio = d_eff / n_feat if n_feat > 0 else 1.0
        nn_stab = rh02["nn_stability_50pct"]
        shuf_nn = rh05["shuffle_nn_preserved"]

        print(f"\n  d_eff(95%) / N_features = {d_eff}/{n_feat} = {ratio:.3f}")
        print(f"  NN stability at 50% features = {nn_stab:.1%}")
        print(f"  Shuffled-mode NN preservation = {shuf_nn:.1%}")

        if ratio < 0.3 and shuf_nn < 0.7:
            print(f"\n  ✅ GATE A: PROCEED — manifold exists and carries geometric structure.")
            print(f"     d_eff ≪ N_features AND shuffling degrades identity.")
        elif ratio > 0.8 and shuf_nn > 0.8:
            print(f"\n  ❌ GATE A: ABANDON — system is a conventional high-dimensional fingerprint.")
        else:
            print(f"\n  ⚠️  GATE A: MIXED — proceed with RH-01 and RH-03 for additional discrimination.")

    # Save results
    if args.out:
        out_path = args.out
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(args.census).parent
        out_path = out_dir / f"rh_gate_a_{ts}.json"

    output = {
        "experiment": "rh_gate_a",
        "timestamp": datetime.now().isoformat(),
        "census_file": str(args.census),
        "sweeps_file": str(args.sweeps) if args.sweeps else None,
        "results": results,
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
