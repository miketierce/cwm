#!/usr/bin/env python3
"""
Phase 1.6 Step 1: Plate Q Measurement
Gate/Kill experiment — measures Q factor for all 5 fused silica plates.

Approach:
  1. Broadband CW sweep (200 Hz – 100 kHz, 100 Hz steps) to find resonances
  2. Ringdown τ measurement at top-N peaks per plate → Q = πfτ
  3. -3 dB bandwidth measurement around each peak → Q_bw = f / Δf
  4. Go/Kill decision: Q < 500 → KILL (skip to MEMS), Q > 1000 → GO

Wiring (per lab diary 2026-04-12):
  AWG → all 5 TX PZTs in parallel
  RX: Plate A→Relay 1, B→2, C→3, D→4, E→5 → PicoScope Ch A
"""
import ctypes
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# ── Paths ──
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

# Ensure DYLD_LIBRARY_PATH is set for PicoScope before any lazy imports
import cwm_picoscope  # noqa: F401 — triggers _ensure_dyld_path()

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab"
RESULTS_DIR = LAB_DIR / "plate_exps"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ── Plate config ──
PLATE_IDS = ["1", "2", "3", "4", "5"]  # relay channels
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

# ── Sweep config ──
F_START = 200       # Hz  (lowest bending mode for 100mm plate ~136 Hz)
F_STOP = 100_000    # Hz  (generous upper range)
F_STEP = 100        # Hz  (100 Hz steps for discovery)
N_AVG_SWEEP = 4     # averages per frequency point during sweep
SETTLE_S = 0.05     # settle time per frequency step (CW)
SETTLE_RELAY_S = 0.10  # settle after relay switch

# ── Ringdown config ──
EXCITE_S = 1.0      # seconds to excite before ringdown
N_PEAKS_TEST = 5    # number of strongest peaks to test per plate
RINGDOWN_CAPTURES = 3  # repeat ringdown for averaging

# ── Bandwidth config ──
BW_SWEEP_PTS = 41   # fine sweep points around each peak
BW_RANGE_PCT = 5    # ±5% around peak


def _hw_open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V DC
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B off
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


def _hw_capture_raw(handle):
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE, N_SAMPLES
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
        return np.array(buf_a[:n], dtype=np.float64)
    return np.zeros(N_SAMPLES, dtype=np.float64)


def broadband_sweep(handle, mux, plate_id: str) -> list[dict]:
    """CW sweep to find resonance peaks for a plate."""
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP, SAMPLE_RATE

    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    freqs = np.arange(F_START, F_STOP + F_STEP, F_STEP)
    name = PLATE_NAMES[plate_id]
    print(f"\n  Plate {name} (relay {plate_id}): broadband sweep "
          f"{F_START}–{F_STOP} Hz, {F_STEP} Hz steps ({len(freqs)} pts)")

    sweep_data = []
    t0 = time.time()

    for i, freq in enumerate(freqs):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq), float(freq), 0.0, 0.0, 0, 0
        )
        time.sleep(SETTLE_S)

        mags = []
        for _ in range(N_AVG_SWEEP):
            raw = _hw_capture_raw(handle)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            tb = int(round(freq / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft_mag) - 1, tb + 3)
            mags.append(float(np.max(fft_mag[lo:hi + 1])))

        avg_mag = float(np.mean(mags))
        sweep_data.append({"freq_hz": round(float(freq), 1), "magnitude": round(avg_mag, 1)})

        if i % 100 == 0:
            elapsed = time.time() - t0
            pct = (i + 1) / len(freqs) * 100
            print(f"    {freq:7.0f} Hz: mag={avg_mag:8.0f}  [{pct:4.1f}% | {elapsed:.0f}s]")

    elapsed = time.time() - t0
    print(f"    Sweep complete: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    return sweep_data


def detect_peaks(sweep_data: list[dict], min_snr_db: float = 10.0) -> list[dict]:
    """Find peaks in sweep data with SNR above threshold."""
    mags = np.array([s["magnitude"] for s in sweep_data])
    noise_floor = float(np.median(mags))
    if noise_floor <= 0:
        noise_floor = 1.0

    peaks = []
    for i in range(1, len(mags) - 1):
        if mags[i] > mags[i - 1] and mags[i] > mags[i + 1]:
            snr_db = 20 * math.log10(mags[i] / noise_floor)
            if snr_db >= min_snr_db:
                peaks.append({
                    "freq_hz": sweep_data[i]["freq_hz"],
                    "magnitude": sweep_data[i]["magnitude"],
                    "snr_db": round(snr_db, 1),
                })

    # Sort by magnitude descending
    peaks.sort(key=lambda p: p["magnitude"], reverse=True)
    return peaks


def measure_ringdown_q(handle, mux, plate_id: str, freq: float) -> dict:
    """Ringdown measurement at a single frequency."""
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP, SAMPLE_RATE
    from scipy.signal import hilbert

    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    tau_list = []
    q_list = []
    r2_list = []
    envelope_peaks = []

    for trial in range(RINGDOWN_CAPTURES):
        # Excite at resonance
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq), float(freq), 0.0, 0.0, 0, 0
        )
        time.sleep(EXCITE_S)

        # Kill drive
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
        time.sleep(0.001)

        # Capture ringdown
        raw = _hw_capture_raw(handle)
        t = np.arange(len(raw)) / SAMPLE_RATE
        analytic = hilbert(raw)
        envelope = np.abs(analytic)
        peak_val = float(np.max(envelope))
        envelope_peaks.append(peak_val)

        # Fit exponential on points > 5% of peak
        mask = envelope > peak_val * 0.05
        if np.sum(mask) > 20:
            t_m = t[mask]
            env_m = envelope[mask]
            log_env = np.log(env_m + 1e-30)
            coeffs = np.polyfit(t_m, log_env, 1)
            if coeffs[0] < 0:
                tau = -1.0 / coeffs[0]
                q = math.pi * freq * tau
                pred = coeffs[0] * t_m + coeffs[1]
                ss_res = np.sum((log_env - pred) ** 2)
                ss_tot = np.sum((log_env - np.mean(log_env)) ** 2)
                r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                tau_list.append(tau)
                q_list.append(q)
                r2_list.append(r2)

    result = {
        "freq_hz": round(freq, 1),
        "n_trials": RINGDOWN_CAPTURES,
        "n_good_fits": len(tau_list),
    }

    if tau_list:
        result["tau_ms_mean"] = round(float(np.mean(tau_list)) * 1000, 3)
        result["tau_ms_std"] = round(float(np.std(tau_list)) * 1000, 3)
        result["Q_ringdown_mean"] = round(float(np.mean(q_list)), 1)
        result["Q_ringdown_std"] = round(float(np.std(q_list)), 1)
        result["fit_r2_mean"] = round(float(np.mean(r2_list)), 4)
        result["envelope_peak_mean"] = round(float(np.mean(envelope_peaks)), 1)
    else:
        result["tau_ms_mean"] = None
        result["Q_ringdown_mean"] = None
        result["fit_r2_mean"] = None

    return result


def measure_bandwidth_q(handle, mux, plate_id: str, freq: float) -> dict:
    """Fine CW sweep around a peak to measure -3 dB bandwidth."""
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP, SAMPLE_RATE

    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    lo = freq * (1 - BW_RANGE_PCT / 100)
    hi = freq * (1 + BW_RANGE_PCT / 100)
    sweep_freqs = np.linspace(lo, hi, BW_SWEEP_PTS)
    sweep_mags = []

    for sf in sweep_freqs:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(sf), float(sf), 0.0, 0.0, 0, 0
        )
        time.sleep(0.05)
        raw = _hw_capture_raw(handle)
        windowed = raw * np.hanning(len(raw))
        nfft = len(raw) * 4
        fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
        bin_hz = freq_axis[1] - freq_axis[0]
        tb = int(round(sf / bin_hz))
        lo_b = max(0, tb - 5)
        hi_b = min(len(fft_mag) - 1, tb + 5)
        sweep_mags.append(float(np.max(fft_mag[lo_b:hi_b + 1])))

    sweep_mags = np.array(sweep_mags)
    peak_mag = float(np.max(sweep_mags))
    threshold_3db = peak_mag / math.sqrt(2)
    above = sweep_mags >= threshold_3db

    result = {"freq_hz": round(freq, 1), "peak_mag": round(peak_mag, 1)}

    if np.any(above):
        indices = np.where(above)[0]
        bw_hz = float(sweep_freqs[indices[-1]] - sweep_freqs[indices[0]])
        peak_f = float(sweep_freqs[np.argmax(sweep_mags)])
        if bw_hz > 0:
            result["bw_3db_hz"] = round(bw_hz, 2)
            result["Q_bandwidth"] = round(peak_f / bw_hz, 1)
            result["peak_freq_measured"] = round(peak_f, 1)
        else:
            result["bw_3db_hz"] = None
            result["Q_bandwidth"] = None
    else:
        result["bw_3db_hz"] = None
        result["Q_bandwidth"] = None

    return result


def run_plate_q_measurement(port: str) -> dict:
    """Main entry point: measure Q for all 5 plates."""
    from relay_mux import RelayMux

    print("\n" + "=" * 70)
    print("  PHASE 1.6 STEP 1: PLATE Q MEASUREMENT")
    print("  Gate/Kill: Q < 500 → KILL | Q > 1,000 → GO")
    print("=" * 70)

    handle = _hw_open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {mux.port}")

    all_results = {}
    t_start = time.time()

    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        print(f"\n{'─' * 70}")
        print(f"  PLATE {name} (relay {pid})")
        print(f"{'─' * 70}")

        # Phase 1: Broadband sweep
        sweep_data = broadband_sweep(handle, mux, pid)

        # Detect peaks
        peaks = detect_peaks(sweep_data)
        print(f"  Detected {len(peaks)} peaks (SNR > 10 dB)")
        for i, p in enumerate(peaks[:10]):
            print(f"    {i+1:2d}. {p['freq_hz']:8.1f} Hz  mag={p['magnitude']:8.0f}  "
                  f"SNR={p['snr_db']:.1f} dB")

        # Phase 2 & 3: Ringdown + bandwidth on top N peaks
        test_peaks = peaks[:N_PEAKS_TEST]
        ringdown_results = []
        bandwidth_results = []

        print(f"\n  Ringdown + bandwidth on top {len(test_peaks)} peaks:")
        for p in test_peaks:
            freq = p["freq_hz"]

            rd = measure_ringdown_q(handle, mux, pid, freq)
            ringdown_results.append(rd)

            bw = measure_bandwidth_q(handle, mux, pid, freq)
            bandwidth_results.append(bw)

            q_rd = rd.get("Q_ringdown_mean")
            q_bw = bw.get("Q_bandwidth")
            tau = rd.get("tau_ms_mean")
            r2 = rd.get("fit_r2_mean")
            bw_hz = bw.get("bw_3db_hz")

            q_rd_s = f"{q_rd:.0f}" if q_rd else "N/A"
            q_bw_s = f"{q_bw:.0f}" if q_bw else "N/A"
            tau_s = f"{tau:.2f} ms" if tau else "N/A"
            r2_s = f"{r2:.3f}" if r2 else "N/A"
            bw_s = f"{bw_hz:.1f} Hz" if bw_hz else "N/A"

            print(f"    {freq:8.1f} Hz: τ={tau_s}  Q_rd={q_rd_s}  "
                  f"BW={bw_s}  Q_bw={q_bw_s}  R²={r2_s}")

        # Collect Q values for this plate
        q_values = []
        for rd in ringdown_results:
            if rd.get("Q_ringdown_mean") is not None:
                q_values.append(rd["Q_ringdown_mean"])
        for bw in bandwidth_results:
            if bw.get("Q_bandwidth") is not None:
                q_values.append(bw["Q_bandwidth"])

        plate_q_median = float(np.median(q_values)) if q_values else 0
        plate_q_max = float(np.max(q_values)) if q_values else 0

        # Verdict
        if plate_q_max >= 1000:
            verdict = "GO ✅"
        elif plate_q_max >= 500:
            verdict = "MARGINAL ⚠️"
        else:
            verdict = "KILL ❌"

        print(f"\n  Plate {name} verdict: {verdict}")
        print(f"    Q median={plate_q_median:.0f}, max={plate_q_max:.0f} "
              f"(from {len(q_values)} measurements)")

        all_results[pid] = {
            "plate_name": name,
            "n_peaks_detected": len(peaks),
            "peaks_top10": peaks[:10],
            "sweep_data": sweep_data,
            "ringdown": ringdown_results,
            "bandwidth": bandwidth_results,
            "q_median": round(plate_q_median, 1),
            "q_max": round(plate_q_max, 1),
            "verdict": verdict,
        }

    # Cleanup
    mux.off()
    _hw_close_scope(handle)

    elapsed = time.time() - t_start
    print(f"\n{'=' * 70}")
    print(f"  OVERALL SUMMARY — {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"{'=' * 70}")
    print(f"  {'Plate':<8} {'Peaks':<8} {'Q_med':<10} {'Q_max':<10} {'Verdict'}")
    print(f"  {'─'*8} {'─'*8} {'─'*10} {'─'*10} {'─'*12}")

    any_go = False
    for pid in PLATE_IDS:
        r = all_results[pid]
        print(f"  {r['plate_name']:<8} {r['n_peaks_detected']:<8} "
              f"{r['q_median']:<10.0f} {r['q_max']:<10.0f} {r['verdict']}")
        if "GO" in r["verdict"]:
            any_go = True

    if any_go:
        print(f"\n  DECISION: At least one plate passes → PROCEED to Step 2 (broadband census)")
    else:
        print(f"\n  DECISION: No plate reached Q > 500 → consider MEMS path")

    # Save
    out_path = RESULTS_DIR / f"plate_q_{TIMESTAMP}.json"
    save_data = {
        "experiment": "Phase 1.6 Step 1: Plate Q Measurement",
        "timestamp": TIMESTAMP,
        "elapsed_s": round(elapsed, 1),
        "config": {
            "f_start": F_START, "f_stop": F_STOP, "f_step": F_STEP,
            "n_avg_sweep": N_AVG_SWEEP, "n_peaks_test": N_PEAKS_TEST,
            "ringdown_captures": RINGDOWN_CAPTURES,
            "plate_ids": PLATE_IDS, "plate_names": PLATE_NAMES,
        },
        "results": all_results,
    }
    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Data saved: {out_path}")

    return save_data


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-11310"
    run_plate_q_measurement(port)
