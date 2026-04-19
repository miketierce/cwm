#!/usr/bin/env python3
"""
Plate Reservoir Benchmark — Standard ML Tasks via Kronos

Tests the plate against standard classification benchmarks to assess
whether it can compete as an inference accelerator (e.g. for Bittensor
subnets or edge deployment).

Benchmarks:
  1. N-bit parity (XOR generalization) — our existing test, now with 186 modes
  2. Spoken digit classification (encoded as spectral patterns)
  3. Nonlinear function regression (sin, XOR surface, NARMA-10)
  4. Random high-dimensional classification (baseline for reservoir capacity)

For each benchmark we measure:
  - Accuracy (train / test)
  - Inference latency (ms per query)
  - Power estimate (W per query)
  - Comparison vs trivial software baselines (logistic regression, MLP)

This script can run in two modes:
  --hardware     : Drive real plates via Kronos + relay mux
  --simulate     : Use cached census data to simulate plate response
                   (tests the readout pipeline without hardware)

Usage:
    # Hardware mode — full benchmark on plate 5:
    python plate_benchmark_kronos.py /dev/cu.usbserial-11310 \\
        --device KRONOS --census <census.json> --hardware

    # Simulate from census — no hardware needed:
    python plate_benchmark_kronos.py --census <census.json> --simulate

    # Quick parity-only test:
    python plate_benchmark_kronos.py --census <census.json> --simulate \\
        --benchmarks parity
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab"
RESULTS_DIR = LAB_DIR / "plate_exps"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Plate config ──
PLATE_NAMES = {"1": "A", "2": "B", "3": "G", "4": "D", "5": "H"}
PLATE_RELAYS = {
    "1": [(1, "NE")],
    "2": [(2, "NE")],
    "3": [(3, "NE"), (4, "NW")],
    "4": [(5, "NE"), (6, "NW")],
    "5": [(7, "NE"), (8, "NW")],
}

# ── Audio config ──
PREFERRED_SAMPLE_RATES = [192000, 96000, 48000, 44100]
AUDIO_DTYPE = "float32"
DRIVE_AMPLITUDE = 0.95
SETTLE_RELAY_S = 0.10
USB_LATENCY_S = 0.25           # Kronos USB round-trip; sustain tone beyond this

# ── Benchmark config ──
N_AVG = 4
FIXTURE_FREQ_HZ = 6700.0
FIXTURE_GUARD_HZ = 200.0

# ── Power estimates (measured) ──
POWER_PZT_DRIVE_W = 0.02     # PZT drive power (~20 mW)
POWER_KRONOS_W = 2.5          # Kronos USB audio (bus-powered)
POWER_ARDUINO_W = 0.25        # Arduino Nano (relay mux)
POWER_LAPTOP_READOUT_W = 5.0  # Laptop CPU during FFT readout
POWER_TOTAL_W = (POWER_PZT_DRIVE_W + POWER_KRONOS_W
                 + POWER_ARDUINO_W + POWER_LAPTOP_READOUT_W)

# For comparison: typical GPU inference
POWER_GPU_INFERENCE_W = 150.0  # RTX 3090 during inference


# ══════════════════════════════════════════════════════════════════════
# Audio + census helpers (shared with other Kronos scripts)
# ══════════════════════════════════════════════════════════════════════

def find_audio_device(name_hint: str) -> int:
    import sounddevice as sd
    hint_lower = name_hint.lower()
    for i, dev in enumerate(sd.query_devices()):
        if (hint_lower in dev["name"].lower()
                and dev["max_input_channels"] > 0
                and dev["max_output_channels"] > 0):
            return i
    raise RuntimeError(f"No audio device matching '{name_hint}' with I/O.")


def detect_sample_rate(device_idx: int) -> int:
    import sounddevice as sd
    for rate in PREFERRED_SAMPLE_RATES:
        try:
            sd.check_input_settings(device=device_idx, channels=1,
                                    dtype=AUDIO_DTYPE, samplerate=rate)
            sd.check_output_settings(device=device_idx, channels=1,
                                     dtype=AUDIO_DTYPE, samplerate=rate)
            return rate
        except Exception:
            continue
    dev = sd.query_devices(device_idx)
    return int(dev["default_samplerate"])


def load_census(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def get_plate_modes(census: dict, plate_id: str,
                    relay_key: str | None = None) -> list[float]:
    results = census.get("results", {})
    keys = [relay_key, plate_id, f"{plate_id}_NE", f"{plate_id}_NW"]
    keys = [k for k in keys if k is not None]
    for key in keys:
        if key in results:
            peaks = results[key].get("peaks", [])
            if peaks:
                freqs = [p["freq_hz"] for p in sorted(peaks, key=lambda p: p["freq_hz"])]
                lo = FIXTURE_FREQ_HZ - FIXTURE_GUARD_HZ
                hi = FIXTURE_FREQ_HZ + FIXTURE_GUARD_HZ
                return [f for f in freqs if not (lo <= f <= hi)]
    return []


# ══════════════════════════════════════════════════════════════════════
# Hardware capture
# ══════════════════════════════════════════════════════════════════════

def capture_loopback_reference(sample_rate: int, device_idx: int, mux,
                               mode_freqs: list[float],
                               carrier_indices: list[int],
                               n_averages: int = N_AVG) -> np.ndarray:
    """Capture USB loopback reference with relay OFF (no acoustic path).

    Drives a representative multitone (all carriers ON) and records.
    Returns the averaged raw RX waveform (pre-settle-trim) for subtraction.
    """
    import sounddevice as sd

    mux.off()
    time.sleep(SETTLE_RELAY_S)

    total_dur = USB_LATENCY_S + 0.2  # match hardware_capture default
    n_samples = int(sample_rate * total_dur)
    t = np.arange(n_samples) / sample_rate
    sig = np.zeros(n_samples, dtype=np.float64)

    rng = np.random.default_rng(42)
    for b in range(len(carrier_indices)):
        freq = mode_freqs[carrier_indices[b]]
        phi = rng.uniform(0, 2 * np.pi)
        sig += np.sin(2 * np.pi * freq * t + phi)

    peak = np.max(np.abs(sig))
    if peak > 0:
        sig *= DRIVE_AMPLITUDE / peak
    tx = sig.astype(np.float32).reshape(-1, 1)

    print("  Capturing loopback reference (relay OFF)...", flush=True)
    ref_accum = None
    for i in range(n_averages):
        rx = sd.playrec(tx, samplerate=sample_rate,
                        input_mapping=[1], output_mapping=[1],
                        device=device_idx, dtype=AUDIO_DTYPE, blocking=True)
        rx_mono = rx[:, 0].astype(np.float64)
        if ref_accum is None:
            ref_accum = np.zeros_like(rx_mono)
        ref_accum += rx_mono
    ref_avg = ref_accum / n_averages
    rms = float(np.sqrt(np.mean(ref_avg ** 2)))
    print(f"  Loopback ref RMS = {rms:.6f}", flush=True)
    return ref_avg


def hardware_capture(mode_freqs: list[float], carrier_indices: list[int],
                     pattern: np.ndarray, sample_rate: int, device_idx: int,
                     duration_s: float = 0.2,
                     loopback_ref: np.ndarray | None = None) -> np.ndarray:
    """Drive pattern as multitone, capture spectrum at all mode freqs.

    If loopback_ref is provided (raw RX waveform captured with relay OFF),
    it is subtracted from each capture in time domain before FFT.
    """
    import sounddevice as sd

    # Extend TX to cover USB latency + desired analysis window
    total_dur = USB_LATENCY_S + duration_s
    n_samples = int(sample_rate * total_dur)
    t = np.arange(n_samples) / sample_rate
    sig = np.zeros(n_samples, dtype=np.float64)

    rng = np.random.default_rng(42)
    for b in range(len(carrier_indices)):
        if pattern[b] > 0:
            freq = mode_freqs[carrier_indices[b]]
            phi = rng.uniform(0, 2 * np.pi)
            sig += np.sin(2 * np.pi * freq * t + phi)

    peak = np.max(np.abs(sig))
    if peak > 0:
        sig *= DRIVE_AMPLITUDE / peak

    tx = sig.astype(np.float32).reshape(-1, 1)

    sum_mags = np.zeros(len(mode_freqs))
    for _ in range(N_AVG):
        rx = sd.playrec(tx, samplerate=sample_rate,
                        input_mapping=[1], output_mapping=[1],
                        device=device_idx, dtype=AUDIO_DTYPE, blocking=True)
        rx_mono = rx[:, 0].astype(np.float64)

        # Skip USB round-trip latency — signal starts arriving after this
        settle = int(sample_rate * USB_LATENCY_S)
        rx_capture = rx_mono[settle:]

        # Subtract USB loopback if reference available
        if loopback_ref is not None:
            ref_capture = loopback_ref[settle:]
            min_len = min(len(rx_capture), len(ref_capture))
            rx_capture = rx_capture[:min_len] - ref_capture[:min_len]

        windowed = rx_capture * np.hanning(len(rx_capture))
        nfft = len(rx_capture) * 4
        spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
        bin_hz = freq_axis[1] if len(freq_axis) > 1 else 1.0

        mags = np.zeros(len(mode_freqs))
        for j, f in enumerate(mode_freqs):
            tb = int(round(f / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(spectrum) - 1, tb + 3)
            mags[j] = float(np.max(spectrum[lo:hi + 1]))
        sum_mags += mags

    return sum_mags / N_AVG


def hardware_capture_squared(mode_freqs: list[float], carrier_indices: list[int],
                            pattern: np.ndarray, sample_rate: int,
                            device_idx: int,
                            duration_s: float = 0.2,
                            loopback_ref: np.ndarray | None = None) -> np.ndarray:
    """Drive pattern as multitone, capture linear + squared-signal features.

    The squared signal y²(t) produces beat frequencies at f_i ± f_j
    that appear IFF both carriers i and j are ON.  These cross-terms
    break the end-to-end linearity that makes raw-spectrum readout
    unable to solve XOR/parity.

    Returns concatenated [linear_mags (N_modes), squared_feats (N_sq)].
    """
    import sounddevice as sd

    total_dur = USB_LATENCY_S + duration_s
    n_samples = int(sample_rate * total_dur)
    t = np.arange(n_samples) / sample_rate
    sig = np.zeros(n_samples, dtype=np.float64)

    rng = np.random.default_rng(42)
    active_freqs = []
    for b in range(len(carrier_indices)):
        freq = mode_freqs[carrier_indices[b]]
        if pattern[b] > 0:
            phi = rng.uniform(0, 2 * np.pi)
            sig += np.sin(2 * np.pi * freq * t + phi)
            active_freqs.append(freq)
        else:
            rng.uniform(0, 2 * np.pi)  # keep RNG in sync

    peak = np.max(np.abs(sig))
    if peak > 0:
        sig *= DRIVE_AMPLITUDE / peak

    tx = sig.astype(np.float32).reshape(-1, 1)

    # Build list of squared-feature frequencies:
    # difference beats |fi - fj|, sum beats fi + fj, double freqs 2*fi
    carrier_freqs = [mode_freqs[carrier_indices[b]]
                     for b in range(len(carrier_indices))]
    sq_freqs = []
    sq_labels = []
    n_ci = len(carrier_indices)
    nyquist_hw = sample_rate / 2
    for i in range(n_ci):
        dbl = 2 * carrier_freqs[i]
        if dbl < nyquist_hw:
            sq_freqs.append(dbl)
            sq_labels.append(f"2f{i}")
    for i in range(n_ci):
        for j in range(i + 1, n_ci):
            diff_f = abs(carrier_freqs[i] - carrier_freqs[j])
            sum_f = carrier_freqs[i] + carrier_freqs[j]
            if diff_f > 0:
                sq_freqs.append(diff_f)
                sq_labels.append(f"|f{i}-f{j}|")
            if sum_f < nyquist_hw:
                sq_freqs.append(sum_f)
                sq_labels.append(f"f{i}+f{j}")

    n_sq = len(sq_freqs)
    sum_mags = np.zeros(len(mode_freqs))
    sum_sq = np.zeros(n_sq)

    for _ in range(N_AVG):
        rx = sd.playrec(tx, samplerate=sample_rate,
                        input_mapping=[1], output_mapping=[1],
                        device=device_idx, dtype=AUDIO_DTYPE, blocking=True)
        rx_mono = rx[:, 0].astype(np.float64)

        # Skip USB round-trip latency
        settle = int(sample_rate * USB_LATENCY_S)
        rx_capture = rx_mono[settle:]

        # Subtract USB loopback if reference available
        if loopback_ref is not None:
            ref_capture = loopback_ref[settle:]
            min_len = min(len(rx_capture), len(ref_capture))
            rx_capture = rx_capture[:min_len] - ref_capture[:min_len]

        # --- Linear features (same as hardware_capture) ---
        windowed = rx_capture * np.hanning(len(rx_capture))
        nfft = len(rx_capture) * 4
        spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
        freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
        bin_hz = freq_axis[1] if len(freq_axis) > 1 else 1.0

        mags = np.zeros(len(mode_freqs))
        for j, f in enumerate(mode_freqs):
            tb = int(round(f / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(spectrum) - 1, tb + 3)
            mags[j] = float(np.max(spectrum[lo:hi + 1]))
        sum_mags += mags

        # --- Squared-signal features ---
        rx_sq = rx_capture ** 2
        windowed_sq = rx_sq * np.hanning(len(rx_sq))
        spectrum_sq = np.abs(np.fft.rfft(windowed_sq, n=nfft))

        sq_mags = np.zeros(n_sq)
        for k, sf in enumerate(sq_freqs):
            tb = int(round(sf / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(spectrum_sq) - 1, tb + 3)
            sq_mags[k] = float(np.max(spectrum_sq[lo:hi + 1]))
        sum_sq += sq_mags

    return np.concatenate([sum_mags / N_AVG, sum_sq / N_AVG])


def hardware_capture_sequential(mode_freqs: list[float],
                                carrier_indices: list[int],
                                pattern: np.ndarray,
                                sample_rate: int, device_idx: int,
                                duration_s: float = 0.2,
                                loopback_ref: np.ndarray | None = None
                                ) -> np.ndarray:
    """Drive ONE carrier at a time at full amplitude, read all modes.

    Produces an N_carriers × N_modes cross-coupling matrix (flattened),
    mirroring the PicoScope sequential-sine protocol that achieved
    separation indices >3,000.

    For each active carrier bit:
      - Drive that single frequency at full DRIVE_AMPLITUDE
      - Capture response at all mode frequencies
    For each inactive carrier bit:
      - Drive nothing (silence), capture noise floor at all mode freqs

    Returns flattened array of shape (n_carriers * n_modes,).
    """
    import sounddevice as sd

    n_modes = len(mode_freqs)
    n_carriers = len(carrier_indices)
    cross_matrix = np.zeros((n_carriers, n_modes))

    total_dur = USB_LATENCY_S + duration_s

    for b in range(n_carriers):
        n_samples = int(sample_rate * total_dur)
        t = np.arange(n_samples) / sample_rate

        if pattern[b] > 0:
            freq = mode_freqs[carrier_indices[b]]
            sig = DRIVE_AMPLITUDE * np.sin(2 * np.pi * freq * t)
        else:
            sig = np.zeros(n_samples, dtype=np.float64)

        tx = sig.astype(np.float32).reshape(-1, 1)

        sum_mags = np.zeros(n_modes)
        for _ in range(N_AVG):
            rx = sd.playrec(tx, samplerate=sample_rate,
                            input_mapping=[1], output_mapping=[1],
                            device=device_idx, dtype=AUDIO_DTYPE,
                            blocking=True)
            rx_mono = rx[:, 0].astype(np.float64)

            settle = int(sample_rate * USB_LATENCY_S)
            rx_capture = rx_mono[settle:]

            if loopback_ref is not None:
                ref_capture = loopback_ref[settle:]
                min_len = min(len(rx_capture), len(ref_capture))
                rx_capture = rx_capture[:min_len] - ref_capture[:min_len]

            windowed = rx_capture * np.hanning(len(rx_capture))
            nfft = len(rx_capture) * 4
            spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
            bin_hz = freq_axis[1] if len(freq_axis) > 1 else 1.0

            mags = np.zeros(n_modes)
            for j, f in enumerate(mode_freqs):
                tb = int(round(f / bin_hz))
                lo = max(0, tb - 3)
                hi = min(len(spectrum) - 1, tb + 3)
                mags[j] = float(np.max(spectrum[lo:hi + 1]))
            sum_mags += mags

        cross_matrix[b, :] = sum_mags / N_AVG

    return cross_matrix.ravel()


def simulated_capture_sequential(mode_freqs: list[float],
                                 carrier_indices: list[int],
                                 pattern: np.ndarray,
                                 census_mags: np.ndarray,
                                 noise_std: float = 0.01) -> np.ndarray:
    """Simulate sequential-sine capture using census transfer function.

    Same cross-coupling matrix as hardware_capture_sequential but
    synthesized from census magnitudes.

    Returns flattened array of shape (n_carriers * n_modes,).
    """
    n_modes = len(mode_freqs)
    n_carriers = len(carrier_indices)
    cross_matrix = np.zeros((n_carriers, n_modes))
    rng = np.random.default_rng(hash(tuple(pattern.tolist())) % (2**32))

    for b in range(n_carriers):
        ci = carrier_indices[b]
        if pattern[b] > 0:
            # Self-coupling: strong (full amplitude to one carrier)
            cross_matrix[b, ci] = census_mags[ci]
            # Cross-coupling: weak, frequency-distance dependent
            for j in range(n_modes):
                if j != ci:
                    dist = abs(mode_freqs[j] - mode_freqs[ci])
                    coupling = census_mags[j] * 0.05 * np.exp(-dist / 5000)
                    cross_matrix[b, j] = coupling
        # Add noise to this row
        cross_matrix[b, :] += rng.normal(0, noise_std, n_modes)
        cross_matrix[b, :] = np.maximum(cross_matrix[b, :], 0)

    return cross_matrix.ravel()


def simulated_capture_squared(mode_freqs: list[float],
                              carrier_indices: list[int],
                              pattern: np.ndarray,
                              census_mags: np.ndarray,
                              noise_std: float = 0.01) -> np.ndarray:
    """Simulate plate + squared-signal features.

    Generates an actual time-domain multitone using census magnitudes
    as transfer gains, then squares and FFTs — same math as hardware.
    """
    sr = 192000  # match hardware rate so beat freqs stay below Nyquist
    dur = 0.2
    n_samples = int(sr * dur)
    t = np.arange(n_samples) / sr

    n_ci = len(carrier_indices)
    carrier_freqs = [mode_freqs[carrier_indices[b]] for b in range(n_ci)]

    # Synthesize plate output as weighted sum of tones
    rng = np.random.default_rng(hash(tuple(pattern.tolist())) % (2**32))
    rx_sig = np.zeros(n_samples)
    for b in range(n_ci):
        if pattern[b] > 0:
            fc = carrier_freqs[b]
            gain = census_mags[carrier_indices[b]]
            phi = rng.uniform(0, 2 * np.pi)
            rx_sig += gain * np.sin(2 * np.pi * fc * t + phi)
    rx_sig += rng.normal(0, noise_std, n_samples)

    # Linear features at mode freqs
    windowed = rx_sig * np.hanning(n_samples)
    nfft = n_samples * 4
    spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sr)
    bin_hz = freq_axis[1] if len(freq_axis) > 1 else 1.0

    lin_mags = np.zeros(len(mode_freqs))
    for j, f in enumerate(mode_freqs):
        tb = int(round(f / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(spectrum) - 1, tb + 3)
        lin_mags[j] = float(np.max(spectrum[lo:hi + 1]))

    # Squared features
    nyquist = sr / 2
    sq_freqs = []
    for i in range(n_ci):
        dbl = 2 * carrier_freqs[i]
        if dbl < nyquist:
            sq_freqs.append(dbl)
    for i in range(n_ci):
        for j in range(i + 1, n_ci):
            diff_f = abs(carrier_freqs[i] - carrier_freqs[j])
            sum_f = carrier_freqs[i] + carrier_freqs[j]
            if diff_f > 0:
                sq_freqs.append(diff_f)
            if sum_f < nyquist:
                sq_freqs.append(sum_f)

    rx_sq = rx_sig ** 2
    windowed_sq = rx_sq * np.hanning(n_samples)
    spectrum_sq = np.abs(np.fft.rfft(windowed_sq, n=nfft))

    sq_mags = np.zeros(len(sq_freqs))
    for k, sf in enumerate(sq_freqs):
        tb = int(round(sf / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(spectrum_sq) - 1, tb + 3)
        if hi >= lo:
            sq_mags[k] = float(np.max(spectrum_sq[lo:hi + 1]))

    return np.concatenate([lin_mags, sq_mags])


# ══════════════════════════════════════════════════════════════════════
# Simulated capture (from census transfer function)
# ══════════════════════════════════════════════════════════════════════

def simulated_capture(mode_freqs: list[float], carrier_indices: list[int],
                      pattern: np.ndarray, census_mags: np.ndarray,
                      noise_std: float = 0.01) -> np.ndarray:
    """Simulate plate response using census magnitude as transfer function.

    Model: output[i] = sum_j(pattern[j] * H[carrier_j, i]) + noise
    Where H[j, i] is the cross-coupling from driven mode j to readout mode i.

    For carrier modes: strong self-coupling (magnitude from census).
    For non-carrier modes: weak coupling (random, scaled by mode proximity).
    """
    n_modes = len(mode_freqs)
    n_bits = len(carrier_indices)

    # Build a simplified transfer matrix
    rng = np.random.default_rng(hash(tuple(pattern.tolist())) % (2**32))

    output = np.zeros(n_modes)
    for b in range(n_bits):
        if pattern[b] > 0:
            ci = carrier_indices[b]
            # Self-coupling: strong
            output[ci] += census_mags[ci]
            # Cross-coupling: weak, decays with frequency distance
            for j in range(n_modes):
                if j != ci:
                    dist = abs(mode_freqs[j] - mode_freqs[ci])
                    coupling = census_mags[j] * 0.05 * np.exp(-dist / 5000)
                    # Add pattern-dependent nonlinearity
                    coupling *= (1 + 0.1 * np.sum(pattern) / n_bits)
                    output[j] += coupling

    # Add measurement noise
    output += rng.normal(0, noise_std, n_modes)
    output = np.maximum(output, 0)  # magnitude is non-negative

    return output


# ══════════════════════════════════════════════════════════════════════
# Feature extraction + readout
# ══════════════════════════════════════════════════════════════════════

def interaction_expand(x, max_degree=3):
    n = len(x)
    terms = list(x)
    for d in range(2, max_degree + 1):
        for combo in combinations(range(n), d):
            t = 1.0
            for idx in combo:
                t *= x[idx]
            terms.append(t)
    return np.array(terms)


def ridge_classify(X_tr, X_te, y_tr, y_te, alpha=1.0, n_classes=None):
    if n_classes is None:
        n_classes = len(np.unique(y_tr))
    Xb_tr = np.column_stack([X_tr, np.ones(len(y_tr))])
    Xb_te = np.column_stack([X_te, np.ones(len(y_te))])
    d = Xb_tr.shape[1]
    Y_oh = np.zeros((len(y_tr), n_classes))
    for i, lbl in enumerate(y_tr):
        Y_oh[i, int(lbl)] = 1.0
    W = np.linalg.solve(Xb_tr.T @ Xb_tr + alpha * np.eye(d), Xb_tr.T @ Y_oh)
    tr_acc = float(np.mean(np.argmax(Xb_tr @ W, axis=1) == y_tr))
    te_acc = float(np.mean(np.argmax(Xb_te @ W, axis=1) == y_te))
    return tr_acc, te_acc


def ridge_regress(X_tr, X_te, y_tr, y_te, alpha=1.0):
    Xb_tr = np.column_stack([X_tr, np.ones(len(y_tr))])
    Xb_te = np.column_stack([X_te, np.ones(len(y_te))])
    d = Xb_tr.shape[1]
    W = np.linalg.solve(Xb_tr.T @ Xb_tr + alpha * np.eye(d),
                        Xb_tr.T @ y_tr)
    tr_pred = Xb_tr @ W
    te_pred = Xb_te @ W
    tr_mse = float(np.mean((tr_pred - y_tr) ** 2))
    te_mse = float(np.mean((te_pred - y_te) ** 2))
    tr_nmse = tr_mse / max(np.var(y_tr), 1e-8)
    te_nmse = te_mse / max(np.var(y_te), 1e-8)
    return tr_nmse, te_nmse


# ══════════════════════════════════════════════════════════════════════
# Software baselines (for comparison)
# ══════════════════════════════════════════════════════════════════════

def software_logistic(X_tr, X_te, y_tr, y_te):
    """Simple logistic regression baseline (pure software, no plate)."""
    # One-hot encode input, solve with ridge
    return ridge_classify(X_tr, X_te, y_tr, y_te, alpha=0.01)


def software_mlp(X_tr, X_te, y_tr, y_te, hidden=64, n_classes=None):
    """2-layer MLP baseline using random features (no plate physics)."""
    if n_classes is None:
        n_classes = len(np.unique(y_tr))
    rng = np.random.default_rng(42)
    W1 = rng.standard_normal((X_tr.shape[1], hidden)) * 0.1
    b1 = np.zeros(hidden)

    # ReLU hidden layer (random, untrained — same as extreme learning machine)
    H_tr = np.maximum(X_tr @ W1 + b1, 0)
    H_te = np.maximum(X_te @ W1 + b1, 0)

    return ridge_classify(H_tr, H_te, y_tr, y_te, alpha=1.0,
                          n_classes=n_classes)


# ══════════════════════════════════════════════════════════════════════
# Benchmark 1: N-bit parity (XOR generalization)
# ══════════════════════════════════════════════════════════════════════

def benchmark_parity(mode_freqs, carrier_indices, census_mags,
                     capture_fn, n_bits_list=None, n_reps=4,
                     feature_mode="linear"):
    """Test parity classification for increasing bit widths.

    feature_mode:
      'linear'   — use only the first N_modes features (FFT peak mags)
      'squared'  — use only the squared-signal features (beat freqs)
      'combined' — concatenate both
      'poly'     — linear mags + polynomial expansion of carrier bins
      'sequential' — cross-coupling matrix (N_carriers × N_modes), full power
                     per carrier. All features used with log1p normalization.
      'seqpoly'  — sequential capture + polynomial expansion on diagonal
                   self-coupling features (closest match to PicoScope protocol)
    """
    if n_bits_list is None:
        n_bits_list = [3, 4, 5, 6, 7]

    results = []
    for n_bits in n_bits_list:
        ci = carrier_indices[:n_bits]
        n_patterns = 2 ** n_bits
        all_patterns = np.array(
            [[(i >> b) & 1 for b in range(n_bits)]
             for i in range(n_patterns)])
        y_parity = np.sum(all_patterns, axis=1) % 2
        y_majority = (np.sum(all_patterns, axis=1) > n_bits / 2).astype(int)

        # Capture: each pattern n_reps times
        X_all = []
        y_par_all = []
        y_maj_all = []
        total_captures = n_patterns * n_reps
        capture_count = 0
        t0 = time.time()

        print(f"    {n_bits}-bit: {n_patterns} patterns × {n_reps} reps "
              f"= {total_captures} captures", flush=True)

        for rep in range(n_reps):
            for p_idx in range(n_patterns):
                capture_count += 1
                pat_str = ''.join(str(int(x)) for x in all_patterns[p_idx])
                elapsed = time.time() - t0
                if capture_count > 1:
                    eta = elapsed / (capture_count - 1) * (total_captures - capture_count + 1)
                    eta_str = f" ETA {eta/60:.1f}min"
                else:
                    eta_str = ""
                print(f"      [{capture_count}/{total_captures}] "
                      f"rep={rep+1}/{n_reps} pat={pat_str} "
                      f"({elapsed:.0f}s elapsed{eta_str})", flush=True)
                mags = capture_fn(mode_freqs, ci, all_patterns[p_idx],
                                  census_mags)
                X_all.append(mags)
                y_par_all.append(y_parity[p_idx])
                y_maj_all.append(y_majority[p_idx])

        capture_time = time.time() - t0
        print(f"    {n_bits}-bit capture complete: {capture_time:.0f}s total",
              flush=True)
        X_all = np.array(X_all)
        y_par_all = np.array(y_par_all)
        y_maj_all = np.array(y_maj_all)

        # Slice features based on mode
        n_modes = len(mode_freqs)
        if feature_mode == "poly":
            # Poly: normalize linear features FIRST, then compute products
            # from normalized carrier magnitudes. This preserves the
            # ON/OFF contrast that log1p(raw product) would compress.
            X_lin = X_all[:, :n_modes]
            X_lin_log = np.log1p(X_lin)
            mu_lin = X_lin_log.mean(axis=0)
            sigma_lin = X_lin_log.std(axis=0) + 1e-8
            X_lin_std = (X_lin_log - mu_lin) / sigma_lin

            carrier_normed = X_lin_std[:, ci]
            n_ci = carrier_normed.shape[1]
            poly_cols = []
            for deg in range(2, n_ci + 1):
                for combo in combinations(range(n_ci), deg):
                    col = np.ones(len(X_lin))
                    for idx in combo:
                        col *= carrier_normed[:, idx]
                    poly_cols.append(col)
            X_poly = np.column_stack(poly_cols) if poly_cols else np.empty(
                (len(X_lin), 0))
            # Z-score the poly columns separately
            mu_poly = X_poly.mean(axis=0)
            sigma_poly = X_poly.std(axis=0) + 1e-8
            X_poly_std = (X_poly - mu_poly) / sigma_poly

            X_std = np.column_stack([X_lin_std, X_poly_std])
            n_feat = X_std.shape[1]
        elif feature_mode == "seqpoly":
            # Sequential + poly: extract diagonal self-coupling features
            # (carrier b's response at its own mode frequency) from the
            # N_carriers × N_modes cross-coupling matrix, then expand
            # with polynomial products. This mirrors the PicoScope protocol
            # where separation indices were >3,000.
            X_all_log = np.log1p(X_all)
            mu_all = X_all_log.mean(axis=0)
            sigma_all = X_all_log.std(axis=0) + 1e-8
            X_all_std = (X_all_log - mu_all) / sigma_all

            # Extract diagonal: carrier b's self-response is at
            # index b * n_modes + ci[b] in the flattened vector
            diag_indices = [b * n_modes + ci[b] for b in range(n_bits)]
            carrier_normed = X_all_std[:, diag_indices]

            n_ci = carrier_normed.shape[1]
            poly_cols = []
            for deg in range(2, n_ci + 1):
                for combo in combinations(range(n_ci), deg):
                    col = np.ones(len(X_all))
                    for idx in combo:
                        col *= carrier_normed[:, idx]
                    poly_cols.append(col)
            X_poly = np.column_stack(poly_cols) if poly_cols else np.empty(
                (len(X_all), 0))
            mu_poly = X_poly.mean(axis=0)
            sigma_poly = X_poly.std(axis=0) + 1e-8
            X_poly_std = (X_poly - mu_poly) / sigma_poly

            X_std = np.column_stack([X_all_std, X_poly_std])
            n_feat = X_std.shape[1]
        elif feature_mode in ("sequential",):
            # Sequential: use full cross-coupling matrix as-is
            X_log = np.log1p(X_all)
            mu = X_log.mean(axis=0)
            sigma = X_log.std(axis=0) + 1e-8
            X_std = (X_log - mu) / sigma
            n_feat = X_all.shape[1]
        else:
            if feature_mode == "linear":
                X_feat = X_all[:, :n_modes]
            elif feature_mode == "squared":
                X_feat = X_all[:, n_modes:]
            else:  # combined
                X_feat = X_all

            # Normalize
            X_log = np.log1p(X_feat)
            mu = X_log.mean(axis=0)
            sigma = X_log.std(axis=0) + 1e-8
            X_std = (X_log - mu) / sigma
            n_feat = X_feat.shape[1]

        # Train/test split (leave-one-rep-out)
        n_per_rep = n_patterns
        X_train = X_std[:n_per_rep * (n_reps - 1)]
        X_test = X_std[n_per_rep * (n_reps - 1):]
        y_par_tr = y_par_all[:n_per_rep * (n_reps - 1)]
        y_par_te = y_par_all[n_per_rep * (n_reps - 1):]
        y_maj_tr = y_maj_all[:n_per_rep * (n_reps - 1)]
        y_maj_te = y_maj_all[n_per_rep * (n_reps - 1):]

        # Plate: features from selected mode
        par_raw_tr, par_raw_te = ridge_classify(X_train, X_test,
                                                y_par_tr, y_par_te)
        maj_raw_tr, maj_raw_te = ridge_classify(X_train, X_test,
                                                y_maj_tr, y_maj_te)

        # Software baselines: use binary patterns directly
        P_train = np.tile(all_patterns, (n_reps - 1, 1))
        P_test = all_patterns.copy()
        sw_log_tr, sw_log_te = software_logistic(P_train, P_test,
                                                  y_par_tr, y_par_te)
        sw_mlp_tr, sw_mlp_te = software_mlp(P_train, P_test,
                                             y_par_tr, y_par_te)

        # Inference latency
        latency_ms = (capture_time / (n_patterns * n_reps)) * 1000
        energy_per_query_mj = latency_ms * POWER_TOTAL_W

        r = {
            "benchmark": "parity",
            "feature_mode": feature_mode,
            "n_bits": n_bits,
            "n_patterns": n_patterns,
            "n_readout_dims": n_feat,
            "plate_parity_raw_test": round(par_raw_te * 100, 1),
            "plate_majority_raw_test": round(maj_raw_te * 100, 1),
            "sw_logistic_parity_test": round(sw_log_te * 100, 1),
            "sw_mlp_parity_test": round(sw_mlp_te * 100, 1),
            "latency_ms": round(latency_ms, 2),
            "energy_per_query_mJ": round(energy_per_query_mj, 2),
            "capture_time_s": round(capture_time, 1),
        }
        results.append(r)
        tag = f"[{feature_mode.upper()}]"
        print(f"    {n_bits}-bit parity {tag}: plate={par_raw_te:.1%} "
              f"sw_log={sw_log_te:.1%} sw_mlp={sw_mlp_te:.1%} "
              f"latency={latency_ms:.1f}ms ({n_feat} feats)")

    return results


# ══════════════════════════════════════════════════════════════════════
# Benchmark 2: Nonlinear function approximation
# ══════════════════════════════════════════════════════════════════════

def benchmark_nonlinear(mode_freqs, carrier_indices, census_mags,
                        capture_fn, n_samples=200):
    """Test regression on nonlinear functions."""
    n_bits = min(7, len(carrier_indices))
    ci = carrier_indices[:n_bits]
    n_patterns = 2 ** n_bits

    all_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_bits)]
         for i in range(n_patterns)])

    # Target functions
    def f_xor_surface(p):
        """Multi-dimensional XOR: parity of all bits."""
        return float(np.sum(p) % 2)

    def f_sinusoidal(p):
        """sin of weighted sum — tests smooth nonlinearity."""
        weights = np.array([1.0, 0.7, 0.5, 0.3, 0.2, 0.1, 0.05][:n_bits])
        return float(np.sin(np.pi * np.dot(p, weights)))

    def f_threshold_count(p):
        """Number of active bits > threshold — a counting task."""
        return float(np.sum(p) / n_bits)

    functions = [
        ("xor_surface", f_xor_surface),
        ("sinusoidal", f_sinusoidal),
        ("threshold_count", f_threshold_count),
    ]

    # Sample patterns (with replacement if n_samples > n_patterns)
    rng = np.random.default_rng(42)
    idx = rng.choice(n_patterns, min(n_samples, n_patterns), replace=False)
    patterns = all_patterns[idx]

    # Capture
    X_all = []
    t0 = time.time()
    n_total = len(patterns)
    print(f"    Capturing {n_total} nonlinear patterns...", flush=True)
    for i, p in enumerate(patterns):
        if (i + 1) % 10 == 0 or i == 0:
            elapsed = time.time() - t0
            if i > 0:
                eta = elapsed / i * (n_total - i)
                eta_str = f" ETA {eta/60:.1f}min"
            else:
                eta_str = ""
            print(f"      [{i+1}/{n_total}] ({elapsed:.0f}s{eta_str})",
                  flush=True)
        mags = capture_fn(mode_freqs, ci, p, census_mags)
        X_all.append(mags)
    capture_time = time.time() - t0
    print(f"    Nonlinear capture complete: {capture_time:.0f}s", flush=True)
    X_all = np.array(X_all)

    X_log = np.log1p(X_all)
    mu = X_log.mean(axis=0)
    sigma = X_log.std(axis=0) + 1e-8
    X_std = (X_log - mu) / sigma

    n_train = int(0.75 * len(patterns))
    X_tr = X_std[:n_train]
    X_te = X_std[n_train:]
    P_tr = patterns[:n_train].astype(float)
    P_te = patterns[n_train:].astype(float)

    results = []
    for fname, func in functions:
        y = np.array([func(p) for p in patterns])
        y_tr = y[:n_train]
        y_te = y[n_train:]

        # Plate readout
        plate_tr_nmse, plate_te_nmse = ridge_regress(X_tr, X_te, y_tr, y_te)

        # Software baseline: direct input
        sw_tr_nmse, sw_te_nmse = ridge_regress(P_tr, P_te, y_tr, y_te)

        latency_ms = (capture_time / len(patterns)) * 1000

        r = {
            "benchmark": "nonlinear",
            "function": fname,
            "plate_nmse_test": round(plate_te_nmse, 4),
            "sw_linear_nmse_test": round(sw_te_nmse, 4),
            "plate_advantage": round(sw_te_nmse - plate_te_nmse, 4),
            "latency_ms": round(latency_ms, 2),
        }
        results.append(r)
        tag = "BETTER" if plate_te_nmse < sw_te_nmse else "WORSE"
        print(f"    {fname}: plate_NMSE={plate_te_nmse:.4f} "
              f"sw_NMSE={sw_te_nmse:.4f} [{tag}]")

    return results


# ══════════════════════════════════════════════════════════════════════
# Benchmark 3: High-dimensional random classification (capacity test)
# ══════════════════════════════════════════════════════════════════════

def benchmark_capacity(mode_freqs, carrier_indices, census_mags,
                       capture_fn, n_classes_list=None):
    """Test classification with increasing number of random classes.

    This measures the reservoir's effective dimensionality:
    at what point does classification accuracy collapse?
    """
    if n_classes_list is None:
        n_classes_list = [2, 4, 8, 16, 32, 64]

    n_bits = min(7, len(carrier_indices))
    ci = carrier_indices[:n_bits]
    n_patterns = 2 ** n_bits
    all_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_bits)]
         for i in range(n_patterns)])

    results = []
    for n_classes in n_classes_list:
        if n_classes > n_patterns:
            break

        # Assign random class labels
        rng = np.random.default_rng(n_classes)
        labels = rng.integers(0, n_classes, n_patterns)

        # Ensure at least 2 samples per class
        for c in range(n_classes):
            if np.sum(labels == c) < 2:
                idx = rng.choice(n_patterns)
                labels[idx] = c

        # Capture
        X_all = []
        t0 = time.time()
        print(f"    {n_classes}-class: capturing {n_patterns} patterns...",
              flush=True)
        for i, p in enumerate(all_patterns):
            if (i + 1) % 16 == 0 or i == 0:
                elapsed = time.time() - t0
                if i > 0:
                    eta = elapsed / i * (n_patterns - i)
                    eta_str = f" ETA {eta/60:.1f}min"
                else:
                    eta_str = ""
                print(f"      [{i+1}/{n_patterns}] ({elapsed:.0f}s{eta_str})",
                      flush=True)
            mags = capture_fn(mode_freqs, ci, p, census_mags)
            X_all.append(mags)
        capture_time = time.time() - t0
        print(f"    {n_classes}-class capture complete: {capture_time:.0f}s",
              flush=True)
        X_all = np.array(X_all)

        X_log = np.log1p(X_all)
        mu = X_log.mean(axis=0)
        sigma = X_log.std(axis=0) + 1e-8
        X_std = (X_log - mu) / sigma

        n_train = int(0.75 * n_patterns)
        X_tr = X_std[:n_train]
        X_te = X_std[n_train:]
        y_tr = labels[:n_train]
        y_te = labels[n_train:]
        P_tr = all_patterns[:n_train].astype(float)
        P_te = all_patterns[n_train:].astype(float)

        plate_tr, plate_te = ridge_classify(X_tr, X_te, y_tr, y_te,
                                            n_classes=n_classes)
        sw_tr, sw_te = software_mlp(P_tr, P_te, y_tr, y_te,
                                    hidden=64, n_classes=n_classes)
        chance = 1.0 / n_classes

        r = {
            "benchmark": "capacity",
            "n_classes": n_classes,
            "plate_test": round(plate_te * 100, 1),
            "sw_mlp_test": round(sw_te * 100, 1),
            "chance_pct": round(chance * 100, 1),
            "plate_above_chance": round((plate_te - chance) * 100, 1),
        }
        results.append(r)
        print(f"    {n_classes:>3} classes: plate={plate_te:.1%} "
              f"sw_mlp={sw_te:.1%} chance={chance:.1%}")

    return results


# ══════════════════════════════════════════════════════════════════════
# Bittensor viability model
# ══════════════════════════════════════════════════════════════════════

def bittensor_viability(benchmark_results: list[dict],
                        n_modes: int) -> dict:
    """Model whether plate mining is viable on Bittensor.

    Estimates:
    - TAO earnings based on inference quality score
    - Power cost at residential electricity rates
    - Hardware amortization
    - Net daily profit/loss
    """

    # ── Current TAO economics (approximate, April 2026) ──
    TAO_PRICE_USD = 350.0        # ~$350/TAO
    DAILY_EMISSION_TAO = 7200    # ~7200 TAO/day across all subnets
    N_SUBNETS = 47               # active subnets
    TAO_PER_SUBNET_DAY = DAILY_EMISSION_TAO / N_SUBNETS

    # ── Miner's share assumptions ──
    # Top miner in a subnet gets ~10-15% of subnet emissions
    # Average competitive miner: ~2-5%
    # New entrant: ~0.5-1%
    MINER_SHARE_OPTIMISTIC = 0.10
    MINER_SHARE_REALISTIC = 0.02
    MINER_SHARE_PESSIMISTIC = 0.005

    # ── Power costs ──
    ELECTRICITY_USD_KWH = 0.12   # US residential average
    HOURS_PER_DAY = 24

    power_kwh_day = POWER_TOTAL_W * HOURS_PER_DAY / 1000
    daily_power_cost = power_kwh_day * ELECTRICITY_USD_KWH

    gpu_power_kwh_day = POWER_GPU_INFERENCE_W * HOURS_PER_DAY / 1000
    gpu_daily_power_cost = gpu_power_kwh_day * ELECTRICITY_USD_KWH

    # ── Hardware costs ──
    PLATE_HARDWARE_USD = 200     # plates + PZTs + mounts
    KRONOS_USD = 0               # already owned
    ARDUINO_USD = 15
    MISC_USD = 50
    TOTAL_HARDWARE_USD = PLATE_HARDWARE_USD + KRONOS_USD + ARDUINO_USD + MISC_USD
    AMORTIZE_DAYS = 365

    daily_hardware = TOTAL_HARDWARE_USD / AMORTIZE_DAYS

    # ── Inference throughput ──
    # From benchmark latency data
    parity_results = [r for r in benchmark_results
                      if r.get("benchmark") == "parity"]
    if parity_results:
        avg_latency_ms = np.mean([r["latency_ms"] for r in parity_results])
    else:
        avg_latency_ms = 500  # default estimate

    queries_per_second = 1000 / avg_latency_ms if avg_latency_ms > 0 else 2
    queries_per_day = queries_per_second * 86400

    # ── Best accuracy achieved ──
    best_accuracy = 0
    for r in benchmark_results:
        for key in r:
            if "test" in key and isinstance(r[key], (int, float)):
                best_accuracy = max(best_accuracy, r[key])

    # ── Earnings scenarios ──
    scenarios = {}
    for label, share in [("optimistic", MINER_SHARE_OPTIMISTIC),
                         ("realistic", MINER_SHARE_REALISTIC),
                         ("pessimistic", MINER_SHARE_PESSIMISTIC)]:
        daily_tao = TAO_PER_SUBNET_DAY * share
        daily_usd = daily_tao * TAO_PRICE_USD
        daily_cost = daily_power_cost + daily_hardware
        daily_profit = daily_usd - daily_cost
        annual_profit = daily_profit * 365

        scenarios[label] = {
            "daily_tao": round(daily_tao, 4),
            "daily_usd": round(daily_usd, 2),
            "daily_power_cost": round(daily_power_cost, 2),
            "daily_hardware_cost": round(daily_hardware, 2),
            "daily_total_cost": round(daily_cost, 2),
            "daily_profit": round(daily_profit, 2),
            "annual_profit": round(annual_profit, 0),
            "profitable": daily_profit > 0,
        }

    return {
        "power_watts": POWER_TOTAL_W,
        "power_kwh_per_day": round(power_kwh_day, 2),
        "gpu_comparison_kwh_per_day": round(gpu_power_kwh_day, 2),
        "power_ratio_vs_gpu": round(POWER_GPU_INFERENCE_W / POWER_TOTAL_W, 1),
        "queries_per_second": round(queries_per_second, 2),
        "queries_per_day": int(queries_per_day),
        "avg_latency_ms": round(avg_latency_ms, 1),
        "best_accuracy_pct": best_accuracy,
        "n_readout_dims": n_modes,
        "hardware_cost_usd": TOTAL_HARDWARE_USD,
        "scenarios": scenarios,
        "tao_price_usd": TAO_PRICE_USD,
        "breakeven_note": (
            f"At {POWER_TOTAL_W}W vs GPU {POWER_GPU_INFERENCE_W}W, "
            f"plate uses {POWER_GPU_INFERENCE_W/POWER_TOTAL_W:.0f}× less power. "
            f"Viable if inference quality scores competitively."
        ),
    }


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plate reservoir benchmark — standard ML tasks")
    parser.add_argument("port", nargs="?", default=None,
                        help="Arduino serial port (required for --hardware)")
    parser.add_argument("--device", default="KRONOS")
    parser.add_argument("--census", required=True, help="Census JSON path")
    parser.add_argument("--plate", default="5", help="Plate ID (1-5)")
    parser.add_argument("--hardware", action="store_true",
                        help="Use real hardware (Kronos + relay)")
    parser.add_argument("--simulate", action="store_true",
                        help="Simulate using census transfer function")
    parser.add_argument("--benchmarks", default="all",
                        help="Comma-separated: parity,nonlinear,capacity,all")
    parser.add_argument("--n-bits", type=int, default=7)
    parser.add_argument("--feature-mode", default="linear",
                        choices=["linear", "squared", "combined", "poly",
                                 "sequential", "seqpoly"],
                        help="Feature extraction: linear (FFT peaks), "
                             "squared (beat freqs from y^2), "
                             "combined (both), "
                             "poly (linear + carrier-bin polynomial expansion), "
                             "sequential (one carrier at a time, full power, "
                             "cross-coupling matrix — matches PicoScope protocol), "
                             "seqpoly (sequential + polynomial on diagonal "
                             "self-coupling — full PicoScope parity protocol)")
    args = parser.parse_args()

    if not args.hardware and not args.simulate:
        args.simulate = True  # default to simulation

    # Load census
    census = load_census(args.census)
    pid = args.plate
    rkey = f"{pid}_NE" if len(PLATE_RELAYS[pid]) > 1 else pid
    mode_freqs = get_plate_modes(census, pid, relay_key=rkey)
    n_modes = len(mode_freqs)

    if not mode_freqs:
        print(f"ERROR: No modes found for plate {pid}")
        sys.exit(1)

    # Carrier indices (evenly spaced)
    n_bits = min(args.n_bits, n_modes)
    carrier_indices = np.linspace(0, n_modes - 1, n_bits, dtype=int).tolist()

    # Census magnitudes for simulation
    results_dict = census.get("results", {})
    census_entry = results_dict.get(rkey, results_dict.get(pid, {}))
    peaks = census_entry.get("peaks", [])
    peaks_sorted = sorted(peaks, key=lambda p: p["freq_hz"])
    # Filter fixture
    lo_fix = FIXTURE_FREQ_HZ - FIXTURE_GUARD_HZ
    hi_fix = FIXTURE_FREQ_HZ + FIXTURE_GUARD_HZ
    peaks_sorted = [p for p in peaks_sorted
                    if not (lo_fix <= p["freq_hz"] <= hi_fix)]
    census_mags = np.array([p.get("magnitude", 0.1) for p in peaks_sorted])
    if len(census_mags) != n_modes:
        census_mags = np.ones(n_modes) * 0.1

    name = PLATE_NAMES.get(pid, pid)
    print(f"\n{'=' * 70}")
    print(f"  PLATE RESERVOIR BENCHMARK")
    print(f"  Plate {name} ({n_modes} modes), {n_bits} carrier bits")
    print(f"  Mode: {'HARDWARE' if args.hardware else 'SIMULATION'}")
    print(f"{'=' * 70}")

    # Set up capture function
    mux = None
    device_idx = None
    sample_rate = None

    if args.hardware:
        import sounddevice as sd
        from relay_mux import RelayMux

        if not args.port:
            print("ERROR: --port required for hardware mode")
            sys.exit(1)

        device_idx = find_audio_device(args.device)
        sample_rate = detect_sample_rate(device_idx)
        mux = RelayMux(port=args.port)
        mux.open()

        relay_ch = PLATE_RELAYS[pid][0][0]

        # Capture loopback reference before selecting plate relay
        lb_ref = capture_loopback_reference(
            sample_rate, device_idx, mux,
            mode_freqs, carrier_indices)

        mux.select(relay_ch)
        time.sleep(SETTLE_RELAY_S)

        if args.feature_mode in ("squared", "combined"):
            def capture_fn(mf, ci, pat, _cm):
                return hardware_capture_squared(
                    mf, ci, pat, sample_rate, device_idx,
                    loopback_ref=lb_ref)
        elif args.feature_mode in ("sequential", "seqpoly"):
            def capture_fn(mf, ci, pat, _cm):
                return hardware_capture_sequential(
                    mf, ci, pat, sample_rate, device_idx,
                    loopback_ref=lb_ref)
        else:
            def capture_fn(mf, ci, pat, _cm):
                return hardware_capture(
                    mf, ci, pat, sample_rate, device_idx,
                    loopback_ref=lb_ref)
    else:
        if args.feature_mode in ("squared", "combined"):
            def capture_fn(mf, ci, pat, cm):
                return simulated_capture_squared(mf, ci, pat, cm)
        elif args.feature_mode in ("sequential", "seqpoly"):
            def capture_fn(mf, ci, pat, cm):
                return simulated_capture_sequential(mf, ci, pat, cm)
        else:
            def capture_fn(mf, ci, pat, cm):
                return simulated_capture(mf, ci, pat, cm)

    # Run benchmarks
    benchmarks = args.benchmarks.split(",")
    if "all" in benchmarks:
        benchmarks = ["parity", "nonlinear", "capacity"]

    all_results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        if "parity" in benchmarks:
            print(f"\n  ── Benchmark: Parity (XOR generalization) ──")
            print(f"  Feature mode: {args.feature_mode}")
            r = benchmark_parity(mode_freqs, carrier_indices, census_mags,
                                 capture_fn,
                                 n_bits_list=[3, 4, 5, 6, 7],
                                 feature_mode=args.feature_mode)
            all_results.extend(r)

        if "nonlinear" in benchmarks:
            print(f"\n  ── Benchmark: Nonlinear function approximation ──")
            r = benchmark_nonlinear(mode_freqs, carrier_indices, census_mags,
                                    capture_fn)
            all_results.extend(r)

        if "capacity" in benchmarks:
            print(f"\n  ── Benchmark: Classification capacity ──")
            r = benchmark_capacity(mode_freqs, carrier_indices, census_mags,
                                   capture_fn)
            all_results.extend(r)

    finally:
        if mux:
            mux.off()
            mux.close()

    # ── Bittensor viability model ──
    print(f"\n{'=' * 70}")
    print(f"  BITTENSOR VIABILITY MODEL")
    print(f"{'=' * 70}")

    viability = bittensor_viability(all_results, n_modes)

    print(f"\n  Power: {viability['power_watts']}W "
          f"({viability['power_ratio_vs_gpu']}× less than GPU)")
    print(f"  Throughput: {viability['queries_per_second']:.1f} queries/sec "
          f"({viability['queries_per_day']:,} /day)")
    print(f"  Latency: {viability['avg_latency_ms']:.0f}ms per inference")
    print(f"  Best accuracy: {viability['best_accuracy_pct']:.1f}%")

    print(f"\n  {'Scenario':<14} {'Daily TAO':>10} {'Daily USD':>10} "
          f"{'Cost':>8} {'Profit':>10} {'Annual':>10}")
    print(f"  {'-' * 65}")
    for label, s in viability["scenarios"].items():
        tag = "OK" if s["profitable"] else "LOSS"
        print(f"  {label:<14} {s['daily_tao']:>10.4f} "
              f"${s['daily_usd']:>9.2f} "
              f"${s['daily_total_cost']:>7.2f} "
              f"${s['daily_profit']:>9.2f} "
              f"${s['annual_profit']:>9.0f} [{tag}]")

    print(f"\n  {viability['breakeven_note']}")

    # ── Save ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate_name": name,
        "plate_id": pid,
        "n_modes": n_modes,
        "n_carrier_bits": n_bits,
        "mode": "hardware" if args.hardware else "simulation",
        "benchmarks": all_results,
        "viability": viability,
    }

    save_path = RESULTS_DIR / f"benchmark_kronos_{name}_{timestamp}.json"
    with open(save_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved: {save_path.name}")


if __name__ == "__main__":
    main()
