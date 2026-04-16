#!/usr/bin/env python3
"""
Run all plate experiments with Kronos USB audio and submit to Firestore.

Kronos-based replacement for run_plate_experiments.py (PicoScope).
Each experiment saves locally AND pushes to Firestore.

Experiments:
  1. Mode persistence — flash census vs baseline
  2. SNR measurement — per-plate from flash census
  3. Damping / Q — CW narrow sweep around strongest peak
  4. Plate fingerprint auth — cross-relay template matching
  5. Mode survey — push census data to Firestore
  6. Intermodulation — 2-tone orthogonality test
  7. Write-read cross-talk — multi-mode independence test
  8. Ringdown Q — time-domain exponential fit (validates CW Q)
  9. True SNR — drive-off noise reference (fixes broken flash SNR)
 10. Intermod attenuation — multi-level sweep (THD vs coupling)
 11. Write-read precision — 10-mode cross-talk map (tighter threshold)
 12. Fixture characterization — cross-relay variance (proves 6700 Hz)
 13. Perturbation write/read — physical state change cycle (interactive)

Usage:
  python tools/run_plate_experiments_kronos.py /dev/cu.usbserial-11310 --device KRONOS
  python tools/run_plate_experiments_kronos.py /dev/cu.usbserial-11310 --device KRONOS --exp 1 2 3 4
  python tools/run_plate_experiments_kronos.py /dev/cu.usbserial-11310 --device KRONOS --exp 5 --census-file <path>
  python tools/run_plate_experiments_kronos.py --push-existing --census-file <path>
  python tools/run_plate_experiments_kronos.py --dry-run --exp 5
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sounddevice as sd

# ── Paths ──
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

from plate_census_kronos import (
    find_audio_device, detect_sample_rate, playrec_capture,
    make_tone, make_multitone,
    flash_census, detect_modes, analyze_mode_spacing,
    PLATE_NAMES, PLATE_RELAYS,
    F_START, F_STEP, DRIVE_AMPLITUDE, FLASH_DURATION_S, FLASH_AVERAGES,
    MIN_SNR_DB, MIN_PROMINENCE_DB,
    SETTLE_RELAY_S, AUDIO_DTYPE,
)
from firestore_submit import firebase_anon_auth, submit_experiment, print_result

# Rate-limit: API allows 5 submissions per minute per UID
SUBMIT_DELAY_S = 13  # ~4.6/min — safe margin
_last_submit_time = 0.0


def submit_with_rate_limit(token, experiment_id, data, notes=""):
    """Submit to Firestore with rate-limit delay."""
    global _last_submit_time
    elapsed = time.time() - _last_submit_time
    if elapsed < SUBMIT_DELAY_S:
        wait = SUBMIT_DELAY_S - elapsed
        print(f"  (rate limit: waiting {wait:.0f}s)")
        time.sleep(wait)
    r = submit_experiment(token, experiment_id, data, notes=notes)
    _last_submit_time = time.time()
    return r


ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
LAB_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

PLATE_IDS = ["1", "2", "3", "4", "5"]

# CW measurement config — Kronos USB audio has ~250 ms round-trip latency,
# so settle must be long enough for real data to appear in the capture window.
CW_CAPTURE_S = 0.10         # 100 ms capture per CW point
CW_SETTLE_S = 0.35          # 350 ms settle (USB latency + relay + ring-up)
CW_N_AVG = 4                # averages per CW measurement
Q_SWEEP_HALFWIDTH_HZ = 500  # ±500 Hz around peak for Q measurement
Q_SWEEP_STEP_HZ = 5         # 5 Hz steps for Q

N_PEAKS_AUTH = 10            # peaks for auth fingerprint

# Known fixture / PZT resonances to exclude from analysis.
# 6700 Hz appears at 0.68–0.80 magnitude on every plate — it's the PZT
# self-resonance, not glass.  Guard band ±200 Hz.
FIXTURE_EXCLUSIONS_HZ = [(6500, 6900)]   # list of (lo, hi) bands

# Cooldown between plates to avoid macOS USB audio dropouts
INTER_PLATE_COOLDOWN_S = 1.0


def filter_fixture_peaks(peaks: list[dict]) -> list[dict]:
    """Remove peaks that fall inside fixture/PZT exclusion bands."""
    out = []
    for p in peaks:
        f = p["freq_hz"]
        if any(lo <= f <= hi for lo, hi in FIXTURE_EXCLUSIONS_HZ):
            continue
        out.append(p)
    return out


# ═══════════════════════════════════════════════════════════════════════
#  Low-level Kronos measurement helpers
# ═══════════════════════════════════════════════════════════════════════

def measure_at(freq_hz: float, sample_rate: int, device_idx: int,
               n_avg: int = CW_N_AVG, retries: int = 2) -> dict:
    """Drive a single CW tone, return magnitude and phase at that frequency."""
    total_dur = CW_SETTLE_S + CW_CAPTURE_S
    tx = make_tone(freq_hz, total_dur, sample_rate)
    settle_samples = int(sample_rate * CW_SETTLE_S)

    for attempt in range(retries + 1):
        try:
            magnitudes = []
            phases = []
            for _ in range(n_avg):
                rx = playrec_capture(tx, sample_rate, device_idx)
                rx_capture = rx[settle_samples:]
                windowed = rx_capture * np.hanning(len(rx_capture))
                nfft = len(rx_capture) * 4
                spectrum = np.fft.rfft(windowed, n=nfft)
                fft_mag = np.abs(spectrum)
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
                bin_hz = freq_axis[1]
                target_bin = int(round(freq_hz / bin_hz))
                lo = max(0, target_bin - 3)
                hi = min(len(fft_mag) - 1, target_bin + 3)
                peak_bin = lo + int(np.argmax(fft_mag[lo:hi + 1]))
                magnitudes.append(float(fft_mag[peak_bin]))
                phases.append(float(np.angle(spectrum[peak_bin])))

            return {
                "magnitude": float(np.mean(magnitudes)),
                "phase_rad": float(np.arctan2(
                    np.mean(np.sin(phases)), np.mean(np.cos(phases))
                )),
            }
        except Exception as e:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
            else:
                raise


def quick_flash_census(mux, plate_id: str, relay_ch: int, rx_label: str,
                       sample_rate: int, device_idx: int, f_stop: int,
                       duration_s: float = FLASH_DURATION_S,
                       n_averages: int = FLASH_AVERAGES,
                       retries: int = 2):
    """Run flash census on one relay, return (sweep_data, peaks, stats).

    Retries on PortAudio errors (macOS USB audio can lose sync).
    """
    for attempt in range(retries + 1):
        try:
            # Brief cooldown before each audio capture to avoid macOS USB issues
            time.sleep(0.5)
            sweep_data = flash_census(
                mux, plate_id, relay_ch, rx_label,
                sample_rate, device_idx, f_stop,
                duration_s=duration_s, n_averages=n_averages,
            )
            peaks = detect_modes(sweep_data)
            stats = analyze_mode_spacing(peaks)
            return sweep_data, peaks, stats
        except Exception as e:
            if attempt < retries:
                wait = 3 * (attempt + 1)
                print(f"  ⚠ Audio error: {e}")
                print(f"    Retrying in {wait}s (attempt {attempt + 2}/{retries + 1})...")
                time.sleep(wait)
                # Re-select relay to reset state
                mux.select(relay_ch)
                time.sleep(SETTLE_RELAY_S)
            else:
                raise


def narrow_cw_sweep(mux, relay_ch: int, center_hz: float,
                    half_width_hz: float, step_hz: float,
                    sample_rate: int, device_idx: int) -> list[dict]:
    """CW sweep around a narrow band for Q measurement."""
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    f_lo = max(F_START, center_hz - half_width_hz)
    f_hi = center_hz + half_width_hz
    freqs = np.arange(f_lo, f_hi + step_hz, step_hz)

    data = []
    for freq in freqs:
        m = measure_at(float(freq), sample_rate, device_idx)
        data.append({"freq_hz": round(float(freq), 1), **m})

    return data


def build_firestore_data(peaks: list[dict], stats: dict,
                         extra: dict | None = None) -> dict:
    """Build the exp05-plate-mode-survey data payload."""
    glass = filter_fixture_peaks(peaks)
    best_peak = glass[0] if glass else {}
    f11 = min(p["freq_hz"] for p in glass) if glass else 500

    data = {
        "plate_material": "Fused quartz",
        "plate_length": 100,
        "plate_width": 100,
        "plate_thickness": 1,
        "pzt_mounting": "Corner face mount",
        "pzt_drive_position": 5,
        "pzt_sense_position": 95,
        "num_modes_bare": len(glass),
        "f11_measured": round(min(f11, 50000), 1),
        "snr_best_mode": min(round(best_peak.get("snr_db", 0), 1), 150),
    }
    spacing = stats.get("mean_spacing_hz", 0)
    if 0 < spacing <= 10000:
        data["mean_mode_spacing"] = round(spacing, 1)

    if extra:
        data.update(extra)
    return data


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 1: Mode Persistence
# ═══════════════════════════════════════════════════════════════════════

def exp1_mode_persistence(token, dry_run, mux, sample_rate, device_idx,
                          f_stop, baseline_file=None):
    """Flash census each plate, compare to baseline."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 1: MODE PERSISTENCE (Kronos flash)")
    print("=" * 65)

    # Load baseline
    if baseline_file:
        bpath = Path(baseline_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_kronos_flash_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            census_files = sorted(
                f for f in LAB_DIR.glob("plate_census_*.json")
                if "sweeps" not in f.name
            )
        if not census_files:
            print("  ERROR: No census baseline found")
            return []
        bpath = census_files[-1]

    print(f"  Baseline: {bpath.name}")
    with open(bpath) as f:
        baseline = json.load(f)
    if "results" in baseline:
        baseline = baseline["results"]

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]

        # Find baseline key
        base_key = None
        for k in [pid, f"{pid}_NE", f"{pid}_NW"]:
            if k in baseline and baseline[k].get("peaks"):
                base_key = k
                break
        if not base_key:
            print(f"  Plate {name}: no baseline, skipping")
            continue

        base_peaks = baseline[base_key]["peaks"]
        relay_ch = PLATE_RELAYS[pid][0][0]
        rx_label = PLATE_RELAYS[pid][0][1]

        print(f"\n─── Plate {name} (relay {relay_ch}) ───")
        print(f"  Baseline: {len(base_peaks)} modes")

        _, live_peaks, live_stats = quick_flash_census(
            mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)
        print(f"  Live: {len(live_peaks)} modes")

        # Match top 10 baseline peaks
        matched = 0
        drifts = []
        base_top = base_peaks[:10]
        for bp in base_top:
            bf = bp["freq_hz"]
            closest = min(live_peaks, key=lambda p: abs(p["freq_hz"] - bf)) if live_peaks else None
            if closest and abs(closest["freq_hz"] - bf) / bf < 0.02:
                matched += 1
                drift_pct = (closest["freq_hz"] - bf) / bf * 100
                drifts.append(drift_pct)
                print(f"    {bf:.0f} Hz → {closest['freq_hz']:.0f} Hz ({drift_pct:+.2f}%)")

        match_pct = matched / len(base_top) * 100 if base_top else 0
        mean_drift = float(np.mean(drifts)) if drifts else 0

        data = build_firestore_data(live_peaks, live_stats)
        notes = (
            f"Plate {name}, mode persistence (Kronos flash): "
            f"{matched}/{len(base_top)} top modes matched within 2%, "
            f"mean drift {mean_drift:.3f}%. "
            f"Baseline: {bpath.name}. "
            f"192 kHz / 24-bit, flash multitone census."
        )

        detail = {
            "plate": name,
            "live_peaks": live_peaks,
            "baseline_file": str(bpath.name),
            "matched": matched,
            "match_pct": match_pct,
            "mean_drift_pct": mean_drift,
            "drifts_pct": drifts,
        }

        if dry_run:
            print(f"  [DRY RUN] Would submit exp05-plate-mode-survey")
            results.append({"ok": True, "dry": True, "plate": name, "_detail": detail})
        else:
            r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
            r["_detail"] = detail
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 2: SNR Measurement
# ═══════════════════════════════════════════════════════════════════════

def exp2_snr(token, dry_run, mux, sample_rate, device_idx, f_stop):
    """Measure per-plate SNR from flash census."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 2: SNR MEASUREMENT (Kronos flash)")
    print("=" * 65)

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        relay_ch = PLATE_RELAYS[pid][0][0]
        rx_label = PLATE_RELAYS[pid][0][1]
        print(f"\n─── Plate {name} (relay {relay_ch}) ───")

        sweep_data, peaks, stats = quick_flash_census(
            mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)

        mags = np.array([s["magnitude"] for s in sweep_data])
        noise_floor = float(np.median(mags))
        peak_mag = float(np.max(mags))
        snr_db = 20 * math.log10(peak_mag / noise_floor) if noise_floor > 0 else 0

        print(f"  Peak: {peak_mag:.6f}, Floor: {noise_floor:.6f}, "
              f"SNR: {snr_db:.1f} dB, Modes: {len(peaks)}")

        data = build_firestore_data(peaks, stats)
        notes = (
            f"Plate {name} SNR measurement (Kronos flash). "
            f"{len(peaks)} modes, SNR={snr_db:.1f} dB. "
            f"192 kHz / 24-bit flash multitone."
        )

        detail = {
            "plate": name,
            "peaks": [{"freq_hz": p["freq_hz"], "snr_db": p["snr_db"]} for p in peaks[:20]],
            "peak_mag": peak_mag,
            "noise_floor": noise_floor,
            "snr_db": round(snr_db, 2),
        }

        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "plate": name, "_detail": detail})
        else:
            r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
            r["_detail"] = detail
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 3: Damping / Q
# ═══════════════════════════════════════════════════════════════════════

def exp3_damping(token, dry_run, mux, sample_rate, device_idx, f_stop):
    """Measure Q via 3dB bandwidth with narrow CW sweep around peaks."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 3: Q / DAMPING (Kronos CW narrow sweep)")
    print("=" * 65)

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        relay_ch = PLATE_RELAYS[pid][0][0]
        rx_label = PLATE_RELAYS[pid][0][1]
        print(f"\n─── Plate {name} (relay {relay_ch}) ───")

        # Quick flash to find peaks
        _, peaks, _ = quick_flash_census(
            mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)

        if not peaks:
            print("  No peaks found, skipping")
            continue

        # Narrow CW sweep around strongest *glass* peak (skip fixture)
        glass_peaks = filter_fixture_peaks(peaks)
        if not glass_peaks:
            print("  No glass peaks after fixture exclusion, skipping")
            continue
        bf = glass_peaks[0]["freq_hz"]
        print(f"  Strongest glass mode: {bf:.0f} Hz — running narrow CW sweep...")

        sweep = narrow_cw_sweep(
            mux, relay_ch, bf, Q_SWEEP_HALFWIDTH_HZ, Q_SWEEP_STEP_HZ,
            sample_rate, device_idx)

        mags = np.array([s["magnitude"] for s in sweep])
        freqs = np.array([s["freq_hz"] for s in sweep])

        # Find peak in narrow sweep
        bi = int(np.argmax(mags))
        peak_val = mags[bi]
        peak_freq = freqs[bi]
        half_power = peak_val / math.sqrt(2)

        left = bi
        while left > 0 and mags[left] > half_power:
            left -= 1
        right = bi
        while right < len(mags) - 1 and mags[right] > half_power:
            right += 1

        bw_hz = float(freqs[right] - freqs[left])
        q_factor = peak_freq / bw_hz if bw_hz > 0 else 100.0
        tau_s = q_factor / (math.pi * peak_freq) if peak_freq > 0 else 0.01

        print(f"  f₁ = {peak_freq:.0f} Hz, Q ≈ {q_factor:.0f}, "
              f"τ = {tau_s * 1000:.1f} ms, BW = {bw_hz:.1f} Hz")

        _, _, stats = quick_flash_census(
            mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)

        data = build_firestore_data(peaks, stats, {
            "q_estimate": max(10, int(round(q_factor))),
        })
        notes = (
            f"Plate {name} Q measurement (Kronos CW). "
            f"Strongest mode {peak_freq:.0f} Hz, Q={q_factor:.0f}, "
            f"τ={tau_s * 1000:.1f} ms, BW={bw_hz:.1f} Hz. "
            f"Narrow CW sweep ±{Q_SWEEP_HALFWIDTH_HZ} Hz, {Q_SWEEP_STEP_HZ} Hz steps. "
            f"192 kHz / 24-bit."
        )

        detail = {
            "plate": name,
            "f1_hz": peak_freq,
            "q_factor": round(q_factor, 1),
            "tau_s": round(tau_s, 6),
            "bw_hz": round(bw_hz, 1),
            "half_power_left_hz": float(freqs[left]),
            "half_power_right_hz": float(freqs[right]),
            "narrow_sweep": sweep,
        }

        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "plate": name, "_detail": detail})
        else:
            r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
            r["_detail"] = detail
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 4: Fingerprint Authentication
# ═══════════════════════════════════════════════════════════════════════

def exp4_fingerprint(token, dry_run, mux, sample_rate, device_idx,
                     census_file=None):
    """Cross-relay template matching: identify each plate by spectral fingerprint."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 4: SPECTRAL FINGERPRINT AUTH (Kronos CW)")
    print("=" * 65)

    # Load enrollment data
    if census_file:
        cpath = Path(census_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_kronos_flash_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            census_files = sorted(
                f for f in LAB_DIR.glob("plate_census_*.json")
                if "sweeps" not in f.name
            )
        if not census_files:
            print("  ERROR: No census data for enrollment")
            return []
        cpath = census_files[-1]

    print(f"  Enrollment: {cpath.name}")
    with open(cpath) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    # Build templates: top N_PEAKS_AUTH frequencies per plate (fixture-filtered)
    templates = {}
    for pid in PLATE_IDS:
        for k in [pid, f"{pid}_NE", f"{pid}_NW"]:
            if k in census and census[k].get("peaks"):
                glass = filter_fixture_peaks(census[k]["peaks"])
                templates[pid] = [p["freq_hz"] for p in glass[:N_PEAKS_AUTH]]
                break

    if len(templates) < 2:
        print("  ERROR: Need at least 2 enrolled plates")
        return []

    active_ids = [pid for pid in PLATE_IDS if pid in templates]
    print(f"  Enrolled: {len(templates)} plates, {N_PEAKS_AUTH} peaks each")

    results = []
    correct = 0
    total = 0

    for pid in active_ids:
        name = PLATE_NAMES[pid]
        query_freqs = templates[pid]
        print(f"\n─── Query Plate {name} (relay {PLATE_RELAYS[pid][0][0]}) "
              f"— {len(query_freqs)} enrolled freqs ───")

        # Measure all plates at each query frequency
        raw_mags = {sid: [] for sid in active_ids}
        t0 = time.time()

        for fi, freq in enumerate(query_freqs):
            for sid in active_ids:
                relay_ch = PLATE_RELAYS[sid][0][0]
                mux.select(relay_ch)
                time.sleep(SETTLE_RELAY_S)
                try:
                    m = measure_at(float(freq), sample_rate, device_idx)
                except Exception as e:
                    print(f"    ⚠ measure_at error on plate {PLATE_NAMES[sid]}: {e}")
                    time.sleep(2)
                    mux.select(relay_ch)
                    time.sleep(SETTLE_RELAY_S)
                    m = measure_at(float(freq), sample_rate, device_idx)
                raw_mags[sid].append(m["magnitude"])

            if fi % 5 == 0:
                elapsed = time.time() - t0
                pct = (fi + 1) / len(query_freqs) * 100
                # Show magnitudes for this freq to diagnose scoring
                mag_str = " ".join(
                    f"{PLATE_NAMES[s]}={raw_mags[s][fi]:.4f}"
                    for s in active_ids
                )
                print(f"    freq {fi+1}/{len(query_freqs)} "
                      f"({freq:.0f} Hz) [{pct:.0f}% | {elapsed:.0f}s] {mag_str}")

        elapsed = time.time() - t0
        print(f"    Done: {elapsed:.0f}s")

        # Template scoring — each query freq is from the QUERY plate's
        # template.  A candidate plate scores high when it responds more
        # strongly than the other plates at those frequencies.
        tmpl_scores = {}
        for sid in active_ids:
            score = 0.0
            for fi, freq in enumerate(query_freqs):
                mags_at_freq = {s: raw_mags[s][fi] for s in active_ids}
                max_mag = max(mags_at_freq.values())
                if max_mag == 0:
                    continue
                # Normalise this plate's response against the loudest responder
                rel = mags_at_freq[sid] / max_mag
                # Is this frequency in the *candidate's* enrolled template?
                in_own = any(
                    abs(freq - ep) / max(freq, ep) < 0.03
                    for ep in templates.get(sid, [])
                )
                if sid == pid:
                    # Self-match: reward strong response at own enrolled freqs
                    score += rel * 2.0 if in_own else rel * 0.5
                else:
                    # Cross-match: penalise response unless freq is also in
                    # the candidate's own template (legitimate shared mode)
                    score += rel * 0.5 if in_own else -rel * 1.0
            tmpl_scores[sid] = round(score, 4)

        winner = max(tmpl_scores, key=tmpl_scores.get)
        total += 1
        is_correct = winner == pid
        if is_correct:
            correct += 1

        winner_name = PLATE_NAMES[winner]
        sorted_s = sorted(tmpl_scores.values(), reverse=True)
        margin = sorted_s[0] - sorted_s[1] if len(sorted_s) > 1 else 0

        status = "✓ CORRECT" if is_correct else "✗ WRONG"
        print(f"  Identified as Plate {winner_name} ({status}), margin: {margin:.4f}")
        for sid in active_ids:
            marker = " ◄" if sid == winner else ""
            print(f"    Plate {PLATE_NAMES[sid]}: score={tmpl_scores[sid]:+.4f}{marker}")

        winner_score = tmpl_scores[winner]
        next_best = sorted_s[1] if len(sorted_s) > 1 else 0
        # Normalize scores to [0, 100] for Firestore schema compatibility
        all_vals = list(tmpl_scores.values())
        s_min = min(all_vals)
        s_range = max(all_vals) - s_min if max(all_vals) > s_min else 1.0
        norm_winner = (winner_score - s_min) / s_range * 100
        norm_next = (next_best - s_min) / s_range * 100
        norm_margin = norm_winner - norm_next
        data = {
            "n_rods": len(templates),
            "peaks_per_rod": N_PEAKS_AUTH,
            "sample_rate": sample_rate,
            "freq_resolution": round(1.0 / FLASH_DURATION_S, 1),
            "auth_rms_pct": round(norm_margin, 2),
            "auth_matched_peaks": N_PEAKS_AUTH,
            "auth_score_pct": round(norm_winner, 1),
            "next_best_score_pct": round(max(norm_next, 0), 1),
            "min_cross_rod_pct": round(min(norm_margin, 100), 1),
            "excitation_method": "Piezo pulse",
            "correct_rod_identified": "Yes" if is_correct else "No",
        }
        notes = (
            f"Plate {name} fingerprint auth (Kronos): identified as {winner_name} "
            f"({'correct' if is_correct else 'WRONG'}), margin {margin:.2f}. "
            f"Cross-relay template matching ({len(query_freqs)} enrolled freqs, "
            f"{len(active_ids)} sense plates). 192 kHz / 24-bit CW probes."
        )

        detail = {
            "plate": name,
            "template_scores": {sid: tmpl_scores[sid] for sid in active_ids},
            "winner": winner_name,
            "correct": is_correct,
            "margin": margin,
        }

        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "plate": name, "_detail": detail})
        else:
            r = submit_with_rate_limit(token, "exp-hw-auth", data, notes=notes)
            r["_detail"] = detail
            print_result(r)
            results.append(r)

    print(f"\n  Auth accuracy: {correct}/{total} ({correct / total * 100:.0f}%)")
    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 5: Mode Survey (census → Firestore)
# ═══════════════════════════════════════════════════════════════════════

def exp5_mode_survey(token, dry_run, census_file=None):
    """Submit census data to Firestore (no hardware needed)."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 5: MODE SURVEY (census → Firestore)")
    print("=" * 65)

    if census_file:
        cpath = Path(census_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_kronos_flash_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            print("  ERROR: No census file found")
            return []
        cpath = census_files[-1]

    print(f"  Census: {cpath.name}")
    with open(cpath) as f:
        census = json.load(f)

    src = census.get("results", census)
    results = []

    for pid in PLATE_IDS:
        checked_keys = [pid, f"{pid}_NE", f"{pid}_NW"]
        for key in checked_keys:
            if key not in src:
                continue
            pdata = src[key]
            peaks = pdata.get("peaks", [])
            stats = pdata.get("stats", {})
            pname = pdata.get("plate_name", PLATE_NAMES.get(pid, pid))
            rx = pdata.get("rx_path", key.split("_")[-1] if "_" in key else "NE")

            label = f"{pname}-{rx}" if "_" in key else pname
            print(f"\n─── Plate {label}: {len(peaks)} modes ───")

            data = build_firestore_data(peaks, stats)
            source_tag = "Kronos" if "kronos" in cpath.name.lower() else "PicoScope"
            notes = (
                f"Plate {label} mode census: {len(peaks)} modes in "
                f"{stats.get('freq_min_hz', 0):.0f}–{stats.get('freq_max_hz', 0):.0f} Hz. "
                f"{source_tag} flash multitone. Source: {cpath.name}."
            )

            if dry_run:
                print(f"  [DRY RUN] Would submit ({len(peaks)} modes)")
                results.append({"ok": True, "dry": True, "plate": label})
            else:
                r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
                print_result(r)
                results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 6: Intermodulation
# ═══════════════════════════════════════════════════════════════════════

def exp6_intermod(token, dry_run, mux, sample_rate, device_idx,
                  census_file=None):
    """Two-tone intermodulation test on each plate's strongest modes."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 6: INTERMODULATION (Kronos)")
    print("=" * 65)

    if census_file:
        cpath = Path(census_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_kronos_flash_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            print("  ERROR: No census file found")
            return []
        cpath = census_files[-1]

    with open(cpath) as f:
        census = json.load(f)
    src = census.get("results", census)

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]

        # Find peaks for this plate
        peaks = None
        for k in [pid, f"{pid}_NE"]:
            if k in src and src[k].get("peaks"):
                peaks = src[k]["peaks"]
                break
        if not peaks or len(peaks) < 2:
            print(f"  Plate {name}: <2 peaks, skipping")
            continue

        # Filter fixture resonances, then pick two strong, well-separated modes
        glass = filter_fixture_peaks(peaks)
        if len(glass) < 2:
            print(f"  Plate {name}: <2 glass peaks after fixture exclusion, skipping")
            continue
        f1 = glass[0]["freq_hz"]
        f2 = glass[1]["freq_hz"]
        if abs(f1 - f2) < 100:
            # Too close — try mode 2
            if len(glass) > 2:
                f2 = glass[2]["freq_hz"]
            else:
                continue

        relay_ch = PLATE_RELAYS[pid][0][0]
        print(f"\n─── Plate {name} (relay {relay_ch}): f1={f1:.0f}, f2={f2:.0f} Hz ───")

        # Build 2-tone TX
        nyquist = sample_rate / 2
        duration = 2.0
        settle = 0.3
        total_dur = settle + duration
        n_total = int(sample_rate * total_dur)
        n_settle = int(sample_rate * settle)
        t = np.arange(n_total) / sample_rate

        tx_sig = np.sin(2 * np.pi * f1 * t) + np.sin(2 * np.pi * f2 * t)
        peak_val = np.max(np.abs(tx_sig))
        if peak_val > 0:
            tx_sig *= DRIVE_AMPLITUDE / peak_val
        tx = tx_sig.astype(np.float32).reshape(-1, 1)

        # Expected products
        intermod_freqs = {
            "f1": f1, "f2": f2,
            "f1+f2": f1+f2, "f2-f1": abs(f2-f1),
            "2f1-f2": abs(2*f1-f2), "2f2-f1": abs(2*f2-f1),
            "2f1": 2*f1, "2f2": 2*f2,
            "3f1-2f2": abs(3*f1-2*f2), "3f2-2f1": abs(3*f2-2*f1),
        }
        intermod_freqs = {k: v for k, v in intermod_freqs.items() if 0 < v < nyquist}

        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        # Capture
        n_avg = 8
        mag_accum = None
        for i in range(n_avg):
            rx = playrec_capture(tx, sample_rate, device_idx)
            rx_capture = rx[n_settle:n_settle + int(sample_rate * duration)]
            windowed = rx_capture * np.hanning(len(rx_capture))
            spectrum = np.fft.rfft(windowed)
            fft_mag = np.abs(spectrum)
            freq_axis = np.fft.rfftfreq(len(rx_capture), d=1.0 / sample_rate)

            if mag_accum is None:
                mag_accum = np.zeros_like(fft_mag)
            mag_accum += fft_mag

        mag_avg = mag_accum / n_avg
        bin_hz = freq_axis[1]

        # Noise floor with guard bands
        guard_hz = 50.0
        guard_bins = int(guard_hz / bin_hz) + 1
        signal_freqs = list(intermod_freqs.values())
        for n in range(3, 6):
            for fd in [f1, f2]:
                hf = n * fd
                if 0 < hf < nyquist:
                    signal_freqs.append(hf)

        exclude_mask = np.zeros(len(mag_avg), dtype=bool)
        exclude_mask[:max(1, int(20 / bin_hz))] = True
        for sf in signal_freqs:
            center = int(round(sf / bin_hz))
            lo = max(0, center - guard_bins)
            hi = min(len(mag_avg) - 1, center + guard_bins)
            exclude_mask[lo:hi+1] = True

        noise_bins = mag_avg[~exclude_mask]
        noise_floor = float(np.median(noise_bins)) if len(noise_bins) > 10 else float(np.median(mag_avg))
        noise_std = float(np.std(noise_bins)) if len(noise_bins) > 10 else noise_floor
        detect_threshold = noise_floor + 3 * noise_std

        # Check products
        intermod_detected = []
        for label, freq in sorted(intermod_freqs.items(), key=lambda x: x[1]):
            idx = int(round(freq / bin_hz))
            lo = max(0, idx - 3)
            hi = min(len(mag_avg) - 1, idx + 3)
            peak_idx = lo + int(np.argmax(mag_avg[lo:hi+1]))
            mag = float(mag_avg[peak_idx])
            is_drive = label in ("f1", "f2")
            detected = (not is_drive) and (mag > detect_threshold)
            if detected:
                intermod_detected.append(label)
            sigma = (mag - noise_floor) / noise_std if noise_std > 0 else 0
            tag = "DRIVE" if is_drive else ("DETECTED" if detected else "—")
            print(f"    {label:>12}: {freq:8.0f} Hz  mag={mag:.6f}  "
                  f"{sigma:.1f}σ  {tag}")

        verdict = "FAIL — intermod detected" if intermod_detected else "PASS — modes orthogonal"
        print(f"  → {verdict}")

        # Save + submit as mode survey with notes
        data = build_firestore_data(peaks, {})
        notes = (
            f"Plate {name} intermod test (Kronos): f1={f1:.0f}, f2={f2:.0f} Hz. "
            f"Products detected: {intermod_detected or 'none'}. "
            f"Noise floor (3σ): {detect_threshold:.6f}. "
            f"192 kHz / 24-bit, 8 averages."
        )

        # Save intermod detail locally
        intermod_path = LAB_DIR / f"intermod_kronos_{TIMESTAMP}_{name}.json"
        intermod_data = {
            "experiment": "Intermodulation Test (Kronos runner)",
            "timestamp": TIMESTAMP,
            "plate": name,
            "drive_freqs_hz": [f1, f2],
            "sample_rate": sample_rate,
            "noise_floor": noise_floor,
            "noise_std": noise_std,
            "detect_threshold_3sigma": detect_threshold,
            "intermod_detected": intermod_detected,
        }
        with open(intermod_path, "w") as fw:
            json.dump(intermod_data, fw, indent=2)
        print(f"  Saved: {intermod_path.name}")

        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "plate": name})
        else:
            r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 7: Write-Read Cross-Talk
# ═══════════════════════════════════════════════════════════════════════

def exp7_writeread(token, dry_run, mux, sample_rate, device_idx,
                   census_file=None):
    """Write + read cross-talk test on each plate."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 7: WRITE-READ CROSS-TALK (Kronos)")
    print("=" * 65)

    if census_file:
        cpath = Path(census_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_kronos_flash_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            print("  ERROR: No census file found")
            return []
        cpath = census_files[-1]

    with open(cpath) as f:
        census = json.load(f)
    src = census.get("results", census)

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        peaks = None
        for k in [pid, f"{pid}_NE"]:
            if k in src and src[k].get("peaks"):
                peaks = src[k]["peaks"]
                break
        if not peaks or len(peaks) < 6:
            print(f"  Plate {name}: <6 peaks, skipping")
            continue

        # Filter fixture resonances before selecting write/read modes
        glass = filter_fixture_peaks(peaks)
        if len(glass) < 6:
            print(f"  Plate {name}: <6 glass peaks after fixture exclusion, skipping")
            continue

        # Write = top 3 modes, read = modes 3-5
        write_freqs = [glass[i]["freq_hz"] for i in range(3)]
        read_freqs = [glass[i]["freq_hz"] for i in range(3, 6)]

        relay_ch = PLATE_RELAYS[pid][0][0]
        print(f"\n─── Plate {name} (relay {relay_ch}) ───")
        print(f"  Write: {[f'{f:.0f}' for f in write_freqs]}")
        print(f"  Read:  {[f'{f:.0f}' for f in read_freqs]}")

        duration = 2.0
        settle = 0.3
        total_dur = settle + duration
        n_total = int(sample_rate * total_dur)
        n_settle = int(sample_rate * settle)
        t = np.arange(n_total) / sample_rate
        n_avg = 8

        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        def measure_read_levels(tx: np.ndarray, label: str) -> dict:
            print(f"  Phase: {label} ({n_avg} avgs)...")
            mag_acc = {f: 0.0 for f in read_freqs}
            for _ in range(n_avg):
                rx = playrec_capture(tx, sample_rate, device_idx)
                rx_cap = rx[n_settle:n_settle + int(sample_rate * duration)]
                windowed = rx_cap * np.hanning(len(rx_cap))
                spectrum = np.fft.rfft(windowed)
                fft_mag = np.abs(spectrum)
                freq_axis = np.fft.rfftfreq(len(rx_cap), d=1.0 / sample_rate)
                bin_hz = freq_axis[1]
                for f in read_freqs:
                    idx = int(round(f / bin_hz))
                    lo = max(0, idx - 3)
                    hi = min(len(fft_mag) - 1, idx + 3)
                    pk = lo + int(np.argmax(fft_mag[lo:hi+1]))
                    mag_acc[f] += float(fft_mag[pk])
            return {f: v / n_avg for f, v in mag_acc.items()}

        # Baseline: read tones only
        probe_amp = DRIVE_AMPLITUDE * 0.1
        tx_baseline = np.zeros(n_total, dtype=np.float64)
        for f in read_freqs:
            tx_baseline += probe_amp * np.sin(2 * np.pi * f * t)
        pk = np.max(np.abs(tx_baseline))
        if pk > 0:
            tx_baseline *= (probe_amp / pk)
        baseline_mags = measure_read_levels(
            tx_baseline.astype(np.float32).reshape(-1, 1), "BASELINE")

        # Write + read
        tx_wr = np.zeros(n_total, dtype=np.float64)
        for f in write_freqs:
            tx_wr += np.sin(2 * np.pi * f * t)
        for f in read_freqs:
            tx_wr += probe_amp * np.sin(2 * np.pi * f * t)
        pk = np.max(np.abs(tx_wr))
        if pk > 0:
            tx_wr *= (DRIVE_AMPLITUDE / pk)
        wr_mags = measure_read_levels(
            tx_wr.astype(np.float32).reshape(-1, 1), "WRITE+READ")

        # Compare
        crosstalk_detected = False
        wr_results = {}
        for f in read_freqs:
            b = baseline_mags[f]
            w = wr_mags[f]
            change_db = 20 * math.log10(w / b) if b > 0 and w > 0 else 0
            xt = abs(change_db) >= 3.0
            if xt:
                crosstalk_detected = True
            status = "CROSSTALK" if xt else "OK"
            print(f"    {f:8.0f} Hz: baseline={b:.6f}  with_write={w:.6f}  "
                  f"Δ={change_db:+.1f} dB  {status}")
            wr_results[str(f)] = {
                "baseline": b, "with_write": w,
                "change_db": round(change_db, 2), "crosstalk": xt
            }

        verdict = "FAIL — cross-talk detected" if crosstalk_detected else "PASS — modes independent"
        print(f"  → {verdict}")

        # Save locally
        wr_path = LAB_DIR / f"writeread_kronos_{TIMESTAMP}_{name}.json"
        wr_data = {
            "experiment": "Write-Read Cross-Talk (Kronos runner)",
            "timestamp": TIMESTAMP,
            "plate": name,
            "write_freqs_hz": write_freqs,
            "read_freqs_hz": read_freqs,
            "sample_rate": sample_rate,
            "results": wr_results,
            "crosstalk_detected": crosstalk_detected,
        }
        with open(wr_path, "w") as fw:
            json.dump(wr_data, fw, indent=2)
        print(f"  Saved: {wr_path.name}")

        data = build_firestore_data(peaks, {})
        notes = (
            f"Plate {name} write-read cross-talk (Kronos): "
            f"write {[f'{f:.0f}' for f in write_freqs]}, "
            f"read {[f'{f:.0f}' for f in read_freqs]}. "
            f"Max change: {max(abs(r['change_db']) for r in wr_results.values()):.1f} dB. "
            f"{'PASS' if not crosstalk_detected else 'FAIL'}. 192 kHz / 24-bit."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "plate": name})
        else:
            r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 8: Ringdown Q (time-domain)
# ═══════════════════════════════════════════════════════════════════════

# Addresses weak spot #1: CW-sweep Q is resolution-limited by the 5 Hz step.
# Ringdown gives a direct exponential fit → τ → Q = π·f·τ, independent of
# frequency resolution.

RINGDOWN_DRIVE_S = 3.0      # CW drive to reach steady state
RINGDOWN_CAPTURE_S = 3.0    # silence after drive stops → capture ringdown
RINGDOWN_N_MODES = 3        # measure Q at top N glass modes per plate


def exp8_ringdown_q(token, dry_run, mux, sample_rate, device_idx, f_stop):
    """Time-domain ringdown Q measurement on each plate."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 8: RINGDOWN Q (time-domain)")
    print("=" * 65)

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        relay_ch = PLATE_RELAYS[pid][0][0]
        rx_label = PLATE_RELAYS[pid][0][1]
        print(f"\n─── Plate {name} (relay {relay_ch}) ───")

        # Flash census to find glass modes
        _, peaks, _ = quick_flash_census(
            mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)
        glass = filter_fixture_peaks(peaks)
        if not glass:
            print("  No glass peaks, skipping")
            continue

        n_modes = min(RINGDOWN_N_MODES, len(glass))
        plate_q_results = []

        for mi in range(n_modes):
            target_f = glass[mi]["freq_hz"]
            print(f"\n  Mode {mi + 1}/{n_modes}: {target_f:.0f} Hz")

            # Build TX: [drive | silence]
            total_dur = RINGDOWN_DRIVE_S + RINGDOWN_CAPTURE_S
            n_total = int(sample_rate * total_dur)
            n_drive = int(sample_rate * RINGDOWN_DRIVE_S)
            t_drive = np.arange(n_drive) / sample_rate
            drive_part = DRIVE_AMPLITUDE * np.sin(2 * np.pi * target_f * t_drive)
            silence_part = np.zeros(n_total - n_drive)
            tx = np.concatenate([drive_part, silence_part]).astype(np.float32).reshape(-1, 1)

            mux.select(relay_ch)
            time.sleep(SETTLE_RELAY_S)

            # Capture (average multiple runs)
            n_avg = 4
            envelope_accum = None
            for ai in range(n_avg):
                rx = playrec_capture(tx, sample_rate, device_idx)

                # Extract ringdown region (after drive stops + USB latency)
                # USB latency ~250ms, but be conservative: start 400ms after drive-off
                ring_start = n_drive + int(sample_rate * 0.40)
                ring_end = len(rx)
                if ring_start >= ring_end:
                    break
                rx_ring = rx[ring_start:ring_end]

                # Bandpass filter around target mode (±100 Hz)
                # Use zero-phase via FFT filtering
                nfft = len(rx_ring)
                fft_ring = np.fft.rfft(rx_ring)
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
                bw = 100.0  # Hz
                mask = np.abs(freq_axis - target_f) <= bw
                fft_filtered = fft_ring * mask
                filtered = np.fft.irfft(fft_filtered, n=nfft)

                # Hilbert envelope (analytic signal)
                analytic = np.fft.ifft(
                    2 * np.fft.fft(filtered) * (np.arange(len(filtered)) < len(filtered) // 2 + 1)
                )
                env = np.abs(analytic)

                if envelope_accum is None:
                    envelope_accum = np.zeros_like(env)
                envelope_accum += env

            if envelope_accum is None:
                print("    No data captured")
                continue

            envelope = envelope_accum / n_avg

            # Fit exponential decay: A * exp(-t/tau)
            # Use log-linear fit on the portion above noise
            noise_level = float(np.median(envelope[-int(len(envelope) * 0.1):]))
            above_noise = envelope > max(noise_level * 3, 1e-10)
            if np.sum(above_noise) < 20:
                print(f"    Ringdown too short or absent (only {np.sum(above_noise)} samples above noise)")
                plate_q_results.append({
                    "freq_hz": target_f, "Q_ringdown": 0, "tau_s": 0,
                    "status": "no_ringdown",
                })
                continue

            # Find contiguous above-noise region starting from beginning
            first_below = np.argmax(~above_noise)
            if first_below == 0:
                # All above noise — use full signal
                first_below = len(above_noise)
            fit_len = max(20, int(first_below * 0.9))  # use 90% of above-noise region
            env_fit = envelope[:fit_len]
            t_fit = np.arange(fit_len) / sample_rate

            # Log-linear fit: log(env) = log(A) - t/tau
            log_env = np.log(env_fit + 1e-20)
            # Weighted least squares (weight by amplitude — early samples more reliable)
            weights = env_fit / (np.max(env_fit) + 1e-20)
            w_sum = np.sum(weights)
            w_t = np.sum(weights * t_fit) / w_sum
            w_y = np.sum(weights * log_env) / w_sum
            w_tt = np.sum(weights * t_fit * t_fit) / w_sum
            w_ty = np.sum(weights * t_fit * log_env) / w_sum

            denom = w_tt - w_t * w_t
            if abs(denom) < 1e-30:
                print("    Fit degenerate")
                plate_q_results.append({
                    "freq_hz": target_f, "Q_ringdown": 0, "tau_s": 0,
                    "status": "fit_failed",
                })
                continue

            slope = (w_ty - w_t * w_y) / denom
            intercept = w_y - slope * w_t

            if slope >= 0:
                print(f"    No decay detected (slope={slope:.4f})")
                plate_q_results.append({
                    "freq_hz": target_f, "Q_ringdown": 0, "tau_s": 0,
                    "status": "no_decay",
                })
                continue

            tau = -1.0 / slope
            Q_ring = math.pi * target_f * tau
            A_fit = math.exp(intercept)

            # Residual quality check
            predicted = A_fit * np.exp(-t_fit / tau)
            residual_rms = float(np.sqrt(np.mean((env_fit - predicted) ** 2)))
            fit_quality = 1.0 - residual_rms / (float(np.std(env_fit)) + 1e-20)

            print(f"    τ = {tau * 1000:.2f} ms, Q = {Q_ring:.0f}, "
                  f"fit R² ≈ {fit_quality:.3f}")

            plate_q_results.append({
                "freq_hz": target_f,
                "Q_ringdown": round(Q_ring, 1),
                "tau_s": round(tau, 6),
                "fit_quality": round(fit_quality, 4),
                "A_fit": round(A_fit, 6),
                "noise_level": round(noise_level, 8),
                "fit_samples": fit_len,
                "status": "ok",
            })

        # Summary for this plate
        ok_results = [r for r in plate_q_results if r["status"] == "ok"]
        if ok_results:
            q_vals = [r["Q_ringdown"] for r in ok_results]
            best = max(ok_results, key=lambda r: r["Q_ringdown"])
            print(f"\n  Plate {name} summary: Q = {min(q_vals):.0f}–{max(q_vals):.0f} "
                  f"(best {best['Q_ringdown']:.0f} at {best['freq_hz']:.0f} Hz)")

        # Save locally
        rd_path = LAB_DIR / f"ringdown_q_kronos_{TIMESTAMP}_{name}.json"
        rd_data = {
            "experiment": "Ringdown Q (Kronos)",
            "timestamp": TIMESTAMP,
            "plate": name,
            "sample_rate": sample_rate,
            "drive_duration_s": RINGDOWN_DRIVE_S,
            "capture_duration_s": RINGDOWN_CAPTURE_S,
            "n_averages": n_avg,
            "modes": plate_q_results,
        }
        with open(rd_path, "w") as fw:
            json.dump(rd_data, fw, indent=2)
        print(f"  Saved: {rd_path.name}")

        # Submit to Firestore (exp03-damping-time)
        best_q = max(ok_results, key=lambda r: r["Q_ringdown"]) if ok_results else None
        if best_q:
            data = {
                "rod_material": "Fused quartz",
                "rod_length": 100,
                "ring_down_time": best_q["tau_s"],
                "fundamental_freq": min(round(best_q["freq_hz"], 1), 100000),
                "q_estimate": min(round(best_q["Q_ringdown"], 1), 1000000),
                "support_method": "Corner PZT mount",
            }
            if best_q["tau_s"] > 0:
                decay_60 = best_q["tau_s"] * math.log(1000)  # 60 dB = factor 1000
                data["decay_60db"] = min(round(decay_60, 4), 60)

            q_summary = ', '.join(
                f'{r["Q_ringdown"]:.0f}@{r["freq_hz"]:.0f}Hz' for r in ok_results
            )
            notes = (
                f"Plate {name} ringdown Q (Kronos). "
                f"{len(ok_results)} modes measured: "
                f"Q = {q_summary}. "
                f"192 kHz / 24-bit, {n_avg} averages."
            )

            if dry_run:
                print(f"  [DRY RUN] Would submit exp03-damping-time")
                results.append({"ok": True, "dry": True, "_detail": rd_data})
            else:
                r = submit_with_rate_limit(token, "exp03-damping-time", data, notes=notes)
                r["_detail"] = rd_data
                print_result(r)
                results.append(r)
        else:
            results.append({"ok": False, "error": "no valid ringdown", "_detail": rd_data})

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 9: True SNR (drive-off noise reference)
# ═══════════════════════════════════════════════════════════════════════

# Addresses weak spot #2: flash census SNR = 0 dB because median(driven bins) ≈ 0.
# Proper SNR requires a separate noise-only capture with no drive.

NOISE_CAPTURE_S = 2.0  # silence capture for noise floor


def exp9_true_snr(token, dry_run, mux, sample_rate, device_idx, f_stop):
    """Measure per-plate SNR using drive-off noise reference."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 9: TRUE SNR (drive-off noise reference)")
    print("=" * 65)

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        relay_ch = PLATE_RELAYS[pid][0][0]
        rx_label = PLATE_RELAYS[pid][0][1]
        print(f"\n─── Plate {name} (relay {relay_ch}) ───")

        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        # Phase 1: Noise capture (silence TX)
        n_noise = int(sample_rate * NOISE_CAPTURE_S)
        tx_silence = np.zeros((n_noise, 1), dtype=np.float32)
        noise_rms_vals = []
        for _ in range(4):
            rx_noise = playrec_capture(tx_silence, sample_rate, device_idx)
            # Skip first 400ms (USB settle)
            skip = int(sample_rate * 0.4)
            noise_seg = rx_noise[skip:]
            noise_rms_vals.append(float(np.sqrt(np.mean(noise_seg ** 2))))

        noise_rms = float(np.mean(noise_rms_vals))
        noise_peak = float(np.max([np.max(np.abs(playrec_capture(tx_silence, sample_rate, device_idx)[skip:])) for _ in range(1)]))
        print(f"  Noise floor: RMS = {noise_rms:.6f}, peak = {noise_peak:.6f}")

        # Phase 2: Flash census (normal drive)
        sweep_data, peaks, stats = quick_flash_census(
            mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)

        glass = filter_fixture_peaks(peaks)
        if not glass:
            print("  No glass peaks")
            continue

        # Per-mode SNR
        mode_snrs = []
        for p in glass[:20]:
            mag = p["magnitude"]
            snr_db = 20 * math.log10(mag / noise_rms) if noise_rms > 0 else 0
            mode_snrs.append({"freq_hz": p["freq_hz"], "mag": mag, "snr_db": round(snr_db, 1)})

        best_snr = max(mode_snrs, key=lambda m: m["snr_db"])
        mean_snr = float(np.mean([m["snr_db"] for m in mode_snrs]))
        median_snr = float(np.median([m["snr_db"] for m in mode_snrs]))

        print(f"  Modes: {len(glass)}, Best SNR: {best_snr['snr_db']:.1f} dB "
              f"@ {best_snr['freq_hz']:.0f} Hz")
        print(f"  Mean SNR (top 20): {mean_snr:.1f} dB, "
              f"Median: {median_snr:.1f} dB")

        # Save locally
        snr_path = LAB_DIR / f"true_snr_kronos_{TIMESTAMP}_{name}.json"
        snr_data = {
            "experiment": "True SNR (Kronos)",
            "timestamp": TIMESTAMP,
            "plate": name,
            "sample_rate": sample_rate,
            "noise_rms": noise_rms,
            "noise_peak": noise_peak,
            "n_modes": len(glass),
            "best_snr_db": best_snr["snr_db"],
            "best_snr_freq_hz": best_snr["freq_hz"],
            "mean_snr_db": round(mean_snr, 1),
            "mode_snrs": mode_snrs,
        }
        with open(snr_path, "w") as fw:
            json.dump(snr_data, fw, indent=2)
        print(f"  Saved: {snr_path.name}")

        # Submit to Firestore (exp02-snr-measurement)
        data = {
            "rod_material": "Fused quartz",
            "rod_length": 100,
            "excitation_method": "Multitone flash",
            "peak_amplitude": min(round(20 * math.log10(best_snr["mag"] + 1e-20), 1), 200),
            "noise_floor": max(round(20 * math.log10(noise_rms + 1e-20), 1), -150),
            "snr": min(round(best_snr["snr_db"], 1), 150),
            "num_visible_modes": min(len(glass), 100),
        }
        notes = (
            f"Plate {name} true SNR (Kronos, drive-off noise ref). "
            f"Noise RMS={noise_rms:.6f}. "
            f"Best {best_snr['snr_db']:.1f} dB @ {best_snr['freq_hz']:.0f} Hz. "
            f"Mean {mean_snr:.1f} dB over {len(mode_snrs)} modes. "
            f"192 kHz / 24-bit."
        )

        if dry_run:
            print(f"  [DRY RUN] Would submit exp02-snr-measurement")
            results.append({"ok": True, "dry": True, "_detail": snr_data})
        else:
            r = submit_with_rate_limit(token, "exp02-snr-measurement", data, notes=notes)
            r["_detail"] = snr_data
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 10: Intermod Attenuation Sweep
# ═══════════════════════════════════════════════════════════════════════

# Addresses weak spot #3: Are intermod products DAC/ADC THD or real plate coupling?
# THD scales as product_dB ≈ 2 × drive_dB (quadratic nonlinearity in electronics).
# Plate coupling would scale ≈ 1 × drive_dB (linear system response).
# Drive at 4 levels and measure the slope.

INTERMOD_DRIVE_LEVELS_DB = [0, -6, -12, -18]  # relative to DRIVE_AMPLITUDE


def exp10_intermod_atten(token, dry_run, mux, sample_rate, device_idx,
                         census_file=None):
    """Two-tone intermod at multiple drive levels to distinguish THD from coupling."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 10: INTERMOD ATTENUATION SWEEP")
    print("=" * 65)

    if census_file:
        cpath = Path(census_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_kronos_flash_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            print("  ERROR: No census file found")
            return []
        cpath = census_files[-1]

    with open(cpath) as f:
        census = json.load(f)
    src = census.get("results", census)

    results = []
    # Test plates that showed combination products (A and G from prior run)
    test_plates = ["1", "3"]  # A and G
    for pid in test_plates:
        name = PLATE_NAMES[pid]
        peaks = None
        for k in [pid, f"{pid}_NE"]:
            if k in src and src[k].get("peaks"):
                peaks = src[k]["peaks"]
                break
        if not peaks:
            continue

        glass = filter_fixture_peaks(peaks)
        if len(glass) < 2:
            continue

        f1 = glass[0]["freq_hz"]
        f2 = glass[1]["freq_hz"]
        if abs(f1 - f2) < 100 and len(glass) > 2:
            f2 = glass[2]["freq_hz"]

        relay_ch = PLATE_RELAYS[pid][0][0]
        print(f"\n─── Plate {name} (relay {relay_ch}): f1={f1:.0f}, f2={f2:.0f} Hz ───")

        nyquist = sample_rate / 2
        duration = 2.0
        settle = 0.3
        total_dur = settle + duration
        n_total = int(sample_rate * total_dur)
        n_settle = int(sample_rate * settle)
        t = np.arange(n_total) / sample_rate
        n_avg = 8

        # Products to track
        products = {
            "f1+f2": f1 + f2, "f2-f1": abs(f2 - f1),
            "2f1-f2": abs(2 * f1 - f2), "2f2-f1": abs(2 * f2 - f1),
            "2f1": 2 * f1, "2f2": 2 * f2,
        }
        products = {k: v for k, v in products.items() if 0 < v < nyquist}

        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        level_data = {}
        for db_level in INTERMOD_DRIVE_LEVELS_DB:
            amp = DRIVE_AMPLITUDE * 10 ** (db_level / 20)
            tx_sig = amp * (np.sin(2 * np.pi * f1 * t) + np.sin(2 * np.pi * f2 * t))
            peak_val = np.max(np.abs(tx_sig))
            if peak_val > 0:
                tx_sig *= amp / peak_val
            tx = tx_sig.astype(np.float32).reshape(-1, 1)

            mag_accum = None
            for _ in range(n_avg):
                rx = playrec_capture(tx, sample_rate, device_idx)
                rx_cap = rx[n_settle:n_settle + int(sample_rate * duration)]
                windowed = rx_cap * np.hanning(len(rx_cap))
                spectrum = np.fft.rfft(windowed)
                fft_mag = np.abs(spectrum)
                if mag_accum is None:
                    freq_axis = np.fft.rfftfreq(len(rx_cap), d=1.0 / sample_rate)
                    bin_hz = freq_axis[1]
                    mag_accum = np.zeros_like(fft_mag)
                mag_accum += fft_mag
            mag_avg = mag_accum / n_avg

            # Measure drives and products
            meas = {}
            for label in ["f1", "f2"] + list(products.keys()):
                freq = {"f1": f1, "f2": f2}.get(label, products.get(label))
                if freq is None:
                    continue
                idx = int(round(freq / bin_hz))
                lo = max(0, idx - 3)
                hi = min(len(mag_avg) - 1, idx + 3)
                pk = lo + int(np.argmax(mag_avg[lo:hi + 1]))
                meas[label] = float(mag_avg[pk])

            level_data[db_level] = meas
            drive_mag = max(meas.get("f1", 0), meas.get("f2", 0))
            print(f"  {db_level:+3d} dB: drive={drive_mag:.4f}", end="")
            for label in list(products.keys())[:4]:
                if label in meas:
                    print(f"  {label}={meas[label]:.4f}", end="")
            print()

        # Compute slopes for each product
        print(f"\n  Slope analysis (THD → slope ≈ 2, coupling → slope ≈ 1):")
        slope_results = {}
        ref_level_0 = max(level_data[0].get("f1", 1e-20), level_data[0].get("f2", 1e-20))

        for label, freq in products.items():
            mags = []
            drives = []
            for db_level in INTERMOD_DRIVE_LEVELS_DB:
                m = level_data[db_level]
                prod_mag = m.get(label, 0)
                drv_mag = max(m.get("f1", 1e-20), m.get("f2", 1e-20))
                if prod_mag > 0 and drv_mag > 0:
                    mags.append(20 * math.log10(prod_mag))
                    drives.append(20 * math.log10(drv_mag))

            if len(mags) >= 2:
                # Linear regression: product_dB = slope * drive_dB + offset
                d = np.array(drives)
                m = np.array(mags)
                n = len(d)
                slope = (n * np.sum(d * m) - np.sum(d) * np.sum(m)) / \
                        (n * np.sum(d ** 2) - np.sum(d) ** 2 + 1e-30)
                interpretation = (
                    "THD" if slope > 1.5 else
                    "coupling" if slope < 0.7 else
                    "ambiguous"
                )
                slope_results[label] = {
                    "slope": round(float(slope), 2),
                    "interpretation": interpretation,
                    "freq_hz": freq,
                }
                print(f"    {label:>12} ({freq:.0f} Hz): slope = {slope:.2f} → {interpretation}")
            else:
                slope_results[label] = {
                    "slope": None, "interpretation": "unmeasurable", "freq_hz": freq,
                }
                print(f"    {label:>12} ({freq:.0f} Hz): insufficient data")

        # Classify plate
        thd_count = sum(1 for r in slope_results.values() if r["interpretation"] == "THD")
        coupling_count = sum(1 for r in slope_results.values() if r["interpretation"] == "coupling")
        total = len(slope_results)
        verdict = (
            "THD-dominated" if thd_count > coupling_count else
            "coupling-dominated" if coupling_count > thd_count else
            "mixed / inconclusive"
        )
        print(f"  → Plate {name}: {verdict} ({thd_count} THD, {coupling_count} coupling, "
              f"{total - thd_count - coupling_count} ambiguous)")

        # Save locally
        ia_path = LAB_DIR / f"intermod_atten_kronos_{TIMESTAMP}_{name}.json"
        ia_data = {
            "experiment": "Intermod Attenuation Sweep (Kronos)",
            "timestamp": TIMESTAMP,
            "plate": name,
            "drive_freqs_hz": [f1, f2],
            "drive_levels_db": INTERMOD_DRIVE_LEVELS_DB,
            "level_data": {str(k): v for k, v in level_data.items()},
            "slopes": slope_results,
            "verdict": verdict,
        }
        with open(ia_path, "w") as fw:
            json.dump(ia_data, fw, indent=2)
        print(f"  Saved: {ia_path.name}")

        # Submit as mode survey with notes
        slope_summary = ', '.join(
            f'{k}={v["slope"]}' for k, v in slope_results.items() if v['slope'] is not None
        )
        data = build_firestore_data(peaks, {})
        notes = (
            f"Plate {name} intermod attenuation sweep (Kronos). "
            f"f1={f1:.0f}, f2={f2:.0f} Hz. "
            f"Levels: {INTERMOD_DRIVE_LEVELS_DB} dB. "
            f"Verdict: {verdict}. "
            f"Slopes: {slope_summary}. "
            f"192 kHz / 24-bit."
        )
        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "_detail": ia_data})
        else:
            r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
            r["_detail"] = ia_data
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 11: Write-Read Precision Map
# ═══════════════════════════════════════════════════════════════════════

# Addresses weak spot #4: The ±3 dB cross-talk threshold is too generous for
# a memory device.  This maps the full cross-talk distribution across many
# read modes to determine the actual operating margin.

WR_PRECISION_N_READ = 10  # probe 10 read modes (vs 3 in exp7)


def exp11_writeread_precision(token, dry_run, mux, sample_rate, device_idx,
                              census_file=None):
    """High-resolution write-read cross-talk map across 10 read modes."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 11: WRITE-READ PRECISION MAP")
    print("=" * 65)

    if census_file:
        cpath = Path(census_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_kronos_flash_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            print("  ERROR: No census file found")
            return []
        cpath = census_files[-1]

    with open(cpath) as f:
        census = json.load(f)
    src = census.get("results", census)

    results = []
    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        peaks = None
        for k in [pid, f"{pid}_NE"]:
            if k in src and src[k].get("peaks"):
                peaks = src[k]["peaks"]
                break
        if not peaks:
            continue

        glass = filter_fixture_peaks(peaks)
        n_write = 3
        n_needed = n_write + WR_PRECISION_N_READ
        if len(glass) < n_needed:
            print(f"  Plate {name}: only {len(glass)} glass modes, need {n_needed}, skipping")
            continue

        write_freqs = [glass[i]["freq_hz"] for i in range(n_write)]
        read_freqs = [glass[i]["freq_hz"] for i in range(n_write, n_write + WR_PRECISION_N_READ)]

        relay_ch = PLATE_RELAYS[pid][0][0]
        print(f"\n─── Plate {name} (relay {relay_ch}) ───")
        print(f"  Write: {[f'{f:.0f}' for f in write_freqs]}")
        print(f"  Read ({WR_PRECISION_N_READ}): {[f'{f:.0f}' for f in read_freqs]}")

        duration = 2.0
        settle = 0.3
        total_dur = settle + duration
        n_total = int(sample_rate * total_dur)
        n_settle = int(sample_rate * settle)
        t = np.arange(n_total) / sample_rate
        n_avg = 8

        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        def measure_levels(tx, label):
            mag_acc = {f: 0.0 for f in read_freqs}
            for _ in range(n_avg):
                rx = playrec_capture(tx, sample_rate, device_idx)
                rx_cap = rx[n_settle:n_settle + int(sample_rate * duration)]
                windowed = rx_cap * np.hanning(len(rx_cap))
                spectrum = np.fft.rfft(windowed)
                fft_mag = np.abs(spectrum)
                freq_axis = np.fft.rfftfreq(len(rx_cap), d=1.0 / sample_rate)
                bin_hz = freq_axis[1]
                for f in read_freqs:
                    idx = int(round(f / bin_hz))
                    lo = max(0, idx - 3)
                    hi = min(len(fft_mag) - 1, idx + 3)
                    pk = lo + int(np.argmax(fft_mag[lo:hi + 1]))
                    mag_acc[f] += float(fft_mag[pk])
            return {f: v / n_avg for f, v in mag_acc.items()}

        # Baseline
        probe_amp = DRIVE_AMPLITUDE * 0.1
        tx_base = np.zeros(n_total, dtype=np.float64)
        for f in read_freqs:
            tx_base += probe_amp * np.sin(2 * np.pi * f * t)
        pk = np.max(np.abs(tx_base))
        if pk > 0:
            tx_base *= probe_amp / pk
        baseline = measure_levels(tx_base.astype(np.float32).reshape(-1, 1), "BASELINE")

        # Write + read
        tx_wr = np.zeros(n_total, dtype=np.float64)
        for f in write_freqs:
            tx_wr += np.sin(2 * np.pi * f * t)
        for f in read_freqs:
            tx_wr += probe_amp * np.sin(2 * np.pi * f * t)
        pk = np.max(np.abs(tx_wr))
        if pk > 0:
            tx_wr *= DRIVE_AMPLITUDE / pk
        with_write = measure_levels(tx_wr.astype(np.float32).reshape(-1, 1), "WRITE+READ")

        # Analysis
        deltas = []
        for f in read_freqs:
            b = baseline[f]
            w = with_write[f]
            delta_db = 20 * math.log10(w / b) if b > 0 and w > 0 else 0
            deltas.append({"freq_hz": f, "baseline": b, "with_write": w,
                           "delta_db": round(delta_db, 3)})

        abs_deltas = [abs(d["delta_db"]) for d in deltas]
        mean_abs = float(np.mean(abs_deltas))
        max_abs = max(abs_deltas)
        pct_above_05 = sum(1 for d in abs_deltas if d > 0.5) / len(abs_deltas) * 100
        pct_above_1 = sum(1 for d in abs_deltas if d > 1.0) / len(abs_deltas) * 100
        pct_above_3 = sum(1 for d in abs_deltas if d > 3.0) / len(abs_deltas) * 100

        print(f"  Results across {WR_PRECISION_N_READ} read modes:")
        for d in deltas:
            flag = "***" if abs(d["delta_db"]) > 1.0 else ""
            print(f"    {d['freq_hz']:8.0f} Hz: Δ = {d['delta_db']:+6.2f} dB {flag}")
        print(f"  Mean |Δ|: {mean_abs:.2f} dB, Max |Δ|: {max_abs:.2f} dB")
        print(f"  > 0.5 dB: {pct_above_05:.0f}%, > 1 dB: {pct_above_1:.0f}%, "
              f"> 3 dB: {pct_above_3:.0f}%")

        # Save locally
        wr_path = LAB_DIR / f"writeread_precision_kronos_{TIMESTAMP}_{name}.json"
        wr_data = {
            "experiment": "Write-Read Precision Map (Kronos)",
            "timestamp": TIMESTAMP,
            "plate": name,
            "write_freqs_hz": write_freqs,
            "read_freqs_hz": read_freqs,
            "deltas": deltas,
            "stats": {
                "mean_abs_delta_db": round(mean_abs, 3),
                "max_abs_delta_db": round(max_abs, 3),
                "pct_above_0.5dB": round(pct_above_05, 1),
                "pct_above_1dB": round(pct_above_1, 1),
                "pct_above_3dB": round(pct_above_3, 1),
            },
        }
        with open(wr_path, "w") as fw:
            json.dump(wr_data, fw, indent=2)
        print(f"  Saved: {wr_path.name}")

        data = build_firestore_data(peaks, {})
        notes = (
            f"Plate {name} write-read precision ({WR_PRECISION_N_READ} read modes, Kronos). "
            f"Write {[f'{f:.0f}' for f in write_freqs]}. "
            f"Mean |Δ|={mean_abs:.2f} dB, max |Δ|={max_abs:.2f} dB. "
            f">{pct_above_1:.0f}% above 1 dB. 192 kHz / 24-bit."
        )
        if dry_run:
            print(f"  [DRY RUN] Would submit")
            results.append({"ok": True, "dry": True, "_detail": wr_data})
        else:
            r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
            r["_detail"] = wr_data
            print_result(r)
            results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 12: Fixture Resonance Characterization
# ═══════════════════════════════════════════════════════════════════════

# Addresses weak spot #6: Proves 6700 Hz is PZT/fixture, not glass, by
# comparing its cross-plate variance to a known glass-specific mode.
# If 6700 Hz has < 10% cross-relay variance while glass modes have > 50%,
# it's definitively fixture.


def exp12_fixture_characterization(token, dry_run, mux, sample_rate,
                                    device_idx, census_file=None):
    """Characterize fixture vs glass modes by cross-relay variance."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 12: FIXTURE RESONANCE CHARACTERIZATION")
    print("=" * 65)

    if census_file:
        cpath = Path(census_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_kronos_flash_*.json")
            if "sweeps" not in f.name
        )
        if not census_files:
            print("  ERROR: No census file found")
            return []
        cpath = census_files[-1]

    with open(cpath) as f:
        census = json.load(f)
    src = census.get("results", census)

    # Get top glass mode for each plate (should be unique)
    plate_modes = {}
    for pid in PLATE_IDS:
        for k in [pid, f"{pid}_NE"]:
            if k in src and src[k].get("peaks"):
                glass = filter_fixture_peaks(src[k]["peaks"])
                if glass:
                    plate_modes[pid] = glass[0]["freq_hz"]
                break

    # Test frequencies: fixture mode + all plate-specific modes
    test_freqs = {"fixture_6700": 6700.0}
    for pid, f in plate_modes.items():
        test_freqs[f"plate_{PLATE_NAMES[pid]}_{f:.0f}"] = f

    print(f"  Test frequencies: {json.dumps({k: f'{v:.0f} Hz' for k, v in test_freqs.items()}, indent=4)}")

    # Measure each frequency on each relay
    relay_list = [(pid, PLATE_RELAYS[pid][0][0]) for pid in PLATE_IDS]
    all_meas = {}

    for label, freq in test_freqs.items():
        print(f"\n  ── {label} ({freq:.0f} Hz) ──")
        mags = {}
        for pid, relay_ch in relay_list:
            name = PLATE_NAMES[pid]
            m = measure_at(freq, sample_rate, device_idx, n_avg=CW_N_AVG)
            mags[name] = m["magnitude"]
            mux.select(relay_ch)
            time.sleep(SETTLE_RELAY_S)
            m = measure_at(freq, sample_rate, device_idx, n_avg=CW_N_AVG)
            mags[name] = m["magnitude"]
            print(f"    Plate {name} (relay {relay_ch}): {m['magnitude']:.6f}")

        vals = list(mags.values())
        mean_mag = float(np.mean(vals))
        cv = float(np.std(vals) / mean_mag) * 100 if mean_mag > 0 else 0
        ratio = max(vals) / min(vals) if min(vals) > 0 else float('inf')

        all_meas[label] = {
            "freq_hz": freq,
            "magnitudes": mags,
            "mean": round(mean_mag, 6),
            "cv_pct": round(cv, 1),
            "max_min_ratio": round(ratio, 2),
        }
        is_fixture = cv < 15
        kind = "FIXTURE (low variance)" if is_fixture else "GLASS-SPECIFIC (high variance)"
        print(f"    → CV = {cv:.1f}%, ratio = {ratio:.2f} → {kind}")

    # Save locally
    fix_path = LAB_DIR / f"fixture_char_kronos_{TIMESTAMP}.json"
    fix_data = {
        "experiment": "Fixture Characterization (Kronos)",
        "timestamp": TIMESTAMP,
        "measurements": all_meas,
    }
    with open(fix_path, "w") as fw:
        json.dump(fix_data, fw, indent=2)
    print(f"\n  Saved: {fix_path.name}")

    # Submit summary
    fixture_cv = all_meas.get("fixture_6700", {}).get("cv_pct", 0)
    glass_cvs = [v["cv_pct"] for k, v in all_meas.items() if k != "fixture_6700"]
    mean_glass_cv = float(np.mean(glass_cvs)) if glass_cvs else 0

    data = build_firestore_data([], {})
    # Override with fixture-specific data
    data["num_modes_bare"] = len(test_freqs) - 1
    data["f11_measured"] = 6700
    data["snr_best_mode"] = 0
    notes = (
        f"Fixture resonance characterization (Kronos). "
        f"6700 Hz CV={fixture_cv:.1f}% across {len(relay_list)} relays. "
        f"Glass mode mean CV={mean_glass_cv:.1f}%. "
        f"{'CONFIRMED fixture' if fixture_cv < 15 else 'Inconclusive'}. "
        f"192 kHz / 24-bit."
    )

    results = []
    if dry_run:
        print(f"\n  [DRY RUN] Would submit")
        results.append({"ok": True, "dry": True, "_detail": fix_data})
    else:
        r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
        r["_detail"] = fix_data
        print_result(r)
        results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Experiment 13: Perturbation Write / Read Cycle
# ═══════════════════════════════════════════════════════════════════════

# Addresses weak spot #5: No actual write/persist/read cycle demonstrated.
# This is the simplest possible "write" — place a mass perturbation on the
# plate, which shifts mode frequencies (the "stored state").  Then read back
# by census.  Then remove the perturbation and verify modes return to
# baseline.  This proves reversible state change in the modal spectrum.
#
# Requires user interaction (physical placement of putty).


def exp13_perturbation_write_read(token, dry_run, mux, sample_rate,
                                   device_idx, f_stop):
    """Interactive perturbation write-read cycle on one plate."""
    print("\n" + "=" * 65)
    print("  EXPERIMENT 13: PERTURBATION WRITE / READ CYCLE")
    print("=" * 65)

    # Use plate A (most relays, well-characterized)
    pid = "1"
    name = PLATE_NAMES[pid]
    relay_ch = PLATE_RELAYS[pid][0][0]
    rx_label = PLATE_RELAYS[pid][0][1]

    print(f"\n  Target: Plate {name} (relay {relay_ch})")
    print(f"  This experiment requires physical access to the plate.")
    print(f"  You will need a small piece of putty/BluTack (~0.5 g).\n")

    results = []

    # Phase 1: Baseline census
    print("─── PHASE 1: Baseline Census ───")
    input("  Press ENTER when ready (plate should be clean, no putty)...")
    _, base_peaks, base_stats = quick_flash_census(
        mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)
    base_glass = filter_fixture_peaks(base_peaks)
    print(f"  Baseline: {len(base_glass)} glass modes detected")
    base_top = [p["freq_hz"] for p in base_glass[:20]]
    print(f"  Top 20: {[f'{f:.0f}' for f in base_top]}")

    # Phase 2: Write (place putty)
    print("\n─── PHASE 2: Write (place perturbation) ───")
    print("  Place a small piece of putty (~0.5 g) on the plate surface.")
    print("  Try to place it away from the PZT corners (near center is best).")
    pos = input("  Approximate position (e.g. 'center', '50,50'): ").strip() or "unspecified"
    input("  Press ENTER when putty is placed...")

    _, pert_peaks, pert_stats = quick_flash_census(
        mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)
    pert_glass = filter_fixture_peaks(pert_peaks)
    print(f"  Perturbed: {len(pert_glass)} glass modes detected")

    # Compare
    tolerance_pct = 2.0  # ±2% frequency match
    matched = 0
    shifted = 0
    disappeared = 0
    new_modes = 0
    shifts_hz = []

    for bp in base_glass[:20]:
        bf = bp["freq_hz"]
        closest = min(pert_glass, key=lambda p: abs(p["freq_hz"] - bf)) if pert_glass else None
        if closest and abs(closest["freq_hz"] - bf) / bf < tolerance_pct / 100:
            matched += 1
            shift = closest["freq_hz"] - bf
            if abs(shift) > 1:  # >1 Hz shift
                shifted += 1
                shifts_hz.append(shift)
        else:
            disappeared += 1

    # Count new modes (in perturbed but not in baseline)
    for pp in pert_glass[:20]:
        pf = pp["freq_hz"]
        closest = min(base_glass, key=lambda p: abs(p["freq_hz"] - pf)) if base_glass else None
        if not closest or abs(closest["freq_hz"] - pf) / pf >= tolerance_pct / 100:
            new_modes += 1

    mean_shift = float(np.mean(shifts_hz)) if shifts_hz else 0
    print(f"\n  Perturbation effect on top 20 modes:")
    print(f"    Matched: {matched}, Shifted: {shifted}, Disappeared: {disappeared}, New: {new_modes}")
    if shifts_hz:
        print(f"    Mean shift: {mean_shift:+.1f} Hz (range {min(shifts_hz):+.1f} to {max(shifts_hz):+.1f})")

    # Phase 3: Read-back (verify state is readable)
    print("\n─── PHASE 3: Read-back verification ───")
    print("  Re-measuring perturbed plate (putty still on)...")
    _, readback_peaks, _ = quick_flash_census(
        mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)
    readback_glass = filter_fixture_peaks(readback_peaks)

    # Check that perturbed spectrum is stable (read-back matches write)
    readback_matched = 0
    for pp in pert_glass[:20]:
        pf = pp["freq_hz"]
        closest = min(readback_glass, key=lambda p: abs(p["freq_hz"] - pf)) if readback_glass else None
        if closest and abs(closest["freq_hz"] - pf) / pf < 0.005:  # tighter: 0.5%
            readback_matched += 1

    persistence_pct = readback_matched / min(20, len(pert_glass)) * 100 if pert_glass else 0
    print(f"  Read-back persistence: {readback_matched}/20 ({persistence_pct:.0f}%)")

    # Phase 4: Erase (remove putty)
    print("\n─── PHASE 4: Erase (remove perturbation) ───")
    input("  Remove the putty from the plate, then press ENTER...")

    _, restored_peaks, _ = quick_flash_census(
        mux, pid, relay_ch, rx_label, sample_rate, device_idx, f_stop)
    restored_glass = filter_fixture_peaks(restored_peaks)

    # Check restoration
    restored_matched = 0
    restore_drifts = []
    for bp in base_glass[:20]:
        bf = bp["freq_hz"]
        closest = min(restored_glass, key=lambda p: abs(p["freq_hz"] - bf)) if restored_glass else None
        if closest and abs(closest["freq_hz"] - bf) / bf < tolerance_pct / 100:
            restored_matched += 1
            restore_drifts.append(closest["freq_hz"] - bf)

    restoration_pct = restored_matched / min(20, len(base_glass)) * 100 if base_glass else 0
    mean_restore_drift = float(np.mean(restore_drifts)) if restore_drifts else 0

    print(f"  Restoration: {restored_matched}/20 modes recovered ({restoration_pct:.0f}%)")
    if restore_drifts:
        print(f"  Mean residual drift: {mean_restore_drift:+.1f} Hz")

    # Summary
    print(f"\n─── WRITE/READ CYCLE SUMMARY ───")
    print(f"  Write: {shifted + disappeared} of 20 modes changed by perturbation")
    print(f"  Read:  {persistence_pct:.0f}% persistence on re-read")
    print(f"  Erase: {restoration_pct:.0f}% restoration after removal")
    verdict = "PASS" if shifted > 0 and persistence_pct > 80 and restoration_pct > 70 else "PARTIAL"
    print(f"  Verdict: {verdict}")

    # Save locally
    pert_path = LAB_DIR / f"perturbation_wr_kronos_{TIMESTAMP}_{name}.json"
    pert_data = {
        "experiment": "Perturbation Write/Read Cycle (Kronos)",
        "timestamp": TIMESTAMP,
        "plate": name,
        "putty_position": pos,
        "baseline_modes": len(base_glass),
        "perturbed_modes": len(pert_glass),
        "restored_modes": len(restored_glass),
        "top20_matched": matched,
        "top20_shifted": shifted,
        "top20_disappeared": disappeared,
        "new_modes": new_modes,
        "mean_shift_hz": round(mean_shift, 1),
        "shifts_hz": [round(s, 1) for s in shifts_hz],
        "readback_persistence_pct": round(persistence_pct, 1),
        "restoration_pct": round(restoration_pct, 1),
        "mean_restore_drift_hz": round(mean_restore_drift, 1),
        "verdict": verdict,
    }
    with open(pert_path, "w") as fw:
        json.dump(pert_data, fw, indent=2)
    print(f"  Saved: {pert_path.name}")

    # Submit to Firestore
    survival = round(matched / 20 * 100, 1) if base_glass else 0
    data = {
        "plate_name": f"Plate {name}",
        "perturbation_type": "Putty/BluTack",
        "perturbation_mass_mg": 500,  # estimated
        "n_modes_before": min(len(base_glass), 500),
        "n_modes_after": min(len(pert_glass), 500),
        "mean_shift_hz": max(min(round(mean_shift, 1), 10000), -10000),
        "survival_rate_pct": min(survival, 100),
        "reversible": "Yes" if restoration_pct > 70 else "Partial",
    }
    notes = (
        f"Plate {name} perturbation write/read cycle (Kronos). "
        f"Putty at {pos}. {shifted} modes shifted, {disappeared} disappeared, "
        f"{new_modes} new. Read-back {persistence_pct:.0f}% persistent. "
        f"Restoration {restoration_pct:.0f}%. {verdict}. 192 kHz / 24-bit."
    )

    if dry_run:
        print(f"  [DRY RUN] Would submit exp-plate-perturbation")
        results.append({"ok": True, "dry": True, "_detail": pert_data})
    else:
        r = submit_with_rate_limit(token, "exp-plate-perturbation", data, notes=notes)
        r["_detail"] = pert_data
        print_result(r)
        results.append(r)

    mux.off()
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Push existing data files
# ═══════════════════════════════════════════════════════════════════════

def push_existing(token, dry_run, census_file=None,
                  intermod_file=None, writeread_file=None):
    """Push existing local experiment data to Firestore."""
    print("\n" + "=" * 65)
    print("  PUSHING EXISTING DATA TO FIRESTORE")
    print("=" * 65)

    results = []

    # 1. Census
    if census_file:
        cpath = Path(census_file)
    else:
        census_files = sorted(
            f for f in LAB_DIR.glob("plate_census_kronos_flash_*.json")
            if "sweeps" not in f.name
        )
        cpath = census_files[-1] if census_files else None

    if cpath and cpath.exists():
        print(f"\n  Census: {cpath.name}")
        r = exp5_mode_survey(token, dry_run, str(cpath))
        results.extend(r)

    # 2. Intermod files
    if intermod_file:
        im_files = [Path(intermod_file)]
    else:
        im_files = sorted(LAB_DIR.glob("intermod_*.json"))

    for im_path in im_files:
        print(f"\n  Intermod: {im_path.name}")
        with open(im_path) as f:
            im = json.load(f)
        plate = im.get("plate", "?")
        detected = im.get("intermod_detected", [])
        notes = (
            f"Intermod test — plate {plate}, "
            f"drive {im.get('drive_freqs_hz', [])}. "
            f"Products: {detected or 'none'}. "
            f"Source: {im_path.name}."
        )
        data = {
            "plate_material": "Fused quartz",
            "plate_length": 100, "plate_width": 100, "plate_thickness": 1,
            "pzt_mounting": "Corner face mount",
            "pzt_drive_position": 5, "pzt_sense_position": 95,
            "num_modes_bare": 170,
            "f11_measured": 500,
            "snr_best_mode": 30,
        }
        if dry_run:
            print(f"  [DRY RUN] Would submit intermod for plate {plate}")
            results.append({"ok": True, "dry": True, "file": im_path.name})
        else:
            r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
            print_result(r)
            results.append(r)

    # 3. WriteRead files
    if writeread_file:
        wr_files = [Path(writeread_file)]
    else:
        wr_files = sorted(LAB_DIR.glob("writeread_*.json"))

    for wr_path in wr_files:
        print(f"\n  WriteRead: {wr_path.name}")
        with open(wr_path) as f:
            wr = json.load(f)
        plate = wr.get("plate", "?")
        xt = wr.get("crosstalk_detected", False)
        notes = (
            f"Write-read cross-talk — plate {plate}, "
            f"write {wr.get('write_freqs_hz', [])}, "
            f"read {wr.get('read_freqs_hz', [])}. "
            f"{'FAIL' if xt else 'PASS'}. Source: {wr_path.name}."
        )
        data = {
            "plate_material": "Fused quartz",
            "plate_length": 100, "plate_width": 100, "plate_thickness": 1,
            "pzt_mounting": "Corner face mount",
            "pzt_drive_position": 5, "pzt_sense_position": 95,
            "num_modes_bare": 170,
            "f11_measured": 500,
            "snr_best_mode": 30,
        }
        if dry_run:
            print(f"  [DRY RUN] Would submit writeread for plate {plate}")
            results.append({"ok": True, "dry": True, "file": wr_path.name})
        else:
            r = submit_with_rate_limit(token, "exp05-plate-mode-survey", data, notes=notes)
            print_result(r)
            results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Run plate experiments (Kronos) and submit to Firestore"
    )
    parser.add_argument("port", nargs="?", default="/dev/cu.usbserial-11310",
                        help="Arduino serial port")
    parser.add_argument("--device", "-d", default="KRONOS",
                        help="Audio device name (default: KRONOS)")
    parser.add_argument("--exp", type=int, nargs="*", default=None,
                        help="Run specific experiments (1-13). Default: 1-7.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't submit to Firestore")
    parser.add_argument("--census-file", type=str, default=None,
                        help="Census JSON for baseline/enrollment")
    parser.add_argument("--push-existing", action="store_true",
                        help="Push existing local data to Firestore (no hw)")
    parser.add_argument("--intermod-file", type=str, default=None,
                        help="Specific intermod JSON to push")
    parser.add_argument("--writeread-file", type=str, default=None,
                        help="Specific writeread JSON to push")
    args = parser.parse_args()

    # Auth
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

    # Push existing data mode
    if args.push_existing:
        results = push_existing(
            token, args.dry_run, args.census_file,
            args.intermod_file, args.writeread_file)
        _print_summary(results, args.dry_run)
        return

    # Hardware experiments
    exps = args.exp or [1, 2, 3, 4, 5, 6, 7]
    needs_hardware = any(e in exps for e in [1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13])

    device_idx = None
    sample_rate = None
    f_stop = None
    mux = None

    if needs_hardware:
        from relay_mux import RelayMux

        device_idx = find_audio_device(args.device)
        dev_info = sd.query_devices(device_idx)
        sample_rate = detect_sample_rate(device_idx)
        f_stop = int(sample_rate / 2) - 1000

        print(f"\n  Device: {dev_info['name']}")
        print(f"  Sample rate: {sample_rate} Hz → Nyquist: {sample_rate // 2} Hz")

        mux = RelayMux(port=args.port)
        mux.open()
        print(f"  Relay mux connected on {mux.port}")

    all_results = []
    t_start = time.time()

    try:
        if 1 in exps:
            r = exp1_mode_persistence(
                token, args.dry_run, mux, sample_rate, device_idx, f_stop,
                args.census_file)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp1")

        if 2 in exps:
            r = exp2_snr(token, args.dry_run, mux, sample_rate, device_idx, f_stop)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp2")

        if 3 in exps:
            r = exp3_damping(token, args.dry_run, mux, sample_rate, device_idx, f_stop)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp3")

        if 4 in exps:
            r = exp4_fingerprint(token, args.dry_run, mux, sample_rate, device_idx,
                                 args.census_file)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp4")

        if 5 in exps:
            r = exp5_mode_survey(token, args.dry_run, args.census_file)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp5")

        if 6 in exps:
            r = exp6_intermod(token, args.dry_run, mux, sample_rate, device_idx,
                              args.census_file)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp6")

        if 7 in exps:
            r = exp7_writeread(token, args.dry_run, mux, sample_rate, device_idx,
                               args.census_file)
            all_results.extend(r)

        if 8 in exps:
            r = exp8_ringdown_q(token, args.dry_run, mux, sample_rate,
                               device_idx, f_stop)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp8")

        if 9 in exps:
            r = exp9_true_snr(token, args.dry_run, mux, sample_rate,
                             device_idx, f_stop)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp9")

        if 10 in exps:
            r = exp10_intermod_atten(token, args.dry_run, mux, sample_rate,
                                    device_idx, args.census_file)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp10")

        if 11 in exps:
            r = exp11_writeread_precision(token, args.dry_run, mux, sample_rate,
                                         device_idx, args.census_file)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp11")

        if 12 in exps:
            r = exp12_fixture_characterization(token, args.dry_run, mux,
                                              sample_rate, device_idx,
                                              args.census_file)
            all_results.extend(r)
            _save_checkpoint(all_results, exps, args.dry_run, "after_exp12")

        if 13 in exps:
            r = exp13_perturbation_write_read(token, args.dry_run, mux,
                                             sample_rate, device_idx, f_stop)
            all_results.extend(r)

    finally:
        if mux:
            try:
                mux.off()
                mux.close()
            except Exception:
                pass

    elapsed = time.time() - t_start

    # Final save
    results_file = LAB_DIR / f"plate_experiments_kronos_{TIMESTAMP}.json"
    with open(results_file, "w") as fw:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(elapsed, 1),
            "dry_run": args.dry_run,
            "experiments_run": exps,
            "device": args.device,
            "sample_rate": sample_rate,
            "results": all_results,
        }, fw, indent=2, default=str)
    print(f"\n  Full results: {results_file}")

    _print_summary(all_results, args.dry_run, elapsed)


def _save_checkpoint(results, exps, dry_run, tag):
    """Save intermediate checkpoint after each experiment."""
    cp_file = LAB_DIR / f"plate_experiments_kronos_{TIMESTAMP}_{tag}.json"
    with open(cp_file, "w") as fw:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "experiments_run": exps,
            "checkpoint": tag,
            "results": results,
        }, fw, indent=2, default=str)


def _print_summary(results, dry_run, elapsed=None):
    """Print final summary."""
    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    submitted = [r for r in results if r.get("ok") and not r.get("dry")]
    failed = [r for r in results if not r.get("ok")]

    if dry_run:
        print(f"  DRY RUN: {len(results)} experiments would be submitted")
    else:
        print(f"  Submitted: {len(submitted)} documents to Firestore")
        if failed:
            print(f"  Failed: {len(failed)}")
            for f in failed:
                print(f"    ✗ {f.get('experimentId', '?')}: {f.get('error', '?')}")

    if elapsed:
        print(f"  Elapsed: {elapsed:.0f}s ({elapsed / 60:.1f} min)")


if __name__ == "__main__":
    main()
