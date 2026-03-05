"""
Mitigation Analysis for WCFOMA Phase Diffusion Kill Risk.

Phase 2 analysis revealed that nanoparticle Brownian phase diffusion
dominates the noise budget at 77.5%, producing SNR = -6.5 dB and 0
reliable modes at the default (10 µm)³ micro-cell parameters.

This module systematically explores mitigations:
  1. Gel immobilization — embed nanoparticles in hydrogel/silica matrix
  2. Cavity scaling — larger cavities average over more particles
  3. Optical readout improvement — more photons reduce shot noise
  4. Higher excitation — brute-force SNR gain (at energy cost)
  5. Ensemble averaging — multi-cell readout for noise reduction
  6. Combined strategies — find the minimum viable parameter set

Key finding: BOTH phase diffusion AND shot noise must be addressed.
No single mitigation is sufficient. The minimum viable combination is:
  gel immobilization (viscosity ×1000) + optical readout (≥10⁸ photons).

References:
  - Notebook 08: phase diffusion kill finding
  - Coffey, "The Langevin Equation" (2004) — Brownian dynamics
  - Rosensweig, "Ferrohydrodynamics" (1985) — ferrofluid properties
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import numpy as np

from .common import K_B, C_FERROFLUID, MicroCellParams
from .noise_decoherence import (
    NoiseParams, NoiseSpectrum, DecoherenceResult,
    compute_noise_spectrum, snr_at_mode, run_decoherence_analysis,
    phase_diffusion_rate,
)


# ---------------------------------------------------------------------------
# Mitigation scenario definitions
# ---------------------------------------------------------------------------

@dataclass
class MitigationScenario:
    """A named set of parameter modifications with cost estimates."""
    name: str
    description: str
    params: NoiseParams
    # Physical feasibility metrics
    cavity_length_m: float = 1e-5       # effective cavity side length
    energy_cost_fJ: float = 2.6         # excitation energy [fJ]
    readout_energy_fJ: float = 100.0    # readout optical energy [fJ]
    complexity: str = "low"             # "low", "medium", "high"
    fabrication_trl: int = 3            # technology readiness level (1–9)
    notes: str = ""


@dataclass
class MitigationSweepResult:
    """Result of sweeping one parameter across a range."""
    parameter_name: str
    parameter_values: np.ndarray
    snr_values: np.ndarray          # dB
    reliable_modes: np.ndarray      # count
    dominant_noise: List[str]
    threshold_value: Optional[float]  # value where SNR first exceeds 10 dB
    threshold_modes: Optional[int]    # modes at threshold


@dataclass
class ViabilityMap:
    """2D map of SNR across two parameter axes."""
    param1_name: str
    param1_values: np.ndarray
    param2_name: str
    param2_values: np.ndarray
    snr_grid: np.ndarray            # (n1, n2) in dB
    modes_grid: np.ndarray          # (n1, n2) reliable modes
    viable_mask: np.ndarray         # (n1, n2) bool — SNR > 10 dB


# ---------------------------------------------------------------------------
# Scenario constructors
# ---------------------------------------------------------------------------

def baseline_scenario() -> MitigationScenario:
    """Default (10 µm)³ micro-cell — the paper's target."""
    return MitigationScenario(
        name="Baseline",
        description="Paper default: (10 µm)³ ferrofluid micro-cell, optical readout",
        params=NoiseParams(),
        cavity_length_m=1e-5,
        energy_cost_fJ=2.6,
        readout_energy_fJ=100.0,
        complexity="low",
        fabrication_trl=3,
        notes="SNR = -6.5 dB, 0 modes — NOT VIABLE",
    )


def gel_immobilized_scenario(
    viscosity_multiplier: float = 1000.0,
) -> MitigationScenario:
    """
    Nanoparticles embedded in a hydrogel or silica matrix.

    Physically: the nanoparticles are dispersed in a thermo-reversible
    gel (e.g., agarose, PVA, or sol-gel silica), dramatically reducing
    their translational and rotational Brownian motion.

    Effective viscosity increases by 10²–10⁵ depending on matrix.
    Trade-off: may reduce Q factor if matrix absorbs acoustic energy.
    """
    eff_viscosity = 0.01 * viscosity_multiplier
    return MitigationScenario(
        name=f"Gel immobilized (η×{viscosity_multiplier:.0f})",
        description=f"Nanoparticles in gel matrix, effective viscosity ×{viscosity_multiplier:.0f}",
        params=NoiseParams(viscosity=eff_viscosity),
        cavity_length_m=1e-5,
        energy_cost_fJ=2.6,
        readout_energy_fJ=100.0,
        complexity="medium",
        fabrication_trl=4,
        notes="Gel-immobilized ferrofluids are well-established in literature",
    )


def larger_cavity_scenario(
    L_um: float = 100.0,
) -> MitigationScenario:
    """
    Larger cavity for better noise averaging.

    Phase diffusion noise scales as coupling² × N_particles, where
    coupling = V_particle / V_cavity. For fixed φ, increasing V_cavity
    reduces the per-particle coupling faster than the particle count grows.

    Trade-off: fewer cells per cm³, reducing storage density.
    """
    L_m = L_um * 1e-6
    V = L_m**3
    cells_per_cm3 = 1e-6 / V  # approximate packing
    return MitigationScenario(
        name=f"Larger cavity ({L_um:.0f} µm)",
        description=f"Cavity side length {L_um:.0f} µm, volume {V:.1e} m³",
        params=NoiseParams(V_cavity=V),
        cavity_length_m=L_m,
        energy_cost_fJ=2.6 * (L_um / 10)**3,  # scales with volume
        readout_energy_fJ=100.0,
        complexity="low",
        fabrication_trl=5,
        notes=f"~{cells_per_cm3:.1e} cells/cm³ (vs 1e9 at 10 µm)",
    )


def high_photon_scenario(
    n_photons: float = 1e8,
) -> MitigationScenario:
    """
    Improved optical readout with more photons.

    Shot noise PSD = 1/N_photons. Increasing from 10⁶ to 10⁸–10¹⁰
    drops the shot noise floor by 20–40 dB.

    Trade-off: readout energy increases proportionally.
    """
    readout_fJ = 100.0 * (n_photons / 1e6)  # linear with photon count
    return MitigationScenario(
        name=f"High-photon readout ({n_photons:.0e})",
        description=f"Optical readout with {n_photons:.0e} photons per measurement",
        params=NoiseParams(n_photons=n_photons),
        cavity_length_m=1e-5,
        energy_cost_fJ=2.6,
        readout_energy_fJ=readout_fJ,
        complexity="medium",
        fabrication_trl=5,
        notes=f"Readout energy {readout_fJ:.0f} fJ — may dominate energy budget",
    )


def combined_scenario(
    viscosity_multiplier: float = 1000.0,
    L_um: float = 100.0,
    n_photons: float = 1e8,
    A_signal: float = 1.0,
) -> MitigationScenario:
    """
    Combined mitigation — the minimum viable configuration.

    Addresses BOTH noise barriers simultaneously:
    1. Gel immobilization → eliminates phase diffusion
    2. More photons → reduces shot noise floor
    3. Optionally larger cavity or stronger excitation
    """
    L_m = L_um * 1e-6
    V = L_m**3
    eff_viscosity = 0.01 * viscosity_multiplier
    readout_fJ = 100.0 * (n_photons / 1e6)
    excite_fJ = 2.6 * A_signal**2 * (L_um / 10)**3

    return MitigationScenario(
        name=f"Combined (η×{viscosity_multiplier:.0f}, {L_um:.0f}µm, {n_photons:.0e}ph)",
        description=(
            f"Gel η×{viscosity_multiplier:.0f} + {L_um:.0f} µm cavity "
            f"+ {n_photons:.0e} photons + A={A_signal}"
        ),
        params=NoiseParams(
            viscosity=eff_viscosity,
            V_cavity=V,
            n_photons=n_photons,
            A_signal=A_signal,
        ),
        cavity_length_m=L_m,
        energy_cost_fJ=excite_fJ,
        readout_energy_fJ=readout_fJ,
        complexity="high",
        fabrication_trl=3,
        notes="Minimum viable: gel + high-photon readout",
    )


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def evaluate_scenario(
    scenario: MitigationScenario,
    n_modes: int = 10,
) -> Dict:
    """
    Evaluate a mitigation scenario — SNR, reliable modes, kill criteria.

    Returns a dict with all key metrics.
    """
    p = scenario.params
    L = scenario.cavity_length_m
    f0 = C_FERROFLUID / (2 * L)

    # Noise spectrum at fundamental
    ns = compute_noise_spectrum(f0, p)

    # SNR at fundamental
    snr_db = snr_at_mode(1, p, L)

    # Full decoherence analysis
    result = run_decoherence_analysis(params=p, L=L)

    # Total energy (excitation + readout + CMOS)
    total_energy_fJ = scenario.energy_cost_fJ + scenario.readout_energy_fJ

    # Storage density
    cell = MicroCellParams()
    cells_per_cm3 = 1e-6 / (L**3)  # approximate packing
    density_tb = result.max_reliable_modes * cell.bits_per_mode * cells_per_cm3 / 1e12

    return {
        "name": scenario.name,
        "snr_db": snr_db,
        "reliable_modes": result.max_reliable_modes,
        "dominant_noise": result.dominant_noise_source,
        "noise_spectrum": ns,
        "total_energy_fJ": total_energy_fJ,
        "density_tb_cm3": density_tb,
        "cavity_um": L * 1e6,
        "kill_snr": result.snr_above_10dB,
        "kill_ber": result.ber_below_1pct,
        "kill_lifetime": result.lifetime_above_1us,
        "viable": result.max_reliable_modes >= 5,
        "complexity": scenario.complexity,
        "trl": scenario.fabrication_trl,
        "decoherence_result": result,
    }


def sweep_viscosity(
    multipliers: np.ndarray = None,
    base_params: NoiseParams = None,
    L: float = 1e-5,
) -> MitigationSweepResult:
    """Sweep viscosity multiplier to find gel immobilization threshold."""
    if multipliers is None:
        multipliers = np.logspace(0, 5, 30)
    if base_params is None:
        base_params = NoiseParams()

    snrs = np.zeros(len(multipliers))
    modes = np.zeros(len(multipliers), dtype=int)
    dominants = []

    for i, mult in enumerate(multipliers):
        p = NoiseParams(
            viscosity=0.01 * mult,
            n_photons=base_params.n_photons,
            V_cavity=base_params.V_cavity,
            A_signal=base_params.A_signal,
        )
        snrs[i] = snr_at_mode(1, p, L)
        res = run_decoherence_analysis(params=p, L=L)
        modes[i] = res.max_reliable_modes
        dominants.append(res.dominant_noise_source)

    # Find threshold
    above = np.where(snrs > 10.0)[0]
    threshold = float(multipliers[above[0]]) if len(above) > 0 else None
    thresh_modes = int(modes[above[0]]) if len(above) > 0 else None

    return MitigationSweepResult(
        parameter_name="viscosity_multiplier",
        parameter_values=multipliers,
        snr_values=snrs,
        reliable_modes=modes,
        dominant_noise=dominants,
        threshold_value=threshold,
        threshold_modes=thresh_modes,
    )


def sweep_photons(
    photon_counts: np.ndarray = None,
    base_params: NoiseParams = None,
    L: float = 1e-5,
) -> MitigationSweepResult:
    """Sweep readout photon count."""
    if photon_counts is None:
        photon_counts = np.logspace(5, 11, 30)
    if base_params is None:
        base_params = NoiseParams()

    snrs = np.zeros(len(photon_counts))
    modes = np.zeros(len(photon_counts), dtype=int)
    dominants = []

    for i, nph in enumerate(photon_counts):
        p = NoiseParams(
            n_photons=nph,
            viscosity=base_params.viscosity,
            V_cavity=base_params.V_cavity,
            A_signal=base_params.A_signal,
        )
        snrs[i] = snr_at_mode(1, p, L)
        res = run_decoherence_analysis(params=p, L=L)
        modes[i] = res.max_reliable_modes
        dominants.append(res.dominant_noise_source)

    above = np.where(snrs > 10.0)[0]
    threshold = float(photon_counts[above[0]]) if len(above) > 0 else None
    thresh_modes = int(modes[above[0]]) if len(above) > 0 else None

    return MitigationSweepResult(
        parameter_name="n_photons",
        parameter_values=photon_counts,
        snr_values=snrs,
        reliable_modes=modes,
        dominant_noise=dominants,
        threshold_value=threshold,
        threshold_modes=thresh_modes,
    )


def sweep_cavity_size(
    L_values_um: np.ndarray = None,
    base_params: NoiseParams = None,
) -> MitigationSweepResult:
    """Sweep cavity size."""
    if L_values_um is None:
        L_values_um = np.logspace(1, 3.5, 30)  # 10 µm to ~3 mm
    if base_params is None:
        base_params = NoiseParams()

    snrs = np.zeros(len(L_values_um))
    modes = np.zeros(len(L_values_um), dtype=int)
    dominants = []

    for i, L_um in enumerate(L_values_um):
        L_m = L_um * 1e-6
        V = L_m**3
        p = NoiseParams(
            V_cavity=V,
            viscosity=base_params.viscosity,
            n_photons=base_params.n_photons,
            A_signal=base_params.A_signal,
        )
        snrs[i] = snr_at_mode(1, p, L_m)
        res = run_decoherence_analysis(params=p, L=L_m)
        modes[i] = res.max_reliable_modes
        dominants.append(res.dominant_noise_source)

    above = np.where(snrs > 10.0)[0]
    threshold = float(L_values_um[above[0]]) if len(above) > 0 else None
    thresh_modes = int(modes[above[0]]) if len(above) > 0 else None

    return MitigationSweepResult(
        parameter_name="cavity_length_um",
        parameter_values=L_values_um,
        snr_values=snrs,
        reliable_modes=modes,
        dominant_noise=dominants,
        threshold_value=threshold,
        threshold_modes=thresh_modes,
    )


def compute_viability_map(
    viscosity_mults: np.ndarray = None,
    photon_counts: np.ndarray = None,
    L: float = 1e-5,
) -> ViabilityMap:
    """
    Compute 2D SNR map: viscosity multiplier × photon count.

    This reveals the minimum viable combined mitigation.
    """
    if viscosity_mults is None:
        viscosity_mults = np.logspace(0, 4, 20)
    if photon_counts is None:
        photon_counts = np.logspace(5, 10, 20)

    n1 = len(viscosity_mults)
    n2 = len(photon_counts)
    snr_grid = np.zeros((n1, n2))
    modes_grid = np.zeros((n1, n2), dtype=int)

    for i, vm in enumerate(viscosity_mults):
        for j, nph in enumerate(photon_counts):
            p = NoiseParams(
                viscosity=0.01 * vm,
                n_photons=nph,
                V_cavity=L**3,
            )
            snr_grid[i, j] = snr_at_mode(1, p, L)
            # Quick mode count via SNR threshold (avoid full analysis for speed)
            if snr_grid[i, j] > 10.0:
                res = run_decoherence_analysis(params=p, L=L)
                modes_grid[i, j] = res.max_reliable_modes
            else:
                modes_grid[i, j] = 0

    return ViabilityMap(
        param1_name="viscosity_multiplier",
        param1_values=viscosity_mults,
        param2_name="n_photons",
        param2_values=photon_counts,
        snr_grid=snr_grid,
        modes_grid=modes_grid,
        viable_mask=snr_grid > 10.0,
    )


def find_minimum_viable(
    L: float = 1e-5,
    target_snr_db: float = 10.0,
    target_modes: int = 5,
) -> Dict:
    """
    Find the minimum parameter modifications that achieve viability.

    Searches for the smallest combined mitigation that produces
    SNR > target_snr_db and at least target_modes reliable modes.

    Returns a dict describing the minimum viable configuration.
    """
    # Strategy: fix gel at moderate level, find minimum photons
    # Then try larger cavity instead of gel

    results = {}

    # Path 1: Gel + photons (keep 10 µm cavity)
    for vm in [10, 100, 1000, 10000]:
        for nph_exp in range(6, 12):
            nph = 10**nph_exp
            p = NoiseParams(
                viscosity=0.01 * vm,
                n_photons=nph,
                V_cavity=L**3,
            )
            snr = snr_at_mode(1, p, L)
            if snr > target_snr_db:
                res = run_decoherence_analysis(params=p, L=L)
                if res.max_reliable_modes >= target_modes:
                    results["gel_photons"] = {
                        "viscosity_mult": vm,
                        "n_photons": nph,
                        "cavity_um": L * 1e6,
                        "snr_db": snr,
                        "modes": res.max_reliable_modes,
                        "total_energy_fJ": 2.6 + 100 * (nph / 1e6),
                    }
                    break
        if "gel_photons" in results:
            break

    # Path 2: Larger cavity + photons (no gel)
    for L_um in [50, 100, 200, 500, 1000]:
        L_m = L_um * 1e-6
        for nph_exp in range(6, 12):
            nph = 10**nph_exp
            p = NoiseParams(
                V_cavity=L_m**3,
                n_photons=nph,
            )
            snr = snr_at_mode(1, p, L_m)
            if snr > target_snr_db:
                res = run_decoherence_analysis(params=p, L=L_m)
                if res.max_reliable_modes >= target_modes:
                    results["cavity_photons"] = {
                        "viscosity_mult": 1,
                        "n_photons": nph,
                        "cavity_um": L_um,
                        "snr_db": snr,
                        "modes": res.max_reliable_modes,
                        "total_energy_fJ": 2.6 * (L_um / 10)**3 + 100 * (nph / 1e6),
                    }
                    break
        if "cavity_photons" in results:
            break

    # Path 3: Combined gel + cavity + photons
    for vm in [10, 100]:
        for L_um in [10, 50, 100]:
            L_m = L_um * 1e-6
            for nph_exp in range(6, 12):
                nph = 10**nph_exp
                p = NoiseParams(
                    viscosity=0.01 * vm,
                    V_cavity=L_m**3,
                    n_photons=nph,
                )
                snr = snr_at_mode(1, p, L_m)
                if snr > target_snr_db:
                    res = run_decoherence_analysis(params=p, L=L_m)
                    if res.max_reliable_modes >= target_modes:
                        results["combined"] = {
                            "viscosity_mult": vm,
                            "n_photons": nph,
                            "cavity_um": L_um,
                            "snr_db": snr,
                            "modes": res.max_reliable_modes,
                            "total_energy_fJ": (
                                2.6 * (L_um / 10)**3 + 100 * (nph / 1e6)
                            ),
                        }
                        break
            if "combined" in results:
                break
        if "combined" in results:
            break

    return results


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

def scenario_comparison_table(scenarios: List[MitigationScenario]) -> str:
    """
    Generate a formatted comparison table for multiple scenarios.
    """
    header = (
        f"{'Scenario':<35} {'SNR[dB]':>8} {'Modes':>6} "
        f"{'Dominant':>18} {'Energy[fJ]':>10} {'TRL':>4} {'Viable':>7}"
    )
    lines = [
        "=" * 100,
        "  MITIGATION SCENARIO COMPARISON",
        "=" * 100,
        f"  {header}",
        "-" * 100,
    ]

    for sc in scenarios:
        ev = evaluate_scenario(sc)
        viable = "✅ YES" if ev["viable"] else "❌ NO"
        lines.append(
            f"  {sc.name:<35} {ev['snr_db']:>8.1f} {ev['reliable_modes']:>6} "
            f"{ev['dominant_noise']:>18} {ev['total_energy_fJ']:>10.0f} "
            f"{sc.fabrication_trl:>4} {viable:>7}"
        )

    lines.append("=" * 100)
    return "\n".join(lines)


def mitigation_summary() -> str:
    """
    Generate the canonical mitigation summary — all key scenarios.
    """
    scenarios = [
        baseline_scenario(),
        gel_immobilized_scenario(100),
        gel_immobilized_scenario(1000),
        larger_cavity_scenario(100),
        larger_cavity_scenario(500),
        high_photon_scenario(1e8),
        high_photon_scenario(1e10),
        combined_scenario(1000, 10, 1e8),
        combined_scenario(100, 50, 1e8),
        combined_scenario(1000, 100, 1e9),
    ]
    table = scenario_comparison_table(scenarios)

    # Find minimum viable
    mvp = find_minimum_viable()

    lines = [table, "", "MINIMUM VIABLE CONFIGURATIONS:", "-" * 50]
    for path, config in mvp.items():
        lines.append(
            f"  {path}: η×{config['viscosity_mult']}, "
            f"{config['cavity_um']:.0f} µm cavity, "
            f"{config['n_photons']:.0e} photons → "
            f"SNR={config['snr_db']:.1f} dB, "
            f"{config['modes']} modes, "
            f"~{config['total_energy_fJ']:.0f} fJ total"
        )

    lines.extend([
        "",
        "KEY INSIGHT:",
        "  Phase diffusion AND shot noise are independent barriers.",
        "  No single mitigation is sufficient at the (10 µm)³ scale.",
        "  Minimum viable: gel immobilization + improved optical readout.",
        "  The architecture IS viable under achievable physical conditions,",
        "  but the paper's default micro-cell parameters need revision.",
    ])

    return "\n".join(lines)
