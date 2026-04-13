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

def _load_enrollment() -> tuple[dict, dict, list]:
    """Load plate enrollment from latest census file."""
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
    plate_names = {}
    for pid in PLATE_IDS:
        if pid in census and census[pid].get("peaks"):
            enrolled[pid] = [p["freq_hz"] for p in census[pid]["peaks"][:N_PEAKS]]
            plate_names[pid] = PLATE_NAMES[pid]

    plate_ids = sorted(enrolled.keys())
    log(f"Loaded enrollment: {len(plate_ids)} plates, {N_PEAKS} peaks each")
    return enrolled, plate_names, plate_ids


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

def block_temporal(handle, mux, enrolled, plate_names, plate_ids,
                   token, dry_run) -> list:
    """Re-measure enrolled frequencies, check for drift."""
    log("\n" + "=" * 65)
    log("  BLOCK 1: TEMPORAL STABILITY")
    log("=" * 65)

    results = []
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

        # Compare: any frequency with magnitude drop > 50% is flagged
        total_mag = sum(live_mags)
        n_alive = sum(1 for m in live_mags if m > 100000)  # threshold

        data = {
            "plate_name": name,
            "n_enrolled": len(freqs),
            "n_alive": n_alive,
            "total_magnitude": round(total_mag, 1),
            "mean_magnitude": round(total_mag / len(freqs), 1) if freqs else 0,
        }
        notes = f"Plate {name} temporal stability: {n_alive}/{len(freqs)} modes alive."

        if dry_run:
            results.append({"ok": True, "dry": True, "plate": name})
        else:
            r = submit_experiment(token, "exp-cim-suite", data, notes=notes)
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Block 2: Boolean All Pairs
# ═══════════════════════════════════════════════════════════════════════

def block_boolean_pairs(handle, mux, enrolled, plate_names, plate_ids,
                        token, dry_run) -> list:
    """AND/OR/XOR via spectral superposition for all plate pairs."""
    log("\n" + "=" * 65)
    log("  BLOCK 2: BOOLEAN ALL PAIRS")
    log("=" * 65)

    results = []
    for pa, pb in combinations(plate_ids, 2):
        na, nb = plate_names[pa], plate_names[pb]
        log(f"\n  Pair: Plate {na} × Plate {nb}")

        freqs_a = enrolled[pa]
        freqs_b = enrolled[pb]
        classified = _classify_frequencies(freqs_a, freqs_b)

        log(f"    A-only: {classified['n_a_only']}, "
            f"B-only: {classified['n_b_only']}, "
            f"Shared: {classified['n_shared']}")

        # Measure each plate at all classified frequencies
        all_freqs = (classified["a_only"] + classified["b_only"]
                     + [s[0] for s in classified["shared"]])

        mags_a = []
        mux.select(int(pa))
        time.sleep(SETTLE_RELAY_S)
        for freq in all_freqs:
            m = _measure_at(handle, freq)
            mags_a.append(m["magnitude"])

        mags_b = []
        mux.select(int(pb))
        time.sleep(SETTLE_RELAY_S)
        for freq in all_freqs:
            m = _measure_at(handle, freq)
            mags_b.append(m["magnitude"])

        # Boolean computation via superposition thresholds
        superposed = [a + b for a, b in zip(mags_a, mags_b)]
        n = len(superposed)
        if n == 0:
            continue

        med = float(np.median(superposed))
        hi_thresh = med * 1.5
        lo_thresh = med * 0.5

        n_and = sum(1 for s in superposed if s > hi_thresh)
        n_or = sum(1 for s in superposed if s > lo_thresh)
        n_xor = sum(1 for s in superposed if lo_thresh < s <= hi_thresh)

        data = {
            "plate_a": na, "plate_b": nb,
            "n_a_only": classified["n_a_only"],
            "n_b_only": classified["n_b_only"],
            "n_shared": classified["n_shared"],
            "n_and": n_and, "n_or": n_or, "n_xor": n_xor,
            "total_freqs": n,
        }

        notes = (
            f"Boolean: Plate {na} × {nb}. "
            f"AND={n_and}, OR={n_or}, XOR={n_xor} out of {n} freqs."
        )

        if dry_run:
            results.append({"ok": True, "dry": True, "pair": f"{na}-{nb}"})
        else:
            r = submit_experiment(token, "exp-cim-suite", data, notes=notes)
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Block 3: Nearest-Neighbor All Pairs
# ═══════════════════════════════════════════════════════════════════════

def block_nn_pairs(handle, mux, enrolled, plate_names, plate_ids,
                   token, dry_run) -> list:
    """For each plate, identify which enrolled template is nearest."""
    log("\n" + "=" * 65)
    log("  BLOCK 3: NEAREST-NEIGHBOR ALL PAIRS")
    log("=" * 65)

    results = []
    correct = 0
    total = 0

    for pid in plate_ids:
        name = plate_names[pid]
        log(f"\n  Query: Plate {name}")

        # Measure at all enrolled frequencies for all plates
        all_freqs = []
        for eid in plate_ids:
            all_freqs.extend(enrolled[eid])
        all_freqs = sorted(set(all_freqs))

        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        raw_mags = {eid: [] for eid in plate_ids}
        for freq in all_freqs:
            m = _measure_at(handle, freq)
            for eid in plate_ids:
                # Check if this freq belongs to this enrollment
                belongs = any(abs(freq - ef) / max(freq, ef) < 0.03
                              for ef in enrolled[eid])
                if belongs:
                    raw_mags[eid].append(m["magnitude"])

        # Pad to equal length
        max_len = max(len(v) for v in raw_mags.values())
        for eid in plate_ids:
            while len(raw_mags[eid]) < max_len:
                raw_mags[eid].append(0.0)

        query_freqs = all_freqs[:max_len]
        scores = _template_score(query_freqs, raw_mags, enrolled, plate_ids)

        winner = max(scores, key=scores.get)
        total += 1
        is_correct = winner == pid
        if is_correct:
            correct += 1

        log(f"    Winner: Plate {plate_names[winner]} "
            f"({'✓' if is_correct else '✗'})")
        for eid in plate_ids:
            log(f"      Plate {plate_names[eid]}: {scores[eid]:.2f}")

        data = {
            "query_plate": name,
            "winner_plate": plate_names[winner],
            "correct": is_correct,
            "scores": scores,
        }
        notes = f"NN: Plate {name} → {plate_names[winner]} ({'correct' if is_correct else 'wrong'})"

        if dry_run:
            results.append({"ok": True, "dry": True, "plate": name})
        else:
            r = submit_experiment(token, "exp-cim-suite", data, notes=notes)
            print_result(r)
            results.append(r)

    log(f"\n  NN accuracy: {correct}/{total}")
    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Block 4: 3-Plate Boolean
# ═══════════════════════════════════════════════════════════════════════

def block_3plate_boolean(handle, mux, enrolled, plate_names, plate_ids,
                         token, dry_run) -> list:
    """AND/OR/XOR across 3 plates simultaneously."""
    log("\n" + "=" * 65)
    log("  BLOCK 4: 3-PLATE BOOLEAN")
    log("=" * 65)

    results = []
    # Pick up to 10 triples
    triples = list(combinations(plate_ids, 3))[:10]

    for pa, pb, pc in triples:
        na, nb, nc = plate_names[pa], plate_names[pb], plate_names[pc]
        log(f"\n  Triple: {na} × {nb} × {nc}")

        # Union of enrolled frequencies
        all_freqs = sorted(set(enrolled[pa] + enrolled[pb] + enrolled[pc]))

        mags = {}
        for pid in [pa, pb, pc]:
            mux.select(int(pid))
            time.sleep(SETTLE_RELAY_S)
            mags[pid] = []
            for freq in all_freqs:
                m = _measure_at(handle, freq)
                mags[pid].append(m["magnitude"])

        # 3-way superposition
        superposed = [mags[pa][i] + mags[pb][i] + mags[pc][i]
                      for i in range(len(all_freqs))]

        med = float(np.median(superposed)) if superposed else 1.0
        hi_thresh = med * 2.0    # all 3 plates active
        mid_thresh = med * 1.0   # 2 of 3
        lo_thresh = med * 0.5    # at least 1

        n_and3 = sum(1 for s in superposed if s > hi_thresh)
        n_or3 = sum(1 for s in superposed if s > lo_thresh)

        data = {
            "plate_a": na, "plate_b": nb, "plate_c": nc,
            "total_freqs": len(all_freqs),
            "n_and3": n_and3, "n_or3": n_or3,
        }
        notes = f"3-plate Boolean: {na}×{nb}×{nc}. AND3={n_and3}, OR3={n_or3}."

        if dry_run:
            results.append({"ok": True, "dry": True, "triple": f"{na}-{nb}-{nc}"})
        else:
            r = submit_experiment(token, "exp-cim-suite", data, notes=notes)
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Block 5: Chained Boolean (A AND B → result XOR C)
# ═══════════════════════════════════════════════════════════════════════

def block_chained(handle, mux, enrolled, plate_names, plate_ids,
                  token, dry_run) -> list:
    """A AND B → intermediate → XOR C."""
    log("\n" + "=" * 65)
    log("  BLOCK 5: CHAINED BOOLEAN")
    log("=" * 65)

    results = []
    # Use first 3 plates
    if len(plate_ids) < 3:
        log("  Need at least 3 plates, skipping")
        return results

    pa, pb, pc = plate_ids[0], plate_ids[1], plate_ids[2]
    na, nb, nc = plate_names[pa], plate_names[pb], plate_names[pc]
    log(f"  Chain: ({na} AND {nb}) XOR {nc}")

    all_freqs = sorted(set(enrolled[pa] + enrolled[pb] + enrolled[pc]))

    mags = {}
    for pid in [pa, pb, pc]:
        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)
        mags[pid] = []
        for freq in all_freqs:
            m = _measure_at(handle, freq)
            mags[pid].append(m["magnitude"])

    # Step 1: A AND B (superpose, high-threshold)
    ab_super = [mags[pa][i] + mags[pb][i] for i in range(len(all_freqs))]
    med_ab = float(np.median(ab_super)) if ab_super else 1.0
    ab_and = [1 if s > med_ab * 1.5 else 0 for s in ab_super]

    # Step 2: (A AND B) XOR C
    c_binary = [1 if mags[pc][i] > float(np.median([m for m in mags[pc] if m > 0] or [1])) * 0.5
                else 0 for i in range(len(all_freqs))]
    xor_result = [a ^ c for a, c in zip(ab_and, c_binary)]

    n_and_hits = sum(ab_and)
    n_xor_hits = sum(xor_result)

    data = {
        "plate_a": na, "plate_b": nb, "plate_c": nc,
        "operation": f"({na} AND {nb}) XOR {nc}",
        "n_and_ab": n_and_hits,
        "n_xor_result": n_xor_hits,
        "total_freqs": len(all_freqs),
    }
    notes = f"Chained: ({na} AND {nb}) XOR {nc}. AND={n_and_hits}, XOR={n_xor_hits}."

    if dry_run:
        results.append({"ok": True, "dry": True})
    else:
        r = submit_experiment(token, "exp-cim-suite", data, notes=notes)
        print_result(r)
        results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Block 6: Noise Robustness (Drive Voltage Sweep)
# ═══════════════════════════════════════════════════════════════════════

def block_noise(handle, mux, enrolled, plate_names, plate_ids,
                token, dry_run) -> list:
    """Sweep drive voltage from 100% down to 10%, measure recall fidelity."""
    log("\n" + "=" * 65)
    log("  BLOCK 6: NOISE ROBUSTNESS (drive voltage sweep)")
    log("=" * 65)

    drive_fractions = [1.0, 0.75, 0.50, 0.25, 0.10]
    results = []

    pid = plate_ids[0]  # Use first plate
    name = plate_names[pid]
    freqs = enrolled[pid]
    mux.select(int(pid))
    time.sleep(SETTLE_RELAY_S)

    log(f"  Plate {name}: sweeping drive voltage")

    baseline_mags = []
    for freq in freqs:
        m = _measure_at(handle, freq)
        baseline_mags.append(m["magnitude"])

    for frac in drive_fractions:
        drive_uv = int(AWG_DRIVE_UVPP * frac)
        mags = []
        for freq in freqs:
            m = _measure_at(handle, freq, drive_uvpp=drive_uv)
            mags.append(m["magnitude"])

        # Correlation with baseline
        if baseline_mags and mags:
            corr = float(np.corrcoef(baseline_mags, mags)[0, 1])
        else:
            corr = 0.0

        log(f"    {frac * 100:5.0f}% drive ({drive_uv} µVpp): "
            f"corr={corr:.4f}, mean_mag={np.mean(mags):.0f}")

        data = {
            "plate_name": name,
            "drive_fraction": frac,
            "drive_uvpp": drive_uv,
            "correlation": round(corr, 4),
            "mean_magnitude": round(float(np.mean(mags)), 1),
        }
        notes = f"Noise: Plate {name} at {frac * 100:.0f}% drive, corr={corr:.4f}."

        if dry_run:
            results.append({"ok": True, "dry": True, "frac": frac})
        else:
            r = submit_experiment(token, "exp-cim-suite", data, notes=notes)
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

ALL_BLOCKS = {
    "temporal": "Temporal stability",
    "boolean-pairs": "Boolean all pairs",
    "nn-pairs": "NN all pairs",
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
        "--port", type=str, default="/dev/cu.usbserial-11310",
        help="Serial port for relay mux"
    )
    args = parser.parse_args()

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

    enrolled, plate_names, plate_ids = _load_enrollment()

    token = None
    if not args.dry_run:
        try:
            token = firebase_anon_auth()
            log("  ✓ Firebase auth OK")
        except Exception as e:
            log(f"  ✗ Auth failed: {e}")
            log("  Continuing in dry-run mode")
            args.dry_run = True
            token = "FAILED"
    else:
        token = "DRY_RUN"
        log("DRY RUN mode")

    all_results = []

    try:
        if "temporal" in blocks:
            all_results.extend(block_temporal(
                handle, mux, enrolled, plate_names, plate_ids, token, args.dry_run))
        if "boolean-pairs" in blocks:
            all_results.extend(block_boolean_pairs(
                handle, mux, enrolled, plate_names, plate_ids, token, args.dry_run))
        if "nn-pairs" in blocks:
            all_results.extend(block_nn_pairs(
                handle, mux, enrolled, plate_names, plate_ids, token, args.dry_run))
        if "3plate-boolean" in blocks:
            all_results.extend(block_3plate_boolean(
                handle, mux, enrolled, plate_names, plate_ids, token, args.dry_run))
        if "chained" in blocks:
            all_results.extend(block_chained(
                handle, mux, enrolled, plate_names, plate_ids, token, args.dry_run))
        if "noise" in blocks:
            all_results.extend(block_noise(
                handle, mux, enrolled, plate_names, plate_ids, token, args.dry_run))
    finally:
        _close_scope(handle)
        mux.close()
        _save_log()

    # Summary
    submitted = [r for r in all_results if r.get("ok") and not r.get("dry")]
    failed = [r for r in all_results if not r.get("ok")]

    log(f"\n{'=' * 65}")
    log(f"  SUMMARY: {len(submitted)} submitted, {len(failed)} failed")
    log(f"{'=' * 65}")

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as fw:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": args.dry_run,
            "blocks": blocks,
            "results": all_results,
        }, fw, indent=2, default=str)
    log(f"  Saved: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
