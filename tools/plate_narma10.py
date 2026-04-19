#!/usr/bin/env python3
"""
NARMA-10 Benchmark — Nonlinear Autoregressive Moving Average

Standard reservoir computing benchmark that tests nonlinear temporal memory.
The task: given input u(t) drawn uniformly from [0, 0.5], predict y(t) where:

  y(t+1) = 0.3·y(t) + 0.05·y(t)·Σ_{i=0}^{9} y(t-i) + 1.5·u(t-9)·u(t) + 0.1

This requires:
  - 10-step temporal memory (u(t-9) term)
  - Nonlinear mixing (y·Σy and u·u products)
  - Fading memory (the 0.3·y(t) autoregressive term)

Why this matters for CWM:
  LLMs/transformers do the same thing at every layer — nonlinear mixing of
  current input with past context. NARMA-10 measures exactly that capability.
  If the plate beats a software RBF kernel on NARMA-10, its mode cross-coupling
  provides genuine computational advantage.

Protocol:
  1. Generate NARMA-10 time series (N steps)
  2. Quantize u(t) → binary pattern (7 bits = 128 levels)
  3. Drive plate sequentially at carrier frequencies → capture spectral response
  4. Optionally run ESN with plate features for temporal memory
  5. Train ridge regression: plate features → y(t)
  6. Compare NMSE against software baselines

Modes:
  --hardware    : Drive real plates via PicoScope + relay mux
  --simulate    : Use cached census data to simulate plate response
  --offline     : Use cached hardware captures from a previous run

Usage:
  PYTHONPATH=. python tools/plate_narma10.py --port /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260412_180543.json \\
      --hardware --plate 4

  PYTHONPATH=. python tools/plate_narma10.py \\
      --census data/results/lab/plate_exps/plate_census_20260412_180543.json \\
      --simulate
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
from sklearn.kernel_ridge import KernelRidge
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

# ── Configuration ─────────────────────────────────────────────────────

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = LAB_DIR / "narma10"
RESULTS_FILE = RESULTS_DIR / f"narma10_{TIMESTAMP}.json"
LOG_FILE = RESULTS_DIR / f"narma10_{TIMESTAMP}.log"

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "G", "4": "D", "5": "H"}
PLATE_RELAYS = {
    "1": [(1, "NE")],
    "2": [(2, "NE")],
    "3": [(3, "NE"), (4, "NW")],
    "4": [(5, "NE"), (6, "NW")],
    "5": [(7, "NE"), (8, "NW")],
}

# NARMA parameters
NARMA_ORDER = 10
N_STEPS = 300           # total time steps (200 train + 100 test)
N_WASHOUT = 50          # initial steps discarded (let ESN state settle)
N_INPUT_BITS = 7        # quantization bits (128 levels over [0, 0.5])
N_PEAKS = 10            # modes per plate from census

# Hardware capture
N_AVG = 8               # FFT averages per measurement
SETTLE_S = 0.10         # AWG settle time
SETTLE_RELAY_S = 0.10   # relay settle time
BURST_MS = 2            # burst duration (ms) for ringdown mode
N_AVG_BURST = 4         # averages per burst capture

# ESN parameters (for temporal reservoir mode)
ESN_HIDDEN = 64
ESN_SPECTRAL_RADIUS = 0.9
ESN_LEAK = 0.5
ESN_INPUT_SCALE = 0.1

# Ridge regression
RIDGE_ALPHA = 1.0

# ── Logging ───────────────────────────────────────────────────────────

_log_lines: list[str] = []


def log(msg: str, also_print: bool = True) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    _log_lines.append(line)
    if also_print:
        print(msg, flush=True)


def _save_log() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w") as f:
        f.write("\n".join(_log_lines) + "\n")


# ═══════════════════════════════════════════════════════════════════════
#  NARMA-10 Time Series Generation
# ═══════════════════════════════════════════════════════════════════════

def generate_narma10(n_steps: int, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Generate NARMA-10 input/output sequences.

    u(t) ~ Uniform[0, 0.5]
    y(t+1) = 0.3·y(t) + 0.05·y(t)·Σ_{i=0}^{9} y(t-i) + 1.5·u(t-9)·u(t) + 0.1

    Returns (u, y) arrays of length n_steps.
    """
    rng = np.random.default_rng(seed)
    total = n_steps + NARMA_ORDER  # extra steps for warmup
    u = rng.uniform(0, 0.5, total)
    y = np.zeros(total)

    for t in range(NARMA_ORDER, total - 1):
        y_sum = np.sum(y[t - NARMA_ORDER:t + 1])
        y[t + 1] = (0.3 * y[t]
                     + 0.05 * y[t] * y_sum
                     + 1.5 * u[t - 9] * u[t]
                     + 0.1)
        # Clip to prevent divergence (standard practice)
        y[t + 1] = np.clip(y[t + 1], 0, 1e6)

    # Trim warmup
    return u[NARMA_ORDER:], y[NARMA_ORDER:]


def quantize_input(u: float, n_bits: int = N_INPUT_BITS) -> np.ndarray:
    """Quantize continuous u ∈ [0, 0.5] to n_bits binary pattern.

    Maps [0, 0.5] → [0, 2^n_bits - 1] → binary vector.
    """
    n_levels = 2 ** n_bits
    level = int(np.clip(u / 0.5 * (n_levels - 1), 0, n_levels - 1))
    return np.array([(level >> b) & 1 for b in range(n_bits)], dtype=np.float64)


# ═══════════════════════════════════════════════════════════════════════
#  Census / Enrollment
# ═══════════════════════════════════════════════════════════════════════

def load_census(census_path: str) -> dict:
    with open(census_path) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]
    return census


def get_plate_modes(census: dict, plate_id: str) -> list[float]:
    """Get enrolled mode frequencies for a plate."""
    if plate_id in census and census[plate_id].get("peaks"):
        peaks = census[plate_id]["peaks"][:N_PEAKS]
        return [p["freq_hz"] for p in peaks]
    return []


def get_carrier_indices(n_modes: int, n_bits: int) -> list[int]:
    """Select carrier indices evenly spaced across mode spectrum."""
    if n_modes <= n_bits:
        return list(range(n_modes))
    return list(np.linspace(0, n_modes - 1, n_bits, dtype=int))


# ═══════════════════════════════════════════════════════════════════════
#  PicoScope Hardware Capture
# ═══════════════════════════════════════════════════════════════════════

def _open_scope():
    import cwm_picoscope  # noqa: F401
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE as TB, N_SAMPLES as NS
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    log("PicoScope opened (Ch A ±1V DC)")
    return handle


def _close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    log("PicoScope closed")


def _capture_spectrum(handle, drive_freq_hz: float,
                      readout_freqs: list[float],
                      drive_uvpp: int = 2_000_000) -> np.ndarray:
    """Drive AWG at drive_freq_hz, return magnitudes at ALL readout freqs.

    This captures the full cross-coupling spectrum — the plate's nonlinear
    kernel in action. When driving mode i, energy bleeds into modes j≠i
    via the perturbation pattern. This cross-coupling IS the computation.
    """
    import cwm_picoscope
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE as TB, N_SAMPLES as NS, SAMPLE_RATE as SR

    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, drive_uvpp, 0,
        float(drive_freq_hz), float(drive_freq_hz), 0.0, 0.0, 0, 0)
    time.sleep(SETTLE_S)

    spectra = []
    for _ in range(N_AVG):
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
        t_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(handle, NS, TB, 1, ctypes.byref(t_ms))
        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.002)
            if time.time() - t0 > 2:
                break
        buf_a = (ctypes.c_int16 * NS)()
        buf_b = (ctypes.c_int16 * NS)()
        overflow = ctypes.c_int16()
        n = ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), NS)
        if n > 0:
            raw = np.array(buf_a[:n], dtype=np.float64)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SR)
            bin_hz = freq_axis[1] - freq_axis[0]

            mags = np.zeros(len(readout_freqs))
            for j, rf in enumerate(readout_freqs):
                tb = int(round(rf / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(fft) - 1, tb + 3)
                mags[j] = float(np.max(fft[lo:hi + 1]))
            spectra.append(mags)

    if spectra:
        return np.mean(spectra, axis=0)
    return np.zeros(len(readout_freqs))


def capture_plate_sequential(handle, mux, mode_freqs: list[float],
                             carrier_indices: list[int],
                             pattern: np.ndarray,
                             plate_id: str) -> np.ndarray:
    """Drive each active carrier, capture FULL spectrum at all modes.

    Returns flat vector: n_carriers × n_modes (cross-coupling matrix).
    Each row = spectrum when driving one carrier. Cross-coupling between
    modes IS the plate's nonlinear computation.
    """
    # PicoScope setup uses direct mapping: plate_id == relay channel
    # (PLATE_RELAYS is for Kronos audio wiring which is different)
    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    n_carriers = len(carrier_indices)
    n_modes = len(mode_freqs)
    cross_matrix = np.zeros((n_carriers, n_modes))

    for b in range(n_carriers):
        if pattern[b] > 0:
            drive_freq = mode_freqs[carrier_indices[b]]
            cross_matrix[b, :] = _capture_spectrum(
                handle, drive_freq, mode_freqs)

    # AWG off
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    return cross_matrix.ravel()


def _capture_single(handle, readout_freqs: list[float]) -> np.ndarray:
    """Single FFT capture (no AWG change). Returns magnitudes at readout freqs."""
    import cwm_picoscope  # noqa: F401
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE as TB, N_SAMPLES as NS, SAMPLE_RATE as SR

    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, NS, TB, 1, ctypes.byref(t_ms))
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.002)
        if time.time() - t0 > 2:
            break
    buf_a = (ctypes.c_int16 * NS)()
    buf_b = (ctypes.c_int16 * NS)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), NS)
    if n <= 0:
        return np.zeros(len(readout_freqs))

    raw = np.array(buf_a[:n], dtype=np.float64)
    windowed = raw * np.hanning(len(raw))
    nfft = len(raw) * 4
    fft = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SR)
    bin_hz = freq_axis[1] - freq_axis[0]

    mags = np.zeros(len(readout_freqs))
    for j, rf in enumerate(readout_freqs):
        tb = int(round(rf / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(fft) - 1, tb + 3)
        mags[j] = float(np.max(fft[lo:hi + 1]))
    return mags


def capture_plate_burst(handle, mux, mode_freqs: list[float],
                        carrier_indices: list[int],
                        pattern: np.ndarray,
                        plate_id: str) -> np.ndarray:
    """Drive carriers in rapid 2ms bursts — ringdown interference mode.

    Instead of settling between carriers (which erases memory), fires
    each active carrier for BURST_MS then immediately captures.
    Each capture sees: current carrier + ringdown tails from ALL
    previously driven carriers in this step.

    Ring-down times: τ ≈ 5.3ms at 30kHz, τ ≈ 1.7ms at 95kHz.
    At 2ms bursts, 30kHz modes still ring at 30-70% amplitude.
    This cross-carrier temporal coupling IS the memory mechanism.

    Returns flat vector: n_carriers × n_modes (same shape as sequential).
    """
    from picosdk.ps2000 import ps2000

    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    n_carriers = len(carrier_indices)
    n_modes = len(mode_freqs)
    cross_matrix = np.zeros((n_carriers, n_modes))

    for avg in range(N_AVG_BURST):
        # Clean start: AWG off, brief pause
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
        time.sleep(0.005)

        for b in range(n_carriers):
            if pattern[b] > 0:
                drive_freq = mode_freqs[carrier_indices[b]]
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, 2_000_000, 0,
                    float(drive_freq), float(drive_freq),
                    0.0, 0.0, 0, 0)
                time.sleep(BURST_MS / 1000.0)
            else:
                ps2000.ps2000_set_sig_gen_built_in(
                    handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
                time.sleep(BURST_MS / 1000.0)

            # Capture immediately — sees current + ringdown from previous
            cross_matrix[b, :] += _capture_single(handle, mode_freqs)

    cross_matrix /= N_AVG_BURST

    # AWG off
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    return cross_matrix.ravel()


# ═══════════════════════════════════════════════════════════════════════
#  Simulated Plate Response
# ═══════════════════════════════════════════════════════════════════════

def simulate_plate_response(mode_freqs: list[float],
                            census_mags: list[float],
                            carrier_indices: list[int],
                            pattern: np.ndarray,
                            rng: np.random.Generator) -> np.ndarray:
    """Simulate plate response using Lorentzian transfer model.

    Returns cross-coupling matrix flattened: n_carriers × n_modes.
    Each carrier drives its mode; cross-coupling adds nonlinearity.
    """
    n_carriers = len(carrier_indices)
    n_modes = len(mode_freqs)
    Q = 500.0  # quality factor

    cross_matrix = np.zeros((n_carriers, n_modes))
    for b in range(n_carriers):
        if pattern[b] > 0:
            ci = carrier_indices[b]
            f_drive = mode_freqs[ci]
            for j in range(n_modes):
                f_mode = mode_freqs[j]
                delta = (f_drive - f_mode) / f_mode
                transfer = 1.0 / (1.0 + (2 * Q * delta) ** 2)
                base_mag = census_mags[j] if j < len(census_mags) else 1e5
                cross_matrix[b, j] = base_mag * transfer

    # Add measurement noise (5% relative + small absolute)
    noise = rng.normal(0, 0.05, cross_matrix.shape) * cross_matrix
    noise += rng.normal(0, 1000, cross_matrix.shape)
    cross_matrix += noise
    return np.maximum(cross_matrix, 0).ravel()


# ═══════════════════════════════════════════════════════════════════════
#  Feature Engineering
# ═══════════════════════════════════════════════════════════════════════

def extract_features(response: np.ndarray, pattern: np.ndarray,
                     mode: str = "plate_poly") -> np.ndarray:
    """Extract features from plate response.

    Modes:
      plate_raw:   log1p of raw response magnitudes
      plate_poly:  log1p + polynomial interaction expansion
      input_only:  just the binary input pattern (no hardware)
      input_poly:  polynomial expansion of input bits
    """
    if mode == "input_only":
        return pattern.copy()

    if mode == "input_poly":
        # Polynomial expansion of input bits (degree 2)
        feats = list(pattern)
        bits = pattern
        for i in range(len(bits)):
            for j in range(i, len(bits)):
                feats.append(bits[i] * bits[j])
        return np.array(feats)

    # Hardware/simulated features
    raw = np.log1p(response)

    if mode == "plate_raw":
        return raw

    if mode == "plate_poly":
        # Raw features + pairwise interactions of carrier magnitudes
        feats = list(raw)
        for i in range(len(raw)):
            for j in range(i, len(raw)):
                feats.append(raw[i] * raw[j])
        return np.array(feats)

    return raw


# ═══════════════════════════════════════════════════════════════════════
#  Echo State Network
# ═══════════════════════════════════════════════════════════════════════

class SimpleESN:
    """Minimal Echo State Network for temporal reservoir computing.

    The plate provides the nonlinear kernel at each time step.
    The ESN provides temporal memory via its recurrent hidden state.
    """

    def __init__(self, input_dim: int, hidden_dim: int = ESN_HIDDEN,
                 spectral_radius: float = ESN_SPECTRAL_RADIUS,
                 leak: float = ESN_LEAK,
                 input_scale: float = ESN_INPUT_SCALE,
                 seed: int = 0):
        rng = np.random.default_rng(seed)
        self.hidden_dim = hidden_dim
        self.leak = leak

        # Input weights (sparse)
        self.W_in = rng.normal(0, input_scale, (hidden_dim, input_dim))

        # Recurrent weights (scaled to spectral radius)
        W = rng.normal(0, 1, (hidden_dim, hidden_dim))
        W *= spectral_radius / np.max(np.abs(np.linalg.eigvals(W)))
        self.W_rec = W

        self.h = np.zeros(hidden_dim)

    def reset(self):
        self.h = np.zeros(self.hidden_dim)

    def step(self, x: np.ndarray) -> np.ndarray:
        """One ESN step: update hidden state, return it."""
        pre = self.W_in @ x + self.W_rec @ self.h
        self.h = (1 - self.leak) * self.h + self.leak * np.tanh(pre)
        return self.h.copy()


# ═══════════════════════════════════════════════════════════════════════
#  NMSE metric
# ═══════════════════════════════════════════════════════════════════════

def nmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Normalized Mean Squared Error = MSE / var(y_true).

    NMSE < 1 means better than predicting the mean.
    NMSE = 0 means perfect prediction.
    Good reservoir: NMSE < 0.1 on NARMA-10.
    """
    var = np.var(y_true)
    if var == 0:
        return float('inf')
    return float(np.mean((y_true - y_pred) ** 2) / var)


# ═══════════════════════════════════════════════════════════════════════
#  Main Benchmark
# ═══════════════════════════════════════════════════════════════════════

def run_narma10(census_path: str,
                plate_id: str = "4",
                mode: str = "simulate",
                port: str = "/dev/cu.usbserial-11310",
                n_steps: int = N_STEPS,
                seed: int = 42,
                burst: bool = False) -> dict:
    """Run NARMA-10 benchmark.

    Approaches tested:
      1. plate_esn:    Plate features → ESN → ridge (temporal reservoir)
      2. plate_direct: Plate features at each step → ridge (no temporal memory)
      3. plate_window: Plate features from sliding window → ridge
      4. sw_rbf:       Software RBF kernel on raw inputs (sklearn)
      5. sw_poly:      Software polynomial features on raw inputs
      6. input_only:   Raw quantized inputs → ridge (baseline)
      7. mean_pred:    Always predict mean(y_train) (trivial baseline)

    If burst=True, also captures ringdown-burst features alongside steady-state.
    """
    capture_label = f"{mode}" + (" + burst" if burst else "")
    log("\n" + "=" * 70)
    log("  NARMA-10 BENCHMARK")
    log(f"  Steps: {n_steps}, Washout: {N_WASHOUT}, Seed: {seed}")
    log(f"  Capture: {capture_label}")
    log("=" * 70)

    # ── Generate NARMA-10 series ──────────────────────────────────────
    u, y = generate_narma10(n_steps, seed=seed)
    log(f"\n  NARMA-10 generated: {n_steps} steps")
    log(f"  u range: [{u.min():.4f}, {u.max():.4f}]")
    log(f"  y range: [{y.min():.4f}, {y.max():.4f}]")
    log(f"  y mean: {y.mean():.4f}, std: {y.std():.4f}")

    # ── Load census ───────────────────────────────────────────────────
    census = load_census(census_path)
    mode_freqs = get_plate_modes(census, plate_id)
    census_mags = []
    if plate_id in census and census[plate_id].get("peaks"):
        census_mags = [p["magnitude"] for p in census[plate_id]["peaks"][:N_PEAKS]]

    n_modes = len(mode_freqs)
    carrier_indices = get_carrier_indices(n_modes, N_INPUT_BITS)
    log(f"  Plate {PLATE_NAMES.get(plate_id, plate_id)}: {n_modes} modes, "
        f"{N_INPUT_BITS} carriers at indices {carrier_indices}")

    # ── Hardware setup (if needed) ────────────────────────────────────
    handle = None
    mux = None
    if mode == "hardware":
        handle = _open_scope()
        from relay_mux import RelayMux
        mux = RelayMux(port=port)
        mux.open()
        log(f"  Relay mux connected on {port}")

    rng = np.random.default_rng(seed + 100)
    t_start = time.time()

    # ── Capture plate responses for each time step ────────────────────
    log(f"\n  Capturing {n_steps} time steps ({capture_label})...")

    plate_responses = []  # one per time step (steady-state)
    burst_responses = []  # one per time step (ringdown burst, if enabled)
    for t in range(n_steps):
        pattern = quantize_input(u[t], N_INPUT_BITS)

        if mode == "hardware":
            resp = capture_plate_sequential(
                handle, mux, mode_freqs, carrier_indices, pattern, plate_id)
            plate_responses.append(resp)

            if burst:
                resp_burst = capture_plate_burst(
                    handle, mux, mode_freqs, carrier_indices, pattern, plate_id)
                burst_responses.append(resp_burst)
        else:
            resp = simulate_plate_response(
                mode_freqs, census_mags, carrier_indices, pattern, rng)
            plate_responses.append(resp)

        if (t + 1) % 50 == 0:
            log(f"    Step {t+1}/{n_steps} done", also_print=(t + 1) % 100 == 0)

    plate_responses = np.array(plate_responses)
    capture_time = time.time() - t_start

    # Cleanup hardware
    if handle is not None:
        _close_scope(handle)
    if mux is not None:
        mux.off()
        mux.close()

    log(f"  Capture complete: {capture_time:.1f}s "
        f"({capture_time/n_steps*1000:.0f} ms/step)")

    # ── Build feature matrices for each approach ──────────────────────
    log("\n  Building feature matrices...")

    # Quantized inputs for all steps
    U_bits = np.array([quantize_input(u[t], N_INPUT_BITS) for t in range(n_steps)])

    # Sliding window size for windowed approaches
    WINDOW = NARMA_ORDER

    # Feature sets
    features = {}

    # 1. Plate features (raw magnitudes, log1p normalized)
    plate_raw = np.log1p(plate_responses)
    features["plate_raw"] = plate_raw

    # 2. Plate + polynomial interactions
    plate_poly_list = []
    for t in range(n_steps):
        pf = extract_features(plate_responses[t], U_bits[t], mode="plate_poly")
        plate_poly_list.append(pf)
    features["plate_poly"] = np.array(plate_poly_list)

    # 3. Plate ESN (plate features fed through ESN for temporal memory)
    esn = SimpleESN(input_dim=plate_raw.shape[1], seed=seed + 200)
    esn_states = []
    for t in range(n_steps):
        h = esn.step(plate_raw[t])
        esn_states.append(h)
    features["plate_esn"] = np.array(esn_states)

    # 4. Plate ESN + plate features concatenated
    features["plate_esn_plus"] = np.hstack([
        features["plate_esn"], plate_raw
    ])

    # 5. Sliding window of plate features (last WINDOW steps concatenated)
    plate_windowed = []
    for t in range(n_steps):
        window_feats = []
        for w in range(WINDOW):
            idx = max(0, t - w)
            window_feats.append(plate_raw[idx])
        plate_windowed.append(np.concatenate(window_feats))
    features["plate_window"] = np.array(plate_windowed)

    # 5b. Burst (ringdown) features — if captured
    if burst_responses:
        burst_arr = np.array(burst_responses)
        burst_raw = np.log1p(burst_arr)
        features["burst_raw"] = burst_raw

        # Burst ESN (ringdown features through ESN — physical + temporal memory)
        esn_b = SimpleESN(input_dim=burst_raw.shape[1], seed=seed + 250)
        esn_b_states = []
        for t in range(n_steps):
            h = esn_b.step(burst_raw[t])
            esn_b_states.append(h)
        features["burst_esn"] = np.array(esn_b_states)

        # Burst + steady-state concatenated (all physics)
        features["burst_plus_ss"] = np.hstack([burst_raw, plate_raw])

        # Burst + steady-state through ESN
        combined_raw = np.hstack([burst_raw, plate_raw])
        esn_c = SimpleESN(input_dim=combined_raw.shape[1], seed=seed + 260)
        esn_c_states = []
        for t in range(n_steps):
            h = esn_c.step(combined_raw[t])
            esn_c_states.append(h)
        features["burst_combined_esn"] = np.array(esn_c_states)

        # Burst window (ringdown creates natural memory, window extends it)
        burst_windowed = []
        for t in range(n_steps):
            window_feats = []
            for w in range(WINDOW):
                idx = max(0, t - w)
                window_feats.append(burst_raw[idx])
            burst_windowed.append(np.concatenate(window_feats))
        features["burst_window"] = np.array(burst_windowed)

    # 6. Input-only (raw binary patterns)
    features["input_only"] = U_bits

    # 7. Input polynomial
    input_poly_list = []
    for t in range(n_steps):
        pf = extract_features(None, U_bits[t], mode="input_poly")
        input_poly_list.append(pf)
    features["input_poly"] = np.array(input_poly_list)

    # 8. Input ESN (raw inputs through ESN, no hardware)
    esn_sw = SimpleESN(input_dim=N_INPUT_BITS, seed=seed + 300)
    esn_sw_states = []
    for t in range(n_steps):
        h = esn_sw.step(U_bits[t])
        esn_sw_states.append(h)
    features["input_esn"] = np.array(esn_sw_states)

    # 9. Input sliding window
    input_windowed = []
    for t in range(n_steps):
        window_feats = []
        for w in range(WINDOW):
            idx = max(0, t - w)
            window_feats.append(U_bits[idx])
        input_windowed.append(np.concatenate(window_feats))
    features["input_window"] = np.array(input_windowed)

    # ── Train/test split ──────────────────────────────────────────────
    n_train = n_steps - n_steps // 3  # ~200 train, ~100 test
    train_slice = slice(N_WASHOUT, n_train)
    test_slice = slice(n_train, n_steps)

    y_train = y[train_slice]
    y_test = y[test_slice]

    log(f"  Train: steps {N_WASHOUT}–{n_train} ({n_train - N_WASHOUT} samples)")
    log(f"  Test:  steps {n_train}–{n_steps} ({n_steps - n_train} samples)")
    log(f"  y_train mean={y_train.mean():.4f} std={y_train.std():.4f}")

    # ── Evaluate each approach ────────────────────────────────────────
    log("\n" + "=" * 70)
    log("  RESULTS")
    log("=" * 70)
    log(f"\n  {'Approach':<25s} {'NMSE (train)':>14s} {'NMSE (test)':>14s} "
        f"{'Features':>10s}")
    log(f"  {'─' * 25} {'─' * 14} {'─' * 14} {'─' * 10}")

    results = {}

    # Trivial baseline: predict mean
    y_pred_mean = np.full_like(y_test, y_train.mean())
    nmse_mean = nmse(y_test, y_pred_mean)
    results["mean_baseline"] = {
        "nmse_train": 1.0, "nmse_test": round(nmse_mean, 6),
        "n_features": 0,
    }
    log(f"  {'mean_baseline':<25s} {'1.000000':>14s} {nmse_mean:>14.6f} {'0':>10s}")

    # Ridge regression on each feature set
    for name, X_all in sorted(features.items()):
        X_tr = X_all[train_slice]
        X_te = X_all[test_slice]

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)

        ridge = Ridge(alpha=RIDGE_ALPHA)
        ridge.fit(X_tr_s, y_train)

        y_pred_tr = ridge.predict(X_tr_s)
        y_pred_te = ridge.predict(X_te_s)

        nm_tr = nmse(y_train, y_pred_tr)
        nm_te = nmse(y_test, y_pred_te)

        results[name] = {
            "nmse_train": round(nm_tr, 6),
            "nmse_test": round(nm_te, 6),
            "n_features": X_tr.shape[1],
        }
        log(f"  {name:<25s} {nm_tr:>14.6f} {nm_te:>14.6f} {X_tr.shape[1]:>10d}")

    # Software RBF kernel (the direct competitor)
    for gamma_name, gamma in [("rbf_auto", None), ("rbf_0.1", 0.1)]:
        X_tr_u = U_bits[train_slice]
        X_te_u = U_bits[test_slice]

        scaler_u = StandardScaler()
        X_tr_us = scaler_u.fit_transform(X_tr_u)
        X_te_us = scaler_u.transform(X_te_u)

        # gamma=None → default 1/n_features
        krr = KernelRidge(alpha=RIDGE_ALPHA, kernel="rbf", gamma=gamma)
        krr.fit(X_tr_us, y_train)

        y_pred_tr = krr.predict(X_tr_us)
        y_pred_te = krr.predict(X_te_us)

        nm_tr = nmse(y_train, y_pred_tr)
        nm_te = nmse(y_test, y_pred_te)

        name = f"sw_{gamma_name}"
        results[name] = {
            "nmse_train": round(nm_tr, 6),
            "nmse_test": round(nm_te, 6),
            "n_features": X_tr_u.shape[1],
            "kernel": "rbf",
            "gamma": str(gamma),
        }
        log(f"  {name:<25s} {nm_tr:>14.6f} {nm_te:>14.6f} "
            f"{X_tr_u.shape[1]:>10d}")

    # Software RBF on windowed inputs (fair comparison for temporal approaches)
    X_tr_w = features["input_window"][train_slice]
    X_te_w = features["input_window"][test_slice]
    scaler_w = StandardScaler()
    X_tr_ws = scaler_w.fit_transform(X_tr_w)
    X_te_ws = scaler_w.transform(X_te_w)

    krr_w = KernelRidge(alpha=RIDGE_ALPHA, kernel="rbf", gamma=None)
    krr_w.fit(X_tr_ws, y_train)
    y_pred_tr_w = krr_w.predict(X_tr_ws)
    y_pred_te_w = krr_w.predict(X_te_ws)
    nm_tr_w = nmse(y_train, y_pred_tr_w)
    nm_te_w = nmse(y_test, y_pred_te_w)

    results["sw_rbf_window"] = {
        "nmse_train": round(nm_tr_w, 6),
        "nmse_test": round(nm_te_w, 6),
        "n_features": X_tr_w.shape[1],
        "kernel": "rbf",
        "gamma": "auto",
        "window": WINDOW,
    }
    log(f"  {'sw_rbf_window':<25s} {nm_tr_w:>14.6f} {nm_te_w:>14.6f} "
        f"{X_tr_w.shape[1]:>10d}")

    # ── Summary ───────────────────────────────────────────────────────
    total_time = time.time() - t_start

    # Find best approach
    best_name = min(results, key=lambda k: results[k]["nmse_test"])
    best_nmse = results[best_name]["nmse_test"]

    # Determine if plate beats software
    plate_best = min(
        (results[k]["nmse_test"] for k in results
         if k.startswith("plate_") or k.startswith("burst_")), default=float('inf'))
    sw_best = min(
        (results[k]["nmse_test"] for k in results
         if k.startswith("sw_") or k.startswith("input_")), default=float('inf'))

    log(f"\n  {'─' * 65}")
    log(f"  Best overall:  {best_name} (NMSE = {best_nmse:.6f})")
    log(f"  Best plate:    NMSE = {plate_best:.6f}")
    log(f"  Best software: NMSE = {sw_best:.6f}")
    if plate_best < sw_best:
        advantage = (1 - plate_best / sw_best) * 100
        log(f"  → PLATE WINS by {advantage:.1f}%")
    else:
        disadvantage = (plate_best / sw_best - 1) * 100
        log(f"  → Software wins by {disadvantage:.1f}%")

    log(f"\n  NARMA-10 quality thresholds:")
    log(f"    NMSE < 0.1  → excellent reservoir")
    log(f"    NMSE < 0.3  → good reservoir")
    log(f"    NMSE < 0.5  → marginal reservoir")
    log(f"    NMSE ≥ 1.0  → no better than predicting the mean")
    log(f"\n  Total time: {total_time:.1f}s")

    # ── Save results ──────────────────────────────────────────────────
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmark": "narma10",
        "narma_order": NARMA_ORDER,
        "n_steps": n_steps,
        "n_washout": N_WASHOUT,
        "n_train": n_train - N_WASHOUT,
        "n_test": n_steps - n_train,
        "n_input_bits": N_INPUT_BITS,
        "plate_id": plate_id,
        "plate_name": PLATE_NAMES.get(plate_id, plate_id),
        "n_modes": n_modes,
        "mode": mode,
        "burst": burst,
        "seed": seed,
        "capture_time_s": round(capture_time, 1),
        "total_time_s": round(total_time, 1),
        "results": results,
        "best_approach": best_name,
        "best_nmse": best_nmse,
        "plate_beats_software": plate_best < sw_best,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log(f"\n  Saved: {RESULTS_FILE}")

    _save_log()
    return payload


# ═══════════════════════════════════════════════════════════════════════
#  Multi-Plate Ensemble: Does "more plates" = "more depth"?
# ═══════════════════════════════════════════════════════════════════════

def run_narma10_ensemble(census_path: str,
                         mode: str = "simulate",
                         n_steps: int = N_STEPS,
                         seed: int = 42) -> dict:
    """Run NARMA-10 with all 5 plates' features concatenated.

    Tests the hypothesis: if one plate can't do NARMA-10,
    does adding more plates (= more features) help?

    Width (more modes) vs Depth (temporal memory) — which matters?
    """
    log(f"\n{'═' * 70}")
    log("  MULTI-PLATE ENSEMBLE (all 5 plates)")
    log(f"{'═' * 70}")

    u, y = generate_narma10(n_steps, seed=seed)

    census = load_census(census_path)
    rng = np.random.default_rng(seed + 100)

    # Collect responses from ALL plates at each step
    all_plate_responses = {}
    total_modes = 0
    for pid in PLATE_IDS:
        mf = get_plate_modes(census, pid)
        if not mf:
            continue
        cm = []
        if pid in census and census[pid].get("peaks"):
            cm = [p["magnitude"] for p in census[pid]["peaks"][:N_PEAKS]]
        ci = get_carrier_indices(len(mf), N_INPUT_BITS)

        resps = []
        for t in range(n_steps):
            pattern = quantize_input(u[t], N_INPUT_BITS)
            resp = simulate_plate_response(mf, cm, ci, pattern, rng)
            resps.append(resp)
        all_plate_responses[pid] = np.array(resps)
        total_modes += len(mf)
        log(f"  Plate {PLATE_NAMES[pid]}: {len(mf)} modes")

    log(f"  Total modes (concatenated): {total_modes}")

    # Concatenate all plates' responses → one wide feature vector
    ensemble_raw = np.hstack([all_plate_responses[pid] for pid in PLATE_IDS
                              if pid in all_plate_responses])
    ensemble_log = np.log1p(ensemble_raw)

    # Build feature sets
    n_train = n_steps - n_steps // 3
    train_slice = slice(N_WASHOUT, n_train)
    test_slice = slice(n_train, n_steps)
    y_train = y[train_slice]
    y_test = y[test_slice]

    U_bits = np.array([quantize_input(u[t], N_INPUT_BITS) for t in range(n_steps)])
    WINDOW = NARMA_ORDER

    features = {}

    # 1. Ensemble raw (all plates concatenated)
    features["ensemble_raw"] = ensemble_log

    # 2. Ensemble ESN (wide plate features through ESN)
    esn_e = SimpleESN(input_dim=ensemble_log.shape[1], seed=seed + 400)
    esn_states = []
    for t in range(n_steps):
        h = esn_e.step(ensemble_log[t])
        esn_states.append(h)
    features["ensemble_esn"] = np.array(esn_states)

    # 3. Ensemble ESN + raw
    features["ensemble_esn_plus"] = np.hstack([
        features["ensemble_esn"], ensemble_log
    ])

    # 4. Ensemble window (sliding window of all plates)
    ew = []
    for t in range(n_steps):
        wf = []
        for w in range(WINDOW):
            idx = max(0, t - w)
            wf.append(ensemble_log[idx])
        ew.append(np.concatenate(wf))
    features["ensemble_window"] = np.array(ew)

    # 5. Controls (same as single-plate)
    features["input_only"] = U_bits

    esn_sw = SimpleESN(input_dim=N_INPUT_BITS, seed=seed + 300)
    esn_sw_states = []
    for t in range(n_steps):
        h = esn_sw.step(U_bits[t])
        esn_sw_states.append(h)
    features["input_esn"] = np.array(esn_sw_states)

    input_windowed = []
    for t in range(n_steps):
        wf = []
        for w in range(WINDOW):
            idx = max(0, t - w)
            wf.append(U_bits[idx])
        input_windowed.append(np.concatenate(wf))
    features["input_window"] = np.array(input_windowed)

    # Best single plate (D, 8 modes) for comparison
    pid_best = "4"
    if pid_best in all_plate_responses:
        features["single_plate_D"] = np.log1p(all_plate_responses[pid_best])

    # Evaluate
    log(f"\n  {'Approach':<25s} {'NMSE (train)':>14s} {'NMSE (test)':>14s} "
        f"{'Features':>10s}")
    log(f"  {'─' * 25} {'─' * 14} {'─' * 14} {'─' * 10}")

    results = {}

    for name, X_all in sorted(features.items()):
        X_tr = X_all[train_slice]
        X_te = X_all[test_slice]

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)

        ridge = Ridge(alpha=RIDGE_ALPHA)
        ridge.fit(X_tr_s, y_train)

        y_pred_tr = ridge.predict(X_tr_s)
        y_pred_te = ridge.predict(X_te_s)

        nm_tr = nmse(y_train, y_pred_tr)
        nm_te = nmse(y_test, y_pred_te)

        results[name] = {
            "nmse_train": round(nm_tr, 6),
            "nmse_test": round(nm_te, 6),
            "n_features": X_tr.shape[1],
        }
        log(f"  {name:<25s} {nm_tr:>14.6f} {nm_te:>14.6f} {X_tr.shape[1]:>10d}")

    # Software RBF window control
    X_tr_w = features["input_window"][train_slice]
    X_te_w = features["input_window"][test_slice]
    scaler_w = StandardScaler()
    X_tr_ws = scaler_w.fit_transform(X_tr_w)
    X_te_ws = scaler_w.transform(X_te_w)
    krr_w = KernelRidge(alpha=RIDGE_ALPHA, kernel="rbf", gamma=None)
    krr_w.fit(X_tr_ws, y_train)
    nm_tr_w = nmse(y_train, krr_w.predict(X_tr_ws))
    nm_te_w = nmse(y_test, krr_w.predict(X_te_ws))
    results["sw_rbf_window"] = {
        "nmse_train": round(nm_tr_w, 6), "nmse_test": round(nm_te_w, 6),
        "n_features": X_tr_w.shape[1],
    }
    log(f"  {'sw_rbf_window':<25s} {nm_tr_w:>14.6f} {nm_te_w:>14.6f} "
        f"{X_tr_w.shape[1]:>10d}")

    # Verdicts
    ens_best = min(results[k]["nmse_test"] for k in results
                   if k.startswith("ensemble_"))
    single_best = results.get("single_plate_D", {}).get("nmse_test", float('inf'))
    input_esn_nmse = results.get("input_esn", {}).get("nmse_test", float('inf'))

    log(f"\n  {'─' * 65}")
    log(f"  Single plate D (8 modes, {results.get('single_plate_D', {}).get('n_features', '?')} feat):  "
        f"NMSE = {single_best:.4f}")
    log(f"  5-plate ensemble ({total_modes} modes):        "
        f"NMSE = {ens_best:.4f}")
    log(f"  Input ESN (no hardware, 64 hidden):  NMSE = {input_esn_nmse:.4f}")

    if ens_best < single_best:
        improvement = (1 - ens_best / single_best) * 100
        log(f"  → 5 plates {improvement:.1f}% better than 1 plate")
    else:
        log(f"  → More plates did NOT help (ensemble ≥ single)")

    if ens_best < input_esn_nmse:
        log(f"  → Ensemble beats software ESN!")
    else:
        gap = (ens_best / input_esn_nmse - 1) * 100
        log(f"  → Software ESN still wins by {gap:.1f}%")

    log(f"\n  VERDICT: {'Width (more plates)' if ens_best < input_esn_nmse else 'Depth (temporal memory)'} "
        f"matters more for NARMA-10")

    # Save
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmark": "narma10_ensemble",
        "n_plates": len(all_plate_responses),
        "total_modes": total_modes,
        "n_steps": n_steps,
        "results": results,
        "ensemble_best_nmse": ens_best,
        "single_plate_D_nmse": single_best,
        "input_esn_nmse": input_esn_nmse,
    }
    ens_file = RESULTS_DIR / f"narma10_ensemble_{TIMESTAMP}.json"
    with open(ens_file, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log(f"  Saved: {ens_file}")
    _save_log()
    return payload


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 benchmark for plate reservoir computing")
    parser.add_argument("--census", type=str, required=True,
                        help="Path to census JSON")
    parser.add_argument("--plate", type=str, default="4",
                        help="Plate ID (default: 4)")
    parser.add_argument("--port", type=str, default="/dev/cu.usbserial-11310",
                        help="Serial port for relay mux")
    parser.add_argument("--hardware", action="store_true",
                        help="Run on real hardware (PicoScope + relay mux)")
    parser.add_argument("--simulate", action="store_true",
                        help="Simulate plate response from census data")
    parser.add_argument("--steps", type=int, default=N_STEPS,
                        help=f"Number of time steps (default: {N_STEPS})")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed")
    parser.add_argument("--all-plates", action="store_true",
                        help="Run on all 5 plates (simulate mode)")
    parser.add_argument("--burst", action="store_true",
                        help="Also capture ringdown-burst features (hardware only)")
    args = parser.parse_args()

    if not args.hardware and not args.simulate:
        args.simulate = True  # default to simulate

    run_mode = "hardware" if args.hardware else "simulate"

    if args.all_plates and run_mode == "simulate":
        for pid in PLATE_IDS:
            census = load_census(args.census)
            modes = get_plate_modes(census, pid)
            if modes:
                log(f"\n{'═' * 70}")
                log(f"  PLATE {PLATE_NAMES[pid]} ({len(modes)} modes)")
                log(f"{'═' * 70}")
                run_narma10(args.census, plate_id=pid, mode=run_mode,
                            port=args.port, n_steps=args.steps, seed=args.seed)
        # Also run multi-plate ensemble
        run_narma10_ensemble(args.census, mode=run_mode,
                             n_steps=args.steps, seed=args.seed)
    else:
        run_narma10(args.census, plate_id=args.plate, mode=run_mode,
                    port=args.port, n_steps=args.steps, seed=args.seed,
                    burst=args.burst)


if __name__ == "__main__":
    main()
