#!/usr/bin/env python3
"""
Plate Echo State — Temporal Memory via Kronos (186-mode readout)

Port of plate_echo_state.py from PicoScope to Kronos USB audio.
Tests whether the plate's ringdown creates measurable temporal memory:

  1. Drive pattern₁ (multitone) for T_excite
  2. Switch instantly to pattern₂ (new multitone OR silence)
  3. After delay Δt, capture full spectral response
  4. The spectrum encodes BOTH current excitation AND residual echo
  5. Train readouts for three tasks:
     - "current":  classify pattern₂ (easy — no memory needed)
     - "previous": classify pattern₁ from residual echo (memory test)
     - "xor_seq":  classify XOR(pattern₁, pattern₂) (temporal computation)
  6. Sweep Δt to map the memory curve

Key upgrade from PicoScope version:
  - 186 readout dimensions (vs 8) → far richer echo signatures
  - 24-bit ADC → can detect weak echoes buried in noise floor
  - sd.playrec() → phase-coherent TX/RX in a single call
  - Dual-RX paths → test if echo signature depends on receiver position

Hardware: Kronos USB audio (192 kHz / 24-bit) + Arduino relay mux.
Requires a prior flash census JSON for mode frequencies.

Usage:
    # Single plate, default delays:
    python plate_echo_state_kronos.py /dev/cu.usbserial-11310 \\
        --device KRONOS --census <census_json>

    # All plates, custom delays:
    python plate_echo_state_kronos.py /dev/cu.usbserial-11310 \\
        --device KRONOS --census <census_json> --all-plates \\
        --delays 1,2,5,10,20,50,100,200

    # High-resolution sweep (more sequences, finer delays):
    python plate_echo_state_kronos.py /dev/cu.usbserial-11310 \\
        --device KRONOS --census <census_json> --n-seq 120 \\
        --delays 1,2,3,5,7,10,15,20,30,50,75,100,150,200,300
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
import sounddevice as sd

# ── Paths ──
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
DRIVE_AMPLITUDE = 0.8
SETTLE_RELAY_S = 0.10

# ── Echo experiment config ──
T_EXCITE_S = 0.20        # drive pattern₁ for this long
N_AVG = 4                # averages per capture
N_INPUT_BITS = 7          # use 7 carrier modes (128 unique patterns)
N_SEQUENCES = 80          # sequence pairs per delay
DEFAULT_DELAYS_MS = [1, 2, 5, 10, 20, 50, 100, 150, 200]
RIDGE_ALPHA = 1.0

# ── Fusion mode ──
# When --fusion is set, we capture from ALL relay paths for each trial
# and concatenate features into a single mega-vector.
# This requires repeating each TX waveform once per relay path.

# ── Fixture resonance exclusion ──
FIXTURE_FREQ_HZ = 6700.0
FIXTURE_GUARD_HZ = 200.0


# ══════════════════════════════════════════════════════════════════════
# Audio helpers
# ══════════════════════════════════════════════════════════════════════

def find_audio_device(name_hint: str) -> int:
    hint_lower = name_hint.lower()
    for i, dev in enumerate(sd.query_devices()):
        if (hint_lower in dev["name"].lower()
                and dev["max_input_channels"] > 0
                and dev["max_output_channels"] > 0):
            return i
    raise RuntimeError(f"No audio device matching '{name_hint}' with I/O.")


def detect_sample_rate(device_idx: int) -> int:
    for rate in PREFERRED_SAMPLE_RATES:
        try:
            sd.check_input_settings(device=device_idx, channels=1,
                                    dtype=AUDIO_DTYPE, samplerate=rate)
            sd.check_output_settings(device=device_idx, channels=1,
                                     dtype=AUDIO_DTYPE, samplerate=rate)
            return rate
        except sd.PortAudioError:
            continue
    dev = sd.query_devices(device_idx)
    return int(dev["default_samplerate"])


def playrec_capture(tx: np.ndarray, sr: int, dev: int) -> np.ndarray:
    """Simultaneous play+record. Returns mono RX (float64)."""
    rx = sd.playrec(
        tx, samplerate=sr,
        input_mapping=[1], output_mapping=[1],
        device=dev, dtype=AUDIO_DTYPE, blocking=True,
    )
    return rx[:, 0].astype(np.float64)


# ══════════════════════════════════════════════════════════════════════
# Census loading
# ══════════════════════════════════════════════════════════════════════

def load_census(census_path: str) -> dict:
    with open(census_path) as f:
        return json.load(f)


def get_plate_modes(census: dict, plate_id: str, relay_key: str | None = None,
                    exclude_fixture: bool = True) -> list[dict]:
    results = census.get("results", {})
    candidates = [relay_key, plate_id, f"{plate_id}_NE", f"{plate_id}_NW"]
    candidates = [c for c in candidates if c is not None]

    peaks = []
    for key in candidates:
        if key in results:
            peaks = results[key].get("peaks", [])
            if peaks:
                break

    if not peaks:
        raise RuntimeError(f"No modes for plate {plate_id}")

    peaks = sorted(peaks, key=lambda p: p["freq_hz"])

    if exclude_fixture:
        lo = FIXTURE_FREQ_HZ - FIXTURE_GUARD_HZ
        hi = FIXTURE_FREQ_HZ + FIXTURE_GUARD_HZ
        peaks = [p for p in peaks if not (lo <= p["freq_hz"] <= hi)]

    return peaks


# ══════════════════════════════════════════════════════════════════════
# Waveform building
# ══════════════════════════════════════════════════════════════════════

def build_echo_waveform(mode_freqs: list[float], carrier_indices: list[int],
                        pattern1: np.ndarray, pattern2: np.ndarray,
                        delay_s: float, sample_rate: int,
                        excite_s: float = T_EXCITE_S,
                        capture_s: float = 0.04) -> tuple[np.ndarray, int, int]:
    """Build a single TX waveform containing the full echo protocol.

    Layout:  [pattern₁ excite] [pattern₂ excite for delay_s] [silence capture window]

    The RX signal during the capture window contains:
      - pattern₂ steady-state (if delay is short, pattern₂ is still ringing)
      - pattern₁ echo (residual energy from the first drive)

    Returns: (tx_signal, capture_start_sample, capture_length_samples)
    """
    n_excite1 = int(sample_rate * excite_s)
    n_delay = int(sample_rate * delay_s)
    n_capture = int(sample_rate * capture_s)
    n_total = n_excite1 + n_delay + n_capture

    t_total = np.arange(n_total) / sample_rate
    sig = np.zeros(n_total, dtype=np.float64)

    rng = np.random.default_rng(9999)  # fixed phases

    # Phase 1: drive pattern₁ for excite period
    for b in range(len(carrier_indices)):
        if pattern1[b] > 0:
            freq = mode_freqs[carrier_indices[b]]
            phi = rng.uniform(0, 2 * np.pi)
            # Only active during excite window
            tone = np.sin(2 * np.pi * freq * t_total + phi)
            tone[n_excite1:] = 0  # silence after excite
            sig += tone

    # Phase 2: drive pattern₂ during delay period
    for b in range(len(carrier_indices)):
        if pattern2[b] > 0:
            freq = mode_freqs[carrier_indices[b]]
            phi = rng.uniform(0, 2 * np.pi)
            tone = np.sin(2 * np.pi * freq * t_total + phi)
            tone[:n_excite1] = 0      # silent during phase 1
            tone[n_excite1 + n_delay:] = 0  # silent during capture
            sig += tone

    # Normalize
    peak = np.max(np.abs(sig))
    if peak > 0:
        sig *= DRIVE_AMPLITUDE / peak

    tx = sig.astype(np.float32).reshape(-1, 1)
    capture_start = n_excite1 + n_delay
    return tx, capture_start, n_capture


# ══════════════════════════════════════════════════════════════════════
# Feature extraction
# ══════════════════════════════════════════════════════════════════════

def extract_spectrum(rx: np.ndarray, sample_rate: int,
                     readout_freqs: list[float],
                     capture_start: int, capture_len: int) -> np.ndarray:
    """Extract magnitude at readout frequencies from the capture window."""
    rx_capture = rx[capture_start:capture_start + capture_len]
    if len(rx_capture) < 64:
        return np.zeros(len(readout_freqs))

    windowed = rx_capture * np.hanning(len(rx_capture))
    nfft = len(rx_capture) * 4
    spectrum = np.fft.rfft(windowed, n=nfft)
    fft_mag = np.abs(spectrum)
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
    bin_hz = freq_axis[1] if len(freq_axis) > 1 else 1.0

    mags = np.zeros(len(readout_freqs))
    for j, f in enumerate(readout_freqs):
        tb = int(round(f / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(fft_mag) - 1, tb + 3)
        mags[j] = float(np.max(fft_mag[lo:hi + 1]))

    return mags


def _interaction_expand(x, max_degree=3):
    n = len(x)
    terms = list(x)
    for d in range(2, max_degree + 1):
        for combo in combinations(range(n), d):
            t = 1.0
            for idx in combo:
                t *= x[idx]
            terms.append(t)
    return np.array(terms)


# ══════════════════════════════════════════════════════════════════════
# Ridge classifier
# ══════════════════════════════════════════════════════════════════════

def ridge_binary(X_tr, X_te, y_tr, y_te, alpha=RIDGE_ALPHA):
    Xb_tr = np.column_stack([X_tr, np.ones(len(y_tr))])
    Xb_te = np.column_stack([X_te, np.ones(len(y_te))])
    d = Xb_tr.shape[1]
    Y_oh = np.zeros((len(y_tr), 2))
    for i, lbl in enumerate(y_tr):
        Y_oh[i, lbl] = 1.0
    W = np.linalg.solve(Xb_tr.T @ Xb_tr + alpha * np.eye(d), Xb_tr.T @ Y_oh)
    tr_acc = float(np.mean(np.argmax(Xb_tr @ W, axis=1) == y_tr))
    te_acc = float(np.mean(np.argmax(Xb_te @ W, axis=1) == y_te))
    return tr_acc, te_acc


# ══════════════════════════════════════════════════════════════════════
# Echo state protocol (per relay path)
# ══════════════════════════════════════════════════════════════════════

def run_echo_state(mux, census: dict, plate_id: str, relay_ch: int,
                   rx_label: str, sample_rate: int, device_idx: int,
                   delays_ms: list[int], n_input_bits: int = N_INPUT_BITS,
                   n_sequences: int = N_SEQUENCES, seed: int = 42) -> dict:
    """Run echo state experiment on one plate/relay path across delays."""

    name = PLATE_NAMES.get(plate_id, plate_id)
    rkey = f"{plate_id}_{rx_label}" if len(PLATE_RELAYS[plate_id]) > 1 else plate_id

    modes = get_plate_modes(census, plate_id, relay_key=rkey)
    n_modes = len(modes)
    mode_freqs = [p["freq_hz"] for p in modes]

    print(f"\n{'=' * 70}")
    print(f"  ECHO STATE — Plate {name}, RX-{rx_label} (relay {relay_ch})")
    print(f"  Modes: {n_modes}, Input bits: {n_input_bits}")
    print(f"  Delays: {delays_ms} ms")
    print(f"  Sequences/delay: {n_sequences}")
    print(f"{'=' * 70}")

    # Select carrier modes evenly spaced across spectrum
    n_input_bits = min(n_input_bits, n_modes)
    carrier_indices = np.linspace(0, n_modes - 1, n_input_bits, dtype=int).tolist()
    carrier_freqs = [mode_freqs[i] for i in carrier_indices]
    print(f"  Carriers ({n_input_bits}): "
          f"{[f'{f:.0f}' for f in carrier_freqs[:10]]}...")

    # All mode frequencies as readout dimensions
    readout_freqs = mode_freqs  # all 186 modes
    n_readout = len(readout_freqs)

    # Map carrier indices into readout space (they're the same array)
    carrier_readout_idx = carrier_indices

    # Select relay
    mux.select(relay_ch)
    time.sleep(SETTLE_RELAY_S)

    # Generate random (pattern₁, pattern₂) pairs
    rng = np.random.default_rng(seed)
    n_patterns = 2 ** n_input_bits
    all_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_input_bits)] for i in range(n_patterns)])

    seq_idx1 = rng.choice(n_patterns, n_sequences)
    seq_idx2 = rng.choice(n_patterns, n_sequences)
    patterns1 = all_patterns[seq_idx1]
    patterns2 = all_patterns[seq_idx2]

    # Labels
    parity1 = np.sum(patterns1, axis=1) % 2
    parity2 = np.sum(patterns2, axis=1) % 2
    xor_seq = (parity1 + parity2) % 2

    # Multi-class labels: which pattern was it (index into pattern space)
    label1 = seq_idx1  # 0..127
    label2 = seq_idx2

    # Train/test split
    n_train = int(0.75 * n_sequences)

    delay_results = []

    for delay_ms in delays_ms:
        delay_s = delay_ms / 1000.0
        print(f"\n  ── Delay: {delay_ms} ms ──")

        X_features = np.zeros((n_sequences, n_readout))
        t0 = time.time()

        for i in range(n_sequences):
            # Build the full TX waveform for this sequence
            tx, cap_start, cap_len = build_echo_waveform(
                mode_freqs, carrier_indices,
                patterns1[i], patterns2[i],
                delay_s, sample_rate)

            # Average multiple captures
            sum_mags = np.zeros(n_readout)
            for _ in range(N_AVG):
                rx = playrec_capture(tx, sample_rate, device_idx)
                mags = extract_spectrum(rx, sample_rate, readout_freqs,
                                        cap_start, cap_len)
                sum_mags += mags
            X_features[i] = sum_mags / N_AVG

            if (i + 1) % 20 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (n_sequences - i - 1) / rate
                print(f"    [{i+1}/{n_sequences}] {elapsed:.0f}s, "
                      f"~{eta:.0f}s remaining")

        capture_time = time.time() - t0
        print(f"    Captured {n_sequences} in {capture_time:.1f}s "
              f"({capture_time/n_sequences:.2f}s/seq)")

        # ── Feature normalization ──
        X_log = np.log1p(X_features)
        X_train = X_log[:n_train]
        X_test = X_log[n_train:]
        mu = X_train.mean(axis=0)
        sigma = X_train.std(axis=0) + 1e-8
        X_train_std = (X_train - mu) / sigma
        X_test_std = (X_test - mu) / sigma

        # Carrier-only features (for comparison with PicoScope-era results)
        X_train_carrier = X_train_std[:, carrier_readout_idx]
        X_test_carrier = X_test_std[:, carrier_readout_idx]

        # Labels
        y_tr_cur = parity2[:n_train]
        y_te_cur = parity2[n_train:]
        y_tr_prev = parity1[:n_train]
        y_te_prev = parity1[n_train:]
        y_tr_xor = xor_seq[:n_train]
        y_te_xor = xor_seq[n_train:]

        # ── Evaluate on multiple feature sets ──
        tasks = {}
        feature_sets = [
            ("carrier", X_train_carrier, X_test_carrier),
            ("full_spectrum", X_train_std, X_test_std),
        ]

        for fs_name, X_tr, X_te in feature_sets:
            for task_name, y_tr, y_te in [
                ("current", y_tr_cur, y_te_cur),
                ("previous", y_tr_prev, y_te_prev),
                ("xor_seq", y_tr_xor, y_te_xor),
            ]:
                key = f"{task_name}_{fs_name}"
                tr_acc, te_acc = ridge_binary(X_tr, X_te, y_tr, y_te)
                tasks[key] = {"train": round(tr_acc * 100, 1),
                              "test": round(te_acc * 100, 1)}

        # ── Echo strength measurement ──
        # For modes active in pattern₁ but NOT pattern₂,
        # is there energy above the noise floor?
        echo_signals = []
        noise_signals = []
        for i in range(n_sequences):
            for b in range(n_input_bits):
                ridx = carrier_readout_idx[b]
                if patterns1[i, b] > 0 and patterns2[i, b] == 0:
                    echo_signals.append(X_log[i, ridx])
                elif patterns1[i, b] == 0 and patterns2[i, b] == 0:
                    noise_signals.append(X_log[i, ridx])

        echo_mean = float(np.mean(echo_signals)) if echo_signals else 0
        noise_mean = float(np.mean(noise_signals)) if noise_signals else 0
        echo_std = float(np.std(echo_signals)) if echo_signals else 1
        noise_std = float(np.std(noise_signals)) if noise_signals else 1
        echo_snr = (echo_mean - noise_mean) / (echo_std + noise_std + 1e-8)

        # ── Non-carrier echo modes ──
        # With 186 modes, many are NOT being driven.  Energy at these
        # frequencies is purely mode-coupling or nonlinear transfer.
        non_carrier_idx = [j for j in range(n_readout)
                           if j not in carrier_readout_idx]
        if non_carrier_idx:
            nc_active = []
            nc_silent = []
            for i in range(n_sequences):
                if np.sum(patterns1[i]) > 0:
                    nc_active.append(np.mean(X_log[i, non_carrier_idx]))
                else:
                    nc_silent.append(np.mean(X_log[i, non_carrier_idx]))
            nc_coupling = (np.mean(nc_active) - np.mean(nc_silent)) if nc_silent else 0
        else:
            nc_coupling = 0

        # ── Print results ──
        print(f"    Echo SNR: {echo_snr:.2f} "
              f"(echo={echo_mean:.2f}±{echo_std:.2f}, "
              f"noise={noise_mean:.2f}±{noise_std:.2f})")
        print(f"    Non-carrier coupling: {nc_coupling:.3f}")
        print(f"    {'Task':<30} {'Train':>7} {'Test':>7}")
        print(f"    {'-' * 46}")
        for tname, info in sorted(tasks.items()):
            marker = " ✓" if info["test"] > 60 else ""
            print(f"    {tname:<30} {info['train']:>6.1f}% "
                  f"{info['test']:>6.1f}%{marker}")

        delay_results.append({
            "delay_ms": delay_ms,
            "tasks": tasks,
            "echo_snr": round(echo_snr, 4),
            "echo_mean": round(echo_mean, 3),
            "noise_mean": round(noise_mean, 3),
            "non_carrier_coupling": round(nc_coupling, 4),
            "capture_time_s": round(capture_time, 1),
            "n_readout_dims": n_readout,
        })

    # ── Summary: Memory Curve ──
    mux.off()

    print(f"\n  ── MEMORY CURVE: Plate {name} RX-{rx_label} ──")
    print(f"  {'Δt(ms)':<8} {'SNR':>6} "
          f"{'cur_c':>7} {'cur_f':>7} "
          f"{'prev_c':>7} {'prev_f':>7} "
          f"{'xor_c':>7} {'xor_f':>7}")
    print(f"  {'-' * 60}")
    for dr in delay_results:
        dt = dr["delay_ms"]
        snr = dr["echo_snr"]
        t = dr["tasks"]
        print(f"  {dt:<8} {snr:>6.2f} "
              f"{t['current_carrier']['test']:>6.1f}% "
              f"{t['current_full_spectrum']['test']:>6.1f}% "
              f"{t['previous_carrier']['test']:>6.1f}% "
              f"{t['previous_full_spectrum']['test']:>6.1f}% "
              f"{t['xor_seq_carrier']['test']:>6.1f}% "
              f"{t['xor_seq_full_spectrum']['test']:>6.1f}%")

    # Key metrics
    def best_test(task_prefix):
        return max(
            dr["tasks"].get(f"{task_prefix}_full_spectrum", {"test": 0})["test"]
            for dr in delay_results)

    best_prev = best_test("previous")
    best_xor = best_test("xor_seq")
    best_cur = best_test("current")

    # Memory horizon: last delay where previous_full > 60%
    memory_horizon_ms = 0
    for dr in delay_results:
        if dr["tasks"]["previous_full_spectrum"]["test"] > 60:
            memory_horizon_ms = dr["delay_ms"]

    # Carrier-only memory horizon (for PicoScope-era comparison)
    memory_horizon_carrier_ms = 0
    for dr in delay_results:
        if dr["tasks"]["previous_carrier"]["test"] > 60:
            memory_horizon_carrier_ms = dr["delay_ms"]

    has_memory = best_prev > 60
    has_computation = best_xor > 60

    print(f"\n  Memory horizon (full spectrum): {memory_horizon_ms} ms")
    print(f"  Memory horizon (carrier only):  {memory_horizon_carrier_ms} ms")
    print(f"  Best previous: {best_prev:.1f}% "
          f"({'MEMORY' if has_memory else 'no memory'})")
    print(f"  Best xor_seq:  {best_xor:.1f}% "
          f"({'TEMPORAL COMPUTE' if has_computation else 'no temporal compute'})")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate_name": name,
        "plate_id": plate_id,
        "rx_label": rx_label,
        "relay_ch": relay_ch,
        "n_modes": n_modes,
        "n_input_bits": n_input_bits,
        "n_sequences": n_sequences,
        "n_readout_dims": n_readout,
        "t_excite_ms": T_EXCITE_S * 1000,
        "n_avg": N_AVG,
        "delays_ms": delays_ms,
        "delay_results": delay_results,
        "memory_horizon_ms": memory_horizon_ms,
        "memory_horizon_carrier_ms": memory_horizon_carrier_ms,
        "best_current_pct": best_cur,
        "best_previous_pct": best_prev,
        "best_xor_seq_pct": best_xor,
        "has_memory": has_memory,
        "has_temporal_compute": has_computation,
        "carrier_indices": carrier_indices,
        "carrier_freqs_hz": carrier_freqs,
        "mode_freqs_hz": mode_freqs,
    }


# ══════════════════════════════════════════════════════════════════════
# Multi-plate fusion: concatenate ALL RX paths into one mega-vector
# ══════════════════════════════════════════════════════════════════════

def run_echo_state_fusion(mux, census: dict, sample_rate: int,
                          device_idx: int, plate_ids: list[str],
                          delays_ms: list[int],
                          n_input_bits: int = N_INPUT_BITS,
                          n_sequences: int = N_SEQUENCES,
                          seed: int = 42) -> dict:
    """Run echo state with fused features from ALL relay paths.

    For each (pattern₁, pattern₂, delay) trial we replay the SAME TX
    waveform through each relay path in sequence, capturing the RX
    spectrum each time.  Features are concatenated into a single vector:

        x = [plate1_NE_mags | plate2_NE_mags | plate3_NE_mags | ...]

    This gives a 1,400+ dimensional readout from physically independent
    resonators, each contributing unique nonlinear dynamics.
    """

    # Collect all relay paths and their mode lists
    relay_paths = []  # (plate_id, relay_ch, rx_label, mode_freqs)
    for pid in plate_ids:
        for relay_ch, rx_label in PLATE_RELAYS[pid]:
            rkey = (f"{pid}_{rx_label}"
                    if len(PLATE_RELAYS[pid]) > 1 else pid)
            try:
                modes = get_plate_modes(census, pid, relay_key=rkey)
                mode_freqs = [p["freq_hz"] for p in modes]
                relay_paths.append((pid, relay_ch, rx_label, mode_freqs))
            except RuntimeError as e:
                print(f"  SKIP {pid}_{rx_label}: {e}")

    n_paths = len(relay_paths)
    dims_per_path = [len(rp[3]) for rp in relay_paths]
    total_dims = sum(dims_per_path)

    print(f"\n{'=' * 75}")
    print(f"  FUSION ECHO STATE — {n_paths} RX paths, "
          f"{total_dims} total readout dims")
    print(f"  Input bits: {n_input_bits}, Sequences: {n_sequences}")
    print(f"  Delays: {delays_ms} ms")
    print(f"{'=' * 75}")
    for pid, rch, rxl, mf in relay_paths:
        name = PLATE_NAMES.get(pid, pid)
        print(f"    Plate {name} RX-{rxl} (relay {rch}): {len(mf)} modes")
    print()

    # Use plate with most modes for carrier selection (TX goes to all)
    # TX drives through whichever relay is active — carrier selection
    # uses modes from the first plate, but the key insight is that ALL
    # plates receive the same acoustic signal through the shared fixture.
    # With separate plates we need to pick carrier freqs that exist on
    # the TX-active plate.  For fusion, we use plate 5 (H) as the
    # reference since it has the most modes.
    ref_idx = max(range(n_paths), key=lambda i: dims_per_path[i])
    ref_mf = relay_paths[ref_idx][3]
    n_input_bits = min(n_input_bits, len(ref_mf))
    carrier_indices = np.linspace(0, len(ref_mf) - 1,
                                  n_input_bits, dtype=int).tolist()
    carrier_freqs = [ref_mf[i] for i in carrier_indices]
    print(f"  Reference plate for TX: {PLATE_NAMES.get(relay_paths[ref_idx][0], '?')}")
    print(f"  Carriers ({n_input_bits}): "
          f"{[f'{f:.0f}' for f in carrier_freqs[:10]]}...")

    # Generate deterministic (pattern₁, pattern₂) sequences
    rng = np.random.default_rng(seed)
    n_patterns = 2 ** n_input_bits
    all_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_input_bits)]
         for i in range(n_patterns)])
    seq_idx1 = rng.choice(n_patterns, n_sequences)
    seq_idx2 = rng.choice(n_patterns, n_sequences)
    patterns1 = all_patterns[seq_idx1]
    patterns2 = all_patterns[seq_idx2]

    # Labels
    parity1 = np.sum(patterns1, axis=1) % 2
    parity2 = np.sum(patterns2, axis=1) % 2
    xor_seq = (parity1 + parity2) % 2

    n_train = int(0.75 * n_sequences)

    delay_results = []

    for delay_ms in delays_ms:
        delay_s = delay_ms / 1000.0
        print(f"\n  ── Delay: {delay_ms} ms ──")

        X_fused = np.zeros((n_sequences, total_dims))
        t0 = time.time()

        for i in range(n_sequences):
            # Build the TX waveform (same for all paths)
            tx, cap_start, cap_len = build_echo_waveform(
                ref_mf, carrier_indices,
                patterns1[i], patterns2[i],
                delay_s, sample_rate)

            # Capture from every relay path with the same TX
            col_offset = 0
            for path_idx, (pid, rch, rxl, mf) in enumerate(relay_paths):
                mux.select(rch)
                time.sleep(SETTLE_RELAY_S)

                sum_mags = np.zeros(len(mf))
                for _ in range(N_AVG):
                    rx = playrec_capture(tx, sample_rate, device_idx)
                    mags = extract_spectrum(rx, sample_rate, mf,
                                            cap_start, cap_len)
                    sum_mags += mags
                X_fused[i, col_offset:col_offset + len(mf)] = sum_mags / N_AVG
                col_offset += len(mf)

            if (i + 1) % 10 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (n_sequences - i - 1) / rate
                print(f"    [{i+1}/{n_sequences}] {elapsed:.0f}s, "
                      f"~{eta:.0f}s remaining")

        capture_time = time.time() - t0
        time_per_seq = capture_time / max(n_sequences, 1)
        print(f"    Captured {n_sequences}×{n_paths} paths in "
              f"{capture_time:.1f}s ({time_per_seq:.2f}s/seq)")

        # ── Feature prep ──
        X_log = np.log1p(X_fused)
        X_train = X_log[:n_train]
        X_test = X_log[n_train:]
        mu = X_train.mean(axis=0)
        sigma = X_train.std(axis=0) + 1e-8
        X_train_std = (X_train - mu) / sigma
        X_test_std = (X_test - mu) / sigma

        # Also build per-plate subsets for ablation
        per_plate_features = {}
        col = 0
        for path_idx, (pid, rch, rxl, mf) in enumerate(relay_paths):
            key = f"{PLATE_NAMES.get(pid, pid)}_{rxl}"
            per_plate_features[key] = (col, col + len(mf))
            col += len(mf)

        # Labels
        y_tr_cur = parity2[:n_train]
        y_te_cur = parity2[n_train:]
        y_tr_prev = parity1[:n_train]
        y_te_prev = parity1[n_train:]
        y_tr_xor = xor_seq[:n_train]
        y_te_xor = xor_seq[n_train:]

        # ── Evaluate: fused, and per-plate ablation ──
        tasks = {}
        feature_sets = [("fused", X_train_std, X_test_std)]

        # Per-plate subsets
        for key, (c0, c1) in per_plate_features.items():
            feature_sets.append(
                (key, X_train_std[:, c0:c1], X_test_std[:, c0:c1]))

        for fs_name, X_tr, X_te in feature_sets:
            for task_name, y_tr, y_te in [
                ("current", y_tr_cur, y_te_cur),
                ("previous", y_tr_prev, y_te_prev),
                ("xor_seq", y_tr_xor, y_te_xor),
            ]:
                tkey = f"{task_name}_{fs_name}"
                tr_acc, te_acc = ridge_binary(X_tr, X_te, y_tr, y_te)
                tasks[tkey] = {"train": round(tr_acc * 100, 1),
                               "test": round(te_acc * 100, 1)}

        # ── Print ──
        print(f"\n    {'Task':<40} {'Train':>7} {'Test':>7}")
        print(f"    {'-' * 56}")
        for tname in sorted(tasks.keys()):
            info = tasks[tname]
            marker = " ***" if ("fused" in tname and info["test"] > 60) else \
                     " ✓" if info["test"] > 60 else ""
            print(f"    {tname:<40} {info['train']:>6.1f}% "
                  f"{info['test']:>6.1f}%{marker}")

        # Fusion uplift: compare fused vs best single-plate
        for task_prefix in ["current", "previous", "xor_seq"]:
            fused_te = tasks[f"{task_prefix}_fused"]["test"]
            single_tes = [
                tasks[f"{task_prefix}_{k}"]["test"]
                for k in per_plate_features]
            best_single = max(single_tes) if single_tes else 0
            uplift = fused_te - best_single
            tag = f"    ↑ {task_prefix} fusion uplift:"
            print(f"{tag:<42} {uplift:>+.1f}%")

        delay_results.append({
            "delay_ms": delay_ms,
            "tasks": tasks,
            "capture_time_s": round(capture_time, 1),
            "total_dims": total_dims,
            "per_plate_dims": {k: c1 - c0
                               for k, (c0, c1) in per_plate_features.items()},
        })

    # ── Summary ──
    mux.off()

    print(f"\n{'=' * 75}")
    print(f"  FUSION MEMORY CURVE ({n_paths} paths, {total_dims} dims)")
    print(f"{'=' * 75}")
    print(f"  {'Δt(ms)':<8} {'cur_fused':>10} {'prev_fused':>11} "
          f"{'xor_fused':>10} {'prev_best1':>11}")
    print(f"  {'-' * 55}")
    for dr in delay_results:
        dt = dr["delay_ms"]
        t = dr["tasks"]
        cur_f = t["current_fused"]["test"]
        prev_f = t["previous_fused"]["test"]
        xor_f = t["xor_seq_fused"]["test"]
        # best single-plate previous
        prev_singles = [t[k]["test"] for k in t
                        if k.startswith("previous_") and "fused" not in k]
        best1 = max(prev_singles) if prev_singles else 0
        print(f"  {dt:<8} {cur_f:>9.1f}% {prev_f:>10.1f}% "
              f"{xor_f:>9.1f}% {best1:>10.1f}%")

    # Key metrics
    best_prev_fused = max(
        dr["tasks"]["previous_fused"]["test"] for dr in delay_results)
    best_xor_fused = max(
        dr["tasks"]["xor_seq_fused"]["test"] for dr in delay_results)

    horizon_fused_ms = 0
    for dr in delay_results:
        if dr["tasks"]["previous_fused"]["test"] > 60:
            horizon_fused_ms = dr["delay_ms"]

    print(f"\n  Memory horizon (fused):  {horizon_fused_ms} ms")
    print(f"  Best previous (fused):   {best_prev_fused:.1f}%")
    print(f"  Best xor_seq (fused):    {best_xor_fused:.1f}%")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "fusion",
        "n_relay_paths": n_paths,
        "total_dims": total_dims,
        "n_input_bits": n_input_bits,
        "n_sequences": n_sequences,
        "n_avg": N_AVG,
        "delays_ms": delays_ms,
        "relay_paths": [
            {"plate_id": pid, "plate_name": PLATE_NAMES.get(pid, pid),
             "relay_ch": rch, "rx_label": rxl, "n_modes": len(mf)}
            for pid, rch, rxl, mf in relay_paths
        ],
        "delay_results": delay_results,
        "memory_horizon_fused_ms": horizon_fused_ms,
        "best_previous_fused_pct": best_prev_fused,
        "best_xor_fused_pct": best_xor_fused,
        "has_memory": best_prev_fused > 60,
        "has_temporal_compute": best_xor_fused > 60,
        "carrier_freqs_hz": carrier_freqs,
    }


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    from relay_mux import RelayMux

    parser = argparse.ArgumentParser(
        description="Plate echo state — temporal memory via Kronos")
    parser.add_argument("port", help="Arduino serial port")
    parser.add_argument("--device", default="KRONOS")
    parser.add_argument("--census", required=True, help="Census JSON path")
    parser.add_argument("--plate", default="5", help="Plate ID (1-5)")
    parser.add_argument("--all-plates", action="store_true")
    parser.add_argument("--delays", default=None,
                        help="Comma-separated delays in ms")
    parser.add_argument("--n-seq", type=int, default=N_SEQUENCES)
    parser.add_argument("--n-bits", type=int, default=N_INPUT_BITS)
    parser.add_argument("--fusion", action="store_true",
                        help="Fuse ALL relay paths into one mega-vector "
                             "(1400+ dims). Overrides --plate/--all-plates.")
    args = parser.parse_args()

    delays_ms = DEFAULT_DELAYS_MS
    if args.delays:
        delays_ms = [int(x.strip()) for x in args.delays.split(",")]

    # Audio setup
    device_idx = find_audio_device(args.device)
    dev_info = sd.query_devices(device_idx)
    sample_rate = detect_sample_rate(device_idx)

    print(f"\n  Device: {dev_info['name']} @ {sample_rate} Hz")

    # Census
    census = load_census(args.census)

    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux on {mux.port}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Fusion mode: all plates, all RX paths → one mega-vector ──
    if args.fusion:
        plate_ids = sorted(PLATE_RELAYS.keys())
        try:
            result = run_echo_state_fusion(
                mux, census, sample_rate, device_idx,
                plate_ids=plate_ids,
                delays_ms=delays_ms,
                n_input_bits=args.n_bits,
                n_sequences=args.n_seq)

            save_path = RESULTS_DIR / \
                f"echo_state_kronos_fusion_{timestamp}.json"
            with open(save_path, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"\n  Saved: {save_path.name}")
        finally:
            mux.off()
            mux.close()
        return

    # ── Standard mode: per-plate ──
    plate_ids = sorted(PLATE_RELAYS.keys()) if args.all_plates else [args.plate]
    all_results = []

    try:
        for pid in plate_ids:
            relays = PLATE_RELAYS[pid]
            for relay_ch, rx_label in relays:
                result = run_echo_state(
                    mux, census, pid, relay_ch, rx_label,
                    sample_rate, device_idx,
                    delays_ms=delays_ms,
                    n_input_bits=args.n_bits,
                    n_sequences=args.n_seq)
                all_results.append(result)

                # Save per-path result
                name = result["plate_name"]
                save_path = RESULTS_DIR / \
                    f"echo_state_kronos_{name}_{rx_label}_{timestamp}.json"
                with open(save_path, "w") as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"\n  Saved: {save_path.name}")
    finally:
        mux.off()
        mux.close()

    # ── Combined summary ──
    if len(all_results) > 1:
        print(f"\n{'=' * 75}")
        print(f"  SUMMARY — ECHO STATE (KRONOS)")
        print(f"{'=' * 75}")
        print(f"  {'Plate':<6} {'RX':<4} {'Modes':>5} {'Horizon':>10} "
              f"{'Prev':>8} {'XOR':>8} {'Memory':>8}")
        print(f"  {'-' * 60}")
        for r in all_results:
            print(f"  {r['plate_name']:<6} {r['rx_label']:<4} "
                  f"{r['n_modes']:>5} {r['memory_horizon_ms']:>8} ms "
                  f"{r['best_previous_pct']:>7.1f}% "
                  f"{r['best_xor_seq_pct']:>7.1f}% "
                  f"{'YES' if r['has_memory'] else 'NO':>8}")

        combined_path = RESULTS_DIR / f"echo_state_kronos_all_{timestamp}.json"
        with open(combined_path, "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"  Combined: {combined_path.name}")


if __name__ == "__main__":
    main()
