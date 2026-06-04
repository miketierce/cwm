#!/usr/bin/env python3
"""
T2.2c — Intermodulation via Arbitrary Waveform Dual-Tone

Definitive intermodulation test using TRUE simultaneous dual-tone excitation
at EQUAL amplitude, both tones from PicoScope AWG arbitrary waveform:
  - AWG produces f1+f2 at equal power through Board D (×3.69) → TX PZT
  - No DDS needed — both tones traverse identical analog path
  - Each tone: 0.5 Vpp at AWG → 1.845 Vpp at PZT (through Board D gain)

Method:
  The PicoScope 2204A AWG supports arbitrary waveform generation via DDS.
  We precompute a 4096-sample buffer containing n1 cycles of f1 and n2 cycles
  of f2, where n1/n2 ≈ f1/f2 with sub-Hz frequency error. The DDS phase
  accumulator replays this buffer at the correct rate to produce both tones.

Protocol:
  For each mode pair (f1, f2):
    a. DUAL: arbitrary waveform with both tones → check IM bins
    b. F1_ONLY: built-in sig gen at f1, 0.5 Vpp (matches per-tone amplitude)
    c. F2_ONLY: built-in sig gen at f2, 0.5 Vpp
    d. SILENCE: AWG off → noise floor
  Compare: are IM products stronger in DUAL vs single-tone baselines?

Mode pairs (from T1.2/T1.3):
  (35840, 57037), (35840, 97011), (54920, 97011), (54920, 57037)

Hardware:
  - PicoScope AWG (arb dual-tone, 1 Vpp total → 0.5 Vpp/tone) → Board D → PZT
  - Board D (OPA2134PA, ×3.69) → 47Ω → TX PZT (SW)
  - RX PZT (NE, relay 8) → Board A (×11) → PicoScope Ch A (±5V)

Advantage over T2.2b:
  - Both tones at EQUAL amplitude (0.5 Vpp each at AWG, ~1.85 Vpp at PZT)
  - Same signal path (no 10kΩ attenuation on second tone)
  - No DDS hardware needed

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t2_2c_intermod_arb.py
  python tools/t2_2c_intermod_arb.py --averages 80
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

# AWG settings
AWG_DUAL_UVPP = 1_000_000    # 1 Vpp total (0.5 Vpp per tone)
AWG_SINGLE_UVPP = 500_000    # 0.5 Vpp for single-tone baselines (matches per-tone)
AWG_BUF_SIZE = 4096          # Max arbitrary waveform buffer for 2204A
AWG_DAC_CLOCK = 2_000_000    # 2 MS/s DAC clock

SETTLE_S = 0.30
N_AVG_DEFAULT = 50

# Mode pairs and precomputed optimal parameters
# (f1, f2, n1, n2) — n1 cycles of f1 and n2 cycles of f2 in the buffer
# All have sub-Hz frequency error and ≥8.9 samples/cycle
PAIR_PARAMS = [
    {"f1": 35_840, "f2": 57_037, "n1": 257, "n2": 409},
    {"f1": 35_840, "f2": 97_011, "n1": 133, "n2": 360},
    {"f1": 54_920, "f2": 97_011, "n1": 244, "n2": 431},
    {"f1": 54_920, "f2": 57_037, "n1": 441, "n2": 458},
]

DYLIB_PATH = (
    '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
)

os.environ['DYLD_LIBRARY_PATH'] = os.path.dirname(DYLIB_PATH)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relay_mux import RelayMux  # noqa: E402

# ---------------------------------------------------------------------------
# Waveform computation
# ---------------------------------------------------------------------------


def compute_delta_phase(f1: float, n1: int) -> int:
    """Compute DDS delta phase for buffer repetition rate = f1/n1."""
    f_rep = f1 / n1
    return int(round(f_rep * (2**32) / AWG_DAC_CLOCK))


def compute_actual_freqs(f1: float, n1: int, n2: int) -> tuple[float, float]:
    """Return actual f1, f2 from integer deltaPhase quantization."""
    delta_phase = compute_delta_phase(f1, n1)
    f_rep = delta_phase * AWG_DAC_CLOCK / (2**32)
    return n1 * f_rep, n2 * f_rep


def generate_dual_tone_buffer(n1: int, n2: int) -> np.ndarray:
    """Generate 4096-sample buffer with n1 cycles of tone1 + n2 cycles of tone2.

    Returns uint8 array (0-255), center=128.
    Each tone at half amplitude so sum stays within range.
    """
    t = np.arange(AWG_BUF_SIZE, dtype=np.float64) / AWG_BUF_SIZE
    signal = 0.5 * np.sin(2 * np.pi * n1 * t) + 0.5 * np.sin(2 * np.pi * n2 * t)
    # Scale: signal range is [-1, +1] → buffer [1, 255] with center at 128
    buf = np.clip(np.round(128 + 127 * signal), 0, 255).astype(np.uint8)
    return buf


# ---------------------------------------------------------------------------
# Hardware helpers
# ---------------------------------------------------------------------------


def open_scope():
    """Open PicoScope and configure Ch A."""
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, 1, 1, RANGE_INDEX)
    return handle, ps2000


def capture_block(handle, ps2000):
    """Capture 2048 samples and return mV array."""
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


def set_awg_builtin(handle, ps2000, freq_hz: float, uvpp: int = AWG_SINGLE_UVPP):
    """Set AWG to built-in sine wave at specified frequency and amplitude."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, uvpp, 0,
        float(freq_hz), float(freq_hz), 0, 0, 0, 0
    )


def stop_awg(handle, ps2000):
    """Turn off AWG."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0, 0, 0, 0
    )


def set_awg_arbitrary(handle, waveform: np.ndarray, delta_phase: int,
                      uvpp: int = AWG_DUAL_UVPP):
    """Load arbitrary waveform into AWG and start DDS playback.

    Args:
        handle: PicoScope handle
        waveform: uint8 numpy array (0-255), length <= 4096
        delta_phase: DDS phase increment per DAC clock tick
        uvpp: peak-to-peak amplitude in µV
    """
    lib = ct.CDLL(DYLIB_PATH)

    # Create ctypes buffer from numpy array
    buf_len = len(waveform)
    c_buf = (ct.c_ubyte * buf_len)(*waveform.tolist())

    ret = lib.ps2000_set_sig_gen_arbitrary(
        ct.c_int16(handle),
        ct.c_int32(0),                  # offsetVoltage (µV)
        ct.c_uint32(uvpp),              # pkToPk (µV)
        ct.c_uint32(delta_phase),       # startDeltaPhase
        ct.c_uint32(delta_phase),       # stopDeltaPhase (same = fixed freq)
        ct.c_uint32(0),                 # deltaPhaseIncrement (0 = no sweep)
        ct.c_uint32(0),                 # dwellCount (0 = no sweep)
        ct.byref(c_buf),               # arbitraryWaveform
        ct.c_int32(buf_len),            # arbitraryWaveformSize
        ct.c_int32(0),                  # sweepType (UP, irrelevant)
        ct.c_uint32(0),                 # sweeps (0 = continuous)
    )

    if ret == 0:
        raise RuntimeError(f"ps2000_set_sig_gen_arbitrary failed (ret={ret})")
    return ret


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


def run_arb_intermod(pair_params: list[dict], n_avg: int, relay_ch: int):
    """Run the arbitrary-waveform dual-tone intermodulation experiment."""
    handle, ps2000 = open_scope()
    mux = RelayMux()
    mux.open()
    mux.select(relay_ch)
    time.sleep(0.2)

    nfft = N_SAMPLES * N_FFT_PAD
    bin_hz = SAMPLE_RATE_HZ / nfft

    print(f"\n{'='*70}")
    print("T2.2c — Intermodulation via Arbitrary Waveform Dual-Tone")
    print(f"{'='*70}")
    print(f"  Pairs: {[(p['f1'], p['f2']) for p in pair_params]}")
    print(f"  Averages: {n_avg}")
    print(f"  AWG arbitrary: 1 Vpp total (0.5 Vpp/tone) → Board D (×3.69) → PZT")
    print(f"  Single-tone baseline: 0.5 Vpp → Board D (×3.69) → PZT")
    print(f"  Both tones at EQUAL amplitude through SAME analog path")
    print(f"  FFT: {N_SAMPLES}×{N_FFT_PAD} zero-pad, bin = {bin_hz:.2f} Hz")
    print(f"  Buffer: {AWG_BUF_SIZE} samples, DAC clock: {AWG_DAC_CLOCK/1e6:.0f} MS/s")
    print(f"{'='*70}")

    # Print frequency accuracy table
    print(f"\n  Frequency accuracy (arbitrary waveform DDS):")
    print(f"  {'Pair':>20s}  {'n1':>4s}  {'n2':>4s}  {'f1_err':>8s}  {'f2_err':>8s}  {'spc1':>5s}  {'spc2':>5s}")
    for p in pair_params:
        f1a, f2a = compute_actual_freqs(p["f1"], p["n1"], p["n2"])
        spc1 = AWG_BUF_SIZE / p["n1"]
        spc2 = AWG_BUF_SIZE / p["n2"]
        print(f"  ({p['f1']}, {p['f2']})"
              f"  {p['n1']:>4d}  {p['n2']:>4d}"
              f"  {abs(p['f1']-f1a):>7.2f}  {abs(p['f2']-f2a):>7.2f}"
              f"  {spc1:>5.1f}  {spc2:>5.1f}")

    # Noise floor measurement
    print(f"\n  Measuring noise floor (all off)...", end=" ", flush=True)
    stop_awg(handle, ps2000)
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

    for pair_idx, pp in enumerate(pair_params):
        f1, f2 = pp["f1"], pp["f2"]
        n1, n2 = pp["n1"], pp["n2"]

        f1_actual, f2_actual = compute_actual_freqs(f1, n1, n2)
        delta_phase = compute_delta_phase(f1, n1)
        im_freqs = get_im_frequencies(f1_actual, f2_actual)

        print(f"\n  {'─'*66}")
        print(f"  Pair {pair_idx+1}: f1={f1/1000:.1f}k (n1={n1}) + f2={f2/1000:.1f}k (n2={n2})")
        print(f"  Actual: f1={f1_actual:.1f} Hz, f2={f2_actual:.1f} Hz")
        print(f"  IM targets: {', '.join(f'{l}={v/1000:.1f}k' for l, v in im_freqs.items())}")
        print(f"  {'─'*66}")

        # Generate dual-tone buffer
        waveform = generate_dual_tone_buffer(n1, n2)

        # --- 4 conditions ---
        conditions = ["DUAL", "F1_ONLY", "F2_ONLY", "SILENCE"]
        condition_data = {}

        for cond in conditions:
            # Set excitation
            if cond == "DUAL":
                set_awg_arbitrary(handle, waveform, delta_phase, AWG_DUAL_UVPP)
            elif cond == "F1_ONLY":
                set_awg_builtin(handle, ps2000, f1_actual, AWG_SINGLE_UVPP)
            elif cond == "F2_ONLY":
                set_awg_builtin(handle, ps2000, f2_actual, AWG_SINGLE_UVPP)
            else:  # SILENCE
                stop_awg(handle, ps2000)
            time.sleep(SETTLE_S)

            # Capture n_avg
            mags_at_bins = {label: [] for label in im_freqs}
            mags_at_bins["f1"] = []
            mags_at_bins["f2"] = []

            for _ in range(n_avg):
                mv = capture_block(handle, ps2000)
                fft_mag, _ = compute_fft(mv)
                mags_at_bins["f1"].append(measure_at_bin(fft_mag, f1_actual, bin_hz))
                mags_at_bins["f2"].append(measure_at_bin(fft_mag, f2_actual, bin_hz))
                for label, freq in im_freqs.items():
                    mags_at_bins[label].append(measure_at_bin(fft_mag, freq, bin_hz))

            condition_data[cond] = {
                k: {"mean": float(np.mean(v)), "std": float(np.std(v))}
                for k, v in mags_at_bins.items()
            }

        # --- Analysis ---
        print(f"\n    {'Bin':>12s}  {'DUAL':>9s}  {'F1only':>9s}  {'F2only':>9s}  "
              f"{'Silence':>9s}  {'Excess':>7s}  {'σ':>5s}")
        print(f"    {'─'*12}  {'─'*9}  {'─'*9}  {'─'*9}  {'─'*9}  {'─'*7}  {'─'*5}")

        pair_result = {"f1_hz": f1, "f2_hz": f2, "n1": n1, "n2": n2,
                       "f1_actual": f1_actual, "f2_actual": f2_actual,
                       "delta_phase": delta_phase, "im_bins": {}}

        # Show carrier levels
        for label in ["f1", "f2"]:
            d = condition_data["DUAL"][label]["mean"]
            f1o = condition_data["F1_ONLY"][label]["mean"]
            f2o = condition_data["F2_ONLY"][label]["mean"]
            sil = condition_data["SILENCE"][label]["mean"]
            print(f"    {label:>12s}  {d:>9.0f}  {f1o:>9.0f}  "
                  f"{f2o:>9.0f}  {sil:>9.0f}  {'—':>7s}  {'—':>5s}")

        # IM products
        for label in im_freqs:
            dual_m = condition_data["DUAL"][label]["mean"]
            dual_s = condition_data["DUAL"][label]["std"]
            f1o_m = condition_data["F1_ONLY"][label]["mean"]
            f1o_s = condition_data["F1_ONLY"][label]["std"]
            f2o_m = condition_data["F2_ONLY"][label]["mean"]
            sil_m = condition_data["SILENCE"][label]["mean"]

            # Baseline = max of single-tone conditions
            baseline = max(f1o_m, f2o_m, sil_m)
            excess_pct = (dual_m - baseline) / baseline * 100 if baseline > 0 else 0

            # Significance: DUAL vs max single-tone
            # Use F1_ONLY as primary baseline (stronger signal, more harmonics)
            pooled_std = np.sqrt((dual_s**2 + f1o_s**2) / 2)
            sigma = (dual_m - f1o_m) / pooled_std if pooled_std > 0 else 0

            max_im_excess = max(max_im_excess, abs(excess_pct))
            max_im_sigma = max(max_im_sigma, abs(sigma))

            print(f"    {label:>12s}  {dual_m:>9.0f}  {f1o_m:>9.0f}  "
                  f"{f2o_m:>9.0f}  {sil_m:>9.0f}  {excess_pct:>+6.1f}%  "
                  f"{sigma:>+4.1f}σ")

            pair_result["im_bins"][label] = {
                "freq_hz": im_freqs[label],
                "dual_mean": dual_m, "dual_std": dual_s,
                "f1only_mean": f1o_m, "f1only_std": f1o_s,
                "f2only_mean": f2o_m,
                "silence_mean": sil_m,
                "excess_pct": excess_pct,
                "sigma_vs_f1only": float(sigma),
            }

        pair_result["carriers"] = {
            "f1_dual": condition_data["DUAL"]["f1"]["mean"],
            "f1_f1only": condition_data["F1_ONLY"]["f1"]["mean"],
            "f2_dual": condition_data["DUAL"]["f2"]["mean"],
            "f2_f2only": condition_data["F2_ONLY"]["f2"]["mean"],
        }
        all_results.append(pair_result)

    # Cleanup
    stop_awg(handle, ps2000)
    mux.off()
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)

    # --- Summary ---
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Method: Arbitrary waveform dual-tone (equal amplitude, same path)")
    print(f"  Max |IM excess| (DUAL vs baseline): {max_im_excess:.1f}%")
    print(f"  Max |σ| (DUAL vs F1-only): {max_im_sigma:.2f}σ")

    if max_im_sigma >= 3.0:
        gate = "PASS"
        print(f"\n  ★ GATE DECISION: PASS (acoustic IM detected at {max_im_sigma:.1f}σ)")
    elif max_im_sigma >= 2.0:
        gate = "MARGINAL"
        print(f"\n  ◆ GATE DECISION: MARGINAL ({max_im_sigma:.1f}σ — suggest more averages)")
    else:
        gate = "FAIL"
        print(f"\n  ✗ GATE DECISION: FAIL (max σ = {max_im_sigma:.2f} — no acoustic IM)")
        print("    Both tones at equal power, same path: plate is linear.")

    # Save results
    out_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "intermodulation"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"t2_2c_arb_dualtone_{ts}.json"

    result_doc = {
        "experiment": "T2.2c_intermod_arb_dualtone",
        "timestamp": datetime.now().isoformat(),
        "plate": "100x100mm_fused_silica",
        "relay_channel": relay_ch,
        "n_averages": n_avg,
        "awg_dual_uvpp": AWG_DUAL_UVPP,
        "awg_single_uvpp": AWG_SINGLE_UVPP,
        "awg_buf_size": AWG_BUF_SIZE,
        "awg_dac_clock": AWG_DAC_CLOCK,
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
        description="T2.2c Intermodulation via Arbitrary Waveform Dual-Tone")
    parser.add_argument("--averages", type=int, default=N_AVG_DEFAULT)
    parser.add_argument("--relay", type=int, default=RELAY_CH)
    args = parser.parse_args()

    run_arb_intermod(
        pair_params=PAIR_PARAMS,
        n_avg=args.averages,
        relay_ch=args.relay,
    )


if __name__ == "__main__":
    main()
