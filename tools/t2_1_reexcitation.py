#!/usr/bin/env python3
"""
T2.1 — Re-excitation Interference (E33) on Fused Silica Plate

Tests whether a residual acoustic vibration (from a first excitation) can
interfere with a second excitation at the same frequency, producing
measurable amplitude contrast. This is the fundamental CWM write-read
interference phenomenon.

Protocol:
  1. Drive mode at frequency f for T_write ms (establish steady-state)
  2. Stop AWG (let plate ring down for T_gap ms)
  3. Re-excite at same frequency f for T_read ms
  4. Capture response amplitude during re-excitation
  5. Compare against baseline (fresh excitation with no prior write)
  6. Sweep T_gap from short (strong residual) to long (decayed away)
  7. Contrast = |A_reexcite - A_baseline| / A_baseline

The residual vibration has phase determined by the write burst. At short
gaps, the re-excitation adds coherently to the residual → constructive
interference → amplitude INCREASE vs baseline. At T_gap ≈ τ, residual
has decayed and contrast → 0.

Success criterion: contrast > 2% at any gap time
Kill criterion: no measurable contrast at any gap → no memory effect

Physics:
  - Q = 2759, f = 35,840 Hz → τ = Q/(π·f) ≈ 24.5 ms
  - At T_gap = 5 ms: residual ≈ 80% of steady-state
  - At T_gap = 10 ms: residual ≈ 66%
  - At T_gap = 25 ms: residual ≈ 36%
  - At T_gap = 50 ms: residual ≈ 13%

Hardware:
  - PicoScope AWG → Board D (3.69×) → TX PZT (SW) → Plate
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V)
  - 2048 samples, timebase 7 → 781,250 Hz → 2.6 ms capture window

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t2_1_reexcitation.py

  # Use 57 kHz mode (cleanest acoustic):
  python tools/t2_1_reexcitation.py --freq 57037

  # Custom gap sweep:
  python tools/t2_1_reexcitation.py --gaps 2 5 10 20 40

  # More averages (slower but more precise):
  python tools/t2_1_reexcitation.py --averages 20
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

AWG_DRIVE_UVPP = 500_000   # 0.5 Vpp

# Default mode: 35,840 Hz (Q=2759, τ≈24.5 ms)
DEFAULT_FREQ_HZ = 35_840.0

# Timing (ms)
T_WRITE_MS = 100       # long enough to reach steady-state (≈4τ → fully rung up)
T_READ_MS = 5          # brief re-excitation burst
DEFAULT_GAPS_MS = [2, 5, 10, 15, 20, 30, 50, 80]  # sweep from short to long

N_AVG_DEFAULT = 10     # averages per measurement point
N_BASELINE = 10        # fresh excitation measurements for baseline

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
    """Turn on AWG at given frequency."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz),
        0, 0, 0, 0
    )


def stop_awg(handle, ps2000):
    """Turn off AWG (set amplitude to 0)."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0, 0, 0, 0
    )


def measure_amplitude(handle, ps2000) -> float:
    """Capture one block and return peak-to-peak amplitude in mV."""
    mv = capture_block(handle, ps2000)
    ac = mv - mv.mean()
    return float(ac.max() - ac.min())


def measure_amplitude_avg(handle, ps2000, n_avg: int) -> tuple[float, float]:
    """Return (mean_pp, std_pp) over n_avg captures."""
    vals = []
    for _ in range(n_avg):
        vals.append(measure_amplitude(handle, ps2000))
        time.sleep(0.01)
    return float(np.mean(vals)), float(np.std(vals))


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------

def run_reexcitation(freq_hz: float, gaps_ms: list[float], n_avg: int,
                     relay_ch: int):
    """Run the re-excitation interference experiment."""
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(relay_ch)
    time.sleep(0.2)

    print(f"\n{'='*60}")
    print(f"T2.1 — Re-excitation Interference (E33)")
    print(f"{'='*60}")
    print(f"Frequency: {freq_hz:,.0f} Hz")
    print(f"T_write: {T_WRITE_MS} ms, T_read: {T_READ_MS} ms")
    print(f"Gaps (ms): {gaps_ms}")
    print(f"Averages per point: {n_avg}")
    print(f"Relay: {relay_ch}")
    print(f"{'='*60}\n")

    # --- Step 1: Measure baseline (fresh excitation, no prior write) ---
    print("  Measuring baseline (fresh excitation, no residual)...")
    # Let plate be silent for 500 ms (well beyond τ=24ms), then excite and measure
    stop_awg(handle, ps2000)
    time.sleep(0.5)

    baseline_vals = []
    for _ in range(N_BASELINE):
        # Fresh excite for T_READ_MS
        set_awg(handle, ps2000, freq_hz)
        time.sleep(T_READ_MS / 1000.0)
        amp = measure_amplitude(handle, ps2000)
        baseline_vals.append(amp)
        # Full silence between baselines (let all residual decay)
        stop_awg(handle, ps2000)
        time.sleep(0.5)

    baseline_mean = float(np.mean(baseline_vals))
    baseline_std = float(np.std(baseline_vals))
    print(f"  Baseline: {baseline_mean:.1f} ± {baseline_std:.1f} mV pp "
          f"(after {T_READ_MS} ms fresh drive)\n")

    # --- Step 2: For each gap, do write → gap → re-excite → measure ---
    results = []
    print(f"  {'Gap (ms)':<10} {'Re-excite (mV)':<16} {'Contrast (%)':<14} {'σ from BL':<10}")
    print(f"  {'-'*10} {'-'*16} {'-'*14} {'-'*10}")

    for gap_ms in gaps_ms:
        reexcite_vals = []
        for _ in range(n_avg):
            # Write phase: drive to steady-state
            set_awg(handle, ps2000, freq_hz)
            time.sleep(T_WRITE_MS / 1000.0)

            # Gap phase: stop drive, let residual ring
            stop_awg(handle, ps2000)
            time.sleep(gap_ms / 1000.0)

            # Read phase: re-excite and immediately capture
            set_awg(handle, ps2000, freq_hz)
            time.sleep(T_READ_MS / 1000.0)
            amp = measure_amplitude(handle, ps2000)
            reexcite_vals.append(amp)

            # Cool down (full decay before next trial)
            stop_awg(handle, ps2000)
            time.sleep(0.3)

        reex_mean = float(np.mean(reexcite_vals))
        reex_std = float(np.std(reexcite_vals))
        contrast_pct = (reex_mean - baseline_mean) / baseline_mean * 100.0
        sigma_from_bl = (reex_mean - baseline_mean) / baseline_std if baseline_std > 0 else 0

        results.append({
            "gap_ms": gap_ms,
            "reexcite_mean_mv": reex_mean,
            "reexcite_std_mv": reex_std,
            "contrast_pct": contrast_pct,
            "sigma_from_baseline": sigma_from_bl,
        })

        status = "✓" if abs(contrast_pct) > 2.0 else "—"
        print(f"  {gap_ms:<10.0f} {reex_mean:<7.1f} ± {reex_std:<5.1f}  "
              f"{contrast_pct:<+14.1f} {sigma_from_bl:<+10.1f} {status}")

    # Cleanup
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # --- Summary ---
    max_contrast = max(abs(r["contrast_pct"]) for r in results)
    max_sigma = max(abs(r["sigma_from_baseline"]) for r in results)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Baseline amplitude: {baseline_mean:.1f} ± {baseline_std:.1f} mV pp")
    print(f"  Max |contrast|: {max_contrast:.1f}%")
    print(f"  Max |σ from baseline|: {max_sigma:.1f}σ")

    # Expected decay profile
    # τ = Q / (π * f)
    tau_ms = 2759 / (np.pi * freq_hz) * 1000
    print(f"  Expected τ: {tau_ms:.1f} ms (Q=2759)")
    print(f"  Expected residual at each gap:")
    for gap_ms in gaps_ms:
        residual_frac = np.exp(-gap_ms / tau_ms)
        print(f"    {gap_ms:>5.0f} ms: {residual_frac*100:.1f}% residual")

    # Gate decision
    if max_contrast > 2.0:
        gate = "PASS"
        print(f"\n  *** GATE DECISION: PASS (max contrast {max_contrast:.1f}% > 2%) ***")
    else:
        gate = "FAIL"
        print(f"\n  *** GATE DECISION: FAIL (max contrast {max_contrast:.1f}% < 2%) ***")
        if max_sigma > 2.0:
            print(f"  NOTE: {max_sigma:.1f}σ separation detected — may be real but below 2% threshold")

    # Save results
    out_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "reexcitation"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"t2_1_reexcite_{ts}.json"

    output = {
        "experiment": "T2.1_reexcitation_interference",
        "timestamp": datetime.now().isoformat(),
        "plate": "100x100mm_fused_silica",
        "relay_channel": relay_ch,
        "frequency_hz": freq_hz,
        "t_write_ms": T_WRITE_MS,
        "t_read_ms": T_READ_MS,
        "awg_amplitude_uvpp": AWG_DRIVE_UVPP,
        "n_avg": n_avg,
        "baseline": {
            "mean_mv": baseline_mean,
            "std_mv": baseline_std,
            "n_samples": N_BASELINE,
        },
        "gap_sweep": results,
        "max_contrast_pct": max_contrast,
        "max_sigma_from_baseline": max_sigma,
        "expected_tau_ms": tau_ms,
        "gate_decision": gate,
    }

    with open(out_path, "w") as fp:
        json.dump(output, fp, indent=2)
    print(f"\n  Results saved: {out_path}")

    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="T2.1 — Re-excitation Interference")
    parser.add_argument("--freq", type=float, default=DEFAULT_FREQ_HZ,
                        help=f"Drive frequency in Hz (default: {DEFAULT_FREQ_HZ})")
    parser.add_argument("--gaps", type=float, nargs="+", default=None,
                        help=f"Gap times in ms (default: {DEFAULT_GAPS_MS})")
    parser.add_argument("--averages", type=int, default=N_AVG_DEFAULT,
                        help=f"Averages per gap point (default: {N_AVG_DEFAULT})")
    parser.add_argument("--relay-ch", type=int, default=RELAY_CH,
                        help=f"Relay channel (default: {RELAY_CH})")
    args = parser.parse_args()

    gaps = args.gaps if args.gaps else DEFAULT_GAPS_MS
    run_reexcitation(
        freq_hz=args.freq,
        gaps_ms=gaps,
        n_avg=args.averages,
        relay_ch=args.relay_ch,
    )


if __name__ == "__main__":
    main()
