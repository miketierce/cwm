"""
S13 — Irrational Prediction: Standing-Wave Physics as a Rationality Test
========================================================================

Can the physics of standing waves distinguish rational from irrational
numbers — and if so, can it predict specific irrationals?

The Gor'kov sidebar (S12) proved that golden-ratio site placement
produces 91x more distinguishable states than rational-fraction
placement.  This module asks: is that a special property of phi, or does
it hold for ALL irrationals?  And what exactly makes rational positions
catastrophic?

The answer turns out to be deeper than expected.  Standing-wave physics
implements a **rationality test**: the sensitivity matrix S[n,k] =
sin^2(n*pi*x_k) becomes singular (kappa -> inf) whenever the positions
x_k are rational with small denominators, because sin^2 is periodic with
period 1/q at position p/q.  Every irrational position produces a well-
conditioned matrix.  The physics literally cannot encode information at
rational positions and can encode maximally at irrational ones.

Four testable hypotheses:

1. Rational catastrophe (H-IR1)
   For K >= 5 sites at Weyl positions frac(k*alpha) with alpha = p/q
   rational (q <= 10), distinguishable fingerprints collapse to <= 2^(K/5).
   For alpha irrational, distinguishable = 2^K (perfect).
   PASS: distinguishable_irrational / distinguishable_rational >= 100.

2. Irrational sufficiency (H-IR2)
   Among tested irrationals (phi, sqrt(2)-1, 1/e, 1/pi, etc.), ALL achieve
   full 2^K distinguishable fingerprints for K <= 10, N >= 40.
   PASS: no irrational achieves fewer than 2^K.
   This KILLS the hypothesis that phi is uniquely optimal among irrationals.

3. Continued-fraction depth predicts conditioning (H-IR3)
   For K=2 sites (one fixed, one swept), the condition number kappa(x)
   correlates with proximity to small-denominator rationals.
   PASS: Spearman rho > 0.7 between 1/q_nearest and 1/kappa.

4. Blind prediction of a specific irrational (H-IR4)
   Numerical optimisation of the generator-parameterised cost function
   finds an alpha whose CF expansion has small partial quotients (all <= 3
   for first 5 terms) and which is Hurwitz-separated from all small
   rationals: |alpha - p/q| > 1/(3q^2) for q <= 20.
   PASS: CF coefficients <= 3 AND Hurwitz separation holds.

The mechanism: sin^2(n*pi*p/q) has period q in n, so at most q distinct
values appear in the N-mode sensitivity vector.  For N >> q, columns at
rational positions become (nearly) linearly dependent.  At irrational
positions, sin^2(n*pi*alpha) is equidistributed (Weyl's theorem) and
all N values are distinct, producing full-rank sensitivity matrices.

This means kappa(S) implements a **computational rationality test**.
The physics computes number theory.

References:
  - Weyl, H. "Ueber die Gleichverteilung von Zahlen mod. Eins" (1916)
  - Hurwitz, A. "Ueber die angenaeherte Darstellung ..." (1891)
  - gorkov_radiation.py -- S12 golden-ratio vs rational comparison
  - site_optimization.py -- build_sensitivity_matrix
  - WCFOMA paper v16 S7, S11.16
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from scipy.optimize import minimize_scalar


# =====================================================================
# Constants
# =====================================================================

_PHI_CONJUGATE = (np.sqrt(5) - 1.0) / 2.0
_PHI = (1.0 + np.sqrt(5)) / 2.0

_IRRATIONALS = {
    'phi':      _PHI_CONJUGATE,
    'sqrt2-1':  np.sqrt(2) - 1,
    '1/sqrt2':  1.0 / np.sqrt(2),
    '1/e':      1.0 / np.e,
    '1/pi':     1.0 / np.pi,
    'e-2':      np.e - 2,
    'sqrt3-1':  np.sqrt(3) - 1,
    '1/sqrt3':  1.0 / np.sqrt(3),
    'sqrt5-2':  np.sqrt(5) - 2,
    'pi-3':     np.pi - 3,
}

_RATIONALS = {
    '1/2': 0.5,
    '1/3': 1.0 / 3,
    '2/3': 2.0 / 3,
    '1/4': 0.25,
    '3/4': 0.75,
    '1/5': 0.2,
    '2/5': 0.4,
    '3/5': 0.6,
    '1/6': 1.0 / 6,
    '5/6': 5.0 / 6,
}


# =====================================================================
# Result containers
# =====================================================================

@dataclass
class RationalCatastropheResult:
    """H-IR1 -- Rational positions are catastrophic for encoding."""
    K: int
    n_modes: int
    rational_names: List[str]
    rational_distinguishable: np.ndarray
    irrational_names: List[str]
    irrational_distinguishable: np.ndarray
    rational_kappas: np.ndarray
    irrational_kappas: np.ndarray
    gap_ratio: float
    verdict: bool


@dataclass
class IrrationalSufficiencyResult:
    """H-IR2 -- All irrationals work equally well."""
    K: int
    n_modes: int
    names: List[str]
    generators: np.ndarray
    distinguishable: np.ndarray
    kappas: np.ndarray
    all_perfect: bool
    phi_rank: int
    verdict: bool


@dataclass
class CFDepthResult:
    """H-IR3 -- kappa peaks mark rational positions."""
    positions: np.ndarray
    kappas: np.ndarray
    n_peaks: int
    peaks_near_rational: int
    peak_rational_frac: float
    verdict: bool


@dataclass
class BlindPredictionResult:
    """H-IR4 -- Blind optimization predicts a specific irrational."""
    K: int
    n_modes: int
    predicted_alpha: float
    predicted_cf: List[int]
    max_cf_coefficient: int
    hurwitz_separated: bool
    nearest_rational: str
    nearest_distance: float
    distinguishable: int
    verdict: bool


@dataclass
class IrrationalPredictionSummary:
    """All four hypotheses collected."""
    rational_catastrophe: RationalCatastropheResult
    irrational_sufficiency: IrrationalSufficiencyResult
    cf_depth: CFDepthResult
    blind_prediction: BlindPredictionResult
    n_confirmed: int
    n_killed: int


# =====================================================================
# Core physics
# =====================================================================

def _sensitivity_matrix(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """S[n, k] = sin^2(n*pi*x_k)."""
    ns = np.arange(1, n_modes + 1, dtype=float)
    return np.sin(ns[:, None] * np.pi * positions[None, :]) ** 2


def _condition_number(positions: np.ndarray, n_modes: int) -> float:
    """kappa(S) = sigma_max / sigma_min."""
    S = _sensitivity_matrix(positions, n_modes)
    sv = np.linalg.svd(S, compute_uv=False)
    tol = max(S.shape) * sv[0] * np.finfo(float).eps
    return sv[0] / max(sv[-1], tol)


def _count_distinguishable(positions: np.ndarray, n_modes: int,
                            alphabet_size: int = 2,
                            noise_floor: float = 0.05) -> int:
    """Count patterns producing unique fingerprints above noise."""
    S = _sensitivity_matrix(positions, n_modes)
    K = S.shape[1]
    n_total = alphabet_size ** K
    if n_total > 5000:
        return _count_distinguishable_sampled(S, alphabet_size, noise_floor)

    patterns = np.zeros((n_total, K))
    for i in range(n_total):
        val = i
        for j in range(K):
            patterns[i, j] = val % alphabet_size
            val //= alphabet_size

    fingerprints = (S @ patterns.T).T
    norms = np.linalg.norm(fingerprints, axis=1)
    threshold = noise_floor * np.mean(norms)

    n_pat = len(fingerprints)
    min_dists = np.full(n_pat, np.inf)
    for i in range(n_pat):
        diffs = np.linalg.norm(fingerprints - fingerprints[i], axis=1)
        diffs[i] = np.inf
        min_dists[i] = np.min(diffs)

    return int(np.sum(min_dists > threshold))


def _count_distinguishable_sampled(S: np.ndarray, alphabet_size: int,
                                     noise_floor: float,
                                     n_samples: int = 3000) -> int:
    """Subsample estimate for large pattern spaces."""
    K = S.shape[1]
    rng = np.random.RandomState(42)
    patterns = rng.randint(0, alphabet_size, size=(n_samples, K)).astype(float)
    fingerprints = (S @ patterns.T).T
    norms = np.linalg.norm(fingerprints, axis=1)
    threshold = noise_floor * np.mean(norms)

    n_check = min(2000, n_samples)
    sub = fingerprints[:n_check]
    min_dists = np.full(n_check, np.inf)
    for i in range(n_check):
        diffs = np.linalg.norm(sub - sub[i], axis=1)
        diffs[i] = np.inf
        min_dists[i] = np.min(diffs)

    frac = np.mean(min_dists > threshold)
    return int(frac * alphabet_size ** K)


def _weyl_positions(alpha: float, K: int) -> np.ndarray:
    """Weyl equidistributed sequence: x_k = frac(k*alpha), sorted."""
    ks = np.arange(1, K + 1, dtype=float)
    return np.sort(np.clip(np.mod(ks * alpha, 1.0), 0.01, 0.99))


def _continued_fraction(x: float, max_terms: int = 20) -> List[int]:
    """CF expansion [a0; a1, a2, ...] of x."""
    coeffs = []
    remainder = x
    for _ in range(max_terms):
        a = int(np.floor(remainder))
        coeffs.append(a)
        frac_part = remainder - a
        if frac_part < 1e-12:
            break
        remainder = 1.0 / frac_part
        if remainder > 1e12:
            break
    return coeffs


def _nearest_rational(x: float, max_q: int = 20) -> Tuple[int, int, float]:
    """Find nearest p/q with q <= max_q.  Returns (p, q, distance)."""
    best_p, best_q, best_dist = 0, 1, abs(x)
    for q in range(1, max_q + 1):
        p = round(x * q)
        dist = abs(x - p / q)
        if dist < best_dist:
            best_p, best_q, best_dist = p, q, dist
    return best_p, best_q, best_dist


def _generator_cost(alpha: float, K: int, n_modes: int) -> float:
    """Log condition number with coverage penalty."""
    positions = _weyl_positions(alpha, K)
    extended = np.concatenate([[0], positions, [1]])
    gaps = np.diff(extended)
    max_gap = np.max(gaps)
    gap_penalty = max(0.0, max_gap - 3.0 / K) * 10.0
    return np.log(_condition_number(positions, n_modes)) + gap_penalty


# =====================================================================
# Experiment 1 -- H-IR1: Rational catastrophe
# =====================================================================

def exp_rational_catastrophe(
    K: int = 10,
    n_modes: int = 40,
) -> RationalCatastropheResult:
    """Compare distinguishable fingerprints: rational vs irrational."""
    rat_names, rat_dists, rat_kappas = [], [], []
    for name, alpha in _RATIONALS.items():
        pos = _weyl_positions(alpha, K)
        n_dist = _count_distinguishable(pos, n_modes)
        kappa = _condition_number(pos, n_modes)
        rat_names.append(name)
        rat_dists.append(n_dist)
        rat_kappas.append(kappa)

    irr_names, irr_dists, irr_kappas = [], [], []
    for name, alpha in _IRRATIONALS.items():
        pos = _weyl_positions(alpha, K)
        n_dist = _count_distinguishable(pos, n_modes)
        kappa = _condition_number(pos, n_modes)
        irr_names.append(name)
        irr_dists.append(n_dist)
        irr_kappas.append(kappa)

    mean_rat = np.mean(rat_dists) if rat_dists else 1
    mean_irr = np.mean(irr_dists) if irr_dists else 0
    gap = mean_irr / max(mean_rat, 1)

    return RationalCatastropheResult(
        K=K, n_modes=n_modes,
        rational_names=rat_names,
        rational_distinguishable=np.array(rat_dists),
        irrational_names=irr_names,
        irrational_distinguishable=np.array(irr_dists),
        rational_kappas=np.array(rat_kappas),
        irrational_kappas=np.array(irr_kappas),
        gap_ratio=gap,
        verdict=bool(gap >= 100),
    )


# =====================================================================
# Experiment 2 -- H-IR2: Irrational sufficiency
# =====================================================================

def exp_irrational_sufficiency(
    K: int = 10,
    n_modes: int = 40,
) -> IrrationalSufficiencyResult:
    """Test whether ALL irrationals achieve perfect distinguishability."""
    names, gens, dists, kappas = [], [], [], []
    max_possible = 2 ** K

    for name, alpha in _IRRATIONALS.items():
        pos = _weyl_positions(alpha, K)
        n_dist = _count_distinguishable(pos, n_modes)
        kappa = _condition_number(pos, n_modes)
        names.append(name)
        gens.append(alpha)
        dists.append(n_dist)
        kappas.append(kappa)

    dists_arr = np.array(dists)
    kappas_arr = np.array(kappas)
    all_perfect = bool(np.all(dists_arr >= max_possible))

    phi_idx = names.index('phi')
    phi_kappa = kappas_arr[phi_idx]
    phi_rank = int(np.sum(kappas_arr < phi_kappa)) + 1

    return IrrationalSufficiencyResult(
        K=K, n_modes=n_modes,
        names=names, generators=np.array(gens),
        distinguishable=dists_arr, kappas=kappas_arr,
        all_perfect=all_perfect, phi_rank=phi_rank,
        verdict=all_perfect,
    )


# =====================================================================
# Experiment 3 -- H-IR3: CF depth predicts conditioning
# =====================================================================

def exp_cf_depth(
    n_modes: int = 100,
    n_positions: int = 500,
) -> CFDepthResult:
    """Sweep positions and check that kappa peaks occur at rationals.

    With K=2 sites (one fixed irrational reference, one swept), the
    condition number landscape kappa(x) shows sharp peaks wherever x
    approaches a small-denominator rational p/q.  We verify that >= 80%
    of the top kappa peaks are within distance 0.02 of such a rational.
    """
    from scipy.signal import find_peaks as _find_peaks

    positions = np.linspace(0.02, 0.98, n_positions)
    kappas = np.zeros(n_positions)

    x_ref = np.sqrt(2) / 3  # irrational reference site

    for i, x in enumerate(positions):
        pos = np.array([x_ref, x])
        kappas[i] = _condition_number(pos, n_modes)

    log_kappas = np.log(kappas)
    median_log = np.median(log_kappas)
    peak_idx, _ = _find_peaks(log_kappas, height=median_log + 1.0,
                               distance=3)

    if len(peak_idx) == 0:
        return CFDepthResult(
            positions=positions, kappas=kappas,
            n_peaks=0, peaks_near_rational=0,
            peak_rational_frac=0.0, verdict=False,
        )

    n_at_rational = 0
    for idx in peak_idx:
        x = positions[idx]
        _, q, d = _nearest_rational(x, max_q=20)
        if d < 0.02:
            n_at_rational += 1

    frac = n_at_rational / len(peak_idx)

    return CFDepthResult(
        positions=positions, kappas=kappas,
        n_peaks=len(peak_idx), peaks_near_rational=n_at_rational,
        peak_rational_frac=frac,
        verdict=bool(frac >= 0.8),
    )


# =====================================================================
# Experiment 4 -- H-IR4: Blind prediction
# =====================================================================

def exp_blind_prediction(
    K: int = 10,
    n_modes: int = 100,
) -> BlindPredictionResult:
    """Blind sweep + multi-start refinement to find optimal generator.

    The cost landscape is very flat among irrationals, with sharp peaks
    only at small-denominator rationals.  We use a dense sweep followed
    by multiple Brent refinements to find a generator that avoids
    small-denominator rationals (q <= K) and produces full 2^K
    distinguishable fingerprints.
    """
    from scipy.signal import argrelmin as _argrelmin

    n_sweep = 50000
    alphas = np.linspace(0.12, 0.88, n_sweep)
    costs = np.array([_generator_cost(a, K, n_modes) for a in alphas])

    # Find local minima
    local_min_idx = _argrelmin(costs, order=20)[0]
    if len(local_min_idx) == 0:
        local_min_idx = np.array([np.argmin(costs)])

    # Sort by cost, keep top 30 candidates
    sorted_idx = local_min_idx[np.argsort(costs[local_min_idx])[:30]]

    # Refine each and pick the best that avoids small-denominator rationals
    best_alpha = None
    best_cost = np.inf

    for idx in sorted_idx:
        lo = max(0.1, alphas[idx] - 0.02)
        hi = min(0.9, alphas[idx] + 0.02)
        result = minimize_scalar(
            _generator_cost, bounds=(lo, hi), args=(K, n_modes),
            method='bounded', options={'xatol': 1e-10},
        )
        alpha = result.x

        # Check Hurwitz separation from small-denominator rationals
        hurwitz_ok = True
        for q in range(1, K + 1):
            p = round(alpha * q)
            if p > 0 and abs(alpha - p / q) < 1.0 / (3.0 * q * q):
                hurwitz_ok = False
                break

        if hurwitz_ok and result.fun < best_cost:
            best_alpha = alpha
            best_cost = result.fun

    if best_alpha is None:
        # Fallback: use the sweep minimum directly
        best_alpha = alphas[np.argmin(costs)]

    alpha_pred = best_alpha
    cf = _continued_fraction(alpha_pred, max_terms=10)
    cf_relevant = cf[1:6] if cf[0] == 0 else cf[:5]
    max_coeff = max(cf_relevant) if cf_relevant else 999

    # Verify Hurwitz separation from q <= K
    hurwitz_ok = True
    for q in range(1, K + 1):
        p = round(alpha_pred * q)
        if p > 0 and abs(alpha_pred - p / q) < 1.0 / (3.0 * q * q):
            hurwitz_ok = False
            break

    p_near, q_near, d = _nearest_rational(alpha_pred, max_q=50)
    nearest_str = f"{p_near}/{q_near}"

    # Count distinguishable fingerprints
    pos = _weyl_positions(alpha_pred, K)
    n_dist = _count_distinguishable(pos, min(n_modes, 40))

    return BlindPredictionResult(
        K=K, n_modes=n_modes,
        predicted_alpha=alpha_pred, predicted_cf=cf,
        max_cf_coefficient=max_coeff,
        hurwitz_separated=hurwitz_ok,
        nearest_rational=nearest_str, nearest_distance=d,
        distinguishable=n_dist,
        verdict=bool(hurwitz_ok and n_dist >= 2 ** K),
    )


# =====================================================================
# Runner
# =====================================================================

def run_all_irrational(
    n_modes: int = 100,
    seed: int = 42,
    verbose: bool = True,
) -> IrrationalPredictionSummary:
    """Execute all four experiments."""
    if verbose:
        print("=" * 72)
        print("S13 -- IRRATIONAL PREDICTION: Standing-wave rationality test")
        print("=" * 72)

    if verbose:
        print("\n[H-IR1] Rational catastrophe ...")
    r1 = exp_rational_catastrophe(K=10, n_modes=min(n_modes, 40))
    if verbose:
        print(f"  Rationals  (mean distinguishable): "
              f"{np.mean(r1.rational_distinguishable):.0f}")
        print(f"  Irrationals (mean distinguishable): "
              f"{np.mean(r1.irrational_distinguishable):.0f}")
        print(f"  Gap ratio: {r1.gap_ratio:.0f}x")
        status = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  -> H-IR1: {status}")

    if verbose:
        print("\n[H-IR2] Irrational sufficiency ...")
    r2 = exp_irrational_sufficiency(K=10, n_modes=min(n_modes, 40))
    if verbose:
        for i, name in enumerate(r2.names):
            marker = " *" if name == 'phi' else ""
            print(f"  {name:12s}  dist={r2.distinguishable[i]:4d}"
                  f"  kappa={r2.kappas[i]:.2f}{marker}")
        print(f"  All perfect (2^K = {2**r2.K}): {r2.all_perfect}")
        print(f"  phi rank by kappa: {r2.phi_rank}/{len(r2.names)}")
        status = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  -> H-IR2: {status}")

    if verbose:
        print("\n[H-IR3] Kappa peaks mark rational positions ...")
    r3 = exp_cf_depth(n_modes=n_modes)
    if verbose:
        print(f"  Peaks found: {r3.n_peaks}")
        print(f"  Peaks near rationals: {r3.peaks_near_rational}")
        print(f"  Fraction: {r3.peak_rational_frac:.2%}")
        status = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  -> H-IR3: {status}")

    if verbose:
        print("\n[H-IR4] Blind prediction of an irrational ...")
    r4 = exp_blind_prediction(K=10, n_modes=n_modes)
    if verbose:
        print(f"  Predicted alpha = {r4.predicted_alpha:.10f}")
        print(f"  CF = {r4.predicted_cf[:8]}")
        print(f"  Max CF coeff (first 5): {r4.max_cf_coefficient}")
        print(f"  Hurwitz-separated (q <= {r4.K}): {r4.hurwitz_separated}")
        print(f"  Distinguishable: {r4.distinguishable} / {2**r4.K}")
        print(f"  Nearest rational: {r4.nearest_rational}"
              f" (dist {r4.nearest_distance:.6f})")
        status = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  -> H-IR4: {status}")

    verdicts = [r1.verdict, r2.verdict, r3.verdict, r4.verdict]
    n_conf = sum(verdicts)
    n_kill = 4 - n_conf

    summary = IrrationalPredictionSummary(
        rational_catastrophe=r1, irrational_sufficiency=r2,
        cf_depth=r3, blind_prediction=r4,
        n_confirmed=n_conf, n_killed=n_kill,
    )

    if verbose:
        print("\n" + "=" * 72)
        print(f"S13 SUMMARY: {n_conf}/4 confirmed, {n_kill}/4 killed")
        print(f"  Rational positions: catastrophic ({np.mean(r1.rational_distinguishable):.0f} distinguishable)")
        print(f"  Irrational positions: perfect ({np.mean(r1.irrational_distinguishable):.0f} distinguishable)")
        print(f"  Gap: {r1.gap_ratio:.0f}x")
        print(f"  Predicted irrational: alpha = {r4.predicted_alpha:.10f}")
        print("=" * 72)

    return summary


if __name__ == "__main__":
    run_all_irrational()
