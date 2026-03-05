"""
Mode Crowding and Thermal Drift Analysis for Micro-Scale WCFOMA Cells

Implements the simulations from the WCFOMA Addendum (February 10, 2026)
on mode distinguishability under thermal perturbation.

Model:
  - Mode frequencies:   f_n = n · Δf,  where Δf = v / (2L)
  - Linewidth:          δf_n = f_n / Q
  - Thermal drift:      max_drift_n = f_n · α · ΔT / reduction_factor
  - Distinguishability:  2 · max_drift_n < Δf - δf_n

Key findings:
  - Without ZIM: ~41 safe modes (0.41 Tb/cm³ at 10 bits/mode)
  - With ZIM (20× drift reduction): ~322 safe modes (3.22 Tb/cm³)
"""

import numpy as np
from dataclasses import dataclass
from typing import Tuple

from .common import ThermalParams, MicroCellParams


@dataclass
class ThermalAnalysisResult:
    """Result container for thermal drift analysis."""
    max_safe_modes: int
    density_tb_per_cm3: float
    delta_f: float                # Mode spacing (Hz)
    Q: float
    alpha: float                  # Drift coefficient (/K)
    delta_T: float                # Temperature variation (K)
    drift_reduction: float        # ZIM reduction factor
    bits_per_mode: int
    cells_per_cm3: float
    label: str = ""

    # Per-mode breakdown for plotting
    mode_numbers: np.ndarray = None
    frequencies: np.ndarray = None
    linewidths: np.ndarray = None
    drift_ranges: np.ndarray = None
    margins: np.ndarray = None


def max_safe_modes(
    delta_f: float,
    Q: float,
    alpha: float,
    delta_T: float,
    drift_reduction: float = 1.0,
) -> int:
    """
    Calculate maximum distinguishable modes under thermal drift.

    Parameters
    ----------
    delta_f : float
        Mode spacing (Hz).
    Q : float
        Quality factor.
    alpha : float
        Fractional drift per Kelvin.
    delta_T : float
        Temperature variation (K).
    drift_reduction : float
        Factor by which ZIM reduces drift.

    Returns
    -------
    int : Maximum number of safe modes.
    """
    n = 1
    while True:
        f_n = n * delta_f
        linewidth = f_n / Q
        max_drift_n = f_n * alpha * delta_T / drift_reduction
        if 2.0 * max_drift_n >= delta_f - linewidth:
            break
        n += 1
    return n - 1


def analyze_thermal_drift(
    cell: MicroCellParams = None,
    thermal: ThermalParams = None,
    use_zim: bool = False,
    label: str = "",
) -> ThermalAnalysisResult:
    """
    Full thermal drift analysis with per-mode breakdown.

    Parameters
    ----------
    cell : MicroCellParams
        Cell geometry and encoding parameters.
    thermal : ThermalParams
        Thermal environment parameters.
    use_zim : bool
        Whether to apply ZIM drift reduction.
    label : str
        Run identifier.

    Returns
    -------
    ThermalAnalysisResult
    """
    if cell is None:
        cell = MicroCellParams()
    if thermal is None:
        thermal = ThermalParams()

    drift_reduction = thermal.drift_reduction_zim if use_zim else 1.0
    delta_f = cell.delta_f

    n_max = max_safe_modes(
        delta_f, thermal.Q, thermal.alpha, thermal.delta_T, drift_reduction
    )

    density = (cell.cells_per_cm3 * n_max * cell.bits_per_mode) / 1e12

    # Per-mode breakdown
    ns = np.arange(1, n_max + 20)  # Include some modes beyond safe limit
    fs = ns * delta_f
    lws = fs / thermal.Q
    drifts = 2.0 * fs * thermal.alpha * thermal.delta_T / drift_reduction
    margins = delta_f - lws - drifts

    return ThermalAnalysisResult(
        max_safe_modes=n_max,
        density_tb_per_cm3=density,
        delta_f=delta_f,
        Q=thermal.Q,
        alpha=thermal.alpha,
        delta_T=thermal.delta_T,
        drift_reduction=drift_reduction,
        bits_per_mode=cell.bits_per_mode,
        cells_per_cm3=cell.cells_per_cm3,
        label=label,
        mode_numbers=ns,
        frequencies=fs,
        linewidths=lws,
        drift_ranges=drifts,
        margins=margins,
    )


def run_standard_thermal_comparison(
    cell: MicroCellParams = None,
    thermal: ThermalParams = None,
) -> dict:
    """
    Run standard comparison: normal vs ZIM under thermal drift.
    Returns dict of label -> ThermalAnalysisResult.
    """
    return {
        "Without ZIM": analyze_thermal_drift(
            cell, thermal, use_zim=False, label="Without ZIM"),
        "With ZIM": analyze_thermal_drift(
            cell, thermal, use_zim=True, label="With ZIM"),
    }


def sensitivity_sweep(
    param_name: str,
    param_values: np.ndarray,
    cell: MicroCellParams = None,
    thermal: ThermalParams = None,
    use_zim: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Sweep a parameter and return (param_values, modes_array, density_array).

    param_name must be one of: 'Q', 'alpha', 'delta_T', 'drift_reduction_zim',
                                'L', 'bits_per_mode'.
    """
    if cell is None:
        cell = MicroCellParams()
    if thermal is None:
        thermal = ThermalParams()

    modes_arr = np.zeros_like(param_values, dtype=int)
    density_arr = np.zeros_like(param_values, dtype=float)

    for i, val in enumerate(param_values):
        # Clone params and override
        c = MicroCellParams(L=cell.L, c=cell.c,
                            bits_per_mode=cell.bits_per_mode,
                            cells_per_cm3=cell.cells_per_cm3)
        t = ThermalParams(alpha=thermal.alpha, delta_T=thermal.delta_T,
                          Q=thermal.Q,
                          drift_reduction_zim=thermal.drift_reduction_zim)

        if param_name == 'Q':
            t.Q = val
        elif param_name == 'alpha':
            t.alpha = val
        elif param_name == 'delta_T':
            t.delta_T = val
        elif param_name == 'drift_reduction_zim':
            t.drift_reduction_zim = val
        elif param_name == 'L':
            c.L = val
            c.cells_per_cm3 = 1e-6 / val**3
        elif param_name == 'bits_per_mode':
            c.bits_per_mode = int(val)
        else:
            raise ValueError(f"Unknown parameter: {param_name}")

        result = analyze_thermal_drift(c, t, use_zim=use_zim)
        modes_arr[i] = result.max_safe_modes
        density_arr[i] = result.density_tb_per_cm3

    return param_values, modes_arr, density_arr
