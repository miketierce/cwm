#!/usr/bin/env python3
"""
CWM PicoScope hardware interface.

Drop-in replacement for _compute_rod_fingerprint() that reads real
spectral fingerprints from a PicoScope 2204A connected via USB.

Hardware wiring (from experiment guide §D.2a):
    AWG out → BNC tee → all PZT hot leads (parallel)
    Channel A → BNC tee → all PZT hot leads (aggregate readout)
    Channel B → (optional) single-rod diagnostic
    All PZT grounds → common ground bar → scope ground

Requires:
    pip install picosdk  # Pico Technology Python wrapper
    PicoScope 2204A USB driver installed (PicoSDK from picotech.com)

Usage:
    from tools.cwm_picoscope import measure_rod_fingerprint, check_hardware

    if check_hardware():
        fp = measure_rod_fingerprint(rod_id=1, pattern_name="A")
        # fp["fingerprint"] is a 20-element list, same as simulation
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulations.glass_resonator import RodGeometry, compute_mode_spectrum

# ── Constants (must match cwm_lab.py) ─────────────────────────────────────
N_MODES = 20
SAMPLE_RATE = 1_000_000  # 1 MS/s — PicoScope 2204A max
N_SAMPLES = 8192          # capture buffer
AWG_BUFFER = 8192         # AWG output buffer
VOLTAGE_RANGE_MV = 500    # ±500 mV (PS2000A_500MV)
SETTLE_MS = 50            # wait after AWG starts before capture
AVERAGES = 4              # number of captures to average for SNR

# Baseline unperturbed frequencies (computed once from rod geometry)
_baseline_cache: dict = {}


def _get_baseline_freqs(
    rod_length_mm: float = 150.0,
    rod_diameter_mm: float = 6.0,
) -> np.ndarray:
    """Return the N_MODES unperturbed longitudinal frequencies in Hz."""
    key = (rod_length_mm, rod_diameter_mm)
    if key not in _baseline_cache:
        rod = RodGeometry(
            length=rod_length_mm / 1000.0,
            diameter=rod_diameter_mm / 1000.0,
            glass_type="borosilicate",
        )
        spec = compute_mode_spectrum(rod, N_MODES)
        _baseline_cache[key] = spec.frequencies.copy()
    return _baseline_cache[key]


def check_hardware() -> bool:
    """Return True if a PicoScope 2204A is connected and reachable."""
    try:
        import ctypes
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok

        handle = ctypes.c_int16()
        status = ps2000a.ps2000aOpenUnit(ctypes.byref(handle), None)
        if status == 0:  # PICO_OK
            ps2000a.ps2000aCloseUnit(handle)
            return True
        return False
    except (ImportError, OSError):
        return False


def _load_awg_waveform(pattern_name: str) -> np.ndarray:
    """Load the pre-generated AWG CSV for a pattern (normalised ±1)."""
    csv_path = Path("data/results/awg") / f"query_{pattern_name.upper()}.csv"
    if csv_path.exists():
        # Skip header line, read single column
        data = np.loadtxt(str(csv_path), skiprows=1)
        return data.astype(np.float64)
    else:
        # Generate a simple chirp spanning the mode frequency range
        baseline = _get_baseline_freqs()
        f_lo = baseline[0] * 0.9
        f_hi = baseline[-1] * 1.1
        t = np.arange(AWG_BUFFER) / SAMPLE_RATE
        phase = 2 * np.pi * (f_lo * t + (f_hi - f_lo) / (2 * t[-1]) * t**2)
        return np.sin(phase)


def measure_rod_fingerprint(
    rod_id: int = 1,
    pattern_name: str = "A",
    rod_length_mm: float = 150.0,
    rod_diameter_mm: float = 6.0,
) -> dict:
    """
    Measure a real rod's spectral fingerprint via PicoScope.

    This is the hardware drop-in for _compute_rod_fingerprint().
    Returns the same dict format: {perturbed_hz, shift_hz, fingerprint}.

    Steps:
        1. Open PicoScope, configure Channel A (±500 mV, DC, 1 MS/s)
        2. Load pre-computed AWG waveform for the pattern
        3. Drive AWG output → aggregate PZT array
        4. Capture N_SAMPLES from Channel A (PZT response)
        5. Average multiple captures for SNR
        6. FFT → find 20 peak frequencies nearest to expected modes
        7. Subtract unperturbed baseline → frequency shifts
    """
    import ctypes
    from picosdk.ps2000a import ps2000a
    from picosdk.functions import assert_pico_ok
    import time

    baseline = _get_baseline_freqs(rod_length_mm, rod_diameter_mm)

    # ── 1. Open unit ─────────────────────────────────────────────────
    handle = ctypes.c_int16()
    assert_pico_ok(ps2000a.ps2000aOpenUnit(ctypes.byref(handle), None))

    try:
        # ── 2. Configure Channel A ───────────────────────────────────
        #   PS2000A_CHANNEL_A = 0
        #   PS2000A_DC = 1
        #   PS2000A_500MV = 5
        assert_pico_ok(ps2000a.ps2000aSetChannel(
            handle, 0, 1, 1, 5, 0.0  # chA, enabled, DC, 500mV, 0V offset
        ))

        # ── 3. Configure timebase ───────────────────────────────────
        #   For 2204A: timebase=1 → 1 MS/s (1 µs interval)
        timebase = ctypes.c_uint32(1)
        time_interval_ns = ctypes.c_float()
        max_samples = ctypes.c_int32()
        assert_pico_ok(ps2000a.ps2000aGetTimebase2(
            handle, timebase, N_SAMPLES,
            ctypes.byref(time_interval_ns), ctypes.byref(max_samples), 0
        ))

        # ── 4. Load AWG waveform ────────────────────────────────────
        awg_data = _load_awg_waveform(pattern_name)
        # PicoScope AWG expects int16 buffer scaled to DAC range
        awg_int16 = (awg_data * 32767).astype(np.int16)
        awg_buffer = (ctypes.c_int16 * len(awg_int16))(*awg_int16)

        # setSigGenArbitrary: drive the AWG with our waveform
        #   offsetVoltage=0, pkToPk=2_000_000 (2Vpp in µV),
        #   startDeltaPhase, stopDeltaPhase, deltaPhaseIncrement,
        #   dwellCount, arbitraryWaveform, arbitraryWaveformSize,
        #   sweepType=0(up), operation=0, indexMode=0(single),
        #   shots=0(continuous), sweeps=0, triggerType=0, triggerSource=0, extInThreshold=0
        assert_pico_ok(ps2000a.ps2000aSetSigGenArbitrary(
            handle,
            0,               # offsetVoltage (µV)
            2_000_000,       # pkToPk (µV) = 2 V
            0, 0, 0, 0,     # delta phase params (unused for single freq)
            awg_buffer,
            len(awg_int16),
            0, 0, 0,        # sweep, operation, indexMode
            0, 0,            # shots, sweeps (0 = continuous)
            0, 0, 0          # trigger params
        ))

        time.sleep(SETTLE_MS / 1000.0)

        # ── 5. Capture and average ──────────────────────────────────
        accumulated = np.zeros(N_SAMPLES, dtype=np.float64)

        for avg_i in range(AVERAGES):
            # Allocate capture buffer
            buf_a = (ctypes.c_int16 * N_SAMPLES)()
            assert_pico_ok(ps2000a.ps2000aSetDataBuffer(
                handle, 0, ctypes.byref(buf_a), N_SAMPLES, 0, 0
            ))

            # Start block capture (no trigger, immediate)
            assert_pico_ok(ps2000a.ps2000aRunBlock(
                handle, 0, N_SAMPLES, timebase, None, 0, None, None
            ))

            # Poll for completion
            ready = ctypes.c_int16(0)
            while ready.value == 0:
                assert_pico_ok(ps2000a.ps2000aIsReady(
                    handle, ctypes.byref(ready)
                ))
                time.sleep(0.001)

            # Retrieve data
            n_captured = ctypes.c_int32(N_SAMPLES)
            overflow = ctypes.c_int16()
            assert_pico_ok(ps2000a.ps2000aGetValues(
                handle, 0, ctypes.byref(n_captured), 0, 0, 0,
                ctypes.byref(overflow)
            ))

            accumulated += np.array(buf_a[:n_captured.value], dtype=np.float64)

        averaged = accumulated / AVERAGES

        # ── 6. FFT and peak extraction ──────────────────────────────
        spectrum = np.fft.rfft(averaged * np.hanning(len(averaged)))
        magnitude = np.abs(spectrum)
        freq_axis = np.fft.rfftfreq(N_SAMPLES, d=1.0 / SAMPLE_RATE)

        # Find the peak frequency nearest each expected mode
        perturbed_hz = np.zeros(N_MODES)
        for i, f_expected in enumerate(baseline):
            # Search window: ±0.5% around expected frequency
            window = f_expected * 0.005
            mask = (freq_axis >= f_expected - window) & (freq_axis <= f_expected + window)
            if np.any(mask):
                idx_in_window = np.where(mask)[0]
                best = idx_in_window[np.argmax(magnitude[mask])]
                # Parabolic interpolation for sub-bin accuracy
                if 0 < best < len(magnitude) - 1:
                    alpha = magnitude[best - 1]
                    beta = magnitude[best]
                    gamma = magnitude[best + 1]
                    if 2 * beta - alpha - gamma != 0:
                        delta = 0.5 * (alpha - gamma) / (alpha - 2 * beta + gamma)
                    else:
                        delta = 0.0
                    perturbed_hz[i] = freq_axis[best] + delta * (freq_axis[1] - freq_axis[0])
                else:
                    perturbed_hz[i] = freq_axis[best]
            else:
                perturbed_hz[i] = f_expected  # fallback: no shift detected

        # ── 7. Compute shifts ───────────────────────────────────────
        shift_hz = perturbed_hz - baseline

    finally:
        # Always close the scope
        ps2000a.ps2000aStop(handle)
        ps2000a.ps2000aSigGenSoftwareControl(handle, 0)  # stop AWG
        ps2000a.ps2000aCloseUnit(handle)

    return {
        "perturbed_hz": perturbed_hz.tolist(),
        "shift_hz": shift_hz.tolist(),
        "fingerprint": shift_hz.tolist(),
    }


# ── CLI for standalone testing ────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="CWM PicoScope hardware measurement")
    parser.add_argument("--check", action="store_true", help="Check if PicoScope is connected")
    parser.add_argument("--measure", action="store_true", help="Measure rod fingerprint")
    parser.add_argument("--rod", type=int, default=1, help="Rod ID (default: 1)")
    parser.add_argument("--pattern", default="A", help="Perturbation pattern (default: A)")
    args = parser.parse_args()

    if args.check:
        connected = check_hardware()
        print(f"PicoScope connected: {connected}")
        sys.exit(0 if connected else 1)

    if args.measure:
        if not check_hardware():
            print("ERROR: No PicoScope detected. Check USB connection and driver.")
            sys.exit(1)

        print(f"Measuring rod {args.rod} (Pattern {args.pattern})...")
        result = measure_rod_fingerprint(rod_id=args.rod, pattern_name=args.pattern)

        baseline = _get_baseline_freqs()
        print(f"\n{'Mode':>4}  {'Baseline Hz':>12}  {'Measured Hz':>12}  {'Shift Hz':>10}")
        print("-" * 44)
        for i in range(N_MODES):
            print(f"{i+1:4d}  {baseline[i]:12.2f}  {result['perturbed_hz'][i]:12.2f}  {result['shift_hz'][i]:10.4f}")

        print(f"\nFingerprint (20 shifts): {[round(s, 4) for s in result['fingerprint']]}")


if __name__ == "__main__":
    main()
