#!/usr/bin/env python3
"""Transparent wavelength/pitch scaling calculator for CWM wave-gate candidates.

This tool intentionally does NOT predict memory capacity, classification accuracy,
Q, energy, fabrication yield, or commercial density. It computes only quantities
that follow directly from user-supplied assumptions.

Examples:
    python tools/wave_gate_scaling.py \
        --velocity 5000 --frequency 5e9 --pitch-lambda 5

    python tools/wave_gate_scaling.py \
        --velocity 5000 --frequency 1e9 5e9 10e9 \
        --pitch-lambda 3 --effective-dimensions 8 --query-rate 1e6 \
        --system-energy 2e-12 --json
"""
from __future__ import annotations

import argparse
import json


def calculate(
    velocity_m_s: float,
    frequency_hz: float,
    pitch_lambda: float,
    effective_dimensions: float | None = None,
    query_rate_hz: float | None = None,
    system_energy_j: float | None = None,
) -> dict:
    wavelength_m = velocity_m_s / frequency_hz
    pitch_m = pitch_lambda * wavelength_m
    cells_per_m2 = 1.0 / (pitch_m * pitch_m)
    result = {
        "velocity_m_s": velocity_m_s,
        "frequency_hz": frequency_hz,
        "wavelength_m": wavelength_m,
        "wavelength_um": wavelength_m * 1e6,
        "pitch_lambda_multiple": pitch_lambda,
        "pitch_m": pitch_m,
        "pitch_um": pitch_m * 1e6,
        "ideal_cells_per_mm2": cells_per_m2 / 1e6,
        "ideal_cells_per_cm2": cells_per_m2 / 1e4,
    }

    if effective_dimensions is not None:
        result["effective_dimensions"] = effective_dimensions
        result["effective_dimensions_per_mm2"] = (
            result["ideal_cells_per_mm2"] * effective_dimensions
        )

    if effective_dimensions is not None and query_rate_hz is not None:
        result["query_rate_hz"] = query_rate_hz
        result["transform_dimensions_per_mm2_s"] = (
            result["ideal_cells_per_mm2"] * effective_dimensions * query_rate_hz
        )

    if effective_dimensions is not None and system_energy_j is not None:
        result["system_energy_j_per_query"] = system_energy_j
        result["effective_dimensions_per_joule"] = (
            effective_dimensions / system_energy_j
            if system_energy_j > 0
            else None
        )

    return result


def fmt(x: float) -> str:
    if x == 0:
        return "0"
    if abs(x) >= 1e4 or abs(x) < 1e-3:
        return f"{x:.4e}"
    return f"{x:.4f}"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Compute wavelength and idealized pitch-density envelopes."
    )
    ap.add_argument("--velocity", type=float, required=True, help="wave velocity in m/s")
    ap.add_argument(
        "--frequency",
        type=float,
        nargs="+",
        required=True,
        help="one or more operating frequencies in Hz",
    )
    ap.add_argument(
        "--pitch-lambda",
        type=float,
        default=3.0,
        help="assumed pitch as a multiple of wavelength (default: 3)",
    )
    ap.add_argument("--effective-dimensions", type=float)
    ap.add_argument("--query-rate", type=float, help="queries/s")
    ap.add_argument("--system-energy", type=float, help="total J/query")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.velocity <= 0:
        ap.error("--velocity must be > 0")
    if args.pitch_lambda <= 0:
        ap.error("--pitch-lambda must be > 0")
    if any(f <= 0 for f in args.frequency):
        ap.error("all --frequency values must be > 0")
    if args.effective_dimensions is not None and args.effective_dimensions < 0:
        ap.error("--effective-dimensions must be >= 0")
    if args.query_rate is not None and args.query_rate < 0:
        ap.error("--query-rate must be >= 0")
    if args.system_energy is not None and args.system_energy < 0:
        ap.error("--system-energy must be >= 0")

    results = [
        calculate(
            velocity_m_s=args.velocity,
            frequency_hz=f,
            pitch_lambda=args.pitch_lambda,
            effective_dimensions=args.effective_dimensions,
            query_rate_hz=args.query_rate,
            system_energy_j=args.system_energy,
        )
        for f in args.frequency
    ]

    if args.json:
        print(json.dumps({"assumption_warning": (
            "Geometric envelope only. Cell density ignores electrodes, routing, "
            "isolation, packaging, yield, and readout."
        ), "results": results}, indent=2))
        return

    print("GEOMETRIC WAVE-GATE SCALING ENVELOPE")
    print("WARNING: idealized geometry only; not a product-density claim.")
    for r in results:
        print()
        print(f"f = {fmt(r['frequency_hz'])} Hz")
        print(f"  wavelength:        {fmt(r['wavelength_um'])} um")
        print(f"  assumed pitch:     {fmt(r['pitch_um'])} um")
        print(f"  cells/mm^2 ideal:  {fmt(r['ideal_cells_per_mm2'])}")
        if "effective_dimensions_per_mm2" in r:
            print(
                "  eff. dims/mm^2:    "
                f"{fmt(r['effective_dimensions_per_mm2'])}"
            )
        if "transform_dimensions_per_mm2_s" in r:
            print(
                "  transform dims/mm^2/s: "
                f"{fmt(r['transform_dimensions_per_mm2_s'])}"
            )
        if "effective_dimensions_per_joule" in r:
            print(
                "  eff. dims/J:       "
                f"{fmt(r['effective_dimensions_per_joule'])}"
            )


if __name__ == "__main__":
    main()
