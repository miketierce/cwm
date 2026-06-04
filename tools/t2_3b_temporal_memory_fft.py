#!/usr/bin/env python3
"""
T2.3b — Ring-down Temporal Memory (FFT-Based, Phase-Sensitive)

Improved version of T2.3 using lessons from T3.1:
  - FFT-bin-specific magnitude at f_probe (isolates from f_prime residual)
  - Complex FFT phase tracking at f_probe
  - Records f_prime residual magnitude (confirms priming energy in plate)
  - Shorter gaps (0.5, 1 ms where f_prime is still >80% amplitude)
  - More averages (50+) for sub-1% sensitivity
  - Full spectrum check for sum/difference frequencies (f1±f2)

Protocol:
  1. CONDITION A (primed): Drive f1 for 50 ms → stop → wait gap →
     drive f2 for 5 ms → capture FFT → extract f2 magnitude+phase
  2. CONDITION B (unprimed): Equivalent silence → drive f2 → capture
  3. Compare f2 response between A and B (amplitude, phase, sum/diff bins)

Key improvement over T2.3: uses bin-specific FFT measurement (like T3.1)
instead of broadband peak-to-peak. At short gaps, the broadband signal
was contaminated by f1 residual, masking any f2-specific coupling.

Success criterion: >2σ difference in f_probe's FFT bin (amplitude or phase)

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t2_3b_temporal_memory_fft.py

  # More averages:
  python tools/t2_3b_temporal_memory_fft.py --averages 80
"""
from __future__ import annotations

import argparse
import ctypes as ct
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SAMPLE_RATE_HZ = 781_250
N_SAMPLES = 2048
TIMEBASE = 7
RANGE_INDEX = 8        # ±5V
RANGE_MV = 5000.0
RELAY_CH = 8
N_FFT_PAD = 4

AWG_DRIVE_UVPP = 500_000   # 0.5 Vpp

T_WRITE_MS = 50            # prime mode for 50 ms
T_PROBE_MS = 5             # brief probe excitation
DEFAULT_GAPS_MS = [0.5, 1, 2, 5, 10, 20, 40]

# Mode pairs: (prime_freq, probe_freq)
DEFAULT_PAIRS = [
    (35_840.0, 57_037.0),
    (57_037.0, 35_840.0),
    (54_920.0, 97_011.0),
    (97_011.0, 54_920.0),
]

N_AVG_DEFAULT = 50

os.environ['DYLD_LIBRARY_PATH'] = (
    '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relay_mux import RelayMux  # noqa: E402

# ---------------------------------------------------------------------------
# PicoScope helpers
# ---------------------------------------------------------------------------


def open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, 1, 1, RANGE_INDEX)
    return handle, ps2000


def capture_block(handle, ps2000):
    """Capture a single 2048-sample block."""
    ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ct.c_int32()))
    time.sleep(0.05)
    for _ in range(200):
        if ps2000.ps2000_ready(handle):
            break
        time.sleep(0.02)
    else:
        raise TimeoutError("PicoScope capture timed out")

    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16(0)
    ps2000.ps2000_get_values(
        handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES, 0
    )
    mv = np.array(buf, dtype=np.float64) * (RANGE_MV / 32767.0)
    return mv


def set_awg(handle, ps2000, freq_hz: float):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0, 0, 0, 0
    )


def stop_awg(handle, ps2000):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0, 0, 0, 0
    )


# ---------------------------------------------------------------------------
# FFT analysis
# ---------------------------------------------------------------------------


def compute_complex_fft(mv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (magnitude, complex_values) of zero-padded FFT."""
    ac = mv - mv.mean()
    window = np.hanning(len(ac))
    nfft = len(ac) * N_FFT_PAD
    fft_complex = np.fft.rfft(ac * window, n=nfft)
    fft_mag = np.abs(fft_complex)
    return fft_mag, fft_complex


def freq_to_bin(freq_hz: float) -> int:
    """Convert frequency to FFT bin (with zero-padding)."""
    nfft = N_SAMPLES * N_FFT_PAD
    bin_hz = SAMPLE_RATE_HZ / nfft
    return int(round(freq_hz / bin_hz))


def extract_bin_features(fft_mag: np.ndarray, fft_complex: np.ndarray,
                          freq_hz: float) -> dict:
    """Extract magnitude, phase, and ±3 bin peak at a target frequency."""
    target_bin = freq_to_bin(freq_hz)
    lo = max(0, target_bin - 3)
    hi = min(len(fft_mag) - 1, target_bin + 3)

    peak_mag = float(fft_mag[lo:hi + 1].max())
    peak_bin = lo + int(fft_mag[lo:hi + 1].argmax())
    phase = float(np.angle(fft_complex[peak_bin]))
    center_mag = float(fft_mag[target_bin])

    return {
        "magnitude": peak_mag,
        "center_magnitude": center_mag,
        "phase_rad": phase,
        "peak_bin": int(peak_bin),
    }


def check_sum_diff_products(fft_mag: np.ndarray, f_prime: float, f_probe: float,
                             noise_floor_mag: float) -> dict:
    """Check for intermodulation products at f1±f2, 2f1±f2, etc."""
    products = {}
    combos = [
        ("f1+f2", f_prime + f_probe),
        ("f1-f2", abs(f_prime - f_probe)),
        ("2f1-f2", abs(2 * f_prime - f_probe)),
        ("2f2-f1", abs(2 * f_probe - f_prime)),
    ]
    nfft = N_SAMPLES * N_FFT_PAD
    max_freq = SAMPLE_RATE_HZ / 2

    for label, freq in combos:
        if freq <= 0 or freq >= max_freq:
            continue
        target_bin = freq_to_bin(freq)
        lo = max(0, target_bin - 3)
        hi = min(len(fft_mag) - 1, target_bin + 3)
        peak = float(fft_mag[lo:hi + 1].max())
        snr = peak / noise_floor_mag if noise_floor_mag > 0 else 0
        products[label] = {"freq_hz": freq, "magnitude": peak, "snr": snr}

    return products


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------


def run_temporal_memory_fft(pairs: list[tuple[float, float]], gaps_ms: list[float],
                             n_avg: int, relay_ch: int):
    """Run improved cross-mode temporal memory experiment."""
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(relay_ch)
    time.sleep(0.2)

    print(f"\n{'='*70}")
    print(f"T2.3b — Ring-down Temporal Memory (FFT-Based, Phase-Sensitive)")
    print(f"{'='*70}")
    print(f"Pairs: {[(f'{f1/1000:.1f}k→{f2/1000:.1f}k') for f1,f2 in pairs]}")
    print(f"T_write: {T_WRITE_MS} ms, T_probe: {T_PROBE_MS} ms")
    print(f"Gaps: {gaps_ms} ms")
    print(f"Averages: {n_avg}")
    print(f"FFT: {N_SAMPLES}×{N_FFT_PAD} zero-pad, bin = "
          f"{SAMPLE_RATE_HZ / (N_SAMPLES * N_FFT_PAD):.2f} Hz")
    print(f"{'='*70}\n")

    # Baseline noise floor (AWG off)
    print("  Measuring noise floor...", end=" ", flush=True)
    stop_awg(handle, ps2000)
    time.sleep(0.3)
    noise_mags = []
    for _ in range(10):
        mv = capture_block(handle, ps2000)
        fft_mag, _ = compute_complex_fft(mv)
        noise_mags.append(fft_mag)
    noise_floor = np.mean(noise_mags, axis=0)
    noise_median = float(np.median(noise_floor[10:]))  # skip DC region
    print(f"median = {noise_median:.1f}")

    all_results = []
    max_sigma_amp = 0.0
    max_sigma_phase = 0.0
    max_contrast = 0.0

    for pair_idx, (f_prime, f_probe) in enumerate(pairs):
        print(f"\n  {'─'*66}")
        print(f"  Pair {pair_idx+1}: prime {f_prime/1000:.1f}k → probe {f_probe/1000:.1f}k")
        print(f"  {'─'*66}")

        # Header
        print(f"    {'Gap':>5s}  {'Δmag%':>7s} {'σ_amp':>6s}  "
              f"{'Δphase°':>8s} {'σ_φ':>6s}  "
              f"{'f1_resid':>9s}  {'IM_best':>8s}")
        print(f"    {'─'*5}  {'─'*7} {'─'*6}  {'─'*8} {'─'*6}  {'─'*9}  {'─'*8}")

        pair_results = {"f_prime_hz": f_prime, "f_probe_hz": f_probe, "gaps": []}

        for gap_ms in gaps_ms:
            # CONDITION A: Primed
            primed_probe_mags = []
            primed_probe_phases = []
            primed_prime_residuals = []
            primed_im_products = []

            for _ in range(n_avg):
                stop_awg(handle, ps2000)
                time.sleep(0.05)

                # Prime: drive f1
                set_awg(handle, ps2000, f_prime)
                time.sleep(T_WRITE_MS / 1000.0)

                # Gap: silence while f1 decays
                stop_awg(handle, ps2000)
                time.sleep(gap_ms / 1000.0)

                # Probe: drive f2 briefly
                set_awg(handle, ps2000, f_probe)
                time.sleep(T_PROBE_MS / 1000.0)

                # Capture and analyze
                mv = capture_block(handle, ps2000)
                fft_mag, fft_complex = compute_complex_fft(mv)

                # Extract f_probe features
                probe_feat = extract_bin_features(fft_mag, fft_complex, f_probe)
                primed_probe_mags.append(probe_feat["magnitude"])
                primed_probe_phases.append(probe_feat["phase_rad"])

                # Extract f_prime residual
                prime_feat = extract_bin_features(fft_mag, fft_complex, f_prime)
                primed_prime_residuals.append(prime_feat["magnitude"])

                # Check IM products
                im = check_sum_diff_products(fft_mag, f_prime, f_probe, noise_median)
                primed_im_products.append(im)

                stop_awg(handle, ps2000)
                time.sleep(0.02)

            # CONDITION B: Unprimed
            unprimed_probe_mags = []
            unprimed_probe_phases = []
            unprimed_prime_residuals = []
            unprimed_im_products = []

            for _ in range(n_avg):
                stop_awg(handle, ps2000)
                time.sleep(0.05)

                # No prime — equivalent silence
                time.sleep((T_WRITE_MS + gap_ms) / 1000.0)

                # Probe: same
                set_awg(handle, ps2000, f_probe)
                time.sleep(T_PROBE_MS / 1000.0)

                mv = capture_block(handle, ps2000)
                fft_mag, fft_complex = compute_complex_fft(mv)

                probe_feat = extract_bin_features(fft_mag, fft_complex, f_probe)
                unprimed_probe_mags.append(probe_feat["magnitude"])
                unprimed_probe_phases.append(probe_feat["phase_rad"])

                prime_feat = extract_bin_features(fft_mag, fft_complex, f_prime)
                unprimed_prime_residuals.append(prime_feat["magnitude"])

                im = check_sum_diff_products(fft_mag, f_prime, f_probe, noise_median)
                unprimed_im_products.append(im)

                stop_awg(handle, ps2000)
                time.sleep(0.02)

            # --- Analysis ---
            p_mag = np.array(primed_probe_mags)
            u_mag = np.array(unprimed_probe_mags)
            p_phase = np.array(primed_probe_phases)
            u_phase = np.array(unprimed_probe_phases)

            # Amplitude comparison
            mag_contrast = (p_mag.mean() - u_mag.mean()) / u_mag.mean() * 100
            pooled_std_mag = np.sqrt((p_mag.std()**2 + u_mag.std()**2) / 2)
            sigma_amp = ((p_mag.mean() - u_mag.mean()) / pooled_std_mag
                         if pooled_std_mag > 0 else 0.0)

            # Phase comparison (circular mean difference)
            phase_diff = np.angle(np.exp(1j * (p_phase - u_phase.mean())))
            mean_phase_shift_deg = float(np.mean(phase_diff)) * 180 / np.pi
            pooled_std_phase = np.sqrt((np.std(p_phase)**2 + np.std(u_phase)**2) / 2)
            sigma_phase = (abs(np.mean(p_phase) - np.mean(u_phase)) / pooled_std_phase
                           if pooled_std_phase > 0 else 0.0)

            # f_prime residual
            prime_resid_mean = float(np.mean(primed_prime_residuals))
            prime_resid_snr = prime_resid_mean / noise_median if noise_median > 0 else 0

            # Best IM product SNR across all primed captures
            best_im_snr = 0.0
            best_im_label = ""
            for im_dict in primed_im_products:
                for label, data in im_dict.items():
                    if data["snr"] > best_im_snr:
                        best_im_snr = data["snr"]
                        best_im_label = label

            # Track maximums
            max_sigma_amp = max(max_sigma_amp, abs(sigma_amp))
            max_sigma_phase = max(max_sigma_phase, abs(sigma_phase))
            max_contrast = max(max_contrast, abs(mag_contrast))

            print(f"    {gap_ms:>5.1f}  {mag_contrast:>+6.2f}% {sigma_amp:>+5.2f}σ  "
                  f"{mean_phase_shift_deg:>+7.2f}° {sigma_phase:>5.2f}σ  "
                  f"{prime_resid_snr:>8.1f}×  "
                  f"{best_im_snr:>5.1f}× {best_im_label}")

            gap_result = {
                "gap_ms": gap_ms,
                "primed_mag_mean": float(p_mag.mean()),
                "primed_mag_std": float(p_mag.std()),
                "unprimed_mag_mean": float(u_mag.mean()),
                "unprimed_mag_std": float(u_mag.std()),
                "mag_contrast_pct": float(mag_contrast),
                "sigma_amplitude": float(sigma_amp),
                "primed_phase_mean_rad": float(p_phase.mean()),
                "unprimed_phase_mean_rad": float(u_phase.mean()),
                "phase_shift_deg": float(mean_phase_shift_deg),
                "sigma_phase": float(sigma_phase),
                "prime_residual_snr": float(prime_resid_snr),
                "best_im_product": best_im_label,
                "best_im_snr": float(best_im_snr),
            }
            pair_results["gaps"].append(gap_result)

        all_results.append(pair_results)

    # Cleanup
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # --- Summary ---
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Max |amplitude σ|: {max_sigma_amp:.2f}σ")
    print(f"  Max |phase σ|:     {max_sigma_phase:.2f}σ")
    print(f"  Max |contrast|:    {max_contrast:.2f}%")

    # Gate decision
    if max_sigma_amp >= 2.0 or max_sigma_phase >= 2.0:
        gate = "PASS"
        print(f"\n  ★ GATE DECISION: PASS (σ ≥ 2 detected)")
    elif max_sigma_amp >= 1.5 or max_sigma_phase >= 1.5:
        gate = "MARGINAL"
        print(f"\n  ◆ GATE DECISION: MARGINAL (1.5 ≤ σ < 2)")
    else:
        gate = "FAIL"
        print(f"\n  ✗ GATE DECISION: FAIL (max σ < 1.5 — no cross-mode coupling)")

    if max_contrast < 1.0 and max_sigma_amp < 1.5:
        print("    Plate modes confirmed fully independent (linear, orthogonal)")

    # Save
    out_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "temporal_memory"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"t2_3b_temporal_fft_{ts}.json"

    result_doc = {
        "experiment": "T2.3b_temporal_memory_fft",
        "timestamp": datetime.now().isoformat(),
        "plate": "100x100mm_fused_silica",
        "relay_channel": relay_ch,
        "n_averages": n_avg,
        "t_write_ms": T_WRITE_MS,
        "t_probe_ms": T_PROBE_MS,
        "gaps_ms": gaps_ms,
        "noise_floor_median": float(noise_median),
        "max_sigma_amplitude": float(max_sigma_amp),
        "max_sigma_phase": float(max_sigma_phase),
        "max_contrast_pct": float(max_contrast),
        "gate_decision": gate,
        "pairs": all_results,
    }

    with open(out_path, "w") as fp:
        json.dump(result_doc, fp, indent=2)
    print(f"\n  Results saved: {out_path}")

    return gate


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="T2.3b Temporal Memory (FFT-based, phase-sensitive)")
    parser.add_argument("--averages", type=int, default=N_AVG_DEFAULT,
                        help="Averages per condition")
    parser.add_argument("--relay", type=int, default=RELAY_CH,
                        help="Relay channel")
    parser.add_argument("--gaps", type=float, nargs="+", default=DEFAULT_GAPS_MS,
                        help="Gap times in ms")
    args = parser.parse_args()

    run_temporal_memory_fft(
        pairs=DEFAULT_PAIRS,
        gaps_ms=args.gaps,
        n_avg=args.averages,
        relay_ch=args.relay,
    )


if __name__ == "__main__":
    main()
