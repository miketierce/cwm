"""
Information-Theoretic Capacity Analysis for WCFOMA.

The paper asserts "10 bits/mode" without formal derivation.  This module
applies Shannon's channel-capacity theorem to compute the actual
achievable capacity under realistic noise conditions discovered in
Phases 1–2.

Key formulas
────────────
  C_mode  = B × log₂(1 + SNR)      bits/s per mode  (Shannon)
  b_mode  = ½ × log₂(1 + SNR)      bits per measurement per mode
  C_cell  = Σ C_mode_n              total cell capacity
  ρ       = C_cell × cells/cm³     density [b/cm³]

We also compute:
  - Read/write latency (excitation + ring-down + readout)
  - Bandwidth per cell and per cm³
  - Capacity under mitigated noise (gel + high-photon) vs baseline

References:
  - Shannon, "A Mathematical Theory of Communication" (1948)
  - Paper v9, Section 2.4 (mode persistence)
  - simulations/noise_decoherence.py (noise budget)
  - simulations/mitigations.py (mitigated parameter sets)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import numpy as np

from .common import K_B, C_FERROFLUID, CavityParams, MicroCellParams
from .noise_decoherence import (
    NoiseParams, compute_noise_spectrum, snr_at_mode,
    run_decoherence_analysis, mode_lifetime,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ChannelCapacity:
    """Information-theoretic capacity results for a single configuration."""
    # Per-mode
    mode_indices: np.ndarray
    mode_frequencies: np.ndarray        # Hz
    snr_per_mode: np.ndarray            # linear (NOT dB)
    bits_per_measurement: np.ndarray    # ½ log₂(1 + SNR)
    capacity_per_mode: np.ndarray       # bits/s = BW × log₂(1+SNR)

    # Cell totals
    total_bits_per_measurement: float   # Σ bits across all modes
    total_capacity_bps: float           # Σ capacity [bits/s]
    usable_modes: int                   # modes with SNR > 0 dB

    # Storage density
    cells_per_cm3: float
    density_bits_per_cm3: float
    density_tb_per_cm3: float

    # Timing
    write_latency_us: float             # excitation time [µs]
    read_latency_us: float              # readout integration time [µs]
    cycle_time_us: float                # write + read
    bandwidth_mbps: float               # total_capacity × duty_cycle

    # Parameters
    cavity_length_m: float
    noise_params: NoiseParams


@dataclass
class ScalingResult:
    """How capacity scales with one parameter."""
    parameter_name: str
    parameter_values: np.ndarray
    bits_per_cell: np.ndarray
    density_tb_cm3: np.ndarray
    energy_fj: np.ndarray
    bandwidth_mbps: np.ndarray
    usable_modes: np.ndarray


@dataclass
class TechComparison:
    """Head-to-head comparison entry for a memory technology."""
    name: str
    energy_pJ: float            # energy per operation [pJ]
    density_tb_cm3: float       # storage density [Tb/cm³]
    read_latency_ns: float      # read latency [ns]
    write_latency_ns: float     # write latency [ns]
    endurance_cycles: float     # write endurance
    retention_s: float          # data retention time [s]
    compute_locality: str       # "none", "partial", "unified"
    maturity: str               # "production", "prototype", "simulation"
    notes: str = ""


# ---------------------------------------------------------------------------
# Shannon capacity computation
# ---------------------------------------------------------------------------

def bits_per_measurement(snr_linear: float) -> float:
    """
    Shannon bits per measurement at a given SNR.

    For a single sample of a signal in AWGN:
      b = ½ × log₂(1 + SNR)

    This is the practical limit; real ADCs achieve less.
    """
    if snr_linear <= 0:
        return 0.0
    return 0.5 * np.log2(1 + snr_linear)


def channel_capacity_bps(snr_linear: float, bandwidth: float) -> float:
    """
    Shannon channel capacity: C = B × log₂(1 + SNR)  [bits/s].
    """
    if snr_linear <= 0:
        return 0.0
    return bandwidth * np.log2(1 + snr_linear)


def compute_channel_capacity(
    params: NoiseParams = None,
    L: float = 1e-5,
    n_modes: int = 10,
    bits_per_mode_paper: float = 10.0,
) -> ChannelCapacity:
    """
    Compute full channel capacity for a WCFOMA cell.

    Parameters
    ----------
    params : NoiseParams
        Noise parameters (determines SNR).
    L : float
        Cavity side length [m].
    n_modes : int
        Number of modes to analyze.
    bits_per_mode_paper : float
        Paper's claimed bits/mode (for comparison).

    Returns
    -------
    ChannelCapacity
        Full capacity analysis.
    """
    if params is None:
        params = NoiseParams()

    modes = np.arange(1, n_modes + 1)
    freqs = modes * C_FERROFLUID / (2 * L)
    bw = params.bandwidth

    # SNR per mode (linear)
    snr_db = np.array([snr_at_mode(m, params, L) for m in modes])
    snr_lin = 10 ** (snr_db / 10)
    snr_lin = np.maximum(snr_lin, 0)  # clip negatives

    # Capacity per mode
    bpm = np.array([bits_per_measurement(s) for s in snr_lin])
    cap = np.array([channel_capacity_bps(s, bw) for s in snr_lin])

    # Usable modes: SNR > 0 dB (linear > 1)
    usable = int(np.sum(snr_lin > 1))

    # Cell totals
    total_bpm = float(np.sum(bpm))
    total_cap = float(np.sum(cap))

    # Storage density
    cells = 1e-6 / (L ** 3)  # cells per cm³
    density_bits = total_bpm * cells
    density_tb = density_bits / 1e12

    # Timing estimates
    # Write: excitation pulse duration ~ 1/(Δf) = 2L/c
    write_time = 2 * L / C_FERROFLUID  # ~14 ns for 10 µm
    # Read: integration time = 1/bandwidth
    read_time = 1.0 / bw
    # Ring-down for mode separation: ~Q/(π × f_fundamental)
    f0 = C_FERROFLUID / (2 * L)
    ringdown = params.Q / (np.pi * f0) if f0 > 0 else 0
    cycle = write_time + ringdown + read_time

    # Bandwidth
    duty = 1.0  # continuous operation assumed
    bw_mbps = total_cap * duty / 1e6

    return ChannelCapacity(
        mode_indices=modes,
        mode_frequencies=freqs,
        snr_per_mode=snr_lin,
        bits_per_measurement=bpm,
        capacity_per_mode=cap,
        total_bits_per_measurement=total_bpm,
        total_capacity_bps=total_cap,
        usable_modes=usable,
        cells_per_cm3=cells,
        density_bits_per_cm3=density_bits,
        density_tb_per_cm3=density_tb,
        write_latency_us=write_time * 1e6,
        read_latency_us=read_time * 1e6,
        cycle_time_us=cycle * 1e6,
        bandwidth_mbps=bw_mbps,
        cavity_length_m=L,
        noise_params=params,
    )


# ---------------------------------------------------------------------------
# Scaling law sweeps
# ---------------------------------------------------------------------------

def sweep_cell_size(
    L_values_um: np.ndarray = None,
    params: NoiseParams = None,
    n_modes: int = 10,
) -> ScalingResult:
    """Sweep cell size and compute capacity at each point."""
    if L_values_um is None:
        L_values_um = np.logspace(0.5, 3, 30)  # 3 µm to 1 mm
    if params is None:
        params = NoiseParams()

    n = len(L_values_um)
    bits = np.zeros(n)
    density = np.zeros(n)
    energy = np.zeros(n)
    bw = np.zeros(n)
    modes_arr = np.zeros(n, dtype=int)

    for i, L_um in enumerate(L_values_um):
        L_m = L_um * 1e-6
        V = L_m ** 3
        p = NoiseParams(
            V_cavity=V,
            viscosity=params.viscosity,
            n_photons=params.n_photons,
            A_signal=params.A_signal,
            Q=params.Q,
            T=params.T,
            bandwidth=params.bandwidth,
        )
        cc = compute_channel_capacity(p, L_m, n_modes)
        bits[i] = cc.total_bits_per_measurement
        density[i] = cc.density_tb_per_cm3
        # Energy scales with cavity volume
        energy[i] = 2.6 * (L_um / 10) ** 3 + 100 * (params.n_photons / 1e6)
        bw[i] = cc.bandwidth_mbps
        modes_arr[i] = cc.usable_modes

    return ScalingResult(
        parameter_name="cavity_length_um",
        parameter_values=L_values_um,
        bits_per_cell=bits,
        density_tb_cm3=density,
        energy_fj=energy,
        bandwidth_mbps=bw,
        usable_modes=modes_arr,
    )


def sweep_Q_factor(
    Q_values: np.ndarray = None,
    params: NoiseParams = None,
    L: float = 1e-5,
    n_modes_max: int = 50,
) -> ScalingResult:
    """Sweep quality factor — affects mode count and SNR."""
    if Q_values is None:
        Q_values = np.logspace(1, 4, 30)
    if params is None:
        params = NoiseParams()

    n = len(Q_values)
    bits = np.zeros(n)
    density = np.zeros(n)
    energy = np.zeros(n)
    bw = np.zeros(n)
    modes_arr = np.zeros(n, dtype=int)

    for i, Q in enumerate(Q_values):
        p = NoiseParams(
            Q=Q,
            V_cavity=params.V_cavity,
            viscosity=params.viscosity,
            n_photons=params.n_photons,
            A_signal=params.A_signal,
            T=params.T,
            bandwidth=params.bandwidth,
        )
        # Mode count limited by Q (modes up to Q)
        nm = min(n_modes_max, max(1, int(Q)))
        cc = compute_channel_capacity(p, L, nm)
        bits[i] = cc.total_bits_per_measurement
        density[i] = cc.density_tb_per_cm3
        energy[i] = 2.6 + 100 * (params.n_photons / 1e6)
        bw[i] = cc.bandwidth_mbps
        modes_arr[i] = cc.usable_modes

    return ScalingResult(
        parameter_name="Q_factor",
        parameter_values=Q_values,
        bits_per_cell=bits,
        density_tb_cm3=density,
        energy_fj=energy,
        bandwidth_mbps=bw,
        usable_modes=modes_arr,
    )


def sweep_temperature(
    T_values: np.ndarray = None,
    params: NoiseParams = None,
    L: float = 1e-5,
    n_modes: int = 10,
) -> ScalingResult:
    """Sweep temperature — affects thermal noise and phase diffusion."""
    if T_values is None:
        T_values = np.linspace(200, 400, 30)  # 200–400 K
    if params is None:
        params = NoiseParams()

    n = len(T_values)
    bits = np.zeros(n)
    density = np.zeros(n)
    energy = np.zeros(n)
    bw = np.zeros(n)
    modes_arr = np.zeros(n, dtype=int)

    for i, T in enumerate(T_values):
        p = NoiseParams(
            T=T,
            V_cavity=params.V_cavity,
            viscosity=params.viscosity,
            n_photons=params.n_photons,
            A_signal=params.A_signal,
            Q=params.Q,
            bandwidth=params.bandwidth,
        )
        cc = compute_channel_capacity(p, L, n_modes)
        bits[i] = cc.total_bits_per_measurement
        density[i] = cc.density_tb_per_cm3
        energy[i] = 2.6 + 100 * (params.n_photons / 1e6)
        bw[i] = cc.bandwidth_mbps
        modes_arr[i] = cc.usable_modes

    return ScalingResult(
        parameter_name="temperature_K",
        parameter_values=T_values,
        bits_per_cell=bits,
        density_tb_cm3=density,
        energy_fj=energy,
        bandwidth_mbps=bw,
        usable_modes=modes_arr,
    )


# ---------------------------------------------------------------------------
# Technology comparison database
# ---------------------------------------------------------------------------

def technology_database() -> Dict[str, TechComparison]:
    """
    Reference data for competing memory technologies.

    Values are representative of state-of-the-art (2024–2025).
    Sources: ITRS, IRDS, published review papers.
    """
    return {
        "DRAM": TechComparison(
            name="DRAM (DDR5)",
            energy_pJ=3.0,          # ~3 pJ/bit at 16 Gb DDR5
            density_tb_cm3=0.01,    # ~8 Gb/die, ~100 mm² die
            read_latency_ns=14.0,   # tCAS ≈ 14 ns
            write_latency_ns=14.0,
            endurance_cycles=1e16,  # effectively unlimited
            retention_s=0.064,      # 64 ms refresh
            compute_locality="none",
            maturity="production",
            notes="Requires periodic refresh; volatile",
        ),
        "SRAM": TechComparison(
            name="SRAM (7nm)",
            energy_pJ=0.5,         # ~0.5 pJ/access
            density_tb_cm3=0.001,  # very low density (6T cell)
            read_latency_ns=0.5,   # sub-ns
            write_latency_ns=0.5,
            endurance_cycles=1e16,
            retention_s=1e10,       # as long as powered
            compute_locality="none",
            maturity="production",
            notes="Cache memory; high area cost",
        ),
        "NAND_Flash": TechComparison(
            name="NAND Flash (3D TLC)",
            energy_pJ=1000.0,       # ~1 nJ/bit program
            density_tb_cm3=1.0,     # ~1 Tb/die, stacked
            read_latency_ns=25000,  # ~25 µs page read
            write_latency_ns=500000,  # ~500 µs program
            endurance_cycles=3000,  # TLC endurance
            retention_s=3.15e7,     # ~1 year at room temp
            compute_locality="none",
            maturity="production",
            notes="High density but slow; non-volatile",
        ),
        "PCM": TechComparison(
            name="Phase-Change (PCM/3DXP)",
            energy_pJ=10.0,        # SET/RESET ~ 10 pJ
            density_tb_cm3=0.1,    # 3D XPoint
            read_latency_ns=50.0,
            write_latency_ns=100.0,
            endurance_cycles=1e8,
            retention_s=3.15e8,    # ~10 years
            compute_locality="partial",
            maturity="production",
            notes="Intel Optane (discontinued); analog IMC demos",
        ),
        "MRAM": TechComparison(
            name="STT-MRAM",
            energy_pJ=1.0,         # ~1 pJ/bit
            density_tb_cm3=0.01,
            read_latency_ns=10.0,
            write_latency_ns=10.0,
            endurance_cycles=1e12,
            retention_s=3.15e8,    # ~10 years
            compute_locality="partial",
            maturity="production",
            notes="Non-volatile; embedded MRAM in SoCs",
        ),
        "ReRAM": TechComparison(
            name="ReRAM/Memristor",
            energy_pJ=0.1,         # ~100 fJ switching
            density_tb_cm3=0.1,
            read_latency_ns=10.0,
            write_latency_ns=10.0,
            endurance_cycles=1e6,
            retention_s=3.15e8,
            compute_locality="partial",
            maturity="prototype",
            notes="Analog IMC demonstrations; variability issues",
        ),
        "Magnonic": TechComparison(
            name="Magnonic Logic",
            energy_pJ=0.01,        # ~10 fJ spin-wave switching
            density_tb_cm3=0.001,
            read_latency_ns=100.0,  # spin-wave propagation
            write_latency_ns=100.0,
            endurance_cycles=1e15,
            retention_s=1e-3,       # ~1 ms (dynamic)
            compute_locality="partial",
            maturity="prototype",
            notes="Spin-wave interference logic; limited demos",
        ),
    }


def wcfoma_entry(
    params: NoiseParams = None,
    L: float = 1e-5,
    n_modes: int = 10,
    label: str = "WCFOMA",
) -> TechComparison:
    """Build a TechComparison entry for a WCFOMA configuration."""
    if params is None:
        params = NoiseParams()

    cc = compute_channel_capacity(params, L, n_modes)

    # Energy: excitation + readout
    excite_fJ = 2.6 * (L * 1e6 / 10) ** 3
    readout_fJ = 100 * (params.n_photons / 1e6)
    total_pJ = (excite_fJ + readout_fJ) / 1000

    return TechComparison(
        name=label,
        energy_pJ=total_pJ,
        density_tb_cm3=cc.density_tb_per_cm3,
        read_latency_ns=cc.read_latency_us * 1000,
        write_latency_ns=cc.write_latency_us * 1000,
        endurance_cycles=1e15,      # acoustic — no wear-out
        retention_s=cc.cycle_time_us * 1e-6 * 1000,  # limited by coherence
        compute_locality="unified",
        maturity="simulation",
        notes=f"{cc.usable_modes} modes, SNR={10*np.log10(max(cc.snr_per_mode[0],1e-30)):.0f}dB",
    )


# ---------------------------------------------------------------------------
# Comparison and output
# ---------------------------------------------------------------------------

def full_comparison_table(
    wcfoma_configs: List[Tuple[str, NoiseParams, float]] = None,
) -> str:
    """
    Generate a formatted comparison table: all techs + WCFOMA configs.

    Parameters
    ----------
    wcfoma_configs : list of (label, NoiseParams, L_meters)
        WCFOMA configurations to include. If None, uses baseline + mitigated.
    """
    db = technology_database()

    if wcfoma_configs is None:
        wcfoma_configs = [
            ("WCFOMA (baseline)", NoiseParams(), 1e-5),
            ("WCFOMA (gel+10⁸ph)", NoiseParams(viscosity=1.0, n_photons=1e8), 1e-5),
            ("WCFOMA (gel+10⁸ph, 50µm)", NoiseParams(viscosity=1.0, n_photons=1e8, V_cavity=(50e-6)**3), 50e-6),
        ]

    entries = list(db.values())
    for label, params, L in wcfoma_configs:
        entries.append(wcfoma_entry(params, L, label=label))

    header = (
        f"{'Technology':<28} {'Energy':>8} {'Density':>10} "
        f"{'Read':>8} {'Write':>8} {'Endur.':>8} {'Retain':>10} "
        f"{'Compute':>10} {'Stage':>12}"
    )
    units = (
        f"{'':28} {'[pJ]':>8} {'[Tb/cm³]':>10} "
        f"{'[ns]':>8} {'[ns]':>8} {'[cyc]':>8} {'[s]':>10} "
        f"{'locality':>10} {'':>12}"
    )

    lines = [
        "=" * 120,
        "  MEMORY TECHNOLOGY COMPARISON",
        "=" * 120,
        f"  {header}",
        f"  {units}",
        "-" * 120,
    ]

    for e in entries:
        retain_str = f"{e.retention_s:.1e}" if e.retention_s < 1e6 else f"{e.retention_s/3.15e7:.0f}yr"
        lines.append(
            f"  {e.name:<28} {e.energy_pJ:>8.2f} {e.density_tb_cm3:>10.4f} "
            f"{e.read_latency_ns:>8.0f} {e.write_latency_ns:>8.0f} "
            f"{e.endurance_cycles:>8.0e} {retain_str:>10} "
            f"{e.compute_locality:>10} {e.maturity:>12}"
        )

    lines.append("=" * 120)
    return "\n".join(lines)


def capacity_summary(cc: ChannelCapacity, label: str = "") -> str:
    """Formatted summary of a channel capacity analysis."""
    paper_bpm = 10.0  # paper's claimed bits/mode
    paper_total = paper_bpm * len(cc.mode_indices)

    lines = [
        "=" * 65,
        f"  CHANNEL CAPACITY ANALYSIS {label}",
        "=" * 65,
        f"  Cavity: {cc.cavity_length_m*1e6:.0f} µm  |  Modes: {len(cc.mode_indices)}  |  Usable: {cc.usable_modes}",
        f"  Bandwidth: {cc.noise_params.bandwidth/1e6:.0f} MHz",
        "-" * 65,
        f"  {'Mode':<6} {'Freq[MHz]':<10} {'SNR[dB]':<10} {'b/meas':<10} {'C[Mb/s]':<10}",
    ]
    for i in range(len(cc.mode_indices)):
        snr_db = 10 * np.log10(max(cc.snr_per_mode[i], 1e-30))
        lines.append(
            f"  {cc.mode_indices[i]:<6} "
            f"{cc.mode_frequencies[i]/1e6:<10.1f} "
            f"{snr_db:<10.1f} "
            f"{cc.bits_per_measurement[i]:<10.2f} "
            f"{cc.capacity_per_mode[i]/1e6:<10.2f}"
        )

    lines.extend([
        "-" * 65,
        f"  Total bits/measurement:   {cc.total_bits_per_measurement:.2f}  (paper claims {paper_total:.0f})",
        f"  Paper overestimates by:   {paper_total/max(cc.total_bits_per_measurement,0.01):.1f}×" if cc.total_bits_per_measurement > 0 else
        f"  Paper overestimates by:   ∞× (0 usable bits)",
        f"  Total capacity:           {cc.total_capacity_bps/1e6:.2f} Mb/s",
        f"  Storage density:          {cc.density_tb_per_cm3:.4f} Tb/cm³",
        "-" * 65,
        f"  Write latency:  {cc.write_latency_us:.4f} µs ({cc.write_latency_us*1000:.1f} ns)",
        f"  Read latency:   {cc.read_latency_us:.2f} µs",
        f"  Cycle time:     {cc.cycle_time_us:.2f} µs",
        f"  Bandwidth:      {cc.bandwidth_mbps:.2f} Mb/s",
        "=" * 65,
    ])
    return "\n".join(lines)
