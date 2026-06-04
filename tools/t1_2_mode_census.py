#!/usr/bin/env python3
"""
T1.2 — Broadband Mode Census (Fused Silica Plate)

Maps all resolvable resonances of the 100×100 mm fused silica plate by
sweeping the AWG through Board D and measuring response amplitude at
each frequency via the RX PZT → Board A → PicoScope Ch A chain.

Protocol:
  1. Linear sweep from f_start to f_stop in n_steps
  2. At each frequency: drive CW, settle, capture, measure peak-to-peak
  3. Identify peaks (local maxima above noise threshold)
  4. Report mode count, frequencies, amplitudes, estimated SNR

Success criterion: ≥ 5 modes above 3σ noise floor
Kill criterion: < 5 modes → insufficient mode structure for CWM

Depends on: T1.1 pass (Q > 1000 confirmed at 35,840 Hz)

Hardware:
  - PicoScope AWG → Board D (3.69×) → TX PZT (SW) → Plate
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A
  - ±5V range (index 8)

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t1_2_mode_census.py

  # Custom range:
  python tools/t1_2_mode_census.py --start 1000 --stop 100000 --steps 500

  # Quick scan (fewer steps):
  python tools/t1_2_mode_census.py --steps 200

  # Use relay 7 (NW sensor):
  python tools/t1_2_mode_census.py --relay-ch 7
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault(
    "DYLD_LIBRARY_PATH",
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources",
)

from picosdk.ps2000 import ps2000

# ── Configuration ─────────────────────────────────────────────────────────

TIMEBASE = 7
SAMPLE_RATE = int(1e9 / 1280)  # 781250 Hz
N_SAMPLES = 2048

# AWG drive: moderate amplitude to avoid Board D clipping at resonances
AWG_DRIVE_UVPP = 500_000  # 0.5 Vpp from AWG → ~1.85 Vpp after Board D

# Ch A voltage range
CH_A_RANGE = 8  # ±5V

# Relay
RELAY_RX = 8  # NE sensor (best coupling, confirmed T1.1)

# Sweep defaults
F_START = 500       # Hz — below first expected plate mode
F_STOP = 100_000   # Hz — PicoScope AWG max ~100 kHz
N_STEPS = 400       # frequency steps (linear)
SETTLE_S = 0.08     # settle time per frequency step (80ms for narrowband modes)
N_AVG = 4           # captures to average per step


# ── Hardware helpers (same as T1.1) ───────────────────────────────────────

def open_scope() -> int:
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, 1, 1, CH_A_RANGE)
    print(f"  PicoScope opened (handle={handle})")
    return handle


def close_scope(handle: int):
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("  PicoScope closed")


def capture_block(handle: int) -> np.ndarray:
    """Capture 2048 samples and return mV array."""
    ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ct.c_int32()))
    time.sleep(0.1)
    for _ in range(100):
        if ps2000.ps2000_ready(handle):
            break
        time.sleep(0.05)
    else:
        return np.zeros(N_SAMPLES, dtype=np.float64)

    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16(0)
    ps2000.ps2000_get_values(
        handle, ct.byref(buf), None, None, None,
        ct.byref(ov), N_SAMPLES, 0
    )
    range_mv = {2: 50, 3: 100, 4: 200, 5: 500, 6: 1000, 7: 2000, 8: 5000}
    scale = range_mv.get(CH_A_RANGE, 5000)
    return np.array(buf, dtype=np.float64) * (scale / 32767.0)


def set_awg(handle: int, freq_hz: float, amplitude_uvpp: int = AWG_DRIVE_UVPP):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, amplitude_uvpp, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )


def measure_amplitude(handle: int, freq_hz: float) -> dict:
    """
    Drive at freq_hz, settle, capture N_AVG blocks, return amplitude stats.
    Returns dict with pp_mv, rms_mv, and the dominant FFT peak info.
    """
    set_awg(handle, freq_hz)
    time.sleep(SETTLE_S)

    pp_values = []
    rms_values = []
    for _ in range(N_AVG):
        data = capture_block(handle)
        # Remove DC
        ac = data - np.mean(data)
        pp_values.append(float(ac.max() - ac.min()))
        rms_values.append(float(np.std(ac)))

    return {
        "freq_hz": freq_hz,
        "pp_mv": np.mean(pp_values),
        "pp_std": np.std(pp_values),
        "rms_mv": np.mean(rms_values),
    }


# ── Peak detection ────────────────────────────────────────────────────────

def find_peaks(freqs: np.ndarray, amplitudes: np.ndarray, noise_floor: float) -> list[dict]:
    """
    Find resonance peaks: local maxima above 3× noise floor.
    Returns list sorted by amplitude (strongest first).
    """
    threshold = noise_floor * 3.0
    peaks = []

    for i in range(2, len(amplitudes) - 2):
        # Local maximum (wider window for robustness)
        if (amplitudes[i] > amplitudes[i-1] and
            amplitudes[i] > amplitudes[i+1] and
            amplitudes[i] > amplitudes[i-2] and
            amplitudes[i] > amplitudes[i+2] and
            amplitudes[i] > threshold):

            snr_db = 20 * np.log10(amplitudes[i] / noise_floor) if noise_floor > 0 else 0
            peaks.append({
                "freq_hz": round(float(freqs[i]), 1),
                "amplitude_mv": round(float(amplitudes[i]), 1),
                "snr_db": round(snr_db, 1),
                "index": i,
            })

    # Sort by amplitude (strongest first)
    peaks.sort(key=lambda x: x["amplitude_mv"], reverse=True)
    return peaks


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="T1.2 — Broadband Mode Census")
    parser.add_argument("--start", type=float, default=F_START,
                        help=f"Start frequency in Hz (default: {F_START})")
    parser.add_argument("--stop", type=float, default=F_STOP,
                        help=f"Stop frequency in Hz (default: {F_STOP})")
    parser.add_argument("--steps", type=int, default=N_STEPS,
                        help=f"Number of frequency steps (default: {N_STEPS})")
    parser.add_argument("--settle", type=float, default=SETTLE_S,
                        help=f"Settle time per step in seconds (default: {SETTLE_S})")
    parser.add_argument("--avg", type=int, default=N_AVG,
                        help=f"Captures to average per step (default: {N_AVG})")
    parser.add_argument("--relay-ch", type=int, default=RELAY_RX,
                        help=f"Relay channel for RX PZT (default: {RELAY_RX})")
    parser.add_argument("--no-relay", action="store_true",
                        help="Skip relay mux")
    args = parser.parse_args()

    print("=" * 70)
    print("  T1.2 — Broadband Mode Census (Fused Silica Plate)")
    print("=" * 70)
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Sweep: {args.start:.0f} – {args.stop:.0f} Hz, {args.steps} steps (linear)")
    print(f"  Settle: {args.settle*1000:.0f} ms/step, {args.avg} averages")
    est_time = args.steps * (args.settle + args.avg * 0.15)
    print(f"  Estimated time: {est_time:.0f} s ({est_time/60:.1f} min)")
    print(f"  Success: ≥ 5 modes above 3σ")

    handle = open_scope()

    mux = None
    if not args.no_relay:
        try:
            from relay_mux import RelayMux
            mux = RelayMux()
            mux.open()
            mux.select(args.relay_ch)
            print(f"  Relay mux: channel {args.relay_ch} selected")
            time.sleep(0.1)
        except Exception as e:
            print(f"  WARNING: Relay mux failed ({e})")
            mux = None

    try:
        # Linear frequency sweep
        freqs = np.linspace(args.start, args.stop, args.steps)
        amplitudes = np.zeros(args.steps)
        rms_values = np.zeros(args.steps)

        print(f"\n  Sweeping {args.steps} frequencies...")
        t0 = time.time()

        for i, freq in enumerate(freqs):
            result = measure_amplitude(handle, freq)
            amplitudes[i] = result["pp_mv"]
            rms_values[i] = result["rms_mv"]

            # Progress every 10%
            if (i + 1) % max(1, args.steps // 10) == 0:
                elapsed = time.time() - t0
                pct = (i + 1) / args.steps * 100
                eta = elapsed / (i + 1) * (args.steps - i - 1)
                print(f"    {i+1}/{args.steps} ({pct:.0f}%) — "
                      f"{freq:.0f} Hz: {amplitudes[i]:.1f} mV pp "
                      f"[{elapsed:.0f}s elapsed, ~{eta:.0f}s remaining]")

        # Turn off AWG
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)

        total_time = time.time() - t0
        print(f"\n  Sweep complete in {total_time:.0f}s")

        # Compute noise floor (median of all measurements)
        noise_floor = float(np.median(amplitudes))
        print(f"  Noise floor (median): {noise_floor:.1f} mV pp")
        print(f"  Peak threshold (3σ): {noise_floor * 3:.1f} mV pp")

        # Find resonance peaks
        peaks = find_peaks(freqs, amplitudes, noise_floor)
        n_peaks = len(peaks)

        # Results
        print(f"\n  {'='*60}")
        print(f"  MODES DETECTED: {n_peaks}")
        print(f"  {'='*60}")

        if peaks:
            print(f"\n  {'#':<4} {'Freq (Hz)':<12} {'Amplitude (mV)':<16} {'SNR (dB)':<10}")
            print(f"  {'-'*4} {'-'*12} {'-'*16} {'-'*10}")
            for rank, p in enumerate(peaks[:30], 1):
                marker = " ★" if p["freq_hz"] > 30000 and p["freq_hz"] < 40000 else ""
                print(f"  {rank:<4} {p['freq_hz']:<12.1f} {p['amplitude_mv']:<16.1f} "
                      f"{p['snr_db']:<10.1f}{marker}")

            # Statistics
            mode_freqs = [p["freq_hz"] for p in peaks]
            print(f"\n  Frequency range: {min(mode_freqs):.0f} – {max(mode_freqs):.0f} Hz")
            print(f"  Mean spacing: {np.mean(np.diff(sorted(mode_freqs))):.0f} Hz" if len(mode_freqs) > 1 else "")
            print(f"  Best SNR: {peaks[0]['snr_db']:.1f} dB at {peaks[0]['freq_hz']:.0f} Hz")

        # Gate decision
        print(f"\n  {'-'*50}")
        if n_peaks >= 5:
            print(f"  DECISION: ✓ PASS — {n_peaks} modes detected (≥ 5 required)")
            print(f"  → Proceed to T1.3 (Single-Capture Eigenmode Discrimination)")
        else:
            print(f"  DECISION: ✗ INSUFFICIENT — only {n_peaks} modes (need ≥ 5)")
            print(f"  → Try: wider sweep, higher drive, or different plate mounting")

        # Save results
        output = {
            "experiment": "T1.2_mode_census",
            "timestamp": datetime.now().isoformat(),
            "plate": "100x100mm_fused_silica",
            "relay_channel": args.relay_ch if not args.no_relay else "direct",
            "sweep": {
                "start_hz": args.start,
                "stop_hz": args.stop,
                "n_steps": args.steps,
                "settle_s": args.settle,
                "n_avg": args.avg,
            },
            "awg_amplitude_uvpp": AWG_DRIVE_UVPP,
            "noise_floor_mv": noise_floor,
            "threshold_mv": noise_floor * 3,
            "n_modes": n_peaks,
            "modes": peaks,
            "sweep_data": {
                "freqs_hz": freqs.tolist(),
                "amplitudes_mv": amplitudes.tolist(),
                "rms_mv": rms_values.tolist(),
            },
            "total_time_s": round(total_time, 1),
            "gate_decision": "PASS" if n_peaks >= 5 else "INSUFFICIENT",
        }

        results_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "plate_census"
        results_dir.mkdir(parents=True, exist_ok=True)
        out_file = results_dir / f"t1_2_census_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(out_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\n  Results saved: {out_file}")

    finally:
        if mux:
            mux.off()
        close_scope(handle)


if __name__ == "__main__":
    main()
