#!/usr/bin/env python3
"""
Temporal reservoir proof-of-concept using external AD9833 DDS.

Proves that plate modes retain energy between capture steps when
the DDS-to-PicoScope bottleneck is eliminated.

Protocol:
  1. AD9833 drives plate at resonant frequency (external DDS — no firmware stall)
  2. PicoScope captures at maximum rate (capture-only, ~431 Hz / 2.3 ms per step)
  3. Binary ON/OFF pattern: alternate between resonance (ON) and off-resonance (OFF)
  4. Measure residual energy at the ON frequency during OFF steps
  5. Compare ordered vs shuffled sequences (temporal memory = order matters)

Expected result at 431 Hz with Q=218 (29.9 kHz), τ=1.99 ms:
  retention = exp(-2.3/1.99) = 31.6% per step

Usage:
  source .venv/bin/activate
  DYLD_LIBRARY_PATH="/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources" \\
    python -u tools/temporal_proof.py /dev/cu.usbserial-11310
"""

import argparse
import ctypes
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from picosdk.ps2000 import ps2000

# ─── Capture parameters ───
TIMEBASE = 7           # 1280 ns/sample → 781.25 kHz
N_SAMPLES = 256        # Minimum for fast capture (~0.33 ms window)
N_STEPS = 500          # Total ON/OFF steps
N_AVG = 1             # No averaging — speed is everything
READY_TIMEOUT_S = 2.0

# ─── Target frequencies ───
FREQ_ON = 29925        # Best Q mode on plate D (Q=218, τ=1.99ms)
FREQ_OFF = 1000        # Far off-resonance (no plate mode here)
RELAY_PLATE_D_NE = 5   # Relay 5 = Plate D NE receiver


def wait_ready(handle, timeout_s=READY_TIMEOUT_S):
    """Poll ps2000_ready with timeout."""
    t0 = time.perf_counter()
    while ps2000.ps2000_ready(handle) == 0:
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError("ps2000_ready timed out")
    return time.perf_counter() - t0


def capture_only(handle, buf_a, buf_b, overflow, t_ms):
    """Capture N_SAMPLES without touching the DDS. Returns raw int16 array."""
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
    wait_ready(handle)
    ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), N_SAMPLES
    )
    return np.array(buf_a[:N_SAMPLES], dtype=np.float64)


def extract_magnitude(raw, freq_hz, sample_rate=781250.0):
    """Extract magnitude at target frequency via FFT."""
    n = len(raw)
    nfft = max(n, 1024)  # Zero-pad for better resolution
    spectrum = np.abs(np.fft.rfft(raw, n=nfft))
    freqs = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
    # Find nearest bin
    idx = np.argmin(np.abs(freqs - freq_hz))
    # Take max of ±3 bins to handle slight frequency drift
    lo = max(0, idx - 3)
    hi = min(len(spectrum), idx + 4)
    return float(np.max(spectrum[lo:hi]))


def main():
    parser = argparse.ArgumentParser(description="Temporal reservoir proof-of-concept")
    parser.add_argument("port", help="Arduino serial port (e.g., /dev/cu.usbserial-11310)")
    parser.add_argument("--relay", type=int, default=RELAY_PLATE_D_NE,
                        help=f"Relay number for RX (default: {RELAY_PLATE_D_NE})")
    parser.add_argument("--freq-on", type=int, default=FREQ_ON,
                        help=f"Resonant frequency Hz (default: {FREQ_ON})")
    parser.add_argument("--steps", type=int, default=N_STEPS,
                        help=f"Total steps (default: {N_STEPS})")
    parser.add_argument("--pattern", choices=["alternating", "random", "burst"],
                        default="alternating",
                        help="ON/OFF pattern type")
    args = parser.parse_args()

    import serial as pyserial
    from dds_ad9833 import DDS

    # ─── Open Arduino (relay + DDS) ───
    print(f"Opening Arduino on {args.port}...")
    ser = pyserial.Serial(args.port, baudrate=9600, timeout=1.0)
    time.sleep(2.5)  # Wait for Arduino boot
    ser.reset_input_buffer()
    dds = DDS(ser)

    # Select relay
    ser.write(f"{args.relay}\n".encode())
    time.sleep(0.1)
    resp = ser.readline().decode().strip()
    print(f"  Relay: {resp}")

    # ─── Open PicoScope (capture only) ───
    print("Opening PicoScope...")
    handle = ps2000.ps2000_open_unit()
    assert handle > 0, f"PicoScope open failed: {handle}"

    # Silence PicoScope AWG (we're using AD9833 instead)
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)

    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A enabled
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B disabled
    ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)    # No trigger

    buf_a = (ctypes.c_int16 * N_SAMPLES)()
    buf_b = (ctypes.c_int16 * N_SAMPLES)()
    overflow = ctypes.c_int16()
    t_ms = ctypes.c_int32()

    # ─── Generate ON/OFF pattern ───
    n_steps = args.steps
    if args.pattern == "alternating":
        pattern = np.array([i % 2 for i in range(n_steps)], dtype=int)
    elif args.pattern == "random":
        rng = np.random.default_rng(42)
        pattern = rng.integers(0, 2, size=n_steps)
    elif args.pattern == "burst":
        # 5 ON, 5 OFF, repeat — shows multi-step decay
        pattern = np.array([(i // 5) % 2 for i in range(n_steps)], dtype=int)

    print(f"\n{'='*60}")
    print(f"Temporal Reservoir Proof — {n_steps} steps")
    print(f"  DDS freq ON:  {args.freq_on} Hz")
    print(f"  DDS freq OFF: {FREQ_OFF} Hz")
    print(f"  Pattern:      {args.pattern}")
    print(f"  Expected retention: {100*np.exp(-2.3/1.99):.1f}% per step (Q=218)")
    print(f"{'='*60}\n")

    # ─── Warm up: verify DDS works ───
    confirmed = dds.set_freq(args.freq_on)
    print(f"  DDS warm-up: set {args.freq_on} Hz → confirmed {confirmed} Hz")
    time.sleep(0.2)

    # Capture one frame to verify signal
    raw = capture_only(handle, buf_a, buf_b, overflow, t_ms)
    mag = extract_magnitude(raw, args.freq_on)
    print(f"  Warm-up capture: magnitude at {args.freq_on} Hz = {mag:.0f}")
    if mag < 100:
        print("  WARNING: Very low signal. Check wiring: AD9833 OUT → relay COM input")

    dds.off()
    time.sleep(0.1)

    # ─── Main capture loop ───
    magnitudes = np.zeros(n_steps)
    step_times = np.zeros(n_steps)
    dds_times = np.zeros(n_steps)

    print(f"\nCapturing {n_steps} steps...")
    t_start = time.perf_counter()

    for i in range(n_steps):
        t0 = time.perf_counter()

        # Set DDS frequency (ON or OFF)
        freq = args.freq_on if pattern[i] == 1 else FREQ_OFF
        dds.set_freq(freq)
        t_dds = time.perf_counter() - t0

        # Capture (PicoScope only — no sig_gen call)
        raw = capture_only(handle, buf_a, buf_b, overflow, t_ms)
        magnitudes[i] = extract_magnitude(raw, args.freq_on)

        step_times[i] = time.perf_counter() - t0
        dds_times[i] = t_dds

        if (i + 1) % 100 == 0:
            rate = (i + 1) / (time.perf_counter() - t_start)
            print(f"  Step {i+1}/{n_steps}  rate={rate:.1f} Hz  "
                  f"step_time={step_times[i]*1000:.1f} ms  "
                  f"dds_time={t_dds*1000:.1f} ms")

    total_time = time.perf_counter() - t_start
    actual_rate = n_steps / total_time

    # ─── Analysis ───
    print(f"\n{'='*60}")
    print(f"TIMING")
    print(f"  Total: {total_time:.1f}s for {n_steps} steps")
    print(f"  Step rate: {actual_rate:.1f} Hz ({np.median(step_times)*1000:.2f} ms median)")
    print(f"  DDS update: {np.median(dds_times)*1000:.2f} ms median")
    print(f"  Capture: {np.median(step_times - dds_times)*1000:.2f} ms median")

    # Separate ON and OFF magnitudes
    on_mask = pattern == 1
    off_mask = pattern == 0
    on_mags = magnitudes[on_mask]
    off_mags = magnitudes[off_mask]

    print(f"\nSIGNAL")
    print(f"  ON steps:  mean={np.mean(on_mags):.0f}  std={np.std(on_mags):.0f}")
    print(f"  OFF steps: mean={np.mean(off_mags):.0f}  std={np.std(off_mags):.0f}")
    print(f"  ON/OFF ratio: {np.mean(on_mags)/max(np.mean(off_mags),1):.2f}x")

    # Temporal memory test: does an OFF step AFTER an ON step have higher
    # magnitude than an OFF step AFTER another OFF step?
    off_after_on = []
    off_after_off = []
    for i in range(1, n_steps):
        if pattern[i] == 0:  # Current step is OFF
            if pattern[i-1] == 1:
                off_after_on.append(magnitudes[i])
            else:
                off_after_off.append(magnitudes[i])

    off_after_on = np.array(off_after_on) if off_after_on else np.array([0.0])
    off_after_off = np.array(off_after_off) if off_after_off else np.array([0.0])

    print(f"\nTEMPORAL MEMORY TEST")
    print(f"  OFF-after-ON:  mean={np.mean(off_after_on):.0f}  (n={len(off_after_on)})")
    print(f"  OFF-after-OFF: mean={np.mean(off_after_off):.0f}  (n={len(off_after_off)})")

    if np.mean(off_after_off) > 0:
        retention = np.mean(off_after_on) / np.mean(off_after_off) - 1.0
        print(f"  Retention signal: {retention*100:+.1f}%")
    else:
        retention = float('inf') if np.mean(off_after_on) > 0 else 0.0
        print(f"  Retention signal: OFF-after-OFF is zero (perfect discrimination)")

    # Shuffle test: does temporal order matter?
    # Train ridge classifier: predict pattern[i] from magnitudes[i-1:i+1]
    from sklearn.linear_model import RidgeClassifier
    from sklearn.model_selection import cross_val_score

    # Features: [mag(t), mag(t-1), mag(t-2)]
    X = np.column_stack([magnitudes[2:], magnitudes[1:-1], magnitudes[:-2]])
    y = pattern[2:]

    # Ordered vs shuffled
    clf = RidgeClassifier(alpha=1.0)
    ordered_acc = np.mean(cross_val_score(clf, X, y, cv=5, scoring="accuracy"))

    rng = np.random.default_rng(99)
    shuf_idx = rng.permutation(len(y))
    shuffled_acc = np.mean(cross_val_score(clf, X[shuf_idx], y[shuf_idx], cv=5, scoring="accuracy"))

    print(f"\nSHUFFLE TEST (5-fold CV)")
    print(f"  Ordered accuracy:  {ordered_acc*100:.1f}%")
    print(f"  Shuffled accuracy: {shuffled_acc*100:.1f}%")
    print(f"  Delta: {(ordered_acc - shuffled_acc)*100:+.1f}%")

    if ordered_acc - shuffled_acc > 0.02:
        print(f"\n  ✅ TEMPORAL MEMORY DETECTED — order matters by "
              f"{(ordered_acc - shuffled_acc)*100:.1f}%")
    else:
        print(f"\n  ❌ No temporal memory detected (delta < 2%)")

    # Expected retention
    if actual_rate > 0:
        step_ms = 1000.0 / actual_rate
        tau_ms = 1.99  # Best mode τ
        expected_retention = np.exp(-step_ms / tau_ms)
        print(f"\nPHYSICS CHECK")
        print(f"  Step period: {step_ms:.2f} ms")
        print(f"  Mode τ: {tau_ms} ms (29.9 kHz, Q=218)")
        print(f"  Expected retention: {expected_retention*100:.1f}%")
        print(f"  Steps of memory (>5%): {int(-np.log(0.05) / (step_ms / tau_ms))}")

    print(f"{'='*60}")

    # ─── Save results ───
    result = {
        "experiment": "temporal_proof",
        "timestamp": datetime.now().isoformat(),
        "params": {
            "freq_on": args.freq_on,
            "freq_off": FREQ_OFF,
            "relay": args.relay,
            "n_steps": n_steps,
            "pattern": args.pattern,
            "n_samples": N_SAMPLES,
            "timebase": TIMEBASE,
        },
        "timing": {
            "total_s": total_time,
            "step_rate_hz": actual_rate,
            "step_time_median_ms": float(np.median(step_times) * 1000),
            "dds_time_median_ms": float(np.median(dds_times) * 1000),
            "capture_time_median_ms": float(np.median(step_times - dds_times) * 1000),
        },
        "signal": {
            "on_mean": float(np.mean(on_mags)),
            "on_std": float(np.std(on_mags)),
            "off_mean": float(np.mean(off_mags)),
            "off_std": float(np.std(off_mags)),
            "on_off_ratio": float(np.mean(on_mags) / max(np.mean(off_mags), 1)),
        },
        "temporal_memory": {
            "off_after_on_mean": float(np.mean(off_after_on)),
            "off_after_off_mean": float(np.mean(off_after_off)),
            "retention_pct": float(retention * 100) if retention != float('inf') else None,
            "ordered_accuracy": float(ordered_acc),
            "shuffled_accuracy": float(shuffled_acc),
            "shuffle_delta": float(ordered_acc - shuffled_acc),
            "temporal_memory_detected": bool(ordered_acc - shuffled_acc > 0.02),
        },
        "pattern": pattern.tolist(),
        "magnitudes": magnitudes.tolist(),
        "step_times_ms": (step_times * 1000).tolist(),
    }

    out_dir = Path("data/results/lab/plate_exps/temporal")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"temporal_proof_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved: {out_path}")

    # ─── Cleanup ───
    dds.off()
    ser.write(b"0\n")  # All relays off
    time.sleep(0.05)
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    ser.close()
    print("Done.")


if __name__ == "__main__":
    main()
