#!/usr/bin/env python3
"""
Plate CIM Experiment Suite — Compute-in-Memory on Fused Silica Plates

Plate equivalent of cim_suite_hw.py (which runs on rods).

Experiment blocks:
  1. Temporal stability  — Compare census peaks across sessions
  2. Boolean pairs       — AND/OR/XOR via spectral superposition (all plate pairs)
  3. NN all pairs        — Nearest-neighbor classification (all plate pairs)
  4. 3-plate Boolean     — AND/OR/XOR across 3 plates simultaneously
  5. Chained Boolean     — A AND B → result XOR C
  6. Noise robustness    — Drive voltage sweep from 100% down to 10%

Signal chain:
  AWG OUT → Drive PZT (all plates share AWG via parallel wiring)
  Relay N → Sense PZT Plate N → PicoScope Ch A

Usage:
  PYTHONPATH=. python tools/plate_cim_suite.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_cim_suite.py --only temporal,boolean-pairs
  PYTHONPATH=. python tools/plate_cim_suite.py --dry-run
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import cwm_picoscope  # noqa: F401
from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux
from firestore_submit import firebase_anon_auth, submit_experiment, print_result

# ── Configuration ─────────────────────────────────────────────────────

N_AVG = 8
SETTLE_S = 0.10
SETTLE_RELAY_S = 0.10
N_PEAKS = 10
FREQ_MATCH_PCT = 3
GUARD_BAND_PCT = 5

# ── Paths ─────────────────────────────────────────────────────────────

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = LAB_DIR / "cim_suite"
RESULTS_FILE = RESULTS_DIR / f"plate_suite_{TIMESTAMP}.json"
LOG_FILE = RESULTS_DIR / f"plate_suite_{TIMESTAMP}.log"

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

# ── Logging ───────────────────────────────────────────────────────────

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


# ── Scope helpers ─────────────────────────────────────────────────────

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    log("PicoScope opened (Ch A ±1V DC)")
    return handle


def _close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    log("PicoScope closed")


def _measure_at(handle, freq_hz: float,
                drive_uvpp: int = AWG_DRIVE_UVPP) -> dict:
    """Drive AWG at freq_hz, capture magnitude."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, drive_uvpp, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)

    magnitudes = []
    for _ in range(N_AVG):
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
            tb = int(round(freq_hz / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft) - 1, tb + 3)
            magnitudes.append(float(np.max(fft[lo:hi + 1])))

    return {"magnitude": round(float(np.mean(magnitudes)), 1) if magnitudes else 0.0}


# ── Enrollment loader ────────────────────────────────────────────────

def _load_enrollment(census_path: str | None = None) -> tuple[dict, dict, dict, list]:
    """Load plate enrollment from latest census file.

    Returns (enrolled_freqs, plate_names, enrolled_mags, plate_ids).
    enrolled_mags maps plate_id -> list of magnitudes (same order as enrolled_freqs).
    """
    if census_path:
        census_file = Path(census_path)
        if not census_file.exists():
            raise FileNotFoundError(f"Census file not found: {census_path}")
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            raise FileNotFoundError("No census file found. Run plate_mode_census.py first.")
        census_file = census_files[-1]

    log(f"Census: {census_file.name}")
    with open(census_file) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    enrolled = {}
    enrolled_mags = {}
    plate_names = {}
    for pid in PLATE_IDS:
        if pid in census and census[pid].get("peaks"):
            peaks = census[pid]["peaks"][:N_PEAKS]
            enrolled[pid] = [p["freq_hz"] for p in peaks]
            enrolled_mags[pid] = [p["magnitude"] for p in peaks]
            plate_names[pid] = PLATE_NAMES[pid]

    plate_ids = sorted(enrolled.keys())
    log(f"Loaded enrollment: {len(plate_ids)} plates, {N_PEAKS} peaks each")
    return enrolled, plate_names, enrolled_mags, plate_ids


# ── Frequency classification ─────────────────────────────────────────

def _classify_frequencies(peaks_a: list[float], peaks_b: list[float],
                          match_pct: float = FREQ_MATCH_PCT) -> dict:
    """Classify frequencies into a_only, b_only, shared."""
    a_only, b_only, shared = [], [], []

    matched_b = set()
    for fa in peaks_a:
        found = False
        for j, fb in enumerate(peaks_b):
            if j in matched_b:
                continue
            if abs(fa - fb) / max(fa, fb) * 100 < match_pct:
                shared.append((fa, fb))
                matched_b.add(j)
                found = True
                break
        if not found:
            a_only.append(fa)

    for j, fb in enumerate(peaks_b):
        if j not in matched_b:
            b_only.append(fb)

    return {
        "a_only": a_only, "b_only": b_only, "shared": shared,
        "n_a_only": len(a_only), "n_b_only": len(b_only), "n_shared": len(shared),
    }


# ── Pre-scan filtering (V5 approach from rods) ───────────────────────

def _prescan_strong_peaks(handle, mux, enrolled, plate_names, plate_ids) -> dict:
    """Phase 0: measure each plate's self-response, filter to strong modes.

    For each plate, drive AWG at each enrolled frequency while measuring on
    that plate's own relay.  Sort magnitudes, split at midpoint, compute
    geometric mean of median(top half) and median(bottom half) as threshold.
    Peaks above the threshold are "strong" — reliable enough to carry Boolean
    information.  Returns dict[pid] → list of strong freq_hz.
    """
    log("\n" + "=" * 65)
    log("  PRE-SCAN: filtering strong modes per plate")
    log("=" * 65)

    strong = {}          # pid → [freq, ...]
    strong_mags = {}     # pid → {freq: magnitude}  (for detection threshold)

    for pid in plate_ids:
        name = plate_names[pid]
        freqs = enrolled[pid][:N_PEAKS]
        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        scan = []
        for freq in freqs:
            m = _measure_at(handle, freq)
            scan.append((freq, m["magnitude"]))

        # Geometric-mean threshold of top/bottom halves
        mags_sorted = sorted(m for _, m in scan)
        mid = len(mags_sorted) // 2
        med_strong = float(np.median(mags_sorted[mid:]))
        med_weak = float(np.median(mags_sorted[:mid])) if mid > 0 else 0.0
        thresh = math.sqrt(med_strong * med_weak) if med_weak > 0 else med_strong * 0.1

        s = [(f, m) for f, m in scan if m > thresh]
        strong[pid] = [f for f, _ in s]
        strong_mags[pid] = {f: m for f, m in s}

        log(f"  Plate {name}: {len(s)}/{len(scan)} strong  "
            f"(thresh {thresh:,.0f})  "
            f"peaks {[round(f) for f in strong[pid]]}")

    mux.off()
    total = sum(len(v) for v in strong.values())
    log(f"  Total strong modes: {total}")
    return strong, strong_mags


# ── Template scoring ─────────────────────────────────────────────────

def _template_score(query_freqs: list[float],
                    raw_mags: dict[str, list[float]],
                    enrolled: dict[str, list[float]],
                    plate_ids: list[str]) -> dict[str, float]:
    """Score each plate against a query pattern."""
    scores = {pid: 0.0 for pid in plate_ids}
    for pi, freq in enumerate(query_freqs):
        mags = {pid: raw_mags[pid][pi] for pid in plate_ids}
        total = sum(mags.values())
        if total == 0:
            continue
        for pid in plate_ids:
            frac = mags[pid] / total
            expected = any(
                abs(freq - ep) / max(freq, ep) < 0.03
                for ep in enrolled[pid]
            )
            if expected:
                scores[pid] += frac * 3.0
            else:
                scores[pid] -= frac * 1.0
    return {pid: round(v, 2) for pid, v in scores.items()}


# ═══════════════════════════════════════════════════════════════════════
#  Block 1: Temporal Stability
# ═══════════════════════════════════════════════════════════════════════

def block_temporal(handle, mux, enrolled, plate_names, plate_ids) -> dict:
    """Re-measure enrolled frequencies, check for drift."""
    log("\n" + "=" * 65)
    log("  BLOCK 1: TEMPORAL STABILITY")
    log("=" * 65)

    t0 = time.time()
    plates = []
    total_alive = 0
    total_enrolled = 0

    for pid in plate_ids:
        name = plate_names[pid]
        freqs = enrolled[pid]
        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        log(f"\n  Plate {name}: measuring {len(freqs)} enrolled frequencies")
        live_mags = []
        for freq in freqs:
            m = _measure_at(handle, freq)
            live_mags.append(m["magnitude"])
            log(f"    {freq:.0f} Hz: {m['magnitude']:.0f}")

        n_alive = sum(1 for m in live_mags if m > 100_000)
        total_alive += n_alive
        total_enrolled += len(freqs)

        plates.append({
            "plate": name, "n_enrolled": len(freqs), "n_alive": n_alive,
            "magnitudes": [round(m, 1) for m in live_mags],
        })
        log(f"    → {n_alive}/{len(freqs)} modes alive")

    mux.off()
    recall_pct = round(total_alive / total_enrolled * 100, 1) if total_enrolled else 0
    duration = round(time.time() - t0, 1)

    log(f"\n  Temporal stability: {total_alive}/{total_enrolled} "
        f"({recall_pct}%) modes alive across {len(plate_ids)} plates")

    return {
        "block": "temporal", "plates": plates,
        "total_alive": total_alive, "total_enrolled": total_enrolled,
        "recall_pct": recall_pct, "duration_s": duration,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Block 2: Boolean All Pairs
# ═══════════════════════════════════════════════════════════════════════

def _boolean_fidelity_v5(mags_a, mags_b, categories, freqs,
                         strong_a, strong_b,
                         thresh_a, thresh_b):
    """V5 pre-scan-filtered Boolean fidelity.

    Detection rule (same as rod V5):
      plate detects "present" if:
        1. The frequency is in its strong-peak set, AND
        2. Its self-response magnitude > its detection threshold
    """
    n = len(categories)
    if n == 0:
        return {"and": 0.0, "or": 0.0, "xor": 0.0}

    and_correct = 0
    or_correct = 0
    xor_correct = 0

    for i in range(n):
        freq = freqs[i]
        cat = categories[i]

        # Enrollment check: freq near this plate's STRONG peaks
        a_enrolled = any(
            abs(freq - sp) / max(freq, sp) < 0.03 for sp in strong_a
        )
        b_enrolled = any(
            abs(freq - sp) / max(freq, sp) < 0.03 for sp in strong_b
        )

        det_a = 1 if (a_enrolled and mags_a[i] > thresh_a) else 0
        det_b = 1 if (b_enrolled and mags_b[i] > thresh_b) else 0

        hw_and = det_a & det_b
        hw_or = det_a | det_b
        hw_xor = det_a ^ det_b

        if cat == "shared":
            exp_and, exp_xor = 1, 0
        else:
            exp_and, exp_xor = 0, 1
        exp_or = 1

        if hw_and == exp_and:
            and_correct += 1
        if hw_or == exp_or:
            or_correct += 1
        if hw_xor == exp_xor:
            xor_correct += 1

    return {
        "and": round(and_correct / n * 100, 1),
        "or": round(or_correct / n * 100, 1),
        "xor": round(xor_correct / n * 100, 1),
    }


def _plate_detection_threshold(strong_peaks_list, strong_mags_dict, pid,
                               mags_measured, freqs_measured):
    """Compute V5 detection threshold for a plate.

    = 50% of the weakest strong peak's self-response magnitude during
    the main-phase measurement.
    """
    min_self = float('inf')
    for i, freq in enumerate(freqs_measured):
        is_strong = any(
            abs(freq - sp) / max(freq, sp) < 0.03
            for sp in strong_peaks_list
        )
        if is_strong:
            min_self = min(min_self, mags_measured[i])
    if min_self == float('inf'):
        # Fallback: use 50% of weakest from pre-scan
        if strong_mags_dict:
            min_self = min(strong_mags_dict.values())
        else:
            min_self = 100_000
    return min_self * 0.5


def block_boolean_pairs(handle, mux, enrolled, plate_names, plate_ids,
                        enrolled_mags=None,
                        prescan=None, prescan_mags=None) -> dict:
    """AND/OR/XOR via spectral superposition for all plate pairs.

    If prescan/prescan_mags are provided (from _prescan_strong_peaks),
    uses V5 pre-scan-filtered Boolean detection. Otherwise falls back
    to adaptive 15%-enrollment thresholding.
    """
    log("\n" + "=" * 65)
    log("  BLOCK 2: BOOLEAN ALL PAIRS"
        + (" (V5 pre-scan filtered)" if prescan else ""))
    log("=" * 65)

    t0 = time.time()
    pairs = []
    fidelities = []

    for pa, pb in combinations(plate_ids, 2):
        na, nb = plate_names[pa], plate_names[pb]

        # Use strong peaks if available, else full enrollment
        freqs_a = prescan[pa] if prescan else enrolled[pa]
        freqs_b = prescan[pb] if prescan else enrolled[pb]
        classified = _classify_frequencies(freqs_a, freqs_b)

        log(f"\n  Pair: Plate {na} × Plate {nb}")
        log(f"    A-only: {classified['n_a_only']}, "
            f"B-only: {classified['n_b_only']}, "
            f"Shared: {classified['n_shared']}")

        # Build frequency list with category labels
        all_freqs = []
        categories = []
        for f in classified["a_only"]:
            all_freqs.append(f)
            categories.append("a_only")
        for f in classified["b_only"]:
            all_freqs.append(f)
            categories.append("b_only")
        for fa, _ in classified["shared"]:
            all_freqs.append(fa)
            categories.append("shared")

        # Measure plate A at all freqs (own relay)
        mags_a = []
        mux.select(int(pa))
        time.sleep(SETTLE_RELAY_S)
        for freq in all_freqs:
            m = _measure_at(handle, freq)
            mags_a.append(m["magnitude"])

        # Measure plate B at all freqs (own relay)
        mags_b = []
        mux.select(int(pb))
        time.sleep(SETTLE_RELAY_S)
        for freq in all_freqs:
            m = _measure_at(handle, freq)
            mags_b.append(m["magnitude"])

        if prescan and prescan_mags:
            # V5: detection threshold = 50% of weakest strong peak's
            # self-response during this measurement pass
            thresh_a = _plate_detection_threshold(
                prescan[pa], prescan_mags[pa], pa, mags_a, all_freqs)
            thresh_b = _plate_detection_threshold(
                prescan[pb], prescan_mags[pb], pb, mags_b, all_freqs)

            fid = _boolean_fidelity_v5(
                mags_a, mags_b, categories, all_freqs,
                prescan[pa], prescan[pb], thresh_a, thresh_b)
        else:
            # Legacy fallback (adaptive 15% enrollment threshold)
            def _enroll_mag(pid, freq):
                if enrolled_mags is None:
                    return None
                for j, ef in enumerate(enrolled[pid]):
                    if abs(freq - ef) / max(freq, ef) * 100 < FREQ_MATCH_PCT:
                        return enrolled_mags[pid][j]
                return 0.0

            enroll_a = [_enroll_mag(pa, f) for f in all_freqs]
            enroll_b = [_enroll_mag(pb, f) for f in all_freqs]

            n = len(categories)
            bit_a, bit_b = [], []
            for i in range(n):
                ta = enroll_a[i] * 0.15 if enroll_a[i] and enroll_a[i] > 0 else 100_000
                tb = enroll_b[i] * 0.15 if enroll_b[i] and enroll_b[i] > 0 else 100_000
                bit_a.append(1 if mags_a[i] > ta else 0)
                bit_b.append(1 if mags_b[i] > tb else 0)

            and_c = or_c = xor_c = 0
            for i in range(n):
                cat = categories[i]
                ha, hb = bit_a[i] & bit_b[i], bit_a[i] | bit_b[i]
                hx = bit_a[i] ^ bit_b[i]
                ea, ex = (1, 0) if cat == "shared" else (0, 1)
                if ha == ea: and_c += 1
                if hb == 1: or_c += 1
                if hx == ex: xor_c += 1
            fid = {
                "and": round(and_c / n * 100, 1) if n else 0,
                "or": round(or_c / n * 100, 1) if n else 0,
                "xor": round(xor_c / n * 100, 1) if n else 0,
            }

        mean_fid = round((fid["and"] + fid["or"] + fid["xor"]) / 3, 1)
        fidelities.append(mean_fid)

        log(f"    Fidelity: AND={fid['and']}%, OR={fid['or']}%, "
            f"XOR={fid['xor']}%, mean={mean_fid}%")

        pairs.append({
            "pair": f"{na}-{nb}",
            "n_a_only": classified["n_a_only"],
            "n_b_only": classified["n_b_only"],
            "n_shared": classified["n_shared"],
            "fidelity_and": fid["and"],
            "fidelity_or": fid["or"],
            "fidelity_xor": fid["xor"],
            "fidelity_mean": mean_fid,
        })

    mux.off()
    overall = round(float(np.mean(fidelities)), 1) if fidelities else 0.0
    worst = round(min(fidelities), 1) if fidelities else 0.0
    duration = round(time.time() - t0, 1)

    log(f"\n  Boolean fidelity: mean={overall}%, worst={worst}%")

    return {
        "block": "boolean-pairs", "pairs": pairs,
        "method": "prescan-v5" if prescan else "adaptive-15pct",
        "mean_fidelity": overall, "worst_fidelity": worst,
        "duration_s": duration,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Block 3: Nearest-Neighbor (Cross-Relay)
# ═══════════════════════════════════════════════════════════════════════

def block_nn_pairs(handle, mux, enrolled, plate_names, plate_ids) -> dict:
    """For each plate, identify via cross-relay template matching."""
    log("\n" + "=" * 65)
    log("  BLOCK 3: NEAREST-NEIGHBOR (cross-relay)")
    log("=" * 65)

    t0 = time.time()
    queries = []
    correct = 0
    margins = []

    for qpid in plate_ids:
        qname = plate_names[qpid]
        query_freqs = enrolled[qpid][:N_PEAKS]

        log(f"\n  Query: Plate {qname} ({len(query_freqs)} freqs)")

        # Cross-relay: for EACH query frequency, measure on ALL plates' relays
        raw_mags = {pid: [] for pid in plate_ids}
        for freq in query_freqs:
            for pid in plate_ids:
                mux.select(int(pid))
                time.sleep(SETTLE_RELAY_S)
                m = _measure_at(handle, freq)
                raw_mags[pid].append(m["magnitude"])
        mux.off()

        scores = _template_score(query_freqs, raw_mags, enrolled, plate_ids)
        winner = max(scores, key=scores.get)
        is_correct = winner == qpid
        margin = scores[qpid] - max(v for k, v in scores.items() if k != qpid)

        if is_correct:
            correct += 1
        margins.append(margin)

        score_strs = ", ".join(
            f"{plate_names[p]}:{scores[p]:+.2f}" for p in plate_ids
        )
        log(f"    Winner: Plate {plate_names[winner]} "
            f"({'✓' if is_correct else '✗'})  margin={margin:+.2f}")
        log(f"    Scores: [{score_strs}]")

        queries.append({
            "query": qname, "winner": plate_names[winner],
            "correct": is_correct, "margin": round(margin, 2),
            "scores": {plate_names[p]: scores[p] for p in plate_ids},
        })

    accuracy = round(correct / len(plate_ids) * 100, 1)
    mean_margin = round(float(np.mean(margins)), 2)
    duration = round(time.time() - t0, 1)

    log(f"\n  NN accuracy: {correct}/{len(plate_ids)} ({accuracy}%), "
        f"mean margin={mean_margin:+.2f}")

    return {
        "block": "nn-pairs", "queries": queries,
        "accuracy": accuracy, "correct": correct, "total": len(plate_ids),
        "mean_margin": mean_margin, "duration_s": duration,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Block 4: 3-Plate Boolean
# ═══════════════════════════════════════════════════════════════════════

def block_3plate_boolean(handle, mux, enrolled, plate_names, plate_ids,
                         enrolled_mags=None,
                         prescan=None, prescan_mags=None) -> dict:
    """AND/OR/XOR across 3 plates simultaneously."""
    log("\n" + "=" * 65)
    log("  BLOCK 4: 3-PLATE BOOLEAN"
        + (" (V5 pre-scan filtered)" if prescan else ""))
    log("=" * 65)

    t0 = time.time()
    triples_data = []
    fidelities = []
    triples = list(combinations(plate_ids, 3))[:10]

    for pa, pb, pc in triples:
        na, nb, nc = plate_names[pa], plate_names[pb], plate_names[pc]
        log(f"\n  Triple: {na} × {nb} × {nc}")

        # Union of strong (or enrolled) frequencies with ownership tracking
        freq_owners = {}  # freq → set of plate_ids that own it
        for pid in [pa, pb, pc]:
            src = prescan[pid] if prescan else enrolled[pid]
            for f in src:
                matched = False
                for existing in freq_owners:
                    if abs(f - existing) / max(f, existing) < 0.03:
                        freq_owners[existing].add(pid)
                        matched = True
                        break
                if not matched:
                    freq_owners[f] = {pid}

        all_freqs = sorted(freq_owners.keys())

        # Measure each plate at all freqs
        mags = {}
        for pid in [pa, pb, pc]:
            mux.select(int(pid))
            time.sleep(SETTLE_RELAY_S)
            mags[pid] = []
            for freq in all_freqs:
                m = _measure_at(handle, freq)
                mags[pid].append(m["magnitude"])

        # 3-way Boolean fidelity
        n = len(all_freqs)
        and3_correct = 0
        or3_correct = 0

        if prescan and prescan_mags:
            # V5: per-plate detection threshold
            thresholds = {}
            for pid in [pa, pb, pc]:
                thresholds[pid] = _plate_detection_threshold(
                    prescan[pid], prescan_mags[pid], pid,
                    mags[pid], all_freqs)

            for i, freq in enumerate(all_freqs):
                owners = freq_owners[freq]
                n_owners = len(owners)
                bits = []
                for pid in [pa, pb, pc]:
                    is_strong = any(
                        abs(freq - sp) / max(freq, sp) < 0.03
                        for sp in prescan[pid]
                    )
                    bits.append(1 if (is_strong and mags[pid][i] > thresholds[pid]) else 0)
                hw_and3 = bits[0] & bits[1] & bits[2]
                hw_or3 = bits[0] | bits[1] | bits[2]
                exp_and3 = 1 if n_owners == 3 else 0
                exp_or3 = 1
                if hw_and3 == exp_and3:
                    and3_correct += 1
                if hw_or3 == exp_or3:
                    or3_correct += 1
        else:
            # Legacy adaptive threshold
            def _get_enroll_mag(pid, freq):
                if enrolled_mags is None:
                    return None
                for j, ef in enumerate(enrolled[pid]):
                    if abs(freq - ef) / max(freq, ef) * 100 < FREQ_MATCH_PCT:
                        return enrolled_mags[pid][j]
                return 0.0

            for i, freq in enumerate(all_freqs):
                owners = freq_owners[freq]
                n_owners = len(owners)
                bits = []
                for pid in [pa, pb, pc]:
                    emag = _get_enroll_mag(pid, freq)
                    if emag is not None and emag > 0:
                        threshold = emag * 0.15
                    else:
                        threshold = max(mags[pid]) * 0.25 if mags[pid] else 1
                    bits.append(1 if mags[pid][i] > threshold else 0)
                hw_and3 = bits[0] & bits[1] & bits[2]
                hw_or3 = bits[0] | bits[1] | bits[2]
                exp_and3 = 1 if n_owners == 3 else 0
                exp_or3 = 1
                if hw_and3 == exp_and3:
                    and3_correct += 1
                if hw_or3 == exp_or3:
                    or3_correct += 1

        and3_fid = round(and3_correct / n * 100, 1) if n else 0
        or3_fid = round(or3_correct / n * 100, 1) if n else 0
        mean_fid = round((and3_fid + or3_fid) / 2, 1)
        fidelities.append(mean_fid)

        log(f"    Fidelity: AND3={and3_fid}%, OR3={or3_fid}%, mean={mean_fid}%")

        triples_data.append({
            "triple": f"{na}-{nb}-{nc}", "n_freqs": n,
            "fidelity_and3": and3_fid, "fidelity_or3": or3_fid,
            "fidelity_mean": mean_fid,
        })

    mux.off()
    overall = round(float(np.mean(fidelities)), 1) if fidelities else 0.0
    duration = round(time.time() - t0, 1)

    log(f"\n  3-plate Boolean overall fidelity: {overall}%")

    return {
        "block": "3plate-boolean",
        "method": "prescan-v5" if prescan else "adaptive-15pct",
        "n_triples": len(triples_data),
        "mean_fidelity": overall,
        "triples": triples_data,
        "duration_s": duration,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Block 5: Chained Boolean
# ═══════════════════════════════════════════════════════════════════════

def block_chained(handle, mux, enrolled, plate_names, plate_ids,
                  enrolled_mags=None,
                  prescan=None, prescan_mags=None) -> dict:
    """(A AND B) XOR C — two-stage Boolean computation."""
    log("\n" + "=" * 65)
    log("  BLOCK 5: CHAINED BOOLEAN"
        + (" (V5 pre-scan filtered)" if prescan else ""))
    log("=" * 65)

    t0 = time.time()

    if len(plate_ids) < 3:
        log("  Need at least 3 plates, skipping")
        return {"block": "chained", "skipped": True, "duration_s": 0}

    pa, pb, pc = plate_ids[0], plate_ids[1], plate_ids[2]
    na, nb, nc = plate_names[pa], plate_names[pb], plate_names[pc]
    log(f"  Chain: ({na} AND {nb}) XOR {nc}")

    # Build freq list with ownership (from strong peaks if available)
    freq_owners = {}
    for pid in [pa, pb, pc]:
        src = prescan[pid] if prescan else enrolled[pid]
        for f in src:
            matched = False
            for existing in freq_owners:
                if abs(f - existing) / max(f, existing) < 0.03:
                    freq_owners[existing].add(pid)
                    matched = True
                    break
            if not matched:
                freq_owners[f] = {pid}

    all_freqs = sorted(freq_owners.keys())

    mags = {}
    for pid in [pa, pb, pc]:
        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)
        mags[pid] = []
        for freq in all_freqs:
            m = _measure_at(handle, freq)
            mags[pid].append(m["magnitude"])

    mux.off()

    n = len(all_freqs)
    chain_correct = 0

    if prescan and prescan_mags:
        # V5: per-plate detection thresholds
        thresholds = {}
        for pid in [pa, pb, pc]:
            thresholds[pid] = _plate_detection_threshold(
                prescan[pid], prescan_mags[pid], pid,
                mags[pid], all_freqs)

        for i, freq in enumerate(all_freqs):
            owners = freq_owners[freq]
            bits = {}
            for pid in [pa, pb, pc]:
                is_strong = any(
                    abs(freq - sp) / max(freq, sp) < 0.03
                    for sp in prescan[pid]
                )
                bits[pid] = 1 if (is_strong and mags[pid][i] > thresholds[pid]) else 0

            hw_chain = (bits[pa] & bits[pb]) ^ bits[pc]
            a_owns = 1 if pa in owners else 0
            b_owns = 1 if pb in owners else 0
            c_owns = 1 if pc in owners else 0
            exp_chain = (a_owns & b_owns) ^ c_owns
            if hw_chain == exp_chain:
                chain_correct += 1
    else:
        # Legacy adaptive threshold
        def _get_enroll_mag(pid, freq):
            if enrolled_mags is None:
                return None
            for j, ef in enumerate(enrolled[pid]):
                if abs(freq - ef) / max(freq, ef) * 100 < FREQ_MATCH_PCT:
                    return enrolled_mags[pid][j]
            return 0.0

        for i, freq in enumerate(all_freqs):
            owners = freq_owners[freq]
            bits = {}
            for pid in [pa, pb, pc]:
                emag = _get_enroll_mag(pid, freq)
                if emag is not None and emag > 0:
                    threshold = emag * 0.15
                else:
                    threshold = max(mags[pid]) * 0.25 if mags[pid] else 1
                bits[pid] = 1 if mags[pid][i] > threshold else 0

            hw_chain = (bits[pa] & bits[pb]) ^ bits[pc]
            a_owns = 1 if pa in owners else 0
            b_owns = 1 if pb in owners else 0
            c_owns = 1 if pc in owners else 0
            exp_chain = (a_owns & b_owns) ^ c_owns
            if hw_chain == exp_chain:
                chain_correct += 1

    fidelity = round(chain_correct / n * 100, 1) if n else 0
    duration = round(time.time() - t0, 1)

    log(f"  Chained fidelity: {fidelity}% ({chain_correct}/{n})")

    return {
        "block": "chained",
        "method": "prescan-v5" if prescan else "adaptive-15pct",
        "plates": [na, nb, nc],
        "operation": f"({na} AND {nb}) XOR {nc}",
        "n_freqs": n, "n_correct": chain_correct,
        "fidelity": fidelity, "duration_s": duration,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Block 6: Noise Robustness (Drive Voltage Sweep)
# ═══════════════════════════════════════════════════════════════════════

def block_noise(handle, mux, enrolled, plate_names, plate_ids) -> dict:
    """Sweep drive voltage from 100% down to 10%, measure recall fidelity."""
    log("\n" + "=" * 65)
    log("  BLOCK 6: NOISE ROBUSTNESS (drive voltage sweep)")
    log("=" * 65)

    t0 = time.time()
    drive_fractions = [1.0, 0.75, 0.50, 0.25, 0.10]
    sweep_results = []
    floor_pct = 100.0  # will track lowest drive % with correct NN

    # Baseline: cross-relay NN at full drive
    log(f"\n  Baseline: full-drive cross-relay NN on {len(plate_ids)} plates")

    pid0 = plate_ids[0]
    name0 = plate_names[pid0]
    query_freqs = enrolled[pid0][:N_PEAKS]

    for frac in drive_fractions:
        drive_uv = int(AWG_DRIVE_UVPP * frac)
        log(f"\n  Drive {frac*100:.0f}% ({drive_uv} µVpp):")

        raw_mags = {pid: [] for pid in plate_ids}
        for freq in query_freqs:
            for pid in plate_ids:
                mux.select(int(pid))
                time.sleep(SETTLE_RELAY_S)
                m = _measure_at(handle, freq, drive_uvpp=drive_uv)
                raw_mags[pid].append(m["magnitude"])
        mux.off()

        scores = _template_score(query_freqs, raw_mags, enrolled, plate_ids)
        winner = max(scores, key=scores.get)
        is_correct = winner == pid0
        margin = scores[pid0] - max(v for k, v in scores.items() if k != pid0)

        # Also compute correlation of this plate's magnitudes against baseline
        if frac == 1.0:
            baseline_mags = raw_mags[pid0][:]
        corr = float(np.corrcoef(baseline_mags, raw_mags[pid0])[0, 1]) \
            if baseline_mags and raw_mags[pid0] else 0.0

        if is_correct:
            floor_pct = frac * 100

        log(f"    Winner: {plate_names[winner]} "
            f"({'✓' if is_correct else '✗'})  "
            f"margin={margin:+.2f}  corr={corr:.4f}")

        sweep_results.append({
            "drive_pct": round(frac * 100, 0),
            "drive_uvpp": drive_uv,
            "winner": plate_names[winner],
            "correct": is_correct,
            "margin": round(margin, 2),
            "correlation": round(corr, 4),
        })

    duration = round(time.time() - t0, 1)
    log(f"\n  Noise floor: correct recall down to {floor_pct}% drive")

    return {
        "block": "noise", "query_plate": name0,
        "sweep": sweep_results, "noise_floor_pct": floor_pct,
        "duration_s": duration,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Firestore submission helper
# ═══════════════════════════════════════════════════════════════════════

FIRESTORE_COLLECTION = "exp-plate-cim-suite"


def _submit_block(token, block_data: dict, dry_run: bool) -> dict | None:
    """Submit one block's summary to Firestore as a single document."""
    block = block_data["block"]
    n_plates = block_data.get("total", 5)  # default

    data = {
        "block_name": block,
        "n_plates": n_plates,
        "duration_s": block_data.get("duration_s", 0),
    }

    if block == "temporal":
        data["n_plates"] = len(block_data.get("plates", []))
        data["recall_accuracy"] = block_data.get("recall_pct", 0)
        notes = (f"Temporal stability: {block_data.get('total_alive', 0)}/"
                 f"{block_data.get('total_enrolled', 0)} modes alive "
                 f"({block_data.get('recall_pct', 0)}%)")

    elif block == "boolean-pairs":
        data["boolean_fidelity"] = block_data.get("mean_fidelity", 0)
        n = len(block_data.get("pairs", []))
        data["n_plates"] = 5
        notes = (f"Boolean all pairs: {n} pairs, "
                 f"mean fidelity {block_data.get('mean_fidelity', 0)}%, "
                 f"worst {block_data.get('worst_fidelity', 0)}%")

    elif block == "nn-pairs":
        data["recall_accuracy"] = block_data.get("accuracy", 0)
        data["n_plates"] = block_data.get("total", 5)
        notes = (f"NN cross-relay: {block_data.get('correct', 0)}/"
                 f"{block_data.get('total', 0)} correct "
                 f"({block_data.get('accuracy', 0)}%), "
                 f"mean margin {block_data.get('mean_margin', 0):+.2f}")

    elif block == "3plate-boolean":
        data["boolean_fidelity"] = block_data.get("mean_fidelity", 0)
        data["n_plates"] = 5
        notes = (f"3-plate Boolean: mean fidelity "
                 f"{block_data.get('mean_fidelity', 0)}%")

    elif block == "chained":
        data["boolean_fidelity"] = block_data.get("fidelity", 0)
        data["n_plates"] = 3
        notes = (f"Chained Boolean: {block_data.get('operation', '?')} "
                 f"fidelity {block_data.get('fidelity', 0)}%")

    elif block == "noise":
        data["noise_floor_pct"] = block_data.get("noise_floor_pct", 0)
        # Get correlation at full drive (should be 1.0)
        sweep = block_data.get("sweep", [])
        if sweep:
            data["correlation"] = sweep[-1].get("correlation", 0)
        data["n_plates"] = 5
        notes = (f"Noise robustness: correct recall down to "
                 f"{block_data.get('noise_floor_pct', 0)}% drive")
    else:
        notes = f"CIM block: {block}"

    if dry_run:
        log(f"  [DRY] Would submit {block}: {data}")
        return None

    r = submit_experiment(token, FIRESTORE_COLLECTION, data, notes=notes)
    return r


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

ALL_BLOCKS = {
    "temporal": "Temporal stability",
    "boolean-pairs": "Boolean all pairs",
    "nn-pairs": "NN all pairs (cross-relay)",
    "3plate-boolean": "3-plate Boolean",
    "chained": "Chained Boolean",
    "noise": "Noise robustness",
}


def main():
    parser = argparse.ArgumentParser(
        description="Plate CIM experiment suite"
    )
    parser.add_argument(
        "--only", type=str, default=None,
        help="Comma-separated list of blocks to run (default: all)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Don't submit to Firestore"
    )
    parser.add_argument(
        "--no-submit", action="store_true",
        help="Save locally but don't submit to Firestore"
    )
    parser.add_argument(
        "--port", type=str, default="/dev/cu.usbserial-11310",
        help="Serial port for relay mux"
    )
    parser.add_argument(
        "--census", type=str, default=None,
        help="Path to census JSON (default: latest plate_census_*.json)"
    )
    args = parser.parse_args()

    skip_submit = args.dry_run or args.no_submit

    blocks = list(ALL_BLOCKS.keys())
    if args.only:
        blocks = [b.strip() for b in args.only.split(",")]

    log("\n" + "=" * 70)
    log("  PLATE CIM EXPERIMENT SUITE")
    log(f"  Blocks: {', '.join(blocks)}")
    log("=" * 70)

    handle = _open_scope()
    mux = RelayMux(port=args.port)
    mux.open()
    log(f"Relay mux connected on {mux.port}")

    enrolled, plate_names, enrolled_mags, plate_ids = _load_enrollment(
        census_path=args.census)

    block_results = {}
    suite_t0 = time.time()

    # Run pre-scan once if any Boolean block is requested
    prescan = None
    prescan_mags = None
    bool_blocks = {"boolean-pairs", "3plate-boolean", "chained"}
    if bool_blocks & set(blocks):
        prescan, prescan_mags = _prescan_strong_peaks(
            handle, mux, enrolled, plate_names, plate_ids)

    try:
        if "temporal" in blocks:
            block_results["temporal"] = block_temporal(
                handle, mux, enrolled, plate_names, plate_ids)
        if "boolean-pairs" in blocks:
            block_results["boolean-pairs"] = block_boolean_pairs(
                handle, mux, enrolled, plate_names, plate_ids,
                enrolled_mags=enrolled_mags,
                prescan=prescan, prescan_mags=prescan_mags)
        if "nn-pairs" in blocks:
            block_results["nn-pairs"] = block_nn_pairs(
                handle, mux, enrolled, plate_names, plate_ids)
        if "3plate-boolean" in blocks:
            block_results["3plate-boolean"] = block_3plate_boolean(
                handle, mux, enrolled, plate_names, plate_ids,
                enrolled_mags=enrolled_mags,
                prescan=prescan, prescan_mags=prescan_mags)
        if "chained" in blocks:
            block_results["chained"] = block_chained(
                handle, mux, enrolled, plate_names, plate_ids,
                enrolled_mags=enrolled_mags,
                prescan=prescan, prescan_mags=prescan_mags)
        if "noise" in blocks:
            block_results["noise"] = block_noise(
                handle, mux, enrolled, plate_names, plate_ids)
    finally:
        _close_scope(handle)
        mux.close()

    suite_duration = round(time.time() - suite_t0, 1)

    # ── Save locally ──────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "blocks_run": blocks,
        "n_plates": len(plate_ids),
        "duration_s": suite_duration,
        "results": block_results,
    }
    with open(RESULTS_FILE, "w") as fw:
        json.dump(save_payload, fw, indent=2, default=str)
    log(f"\n  Saved: {RESULTS_FILE}")

    # ── Submit to Firestore (one doc per block) ───────────────────────
    log("\n" + "=" * 65)
    log("  FIRESTORE SUBMISSION")
    log("=" * 65)

    if not skip_submit:
        try:
            token = firebase_anon_auth()
            log("  ✓ Firebase auth OK")
        except Exception as e:
            log(f"  ✗ Auth failed: {e}")
            token = None

        if token:
            for bname, bdata in block_results.items():
                r = _submit_block(token, bdata, dry_run=False)
                if r:
                    status = "✓" if r.get("ok") else "✗"
                    doc_id = r.get("id", r.get("error", "?"))
                    log(f"  {bname}: {status} {doc_id}")
                    print_result(r)
                time.sleep(1)  # respect rate limit
    else:
        log("  Skipped (--dry-run or --no-submit)")

    # ── Summary ───────────────────────────────────────────────────────
    log(f"\n{'=' * 65}")
    log(f"  SUITE SUMMARY ({suite_duration}s)")
    log(f"{'=' * 65}")

    for bname, bdata in block_results.items():
        btype = bdata.get("block", bname)
        if btype == "temporal":
            log(f"  Temporal:     {bdata.get('recall_pct', '?')}% modes alive")
        elif btype == "boolean-pairs":
            log(f"  Boolean:      {bdata.get('mean_fidelity', '?')}% mean fidelity")
        elif btype == "nn-pairs":
            log(f"  NN:           {bdata.get('accuracy', '?')}% accuracy, "
                f"margin {bdata.get('mean_margin', '?'):+.2f}")
        elif btype == "3plate-boolean":
            log(f"  3-plate:      {bdata.get('mean_fidelity', '?')}% mean fidelity")
        elif btype == "chained":
            log(f"  Chained:      {bdata.get('fidelity', '?')}% fidelity")
        elif btype == "noise":
            log(f"  Noise floor:  {bdata.get('noise_floor_pct', '?')}% drive")

    _save_log()
    log(f"\n  Log: {LOG_FILE}")


if __name__ == "__main__":
    main()
