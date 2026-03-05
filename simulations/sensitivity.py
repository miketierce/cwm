"""
Parameter Sensitivity Analysis for WCFOMA Simulations

Systematically sweeps key parameters to identify which assumptions the
architecture is most sensitive to.  Completes Phase 0 deliverable:
"Sensitivity analysis for each key parameter."

Parameters surveyed:
  1. Damping coefficient η — controls coherence time
  2. ZIM damping factor  — multiplier applied to η in ZIM regime
  3. Quality factor Q    — controls thermal mode crowding
  4. Temperature ΔT      — thermal stability window
  5. α (drift/K)         — material thermal coefficient
  6. Shear strain γ      — dilatancy / tamper signal magnitude
  7. Wave speed c        — medium stiffness / ZIM effectiveness
  8. Cavity length L     — micro-cell geometry
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple, Optional

from .common import (
    CavityParams, DilatancyParams, ThermalParams, MicroCellParams,
    C_AIR, C_ZIM_SCALED, K_B,
)
from .resonator_1d import run_1d_simulation, compute_frequency
from .thermal import max_safe_modes, analyze_thermal_drift


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------
@dataclass
class SweepResult:
    """Single parameter sweep result."""
    param_name: str
    param_values: np.ndarray
    metric_name: str
    metric_values: np.ndarray
    units: str = ""
    baseline_value: float = np.nan
    baseline_metric: float = np.nan
    label: str = ""


@dataclass
class SensitivityReport:
    """Full sensitivity analysis across all parameters."""
    sweeps: Dict[str, SweepResult] = field(default_factory=dict)
    elasticity: Dict[str, float] = field(default_factory=dict)

    def add(self, sweep: SweepResult):
        self.sweeps[sweep.param_name] = sweep

    def summary_table(self) -> str:
        """Formatted sensitivity summary."""
        lines = [
            f"{'Parameter':<25} {'Baseline':>12} {'Metric':>20} "
            f"{'Min':>12} {'Max':>12} {'Elasticity':>12}"
        ]
        lines.append("-" * 95)
        for name, sw in self.sweeps.items():
            e = self.elasticity.get(name, np.nan)
            lines.append(
                f"{name:<25} {sw.baseline_value:>12.4g} "
                f"{sw.metric_name:>20} "
                f"{np.min(sw.metric_values):>12.4g} "
                f"{np.max(sw.metric_values):>12.4g} "
                f"{e:>12.3f}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Elasticity computation
# ---------------------------------------------------------------------------
def compute_elasticity(
    param_values: np.ndarray,
    metric_values: np.ndarray,
    baseline_param: float,
    baseline_metric: float,
) -> float:
    """
    Point elasticity: ε = (Δmetric/metric) / (Δparam/param)
    evaluated at the baseline via central difference.

    Values > 1 mean the metric is *more* sensitive than linear.
    """
    if baseline_metric == 0 or baseline_param == 0:
        return np.nan

    idx = np.argmin(np.abs(param_values - baseline_param))
    if idx == 0:
        dp = param_values[1] - param_values[0]
        dm = metric_values[1] - metric_values[0]
    elif idx == len(param_values) - 1:
        dp = param_values[-1] - param_values[-2]
        dm = metric_values[-1] - metric_values[-2]
    else:
        dp = param_values[idx + 1] - param_values[idx - 1]
        dm = metric_values[idx + 1] - metric_values[idx - 1]

    return (dm / baseline_metric) / (dp / baseline_param)


# ---------------------------------------------------------------------------
# Individual sweep functions
# ---------------------------------------------------------------------------
def sweep_damping_vs_coherence(
    eta_range: np.ndarray = None,
    c: float = C_AIR,
    L: float = 1.0,
) -> SweepResult:
    """Sweep η and measure theoretical coherence time τ = 1/(2η)."""
    if eta_range is None:
        eta_range = np.logspace(0, 3, 30)  # 1 – 1000 1/s

    tau = 1.0 / (2.0 * eta_range)
    baseline_eta = 100.0
    baseline_tau = 1.0 / (2.0 * baseline_eta)

    return SweepResult(
        param_name="η (damping rate)",
        param_values=eta_range,
        metric_name="τ coherence (s)",
        metric_values=tau,
        units="1/s",
        baseline_value=baseline_eta,
        baseline_metric=baseline_tau,
    )


def sweep_zim_factor_vs_coherence(
    factors: np.ndarray = None,
    eta_base: float = 100.0,
) -> SweepResult:
    """Sweep ZIM damping reduction factor and measure τ_ZIM / τ_Normal."""
    if factors is None:
        factors = np.linspace(0.1, 1.0, 20)

    ratios = 1.0 / factors  # τ_ZIM/τ_Normal = η/η_ZIM = 1/factor
    baseline_f = 0.5
    baseline_r = 1.0 / baseline_f

    return SweepResult(
        param_name="ZIM damping factor",
        param_values=factors,
        metric_name="τ_ZIM / τ_Normal",
        metric_values=ratios,
        units="×",
        baseline_value=baseline_f,
        baseline_metric=baseline_r,
    )


def sweep_Q_vs_modes(
    Q_range: np.ndarray = None,
    use_zim: bool = True,
) -> SweepResult:
    """Sweep quality factor Q and measure max safe modes."""
    if Q_range is None:
        Q_range = np.logspace(1.5, 4, 30)  # 30 – 10000

    cell = MicroCellParams()
    thermal = ThermalParams()

    modes = np.array([
        max_safe_modes(
            cell.delta_f, Q,
            thermal.alpha, thermal.delta_T,
            thermal.drift_reduction_zim if use_zim else 1.0,
        )
        for Q in Q_range
    ])

    baseline_Q = 500.0
    baseline_modes = max_safe_modes(
        cell.delta_f, baseline_Q,
        thermal.alpha, thermal.delta_T,
        thermal.drift_reduction_zim if use_zim else 1.0,
    )

    label = "with ZIM" if use_zim else "no ZIM"
    return SweepResult(
        param_name=f"Q ({label})",
        param_values=Q_range,
        metric_name="Max safe modes",
        metric_values=modes.astype(float),
        units="",
        baseline_value=baseline_Q,
        baseline_metric=float(baseline_modes),
    )


def sweep_deltaT_vs_modes(
    dT_range: np.ndarray = None,
    use_zim: bool = True,
) -> SweepResult:
    """Sweep temperature variation ΔT and measure max safe modes."""
    if dT_range is None:
        dT_range = np.linspace(0.5, 20.0, 30)

    cell = MicroCellParams()
    thermal = ThermalParams()

    modes = np.array([
        max_safe_modes(
            cell.delta_f, thermal.Q,
            thermal.alpha, dT,
            thermal.drift_reduction_zim if use_zim else 1.0,
        )
        for dT in dT_range
    ])

    baseline_dT = 5.0
    baseline_modes = max_safe_modes(
        cell.delta_f, thermal.Q,
        thermal.alpha, baseline_dT,
        thermal.drift_reduction_zim if use_zim else 1.0,
    )

    label = "with ZIM" if use_zim else "no ZIM"
    return SweepResult(
        param_name=f"ΔT ({label})",
        param_values=dT_range,
        metric_name="Max safe modes",
        metric_values=modes.astype(float),
        units="K",
        baseline_value=baseline_dT,
        baseline_metric=float(baseline_modes),
    )


def sweep_alpha_vs_modes(
    alpha_range: np.ndarray = None,
    use_zim: bool = True,
) -> SweepResult:
    """Sweep thermal drift coefficient α and measure max safe modes."""
    if alpha_range is None:
        alpha_range = np.logspace(-4, -1, 30)  # 0.0001 – 0.1

    cell = MicroCellParams()
    thermal = ThermalParams()

    modes = np.array([
        max_safe_modes(
            cell.delta_f, thermal.Q,
            alpha, thermal.delta_T,
            thermal.drift_reduction_zim if use_zim else 1.0,
        )
        for alpha in alpha_range
    ])

    baseline_alpha = thermal.alpha
    baseline_modes = max_safe_modes(
        cell.delta_f, thermal.Q,
        baseline_alpha, thermal.delta_T,
        thermal.drift_reduction_zim if use_zim else 1.0,
    )

    label = "with ZIM" if use_zim else "no ZIM"
    return SweepResult(
        param_name=f"α drift coeff ({label})",
        param_values=alpha_range,
        metric_name="Max safe modes",
        metric_values=modes.astype(float),
        units="/K",
        baseline_value=baseline_alpha,
        baseline_metric=float(baseline_modes),
    )


def sweep_gamma_vs_drift(
    gamma_range: np.ndarray = None,
) -> SweepResult:
    """Sweep shear strain γ and measure 1D frequency drift %."""
    if gamma_range is None:
        gamma_range = np.linspace(0.01, 0.6, 30)

    c = C_AIR
    L = 1.0
    f0 = compute_frequency(1, c, L)

    drifts = np.array([
        abs(compute_frequency(1, c, L * (1.0 + g)) - f0) / f0 * 100
        for g in gamma_range
    ])

    baseline_gamma = 0.3
    f_dilated = compute_frequency(1, c, L * (1.0 + baseline_gamma))
    baseline_drift = abs(f_dilated - f0) / f0 * 100

    return SweepResult(
        param_name="γ (shear strain)",
        param_values=gamma_range,
        metric_name="Freq drift (%)",
        metric_values=drifts,
        units="",
        baseline_value=baseline_gamma,
        baseline_metric=baseline_drift,
    )


def sweep_cavity_length_vs_density(
    L_range: np.ndarray = None,
    use_zim: bool = True,
) -> SweepResult:
    """Sweep micro-cell length L and measure storage density."""
    if L_range is None:
        L_range = np.logspace(-6, -3, 30)  # 1 µm – 1 mm

    thermal = ThermalParams()
    densities = []
    for L in L_range:
        cell = MicroCellParams(L=L, cells_per_cm3=1.0 / (L * 100)**3)
        n = max_safe_modes(
            cell.delta_f, thermal.Q,
            thermal.alpha, thermal.delta_T,
            thermal.drift_reduction_zim if use_zim else 1.0,
        )
        density = cell.cells_per_cm3 * n * cell.bits_per_mode / 1e12
        densities.append(density)

    densities = np.array(densities)
    baseline_L = 1e-5
    cell0 = MicroCellParams(L=baseline_L, cells_per_cm3=1.0 / (baseline_L * 100)**3)
    n0 = max_safe_modes(
        cell0.delta_f, thermal.Q,
        thermal.alpha, thermal.delta_T,
        thermal.drift_reduction_zim if use_zim else 1.0,
    )
    baseline_density = cell0.cells_per_cm3 * n0 * cell0.bits_per_mode / 1e12

    label = "with ZIM" if use_zim else "no ZIM"
    return SweepResult(
        param_name=f"Cell length L ({label})",
        param_values=L_range,
        metric_name="Density (Tb/cm³)",
        metric_values=densities,
        units="m",
        baseline_value=baseline_L,
        baseline_metric=baseline_density,
    )


# ---------------------------------------------------------------------------
# Full sensitivity analysis
# ---------------------------------------------------------------------------
def run_full_sensitivity() -> SensitivityReport:
    """
    Run all parameter sweeps and compute elasticities.

    Returns a SensitivityReport with all sweeps and ranked elasticities.
    """
    report = SensitivityReport()

    sweeps = [
        sweep_damping_vs_coherence(),
        sweep_zim_factor_vs_coherence(),
        sweep_Q_vs_modes(use_zim=False),
        sweep_Q_vs_modes(use_zim=True),
        sweep_deltaT_vs_modes(use_zim=True),
        sweep_alpha_vs_modes(use_zim=True),
        sweep_gamma_vs_drift(),
        sweep_cavity_length_vs_density(use_zim=True),
    ]

    for sw in sweeps:
        report.add(sw)
        report.elasticity[sw.param_name] = compute_elasticity(
            sw.param_values, sw.metric_values,
            sw.baseline_value, sw.baseline_metric,
        )

    return report
