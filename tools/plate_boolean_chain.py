#!/usr/bin/env python3
"""
Chained Plate Boolean Compute — AND/OR/XOR via Mode Superposition

Adapts the V5 pre-scan filtered self-response Boolean protocol to the
5-plate glass plate array, reading ALL plates at each frequency via
relay MUX (the "chain" approach).

Physical principle:
  Two plates' mode frequency sets serve as binary patterns A and B.
  The union A∪B is driven one frequency at a time. Each plate's
  self-response at its own enrolled modes reveals whether that mode
  is "active" (present in the drive set).

  Enrollment data = census mode frequencies (from plate_census JSON).
  This replaces the rod users.json enrollment — same principle, plates
  instead of rods.

Protocol (V5 adapted for plates):
  Phase 0 — Pre-scan:
    For each pattern plate, select its relay, drive at each census
    mode, measure self-response magnitude. Filter to strong modes
    using geometric-mean threshold of upper/lower halves.

  Phase 1 — Classify:
    Strong peaks → both / a-only / b-only (±3% freq tolerance).

  Phase 2 — Measure:
    For each frequency in union(A,B), drive AWG, cycle MUX through
    ALL plates (B, G, D, H), capture magnitude at each.

  Phase 3 — Detect:
    Per-plate threshold = 50% of weakest strong peak's self-mag.
    det_A = (freq enrolled in A) AND (mag_A > threshold_A)
    det_B = (freq enrolled in B) AND (mag_B > threshold_B)
    AND = det_A & det_B
    OR  = det_A | det_B
    XOR = det_A ^ det_B

  Phase 4 — Witness check:
    Non-pattern plates (witnesses) also have magnitudes at each freq.
    If a witness plate has an enrolled mode near a union freq, its
    response provides an independent corroboration signal.

Usage:
  DYLD_LIBRARY_PATH="..." python tools/plate_boolean_chain.py \\
      --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260417_200041.json \\
      --pattern-a 2 --pattern-b 3_NE

  Plate keys: 2=B(NE), 3_NE=G(NE), 4_NE=D(NE), 5_NE=H(NE)
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
LAB_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ─────────────────────────────────────────────────────

N_AVG = 8
N_AVG_PRESCAN = 4
SETTLE_S = 0.15
SETTLE_RELAY_S = 0.10
FREQ_MATCH_PCT = 3.0   # % tolerance for frequency matching
AWG_DRIVE_UVPP = 2_000_000

# Plate definitions: census_key → (relay_channel, label)
PLATE_MAP = {
    "2":    (2, "B-NE"),
    "3_NE": (3, "G-NE"),
    "4_NE": (5, "D-NE"),
    "5_NE": (7, "H-NE"),
}


# ── Logging ───────────────────────────────────────────────────────────

_log_lines: list[str] = []


def log(msg: str, also_print: bool = True) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    _log_lines.append(line)
    if also_print:
        print(msg)


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


def _measure_at(handle, freq_hz: float, n_avg: int = N_AVG) -> float:
    """Drive AWG at freq_hz, capture n_avg times, return mean magnitude."""
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE
    from picosdk.ps2000 import ps2000

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0)
    time.sleep(SETTLE_S)

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
            target_bin = int(round(freq_hz / bin_hz))
            lo = max(0, target_bin - 3)
            hi = min(len(fft_mag) - 1, target_bin + 3)
            magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))

    return float(np.mean(magnitudes)) if magnitudes else 0.0


def _awg_off(handle):
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)


# ── Frequency classification ─────────────────────────────────────────

def classify_frequencies(peaks_a, peaks_b, match_pct=FREQ_MATCH_PCT):
    """Classify union of two peak sets into both/a-only/b-only."""
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
    all_freqs = sorted(both + a_only + b_only)

    return {
        "both": sorted(both),
        "a_only": sorted(a_only),
        "b_only": sorted(b_only),
        "all": all_freqs,
    }


def freq_match(f1, f2, pct=FREQ_MATCH_PCT):
    """Check if two frequencies match within pct%."""
    return abs(f1 - f2) / max(f1, f2) * 100 < pct


# ══════════════════════════════════════════════════════════════════════
# Main experiment
# ══════════════════════════════════════════════════════════════════════

def run_boolean_chain(mux, census, key_a, key_b, no_prescan=False):
    """Run chained Boolean compute with V5 pre-scan protocol.

    Args:
        mux: RelayMux instance
        census: dict of census results (key → {peaks: [...]})
        key_a: census key for pattern A plate
        key_b: census key for pattern B plate
        no_prescan: if True, skip pre-scan and use all enrolled modes
    """
    # ── Load enrollment from census ───────────────────────────────────
    enrolled = {}  # census_key → [freq_hz, ...]
    for key in PLATE_MAP:
        if key in census and census[key].get("peaks"):
            enrolled[key] = [p["freq_hz"] for p in census[key]["peaks"]]

    relay_a, label_a = PLATE_MAP[key_a]
    relay_b, label_b = PLATE_MAP[key_b]

    log(f"\n{'═'*70}")
    log(f"  CHAINED PLATE BOOLEAN COMPUTE — V5 Pre-Scan + Self-Response")
    log(f"{'═'*70}")
    log(f"  Pattern A: {label_a} (key={key_a}, relay={relay_a})")
    log(f"    Enrolled modes: {len(enrolled.get(key_a, []))}")
    log(f"    Freqs: {[f'{f/1000:.1f}k' for f in enrolled.get(key_a, [])]}")
    log(f"  Pattern B: {label_b} (key={key_b}, relay={relay_b})")
    log(f"    Enrolled modes: {len(enrolled.get(key_b, []))}")
    log(f"    Freqs: {[f'{f/1000:.1f}k' for f in enrolled.get(key_b, [])]}")

    # List all chain plates
    chain_plates = []
    for key, (relay, label) in PLATE_MAP.items():
        if key in enrolled:
            chain_plates.append((key, relay, label))
    log(f"  Chain plates: {[cp[2] for cp in chain_plates]}")

    t_start = time.time()
    handle = _open_scope()

    try:
        # ── Phase 0: Pre-scan — self-response at all enrolled peaks ──
        log(f"\n{'━'*70}")
        log(f"  PHASE 0: Pre-scan — self-response filtering")
        log(f"{'━'*70}")

        strong_peaks = {}  # key → [freq_hz, ...]
        prescan_mags = {}  # key → {freq: magnitude}

        if no_prescan:
            log(f"\n  --no-prescan: using ALL enrolled modes")
            for key in [key_a, key_b]:
                peaks = enrolled.get(key, [])
                strong_peaks[key] = list(peaks)
                prescan_mags[key] = {}
                _, label = PLATE_MAP[key]
                log(f"    {label}: {len(peaks)} modes (all kept)")
        else:
            for key in [key_a, key_b]:
                relay, label = PLATE_MAP[key]
                peaks = enrolled.get(key, [])
                if not peaks:
                    log(f"  WARNING: {label} has no enrolled modes, skipping")
                    strong_peaks[key] = []
                    prescan_mags[key] = {}
                    continue

                mux.select(relay)
                time.sleep(SETTLE_RELAY_S)

                scan_results = []
                log(f"\n  Pre-scan {label} — {len(peaks)} enrolled modes:")
                for i, freq in enumerate(peaks):
                    mag = _measure_at(handle, freq, n_avg=N_AVG_PRESCAN)
                    scan_results.append((freq, mag))
                    log(f"    f{i+1:2d}={freq/1000:7.2f} kHz  mag={mag:12.0f}",
                        also_print=True)

                # Adaptive threshold: geometric mean of median halves
                mags_sorted = sorted([m for _, m in scan_results])
                mid = len(mags_sorted) // 2
                if mid == 0:
                    mid = 1
                med_strong = float(np.median(mags_sorted[mid:]))
                med_weak = float(np.median(mags_sorted[:mid]))
                if med_weak > 0:
                    thresh = math.sqrt(med_strong * med_weak)
                else:
                    thresh = med_strong * 0.1

                strong = [(f, m) for f, m in scan_results if m > thresh]
                weak = [(f, m) for f, m in scan_results if m <= thresh]
                strong_peaks[key] = [f for f, m in strong]
                prescan_mags[key] = {f: m for f, m in scan_results}

                log(f"    Threshold: {thresh:.0f}")
                log(f"    Strong: {len(strong)}/{len(scan_results)}  "
                    f"Weak: {len(weak)}/{len(scan_results)}")
                log(f"    Strong freqs: {[f'{f/1000:.1f}k' for f in strong_peaks[key]]}")

            mux.off()

        # ── Phase 1: Classify strong peaks ────────────────────────────
        log(f"\n{'━'*70}")
        log(f"  PHASE 1: Frequency classification")
        log(f"{'━'*70}")

        peaks_a = strong_peaks[key_a]
        peaks_b = strong_peaks[key_b]
        classes = classify_frequencies(peaks_a, peaks_b)
        all_freqs = classes["all"]

        log(f"  A strong: {len(peaks_a)} modes")
        log(f"  B strong: {len(peaks_b)} modes")
        log(f"  Both A∩B:  {len(classes['both'])} — "
            f"{[f'{f/1000:.1f}k' for f in classes['both']]}")
        log(f"  A only:    {len(classes['a_only'])} — "
            f"{[f'{f/1000:.1f}k' for f in classes['a_only']]}")
        log(f"  B only:    {len(classes['b_only'])} — "
            f"{[f'{f/1000:.1f}k' for f in classes['b_only']]}")
        log(f"  Union:     {len(all_freqs)} frequencies")

        if not all_freqs:
            log("  ERROR: No frequencies to test")
            _close_scope(handle)
            return None

        # ── Phase 2: Measure every frequency on ALL plates (chain) ────
        log(f"\n{'━'*70}")
        log(f"  PHASE 2: Chain measurement — all plates at each frequency")
        log(f"{'━'*70}")

        raw_mags = []  # list of {key: magnitude} per frequency

        for fi, freq in enumerate(all_freqs):
            plate_mags = {}
            for key, relay, label in chain_plates:
                mux.select(relay)
                time.sleep(SETTLE_RELAY_S)
                mag = _measure_at(handle, freq, n_avg=N_AVG)
                plate_mags[key] = mag

            raw_mags.append(plate_mags)

            # Print progress
            mag_str = "  ".join(
                f"{lbl}={plate_mags[k]:9.0f}"
                for k, _, lbl in chain_plates
            )
            log(f"  f{fi+1:2d} {freq/1000:7.2f} kHz  {mag_str}")

        _awg_off(handle)
        mux.off()

    finally:
        _close_scope(handle)

    duration = time.time() - t_start

    # ── Phase 3: Per-plate threshold detection ────────────────────────
    log(f"\n{'━'*70}")
    log(f"  PHASE 3: Boolean extraction — per-plate self-response")
    log(f"{'━'*70}")

    # Thresholds: 50% of weakest strong peak's self-response magnitude
    rod_thresholds = {}
    for key in [key_a, key_b]:
        min_self_mag = float('inf')
        for fi, freq in enumerate(all_freqs):
            is_enrolled = any(freq_match(freq, ep) for ep in strong_peaks[key])
            if is_enrolled:
                min_self_mag = min(min_self_mag, raw_mags[fi][key])

        if min_self_mag == float('inf'):
            min_self_mag = 100000
        rod_thresholds[key] = min_self_mag * 0.5
        _, label = PLATE_MAP[key]
        log(f"  {label}: weakest strong self-mag={min_self_mag:.0f}  "
            f"threshold={rod_thresholds[key]:.0f}")

    # Build frequency category map
    freq_cat = {}
    for f in classes["both"]:
        freq_cat[round(f, 1)] = "both"
    for f in classes["a_only"]:
        freq_cat[round(f, 1)] = "a_only"
    for f in classes["b_only"]:
        freq_cat[round(f, 1)] = "b_only"

    # Print header
    log(f"\n  {'Freq':>8s}  {'Cat':>7s}  "
        f"{'mag_A':>10s}  {'mag_B':>10s}  "
        f"{'det_A':>5s}  {'det_B':>5s}  "
        f"{'AND':>4s}  {'OR':>3s}  {'XOR':>4s}  {'ok':>3s}")
    log(f"  {'─'*8}  {'─'*7}  "
        f"{'─'*10}  {'─'*10}  "
        f"{'─'*5}  {'─'*5}  "
        f"{'─'*4}  {'─'*3}  {'─'*4}  {'─'*3}")

    and_correct = 0
    or_correct = 0
    xor_correct = 0
    total_bits = 0
    results_per_freq = []

    for fi, freq in enumerate(all_freqs):
        mags = raw_mags[fi]
        mag_a = mags[key_a]
        mag_b = mags[key_b]

        # Use the CLASSIFICATION result for enrollment, not re-matching.
        # This prevents 28.82k (a-only) from matching G's 29.25k mode
        # when the classifier already assigned 29.23k as the "both" freq.
        cat = freq_cat.get(round(freq, 1), "?")
        a_enrolled = cat in ("both", "a_only")
        b_enrolled = cat in ("both", "b_only")

        # Per-plate self-response detection
        det_a = 1 if (a_enrolled and mag_a > rod_thresholds[key_a]) else 0
        det_b = 1 if (b_enrolled and mag_b > rod_thresholds[key_b]) else 0

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

        # Witness magnitudes
        witness_mags = {}
        for wk, _, wl in chain_plates:
            if wk not in (key_a, key_b):
                witness_mags[wl] = mags[wk]

        cat_label = cat.replace("_", "-")
        log(f"  {freq/1000:7.2f}k  {cat_label:>7s}  "
            f"{mag_a:10.0f}  {mag_b:10.0f}  "
            f"{'  ✓' if det_a == in_a else '  ✗':>5s}  "
            f"{'  ✓' if det_b == in_b else '  ✗':>5s}  "
            f"{'✓' if and_ok else '✗':>4s}  "
            f"{'✓' if or_ok else '✗':>3s}  "
            f"{'✓' if xor_ok else '✗':>4s}  "
            f"{'✓' if all_ok else '✗':>3s}")

        results_per_freq.append({
            "freq_hz": round(freq, 1),
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
            "witness_mags": {k: round(v, 1) for k, v in witness_mags.items()},
        })

    and_fidelity = and_correct / total_bits if total_bits > 0 else 0
    or_fidelity = or_correct / total_bits if total_bits > 0 else 0
    xor_fidelity = xor_correct / total_bits if total_bits > 0 else 0
    mean_fidelity = (and_fidelity + or_fidelity + xor_fidelity) / 3

    log(f"\n{'━'*70}")
    log(f"  RESULTS — Chained Plate Boolean Compute")
    log(f"{'━'*70}")
    log(f"  AND fidelity: {and_correct}/{total_bits} ({and_fidelity*100:.0f}%)")
    log(f"  OR  fidelity: {or_correct}/{total_bits} ({or_fidelity*100:.0f}%)")
    log(f"  XOR fidelity: {xor_correct}/{total_bits} ({xor_fidelity*100:.0f}%)")
    log(f"  Mean fidelity: {mean_fidelity*100:.0f}%")
    log(f"  Duration: {duration:.1f}s")

    # ── Phase 4: Witness analysis ─────────────────────────────────────
    log(f"\n{'━'*70}")
    log(f"  PHASE 4: Witness plate analysis")
    log(f"{'━'*70}")

    witness_keys = [k for k, _, _ in chain_plates if k not in (key_a, key_b)]
    for wk in witness_keys:
        _, wlabel = PLATE_MAP[wk]
        w_enrolled = enrolled.get(wk, [])

        hits = 0
        checks = 0
        for fi, freq in enumerate(all_freqs):
            w_has_mode = any(freq_match(freq, ep) for ep in w_enrolled)
            if w_has_mode:
                checks += 1
                cat = freq_cat.get(round(freq, 1), "?")
                in_a = cat in ("both", "a_only")
                in_b = cat in ("both", "b_only")
                w_mag = raw_mags[fi][wk]

                # Witness "sees" the frequency because it has its own
                # mode nearby — independent confirmation
                log(f"    {wlabel} @ {freq/1000:.1f}k: mag={w_mag:.0f}  "
                    f"cat={cat}  in_A={in_a}  in_B={in_b}")
                hits += 1

        if checks > 0:
            log(f"    {wlabel}: {hits} enrolled modes overlap with "
                f"union A∪B ({checks} checked)")
        else:
            log(f"    {wlabel}: no enrolled modes overlap with union A∪B")

    # ── Save ──────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = LAB_DIR / f"bool_chain_{ts}.json"

    experiment = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "boolean_chain",
        "method": "v5-prescan-filtered-self-response",
        "pattern_a": {"key": key_a, "label": label_a, "relay": relay_a},
        "pattern_b": {"key": key_b, "label": label_b, "relay": relay_b},
        "chain_plates": [
            {"key": k, "label": l, "relay": r} for k, r, l in chain_plates
        ],
        "enrolled_a": [round(f, 1) for f in enrolled.get(key_a, [])],
        "enrolled_b": [round(f, 1) for f in enrolled.get(key_b, [])],
        "strong_a": [round(f, 1) for f in strong_peaks.get(key_a, [])],
        "strong_b": [round(f, 1) for f in strong_peaks.get(key_b, [])],
        "classes": {k: [round(f, 1) for f in v] for k, v in classes.items()},
        "thresholds": {k: round(v, 1) for k, v in rod_thresholds.items()},
        "results_per_freq": results_per_freq,
        "analysis": {
            "and_fidelity": round(and_fidelity, 3),
            "or_fidelity": round(or_fidelity, 3),
            "xor_fidelity": round(xor_fidelity, 3),
            "mean_fidelity": round(mean_fidelity, 3),
            "total_bits": total_bits,
            "and_correct": and_correct,
            "or_correct": or_correct,
            "xor_correct": xor_correct,
        },
        "duration_s": round(duration, 1),
    }

    with open(out_path, "w") as f:
        json.dump(experiment, f, indent=2)
    log(f"\n  Results saved: {out_path.name}")

    # Save log
    log_path = LAB_DIR / f"bool_chain_{ts}.log"
    with open(log_path, "w") as f:
        f.write("\n".join(_log_lines) + "\n")
    log(f"  Log saved: {log_path.name}")
    log(f"{'═'*70}\n")

    return experiment


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Chained plate Boolean compute — AND/OR/XOR via V5 protocol")
    parser.add_argument("--port", required=True, help="Arduino serial port")
    parser.add_argument("--census", required=True, help="Plate census JSON")
    parser.add_argument("--pattern-a", default="2",
                        help="Census key for pattern A (default: 2=Plate B)")
    parser.add_argument("--pattern-b", default="3_NE",
                        help="Census key for pattern B (default: 3_NE=Plate G)")
    parser.add_argument("--no-prescan", action="store_true",
                        help="Skip pre-scan filtering, use all enrolled modes")
    args = parser.parse_args()

    # Validate plate keys
    if args.pattern_a not in PLATE_MAP:
        print(f"  ERROR: Unknown plate key '{args.pattern_a}'")
        print(f"  Valid keys: {list(PLATE_MAP.keys())}")
        sys.exit(1)
    if args.pattern_b not in PLATE_MAP:
        print(f"  ERROR: Unknown plate key '{args.pattern_b}'")
        print(f"  Valid keys: {list(PLATE_MAP.keys())}")
        sys.exit(1)

    # Load census
    with open(args.census) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    from relay_mux import RelayMux
    mux = RelayMux(port=args.port)
    mux.open()
    time.sleep(0.5)

    try:
        run_boolean_chain(mux, census, args.pattern_a, args.pattern_b,
                          no_prescan=args.no_prescan)
    finally:
        mux.close()


if __name__ == "__main__":
    main()
