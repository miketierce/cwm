#!/usr/bin/env python3
"""
CWM PicoScope hardware interface.

Drop-in replacement for _compute_rod_fingerprint() that reads real
spectral fingerprints from a PicoScope 2204A connected via USB.

Supports both driver families:
    - ps2000a (standard on Windows/Linux)
    - ps2000  (required on macOS ARM64 for some 2204A units)

The driver auto-detects which API works and locates the native SDK
libraries inside the PicoScope app bundle on macOS.

Hardware wiring (from experiment guide §D.2a):
    AWG out → BNC tee → all PZT hot leads (parallel)
    Channel A → BNC tee → all PZT hot leads (aggregate readout)
    Channel B → (optional) single-rod diagnostic
    All PZT grounds → common ground bar → scope ground

Requires:
    pip install picosdk  # Pico Technology Python wrapper
    PicoScope 7 app installed (includes native SDK libraries)

Usage:
    from tools.cwm_picoscope import measure_rod_fingerprint, check_hardware

    if check_hardware():
        fp = measure_rod_fingerprint(rod_id=1, pattern_name="A")
        # fp["fingerprint"] is a 20-element list, same as simulation
"""

import os
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
VOLTAGE_RANGE_MV = 500    # ±500 mV
SETTLE_MS = 50            # wait after AWG starts before capture
AVERAGES = 4              # number of captures to average for SNR

# Baseline unperturbed frequencies (computed once from rod geometry)
_baseline_cache: dict = {}

# ── macOS SDK library path auto-detection ─────────────────────────────────
_MACOS_APP_PATHS = [
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources",
    "/Applications/PicoScope 7 T&M.app/Contents/Resources",
    "/Applications/PicoScope.app/Contents/Resources",
]


def _ensure_dyld_path():
    """On macOS, ensure DYLD_LIBRARY_PATH includes the PicoScope SDK libraries."""
    if sys.platform != "darwin":
        return
    current = os.environ.get("DYLD_LIBRARY_PATH", "")
    for app_path in _MACOS_APP_PATHS:
        if Path(app_path).exists() and app_path not in current:
            os.environ["DYLD_LIBRARY_PATH"] = f"{app_path}:{current}" if current else app_path
            return


_ensure_dyld_path()

# Which driver API to use: "ps2000a", "ps2000", or None (not yet detected)
_driver_api = None  # "ps2000a", "ps2000", or None (not yet detected)


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
    """Return True if a PicoScope 2204A is connected and reachable.

    Tries ps2000a first (standard driver), then falls back to ps2000
    (required on macOS ARM64 for some 2204A units).  Sets _driver_api
    for subsequent calls.
    """
    global _driver_api

    # Try ps2000a first
    try:
        import ctypes
        from picosdk.ps2000a import ps2000a
        handle = ctypes.c_int16()
        status = ps2000a.ps2000aOpenUnit(ctypes.byref(handle), None)
        if status == 0:  # PICO_OK
            ps2000a.ps2000aCloseUnit(handle)
            _driver_api = "ps2000a"
            return True
    except (ImportError, OSError):
        pass

    # Try ps2000 (non-A) — needed on macOS ARM64
    try:
        from picosdk.ps2000 import ps2000
        handle = ps2000.ps2000_open_unit()
        if handle > 0:
            ps2000.ps2000_close_unit(handle)
            _driver_api = "ps2000"
            return True
    except (ImportError, OSError):
        pass

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

    Dispatches to the correct driver API (ps2000a or ps2000) based on
    what check_hardware() detected.
    """
    global _driver_api
    if _driver_api is None:
        if not check_hardware():
            raise RuntimeError("No PicoScope detected")

    baseline = _get_baseline_freqs(rod_length_mm, rod_diameter_mm)
    awg_data = _load_awg_waveform(pattern_name)

    if _driver_api == "ps2000a":
        averaged = _capture_ps2000a(awg_data)
    else:
        averaged = _capture_ps2000(awg_data)

    # ── FFT and peak extraction ──────────────────────────────────────
    spectrum = np.fft.rfft(averaged * np.hanning(len(averaged)))
    magnitude = np.abs(spectrum)
    freq_axis = np.fft.rfftfreq(len(averaged), d=1.0 / SAMPLE_RATE)

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

    shift_hz = perturbed_hz - baseline

    return {
        "perturbed_hz": perturbed_hz.tolist(),
        "shift_hz": shift_hz.tolist(),
        "fingerprint": shift_hz.tolist(),
    }


def _capture_ps2000a(awg_data: np.ndarray) -> np.ndarray:
    """Capture averaged waveform using the ps2000a (A-series) driver."""
    import ctypes
    import time
    from picosdk.ps2000a import ps2000a
    from picosdk.functions import assert_pico_ok

    handle = ctypes.c_int16()
    assert_pico_ok(ps2000a.ps2000aOpenUnit(ctypes.byref(handle), None))

    try:
        # Configure Channel A: enabled, DC coupling, ±500 mV (range 5), 0V offset
        assert_pico_ok(ps2000a.ps2000aSetChannel(handle, 0, 1, 1, 5, 0.0))

        # Timebase 1 → 1 MS/s
        timebase = ctypes.c_uint32(1)
        time_interval_ns = ctypes.c_float()
        max_samples = ctypes.c_int32()
        assert_pico_ok(ps2000a.ps2000aGetTimebase2(
            handle, timebase, N_SAMPLES,
            ctypes.byref(time_interval_ns), ctypes.byref(max_samples), 0
        ))

        # Load AWG waveform
        awg_int16 = (awg_data * 32767).astype(np.int16)
        awg_buffer = (ctypes.c_int16 * len(awg_int16))(*awg_int16)
        assert_pico_ok(ps2000a.ps2000aSetSigGenArbitrary(
            handle, 0, 2_000_000, 0, 0, 0, 0,
            awg_buffer, len(awg_int16), 0, 0, 0, 0, 0, 0, 0, 0
        ))

        time.sleep(SETTLE_MS / 1000.0)

        # Capture and average
        accumulated = np.zeros(N_SAMPLES, dtype=np.float64)
        for _ in range(AVERAGES):
            buf_a = (ctypes.c_int16 * N_SAMPLES)()
            assert_pico_ok(ps2000a.ps2000aSetDataBuffer(
                handle, 0, ctypes.byref(buf_a), N_SAMPLES, 0, 0
            ))
            assert_pico_ok(ps2000a.ps2000aRunBlock(
                handle, 0, N_SAMPLES, timebase, None, 0, None, None
            ))
            ready = ctypes.c_int16(0)
            while ready.value == 0:
                assert_pico_ok(ps2000a.ps2000aIsReady(handle, ctypes.byref(ready)))
                time.sleep(0.001)
            n_captured = ctypes.c_int32(N_SAMPLES)
            overflow = ctypes.c_int16()
            assert_pico_ok(ps2000a.ps2000aGetValues(
                handle, 0, ctypes.byref(n_captured), 0, 0, 0, ctypes.byref(overflow)
            ))
            accumulated += np.array(buf_a[:n_captured.value], dtype=np.float64)

        return accumulated / AVERAGES

    finally:
        ps2000a.ps2000aStop(handle)
        try:
            ps2000a.ps2000aSigGenSoftwareControl(handle, 0)
        except Exception:
            pass
        ps2000a.ps2000aCloseUnit(handle)


def _capture_ps2000(awg_data: np.ndarray) -> np.ndarray:
    """Capture averaged waveform using the ps2000 (non-A) driver.

    Used on macOS ARM64 where the 2204A presents via the ps2000 API.
    The ps2000 2204A has a max single-channel buffer of ~3968 samples.
    """
    import ctypes
    import time
    from picosdk.ps2000 import ps2000

    # ps2000 2204A max buffer is ~3968 for single channel
    capture_samples = min(N_SAMPLES, 3968)

    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")

    try:
        # Configure Channel A: enabled, DC coupling, ±500mV (PS2000_500MV = 6)
        ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
        # Disable Channel B
        ps2000.ps2000_set_channel(handle, 1, False, 1, 6)

        # Load AWG waveform (if the unit supports it)
        try:
            awg_int16 = (awg_data * 32767).astype(np.int16)
            awg_buffer = (ctypes.c_int16 * len(awg_int16))(*awg_int16)
            ps2000.ps2000_set_sig_gen_arbitrary(
                handle, 0, 2_000_000,  # offset=0, pkToPk=2Vpp in µV
                0, 0, 0, 0,            # delta phase params
                awg_buffer, len(awg_int16),
                0, 0                    # sweep, sweeps
            )
            time.sleep(SETTLE_MS / 1000.0)
        except Exception:
            pass  # Unit may not support AWG — capture ambient response

        # Capture and average
        # ps2000: timebase 3 ≈ 1 µs sample interval for 2204A
        accumulated = np.zeros(capture_samples, dtype=np.float64)

        for _ in range(AVERAGES):
            time_ms = ctypes.c_int32()
            ps2000.ps2000_run_block(handle, capture_samples, 3, 1, ctypes.byref(time_ms))

            t0 = time.time()
            while ps2000.ps2000_ready(handle) == 0:
                time.sleep(0.001)
                if time.time() - t0 > 5:
                    break

            buf_a = (ctypes.c_int16 * capture_samples)()
            buf_b = (ctypes.c_int16 * capture_samples)()
            overflow = ctypes.c_int16()
            n = ps2000.ps2000_get_values(
                handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                None, None, ctypes.byref(overflow), capture_samples
            )
            if n > 0:
                accumulated[:n] += np.array(buf_a[:n], dtype=np.float64)

        return accumulated / AVERAGES

    finally:
        ps2000.ps2000_stop(handle)
        ps2000.ps2000_close_unit(handle)


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
