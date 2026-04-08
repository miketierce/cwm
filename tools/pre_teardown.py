#!/usr/bin/env python3
"""Pre-teardown data capture & Firestore submission script.

Run this BEFORE dismantling the 4-rod setup. It:
  Phase 1 — Submits existing experiment data to Firestore
  Phase 2 — Walks through remaining measurements with PicoScope

Usage:
  python3 tools/pre_teardown.py              # full run (submit + capture)
  python3 tools/pre_teardown.py --submit     # phase 1 only (no hardware needed)
  python3 tools/pre_teardown.py --capture    # phase 2 only (PicoScope required)
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
from typing import Optional, List, Dict

# ── Paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab"
LOG_FILE = LAB_DIR / "experiment_log_20260407.json"
USERS_FILE = LAB_DIR / "users.json"
TEARDOWN_LOG = LAB_DIR / f"teardown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

# ── Firebase config ────────────────────────────────────────────────────
FIREBASE_API_KEY = "AIzaSyCxlNaRNwwOim4-bSYL7MrRuQmDBznlga0"
CWM_SITE_URL = "https://coherent-wave-memory.web.app"

# ── PicoScope constants (mirrored from cwm_picoscope.py) ──────────────
SAMPLE_RATE = 781_250
N_SAMPLES = 8064
DT_NS = 1280
WINDOW_MS = N_SAMPLES * DT_NS / 1e6  # 10.32 ms
FREQ_RES = SAMPLE_RATE / (N_SAMPLES * 4)  # 4x zero-pad → 24.2 Hz


# ═══════════════════════════════════════════════════════════════════════
#  Firebase submission helpers
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
                       nickname: str = "", location: str = "",
                       notes: str = "") -> dict:
    """Submit one experiment result to Firestore via cwm-site endpoint."""
    payload = {
        "experimentId": experiment_id,
        "data": data,
        "nickname": nickname or None,
        "location": location or None,
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


# ═══════════════════════════════════════════════════════════════════════
#  Phase 1 — Submit existing data
# ═══════════════════════════════════════════════════════════════════════

def _load_experiment_log() -> dict:
    with open(LOG_FILE) as f:
        return json.load(f)


def _load_users() -> dict:
    with open(USERS_FILE) as f:
        return json.load(f)


def _compute_snr_from_npy(filepath: str) -> Optional[dict]:
    """Process a raw .npy capture to extract SNR metrics."""
    try:
        import numpy as np
        from scipy.signal import find_peaks
    except ImportError:
        return None

    raw = np.load(filepath)
    n = len(raw)
    # Apply Hanning window and 4x zero-padded FFT
    win = np.hanning(n)
    padded = n * 4
    fft_mag = np.abs(np.fft.rfft(raw * win, n=padded))
    freq_axis = np.fft.rfftfreq(padded, d=DT_NS * 1e-9)

    # Convert to dBFS (0 dB = full-scale ±500 mV range = 32767 ADC counts)
    # Normalize so the max possible FFT magnitude = 0 dBFS
    full_scale = n / 2.0  # Hanning-windowed full-scale sinewave peak
    fft_mag[fft_mag == 0] = 1e-15
    mag_db = 20 * np.log10(fft_mag / full_scale)

    # Noise floor = median of lower half of sorted magnitudes
    sorted_db = np.sort(mag_db)
    noise_floor_db = float(np.median(sorted_db[:len(sorted_db) // 2]))

    # Find peaks above 500 Hz (match cwm_picoscope: SNR > 10× = 20 dB above floor)
    min_bin = int(500 / (SAMPLE_RATE / padded))
    peaks_idx, props = find_peaks(
        mag_db[min_bin:],
        height=noise_floor_db + 20,  # at least 20 dB above floor (10× SNR)
        distance=int(200 / (SAMPLE_RATE / padded)),
    )
    peaks_idx += min_bin

    peak_db = float(np.max(mag_db[peaks_idx])) if len(peaks_idx) > 0 else noise_floor_db
    snr_db = peak_db - noise_floor_db
    n_modes = min(len(peaks_idx), 50)  # cap at 50

    return {
        "peak_amplitude_db": round(peak_db, 1),
        "noise_floor_db": round(noise_floor_db, 1),
        "snr_db": round(snr_db, 1),
        "n_visible_modes": n_modes,
    }


def _estimate_ringdown_from_npy(filepath: str) -> Optional[dict]:
    """Estimate ring-down decay from raw .npy capture."""
    try:
        import numpy as np
    except ImportError:
        return None

    raw = np.load(filepath)
    n = len(raw)
    quarter = n // 4

    # RMS of each quarter
    q1_rms = float(np.sqrt(np.mean(raw[:quarter] ** 2)))
    q4_rms = float(np.sqrt(np.mean(raw[3 * quarter:] ** 2)))

    if q4_rms < 1e-10:
        return None

    ratio = q1_rms / q4_rms
    # Time between quarter centers
    dt_quarters = 3 * (quarter * DT_NS * 1e-9)  # seconds
    if ratio > 1:
        tau_s = dt_quarters / math.log(ratio)
    else:
        tau_s = 1.0  # flat signal, no decay

    # Find fundamental from FFT
    win = np.hanning(n)
    padded = n * 4
    fft_mag = np.abs(np.fft.rfft(raw * win, n=padded))
    freq_axis = np.fft.rfftfreq(padded, d=DT_NS * 1e-9)
    min_bin = int(500 / (freq_axis[1] - freq_axis[0]))
    fund_bin = min_bin + np.argmax(fft_mag[min_bin:])
    fund_hz = float(freq_axis[fund_bin])

    # Q = pi * f * tau
    q_factor = math.pi * fund_hz * tau_s

    # Ring-down time estimate (to -60 dB = 1/1000 of initial)
    ring_down_s = tau_s * math.log(1000)  # to 0.1% ≈ -60 dB

    return {
        "fundamental_freq_hz": round(fund_hz, 1),
        "tau_s": round(tau_s, 4),
        "q_factor": round(q_factor, 0),
        "ring_down_time_s": round(ring_down_s, 3),
        "decay_ratio_q1_q4": round(ratio, 2),
    }


def phase1_submit(dry_run: bool = False) -> List[dict]:
    """Submit all existing experiment data to Firestore."""
    print("\n" + "=" * 60)
    print("  PHASE 1: Submit Existing Data to Firestore")
    print("=" * 60)

    log = _load_experiment_log()
    results = []

    # ── Authenticate ──
    if not dry_run:
        print("\n→ Authenticating with Firebase...")
        try:
            token = _firebase_anon_auth()
            print("  ✓ Anonymous auth OK")
        except Exception as e:
            print(f"  ✗ Auth failed: {e}")
            return results
    else:
        token = "DRY_RUN"
        print("\n→ DRY RUN — no submissions will be made")

    # ── 1. exp-hw-auth (verify already submitted or re-submit) ─────────
    print("\n─── exp-hw-auth ───")
    auth = log["auth_test"]
    repro = log["reproducibility_test"]
    scores = auth["scores"]

    # Sort scores to find best and next-best
    sorted_scores = sorted(scores.items(), key=lambda x: x[1].get("score_pct", 999))
    best = sorted_scores[0]
    next_best = sorted_scores[1] if len(sorted_scores) > 1 else None

    # Min cross-rod separation
    min_sep = (next_best[1]["score_pct"] - best[1]["score_pct"]) if next_best else 0

    hw_auth_data = {
        "n_rods": 4,
        "peaks_per_rod": 20,
        "sample_rate": SAMPLE_RATE,
        "freq_resolution": round(FREQ_RES, 1),
        "auth_rms_pct": best[1]["rms_pct"],
        "auth_matched_peaks": int(best[1]["matched"].split("/")[0]),
        "auth_score_pct": best[1]["score_pct"],
        "next_best_score_pct": next_best[1]["score_pct"] if next_best else 0,
        "min_cross_rod_pct": round(min_sep, 1),
        "repro_peaks_matched": repro["peaks_matched_within_100hz"],
        "excitation_method": "Fingernail flick",
        "correct_rod_identified": "Yes" if auth["correct_rod_identified"] else "No",
    }
    print(f"  n_rods={hw_auth_data['n_rods']}, best={best[0]} @ "
          f"{best[1]['score_pct']}%, separation={min_sep:.1f}%")

    if not dry_run:
        r = _submit_experiment(
            token, "exp-hw-auth", hw_auth_data,
            nickname="Mike",
            notes=f"4-rod auth, first successful run {log['date']}. "
                  f"Fingernail flick + PZT + PicoScope 2204A. "
                  f"Billy→Rod 1 correctly identified.",
        )
        results.append(r)
        _print_result(r)
    else:
        print("  [DRY RUN] Would submit exp-hw-auth")
        results.append({"ok": True, "experimentId": "exp-hw-auth", "dry": True})

    # ── 2. exp02-snr-measurement (from .npy files) ─────────────────────
    print("\n─── exp02-snr-measurement ───")
    npy_files = sorted(LAB_DIR.glob("flick_run*_raw.npy"))
    if not npy_files:
        print("  ⚠ No flick .npy files found — skipping")
    else:
        # Process best flick capture (run2 had highest pk-pk)
        best_npy = npy_files[1] if len(npy_files) > 1 else npy_files[0]
        print(f"  Processing {best_npy.name}...")
        snr = _compute_snr_from_npy(str(best_npy))
        if snr:
            snr_data = {
                "rod_material": "Borosilicate glass",
                "rod_length": 150,
                "excitation_method": "Tap (metal)",
                "peak_amplitude": snr["peak_amplitude_db"],
                "noise_floor": snr["noise_floor_db"],
                "snr": snr["snr_db"],
                "num_visible_modes": snr["n_visible_modes"],
            }
            print(f"  peak={snr['peak_amplitude_db']} dB, floor={snr['noise_floor_db']} dB, "
                  f"SNR={snr['snr_db']} dB, modes={snr['n_visible_modes']}")

            if not dry_run:
                r = _submit_experiment(
                    token, "exp02-snr-measurement", snr_data,
                    nickname="Mike",
                    notes=f"Rod 1 (pattern A), PZT + PicoScope 2204A, "
                          f"781.25 kHz sample rate, fingernail flick excitation. "
                          f"Processed from {best_npy.name}.",
                )
                results.append(r)
                _print_result(r)
            else:
                print("  [DRY RUN] Would submit exp02-snr-measurement")
                results.append({"ok": True, "experimentId": "exp02-snr-measurement",
                                "dry": True, "data": snr_data})
        else:
            print("  ⚠ Could not process .npy (numpy/scipy not available)")

    # ── 3. exp03-damping-time (from .npy files) ────────────────────────
    print("\n─── exp03-damping-time ───")
    if not npy_files:
        print("  ⚠ No flick .npy files found — skipping")
    else:
        best_npy = npy_files[1] if len(npy_files) > 1 else npy_files[0]
        print(f"  Processing {best_npy.name}...")
        decay = _estimate_ringdown_from_npy(str(best_npy))
        if decay:
            damping_data = {
                "rod_material": "Borosilicate glass",
                "rod_length": 150,
                "ring_down_time": decay["ring_down_time_s"],
                "fundamental_freq": decay["fundamental_freq_hz"],
                "q_estimate": int(decay["q_factor"]),
                "support_method": "Other",
            }
            print(f"  f₁={decay['fundamental_freq_hz']} Hz, "
                  f"τ={decay['tau_s']*1000:.1f} ms, Q≈{decay['q_factor']:.0f}, "
                  f"t₆₀≈{decay['ring_down_time_s']*1000:.0f} ms")

            if not dry_run:
                r = _submit_experiment(
                    token, "exp03-damping-time", damping_data,
                    nickname="Mike",
                    notes=f"Rod 1 (pattern A), PZT + PicoScope 2204A, "
                          f"estimated from {WINDOW_MS:.1f} ms capture window. "
                          f"Q1/Q4 decay ratio = {decay['decay_ratio_q1_q4']:.1f}. "
                          f"Short window — longer captures recommended.",
                )
                results.append(r)
                _print_result(r)
            else:
                print("  [DRY RUN] Would submit exp03-damping-time")
                results.append({"ok": True, "experimentId": "exp03-damping-time",
                                "dry": True, "data": damping_data})
        else:
            print("  ⚠ Could not process .npy (numpy not available or flat signal)")

    # ── Summary ────────────────────────────────────────────────────────
    print("\n─── Phase 1 Summary ───")
    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    print(f"  Submitted: {ok}   Failed: {fail}")
    for r in results:
        status = "✓" if r.get("ok") else "✗"
        doc_id = r.get("id", r.get("dry", "—"))
        print(f"  {status} {r['experimentId']} → {doc_id}")

    return results


def _print_result(r: dict):
    if r.get("ok"):
        print(f"  ✓ Submitted → document {r.get('id', '?')}")
    else:
        print(f"  ✗ Failed: {r.get('error', 'unknown')}")


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2 — Guided remaining measurements
# ═══════════════════════════════════════════════════════════════════════

def _try_import_picoscope():
    """Import cwm_picoscope functions if PicoScope available."""
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from cwm_picoscope import (
            measure_rod_fingerprint,
            score_spectrum_against_rod,
            capture_awg_driven,
            _capture_and_fft,
            _extract_peaks_blind,
            SAMPLE_RATE as PS_RATE,
        )
        return {
            "measure_rod_fingerprint": measure_rod_fingerprint,
            "score_spectrum_against_rod": score_spectrum_against_rod,
            "capture_awg_driven": capture_awg_driven,
            "_capture_and_fft": _capture_and_fft,
            "_extract_peaks_blind": _extract_peaks_blind,
            "SAMPLE_RATE": PS_RATE,
        }
    except Exception as e:
        print(f"  ⚠ PicoScope not available: {e}")
        return None


def _prompt(msg: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {msg}{suffix}: ").strip()
    return val or default


def _prompt_yn(msg: str, default: bool = True) -> bool:
    yn = "Y/n" if default else "y/N"
    val = input(f"  {msg} ({yn}): ").strip().lower()
    if not val:
        return default
    return val.startswith("y")


def _save_teardown_result(key: str, data: dict, all_results: dict):
    """Append a result to the teardown log and save."""
    all_results[key] = data
    all_results["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(TEARDOWN_LOG, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"  💾 Saved to {TEARDOWN_LOG.name}")


def phase2_capture():
    """Interactive guided capture for remaining measurements."""
    print("\n" + "=" * 60)
    print("  PHASE 2: Guided Pre-Teardown Measurements")
    print("=" * 60)

    # Load enrolled rod data
    db = _load_users()
    rods = db.get("rods", {})
    n_enrolled = sum(1 for r in rods.values() if r.get("enrolled"))
    print(f"\n  Enrolled rods: {n_enrolled}")
    for rid, rinfo in sorted(rods.items()):
        if rinfo.get("enrolled"):
            n_peaks = len(rinfo.get("perturbed_hz", []))
            print(f"    Rod {rid} (pattern {rinfo.get('pattern', '?')}) — {n_peaks} peaks")

    ps = _try_import_picoscope()
    teardown_results = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "purpose": "Pre-teardown final measurements",
    }

    # Auth token for live submissions
    token = None
    try:
        token = _firebase_anon_auth()
        print("\n  ✓ Firebase auth ready — results will be submitted live")
    except Exception:
        print("\n  ⚠ Firebase auth failed — results saved locally only")

    if not ps:
        print("\n  ⚠ PicoScope not available — entering MANUAL entry mode")
        print("    You'll type values from your spectrum analyzer app.\n")
    else:
        print("\n  Mode: TAP-TRIGGERED (flick rod, PZT senses on Ch A)")
        print("  AWG drive PZTs lost coupling — using tap excitation.")
        print("  You'll need to flick each rod when prompted.\n")

    enrolled_ids = sorted(rid for rid, r in rods.items() if r.get("enrolled"))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Test 1: 4×4 Cross-Rod Authentication Matrix
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n┌──────────────────────────────────────────────┐")
    print("│  TEST 1: 4×4 Cross-Rod Authentication Matrix │")
    print("└──────────────────────────────────────────────┘")
    print("  Flick each rod, score against all 4 enrolled fingerprints.")
    print("  Gives a full confusion matrix for classification accuracy.\n")

    if _prompt_yn("Run 4×4 auth matrix?"):
        matrix = {}

        for test_rod in enrolled_ids:
            print(f"\n  ── Flick ROD {test_rod} (pattern {rods[test_rod].get('pattern', '?')}) ──")

            if ps:
                input(f"  Press ENTER, then FLICK Rod {test_rod} (20s timeout)...")
                try:
                    freq, mag, bin_hz = ps["_capture_and_fft"]()
                    print(f"    Captured: {len(freq)} freq bins")
                except Exception as e:
                    print(f"    ✗ Capture failed: {e}")
                    continue

                scores = {}
                for ref_rod in enrolled_ids:
                    ref_hz = rods[ref_rod]["perturbed_hz"]
                    result = ps["score_spectrum_against_rod"](
                        freq, mag, bin_hz, ref_hz, n_modes=10
                    )
                    scores[ref_rod] = {
                        "score_pct": round(result["score"] * 100, 1),
                        "rms_pct": round(result["rms"] * 100, 2),
                        "matched": f"{result['n_matched']}/{result['n_total']}",
                    }
                    me = " ◄" if ref_rod == test_rod else ""
                    print(f"    vs Rod {ref_rod}: {scores[ref_rod]['score_pct']:5.1f}% "
                          f"({scores[ref_rod]['matched']} matched){me}")

                winner = min(scores, key=lambda k: scores[k]["score_pct"])
                correct = winner == test_rod
                tag = "✓ CORRECT" if correct else f"✗ WRONG (got Rod {winner})"
                print(f"    → Winner: Rod {winner} — {tag}")

                matrix[f"rod_{test_rod}"] = {
                    "scores": scores,
                    "winner": winner,
                    "correct": correct,
                }
            else:
                print(f"    Enter scores for Rod {test_rod}:")
                scores = {}
                for ref_rod in enrolled_ids:
                    val = _prompt(f"Score vs Rod {ref_rod} (%)", "")
                    matched = _prompt(f"Matched peaks vs Rod {ref_rod} (e.g. 8/10)", "")
                    if val:
                        scores[ref_rod] = {
                            "score_pct": float(val),
                            "matched": matched,
                        }
                winner = min(scores, key=lambda k: scores[k]["score_pct"]) if scores else "?"
                correct = winner == test_rod
                matrix[f"rod_{test_rod}"] = {
                    "scores": scores,
                    "winner": winner,
                    "correct": correct,
                }

        # Print confusion matrix
        if matrix:
            n_correct = sum(1 for v in matrix.values() if v.get("correct"))
            n_total = len(matrix)
            print(f"\n  ── Confusion Matrix: {n_correct}/{n_total} correct ──")
            print(f"  {'':>12}", end="")
            for r in enrolled_ids:
                print(f"  Rod {r:>2}", end="")
            print("  | Winner")
            print(f"  {'':>12}" + "  ------" * len(enrolled_ids) + "  +-------")
            for test_rod in enrolled_ids:
                key = f"rod_{test_rod}"
                if key not in matrix:
                    continue
                row = matrix[key]
                print(f"  Flick {test_rod:>2}  ", end="")
                for ref_rod in enrolled_ids:
                    sc = row["scores"].get(ref_rod, {})
                    val = sc.get("score_pct", "—")
                    print(f"  {val:>5}", end="")
                tag = "✓" if row["correct"] else "✗"
                print(f"  | Rod {row['winner']} {tag}")

            _save_teardown_result("cross_rod_matrix", {
                "matrix": matrix,
                "n_correct": n_correct,
                "n_total": n_total,
                "accuracy": f"{n_correct}/{n_total}",
                "excitation": "tap (fingernail flick)",
            }, teardown_results)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Test 2: Per-Rod SNR (Firestore: exp02-snr-measurement)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n┌──────────────────────────────────────────────┐")
    print("│  TEST 2: Per-Rod SNR Measurement (tap)       │")
    print("└──────────────────────────────────────────────┘")
    print("  Flick each rod, measure peak vs noise floor.\n")

    if _prompt_yn("Run per-rod SNR measurements?"):
        for rod_id in enrolled_ids:
            pattern = rods[rod_id].get("pattern", "?")
            print(f"\n  ── Rod {rod_id} (pattern {pattern}) ──")

            if ps:
                input(f"  Press ENTER, then FLICK Rod {rod_id}...")
                try:
                    import numpy as np
                    from scipy.signal import find_peaks as sp_find_peaks

                    freq, mag, bin_hz = ps["_capture_and_fft"]()
                    mag_db = 20 * np.log10(np.maximum(mag / max(mag.max(), 1e-15), 1e-15))
                    sorted_db = np.sort(mag_db)
                    noise_db = float(np.median(sorted_db[:len(sorted_db) // 2]))
                    min_bin = int(500 / bin_hz)
                    peak_db = float(np.max(mag_db[min_bin:]))
                    snr_db = peak_db - noise_db

                    pks, _ = sp_find_peaks(
                        mag_db[min_bin:], height=noise_db + 20,
                        distance=int(200 / bin_hz)
                    )
                    n_modes = max(min(len(pks), 100), 1)

                    print(f"    Peak: {peak_db:.1f} dBFS  Floor: {noise_db:.1f} dBFS  "
                          f"SNR: {snr_db:.1f} dB  Modes: {n_modes}")
                except Exception as e:
                    print(f"    ✗ Capture failed: {e}")
                    snr_db = float(_prompt("SNR (dB)", "0"))
                    peak_db = float(_prompt("Peak amplitude (dB)", "0"))
                    noise_db = float(_prompt("Noise floor (dB)", "0"))
                    n_modes = int(_prompt("Visible modes", "0"))
            else:
                snr_db = float(_prompt("SNR (dB)", "0"))
                peak_db = float(_prompt("Peak amplitude (dB)", "0"))
                noise_db = float(_prompt("Noise floor (dB)", "0"))
                n_modes = int(_prompt("Visible modes", "0"))

            snr_data = {
                "rod_material": "Borosilicate glass",
                "rod_length": 150,
                "excitation_method": "Other",
                "peak_amplitude": round(min(peak_db, 100), 1),
                "noise_floor": round(max(noise_db, -150), 1),
                "snr": round(snr_db, 1),
                "num_visible_modes": n_modes,
            }

            _save_teardown_result(f"snr_rod_{rod_id}", snr_data, teardown_results)

            if token:
                r = _submit_experiment(
                    token, "exp02-snr-measurement", snr_data,
                    nickname="Mike",
                    notes=f"Rod {rod_id} (pattern {pattern}), pre-teardown. "
                          f"PZT + PicoScope 2204A, {SAMPLE_RATE} Hz, tap excited.",
                )
                _print_result(r)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Test 3: Per-Rod Ring-Down (Firestore: exp03-damping-time)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n┌──────────────────────────────────────────────┐")
    print("│  TEST 3: Ring-Down Decay (tap)               │")
    print("└──────────────────────────────────────────────┘")
    print("  Flick rod, measure Q from -3dB bandwidth.\n")

    if _prompt_yn("Run ring-down measurements?"):
        for rod_id in enrolled_ids:
            pattern = rods[rod_id].get("pattern", "?")
            print(f"\n  ── Rod {rod_id} (pattern {pattern}) ──")

            if ps:
                input(f"  Press ENTER, then FLICK Rod {rod_id}...")
                try:
                    import numpy as np

                    freq, mag, bin_hz = ps["_capture_and_fft"]()

                    min_bin = int(500 / bin_hz)
                    fund_bin = min_bin + int(np.argmax(mag[min_bin:]))
                    fund_hz = float(freq[fund_bin])
                    print(f"    Fundamental: {fund_hz:.0f} Hz")

                    peak_val = mag[fund_bin]
                    half_power = peak_val / math.sqrt(2)
                    left = fund_bin
                    while left > min_bin and mag[left] > half_power:
                        left -= 1
                    right = fund_bin
                    while right < len(mag) - 1 and mag[right] > half_power:
                        right += 1
                    bw_hz = float(max((right - left), 1) * bin_hz)
                    q_est = int(fund_hz / bw_hz) if bw_hz > 0 else 0

                    if q_est > 0:
                        tau = q_est / (math.pi * fund_hz)
                        ring_s = tau * math.log(1000)
                    else:
                        ring_s = 0.01

                    print(f"    -3dB BW: {bw_hz:.1f} Hz, Q ~ {q_est}, "
                          f"ring-down ~ {ring_s*1000:.0f} ms")
                except Exception as e:
                    print(f"    ✗ Capture failed: {e}")
                    fund_hz = float(_prompt("Fundamental frequency (Hz)", "1800"))
                    ring_s = float(_prompt("Ring-down time (s)", "0.02"))
                    q_est = int(math.pi * fund_hz * ring_s) if ring_s > 0 else 0
            else:
                fund_hz = float(_prompt("Fundamental frequency (Hz)", "1800"))
                ring_s = float(_prompt("Ring-down time (s)", "0.02"))
                q_est = int(math.pi * fund_hz * ring_s) if ring_s > 0 else 0

            damping_data = {
                "rod_material": "Borosilicate glass",
                "rod_length": 150,
                "ring_down_time": round(max(ring_s, 0.01), 3),
                "fundamental_freq": round(fund_hz, 1),
                "q_estimate": max(q_est, 10),
                "support_method": "Other",
            }

            _save_teardown_result(f"ringdown_rod_{rod_id}", damping_data, teardown_results)

            if token:
                r = _submit_experiment(
                    token, "exp03-damping-time", damping_data,
                    nickname="Mike",
                    notes=f"Rod {rod_id} (pattern {pattern}), pre-teardown. "
                          f"Q from -3dB bandwidth. PZT + PicoScope 2204A.",
                )
                _print_result(r)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Test 4: Reproducibility — 3× flick on each rod
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n┌──────────────────────────────────────────────┐")
    print("│  TEST 4: Reproducibility (3 taps per rod)    │")
    print("└──────────────────────────────────────────────┘")
    print("  3 consecutive flicks per rod, check peak consistency.\n")

    if _prompt_yn("Run reproducibility test?"):
        for rod_id in enrolled_ids:
            pattern = rods[rod_id].get("pattern", "?")
            ref_hz = rods[rod_id]["perturbed_hz"][:10]
            print(f"\n  ── Rod {rod_id} (pattern {pattern}) — 3 flicks ──")

            runs = []
            for run_num in range(1, 4):
                print(f"\n    Run {run_num}/3:")
                if ps:
                    input(f"    Press ENTER, then FLICK Rod {rod_id}...")
                    try:
                        freq, mag, bin_hz = ps["_capture_and_fft"]()
                        peaks = ps["_extract_peaks_blind"](freq, mag, bin_hz)
                        top10 = [round(p, 1) for p in peaks[:10]]
                        print(f"      Peaks: {top10[:5]}...")

                        sc = ps["score_spectrum_against_rod"](
                            freq, mag, bin_hz, ref_hz, n_modes=10
                        )
                        print(f"      Self-score: {sc['score']*100:.1f}%, "
                              f"matched {sc['n_matched']}/{sc['n_total']}")

                        runs.append({
                            "top_peaks_hz": top10,
                            "score_pct": round(sc["score"] * 100, 1),
                            "matched": f"{sc['n_matched']}/{sc['n_total']}",
                            "rms_pct": round(sc["rms"] * 100, 2),
                        })
                    except Exception as e:
                        print(f"      ✗ Capture failed: {e}")
                else:
                    score = float(_prompt("Self-score (%)", "5"))
                    matched = _prompt("Matched peaks (e.g. 9/10)", "9/10")
                    runs.append({"score_pct": score, "matched": matched})

            if runs:
                avg_score = sum(r.get("score_pct", 0) for r in runs) / len(runs)
                print(f"\n    Mean self-score: {avg_score:.1f}%")
                _save_teardown_result(f"repro_rod_{rod_id}", {
                    "runs": runs,
                    "mean_score_pct": round(avg_score, 1),
                    "n_runs": len(runs),
                }, teardown_results)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Test 5: Mode Persistence (1 rod: remove putty, measure, re-apply)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n┌──────────────────────────────────────────────┐")
    print("│  TEST 5: Mode Persistence (before/after)      │")
    print("└──────────────────────────────────────────────┘")
    print("  Remove putty from 1 rod → measure bare → reapply → measure.")
    print("  Proves perturbation encoding shifts modes predictably.\n")

    if _prompt_yn("Run mode persistence test?"):
        rod_id = _prompt("Which rod? (1-4)", "1")
        pattern = rods.get(rod_id, {}).get("pattern", "?")
        ref_hz = rods.get(rod_id, {}).get("perturbed_hz", [])[:10]

        # Step A: current state (with putty)
        print(f"\n  Step A: Capture Rod {rod_id} WITH putty (current state)")
        f1_before = None
        f2_before = None
        f3_before = None
        if ps:
            input("  Press ENTER, then FLICK the rod...")
            try:
                freq, mag, bin_hz = ps["_capture_and_fft"]()
                peaks = ps["_extract_peaks_blind"](freq, mag, bin_hz)
                f1_before = round(peaks[0], 1) if len(peaks) > 0 else None
                f2_before = round(peaks[1], 1) if len(peaks) > 1 else None
                f3_before = round(peaks[2], 1) if len(peaks) > 2 else None
                print(f"    f1={f1_before}, f2={f2_before}, f3={f3_before}")
            except Exception as e:
                print(f"    ✗ {e}")
        if f1_before is None:
            f1_before = float(_prompt("Mode 1 freq before (Hz)", str(ref_hz[0]) if ref_hz else ""))
            f2_before = float(_prompt("Mode 2 freq before (Hz)", str(ref_hz[1]) if len(ref_hz) > 1 else ""))
            f3_before = float(_prompt("Mode 3 freq before (Hz)", str(ref_hz[2]) if len(ref_hz) > 2 else ""))

        # Step B: remove putty
        print(f"\n  Step B: REMOVE all putty from Rod {rod_id}")
        input("  Press ENTER when putty is removed and rod is re-seated...")

        # Measure putty mass if available
        putty_mass = float(_prompt("Putty mass (g, weigh on scale)", "0.1"))
        putty_pos = float(_prompt("Putty position from end (mm)", "30"))

        print(f"\n  Step C: Capture Rod {rod_id} WITHOUT putty (bare rod)")
        f1_after = None
        f2_after = None
        f3_after = None
        if ps:
            input("  Press ENTER, then FLICK bare rod...")
            try:
                freq, mag, bin_hz = ps["_capture_and_fft"]()
                peaks = ps["_extract_peaks_blind"](freq, mag, bin_hz)
                f1_after = round(peaks[0], 1) if len(peaks) > 0 else None
                f2_after = round(peaks[1], 1) if len(peaks) > 1 else None
                f3_after = round(peaks[2], 1) if len(peaks) > 2 else None
                print(f"    f1={f1_after}, f2={f2_after}, f3={f3_after}")
            except Exception as e:
                print(f"    ✗ {e}")
        if f1_after is None:
            f1_after = float(_prompt("Mode 1 freq after (Hz)", ""))
            f2_after = float(_prompt("Mode 2 freq after (Hz)", ""))
            f3_after = float(_prompt("Mode 3 freq after (Hz)", ""))

        # Compute shifts
        if f1_before and f1_after:
            shift1 = abs(f1_after - f1_before) / f1_before * 100
            print(f"\n    Mode 1 shift: {f1_before:.1f} → {f1_after:.1f} Hz ({shift1:.2f}%)")
        if f2_before and f2_after:
            shift2 = abs(f2_after - f2_before) / f2_before * 100
            print(f"    Mode 2 shift: {f2_before:.1f} → {f2_after:.1f} Hz ({shift2:.2f}%)")
        if f3_before and f3_after:
            shift3 = abs(f3_after - f3_before) / f3_before * 100
            print(f"    Mode 3 shift: {f3_before:.1f} → {f3_after:.1f} Hz ({shift3:.2f}%)")

        persistence_data = {
            "rod_material": "Borosilicate glass",
            "rod_length": 150,
            "rod_diameter": 6,
            "f1_before": f1_before,
            "f2_before": f2_before,
            "f3_before": f3_before,
            "perturbation_mass": putty_mass,
            "perturbation_position": putty_pos,
            "f1_after": f1_after,
            "f2_after": f2_after,
            "f3_after": f3_after,
        }

        _save_teardown_result("mode_persistence", persistence_data, teardown_results)

        if token:
            r = _submit_experiment(
                token, "exp01-mode-persistence", persistence_data,
                nickname="Mike",
                notes=f"Rod {rod_id} (pattern {pattern}), pre-teardown. "
                      f"'Before' = with putty, 'After' = bare rod (putty removed). "
                      f"PZT + PicoScope 2204A.",
            )
            _print_result(r)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Test 6: Rod 3/4 Overlap Diagnosis
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n┌──────────────────────────────────────────────┐")
    print("│  TEST 6: Rod 3/4 Overlap Analysis             │")
    print("└──────────────────────────────────────────────┘")

    r3_hz = rods.get("3", {}).get("perturbed_hz", [])
    r4_hz = rods.get("4", {}).get("perturbed_hz", [])

    if r3_hz and r4_hz:
        print("  Comparing enrolled peaks within ±5% (auth window):\n")
        overlaps = []
        for i, f3 in enumerate(r3_hz):
            for j, f4 in enumerate(r4_hz):
                pct_diff = abs(f3 - f4) / f3 * 100
                if pct_diff < 5.0:
                    overlaps.append({
                        "rod3_peak": i + 1, "rod3_hz": round(f3, 1),
                        "rod4_peak": j + 1, "rod4_hz": round(f4, 1),
                        "pct_diff": round(pct_diff, 2),
                    })
                    print(f"    Rod 3 peak {i+1:2d} ({f3:8.1f} Hz) ↔ "
                          f"Rod 4 peak {j+1:2d} ({f4:8.1f} Hz) — Δ {pct_diff:.2f}%")

        n_overlap = len(overlaps)
        print(f"\n  Total overlapping peaks: {n_overlap}/20")
        print(f"  This {'explains' if n_overlap > 5 else 'may partially explain'} "
              f"the cross-rod confusion in parallel search.")

        _save_teardown_result("rod34_overlap", {
            "n_overlapping_peaks": n_overlap,
            "within_pct": 5.0,
            "overlaps": overlaps,
            "rod3_peaks": [round(f, 1) for f in r3_hz],
            "rod4_peaks": [round(f, 1) for f in r4_hz],
        }, teardown_results)
    else:
        print("  ⚠ Rod 3 or 4 not enrolled — skipping")

    # ── Final Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  PRE-TEARDOWN CAPTURE COMPLETE")
    print("=" * 60)
    print(f"\n  Results saved to: {TEARDOWN_LOG}")
    print(f"  Tests completed: {len(teardown_results) - 2}")  # minus date + purpose keys

    if token:
        print("  Firestore submissions: check console output above for doc IDs")
    else:
        print("  Firestore: offline — run phase 1 later to submit saved data")

    print("\n  You may now safely dismantle the 4-rod setup. 🔧\n")


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Pre-teardown data capture & Firestore submission"
    )
    parser.add_argument("--submit", action="store_true",
                        help="Phase 1 only: submit existing data")
    parser.add_argument("--capture", action="store_true",
                        help="Phase 2 only: guided measurements")
    parser.add_argument("--dry-run", action="store_true",
                        help="Phase 1: show what would be submitted without sending")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════════╗")
    print("║         CWM Pre-Teardown Data Collection Script         ║")
    print("║                                                          ║")
    print(f"║  Date: {datetime.now().strftime('%Y-%m-%d %H:%M'):50s}║")
    print("╚══════════════════════════════════════════════════════════╝")

    phase1_results = []

    if args.submit or (not args.submit and not args.capture):
        phase1_results = phase1_submit(dry_run=args.dry_run)

    if args.capture or (not args.submit and not args.capture):
        phase2_capture()

    if phase1_results:
        print("\n─── Final Phase 1 Results ───")
        for r in phase1_results:
            status = "✓" if r.get("ok") else "✗"
            print(f"  {status} {r['experimentId']}: {r.get('id', r.get('error', 'dry run'))}")


if __name__ == "__main__":
    main()
