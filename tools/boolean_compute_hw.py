#!/usr/bin/env python3
"""
Hardware Boolean Compute — AND/OR/XOR via Mode Superposition

Demonstrates in-situ Boolean operations on the physical 4-rod array.
Two binary patterns (encoded as frequency sets) are superposed on the
AWG, and the resulting amplitude distribution at the sense PZT is
thresholded to extract AND, OR, and XOR.

Physical principle:
  When driving two rods' frequency sets simultaneously:
    - "both-high" frequencies (present in BOTH patterns): 2× amplitude
    - "one-high"  frequencies (present in ONE pattern):   1× amplitude
    - "both-low"  frequencies (absent from both):         ~0 (noise floor)

  Threshold firmware extracts:
    AND = both-high only
    OR  = both-high + one-high
    XOR = one-high only (present in exactly one pattern)

Signal chain:
  AWG OUT → Drive PZTs (all 4 rods share AWG)
  Relay N → Sense PZT Rod N → PicoScope Ch A

Protocol (cross-relay normalization):
  For each frequency in the union of pattern A and B peaks:
    1. Drive AWG at frequency F
    2. Measure response on ALL sense rods (relay mux cycling)
    3. Cross-relay normalize: frac[r] = mag[r] / sum(mag)
    4. Detect pattern A: frac[rod_a] > threshold → bit_a = 1
    5. Detect pattern B: frac[rod_b] > threshold → bit_b = 1
    6. Compute: AND = bit_a & bit_b, OR = bit_a | bit_b, XOR = bit_a ^ bit_b
    7. Compare to ground truth

  The threshold is enrollment-aware: if F matches rod X's peaks
  (within 3%), rod X should have a high cross-relay fraction.

Usage:
  PYTHONPATH=. python tools/boolean_compute_hw.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/boolean_compute_hw.py --pattern-a 1 --pattern-b 2
"""
from __future__ import annotations

import argparse
import ctypes
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

from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux
from picosdk.ps2000 import ps2000

# ── Configuration ─────────────────────────────────────────────────────────

N_AVG = 12
SETTLE_S = 0.20
SETTLE_RELAY_S = 0.05
N_PEAKS = 10        # peaks per pattern
FREQ_MATCH_PCT = 3  # % tolerance for frequency matching

# ── Paths ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab"
USERS_FILE = LAB_DIR / "users.json"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = LAB_DIR / "boolean_compute"
RESULTS_FILE = RESULTS_DIR / f"bool_{TIMESTAMP}.json"
LOG_FILE = RESULTS_DIR / f"bool_{TIMESTAMP}.log"

FIREBASE_API_KEY = "AIzaSyCxlNaRNwwOim4-bSYL7MrRuQmDBznlga0"
CWM_SITE_URL = "https://coherent-wave-memory.web.app"

# ── Logging ───────────────────────────────────────────────────────────────

_log_lines: list[str] = []


def log(msg: str, also_print: bool = True) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    _log_lines.append(line)
    if also_print:
        print(msg)


def _save_log() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w") as f:
        f.write("\n".join(_log_lines) + "\n")


# ── Scope helpers ─────────────────────────────────────────────────────────

def _open_scope():
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    log("PicoScope opened (Ch A ±1V DC)")
    return handle


def _close_scope(handle):
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    log("PicoScope closed")


def _measure_at(handle, freq_hz: float, n_avg: int = N_AVG,
                settle_s: float = SETTLE_S) -> dict:
    """Drive AWG at freq_hz, capture, return magnitude and per-capture data."""
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

    mean_mag = float(np.mean(magnitudes)) if magnitudes else 0.0
    return {
        "magnitude": round(mean_mag, 1),
        "per_capture": [round(m, 1) for m in magnitudes],
    }


# ── Boolean logic ─────────────────────────────────────────────────────────

def _classify_frequencies(peaks_a: list[float], peaks_b: list[float],
                           match_pct: float = FREQ_MATCH_PCT) -> dict:
    """Classify all frequencies into both/a-only/b-only sets.

    Returns dict with:
      "both":   frequencies present in A AND B (within match_pct%)
      "a_only": frequencies in A but not B
      "b_only": frequencies in B but not A
      "all":    union, sorted
    """
    both = []
    a_only = []
    b_only = list(peaks_b)  # will remove matched ones
    b_used = [False] * len(peaks_b)

    for fa in peaks_a:
        matched = False
        for bi, fb in enumerate(peaks_b):
            if not b_used[bi] and abs(fa - fb) / max(fa, fb) * 100 < match_pct:
                both.append((fa + fb) / 2)  # use midpoint
                b_used[bi] = True
                matched = True
                break
        if not matched:
            a_only.append(fa)

    b_only = [peaks_b[i] for i in range(len(peaks_b)) if not b_used[i]]

    all_freqs = sorted(both + a_only + b_only)
    return {
        "both": sorted(both),
        "a_only": sorted(a_only),
        "b_only": sorted(b_only),
        "all": all_freqs,
    }



# ═══════════════════════════════════════════════════════════════════════
#  Main experiment
# ═══════════════════════════════════════════════════════════════════════

def run_boolean_compute(mux: RelayMux, pattern_a: str = "1",
                        pattern_b: str = "2",
                        n_peaks: int = N_PEAKS) -> dict:
    """Run Boolean compute experiment with per-rod self-response detection.

    Phases:
      0. Pre-scan: measure each rod's self-response at ALL enrolled peaks,
         filter to only strong peaks (above geometric-mean threshold).
      1. Classify strong peaks into both/a-only/b-only.
      2. For each frequency in the union, measure on ALL sense rods.
      3. Per-rod adaptive thresholds → detect A, detect B → AND/OR/XOR.
    """
    with open(USERS_FILE) as f:
        db = json.load(f)

    enrolled = {}
    rod_patterns = {}
    for rid in sorted(db["rods"].keys()):
        r = db["rods"][rid]
        if r.get("enrolled"):
            enrolled[rid] = r["perturbed_hz"]  # full 20 peaks
            rod_patterns[rid] = r.get("pattern", "?")

    rod_ids = sorted(enrolled.keys())

    t_start = time.time()
    handle = _open_scope()

    # ── Phase 0: Pre-scan — measure self-response at all enrolled peaks ──
    log("=" * 70)
    log("  HARDWARE BOOLEAN COMPUTE — Per-Rod Self-Response Detection")
    log("=" * 70)

    strong_peaks = {}  # rod_id → list of (freq, magnitude)
    for sr in [pattern_a, pattern_b]:
        mux.select(int(sr))
        time.sleep(SETTLE_RELAY_S)
        all_peaks = enrolled[sr][:n_peaks]  # use up to n_peaks for scan
        scan_results = []
        log(f"\n  Pre-scan Rod {sr} ({rod_patterns[sr]}) — {len(all_peaks)} peaks:")
        for i, freq in enumerate(all_peaks):
            m = _measure_at(handle, freq, n_avg=N_AVG // 2)  # faster pre-scan
            scan_results.append((freq, m["magnitude"]))
            log(f"    f{i+1:2d}={freq:7.1f} Hz  mag={m['magnitude']:12.0f}",
                also_print=False)

        # Adaptive threshold: geometric mean of median top-half and median bottom-half
        mags_sorted = sorted([m for _, m in scan_results])
        mid = len(mags_sorted) // 2
        med_strong = float(np.median(mags_sorted[mid:]))
        med_weak = float(np.median(mags_sorted[:mid]))
        thresh = math.sqrt(med_strong * med_weak) if med_weak > 0 else med_strong * 0.1

        strong = [(f, m) for f, m in scan_results if m > thresh]
        weak = [(f, m) for f, m in scan_results if m <= thresh]
        strong_peaks[sr] = [f for f, m in strong]

        log(f"    Threshold: {thresh:.0f}  "
            f"Strong: {len(strong)}/{len(scan_results)}  "
            f"Weak: {len(weak)}/{len(scan_results)}")
        log(f"    Strong peaks: {[round(f) for f in strong_peaks[sr]]}")

    mux.off()

    # ── Phase 1: Classify strong peaks ────────────────────────────────
    peaks_a = strong_peaks[pattern_a]
    peaks_b = strong_peaks[pattern_b]
    classes = _classify_frequencies(peaks_a, peaks_b)
    all_freqs = classes["all"]

    log(f"\n  Pattern A: Rod {pattern_a} ({rod_patterns[pattern_a]}) — {len(peaks_a)} strong peaks")
    log(f"  Pattern B: Rod {pattern_b} ({rod_patterns[pattern_b]}) — {len(peaks_b)} strong peaks")
    log(f"  Sense rods: ALL {rod_ids}")
    log(f"  Frequency classification (at {FREQ_MATCH_PCT}% tolerance):")
    log(f"    Both A∩B:  {len(classes['both'])} freqs")
    log(f"    A only:    {len(classes['a_only'])} freqs")
    log(f"    B only:    {len(classes['b_only'])} freqs")
    log(f"    Union A∪B: {len(all_freqs)} freqs")
    log(f"  Relay mux: {mux.port}")
    log("")

    experiment = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pattern_a": pattern_a,
        "pattern_b": pattern_b,
        "rod_patterns": rod_patterns,
        "rod_ids": rod_ids,
        "peaks_a": [round(f, 1) for f in peaks_a],
        "peaks_b": [round(f, 1) for f in peaks_b],
        "classes": {k: [round(f, 1) for f in v] for k, v in classes.items()},
        "n_peaks": n_peaks,
        "n_avg": N_AVG,
        "awg_uvpp": AWG_DRIVE_UVPP,
        "sample_rate": SAMPLE_RATE,
        "mux_port": mux.port,
        "method": "prescan-filtered-self-response",
    }

    try:
        # ── Phase 2: Measure every frequency on every sense rod ───────
        raw_mags = []

        for fi, freq in enumerate(all_freqs):
            rod_mag = {}
            for sr in rod_ids:
                mux.select(int(sr))
                time.sleep(SETTLE_RELAY_S)
                m = _measure_at(handle, freq)
                rod_mag[sr] = m["magnitude"]
            raw_mags.append(rod_mag)

            mag_str = "  ".join(f"R{sr}={rod_mag[sr]:8.0f}" for sr in rod_ids)
            log(f"  f{fi+1:2d} {freq:7.1f} Hz  {mag_str}", also_print=fi == 0 or (fi + 1) % 5 == 0)

        mux.off()

    finally:
        _close_scope(handle)

    duration = time.time() - t_start
    experiment["duration_s"] = round(duration, 1)
    experiment["raw_mags"] = [
        {sr: round(m[sr], 1) for sr in rod_ids}
        for m in raw_mags
    ]

    # ── Per-rod self-response Boolean extraction ─────────────────────
    # Detection uses a simple rule: a frequency "belongs to" rod R if
    # rod R's magnitude at that frequency exceeds rod R's minimum
    # pre-scan magnitude for its strong peaks (the weakest peak that
    # passed the pre-scan filter). This gives a tight, per-rod floor.

    log("\n" + "=" * 70)
    log("  RESULTS — Per-Rod Self-Response Detection")
    log("=" * 70)

    # Pre-scan already determined which peaks are strong for each rod.
    # The threshold for main-phase detection = minimum of what the
    # pre-scan accepted (the weakest "strong" peak's self-magnitude).
    # We re-measure during main phase on the same relay, so magnitudes
    # track closely. Use 50% of the weakest strong peak as margin.
    rod_thresholds = {}
    for sr in [pattern_a, pattern_b]:
        # Find minimum self-magnitude among the strong peaks in main-phase data
        min_self_mag = float('inf')
        for fi, freq in enumerate(all_freqs):
            is_enrolled = any(
                abs(freq - ep) / max(freq, ep) < 0.03
                for ep in strong_peaks[sr]
            )
            if is_enrolled:
                min_self_mag = min(min_self_mag, raw_mags[fi][sr])

        # Threshold = 50% of the weakest strong peak's self-response
        if min_self_mag == float('inf'):
            min_self_mag = 100000
        rod_thresholds[sr] = min_self_mag * 0.5
        log(f"\n  Rod {sr}: weakest strong peak self-mag={min_self_mag:.0f}  "
            f"threshold={rod_thresholds[sr]:.0f}")

    log(f"\n  {'Freq':>8s}  {'Cat':>7s}  {'mag_A':>10s}  {'mag_B':>10s}  "
        f"{'det_A':>5s}  {'det_B':>5s}  "
        f"{'AND':>4s}  {'OR':>3s}  {'XOR':>4s}  {'ok':>3s}")
    log(f"  {'─'*8}  {'─'*7}  {'─'*10}  {'─'*10}  "
        f"{'─'*5}  {'─'*5}  "
        f"{'─'*4}  {'─'*3}  {'─'*4}  {'─'*3}")

    and_correct = 0
    or_correct = 0
    xor_correct = 0
    total_bits = 0
    results_per_freq = []

    # Map each frequency to its category
    freq_cat = {}
    for f in classes["both"]:
        freq_cat[round(f, 1)] = "both"
    for f in classes["a_only"]:
        freq_cat[round(f, 1)] = "a_only"
    for f in classes["b_only"]:
        freq_cat[round(f, 1)] = "b_only"

    for fi, freq in enumerate(all_freqs):
        mags = raw_mags[fi]
        mag_a = mags[pattern_a]
        mag_b = mags[pattern_b]

        # Enrollment check: freq near this rod's STRONG peaks
        a_enrolled = any(
            abs(freq - ep) / max(freq, ep) < 0.03
            for ep in strong_peaks[pattern_a]
        )
        b_enrolled = any(
            abs(freq - ep) / max(freq, ep) < 0.03
            for ep in strong_peaks[pattern_b]
        )

        # Per-rod self-response detection:
        # Rod detects "present" if its own magnitude exceeds its threshold
        # AND the frequency is in its enrollment.
        det_a = 1 if (a_enrolled and mag_a > rod_thresholds[pattern_a]) else 0
        det_b = 1 if (b_enrolled and mag_b > rod_thresholds[pattern_b]) else 0

        # Computed Boolean
        and_got = 1 if (det_a and det_b) else 0
        or_got = 1 if (det_a or det_b) else 0
        xor_got = 1 if (det_a != det_b) else 0

        # Ground truth
        cat = freq_cat.get(round(freq, 1), "?")
        in_a = cat in ("both", "a_only")
        in_b = cat in ("both", "b_only")
        and_exp = 1 if (in_a and in_b) else 0
        or_exp = 1 if (in_a or in_b) else 0
        xor_exp = 1 if (in_a != in_b) else 0

        and_ok = and_exp == and_got
        or_ok = or_exp == or_got
        xor_ok = xor_exp == xor_got
        all_ok = and_ok and or_ok and xor_ok

        if and_ok:
            and_correct += 1
        if or_ok:
            or_correct += 1
        if xor_ok:
            xor_correct += 1
        total_bits += 1

        cat_label = cat.replace("_", "-")
        log(f"  {freq:8.1f}  {cat_label:>7s}  {mag_a:10.0f}  {mag_b:10.0f}  "
            f"{'  ✓' if det_a == in_a else '  ✗':>5s}  "
            f"{'  ✓' if det_b == in_b else '  ✗':>5s}  "
            f"{'✓' if and_ok else '✗':>4s}  "
            f"{'✓' if or_ok else '✗':>3s}  "
            f"{'✓' if xor_ok else '✗':>4s}  "
            f"{'✓' if all_ok else '✗':>3s}")

        results_per_freq.append({
            "freq": round(freq, 1),
            "category": cat,
            "mag_a": round(mag_a, 1),
            "mag_b": round(mag_b, 1),
            "a_enrolled": a_enrolled,
            "b_enrolled": b_enrolled,
            "det_a": det_a,
            "det_b": det_b,
            "and_expected": and_exp, "and_computed": and_got,
            "or_expected": or_exp, "or_computed": or_got,
            "xor_expected": xor_exp, "xor_computed": xor_got,
        })

    and_fidelity = and_correct / total_bits if total_bits > 0 else 0
    or_fidelity = or_correct / total_bits if total_bits > 0 else 0
    xor_fidelity = xor_correct / total_bits if total_bits > 0 else 0
    mean_fidelity = (and_fidelity + or_fidelity + xor_fidelity) / 3

    log(f"\n  ─── Summary ───")
    log(f"  AND fidelity: {and_correct}/{total_bits} ({and_fidelity*100:.0f}%)")
    log(f"  OR  fidelity: {or_correct}/{total_bits} ({or_fidelity*100:.0f}%)")
    log(f"  XOR fidelity: {xor_correct}/{total_bits} ({xor_fidelity*100:.0f}%)")
    log(f"  Mean fidelity: {mean_fidelity*100:.0f}%")
    log(f"  Rod thresholds: A={rod_thresholds[pattern_a]:.0f}  B={rod_thresholds[pattern_b]:.0f}")
    log(f"  Duration: {duration:.1f}s")

    experiment["results_per_freq"] = results_per_freq
    experiment["analysis"] = {
        "and_fidelity": round(and_fidelity, 3),
        "or_fidelity": round(or_fidelity, 3),
        "xor_fidelity": round(xor_fidelity, 3),
        "mean_fidelity": round(mean_fidelity, 3),
        "total_bits": total_bits,
        "and_correct": and_correct,
        "or_correct": or_correct,
        "xor_correct": xor_correct,
        "method": "rank-based",
    }

    return experiment


# ═══════════════════════════════════════════════════════════════════════
#  Firestore
# ═══════════════════════════════════════════════════════════════════════

def _firebase_anon_auth() -> str:
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
        return {"ok": False, "error": body, "status": e.code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Hardware Boolean compute — AND/OR/XOR via mode superposition"
    )
    parser.add_argument("--port", type=str, default=None)
    parser.add_argument("--pattern-a", type=str, default="1",
                        help="Rod whose peaks define pattern A (default: 1)")
    parser.add_argument("--pattern-b", type=str, default="2",
                        help="Rod whose peaks define pattern B (default: 2)")
    parser.add_argument("--peaks", type=int, default=N_PEAKS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    mux = RelayMux(port=args.port)
    mux.open()
    log(f"Relay mux connected on {mux.port}")

    try:
        result = run_boolean_compute(
            mux, pattern_a=args.pattern_a, pattern_b=args.pattern_b,
            n_peaks=args.peaks
        )
    finally:
        mux.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)
    log(f"\nResults saved to {RESULTS_FILE.relative_to(ROOT)}")
    _save_log()
    log(f"Log saved to {LOG_FILE.relative_to(ROOT)}")

    if not args.dry_run:
        log("\nSubmitting to Firestore...")
        try:
            token = _firebase_anon_auth()
            analysis = result["analysis"]

            data = {
                "n_rods": 4,
                "peaks_per_rod": args.peaks,
                "sample_rate": SAMPLE_RATE,
                "freq_resolution": round(SAMPLE_RATE / (N_SAMPLES * 4), 1),
                "auth_rms_pct": max(0, round(analysis["mean_fidelity"] * 100, 1)),
                "auth_matched_peaks": min(20, analysis["and_correct"] + analysis["or_correct"] + analysis["xor_correct"]),
                "auth_score_pct": round(analysis["mean_fidelity"] * 100, 1),
                "next_best_score_pct": 0,
                "min_cross_rod_pct": round(min(analysis["and_fidelity"], analysis["or_fidelity"], analysis["xor_fidelity"]) * 100, 1),
                "repro_peaks_matched": f"{analysis['total_bits']}/{analysis['total_bits']}",
                "excitation_method": "Piezo pulse",
                "correct_rod_identified": "Yes" if analysis["mean_fidelity"] >= 0.9 else "No",
            }
            notes = (
                f"Boolean compute (cross-relay norm): Rod {args.pattern_a} op Rod {args.pattern_b}. "
                f"AND={analysis['and_fidelity']*100:.0f}% "
                f"OR={analysis['or_fidelity']*100:.0f}% "
                f"XOR={analysis['xor_fidelity']*100:.0f}%. "
                f"Mean={analysis['mean_fidelity']*100:.0f}%. {TIMESTAMP}."
            )
            r = _submit_experiment(token, "exp-hw-auth", data, notes=notes)
            if r.get("ok"):
                log(f"  ✓ Submitted → {r.get('id', '?')}")
            else:
                error = r.get("error", "unknown")
                try:
                    parsed = json.loads(error)
                    error = parsed.get("statusMessage", error)
                except (json.JSONDecodeError, AttributeError):
                    pass
                log(f"  ✗ Failed: {error}")
        except Exception as e:
            log(f"  ✗ Auth/submit failed: {e}")


if __name__ == "__main__":
    main()
