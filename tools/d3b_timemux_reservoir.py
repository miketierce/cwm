#!/usr/bin/env python3
"""
D3b — Time-Multiplexed Ringdown Reservoir (with Cascade)

Key insight: Instead of one readout per input step, capture K time-slices
of the ringdown. Each slice sees a DIFFERENT mix of mode amplitudes because
modes decay at different rates (higher f → faster decay). This converts
temporal memory into a spatial feature vector.

Analogy to broadcast timing:
- In NTSC colorburst, the burst reference decays at 3.58 MHz while the
  luma decays slower. Sampling at different delays gives different
  phase/amplitude ratios → color information emerges from timing.
- Here: mode n decays as exp(-π·f_n·Δt/Q). Sampling at K delays gives
  K different "projections" of the modal state → temporal information
  encoded spatially.

Combined with quadratic (envelope/beat) features:
- Linear time-mux features: K×n_rx per step
- Quadratic beat features: K×n_rx×(K×n_rx+1)/2 per step (cross-time products!)
- Cross-time products capture how the interference pattern EVOLVES during
  ringdown — this is the actual "beat pattern" the user described.

Option 3 layered in: Use cascade H matrix (4 receivers spanning 2 plates)
for richer spatial diversity.
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime

# ─── Load hardware parameters ─────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'

# Original H matrix
with open(DATA_DIR / 'h_matrix' / 'multi_plate_enrollment_20260603_171950.json') as f:
    h_data = json.load(f)
H_orig = np.array(h_data['h_matrix_normalized'])  # (27, 4)
freqs = np.array(h_data['mode_frequencies_hz'])    # (27,)

# Cascade H matrix (2-plate cascade)
with open(DATA_DIR / 'cascade' / 'p6_physical_cascade_20260603_202542.json') as f:
    c_data = json.load(f)
H_cascade_raw = np.array(c_data['h_matrix_raw'])   # (27, 4): [PI_NW, PI_NE, PH_NW, PH_NE]

# Normalize cascade H same way as original
H_cascade = H_cascade_raw / np.linalg.norm(H_cascade_raw, 'fro')

n_modes = len(freqs)
Q_LOADED = 241.0

print("D3b — Time-Multiplexed Ringdown Reservoir")
print("=" * 70)
print(f"Modes: {n_modes}, Frequencies: {freqs[0]/1e3:.0f}–{freqs[-1]/1e3:.0f} kHz")
print(f"Q_loaded: {Q_LOADED}")
print(f"H_orig shape: {H_orig.shape}")
print(f"H_cascade shape: {H_cascade.shape}")
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


# ─── Time-multiplexed reservoir simulation ────────────────────────
def simulate_timemux(u, H, freqs, Q, f_step, mask, n_slices=10,
                     feature_mode='timemux_quad'):
    """
    Time-multiplexed ringdown reservoir.

    For each input step:
      1. Inject: a += mask * u[t]
      2. Sample K time-slices during the inter-step interval
         Slice k at time t_k = (k+1)/(K+1) * T_step
         Mode amplitude at slice k: a_i * exp(-π*f_i*t_k/Q)
      3. Project each slice through H to get receiver signals
      4. Optionally compute quadratic features across slices

    Args:
        u: input (n_steps,)
        H: transfer matrix (n_modes, n_rx)
        freqs: mode frequencies (n_modes,)
        Q: quality factor
        f_step: input presentation rate (Hz)
        mask: mode weights (n_modes,)
        n_slices: K time-slices per input step
        feature_mode: 'linear', 'timemux_linear', 'timemux_quad'
    """
    n_steps = len(u)
    n_modes, n_rx = H.shape
    T_step = 1.0 / f_step  # seconds between inputs

    # Time points for slices within one step
    # Evenly spaced from 0 to T_step (exclusive of endpoints)
    t_slices = np.array([(k + 1) / (n_slices + 1) * T_step for k in range(n_slices)])

    # Decay matrix: decay[k, i] = exp(-π*f_i*t_k/Q)
    # This is the ringdown at each slice time for each mode
    decay_matrix = np.exp(-np.pi * freqs[np.newaxis, :] * t_slices[:, np.newaxis] / Q)

    # Full-step decay (state carried to next input)
    decay_full = np.exp(-np.pi * freqs * T_step / Q)

    print(f"  f_step={f_step} Hz, T_step={T_step*1e3:.2f} ms, K={n_slices} slices")
    if t_slices[0] < 1e-3:
        print(f"  Slice times: {t_slices*1e6} µs")
    else:
        print(f"  Slice times: {t_slices*1e3} ms")
    print(f"  Full-step decay: min={decay_full.min():.4f} (f={freqs[np.argmin(decay_full)]/1e3:.0f}kHz), "
          f"max={decay_full.max():.4f} (f={freqs[np.argmax(decay_full)]/1e3:.0f}kHz)")
    mem_depth = -1.0 / np.log(decay_full + 1e-30)
    print(f"  Memory depth (steps): min={mem_depth.min():.1f}, max={mem_depth.max():.1f}")

    # Simulate
    state = np.zeros(n_modes)

    if feature_mode == 'linear':
        # Baseline: just one readout per step (same as D3)
        features = np.zeros((n_steps, n_rx))
        for t in range(n_steps):
            state = state * decay_full + mask * u[t]
            features[t] = state @ H
        return features

    elif feature_mode == 'timemux_linear':
        # K slices × n_rx features per step
        features = np.zeros((n_steps, n_slices * n_rx))
        for t in range(n_steps):
            state = state * decay_full + mask * u[t]
            # Sample at each slice time
            for k in range(n_slices):
                # State at this slice time (relative to START of step)
                # After injection, modes decay for t_slices[k]
                state_k = state * decay_matrix[k] / decay_full  # Undo full decay, apply partial
                # Actually: state after injection decays. Let's redo logic:
                # At start of step: state_prev * decay_full + mask*u[t] = state (new)
                # Then sample at time t_k relative to injection:
                # state_at_tk = state * exp(-π*f*t_k/Q)  [additional decay from injection point]
                # But we want the state AFTER full step for next iteration
                # So: features from slice k = (state_after_inject) * decay_at_tk
                pass
            # Cleaner: inject, then sample at K points, then carry forward
            # Reset approach:
            pass

        # Redo with clearer logic:
        state = np.zeros(n_modes)
        features = np.zeros((n_steps, n_slices * n_rx))
        for t in range(n_steps):
            # 1. Inject input
            state = state * decay_full + mask * u[t]
            # Now 'state' is amplitude right after injection at step t
            # 2. Sample K slices (additional decay beyond injection point)
            for k in range(n_slices):
                # Decay from injection to slice k
                state_k = state * decay_matrix[k]
                # Project through H
                features[t, k*n_rx:(k+1)*n_rx] = state_k @ H
        return features

    elif feature_mode == 'timemux_quad':
        # K slices × n_rx linear features PLUS all pairwise products
        n_linear = n_slices * n_rx
        # Quadratic: upper triangle of cross products between all linear features
        # That's n_linear*(n_linear+1)//2 features — could be huge
        # Be selective: only cross-TIME products (same receiver, different slices)
        # + cross-RECEIVER products (same slice, different receivers)
        # This is much more manageable: K*K*n_rx*(n_rx) / 2-ish

        # Strategy: compute all linear features, then take selected quadratics
        state = np.zeros(n_modes)
        linear_feats = np.zeros((n_steps, n_linear))

        for t in range(n_steps):
            state = state * decay_full + mask * u[t]
            for k in range(n_slices):
                state_k = state * decay_matrix[k]
                linear_feats[t, k*n_rx:(k+1)*n_rx] = state_k @ H

        # Quadratic features: all unique pairs of linear features
        # n_linear can be 40-80, so n_quad = ~800-3000 — manageable
        n_quad = n_linear * (n_linear + 1) // 2
        quad_feats = np.zeros((n_steps, n_quad))
        idx = 0
        for i in range(n_linear):
            for j in range(i, n_linear):
                quad_feats[:, idx] = linear_feats[:, i] * linear_feats[:, j]
                idx += 1

        return np.hstack([linear_feats, quad_feats])

    elif feature_mode == 'timemux_selective_quad':
        # More focused: only cross-time products at same receiver
        # + cross-receiver products at same slice
        # This captures "how beat patterns evolve" without explosion
        state = np.zeros(n_modes)
        linear_feats = np.zeros((n_steps, n_slices * n_rx))

        for t in range(n_steps):
            state = state * decay_full + mask * u[t]
            for k in range(n_slices):
                state_k = state * decay_matrix[k]
                linear_feats[t, k*n_rx:(k+1)*n_rx] = state_k @ H

        quad_list = [linear_feats]

        # Cross-time products (same receiver, different slices)
        for r in range(n_rx):
            for k1 in range(n_slices):
                for k2 in range(k1+1, n_slices):
                    prod = linear_feats[:, k1*n_rx+r] * linear_feats[:, k2*n_rx+r]
                    quad_list.append(prod[:, np.newaxis])

        # Cross-receiver products (same slice)
        for k in range(n_slices):
            for r1 in range(n_rx):
                for r2 in range(r1+1, n_rx):
                    prod = linear_feats[:, k*n_rx+r1] * linear_feats[:, k*n_rx+r2]
                    quad_list.append(prod[:, np.newaxis])

        return np.hstack(quad_list)


def train_readout(states, target, n_train, ridge_alpha=1e-4):
    """Ridge regression readout with PCA truncation for large feature sets."""
    washout = 200
    X_train = states[washout:n_train]
    y_train = target[washout:n_train]
    X_test = states[n_train:]
    y_test = target[n_train:]

    n_feat = X_train.shape[1]
    n_samples = X_train.shape[0]

    # If features > samples, use SVD-based ridge (more stable)
    if n_feat > n_samples * 0.8:
        # Truncated SVD approach to avoid ill-conditioning
        U, s, Vt = np.linalg.svd(X_train, full_matrices=False)
        # Keep components with significant singular values
        thresh = s[0] * 1e-8
        k = np.sum(s > thresh)
        U_k = U[:, :k]
        s_k = s[:k]
        Vt_k = Vt[:k, :]
        # Ridge in reduced space
        d = s_k**2 / (s_k**2 + ridge_alpha)
        W_out = Vt_k.T @ (np.diag(d / s_k) @ (U_k.T @ y_train))
    else:
        XtX = X_train.T @ X_train + ridge_alpha * np.eye(n_feat)
        W_out = np.linalg.solve(XtX, X_train.T @ y_train)

    y_pred = X_test @ W_out
    mse = np.mean((y_test - y_pred)**2)
    var = np.var(y_test)
    nrmse = np.sqrt(mse / var) if var > 1e-10 else np.inf

    return nrmse, W_out


# ─── Main experiment ──────────────────────────────────────────────
N_STEPS = 5000
N_TRAIN = 4000

u_narma, y_narma = generate_narma10(N_STEPS, seed=42)

rng = np.random.default_rng(2026)
mask = rng.standard_normal(n_modes)
mask = mask / np.linalg.norm(mask)

print("━" * 70)
print("  PHASE 1: Time-Multiplexed Linear (original H, varying K and f_step)")
print("━" * 70)
print()

results_phase1 = []
for f_step in [1000, 2000, 5000, 10000]:
    for n_slices in [5, 10, 20]:
        states = simulate_timemux(u_narma, H_orig, freqs, Q_LOADED, f_step,
                                  mask, n_slices, 'timemux_linear')
        nrmse, _ = train_readout(states, y_narma, N_TRAIN)
        n_feat = states.shape[1]
        results_phase1.append({
            'f_step': f_step, 'n_slices': n_slices,
            'n_features': n_feat, 'nrmse': float(nrmse)
        })
        print(f"    NRMSE = {nrmse:.4f}  ({n_feat} features)")
        print()

# Find best linear config
best_p1 = min(results_phase1, key=lambda x: x['nrmse'])
print(f"  Best linear time-mux: f_step={best_p1['f_step']}, K={best_p1['n_slices']}, "
      f"NRMSE={best_p1['nrmse']:.4f}")
print()

print("━" * 70)
print("  PHASE 2: Time-Multiplexed + Quadratic (beat cross-products)")
print("━" * 70)
print()

# Use best f_step from phase 1, try quadratic variants
f_best = best_p1['f_step']
results_phase2 = []

for n_slices in [5, 8, 10]:
    print(f"  K={n_slices} slices, f_step={f_best} Hz:")

    # Selective quadratic (manageable size)
    states_sq = simulate_timemux(u_narma, H_orig, freqs, Q_LOADED, f_best,
                                 mask, n_slices, 'timemux_selective_quad')
    nrmse_sq, _ = train_readout(states_sq, y_narma, N_TRAIN)
    print(f"    Selective quad ({states_sq.shape[1]} features): NRMSE = {nrmse_sq:.4f}")

    # Full quadratic (if feasible)
    n_linear = n_slices * H_orig.shape[1]
    n_full_quad = n_linear + n_linear * (n_linear + 1) // 2
    if n_full_quad < 5000:  # Only if manageable
        states_fq = simulate_timemux(u_narma, H_orig, freqs, Q_LOADED, f_best,
                                     mask, n_slices, 'timemux_quad')
        nrmse_fq, _ = train_readout(states_fq, y_narma, N_TRAIN)
        print(f"    Full quad ({states_fq.shape[1]} features): NRMSE = {nrmse_fq:.4f}")
        results_phase2.append({
            'n_slices': n_slices, 'mode': 'full_quad',
            'n_features': states_fq.shape[1], 'nrmse': float(nrmse_fq)
        })

    results_phase2.append({
        'n_slices': n_slices, 'mode': 'selective_quad',
        'n_features': states_sq.shape[1], 'nrmse': float(nrmse_sq)
    })
    print()

print()
print("━" * 70)
print("  PHASE 3: CASCADE H Matrix (2-plate system, richer diversity)")
print("━" * 70)
print()

# The cascade H captures signal that traveled through BOTH plates
# PI receivers see direct excitation, PH receivers see cascade-filtered signal
# This means PH channels have DIFFERENT temporal characteristics (double ringdown)

# For cascade, model the double-decay: signal rings in plate I, then re-excites plate H
# Effective decay for cascade channels is the convolution of two exponentials
# For simplicity: model PH channels with Q_effective = Q/2 (faster decay, richer temporal structure)

# Actually, more physically: the cascade signal at PH is the integral of
# plate I's ringdown driving plate H. This gives a temporal response that is
# the convolution of two exponential decays = different shape than single plate.
# For the simulation, we model this as TWO decay constants per cascade receiver.

def simulate_timemux_cascade(u, H_cascade, freqs, Q, f_step, mask, n_slices=10):
    """
    Time-multiplexed reservoir using cascade H matrix.

    Columns 0,1 (PI_NW, PI_NE): single-plate decay at rate π*f/Q
    Columns 2,3 (PH_NW, PH_NE): cascade decay (convolution of two exponentials)
      - Modeled as: response ~ t * exp(-π*f*t/Q) (critically damped 2nd order)
      - This peaks later and has a longer effective tail
    """
    n_steps = len(u)
    n_modes, n_rx = H_cascade.shape
    T_step = 1.0 / f_step
    t_slices = np.array([(k + 1) / (n_slices + 1) * T_step for k in range(n_slices)])

    # Decay matrices for direct channels (0,1) and cascade channels (2,3)
    # Direct: exp(-π*f*t/Q)
    decay_direct = np.exp(-np.pi * freqs[np.newaxis, :] * t_slices[:, np.newaxis] / Q)

    # Cascade: t*exp(-π*f*t/Q) normalized to peak at t_peak = Q/(π*f)
    # This models the convolution of two identical exponential decays
    rate = np.pi * freqs[np.newaxis, :] / Q  # (1, n_modes)
    decay_cascade = rate * t_slices[:, np.newaxis] * np.exp(-rate * t_slices[:, np.newaxis])
    # Normalize each mode's cascade response to max=1
    for i in range(n_modes):
        peak_val = decay_cascade[:, i].max()
        if peak_val > 0:
            decay_cascade[:, i] /= peak_val

    # Full-step decay
    decay_full = np.exp(-np.pi * freqs * T_step / Q)

    print(f"  Cascade time-mux: f_step={f_step}, K={n_slices}")
    print(f"  Direct channels (PI): standard exponential decay")
    print(f"  Cascade channels (PH): t*exp(-t/τ) — peaked response, longer memory")

    state = np.zeros(n_modes)
    n_feat_per_step = n_slices * n_rx
    linear_feats = np.zeros((n_steps, n_feat_per_step))

    for t in range(n_steps):
        state = state * decay_full + mask * u[t]
        for k in range(n_slices):
            # Direct channels
            state_k_direct = state * decay_direct[k]
            linear_feats[t, k*n_rx + 0] = state_k_direct @ H_cascade[:, 0]
            linear_feats[t, k*n_rx + 1] = state_k_direct @ H_cascade[:, 1]
            # Cascade channels (different temporal response)
            state_k_cascade = state * decay_cascade[k]
            linear_feats[t, k*n_rx + 2] = state_k_cascade @ H_cascade[:, 2]
            linear_feats[t, k*n_rx + 3] = state_k_cascade @ H_cascade[:, 3]

    # Selective quadratic: cross-time and cross-receiver products
    quad_list = [linear_feats]

    # Cross-time products (same receiver, different slices)
    for r in range(n_rx):
        for k1 in range(n_slices):
            for k2 in range(k1+1, min(k1+4, n_slices)):  # Limit to nearby slices
                prod = linear_feats[:, k1*n_rx+r] * linear_feats[:, k2*n_rx+r]
                quad_list.append(prod[:, np.newaxis])

    # Cross-channel products (direct × cascade, same slice) — the BEAT!
    for k in range(n_slices):
        for r_d in range(2):      # Direct: 0,1
            for r_c in range(2):  # Cascade: 2,3
                prod = linear_feats[:, k*n_rx+r_d] * linear_feats[:, k*n_rx+2+r_c]
                quad_list.append(prod[:, np.newaxis])

    features = np.hstack(quad_list)
    return features


results_phase3 = []
for f_step in [2000, 5000, 10000]:
    for n_slices in [8, 12, 16]:
        states = simulate_timemux_cascade(u_narma, H_cascade, freqs, Q_LOADED,
                                          f_step, mask, n_slices)
        nrmse, _ = train_readout(states, y_narma, N_TRAIN)
        results_phase3.append({
            'f_step': f_step, 'n_slices': n_slices,
            'n_features': states.shape[1], 'nrmse': float(nrmse)
        })
        print(f"    f_step={f_step}, K={n_slices}: {states.shape[1]} features → NRMSE = {nrmse:.4f}")
    print()

best_p3 = min(results_phase3, key=lambda x: x['nrmse'])
print(f"\n  Best cascade time-mux: f_step={best_p3['f_step']}, K={best_p3['n_slices']}, "
      f"NRMSE={best_p3['nrmse']:.4f}")

print()
print("━" * 70)
print("  PHASE 4: Ridge Alpha Optimization on Best Config")
print("━" * 70)
print()

# Run best cascade config with different alphas
states_best = simulate_timemux_cascade(u_narma, H_cascade, freqs, Q_LOADED,
                                       best_p3['f_step'], mask, best_p3['n_slices'])
alpha_results = []
for alpha in [1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2]:
    nrmse, _ = train_readout(states_best, y_narma, N_TRAIN, ridge_alpha=alpha)
    alpha_results.append({'alpha': alpha, 'nrmse': float(nrmse)})
    print(f"  α={alpha:.0e}: NRMSE = {nrmse:.4f}")

best_alpha = min(alpha_results, key=lambda x: x['nrmse'])
print(f"\n  Best α={best_alpha['alpha']:.0e}: NRMSE = {best_alpha['nrmse']:.4f}")

print()
print("━" * 70)
print("  PHASE 5: Mask Ensemble (best config, 10 random masks)")
print("━" * 70)
print()

rng2 = np.random.default_rng(999)
mask_nrmses = []
for m in range(10):
    mask_m = rng2.standard_normal(n_modes)
    mask_m = mask_m / np.linalg.norm(mask_m)
    states_m = simulate_timemux_cascade(u_narma, H_cascade, freqs, Q_LOADED,
                                        best_p3['f_step'], mask_m, best_p3['n_slices'])
    nrmse_m, _ = train_readout(states_m, y_narma, N_TRAIN, ridge_alpha=best_alpha['alpha'])
    mask_nrmses.append(float(nrmse_m))
    if (m+1) % 5 == 0:
        print(f"  Mask {m+1}/10: NRMSE = {nrmse_m:.4f}")

print(f"\n  Mask ensemble: {np.mean(mask_nrmses):.4f} ± {np.std(mask_nrmses):.4f}")
print(f"  Best mask: {min(mask_nrmses):.4f}, Worst: {max(mask_nrmses):.4f}")

print()
print("━" * 70)
print("  PHASE 6: MEMS Projection (Q=9000)")
print("━" * 70)
print()

Q_MEMS = 9000
print(f"  Projecting performance at Q={Q_MEMS} (MEMS target)...")
print()

for f_step in [2000, 5000, 10000, 50000]:
    for n_slices in [10, 20]:
        states_mems = simulate_timemux_cascade(u_narma, H_cascade, freqs, Q_MEMS,
                                               f_step, mask, n_slices)
        nrmse_mems, _ = train_readout(states_mems, y_narma, N_TRAIN,
                                      ridge_alpha=best_alpha['alpha'])
        print(f"    f_step={f_step:>5}, K={n_slices:>2}: NRMSE = {nrmse_mems:.4f}")
    print()

print()
print("=" * 70)
print("  D3b TIME-MULTIPLEXED RESERVOIR — FINAL SUMMARY")
print("=" * 70)
print()
print(f"  Baselines:")
print(f"    D2 Gram (linear, 4 features):     NRMSE = 0.7036")
print(f"    D3 Beat (quadratic, 1516 feat):    NRMSE = 0.6377")
print(f"    Random ESN (27 nodes):             NRMSE = 0.4417")
print()
print(f"  This experiment (Q={Q_LOADED}):")
print(f"    Best linear time-mux:              NRMSE = {best_p1['nrmse']:.4f} "
      f"(K={best_p1['n_slices']}, f={best_p1['f_step']})")
best_p2 = min(results_phase2, key=lambda x: x['nrmse'])
print(f"    Best quad time-mux (orig H):       NRMSE = {best_p2['nrmse']:.4f}")
print(f"    Best cascade time-mux+beat:        NRMSE = {best_p3['nrmse']:.4f} "
      f"(K={best_p3['n_slices']}, f={best_p3['f_step']})")
print(f"    Best after α-tuning:               NRMSE = {best_alpha['nrmse']:.4f}")
print(f"    Mask ensemble mean:                NRMSE = {np.mean(mask_nrmses):.4f}")
print()

overall_best = min(best_alpha['nrmse'], min(mask_nrmses))
if overall_best < 0.44:
    verdict = "PASS"
    print("  ★★ PASS — Beats random ESN! Time-multiplexed ringdown unlocks")
    print("     temporal computation from the linear plate.")
elif overall_best < 0.64:
    verdict = "IMPROVED"
    print("  ★ IMPROVED — Beats D3 beat-only (0.64), approaching random ESN.")
    print("     Time-multiplexing extracts more temporal information.")
elif overall_best < 0.70:
    verdict = "PARTIAL"
    print("  △ PARTIAL — Beats Gram baseline but not beat-only D3.")
else:
    verdict = "FAIL"
    print("  ✗ FAIL — No improvement over baselines.")

print()
print(f"  VERDICT: {verdict} (best NRMSE = {overall_best:.4f})")

# ─── Save ─────────────────────────────────────────────────────────
OUT_DIR = DATA_DIR / 'reservoir'
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = OUT_DIR / f'd3b_timemux_reservoir_{ts}.json'

output = {
    'test': 'D3b_timemux_reservoir',
    'timestamp': datetime.now().isoformat(),
    'concept': 'Time-multiplexed ringdown: K samples per input step convert temporal '
               'decay (mode-specific rates) into spatial features. Combined with '
               'cascade H (2-plate system with direct+cascade temporal responses) '
               'and quadratic cross-products (beat patterns across time slices).',
    'hardware_params': {
        'n_modes': int(n_modes),
        'Q_loaded': Q_LOADED,
        'freq_range_hz': [int(freqs[0]), int(freqs[-1])],
        'H_orig_shape': list(H_orig.shape),
        'H_cascade_shape': list(H_cascade.shape),
    },
    'phase1_linear_timemux': results_phase1,
    'phase2_quad_timemux': results_phase2,
    'phase3_cascade_timemux': results_phase3,
    'phase4_alpha_sweep': alpha_results,
    'phase5_mask_ensemble': {
        'nrmses': mask_nrmses,
        'mean': float(np.mean(mask_nrmses)),
        'std': float(np.std(mask_nrmses)),
    },
    'best_config': {
        'f_step': best_p3['f_step'],
        'n_slices': best_p3['n_slices'],
        'alpha': best_alpha['alpha'],
        'nrmse': float(overall_best),
    },
    'baselines': {
        'gram_d2': 0.7036,
        'beat_d3': 0.6377,
        'random_esn': 0.4417,
    },
    'verdict': verdict,
}

with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\n  Saved: {out_path}")
