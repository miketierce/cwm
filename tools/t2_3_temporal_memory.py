#!/usr/bin/env python3
"""
T2.3 — Ring-down Temporal Memory (Fused Silica Plate)

Tests whether the presence of a decaying eigenmode affects the response
measured at a different mode's frequency. This probes cross-mode energy
transfer during ringdown — a temporal memory effect.

Protocol:
  1. CONDITION A (primed): Drive f1 for T_write ms, stop, wait T_gap ms,
     then drive f2 briefly and capture amplitude at f2.
  2. CONDITION B (unprimed): Skip f1 drive, just silence for equivalent
     time, then drive f2 briefly and capture amplitude at f2.
  3. Compare: does f1 priming affect f2 response?
  4. Repeat for multiple mode pairs and gap times.

If cross-mode decay exists, the f2 amplitude should differ between
primed (A) and unprimed (B) conditions — the decaying f1 vibration
modulates the plate's response at f2.

Success criterion: measurable difference in f2 amplitude between
  primed and unprimed conditions (>2σ or >5% contrast)

Mode pairs:
  f1=35,840 Hz → measure f2=57,037 Hz (and vice versa)
  f1=54,920 Hz → measure f2=97,011 Hz

Hardware:
  - PicoScope AWG → Board D (3.69×) → TX PZT (SW) → Plate
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V)

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t2_3_temporal_memory.py

  # Specific pair:
  python tools/t2_3_temporal_memory.py --f-prime 35840 --f-probe 57037

  # More averages:
  python tools/t2_3_temporal_memory.py --averages 30
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

T_WRITE_MS = 50            # prime mode for 50 ms (enough to reach ~87% of steady-state)
T_PROBE_MS = 5             # brief probe excitation
DEFAULT_GAPS_MS = [2, 5, 10, 20, 40]  # gap between prime and probe

# Mode pairs: (prime_freq, probe_freq)
DEFAULT_PAIRS = [
    (35_840.0, 57_037.0),
    (57_037.0, 35_840.0),
    (54_920.0, 97_011.0),
    (97_011.0, 54_920.0),
]

N_AVG_DEFAULT = 20

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
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0, 0, 0, 0
    )


def stop_awg(handle, ps2000):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0, 0, 0, 0
    )


def measure_amplitude(handle, ps2000) -> float:
    """Capture and return peak-to-peak mV."""
    mv = capture_block(handle, ps2000)
    ac = mv - mv.mean()
    return float(ac.max() - ac.min())


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------

def run_temporal_memory(pairs: list[tuple[float, float]], gaps_ms: list[float],
                        n_avg: int, relay_ch: int):
    """Run cross-mode temporal memory experiment."""
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(relay_ch)
    time.sleep(0.2)

    print(f"\n{'='*65}")
    print(f"T2.3 — Ring-down Temporal Memory")
    print(f"{'='*65}")
    print(f"Pairs (prime → probe): {[(f'{f1/1000:.1f}k',f'{f2/1000:.1f}k') for f1,f2 in pairs]}")
    print(f"T_write: {T_WRITE_MS} ms, T_probe: {T_PROBE_MS} ms")
    print(f"Gaps: {gaps_ms} ms")
    print(f"Averages: {n_avg}")
    print(f"{'='*65}\n")

    all_results = []

    for pair_idx, (f_prime, f_probe) in enumerate(pairs):
        print(f"  --- Pair {pair_idx+1}: prime {f_prime/1000:.1f}k → probe {f_probe/1000:.1f}k ---")

        pair_results = {"f_prime_hz": f_prime, "f_probe_hz": f_probe, "gaps": []}

        for gap_ms in gaps_ms:
            # CONDITION A: Primed (drive f_prime, wait gap, probe f_probe)
            primed_vals = []
            for _ in range(n_avg):
                stop_awg(handle, ps2000)
                time.sleep(0.1)  # full silence

                # Prime: drive f1
                set_awg(handle, ps2000, f_prime)
                time.sleep(T_WRITE_MS / 1000.0)

                # Gap: silence while f1 decays
                stop_awg(handle, ps2000)
                time.sleep(gap_ms / 1000.0)

                # Probe: drive f2 briefly and measure
                set_awg(handle, ps2000, f_probe)
                time.sleep(T_PROBE_MS / 1000.0)
                amp = measure_amplitude(handle, ps2000)
                primed_vals.append(amp)

                stop_awg(handle, ps2000)
                time.sleep(0.05)

            # CONDITION B: Unprimed (equivalent silence, then probe f_probe)
            unprimed_vals = []
            for _ in range(n_avg):
                stop_awg(handle, ps2000)
                time.sleep(0.1)

                # No prime — just wait equivalent time
                time.sleep((T_WRITE_MS + gap_ms) / 1000.0)

                # Probe: same as above
                set_awg(handle, ps2000, f_probe)
                time.sleep(T_PROBE_MS / 1000.0)
                amp = measure_amplitude(handle, ps2000)
                unprimed_vals.append(amp)

                stop_awg(handle, ps2000)
                time.sleep(0.05)

            primed_mean = float(np.mean(primed_vals))
            primed_std = float(np.std(primed_vals))
            unprimed_mean = float(np.mean(unprimed_vals))
            unprimed_std = float(np.std(unprimed_vals))

            # Contrast: how different is primed from unprimed
            contrast_pct = (primed_mean - unprimed_mean) / unprimed_mean * 100 if unprimed_mean > 0 else 0
            # Pooled std for significance
            pooled_std = np.sqrt((primed_std**2 + unprimed_std**2) / 2)
            sigma_diff = (primed_mean - unprimed_mean) / pooled_std if pooled_std > 0 else 0

            gap_result = {
                "gap_ms": gap_ms,
                "primed_mean_mv": primed_mean,
                "primed_std_mv": primed_std,
                "unprimed_mean_mv": unprimed_mean,
                "unprimed_std_mv": unprimed_std,
                "contrast_pct": contrast_pct,
                "sigma_diff": sigma_diff,
            }
            pair_results["gaps"].append(gap_result)

            status = "✓" if abs(contrast_pct) > 5 or abs(sigma_diff) > 2 else "—"
            print(f"    gap={gap_ms:>3}ms: primed={primed_mean:>6.1f}±{primed_std:>5.1f}  "
                  f"unprimed={unprimed_mean:>6.1f}±{unprimed_std:>5.1f}  "
                  f"Δ={contrast_pct:>+5.1f}%  ({sigma_diff:>+4.1f}σ) {status}")

        all_results.append(pair_results)
        print()

    # Cleanup
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # Summary
    max_contrast = 0.0
    max_sigma = 0.0
    for pr in all_results:
        for g in pr["gaps"]:
            if abs(g["contrast_pct"]) > abs(max_contrast):
                max_contrast = g["contrast_pct"]
            if abs(g["sigma_diff"]) > abs(max_sigma):
                max_sigma = g["sigma_diff"]

    print(f"\n{'='*65}")
    print("SUMMARY")
    print(f"{'='*65}")
    print(f"  Max |contrast|: {abs(max_contrast):.1f}%")
    print(f"  Max |σ difference|: {abs(max_sigma):.1f}σ")

    # Gate: measurable cross-mode decay
    if abs(max_sigma) > 2.0 or abs(max_contrast) > 5.0:
        gate = "PASS"
        print(f"\n  *** GATE DECISION: PASS (cross-mode effect detected) ***")
    else:
        gate = "FAIL"
        print(f"\n  *** GATE DECISION: FAIL (no measurable cross-mode decay) ***")

    # Save
    out_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "temporal_memory"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"t2_3_temporal_{ts}.json"

    output = {
        "experiment": "T2.3_temporal_memory",
        "timestamp": datetime.now().isoformat(),
        "plate": "100x100mm_fused_silica",
        "relay_channel": relay_ch,
        "t_write_ms": T_WRITE_MS,
        "t_probe_ms": T_PROBE_MS,
        "awg_amplitude_uvpp": AWG_DRIVE_UVPP,
        "n_avg": n_avg,
        "pairs": all_results,
        "max_contrast_pct": max_contrast,
        "max_sigma_diff": max_sigma,
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
    parser = argparse.ArgumentParser(description="T2.3 — Temporal Memory")
    parser.add_argument("--f-prime", type=float, default=None,
                        help="Prime frequency (Hz). Tests single pair if set with --f-probe.")
    parser.add_argument("--f-probe", type=float, default=None,
                        help="Probe frequency (Hz).")
    parser.add_argument("--gaps", type=float, nargs="+", default=None,
                        help=f"Gap times in ms (default: {DEFAULT_GAPS_MS})")
    parser.add_argument("--averages", type=int, default=N_AVG_DEFAULT,
                        help=f"Averages per condition (default: {N_AVG_DEFAULT})")
    parser.add_argument("--relay-ch", type=int, default=RELAY_CH,
                        help=f"Relay channel (default: {RELAY_CH})")
    args = parser.parse_args()

    if args.f_prime and args.f_probe:
        pairs = [(args.f_prime, args.f_probe)]
    else:
        pairs = DEFAULT_PAIRS

    gaps = args.gaps if args.gaps else DEFAULT_GAPS_MS

    run_temporal_memory(pairs=pairs, gaps_ms=gaps, n_avg=args.averages,
                        relay_ch=args.relay_ch)


if __name__ == "__main__":
    main()
