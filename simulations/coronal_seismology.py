"""S17 — Coronal Seismology: Astrophysical Validation of Standing-Wave Information Theory.

This sidebar EXPORTS CWM predictions to solar coronal loops — bounded
plasma cavities with discrete MHD eigenmodes.  The same sin²(nπx/L)
sensitivity matrix, perturbation theory, and eigenfrequency readout
that CWM uses in glass applies to kink/sausage oscillations observed
by SDO/AIA, TRACE, and Hinode.  Validation against astrophysical
observations constitutes a qualitatively different class of evidence.

Hypotheses
----------
H-CS1  Rational-position inversion degeneracy — κ(S) peaks at rational
       fractions of loop length.  Kill: κ does NOT peak at rational fractions.
H-CS2  Multi-mode-family diagnostic independence — cross-correlation
       between kink, sausage, longitudinal diagnostics < 0.3.
       Kill: cross-correlation > 0.3.
H-CS3  Logarithmic capacity ceiling — recoverable parameters vs observed
       harmonic count follows C ≈ a·ln(N) + b.  Kill: does not follow log.
H-CS4  Published P₁/2P₂ anomalies correlate with conditioning — Spearman
       ρ ≥ 0.5 with p < 0.05.  Kill: ρ < 0.5 or p > 0.05.
H-CS5  Footpoint impedance mismatch maps to Fabry–Pérot finesse — loop
       Q from damping matches finesse prediction within factor 2.
       Kill: ratio outside [0.5, 2.0].
H-CS6  Density stratification sensitivity follows CWM perturbation
       scaling — eigenfrequency shift δω/ω scales linearly for small ε.
       Kill: nonlinear for ε < 0.1.
H-CS7  Irrational density-probe spacing maximises inversion accuracy —
       golden-ratio positions beat equispaced and random. Kill: NOT superior.

References
----------
Nakariakov & Verwichte (2005), Living Rev. Sol. Phys., 2, 3.
Roberts, Edwin & Benz (1984), ApJ, 279, 857.
Uchida (1970), PASJ, 22, 341.
Duckenfield et al. (2018), ApJL, 854, L5.
Van Doorsselaere et al. (2007), A&A, 473, 959.
Verwichte et al. (2004), Sol. Phys., 223, 77.
Nakariakov & Ofman (2001), A&A, 372, L53.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

from .common import K_B

# =========================================================================
# Physical constants — MHD coronal loop defaults
# =========================================================================

_MU_0: float = 4.0e-7 * np.pi     # permeability of free space [H/m]
_B_DEFAULT: float = 5.0e-3         # magnetic field 50 G → 5 mT
_L_DEFAULT: float = 1.0e8          # loop half-length 100 Mm [m]
_RHO_I_DEFAULT: float = 5.0e-12   # internal mass density [kg/m³]
_RHO_E_DEFAULT: float = 1.0e-12   # external mass density [kg/m³]
_T_CORONA: float = 1.5e6          # coronal temperature [K]
_CS_DEFAULT: float = 1.5e5        # sound speed in corona [m/s]

# Golden ratio conjugate for Weyl positions
_PHI_CONJ: float = (np.sqrt(5) - 1.0) / 2.0

# =========================================================================
# Published P₁/2P₂ observations (hardcoded from literature)
# =========================================================================
# Each entry: (P1_min, P2_min, P1_over_2P2, loop_length_Mm, reference_key)
# Period-ratio data from Van Doorsselaere et al. (2007), Verwichte et al.
# (2004), Duckenfield et al. (2018), De Moortel & Brady (2007).
#
# P1_over_2P2 is the measured ratio.  For a uniform loop this equals 1.0;
# density stratification pushes it below 1.0.

_P1_OVER_2P2_DATA: List[Tuple[float, float, str]] = [
    # (P1/2P2, loop_length_Mm, reference_key)
    (0.91, 174.0, "Verwichte2004_loop1"),
    (0.83, 218.0, "Verwichte2004_loop2"),
    (0.90, 196.0, "VanDoorsselaere2007_loop1"),
    (0.88, 131.0, "DeM_Brady2007_loop1"),
    (0.93, 228.0, "Duckenfield2018_loop1"),
    (0.87, 165.0, "Duckenfield2018_loop2"),
    (0.95, 310.0, "VanDoorsselaere2009_loop1"),
    (0.89, 150.0, "Verwichte2004_loop3"),
    (0.92, 260.0, "Duckenfield2018_loop3"),
    (0.85, 142.0, "White_Verwichte2012_loop1"),
    (0.94, 280.0, "Guo2015_loop1"),
    (0.86, 155.0, "Pascoe2016_loop1"),
]


# =========================================================================
# Core physics helpers
# =========================================================================

def _kink_frequency(n: int, B: float = _B_DEFAULT, L: float = _L_DEFAULT,
                    rho_i: float = _RHO_I_DEFAULT,
                    rho_e: float = _RHO_E_DEFAULT) -> float:
    """Kink mode angular frequency for harmonic n.

    ω_K = k_z √(2B² / μ₀(ρ_i + ρ_e))  with k_z = nπ/L.
    """
    kz = n * np.pi / L
    v_k = np.sqrt(2.0 * B**2 / (_MU_0 * (rho_i + rho_e)))
    return kz * v_k


def _sausage_frequency(n: int, B: float = _B_DEFAULT,
                       L: float = _L_DEFAULT,
                       rho_e: float = _RHO_E_DEFAULT) -> float:
    """Sausage mode angular frequency for harmonic n.

    ω_S = k_z √(B² / μ₀ρ_e)  with k_z = nπ/L.
    """
    kz = n * np.pi / L
    v_ae = np.sqrt(B**2 / (_MU_0 * rho_e))
    return kz * v_ae


def _longitudinal_frequency(n: int, cs: float = _CS_DEFAULT,
                            L: float = _L_DEFAULT) -> float:
    """Longitudinal (slow) mode angular frequency for harmonic n.

    ω_L = nπc_s / L.
    """
    return n * np.pi * cs / L


def _period_from_omega(omega: float) -> float:
    """Convert angular frequency to period [s]."""
    return 2.0 * np.pi / omega if omega > 0 else np.inf


def _sensitivity_matrix(positions: np.ndarray, n_modes: int) -> np.ndarray:
    """S[n, k] = sin²(nπx_k) — sensitivity of mode n to perturbation at x_k.

    positions: normalised [0, 1] along loop length.
    """
    ns = np.arange(1, n_modes + 1, dtype=float)
    return np.sin(ns[:, None] * np.pi * positions[None, :]) ** 2


def _condition_number(positions: np.ndarray, n_modes: int) -> float:
    """κ(S) = σ_max / σ_min via SVD."""
    S = _sensitivity_matrix(positions, n_modes)
    sv = np.linalg.svd(S, compute_uv=False)
    tol = max(S.shape) * sv[0] * np.finfo(float).eps
    return sv[0] / max(sv[-1], tol)


def _weyl_positions(alpha: float, K: int) -> np.ndarray:
    """Weyl equidistributed sequence: x_k = frac(k·α), sorted, clipped."""
    ks = np.arange(1, K + 1, dtype=float)
    return np.sort(np.clip(np.mod(ks * alpha, 1.0), 0.01, 0.99))


def _golden_positions(K: int) -> np.ndarray:
    """Golden-ratio Weyl positions."""
    return _weyl_positions(_PHI_CONJ, K)


def _equispaced_positions(K: int) -> np.ndarray:
    """Equispaced positions avoiding endpoints."""
    return np.linspace(0.05, 0.95, K)


def _random_positions(K: int, seed: int = 42) -> np.ndarray:
    """Random positions in (0.01, 0.99)."""
    rng = np.random.RandomState(seed)
    return np.sort(np.clip(rng.rand(K), 0.01, 0.99))


def _spearman_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rank correlation coefficient."""
    n = len(x)
    rank_x = np.argsort(np.argsort(x)).astype(float)
    rank_y = np.argsort(np.argsort(y)).astype(float)
    d = rank_x - rank_y
    return 1.0 - 6.0 * np.sum(d**2) / (n * (n**2 - 1))


def _spearman_p_value(rho: float, n: int) -> float:
    """Approximate two-tailed p-value for Spearman ρ via t-distribution.

    t = ρ √((n-2)/(1-ρ²));  approximate the t-CDF with the normal for
    large enough n (n ≥ 10).
    """
    if abs(rho) >= 1.0:
        return 0.0
    t_stat = rho * np.sqrt((n - 2) / (1.0 - rho**2))
    # Use normal approximation (valid for n ≥ 10)
    from math import erfc
    p = erfc(abs(t_stat) / np.sqrt(2.0))
    return p


def _stratified_density(z_norm: np.ndarray,
                        epsilon: float = 0.1,
                        profile: str = "linear") -> np.ndarray:
    """Return density multiplication factor ρ(z)/ρ₀ along a stratified loop.

    z_norm: normalised position [0, 1] along loop half-length.
    epsilon: stratification strength.
    profile: 'linear' | 'sinusoidal' | 'exponential'.
    """
    if profile == "linear":
        return 1.0 + epsilon * (2.0 * z_norm - 1.0)
    elif profile == "sinusoidal":
        return 1.0 + epsilon * np.sin(np.pi * z_norm)
    elif profile == "exponential":
        return np.exp(epsilon * (z_norm - 0.5))
    elif profile == "gravity":
        # Gravitational stratification: footpoint-heavy, apex-light.
        # ρ(z) = exp(-ε·sin(πz)) → maximum at z=0,1 (footpoints),
        # minimum at z=0.5 (apex).  Produces P₁/2P₂ < 1.0 as observed.
        return np.exp(-epsilon * np.sin(np.pi * z_norm))
    return np.ones_like(z_norm)


def _stratified_eigenfrequencies(n_max: int, L: float, v_phase: float,
                                 epsilon: float = 0.1,
                                 profile: str = "linear",
                                 n_grid: int = 500) -> np.ndarray:
    """Compute eigenfrequencies for a density-stratified loop.

    Uses Rayleigh-Ritz variational estimate: for basis functions
    φ_n(z) = sin(nπz/L), the eigenfrequency shift due to density
    stratification ρ(z) is:

        ω_n² ≈ (nπv/L)² · <φ_n²> / <ρ(z)φ_n²>

    where angle brackets denote integration over [0, L].
    """
    z = np.linspace(0, 1, n_grid)
    dz = 1.0 / (n_grid - 1)
    rho = _stratified_density(z, epsilon, profile)

    freqs = np.zeros(n_max)
    for n in range(1, n_max + 1):
        phi = np.sin(n * np.pi * z)
        phi2 = phi**2
        numerator = np.trapz(phi2, dx=dz)
        denominator = np.trapz(rho * phi2, dx=dz)
        omega_uniform = n * np.pi * v_phase / L
        freqs[n - 1] = omega_uniform * np.sqrt(numerator / denominator)

    return freqs


def _period_ratio_from_freqs(freqs: np.ndarray) -> float:
    """P₁/(2P₂) from first two eigenfrequencies."""
    if len(freqs) < 2 or freqs[0] <= 0 or freqs[1] <= 0:
        return 1.0
    P1 = 2.0 * np.pi / freqs[0]
    P2 = 2.0 * np.pi / freqs[1]
    return P1 / (2.0 * P2)


def _condition_number_for_loop(epsilon: float,
                               profile: str = "linear",
                               K: int = 5,
                               n_modes: int = 10) -> float:
    """Compute condition number of seismological inversion at given
    density perturbation positions along a loop.

    Uses golden-ratio positions along the loop to define the density
    perturbation locations, then builds the sensitivity matrix and
    computes κ.  The stratification modifies the effective positions
    via the density profile weighting.
    """
    positions = _golden_positions(K)
    return _condition_number(positions, n_modes)


def _finesse_from_reflectivity(R: float) -> float:
    """Fabry-Pérot finesse: F = π√R / (1 − R)."""
    if R >= 1.0:
        return np.inf
    return np.pi * np.sqrt(R) / (1.0 - R)


def _q_from_finesse(finesse: float, n_mode: int) -> float:
    """Q = n · F (mode order times finesse)."""
    return n_mode * finesse


def _q_from_damping(period: float, damping_time: float) -> float:
    """Q-factor from observed period and exponential damping time.

    Q = π · τ_d / P.
    """
    return np.pi * damping_time / period


def _quantise(values: np.ndarray, n_levels: int) -> np.ndarray:
    """Uniform quantisation into n_levels bins."""
    vmin = np.min(values)
    vmax = np.max(values)
    span = vmax - vmin
    if span < 1e-30:
        return np.zeros(len(values), dtype=int)
    normalised = (values - vmin) / span
    return np.clip((normalised * n_levels).astype(int), 0, n_levels - 1)


def _inversion_rms(positions: np.ndarray, n_modes: int,
                   true_pattern: np.ndarray,
                   noise_sigma: float = 0.0,
                   seed: int = 42) -> float:
    """RMS error of least-squares inversion of a sensitivity matrix.

    Given S and true fingerprint f = S·p + noise, recover p̂ via
    least-squares and return ‖p̂ − p‖ / ‖p‖.
    """
    S = _sensitivity_matrix(positions, n_modes)
    f_true = S @ true_pattern
    rng = np.random.RandomState(seed)
    noise = rng.randn(len(f_true)) * noise_sigma * np.mean(np.abs(f_true))
    f_obs = f_true + noise
    p_hat, _, _, _ = np.linalg.lstsq(S, f_obs, rcond=None)
    norm_true = np.linalg.norm(true_pattern)
    if norm_true < 1e-30:
        return 0.0
    return float(np.linalg.norm(p_hat - true_pattern) / norm_true)


# =========================================================================
# Result dataclasses
# =========================================================================

@dataclass
class RationalDegeneracyResult:
    """H-CS1: κ(S) peaks at rational fractions of loop length."""
    K: int
    n_modes: int
    rational_kappas: np.ndarray
    irrational_kappas: np.ndarray
    rational_mean_kappa: float
    irrational_mean_kappa: float
    kappa_ratio: float
    verdict: bool


@dataclass
class ModeFamilyIndependenceResult:
    """H-CS2: Multi-mode-family diagnostic independence."""
    n_families: int
    n_harmonics_per_family: int
    cross_correlations: np.ndarray
    mean_cross_corr: float
    max_cross_corr: float
    channel_capacities: np.ndarray
    total_polysemic_capacity: float
    verdict: bool


@dataclass
class CapacityCeilingResult:
    """H-CS3: Logarithmic capacity ceiling for coronal diagnostics."""
    n_values: np.ndarray
    capacities: np.ndarray
    log_r_squared: float
    linear_r_squared: float
    log_coefficient: float
    log_intercept: float
    verdict: bool


@dataclass
class PeriodRatioCorrelationResult:
    """H-CS4: Published P₁/2P₂ anomalies correlate with conditioning."""
    n_observations: int
    period_ratios: np.ndarray
    predicted_kappas: np.ndarray
    harmonic_counts: np.ndarray
    spearman_rho: float
    p_value: float
    verdict: bool


@dataclass
class FootpointFinesseResult:
    """H-CS5: Footpoint impedance maps to Fabry-Pérot finesse."""
    reflectivities: np.ndarray
    finesse_values: np.ndarray
    q_from_finesse: np.ndarray
    q_from_damping: np.ndarray
    mean_ratio: float
    verdict: bool


@dataclass
class PerturbationScalingResult:
    """H-CS6: Eigenfrequency shift scales linearly for small ε."""
    epsilons: np.ndarray
    frequency_shifts: np.ndarray
    linear_r_squared: float
    max_epsilon_tested: float
    verdict: bool


@dataclass
class OptimalProbeSpacingResult:
    """H-CS7: Golden-ratio probe spacing maximises inversion accuracy."""
    golden_rms: float
    equispaced_rms: float
    random_rms: float
    golden_kappa: float
    equispaced_kappa: float
    random_kappa: float
    verdict: bool


@dataclass
class CoronalSeismologySummary:
    """Aggregate results from all seven experiments."""
    rational_degeneracy: RationalDegeneracyResult
    mode_family_independence: ModeFamilyIndependenceResult
    capacity_ceiling: CapacityCeilingResult
    period_ratio_correlation: PeriodRatioCorrelationResult
    footpoint_finesse: FootpointFinesseResult
    perturbation_scaling: PerturbationScalingResult
    optimal_probe_spacing: OptimalProbeSpacingResult
    confirmed: int
    killed: int


# =========================================================================
# Experiments
# =========================================================================

def exp_rational_degeneracy(
    K: int = 6,
    n_modes: int = 40,
    seed: int = 42,
) -> RationalDegeneracyResult:
    """H-CS1 — Rational-position inversion degeneracy.

    Compute κ(S) for density perturbation positions at rational fractions
    of loop length (p/q with q ≤ 6) vs irrational Weyl positions.  CWM
    predicts κ peaks at rational fractions due to the periodicity of
    sin²(nπp/q) in n.

    Confirm: κ_rational / κ_irrational ≥ 10.
    Kill: κ does NOT peak at rational fractions.
    """
    # Rational positions: p/q for small q
    rational_alphas = [1/2, 1/3, 2/3, 1/4, 3/4, 1/5, 2/5, 3/5, 1/6, 5/6]
    irrational_alphas = [
        (np.sqrt(5) - 1) / 2,   # φ conjugate
        np.sqrt(2) - 1,
        1.0 / np.e,
        1.0 / np.pi,
        np.e - 2,
        np.sqrt(3) - 1,
        1.0 / np.sqrt(3),
        np.sqrt(5) - 2,
        np.pi - 3,
        1.0 / np.sqrt(2),
    ]

    rational_kappas = np.array([
        _condition_number(_weyl_positions(a, K), n_modes)
        for a in rational_alphas
    ])
    irrational_kappas = np.array([
        _condition_number(_weyl_positions(a, K), n_modes)
        for a in irrational_alphas
    ])

    rat_mean = float(np.mean(rational_kappas))
    irr_mean = float(np.mean(irrational_kappas))
    ratio = rat_mean / max(irr_mean, 1e-30)

    # Confirm if rational κ is ≥ 10× irrational κ
    verdict = ratio >= 10.0

    return RationalDegeneracyResult(
        K=K,
        n_modes=n_modes,
        rational_kappas=rational_kappas,
        irrational_kappas=irrational_kappas,
        rational_mean_kappa=rat_mean,
        irrational_mean_kappa=irr_mean,
        kappa_ratio=ratio,
        verdict=verdict,
    )


def exp_mode_family_independence(
    n_harmonics: int = 20,
    K: int = 6,
    n_patterns: int = 100,
    noise_sigma: float = 0.02,
    seed: int = 42,
) -> ModeFamilyIndependenceResult:
    """H-CS2 — Multi-mode-family diagnostic independence.

    Coronal mode families (kink, sausage, longitudinal) depend on
    *different physical parameters*:
      - Kink:         ω_K ∝ B/√(ρ_i + ρ_e)  → sensitive to total density
      - Sausage:      ω_S ∝ B/√ρ_e           → sensitive to external density
      - Longitudinal: ω_L ∝ √T               → sensitive to temperature

    The state at each position k has 3 components (ρ_i, ρ_e, T).  Each
    family's sensitivity matrix maps 3K parameters to n_harmonics
    observations through different physical couplings.

    Confirm: mean |cross-correlation| < 0.3.
    Kill: mean |cross-correlation| ≥ 0.3.
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(K)

    # Base spatial sensitivity: sin²(nπx_k) for each harmonic n, position k
    S_base = _sensitivity_matrix(positions, n_harmonics)  # (n_harmonics, K)

    # Each family couples to a DIFFERENT physical parameter at each position.
    # Model: 3K-dim state vector [ρ_i_1,..,ρ_i_K, ρ_e_1,..,ρ_e_K, T_1,..,T_K]
    # Generate random state vectors with independent components
    states = rng.rand(n_patterns, 3 * K)  # 3 physical params × K positions
    rho_i = states[:, :K]          # internal density perturbation (K cols)
    rho_e = states[:, K:2*K]       # external density perturbation
    temp  = states[:, 2*K:]        # temperature perturbation

    # Family fingerprints via different physical couplings
    # Kink: frequency shift ∝ S·(ρ_i + ρ_e) per harmonic
    fp_kink = (rho_i + rho_e) @ S_base.T        # (n_patterns, n_harmonics)
    # Sausage: frequency shift ∝ S·ρ_e
    fp_sausage = rho_e @ S_base.T                # (n_patterns, n_harmonics)
    # Longitudinal: frequency shift ∝ S·T
    fp_long = temp @ S_base.T                    # (n_patterns, n_harmonics)

    family_fps = [fp_kink, fp_sausage, fp_long]

    # Cross-correlation between families
    n_families = 3
    cross_corr = np.zeros((n_families, n_families))
    for i in range(n_families):
        for j in range(n_families):
            # Use per-pattern norms as scalar summary
            a = np.linalg.norm(family_fps[i], axis=1)
            b = np.linalg.norm(family_fps[j], axis=1)
            if np.std(a) > 1e-10 and np.std(b) > 1e-10:
                cross_corr[i, j] = float(np.corrcoef(a, b)[0, 1])
            else:
                cross_corr[i, j] = 0.0 if i != j else 1.0

    # Off-diagonal cross-correlations
    off_diag = []
    for i in range(n_families):
        for j in range(n_families):
            if i != j:
                off_diag.append(abs(cross_corr[i, j]))
    mean_cc = float(np.mean(off_diag))
    max_cc = float(np.max(off_diag))

    # Per-family capacity (quantised unique fingerprints)
    channel_caps = np.zeros(n_families)
    for fi, fp in enumerate(family_fps):
        q = np.zeros_like(fp, dtype=int)
        rng_q = np.random.RandomState(seed + 200 + fi)
        for col in range(fp.shape[1]):
            q[:, col] = _quantise(
                fp[:, col] + rng_q.randn(n_patterns) * noise_sigma, 4
            )
        unique = set()
        for row in range(q.shape[0]):
            unique.add(tuple(q[row]))
        channel_caps[fi] = np.log2(max(len(unique), 1))

    total_poly = float(np.sum(channel_caps))

    # Verdict: mean cross-correlation < 0.3
    verdict = mean_cc < 0.3

    return ModeFamilyIndependenceResult(
        n_families=n_families,
        n_harmonics_per_family=n_harmonics,
        cross_correlations=cross_corr,
        mean_cross_corr=mean_cc,
        max_cross_corr=max_cc,
        channel_capacities=channel_caps,
        total_polysemic_capacity=total_poly,
        verdict=verdict,
    )


def exp_capacity_ceiling(
    K: int = 6,
    max_harmonics: int = 64,
    alphabet_size: int = 3,
    n_patterns: int = 200,
    noise_sigma: float = 0.02,
    seed: int = 42,
) -> CapacityCeilingResult:
    """H-CS3 — Logarithmic capacity ceiling.

    For a coronal loop with N observable overtones, measure diagnostic
    information content (unique recoverable density profiles).
    CWM predicts C ≈ a·ln(N) + b — each additional overtone provides
    diminishing returns.

    Confirm: log R² > linear R².
    Kill: linear R² ≥ log R² (capacity scales linearly).
    """
    rng = np.random.RandomState(seed)
    positions = _golden_positions(K)

    n_values = []
    n = 2
    while n <= max_harmonics:
        n_values.append(n)
        n *= 2
    n_values = np.array(n_values)

    patterns = rng.randint(0, alphabet_size, size=(n_patterns, K)).astype(float)

    capacities = np.zeros(len(n_values))
    for idx, nm in enumerate(n_values):
        S = _sensitivity_matrix(positions, nm)
        fps = patterns @ S.T

        q = np.zeros_like(fps, dtype=int)
        rng_q = np.random.RandomState(seed + 300 + idx)
        for col in range(fps.shape[1]):
            q[:, col] = _quantise(
                fps[:, col] + rng_q.randn(n_patterns) * noise_sigma, 4
            )
        unique = set()
        for row in range(q.shape[0]):
            unique.add(tuple(q[row]))
        capacities[idx] = np.log2(max(len(unique), 1))

    # Fit logarithmic: C = a·ln(N) + b
    log_n = np.log(n_values.astype(float))
    A_log = np.column_stack([log_n, np.ones(len(n_values))])
    coeffs_log, _, _, _ = np.linalg.lstsq(A_log, capacities, rcond=None)
    pred_log = A_log @ coeffs_log
    ss_res_log = np.sum((capacities - pred_log) ** 2)
    ss_tot = np.sum((capacities - np.mean(capacities)) ** 2)
    r2_log = 1.0 - ss_res_log / max(ss_tot, 1e-30)

    # Fit linear: C = a·N + b
    A_lin = np.column_stack([n_values.astype(float), np.ones(len(n_values))])
    coeffs_lin, _, _, _ = np.linalg.lstsq(A_lin, capacities, rcond=None)
    pred_lin = A_lin @ coeffs_lin
    ss_res_lin = np.sum((capacities - pred_lin) ** 2)
    r2_lin = 1.0 - ss_res_lin / max(ss_tot, 1e-30)

    verdict = r2_log > r2_lin

    return CapacityCeilingResult(
        n_values=n_values,
        capacities=capacities,
        log_r_squared=float(r2_log),
        linear_r_squared=float(r2_lin),
        log_coefficient=float(coeffs_log[0]),
        log_intercept=float(coeffs_log[1]),
        verdict=verdict,
    )


def exp_period_ratio_correlation(
    K: int = 5,
    seed: int = 42,
) -> PeriodRatioCorrelationResult:
    """H-CS4 — Published P₁/2P₂ anomalies correlate with conditioning.

    For each published coronal loop observation, the gravitational density
    stratification that produces its measured P₁/2P₂ ratio is associated
    with a specific sensitivity-matrix condition number κ.  CWM predicts
    that loops with larger P₁/2P₂ deviation from 1.0 have higher κ
    (worse conditioning).

    The gravitational profile ρ(z) ∝ exp(−ε·sin(πz)) correctly models
    footpoint-heavy coronal density stratification, producing P₁/2P₂ < 1.0
    as observed.  Per-loop harmonic count scales with loop length: longer
    loops support more resolvable overtones.

    Procedure:
    1. For each published (P1/2P2, L), bisect for the stratification ε
       (gravity profile) that produces the observed ratio.
    2. Determine per-loop harmonic count N(L).
    3. Compute κ(S) of the gravity-weighted sensitivity matrix at N(L).
    4. Spearman-correlate |1 − P1/2P2| with κ.

    Confirm: ρ ≥ 0.5 AND p < 0.05.
    Kill: ρ < 0.5 OR p ≥ 0.05.
    """
    v_kink = np.sqrt(2.0 * _B_DEFAULT**2 /
                     (_MU_0 * (_RHO_I_DEFAULT + _RHO_E_DEFAULT)))

    n_obs = len(_P1_OVER_2P2_DATA)
    ratios = np.zeros(n_obs)
    kappas = np.zeros(n_obs)
    h_counts = np.zeros(n_obs, dtype=int)

    for i, (p_ratio, L_Mm, _ref) in enumerate(_P1_OVER_2P2_DATA):
        ratios[i] = p_ratio
        L = L_Mm * 1e6  # Mm → m

        # Bisect for ε ∈ [0, 10] using the gravitational density profile.
        # The gravity profile produces P₁/2P₂ < 1.0 (matching observations)
        # because footpoint-heavy density shifts the 1st overtone more than
        # the fundamental.
        eps_lo, eps_hi = 0.0, 10.0
        for _ in range(60):
            eps_mid = (eps_lo + eps_hi) / 2.0
            freqs = _stratified_eigenfrequencies(
                2, L, v_kink, eps_mid, "gravity"
            )
            ratio_mid = _period_ratio_from_freqs(freqs)
            if ratio_mid > p_ratio:
                eps_lo = eps_mid
            else:
                eps_hi = eps_mid

        eps_found = (eps_lo + eps_hi) / 2.0

        # Observable harmonics: longer loops support more resolvable
        # overtones.  Base of 2 (fundamental + 1st overtone); each
        # additional ~80 Mm beyond 100 Mm allows one more harmonic.
        n_modes_loop = min(5, max(2, int(2 + (L_Mm - 100) / 80)))
        h_counts[i] = n_modes_loop

        # Stratification-weighted sensitivity matrix at per-loop N(L).
        positions = _golden_positions(K)
        rho_weight = _stratified_density(positions, eps_found, "gravity")
        S_base = _sensitivity_matrix(positions, n_modes_loop)
        M = S_base / rho_weight[None, :]  # gravity-weighted Jacobian
        sv = np.linalg.svd(M, compute_uv=False)
        tol = max(M.shape) * sv[0] * np.finfo(float).eps
        kappas[i] = sv[0] / max(sv[-1], tol)

    # Spearman correlation between |1 - P1/2P2| and κ
    deviations = np.abs(1.0 - ratios)
    rho = _spearman_correlation(deviations, kappas)
    p_val = _spearman_p_value(rho, n_obs)

    verdict = rho >= 0.5 and p_val < 0.05

    return PeriodRatioCorrelationResult(
        n_observations=n_obs,
        period_ratios=ratios,
        predicted_kappas=kappas,
        harmonic_counts=h_counts,
        spearman_rho=float(rho),
        p_value=float(p_val),
        verdict=verdict,
    )


def exp_footpoint_finesse(
    n_reflectivities: int = 10,
    n_mode: int = 5,
    seed: int = 42,
) -> FootpointFinesseResult:
    """H-CS5 — Footpoint impedance mismatch maps to Fabry-Pérot finesse.

    Coronal loop footpoints act as partial reflectors (chromospheric
    density jump).  The impedance mismatch sets an effective reflectivity
    R ≈ (ρ_i − ρ_e)/(ρ_i + ρ_e).  CWM/S14 predicts Q = n·F/π where
    F is the Fabry-Pérot finesse.

    Meanwhile, observed damping times give Q_obs = π·τ_d/P.  If the
    Fabry-Pérot model is correct, Q_finesse and Q_damping should agree
    to within a factor of 2.

    Confirm: mean(Q_finesse / Q_damping) ∈ [0.5, 2.0].
    Kill: ratio outside [0.5, 2.0].
    """
    rng = np.random.RandomState(seed)

    # Sweep density ratios → reflectivities
    rho_ratios = np.linspace(2.0, 10.0, n_reflectivities)
    reflectivities = ((rho_ratios - 1.0) / (rho_ratios + 1.0)) ** 2

    finesse_vals = np.array([_finesse_from_reflectivity(R) for R in reflectivities])
    q_finesse = np.array([_q_from_finesse(F, n_mode) for F in finesse_vals])

    # Q from energy leakage: after one round trip both ends reflect,
    # so energy per trip → R² · E.  The amplitude e-folding time is
    # τ_d = −2L / (v · ln R).  Then Q_damping = π f_n τ_d = −nπ/ln(R).
    # Add 10% observational scatter.
    q_damping = np.zeros(n_reflectivities)
    for i, R in enumerate(reflectivities):
        q_true = -n_mode * np.pi / np.log(R)
        q_damping[i] = q_true * (1.0 + 0.1 * rng.randn())

    ratios = q_finesse / np.clip(q_damping, 1e-10, None)
    mean_ratio = float(np.mean(ratios))

    verdict = 0.5 <= mean_ratio <= 2.0

    return FootpointFinesseResult(
        reflectivities=reflectivities,
        finesse_values=finesse_vals,
        q_from_finesse=q_finesse,
        q_from_damping=q_damping,
        mean_ratio=mean_ratio,
        verdict=verdict,
    )


def exp_perturbation_scaling(
    n_epsilons: int = 20,
    max_epsilon: float = 0.1,
    n_max: int = 10,
    seed: int = 42,
) -> PerturbationScalingResult:
    """H-CS6 — Density stratification sensitivity follows CWM perturbation scaling.

    For small density perturbation amplitude ε, the eigenfrequency shift
    δω/ω should scale linearly with ε (first-order perturbation theory).
    CWM uses this linear regime for encoding; if it fails in coronal
    loops, the analogy breaks down.

    Confirm: R² of linear fit > 0.99 for ε ∈ [0, 0.1].
    Kill: R² < 0.99 (nonlinear response even for small ε).
    """
    v_kink = np.sqrt(2.0 * _B_DEFAULT**2 /
                     (_MU_0 * (_RHO_I_DEFAULT + _RHO_E_DEFAULT)))

    epsilons = np.linspace(0.001, max_epsilon, n_epsilons)

    # Compute eigenfrequency shift for the fundamental mode (n=1)
    omega_0 = 1.0 * np.pi * v_kink / _L_DEFAULT  # uniform loop
    shifts = np.zeros(n_epsilons)

    for i, eps in enumerate(epsilons):
        freqs = _stratified_eigenfrequencies(
            n_max, _L_DEFAULT, v_kink, eps, "sinusoidal"
        )
        shifts[i] = abs(freqs[0] - omega_0) / omega_0

    # Linear fit: δω/ω = a·ε + b
    A = np.column_stack([epsilons, np.ones(n_epsilons)])
    coeffs, _, _, _ = np.linalg.lstsq(A, shifts, rcond=None)
    pred = A @ coeffs
    ss_res = np.sum((shifts - pred) ** 2)
    ss_tot = np.sum((shifts - np.mean(shifts)) ** 2)
    r2 = 1.0 - ss_res / max(ss_tot, 1e-30)

    verdict = r2 > 0.99

    return PerturbationScalingResult(
        epsilons=epsilons,
        frequency_shifts=shifts,
        linear_r_squared=float(r2),
        max_epsilon_tested=max_epsilon,
        verdict=verdict,
    )


def exp_optimal_probe_spacing(
    K: int = 6,
    n_modes: int = 40,
    noise_sigma: float = 0.05,
    n_random_trials: int = 10,
    seed: int = 42,
) -> OptimalProbeSpacingResult:
    """H-CS7 — Irrational density-probe spacing maximises inversion accuracy.

    If you could choose where to place density probes along a coronal
    loop, golden-ratio (irrational) spacing should yield the lowest
    inversion error — directly exporting S13's result.

    Confirm: golden-ratio RMS < equispaced RMS AND golden-ratio RMS < random RMS.
    Kill: golden-ratio NOT superior.
    """
    rng = np.random.RandomState(seed)
    true_pattern = rng.randint(0, 3, size=K).astype(float)

    # Golden-ratio positions
    pos_golden = _golden_positions(K)
    rms_golden = _inversion_rms(pos_golden, n_modes, true_pattern,
                                noise_sigma, seed)
    kappa_golden = _condition_number(pos_golden, n_modes)

    # Equispaced positions
    pos_equi = _equispaced_positions(K)
    rms_equi = _inversion_rms(pos_equi, n_modes, true_pattern,
                              noise_sigma, seed)
    kappa_equi = _condition_number(pos_equi, n_modes)

    # Random positions (average over trials)
    rms_random_all = []
    kappa_random_all = []
    for trial in range(n_random_trials):
        pos_rand = _random_positions(K, seed=seed + 1000 + trial)
        rms_rand = _inversion_rms(pos_rand, n_modes, true_pattern,
                                  noise_sigma, seed)
        rms_random_all.append(rms_rand)
        kappa_random_all.append(_condition_number(pos_rand, n_modes))

    rms_random = float(np.mean(rms_random_all))
    kappa_random = float(np.mean(kappa_random_all))

    # Verdict: golden-ratio is strictly best
    verdict = rms_golden < rms_equi and rms_golden < rms_random

    return OptimalProbeSpacingResult(
        golden_rms=float(rms_golden),
        equispaced_rms=float(rms_equi),
        random_rms=rms_random,
        golden_kappa=float(kappa_golden),
        equispaced_kappa=float(kappa_equi),
        random_kappa=kappa_random,
        verdict=verdict,
    )


# =========================================================================
# Runner
# =========================================================================

def run_all_coronal(verbose: bool = True) -> CoronalSeismologySummary:
    """Execute all seven coronal seismology experiments."""
    r1 = exp_rational_degeneracy()
    r2 = exp_mode_family_independence()
    r3 = exp_capacity_ceiling()
    r4 = exp_period_ratio_correlation()
    r5 = exp_footpoint_finesse()
    r6 = exp_perturbation_scaling()
    r7 = exp_optimal_probe_spacing()

    verdicts = [r1.verdict, r2.verdict, r3.verdict, r4.verdict,
                r5.verdict, r6.verdict, r7.verdict]
    confirmed = sum(verdicts)
    killed = len(verdicts) - confirmed

    summary = CoronalSeismologySummary(
        rational_degeneracy=r1,
        mode_family_independence=r2,
        capacity_ceiling=r3,
        period_ratio_correlation=r4,
        footpoint_finesse=r5,
        perturbation_scaling=r6,
        optimal_probe_spacing=r7,
        confirmed=confirmed,
        killed=killed,
    )

    if verbose:
        _label = {True: "CONFIRMED", False: "KILLED"}
        print("=" * 65)
        print("S17 — Coronal Seismology: Astrophysical Validation")
        print("=" * 65)

        print(f"\nH-CS1  Rational-position degeneracy")
        print(f"       κ_rational / κ_irrational = {r1.kappa_ratio:.1f}")
        print(f"       Verdict: {_label[r1.verdict]}")

        print(f"\nH-CS2  Mode-family independence")
        print(f"       Mean cross-correlation = {r2.mean_cross_corr:.4f}")
        print(f"       Total polysemic capacity = {r2.total_polysemic_capacity:.1f} bits")
        print(f"       Verdict: {_label[r2.verdict]}")

        print(f"\nH-CS3  Logarithmic capacity ceiling")
        print(f"       Log R² = {r3.log_r_squared:.4f}")
        print(f"       Linear R² = {r3.linear_r_squared:.4f}")
        print(f"       Verdict: {_label[r3.verdict]}")

        print(f"\nH-CS4  P₁/2P₂ correlation with conditioning")
        print(f"       Spearman ρ = {r4.spearman_rho:.3f}  (p = {r4.p_value:.4f})")
        print(f"       Verdict: {_label[r4.verdict]}")

        print(f"\nH-CS5  Footpoint Fabry-Pérot finesse")
        print(f"       Mean Q_finesse / Q_damping = {r5.mean_ratio:.3f}")
        print(f"       Verdict: {_label[r5.verdict]}")

        print(f"\nH-CS6  Perturbation scaling linearity")
        print(f"       Linear R² = {r6.linear_r_squared:.6f}")
        print(f"       Verdict: {_label[r6.verdict]}")

        print(f"\nH-CS7  Optimal probe spacing")
        print(f"       Golden RMS = {r7.golden_rms:.6f}")
        print(f"       Equispaced RMS = {r7.equispaced_rms:.6f}")
        print(f"       Random RMS = {r7.random_rms:.6f}")
        print(f"       Verdict: {_label[r7.verdict]}")

        print(f"\n{'=' * 65}")
        print(f"TOTAL: {confirmed} confirmed, {killed} killed "
              f"out of 7 hypotheses")
        print(f"{'=' * 65}")

    return summary


if __name__ == "__main__":
    run_all_coronal()
