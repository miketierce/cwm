#!/usr/bin/env python3
"""
Progressive Boolean Sweep — find the bit-count limit of plate Boolean compute.

Performs a single comprehensive hardware capture across all 7 receivers
(B-NE, G-NE, G-NW, D-NE, D-NW, H-NE, H-NW), then analyzes progressively
larger pattern configurations offline to find where Boolean fidelity degrades.

Each step is tested both with and without V5 prescan filtering.

Sweep steps:
  1. B vs G (NE only)              — baseline 7-bit
  2. D_NE vs G_NE                  — proven 8-bit
  3. D(NE+NW) vs G(NE+NW)         — add NW receivers
  4. D+H(NE) vs G+B               — multi-plate, NE only
  5. D(all)+H(NE) vs G(all)+B     — add D,G NW
  6. D(all)+H(all) vs G(all)+B    — max config

Usage:
  DYLD_LIBRARY_PATH="..." python tools/plate_boolean_sweep.py \\
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
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
LAB_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ─────────────────────────────────────────────────────

N_AVG = 8
SETTLE_S = 0.15       # AWG settle
SETTLE_RELAY = 0.10   # relay settle
FREQ_MATCH_PCT = 3.0  # cross-pattern classification tolerance
INTRA_DEDUP_PCT = 1.0 # intra-pattern mode dedup tolerance
AWG_DRIVE_UVPP = 2_000_000

# All 7 receivers (plate A excluded — no dual-RX, not used as pattern)
ALL_RECEIVERS = {
    "2":    (2, "B-NE"),
    "3_NE": (3, "G-NE"),
    "3_NW": (4, "G-NW"),
    "4_NE": (5, "D-NE"),
    "4_NW": (6, "D-NW"),
    "5_NE": (7, "H-NE"),
    "5_NW": (8, "H-NW"),
}

# Progressive sweep configurations
SWEEP_STEPS = [
    {"name": "B vs G (NE)",
     "keys_a": ["2"],                              "keys_b": ["3_NE"]},
    {"name": "D_NE vs G_NE",
     "keys_a": ["4_NE"],                           "keys_b": ["3_NE"]},
    {"name": "D(NE+NW) vs G(NE+NW)",
     "keys_a": ["4_NE", "4_NW"],                   "keys_b": ["3_NE", "3_NW"]},
    {"name": "D+H(NE) vs G+B",
     "keys_a": ["4_NE", "5_NE"],                   "keys_b": ["3_NE", "2"]},
    {"name": "D(all)+H(NE) vs G(all)+B",
     "keys_a": ["4_NE", "4_NW", "5_NE"],           "keys_b": ["3_NE", "3_NW", "2"]},
    {"name": "D(all)+H(all) vs G(all)+B",
     "keys_a": ["4_NE", "4_NW", "5_NE", "5_NW"],  "keys_b": ["3_NE", "3_NW", "2"]},
]


# ── Logging ───────────────────────────────────────────────────────────

_log_lines: list[str] = []


def log(msg: str = "", also_print: bool = True) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    _log_lines.append(line)
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
    """Capture n_avg block acquisitions, return mean FFT magnitude at drive freq."""
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
    """Find nearest frequency in a list."""
    return min(freqs, key=lambda f: abs(f - target))


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
    return {
        "both": sorted(both),
        "a_only": sorted(a_only),
        "b_only": sorted(b_only),
        "all": sorted(both + a_only + b_only),
    }


def merge_strong(census, keys, strong_per_key, dedup_pct=INTRA_DEDUP_PCT):
    """Merge strong modes from multiple census keys, dedup within tolerance.

    Returns: list of (freq_hz, frozenset_of_source_keys), sorted by freq.
    """
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


# ── Comprehensive capture ─────────────────────────────────────────────

def build_master_freqs(census):
    """Collect all unique frequencies from census for our receivers."""
    raw = set()
    for key in ALL_RECEIVERS:
        if key in census and census[key].get("peaks"):
            for p in census[key]["peaks"]:
                raw.add(p["freq_hz"])
    return sorted(raw)


def comprehensive_capture(handle, mux, master_freqs):
    """Capture all master frequencies across all 7 receivers.

    Optimized: AWG set once per freq, then cycle receivers.
    Returns: {freq: {key: magnitude}}
    """
    receivers = [(k, r, l) for k, (r, l) in ALL_RECEIVERS.items()]
    capture = {}
    total = len(master_freqs) * len(receivers)
    done = 0

    for fi, freq in enumerate(master_freqs):
        _set_awg(handle, freq)
        time.sleep(SETTLE_S)

        capture[freq] = {}
        for key, relay, label in receivers:
            mux.select(relay)
            time.sleep(SETTLE_RELAY)
            mag = _capture_mag(handle, freq)
            capture[freq][key] = mag
            done += 1

        if (fi + 1) % 5 == 0 or fi == len(master_freqs) - 1:
            log(f"    {fi+1}/{len(master_freqs)} freqs  "
                f"({done}/{total} meas)  "
                f"last={freq/1000:.1f}k")

    mux.off()
    return capture


# ── Analysis ──────────────────────────────────────────────────────────

def analyze_step(capture, census, master_freqs, keys_a, keys_b,
                 use_prescan=True, step_name=""):
    """Analyze one sweep configuration from pre-captured data.

    Returns dict with fidelity metrics and per-frequency results.
    """
    all_keys = keys_a + keys_b
    prescan_tag = "prescan" if use_prescan else "no-prescan"

    # 1. Collect enrolled modes per key
    enrolled = {}
    for key in all_keys:
        if key in census and census[key].get("peaks"):
            enrolled[key] = [p["freq_hz"] for p in census[key]["peaks"]]
        else:
            enrolled[key] = []

    # 2. Per-key prescan filtering
    strong_per_key = {}
    key_prescan_info = {}  # key → (n_enrolled, n_strong, threshold)

    for key in all_keys:
        peaks = enrolled[key]
        if not peaks:
            strong_per_key[key] = []
            key_prescan_info[key] = (0, 0, 0)
            continue

        # Self-response from capture: drive at mode freq, read own relay
        scan = []
        for freq in peaks:
            nf = nearest_freq(freq, master_freqs)
            mag = capture.get(nf, {}).get(key, 0)
            scan.append((freq, mag))

        if not use_prescan or len(scan) <= 2:
            strong_per_key[key] = list(peaks)
            key_prescan_info[key] = (len(peaks), len(peaks), 0)
        else:
            mags_sorted = sorted([m for _, m in scan])
            mid = max(1, len(mags_sorted) // 2)
            med_strong = float(np.median(mags_sorted[mid:]))
            med_weak = float(np.median(mags_sorted[:mid]))
            thresh = math.sqrt(med_strong * med_weak) if med_weak > 0 else med_strong * 0.1

            strong_per_key[key] = [f for f, m in scan if m > thresh]
            key_prescan_info[key] = (len(peaks), len(strong_per_key[key]), thresh)

    # 3. Merge strong modes within each pattern (dedup at 1%)
    strong_a = merge_strong(census, keys_a, strong_per_key)
    strong_b = merge_strong(census, keys_b, strong_per_key)

    # 4. Classify: both / a-only / b-only
    freqs_a = [f for f, _ in strong_a]
    freqs_b = [f for f, _ in strong_b]
    classes = classify_frequencies(freqs_a, freqs_b)
    all_freqs = classes["all"]

    # Print step header
    log(f"\n  {'─'*66}")
    log(f"  {step_name}  [{prescan_tag}]")
    log(f"  {'─'*66}")

    # Per-key enrollment summary
    for side, keys in [("A", keys_a), ("B", keys_b)]:
        parts = []
        for key in keys:
            n_enr, n_str, _ = key_prescan_info[key]
            _, label = ALL_RECEIVERS[key]
            parts.append(f"{label}({n_enr}→{n_str})")
        merged_n = len(strong_a) if side == "A" else len(strong_b)
        log(f"    {side}: {', '.join(parts)} → {merged_n} merged strong")

    log(f"    Union: {len(all_freqs)} bits  "
        f"({len(classes['both'])} both, "
        f"{len(classes['a_only'])} a-only, "
        f"{len(classes['b_only'])} b-only)")

    if not all_freqs:
        log("    ERROR: No frequencies to test")
        return {"mean_fidelity": 0, "total_bits": 0,
                "and_fidelity": 0, "or_fidelity": 0, "xor_fidelity": 0}

    # 5. Build category map
    freq_cat = {}
    for f in classes["both"]:
        freq_cat[round(f, 1)] = "both"
    for f in classes["a_only"]:
        freq_cat[round(f, 1)] = "a_only"
    for f in classes["b_only"]:
        freq_cat[round(f, 1)] = "b_only"

    # Helper: find source keys for a classified frequency within a pattern
    def find_sources(freq, strong_modes):
        for sf, sources in strong_modes:
            if freq_match(freq, sf):
                return sources
        return frozenset()

    # 6. Per-key detection thresholds (50% of weakest strong mode self-response)
    key_thresholds = {}
    for key in all_keys:
        strong = strong_a if key in keys_a else strong_b
        self_mags = []
        for sf, sources in strong:
            if key in sources:
                nf = nearest_freq(sf, master_freqs)
                self_mags.append(capture.get(nf, {}).get(key, 0))
        if self_mags:
            key_thresholds[key] = min(self_mags) * 0.5
        else:
            key_thresholds[key] = float('inf')

    thresh_parts = [f"{ALL_RECEIVERS[k][1]}={v/1e6:.2f}M"
                    for k, v in key_thresholds.items() if v < float('inf')]
    log(f"    Thresholds: {', '.join(thresh_parts)}")

    # 7. Per-frequency table header
    log(f"\n    {'Freq':>8s}  {'Cat':>7s}  "
        f"{'mag_A':>10s}  {'mag_B':>10s}  "
        f"{'dA':>2s} {'dB':>2s}  "
        f"{'AND':>3s} {'OR':>2s} {'XOR':>3s} {'ok':>2s}")
    log(f"    {'─'*8}  {'─'*7}  "
        f"{'─'*10}  {'─'*10}  "
        f"{'─'*2} {'─'*2}  "
        f"{'─'*3} {'─'*2} {'─'*3} {'─'*2}")

    # 8. Detection and Boolean scoring
    and_c = or_c = xor_c = 0
    total_bits = len(all_freqs)
    per_freq = []

    for freq in all_freqs:
        cat = freq_cat.get(round(freq, 1), "?")
        a_enrolled = cat in ("both", "a_only")
        b_enrolled = cat in ("both", "b_only")

        nf = nearest_freq(freq, master_freqs)

        # Pattern A detection: any contributing key exceeds its threshold
        det_a = False
        mag_a_best = 0
        if a_enrolled:
            sources = find_sources(freq, strong_a)
            for key in sources:
                mag = capture.get(nf, {}).get(key, 0)
                mag_a_best = max(mag_a_best, mag)
                if mag > key_thresholds.get(key, float('inf')):
                    det_a = True

        # Pattern B detection
        det_b = False
        mag_b_best = 0
        if b_enrolled:
            sources = find_sources(freq, strong_b)
            for key in sources:
                mag = capture.get(nf, {}).get(key, 0)
                mag_b_best = max(mag_b_best, mag)
                if mag > key_thresholds.get(key, float('inf')):
                    det_b = True

        # Computed Boolean
        and_got = det_a and det_b
        or_got = det_a or det_b
        xor_got = det_a != det_b

        # Ground truth
        and_exp = a_enrolled and b_enrolled
        or_exp = a_enrolled or b_enrolled
        xor_exp = a_enrolled != b_enrolled

        and_ok = and_exp == and_got
        or_ok = or_exp == or_got
        xor_ok = xor_exp == xor_got
        all_ok = and_ok and or_ok and xor_ok

        if and_ok: and_c += 1
        if or_ok: or_c += 1
        if xor_ok: xor_c += 1

        cat_label = cat.replace("_", "-")
        da_sym = "✓" if (det_a == a_enrolled) else "✗"
        db_sym = "✓" if (det_b == b_enrolled) else "✗"
        log(f"    {freq/1000:7.2f}k  {cat_label:>7s}  "
            f"{mag_a_best:10.0f}  {mag_b_best:10.0f}  "
            f"{da_sym:>2s} {db_sym:>2s}  "
            f"{'✓' if and_ok else '✗':>3s} "
            f"{'✓' if or_ok else '✗':>2s} "
            f"{'✓' if xor_ok else '✗':>3s} "
            f"{'✓' if all_ok else '✗':>2s}")

        per_freq.append({
            "freq_hz": round(freq, 1),
            "category": cat,
            "mag_a": round(mag_a_best, 1),
            "mag_b": round(mag_b_best, 1),
            "det_a": det_a, "det_b": det_b,
            "and_ok": and_ok, "or_ok": or_ok, "xor_ok": xor_ok,
        })

    and_fid = and_c / total_bits
    or_fid = or_c / total_bits
    xor_fid = xor_c / total_bits
    mean_fid = (and_fid + or_fid + xor_fid) / 3

    log(f"\n    AND: {and_c}/{total_bits} ({and_fid*100:.0f}%)  "
        f"OR: {or_c}/{total_bits} ({or_fid*100:.0f}%)  "
        f"XOR: {xor_c}/{total_bits} ({xor_fid*100:.0f}%)  "
        f"Mean: {mean_fid*100:.0f}%")

    return {
        "step_name": step_name,
        "use_prescan": use_prescan,
        "keys_a": keys_a,
        "keys_b": keys_b,
        "prescan_info": {k: {"enrolled": e, "strong": s, "thresh": round(t, 1)}
                         for k, (e, s, t) in key_prescan_info.items()},
        "strong_a_count": len(strong_a),
        "strong_b_count": len(strong_b),
        "classes": {k: [round(f, 1) for f in v] for k, v in classes.items()},
        "total_bits": total_bits,
        "and_correct": and_c, "or_correct": or_c, "xor_correct": xor_c,
        "and_fidelity": round(and_fid, 3),
        "or_fidelity": round(or_fid, 3),
        "xor_fidelity": round(xor_fid, 3),
        "mean_fidelity": round(mean_fid, 3),
        "thresholds": {k: round(v, 1) for k, v in key_thresholds.items()
                       if v < float('inf')},
        "per_freq": per_freq,
    }


# ══════════════════════════════════════════════════════════════════════
# Sweep runner
# ══════════════════════════════════════════════════════════════════════

def run_sweep(mux, census):
    """Run comprehensive capture + progressive analysis."""

    log(f"\n{'═'*70}")
    log(f"  PROGRESSIVE BOOLEAN SWEEP — Find the Bit-Count Limit")
    log(f"{'═'*70}")

    # Build master frequency list
    master_freqs = build_master_freqs(census)
    log(f"\n  Master frequency list: {len(master_freqs)} unique frequencies")
    log(f"  Range: {master_freqs[0]/1000:.1f}k – {master_freqs[-1]/1000:.1f}k")
    n_recv = len(ALL_RECEIVERS)
    total_meas = len(master_freqs) * n_recv
    est_time = len(master_freqs) * (SETTLE_S + n_recv * (SETTLE_RELAY + 0.12))
    log(f"  Receivers: {n_recv}")
    log(f"  Total measurements: {total_meas}")
    log(f"  Estimated capture time: {est_time:.0f}s")

    # ── Hardware capture ──────────────────────────────────────────────
    log(f"\n{'━'*70}")
    log(f"  PHASE 0: Comprehensive capture — all freqs × all receivers")
    log(f"{'━'*70}")

    t0 = time.time()
    handle = _open_scope()
    try:
        capture = comprehensive_capture(handle, mux, master_freqs)
        _awg_off(handle)
    finally:
        _close_scope(handle)

    capture_duration = time.time() - t0
    log(f"\n  Capture complete: {capture_duration:.1f}s "
        f"({total_meas} measurements)")

    # ── Progressive analysis ──────────────────────────────────────────
    log(f"\n{'━'*70}")
    log(f"  PHASE 1: Progressive analysis — {len(SWEEP_STEPS)} steps × 2 variants")
    log(f"{'━'*70}")

    all_results = []

    for si, step in enumerate(SWEEP_STEPS, 1):
        name = f"Step {si}: {step['name']}"

        # Validate keys exist in census
        missing = [k for k in step["keys_a"] + step["keys_b"]
                   if k not in census or not census[k].get("peaks")]
        if missing:
            log(f"\n  {name}: SKIP — missing census keys {missing}")
            continue

        # Run with prescan
        r_pre = analyze_step(capture, census, master_freqs,
                             step["keys_a"], step["keys_b"],
                             use_prescan=True, step_name=name)
        all_results.append(r_pre)

        # Run without prescan
        r_no = analyze_step(capture, census, master_freqs,
                            step["keys_a"], step["keys_b"],
                            use_prescan=False, step_name=name)
        all_results.append(r_no)

    # ── Summary table ─────────────────────────────────────────────────
    log(f"\n{'═'*70}")
    log(f"  SUMMARY — Progressive Boolean Sweep")
    log(f"{'═'*70}")
    log(f"\n  {'Step':>4s}  {'Config':<28s}  {'Prescan':>7s}  "
        f"{'Bits':>4s}  {'AND':>4s}  {'OR':>4s}  {'XOR':>4s}  {'Mean':>4s}")
    log(f"  {'─'*4}  {'─'*28}  {'─'*7}  "
        f"{'─'*4}  {'─'*4}  {'─'*4}  {'─'*4}  {'─'*4}")

    for r in all_results:
        sname = r.get("step_name", "?")
        # Extract step number
        step_num = sname.split(":")[0].replace("Step ", "").strip() if ":" in sname else "?"
        config = sname.split(": ", 1)[1] if ": " in sname else sname
        pre = "yes" if r["use_prescan"] else "no"
        bits = r["total_bits"]
        and_pct = f"{r['and_fidelity']*100:.0f}%"
        or_pct = f"{r['or_fidelity']*100:.0f}%"
        xor_pct = f"{r['xor_fidelity']*100:.0f}%"
        mean_pct = f"{r['mean_fidelity']*100:.0f}%"

        log(f"  {step_num:>4s}  {config:<28s}  {pre:>7s}  "
            f"{bits:>4d}  {and_pct:>4s}  {or_pct:>4s}  {xor_pct:>4s}  {mean_pct:>4s}")

    log(f"\n  Total duration: {time.time() - t0:.1f}s "
        f"(capture: {capture_duration:.1f}s)")

    # ── Save results ──────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Serialize capture data (convert float keys to strings for JSON)
    capture_serial = {}
    for freq, readings in capture.items():
        capture_serial[str(freq)] = {k: round(v, 1) for k, v in readings.items()}

    experiment = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "boolean_sweep",
        "method": "v5-progressive-sweep",
        "master_freqs": [round(f, 1) for f in master_freqs],
        "receivers": {k: {"relay": r, "label": l}
                      for k, (r, l) in ALL_RECEIVERS.items()},
        "sweep_steps": SWEEP_STEPS,
        "results": all_results,
        "capture": capture_serial,
        "capture_duration_s": round(capture_duration, 1),
        "total_duration_s": round(time.time() - t0, 1),
    }

    out_path = LAB_DIR / f"bool_sweep_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(experiment, f, indent=2)
    log(f"\n  Results saved: {out_path.name}")

    log_path = LAB_DIR / f"bool_sweep_{ts}.log"
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
        description="Progressive Boolean sweep — find bit-count limit")
    parser.add_argument("--port", required=True, help="Arduino serial port")
    parser.add_argument("--census", required=True, help="Plate census JSON")
    args = parser.parse_args()

    with open(args.census) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    # Validate census has our receiver keys
    available = [k for k in ALL_RECEIVERS if k in census and census[k].get("peaks")]
    missing = [k for k in ALL_RECEIVERS if k not in available]
    if missing:
        log(f"  WARNING: Census missing receiver keys: {missing}")
    log(f"  Census loaded: {len(available)}/{len(ALL_RECEIVERS)} receivers available")

    from relay_mux import RelayMux
    mux = RelayMux(port=args.port)
    mux.open()
    time.sleep(0.5)

    try:
        run_sweep(mux, census)
    finally:
        mux.close()


if __name__ == "__main__":
    main()
