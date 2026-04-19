#!/usr/bin/env python3
"""
Measure Q factors of glass plate modes via ringdown analysis.

Drives a single carrier at full amplitude, then kills the AWG and captures
the ringdown waveform.  Fits an exponential decay envelope to extract Q.

This is the critical measurement that determines whether the plate can
function as a temporal reservoir:
  Q ≥ 200  →  rapid-fire reservoir computing is feasible (100+ Hz step rate)
  Q < 100  →  temporal memory is too short; pivot to spatial computing

Usage:
  DYLD_LIBRARY_PATH="/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources" \
    python tools/measure_q.py --port /dev/cu.usbserial-11310 --plate 4_NE

  # Simulation mode (no hardware):
  python tools/measure_q.py --simulate
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.signal import hilbert, butter, filtfilt

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

ROOT = TOOLS_DIR.parent
RESULTS_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"

# ── Hardware constants ─────────────────────────────────────────────

AWG_DRIVE_UVPP = 2_000_000       # 2 Vpp
ARB_LEN = 4096                    # AWG buffer length

# For Q measurement we want longer capture at moderate sample rate.
# Timebase 7: 1280 ns/sample = 781.25 kHz, 8064 samples = 10.3 ms
# That's fine — mode ringdown at Q=100, f=30kHz decays in ~1ms.
# We'll see the full decay in one capture.
TIMEBASE = 7
DT_NS = 1280
SAMPLE_RATE = int(1e9 / DT_NS)   # 781250 Hz
N_SAMPLES = 8064

# Relay settling
SETTLE_RELAY_S = 0.10
# Steady-state settling before kill — let modes reach full amplitude
STEADY_STATE_S = 0.20

# Test frequencies: our 10 NARMA carriers + a few census modes
CARRIERS_HZ = [
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]

EXTRA_MODES_HZ = [
    11_425, 33_225, 47_800, 68_200, 89_400,
]

# Receiver map (same as narma_ladder.py)
RECEIVER_MAP = {
    "1":    (1, "A-NE"),
    "2":    (2, "B-NE"),
    "3_NE": (3, "G-NE"),
    "4_NE": (5, "D-NE"),
    "5_NE": (7, "H-NE"),
}


def drive_single_tone(handle, freq_hz, amplitude=1.0):
    """Drive one frequency via ARB waveform at specified amplitude."""
    from picosdk.ps2000 import ps2000

    if amplitude <= 0:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
        return

    f_rep = max(10.0, math.ceil(freq_hz / (ARB_LEN // 2 - 10)))
    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    buf = np.zeros(ARB_LEN, dtype=np.float64)
    k = round(freq_hz / f_rep)
    if k >= 1 and k <= ARB_LEN // 2:
        phase = 2 * np.pi * k * np.arange(ARB_LEN) / ARB_LEN
        buf = amplitude * np.sin(phase)

    peak = np.max(np.abs(buf))
    if peak > 0:
        buf /= peak

    arb_u8 = ((buf * 127) + 128).clip(0, 255).astype(np.uint8)
    arb_buf = (ctypes.c_uint8 * ARB_LEN)(*arb_u8.tolist())
    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, AWG_DRIVE_UVPP,
        delta_phase, delta_phase,
        0, 0, arb_buf, ARB_LEN, 0, 0
    )


def kill_awg(handle):
    """Silence the AWG as fast as possible."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)


def capture_raw(handle, n_samples=N_SAMPLES, timebase=TIMEBASE):
    """Capture raw time-domain waveform."""
    from picosdk.ps2000 import ps2000

    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, n_samples, timebase, 1, ctypes.byref(t_ms))

    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 5:
            break

    buf_a = (ctypes.c_int16 * n_samples)()
    buf_b = (ctypes.c_int16 * n_samples)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), n_samples)

    if n <= 0:
        return np.zeros(n_samples)
    return np.array(buf_a[:n], dtype=np.float64)


def measure_ringdown(handle, freq_hz, n_captures=3):
    """Drive a tone to steady-state, kill AWG, capture ringdown.

    Strategy:
      1. Drive the tone for STEADY_STATE_S to let mode fully ring up
      2. Start a capture (10.3 ms window at 781 kHz)
      3. Immediately kill the AWG (~1-2 ms latency)
      4. The capture contains: ~1-2 ms of driven signal + ~8 ms of ringdown

    We repeat n_captures times and return all waveforms.
    """
    waveforms = []
    for _ in range(n_captures):
        # Drive to steady state
        drive_single_tone(handle, freq_hz, amplitude=1.0)
        time.sleep(STEADY_STATE_S)

        # Start capture AND kill AWG as fast as possible
        # The capture runs for 10.3ms total
        # Python command latency between these two calls is ~0.5-2ms
        raw = capture_with_kill(handle, freq_hz)
        waveforms.append(raw)

        # Brief silence before next measurement
        time.sleep(0.05)

    return waveforms


def capture_with_kill(handle, freq_hz):
    """Start capture, then immediately kill AWG. Return raw waveform.

    The waveform will contain:
      - First ~1-3 ms: driven steady-state signal
      - Remaining ~7-9 ms: free ringdown (decaying oscillation)
    """
    from picosdk.ps2000 import ps2000

    # Arm the capture
    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))

    # Small delay to ensure capture is running
    time.sleep(0.001)

    # KILL the AWG — the tone dies, modes ring down
    kill_awg(handle)

    # Wait for capture to complete
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 5:
            break

    # Read the waveform
    buf_a = (ctypes.c_int16 * N_SAMPLES)()
    buf_b = (ctypes.c_int16 * N_SAMPLES)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), N_SAMPLES)

    if n <= 0:
        return np.zeros(N_SAMPLES)
    return np.array(buf_a[:n], dtype=np.float64)


def analyze_ringdown(waveform, freq_hz, sample_rate=SAMPLE_RATE):
    """Extract Q factor from a ringdown waveform.

    1. Bandpass filter around the target frequency
    2. Compute analytic signal (Hilbert transform) → amplitude envelope
    3. Find the kill point (where envelope starts decaying)
    4. Fit exponential decay to the envelope after kill point
    5. Q = π × f × τ_decay
    """
    dt = 1.0 / sample_rate
    n = len(waveform)
    t = np.arange(n) * dt

    # Bandpass filter: ±20% around target frequency
    bw_frac = 0.20
    f_lo = max(100, freq_hz * (1 - bw_frac))
    f_hi = min(sample_rate / 2 - 100, freq_hz * (1 + bw_frac))
    nyq = sample_rate / 2
    b, a = butter(4, [f_lo / nyq, f_hi / nyq], btype='band')
    filtered = filtfilt(b, a, waveform)

    # Compute amplitude envelope via Hilbert transform
    analytic = hilbert(filtered)
    envelope = np.abs(analytic)

    # Smooth envelope with a moving average (window = ~2 cycles)
    cycle_samples = max(5, int(2 * sample_rate / freq_hz))
    kernel = np.ones(cycle_samples) / cycle_samples
    env_smooth = np.convolve(envelope, kernel, mode='same')

    # Find the kill point: largest drop in smoothed envelope
    # The drive stops ~1-3 ms into the capture
    # Look for where the envelope reaches its peak and starts decaying
    peak_idx = np.argmax(env_smooth[:len(env_smooth)//2])

    # Find the start of decay: first point after peak where envelope
    # drops below 90% of peak, then backtrack to 95%
    peak_val = env_smooth[peak_idx]
    if peak_val < 1:
        return {"freq_hz": freq_hz, "Q": 0, "tau_ms": 0,
                "peak_amplitude": 0, "error": "no signal"}

    # Find decay start: walk forward from peak until consistent decrease
    decay_start = peak_idx
    for i in range(peak_idx, min(peak_idx + cycle_samples * 5, n - 1)):
        if env_smooth[i] < 0.85 * peak_val:
            # Backtrack a bit to catch the start
            decay_start = max(peak_idx, i - cycle_samples)
            break

    # Find decay end: where envelope drops below 5% of peak or noise floor
    noise_floor = np.median(env_smooth[-cycle_samples*3:]) if n > cycle_samples*3 else 0
    threshold = max(0.03 * peak_val, 2 * noise_floor)
    decay_end = n - 1
    for i in range(decay_start, n):
        if env_smooth[i] < threshold:
            decay_end = i
            break

    # Need at least a few cycles of decay for a good fit
    min_decay_samples = cycle_samples * 2
    if decay_end - decay_start < min_decay_samples:
        return {"freq_hz": freq_hz, "Q": 0, "tau_ms": 0,
                "peak_amplitude": float(peak_val),
                "decay_start_ms": decay_start * dt * 1000,
                "error": "decay too short"}

    # Fit exponential: log(envelope) = log(A) - t/τ
    t_decay = t[decay_start:decay_end] - t[decay_start]
    env_decay = env_smooth[decay_start:decay_end]

    # Remove zero/negative values for log fit
    valid = env_decay > 0
    if np.sum(valid) < 10:
        return {"freq_hz": freq_hz, "Q": 0, "tau_ms": 0,
                "peak_amplitude": float(peak_val),
                "error": "insufficient valid points"}

    log_env = np.log(env_decay[valid])
    t_valid = t_decay[valid]

    # Linear regression: log(env) = a - t/τ → slope = -1/τ
    coeffs = np.polyfit(t_valid, log_env, 1)
    slope = coeffs[0]  # should be negative

    if slope >= 0:
        return {"freq_hz": freq_hz, "Q": 0, "tau_ms": 0,
                "peak_amplitude": float(peak_val),
                "slope": float(slope),
                "error": "positive slope (no decay)"}

    tau = -1.0 / slope  # decay time constant in seconds
    Q = np.pi * freq_hz * tau

    # R² of the fit
    predicted = coeffs[0] * t_valid + coeffs[1]
    ss_res = np.sum((log_env - predicted) ** 2)
    ss_tot = np.sum((log_env - np.mean(log_env)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return {
        "freq_hz": freq_hz,
        "Q": float(Q),
        "tau_ms": float(tau * 1000),
        "peak_amplitude": float(peak_val),
        "decay_start_ms": float(decay_start * dt * 1000),
        "decay_end_ms": float(decay_end * dt * 1000),
        "decay_samples": int(decay_end - decay_start),
        "r_squared": float(r_squared),
        "slope": float(slope),
    }


def simulate_ringdown(freq_hz, Q=150, amplitude=1000, sample_rate=SAMPLE_RATE,
                       n_samples=N_SAMPLES, kill_sample=1500):
    """Simulate a ringdown waveform for testing the analysis."""
    dt = 1.0 / sample_rate
    t = np.arange(n_samples) * dt
    tau = Q / (np.pi * freq_hz)

    waveform = np.zeros(n_samples)
    # Before kill: steady-state driven oscillation
    waveform[:kill_sample] = amplitude * np.sin(2 * np.pi * freq_hz * t[:kill_sample])
    # After kill: exponential decay
    t_after = t[kill_sample:] - t[kill_sample]
    waveform[kill_sample:] = amplitude * np.exp(-t_after / tau) * \
        np.sin(2 * np.pi * freq_hz * t[kill_sample:])

    # Add noise
    noise = np.random.randn(n_samples) * amplitude * 0.02
    waveform += noise

    return waveform


def measure_q_bandwidth(handle, freq_hz, sample_rate=SAMPLE_RATE,
                         n_samples=N_SAMPLES, n_steps=21, max_bw_hz=5000):
    """Measure Q via frequency response bandwidth.

    Sweep the drive frequency around freq_hz and measure the response
    magnitude at the receiver.  Fit a Lorentzian to find the -3dB width.

    Q = f₀ / FWHM

    This is much more robust than ringdown because:
      - No timing issues (steady-state measurement at each frequency)
      - Works for any Q value
      - Uses existing FFT magnitude measurement
    """
    from picosdk.ps2000 import ps2000

    # Sweep range: start wide, will narrow if needed
    half_bw = max_bw_hz
    freqs_sweep = np.linspace(freq_hz - half_bw, freq_hz + half_bw, n_steps)

    mags = []
    for f_drive in freqs_sweep:
        if f_drive < 500:
            mags.append(0)
            continue
        drive_single_tone(handle, f_drive, amplitude=1.0)
        time.sleep(0.08)  # shorter settle for speed

        # Capture FFT magnitude at the DRIVE frequency
        mag = _capture_magnitude_at(handle, f_drive, sample_rate, n_samples)
        mags.append(mag)

    mags = np.array(mags)

    # Also capture the noise floor magnitude
    kill_awg(handle)
    time.sleep(0.08)
    noise_mag = _capture_magnitude_at(handle, freq_hz, sample_rate, n_samples)

    return _fit_lorentzian(freqs_sweep, mags, freq_hz, noise_mag)


def _capture_magnitude_at(handle, freq_hz, sample_rate, n_samples):
    """Capture and return FFT magnitude at a specific frequency."""
    from picosdk.ps2000 import ps2000

    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, n_samples, TIMEBASE, 1, ctypes.byref(t_ms))

    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 5:
            break

    buf_a = (ctypes.c_int16 * n_samples)()
    buf_b = (ctypes.c_int16 * n_samples)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), n_samples)

    if n <= 0:
        return 0.0

    raw = np.array(buf_a[:n], dtype=np.float64)
    windowed = raw * np.hanning(len(raw))
    nfft = len(raw) * 4
    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
    bin_hz = freq_axis[1] - freq_axis[0]

    target_bin = int(round(freq_hz / bin_hz))
    lo = max(0, target_bin - 3)
    hi = min(len(fft_mag) - 1, target_bin + 3)
    return float(np.max(fft_mag[lo:hi + 1]))


def _fit_lorentzian(freqs, mags, f_center, noise_mag):
    """Fit a Lorentzian to the frequency response and extract Q."""
    mags = np.array(mags, dtype=float)
    peak_idx = np.argmax(mags)
    peak_mag = mags[peak_idx]
    peak_freq = freqs[peak_idx]

    if peak_mag < 2 * noise_mag or peak_mag < 1000:
        return {"freq_hz": f_center, "Q": 0, "tau_ms": 0,
                "error": "no clear peak above noise"}

    # Find -3dB points (magnitude drops to peak/√2 = 0.707×peak)
    half_power = peak_mag / np.sqrt(2)

    # Search left of peak
    f_lo = freqs[0]
    for i in range(peak_idx, -1, -1):
        if mags[i] < half_power:
            # Linear interpolation
            if i < peak_idx:
                frac = (half_power - mags[i]) / (mags[i + 1] - mags[i]) if mags[i + 1] != mags[i] else 0
                f_lo = freqs[i] + frac * (freqs[i + 1] - freqs[i])
            break

    # Search right of peak
    f_hi = freqs[-1]
    for i in range(peak_idx, len(freqs)):
        if mags[i] < half_power:
            if i > peak_idx:
                frac = (half_power - mags[i]) / (mags[i - 1] - mags[i]) if mags[i - 1] != mags[i] else 0
                f_hi = freqs[i] - frac * (freqs[i] - freqs[i - 1])
            break

    fwhm = f_hi - f_lo
    if fwhm <= 0:
        return {"freq_hz": f_center, "Q": 0, "tau_ms": 0,
                "peak_freq": float(peak_freq), "peak_mag": float(peak_mag),
                "error": "could not find FWHM (peak at edge of sweep?)"}

    Q = peak_freq / fwhm
    tau = Q / (np.pi * peak_freq)

    return {
        "freq_hz": f_center,
        "peak_freq": float(peak_freq),
        "Q": float(Q),
        "tau_ms": float(tau * 1000),
        "fwhm_hz": float(fwhm),
        "peak_mag": float(peak_mag),
        "noise_mag": float(noise_mag),
        "snr": float(peak_mag / noise_mag) if noise_mag > 0 else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Measure plate mode Q factors")
    parser.add_argument("--port", help="Arduino serial port for relay MUX")
    parser.add_argument("--plate", default="4_NE",
                        help="Plate key (default: 4_NE)")
    parser.add_argument("--simulate", action="store_true",
                        help="Run with simulated data")
    parser.add_argument("--captures", type=int, default=3,
                        help="Number of ringdown captures per frequency")
    parser.add_argument("--extra", action="store_true",
                        help="Also measure extra (non-carrier) modes")
    parser.add_argument("--method", default="both", choices=["ringdown", "bandwidth", "both"],
                        help="Measurement method (default: both)")
    args = parser.parse_args()

    freqs = list(CARRIERS_HZ)
    if args.extra:
        freqs.extend(EXTRA_MODES_HZ)
    freqs.sort()

    print("══════════════════════════════════════════════════════════════")
    print("  MODE Q-FACTOR MEASUREMENT — Ringdown Analysis")
    print("══════════════════════════════════════════════════════════════")
    print()
    print(f"  Plate: {args.plate}")
    print(f"  Frequencies: {len(freqs)}")
    print(f"  Captures per freq: {args.captures}")
    print(f"  Sample rate: {SAMPLE_RATE/1e6:.3f} MHz ({N_SAMPLES} samples = {N_SAMPLES/SAMPLE_RATE*1000:.1f} ms)")
    print()

    results = []

    if args.simulate:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  SIMULATION MODE")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        np.random.seed(42)

        for freq_hz in freqs:
            # Simulate with varying Q (increases with frequency — typical for glass)
            sim_Q = 80 + (freq_hz / 1000) * 3  # Q ~ 80-260 range
            all_results = []
            for cap in range(args.captures):
                wf = simulate_ringdown(freq_hz, Q=sim_Q,
                                       kill_sample=int(1.5e-3 * SAMPLE_RATE))
                r = analyze_ringdown(wf, freq_hz)
                all_results.append(r)

            # Average Q across captures
            Qs = [r["Q"] for r in all_results if r["Q"] > 0]
            avg_Q = np.mean(Qs) if Qs else 0
            std_Q = np.std(Qs) if len(Qs) > 1 else 0
            r2s = [r.get("r_squared", 0) for r in all_results if r["Q"] > 0]
            avg_r2 = np.mean(r2s) if r2s else 0

            result = {
                "freq_hz": freq_hz,
                "Q_mean": float(avg_Q),
                "Q_std": float(std_Q),
                "Q_true": float(sim_Q),
                "tau_ms": float(avg_Q / (np.pi * freq_hz) * 1000) if avg_Q > 0 else 0,
                "r_squared": float(avg_r2),
                "n_good": len(Qs),
            }
            results.append(result)

    else:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  HARDWARE MEASUREMENT")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        from picosdk.ps2000 import ps2000
        from relay_mux import RelayMux

        handle = ps2000.ps2000_open_unit()
        if handle <= 0:
            raise RuntimeError(f"ps2000_open_unit failed ({handle})")

        ps2000.ps2000_set_channel(handle, 0, True, 1, 6)  # Ch A, DC, ±1V
        ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
        print("  PicoScope opened")

        mux = RelayMux(args.port)
        mux.open()
        time.sleep(0.5)

        relay_ch, rx_name = RECEIVER_MAP[args.plate]
        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)
        print(f"  MUX → relay {relay_ch} ({rx_name})")
        print()

        try:
            if args.method in ("ringdown", "both"):
                print("  ── Ringdown method ──")
                for freq_hz in freqs:
                    print(f"  Measuring {freq_hz/1000:.1f} kHz ... ", end="", flush=True)
                    all_results = []

                    for cap in range(args.captures):
                        drive_single_tone(handle, freq_hz, amplitude=1.0)
                        time.sleep(STEADY_STATE_S)
                        wf = capture_with_kill(handle, freq_hz)
                        r = analyze_ringdown(wf, freq_hz)
                        all_results.append(r)
                        time.sleep(0.05)

                    Qs = [r["Q"] for r in all_results if r["Q"] > 0]
                    avg_Q = np.mean(Qs) if Qs else 0
                    std_Q = np.std(Qs) if len(Qs) > 1 else 0
                    r2s = [r.get("r_squared", 0) for r in all_results if r["Q"] > 0]
                    avg_r2 = np.mean(r2s) if r2s else 0

                    result = {
                        "freq_hz": freq_hz,
                        "method": "ringdown",
                        "Q_mean": float(avg_Q),
                        "Q_std": float(std_Q),
                        "tau_ms": float(avg_Q / (np.pi * freq_hz) * 1000) if avg_Q > 0 else 0,
                        "r_squared": float(avg_r2),
                        "n_good": len(Qs),
                    }
                    results.append(result)

                    if avg_Q > 0:
                        tau_ms = avg_Q / (np.pi * freq_hz) * 1000
                        print(f"Q = {avg_Q:.0f} ± {std_Q:.0f}  τ = {tau_ms:.2f} ms  R² = {avg_r2:.3f}")
                    else:
                        errors = [r.get("error", "unknown") for r in all_results]
                        print(f"FAILED ({errors[0]})")
                print()

            if args.method in ("bandwidth", "both"):
                print("  ── Bandwidth method (frequency sweep) ──")
                for freq_hz in freqs:
                    print(f"  Sweeping {freq_hz/1000:.1f} kHz ± 5 kHz ... ", end="", flush=True)

                    r = measure_q_bandwidth(handle, freq_hz)
                    r["method"] = "bandwidth"
                    results.append(r)

                    if r["Q"] > 0:
                        print(f"Q = {r['Q']:.0f}  τ = {r['tau_ms']:.3f} ms  FWHM = {r['fwhm_hz']:.0f} Hz  SNR = {r['snr']:.0f}×")
                    else:
                        print(f"FAILED ({r.get('error', 'unknown')})")
                print()

        finally:
            # Silence AWG
            try:
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
            except Exception:
                pass
            mux.close()
            ps2000.ps2000_stop(handle)
            ps2000.ps2000_close_unit(handle)
            print("\n  PicoScope closed")

    # ── Print summary ────────────────────────────────────────────────

    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Q-FACTOR RESULTS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Group by method
    for method_name in ["ringdown", "bandwidth"]:
        method_results = [r for r in results if r.get("method") == method_name]
        if not method_results:
            continue

        print(f"\n  Method: {method_name}")
        print(f"  {'Freq (kHz)':>10s}  {'Q':>8s}  {'± σ':>6s}  {'τ (ms)':>8s}  {'Max rate':>10s}")
        print(f"  {'─'*10}  {'─'*8}  {'─'*6}  {'─'*8}  {'─'*10}")

        for r in method_results:
            f_khz = r["freq_hz"] / 1000
            Q = r.get("Q_mean", r.get("Q", 0))
            std = r.get("Q_std", 0)
            tau = r.get("tau_ms", 0)

            if Q > 0:
                tau_s = Q / (np.pi * r["freq_hz"])
                max_rate = 1.0 / (2.3 * tau_s)
                rate_str = f"{max_rate:.0f} Hz"
            else:
                rate_str = "N/A"

            q_true = r.get("Q_true", "")
            true_str = f"  (true={q_true:.0f})" if q_true else ""
            extra = ""
            if "fwhm_hz" in r:
                extra = f"  FWHM={r['fwhm_hz']:.0f}Hz"
            print(f"  {f_khz:10.1f}  {Q:8.0f}  {std:6.0f}  {tau:8.3f}  {rate_str:>10s}{true_str}{extra}")

    # Overall summary — use bandwidth results if available, else ringdown
    bw_results = [r for r in results if r.get("method") == "bandwidth"]
    rd_results = [r for r in results if r.get("method") == "ringdown"]
    best_results = bw_results if bw_results else rd_results

    good_qs = []
    for r in best_results:
        Q = r.get("Q_mean", r.get("Q", 0))
        if Q > 0:
            good_qs.append(Q)

    print()

    if good_qs:
        median_Q = np.median(good_qs)
        min_Q = np.min(good_qs)
        max_Q = np.max(good_qs)

        # Representative decay time at 35 kHz
        repr_tau = median_Q / (np.pi * 35000) * 1000
        repr_rate = 1.0 / (2.3 * median_Q / (np.pi * 35000))

        print(f"  Summary: Q = {min_Q:.0f} – {max_Q:.0f} (median {median_Q:.0f})")
        print(f"  Representative τ at 35 kHz: {repr_tau:.2f} ms")
        print(f"  Max step rate for temporal reservoir: {repr_rate:.0f} Hz")
        print()

        if median_Q >= 200:
            print("  ★ Q ≥ 200 → TEMPORAL RESERVOIR IS FEASIBLE!")
            print(f"    Step rate up to {repr_rate:.0f} Hz ({1000/repr_rate:.1f} ms/step)")
            print("    Mode memory spans 2-5 steps → genuine temporal computation")
            print("    → Implement rapid-fire NARMA-10 with time-domain features")
        elif median_Q >= 100:
            print("  ◉ Q = 100-200 → MARGINAL temporal reservoir")
            print(f"    Step rate up to {repr_rate:.0f} Hz ({1000/repr_rate:.1f} ms/step)")
            print("    Mode memory spans ~1-2 steps → limited but useful")
            print("    → Try rapid-fire capture with careful timing")
        else:
            print("  ○ Q < 100 → Temporal reservoir NOT feasible at plate frequencies")
            print("    Mode energy decays too fast between steps")
            print("    → Pivot to spatial computing / multi-receiver approach")
    else:
        print("  WARNING: No valid Q measurements!")

    # ── Save results ────────────────────────────────────────────────

    outfile = RESULTS_DIR / f"q_factors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "q_factor_ringdown",
        "mode": "simulation" if args.simulate else "hardware",
        "plate": args.plate,
        "sample_rate": SAMPLE_RATE,
        "n_samples": N_SAMPLES,
        "captures_per_freq": args.captures,
        "results": [{k: v for k, v in r.items() if k != "raw_results"} for r in results],
    }
    outfile.write_text(json.dumps(save_data, indent=2))
    print(f"\n  Saved: {outfile.name}")
    print()

    print("══════════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
