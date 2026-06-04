#!/usr/bin/env python3
"""
T2.2 — 3-Source Intermodulation Products (Fused Silica Plate)

Tests for nonlinear mixing between simultaneously-ringing eigenmodes.
If the plate has ANY nonlinearity, driving two modes (f1, f2) should
produce intermodulation products at f1±f2, 2f1-f2, 2f2-f1, etc.

Limitation: PicoScope AWG outputs only one frequency at a time.
Workaround: Sequential excitation — drive f1 for T_burst ms, then f2
for T_burst ms. Both modes ring simultaneously (τ≈20 ms >> T_burst).
Capture FFT during coexistence window and look for IM products.

Protocol:
  1. Drive f1 for T_burst ms (establish mode 1 ringing)
  2. Immediately switch to f2 for T_burst ms (mode 1 still ringing)
  3. Stop AWG, immediately capture (both modes decaying together)
  4. Compute FFT; check for energy at IM frequencies (f2-f1, f1+f2, 2f1-f2, 2f2-f1)
  5. Compare IM amplitudes vs noise floor
  6. Control: measure with relay OFF (electrical only) to verify IM is acoustic

Success criterion: ≥ 3 IM products at > 2× ON/OFF ratio
Kill criterion: no IM products above noise → plate is purely linear

Mode pairs to test (well-separated, confirmed acoustic):
  Pair A: f1=35,840 Hz, f2=57,037 Hz → IM: 21,197 / 92,877 / 14,643 / 78,234 Hz
  Pair B: f1=35,840 Hz, f2=97,011 Hz → IM: 61,171 / 132,851 (above Nyquist/2)
  Pair C: f1=54,920 Hz, f2=97,011 Hz → IM: 42,091 / 151,931 / 12,829 / 139,102 Hz

Hardware:
  - PicoScope AWG → Board D (3.69×) → TX PZT (SW) → Plate
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V)
  - 2048 samples, timebase 7 → 781,250 Hz → FFT bin = 381.5 Hz

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t2_2_intermodulation.py

  # Test specific pair:
  python tools/t2_2_intermodulation.py --f1 35840 --f2 57037

  # More averages:
  python tools/t2_2_intermodulation.py --averages 30
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
FFT_BIN_HZ = SAMPLE_RATE_HZ / N_SAMPLES  # 381.5 Hz
RANGE_INDEX = 8        # ±5V
RANGE_MV = 5000.0
RELAY_CH = 8

AWG_DRIVE_UVPP = 500_000   # 0.5 Vpp

# Sequential burst timing
T_BURST_MS = 15        # drive each mode for 15 ms (< τ≈24 ms so first mode still ringing)

# Mode pairs to test
DEFAULT_PAIRS = [
    (35_840.0, 57_037.0),   # Pair A
    (35_840.0, 97_011.0),   # Pair B
    (54_920.0, 97_011.0),   # Pair C
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


def compute_fft(mv: np.ndarray) -> np.ndarray:
    """Single-sided FFT magnitude (mV), Hanning windowed."""
    ac = mv - mv.mean()
    window = np.hanning(len(ac))
    fft_vals = np.fft.rfft(ac * window)
    mag = np.abs(fft_vals) * 2.0 / N_SAMPLES
    return mag


def freq_to_bin(freq_hz: float) -> int:
    return int(round(freq_hz / FFT_BIN_HZ))


def get_bin_amplitude(mag: np.ndarray, freq_hz: float, search_radius: int = 2) -> float:
    """Get max amplitude within ±search_radius bins of target frequency."""
    cbin = freq_to_bin(freq_hz)
    lo = max(1, cbin - search_radius)
    hi = min(len(mag) - 1, cbin + search_radius)
    return float(mag[lo:hi+1].max())


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------

def compute_im_frequencies(f1: float, f2: float) -> dict[str, float]:
    """Compute intermodulation product frequencies."""
    nyquist = SAMPLE_RATE_HZ / 2
    products = {
        "f2-f1": abs(f2 - f1),
        "f1+f2": f1 + f2,
        "2f1-f2": abs(2*f1 - f2),
        "2f2-f1": abs(2*f2 - f1),
        "3f1-2f2": abs(3*f1 - 2*f2),
        "3f2-2f1": abs(3*f2 - 2*f1),
    }
    # Only keep products below Nyquist
    return {k: v for k, v in products.items() if v < nyquist and v > 100}


def run_pair(handle, ps2000, f1: float, f2: float, n_avg: int,
             relay_on: bool) -> dict:
    """Run intermodulation test for one frequency pair."""
    im_freqs = compute_im_frequencies(f1, f2)

    # Accumulate FFT magnitudes
    mag_accum = None

    for trial in range(n_avg):
        # Silence first (let any residual decay)
        stop_awg(handle, ps2000)
        time.sleep(0.05)

        # Drive f1 for T_BURST_MS
        set_awg(handle, ps2000, f1)
        time.sleep(T_BURST_MS / 1000.0)

        # Switch to f2 for T_BURST_MS (f1 still ringing in plate)
        set_awg(handle, ps2000, f2)
        time.sleep(T_BURST_MS / 1000.0)

        # Stop and capture immediately (both modes decaying together)
        stop_awg(handle, ps2000)
        time.sleep(0.001)  # minimal delay

        mv = capture_block(handle, ps2000)
        mag = compute_fft(mv)

        if mag_accum is None:
            mag_accum = mag.copy()
        else:
            mag_accum += mag

    mag_avg = mag_accum / n_avg

    # Measure fundamentals and IM products
    f1_amp = get_bin_amplitude(mag_avg, f1)
    f2_amp = get_bin_amplitude(mag_avg, f2)

    # Noise floor: median of all bins excluding fundamentals and IM regions
    noise_mask = np.ones(len(mag_avg), dtype=bool)
    noise_mask[0] = False
    for freq in [f1, f2] + list(im_freqs.values()):
        cb = freq_to_bin(freq)
        noise_mask[max(0, cb-5):min(len(mag_avg), cb+6)] = False
    noise_floor = float(np.median(mag_avg[noise_mask]))

    im_results = {}
    for name, freq in im_freqs.items():
        amp = get_bin_amplitude(mag_avg, freq)
        snr = amp / noise_floor if noise_floor > 0 else 0
        im_results[name] = {
            "freq_hz": freq,
            "bin": freq_to_bin(freq),
            "amplitude_mv": amp,
            "snr_vs_noise": snr,
        }

    return {
        "f1_hz": f1,
        "f2_hz": f2,
        "f1_amplitude_mv": f1_amp,
        "f2_amplitude_mv": f2_amp,
        "noise_floor_mv": noise_floor,
        "im_products": im_results,
    }


def run_intermodulation(pairs: list[tuple[float, float]], n_avg: int,
                        relay_ch: int):
    """Run the full intermodulation experiment."""
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()

    print(f"\n{'='*65}")
    print(f"T2.2 — 3-Source Intermodulation Products")
    print(f"{'='*65}")
    print(f"Pairs: {pairs}")
    print(f"Burst time: {T_BURST_MS} ms per mode")
    print(f"Averages: {n_avg}")
    print(f"FFT bin: {FFT_BIN_HZ:.1f} Hz")
    print(f"{'='*65}\n")

    all_results = []

    for pair_idx, (f1, f2) in enumerate(pairs):
        im_freqs = compute_im_frequencies(f1, f2)
        print(f"  --- Pair {pair_idx+1}: {f1/1000:.1f} kHz + {f2/1000:.1f} kHz ---")
        print(f"  IM products: {', '.join(f'{k}={v/1000:.1f}k' for k,v in im_freqs.items())}")

        # Relay ON (acoustic)
        mux.select(relay_ch)
        time.sleep(0.2)
        print(f"  [Relay ON]  ", end="", flush=True)
        res_on = run_pair(handle, ps2000, f1, f2, n_avg, relay_on=True)
        print(f"f1={res_on['f1_amplitude_mv']:.2f} mV, f2={res_on['f2_amplitude_mv']:.2f} mV, "
              f"noise={res_on['noise_floor_mv']:.3f} mV")

        # Relay OFF (electrical only)
        mux.off()
        time.sleep(0.2)
        print(f"  [Relay OFF] ", end="", flush=True)
        res_off = run_pair(handle, ps2000, f1, f2, n_avg, relay_on=False)
        print(f"f1={res_off['f1_amplitude_mv']:.2f} mV, f2={res_off['f2_amplitude_mv']:.2f} mV, "
              f"noise={res_off['noise_floor_mv']:.3f} mV")

        # Compare IM products
        print(f"\n  {'Product':<10} {'Freq (kHz)':<12} {'ON (mV)':<10} {'OFF (mV)':<10} "
              f"{'Ratio':<8} {'ON SNR':<8} {'Acoustic?'}")
        print(f"  {'-'*10} {'-'*12} {'-'*10} {'-'*10} {'-'*8} {'-'*8} {'-'*10}")

        n_acoustic_im = 0
        for name in im_freqs:
            on_amp = res_on["im_products"][name]["amplitude_mv"]
            off_amp = res_off["im_products"][name]["amplitude_mv"]
            on_snr = res_on["im_products"][name]["snr_vs_noise"]
            ratio = on_amp / off_amp if off_amp > 0 else float('inf')
            is_acoustic = ratio > 2.0 and on_snr > 2.0
            if is_acoustic:
                n_acoustic_im += 1
            verdict = "✓ YES" if is_acoustic else "—"
            print(f"  {name:<10} {im_freqs[name]/1000:<12.2f} {on_amp:<10.4f} "
                  f"{off_amp:<10.4f} {ratio:<8.2f} {on_snr:<8.1f} {verdict}")

        print(f"\n  Acoustic IM products for this pair: {n_acoustic_im}")
        print()

        all_results.append({
            "pair": [f1, f2],
            "relay_on": res_on,
            "relay_off": res_off,
            "n_acoustic_im": n_acoustic_im,
        })

    # Cleanup
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # Summary
    total_acoustic_im = sum(r["n_acoustic_im"] for r in all_results)
    print(f"\n{'='*65}")
    print("SUMMARY")
    print(f"{'='*65}")
    print(f"  Total acoustic IM products across all pairs: {total_acoustic_im}")
    for i, r in enumerate(all_results):
        f1, f2 = r["pair"]
        print(f"  Pair {i+1} ({f1/1000:.1f}k + {f2/1000:.1f}k): {r['n_acoustic_im']} acoustic IM products")

    if total_acoustic_im >= 3:
        gate = "PASS"
        print(f"\n  *** GATE DECISION: PASS ({total_acoustic_im} acoustic IM products ≥ 3) ***")
    else:
        gate = "FAIL"
        print(f"\n  *** GATE DECISION: FAIL ({total_acoustic_im} acoustic IM products < 3) ***")
        print(f"  NOTE: Plate may be too linear for intermodulation at this drive level")

    # Save
    out_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "intermodulation"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"t2_2_intermod_{ts}.json"

    output = {
        "experiment": "T2.2_intermodulation_products",
        "timestamp": datetime.now().isoformat(),
        "plate": "100x100mm_fused_silica",
        "relay_channel": relay_ch,
        "t_burst_ms": T_BURST_MS,
        "awg_amplitude_uvpp": AWG_DRIVE_UVPP,
        "n_avg": n_avg,
        "pairs": all_results,
        "total_acoustic_im": total_acoustic_im,
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
    parser = argparse.ArgumentParser(description="T2.2 — Intermodulation Products")
    parser.add_argument("--f1", type=float, default=None,
                        help="First frequency (Hz). If set, only tests this pair.")
    parser.add_argument("--f2", type=float, default=None,
                        help="Second frequency (Hz). Required if --f1 is set.")
    parser.add_argument("--averages", type=int, default=N_AVG_DEFAULT,
                        help=f"Averages per measurement (default: {N_AVG_DEFAULT})")
    parser.add_argument("--relay-ch", type=int, default=RELAY_CH,
                        help=f"Relay channel (default: {RELAY_CH})")
    args = parser.parse_args()

    if args.f1 and args.f2:
        pairs = [(args.f1, args.f2)]
    else:
        pairs = DEFAULT_PAIRS

    run_intermodulation(pairs=pairs, n_avg=args.averages, relay_ch=args.relay_ch)


if __name__ == "__main__":
    main()
