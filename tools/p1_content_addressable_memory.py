#!/usr/bin/env python3
"""
P1: Content-Addressable Memory — Mode-as-Address Lookup Table

Demonstrates the plate as a physical content-addressable memory:
- Each enrolled eigenmode frequency IS an address
- The 4-channel spatial amplitude response IS the stored content
- READ: drive frequency → measure 4-ch response → decode to symbol
- ASSOCIATIVE QUERY: drive partial/noisy → find nearest match

The plate's 100% discrimination at enrolled frequencies (T3.1, T3.4)
means this is expected to work perfectly. The goal is to demonstrate
the CAM framing and measure:
  1. Capacity (how many distinct symbols can be stored)
  2. Retrieval accuracy (exact match and nearest-neighbor)
  3. Noise robustness (how much noise before retrieval fails)
  4. Associative recall (partial query → correct symbol)

Uses the multi-plate enrollment data (no hardware needed).
"""

import argparse
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from scipy.spatial.distance import cosine, euclidean


def load_enrollment():
    """Load multi-plate enrollment data."""
    h_path = Path('data/results/h_matrix/multi_plate_enrollment_20260603_171950.json')
    with open(h_path) as f:
        data = json.load(f)

    H = np.array(data['h_matrix_normalized'])  # 27×4
    freqs = data['mode_frequencies_hz']  # 27 frequencies

    return H, freqs, data


def build_memory_table(H, freqs):
    """
    Build the content-addressable memory table.

    Each row of H is a "memory entry":
      - Address: the frequency (mode index)
      - Content: the 4D spatial signature (amplitudes on 4 receivers)
    """
    n_entries = H.shape[0]
    table = []
    for i in range(n_entries):
        table.append({
            'address': i,
            'frequency_hz': freqs[i],
            'content': H[i],  # 4D vector
            'content_norm': H[i] / np.linalg.norm(H[i]),
        })
    return table


def exact_retrieval(table, query_vector, metric='cosine'):
    """
    Retrieve the closest memory entry to the query vector.
    Returns: (best_index, distance, all_distances)
    """
    distances = []
    for entry in table:
        if metric == 'cosine':
            d = cosine(query_vector, entry['content'])
        elif metric == 'euclidean':
            d = euclidean(query_vector, entry['content_norm'])
        elif metric == 'dot':
            d = -np.dot(query_vector / np.linalg.norm(query_vector),
                        entry['content_norm'])
        else:
            raise ValueError(f"Unknown metric: {metric}")
        distances.append(d)

    best_idx = np.argmin(distances)
    return best_idx, distances[best_idx], distances


def test_exact_retrieval(table, H):
    """Test: query with exact stored pattern → should return correct address."""
    n = len(table)
    correct = 0
    margins = []

    for i in range(n):
        query = H[i]
        best_idx, best_dist, all_dists = exact_retrieval(table, query)
        if best_idx == i:
            correct += 1
            # Margin: distance to 2nd closest
            sorted_dists = sorted(all_dists)
            if len(sorted_dists) > 1:
                margins.append(sorted_dists[1] - sorted_dists[0])

    return correct / n, margins


def test_noisy_retrieval(table, H, noise_levels, n_trials=100, seed=42):
    """Test: query with noisy version of stored pattern."""
    rng = np.random.default_rng(seed)
    n = len(table)

    results = {}
    for sigma in noise_levels:
        correct = 0
        total = 0
        for trial in range(n_trials):
            idx = rng.integers(0, n)
            query = H[idx] + rng.normal(0, sigma, H.shape[1])
            query = np.clip(query, 0, None)  # Amplitudes are non-negative

            best_idx, _, _ = exact_retrieval(table, query)
            if best_idx == idx:
                correct += 1
            total += 1

        results[sigma] = correct / total

    return results


def test_partial_query(table, H, n_channels_missing, n_trials=100, seed=42):
    """Test: query with some channels zeroed out (partial information)."""
    rng = np.random.default_rng(seed)
    n = len(table)
    n_ch = H.shape[1]

    results = {}
    for n_missing in n_channels_missing:
        correct = 0
        total = 0
        for trial in range(n_trials):
            idx = rng.integers(0, n)
            query = H[idx].copy()

            # Zero out n_missing channels
            missing_chs = rng.choice(n_ch, size=n_missing, replace=False)
            query[missing_chs] = 0

            best_idx, _, _ = exact_retrieval(table, query, metric='euclidean')
            if best_idx == idx:
                correct += 1
            total += 1

        results[n_missing] = correct / total

    return results


def test_interpolation_query(table, H, n_trials=100, seed=42):
    """Test: query is a blend of two stored patterns. Does it find the dominant one?"""
    rng = np.random.default_rng(seed)
    n = len(table)

    results_by_alpha = {}
    for alpha in [0.9, 0.8, 0.7, 0.6, 0.55, 0.51]:
        correct = 0
        for trial in range(n_trials):
            idx1, idx2 = rng.choice(n, size=2, replace=False)
            query = alpha * H[idx1] + (1 - alpha) * H[idx2]

            best_idx, _, _ = exact_retrieval(table, query)
            if best_idx == idx1:
                correct += 1

        results_by_alpha[alpha] = correct / n_trials

    return results_by_alpha


def compute_separation_stats(H):
    """Compute pairwise angular separation between all stored patterns."""
    n = H.shape[0]
    norms = H / np.linalg.norm(H, axis=1, keepdims=True)

    angles = []
    for i in range(n):
        for j in range(i+1, n):
            cos_sim = np.dot(norms[i], norms[j])
            cos_sim = np.clip(cos_sim, -1, 1)
            angle_deg = np.degrees(np.arccos(cos_sim))
            angles.append(angle_deg)

    return {
        'min_angle_deg': float(np.min(angles)),
        'max_angle_deg': float(np.max(angles)),
        'mean_angle_deg': float(np.mean(angles)),
        'median_angle_deg': float(np.median(angles)),
        'std_angle_deg': float(np.std(angles)),
    }


def main():
    parser = argparse.ArgumentParser(description='P1: Content-Addressable Memory')
    parser.add_argument('--n-noise-trials', type=int, default=200,
                        help='Trials per noise level')
    args = parser.parse_args()

    print("=" * 70)
    print("  P1: Content-Addressable Memory (Mode-as-Address)")
    print("=" * 70)
    print()
    print("  Architecture: Physical plate as lookup table")
    print("  Address:  eigenmode frequency (drive at f_i)")
    print("  Content:  4-channel spatial amplitude vector (H[i,:])")
    print("  Read:     drive f_i → measure 4-ch response → decode")
    print("  Query:    drive unknown → find nearest stored pattern")
    print()

    # ─── Load enrollment data ─────────────────────────────────────
    H, freqs, raw_data = load_enrollment()
    n_entries, n_channels = H.shape

    print(f"  Memory size: {n_entries} entries × {n_channels} channels")
    print(f"  Frequency range: {freqs[0]/1000:.0f}–{freqs[-1]/1000:.0f} kHz")
    print(f"  Capacity: {n_entries} symbols (one per eigenmode)")
    print()

    # ─── Build memory table ───────────────────────────────────────
    table = build_memory_table(H, freqs)

    # ─── Separation statistics ────────────────────────────────────
    print("  [1] Pattern separation (angular diversity)...")
    sep_stats = compute_separation_stats(H)
    print(f"      Min angle:    {sep_stats['min_angle_deg']:.1f}°")
    print(f"      Max angle:    {sep_stats['max_angle_deg']:.1f}°")
    print(f"      Mean angle:   {sep_stats['mean_angle_deg']:.1f}°")
    print(f"      Median angle: {sep_stats['median_angle_deg']:.1f}°")
    print()

    # ─── Test 1: Exact retrieval ──────────────────────────────────
    print("  [2] Exact retrieval (query = stored pattern)...")
    acc_exact, margins = test_exact_retrieval(table, H)
    print(f"      Accuracy: {acc_exact*100:.1f}% ({int(acc_exact*n_entries)}/{n_entries})")
    if margins:
        print(f"      Mean margin (cosine gap to 2nd): {np.mean(margins):.4f}")
        print(f"      Min margin:  {np.min(margins):.4f}")
    print()

    # ─── Test 2: Noisy retrieval ──────────────────────────────────
    print(f"  [3] Noisy retrieval ({args.n_noise_trials} trials per σ)...")
    # Noise levels relative to mean amplitude
    mean_amp = H.mean()
    noise_fracs = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0]
    noise_sigmas = [f * mean_amp for f in noise_fracs]

    noisy_results = test_noisy_retrieval(table, H, noise_sigmas,
                                          n_trials=args.n_noise_trials)

    print(f"      {'σ/mean':>8s}  {'σ (abs)':>10s}  {'Accuracy':>10s}")
    for frac, sigma in zip(noise_fracs, noise_sigmas):
        acc = noisy_results[sigma]
        print(f"      {frac:8.2f}  {sigma:10.4f}  {acc*100:10.1f}%")

    # Find noise threshold (accuracy drops below 90%)
    threshold_frac = None
    for frac, sigma in zip(noise_fracs, noise_sigmas):
        if noisy_results[sigma] < 0.9:
            threshold_frac = frac
            break
    print(f"      Noise tolerance (>90% acc): σ/mean < {threshold_frac if threshold_frac else '>1.0'}")
    print()

    # ─── Test 3: Partial query ────────────────────────────────────
    print(f"  [4] Partial query (missing channels)...")
    partial_results = test_partial_query(table, H, [1, 2, 3],
                                          n_trials=args.n_noise_trials)
    for n_missing, acc in partial_results.items():
        print(f"      {n_missing}/{n_channels} channels missing: {acc*100:.1f}% accuracy")
    print()

    # ─── Test 4: Associative / interpolation ─────────────────────
    print(f"  [5] Associative recall (blended queries)...")
    interp_results = test_interpolation_query(table, H,
                                               n_trials=args.n_noise_trials)
    print(f"      Query = α×pattern_A + (1-α)×pattern_B → retrieve A?")
    for alpha, acc in sorted(interp_results.items(), reverse=True):
        marker = " ★" if acc >= 0.9 else ""
        print(f"      α={alpha:.2f}: {acc*100:.1f}%{marker}")
    print()

    # ─── Test 5: k-nearest neighbors ─────────────────────────────
    print(f"  [6] Nearest-neighbor structure (cluster analysis)...")
    # For each entry, find its closest neighbor
    norms = H / np.linalg.norm(H, axis=1, keepdims=True)
    sim_matrix = norms @ norms.T
    np.fill_diagonal(sim_matrix, -1)  # Exclude self

    closest_pairs = []
    for i in range(n_entries):
        j = np.argmax(sim_matrix[i])
        sim = sim_matrix[i, j]
        closest_pairs.append((i, j, freqs[i], freqs[j], sim))

    closest_pairs.sort(key=lambda x: -x[4])
    print(f"      Most similar pairs (potential confusion):")
    for i, j, fi, fj, sim in closest_pairs[:5]:
        angle = np.degrees(np.arccos(np.clip(sim, -1, 1)))
        print(f"        {fi/1000:.0f} kHz ↔ {fj/1000:.0f} kHz: cos={sim:.4f} ({angle:.1f}°)")
    print()

    # ─── Summary ──────────────────────────────────────────────────
    print("=" * 70)
    print("  P1 RESULTS: CONTENT-ADDRESSABLE MEMORY")
    print("=" * 70)
    print()
    print(f"  Capacity:           {n_entries} symbols (27 eigenmodes)")
    print(f"  Channels:           {n_channels} receivers")
    print(f"  Exact retrieval:    {acc_exact*100:.1f}%")
    print(f"  Noise tolerance:    σ/mean < {threshold_frac if threshold_frac else '>1.0'} for >90% accuracy")
    print(f"  Partial (1 ch missing): {partial_results[1]*100:.1f}%")
    print(f"  Partial (2 ch missing): {partial_results[2]*100:.1f}%")
    print(f"  Associative (α=0.7):    {interp_results[0.7]*100:.1f}%")
    print(f"  Min angular sep:    {sep_stats['min_angle_deg']:.1f}°")
    print()

    # Verdict
    if acc_exact >= 0.99 and (threshold_frac is None or threshold_frac >= 0.2):
        verdict = "PASS"
        print("  ★ PASS — Perfect retrieval with strong noise robustness")
    elif acc_exact >= 0.95:
        verdict = "PASS_MARGINAL"
        print("  △ PASS (marginal) — Near-perfect retrieval")
    else:
        verdict = "FAIL"
        print(f"  ✗ FAIL — Retrieval accuracy {acc_exact*100:.1f}% < 95%")

    print()

    # ─── Information-theoretic capacity ──────────────────────────
    print("  [7] Information capacity analysis...")
    # Bits stored = log2(n_entries) per lookup
    bits_per_lookup = np.log2(n_entries)
    # Bits per channel = log2(distinguishable levels)
    # From T3.4: 8 levels per mode → 3 bits per channel
    bits_analog = n_channels * 3  # Conservative: 3 bits per channel
    print(f"      Address bits (frequency selection): {bits_per_lookup:.1f} bits")
    print(f"      Content bits (per entry, 3-bit/ch): {bits_analog} bits")
    print(f"      Total addressable:  {n_entries} × {bits_analog} = {n_entries * bits_analog} bits")
    print(f"      Density: {n_entries * bits_analog / n_entries:.0f} bits per physical mode")
    print()

    # ─── Save ─────────────────────────────────────────────────────
    DATA_DIR = Path('data/results/cam')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = DATA_DIR / f'p1_content_addressable_memory_{ts}.json'

    output = {
        'experiment': 'P1_content_addressable_memory',
        'timestamp': datetime.now().isoformat(),
        'config': {
            'n_entries': int(n_entries),
            'n_channels': int(n_channels),
            'frequencies_hz': freqs,
            'h_matrix_source': 'multi_plate_enrollment_20260603_171950.json',
            'n_noise_trials': args.n_noise_trials,
        },
        'separation': sep_stats,
        'exact_retrieval_accuracy': float(acc_exact),
        'exact_retrieval_margins': [float(m) for m in margins],
        'noisy_retrieval': {str(f): float(noisy_results[s]) for f, s in zip(noise_fracs, noise_sigmas)},
        'partial_retrieval': {str(k): float(v) for k, v in partial_results.items()},
        'associative_retrieval': {str(k): float(v) for k, v in interp_results.items()},
        'noise_threshold_frac': float(threshold_frac) if threshold_frac else None,
        'information_capacity': {
            'n_symbols': int(n_entries),
            'bits_per_lookup': float(bits_per_lookup),
            'bits_per_entry': int(bits_analog),
        },
        'verdict': verdict,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {out_path}")
    print("  Done.")


if __name__ == '__main__':
    main()
