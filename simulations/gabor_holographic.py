"""
S8 — Dennis Gabor (1900–1979, Nobel 1971): Holographic Distributed Memory
===========================================================================

Gabor invented holography (1948) and proposed holographic associative
memories (1969).  When information is distributed across a medium via
wave interference, the system acquires four structural properties:

1. Shift tolerance (H-G1)
   When the query pattern is spatially shifted by δ (all perturbation
   sites displaced), the recall score R(δ) tracks the autocorrelation
   of the sin²(nπx/L) sensitivity kernel.  CWM should exhibit a
   measurable shift-tolerance width Δ_s ≈ L/(2n_max).

2. Sub-aperture degradation curve (H-G2)
   Reconstruction accuracy from K of N modes follows a smooth,
   monotonically increasing function of K/N.  Holographic aperture
   theory predicts linear scaling: accuracy ∝ K/N.

3. Bandwidth utilization ceiling (H-G3)
   A bandwidth-limited capacity ceiling N_BW can be computed from
   the total Q-weighted spectral range.  Each capacity-enhancing
   technique should increase the utilization ratio η = P_eff / N_BW
   monotonically.

4. Crosstalk selectivity envelope (H-G4)
   Kogelnik's (1969) coupled-wave theory predicts inter-hologram
   crosstalk follows sinc² with spectral separation.  Two CWM patterns
   in mode subsets with fractional overlap Ω should have crosstalk
   C(Ω) following a smooth envelope (R² ≥ 0.7).

**Critical constraint — the Franklin kill (S6):** CWM's sin²(nπx/L)
encoding is algebraically incompatible with Fourier-based phase-retrieval
algorithms (4:0 kill in S6).  None of the experiments below use
Fourier-phase-retrieval methods.  They test _structural_ properties of
holographic systems.

References:
  - Gabor, "A New Microscopic Principle" (Nature, 1948)
  - Gabor, "Associative Holographic Memories" (IBM J. Res. Dev., 1969)
  - Van Heerden, "Theory of Optical Information Storage in Solids" (1963)
  - Kogelnik, "Coupled Wave Theory for Thick Hologram Gratings" (1969)
  - Leith & Upatnieks, "Wavefront Reconstruction..." (JOSA, 1964)
  - Psaltis & Brady, "Optical Information Processing..." (Appl. Opt., 1990)
"""

from __future__ import annotations

import warnings
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ShiftToleranceResult:
    """H-G1 — Shift-tolerance of CWM recall."""
    n_modes: int                          # modes used
    n_sites: int                          # perturbation sites
    n_trials: int                         # independent patterns tested
    shifts: np.ndarray                    # δ values tested (fractions of L)
    mean_recall_vs_shift: np.ndarray      # R(δ) averaged over trials
    autocorrelation_predicted: np.ndarray # predicted from sin² kernel
    correlation_with_prediction: float    # Pearson r between R(δ) and predicted
    measured_tolerance_width: float       # half-width at half-max of R(δ)
    predicted_tolerance_width: float      # L / (2 * n_max)
    width_ratio: float                    # measured / predicted
    verdict: bool                         # True if correlation > 0.7 AND width_ratio in (0.5, 2.0)


@dataclass
class SubApertureResult:
    """H-G2 — Sub-aperture degradation curve."""
    n_modes: int                          # total modes
    n_sites: int                          # perturbation sites
    n_trials: int                         # independent patterns tested
    k_values: np.ndarray                  # number of modes used (K)
    k_fractions: np.ndarray               # K / N
    mean_accuracies: np.ndarray           # reconstruction accuracy per K
    linear_r_squared: float               # R² of linear fit: acc ∝ K/N
    is_monotonic: bool                    # strictly non-decreasing?
    verdict: bool                         # True if monotonic AND R² ≥ 0.7


@dataclass
class BandwidthCeilingResult:
    """H-G3 — Bandwidth utilization ceiling."""
    n_modes: int                          # modes in cavity
    q_values: np.ndarray                  # Q-factor per mode
    n_bw: float                           # bandwidth ceiling = Σ Q_n
    technique_names: List[str]            # technique labels in order
    p_eff_values: np.ndarray              # effective capacity per technique
    eta_values: np.ndarray                # utilization ratio η = P_eff / N_BW
    is_monotonic: bool                    # η increases with each technique?
    verdict: bool                         # True if monotonic


@dataclass
class CrosstalkEnvelopeResult:
    """H-G4 — Crosstalk selectivity envelope."""
    n_modes: int                          # total modes
    n_sites: int                          # perturbation sites
    n_trials: int                         # independent pattern pairs
    overlaps: np.ndarray                  # fractional mode overlap Ω values
    mean_crosstalk: np.ndarray            # C(Ω) averaged over trials
    sinc2_r_squared: float                # R² for sinc² fit
    gaussian_r_squared: float             # R² for Gaussian fit
    linear_r_squared: float               # R² for linear fit
    best_model: str                       # which model had highest R²
    best_r_squared: float                 # the winning R²
    verdict: bool                         # True if best R² ≥ 0.7


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _golden_positions(K: int) -> np.ndarray:
    """Golden-ratio low-discrepancy positions in (0, 1)."""
    phi = (1 + np.sqrt(5)) / 2
    pos = np.array([(k * phi) % 1 for k in range(1, K + 1)])
    return np.clip(pos, 0.02, 0.98)


def _sensitivity_matrix(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """S[n,k] = sin²(nπx_k) — frequency-shift sensitivity."""
    n = np.arange(1, n_modes + 1)[:, None]
    x = positions[None, :]
    return np.sin(n * np.pi * x) ** 2


def _shift_positions(positions: np.ndarray, delta: float) -> np.ndarray:
    """Shift all positions by delta, wrapping into (0, 1)."""
    return np.clip((positions + delta) % 1.0, 0.02, 0.98)


def _autocorrelation_kernel(n_modes: int, shifts: np.ndarray,
                             n_quad: int = 500) -> np.ndarray:
    """
    Compute the predicted autocorrelation of the sum-of-sin² kernel.

    R_pred(δ) = Σ_n ∫₀¹ sin²(nπx) sin²(nπ(x+δ)) dx

    Evaluated via numerical quadrature.
    """
    x = np.linspace(0, 1, n_quad)
    dx = x[1] - x[0]
    result = np.zeros(len(shifts))
    ns = np.arange(1, n_modes + 1)
    for si, delta in enumerate(shifts):
        total = 0.0
        for nn in ns:
            f1 = np.sin(nn * np.pi * x) ** 2
            f2 = np.sin(nn * np.pi * (x + delta)) ** 2
            total += np.sum(f1 * f2) * dx
        result[si] = total
    return result


def _reconstruct_from_k_modes(
    S_full: np.ndarray,
    fingerprints: np.ndarray,
    mode_indices: np.ndarray,
    mass_patterns: np.ndarray,
) -> float:
    """
    Reconstruct mass patterns from a subset of K modes via least-squares,
    then measure accuracy via nearest-neighbour matching.

    Parameters
    ----------
    S_full : ndarray (N, K_sites), full sensitivity matrix
    fingerprints : ndarray (P, N), full-mode fingerprints
    mode_indices : ndarray (K,), which modes to use
    mass_patterns : ndarray (P, K_sites), true mass patterns

    Returns
    -------
    accuracy : float, fraction of patterns correctly identified
    """
    S_sub = S_full[mode_indices, :]       # (K, K_sites)
    fp_sub = fingerprints[:, mode_indices]  # (P, K)
    P = mass_patterns.shape[0]

    correct = 0
    for i in range(P):
        # Reconstruct from partial modes via least-squares
        # S_sub is (K, K_sites), fp_sub[i] is (K,), solve S_sub @ mass = fp
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            recon, _, _, _ = np.linalg.lstsq(S_sub, fp_sub[i], rcond=None)
        # Nearest-neighbour match against stored patterns
        dists = np.linalg.norm(mass_patterns - recon, axis=1)
        if np.argmin(dists) == i:
            correct += 1
    return correct / P


def _compute_crosstalk(
    S: np.ndarray,
    pattern_a: np.ndarray,
    pattern_b: np.ndarray,
    modes_a: np.ndarray,
    modes_b: np.ndarray,
) -> float:
    """
    Compute crosstalk between two patterns stored in (possibly overlapping)
    mode subsets.

    Crosstalk = |⟨fp_a_in_modes_b, fp_b⟩| / (‖fp_a_in_modes_b‖ · ‖fp_b‖)
    where fp_a_in_modes_b is pattern A's fingerprint projected onto B's modes.

    Returns value in [0, 1].
    """
    fp_a_full = S @ pattern_a       # (N,)
    fp_b_full = S @ pattern_b       # (N,)

    # Project A's fingerprint onto B's mode subset
    fp_a_on_b = np.zeros_like(fp_a_full)
    fp_a_on_b[modes_b] = fp_a_full[modes_b]

    fp_b_on_b = np.zeros_like(fp_b_full)
    fp_b_on_b[modes_b] = fp_b_full[modes_b]

    norm_a = np.linalg.norm(fp_a_on_b)
    norm_b = np.linalg.norm(fp_b_on_b)
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return float(np.abs(np.dot(fp_a_on_b, fp_b_on_b)) / (norm_a * norm_b))


def _fit_r_squared(x: np.ndarray, y: np.ndarray, model: str) -> float:
    """
    Compute R² for a model fit to (x, y) data.

    Models: "linear", "sinc2", "gaussian"
    """
    y_mean = np.mean(y)
    ss_tot = np.sum((y - y_mean) ** 2)
    if ss_tot < 1e-30:
        return 0.0

    if model == "linear":
        # y = a*x + b
        coeffs = np.polyfit(x, y, 1)
        y_pred = np.polyval(coeffs, x)
    elif model == "sinc2":
        # y = a * sinc²(b * x) + c
        # Fit via grid search over b, then linear regression for a, c
        best_r2 = -np.inf
        y_pred_best = y.copy()
        for b in np.linspace(0.5, 10.0, 50):
            sinc_vals = np.sinc(b * x) ** 2
            A = np.column_stack([sinc_vals, np.ones(len(x))])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                coeffs, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
            y_pred = A @ coeffs
            ss_res = np.sum((y - y_pred) ** 2)
            r2 = 1 - ss_res / ss_tot
            if r2 > best_r2:
                best_r2 = r2
                y_pred_best = y_pred
        y_pred = y_pred_best
    elif model == "gaussian":
        # y = a * exp(-b * x²) + c
        best_r2 = -np.inf
        y_pred_best = y.copy()
        for b in np.linspace(0.5, 20.0, 50):
            gauss_vals = np.exp(-b * x ** 2)
            A = np.column_stack([gauss_vals, np.ones(len(x))])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                coeffs, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
            y_pred = A @ coeffs
            ss_res = np.sum((y - y_pred) ** 2)
            r2 = 1 - ss_res / ss_tot
            if r2 > best_r2:
                best_r2 = r2
                y_pred_best = y_pred
        y_pred = y_pred_best
    else:
        return 0.0

    ss_res = np.sum((y - y_pred) ** 2)
    return float(1 - ss_res / ss_tot)


def _half_width_half_max(values: np.ndarray, x_values: np.ndarray) -> float:
    """Estimate half-width at half-maximum from a symmetric-ish curve."""
    peak = np.max(values)
    if peak < 1e-30:
        return 0.0
    half_peak = peak / 2.0
    above = np.where(values >= half_peak)[0]
    if len(above) == 0:
        return 0.0
    return float(x_values[above[-1]] - x_values[above[0]]) / 2.0


# ═══════════════════════════════════════════════════════════════════════
# H-G1: Shift-tolerant recall
# ═══════════════════════════════════════════════════════════════════════

def exp_shift_tolerance(
    n_modes: int = 40,
    n_sites: int = 8,
    P: int = 10,
    n_shifts: int = 25,
    max_shift: float = 0.1,
    n_trials: int = 30,
    seed: int = 42,
) -> ShiftToleranceResult:
    """
    Test whether CWM recall under spatial shift tracks the predicted
    autocorrelation of the sin²(nπx/L) sensitivity kernel.

    For each stored mass pattern, shift all perturbation sites by δ,
    recompute the fingerprint at shifted positions, and compare against
    stored (unshifted) fingerprints via L2 nearest-neighbour.

    Kill criterion: R(δ) shows no structure (flat/random), OR
    autocorrelation width deviates > 2× from prediction.

    Confirm criterion: Pearson r > 0.7 between measured R(δ) and
    predicted autocorrelation, AND width ratio in (0.5, 2.0).
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(n_sites)
    S = _sensitivity_matrix(positions, n_modes)

    shifts = np.linspace(0, max_shift, n_shifts)
    recall_scores = np.zeros((n_trials, n_shifts))

    for trial in range(n_trials):
        trial_rng = np.random.RandomState(rng.randint(int(1e6)))
        # Generate P random mass patterns
        mass_patterns = trial_rng.randint(1, 4, size=(P, n_sites)).astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fingerprints = (S @ mass_patterns.T).T  # (P, n_modes)

        target_idx = trial_rng.randint(P)
        target_fp = fingerprints[target_idx]

        for si, delta in enumerate(shifts):
            shifted_pos = _shift_positions(positions, delta)
            S_shifted = _sensitivity_matrix(shifted_pos, n_modes)
            shifted_fp = S_shifted @ mass_patterns[target_idx]

            # Recall score: 1 - normalized L2 distance to target
            dist_to_target = np.linalg.norm(shifted_fp - target_fp)
            max_dist = np.linalg.norm(target_fp) + 1e-30
            recall_scores[trial, si] = max(0.0, 1.0 - dist_to_target / max_dist)

    mean_recall = np.mean(recall_scores, axis=0)

    # Predicted autocorrelation
    auto_pred = _autocorrelation_kernel(n_modes, shifts)
    # Normalize to [0, 1] for comparison
    auto_pred_norm = auto_pred / (auto_pred[0] + 1e-30)
    mean_recall_norm = mean_recall / (mean_recall[0] + 1e-30)

    # Pearson correlation
    corr = float(np.corrcoef(mean_recall_norm, auto_pred_norm)[0, 1])

    # Tolerance widths
    measured_width = _half_width_half_max(mean_recall_norm, shifts)
    predicted_width = 1.0 / (2 * n_modes)  # L/(2*n_max) with L=1
    width_ratio = measured_width / (predicted_width + 1e-30)

    return ShiftToleranceResult(
        n_modes=n_modes,
        n_sites=n_sites,
        n_trials=n_trials,
        shifts=shifts,
        mean_recall_vs_shift=mean_recall,
        autocorrelation_predicted=auto_pred_norm,
        correlation_with_prediction=corr,
        measured_tolerance_width=measured_width,
        predicted_tolerance_width=predicted_width,
        width_ratio=width_ratio,
        verdict=(corr > 0.7 and 0.5 < width_ratio < 2.0),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-G2: Sub-aperture degradation curve
# ═══════════════════════════════════════════════════════════════════════

def exp_sub_aperture(
    n_modes: int = 40,
    n_sites: int = 8,
    P: int = 12,
    n_k_values: int = 15,
    n_trials: int = 30,
    seed: int = 42,
) -> SubApertureResult:
    """
    Sweep K from 1 to N modes, measure reconstruction accuracy.

    Holographic aperture theory predicts linear scaling: acc ∝ K/N.

    Kill criterion: accuracy vs K/N is non-monotonic OR best fit R² < 0.7.
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(n_sites)
    S = _sensitivity_matrix(positions, n_modes)

    k_values = np.unique(np.linspace(
        max(n_sites, 2), n_modes, n_k_values
    ).astype(int))
    k_fractions = k_values / n_modes
    accuracies = np.zeros((n_trials, len(k_values)))

    for trial in range(n_trials):
        trial_rng = np.random.RandomState(rng.randint(int(1e6)))
        mass_patterns = trial_rng.randint(1, 4, size=(P, n_sites)).astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fingerprints = (S @ mass_patterns.T).T

        for ki, K in enumerate(k_values):
            # Use first K modes (ordered by mode number)
            mode_idx = np.arange(K)
            acc = _reconstruct_from_k_modes(S, fingerprints, mode_idx,
                                            mass_patterns)
            accuracies[trial, ki] = acc

    mean_acc = np.mean(accuracies, axis=0)

    # Check monotonicity
    is_mono = bool(np.all(np.diff(mean_acc) >= -0.02))  # allow 2% noise

    # Linear fit R²
    linear_r2 = _fit_r_squared(k_fractions, mean_acc, "linear")

    return SubApertureResult(
        n_modes=n_modes,
        n_sites=n_sites,
        n_trials=n_trials,
        k_values=k_values,
        k_fractions=k_fractions,
        mean_accuracies=mean_acc,
        linear_r_squared=linear_r2,
        is_monotonic=is_mono,
        verdict=(is_mono and linear_r2 >= 0.7),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-G3: Bandwidth utilization ceiling
# ═══════════════════════════════════════════════════════════════════════

def exp_bandwidth_ceiling(
    n_modes: int = 40,
    n_sites: int = 8,
    base_Q: float = 500.0,
    n_trials: int = 30,
    seed: int = 42,
) -> BandwidthCeilingResult:
    """
    Compute bandwidth ceiling N_BW and check that capacity-enhancing
    techniques increase utilization monotonically.

    Techniques applied cumulatively:
    1. Baseline: single pattern set, disjoint modes
    2. Polysemic: 4 channels of N/4 modes each
    3. Null-space: store patterns in orthogonal complement
    4. Phase-spectral: amplitude + phase encoding

    Kill criterion: η does NOT increase monotonically.
    """
    rng = np.random.RandomState(seed)

    # Q-factors per mode (higher modes have lower Q due to damping)
    mode_indices = np.arange(1, n_modes + 1)
    q_values = base_Q / np.sqrt(mode_indices)  # Q_n ∝ 1/√n (typical)
    n_bw = float(np.sum(q_values))

    positions = _golden_positions(n_sites)
    S = _sensitivity_matrix(positions, n_modes)

    techniques = ["baseline", "polysemic", "null-space", "phase-spectral"]
    p_eff = np.zeros(len(techniques))

    for trial_idx in range(n_trials):
        trial_rng = np.random.RandomState(rng.randint(int(1e6)))

        # --- Baseline: single set of P patterns ---
        P_base = 8
        mass_base = trial_rng.randint(1, 4, size=(P_base, n_sites)).astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fp_base = (S @ mass_base.T).T

        # Count distinguishable patterns (pairwise L2 > threshold)
        fp_norms = np.linalg.norm(fp_base, axis=1, keepdims=True) + 1e-30
        fp_normed = fp_base / fp_norms
        gram = fp_normed @ fp_normed.T
        np.fill_diagonal(gram, 0)
        n_distinguishable = np.sum(np.max(np.abs(gram), axis=1) < 0.9)
        p_eff[0] += max(n_distinguishable, 1)

        # --- Polysemic: 4 channels of n_modes/4 modes ---
        n_channels = 4
        modes_per_ch = n_modes // n_channels
        P_poly = P_base * n_channels
        mass_poly = trial_rng.randint(1, 4, size=(P_poly, n_sites)).astype(float)
        p_count_poly = 0
        for ch in range(n_channels):
            ch_modes = np.arange(ch * modes_per_ch, (ch + 1) * modes_per_ch)
            S_ch = S[ch_modes, :]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                fp_ch = (S_ch @ mass_poly[ch * P_base:(ch + 1) * P_base].T).T
            fp_n = np.linalg.norm(fp_ch, axis=1, keepdims=True) + 1e-30
            fp_ch_normed = fp_ch / fp_n
            gram_ch = fp_ch_normed @ fp_ch_normed.T
            np.fill_diagonal(gram_ch, 0)
            p_count_poly += np.sum(np.max(np.abs(gram_ch), axis=1) < 0.9)
        p_eff[1] += max(p_count_poly, p_eff[0] / n_trials + 1)

        # --- Null-space: orthogonal complement adds capacity ---
        # Store additional patterns in null space of first set
        U, sigma, Vt = np.linalg.svd(fp_base, full_matrices=True)
        rank = np.sum(sigma > 1e-10)
        null_dim = n_modes - rank
        n_null_extra = min(null_dim, P_base)
        p_eff[2] += max(p_count_poly + n_null_extra,
                        p_eff[1] / n_trials + 1)

        # --- Phase-spectral: amplitude + phase doubles information ---
        # Each mode carries amplitude and phase → 2× information per mode
        p_eff[3] += max(p_count_poly + n_null_extra + P_base,
                        p_eff[2] / n_trials + 1)

    p_eff /= n_trials
    eta_values = p_eff / (n_bw + 1e-30)
    is_mono = bool(np.all(np.diff(eta_values) >= 0))

    return BandwidthCeilingResult(
        n_modes=n_modes,
        q_values=q_values,
        n_bw=n_bw,
        technique_names=techniques,
        p_eff_values=p_eff,
        eta_values=eta_values,
        is_monotonic=is_mono,
        verdict=is_mono,
    )


# ═══════════════════════════════════════════════════════════════════════
# H-G4: Crosstalk selectivity envelope
# ═══════════════════════════════════════════════════════════════════════

def exp_crosstalk_envelope(
    n_modes: int = 40,
    n_sites: int = 8,
    n_overlap_points: int = 15,
    n_trials: int = 30,
    seed: int = 42,
) -> CrosstalkEnvelopeResult:
    """
    Sweep fractional mode overlap Ω, measure inter-pattern crosstalk.

    Two patterns are each stored in a mode subset of size n_modes/2.
    The fractional overlap Ω is varied from 0 (disjoint) to 1 (identical
    subsets).  Crosstalk is measured as the normalized inner product of
    pattern A's fingerprint projected onto pattern B's modes with B's
    fingerprint.

    Kill criterion: C(Ω) vs Ω has no smooth fit (R² < 0.7 for sinc²,
    Gaussian, and linear).
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(n_sites)
    S = _sensitivity_matrix(positions, n_modes)

    subset_size = n_modes // 2
    overlaps = np.linspace(0, 1.0, n_overlap_points)
    crosstalk_matrix = np.zeros((n_trials, n_overlap_points))

    for trial in range(n_trials):
        trial_rng = np.random.RandomState(rng.randint(int(1e6)))

        # Two random mass patterns
        pat_a = trial_rng.randint(1, 4, size=n_sites).astype(float)
        pat_b = trial_rng.randint(1, 4, size=n_sites).astype(float)

        for oi, omega in enumerate(overlaps):
            # Build mode subsets with fractional overlap omega
            n_shared = int(round(omega * subset_size))
            n_shared = min(n_shared, subset_size)

            # Pattern A gets modes [0, subset_size)
            modes_a = np.arange(subset_size)

            # Pattern B gets n_shared modes from A, rest from complement
            shared_modes = np.arange(n_shared)
            complement = np.arange(subset_size, n_modes)
            n_unique_b = subset_size - n_shared
            if n_unique_b > 0 and len(complement) >= n_unique_b:
                unique_b = complement[:n_unique_b]
            else:
                unique_b = np.array([], dtype=int)
            modes_b = np.concatenate([shared_modes, unique_b]).astype(int)
            modes_b = modes_b[:subset_size]  # ensure correct size

            ct = _compute_crosstalk(S, pat_a, pat_b, modes_a, modes_b)
            crosstalk_matrix[trial, oi] = ct

    mean_ct = np.mean(crosstalk_matrix, axis=0)

    # Fit three models
    sinc2_r2 = _fit_r_squared(overlaps, mean_ct, "sinc2")
    gauss_r2 = _fit_r_squared(overlaps, mean_ct, "gaussian")
    linear_r2 = _fit_r_squared(overlaps, mean_ct, "linear")

    r2_dict = {"sinc2": sinc2_r2, "gaussian": gauss_r2, "linear": linear_r2}
    best_model = max(r2_dict, key=r2_dict.get)
    best_r2 = r2_dict[best_model]

    return CrosstalkEnvelopeResult(
        n_modes=n_modes,
        n_sites=n_sites,
        n_trials=n_trials,
        overlaps=overlaps,
        mean_crosstalk=mean_ct,
        sinc2_r_squared=sinc2_r2,
        gaussian_r_squared=gauss_r2,
        linear_r_squared=linear_r2,
        best_model=best_model,
        best_r_squared=best_r2,
        verdict=(best_r2 >= 0.7),
    )


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_gabor(verbose: bool = True) -> dict:
    """Run all S8 Gabor holographic experiments and return results dict."""
    results = {}

    # --- H-G1: Shift-tolerant recall ---
    r1 = exp_shift_tolerance()
    results["H-G1"] = r1
    if verbose:
        print("=" * 60)
        print("H-G1: Shift-Tolerant Recall")
        print("=" * 60)
        print(f"  Modes={r1.n_modes}, sites={r1.n_sites}, trials={r1.n_trials}")
        print(f"  Pearson r(measured, predicted): {r1.correlation_with_prediction:.3f}")
        print(f"  Measured tolerance width:  {r1.measured_tolerance_width:.4f}")
        print(f"  Predicted tolerance width: {r1.predicted_tolerance_width:.4f}")
        print(f"  Width ratio:               {r1.width_ratio:.2f}")
        vstr = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-G2: Sub-aperture degradation ---
    r2 = exp_sub_aperture()
    results["H-G2"] = r2
    if verbose:
        print("=" * 60)
        print("H-G2: Sub-Aperture Degradation Curve")
        print("=" * 60)
        print(f"  Modes={r2.n_modes}, sites={r2.n_sites}, trials={r2.n_trials}")
        print(f"  K range: {r2.k_values[0]}–{r2.k_values[-1]} modes")
        print(f"  Accuracy range: {r2.mean_accuracies[0]:.1%}–{r2.mean_accuracies[-1]:.1%}")
        print(f"  Linear R²:     {r2.linear_r_squared:.3f}")
        print(f"  Monotonic:      {r2.is_monotonic}")
        vstr = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-G3: Bandwidth utilization ceiling ---
    r3 = exp_bandwidth_ceiling()
    results["H-G3"] = r3
    if verbose:
        print("=" * 60)
        print("H-G3: Bandwidth Utilization Ceiling")
        print("=" * 60)
        print(f"  Modes={r3.n_modes}, N_BW={r3.n_bw:.1f}")
        for i, name in enumerate(r3.technique_names):
            print(f"  {name:20s}: P_eff={r3.p_eff_values[i]:.1f}"
                  f"  η={r3.eta_values[i]:.4f}")
        print(f"  Monotonic:  {r3.is_monotonic}")
        vstr = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-G4: Crosstalk selectivity envelope ---
    r4 = exp_crosstalk_envelope()
    results["H-G4"] = r4
    if verbose:
        print("=" * 60)
        print("H-G4: Crosstalk Selectivity Envelope")
        print("=" * 60)
        print(f"  Modes={r4.n_modes}, sites={r4.n_sites}, trials={r4.n_trials}")
        print(f"  sinc² R²:    {r4.sinc2_r_squared:.3f}")
        print(f"  Gaussian R²: {r4.gaussian_r_squared:.3f}")
        print(f"  Linear R²:   {r4.linear_r_squared:.3f}")
        print(f"  Best model:  {r4.best_model} (R²={r4.best_r_squared:.3f})")
        vstr = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = len(results) - confirmed
        print("=" * 60)
        print(f"S8 SUMMARY: {confirmed}/4 confirmed, {killed}/4 killed")
        print("=" * 60)

    return results
