#!/usr/bin/env python3
"""
Re-enroll Rod 4 after putty reconfiguration, then verify all 4 rods
are visible on Ch A with sequential tap captures.

Usage:
  1. Run this script
  2. When prompted, flick Rod 4 (new putty at 15mm + 63mm)
  3. Script updates users.json with new Rod 4 peaks
  4. Then prompts for taps on Rods 1-4 to verify Ch A sees them all
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwm_picoscope import (
    _capture_and_fft,
    _extract_peaks_blind,
    check_hardware,
    N_MODES,
)

USERS = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "users.json"


def tap_capture(rod_label: str) -> tuple:
    """Prompt for a tap and capture spectrum. Returns (freq, mag, bin_hz, peaks_hz)."""
    print(f"\n  >>> FLICK {rod_label} NOW <<<")
    freq, mag, bin_hz = _capture_and_fft()
    rms = np.sqrt(np.mean(mag ** 2))
    min_bin = int(500 / bin_hz)
    noise = np.median(mag[min_bin:])
    peak_idx = min_bin + np.argmax(mag[min_bin:])
    snr = mag[peak_idx] / noise
    print(f"  Captured: SNR={snr:.0f}x ({20*np.log10(max(snr,1)):.0f} dB), "
          f"peak @ {freq[peak_idx]:.0f} Hz")

    peaks = _extract_peaks_blind(freq, mag, bin_hz)
    print(f"  Found {len(peaks)} peaks: {[round(p, 1) for p in peaks[:10]]}")
    return freq, mag, bin_hz, peaks


def main():
    if not check_hardware():
        print("ERROR: No PicoScope detected")
        sys.exit(1)

    with open(USERS) as f:
        db = json.load(f)

    print("=" * 60)
    print("  ROD 4 RE-ENROLLMENT + 4-ROD VERIFICATION")
    print("=" * 60)
    print()
    print("  Config: All 4 sense PZTs on Ch A")
    print("  Rod 4: new putty at 15mm + 63mm (pattern E)")
    print()

    # ── Step 1: Re-enroll Rod 4 ──────────────────────────────────────
    print("─── STEP 1: RE-ENROLL ROD 4 ───")
    print("  Old Rod 4 peaks: "
          f"{[round(f, 1) for f in db['rods']['4']['perturbed_hz'][:10]]}")

    _, _, _, peaks4 = tap_capture("Rod 4")

    # Pad to N_MODES
    while len(peaks4) < N_MODES:
        peaks4.append(0.0)
    peaks4 = peaks4[:N_MODES]

    # Save old enrollment for reference
    old_peaks = db["rods"]["4"]["perturbed_hz"][:10]

    # Update Rod 4
    db["rods"]["4"]["perturbed_hz"] = [float(p) for p in peaks4]
    db["rods"]["4"]["fingerprint"] = [float(p) for p in peaks4]
    db["rods"]["4"]["pattern"] = "E"
    db["rods"]["4"]["enrolled"] = True
    db["rods"]["4"]["hw_enrolled"] = True
    db["rods"]["4"]["putty_config"] = {
        "positions_mm": [15, 63],
        "positions_frac": [0.10, 0.42],
        "n_pellets": 2,
        "previous_pattern": "D",
        "previous_positions_mm": [30, 120],
    }

    with open(USERS, "w") as f:
        json.dump(db, f, indent=2)
    print(f"\n  ✓ Rod 4 re-enrolled as pattern E")
    print(f"  New peaks: {[round(p, 1) for p in peaks4[:10]]}")

    # Compare old vs new
    print(f"\n  Comparison (old D → new E):")
    for i in range(10):
        of = old_peaks[i] if i < len(old_peaks) else 0
        nf = peaks4[i]
        if of > 0 and nf > 0:
            shift = (nf - of) / of * 100
            print(f"    f{i+1:2d}: {of:8.1f} → {nf:8.1f} Hz  ({shift:+.1f}%)")
        elif nf > 0:
            print(f"    f{i+1:2d}:     new → {nf:8.1f} Hz")

    # Check uniqueness vs other rods
    other_peaks = []
    for rid in ["1", "2", "3"]:
        other_peaks.extend(db["rods"][rid]["perturbed_hz"][:10])

    n_unique = 0
    for p in peaks4[:10]:
        if p <= 0:
            continue
        is_unique = all(abs(p - op) / p > 0.05 for op in other_peaks if op > 0)
        if is_unique:
            n_unique += 1
    print(f"\n  Unique peaks (>5% from Rods 1-3): {n_unique}/10")
    print(f"  Previous (pattern D): 1/10")

    # ── Step 2: Verify all 4 rods on Ch A ────────────────────────────
    print("\n─── STEP 2: VERIFY ALL RODS ON Ch A ───")
    print("  I'll capture a tap from each rod to confirm Ch A sees them.")
    print("  Wait 3 seconds between rods.")

    rod_snrs = {}
    rod_peaks_found = {}
    for rid in ["1", "2", "3", "4"]:
        input(f"\n  Press Enter, then flick Rod {rid}...")
        try:
            freq, mag, bin_hz, peaks = tap_capture(f"Rod {rid}")
            min_bin = int(500 / bin_hz)
            noise = np.median(mag[min_bin:])
            peak_idx = min_bin + np.argmax(mag[min_bin:])
            snr = mag[peak_idx] / noise
            rod_snrs[rid] = snr
            rod_peaks_found[rid] = len(peaks)
        except RuntimeError as e:
            print(f"  ✗ Rod {rid}: {e}")
            rod_snrs[rid] = 0
            rod_peaks_found[rid] = 0

    print("\n─── VERIFICATION SUMMARY ───")
    print(f"  {'Rod':>5} {'SNR':>8} {'dB':>6} {'Peaks':>6} {'Status'}")
    print(f"  {'---':>5} {'---':>8} {'--':>6} {'-----':>6} {'------'}")
    all_ok = True
    for rid in ["1", "2", "3", "4"]:
        snr = rod_snrs[rid]
        db_val = 20 * np.log10(max(snr, 1))
        n_peaks = rod_peaks_found[rid]
        ok = snr > 10 and n_peaks >= 5
        status = "✓ OK" if ok else "✗ WEAK"
        if not ok:
            all_ok = False
        print(f"  Rod {rid:>1} {snr:>8.0f}x {db_val:>5.0f} {n_peaks:>6} {status}")

    if all_ok:
        print("\n  ✓ All 4 rods visible on Ch A — ready for stepped-dwell test")
    else:
        print("\n  ⚠ Some rods weak — check PZT connections before proceeding")

    return all_ok


if __name__ == "__main__":
    main()
