#!/usr/bin/env python3
"""Retrospective FT-0 analysis for distributed partial-view CWM hypotheses.

This tool does NOT prove holography. It reuses committed historical datasets to
ask whether a task label remains recoverable from partial spectral or spatial
views.

Inputs:
- E26 partial-query recall: adaptive top-K historical experiment.
- E36 null-control raw_data: exhaustive arbitrary mode-index subset analysis.
- E8 dual-receiver compute-basis: same discrete state decoded from two spatial
  receiver positions with different analog intensity ratios.
- FT-1 S1-S3: machine-readable transfer stability / electrical-control context.

The E36 scoring intentionally reproduces the original exp_null_control scoring
rule from tools/additional_experiments.py. Results are retrospective,
same-session, small-N hypothesis-forming evidence only.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_E26 = ROOT / "data/results/lab/additional_exps/additional_20260409_171342.json"
DEFAULT_E36 = ROOT / "data/results/lab/additional_exps/additional_20260411_105304.json"
DEFAULT_USERS = ROOT / "data/results/lab/users.json"
DEFAULT_E8 = ROOT / "data/results/quantum_bridge/e8_compute_basis_20260602_183334.json"
DEFAULT_FT1 = [
    ROOT / "data/results/k_eff/FT1-S1/derived/summary.json",
    ROOT / "data/results/k_eff/FT1-S2/derived/summary.json",
    ROOT / "data/results/k_eff/FT1-S3/derived/summary.json",
]
DEFAULT_FT1_HELD = ROOT / "data/results/k_eff/FT1-S3/derived/superposition_heldout.json"

FREQ_MATCH_FRAC = 0.03


def load_json(path: Path):
    return json.loads(path.read_text())


def enrollment(users: dict, rods: list[str]) -> dict[str, list[float]]:
    return {
        r: [float(x) for x in users["rods"][r]["perturbed_hz"][:10]]
        for r in rods
    }


def expected_at_frequency(freq: float, peaks: list[float]) -> bool:
    return any(abs(freq - ep) / max(freq, ep) < FREQ_MATCH_FRAC for ep in peaks)


def score_subset(raw_data: dict, enrolled: dict, rods: list[str], indices: tuple[int, ...]):
    correct = 0
    margins: list[float] = []

    for query_rod in rods:
        scores = {sense_rod: 0.0 for sense_rod in rods}

        for peak_index in indices:
            freq = enrolled[query_rod][peak_index]
            mags = {
                sense_rod: float(raw_data[query_rod][sense_rod][peak_index])
                for sense_rod in rods
            }
            total = sum(mags.values())
            if total <= 0:
                continue

            for sense_rod in rods:
                frac = mags[sense_rod] / total
                scores[sense_rod] += frac * (
                    3.0 if expected_at_frequency(freq, enrolled[sense_rod]) else -1.0
                )

        winner = max(scores, key=scores.get)
        if winner == query_rod:
            correct += 1

        best_other = max(scores[r] for r in rods if r != query_rod)
        margins.append(scores[query_rod] - best_other)

    return {
        "accuracy": correct / len(rods),
        "correct": correct,
        "n_rods": len(rods),
        "mean_margin": mean(margins),
        "min_margin": min(margins),
    }


def exhaustive_e36(e36: dict, users: dict):
    raw_data = e36["results"]["null_control"]["raw_data"]
    rods = sorted(raw_data)
    enrolled = enrollment(users, rods)

    rows = []
    perfect_examples = {}

    for k in range(1, 11):
        evaluations = []
        for indices in itertools.combinations(range(10), k):
            r = score_subset(raw_data, enrolled, rods, indices)
            r["indices"] = list(indices)
            evaluations.append(r)

        accuracies = [r["accuracy"] for r in evaluations]
        margins = sorted(r["mean_margin"] for r in evaluations)
        perfect = [r for r in evaluations if r["accuracy"] == 1.0]

        rows.append(
            {
                "k_modes": k,
                "n_subsets": len(evaluations),
                "mean_accuracy": mean(accuracies),
                "fraction_subsets_100pct": len(perfect) / len(evaluations),
                "fraction_subsets_ge_75pct": (
                    sum(a >= 0.75 for a in accuracies) / len(evaluations)
                ),
                "median_mean_margin": median(margins),
                "minimum_mean_margin": min(margins),
            }
        )
        if k <= 4:
            perfect_examples[str(k)] = [
                {
                    "indices": r["indices"],
                    "mean_margin": r["mean_margin"],
                }
                for r in perfect[:5]
            ]

    return {
        "status": "retrospective same-session exploratory analysis",
        "scoring_rule": (
            "Reproduces E36 frequency-match scoring: expected +3*magnitude_fraction, "
            "unexpected -1*magnitude_fraction, 3% frequency match tolerance."
        ),
        "important_difference_from_E26": (
            "Enumerates every combination of fixed peak indices rather than selecting "
            "the query rod's strongest K modes from a preliminary full-spectrum measurement."
        ),
        "rows": rows,
        "perfect_subset_examples": perfect_examples,
    }


def summarize_e26(e26: dict):
    result = e26["results"]["partial_query_recall"]
    return {
        "status": "historical adaptive-top-K hardware experiment",
        "min_peaks_for_100pct": result["min_peaks_for_100pct"],
        "results": result["results"],
        "claim_limit": (
            "Modes were ranked by a fresh full-spectrum measurement for each query rod "
            "before top-K testing; this is not arbitrary-subset or blind partial-view evidence."
        ),
    }


def summarize_e8(e8: dict):
    dec = e8["decode_results"]
    all_same = all(
        row["decoded_A"] == label
        and row["decoded_B"] == label
        and row["accuracy_A"] == 100.0
        and row["accuracy_B"] == 100.0
        for label, row in dec.items()
    )
    return {
        "status": "historical same-session two-receiver experiment",
        "same_four_states_recovered_at_both_receivers": all_same,
        "n_input_states": len(dec),
        "receiver_A_distinct_states": e8["n_distinct_A"],
        "receiver_B_distinct_states": e8["n_distinct_B"],
        "pattern_11_intensity_ratio_A_f1_over_f2": e8["intensity_ratios_pattern_11"][
            "ratio_A_f1_over_f2"
        ],
        "pattern_11_intensity_ratio_B_f1_over_f2": e8["intensity_ratios_pattern_11"][
            "ratio_B_f1_over_f2"
        ],
        "ratio_of_ratios": e8["intensity_ratios_pattern_11"]["ratio_of_ratios"],
        "claim_limit": (
            "Both receivers recover the same 2-bit input state. Treat this as redundant "
            "spatial access with different analog views, not four independent bits."
        ),
    }


def summarize_ft1(summary_paths: list[Path], held_path: Path):
    sessions = []
    for path in summary_paths:
        d = load_json(path)
        sessions.append(
            {
                "session_id": d["session_id"],
                "glass_vs_electrical_only": d.get("glass_vs_electrical_only"),
                "loopback": d.get("loopback"),
            }
        )

    held = load_json(held_path)
    held_aggregates = {}
    for ch, chdata in held["channels"].items():
        held_aggregates[ch] = {}
        for order, result in chdata["result"].items():
            held_aggregates[ch][order] = {
                "complex_error_median": result["e_median"],
                "magnitude_error_median": result["e_mag_median"],
                "noise_limited_error_median": result["e_noise_median"],
                "phase_bias_deg_median": result["phase_bias_deg_median"],
            }

    return {
        "status": "context, not a partial-view experiment",
        "sessions": sessions,
        "original_preregistered_heldout_summary": held_aggregates,
        "interpretation": (
            "FT-1 establishes a qualified complex transfer/reference framework and shows "
            "that cross-session transfer changes can dominate held-out prediction. Any "
            "partial-view/reconstruction experiment must control fixture and temperature."
        ),
        "posthoc_matched_frequency_note": (
            "See docs/lab_diary_20261027.md section 9: matched-frequency post hoc analysis "
            "reported 1.2-2.0% within-session and 7-8% held-out median superposition error. "
            "This does not change FT-1's preregistered INCONCLUSIVE outcome."
        ),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    e26 = load_json(DEFAULT_E26)
    e36 = load_json(DEFAULT_E36)
    users = load_json(DEFAULT_USERS)
    e8 = load_json(DEFAULT_E8)

    result = {
        "analysis": "CWM holographic-like / distributed partial-view FT-0",
        "claim_boundary": (
            "Tests task-level redundancy across partial spectral/spatial views. "
            "It does not demonstrate optical-style holographic field reconstruction, "
            "quantum holography, or a full state recoverable from every fragment."
        ),
        "e26_adaptive_top_k": summarize_e26(e26),
        "e36_exhaustive_mode_subsets": exhaustive_e36(e36, users),
        "e8_two_spatial_views": summarize_e8(e8),
        "ft1_transfer_context": summarize_ft1(DEFAULT_FT1, DEFAULT_FT1_HELD),
        "hypothesis": (
            "Task identity may be redundantly distributed across the CWM response: "
            "moderate partial spectral or spatial views can preserve the same discrete "
            "state even when the analog transfer observed by each view differs."
        ),
        "next_required_test": (
            "Preregister random/fixed spectral subsets and multiple spatial receiver views, "
            "freeze selection/decoder on training sessions, and score complete later sessions "
            "under controlled fixture/temperature conditions. Separately test reference-assisted "
            "complex reconstruction; do not merge it with task-level redundancy."
        ),
    }

    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")


if __name__ == "__main__":
    main()
