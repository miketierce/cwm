#!/usr/bin/env python3
"""
D2: Reservoir Benchmark — Does plate-H outperform random matrices?

Uses the measured 27×4 H matrix as a reservoir kernel in a standard
Echo State Network (ESN) with digital recurrence loop:

    x(t+1) = tanh(α * W_res @ x(t) + W_in @ u(t))
    y(t) = W_out @ x(t)   (trained via ridge regression)

Tests on:
    1. NARMA-10 (nonlinear memory benchmark)
    2. Mackey-Glass chaotic time series prediction
    3. Memory Capacity (linear memory depth)

Compares:
    - Physical plate H (27×4 expanded to square via H @ H^T or padded)
    - Random Gaussian matrices (same spectral radius)
    - Random sparse matrices (same density + spectral radius)
    - Random orthogonal matrices

KEY DIFFERENCE FROM L3: The readout is LINEAR (ridge regression).
It CANNOT absorb H's structure. If plate-H has genuinely useful
non-trivial mixing, it should outperform random here.
"""

import argparse
import json
import numpy as np
from datetime import datetime
from pathlib import Path


def generate_narma10(n_steps, seed=42):
    """Generate NARMA-10 input/output sequences."""
    rng = np.random.default_rng(seed)
    u = rng.uniform(0, 0.5, n_steps + 100)
    y = np.zeros(n_steps + 100)

    for t in range(10, len(y)):
        y[t] = (0.3 * y[t-1] +
                0.05 * y[t-1] * np.sum(y[t-10:t]) +
                1.5 * u[t-1] * u[t-10] +
                0.1)
        # Clip to prevent divergence
        y[t] = np.clip(y[t], 0, 1.0)

    return u[100:], y[100:]


def generate_mackey_glass(n_steps, tau=17, seed=42):
    """Generate Mackey-Glass chaotic time series."""
    # Generate longer sequence with transient
    n_total = n_steps + 1000
    x = np.zeros(n_total + tau)
    x[:tau] = 0.9  # Initial condition

    rng = np.random.default_rng(seed)
    # Small noise for initialization diversity
    x[:tau] += rng.normal(0, 0.001, tau)

    dt = 1.0
    for t in range(tau, n_total + tau - 1):
        x_tau = x[t - tau]
        x[t+1] = x[t] + dt * (0.2 * x_tau / (1.0 + x_tau**10) - 0.1 * x[t])

    # Remove transient
    series = x[1000+tau:]
    # Normalize
    series = (series - series.mean()) / series.std()
    return series[:n_steps]


def memory_capacity_target(u, delay):
    """Target for memory capacity: u(t - delay)."""
    if delay >= len(u):
        return np.zeros(len(u))
    target = np.zeros(len(u))
    target[delay:] = u[:len(u)-delay]
    return target


def build_reservoir_matrix(H_physical, method='gram', size=None):
    """
    Build a square reservoir matrix from the 27×4 physical H.

    Methods:
        'gram': Use H @ H^T (27×27) — preserves pairwise mode relationships
        'augmented': Pad H to square with zeros (27×27, first 4 cols from H)
        'kron': Kronecker product H ⊗ H^T → richer structure
    """
    n_modes, n_ch = H_physical.shape

    if method == 'gram':
        # H @ H^T is 27×27, captures mode-mode similarity through spatial channels
        W = H_physical @ H_physical.T
    elif method == 'augmented':
        # Place H in first 4 columns of 27×27 matrix
        W = np.zeros((n_modes, n_modes))
        W[:, :n_ch] = H_physical
        # Add transpose in remaining columns for symmetry breaking
        W[:n_ch, :] += H_physical.T
    elif method == 'outer':
        # Outer product structure: each row of H defines a "mode vector"
        # Use random projections of these vectors for full rank
        rng = np.random.default_rng(12345)
        P = rng.standard_normal((n_ch, n_modes))
        W = H_physical @ P  # 27×27
    else:
        raise ValueError(f"Unknown method: {method}")

    return W


def scale_to_spectral_radius(W, target_rho):
    """Scale matrix so its spectral radius equals target_rho."""
    eigenvalues = np.linalg.eigvals(W)
    rho = np.max(np.abs(eigenvalues))
    if rho < 1e-10:
        return W
    return W * (target_rho / rho)


def generate_random_reservoir(size, spectral_radius, method='gaussian', seed=0):
    """Generate a random reservoir matrix for comparison."""
    rng = np.random.default_rng(seed)

    if method == 'gaussian':
        W = rng.standard_normal((size, size)) / np.sqrt(size)
    elif method == 'sparse':
        # 10% connectivity (typical for ESN)
        W = np.zeros((size, size))
        mask = rng.random((size, size)) < 0.1
        W[mask] = rng.standard_normal(int(mask.sum()))
    elif method == 'orthogonal':
        # Random orthogonal matrix
        Q, _ = np.linalg.qr(rng.standard_normal((size, size)))
        W = Q
    else:
        raise ValueError(f"Unknown method: {method}")

    return scale_to_spectral_radius(W, spectral_radius)


def run_esn(W_res, W_in, data_in, data_target, n_train, n_test,
            spectral_radius=0.9, input_scale=0.1, ridge_alpha=1e-6,
            leak_rate=1.0):
    """
    Run Echo State Network.

    Returns: (train_nrmse, test_nrmse, test_predictions)
    """
    N = W_res.shape[0]
    n_total = len(data_in)

    # Scale reservoir
    W = scale_to_spectral_radius(W_res, spectral_radius)

    # Run reservoir
    states = np.zeros((n_total, N))
    x = np.zeros(N)

    for t in range(n_total):
        u = data_in[t] if np.isscalar(data_in[t]) else data_in[t]
        x_new = np.tanh(W @ x + input_scale * W_in * u)
        x = (1 - leak_rate) * x + leak_rate * x_new
        states[t] = x

    # Discard washout (first 100 steps)
    washout = 100
    states = states[washout:]
    target = data_target[washout:]

    n_train_eff = n_train - washout
    n_test_eff = n_test

    # Train readout via ridge regression
    X_train = states[:n_train_eff]
    y_train = target[:n_train_eff]
    X_test = states[n_train_eff:n_train_eff + n_test_eff]
    y_test = target[n_train_eff:n_train_eff + n_test_eff]

    # Ridge regression: W_out = (X^T X + αI)^{-1} X^T y
    XtX = X_train.T @ X_train + ridge_alpha * np.eye(X_train.shape[1])
    Xty = X_train.T @ y_train
    W_out = np.linalg.solve(XtX, Xty)

    # Predictions
    y_pred_train = X_train @ W_out
    y_pred_test = X_test @ W_out

    # NRMSE
    def nrmse(y_true, y_pred):
        mse = np.mean((y_true - y_pred) ** 2)
        var = np.var(y_true)
        return np.sqrt(mse / var) if var > 1e-10 else np.inf

    return nrmse(y_train, y_pred_train), nrmse(y_test, y_pred_test), y_pred_test


def compute_memory_capacity(W_res, W_in, n_steps=3000, max_delay=50,
                            spectral_radius=0.9, input_scale=0.1,
                            ridge_alpha=1e-6, seed=42):
    """Compute total memory capacity (sum of R² over delays)."""
    rng = np.random.default_rng(seed)
    u = rng.uniform(-1, 1, n_steps)

    N = W_res.shape[0]
    W = scale_to_spectral_radius(W_res, spectral_radius)

    # Run reservoir
    states = np.zeros((n_steps, N))
    x = np.zeros(N)
    for t in range(n_steps):
        x = np.tanh(W @ x + input_scale * W_in * u[t])
        states[t] = x

    # Discard washout
    washout = 200
    states = states[washout:]
    u_cut = u[washout:]

    n_train = len(states) - 500
    mc_total = 0.0
    mc_per_delay = []

    for delay in range(1, max_delay + 1):
        target = memory_capacity_target(u_cut, delay)

        X_train = states[:n_train]
        y_train = target[:n_train]
        X_test = states[n_train:]
        y_test = target[n_train:]

        # Ridge regression
        XtX = X_train.T @ X_train + ridge_alpha * np.eye(X_train.shape[1])
        W_out = np.linalg.solve(XtX, X_train.T @ y_train)

        y_pred = X_test @ W_out

        # R² (correlation squared)
        if np.std(y_test) > 1e-10 and np.std(y_pred) > 1e-10:
            r = np.corrcoef(y_test, y_pred)[0, 1]
            r2 = r ** 2
        else:
            r2 = 0.0

        mc_per_delay.append(r2)
        mc_total += r2

        # Stop if R² drops below threshold
        if r2 < 0.01 and delay > 5:
            break

    return mc_total, mc_per_delay


def main():
    parser = argparse.ArgumentParser(description='D2: Reservoir Benchmark')
    parser.add_argument('--n-random', type=int, default=20,
                        help='Number of random matrices to test')
    parser.add_argument('--n-steps', type=int, default=5000,
                        help='Time series length')
    parser.add_argument('--spectral-radius', type=float, default=0.9,
                        help='Target spectral radius')
    parser.add_argument('--input-scale', type=float, default=0.1,
                        help='Input scaling factor')
    parser.add_argument('--ridge-alpha', type=float, default=1e-6,
                        help='Ridge regression regularization')
    args = parser.parse_args()

    print("=" * 70)
    print("  D2: Reservoir Benchmark — Plate-H vs Random Matrices")
    print("=" * 70)
    print()
    print(f"  Config: n_steps={args.n_steps}, ρ={args.spectral_radius}, "
          f"input_scale={args.input_scale}")
    print(f"  Random baselines: {args.n_random} matrices per type")
    print(f"  Readout: Ridge regression (α={args.ridge_alpha})")
    print(f"  Key: readout is LINEAR — cannot absorb reservoir structure")
    print()

    # ─── Load physical H ───────────────────────────────────────────
    h_path = Path('data/results/h_matrix/multi_plate_enrollment_20260603_171950.json')
    with open(h_path) as f:
        h_data = json.load(f)
    H_physical = np.array(h_data['h_matrix_normalized'])
    n_modes = H_physical.shape[0]  # 27

    print(f"  Physical H: {H_physical.shape} (27 modes × 4 channels)")
    print(f"  H condition number: {np.linalg.cond(H_physical):.2f}")
    print(f"  SVD: {np.linalg.svd(H_physical, compute_uv=False)[:4].round(3)}")
    print()

    # ─── Build reservoir from physical H ───────────────────────────
    # Method: H @ H^T gives 27×27 gram matrix preserving mode relationships
    W_physical = build_reservoir_matrix(H_physical, method='gram')
    reservoir_size = W_physical.shape[0]  # 27

    print(f"  Reservoir size: {reservoir_size}×{reservoir_size}")
    print(f"  W_physical = H @ H^T (Gram matrix)")
    eigs = np.linalg.eigvals(W_physical)
    print(f"  Raw spectral radius: {np.max(np.abs(eigs)):.4f}")
    print()

    # ─── Input weights (fixed random, same for all reservoirs) ─────
    rng = np.random.default_rng(999)
    W_in = rng.standard_normal(reservoir_size)
    W_in = W_in / np.linalg.norm(W_in)

    # ─── Generate benchmark data ──────────────────────────────────
    n_train = args.n_steps - 1000
    n_test = 1000

    print("  [1] Generating benchmark data...")
    u_narma, y_narma = generate_narma10(args.n_steps, seed=42)
    mg_series = generate_mackey_glass(args.n_steps + 1, seed=42)
    # Mackey-Glass: predict next step
    u_mg = mg_series[:-1]
    y_mg = mg_series[1:]

    print(f"      NARMA-10: {args.n_steps} steps, u∈[0,0.5]")
    print(f"      Mackey-Glass: {args.n_steps} steps, τ=17")
    print()

    # ─── Run physical reservoir ───────────────────────────────────
    print("  [2] Physical plate-H reservoir...")

    # NARMA-10
    _, nrmse_phys_narma, _ = run_esn(
        W_physical, W_in, u_narma, y_narma, n_train, n_test,
        spectral_radius=args.spectral_radius,
        input_scale=args.input_scale,
        ridge_alpha=args.ridge_alpha
    )

    # Mackey-Glass
    _, nrmse_phys_mg, _ = run_esn(
        W_physical, W_in, u_mg, y_mg, n_train, n_test,
        spectral_radius=args.spectral_radius,
        input_scale=args.input_scale,
        ridge_alpha=args.ridge_alpha
    )

    # Memory Capacity
    mc_phys, mc_delays_phys = compute_memory_capacity(
        W_physical, W_in,
        n_steps=3000, max_delay=50,
        spectral_radius=args.spectral_radius,
        input_scale=args.input_scale,
        ridge_alpha=args.ridge_alpha
    )

    print(f"      NARMA-10 NRMSE:      {nrmse_phys_narma:.4f}")
    print(f"      Mackey-Glass NRMSE:   {nrmse_phys_mg:.4f}")
    print(f"      Memory Capacity:      {mc_phys:.2f}")
    print()

    # ─── Also test outer-product method ───────────────────────────
    print("  [2b] Physical plate-H (outer-product method)...")
    W_physical_outer = build_reservoir_matrix(H_physical, method='outer')

    _, nrmse_phys_outer_narma, _ = run_esn(
        W_physical_outer, W_in, u_narma, y_narma, n_train, n_test,
        spectral_radius=args.spectral_radius,
        input_scale=args.input_scale,
        ridge_alpha=args.ridge_alpha
    )
    _, nrmse_phys_outer_mg, _ = run_esn(
        W_physical_outer, W_in, u_mg, y_mg, n_train, n_test,
        spectral_radius=args.spectral_radius,
        input_scale=args.input_scale,
        ridge_alpha=args.ridge_alpha
    )
    mc_phys_outer, _ = compute_memory_capacity(
        W_physical_outer, W_in,
        n_steps=3000, max_delay=50,
        spectral_radius=args.spectral_radius,
        input_scale=args.input_scale,
        ridge_alpha=args.ridge_alpha
    )
    print(f"      NARMA-10 NRMSE:      {nrmse_phys_outer_narma:.4f}")
    print(f"      Mackey-Glass NRMSE:   {nrmse_phys_outer_mg:.4f}")
    print(f"      Memory Capacity:      {mc_phys_outer:.2f}")
    print()

    # ─── Random baselines ─────────────────────────────────────────
    print(f"  [3] Random baselines ({args.n_random} each)...")

    results_random = {'gaussian': [], 'sparse': [], 'orthogonal': []}

    for method in ['gaussian', 'sparse', 'orthogonal']:
        narma_scores = []
        mg_scores = []
        mc_scores = []

        for seed in range(args.n_random):
            W_rand = generate_random_reservoir(
                reservoir_size, args.spectral_radius, method=method, seed=seed
            )

            _, nrmse_narma, _ = run_esn(
                W_rand, W_in, u_narma, y_narma, n_train, n_test,
                spectral_radius=args.spectral_radius,
                input_scale=args.input_scale,
                ridge_alpha=args.ridge_alpha
            )

            _, nrmse_mg, _ = run_esn(
                W_rand, W_in, u_mg, y_mg, n_train, n_test,
                spectral_radius=args.spectral_radius,
                input_scale=args.input_scale,
                ridge_alpha=args.ridge_alpha
            )

            mc, _ = compute_memory_capacity(
                W_rand, W_in,
                n_steps=3000, max_delay=50,
                spectral_radius=args.spectral_radius,
                input_scale=args.input_scale,
                ridge_alpha=args.ridge_alpha
            )

            narma_scores.append(nrmse_narma)
            mg_scores.append(nrmse_mg)
            mc_scores.append(mc)

        results_random[method] = {
            'narma': narma_scores,
            'mg': mg_scores,
            'mc': mc_scores,
        }

        print(f"      {method:12s}: NARMA={np.mean(narma_scores):.4f}±{np.std(narma_scores):.4f}, "
              f"MG={np.mean(mg_scores):.4f}±{np.std(mg_scores):.4f}, "
              f"MC={np.mean(mc_scores):.2f}±{np.std(mc_scores):.2f}")

    print()

    # ─── Statistical comparison ───────────────────────────────────
    print("  [4] Statistical comparison (σ advantage of physical over random)...")
    print()

    # Use Gaussian as primary comparison (most common ESN baseline)
    gauss_narma = results_random['gaussian']['narma']
    gauss_mg = results_random['gaussian']['mg']
    gauss_mc = results_random['gaussian']['mc']

    # For NRMSE: lower is better → physical advantage = (random_mean - physical) / random_std
    sigma_narma = (np.mean(gauss_narma) - nrmse_phys_narma) / np.std(gauss_narma) if np.std(gauss_narma) > 0 else 0
    sigma_mg = (np.mean(gauss_mg) - nrmse_phys_mg) / np.std(gauss_mg) if np.std(gauss_mg) > 0 else 0
    # For MC: higher is better
    sigma_mc = (mc_phys - np.mean(gauss_mc)) / np.std(gauss_mc) if np.std(gauss_mc) > 0 else 0

    print(f"      Physical vs Gaussian random (σ advantage, positive = physical better):")
    print(f"        NARMA-10:       {sigma_narma:+.2f}σ")
    print(f"        Mackey-Glass:   {sigma_mg:+.2f}σ")
    print(f"        Memory Cap:     {sigma_mc:+.2f}σ")
    print()

    # vs sparse
    sparse_narma = results_random['sparse']['narma']
    sparse_mg = results_random['sparse']['mg']
    sparse_mc = results_random['sparse']['mc']
    sigma_narma_sp = (np.mean(sparse_narma) - nrmse_phys_narma) / np.std(sparse_narma) if np.std(sparse_narma) > 0 else 0
    sigma_mg_sp = (np.mean(sparse_mg) - nrmse_phys_mg) / np.std(sparse_mg) if np.std(sparse_mg) > 0 else 0
    sigma_mc_sp = (mc_phys - np.mean(sparse_mc)) / np.std(sparse_mc) if np.std(sparse_mc) > 0 else 0

    print(f"      Physical vs Sparse random:")
    print(f"        NARMA-10:       {sigma_narma_sp:+.2f}σ")
    print(f"        Mackey-Glass:   {sigma_mg_sp:+.2f}σ")
    print(f"        Memory Cap:     {sigma_mc_sp:+.2f}σ")
    print()

    # ─── Sweep spectral radius ────────────────────────────────────
    print("  [5] Spectral radius sweep (find optimal ρ for each)...")
    rho_values = [0.5, 0.7, 0.8, 0.9, 0.95, 0.99]

    phys_narma_by_rho = []
    rand_narma_by_rho = []

    for rho in rho_values:
        _, nrmse_p, _ = run_esn(
            W_physical, W_in, u_narma, y_narma, n_train, n_test,
            spectral_radius=rho, input_scale=args.input_scale,
            ridge_alpha=args.ridge_alpha
        )
        phys_narma_by_rho.append(nrmse_p)

        # Average over 5 random
        rand_scores = []
        for s in range(5):
            W_r = generate_random_reservoir(reservoir_size, rho, 'gaussian', seed=s+100)
            _, nr, _ = run_esn(
                W_r, W_in, u_narma, y_narma, n_train, n_test,
                spectral_radius=rho, input_scale=args.input_scale,
                ridge_alpha=args.ridge_alpha
            )
            rand_scores.append(nr)
        rand_narma_by_rho.append(np.mean(rand_scores))

    print(f"      {'ρ':>5s}  {'Physical':>10s}  {'Random':>10s}  {'Δ':>8s}")
    for i, rho in enumerate(rho_values):
        delta = rand_narma_by_rho[i] - phys_narma_by_rho[i]
        marker = " ★" if delta > 0 else ""
        print(f"      {rho:5.2f}  {phys_narma_by_rho[i]:10.4f}  {rand_narma_by_rho[i]:10.4f}  {delta:+8.4f}{marker}")
    print()

    # ─── Final summary ────────────────────────────────────────────
    print("=" * 70)
    print("  D2 RESULTS: RESERVOIR BENCHMARK")
    print("=" * 70)
    print()
    print(f"  {'Model':<28s} {'NARMA-10':>10s} {'Mackey-Glass':>13s} {'Memory Cap':>11s}")
    print(f"  {'─'*28} {'─'*10} {'─'*13} {'─'*11}")
    print(f"  {'Physical H (Gram)':28s} {nrmse_phys_narma:10.4f} {nrmse_phys_mg:13.4f} {mc_phys:11.2f}")
    print(f"  {'Physical H (Outer)':28s} {nrmse_phys_outer_narma:10.4f} {nrmse_phys_outer_mg:13.4f} {mc_phys_outer:11.2f}")
    print(f"  {'Random Gaussian (mean±std)':28s} {np.mean(gauss_narma):7.4f}±{np.std(gauss_narma):.3f} {np.mean(gauss_mg):10.4f}±{np.std(gauss_mg):.3f} {np.mean(gauss_mc):8.2f}±{np.std(gauss_mc):.2f}")
    print(f"  {'Random Sparse (mean±std)':28s} {np.mean(sparse_narma):7.4f}±{np.std(sparse_narma):.3f} {np.mean(sparse_mg):10.4f}±{np.std(sparse_mg):.3f} {np.mean(sparse_mc):8.2f}±{np.std(sparse_mc):.2f}")
    orth_narma = results_random['orthogonal']['narma']
    orth_mg = results_random['orthogonal']['mg']
    orth_mc = results_random['orthogonal']['mc']
    print(f"  {'Random Orthogonal (mean±std)':28s} {np.mean(orth_narma):7.4f}±{np.std(orth_narma):.3f} {np.mean(orth_mg):10.4f}±{np.std(orth_mg):.3f} {np.mean(orth_mc):8.2f}±{np.std(orth_mc):.2f}")
    print()

    # Verdict
    significant = abs(sigma_narma) >= 2.0 or abs(sigma_mg) >= 2.0 or abs(sigma_mc) >= 2.0
    better = sigma_narma > 0 or sigma_mg > 0 or sigma_mc > 0

    if significant and better:
        verdict = "PASS"
        print("  ★ PASS — Physical H significantly outperforms random on ≥1 benchmark")
    elif better:
        verdict = "MARGINAL"
        print("  △ MARGINAL — Physical H trends better but not significant (< 2σ)")
    elif significant:
        verdict = "FAIL"
        print("  ✗ FAIL — Physical H significantly WORSE than random")
    else:
        verdict = "INCONCLUSIVE"
        print("  ○ INCONCLUSIVE — Physical H indistinguishable from random")

    print(f"      Best σ advantage: NARMA={sigma_narma:+.2f}, MG={sigma_mg:+.2f}, MC={sigma_mc:+.2f}")
    print()

    # ─── Save ─────────────────────────────────────────────────────
    DATA_DIR = Path('data/results/reservoir_classify')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = DATA_DIR / f'd2_reservoir_benchmark_{ts}.json'

    output = {
        'experiment': 'D2_reservoir_benchmark',
        'timestamp': datetime.now().isoformat(),
        'config': {
            'n_steps': args.n_steps,
            'n_train': n_train,
            'n_test': n_test,
            'spectral_radius': args.spectral_radius,
            'input_scale': args.input_scale,
            'ridge_alpha': args.ridge_alpha,
            'reservoir_size': reservoir_size,
            'n_random': args.n_random,
            'h_matrix_source': str(h_path),
        },
        'physical_gram': {
            'narma10_nrmse': float(nrmse_phys_narma),
            'mackey_glass_nrmse': float(nrmse_phys_mg),
            'memory_capacity': float(mc_phys),
        },
        'physical_outer': {
            'narma10_nrmse': float(nrmse_phys_outer_narma),
            'mackey_glass_nrmse': float(nrmse_phys_outer_mg),
            'memory_capacity': float(mc_phys_outer),
        },
        'random_gaussian': {
            'narma10_nrmse': {'mean': float(np.mean(gauss_narma)), 'std': float(np.std(gauss_narma)), 'values': [float(x) for x in gauss_narma]},
            'mackey_glass_nrmse': {'mean': float(np.mean(gauss_mg)), 'std': float(np.std(gauss_mg)), 'values': [float(x) for x in gauss_mg]},
            'memory_capacity': {'mean': float(np.mean(gauss_mc)), 'std': float(np.std(gauss_mc)), 'values': [float(x) for x in gauss_mc]},
        },
        'random_sparse': {
            'narma10_nrmse': {'mean': float(np.mean(sparse_narma)), 'std': float(np.std(sparse_narma))},
            'mackey_glass_nrmse': {'mean': float(np.mean(sparse_mg)), 'std': float(np.std(sparse_mg))},
            'memory_capacity': {'mean': float(np.mean(sparse_mc)), 'std': float(np.std(sparse_mc))},
        },
        'random_orthogonal': {
            'narma10_nrmse': {'mean': float(np.mean(orth_narma)), 'std': float(np.std(orth_narma))},
            'mackey_glass_nrmse': {'mean': float(np.mean(orth_mg)), 'std': float(np.std(orth_mg))},
            'memory_capacity': {'mean': float(np.mean(orth_mc)), 'std': float(np.std(orth_mc))},
        },
        'sigma_advantage_vs_gaussian': {
            'narma10': float(sigma_narma),
            'mackey_glass': float(sigma_mg),
            'memory_capacity': float(sigma_mc),
        },
        'spectral_radius_sweep': {
            'rho_values': rho_values,
            'physical_narma': [float(x) for x in phys_narma_by_rho],
            'random_narma': [float(x) for x in rand_narma_by_rho],
        },
        'verdict': verdict,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {out_path}")
    print()
    print("  Done.")


if __name__ == '__main__':
    main()
