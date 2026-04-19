#!/usr/bin/env python3
"""
Push Boolean Compute — find the upper bit-count limit.

Extends the sweep with:
  - Plate A (relay 1) added to receiver pool (8 receivers total)
  - Supplemental probes at gap frequencies between known modes
  - Cross-detection of modes from capture data (frequencies where a
    receiver shows strong signal but was not in its census)
  - ALL possible 2-way plate partitions tested
  - Reports the configuration with maximum bits at 100% fidelity

Usage:
  DYLD_LIBRARY_PATH="..." python tools/plate_boolean_push.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260417_200041.json
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
LAB_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ─────────────────────────────────────────────────────

N_AVG = 8
SETTLE_S = 0.15
SETTLE_RELAY = 0.10
FREQ_MATCH_PCT = 3.0
INTRA_DEDUP_PCT = 1.0
AWG_DRIVE_UVPP = 2_000_000
NEW_MODE_THRESHOLD = 1_500_000  # mag above this on a non-census freq = new mode
PROBE_GAP_MIN_HZ = 2000        # only probe gaps wider than this

# All 8 receivers (includes plate A)
ALL_RECEIVERS = {
    "1":    (1, "A-NE"),
    "2":    (2, "B-NE"),
    "3_NE": (3, "G-NE"),
    "3_NW": (4, "G-NW"),
    "4_NE": (5, "D-NE"),
    "4_NW": (6, "D-NW"),
    "5_NE": (7, "H-NE"),
    "5_NW": (8, "H-NW"),
}

# Plate → census keys
PLATES = {
    "A": ["1"],
    "B": ["2"],
    "G": ["3_NE", "3_NW"],
    "D": ["4_NE", "4_NW"],
    "H": ["5_NE", "5_NW"],
}

# ── Logging ───────────────────────────────────────────────────────────

_log_lines: list[str] = []


def log(msg: str = "", also_print: bool = True) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    _log_lines.append(f"[{ts}] {msg}")
    if also_print:
        print(msg, flush=True)


# ── Scope helpers ─────────────────────────────────────────────────────

def _open_scope():
    import cwm_picoscope  # noqa: F401
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    log("  PicoScope opened (Ch A ±1V DC)")
    return handle


def _close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    log("  PicoScope closed")


def _set_awg(handle, freq_hz):
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0)


def _awg_off(handle):
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)


def _capture_mag(handle, drive_freq_hz, n_avg=N_AVG):
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE
    from picosdk.ps2000 import ps2000

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
            None, None, ctypes.byref(overflow), N_SAMPLES)
        if n > 0:
            raw = np.array(buf_a[:n], dtype=np.float64)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            target_bin = int(round(drive_freq_hz / bin_hz))
            lo = max(0, target_bin - 3)
            hi = min(len(fft_mag) - 1, target_bin + 3)
            magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))

    return float(np.mean(magnitudes)) if magnitudes else 0.0


# ── Frequency helpers ─────────────────────────────────────────────────

def freq_match(f1, f2, pct=FREQ_MATCH_PCT):
    return abs(f1 - f2) / max(f1, f2) * 100 < pct


def nearest_freq(target, freqs):
    return min(freqs, key=lambda f: abs(f - target))


def classify_frequencies(peaks_a, peaks_b, match_pct=FREQ_MATCH_PCT):
    both = []
    a_only = []
    b_used = [False] * len(peaks_b)

    for fa in peaks_a:
        matched = False
        for bi, fb in enumerate(peaks_b):
            if not b_used[bi] and abs(fa - fb) / max(fa, fb) * 100 < match_pct:
                both.append((fa + fb) / 2.0)
                b_used[bi] = True
                matched = True
                break
        if not matched:
            a_only.append(fa)

    b_only = [peaks_b[i] for i in range(len(peaks_b)) if not b_used[i]]
    return {
        "both": sorted(both),
        "a_only": sorted(a_only),
        "b_only": sorted(b_only),
        "all": sorted(both + a_only + b_only),
    }


def merge_strong(keys, strong_per_key, dedup_pct=INTRA_DEDUP_PCT):
    raw = []
    for key in keys:
        for freq in strong_per_key.get(key, []):
            raw.append((freq, key))
    raw.sort(key=lambda x: x[0])

    merged = []
    for freq, key in raw:
        if merged:
            last_freq, last_keys = merged[-1]
            if abs(freq - last_freq) / max(freq, last_freq) * 100 < dedup_pct:
                merged[-1] = (last_freq, last_keys | {key})
                continue
        merged.append((freq, {key}))

    return [(f, frozenset(ks)) for f, ks in merged]


# ── Master frequency list ─────────────────────────────────────────────

def build_master_freqs(census):
    """All census frequencies plus probes in gaps."""
    raw = set()
    for key in ALL_RECEIVERS:
        if key in census and census[key].get("peaks"):
            for p in census[key]["peaks"]:
                raw.add(p["freq_hz"])
    master = sorted(raw)

    # Add probes in gaps > PROBE_GAP_MIN_HZ
    probes = []
    for i in range(len(master) - 1):
        gap = master[i + 1] - master[i]
        if gap > PROBE_GAP_MIN_HZ:
            n = max(1, int(gap / 3000))
            for j in range(1, n + 1):
                f = master[i] + gap * j / (n + 1)
                probes.append(round(f, 1))

    # Also probe below lowest and above highest
    if master[0] > 8000:
        probes.extend([5000.0, 7000.0, 9000.0])
    if master[-1] < 95000:
        probes.extend([92000.0, 95000.0])

    all_freqs = sorted(set(master) | set(probes))
    return all_freqs, sorted(set(master)), sorted(probes)


# ── Comprehensive capture ─────────────────────────────────────────────

def comprehensive_capture(handle, mux, all_freqs):
    receivers = [(k, r, l) for k, (r, l) in ALL_RECEIVERS.items()]
    capture = {}
    total = len(all_freqs) * len(receivers)
    done = 0

    for fi, freq in enumerate(all_freqs):
        _set_awg(handle, freq)
        time.sleep(SETTLE_S)

        capture[freq] = {}
        for key, relay, label in receivers:
            mux.select(relay)
            time.sleep(SETTLE_RELAY)
            mag = _capture_mag(handle, freq)
            capture[freq][key] = mag
            done += 1

        if (fi + 1) % 5 == 0 or fi == len(all_freqs) - 1:
            log(f"    {fi+1}/{len(all_freqs)} freqs  "
                f"({done}/{total} meas)  "
                f"last={freq/1000:.1f}k")

    mux.off()
    return capture


# ── Cross-detection of new modes ──────────────────────────────────────

def cross_detect_modes(capture, census, all_freqs, threshold=NEW_MODE_THRESHOLD):
    """Find frequencies where a receiver shows strong signal but no census peak."""
    new_modes = {}  # key → [freq_hz, ...]

    for freq in all_freqs:
        readings = capture.get(freq, {})
        for key in ALL_RECEIVERS:
            if key not in census or not census[key].get("peaks"):
                continue
            mag = readings.get(key, 0)
            if mag < threshold:
                continue
            # Check if this freq is near any existing census peak for this key
            census_freqs = [p["freq_hz"] for p in census[key]["peaks"]]
            is_known = any(abs(freq - cf) / max(freq, cf) * 100 < 2.0
                          for cf in census_freqs)
            if not is_known:
                new_modes.setdefault(key, []).append((freq, mag))

    return new_modes


# ── Generate all 2-way plate partitions ───────────────────────────────

def generate_partitions():
    """All non-trivial 2-way splits of plates. Each side has ≥1 plate."""
    all_plates = ["A", "B", "G", "D", "H"]
    partitions = []
    seen = set()

    for r in range(1, len(all_plates)):
        for combo in combinations(all_plates, r):
            side_a = sorted(combo)
            side_b = sorted(set(all_plates) - set(combo))
            key = (tuple(side_a), tuple(side_b))
            rev = (tuple(side_b), tuple(side_a))
            if key not in seen and rev not in seen:
                seen.add(key)
                partitions.append((side_a, side_b))

    return partitions


def expand_partition(plates_a, plates_b):
    """Convert plate names to census keys."""
    keys_a = []
    for p in plates_a:
        keys_a.extend(PLATES[p])
    keys_b = []
    for p in plates_b:
        keys_b.extend(PLATES[p])
    return keys_a, keys_b


# ── Analysis (same logic as sweep, with per-key thresholds) ───────────

def analyze_partition(capture, census, all_freqs, keys_a, keys_b,
                      use_prescan=True, label=""):
    """Analyze one partition. Returns dict with fidelity metrics."""
    all_keys = keys_a + keys_b

    # 1. Enrolled modes per key
    enrolled = {}
    for key in all_keys:
        if key in census and census[key].get("peaks"):
            enrolled[key] = [p["freq_hz"] for p in census[key]["peaks"]]
        else:
            enrolled[key] = []

    # 2. Prescan filtering per key
    strong_per_key = {}
    for key in all_keys:
        peaks = enrolled[key]
        if not peaks:
            strong_per_key[key] = []
            continue

        scan = []
        for freq in peaks:
            nf = nearest_freq(freq, all_freqs)
            mag = capture.get(nf, {}).get(key, 0)
            scan.append((freq, mag))

        if not use_prescan or len(scan) <= 2:
            strong_per_key[key] = list(peaks)
        else:
            mags_sorted = sorted([m for _, m in scan])
            mid = max(1, len(mags_sorted) // 2)
            med_hi = float(np.median(mags_sorted[mid:]))
            med_lo = float(np.median(mags_sorted[:mid]))
            thresh = math.sqrt(med_hi * med_lo) if med_lo > 0 else med_hi * 0.1
            strong_per_key[key] = [f for f, m in scan if m > thresh]

    # 3. Merge strong modes within each pattern
    strong_a = merge_strong(keys_a, strong_per_key)
    strong_b = merge_strong(keys_b, strong_per_key)

    # 4. Classify
    freqs_a = [f for f, _ in strong_a]
    freqs_b = [f for f, _ in strong_b]
    classes = classify_frequencies(freqs_a, freqs_b)
    union_freqs = classes["all"]

    if not union_freqs:
        return {"total_bits": 0, "mean_fidelity": 0, "label": label,
                "use_prescan": use_prescan}

    # 5. Build category map
    freq_cat = {}
    for f in classes["both"]:
        freq_cat[round(f, 1)] = "both"
    for f in classes["a_only"]:
        freq_cat[round(f, 1)] = "a_only"
    for f in classes["b_only"]:
        freq_cat[round(f, 1)] = "b_only"

    def find_sources(freq, strong_modes):
        for sf, sources in strong_modes:
            if freq_match(freq, sf):
                return sources
        return frozenset()

    # 6. Per-key thresholds
    key_thresholds = {}
    for key in all_keys:
        strong = strong_a if key in keys_a else strong_b
        self_mags = []
        for sf, sources in strong:
            if key in sources:
                nf = nearest_freq(sf, all_freqs)
                self_mags.append(capture.get(nf, {}).get(key, 0))
        key_thresholds[key] = min(self_mags) * 0.5 if self_mags else float('inf')

    # 7. Detection and scoring
    and_c = or_c = xor_c = 0
    total_bits = len(union_freqs)
    failures = []

    for freq in union_freqs:
        cat = freq_cat.get(round(freq, 1), "?")
        a_enrolled = cat in ("both", "a_only")
        b_enrolled = cat in ("both", "b_only")

        nf = nearest_freq(freq, all_freqs)

        det_a = False
        if a_enrolled:
            sources = find_sources(freq, strong_a)
            for key in sources:
                if capture.get(nf, {}).get(key, 0) > key_thresholds.get(key, float('inf')):
                    det_a = True
                    break

        det_b = False
        if b_enrolled:
            sources = find_sources(freq, strong_b)
            for key in sources:
                if capture.get(nf, {}).get(key, 0) > key_thresholds.get(key, float('inf')):
                    det_b = True
                    break

        and_got = det_a and det_b
        or_got = det_a or det_b
        xor_got = det_a != det_b

        and_exp = a_enrolled and b_enrolled
        or_exp = a_enrolled or b_enrolled
        xor_exp = a_enrolled != b_enrolled

        and_ok = and_exp == and_got
        or_ok = or_exp == or_got
        xor_ok = xor_exp == xor_got

        if and_ok: and_c += 1
        if or_ok: or_c += 1
        if xor_ok: xor_c += 1

        if not (and_ok and or_ok and xor_ok):
            failures.append({
                "freq": round(freq, 1),
                "cat": cat,
                "det_a": det_a, "exp_a": a_enrolled,
                "det_b": det_b, "exp_b": b_enrolled,
            })

    and_f = and_c / total_bits
    or_f = or_c / total_bits
    xor_f = xor_c / total_bits
    mean_f = (and_f + or_f + xor_f) / 3

    return {
        "label": label,
        "use_prescan": use_prescan,
        "total_bits": total_bits,
        "n_both": len(classes["both"]),
        "n_a_only": len(classes["a_only"]),
        "n_b_only": len(classes["b_only"]),
        "strong_a": len(strong_a),
        "strong_b": len(strong_b),
        "and_fidelity": round(and_f, 3),
        "or_fidelity": round(or_f, 3),
        "xor_fidelity": round(xor_f, 3),
        "mean_fidelity": round(mean_f, 3),
        "failures": failures,
    }


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def run_push(mux, census):
    log(f"\n{'═'*70}")
    log(f"  PUSH BOOLEAN COMPUTE — Find the Upper Bit-Count Limit")
    log(f"{'═'*70}")

    # ── Build frequency list ──────────────────────────────────────────
    all_freqs, census_freqs, probe_freqs = build_master_freqs(census)
    log(f"\n  Census frequencies: {len(census_freqs)}")
    log(f"  Probe frequencies: {len(probe_freqs)}")
    log(f"  Total frequencies: {len(all_freqs)}")
    log(f"  Range: {all_freqs[0]/1000:.1f}k – {all_freqs[-1]/1000:.1f}k")

    n_recv = len(ALL_RECEIVERS)
    total_meas = len(all_freqs) * n_recv
    est_time = total_meas * 0.6
    log(f"  Receivers: {n_recv} (including plate A)")
    log(f"  Total measurements: {total_meas}")
    log(f"  Estimated time: {est_time:.0f}s ({est_time/60:.1f}m)")

    # ── Hardware capture ──────────────────────────────────────────────
    log(f"\n{'━'*70}")
    log(f"  PHASE 0: Comprehensive capture")
    log(f"{'━'*70}")

    t0 = time.time()
    handle = _open_scope()
    try:
        capture = comprehensive_capture(handle, mux, all_freqs)
        _awg_off(handle)
    finally:
        _close_scope(handle)

    cap_dur = time.time() - t0
    log(f"\n  Capture: {cap_dur:.1f}s ({total_meas} measurements)")

    # ── Cross-detect new modes ────────────────────────────────────────
    log(f"\n{'━'*70}")
    log(f"  PHASE 1: Cross-detection — mining capture for new modes")
    log(f"{'━'*70}")

    new_modes = cross_detect_modes(capture, census, all_freqs)
    total_new = sum(len(v) for v in new_modes.values())
    log(f"\n  New modes discovered: {total_new}")

    # Build augmented census
    aug_census = {}
    for key in ALL_RECEIVERS:
        if key in census and census[key].get("peaks"):
            aug_census[key] = {"peaks": list(census[key]["peaks"])}
        else:
            aug_census[key] = {"peaks": []}

    for key, mode_list in new_modes.items():
        _, label = ALL_RECEIVERS[key]
        for freq, mag in mode_list:
            log(f"    {label}: NEW mode at {freq/1000:.1f}k (mag={mag/1e6:.2f}M)")
            aug_census[key]["peaks"].append({
                "freq_hz": freq,
                "magnitude": mag,
                "source": "cross_detected",
            })

    # ── Check probes for strong signals ───────────────────────────────
    log(f"\n  Probe frequency discoveries:")
    probe_hits = 0
    for freq in probe_freqs:
        readings = capture.get(freq, {})
        for key in ALL_RECEIVERS:
            mag = readings.get(key, 0)
            if mag > NEW_MODE_THRESHOLD:
                _, label = ALL_RECEIVERS[key]
                # Check not already known
                census_freqs_key = [p["freq_hz"] for p in aug_census.get(key, {}).get("peaks", [])]
                is_known = any(abs(freq - cf) / max(freq, cf) * 100 < 2.0
                              for cf in census_freqs_key)
                if not is_known:
                    log(f"    PROBE HIT: {label} @ {freq/1000:.1f}k "
                        f"(mag={mag/1e6:.2f}M)")
                    aug_census[key]["peaks"].append({
                        "freq_hz": freq,
                        "magnitude": mag,
                        "source": "probe_detected",
                    })
                    probe_hits += 1

    log(f"  Probe hits: {probe_hits}")

    # Rebuild master freq list with augmented census
    aug_freqs = set()
    for key in ALL_RECEIVERS:
        for p in aug_census.get(key, {}).get("peaks", []):
            aug_freqs.add(p["freq_hz"])
    aug_all_freqs = sorted(aug_freqs | set(all_freqs))
    log(f"  Augmented frequency count: {len(aug_all_freqs)} "
        f"(was {len(all_freqs)})")

    # ── Test all partitions ───────────────────────────────────────────
    log(f"\n{'━'*70}")
    log(f"  PHASE 2: Exhaustive partition search (no-prescan)")
    log(f"{'━'*70}")

    partitions = generate_partitions()
    log(f"  Testing {len(partitions)} partitions...")

    results = []
    for plates_a, plates_b in partitions:
        keys_a, keys_b = expand_partition(plates_a, plates_b)

        # Check all keys have census data
        missing = [k for k in keys_a + keys_b
                   if k not in aug_census or not aug_census[k].get("peaks")]
        if missing:
            continue

        label = f"{'+'.join(plates_a)} vs {'+'.join(plates_b)}"

        r = analyze_partition(capture, aug_census, aug_all_freqs,
                              keys_a, keys_b,
                              use_prescan=False, label=label)
        results.append(r)

    # Sort by bits descending, then by mean fidelity
    results.sort(key=lambda r: (-r["total_bits"], -r["mean_fidelity"]))

    # ── Summary table ─────────────────────────────────────────────────
    log(f"\n{'═'*70}")
    log(f"  RESULTS — All Partitions (no-prescan), sorted by bits")
    log(f"{'═'*70}")
    log(f"\n  {'Partition':<30s}  {'Bits':>4s}  {'Both':>4s}  "
        f"{'A':>3s}  {'B':>3s}  "
        f"{'AND':>4s}  {'OR':>4s}  {'XOR':>4s}  {'Mean':>4s}")
    log(f"  {'─'*30}  {'─'*4}  {'─'*4}  "
        f"{'─'*3}  {'─'*3}  "
        f"{'─'*4}  {'─'*4}  {'─'*4}  {'─'*4}")

    for r in results:
        bits = r["total_bits"]
        label = r["label"]
        n_b = r["n_both"]
        n_a = r["n_a_only"]
        n_bo = r["n_b_only"]
        and_p = f"{r['and_fidelity']*100:.0f}%"
        or_p = f"{r['or_fidelity']*100:.0f}%"
        xor_p = f"{r['xor_fidelity']*100:.0f}%"
        mean_p = f"{r['mean_fidelity']*100:.0f}%"

        marker = " ◄" if r["mean_fidelity"] == 1.0 and bits >= 20 else ""
        log(f"  {label:<30s}  {bits:>4d}  {n_b:>4d}  "
            f"{n_a:>3d}  {n_bo:>3d}  "
            f"{and_p:>4s}  {or_p:>4s}  {xor_p:>4s}  {mean_p:>4s}{marker}")

    # ── Best 100% result ──────────────────────────────────────────────
    perfect = [r for r in results if r["mean_fidelity"] == 1.0]
    if perfect:
        best = max(perfect, key=lambda r: r["total_bits"])
        log(f"\n  ★ BEST 100% CONFIG: {best['label']} — "
            f"{best['total_bits']} bits")
    else:
        log(f"\n  ★ No partition achieved 100% fidelity!")

    # ── Where does it break? ──────────────────────────────────────────
    log(f"\n{'━'*70}")
    log(f"  PHASE 3: Breakdown analysis — per-frequency detail for top configs")
    log(f"{'━'*70}")

    # Show top 3 by bits + failures for the first imperfect one
    shown = 0
    for r in results:
        if shown >= 3 and r["mean_fidelity"] == 1.0:
            continue
        if shown >= 5:
            break

        log(f"\n  {r['label']}  [{r['total_bits']} bits]  "
            f"Mean={r['mean_fidelity']*100:.0f}%")

        if r["failures"]:
            for fail in r["failures"]:
                log(f"    FAIL: {fail['freq']/1000:.1f}k  cat={fail['cat']}  "
                    f"det_A={fail['det_a']}(exp={fail['exp_a']})  "
                    f"det_B={fail['det_b']}(exp={fail['exp_b']})")
        else:
            log(f"    All {r['total_bits']} frequencies passed ✓")

        shown += 1

    # ── Also test with prescan for the best configs ───────────────────
    log(f"\n{'━'*70}")
    log(f"  PHASE 4: Prescan variants for top no-prescan configs")
    log(f"{'━'*70}")

    top_configs = results[:8]  # Top 8 by bits
    prescan_results = []

    for r in top_configs:
        label = r["label"]
        parts = label.split(" vs ")
        plates_a = parts[0].split("+")
        plates_b = parts[1].split("+")
        keys_a, keys_b = expand_partition(plates_a, plates_b)

        rp = analyze_partition(capture, aug_census, aug_all_freqs,
                               keys_a, keys_b,
                               use_prescan=True, label=label)
        prescan_results.append(rp)

    log(f"\n  {'Partition':<30s}  {'NoPre':>5s}  {'Pre':>4s}  "
        f"{'AND':>4s}  {'OR':>4s}  {'XOR':>4s}  {'Mean':>4s}")
    log(f"  {'─'*30}  {'─'*5}  {'─'*4}  "
        f"{'─'*4}  {'─'*4}  {'─'*4}  {'─'*4}")

    for no_pre, pre in zip(top_configs, prescan_results):
        label = no_pre["label"]
        nb = no_pre["total_bits"]
        pb = pre["total_bits"]
        and_p = f"{pre['and_fidelity']*100:.0f}%"
        or_p = f"{pre['or_fidelity']*100:.0f}%"
        xor_p = f"{pre['xor_fidelity']*100:.0f}%"
        mean_p = f"{pre['mean_fidelity']*100:.0f}%"
        log(f"  {label:<30s}  {nb:>5d}  {pb:>4d}  "
            f"{and_p:>4s}  {or_p:>4s}  {xor_p:>4s}  {mean_p:>4s}")

    # ── Save ──────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    total_dur = time.time() - t0

    capture_serial = {}
    for freq, readings in capture.items():
        capture_serial[str(freq)] = {k: round(v, 1) for k, v in readings.items()}

    experiment = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "boolean_push",
        "method": "exhaustive-partition-search",
        "census_freqs": len(census_freqs),
        "probe_freqs": len(probe_freqs),
        "total_freqs": len(all_freqs),
        "new_modes_detected": total_new,
        "probe_hits": probe_hits,
        "partitions_tested": len(results),
        "results_no_prescan": results,
        "results_prescan": prescan_results,
        "capture": capture_serial,
        "capture_duration_s": round(cap_dur, 1),
        "total_duration_s": round(total_dur, 1),
    }

    out_path = LAB_DIR / f"bool_push_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(experiment, f, indent=2, default=str)
    log(f"\n  Results saved: {out_path.name}")

    log_path = LAB_DIR / f"bool_push_{ts}.log"
    with open(log_path, "w") as f:
        f.write("\n".join(_log_lines) + "\n")
    log(f"  Log saved: {log_path.name}")

    log(f"\n  Total duration: {total_dur:.1f}s "
        f"(capture: {cap_dur:.1f}s)")
    log(f"{'═'*70}\n")

    return experiment


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Push Boolean compute — find upper bit-count limit")
    parser.add_argument("--port", required=True, help="Arduino serial port")
    parser.add_argument("--census", required=True, help="Plate census JSON")
    args = parser.parse_args()

    with open(args.census) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    available = [k for k in ALL_RECEIVERS if k in census and census[k].get("peaks")]
    missing = [k for k in ALL_RECEIVERS if k not in available]
    log(f"  Census loaded: {len(available)}/{len(ALL_RECEIVERS)} receivers")
    if missing:
        log(f"  Missing: {missing}")

    from relay_mux import RelayMux
    mux = RelayMux(port=args.port)
    mux.open()
    time.sleep(0.5)

    try:
        run_push(mux, census)
    finally:
        mux.close()


if __name__ == "__main__":
    main()
