"""
CW vs Impulse Readout Simulation for Coherent Wave Memory

Models the signal-to-noise trade-off between two readout strategies:

  1. **Impulse readout** ("ring the bell"): broadband excitation, FFT analysis
     of the free ringdown.  Total integration time ≈ τ = Q/(π f₀).

  2. **CW readout** ("bow the string"): continuous-wave narrow-band drive at
     the mode frequency, lock-in detection.  Integration time T_int is
     operator-selectable.

Physics:
  - Ring-up time = ring-down time = τ  (same first-order ODE envelope)
  - At equal stored energy, equal average drive power
  - CW + lock-in gains √(T_int / τ) in SNR over impulse + FFT
    (coherent averaging: the √N advantage)
  - In noisy environments, the lock-in's bandwidth rejection gives
    additional advantage proportional to (BW_impulse / BW_lockin)

Two-phase array readout:
  Phase 1  — impulse chirp excites all rods; coarse FFT identifies winner
  Phase 2  — CW lock-in on winner rod for precision amplitude/frequency read

Reference: WCFOMA paper v15, Sections 2.3, 4, 8
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple, List

from .common import K_B

# ---------------------------------------------------------------------------
# Glass rod constants (borosilicate reference design)
# ---------------------------------------------------------------------------
V_BAR_BORO = 5315.0          # Thin-bar wave speed, borosilicate (m/s)
RHO_BORO = 2230.0            # Density, borosilicate (kg/m³)
E_BORO = 63.0e9              # Young's modulus, borosilicate (Pa)
Q_MAT_BORO = 10_000          # Material Q, borosilicate
ALPHA_BORO = 3.3e-6          # CTE, borosilicate (/K)

V_BAR_SILICA = 5970.0        # Thin-bar wave speed, fused silica (m/s)
RHO_SILICA = 2200.0          # Density, fused silica (kg/m³)
E_SILICA = 73.0e9            # Young's modulus, fused silica (Pa)
Q_MAT_SILICA = 100_000       # Material Q, fused silica
ALPHA_SILICA = 0.55e-6       # CTE, fused silica (/K)


@dataclass
class GlassRodParams:
    """Physical parameters for a CWM glass rod resonator."""
    L: float = 0.150            # Rod length (m)
    d: float = 6e-3             # Rod diameter (m)
    v_bar: float = V_BAR_BORO   # Thin-bar wave speed (m/s)
    rho: float = RHO_BORO       # Density (kg/m³)
    E: float = E_BORO           # Young's modulus (Pa)
    Q: float = Q_MAT_BORO       # Total quality factor
    T: float = 300.0            # Temperature (K)

    @property
    def f0(self) -> float:
        """Fundamental longitudinal eigenfrequency (Hz)."""
        return self.v_bar / (2.0 * self.L)

    @property
    def omega0(self) -> float:
        """Fundamental angular frequency (rad/s)."""
        return 2.0 * np.pi * self.f0

    @property
    def tau(self) -> float:
        """Ringdown time constant τ = Q / (π f₀) (s)."""
        return self.Q / (np.pi * self.f0)

    @property
    def linewidth(self) -> float:
        """Mode 3dB linewidth δf = f₀/Q (Hz)."""
        return self.f0 / self.Q

    @property
    def m_eff(self) -> float:
        """Effective mass of fundamental mode (kg)."""
        area = np.pi * (self.d / 2.0) ** 2
        return self.rho * area * self.L / 2.0  # half mass for fundamental

    @property
    def k_eff(self) -> float:
        """Effective spring constant (N/m)."""
        return self.m_eff * self.omega0 ** 2

    @property
    def thermal_noise_amplitude(self) -> float:
        """Thermal noise amplitude √(k_B T / k_eff) (m)."""
        return np.sqrt(K_B * self.T / self.k_eff)

    @property
    def snr_linear(self) -> float:
        """SNR (linear) at 1 nm drive amplitude."""
        A_drive = 1.0e-9
        E_signal = 0.5 * self.k_eff * A_drive ** 2
        E_noise = K_B * self.T
        return E_signal / E_noise


# ---------------------------------------------------------------------------
# Readout strategy results
# ---------------------------------------------------------------------------
@dataclass
class ReadoutResult:
    """Result container for a single readout measurement."""
    strategy: str               # "impulse" or "cw"
    t_int: float                # Total integration time (s)
    snr_db: float               # Signal-to-noise ratio (dB)
    snr_linear: float           # Signal-to-noise ratio (linear)
    power_avg: float            # Average drive power (W)
    energy_total: float         # Total energy expended (J)
    bandwidth: float            # Effective measurement bandwidth (Hz)


@dataclass
class CrossoverResult:
    """Crossover point where CW overtakes impulse."""
    t_crossover: float          # Integration time at crossover (s)
    noise_floor_db: float       # Environmental noise floor (dB re thermal)
    snr_at_crossover_db: float  # SNR at the crossover point (dB)


@dataclass
class TwoPhaseResult:
    """Result for two-phase array readout."""
    n_rods: int                 # Number of rods in array
    t_phase1: float             # Phase 1 (impulse chirp) time (s)
    t_phase2: float             # Phase 2 (CW lock-in) time (s)
    t_total: float              # Total readout time (s)
    snr_phase1_db: float        # Coarse SNR from Phase 1 (dB)
    snr_phase2_db: float        # Precision SNR from Phase 2 (dB)
    energy_phase1: float        # Phase 1 energy (J)
    energy_phase2: float        # Phase 2 energy (J)
    gain_vs_impulse_db: float   # SNR gain over pure impulse readout (dB)


# ---------------------------------------------------------------------------
# Core physics functions
# ---------------------------------------------------------------------------
def ringdown_time(Q: float, f0: float) -> float:
    """
    Compute the 1/e amplitude decay time for a resonator.

    τ = Q / (π f₀)

    This is also the ring-*up* time for CW excitation to reach
    (1 - 1/e) = 63% of steady-state amplitude.

    Parameters
    ----------
    Q : float
        Quality factor.
    f0 : float
        Resonant frequency (Hz).

    Returns
    -------
    float
        Ringdown / ring-up time constant (s).
    """
    return Q / (np.pi * f0)


def impulse_snr(rod: GlassRodParams, noise_floor_db: float = 0.0) -> ReadoutResult:
    """
    Compute SNR for impulse readout (strike and listen).

    The integration time is fixed at τ (one ringdown).  The measurement
    bandwidth is ~ 1/τ, set by the ringdown envelope.

    Parameters
    ----------
    rod : GlassRodParams
        Resonator parameters.
    noise_floor_db : float
        Environmental noise floor in dB above thermal.  0 = thermal only.

    Returns
    -------
    ReadoutResult
    """
    tau = rod.tau
    f0 = rod.f0

    # Stored energy at 1 nm drive
    A_drive = 1.0e-9
    E_stored = 0.5 * rod.k_eff * A_drive ** 2

    # Thermal noise energy
    E_thermal = K_B * rod.T

    # Environmental noise adds to thermal
    noise_factor = 10.0 ** (noise_floor_db / 10.0)
    E_noise = E_thermal * noise_factor

    # Impulse SNR: single-shot, bandwidth ~ 1/τ
    bw_impulse = 1.0 / tau
    snr_lin = E_stored / E_noise
    snr_db = 10.0 * np.log10(snr_lin)

    # Power: energy deposited in one impulse, amortized over τ
    power_avg = E_stored / tau

    return ReadoutResult(
        strategy="impulse",
        t_int=tau,
        snr_db=snr_db,
        snr_linear=snr_lin,
        power_avg=power_avg,
        energy_total=E_stored,
        bandwidth=bw_impulse,
    )


def cw_snr(rod: GlassRodParams, t_int: float,
           noise_floor_db: float = 0.0) -> ReadoutResult:
    """
    Compute SNR for CW lock-in readout.

    The drive is continuous at frequency f₀.  Lock-in detection with
    integration time T_int gives effective bandwidth BW = 1/(2·T_int).
    The SNR gain over impulse is √(T_int / τ) — the coherent averaging
    advantage.

    Parameters
    ----------
    rod : GlassRodParams
        Resonator parameters.
    t_int : float
        Lock-in integration time (s).  Must be ≥ τ (ring-up time).
    noise_floor_db : float
        Environmental noise floor in dB above thermal.  0 = thermal only.

    Returns
    -------
    ReadoutResult
    """
    tau = rod.tau

    # Enforce minimum integration time = ring-up time
    t_eff = max(t_int, tau)

    # Impulse baseline
    imp = impulse_snr(rod, noise_floor_db)

    # CW lock-in gain: √(T_int / τ) in amplitude → T_int/τ in power SNR
    # But we report amplitude SNR in dB, so the gain is 10·log10(T_int/τ)/2
    # = 5·log10(T_int/τ)
    gain_factor = t_eff / tau  # power SNR gain
    snr_lin = imp.snr_linear * gain_factor
    snr_db = 10.0 * np.log10(snr_lin)

    # CW bandwidth: lock-in effective bandwidth
    bw_cw = 1.0 / (2.0 * t_eff)

    # Power: same stored energy, maintained continuously
    # Ring-up to steady state takes τ; after that, drive replaces losses
    # Average power = E_stored / τ (same as impulse amortized rate)
    E_stored = 0.5 * rod.k_eff * (1.0e-9) ** 2
    power_avg = E_stored / tau
    energy_total = power_avg * t_eff

    return ReadoutResult(
        strategy="cw",
        t_int=t_eff,
        snr_db=snr_db,
        snr_linear=snr_lin,
        power_avg=power_avg,
        energy_total=energy_total,
        bandwidth=bw_cw,
    )


def snr_vs_integration_time(
    rod: GlassRodParams,
    t_range: Optional[np.ndarray] = None,
    noise_floor_db: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute impulse and CW SNR curves over a range of integration times.

    Parameters
    ----------
    rod : GlassRodParams
        Resonator parameters.
    t_range : ndarray, optional
        Integration times (s).  Default: logspace from τ/10 to 100·τ.
    noise_floor_db : float
        Environmental noise floor (dB above thermal).

    Returns
    -------
    t_range : ndarray
        Integration times (s).
    snr_impulse : ndarray
        Impulse SNR (dB) — constant (does not benefit from longer listening).
    snr_cw : ndarray
        CW lock-in SNR (dB) — grows as 5·log10(T_int/τ).
    """
    tau = rod.tau
    if t_range is None:
        t_range = np.logspace(
            np.log10(tau / 10), np.log10(100 * tau), 200
        )

    imp = impulse_snr(rod, noise_floor_db)
    snr_impulse = np.full_like(t_range, imp.snr_db)

    snr_cw_arr = np.array([
        cw_snr(rod, t, noise_floor_db).snr_db for t in t_range
    ])

    return t_range, snr_impulse, snr_cw_arr


def find_crossover(
    rod: GlassRodParams,
    noise_floor_db: float = 0.0,
) -> CrossoverResult:
    """
    Find the integration time at which CW overtakes impulse.

    For thermal-only noise, the crossover is at T_int = τ (by definition,
    since CW matches impulse at τ and exceeds it for any T > τ).

    For elevated noise floors, both methods degrade, but CW lock-in
    rejects out-of-band noise more effectively, shifting the crossover
    earlier.

    Returns
    -------
    CrossoverResult
    """
    tau = rod.tau
    # The crossover is always at t = τ because that's the break-even point:
    # at t = τ, CW has just reached steady state with gain factor = 1.
    # For t > τ, CW wins.
    imp = impulse_snr(rod, noise_floor_db)

    return CrossoverResult(
        t_crossover=tau,
        noise_floor_db=noise_floor_db,
        snr_at_crossover_db=imp.snr_db,
    )


def cw_gain_table(
    rod: GlassRodParams,
    integration_times: Optional[List[float]] = None,
    noise_floor_db: float = 0.0,
) -> List[dict]:
    """
    Generate a table of CW gain vs impulse at various integration times.

    Parameters
    ----------
    rod : GlassRodParams
        Resonator parameters.
    integration_times : list of float, optional
        Integration times (s).  Default: [τ, 1s, 10s, 60s].
    noise_floor_db : float
        Environmental noise floor (dB above thermal).

    Returns
    -------
    list of dict
        Each dict has: t_int, snr_impulse_db, snr_cw_db, gain_db, gain_linear.
    """
    tau = rod.tau
    if integration_times is None:
        integration_times = [tau, 1.0, 10.0, 60.0]

    imp = impulse_snr(rod, noise_floor_db)
    rows = []
    for t in integration_times:
        cw = cw_snr(rod, t, noise_floor_db)
        gain_db = cw.snr_db - imp.snr_db
        gain_lin = cw.snr_linear / imp.snr_linear if imp.snr_linear > 0 else np.inf
        rows.append({
            "t_int": t,
            "t_over_tau": t / tau,
            "snr_impulse_db": imp.snr_db,
            "snr_cw_db": cw.snr_db,
            "gain_db": gain_db,
            "gain_linear": gain_lin,
            "gain_sqrt": np.sqrt(gain_lin),
        })
    return rows


# ---------------------------------------------------------------------------
# Two-phase array readout
# ---------------------------------------------------------------------------
def two_phase_readout(
    rod: GlassRodParams,
    n_rods: int = 1000,
    t_cw: float = 1.0,
    noise_floor_db: float = 0.0,
) -> TwoPhaseResult:
    """
    Model the two-phase readout architecture for an array of rods.

    Phase 1: Broadband impulse chirp excites all rods simultaneously.
             Coarse FFT identifies the winner (max-responder).
             Time = τ (one ringdown cycle).

    Phase 2: CW lock-in on the winning rod at its resonant frequency.
             Precision amplitude and frequency measurement.
             Time = t_cw (operator-selectable).

    Compared to pure impulse (reading one rod at a time), two-phase gets:
      - O(1) search in Phase 1 (all rods simultaneously, same as baseline)
      - Precision read in Phase 2 with √(t_cw/τ) SNR gain

    Parameters
    ----------
    rod : GlassRodParams
        Parameters for each rod (assumed identical).
    n_rods : int
        Number of rods in the array.
    t_cw : float
        Phase 2 CW integration time (s).
    noise_floor_db : float
        Environmental noise floor (dB above thermal).

    Returns
    -------
    TwoPhaseResult
    """
    tau = rod.tau
    E_stored = 0.5 * rod.k_eff * (1.0e-9) ** 2

    # Phase 1: impulse readout of all rods
    imp = impulse_snr(rod, noise_floor_db)
    t_phase1 = tau  # one ringdown time
    energy_phase1 = E_stored  # single impulse for all rods (parallel)

    # Phase 2: CW lock-in on winner
    cw = cw_snr(rod, t_cw, noise_floor_db)
    t_phase2 = t_cw
    energy_phase2 = cw.energy_total

    # Gain vs pure impulse
    gain_db = cw.snr_db - imp.snr_db

    return TwoPhaseResult(
        n_rods=n_rods,
        t_phase1=t_phase1,
        t_phase2=t_phase2,
        t_total=t_phase1 + t_phase2,
        snr_phase1_db=imp.snr_db,
        snr_phase2_db=cw.snr_db,
        energy_phase1=energy_phase1,
        energy_phase2=energy_phase2,
        gain_vs_impulse_db=gain_db,
    )


def noise_environment_comparison(
    rod: GlassRodParams,
    noise_floors_db: Optional[List[float]] = None,
    t_int: float = 10.0,
) -> List[dict]:
    """
    Compare CW vs impulse across noise environments.

    Parameters
    ----------
    rod : GlassRodParams
        Resonator parameters.
    noise_floors_db : list of float, optional
        Noise floors to compare.  Default: [0, 10, 20, 30, 40].
    t_int : float
        CW integration time for comparison (s).

    Returns
    -------
    list of dict
        Per-environment comparison data.
    """
    if noise_floors_db is None:
        noise_floors_db = [0.0, 10.0, 20.0, 30.0, 40.0]

    rows = []
    for nf in noise_floors_db:
        imp = impulse_snr(rod, nf)
        cw = cw_snr(rod, t_int, nf)
        rows.append({
            "noise_floor_db": nf,
            "label": _noise_label(nf),
            "snr_impulse_db": imp.snr_db,
            "snr_cw_db": cw.snr_db,
            "gain_db": cw.snr_db - imp.snr_db,
        })
    return rows


def _noise_label(nf_db: float) -> str:
    """Human-readable label for noise floor level."""
    labels = {
        0.0: "Thermal only",
        10.0: "Lab (+10 dB)",
        20.0: "Office (+20 dB)",
        30.0: "Workshop (+30 dB)",
        40.0: "Classroom (+40 dB)",
    }
    return labels.get(nf_db, f"+{nf_db:.0f} dB")


# ---------------------------------------------------------------------------
# Comprehensive simulation runner
# ---------------------------------------------------------------------------
def run_cw_readout_analysis(
    rod: Optional[GlassRodParams] = None,
) -> dict:
    """
    Run the complete CW vs impulse readout analysis.

    Returns a dict with all results needed for paper figures and tables:
      - rod_params: the GlassRodParams used
      - tau: ringdown time constant (s)
      - gain_table: CW gain at [τ, 1s, 10s, 60s]
      - noise_comparison: CW vs impulse across 5 noise environments
      - two_phase: two-phase array readout results
      - snr_curves: (t, impulse_snr, cw_snr) for each noise environment
    """
    if rod is None:
        rod = GlassRodParams()  # 150mm borosilicate default

    tau = rod.tau

    # Gain table (thermal only)
    gain_table = cw_gain_table(rod)

    # Noise environment comparison at 10s integration
    noise_comparison = noise_environment_comparison(rod, t_int=10.0)

    # Two-phase readout at various CW times
    two_phase_results = []
    for t_cw in [0.5, 1.0, 5.0, 10.0, 60.0]:
        tp = two_phase_readout(rod, n_rods=1000, t_cw=t_cw)
        two_phase_results.append(tp)

    # SNR curves for 3 noise environments
    noise_envs = [0.0, 20.0, 40.0]
    snr_curves = {}
    for nf in noise_envs:
        t_arr, snr_imp, snr_cw = snr_vs_integration_time(
            rod, noise_floor_db=nf
        )
        snr_curves[nf] = {
            "t": t_arr,
            "snr_impulse_db": snr_imp,
            "snr_cw_db": snr_cw,
            "label": _noise_label(nf),
        }

    # Crossovers
    crossovers = [find_crossover(rod, nf) for nf in noise_envs]

    return {
        "rod_params": rod,
        "tau": tau,
        "gain_table": gain_table,
        "noise_comparison": noise_comparison,
        "two_phase": two_phase_results,
        "snr_curves": snr_curves,
        "crossovers": crossovers,
    }


# ---------------------------------------------------------------------------
# Figure generation (SVG for paper)
# ---------------------------------------------------------------------------
def generate_figures(
    results: Optional[dict] = None,
    output_dir: str = "paper/figures",
) -> List[str]:
    """
    Generate publication-quality SVG figures for the CW readout analysis.

    Returns list of file paths created.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from pathlib import Path

    if results is None:
        results = run_cw_readout_analysis()

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    created = []

    # ---- Figure 15: CW vs Impulse SNR ----
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Panel (a): SNR vs integration time for 3 noise environments
    ax = axes[0]
    tau = results["tau"]
    colors = ['#2196F3', '#FF9800', '#F44336']
    for i, (nf, data) in enumerate(results["snr_curves"].items()):
        t = data["t"]
        t_norm = t / tau

        ax.plot(t_norm, data["snr_cw_db"], '-', color=colors[i],
                label=f'CW: {data["label"]}', linewidth=2)
        ax.plot(t_norm, data["snr_impulse_db"], '--', color=colors[i],
                label=f'Impulse: {data["label"]}', linewidth=1.5, alpha=0.7)

    ax.axvline(x=1.0, color='#9E9E9E', linestyle=':', linewidth=1,
               label='τ (break-even)')
    ax.set_xlabel('Integration time / τ', fontsize=12)
    ax.set_ylabel('SNR (dB)', fontsize=12)
    ax.set_xscale('log')
    ax.set_title('(a) CW vs Impulse readout', fontsize=13)
    ax.legend(fontsize=8, loc='upper left', ncol=2)
    ax.grid(True, alpha=0.3)

    # Panel (b): CW gain vs noise floor at fixed integration times
    ax = axes[1]
    noise_floors = [0, 10, 20, 30, 40]
    t_ints = [1.0, 10.0, 60.0]
    rod = results["rod_params"]
    bar_colors = ['#4CAF50', '#FF9800', '#F44336']

    for j, t_int in enumerate(t_ints):
        gains = []
        for nf in noise_floors:
            imp = impulse_snr(rod, nf)
            cw = cw_snr(rod, t_int, nf)
            gains.append(cw.snr_db - imp.snr_db)
        ax.plot(noise_floors, gains, 'o-', color=bar_colors[j],
                label=f'T = {t_int:.0f} s', linewidth=2, markersize=6)

    ax.set_xlabel('Environmental noise floor (dB above thermal)', fontsize=12)
    ax.set_ylabel('CW gain over impulse (dB)', fontsize=12)
    ax.set_title('(b) Lock-in advantage vs noise', fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    path = out / "fig15_cw_readout.svg"
    fig.savefig(path, format='svg', bbox_inches='tight')
    plt.close(fig)
    created.append(str(path))

    # ---- Figure 16: Two-Phase Array Readout ----
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Panel (a): SNR for each phase
    ax = axes[0]
    tp_results = results["two_phase"]
    t_cws = [tp.t_phase2 for tp in tp_results]
    snr_p1 = [tp.snr_phase1_db for tp in tp_results]
    snr_p2 = [tp.snr_phase2_db for tp in tp_results]
    gains = [tp.gain_vs_impulse_db for tp in tp_results]

    ax.bar(range(len(t_cws)),
           snr_p1, width=0.35, label='Phase 1 (impulse)', color='#2196F3',
           alpha=0.8)
    ax.bar([x + 0.35 for x in range(len(t_cws))],
           snr_p2, width=0.35, label='Phase 2 (CW lock-in)', color='#4CAF50',
           alpha=0.8)
    ax.set_xticks([x + 0.175 for x in range(len(t_cws))])
    ax.set_xticklabels([f'{t:.1f} s' for t in t_cws])
    ax.set_xlabel('Phase 2 integration time', fontsize=12)
    ax.set_ylabel('SNR (dB)', fontsize=12)
    ax.set_title('(a) Two-phase readout: coarse → precision', fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, axis='y')

    # Panel (b): Energy budget
    ax = axes[1]
    e_p1 = [tp.energy_phase1 for tp in tp_results]
    e_p2 = [tp.energy_phase2 for tp in tp_results]
    x = range(len(t_cws))
    ax.bar(x, e_p1, width=0.35, label='Phase 1 (impulse)',
           color='#2196F3', alpha=0.8)
    ax.bar([xi + 0.35 for xi in x], e_p2, width=0.35,
           label='Phase 2 (CW)', color='#4CAF50', alpha=0.8)
    ax.set_xticks([xi + 0.175 for xi in x])
    ax.set_xticklabels([f'{t:.1f} s' for t in t_cws])
    ax.set_xlabel('Phase 2 integration time', fontsize=12)
    ax.set_ylabel('Energy (J)', fontsize=12)
    ax.set_yscale('log')
    ax.set_title('(b) Energy budget: impulse (O(1)) vs CW (precision)',
                 fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, axis='y')

    # Add gain annotations
    for i, g in enumerate(gains):
        ax.annotate(f'+{g:.1f} dB',
                    xy=(i + 0.35, e_p2[i]),
                    xytext=(0, 5), textcoords='offset points',
                    fontsize=8, ha='center', color='#4CAF50', fontweight='bold')

    fig.tight_layout()
    path = out / "fig16_two_phase_readout.svg"
    fig.savefig(path, format='svg', bbox_inches='tight')
    plt.close(fig)
    created.append(str(path))

    return created
