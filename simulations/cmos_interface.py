"""
CMOS Interface Energy Model for WCFOMA

Models the energy budget of reading/writing a single WCFOMA memory cell
through a realistic analog CMOS front-end.  This is critical for validating
the paper's claim of fJ-scale energy per operation.

The readout chain is:
  1. Excitation pulse (write) — transducer drives cavity mode
  2. Sensing (read) — pickup coil / Faraday rotation captures signal
  3. ADC digitization — converts analog resonance to digital representation
  4. Thermal noise floor — sets minimum signal energy

Reference: Paper Sections 5.2, 6.1, 8 — energy projections.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional

from .common import K_B, C_FERROFLUID


# ---------------------------------------------------------------------------
# Physical / circuit constants
# ---------------------------------------------------------------------------
E_CHARGE = 1.602e-19           # Coulomb
KT_ROOM = K_B * 300.0          # Thermal energy at room temperature (J)

# CMOS technology nodes — typical Cgate and fT
TECH_NODES = {
    "180nm": {"C_gate": 10e-15, "f_T": 40e9,  "V_dd": 1.8},
    "65nm":  {"C_gate": 1.5e-15, "f_T": 200e9, "V_dd": 1.2},
    "28nm":  {"C_gate": 0.7e-15, "f_T": 300e9, "V_dd": 0.9},
    "7nm":   {"C_gate": 0.3e-15, "f_T": 500e9, "V_dd": 0.7},
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class TransducerParams:
    """Excitation/sensing transducer model."""
    # Inductive coil parameters
    n_turns: int = 100              # Coil turns
    coil_radius: float = 5e-3      # Coil radius (m)
    coil_inductance: float = 1e-6   # Inductance (H)
    coil_resistance: float = 1.0    # DC resistance (Ω)
    coupling_factor: float = 0.1    # Fraction of energy coupled to cavity

    # Faraday rotation readout (alternative)
    laser_power: float = 1e-6       # Laser power (W)
    readout_time: float = 1e-9      # Integration time (s)


@dataclass
class ADCParams:
    """ADC specification."""
    bits: int = 10                  # Resolution
    sample_rate: float = 100e6      # Samples/s
    energy_per_conversion: float = 1e-12  # J (1 pJ — state-of-art SAR ADC)


@dataclass
class CellEnergyBudget:
    """Complete energy budget for one read/write operation."""
    # Write path
    E_excitation: float = 0.0       # Energy to excite cavity mode (J)
    E_thermal_min: float = 0.0      # Minimum excitation to beat thermal noise (J)

    # Read path
    E_sense: float = 0.0            # Sensing energy (J)
    E_amplifier: float = 0.0        # Preamplifier energy (J)
    E_adc: float = 0.0              # ADC conversion energy (J)

    # Overhead
    E_addressing: float = 0.0       # Row/column selection energy (J)
    E_io: float = 0.0               # I/O driver energy (J)

    @property
    def E_write_total(self) -> float:
        return self.E_excitation + self.E_addressing

    @property
    def E_read_total(self) -> float:
        return self.E_sense + self.E_amplifier + self.E_adc + self.E_addressing

    @property
    def E_total(self) -> float:
        """Total energy for one write + one read."""
        return self.E_write_total + self.E_read_total

    def breakdown_dict(self) -> Dict[str, float]:
        return {
            "Excitation":   self.E_excitation,
            "Thermal min":  self.E_thermal_min,
            "Sensing":      self.E_sense,
            "Amplifier":    self.E_amplifier,
            "ADC":          self.E_adc,
            "Addressing":   self.E_addressing,
            "I/O":          self.E_io,
            "Write total":  self.E_write_total,
            "Read total":   self.E_read_total,
            "Total":        self.E_total,
        }

    def summary(self) -> str:
        lines = [
            "=" * 55,
            "CMOS Interface Energy Budget (per operation)",
            "=" * 55,
        ]
        for k, v in self.breakdown_dict().items():
            if k in ("Write total", "Read total", "Total"):
                lines.append("-" * 55)
            lines.append(f"  {k:<20s}  {v:>12.2e} J  ({v*1e15:>8.1f} fJ)")
        lines.append("=" * 55)
        return "\n".join(lines)


@dataclass
class CMOSInterfaceModel:
    """Full CMOS interface model combining all sub-models."""
    tech_node: str = "28nm"
    transducer: TransducerParams = field(default_factory=TransducerParams)
    adc: ADCParams = field(default_factory=ADCParams)
    cell_length: float = 10e-6      # Cell size (m)
    c_medium: float = C_FERROFLUID  # Wave speed in medium (m/s)
    Q: float = 500.0                # Quality factor
    n_modes: int = 10               # Modes per cell
    T: float = 300.0                # Temperature (K)


# ---------------------------------------------------------------------------
# Energy calculations
# ---------------------------------------------------------------------------
def excitation_energy(
    cell_length: float,
    c: float,
    Q: float,
    n_modes: int = 1,
    T: float = 300.0,
    snr_margin: float = 10.0,
) -> Tuple[float, float]:
    """
    Minimum energy to excite a single mode above thermal noise floor.

    The cavity stores energy E = (1/2) m_eff ω² A² where m_eff is the
    effective mass of the mode. For a fJ-scale operation, we need:
      E_excite >= snr_margin × k_B T

    Also returns the thermal floor energy.

    Parameters
    ----------
    cell_length : float
        Cell dimension (m).
    c : float
        Wave speed in medium (m/s).
    Q : float
        Quality factor.
    n_modes : int
        Number of modes to excite simultaneously.
    T : float
        Temperature (K).
    snr_margin : float
        Required SNR above thermal (linear, not dB).

    Returns
    -------
    (E_excite, E_thermal)
        Excitation energy and thermal floor energy, both in Joules.
    """
    E_thermal = K_B * T
    E_excite = snr_margin * E_thermal * n_modes
    return E_excite, E_thermal


def sensing_energy(
    transducer: TransducerParams,
    method: str = "inductive",
) -> float:
    """
    Energy consumed by the sensing transducer for one readout event.

    Inductive: E = (1/2) L I² where I is set by coupling
    Faraday:   E = P_laser × t_readout
    """
    if method == "inductive":
        # Minimum current to sense one mode: I ~ sqrt(2 kT / L)
        I_min = np.sqrt(2 * KT_ROOM / transducer.coil_inductance)
        # Actual current with coupling overhead
        I_read = I_min / transducer.coupling_factor
        E = 0.5 * transducer.coil_inductance * I_read**2
        # But capped at practical minimum — coil dissipation dominates
        E_dissipation = transducer.coil_resistance * I_read**2 * 1e-9  # 1ns read
        return max(E, E_dissipation)
    elif method == "faraday":
        return transducer.laser_power * transducer.readout_time
    else:
        raise ValueError(f"Unknown sensing method: {method}")


def amplifier_energy(
    tech_node: str = "28nm",
    bandwidth: float = 100e6,
    gain: float = 100.0,
) -> float:
    """
    Preamplifier energy for one readout cycle.

    Uses CMOS technology-specific parameters. The amplifier operates
    for one readout window (≈ 1/bandwidth).

    E_amp ≈ C_gate × V_dd² × (bandwidth / f_T) × gain_stages
    """
    tech = TECH_NODES.get(tech_node, TECH_NODES["28nm"])
    C_gate = tech["C_gate"]
    V_dd = tech["V_dd"]
    f_T = tech["f_T"]

    # Number of gain stages (each gives ~10× gain)
    n_stages = max(1, int(np.ceil(np.log10(gain))))

    # Energy per stage per cycle
    E_per_stage = C_gate * V_dd**2

    # Bandwidth fraction of fT determines how many transistors switch
    bw_fraction = min(1.0, bandwidth / f_T)

    # Total: stages × switching energy × bandwidth utilization
    # Factor of 10 accounts for bias currents and parasitic switching
    E_amp = n_stages * E_per_stage * bw_fraction * 10

    # Scale by readout window
    t_read = 1.0 / bandwidth
    return E_amp


def addressing_energy(
    tech_node: str = "28nm",
    array_size: int = 1000,
) -> float:
    """
    Energy to select one cell in an array (row/column decoders + wordline).

    E_address ≈ C_wire × V_dd² where C_wire scales with sqrt(array_size)
    """
    tech = TECH_NODES.get(tech_node, TECH_NODES["28nm"])
    V_dd = tech["V_dd"]

    # Wire capacitance model: ~0.2 fF/µm, wordline length ~ sqrt(N) × 10µm
    wire_length_um = np.sqrt(array_size) * 10
    C_wire = wire_length_um * 0.2e-15  # F

    # Decoder switching (log2(N) gates)
    n_decoder_gates = max(1, int(np.ceil(np.log2(array_size))))
    C_gate = TECH_NODES[tech_node]["C_gate"]
    E_decoder = n_decoder_gates * C_gate * V_dd**2

    return C_wire * V_dd**2 + E_decoder


def compute_energy_budget(
    model: Optional[CMOSInterfaceModel] = None,
    sensing_method: str = "inductive",
) -> CellEnergyBudget:
    """
    Compute the complete energy budget for one WCFOMA cell operation.

    Parameters
    ----------
    model : CMOSInterfaceModel
        Full interface specification. Uses defaults if None.
    sensing_method : str
        "inductive" or "faraday"

    Returns
    -------
    CellEnergyBudget
    """
    if model is None:
        model = CMOSInterfaceModel()

    # Write energy
    E_excite, E_thermal = excitation_energy(
        model.cell_length, model.c_medium, model.Q,
        model.n_modes, model.T,
    )

    # Read energy
    E_sense = sensing_energy(model.transducer, sensing_method)
    E_amp = amplifier_energy(model.tech_node, bandwidth=model.c_medium / model.cell_length)
    E_adc_val = model.adc.energy_per_conversion

    # Addressing
    E_addr = addressing_energy(model.tech_node, array_size=1000)

    # I/O (negligible for on-chip, ~pJ for off-chip)
    E_io = 0.0

    return CellEnergyBudget(
        E_excitation=E_excite,
        E_thermal_min=E_thermal,
        E_sense=E_sense,
        E_amplifier=E_amp,
        E_adc=E_adc_val,
        E_addressing=E_addr,
        E_io=E_io,
    )


# ---------------------------------------------------------------------------
# Comparison with conventional technologies
# ---------------------------------------------------------------------------
def technology_comparison(budget: CellEnergyBudget) -> Dict[str, Dict[str, float]]:
    """
    Compare WCFOMA energy budget against conventional memory technologies.

    Returns dict of technology -> {energy_per_op, density, ratio_vs_wcfoma}.
    """
    wcfoma_energy = budget.E_total

    technologies = {
        "SRAM (6T, 28nm)": {
            "energy_per_op_J": 5e-15,     # ~5 fJ
            "density_bits_cm3": 1e9,       # ~1 Gb/cm³
        },
        "DRAM (28nm)": {
            "energy_per_op_J": 1e-12,     # ~1 pJ
            "density_bits_cm3": 1e10,      # ~10 Gb/cm³
        },
        "NAND Flash": {
            "energy_per_op_J": 10e-9,     # ~10 nJ (write)
            "density_bits_cm3": 1e12,      # ~1 Tb/cm³
        },
        "ReRAM/MRAM": {
            "energy_per_op_J": 100e-15,   # ~100 fJ
            "density_bits_cm3": 1e10,
        },
        "WCFOMA (this model)": {
            "energy_per_op_J": wcfoma_energy,
            "density_bits_cm3": 3.22e12,   # paper projection
        },
    }

    for tech_name, vals in technologies.items():
        vals["ratio_vs_wcfoma"] = vals["energy_per_op_J"] / wcfoma_energy

    return technologies


def format_comparison_table(technologies: Dict) -> str:
    """Pretty-print technology comparison."""
    lines = [
        f"{'Technology':<25} {'Energy/op':>12} {'Density':>15} {'vs WCFOMA':>12}",
        "-" * 66,
    ]
    for name, vals in technologies.items():
        e = vals["energy_per_op_J"]
        d = vals["density_bits_cm3"]
        r = vals["ratio_vs_wcfoma"]
        # Auto-scale energy
        if e >= 1e-9:
            e_str = f"{e*1e9:.1f} nJ"
        elif e >= 1e-12:
            e_str = f"{e*1e12:.1f} pJ"
        else:
            e_str = f"{e*1e15:.1f} fJ"
        # Auto-scale density
        if d >= 1e12:
            d_str = f"{d/1e12:.2f} Tb/cm³"
        elif d >= 1e9:
            d_str = f"{d/1e9:.1f} Gb/cm³"
        else:
            d_str = f"{d:.1e}"
        lines.append(f"{name:<25} {e_str:>12} {d_str:>15} {r:>11.1f}×")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Kill criteria check
# ---------------------------------------------------------------------------
def energy_kill_check(budget: CellEnergyBudget) -> Dict[str, Tuple[str, bool]]:
    """
    Check energy budget against kill criteria from ROADMAP.

    Returns dict of criterion -> (description, passes).
    """
    checks = {}

    # Kill: energy > pJ (enters DRAM territory)
    checks["total_energy"] = (
        f"Total {budget.E_total*1e15:.1f} fJ < 1 pJ",
        budget.E_total < 1e-12,
    )

    # Kill: excitation below thermal noise
    checks["thermal_margin"] = (
        f"Excitation {budget.E_excitation*1e15:.1f} fJ > "
        f"thermal {budget.E_thermal_min*1e15:.3f} fJ",
        budget.E_excitation > budget.E_thermal_min,
    )

    # Warning: read energy dominates (suggests interface is bottleneck)
    read_frac = budget.E_read_total / budget.E_total if budget.E_total > 0 else 0
    checks["read_fraction"] = (
        f"Read fraction {read_frac*100:.0f}% (< 90% target)",
        read_frac < 0.9,
    )

    return checks
