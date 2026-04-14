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

def _load_enrollment() -> tuple[dict, dict, dict, list]:
    """Load plate enrollment from latest census file.

    Returns (enrolled_freqs, plate_names, enrolled_mags, plate_ids).
    enrolled_mags maps plate_id -> list of magnitudes (same order as enrolled_freqs).
    """
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        raise FileNotFoundError("No census file found. Run plate_mode_census.py first.")

    with open(census_files[-1]) as f:
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

def _boolean_fidelity(mags_a, mags_b, categories,
                      enroll_mags_a=None, enroll_mags_b=None):
    """Compute Boolean fidelity against expected truth tables.

    categories[i] = 'a_only' | 'b_only' | 'shared'

    Truth tables (magnitude-based):
      AND:  shared → expect both high (1), else 0
      OR:   any → expect at least one high (1), always 1 for our freqs
      XOR:  a_only or b_only → expect 1, shared → expect 0

    Adaptive thresholding: if enroll_mags_a/b are provided, each frequency
    gets its own threshold = 15% of that plate's enrollment magnitude at
    that frequency. This calibrates against per-frequency sensitivity
    rather than using a global max.
    """
    n = len(categories)
    if n == 0:
        return {"and": 0.0, "or": 0.0, "xor": 0.0}

    if enroll_mags_a is not None and enroll_mags_b is not None:
        # Adaptive: per-frequency threshold from enrollment data
        bit_a = []
        bit_b = []
        for i in range(n):
            # Plate A: "active" if live mag > 15% of its enrollment mag
            thresh_a_i = enroll_mags_a[i] * 0.15 if enroll_mags_a[i] > 0 else 100_000
            thresh_b_i = enroll_mags_b[i] * 0.15 if enroll_mags_b[i] > 0 else 100_000
            bit_a.append(1 if mags_a[i] > thresh_a_i else 0)
            bit_b.append(1 if mags_b[i] > thresh_b_i else 0)
    else:
        # Fallback: global 25% of max
        max_a = max(mags_a) if mags_a else 1
        max_b = max(mags_b) if mags_b else 1
        thresh_a = max_a * 0.25
        thresh_b = max_b * 0.25
        bit_a = [1 if m > thresh_a else 0 for m in mags_a]
        bit_b = [1 if m > thresh_b else 0 for m in mags_b]

    and_correct = 0
    or_correct = 0
    xor_correct = 0
    for i in range(n):
        cat = categories[i]
        a, b = bit_a[i], bit_b[i]
        hw_and = a & b
        hw_or = a | b
        hw_xor = a ^ b
        # Expected from categories
        if cat == "shared":
            exp_and, exp_xor = 1, 0
        else:
            exp_and, exp_xor = 0, 1
        exp_or = 1  # all tested freqs are in at least one enrollment
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


def block_boolean_pairs(handle, mux, enrolled, plate_names, plate_ids,
                        enrolled_mags=None) -> dict:
    """AND/OR/XOR via spectral superposition for all plate pairs."""
    log("\n" + "=" * 65)
    log("  BLOCK 2: BOOLEAN ALL PAIRS")
    log("=" * 65)

    t0 = time.time()
    pairs = []
    fidelities = []

    for pa, pb in combinations(plate_ids, 2):
        na, nb = plate_names[pa], plate_names[pb]
        log(f"\n  Pair: Plate {na} × Plate {nb}")

        freqs_a = enrolled[pa]
        freqs_b = enrolled[pb]
        classified = _classify_frequencies(freqs_a, freqs_b)

        log(f"    A-only: {classified['n_a_only']}, "
            f"B-only: {classified['n_b_only']}, "
            f"Shared: {classified['n_shared']}")

        # Build enrollment magnitude lookup for adaptive thresholding
        def _enroll_mag(pid, freq):
            """Get enrollment magnitude for a plate at a given frequency."""
            if enrolled_mags is None:
                return None
            for i, ef in enumerate(enrolled[pid]):
                if abs(freq - ef) / max(freq, ef) * 100 < FREQ_MATCH_PCT:
                    return enrolled_mags[pid][i]
            return 0.0  # not enrolled → zero reference

        # Build frequency list with category labels
        all_freqs = []
        categories = []
        enroll_a = []  # enrollment magnitudes for plate A at each freq
        enroll_b = []  # enrollment magnitudes for plate B at each freq
        for f in classified["a_only"]:
            all_freqs.append(f)
            categories.append("a_only")
            enroll_a.append(_enroll_mag(pa, f))
            enroll_b.append(_enroll_mag(pb, f))
        for f in classified["b_only"]:
            all_freqs.append(f)
            categories.append("b_only")
            enroll_a.append(_enroll_mag(pa, f))
            enroll_b.append(_enroll_mag(pb, f))
        for fa, _ in classified["shared"]:
            all_freqs.append(fa)
            categories.append("shared")
            enroll_a.append(_enroll_mag(pa, fa))
            enroll_b.append(_enroll_mag(pb, fa))

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

        fid = _boolean_fidelity(mags_a, mags_b, categories,
                               enroll_mags_a=enroll_a if enrolled_mags else None,
                               enroll_mags_b=enroll_b if enrolled_mags else None)
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
                         enrolled_mags=None) -> dict:
    """AND/OR/XOR across 3 plates simultaneously."""
    log("\n" + "=" * 65)
    log("  BLOCK 4: 3-PLATE BOOLEAN")
    log("=" * 65)

    t0 = time.time()
    triples_data = []
    fidelities = []
    triples = list(combinations(plate_ids, 3))[:10]

    def _get_enroll_mag(pid, freq):
        """Lookup enrollment magnitude for adaptive threshold."""
        if enrolled_mags is None:
            return None
        for j, ef in enumerate(enrolled[pid]):
            if abs(freq - ef) / max(freq, ef) * 100 < FREQ_MATCH_PCT:
                return enrolled_mags[pid][j]
        return 0.0

    for pa, pb, pc in triples:
        na, nb, nc = plate_names[pa], plate_names[pb], plate_names[pc]
        log(f"\n  Triple: {na} × {nb} × {nc}")

        # Union of enrolled frequencies with category tracking
        freq_owners = {}  # freq → set of plate_ids that own it
        for pid in [pa, pb, pc]:
            for f in enrolled[pid]:
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

        # 3-way Boolean fidelity: AND3 expects all 3 own the freq
        n = len(all_freqs)
        and3_correct = 0
        or3_correct = 0
        for i, freq in enumerate(all_freqs):
            owners = freq_owners[freq]
            n_owners = len(owners)
            # Binarise per-plate with adaptive threshold
            bits = []
            for pid in [pa, pb, pc]:
                emag = _get_enroll_mag(pid, freq)
                if emag is not None and emag > 0:
                    threshold = emag * 0.15
                else:
            # 3-way Boolean fidelity: AND3 expects all 3 own the freq
        n = len(all_freqs)
        and3_correct = 0
        or3_correct = 0
        for i, freq in enumerate(all_freqs):
            owners = freq_owners[freq]
            n_owners = len(owners)
            # Binarise per-plate with adaptive threshold
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
            exp_or3 = 1  # all freqs belong to at least one plate
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
    duration = round(time.time() - t0, 1),
                  enrolled_mags=None) -> dict:
    """(A AND B) XOR C — two-stage Boolean computation."""
    log("\n" + "=" * 65)
    log("  BLOCK 5: CHAINED BOOLEAN")
    log("=" * 65)

    t0 = time.time()

    if len(plate_ids) < 3:
        log("  Need at least 3 plates, skipping")
        return {"block": "chained", "skipped": True, "duration_s": 0}

    pa, pb, pc = plate_ids[0], plate_ids[1], plate_ids[2]
    na, nb, nc = plate_names[pa], plate_names[pb], plate_names[pc]
    log(f"  Chain: ({na} AND {nb}) XOR {nc}")

    def _get_enroll_mag(pid, freq):
        if enrolled_mags is None:
            return None
        for j, ef in enumerate(enrolled[pid]):
            if abs(freq - ef) / max(freq, ef) * 100 < FREQ_MATCH_PCT:
                return enrolled_mags[pid][j]
        return 0.0e_names, plate_ids,
                  enrolled_mags=None) -> dict:
    """(A AND B) XOR C — two-stage Boolean computation."""
    log("\n" + "=" * 65)
    log("  BLOCK 5: CHAINED BOOLEAN")
    log("=" * 65)

    t0 = time.time()

    if len(plate_ids) < 3:
        log("  Need at least 3 plates, skipping")
        return {"block": "chained", "skipped": True, "duration_s": 0}

    pa, pb, pc = plate_ids[0], plate_ids[1], plate_ids[2]
    na, nb, nc = plate_names[pa], plate_names[pb], plate_names[pc]
    log(f"  Chain: ({na} AND {nb}) XOR {nc}")

    def _get_enroll_mag(pid, freq):
        if enrolled_mags is None:
            return None
        for j, ef in enumerate(enrolled[pid]):
            if abs(freq - ef) / max(freq, ef) * 100 < FREQ_MATCH_PCT:
                return enrolled_mags[pid][j]
        return 0.0

    # Build freq list with ownership
    freq_owners = {}
    for pid in [pa, pb, pc]:
        for f in enrolled[pid]:
            matched = False
            for existing in freq_owners:
                if abs(f - existing) / max(f, existing) < 0.03:
                   with adaptive threshold
        bits = {}
        for pid in [pa, pb, pc]:
            emag = _get_enroll_mag(pid, freq)
            if emag is not None and emag > 0:
                threshold = emag * 0.15
            else:
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
    for i, freq in enumerate(all_freqs):
        owners = freq_owners[freq]
        # Binarise with adaptive threshold
        bits = {}
        for pid in [pa, pb, pc]:
            emag = _get_enroll_mag(pid, freq)
            if emag is not None and emag > 0:
                threshold = emag * 0.15
            else:
                threshold = max(mags[pid]) * 0.25 if mags[pid] else 1
            bits[pid] = 1 if mags[pid][i] > threshold else 0

        hw_chain = (bits[pa] & bits[pb]) ^ bits[pc]

        # Expected: (A owns freq AND B owns freq) XOR (C owns freq)
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

    enrolled, plate_names, enrolled_mags, plate_ids = _load_enrollment()

    block_results = {}
    suite_t0 = time.time()

    try:
        if "temporal" in blocks:
            block_results["temporal"] = block_temporal(
                handle, mux, enrolled, plate_names, plate_ids)
        if "boolean-pairs" in blocks:
            block_results["boolean-pairs"] = block_boolean_pairs(
                handle, mux, enrolled, plate_names, plate_ids,
                enrolled_mags=enrolled_mags)
        if "nn-pairs" in blocks:
            block_results["nn-pairs"] = block_nn_pairs(
                handle, mux, enrolled, plate_names, plate_ids)
        if "3plate-boolean" in blocks:
            block_results["3plate-boolean"] = block_3plate_boolean(
                handle, mux, enrolled, plate_names, plate_ids,
                enrolled_mags=enrolled_mags)
        if "chained" in blocks:
            block_results["chained"] = block_chained(
                handle, mux, enrolled, plate_names, plate_ids,
                enrolled_mags=enrolled_mags)
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
