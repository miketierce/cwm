#!/usr/bin/env python3
"""
T2.2b — Intermodulation via Simultaneous Dual-Tone (AWG + DDS)

Definitive intermodulation test using TRUE simultaneous dual-tone excitation:
  - PicoScope AWG drives f1 through Board D (strong carrier, ~3.47 Vpp at PZT)
  - AD9833 DDS#1 drives f2 through Board D summing node (weaker, ~0.4 Vpp)
  - Both feed Board D col 5 → amplified × 3.69 → TX PZT → plate

Protocol:
  1. For each mode pair (f1, f2):
     a. DUAL: AWG at f1 + DDS at f2 simultaneously → capture → check IM bins
     b. AWG-ONLY: AWG at f1, DDS off → capture → baseline IM level
     c. DDS-ONLY: DDS at f2, AWG off → capture → baseline IM level
     d. SILENCE: both off → noise floor
  2. Compare: are IM products (f1±f2, 2f1-f2, 2f2-f1) STRONGER in DUAL vs baselines?

If acoustic nonlinearity exists, IM products will be measurably stronger when both
tones are physically present in the plate simultaneously.

Mode pairs (from T1.2/T1.3 confirmed modes):
  (35840, 57037), (35840, 97011), (54920, 97011), (54920, 57037)

Hardware:
  - PicoScope AWG (0.5 Vpp) → Board D col 5 (summing node)
  - AD9833 DDS#1 (670 mVpp) → 10kΩ → Board D col 5 (summing node)
  - Board D (OPA2134PA, ×3.69) → 47Ω → TX PZT (SW)
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V)

DDS Arduino: /dev/cu.usbserial-1120, 115200 baud, commands F1:<freq>, Foff

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t2_2b_intermod_dualtone.py

  # More averages:
  python tools/t2_2b_intermod_dualtone.py --averages 80
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
import serial

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

AWG_DRIVE_UVPP = 500_000   # 0.5 Vpp (same as all T-series experiments)
DDS_PORT = "/dev/cu.usbserial-1120"
DDS_BAUD = 115200

SETTLE_S = 0.30             # generous settle for steady-state
N_AVG_DEFAULT = 50

# Mode pairs to test
DEFAULT_PAIRS = [
    (35_840, 57_037),
    (35_840, 97_011),
    (54_920, 97_011),
    (54_920, 57_037),
]

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
    ps2000.ps2000_set_channel(handle, 0, 1, 1, RANGE_INDEX)
    return handle, ps2000


def capture_block(handle, ps2000):
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


def open_dds(port: str = DDS_PORT, baud: int = DDS_BAUD) -> serial.Serial:
    ser = serial.Serial(port, baud, timeout=2)
    time.sleep(2.5)  # Arduino reset
    ser.reset_input_buffer()
    # Verify connection
    ser.write(b"D?\n")
    time.sleep(0.1)
    resp = ser.readline().decode("ascii", errors="replace").strip()
    if "DDS:" not in resp:
        raise RuntimeError(f"DDS Arduino not responding: {resp!r}")
    return ser


def dds_set_freq(ser: serial.Serial, channel: int, freq_hz: int):
    cmd = f"F{channel}:{freq_hz}\n"
    ser.write(cmd.encode())
    time.sleep(0.01)
    ser.readline()  # consume response


def dds_off(ser: serial.Serial):
    ser.write(b"Foff\n")
    time.sleep(0.01)
    ser.readline()


# ---------------------------------------------------------------------------
# FFT analysis
# ---------------------------------------------------------------------------


def compute_fft(mv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (fft_magnitude, freq_axis) with zero-padding."""
    ac = mv - mv.mean()
    window = np.hanning(len(ac))
    nfft = len(ac) * N_FFT_PAD
    fft_mag = np.abs(np.fft.rfft(ac * window, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE_HZ)
    return fft_mag, freq_axis


def measure_at_bin(fft_mag: np.ndarray, freq_hz: float, bin_hz: float) -> float:
    """Peak magnitude within ±3 bins of target frequency."""
    target_bin = int(round(freq_hz / bin_hz))
    lo = max(0, target_bin - 3)
    hi = min(len(fft_mag) - 1, target_bin + 3)
    return float(fft_mag[lo:hi + 1].max())


def get_im_frequencies(f1: float, f2: float) -> dict[str, float]:
    """Return dict of IM product labels → frequencies."""
    products = {}
    candidates = [
        ("f1+f2", f1 + f2),
        ("|f1-f2|", abs(f1 - f2)),
        ("2f1-f2", 2 * f1 - f2),
        ("2f2-f1", 2 * f2 - f1),
        ("f1+2f2", f1 + 2 * f2),
        ("2f1+f2", 2 * f1 + f2),
    ]
    max_freq = SAMPLE_RATE_HZ / 2
    for label, freq in candidates:
        if 0 < freq < max_freq:
            products[label] = freq
    return products


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------


def run_dualtone_intermod(pairs: list[tuple[int, int]], n_avg: int, relay_ch: int):
    """Run the dual-tone intermodulation experiment."""
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(relay_ch)
    time.sleep(0.2)
    dds = open_dds()

    nfft = N_SAMPLES * N_FFT_PAD
    bin_hz = SAMPLE_RATE_HZ / nfft

    print(f"\n{'='*70}")
    print(f"T2.2b — Intermodulation via Simultaneous Dual-Tone (AWG + DDS)")
    print(f"{'='*70}")
    print(f"  Pairs: {pairs}")
    print(f"  Averages: {n_avg}")
    print(f"  AWG: 0.5 Vpp → Board D (×3.69) → PZT")
    print(f"  DDS: 670 mVpp → 10kΩ → Board D (×3.69) → PZT")
    print(f"  FFT: {N_SAMPLES}×{N_FFT_PAD} zero-pad, bin = {bin_hz:.2f} Hz")
    print(f"  DDS port: {DDS_PORT}")
    print(f"{'='*70}\n")

    # Noise floor measurement
    print("  Measuring noise floor (all off)...", end=" ", flush=True)
    stop_awg(handle, ps2000)
    dds_off(dds)
    time.sleep(SETTLE_S)
    noise_mags = []
    for _ in range(10):
        mv = capture_block(handle, ps2000)
        fft_mag, _ = compute_fft(mv)
        noise_mags.append(fft_mag)
    noise_floor = np.mean(noise_mags, axis=0)
    noise_median = float(np.median(noise_floor[10:]))
    print(f"median = {noise_median:.1f}")

    all_results = []
    max_im_excess = 0.0
    max_im_sigma = 0.0

    for pair_idx, (f1, f2) in enumerate(pairs):
        im_freqs = get_im_frequencies(float(f1), float(f2))

        print(f"\n  {'─'*66}")
        print(f"  Pair {pair_idx+1}: AWG={f1/1000:.1f}k + DDS={f2/1000:.1f}k")
        print(f"  IM targets: {', '.join(f'{l}={v/1000:.1f}k' for l, v in im_freqs.items())}")
        print(f"  {'─'*66}")

        # --- 4 conditions ---
        conditions = {
            "DUAL": {"awg": f1, "dds": f2},
            "AWG_ONLY": {"awg": f1, "dds": None},
            "DDS_ONLY": {"awg": None, "dds": f2},
            "SILENCE": {"awg": None, "dds": None},
        }

        condition_data = {}

        for cond_name, cfg in conditions.items():
            # Set excitation
            if cfg["awg"]:
                set_awg(handle, ps2000, cfg["awg"])
            else:
                stop_awg(handle, ps2000)
            if cfg["dds"]:
                dds_set_freq(dds, 1, cfg["dds"])
            else:
                dds_off(dds)
            time.sleep(SETTLE_S)

            # Capture n_avg
            mags_at_bins = {label: [] for label in im_freqs}
            mags_at_bins["f1"] = []
            mags_at_bins["f2"] = []

            for _ in range(n_avg):
                mv = capture_block(handle, ps2000)
                fft_mag, _ = compute_fft(mv)

                mags_at_bins["f1"].append(measure_at_bin(fft_mag, f1, bin_hz))
                mags_at_bins["f2"].append(measure_at_bin(fft_mag, f2, bin_hz))
                for label, freq in im_freqs.items():
                    mags_at_bins[label].append(measure_at_bin(fft_mag, freq, bin_hz))

            condition_data[cond_name] = {
                k: {"mean": float(np.mean(v)), "std": float(np.std(v))}
                for k, v in mags_at_bins.items()
            }

        # --- Analysis: compare DUAL vs baselines ---
        print(f"\n    {'Bin':>12s}  {'DUAL':>9s}  {'AWG':>9s}  {'DDS':>9s}  "
              f"{'Silence':>9s}  {'Excess':>7s}  {'σ':>5s}")
        print(f"    {'─'*12}  {'─'*9}  {'─'*9}  {'─'*9}  {'─'*9}  {'─'*7}  {'─'*5}")

        pair_result = {"f1_hz": f1, "f2_hz": f2, "im_bins": {}}

        # Show carrier levels first
        for label in ["f1", "f2"]:
            dual_m = condition_data["DUAL"][label]["mean"]
            awg_m = condition_data["AWG_ONLY"][label]["mean"]
            dds_m = condition_data["DDS_ONLY"][label]["mean"]
            sil_m = condition_data["SILENCE"][label]["mean"]
            print(f"    {label:>12s}  {dual_m:>9.0f}  {awg_m:>9.0f}  "
                  f"{dds_m:>9.0f}  {sil_m:>9.0f}  {'—':>7s}  {'—':>5s}")

        # IM products: key comparison
        for label in im_freqs:
            dual_m = condition_data["DUAL"][label]["mean"]
            dual_s = condition_data["DUAL"][label]["std"]
            awg_m = condition_data["AWG_ONLY"][label]["mean"]
            awg_s = condition_data["AWG_ONLY"][label]["std"]
            dds_m = condition_data["DDS_ONLY"][label]["mean"]
            sil_m = condition_data["SILENCE"][label]["mean"]

            # Baseline = max of AWG-only, DDS-only, silence at this bin
            baseline = max(awg_m, dds_m, sil_m)
            excess_pct = (dual_m - baseline) / baseline * 100 if baseline > 0 else 0

            # Significance: is DUAL > AWG_ONLY?
            pooled_std = np.sqrt((dual_s**2 + awg_s**2) / 2)
            sigma = (dual_m - awg_m) / pooled_std if pooled_std > 0 else 0

            max_im_excess = max(max_im_excess, abs(excess_pct))
            max_im_sigma = max(max_im_sigma, abs(sigma))

            print(f"    {label:>12s}  {dual_m:>9.0f}  {awg_m:>9.0f}  "
                  f"{dds_m:>9.0f}  {sil_m:>9.0f}  {excess_pct:>+6.1f}%  "
                  f"{sigma:>+4.1f}σ")

            pair_result["im_bins"][label] = {
                "freq_hz": im_freqs[label],
                "dual_mean": dual_m, "dual_std": dual_s,
                "awg_only_mean": awg_m, "dds_only_mean": dds_m,
                "silence_mean": sil_m,
                "excess_pct": excess_pct,
                "sigma_vs_awg": float(sigma),
            }

        pair_result["carriers"] = {
            "f1_dual": condition_data["DUAL"]["f1"]["mean"],
            "f1_awg": condition_data["AWG_ONLY"]["f1"]["mean"],
            "f2_dual": condition_data["DUAL"]["f2"]["mean"],
            "f2_dds": condition_data["DDS_ONLY"]["f2"]["mean"],
        }
        all_results.append(pair_result)

    # Cleanup
    stop_awg(handle, ps2000)
    dds_off(dds)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    dds.close()

    # --- Summary ---
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Max |IM excess| (DUAL vs baseline): {max_im_excess:.1f}%")
    print(f"  Max |σ| (DUAL vs AWG-only): {max_im_sigma:.2f}σ")

    if max_im_sigma >= 3.0:
        gate = "PASS"
        print(f"\n  ★ GATE DECISION: PASS (acoustic IM detected at {max_im_sigma:.1f}σ)")
    elif max_im_sigma >= 2.0:
        gate = "MARGINAL"
        print(f"\n  ◆ GATE DECISION: MARGINAL ({max_im_sigma:.1f}σ)")
    else:
        gate = "FAIL"
        print(f"\n  ✗ GATE DECISION: FAIL (max σ = {max_im_sigma:.2f} — no acoustic IM)")
        print("    IM bins are at baseline regardless of dual-tone drive.")

    # Save
    out_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "intermodulation"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"t2_2b_dualtone_{ts}.json"

    result_doc = {
        "experiment": "T2.2b_intermod_dualtone",
        "timestamp": datetime.now().isoformat(),
        "plate": "100x100mm_fused_silica",
        "relay_channel": relay_ch,
        "n_averages": n_avg,
        "awg_uvpp": AWG_DRIVE_UVPP,
        "dds_port": DDS_PORT,
        "noise_floor_median": float(noise_median),
        "max_im_excess_pct": float(max_im_excess),
        "max_im_sigma": float(max_im_sigma),
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
        description="T2.2b Intermodulation via Dual-Tone (AWG + DDS)")
    parser.add_argument("--averages", type=int, default=N_AVG_DEFAULT)
    parser.add_argument("--relay", type=int, default=RELAY_CH)
    parser.add_argument("--dds-port", default=DDS_PORT)
    args = parser.parse_args()

    run_dualtone_intermod(
        pairs=DEFAULT_PAIRS,
        n_avg=args.averages,
        relay_ch=args.relay,
    )


if __name__ == "__main__":
    main()
