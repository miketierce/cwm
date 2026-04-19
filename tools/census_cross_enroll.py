#!/usr/bin/env python3
"""
Census Cross-Enrollment — augment census with cross-detected modes.

Reads an existing census and the push experiment capture data, then
produces a new census file where each receiver includes modes
discovered via cross-detection (frequencies where the receiver shows
strong response but had no original census peak).

The cross-detection threshold can be set; default is 1.5M magnitude
(same as the push experiment used).

Usage:
  python tools/census_cross_enroll.py \\
      --census data/results/lab/plate_exps/plate_census_20260417_200041.json \\
      --push   data/results/lab/plate_exps/bool_push_20260418_135737.json \\
      [--threshold 1500000] [--dedup-pct 2.0]
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"

DEFAULT_THRESHOLD = 1_500_000
DEFAULT_DEDUP_PCT = 2.0  # merge modes within this % of each other


def load_census(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def load_push(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def dedup_modes(modes: list[dict], pct: float) -> list[dict]:
    """Merge modes within pct% of each other, keeping the strongest."""
    if not modes:
        return []
    sorted_modes = sorted(modes, key=lambda m: m["freq_hz"])
    result = [sorted_modes[0]]
    for m in sorted_modes[1:]:
        prev = result[-1]
        if abs(m["freq_hz"] - prev["freq_hz"]) / max(m["freq_hz"], prev["freq_hz"]) * 100 < pct:
            # Keep the stronger one
            if m["magnitude"] > prev["magnitude"]:
                result[-1] = m
        else:
            result.append(m)
    return result


def cross_enroll(census: dict, push: dict,
                 threshold: float = DEFAULT_THRESHOLD,
                 dedup_pct: float = DEFAULT_DEDUP_PCT) -> dict:
    """Augment census with cross-detected modes from push capture."""
    capture = push["capture"]  # {freq_str: {key: magnitude, ...}, ...}
    results = census["results"]

    augmented = deepcopy(census)
    aug_results = augmented["results"]

    stats = {}  # key -> {"original": N, "added": N, "total": N}

    for key in sorted(results.keys()):
        original_peaks = results[key].get("peaks", [])
        original_freqs = [p["freq_hz"] for p in original_peaks]
        n_original = len(original_freqs)

        new_modes = []

        for freq_str, readings in capture.items():
            freq_hz = float(freq_str)
            mag = readings.get(key, 0)
            if mag < threshold:
                continue

            # Check if near an existing census peak for this key
            is_known = any(
                abs(freq_hz - cf) / max(freq_hz, cf) * 100 < dedup_pct
                for cf in original_freqs
            )
            if is_known:
                continue

            # Also check if near an already-added new mode
            already_added = any(
                abs(freq_hz - nm["freq_hz"]) / max(freq_hz, nm["freq_hz"]) * 100 < dedup_pct
                for nm in new_modes
            )
            if already_added:
                # Keep stronger
                for i, nm in enumerate(new_modes):
                    if abs(freq_hz - nm["freq_hz"]) / max(freq_hz, nm["freq_hz"]) * 100 < dedup_pct:
                        if mag > nm["magnitude"]:
                            new_modes[i] = {
                                "freq_hz": freq_hz,
                                "magnitude": mag,
                                "snr_db": 0.0,
                                "prominence_db": 0.0,
                                "phase_rad": 0.0,
                                "phase_std": 0.0,
                                "source": "cross_detect",
                            }
                        break
                continue

            new_modes.append({
                "freq_hz": freq_hz,
                "magnitude": mag,
                "snr_db": 0.0,       # not measured in push capture
                "prominence_db": 0.0,
                "phase_rad": 0.0,
                "phase_std": 0.0,
                "source": "cross_detect",
            })

        # Combine and dedup
        all_modes = list(original_peaks) + new_modes
        # Tag originals
        for m in all_modes:
            if "source" not in m:
                m["source"] = "census"

        all_modes = dedup_modes(all_modes, dedup_pct)

        aug_results[key]["peaks"] = all_modes
        stats[key] = {
            "original": n_original,
            "added": len(all_modes) - n_original,
            "total": len(all_modes),
        }

    return augmented, stats


def main():
    parser = argparse.ArgumentParser(
        description="Augment census with cross-detected modes from push capture")
    parser.add_argument("--census", required=True,
                        help="Path to original census JSON")
    parser.add_argument("--push", required=True,
                        help="Path to push experiment JSON")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Magnitude threshold for cross-detection (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--dedup-pct", type=float, default=DEFAULT_DEDUP_PCT,
                        help=f"Dedup percentage for merging nearby modes (default: {DEFAULT_DEDUP_PCT})")
    args = parser.parse_args()

    print(f"  Loading census: {args.census}")
    census = load_census(args.census)
    print(f"  Loading push:   {args.push}")
    push = load_push(args.push)

    print(f"\n  Cross-detection threshold: {args.threshold:,.0f}")
    print(f"  Dedup tolerance: {args.dedup_pct}%")
    print()

    augmented, stats = cross_enroll(census, push, args.threshold, args.dedup_pct)

    # Update metadata
    augmented["experiment"] = "census_cross_enrolled"
    augmented["cross_enrollment"] = {
        "source_census": args.census,
        "source_push": args.push,
        "threshold": args.threshold,
        "dedup_pct": args.dedup_pct,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "per_receiver": stats,
    }

    # Print summary
    print("  ┌─────────┬──────────┬───────┬───────┐")
    print("  │ Key     │ Original │ Added │ Total │")
    print("  ├─────────┼──────────┼───────┼───────┤")
    total_orig = 0
    total_added = 0
    total_all = 0
    for key in sorted(stats.keys()):
        s = stats[key]
        total_orig += s["original"]
        total_added += s["added"]
        total_all += s["total"]
        print(f"  │ {key:7s} │ {s['original']:8d} │ {s['added']:5d} │ {s['total']:5d} │")
    print("  ├─────────┼──────────┼───────┼───────┤")
    print(f"  │ TOTAL   │ {total_orig:8d} │ {total_added:5d} │ {total_all:5d} │")
    print("  └─────────┴──────────┴───────┴───────┘")

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = LAB_DIR / f"plate_census_cross_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(augmented, f, indent=2, default=str)
    print(f"\n  Saved: {out_path.name}")
    print(f"  Modes: {total_orig} → {total_all} (+{total_added})")

    return str(out_path)


if __name__ == "__main__":
    main()
