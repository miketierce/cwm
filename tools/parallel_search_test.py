#!/usr/bin/env python3
"""
Parallel search diagnostic — two-PZT topology.

Wiring:
  AWG OUT → Drive PZTs (all rods in parallel, one PZT on each rod end)
  Ch A    → Sense PZTs (all rods in parallel, second PZT on opposite end)

Tests:
  1. Baseline noise (AWG off) — verify sense PZTs are quiet
  2. Broadband sweep — excite all rods, see aggregate response
  3. Per-rod scoring — score the aggregate response against each enrolled rod
  4. Single-freq probe — drive at one rod's known peak, confirm it dominates

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python3 tools/parallel_search_test.py
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.cwm_picoscope import (
    check_hardware,
    capture_awg_driven,
    score_spectrum_against_rod,
    parallel_search,
    _capture_and_fft,
    SAMPLE_RATE,
    N_SAMPLES,
    VOLTAGE_RANGE_MV,
)

DATA_DIR = Path("data/results/lab")


def load_enrolled_rods():
    """Load enrolled rod data from users.json."""
    users_path = DATA_DIR / "users.json"
    if not users_path.exists():
        print("ERROR: No users.json found. Enroll rods first.")
        sys.exit(1)
    db = json.loads(users_path.read_text())
    rods = {}
    for rod_key, rod_info in db.get("rods", {}).items():
        if rod_info.get("enrolled"):
            rods[rod_key] = rod_info
    if not rods:
        print("ERROR: No enrolled rods found.")
        sys.exit(1)
    return rods


def test_baseline_noise():
    """Test 1: Capture with NO AWG — just sense PZT noise floor."""
    print("\n" + "=" * 60)
    print("TEST 1: Baseline noise (no AWG, no tap)")
    print("  Leave rods untouched. This measures the sense PZT noise floor.")
    print("=" * 60)
    input("  Press Enter when ready...")

    # Use tap capture with very short timeout to just grab noise
    # (will auto-trigger after timeout)
    try:
        freq_axis, magnitude, bin_hz = _capture_and_fft()
    except RuntimeError:
        print("  Timeout (expected) — capturing noise anyway")
        # If _capture_and_fft raises on timeout, we need a different approach
        # Use AWG-driven capture with AWG off (just noise)
        freq_axis, magnitude, bin_hz = capture_awg_driven(
            awg_mode="sine", awg_freq_hz=0.1, n_averages=1,
        )

    noise_floor = np.median(magnitude)
    peak = np.max(magnitude)
    rms_mv = np.sqrt(np.mean((magnitude / 32767 * VOLTAGE_RANGE_MV) ** 2))

    print(f"\n  Noise floor (median):  {noise_floor:.0f} ADC counts")
    print(f"  Peak magnitude:        {peak:.0f} ADC counts")
    print(f"  Peak/noise ratio:      {peak/noise_floor:.1f}×")
    print(f"  Estimated RMS:         {rms_mv:.2f} mV")

    # Find any peaks above 5× noise
    from scipy.signal import find_peaks as _find_peaks
    peaks, _ = _find_peaks(magnitude, height=noise_floor * 5, distance=10)
    if len(peaks) > 0:
        print(f"\n  ⚠️  {len(peaks)} peaks above 5× noise:")
        for p in peaks[:5]:
            print(f"      {freq_axis[p]:8.1f} Hz  SNR {magnitude[p]/noise_floor:.1f}×")
    else:
        print(f"\n  ✅ Clean noise floor — no spurious peaks")

    return noise_floor


def test_broadband_sweep(enrolled_rods):
    """Test 2: Broadband sweep — excite all rods, measure aggregate."""
    print("\n" + "=" * 60)
    print("TEST 2: Broadband sweep (AWG 1–100 kHz chirp)")
    print("  All rods should resonate. Ch A sees the aggregate response.")
    print("=" * 60)
    input("  Press Enter when ready...")

    freq_axis, magnitude, bin_hz = capture_awg_driven(
        awg_mode="sweep",
        awg_start_hz=1000.0,
        awg_stop_hz=100000.0,
        n_averages=4,
    )

    noise_floor = np.median(magnitude)
    print(f"\n  Noise floor: {noise_floor:.0f}")

    from scipy.signal import find_peaks as _find_peaks
    min_dist = max(1, int(200 / bin_hz))
    peaks, _ = _find_peaks(
        magnitude, height=noise_floor * 5, distance=min_dist
    )
    peaks = peaks[freq_axis[peaks] >= 500]  # ignore hum

    if len(peaks) == 0:
        print("\n  ❌ No peaks detected above noise floor!")
        print("     Check wiring: AWG→Drive PZTs, Ch A→Sense PZTs")
        return freq_axis, magnitude, bin_hz

    heights = magnitude[peaks]
    top = np.argsort(heights)[::-1][:20]

    print(f"\n  Found {len(peaks)} peaks above 5× noise. Top 20:")
    print(f"  {'Freq Hz':>10}  {'SNR':>8}  {'Match?':>8}")
    print(f"  {'-'*30}")

    for idx in top:
        p = peaks[idx]
        f_hz = freq_axis[p]
        snr = magnitude[p] / noise_floor

        # Check if this peak matches any enrolled rod
        match_rod = ""
        for rod_key, rod_info in enrolled_rods.items():
            for ef in rod_info.get("perturbed_hz", []):
                if ef > 0 and abs(f_hz - ef) / ef < 0.05:
                    match_rod = rod_key
                    break
            if match_rod:
                break

        print(f"  {f_hz:10.1f}  {snr:8.1f}×  {match_rod:>8}")

    pk_pk_mv = (np.max(magnitude) - np.min(magnitude)) / 32767 * VOLTAGE_RANGE_MV
    print(f"\n  Response pk-pk: ~{pk_pk_mv:.1f} mV")

    return freq_axis, magnitude, bin_hz


def test_per_rod_scoring(freq_axis, magnitude, bin_hz, enrolled_rods):
    """Test 3: Score the broadband response against each enrolled rod."""
    print("\n" + "=" * 60)
    print("TEST 3: Per-rod scoring (which rod resonates strongest?)")
    print("=" * 60)

    results = []
    for rod_key, rod_info in enrolled_rods.items():
        score = score_spectrum_against_rod(
            freq_axis, magnitude, bin_hz,
            rod_info["perturbed_hz"], n_modes=10,
        )
        results.append({"rod": rod_key, **score})
        print(f"  {rod_key}: matched {score['n_matched']}/{score['n_total']}  "
              f"RMS {score['rms']*100:.2f}%  score {score['score']*100:.1f}%")

    results.sort(key=lambda r: r["score"])
    winner = results[0]
    print(f"\n  🏆 Best match: {winner['rod']} at {winner['score']*100:.1f}%")

    if len(results) > 1:
        margin = (results[1]["score"] - results[0]["score"]) / results[0]["score"] * 100
        print(f"     Margin to 2nd: {margin:.0f}%")


def test_parallel_search_api(enrolled_rods):
    """Test 4: Full parallel_search() API call."""
    print("\n" + "=" * 60)
    print("TEST 4: parallel_search() API — broadband sweep")
    print("=" * 60)
    input("  Press Enter when ready...")

    t0 = time.time()
    result = parallel_search(
        enrolled_rods, n_modes=10,
        awg_mode="sweep",
        awg_start_hz=1000.0,
        awg_stop_hz=100000.0,
    )
    elapsed_ms = (time.time() - t0) * 1000

    print(f"\n  Tested {result['n_rods_tested']} rods in {elapsed_ms:.0f} ms")
    print(f"\n  {'Rod':>8}  {'Matched':>8}  {'RMS %':>8}  {'Score %':>8}")
    print(f"  {'-'*36}")

    for r in result["ranked"]:
        print(f"  {r['rod_id']:>8}  {r['n_matched']}/{r['n_total']:>3}    "
              f"{r['rms']*100:7.2f}  {r['score']*100:7.1f}")

    w = result["winner"]
    if w:
        print(f"\n  🏆 Winner: {w['rod_id']}  "
              f"({w['n_matched']}/{w['n_total']} peaks, "
              f"{w['score']*100:.1f}% score)")
    else:
        print("\n  ❌ No winner — all rods failed to match")

    return result


def test_single_freq_probe(enrolled_rods):
    """Test 5: Drive at one rod's known peak frequency."""
    print("\n" + "=" * 60)
    print("TEST 5: Single-frequency probe")
    print("=" * 60)

    # Pick Rod 1's strongest peak (first non-zero entry)
    rod_1 = enrolled_rods.get("1", enrolled_rods.get("rod_1", {}))
    if not rod_1:
        rod_key = list(enrolled_rods.keys())[0]
        rod_1 = enrolled_rods[rod_key]
        print(f"  Using {rod_key}")
    else:
        rod_key = "1"

    peaks = [f for f in rod_1.get("perturbed_hz", []) if f > 0]
    if not peaks:
        print("  No peaks for this rod!")
        return

    # Pick the 2nd peak (skip lowest which is often weak)
    probe_freq = peaks[min(1, len(peaks) - 1)]
    print(f"  Driving at {probe_freq:.1f} Hz ({rod_key}'s peak)")
    input("  Press Enter when ready...")

    freq_axis, magnitude, bin_hz = capture_awg_driven(
        awg_mode="sine",
        awg_freq_hz=probe_freq,
        n_averages=4,
    )

    noise_floor = np.median(magnitude)

    # Check response at the probe frequency
    idx = np.argmin(np.abs(freq_axis - probe_freq))
    window = 5
    local_peak = np.max(magnitude[max(0, idx - window):idx + window])
    snr = local_peak / noise_floor

    print(f"\n  Response at {probe_freq:.1f} Hz: SNR {snr:.1f}×")

    # Check harmonics
    for harmonic in [2, 3]:
        h_freq = probe_freq * harmonic
        if h_freq < freq_axis[-1]:
            h_idx = np.argmin(np.abs(freq_axis - h_freq))
            h_peak = np.max(magnitude[max(0, h_idx - window):h_idx + window])
            h_snr = h_peak / noise_floor
            print(f"  Harmonic {harmonic}× ({h_freq:.0f} Hz): SNR {h_snr:.1f}×")

    # Now score all rods on this single-freq response
    print(f"\n  Scoring all rods on single-freq response:")
    for rk, ri in enrolled_rods.items():
        score = score_spectrum_against_rod(
            freq_axis, magnitude, bin_hz,
            ri["perturbed_hz"], n_modes=10,
        )
        marker = " ← DRIVEN" if rk in (rod_key, "rod_" + rod_key) else ""
        print(f"    {rk}: {score['n_matched']}/{score['n_total']} matched, "
              f"score {score['score']*100:.1f}%{marker}")


def main():
    print("╔══════════════════════════════════════════════════╗")
    print("║  CWM Parallel Search Diagnostic (Two-PZT Mode)  ║")
    print("╠══════════════════════════════════════════════════╣")
    print("║  Wiring:                                        ║")
    print("║    AWG OUT → Drive PZTs (all rods, near end)    ║")
    print("║    Ch A    → Sense PZTs (all rods, far end)     ║")
    print("║                                                  ║")
    print("║  Each rod has 2 PZTs on opposite ends.          ║")
    print("║  Drive PZTs wired in parallel to AWG.           ║")
    print("║  Sense PZTs wired in parallel to Ch A.          ║")
    print("╚══════════════════════════════════════════════════╝")

    if not check_hardware():
        print("\nERROR: No PicoScope detected. Check USB connection.")
        sys.exit(1)
    print("\n✅ PicoScope connected")

    enrolled_rods = load_enrolled_rods()
    n_rods = len(enrolled_rods)
    print(f"✅ {n_rods} rods enrolled")
    for rk, ri in enrolled_rods.items():
        hz = [f for f in ri.get("perturbed_hz", []) if f > 0]
        print(f"   {rk}: {len(hz)} peaks, {min(hz):.0f}–{max(hz):.0f} Hz")

    # Test 1: Baseline noise
    noise = test_baseline_noise()

    # Test 2: Broadband sweep
    freq_axis, magnitude, bin_hz = test_broadband_sweep(enrolled_rods)

    # Test 3: Score per rod
    test_per_rod_scoring(freq_axis, magnitude, bin_hz, enrolled_rods)

    # Test 4: Full API
    result = test_parallel_search_api(enrolled_rods)

    # Test 5: Single-freq probe
    test_single_freq_probe(enrolled_rods)

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)
    print("\nKey questions answered:")
    print("  1. Can the sense PZTs detect acoustic energy from the drive PZTs?")
    print("  2. Does the aggregate response contain rod-specific peaks?")
    print("  3. Can we score the response to identify individual rods?")
    print("  4. Does driving at one rod's frequency make that rod dominate?")


if __name__ == "__main__":
    main()
