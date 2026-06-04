#!/usr/bin/env python3
"""
T3.2 — Phase-Spectral Encoding

Tests whether the plate's eigenmode phases are stable and deterministic,
which would enable using phase as an additional encoding axis (doubling
information capacity beyond amplitude-only).

Concept:
  CWM modes carry both amplitude |H(f)| and phase arg(H(f)). If the system
  transfer function phase is repeatable, phase becomes a second independent
  encoding channel. This experiment measures phase stability by:
    1. Driving each confirmed mode at its resonant frequency
    2. Triggering the capture on the received signal (Ch A rising edge)
    3. Measuring FFT phase at the mode frequency across N captures
    4. Computing σ_phase for each mode

  Trigger synchronization is critical: without it, the capture start time is
  random relative to the AWG cycle, adding uniform phase noise.

Success Metric:
  > 50% of modes (i.e., ≥3 of 4) have σ_phase < 0.5 rad across 100 trials.

Additional measurements:
  - Phase drift test: 100 captures over 30 seconds (temporal stability)
  - Cross-mode phase matrix: phase relationships between modes
  - Phase vs amplitude: verify linearity (phase independent of drive level)

Hardware:
  - PicoScope AWG (0.5 Vpp) → Board D (×3.69) → TX PZT (SW)
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V)
  - Trigger: Ch A rising edge at 0 mV threshold

Modes:
  35,840 / 54,920 / 57,037 / 97,011 Hz

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t3_2_phase_spectral.py
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
SETTLE_S = 0.50             # longer settle for phase stability
N_TRIALS = 100              # captures per mode

MODES_HZ = [35_840, 54_920, 57_037, 97_011]

# Trigger: Ch A, rising edge, threshold in ADC counts
# For ±5V range: 1 ADC count = 5000/32767 ≈ 0.153 mV
# Use 0 threshold (zero crossing) for consistent trigger point
TRIGGER_SOURCE = 0    # Ch A
TRIGGER_THRESH = 0    # 0 mV (zero crossing)
TRIGGER_DIR = 0       # rising
TRIGGER_DELAY = 0
TRIGGER_AUTO_MS = 2000  # 2s auto-trigger fallback

os.environ['DYLD_LIBRARY_PATH'] = (
    '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relay_mux import RelayMux  # noqa: E402

# ---------------------------------------------------------------------------
# Hardware helpers
# ---------------------------------------------------------------------------


def open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle})")
    # AC coupling (dc=0) removes ~3V DC offset from Board A,
    # centering signal at 0 so trigger threshold 0 works correctly
    ps2000.ps2000_set_channel(handle, 0, 1, 0, RANGE_INDEX)
    return handle, ps2000


def capture_triggered(handle, ps2000):
    """Capture 2048 samples with Ch A trigger (phase-locked to signal)."""
    ps2000.ps2000_set_trigger(
        handle, TRIGGER_SOURCE, TRIGGER_THRESH, TRIGGER_DIR,
        TRIGGER_DELAY, TRIGGER_AUTO_MS
    )
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ct.c_int32()))
    time.sleep(0.01)
    for _ in range(400):
        if ps2000.ps2000_ready(handle):
            break
        time.sleep(0.01)
    else:
        raise TimeoutError("PicoScope capture timed out (trigger not found?)")

    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16(0)
    ps2000.ps2000_get_values(
        handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES, 0
    )
    mv = np.array(buf, dtype=np.float64) * (RANGE_MV / 32767.0)
    return mv


def capture_free(handle, ps2000):
    """Capture without trigger (for comparison)."""
    ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ct.c_int32()))
    time.sleep(0.05)
    for _ in range(200):
        if ps2000.ps2000_ready(handle):
            break
        time.sleep(0.02)
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16(0)
    ps2000.ps2000_get_values(
        handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES, 0
    )
    mv = np.array(buf, dtype=np.float64) * (RANGE_MV / 32767.0)
    return mv


def set_awg(handle, ps2000, freq_hz: float, uvpp: int = AWG_DRIVE_UVPP):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, uvpp, 0,
        float(freq_hz), float(freq_hz), 0, 0, 0, 0
    )


def stop_awg(handle, ps2000):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0, 0, 0, 0
    )


# ---------------------------------------------------------------------------
# FFT phase measurement
# ---------------------------------------------------------------------------


def measure_phase_at_freq(mv: np.ndarray, target_hz: float) -> tuple[float, float]:
    """Measure FFT phase and magnitude at target frequency.

    Returns (phase_rad, magnitude).
    Phase is in [-π, π].
    """
    ac = mv - mv.mean()
    window = np.hanning(len(ac))
    nfft = len(ac) * N_FFT_PAD
    fft_complex = np.fft.rfft(ac * window, n=nfft)
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE_HZ)

    # Find bin closest to target
    bin_idx = int(round(target_hz / (SAMPLE_RATE_HZ / nfft)))
    # Search ±3 bins for peak magnitude (in case of slight freq mismatch)
    lo = max(0, bin_idx - 3)
    hi = min(len(fft_complex) - 1, bin_idx + 3)
    search = np.abs(fft_complex[lo:hi + 1])
    peak_offset = np.argmax(search)
    peak_bin = lo + peak_offset

    phase = float(np.angle(fft_complex[peak_bin]))
    magnitude = float(np.abs(fft_complex[peak_bin]))

    return phase, magnitude


def circular_std(phases: np.ndarray) -> float:
    """Compute circular standard deviation (in radians).

    Uses the formula: σ_circ = sqrt(-2 * ln(R))
    where R = |mean of unit vectors|.
    """
    unit_vectors = np.exp(1j * phases)
    R = np.abs(np.mean(unit_vectors))
    if R >= 1.0:
        return 0.0
    if R < 1e-10:
        return np.pi  # uniform distribution
    return float(np.sqrt(-2.0 * np.log(R)))


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------


def run_phase_spectral(modes: list[int], n_trials: int, relay_ch: int):
    """Run the phase-spectral encoding experiment."""
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(relay_ch)
    time.sleep(0.2)

    bin_hz = SAMPLE_RATE_HZ / (N_SAMPLES * N_FFT_PAD)

    print(f"\n{'='*70}")
    print("T3.2 — Phase-Spectral Encoding")
    print(f"{'='*70}")
    print(f"  Modes: {modes} Hz")
    print(f"  Trials: {n_trials}")
    print(f"  Trigger: Ch A rising edge @ 0 mV")
    print(f"  FFT bin: {bin_hz:.2f} Hz (4× zero-pad)")
    print(f"  Pass criterion: >50% modes with σ_phase < 0.5 rad")
    print(f"{'='*70}")

    all_results = []

    # ─────────────────────────────────────────────────────────────
    # Part 1: Phase stability per mode (triggered captures)
    # ─────────────────────────────────────────────────────────────
    print(f"\n  Part 1: Phase stability (triggered, {n_trials} trials/mode)")
    print(f"  {'Mode Hz':>10s}  {'σ_phase':>8s}  {'mean φ':>8s}  {'SNR':>6s}  {'Status':>8s}")
    print(f"  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*6}  {'─'*8}")

    mode_results = []
    for freq in modes:
        set_awg(handle, ps2000, freq)
        time.sleep(SETTLE_S)

        phases = []
        magnitudes = []
        for _ in range(n_trials):
            mv = capture_triggered(handle, ps2000)
            phase, mag = measure_phase_at_freq(mv, freq)
            phases.append(phase)
            magnitudes.append(mag)

        phases = np.array(phases)
        magnitudes = np.array(magnitudes)

        sigma_phase = circular_std(phases)
        mean_phase = float(np.angle(np.mean(np.exp(1j * phases))))
        mean_mag = float(np.mean(magnitudes))
        snr = mean_mag / np.median(magnitudes) if np.median(magnitudes) > 0 else 0

        passed = sigma_phase < 0.5
        status = "PASS" if passed else "FAIL"

        print(f"  {freq:>10d}  {sigma_phase:>8.4f}  {mean_phase:>+8.3f}  "
              f"{mean_mag:>6.0f}  {status:>8s}")

        mode_results.append({
            "freq_hz": freq,
            "sigma_phase_rad": sigma_phase,
            "mean_phase_rad": mean_phase,
            "mean_magnitude": mean_mag,
            "phase_stable": passed,
            "all_phases": phases.tolist(),
            "all_magnitudes": magnitudes.tolist(),
        })

    n_stable = sum(1 for r in mode_results if r["phase_stable"])
    pct_stable = 100 * n_stable / len(modes)

    # ─────────────────────────────────────────────────────────────
    # Part 2: Free-running comparison (no trigger — shows trigger benefit)
    # ─────────────────────────────────────────────────────────────
    print(f"\n  Part 2: Free-running comparison (no trigger, 50 trials)")
    print(f"  {'Mode Hz':>10s}  {'σ_trig':>8s}  {'σ_free':>8s}  {'Improvement':>12s}")
    print(f"  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*12}")

    free_results = []
    for i, freq in enumerate(modes):
        set_awg(handle, ps2000, freq)
        time.sleep(SETTLE_S)

        phases_free = []
        for _ in range(50):
            mv = capture_free(handle, ps2000)
            phase, _ = measure_phase_at_freq(mv, freq)
            phases_free.append(phase)

        sigma_free = circular_std(np.array(phases_free))
        sigma_trig = mode_results[i]["sigma_phase_rad"]
        improvement = sigma_free / sigma_trig if sigma_trig > 0 else float('inf')

        print(f"  {freq:>10d}  {sigma_trig:>8.4f}  {sigma_free:>8.4f}  "
              f"{improvement:>10.1f}×")

        free_results.append({
            "freq_hz": freq,
            "sigma_free_rad": sigma_free,
            "sigma_triggered_rad": sigma_trig,
        })

    # ─────────────────────────────────────────────────────────────
    # Part 3: Phase drift over time (30 seconds, same mode)
    # ─────────────────────────────────────────────────────────────
    print(f"\n  Part 3: Temporal phase drift (35840 Hz over 30 seconds)")
    drift_freq = modes[0]
    set_awg(handle, ps2000, drift_freq)
    time.sleep(SETTLE_S)

    drift_phases = []
    drift_times = []
    t0 = time.time()
    for _ in range(100):
        mv = capture_triggered(handle, ps2000)
        phase, _ = measure_phase_at_freq(mv, drift_freq)
        drift_phases.append(phase)
        drift_times.append(time.time() - t0)
        time.sleep(0.25)  # ~25s total

    drift_phases = np.array(drift_phases)
    drift_times = np.array(drift_times)

    # Linear regression on unwrapped phase to detect drift rate
    unwrapped = np.unwrap(drift_phases)
    if len(unwrapped) > 1:
        coeffs = np.polyfit(drift_times, unwrapped, 1)
        drift_rate = coeffs[0]  # rad/sec
    else:
        drift_rate = 0.0

    sigma_drift = circular_std(drift_phases)
    print(f"  σ_phase over 30s: {sigma_drift:.4f} rad")
    print(f"  Drift rate: {drift_rate:.4f} rad/s ({np.degrees(drift_rate):.2f} °/s)")
    print(f"  Total drift: {abs(drift_rate * 30):.3f} rad over 30s")

    # ─────────────────────────────────────────────────────────────
    # Part 4: Cross-mode phase matrix
    # ─────────────────────────────────────────────────────────────
    print(f"\n  Part 4: Cross-mode phase relationships (unique phase per mode)")
    print(f"  {'Mode':>10s}  {'Phase':>8s}")
    print(f"  {'─'*10}  {'─'*8}")
    for r in mode_results:
        print(f"  {r['freq_hz']:>10d}  {r['mean_phase_rad']:>+8.3f} rad "
              f"({np.degrees(r['mean_phase_rad']):>+7.1f}°)")

    # Check if phases are distinguishable (pairwise separation > 2σ)
    phase_separable = True
    for i in range(len(mode_results)):
        for j in range(i + 1, len(mode_results)):
            diff = abs(mode_results[i]["mean_phase_rad"] - mode_results[j]["mean_phase_rad"])
            diff = min(diff, 2 * np.pi - diff)  # circular distance
            max_sigma = max(mode_results[i]["sigma_phase_rad"],
                           mode_results[j]["sigma_phase_rad"])
            if diff < 2 * max_sigma:
                phase_separable = False

    # Cleanup
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # ─────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Phase-stable modes (σ < 0.5 rad): {n_stable}/{len(modes)} ({pct_stable:.0f}%)")
    print(f"  Best σ_phase: {min(r['sigma_phase_rad'] for r in mode_results):.4f} rad")
    print(f"  Worst σ_phase: {max(r['sigma_phase_rad'] for r in mode_results):.4f} rad")
    print(f"  Phase drift (30s): {sigma_drift:.4f} rad")
    print(f"  Cross-mode phases distinguishable: {'YES' if phase_separable else 'NO'}")

    if pct_stable > 50:
        gate = "PASS"
        print(f"\n  ★ GATE DECISION: PASS — {n_stable}/{len(modes)} modes phase-stable")
        print(f"    Phase provides a viable second encoding axis.")
    else:
        gate = "FAIL"
        print(f"\n  ✗ GATE DECISION: FAIL — only {n_stable}/{len(modes)} modes phase-stable")
        print(f"    Phase too noisy for reliable encoding.")

    # Save results
    out_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "phase_spectral"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"t3_2_phase_spectral_{ts}.json"

    result_doc = {
        "experiment": "T3.2_phase_spectral_encoding",
        "timestamp": datetime.now().isoformat(),
        "plate": "100x100mm_fused_silica",
        "relay_channel": relay_ch,
        "n_trials": n_trials,
        "trigger": {"source": "ChA", "threshold_mV": 0, "direction": "rising"},
        "awg_uvpp": AWG_DRIVE_UVPP,
        "gate_decision": gate,
        "n_stable": n_stable,
        "pct_stable": pct_stable,
        "mode_results": mode_results,
        "free_running_comparison": free_results,
        "drift_test": {
            "freq_hz": drift_freq,
            "duration_s": float(drift_times[-1]),
            "sigma_phase_rad": sigma_drift,
            "drift_rate_rad_per_s": drift_rate,
            "phases": drift_phases.tolist(),
            "times": drift_times.tolist(),
        },
        "cross_mode_separable": phase_separable,
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
        description="T3.2 Phase-Spectral Encoding")
    parser.add_argument("--trials", type=int, default=N_TRIALS)
    parser.add_argument("--relay", type=int, default=RELAY_CH)
    args = parser.parse_args()

    run_phase_spectral(
        modes=MODES_HZ,
        n_trials=args.trials,
        relay_ch=args.relay,
    )


if __name__ == "__main__":
    main()
