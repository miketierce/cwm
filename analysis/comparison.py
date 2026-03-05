"""
Cross-Experiment Comparison Tables

Generates comparison tables matching paper Section 8 format,
plus experiment-vs-claim validation summaries.
"""

import numpy as np
from typing import Dict, List, Tuple


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
