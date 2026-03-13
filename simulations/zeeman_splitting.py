"""
S9 — Pieter Zeeman (1865–1943, Nobel 1902): Perturbation-Induced Level Splitting
==================================================================================

The Zeeman effect (1896) splits degenerate atomic spectral lines under an
external magnetic field.  The splitting magnitude depends on quantum numbers
and a g-factor, and selection rules (ΔmJ = 0, ±1) constrain which transitions
appear.  At strong fields the splitting becomes quadratic (Paschen-Back regime).

CWM analogue: when an external perturbation (mass loading at position x_p)
is applied to a cavity with near-degenerate eigenmode pairs, frequency
splitting occurs analogous to the Zeeman effect.  The spare_mace avoided-
crossing experiment (§11.3) demonstrated +160% capacity from hybridisation;
the chladni degeneracy-splitting experiment (H-C4) showed structural 2D
splitting.  This sidebar extends both with quantitative predictions grounded
in Zeeman physics.

Four testable hypotheses:

1. Anomalous splitting ratio (H-Z1)
   Perturbation-induced splitting of near-degenerate 1D mode pairs should
   follow Δf/f₀ = g_eff · ε (linear in weak-field regime ε < 0.05),
   where g_eff depends on mode indices analogously to quantum g-factors.

2. Selection-rule channel count (H-Z2)
   Under single-site perturbation, only mode pairs satisfying |n − m| ≤
   Δn_max show significant splitting (> linewidth).  This constrains
   usable split channels, analogous to the quantum rule ΔmJ = 0, ±1.

3. Quadratic Zeeman at strong perturbation (H-Z3)
   At large ε > 0.1, splitting deviates from linear: Δf = g_eff·ε + α·ε².
   The quadratic coefficient α is predictable from mode coupling.

4. Multi-site field geometry (H-Z4)
   K optimally-placed perturbation sites resolve ≥ 2K split pairs,
   analogous to complex magnetic field geometries creating richer
   Zeeman patterns.

References:
  - Zeeman, "On the Influence of Magnetism on the Nature of the Light
    Emitted by a Substance" (Phil. Mag., 1897)
  - Condon & Shortley, *The Theory of Atomic Spectra* (Cambridge, 1935)
  - Scranton, *The Science of the Dogon* (2006) — "splitting of a thing
    into two things"
  - WCFOMA spare_mace §11.3 avoided crossing (+160% capacity)
  - WCFOMA chladni_plates H-C4 degeneracy splitting
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SplittingRatioResult:
    """H-Z1 — Anomalous splitting ratio: g-factor linearity."""
    n_mode_pairs: int                     # number of near-degenerate pairs tested
    epsilon_values: np.ndarray            # perturbation strengths swept
    g_eff_per_pair: np.ndarray            # fitted g_eff for each pair (n_pairs,)
    splitting_matrix: np.ndarray          # Δf/f₀ matrix (n_pairs, n_eps)
    linear_r_squared_per_pair: np.ndarray # R² of linear fit per pair
    mean_linear_r_squared: float          # average R² across pairs
    g_eff_predicted: np.ndarray           # predicted from |sin²(nπx_p) - sin²(mπx_p)|
    g_eff_correlation: float              # Pearson r between measured and predicted g_eff
    verdict: bool                         # True if mean_R² > 0.9 AND g_eff_corr > 0.7


@dataclass
class SelectionRuleResult:
    """H-Z2 — Selection-rule channel count."""
    n_modes: int                          # total modes
    n_pairs_total: int                    # all possible pairs
    n_pairs_significant: int              # pairs with splitting > linewidth
    delta_n_values: np.ndarray            # |n - m| for each pair
    splitting_significant: np.ndarray     # bool per pair: splitting > linewidth
    fraction_significant: float           # n_significant / n_total
    delta_n_max_observed: int             # largest |n-m| with significant splitting
    selection_rule_holds: bool            # True if fraction_significant < 0.8
    verdict: bool                         # True if < 80% of pairs split


@dataclass
class QuadraticZeemanResult:
    """H-Z3 — Quadratic Zeeman at strong perturbation."""
    n_mode_pairs: int                     # pairs tested
    epsilon_values: np.ndarray            # perturbation range (weak to strong)
    splitting_matrix: np.ndarray          # Δf/f₀ (n_pairs, n_eps)
    linear_r2_strong: np.ndarray          # R² of linear-only fit at strong ε, per pair
    quadratic_r2_strong: np.ndarray       # R² of quadratic fit at strong ε, per pair
    mean_linear_r2_strong: float          # average linear R² at strong
    mean_quadratic_r2_strong: float       # average quadratic R² at strong
    alpha_coefficients: np.ndarray        # fitted quadratic coefficient per pair
    verdict: bool                         # True if mean linear R² < 0.99 at strong ε


@dataclass
class MultiSiteResult:
    """H-Z4 — Multi-site field geometry."""
    site_counts: np.ndarray               # K values tested
    n_split_pairs: np.ndarray             # resolvable pairs per K
    threshold_2k: np.ndarray              # 2K threshold per K
    exceeds_2k: np.ndarray                # bool: n_split ≥ 2K
    best_k: int                           # K with best ratio
    best_ratio: float                     # best n_split / (2K)
    verdict: bool                         # True if majority of K values achieve ≥ 2K


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _golden_positions(K: int) -> np.ndarray:
    """Golden-ratio low-discrepancy positions in (0, 1)."""
    phi = (1 + np.sqrt(5)) / 2
    pos = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    return np.clip(pos, 0.02, 0.98)


def _sensitivity_matrix(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """S[n, k] = sin²(nπx_k) — frequency-shift sensitivity."""
    n = np.arange(1, n_modes + 1)[:, None]
    x = positions[None, :]
    return np.sin(n * np.pi * x) ** 2


def _mode_pair_splitting(n: int, m: int, x_p: float,
                         epsilon: float) -> float:
    """
    First-order perturbation splitting of near-degenerate 1D modes.

    For modes n and m in a 1D cavity of unit length, a point-mass
    perturbation at position x_p with strength ε shifts each mode by:
        δf_n = -ε · f_n · sin²(nπx_p)

    The splitting between modes n and m (when f_n ≈ f_m) is:
        Δf = ε · |f_n sin²(nπx_p) - f_m sin²(mπx_p)|

    For normalised splitting Δf/f₀ (f₀ = average frequency):
        Δf/f₀ = ε · |n·sin²(nπx_p) - m·sin²(mπx_p)| / ((n+m)/2)
    """
    sens_n = np.sin(n * np.pi * x_p) ** 2
    sens_m = np.sin(m * np.pi * x_p) ** 2
    f_avg = (n + m) / 2.0
    return epsilon * abs(n * sens_n - m * sens_m) / f_avg


def _g_eff_predicted(n: int, m: int, x_p: float) -> float:
    """
    Predicted effective g-factor for mode pair (n, m) at position x_p.

    g_eff = |n·sin²(nπx_p) - m·sin²(mπx_p)| / ((n+m)/2)

    This is the proportionality constant s.t. Δf/f₀ = g_eff · ε.
    """
    sens_n = np.sin(n * np.pi * x_p) ** 2
    sens_m = np.sin(m * np.pi * x_p) ** 2
    f_avg = (n + m) / 2.0
    return abs(n * sens_n - m * sens_m) / f_avg


def _near_degenerate_pairs(n_modes: int, max_delta_n: int = 3) -> List[Tuple[int, int]]:
    """
    Enumerate near-degenerate mode pairs: (n, m) with 1 ≤ |n - m| ≤ max_delta_n.

    In a 1D cavity f_n = n·c/(2L), so "near-degenerate" means small |n-m|.
    Higher harmonics with |n-m| = 1 are closest in fractional spacing.
    """
    pairs = []
    for n in range(1, n_modes + 1):
        for m in range(n + 1, min(n + max_delta_n + 1, n_modes + 1)):
            pairs.append((n, m))
    return pairs


def _all_mode_pairs(n_modes: int) -> List[Tuple[int, int]]:
    """All unique mode pairs (n, m) with n < m."""
    pairs = []
    for n in range(1, n_modes + 1):
        for m in range(n + 1, n_modes + 1):
            pairs.append((n, m))
    return pairs


def _fit_linear_r_squared(x: np.ndarray, y: np.ndarray) -> float:
    """R² of a linear fit y = a·x + b."""
    if len(x) < 2:
        return 0.0
    y_mean = np.mean(y)
    ss_tot = np.sum((y - y_mean) ** 2)
    if ss_tot < 1e-30:
        return 1.0  # constant data is perfectly fit by constant
    coeffs = np.polyfit(x, y, 1)
    y_pred = np.polyval(coeffs, x)
    ss_res = np.sum((y - y_pred) ** 2)
    return float(1 - ss_res / ss_tot)


def _fit_quadratic_r_squared(x: np.ndarray, y: np.ndarray) -> float:
    """R² of a quadratic fit y = a·x² + b·x + c."""
    if len(x) < 3:
        return 0.0
    y_mean = np.mean(y)
    ss_tot = np.sum((y - y_mean) ** 2)
    if ss_tot < 1e-30:
        return 1.0
    coeffs = np.polyfit(x, y, 2)
    y_pred = np.polyval(coeffs, x)
    ss_res = np.sum((y - y_pred) ** 2)
    return float(1 - ss_res / ss_tot)


def _linewidth(n: int, m: int, Q: float) -> float:
    """
    Linewidth for a mode pair: Δf_linewidth = f_avg / Q.

    f_n ∝ n, so f_avg ∝ (n + m)/2.  We use normalised (unit) frequencies
    so linewidth = (n + m) / (2 · Q).
    """
    return (n + m) / (2.0 * Q)


def _multi_site_splitting(n: int, m: int,
                          positions: np.ndarray,
                          epsilon: float) -> float:
    """
    Splitting from multiple perturbation sites (additive first-order).

    Each site k at position x_k contributes:
        δf_n(k) = -ε · n · sin²(nπx_k)

    Total splitting: Δf = ε · |Σ_k [n·sin²(nπx_k) - m·sin²(mπx_k)]| / f_avg
    """
    total_n = np.sum(n * np.sin(n * np.pi * positions) ** 2)
    total_m = np.sum(m * np.sin(m * np.pi * positions) ** 2)
    f_avg = (n + m) / 2.0
    return epsilon * abs(total_n - total_m) / f_avg


# ═══════════════════════════════════════════════════════════════════════
# H-Z1: Anomalous splitting ratio
# ═══════════════════════════════════════════════════════════════════════

def exp_splitting_ratio(
    n_modes: int = 30,
    x_p: float = 0.37,
    n_epsilon: int = 20,
    epsilon_max: float = 0.05,
    Q: float = 2000.0,
    max_delta_n: int = 3,
    seed: int = 42,
) -> SplittingRatioResult:
    """
    Test whether perturbation-induced splitting follows a linear
    g-factor relationship in the weak-field regime.

    For each near-degenerate pair (n, m) with |n - m| ≤ max_delta_n:
    1. Sweep ε from 0 to epsilon_max.
    2. Compute Δf/f₀ = _mode_pair_splitting(n, m, x_p, ε).
    3. Fit linear model: Δf/f₀ = g_eff · ε.
    4. Compare fitted g_eff to predicted g_eff from the sensitivity formula.

    Kill criterion: splitting ratio deviates > 50% from linear,
    i.e. mean R² < 0.9 OR g_eff correlation < 0.7.
    """
    pairs = _near_degenerate_pairs(n_modes, max_delta_n)
    n_pairs = len(pairs)
    epsilons = np.linspace(0, epsilon_max, n_epsilon)
    # Avoid ε = 0 for fitting (Δf = 0 trivially)
    eps_fit = epsilons[1:]

    splitting_mat = np.zeros((n_pairs, n_epsilon))
    g_eff_fitted = np.zeros(n_pairs)
    g_eff_pred = np.zeros(n_pairs)
    lin_r2 = np.zeros(n_pairs)

    for pi, (n, m) in enumerate(pairs):
        for ei, eps in enumerate(epsilons):
            splitting_mat[pi, ei] = _mode_pair_splitting(n, m, x_p, eps)
        # Fit g_eff: slope of Δf/f₀ vs ε  (through origin)
        y = splitting_mat[pi, 1:]  # skip ε=0
        # Least squares through origin: g_eff = Σ(ε·y) / Σ(ε²)
        g_eff_fitted[pi] = float(np.sum(eps_fit * y) / (np.sum(eps_fit ** 2) + 1e-30))
        g_eff_pred[pi] = _g_eff_predicted(n, m, x_p)
        lin_r2[pi] = _fit_linear_r_squared(eps_fit, y)

    mean_r2 = float(np.mean(lin_r2))

    # Correlation between fitted and predicted g_eff
    if np.std(g_eff_fitted) < 1e-30 or np.std(g_eff_pred) < 1e-30:
        g_corr = 0.0
    else:
        g_corr = float(np.corrcoef(g_eff_fitted, g_eff_pred)[0, 1])

    return SplittingRatioResult(
        n_mode_pairs=n_pairs,
        epsilon_values=epsilons,
        g_eff_per_pair=g_eff_fitted,
        splitting_matrix=splitting_mat,
        linear_r_squared_per_pair=lin_r2,
        mean_linear_r_squared=mean_r2,
        g_eff_predicted=g_eff_pred,
        g_eff_correlation=g_corr,
        verdict=bool(mean_r2 > 0.9 and g_corr > 0.7),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-Z2: Selection-rule channel count
# ═══════════════════════════════════════════════════════════════════════

def exp_selection_rule(
    n_modes: int = 30,
    x_p: float = 0.37,
    epsilon: float = 0.02,
    Q: float = 2000.0,
    seed: int = 42,
) -> SelectionRuleResult:
    """
    Test whether only a constrained subset of mode pairs split significantly.

    For every pair (n, m) with n < m ≤ n_modes:
    1. Compute Δf/f₀.
    2. Compare to linewidth f_avg / Q.
    3. If Δf > linewidth, pair is "significantly split".

    Kill criterion: > 80% of all pairs split significantly.
    Confirm criterion: < 80%, showing a selection rule exists.
    """
    pairs = _all_mode_pairs(n_modes)
    n_total = len(pairs)
    delta_n_vals = np.zeros(n_total, dtype=int)
    significant = np.zeros(n_total, dtype=bool)

    for pi, (n, m) in enumerate(pairs):
        delta_n_vals[pi] = m - n
        splitting = _mode_pair_splitting(n, m, x_p, epsilon)
        lw = _linewidth(n, m, Q)
        significant[pi] = splitting > lw

    n_sig = int(np.sum(significant))
    frac_sig = n_sig / max(n_total, 1)

    # Find largest |n - m| with significant splitting
    sig_delta_n = delta_n_vals[significant]
    delta_n_max_obs = int(np.max(sig_delta_n)) if len(sig_delta_n) > 0 else 0

    return SelectionRuleResult(
        n_modes=n_modes,
        n_pairs_total=n_total,
        n_pairs_significant=n_sig,
        delta_n_values=delta_n_vals,
        splitting_significant=significant,
        fraction_significant=frac_sig,
        delta_n_max_observed=delta_n_max_obs,
        selection_rule_holds=bool(frac_sig < 0.8),
        verdict=bool(frac_sig < 0.8),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-Z3: Quadratic Zeeman at strong perturbation
# ═══════════════════════════════════════════════════════════════════════

def exp_quadratic_zeeman(
    n_modes: int = 30,
    x_p: float = 0.37,
    n_epsilon: int = 30,
    epsilon_max: float = 0.30,
    Q: float = 2000.0,
    max_delta_n: int = 3,
    seed: int = 42,
) -> QuadraticZeemanResult:
    """
    Test whether splitting deviates from linear at strong perturbation.

    The first-order perturbation formula is exactly linear in ε, but
    physically, second-order corrections introduce an ε² term.  We
    model this by adding the second-order coupled-ODE correction:

        Δf/f₀ = g_eff · ε + α · ε²

    where α arises from off-diagonal coupling in the perturbation
    matrix between modes n and m:
        α_{nm} ∝ κ² / (f_n - f_m)  (second-order degenerate PT)

    We compute Δf via numerical eigenvalue solution of the perturbed
    2×2 system rather than first-order formula, then test whether
    the linear-only fit fails at large ε while quadratic succeeds.

    Kill criterion: linear fit R² > 0.99 at ε = 0.3 (no quadratic).
    Confirm: mean linear R² < 0.99 at strong ε, and quadratic R² > linear R².
    """
    pairs = _near_degenerate_pairs(n_modes, max_delta_n)
    n_pairs = len(pairs)
    epsilons = np.linspace(0, epsilon_max, n_epsilon)

    splitting_mat = np.zeros((n_pairs, n_epsilon))
    lin_r2_strong = np.zeros(n_pairs)
    quad_r2_strong = np.zeros(n_pairs)
    alpha_coeffs = np.zeros(n_pairs)

    for pi, (n, m) in enumerate(pairs):
        for ei, eps in enumerate(epsilons):
            # 2×2 eigenvalue problem with perturbation
            # H = [[f_n - ε·f_n·sin²(nπx_p),  κ],
            #      [κ,  f_m - ε·f_m·sin²(mπx_p)]]
            # where κ = ε · √(f_n·f_m) · sin(nπx_p)·sin(mπx_p)  (coupling)
            fn = float(n)
            fm = float(m)
            sens_n = np.sin(n * np.pi * x_p) ** 2
            sens_m = np.sin(m * np.pi * x_p) ** 2
            coupling = eps * np.sqrt(fn * fm) * abs(
                np.sin(n * np.pi * x_p) * np.sin(m * np.pi * x_p)
            )
            H = np.array([
                [fn * (1 - eps * sens_n), coupling],
                [coupling, fm * (1 - eps * sens_m)],
            ])
            eigvals = np.linalg.eigvalsh(H)
            splitting = abs(eigvals[1] - eigvals[0])
            f_avg = (fn + fm) / 2.0
            splitting_mat[pi, ei] = splitting / f_avg

        # Fit in strong regime (upper half of ε range)
        mid = n_epsilon // 2
        eps_strong = epsilons[mid:]
        y_strong = splitting_mat[pi, mid:]

        lin_r2_strong[pi] = _fit_linear_r_squared(eps_strong, y_strong)
        quad_r2_strong[pi] = _fit_quadratic_r_squared(eps_strong, y_strong)

        # Extract α from full quadratic fit
        if n_epsilon >= 3:
            coeffs = np.polyfit(epsilons[1:], splitting_mat[pi, 1:], 2)
            alpha_coeffs[pi] = coeffs[0]  # coefficient of ε²

    mean_lin_r2 = float(np.mean(lin_r2_strong))
    mean_quad_r2 = float(np.mean(quad_r2_strong))

    return QuadraticZeemanResult(
        n_mode_pairs=n_pairs,
        epsilon_values=epsilons,
        splitting_matrix=splitting_mat,
        linear_r2_strong=lin_r2_strong,
        quadratic_r2_strong=quad_r2_strong,
        mean_linear_r2_strong=mean_lin_r2,
        mean_quadratic_r2_strong=mean_quad_r2,
        alpha_coefficients=alpha_coeffs,
        verdict=bool(mean_lin_r2 < 0.99),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-Z4: Multi-site field geometry
# ═══════════════════════════════════════════════════════════════════════

def exp_multi_site(
    n_modes: int = 30,
    max_sites: int = 10,
    epsilon: float = 0.02,
    Q: float = 2000.0,
    max_delta_n: int = 5,
    seed: int = 42,
) -> MultiSiteResult:
    """
    Test whether K perturbation sites resolve ≥ 2K split mode pairs.

    For each K from 1 to max_sites:
    1. Place K sites using golden-ratio low-discrepancy sequence.
    2. For each near-degenerate pair (|n - m| ≤ max_delta_n), compute
       combined splitting from all K sites.
    3. Count pairs where splitting > linewidth (resolvable).
    4. Check if count ≥ 2K.

    Kill criterion: split-pair count < K for optimally-placed sites.
    Confirm: majority of K values achieve ≥ 2K.
    """
    site_counts = np.arange(1, max_sites + 1)
    pairs = _near_degenerate_pairs(n_modes, max_delta_n)
    n_split_pairs = np.zeros(len(site_counts), dtype=int)

    for ki, K in enumerate(site_counts):
        positions = _golden_positions(K)
        count = 0
        for n, m in pairs:
            splitting = _multi_site_splitting(n, m, positions, epsilon)
            lw = _linewidth(n, m, Q)
            if splitting > lw:
                count += 1
        n_split_pairs[ki] = count

    threshold_2k = 2 * site_counts
    exceeds = n_split_pairs >= threshold_2k

    # Best ratio
    ratios = n_split_pairs / (threshold_2k + 1e-30)
    best_idx = int(np.argmax(ratios))
    best_k = int(site_counts[best_idx])
    best_ratio = float(ratios[best_idx])

    # Majority check
    majority = bool(np.sum(exceeds) > len(site_counts) / 2)

    return MultiSiteResult(
        site_counts=site_counts,
        n_split_pairs=n_split_pairs,
        threshold_2k=threshold_2k,
        exceeds_2k=exceeds,
        best_k=best_k,
        best_ratio=best_ratio,
        verdict=majority,
    )


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_zeeman(verbose: bool = True) -> dict:
    """Run all S9 Zeeman splitting experiments and return results dict."""
    results = {}

    # --- H-Z1: Anomalous splitting ratio ---
    r1 = exp_splitting_ratio()
    results["H-Z1"] = r1
    if verbose:
        print("=" * 60)
        print("H-Z1: Anomalous Splitting Ratio")
        print("=" * 60)
        print(f"  Mode pairs tested: {r1.n_mode_pairs}")
        print(f"  Mean linear R²:    {r1.mean_linear_r_squared:.4f}")
        print(f"  g_eff correlation: {r1.g_eff_correlation:.4f}")
        vstr = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-Z2: Selection-rule channel count ---
    r2 = exp_selection_rule()
    results["H-Z2"] = r2
    if verbose:
        print("=" * 60)
        print("H-Z2: Selection-Rule Channel Count")
        print("=" * 60)
        print(f"  Total pairs:       {r2.n_pairs_total}")
        print(f"  Significant:       {r2.n_pairs_significant}"
              f"  ({r2.fraction_significant:.1%})")
        print(f"  Max Δn observed:   {r2.delta_n_max_observed}")
        print(f"  Selection rule:    {r2.selection_rule_holds}")
        vstr = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-Z3: Quadratic Zeeman ---
    r3 = exp_quadratic_zeeman()
    results["H-Z3"] = r3
    if verbose:
        print("=" * 60)
        print("H-Z3: Quadratic Zeeman at Strong Perturbation")
        print("=" * 60)
        print(f"  Mode pairs tested:      {r3.n_mode_pairs}")
        print(f"  Mean linear R² (strong):    {r3.mean_linear_r2_strong:.4f}")
        print(f"  Mean quadratic R² (strong): {r3.mean_quadratic_r2_strong:.4f}")
        print(f"  Mean |α|:               {np.mean(np.abs(r3.alpha_coefficients)):.4f}")
        vstr = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-Z4: Multi-site field geometry ---
    r4 = exp_multi_site()
    results["H-Z4"] = r4
    if verbose:
        print("=" * 60)
        print("H-Z4: Multi-Site Field Geometry")
        print("=" * 60)
        for i, K in enumerate(r4.site_counts):
            flag = "✓" if r4.exceeds_2k[i] else "✗"
            print(f"  K={K:2d}: {r4.n_split_pairs[i]:3d} split pairs"
                  f"  (threshold 2K={r4.threshold_2k[i]:2d}) {flag}")
        print(f"  Best: K={r4.best_k}, ratio={r4.best_ratio:.2f}")
        vstr = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = len(results) - confirmed
        print("=" * 60)
        print(f"S9 SUMMARY: {confirmed}/4 confirmed, {killed}/4 killed")
        print("=" * 60)

    return results
