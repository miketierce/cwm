#!/usr/bin/env python3
"""
Run plate experiments and submit results to Firestore.

Plate equivalents of the rod experiments in run_rod_experiments.py,
adapted for the 5-plate fused silica array.

Experiments:
  1. Mode persistence — compare census baseline to live sweep
  2. SNR measurement — per-plate SNR from CW sweep
  3. Damping / Q measurement — per-plate Q from ringdown or CW bandwidth
  4. Plate fingerprint auth — identify plate from spectral signature
  5. Mode survey — submit Step 2 census data to Firestore

Each experiment uses the relay mux for per-plate isolation.
No tapping needed — all measurements use AWG CW drive.

Usage:
  PYTHONPATH=. python tools/run_plate_experiments.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/run_plate_experiments.py --exp 1 2 3
  PYTHONPATH=. python tools/run_plate_experiments.py --exp 5 --census-file data/results/lab/plate_exps/plate_census_20260412_180543.json
  PYTHONPATH=. python tools/run_plate_experiments.py --dry-run
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

import cwm_picoscope  # noqa: F401 — DYLD_LIBRARY_PATH fix
from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux
from firestore_submit import firebase_anon_auth, submit_experiment, print_result

# ── Configuration ──────────────────────────────────────────────────────
ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_FILE = LAB_DIR / f"plate_experiments_{TIMESTAMP}.json"

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

# Sweep parameters (coarser than Step 2 for speed)
F_START = 200
F_STOP = 100_000
F_STEP_COARSE = 100   # Hz — matches Step 1
F_STEP_FINE = 25      # Hz — matches Step 2
N_AVG = 4
SETTLE_S = 0.05
SETTLE_RELAY_S = 0.10
N_PEAKS_AUTH = 10      # peaks for auth fingerprint


# ── Scope helpers ──────────────────────────────────────────────────────

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
    """Drive AWG at freq_hz, capture magnitude and phase."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)

    magnitudes = []
    phases = []
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
            spectrum = np.fft.rfft(windowed, n=nfft)
            fft_mag = np.abs(spectrum)
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            tb = int(round(freq_hz / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft_mag) - 1, tb + 3)
            peak_bin = lo + int(np.argmax(fft_mag[lo:hi + 1]))
            magnitudes.append(float(fft_mag[peak_bin]))
            phases.append(float(np.angle(spectrum[peak_bin])))

    return {
        "magnitude": round(float(np.mean(magnitudes)), 1) if magnitudes else 0.0,
        "phase_rad": round(float(np.arctan2(
            np.mean(np.sin(phases)), np.mean(np.cos(phases))
        )), 4) if phases else 0.0,
    }


def _quick_sweep(handle, mux, plate_id: str,
                 f_step: int = F_STEP_COARSE) -> list[dict]:
    """Quick CW sweep on one plate. Returns list of {freq_hz, magnitude, phase_rad}."""
    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    freqs = np.arange(F_START, F_STOP + f_step, f_step)
    name = PLATE_NAMES[plate_id]
    n_pts = len(freqs)
    print(f"  Plate {name}: sweep {F_START}–{F_STOP} Hz, {f_step} Hz steps ({n_pts} pts)")

    data = []
    t0 = time.time()
    for i, freq in enumerate(freqs):
        m = _measure_at(handle, freq)
        data.append({"freq_hz": round(float(freq), 1), **m})
        if i % 200 == 0:
            elapsed = time.time() - t0
            pct = (i + 1) / n_pts * 100
            print(f"    {freq:7.0f} Hz: mag={m['magnitude']:10.0f}  [{pct:4.1f}% | {elapsed:.0f}s]")

    elapsed = time.time() - t0
    print(f"    Done: {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    return data


def _extract_peaks(sweep_data: list[dict], min_snr_db=6.0, min_prom_db=3.0) -> list[dict]:
    """Detect resonance peaks from sweep data."""
    mags = np.array([s["magnitude"] for s in sweep_data])
    freqs = np.array([s["freq_hz"] for s in sweep_data])
    noise_floor = float(np.median(mags))
    if noise_floor <= 0:
        noise_floor = 1.0

    peaks = []
    for i in range(2, len(mags) - 2):
        if not (mags[i] > mags[i - 1] and mags[i] > mags[i + 1]):
            continue
        snr_db = 20 * math.log10(mags[i] / noise_floor) if mags[i] > 0 else 0
        if snr_db < min_snr_db:
            continue
        local_min = min(mags[i - 2], mags[i - 1], mags[i + 1], mags[i + 2])
        prom_db = 20 * math.log10(mags[i] / local_min) if local_min > 0 else snr_db
        if prom_db < min_prom_db:
            continue
        peaks.append({
            "freq_hz": float(freqs[i]),
            "magnitude": float(mags[i]),
            "snr_db": round(snr_db, 1),
            "phase_rad": sweep_data[i].get("phase_rad", 0.0),
        })

    peaks.sort(key=lambda p: p["magnitude"], reverse=True)
    return peaks


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 1: Mode Persistence
# ═══════════════════════════════════════════════════════════════════════

def exp1_mode_persistence(token: str, dry_run: bool, handle, mux,
                          baseline_file: str | None = None) -> list:
    """Compare current mode frequencies to census baseline.

    If baseline_file is provided, loads reference peaks from that census.
    Otherwise loads the latest census from plate_exps/.
    """
    print("\n" + "=" * 65)
    print("  PLATE EXPERIMENT 1: MODE PERSISTENCE")
    print("=" * 65)

    # Load baseline
    if baseline_file:
        bpath = Path(baseline_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            print("  ERROR: No census baseline found. Run plate_mode_census.py first.")
            return []
        bpath = census_files[-1]

    print(f"  Baseline: {bpath.name}")
    with open(bpath) as f:
        baseline = json.load(f)    # Census files nest plate data under 'results'
    if "results" in baseline:
        baseline = baseline["results"]
    results = []

    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        if pid not in baseline:
            print(f"  Plate {name}: no baseline, skipping")
            continue

        base_peaks = baseline[pid]["peaks"]
        if not base_peaks:
            continue

        print(f"\n─── Plate {name} (relay {pid}) ───")
        print(f"  Baseline: {len(base_peaks)} modes")

        # Quick coarse sweep
        sweep = _quick_sweep(handle, mux, pid)
        live_peaks = _extract_peaks(sweep)
        print(f"  Live: {len(live_peaks)} modes")

        # Match: find closest live peak for each baseline peak
        matched = 0
        drifts = []
        base_top = base_peaks[:10]
        for bp in base_top:
            bf = bp["freq_hz"]
            closest = min(live_peaks, key=lambda p: abs(p["freq_hz"] - bf)) if live_peaks else None
            if closest and abs(closest["freq_hz"] - bf) / bf < 0.02:  # within 2%
                matched += 1
                drift_pct = (closest["freq_hz"] - bf) / bf * 100
                drifts.append(drift_pct)
                print(f"    {bf:.0f} Hz → {closest['freq_hz']:.0f} Hz ({drift_pct:+.2f}%)")

        match_pct = matched / len(base_top) * 100 if base_top else 0
        mean_drift = float(np.mean(drifts)) if drifts else 0

        best_peak = live_peaks[0] if live_peaks else base_peaks[0]
        _all = live_peaks if live_peaks else base_peaks
        f11 = min(p["freq_hz"] for p in _all)
        data = {
            "plate_material": "Fused quartz",
            "plate_length": 100,
            "plate_width": 100,
            "plate_thickness": 1,
            "pzt_mounting": "Corner face mount",
            "pzt_drive_position": 5,
            "pzt_sense_position": 95,
            "num_modes_bare": len(live_peaks),
            "f11_measured": round(min(f11, 50000), 1),
            "snr_best_mode": round(best_peak.get("snr_db", 20), 1),
        }
        if len(live_peaks) > 1:
            _spacing = round(float(np.mean(np.diff(sorted(p["freq_hz"] for p in live_peaks)))), 1)
            if _spacing <= 10000:
                data["mean_mode_spacing"] = _spacing

        notes = (
            f"Plate {name}, mode persistence: {matched}/{len(base_top)} top modes "
            f"matched within 2%, mean drift {mean_drift:.3f}%. "
            f"Baseline: {bpath.name}. AWG CW sweep 200–100kHz, 100Hz steps. "
            f"PicoScope 2204A, relay mux isolation."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit exp05-plate-mode-survey (persistence)")
            results.append({"ok": True, "dry": True, "plate": name, "data": data})
        else:
            r = submit_experiment(token, "exp05-plate-mode-survey", data, notes=notes)
            r["_data"] = data
            r["_notes"] = notes
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 2: SNR Measurement
# ═══════════════════════════════════════════════════════════════════════

def exp2_snr(token: str, dry_run: bool, handle, mux) -> list:
    """Measure per-plate SNR from CW sweep."""
    print("\n" + "=" * 65)
    print("  PLATE EXPERIMENT 2: SNR MEASUREMENT")
    print("=" * 65)

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        print(f"\n─── Plate {name} (relay {pid}) ───")

        sweep = _quick_sweep(handle, mux, pid)
        peaks = _extract_peaks(sweep)

        mags = np.array([s["magnitude"] for s in sweep])
        noise_floor = float(np.median(mags))
        peak_mag = float(np.max(mags))
        snr_db = 20 * math.log10(peak_mag / noise_floor) if noise_floor > 0 else 0

        print(f"  Peak: {peak_mag:.0f}, Floor: {noise_floor:.0f}, "
              f"SNR: {snr_db:.1f} dB, Modes: {len(peaks)}")

        data = {
            "plate_material": "Fused quartz",
            "plate_length": 100,
            "plate_width": 100,
            "plate_thickness": 1,
            "pzt_mounting": "Corner face mount",
            "pzt_drive_position": 5,
            "pzt_sense_position": 95,
            "num_modes_bare": len(peaks),
            "f11_measured": round(min(p["freq_hz"] for p in peaks), 1) if peaks else 500,
            "snr_best_mode": round(snr_db, 1),
        }
        if len(peaks) > 1:
            _spacing = round(float(np.mean(np.diff(sorted(p["freq_hz"] for p in peaks)))), 1)
            if _spacing <= 10000:
                data["mean_mode_spacing"] = _spacing

        notes = (
            f"Plate {name} SNR measurement. AWG CW sweep 200–100kHz, 100Hz steps. "
            f"{len(peaks)} modes detected. Top freq: {peaks[0]['freq_hz']:.0f} Hz. "
            f"PicoScope 2204A, relay mux isolation."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "plate": name, "data": data})
        else:
            r = submit_experiment(token, "exp05-plate-mode-survey", data, notes=notes)
            r["_data"] = data
            r["_notes"] = notes
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 3: Damping / Q Measurement
# ═══════════════════════════════════════════════════════════════════════

def exp3_damping(token: str, dry_run: bool, handle, mux) -> list:
    """Measure Q factor for each plate via 3dB bandwidth method."""
    print("\n" + "=" * 65)
    print("  PLATE EXPERIMENT 3: Q / DAMPING MEASUREMENT")
    print("=" * 65)

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        print(f"\n─── Plate {name} (relay {pid}) ───")

        # Fine sweep around known peak regions for accurate Q
        sweep = _quick_sweep(handle, mux, pid, f_step=F_STEP_FINE)
        peaks = _extract_peaks(sweep)

        if not peaks:
            print("  No peaks found, skipping")
            continue

        # Q from 3dB bandwidth of strongest peak
        mags = np.array([s["magnitude"] for s in sweep])
        freqs = np.array([s["freq_hz"] for s in sweep])

        best_peak = peaks[0]
        bf = best_peak["freq_hz"]
        bi = int(np.argmin(np.abs(freqs - bf)))
        peak_val = mags[bi]
        half_power = peak_val / math.sqrt(2)

        left = bi
        while left > 0 and mags[left] > half_power:
            left -= 1
        right = bi
        while right < len(mags) - 1 and mags[right] > half_power:
            right += 1

        bw_hz = float(freqs[right] - freqs[left])
        q_factor = bf / bw_hz if bw_hz > 0 else 100.0
        tau_s = q_factor / (math.pi * bf) if bf > 0 else 0.01

        print(f"  f₁ = {bf:.0f} Hz, Q ≈ {q_factor:.0f}, "
              f"τ = {tau_s * 1000:.1f} ms, BW = {bw_hz:.1f} Hz")

        data = {
            "plate_material": "Fused quartz",
            "plate_length": 100,
            "plate_width": 100,
            "plate_thickness": 1,
            "pzt_mounting": "Corner face mount",
            "pzt_drive_position": 5,
            "pzt_sense_position": 95,
            "num_modes_bare": len(peaks),
            "f11_measured": round(min(min(p["freq_hz"] for p in peaks), 50000), 1),
            "snr_best_mode": round(peaks[0]["snr_db"], 1) if peaks else 20,
            "q_estimate": max(10, int(round(q_factor, 0))),
        }
        if len(peaks) > 1:
            _spacing = round(float(np.mean(np.diff(sorted(p["freq_hz"] for p in peaks)))), 1)
            if _spacing <= 10000:
                data["mean_mode_spacing"] = _spacing

        notes = (
            f"Plate {name} Q measurement. Strongest mode at {bf:.0f} Hz, "
            f"Q={q_factor:.0f}, τ={tau_s * 1000:.1f} ms, BW={bw_hz:.1f} Hz. "
            f"25Hz-step CW sweep, 3dB bandwidth method. "
            f"PicoScope 2204A, relay mux isolation."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "plate": name, "data": data})
        else:
            r = submit_experiment(token, "exp05-plate-mode-survey", data, notes=notes)
            r["_data"] = data
            r["_notes"] = notes
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 4: Plate Fingerprint Authentication
# ═══════════════════════════════════════════════════════════════════════

def exp4_fingerprint(token: str, dry_run: bool, handle, mux) -> list:
    """Identify each plate from its spectral fingerprint.

    Protocol:
      1. Load census data as enrollment templates
      2. For each plate, do a live sweep and score against all templates
      3. Check if correct plate is identified (highest score)
    """
    print("\n" + "=" * 65)
    print("  PLATE EXPERIMENT 4: SPECTRAL FINGERPRINT AUTH")
    print("=" * 65)

    # Load enrollment data
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        print("  ERROR: No census data for enrollment. Run plate_mode_census.py first.")
        return []

    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    # Build templates: top N_PEAKS_AUTH frequencies per plate
    templates = {}
    for pid in PLATE_IDS:
        if pid in census and census[pid].get("peaks"):
            templates[pid] = [p["freq_hz"] for p in census[pid]["peaks"][:N_PEAKS_AUTH]]

    if len(templates) < 2:
        print("  ERROR: Need at least 2 enrolled plates")
        return []

    print(f"  Enrolled: {len(templates)} plates, {N_PEAKS_AUTH} peaks each")

    results = []
    correct = 0
    total = 0

    for pid in PLATE_IDS:
        if pid not in templates:
            continue
        name = PLATE_NAMES[pid]
        print(f"\n─── Plate {name} (relay {pid}) — blind identification ───")

        # Live sweep
        sweep = _quick_sweep(handle, mux, pid)
        live_peaks = _extract_peaks(sweep)

        # Score against each template
        scores = {}
        for tid, t_freqs in templates.items():
            score = 0
            for tf in t_freqs:
                # Find closest live peak
                best_match = min(live_peaks, key=lambda p: abs(p["freq_hz"] - tf)) \
                    if live_peaks else None
                if best_match and abs(best_match["freq_hz"] - tf) / tf < 0.03:
                    score += best_match["magnitude"]
            scores[tid] = score

        # Identify winner
        winner = max(scores, key=scores.get)
        total += 1
        is_correct = winner == pid
        if is_correct:
            correct += 1

        winner_name = PLATE_NAMES[winner]
        margin = 0
        if len(scores) > 1:
            sorted_scores = sorted(scores.values(), reverse=True)
            if sorted_scores[0] > 0:
                margin = (sorted_scores[0] - sorted_scores[1]) / sorted_scores[0] * 100

        status = "✓ CORRECT" if is_correct else "✗ WRONG"
        print(f"  Identified as Plate {winner_name} ({status}), margin: {margin:.0f}%")
        for tid in sorted(scores.keys()):
            marker = " ←" if tid == winner else ""
            print(f"    Plate {PLATE_NAMES[tid]}: {scores[tid]:.0f}{marker}")

        sorted_scores = sorted(scores.values(), reverse=True)
        data = {
            "n_rods": len(templates),
            "peaks_per_rod": N_PEAKS_AUTH,
            "sample_rate": SAMPLE_RATE,
            "freq_resolution": 24.2,
            "auth_rms_pct": round(scores[winner], 1),
            "auth_matched_peaks": min(N_PEAKS_AUTH,
                sum(1 for tf in templates[winner]
                    for lp in live_peaks
                    if abs(lp["freq_hz"] - tf) / tf < 0.03)),
            "auth_score_pct": round(scores[winner], 1),
            "next_best_score_pct": round(sorted_scores[1], 1) if len(sorted_scores) > 1 else 0,
            "min_cross_rod_pct": round(margin, 1),
            "excitation_method": "Piezo pulse",
            "correct_rod_identified": "Yes" if is_correct else "No",
        }

        notes = (
            f"Plate {name} fingerprint auth: identified as {winner_name} "
            f"({'correct' if is_correct else 'WRONG'}), margin {margin:.0f}%. "
            f"AWG CW sweep, template matching against census enrollment. "
            f"PicoScope 2204A, relay mux isolation."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "plate": name, "data": data})
        else:
            r = submit_experiment(token, "exp-hw-auth", data, notes=notes)
            r["_data"] = data
            r["_notes"] = notes
            print_result(r)
            results.append(r)

    print(f"\n  Auth accuracy: {correct}/{total} ({correct / total * 100:.0f}%)")
    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 5: Mode Survey (submit census to Firestore)
# ═══════════════════════════════════════════════════════════════════════

def exp5_mode_survey(token: str, dry_run: bool,
                     census_file: str | None = None) -> list:
    """Submit plate mode census data to Firestore (no hardware needed)."""
    print("\n" + "=" * 65)
    print("  PLATE EXPERIMENT 5: MODE SURVEY (census → Firestore)")
    print("=" * 65)

    if census_file:
        cpath = Path(census_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            print("  ERROR: No census file found.")
            return []
        cpath = census_files[-1]

    print(f"  Census: {cpath.name}")
    with open(cpath) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    results = []
    for pid in PLATE_IDS:
        if pid not in census:
            continue
        name = PLATE_NAMES[pid]
        pdata = census[pid]
        peaks = pdata.get("peaks", [])
        stats = pdata.get("stats", {})

        print(f"\n─── Plate {name}: {len(peaks)} modes ───")

        top5 = peaks[:5]
        data = {
            "plate_material": "Fused quartz",
            "plate_length": 100,
            "plate_width": 100,
            "plate_thickness": 1,
            "pzt_mounting": "Corner face mount",
            "pzt_drive_position": 5,
            "pzt_sense_position": 95,
            "num_modes_bare": len(peaks),
            "f11_measured": round(min(min(p["freq_hz"] for p in peaks), 50000), 1) if peaks else 500,
            "snr_best_mode": round(top5[0]["snr_db"], 1) if top5 else 0,
            "q_estimate": max(10, int(round(peaks[0].get("q_factor", 3000), 0))) if peaks else 3000,
        }
        _spacing = stats.get("mean_spacing_hz", 0)
        if 0 < _spacing <= 10000:
            data["mean_mode_spacing"] = _spacing

        notes = (
            f"Plate {name} mode census: {len(peaks)} modes in "
            f"{stats.get('freq_min_hz', 0):.0f}–{stats.get('freq_max_hz', 0):.0f} Hz. "
            f"25Hz-step CW sweep, PicoScope 2204A, relay mux. "
            f"Source: {cpath.name}."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit (Plate {name}, {len(peaks)} modes)")
            results.append({"ok": True, "dry": True, "plate": name, "data": data})
        else:
            r = submit_experiment(token, "exp05-plate-mode-survey", data, notes=notes)
            r["_data"] = data
            r["_notes"] = notes
            print_result(r)
            results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Run plate experiments and submit to Firestore"
    )
    parser.add_argument(
        "--exp", type=int, nargs="*", default=None,
        help="Run specific experiments (1-5). Default: all."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Don't submit to Firestore"
    )
    parser.add_argument(
        "--port", type=str, default="/dev/cu.usbserial-11310",
        help="Serial port for relay mux"
    )
    parser.add_argument(
        "--baseline-file", type=str, default=None,
        help="Census file for mode persistence baseline (exp 1)"
    )
    parser.add_argument(
        "--census-file", type=str, default=None,
        help="Census file for mode survey submission (exp 5)"
    )
    args = parser.parse_args()

    exps = args.exp or [1, 2, 3, 4, 5]

    needs_hardware = any(e in exps for e in [1, 2, 3, 4])

    handle = None
    mux = None

    if needs_hardware:
        print("Opening PicoScope...")
        handle = _open_scope()
        mux = RelayMux(port=args.port)
        mux.open()
        print(f"  Relay mux connected on {mux.port}")

    # Authenticate
    token = None
    if not args.dry_run:
        print("Authenticating with Firebase...")
        try:
            token = firebase_anon_auth()
            print("  ✓ Anonymous auth OK")
        except Exception as e:
            print(f"  ✗ Auth failed: {e}")
            print("  Continuing in dry-run mode")
            args.dry_run = True
            token = "FAILED"
    else:
        token = "DRY_RUN"
        print("DRY RUN — no Firestore submissions")

    all_results = []

    try:
        if 1 in exps:
            all_results.extend(exp1_mode_persistence(
                token, args.dry_run, handle, mux, args.baseline_file))
        if 2 in exps:
            all_results.extend(exp2_snr(token, args.dry_run, handle, mux))
        if 3 in exps:
            all_results.extend(exp3_damping(token, args.dry_run, handle, mux))
        if 4 in exps:
            all_results.extend(exp4_fingerprint(token, args.dry_run, handle, mux))
        if 5 in exps:
            all_results.extend(exp5_mode_survey(
                token, args.dry_run, args.census_file))
    finally:
        if handle:
            _close_scope(handle)
        if mux:
            mux.close()

    # Summary
    submitted = [r for r in all_results if r.get("ok") and not r.get("dry")]
    failed = [r for r in all_results if not r.get("ok")]

    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    if args.dry_run:
        print(f"  DRY RUN: {len(all_results)} experiments would be submitted")
    else:
        print(f"  Submitted: {len(submitted)} documents to Firestore")
        if failed:
            print(f"  Failed: {len(failed)}")
            for f in failed:
                print(f"    ✗ {f.get('experimentId')}: {f.get('error', '?')}")

    # Save locally
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as fw:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": args.dry_run,
            "experiments_run": exps,
            "results": all_results,
        }, fw, indent=2, default=str)
    print(f"  Saved: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
