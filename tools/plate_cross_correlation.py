#!/usr/bin/env python3
"""
Plate E16: Cross-Correlation Matrix — Fused Silica Plates

Rod result: max |ρ| = 0.79 (FAIL — paper claims ≤ 0.21)
Plates have Q 7,687–30,830 (10–60× rods) → sharper peaks → lower cross-correlation.

Builds 5×5 Pearson correlation matrix from enrolled fingerprints.
Tests self-response (query plate i, sense plate i) and full-response
(query plate i, sense ALL plates) correlation matrices.

Signal chain:
  AWG OUT → Drive PZT (all plates share AWG via parallel wiring)
  Relay N → Sense PZT Plate N → PicoScope Ch A

Usage:
  PYTHONPATH=. python tools/plate_cross_correlation.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_cross_correlation.py --dry-run
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

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_FILE = LAB_DIR / f"cross_correlation_{TIMESTAMP}.json"


# ── Scope helpers ─────────────────────────────────────────────────────

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    print("  PicoScope opened (Ch A ±1V DC)")
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
    print("  PicoScope closed")


def _measure_at(handle, freq_hz: float) -> dict:
    """Drive AWG at freq_hz, capture N_AVG-averaged magnitude."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
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

def _load_enrollment() -> tuple[dict, list]:
    """Load plate enrollment from latest census file.
    Returns (enrolled_freqs_by_plate, plate_ids)."""
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
    for pid in PLATE_IDS:
        if pid in census and census[pid].get("peaks"):
            peaks = census[pid]["peaks"][:N_PEAKS]
            enrolled[pid] = [p["freq_hz"] for p in peaks]

    plate_ids = sorted(enrolled.keys())
    print(f"  Loaded enrollment: {len(plate_ids)} plates, ≤{N_PEAKS} peaks each")
    return enrolled, plate_ids


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Plate E16: Cross-Correlation Matrix")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit", action="store_true", help="Submit to Firestore")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  EXPERIMENT E16 (Plates): Cross-Correlation Matrix")
    print("=" * 70)

    enrolled, plate_ids = _load_enrollment()

    if args.dry_run:
        print("\n  [DRY RUN] Would measure cross-correlation on "
              f"{len(plate_ids)} plates")
        return

    handle = _open_scope()
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {args.port}")

    t_start = time.time()

    # ── Collect all unique frequencies across all plates ──────────────
    all_freqs = set()
    for pid in plate_ids:
        all_freqs.update(enrolled[pid])
    all_freqs = sorted(all_freqs)
    print(f"\n  Total unique frequencies across all plates: {len(all_freqs)}")

    # ── Measure each plate's response at ALL frequencies ─────────────
    # peak_log[sense_plate][freq] = magnitude
    peak_log: dict[str, dict[float, float]] = {}

    for pid in plate_ids:
        print(f"\n  Measuring Plate {PLATE_NAMES[pid]} (relay {pid}) "
              f"at {len(all_freqs)} frequencies...")
        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        peak_log[pid] = {}
        for freq in all_freqs:
            m = _measure_at(handle, freq)
            peak_log[pid][freq] = m["magnitude"]

        own_freqs = enrolled[pid]
        own_mags = [peak_log[pid][f] for f in own_freqs]
        print(f"    Own-peak mean mag: {np.mean(own_mags):.0f}")

    # ── Build self-response fingerprints (own peaks only) ────────────
    print("\n  --- Self-Response Correlation (own peaks) ---")
    self_fingerprints = {}
    for pid in plate_ids:
        fp = [peak_log[pid][f] for f in enrolled[pid]]
        self_fingerprints[pid] = np.array(fp, dtype=np.float64)

    self_corr: dict[str, dict[str, float]] = {}
    for pi in plate_ids:
        self_corr[pi] = {}
        for pj in plate_ids:
            # Use pi's enrolled frequencies measured on both plates
            vi = np.array([peak_log[pi][f] for f in enrolled[pi]], dtype=np.float64)
            vj = np.array([peak_log[pj][f] for f in enrolled[pi]], dtype=np.float64)
            if np.std(vi) > 0 and np.std(vj) > 0:
                r = float(np.corrcoef(vi, vj)[0, 1])
            else:
                r = 0.0
            self_corr[pi][pj] = round(r, 4)

    header = "        " + "  ".join(f"Plate {PLATE_NAMES[p]}" for p in plate_ids)
    print(f"  {header}")
    for pi in plate_ids:
        row = "  ".join(f"{self_corr[pi][pj]:>7.4f}" for pj in plate_ids)
        print(f"  Plate {PLATE_NAMES[pi]}  {row}")

    off_diag = [self_corr[pi][pj] for pi in plate_ids
                for pj in plate_ids if pi != pj]
    max_off_self = max(abs(v) for v in off_diag)
    mean_off_self = float(np.mean([abs(v) for v in off_diag]))

    print(f"\n  Max |off-diagonal| (self): {max_off_self:.4f} (paper claims ≤ 0.21)")
    print(f"  Mean |off-diagonal| (self): {mean_off_self:.4f}")

    # ── Build full-response fingerprints (all frequencies) ───────────
    print("\n  --- Full-Response Correlation (all frequencies) ---")
    full_fingerprints = {}
    for pid in plate_ids:
        fp = [peak_log[pid][f] for f in all_freqs]
        full_fingerprints[pid] = np.array(fp, dtype=np.float64)

    full_corr: dict[str, dict[str, float]] = {}
    for pi in plate_ids:
        full_corr[pi] = {}
        for pj in plate_ids:
            vi = full_fingerprints[pi]
            vj = full_fingerprints[pj]
            if np.std(vi) > 0 and np.std(vj) > 0:
                r = float(np.corrcoef(vi, vj)[0, 1])
            else:
                r = 0.0
            full_corr[pi][pj] = round(r, 4)

    header = "        " + "  ".join(f"Plate {PLATE_NAMES[p]}" for p in plate_ids)
    print(f"  {header}")
    for pi in plate_ids:
        row = "  ".join(f"{full_corr[pi][pj]:>7.4f}" for pj in plate_ids)
        print(f"  Plate {PLATE_NAMES[pi]}  {row}")

    full_off = [full_corr[pi][pj] for pi in plate_ids
                for pj in plate_ids if pi != pj]
    max_off_full = max(abs(v) for v in full_off)
    mean_off_full = float(np.mean([abs(v) for v in full_off]))

    print(f"\n  Max |off-diagonal| (full): {max_off_full:.4f}")
    print(f"  Mean |off-diagonal| (full): {mean_off_full:.4f}")

    # ── Pairwise analysis ────────────────────────────────────────────
    print("\n  --- Pairwise Separation ---")
    for i, pi in enumerate(plate_ids):
        for pj in plate_ids[i + 1:]:
            r_self = self_corr[pi][pj]
            r_full = full_corr[pi][pj]
            print(f"    {PLATE_NAMES[pi]}×{PLATE_NAMES[pj]}: "
                  f"self ρ={r_self:+.4f}, full ρ={r_full:+.4f}")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.1f}s")

    # ── Verdict ──────────────────────────────────────────────────────
    rod_max = 0.79
    paper_target = 0.21
    if max_off_self <= paper_target:
        verdict = f"PASS — max |ρ|={max_off_self:.3f} ≤ {paper_target} (paper target)"
    elif max_off_self < rod_max:
        verdict = (f"IMPROVED — max |ρ|={max_off_self:.3f} < rod {rod_max:.2f}, "
                   f"but > paper target {paper_target}")
    else:
        verdict = f"NO IMPROVEMENT — max |ρ|={max_off_self:.3f} ≥ rod {rod_max:.2f}"

    print(f"\n  VERDICT: {verdict}")
    print(f"  Rod baseline: max |ρ| = {rod_max}")
    print(f"  Paper target: max |ρ| ≤ {paper_target}")

    # ── Save ─────────────────────────────────────────────────────────
    _close_scope(handle)
    mux.off()

    results = {
        "experiment": "plate_cross_correlation",
        "experiment_id": "E16",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "paper_claim": "Max off-diagonal |ρ| ≤ 0.21 (C12)",
        "rod_baseline": {"max_off_diagonal": rod_max},
        "n_plates": len(plate_ids),
        "n_peaks_per_plate": N_PEAKS,
        "n_unique_frequencies": len(all_freqs),
        "self_response_correlation": self_corr,
        "full_response_correlation": full_corr,
        "max_off_diagonal_self": round(max_off_self, 4),
        "mean_off_diagonal_self": round(mean_off_self, 4),
        "max_off_diagonal_full": round(max_off_full, 4),
        "mean_off_diagonal_full": round(mean_off_full, 4),
        "peak_log": {pid: {str(f): m for f, m in mags.items()}
                     for pid, mags in peak_log.items()},
        "verdict": verdict,
        "runtime_s": round(elapsed, 1),
    }

    LAB_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as fw:
        json.dump(results, fw, indent=2, default=str)
    print(f"\n  Saved: {RESULTS_FILE}")

    # ── Firestore submission ─────────────────────────────────────────
    if args.submit:
        token = firebase_anon_auth()
        if token:
            data = {
                "experiment_id": "E16",
                "substrate": "fused_silica_plate",
                "n_plates": len(plate_ids),
                "max_off_diagonal_self": round(max_off_self, 4),
                "mean_off_diagonal_self": round(mean_off_self, 4),
                "max_off_diagonal_full": round(max_off_full, 4),
                "paper_target": paper_target,
                "rod_baseline": rod_max,
                "verdict": verdict,
            }
            r = submit_experiment(
                token, "exp-plate-cross-correlation", data,
                notes=f"E16 cross-correlation: {verdict}"
            )
            print_result(r)


if __name__ == "__main__":
    main()
