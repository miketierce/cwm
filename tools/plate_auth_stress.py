#!/usr/bin/env python3
"""
Plate Authentication Stress Test — Multi-Channel Template Matching

Stress-tests plate identification using ALL extractable readout channels
from the same physical sense PZT:

  Channel 1: Magnitude (cross-relay normalized) — proven baseline
  Channel 2: Phase angle — resonance phase shift is plate-specific
  Channel 3: 2nd harmonic ratio (H2/H1) — nonlinear response fingerprint
  Channel 4: 3rd harmonic ratio (H3/H1) — higher-order nonlinearity
  Channel 5: Spectral width — local Q proxy, plate-specific damping

All channels are extracted from the SAME FFT capture — no additional
hardware cost.  The combined multi-channel template score should be
more robust than magnitude alone.

Protocol:
  1. Enrollment: measure each plate at its own enrolled freqs across all
     5 relay channels.  Record all 5 features per freq per plate.
  2. Auth: for each query plate, drive at its enrolled freqs, measure
     all 5 sense plates on all 5 channels, template-match with
     per-channel cross-relay normalization + boost/penalty.
  3. Repeat N trials for reproducibility statistics.

Signal chain (same as existing):
  AWG OUT → all 5 TX PZTs (shared drive)
  Relay N → Sense PZT Plate N → PicoScope Ch A

Usage:
  PYTHONPATH=. python tools/plate_auth_stress.py
  PYTHONPATH=. python tools/plate_auth_stress.py --trials 3
  PYTHONPATH=. python tools/plate_auth_stress.py --dry-run
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

# ── Configuration ──────────────────────────────────────────────────────
ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_FILE = LAB_DIR / f"auth_stress_{TIMESTAMP}.json"

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

N_AVG = 8            # more averages for stability
SETTLE_S = 0.05      # AWG settle
SETTLE_RELAY_S = 0.10  # relay settle

# Channel weights for combined score (tunable)
CHANNEL_WEIGHTS = {
    "magnitude": 1.0,
    "phase": 0.5,
    "h2_ratio": 0.3,
    "h3_ratio": 0.2,
    "spectral_width": 0.3,
}

# Template scoring: boost expected, penalize unexpected
BOOST = 3.0
PENALTY = 1.0
MATCH_TOL = 0.03     # 3% frequency match tolerance


# ── Multi-channel measurement ─────────────────────────────────────────

def _measure_multi(handle, freq_hz: float) -> dict:
    """Drive AWG at freq_hz, extract 5 readout channels from same capture.

    Returns dict with:
      magnitude  — FFT magnitude at fundamental
      phase_rad  — FFT phase at fundamental
      h2_ratio   — 2nd harmonic magnitude / fundamental (H2/H1)
      h3_ratio   — 3rd harmonic magnitude / fundamental (H3/H1)
      spectral_width — 6dB width in bins around fundamental peak
    """
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)

    mags, phs = [], []
    h2_ratios, h3_ratios = [], []
    widths = []

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
        if n <= 0:
            continue

        raw = np.array(buf_a[:n], dtype=np.float64)
        windowed = raw * np.hanning(len(raw))
        nfft = len(raw) * 4
        spectrum = np.fft.rfft(windowed, n=nfft)
        fft_mag = np.abs(spectrum)
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
        bin_hz = freq_axis[1] - freq_axis[0]

        # Channel 1: Magnitude at fundamental
        tb = int(round(freq_hz / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(fft_mag) - 1, tb + 3)
        peak_bin = lo + int(np.argmax(fft_mag[lo:hi + 1]))
        h1 = float(fft_mag[peak_bin])
        mags.append(h1)

        # Channel 2: Phase at fundamental
        phs.append(float(np.angle(spectrum[peak_bin])))

        # Channel 3: 2nd harmonic ratio
        tb2 = int(round(2 * freq_hz / bin_hz))
        if tb2 + 3 < len(fft_mag):
            lo2 = max(0, tb2 - 3)
            hi2 = min(len(fft_mag) - 1, tb2 + 3)
            h2 = float(np.max(fft_mag[lo2:hi2 + 1]))
            h2_ratios.append(h2 / h1 if h1 > 0 else 0.0)
        else:
            h2_ratios.append(0.0)

        # Channel 4: 3rd harmonic ratio
        tb3 = int(round(3 * freq_hz / bin_hz))
        if tb3 + 3 < len(fft_mag):
            lo3 = max(0, tb3 - 3)
            hi3 = min(len(fft_mag) - 1, tb3 + 3)
            h3 = float(np.max(fft_mag[lo3:hi3 + 1]))
            h3_ratios.append(h3 / h1 if h1 > 0 else 0.0)
        else:
            h3_ratios.append(0.0)

        # Channel 5: Spectral width (6dB below peak, in bins)
        half_power = h1 / 2.0
        width_bins = 0
        for offset in range(1, 20):
            left_ok = (peak_bin - offset >= 0 and
                       fft_mag[peak_bin - offset] > half_power)
            right_ok = (peak_bin + offset < len(fft_mag) and
                        fft_mag[peak_bin + offset] > half_power)
            if left_ok or right_ok:
                width_bins = offset
            else:
                break
        widths.append(width_bins * 2 + 1)  # total width in bins

    return {
        "magnitude": round(float(np.mean(mags)), 1) if mags else 0.0,
        "phase_rad": round(float(np.arctan2(
            np.mean(np.sin(phs)), np.mean(np.cos(phs))
        )), 4) if phs else 0.0,
        "h2_ratio": round(float(np.mean(h2_ratios)), 6) if h2_ratios else 0.0,
        "h3_ratio": round(float(np.mean(h3_ratios)), 6) if h3_ratios else 0.0,
        "spectral_width": round(float(np.mean(widths)), 2) if widths else 1.0,
        "per_capture_mags": [round(m, 1) for m in mags],
    }


# ── Scope helpers ──────────────────────────────────────────────────────

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
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


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Plate auth stress test")
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--trials", type=int, default=3,
                        help="Number of auth trials for reproducibility")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-submit", action="store_true",
                        help="Skip Firestore submission")
    args = parser.parse_args()

    # Load enrollment
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        print("ERROR: No census data. Run plate_mode_census.py first.")
        return

    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    templates = {}
    for pid in PLATE_IDS:
        if pid in census and census[pid].get("peaks"):
            templates[pid] = census[pid]["peaks"]  # full peak data

    active_ids = [pid for pid in PLATE_IDS if pid in templates]
    n_plates = len(active_ids)

    print("=" * 70)
    print("  PLATE AUTH STRESS TEST — MULTI-CHANNEL TEMPLATE MATCHING")
    print("=" * 70)
    print(f"  Plates: {n_plates} ({', '.join(PLATE_NAMES[p] for p in active_ids)})")
    print(f"  Peaks per plate: {[len(templates[p]) for p in active_ids]}")
    print(f"  Channels: {len(CHANNEL_WEIGHTS)} "
          f"({', '.join(CHANNEL_WEIGHTS.keys())})")
    print(f"  Trials: {args.trials}")

    # Open hardware
    if not args.dry_run:
        print("\nOpening hardware...")
        handle = _open_scope()
        mux = RelayMux(args.port)
        mux.open()
        print(f"  PicoScope + mux ready (port: {mux.port})")
    else:
        handle = None
        mux = None

    # ── Phase 1: Multi-channel enrollment ──────────────────────────────
    # Measure each plate at ALL plates' enrolled frequencies to build
    # a multi-channel enrollment profile.

    print("\n" + "═" * 70)
    print("  PHASE 1: MULTI-CHANNEL ENROLLMENT")
    print("═" * 70)

    # Collect union of all enrolled frequencies
    all_freqs = set()
    for pid in active_ids:
        for p in templates[pid]:
            all_freqs.add(p["freq_hz"])
    all_freqs = sorted(all_freqs)
    print(f"  Union of enrolled frequencies: {len(all_freqs)}")

    # enrollment[plate_id][freq] = {magnitude, phase_rad, h2_ratio, h3_ratio, spectral_width}
    enrollment = {pid: {} for pid in active_ids}

    if not args.dry_run:
        t0 = time.time()
        for fi, freq in enumerate(all_freqs):
            for sid in active_ids:
                mux.select(int(sid))
                time.sleep(SETTLE_RELAY_S)
                m = _measure_multi(handle, freq)
                enrollment[sid][freq] = m

            if fi % 5 == 0 or fi == len(all_freqs) - 1:
                elapsed = time.time() - t0
                pct = (fi + 1) / len(all_freqs) * 100
                print(f"    freq {fi+1}/{len(all_freqs)} "
                      f"({freq:.0f} Hz) [{pct:.0f}% | {elapsed:.0f}s]")

        elapsed = time.time() - t0
        print(f"  Enrollment done: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    else:
        print("  [DRY RUN] Skipping enrollment capture")

    # Print enrollment summary
    print("\n  Enrollment profiles:")
    for pid in active_ids:
        freqs_for = [p["freq_hz"] for p in templates[pid]]
        name = PLATE_NAMES[pid]
        if enrollment[pid]:
            own_mags = [enrollment[pid].get(f, {}).get("magnitude", 0)
                        for f in freqs_for if f in enrollment[pid]]
            avg_mag = np.mean(own_mags) if own_mags else 0
            own_phases = [enrollment[pid].get(f, {}).get("phase_rad", 0)
                          for f in freqs_for if f in enrollment[pid]]
            own_h2 = [enrollment[pid].get(f, {}).get("h2_ratio", 0)
                       for f in freqs_for if f in enrollment[pid]]
            print(f"    Plate {name}: {len(freqs_for)} freqs, "
                  f"avg_mag={avg_mag:.0f}, "
                  f"avg_phase={np.mean(own_phases):.3f} rad, "
                  f"avg_h2={np.mean(own_h2):.4f}")

    # ── Phase 2: Multi-trial authentication ────────────────────────────
    print("\n" + "═" * 70)
    print("  PHASE 2: MULTI-TRIAL AUTHENTICATION")
    print("═" * 70)

    trial_results = []

    for trial in range(1, args.trials + 1):
        print(f"\n{'─' * 60}")
        print(f"  TRIAL {trial}/{args.trials}")
        print(f"{'─' * 60}")

        trial_correct = 0
        trial_data = []

        for pid in active_ids:
            name = PLATE_NAMES[pid]
            query_freqs = [p["freq_hz"] for p in templates[pid]]
            print(f"\n  Query Plate {name} ({len(query_freqs)} freqs)")

            if args.dry_run:
                # Fake data for testing
                trial_data.append({
                    "query": pid, "winner": pid, "correct": True,
                    "scores": {s: 0. for s in active_ids},
                    "channel_scores": {},
                })
                trial_correct += 1
                continue

            # Measure all plates at query freqs
            raw = {sid: [] for sid in active_ids}
            t0 = time.time()

            for fi, freq in enumerate(query_freqs):
                for sid in active_ids:
                    mux.select(int(sid))
                    time.sleep(SETTLE_RELAY_S)
                    m = _measure_multi(handle, freq)
                    raw[sid].append(m)

            elapsed = time.time() - t0

            # Multi-channel template scoring
            channel_scores = {ch: {sid: 0.0 for sid in active_ids}
                              for ch in CHANNEL_WEIGHTS}

            for fi, freq in enumerate(query_freqs):
                for ch_name in CHANNEL_WEIGHTS:
                    # Get channel values across all sense plates at this freq
                    if ch_name == "magnitude":
                        vals = {s: raw[s][fi]["magnitude"] for s in active_ids}
                    elif ch_name == "phase":
                        # Use absolute phase deviation from enrollment
                        vals = {}
                        for s in active_ids:
                            live_ph = raw[s][fi]["phase_rad"]
                            enroll_ph = enrollment[s].get(freq, {}).get("phase_rad", 0)
                            # Phase similarity = 1 / (1 + |delta|)
                            delta = abs(math.atan2(
                                math.sin(live_ph - enroll_ph),
                                math.cos(live_ph - enroll_ph)
                            ))
                            vals[s] = 1.0 / (1.0 + delta)
                    elif ch_name == "h2_ratio":
                        vals = {s: raw[s][fi]["h2_ratio"] for s in active_ids}
                    elif ch_name == "h3_ratio":
                        vals = {s: raw[s][fi]["h3_ratio"] for s in active_ids}
                    elif ch_name == "spectral_width":
                        vals = {s: raw[s][fi]["spectral_width"] for s in active_ids}

                    # Cross-channel normalization
                    total = sum(abs(v) for v in vals.values())
                    if total == 0:
                        continue

                    for sid in active_ids:
                        frac = abs(vals[sid]) / total

                        # Does this sense plate have an enrolled peak near freq?
                        expected = any(
                            abs(freq - ep["freq_hz"]) / max(freq, ep["freq_hz"]) < MATCH_TOL
                            for ep in templates[sid]
                        )

                        if expected:
                            channel_scores[ch_name][sid] += frac * BOOST
                        else:
                            channel_scores[ch_name][sid] -= frac * PENALTY

            # Combine channels with weights
            combined = {sid: 0.0 for sid in active_ids}
            for ch_name, weight in CHANNEL_WEIGHTS.items():
                for sid in active_ids:
                    combined[sid] += weight * channel_scores[ch_name][sid]

            winner = max(combined, key=combined.get)
            is_correct = winner == pid
            if is_correct:
                trial_correct += 1

            # Print results
            status = "✓" if is_correct else "✗"
            wname = PLATE_NAMES[winner]
            sorted_s = sorted(combined.values(), reverse=True)
            margin = sorted_s[0] - sorted_s[1] if len(sorted_s) > 1 else 0

            print(f"    → {wname} {status}  margin={margin:.2f}  "
                  f"({elapsed:.1f}s)")
            for sid in active_ids:
                marker = " ◄" if sid == winner else ""
                ch_str = "  ".join(
                    f"{ch[:3]}={channel_scores[ch][sid]:+.2f}"
                    for ch in CHANNEL_WEIGHTS
                )
                print(f"      {PLATE_NAMES[sid]}: "
                      f"combined={combined[sid]:+.2f}  "
                      f"[{ch_str}]{marker}")

            trial_data.append({
                "query": pid,
                "query_name": name,
                "winner": winner,
                "winner_name": wname,
                "correct": is_correct,
                "margin": round(margin, 4),
                "combined_scores": {sid: round(combined[sid], 4) for sid in active_ids},
                "channel_scores": {
                    ch: {sid: round(channel_scores[ch][sid], 4)
                         for sid in active_ids}
                    for ch in CHANNEL_WEIGHTS
                },
                "raw_measurements": {
                    sid: raw[sid] for sid in active_ids
                } if not args.dry_run else {},
            })

        accuracy = trial_correct / n_plates * 100
        print(f"\n  Trial {trial}: {trial_correct}/{n_plates} "
              f"({accuracy:.0f}%)")

        trial_results.append({
            "trial": trial,
            "correct": trial_correct,
            "total": n_plates,
            "accuracy_pct": accuracy,
            "per_plate": trial_data,
        })

    # ── Summary ────────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  SUMMARY")
    print("═" * 70)

    accuracies = [t["accuracy_pct"] for t in trial_results]
    margins = []
    for t in trial_results:
        for pd in t["per_plate"]:
            if pd.get("margin") is not None:
                margins.append(pd["margin"])

    print(f"  Trials: {args.trials}")
    print(f"  Accuracy: {np.mean(accuracies):.0f}% "
          f"(min={min(accuracies):.0f}%, max={max(accuracies):.0f}%)")
    if margins:
        print(f"  Margins: mean={np.mean(margins):.2f}, "
              f"min={min(margins):.2f}, max={max(margins):.2f}")

    # Per-trial breakdown
    print("\n  Per-trial accuracy:")
    for t in trial_results:
        print(f"    Trial {t['trial']}: {t['correct']}/{t['total']} ({t['accuracy_pct']:.0f}%)")

    # Channel ablation — show per-channel accuracy
    print("\n  Per-channel solo accuracy (ablation):")
    for ch_name in CHANNEL_WEIGHTS:
        ch_correct = 0
        ch_total = 0
        for t in trial_results:
            for pd in t["per_plate"]:
                if "channel_scores" in pd and pd["channel_scores"]:
                    ch_scores = pd["channel_scores"].get(ch_name, {})
                    if ch_scores:
                        ch_winner = max(ch_scores, key=ch_scores.get)
                        if ch_winner == pd["query"]:
                            ch_correct += 1
                        ch_total += 1
        if ch_total > 0:
            print(f"    {ch_name:20s}: {ch_correct}/{ch_total} "
                  f"({ch_correct/ch_total*100:.0f}%)")

    # ── Firestore submission ───────────────────────────────────────────
    if not args.no_submit and not args.dry_run:
        print("\nSubmitting to Firestore...")
        token = firebase_anon_auth()
        # Submit one doc per trial with overall results
        for t in trial_results:
            data = {
                "n_rods": n_plates,
                "peaks_per_rod": max(len(templates[p]) for p in active_ids),
                "sample_rate": SAMPLE_RATE,
                "freq_resolution": 24.2,
                "auth_rms_pct": round(np.mean(margins), 2) if margins else 0,
                "auth_matched_peaks": max(len(templates[p]) for p in active_ids),
                "auth_score_pct": round(t["accuracy_pct"], 1),
                "next_best_score_pct": round(min(margins), 1) if margins else 0,
                "min_cross_rod_pct": round(min(margins), 1) if margins else 0,
                "excitation_method": "Piezo pulse",
                "correct_rod_identified": "Yes" if t["accuracy_pct"] == 100 else "No",
            }
            notes = (
                f"Stress test trial {t['trial']}: {t['correct']}/{t['total']} "
                f"({t['accuracy_pct']:.0f}%). "
                f"5-channel template matching (mag+phase+H2+H3+width). "
                f"Cross-relay normalization, boost/penalty scoring. "
                f"PicoScope 2204A, relay mux."
            )
            r = submit_experiment(token, "exp-hw-auth", data, notes=notes)
            print_result(r)

    # ── Save locally ───────────────────────────────────────────────────
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    save_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "n_plates": n_plates,
            "n_trials": args.trials,
            "n_avg": N_AVG,
            "channel_weights": CHANNEL_WEIGHTS,
            "boost": BOOST,
            "penalty": PENALTY,
            "match_tolerance": MATCH_TOL,
        },
        "enrollment": {
            pid: {
                str(freq): data
                for freq, data in enrollment[pid].items()
            } for pid in active_ids
        },
        "trials": trial_results,
        "summary": {
            "mean_accuracy_pct": round(float(np.mean(accuracies)), 1),
            "min_accuracy_pct": round(float(min(accuracies)), 1),
            "max_accuracy_pct": round(float(max(accuracies)), 1),
            "mean_margin": round(float(np.mean(margins)), 4) if margins else 0,
            "min_margin": round(float(min(margins)), 4) if margins else 0,
        },
    }
    with open(RESULTS_FILE, "w") as fw:
        json.dump(save_data, fw, indent=2, default=str)
    print(f"\n  Saved: {RESULTS_FILE}")

    # Cleanup
    if not args.dry_run:
        mux.off()
        _close_scope(handle)
        print("  Hardware closed")


if __name__ == "__main__":
    main()
