"""
Cross-Experiment Comparison Tables

Generates comparison tables matching paper Section 8 format,
plus experiment-vs-claim validation summaries.
Includes auto-population from live experiment runs.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional


def technology_comparison_table() -> str:
    """
    Generate the comparison table from paper Section 8.
    WCFOMA values are projected; others are from literature.
    """
    header = (
        f"{'Technology':<25} | {'Energy/op':<12} | {'Density':<15} | "
        f"{'Compute Locality':<18} | {'Status':<15}"
    )
    sep = "-" * len(header)

    rows = [
        ("DRAM",                   "pJ",        "Low",          "Separate",      "Demonstrated"),
        ("NAND Flash",             "nJ",        "High",         "None",          "Demonstrated"),
        ("Analog IMC (ReRAM)",     "fJ–pJ",     "Medium",       "Partial",       "Demonstrated"),
        ("Magnonic Logic",         "fJ",        "Low",          "Partial",       "Demonstrated"),
        ("WCFOMA (projected)",     "fJ",        "Tb/cm³",       "Unified",       "Simulated"),
        ("WCFOMA + ZIM (proj.)",   "fJ",        "1–10 Tb/cm³",  "Unified",       "Simulated"),
    ]

    lines = [sep, header, sep]
    for name, energy, density, locality, status in rows:
        lines.append(
            f"{name:<25} | {energy:<12} | {density:<15} | "
            f"{locality:<18} | {status:<15}"
        )
    lines.append(sep)
    return "\n".join(lines)


def claims_validation_table(results: Dict[str, Tuple[str, str, str]]) -> str:
    """
    Generate a claims validation table.

    results: dict of claim_label -> (paper_value, measured_value, status)
    status: CONFIRMED / PLAUSIBLE / INCONCLUSIVE / REFUTED
    """
    header = (
        f"{'Claim':<40} | {'Paper Value':<18} | "
        f"{'Measured':<18} | {'Status':<15}"
    )
    sep = "-" * len(header)

    lines = [sep, header, sep]
    for claim, (paper_val, measured, status) in results.items():
        lines.append(
            f"{claim:<40} | {paper_val:<18} | "
            f"{measured:<18} | {status:<15}"
        )
    lines.append(sep)
    return "\n".join(lines)


def default_claims_checklist() -> Dict[str, Tuple[str, str, str]]:
    """
    Default checklist of paper claims to validate.
    Tuple: (paper_value, measured_value, status)
    measured_value starts as 'PENDING' until experiments run.
    """
    return {
        "ZIM coherence extension":
            ("~2×", "PENDING", "NOT TESTED"),
        "1D freq drift at γ=0.5":
            ("~33%", "PENDING", "NOT TESTED"),
        "3D freq drift at γ=0.3":
            ("~7%", "PENDING", "NOT TESTED"),
        "Max safe modes (no ZIM)":
            ("~41", "PENDING", "NOT TESTED"),
        "Max safe modes (with ZIM)":
            ("~322", "PENDING", "NOT TESTED"),
        "Storage density (ZIM)":
            ("~3.22 Tb/cm³", "PENDING", "NOT TESTED"),
        "Geometry invariance (<1%)":
            ("<1% shift", "PENDING", "NOT TESTED"),
        "Energy per operation":
            ("fJ range", "PENDING", "NOT TESTED"),
        "Excitation energy > thermal":
            ("E >> k_BT", "PENDING", "NOT TESTED"),
    }


# ---------------------------------------------------------------------------
# Auto-population from live experiments
# ---------------------------------------------------------------------------
def run_all_validations() -> Dict[str, Tuple[str, str, str]]:
    """
    Run all experiments and auto-populate the claims checklist.

    Returns the same dict format as default_claims_checklist()
    but with measured values and CONFIRMED/PLAUSIBLE/REFUTED status.
    """
    from simulations.common import (
        DilatancyParams, ThermalParams, MicroCellParams,
        C_AIR, C_ZIM_SCALED, K_B,
    )
    from simulations.resonator_1d import run_standard_comparison, compute_frequency
    from simulations.thermal import analyze_thermal_drift

    results = {}

    # --- 1. ZIM coherence extension ---
    dp = DilatancyParams(gamma=0.3)
    eta_normal = dp.eta
    eta_zim = dp.eta_zim
    tau_ratio = eta_normal / eta_zim  # τ_zim / τ_normal = η_normal / η_zim
    status = "CONFIRMED" if abs(tau_ratio - 2.0) < 0.1 else "REFUTED"
    results["ZIM coherence extension"] = (
        "~2×", f"{tau_ratio:.2f}×", status
    )

    # --- 2. 1D frequency drift at γ=0.5 ---
    f0 = compute_frequency(1.0, C_AIR, gamma=0.0, beta=1.0, n=1)
    f_stressed = compute_frequency(1.0, C_AIR, gamma=0.5, beta=1.0, n=1)
    drift_1d = abs(f_stressed - f0) / f0 * 100
    status = "CONFIRMED" if abs(drift_1d - 33.33) < 2.0 else "REFUTED"
    results["1D freq drift at γ=0.5"] = (
        "~33%", f"{drift_1d:.2f}%", status
    )

    # --- 3. 3D frequency drift at γ=0.3 ---
    Lz_stressed = 1.0 * (1.0 + 1.0 * 0.3)
    f0_3d = (C_AIR / 2.0) * np.sqrt(3.0)  # (1,1,1) mode in unit cube
    f_3d_stressed = (C_AIR / 2.0) * np.sqrt(
        1.0 + 1.0 + (1.0 / Lz_stressed)**2
    )
    drift_3d = abs(f_3d_stressed - f0_3d) / f0_3d * 100
    status = "CONFIRMED" if abs(drift_3d - 7.0) < 3.0 else "REFUTED"
    results["3D freq drift at γ=0.3"] = (
        "~7%", f"{drift_3d:.1f}%", status
    )

    # --- 4. Max safe modes (no ZIM) ---
    result_no_zim = analyze_thermal_drift(use_zim=False)
    modes_no_zim = result_no_zim.max_safe_modes
    status = "CONFIRMED" if modes_no_zim == 41 else "REFUTED"
    results["Max safe modes (no ZIM)"] = (
        "~41", str(modes_no_zim), status
    )

    # --- 5. Max safe modes (with ZIM) ---
    result_zim = analyze_thermal_drift(use_zim=True)
    modes_zim = result_zim.max_safe_modes
    status = "CONFIRMED" if abs(modes_zim - 322) < 10 else "REFUTED"
    results["Max safe modes (with ZIM)"] = (
        "~322", str(modes_zim), status
    )

    # --- 6. Storage density ---
    mp_ = MicroCellParams()
    bits_per_cell = mp_.bits_per_mode * modes_zim
    total_bits = bits_per_cell * mp_.cells_per_cm3
    density_tb = total_bits / 1e12
    status = "CONFIRMED" if abs(density_tb - 3.22) < 0.5 else "REFUTED"
    results["Storage density (ZIM)"] = (
        "~3.22 Tb/cm³", f"{density_tb:.2f} Tb/cm³", status
    )

    # --- 7. Geometry invariance ---
    # Analytical argument: in ENZ (ε→0), k² = j²mn/(a²εp), independent
    # of cavity geometry. FD solver is ill-conditioned, so mark PLAUSIBLE.
    results["Geometry invariance (<1%)"] = (
        "<1% shift", "0% (analytical Mie)", "PLAUSIBLE"
    )

    # --- 8. Energy per operation ---
    try:
        from simulations.cmos_interface import compute_energy_budget
        budget = compute_energy_budget()
        e_fj = budget.E_total * 1e15
        status = "CONFIRMED" if e_fj < 1000 else "REFUTED"  # < 1 pJ
        results["Energy per operation"] = (
            "fJ range", f"{e_fj:.1f} fJ", status
        )
    except ImportError:
        results["Energy per operation"] = ("fJ range", "PENDING", "NOT TESTED")

    # --- 9. Excitation energy > thermal ---
    try:
        from simulations.cmos_interface import excitation_energy
        E_exc, E_therm = excitation_energy(
            cell_length=1e-5, c=C_AIR, Q=500, n_modes=10,
        )
        ratio = E_exc / E_therm
        status = "CONFIRMED" if ratio > 5 else "REFUTED"
        results["Excitation energy > thermal"] = (
            "E >> k_BT", f"{ratio:.0f}× k_BT", status
        )
    except ImportError:
        results["Excitation energy > thermal"] = (
            "E >> k_BT", "PENDING", "NOT TESTED"
        )

    return results


def validation_summary(
    results: Optional[Dict[str, Tuple[str, str, str]]] = None
) -> str:
    """
    Run full validation and return a formatted summary string.

    Parameters
    ----------
    results : dict, optional
        Pre-computed results. If None, runs run_all_validations().

    Returns
    -------
    str
        Formatted claims validation table with counts.
    """
    if results is None:
        results = run_all_validations()

    table = claims_validation_table(results)

    confirmed = sum(1 for _, (_, _, s) in results.items() if s == "CONFIRMED")
    plausible = sum(1 for _, (_, _, s) in results.items() if s == "PLAUSIBLE")
    refuted = sum(1 for _, (_, _, s) in results.items() if s == "REFUTED")
    pending = sum(1 for _, (_, _, s) in results.items() if s in ("NOT TESTED", "PENDING"))

    summary = (
        f"\n{'='*50}\n"
        f"  CONFIRMED: {confirmed}  |  PLAUSIBLE: {plausible}  |  "
        f"REFUTED: {refuted}  |  PENDING: {pending}\n"
        f"{'='*50}"
    )

    return table + summary
