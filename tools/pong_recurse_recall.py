#!/usr/bin/env python3
"""
Pong RECURSIVE recall — the discrete path integral over the deck
================================================================

User's idea (2026-06-21): "we are pattern matching every possible future state
AND the possible future states of those states, assigning probabilities."

Single-step prediction-by-recall (pong_predict_recall.py, validated 81%) stores
each card's *final* landing — the deck is a static lookup table. This tool stores
only each card's *immediate successor* (a local edge) and ROLLS THE DECK FORWARD
by recall. Two roll-forward modes:

  GREEDY    — query → nearest card c0 → follow its stored edge c0→c1→c2→… → landing.
              One glass match, then walk deterministic edges. (Should ≈ one-shot
              lookup: a consistency check that the edge-walk reproduces the future.)

  PATH-INTEGRAL — query → SOFTMAX similarity over ALL cards = p0, a probability
              distribution (the |amplitude|→probability step). Propagate the whole
              distribution through the transition matrix T for K steps:
                  p_{t+1} = p_t · T ,   landing_dist += p_t · L
              The predicted landing = argmax of the summed landing distribution.
              This is literally a discrete sum over paths through the deck — every
              future, and the futures of those futures, weighted by match.

The scientific question (honest, falsifiable):
  Under a NOISY/partial query, does summing over paths (PATH-INTEGRAL) degrade
  more gracefully than committing to one path (GREEDY)? If the distribution
  reinforces the true landing region while wrong matches wash out, that is
  "summing over histories denoises" — the path-integral payoff, measured.
  Always vs the WIRE baseline (driven bins only).

═══ PHASE NOTE (keep in mind, per 2026-06-21 honesty review) ═══
This sum is CLASSICAL: p0 ≥ 0 and the edge weights in T are real & non-negative,
so contributions only ADD — a Markov/probability propagation, never cancellation.
A genuine path integral sums COMPLEX amplitudes e^{iS}; wrong paths CANCEL. Our
recall matches on magnitude (energy) and throws phase away, so we cannot cancel.
That is the honest "energy not phase" gap — made concrete here at the TRANSITION
step. The hook `EDGE_WEIGHT` below is where a complex, phase-bearing weight would
multiply in. E9 (2026-06-03) already proved the NCO can drive two coherent tones
at 180° and cancel a mode to 99% depth — so the cancelling ingredient is a
MEASURED capability we have not yet wired into recall, not a missing one.

Replays the captured glass fingerprints from pong_predict_recall.py (no hardware
needed — same physics, new analysis):
  python3 tools/pong_recurse_recall.py            # newest capture
  python3 tools/pong_recurse_recall.py --npz data/results/pong/pong_predict_data_*.npz
"""
import numpy as np
import json, math, argparse, glob
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='Pong recursive / path-integral recall')
ap.add_argument('--npz', type=str, default=None, help='captured glass data (default: newest)')
ap.add_argument('--beta', type=float, default=4.0, help='softmax sharpness for query distribution')
ap.add_argument('--ksteps', type=int, default=40, help='max roll-forward steps (== landing() cap)')
ap.add_argument('--seed', type=int, default=0)
args = ap.parse_args()

COURT_W, COURT_H = 8, 8
PADDLE_H = 3
N_WIN = 7                      # window bins per axis (must match capture)
AXES = ['x', 'y', 'vx', 'vy']  # capture order
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = Path('data/results/pong'); OUT.mkdir(parents=True, exist_ok=True)

print("=" * 72)
print("  PONG RECURSIVE RECALL — rolling the deck forward (discrete path integral)")
print("  greedy walk  vs  path-integral (sum over paths)  vs  one-shot lookup")
print("=" * 72)

# ─── Load captured glass fingerprints ────────────────────────────────────
npz_path = args.npz or (sorted(glob.glob('data/results/pong/pong_predict_data_*.npz'))[-1])
d = np.load(npz_path)
X = d['X']                                   # (N*R, F) drift-normalized at capture? no — raw; we re-norm
xs, ys, vxs, vys = d['xs'], d['ys'], d['vxs'], d['vys']
land_row = d['land'].astype(int)             # stored landing per row
grp = d['grp'].astype(int)                   # state index per row
F = X.shape[1]
R = int(round(len(grp) / (grp.max() + 1)))
N = grp.max() + 1
X = X / (X.mean(1, keepdims=True) + 1e-9)     # per-capture mean normalize (drift cancel)
print(f"\n[1] Replaying {Path(npz_path).name}: {N} states × {R} repeats, {F} features")

# wire baseline = the directly-driven center bins (reconstruct capture layout)
DRIVEN = [i * N_WIN + N_WIN // 2 for i in range(len(AXES))]   # x,y,vx,vy centers
n_census = F - len(AXES) * N_WIN
print(f"    wire cols (driven bins): {DRIVEN}   |   census modes: {n_census}")

# ─── Rebuild the deck dynamics (state → successor, or absorb → landing) ───
states = [(x, y, vx, vy) for x in range(COURT_W) for y in range(COURT_H)
          for vx in (-1, 1) for vy in (-1, 1)]
assert len(states) == N, f"state count {len(states)} != {N}"
idx_of = {s: i for i, s in enumerate(states)}


def landing(bx, by, vx, vy):
    """Full forward-sim → paddle-plane y (the stored 'future'; matches predict tool)."""
    x, y = float(bx), float(by)
    for _ in range(40):
        x += vx; y += vy
        if y < 0: y = -y; vy = -vy
        if y > COURT_H - 1: y = 2 * (COURT_H - 1) - y; vy = -vy
        if x < 0: x = -x; vx = -vx
        if x >= COURT_W - 1: return int(round(np.clip(y, 0, COURT_H - 1)))
    return (COURT_H - 1) // 2


def step_absorb(s):
    """One physics tick. Returns (successor_state, None) or (None, landing_row) if absorbed."""
    x, y, vx, vy = s
    nx, ny, nvx, nvy = x + vx, y + vy, vx, vy
    if ny < 0: ny = -ny; nvy = -nvy
    if ny > COURT_H - 1: ny = 2 * (COURT_H - 1) - ny; nvy = -nvy
    if nx < 0: nx = -nx; nvx = -nvx
    ny = int(round(np.clip(ny, 0, COURT_H - 1)))
    if nx >= COURT_W - 1:
        return None, ny
    return (nx, ny, nvx, nvy), None


land_oneshot = np.array([landing(*s) for s in states])          # the stored final landing
succ = np.full(N, -1, int)                                       # successor state index, -1 = absorbing
land_edge = np.full(N, -1, int)                                  # landing row if absorbing
for i, s in enumerate(states):
    ns, lr = step_absorb(s)
    if ns is None:
        land_edge[i] = lr
    else:
        succ[i] = idx_of[ns]

# Transition matrix T (move mass) and absorb matrix L (drain mass → landing rows).
# EDGE_WEIGHT: real & non-negative here (classical Markov sum). A genuine path
# integral would make this a COMPLEX amplitude (E9 coherent-phase drive) so paths
# can CANCEL — see PHASE NOTE at top. Marked so the hook is obvious.
EDGE_WEIGHT = 1.0
T = np.zeros((N, N)); L = np.zeros((N, COURT_H))
for i in range(N):
    if succ[i] < 0:
        L[i, land_edge[i]] = 1.0
    else:
        T[i, succ[i]] = EDGE_WEIGHT

# sanity: walking edges greedily must reproduce the one-shot landing
def walk(i):
    for _ in range(args.ksteps):
        if succ[i] < 0:
            return land_edge[i]
        i = succ[i]
    return (COURT_H - 1) // 2
walk_match = np.mean([walk(i) == land_oneshot[i] for i in range(N)]) * 100
print(f"[2] Deck dynamics: edge-walk reproduces stored landing on {walk_match:.0f}% of cards "
      f"({'consistent' if walk_match > 99 else 'CHECK'})")


def hit(pred, true):
    return abs(int(round(pred)) - int(true)) <= PADDLE_H // 2

# ─── Predictors (leave-one-repeat-out; query = held-out repeat) ──────────
def per_state_centroids(tr_rows, cols):
    """Mean fingerprint per state over training repeats, standardized."""
    Xs = X[np.ix_(tr_rows, cols)]
    mu = Xs.mean(0); sd = Xs.std(0); sd[sd < 1e-9] = 1
    A = (Xs - mu) / sd
    g = grp[tr_rows]
    C = np.zeros((N, len(cols)))
    for c in range(N):
        m = g == c
        C[c] = A[m].mean(0) if m.any() else 0.0
    return C, mu, sd


def query_dist(q_std, C, beta):
    """Softmax-over-deck similarity = p0 (the |amplitude|→probability step)."""
    dsq = ((C - q_std) ** 2).sum(1)
    z = -beta * (dsq - dsq.min()) / (dsq.std() + 1e-9)
    p = np.exp(z - z.max()); return p / p.sum()


def propagate(p0):
    """Roll the whole distribution forward through the deck: discrete sum over paths."""
    p = p0.copy(); land_dist = np.zeros(COURT_H)
    for _ in range(args.ksteps):
        land_dist += p @ L          # drain mass sitting on absorbing cards
        p = p @ T                   # move the rest (absorbed mass dies: T row = 0)
        if p.sum() < 1e-9:
            break
    land_dist[(COURT_H - 1) // 2] += p.sum()   # any non-absorbed remainder → middle
    return land_dist


def evaluate(method, noise=0.0, wire=False, beta=None):
    beta = args.beta if beta is None else beta
    cols = np.array(DRIVEN) if wire else np.arange(F)
    rng = np.random.default_rng(args.seed)
    hits = 0; tot = 0
    for rte in range(R):
        te = np.array([i for i in range(len(grp)) if i % R == rte])
        tr = np.array([i for i in range(len(grp)) if i % R != rte])
        C, mu, sd = per_state_centroids(tr, cols)
        Xc = (X[np.ix_(te, cols)] - mu) / sd
        for j, i in enumerate(te):
            q = Xc[j] + (rng.standard_normal(len(cols)) * noise if noise else 0.0)
            p0 = query_dist(q, C, beta)
            c0 = int(np.argmax(p0))
            if method == 'oneshot':
                pred = land_oneshot[c0]                 # nearest card's stored landing
            elif method == 'greedy':
                pred = walk(c0)                         # follow edges from nearest card
            elif method == 'pathint':
                pred = int(np.argmax(propagate(p0)))    # sum over all paths
            else:
                raise ValueError(method)
            hits += hit(pred, land_oneshot[grp[i]]); tot += 1
    return hits / tot * 100


# baselines
stat = np.mean([hit((COURT_H - 1) / 2, land_oneshot[g]) for g in range(N)]) * 100
rng = np.random.default_rng(1)
rand = np.mean([np.mean([hit(rng.integers(0, COURT_H), land_oneshot[g]) for g in range(N)])
                for _ in range(40)]) * 100

print(f"\n[3] PREDICT the landing — CLEAN query (leave-one-repeat-out):")
print(f"    {'method':<46}{'intercept':>10}")
print(f"    {'-'*46}{'-'*10}")
res = {}
for name, m, wire in [
    ('(baseline) one-shot lookup  (glass, k=1)', 'oneshot', False),
    ('greedy edge-walk            (glass)', 'greedy', False),
    ('PATH-INTEGRAL sum-over-paths (glass)', 'pathint', False),
    ('PATH-INTEGRAL sum-over-paths (WIRE)', 'pathint', True),
]:
    v = evaluate(m, wire=wire); res[name] = v
    print(f"    {name:<46}{v:>9.0f}%")
print(f"    {'-'*46}{'-'*10}")
print(f"    {'stationary baseline':<46}{stat:>9.0f}%")
print(f"    {'random baseline':<46}{rand:>9.0f}%")

print(f"\n[4] The path-integral test — does summing over paths denoise vs committing?")
print(f"    (FAIR standardized-space query noise; the realistic prediction regime)")
print(f"    {'noise σ':>8}{'greedy':>9}{'path-int':>10}{'one-shot':>10}{'wire path-int':>15}")
noise_tbl = []
for nz in (0.0, 0.5, 1.0, 1.5, 2.0):
    g = evaluate('greedy', noise=nz)
    pi = evaluate('pathint', noise=nz)
    os_ = evaluate('oneshot', noise=nz)
    wpi = evaluate('pathint', noise=nz, wire=True)
    noise_tbl.append((nz, g, pi, os_, wpi))
    print(f"    {nz:>8}{g:>8.0f}%{pi:>9.0f}%{os_:>9.0f}%{wpi:>14.0f}%")

print(f"\n[5] Verdict:")
# does path-integral beat greedy under noise (the denoising-by-summation claim)?
gains = [(pi - g) for (nz, g, pi, os_, wpi) in noise_tbl if nz >= 1.0]
glass_wire = [(pi - wpi) for (nz, g, pi, os_, wpi) in noise_tbl if nz >= 1.0]
if np.mean(gains) > 4:
    print(f"  ✓ SUM-OVER-PATHS DENOISES: path-integral beats greedy by "
          f"{np.mean(gains):+.0f} pts under noise (σ≥1). Hedging over futures-of-futures")
    print(f"    reinforces the true landing region while wrong matches wash out.")
elif np.mean(gains) > -2:
    print(f"  ~ path-integral ≈ greedy under noise ({np.mean(gains):+.0f} pts). The classical "
          f"(real, additive) sum neither helps nor hurts vs committing —")
    print(f"    consistent with: bounces scatter nearby cards to different landings, so")
    print(f"    real-valued mass spreads instead of reinforcing. Cancellation (phase) would sharpen it.")
else:
    print(f"  ✗ greedy beats path-integral by {-np.mean(gains):.0f} pts under noise: the spread")
    print(f"    distribution hurts. A CLASSICAL sum can't cancel wrong paths — motivates the phase channel.")
if np.mean(glass_wire) > 6:
    print(f"  ✓ Glass sum beats WIRE sum by {np.mean(glass_wire):+.0f} pts under noise = the distributed")
    print(f"    fingerprint denoises the partial query; the single wire bin cannot.")

print(f"\n[6] PHASE — the honest ceiling on this experiment:")
print(f"    This sum is CLASSICAL: weights ≥ 0, contributions only ADD (Markov propagation).")
print(f"    A true path integral sums COMPLEX amplitudes so wrong paths CANCEL. We match on")
print(f"    magnitude (energy) and discard phase — so we cannot cancel. E9 (99% coherent-phase")
print(f"    cancellation, 2026-06-03) proves the NCO CAN make complex edge weights; wiring that")
print(f"    into EDGE_WEIGHT is the next experiment to tighten the analogy quantum-ward.")

json.dump({
    'timestamp': TS, 'npz': str(npz_path), 'n_states': int(N), 'repeats': int(R),
    'edge_walk_consistency_pct': float(walk_match),
    'clean': {k: float(v) for k, v in res.items()},
    'stationary': float(stat), 'random': float(rand),
    'noise_table': [{'sigma': nz, 'greedy': g, 'pathint': pi, 'oneshot': os_, 'wire_pathint': wpi}
                    for (nz, g, pi, os_, wpi) in noise_tbl],
    'beta': args.beta, 'ksteps': args.ksteps,
    'note': 'classical real-amplitude sum; phase channel (E9) would enable cancellation',
}, open(OUT / f'pong_recurse_{TS}.json', 'w'), indent=2)
print(f"\n  Saved: {OUT / f'pong_recurse_{TS}.json'}")
print("=" * 72)
