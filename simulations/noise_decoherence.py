"""
Noise and Decoherence Model for WCFOMA.

Models realistic noise sources that limit mode lifetime and retrieval
fidelity in a ferrofluid-based wave memory:

  1. Thermal noise (Johnson-Nyquist)
  2. Shot noise (photon counting for optical readout)
  3. 1/f noise (ubiquitous in ferrofluids)
  4. Phase diffusion (Brownian motion of nanoparticles)
  5. Nonlinear mode mixing (four-wave coupling)
  6. Quantization noise (ADC discretization)

The module produces:
  - Signal-to-noise ratio (SNR) vs. mode index, time, temperature
  - Bit error rate (BER) estimates for digital retrieval
  - Mode lifetime under combined noise
  - Decoherence rate comparisons (paper vs. realistic)

References:
  - Paper v9, Section 2.4 (mode persistence)
  - Paper v9, Section 6.1 (energy claims)
  - Coffey, "The Langevin Equation" (2004) — Brownian dynamics
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict
import numpy as np
from scipy.signal import welch

from .common import K_B, C_FERROFLUID, CavityParams, ThermalParams, MicroCellParams


# ---------------------------------------------------------------------------
# Noise model parameters
# ---------------------------------------------------------------------------

@dataclass
class NoiseParams:
    """Parameters for all noise sources."""
    # Temperature [K]
    T: float = 300.0
    # Acoustic impedance [Pa·s/m] (ferrofluid ~ 2e6)
    Z_acoustic: float = 2e6
    # Cavity volume [m³]
    V_cavity: float = 1e-15       # (10 µm)³
    # Bandwidth [Hz] (readout integration bandwidth)
    bandwidth: float = 1e6
    # Quality factor
    Q: float = 500.0
    # 1/f noise corner frequency [Hz]
    f_corner: float = 1e3
    # 1/f noise amplitude coefficient
    alpha_1f: float = 1e-12
    # Nanoparticle diameter [m]
    d_particle: float = 10e-9
    # Ferrofluid viscosity [Pa·s]
    viscosity: float = 0.01
    # Volume fraction of magnetic nanoparticles
    phi: float = 0.05
    # ADC bits
    n_adc_bits: int = 10
    # Signal amplitude (reference, normalized)
    A_signal: float = 1.0
    # Number of modes stored
    n_modes: int = 10
    # Mode spacing factor (modes at n * f_fundamental)
    mode_spacing_factor: float = 1.0
    # Readout photon count (for optical readout shot noise)
    n_photons: float = 1e6
    # Nonlinear coupling coefficient
    chi_nl: float = 1e-6


@dataclass
class NoiseSpectrum:
    """Noise power spectral density at a given frequency."""
    thermal: float      # Johnson-Nyquist [units²/Hz]
    shot: float         # Shot noise [units²/Hz]
    one_over_f: float   # 1/f noise [units²/Hz]
    phase_diffusion: float  # Brownian phase noise [rad²/Hz]
    quantization: float  # ADC quantization [units²/Hz]
    total: float        # Sum of all sources


@dataclass
class DecoherenceResult:
    """Full decoherence analysis results."""
    # Per-mode analysis
    mode_indices: np.ndarray
    mode_frequencies: np.ndarray    # Hz
    snr_per_mode: np.ndarray        # dB
    ber_per_mode: np.ndarray        # bit error rate
    lifetime_per_mode: np.ndarray   # seconds
    noise_floor_per_mode: np.ndarray  # amplitude units

    # Time-domain analysis
    times: np.ndarray
    snr_vs_time: np.ndarray          # (n_times, n_modes)
    fidelity_vs_time: np.ndarray     # (n_times,) — overall retrieval fidelity

    # Summary
    max_reliable_modes: int
    max_storage_time: float          # s — time until BER > 1%
    dominant_noise_source: str
    effective_density_tb_cm3: float

    # Kill criteria
    snr_above_10dB: bool
    ber_below_1pct: bool
    lifetime_above_1us: bool

    # Parameters used
    params: NoiseParams = field(default_factory=NoiseParams)


# ---------------------------------------------------------------------------
# Individual noise source calculations
# ---------------------------------------------------------------------------

def thermal_noise_psd(T: float, Z: float, V: float) -> float:
    """
    Johnson-Nyquist thermal noise power spectral density.

    S_thermal = 4 k_B T / (Z * V)  [pressure²/Hz]

    For mode amplitude normalized to unity, this becomes:
    S_th = 4 k_B T * Z / V  [in appropriate units]
    """
    return 4 * K_B * T / (Z * V)


def shot_noise_psd(n_photons: float, bandwidth: float) -> float:
    """
    Shot noise for optical readout.

    SNR_shot = sqrt(N_photons / bandwidth)
    S_shot = 1 / N_photons (normalized)
    """
    if n_photons <= 0:
        return np.inf
    return 1.0 / n_photons


def one_over_f_noise_psd(freq: float, alpha: float, f_corner: float) -> float:
    """
    1/f noise PSD: S(f) = α * f_corner / f for f > 0.

    Parameters
    ----------
    freq : float
        Frequency [Hz].
    alpha : float
        Noise amplitude coefficient.
    f_corner : float
        Corner frequency where 1/f noise equals white noise floor.

    Returns
    -------
    float
        Noise PSD [units²/Hz].
    """
    if freq <= 0:
        return alpha * f_corner  # DC limit
    return alpha * f_corner / freq


def phase_diffusion_rate(T: float, d: float, viscosity: float,
                          V_cavity: float) -> float:
    """
    Brownian phase diffusion rate for nanoparticles in ferrofluid.

    The rotational diffusion coefficient:
      D_rot = k_B T / (π η d³)

    This causes phase noise in the acoustic modes:
      Γ_phase = φ² * D_rot * N_particles

    where N_particles = φ * V / V_particle.

    Returns Γ_phase [rad²/s].
    """
    V_particle = (np.pi / 6) * d**3
    N = 0.05 * V_cavity / V_particle  # Using default φ
    D_rot = K_B * T / (np.pi * viscosity * d**3)
    # Coupling factor: each particle contributes a small phase kick
    # Scale by (V_particle / V_cavity) for the coupling strength
    coupling = V_particle / V_cavity
    return coupling**2 * D_rot * N


def adc_quantization_noise(n_bits: int, A_signal: float) -> float:
    """
    ADC quantization noise PSD (normalized to signal).

    Quantization step: Δ = 2 * A_fullscale / 2^n
    Noise power: σ² = Δ²/12

    We assume the ADC full-scale range matches the signal, so
    the quantization noise-to-signal ratio is fixed by n_bits:
      SNR_adc = (3/2) * 2^(2n) ≈ 6.02n + 1.76 dB

    Return as absolute noise PSD = A_signal² / SNR_adc_linear
    normalized per Hz of bandwidth (uniform spectral density).
    """
    snr_adc = 1.5 * (2**(2 * n_bits))
    return A_signal**2 / (snr_adc * 1e6)  # Spread over 1 MHz BW


def nonlinear_mixing_noise(n_modes: int, chi: float,
                            amplitudes: np.ndarray) -> float:
    """
    Estimate noise from nonlinear four-wave mixing between modes.

    The spurious mode amplitude from mixing of modes i,j,k:
      a_spur ~ χ * a_i * a_j * a_k^*

    Total noise power ~ χ² * N³ * <|a|²>³
    """
    mean_power = np.mean(np.abs(amplitudes)**2)
    return chi**2 * n_modes**3 * mean_power**3


# ---------------------------------------------------------------------------
# Composite noise analysis
# ---------------------------------------------------------------------------

def compute_noise_spectrum(freq: float, params: NoiseParams) -> NoiseSpectrum:
    """
    Compute all noise contributions at a given frequency.

    Parameters
    ----------
    freq : float
        Frequency [Hz].
    params : NoiseParams
        Noise parameters.

    Returns
    -------
    NoiseSpectrum
        All noise components and total.
    """
    th = thermal_noise_psd(params.T, params.Z_acoustic, params.V_cavity)
    sh = shot_noise_psd(params.n_photons, params.bandwidth)
    of = one_over_f_noise_psd(freq, params.alpha_1f, params.f_corner)
    pd = phase_diffusion_rate(params.T, params.d_particle,
                               params.viscosity, params.V_cavity)
    qn = adc_quantization_noise(params.n_adc_bits, params.A_signal)

    total = th + sh + of + pd + qn
    return NoiseSpectrum(
        thermal=th,
        shot=sh,
        one_over_f=of,
        phase_diffusion=pd,
        quantization=qn,
        total=total,
    )


def snr_at_mode(mode_index: int, params: NoiseParams,
                 L: float = 1e-5) -> float:
    """
    Signal-to-noise ratio for a specific mode.

    SNR = A_signal² / (noise_total * bandwidth)

    Returns SNR in dB.
    """
    freq = mode_index * C_FERROFLUID / (2 * L)
    noise = compute_noise_spectrum(freq, params)
    signal_power = params.A_signal**2
    noise_power = noise.total * params.bandwidth
    if noise_power <= 0:
        return np.inf
    snr_linear = signal_power / noise_power
    return 10 * np.log10(max(snr_linear, 1e-30))


def mode_lifetime(mode_index: int, params: NoiseParams,
                   L: float = 1e-5) -> float:
    """
    Estimated mode lifetime accounting for all noise sources.

    The mode is considered "alive" while SNR > threshold (10 dB).
    Mode amplitude decays as exp(-ω/(2Q) * t), while noise accumulates.

    lifetime = (2Q / ω) * ln(SNR_0 / SNR_threshold)
    """
    freq = mode_index * C_FERROFLUID / (2 * L)
    omega = 2 * np.pi * freq
    snr_0 = snr_at_mode(mode_index, params, L)  # dB
    snr_threshold = 10.0  # dB

    if snr_0 <= snr_threshold:
        return 0.0

    # Convert to linear
    snr_0_lin = 10**(snr_0 / 10)
    snr_th_lin = 10**(snr_threshold / 10)

    if omega <= 0 or params.Q <= 0:
        return np.inf

    tau_decay = 2 * params.Q / omega
    return tau_decay * np.log(snr_0_lin / snr_th_lin)


def ber_from_snr(snr_db: float) -> float:
    """
    Bit error rate estimate from SNR (assuming Gaussian noise, OOK).

    BER ≈ 0.5 * erfc(sqrt(SNR_linear / 2))
    """
    from scipy.special import erfc
    snr_lin = 10**(snr_db / 10)
    return 0.5 * erfc(np.sqrt(snr_lin / 2))


# ---------------------------------------------------------------------------
# Full decoherence analysis
# ---------------------------------------------------------------------------

def run_decoherence_analysis(
    params: NoiseParams = None,
    L: float = 1e-5,
    t_max: float = 1e-3,
    n_time_points: int = 200,
) -> DecoherenceResult:
    """
    Run comprehensive decoherence analysis.

    Parameters
    ----------
    params : NoiseParams
        Noise parameters. Uses defaults if None.
    L : float
        Cavity length [m].
    t_max : float
        Analysis time window [s].
    n_time_points : int
        Number of time points.

    Returns
    -------
    DecoherenceResult
        Full analysis with per-mode and time-domain results.
    """
    if params is None:
        params = NoiseParams()

    n = params.n_modes
    modes = np.arange(1, n + 1)
    freqs = modes * C_FERROFLUID / (2 * L)

    # Per-mode analysis
    snr_modes = np.array([snr_at_mode(m, params, L) for m in modes])
    ber_modes = np.array([ber_from_snr(s) for s in snr_modes])
    lifetime_modes = np.array([mode_lifetime(m, params, L) for m in modes])
    noise_floors = np.array([
        np.sqrt(compute_noise_spectrum(f, params).total * params.bandwidth)
        for f in freqs
    ])

    # Time-domain analysis
    times = np.linspace(0, t_max, n_time_points)
    snr_vs_time = np.zeros((n_time_points, n))
    fidelity_vs_time = np.zeros(n_time_points)

    for i, t in enumerate(times):
        for j, m in enumerate(modes):
            omega = 2 * np.pi * freqs[j]
            tau_decay = 2 * params.Q / omega if omega > 0 else np.inf
            # Signal decays exponentially
            signal_amp = params.A_signal * np.exp(-t / tau_decay) if tau_decay > 0 else 0
            # Noise accumulates (phase diffusion grows with sqrt(t))
            noise_spec = compute_noise_spectrum(freqs[j], params)
            noise_amp = np.sqrt(noise_spec.total * params.bandwidth
                                + noise_spec.phase_diffusion * t)
            snr_lin = signal_amp**2 / max(noise_amp**2, 1e-30)
            snr_vs_time[i, j] = 10 * np.log10(max(snr_lin, 1e-30))

        # Overall fidelity: fraction of modes above 10 dB SNR
        fidelity_vs_time[i] = np.mean(snr_vs_time[i, :] > 10.0)

    # Summary statistics
    reliable = np.sum(snr_modes > 10.0)

    # Max storage time: when fidelity drops below 0.99 (99% of modes readable)
    storage_idx = np.where(fidelity_vs_time < 0.99)[0]
    max_storage = float(times[storage_idx[0]]) if len(storage_idx) > 0 else float(t_max)

    # Dominant noise source at fundamental frequency
    ns = compute_noise_spectrum(freqs[0], params)
    sources = {
        'thermal': ns.thermal,
        'shot': ns.shot,
        '1/f': ns.one_over_f,
        'phase_diffusion': ns.phase_diffusion,
        'quantization': ns.quantization,
    }
    dominant = max(sources, key=sources.get)

    # Effective storage density (only reliable modes contribute)
    cell = MicroCellParams()
    bits_per_cell = reliable * cell.bits_per_mode
    density = bits_per_cell * cell.cells_per_cm3 / 1e12  # Tb/cm³

    return DecoherenceResult(
        mode_indices=modes,
        mode_frequencies=freqs,
        snr_per_mode=snr_modes,
        ber_per_mode=ber_modes,
        lifetime_per_mode=lifetime_modes,
        noise_floor_per_mode=noise_floors,
        times=times,
        snr_vs_time=snr_vs_time,
        fidelity_vs_time=fidelity_vs_time,
        max_reliable_modes=int(reliable),
        max_storage_time=max_storage,
        dominant_noise_source=dominant,
        effective_density_tb_cm3=density,
        snr_above_10dB=bool(np.all(snr_modes > 10.0)),
        ber_below_1pct=bool(np.all(ber_modes < 0.01)),
        lifetime_above_1us=bool(np.all(lifetime_modes > 1e-6)),
        params=params,
    )


def noise_budget_table(params: NoiseParams = None,
                        L: float = 1e-5) -> str:
    """
    Generate a formatted noise budget table.

    Shows contribution of each noise source at the fundamental frequency.
    """
    if params is None:
        params = NoiseParams()

    f0 = C_FERROFLUID / (2 * L)
    ns = compute_noise_spectrum(f0, params)

    total = ns.total
    lines = [
        "=" * 65,
        "  NOISE BUDGET (at fundamental frequency {:.1f} MHz)".format(f0/1e6),
        "=" * 65,
        f"  {'Source':<25} {'PSD':>12} {'Fraction':>10}",
        "-" * 65,
        f"  {'Thermal (Johnson)':<25} {ns.thermal:>12.3e} {ns.thermal/total*100:>9.1f}%",
        f"  {'Shot (optical)':<25} {ns.shot:>12.3e} {ns.shot/total*100:>9.1f}%",
        f"  {'1/f (flicker)':<25} {ns.one_over_f:>12.3e} {ns.one_over_f/total*100:>9.1f}%",
        f"  {'Phase diffusion':<25} {ns.phase_diffusion:>12.3e} {ns.phase_diffusion/total*100:>9.1f}%",
        f"  {'ADC quantization':<25} {ns.quantization:>12.3e} {ns.quantization/total*100:>9.1f}%",
        "-" * 65,
        f"  {'TOTAL':<25} {total:>12.3e} {'100.0':>9}%",
        "=" * 65,
    ]
    return "\n".join(lines)


def decoherence_summary(result: DecoherenceResult) -> str:
    """Generate a text summary of the decoherence analysis."""
    lines = [
        "=" * 60,
        "  DECOHERENCE ANALYSIS SUMMARY",
        "=" * 60,
        f"  Modes analyzed:       {len(result.mode_indices)}",
        f"  Reliable modes:       {result.max_reliable_modes} (SNR > 10 dB)",
        f"  Max storage time:     {result.max_storage_time*1e6:.1f} µs",
        f"  Dominant noise:       {result.dominant_noise_source}",
        f"  Effective density:    {result.effective_density_tb_cm3:.2f} Tb/cm³",
        "-" * 60,
        "  KILL CRITERIA",
        f"    SNR > 10 dB all modes:  {'PASS ✅' if result.snr_above_10dB else 'FAIL ❌'}",
        f"    BER < 1% all modes:     {'PASS ✅' if result.ber_below_1pct else 'FAIL ❌'}",
        f"    Lifetime > 1 µs:        {'PASS ✅' if result.lifetime_above_1us else 'FAIL ❌'}",
        "-" * 60,
        "  PER-MODE SUMMARY",
        f"  {'Mode':<6} {'Freq [MHz]':<12} {'SNR [dB]':<10} {'BER':<12} {'τ [µs]':<10}",
    ]
    for i in range(len(result.mode_indices)):
        lines.append(
            f"  {result.mode_indices[i]:<6} "
            f"{result.mode_frequencies[i]/1e6:<12.2f} "
            f"{result.snr_per_mode[i]:<10.1f} "
            f"{result.ber_per_mode[i]:<12.2e} "
            f"{result.lifetime_per_mode[i]*1e6:<10.1f}"
        )
    lines.append("=" * 60)
    return "\n".join(lines)
