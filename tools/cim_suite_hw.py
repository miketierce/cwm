#!/usr/bin/env python3
"""
CIM Experiment Suite — Comprehensive Compute-in-Memory Validation

Runs six experiment blocks on the physical 4-rod array:

  1. Temporal stability  — Re-run recall + Boolean to check 24h drift
  2. Boolean all pairs   — 6 rod pairs (including 80% overlap stress)
  3. NN all pairs        — 6 rod pairs nearest-neighbor sweeps
  4. 3-pattern Boolean   — AND/OR/XOR across 3 rods simultaneously
  5. Chained Boolean     — A AND B → result XOR C (multi-step compute)
  6. Noise robustness    — Drive voltage sweep from 100% down to 10%

Signal chain:
  AWG OUT → Drive PZTs (all 4 rods share AWG)
  Relay N → Sense PZT Rod N → PicoScope Ch A

Usage:
  PYTHONPATH=. python tools/cim_suite_hw.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/cim_suite_hw.py --only temporal,boolean-pairs
  PYTHONPATH=. python tools/cim_suite_hw.py --dry-run
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
from itertools import combinations
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
N_PEAKS = 10
FREQ_MATCH_PCT = 3
GUARD_BAND_PCT = 5        # exclude a_only/b_only freqs within 5% of other rod's enrolled peaks

# ── Paths ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab"
USERS_FILE = LAB_DIR / "users.json"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = LAB_DIR / "cim_suite"
RESULTS_FILE = RESULTS_DIR / f"suite_{TIMESTAMP}.json"
LOG_FILE = RESULTS_DIR / f"suite_{TIMESTAMP}.log"

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
                settle_s: float = SETTLE_S,
                drive_uvpp: int = AWG_DRIVE_UVPP) -> dict:
    """Drive AWG at freq_hz, capture, return magnitude."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, drive_uvpp, 0,
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

    return {"magnitude": round(float(np.mean(magnitudes)), 1) if magnitudes else 0.0}


# ── Enrollment loader ────────────────────────────────────────────────────

def _load_enrollment() -> tuple[dict, dict, list]:
    """Return (enrolled, rod_patterns, rod_ids)."""
    with open(USERS_FILE) as f:
        db = json.load(f)
    enrolled = {}
    rod_patterns = {}
    for rid in sorted(db["rods"].keys()):
        r = db["rods"][rid]
        if r.get("enrolled"):
            enrolled[rid] = r["perturbed_hz"]
            rod_patterns[rid] = r.get("pattern", "?")
    rod_ids = sorted(enrolled.keys())
    return enrolled, rod_patterns, rod_ids


# ── Template scoring (for recall + NN) ───────────────────────────────────

def _template_score(query_freqs: list[float],
                    raw_mags: dict[str, list[float]],
                    enrolled: dict[str, list[float]],
                    rod_ids: list[str]) -> dict[str, float]:
    scores = {sr: 0.0 for sr in rod_ids}
    for pi, freq in enumerate(query_freqs):
        mags = {sr: raw_mags[sr][pi] for sr in rod_ids}
        total = sum(mags.values())
        if total == 0:
            continue
        for sr in rod_ids:
            frac = mags[sr] / total
            expected = any(
                abs(freq - ep) / max(freq, ep) < 0.03
                for ep in enrolled[sr]
            )
            if expected:
                scores[sr] += frac * 3.0
            else:
                scores[sr] -= frac * 1.0
    return {sr: round(v, 2) for sr, v in scores.items()}


# ── Freq classification (for Boolean) ────────────────────────────────────

def _classify_frequencies(peaks_a: list[float], peaks_b: list[float],
                           match_pct: float = FREQ_MATCH_PCT,
                           full_enroll_a: list[float] | None = None,
                           full_enroll_b: list[float] | None = None,
                           guard_pct: float = GUARD_BAND_PCT) -> dict:
    both, a_only = [], []
    b_used = [False] * len(peaks_b)

    for fa in peaks_a:
        matched = False
        for bi, fb in enumerate(peaks_b):
            if not b_used[bi] and abs(fa - fb) / max(fa, fb) * 100 < match_pct:
                both.append((fa + fb) / 2)
                b_used[bi] = True
                matched = True
                break
        if not matched:
            a_only.append(fa)

    b_only = [peaks_b[i] for i in range(len(peaks_b)) if not b_used[i]]

    # Guard band: drop a_only freqs too close to any of B's full enrollment
    guarded_a, guarded_b = [], []
    if full_enroll_b is not None:
        for fa in a_only:
            if any(abs(fa - fb) / max(fa, fb) * 100 < guard_pct for fb in full_enroll_b):
                guarded_a.append(fa)
        a_only = [f for f in a_only if f not in guarded_a]
    if full_enroll_a is not None:
        for fb in b_only:
            if any(abs(fb - fa) / max(fb, fa) * 100 < guard_pct for fa in full_enroll_a):
                guarded_b.append(fb)
        b_only = [f for f in b_only if f not in guarded_b]

    return {
        "both": sorted(both), "a_only": sorted(a_only),
        "b_only": sorted(b_only), "all": sorted(both + a_only + b_only),
        "guarded": sorted(guarded_a + guarded_b),
    }


def _classify_three(peaks_a, peaks_b, peaks_c, match_pct=FREQ_MATCH_PCT):
    """Classify frequencies from three rods into 7 categories:
    abc, ab, ac, bc, a_only, b_only, c_only."""

    def near(f1, f2):
        return abs(f1 - f2) / max(f1, f2) * 100 < match_pct

    # Find A∩B matches
    ab_matched_a = set()
    ab_matched_b = set()
    for ai, fa in enumerate(peaks_a):
        for bi, fb in enumerate(peaks_b):
            if bi not in ab_matched_b and near(fa, fb):
                ab_matched_a.add(ai)
                ab_matched_b.add(bi)
                break

    # Find A∩C matches
    ac_matched_a = set()
    ac_matched_c = set()
    for ai, fa in enumerate(peaks_a):
        for ci, fc in enumerate(peaks_c):
            if ci not in ac_matched_c and near(fa, fc):
                ac_matched_a.add(ai)
                ac_matched_c.add(ci)
                break

    # Find B∩C matches
    bc_matched_b = set()
    bc_matched_c = set()
    for bi, fb in enumerate(peaks_b):
        for ci, fc in enumerate(peaks_c):
            if ci not in bc_matched_c and near(fb, fc):
                bc_matched_b.add(bi)
                bc_matched_c.add(ci)
                break

    # Classify each peak
    result = {"abc": [], "ab": [], "ac": [], "bc": [],
              "a_only": [], "b_only": [], "c_only": []}

    for ai, fa in enumerate(peaks_a):
        in_b = ai in ab_matched_a
        in_c = ai in ac_matched_a
        if in_b and in_c:
            result["abc"].append(fa)
        elif in_b:
            result["ab"].append(fa)
        elif in_c:
            result["ac"].append(fa)
        else:
            result["a_only"].append(fa)

    for bi, fb in enumerate(peaks_b):
        if bi in ab_matched_b:
            continue  # already counted in A-side
        in_c = bi in bc_matched_b
        if in_c:
            result["bc"].append(fb)
        else:
            result["b_only"].append(fb)

    for ci, fc in enumerate(peaks_c):
        if ci in ac_matched_c or ci in bc_matched_c:
            continue  # already counted
        result["c_only"].append(fc)

    all_freqs = sorted(
        sum(result.values(), [])
    )
    result["all"] = all_freqs
    return result


# ── Pre-scan for strong peaks ────────────────────────────────────────────

def _prescan_rod(handle, mux: RelayMux, rod_id: str,
                 peaks: list[float], rod_pattern: str) -> tuple[list[float], float]:
    """Measure rod's self-response at all peaks, return strong peaks + threshold."""
    mux.select(int(rod_id))
    time.sleep(SETTLE_RELAY_S)

    scan_results = []
    for freq in peaks:
        m = _measure_at(handle, freq, n_avg=N_AVG // 2)
        scan_results.append((freq, m["magnitude"]))

    mags_sorted = sorted([m for _, m in scan_results])
    mid = len(mags_sorted) // 2
    med_strong = float(np.median(mags_sorted[mid:]))
    med_weak = float(np.median(mags_sorted[:mid]))
    thresh = math.sqrt(med_strong * med_weak) if med_weak > 0 else med_strong * 0.1

    strong = [(f, m) for f, m in scan_results if m > thresh]
    strong_freqs = [f for f, _ in strong]
    log(f"  Rod {rod_id} ({rod_pattern}): {len(strong)}/{len(scan_results)} strong, "
        f"thresh={thresh:.0f}, peaks={[round(f) for f in strong_freqs]}")
    return strong_freqs, thresh


# ── Measure all rods at a set of frequencies ─────────────────────────────

def _measure_all_rods(handle, mux: RelayMux, freqs: list[float],
                      rod_ids: list[str], drive_uvpp: int = AWG_DRIVE_UVPP,
                      verbose: bool = False) -> list[dict]:
    """For each freq, measure on all sense rods. Returns list of {rod: mag}."""
    raw_mags = []
    for fi, freq in enumerate(freqs):
        rod_mag = {}
        for sr in rod_ids:
            mux.select(int(sr))
            time.sleep(SETTLE_RELAY_S)
            m = _measure_at(handle, freq, drive_uvpp=drive_uvpp)
            rod_mag[sr] = m["magnitude"]
        raw_mags.append(rod_mag)
        if verbose and (fi == 0 or (fi + 1) % 5 == 0 or fi == len(freqs) - 1):
            mag_str = "  ".join(f"R{sr}={rod_mag[sr]:8.0f}" for sr in rod_ids)
            log(f"    f{fi+1:2d} {freq:7.1f} Hz  {mag_str}")
    mux.off()
    return raw_mags


# ── Boolean extraction (2 patterns) ─────────────────────────────────────

def _extract_boolean_2(all_freqs, raw_mags, strong_peaks_a, strong_peaks_b,
                       pattern_a, pattern_b, classes):
    """Extract AND/OR/XOR from 2-pattern measurement data."""
    # Detection thresholds from weakest strong peak in main-phase
    rod_thresholds = {}
    for sr, sp in [(pattern_a, strong_peaks_a), (pattern_b, strong_peaks_b)]:
        min_self = float('inf')
        for fi, freq in enumerate(all_freqs):
            is_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in sp)
            if is_enrolled:
                min_self = min(min_self, raw_mags[fi][sr])
        rod_thresholds[sr] = (min_self if min_self != float('inf') else 100000) * 0.5

    # Build freq→category map
    freq_cat = {}
    for f in classes["both"]:
        freq_cat[round(f, 1)] = "both"
    for f in classes["a_only"]:
        freq_cat[round(f, 1)] = "a_only"
    for f in classes["b_only"]:
        freq_cat[round(f, 1)] = "b_only"

    results = []
    and_c = or_c = xor_c = total = 0

    for fi, freq in enumerate(all_freqs):
        mag_a = raw_mags[fi][pattern_a]
        mag_b = raw_mags[fi][pattern_b]

        a_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in strong_peaks_a)
        b_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in strong_peaks_b)

        det_a = 1 if (a_enrolled and mag_a > rod_thresholds[pattern_a]) else 0
        det_b = 1 if (b_enrolled and mag_b > rod_thresholds[pattern_b]) else 0

        and_got = 1 if (det_a and det_b) else 0
        or_got = 1 if (det_a or det_b) else 0
        xor_got = 1 if (det_a != det_b) else 0

        cat = freq_cat.get(round(freq, 1), "?")
        in_a = cat in ("both", "a_only")
        in_b = cat in ("both", "b_only")
        and_exp = 1 if (in_a and in_b) else 0
        or_exp = 1 if (in_a or in_b) else 0
        xor_exp = 1 if (in_a != in_b) else 0

        and_c += (and_exp == and_got)
        or_c += (or_exp == or_got)
        xor_c += (xor_exp == xor_got)
        total += 1

        results.append({
            "freq": round(freq, 1), "category": cat,
            "mag_a": round(mag_a, 1), "mag_b": round(mag_b, 1),
            "det_a": det_a, "det_b": det_b,
            "and_exp": and_exp, "and_got": and_got,
            "or_exp": or_exp, "or_got": or_got,
            "xor_exp": xor_exp, "xor_got": xor_got,
        })

    return {
        "and_fidelity": round(and_c / total, 3) if total else 0,
        "or_fidelity": round(or_c / total, 3) if total else 0,
        "xor_fidelity": round(xor_c / total, 3) if total else 0,
        "mean_fidelity": round((and_c + or_c + xor_c) / (3 * total), 3) if total else 0,
        "total_bits": total, "and_correct": and_c, "or_correct": or_c, "xor_correct": xor_c,
        "rod_thresholds": {k: round(v, 1) for k, v in rod_thresholds.items()},
        "per_freq": results,
    }


# ── Kendall tau ───────────────────────────────────────────────────────────

def _kendall_tau(rank_a, rank_b):
    n = len(rank_a)
    con = dis = 0
    for i in range(n):
        for j in range(i + 1, n):
            product = (rank_a[i] - rank_a[j]) * (rank_b[i] - rank_b[j])
            if product > 0:
                con += 1
            elif product < 0:
                dis += 1
    total = con + dis
    return (con - dis) / total if total > 0 else 1.0


# ══════════════════════════════════════════════════════════════════════════
#  EXPERIMENT 1: Temporal Stability Retest
# ══════════════════════════════════════════════════════════════════════════

def run_temporal_stability(handle, mux: RelayMux, enrolled, rod_patterns, rod_ids):
    """Re-run recall (4-rod template) + Boolean (Rod 1 vs 2) to check drift."""
    log("\n" + "=" * 70)
    log("  EXPERIMENT 1: Temporal Stability (24h retest)")
    log("=" * 70)

    results = {"recall": [], "boolean": None}

    # ── Recall: measure each rod's query pattern against all rods ─────
    log("\n  [Recall] Measuring 4×4 matrix...")
    for qr in rod_ids:
        query_peaks = enrolled[qr][:N_PEAKS]
        raw = {sr: [] for sr in rod_ids}

        for freq in query_peaks:
            for sr in rod_ids:
                mux.select(int(sr))
                time.sleep(SETTLE_RELAY_S)
                m = _measure_at(handle, freq)
                raw[sr].append(m["magnitude"])
        mux.off()

        scores = _template_score(query_peaks, raw, enrolled, rod_ids)
        winner = max(scores, key=scores.get)
        correct = winner == qr
        margin = scores[qr] - max(v for k, v in scores.items() if k != qr)

        log(f"    Q={qr}: winner=Rod {winner} {'✓' if correct else '✗'}  "
            f"score={scores[qr]:+.1f}  margin={margin:+.1f}")

        results["recall"].append({
            "query_rod": qr, "winner": winner, "correct": correct,
            "scores": scores, "margin": round(margin, 2),
        })

    recall_acc = sum(1 for r in results["recall"] if r["correct"]) / len(rod_ids)
    mean_margin = np.mean([r["margin"] for r in results["recall"]])
    log(f"\n  [Recall] Accuracy: {sum(1 for r in results['recall'] if r['correct'])}/{len(rod_ids)} "
        f"({recall_acc*100:.0f}%), mean margin={mean_margin:+.2f}")

    # ── Boolean: Rod 1 vs 2 with pre-scan ─────────────────────────────
    log("\n  [Boolean] Rod 1 vs 2 with pre-scan...")
    pa, pb = "1", "2"
    sp_a, _ = _prescan_rod(handle, mux, pa, enrolled[pa][:N_PEAKS], rod_patterns[pa])
    sp_b, _ = _prescan_rod(handle, mux, pb, enrolled[pb][:N_PEAKS], rod_patterns[pb])
    mux.off()

    classes = _classify_frequencies(sp_a, sp_b,
                                    full_enroll_a=enrolled[pa],
                                    full_enroll_b=enrolled[pb])
    all_freqs = classes["all"]
    raw_mags = _measure_all_rods(handle, mux, all_freqs, rod_ids, verbose=True)

    bool_result = _extract_boolean_2(
        all_freqs, raw_mags, sp_a, sp_b, pa, pb, classes
    )
    results["boolean"] = bool_result
    log(f"\n  [Boolean] AND={bool_result['and_fidelity']*100:.0f}%  "
        f"OR={bool_result['or_fidelity']*100:.0f}%  "
        f"XOR={bool_result['xor_fidelity']*100:.0f}%  "
        f"Mean={bool_result['mean_fidelity']*100:.0f}%")
    results["recall_accuracy"] = round(recall_acc, 3)
    results["recall_mean_margin"] = round(float(mean_margin), 2)
    return results


# ══════════════════════════════════════════════════════════════════════════
#  EXPERIMENT 2: Boolean on All 6 Rod Pairs
# ══════════════════════════════════════════════════════════════════════════

def run_boolean_all_pairs(handle, mux: RelayMux, enrolled, rod_patterns, rod_ids):
    """Test Boolean compute on all C(4,2)=6 rod pairs."""
    log("\n" + "=" * 70)
    log("  EXPERIMENT 2: Boolean Compute — All 6 Rod Pairs")
    log("=" * 70)

    pairs = list(combinations(rod_ids, 2))
    results = []

    for pa, pb in pairs:
        log(f"\n  ── Pair Rod {pa} vs Rod {pb} ──")

        # Pre-scan both rods
        sp_a, _ = _prescan_rod(handle, mux, pa, enrolled[pa][:N_PEAKS], rod_patterns[pa])
        sp_b, _ = _prescan_rod(handle, mux, pb, enrolled[pb][:N_PEAKS], rod_patterns[pb])
        mux.off()

        if not sp_a or not sp_b:
            log(f"    SKIP: no strong peaks (A={len(sp_a)}, B={len(sp_b)})")
            results.append({"pair": [pa, pb], "skipped": True})
            continue

        classes = _classify_frequencies(sp_a, sp_b,
                                        full_enroll_a=enrolled[pa],
                                        full_enroll_b=enrolled[pb])
        all_freqs = classes["all"]
        guarded = classes.get("guarded", [])
        guard_msg = f", guarded={len(guarded)}" if guarded else ""
        log(f"    Union: {len(all_freqs)} freqs (both={len(classes['both'])}, "
            f"a-only={len(classes['a_only'])}, b-only={len(classes['b_only'])}{guard_msg})")
        if guarded:
            log(f"    Guard-band excluded: {[round(f,1) for f in guarded]}")

        raw_mags = _measure_all_rods(handle, mux, all_freqs, rod_ids)
        bool_result = _extract_boolean_2(
            all_freqs, raw_mags, sp_a, sp_b, pa, pb, classes
        )

        overlap_count = len(classes["both"])
        overlap_pct = round(100 * overlap_count / max(len(sp_a), len(sp_b)), 1) if sp_a and sp_b else 0

        log(f"    AND={bool_result['and_fidelity']*100:.0f}%  "
            f"OR={bool_result['or_fidelity']*100:.0f}%  "
            f"XOR={bool_result['xor_fidelity']*100:.0f}%  "
            f"Mean={bool_result['mean_fidelity']*100:.0f}%  "
            f"Overlap={overlap_pct}%")

        results.append({
            "pair": [pa, pb],
            "patterns": [rod_patterns[pa], rod_patterns[pb]],
            "strong_a": len(sp_a), "strong_b": len(sp_b),
            "overlap_pct": overlap_pct,
            "analysis": {k: v for k, v in bool_result.items() if k != "per_freq"},
            "per_freq": bool_result["per_freq"],
        })

    return results


# ══════════════════════════════════════════════════════════════════════════
#  EXPERIMENT 3: Nearest-Neighbor on All 6 Pairs
# ══════════════════════════════════════════════════════════════════════════

def _build_interpolated_query(peaks_a, peaks_b, alpha, n_peaks):
    candidates = []
    for f in peaks_a:
        candidates.append((f, 1.0 - alpha, "A"))
    for f in peaks_b:
        candidates.append((f, alpha, "B"))
    candidates.sort(key=lambda x: -x[1])
    selected = candidates[:n_peaks]
    selected.sort(key=lambda x: x[0])
    return [s[0] for s in selected], [(s[0], s[1], s[2]) for s in selected]


def run_nn_all_pairs(handle, mux: RelayMux, enrolled, rod_patterns, rod_ids):
    """Nearest-neighbor α-sweep on all 6 rod pairs."""
    log("\n" + "=" * 70)
    log("  EXPERIMENT 3: Nearest-Neighbor — All 6 Rod Pairs")
    log("=" * 70)

    pairs = list(combinations(rod_ids, 2))
    n_steps = 11
    results = []

    for ra, rb in pairs:
        log(f"\n  ── Pair Rod {ra} (→{rod_patterns[ra]}) vs Rod {rb} (→{rod_patterns[rb]}) ──")
        peaks_a = enrolled[ra][:N_PEAKS]
        peaks_b = enrolled[rb][:N_PEAKS]
        alphas = np.linspace(0.0, 1.0, n_steps)

        pair_results = []
        expected_rankings = []  # for tau: expect A first at low α, B first at high α

        for ai, alpha in enumerate(alphas):
            query_freqs, _ = _build_interpolated_query(peaks_a, peaks_b, alpha, N_PEAKS)
            raw = {sr: [] for sr in rod_ids}

            for freq in query_freqs:
                for sr in rod_ids:
                    mux.select(int(sr))
                    time.sleep(SETTLE_RELAY_S)
                    m = _measure_at(handle, freq)
                    raw[sr].append(m["magnitude"])
            mux.off()

            scores = _template_score(query_freqs, raw, enrolled, rod_ids)
            winner = max(scores, key=scores.get)

            # Expected: A wins at low α, B wins at high α
            if alpha <= 0.5:
                expected = ra
            else:
                expected = rb
            correct = winner == expected

            pair_results.append({
                "alpha": round(alpha, 2), "winner": winner,
                "expected": expected, "correct": correct,
                "scores": scores,
            })
            expected_rankings.append(expected)

            log(f"    α={alpha:.1f}  winner=Rod {winner} "
                f"{'✓' if correct else '✗'}  "
                f"A={scores[ra]:+.1f}  B={scores[rb]:+.1f}",
                also_print=ai % 3 == 0 or ai == n_steps - 1)

        n_correct = sum(1 for r in pair_results if r["correct"])
        # Compute Kendall tau between expected and actual winner rankings
        expected_rank = [0 if r["expected"] == ra else 1 for r in pair_results]
        actual_rank = [0 if r["winner"] == ra else 1 for r in pair_results]
        tau = _kendall_tau(expected_rank, actual_rank)

        log(f"    Score: {n_correct}/{n_steps} ({n_correct/n_steps*100:.0f}%), τ={tau:.3f}")

        results.append({
            "pair": [ra, rb],
            "patterns": [rod_patterns[ra], rod_patterns[rb]],
            "n_correct": n_correct, "n_steps": n_steps,
            "accuracy": round(n_correct / n_steps, 3),
            "kendall_tau": round(tau, 3),
            "steps": pair_results,
        })

    return results


# ══════════════════════════════════════════════════════════════════════════
#  EXPERIMENT 4: 3-Pattern Boolean
# ══════════════════════════════════════════════════════════════════════════

def run_boolean_three(handle, mux: RelayMux, enrolled, rod_patterns, rod_ids):
    """Boolean AND/OR/XOR across 3 rods simultaneously.

    Truth table for 3 inputs (a, b, c):
      AND3 = a & b & c
      OR3  = a | b | c
      MAJ  = majority(a, b, c) — at least 2 of 3
      XOR3 = a ^ b ^ c  (odd-parity)
    """
    log("\n" + "=" * 70)
    log("  EXPERIMENT 4: 3-Pattern Boolean (Rods 1, 2, 3)")
    log("=" * 70)

    # Use rods 1, 2, 3 (rod 4 shares 80% with rod 1 — keep as independent sense)
    pa, pb, pc = "1", "2", "3"

    # Pre-scan all three
    log("\n  Pre-scan phase:")
    sp_a, _ = _prescan_rod(handle, mux, pa, enrolled[pa][:N_PEAKS], rod_patterns[pa])
    sp_b, _ = _prescan_rod(handle, mux, pb, enrolled[pb][:N_PEAKS], rod_patterns[pb])
    sp_c, _ = _prescan_rod(handle, mux, pc, enrolled[pc][:N_PEAKS], rod_patterns[pc])
    mux.off()

    classes = _classify_three(sp_a, sp_b, sp_c)
    all_freqs = classes["all"]

    log(f"\n  Patterns: A=Rod {pa}, B=Rod {pb}, C=Rod {pc}")
    log(f"  Strong: A={len(sp_a)}, B={len(sp_b)}, C={len(sp_c)}")
    log(f"  Classification: abc={len(classes['abc'])}, ab={len(classes['ab'])}, "
        f"ac={len(classes['ac'])}, bc={len(classes['bc'])}, "
        f"a={len(classes['a_only'])}, b={len(classes['b_only'])}, c={len(classes['c_only'])}")
    log(f"  Union: {len(all_freqs)} freqs")

    # Measure all rods at all freqs
    log("\n  Measuring...")
    raw_mags = _measure_all_rods(handle, mux, all_freqs, rod_ids, verbose=True)

    # Per-rod thresholds from self-response at strong peaks
    rod_thresholds = {}
    for sr, sp in [(pa, sp_a), (pb, sp_b), (pc, sp_c)]:
        min_self = float('inf')
        for fi, freq in enumerate(all_freqs):
            is_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in sp)
            if is_enrolled:
                min_self = min(min_self, raw_mags[fi][sr])
        rod_thresholds[sr] = (min_self if min_self != float('inf') else 100000) * 0.5

    # Build ground truth category map
    freq_cat = {}
    for f in classes["abc"]:
        freq_cat[round(f, 1)] = "abc"
    for f in classes["ab"]:
        freq_cat[round(f, 1)] = "ab"
    for f in classes["ac"]:
        freq_cat[round(f, 1)] = "ac"
    for f in classes["bc"]:
        freq_cat[round(f, 1)] = "bc"
    for f in classes["a_only"]:
        freq_cat[round(f, 1)] = "a_only"
    for f in classes["b_only"]:
        freq_cat[round(f, 1)] = "b_only"
    for f in classes["c_only"]:
        freq_cat[round(f, 1)] = "c_only"

    # Extract Boolean operations
    and3_c = or3_c = maj_c = xor3_c = 0
    total = 0
    per_freq = []

    log(f"\n  {'Freq':>8s}  {'Cat':>6s}  {'dA':>3s}  {'dB':>3s}  {'dC':>3s}  "
        f"{'AND3':>4s}  {'OR3':>3s}  {'MAJ':>3s}  {'XOR3':>4s}")

    for fi, freq in enumerate(all_freqs):
        cat = freq_cat.get(round(freq, 1), "?")

        # Detection
        a_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in sp_a)
        b_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in sp_b)
        c_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in sp_c)

        det_a = 1 if (a_enrolled and raw_mags[fi][pa] > rod_thresholds[pa]) else 0
        det_b = 1 if (b_enrolled and raw_mags[fi][pb] > rod_thresholds[pb]) else 0
        det_c = 1 if (c_enrolled and raw_mags[fi][pc] > rod_thresholds[pc]) else 0

        # Computed
        and3 = 1 if (det_a and det_b and det_c) else 0
        or3 = 1 if (det_a or det_b or det_c) else 0
        maj = 1 if (det_a + det_b + det_c >= 2) else 0
        xor3 = (det_a ^ det_b ^ det_c)

        # Ground truth
        gt_a = 1 if cat in ("abc", "ab", "ac", "a_only") else 0
        gt_b = 1 if cat in ("abc", "ab", "bc", "b_only") else 0
        gt_c = 1 if cat in ("abc", "ac", "bc", "c_only") else 0

        and3_exp = 1 if (gt_a and gt_b and gt_c) else 0
        or3_exp = 1 if (gt_a or gt_b or gt_c) else 0
        maj_exp = 1 if (gt_a + gt_b + gt_c >= 2) else 0
        xor3_exp = (gt_a ^ gt_b ^ gt_c)

        and3_c += (and3 == and3_exp)
        or3_c += (or3 == or3_exp)
        maj_c += (maj == maj_exp)
        xor3_c += (xor3 == xor3_exp)
        total += 1

        ok = "✓" if (and3 == and3_exp and or3 == or3_exp and
                      maj == maj_exp and xor3 == xor3_exp) else "✗"
        log(f"  {freq:8.1f}  {cat:>6s}  {det_a:>3d}  {det_b:>3d}  {det_c:>3d}  "
            f"{'✓' if and3 == and3_exp else '✗':>4s}  "
            f"{'✓' if or3 == or3_exp else '✗':>3s}  "
            f"{'✓' if maj == maj_exp else '✗':>3s}  "
            f"{'✓' if xor3 == xor3_exp else '✗':>4s}  {ok}",
            also_print=fi == 0 or (fi + 1) % 5 == 0 or fi == len(all_freqs) - 1)

        per_freq.append({
            "freq": round(freq, 1), "category": cat,
            "det_a": det_a, "det_b": det_b, "det_c": det_c,
            "mag_a": round(raw_mags[fi][pa], 1),
            "mag_b": round(raw_mags[fi][pb], 1),
            "mag_c": round(raw_mags[fi][pc], 1),
        })

    analysis = {
        "and3_fidelity": round(and3_c / total, 3) if total else 0,
        "or3_fidelity": round(or3_c / total, 3) if total else 0,
        "majority_fidelity": round(maj_c / total, 3) if total else 0,
        "xor3_fidelity": round(xor3_c / total, 3) if total else 0,
        "mean_fidelity": round((and3_c + or3_c + maj_c + xor3_c) / (4 * total), 3) if total else 0,
        "total_bits": total,
    }

    log(f"\n  AND3={analysis['and3_fidelity']*100:.0f}%  "
        f"OR3={analysis['or3_fidelity']*100:.0f}%  "
        f"MAJ={analysis['majority_fidelity']*100:.0f}%  "
        f"XOR3={analysis['xor3_fidelity']*100:.0f}%  "
        f"Mean={analysis['mean_fidelity']*100:.0f}%")

    return {
        "rods": [pa, pb, pc],
        "patterns": [rod_patterns[pa], rod_patterns[pb], rod_patterns[pc]],
        "strong_peaks": {pa: len(sp_a), pb: len(sp_b), pc: len(sp_c)},
        "classification": {k: len(v) for k, v in classes.items()},
        "analysis": analysis,
        "per_freq": per_freq,
    }


# ══════════════════════════════════════════════════════════════════════════
#  EXPERIMENT 5: Chained Boolean  (A AND B) → result XOR C
# ══════════════════════════════════════════════════════════════════════════

def run_chained_boolean(handle, mux: RelayMux, enrolled, rod_patterns, rod_ids):
    """Two-step Boolean: compute A AND B, then XOR the result with C.

    Step 1: Measure A∩B (prescan + detection → get AND result vector)
    Step 2: Take AND result, treat as a new "pattern", XOR with C

    This tests composability — can CIM results feed into further CIM ops?
    """
    log("\n" + "=" * 70)
    log("  EXPERIMENT 5: Chained Boolean — (A AND B) XOR C")
    log("=" * 70)

    pa, pb, pc = "1", "2", "3"

    # Pre-scan all three
    log("\n  Pre-scan phase:")
    sp_a, _ = _prescan_rod(handle, mux, pa, enrolled[pa][:N_PEAKS], rod_patterns[pa])
    sp_b, _ = _prescan_rod(handle, mux, pb, enrolled[pb][:N_PEAKS], rod_patterns[pb])
    sp_c, _ = _prescan_rod(handle, mux, pc, enrolled[pc][:N_PEAKS], rod_patterns[pc])
    mux.off()

    # Step 1: A AND B  (frequencies present in both A and B)
    classes_ab = _classify_frequencies(sp_a, sp_b,
                                       full_enroll_a=enrolled[pa],
                                       full_enroll_b=enrolled[pb])
    and_result_freqs = classes_ab["both"]  # freqs where both A and B have strong peaks

    log(f"\n  Step 1: A AND B")
    log(f"    A strong: {[round(f) for f in sp_a]}")
    log(f"    B strong: {[round(f) for f in sp_b]}")
    log(f"    A ∩ B (AND result): {len(and_result_freqs)} freqs: {[round(f) for f in and_result_freqs]}")

    # Step 2: (A AND B) XOR C
    # The AND result is a set of freqs. XOR with C = freqs in exactly one of {AND-result, C}
    classes_chain = _classify_frequencies(and_result_freqs, sp_c)

    log(f"\n  Step 2: (A AND B) XOR C")
    log(f"    AND-result: {[round(f) for f in and_result_freqs]}")
    log(f"    C strong: {[round(f) for f in sp_c]}")
    log(f"    Both: {len(classes_chain['both'])}, AND-only: {len(classes_chain['a_only'])}, "
        f"C-only: {len(classes_chain['b_only'])}")

    # XOR ground truth: freqs in exactly one of (AND-result, C)
    xor_expected = sorted(classes_chain["a_only"] + classes_chain["b_only"])
    all_freqs = classes_chain["all"]

    log(f"    XOR expected: {len(xor_expected)} freqs")
    log(f"    Total union: {len(all_freqs)} freqs")

    # Now physically verify: measure all union freqs and check detection
    log("\n  Physical verification:")
    raw_mags = _measure_all_rods(handle, mux, all_freqs, rod_ids, verbose=True)

    # For the chained result, we need to detect:
    # - "AND-result" freqs: both A and B should resonate
    # - "C" freqs: C should resonate
    # Then XOR = exactly one of {AND-detected, C-detected}

    # Thresholds for A, B, C
    rod_thresholds = {}
    for sr, sp in [(pa, sp_a), (pb, sp_b), (pc, sp_c)]:
        min_self = float('inf')
        for fi, freq in enumerate(all_freqs):
            is_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in sp)
            if is_enrolled:
                min_self = min(min_self, raw_mags[fi][sr])
        rod_thresholds[sr] = (min_self if min_self != float('inf') else 100000) * 0.5

    correct = 0
    total = 0
    per_freq = []

    for fi, freq in enumerate(all_freqs):
        # Detect A and B presence
        a_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in sp_a)
        b_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in sp_b)
        c_enrolled = any(abs(freq - ep) / max(freq, ep) < 0.03 for ep in sp_c)

        det_a = 1 if (a_enrolled and raw_mags[fi][pa] > rod_thresholds[pa]) else 0
        det_b = 1 if (b_enrolled and raw_mags[fi][pb] > rod_thresholds[pb]) else 0
        det_c = 1 if (c_enrolled and raw_mags[fi][pc] > rod_thresholds[pc]) else 0

        # Chained: (A AND B) XOR C
        and_ab = 1 if (det_a and det_b) else 0
        chain_xor = 1 if (and_ab != det_c) else 0

        # Ground truth
        cat = "?"
        fr = round(freq, 1)
        for f in classes_chain["both"]:
            if abs(fr - round(f, 1)) < 1:
                cat = "both"
        for f in classes_chain["a_only"]:
            if abs(fr - round(f, 1)) < 1:
                cat = "and-only"
        for f in classes_chain["b_only"]:
            if abs(fr - round(f, 1)) < 1:
                cat = "c-only"

        # XOR expected: 1 for and-only and c-only, 0 for both
        xor_exp = 1 if cat in ("and-only", "c-only") else 0
        ok = chain_xor == xor_exp
        correct += ok
        total += 1

        log(f"    f={freq:7.1f}  cat={cat:>8s}  dA={det_a} dB={det_b} dC={det_c}  "
            f"AND={and_ab} XOR_C={chain_xor}  exp={xor_exp}  {'✓' if ok else '✗'}")

        per_freq.append({
            "freq": round(freq, 1), "category": cat,
            "det_a": det_a, "det_b": det_b, "det_c": det_c,
            "and_ab": and_ab, "chain_xor": chain_xor, "xor_expected": xor_exp,
            "correct": ok,
        })

    fidelity = round(correct / total, 3) if total else 0
    log(f"\n  Chained (A AND B) XOR C: {correct}/{total} ({fidelity*100:.0f}%)")

    return {
        "rods": [pa, pb, pc],
        "and_result_freqs": [round(f, 1) for f in and_result_freqs],
        "xor_expected_freqs": [round(f, 1) for f in xor_expected],
        "fidelity": fidelity,
        "correct": correct, "total": total,
        "per_freq": per_freq,
    }


# ══════════════════════════════════════════════════════════════════════════
#  EXPERIMENT 6: Noise Robustness Sweep
# ══════════════════════════════════════════════════════════════════════════

def run_noise_sweep(handle, mux: RelayMux, enrolled, rod_patterns, rod_ids):
    """Sweep AWG drive voltage from 100% → 10% and measure recall + Boolean degradation.

    PS2204A AWG range: 0 to 2,000,000 µVpp.
    Steps: 100%, 80%, 60%, 40%, 20%, 10% of 2Vpp.
    """
    log("\n" + "=" * 70)
    log("  EXPERIMENT 6: Noise Robustness — Drive Voltage Sweep")
    log("=" * 70)

    voltage_fracs = [1.0, 0.8, 0.6, 0.4, 0.2, 0.1]
    results = []

    for vfrac in voltage_fracs:
        drive_uvpp = int(AWG_DRIVE_UVPP * vfrac)
        log(f"\n  ── Drive = {vfrac*100:.0f}% ({drive_uvpp/1e6:.1f} Vpp) ──")

        # Quick recall: just Rod 1 query
        qr = "1"
        query_peaks = enrolled[qr][:N_PEAKS]
        raw = {sr: [] for sr in rod_ids}
        for freq in query_peaks:
            for sr in rod_ids:
                mux.select(int(sr))
                time.sleep(SETTLE_RELAY_S)
                m = _measure_at(handle, freq, drive_uvpp=drive_uvpp)
                raw[sr].append(m["magnitude"])
        mux.off()

        scores = _template_score(query_peaks, raw, enrolled, rod_ids)
        winner = max(scores, key=scores.get)
        recall_ok = winner == qr
        margin = scores[qr] - max(v for k, v in scores.items() if k != qr)

        # Quick Boolean: Rod 1 vs 2 prescan at this voltage
        pa, pb = "1", "2"

        # Pre-scan at reduced voltage
        sp_a_freqs = []
        mux.select(int(pa))
        time.sleep(SETTLE_RELAY_S)
        scan_a = []
        for freq in enrolled[pa][:N_PEAKS]:
            m = _measure_at(handle, freq, n_avg=N_AVG // 2, drive_uvpp=drive_uvpp)
            scan_a.append((freq, m["magnitude"]))
        mags_s = sorted([m for _, m in scan_a])
        mid = len(mags_s) // 2
        th = math.sqrt(float(np.median(mags_s[mid:])) * float(np.median(mags_s[:mid]))) if np.median(mags_s[:mid]) > 0 else float(np.median(mags_s[mid:])) * 0.1
        sp_a_freqs = [f for f, m in scan_a if m > th]

        sp_b_freqs = []
        mux.select(int(pb))
        time.sleep(SETTLE_RELAY_S)
        scan_b = []
        for freq in enrolled[pb][:N_PEAKS]:
            m = _measure_at(handle, freq, n_avg=N_AVG // 2, drive_uvpp=drive_uvpp)
            scan_b.append((freq, m["magnitude"]))
        mags_s = sorted([m for _, m in scan_b])
        mid = len(mags_s) // 2
        th = math.sqrt(float(np.median(mags_s[mid:])) * float(np.median(mags_s[:mid]))) if np.median(mags_s[:mid]) > 0 else float(np.median(mags_s[mid:])) * 0.1
        sp_b_freqs = [f for f, m in scan_b if m > th]
        mux.off()

        if sp_a_freqs and sp_b_freqs:
            classes = _classify_frequencies(sp_a_freqs, sp_b_freqs,
                                            full_enroll_a=enrolled[pa],
                                            full_enroll_b=enrolled[pb])
            all_freqs = classes["all"]
            raw_mags = _measure_all_rods(handle, mux, all_freqs, rod_ids, drive_uvpp=drive_uvpp)
            bool_result = _extract_boolean_2(
                all_freqs, raw_mags, sp_a_freqs, sp_b_freqs, pa, pb, classes
            )
            bool_mean = bool_result["mean_fidelity"]
        else:
            bool_mean = 0.0
            bool_result = {"and_fidelity": 0, "or_fidelity": 0, "xor_fidelity": 0, "mean_fidelity": 0}

        log(f"    Recall: Rod {winner} {'✓' if recall_ok else '✗'}  margin={margin:+.1f}  "
            f"Boolean: AND={bool_result['and_fidelity']*100:.0f}% "
            f"OR={bool_result['or_fidelity']*100:.0f}% "
            f"XOR={bool_result['xor_fidelity']*100:.0f}% "
            f"Mean={bool_mean*100:.0f}%")

        results.append({
            "voltage_frac": vfrac,
            "drive_uvpp": drive_uvpp,
            "recall_winner": winner,
            "recall_correct": recall_ok,
            "recall_margin": round(margin, 2),
            "recall_scores": scores,
            "boolean_and": bool_result["and_fidelity"],
            "boolean_or": bool_result["or_fidelity"],
            "boolean_xor": bool_result["xor_fidelity"],
            "boolean_mean": bool_mean,
            "strong_a": len(sp_a_freqs),
            "strong_b": len(sp_b_freqs),
        })

    return results


# ══════════════════════════════════════════════════════════════════════════
#  Firestore
# ══════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════

ALL_EXPERIMENTS = [
    "temporal", "boolean-pairs", "nn-pairs",
    "boolean-three", "chained", "noise-sweep"
]


def main():
    parser = argparse.ArgumentParser(description="CIM experiment suite")
    parser.add_argument("--port", type=str, default=None)
    parser.add_argument("--only", type=str, default=None,
                        help=f"Comma-separated subset of: {','.join(ALL_EXPERIMENTS)}")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-submit", action="store_true")
    args = parser.parse_args()

    experiments = ALL_EXPERIMENTS
    if args.only:
        experiments = [e.strip() for e in args.only.split(",")]

    mux = RelayMux(port=args.port)
    mux.open()
    log(f"Relay mux connected on {mux.port}")

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    log(f"Enrolled rods: {rod_ids} ({[rod_patterns[r] for r in rod_ids]})")

    handle = _open_scope()
    t_start = time.time()

    suite_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiments_run": experiments,
        "rod_ids": rod_ids,
        "rod_patterns": rod_patterns,
        "awg_drive_uvpp": AWG_DRIVE_UVPP,
        "sample_rate": SAMPLE_RATE,
        "n_avg": N_AVG,
        "n_peaks": N_PEAKS,
    }

    try:
        if "temporal" in experiments:
            suite_results["temporal_stability"] = run_temporal_stability(
                handle, mux, enrolled, rod_patterns, rod_ids
            )

        if "boolean-pairs" in experiments:
            suite_results["boolean_all_pairs"] = run_boolean_all_pairs(
                handle, mux, enrolled, rod_patterns, rod_ids
            )

        if "nn-pairs" in experiments:
            suite_results["nn_all_pairs"] = run_nn_all_pairs(
                handle, mux, enrolled, rod_patterns, rod_ids
            )

        if "boolean-three" in experiments:
            suite_results["boolean_three"] = run_boolean_three(
                handle, mux, enrolled, rod_patterns, rod_ids
            )

        if "chained" in experiments:
            suite_results["chained_boolean"] = run_chained_boolean(
                handle, mux, enrolled, rod_patterns, rod_ids
            )

        if "noise-sweep" in experiments:
            suite_results["noise_sweep"] = run_noise_sweep(
                handle, mux, enrolled, rod_patterns, rod_ids
            )

    finally:
        _close_scope(handle)
        mux.close()

    duration = time.time() - t_start
    suite_results["total_duration_s"] = round(duration, 1)

    # ── Summary ───────────────────────────────────────────────────────
    log("\n" + "=" * 70)
    log("  SUITE SUMMARY")
    log("=" * 70)

    if "temporal_stability" in suite_results:
        ts = suite_results["temporal_stability"]
        log(f"  Temporal: Recall={ts['recall_accuracy']*100:.0f}% "
            f"(margin={ts['recall_mean_margin']:+.2f})  "
            f"Boolean={ts['boolean']['mean_fidelity']*100:.0f}%")

    if "boolean_all_pairs" in suite_results:
        for bp in suite_results["boolean_all_pairs"]:
            if bp.get("skipped"):
                log(f"  Bool {bp['pair'][0]}v{bp['pair'][1]}: SKIPPED")
            else:
                a = bp["analysis"]
                log(f"  Bool {bp['pair'][0]}v{bp['pair'][1]}: "
                    f"AND={a['and_fidelity']*100:.0f}% OR={a['or_fidelity']*100:.0f}% "
                    f"XOR={a['xor_fidelity']*100:.0f}% (overlap={bp['overlap_pct']}%)")

    if "nn_all_pairs" in suite_results:
        for nn in suite_results["nn_all_pairs"]:
            log(f"  NN {nn['pair'][0]}→{nn['pair'][1]}: "
                f"{nn['n_correct']}/{nn['n_steps']} τ={nn['kendall_tau']:.3f}")

    if "boolean_three" in suite_results:
        b3 = suite_results["boolean_three"]["analysis"]
        log(f"  3-Bool: AND3={b3['and3_fidelity']*100:.0f}% "
            f"OR3={b3['or3_fidelity']*100:.0f}% "
            f"MAJ={b3['majority_fidelity']*100:.0f}% "
            f"XOR3={b3['xor3_fidelity']*100:.0f}%")

    if "chained_boolean" in suite_results:
        ch = suite_results["chained_boolean"]
        log(f"  Chained: (A AND B) XOR C = {ch['correct']}/{ch['total']} "
            f"({ch['fidelity']*100:.0f}%)")

    if "noise_sweep" in suite_results:
        for ns in suite_results["noise_sweep"]:
            log(f"  Noise {ns['voltage_frac']*100:.0f}%Vpp: "
                f"recall={'✓' if ns['recall_correct'] else '✗'} "
                f"(margin={ns['recall_margin']:+.1f})  "
                f"bool={ns['boolean_mean']*100:.0f}%")

    log(f"\n  Total duration: {duration:.0f}s")

    # ── Save ──────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(suite_results, f, indent=2, default=str)
    log(f"\n  Results saved to {RESULTS_FILE.relative_to(ROOT)}")
    _save_log()
    log(f"  Log saved to {LOG_FILE.relative_to(ROOT)}")

    # ── Submit ────────────────────────────────────────────────────────
    if not args.dry_run and not args.no_submit:
        log("\n  Submitting to Firestore...")
        try:
            token = _firebase_anon_auth()

            # Build summary data for submission
            summary_parts = []
            if "temporal_stability" in suite_results:
                ts = suite_results["temporal_stability"]
                summary_parts.append(
                    f"Temporal: recall={ts['recall_accuracy']*100:.0f}%, "
                    f"bool={ts['boolean']['mean_fidelity']*100:.0f}%"
                )
            if "boolean_all_pairs" in suite_results:
                means = [bp["analysis"]["mean_fidelity"]
                         for bp in suite_results["boolean_all_pairs"]
                         if not bp.get("skipped")]
                if means:
                    summary_parts.append(
                        f"BoolPairs: mean={np.mean(means)*100:.0f}% "
                        f"(min={min(means)*100:.0f}%, max={max(means)*100:.0f}%)"
                    )
            if "nn_all_pairs" in suite_results:
                accs = [nn["accuracy"] for nn in suite_results["nn_all_pairs"]]
                summary_parts.append(
                    f"NN: mean={np.mean(accs)*100:.0f}% "
                    f"(min={min(accs)*100:.0f}%)"
                )
            if "boolean_three" in suite_results:
                b3 = suite_results["boolean_three"]["analysis"]
                summary_parts.append(f"3-Bool: mean={b3['mean_fidelity']*100:.0f}%")
            if "chained_boolean" in suite_results:
                ch = suite_results["chained_boolean"]
                summary_parts.append(f"Chained: {ch['fidelity']*100:.0f}%")
            if "noise_sweep" in suite_results:
                ns_list = suite_results["noise_sweep"]
                min_v = min(ns["voltage_frac"] for ns in ns_list if ns["recall_correct"])
                summary_parts.append(f"Noise: recall OK down to {min_v*100:.0f}%Vpp")

            data = {
                "n_rods": 4,
                "peaks_per_rod": N_PEAKS,
                "experiments_run": len(experiments),
                "duration_s": int(duration),
            }
            # Populate optional fields from results
            if "temporal_stability" in suite_results:
                ts = suite_results["temporal_stability"]
                data["recall_accuracy"] = round(ts["recall_accuracy"] * 100, 1)
                data["recall_margin"] = round(ts["recall_mean_margin"], 2)
            if "boolean_all_pairs" in suite_results:
                means = [bp["analysis"]["mean_fidelity"]
                         for bp in suite_results["boolean_all_pairs"]
                         if not bp.get("skipped")]
                if means:
                    data["boolean_mean_fidelity"] = round(np.mean(means) * 100, 1)
                    data["boolean_min_fidelity"] = round(min(means) * 100, 1)
            if "nn_all_pairs" in suite_results:
                accs = [nn["accuracy"] for nn in suite_results["nn_all_pairs"]]
                taus = [nn["kendall_tau"] for nn in suite_results["nn_all_pairs"]]
                data["nn_accuracy"] = round(np.mean(accs) * 100, 1)
                data["nn_kendall_tau"] = round(np.mean(taus), 3)
            if "boolean_three" in suite_results:
                b3 = suite_results["boolean_three"]["analysis"]
                data["three_pattern_fidelity"] = round(b3["mean_fidelity"] * 100, 1)
            if "chained_boolean" in suite_results:
                ch = suite_results["chained_boolean"]
                data["chained_fidelity"] = round(ch["fidelity"] * 100, 1)
            if "noise_sweep" in suite_results:
                ns_list = suite_results["noise_sweep"]
                ok_fracs = [ns["voltage_frac"] for ns in ns_list if ns["recall_correct"]]
                if ok_fracs:
                    data["noise_floor_pct"] = round(min(ok_fracs) * 100)
            notes = f"CIM Suite: {'; '.join(summary_parts)}"
            resp = _submit_experiment(token, "exp-cim-suite", data, notes=notes)
            if resp.get("ok"):
                log(f"  Firestore → {resp['id']}")
            else:
                log(f"  Firestore error: {resp.get('error', 'unknown')}")
        except Exception as e:
            log(f"  Firestore submit failed: {e}")

    log("\n  Done.")


if __name__ == "__main__":
    main()
