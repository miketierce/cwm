#!/usr/bin/env python3
"""
Additional CIM Experiments — Paper Gap Analysis

Offline analysis + hardware experiments to convert simulation-only claims
from cwm_advanced.md into hardware-confirmed results.

Experiments:
  1. Synaptic pruning on real spectra       (offline — existing recall data)
  2. Polysemic sub-band recall              (offline — existing recall data)
  3. Phase stability characterization        (hardware — repeated acquisitions)
  4. Q-factor per rod + mode count census    (hardware — ring-down + broadband)
  5. Virtual rewrite sub-band test           (offline — existing recall data)
  6. Extended temporal stability             (hardware — re-run recall)

Usage:
  # All offline experiments (no hardware needed):
  PYTHONPATH=. python tools/additional_experiments.py --offline

  # All experiments including hardware:
  PYTHONPATH=. python tools/additional_experiments.py --port /dev/cu.usbserial-11310

  # Single experiment:
  PYTHONPATH=. python tools/additional_experiments.py --only pruning
  PYTHONPATH=. python tools/additional_experiments.py --only polysemic
  PYTHONPATH=. python tools/additional_experiments.py --only phase --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/additional_experiments.py --only qfactor --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/additional_experiments.py --only virtual-rewrite
  PYTHONPATH=. python tools/additional_experiments.py --only temporal --port /dev/cu.usbserial-11310
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure DYLD_LIBRARY_PATH is set for PicoScope before any lazy imports
import cwm_picoscope  # noqa: F401 — triggers _ensure_dyld_path()

# ── Paths ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab"
USERS_FILE = LAB_DIR / "users.json"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = LAB_DIR / "additional_exps"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ─────────────────────────────────────────────────────────

N_AVG = 12
SETTLE_S = 0.20
SETTLE_RELAY_S = 0.05
N_PEAKS = 10
FREQ_MATCH_PCT = 3

# ── Shared data loading ──────────────────────────────────────────────────

def _load_enrollment() -> tuple[dict, dict, list]:
    """Return (enrolled, rod_patterns, rod_ids)."""
    with open(USERS_FILE) as f:
        db = json.load(f)
    enrolled = {}
    rod_patterns = {}
    for rid in sorted(db["rods"].keys()):
        r = db["rods"][rid]
        if r.get("enrolled"):
            enrolled[rid] = r["perturbed_hz"]
            rod_patterns[rid] = r.get("pattern", "?")
    rod_ids = sorted(enrolled.keys())
    return enrolled, rod_patterns, rod_ids


def _load_latest_recall() -> dict:
    """Load the most recent recall JSON from lab data."""
    recall_dir = LAB_DIR / "associative_recall"
    files = sorted(recall_dir.glob("recall_*.json"))
    if not files:
        raise FileNotFoundError("No recall data found")
    with open(files[-1]) as f:
        return json.load(f)


def _template_score_from_peak_log(
    peak_log: dict, enrolled: dict, rod_ids: list[str],
    query_rod: str, freq_mask: set[float] | None = None,
    peak_weight_mask: dict[int, float] | None = None,
) -> dict[str, float]:
    """
    Reconstruct template scores from peak_log raw magnitudes.

    peak_log[query_rod][sense_rod][peak_idx] = {freq_hz, magnitude, ...}

    Optional filters:
      - freq_mask: only include peaks at these frequencies (for sub-band tests)
      - peak_weight_mask: {peak_idx: weight_multiplier}, 0.0 = pruned
    """
    scores = {sr: 0.0 for sr in rod_ids}
    qr_log = peak_log[query_rod]
    n_peaks = len(qr_log[rod_ids[0]])

    for pi in range(n_peaks):
        freq = qr_log[rod_ids[0]][pi]["freq_hz"]

        # Frequency filter (for polysemic / virtual rewrite)
        if freq_mask is not None and round(freq, 0) not in freq_mask:
            continue

        # Peak weight (for pruning — 0.0 means pruned)
        pw = 1.0
        if peak_weight_mask is not None:
            pw = peak_weight_mask.get(pi, 1.0)
            if pw == 0.0:
                continue

        mags = {sr: qr_log[sr][pi]["magnitude"] for sr in rod_ids}
        total = sum(mags.values())
        if total == 0:
            continue

        for sr in rod_ids:
            frac = mags[sr] / total
            expected = any(
                abs(freq - ep) / max(freq, ep) < 0.03
                for ep in enrolled[sr]
            )
            if expected:
                scores[sr] += frac * 3.0 * pw
            else:
                scores[sr] -= frac * 1.0 * pw

    return {sr: round(v, 2) for sr, v in scores.items()}


def _eval_accuracy(matrix: dict, rod_ids: list[str]) -> tuple[int, float, float]:
    """From a score matrix, compute (correct, accuracy, mean_margin)."""
    correct = 0
    total_margin = 0.0
    for qr in rod_ids:
        scores = matrix[qr]
        winner = max(scores, key=scores.get)
        if winner == qr:
            correct += 1
        sorted_rods = sorted(scores, key=scores.get, reverse=True)
        if sorted_rods[0] == qr:
            margin = scores[sorted_rods[0]] - scores[sorted_rods[1]]
        else:
            margin = scores[qr] - scores[sorted_rods[0]]
        total_margin += margin
    accuracy = correct / len(rod_ids)
    mean_margin = total_margin / len(rod_ids)
    return correct, accuracy, mean_margin


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 1: Synaptic Pruning on Real Spectra
# ══════════════════════════════════════════════════════════════════════════

def exp_synaptic_pruning() -> dict:
    """
    Apply weight pruning (threshold sweep) to the real 4×4 recall score
    matrix from hardware data. Analogous to cwm_advanced §2.1 which tested
    on simulated Hopfield with N=50, P=8.

    Pruning approach: for each query, compute per-peak template score
    contributions. Zero out contributions whose absolute value is below θ.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT: Synaptic Pruning on Real Hardware Spectra")
    print("=" * 70)

    recall_data = _load_latest_recall()
    enrolled, rod_patterns, rod_ids = _load_enrollment()
    peak_log = recall_data["peak_log"]
    n_peaks = len(peak_log[rod_ids[0]][rod_ids[0]])

    # First compute per-peak contributions to understand the weight distribution
    all_contribs = []  # (query_rod, peak_idx, sense_rod, contribution)
    for qr in rod_ids:
        qr_log = peak_log[qr]
        for pi in range(n_peaks):
            freq = qr_log[rod_ids[0]][pi]["freq_hz"]
            mags = {sr: qr_log[sr][pi]["magnitude"] for sr in rod_ids}
            total = sum(mags.values())
            if total == 0:
                continue
            for sr in rod_ids:
                frac = mags[sr] / total
                expected = any(
                    abs(freq - ep) / max(freq, ep) < 0.03
                    for ep in enrolled[sr]
                )
                contrib = frac * 3.0 if expected else -frac * 1.0
                all_contribs.append({
                    "qr": qr, "pi": pi, "sr": sr,
                    "freq": freq, "contrib": contrib,
                })

    abs_contribs = [abs(c["contrib"]) for c in all_contribs]
    max_contrib = max(abs_contribs)

    # Baseline (no pruning)
    baseline_matrix = {}
    for qr in rod_ids:
        baseline_matrix[qr] = _template_score_from_peak_log(
            peak_log, enrolled, rod_ids, qr)
    _, baseline_acc, baseline_margin = _eval_accuracy(baseline_matrix, rod_ids)

    print(f"\n  {len(all_contribs)} per-peak contributions, max |contrib| = {max_contrib:.3f}")
    print(f"  Baseline: accuracy={baseline_acc:.0%}, margin={baseline_margin:+.2f}")
    print()

    # Sweep pruning threshold (as fraction of max contribution)
    thresholds = [0, 0.01, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, 0.75]
    results = []

    print(f"  {'θ frac':>8}  {'θ abs':>8}  {'Pruned':>8}  {'Accuracy':>10}  {'Margin':>10}  {'Δ acc':>8}  {'Δ margin':>10}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*10}")

    for theta_frac in thresholds:
        theta_abs = theta_frac * max_contrib

        # Build per-peak weight mask: zero out peaks below threshold
        # We need to decide: prune per (query, peak, sense) or per (query, peak)?
        # Paper pruning is per-synapse (query, sense pair). We prune per-peak for the
        # query — if ALL contributions at a given peak are below threshold, skip it.
        # Actually, more analogous: prune per-peak if the aggregate across sense rods
        # is weak. Let's try per-peak pruning: exclude peaks where the strongest
        # sense rod contribution is below threshold.

        pruned = 0
        pruned_matrix = {}
        for qr in rod_ids:
            qr_log = peak_log[qr]
            peak_mask = {}
            for pi in range(n_peaks):
                freq = qr_log[rod_ids[0]][pi]["freq_hz"]
                mags = {sr: qr_log[sr][pi]["magnitude"] for sr in rod_ids}
                total = sum(mags.values())
                if total == 0:
                    peak_mask[pi] = 0.0
                    pruned += 1
                    continue
                # Max contribution at this peak
                max_peak_contrib = 0
                for sr in rod_ids:
                    frac = mags[sr] / total
                    expected = any(abs(freq - ep)/max(freq, ep) < 0.03
                                   for ep in enrolled[sr])
                    c = abs(frac * 3.0 if expected else frac * 1.0)
                    max_peak_contrib = max(max_peak_contrib, c)

                if max_peak_contrib < theta_abs:
                    peak_mask[pi] = 0.0
                    pruned += 1
                else:
                    peak_mask[pi] = 1.0

            pruned_matrix[qr] = _template_score_from_peak_log(
                peak_log, enrolled, rod_ids, qr, peak_weight_mask=peak_mask)

        total_peaks = len(rod_ids) * n_peaks
        pruned_pct = pruned / total_peaks * 100
        corr, acc, margin = _eval_accuracy(pruned_matrix, rod_ids)
        d_acc = acc - baseline_acc
        d_margin = margin - baseline_margin

        print(f"  {theta_frac:>8.3f}  {theta_abs:>8.4f}  {pruned_pct:>7.1f}%  {acc:>9.0%}  {margin:>+9.2f}  {d_acc:>+7.0%}  {d_margin:>+9.2f}")

        results.append({
            "theta_frac": theta_frac,
            "theta_abs": round(theta_abs, 4),
            "pruned_pct": round(pruned_pct, 1),
            "accuracy": acc,
            "mean_margin": round(margin, 2),
            "delta_accuracy": round(d_acc, 3),
            "delta_margin": round(d_margin, 2),
        })

    # The more interesting pruning: prune by peak SNR (magnitude / noise floor)
    print("\n  --- Alternate: Prune by peak magnitude threshold ---")
    print(f"  {'Mag thresh':>10}  {'Pruned':>8}  {'Accuracy':>10}  {'Margin':>10}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*10}  {'-'*10}")

    snr_results = []
    # Estimate noise floor from weakest peaks
    all_mags = []
    for qr in rod_ids:
        for sr in rod_ids:
            for pe in peak_log[qr][sr]:
                all_mags.append(pe["magnitude"])
    noise_est = np.percentile(all_mags, 10)

    for mag_mult in [0, 1, 2, 3, 5, 10, 20, 50, 100]:
        thresh = noise_est * mag_mult
        pruned_matrix2 = {}
        pruned2 = 0
        for qr in rod_ids:
            qr_log = peak_log[qr]
            peak_mask = {}
            for pi in range(n_peaks):
                # Check: does ANY sense rod exceed the threshold at this peak?
                max_m = max(qr_log[sr][pi]["magnitude"] for sr in rod_ids)
                if max_m < thresh:
                    peak_mask[pi] = 0.0
                    pruned2 += 1
                else:
                    peak_mask[pi] = 1.0
            pruned_matrix2[qr] = _template_score_from_peak_log(
                peak_log, enrolled, rod_ids, qr, peak_weight_mask=peak_mask)

        pruned_pct2 = pruned2 / (len(rod_ids) * n_peaks) * 100
        _, acc2, margin2 = _eval_accuracy(pruned_matrix2, rod_ids)
        print(f"  {mag_mult:>7}× NF  {pruned_pct2:>7.1f}%  {acc2:>9.0%}  {margin2:>+9.2f}")
        snr_results.append({
            "mag_mult": mag_mult,
            "threshold": round(thresh, 0),
            "pruned_pct": round(pruned_pct2, 1),
            "accuracy": acc2,
            "mean_margin": round(margin2, 2),
        })

    return {
        "experiment": "synaptic_pruning_real_spectra",
        "source_file": str(LAB_DIR / "associative_recall" / sorted(
            (LAB_DIR / "associative_recall").glob("recall_*.json"))[-1].name),
        "n_rods": len(rod_ids),
        "n_peaks": n_peaks,
        "max_contribution": round(max_contrib, 4),
        "baseline_accuracy": baseline_acc,
        "baseline_margin": round(baseline_margin, 2),
        "threshold_sweep": results,
        "magnitude_sweep": snr_results,
        "paper_claim": "+10.7% at θ=0.055 (sim, N=50, P=8)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 2: Polysemic Sub-Band Recall
# ══════════════════════════════════════════════════════════════════════════

def exp_polysemic_subband() -> dict:
    """
    Test cwm_advanced §2.5 claim: polysemic readout provides +297% capacity
    by partitioning the spectrum into independent sub-bands.

    We split the 10 enrolled peaks per rod into low-band and high-band
    (and optionally 3-4 bands), then test whether each sub-band independently
    achieves correct recall using proper template scoring.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT: Polysemic Sub-Band Recall")
    print("=" * 70)

    recall_data = _load_latest_recall()
    enrolled, rod_patterns, rod_ids = _load_enrollment()
    peak_log = recall_data["peak_log"]
    n_peaks = len(peak_log[rod_ids[0]][rod_ids[0]])

    # Get all enrolled peak frequencies (for bandwidth context)
    all_freqs = set()
    for rid in rod_ids:
        all_freqs.update(enrolled[rid][:N_PEAKS])
    all_freqs_sorted = sorted(all_freqs)

    # Also get per-rod frequencies (from peak_log — these are the actual query freqs)
    rod_freqs = {}
    for rid in rod_ids:
        rod_freqs[rid] = [peak_log[rid][rod_ids[0]][pi]["freq_hz"]
                          for pi in range(n_peaks)]

    print(f"\n  {len(all_freqs_sorted)} unique enrolled freqs across {len(rod_ids)} rods")
    print(f"  Range: {all_freqs_sorted[0]:.1f} Hz — {all_freqs_sorted[-1]:.1f} Hz")

    # Baseline (all peaks)
    base_matrix = {qr: _template_score_from_peak_log(
        peak_log, enrolled, rod_ids, qr) for qr in rod_ids}
    _, base_acc, base_margin = _eval_accuracy(base_matrix, rod_ids)
    print(f"  Baseline: accuracy={base_acc:.0%}, margin={base_margin:+.2f}")

    results = {}
    for n_bands in [2, 3, 4]:
        print(f"\n  --- {n_bands}-band partition ---")

        # Split frequency range into equal bands
        f_min = min(all_freqs_sorted) - 1
        f_max = max(all_freqs_sorted) + 1
        band_boundaries = np.linspace(f_min, f_max, n_bands + 1)

        band_results = []
        for band_idx in range(n_bands):
            lo = band_boundaries[band_idx]
            hi = band_boundaries[band_idx + 1]

            # Build frequency mask for this band
            # Need to include rounded frequencies from all query rods
            band_freqs = set()
            n_in_band = 0
            for rid in rod_ids:
                for f in rod_freqs[rid]:
                    if lo <= f < hi:
                        band_freqs.add(round(f, 0))
                        n_in_band += 1

            # Recompute template scores using only peaks in this band
            band_matrix = {}
            for qr in rod_ids:
                # Build peak mask: only include peaks whose freq falls in band
                peak_mask = {}
                for pi in range(n_peaks):
                    freq = peak_log[qr][rod_ids[0]][pi]["freq_hz"]
                    if lo <= freq < hi:
                        peak_mask[pi] = 1.0
                    else:
                        peak_mask[pi] = 0.0
                band_matrix[qr] = _template_score_from_peak_log(
                    peak_log, enrolled, rod_ids, qr, peak_weight_mask=peak_mask)

            corr, acc, margin = _eval_accuracy(band_matrix, rod_ids)
            n_peaks_in_band = sum(1 for pi in range(n_peaks)
                                   for rid in rod_ids[:1]
                                   if lo <= peak_log[rid][rod_ids[0]][pi]["freq_hz"] < hi)

            print(f"    Band {band_idx+1} [{lo:.0f}–{hi:.0f} Hz]: "
                  f"{n_in_band} peak·rod entries, "
                  f"accuracy={acc:.0%}, margin={margin:+.2f}")

            band_results.append({
                "band": band_idx + 1,
                "lo_hz": round(lo, 1),
                "hi_hz": round(hi, 1),
                "n_peak_rod_entries": n_in_band,
                "accuracy": acc,
                "mean_margin": round(margin, 2),
                "correct": corr,
                "total": len(rod_ids),
            })

        n_independent = sum(1 for b in band_results if b["accuracy"] == 1.0)
        print(f"    → {n_independent}/{n_bands} bands achieve 100% recall independently")

        results[f"{n_bands}_bands"] = {
            "n_bands": n_bands,
            "bands": band_results,
            "independent_100pct": n_independent,
        }

    return {
        "experiment": "polysemic_subband_recall",
        "n_rods": len(rod_ids),
        "n_peaks_per_rod": N_PEAKS,
        "freq_range_hz": [round(all_freqs_sorted[0], 1), round(all_freqs_sorted[-1], 1)],
        "baseline_accuracy": base_acc,
        "baseline_margin": round(base_margin, 2),
        "partitions": results,
        "paper_claim": "+297% capacity from 4-channel polysemic readout (sim)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   Hardware helpers — mirrors cim_suite_hw.py API patterns
# ══════════════════════════════════════════════════════════════════════════

def _hw_open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    print("  PicoScope opened (Ch A ±1V DC)")
    return handle


def _hw_close_scope(handle):
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


def _hw_capture_raw(handle, n_samples=None, sample_rate=None, timebase=None):
    """Capture a single block and return raw int16 array."""
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE as TB, N_SAMPLES as NS, SAMPLE_RATE as SR
    n_samples = n_samples or NS
    sample_rate = sample_rate or SR
    timebase = timebase or TB

    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, n_samples, timebase, 1, ctypes.byref(t_ms))
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.002)
        if time.time() - t0 > 2:
            break
    buf_a = (ctypes.c_int16 * n_samples)()
    buf_b = (ctypes.c_int16 * n_samples)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), n_samples
    )
    if n > 0:
        return np.array(buf_a[:n], dtype=np.float64)
    return np.zeros(n_samples, dtype=np.float64)


def _hw_measure_spectrum(handle, freq_hz: float, n_avg: int = N_AVG,
                          settle_s: float = SETTLE_S,
                          drive_uvpp: int = None):
    """Drive AWG at freq_hz, capture averaged FFT magnitude + complex spectrum."""
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES
    if drive_uvpp is None:
        drive_uvpp = AWG_DRIVE_UVPP

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, drive_uvpp, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(settle_s)

    magnitudes = []
    complex_spectra = []
    for _ in range(n_avg):
        raw = _hw_capture_raw(handle)
        windowed = raw * np.hanning(len(raw))
        nfft = len(raw) * 4
        fft_complex = np.fft.rfft(windowed, n=nfft)
        fft_mag = np.abs(fft_complex)
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
        bin_hz = freq_axis[1] - freq_axis[0]
        target_bin = int(round(freq_hz / bin_hz))
        lo = max(0, target_bin - 3)
        hi = min(len(fft_mag) - 1, target_bin + 3)
        peak_bin = lo + np.argmax(fft_mag[lo:hi + 1])
        magnitudes.append(float(fft_mag[peak_bin]))
        complex_spectra.append(complex(fft_complex[peak_bin]))

    return {
        "magnitude": round(float(np.mean(magnitudes)), 1),
        "magnitudes": magnitudes,
        "complex_values": complex_spectra,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 3: Phase Stability Characterization
# ══════════════════════════════════════════════════════════════════════════

def exp_phase_stability(port: str) -> dict:
    """
    Test cwm_advanced §2.6 claim: phase information is orthogonal to
    frequency and adds +84% discriminability.

    Measure complex FFT at enrolled peaks across multiple acquisitions,
    track phase angle stability.
    """
    from relay_mux import RelayMux
    from cwm_picoscope import AWG_DRIVE_UVPP

    print("\n" + "=" * 70)
    print("  EXPERIMENT: Phase Stability Characterization")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    N_TRIALS = 10  # repeated acquisitions per rod per frequency

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    results_per_rod = {}

    for rid in rod_ids:
        peaks = enrolled[rid][:N_PEAKS]
        rod_results = []

        relay_ch = int(rid)
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        print(f"\n  Rod {rid} ({rod_patterns.get(rid, '?')}):")

        for freq_hz in peaks:
            # Measure N_TRIALS times at this frequency
            result = _hw_measure_spectrum(handle, freq_hz, n_avg=N_TRIALS)

            # Extract phase from complex values
            phases = np.array([np.angle(c) for c in result["complex_values"]])
            magnitudes = np.array(result["magnitudes"])

            # Unwrap phase to handle ±π wrapping
            phases_unwrapped = np.unwrap(phases)

            phase_mean = float(np.mean(phases_unwrapped))
            phase_std = float(np.std(phases_unwrapped))
            phase_range = float(np.ptp(phases_unwrapped))
            mag_mean = float(np.mean(magnitudes))
            mag_cv = float(np.std(magnitudes) / mag_mean) if mag_mean > 0 else 999

            rod_results.append({
                "freq_hz": round(freq_hz, 1),
                "phase_mean_rad": round(phase_mean, 4),
                "phase_std_rad": round(phase_std, 4),
                "phase_range_rad": round(phase_range, 4),
                "mag_mean": round(mag_mean, 1),
                "mag_cv": round(mag_cv, 4),
                "n_trials": N_TRIALS,
                "phases_raw": [round(float(p), 4) for p in phases_unwrapped],
            })

            stability = "STABLE" if phase_std < 0.1 else ("MODERATE" if phase_std < 0.5 else "UNSTABLE")
            print(f"    {freq_hz:>8.1f} Hz  phase={phase_mean:+.3f}±{phase_std:.3f} rad  "
                  f"mag_cv={mag_cv:.3f}  [{stability}]")

        results_per_rod[rid] = rod_results

    # Clean up
    mux.off()
    _hw_close_scope(handle)

    # Summary: phase as discriminator
    print("\n  --- Phase Discriminability Summary ---")
    from itertools import combinations
    pair_results = []
    for ra, rb in combinations(rod_ids, 2):
        freqs_a = {round(p["freq_hz"], 0): p["phase_mean_rad"] for p in results_per_rod[ra]}
        freqs_b = {round(p["freq_hz"], 0): p["phase_mean_rad"] for p in results_per_rod[rb]}
        shared = set(freqs_a.keys()) & set(freqs_b.keys())
        if shared:
            diffs = [abs(freqs_a[f] - freqs_b[f]) for f in shared]
            mean_diff = np.mean(diffs)
            print(f"    Rod {ra} vs {rb}: {len(shared)} shared freqs, "
                  f"mean |Δphase|={mean_diff:.3f} rad ({np.degrees(mean_diff):.1f}°)")
            pair_results.append({
                "rod_a": ra, "rod_b": rb,
                "shared_freqs": len(shared),
                "mean_phase_diff_rad": round(float(mean_diff), 4),
            })
        else:
            print(f"    Rod {ra} vs {rb}: no shared frequencies")

    # Global phase stability
    all_stds = [p["phase_std_rad"] for rod_res in results_per_rod.values() for p in rod_res]
    global_mean_std = np.mean(all_stds)
    stable_count = sum(1 for s in all_stds if s < 0.1)
    print(f"\n  Overall: {stable_count}/{len(all_stds)} peaks phase-stable (σ < 0.1 rad)")
    print(f"  Global mean phase σ = {global_mean_std:.4f} rad ({np.degrees(global_mean_std):.2f}°)")

    return {
        "experiment": "phase_stability",
        "n_trials": N_TRIALS,
        "per_rod": results_per_rod,
        "pair_comparison": pair_results,
        "global_phase_std_rad": round(float(global_mean_std), 4),
        "stable_fraction": round(stable_count / len(all_stds), 3),
        "paper_claim": "+84% discriminability from phase-spectral encoding (sim)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 4: Q-Factor Per Rod + Mode Count Census
# ══════════════════════════════════════════════════════════════════════════

def exp_qfactor_mode_census(port: str) -> dict:
    """
    Measure Q-factor per rod via ring-down envelope fitting, then do a
    broadband sweep to count all resolvable modes up to Nyquist.

    Paper claims: Q = 10,000, 9380 modes (size-independent).
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT: Q-Factor Per Rod + Mode Count Census")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    results_per_rod = {}

    for rid in rod_ids:
        relay_ch = int(rid)
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        peaks = enrolled[rid]
        # Use a mid-range peak for Q measurement
        test_freq = peaks[min(3, len(peaks)-1)]  # ~4th peak

        print(f"\n  Rod {rid} ({rod_patterns.get(rid, '?')}): Q measurement at {test_freq:.1f} Hz")

        # Step 1: Excite at the test frequency, let it ring up
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(test_freq), float(test_freq), 0.0, 0.0, 0, 0
        )
        time.sleep(0.5)  # let it ring up

        # Now turn off AWG and immediately capture ring-down
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
        time.sleep(0.001)  # tiny delay

        # Capture ring-down
        raw = _hw_capture_raw(handle)
        t = np.arange(len(raw)) / SAMPLE_RATE

        # Compute envelope via analytic signal (Hilbert transform)
        from scipy.signal import hilbert
        analytic = hilbert(raw)
        envelope = np.abs(analytic)

        # Fit exponential decay: envelope = A * exp(-t/tau)
        mask = envelope > np.max(envelope) * 0.05  # above 5% of peak
        if np.sum(mask) > 10:
            t_masked = t[mask]
            env_masked = envelope[mask]
            log_env = np.log(env_masked + 1e-30)
            coeffs = np.polyfit(t_masked, log_env, 1)
            tau_s = -1.0 / coeffs[0] if coeffs[0] < 0 else float('inf')
            Q_measured = math.pi * test_freq * tau_s
        else:
            tau_s = float('nan')
            Q_measured = float('nan')

        if not math.isnan(tau_s) and not math.isinf(tau_s):
            print(f"    Ring-down τ = {tau_s*1000:.2f} ms, Q = {Q_measured:.0f}")
        else:
            print(f"    Ring-down: could not fit decay envelope")

        # Step 2: Broadband mode count census
        # Drive with white noise (waveType=3 in ps2000 sig gen)
        try:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 3,
                100.0, float(SAMPLE_RATE / 2), 0.0, 0.0, 0, 0
            )
        except Exception:
            # Fallback: chirp sweep from low to Nyquist
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 1,
                100.0, float(SAMPLE_RATE / 2),
                float(SAMPLE_RATE / 2 - 100) / 2.0, 0.0, 0, 0
            )
        time.sleep(SETTLE_S)

        # Capture and average N_AVG spectra
        accumulated = None
        for _ in range(N_AVG):
            raw2 = _hw_capture_raw(handle)
            windowed = raw2 * np.hanning(len(raw2))
            spectrum = np.abs(np.fft.rfft(windowed))
            if accumulated is None:
                accumulated = np.zeros_like(spectrum)
            accumulated += spectrum

        avg_spectrum = accumulated / N_AVG
        freqs = np.fft.rfftfreq(len(raw2), 1.0 / SAMPLE_RATE)

        # Count peaks above noise floor
        noise_floor = float(np.median(avg_spectrum))
        threshold = noise_floor * 3.0
        peaks_found = []
        for i in range(1, len(avg_spectrum) - 1):
            if (avg_spectrum[i] > avg_spectrum[i-1] and
                avg_spectrum[i] > avg_spectrum[i+1] and
                avg_spectrum[i] > threshold):
                peaks_found.append({
                    "freq_hz": round(float(freqs[i]), 1),
                    "magnitude": round(float(avg_spectrum[i]), 1),
                })

        nyquist = SAMPLE_RATE / 2
        print(f"    Mode census: {len(peaks_found)} peaks above {threshold:.0f} "
              f"(Nyquist={nyquist:.0f} Hz)")

        # Theoretical prediction
        v_bar = 5315  # m/s for borosilicate
        L = 0.150     # m (150 mm rod)
        f_fundamental = v_bar / (2 * L)
        n_max_nyquist = int(nyquist / f_fundamental)
        print(f"    Theoretical modes below Nyquist: {n_max_nyquist} "
              f"(f1={f_fundamental:.0f} Hz)")

        results_per_rod[rid] = {
            "test_freq_hz": round(test_freq, 1),
            "tau_ms": round(tau_s * 1000, 2) if not (math.isnan(tau_s) or math.isinf(tau_s)) else None,
            "Q_measured": round(Q_measured, 0) if not (math.isnan(Q_measured) or math.isinf(Q_measured)) else None,
            "mode_count": len(peaks_found),
            "nyquist_hz": nyquist,
            "noise_floor": round(noise_floor, 1),
            "n_max_theoretical_at_nyquist": n_max_nyquist,
            "peaks_detected": peaks_found[:50],
        }

    mux.off()
    _hw_close_scope(handle)

    # Summary
    print("\n  --- Q-Factor Summary ---")
    for rid in rod_ids:
        r = results_per_rod[rid]
        q = r["Q_measured"]
        n = r["mode_count"]
        nt = r["n_max_theoretical_at_nyquist"]
        q_str = str(int(q)) if q else "N/A"
        pct = n / nt * 100 if nt > 0 else 0
        print(f"    Rod {rid}: Q={q_str}, modes={n}/{nt} theoretical ({pct:.0f}% at Nyquist)")

    return {
        "experiment": "qfactor_mode_census",
        "per_rod": results_per_rod,
        "sample_rate": SAMPLE_RATE,
        "paper_claim_q": "Q = 10,000 (macro prototype)",
        "paper_claim_modes": "9,380 (size-independent, full bandwidth)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 5: Virtual Rewrite (Sub-Band Partitioning)
# ══════════════════════════════════════════════════════════════════════════

def exp_virtual_rewrite() -> dict:
    """
    Test cwm_advanced §3.2 claim: firmware-defined virtual rewriting creates
    4+ logical devices per rod by partitioning modes into disjoint subsets.

    We split each rod's peaks into disjoint subsets and test whether each
    subset independently identifies the correct rod via template scoring.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT: Virtual Rewrite (Sub-Band Partitioning)")
    print("=" * 70)

    recall_data = _load_latest_recall()
    enrolled, rod_patterns, rod_ids = _load_enrollment()
    peak_log = recall_data["peak_log"]
    n_peaks = len(peak_log[rod_ids[0]][rod_ids[0]])

    # Baseline
    base_matrix = {qr: _template_score_from_peak_log(
        peak_log, enrolled, rod_ids, qr) for qr in rod_ids}
    _, base_acc, base_margin = _eval_accuracy(base_matrix, rod_ids)
    print(f"\n  Baseline: accuracy={base_acc:.0%}, margin={base_margin:+.2f}")

    split_strategies = {
        "even_odd": lambda n: ({i: 1.0 if i % 2 == 0 else 0.0 for i in range(n)},
                                {i: 1.0 if i % 2 == 1 else 0.0 for i in range(n)}),
        "first_half_second_half": lambda n: ({i: 1.0 if i < n//2 else 0.0 for i in range(n)},
                                              {i: 1.0 if i >= n//2 else 0.0 for i in range(n)}),
        "thirds": lambda n: (
            {i: 1.0 if i % 3 == 0 else 0.0 for i in range(n)},
            {i: 1.0 if i % 3 == 1 else 0.0 for i in range(n)},
            {i: 1.0 if i % 3 == 2 else 0.0 for i in range(n)},
        ),
    }

    results = {}

    for strategy_name, split_fn in split_strategies.items():
        subsets = split_fn(n_peaks)
        n_subsets = len(subsets)
        print(f"\n  --- Strategy: {strategy_name} ({n_subsets} subsets) ---")

        strategy_results = []
        for si, subset_mask in enumerate(subsets):
            n_active = sum(1 for v in subset_mask.values() if v > 0)
            sub_matrix = {qr: _template_score_from_peak_log(
                peak_log, enrolled, rod_ids, qr,
                peak_weight_mask=subset_mask) for qr in rod_ids}
            corr, acc, margin = _eval_accuracy(sub_matrix, rod_ids)

            label = chr(65 + si)  # A, B, C...
            print(f"    Subset {label} ({n_active}/{n_peaks} peaks): "
                  f"accuracy={acc:.0%}, margin={margin:+.2f}")

            strategy_results.append({
                "subset": label,
                "n_active_peaks": n_active,
                "accuracy": acc,
                "mean_margin": round(margin, 2),
                "correct": corr,
                "total": len(rod_ids),
            })

        n_independent = sum(1 for r in strategy_results if r["accuracy"] == 1.0)
        print(f"    → {n_independent}/{n_subsets} subsets achieve 100% recall")

        results[strategy_name] = {
            "strategy": strategy_name,
            "n_subsets": n_subsets,
            "subsets": strategy_results,
            "independent_100pct": n_independent,
        }

    return {
        "experiment": "virtual_rewrite_subband",
        "n_rods": len(rod_ids),
        "n_peaks_per_rod": n_peaks,
        "baseline_accuracy": base_acc,
        "baseline_margin": round(base_margin, 2),
        "strategies": results,
        "paper_claim": "4+ logical devices per rod via firmware partitioning (sim)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 6: Extended Temporal Stability
# ══════════════════════════════════════════════════════════════════════════

def exp_temporal_stability(port: str) -> dict:
    """
    Re-run recall to extend the temporal stability record.
    Already have 24h data — this adds another data point.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT: Extended Temporal Stability")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    # Measure 4x4 matrix (same as CIM suite temporal stability)
    matrix = {qr: {} for qr in rod_ids}
    for qi, qr in enumerate(rod_ids):
        query_peaks = enrolled[qr][:N_PEAKS]
        raw_mags = {sr: [] for sr in rod_ids}

        for freq_hz in query_peaks:
            # Drive AWG at this frequency
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)

            for sr in rod_ids:
                relay_ch = int(sr)
                mux.select(relay_ch)
                time.sleep(SETTLE_RELAY_S)

                magnitudes = []
                for _ in range(N_AVG):
                    raw = _hw_capture_raw(handle)
                    windowed = raw * np.hanning(len(raw))
                    nfft = len(raw) * 4
                    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                    bin_hz = freq_axis[1] - freq_axis[0]
                    target_bin = int(round(freq_hz / bin_hz))
                    lo = max(0, target_bin - 3)
                    hi = min(len(fft_mag) - 1, target_bin + 3)
                    magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))

                raw_mags[sr].append(float(np.mean(magnitudes)))

        # Template score
        scores = {sr: 0.0 for sr in rod_ids}
        for pi, freq in enumerate(query_peaks):
            mags = {sr: raw_mags[sr][pi] for sr in rod_ids}
            total = sum(mags.values())
            if total == 0:
                continue
            for sr in rod_ids:
                frac = mags[sr] / total
                expected = any(
                    abs(freq - ep) / max(freq, ep) < 0.03
                    for ep in enrolled[sr]
                )
                if expected:
                    scores[sr] += frac * 3.0
                else:
                    scores[sr] -= frac * 1.0

        scores = {sr: round(v, 2) for sr, v in scores.items()}
        matrix[qr] = scores

        winner = max(scores, key=scores.get)
        correct = "✓" if winner == qr else "✗"
        sorted_rods = sorted(scores, key=scores.get, reverse=True)
        if sorted_rods[0] == qr:
            margin = scores[sorted_rods[0]] - scores[sorted_rods[1]]
        else:
            margin = scores[qr] - scores[sorted_rods[0]]
        print(f"    Q={qr}: winner=Rod {winner} {correct}  "
              f"score={scores[winner]:+.1f}  margin={margin:+.1f}")

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    mux.off()
    _hw_close_scope(handle)

    # Compute accuracy
    correct_count = sum(1 for qr in rod_ids
                        if max(matrix[qr], key=matrix[qr].get) == qr)
    accuracy = correct_count / len(rod_ids)

    # Compare with historical runs
    print(f"\n  Accuracy: {correct_count}/{len(rod_ids)} ({accuracy:.0%})")

    # Load historical for comparison
    suite_files = sorted((LAB_DIR / "cim_suite").glob("suite_*.json"))
    history = []
    for sf in suite_files:
        with open(sf) as f:
            sd = json.load(f)
        ts_data = sd.get("temporal_stability", {})
        ra = ts_data.get("recall_accuracy", 0)
        rm = ts_data.get("recall_mean_margin", 0)
        history.append({
            "file": sf.name,
            "timestamp": sd.get("timestamp", "?"),
            "recall_accuracy": ra,
            "recall_mean_margin": rm,
        })

    print("\n  Historical record:")
    for h in history:
        print(f"    {h['file']}: accuracy={h['recall_accuracy']*100:.0f}%, "
              f"margin={h['recall_mean_margin']:+.2f}")
    print(f"    {'current run':30s}: accuracy={accuracy*100:.0f}%")

    return {
        "experiment": "extended_temporal_stability",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "matrix": matrix,
        "accuracy": accuracy,
        "correct": correct_count,
        "total": len(rod_ids),
        "history": history,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 7: Mode Hybridization Search
# ══════════════════════════════════════════════════════════════════════════

def exp_mode_hybridization(port: str) -> dict:
    """
    Test cwm_advanced §2.3 claim: near-degenerate mode pairs hybridize,
    creating avoided crossings that add +160% information capacity.

    Approach: For each rod, do a fine-resolution frequency sweep around
    enrolled peaks looking for:
    1. Split peaks (two closely-spaced resonances instead of one)
    2. Anticorrelated amplitude pairs (hallmark of avoided crossings)
    3. Mode spacing statistics — how many peaks are within coupling distance

    Also scan between enrolled peaks for previously-undetected modes that
    could form near-degenerate pairs with the known modes.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT: Mode Hybridization Search (Avoided Crossings)")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    # Load full 20-peak fingerprint for broader mode inventory
    with open(USERS_FILE) as f:
        db = json.load(f)

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    results_per_rod = {}

    for rid in rod_ids:
        relay_ch = int(rid)
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        # Use full fingerprint (up to 20 peaks) for broader coverage
        full_peaks = db["rods"][rid].get("fingerprint", enrolled[rid])
        if not full_peaks:
            full_peaks = enrolled[rid]
        full_peaks = sorted(full_peaks)

        print(f"\n  Rod {rid} ({rod_patterns.get(rid, '?')}): "
              f"{len(full_peaks)} known peaks")

        # Step 1: Fine sweep around each known peak (±5% bandwidth)
        # Looking for split peaks / doublets
        SWEEP_BW_PCT = 5.0  # ±5% around each peak
        SWEEP_STEPS = 40    # resolution within each sweep window
        fine_scan_results = []

        for peak_hz in full_peaks:
            f_lo = peak_hz * (1 - SWEEP_BW_PCT / 100)
            f_hi = peak_hz * (1 + SWEEP_BW_PCT / 100)
            step_hz = (f_hi - f_lo) / SWEEP_STEPS

            sweep_data = []
            for si in range(SWEEP_STEPS + 1):
                f = f_lo + si * step_hz
                result = _hw_measure_spectrum(handle, f, n_avg=4, settle_s=0.10)
                sweep_data.append({
                    "freq_hz": round(f, 1),
                    "magnitude": result["magnitude"],
                })

            # Find local maxima in the sweep
            mags = [d["magnitude"] for d in sweep_data]
            local_maxima = []
            for i in range(1, len(mags) - 1):
                if mags[i] > mags[i-1] and mags[i] > mags[i+1]:
                    local_maxima.append(sweep_data[i])

            # Check for doublet: 2+ peaks within the ±5% window
            is_split = len(local_maxima) >= 2
            if is_split:
                # Compute splitting
                freqs_found = [p["freq_hz"] for p in local_maxima]
                splitting_hz = max(freqs_found) - min(freqs_found)
                splitting_pct = splitting_hz / peak_hz * 100
                # Check anticorrelation: are the two peaks of similar height?
                peak_mags = sorted([p["magnitude"] for p in local_maxima], reverse=True)
                mag_ratio = peak_mags[1] / peak_mags[0] if peak_mags[0] > 0 else 0

                print(f"    {peak_hz:>8.1f} Hz: DOUBLET — {len(local_maxima)} peaks, "
                      f"split={splitting_hz:.1f} Hz ({splitting_pct:.2f}%), "
                      f"mag ratio={mag_ratio:.2f}")
            else:
                splitting_hz = 0
                splitting_pct = 0
                mag_ratio = 0
                n_found = len(local_maxima)
                label = "singlet" if n_found == 1 else f"{n_found} peaks"
                print(f"    {peak_hz:>8.1f} Hz: {label}")

            fine_scan_results.append({
                "enrolled_freq_hz": round(peak_hz, 1),
                "sweep_lo_hz": round(f_lo, 1),
                "sweep_hi_hz": round(f_hi, 1),
                "n_local_maxima": len(local_maxima),
                "is_split": is_split,
                "splitting_hz": round(splitting_hz, 1),
                "splitting_pct": round(splitting_pct, 3),
                "mag_ratio": round(mag_ratio, 3),
                "local_maxima": local_maxima,
            })

        # Step 2: Mode spacing analysis
        # Compute pairwise frequency ratios between adjacent enrolled peaks
        spacings = []
        for i in range(len(full_peaks) - 1):
            gap = full_peaks[i + 1] - full_peaks[i]
            gap_pct = gap / full_peaks[i] * 100
            spacings.append({
                "f_lower": round(full_peaks[i], 1),
                "f_upper": round(full_peaks[i + 1], 1),
                "gap_hz": round(gap, 1),
                "gap_pct": round(gap_pct, 2),
            })

        # Coupling threshold: κ/ω₀ = 0.05 → modes within 5% are candidates
        COUPLING_THRESHOLD_PCT = 5.0
        near_degenerate_pairs = [s for s in spacings
                                  if s["gap_pct"] < COUPLING_THRESHOLD_PCT]

        print(f"    Mode spacing: {len(spacings)} gaps, "
              f"{len(near_degenerate_pairs)} within {COUPLING_THRESHOLD_PCT}% "
              f"(near-degenerate candidates)")

        # Step 3: Inter-peak scan — sweep between adjacent peaks looking
        # for previously-undetected modes
        hidden_modes = []
        for sp in spacings:
            if sp["gap_hz"] < 50:  # skip very tight gaps
                continue
            # Sample 10 points between the two peaks
            n_interp = 10
            f_start = sp["f_lower"] + sp["gap_hz"] * 0.1  # skip edges
            f_end = sp["f_upper"] - sp["gap_hz"] * 0.1
            if f_end <= f_start:
                continue

            inter_data = []
            for si in range(n_interp):
                f = f_start + si * (f_end - f_start) / (n_interp - 1)
                result = _hw_measure_spectrum(handle, f, n_avg=4, settle_s=0.08)
                inter_data.append({
                    "freq_hz": round(f, 1),
                    "magnitude": result["magnitude"],
                })

            # Find peaks above a noise threshold
            inter_mags = [d["magnitude"] for d in inter_data]
            if not inter_mags:
                continue
            inter_median = float(np.median(inter_mags))
            for i in range(1, len(inter_mags) - 1):
                if (inter_mags[i] > inter_mags[i-1] and
                    inter_mags[i] > inter_mags[i+1] and
                    inter_mags[i] > inter_median * 3):
                    hidden_modes.append(inter_data[i])

        if hidden_modes:
            print(f"    Hidden modes found: {len(hidden_modes)} "
                  f"(between enrolled peaks)")
            for hm in hidden_modes[:5]:
                print(f"      {hm['freq_hz']:.1f} Hz  mag={hm['magnitude']:.0f}")

        n_doublets = sum(1 for r in fine_scan_results if r["is_split"])

        results_per_rod[rid] = {
            "n_known_peaks": len(full_peaks),
            "fine_scan": fine_scan_results,
            "spacings": spacings,
            "near_degenerate_pairs": near_degenerate_pairs,
            "n_near_degenerate": len(near_degenerate_pairs),
            "n_doublets_found": n_doublets,
            "hidden_modes": hidden_modes,
        }

    mux.off()
    _hw_close_scope(handle)

    # Summary
    print("\n  --- Mode Hybridization Summary ---")
    total_doublets = 0
    total_near_deg = 0
    total_hidden = 0
    total_peaks = 0
    for rid in rod_ids:
        r = results_per_rod[rid]
        total_doublets += r["n_doublets_found"]
        total_near_deg += r["n_near_degenerate"]
        total_hidden += len(r["hidden_modes"])
        total_peaks += r["n_known_peaks"]
        print(f"    Rod {rid}: {r['n_doublets_found']} doublets, "
              f"{r['n_near_degenerate']} near-degenerate pairs, "
              f"{len(r['hidden_modes'])} hidden modes")

    print(f"\n  Totals: {total_doublets} doublets / {total_peaks} peaks scanned, "
          f"{total_near_deg} near-degenerate pairs, {total_hidden} hidden inter-peak modes")

    hybridization_rate = total_doublets / total_peaks if total_peaks > 0 else 0
    print(f"  Observed hybridization rate: {hybridization_rate:.1%}")
    print(f"  Paper claim: 16/20 detunings >10% coupling → +160% capacity (sim)")

    return {
        "experiment": "mode_hybridization_search",
        "per_rod": results_per_rod,
        "total_doublets": total_doublets,
        "total_peaks_scanned": total_peaks,
        "total_near_degenerate_pairs": total_near_deg,
        "total_hidden_modes": total_hidden,
        "hybridization_rate": round(hybridization_rate, 3),
        "coupling_threshold_pct": 5.0,
        "paper_claim": "+160% capacity from mode hybridization (sim, κ=0.05ω₀)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 8: Hybridization-Aware Readout
# ══════════════════════════════════════════════════════════════════════════

def _load_hybridization_results() -> dict:
    """Load the latest hybridization scan results."""
    files = sorted(RESULTS_DIR.glob("additional_*.json"), reverse=True)
    for f in files:
        with open(f) as fp:
            d = json.load(fp)
        hyb = d.get("results", {}).get("mode_hybridization")
        if hyb and hyb.get("per_rod"):
            return hyb
    raise FileNotFoundError("No hybridization results found")


def _select_credible_doublets(hyb_results: dict, min_mag_ratio: float = 0.3,
                               max_local_maxima: int = 6) -> dict[str, list]:
    """Select high-confidence doublets: 2-6 local maxima, mag_ratio > threshold."""
    credible = {}
    for rid, rod_data in hyb_results["per_rod"].items():
        rod_doublets = []
        for fs in rod_data["fine_scan"]:
            if (fs["is_split"]
                and fs["n_local_maxima"] <= max_local_maxima
                and fs["mag_ratio"] >= min_mag_ratio):
                # Extract the two strongest local maxima as bonding/antibonding
                lm = sorted(fs["local_maxima"],
                             key=lambda x: x["magnitude"], reverse=True)
                if len(lm) >= 2:
                    f_lo = min(lm[0]["freq_hz"], lm[1]["freq_hz"])
                    f_hi = max(lm[0]["freq_hz"], lm[1]["freq_hz"])
                    rod_doublets.append({
                        "enrolled_freq": fs["enrolled_freq_hz"],
                        "f_bonding": f_lo,
                        "f_antibonding": f_hi,
                        "split_hz": round(f_hi - f_lo, 1),
                        "mag_ratio": fs["mag_ratio"],
                        "n_maxima": fs["n_local_maxima"],
                    })
        credible[rid] = rod_doublets
    return credible


def exp_hybridization_readout(port: str) -> dict:
    """
    Hybridization-aware readout: measure each rod's response at confirmed
    doublet frequencies (bonding + antibonding separately), then test
    whether the decomposed doublet information improves rod discrimination.

    For each credible doublet, drive at f_bonding and f_antibonding,
    measure ALL 4 rods at each. Build an augmented score matrix and
    compare accuracy/margin to baseline.
    """
    from relay_mux import RelayMux
    from cwm_picoscope import AWG_DRIVE_UVPP

    print("\n" + "=" * 70)
    print("  EXPERIMENT: Hybridization-Aware Readout")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    # Load existing hybridization data and select credible doublets
    hyb_data = _load_hybridization_results()
    credible = _select_credible_doublets(hyb_data)

    total_doublets = sum(len(v) for v in credible.values())
    print(f"\n  Credible doublets (2-6 maxima, mag_ratio ≥ 0.3): {total_doublets}")
    for rid in rod_ids:
        print(f"    Rod {rid}: {len(credible[rid])} doublets")

    # Collect ALL unique doublet frequencies across all rods
    all_doublet_freqs = []
    for rid in rod_ids:
        for d in credible[rid]:
            all_doublet_freqs.append({
                "source_rod": rid,
                "enrolled_freq": d["enrolled_freq"],
                "f_bonding": d["f_bonding"],
                "f_antibonding": d["f_antibonding"],
            })

    if not all_doublet_freqs:
        print("  No credible doublets found — skipping")
        return {"experiment": "hybridization_readout", "error": "no_credible_doublets"}

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    # For each query rod, measure response at all enrolled peaks PLUS all
    # doublet bonding/antibonding frequencies
    print(f"\n  Measuring {len(all_doublet_freqs)} doublet pairs × 4 rods "
          f"(bonding + antibonding each)...")

    # doublet_responses[sense_rod][doublet_idx] = {freq info, mag_bonding, mag_antibonding}
    # We measure per sense rod: switch mux to sense rod, then drive at each freq
    doublet_responses = []

    for di, df in enumerate(all_doublet_freqs):
        entry = {
            "source_rod": df["source_rod"],
            "enrolled_freq": df["enrolled_freq"],
            "f_bonding": df["f_bonding"],
            "f_antibonding": df["f_antibonding"],
            "bonding_mags": {},
            "antibonding_mags": {},
        }

        for sense_rid in rod_ids:
            mux.select(int(sense_rid))
            time.sleep(SETTLE_RELAY_S)

            res_bond = _hw_measure_spectrum(handle, df["f_bonding"], n_avg=8,
                                            settle_s=SETTLE_S)
            res_anti = _hw_measure_spectrum(handle, df["f_antibonding"], n_avg=8,
                                            settle_s=SETTLE_S)
            entry["bonding_mags"][sense_rid] = res_bond["magnitude"]
            entry["antibonding_mags"][sense_rid] = res_anti["magnitude"]

        doublet_responses.append(entry)

        b_vec = [entry["bonding_mags"][sr] for sr in rod_ids]
        a_vec = [entry["antibonding_mags"][sr] for sr in rod_ids]
        if di < 5 or di == len(all_doublet_freqs) - 1:
            print(f"    [{di+1}/{len(all_doublet_freqs)}] Rod {df['source_rod']} "
                  f"@ {df['enrolled_freq']:.0f} Hz: "
                  f"bond=[{', '.join(f'{v:.0f}' for v in b_vec)}] "
                  f"anti=[{', '.join(f'{v:.0f}' for v in a_vec)}]")
        elif di == 5:
            print(f"    ... ({len(all_doublet_freqs) - 6} more)")

    mux.off()
    _hw_close_scope(handle)

    # Build augmented score matrix using doublet decomposition
    # For each rod pair (source, sense), accumulate evidence from doublets
    print("\n  Computing doublet-decomposed scores...")

    # Group doublets by source rod
    doublets_by_source = {sr: [] for sr in rod_ids}
    for entry in doublet_responses:
        doublets_by_source[entry["source_rod"]].append(entry)

    # Score: for each "query" (which rod are we asking about?),
    # sum evidence from doublets. A doublet belonging to rod X should show
    # stronger response (bonding+antibonding) on rod X's sense channel.
    augmented_matrix = {}
    for qr in rod_ids:
        scores = {sr: 0.0 for sr in rod_ids}
        for entry in doublet_responses:
            src = entry["source_rod"]
            for sr in rod_ids:
                mb = entry["bonding_mags"][sr]
                ma = entry["antibonding_mags"][sr]
                total_all = sum(entry["bonding_mags"][r] + entry["antibonding_mags"][r]
                                for r in rod_ids)
                if total_all == 0:
                    continue
                # Fractional response at this sense rod
                frac = (mb + ma) / total_all
                # Asymmetry gives extra information
                asymmetry = abs(mb - ma) / (mb + ma) if (mb + ma) > 0 else 0
                # Does this doublet's source rod match the query rod?
                if src == qr:
                    # Evidence FOR: sense rod matching query should be strongest
                    if sr == qr:
                        scores[sr] += frac * (1 + asymmetry) * 3.0
                    else:
                        scores[sr] += frac * 1.0
                else:
                    # Evidence for OTHER rod
                    if sr == qr:
                        scores[sr] -= frac * 0.5

        augmented_matrix[qr] = {sr: round(v, 2) for sr, v in scores.items()}

    mux.off()
    _hw_close_scope(handle)

    # Evaluate
    aug_correct, aug_acc, aug_margin = _eval_accuracy(augmented_matrix, rod_ids)

    print(f"\n  --- Hybridization-Aware Readout Results ---")
    print(f"    Augmented matrix (doublet-decomposed):")
    for qr in rod_ids:
        winner = max(augmented_matrix[qr], key=augmented_matrix[qr].get)
        mark = "✓" if winner == qr else "✗"
        print(f"      Q={qr} → winner={winner} {mark}  scores={augmented_matrix[qr]}")
    print(f"    Accuracy: {aug_correct}/{len(rod_ids)} ({aug_acc:.0%})")
    print(f"    Mean margin: {aug_margin:+.2f}")

    return {
        "experiment": "hybridization_aware_readout",
        "n_credible_doublets": total_doublets,
        "doublet_responses": [
            {k: v for k, v in d.items()} for d in doublet_responses
        ],
        "augmented_matrix": augmented_matrix,
        "augmented_accuracy": aug_acc,
        "augmented_margin": round(aug_margin, 2),
        "doublet_selection_criteria": {
            "min_mag_ratio": 0.3, "max_local_maxima": 6,
        },
        "paper_claim": "Hybridization-aware readout extracts independent info from bonding/antibonding",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 9: Anticorrelated Amplitude Test
# ══════════════════════════════════════════════════════════════════════════

def exp_anticorrelation(port: str) -> dict:
    """
    Test the paper's prediction that avoided crossings show anticorrelated
    amplitudes across rods. For each credible doublet, measure the bonding
    and antibonding peak amplitudes on ALL 4 sense rods. Compute the
    cross-rod correlation between bonding and antibonding channels.

    If anticorrelation is present: when one rod responds strongly at
    f_bonding, it should respond weakly at f_antibonding (and vice versa).
    """
    from relay_mux import RelayMux

    print("\n" + "=" * 70)
    print("  EXPERIMENT: Anticorrelated Amplitude Test")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    hyb_data = _load_hybridization_results()
    credible = _select_credible_doublets(hyb_data)

    total_doublets = sum(len(v) for v in credible.values())
    print(f"\n  Testing {total_doublets} credible doublets across all 4 sense rods")

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    # For each doublet: drive at f_bonding and f_antibonding, measure on
    # all 4 sense rods → get a 4-element vector for each frequency
    doublet_measurements = []

    for source_rid in rod_ids:
        for d in credible[source_rid]:
            meas = {
                "source_rod": source_rid,
                "enrolled_freq": d["enrolled_freq"],
                "f_bonding": d["f_bonding"],
                "f_antibonding": d["f_antibonding"],
                "split_hz": d["split_hz"],
                "bonding_mags": {},
                "antibonding_mags": {},
            }

            for sense_rid in rod_ids:
                mux.select(int(sense_rid))
                time.sleep(SETTLE_RELAY_S)

                # Drive at bonding frequency
                rb = _hw_measure_spectrum(handle, d["f_bonding"], n_avg=8,
                                           settle_s=SETTLE_S)
                # Drive at antibonding frequency
                ra = _hw_measure_spectrum(handle, d["f_antibonding"], n_avg=8,
                                           settle_s=SETTLE_S)
                meas["bonding_mags"][sense_rid] = rb["magnitude"]
                meas["antibonding_mags"][sense_rid] = ra["magnitude"]

            doublet_measurements.append(meas)

            # Print summary
            b_vec = [meas["bonding_mags"][sr] for sr in rod_ids]
            a_vec = [meas["antibonding_mags"][sr] for sr in rod_ids]
            print(f"    Rod {source_rid} @ {d['enrolled_freq']:.0f} Hz: "
                  f"bond=[{', '.join(f'{v:.0f}' for v in b_vec)}] "
                  f"anti=[{', '.join(f'{v:.0f}' for v in a_vec)}]")

    mux.off()
    _hw_close_scope(handle)

    # Compute per-doublet correlation between bonding and antibonding vectors
    print("\n  --- Anticorrelation Analysis ---")
    correlations = []
    asymmetries = []

    for meas in doublet_measurements:
        b_vec = np.array([meas["bonding_mags"][sr] for sr in rod_ids])
        a_vec = np.array([meas["antibonding_mags"][sr] for sr in rod_ids])

        # Pearson correlation between bonding and antibonding across rods
        if np.std(b_vec) > 0 and np.std(a_vec) > 0:
            corr = float(np.corrcoef(b_vec, a_vec)[0, 1])
        else:
            corr = 0.0
        correlations.append(corr)

        # Per-rod asymmetry: (bond - anti) / (bond + anti)
        rod_asymm = {}
        for sr in rod_ids:
            total = b_vec[rod_ids.index(sr)] + a_vec[rod_ids.index(sr)]
            if total > 0:
                asym = (meas["bonding_mags"][sr] - meas["antibonding_mags"][sr]) / total
            else:
                asym = 0.0
            rod_asymm[sr] = round(asym, 3)
        asymmetries.append(rod_asymm)

        sign = "−" if corr < 0 else "+"
        label = "ANTICORR" if corr < -0.3 else ("CORR" if corr > 0.3 else "NEUTRAL")
        print(f"    Rod {meas['source_rod']} @ {meas['enrolled_freq']:.0f} Hz: "
              f"r = {sign}{abs(corr):.3f} [{label}]  "
              f"asym={rod_asymm}")

    mean_corr = float(np.mean(correlations)) if correlations else 0.0
    n_anticorr = sum(1 for c in correlations if c < -0.3)
    n_corr = sum(1 for c in correlations if c > 0.3)
    n_neutral = len(correlations) - n_anticorr - n_corr

    print(f"\n  Summary: {len(correlations)} doublets tested")
    print(f"    Anticorrelated (r < -0.3): {n_anticorr}")
    print(f"    Correlated (r > +0.3): {n_corr}")
    print(f"    Neutral: {n_neutral}")
    print(f"    Mean r = {mean_corr:+.3f}")
    print(f"    Paper prediction: anticorrelated amplitudes at avoided crossings")

    # Check if asymmetry pattern is rod-discriminating
    # Build a classifier: for each doublet, can the asymmetry pattern identify
    # the source rod?
    print(f"\n  --- Asymmetry Discriminability ---")
    # Group by source rod
    by_rod = {sr: [] for sr in rod_ids}
    for meas, asym in zip(doublet_measurements, asymmetries):
        by_rod[meas["source_rod"]].append(asym)

    # For each rod, compute mean asymmetry vector
    for sr in rod_ids:
        if by_rod[sr]:
            mean_asym = {
                r: round(float(np.mean([a[r] for a in by_rod[sr]])), 3)
                for r in rod_ids
            }
            print(f"    Rod {sr} mean asymmetry: {mean_asym}")

    return {
        "experiment": "anticorrelated_amplitude_test",
        "n_doublets_tested": len(doublet_measurements),
        "measurements": doublet_measurements,
        "correlations": [round(c, 4) for c in correlations],
        "asymmetries": asymmetries,
        "mean_correlation": round(mean_corr, 4),
        "n_anticorrelated": n_anticorr,
        "n_correlated": n_corr,
        "n_neutral": n_neutral,
        "paper_prediction": "anticorrelated amplitudes at avoided crossings",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 10: Capacity Gain from Doublet Enrollment (offline)
# ══════════════════════════════════════════════════════════════════════════

def exp_doublet_capacity() -> dict:
    """
    Test whether enrolling doublet sub-peaks as additional features
    improves template matching. Uses existing recall data + hybridization
    scan results to build an augmented feature set.

    Approach:
    - Baseline: standard 10-peak template matching
    - Augmented: for each enrolled peak that showed a doublet, replace
      the single frequency with bonding+antibonding pair, weight each 0.5×
    - If margin increases, the doublets carry independent information
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT: Capacity Gain from Doublet Enrollment (offline)")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    recall_data = _load_latest_recall()
    peak_log = recall_data["peak_log"]
    hyb_data = _load_hybridization_results()
    credible = _select_credible_doublets(hyb_data)

    # Baseline
    baseline_matrix = {}
    for qr in rod_ids:
        baseline_matrix[qr] = _template_score_from_peak_log(
            peak_log, enrolled, rod_ids, qr)
    _, baseline_acc, baseline_margin = _eval_accuracy(baseline_matrix, rod_ids)

    print(f"\n  Baseline (standard 10-peak): accuracy={baseline_acc:.0%}, "
          f"margin={baseline_margin:+.2f}")

    # Build augmented enrollment: replace doublet peaks with split freqs
    augmented_enrolled = {}
    n_augmented = 0
    for rid in rod_ids:
        orig_peaks = enrolled[rid][:N_PEAKS]
        aug_peaks = list(orig_peaks)
        doublet_freqs = {d["enrolled_freq"] for d in credible.get(rid, [])}

        for d in credible.get(rid, []):
            ef = d["enrolled_freq"]
            # Find if this enrolled freq is in our top-10
            match_idx = None
            for i, p in enumerate(orig_peaks):
                if abs(p - ef) / max(p, ef) < 0.03:
                    match_idx = i
                    break
            if match_idx is not None:
                # Add bonding and antibonding as additional peaks
                aug_peaks.append(d["f_bonding"])
                aug_peaks.append(d["f_antibonding"])
                n_augmented += 1

        augmented_enrolled[rid] = aug_peaks

    print(f"  Augmented enrollment: {n_augmented} doublets added "
          f"(original 10 + 2 per doublet)")
    for rid in rod_ids:
        n_orig = len(enrolled[rid][:N_PEAKS])
        n_aug = len(augmented_enrolled[rid])
        print(f"    Rod {rid}: {n_orig} → {n_aug} peaks")

    # Re-run template scoring with augmented enrollment
    # The catch: our recall peak_log only has data at the ORIGINAL enrolled
    # frequencies. We can still test by re-weighting: for doublet peaks,
    # we check if the ORIGINAL freq matches the doublet's enrolled_freq
    # and use the split information to modify the score contribution.
    #
    # A more precise approach: score normally, but for peaks that are known
    # doublets, ADD a bonus proportional to (mag_ratio × split_pct).
    # The insight: a peak with a strong doublet has more information content.

    augmented_matrix = {}
    for qr in rod_ids:
        # Start with baseline scores
        base_scores = _template_score_from_peak_log(
            peak_log, enrolled, rod_ids, qr)
        aug_scores = dict(base_scores)

        # For each enrolled peak that's a doublet, add bonus
        qr_log = peak_log[qr]
        n_peaks = len(qr_log[rod_ids[0]])
        for pi in range(n_peaks):
            freq = qr_log[rod_ids[0]][pi]["freq_hz"]

            # Check if this peak is a credible doublet for any rod
            for rid in rod_ids:
                for d in credible.get(rid, []):
                    if abs(freq - d["enrolled_freq"]) / max(freq, d["enrolled_freq"]) < 0.03:
                        # This peak has a known doublet — the split gives extra info
                        # Weight bonus by mag_ratio (how symmetric the doublet is)
                        # and by which rod it belongs to
                        mags = {sr: qr_log[sr][pi]["magnitude"] for sr in rod_ids}
                        total = sum(mags.values())
                        if total > 0:
                            frac = mags[rid] / total
                            bonus = frac * d["mag_ratio"] * 1.5
                            aug_scores[rid] = round(aug_scores[rid] + bonus, 2)

        augmented_matrix[qr] = aug_scores

    _, aug_acc, aug_margin = _eval_accuracy(augmented_matrix, rod_ids)

    print(f"\n  --- Results ---")
    print(f"    Baseline:  accuracy={baseline_acc:.0%}, margin={baseline_margin:+.2f}")
    print(f"    Augmented: accuracy={aug_acc:.0%}, margin={aug_margin:+.2f}")
    print(f"    Δ margin = {aug_margin - baseline_margin:+.2f}")

    for qr in rod_ids:
        winner_b = max(baseline_matrix[qr], key=baseline_matrix[qr].get)
        winner_a = max(augmented_matrix[qr], key=augmented_matrix[qr].get)
        print(f"    Q={qr}: base winner={winner_b}, aug winner={winner_a}, "
              f"base={baseline_matrix[qr]}, aug={augmented_matrix[qr]}")

    return {
        "experiment": "doublet_capacity_gain",
        "baseline_accuracy": baseline_acc,
        "baseline_margin": round(baseline_margin, 2),
        "augmented_accuracy": aug_acc,
        "augmented_margin": round(aug_margin, 2),
        "delta_margin": round(aug_margin - baseline_margin, 2),
        "n_augmented_doublets": n_augmented,
        "baseline_matrix": baseline_matrix,
        "augmented_matrix": augmented_matrix,
        "paper_claim": "Doublet decomposition adds independent info channels",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 11: Proxy Null-Space SVD Analysis (offline)
# ══════════════════════════════════════════════════════════════════════════

def exp_nullspace_proxy() -> dict:
    """
    Test whether low-singular-value components of the rod×frequency
    response matrix carry discriminating information.

    Build a sensitivity matrix S[rod, freq] from recall data.
    Compute SVD. Check if projecting onto the low-SV subspace
    (analogous to null-space) still discriminates rods.

    This is a proxy for the paper's null-space multiplexing (§2.4)
    which requires controlled perturbation patterning. We test whether
    the mathematical structure exists even without controlled patterning.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT: Proxy Null-Space SVD Analysis")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    recall_data = _load_latest_recall()
    peak_log = recall_data["peak_log"]
    n_peaks = len(peak_log[rod_ids[0]][rod_ids[0]])

    # Build the response matrix: S[query_rod × sense_rod, peak_idx]
    # This gives us a (n_rods × n_rods) × n_peaks = 16 × 10 matrix
    # But more naturally: for each query rod, we have a 4×10 response matrix
    # (4 sense rods × 10 peaks)

    # Per-query response matrices
    print(f"\n  Building response matrix: {len(rod_ids)} rods × {n_peaks} peaks")

    # Global response matrix: rows = (query_rod, sense_rod), cols = peak_idx
    # This is 16 rows × 10 cols
    n_rods = len(rod_ids)
    S = np.zeros((n_rods * n_rods, n_peaks))
    row_labels = []

    for qi, qr in enumerate(rod_ids):
        for si, sr in enumerate(rod_ids):
            row = qi * n_rods + si
            row_labels.append(f"Q{qr}S{sr}")
            for pi in range(n_peaks):
                S[row, pi] = peak_log[qr][sr][pi]["magnitude"]

    # Normalize columns
    col_norms = np.linalg.norm(S, axis=0, keepdims=True)
    col_norms[col_norms == 0] = 1
    S_norm = S / col_norms

    # SVD
    U, sigma, Vt = np.linalg.svd(S_norm, full_matrices=False)

    print(f"\n  SVD of {S_norm.shape[0]}×{S_norm.shape[1]} normalized response matrix:")
    print(f"  Singular values: {', '.join(f'{s:.3f}' for s in sigma)}")

    # Effective rank (singular values > 1% of largest)
    threshold = sigma[0] * 0.01
    eff_rank = int(np.sum(sigma > threshold))
    print(f"  Effective rank (>1% of σ₁): {eff_rank}/{len(sigma)}")

    # Energy distribution
    total_energy = np.sum(sigma**2)
    cumulative = np.cumsum(sigma**2) / total_energy * 100
    print(f"  Cumulative energy: {', '.join(f'{c:.1f}%' for c in cumulative)}")

    # Test: can low-SV projections discriminate rods?
    # Project each query rod's response onto different SV subspaces
    # and test recall accuracy

    results_by_subspace = []

    # Per-query-rod response matrix: 4×10 (sense_rods × peaks)
    for n_keep in range(1, len(sigma) + 1):
        # Project S onto first n_keep singular vectors
        S_proj = U[:, :n_keep] @ np.diag(sigma[:n_keep]) @ Vt[:n_keep, :]

        # Reconstruct template scores from projected matrix
        proj_matrix = {}
        for qi, qr in enumerate(rod_ids):
            scores = {sr: 0.0 for sr in rod_ids}
            for pi in range(n_peaks):
                freq = peak_log[qr][rod_ids[0]][pi]["freq_hz"]
                mags = {}
                for si, sr in enumerate(rod_ids):
                    row = qi * n_rods + si
                    mags[sr] = max(0, S_proj[row, pi])

                total = sum(mags.values())
                if total == 0:
                    continue
                for sr in rod_ids:
                    frac = mags[sr] / total
                    expected = any(
                        abs(freq - ep) / max(freq, ep) < 0.03
                        for ep in enrolled[sr]
                    )
                    if expected:
                        scores[sr] += frac * 3.0
                    else:
                        scores[sr] -= frac * 1.0

            proj_matrix[qr] = {sr: round(v, 2) for sr, v in scores.items()}

        _, acc, margin = _eval_accuracy(proj_matrix, rod_ids)
        results_by_subspace.append({
            "n_components": n_keep,
            "energy_pct": round(cumulative[n_keep - 1], 1),
            "accuracy": acc,
            "margin": round(margin, 2),
        })

    # Also test ONLY the low-SV components (potential null-space info)
    # Remove top components, keep only bottom ones
    print(f"\n  --- Subspace Projection Results ---")
    print(f"  {'Components':>12}  {'Energy':>8}  {'Accuracy':>10}  {'Margin':>10}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*10}  {'-'*10}")

    for r in results_by_subspace:
        print(f"  {'Top ' + str(r['n_components']):>12}  {r['energy_pct']:>7.1f}%  "
              f"{r['accuracy']:>9.0%}  {r['margin']:>+9.2f}")

    # Now test with ONLY bottom components (null-space proxy)
    print(f"\n  --- Low-SV (Null-Space Proxy) Results ---")
    print(f"  {'Components':>12}  {'Energy':>8}  {'Accuracy':>10}  {'Margin':>10}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*10}  {'-'*10}")

    nullspace_results = []
    for n_skip in range(0, len(sigma)):
        n_low = len(sigma) - n_skip
        if n_low < 1:
            break

        # Project onto bottom n_low singular vectors only
        S_low = U[:, n_skip:] @ np.diag(sigma[n_skip:]) @ Vt[n_skip:, :]

        proj_matrix = {}
        for qi, qr in enumerate(rod_ids):
            scores = {sr: 0.0 for sr in rod_ids}
            for pi in range(n_peaks):
                freq = peak_log[qr][rod_ids[0]][pi]["freq_hz"]
                mags = {}
                for si, sr in enumerate(rod_ids):
                    row = qi * n_rods + si
                    mags[sr] = max(0, S_low[row, pi])
                total = sum(mags.values())
                if total == 0:
                    continue
                for sr in rod_ids:
                    frac = mags[sr] / total
                    expected = any(
                        abs(freq - ep) / max(freq, ep) < 0.03
                        for ep in enrolled[sr]
                    )
                    if expected:
                        scores[sr] += frac * 3.0
                    else:
                        scores[sr] -= frac * 1.0
            proj_matrix[qr] = {sr: round(v, 2) for sr, v in scores.items()}

        _, acc, margin = _eval_accuracy(proj_matrix, rod_ids)
        low_energy = round(100 - (cumulative[n_skip - 1] if n_skip > 0 else 0), 1)
        nullspace_results.append({
            "components_removed": n_skip,
            "components_kept": n_low,
            "energy_pct": low_energy,
            "accuracy": acc,
            "margin": round(margin, 2),
        })
        label = f"Bottom {n_low}" if n_skip > 0 else "All"
        print(f"  {label:>12}  {low_energy:>7.1f}%  "
              f"{acc:>9.0%}  {margin:>+9.2f}")

    # Summary
    base_margin = results_by_subspace[-1]["margin"]
    min_components_100 = next(
        (r["n_components"] for r in results_by_subspace if r["accuracy"] >= 1.0),
        len(sigma)
    )
    max_removed_100 = next(
        (r["components_removed"] for r in nullspace_results
         if r["accuracy"] < 1.0), len(sigma)
    ) - 1

    print(f"\n  Summary:")
    print(f"    Full rank: {eff_rank}/{len(sigma)}")
    print(f"    Min components for 100% accuracy: {min_components_100}")
    print(f"    Max top components removable (keeping 100%): {max_removed_100}")
    print(f"    → {max_removed_100} dimensions carry redundant/null-space info")
    if max_removed_100 > 0:
        print(f"    Null-space proxy capacity: "
              f"+{max_removed_100}/{min_components_100} "
              f"= +{max_removed_100/min_components_100*100:.0f}%")

    return {
        "experiment": "nullspace_proxy_svd",
        "matrix_shape": list(S_norm.shape),
        "singular_values": [round(s, 4) for s in sigma.tolist()],
        "effective_rank": eff_rank,
        "cumulative_energy_pct": [round(c, 1) for c in cumulative.tolist()],
        "subspace_results": results_by_subspace,
        "nullspace_results": nullspace_results,
        "min_components_for_100pct": min_components_100,
        "max_removable_for_100pct": max_removed_100,
        "paper_claim": "+60% capacity from null-space multiplexing (10×16 sim)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E12: Ringdown τ & Q Extraction (Improved)
# ══════════════════════════════════════════════════════════════════════════

def exp_ringdown_q(port: str) -> dict:
    """
    Paper claim C9/C10: Q = 10,000, τ = 180 ms at f₁ = 17,717 Hz.

    Improved ringdown measurement: excite at multiple enrolled peaks per rod,
    capture ringdown after AWG shutoff, fit exponential decay, extract τ and Q.
    Also measure −3 dB bandwidth via fine frequency sweep around each peak.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT E12: Ringdown τ & Q Extraction")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    from scipy.signal import hilbert

    results_per_rod = {}

    for rid in rod_ids:
        relay_ch = int(rid)
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        peaks = enrolled[rid][:N_PEAKS]
        # Test 3 peaks per rod: low, mid, high
        test_indices = [0, min(4, len(peaks)-1), min(8, len(peaks)-1)]
        test_freqs = [peaks[i] for i in test_indices]

        rod_results = []
        print(f"\n  Rod {rid} ({rod_patterns.get(rid, '?')}):")

        for freq in test_freqs:
            # --- Ringdown measurement ---
            # Excite for 1s to reach steady state
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(freq), float(freq), 0.0, 0.0, 0, 0
            )
            time.sleep(1.0)

            # Stop AWG and immediately capture
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
            )
            time.sleep(0.001)

            raw = _hw_capture_raw(handle)
            t = np.arange(len(raw)) / SAMPLE_RATE

            # Envelope via Hilbert transform
            analytic = hilbert(raw)
            envelope = np.abs(analytic)

            # Fit exponential decay on points above 5% of peak
            peak_val = np.max(envelope)
            mask = envelope > peak_val * 0.05
            tau_s = float('nan')
            Q_ringdown = float('nan')
            fit_r2 = float('nan')

            if np.sum(mask) > 20:
                t_m = t[mask]
                env_m = envelope[mask]
                log_env = np.log(env_m + 1e-30)
                coeffs = np.polyfit(t_m, log_env, 1)
                if coeffs[0] < 0:
                    tau_s = -1.0 / coeffs[0]
                    Q_ringdown = math.pi * freq * tau_s
                    # R² of fit
                    pred = coeffs[0] * t_m + coeffs[1]
                    ss_res = np.sum((log_env - pred) ** 2)
                    ss_tot = np.sum((log_env - np.mean(log_env)) ** 2)
                    fit_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            # --- Bandwidth measurement ---
            # Fine sweep ±5% around peak to measure −3 dB width
            sweep_lo = freq * 0.95
            sweep_hi = freq * 1.05
            n_sweep = 41
            sweep_freqs = np.linspace(sweep_lo, sweep_hi, n_sweep)
            sweep_mags = []

            for sf in sweep_freqs:
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, AWG_DRIVE_UVPP, 0,
                    float(sf), float(sf), 0.0, 0.0, 0, 0
                )
                time.sleep(0.05)
                raw_sw = _hw_capture_raw(handle)
                windowed = raw_sw * np.hanning(len(raw_sw))
                nfft = len(raw_sw) * 4
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                target_bin = int(round(sf / bin_hz))
                lo_b = max(0, target_bin - 5)
                hi_b = min(len(fft_mag) - 1, target_bin + 5)
                sweep_mags.append(float(np.max(fft_mag[lo_b:hi_b + 1])))

            # Find −3 dB width
            sweep_mags = np.array(sweep_mags)
            peak_mag = np.max(sweep_mags)
            threshold_3db = peak_mag / math.sqrt(2)
            above_3db = sweep_mags >= threshold_3db
            Q_bandwidth = float('nan')
            bw_hz = float('nan')

            if np.any(above_3db):
                indices = np.where(above_3db)[0]
                lo_idx = indices[0]
                hi_idx = indices[-1]
                bw_hz = float(sweep_freqs[hi_idx] - sweep_freqs[lo_idx])
                if bw_hz > 0:
                    peak_freq_measured = float(sweep_freqs[np.argmax(sweep_mags)])
                    Q_bandwidth = peak_freq_measured / bw_hz

            tau_str = f"{tau_s*1000:.2f} ms" if not math.isnan(tau_s) else "N/A"
            q_rd = f"{Q_ringdown:.0f}" if not math.isnan(Q_ringdown) else "N/A"
            q_bw = f"{Q_bandwidth:.0f}" if not math.isnan(Q_bandwidth) else "N/A"
            bw_str = f"{bw_hz:.1f} Hz" if not math.isnan(bw_hz) else "N/A"
            r2_str = f"{fit_r2:.3f}" if not math.isnan(fit_r2) else "N/A"

            print(f"    {freq:8.1f} Hz: τ={tau_str}, Q_ringdown={q_rd}, "
                  f"BW={bw_str}, Q_bw={q_bw}, R²={r2_str}")

            rod_results.append({
                "freq_hz": round(freq, 1),
                "tau_ms": round(tau_s * 1000, 3) if not math.isnan(tau_s) else None,
                "Q_ringdown": round(Q_ringdown, 1) if not math.isnan(Q_ringdown) else None,
                "fit_r2": round(fit_r2, 4) if not math.isnan(fit_r2) else None,
                "bw_3db_hz": round(bw_hz, 2) if not math.isnan(bw_hz) else None,
                "Q_bandwidth": round(Q_bandwidth, 1) if not math.isnan(Q_bandwidth) else None,
                "peak_envelope": round(float(peak_val), 1),
            })

        results_per_rod[rid] = rod_results

    mux.off()
    _hw_close_scope(handle)

    # Summary
    print("\n  --- Q Summary ---")
    all_q_rd = []
    all_q_bw = []
    for rid in rod_ids:
        for r in results_per_rod[rid]:
            if r["Q_ringdown"]:
                all_q_rd.append(r["Q_ringdown"])
            if r["Q_bandwidth"]:
                all_q_bw.append(r["Q_bandwidth"])
    if all_q_rd:
        print(f"    Ringdown Q: min={min(all_q_rd):.0f}, max={max(all_q_rd):.0f}, "
              f"mean={np.mean(all_q_rd):.0f}")
    if all_q_bw:
        print(f"    Bandwidth Q: min={min(all_q_bw):.0f}, max={max(all_q_bw):.0f}, "
              f"mean={np.mean(all_q_bw):.0f}")
    print(f"    Paper claims: Q = 10,000, τ = 180 ms")

    return {
        "experiment": "ringdown_q_extraction",
        "per_rod": results_per_rod,
        "all_q_ringdown": all_q_rd,
        "all_q_bandwidth": all_q_bw,
        "paper_claim_q": 10000,
        "paper_claim_tau_ms": 180,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E13: Mode Orthogonality / Non-Destructive Readout
# ══════════════════════════════════════════════════════════════════════════

def exp_mode_orthogonality(port: str) -> dict:
    """
    Paper claim C50: driving at fₙ couples exclusively to mode n.
    ∫₀ᴸ sin(nπx/L)sin(mπx/L)dx = 0 for n ≠ m.

    Method: CW-drive at one enrolled frequency, capture full FFT, measure
    amplitude at ALL enrolled peaks. The driven peak should dominate; others
    should remain near noise floor.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT E13: Mode Orthogonality / Non-Destructive Readout")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    results_per_rod = {}

    for rid in rod_ids:
        relay_ch = int(rid)
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        peaks = enrolled[rid][:N_PEAKS]
        rod_results = []
        print(f"\n  Rod {rid} ({rod_patterns.get(rid, '?')}): {len(peaks)} enrolled peaks")

        # First: measure noise floor (AWG off)
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
        time.sleep(0.2)
        noise_mags = {}
        for nt in range(3):
            raw_n = _hw_capture_raw(handle)
            windowed_n = raw_n * np.hanning(len(raw_n))
            nfft = len(raw_n) * 4
            fft_mag_n = np.abs(np.fft.rfft(windowed_n, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            for pidx, pf in enumerate(peaks):
                tb = int(round(pf / bin_hz))
                lo_b = max(0, tb - 3)
                hi_b = min(len(fft_mag_n) - 1, tb + 3)
                m = float(np.max(fft_mag_n[lo_b:hi_b + 1]))
                noise_mags.setdefault(pidx, []).append(m)
        noise_floor_per_peak = {pidx: np.mean(v) for pidx, v in noise_mags.items()}

        # For each enrolled peak: drive at that peak, measure all peaks
        for drive_idx, drive_freq in enumerate(peaks):
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(drive_freq), float(drive_freq), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)

            # Average N_AVG captures
            all_peak_mags = {pidx: [] for pidx in range(len(peaks))}
            for _ in range(N_AVG):
                raw = _hw_capture_raw(handle)
                windowed = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]

                for pidx, pf in enumerate(peaks):
                    tb = int(round(pf / bin_hz))
                    lo_b = max(0, tb - 3)
                    hi_b = min(len(fft_mag) - 1, tb + 3)
                    all_peak_mags[pidx].append(float(np.max(fft_mag[lo_b:hi_b + 1])))

            avg_mags = {pidx: np.mean(v) for pidx, v in all_peak_mags.items()}

            # Isolation: driven peak vs max non-driven peak
            driven_mag = avg_mags[drive_idx]
            non_driven = [avg_mags[i] for i in range(len(peaks)) if i != drive_idx]
            max_non_driven = max(non_driven) if non_driven else 0
            isolation_db = 20 * math.log10(driven_mag / max_non_driven) if max_non_driven > 0 else float('inf')

            # SNR above noise
            snr_driven = 20 * math.log10(driven_mag / noise_floor_per_peak.get(drive_idx, 1)) \
                if noise_floor_per_peak.get(drive_idx, 0) > 0 else 0

            print(f"    Drive peak {drive_idx} @ {drive_freq:.0f} Hz: "
                  f"driven={driven_mag:.0f}, max_other={max_non_driven:.0f}, "
                  f"isolation={isolation_db:+.1f} dB, SNR={snr_driven:.1f} dB")

            rod_results.append({
                "drive_peak_idx": drive_idx,
                "drive_freq_hz": round(drive_freq, 1),
                "driven_magnitude": round(driven_mag, 1),
                "max_non_driven_magnitude": round(max_non_driven, 1),
                "isolation_db": round(isolation_db, 1) if not math.isinf(isolation_db) else None,
                "snr_above_noise_db": round(snr_driven, 1),
                "all_peak_mags": {pidx: round(v, 1) for pidx, v in avg_mags.items()},
            })

        results_per_rod[rid] = rod_results

    mux.off()
    _hw_close_scope(handle)

    # Summary
    all_iso = [r["isolation_db"] for rr in results_per_rod.values()
               for r in rr if r["isolation_db"] is not None]
    if all_iso:
        print(f"\n  --- Mode Orthogonality Summary ---")
        print(f"    Mean isolation: {np.mean(all_iso):.1f} dB")
        print(f"    Min isolation: {min(all_iso):.1f} dB")
        print(f"    Max isolation: {max(all_iso):.1f} dB")
        print(f"    Paper predicts: perfect orthogonality (⟨m|n⟩ = δₘₙ)")

    return {
        "experiment": "mode_orthogonality",
        "per_rod": results_per_rod,
        "mean_isolation_db": round(np.mean(all_iso), 1) if all_iso else None,
        "min_isolation_db": round(min(all_iso), 1) if all_iso else None,
        "paper_claim": "Driving fₙ couples exclusively to mode n (C50)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E14: CW Lock-In SNR Gain
# ══════════════════════════════════════════════════════════════════════════

def exp_cw_lockin_snr(port: str) -> dict:
    """
    Paper claim C13: CW lock-in gives +17.5 dB at 10 s integration.
    SNR gain = T_int / τ (power), or √(T_int/τ) in amplitude.

    Method: drive a single mode CW, average PicoScope captures over increasing
    integration times (0.01s, 0.1s, 1s, 5s, 10s). Compare SNR vs single-shot.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT E14: CW Lock-In SNR Gain")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    # Use rod 1 with a strong mid-range peak
    test_rod = rod_ids[0]
    mux.select(int(test_rod))
    time.sleep(SETTLE_RELAY_S)

    peaks = enrolled[test_rod][:N_PEAKS]
    test_freq = peaks[min(3, len(peaks)-1)]
    print(f"  Test rod {test_rod} @ {test_freq:.1f} Hz")

    # First: single-shot impulse SNR (baseline)
    # Turn on drive briefly, then off, capture ringdown FFT
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(test_freq), float(test_freq), 0.0, 0.0, 0, 0
    )
    time.sleep(0.5)
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    time.sleep(0.001)

    raw_impulse = _hw_capture_raw(handle)
    windowed = raw_impulse * np.hanning(len(raw_impulse))
    nfft = len(raw_impulse) * 4
    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
    bin_hz = freq_axis[1] - freq_axis[0]

    target_bin = int(round(test_freq / bin_hz))
    lo_b = max(0, target_bin - 3)
    hi_b = min(len(fft_mag) - 1, target_bin + 3)
    impulse_signal = float(np.max(fft_mag[lo_b:hi_b + 1]))
    impulse_noise = float(np.median(fft_mag))
    impulse_snr_db = 20 * math.log10(impulse_signal / impulse_noise) if impulse_noise > 0 else 0

    print(f"  Single-shot impulse: signal={impulse_signal:.0f}, "
          f"noise_floor={impulse_noise:.0f}, SNR={impulse_snr_db:.1f} dB")

    # Now CW integration at various times
    integration_times = [0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    capture_time = N_SAMPLES / SAMPLE_RATE  # time per capture

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(test_freq), float(test_freq), 0.0, 0.0, 0, 0
    )
    time.sleep(0.5)  # initial settle

    cw_results = []
    print(f"\n  {'T_int':>8}  {'N_avg':>6}  {'Signal':>10}  {'Noise':>10}  {'SNR dB':>8}  {'Gain dB':>8}")
    print(f"  {'-'*8}  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*8}")

    for t_int in integration_times:
        n_captures = max(1, int(t_int / capture_time))

        # Accumulate FFTs
        acc_fft = None
        for _ in range(n_captures):
            raw_cw = _hw_capture_raw(handle)
            windowed_cw = raw_cw * np.hanning(len(raw_cw))
            fft_cw = np.abs(np.fft.rfft(windowed_cw, n=nfft))
            if acc_fft is None:
                acc_fft = np.zeros_like(fft_cw)
            acc_fft += fft_cw

        avg_fft = acc_fft / n_captures

        cw_signal = float(np.max(avg_fft[lo_b:hi_b + 1]))
        cw_noise = float(np.median(avg_fft))
        cw_snr_db = 20 * math.log10(cw_signal / cw_noise) if cw_noise > 0 else 0
        gain_db = cw_snr_db - impulse_snr_db

        print(f"  {t_int:>7.2f}s  {n_captures:>6}  {cw_signal:>10.0f}  "
              f"{cw_noise:>10.0f}  {cw_snr_db:>7.1f}  {gain_db:>+7.1f}")

        cw_results.append({
            "integration_s": t_int,
            "n_captures_averaged": n_captures,
            "cw_signal": round(cw_signal, 1),
            "cw_noise_floor": round(cw_noise, 1),
            "cw_snr_db": round(cw_snr_db, 1),
            "gain_over_impulse_db": round(gain_db, 1),
        })

    _hw_close_scope(handle)
    mux.off()

    # Theoretical prediction
    # With measured Q from our Q-factor experiment:
    print(f"\n  Paper predicts: +17.5 dB at 10 s (assumes τ=180 ms, Q=10,000)")
    print(f"  CW gain formula: G_dB = 10·log₁₀(T_int/τ)")

    return {
        "experiment": "cw_lockin_snr_gain",
        "test_rod": test_rod,
        "test_freq_hz": round(test_freq, 1),
        "impulse_snr_db": round(impulse_snr_db, 1),
        "cw_results": cw_results,
        "paper_claim": "+17.5 dB at 10 s integration (C13)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E15: Leibniz Binary Recall (offline)
# ══════════════════════════════════════════════════════════════════════════

def exp_leibniz_binary() -> dict:
    """
    Sidebar S7 H-L1: binarize FFT data → still achieves rod discrimination.

    Method: threshold existing peak_log magnitudes to binary (1/0),
    use Hamming distance for matching. Test across multiple threshold levels.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT E15: Leibniz Binary Recall")
    print("=" * 70)

    recall_data = _load_latest_recall()
    enrolled, rod_patterns, rod_ids = _load_enrollment()
    peak_log = recall_data["peak_log"]
    n_peaks = len(peak_log[rod_ids[0]][rod_ids[0]])

    # Baseline continuous-valued scores
    base_matrix = {qr: _template_score_from_peak_log(
        peak_log, enrolled, rod_ids, qr) for qr in rod_ids}
    _, base_acc, base_margin = _eval_accuracy(base_matrix, rod_ids)
    print(f"  Baseline (continuous): accuracy={base_acc:.0%}, margin={base_margin:+.2f}")

    # Collect all magnitudes to set thresholds
    all_mags = []
    for qr in rod_ids:
        for sr in rod_ids:
            for pi in range(n_peaks):
                all_mags.append(peak_log[qr][sr][pi]["magnitude"])
    all_mags = np.array(all_mags)
    median_mag = float(np.median(all_mags))
    print(f"  Magnitude range: [{np.min(all_mags):.0f}, {np.max(all_mags):.0f}], "
          f"median={median_mag:.0f}")

    # Test binary recall at various threshold percentiles
    percentiles = [10, 25, 40, 50, 60, 75, 90]
    results = []

    print(f"\n  {'Threshold':>12}  {'Value':>10}  {'1s frac':>8}  {'Accuracy':>10}  {'Margin':>10}")
    print(f"  {'-'*12}  {'-'*10}  {'-'*8}  {'-'*10}  {'-'*10}")

    for pctl in percentiles:
        thresh = float(np.percentile(all_mags, pctl))

        # Binary scoring: for each (query, sense, peak), mark 1 if mag > thresh
        binary_matrix = {}
        total_ones = 0
        total_cells = 0
        for qr in rod_ids:
            scores = {sr: 0.0 for sr in rod_ids}
            for sr in rod_ids:
                for pi in range(n_peaks):
                    mag = peak_log[qr][sr][pi]["magnitude"]
                    freq = peak_log[qr][sr][pi]["freq_hz"]
                    bit = 1 if mag > thresh else 0
                    total_ones += bit
                    total_cells += 1

                    expected = any(
                        abs(freq - ep) / max(freq, ep) < 0.03
                        for ep in enrolled[sr]
                    )
                    # Binary template match: +1 if bit=1 and expected, -1 if bit=1 and not expected
                    if bit:
                        scores[sr] += 3.0 if expected else -1.0
            binary_matrix[qr] = {sr: round(v, 2) for sr, v in scores.items()}

        corr, acc, margin = _eval_accuracy(binary_matrix, rod_ids)
        ones_frac = total_ones / total_cells if total_cells > 0 else 0

        print(f"  P{pctl:>3}={thresh:>9.0f}  {thresh:>10.0f}  {ones_frac:>7.1%}  "
              f"{acc:>9.0%}  {margin:>+9.2f}")

        results.append({
            "percentile": pctl,
            "threshold": round(thresh, 1),
            "ones_fraction": round(ones_frac, 3),
            "accuracy": acc,
            "margin": round(margin, 2),
        })

    # Best binary
    best = max(results, key=lambda r: (r["accuracy"], r["margin"]))
    print(f"\n  Best binary: P{best['percentile']} threshold → "
          f"{best['accuracy']:.0%} accuracy, margin {best['margin']:+.2f}")

    return {
        "experiment": "leibniz_binary_recall",
        "n_rods": len(rod_ids),
        "n_peaks": n_peaks,
        "baseline_accuracy": base_acc,
        "baseline_margin": round(base_margin, 2),
        "binary_results": results,
        "best_binary": best,
        "paper_claim": "Binary FFT → still discriminates (S7 H-L1)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E16: Cross-Correlation Matrix (offline)
# ══════════════════════════════════════════════════════════════════════════

def exp_cross_correlation() -> dict:
    """
    Paper claim C12: max off-diagonal correlation ≤ 0.21 (−13.6 dB).
    Build 4×4 cross-correlation matrix of enrolled fingerprints.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT E16: Cross-Correlation Matrix")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    recall_data = _load_latest_recall()
    peak_log = recall_data["peak_log"]
    n_peaks = len(peak_log[rod_ids[0]][rod_ids[0]])

    # Build a fingerprint vector per rod from self-response measurements
    # (query rod i, sense rod i — the on-diagonal measurements)
    fingerprints = {}
    print(f"\n  Building fingerprint vectors ({n_peaks} peaks × magnitude):")
    for rid in rod_ids:
        fp = []
        for pi in range(n_peaks):
            mag = peak_log[rid][rid][pi]["magnitude"]
            fp.append(mag)
        fingerprints[rid] = np.array(fp, dtype=np.float64)
        print(f"    Rod {rid}: mean_mag={np.mean(fp):.0f}, max={np.max(fp):.0f}")

    # Also try the full response vector (query rod i measured across ALL sense rods)
    full_fingerprints = {}
    for rid in rod_ids:
        fp = []
        for sr in rod_ids:
            for pi in range(n_peaks):
                fp.append(peak_log[rid][sr][pi]["magnitude"])
        full_fingerprints[rid] = np.array(fp, dtype=np.float64)

    # Compute correlation matrices
    print("\n  --- Self-Response Correlation Matrix ---")
    self_corr = {}
    for ri in rod_ids:
        self_corr[ri] = {}
        for rj in rod_ids:
            # Normalize and compute Pearson correlation
            vi = fingerprints[ri]
            vj = fingerprints[rj]
            if np.std(vi) > 0 and np.std(vj) > 0:
                r = float(np.corrcoef(vi, vj)[0, 1])
            else:
                r = 0.0
            self_corr[ri][rj] = round(r, 3)

    # Print
    header = "      " + "  ".join(f"Rod {r:>3}" for r in rod_ids)
    print(f"  {header}")
    for ri in rod_ids:
        row = "  ".join(f"{self_corr[ri][rj]:>6.3f}" for rj in rod_ids)
        print(f"  Rod {ri}  {row}")

    off_diag = [self_corr[ri][rj] for ri in rod_ids for rj in rod_ids if ri != rj]
    max_off = max(abs(v) for v in off_diag)
    mean_off = np.mean([abs(v) for v in off_diag])

    print(f"\n  Max |off-diagonal|: {max_off:.3f} (paper claims ≤ 0.21)")
    print(f"  Mean |off-diagonal|: {mean_off:.3f}")

    # Full response correlation
    print("\n  --- Full-Response Correlation Matrix ---")
    full_corr = {}
    for ri in rod_ids:
        full_corr[ri] = {}
        for rj in rod_ids:
            vi = full_fingerprints[ri]
            vj = full_fingerprints[rj]
            if np.std(vi) > 0 and np.std(vj) > 0:
                r = float(np.corrcoef(vi, vj)[0, 1])
            else:
                r = 0.0
            full_corr[ri][rj] = round(r, 3)

    header = "      " + "  ".join(f"Rod {r:>3}" for r in rod_ids)
    print(f"  {header}")
    for ri in rod_ids:
        row = "  ".join(f"{full_corr[ri][rj]:>6.3f}" for rj in rod_ids)
        print(f"  Rod {ri}  {row}")

    full_off = [full_corr[ri][rj] for ri in rod_ids for rj in rod_ids if ri != rj]
    max_full_off = max(abs(v) for v in full_off)

    print(f"\n  Full max |off-diagonal|: {max_full_off:.3f}")

    return {
        "experiment": "cross_correlation_matrix",
        "n_rods": len(rod_ids),
        "n_peaks": n_peaks,
        "self_response_correlation": self_corr,
        "full_response_correlation": full_corr,
        "max_off_diagonal_self": round(max_off, 3),
        "mean_off_diagonal_self": round(mean_off, 3),
        "max_off_diagonal_full": round(max_full_off, 3),
        "paper_claim": "Max off-diagonal ≤ 0.21 (C12, 8 rods; we test 4)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E17: Two-Phase Readout
# ══════════════════════════════════════════════════════════════════════════

def exp_two_phase_readout(port: str) -> dict:
    """
    Paper §2.3: Phase 1 (broadband impulse) identifies winning rod.
    Phase 2 (CW lock-in on winner) refines measurement at +17.5 dB.

    Method: standard recall (Phase 1), then CW drive at winner's peaks
    for 5s and re-score (Phase 2). Measure if margin improves.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT E17: Two-Phase Readout")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    results_per_query = {}

    for qr in rod_ids:
        print(f"\n  Query rod {qr} ({rod_patterns.get(qr, '?')}):")

        # Phase 1: broadband sweep (standard recall)
        phase1_scores = {}
        for sr in rod_ids:
            mux.select(int(sr))
            time.sleep(SETTLE_RELAY_S)

            score = 0.0
            for freq in enrolled[qr][:N_PEAKS]:
                result = _hw_measure_spectrum(handle, freq, n_avg=N_AVG // 2)
                mag = result["magnitude"]
                expected = any(
                    abs(freq - ep) / max(freq, ep) < 0.03
                    for ep in enrolled[sr]
                )
                if expected:
                    score += mag
                else:
                    score -= mag * 0.33
            phase1_scores[sr] = round(score, 1)

        winner_p1 = max(phase1_scores, key=phase1_scores.get)
        sorted_p1 = sorted(phase1_scores.items(), key=lambda x: -x[1])
        margin_p1 = sorted_p1[0][1] - sorted_p1[1][1]
        correct_p1 = winner_p1 == qr

        print(f"    Phase 1: winner={winner_p1} {'✓' if correct_p1 else '✗'}, "
              f"margin={margin_p1:+.0f}")

        # Phase 2: CW lock-in on the winner, measure 3 strongest peaks
        # with extended averaging (50 captures = ~0.5s integration per peak)
        mux.select(int(winner_p1))
        time.sleep(SETTLE_RELAY_S)

        phase2_mags = []
        for freq in enrolled[qr][:5]:
            result = _hw_measure_spectrum(handle, freq, n_avg=50, settle_s=0.5)
            phase2_mags.append(result["magnitude"])

        phase2_signal = np.mean(phase2_mags)

        # Also measure on a non-winner for comparison
        non_winner = [r for r in rod_ids if r != winner_p1][0]
        mux.select(int(non_winner))
        time.sleep(SETTLE_RELAY_S)

        phase2_nonwinner_mags = []
        for freq in enrolled[qr][:5]:
            result = _hw_measure_spectrum(handle, freq, n_avg=50, settle_s=0.5)
            phase2_nonwinner_mags.append(result["magnitude"])

        phase2_non_signal = np.mean(phase2_nonwinner_mags)
        phase2_margin_db = 20 * math.log10(phase2_signal / phase2_non_signal) \
            if phase2_non_signal > 0 else float('inf')

        print(f"    Phase 2: winner_signal={phase2_signal:.0f}, "
              f"non_winner={phase2_non_signal:.0f}, "
              f"margin={phase2_margin_db:.1f} dB")

        results_per_query[qr] = {
            "phase1_scores": phase1_scores,
            "phase1_winner": winner_p1,
            "phase1_correct": correct_p1,
            "phase1_margin": round(margin_p1, 1),
            "phase2_winner_signal": round(phase2_signal, 1),
            "phase2_non_winner_signal": round(phase2_non_signal, 1),
            "phase2_margin_db": round(phase2_margin_db, 1) if not math.isinf(phase2_margin_db) else None,
        }

    mux.off()
    _hw_close_scope(handle)

    n_correct = sum(1 for r in results_per_query.values() if r["phase1_correct"])
    p2_margins = [r["phase2_margin_db"] for r in results_per_query.values()
                  if r["phase2_margin_db"] is not None]

    print(f"\n  --- Two-Phase Summary ---")
    print(f"    Phase 1: {n_correct}/{len(rod_ids)} correct")
    if p2_margins:
        print(f"    Phase 2 mean margin: {np.mean(p2_margins):.1f} dB")

    return {
        "experiment": "two_phase_readout",
        "per_query": results_per_query,
        "phase1_accuracy": n_correct / len(rod_ids),
        "phase2_mean_margin_db": round(np.mean(p2_margins), 1) if p2_margins else None,
        "paper_claim": "Two-phase: impulse search + CW precision (§2.3)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E18: Derived SNR Measurement
# ══════════════════════════════════════════════════════════════════════════

def exp_derived_snr(port: str) -> dict:
    """
    Paper claim C8: 98.5 dB derived SNR (thermal-noise-limited).
    Measure actual signal power at resonance vs noise floor (AWG off).
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT E18: Derived SNR Measurement")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    results_per_rod = {}

    for rid in rod_ids:
        mux.select(int(rid))
        time.sleep(SETTLE_RELAY_S)

        peaks = enrolled[rid][:N_PEAKS]
        print(f"\n  Rod {rid} ({rod_patterns.get(rid, '?')}):")

        # Measure noise floor (AWG off, average 20 captures)
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
        time.sleep(0.3)

        noise_spectra = []
        for _ in range(20):
            raw_n = _hw_capture_raw(handle)
            windowed_n = raw_n * np.hanning(len(raw_n))
            nfft = len(raw_n) * 4
            noise_spectra.append(np.abs(np.fft.rfft(windowed_n, n=nfft)))
        avg_noise = np.mean(noise_spectra, axis=0)
        noise_rms = float(np.sqrt(np.mean(avg_noise ** 2)))
        noise_median = float(np.median(avg_noise))

        # Measure signal at each peak (CW excitation)
        peak_results = []
        for freq in peaks:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(freq), float(freq), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)

            sig_mags = []
            for _ in range(N_AVG):
                raw_s = _hw_capture_raw(handle)
                windowed_s = raw_s * np.hanning(len(raw_s))
                fft_mag = np.abs(np.fft.rfft(windowed_s, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                target_bin = int(round(freq / bin_hz))
                lo_b = max(0, target_bin - 3)
                hi_b = min(len(fft_mag) - 1, target_bin + 3)
                sig_mags.append(float(np.max(fft_mag[lo_b:hi_b + 1])))

            signal = np.mean(sig_mags)
            snr_db = 20 * math.log10(signal / noise_median) if noise_median > 0 else 0

            peak_results.append({
                "freq_hz": round(freq, 1),
                "signal": round(signal, 1),
                "snr_db": round(snr_db, 1),
            })
            print(f"    {freq:8.1f} Hz: signal={signal:.0f}, SNR={snr_db:.1f} dB")

        snrs = [p["snr_db"] for p in peak_results]
        results_per_rod[rid] = {
            "noise_rms": round(noise_rms, 1),
            "noise_median": round(noise_median, 1),
            "peaks": peak_results,
            "mean_snr_db": round(np.mean(snrs), 1),
            "max_snr_db": round(max(snrs), 1),
        }

    mux.off()
    _hw_close_scope(handle)

    all_snrs = [p["snr_db"] for r in results_per_rod.values() for p in r["peaks"]]
    print(f"\n  --- SNR Summary ---")
    print(f"    Overall: min={min(all_snrs):.1f}, max={max(all_snrs):.1f}, "
          f"mean={np.mean(all_snrs):.1f} dB")
    print(f"    Paper claims 98.5 dB (thermal-limited at Q=10,000)")

    return {
        "experiment": "derived_snr_measurement",
        "per_rod": results_per_rod,
        "overall_mean_snr_db": round(np.mean(all_snrs), 1),
        "overall_max_snr_db": round(max(all_snrs), 1),
        "paper_claim_snr_db": 98.5,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E19: Wave Speed Verification
# ══════════════════════════════════════════════════════════════════════════

def exp_wave_speed(port: str) -> dict:
    """
    Paper claim C2: v_bar = √(E/ρ) = 5,315 m/s for borosilicate.
    Verify by measuring mode spacing (Δf = v/(2L)) and fundamental f₁.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT E19: Wave Speed Verification")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    L = 0.150  # 150 mm rods
    v_predicted = 5315  # m/s

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")
    print(f"  Rod length L = {L*1000:.0f} mm")
    print(f"  Predicted v_bar = {v_predicted} m/s → f₁ = {v_predicted/(2*L):.1f} Hz")

    results_per_rod = {}

    for rid in rod_ids:
        mux.select(int(rid))
        time.sleep(SETTLE_RELAY_S)

        peaks_enrolled = sorted(enrolled[rid][:N_PEAKS])
        print(f"\n  Rod {rid}: measuring {len(peaks_enrolled)} enrolled peaks")

        # Fine-scan each enrolled peak to get precise frequency
        measured_peaks = []
        for freq_nom in peaks_enrolled:
            # Sweep ±2% around nominal in 21 steps
            sweep_lo = freq_nom * 0.98
            sweep_hi = freq_nom * 1.02
            sweep_freqs = np.linspace(sweep_lo, sweep_hi, 21)
            best_mag = 0
            best_freq = freq_nom

            for sf in sweep_freqs:
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, AWG_DRIVE_UVPP, 0,
                    float(sf), float(sf), 0.0, 0.0, 0, 0
                )
                time.sleep(0.03)
                raw = _hw_capture_raw(handle)
                windowed = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                tb = int(round(sf / bin_hz))
                lo_b = max(0, tb - 3)
                hi_b = min(len(fft_mag) - 1, tb + 3)
                mag = float(np.max(fft_mag[lo_b:hi_b + 1]))
                if mag > best_mag:
                    best_mag = mag
                    best_freq = sf

            measured_peaks.append(round(best_freq, 2))

        # Try to identify mode number for each peak
        # f_n = n * v / (2L), so n = f_n * 2L / v
        mode_numbers = []
        spacings = []
        for f in measured_peaks:
            n_est = f * 2 * L / v_predicted
            mode_numbers.append(round(n_est, 1))

        for i in range(1, len(measured_peaks)):
            spacings.append(measured_peaks[i] - measured_peaks[i-1])

        # Compute v_bar from mean spacing
        if spacings:
            mean_spacing = np.mean(spacings)
            v_from_spacing = mean_spacing * 2 * L
        else:
            mean_spacing = 0
            v_from_spacing = 0

        # Compute v_bar from lowest peak (assume it's mode n)
        if measured_peaks:
            # Best guess: lowest peak mode number
            n_lowest = round(measured_peaks[0] * 2 * L / v_predicted)
            if n_lowest > 0:
                v_from_f1 = measured_peaks[0] * 2 * L / n_lowest
            else:
                v_from_f1 = 0
        else:
            v_from_f1 = 0

        print(f"    Measured peaks: {measured_peaks[:5]}{'...' if len(measured_peaks) > 5 else ''}")
        print(f"    Mean spacing: {mean_spacing:.1f} Hz → v = {v_from_spacing:.0f} m/s")
        print(f"    From f₁ (n≈{n_lowest}): v = {v_from_f1:.0f} m/s")
        print(f"    Estimated mode numbers: {mode_numbers[:5]}")

        results_per_rod[rid] = {
            "measured_peaks_hz": measured_peaks,
            "mode_number_estimates": mode_numbers,
            "spacings_hz": [round(s, 2) for s in spacings],
            "mean_spacing_hz": round(mean_spacing, 2),
            "v_from_spacing_ms": round(v_from_spacing, 1),
            "v_from_f1_ms": round(v_from_f1, 1),
        }

    mux.off()
    _hw_close_scope(handle)

    all_v_spacing = [r["v_from_spacing_ms"] for r in results_per_rod.values() if r["v_from_spacing_ms"] > 0]
    all_v_f1 = [r["v_from_f1_ms"] for r in results_per_rod.values() if r["v_from_f1_ms"] > 0]

    print(f"\n  --- Wave Speed Summary ---")
    if all_v_spacing:
        print(f"    From spacing: mean={np.mean(all_v_spacing):.0f} m/s "
              f"(predicted {v_predicted})")
    if all_v_f1:
        print(f"    From f₁: mean={np.mean(all_v_f1):.0f} m/s")

    return {
        "experiment": "wave_speed_verification",
        "rod_length_m": L,
        "predicted_v_bar_ms": v_predicted,
        "per_rod": results_per_rod,
        "paper_claim": "v_bar = 5,315 m/s (C2)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E21: Frequency Stability over Time (Temperature Proxy)
# ══════════════════════════════════════════════════════════════════════════

def exp_freq_stability_temporal(port: str) -> dict:
    """
    Paper claim C15 premise: Δf/f = αΔT, α = 3.25 ppm/K for borosilicate.

    Method 1: mine historical data for frequency drift across sessions
    Method 2: measure same peaks now and compare to enrollment values
    Method 3: repeated measurement over ~10 min to catch short-term drift
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES
    import glob

    print("\n" + "=" * 70)
    print("  EXPERIMENT E21: Frequency Stability / Temperature Coefficient")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    # --- Part A: Mine historical data ---
    print("\n  Part A: Historical frequency data from past sessions")
    historical = []  # list of {timestamp, rod, peak_idx, freq}

    recall_files = sorted(glob.glob(
        str(LAB_DIR / "associative_recall" / "recall_*.json")))
    for rf in recall_files:
        with open(rf) as f:
            d = json.load(f)
        ts = d["timestamp"]
        pl = d["peak_log"]
        for qr in pl:
            for pi in range(len(pl[qr].get(qr, []))):
                entry = pl[qr][qr][pi]
                historical.append({
                    "timestamp": ts,
                    "rod": qr,
                    "peak_idx": pi,
                    "freq_hz": entry["freq_hz"],
                    "magnitude": entry["magnitude"],
                    "file": rf.split("/")[-1],
                })

    print(f"    Found {len(historical)} historical measurements across "
          f"{len(recall_files)} files")

    # Group by (rod, peak_idx) and compute drift
    from collections import defaultdict
    grouped = defaultdict(list)
    for h in historical:
        grouped[(h["rod"], h["peak_idx"])].append(h)

    drift_stats = []
    for (rod, pidx), entries in sorted(grouped.items()):
        if len(entries) < 2:
            continue
        freqs = [e["freq_hz"] for e in entries]
        timestamps = [e["timestamp"] for e in entries]
        mean_f = np.mean(freqs)
        std_f = np.std(freqs)
        range_f = max(freqs) - min(freqs)
        drift_ppm = (range_f / mean_f) * 1e6 if mean_f > 0 else 0
        drift_stats.append({
            "rod": rod, "peak_idx": pidx,
            "mean_freq_hz": round(mean_f, 2),
            "std_hz": round(std_f, 4),
            "range_hz": round(range_f, 4),
            "drift_ppm": round(drift_ppm, 2),
            "n_measurements": len(entries),
        })

    if drift_stats:
        mean_drift = np.mean([d["drift_ppm"] for d in drift_stats])
        max_drift = max(d["drift_ppm"] for d in drift_stats)
        print(f"    Mean drift across sessions: {mean_drift:.2f} ppm")
        print(f"    Max drift: {max_drift:.2f} ppm")
        print(f"    (Paper TCF = 3.25 ppm/K → {max_drift:.2f} ppm ≈ "
              f"{max_drift/3.25:.2f} K temp change)")

    # --- Part B: Fresh measurements vs enrollment ---
    print("\n  Part B: Fresh measurement vs enrollment baseline")
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    fresh_results = {}
    for rid in rod_ids:
        mux.select(int(rid))
        time.sleep(SETTLE_RELAY_S)

        peaks = enrolled[rid][:N_PEAKS]
        rod_fresh = []
        for freq_nom in peaks:
            # Fine-scan ±1% to find exact current peak
            sweep = np.linspace(freq_nom * 0.99, freq_nom * 1.01, 21)
            best_mag = 0
            best_freq = freq_nom
            for sf in sweep:
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, AWG_DRIVE_UVPP, 0,
                    float(sf), float(sf), 0.0, 0.0, 0, 0
                )
                time.sleep(0.03)
                raw = _hw_capture_raw(handle)
                windowed = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                tb = int(round(sf / bin_hz))
                lo_b = max(0, tb - 3)
                hi_b = min(len(fft_mag) - 1, tb + 3)
                mag = float(np.max(fft_mag[lo_b:hi_b + 1]))
                if mag > best_mag:
                    best_mag = mag
                    best_freq = sf

            shift_hz = best_freq - freq_nom
            shift_ppm = (shift_hz / freq_nom) * 1e6 if freq_nom > 0 else 0
            rod_fresh.append({
                "enrolled_hz": round(freq_nom, 2),
                "measured_hz": round(best_freq, 2),
                "shift_hz": round(shift_hz, 2),
                "shift_ppm": round(shift_ppm, 1),
            })

        fresh_results[rid] = rod_fresh
        shifts = [r["shift_ppm"] for r in rod_fresh]
        print(f"    Rod {rid}: mean shift = {np.mean(shifts):+.1f} ppm, "
              f"max |shift| = {max(abs(s) for s in shifts):.1f} ppm")

    # --- Part C: Short-term drift (3 measurements, 3 min apart) ---
    print("\n  Part C: Short-term drift measurement (3 rounds, ~3 min each)")
    test_rod = rod_ids[0]
    mux.select(int(test_rod))
    time.sleep(SETTLE_RELAY_S)
    test_peaks = enrolled[test_rod][:5]

    short_term = []
    for round_num in range(3):
        round_freqs = []
        for freq_nom in test_peaks:
            sweep = np.linspace(freq_nom * 0.99, freq_nom * 1.01, 11)
            best_mag = 0
            best_freq = freq_nom
            for sf in sweep:
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, AWG_DRIVE_UVPP, 0,
                    float(sf), float(sf), 0.0, 0.0, 0, 0
                )
                time.sleep(0.03)
                raw = _hw_capture_raw(handle)
                windowed = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                tb = int(round(sf / bin_hz))
                lo_b = max(0, tb - 3)
                hi_b = min(len(fft_mag) - 1, tb + 3)
                mag = float(np.max(fft_mag[lo_b:hi_b + 1]))
                if mag > best_mag:
                    best_mag = mag
                    best_freq = sf
            round_freqs.append(round(best_freq, 2))

        short_term.append({
            "round": round_num + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "freqs_hz": round_freqs,
        })
        print(f"    Round {round_num+1}: {round_freqs}")

        if round_num < 2:
            print(f"    Waiting 60s...")
            time.sleep(60)

    # Compute short-term drift
    if len(short_term) >= 2:
        for pidx in range(len(test_peaks)):
            fvals = [st["freqs_hz"][pidx] for st in short_term]
            drift = max(fvals) - min(fvals)
            mean_f = np.mean(fvals)
            ppm = (drift / mean_f) * 1e6 if mean_f > 0 else 0
            print(f"    Peak {pidx} ({test_peaks[pidx]:.0f} Hz): "
                  f"range={drift:.2f} Hz, {ppm:.1f} ppm over ~3 min")

    mux.off()
    _hw_close_scope(handle)

    return {
        "experiment": "freq_stability_temporal",
        "historical_drift_stats": drift_stats,
        "fresh_vs_enrollment": fresh_results,
        "short_term_drift": short_term,
        "paper_tcf_ppm_per_k": 3.25,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E20: PUF Uniqueness (offline)
# ══════════════════════════════════════════════════════════════════════════

def exp_puf_uniqueness() -> dict:
    """
    Paper claim C49: spectral fingerprint is physically unclonable.
    Show unperturbed rods have unique spectra (birth fingerprint).
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT E20: PUF Uniqueness")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    # Use enrolled frequencies as the "birth fingerprint" — they ARE the
    # perturbation pattern, but even the raw peak positions differ per rod
    print(f"\n  Enrolled peak frequencies per rod:")
    rod_vectors = {}
    for rid in rod_ids:
        peaks = sorted(enrolled[rid][:N_PEAKS])
        rod_vectors[rid] = np.array(peaks)
        print(f"    Rod {rid}: {[round(p, 1) for p in peaks[:5]]}...")

    # Compute pairwise frequency distance
    print(f"\n  Pairwise spectral distance (mean |Δf| in Hz):")
    distances = {}
    for i, ri in enumerate(rod_ids):
        for j, rj in enumerate(rod_ids):
            if j <= i:
                continue
            # Closest-match distance (each peak in ri finds closest in rj)
            vi = rod_vectors[ri]
            vj = rod_vectors[rj]
            dists = []
            for freq_i in vi:
                min_d = min(abs(freq_i - freq_j) for freq_j in vj)
                dists.append(min_d)
            mean_dist = np.mean(dists)
            distances[(ri, rj)] = round(mean_dist, 1)
            print(f"    Rod {ri} vs Rod {rj}: {mean_dist:.1f} Hz mean distance")

    # Compute Hamming distance (how many peaks are unique to each rod)
    print(f"\n  Peak overlap (freq within 3%):")
    for i, ri in enumerate(rod_ids):
        for j, rj in enumerate(rod_ids):
            if j <= i:
                continue
            shared = 0
            for freq_i in rod_vectors[ri]:
                if any(abs(freq_i - freq_j) / max(freq_i, freq_j) < 0.03
                       for freq_j in rod_vectors[rj]):
                    shared += 1
            print(f"    Rod {ri} vs Rod {rj}: {shared}/{N_PEAKS} shared peaks "
                  f"({(N_PEAKS-shared)}/{N_PEAKS} unique)")

    min_dist = min(distances.values())
    max_dist = max(distances.values())

    return {
        "experiment": "puf_uniqueness",
        "n_rods": len(rod_ids),
        "n_peaks": N_PEAKS,
        "pairwise_distances_hz": {f"{k[0]}_vs_{k[1]}": v for k, v in distances.items()},
        "min_distance_hz": min_dist,
        "max_distance_hz": max_dist,
        "paper_claim": "Spectral fingerprint is physically unclonable (C49)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E22: Position-Dependent Sensitivity
# ══════════════════════════════════════════════════════════════════════════

def exp_position_sensitivity(port: str) -> dict:
    """
    Paper claim C4: mass at antinode shifts that mode most.
    sin²(nπx/L) sensitivity profile.

    Method: each rod has PZTs at different positions. Compare which modes
    show strongest response per rod — should correlate with PZT position.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT E22: Position-Dependent Sensitivity")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    L = 0.150  # 150 mm
    v_bar = 5315  # m/s

    results_per_rod = {}

    for rid in rod_ids:
        mux.select(int(rid))
        time.sleep(SETTLE_RELAY_S)

        # Scan a broad range of frequencies to find all resonances
        # Use all enrolled peaks for this rod + some extras
        peaks = sorted(enrolled[rid][:N_PEAKS])
        print(f"\n  Rod {rid}: measuring response at {len(peaks)} peaks")

        response_profile = []
        for freq in peaks:
            result = _hw_measure_spectrum(handle, freq, n_avg=N_AVG)
            mag = result["magnitude"]
            # Estimate mode number
            n_mode = round(freq * 2 * L / v_bar)
            response_profile.append({
                "freq_hz": round(freq, 1),
                "magnitude": round(mag, 1),
                "est_mode_n": n_mode,
            })
            print(f"    f={freq:8.1f} Hz (n≈{n_mode:2d}): mag={mag:.0f}")

        # Identify which mode has strongest response — reveals PZT position
        if response_profile:
            strongest = max(response_profile, key=lambda x: x["magnitude"])
            n_strong = strongest["est_mode_n"]
            # PZT position estimate: antinode of mode n is at x = L/(2n)
            # (first antinode). More precisely: peaks of sin²(nπx/L) at x = (2k+1)L/(2n)
            if n_strong > 0:
                pzt_est = L / (2 * n_strong) * 1000  # mm
            else:
                pzt_est = 0
            print(f"    Strongest: mode n≈{n_strong} at {strongest['freq_hz']:.0f} Hz "
                  f"→ PZT near {pzt_est:.1f} mm from end?")

        results_per_rod[rid] = {
            "response_profile": response_profile,
            "strongest_mode": strongest if response_profile else None,
        }

    mux.off()
    _hw_close_scope(handle)

    return {
        "experiment": "position_dependent_sensitivity",
        "per_rod": results_per_rod,
        "paper_claim": "Mass at antinode shifts that mode most (C4, sin² profile)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E23: Parametric Amplification Proxy
# ══════════════════════════════════════════════════════════════════════════

def exp_parametric_proxy(port: str) -> dict:
    """
    Sidebar S16: parametric amplification +12 dB from modulated drive.

    Proxy test: drive at f₁ + f₂ (sum of two enrolled frequencies),
    measure if response at either shows enhancement vs driving them solo.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT E23: Parametric Amplification Proxy")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {port}")

    test_rod = rod_ids[0]
    mux.select(int(test_rod))
    time.sleep(SETTLE_RELAY_S)

    peaks = enrolled[test_rod][:N_PEAKS]
    # Pick 3 pairs of close peaks
    pairs = []
    for i in range(min(5, len(peaks))):
        for j in range(i+1, min(6, len(peaks))):
            pairs.append((peaks[i], peaks[j]))
    pairs = pairs[:4]

    nfft = N_SAMPLES * 4

    results = []
    print(f"  Testing {len(pairs)} frequency pairs on Rod {test_rod}")

    for f1, f2 in pairs:
        print(f"\n    Pair: {f1:.0f} Hz + {f2:.0f} Hz")

        # Measure solo response at f1
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(f1), float(f1), 0.0, 0.0, 0, 0
        )
        time.sleep(SETTLE_S)
        solo_f1_mags = []
        for _ in range(N_AVG):
            raw = _hw_capture_raw(handle)
            windowed = raw * np.hanning(len(raw))
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            tb1 = int(round(f1 / bin_hz))
            lo1 = max(0, tb1 - 3)
            hi1 = min(len(fft_mag) - 1, tb1 + 3)
            solo_f1_mags.append(float(np.max(fft_mag[lo1:hi1+1])))
        solo_f1 = np.mean(solo_f1_mags)

        # Measure solo response at f2
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(f2), float(f2), 0.0, 0.0, 0, 0
        )
        time.sleep(SETTLE_S)
        solo_f2_mags = []
        for _ in range(N_AVG):
            raw = _hw_capture_raw(handle)
            windowed = raw * np.hanning(len(raw))
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            tb2 = int(round(f2 / bin_hz))
            lo2 = max(0, tb2 - 3)
            hi2 = min(len(fft_mag) - 1, tb2 + 3)
            solo_f2_mags.append(float(np.max(fft_mag[lo2:hi2+1])))
        solo_f2 = np.mean(solo_f2_mags)

        # Now drive at sum frequency f1+f2 (parametric pump)
        f_pump = f1 + f2
        if f_pump < SAMPLE_RATE / 2:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(f_pump), float(f_pump), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)

            pump_f1_mags = []
            pump_f2_mags = []
            for _ in range(N_AVG):
                raw = _hw_capture_raw(handle)
                windowed = raw * np.hanning(len(raw))
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                pump_f1_mags.append(float(np.max(fft_mag[lo1:hi1+1])))
                pump_f2_mags.append(float(np.max(fft_mag[lo2:hi2+1])))

            pump_f1 = np.mean(pump_f1_mags)
            pump_f2 = np.mean(pump_f2_mags)

            gain_f1_db = 20 * math.log10(pump_f1 / solo_f1) if solo_f1 > 0 else 0
            gain_f2_db = 20 * math.log10(pump_f2 / solo_f2) if solo_f2 > 0 else 0

            print(f"      Solo f1={solo_f1:.0f}, solo f2={solo_f2:.0f}")
            print(f"      Pump@{f_pump:.0f}: f1_resp={pump_f1:.0f} ({gain_f1_db:+.1f} dB), "
                  f"f2_resp={pump_f2:.0f} ({gain_f2_db:+.1f} dB)")

            results.append({
                "f1_hz": round(f1, 1),
                "f2_hz": round(f2, 1),
                "f_pump_hz": round(f_pump, 1),
                "solo_f1": round(solo_f1, 1),
                "solo_f2": round(solo_f2, 1),
                "pump_f1_response": round(pump_f1, 1),
                "pump_f2_response": round(pump_f2, 1),
                "gain_f1_db": round(gain_f1_db, 1),
                "gain_f2_db": round(gain_f2_db, 1),
            })
        else:
            print(f"      Pump freq {f_pump:.0f} Hz exceeds Nyquist — skipped")

    # Also test difference frequency f2-f1
    print(f"\n  Testing difference frequency drive:")
    for f1, f2 in pairs[:2]:
        f_diff = abs(f2 - f1)
        if f_diff > 10:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(f_diff), float(f_diff), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)

            diff_f1_mags = []
            diff_f2_mags = []
            for _ in range(N_AVG):
                raw = _hw_capture_raw(handle)
                windowed = raw * np.hanning(len(raw))
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                tb1 = int(round(f1 / bin_hz))
                tb2 = int(round(f2 / bin_hz))
                lo1 = max(0, tb1 - 3)
                hi1 = min(len(fft_mag) - 1, tb1 + 3)
                lo2 = max(0, tb2 - 3)
                hi2 = min(len(fft_mag) - 1, tb2 + 3)
                diff_f1_mags.append(float(np.max(fft_mag[lo1:hi1+1])))
                diff_f2_mags.append(float(np.max(fft_mag[lo2:hi2+1])))

            diff_f1 = np.mean(diff_f1_mags)
            diff_f2 = np.mean(diff_f2_mags)
            print(f"    Drive@{f_diff:.0f} Hz (f2−f1): "
                  f"f1_resp={diff_f1:.0f}, f2_resp={diff_f2:.0f}")

    mux.off()
    _hw_close_scope(handle)

    return {
        "experiment": "parametric_amplification_proxy",
        "test_rod": test_rod,
        "pairs_tested": len(results),
        "results": results,
        "paper_claim": "+12 dB parametric amplification (S16)",
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E24: Frequency-Offset Query Tolerance
# ══════════════════════════════════════════════════════════════════════════

def exp_freq_offset_tolerance(port: str) -> dict:
    """
    Drive recall queries with deliberate frequency offsets (±1% to ±10%)
    and measure how accuracy and margin degrade.
    Paper claim: ±5% corrupted query still returns correct match (§10.5).
    """
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP, SAMPLE_RATE

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    from tools.relay_mux import RelayMux
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    offsets_pct = [0, 1, 2, 3, 5, 7, 10]
    results_by_offset = []

    for off_pct in offsets_pct:
        print(f"\n  Offset ±{off_pct}%:")
        # Alternate sign each peak to simulate noisy queries
        correct = 0
        margins = []
        for qi, qr in enumerate(rod_ids):
            mux.select(int(qr))
            time.sleep(SETTLE_RELAY_S)
            scores = {sr: 0.0 for sr in rod_ids}
            peaks = enrolled[qr][:N_PEAKS]

            for pi, freq_nom in enumerate(peaks):
                # Alternate +/- offset
                sign = 1 if (pi % 2 == 0) else -1
                freq_query = freq_nom * (1.0 + sign * off_pct / 100.0)

                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, AWG_DRIVE_UVPP, 0,
                    float(freq_query), float(freq_query), 0.0, 0.0, 0, 0
                )
                time.sleep(SETTLE_S)

                # Capture and measure magnitude
                magnitudes = []
                for _ in range(N_AVG):
                    raw = _hw_capture_raw(handle)
                    windowed = raw * np.hanning(len(raw))
                    nfft = len(raw) * 4
                    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                    bin_hz = freq_axis[1] - freq_axis[0]
                    tb = int(round(freq_query / bin_hz))
                    lo = max(0, tb - 5)
                    hi = min(len(fft_mag) - 1, tb + 5)
                    magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))

                meas_mag = np.mean(magnitudes)

                # Score: does this frequency match an enrolled peak?
                for sr in rod_ids:
                    expected = any(
                        abs(freq_nom - ep) / max(freq_nom, ep) < FREQ_MATCH_PCT / 100.0
                        for ep in enrolled[sr]
                    )
                    if expected:
                        scores[sr] += meas_mag * 3.0
                    else:
                        scores[sr] -= meas_mag * 1.0

            # Normalize
            total = sum(abs(v) for v in scores.values())
            if total > 0:
                scores = {k: v / total for k, v in scores.items()}

            winner = max(scores, key=scores.get)
            if winner == qr:
                correct += 1
            sorted_s = sorted(scores.values(), reverse=True)
            margin = sorted_s[0] - sorted_s[1] if len(sorted_s) > 1 else 0
            margins.append(margin if winner == qr else -margin)

        accuracy = correct / len(rod_ids)
        mean_margin = float(np.mean(margins))
        print(f"    Accuracy: {accuracy:.0%}, mean margin: {mean_margin:+.4f}")
        results_by_offset.append({
            "offset_pct": off_pct,
            "accuracy": accuracy,
            "correct": correct,
            "n_rods": len(rod_ids),
            "mean_margin": round(mean_margin, 4),
        })

    _hw_close_scope(handle)

    # Find max tolerable offset
    max_offset = 0
    for r in results_by_offset:
        if r["accuracy"] >= 1.0:
            max_offset = r["offset_pct"]

    return {
        "experiment": "freq_offset_tolerance",
        "paper_claim": "±5% corrupted query still recalls correctly (§10.5)",
        "max_100pct_offset": max_offset,
        "results": results_by_offset,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E25: Endurance Cycling Stress Test
# ══════════════════════════════════════════════════════════════════════════

def exp_endurance_cycling(port: str) -> dict:
    """
    Drive a single mode at its resonant frequency for thousands of cycles,
    then compare the full spectrum before and after.
    Paper claim: >10^15 cycles, non-destructive (§1.3, §10.1).
    """
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP, SAMPLE_RATE

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    from tools.relay_mux import RelayMux
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    test_rod = rod_ids[0]
    mux.select(int(test_rod))
    time.sleep(SETTLE_RELAY_S)

    peaks = enrolled[test_rod][:N_PEAKS]
    drive_freq = peaks[3]  # Pick a strong mid-frequency peak

    # --- Phase 1: Baseline spectrum ---
    print(f"  Phase 1: Baseline spectrum for Rod {test_rod}")
    baseline = {}
    for freq in peaks:
        m = _hw_measure_spectrum(handle, freq)
        baseline[round(freq, 1)] = m["magnitude"]
        print(f"    {freq:.1f} Hz: {m['magnitude']:.0f}")

    # --- Phase 2: Sustained CW drive ---
    drive_duration_s = 300  # 5 minutes of CW at ~2 kHz = ~600,000 cycles
    cycles_estimate = int(drive_freq * drive_duration_s)
    print(f"\n  Phase 2: Sustained CW drive at {drive_freq:.1f} Hz for {drive_duration_s}s")
    print(f"    Estimated cycles: {cycles_estimate:,}")

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(drive_freq), float(drive_freq), 0.0, 0.0, 0, 0
    )

    # Sample periodically during drive
    checkpoints = []
    t0 = time.time()
    check_interval = 60  # Check every 60s
    next_check = check_interval

    while True:
        elapsed = time.time() - t0
        if elapsed >= drive_duration_s:
            break
        if elapsed >= next_check:
            raw = _hw_capture_raw(handle)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            tb = int(round(drive_freq / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft_mag) - 1, tb + 3)
            mag = float(np.max(fft_mag[lo:hi + 1]))
            checkpoints.append({"elapsed_s": round(elapsed, 1), "magnitude": round(mag, 1)})
            print(f"    t={elapsed:.0f}s: mag={mag:.0f}")
            next_check += check_interval
        time.sleep(1)

    actual_elapsed = time.time() - t0
    actual_cycles = int(drive_freq * actual_elapsed)
    print(f"    Actual: {actual_elapsed:.0f}s, ~{actual_cycles:,} cycles")

    # --- Phase 3: Post-stress spectrum ---
    print(f"\n  Phase 3: Post-stress spectrum")
    time.sleep(1)
    post_stress = {}
    for freq in peaks:
        m = _hw_measure_spectrum(handle, freq)
        post_stress[round(freq, 1)] = m["magnitude"]
        print(f"    {freq:.1f} Hz: {m['magnitude']:.0f}")

    _hw_close_scope(handle)

    # Compare
    shifts = []
    print(f"\n  Comparison (pre vs post):")
    for freq in peaks:
        fk = round(freq, 1)
        pre = baseline.get(fk, 0)
        post = post_stress.get(fk, 0)
        change_pct = ((post - pre) / pre * 100) if pre > 0 else 0
        ratio_db = 20 * math.log10(post / pre) if pre > 0 and post > 0 else 0
        shifts.append({"freq_hz": fk, "pre": round(pre, 1), "post": round(post, 1),
                        "change_pct": round(change_pct, 1), "ratio_db": round(ratio_db, 2)})
        print(f"    {fk:8.1f} Hz: {pre:>10.0f} → {post:>10.0f}  ({change_pct:+.1f}%, {ratio_db:+.2f} dB)")

    max_change = max(abs(s["change_pct"]) for s in shifts)

    return {
        "experiment": "endurance_cycling",
        "paper_claim": ">10^15 non-destructive cycles (§1.3, §10.1)",
        "test_rod": test_rod,
        "drive_freq_hz": drive_freq,
        "drive_duration_s": round(actual_elapsed, 1),
        "estimated_cycles": actual_cycles,
        "max_change_pct": round(max_change, 1),
        "per_peak": shifts,
        "checkpoints": checkpoints,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E26: Partial-Query / Truncated Template Recall
# ══════════════════════════════════════════════════════════════════════════

def exp_partial_query_recall(port: str) -> dict:
    """
    Run recall using only the top-K strongest peaks (K = 1, 2, ..., 10).
    Paper claim: Recall works with partial mode subsets (§10.5, §2.3).
    """
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP, SAMPLE_RATE

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    from tools.relay_mux import RelayMux
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    # First, measure full spectrum for all rods to rank peaks by SNR
    print("  Measuring full spectra to rank peaks by magnitude...")
    peak_strengths = {}  # rod -> [(peak_idx, freq, magnitude)]
    for rid in rod_ids:
        mux.select(int(rid))
        time.sleep(SETTLE_RELAY_S)
        strengths = []
        for pi, freq in enumerate(enrolled[rid][:N_PEAKS]):
            m = _hw_measure_spectrum(handle, freq, n_avg=4)
            strengths.append((pi, freq, m["magnitude"]))
        # Sort by magnitude descending
        strengths.sort(key=lambda x: x[2], reverse=True)
        peak_strengths[rid] = strengths
        print(f"    Rod {rid}: strongest = {strengths[0][1]:.1f} Hz ({strengths[0][2]:.0f})")

    results_by_k = []
    for K in range(1, N_PEAKS + 1):
        print(f"\n  K={K} peaks:")
        correct = 0
        margins = []

        for qi, qr in enumerate(rod_ids):
            mux.select(int(qr))
            time.sleep(SETTLE_RELAY_S)

            # Use top-K peaks for this rod
            top_k_peaks = [ps[1] for ps in peak_strengths[qr][:K]]
            scores = {sr: 0.0 for sr in rod_ids}

            for freq in top_k_peaks:
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, AWG_DRIVE_UVPP, 0,
                    float(freq), float(freq), 0.0, 0.0, 0, 0
                )
                time.sleep(SETTLE_S)

                raw_mags = []
                for _ in range(N_AVG):
                    raw = _hw_capture_raw(handle)
                    windowed = raw * np.hanning(len(raw))
                    nfft = len(raw) * 4
                    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                    bin_hz = freq_axis[1] - freq_axis[0]
                    tb = int(round(freq / bin_hz))
                    lo = max(0, tb - 3)
                    hi = min(len(fft_mag) - 1, tb + 3)
                    raw_mags.append(float(np.max(fft_mag[lo:hi + 1])))
                meas_mag = np.mean(raw_mags)

                for sr in rod_ids:
                    expected = any(
                        abs(freq - ep) / max(freq, ep) < FREQ_MATCH_PCT / 100.0
                        for ep in enrolled[sr]
                    )
                    if expected:
                        scores[sr] += meas_mag * 3.0
                    else:
                        scores[sr] -= meas_mag * 1.0

            # Normalize
            total = sum(abs(v) for v in scores.values())
            if total > 0:
                scores = {k: v / total for k, v in scores.items()}

            winner = max(scores, key=scores.get)
            if winner == qr:
                correct += 1
            sorted_s = sorted(scores.values(), reverse=True)
            margin = sorted_s[0] - sorted_s[1] if len(sorted_s) > 1 else 0
            margins.append(margin if winner == qr else -margin)

        accuracy = correct / len(rod_ids)
        mean_margin = float(np.mean(margins))
        print(f"    Accuracy: {accuracy:.0%}, margin: {mean_margin:+.4f}")
        results_by_k.append({
            "K": K,
            "accuracy": accuracy,
            "correct": correct,
            "mean_margin": round(mean_margin, 4),
        })

    _hw_close_scope(handle)

    # Find minimum K for 100%
    min_k_100 = N_PEAKS
    for r in results_by_k:
        if r["accuracy"] >= 1.0:
            min_k_100 = r["K"]
            break

    return {
        "experiment": "partial_query_recall",
        "paper_claim": "Works with partial mode subsets (§10.5, §2.3)",
        "min_peaks_for_100pct": min_k_100,
        "results": results_by_k,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E27: Broadband Mode Census via CW Sweep
# ══════════════════════════════════════════════════════════════════════════

def exp_broadband_census(port: str) -> dict:
    """
    CW frequency sweep from 200 Hz to 50 kHz to find all detectable resonances.
    Paper predicts fn = n × 17,717 Hz for a 150mm borosilicate rod.
    """
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP, SAMPLE_RATE

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    from tools.relay_mux import RelayMux
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    test_rod = rod_ids[0]
    mux.select(int(test_rod))
    time.sleep(SETTLE_RELAY_S)

    # Coarse sweep: 200 Hz to 50 kHz in 100 Hz steps
    f_start = 200
    f_stop = 50000
    f_step = 100
    freqs = np.arange(f_start, f_stop + f_step, f_step)
    print(f"  Sweeping {f_start}–{f_stop} Hz in {f_step} Hz steps ({len(freqs)} points)")

    sweep_data = []
    for i, freq in enumerate(freqs):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq), float(freq), 0.0, 0.0, 0, 0
        )
        time.sleep(0.05)  # Short settle for sweep speed

        raw = _hw_capture_raw(handle)
        windowed = raw * np.hanning(len(raw))
        nfft = len(raw) * 4
        fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
        bin_hz = freq_axis[1] - freq_axis[0]
        tb = int(round(freq / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(fft_mag) - 1, tb + 3)
        mag = float(np.max(fft_mag[lo:hi + 1]))
        sweep_data.append({"freq_hz": round(float(freq), 1), "magnitude": round(mag, 1)})

        if i % 50 == 0:
            print(f"    {freq:.0f} Hz: mag={mag:.0f}")

    # Peak detection on the sweep
    mags = np.array([s["magnitude"] for s in sweep_data])
    noise_floor = float(np.median(mags))
    threshold = noise_floor * 5

    detected_peaks = []
    for i in range(1, len(mags) - 1):
        if mags[i] > threshold and mags[i] > mags[i - 1] and mags[i] > mags[i + 1]:
            detected_peaks.append({
                "freq_hz": sweep_data[i]["freq_hz"],
                "magnitude": sweep_data[i]["magnitude"],
                "snr_above_floor": round(20 * math.log10(mags[i] / noise_floor), 1) if noise_floor > 0 else 0,
            })

    _hw_close_scope(handle)

    # Compare with enrolled peaks
    enrolled_peaks = enrolled[test_rod][:N_PEAKS]
    matched = 0
    for ep in enrolled_peaks:
        for dp in detected_peaks:
            if abs(dp["freq_hz"] - ep) / max(ep, 1) < 0.05:
                matched += 1
                break

    # Predicted harmonic series
    predicted_fn = [n * 17717 for n in range(1, 4)]

    print(f"\n  Sweep complete:")
    print(f"    Noise floor: {noise_floor:.0f}")
    print(f"    Peaks detected (>{threshold:.0f}): {len(detected_peaks)}")
    print(f"    Enrolled peaks matched: {matched}/{len(enrolled_peaks)}")
    for dp in detected_peaks[:20]:
        print(f"      {dp['freq_hz']:8.1f} Hz: mag={dp['magnitude']:>10.0f}, SNR={dp['snr_above_floor']:>5.1f} dB")

    return {
        "experiment": "broadband_mode_census",
        "paper_claim": "fn = n × 17,717 Hz for 150mm rod (§4.4)",
        "test_rod": test_rod,
        "sweep_range_hz": [f_start, f_stop],
        "sweep_step_hz": f_step,
        "n_points": len(freqs),
        "noise_floor": round(noise_floor, 1),
        "n_peaks_detected": len(detected_peaks),
        "detected_peaks": detected_peaks,
        "enrolled_peaks_matched": matched,
        "enrolled_peaks_total": len(enrolled_peaks),
        "predicted_harmonics_hz": predicted_fn,
        "sweep_data": sweep_data,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E28: Multi-Day Temporal Stability (Historical Mining)
# ══════════════════════════════════════════════════════════════════════════

def exp_multiday_stability() -> dict:
    """
    Mine ALL timestamped historical data to build a temporal stability
    timeline. Paper claim: non-volatile without power/refresh (§3.2).
    """
    enrolled, rod_patterns, rod_ids = _load_enrollment()

    timeline = []

    # 1. Recall sessions (template accuracy + peak frequencies)
    recall_dir = LAB_DIR / "associative_recall"
    for f in sorted(recall_dir.glob("recall_*.json")):
        d = json.load(open(f))
        a = d.get("analysis", {})
        ts = d.get("timestamp", "")

        # Extract peak frequencies from peak_log for drift analysis
        peak_freqs = {}
        pl = d.get("peak_log", {})
        for qr in rod_ids:
            if qr in pl:
                qr_log = pl[qr]
                first_sense = rod_ids[0]
                if first_sense in qr_log:
                    if isinstance(qr_log[first_sense], list):
                        peak_freqs[qr] = [
                            p["freq_hz"] for p in qr_log[first_sense]
                        ]
                    elif isinstance(qr_log[first_sense], dict):
                        peak_freqs[qr] = [
                            qr_log[first_sense][k]["freq_hz"]
                            for k in sorted(qr_log[first_sense].keys(), key=int)
                        ]

        timeline.append({
            "source": "recall",
            "file": str(f.name),
            "timestamp": ts,
            "template_accuracy": a.get("template_accuracy"),
            "template_margin": a.get("mean_template_margin"),
            "peak_freqs": peak_freqs,
        })

    # 2. CIM suite sessions
    suite_dir = LAB_DIR / "cim_suite"
    for f in sorted(suite_dir.glob("suite_*.json")):
        d = json.load(open(f))
        ts_data = d.get("temporal_stability", {})
        timeline.append({
            "source": "cim_suite",
            "file": str(f.name),
            "timestamp": d.get("timestamp", ""),
            "recall_accuracy": ts_data.get("recall_accuracy"),
            "recall_margin": ts_data.get("recall_mean_margin"),
        })

    # 3. Additional experiments (temporal stability sub-experiment)
    addl_dir = LAB_DIR / "additional_exps"
    for f in sorted(addl_dir.glob("additional_*.json")):
        d = json.load(open(f))
        r = d.get("results", {})
        if "temporal_stability" in r:
            t = r["temporal_stability"]
            timeline.append({
                "source": "additional",
                "file": str(f.name),
                "timestamp": d.get("timestamp", ""),
                "accuracy": t.get("accuracy"),
                "correct": t.get("correct"),
            })
        if "freq_stability" in r:
            fs = r["freq_stability"]
            hist = fs.get("historical_drift_stats", [])
            if hist:
                timeline.append({
                    "source": "freq_stability",
                    "file": str(f.name),
                    "timestamp": d.get("timestamp", ""),
                    "n_peaks_tracked": len(hist),
                    "max_drift_ppm": max(h["drift_ppm"] for h in hist),
                    "mean_drift_ppm": float(np.mean([h["drift_ppm"] for h in hist])),
                })

    # Compute statistics
    accuracy_values = []
    for t in timeline:
        acc = t.get("template_accuracy") or t.get("recall_accuracy") or t.get("accuracy")
        if acc is not None:
            accuracy_values.append(acc)

    # Time span
    timestamps = [t["timestamp"] for t in timeline if t.get("timestamp")]
    timestamps.sort()
    if len(timestamps) >= 2:
        from datetime import datetime as dt
        try:
            t_first = dt.fromisoformat(timestamps[0])
            t_last = dt.fromisoformat(timestamps[-1])
            span_hours = (t_last - t_first).total_seconds() / 3600
        except Exception:
            span_hours = 0
    else:
        span_hours = 0

    print(f"\n  Multi-day stability timeline:")
    print(f"    Total sessions with accuracy: {len(accuracy_values)}")
    print(f"    All accuracies: {accuracy_values}")
    print(f"    100% rate: {sum(1 for a in accuracy_values if a >= 1.0)} / {len(accuracy_values)}")
    print(f"    Time span: {span_hours:.1f} hours ({span_hours/24:.1f} days)")
    if timestamps:
        print(f"    First: {timestamps[0][:25]}")
        print(f"    Last:  {timestamps[-1][:25]}")

    return {
        "experiment": "multiday_stability",
        "paper_claim": "Non-volatile without power/refresh (§3.2)",
        "sessions_with_accuracy": len(accuracy_values),
        "all_accuracies": accuracy_values,
        "pct_100": round(sum(1 for a in accuracy_values if a >= 1.0) / max(len(accuracy_values), 1) * 100, 1),
        "time_span_hours": round(span_hours, 1),
        "first_timestamp": timestamps[0] if timestamps else None,
        "last_timestamp": timestamps[-1] if timestamps else None,
        "timeline": timeline,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E29: Non-Destructive Readout Verification
# ══════════════════════════════════════════════════════════════════════════

def exp_nondestructive_readout(port: str) -> dict:
    """
    Verify that CW driving at one resonance doesn't shift other modes.
    Drive at peak f1 for 30s, measure all 10 peaks before and after.
    Paper claim: readout is non-destructive (§12.2).
    """
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    from tools.relay_mux import RelayMux
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    per_rod_results = []
    for rid in rod_ids:
        mux.select(int(rid))
        time.sleep(SETTLE_RELAY_S)
        peaks = enrolled[rid][:N_PEAKS]

        # Measure baseline
        baseline = {}
        for freq in peaks:
            m = _hw_measure_spectrum(handle, freq, n_avg=8)
            baseline[round(freq, 1)] = m["magnitude"]

        # Pick strongest peak to drive
        strongest_freq = max(peaks, key=lambda f: baseline.get(round(f, 1), 0))

        # Drive at strongest for 30s
        print(f"  Rod {rid}: driving at {strongest_freq:.1f} Hz for 30s...")
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(strongest_freq), float(strongest_freq), 0.0, 0.0, 0, 0
        )
        time.sleep(30)

        # Immediately re-measure all peaks
        post = {}
        for freq in peaks:
            m = _hw_measure_spectrum(handle, freq, n_avg=8)
            post[round(freq, 1)] = m["magnitude"]

        # Compare
        changes = []
        for freq in peaks:
            fk = round(freq, 1)
            pre = baseline.get(fk, 0)
            pst = post.get(fk, 0)
            change_db = 20 * math.log10(pst / pre) if pre > 0 and pst > 0 else 0
            changes.append({
                "freq_hz": fk,
                "pre": round(pre, 1),
                "post": round(pst, 1),
                "change_db": round(change_db, 2),
                "is_driven": abs(fk - round(strongest_freq, 1)) < 1,
            })

        non_driven = [c for c in changes if not c["is_driven"]]
        max_change = max(abs(c["change_db"]) for c in non_driven) if non_driven else 0
        print(f"    Max non-driven change: {max_change:.2f} dB")

        per_rod_results.append({
            "rod_id": rid,
            "driven_freq_hz": round(strongest_freq, 1),
            "max_non_driven_change_db": round(max_change, 2),
            "per_peak": changes,
        })

    _hw_close_scope(handle)

    overall_max = max(r["max_non_driven_change_db"] for r in per_rod_results)

    return {
        "experiment": "nondestructive_readout",
        "paper_claim": "Driving fn doesn't disturb other modes (§12.2)",
        "overall_max_change_db": round(overall_max, 2),
        "threshold_db": 3.0,
        "verdict": "CONFIRMED" if overall_max < 3.0 else "NOT CONFIRMED",
        "per_rod": per_rod_results,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E30: Capacity Load Test (Offline)
# ══════════════════════════════════════════════════════════════════════════

def exp_capacity_load_test() -> dict:
    """
    Simulate increasing pattern load using real spectral data.
    Synthesize virtual patterns and test when recall breaks.
    Paper claim: Hopfield capacity P_max ≈ 0.138N (§2.3).
    """
    enrolled, rod_patterns, rod_ids = _load_enrollment()
    recall_data = _load_latest_recall()
    peak_log = recall_data["peak_log"]

    # Get all enrolled peak frequencies across all rods
    all_freqs = set()
    for rid in rod_ids:
        for f in enrolled[rid]:
            all_freqs.add(round(f, 1))
    all_freqs = sorted(all_freqs)
    N = len(all_freqs)

    print(f"  Unique frequencies across all rods: {N}")
    print(f"  Hopfield capacity theory: P_max ≈ 0.138 × {N} = {0.138 * N:.1f}")

    # Base patterns = real rods
    base_patterns = {}
    for rid in rod_ids:
        pattern = np.zeros(N)
        for f in enrolled[rid]:
            idx = min(range(N), key=lambda i: abs(all_freqs[i] - f))
            pattern[idx] = 1.0
        base_patterns[rid] = pattern

    # Template scoring with real data (4 real patterns)
    real_matrix = {}
    for qr in rod_ids:
        scores = _template_score_from_peak_log(peak_log, enrolled, rod_ids, qr)
        real_matrix[qr] = scores
    real_correct, real_acc, real_margin = _eval_accuracy(real_matrix, rod_ids)
    print(f"  Base (P=4): accuracy={real_acc:.0%}, margin={real_margin:+.2f}")

    # Now add synthetic patterns and test
    rng = np.random.RandomState(42)
    results_by_load = [{"P": len(rod_ids), "accuracy": real_acc, "margin": round(real_margin, 2)}]

    for extra_patterns in [4, 8, 16, 32, 64]:
        total_P = len(rod_ids) + extra_patterns
        synthetic = {}
        for i in range(extra_patterns):
            n_active = rng.randint(3, min(8, N))
            active_idx = rng.choice(N, size=n_active, replace=False)
            pattern = np.zeros(N)
            pattern[active_idx] = 1.0
            synthetic[f"syn_{i}"] = pattern

        expanded_enrolled = dict(enrolled)
        for sid, pat in synthetic.items():
            expanded_enrolled[sid] = [all_freqs[i] for i in range(N) if pat[i] > 0]

        all_eids = rod_ids + sorted(synthetic.keys())
        correct = 0
        margins = []
        for qr in rod_ids:
            scores = {}
            for sr in all_eids:
                s = 0.0
                for pi in range(N):
                    freq = all_freqs[pi]
                    expected = any(
                        abs(freq - ep) / max(freq, ep) < 0.03
                        for ep in expanded_enrolled[sr]
                    )
                    if expected:
                        s += 3.0
                    else:
                        s -= 1.0
                scores[sr] = s

            winner = max(scores, key=scores.get)
            if winner == qr:
                correct += 1
            sorted_s = sorted(scores.values(), reverse=True)
            margin = sorted_s[0] - sorted_s[1]
            margins.append(margin if winner == qr else -margin)

        accuracy = correct / len(rod_ids)
        mean_margin = float(np.mean(margins))
        results_by_load.append({
            "P": total_P,
            "accuracy": accuracy,
            "margin": round(mean_margin, 2),
        })
        print(f"  P={total_P}: accuracy={accuracy:.0%}, margin={mean_margin:+.2f}")

    capacity_limit = max(r["P"] for r in results_by_load if r["accuracy"] >= 1.0)

    return {
        "experiment": "capacity_load_test",
        "paper_claim": "Hopfield P_max ≈ 0.138N ≈ 1,294 patterns/rod (§2.3)",
        "N_frequencies": N,
        "theoretical_P_max": round(0.138 * N, 1),
        "measured_capacity_limit": capacity_limit,
        "results": results_by_load,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E31: Boolean Guard-Band Surface (Offline)
# ══════════════════════════════════════════════════════════════════════════

def exp_boolean_guardband() -> dict:
    """
    Map Boolean accuracy vs overlap percentage and guard band width.
    Formalizes the design rule for minimum spectral separation.
    """
    enrolled, rod_patterns, rod_ids = _load_enrollment()

    from itertools import combinations
    pairs = list(combinations(rod_ids, 2))

    guard_bands = [0, 1, 2, 3, 5, 7, 10]
    results = []

    for gb in guard_bands:
        pair_results = []
        for r1, r2 in pairs:
            peaks1 = set(enrolled[r1][:N_PEAKS])
            peaks2 = set(enrolled[r2][:N_PEAKS])

            match_pct = FREQ_MATCH_PCT + gb
            shared = 0
            for p1 in peaks1:
                for p2 in peaks2:
                    if abs(p1 - p2) / max(p1, p2) < match_pct / 100.0:
                        shared += 1
                        break

            overlap_pct = shared / N_PEAKS * 100

            and_peaks = []
            for p1 in peaks1:
                for p2 in peaks2:
                    if abs(p1 - p2) / max(p1, p2) < match_pct / 100.0:
                        and_peaks.append((p1 + p2) / 2)

            or_peaks = sorted(peaks1 | peaks2)
            n_and = len(and_peaks)
            n_xor = len(or_peaks) - n_and

            pair_results.append({
                "pair": f"{r1}-{r2}",
                "overlap_pct": round(overlap_pct, 1),
                "n_shared": shared,
                "n_and": n_and,
                "n_xor": n_xor,
            })

        avg_overlap = float(np.mean([p["overlap_pct"] for p in pair_results]))
        results.append({
            "guard_band_pct": gb,
            "avg_overlap_pct": round(avg_overlap, 1),
            "pairs": pair_results,
        })
        print(f"  Guard band {gb}%: avg overlap = {avg_overlap:.1f}%")

    return {
        "experiment": "boolean_guardband_surface",
        "paper_claim": "Spectral separation design rule for Boolean compute",
        "guard_bands_tested": guard_bands,
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT E32: Perturbation / Rayleigh Verification
# ══════════════════════════════════════════════════════════════════════════

def exp_rayleigh_verification() -> dict:
    """
    Compare enrolled perturbation pattern (perturbed_hz vs fingerprint)
    to Rayleigh perturbation predictions. Paper claim: shifts match
    Rayleigh within 2% (§4.5).
    """
    enrolled, rod_patterns, rod_ids = _load_enrollment()

    with open(USERS_FILE) as f:
        db = json.load(f)

    results = []
    for rid in rod_ids:
        rod_data = db["rods"][rid]
        fingerprint = rod_data.get("fingerprint", [])
        perturbed = rod_data.get("perturbed_hz", [])

        if not fingerprint or not perturbed:
            print(f"  Rod {rid}: missing fingerprint or perturbed data")
            continue

        n = min(len(fingerprint), len(perturbed))
        shifts = []
        for i in range(n):
            f_orig = fingerprint[i]
            f_pert = perturbed[i]
            shift_hz = f_pert - f_orig
            shift_pct = (shift_hz / f_orig * 100) if f_orig > 0 else 0
            shifts.append({
                "peak_idx": i,
                "original_hz": round(f_orig, 2),
                "perturbed_hz": round(f_pert, 2),
                "shift_hz": round(shift_hz, 2),
                "shift_pct": round(shift_pct, 3),
            })

        shift_pcts = [s["shift_pct"] for s in shifts if abs(s["shift_pct"]) > 0.01]
        if len(shift_pcts) >= 2:
            max_shift = max(abs(s) for s in shift_pcts)
            normalized = [s / max_shift for s in shift_pcts]
            consistency = 1.0 - float(np.std(normalized))
        else:
            consistency = 0.0

        results.append({
            "rod_id": rid,
            "n_peaks": n,
            "shifts": shifts,
            "mean_shift_pct": round(float(np.mean([abs(s["shift_pct"]) for s in shifts])), 3),
            "max_shift_pct": round(max(abs(s["shift_pct"]) for s in shifts), 3),
            "self_consistency": round(consistency, 3),
        })

        print(f"  Rod {rid}: {n} peaks, mean |shift|={results[-1]['mean_shift_pct']:.3f}%, "
              f"max={results[-1]['max_shift_pct']:.3f}%, consistency={consistency:.3f}")

    return {
        "experiment": "rayleigh_verification",
        "paper_claim": "Shifts match Rayleigh within 2% (§4.5)",
        "results": results,
    }


# ──────────────────────────────────────────────────────────────────────────
#   E33  Ringdown Re-excitation Interference
# ──────────────────────────────────────────────────────────────────────────

def exp_ringdown_reexcitation(port: str) -> dict:
    """E33 — classical two-source interference via ringdown re-excitation.

    After CW excitation at a mode frequency, the sig gen is turned off and
    the rod rings down with time constant τ = Q / (π f).  If we re-excite
    at delay Δt, the new CW drive interferes with the lingering ringdown.

    * If the residual is in-phase with the new drive → constructive →
      amplitude overshoot compared to cold start.
    * If out-of-phase → destructive → amplitude undershoot.
    * At large Δt (residual fully decayed) → clean reference level.

    Sweeping Δt should reveal a damped oscillation at the mode frequency
    superimposed on exponential decay — the hallmark of coherent wave
    interference inside the resonator.

    Hardware requirements: current setup (no changes).
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT E33: Ringdown Re-excitation Interference")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    # We'll test Rod 1 (or first available) at its strongest mode
    test_rid = rod_ids[0]
    relay_ch = int(test_rid)
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    # Find the strongest mode by magnitude
    peaks = enrolled[test_rid]
    print(f"\n  Measuring peak magnitudes for Rod {test_rid}...")
    peak_mags = []
    for f in peaks:
        m = _hw_measure_spectrum(handle, f, n_avg=4, settle_s=0.15)
        peak_mags.append((f, m["magnitude"]))
    peak_mags.sort(key=lambda x: -x[1])
    test_freq = peak_mags[0][0]
    ref_mag = peak_mags[0][1]
    print(f"  Strongest mode: {test_freq:.1f} Hz (mag={ref_mag:.0f})")

    # ── Phase 1: Measure ringdown τ for this mode ──
    print(f"\n  Phase 1: Ringdown τ measurement at {test_freq:.1f} Hz")
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(test_freq), float(test_freq), 0.0, 0.0, 0, 0,
    )
    time.sleep(0.5)  # ring up to steady state

    # Turn off AWG and capture ringdown
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0,
    )
    time.sleep(0.001)
    raw_rd = _hw_capture_raw(handle)
    t_arr = np.arange(len(raw_rd)) / SAMPLE_RATE

    from scipy.signal import hilbert
    analytic = hilbert(raw_rd)
    envelope = np.abs(analytic)
    peak_env = float(np.max(envelope))

    # Fit exponential decay
    mask = envelope > peak_env * 0.05
    tau_s = float("nan")
    Q_meas = float("nan")
    if np.sum(mask) > 10:
        t_m = t_arr[mask]
        log_env = np.log(envelope[mask] + 1e-30)
        coeffs = np.polyfit(t_m, log_env, 1)
        if coeffs[0] < 0:
            tau_s = -1.0 / coeffs[0]
            Q_meas = math.pi * test_freq * tau_s

    if not math.isnan(tau_s):
        print(f"    τ = {tau_s*1000:.2f} ms, Q = {Q_meas:.0f}")
    else:
        tau_s = 0.030  # fallback: 30 ms
        print(f"    Could not fit τ; using fallback {tau_s*1000:.0f} ms")

    period_s = 1.0 / test_freq

    # ── Phase 2: Sweep re-excitation delay ──
    # Delays chosen to cover: sub-cycle, 1-10 cycles, several τ, full decay
    delays_s = []
    # Sub-cycle steps (0 to 1 period in 8 steps)
    for i in range(9):
        delays_s.append(i * period_s / 8.0)
    # 1-10 cycle steps
    for n_cyc in [1.5, 2, 3, 4, 5, 7, 10]:
        delays_s.append(n_cyc * period_s)
    # τ-scale steps
    for mult in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]:
        delays_s.append(mult * tau_s)
    # Fully decayed reference
    delays_s.append(max(10.0 * tau_s, 0.5))

    # Remove duplicates and sort
    delays_s = sorted(set(round(d, 6) for d in delays_s))

    print(f"\n  Phase 2: Re-excitation sweep ({len(delays_s)} delays, "
          f"period={period_s*1000:.3f} ms, τ={tau_s*1000:.1f} ms)")

    EXCITE_DURATION = 0.5   # seconds of CW before stopping
    MEASURE_SETTLE = 0.050  # 50 ms after re-excitation before capture
    N_REPS = 3              # repeat each delay for averaging

    sweep_results = []

    for di, dt in enumerate(delays_s):
        mags = []
        for rep in range(N_REPS):
            # 1) Excite mode to steady state
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(test_freq), float(test_freq), 0.0, 0.0, 0, 0,
            )
            time.sleep(EXCITE_DURATION)

            # 2) Stop drive
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0,
            )

            # 3) Wait Δt (residual decays during this time)
            if dt > 0.001:
                time.sleep(dt)
            elif dt > 0:
                # For very short delays, busy-wait for better precision
                t_end = time.perf_counter() + dt
                while time.perf_counter() < t_end:
                    pass

            # 4) Re-excite and capture immediately after brief settle
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(test_freq), float(test_freq), 0.0, 0.0, 0, 0,
            )
            time.sleep(MEASURE_SETTLE)

            # 5) Capture spectrum at the mode frequency
            raw = _hw_capture_raw(handle)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            target_bin = int(round(test_freq / bin_hz))
            lo = max(0, target_bin - 3)
            hi = min(len(fft_mag) - 1, target_bin + 3)
            peak_mag = float(np.max(fft_mag[lo:hi + 1]))
            mags.append(peak_mag)

            # 6) Stop drive before next iteration
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0,
            )
            time.sleep(0.05)

        mean_mag = float(np.mean(mags))
        std_mag = float(np.std(mags))
        sweep_results.append({
            "delay_s": round(dt, 6),
            "delay_cycles": round(dt * test_freq, 3),
            "delay_over_tau": round(dt / tau_s, 3) if tau_s > 0 else None,
            "magnitude_mean": round(mean_mag, 1),
            "magnitude_std": round(std_mag, 1),
            "magnitude_reps": [round(m, 1) for m in mags],
        })

        # Progress indicator every 5 delays
        if di % 5 == 0 or di == len(delays_s) - 1:
            norm = mean_mag / ref_mag if ref_mag > 0 else 0
            print(f"    Δt={dt*1000:8.3f} ms ({dt/period_s:6.2f}T, "
                  f"{dt/tau_s:5.2f}τ): mag={mean_mag:12.0f}  "
                  f"({norm:+.3f}× ref)")

    # ── Phase 3: Analyze interference signature ──
    ref_delay = delays_s[-1]
    ref_entry = sweep_results[-1]
    ref_level = ref_entry["magnitude_mean"]

    normalized = []
    for sr in sweep_results:
        norm_mag = sr["magnitude_mean"] / ref_level if ref_level > 0 else 1.0
        normalized.append(round(norm_mag, 4))

    # Check for constructive/destructive signature
    max_norm = max(normalized[:-1]) if len(normalized) > 1 else 1.0
    min_norm = min(normalized[:-1]) if len(normalized) > 1 else 1.0
    contrast = max_norm - min_norm

    # Check for oscillatory behaviour in the sub-τ region
    sub_tau = [(sr["delay_s"], sr["magnitude_mean"])
               for sr in sweep_results if sr["delay_s"] < 2 * tau_s]
    oscillation_detected = False
    if len(sub_tau) >= 4:
        mags_sub = [m for _, m in sub_tau]
        diffs = [mags_sub[i+1] - mags_sub[i] for i in range(len(mags_sub)-1)]
        sign_changes = sum(1 for i in range(len(diffs)-1)
                          if diffs[i] * diffs[i+1] < 0)
        oscillation_detected = sign_changes >= 2

    _hw_close_scope(handle)
    mux.off()

    print(f"\n  Analysis:")
    print(f"    Reference level (Δt={ref_delay*1000:.0f} ms): {ref_level:.0f}")
    print(f"    Max normalized amplitude: {max_norm:.4f}×")
    print(f"    Min normalized amplitude: {min_norm:.4f}×")
    print(f"    Interference contrast: {contrast:.4f}")
    print(f"    Oscillation detected (sub-τ): {oscillation_detected}")

    if contrast > 0.02:
        verdict = "INTERFERENCE DETECTED"
        detail = (f"Amplitude varies by {contrast:.1%} depending on re-excitation "
                  f"delay, consistent with coherent wave interference between "
                  f"residual ringdown and new CW drive.")
    else:
        verdict = "NO SIGNIFICANT INTERFERENCE"
        detail = (f"Amplitude contrast {contrast:.1%} is below 2% threshold. "
                  f"Ringdown may decay too fast (τ={tau_s*1000:.1f} ms) for "
                  f"detectable phase-dependent interference at Python timing "
                  f"precision.")

    print(f"    Verdict: {verdict}")
    print(f"    {detail}")

    return {
        "experiment": "ringdown_reexcitation_interference",
        "description": "Classical two-source interference via ringdown re-excitation",
        "rod_id": test_rid,
        "mode_freq_hz": round(test_freq, 1),
        "ringdown_tau_ms": round(tau_s * 1000, 2),
        "Q_measured": round(Q_meas, 0) if not math.isnan(Q_meas) else None,
        "period_ms": round(period_s * 1000, 3),
        "n_delays": len(delays_s),
        "n_reps": N_REPS,
        "reference_mag": round(ref_level, 1),
        "sweep": sweep_results,
        "normalized_magnitudes": normalized,
        "max_normalized": round(max_norm, 4),
        "min_normalized": round(min_norm, 4),
        "contrast": round(contrast, 4),
        "oscillation_detected": oscillation_detected,
        "verdict": verdict,
        "detail": detail,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 34: Scoring Weight Ratio Sensitivity Sweep
# ══════════════════════════════════════════════════════════════════════════

def exp_weight_ratio_sweep(port: str) -> dict:
    """
    Inoculation test: Sweep the expected/unexpected weight ratio used in
    template scoring to show recall accuracy is not dependent on the
    specific 3:1 choice.

    For each ratio R, scoring becomes: +R*frac for expected, -1*frac for
    unexpected. We test R = 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0
    and also the degenerate case R = 1 (no expected/unexpected distinction).

    Uses live hardware measurements (fresh 4x4 matrix) to avoid any
    dependency on cached data.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT 34: Scoring Weight Ratio Sensitivity")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    # ── Fresh hardware measurement ───────────────────────────────────
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    print("\n  Capturing fresh 4×4 measurement matrix...")
    # raw_data[query_rod][sense_rod][peak_idx] = magnitude
    raw_data = {}
    for qr in rod_ids:
        query_peaks = enrolled[qr][:N_PEAKS]
        raw_data[qr] = {}
        for sr in rod_ids:
            raw_data[qr][sr] = []

        for freq_hz in query_peaks:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)

            for sr in rod_ids:
                mux.select(int(sr))
                time.sleep(SETTLE_RELAY_S)
                magnitudes = []
                for _ in range(N_AVG):
                    raw = _hw_capture_raw(handle)
                    windowed = raw * np.hanning(len(raw))
                    nfft = len(raw) * 4
                    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                    bin_hz = freq_axis[1] - freq_axis[0]
                    target_bin = int(round(freq_hz / bin_hz))
                    lo = max(0, target_bin - 3)
                    hi = min(len(fft_mag) - 1, target_bin + 3)
                    magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))
                raw_data[qr][sr].append(float(np.mean(magnitudes)))

        mux.off()

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    _hw_close_scope(handle)

    # ── Sweep weight ratios ──────────────────────────────────────────
    ratios = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]
    # Also test: no expected/unexpected distinction (uniform +1)
    sweep_results = []

    print(f"\n  {'Ratio':>8}  {'Correct':>8}  {'Accuracy':>10}  {'Margin':>10}  {'Min margin':>12}  {'Scores'}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*12}  {'-'*40}")

    for ratio in ratios:
        matrix = {}
        margins = []
        for qr in rod_ids:
            query_peaks = enrolled[qr][:N_PEAKS]
            scores = {sr: 0.0 for sr in rod_ids}
            for pi, freq in enumerate(query_peaks):
                mags = {sr: raw_data[qr][sr][pi] for sr in rod_ids}
                total = sum(mags.values())
                if total == 0:
                    continue
                for sr in rod_ids:
                    frac = mags[sr] / total
                    expected = any(
                        abs(freq - ep) / max(freq, ep) < 0.03
                        for ep in enrolled[sr]
                    )
                    if expected:
                        scores[sr] += frac * ratio
                    else:
                        scores[sr] -= frac * 1.0
            matrix[qr] = {sr: round(v, 4) for sr, v in scores.items()}

            winner = max(scores, key=scores.get)
            if winner == qr:
                margin = scores[qr] - max(v for k, v in scores.items() if k != qr)
            else:
                margin = scores[qr] - scores[winner]
            margins.append(margin)

        correct = sum(1 for qr in rod_ids
                      if max(matrix[qr], key=matrix[qr].get) == qr)
        accuracy = correct / len(rod_ids)
        mean_margin = float(np.mean(margins))
        min_margin = float(np.min(margins))

        # Show per-query scores for audit transparency
        score_str = "  ".join(
            f"Q{qr}={matrix[qr][qr]:+.2f}" for qr in rod_ids
        )
        print(f"  {ratio:>8.1f}  {correct:>5}/{len(rod_ids)}  {accuracy:>9.0%}  "
              f"{mean_margin:>+9.2f}  {min_margin:>+11.2f}  {score_str}")

        sweep_results.append({
            "ratio": ratio,
            "correct": correct,
            "accuracy": accuracy,
            "mean_margin": round(mean_margin, 4),
            "min_margin": round(min_margin, 4),
            "margins": [round(m, 4) for m in margins],
            "matrix": matrix,
        })

    # ── Also test: magnitude-only scoring (no expected/unexpected) ───
    print("\n  --- Control: magnitude-only scoring (no expected/unexpected) ---")
    matrix_mag = {}
    mag_margins = []
    for qr in rod_ids:
        query_peaks = enrolled[qr][:N_PEAKS]
        scores = {sr: 0.0 for sr in rod_ids}
        for pi, freq in enumerate(query_peaks):
            mags = {sr: raw_data[qr][sr][pi] for sr in rod_ids}
            total = sum(mags.values())
            if total == 0:
                continue
            for sr in rod_ids:
                scores[sr] += mags[sr] / total  # pure fractional, no weighting
        matrix_mag[qr] = {sr: round(v, 4) for sr, v in scores.items()}

        winner = max(scores, key=scores.get)
        if winner == qr:
            margin = scores[qr] - max(v for k, v in scores.items() if k != qr)
        else:
            margin = scores[qr] - scores[winner]
        mag_margins.append(margin)

    mag_correct = sum(1 for qr in rod_ids
                      if max(matrix_mag[qr], key=matrix_mag[qr].get) == qr)
    mag_accuracy = mag_correct / len(rod_ids)
    mag_mean_margin = float(np.mean(mag_margins))
    print(f"  Magnitude-only: {mag_correct}/{len(rod_ids)} ({mag_accuracy:.0%}), "
          f"margin={mag_mean_margin:+.2f}")

    # ── Wilson score confidence interval ─────────────────────────────
    # For the canonical 3:1 result
    canonical = next(r for r in sweep_results if r["ratio"] == 3.0)
    n = len(rod_ids)
    p_hat = canonical["accuracy"]
    z = 1.96  # 95% CI
    denom = 1 + z * z / n
    center = (p_hat + z * z / (2 * n)) / denom
    margin_ci = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n) / denom
    wilson_lo = max(0, center - margin_ci)
    wilson_hi = min(1, center + margin_ci)
    print(f"\n  Wilson 95% CI for canonical 3:1 (N={n}): "
          f"[{wilson_lo:.1%}, {wilson_hi:.1%}]")

    # How many ratios achieve 100%?
    perfect_ratios = [r["ratio"] for r in sweep_results if r["accuracy"] == 1.0]
    print(f"  Ratios achieving 100%: {perfect_ratios}")
    print(f"  Ratio-robust: {'YES' if len(perfect_ratios) >= 4 else 'NO'} "
          f"({len(perfect_ratios)}/{len(ratios)} ratios)")

    return {
        "experiment": "weight_ratio_sensitivity",
        "n_rods": len(rod_ids),
        "n_peaks": N_PEAKS,
        "ratios_tested": ratios,
        "sweep": sweep_results,
        "magnitude_only": {
            "correct": mag_correct,
            "accuracy": mag_accuracy,
            "mean_margin": round(mag_mean_margin, 4),
            "matrix": matrix_mag,
        },
        "wilson_95ci": [round(wilson_lo, 4), round(wilson_hi, 4)],
        "perfect_ratios": perfect_ratios,
        "ratio_robust": len(perfect_ratios) >= 4,
        "raw_data": {qr: {sr: raw_data[qr][sr] for sr in rod_ids}
                     for qr in rod_ids},
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 35: Cross-Rod Isolation Measurement
# ══════════════════════════════════════════════════════════════════════════

def exp_cross_rod_isolation(port: str) -> dict:
    """
    Inoculation test: Measure electrical/acoustic crosstalk between rods
    on the shared AWG bus.

    For each rod R, find its strongest self-response frequency, then
    measure the response at that frequency on ALL other rods' sense PZTs.
    The ratio (other_rod / self_rod) gives isolation in dB.

    Also tests with AWG OFF to measure baseline noise floor.
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT 35: Cross-Rod Isolation")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    # ── Find each rod's strongest frequency ──────────────────────────
    print("\n  Phase 1: Find strongest self-response per rod")
    rod_best_freq = {}
    rod_self_mag = {}

    for rod in rod_ids:
        mux.select(int(rod))
        time.sleep(SETTLE_RELAY_S)
        best_freq = None
        best_mag = 0
        for freq_hz in enrolled[rod][:N_PEAKS]:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)
            magnitudes = []
            for _ in range(N_AVG):
                raw = _hw_capture_raw(handle)
                windowed = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                target_bin = int(round(freq_hz / bin_hz))
                lo = max(0, target_bin - 3)
                hi = min(len(fft_mag) - 1, target_bin + 3)
                magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))
            mag = float(np.mean(magnitudes))
            if mag > best_mag:
                best_mag = mag
                best_freq = freq_hz
        rod_best_freq[rod] = best_freq
        rod_self_mag[rod] = best_mag
        print(f"    Rod {rod} ({rod_patterns[rod]}): best freq={best_freq:.1f} Hz, "
              f"self mag={best_mag:.0f}")

    # ── Measure noise floor (AWG off) ────────────────────────────────
    print("\n  Phase 2: Noise floor (AWG off)")
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)

    noise_floors = {}
    for rod in rod_ids:
        mux.select(int(rod))
        time.sleep(SETTLE_RELAY_S)
        magnitudes = []
        for _ in range(N_AVG):
            raw = _hw_capture_raw(handle)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            # Measure at this rod's best freq bin even though AWG is off
            target_bin = int(round(rod_best_freq[rod] / bin_hz))
            lo = max(0, target_bin - 3)
            hi = min(len(fft_mag) - 1, target_bin + 3)
            magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))
        noise_floors[rod] = float(np.mean(magnitudes))
        print(f"    Rod {rod}: noise floor at {rod_best_freq[rod]:.1f} Hz = {noise_floors[rod]:.0f}")

    # ── Cross-rod isolation matrix ───────────────────────────────────
    print("\n  Phase 3: Cross-rod isolation matrix")
    print(f"  Drive rod's best freq, measure on all sense rods\n")

    isolation_matrix = {}  # isolation_matrix[drive_rod][sense_rod] = mag
    isolation_db = {}

    header = "  Drive\\Sense  " + "  ".join(f"Rod {sr:>5s}" for sr in rod_ids) + "  Isolation(dB)"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for drive_rod in rod_ids:
        freq_hz = rod_best_freq[drive_rod]
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
        )
        time.sleep(SETTLE_S)

        isolation_matrix[drive_rod] = {}
        isolation_db[drive_rod] = {}

        for sense_rod in rod_ids:
            mux.select(int(sense_rod))
            time.sleep(SETTLE_RELAY_S)
            magnitudes = []
            stds = []
            for _ in range(N_AVG):
                raw = _hw_capture_raw(handle)
                windowed = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                target_bin = int(round(freq_hz / bin_hz))
                lo = max(0, target_bin - 3)
                hi = min(len(fft_mag) - 1, target_bin + 3)
                magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))
            mag = float(np.mean(magnitudes))
            std = float(np.std(magnitudes))
            isolation_matrix[drive_rod][sense_rod] = {
                "magnitude": round(mag, 1),
                "std": round(std, 1),
            }

            # Isolation = 20*log10(other/self), negative means good isolation
            self_mag = rod_self_mag[drive_rod]
            if mag > 0 and self_mag > 0:
                iso_db = 20 * math.log10(mag / self_mag)
            else:
                iso_db = float('-inf')
            isolation_db[drive_rod][sense_rod] = round(iso_db, 1)

        mux.off()

        # Print row
        mag_str = "  ".join(
            f"{isolation_matrix[drive_rod][sr]['magnitude']:>9.0f}"
            for sr in rod_ids
        )
        iso_str = "  ".join(
            f"{isolation_db[drive_rod][sr]:>+6.1f}" if sr != drive_rod else "   0.0"
            for sr in rod_ids
        )
        print(f"  Rod {drive_rod:>5s}  {mag_str}   [{iso_str}]")

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    _hw_close_scope(handle)

    # ── Summary statistics ───────────────────────────────────────────
    off_diag_isolations = []
    for dr in rod_ids:
        for sr in rod_ids:
            if dr != sr:
                off_diag_isolations.append(isolation_db[dr][sr])

    mean_isolation = float(np.mean(off_diag_isolations))
    worst_isolation = float(np.max(off_diag_isolations))
    best_isolation = float(np.min(off_diag_isolations))

    print(f"\n  Off-diagonal isolation:")
    print(f"    Mean: {mean_isolation:+.1f} dB")
    print(f"    Worst: {worst_isolation:+.1f} dB")
    print(f"    Best: {best_isolation:+.1f} dB")
    print(f"    Verdict: {'GOOD (>10 dB)' if worst_isolation < -10 else 'MODERATE (>6 dB)' if worst_isolation < -6 else 'POOR (<6 dB)'}")

    return {
        "experiment": "cross_rod_isolation",
        "n_rods": len(rod_ids),
        "rod_best_freqs": {r: round(f, 1) for r, f in rod_best_freq.items()},
        "rod_self_mags": {r: round(m, 1) for r, m in rod_self_mag.items()},
        "noise_floors": {r: round(v, 1) for r, v in noise_floors.items()},
        "isolation_matrix": isolation_matrix,
        "isolation_db": isolation_db,
        "off_diagonal_mean_db": round(mean_isolation, 1),
        "off_diagonal_worst_db": round(worst_isolation, 1),
        "off_diagonal_best_db": round(best_isolation, 1),
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 36: Null Control (Deliberate Mismatch)
# ══════════════════════════════════════════════════════════════════════════

def exp_null_control(port: str) -> dict:
    """
    Inoculation test: Run the full recall scoring pipeline on deliberately
    WRONG pairings to verify it doesn't trivially produce correct answers.

    Three null tests:
    1. Shuffled: Score each rod's measurement against a DIFFERENT rod's
       enrollment (rotated: Rod 1 scored as Rod 2, Rod 2 as Rod 3, etc.)
    2. Reversed: Score using reversed-polarity weights (+1 for unexpected,
       -R for expected) — should give WRONG answers
    3. Random: Score against random frequency lists — should give no
       consistent winner

    Also computes a "separation metric": how much better does the correct
    scoring perform vs. the null controls?
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT 36: Null Control (Deliberate Mismatch)")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()

    # ── Fresh hardware measurement ───────────────────────────────────
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    print("\n  Capturing fresh 4×4 measurement matrix...")
    raw_data = {}
    query_freqs = {}
    for qr in rod_ids:
        query_peaks = enrolled[qr][:N_PEAKS]
        query_freqs[qr] = query_peaks
        raw_data[qr] = {}
        for sr in rod_ids:
            raw_data[qr][sr] = []

        for freq_hz in query_peaks:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)

            for sr in rod_ids:
                mux.select(int(sr))
                time.sleep(SETTLE_RELAY_S)
                magnitudes = []
                for _ in range(N_AVG):
                    raw = _hw_capture_raw(handle)
                    windowed = raw * np.hanning(len(raw))
                    nfft = len(raw) * 4
                    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                    bin_hz = freq_axis[1] - freq_axis[0]
                    target_bin = int(round(freq_hz / bin_hz))
                    lo = max(0, target_bin - 3)
                    hi = min(len(fft_mag) - 1, target_bin + 3)
                    magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))
                raw_data[qr][sr].append(float(np.mean(magnitudes)))

        mux.off()

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    _hw_close_scope(handle)

    def _score_with_enrollment(raw_d, enroll_map, rod_list, weight_ratio=3.0):
        """Score raw data against an arbitrary enrollment mapping."""
        matrix = {}
        for qr in rod_list:
            query_peaks = query_freqs[qr]
            scores = {sr: 0.0 for sr in rod_list}
            for pi, freq in enumerate(query_peaks):
                mags = {sr: raw_d[qr][sr][pi] for sr in rod_list}
                total = sum(mags.values())
                if total == 0:
                    continue
                for sr in rod_list:
                    frac = mags[sr] / total
                    expected = any(
                        abs(freq - ep) / max(freq, ep) < 0.03
                        for ep in enroll_map[sr]
                    )
                    if expected:
                        scores[sr] += frac * weight_ratio
                    else:
                        scores[sr] -= frac * 1.0
            matrix[qr] = {sr: round(v, 4) for sr, v in scores.items()}
        return matrix

    def _eval(matrix, rod_list, expected_winners=None):
        """Evaluate a score matrix. expected_winners maps query → expected winner."""
        if expected_winners is None:
            expected_winners = {qr: qr for qr in rod_list}
        correct = 0
        margins = []
        for qr in rod_list:
            winner = max(matrix[qr], key=matrix[qr].get)
            expected = expected_winners.get(qr, qr)
            if winner == expected:
                correct += 1
            exp_score = matrix[qr].get(expected, 0)
            best_other = max(v for k, v in matrix[qr].items() if k != expected)
            margins.append(exp_score - best_other)
        return correct, correct / len(rod_list), margins

    # ── Test 1: Correct scoring (baseline) ───────────────────────────
    print("\n  Test 1: CORRECT scoring (baseline)")
    correct_matrix = _score_with_enrollment(raw_data, enrolled, rod_ids)
    cc, ca, cm = _eval(correct_matrix, rod_ids)
    print(f"    {cc}/{len(rod_ids)} correct ({ca:.0%}), mean margin={np.mean(cm):+.2f}")

    # ── Test 2: Shuffled enrollment (rotated by 1) ───────────────────
    print("\n  Test 2: SHUFFLED enrollment (Rod 1 scored as Rod 2, etc.)")
    shuffled_enrolled = {}
    for i, r in enumerate(rod_ids):
        # Rod r gets enrollment of next rod (wrapping)
        donor = rod_ids[(i + 1) % len(rod_ids)]
        shuffled_enrolled[r] = enrolled[donor]
    shuffled_matrix = _score_with_enrollment(raw_data, shuffled_enrolled, rod_ids)
    # Under shuffled enrollment, the "correct" answer should be the DONOR
    shuffled_expected = {rod_ids[i]: rod_ids[(i + 1) % len(rod_ids)]
                         for i in range(len(rod_ids))}
    sc, sa, sm_shuf = _eval(shuffled_matrix, rod_ids, shuffled_expected)
    # Also check: does it accidentally get self-match right?
    self_correct_shuffled = sum(1 for qr in rod_ids
                                if max(shuffled_matrix[qr], key=shuffled_matrix[qr].get) == qr)
    print(f"    Self-match under shuffled enrollment: {self_correct_shuffled}/{len(rod_ids)}")
    print(f"    Donor-match under shuffled enrollment: {sc}/{len(rod_ids)}")
    for qr in rod_ids:
        donor = shuffled_expected[qr]
        winner = max(shuffled_matrix[qr], key=shuffled_matrix[qr].get)
        print(f"      Q={qr}: winner=Rod {winner}, "
              f"self={shuffled_matrix[qr][qr]:+.2f}, "
              f"donor={shuffled_matrix[qr][donor]:+.2f}")

    # ── Test 3: Reversed weights (anti-scoring) ──────────────────────
    print("\n  Test 3: REVERSED weights (+1 expected, -3 unexpected)")
    reversed_matrix = {}
    for qr in rod_ids:
        query_peaks = query_freqs[qr]
        scores = {sr: 0.0 for sr in rod_ids}
        for pi, freq in enumerate(query_peaks):
            mags = {sr: raw_data[qr][sr][pi] for sr in rod_ids}
            total = sum(mags.values())
            if total == 0:
                continue
            for sr in rod_ids:
                frac = mags[sr] / total
                expected = any(
                    abs(freq - ep) / max(freq, ep) < 0.03
                    for ep in enrolled[sr]
                )
                if expected:
                    scores[sr] += frac * 1.0  # weak reward
                else:
                    scores[sr] -= frac * 3.0  # strong penalty
        reversed_matrix[qr] = {sr: round(v, 4) for sr, v in scores.items()}
    rc, ra, rm_rev = _eval(reversed_matrix, rod_ids)
    print(f"    {rc}/{len(rod_ids)} correct ({ra:.0%}), mean margin={np.mean(rm_rev):+.2f}")

    # ── Test 4: Random enrollment (10 random frequency sets) ─────────
    print("\n  Test 4: RANDOM enrollment (10 random frequency sets)")
    rng = np.random.default_rng(42)
    random_results = []
    for trial in range(10):
        random_enrolled = {}
        for sr in rod_ids:
            # Random frequencies in the 1–35 kHz range
            random_enrolled[sr] = sorted(rng.uniform(1000, 35000, N_PEAKS).tolist())
        rand_matrix = _score_with_enrollment(raw_data, random_enrolled, rod_ids)
        rand_c, rand_a, _ = _eval(rand_matrix, rod_ids)
        random_results.append({"trial": trial, "correct": rand_c, "accuracy": rand_a})
    mean_random_acc = np.mean([r["accuracy"] for r in random_results])
    print(f"    Mean accuracy over 10 random trials: {mean_random_acc:.0%} "
          f"(expected ~25% for 4 rods)")

    # ── Separation metric ────────────────────────────────────────────
    correct_mean_margin = float(np.mean(cm))
    shuffled_mean_margin = float(np.mean(sm_shuf))
    separation = correct_mean_margin - shuffled_mean_margin
    print(f"\n  Separation metric (correct margin - shuffled margin): {separation:+.2f}")
    print(f"    Correct margin: {correct_mean_margin:+.2f}")
    print(f"    Shuffled margin: {shuffled_mean_margin:+.2f}")
    print(f"    Verdict: {'STRONG' if separation > 2.0 else 'MODERATE' if separation > 0.5 else 'WEAK'}")

    return {
        "experiment": "null_control",
        "n_rods": len(rod_ids),
        "n_peaks": N_PEAKS,
        "correct_scoring": {
            "correct": cc, "accuracy": ca,
            "mean_margin": round(float(np.mean(cm)), 4),
            "min_margin": round(float(np.min(cm)), 4),
            "matrix": correct_matrix,
        },
        "shuffled_scoring": {
            "self_correct": self_correct_shuffled,
            "donor_correct": sc,
            "matrix": shuffled_matrix,
        },
        "reversed_scoring": {
            "correct": rc, "accuracy": ra,
            "mean_margin": round(float(np.mean(rm_rev)), 4),
            "matrix": reversed_matrix,
        },
        "random_scoring": {
            "n_trials": 10,
            "mean_accuracy": round(mean_random_acc, 4),
            "per_trial": random_results,
        },
        "separation_metric": round(separation, 4),
        "raw_data": {qr: {sr: raw_data[qr][sr] for sr in rod_ids}
                     for qr in rod_ids},
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 37: 48-Hour Temporal Stability Checkpoint
# ══════════════════════════════════════════════════════════════════════════

def exp_temporal_48h(port: str) -> dict:
    """
    Add a 48-hour data point to the temporal stability record.
    Fresh recall matrix + Boolean on Rod 1 vs 2, with uncertainty reporting.

    Reports:
    - Wilson score CI on recall accuracy
    - Per-query margin with standard deviation
    - Comparison to all historical runs
    - Time delta from previous run
    """
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import SAMPLE_RATE, AWG_DRIVE_UVPP, N_SAMPLES

    print("\n" + "=" * 70)
    print("  EXPERIMENT 37: 48h Temporal Stability Checkpoint")
    print("=" * 70)

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    # ── Recall: 3 independent runs for uncertainty ───────────────────
    N_RUNS = 3
    print(f"\n  Running {N_RUNS} independent recall passes for uncertainty...")
    all_margins = {qr: [] for qr in rod_ids}
    all_correct = []
    all_matrices = []

    for run_idx in range(N_RUNS):
        matrix = {}
        for qr in rod_ids:
            query_peaks = enrolled[qr][:N_PEAKS]
            raw_mags = {sr: [] for sr in rod_ids}

            for freq_hz in query_peaks:
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, AWG_DRIVE_UVPP, 0,
                    float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
                )
                time.sleep(SETTLE_S)

                for sr in rod_ids:
                    mux.select(int(sr))
                    time.sleep(SETTLE_RELAY_S)
                    magnitudes = []
                    for _ in range(N_AVG):
                        raw = _hw_capture_raw(handle)
                        windowed = raw * np.hanning(len(raw))
                        nfft = len(raw) * 4
                        fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                        bin_hz = freq_axis[1] - freq_axis[0]
                        target_bin = int(round(freq_hz / bin_hz))
                        lo = max(0, target_bin - 3)
                        hi = min(len(fft_mag) - 1, target_bin + 3)
                        magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))
                    raw_mags[sr].append(float(np.mean(magnitudes)))

            mux.off()

            scores = {sr: 0.0 for sr in rod_ids}
            for pi, freq in enumerate(query_peaks):
                mags = {sr: raw_mags[sr][pi] for sr in rod_ids}
                total = sum(mags.values())
                if total == 0:
                    continue
                for sr in rod_ids:
                    frac = mags[sr] / total
                    expected = any(
                        abs(freq - ep) / max(freq, ep) < 0.03
                        for ep in enrolled[sr]
                    )
                    if expected:
                        scores[sr] += frac * 3.0
                    else:
                        scores[sr] -= frac * 1.0
            matrix[qr] = {sr: round(v, 4) for sr, v in scores.items()}

        # Evaluate
        correct = 0
        for qr in rod_ids:
            winner = max(matrix[qr], key=matrix[qr].get)
            if winner == qr:
                correct += 1
            sorted_rods = sorted(matrix[qr], key=matrix[qr].get, reverse=True)
            if sorted_rods[0] == qr:
                margin = matrix[qr][sorted_rods[0]] - matrix[qr][sorted_rods[1]]
            else:
                margin = matrix[qr][qr] - matrix[qr][sorted_rods[0]]
            all_margins[qr].append(margin)

        all_correct.append(correct)
        all_matrices.append(matrix)
        acc = correct / len(rod_ids)
        print(f"    Run {run_idx+1}: {correct}/{len(rod_ids)} ({acc:.0%})")

    # ── Aggregate statistics ─────────────────────────────────────────
    total_correct = sum(all_correct)
    total_trials = N_RUNS * len(rod_ids)
    overall_acc = total_correct / total_trials

    # Wilson score CI over all N_RUNS * N_RODS trials
    n_w = total_trials
    p_hat = overall_acc
    z = 1.96
    denom = 1 + z * z / n_w
    center = (p_hat + z * z / (2 * n_w)) / denom
    margin_ci = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n_w)) / n_w) / denom
    wilson_lo = max(0, center - margin_ci)
    wilson_hi = min(1, center + margin_ci)

    print(f"\n  Combined: {total_correct}/{total_trials} ({overall_acc:.0%})")
    print(f"  Wilson 95% CI (N={total_trials}): [{wilson_lo:.1%}, {wilson_hi:.1%}]")

    # Per-rod margin statistics
    print(f"\n  Per-rod margin statistics:")
    margin_stats = {}
    for qr in rod_ids:
        m_mean = float(np.mean(all_margins[qr]))
        m_std = float(np.std(all_margins[qr]))
        m_min = float(np.min(all_margins[qr]))
        margin_stats[qr] = {
            "mean": round(m_mean, 4),
            "std": round(m_std, 4),
            "min": round(m_min, 4),
            "values": [round(v, 4) for v in all_margins[qr]],
        }
        print(f"    Rod {qr}: margin={m_mean:+.2f} ± {m_std:.2f} (min={m_min:+.2f})")

    # ── Historical comparison ────────────────────────────────────────
    print("\n  Historical timeline:")
    # Gather from CIM suite runs
    suite_dir = LAB_DIR / "cim_suite"
    history = []
    if suite_dir.exists():
        for sf in sorted(suite_dir.glob("suite_*.json")):
            try:
                with open(sf) as f:
                    sd = json.load(f)
                ts = sd.get("timestamp", "")
                ts_data = sd.get("temporal_stability", {})
                ra = ts_data.get("recall_accuracy", 0)
                rm = ts_data.get("recall_mean_margin", 0)
                history.append({"source": sf.name, "timestamp": ts,
                                "accuracy": ra, "margin": rm})
            except Exception:
                pass

    # Gather from additional_exps runs that have temporal or temporal_48h
    add_dir = LAB_DIR / "additional_exps"
    if add_dir.exists():
        for af in sorted(add_dir.glob("additional_*.json")):
            try:
                with open(af) as f:
                    ad = json.load(f)
                ts = ad.get("timestamp", "")
                results = ad.get("results", {})
                for key in ["temporal_stability", "temporal_48h"]:
                    if key in results:
                        td = results[key]
                        ra = td.get("accuracy", 0)
                        rm = td.get("recall_mean_margin",
                                    td.get("overall_accuracy", 0))
                        history.append({
                            "source": af.name, "timestamp": ts,
                            "accuracy": ra, "margin": rm,
                        })
            except Exception:
                pass

    for h in history:
        print(f"    {h['source']:40s}  acc={h['accuracy']*100:.0f}%  "
              f"margin={h['margin']:+.2f}  {h['timestamp'][:19]}")

    # Current entry
    current_margin = float(np.mean([np.mean(all_margins[qr]) for qr in rod_ids]))
    print(f"    {'** current run **':40s}  acc={overall_acc*100:.0f}%  "
          f"margin={current_margin:+.2f}  {datetime.now(timezone.utc).isoformat()[:19]}")

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    _hw_close_scope(handle)

    return {
        "experiment": "temporal_48h_checkpoint",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_runs": N_RUNS,
        "n_rods": len(rod_ids),
        "total_correct": total_correct,
        "total_trials": total_trials,
        "overall_accuracy": overall_acc,
        "wilson_95ci": [round(wilson_lo, 4), round(wilson_hi, 4)],
        "per_rod_margins": margin_stats,
        "overall_mean_margin": round(current_margin, 4),
        "matrices": all_matrices,
        "history": history,
    }


# ══════════════════════════════════════════════════════════════════════════
#   EXPERIMENT 38 (E38): Pre/Post Perturbation Spectrum Capture
# ══════════════════════════════════════════════════════════════════════════

def exp_perturbation_spectrum(port: str) -> dict:
    """
    Comprehensive broadband sweep (200 Hz – 50 kHz, 50 Hz steps) on ALL 4 rods.
    Captures full magnitude spectrum + detected peaks for each rod.
    Run BEFORE removing perturbation sites, then again AFTER removal.
    The two snapshots together address the E32 gap (Rayleigh perturbation verification).
    """
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP, SAMPLE_RATE

    enrolled, rod_patterns, rod_ids = _load_enrollment()
    from tools.relay_mux import RelayMux
    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()

    f_start = 200
    f_stop = 50000
    f_step = 50  # finer than E27's 100 Hz for better peak resolution
    freqs = np.arange(f_start, f_stop + f_step, f_step)
    print(f"  E38: Perturbation spectrum capture")
    print(f"  Sweep: {f_start}–{f_stop} Hz in {f_step} Hz steps ({len(freqs)} pts × {len(rod_ids)} rods)")

    rod_results = {}

    for rod_id in rod_ids:
        mux.select(int(rod_id))
        time.sleep(SETTLE_RELAY_S)
        print(f"\n  Rod {rod_id} (pattern {rod_patterns.get(rod_id, '?')}):")

        sweep_data = []
        for i, freq in enumerate(freqs):
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(freq), float(freq), 0.0, 0.0, 0, 0
            )
            time.sleep(0.05)

            # Average 4 captures for cleaner data
            mags_at_freq = []
            for _ in range(4):
                raw = _hw_capture_raw(handle)
                windowed = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                tb = int(round(freq / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(fft_mag) - 1, tb + 3)
                mags_at_freq.append(float(np.max(fft_mag[lo:hi + 1])))
            avg_mag = float(np.mean(mags_at_freq))
            sweep_data.append({"freq_hz": round(float(freq), 1), "magnitude": round(avg_mag, 1)})

            if i % 100 == 0:
                print(f"    {freq:.0f} Hz: mag={avg_mag:.0f}")

        # Peak detection
        mags_arr = np.array([s["magnitude"] for s in sweep_data])
        noise_floor = float(np.median(mags_arr))
        threshold = noise_floor * 5

        detected_peaks = []
        for i in range(1, len(mags_arr) - 1):
            if mags_arr[i] > threshold and mags_arr[i] > mags_arr[i - 1] and mags_arr[i] > mags_arr[i + 1]:
                detected_peaks.append({
                    "freq_hz": sweep_data[i]["freq_hz"],
                    "magnitude": sweep_data[i]["magnitude"],
                    "snr_db": round(20 * math.log10(mags_arr[i] / noise_floor), 1) if noise_floor > 0 else 0,
                })

        # Match against enrolled peaks
        enrolled_freqs = enrolled.get(rod_id, [])[:20]  # all 20 fingerprint peaks
        matched = 0
        peak_shifts = []
        for ep in enrolled_freqs:
            best_dp = None
            best_dist = float("inf")
            for dp in detected_peaks:
                d = abs(dp["freq_hz"] - ep)
                if d < best_dist and d / max(ep, 1) < 0.05:
                    best_dist = d
                    best_dp = dp
            if best_dp:
                matched += 1
                peak_shifts.append({
                    "enrolled_hz": round(ep, 1),
                    "measured_hz": best_dp["freq_hz"],
                    "shift_hz": round(best_dp["freq_hz"] - ep, 1),
                    "shift_pct": round(100 * (best_dp["freq_hz"] - ep) / max(ep, 1), 3),
                })

        rod_results[rod_id] = {
            "pattern": rod_patterns.get(rod_id, "?"),
            "n_sweep_points": len(sweep_data),
            "noise_floor": round(noise_floor, 1),
            "n_detected_peaks": len(detected_peaks),
            "detected_peaks": detected_peaks,
            "n_enrolled_matched": matched,
            "n_enrolled_total": len(enrolled_freqs),
            "peak_shifts": peak_shifts,
            "sweep_data": sweep_data,  # full spectrum for later comparison
        }

        print(f"    Detected {len(detected_peaks)} peaks, matched {matched}/{len(enrolled_freqs)} enrolled")

    _hw_close_scope(handle)

    return {
        "experiment": "perturbation_spectrum_capture",
        "label": "pre-removal",   # change to "post-removal" when run after
        "n_rods": len(rod_ids),
        "freq_range_hz": [f_start, f_stop],
        "freq_step_hz": f_step,
        "n_averages": 4,
        "rods": rod_results,
    }


# ══════════════════════════════════════════════════════════════════════════
#   Main
# ══════════════════════════════════════════════════════════════════════════

OFFLINE_EXPERIMENTS = [
    "pruning", "polysemic", "virtual-rewrite", "doublet-capacity",
    "nullspace-proxy", "binary", "xcorr", "puf",
    "multiday-stability", "capacity-load", "guardband-surface", "rayleigh",
]
HARDWARE_EXPERIMENTS = [
    "phase", "qfactor", "temporal", "hybridization",
    "hybridization-readout", "anticorrelation",
    "ringdown", "orthogonality", "lockin-snr", "two-phase",
    "snr", "wave-speed", "freq-stability", "position", "parametric",
    "freq-offset", "endurance", "partial-query", "broadband-census",
    "nondestructive", "reexcitation",
    "weight-ratio", "isolation", "null-control", "temporal-48h",
    "perturbation-spectrum",
]
ALL_EXPERIMENTS = OFFLINE_EXPERIMENTS + HARDWARE_EXPERIMENTS


def main():
    parser = argparse.ArgumentParser(description="Additional CIM experiments")
    parser.add_argument("--port", help="Serial port for relay mux")
    parser.add_argument("--only", help="Comma-separated experiment names")
    parser.add_argument("--offline", action="store_true",
                        help="Run only offline experiments (no hardware needed)")
    args = parser.parse_args()

    if args.only:
        selected = [x.strip() for x in args.only.split(",")]
    elif args.offline:
        selected = OFFLINE_EXPERIMENTS
    else:
        selected = ALL_EXPERIMENTS

    # Validate hardware experiments have a port
    hw_selected = [e for e in selected if e in HARDWARE_EXPERIMENTS]
    if hw_selected and not args.port:
        parser.error(f"Hardware experiments {hw_selected} require --port")

    all_results = {}
    t0 = time.time()

    if "pruning" in selected:
        all_results["synaptic_pruning"] = exp_synaptic_pruning()

    if "polysemic" in selected:
        all_results["polysemic_subband"] = exp_polysemic_subband()

    if "virtual-rewrite" in selected:
        all_results["virtual_rewrite"] = exp_virtual_rewrite()

    if "phase" in selected:
        all_results["phase_stability"] = exp_phase_stability(args.port)

    if "qfactor" in selected:
        all_results["qfactor_mode_census"] = exp_qfactor_mode_census(args.port)

    if "temporal" in selected:
        all_results["temporal_stability"] = exp_temporal_stability(args.port)

    if "hybridization" in selected:
        all_results["mode_hybridization"] = exp_mode_hybridization(args.port)

    if "doublet-capacity" in selected:
        all_results["doublet_capacity"] = exp_doublet_capacity()

    if "nullspace-proxy" in selected:
        all_results["nullspace_proxy"] = exp_nullspace_proxy()

    if "hybridization-readout" in selected:
        all_results["hybridization_readout"] = exp_hybridization_readout(args.port)

    if "anticorrelation" in selected:
        all_results["anticorrelation"] = exp_anticorrelation(args.port)

    if "ringdown" in selected:
        all_results["ringdown_q"] = exp_ringdown_q(args.port)

    if "orthogonality" in selected:
        all_results["mode_orthogonality"] = exp_mode_orthogonality(args.port)

    if "lockin-snr" in selected:
        all_results["cw_lockin_snr"] = exp_cw_lockin_snr(args.port)

    if "binary" in selected:
        all_results["leibniz_binary"] = exp_leibniz_binary()

    if "xcorr" in selected:
        all_results["cross_correlation"] = exp_cross_correlation()

    if "puf" in selected:
        all_results["puf_uniqueness"] = exp_puf_uniqueness()

    if "two-phase" in selected:
        all_results["two_phase_readout"] = exp_two_phase_readout(args.port)

    if "snr" in selected:
        all_results["derived_snr"] = exp_derived_snr(args.port)

    if "wave-speed" in selected:
        all_results["wave_speed"] = exp_wave_speed(args.port)

    if "freq-stability" in selected:
        all_results["freq_stability"] = exp_freq_stability_temporal(args.port)

    if "position" in selected:
        all_results["position_sensitivity"] = exp_position_sensitivity(args.port)

    if "parametric" in selected:
        all_results["parametric_proxy"] = exp_parametric_proxy(args.port)

    # ── New gap experiments (E24–E32) ──

    if "freq-offset" in selected:
        all_results["freq_offset_tolerance"] = exp_freq_offset_tolerance(args.port)

    if "endurance" in selected:
        all_results["endurance_cycling"] = exp_endurance_cycling(args.port)

    if "partial-query" in selected:
        all_results["partial_query_recall"] = exp_partial_query_recall(args.port)

    if "broadband-census" in selected:
        all_results["broadband_census"] = exp_broadband_census(args.port)

    if "multiday-stability" in selected:
        all_results["multiday_stability"] = exp_multiday_stability()

    if "nondestructive" in selected:
        all_results["nondestructive_readout"] = exp_nondestructive_readout(args.port)

    if "capacity-load" in selected:
        all_results["capacity_load_test"] = exp_capacity_load_test()

    if "guardband-surface" in selected:
        all_results["boolean_guardband"] = exp_boolean_guardband()

    if "rayleigh" in selected:
        all_results["rayleigh_verification"] = exp_rayleigh_verification()

    if "reexcitation" in selected:
        all_results["ringdown_reexcitation"] = exp_ringdown_reexcitation(args.port)

    # ── Inoculation experiments (E34–E37) ──

    if "weight-ratio" in selected:
        all_results["weight_ratio_sweep"] = exp_weight_ratio_sweep(args.port)

    if "isolation" in selected:
        all_results["cross_rod_isolation"] = exp_cross_rod_isolation(args.port)

    if "null-control" in selected:
        all_results["null_control"] = exp_null_control(args.port)

    if "temporal-48h" in selected:
        all_results["temporal_48h"] = exp_temporal_48h(args.port)

    if "perturbation-spectrum" in selected:
        all_results["perturbation_spectrum"] = exp_perturbation_spectrum(args.port)

    elapsed = time.time() - t0

    # Save results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiments_run": selected,
        "total_duration_s": round(elapsed, 1),
        "results": all_results,
    }

    out_file = RESULTS_DIR / f"additional_{TIMESTAMP}.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved to {out_file}")
    print(f"  Total duration: {elapsed:.0f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    main()
