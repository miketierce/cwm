#!/usr/bin/env python3
"""
Plate E23: Parametric Amplification Proxy — Fused Silica Plates

Rod result: All configurations showed loss — FAILED (Q too low, 204–572).
Paper claim: +12 dB parametric amplification.
Plate Q: 7,687–30,830 — NOW EXCEEDS the 5,000 threshold for parametric gain.

Proxy test: drive at f_pump = f₁ + f₂ (sum of two enrolled plate
frequencies), measure whether the response at f₁ or f₂ shows
enhancement vs driving them solo. If gain > 0 dB, parametric coupling
is present. Target: +12 dB (paper claim).

Also tests difference-frequency pumping: f_pump = |f₁ − f₂|.

Signal chain:
  AWG OUT → Drive PZT (all plates share AWG via parallel wiring)
  Relay N → Sense PZT Plate N → PicoScope Ch A

Usage:
  PYTHONPATH=. python tools/plate_parametric_proxy.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_parametric_proxy.py --plate D
  PYTHONPATH=. python tools/plate_parametric_proxy.py --dry-run
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
SETTLE_S = 0.15           # Slightly longer settle for parametric
SETTLE_RELAY_S = 0.10
N_PEAKS = 10
MAX_PAIRS = 6             # Test up to 6 frequency pairs per plate

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}
NAME_TO_ID = {v: k for k, v in PLATE_NAMES.items()}

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_FILE = LAB_DIR / f"parametric_proxy_{TIMESTAMP}.json"


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


def _measure_fft_at(handle, drive_freq: float,
                    target_freq: float) -> float:
    """Drive AWG at drive_freq, measure FFT magnitude at target_freq."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(drive_freq), float(drive_freq), 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)

    magnitudes = []
    for _ in range(N_AVG):
        raw = _capture_raw(handle)
        if len(raw) > 0:
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            tb = int(round(target_freq / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft_mag) - 1, tb + 3)
            magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))

    return float(np.mean(magnitudes)) if magnitudes else 0.0


def _measure_solo(handle, freq: float) -> float:
    """Drive and measure at the same frequency (self-excitation baseline)."""
    return _measure_fft_at(handle, freq, freq)


# ── Enrollment loader ────────────────────────────────────────────────

def _load_enrollment() -> tuple[dict, list]:
    """Load plate enrollment from latest census file."""
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        raise FileNotFoundError("No census file found.")

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
    parser = argparse.ArgumentParser(
        description="Plate E23: Parametric Amplification Proxy"
    )
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--plate", default=None,
                        help="Plate letter (A-E) or 'all'. Default: D and E (8-mode plates).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit", action="store_true", help="Submit to Firestore")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  EXPERIMENT E23 (Plates): Parametric Amplification Proxy")
    print("=" * 70)
    print("  Paper claim: +12 dB parametric gain")
    print("  Rod result: ALL LOSS (Q 204–572 too low)")
    print("  Plate Q: 7,687–30,830 — exceeds 5,000 threshold")

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
        # Default: test D and E (8-mode plates, highest Q)
        test_plates = [p for p in ["4", "5"] if p in plate_ids]
        if not test_plates:
            test_plates = plate_ids[:2]

    nyquist = SAMPLE_RATE / 2

    if args.dry_run:
        for pid in test_plates:
            peaks = enrolled[pid]
            pairs = [(peaks[i], peaks[j])
                     for i in range(min(4, len(peaks)))
                     for j in range(i + 1, min(5, len(peaks)))][:MAX_PAIRS]
            print(f"\n  [DRY RUN] Plate {PLATE_NAMES[pid]}: "
                  f"would test {len(pairs)} frequency pairs")
            for f1, f2 in pairs:
                f_sum = f1 + f2
                f_diff = abs(f1 - f2)
                ok = "✓" if f_sum < nyquist else "✗ (>Nyquist)"
                print(f"    {f1:.0f} + {f2:.0f} = {f_sum:.0f} Hz {ok}, "
                      f"diff = {f_diff:.0f} Hz")
        return

    handle = _open_scope()
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {args.port}")

    t_start = time.time()
    all_results = []

    for pid in test_plates:
        print(f"\n  {'=' * 60}")
        print(f"  Testing Plate {PLATE_NAMES[pid]} (relay {pid})")
        print(f"  {'=' * 60}")

        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        peaks = enrolled[pid]

        # Build frequency pairs (first few peaks)
        pairs = []
        for i in range(min(4, len(peaks))):
            for j in range(i + 1, min(5, len(peaks))):
                pairs.append((peaks[i], peaks[j]))
        pairs = pairs[:MAX_PAIRS]

        plate_results = []

        for pi, (f1, f2) in enumerate(pairs):
            f_sum = f1 + f2
            f_diff = abs(f1 - f2)

            print(f"\n    Pair {pi + 1}/{len(pairs)}: "
                  f"f₁={f1:.0f} Hz, f₂={f2:.0f} Hz")
            print(f"      Sum pump: {f_sum:.0f} Hz, "
                  f"Diff pump: {f_diff:.0f} Hz")

            # ── Solo baselines ───────────────────────────────────────
            solo_f1 = _measure_solo(handle, f1)
            solo_f2 = _measure_solo(handle, f2)
            print(f"      Solo f₁: {solo_f1:.0f}")
            print(f"      Solo f₂: {solo_f2:.0f}")

            pair_result = {
                "f1_hz": round(f1, 1),
                "f2_hz": round(f2, 1),
                "solo_f1_mag": round(solo_f1, 1),
                "solo_f2_mag": round(solo_f2, 1),
                "tests": [],
            }

            # ── Sum-frequency pump: drive at f1+f2, measure at f1 and f2 ─
            if f_sum < nyquist:
                pump_f1 = _measure_fft_at(handle, f_sum, f1)
                pump_f2 = _measure_fft_at(handle, f_sum, f2)
                gain_f1_db = (20 * math.log10(pump_f1 / solo_f1)
                              if solo_f1 > 0 and pump_f1 > 0 else -99)
                gain_f2_db = (20 * math.log10(pump_f2 / solo_f2)
                              if solo_f2 > 0 and pump_f2 > 0 else -99)
                print(f"      Sum pump → f₁: {pump_f1:.0f} "
                      f"({gain_f1_db:+.1f} dB vs solo)")
                print(f"      Sum pump → f₂: {pump_f2:.0f} "
                      f"({gain_f2_db:+.1f} dB vs solo)")
                pair_result["tests"].append({
                    "pump_type": "sum",
                    "pump_freq_hz": round(f_sum, 1),
                    "response_at_f1": round(pump_f1, 1),
                    "response_at_f2": round(pump_f2, 1),
                    "gain_f1_db": round(gain_f1_db, 2),
                    "gain_f2_db": round(gain_f2_db, 2),
                    "max_gain_db": round(max(gain_f1_db, gain_f2_db), 2),
                })
            else:
                print(f"      Sum pump {f_sum:.0f} Hz > Nyquist "
                      f"{nyquist:.0f} Hz — SKIPPED")
                pair_result["tests"].append({
                    "pump_type": "sum",
                    "pump_freq_hz": round(f_sum, 1),
                    "skipped": True,
                    "reason": "above_nyquist",
                })

            # ── Difference-frequency pump: |f1-f2|, measure at f1 and f2 ─
            if f_diff > 100:  # Only if diff is meaningful
                diff_f1 = _measure_fft_at(handle, f_diff, f1)
                diff_f2 = _measure_fft_at(handle, f_diff, f2)
                gain_f1_db = (20 * math.log10(diff_f1 / solo_f1)
                              if solo_f1 > 0 and diff_f1 > 0 else -99)
                gain_f2_db = (20 * math.log10(diff_f2 / solo_f2)
                              if solo_f2 > 0 and diff_f2 > 0 else -99)
                print(f"      Diff pump → f₁: {diff_f1:.0f} "
                      f"({gain_f1_db:+.1f} dB vs solo)")
                print(f"      Diff pump → f₂: {diff_f2:.0f} "
                      f"({gain_f2_db:+.1f} dB vs solo)")
                pair_result["tests"].append({
                    "pump_type": "difference",
                    "pump_freq_hz": round(f_diff, 1),
                    "response_at_f1": round(diff_f1, 1),
                    "response_at_f2": round(diff_f2, 1),
                    "gain_f1_db": round(gain_f1_db, 2),
                    "gain_f2_db": round(gain_f2_db, 2),
                    "max_gain_db": round(max(gain_f1_db, gain_f2_db), 2),
                })
            else:
                print(f"      Diff pump {f_diff:.0f} Hz too low — SKIPPED")

            plate_results.append(pair_result)

        # ── Plate summary ────────────────────────────────────────────
        all_gains = []
        for pr in plate_results:
            for t in pr["tests"]:
                if not t.get("skipped"):
                    all_gains.append(t["max_gain_db"])

        max_gain = max(all_gains) if all_gains else -99
        any_positive = any(g > 0 for g in all_gains)

        if max_gain >= 12:
            plate_verdict = f"CONFIRMED — max gain {max_gain:+.1f} dB (≥+12 dB target)"
        elif max_gain > 0:
            plate_verdict = f"PARTIAL GAIN — max {max_gain:+.1f} dB (below +12 dB target)"
        elif max_gain > -3:
            plate_verdict = f"MARGINAL — max {max_gain:+.1f} dB (near unity)"
        else:
            plate_verdict = f"LOSS — max {max_gain:+.1f} dB (no parametric gain)"

        print(f"\n  Plate {PLATE_NAMES[pid]} verdict: {plate_verdict}")
        print(f"    Max gain across all pairs: {max_gain:+.1f} dB")
        print(f"    Any positive gain: {'YES' if any_positive else 'NO'}")

        all_results.append({
            "plate_id": pid,
            "plate_name": PLATE_NAMES[pid],
            "n_pairs": len(pairs),
            "pair_results": plate_results,
            "max_gain_db": round(max_gain, 2),
            "any_positive_gain": any_positive,
            "verdict": plate_verdict,
        })

    elapsed = time.time() - t_start
    _close_scope(handle)
    mux.off()

    # ── Overall verdict ──────────────────────────────────────────────
    print(f"\n  {'=' * 60}")
    print(f"  SUMMARY — Parametric Amplification Proxy")
    print(f"  {'=' * 60}")

    overall_max = max(r["max_gain_db"] for r in all_results)
    overall_any = any(r["any_positive_gain"] for r in all_results)

    if overall_max >= 12:
        overall_verdict = (f"CONFIRMED — max gain {overall_max:+.1f} dB "
                           f"(paper target +12 dB)")
    elif overall_max > 0:
        overall_verdict = (f"PARTIAL — max gain {overall_max:+.1f} dB "
                           f"(positive but below +12 dB)")
    else:
        overall_verdict = (f"NOT CONFIRMED — max gain {overall_max:+.1f} dB "
                           f"(rod result: all loss)")

    print(f"  Overall max gain: {overall_max:+.1f} dB")
    print(f"  Paper target: +12 dB")
    print(f"  Rod baseline: all loss (Q too low)")
    print(f"  Verdict: {overall_verdict}")
    print(f"  Runtime: {elapsed:.1f}s")

    for r in all_results:
        print(f"    Plate {r['plate_name']}: max {r['max_gain_db']:+.1f} dB — "
              f"{r['verdict']}")

    # ── Save ─────────────────────────────────────────────────────────
    save_data = {
        "experiment": "plate_parametric_proxy",
        "experiment_id": "E23",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "paper_claim": "+12 dB parametric amplification",
        "rod_baseline": {"result": "all loss", "reason": "Q too low (204-572)"},
        "plate_q_range": "7,687–30,830",
        "config": {
            "n_avg": N_AVG,
            "settle_s": SETTLE_S,
            "drive_uvpp": AWG_DRIVE_UVPP,
            "sample_rate": SAMPLE_RATE,
            "nyquist_hz": nyquist,
        },
        "plate_results": all_results,
        "summary": {
            "plates_tested": len(all_results),
            "overall_max_gain_db": round(overall_max, 2),
            "any_positive_gain": overall_any,
            "verdict": overall_verdict,
        },
        "runtime_s": round(elapsed, 1),
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
                    "experiment_id": "E23",
                    "substrate": "fused_silica_plate",
                    "plate": r["plate_name"],
                    "max_gain_db": r["max_gain_db"],
                    "any_positive_gain": r["any_positive_gain"],
                    "n_pairs_tested": r["n_pairs"],
                    "verdict": r["verdict"],
                }
                res = submit_experiment(
                    token, "exp-plate-parametric", data,
                    notes=f"E23 Plate {r['plate_name']}: {r['verdict']}"
                )
                print_result(res)


if __name__ == "__main__":
    main()
