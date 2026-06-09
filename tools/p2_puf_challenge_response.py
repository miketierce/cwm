#!/usr/bin/env python3
"""
P2: Physical Unclonable Function — Challenge-Response Protocol

Demonstrates the plate as a PUF:
- Challenge: random subset of frequencies driven simultaneously
- Response: 4-channel amplitude pattern (unique to this plate)
- Security: response cannot be predicted without possessing the plate

Uses multi-plate enrollment to compare:
- Intra-plate consistency (same plate, same challenge → same response)
- Inter-plate distinctiveness (different plates, same challenge → different response)
- Impersonation resistance (how many CRPs needed to predict new responses)

From E3: temporal stability is proven (7/7 epochs, <1% drift over hours).
From E1: S=2.83 proves non-separable freq×space → responses carry more
information than simple frequency responses.
"""

import argparse
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from itertools import combinations


def load_enrollment():
    """Load multi-plate enrollment data."""
    h_path = Path('data/results/h_matrix/multi_plate_enrollment_20260603_171950.json')
    with open(h_path) as f:
        data = json.load(f)

    H = np.array(data['h_matrix_normalized'])  # 27×4
    freqs = data['mode_frequencies_hz']
    return H, freqs, data


def generate_challenge(n_freqs, n_modes, rng):
    """Generate a random challenge (subset of frequency indices)."""
    return sorted(rng.choice(n_modes, size=n_freqs, replace=False).tolist())


def compute_response(H, challenge):
    """
    Compute the plate's response to a frequency challenge.

    In the physical system: drive all challenge frequencies simultaneously,
    measure 4-channel amplitude response. Due to linearity (T2.2), the
    response is the SUM of individual mode responses.

    Response = sum of H[i,:] for i in challenge frequencies.
    Normalize to unit vector for comparison.
    """
    response = np.sum(H[challenge], axis=0)
    norm = np.linalg.norm(response)
    if norm > 0:
        response = response / norm
    return response


def hamming_distance_bits(r1, r2, n_bits=8):
    """Quantize responses to n_bits and compute Hamming distance."""
    # Quantize each channel to n_bits levels
    def quantize(r, n_bits):
        levels = 2**n_bits
        # Map [0, max_component] to [0, levels-1]
        q = np.floor(r * (levels - 1)).astype(int)
        return np.clip(q, 0, levels - 1)

    q1 = quantize(r1, n_bits)
    q2 = quantize(r2, n_bits)

    # Bit-level Hamming
    total_bits = 0
    diff_bits = 0
    for a, b in zip(q1, q2):
        xor = a ^ b
        diff_bits += bin(xor).count('1')
        total_bits += n_bits

    return diff_bits, total_bits


def main():
    parser = argparse.ArgumentParser(description='P2: PUF Challenge-Response')
    parser.add_argument('--n-challenges', type=int, default=1000,
                        help='Number of challenge-response pairs to generate')
    parser.add_argument('--challenge-size', type=int, default=3,
                        help='Number of frequencies per challenge')
    parser.add_argument('--n-attack-samples', type=int, default=50,
                        help='CRPs revealed to attacker for modeling attack')
    args = parser.parse_args()

    print("=" * 70)
    print("  P2: Physical Unclonable Function — Challenge-Response Protocol")
    print("=" * 70)
    print()
    print(f"  Challenge: {args.challenge_size} frequencies from 27 modes")
    print(f"  Response:  4-channel amplitude vector (normalized)")
    print(f"  CRP pairs: {args.n_challenges}")
    print()

    # ─── Load enrollment ──────────────────────────────────────────
    H, freqs, raw_data = load_enrollment()
    n_modes, n_ch = H.shape

    # Split into "Plate I" (channels 0,1) and "Plate H" (channels 2,3)
    # to simulate inter-plate comparison
    H_plate_I = H[:, :2]  # First 2 channels = Plate I NW, NE
    H_plate_H = H[:, 2:]  # Last 2 channels = Plate H NW, NE

    print(f"  Plate I: channels [NW, NE] (first 2)")
    print(f"  Plate H: channels [NW, NE] (last 2)")
    print(f"  Combined: 4 channels for full PUF response")
    print()

    # ─── Generate CRP database ───────────────────────────────────
    print(f"  [1] Generating {args.n_challenges} challenge-response pairs...")
    rng = np.random.default_rng(42)

    challenges = []
    responses_full = []  # 4-channel response
    responses_I = []     # Plate I only
    responses_H = []     # Plate H only

    for i in range(args.n_challenges):
        c = generate_challenge(args.challenge_size, n_modes, rng)
        challenges.append(c)
        responses_full.append(compute_response(H, c))
        responses_I.append(compute_response(H_plate_I, c))
        responses_H.append(compute_response(H_plate_H, c))

    responses_full = np.array(responses_full)
    responses_I = np.array(responses_I)
    responses_H = np.array(responses_H)

    from math import comb
    n_possible = comb(n_modes, args.challenge_size)
    print(f"      CRP space: C({n_modes},{args.challenge_size}) = {n_possible} possible challenges")
    print(f"      Generated: {args.n_challenges} ({100*args.n_challenges/n_possible:.1f}% of space)")
    print()

    # ─── Intra-plate consistency (reproducibility) ────────────────
    print("  [2] Intra-plate consistency (same plate, same challenge)...")
    # Simulate measurement noise (from E3: CV ≈ 0.2% over hours)
    noise_cv = 0.002  # 0.2% coefficient of variation

    n_repeats = 100
    intra_dists = []
    for i in range(min(100, args.n_challenges)):
        base_response = responses_full[i]
        for _ in range(n_repeats):
            noisy = base_response * (1 + rng.normal(0, noise_cv, n_ch))
            noisy = noisy / np.linalg.norm(noisy)
            dist = 1 - np.dot(base_response, noisy)
            intra_dists.append(dist)

    print(f"      Noise model: CV = {noise_cv*100:.1f}% (from E3 stability)")
    print(f"      Intra-plate cosine distance: {np.mean(intra_dists):.6f} ± {np.std(intra_dists):.6f}")
    print(f"      Max intra-plate distance:    {np.max(intra_dists):.6f}")
    print()

    # ─── Inter-plate distinctiveness ──────────────────────────────
    print("  [3] Inter-plate distinctiveness (Plate I vs Plate H, same challenge)...")
    inter_dists = []
    for i in range(args.n_challenges):
        dist = 1 - np.dot(responses_I[i], responses_H[i])
        inter_dists.append(dist)

    print(f"      Inter-plate cosine distance: {np.mean(inter_dists):.4f} ± {np.std(inter_dists):.4f}")
    print(f"      Min inter-plate distance:    {np.min(inter_dists):.4f}")
    print(f"      Max inter-plate distance:    {np.max(inter_dists):.4f}")
    print()

    # Separation ratio
    sep_ratio = np.min(inter_dists) / np.max(intra_dists) if np.max(intra_dists) > 0 else np.inf
    print(f"      Separation ratio (min inter / max intra): {sep_ratio:.0f}×")
    print(f"      → {'CLEAN SEPARATION' if sep_ratio > 10 else 'OVERLAP RISK'}")
    print()

    # ─── Response uniqueness (inter-challenge) ────────────────────
    print("  [4] Response uniqueness (different challenges → different responses)...")
    # Sample pairwise distances between different challenges
    n_sample = min(5000, args.n_challenges * (args.n_challenges - 1) // 2)
    unique_dists = []
    pairs = rng.choice(args.n_challenges, size=(n_sample, 2), replace=True)
    for i, j in pairs:
        if i != j:
            dist = 1 - np.dot(responses_full[i], responses_full[j])
            unique_dists.append(dist)

    print(f"      Mean inter-challenge distance: {np.mean(unique_dists):.4f} ± {np.std(unique_dists):.4f}")
    print(f"      Min distance (closest pair):   {np.min(unique_dists):.4f}")

    # Collision probability
    threshold = np.max(intra_dists) * 5  # 5× the noise floor
    n_collisions = sum(1 for d in unique_dists if d < threshold)
    collision_rate = n_collisions / len(unique_dists)
    print(f"      Collision rate (dist < {threshold:.5f}): {collision_rate*100:.3f}%")
    print()

    # ─── Hamming distance analysis ────────────────────────────────
    print("  [5] Bit-level analysis (8-bit quantization)...")

    # Intra-plate Hamming (should be ~0)
    intra_hd = []
    for i in range(min(200, args.n_challenges)):
        base = responses_full[i]
        noisy = base * (1 + rng.normal(0, noise_cv, n_ch))
        noisy = noisy / np.linalg.norm(noisy)
        diff, total = hamming_distance_bits(base, noisy, n_bits=8)
        intra_hd.append(diff / total)

    # Inter-plate Hamming (should be ~50%)
    inter_hd = []
    for i in range(min(500, args.n_challenges)):
        diff, total = hamming_distance_bits(responses_I[i], responses_H[i], n_bits=8)
        inter_hd.append(diff / total)

    # Inter-challenge Hamming
    cross_hd = []
    for i in range(500):
        j = (i + 1) % args.n_challenges
        diff, total = hamming_distance_bits(responses_full[i], responses_full[j], n_bits=8)
        cross_hd.append(diff / total)

    print(f"      Intra-plate HD (noise):    {np.mean(intra_hd)*100:.2f}% ± {np.std(intra_hd)*100:.2f}%")
    print(f"      Inter-plate HD:            {np.mean(inter_hd)*100:.2f}% ± {np.std(inter_hd)*100:.2f}%")
    print(f"      Inter-challenge HD:        {np.mean(cross_hd)*100:.2f}% ± {np.std(cross_hd)*100:.2f}%")
    print(f"      Ideal: intra≈0%, inter≈50%")
    print()

    # ─── Modeling attack resistance ──────────────────────────────
    print(f"  [6] Modeling attack resistance...")
    print(f"      Attacker observes {args.n_attack_samples} CRPs, tries to predict new responses")
    print()

    # Attacker sees first N CRP pairs and tries to reconstruct H
    n_attack = args.n_attack_samples
    attack_challenges = challenges[:n_attack]
    attack_responses = responses_full[:n_attack]

    # Attack: least-squares fit of H from CRPs
    # response ≈ normalize(sum(H[c_i])) → hard to invert due to normalization
    # Simpler attack: build A matrix where each row = indicator of which modes are in challenge
    A = np.zeros((n_attack, n_modes))
    for i, c in enumerate(attack_challenges):
        for idx in c:
            A[i, idx] = 1.0

    # Target: unnormalized responses (undo normalization with known challenge size)
    # The attacker doesn't know the normalization, so use raw response
    targets = attack_responses  # Already normalized, attacker sees this

    # Least-squares: H_hat = (A^T A + λI)^{-1} A^T targets
    for lam in [1e-6, 1e-3, 0.1]:
        H_hat = np.linalg.solve(A.T @ A + lam * np.eye(n_modes), A.T @ targets)

        # Test on unseen challenges
        n_test = min(200, args.n_challenges - n_attack)
        test_challenges = challenges[n_attack:n_attack + n_test]
        test_responses = responses_full[n_attack:n_attack + n_test]

        pred_errors = []
        correct_retrievals = 0

        for i, c in enumerate(test_challenges):
            # Attacker's prediction
            pred = np.sum(H_hat[c], axis=0)
            pred_norm = np.linalg.norm(pred)
            if pred_norm > 0:
                pred = pred / pred_norm

            # Error
            err = 1 - np.dot(pred, test_responses[i])
            pred_errors.append(err)

            # Would attacker pass verification? (threshold = 5× noise)
            if err < threshold:
                correct_retrievals += 1

        attack_success = correct_retrievals / n_test
        print(f"      λ={lam:.0e}: mean error={np.mean(pred_errors):.4f}, "
              f"attack success={attack_success*100:.1f}% "
              f"({'BROKEN' if attack_success > 0.5 else 'SECURE'})")

    print()

    # Information-theoretic bound
    # H has 27×4 = 108 free parameters. Each CRP reveals ~4 dimensions of info.
    # Need at least 108/4 = 27 CRPs to fully determine H.
    min_crps_theory = n_modes * n_ch / n_ch  # = n_modes (27)
    print(f"      Information-theoretic bound: ≥ {int(min_crps_theory)} CRPs to model H")
    print(f"      Practical bound (with normalization ambiguity): higher")
    print()

    # ─── Entropy analysis ─────────────────────────────────────────
    print("  [7] Response entropy...")
    # Per-channel entropy of responses
    for ch in range(n_ch):
        vals = responses_full[:, ch]
        # Histogram-based entropy
        hist, _ = np.histogram(vals, bins=32, density=True)
        hist = hist[hist > 0]
        bin_width = (vals.max() - vals.min()) / 32
        entropy = -np.sum(hist * bin_width * np.log2(hist * bin_width + 1e-10))
        print(f"      Channel {ch}: entropy ≈ {entropy:.2f} bits (32-bin histogram)")

    total_entropy_bits = n_ch * 8  # Upper bound: 8 bits per channel
    print(f"      Max response entropy: {total_entropy_bits} bits (4 ch × 8 bit)")
    print()

    # ─── Final Summary ────────────────────────────────────────────
    print("=" * 70)
    print("  P2 RESULTS: PUF CHALLENGE-RESPONSE PROTOCOL")
    print("=" * 70)
    print()
    print(f"  Challenge space:      C(27,{args.challenge_size}) = {n_possible} challenges")
    print(f"  Response dimension:   {n_ch} channels × 8 bits = 32 bits")
    print(f"  Reproducibility:      cosine dist = {np.mean(intra_dists):.6f} (at 0.2% CV)")
    print(f"  Distinctiveness:      cosine dist = {np.mean(inter_dists):.4f} (inter-plate)")
    print(f"  Separation ratio:     {sep_ratio:.0f}× (min inter / max intra)")
    print(f"  Collision rate:       {collision_rate*100:.3f}%")
    print(f"  Modeling resistance:  {args.n_attack_samples} CRPs → "
          f"{'BROKEN' if attack_success > 0.5 else 'SECURE'}")
    print()

    # FAR/FRR
    # False Accept: inter-plate distance < threshold
    far = sum(1 for d in inter_dists if d < threshold) / len(inter_dists)
    # False Reject: intra-plate distance > threshold
    frr = sum(1 for d in intra_dists if d > threshold) / len(intra_dists)
    print(f"  FAR (false accept):   {far*100:.2f}%")
    print(f"  FRR (false reject):   {frr*100:.2f}%")
    print()

    if far < 0.001 and frr < 0.01 and sep_ratio > 10:
        verdict = "PASS"
        print("  ★ PASS — PUF properties verified: unique, stable, distinct")
    elif far < 0.01 and sep_ratio > 5:
        verdict = "PASS_MARGINAL"
        print("  △ PASS (marginal) — Good PUF properties")
    else:
        verdict = "FAIL"
        print(f"  ✗ FAIL — FAR={far*100:.1f}%, separation={sep_ratio:.1f}×")

    print()

    # ─── Save ─────────────────────────────────────────────────────
    DATA_DIR = Path('data/results/cam')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = DATA_DIR / f'p2_puf_challenge_response_{ts}.json'

    output = {
        'experiment': 'P2_PUF_challenge_response',
        'timestamp': datetime.now().isoformat(),
        'config': {
            'n_challenges': args.n_challenges,
            'challenge_size': args.challenge_size,
            'n_modes': int(n_modes),
            'n_channels': int(n_ch),
            'noise_cv': noise_cv,
            'n_attack_samples': args.n_attack_samples,
        },
        'challenge_space': int(n_possible),
        'intra_plate': {
            'mean_cosine_dist': float(np.mean(intra_dists)),
            'std': float(np.std(intra_dists)),
            'max': float(np.max(intra_dists)),
        },
        'inter_plate': {
            'mean_cosine_dist': float(np.mean(inter_dists)),
            'std': float(np.std(inter_dists)),
            'min': float(np.min(inter_dists)),
        },
        'separation_ratio': float(sep_ratio),
        'collision_rate': float(collision_rate),
        'hamming_distances': {
            'intra_mean': float(np.mean(intra_hd)),
            'inter_plate_mean': float(np.mean(inter_hd)),
            'inter_challenge_mean': float(np.mean(cross_hd)),
        },
        'far': float(far),
        'frr': float(frr),
        'modeling_attack': {
            'n_observed_crps': args.n_attack_samples,
            'attack_success_rate': float(attack_success),
        },
        'verdict': verdict,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {out_path}")
    print("  Done.")


if __name__ == '__main__':
    main()
