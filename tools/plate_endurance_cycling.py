#!/usr/bin/env python3
"""
Plate E25: Endurance Cycling — Fused Silica Plates

Rod result: 549K cycles, strong modes shifted <0.2 dB — CONFIRMED.
Paper claim: >10^15 non-destructive cycles (§1.3, §10.1).

Drives each plate at its strongest resonant mode for ~5 minutes of CW
excitation, takes periodic magnitude checkpoints, then compares pre/post
full spectral fingerprint to verify no degradation.

Signal chain:
  AWG OUT → Drive PZT (all plates share AWG via parallel wiring)
  Relay N → Sense PZT Plate N → PicoScope Ch A

Usage:
  PYTHONPATH=. python tools/plate_endurance_cycling.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_endurance_cycling.py --plate D --duration 600
  PYTHONPATH=. python tools/plate_endurance_cycling.py --dry-run
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
DRIVE_DURATION_S = 300       # 5 minutes default
CHECK_INTERVAL_S = 60        # checkpoint every 60s

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}
NAME_TO_ID = {v: k for k, v in PLATE_NAMES.items()}

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_FILE = LAB_DIR / f"endurance_cycling_{TIMESTAMP}.json"


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


def _capture_raw(handle) -> np.ndarray:
    """Capture a single raw waveform."""
    from picosdk.ps2000 import ps2000
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
    return np.array(buf_a[:n], dtype=np.float64) if n > 0 else np.zeros(N_SAMPLES)


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
        raw = _capture_raw(handle)
        if len(raw) > 0:
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


def _measure_checkpoint(handle, drive_freq: float) -> float:
    """Quick magnitude measurement at the drive frequency during CW."""
    raw = _capture_raw(handle)
    if len(raw) == 0:
        return 0.0
    windowed = raw * np.hanning(len(raw))
    nfft = len(raw) * 4
    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
    bin_hz = freq_axis[1] - freq_axis[0]
    tb = int(round(drive_freq / bin_hz))
    lo = max(0, tb - 3)
    hi = min(len(fft_mag) - 1, tb + 3)
    return float(np.max(fft_mag[lo:hi + 1]))


# ── Enrollment loader ────────────────────────────────────────────────

def _load_enrollment() -> tuple[dict, list]:
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
    for pid in PLATE_IDS:
        if pid in census and census[pid].get("peaks"):
            peaks = census[pid]["peaks"][:N_PEAKS]
            enrolled[pid] = [p["freq_hz"] for p in peaks]

    plate_ids = sorted(enrolled.keys())
    print(f"  Loaded enrollment: {len(plate_ids)} plates, ≤{N_PEAKS} peaks each")
    return enrolled, plate_ids


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Plate E25: Endurance Cycling")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--plate", default=None,
                        help="Plate letter (A-E) or 'all'. Default: strongest Q plate.")
    parser.add_argument("--duration", type=int, default=DRIVE_DURATION_S,
                        help=f"Drive duration in seconds (default: {DRIVE_DURATION_S})")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit", action="store_true", help="Submit to Firestore")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  EXPERIMENT E25 (Plates): Endurance Cycling")
    print("=" * 70)

    enrolled, plate_ids = _load_enrollment()

    # Determine which plates to test
    if args.plate and args.plate.lower() == "all":
        test_plates = plate_ids
    elif args.plate:
        pid = NAME_TO_ID.get(args.plate.upper())
        if pid and pid in plate_ids:
            test_plates = [pid]
        else:
            print(f"  ERROR: Plate '{args.plate}' not found")
            return
    else:
        # Default: test plate D (strongest Q from earlier measurements)
        test_plates = ["4"] if "4" in plate_ids else [plate_ids[0]]

    if args.dry_run:
        for pid in test_plates:
            drive_freq = enrolled[pid][0]
            est_cycles = int(drive_freq * args.duration)
            print(f"\n  [DRY RUN] Plate {PLATE_NAMES[pid]}: would drive "
                  f"{drive_freq:.0f} Hz for {args.duration}s (~{est_cycles:,} cycles)")
        return

    handle = _open_scope()
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {args.port}")

    all_results = []
    t_total_start = time.time()

    for pid in test_plates:
        print(f"\n  {'=' * 60}")
        print(f"  Testing Plate {PLATE_NAMES[pid]} (relay {pid})")
        print(f"  {'=' * 60}")

        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        peaks = enrolled[pid]
        # Drive the strongest peak (index 0 from census — sorted by magnitude)
        drive_freq = peaks[0]
        est_cycles = int(drive_freq * args.duration)

        print(f"\n  Drive frequency: {drive_freq:.1f} Hz")
        print(f"  Duration: {args.duration}s, estimated cycles: {est_cycles:,}")

        # ── Phase 1: Baseline spectrum ───────────────────────────────
        print(f"\n  Phase 1: Baseline spectrum ({len(peaks)} peaks)")
        baseline = {}
        for freq in peaks:
            m = _measure_at(handle, freq)
            baseline[round(freq, 1)] = m["magnitude"]
            print(f"    {freq:>10.1f} Hz: {m['magnitude']:>10.0f}")

        # ── Phase 2: Sustained CW drive with checkpoints ────────────
        print(f"\n  Phase 2: Sustained CW drive at {drive_freq:.1f} Hz "
              f"for {args.duration}s...")

        from picosdk.ps2000 import ps2000
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(drive_freq), float(drive_freq), 0.0, 0.0, 0, 0
        )

        checkpoints = []
        t0 = time.time()
        next_check = CHECK_INTERVAL_S

        while True:
            elapsed = time.time() - t0
            if elapsed >= args.duration:
                break
            if elapsed >= next_check:
                mag = _measure_checkpoint(handle, drive_freq)
                checkpoints.append({
                    "elapsed_s": round(elapsed, 1),
                    "magnitude": round(mag, 1),
                })
                print(f"    t={elapsed:>5.0f}s: mag={mag:>10.0f}")
                next_check += CHECK_INTERVAL_S
            time.sleep(1)

        actual_elapsed = time.time() - t0
        actual_cycles = int(drive_freq * actual_elapsed)
        print(f"    Completed: {actual_elapsed:.0f}s, ~{actual_cycles:,} cycles")

        # ── Phase 3: Post-stress spectrum ────────────────────────────
        print(f"\n  Phase 3: Post-stress spectrum")
        # Brief settle after stopping continuous drive
        time.sleep(1.0)
        post_stress = {}
        for freq in peaks:
            m = _measure_at(handle, freq)
            post_stress[round(freq, 1)] = m["magnitude"]
            print(f"    {freq:>10.1f} Hz: {m['magnitude']:>10.0f}")

        # ── Compare ──────────────────────────────────────────────────
        shifts = []
        print(f"\n  Comparison (pre → post):")
        for freq in peaks:
            fk = round(freq, 1)
            pre = baseline.get(fk, 0)
            post = post_stress.get(fk, 0)
            change_pct = ((post - pre) / pre * 100) if pre > 0 else 0
            ratio_db = (20 * math.log10(post / pre)
                        if pre > 0 and post > 0 else 0)
            shifts.append({
                "freq_hz": fk,
                "pre": round(pre, 1),
                "post": round(post, 1),
                "change_pct": round(change_pct, 1),
                "ratio_db": round(ratio_db, 2),
            })
            print(f"    {fk:>10.1f} Hz: {pre:>10.0f} → {post:>10.0f}  "
                  f"({change_pct:+.1f}%, {ratio_db:+.2f} dB)")

        max_change_pct = max(abs(s["change_pct"]) for s in shifts)
        max_change_db = max(abs(s["ratio_db"]) for s in shifts)
        mean_change_db = float(np.mean([abs(s["ratio_db"]) for s in shifts]))

        # Checkpoint stability (drift during drive)
        if len(checkpoints) >= 2:
            cp_mags = [c["magnitude"] for c in checkpoints]
            cp_drift_pct = ((cp_mags[-1] - cp_mags[0]) / cp_mags[0] * 100
                            if cp_mags[0] > 0 else 0)
        else:
            cp_drift_pct = 0

        # Verdict
        if max_change_db <= 0.5:
            verdict = (f"PASS — max change {max_change_db:.2f} dB "
                       f"(≤0.5 dB threshold)")
        elif max_change_db <= 1.0:
            verdict = (f"MARGINAL — max change {max_change_db:.2f} dB "
                       f"(0.5–1.0 dB)")
        else:
            verdict = f"DEGRADATION — max change {max_change_db:.2f} dB (>1.0 dB)"

        print(f"\n  Plate {PLATE_NAMES[pid]} verdict: {verdict}")
        print(f"    Max change: {max_change_db:.2f} dB ({max_change_pct:.1f}%)")
        print(f"    Mean change: {mean_change_db:.2f} dB")
        print(f"    CW drift during drive: {cp_drift_pct:+.1f}%")

        all_results.append({
            "plate_id": pid,
            "plate_name": PLATE_NAMES[pid],
            "drive_freq_hz": drive_freq,
            "drive_duration_s": round(actual_elapsed, 1),
            "estimated_cycles": actual_cycles,
            "baseline": baseline,
            "post_stress": post_stress,
            "per_peak": shifts,
            "checkpoints": checkpoints,
            "max_change_pct": round(max_change_pct, 1),
            "max_change_db": round(max_change_db, 2),
            "mean_change_db": round(mean_change_db, 2),
            "checkpoint_drift_pct": round(cp_drift_pct, 1),
            "verdict": verdict,
        })

    total_elapsed = time.time() - t_total_start
    _close_scope(handle)
    mux.off()

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n  {'=' * 60}")
    print(f"  SUMMARY — Endurance Cycling")
    print(f"  {'=' * 60}")
    total_cycles = sum(r["estimated_cycles"] for r in all_results)
    worst_db = max(r["max_change_db"] for r in all_results)
    print(f"  Plates tested: {len(all_results)}")
    print(f"  Total cycles: {total_cycles:,}")
    print(f"  Worst change: {worst_db:.2f} dB")
    print(f"  Rod baseline: 549K cycles, <0.2 dB shift")
    print(f"  Total runtime: {total_elapsed:.1f}s")

    for r in all_results:
        print(f"    Plate {r['plate_name']}: {r['estimated_cycles']:,} cycles, "
              f"max {r['max_change_db']:.2f} dB — {r['verdict']}")

    # ── Save ─────────────────────────────────────────────────────────
    save_data = {
        "experiment": "plate_endurance_cycling",
        "experiment_id": "E25",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "paper_claim": ">10^15 non-destructive cycles (§1.3, §10.1)",
        "rod_baseline": {"cycles": 549000, "max_change_db": 0.2},
        "config": {
            "drive_duration_s": args.duration,
            "n_avg": N_AVG,
            "drive_uvpp": AWG_DRIVE_UVPP,
            "checkpoint_interval_s": CHECK_INTERVAL_S,
        },
        "plate_results": all_results,
        "summary": {
            "plates_tested": len(all_results),
            "total_cycles": total_cycles,
            "worst_change_db": round(worst_db, 2),
        },
        "runtime_s": round(total_elapsed, 1),
    }

    LAB_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as fw:
        json.dump(save_data, fw, indent=2, default=str)
    print(f"\n  Saved: {RESULTS_FILE}")

    # ── Firestore submission ─────────────────────────────────────────
    if args.submit:
        token = firebase_anon_auth()
        if token:
            for r in all_results:
                data = {
                    "experiment_id": "E25",
                    "substrate": "fused_silica_plate",
                    "plate": r["plate_name"],
                    "drive_freq_hz": r["drive_freq_hz"],
                    "cycles": r["estimated_cycles"],
                    "max_change_db": r["max_change_db"],
                    "verdict": r["verdict"],
                }
                res = submit_experiment(
                    token, "exp-plate-endurance", data,
                    notes=f"E25 Plate {r['plate_name']}: "
                          f"{r['estimated_cycles']:,} cycles, {r['verdict']}"
                )
                print_result(res)


if __name__ == "__main__":
    main()
