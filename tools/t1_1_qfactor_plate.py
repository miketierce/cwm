#!/usr/bin/env python3
"""
T1.1 — Q-Factor Ringdown Measurement (Fused Silica Plate)

Gate/Kill experiment: Measures Q-factor of the 100×100 mm fused silica plate
via exponential ringdown envelope fitting.

Protocol:
  1. Select relay channel for RX PZT
  2. Drive plate at a resonance via AWG → Board D → TX PZT
  3. Let plate ring up to steady state (~1 second)
  4. Cut AWG abruptly (set amplitude to 0)
  5. Immediately capture ringdown on Ch A (through Board A preamp)
  6. Fit exponential envelope: A·exp(−t/τ)
  7. Compute Q = π · f · τ

Kill criterion:  Q < 500 → stop, skip to MEMS
Go criterion:   Q > 1000 → proceed with full experiment suite

Hardware:
  - PicoScope AWG → Board D (3.69× gain) → TX PZT on plate
  - RX PZT on plate → relay 7 or 8 → Board A (11×) → PicoScope Ch A
  - Board D supply: ±9V dual battery

Usage:
  cd /Users/Mike/Code/wcfoma
  source .venv/bin/activate
  python tools/t1_1_qfactor_plate.py

  # If relay mux is not connected, use --no-relay to read Ch A directly:
  python tools/t1_1_qfactor_plate.py --no-relay

  # Specify drive frequency manually:
  python tools/t1_1_qfactor_plate.py --freq 4567

  # Try multiple frequencies from tap-test resonances:
  python tools/t1_1_qfactor_plate.py --sweep
"""
from __future__ import annotations

import argparse
import ctypes as ct
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure DYLD_LIBRARY_PATH for PicoScope
os.environ.setdefault(
    "DYLD_LIBRARY_PATH",
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources",
)

from picosdk.ps2000 import ps2000

# ── Configuration ─────────────────────────────────────────────────────────

# PicoScope timing (timebase 7 = 1280 ns/sample = 781.25 kHz)
TIMEBASE = 7
DT_NS = 1280
SAMPLE_RATE = int(1e9 / DT_NS)  # 781250 Hz
N_SAMPLES = 2048  # reliable capture size for ps2000 macOS driver

# AWG drive amplitude (µVpp) — Board D amplifies by 3.69× → ~3.47 Vpp at PZT
AWG_DRIVE_UVPP = 1_000_000  # 1 Vpp from AWG → 3.69 Vpp after Board D

# Voltage range for Ch A (receive side, after Board A ×11 preamp)
# Start conservative — can auto-range if signal clips
CH_A_RANGE = 8  # ±5V range (index 8) — safe for initial discovery

# Relay channels for the plate
# TX PZT is wired direct from Board D (no relay)
# Relay 7 = NW corner RX PZT sensor
# Relay 8 = NE corner RX PZT sensor
RELAY_RX = 8  # NE RX PZT — diagonal from TX gives longest acoustic path

# Known plate resonances from May 22 tap test (Hz)
PLATE_RESONANCES = [291, 388, 484]

# Ringdown capture timing
RING_UP_S = 1.0       # time to let plate reach steady state
RING_DOWN_DELAY_S = 0.001  # delay after AWG off before capture (1 ms)
N_RINGDOWN_CAPTURES = 5    # repeated captures for averaging


# ── Helper functions ──────────────────────────────────────────────────────

def open_scope() -> int:
    """Open PicoScope and return handle."""
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Failed to open PicoScope (handle={handle}). Is it connected?")
    print(f"  PicoScope opened (handle={handle})")
    return handle


def close_scope(handle: int):
    """Shut down AWG and close PicoScope."""
    ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("  PicoScope closed")


def setup_channel_a(handle: int, range_idx: int = CH_A_RANGE):
    """Configure Ch A for AC-coupled measurement."""
    ps2000.ps2000_set_channel(handle, 0, 1, 1, range_idx)


def capture_block(handle: int, n_samples: int = N_SAMPLES) -> np.ndarray:
    """Capture a single block and return data in mV."""
    # Exact pattern from proven Board D validation: source=5(None), auto_ms=1
    ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
    ps2000.ps2000_run_block(handle, n_samples, TIMEBASE, 1, ct.byref(ct.c_int32()))
    time.sleep(0.1)  # let capture complete (2048 samples @ 1280ns = 2.6ms)

    for _ in range(100):
        if ps2000.ps2000_ready(handle):
            break
        time.sleep(0.05)
    else:
        # Don't raise — return zeros (matches _hw_capture_raw graceful fallback)
        return np.zeros(n_samples, dtype=np.float64)

    buf = (ct.c_int16 * n_samples)()
    ov = ct.c_int16(0)
    ps2000.ps2000_get_values(
        handle, ct.byref(buf), None, None, None,
        ct.byref(ov), n_samples, 0
    )

    # Convert to mV based on range
    range_mv = {2: 50, 3: 100, 4: 200, 5: 500, 6: 1000, 7: 2000, 8: 5000}
    scale = range_mv.get(CH_A_RANGE, 5000)
    mv = np.array(buf, dtype=np.float64) * (scale / 32767.0)
    return mv


def set_awg_sine(handle: int, freq_hz: float, amplitude_uvpp: int = AWG_DRIVE_UVPP):
    """Set AWG to continuous sine at given frequency."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, amplitude_uvpp, 0,
        float(freq_hz), float(freq_hz),
        0.0, 0.0, 0, 0
    )


def set_awg_off(handle: int):
    """Turn AWG output to zero amplitude (abrupt cutoff for ringdown)."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )


def fit_ringdown(signal_mv: np.ndarray, freq_hz: float) -> dict:
    """
    Fit exponential decay to the signal envelope.

    Returns dict with tau_ms, Q, R_squared, peak_mv, and fit diagnostics.
    """
    from scipy.signal import hilbert

    t = np.arange(len(signal_mv)) / SAMPLE_RATE

    # Remove DC using the last 10% of samples (noise floor, after any decay)
    noise_section = signal_mv[int(len(signal_mv) * 0.9):]
    signal_mv = signal_mv - np.mean(noise_section)

    # Compute envelope via Hilbert transform
    analytic = hilbert(signal_mv)
    envelope = np.abs(analytic)

    # Smooth envelope: moving average over ~2 cycles at the drive frequency
    samples_per_cycle = max(int(SAMPLE_RATE / freq_hz), 1)
    window = max(samples_per_cycle * 2, 10)
    if window < len(envelope):
        kernel = np.ones(window) / window
        envelope = np.convolve(envelope, kernel, mode='same')

    # Find the peak of the envelope
    peak_idx = np.argmax(envelope)
    peak_mv = float(envelope[peak_idx])

    # Only fit the decay portion (from peak onward)
    env_decay = envelope[peak_idx:]
    t_decay = t[peak_idx:] - t[peak_idx]

    # Noise floor: RMS of last 10% of envelope
    noise_floor = float(np.mean(envelope[int(len(envelope) * 0.9):]))

    # Mask: fit where envelope > noise_floor + 2σ (or 10% of peak, whichever is higher)
    threshold = max(noise_floor * 2, peak_mv * 0.10)
    mask = env_decay > threshold
    if np.sum(mask) < 10:
        return {
            "tau_ms": None, "Q": None, "R_squared": None,
            "peak_mv": peak_mv, "noise_floor_mv": noise_floor,
            "error": "Insufficient decay points above threshold"
        }

    t_fit = t_decay[mask]
    env_fit = env_decay[mask]
    log_env = np.log(env_fit)

    # Linear fit: log(envelope) = log(A) + (-1/tau) * t
    coeffs, residuals, rank, sv, rcond = np.polyfit(t_fit, log_env, 1, full=True)
    slope = coeffs[0]

    if slope >= 0:
        return {
            "tau_ms": None, "Q": None, "R_squared": None,
            "peak_mv": peak_mv, "noise_floor_mv": noise_floor,
            "error": "Envelope not decaying (slope >= 0)"
        }

    tau_s = -1.0 / slope
    Q = math.pi * freq_hz * tau_s

    # R² goodness of fit
    predicted = coeffs[0] * t_fit + coeffs[1]
    ss_res = np.sum((log_env - predicted) ** 2)
    ss_tot = np.sum((log_env - np.mean(log_env)) ** 2)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return {
        "tau_ms": round(tau_s * 1000, 3),
        "Q": round(Q, 1),
        "R_squared": round(r_squared, 4),
        "peak_mv": round(peak_mv, 2),
        "noise_floor_mv": round(noise_floor, 2),
        "decay_points": int(np.sum(mask)),
        "slope": round(slope, 2),
        "error": None,
    }


def measure_q_at_frequency(handle: int, freq_hz: float, n_avg: int = N_RINGDOWN_CAPTURES,
                           ring_up_s: float = RING_UP_S) -> dict:
    """
    Complete Q measurement cycle at one frequency:
      1. Ring up (CW drive for ring_up_s)
      2. Start capture, then immediately cut AWG (catches the decay onset)
      3. Repeat n_avg times and average
      4. Fit exponential envelope
    """
    print(f"\n  Measuring Q at {freq_hz:.1f} Hz...")

    # Step 1: Ring up — drive at frequency for steady state
    set_awg_sine(handle, freq_hz)
    print(f"    Ringing up ({ring_up_s}s)...", end="", flush=True)
    time.sleep(ring_up_s)
    print(" done")

    # Step 2: Capture steady-state reference (for SNR calculation)
    steady_state = capture_block(handle)
    ss_pp = float(steady_state.max() - steady_state.min())
    print(f"    Steady-state: {ss_pp:.1f} mV p-p")

    # Step 3: Capture ringdown — cut AWG then immediately capture (no delay)
    ringdown_captures = []
    for i in range(n_avg):
        # Re-excite to steady state between captures
        if i > 0:
            set_awg_sine(handle, freq_hz)
            time.sleep(ring_up_s * 0.5)  # shorter re-excitation

        # Cut AWG abruptly then capture immediately
        set_awg_off(handle)
        # No delay — capture starts immediately to catch early decay
        rd = capture_block(handle)
        ringdown_captures.append(rd)

    # Average the ringdown captures
    rd_avg = np.mean(ringdown_captures, axis=0)

    # Step 4: Fit exponential decay
    result = fit_ringdown(rd_avg, freq_hz)
    result["freq_hz"] = freq_hz
    result["steady_state_pp_mv"] = round(ss_pp, 1)
    result["n_averages"] = n_avg

    if result["Q"] is not None:
        print(f"    τ = {result['tau_ms']:.2f} ms, Q = {result['Q']:.0f} (R² = {result['R_squared']:.3f})")
    else:
        print(f"    FAILED: {result.get('error', 'unknown')}")

    return result


# ── Broadband resonance finder ────────────────────────────────────────────

def find_plate_resonances(handle: int, f_start: float = 200, f_stop: float = 50000,
                          n_steps: int = 200) -> list[float]:
    """
    Quick swept-sine scan to find plate resonance peaks.
    Steps through frequencies, measures amplitude at each.
    Returns list of peak frequencies sorted by amplitude (strongest first).
    """
    print(f"\n  Scanning for resonances ({f_start:.0f}–{f_stop:.0f} Hz, {n_steps} steps)...")
    freqs = np.geomspace(f_start, f_stop, n_steps)
    amplitudes = []

    for i, f in enumerate(freqs):
        set_awg_sine(handle, f, amplitude_uvpp=500_000)  # moderate drive
        time.sleep(0.05)  # short settle
        data = capture_block(handle)
        pp = float(data.max() - data.min())
        amplitudes.append(pp)
        if (i + 1) % 50 == 0:
            print(f"    {i+1}/{n_steps} ({f:.0f} Hz, {pp:.1f} mV pp)")

    amplitudes = np.array(amplitudes)
    set_awg_off(handle)

    # Find peaks (local maxima above 3× median)
    median_amp = float(np.median(amplitudes))
    threshold = median_amp * 3.0
    peaks = []
    for i in range(1, len(amplitudes) - 1):
        if (amplitudes[i] > amplitudes[i-1] and
            amplitudes[i] > amplitudes[i+1] and
            amplitudes[i] > threshold):
            peaks.append((float(freqs[i]), float(amplitudes[i])))

    # Sort by amplitude (strongest first)
    peaks.sort(key=lambda x: x[1], reverse=True)

    print(f"    Found {len(peaks)} resonances above threshold ({threshold:.1f} mV)")
    for rank, (f, amp) in enumerate(peaks[:10], 1):
        print(f"      #{rank}: {f:.1f} Hz ({amp:.1f} mV pp)")

    return [f for f, _ in peaks]


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="T1.1 — Plate Q-Factor Ringdown")
    parser.add_argument("--freq", type=float, default=None,
                        help="Drive frequency in Hz (default: auto-scan)")
    parser.add_argument("--sweep", action="store_true",
                        help="Measure Q at all detected resonances")
    parser.add_argument("--no-relay", action="store_true",
                        help="Skip relay mux (Ch A wired directly)")
    parser.add_argument("--relay-ch", type=int, default=RELAY_RX,
                        help=f"Relay channel for RX PZT (default: {RELAY_RX})")
    parser.add_argument("--ring-up", type=float, default=RING_UP_S,
                        help=f"Ring-up time in seconds (default: {RING_UP_S})")
    parser.add_argument("--n-avg", type=int, default=N_RINGDOWN_CAPTURES,
                        help=f"Number of ringdown captures to average (default: {N_RINGDOWN_CAPTURES})")
    args = parser.parse_args()

    print("=" * 70)
    print("  T1.1 — Q-Factor Ringdown Measurement (Fused Silica Plate)")
    print("=" * 70)
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Plate: 100×100 mm fused silica")
    print(f"  Signal chain: AWG → Board D (×3.69) → TX PZT → Plate → RX PZT → Board A (×11) → Ch A")
    print(f"  Kill criterion: Q < 500")
    print(f"  Go criterion: Q > 1000")

    # Open hardware
    handle = open_scope()
    setup_channel_a(handle)

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
            print(f"  WARNING: Relay mux failed ({e}). Proceeding without mux.")
            mux = None

    ring_up_time = args.ring_up

    try:
        # Determine which frequencies to test
        if args.freq:
            test_freqs = [args.freq]
        elif args.sweep:
            test_freqs = find_plate_resonances(handle)
            if not test_freqs:
                print("\n  ERROR: No resonances found. Check wiring and PZT coupling.")
                close_scope(handle)
                return
            test_freqs = test_freqs[:8]  # top 8 resonances
        else:
            # Default: try known plate resonances from tap test + auto-scan
            print("\n  Using known resonances from tap test + auto-scan...")
            test_freqs = find_plate_resonances(handle)
            if not test_freqs:
                # Fallback to known tap-test values
                test_freqs = PLATE_RESONANCES
                print(f"  Falling back to tap-test values: {test_freqs}")
            else:
                test_freqs = test_freqs[:5]

        # Measure Q at each frequency
        results = []
        for freq in test_freqs:
            r = measure_q_at_frequency(handle, freq, n_avg=args.n_avg, ring_up_s=ring_up_time)
            results.append(r)

        # Summary
        print("\n" + "=" * 70)
        print("  RESULTS SUMMARY")
        print("=" * 70)
        print(f"  {'Freq (Hz)':<12} {'τ (ms)':<10} {'Q':<10} {'R²':<8} {'Peak (mV)':<10} {'Verdict'}")
        print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*8} {'-'*10} {'-'*10}")

        q_values = []
        for r in results:
            freq = r["freq_hz"]
            if r["Q"] is not None:
                q_values.append(r["Q"])
                if r["Q"] >= 1000:
                    verdict = "✓ GO"
                elif r["Q"] >= 500:
                    verdict = "~ MARGINAL"
                else:
                    verdict = "✗ KILL"
                print(f"  {freq:<12.1f} {r['tau_ms']:<10.2f} {r['Q']:<10.0f} "
                      f"{r['R_squared']:<8.3f} {r['peak_mv']:<10.1f} {verdict}")
            else:
                print(f"  {freq:<12.1f} {'—':<10} {'—':<10} {'—':<8} "
                      f"{r.get('peak_mv', 0):<10.1f} FAIL: {r['error']}")

        # Gate/Kill decision
        print("\n  " + "-" * 50)
        if q_values:
            best_q = max(q_values)
            median_q = float(np.median(q_values))
            print(f"  Best Q: {best_q:.0f} | Median Q: {median_q:.0f} | Modes measured: {len(q_values)}")

            if best_q >= 1000:
                print(f"  DECISION: ✓ GO — Q = {best_q:.0f} exceeds 1000 threshold")
                print(f"  → Proceed to T1.2 (Broadband Mode Census)")
            elif best_q >= 500:
                print(f"  DECISION: ~ MARGINAL — Q = {best_q:.0f} (between 500–1000)")
                print(f"  → Proceed cautiously. E33 interference unlikely but other experiments viable.")
            else:
                print(f"  DECISION: ✗ KILL — Best Q = {best_q:.0f} < 500")
                print(f"  → Plate coupling or material insufficient. Consider:")
                print(f"    - Better PZT bonding (thinner glue layer)")
                print(f"    - Different mounting (reduce boundary damping)")
                print(f"    - Skip to MEMS if mounting fixes don't help")
        else:
            print("  DECISION: INCONCLUSIVE — no valid Q measurements")
            print("  → Check: is RX PZT detecting signal? Try --sweep to find resonances first")

        # Save results
        output = {
            "experiment": "T1.1_qfactor_plate",
            "timestamp": datetime.now().isoformat(),
            "plate": "100x100mm_fused_silica",
            "signal_chain": "AWG→BoardD(3.69x)→TX_PZT→plate→RX_PZT→relay→BoardA(11x)→ChA",
            "awg_amplitude_uvpp": AWG_DRIVE_UVPP,
            "ch_a_range_index": CH_A_RANGE,
            "relay_channel": args.relay_ch if not args.no_relay else "direct",
            "ring_up_s": ring_up_time,
            "n_averages": args.n_avg,
            "results": results,
            "best_Q": max(q_values) if q_values else None,
            "median_Q": float(np.median(q_values)) if q_values else None,
            "gate_decision": (
                "GO" if q_values and max(q_values) >= 1000 else
                "MARGINAL" if q_values and max(q_values) >= 500 else
                "KILL" if q_values else "INCONCLUSIVE"
            ),
        }

        results_dir = Path(__file__).resolve().parent.parent / "data" / "results" / "plate_q"
        results_dir.mkdir(parents=True, exist_ok=True)
        out_file = results_dir / f"t1_1_qfactor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(out_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\n  Results saved: {out_file}")

    finally:
        if mux:
            mux.off()
        close_scope(handle)


if __name__ == "__main__":
    main()
