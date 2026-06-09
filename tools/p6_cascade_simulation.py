#!/usr/bin/env python3
"""
P6: Multi-Plate Cascade — Simulated Characterization

Simulates what a physical cascade (Plate I → amp → Plate H) would produce,
using the known enrollment data and proven linearity (T2.2).

Physical cascade wiring: NCO → Plate I → NE RX → Board D (×3.7) → Plate H SW TX → Plate H RX

For frequency f, the cascade produces:
  Direct from Plate I:  [H_I[f, NW], H_I[f, NE]]
  Through cascade:      [H_H[f, NW] × H_I[f, NE] × gain, H_H[f, NE] × H_I[f, NE] × gain]

The cascade channels are PRODUCTS of both plates' transfer functions — this is a
polynomial feature expansion that increases effective rank beyond either plate alone.

Tests:
1. Cascade H matrix properties (rank, condition number, spectral structure)
2. Comparison with single-plate H
3. Reservoir benchmark redux (D2-style) with cascaded features
4. Memory capacity with cascade
"""

import json
import numpy as np
from datetime import datetime
from pathlib import Path
from math import comb


def load_enrollment():
    """Load multi-plate enrollment."""
    h_path = Path('data/results/h_matrix/multi_plate_enrollment_20260603_171950.json')
    with open(h_path) as f:
        data = json.load(f)
    H = np.array(data['h_matrix_normalized'])  # 27×4
    freqs = data['mode_frequencies_hz']
    return H, freqs


def build_cascade_matrix(H, gain=3.7):
    """
    Build the cascaded transfer matrix.

    H columns: [Plate_I_NW, Plate_I_NE, Plate_H_NW, Plate_H_NE]

    Cascade wiring: Plate I NE RX → Board D (×gain) → Plate H SW TX

    For each frequency f, the cascade measurement gives:
      ch0: H[f, 0]  (Plate I NW — direct)
      ch1: H[f, 1]  (Plate I NE — direct, also the cascade drive)
      ch2: H[f, 2]  (Plate H NW — direct from NCO bypass)
      ch3: H[f, 3]  (Plate H NE — direct from NCO bypass)
      ch4: H[f, 2] × H[f, 1] × gain  (Plate H NW from cascade)
      ch5: H[f, 3] × H[f, 1] × gain  (Plate H NE from cascade)

    But in practice, if we re-route so Plate H is ONLY driven through cascade
    (no direct NCO path), then we get 4 clean channels:
      ch0: H[f, 0]  (Plate I NW — direct)
      ch1: H[f, 1]  (Plate I NE — also drives cascade)
      ch2: H[f, 2] × H[f, 1] × gain  (Plate H NW from cascade)
      ch3: H[f, 3] × H[f, 1] × gain  (Plate H NE from cascade)
    """
    n_modes = H.shape[0]

    # Option A: All 6 channels (both direct and cascade)
    H_6ch = np.zeros((n_modes, 6))
    H_6ch[:, 0] = H[:, 0]  # Plate I NW
    H_6ch[:, 1] = H[:, 1]  # Plate I NE
    H_6ch[:, 2] = H[:, 2]  # Plate H NW (direct)
    H_6ch[:, 3] = H[:, 3]  # Plate H NE (direct)
    H_6ch[:, 4] = H[:, 2] * H[:, 1] * gain  # Cascade: H_NW × PI_NE × gain
    H_6ch[:, 5] = H[:, 3] * H[:, 1] * gain  # Cascade: H_NE × PI_NE × gain

    # Option B: Pure cascade (Plate H only driven via Plate I)
    H_cascade = np.zeros((n_modes, 4))
    H_cascade[:, 0] = H[:, 0]  # Plate I NW (direct)
    H_cascade[:, 1] = H[:, 1]  # Plate I NE (direct)
    H_cascade[:, 2] = H[:, 2] * H[:, 1] * gain  # Cascade NW
    H_cascade[:, 3] = H[:, 3] * H[:, 1] * gain  # Cascade NE

    return H_6ch, H_cascade


def analyze_matrix(H, name):
    """Analyze matrix properties."""
    n, m = H.shape
    U, s, Vt = np.linalg.svd(H, full_matrices=False)

    # Effective rank (Shannon entropy of normalized singular values)
    s_norm = s / s.sum()
    entropy = -np.sum(s_norm * np.log(s_norm + 1e-15))
    eff_rank = np.exp(entropy)

    cond = s[0] / s[-1] if s[-1] > 0 else np.inf

    print(f"    {name} ({n}×{m}):")
    print(f"      SVD: [{', '.join(f'{v:.3f}' for v in s)}]")
    print(f"      Condition number: {cond:.2f}")
    print(f"      Effective rank:   {eff_rank:.2f}")
    print(f"      Value range:      [{H.min():.4f}, {H.max():.4f}]")

    return {'svd': s.tolist(), 'condition': float(cond),
            'effective_rank': float(eff_rank), 'shape': [n, m]}


def esn_reservoir_test(W, name, tasks=None):
    """
    Run ESN benchmark with given reservoir matrix (state = tanh(W @ input_proj)).
    W is n×n (Gram matrix from H@H^T or similar).
    """
    if tasks is None:
        tasks = ['narma10', 'mackey_glass', 'memory_capacity']

    results = {}
    rng = np.random.default_rng(123)
    N = W.shape[0]

    for task in tasks:
        if task == 'narma10':
            T = 2000
            u = 0.2 * rng.uniform(size=T)
            y = np.zeros(T)
            for t in range(10, T):
                y[t] = (0.3 * y[t-1] + 0.05 * y[t-1] * np.sum(y[t-10:t]) +
                        1.5 * u[t-1] * u[t-10] + 0.1)

            # ESN states
            x = np.zeros((T, N))
            w_in = rng.normal(0, 0.1, (N, 1))

            # Spectral radius normalization
            sr = np.max(np.abs(np.linalg.eigvalsh(W)))
            W_scaled = W * (0.9 / sr) if sr > 0 else W

            for t in range(1, T):
                x[t] = np.tanh(W_scaled @ x[t-1] + w_in.flatten() * u[t])

            # Ridge regression readout
            train_x = x[500:1500]
            train_y = y[500:1500]
            test_x = x[1500:]
            test_y = y[1500:]

            lam = 1e-4
            w_out = np.linalg.solve(train_x.T @ train_x + lam * np.eye(N),
                                     train_x.T @ train_y)
            pred = test_x @ w_out

            nrmse = np.sqrt(np.mean((pred - test_y)**2)) / np.std(test_y)
            results['narma10_nrmse'] = float(nrmse)

        elif task == 'mackey_glass':
            T = 2000
            mg = np.zeros(T + 200)
            mg[:30] = 1.2
            tau = 17
            for t in range(29, T + 199):
                mg[t+1] = mg[t] + 0.2 * mg[t-tau] / (1 + mg[t-tau]**10) - 0.1 * mg[t]
            mg = mg[200:]
            mg = (mg - mg.mean()) / mg.std()

            u = mg[:-1]
            y = mg[1:]

            x = np.zeros((len(u), N))
            w_in = rng.normal(0, 0.1, (N, 1))
            sr = np.max(np.abs(np.linalg.eigvalsh(W)))
            W_scaled = W * (0.9 / sr) if sr > 0 else W

            for t in range(1, len(u)):
                x[t] = np.tanh(W_scaled @ x[t-1] + w_in.flatten() * u[t])

            train_x = x[500:1500]
            train_y = y[500:1500]
            test_x = x[1500:]
            test_y = y[1500:]

            lam = 1e-4
            w_out = np.linalg.solve(train_x.T @ train_x + lam * np.eye(N),
                                     train_x.T @ train_y)
            pred = test_x @ w_out
            nrmse = np.sqrt(np.mean((pred - test_y)**2)) / np.std(test_y)
            results['mackey_glass_nrmse'] = float(nrmse)

        elif task == 'memory_capacity':
            T = 2000
            u = rng.normal(size=T)

            x = np.zeros((T, N))
            w_in = rng.normal(0, 0.1, (N, 1))
            sr = np.max(np.abs(np.linalg.eigvalsh(W)))
            W_scaled = W * (0.9 / sr) if sr > 0 else W

            for t in range(1, T):
                x[t] = np.tanh(W_scaled @ x[t-1] + w_in.flatten() * u[t])

            train_x = x[200:1200]
            test_x = x[1200:]

            mc_total = 0.0
            for delay in range(1, N + 1):
                train_y = u[200 - delay:1200 - delay]
                test_y = u[1200 - delay:T - delay]

                lam = 1e-4
                w_out = np.linalg.solve(train_x.T @ train_x + lam * np.eye(N),
                                         train_x.T @ train_y)
                pred = test_x @ w_out

                corr = np.corrcoef(pred, test_y)[0, 1]
                mc_total += corr**2 if not np.isnan(corr) else 0

            results['memory_capacity'] = float(mc_total)

    return results


def main():
    print("=" * 70)
    print("  P6: Multi-Plate Cascade — Simulated Characterization")
    print("=" * 70)
    print()
    print("  Physics: NCO → Plate I → ×3.7 amp → Plate H → measure")
    print("  Cascade channels = product of both plates' transfer functions")
    print("  This creates polynomial (degree-2) feature expansion")
    print()

    # ─── Load data ────────────────────────────────────────────────
    H, freqs = load_enrollment()
    n_modes, n_ch = H.shape
    print(f"  Enrollment: {n_modes} modes × {n_ch} channels")
    print(f"  Freq range: {freqs[0]/1000:.1f} – {freqs[-1]/1000:.1f} kHz")
    print()

    # ─── Build cascade matrices ───────────────────────────────────
    print("  [1] Building cascade matrices...")
    H_6ch, H_cascade = build_cascade_matrix(H, gain=3.7)

    # Normalize cascade for fair comparison
    H_cascade_norm = H_cascade.copy()
    for col in range(H_cascade_norm.shape[1]):
        mx = H_cascade_norm[:, col].max()
        if mx > 0:
            H_cascade_norm[:, col] /= mx

    H_6ch_norm = H_6ch.copy()
    for col in range(H_6ch_norm.shape[1]):
        mx = H_6ch_norm[:, col].max()
        if mx > 0:
            H_6ch_norm[:, col] /= mx

    print()

    # ─── Matrix analysis ──────────────────────────────────────────
    print("  [2] Matrix analysis...")
    print()

    props_orig = analyze_matrix(H, "Original H (direct)")
    print()
    props_cascade = analyze_matrix(H_cascade_norm, "Cascade H (4ch, polynomial)")
    print()
    props_6ch = analyze_matrix(H_6ch_norm, "Combined H (6ch, direct+cascade)")
    print()

    # Frobenius distance between original and cascade
    # Compare first 4 cols of original vs cascade (both 27×4)
    frob_dist = np.linalg.norm(H - H_cascade_norm, 'fro')
    frob_orig = np.linalg.norm(H, 'fro')
    print(f"    Frobenius distance (H vs H_cascade): {frob_dist:.4f} ({100*frob_dist/frob_orig:.1f}% of ||H||)")
    print()

    # ─── Gram matrices for reservoir ──────────────────────────────
    print("  [3] Reservoir weight matrices (Gram: H @ H^T)...")
    print()

    # Original: 27×4 → Gram = 27×27 (rank 4)
    W_orig = H @ H.T
    U, s_orig, _ = np.linalg.svd(W_orig)
    print(f"    Original Gram (H@H^T): rank-{np.sum(s_orig > 1e-10)}")
    print(f"      Top eigenvalues: [{', '.join(f'{v:.2f}' for v in s_orig[:6])}...]")

    # Cascade 4ch: 27×4 → Gram = 27×27 (still rank 4 maximum, but different structure)
    W_cascade = H_cascade_norm @ H_cascade_norm.T
    U, s_cascade, _ = np.linalg.svd(W_cascade)
    print(f"    Cascade Gram (H_c@H_c^T): rank-{np.sum(s_cascade > 1e-10)}")
    print(f"      Top eigenvalues: [{', '.join(f'{v:.2f}' for v in s_cascade[:6])}...]")

    # 6-channel combined: 27×6 → Gram = 27×27 (rank up to 6!)
    W_6ch = H_6ch_norm @ H_6ch_norm.T
    U, s_6ch, _ = np.linalg.svd(W_6ch)
    print(f"    Combined 6ch Gram (H_6@H_6^T): rank-{np.sum(s_6ch > 1e-10)}")
    print(f"      Top eigenvalues: [{', '.join(f'{v:.2f}' for v in s_6ch[:8])}...]")
    print()

    # Random baseline (rank-4)
    rng = np.random.default_rng(42)
    H_rand = rng.normal(size=(n_modes, 4))
    H_rand = H_rand / H_rand.max(axis=0)
    W_rand = H_rand @ H_rand.T
    U, s_rand, _ = np.linalg.svd(W_rand)
    print(f"    Random Gram (4ch): rank-{np.sum(s_rand > 1e-10)}")
    print(f"      Top eigenvalues: [{', '.join(f'{v:.2f}' for v in s_rand[:6])}...]")

    # Random 6ch
    H_rand6 = rng.normal(size=(n_modes, 6))
    H_rand6 = H_rand6 / H_rand6.max(axis=0)
    W_rand6 = H_rand6 @ H_rand6.T
    U, s_rand6, _ = np.linalg.svd(W_rand6)
    print(f"    Random Gram (6ch): rank-{np.sum(s_rand6 > 1e-10)}")
    print(f"      Top eigenvalues: [{', '.join(f'{v:.2f}' for v in s_rand6[:8])}...]")
    print()

    # ─── Reservoir benchmark ──────────────────────────────────────
    print("  [4] Reservoir benchmark (D2-style ESN)...")
    print()

    configs = [
        ("Physical 4ch (original)", W_orig),
        ("Cascade 4ch (polynomial)", W_cascade),
        ("Combined 6ch (direct+cascade)", W_6ch),
        ("Random 4ch", W_rand),
        ("Random 6ch", W_rand6),
    ]

    all_results = {}
    for name, W in configs:
        print(f"    Testing: {name}...")
        res = esn_reservoir_test(W, name)
        all_results[name] = res
        print(f"      NARMA-10 NRMSE: {res['narma10_nrmse']:.4f}")
        print(f"      Mackey-Glass NRMSE: {res['mackey_glass_nrmse']:.4f}")
        print(f"      Memory Capacity: {res['memory_capacity']:.1f}")
        print()

    # ─── Cascade benefit analysis ─────────────────────────────────
    print("  [5] Cascade benefit analysis...")
    print()

    narma_orig = all_results["Physical 4ch (original)"]['narma10_nrmse']
    narma_cascade = all_results["Cascade 4ch (polynomial)"]['narma10_nrmse']
    narma_6ch = all_results["Combined 6ch (direct+cascade)"]['narma10_nrmse']
    narma_rand4 = all_results["Random 4ch"]['narma10_nrmse']
    narma_rand6 = all_results["Random 6ch"]['narma10_nrmse']

    mc_orig = all_results["Physical 4ch (original)"]['memory_capacity']
    mc_cascade = all_results["Cascade 4ch (polynomial)"]['memory_capacity']
    mc_6ch = all_results["Combined 6ch (direct+cascade)"]['memory_capacity']
    mc_rand4 = all_results["Random 4ch"]['memory_capacity']
    mc_rand6 = all_results["Random 6ch"]['memory_capacity']

    print(f"    NARMA-10 improvement (lower=better):")
    print(f"      Original → Cascade:  {narma_orig:.4f} → {narma_cascade:.4f} ({100*(narma_orig-narma_cascade)/narma_orig:+.1f}%)")
    print(f"      Original → Combined: {narma_orig:.4f} → {narma_6ch:.4f} ({100*(narma_orig-narma_6ch)/narma_orig:+.1f}%)")
    print(f"      Random 4ch baseline: {narma_rand4:.4f}")
    print(f"      Random 6ch baseline: {narma_rand6:.4f}")
    print()
    print(f"    Memory Capacity improvement (higher=better):")
    print(f"      Original → Cascade:  {mc_orig:.1f} → {mc_cascade:.1f} ({100*(mc_cascade-mc_orig)/mc_orig:+.1f}%)")
    print(f"      Original → Combined: {mc_orig:.1f} → {mc_6ch:.1f} ({100*(mc_6ch-mc_orig)/mc_orig:+.1f}%)")
    print(f"      Random 4ch baseline: {mc_rand4:.1f}")
    print(f"      Random 6ch baseline: {mc_rand6:.1f}")
    print()

    # ─── Key insight ──────────────────────────────────────────────
    print("  [6] Key insight: Does cascade help?")
    print()

    # The question: does the polynomial (multiplicative) expansion from the
    # cascade provide benefit beyond simply adding more channels?
    # Compare: cascade 4ch vs random 4ch, and combined 6ch vs random 6ch

    cascade_vs_rand4_narma = narma_cascade - narma_rand4
    combined_vs_rand6_narma = narma_6ch - narma_rand6
    cascade_vs_rand4_mc = mc_cascade - mc_rand4
    combined_vs_rand6_mc = mc_6ch - mc_rand6

    print(f"    Cascade vs Random (same dims):")
    print(f"      NARMA: cascade_4ch - rand_4ch = {cascade_vs_rand4_narma:+.4f}")
    print(f"      NARMA: combined_6ch - rand_6ch = {combined_vs_rand6_narma:+.4f}")
    print(f"      MC: cascade_4ch - rand_4ch = {cascade_vs_rand4_mc:+.1f}")
    print(f"      MC: combined_6ch - rand_6ch = {combined_vs_rand6_mc:+.1f}")
    print()

    # Does cascade outperform single plate?
    cascade_helps_narma = narma_cascade < narma_orig
    cascade_helps_mc = mc_cascade > mc_orig
    combined_helps_narma = narma_6ch < narma_orig
    combined_helps_mc = mc_6ch > mc_orig

    print(f"    Cascade improves on single plate:")
    print(f"      NARMA: {'YES' if cascade_helps_narma else 'NO'} (4ch)")
    print(f"      MC:    {'YES' if cascade_helps_mc else 'NO'} (4ch)")
    print(f"      NARMA: {'YES' if combined_helps_narma else 'NO'} (6ch combined)")
    print(f"      MC:    {'YES' if combined_helps_mc else 'NO'} (6ch combined)")
    print()

    # ─── Verdict ──────────────────────────────────────────────────
    print("=" * 70)
    print("  P6 RESULTS: CASCADE CHARACTERIZATION (SIMULATION)")
    print("=" * 70)
    print()

    rank_increase = np.sum(s_6ch > 1e-10) > np.sum(s_orig > 1e-10)
    structure_different = frob_dist / frob_orig > 0.10
    reservoir_better = combined_helps_narma or combined_helps_mc

    print(f"  Rank increase (6ch vs 4ch):     {np.sum(s_orig > 1e-10)} → {np.sum(s_6ch > 1e-10)} ({'YES' if rank_increase else 'NO'})")
    print(f"  Structure different (>10%):      {100*frob_dist/frob_orig:.1f}% ({'YES' if structure_different else 'NO'})")
    print(f"  Reservoir improvement:           {'YES' if reservoir_better else 'NO'}")
    print()

    if rank_increase and structure_different and reservoir_better:
        verdict = "PASS"
        print("  ★ PASS — Cascade increases rank and improves reservoir")
        print("           Physical experiment WORTH DOING")
    elif rank_increase or reservoir_better:
        verdict = "PASS_MARGINAL"
        print("  △ PASS (marginal) — Some improvement from cascade")
        print("           Physical experiment may be interesting")
    else:
        verdict = "FAIL"
        print("  ✗ FAIL — Cascade does not help")
        print("           Physical experiment NOT justified")

    print()

    # ─── Save ─────────────────────────────────────────────────────
    DATA_DIR = Path('data/results/reservoir_classify')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = DATA_DIR / f'p6_cascade_simulation_{ts}.json'

    output = {
        'experiment': 'P6_cascade_simulation',
        'timestamp': datetime.now().isoformat(),
        'note': 'SIMULATION ONLY — predicts physical cascade from enrollment data',
        'matrix_analysis': {
            'original': props_orig,
            'cascade_4ch': props_cascade,
            'combined_6ch': props_6ch,
        },
        'gram_ranks': {
            'original_4ch': int(np.sum(s_orig > 1e-10)),
            'cascade_4ch': int(np.sum(s_cascade > 1e-10)),
            'combined_6ch': int(np.sum(s_6ch > 1e-10)),
        },
        'frobenius_distance_pct': float(100 * frob_dist / frob_orig),
        'reservoir_results': {k: v for k, v in all_results.items()},
        'cascade_helps': {
            'rank_increase': bool(rank_increase),
            'structure_different': bool(structure_different),
            'narma_improved': bool(cascade_helps_narma or combined_helps_narma),
            'mc_improved': bool(cascade_helps_mc or combined_helps_mc),
        },
        'verdict': verdict,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {out_path}")
    print("  Done.")


if __name__ == '__main__':
    main()
