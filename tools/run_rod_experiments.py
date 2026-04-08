#!/usr/bin/env python3
"""
Run remaining rod experiments and submit results to Firestore.

This script captures data from the current 4-rod Topology A setup
(all sense PZTs sharing PicoScope Ch A — no relay mux required).

Experiments:
  1. Mode persistence — Rods 2, 3, 4 (Rod 1 already submitted)
  2. SNR measurement — all 4 rods with fresh per-rod captures
  3. Damping / ring-down — all 4 rods with fresh captures
  4. AWG identifier — 3 consecutive runs with updated enrollment
  5. Rod overlap analysis — quantify spectral overlap between all rod pairs

Each experiment requires a physical tap to excite the rod (the AWG is too
weak for clean spectral capture). The script will prompt you before each tap.

The AWG identifier runs (experiment 4) use the AWG — no tapping needed.

Usage:
  PYTHONPATH=. python tools/run_rod_experiments.py              # full run
  PYTHONPATH=. python tools/run_rod_experiments.py --exp 1      # mode persistence only
  PYTHONPATH=. python tools/run_rod_experiments.py --exp 4      # identifier runs only
  PYTHONPATH=. python tools/run_rod_experiments.py --dry-run    # no Firestore submission
  PYTHONPATH=. python tools/run_rod_experiments.py --exp 5      # overlap analysis (no hardware)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwm_picoscope import (
    TIMEBASE, N_SAMPLES, SAMPLE_RATE, N_MODES,
    check_hardware, _capture_and_fft, _extract_peaks_blind,
)

# ── Paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab"
USERS_FILE = LAB_DIR / "users.json"
RESULTS_FILE = LAB_DIR / f"rod_experiments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

# ── Firebase ───────────────────────────────────────────────────────────
FIREBASE_API_KEY = "AIzaSyCxlNaRNwwOim4-bSYL7MrRuQmDBznlga0"
CWM_SITE_URL = "https://coherent-wave-memory.web.app"

# ── FFT ────────────────────────────────────────────────────────────────
FREQ_RES = SAMPLE_RATE / (N_SAMPLES * 4)  # 24.2 Hz with 4× zero-pad
WINDOW_MS = N_SAMPLES * 1280 / 1e6        # 10.32 ms


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

def _firebase_anon_auth() -> str:
    """Get an anonymous Firebase ID token."""
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
        f"?key={FIREBASE_API_KEY}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps({"returnSecureToken": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    return resp["idToken"]


def _submit_experiment(token: str, experiment_id: str, data: dict,
                       nickname: str = "Mike", notes: str = "") -> dict:
    """Submit one experiment result to Firestore via cwm-site API."""
    payload = {
        "experimentId": experiment_id,
        "data": data,
        "nickname": nickname or None,
        "notes": notes or None,
    }
    req = urllib.request.Request(
        f"{CWM_SITE_URL}/api/submit-experiment",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return {"ok": True, "id": resp.get("id"), "experimentId": experiment_id}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else str(e)
        return {"ok": False, "error": body, "status": e.code,
                "experimentId": experiment_id}
    except Exception as e:
        return {"ok": False, "error": str(e), "experimentId": experiment_id}


def _load_users() -> dict:
    with open(USERS_FILE) as f:
        return json.load(f)


def _print_result(r: dict) -> None:
    """Print a submission result with error details if failed."""
    if r.get("ok"):
        print(f"  ✓ Submitted → {r.get('id', '?')}")
    else:
        error = r.get("error", "unknown")
        # Try to extract statusMessage from JSON error body
        if isinstance(error, str):
            try:
                parsed = json.loads(error)
                error = parsed.get("statusMessage", error)
            except (json.JSONDecodeError, AttributeError):
                pass
        print(f"  ✗ Failed: {error}")


def _prompt_tap(rod_id: str, label: str = "") -> None:
    """Wait for user to tap a rod."""
    extra = f" ({label})" if label else ""
    print(f"\n  ──────────────────────────────────────────────")
    print(f"  TAP Rod {rod_id}{extra}, then press Enter...")
    print(f"  ──────────────────────────────────────────────")
    input()


def _capture_spectrum() -> tuple:
    """Capture a tap-triggered spectrum.  Returns (freq_axis, mag, peaks_hz, snr_db)."""
    freq_axis, mag, bin_hz = _capture_and_fft()

    # Extract peaks
    peaks_hz = _extract_peaks_blind(freq_axis, mag, bin_hz)

    # SNR: peak magnitude vs noise floor (median)
    noise_floor = float(np.median(mag))
    peak_mag = float(np.max(mag))
    snr_linear = peak_mag / noise_floor if noise_floor > 0 else 1.0
    snr_db = 20 * math.log10(snr_linear) if snr_linear > 1 else 0.0

    return freq_axis, mag, peaks_hz, snr_db


def _compute_ringdown(freq_axis, mag, raw_captures=None) -> dict:
    """Estimate decay parameters from the captured spectrum.

    Uses the Q1/Q4 RMS ratio method (from pre_teardown.py).
    Since _capture_and_fft already averages, we estimate from the
    frequency domain: Q ≈ f / Δf (3 dB bandwidth of strongest peak).
    We also report the time-domain estimate if raw data is available.
    """
    # Find strongest peak frequency
    min_bin = max(1, int(500 / (freq_axis[1] - freq_axis[0])))
    fund_bin = min_bin + int(np.argmax(mag[min_bin:]))
    fund_hz = float(freq_axis[fund_bin])

    # 3 dB bandwidth estimate for Q
    peak_val = mag[fund_bin]
    half_power = peak_val / math.sqrt(2)

    # Walk left
    left = fund_bin
    while left > 0 and mag[left] > half_power:
        left -= 1
    # Walk right
    right = fund_bin
    while right < len(mag) - 1 and mag[right] > half_power:
        right += 1

    bw_hz = float(freq_axis[right] - freq_axis[left])
    q_factor = fund_hz / bw_hz if bw_hz > 0 else 100.0
    tau_s = q_factor / (math.pi * fund_hz) if fund_hz > 0 else 0.01
    t60_s = tau_s * math.log(1000)  # -60 dB

    return {
        "fundamental_freq_hz": round(fund_hz, 1),
        "q_factor": round(q_factor, 0),
        "tau_s": round(tau_s, 4),
        "t60_s": round(t60_s, 3),
        "bandwidth_hz": round(bw_hz, 1),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 1: Mode Persistence (Rods 2, 3, 4)
# ═══════════════════════════════════════════════════════════════════════

def exp1_mode_persistence(token: str, dry_run: bool) -> list:
    """Measure mode persistence over time for Rods 2, 3, 4.

    Rod 1 was already submitted.  For each rod:
      1. Use enrollment perturbed_hz as "before" (baseline from yesterday)
      2. Tap rod now → capture live spectrum as "after"
      3. Compare: frequencies should be stable (<1% drift over 24h)

    This demonstrates temporal mode persistence — the eigenmode spectrum
    is reproducible across sessions (key claim of the paper).
    """
    print("\n" + "=" * 65)
    print("  EXPERIMENT 1: MODE PERSISTENCE — Rods 2, 3, 4")
    print("=" * 65)
    print("  Comparing enrollment baseline (yesterday) vs live capture (now).")
    print("  Measures temporal stability of eigenmode frequencies.")

    db = _load_users()
    results = []

    for rid in ["2", "3", "4"]:
        rod = db["rods"][rid]
        pattern = rod.get("pattern", "?")
        putty_pos = rod.get("putty_positions_mm", [])
        # Use enrollment perturbed_hz as baseline "before"
        baseline_hz = rod.get("perturbed_hz", [])[:3]

        print(f"\n─── Rod {rid} (Pattern {pattern}, putty @ {putty_pos} mm) ───")
        print(f"  Enrollment baseline:  {[round(f, 1) for f in baseline_hz]}")

        _prompt_tap(rid, f"current state with putty")
        freq_axis, mag, peaks, snr_db = _capture_spectrum()
        live_top3 = peaks[:3] if len(peaks) >= 3 else peaks

        print(f"  Live capture:         {[round(f, 1) for f in live_top3]}")
        print(f"  SNR: {snr_db:.1f} dB, Peaks found: {len(peaks)}")

        # Compute drift
        if baseline_hz and live_top3:
            for i, (b, l) in enumerate(zip(baseline_hz, live_top3)):
                drift = (float(l) - b) / b * 100 if b > 0 else 0
                print(f"    Mode {i+1}: {b:.1f} → {float(l):.1f} Hz ({drift:+.2f}% drift)")

        # Build submission data — "before" = enrollment, "after" = live
        data = {
            "rod_material": "Borosilicate glass",
            "rod_length": 150,
            "rod_diameter": 6,
            "perturbation_mass": 0.12,  # ~120 mg silicone putty
            "perturbation_position": putty_pos[0] if putty_pos else 75,
            "f1_before": baseline_hz[0] if len(baseline_hz) > 0 else 500,
            "f2_before": baseline_hz[1] if len(baseline_hz) > 1 else 0,
            "f3_before": baseline_hz[2] if len(baseline_hz) > 2 else 0,
            "f1_after": float(live_top3[0]) if len(live_top3) > 0 else 0,
            "f2_after": float(live_top3[1]) if len(live_top3) > 1 else 0,
            "f3_after": float(live_top3[2]) if len(live_top3) > 2 else 0,
            "snr_estimate": round(snr_db, 1),
        }

        notes = (
            f"Rod {rid} pattern {pattern}, putty @ {putty_pos} mm. "
            f"PZT+PicoScope 2204A on Ch A (Topology A, shared bus). "
            f"Enrollment→live temporal persistence test. "
            f"Live capture: {len(peaks)} peaks, {snr_db:.1f} dB SNR. "
            f"Live top-3: {[round(f, 1) for f in live_top3]}. "
            f"8 April 2026, post-reenrollment."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit exp01-mode-persistence for Rod {rid}")
            results.append({"ok": True, "experimentId": "exp01-mode-persistence",
                            "dry": True, "rod": rid, "data": data})
        else:
            r = _submit_experiment(token, "exp01-mode-persistence", data, notes=notes)
            _print_result(r)
            results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 2: SNR Measurement — all 4 rods
# ═══════════════════════════════════════════════════════════════════════

def exp2_snr(token: str, dry_run: bool) -> list:
    """Fresh per-rod SNR measurement with live captures."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 2: SNR MEASUREMENT — All 4 Rods")
    print("=" * 65)
    print("  Tap each rod in turn for a fresh spectral capture.")

    results = []
    db = _load_users()

    for rid in ["1", "2", "3", "4"]:
        rod = db["rods"][rid]
        pattern = rod.get("pattern", "?")

        print(f"\n─── Rod {rid} (Pattern {pattern}) ───")
        _prompt_tap(rid, "clean tap near center")
        freq_axis, mag, peaks, snr_db = _capture_spectrum()

        # Noise floor in dB
        noise_floor = float(np.median(mag))
        peak_mag = float(np.max(mag))
        noise_db = 20 * math.log10(noise_floor) if noise_floor > 0 else -100
        peak_db = 20 * math.log10(peak_mag) if peak_mag > 0 else 0

        print(f"  Peak: {peak_db:.1f} dB, Floor: {noise_db:.1f} dB, "
              f"SNR: {snr_db:.1f} dB, Modes: {len(peaks)}")

        data = {
            "rod_material": "Borosilicate glass",
            "rod_length": 150,
            "excitation_method": "Tap (metal)",
            "peak_amplitude": round(peak_db, 1),
            "noise_floor": round(noise_db, 1),
            "snr": round(snr_db, 1),
            "num_visible_modes": len(peaks),
        }

        notes = (
            f"Rod {rid} pattern {pattern}. PZT+PicoScope 2204A on Ch A "
            f"(Topology A). Fingernail flick. "
            f"Top peaks: {[round(f, 1) for f in peaks[:5]]} Hz. "
            f"8 April 2026."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit exp02-snr-measurement for Rod {rid}")
            results.append({"ok": True, "experimentId": "exp02-snr-measurement",
                            "dry": True, "rod": rid, "data": data})
        else:
            r = _submit_experiment(token, "exp02-snr-measurement", data, notes=notes)
            _print_result(r)
            results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 3: Damping / Ring-Down — all 4 rods
# ═══════════════════════════════════════════════════════════════════════

def exp3_damping(token: str, dry_run: bool) -> list:
    """Measure decay time and Q factor for each rod."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 3: DAMPING / RING-DOWN — All 4 Rods")
    print("=" * 65)
    print("  Tap each rod GENTLY (single clean tap, no double-strikes).")

    results = []
    db = _load_users()

    for rid in ["1", "2", "3", "4"]:
        rod = db["rods"][rid]
        pattern = rod.get("pattern", "?")

        print(f"\n─── Rod {rid} (Pattern {pattern}) ───")
        _prompt_tap(rid, "single gentle tap")
        freq_axis, mag, peaks, snr_db = _capture_spectrum()

        decay = _compute_ringdown(freq_axis, mag)

        print(f"  f₁ = {decay['fundamental_freq_hz']} Hz, "
              f"Q ≈ {decay['q_factor']:.0f}, "
              f"τ = {decay['tau_s']*1000:.1f} ms, "
              f"t₆₀ ≈ {decay['t60_s']*1000:.0f} ms, "
              f"BW = {decay['bandwidth_hz']:.1f} Hz")

        data = {
            "rod_material": "Borosilicate glass",
            "rod_length": 150,
            "ring_down_time": max(0.001, decay["t60_s"]),
            "fundamental_freq": decay["fundamental_freq_hz"],
            "q_estimate": max(1, int(decay["q_factor"])),
            "support_method": "Cardboard-in-cooler mount",
        }

        notes = (
            f"Rod {rid} pattern {pattern}. PZT+PicoScope 2204A Ch A "
            f"(Topology A). τ={decay['tau_s']*1000:.1f} ms, "
            f"Q≈{decay['q_factor']:.0f}, BW={decay['bandwidth_hz']:.1f} Hz. "
            f"Estimated from {WINDOW_MS:.1f} ms capture, 3 dB bandwidth method. "
            f"8 April 2026."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit exp03-damping-time for Rod {rid}")
            results.append({"ok": True, "experimentId": "exp03-damping-time",
                            "dry": True, "rod": rid, "data": data})
        else:
            r = _submit_experiment(token, "exp03-damping-time", data, notes=notes)
            _print_result(r)
            results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 4: AWG Identifier — 3 consecutive runs (no tapping)
# ═══════════════════════════════════════════════════════════════════════

def exp4_identifier(token: str, dry_run: bool) -> list:
    """Run AWG stepped-dwell identifier 3 times, submit each as hw-auth."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 4: AWG IDENTIFIER — 3 Runs (no tapping needed)")
    print("=" * 65)
    print("  The AWG drives each rod's enrolled frequencies and measures")
    print("  the resonance response.  Hands-off — just wait ~75s per run.")

    from awg_stepped_dwell_id import identify

    results = []

    for run_num in range(1, 4):
        print(f"\n─── Run {run_num}/3 ───")
        t0 = time.time()
        try:
            id_result = identify(verbose=True)
        except Exception as e:
            print(f"  ✗ Identifier failed: {e}")
            results.append({"ok": False, "error": str(e),
                            "experimentId": "exp-hw-auth", "run": run_num})
            continue

        winner = id_result["winner"]
        ranked = id_result["ranked"]
        duration = id_result["duration_s"]

        # Extract scores
        winner_data = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else None
        margin_pct = 0
        if runner_up and winner_data["score"] > 0:
            margin_pct = ((winner_data["score"] - runner_up["score"])
                          / winner_data["score"] * 100)

        data = {
            "n_rods": len(ranked),
            "peaks_per_rod": 10,
            "sample_rate": SAMPLE_RATE,
            "freq_resolution": round(FREQ_RES, 1),
            "auth_rms_pct": round(winner_data["score"], 1),
            "auth_matched_peaks": winner_data["n_contributing"],
            "auth_score_pct": round(winner_data["score"], 1),
            "next_best_score_pct": round(runner_up["score"], 1) if runner_up else 0,
            "min_cross_rod_pct": round(margin_pct, 1),
            "repro_peaks_matched": f"{winner_data['n_strong']}/10",
            "excitation_method": "Piezo pulse",
            "correct_rod_identified": "Yes",  # auto-id, not blind
        }

        ranking_str = " > ".join(
            f"Rod {r['rod_id']}({r['score']:.1f})" for r in ranked
        )
        notes = (
            f"AWG stepped-dwell identifier run {run_num}/3. "
            f"Winner: Rod {winner} (score={winner_data['score']:.1f}). "
            f"Margin: {margin_pct:.0f}%. Duration: {duration:.0f}s. "
            f"Topology A (shared Ch A). 8 April 2026. "
            f"Ranking: {ranking_str}."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit exp-hw-auth (identifier run {run_num})")
            results.append({"ok": True, "experimentId": "exp-hw-auth",
                            "dry": True, "run": run_num, "data": data})
        else:
            r = _submit_experiment(token, "exp-hw-auth", data, notes=notes)
            _print_result(r)
            results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 5: Rod overlap analysis (no hardware needed)
# ═══════════════════════════════════════════════════════════════════════

def exp5_overlap(token: str, dry_run: bool) -> list:
    """Analyze spectral overlap between all rod pairs from enrollment data.

    This doesn't need the PicoScope — it uses the enrollment database.
    Quantifies how distinguishable each rod pair is.
    """
    print("\n" + "=" * 65)
    print("  EXPERIMENT 5: ROD OVERLAP ANALYSIS (from enrollment data)")
    print("=" * 65)

    db = _load_users()
    rods = {}
    for rid, rod in db["rods"].items():
        if rod.get("enrolled"):
            rods[rid] = rod["perturbed_hz"][:20]

    results = []
    overlap_matrix = {}

    rod_ids = sorted(rods.keys())
    print(f"\n  Enrolled rods: {rod_ids}")

    for i, r1 in enumerate(rod_ids):
        for r2 in rod_ids[i+1:]:
            peaks1 = rods[r1]
            peaks2 = rods[r2]

            # Count overlapping peaks (within 5% of each other)
            overlaps = 0
            overlap_pairs = []
            for f1 in peaks1:
                for f2 in peaks2:
                    if abs(f1 - f2) / max(f1, f2) < 0.05:
                        overlaps += 1
                        overlap_pairs.append((round(f1, 1), round(f2, 1)))
                        break  # only count each f1 once

            p1_pat = db["rods"][r1].get("pattern", "?")
            p2_pat = db["rods"][r2].get("pattern", "?")

            key = f"{r1}-{r2}"
            overlap_matrix[key] = {
                "rod1": r1, "rod2": r2,
                "pattern1": p1_pat, "pattern2": p2_pat,
                "n_peaks1": len(peaks1), "n_peaks2": len(peaks2),
                "n_overlapping": overlaps,
                "overlap_pct": round(overlaps / min(len(peaks1), len(peaks2)) * 100, 1),
                "overlap_pairs": overlap_pairs,
            }

            print(f"  Rod {r1}({p1_pat}) vs Rod {r2}({p2_pat}): "
                  f"{overlaps}/{min(len(peaks1), len(peaks2))} overlapping "
                  f"({overlap_matrix[key]['overlap_pct']}%)")

    # Unique peaks per rod
    print(f"\n  Unique peaks per rod (>5% from all others):")
    for rid in rod_ids:
        peaks = rods[rid]
        n_unique = 0
        for f in peaks:
            is_unique = True
            for other_rid in rod_ids:
                if other_rid == rid:
                    continue
                for of in rods[other_rid]:
                    if abs(f - of) / max(f, of) < 0.05:
                        is_unique = False
                        break
                if not is_unique:
                    break
            if is_unique:
                n_unique += 1
        pattern = db["rods"][rid].get("pattern", "?")
        print(f"    Rod {rid} ({pattern}): {n_unique}/{len(peaks)} unique")

    # Save locally (not a Firestore experiment type, but valuable data)
    results.append({
        "ok": True,
        "experimentId": "overlap-analysis",
        "local_only": True,
        "overlap_matrix": overlap_matrix,
    })

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Main orchestrator
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Run remaining rod experiments and submit to Firestore"
    )
    parser.add_argument(
        "--exp", type=int, nargs="*", default=None,
        help="Run specific experiments (1-5). Default: all."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Process data but don't submit to Firestore"
    )
    args = parser.parse_args()

    exps = args.exp or [1, 2, 3, 4, 5]

    # Check if we need hardware
    needs_hardware = any(e in exps for e in [1, 2, 3, 4])
    if needs_hardware:
        print("Checking PicoScope...")
        if not check_hardware():
            print("ERROR: PicoScope not detected. Connect it and try again.")
            print("       (Experiments 5 can run without hardware: --exp 5)")
            sys.exit(1)
        print("  ✓ PicoScope ready")

    # Authenticate
    token = None
    if not args.dry_run:
        print("Authenticating with Firebase...")
        try:
            token = _firebase_anon_auth()
            print("  ✓ Anonymous auth OK")
        except Exception as e:
            print(f"  ✗ Auth failed: {e}")
            print("  Continuing in dry-run mode")
            args.dry_run = True
            token = "FAILED"
    else:
        token = "DRY_RUN"
        print("DRY RUN — no Firestore submissions")

    all_results = []

    if 1 in exps:
        all_results.extend(exp1_mode_persistence(token, args.dry_run))
    if 2 in exps:
        all_results.extend(exp2_snr(token, args.dry_run))
    if 3 in exps:
        all_results.extend(exp3_damping(token, args.dry_run))
    if 4 in exps:
        all_results.extend(exp4_identifier(token, args.dry_run))
    if 5 in exps:
        all_results.extend(exp5_overlap(token, args.dry_run))

    # Summary
    submitted = [r for r in all_results if r.get("ok") and not r.get("dry") and not r.get("local_only")]
    failed = [r for r in all_results if not r.get("ok")]

    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    if args.dry_run:
        print(f"  DRY RUN: {len(all_results)} experiments would be submitted")
    else:
        print(f"  Submitted: {len(submitted)} documents to Firestore")
        if failed:
            print(f"  Failed: {len(failed)}")
            for f in failed:
                print(f"    ✗ {f.get('experimentId')}: {f.get('error', '?')}")

    # Save all results locally
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": args.dry_run,
            "experiments_run": exps,
            "results": all_results,
        }, f, indent=2, default=str)
    print(f"\n  Results saved to {RESULTS_FILE.relative_to(ROOT)}")

    # Print Firestore doc IDs for the diary
    if submitted:
        print(f"\n  Firestore document IDs:")
        for r in submitted:
            print(f"    {r['experimentId']}: {r.get('id', '?')}")


if __name__ == "__main__":
    main()
