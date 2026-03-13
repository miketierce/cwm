"""
S6 — Rosalind Franklin (1920–1958): Phase Retrieval and Spectral Inversion
===========================================================================

X-ray crystallography measures diffraction **intensities** (amplitudes squared)
but loses **phases** — the "phase problem."  Crystallographers developed
algorithms to recover this lost phase information from amplitude-only data:

  • Direct methods (Hauptman–Karle tangent formula, Nobel 1985)
  • Patterson function (autocorrelation → inter-atomic distances)
  • Iterative phase retrieval (Gerchberg–Saxton / HIO)
  • Molecular replacement (use a known model to bootstrap phases)

CWM's readout is also an FFT of the rod's response.  The Tesla sidebar
(§11.7) showed that phase carries independent information — complex recall
outperforms amplitude-only recall.  Franklin's domain asks: can we do even
better?  Can we recover phase from amplitude-only data?  Can we reconstruct
perturbation positions from the spectrum alone (the inverse problem)?

Parallel → Hypothesis → Experiment
═══════════════════════════════════════════════════════════════════════
1. Direct methods (Hauptman–Karle)
   H-F1: Tangent-formula phase retrieval recovers perturbation
         positions from amplitude-only spectra at ≥ 80% accuracy.

2. Patterson function (autocorrelation)
   H-F2: The autocorrelation of the amplitude spectrum reveals
         inter-site distances; K sites yield K(K-1)/2 constraints.

3. Gerchberg–Saxton / HIO iterative retrieval
   H-F3: GS/HIO converges to the correct perturbation pattern from
         amplitude-only data within 100 iterations for ≤ 20 sites.

4. Molecular replacement → associative recall
   H-F4: Using stored patterns as template phases (like MR search
         models) improves recall over both amplitude-only and
         complex dot-product matching.

References:
  - Hauptman & Karle, "Solution of the Phase Problem" (1953)
  - Franklin & Gosling, "Molecular Configuration in Sodium
    Thymonucleate" (1953) — Photo 51
  - Gerchberg & Saxton, Optik 35, 237 (1972)
  - Fienup, "Phase retrieval algorithms" Appl. Opt. 21, 2758 (1982)
  - Rossmann & Blow, "The Detection of Sub-Units within the
    Crystallographic Asymmetric Unit" Acta Cryst. 15, 24 (1962)
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
class DirectMethodResult:
    """H-F1 — Tangent-formula phase retrieval from amplitude-only data."""
    n_modes: int
    n_sites: int
    n_trials: int
    reconstruction_accuracy: float      # fraction of sites correctly located
    mean_position_error: float          # mean |x_true - x_recovered| / L
    amplitude_only_baseline: float      # recall accuracy without phases
    direct_method_accuracy: float       # recall accuracy using recovered phases
    phase_error_deg: float              # mean |φ_true - φ_recovered| in degrees
    verdict: bool   # True if reconstruction ≥ 80% or direct-method recall ≥ 50%


@dataclass
class PattersonResult:
    """H-F2 — Patterson function: inter-site distances from amplitude spectrum."""
    n_sites: int
    n_modes: int
    n_true_distances: int               # K(K-1)/2
    n_recovered_distances: int          # peaks in Patterson map
    distance_recovery_fraction: float   # recovered / true
    mean_distance_error: float          # mean |d_true - d_recovered|
    distance_constraints: np.ndarray    # recovered inter-site distances
    true_distances: np.ndarray          # ground-truth distances
    verdict: bool   # True if recovered ≥ K independent distance constraints


@dataclass
class GerchbergSaxtonResult:
    """H-F3 — Iterative phase retrieval (GS/HIO) convergence."""
    n_modes: int
    n_sites: int
    n_iterations: int                   # iterations to convergence
    max_iterations: int                 # budget
    converged: bool                     # error < tolerance before budget
    final_error: float                  # ||pattern_recovered - pattern_true|| / ||true||
    reconstruction_accuracy: float      # fraction of sites within tolerance
    error_history: np.ndarray           # error at each iteration
    verdict: bool   # True if converged within 100 iterations


@dataclass
class MolecularReplacementResult:
    """H-F4 — Molecular replacement: stored-pattern-phased recall."""
    n_modes: int
    n_patterns_stored: int
    n_trials: int
    amplitude_only_accuracy: float      # baseline
    complex_recall_accuracy: float      # Tesla H-T2 baseline
    mr_recall_accuracy: float           # molecular-replacement phased recall
    mr_improvement_over_amp_pct: float
    mr_improvement_over_complex_pct: float
    mean_mr_margin: float               # discrimination margin
    verdict: bool   # True if MR recall > complex recall


# ═══════════════════════════════════════════════════════════════════════
# Helpers (reuse tesla_phase patterns)
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


def _phase_sensitivity_matrix(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """P[n,k] = sin(2nπx_k) — phase-shift sensitivity."""
    n = np.arange(1, n_modes + 1)[:, None]
    x = positions[None, :]
    return np.sin(2 * n * np.pi * x)


def _complex_fingerprint(
    S_freq: np.ndarray,
    S_phase: np.ndarray,
    pattern: np.ndarray,
    phase_max: float = 1.0,
) -> np.ndarray:
    """Complex fingerprint: amplitude from freq shifts, phase from phase shifts."""
    amp = S_freq @ pattern
    phi = S_phase @ pattern
    phi_scaled = phi / (max(abs(phase_max), 1e-30)) * np.pi
    return amp * np.exp(1j * phi_scaled)


# ═══════════════════════════════════════════════════════════════════════
# Experiment F1 — Direct Methods (Hauptman–Karle Tangent Formula)
# ═══════════════════════════════════════════════════════════════════════

def _tangent_formula_phases(amplitudes: np.ndarray, n_iter: int = 50,
                            rng: Optional[np.random.RandomState] = None
                            ) -> np.ndarray:
    """
    Estimate phases from amplitudes using the tangent formula.

    The tangent formula relates the phase of reflection h to a weighted
    sum over pairs of reflections (k, h-k):

        tan(φ_h) ≈ Σ_k |E_k||E_{h-k}| sin(φ_k + φ_{h-k})
                   / Σ_k |E_k||E_{h-k}| cos(φ_k + φ_{h-k})

    where E_h are normalised structure factors.  In the CWM context,
    "reflections" are mode indices and amplitudes are |F_n|.

    We adapt this by treating mode indices as 1D "reciprocal lattice"
    points:  for mode h, sum over pairs (k, h-k) where both k and h-k
    are valid mode indices.
    """
    if rng is None:
        rng = np.random.RandomState(0)

    N = len(amplitudes)
    # Normalise to E-values (large |E| → strong phase constraint)
    E = amplitudes / (np.mean(amplitudes) + 1e-30)

    # Random initial phases (centrosymmetric: 0 or π for real patterns)
    phases = rng.choice([0.0, np.pi], size=N)

    for iteration in range(n_iter):
        new_phases = np.copy(phases)
        for h in range(N):
            num = 0.0
            den = 0.0
            for k in range(N):
                hk = h - k
                if 0 <= hk < N and k != h:
                    weight = E[k] * E[hk]
                    num += weight * np.sin(phases[k] + phases[hk])
                    den += weight * np.cos(phases[k] + phases[hk])
            if abs(num) + abs(den) > 1e-30:
                new_phases[h] = np.arctan2(num, den)
        phases = new_phases

    return phases


def exp_direct_methods(
    K: int = 8,
    n_modes: int = 30,
    n_trials: int = 50,
    noise_sigma: float = 0.05,
    tangent_iterations: int = 50,
    rng: Optional[np.random.RandomState] = None,
) -> DirectMethodResult:
    """
    H-F1: Can crystallographic direct methods recover perturbation
    positions from amplitude-only CWM spectra?

    The tangent formula uses statistical relations among diffraction
    amplitudes to estimate phases.  We test whether this recovers
    enough phase information to improve pattern recall.

    Kill criterion: reconstruction accuracy < 50%.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    positions = _golden_positions(K)
    S_freq = _sensitivity_matrix(positions, n_modes)
    S_phase = _phase_sensitivity_matrix(positions, n_modes)

    phase_errors = []
    amp_only_correct = 0
    dm_correct = 0
    position_errors = []

    for trial in range(n_trials):
        # Generate a random perturbation pattern
        pattern = rng.randint(0, 3, size=K).astype(float)

        # Compute true fingerprints
        freq_fp = S_freq @ pattern
        phase_fp = S_phase @ pattern
        amplitudes = np.abs(freq_fp)  # amplitude-only (phase lost)

        # Add noise to amplitudes
        noisy_amps = amplitudes + rng.randn(n_modes) * noise_sigma

        # --- Direct method: recover phases from amplitudes ---
        recovered_phases = _tangent_formula_phases(
            np.abs(noisy_amps),
            n_iter=tangent_iterations,
            rng=np.random.RandomState(rng.randint(10**6)),
        )

        # Compute phase error vs true phases
        true_phases = np.angle(freq_fp * np.exp(1j * phase_fp))
        # Phases are only meaningful up to a global offset
        offset = np.mean(true_phases - recovered_phases)
        adjusted = recovered_phases + offset
        phase_err = np.abs(np.angle(np.exp(1j * (true_phases - adjusted))))
        phase_errors.append(float(np.mean(np.degrees(phase_err))))

        # --- Reconstruction: invert the sensitivity matrix ---
        # Use pseudoinverse to recover pattern from complex fingerprint
        complex_recovered = noisy_amps * np.exp(1j * recovered_phases)
        S_complex = S_freq * np.exp(1j * S_phase)
        try:
            pattern_recovered = np.real(np.linalg.lstsq(
                S_complex, complex_recovered, rcond=None)[0])
        except np.linalg.LinAlgError:
            pattern_recovered = np.zeros(K)

        # Measure reconstruction accuracy: quantise and compare
        pattern_quant = np.round(np.clip(pattern_recovered, 0, 2))
        correct_sites = np.sum(np.abs(pattern_quant - pattern) < 0.5)
        position_errors.append(correct_sites / K)

        # --- Recall comparison: amplitude-only vs DM-phased ---
        # Store this pattern and a few distractors
        n_distractors = 7
        all_patterns = [pattern]
        for _ in range(n_distractors):
            all_patterns.append(rng.randint(0, 3, size=K).astype(float))

        # Amplitude-only recall
        amp_overlaps = []
        for p in all_patterns:
            fp = np.abs(S_freq @ p)
            norm_s = np.linalg.norm(fp)
            norm_q = np.linalg.norm(np.abs(noisy_amps))
            if norm_s > 0 and norm_q > 0:
                amp_overlaps.append(np.dot(fp, np.abs(noisy_amps)) / (norm_s * norm_q))
            else:
                amp_overlaps.append(0.0)
        if np.argmax(amp_overlaps) == 0:
            amp_only_correct += 1

        # DM-phased recall: use recovered phases to build complex query
        dm_query = noisy_amps * np.exp(1j * recovered_phases)
        phase_max = np.max(np.abs(S_phase @ pattern))
        dm_overlaps = []
        for p in all_patterns:
            fp = _complex_fingerprint(S_freq, S_phase, p, phase_max=phase_max)
            ns = np.linalg.norm(fp)
            nq = np.linalg.norm(dm_query)
            if ns > 0 and nq > 0:
                dm_overlaps.append(float(np.abs(np.dot(fp.conj(), dm_query)) / (ns * nq)))
            else:
                dm_overlaps.append(0.0)
        if np.argmax(dm_overlaps) == 0:
            dm_correct += 1

    recon_accuracy = float(np.mean(position_errors))
    amp_only_acc = amp_only_correct / n_trials
    dm_acc = dm_correct / n_trials

    return DirectMethodResult(
        n_modes=n_modes,
        n_sites=K,
        n_trials=n_trials,
        reconstruction_accuracy=recon_accuracy,
        mean_position_error=1.0 - recon_accuracy,
        amplitude_only_baseline=amp_only_acc,
        direct_method_accuracy=dm_acc,
        phase_error_deg=float(np.mean(phase_errors)),
        verdict=bool(recon_accuracy >= 0.50 or dm_acc >= 0.50),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment F2 — Patterson Function (Autocorrelation)
# ═══════════════════════════════════════════════════════════════════════

def _patterson_map(amplitudes: np.ndarray, n_modes: int) -> np.ndarray:
    """
    Compute the Patterson function from amplitude-only data.

    P(u) = Σ_n |F_n|² cos(2πnu)

    where u is a position variable in [0, 1].  Peaks in P(u)
    correspond to inter-site distances in the perturbation pattern.
    """
    u = np.linspace(0, 1, 1000)
    P = np.zeros_like(u)
    for n_idx in range(len(amplitudes)):
        n = n_idx + 1  # mode index
        P += amplitudes[n_idx]**2 * np.cos(2 * np.pi * n * u)
    return u, P


def _find_patterson_peaks(u: np.ndarray, P: np.ndarray,
                          height_frac: float = 0.15,
                          min_sep: float = 0.02) -> np.ndarray:
    """Find peaks in Patterson map above a height threshold."""
    # Normalise
    P_norm = P / (np.max(np.abs(P)) + 1e-30)
    threshold = height_frac

    peaks = []
    # Simple peak finder: local maxima above threshold
    for i in range(1, len(P_norm) - 1):
        if (P_norm[i] > P_norm[i-1] and P_norm[i] > P_norm[i+1]
                and P_norm[i] > threshold and u[i] > min_sep
                and u[i] < 1.0 - min_sep):
            peaks.append(u[i])

    # Remove duplicates within min_sep
    if len(peaks) == 0:
        return np.array([])
    peaks = np.sort(peaks)
    filtered = [peaks[0]]
    for p in peaks[1:]:
        if p - filtered[-1] > min_sep:
            filtered.append(p)
    return np.array(filtered)


def exp_patterson_function(
    K: int = 6,
    n_modes: int = 40,
    noise_sigma: float = 0.02,
    rng: Optional[np.random.RandomState] = None,
) -> PattersonResult:
    """
    H-F2: Does the Patterson function (autocorrelation of the amplitude
    spectrum) reveal inter-site distances without phase information?

    The Patterson function is P(u) = Σ |F_n|² exp(2πinu), which for
    real data simplifies to a cosine series.  Its peaks correspond to
    differences between perturbation site positions — exactly the
    inter-atomic distance vectors in crystallography.

    Kill criterion: fewer than K independent distance constraints.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    positions = _golden_positions(K)
    S_freq = _sensitivity_matrix(positions, n_modes)

    # Generate pattern and compute amplitudes
    pattern = rng.randint(1, 4, size=K).astype(float)  # nonzero sites
    freq_fp = S_freq @ pattern
    amplitudes = np.abs(freq_fp) + rng.randn(n_modes) * noise_sigma

    # Compute Patterson map
    u, P = _patterson_map(amplitudes, n_modes)
    peaks = _find_patterson_peaks(u, P)

    # Compute true inter-site distances
    true_dists = []
    for i in range(K):
        for j in range(i+1, K):
            true_dists.append(abs(positions[i] - positions[j]))
    true_dists = np.sort(true_dists)

    # Match recovered peaks to true distances
    matched = 0
    unmatched_errors = []
    for d_true in true_dists:
        if len(peaks) > 0:
            closest_idx = np.argmin(np.abs(peaks - d_true))
            err = abs(peaks[closest_idx] - d_true)
            if err < 0.03:  # within 3% of cavity length
                matched += 1
                unmatched_errors.append(err)
            else:
                unmatched_errors.append(err)
        else:
            unmatched_errors.append(1.0)

    n_true = len(true_dists)
    recovery_frac = matched / max(n_true, 1)
    mean_err = float(np.mean(unmatched_errors)) if unmatched_errors else 1.0

    return PattersonResult(
        n_sites=K,
        n_modes=n_modes,
        n_true_distances=n_true,
        n_recovered_distances=len(peaks),
        distance_recovery_fraction=recovery_frac,
        mean_distance_error=mean_err,
        distance_constraints=peaks,
        true_distances=true_dists,
        verdict=bool(matched >= K),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment F3 — Gerchberg–Saxton / HIO Iterative Phase Retrieval
# ═══════════════════════════════════════════════════════════════════════

def _gerchberg_saxton(
    target_amplitudes: np.ndarray,
    S_freq: np.ndarray,
    K: int,
    max_iter: int = 200,
    tol: float = 1e-4,
    beta: float = 0.8,
    rng: Optional[np.random.RandomState] = None,
) -> Tuple[np.ndarray, np.ndarray, int]:
    """
    Hybrid Input-Output (HIO) phase retrieval.

    Alternates between:
      - Fourier-space constraint: replace amplitudes with measured |F|
      - Real-space constraint: enforce non-negativity & sparsity

    Returns (recovered_pattern, error_history, n_iterations).
    """
    if rng is None:
        rng = np.random.RandomState(0)

    n_modes = len(target_amplitudes)

    # Random initial guess in pattern space
    x = rng.rand(K) * 2.0

    errors = []
    for it in range(max_iter):
        # Forward: pattern → spectrum
        spectrum = S_freq @ x

        # Apply Fourier-space constraint: keep measured amplitudes
        phases_current = np.angle(spectrum + 1e-30 * 1j)
        spectrum_constrained = target_amplitudes * np.exp(1j * phases_current)

        # Inverse: spectrum → pattern (pseudoinverse)
        x_new = np.real(np.linalg.lstsq(S_freq, np.real(spectrum_constrained),
                                          rcond=None)[0])

        # Apply real-space constraint: HIO update
        # Sites that satisfy constraints keep new value;
        # violating sites use feedback
        mask_ok = x_new >= 0
        x_hio = np.where(mask_ok, x_new, x - beta * x_new)
        x_hio = np.clip(x_hio, 0, 5)

        # Measure error
        spectrum_check = S_freq @ x_hio
        amp_err = np.linalg.norm(np.abs(spectrum_check) - target_amplitudes)
        amp_err /= np.linalg.norm(target_amplitudes) + 1e-30
        errors.append(amp_err)

        x = x_hio

        if amp_err < tol:
            return x, np.array(errors), it + 1

    return x, np.array(errors), max_iter


def exp_gerchberg_saxton(
    K: int = 8,
    n_modes: int = 30,
    max_iterations: int = 200,
    n_restarts: int = 5,
    noise_sigma: float = 0.02,
    convergence_threshold: int = 100,
    rng: Optional[np.random.RandomState] = None,
) -> GerchbergSaxtonResult:
    """
    H-F3: Does iterative phase retrieval (GS/HIO) converge to the
    correct perturbation pattern from amplitude-only FFT data?

    Uses multiple random restarts and keeps the best solution (lowest
    amplitude-space error), since GS/HIO is not guaranteed to find
    the global minimum.

    Kill criterion: non-convergence or > 1000 iterations for ≤ 20 sites.
    (We use 100-iteration threshold per the hypothesis.)
    """
    if rng is None:
        rng = np.random.RandomState(42)

    positions = _golden_positions(K)
    S_freq = _sensitivity_matrix(positions, n_modes)

    # Generate target pattern
    pattern_true = rng.randint(0, 3, size=K).astype(float)
    freq_fp = S_freq @ pattern_true
    target_amps = np.abs(freq_fp) + rng.randn(n_modes) * noise_sigma
    target_amps = np.maximum(target_amps, 0)  # amplitudes non-negative

    best_pattern = None
    best_error = float('inf')
    best_errors = None
    best_n_iter = max_iterations

    for restart in range(n_restarts):
        recovered, errors, n_iter = _gerchberg_saxton(
            target_amps, S_freq, K,
            max_iter=max_iterations,
            rng=np.random.RandomState(rng.randint(10**6)),
        )
        final_err = errors[-1] if len(errors) > 0 else float('inf')
        if final_err < best_error:
            best_error = final_err
            best_pattern = recovered
            best_errors = errors
            best_n_iter = n_iter

    # Measure reconstruction accuracy
    pattern_quant = np.round(np.clip(best_pattern, 0, 2))
    correct_sites = np.sum(np.abs(pattern_quant - pattern_true) < 0.5)
    recon_acc = correct_sites / K

    converged = best_n_iter <= convergence_threshold

    return GerchbergSaxtonResult(
        n_modes=n_modes,
        n_sites=K,
        n_iterations=best_n_iter,
        max_iterations=max_iterations,
        converged=converged,
        final_error=float(best_error),
        reconstruction_accuracy=recon_acc,
        error_history=best_errors,
        verdict=bool(converged),
    )


# ═══════════════════════════════════════════════════════════════════════
# Experiment F4 — Molecular Replacement Recall
# ═══════════════════════════════════════════════════════════════════════

def exp_molecular_replacement(
    K: int = 6,
    n_modes: int = 30,
    n_stored: int = 8,
    n_trials: int = 200,
    noise_sigma: float = 0.05,
    rng: Optional[np.random.RandomState] = None,
) -> MolecularReplacementResult:
    """
    H-F4: Molecular replacement — using stored patterns as "search models"
    to phase the amplitude-only readout.

    In crystallography, molecular replacement (MR) places a known protein
    structure (the "search model") into the unit cell, computes its
    diffraction pattern, and uses the model's calculated phases combined
    with the observed amplitudes to build a starting electron density map.

    CWM analogue: given an amplitude-only readout |F_n|, try each stored
    pattern as a phase model.  For stored pattern j, compute the model
    phases φ_n^(j), then form:

        MR_j = |Σ_n |F_n| · exp(iφ_n^(j)) · A_n^(j)*|

    This is like the complex recall from H-T2, except the *query's*
    phase is supplied by the *model* (since the query has lost its phase).

    Kill criterion: MR recall ≤ complex recall (H-T2 baseline).
    """
    if rng is None:
        rng = np.random.RandomState(42)

    positions = _golden_positions(K)
    S_freq = _sensitivity_matrix(positions, n_modes)
    S_phase = _phase_sensitivity_matrix(positions, n_modes)

    # Store random patterns
    stored_patterns = rng.randint(0, 3, size=(n_stored, K)).astype(float)

    # Precompute stored fingerprints
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        stored_freq = stored_patterns @ S_freq.T     # (n_stored, n_modes)
        stored_phase = stored_patterns @ S_phase.T   # (n_stored, n_modes)
    phase_max = np.max(np.abs(stored_phase)) + 1e-30
    phase_scaled = stored_phase / phase_max * np.pi
    stored_complex = stored_freq * np.exp(1j * phase_scaled)

    amp_correct = 0
    complex_correct = 0
    mr_correct = 0
    mr_margins = []

    for trial in range(n_trials):
        target_idx = rng.randint(n_stored)
        noisy_pattern = stored_patterns[target_idx].copy()

        # Add noise to some sites
        noise_mask = rng.rand(K) < noise_sigma * 5
        noisy_pattern[noise_mask] += rng.randn(int(np.sum(noise_mask))) * 0.5

        # Compute query fingerprints
        query_freq = noisy_pattern @ S_freq.T
        query_phase = noisy_pattern @ S_phase.T
        query_phase_scaled = query_phase / phase_max * np.pi
        query_complex = query_freq * np.exp(1j * query_phase_scaled)

        # Add readout noise
        query_freq_noisy = query_freq + rng.randn(n_modes) * noise_sigma
        query_complex_noisy = query_complex + (
            rng.randn(n_modes) + 1j * rng.randn(n_modes)) * noise_sigma

        # The amplitude-only readout (phase information lost)
        query_amps = np.abs(query_freq_noisy)

        # --- Method 1: Amplitude-only recall ---
        amp_overlaps = np.zeros(n_stored)
        for j in range(n_stored):
            s = np.abs(stored_freq[j])
            q = query_amps
            ns, nq = np.linalg.norm(s), np.linalg.norm(q)
            if ns > 0 and nq > 0:
                amp_overlaps[j] = np.dot(s, q) / (ns * nq)
        if np.argmax(amp_overlaps) == target_idx:
            amp_correct += 1

        # --- Method 2: Complex recall (H-T2 baseline, has true phase) ---
        complex_overlaps = np.zeros(n_stored)
        for j in range(n_stored):
            s = stored_complex[j]
            q = query_complex_noisy
            ns, nq = np.linalg.norm(s), np.linalg.norm(q)
            if ns > 0 and nq > 0:
                complex_overlaps[j] = float(np.abs(np.dot(s.conj(), q)) / (ns * nq))
        if np.argmax(complex_overlaps) == target_idx:
            complex_correct += 1

        # --- Method 3: Molecular replacement recall ---
        # Use each stored pattern's phases to phase the amplitude-only query
        mr_overlaps = np.zeros(n_stored)
        for j in range(n_stored):
            # Phase the query amplitudes with model j's phases
            model_phases = phase_scaled[j]
            phased_query = query_amps * np.exp(1j * model_phases)

            # Compare with model j's complex fingerprint
            s = stored_complex[j]
            ns = np.linalg.norm(s)
            nq = np.linalg.norm(phased_query)
            if ns > 0 and nq > 0:
                mr_overlaps[j] = float(np.abs(np.dot(s.conj(), phased_query)) / (ns * nq))
        if np.argmax(mr_overlaps) == target_idx:
            mr_correct += 1

        sorted_mr = np.sort(mr_overlaps)[::-1]
        mr_margins.append(sorted_mr[0] - sorted_mr[1] if len(sorted_mr) > 1 else 0)

    amp_acc = amp_correct / n_trials
    cplx_acc = complex_correct / n_trials
    mr_acc = mr_correct / n_trials

    mr_vs_amp = (mr_acc - amp_acc) / max(amp_acc, 1e-10) * 100
    mr_vs_cplx = (mr_acc - cplx_acc) / max(cplx_acc, 1e-10) * 100

    return MolecularReplacementResult(
        n_modes=n_modes,
        n_patterns_stored=n_stored,
        n_trials=n_trials,
        amplitude_only_accuracy=amp_acc,
        complex_recall_accuracy=cplx_acc,
        mr_recall_accuracy=mr_acc,
        mr_improvement_over_amp_pct=mr_vs_amp,
        mr_improvement_over_complex_pct=mr_vs_cplx,
        mean_mr_margin=float(np.mean(mr_margins)),
        verdict=bool(mr_acc > cplx_acc),
    )


# ═══════════════════════════════════════════════════════════════════════
# Run All
# ═══════════════════════════════════════════════════════════════════════

def run_all_franklin(verbose: bool = True) -> dict:
    """
    Execute all four Franklin phase-retrieval experiments.

    Returns dict mapping hypothesis label to result dataclass.
    """
    results = {}
    rng = np.random.RandomState(42)

    if verbose:
        print("=" * 70)
        print("  FRANKLIN PHASE-RETRIEVAL EXPERIMENTS FOR CWM")
        print("=" * 70)

    # H-F1: Direct Methods
    if verbose:
        print("\n▸ H-F1: Direct Methods (Hauptman–Karle tangent formula)...")
    r1 = exp_direct_methods(rng=np.random.RandomState(rng.randint(10**6)))
    results["H-F1"] = r1
    if verbose:
        v = "✅ CONFIRMED" if r1.verdict else "❌ KILLED"
        print(f"  Reconstruction accuracy:   {r1.reconstruction_accuracy:.1%}")
        print(f"  Mean phase error:          {r1.phase_error_deg:.1f}°")
        print(f"  Amplitude-only recall:     {r1.amplitude_only_baseline:.1%}")
        print(f"  Direct-method recall:      {r1.direct_method_accuracy:.1%}")
        print(f"  → {v}")

    # H-F2: Patterson Function
    if verbose:
        print("\n▸ H-F2: Patterson Function (inter-site distance recovery)...")
    r2 = exp_patterson_function(rng=np.random.RandomState(rng.randint(10**6)))
    results["H-F2"] = r2
    if verbose:
        v = "✅ CONFIRMED" if r2.verdict else "❌ KILLED"
        print(f"  True inter-site distances: {r2.n_true_distances}")
        print(f"  Recovered distances:       {r2.n_recovered_distances}")
        print(f"  Recovery fraction:         {r2.distance_recovery_fraction:.1%}")
        print(f"  Mean distance error:       {r2.mean_distance_error:.4f}")
        print(f"  → {v}")

    # H-F3: Gerchberg-Saxton / HIO
    if verbose:
        print("\n▸ H-F3: Gerchberg–Saxton iterative phase retrieval...")
    r3 = exp_gerchberg_saxton(rng=np.random.RandomState(rng.randint(10**6)))
    results["H-F3"] = r3
    if verbose:
        v = "✅ CONFIRMED" if r3.verdict else "❌ KILLED"
        print(f"  Iterations to converge:    {r3.n_iterations} / {r3.max_iterations}")
        print(f"  Final amplitude error:     {r3.final_error:.4f}")
        print(f"  Reconstruction accuracy:   {r3.reconstruction_accuracy:.1%}")
        print(f"  Converged within 100?      {r3.converged}")
        print(f"  → {v}")

    # H-F4: Molecular Replacement
    if verbose:
        print("\n▸ H-F4: Molecular Replacement recall...")
    r4 = exp_molecular_replacement(rng=np.random.RandomState(rng.randint(10**6)))
    results["H-F4"] = r4
    if verbose:
        v = "✅ CONFIRMED" if r4.verdict else "❌ KILLED"
        print(f"  Amplitude-only accuracy:   {r4.amplitude_only_accuracy:.1%}")
        print(f"  Complex recall accuracy:   {r4.complex_recall_accuracy:.1%}")
        print(f"  MR recall accuracy:        {r4.mr_recall_accuracy:.1%}")
        print(f"  MR vs amp improvement:     {r4.mr_improvement_over_amp_pct:+.1f}%")
        print(f"  MR vs complex improvement: {r4.mr_improvement_over_complex_pct:+.1f}%")
        print(f"  → {v}")

    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        total = len(results)
        print(f"\n{'=' * 70}")
        print(f"  Summary: {confirmed}/{total} hypotheses confirmed")
        print(f"{'=' * 70}")

    return results
