"""
Common constants, default parameters, and utility functions shared across
all WCFOMA simulations.

Reference: WCFOMA paper v9, Sections 3–5 and Appendix D.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Project-level counts (single source of truth for paper, PDFs, docs)
# ---------------------------------------------------------------------------
SIM_MODULE_COUNT = 41        # Number of simulation modules in simulations/
TEST_COUNT = 1635            # Total automated tests (pytest --collect-only -q)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
K_B = 1.380649e-23          # Boltzmann constant  (J/K)
C_AIR = 340.0               # Speed of sound in air (m/s)
C_ZIM_FULL = 3.4e8          # ZIM effective wave speed (m/s) — near-infinite phase velocity
C_ZIM_SCALED = 3.4e4        # Numerically tractable scaled ZIM speed (m/s)
C_FERROFLUID = 1400.0       # Approximate speed of sound in ferrofluid (m/s)


# ---------------------------------------------------------------------------
# Default simulation parameters (from paper Section 5.3)
# ---------------------------------------------------------------------------
@dataclass
class DilatancyParams:
    """Parameters governing granular dilatancy response."""
    beta: float = 1.0               # Dilation coefficient (dimensionless)
    gamma: float = 0.3              # Applied shear strain (dimensionless)
    eta_coefficient: float = 333.333  # Viscous damping rate per unit shear (1/s)
    zim_damping_factor: float = 0.5   # ZIM reduces damping by this factor

    @property
    def eta(self) -> float:
        """Effective damping rate for normal medium."""
        return self.eta_coefficient * self.gamma

    @property
    def eta_zim(self) -> float:
        """Effective damping rate for ZIM medium."""
        return self.eta * self.zim_damping_factor

    def dilated_length(self, L: float) -> float:
        """Return dilated cavity length under shear: L' = L(1 + β·γ)."""
        return L * (1.0 + self.beta * self.gamma)


@dataclass
class CavityParams:
    """Parameters for a resonant cavity."""
    L: float = 1.0                  # Base cavity length (m)
    c_normal: float = C_AIR         # Normal wave speed (m/s)
    c_zim: float = C_ZIM_SCALED     # ZIM wave speed (m/s)
    dilatancy: DilatancyParams = field(default_factory=DilatancyParams)

    def mode_frequency(self, n: int, c: Optional[float] = None,
                       L: Optional[float] = None) -> float:
        """
        Resonant frequency for mode n in a 1D cavity.
        f_n = n * c / (2 * L)
        """
        c = c if c is not None else self.c_normal
        L = L if L is not None else self.L
        return n * c / (2.0 * L)


@dataclass
class ThermalParams:
    """Parameters for thermal drift analysis (Addendum, Section 2)."""
    alpha: float = 0.0022    # Fractional frequency drift per Kelvin (/K)
    delta_T: float = 5.0     # Temperature variation (K)
    Q: float = 500.0         # Quality factor (conservative for micro-scale)
    drift_reduction_zim: float = 20.0  # ZIM drift reduction factor


@dataclass
class MicroCellParams:
    """Parameters for a micro-scale WCFOMA cell."""
    L: float = 1e-5          # Cell length (m) — 10 µm
    c: float = C_AIR         # Wave speed (m/s)
    bits_per_mode: int = 10  # Analog encoding depth (bits)
    cells_per_cm3: float = 1e9  # Cell packing density

    @property
    def delta_f(self) -> float:
        """Mode spacing (Hz)."""
        return self.c / (2.0 * self.L)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------
def thermal_noise_amplitude(k_eff: float, T: float = 300.0) -> float:
    """
    Thermal noise amplitude for a harmonic mode.
    A_thermal = sqrt(k_B T / k_eff)
    """
    return np.sqrt(K_B * T / k_eff)


def excitation_energy(k_eff: float, amplitude: float) -> float:
    """
    Energy to excite a mode: E = 0.5 * k * A^2
    """
    return 0.5 * k_eff * amplitude**2
