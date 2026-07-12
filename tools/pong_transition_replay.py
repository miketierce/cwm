#!/usr/bin/env python3
"""
Pong transition replay from saved CWM captures.
Uses the enrollment feature matrix to test trajectory prediction:
  1. Build empirical transition table from enrolled states
  2. Given a start state, identify it via CWM recall (KNN on features)
  3. Walk stored successors to predict landing
  4. Compare: glass features vs wire-only vs random projection

This is the offline version of pong_trajectory_recall.py —
no hardware needed, uses saved recall_enroll npz.

Usage: python3 tools/pong_transition_replay.py [npz]
"""
import numpy as np, json, sys, glob, time
from pathlib import Path

p = sys.argv[1] if len(sys.argv) > 1 else sorted(
    glob.glob('data/results/pong/recall_enroll_*.npz'))[-1]
d = np.load(p)
X = d['X']; L = d['L']; R = int(d['repeats']); PADH = int(d['padh'])
driven = d['driven']; NW = int(d['nw']); naxes = int(d['naxes'])
xs = d['xs']; ys = d['ys']; vx = d['vx']; vy = d['vy']; land = d['land']
Fd = X.shape[1]; axis_block = naxes * NW
X = X / (X.mean(1, keepdims=True) + 1e-9)
rng = np.random.default_rng(42)

CW, CHt = 8, 8  # court width, height (from recall_enroll_save.py)
print(f"Loaded {p}: X{X.shape}, states: xs∈[{xs.min()},{xs.max()}], "
      f"ys∈[{ys.min()},{ys.max()}], vx∈{set(vx.tolist())}, vy∈{set(vy.tolist())}")

t0 = time.time()
results = {'source': str(p)}


# ============================================================
# 1. Build state space and transition table
# ============================================================
def pong_step(x, y, svx, svy):
    """One Pong step: advance ball, bounce off walls."""
    nx, ny = x + svx, y + svy
    if ny < 0: ny = -ny; svy = -svy
    if ny > CHt - 1: ny = 2 * (CHt - 1) - ny; svy = -svy
    if nx < 0: nx = -nx; svx = -svx
    return nx, ny, svx, svy


def landing_from(x, y, svx, svy):
    """Roll out until ball reaches far wall."""
    for _ in range(50):
        x, y, svx, svy = pong_step(x, y, svx, svy)
        if x >= CW - 1:
            return int(round(np.clip(y, 0, CHt - 1)))
    return (CHt - 1) // 2


# Unique states and their indices
state_tuples = list(zip(xs.tolist(), ys.tolist(), vx.tolist(), vy.tolist()))
unique_states = sorted(set(state_tuples))
state_to_idx = {s: i for i, s in enumerate(unique_states)}
Ns = len(unique_states)
print(f"Unique states: {Ns}")

# Build transition table: state -> next state (one Pong step)
transitions = {}
for s in unique_states:
    ns = pong_step(*s)
    # Clamp to nearest known state
    ns_clamped = min(unique_states, key=lambda u: sum((a-b)**2 for a, b in zip(u, ns)))
    transitions[s] = ns_clamped

# Build per-state centroids from enrolled features
# Average over repeats for each unique state
state_centroids = np.zeros((Ns, Fd))
state_counts = np.zeros(Ns)
state_landing = np.zeros(Ns, dtype=int)
for i in range(len(X)):
    si = state_to_idx[state_tuples[i]]
    state_centroids[si] += X[i]
    state_counts[si] += 1
    state_landing[si] = L[i]
state_centroids /= (state_counts[:, None] + 1e-9)


# ============================================================
# 2. Trajectory recall: identify start, walk transitions
# ============================================================
def recall_trajectory(query_feats, centroids, sigma=0.0):
    """Given a query feature vector, find nearest state centroid,
    then walk transitions to predict landing."""
    rr = np.random.default_rng(99)
    q = query_feats.copy()
    if sigma > 0:
        q = q + rr.standard_normal(len(q)) * sigma

    # Normalize
    mu = centroids.mean(0); sd = centroids.std(0); sd[sd < 1e-9] = 1
    qn = (q - mu) / sd
    cn = (centroids - mu) / sd

    # Nearest centroid
    dists = ((cn - qn) ** 2).sum(1)
    best = np.argmin(dists)
    start_state = unique_states[best]

    # Walk transitions to landing
    s = start_state
    for step in range(50):
        if s[0] >= CW - 1:
            return int(round(np.clip(s[1], 0, CHt - 1))), best
        s = transitions[s]

    return (CHt - 1) // 2, best


# ============================================================
# 3. Evaluate: LORO trajectory recall
# ============================================================
print("\n" + "=" * 60)
print("TRAJECTORY RECALL (LORO, walk stored transitions)")
print("=" * 60)

sig_grid = [0, 0.5, 1.0, 1.5, 2.0, 3.0]

# Build LORO centroids (leave one repeat out)
def loro_trajectory(feat_fn, sigma_grid):
    """Leave-one-repeat-out trajectory recall."""
    accs = []
    for sig in sigma_grid:
        hit = tot = 0
        rr = np.random.default_rng(99)
        for rt in range(R):
            te = [i for i in range(len(X)) if i % R == rt]
            tr = [i for i in range(len(X)) if i % R != rt]

            # Build centroids from training fold
            cents = np.zeros((Ns, feat_fn(X[0:1]).shape[1]))
            cnts = np.zeros(Ns)
            for i in tr:
                si = state_to_idx[state_tuples[i]]
                cents[si] += feat_fn(X[i:i+1])[0]
                cnts[si] += 1
            cents /= (cnts[:, None] + 1e-9)

            mu = cents.mean(0); sd = cents.std(0); sd[sd < 1e-9] = 1
            cn = (cents - mu) / sd

            for i in te:
                q = feat_fn(X[i:i+1])[0]
                if sig > 0:
                    q = q + rr.standard_normal(len(q)) * sig
                qn = (q - mu) / sd
                dists = ((cn - qn) ** 2).sum(1)
                best = np.argmin(dists)
                s = unique_states[best]

                # Walk transitions
                pred_land = (CHt - 1) // 2
                for step in range(50):
                    if s[0] >= CW - 1:
                        pred_land = int(round(np.clip(s[1], 0, CHt - 1)))
                        break
                    s = transitions[s]

                true_land = L[i]
                hit += abs(pred_land - true_land) <= PADH // 2
                tot += 1
        accs.append(hit / tot * 100)
    return accs

# Feature extractors
glass_fn = lambda x: x
wire_fn = lambda x: x[:, driven]
RP = rng.standard_normal((len(driven), Fd)) / np.sqrt(len(driven))
wire_rp_fn = lambda x: x[:, driven] @ RP

# Partial query: hide vx, vy
mask_pq = np.ones(Fd); mask_pq[2*NW:4*NW] = 0
glass_pq_fn = lambda x: x * mask_pq

print("\nMethod           " + "  ".join(f"σ={s}" for s in sig_grid))

for name, fn in [('glass_full', glass_fn),
                 ('wire_only', wire_fn),
                 ('wire_rp240', wire_rp_fn),
                 ('glass_partial', glass_pq_fn)]:
    accs = loro_trajectory(fn, sig_grid)
    results[f'trajectory_{name}'] = [round(a, 2) for a in accs]
    print(f"  {name:16s} " + "  ".join(f"{a:5.1f}" for a in accs))
    print(f"    [{time.time() - t0:.0f}s]")

# ============================================================
# 4. Multi-step horizon test: how many steps ahead can we predict?
# ============================================================
print("\n" + "=" * 60)
print("MULTI-STEP HORIZON (sigma=1.0, glass_full)")
print("=" * 60)

# For each test sample, predict N steps ahead
horizons = [1, 2, 3, 5, 8, 12]
horizon_results = {}

for H in horizons:
    hit = tot = 0
    for rt in range(R):
        te = [i for i in range(len(X)) if i % R == rt]
        tr = [i for i in range(len(X)) if i % R != rt]

        cents = np.zeros((Ns, Fd)); cnts = np.zeros(Ns)
        for i in tr:
            si = state_to_idx[state_tuples[i]]
            cents[si] += X[i]; cnts[si] += 1
        cents /= (cnts[:, None] + 1e-9)
        mu = cents.mean(0); sd = cents.std(0); sd[sd < 1e-9] = 1
        cn = (cents - mu) / sd

        for i in te:
            q = X[i] + rng.standard_normal(Fd) * 1.0
            qn = (q - mu) / sd
            # Identify start
            best = np.argmin(((cn - qn) ** 2).sum(1))
            s = unique_states[best]

            # Walk H steps
            for _ in range(H):
                s = transitions[s]

            # Actual state H steps ahead
            true_s = state_tuples[i]
            for _ in range(H):
                true_s = pong_step(*true_s)
                true_s = min(unique_states, key=lambda u: sum((a-b)**2 for a, b in zip(u, true_s)))

            # Compare position
            hit += (s == true_s)
            tot += 1

    acc = hit / tot * 100
    horizon_results[f'{H}_step'] = round(acc, 2)
    print(f"  {H:2d}-step ahead: {acc:5.1f}%")

results['multi_step_horizon'] = horizon_results

# ============================================================
# Save
# ============================================================
out = Path(p).with_name('transition_replay_' + Path(p).stem.split('_')[-1] + '.json')
json.dump(results, open(out, 'w'), indent=1)
print(f"\nSaved to {out}")
print(f"Total time: {time.time() - t0:.0f}s")
