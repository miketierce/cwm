#!/usr/bin/env python3
"""Preliminary quantum-transition bounds from existing CWM data.

This analysis does not search for a quantum witness. It tests how far the
saved classical data can already constrain QT-0B, QT-0C, QT-1B, and QT-1C.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "results"
H = 6.62607015e-34
K_B = 1.380649e-23


def _json_number(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_number(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_number(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _summary(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=float)
    return {
        "count": int(array.size),
        "min": float(np.min(array)),
        "median": float(np.median(array)),
        "mean": float(np.mean(array)),
        "max": float(np.max(array)),
    }


def _fit_harmonics(phases_deg: list[float], energy: list[float]) -> dict[str, float]:
    theta = np.deg2rad(np.asarray(phases_deg, dtype=float))
    values = np.asarray(energy, dtype=float)
    first = np.column_stack([np.ones_like(theta), np.cos(theta), np.sin(theta)])
    second = np.column_stack(
        [first, np.cos(2.0 * theta), np.sin(2.0 * theta)]
    )

    beta_first = np.linalg.lstsq(first, values, rcond=None)[0]
    beta_second = np.linalg.lstsq(second, values, rcond=None)[0]
    fit_first = first @ beta_first
    fit_second = second @ beta_second
    total = float(np.sum((values - np.mean(values)) ** 2))
    residual_first = float(np.sum((values - fit_first) ** 2))
    residual_second = float(np.sum((values - fit_second) ** 2))

    leave_one_out = np.empty_like(values)
    for index in range(values.size):
        keep = np.arange(values.size) != index
        beta = np.linalg.lstsq(first[keep], values[keep], rcond=None)[0]
        leave_one_out[index] = first[index] @ beta

    cv_residual = float(np.sum((values - leave_one_out) ** 2))
    first_amplitude = float(np.hypot(beta_first[1], beta_first[2]))
    second_amplitude = float(np.hypot(beta_second[3], beta_second[4]))
    span = float(np.ptp(values))

    return {
        "r2_first_harmonic": 1.0 - residual_first / total if total else 1.0,
        "r2_first_harmonic_loo": 1.0 - cv_residual / total if total else 1.0,
        "r2_second_harmonic": 1.0 - residual_second / total if total else 1.0,
        "delta_r2_second_harmonic": (
            residual_first - residual_second
        ) / total if total else 0.0,
        "first_harmonic_modulation_fraction": (
            first_amplitude / abs(beta_first[0]) if beta_first[0] else math.inf
        ),
        "second_to_first_harmonic_amplitude": (
            second_amplitude / first_amplitude if first_amplitude else math.inf
        ),
        "normalized_rmse": (
            math.sqrt(residual_first / values.size) / span if span else 0.0
        ),
    }


def analyze_phase_interference() -> dict[str, Any]:
    source_files = sorted((DATA / "phase_interference").glob("phase_interference_*.json"))
    sweeps: list[dict[str, Any]] = []
    for source in source_files:
        payload = json.loads(source.read_text())
        for index, scan in enumerate(payload.get("sectionA_scan", [])):
            phases = scan.get("phases", [])
            energy = scan.get("energy", [])
            if len(phases) != len(energy) or len(phases) < 12:
                continue
            fit = _fit_harmonics(phases, energy)
            sweeps.append(
                {
                    "source": str(source.relative_to(ROOT)),
                    "scan_index": index,
                    "frequency_hz": float(scan["freq"]),
                    "n_phase_points": len(phases),
                    "stored_cos_fit_r": float(scan.get("cos_fit_r", math.nan)),
                    **fit,
                }
            )

    train_r2 = [row["r2_first_harmonic"] for row in sweeps]
    cv_r2 = [row["r2_first_harmonic_loo"] for row in sweeps]
    delta_r2 = [row["delta_r2_second_harmonic"] for row in sweeps]
    harmonic_ratio = [row["second_to_first_harmonic_amplitude"] for row in sweeps]
    return {
        "roadmap_gate": "QT-0B precursor",
        "source_file_count": len(source_files),
        "sweep_count": len(sweeps),
        "first_harmonic_r2": _summary(train_r2),
        "first_harmonic_leave_one_out_r2": _summary(cv_r2),
        "fraction_sweeps_cv_r2_ge_0_8": float(np.mean(np.asarray(cv_r2) >= 0.8)),
        "second_harmonic_delta_r2": _summary(delta_r2),
        "second_to_first_harmonic_amplitude": _summary(harmonic_ratio),
        "worst_first_harmonic_sweep": min(
            sweeps, key=lambda row: row["r2_first_harmonic_loo"]
        ),
        "interpretation": (
            "A first-harmonic phase model is the classical two-path interference null. "
            "Fit quality constrains that null but does not close it uniformly and cannot "
            "establish a quantum witness."
        ),
        "limitation": (
            "Saved files contain phase-energy grids and spectra, not raw phase-referenced "
            "time-domain voltage for a complete QT-0B stochastic model."
        ),
        "sweeps": sweeps,
    }


def analyze_intermodulation() -> dict[str, Any]:
    source_files = sorted((DATA / "intermodulation").glob("*.json"))
    snr_records: list[float] = []
    standardized_records: list[dict[str, Any]] = []
    experiment_decisions: list[dict[str, Any]] = []

    for source in source_files:
        payload = json.loads(source.read_text())
        experiment_decisions.append(
            {
                "source": str(source.relative_to(ROOT)),
                "experiment": payload.get("experiment"),
                "gate_decision": payload.get("gate_decision"),
            }
        )
        for pair_index, pair in enumerate(payload.get("pairs", [])):
            relay_products = pair.get("relay_on", {}).get("im_products", {})
            for name, product in relay_products.items():
                if "snr_vs_noise" in product:
                    snr_records.append(float(product["snr_vs_noise"]))

            for name, product in pair.get("im_bins", {}).items():
                sigma_key = next(
                    (
                        key
                        for key in ("sigma_vs_awg", "sigma_vs_f1only")
                        if key in product
                    ),
                    None,
                )
                if sigma_key is None:
                    continue
                standardized_records.append(
                    {
                        "source": str(source.relative_to(ROOT)),
                        "pair_index": pair_index,
                        "product": name,
                        "sigma": float(product[sigma_key]),
                        "sigma_reference": sigma_key,
                    }
                )

    sigma = np.asarray([row["sigma"] for row in standardized_records], dtype=float)
    positive_sigma = sigma[sigma > 0]
    reference_counts = {
        reference: sum(
            row["sigma_reference"] == reference for row in standardized_records
        )
        for reference in sorted(
            {row["sigma_reference"] for row in standardized_records}
        )
    }
    return {
        "roadmap_gates": ["QT-0B precursor", "QT-1C precursor"],
        "source_file_count": len(source_files),
        "noise_ratio_record_count": len(snr_records),
        "noise_ratio_max": float(max(snr_records)) if snr_records else None,
        "standardized_record_count": len(standardized_records),
        "max_positive_sigma": float(np.max(positive_sigma)) if positive_sigma.size else 0.0,
        "max_absolute_sigma": float(np.max(np.abs(sigma))) if sigma.size else 0.0,
        "positive_products_ge_3_sigma": int(np.sum(sigma >= 3.0)),
        "absolute_products_ge_3_sigma": int(np.sum(np.abs(sigma) >= 3.0)),
        "sigma_reference_counts": reference_counts,
        "interpretation": (
            "No >=3 sigma intermodulation product supports the linear-substrate null at "
            "the tested drive settings."
        ),
        "limitation": (
            "The captures do not provide a calibrated displacement sweep, so they cannot "
            "identify a Duffing coefficient or single-quantum Kerr rate K."
        ),
        "experiment_decisions": experiment_decisions,
        "standardized_records": standardized_records,
    }


def _rank_metrics(matrix: np.ndarray) -> dict[str, Any]:
    singular = np.linalg.svd(matrix, compute_uv=False)
    power = singular**2
    probability = power / np.sum(power)
    entropy_rank = float(np.exp(-np.sum(probability * np.log(probability))))
    return {
        "shape": list(matrix.shape),
        "singular_values": singular.tolist(),
        "algebraic_rank": int(np.linalg.matrix_rank(matrix)),
        "stable_rank": float(np.sum(power) / power[0]),
        "entropy_effective_rank": entropy_rank,
        "condition_number": float(singular[0] / singular[-1]),
    }


def analyze_h_matrix() -> dict[str, Any]:
    source = DATA / "h_matrix" / "l1_h_matrix_20260602_220004.npz"
    with np.load(source, allow_pickle=False) as payload:
        raw = np.asarray(payload["H_raw"], dtype=float)
        normalized = np.asarray(payload["H_norm"], dtype=float)

    gain_normalized = raw / np.linalg.norm(raw, axis=0, keepdims=True)
    correlation = float(np.corrcoef(raw.T)[0, 1])
    return {
        "roadmap_gate": "QT-1B precursor",
        "source": str(source.relative_to(ROOT)),
        "acquisition_channel_ceiling": raw.shape[1],
        "raw": _rank_metrics(raw),
        "stored_normalized": _rank_metrics(normalized),
        "column_gain_normalized": _rank_metrics(gain_normalized),
        "receiver_amplitude_correlation": correlation,
        "interpretation": (
            "The matrix is algebraically rank 2 but has only two simultaneous receiver "
            "channels; existing data cannot test the roadmap's rank-8 gate."
        ),
    }


def _thermal_row(frequency_hz: float, q: float, temperature_k: float) -> dict[str, float]:
    exponent = H * frequency_hz / (K_B * temperature_k)
    occupation = 1.0 / math.expm1(exponent)
    linewidth_hz = frequency_hz / q
    return {
        "frequency_hz": frequency_hz,
        "q": q,
        "temperature_k": temperature_k,
        "n_th": occupation,
        "gamma_m_over_2pi_hz": linewidth_hz,
        "gamma_up_over_2pi_hz": linewidth_hz * occupation,
        "gamma_sigma_over_2pi_hz": linewidth_hz * (2.0 * occupation + 1.0),
        "qf_screen_ratio": q * frequency_hz / (K_B * temperature_k / H),
    }


def analyze_measured_q() -> dict[str, Any]:
    source = DATA / "temporal" / "e10_qfactor_memory_20260603_200902.json"
    payload = json.loads(source.read_text())
    rows = []
    for mode in payload["per_mode"].values():
        frequency_hz = float(mode["peak_frequency_hz"])
        q = float(mode["Q"])
        rows.append(
            {
                "source_frequency_hz": float(mode["frequency_hz"]),
                **_thermal_row(frequency_hz, q, 300.0),
            }
        )

    q_values = [row["q"] for row in rows]
    qf_ratios = [row["qf_screen_ratio"] for row in rows]
    gamma_up = [row["gamma_up_over_2pi_hz"] for row in rows]
    return {
        "roadmap_gate": "QT-0C measured macro anchor",
        "source": str(source.relative_to(ROOT)),
        "loaded_q": _summary(q_values),
        "qf_screen_ratio": _summary(qf_ratios),
        "gamma_up_over_2pi_hz": _summary(gamma_up),
        "best_measured_mode": max(rows, key=lambda row: row["qf_screen_ratio"]),
        "interpretation": (
            "Loaded macro modes are useful classical controls but remain many orders of "
            "magnitude below the bare room-temperature Qf screen."
        ),
        "modes": rows,
    }


def simulate_rate_envelope() -> dict[str, Any]:
    rows = []
    for temperature_k in (280.0, 300.0, 320.0):
        for frequency_hz in (3.5e6, 10e6, 35e6):
            for q in (1e4, 1e5, 1e6):
                thermal = _thermal_row(frequency_hz, q, temperature_k)
                required_coupling = {}
                for gamma_q_hz in (1e3, 1e4, 1e5):
                    required_coupling[str(int(gamma_q_hz))] = 0.5 * math.sqrt(
                        gamma_q_hz * thermal["gamma_sigma_over_2pi_hz"]
                    )
                rows.append(
                    {
                        **thermal,
                        "required_g_over_2pi_hz_for_cq_1": required_coupling,
                    }
                )

    return {
        "roadmap_gate": "QT-0C simulation",
        "model": "Bose-Einstein occupation plus frozen roadmap Cq convention",
        "assumptions": {
            "frequencies_hz": [3.5e6, 10e6, 35e6],
            "q_values": [1e4, 1e5, 1e6],
            "temperatures_k": [280.0, 300.0, 320.0],
            "gamma_q_over_2pi_hz": [1e3, 1e4, 1e5],
        },
        "rows": rows,
    }


def simulate_mems_rod_proxy() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from simulations.glass_resonator import RodGeometry
    from simulations.mems_q_model import (
        AnchorDesign,
        OperatingConditions,
        compute_Q_budget,
    )

    rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type="fused_silica")
    conditions = OperatingConditions(temperature=300.0, pressure=1.0)
    scenarios = {
        "end_anchor": AnchorDesign(),
        "nodal_isolated_anchor": AnchorDesign(
            tether_width=1e-6,
            tether_thickness=1e-6,
            tether_length=50e-6,
            attachment_position="nodal",
            isolation_trenches=True,
        ),
    }
    output = {}
    for name, anchor in scenarios.items():
        result = compute_Q_budget(rod=rod, anchor=anchor, conditions=conditions)
        output[name] = {
            "frequency_hz": result.frequency,
            "q_total": result.Q_total,
            "qf_screen_ratio": result.Q_total * result.frequency / (K_B * 300.0 / H),
            "qf_screen_gap": (K_B * 300.0 / H) / (result.Q_total * result.frequency),
            "dominant_loss": result.dominant_loss,
            "loss_budget": result.loss_budget,
        }

    return {
        "roadmap_gate": "QT-0C geometry proxy only",
        "model": "simulations.mems_q_model 1 mm x 40 um fused-silica rod",
        "warning": (
            "The roadmap target is a 1 mm x 1 mm x 50 um plate. This rod model is a "
            "sensitivity proxy, not a prediction for the proposed die."
        ),
        "scenarios": output,
    }


def simulate_parametric_thresholds(
    measured_q: dict[str, Any], mems_proxy: dict[str, Any]
) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from simulations.mathieu_parametric import _epsilon_threshold

    scenarios = {
        "measured_loaded_q_median": measured_q["loaded_q"]["median"],
        "measured_loaded_q_max": measured_q["loaded_q"]["max"],
        "roadmap_classical_mems_target": 1e4,
        "rod_proxy_end_anchor": mems_proxy["scenarios"]["end_anchor"]["q_total"],
        "rod_proxy_nodal_isolated": mems_proxy["scenarios"]["nodal_isolated_anchor"]["q_total"],
    }
    rows = []
    for name, q in scenarios.items():
        epsilon = float(_epsilon_threshold(q))
        rows.append(
            {
                "scenario": name,
                "q": q,
                "epsilon_threshold_fraction": epsilon,
                "epsilon_threshold_percent": 100.0 * epsilon,
            }
        )
    return {
        "roadmap_gate": "QT-1C classical precursor simulation",
        "model": "simulations.mathieu_parametric._epsilon_threshold: epsilon_min = 2/Q",
        "rows": rows,
        "interpretation": (
            "Higher Q sharply lowers the classical parametric threshold, but crossing it "
            "does not cool the mode or produce a nonclassical state."
        ),
        "limitation": (
            "Existing captures do not calibrate fractional stiffness modulation versus drive, "
            "so these thresholds cannot yet be converted into a required voltage or pump power."
        ),
    }


def _format_scientific(value: float) -> str:
    return f"{value:.3e}"


def render_report(results: dict[str, Any]) -> str:
    phase = results["phase_interference"]
    intermod = results["intermodulation"]
    h_matrix = results["h_matrix"]
    measured = results["measured_q"]
    rate_envelope = results["rate_envelope"]
    proxy = results["mems_rod_proxy"]
    parametric = results["parametric_thresholds"]
    best = measured["best_measured_mode"]
    coupling_rows = [
        row
        for row in rate_envelope["rows"]
        if row["temperature_k"] == 300.0 and row["frequency_hz"] == 10e6
    ]

    lines = [
        "# CWM Quantum Transition: Preliminary Existing-Data Results",
        "",
        "**Status:** PRELIMINARY / CLASSICAL BOUNDS. No quantum state or quantum witness was measured.",
        "",
        "## Result Summary",
        "",
        "| Question | Preliminary result | Meaning |",
        "| --- | --- | --- |",
        (
            f"| Does a classical phase model explain the saved sweeps? | "
            f"{phase['sweep_count']} sweeps; median leave-one-phase-out first-harmonic R2 "
            f"{phase['first_harmonic_leave_one_out_r2']['median']:.3f} "
            f"(training R2 {phase['first_harmonic_r2']['median']:.3f}) | "
            "Quantifies the classical interference null; not a quantum witness |"
        ),
        (
            f"| Is nonlinearity resolved at the tested macro drive? | "
            f"Maximum positive standardized excess {intermod['max_positive_sigma']:.2f} sigma; "
            f"{intermod['positive_products_ge_3_sigma']} products at or above 3 sigma | "
            "No detected intermodulation; K remains unidentifiable |"
        ),
        (
            f"| What rank is visible now? | H shape "
            f"{h_matrix['raw']['shape'][0]} x {h_matrix['raw']['shape'][1]}; "
            f"entropy-effective rank {h_matrix['raw']['entropy_effective_rank']:.3f} | "
            "Two-channel ceiling; rank-8 still requires new hardware |"
        ),
        (
            f"| How close is the best measured mode to the 300 K bare Qf screen? | "
            f"f={best['frequency_hz'] / 1e3:.2f} kHz, Q={best['q']:.1f}, "
            f"Qf/(kBT/h)={_format_scientific(best['qf_screen_ratio'])} | "
            "A measured classical baseline, not a MEMS quantum projection |"
        ),
        (
            f"| Does higher Q help the classical parametric threshold? | "
            f"epsilon_min falls from {parametric['rows'][0]['epsilon_threshold_percent']:.3f}% "
            f"at measured median Q to 0.020% at Q=1e4 | "
            "Useful for a classical latch; does not solve thermal occupation |"
        ),
        "",
        "## 1. Classical Phase Null (QT-0B Precursor)",
        "",
        (
            f"Across {phase['sweep_count']} saved phase-energy sweeps, the median fitted "
            f"first-harmonic R2 is {phase['first_harmonic_r2']['median']:.3f}; "
            f"leave-one-phase-out prediction gives {phase['first_harmonic_leave_one_out_r2']['median']:.3f}. "
            f"The fraction with cross-validated R2 >= 0.8 is "
            f"{phase['fraction_sweeps_cv_r2_ge_0_8']:.1%}."
        ),
        "",
        (
            f"The worst sweep is {phase['worst_first_harmonic_sweep']['frequency_hz'] / 1e3:.1f} kHz "
            f"with leave-one-out R2 {phase['worst_first_harmonic_sweep']['r2_first_harmonic_loo']:.3f}; "
            f"the median second-harmonic improvement is "
            f"{phase['second_harmonic_delta_r2']['median']:.3f}. The simple null therefore "
            "describes much, but not all, of the archive. Weak modulation, source distortion, "
            "or multimode terms must be tested before interpreting residuals."
        ),
        "",
        (
            "This is evidence about model adequacy only. The archive contains phase-energy "
            "grids and spectra, not the raw phase-referenced voltage records needed to close QT-0B."
        ),
        "",
        "## 2. Macro Nonlinearity Bound (QT-1C Precursor)",
        "",
        (
            f"The controlled dual-tone files contain {intermod['standardized_record_count']} "
            f"standardized IM comparisons. The largest positive excess is "
            f"{intermod['max_positive_sigma']:.2f} sigma, the largest absolute deviation is "
            f"{intermod['max_absolute_sigma']:.2f} sigma, and none reaches 3 sigma. "
            f"The earlier noise-ratio scan peaks at {intermod['noise_ratio_max']:.2f} times its "
            "local noise floor."
        ),
        "",
        (
            "The standardized values use the AWG-only or f1-only single-tone floor according "
            "to the source experiment; the machine-readable summary preserves that reference "
            "for every comparison. Because no uncorrected comparison reaches 3 sigma, a "
            "multiple-comparison correction cannot create a detection. This supports a linear "
            "macro-substrate null at the tested settings, but the dataset has no calibrated "
            "effect-size or power bound. It does not measure a Duffing coefficient or K because "
            "displacement calibration and a drive-power sweep are absent."
        ),
        "",
        "## 3. Readout Rank Bound (QT-1B Precursor)",
        "",
        (
            f"The simultaneous H matrix has two receiver columns. Its raw singular-value "
            f"condition number is {h_matrix['raw']['condition_number']:.2f}, algebraic rank is "
            f"{h_matrix['raw']['algebraic_rank']}, and entropy-effective rank is "
            f"{h_matrix['raw']['entropy_effective_rank']:.3f}. After column-gain normalization, "
            f"the entropy-effective rank is "
            f"{h_matrix['column_gain_normalized']['entropy_effective_rank']:.3f}."
        ),
        "",
        "No reanalysis of these two channels can establish rank 8; additional independent receivers are required.",
        "",
        "## 4. Thermal and Coupling Envelope (QT-0C)",
        "",
        (
            f"The ten-mode June 3 bandwidth dataset has median loaded Q "
            f"{measured['loaded_q']['median']:.1f} and maximum Q "
            f"{measured['loaded_q']['max']:.1f}. The best measured Qf screen ratio is "
            f"{_format_scientific(best['qf_screen_ratio'])}."
        ),
        "",
        "The generated JSON includes the full 280-320 K, 3.5-35 MHz, Q=1e4-1e6 coupling envelope for Cq=1.",
        "",
        "### Representative 300 K coupling screen",
        "",
        "At high temperature the thermal rate is nearly frequency-independent at fixed Q. The 10 MHz rows are representative of the 3.5-35 MHz band.",
        "",
        "| Q | Gamma_Sigma / 2pi | Required g / 2pi at gamma_q / 2pi = 1 kHz | At 10 kHz | At 100 kHz |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in coupling_rows:
        coupling = row["required_g_over_2pi_hz_for_cq_1"]
        lines.append(
            f"| {row['q']:.0e} | {row['gamma_sigma_over_2pi_hz'] / 1e6:.2f} MHz | "
            f"{coupling['1000'] / 1e3:.1f} kHz | {coupling['10000'] / 1e3:.1f} kHz | "
            f"{coupling['100000'] / 1e3:.1f} kHz |"
        )
    lines.extend(
        [
            "",
        "### Existing MEMS model proxy",
        "",
        "| Scenario | Frequency | Modeled Q | Qf screen ratio | Remaining gap | Dominant loss |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for name, scenario in proxy["scenarios"].items():
        lines.append(
            f"| {name} | {scenario['frequency_hz'] / 1e6:.3f} MHz | "
            f"{scenario['q_total']:.1f} | {_format_scientific(scenario['qf_screen_ratio'])} | "
            f"{scenario['qf_screen_gap']:.1f}x | "
            f"{scenario['dominant_loss']} |"
        )
    lines.extend(
        [
            "",
            proxy["warning"],
            "",
            "## 5. Classical Parametric Threshold (QT-1C Simulation)",
            "",
            "| Scenario | Q | epsilon_min |",
            "| --- | ---: | ---: |",
        ]
    )
    for row in parametric["rows"]:
        label = row["scenario"]
        if label.startswith("rod_proxy"):
            label += " (rod geometry; see Section 4 caveat)"
        lines.append(
            f"| {label} | {row['q']:.1f} | "
            f"{row['epsilon_threshold_percent']:.4f}% |"
        )
    lines.extend(
        [
            "",
            parametric["interpretation"],
            "",
            parametric["limitation"],
            "",
            "## What Existing Data Cannot Answer",
            "",
            "- No saved dataset contains a quantum subsystem, single-shot quantum outcomes, or a nonclassical mechanical-state witness.",
            "- No calibrated displacement sweep supports an estimate of the single-quantum Kerr rate K.",
            "- No qubit-mode coupling data support an estimate of g or measured quantum cooperativity Cq.",
            "- No MEMS die exists yet, so MEMS Q, rank, heating, and transducer loading remain projected.",
            "- The saved phase grids can test a deterministic interference model but cannot complete the stochastic raw-voltage null required by QT-0B.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python3 tools/quantum_transition_preliminary.py",
            "```",
            "",
            "Machine-readable details are in `data/results/quantum_transition/preliminary_existing_data/summary.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATA / "quantum_transition" / "preliminary_existing_data",
    )
    args = parser.parse_args()

    measured_q = analyze_measured_q()
    mems_proxy = simulate_mems_rod_proxy()
    results = {
        "status": "PRELIMINARY_CLASSICAL_BOUNDS",
        "phase_interference": analyze_phase_interference(),
        "intermodulation": analyze_intermodulation(),
        "h_matrix": analyze_h_matrix(),
        "measured_q": measured_q,
        "rate_envelope": simulate_rate_envelope(),
        "mems_rod_proxy": mems_proxy,
        "parametric_thresholds": simulate_parametric_thresholds(
            measured_q, mems_proxy
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "summary.json"
    report_path = args.output_dir / "report.md"
    summary_path.write_text(json.dumps(_json_number(results), indent=2) + "\n")
    report_path.write_text(render_report(results))
    print(f"Wrote {summary_path.relative_to(ROOT)}")
    print(f"Wrote {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()