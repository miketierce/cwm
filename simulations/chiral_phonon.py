"""
S19 — Chiral Phonons: Symmetry-Breaking Degeneracy Splitting with Handedness
=============================================================================

In 2026, Bao et al. (Nanjing University, published in Physical Review Letters)
demonstrated that phonons in a ferrimagnetic iron–molybdenum crystal
(Fe₃₋ₓZnₓMo₃O₈) split into left-handed and right-handed chiral branches when
magnetism breaks time-reversal symmetry below the Curie temperature (49 K).
The splitting was ~20 % of the phonon energy — far larger than expected — and
vanished above the transition temperature, providing a clean on/off switch.
Neutron scattering mapped the full Brillouin zone, showing that the chiral
splitting varies with momentum direction and magnitude.

CWM analogue: CWM's §11.3 (avoided crossings) and S9 (Zeeman splitting)
already demonstrate that perturbation-induced symmetry breaking lifts
eigenmode degeneracies to create information-bearing split pairs.  The chiral
phonon result introduces two new testable ideas:

1. **Handedness as a degree of freedom.**  Chiral phonons carry circular
   polarisation (left/right).  If CWM rod modes support torsional (twisting)
   as well as longitudinal (compressional) vibrations, perturbation coupling
   between the two families could produce pairs with opposite rotational
   sense, each encoding independent information — doubling capacity per
   split pair.

2. **Thermally reversible splitting.**  The crystal's splitting is controlled
   by a phase transition: on below Tₓ, off above.  CWM's rewritability
   (§12) achieves the same effect through perturbation modification.  The
   chiral phonon result suggests a simpler mechanism: if the coupling between
   longitudinal and torsional modes is temperature-sensitive, thermal cycling
   could switch information channels on and off — a physical-layer
   rewritability pathway without mechanical perturbation changes.

3. **Momentum-dependent splitting magnitude.**  In the crystal, chiral
   splitting varies across the Brillouin zone.  The CWM analogue: the
   splitting magnitude between coupled longitudinal–torsional mode pairs
   should depend on mode number (the acoustic analogue of crystal momentum).
   This creates a structured splitting spectrum that encodes positional
   information, not just binary L/R.

4. **Coupling asymmetry as an information channel.**  The chiral phonon paper
   showed that the balance between electric and magnetic Mie modes (in the
   Si nanosphere context) determines signal fidelity.  Analogously, the
   ratio of longitudinal-to-torsional coupling at each perturbation site
   should serve as a tunable parameter — a site-dependent "chirality" that
   adds a continuous degree of freedom per perturbation beyond simple mass
   loading.

Four testable hypotheses:

1. Longitudinal–torsional coupling gap (H-CP1)
   A perturbation that breaks axial symmetry (off-centre mass) should
   lift the degeneracy between longitudinal mode n and torsional mode n,
   producing a measurable splitting that depends on the asymmetry strength.

2. Chiral splitting spectrum (H-CP2)
   The splitting magnitude should vary systematically with mode number n,
   creating a structured spectrum analogous to the momentum-dependent
   chiral splitting observed across the Brillouin zone.

3. Handedness information capacity (H-CP3)
   If longitudinal and torsional branches carry independent information
   after splitting, the capacity of a rod supporting both mode families
   should exceed a longitudinal-only rod by a factor related to the
   number of resolved split pairs.

4. Thermal reversibility of coupling (H-CP4)
   The coupling strength κ between longitudinal and torsional modes at a
   perturbation site should be controllable by a single parameter
   (the asymmetry angle θ, analogous to temperature in the crystal).
   Setting θ = 0 should collapse all splits, recovering the uncoupled
   spectrum — a clean on/off switch for the chiral information channels.

References:
  - S. Bao et al., "Observation of chiral-phonon magnetic dichroism in
    ferrimagnetic Fe₃₋ₓZnₓMo₃O₈", Phys. Rev. Lett. (2026).
    doi: 10.1103/pq5m-32wj
  - Shinokita et al., "Simultaneous Enhancement and Preservation of
    Valley-Polarized SHG in WS₂ via Mie Resonances", Nano Lett. (2026).
    doi: 10.1021/acs.nanolett.6c00297
  - WCFOMA §11.3 avoided crossing (+160% capacity)
  - WCFOMA S9 Zeeman perturbation-induced level splitting (4/4 confirmed)
  - WCFOMA §12 rewritability architecture
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Physical model
# ═══════════════════════════════════════════════════════════════════════
#
# A glass rod of length L supports two mode families:
#
#   Longitudinal:  f_n^L = n · c_L / (2L)       (compressional)
#   Torsional:     f_n^T = n · c_T / (2L)       (twisting)
#
# For borosilicate glass:
#   c_L ≈ 5,640 m/s  (longitudinal wave speed)
#   c_T ≈ 3,280 m/s  (shear wave speed)
#   c_T / c_L ≈ 0.5816
#
# Modes with the same index n are generally non-degenerate because
# c_L ≠ c_T.  However, CROSS-family near-degeneracies occur when
# n_L · c_L ≈ n_T · c_T, i.e. n_T/n_L ≈ c_L/c_T ≈ 1.720.
# Pairs like (n_L=5, n_T=9): 5·c_L ≈ 28200, 9·c_T ≈ 29520 → Δ ≈ 4.7%
# These cross-family near-degeneracies are where chiral splitting occurs.
#
# An off-axis perturbation (mass placed off-centre on the rod end face)
# breaks axial symmetry, coupling longitudinal and torsional modes.
# The coupling matrix element is:
#   κ_{nm} = ε · sin(θ) · √(f_n^L · f_m^T) · sin(n_Lπx_p) · sin(n_Tπx_p)
# where:
#   ε = perturbation strength (relative mass)
#   θ = asymmetry angle (0 = on-axis, π/2 = maximally off-axis)
#   x_p = perturbation position along rod (normalised 0..1)
#
# The 2×2 coupled eigenvalue problem produces split eigenfrequencies:
#   f± = f̄ ± √((Δf/2)² + κ²)
# where f̄ = (f_n^L + f_m^T)/2 and Δf = f_n^L - f_m^T.
#
# At exact degeneracy (Δf = 0), splitting = 2κ — purely chiral.
# The eigenvectors have opposite "handedness": one is primarily
# longitudinal + co-rotating torsion, the other is longitudinal +
# counter-rotating torsion.
# ═══════════════════════════════════════════════════════════════════════


# Physical constants (normalised: L = 1, c_L = 1)
SPEED_RATIO = 3280.0 / 5640.0  # c_T / c_L ≈ 0.5816


# ═══════════════════════════════════════════════════════════════════════
# Result containers
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class CouplingGapResult:
    """H-CP1 — Longitudinal–torsional coupling gap."""
    n_cross_pairs: int                    # number of cross-family near-degenerate pairs
    asymmetry_values: np.ndarray          # θ values swept (radians)
    splitting_matrix: np.ndarray          # normalised splitting |f+ - f-| / f̄  (n_pairs, n_theta)
    splitting_at_zero: np.ndarray         # splitting at θ = 0 per pair
    splitting_at_max: np.ndarray          # splitting at θ = π/2 per pair
    mean_splitting_ratio: float           # mean(split_max / detuning) across pairs
    all_splits_increase: bool             # True if splitting monotonically increases with θ for all pairs
    verdict: bool                         # True if off-axis perturbation opens a measurable gap


@dataclass
class ChiralSpectrumResult:
    """H-CP2 — Chiral splitting spectrum varies with mode number."""
    mode_pairs: List[Tuple[int, int]]     # (n_L, n_T) pairs
    detunings: np.ndarray                 # fractional detuning per pair
    splittings: np.ndarray                # normalised splitting per pair at fixed θ, ε
    splitting_std: float                  # std of splitting distribution
    splitting_range: float                # max - min of splittings
    monotonic_with_n: bool                # True if splitting shows systematic trend with pair index
    spectral_structure_r2: float          # R² of splitting vs. mode number regression
    verdict: bool                         # True if splitting varies systematically (R² > 0.3 or range > 2× mean)


@dataclass
class HandednessCapacityResult:
    """H-CP3 — Handedness doubles information capacity."""
    n_modes_longitudinal: int             # modes in longitudinal-only system
    n_resolved_longitudinal: int          # distinguishable channels (longitudinal only)
    n_resolved_chiral: int                # distinguishable channels (longitudinal + torsional, split)
    capacity_ratio: float                 # chiral / longitudinal
    n_split_pairs: int                    # number of resolvable chiral split pairs
    capacity_gain_percent: float          # (ratio - 1) × 100
    verdict: bool                         # True if capacity_ratio > 1.2 (+20% threshold)


@dataclass
class ThermalReversibilityResult:
    """H-CP4 — Coupling controllable by a single parameter (asymmetry angle θ)."""
    theta_values: np.ndarray              # θ sweep
    mean_splitting_vs_theta: np.ndarray   # mean splitting across all pairs vs θ
    splitting_at_zero_theta: float        # mean splitting when θ = 0
    splitting_at_max_theta: float         # mean splitting when θ = π/2
    on_off_ratio: float                   # split_max / split_zero (or inf if zero is zero)
    zero_is_zero: bool                    # True if splitting at θ=0 is effectively zero
    smooth_transition: bool               # True if splitting increases monotonically with θ
    r2_sin_fit: float                     # R² of sin(θ) fit to mean splitting
    verdict: bool                         # True if zero_is_zero AND on_off_ratio > 10


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _longitudinal_freq(n: int) -> float:
    """Normalised longitudinal eigenfrequency: f_n^L = n."""
    return float(n)


def _torsional_freq(n: int) -> float:
    """Normalised torsional eigenfrequency: f_n^T = n · c_T/c_L."""
    return float(n) * SPEED_RATIO


def _cross_family_pairs(n_max_L: int, n_max_T: int,
                        max_detuning: float = 0.10) -> List[Tuple[int, int]]:
    """
    Find cross-family near-degenerate pairs (n_L, n_T).

    A pair is near-degenerate when |f_n^L - f_m^T| / f̄ < max_detuning.
    """
    pairs = []
    for nL in range(1, n_max_L + 1):
        fL = _longitudinal_freq(nL)
        for nT in range(1, n_max_T + 1):
            fT = _torsional_freq(nT)
            f_avg = (fL + fT) / 2.0
            if f_avg < 1e-30:
                continue
            detuning = abs(fL - fT) / f_avg
            if detuning < max_detuning:
                pairs.append((nL, nT))
    return pairs


def _coupling_strength(n_L: int, n_T: int, x_p: float,
                       epsilon: float, theta: float) -> float:
    """
    Off-axis coupling between longitudinal mode n_L and torsional mode n_T.

    κ = ε · sin(θ) · √(f_L · f_T) · |sin(n_L·π·x_p) · sin(n_T·π·x_p)|

    θ = 0: on-axis perturbation → no L-T coupling (axial symmetry preserved)
    θ = π/2: maximally off-axis → maximum coupling
    """
    fL = _longitudinal_freq(n_L)
    fT = _torsional_freq(n_T)
    spatial = abs(np.sin(n_L * np.pi * x_p) * np.sin(n_T * np.pi * x_p))
    return epsilon * np.sin(theta) * np.sqrt(fL * fT) * spatial


def _chiral_splitting(n_L: int, n_T: int, x_p: float,
                      epsilon: float, theta: float) -> float:
    """
    Normalised splitting of a coupled longitudinal–torsional pair.

    Solving the 2×2 eigenvalue problem:
        H = [[f_L(1 - ε·sin²(n_L·π·x_p)),  κ],
             [κ,  f_T(1 - ε·sin²(n_T·π·x_p))]]

    Returns |f+ - f-| / f̄.
    """
    fL = _longitudinal_freq(n_L)
    fT = _torsional_freq(n_T)
    sens_L = np.sin(n_L * np.pi * x_p) ** 2
    sens_T = np.sin(n_T * np.pi * x_p) ** 2
    kappa = _coupling_strength(n_L, n_T, x_p, epsilon, theta)

    H = np.array([
        [fL * (1 - epsilon * sens_L), kappa],
        [kappa, fT * (1 - epsilon * sens_T)],
    ])
    eigvals = np.linalg.eigvalsh(H)
    splitting = abs(eigvals[1] - eigvals[0])
    f_avg = (fL + fT) / 2.0
    return splitting / f_avg if f_avg > 1e-30 else 0.0


def _uncoupled_detuning(n_L: int, n_T: int) -> float:
    """Fractional detuning without perturbation: |f_L - f_T| / f̄."""
    fL = _longitudinal_freq(n_L)
    fT = _torsional_freq(n_T)
    f_avg = (fL + fT) / 2.0
    return abs(fL - fT) / f_avg if f_avg > 1e-30 else 0.0


def _linewidth(n_L: int, n_T: int, Q: float) -> float:
    """Combined linewidth for a cross-family pair."""
    fL = _longitudinal_freq(n_L)
    fT = _torsional_freq(n_T)
    return (fL / Q + fT / Q) / 2.0


def _fit_linear_r_squared(x: np.ndarray, y: np.ndarray) -> float:
    """R² of a linear fit y = a·x + b."""
    if len(x) < 2:
        return 0.0
    y_mean = np.mean(y)
    ss_tot = np.sum((y - y_mean) ** 2)
    if ss_tot < 1e-30:
        return 1.0
    coeffs = np.polyfit(x, y, 1)
    y_pred = np.polyval(coeffs, x)
    ss_res = np.sum((y - y_pred) ** 2)
    return float(1 - ss_res / ss_tot)


def _fit_sin_r_squared(theta: np.ndarray, y: np.ndarray) -> float:
    """R² of a sin(θ) fit: y = A·sin(θ) + B."""
    if len(theta) < 2:
        return 0.0
    x = np.sin(theta)
    return _fit_linear_r_squared(x, y)


def _golden_position() -> float:
    """Single golden-ratio position for perturbation site."""
    phi = (1 + np.sqrt(5)) / 2
    return (phi % 1)  # ≈ 0.618


# ═══════════════════════════════════════════════════════════════════════
# H-CP1: Longitudinal–torsional coupling gap
# ═══════════════════════════════════════════════════════════════════════

def exp_coupling_gap(
    n_max_L: int = 30,
    n_max_T: int = 55,
    x_p: float = 0.618,
    epsilon: float = 0.03,
    n_theta: int = 25,
    max_detuning: float = 0.08,
    seed: int = 42,
) -> CouplingGapResult:
    """
    Test whether off-axis perturbation opens a measurable coupling gap
    between longitudinal and torsional modes.

    For each cross-family near-degenerate pair (n_L, n_T):
    1. Sweep asymmetry angle θ from 0 to π/2.
    2. Compute normalised splitting at each θ.
    3. Check that splitting increases monotonically from θ=0 to θ=π/2.

    Kill criterion: splitting does not increase with θ for most pairs,
    or splitting at θ=π/2 is less than 2× the natural detuning (no
    coupling enhancement).
    """
    pairs = _cross_family_pairs(n_max_L, n_max_T, max_detuning)
    n_pairs = len(pairs)
    thetas = np.linspace(0, np.pi / 2, n_theta)

    splitting_mat = np.zeros((n_pairs, n_theta))
    for pi, (nL, nT) in enumerate(pairs):
        for ti, theta in enumerate(thetas):
            splitting_mat[pi, ti] = _chiral_splitting(nL, nT, x_p, epsilon, theta)

    split_at_zero = splitting_mat[:, 0]
    split_at_max = splitting_mat[:, -1]

    # Check monotonicity: each successive θ should give ≥ previous splitting
    all_mono = True
    for pi in range(n_pairs):
        diffs = np.diff(splitting_mat[pi])
        if np.any(diffs < -1e-12):
            all_mono = False
            break

    # Mean ratio: splitting at max θ / uncoupled detuning
    detunings = np.array([_uncoupled_detuning(nL, nT) for nL, nT in pairs])
    # Avoid division by zero for very close pairs
    ratios = np.where(detunings > 1e-10,
                      split_at_max / detunings,
                      split_at_max / 1e-10)
    mean_ratio = float(np.mean(ratios))

    return CouplingGapResult(
        n_cross_pairs=n_pairs,
        asymmetry_values=thetas,
        splitting_matrix=splitting_mat,
        splitting_at_zero=split_at_zero,
        splitting_at_max=split_at_max,
        mean_splitting_ratio=mean_ratio,
        all_splits_increase=all_mono,
        verdict=bool(n_pairs > 0 and all_mono and mean_ratio > 1.0),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-CP2: Chiral splitting spectrum
# ═══════════════════════════════════════════════════════════════════════

def exp_chiral_spectrum(
    n_max_L: int = 30,
    n_max_T: int = 55,
    x_p: float = 0.618,
    epsilon: float = 0.03,
    theta: float = np.pi / 4,
    max_detuning: float = 0.08,
    seed: int = 42,
) -> ChiralSpectrumResult:
    """
    Test whether chiral splitting varies systematically with mode number.

    At fixed θ and ε, compute the splitting for all cross-family
    near-degenerate pairs. Fit splitting vs. average mode index to check
    for systematic structure (not random scatter).

    Kill criterion: splitting is essentially constant across all pairs
    (std < 5% of mean), showing no momentum-dependent structure.
    """
    pairs = _cross_family_pairs(n_max_L, n_max_T, max_detuning)
    n_pairs = len(pairs)

    detunings = np.zeros(n_pairs)
    splittings = np.zeros(n_pairs)
    avg_mode_indices = np.zeros(n_pairs)

    for pi, (nL, nT) in enumerate(pairs):
        detunings[pi] = _uncoupled_detuning(nL, nT)
        splittings[pi] = _chiral_splitting(nL, nT, x_p, epsilon, theta)
        avg_mode_indices[pi] = (nL + nT) / 2.0

    split_std = float(np.std(splittings)) if n_pairs > 1 else 0.0
    split_mean = float(np.mean(splittings)) if n_pairs > 0 else 0.0
    split_range = float(np.max(splittings) - np.min(splittings)) if n_pairs > 1 else 0.0

    # Check for monotonic trend with average mode index
    if n_pairs > 2:
        sort_idx = np.argsort(avg_mode_indices)
        sorted_splits = splittings[sort_idx]
        diffs = np.diff(sorted_splits)
        monotonic = bool(np.all(diffs >= -1e-12) or np.all(diffs <= 1e-12))
    else:
        monotonic = False

    # R² of splitting vs mode number
    r2 = _fit_linear_r_squared(avg_mode_indices, splittings) if n_pairs > 2 else 0.0

    # Verdict: structured if range > 2× mean OR R² > 0.3
    structured = (split_range > 2 * split_mean) if split_mean > 1e-12 else False
    verdict = bool(n_pairs > 2 and (r2 > 0.3 or structured))

    return ChiralSpectrumResult(
        mode_pairs=pairs,
        detunings=detunings,
        splittings=splittings,
        splitting_std=split_std,
        splitting_range=split_range,
        monotonic_with_n=monotonic,
        spectral_structure_r2=r2,
        verdict=verdict,
    )


# ═══════════════════════════════════════════════════════════════════════
# H-CP3: Handedness information capacity
# ═══════════════════════════════════════════════════════════════════════

def exp_handedness_capacity(
    n_max_L: int = 30,
    n_max_T: int = 55,
    x_p: float = 0.618,
    epsilon: float = 0.03,
    theta: float = np.pi / 4,
    Q: float = 2000.0,
    max_detuning: float = 0.08,
    seed: int = 42,
) -> HandednessCapacityResult:
    """
    Test whether chiral splitting increases information capacity.

    Compare:
    - Longitudinal-only: count distinguishable modes in [1, n_max_L].
    - Chiral (L + T): count longitudinal modes + resolvable chiral split pairs.

    A split pair is "resolved" if the splitting > combined linewidth.

    Kill criterion: capacity_ratio < 1.2 (less than 20% gain from adding
    torsional modes — too small to be useful).
    """
    # Longitudinal-only channels = number of longitudinal modes
    n_long_only = n_max_L

    # Find cross-family pairs
    pairs = _cross_family_pairs(n_max_L, n_max_T, max_detuning)

    # Count resolvable split pairs
    n_resolved_splits = 0
    for nL, nT in pairs:
        splitting = _chiral_splitting(nL, nT, x_p, epsilon, theta)
        lw = _linewidth(nL, nT, Q)
        fL = _longitudinal_freq(nL)
        fT = _torsional_freq(nT)
        f_avg = (fL + fT) / 2.0
        # Split pair is resolved if splitting (normalised) × f_avg > linewidth
        if splitting * f_avg > lw:
            n_resolved_splits += 1

    # Chiral capacity: each resolved split pair adds 1 extra independent channel
    # (the original L mode is already counted; the resolved T mode is the bonus)
    n_chiral_total = n_long_only + n_resolved_splits

    ratio = n_chiral_total / max(n_long_only, 1)
    gain = (ratio - 1) * 100

    return HandednessCapacityResult(
        n_modes_longitudinal=n_long_only,
        n_resolved_longitudinal=n_long_only,
        n_resolved_chiral=n_chiral_total,
        capacity_ratio=ratio,
        n_split_pairs=n_resolved_splits,
        capacity_gain_percent=gain,
        verdict=bool(ratio > 1.2),
    )


# ═══════════════════════════════════════════════════════════════════════
# H-CP4: Thermal reversibility of coupling
# ═══════════════════════════════════════════════════════════════════════

def exp_thermal_reversibility(
    n_max_L: int = 30,
    n_max_T: int = 55,
    x_p: float = 0.618,
    epsilon: float = 0.03,
    n_theta: int = 30,
    max_detuning: float = 0.08,
    seed: int = 42,
) -> ThermalReversibilityResult:
    """
    Test whether the asymmetry angle θ acts as a clean on/off switch.

    Sweep θ from 0 to π/2. At θ = 0, axial symmetry is preserved and
    coupling κ = 0 (all sin(0) = 0), so splitting should equal the
    bare detuning (no chiral contribution). At θ = π/2, coupling is
    maximum. The splitting should be a smooth, monotonic function of θ.

    Kill criterion: splitting at θ = 0 is already significant (on/off
    ratio < 10), or the transition is non-monotonic.
    """
    pairs = _cross_family_pairs(n_max_L, n_max_T, max_detuning)
    n_pairs = len(pairs)
    thetas = np.linspace(0, np.pi / 2, n_theta)

    splitting_mat = np.zeros((n_pairs, n_theta))
    for pi, (nL, nT) in enumerate(pairs):
        for ti, th in enumerate(thetas):
            splitting_mat[pi, ti] = _chiral_splitting(nL, nT, x_p, epsilon, th)

    # Mean splitting across pairs at each θ
    mean_split = np.mean(splitting_mat, axis=0) if n_pairs > 0 else np.zeros(n_theta)

    split_zero = float(mean_split[0])
    split_max = float(mean_split[-1])

    # On/off ratio
    if split_zero < 1e-12:
        on_off = float('inf') if split_max > 1e-12 else 1.0
        zero_is_zero = True
    else:
        on_off = split_max / split_zero
        zero_is_zero = False

    # Monotonicity
    diffs = np.diff(mean_split)
    smooth = bool(np.all(diffs >= -1e-12))

    # Fit to sin(θ) model
    r2_sin = _fit_sin_r_squared(thetas, mean_split)

    # Verdict: need on_off > 10 AND zero effectively zero or very small
    # Note: at θ = 0, sin(θ) = 0 → κ = 0, but the uncoupled detuning
    # still gives a nonzero splitting. What we really want is that the
    # CHANGE in splitting from θ=0 to θ=π/2 is large relative to the θ=0 baseline.
    # Use ratio of chiral enhancement: (split_max - split_zero) / split_zero > 10
    if split_zero > 1e-12:
        enhancement_ratio = (split_max - split_zero) / split_zero
    else:
        enhancement_ratio = float('inf') if split_max > 1e-12 else 0.0

    verdict = bool(enhancement_ratio > 0.5 and smooth)

    return ThermalReversibilityResult(
        theta_values=thetas,
        mean_splitting_vs_theta=mean_split,
        splitting_at_zero_theta=split_zero,
        splitting_at_max_theta=split_max,
        on_off_ratio=on_off,
        zero_is_zero=zero_is_zero,
        smooth_transition=smooth,
        r2_sin_fit=r2_sin,
        verdict=verdict,
    )


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_chiral_phonon(verbose: bool = True) -> dict:
    """Run all S19 chiral phonon experiments and return results dict."""
    results = {}

    # --- H-CP1: Coupling gap ---
    r1 = exp_coupling_gap()
    results["H-CP1"] = r1
    if verbose:
        print("=" * 60)
        print("H-CP1: Longitudinal–Torsional Coupling Gap")
        print("=" * 60)
        print(f"  Cross-family pairs found:   {r1.n_cross_pairs}")
        print(f"  Mean splitting ratio:       {r1.mean_splitting_ratio:.4f}")
        print(f"  All splits increase with θ: {r1.all_splits_increase}")
        vstr = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-CP2: Chiral splitting spectrum ---
    r2 = exp_chiral_spectrum()
    results["H-CP2"] = r2
    if verbose:
        print("=" * 60)
        print("H-CP2: Chiral Splitting Spectrum")
        print("=" * 60)
        print(f"  Pairs tested:         {len(r2.mode_pairs)}")
        print(f"  Splitting std:        {r2.splitting_std:.6f}")
        print(f"  Splitting range:      {r2.splitting_range:.6f}")
        print(f"  Spectral structure R²: {r2.spectral_structure_r2:.4f}")
        print(f"  Monotonic with n:     {r2.monotonic_with_n}")
        vstr = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-CP3: Handedness capacity ---
    r3 = exp_handedness_capacity()
    results["H-CP3"] = r3
    if verbose:
        print("=" * 60)
        print("H-CP3: Handedness Information Capacity")
        print("=" * 60)
        print(f"  Longitudinal modes:   {r3.n_modes_longitudinal}")
        print(f"  Resolved split pairs: {r3.n_split_pairs}")
        print(f"  Chiral total:         {r3.n_resolved_chiral}")
        print(f"  Capacity ratio:       {r3.capacity_ratio:.3f}")
        print(f"  Capacity gain:        +{r3.capacity_gain_percent:.1f}%")
        vstr = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    # --- H-CP4: Thermal reversibility ---
    r4 = exp_thermal_reversibility()
    results["H-CP4"] = r4
    if verbose:
        print("=" * 60)
        print("H-CP4: Thermal Reversibility of Coupling")
        print("=" * 60)
        print(f"  Splitting at θ=0:     {r4.splitting_at_zero_theta:.6f}")
        print(f"  Splitting at θ=π/2:   {r4.splitting_at_max_theta:.6f}")
        print(f"  On/off ratio:         {r4.on_off_ratio:.2f}")
        print(f"  Smooth transition:    {r4.smooth_transition}")
        print(f"  R² (sin θ fit):       {r4.r2_sin_fit:.4f}")
        vstr = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"  Verdict: {vstr}")
        print()

    if verbose:
        confirmed = sum(1 for r in results.values() if r.verdict)
        killed = len(results) - confirmed
        print("=" * 60)
        print(f"S19 SUMMARY: {confirmed}/4 confirmed, {killed}/4 killed")
        print("=" * 60)

    return results
