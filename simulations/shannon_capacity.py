"""Shannon–Nyquist channel capacity and optimal mode allocation (Sidebar 15).

Hypotheses
----------
H-SN1  Waterfilling capacity gain ≥ 5 % over uniform allocation.
H-SN2  Faithful reconstruction of K sites requires ≥ 2K modes at finite SNR.
H-SN3  Uniform allocation achieves ≥ 85 % of Shannon (waterfilling) limit.
H-SN4  Mutual information per mode > 0.5 bits for n ≤ n_max/2 and < 0.1 bits
       for n > n_max.

Each experiment returns a typed dataclass; ``run_all_shannon`` collects and
summarises results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .common import C_FERROFLUID, K_B
from .noise_decoherence import NoiseParams, snr_at_mode

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

_L_DEFAULT: float = 1e-5       # cavity length [m] (10 µm)
_N_MODES_DEFAULT: int = 20     # default number of modes to analyse
_Q_DEFAULT: float = 500.0      # default quality factor
_T_DEFAULT: float = 300.0      # ambient temperature [K]
_BW_DEFAULT: float = 1e6       # readout bandwidth [Hz]
_TOTAL_POWER: float = 1.0      # normalised total readout power (arb. units)

# ---------------------------------------------------------------------------
# SNR profile helpers
# ---------------------------------------------------------------------------


def _snr_profile_db(n_modes: int, params: NoiseParams,
                    L: float = _L_DEFAULT) -> np.ndarray:
    """Return per-mode SNR in dB for modes 1 … n_modes."""
    return np.array([snr_at_mode(m, params, L) for m in range(1, n_modes + 1)])


def _snr_profile_linear(n_modes: int, params: NoiseParams,
                         L: float = _L_DEFAULT) -> np.ndarray:
    """Return per-mode SNR in linear scale, clipped to ≥ 0."""
    db = _snr_profile_db(n_modes, params, L)
    return np.maximum(10.0 ** (db / 10.0), 0.0)


def _mode_dependent_snr(n_modes: int, snr_base: float,
                        alpha: float = 1.0) -> np.ndarray:
    """Analytic mode-dependent SNR: SNR_n = snr_base / n^alpha.

    This captures the physical reality that higher modes have broader
    linewidths (δf_n ∝ n) and larger thermal drift (Δf_n ∝ n), leading
    to SNR that decreases with mode number.
    """
    modes = np.arange(1, n_modes + 1, dtype=float)
    return snr_base / modes ** alpha

# ---------------------------------------------------------------------------
# Waterfilling
# ---------------------------------------------------------------------------


def _waterfilling(noise_levels: np.ndarray,
                  total_power: float) -> np.ndarray:
    """Classic waterfilling power allocation.

    Parameters
    ----------
    noise_levels : array
        Per-channel noise power N_n (must be > 0).
    total_power : float
        Total power budget P_total = Σ P_n.

    Returns
    -------
    powers : array
        Optimal per-channel power P_n = max(μ - N_n, 0).
    """
    N = np.asarray(noise_levels, dtype=float)
    n_ch = len(N)
    # Sort channels by noise level (ascending)
    idx = np.argsort(N)
    N_sorted = N[idx]

    # Progressively drop the noisiest channels until all active
    # channels receive positive power.
    powers = np.zeros(n_ch)
    active = n_ch
    while active > 0:
        mu = (total_power + np.sum(N_sorted[:active])) / active
        if mu > N_sorted[active - 1]:
            # All active channels get positive power
            powers[idx[:active]] = mu - N_sorted[:active]
            break
        active -= 1
    return powers


def _capacity_with_powers(snr_linear: np.ndarray,
                          powers: np.ndarray) -> float:
    """Total capacity C = Σ 0.5 log₂(1 + P_n · SNR_n) in bits/measurement."""
    effective = np.maximum(powers * snr_linear, 0.0)
    return float(np.sum(0.5 * np.log2(1.0 + effective)))


def _capacity_uniform(snr_linear: np.ndarray,
                      total_power: float) -> float:
    """Capacity with uniform power allocation."""
    n = len(snr_linear)
    p_each = total_power / n
    return _capacity_with_powers(snr_linear, np.full(n, p_each))

# ---------------------------------------------------------------------------
# Mutual information
# ---------------------------------------------------------------------------


def _mutual_info_per_mode(snr_linear: np.ndarray) -> np.ndarray:
    """I(X_n; Y_n) = 0.5 log₂(1 + SNR_n) bits/mode."""
    return 0.5 * np.log2(1.0 + np.maximum(snr_linear, 0.0))

# ---------------------------------------------------------------------------
# Nyquist reconstruction
# ---------------------------------------------------------------------------


def _reconstruction_error(K: int, N_meas: int,
                          snr_linear: np.ndarray) -> float:
    """Mean-square reconstruction error for K sites from N_meas modes.

    Uses the first N_meas modes of the given SNR profile.  The
    reconstruction assumes a sin²-basis expansion; the error is:

        ε = Σ_{n > N_meas}^{n_max} s_n²  +  Σ_{n=1}^{N_meas} s_n² / (1 + SNR_n)

    where s_n is the signal coefficient for mode n.  For a K-site
    perturbation with equal amplitudes: s_n = 1/K for n ≤ 2K, 0 otherwise.
    """
    n_max = len(snr_linear)
    s = np.zeros(n_max)
    for n in range(min(2 * K, n_max)):
        s[n] = 1.0 / K

    # Noise-limited error on measured modes
    N = min(N_meas, n_max)
    err_measured = np.sum(s[:N] ** 2 / (1.0 + snr_linear[:N]))
    # Aliasing error from unmeasured modes
    err_alias = np.sum(s[N:] ** 2)
    return float(err_measured + err_alias)

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WaterfillingResult:
    """H-SN1: Waterfilling capacity gain."""
    capacity_uniform: float       # bits/meas, uniform allocation
    capacity_waterfill: float     # bits/meas, waterfilling
    gain_percent: float           # (wf - uniform) / uniform × 100
    n_cutoff: int                 # modes receiving zero power
    n_modes: int
    snr_base: float
    alpha: float
    verdict: bool                 # True → CONFIRMED (gain ≥ 5 %)


@dataclass
class NyquistMinimumResult:
    """H-SN2: Nyquist 2K mode minimum."""
    K: int
    error_K: float                # reconstruction error with K modes
    error_2K: float               # reconstruction error with 2K modes
    error_ratio: float            # error_K / error_2K
    snr_db_mean: float            # mean SNR of measured modes
    K_suffices: bool              # True if K modes give error < threshold
    verdict: bool                 # True → CONFIRMED (K modes insufficient)


@dataclass
class CapacityUtilisationResult:
    """H-SN3: Capacity utilisation ratio."""
    capacity_uniform: float
    capacity_waterfill: float
    utilisation: float            # uniform / waterfill
    n_modes: int
    verdict: bool                 # True → CONFIRMED (utilisation ≥ 85 %)


@dataclass
class MutualInfoResult:
    """H-SN4: Mutual information per mode."""
    mi_per_mode: np.ndarray       # I(X_n; Y_n) for each mode
    n_max: int                    # usable mode count (SNR > 0 dB)
    mi_low_half_mean: float       # mean MI for n ≤ n_max/2
    mi_above_nmax_mean: float     # mean MI for n > n_max
    low_half_above_05: bool       # True if mean MI > 0.5 bits
    above_nmax_below_01: bool     # True if mean MI < 0.1 bits
    verdict: bool                 # True → CONFIRMED (both conditions)


@dataclass
class ShannonCapacitySummary:
    """Aggregate results from all four experiments."""
    waterfilling: WaterfillingResult
    nyquist: NyquistMinimumResult
    utilisation: CapacityUtilisationResult
    mutual_info: MutualInfoResult
    confirmed: int
    killed: int

# ---------------------------------------------------------------------------
# Experiment functions
# ---------------------------------------------------------------------------


def exp_waterfilling_gain(
    n_modes: int = 30,
    snr_base: float = 1000.0,
    alpha: float = 1.0,
    total_power: float = _TOTAL_POWER,
) -> WaterfillingResult:
    """H-SN1 — Compare waterfilling vs uniform allocation.

    Uses an analytic mode-dependent SNR profile (SNR_n = snr_base / n^α)
    that captures linewidth broadening and thermal drift at high mode
    numbers.  The waterfilling algorithm allocates readout power optimally.
    """
    snr_lin = _mode_dependent_snr(n_modes, snr_base, alpha)

    # Noise levels: N_n = 1 / SNR_n (normalised)
    noise = 1.0 / np.maximum(snr_lin, 1e-30)

    # Waterfilling allocation
    powers_wf = _waterfilling(noise, total_power)
    cap_wf = _capacity_with_powers(snr_lin, powers_wf)

    # Uniform allocation
    cap_uni = _capacity_uniform(snr_lin, total_power)

    gain = (cap_wf - cap_uni) / max(cap_uni, 1e-30) * 100.0

    # Number of modes cut off (zero power)
    n_cutoff = int(np.sum(powers_wf < 1e-15))

    return WaterfillingResult(
        capacity_uniform=cap_uni,
        capacity_waterfill=cap_wf,
        gain_percent=gain,
        n_cutoff=n_cutoff,
        n_modes=n_modes,
        snr_base=snr_base,
        alpha=alpha,
        verdict=bool(gain >= 5.0),
    )


def exp_nyquist_minimum(
    K: int = 5,
    n_modes: int = 40,
    snr_base: float = 100.0,
    alpha: float = 1.0,
    error_threshold: float = 0.05,
) -> NyquistMinimumResult:
    """H-SN2 — Test whether K modes suffice or 2K are required.

    Computes reconstruction error for a K-site perturbation pattern
    using K and 2K modes at realistic (finite) SNR.  At high SNR
    (> 40 dB) K modes may suffice (Leibniz H-L3); at moderate SNR
    the Nyquist 2K minimum should be necessary.
    """
    snr_lin = _mode_dependent_snr(n_modes, snr_base, alpha)
    snr_db = 10.0 * np.log10(np.maximum(snr_lin, 1e-30))

    err_K = _reconstruction_error(K, K, snr_lin)
    err_2K = _reconstruction_error(K, 2 * K, snr_lin)

    ratio = err_K / max(err_2K, 1e-30)
    mean_snr = float(np.mean(snr_db[:min(2 * K, n_modes)]))

    # K suffices if error < threshold even with only K modes
    k_suffices = err_K < error_threshold

    # CONFIRMED if K modes do NOT suffice (i.e. 2K is needed)
    return NyquistMinimumResult(
        K=K,
        error_K=err_K,
        error_2K=err_2K,
        error_ratio=ratio,
        snr_db_mean=mean_snr,
        K_suffices=k_suffices,
        verdict=bool(not k_suffices),
    )


def exp_capacity_utilisation(
    n_modes: int = 30,
    snr_base: float = 1000.0,
    alpha: float = 1.0,
    total_power: float = _TOTAL_POWER,
) -> CapacityUtilisationResult:
    """H-SN3 — Ratio of uniform capacity to waterfilling capacity.

    A high utilisation (≥ 85 %) means the paper's simple uniform model
    is a close approximation to the information-theoretic optimum.
    """
    snr_lin = _mode_dependent_snr(n_modes, snr_base, alpha)
    noise = 1.0 / np.maximum(snr_lin, 1e-30)

    powers_wf = _waterfilling(noise, total_power)
    cap_wf = _capacity_with_powers(snr_lin, powers_wf)
    cap_uni = _capacity_uniform(snr_lin, total_power)

    util = cap_uni / max(cap_wf, 1e-30)

    return CapacityUtilisationResult(
        capacity_uniform=cap_uni,
        capacity_waterfill=cap_wf,
        utilisation=util,
        n_modes=n_modes,
        verdict=bool(util >= 0.85),
    )


def exp_mutual_info(
    n_modes: int = 40,
    params: NoiseParams | None = None,
    L: float = _L_DEFAULT,
) -> MutualInfoResult:
    """H-SN4 — Mutual information per mode vs n_max boundary.

    Uses the full physics-based SNR model from noise_decoherence.py.
    n_max is the largest mode with SNR > 0 dB.
    """
    if params is None:
        params = NoiseParams()

    snr_lin = _snr_profile_linear(n_modes, params, L)
    mi = _mutual_info_per_mode(snr_lin)

    # n_max: last mode with SNR > 0 dB (linear > 1)
    usable = np.where(snr_lin > 1.0)[0]
    n_max = int(usable[-1] + 1) if len(usable) > 0 else 0

    # Low half: modes 1 … floor(n_max/2)
    half = max(n_max // 2, 1)
    mi_low_mean = float(np.mean(mi[:half])) if half > 0 else 0.0

    # Above n_max: modes n_max+1 …
    if n_max < n_modes:
        mi_high_mean = float(np.mean(mi[n_max:]))
    else:
        # All modes usable — no modes above n_max
        mi_high_mean = 0.0

    low_ok = mi_low_mean > 0.5
    high_ok = mi_high_mean < 0.1

    return MutualInfoResult(
        mi_per_mode=mi,
        n_max=n_max,
        mi_low_half_mean=mi_low_mean,
        mi_above_nmax_mean=mi_high_mean,
        low_half_above_05=low_ok,
        above_nmax_below_01=high_ok,
        verdict=bool(low_ok and high_ok),
    )

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_all_shannon(verbose: bool = True) -> ShannonCapacitySummary:
    """Execute all four Shannon–Nyquist experiments and summarise."""

    if verbose:
        print("=" * 72)
        print("  S15 — Shannon & Nyquist: Channel Capacity")
        print("=" * 72)

    # H-SN1 — Waterfilling gain
    r1 = exp_waterfilling_gain()
    if verbose:
        tag = "CONFIRMED" if r1.verdict else "KILLED"
        print(f"\n[H-SN1] Waterfilling gain: {r1.gain_percent:.2f} %")
        print(f"  Uniform capacity:  {r1.capacity_uniform:.4f} bits/meas")
        print(f"  Waterfill capacity: {r1.capacity_waterfill:.4f} bits/meas")
        print(f"  Modes cut off: {r1.n_cutoff}/{r1.n_modes}")
        print(f"  → {tag}")

    # H-SN2 — Nyquist minimum
    r2 = exp_nyquist_minimum()
    if verbose:
        tag = "CONFIRMED" if r2.verdict else "KILLED"
        print(f"\n[H-SN2] Nyquist 2K minimum (K={r2.K}):")
        print(f"  Error (K modes):   {r2.error_K:.6f}")
        print(f"  Error (2K modes):  {r2.error_2K:.6f}")
        print(f"  Error ratio K/2K:  {r2.error_ratio:.2f}")
        print(f"  Mean SNR (dB):     {r2.snr_db_mean:.1f}")
        print(f"  K suffices: {r2.K_suffices}")
        print(f"  → {tag}")

    # H-SN3 — Capacity utilisation
    r3 = exp_capacity_utilisation()
    if verbose:
        tag = "CONFIRMED" if r3.verdict else "KILLED"
        print(f"\n[H-SN3] Capacity utilisation: {r3.utilisation:.4f}")
        print(f"  Uniform:    {r3.capacity_uniform:.4f}")
        print(f"  Waterfill:  {r3.capacity_waterfill:.4f}")
        print(f"  → {tag}")

    # H-SN4 — Mutual information
    r4 = exp_mutual_info()
    if verbose:
        tag = "CONFIRMED" if r4.verdict else "KILLED"
        print(f"\n[H-SN4] Mutual information per mode:")
        print(f"  n_max: {r4.n_max}")
        print(f"  Mean MI (n ≤ n_max/2): {r4.mi_low_half_mean:.4f} bits")
        print(f"  Mean MI (n > n_max):   {r4.mi_above_nmax_mean:.4f} bits")
        print(f"  → {tag}")

    # Summary
    verdicts = [r1.verdict, r2.verdict, r3.verdict, r4.verdict]
    confirmed = sum(verdicts)
    killed = len(verdicts) - confirmed

    if verbose:
        print("\n" + "-" * 72)
        print(f"  Summary: {confirmed} confirmed, {killed} killed")
        labels = ["H-SN1", "H-SN2", "H-SN3", "H-SN4"]
        for lbl, v in zip(labels, verdicts):
            print(f"    {lbl}: {'CONFIRMED' if v else 'KILLED'}")
        print("-" * 72)

    return ShannonCapacitySummary(
        waterfilling=r1,
        nyquist=r2,
        utilisation=r3,
        mutual_info=r4,
        confirmed=confirmed,
        killed=killed,
    )


if __name__ == "__main__":
    run_all_shannon()
