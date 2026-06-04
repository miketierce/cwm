#!/usr/bin/env python3
"""
T1.3 — Single-Capture Eigenmode Discrimination (Fused Silica Plate)

Tests whether a single 2048-sample capture can identify which eigenmode
is being driven, by computing the FFT and checking if the correct bin
dominates. This is the fundamental CWM readout primitive: write a mode,
capture once, read back which mode was written.

Protocol:
  1. For each confirmed acoustic mode (from T1.2):
     a. Drive that frequency CW via AWG → Board D → TX PZT
     b. Wait for steady-state (200 ms settle)
     c. Capture single block (2048 samples, timebase 7 = 781.25 kHz)
     d. Compute FFT magnitude spectrum
     e. Find peak bin; check if it matches the driven frequency
  2. Repeat N trials per frequency for statistics
  3. Compute per-mode classification accuracy and per-bin SNR
  4. Report discrimination matrix (confusion-style)

Success criterion: per-bin SNR > 1σ (peak bin amplitude > mean + 1 stddev)
Kill criterion: per-bin SNR < 1σ → need more gain or longer capture

Confirmed acoustic modes (from T1.2 relay ON/OFF test):
  35,840 Hz  (T1.1 validated, Q≈2759)
  54,920 Hz  (ratio 2.70)
  55,543 Hz  (ratio 2.40)
  57,037 Hz  (ratio 5.00, cleanest)
  97,011 Hz  (ratio 2.57)

Hardware:
  - PicoScope AWG → Board D (3.69×) → TX PZT (SW) → Plate
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V)
  - 2048 samples, timebase 7 → 781,250 Hz sample rate
  - FFT bin width: 781250 / 2048 = 381.5 Hz

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t1_3_eigenmode_discrim.py

  # Fewer trials (quick check):
  python tools/t1_3_eigenmode_discrim.py --trials 5

  # Custom mode list:
  python tools/t1_3_eigenmode_discrim.py --freqs 35840 57037 97011
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

SAMPLE_RATE_HZ = 781_250          # timebase 7 = 1280 ns/sample
N_SAMPLES = 2048
TIMEBASE = 7
FFT_BIN_HZ = SAMPLE_RATE_HZ / N_SAMPLES  # ~381.5 Hz

# Confirmed acoustic modes from T1.2
DEFAULT_MODES_HZ = [35_840, 54_920, 55_543, 57_037, 97_011]

AWG_DRIVE_UVPP = 500_000          # 0.5 Vpp (same as T1.2)
SETTLE_S = 0.2                     # time to reach steady-state
RELAY_CH = 8                       # NE sensor (best coupling)
RANGE_INDEX = 8                    # ±5V
RANGE_MV = 5000.0
N_TRIALS_DEFAULT = 20              # captures per mode

# ---------------------------------------------------------------------------
# PicoScope helpers
# ---------------------------------------------------------------------------

os.environ['DYLD_LIBRARY_PATH'] = (
    '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relay_mux import RelayMux  # noqa: E402


def open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, 1, 1, RANGE_INDEX)
    return handle, ps2000


def capture_block(handle, ps2000):
    """Capture a single 2048-sample block with auto-trigger."""
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
    """Set AWG to CW sine at given frequency."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz),
        0, 0, 0, 0
    )


def stop_awg(handle, ps2000):
    """Turn off AWG."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0, 0, 0, 0
    )


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def compute_fft_magnitude(mv: np.ndarray) -> np.ndarray:
    """Return single-sided FFT magnitude in mV (DC bin excluded)."""
    ac = mv - mv.mean()
    window = np.hanning(len(ac))
    fft_vals = np.fft.rfft(ac * window)
    mag = np.abs(fft_vals) * 2.0 / N_SAMPLES  # normalize
    return mag


def freq_to_bin(freq_hz: float) -> int:
    """Convert frequency to nearest FFT bin index."""
    return int(round(freq_hz / FFT_BIN_HZ))


def bin_to_freq(bin_idx: int) -> float:
    """Convert FFT bin index to frequency."""
    return bin_idx * FFT_BIN_HZ


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run_discrimination(modes_hz: list[float], n_trials: int, relay_ch: int):
    """Run the eigenmode discrimination experiment."""
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(relay_ch)
    time.sleep(0.2)

    # Map each mode to its expected FFT bin
    mode_bins = {f: freq_to_bin(f) for f in modes_hz}
    n_modes = len(modes_hz)

    print(f"\n{'='*60}")
    print(f"T1.3 — Single-Capture Eigenmode Discrimination")
    print(f"{'='*60}")
    print(f"Modes: {modes_hz}")
    print(f"FFT bin width: {FFT_BIN_HZ:.1f} Hz")
    print(f"Expected bins: {mode_bins}")
    print(f"Trials per mode: {n_trials}")
    print(f"Relay: {relay_ch}")
    print(f"{'='*60}\n")

    # Results storage
    # confusion[i][j] = how many times mode i was classified as mode j
    confusion = np.zeros((n_modes, n_modes), dtype=int)
    snr_values = {f: [] for f in modes_hz}
    all_spectra = {f: [] for f in modes_hz}

    for i, drive_freq in enumerate(modes_hz):
        print(f"  Driving {drive_freq:,.0f} Hz (bin {mode_bins[drive_freq]})...", end=" ", flush=True)
        set_awg(handle, ps2000, drive_freq)
        time.sleep(SETTLE_S)

        correct = 0
        for trial in range(n_trials):
            mv = capture_block(handle, ps2000)
            mag = compute_fft_magnitude(mv)

            # Find which mode bin has the highest magnitude
            # Search only within ±2 bins of each mode
            best_mode_idx = -1
            best_amplitude = 0.0
            for j, candidate_freq in enumerate(modes_hz):
                cbin = mode_bins[candidate_freq]
                # Look at ±2 bins around expected
                lo = max(1, cbin - 2)
                hi = min(len(mag) - 1, cbin + 2)
                local_max = float(mag[lo:hi+1].max())
                if local_max > best_amplitude:
                    best_amplitude = local_max
                    best_mode_idx = j

            confusion[i][best_mode_idx] += 1
            if best_mode_idx == i:
                correct += 1

            # Compute per-bin SNR for the driven mode
            driven_bin = mode_bins[drive_freq]
            lo = max(1, driven_bin - 2)
            hi = min(len(mag) - 1, driven_bin + 2)
            peak_val = float(mag[lo:hi+1].max())
            # Noise: all bins except ±5 around any mode
            noise_mask = np.ones(len(mag), dtype=bool)
            noise_mask[0] = False  # skip DC
            for f in modes_hz:
                cb = mode_bins[f]
                noise_mask[max(0, cb-5):min(len(mag), cb+6)] = False
            if noise_mask.sum() > 10:
                noise_mean = float(mag[noise_mask].mean())
                noise_std = float(mag[noise_mask].std())
            else:
                noise_mean = float(mag[1:].mean())
                noise_std = float(mag[1:].std())

            snr_sigma = (peak_val - noise_mean) / noise_std if noise_std > 0 else 0.0
            snr_values[drive_freq].append(snr_sigma)

            if trial == 0:
                all_spectra[drive_freq] = mag.tolist()

        accuracy = correct / n_trials * 100
        mean_snr = float(np.mean(snr_values[drive_freq]))
        print(f"{correct}/{n_trials} correct ({accuracy:.0f}%), mean SNR = {mean_snr:.1f}σ")

    # Stop AWG
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # Report
    print(f"\n{'='*60}")
    print("CONFUSION MATRIX (rows=driven, cols=classified)")
    print(f"{'='*60}")
    header = "          " + "".join(f"{f/1000:>7.1f}k" for f in modes_hz)
    print(header)
    for i, f in enumerate(modes_hz):
        row = f"{f/1000:>7.1f}k  " + "".join(f"{confusion[i][j]:>8d}" for j in range(n_modes))
        print(row)

    # Overall metrics
    total_correct = int(np.trace(confusion))
    total_trials = n_modes * n_trials
    overall_acc = total_correct / total_trials * 100

    per_mode_snr = {f: float(np.mean(v)) for f, v in snr_values.items()}
    min_snr = min(per_mode_snr.values())

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Overall accuracy: {total_correct}/{total_trials} ({overall_acc:.1f}%)")
    print(f"  Per-mode SNR (σ):")
    for f in modes_hz:
        s = per_mode_snr[f]
        status = "✓" if s > 1.0 else "✗"
        print(f"    {f:>7,.0f} Hz: {s:>5.1f}σ  {status}")
    print(f"  Min per-bin SNR: {min_snr:.1f}σ")

    # Gate decision
    if min_snr >= 1.0:
        gate = "PASS"
        print(f"\n  *** GATE DECISION: PASS (min SNR {min_snr:.1f}σ ≥ 1σ) ***")
    else:
        gate = "FAIL"
        print(f"\n  *** GATE DECISION: FAIL (min SNR {min_snr:.1f}σ < 1σ — need more gain) ***")

    # Save results
    out_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "plate_discrim"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"t1_3_discrim_{ts}.json"

    result = {
        "experiment": "T1.3_eigenmode_discrimination",
        "timestamp": datetime.now().isoformat(),
        "plate": "100x100mm_fused_silica",
        "relay_channel": relay_ch,
        "modes_hz": modes_hz,
        "mode_bins": {str(f): b for f, b in mode_bins.items()},
        "fft_bin_hz": FFT_BIN_HZ,
        "n_trials": n_trials,
        "awg_amplitude_uvpp": AWG_DRIVE_UVPP,
        "settle_s": SETTLE_S,
        "confusion_matrix": confusion.tolist(),
        "overall_accuracy_pct": overall_acc,
        "per_mode_snr_sigma": per_mode_snr,
        "min_snr_sigma": min_snr,
        "gate_decision": gate,
        "sample_spectra": {str(f): s for f, s in all_spectra.items()},
    }

    with open(out_path, "w") as fp:
        json.dump(result, fp, indent=2)
    print(f"\n  Results saved: {out_path}")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="T1.3 — Eigenmode Discrimination")
    parser.add_argument("--freqs", type=float, nargs="+", default=None,
                        help="Mode frequencies in Hz (default: 5 confirmed acoustic)")
    parser.add_argument("--trials", type=int, default=N_TRIALS_DEFAULT,
                        help=f"Captures per mode (default: {N_TRIALS_DEFAULT})")
    parser.add_argument("--relay-ch", type=int, default=RELAY_CH,
                        help=f"Relay channel (default: {RELAY_CH})")
    args = parser.parse_args()

    modes = args.freqs if args.freqs else DEFAULT_MODES_HZ
    run_discrimination(modes_hz=modes, n_trials=args.trials, relay_ch=args.relay_ch)


if __name__ == "__main__":
    main()
