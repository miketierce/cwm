#!/usr/bin/env python3
"""
AWG stepped-dwell rod identifier.

Exploits the discovery that driving the AWG at a rod's enrolled frequencies
produces measurable mechanical resonance (2-11× above feedthrough) even
though the absolute signal is orders of magnitude weaker than a tap.

Algorithm:
  1. Measure feedthrough baseline at off-resonance reference frequencies
  2. For each enrolled rod, drive AWG at its peak frequencies and measure
     the on-resonance magnitude
  3. Compute ratio = on_resonance / interpolated_baseline at each peak
  4. Score each rod using weighted sum of (ratio - 1) for ratios > 1,
     emphasizing high-frequency peaks (>3 kHz) where feedthrough is
     lower and resonance ratios are larger
  5. Winner = rod with highest score; Rod on Ch B (disabled) will always
     score lowest, providing channel discrimination

Limitations:
  - Only works with Ch A (Ch B breaks ps2000 on macOS ARM64)
  - Takes ~2 minutes for 4 rods (40 frequencies × 0.2s settle × 12 avgs)
  - Marginal discrimination for rods with many overlapping peaks (Rod 4)
  - Not a replacement for tap mode; a proof-of-concept for autonomous excitation

Usage:
  python tools/awg_stepped_dwell_id.py [--users path/to/users.json]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from picosdk.ps2000 import ps2000

# ── Configuration ─────────────────────────────────────────────────────────

N_PEAKS = 10              # enrolled peaks per rod to test
N_AVG_ON = 12             # captures per on-resonance frequency
N_AVG_OFF = 8             # captures per off-resonance point
SETTLE_ON_S = 0.20        # AWG settle time for on-resonance
SETTLE_OFF_S = 0.15       # AWG settle time for off-resonance
HF_THRESHOLD_HZ = 3000.0  # high-freq threshold for weighted scoring
HF_WEIGHT = 3.0           # weight multiplier for peaks > HF_THRESHOLD
RATIO_THRESHOLD = 1.2     # minimum ratio to count as contributing
PROXIMITY_PCT = 5.0        # ±% to consider peaks overlapping

DEFAULT_USERS = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "users.json"


# ── Scope helpers ─────────────────────────────────────────────────────────

def _open_scope():
    """Open PicoScope with Ch A only (Ch B disabled — macOS ps2000 bug)."""
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V, DC
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B OFF
    return handle


def _close_scope(handle):
    """Silence AWG and close scope."""
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)


def _measure_at(handle, freq_hz: float, n_avg: int, settle_s: float) -> float:
    """Drive AWG at freq_hz, capture n_avg blocks, return FFT magnitude at that freq."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(settle_s)

    magnitudes = []
    for _ in range(n_avg):
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
        t_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.002)
            if time.time() - t0 > 2:
                break
        buf_a = (ctypes.c_int16 * N_SAMPLES)()
        buf_b = (ctypes.c_int16 * N_SAMPLES)()
        overflow = ctypes.c_int16()
        n = ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES
        )
        if n > 0:
            raw = np.array(buf_a[:n], dtype=np.float64)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            target_bin = int(round(freq_hz / bin_hz))
            lo = max(0, target_bin - 3)
            hi = min(len(fft) - 1, target_bin + 3)
            magnitudes.append(float(np.max(fft[lo:hi + 1])))

    return float(np.mean(magnitudes)) if magnitudes else 0.0


# ── Baseline interpolation ────────────────────────────────────────────────

def _build_baseline(handle, all_peaks_hz: list[float]) -> tuple:
    """Build feedthrough baseline from off-resonance reference points.

    Places reference points at midpoints between consecutive enrolled peaks
    (where no rod should resonate), plus 500 Hz and max+2000 Hz anchors.
    Returns (sorted_freqs, sorted_mags) for linear interpolation.
    """
    sorted_peaks = sorted(set(round(f, 1) for f in all_peaks_hz))

    off_freqs = []
    for i in range(len(sorted_peaks) - 1):
        mid = (sorted_peaks[i] + sorted_peaks[i + 1]) / 2
        # Only use if far enough from any peak
        if all(abs(mid - p) / p > 0.03 for p in sorted_peaks):
            off_freqs.append(mid)

    # Add anchor points at extremes
    off_freqs = [500.0] + off_freqs + [max(sorted_peaks) + 2000.0]

    off_mags = []
    for f in off_freqs:
        mag = _measure_at(handle, f, N_AVG_OFF, SETTLE_OFF_S)
        off_mags.append(mag)

    return off_freqs, off_mags


def _interpolate_baseline(freq_hz: float, off_freqs: list, off_mags: list) -> float:
    """Linearly interpolate feedthrough baseline at freq_hz."""
    if freq_hz <= off_freqs[0]:
        return off_mags[0]
    if freq_hz >= off_freqs[-1]:
        return off_mags[-1]
    for i in range(len(off_freqs) - 1):
        if off_freqs[i] <= freq_hz <= off_freqs[i + 1]:
            frac = (freq_hz - off_freqs[i]) / (off_freqs[i + 1] - off_freqs[i])
            return off_mags[i] + frac * (off_mags[i + 1] - off_mags[i])
    return off_mags[-1]


# ── Uniqueness analysis ──────────────────────────────────────────────────

def _find_unique_peaks(enrolled_rods: dict) -> dict:
    """For each rod, identify which peaks are unique (no other rod within ±PROXIMITY_PCT%).

    Returns {rod_id: [bool, ...]} indicating uniqueness of each peak.
    """
    result = {}
    for rid, peaks in enrolled_rods.items():
        unique = []
        for f in peaks:
            is_unique = True
            for other_rid, other_peaks in enrolled_rods.items():
                if other_rid == rid:
                    continue
                for of in other_peaks:
                    if abs(f - of) / f < PROXIMITY_PCT / 100:
                        is_unique = False
                        break
                if not is_unique:
                    break
            unique.append(is_unique)
        result[rid] = unique
    return result


# ── Scoring ───────────────────────────────────────────────────────────────

def _score_rod(ratios: list[float], freqs: list[float],
               is_unique: list[bool]) -> dict:
    """Score a rod's resonance ratio profile.

    Scoring weights:
      - Ratios > RATIO_THRESHOLD contribute (ratio - 1) to the score
      - Peaks > HF_THRESHOLD_HZ get HF_WEIGHT multiplier (less feedthrough)
      - Unique peaks get 2× bonus (no ambiguity with other rods)

    Returns dict with score, contributing peaks, and diagnostics.
    """
    total = 0.0
    contributors = []
    for i, (ratio, freq, uniq) in enumerate(zip(ratios, freqs, is_unique)):
        if ratio < RATIO_THRESHOLD:
            continue
        excess = ratio - 1.0
        weight = HF_WEIGHT if freq > HF_THRESHOLD_HZ else 1.0
        if uniq:
            weight *= 2.0
        contribution = excess * weight
        total += contribution
        contributors.append({
            "peak_idx": i + 1,
            "freq_hz": round(freq, 1),
            "ratio": round(ratio, 2),
            "weight": round(weight, 1),
            "contribution": round(contribution, 2),
            "unique": uniq,
        })
    return {
        "score": round(total, 2),
        "n_contributing": len(contributors),
        "contributors": contributors,
    }


# ── Main identification ──────────────────────────────────────────────────

def identify(users_path: Path = DEFAULT_USERS,
             verbose: bool = True) -> dict:
    """Run stepped-dwell AWG identification on all enrolled rods.

    Returns:
      {
        "winner": rod_id,
        "ranked": [{rod_id, score, n_contributing, ratios, ...}, ...],
        "baseline_points": int,
        "duration_s": float,
      }
    """
    with open(users_path) as f:
        db = json.load(f)

    enrolled = {}
    for rid in sorted(db["rods"].keys()):
        r = db["rods"][rid]
        if r.get("enrolled"):
            enrolled[rid] = r["perturbed_hz"][:N_PEAKS]

    if not enrolled:
        raise RuntimeError("No enrolled rods in database")

    uniqueness = _find_unique_peaks(enrolled)
    all_peaks = [f for peaks in enrolled.values() for f in peaks]

    if verbose:
        print("=" * 65)
        print("  AWG STEPPED-DWELL IDENTIFICATION")
        print("=" * 65)
        print(f"  Enrolled rods: {list(enrolled.keys())}")
        for rid, peaks in enrolled.items():
            n_uniq = sum(uniqueness[rid])
            print(f"    Rod {rid}: {len(peaks)} peaks, "
                  f"{n_uniq} unique (>{PROXIMITY_PCT}% from others)")
        print()

    t_start = time.time()
    handle = _open_scope()

    try:
        # Phase 1: Feedthrough baseline
        if verbose:
            print("Phase 1: Measuring feedthrough baseline...", end="", flush=True)
        off_freqs, off_mags = _build_baseline(handle, all_peaks)
        if verbose:
            print(f" {len(off_freqs)} points")

        # Phase 2: On-resonance measurement for each rod
        rod_results = {}
        for rid, peaks in enrolled.items():
            if verbose:
                print(f"Phase 2: Rod {rid} ({len(peaks)} peaks)...",
                      end="", flush=True)
            ratios = []
            on_mags = []
            for f in peaks:
                on_mag = _measure_at(handle, f, N_AVG_ON, SETTLE_ON_S)
                bl = _interpolate_baseline(f, off_freqs, off_mags)
                ratio = on_mag / bl if bl > 0 else 0.0
                ratios.append(ratio)
                on_mags.append(on_mag)
            if verbose:
                strong = sum(1 for r in ratios if r > 2.0)
                print(f" {strong} strong resonances")

            score_info = _score_rod(ratios, peaks, uniqueness[rid])

            rod_results[rid] = {
                "rod_id": rid,
                "pattern": db["rods"][rid].get("pattern", "?"),
                "ratios": [round(r, 2) for r in ratios],
                "on_mags": [round(m, 0) for m in on_mags],
                "score": score_info["score"],
                "n_contributing": score_info["n_contributing"],
                "contributors": score_info["contributors"],
                "n_unique": sum(uniqueness[rid]),
                "n_strong": sum(1 for r in ratios if r > 2.0),
            }

    finally:
        _close_scope(handle)

    duration = time.time() - t_start

    # Rank by score (highest = most resonance = best match)
    ranked = sorted(rod_results.values(), key=lambda r: -r["score"])
    winner = ranked[0]["rod_id"] if ranked else None

    result = {
        "winner": winner,
        "ranked": ranked,
        "baseline_points": len(off_freqs),
        "duration_s": round(duration, 1),
    }

    if verbose:
        print()
        print("=" * 65)
        print("  RESULTS")
        print("=" * 65)
        print(f"{'Rod':>5} {'Pattern':>8} {'Score':>8} {'Strong':>7} "
              f"{'Contrib':>8} {'Ratios'}")
        print(f"{'---':>5} {'-------':>8} {'-----':>8} {'------':>7} "
              f"{'-------':>8} {'------'}")
        for r in ranked:
            ratio_str = " ".join(
                f"{v:4.1f}{'*' if v > 2 else ' '}"
                for v in r["ratios"]
            )
            print(f"{r['rod_id']:>5} {r['pattern']:>8} {r['score']:>8.1f} "
                  f"{r['n_strong']:>7} {r['n_contributing']:>8}  "
                  f"[{ratio_str}]")

        print(f"\n  >>> Winner: Rod {winner} "
              f"(score={ranked[0]['score']:.1f})")
        if len(ranked) >= 2:
            margin = ranked[0]["score"] - ranked[1]["score"]
            pct = margin / ranked[0]["score"] * 100 if ranked[0]["score"] > 0 else 0
            print(f"  >>> Margin: {margin:.1f} ({pct:.0f}% over Rod {ranked[1]['rod_id']})")

        print(f"\n  Duration: {duration:.1f}s  "
              f"Baseline points: {len(off_freqs)}")

        # Show top contributing peaks for winner
        if ranked[0]["contributors"]:
            print(f"\n  Winner's contributing peaks:")
            for c in ranked[0]["contributors"]:
                u = " (unique)" if c["unique"] else ""
                print(f"    f{c['peak_idx']:2d} = {c['freq_hz']:8.1f} Hz  "
                      f"ratio={c['ratio']:5.2f}  "
                      f"weight={c['weight']:.0f}×  "
                      f"→ {c['contribution']:.2f}{u}")

    return result


# ── CLI entry point ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AWG stepped-dwell rod identification"
    )
    parser.add_argument(
        "--users", type=Path, default=DEFAULT_USERS,
        help="Path to users.json enrollment database"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress verbose output"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output result as JSON"
    )
    args = parser.parse_args()

    result = identify(users_path=args.users, verbose=not args.quiet)

    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
