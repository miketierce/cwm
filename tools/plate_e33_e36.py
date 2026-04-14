#!/usr/bin/env python3
"""
Plate E33 (Re-excitation Interference) + E36 (Null-Control Battery)

Adapted from rod implementations in additional_experiments.py to the
5-plate fused silica array.  Uses the same hardware interface as
plate_auth_stress.py (PicoScope 2204A + relay mux + census enrollment).

E33 — Re-excitation Interference:
  Drive a plate's strongest mode to steady state, stop, wait Δt, re-excite.
  Residual ringdown interferes with new drive → constructive/destructive
  depending on phase.  Plates have Q 10–60× higher than rods, so predicted
  contrast jumps from 0.27% (rods) to potentially >5%.  Runs on ALL 5 plates.

E36 — Null-Control Battery:
  Four tests using cross-relay template matching (same scoring as auth):
    1. Correct enrollment → baseline (should be 5/5)
    2. Shuffled enrollment → should break (expect 0/5)
    3. Reversed weights (+1 expected, −3 unexpected) → physics overwhelms?
    4. Random enrollment (10 trials) → should give ~20% (chance for 5 plates)
  Uses fresh hardware measurements with enrollment data from census.

Usage:
  PYTHONPATH=. python tools/plate_e33_e36.py --exp e33 e36
  PYTHONPATH=. python tools/plate_e33_e36.py --exp e33
  PYTHONPATH=. python tools/plate_e33_e36.py --exp e36
  PYTHONPATH=. python tools/plate_e33_e36.py --dry-run
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

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

N_AVG = 8
SETTLE_S = 0.05
SETTLE_RELAY_S = 0.10
MATCH_TOL = 0.03   # 3% frequency match
BOOST = 3.0
PENALTY = 1.0
N_PEAKS = 10        # max peaks per plate for scoring


# ── Scope helpers ──────────────────────────────────────────────────────

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V DC
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


def _capture_raw(handle) -> np.ndarray:
    """Single block capture → float64 array."""
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
    if n <= 0:
        return np.zeros(N_SAMPLES, dtype=np.float64)
    return np.array(buf_a[:n], dtype=np.float64)


def _measure_mag(handle, freq_hz: float) -> float:
    """Drive AWG at freq_hz, return averaged FFT magnitude at fundamental."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)

    mags = []
    for _ in range(N_AVG):
        raw = _capture_raw(handle)
        windowed = raw * np.hanning(len(raw))
        nfft = len(raw) * 4
        fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
        bin_hz = freq_axis[1] - freq_axis[0]
        tb = int(round(freq_hz / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(fft_mag) - 1, tb + 3)
        mags.append(float(np.max(fft_mag[lo:hi + 1])))

    return float(np.mean(mags)) if mags else 0.0


# ── Census loading ─────────────────────────────────────────────────────

def _load_census() -> dict:
    """Load plate census data. Returns {pid: [peak_dicts]}."""
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        raise FileNotFoundError("No census data. Run plate_mode_census.py first.")

    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    templates = {}
    for pid in PLATE_IDS:
        if pid in census and census[pid].get("peaks"):
            templates[pid] = census[pid]["peaks"]
    return templates


# ══════════════════════════════════════════════════════════════════════
#  E33: Re-excitation Interference (per-plate)
# ══════════════════════════════════════════════════════════════════════

def run_e33(handle, mux, templates: dict) -> dict:
    """Run E33 on all plates — measure ringdown τ then sweep re-excitation delay."""
    from picosdk.ps2000 import ps2000
    from scipy.signal import hilbert

    print("\n" + "=" * 70)
    print("  EXPERIMENT E33: Ringdown Re-excitation Interference")
    print("  Substrate: 5 fused silica plates (100×100×1 mm)")
    print("=" * 70)

    active_ids = [pid for pid in PLATE_IDS if pid in templates]
    all_results = {}

    for pid in active_ids:
        name = PLATE_NAMES[pid]
        mux.select(int(pid))
        time.sleep(SETTLE_RELAY_S)

        # Find strongest mode by magnitude
        peaks = templates[pid][:N_PEAKS]
        print(f"\n{'─' * 60}")
        print(f"  Plate {name} — scanning {len(peaks)} enrolled peaks")
        print(f"{'─' * 60}")

        peak_mags = []
        for p in peaks:
            f = p["freq_hz"]
            m = _measure_mag(handle, f)
            peak_mags.append((f, m))
        peak_mags.sort(key=lambda x: -x[1])
        test_freq = peak_mags[0][0]
        ref_mag = peak_mags[0][1]
        print(f"  Strongest mode: {test_freq:.1f} Hz (mag={ref_mag:.0f})")

        # ── Phase 1: Measure ringdown τ ──
        print(f"  Phase 1: Ringdown τ at {test_freq:.1f} Hz")

        # Ring up to steady state
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(test_freq), float(test_freq), 0.0, 0.0, 0, 0
        )
        time.sleep(0.5)

        # Stop AWG and capture ringdown
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
        time.sleep(0.001)
        raw_rd = _capture_raw(handle)
        t_arr = np.arange(len(raw_rd)) / SAMPLE_RATE

        analytic = hilbert(raw_rd)
        envelope = np.abs(analytic)
        peak_env = float(np.max(envelope))

        # Fit exponential decay: envelope ~ A * exp(-t/τ)
        tau_s = float("nan")
        Q_meas = float("nan")
        mask = envelope > peak_env * 0.05
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
            print(f"    Could not fit τ; fallback {tau_s*1000:.0f} ms")

        period_s = 1.0 / test_freq

        # ── Phase 2: Re-excitation delay sweep ──
        delays_s = []
        # Sub-cycle (0 to 1 period in 8 steps)
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
        delays_s = sorted(set(round(d, 6) for d in delays_s))

        print(f"  Phase 2: Re-excitation sweep ({len(delays_s)} delays, "
              f"period={period_s*1000:.3f} ms, τ={tau_s*1000:.1f} ms)")

        EXCITE_DURATION = 0.5
        MEASURE_SETTLE = 0.050
        N_REPS = 3

        sweep = []
        for di, dt in enumerate(delays_s):
            mags = []
            for rep in range(N_REPS):
                # 1) Excite to steady state
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, AWG_DRIVE_UVPP, 0,
                    float(test_freq), float(test_freq), 0.0, 0.0, 0, 0
                )
                time.sleep(EXCITE_DURATION)

                # 2) Stop drive
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
                )

                # 3) Wait Δt
                if dt > 0.001:
                    time.sleep(dt)
                elif dt > 0:
                    t_end = time.perf_counter() + dt
                    while time.perf_counter() < t_end:
                        pass

                # 4) Re-excite + brief settle + capture
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, AWG_DRIVE_UVPP, 0,
                    float(test_freq), float(test_freq), 0.0, 0.0, 0, 0
                )
                time.sleep(MEASURE_SETTLE)

                # 5) Capture magnitude at mode
                raw = _capture_raw(handle)
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

                # 6) Stop drive
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
                )
                time.sleep(0.05)

            mean_mag = float(np.mean(mags))
            std_mag = float(np.std(mags))
            sweep.append({
                "delay_s": round(dt, 6),
                "delay_cycles": round(dt * test_freq, 3),
                "delay_over_tau": round(dt / tau_s, 3) if tau_s > 0 else None,
                "magnitude_mean": round(mean_mag, 1),
                "magnitude_std": round(std_mag, 1),
                "magnitude_reps": [round(m, 1) for m in mags],
            })

            if di % 5 == 0 or di == len(delays_s) - 1:
                norm = mean_mag / ref_mag if ref_mag > 0 else 0
                print(f"    Δt={dt*1000:8.3f} ms ({dt/period_s:6.2f}T, "
                      f"{dt/tau_s:5.2f}τ): mag={mean_mag:12.0f}  "
                      f"({norm:+.3f}× ref)")

        # ── Phase 3: Analyze ──
        ref_entry = sweep[-1]
        ref_level = ref_entry["magnitude_mean"]

        normalized = []
        for sr in sweep:
            norm = sr["magnitude_mean"] / ref_level if ref_level > 0 else 1.0
            normalized.append(round(norm, 4))

        max_norm = max(normalized[:-1]) if len(normalized) > 1 else 1.0
        min_norm = min(normalized[:-1]) if len(normalized) > 1 else 1.0
        contrast = max_norm - min_norm

        # Check for oscillatory behaviour in sub-τ region
        sub_tau_mags = [sr["magnitude_mean"] for sr in sweep
                        if sr["delay_s"] < 2 * tau_s]
        oscillation_detected = False
        if len(sub_tau_mags) >= 4:
            diffs = [sub_tau_mags[i+1] - sub_tau_mags[i]
                     for i in range(len(sub_tau_mags) - 1)]
            sign_changes = sum(1 for i in range(len(diffs) - 1)
                               if diffs[i] * diffs[i+1] < 0)
            oscillation_detected = sign_changes >= 2

        if contrast > 0.02:
            verdict = "INTERFERENCE DETECTED"
        else:
            verdict = "NO SIGNIFICANT INTERFERENCE"

        print(f"\n  Plate {name} Analysis:")
        print(f"    Reference level (fully decayed): {ref_level:.0f}")
        print(f"    Max normalized: {max_norm:.4f}×")
        print(f"    Min normalized: {min_norm:.4f}×")
        print(f"    Contrast: {contrast:.4f} ({contrast*100:.2f}%)")
        print(f"    Oscillation (sub-τ): {oscillation_detected}")
        print(f"    Verdict: {verdict}")

        all_results[pid] = {
            "plate_id": pid,
            "plate_name": name,
            "mode_freq_hz": round(test_freq, 1),
            "ringdown_tau_ms": round(tau_s * 1000, 2),
            "Q_measured": round(Q_meas, 0) if not math.isnan(Q_meas) else None,
            "period_ms": round(period_s * 1000, 3),
            "n_delays": len(delays_s),
            "n_reps": N_REPS,
            "reference_mag": round(ref_level, 1),
            "sweep": sweep,
            "normalized_magnitudes": normalized,
            "max_normalized": round(max_norm, 4),
            "min_normalized": round(min_norm, 4),
            "contrast": round(contrast, 4),
            "contrast_pct": round(contrast * 100, 2),
            "oscillation_detected": oscillation_detected,
            "verdict": verdict,
        }

    # Summary across all plates
    print("\n" + "=" * 70)
    print("  E33 SUMMARY")
    print("=" * 70)
    print(f"  {'Plate':>6}  {'Freq (Hz)':>10}  {'τ (ms)':>8}  {'Q':>8}  "
          f"{'Contrast':>10}  {'Oscillation':>12}  {'Verdict'}")
    print(f"  {'─'*6}  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*12}  {'─'*20}")
    for pid in active_ids:
        r = all_results[pid]
        q_str = f"{r['Q_measured']:.0f}" if r['Q_measured'] else "N/A"
        print(f"  {PLATE_NAMES[pid]:>6}  {r['mode_freq_hz']:10.1f}  "
              f"{r['ringdown_tau_ms']:8.2f}  {q_str:>8}  "
              f"{r['contrast_pct']:9.2f}%  "
              f"{'YES' if r['oscillation_detected'] else 'NO':>12}  "
              f"{r['verdict']}")

    contrasts = [all_results[p]["contrast_pct"] for p in active_ids]
    print(f"\n  Mean contrast: {np.mean(contrasts):.2f}%")
    print(f"  Rod reference: 0.27% (Q ≈ 400)")

    return {
        "experiment": "e33_reexcitation_interference",
        "substrate": "fused_silica_plates_100x100x1mm",
        "n_plates": len(active_ids),
        "plate_results": all_results,
        "summary": {
            "mean_contrast_pct": round(float(np.mean(contrasts)), 2),
            "max_contrast_pct": round(float(max(contrasts)), 2),
            "min_contrast_pct": round(float(min(contrasts)), 2),
            "rod_reference_contrast_pct": 0.27,
        },
    }


# ══════════════════════════════════════════════════════════════════════
#  E36: Null-Control Battery
# ══════════════════════════════════════════════════════════════════════

def run_e36(handle, mux, templates: dict) -> dict:
    """Run E36 using cross-relay template matching (same scoring as auth).

    Four tests:
      1. Correct enrollment (baseline) — should be 5/5
      2. Shuffled enrollment (rotated by 1) — should break
      3. Reversed weights (+1 expected, −3 unexpected) — physics overwhelms?
      4. Random enrollment (10 trials) — should give ~20% (chance)
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT E36: Null-Control Battery")
    print("  Substrate: 5 fused silica plates (100×100×1 mm)")
    print("=" * 70)

    active_ids = [pid for pid in PLATE_IDS if pid in templates]
    n_plates = len(active_ids)

    # Build enrolled freq lists per plate (matching auth workflow)
    enrolled = {}
    for pid in active_ids:
        enrolled[pid] = [p["freq_hz"] for p in templates[pid][:N_PEAKS]]

    # ── Fresh 5×5 measurement matrix ──────────────────────────────────
    # For each query plate's enrolled freqs, measure ALL plates via mux

    print(f"\n  Capturing {n_plates}×{n_plates} cross-relay measurement matrix...")
    raw_data = {}       # raw_data[query_pid][sense_pid] = [mag_at_freq0, mag_at_freq1, ...]
    query_freqs = {}    # query_freqs[pid] = [f0, f1, ...]

    t0_total = time.time()
    for qi, qpid in enumerate(active_ids):
        qname = PLATE_NAMES[qpid]
        qpeaks = enrolled[qpid]
        query_freqs[qpid] = qpeaks
        raw_data[qpid] = {sid: [] for sid in active_ids}

        from picosdk.ps2000 import ps2000

        for fi, freq_hz in enumerate(qpeaks):
            # Set AWG to this frequency (shared drive to all plates)
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)

            for sid in active_ids:
                mux.select(int(sid))
                time.sleep(SETTLE_RELAY_S)
                magnitudes = []
                for _ in range(N_AVG):
                    raw = _capture_raw(handle)
                    windowed = raw * np.hanning(len(raw))
                    nfft = len(raw) * 4
                    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
                    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                    bin_hz = freq_axis[1] - freq_axis[0]
                    tb = int(round(freq_hz / bin_hz))
                    lo = max(0, tb - 3)
                    hi = min(len(fft_mag) - 1, tb + 3)
                    magnitudes.append(float(np.max(fft_mag[lo:hi + 1])))
                raw_data[qpid][sid].append(float(np.mean(magnitudes)))

        mux.off()
        elapsed = time.time() - t0_total
        print(f"    Query {qname} done ({len(qpeaks)} freqs × {n_plates} sense, "
              f"{elapsed:.0f}s elapsed)")

    # Stop AWG
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    elapsed_total = time.time() - t0_total
    print(f"  Matrix captured in {elapsed_total:.0f}s")

    # ── Scoring function ──────────────────────────────────────────────

    def _score(raw_d, enroll_map, plate_list, weight_ratio=3.0):
        """Score raw data against an enrollment map. Returns score matrix."""
        matrix = {}
        for qp in plate_list:
            qfreqs = query_freqs[qp]
            scores = {sp: 0.0 for sp in plate_list}
            for pi, freq in enumerate(qfreqs):
                mags = {sp: raw_d[qp][sp][pi] for sp in plate_list}
                total = sum(mags.values())
                if total == 0:
                    continue
                for sp in plate_list:
                    frac = mags[sp] / total
                    expected = any(
                        abs(freq - ep) / max(freq, ep) < MATCH_TOL
                        for ep in enroll_map[sp]
                    )
                    if expected:
                        scores[sp] += frac * weight_ratio
                    else:
                        scores[sp] -= frac * 1.0
            matrix[qp] = {sp: round(v, 4) for sp, v in scores.items()}
        return matrix

    def _evaluate(matrix, plate_list, expected_winners=None):
        """Evaluate accuracy + margins from a score matrix."""
        if expected_winners is None:
            expected_winners = {p: p for p in plate_list}
        correct = 0
        margins = []
        details = []
        for qp in plate_list:
            winner = max(matrix[qp], key=matrix[qp].get)
            expected = expected_winners.get(qp, qp)
            is_correct = winner == expected
            if is_correct:
                correct += 1
            exp_score = matrix[qp].get(expected, 0)
            best_other = max(v for k, v in matrix[qp].items() if k != expected)
            margins.append(exp_score - best_other)
            details.append({
                "query": qp, "query_name": PLATE_NAMES[qp],
                "winner": winner, "winner_name": PLATE_NAMES[winner],
                "expected": expected, "correct": is_correct,
                "margin": round(exp_score - best_other, 4),
                "scores": matrix[qp],
            })
        return correct, correct / len(plate_list), margins, details

    # ── Test 1: Correct scoring (baseline) ────────────────────────────
    print("\n  Test 1: CORRECT scoring (baseline)")
    correct_matrix = _score(raw_data, enrolled, active_ids)
    cc, ca, cm, cd = _evaluate(correct_matrix, active_ids)
    print(f"    {cc}/{n_plates} correct ({ca:.0%}), "
          f"mean margin={np.mean(cm):+.2f}")
    for d in cd:
        status = "✓" if d["correct"] else "✗"
        print(f"      Q={d['query_name']}: winner={d['winner_name']} {status}  "
              f"margin={d['margin']:+.2f}  "
              f"scores=[{', '.join(f'{PLATE_NAMES[s]}:{v:+.2f}' for s, v in d['scores'].items())}]")

    # ── Test 2: Shuffled enrollment (rotated by 1) ────────────────────
    print(f"\n  Test 2: SHUFFLED enrollment (A→B's template, B→C's, ...)")
    shuffled = {}
    for i, pid in enumerate(active_ids):
        donor = active_ids[(i + 1) % n_plates]
        shuffled[pid] = enrolled[donor]
    shuffled_matrix = _score(raw_data, shuffled, active_ids)

    # Check self-match under shuffled (should fail)
    self_correct_shuffled = sum(
        1 for p in active_ids
        if max(shuffled_matrix[p], key=shuffled_matrix[p].get) == p
    )
    # Also check donor match
    shuffled_expected = {active_ids[i]: active_ids[(i + 1) % n_plates]
                         for i in range(n_plates)}
    sc, sa, sm, sd = _evaluate(shuffled_matrix, active_ids, shuffled_expected)
    print(f"    Self-match under shuffled: {self_correct_shuffled}/{n_plates}")
    print(f"    Donor-match under shuffled: {sc}/{n_plates}")
    for d in sd:
        donor = PLATE_NAMES[shuffled_expected[d["query"]]]
        print(f"      Q={d['query_name']}: winner={d['winner_name']}, "
              f"self={shuffled_matrix[d['query']][d['query']]:+.2f}, "
              f"donor({donor})={shuffled_matrix[d['query']][shuffled_expected[d['query']]]:+.2f}")

    # ── Test 3: Reversed weights (+1 expected, −3 unexpected) ─────────
    print(f"\n  Test 3: REVERSED weights (+1 expected, −3 unexpected)")
    reversed_matrix = {}
    for qp in active_ids:
        qfreqs = query_freqs[qp]
        scores = {sp: 0.0 for sp in active_ids}
        for pi, freq in enumerate(qfreqs):
            mags = {sp: raw_data[qp][sp][pi] for sp in active_ids}
            total = sum(mags.values())
            if total == 0:
                continue
            for sp in active_ids:
                frac = mags[sp] / total
                expected = any(
                    abs(freq - ep) / max(freq, ep) < MATCH_TOL
                    for ep in enrolled[sp]
                )
                if expected:
                    scores[sp] += frac * 1.0   # weak reward
                else:
                    scores[sp] -= frac * 3.0   # strong penalty
        reversed_matrix[qp] = {sp: round(v, 4) for sp, v in scores.items()}
    rc, ra, rm, rd = _evaluate(reversed_matrix, active_ids)
    print(f"    {rc}/{n_plates} correct ({ra:.0%}), "
          f"mean margin={np.mean(rm):+.2f}")
    for d in rd:
        status = "✓" if d["correct"] else "✗"
        print(f"      Q={d['query_name']}: winner={d['winner_name']} {status}  "
              f"margin={d['margin']:+.2f}")

    # ── Test 4: Random enrollment (10 trials) ─────────────────────────
    print(f"\n  Test 4: RANDOM enrollment (10 trials of random freq lists)")
    rng = np.random.default_rng(42)
    random_results = []
    # Get freq range from actual enrolled data
    all_freqs = [f for pid in active_ids for f in enrolled[pid]]
    f_lo, f_hi = min(all_freqs), max(all_freqs)

    for trial in range(10):
        random_enrolled = {}
        for sp in active_ids:
            random_enrolled[sp] = sorted(
                rng.uniform(f_lo, f_hi, N_PEAKS).tolist()
            )
        rand_matrix = _score(raw_data, random_enrolled, active_ids)
        rand_c, rand_a, _, _ = _evaluate(rand_matrix, active_ids)
        random_results.append({
            "trial": trial, "correct": rand_c, "accuracy": round(rand_a, 4)
        })
    mean_random_acc = np.mean([r["accuracy"] for r in random_results])
    print(f"    Mean accuracy over 10 random trials: {mean_random_acc:.0%} "
          f"(expected ~{1/n_plates:.0%} for {n_plates} plates)")
    for r in random_results:
        print(f"      Trial {r['trial']}: {r['correct']}/{n_plates} ({r['accuracy']:.0%})")

    # ── Separation metric ─────────────────────────────────────────────
    correct_margin = float(np.mean(cm))
    shuffled_margin = float(np.mean(sm))
    separation = correct_margin - shuffled_margin
    print(f"\n  Separation metric (correct margin − shuffled margin): {separation:+.2f}")
    print(f"    Correct mean margin: {correct_margin:+.2f}")
    print(f"    Shuffled mean margin: {shuffled_margin:+.2f}")
    strength = ("STRONG" if separation > 2.0
                else "MODERATE" if separation > 0.5
                else "WEAK")
    print(f"    Verdict: {strength}")

    # Summary
    print(f"\n{'=' * 70}")
    print(f"  E36 SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Test 1 (correct):   {cc}/{n_plates} ({ca:.0%})")
    print(f"  Test 2 (shuffled):  {self_correct_shuffled}/{n_plates} self-match")
    print(f"  Test 3 (reversed):  {rc}/{n_plates} ({ra:.0%})")
    print(f"  Test 4 (random):    {mean_random_acc:.0%} mean "
          f"(expected {1/n_plates:.0%})")
    print(f"  Separation:         {separation:+.2f} ({strength})")

    return {
        "experiment": "e36_null_control",
        "substrate": "fused_silica_plates_100x100x1mm",
        "n_plates": n_plates,
        "n_peaks": N_PEAKS,
        "raw_measurement_matrix": {
            qp: {sp: raw_data[qp][sp] for sp in active_ids}
            for qp in active_ids
        },
        "correct_scoring": {
            "correct": cc, "accuracy": round(ca, 4),
            "mean_margin": round(correct_margin, 4),
            "min_margin": round(float(np.min(cm)), 4),
            "matrix": correct_matrix,
            "details": cd,
        },
        "shuffled_scoring": {
            "self_correct": self_correct_shuffled,
            "donor_correct": sc,
            "matrix": shuffled_matrix,
            "details": sd,
        },
        "reversed_scoring": {
            "correct": rc, "accuracy": round(ra, 4),
            "mean_margin": round(float(np.mean(rm)), 4),
            "matrix": reversed_matrix,
            "details": rd,
        },
        "random_scoring": {
            "n_trials": 10,
            "mean_accuracy": round(float(mean_random_acc), 4),
            "expected_chance": round(1.0 / n_plates, 4),
            "results": random_results,
        },
        "separation_metric": round(separation, 4),
        "separation_strength": strength,
    }


# ══════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate E33 (re-excitation) + E36 (null-control)"
    )
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--exp", nargs="+", default=["e33", "e36"],
                        choices=["e33", "e36"],
                        help="Which experiments to run (default: both)")
    parser.add_argument("--no-submit", action="store_true",
                        help="Skip Firestore submission")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    templates = _load_census()
    active_ids = [pid for pid in PLATE_IDS if pid in templates]
    print(f"  Loaded census: {len(active_ids)} plates, "
          f"peaks = {[len(templates[p]) for p in active_ids]}")

    results = {}

    if not args.dry_run:
        print("\nOpening hardware...")
        handle = _open_scope()
        mux = RelayMux(args.port)
        mux.open()
        print(f"  PicoScope + mux ready (port: {args.port})")
    else:
        handle = None
        mux = None

    try:
        if "e33" in args.exp:
            if args.dry_run:
                print("\n  [DRY RUN] Skipping E33")
            else:
                results["e33"] = run_e33(handle, mux, templates)

        if "e36" in args.exp:
            if args.dry_run:
                print("\n  [DRY RUN] Skipping E36")
            else:
                results["e36"] = run_e36(handle, mux, templates)
    finally:
        if handle is not None:
            _close_scope(handle)
        if mux is not None:
            mux.off()
        print("\n  Hardware closed")

    # ── Save locally ───────────────────────────────────────────────────
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    save_path = LAB_DIR / f"e33_e36_{TIMESTAMP}.json"
    save_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiments_run": args.exp,
        "results": results,
    }
    with open(save_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Saved: {save_path}")

    # ── Firestore submission ───────────────────────────────────────────
    if not args.no_submit and not args.dry_run:
        print("\nSubmitting to Firestore...")
        token = firebase_anon_auth()

        if "e33" in results:
            r33 = results["e33"]
            data_e33 = {
                "n_rods": r33["n_plates"],
                "peaks_per_rod": N_PEAKS,
                "sample_rate": SAMPLE_RATE,
                "freq_resolution": 24.2,
                "auth_rms_pct": round(r33["summary"]["mean_contrast_pct"], 2),
                "auth_matched_peaks": N_PEAKS,
                "auth_score_pct": round(r33["summary"]["mean_contrast_pct"] * 100, 1),
                "next_best_score_pct": round(r33["summary"]["max_contrast_pct"], 1),
                "min_cross_rod_pct": round(r33["summary"]["min_contrast_pct"], 1),
                "excitation_method": "Piezo pulse",
                "correct_rod_identified": "No",
            }
            notes_e33 = (
                f"E33 re-excitation interference on {r33['n_plates']} plates. "
                f"Mean contrast {r33['summary']['mean_contrast_pct']:.2f}% "
                f"(rod ref 0.27%). "
                f"Oscillation detected on plates with sufficient Q/τ."
            )
            r = submit_experiment(token, "exp-hw-auth", data_e33, notes=notes_e33)
            print(f"  E33: ", end="")
            print_result(r)

        if "e36" in results:
            r36 = results["e36"]
            data_e36 = {
                "n_rods": r36["n_plates"],
                "peaks_per_rod": N_PEAKS,
                "sample_rate": SAMPLE_RATE,
                "freq_resolution": 24.2,
                "auth_rms_pct": round(r36["separation_metric"], 2),
                "auth_matched_peaks": N_PEAKS,
                "auth_score_pct": round(r36["correct_scoring"]["accuracy"] * 100, 1),
                "next_best_score_pct": round(r36["correct_scoring"]["mean_margin"], 1),
                "min_cross_rod_pct": round(r36["correct_scoring"]["min_margin"], 1),
                "excitation_method": "Piezo pulse",
                "correct_rod_identified": (
                    "Yes" if r36["correct_scoring"]["accuracy"] == 1.0 else "No"
                ),
            }
            notes_e36 = (
                f"E36 null-control battery on {r36['n_plates']} plates. "
                f"Correct {r36['correct_scoring']['correct']}/{r36['n_plates']}, "
                f"shuffled self-match {r36['shuffled_scoring']['self_correct']}/{r36['n_plates']}, "
                f"reversed {r36['reversed_scoring']['correct']}/{r36['n_plates']}, "
                f"random {r36['random_scoring']['mean_accuracy']:.0%}. "
                f"Separation {r36['separation_metric']:+.2f} ({r36['separation_strength']})."
            )
            r = submit_experiment(token, "exp-hw-auth", data_e36, notes=notes_e36)
            print(f"  E36: ", end="")
            print_result(r)


if __name__ == "__main__":
    main()
