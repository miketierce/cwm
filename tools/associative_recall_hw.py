#!/usr/bin/env python3
"""
Hardware Associative Recall — 4×4 Discrimination Matrix

Demonstrates compute-in-memory associative recall on the physical 4-rod
array.  For each enrolled rod ("query pattern"), drives the AWG at that
rod's multi-tone eigenfrequencies, then measures every rod's individual
response via the relay mux.

The rod whose stored pattern matches the query should produce the
strongest response — the diagonal of the 4×4 matrix should dominate.
This is the hardware analogue of experiment 06 (simulated associative
recall in glass_resonator.py).

Signal chain:
  AWG OUT → Drive PZTs (all 4 rods share AWG via T-connector)
  Relay N → Sense PZT Rod N → PicoScope Ch A

Protocol:
  For each query Q ∈ {Rod1, Rod2, Rod3, Rod4}:
    1. Drive AWG with multi-tone at Q's enrolled peaks
    2. For each rod R ∈ {1, 2, 3, 4}:
       a. Select relay R (isolate R's sense PZT)
       b. Measure FFT magnitude at each of Q's peak frequencies
       c. Record per-peak and aggregate response
    3. Store row Q of the discrimination matrix

Output:
  - 4×4 discrimination matrix (energy at each query×rod cell)
  - Diagonal dominance in dB
  - Per-peak response logs for every measurement
  - JSON results file with full data
  - Optional Firestore submission

Usage:
  PYTHONPATH=. python tools/associative_recall_hw.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/associative_recall_hw.py --dry-run
  PYTHONPATH=. python tools/associative_recall_hw.py --peaks 5   # use top-5 peaks only
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

# Import cwm_picoscope first to set DYLD_LIBRARY_PATH on macOS
from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux
from picosdk.ps2000 import ps2000

# ── Configuration ─────────────────────────────────────────────────────────

N_PEAKS_DEFAULT = 20      # enrolled peaks per query (use all 20 for weighting)
N_AVG = 12                # captures per measurement point
SETTLE_S = 0.20           # AWG settle time before capture
SETTLE_RELAY_S = 0.05     # settle after relay switch

# Uniqueness weight tiers
WEIGHT_UNIQUE = 4.0       # peak >5% from any other rod's peak
WEIGHT_SEMI   = 2.0       # peak 2–5% from nearest other-rod peak
WEIGHT_SHARED = 0.5       # peak <2% from nearest other-rod peak

# ── Paths ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab"
USERS_FILE = LAB_DIR / "users.json"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = LAB_DIR / "associative_recall"
RESULTS_FILE = RESULTS_DIR / f"recall_{TIMESTAMP}.json"
LOG_FILE = RESULTS_DIR / f"recall_{TIMESTAMP}.log"

# ── Firebase ──────────────────────────────────────────────────────────────

FIREBASE_API_KEY = "AIzaSyCxlNaRNwwOim4-bSYL7MrRuQmDBznlga0"
CWM_SITE_URL = "https://coherent-wave-memory.web.app"


# ═══════════════════════════════════════════════════════════════════════
#  Logging
# ═══════════════════════════════════════════════════════════════════════

_log_lines: list[str] = []


def log(msg: str, also_print: bool = True) -> None:
    """Append to in-memory log and optionally print."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    _log_lines.append(line)
    if also_print:
        print(msg)


def _save_log() -> None:
    """Write accumulated log to disk."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w") as f:
        f.write("\n".join(_log_lines))
        f.write("\n")


# ═══════════════════════════════════════════════════════════════════════
#  Scope helpers (from awg_stepped_dwell_id.py)
# ═══════════════════════════════════════════════════════════════════════

def _open_scope():
    """Open PicoScope with Ch A only."""
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V DC
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B OFF
    log("PicoScope opened (Ch A ±1V DC)")
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
    log("PicoScope closed")


def _measure_at(handle, freq_hz: float, n_avg: int = N_AVG,
                settle_s: float = SETTLE_S) -> dict:
    """Drive AWG at freq_hz, capture n_avg blocks, return measurement data.

    Returns dict with:
      - freq_hz: driven frequency
      - magnitude: mean FFT magnitude at target bin
      - magnitudes: list of per-capture magnitudes
      - noise_floor: median FFT magnitude (background)
      - snr_db: magnitude / noise in dB
    """
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(settle_s)

    magnitudes = []
    noise_floors = []
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
            noise_floors.append(float(np.median(fft)))

    mean_mag = float(np.mean(magnitudes)) if magnitudes else 0.0
    mean_noise = float(np.mean(noise_floors)) if noise_floors else 1.0
    snr_linear = mean_mag / mean_noise if mean_noise > 0 else 0.0
    snr_db = 20 * math.log10(snr_linear) if snr_linear > 1 else 0.0

    return {
        "freq_hz": round(freq_hz, 1),
        "magnitude": round(mean_mag, 1),
        "magnitudes": [round(m, 1) for m in magnitudes],
        "noise_floor": round(mean_noise, 1),
        "snr_db": round(snr_db, 1),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Feedthrough baseline
# ═══════════════════════════════════════════════════════════════════════

def _measure_baseline(handle, all_peaks_hz: list[float],
                      mux: RelayMux = None,
                      rod_ids: list[str] = None) -> dict:
    """Build feedthrough baseline, per-relay if mux provided.

    Returns:
      If mux: {rod_id: (off_freqs, off_mags)} — per-relay baselines
      If no mux: {"shared": (off_freqs, off_mags)}
    """
    sorted_peaks = sorted(set(round(f, 1) for f in all_peaks_hz))

    off_freqs = []
    for i in range(len(sorted_peaks) - 1):
        mid = (sorted_peaks[i] + sorted_peaks[i + 1]) / 2
        if all(abs(mid - p) / p > 0.03 for p in sorted_peaks):
            off_freqs.append(mid)

    off_freqs = [500.0] + off_freqs + [max(sorted_peaks) + 2000.0]

    baselines = {}

    if mux and rod_ids:
        # Per-relay baseline: each relay path has different coupling
        for rid in rod_ids:
            mux.select(int(rid))
            time.sleep(SETTLE_RELAY_S)
            log(f"  Baseline for relay {rid}...", also_print=True)
            off_mags = []
            for f in off_freqs:
                m = _measure_at(handle, f, n_avg=8, settle_s=0.15)
                off_mags.append(m["magnitude"])
                log(f"    BL R{rid} {f:.0f} Hz → {m['magnitude']:.0f}",
                    also_print=False)
            baselines[rid] = (off_freqs, off_mags)
        mux.off()
    else:
        log(f"  Measuring shared baseline at {len(off_freqs)} points...")
        off_mags = []
        for f in off_freqs:
            m = _measure_at(handle, f, n_avg=8, settle_s=0.15)
            off_mags.append(m["magnitude"])
        baselines["shared"] = (off_freqs, off_mags)

    return baselines


def _baseline_at(freq_hz: float, off_freqs: list, off_mags: list) -> float:
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


# ═══════════════════════════════════════════════════════════════════════
#  Peak uniqueness analysis
# ═══════════════════════════════════════════════════════════════════════

def _compute_peak_weights(enrolled: dict[str, list[float]],
                          rod_ids: list[str]) -> dict[str, list[dict]]:
    """Compute per-peak uniqueness weight for each rod.

    For each peak, find minimum frequency distance (%) to nearest peak
    of any OTHER rod.  Assign weight tiers:
      >5%  → UNIQUE  (weight 4.0)
      2-5% → semi    (weight 2.0)
      <2%  → shared  (weight 0.5)

    Returns:
      {rod_id: [{"freq": f, "min_dist_pct": d, "tier": t, "weight": w,
                  "nearest_rod": r}, ...]}
    """
    result = {}
    for rid in rod_ids:
        peaks_info = []
        for freq in enrolled[rid]:
            min_dist = 100.0
            nearest_rod = "?"
            for other in rod_ids:
                if other == rid:
                    continue
                for of in enrolled[other]:
                    dist = abs(freq - of) / max(freq, of) * 100
                    if dist < min_dist:
                        min_dist = dist
                        nearest_rod = other
            if min_dist > 5.0:
                tier, weight = "UNIQUE", WEIGHT_UNIQUE
            elif min_dist > 2.0:
                tier, weight = "semi", WEIGHT_SEMI
            else:
                tier, weight = "shared", WEIGHT_SHARED
            peaks_info.append({
                "freq": freq,
                "min_dist_pct": round(min_dist, 1),
                "tier": tier,
                "weight": weight,
                "nearest_rod": nearest_rod,
            })
        result[rid] = peaks_info
    return result


# ═══════════════════════════════════════════════════════════════════════
#  Main experiment
# ═══════════════════════════════════════════════════════════════════════

def run_associative_recall(mux: RelayMux, n_peaks: int = N_PEAKS_DEFAULT,
                           strategy: str = "template") -> dict:
    """Run the 4×4 associative recall experiment.

    strategy:
      "all"      — equal weight on all peaks, baseline ratio (original)
      "weighted" — weight peaks by uniqueness (UNIQUE=4×, semi=2×, shared=0.5×)
      "unique"   — only use peaks with >5% uniqueness
      "template" — cross-relay normalization with enrollment template matching:
                   for each query freq, normalize magnitude across all 4 sense
                   relays, then boost score where sense rod is expected to
                   resonate and penalize where it shouldn't.  No baseline needed.

    Returns full result dict with matrix, per-peak logs, and diagnostics.
    """
    # Load enrollment data
    with open(USERS_FILE) as f:
        db = json.load(f)

    enrolled = {}
    rod_patterns = {}
    for rid in sorted(db["rods"].keys()):
        r = db["rods"][rid]
        if r.get("enrolled"):
            enrolled[rid] = r["perturbed_hz"][:n_peaks]
            rod_patterns[rid] = r.get("pattern", "?")

    rod_ids = sorted(enrolled.keys())
    n_rods = len(rod_ids)
    all_peaks = [f for peaks in enrolled.values() for f in peaks]

    # Compute uniqueness weights
    peak_weights = _compute_peak_weights(enrolled, rod_ids)

    # Filter peaks for "unique" strategy
    if strategy == "unique":
        for rid in rod_ids:
            pw = peak_weights[rid]
            unique_indices = [i for i, p in enumerate(pw) if p["tier"] == "UNIQUE"]
            semi_indices = [i for i, p in enumerate(pw) if p["tier"] == "semi"]
            # Use unique + semi if fewer than 3 unique peaks
            if len(unique_indices) < 3:
                keep = unique_indices + semi_indices
            else:
                keep = unique_indices
            keep.sort()
            if len(keep) == 0:
                keep = [i for i, p in enumerate(pw)
                        if p["min_dist_pct"] == max(x["min_dist_pct"] for x in pw)]
            enrolled[rid] = [enrolled[rid][i] for i in keep]
            peak_weights[rid] = [peak_weights[rid][i] for i in keep]
        # Recompute all_peaks after filtering
        all_peaks = [f for peaks in enrolled.values() for f in peaks]

    log("=" * 70)
    log("  HARDWARE ASSOCIATIVE RECALL — 4×4 Discrimination Matrix")
    log("=" * 70)
    log(f"  Rods: {rod_ids}  Patterns: {[rod_patterns[r] for r in rod_ids]}")
    log(f"  Strategy: {strategy}")
    log(f"  Peaks per query: {[len(enrolled[r]) for r in rod_ids]}")
    log(f"  Captures per point: {N_AVG}")
    log(f"  Relay mux: {mux.port}")

    # Show weight profile
    for rid in rod_ids:
        pw = peak_weights[rid]
        n_u = sum(1 for p in pw if p["tier"] == "UNIQUE")
        n_s = sum(1 for p in pw if p["tier"] == "semi")
        n_sh = sum(1 for p in pw if p["tier"] == "shared")
        total_w = sum(p["weight"] for p in pw)
        log(f"  Rod {rid}: {n_u} unique + {n_s} semi + {n_sh} shared "
            f"= {len(pw)} peaks, total_weight={total_w:.1f}")
    log("")

    t_start = time.time()
    handle = _open_scope()

    # Full experiment data
    experiment = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rod_ids": rod_ids,
        "patterns": {r: rod_patterns[r] for r in rod_ids},
        "enrolled_peaks": {r: enrolled[r] for r in rod_ids},
        "n_peaks": n_peaks,
        "strategy": strategy,
        "peak_weights": {r: [p["weight"] for p in peak_weights[r]] for r in rod_ids},
        "n_avg": N_AVG,
        "settle_s": SETTLE_S,
        "awg_uvpp": AWG_DRIVE_UVPP,
        "sample_rate": SAMPLE_RATE,
        "mux_port": mux.port,
    }

    try:
        # ── Phase 0: Per-relay feedthrough baseline ──────────────────
        log("Phase 0: Per-relay feedthrough baselines")
        baselines = _measure_baseline(handle, all_peaks, mux=mux, rod_ids=rod_ids)
        experiment["baseline"] = {
            rid: {
                "freqs": bl[0],
                "mags": [round(m, 1) for m in bl[1]],
            }
            for rid, bl in baselines.items()
        }
        n_bl = sum(len(bl[0]) for bl in baselines.values())
        log(f"  Baselines: {len(baselines)} relays × {len(list(baselines.values())[0][0])} points = {n_bl} total\n")

        # ── Phase 1: 4×4 measurement matrix ───────────────────────────
        #
        # matrix[query_rod][sense_rod] = aggregate response energy
        # peak_log[query_rod][sense_rod] = list of per-peak measurements
        #
        matrix = {}         # {query_id: {sense_id: energy}}
        ratio_matrix = {}   # {query_id: {sense_id: mean_ratio}}
        weighted_matrix = {} # {query_id: {sense_id: weighted_score}}
        template_matrix = {} # {query_id: {sense_id: template_score}}
        peak_log = {}       # {query_id: {sense_id: [per-peak data]}}

        for qi, query_rod in enumerate(rod_ids):
            query_peaks = enrolled[query_rod]
            query_pattern = rod_patterns[query_rod]
            query_pw = peak_weights[query_rod]

            log(f"═══ Query {qi+1}/{n_rods}: Rod {query_rod} "
                f"(Pattern {query_pattern}, {len(query_peaks)} peaks) ═══")

            matrix[query_rod] = {}
            ratio_matrix[query_rod] = {}
            weighted_matrix[query_rod] = {}
            template_matrix[query_rod] = {}
            peak_log[query_rod] = {}

            # Collect raw measurements: raw_meas[sense_rod][peak_idx] = measurement dict
            raw_meas = {sr: [] for sr in rod_ids}

            for si, sense_rod in enumerate(rod_ids):
                # Switch relay to sense this rod
                mux.select(int(sense_rod))
                time.sleep(SETTLE_RELAY_S)
                log(f"  ─── Sense Rod {sense_rod} "
                    f"(Pattern {rod_patterns[sense_rod]}) ───")

                # Use this relay's own baseline for normalization
                bl_freqs, bl_mags = baselines[sense_rod]

                rod_energy = 0.0
                rod_ratios = []
                rod_weighted = 0.0
                rod_peaks_data = []

                for pi, freq in enumerate(query_peaks):
                    w = query_pw[pi]["weight"]
                    m = _measure_at(handle, freq)
                    bl = _baseline_at(freq, bl_freqs, bl_mags)
                    ratio = m["magnitude"] / bl if bl > 0 else 0.0

                    rod_energy += m["magnitude"]
                    rod_ratios.append(ratio)
                    rod_weighted += w * ratio  # weighted ratio sum

                    peak_data = {
                        "peak_idx": pi + 1,
                        "freq_hz": round(freq, 1),
                        "magnitude": m["magnitude"],
                        "baseline": round(bl, 1),
                        "ratio": round(ratio, 2),
                        "weight": w,
                        "weighted_ratio": round(w * ratio, 2),
                        "tier": query_pw[pi]["tier"],
                        "snr_db": m["snr_db"],
                        "noise_floor": m["noise_floor"],
                        "per_capture": m["magnitudes"],
                    }
                    rod_peaks_data.append(peak_data)
                    raw_meas[sense_rod].append(m)

                    # Compact per-peak log
                    tier_tag = f"[{query_pw[pi]['tier']:6s}]"
                    marker = "**" if ratio > 2.0 else "  "
                    log(f"    f{pi+1:2d}={freq:7.1f} Hz  "
                        f"mag={m['magnitude']:7.0f}  "
                        f"BL={bl:6.0f}  "
                        f"r={ratio:5.2f}  "
                        f"w={w:.1f}  "
                        f"wr={w*ratio:6.2f}{marker}  "
                        f"{tier_tag}",
                        also_print=False)

                mean_ratio = float(np.mean(rod_ratios))
                matrix[query_rod][sense_rod] = round(rod_energy, 1)
                ratio_matrix[query_rod][sense_rod] = round(mean_ratio, 2)
                weighted_matrix[query_rod][sense_rod] = round(rod_weighted, 2)
                peak_log[query_rod][sense_rod] = rod_peaks_data

                n_strong = sum(1 for r in rod_ratios if r > 2.0)
                log(f"    → energy={rod_energy:.0f}  "
                    f"mean_ratio={mean_ratio:.2f}  "
                    f"weighted={rod_weighted:.1f}  "
                    f"strong={n_strong}/{len(query_peaks)}")

            # ── Template scoring (cross-relay normalization) ──────────
            # For each peak frequency, normalize magnitude across all 4
            # sense rods.  Then: boost if sense rod is EXPECTED to resonate
            # at that freq (within 3% of one of its enrolled peaks),
            # penalize if not expected.
            log(f"\n  Template scoring for Query {query_rod}:")
            # all_enrolled has full 20-peak enrollment for template matching
            all_enrolled = {rid: db["rods"][rid]["perturbed_hz"]
                            for rid in rod_ids}

            for sr in rod_ids:
                tmpl_score = 0.0
                for pi, freq in enumerate(query_peaks):
                    # Magnitudes across all sense rods at this frequency
                    mags = {s: raw_meas[s][pi]["magnitude"] for s in rod_ids}
                    total = sum(mags.values())
                    if total == 0:
                        continue
                    frac = mags[sr] / total

                    # Does this sense rod have an enrolled peak near this freq?
                    expected = any(
                        abs(freq - ep) / max(freq, ep) < 0.03
                        for ep in all_enrolled[sr]
                    )

                    if expected:
                        tmpl_score += frac * 3.0   # expected resonance → boost
                    else:
                        tmpl_score -= frac * 1.0   # unexpected → penalize

                template_matrix[query_rod][sr] = round(tmpl_score, 2)
                log(f"    Sense Rod {sr}: template_score={tmpl_score:.2f}"
                    f"{'  ◄ (diagonal)' if sr == query_rod else ''}",
                    also_print=False)

            # Print compact template scores
            tmpl_winner = max(template_matrix[query_rod],
                              key=template_matrix[query_rod].get)
            log(f"  Template: " + "  ".join(
                f"R{sr}={template_matrix[query_rod][sr]:+.1f}"
                f"{'◄' if sr == query_rod else ' '}"
                for sr in rod_ids) +
                f"  → R{tmpl_winner} "
                f"{'✓' if tmpl_winner == query_rod else '✗'}")

            log("")

        # Turn off relay
        mux.off()

    finally:
        _close_scope(handle)

    duration = time.time() - t_start
    experiment["duration_s"] = round(duration, 1)
    experiment["matrix_energy"] = matrix
    experiment["matrix_ratio"] = ratio_matrix
    experiment["matrix_weighted"] = weighted_matrix
    experiment["matrix_template"] = template_matrix
    experiment["peak_log"] = peak_log

    # ── Analysis ──────────────────────────────────────────────────────

    log("=" * 70)
    log("  RESULTS")
    log("=" * 70)

    # Print energy matrix
    log("\n  Energy Matrix (Query → Sense):")
    header = "         " + "".join(f"  Rod {r:>2s}  " for r in rod_ids)
    log(header)
    log("         " + "-" * (10 * n_rods))
    for qr in rod_ids:
        cells = []
        for sr in rod_ids:
            val = matrix[qr][sr]
            marker = " ◄" if qr == sr else "  "
            cells.append(f"{val:7.0f}{marker}")
        log(f"  Q={qr:>2s}  |{'|'.join(cells)}|")

    # Print ratio matrix
    log("\n  Ratio Matrix (Query → Sense, vs feedthrough baseline):")
    header = "         " + "".join(f"  Rod {r:>2s}  " for r in rod_ids)
    log(header)
    log("         " + "-" * (10 * n_rods))
    for qr in rod_ids:
        cells = []
        for sr in rod_ids:
            val = ratio_matrix[qr][sr]
            marker = " ◄" if qr == sr else "  "
            cells.append(f"{val:7.2f}{marker}")
        log(f"  Q={qr:>2s}  |{'|'.join(cells)}|")

    # Print weighted matrix
    log("\n  Weighted Matrix (uniqueness-weighted ratio sums):")
    header = "         " + "".join(f"  Rod {r:>2s}  " for r in rod_ids)
    log(header)
    log("         " + "-" * (10 * n_rods))
    for qr in rod_ids:
        cells = []
        for sr in rod_ids:
            val = weighted_matrix[qr][sr]
            marker = " ◄" if qr == sr else "  "
            cells.append(f"{val:7.1f}{marker}")
        log(f"  Q={qr:>2s}  |{'|'.join(cells)}|")

    # Print template matrix
    log("\n  Template Matrix (cross-relay normalized, enrollment-matched):")
    header = "         " + "".join(f"  Rod {r:>2s}  " for r in rod_ids)
    log(header)
    log("         " + "-" * (10 * n_rods))
    for qr in rod_ids:
        cells = []
        for sr in rod_ids:
            val = template_matrix[qr][sr]
            marker = " ◄" if qr == sr else "  "
            cells.append(f"{val:+7.1f}{marker}")
        log(f"  Q={qr:>2s}  |{'|'.join(cells)}|")

    # Diagonal dominance analysis
    log("\n  Diagonal Dominance (energy-based):")
    diagonal_dominance_db = []
    correct_count = 0

    for qr in rod_ids:
        diag_energy = matrix[qr][qr]
        off_diag = [matrix[qr][sr] for sr in rod_ids if sr != qr]
        best_off = max(off_diag)
        worst_off = min(off_diag)
        mean_off = float(np.mean(off_diag))

        # Dominance in dB
        if best_off > 0:
            dom_db = 20 * math.log10(diag_energy / best_off)
        else:
            dom_db = float("inf")
        diagonal_dominance_db.append(dom_db)

        # Did the diagonal win?
        won = diag_energy > best_off
        if won:
            correct_count += 1

        symbol = "✓" if won else "✗"
        log(f"    Query Rod {qr}: diag={diag_energy:.0f}  "
            f"best_off={best_off:.0f}  "
            f"dominance={dom_db:+.1f} dB  {symbol}")

    # Also check ratio-matrix diagonal dominance (coupling-normalized)
    log("\n  Diagonal Dominance (ratio-normalized):")
    ratio_correct_count = 0
    ratio_dominance_db = []
    for qr in rod_ids:
        diag_ratio = ratio_matrix[qr][qr]
        off_ratios = [ratio_matrix[qr][sr] for sr in rod_ids if sr != qr]
        best_off_ratio = max(off_ratios)
        if best_off_ratio > 0:
            dom_db = 20 * math.log10(diag_ratio / best_off_ratio)
        else:
            dom_db = float("inf")
        ratio_dominance_db.append(dom_db)
        won = diag_ratio > best_off_ratio
        if won:
            ratio_correct_count += 1
        symbol = "✓" if won else "✗"
        log(f"    Query Rod {qr}: diag_ratio={diag_ratio:.2f}  "
            f"best_off={best_off_ratio:.2f}  "
            f"dominance={dom_db:+.1f} dB  {symbol}")

    # Weighted diagonal dominance (the key metric for "weighted" strategy)
    log("\n  Diagonal Dominance (weighted score):")
    wtd_correct_count = 0
    wtd_dominance_db = []
    for qr in rod_ids:
        diag_wtd = weighted_matrix[qr][qr]
        off_wtds = [weighted_matrix[qr][sr] for sr in rod_ids if sr != qr]
        best_off_wtd = max(off_wtds)
        if best_off_wtd > 0:
            dom_db = 20 * math.log10(diag_wtd / best_off_wtd)
        else:
            dom_db = float("inf")
        wtd_dominance_db.append(dom_db)
        won = diag_wtd > best_off_wtd
        if won:
            wtd_correct_count += 1
        symbol = "✓" if won else "✗"
        log(f"    Query Rod {qr}: diag_wtd={diag_wtd:.1f}  "
            f"best_off={best_off_wtd:.1f}  "
            f"dominance={dom_db:+.1f} dB  {symbol}")

    # Template diagonal dominance (the key metric for "template" strategy)
    log("\n  Diagonal Dominance (template — cross-relay normalized):")
    tmpl_correct_count = 0
    tmpl_dominance = []  # raw score margin (not dB — can be negative)
    for qr in rod_ids:
        diag_tmpl = template_matrix[qr][qr]
        off_tmpls = [template_matrix[qr][sr] for sr in rod_ids if sr != qr]
        best_off_tmpl = max(off_tmpls)
        margin = diag_tmpl - best_off_tmpl
        won = diag_tmpl > best_off_tmpl
        if won:
            tmpl_correct_count += 1
        symbol = "✓" if won else "✗"
        log(f"    Query Rod {qr}: diag={diag_tmpl:+.2f}  "
            f"best_off={best_off_tmpl:+.2f}  "
            f"margin={margin:+.2f}  {symbol}")
        tmpl_dominance.append(margin)

    mean_dominance = float(np.mean(diagonal_dominance_db))
    recall_accuracy = correct_count / n_rods
    mean_ratio_dom = float(np.mean(ratio_dominance_db))
    ratio_accuracy = ratio_correct_count / n_rods
    mean_wtd_dom = float(np.mean(wtd_dominance_db))
    wtd_accuracy = wtd_correct_count / n_rods
    mean_tmpl_margin = float(np.mean(tmpl_dominance))
    tmpl_accuracy = tmpl_correct_count / n_rods

    log(f"\n  ─── Summary ───")
    log(f"  Strategy: {strategy}")
    log(f"  Energy recall accuracy:   {correct_count}/{n_rods} "
        f"({recall_accuracy*100:.0f}%)")
    log(f"  Ratio recall accuracy:    {ratio_correct_count}/{n_rods} "
        f"({ratio_accuracy*100:.0f}%)")
    log(f"  Weighted recall accuracy: {wtd_correct_count}/{n_rods} "
        f"({wtd_accuracy*100:.0f}%)")
    log(f"  Template recall accuracy: {tmpl_correct_count}/{n_rods} "
        f"({tmpl_accuracy*100:.0f}%)")
    log(f"  Mean energy dominance:    {mean_dominance:+.1f} dB")
    log(f"  Mean ratio dominance:     {mean_ratio_dom:+.1f} dB")
    log(f"  Mean weighted dominance:  {mean_wtd_dom:+.1f} dB")
    log(f"  Mean template margin:     {mean_tmpl_margin:+.2f}")
    log(f"  Duration: {duration:.1f}s")

    # Spectral overlap analysis — explains recall accuracy
    log(f"\n  ─── Overlap Analysis (explains low recall) ───")
    for qi, qr in enumerate(rod_ids):
        qpeaks = set(round(f, 0) for f in enrolled[qr])
        for sr in rod_ids:
            if sr == qr:
                continue
            speaks = set(round(f, 0) for f in enrolled[sr])
            shared = sum(1 for qf in enrolled[qr]
                         if any(abs(qf - sf) / max(qf, sf) < 0.05
                                for sf in enrolled[sr]))
            log(f"    Q={qr} vs S={sr}: {shared}/{len(enrolled[qr])} "
                f"query peaks within 5% of sense rod's peaks "
                f"({shared/len(enrolled[qr])*100:.0f}% overlap)")

    # Store analysis
    experiment["analysis"] = {
        "strategy": strategy,
        "diagonal_dominance_db": [round(d, 1) for d in diagonal_dominance_db],
        "mean_dominance_db": round(mean_dominance, 1),
        "recall_accuracy": recall_accuracy,
        "correct_count": correct_count,
        "ratio_dominance_db": [round(d, 1) for d in ratio_dominance_db],
        "mean_ratio_dominance_db": round(mean_ratio_dom, 1),
        "ratio_correct_count": ratio_correct_count,
        "ratio_accuracy": ratio_accuracy,
        "weighted_dominance_db": [round(d, 1) for d in wtd_dominance_db],
        "mean_weighted_dominance_db": round(mean_wtd_dom, 1),
        "weighted_correct_count": wtd_correct_count,
        "weighted_accuracy": wtd_accuracy,
        "template_margin": [round(d, 2) for d in tmpl_dominance],
        "mean_template_margin": round(mean_tmpl_margin, 2),
        "template_correct_count": tmpl_correct_count,
        "template_accuracy": tmpl_accuracy,
        "n_rods": n_rods,
    }

    # Per-query detail for Firestore
    query_details = []
    for qi, qr in enumerate(rod_ids):
        ranked = sorted(
            [(sr, matrix[qr][sr]) for sr in rod_ids],
            key=lambda x: -x[1]
        )
        query_details.append({
            "query_rod": qr,
            "query_pattern": rod_patterns[qr],
            "ranked": [{"rod": r, "energy": round(e, 1)} for r, e in ranked],
            "winner": ranked[0][0],
            "correct": ranked[0][0] == qr,
            "dominance_db": round(diagonal_dominance_db[qi], 1),
        })
    experiment["query_details"] = query_details

    return experiment


# ═══════════════════════════════════════════════════════════════════════
#  Firestore submission
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


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Hardware associative recall — 4×4 discrimination matrix"
    )
    parser.add_argument(
        "--port", type=str, default=None,
        help="Serial port for relay mux (default: auto-detect CH340)"
    )
    parser.add_argument(
        "--peaks", type=int, default=N_PEAKS_DEFAULT,
        help=f"Number of enrolled peaks per query (default: {N_PEAKS_DEFAULT})"
    )
    parser.add_argument(
        "--strategy", type=str, default="template",
        choices=["all", "weighted", "unique", "template"],
        help="Scoring strategy: all (equal weight), weighted (uniqueness-weighted), "
             "unique (unique+semi peaks only), template (cross-relay + enrollment matching). "
             "Default: template"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run experiment but don't submit to Firestore"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print full JSON result to stdout"
    )
    args = parser.parse_args()

    # Open relay mux
    mux = RelayMux(port=args.port)
    mux.open()
    log(f"Relay mux connected on {mux.port}")

    try:
        result = run_associative_recall(mux, n_peaks=args.peaks,
                                        strategy=args.strategy)
    finally:
        mux.close()

    # Save results to disk
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)
    log(f"\nResults saved to {RESULTS_FILE.relative_to(ROOT)}")

    # Save log
    _save_log()
    log(f"Log saved to {LOG_FILE.relative_to(ROOT)}")

    # Submit to Firestore as exp-hw-auth (closest existing type)
    if not args.dry_run:
        log("\nSubmitting to Firestore...")
        try:
            token = _firebase_anon_auth()
            analysis = result["analysis"]

            data = {
                "n_rods": analysis["n_rods"],
                "peaks_per_rod": result["n_peaks"],
                "sample_rate": SAMPLE_RATE,
                "freq_resolution": round(SAMPLE_RATE / (N_SAMPLES * 4), 1),
                "auth_rms_pct": max(0, round(analysis.get("mean_template_margin", 0) * 100, 1)),
                "auth_matched_peaks": analysis.get("template_correct_count", analysis["correct_count"]),
                "auth_score_pct": max(0, round(analysis.get("template_accuracy", analysis["recall_accuracy"]) * 100, 1)),
                "next_best_score_pct": 0,
                "min_cross_rod_pct": round(analysis.get("template_accuracy", analysis["recall_accuracy"]) * 100, 1),
                "repro_peaks_matched": f"{analysis.get('template_correct_count', analysis['correct_count'])}/{analysis['n_rods']}",
                "excitation_method": "Piezo pulse",
                "correct_rod_identified": "Yes" if analysis.get("template_accuracy", 0) == 1.0 else "No",
            }

            notes = (
                f"Associative recall 4×4 discrimination matrix. "
                f"Strategy: {result.get('strategy', 'all')}. "
                f"Accuracy: energy={analysis['correct_count']}/{analysis['n_rods']}, "
                f"template={analysis.get('template_correct_count', '?')}/{analysis['n_rods']}. "
                f"Mean template margin: {analysis.get('mean_template_margin', 0):.2f}. "
                f"{result['n_peaks']} max peaks/query, {N_AVG} avg/point. "
                f"Relay-mux isolated. {TIMESTAMP}. "
                f"Duration: {result['duration_s']:.0f}s."
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

    if args.json:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
