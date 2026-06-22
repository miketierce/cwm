#!/usr/bin/env python3
"""
Pong PHASE-WEIGHTED recursion — the COMPLEX path sum (can paths cancel?)
=======================================================================

This is the phase-weighted version of pong_recurse_recall.py. The classical
version summed REAL, non-negative probability mass over paths (Markov), which
can only ADD — it bought a consistent but modest +5 under noise. A genuine path
integral sums COMPLEX amplitudes a = √p · e^{iφ}, so contributions can CANCEL.
Here we give each card a phase and sum complex amplitudes at each landing:

    P(landing ℓ) = | Σ_{cards c → ℓ}  √p0[c] · e^{iφ(c)} |²        (complex)
        vs (classical)   Σ_{cards c → ℓ}  p0[c]                    (real, additive)

PHASE MODEL (honest, not tuned to win): φ(c) = k0 · K(c), where K(c) = number of
ticks the ball takes to reach the paddle plane from card c. This is the textbook
SEMICLASSICAL action for constant-speed motion (S = ∫L dt ∝ path length ∝ steps),
i.e. an "acoustic path length." It is a *dynamics* phase, applied uniformly to
right and wrong cards alike — so whether it helps is a real empirical question
(stationary-phase near the true card vs scatter for noise matches). We sweep k0
over a full turn and report the WHOLE curve, not a cherry-picked value.

═══ WHAT THIS IS / IS NOT (read before believing any number) ═══
  • This is a SILICON SIMULATION on replayed MAGNITUDE fingerprints. It predicts
    whether a complex (cancelling) sum *would* beat the real (additive) sum IF the
    phase were physically present. It is NOT glass compute — the captured data has
    NO measured phase (we discarded np.angle at capture time).
  • The cancellation it models is CLASSICAL phasor interference (the same complex
    algebra as E9's 99% acoustic cancellation), NOT quantum amplitude. No Hilbert
    space, no entanglement, no quantum speedup. "Classical analog of the path
    integral, now WITH cancellation" — one notch tighter than the additive version,
    still classical.
  • k0 is NOT a free knob in hardware: it is fixed by the drive frequency / mode
    wavenumber. Picking best-k0 here is a HYPOTHESIS to validate on the bench, not
    a result. The honest hardware realizations are listed at the end of the run.

Replays the captured glass fingerprints (no hardware needed):
  python3 tools/pong_phase_recurse.py
  python3 tools/pong_phase_recurse.py --npz data/results/pong/pong_predict_data_*.npz
"""
import numpy as np
import json, argparse, glob
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser(description='Pong complex (phase-weighted) path sum')
ap.add_argument('--npz', type=str, default=None)
ap.add_argument('--beta', type=float, default=4.0, help='softmax sharpness for query distribution')
ap.add_argument('--ksteps', type=int, default=40)
ap.add_argument('--nk', type=int, default=17, help='k0 sweep points over [0, 2π]')
ap.add_argument('--seed', type=int, default=0)
args = ap.parse_args()

COURT_W, COURT_H = 8, 8
PADDLE_H = 3
N_WIN = 7
AXES = ['x', 'y', 'vx', 'vy']
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = Path('data/results/pong'); OUT.mkdir(parents=True, exist_ok=True)

print("=" * 74)
print("  PONG PHASE-WEIGHTED RECURSION — the COMPLEX path sum (can paths cancel?)")
print("  real additive (classical)  vs  complex phasor (cancelling)  vs  wire")
print("=" * 74)

# ─── Load captured glass fingerprints (MAGNITUDE only — phase was discarded) ──
npz_path = args.npz or (sorted(glob.glob('data/results/pong/pong_predict_data_*.npz'))[-1])
d = np.load(npz_path)
X = d['X']; land_row = d['land'].astype(int); grp = d['grp'].astype(int)
F = X.shape[1]; R = int(round(len(grp) / (grp.max() + 1))); N = grp.max() + 1
X = X / (X.mean(1, keepdims=True) + 1e-9)
DRIVEN = [i * N_WIN + N_WIN // 2 for i in range(len(AXES))]
print(f"\n[1] Replaying {Path(npz_path).name}: {N} states × {R} repeats, {F} features "
      f"(MAGNITUDE only — no measured phase)")

# ─── Deck dynamics + per-card step count K (the action/path-length phase) ─────
states = [(x, y, vx, vy) for x in range(COURT_W) for y in range(COURT_H)
          for vx in (-1, 1) for vy in (-1, 1)]
assert len(states) == N
idx_of = {s: i for i, s in enumerate(states)}


def roll(s):
    """Forward-sim → (landing y, steps K) reaching the paddle plane."""
    x, y, vx, vy = float(s[0]), float(s[1]), s[2], s[3]
    for k in range(1, args.ksteps + 1):
        x += vx; y += vy
        if y < 0: y = -y; vy = -vy
        if y > COURT_H - 1: y = 2 * (COURT_H - 1) - y; vy = -vy
        if x < 0: x = -x; vx = -vx
        if x >= COURT_W - 1:
            return int(round(np.clip(y, 0, COURT_H - 1))), k
    return (COURT_H - 1) // 2, args.ksteps


L_of = np.zeros(N, int)   # landing per card
K_of = np.zeros(N, int)   # steps-to-land per card (→ phase)
for i, s in enumerate(states):
    L_of[i], K_of[i] = roll(s)
print(f"[2] Dynamics: landing range {L_of.min()}–{L_of.max()}, "
      f"steps-to-land K range {K_of.min()}–{K_of.max()} (drives the action phase φ=k0·K)")


def hit(pred, true):
    return abs(int(round(pred)) - int(true)) <= PADDLE_H // 2


def centroids(tr_rows, cols):
    Xs = X[np.ix_(tr_rows, cols)]
    mu = Xs.mean(0); sd = Xs.std(0); sd[sd < 1e-9] = 1
    A = (Xs - mu) / sd; g = grp[tr_rows]
    C = np.zeros((N, len(cols)))
    for c in range(N):
        m = g == c
        C[c] = A[m].mean(0) if m.any() else 0.0
    return C, mu, sd


def query_dist(q, C, beta):
    dsq = ((C - q) ** 2).sum(1)
    z = -beta * (dsq - dsq.min()) / (dsq.std() + 1e-9)
    p = np.exp(z - z.max()); return p / p.sum()


def predict(p0, mode, k0=0.0):
    """Collapse the query distribution over cards → a landing.
    classical: incoherent real sum of mass per landing.
    complex:   coherent phasor sum √p0·e^{ik0·K} per landing, then |·|²."""
    if mode == 'classical':
        ld = np.zeros(COURT_H)
        np.add.at(ld, L_of, p0)
        return int(np.argmax(ld))
    # complex phasor sum
    amp = np.sqrt(p0) * np.exp(1j * k0 * K_of)
    acc = np.zeros(COURT_H, dtype=complex)
    np.add.at(acc, L_of, amp)
    return int(np.argmax(np.abs(acc) ** 2))


def evaluate(mode, noise=0.0, wire=False, k0=0.0):
    cols = np.array(DRIVEN) if wire else np.arange(F)
    rng = np.random.default_rng(args.seed); hits = 0; tot = 0
    for rte in range(R):
        te = [i for i in range(len(grp)) if i % R == rte]
        tr = [i for i in range(len(grp)) if i % R != rte]
        C, mu, sd = centroids(tr, cols)
        Xc = (X[np.ix_(te, cols)] - mu) / sd
        for j, i in enumerate(te):
            q = Xc[j] + (rng.standard_normal(len(cols)) * noise if noise else 0.0)
            p0 = query_dist(q, C, args.beta)
            hits += hit(predict(p0, mode, k0), L_of[grp[i]]); tot += 1
    return hits / tot * 100


# baselines
stat = np.mean([hit((COURT_H - 1) / 2, L_of[g]) for g in range(N)]) * 100

# ─── Sweep the phase wavenumber k0 (physically = drive-freq/mode wavenumber) ──
k0s = np.linspace(0, 2 * np.pi, args.nk)
print(f"\n[3] k0 sweep — complex sum at each phase wavenumber, CLEAN query "
      f"(k0=0 ⇒ fully constructive; k0>0 introduces cancellation):")
print(f"    classical (real additive, the +5 baseline) = {evaluate('classical'):.0f}%")
clean_curve = [(float(k0), evaluate('complex', k0=k0)) for k0 in k0s]
for k0, v in clean_curve:
    bar = '#' * int(round(v / 3))
    print(f"    k0={k0:4.2f}  {v:5.0f}%  {bar}")
best_k0, best_clean = max(clean_curve, key=lambda t: t[1])
print(f"    → best k0={best_k0:.2f} → {best_clean:.0f}% (HYPOTHESIS; k0 is set by drive freq on bench)")

# ─── The real test: does the COMPLEX (cancelling) sum beat CLASSICAL under noise? ──
print(f"\n[4] COMPLEX vs CLASSICAL under FAIR query noise (the prediction regime):")
print(f"    {'σ':>5}{'classical':>11}{'complex(best k0)':>18}{'Δ':>7}{'wire complex':>14}")
noise_tbl = []
for nz in (0.0, 0.5, 1.0, 1.5, 2.0):
    cl = evaluate('classical', noise=nz)
    # pick k0 on the CLEAN curve only (no peeking at the noisy label) — honest
    cx = evaluate('complex', noise=nz, k0=best_k0)
    wx = evaluate('complex', noise=nz, k0=best_k0, wire=True)
    noise_tbl.append((nz, cl, cx, wx))
    print(f"    {nz:>5}{cl:>10.0f}%{cx:>17.0f}%{cx-cl:>+6.0f}{wx:>13.0f}%")

print(f"\n[5] Verdict:")
dlt = [cx - cl for (nz, cl, cx, wx) in noise_tbl if nz >= 1.0]
mean_d = float(np.mean(dlt))
if mean_d > 4:
    print(f"  ✓ COMPLEX SUM BEATS CLASSICAL by {mean_d:+.0f} pts under noise: phasor cancellation")
    print(f"    sharpens the landing distribution — wrong-path contributions destructively cancel.")
    print(f"    → WORTH realizing physically (the phase model earns a bench test).")
elif mean_d > -2:
    print(f"  ~ COMPLEX ≈ CLASSICAL ({mean_d:+.0f} pts). The action-phase model neither helps nor")
    print(f"    hurts here — for THIS geometry the step-count phase doesn't create a stationary-")
    print(f"    phase advantage. An honest null: cancellation needs a phase that varies the RIGHT way.")
else:
    print(f"  ✗ COMPLEX worse by {-mean_d:.0f} pts: this phase model cancels GOOD contributions too.")
    print(f"    Honest null — don't pursue THIS φ; the readout (acoustic) phase is the better lever.")
print(f"    (classical additive baseline still denoises vs wire; see pong_recurse_recall.py)")

print(f"\n[6] HONEST hardware path — what 'coherent-phase NCO drive' actually buys:")
print(f"    • PROVEN doable: E9 (2026-06-03) — two NCO tones, same freq, 180°, shared 126 MHz")
print(f"      clock → 98.9% mode cancellation. The cancelling ingredient is REAL on this bench.")
print(f"    • But that is CLASSICAL acoustic (phasor) interference, not quantum amplitude.")
print(f"      It gives the path integral's COMPLEX-SUM STRUCTURE classically — no quantum speedup.")
print(f"    • Two genuine wave-native realizations (this sim only motivates them):")
print(f"        (A) RECORD the readout phase we currently discard (T3.2: σ_phase 0.12–0.28 rad,")
print(f"            stable) → complex fingerprints → richer match. Cheap: store np.angle at capture.")
print(f"        (B) PHYSICAL interference match (E9 generalized): drive query + stored-card")
print(f"            conjugate at 180°, read residual energy. Low residual = match. Glass cancels.")

json.dump({
    'timestamp': TS, 'npz': str(npz_path), 'n_states': int(N), 'repeats': int(R),
    'phase_model': 'phi = k0 * steps_to_land (semiclassical action, constant speed)',
    'classical_clean': float(evaluate('classical')),
    'clean_k0_curve': clean_curve, 'best_k0': float(best_k0),
    'noise_table': [{'sigma': nz, 'classical': cl, 'complex_bestk0': cx, 'wire_complex': wx}
                    for (nz, cl, cx, wx) in noise_tbl],
    'mean_complex_minus_classical_noisy': mean_d,
    'caveat': 'SILICON sim on magnitude-only replay; classical phasor not quantum; k0 set by drive freq on bench',
}, open(OUT / f'pong_phase_recurse_{TS}.json', 'w'), indent=2)
print(f"\n  Saved: {OUT / f'pong_phase_recurse_{TS}.json'}")
print("=" * 74)
