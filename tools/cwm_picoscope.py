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
# NOTE: The ps2000 macOS driver has a time-unit bug — it reports picoseconds
# but actually means nanoseconds.  Timebase 7 = 1280 ns/sample = 781.25 kHz.
# This gives Nyquist of 390 kHz (covers all 20 rod modes up to ~350 kHz)
# and with 8064 samples × 4× zero-pad → 24 Hz frequency resolution.
TIMEBASE = 7              # ps2000 timebase index
DT_NS = 1280              # sample interval in nanoseconds (timebase 7)
SAMPLE_RATE = int(1e9 / DT_NS)   # 781250 Hz
N_SAMPLES = 8064          # capture buffer (ps2000 max at this timebase)
AWG_BUFFER = 8192         # AWG output buffer
VOLTAGE_RANGE_MV = 500    # ±500 mV
SETTLE_MS = 20            # wait after AWG starts before capture
AVERAGES = 16             # number of captures to average for SNR
TAP_TRIGGER_MV = 200      # trigger threshold for tap detection (mV)
TAP_TIMEOUT_MS = 20000    # how long to wait for a tap (ms)
AWG_CHIRP_LO = 1000.0     # AWG chirp start frequency (Hz)
AWG_CHIRP_HI = 100000.0   # AWG chirp stop frequency (Hz) — PS2204A sig gen max
AWG_DRIVE_UVPP = 2_000_000  # AWG amplitude for parallel search (2 Vpp max)
AWG_SETTLE_S = 0.15       # wait for AWG stabilisation before capture

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


def _capture_and_fft() -> tuple:
    """Capture a tap ring-down and return (freq_axis, magnitude, bin_hz).

    Handles driver selection, trigger arming, and 4× zero-padded FFT.
    Used by both enrollment and authentication paths.
    """
    global _driver_api
    if _driver_api is None:
        if not check_hardware():
            raise RuntimeError("No PicoScope detected")

    if _driver_api == "ps2000a":
        captures = _capture_ps2000a()
    else:
        captures = _capture_ps2000()

    if not captures:
        raise RuntimeError("No captures returned from PicoScope")

    cap_len = len(captures[0])
    n_fft = cap_len * 4
    freq_axis = np.fft.rfftfreq(n_fft, d=1.0 / SAMPLE_RATE)
    bin_hz = freq_axis[1] - freq_axis[0]

    accumulated_mag = np.zeros(n_fft // 2 + 1, dtype=np.float64)
    for raw in captures:
        windowed = raw[:cap_len] * np.hanning(cap_len)
        spectrum = np.fft.rfft(windowed, n=n_fft)
        accumulated_mag += np.abs(spectrum)
    magnitude = accumulated_mag / len(captures)

    return freq_axis, magnitude, bin_hz


def _extract_peaks_blind(freq_axis, magnitude, bin_hz) -> list:
    """Find strongest peaks above noise floor (enrollment mode).

    Returns list of refined peak frequencies sorted ascending, up to N_MODES.
    """
    from scipy.signal import find_peaks as _find_peaks

    noise_floor = np.median(magnitude)
    min_snr = 10.0
    min_dist_bins = max(1, int(200 / bin_hz))
    min_freq = 500.0  # ignore mains hum, cable pickup, and box resonances

    peaks, _ = _find_peaks(
        magnitude, height=noise_floor * min_snr, distance=min_dist_bins
    )
    peaks = peaks[freq_axis[peaks] >= min_freq]

    if len(peaks) == 0:
        raise RuntimeError(
            "No spectral peaks found above noise floor. "
            "Flick the rod harder or check PZT connection."
        )

    heights = magnitude[peaks]
    top_idx = np.argsort(heights)[::-1][:N_MODES]
    top_peaks = peaks[top_idx]
    top_peaks = top_peaks[np.argsort(freq_axis[top_peaks])]

    def _parabolic(idx):
        if 0 < idx < len(magnitude) - 1:
            a, b, c = magnitude[idx - 1], magnitude[idx], magnitude[idx + 1]
            denom = 2 * b - a - c
            if denom != 0:
                delta = 0.5 * (a - c) / denom
                return freq_axis[idx] + delta * bin_hz
        return freq_axis[idx]

    return [_parabolic(p) for p in top_peaks]


def _extract_peaks_ref(freq_axis, magnitude, bin_hz,
                       reference_hz, window_frac=0.05) -> np.ndarray:
    """Search for peaks near enrolled reference frequencies.

    For each reference frequency, finds the highest magnitude within
    ±window_frac and checks if it's a genuine peak (above noise floor).
    Returns array of found frequencies (0.0 where no peak detected).
    """
    noise_floor = np.median(magnitude)
    min_peak_height = noise_floor * 3.0  # must be above 3× noise

    def _parabolic(idx):
        if 0 < idx < len(magnitude) - 1:
            a, b, c = magnitude[idx - 1], magnitude[idx], magnitude[idx + 1]
            denom = 2 * b - a - c
            if denom != 0:
                delta = 0.5 * (a - c) / denom
                return freq_axis[idx] + delta * bin_hz
        return freq_axis[idx]

    search_centers = np.array(reference_hz, dtype=float)
    result = np.zeros(len(search_centers))
    for i, f_center in enumerate(search_centers):
        if f_center <= 0:
            continue
        window = f_center * window_frac
        mask = (freq_axis >= f_center - window) & (freq_axis <= f_center + window)
        if np.any(mask):
            idx_in_window = np.where(mask)[0]
            best = idx_in_window[np.argmax(magnitude[mask])]
            if magnitude[best] >= min_peak_height:
                result[i] = _parabolic(best)
    return result


def measure_rod_fingerprint(
    rod_id: int = 1,
    pattern_name: str = "A",
    rod_length_mm: float = 150.0,
    rod_diameter_mm: float = 6.0,
    reference_hz=None,
) -> dict:
    """
    Measure a real rod's spectral fingerprint via PicoScope.

    Tap-triggered: arms the scope at 200 mV trigger, waits for a
    fingernail flick on the glass rod, captures the ring-down, and
    extracts spectral peaks from the 4×-zero-padded FFT.

    Enrollment mode (reference_hz=None):
        Blind peak search — finds the strongest spectral peaks above
        10× noise floor, sorted by frequency.  No theoretical baselines.

    Authentication mode (reference_hz provided):
        Searches ±5% windows around the enrolled peak frequencies.

    Returns: {perturbed_hz, shift_hz, fingerprint, n_peaks_found}
    """
    freq_axis, magnitude, bin_hz = _capture_and_fft()

    if reference_hz is not None:
        perturbed_hz = _extract_peaks_ref(
            freq_axis, magnitude, bin_hz, reference_hz
        )
        search_centers = np.array(reference_hz, dtype=float)
        n_found = int(np.count_nonzero(perturbed_hz))
        shift_hz = perturbed_hz - search_centers
    else:
        refined = _extract_peaks_blind(freq_axis, magnitude, bin_hz)
        n_found = len(refined)
        while len(refined) < N_MODES:
            refined.append(0.0)
        perturbed_hz = np.array(refined[:N_MODES])
        shift_hz = np.zeros(N_MODES)

    return {
        "perturbed_hz": perturbed_hz.tolist(),
        "shift_hz": shift_hz.tolist(),
        "fingerprint": perturbed_hz.tolist(),
        "n_peaks_found": n_found,
    }


def score_spectrum_against_rod(freq_axis, magnitude, bin_hz,
                               enrolled_hz, n_modes=10) -> dict:
    """Score a live spectrum against one enrolled rod's peaks.

    Searches ±5% around each enrolled peak.  Returns:
      - score: combined metric (lower = better match). Penalises both
        frequency deviation AND missed peaks so a rod with 8/10 matches
        at 2% beats a rod with 7/10 at 1.9%.
      - rms: fractional RMS deviation for matched peaks only
      - n_matched: how many enrolled peaks found in live spectrum
      - n_total: how many enrolled peaks tested
    """
    enr = np.array(enrolled_hz, dtype=float)
    enr_nonzero = enr[enr > 0][:n_modes]

    found = _extract_peaks_ref(freq_axis, magnitude, bin_hz, enr_nonzero)
    matched_fracs = []
    for i, ef in enumerate(enr_nonzero):
        if found[i] > 0:
            matched_fracs.append(abs(found[i] - ef) / ef)

    n_total = len(enr_nonzero)
    n_matched = len(matched_fracs)

    if n_matched >= 3:
        rms = float(np.sqrt(np.mean(np.array(matched_fracs) ** 2)))
        # Penalty for missed peaks: each miss adds 5% (the window size)
        # to the effective distance, so a rod with fewer matches scores worse
        n_missed = n_total - n_matched
        miss_penalty = n_missed * 0.05
        score = rms + miss_penalty
    else:
        rms = float("inf")
        score = float("inf")

    return {
        "score": score,
        "rms": rms,
        "n_matched": n_matched,
        "n_total": len(enr_nonzero),
    }


def score_spectrum_energy(freq_axis, magnitude, bin_hz,
                          enrolled_hz, n_modes=10) -> dict:
    """Score a live spectrum by total energy at a rod's enrolled peaks.

    Unlike score_spectrum_against_rod (which measures frequency deviation),
    this measures how much energy the rod contributes to the aggregate
    response — the correct metric for AWG-driven parallel search.

    Returns:
      - energy: sum of magnitudes at enrolled peak locations
      - mean_snr: average SNR at enrolled peak locations
      - n_detected: peaks above 3× noise floor
      - n_total: enrolled peaks tested
    """
    enr = np.array(enrolled_hz, dtype=float)
    enr_nonzero = enr[enr > 0][:n_modes]
    noise_floor = np.median(magnitude)
    if noise_floor <= 0:
        noise_floor = 1.0

    total_energy = 0.0
    snr_vals = []
    n_detected = 0
    window_bins = max(1, int(200 / bin_hz))  # ±200 Hz search window

    for f_center in enr_nonzero:
        idx = np.argmin(np.abs(freq_axis - f_center))
        lo = max(0, idx - window_bins)
        hi = min(len(magnitude), idx + window_bins + 1)
        local_max = np.max(magnitude[lo:hi])
        total_energy += local_max
        snr = local_max / noise_floor
        snr_vals.append(snr)
        if snr >= 3.0:
            n_detected += 1

    mean_snr = float(np.mean(snr_vals)) if snr_vals else 0.0

    return {
        "energy": float(total_energy),
        "mean_snr": mean_snr,
        "n_detected": n_detected,
        "n_total": len(enr_nonzero),
    }


# ── Two-PZT AWG-driven capture (parallel search) ─────────────────────────
#
# Topology:
#   AWG OUT → Drive PZTs (all rods in parallel, one PZT per rod)
#   Ch A    → Sense PZTs (all rods in parallel, second PZT per rod)
#   Ch B    → (optional) individual rod diagnostic
#
# The AWG excites all rods simultaneously with a multi-tone query.
# Ch A picks up the aggregate acoustic response from the sense PZTs.
# The rod whose eigenmode fingerprint best matches the query absorbs
# the most energy and dominates the aggregate signal.
#
# Because drive and sense are physically separate transducers on
# opposite ends of each rod, Ch A sees only the acoustic response —
# no direct electrical feed-through of the drive signal.

def _build_multitone(frequencies_hz, n_samples=None, sample_rate=None,
                     amplitudes=None):
    """Synthesize a multi-tone waveform from a list of frequencies.

    Returns a float64 array normalised to ±1.0.
    """
    sr = sample_rate or SAMPLE_RATE
    ns = n_samples or N_SAMPLES
    t = np.arange(ns) / sr
    signal = np.zeros(ns, dtype=np.float64)

    for i, f in enumerate(frequencies_hz):
        if f <= 0:
            continue
        amp = amplitudes[i] if amplitudes is not None else 1.0
        signal += amp * np.sin(2 * np.pi * f * t)

    peak = np.max(np.abs(signal))
    if peak > 0:
        signal /= peak
    return signal


def _capture_awg_driven_ps2000(awg_mode="sweep", awg_freq_hz=None,
                                awg_start_hz=None, awg_stop_hz=None,
                                multitone_hz=None, n_averages=4) -> list:
    """AWG-driven capture using separate drive/sense PZTs (ps2000).

    Starts the AWG, waits for stabilisation, captures response on Ch A.
    No trigger — free-running auto-capture since the AWG runs continuously.
    Returns a list of raw ADC captures (float64 arrays).

    AWG modes:
      - "sweep": broadband chirp from awg_start_hz to awg_stop_hz
      - "sine":  fixed frequency at awg_freq_hz
      - "multitone": arbitrary waveform summing frequencies in multitone_hz
    """
    import ctypes
    import time
    from picosdk.ps2000 import ps2000

    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")

    try:
        # Ch A = sense PZTs, DC coupling, ±500 mV
        ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
        # Ch B off (could enable for per-rod diagnostic later)
        ps2000.ps2000_set_channel(handle, 1, False, 1, 6)

        # ── Configure AWG on drive PZTs ──────────────────────────────
        if awg_mode == "sweep":
            lo = awg_start_hz or AWG_CHIRP_LO
            hi = awg_stop_hz or AWG_CHIRP_HI
            # Sweep increment: cover range in ~0.5 s
            dwell = 0.001
            sweep_time = 0.5
            increment = (hi - lo) * dwell / sweep_time
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(lo), float(hi),
                float(increment), float(dwell),
                0, 0  # sweep up, continuous
            )

        elif awg_mode == "sine":
            freq = float(awg_freq_hz or 10000)
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                freq, freq, 0.0, 0.0, 0, 0
            )

        elif awg_mode == "multitone" and multitone_hz is not None:
            # PS2000 arb: 4096-sample buffer, 48 MHz clock, 32-bit phase
            # accumulator.  Buffer repeats at f_rep = delta_phase * 48e6 / 2^32.
            # Each target tone must be an integer harmonic of f_rep.
            #
            # Strategy: pick f_rep so that all target freqs are integer
            # multiples.  f_rep = 10 Hz works for freqs up to 20 kHz
            # (Nyquist = 4096/2 * 10 = 20480 Hz).
            arb_len = 4096
            f_rep = 10.0  # buffer repeats at 10 Hz
            delta_phase = int(f_rep * (2**32) / 48_000_000)
            if delta_phase < 1:
                delta_phase = 1

            # Build buffer: sum of sinusoids at integer harmonics
            buf_signal = np.zeros(arb_len, dtype=np.float64)
            for f_target in multitone_hz:
                if f_target <= 0:
                    continue
                k = round(f_target / f_rep)  # harmonic number
                if k < 1 or k > arb_len // 2:
                    continue
                phase = 2 * np.pi * k * np.arange(arb_len) / arb_len
                buf_signal += np.sin(phase)

            # Normalise to ±1 then map to unsigned 8-bit (0–255)
            peak = np.max(np.abs(buf_signal))
            if peak > 0:
                buf_signal /= peak
            arb_u8 = ((buf_signal * 127) + 128).clip(0, 255).astype(np.uint8)
            arb_buf = (ctypes.c_uint8 * arb_len)(*arb_u8.tolist())

            ps2000.ps2000_set_sig_gen_arbitrary(
                handle, 0, AWG_DRIVE_UVPP,
                delta_phase, delta_phase,
                0, 0,
                arb_buf, arb_len, 0, 0
            )

        # ── Wait for AWG to stabilise and rod to reach steady state ──
        time.sleep(AWG_SETTLE_S)

        # ── Auto-trigger (no external trigger — AWG is always on) ────
        ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)  # source=none, auto=1ms

        # ── Capture n_averages blocks ────────────────────────────────
        captures = []
        for _ in range(n_averages):
            time_ms = ctypes.c_int32()
            ps2000.ps2000_run_block(
                handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(time_ms)
            )

            t0 = time.time()
            while ps2000.ps2000_ready(handle) == 0:
                time.sleep(0.001)
                if time.time() - t0 > 5:
                    break

            buf_a = (ctypes.c_int16 * N_SAMPLES)()
            buf_b = (ctypes.c_int16 * N_SAMPLES)()
            overflow = ctypes.c_int16()
            n = ps2000.ps2000_get_values(
                handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                None, None, ctypes.byref(overflow), N_SAMPLES
            )
            if n > 0:
                captures.append(np.array(buf_a[:n], dtype=np.float64))

        # ── Turn off AWG ─────────────────────────────────────────────
        try:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0
            )
        except Exception:
            pass

        return captures

    finally:
        ps2000.ps2000_stop(handle)
        ps2000.ps2000_close_unit(handle)


def _capture_awg_driven_ps2000a(awg_mode="sweep", awg_freq_hz=None,
                                 awg_start_hz=None, awg_stop_hz=None,
                                 multitone_hz=None, n_averages=4) -> list:
    """AWG-driven capture using ps2000a driver.  Same as ps2000 version."""
    import ctypes
    import time
    from picosdk.ps2000a import ps2000a
    from picosdk.functions import assert_pico_ok

    handle = ctypes.c_int16()
    assert_pico_ok(ps2000a.ps2000aOpenUnit(ctypes.byref(handle), None))

    try:
        assert_pico_ok(ps2000a.ps2000aSetChannel(handle, 0, 1, 1, 5, 0.0))

        if awg_mode == "sweep":
            lo = awg_start_hz or AWG_CHIRP_LO
            hi = awg_stop_hz or AWG_CHIRP_HI
            dwell = 0.001
            sweep_time = 0.5
            increment = (hi - lo) * dwell / sweep_time
            assert_pico_ok(ps2000a.ps2000aSetSigGenBuiltIn(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(lo), float(hi),
                float(increment), float(dwell),
                0, 0, 0, 0, 0, 0
            ))

        elif awg_mode == "sine":
            freq = float(awg_freq_hz or 10000)
            assert_pico_ok(ps2000a.ps2000aSetSigGenBuiltIn(
                handle, 0, AWG_DRIVE_UVPP, 0,
                freq, freq, 0, 0, 0, 0, 0, 0, 0, 0
            ))

        time.sleep(AWG_SETTLE_S)

        # Auto-trigger
        assert_pico_ok(ps2000a.ps2000aSetSimpleTrigger(
            handle, 0, 0, 0, 0, 0, 1
        ))

        captures = []
        for _ in range(n_averages):
            buf_a = (ctypes.c_int16 * N_SAMPLES)()
            assert_pico_ok(ps2000a.ps2000aSetDataBuffer(
                handle, 0, ctypes.byref(buf_a), N_SAMPLES, 0, 0
            ))
            tb = ctypes.c_uint32(TIMEBASE)
            assert_pico_ok(ps2000a.ps2000aRunBlock(
                handle, 0, N_SAMPLES, tb, None, 0, None, None
            ))
            ready = ctypes.c_int16(0)
            t0 = time.time()
            while ready.value == 0:
                assert_pico_ok(ps2000a.ps2000aIsReady(
                    handle, ctypes.byref(ready)
                ))
                time.sleep(0.001)
                if time.time() - t0 > 5:
                    break
            n_captured = ctypes.c_int32(N_SAMPLES)
            ov = ctypes.c_int16()
            assert_pico_ok(ps2000a.ps2000aGetValues(
                handle, 0, ctypes.byref(n_captured), 0, 0, 0, ctypes.byref(ov)
            ))
            if n_captured.value > 0:
                captures.append(
                    np.array(buf_a[:n_captured.value], dtype=np.float64)
                )

        # Turn off AWG
        try:
            assert_pico_ok(ps2000a.ps2000aSetSigGenBuiltIn(
                handle, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0
            ))
        except Exception:
            pass

        return captures

    finally:
        ps2000a.ps2000aStop(handle)
        ps2000a.ps2000aCloseUnit(handle)


def capture_awg_driven(awg_mode="sweep", awg_freq_hz=None,
                       awg_start_hz=None, awg_stop_hz=None,
                       multitone_hz=None, n_averages=4):
    """AWG-driven capture with automatic driver selection.

    Returns (freq_axis, magnitude, bin_hz) — same as _capture_and_fft()
    but using AWG excitation on separate drive PZTs instead of tap.

    Topology (two-PZT per rod):
      AWG OUT → Drive PZTs (all rods in parallel)
      Ch A    → Sense PZTs (all rods in parallel)
    """
    global _driver_api
    if _driver_api is None:
        if not check_hardware():
            raise RuntimeError("No PicoScope detected")

    if _driver_api == "ps2000a":
        captures = _capture_awg_driven_ps2000a(
            awg_mode=awg_mode, awg_freq_hz=awg_freq_hz,
            awg_start_hz=awg_start_hz, awg_stop_hz=awg_stop_hz,
            multitone_hz=multitone_hz, n_averages=n_averages,
        )
    else:
        captures = _capture_awg_driven_ps2000(
            awg_mode=awg_mode, awg_freq_hz=awg_freq_hz,
            awg_start_hz=awg_start_hz, awg_stop_hz=awg_stop_hz,
            multitone_hz=multitone_hz, n_averages=n_averages,
        )

    if not captures:
        raise RuntimeError("No captures returned (AWG-driven mode)")

    cap_len = len(captures[0])
    n_fft = cap_len * 4
    freq_axis = np.fft.rfftfreq(n_fft, d=1.0 / SAMPLE_RATE)
    bin_hz = freq_axis[1] - freq_axis[0]

    accumulated_mag = np.zeros(n_fft // 2 + 1, dtype=np.float64)
    for raw in captures:
        windowed = raw[:cap_len] * np.hanning(cap_len)
        spectrum = np.fft.rfft(windowed, n=n_fft)
        accumulated_mag += np.abs(spectrum)
    magnitude = accumulated_mag / len(captures)

    return freq_axis, magnitude, bin_hz


def parallel_search(enrolled_rods: dict, n_modes=10,
                    awg_mode="sweep", awg_start_hz=None,
                    awg_stop_hz=None, multitone_hz=None,
                    n_averages=4):
    """Drive all rods via AWG and identify which one resonates strongest.

    enrolled_rods: dict keyed by rod name/id, values have "perturbed_hz".
    Uses energy-based scoring: the rod with the highest aggregate energy
    at its enrolled peak frequencies is the winner (this IS the dot-product
    parallel search described in the paper).

    Returns ranked list with both energy and frequency-match scores.
    """
    freq_axis, magnitude, bin_hz = capture_awg_driven(
        awg_mode=awg_mode,
        awg_start_hz=awg_start_hz,
        awg_stop_hz=awg_stop_hz,
        multitone_hz=multitone_hz,
        n_averages=n_averages,
    )

    results = []
    for rod_id, rod_info in enrolled_rods.items():
        enrolled_hz = rod_info.get("perturbed_hz", [])
        if not enrolled_hz:
            continue
        # Energy score (higher = more resonance = better match)
        energy = score_spectrum_energy(
            freq_axis, magnitude, bin_hz, enrolled_hz, n_modes=n_modes,
        )
        # Frequency-match score (lower = better, for comparison)
        freq_score = score_spectrum_against_rod(
            freq_axis, magnitude, bin_hz, enrolled_hz, n_modes=n_modes,
        )
        results.append({
            "rod_id": rod_id,
            "energy": energy["energy"],
            "mean_snr": energy["mean_snr"],
            "n_detected": energy["n_detected"],
            "freq_score": freq_score["score"],
            "freq_rms": freq_score["rms"],
            "n_matched": freq_score["n_matched"],
            "n_total": energy["n_total"],
        })

    # Rank by frequency-match score (lower = better pattern match).
    # This measures fingerprint fidelity — how many enrolled peaks appear
    # in the aggregate spectrum and at what deviation.
    # Energy is reported but NOT used for ranking (coupling-strength bias).
    results.sort(key=lambda r: r["freq_score"])

    return {
        "ranked": results,
        "winner": results[0] if results else None,
        "n_rods_tested": len(results),
        "scoring": "freq_score (lower = better pattern match)",
    }


def _capture_ps2000a() -> list:
    """Tap-triggered capture using the ps2000a (A-series) driver.

    Same as _capture_ps2000 but for A-series driver API.
    """
    import ctypes
    import time
    from picosdk.ps2000a import ps2000a
    from picosdk.functions import assert_pico_ok

    handle = ctypes.c_int16()
    assert_pico_ok(ps2000a.ps2000aOpenUnit(ctypes.byref(handle), None))

    try:
        # Channel A: DC coupling, ±500 mV (range 5)
        assert_pico_ok(ps2000a.ps2000aSetChannel(handle, 0, 1, 1, 5, 0.0))

        # Rising-edge trigger on Channel A
        threshold_counts = int(TAP_TRIGGER_MV / VOLTAGE_RANGE_MV * 32512)
        assert_pico_ok(ps2000a.ps2000aSetSimpleTrigger(
            handle, 1, 0, threshold_counts, 2, 0, TAP_TIMEOUT_MS
        ))

        buf_a = (ctypes.c_int16 * N_SAMPLES)()
        assert_pico_ok(ps2000a.ps2000aSetDataBuffer(
            handle, 0, ctypes.byref(buf_a), N_SAMPLES, 0, 0
        ))
        timebase_a = ctypes.c_uint32(TIMEBASE)
        assert_pico_ok(ps2000a.ps2000aRunBlock(
            handle, 0, N_SAMPLES, timebase_a, None, 0, None, None
        ))
        ready = ctypes.c_int16(0)
        t0 = time.time()
        while ready.value == 0:
            assert_pico_ok(ps2000a.ps2000aIsReady(handle, ctypes.byref(ready)))
            time.sleep(0.001)
            if time.time() - t0 > (TAP_TIMEOUT_MS / 1000.0 + 2):
                break
        n_captured = ctypes.c_int32(N_SAMPLES)
        overflow = ctypes.c_int16()
        assert_pico_ok(ps2000a.ps2000aGetValues(
            handle, 0, ctypes.byref(n_captured), 0, 0, 0, ctypes.byref(overflow)
        ))
        if n_captured.value > 0:
            return [np.array(buf_a[:n_captured.value], dtype=np.float64)]
        return []

    finally:
        ps2000a.ps2000aStop(handle)
        ps2000a.ps2000aCloseUnit(handle)


def _capture_ps2000() -> list:
    """Tap-triggered capture using the ps2000 (non-A) driver.

    Arms a rising-edge trigger on Channel A at TAP_TRIGGER_MV.
    Waits up to TAP_TIMEOUT_MS for a tap on the rod/PZT, then
    captures the ring-down.  Returns a single capture in a list.

    Wiring: Ch A → BNC-to-alligator → PZT (red→red, black→black).
    No T-adapter, no AWG.  Tap the glass rod body (not the PZT) with
    a fingernail for broadband impulse excitation.
    """
    import ctypes
    import time
    from picosdk.ps2000 import ps2000

    capture_samples = N_SAMPLES  # 8064

    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")

    try:
        # Channel A: DC coupling, ±500 mV (range index 6)
        ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
        ps2000.ps2000_set_channel(handle, 1, False, 1, 6)

        # Rising-edge trigger on Channel A
        threshold_counts = int(TAP_TRIGGER_MV / VOLTAGE_RANGE_MV * 32767)
        ps2000.ps2000_set_trigger(
            handle,
            0,                   # source = Channel A
            threshold_counts,    # threshold in ADC counts
            0,                   # direction: 0 = rising
            0,                   # delay (samples)
            TAP_TIMEOUT_MS       # auto_trigger_ms
        )

        # Arm capture at timebase 7 (781 kHz, 8064 samples, ~10.3 ms)
        time_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(
            handle, capture_samples, TIMEBASE, 1, ctypes.byref(time_ms)
        )

        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.001)
            if time.time() - t0 > (TAP_TIMEOUT_MS / 1000.0 + 2):
                break

        buf_a = (ctypes.c_int16 * capture_samples)()
        buf_b = (ctypes.c_int16 * capture_samples)()
        overflow = ctypes.c_int16()
        n = ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), capture_samples
        )
        if n > 0:
            return [np.array(buf_a[:n], dtype=np.float64)]
        return []

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
