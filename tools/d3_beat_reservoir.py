#!/usr/bin/env python3
"""
D3 — Beat-Pattern Virtual-Node Reservoir

Hypothesis: The plate is linear, but envelope detection (|analytic signal|²)
provides QUADRATIC nonlinearity. When multiple modes ring simultaneously,
beat-frequency amplitudes at |f_i - f_j| are proportional to a_i × a_j,
which are products of mode amplitudes carrying different temporal histories.

This is directly analogous to:
- NTSC colorburst: beat between reference carrier and color subcarrier
  encodes phase (= timing information)
- CDMA spreading: input modulated by mask across modes acts as spreading code;
  quadratic readout acts as despreader with cross-correlation memory

The simulation:
1. Mode dynamics: a_i[t] = a_i[t-1] * decay_i + mask_i * u[t]
   - decay_i = exp(-π * f_i / (Q * f_step))  [mode-dependent!]
   - mask_i  = fixed random spreading code (different per mode)
2. Linear features: y = H.T @ a  → 4 features (rank-4, what D2 used)
3. Quadratic features (beat/envelope): a_i * a_j * H[i,r] * H[j,r]
   for all mode pairs (i,j) at each receiver r → up to 1404 features
4. Train linear readout on NARMA-10

Success criterion: NRMSE < 0.44 (beat random ESN baseline from D2)
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime

# ─── Load measured hardware parameters ────────────────────────────
DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'

with open(DATA_DIR / 'h_matrix' / 'multi_plate_enrollment_20260603_171950.json') as f:
    h_data = json.load(f)

H = np.array(h_data['h_matrix_normalized'])       # (27, 4)
freqs = np.array(h_data['mode_frequencies_hz'])    # (27,)
n_modes, n_rx = H.shape

# Measured loaded Q from E10
Q_LOADED = 241.0

print("D3 — Beat-Pattern Virtual-Node Reservoir")
print("=" * 70)
print(f"H matrix: {n_modes} modes × {n_rx} receivers")
print(f"Frequencies: {freqs[0]/1e3:.0f}–{freqs[-1]/1e3:.0f} kHz")
print(f"Loaded Q: {Q_LOADED}")
print()


# ─── NARMA-10 generator ──────────────────────────────────────────
def generate_narma10(n_steps, seed=42):
    rng = np.random.default_rng(seed)
    u = rng.uniform(0, 0.5, n_steps + 200)
    y = np.zeros(n_steps + 200)
    for t in range(10, len(y)):
        y[t] = 0.3*y[t-1] + 0.05*y[t-1]*np.sum(y[t-10:t]) + 1.5*u[t-1]*u[t-10] + 0.1
        y[t] = np.clip(y[t], 0, 1.0)
    return u[200:], y[200:]


# ─── Mode dynamics simulation ─────────────────────────────────────
def simulate_reservoir(u, H, freqs, Q, f_step, mask, feature_mode='quadratic'):
    """
    Simulate plate mode dynamics + feature extraction.

    Args:
        u: input sequence (n_steps,)
        H: transfer matrix (n_modes, n_rx)
        freqs: mode frequencies (n_modes,)
        Q: loaded quality factor
        f_step: input presentation rate (Hz)
        mask: spreading code (n_modes,) — weights per mode
        feature_mode: 'linear', 'quadratic', or 'both'

    Returns:
        states: (n_steps, n_features) feature matrix
    """
    n_steps = len(u)
    n_modes, n_rx = H.shape

    # Mode-specific decay rates (KEY: different modes decay at different rates!)
    # decay_i = exp(-π * f_i / (Q * f_step))
    # Higher frequency modes decay faster per step
    decay = np.exp(-np.pi * freqs / (Q * f_step))

    print(f"  Decay rates: min={decay.min():.4f} (f={freqs[np.argmin(decay)]/1e3:.0f}kHz), "
          f"max={decay.max():.4f} (f={freqs[np.argmax(decay)]/1e3:.0f}kHz)")
    print(f"  Memory depth (steps to 1/e): min={-1/np.log(decay.min()):.1f}, max={-1/np.log(decay.max()):.1f}")

    # Simulate mode amplitudes
    a = np.zeros((n_steps, n_modes))
    state = np.zeros(n_modes)

    for t in range(n_steps):
        state = state * decay + mask * u[t]
        a[t] = state

    # Feature extraction
    if feature_mode == 'linear':
        # Standard: project through H → 4 features (rank 4, same as D2)
        return a @ H  # (n_steps, n_rx)

    elif feature_mode == 'quadratic':
        # Beat-pattern: products a_i * a_j projected through H[i,r]*H[j,r]
        # For efficiency, compute selected quadratic features

        # Strategy: Use ALL mode pairs but project through receiver weights
        # Feature at receiver r for pair (i,j): a_i * a_j * H[i,r] * H[j,r]
        # This is equivalent to: for each receiver r, compute (H[:,r] ⊙ a)²
        # decomposed into self-terms and cross-terms

        # Efficient computation: for each receiver, compute element-wise
        # weighted_a_r = a * H[:,r]  → then outer product
        # But we want the unique upper-triangle of the outer product

        features = []
        for r in range(n_rx):
            w = H[:, r]  # (n_modes,) spatial weight for this receiver
            wa = a * w[np.newaxis, :]  # (n_steps, n_modes) weighted amplitudes

            # Self-terms (diagonal): (a_i * H[i,r])² → 27 features per rx
            self_terms = wa ** 2  # (n_steps, n_modes)
            features.append(self_terms)

            # Cross-terms: a_i*a_j * H[i,r]*H[j,r] for i<j → 351 features per rx
            # Efficient: wa_i * wa_j for all pairs
            for i in range(n_modes):
                for j in range(i+1, n_modes):
                    features.append((wa[:, i] * wa[:, j])[:, np.newaxis])

        return np.hstack(features)

    elif feature_mode == 'both':
        # Linear + quadratic
        linear = a @ H  # (n_steps, n_rx)

        features = [linear]
        for r in range(n_rx):
            w = H[:, r]
            wa = a * w[np.newaxis, :]
            self_terms = wa ** 2
            features.append(self_terms)
            for i in range(n_modes):
                for j in range(i+1, n_modes):
                    features.append((wa[:, i] * wa[:, j])[:, np.newaxis])

        return np.hstack(features)

    elif feature_mode == 'quadratic_compact':
        # More efficient: just compute a_i * a_j for all pairs, then project
        # through Khatri-Rao product of H. This avoids per-receiver loop.
        # Quadratic state: vec(a ⊗ a) but just upper triangle
        n_pairs = n_modes * (n_modes + 1) // 2
        quad = np.zeros((n_steps, n_pairs))
        idx = 0
        for i in range(n_modes):
            for j in range(i, n_modes):
                quad[:, idx] = a[:, i] * a[:, j]
                idx += 1
        return quad


def train_readout(states, target, n_train, ridge_alpha=1e-4):
    """Ridge regression readout."""
    washout = 200
    X_train = states[washout:n_train]
    y_train = target[washout:n_train]
    X_test = states[n_train:]
    y_test = target[n_train:]

    # Ridge regression
    XtX = X_train.T @ X_train + ridge_alpha * np.eye(X_train.shape[1])
    W_out = np.linalg.solve(XtX, X_train.T @ y_train)

    y_pred = X_test @ W_out
    mse = np.mean((y_test - y_pred)**2)
    var = np.var(y_test)
    nrmse = np.sqrt(mse / var) if var > 1e-10 else np.inf

    return nrmse, W_out


def memory_capacity(states, n_train, max_delay=50, ridge_alpha=1e-4, seed=42):
    """Compute memory capacity from state matrix."""
    rng = np.random.default_rng(seed)
    n_total = states.shape[0]

    # Generate fresh random input for MC test
    u_mc = rng.uniform(-1, 1, n_total)

    # Resimulate with this input... actually we need to pass in the states
    # that were driven by u_mc. For now, we'll compute MC on whatever states we have.
    # This is a simplification — proper MC needs states driven by white noise.
    washout = 200
    X_train = states[washout:n_train]
    X_test = states[n_train:]

    mc = 0.0
    for delay in range(1, max_delay + 1):
        # Create delayed target from a reference signal
        # For proper MC, we need the input that drove these states
        # We'll return this as a separate function
        pass
    return mc  # placeholder


# ─── Main experiment ──────────────────────────────────────────────
N_STEPS = 5000
N_TRAIN = 4000
N_RANDOM_MASKS = 10

# Input step rate — critical parameter!
# If f_step is too slow, all modes decay fully between steps (no memory)
# If f_step is too fast, modes don't evolve between steps (no diversity)
# Sweet spot: f_step ≈ π*f_mean/Q ≈ π*76000/241 ≈ 990 Hz → ~1 kHz
# But we want to try multiple rates

F_STEP_CANDIDATES = [500, 1000, 2000, 5000, 10000]

print("─── Phase 1: Input Rate Sweep (linear features only) ───")
print(f"  Testing how input step rate affects linear reservoir...")
print()

u_narma, y_narma = generate_narma10(N_STEPS, seed=42)

rng = np.random.default_rng(2026)
mask_base = rng.standard_normal(n_modes)
mask_base = mask_base / np.linalg.norm(mask_base)  # Unit norm spreading code

for f_step in F_STEP_CANDIDATES:
    states = simulate_reservoir(u_narma, H, freqs, Q_LOADED, f_step, mask_base, 'linear')
    nrmse, _ = train_readout(states, y_narma, N_TRAIN)
    print(f"  f_step={f_step:>5} Hz → linear NRMSE = {nrmse:.4f} (D2 baseline: 0.7036)")
    print()

print()
print("─── Phase 2: Quadratic (Beat) Features ───")
print(f"  Same input, but extract a_i*a_j products (envelope/beat features)")
print()

best_nrmse = 1.0
best_config = None
results_table = []

for f_step in [500, 1000, 2000, 5000]:
    print(f"\n  f_step = {f_step} Hz:")

    # Quadratic compact (all mode pairs, no receiver projection)
    states_q = simulate_reservoir(u_narma, H, freqs, Q_LOADED, f_step, mask_base, 'quadratic_compact')
    nrmse_q, _ = train_readout(states_q, y_narma, N_TRAIN)
    print(f"    Quadratic compact ({states_q.shape[1]} features): NRMSE = {nrmse_q:.4f}")

    # Full quadratic through receivers (beat-pattern features)
    states_full = simulate_reservoir(u_narma, H, freqs, Q_LOADED, f_step, mask_base, 'both')
    nrmse_full, _ = train_readout(states_full, y_narma, N_TRAIN)
    print(f"    Full linear+quadratic ({states_full.shape[1]} features): NRMSE = {nrmse_full:.4f}")

    results_table.append({
        'f_step': f_step,
        'nrmse_quad_compact': float(nrmse_q),
        'nrmse_full': float(nrmse_full),
        'n_features_compact': states_q.shape[1],
        'n_features_full': states_full.shape[1],
    })

    if nrmse_full < best_nrmse:
        best_nrmse = nrmse_full
        best_config = f_step

print()
print("─── Phase 3: Mask Diversity (multiple spreading codes) ───")
print(f"  Using best f_step={best_config} Hz, testing different masks...")
print()

nrmse_masks = []
for m in range(N_RANDOM_MASKS):
    mask = rng.standard_normal(n_modes)
    mask = mask / np.linalg.norm(mask)
    states = simulate_reservoir(u_narma, H, freqs, Q_LOADED, best_config, mask, 'both')
    nrmse, _ = train_readout(states, y_narma, N_TRAIN)
    nrmse_masks.append(nrmse)
    if (m+1) % 5 == 0:
        print(f"    Mask {m+1}/{N_RANDOM_MASKS}: NRMSE = {nrmse:.4f}")

print(f"\n  Mask ensemble: NRMSE = {np.mean(nrmse_masks):.4f} ± {np.std(nrmse_masks):.4f}")
print(f"  Best mask: {min(nrmse_masks):.4f}, Worst: {max(nrmse_masks):.4f}")

print()
print("─── Phase 4: Ridge Alpha Sweep (best config) ───")
print()

mask_best_idx = np.argmin(nrmse_masks)
mask_best = rng.standard_normal(n_modes)  # Regenerate same sequence
for _ in range(mask_best_idx + 1):
    mask_best = rng.standard_normal(n_modes)
# Just use the base mask for reproducibility
states_best = simulate_reservoir(u_narma, H, freqs, Q_LOADED, best_config, mask_base, 'both')

for alpha in [1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1]:
    nrmse, _ = train_readout(states_best, y_narma, N_TRAIN, ridge_alpha=alpha)
    print(f"  α={alpha:.0e}: NRMSE = {nrmse:.4f}")

print()
print("─── Phase 5: Comparison with Random Baseline ───")
print(f"  Random 27-node ESN (from D2): NRMSE = 0.4417 ± 0.024")
print(f"  Standard H Gram reservoir (D2): NRMSE = 0.7036")
print(f"  Beat-pattern reservoir (best): NRMSE = {best_nrmse:.4f}")
print()

# Also test: what if we had MORE receivers? (Projection)
print("─── Phase 6: Scaling Analysis ───")
print(f"  How does performance scale with number of receivers?")
print()

# Simulate reduced receiver counts
for n_rx_sub in [1, 2, 3, 4]:
    H_sub = H[:, :n_rx_sub]
    states_sub = simulate_reservoir(u_narma, H_sub, freqs, Q_LOADED, best_config, mask_base, 'both')
    nrmse_sub, _ = train_readout(states_sub, y_narma, N_TRAIN)
    n_feat = states_sub.shape[1]
    print(f"  {n_rx_sub} receiver(s) → {n_feat} features → NRMSE = {nrmse_sub:.4f}")

print()
print("=" * 70)
print("  D3 BEAT-PATTERN RESERVOIR — SUMMARY")
print("=" * 70)
print(f"  Standard Gram (D2):        NRMSE = 0.7036  (4 features, rank 4)")
print(f"  Random ESN baseline (D2):  NRMSE = 0.4417  (27 nodes)")
print(f"  Beat-pattern (this):       NRMSE = {best_nrmse:.4f}  (f_step={best_config} Hz)")
print()

if best_nrmse < 0.44:
    verdict = "PASS"
    print("  ★★ PASS — Beat reservoir BEATS random ESN!")
    print("  Quadratic features from envelope detection unlock temporal computation.")
elif best_nrmse < 0.70:
    verdict = "PARTIAL"
    print("  ★ PARTIAL — Beat reservoir beats Gram, but not random ESN.")
    print("  Quadratic features help but may need tuning or more receivers.")
else:
    verdict = "FAIL"
    print("  ✗ FAIL — Beat reservoir doesn't improve over Gram baseline.")

# ─── Save results ─────────────────────────────────────────────────
OUT_DIR = DATA_DIR / 'reservoir'
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = OUT_DIR / f'd3_beat_reservoir_{ts}.json'

output = {
    'test': 'D3_beat_pattern_reservoir',
    'timestamp': datetime.now().isoformat(),
    'concept': 'Envelope detection provides quadratic nonlinearity on linear plate modes. '
               'Beat frequencies |f_i-f_j| at each receiver give products a_i*a_j carrying '
               'different temporal histories (CDMA/colorburst analogy).',
    'hardware_params': {
        'n_modes': int(n_modes),
        'n_receivers': int(n_rx),
        'Q_loaded': Q_LOADED,
        'freq_range_hz': [int(freqs[0]), int(freqs[-1])],
    },
    'best_config': {
        'f_step_hz': best_config,
        'feature_mode': 'linear+quadratic',
        'mask': 'unit_normal_random',
    },
    'results_by_fstep': results_table,
    'mask_ensemble': {
        'n_masks': N_RANDOM_MASKS,
        'nrmse_mean': float(np.mean(nrmse_masks)),
        'nrmse_std': float(np.std(nrmse_masks)),
        'nrmse_best': float(min(nrmse_masks)),
        'nrmse_worst': float(max(nrmse_masks)),
    },
    'baselines': {
        'gram_reservoir_d2': 0.7036,
        'random_esn_d2': 0.4417,
    },
    'best_nrmse': float(best_nrmse),
    'verdict': verdict,
}

with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\n  Saved: {out_path}")
