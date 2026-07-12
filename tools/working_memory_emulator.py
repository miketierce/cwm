#!/usr/bin/env python3
"""
Classical phononic working memory emulator (PR #5).

Tests whether saved CWM features can support a working-memory cycle:
  ADDRESS → READ → MODIFY → WRITE-BACK → RE-READ

Since we don't have hardware write capability, this emulates the cycle:
  1. ADDRESS: select a frequency slot (subset of features)
  2. READ: recall stored state from that slot via KNN
  3. MODIFY: perturb the recalled features (simulate write)
  4. WRITE-BACK: update the stored centroid
  5. RE-READ: verify the modified state is retrievable

Also tests:
  - Slot capacity: how many independent "memory slots" can be addressed?
  - Retention: does repeated read degrade the slot?
  - Interference: does writing to slot A corrupt slot B?

Usage: python3 tools/working_memory_emulator.py [npz]
"""
import numpy as np, json, sys, glob, time
from pathlib import Path

p = sys.argv[1] if len(sys.argv) > 1 else sorted(
    glob.glob('data/results/pong/recall_enroll_*.npz'))[-1]
d = np.load(p)
X = d['X']; L = d['L']; R = int(d['repeats']); PADH = int(d['padh'])
driven = d['driven']; NW = int(d['nw']); naxes = int(d['naxes'])
xs = d['xs']; ys = d['ys']; vx = d['vx']; vy = d['vy']
Fd = X.shape[1]; axis_block = naxes * NW
X = X / (X.mean(1, keepdims=True) + 1e-9)
rng = np.random.default_rng(42)

print(f"Loaded {p}: X{X.shape}")
results = {'source': str(p)}
t0 = time.time()


# ==============================================================
# Build state centroids (average over repeats)
# ==============================================================
state_tuples = list(zip(xs.tolist(), ys.tolist(), vx.tolist(), vy.tolist()))
unique_states = sorted(set(state_tuples))
state_to_idx = {s: i for i, s in enumerate(unique_states)}
Ns = len(unique_states)

centroids = np.zeros((Ns, Fd))
counts = np.zeros(Ns)
for i in range(len(X)):
    si = state_to_idx[state_tuples[i]]
    centroids[si] += X[i]
    counts[si] += 1
centroids /= (counts[:, None] + 1e-9)

# Per-state variance (noise floor for reads)
state_var = np.zeros((Ns, Fd))
for i in range(len(X)):
    si = state_to_idx[state_tuples[i]]
    state_var[si] += (X[i] - centroids[si]) ** 2
state_var /= (counts[:, None] - 1 + 1e-9)
state_std = np.sqrt(state_var.mean(0))  # mean std per feature

print(f"States: {Ns}, Repeats per state: {R}")


# ==============================================================
# 1. MEMORY SLOT DEFINITION
# ==============================================================
print("\n" + "=" * 60)
print("1. MEMORY SLOT DEFINITIONS")
print("=" * 60)

# Define memory slots as groups of states
# Slot = a subset of the state space that can be independently addressed
# We'll use landing (L) as the natural "address" — 8 possible landings
n_landings = len(np.unique(L))
print(f"  Natural address space: {n_landings} landing values")

# Map states to their landing values
state_landing = np.zeros(Ns, dtype=int)
for i in range(len(X)):
    si = state_to_idx[state_tuples[i]]
    state_landing[si] = L[i]


# ==============================================================
# 2. ADDRESS-READ CYCLE
# ==============================================================
print("\n" + "=" * 60)
print("2. ADDRESS → READ (content-addressable retrieval)")
print("=" * 60)


def read_slot(query, memory, sigma=0.0):
    """Read: find nearest centroid to query, return its state index."""
    q = query.copy()
    if sigma > 0:
        q += rng.standard_normal(len(q)) * sigma
    mu = memory.mean(0); sd = memory.std(0); sd[sd < 1e-9] = 1
    qn = (q - mu) / sd; mn = (memory - mu) / sd
    dists = ((mn - qn) ** 2).sum(1)
    return np.argmin(dists)


# Test read accuracy at various noise levels
sig_grid = [0, 0.5, 1.0, 1.5, 2.0, 3.0]
read_results = {}

for sig in sig_grid:
    correct = 0; total = 0
    for i in range(len(X)):
        si_true = state_to_idx[state_tuples[i]]
        si_read = read_slot(X[i], centroids, sigma=sig)
        # Count as correct if same landing
        correct += (state_landing[si_read] == L[i])
        total += 1
    acc = correct / total * 100
    read_results[f'sigma_{sig}'] = round(acc, 2)
    print(f"  σ={sig:3.1f}: landing match = {acc:.1f}%")

results['address_read'] = read_results


# ==============================================================
# 3. MODIFY → WRITE-BACK → RE-READ CYCLE
# ==============================================================
print("\n" + "=" * 60)
print("3. MODIFY → WRITE-BACK → RE-READ")
print("=" * 60)

# Simulate a working-memory update:
# 1. Read state from memory
# 2. Modify it (e.g., shift landing by ±1)
# 3. Write modified centroid back
# 4. Re-read and verify

modify_strengths = [0.1, 0.25, 0.5, 1.0, 2.0]
write_results = {}

for strength in modify_strengths:
    memory = centroids.copy()
    n_written = 0; n_read_back = 0; n_correct_original = 0

    # Pick 20 random states to modify
    test_states = rng.choice(Ns, min(20, Ns), replace=False)

    for si in test_states:
        # Read original
        original_read = read_slot(centroids[si], memory)
        if original_read == si:
            n_correct_original += 1

        # Modify: shift the centroid toward a neighboring state
        target_si = (si + 1) % Ns
        direction = centroids[target_si] - centroids[si]
        direction /= (np.linalg.norm(direction) + 1e-9)
        modification = direction * strength * np.linalg.norm(state_std)

        # Write back
        memory[si] = centroids[si] + modification
        n_written += 1

        # Re-read: can we retrieve the modified state?
        re_read = read_slot(memory[si], memory)
        if re_read == si:
            n_read_back += 1

    write_results[f'strength_{strength}'] = {
        'n_tested': len(test_states),
        'original_read_acc': round(n_correct_original / len(test_states) * 100, 1),
        'write_back_acc': round(n_read_back / len(test_states) * 100, 1),
    }
    print(f"  modify_strength={strength:.2f}: "
          f"original_read={n_correct_original}/{len(test_states)} "
          f"write_back={n_read_back}/{len(test_states)}")

results['modify_write_read'] = write_results


# ==============================================================
# 4. INTERFERENCE TEST: does writing to slot A corrupt slot B?
# ==============================================================
print("\n" + "=" * 60)
print("4. INTERFERENCE: write to A, check B")
print("=" * 60)

interference_results = {}
for n_writes in [1, 5, 10, 20, 50]:
    memory = centroids.copy()

    # Write to random slots
    write_targets = rng.choice(Ns, n_writes, replace=False)
    for si in write_targets:
        noise = rng.standard_normal(Fd) * np.linalg.norm(state_std) * 0.5
        memory[si] = centroids[si] + noise

    # Check unmodified slots
    untouched = [s for s in range(Ns) if s not in write_targets]
    if len(untouched) == 0:
        continue

    correct = 0
    for si in untouched:
        ri = read_slot(centroids[si], memory)
        correct += (ri == si)
    acc = correct / len(untouched) * 100

    interference_results[f'{n_writes}_writes'] = {
        'n_untouched': len(untouched),
        'intact_acc': round(acc, 1),
    }
    print(f"  After {n_writes:2d} writes: "
          f"{correct}/{len(untouched)} untouched slots intact ({acc:.1f}%)")

results['interference'] = interference_results


# ==============================================================
# 5. SLOT CAPACITY: max distinguishable states
# ==============================================================
print("\n" + "=" * 60)
print("5. SLOT CAPACITY (max distinguishable states at σ=1.0)")
print("=" * 60)

# Progressively merge nearest centroids, measure recall accuracy
for n_slots in [256, 128, 64, 32, 16, 8, 4]:
    if n_slots > Ns:
        continue

    # K-means-like grouping by nearest centroid
    # Simple approach: take every k-th state
    step = max(1, Ns // n_slots)
    slot_centroids = centroids[::step][:n_slots]

    # Assign all states to nearest slot
    assignments = np.zeros(Ns, dtype=int)
    for si in range(Ns):
        dists = ((slot_centroids - centroids[si]) ** 2).sum(1)
        assignments[si] = np.argmin(dists)

    # Test: can we read the correct SLOT from noisy queries?
    correct = 0; total = 0
    for i in range(len(X)):
        si_true = state_to_idx[state_tuples[i]]
        slot_true = assignments[si_true]

        q = X[i] + rng.standard_normal(Fd) * 1.0
        mu = slot_centroids.mean(0); sd = slot_centroids.std(0); sd[sd < 1e-9] = 1
        qn = (q - mu) / sd; sn = (slot_centroids - mu) / sd
        slot_read = np.argmin(((sn - qn) ** 2).sum(1))

        correct += (slot_read == slot_true)
        total += 1

    acc = correct / total * 100
    print(f"  {n_slots:3d} slots: {acc:.1f}% correct at σ=1.0")
    results.setdefault('slot_capacity', {})[f'{n_slots}_slots'] = round(acc, 1)


# ==============================================================
# 6. RETENTION: repeated reads without refresh
# ==============================================================
print("\n" + "=" * 60)
print("6. RETENTION (repeated noisy reads, no refresh)")
print("=" * 60)

# Simulate: read a slot N times with noise, each time using
# the previous read result as the query (drift test)
n_trials = 50
max_reads = 20

for sig in [0.5, 1.0, 2.0]:
    survival = np.zeros(max_reads)
    for trial in range(n_trials):
        si = rng.integers(0, Ns)
        query = centroids[si].copy()
        for step in range(max_reads):
            query = query + rng.standard_normal(Fd) * sig
            read_si = read_slot(query, centroids)
            if state_landing[read_si] == state_landing[si]:
                survival[step] += 1
            # Use the retrieved centroid for next read (auto-correction)
            query = centroids[read_si].copy()

    survival = survival / n_trials * 100
    print(f"  σ={sig}: reads 1/5/10/20 → "
          f"{survival[0]:.0f}/{survival[4]:.0f}/{survival[9]:.0f}/{survival[19]:.0f}%")
    results.setdefault('retention', {})[f'sigma_{sig}'] = [round(s, 1) for s in survival.tolist()]


# ==============================================================
# Save
# ==============================================================
out = Path('data/results/working_memory_emulator.json')
json.dump(results, open(out, 'w'), indent=1)
print(f"\n{'=' * 60}")
print(f"Saved to {out}")
print(f"Total time: {time.time() - t0:.0f}s")
