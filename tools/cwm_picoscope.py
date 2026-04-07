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
AVERAGES = 16              # number of captures to average for SNR

# Baseline unperturbed frequencies (computed once from rod geometry)
_baseline_cache: dict = {}

# Voltage range enum values (same for ps2000 and ps2000a from ±50 mV up)
VOLTAGE_RANGE_ENUM = {
    50: 2,     # ±50 mV
    100: 3,    # ±100 mV
    200: 4,    # ±200 mV
    500: 5,    # ±500 mV
    1000: 6,   # ±1 V
    2000: 7,   # ±2 V
}

# ── Experiment Presets (Table D.2a from experiment guide) ─────────────────

EXPERIMENT_PRESETS = {
    "exp01": {
        "name": "Exp 1 – Mode Persistence (Tap)",
        "description": "Strike the rod, capture spectrum. No AWG — ambient tap only.",
        "awg_mode": "off",
        "range_mv": 50,
        "timebase": 3,
        "samples": 3968,
        "averages": 1,
        "trigger_enabled": True,
        "trigger_source": 0,
        "trigger_threshold_mv": 5,
        "trigger_direction": 0,
        "trigger_auto_ms": 2000,
        "view": "both",
        "firebase_id": "exp01-mode-persistence",
    },
    "exp02a": {
        "name": "Exp 2a – Ring-Down Decay",
        "description": "Single sine pulse at f₁, measure decay envelope.",
        "awg_mode": "sine",
        "awg_freq_hz": 17700,
        "awg_amplitude_uvpp": 500_000,
        "awg_shots": 1,
        "range_mv": 500,
        "timebase": 3,
        "samples": 3968,
        "averages": 1,
        "trigger_enabled": True,
        "trigger_source": 0,
        "trigger_threshold_mv": 50,
        "trigger_direction": 0,
        "trigger_auto_ms": 0,
        "view": "both",
        "firebase_id": "exp03-damping-time",
    },
    "exp02b": {
        "name": "Exp 2b – Bandwidth / SNR",
        "description": "Narrow sweep 17–18.5 kHz, measure spectral peaks and SNR.",
        "awg_mode": "sweep",
        "awg_start_freq_hz": 17000,
        "awg_stop_freq_hz": 18500,
        "awg_amplitude_uvpp": 200_000,
        "awg_sweep_time_s": 2.0,
        "range_mv": 200,
        "timebase": 3,
        "samples": 3968,
        "averages": 4,
        "trigger_enabled": False,
        "view": "spectrum",
        "firebase_id": "exp02-snr-measurement",
    },
    "exp03": {
        "name": "Exp 3 – Mode Comb (Full Spectrum)",
        "description": "Broadband sweep 1–200 kHz, reveal all eigenmodes.",
        "awg_mode": "sweep",
        "awg_start_freq_hz": 1000,
        "awg_stop_freq_hz": 200000,
        "awg_amplitude_uvpp": 500_000,
        "awg_sweep_time_s": 1.0,
        "range_mv": 500,
        "timebase": 3,
        "samples": 3968,
        "averages": 4,
        "trigger_enabled": False,
        "view": "spectrum",
        "firebase_id": None,
    },
    "exp04": {
        "name": "Exp 4 – Thermal Stability",
        "description": "Quick mode-comb snapshot. Same config as Exp 3.",
        "awg_mode": "sweep",
        "awg_start_freq_hz": 1000,
        "awg_stop_freq_hz": 200000,
        "awg_amplitude_uvpp": 500_000,
        "awg_sweep_time_s": 1.0,
        "range_mv": 500,
        "timebase": 3,
        "samples": 3968,
        "averages": 4,
        "trigger_enabled": False,
        "view": "spectrum",
        "firebase_id": None,
    },
    "exp05": {
        "name": "Exp 5 – Perturbation Sensitivity",
        "description": "Mode comb with mass perturbation applied.",
        "awg_mode": "sweep",
        "awg_start_freq_hz": 1000,
        "awg_stop_freq_hz": 200000,
        "awg_amplitude_uvpp": 500_000,
        "awg_sweep_time_s": 1.0,
        "range_mv": 500,
        "timebase": 3,
        "samples": 3968,
        "averages": 4,
        "trigger_enabled": False,
        "view": "spectrum",
        "firebase_id": None,
    },
    "exp06": {
        "name": "Exp 6 – Recall (Arbitrary Waveform)",
        "description": "Load query_X.csv into AWG, measure recall spectrum.",
        "awg_mode": "arbitrary",
        "awg_amplitude_uvpp": 400_000,
        "range_mv": 200,
        "timebase": 3,
        "samples": 3968,
        "averages": 4,
        "trigger_enabled": False,
        "view": "spectrum",
        "firebase_id": None,
    },
    "exp07": {
        "name": "Exp 7 – CW Readout (Single Frequency)",
        "description": "Continuous sine at measured f₁, free-running capture.",
        "awg_mode": "sine",
        "awg_freq_hz": 17700,
        "awg_amplitude_uvpp": 200_000,
        "awg_shots": 0,
        "range_mv": 200,
        "timebase": 3,
        "samples": 3968,
        "averages": 1,
        "trigger_enabled": False,
        "view": "both",
        "firebase_id": None,
    },
    "exp_generic": {
        "name": "Exps 8–14 – Generic Spectrum",
        "description": "Default broadband sweep for experiments 8–14.",
        "awg_mode": "sweep",
        "awg_start_freq_hz": 1000,
        "awg_stop_freq_hz": 200000,
        "awg_amplitude_uvpp": 500_000,
        "awg_sweep_time_s": 1.0,
        "range_mv": 200,
        "timebase": 3,
        "samples": 3968,
        "averages": 4,
        "trigger_enabled": False,
        "view": "spectrum",
        "firebase_id": None,
    },
}

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
    reference_hz=None,
) -> dict:
    """
    Measure a real rod's spectral fingerprint via PicoScope.

    This is the hardware drop-in for _compute_rod_fingerprint().
    Returns the same dict format: {perturbed_hz, shift_hz, fingerprint}.

    Dispatches to the correct driver API (ps2000a or ps2000) based on
    what check_hardware() detected.

    Args:
        reference_hz: If provided (list/array of N_MODES frequencies),
            search for peaks around these values instead of the theoretical
            baseline. Use this during authentication so the search centres
            on the enrolled frequencies, not the theoretical baseline.
            Window is ±2% when reference_hz is None (enrollment),
            ±1.5% when reference_hz is provided (authentication).
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

    # Choose search centres and window fraction
    if reference_hz is not None:
        search_centers = np.array(reference_hz, dtype=float)
        window_frac = 0.015   # ±1.5% around enrolled frequency
    else:
        search_centers = baseline
        window_frac = 0.020   # ±2% around theoretical baseline (was 0.5%)

    # Find the peak frequency nearest each expected mode
    perturbed_hz = np.zeros(N_MODES)
    for i, f_center in enumerate(search_centers[:N_MODES]):
        window = f_center * window_frac
        mask = (freq_axis >= f_center - window) & (freq_axis <= f_center + window)
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
            # Fallback: no peak found in window, use search centre
            perturbed_hz[i] = f_center

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


# ── Wizard-mode scope management ──────────────────────────────────────────
# Persistent state for the experiment wizard (configure once, capture many)

_scope_handle = None   # ctypes handle (ps2000a) or int (ps2000)
_scope_open = False
_scope_config: dict = {}


def is_scope_busy() -> bool:
    """Return True if the scope is held open by the wizard."""
    return _scope_open


def get_experiment_presets() -> dict:
    """Return a summary of available experiment presets."""
    return {
        k: {
            "name": v["name"],
            "description": v["description"],
            "view": v["view"],
            "firebase_id": v.get("firebase_id"),
        }
        for k, v in EXPERIMENT_PRESETS.items()
    }


def get_scope_status() -> dict:
    """Return current scope connection status and active configuration."""
    global _driver_api
    hw = False
    if _scope_open:
        hw = True
    elif _driver_api is not None:
        hw = True
    else:
        hw = check_hardware()

    return {
        "hardware_available": hw,
        "scope_open": _scope_open,
        "driver": _driver_api,
        "config": _get_config_summary() if _scope_config else None,
    }


def _get_config_summary() -> dict:
    c = _scope_config
    if not c:
        return {}
    return {
        "preset": c.get("_preset_id", ""),
        "name": c.get("name", ""),
        "awg_mode": c.get("awg_mode", "off"),
        "range_mv": c.get("range_mv", 500),
        "view": c.get("view", "spectrum"),
        "simulated": c.get("simulated", False),
    }


def _open_scope():
    """Open the scope handle.  Reuses existing handle if already open."""
    global _scope_handle, _scope_open, _driver_api

    if _scope_open and _scope_handle is not None:
        return _scope_handle

    # Ensure driver is detected
    if _driver_api is None:
        if not check_hardware():
            return None

    if _driver_api == "ps2000a":
        import ctypes
        from picosdk.ps2000a import ps2000a
        handle = ctypes.c_int16()
        status = ps2000a.ps2000aOpenUnit(ctypes.byref(handle), None)
        if status == 0:
            _scope_handle = handle
            _scope_open = True
            return handle
    elif _driver_api == "ps2000":
        from picosdk.ps2000 import ps2000
        handle = ps2000.ps2000_open_unit()
        if handle > 0:
            _scope_handle = handle
            _scope_open = True
            return handle

    return None


def close_scope() -> dict:
    """Close the scope handle and reset wizard state."""
    global _scope_handle, _scope_open, _scope_config

    if not _scope_open:
        return {"ok": True, "message": "Already closed"}

    try:
        if _driver_api == "ps2000a":
            from picosdk.ps2000a import ps2000a
            ps2000a.ps2000aStop(_scope_handle)
            ps2000a.ps2000aCloseUnit(_scope_handle)
        elif _driver_api == "ps2000":
            from picosdk.ps2000 import ps2000
            ps2000.ps2000_stop(_scope_handle)
            ps2000.ps2000_close_unit(_scope_handle)
    except Exception:
        pass

    _scope_handle = None
    _scope_open = False
    _scope_config = {}
    return {"ok": True}


def configure_scope(preset_id: str, pattern_name: str = "A",
                    awg_freq_hz: float = None) -> dict:
    """Configure the scope for a specific experiment preset.

    Opens the scope handle if not open and applies all channel, trigger,
    and AWG settings from the preset.  Returns the active configuration
    summary.
    """
    global _scope_config
    import ctypes
    import time as _time

    if preset_id not in EXPERIMENT_PRESETS:
        return {"error": f"Unknown preset: {preset_id}"}

    config = dict(EXPERIMENT_PRESETS[preset_id])
    config["_preset_id"] = preset_id
    config["pattern_name"] = pattern_name
    if awg_freq_hz is not None:
        config["awg_freq_hz"] = awg_freq_hz

    handle = _open_scope()
    if handle is None:
        # Fall back to simulation
        config["simulated"] = True
        _scope_config = config
        return {"ok": True, "config": _get_config_summary(), "simulated": True}

    range_mv = config.get("range_mv", 500)
    range_enum = VOLTAGE_RANGE_ENUM.get(range_mv, 5)

    try:
        if _driver_api == "ps2000":
            from picosdk.ps2000 import ps2000

            # Channel A: enabled, DC coupling
            ps2000.ps2000_set_channel(handle, 0, True, 1, range_enum)
            # Disable Channel B
            ps2000.ps2000_set_channel(handle, 1, False, 1, range_enum)

            # Trigger
            if config.get("trigger_enabled"):
                thresh_adc = int(
                    config.get("trigger_threshold_mv", 5) / range_mv * 32767
                )
                ps2000.ps2000_set_trigger(
                    handle,
                    config.get("trigger_source", 0),
                    thresh_adc,
                    config.get("trigger_direction", 0),
                    0,
                    config.get("trigger_auto_ms", 1000),
                )
            else:
                # No trigger — immediate auto
                ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)

            # AWG
            _configure_awg_ps2000(handle, config, pattern_name)

        elif _driver_api == "ps2000a":
            from picosdk.ps2000a import ps2000a
            from picosdk.functions import assert_pico_ok

            assert_pico_ok(
                ps2000a.ps2000aSetChannel(handle, 0, 1, 1, range_enum, 0.0)
            )

            if config.get("trigger_enabled"):
                thresh_adc = int(
                    config.get("trigger_threshold_mv", 5) / range_mv * 32767
                )
                assert_pico_ok(
                    ps2000a.ps2000aSetSimpleTrigger(
                        handle, 1, 0, thresh_adc, 2, 0,
                        config.get("trigger_auto_ms", 1000),
                    )
                )
            else:
                assert_pico_ok(
                    ps2000a.ps2000aSetSimpleTrigger(handle, 0, 0, 0, 0, 0, 1)
                )

            _configure_awg_ps2000a(handle, config, pattern_name)

    except Exception as e:
        config["setup_error"] = str(e)

    _scope_config = config
    return {"ok": True, "config": _get_config_summary()}


def _configure_awg_ps2000(handle, config: dict, pattern_name: str):
    """Set AWG output on the ps2000 driver."""
    import ctypes
    from picosdk.ps2000 import ps2000

    awg_mode = config.get("awg_mode", "off")

    if awg_mode == "off":
        try:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0
            )
        except Exception:
            pass

    elif awg_mode == "sine":
        freq = float(config.get("awg_freq_hz", 17700))
        amp = config.get("awg_amplitude_uvpp", 500_000)
        shots = config.get("awg_shots", 0)
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, amp, 0, freq, freq, 0.0, 0.0, 0, shots
        )

    elif awg_mode == "sweep":
        start = float(config.get("awg_start_freq_hz", 1000))
        stop = float(config.get("awg_stop_freq_hz", 200000))
        amp = config.get("awg_amplitude_uvpp", 500_000)
        sweep_time = config.get("awg_sweep_time_s", 1.0)
        dwell = 0.001
        increment = (stop - start) * dwell / sweep_time
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, amp, 0, start, stop, increment, dwell, 0, 1
        )

    elif awg_mode == "arbitrary":
        awg_data = _load_awg_waveform(pattern_name)
        amp = config.get("awg_amplitude_uvpp", 400_000)
        awg_int16 = (awg_data * 32767).astype(np.int16)
        awg_buffer = (ctypes.c_int16 * len(awg_int16))(*awg_int16)
        ps2000.ps2000_set_sig_gen_arbitrary(
            handle, 0, amp, 0, 0, 0, 0, awg_buffer, len(awg_int16), 0, 0
        )


def _configure_awg_ps2000a(handle, config: dict, pattern_name: str):
    """Set AWG output on the ps2000a driver."""
    import ctypes
    from picosdk.ps2000a import ps2000a
    from picosdk.functions import assert_pico_ok

    awg_mode = config.get("awg_mode", "off")

    if awg_mode == "off":
        try:
            assert_pico_ok(
                ps2000a.ps2000aSetSigGenBuiltIn(
                    handle, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0
                )
            )
        except Exception:
            pass

    elif awg_mode == "sine":
        freq = float(config.get("awg_freq_hz", 17700))
        amp = config.get("awg_amplitude_uvpp", 500_000)
        shots = config.get("awg_shots", 0)
        assert_pico_ok(
            ps2000a.ps2000aSetSigGenBuiltIn(
                handle, 0, amp, 0, freq, freq, 0, 0, 0, shots, 0, 0, 0, 0
            )
        )

    elif awg_mode == "sweep":
        start = float(config.get("awg_start_freq_hz", 1000))
        stop = float(config.get("awg_stop_freq_hz", 200000))
        amp = config.get("awg_amplitude_uvpp", 500_000)
        sweep_time = config.get("awg_sweep_time_s", 1.0)
        dwell = 0.001
        increment = (stop - start) * dwell / sweep_time
        assert_pico_ok(
            ps2000a.ps2000aSetSigGenBuiltIn(
                handle, 0, amp, 0, start, stop, increment, dwell, 0, 1,
                0, 0, 0, 0,
            )
        )

    elif awg_mode == "arbitrary":
        awg_data = _load_awg_waveform(pattern_name)
        amp = config.get("awg_amplitude_uvpp", 400_000)
        awg_int16 = (awg_data * 32767).astype(np.int16)
        awg_buffer = (ctypes.c_int16 * len(awg_int16))(*awg_int16)
        assert_pico_ok(
            ps2000a.ps2000aSetSigGenArbitrary(
                handle, 0, amp, 0, 0, 0, 0,
                awg_buffer, len(awg_int16), 0, 0, 0, 0, 0, 0, 0, 0,
            )
        )


def capture_block() -> dict:
    """Run a block capture using the current wizard configuration.

    Returns time-domain waveform data (time_us, voltage_mv) plus metadata.
    Falls back to simulation if no hardware is available.
    """
    if not _scope_config:
        return {"error": "Scope not configured. Call configure_scope first."}

    config = _scope_config

    # Simulation fallback
    if config.get("simulated") or not _scope_open:
        return simulate_capture(config)

    max_buf = 3968 if _driver_api == "ps2000" else 8192
    samples = min(config.get("samples", max_buf), max_buf)
    timebase = config.get("timebase", 3)
    averages = config.get("averages", 1)
    range_mv = config.get("range_mv", 500)

    import ctypes
    import time as _time

    handle = _scope_handle
    accumulated = np.zeros(samples, dtype=np.float64)
    n_actual = 0

    if _driver_api == "ps2000":
        from picosdk.ps2000 import ps2000

        for _ in range(averages):
            time_ms_c = ctypes.c_int32()
            ps2000.ps2000_run_block(
                handle, samples, timebase, 1, ctypes.byref(time_ms_c)
            )

            t0 = _time.time()
            while ps2000.ps2000_ready(handle) == 0:
                _time.sleep(0.001)
                if _time.time() - t0 > 10:
                    break

            buf_a = (ctypes.c_int16 * samples)()
            buf_b = (ctypes.c_int16 * samples)()
            overflow = ctypes.c_int16()
            n = ps2000.ps2000_get_values(
                handle,
                ctypes.byref(buf_a), ctypes.byref(buf_b),
                None, None,
                ctypes.byref(overflow), samples,
            )
            if n > 0:
                accumulated[:n] += np.array(buf_a[:n], dtype=np.float64)
                n_actual = max(n_actual, n)

    elif _driver_api == "ps2000a":
        from picosdk.ps2000a import ps2000a
        from picosdk.functions import assert_pico_ok

        n_actual = samples
        for _ in range(averages):
            buf_a = (ctypes.c_int16 * samples)()
            assert_pico_ok(
                ps2000a.ps2000aSetDataBuffer(
                    handle, 0, ctypes.byref(buf_a), samples, 0, 0
                )
            )
            tb = ctypes.c_uint32(timebase)
            assert_pico_ok(
                ps2000a.ps2000aRunBlock(
                    handle, 0, samples, tb, None, 0, None, None
                )
            )
            ready = ctypes.c_int16(0)
            t0 = _time.time()
            while ready.value == 0:
                assert_pico_ok(
                    ps2000a.ps2000aIsReady(handle, ctypes.byref(ready))
                )
                _time.sleep(0.001)
                if _time.time() - t0 > 10:
                    break
            n_captured = ctypes.c_int32(samples)
            ov = ctypes.c_int16()
            assert_pico_ok(
                ps2000a.ps2000aGetValues(
                    handle, 0, ctypes.byref(n_captured), 0, 0, 0,
                    ctypes.byref(ov),
                )
            )
            accumulated += np.array(
                buf_a[:n_captured.value], dtype=np.float64
            )
            n_actual = n_captured.value
    else:
        return {"error": "No driver available"}

    averaged = accumulated / max(averages, 1)
    voltage_mv = (averaged[:n_actual] * range_mv / 32767.0).tolist()

    # Time axis
    interval_us = float(timebase - 2) if timebase >= 3 else 0.01 * (2 ** timebase)
    sample_rate = 1_000_000.0 / interval_us
    time_us = (np.arange(n_actual) * interval_us).tolist()

    return {
        "time_us": time_us,
        "voltage_mv": voltage_mv,
        "sample_rate": sample_rate,
        "n_samples": n_actual,
        "range_mv": range_mv,
        "timebase": timebase,
        "averages": averages,
    }


def compute_spectrum(voltage_mv: list, sample_rate: float) -> dict:
    """Compute FFT spectrum from time-domain waveform data.

    Returns frequency axis (Hz), magnitude (dB), and detected peaks.
    """
    data = np.array(voltage_mv, dtype=np.float64)
    n = len(data)
    if n < 4:
        return {"freq_hz": [], "magnitude_db": [], "peaks": []}

    windowed = data * np.hanning(n)
    spectrum = np.fft.rfft(windowed)
    magnitude = np.abs(spectrum) * 2.0 / n
    magnitude_db = 20 * np.log10(np.maximum(magnitude, 1e-10))
    freq_hz = np.fft.rfftfreq(n, d=1.0 / sample_rate)

    peaks = _find_spectral_peaks(freq_hz, magnitude_db)

    # Compute noise floor and SNR
    if len(magnitude_db) > 10:
        sorted_mags = np.sort(magnitude_db)
        noise_floor = float(np.median(sorted_mags[:len(sorted_mags) // 2]))
    else:
        noise_floor = -100.0

    peak_max = peaks[0]["magnitude_db"] if peaks else noise_floor
    snr = round(peak_max - noise_floor, 1)

    return {
        "freq_hz": freq_hz.tolist(),
        "magnitude_db": magnitude_db.tolist(),
        "peaks": peaks,
        "noise_floor_db": round(noise_floor, 1),
        "snr_db": snr,
        "freq_resolution_hz": round(float(sample_rate / n), 1),
        "max_freq_hz": round(float(sample_rate / 2), 1),
    }


def _find_spectral_peaks(freq_hz, magnitude_db,
                         threshold_db: float = -40,
                         min_distance_hz: float = 500) -> list:
    """Detect spectral peaks above threshold with minimum spacing."""
    mag = np.array(magnitude_db)
    freq = np.array(freq_hz)

    peaks = []
    for i in range(2, len(mag) - 2):
        if (mag[i] > threshold_db
                and mag[i] > mag[i - 1] and mag[i] > mag[i + 1]
                and mag[i] > mag[i - 2] and mag[i] > mag[i + 2]):
            # Filter by minimum distance
            too_close = False
            for p in peaks:
                if abs(freq[i] - p["freq_hz"]) < min_distance_hz:
                    if mag[i] > p["magnitude_db"]:
                        peaks.remove(p)
                    else:
                        too_close = True
                    break

            if not too_close:
                # Parabolic interpolation
                alpha, beta, gamma = mag[i - 1], mag[i], mag[i + 1]
                denom = alpha - 2 * beta + gamma
                if abs(denom) > 1e-10:
                    delta = 0.5 * (alpha - gamma) / denom
                    refined_freq = freq[i] + delta * (freq[1] - freq[0])
                    refined_mag = beta - 0.25 * (alpha - gamma) * delta
                else:
                    refined_freq, refined_mag = freq[i], beta

                peaks.append({
                    "freq_hz": round(float(refined_freq), 1),
                    "magnitude_db": round(float(refined_mag), 1),
                })

    peaks.sort(key=lambda p: p["freq_hz"])
    return peaks[:50]


def simulate_capture(config: dict = None) -> dict:
    """Generate simulated capture data for testing without hardware."""
    if config is None:
        config = EXPERIMENT_PRESETS.get("exp03", {})

    baseline = _get_baseline_freqs()
    n_samples = min(config.get("samples", 3968), 3968)
    t = np.arange(n_samples) / SAMPLE_RATE
    rng = np.random.default_rng(42)
    signal = np.zeros(n_samples)

    awg_mode = config.get("awg_mode", "sweep")

    if awg_mode == "off":
        # Tap response — decaying sinusoids
        for i, freq in enumerate(baseline):
            amp = 5.0 / (i + 1)
            signal += amp * np.sin(2 * np.pi * freq * t) * np.exp(-(50 + 10 * i) * t)
    else:
        # AWG-excited steady-state
        for i, freq in enumerate(baseline):
            amp = 3.0 / (1 + 0.5 * i)
            jitter = freq * (1 + rng.normal(0, 0.001))
            signal += amp * np.sin(2 * np.pi * jitter * t)

    range_mv = config.get("range_mv", 500)
    noise = rng.normal(0, range_mv * 0.005, n_samples)
    voltage_mv = np.clip(signal + noise, -range_mv, range_mv)

    return {
        "time_us": (t * 1_000_000).tolist(),
        "voltage_mv": voltage_mv.tolist(),
        "sample_rate": float(SAMPLE_RATE),
        "n_samples": n_samples,
        "range_mv": range_mv,
        "timebase": 3,
        "averages": 1,
        "simulated": True,
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
