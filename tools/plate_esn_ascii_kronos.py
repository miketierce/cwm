#!/usr/bin/env python3
"""
Full-ASCII Reservoir Computing via Kronos + Fused Silica Plates (ESN v5)

Exploits the 186-mode Kronos census to encode and classify all 128 ASCII
characters using the plate eigenmode spectrum as a nonlinear reservoir.

Three encoding strategies (tested head-to-head):
  1. Single-tone:  char c → excite mode c  (needs ≥128 modes)
  2. Binary:       char c → 7-bit binary mask over 7 carrier modes
  3. Sparse K-hot: char c → unique K-of-N mode subset (combinatorial)

Each encoding drives a multitone TX waveform through the Kronos, captures the
full spectral response as a feature vector (186-dim magnitude), and trains a
linear readout (ridge regression) to classify 128 ASCII characters.

The primary task is direct classification (no sequence memory needed — we
want to establish that the plate can separate 128 classes first).  A secondary
sequence-reversal task tests temporal memory with the full alphabet.

Hardware: Kronos USB audio (24-bit, 192 kHz) + Arduino relay mux.
Requires a prior flash census JSON for mode frequencies.

Usage:
    # Calibrate all 128 chars × 8 reps on plate 5 (NE path):
    python plate_esn_ascii_kronos.py calibrate /dev/cu.usbserial-11310 \\
        --device KRONOS --census <census_json>

    # Run ESN experiment from saved calibration:
    python plate_esn_ascii_kronos.py experiment --calibration <calib_json>

    # Full pipeline (calibrate + experiment):
    python plate_esn_ascii_kronos.py full /dev/cu.usbserial-11310 \\
        --device KRONOS --census <census_json>
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

# ── ASCII experiment config ──
N_ASCII = 128            # full ASCII alphabet
N_CALIB_REPS = 8         # captures per char per RX path
CALIB_DURATION_S = 0.5   # TX+RX duration per capture (includes settle)
CALIB_SETTLE_S = 0.1     # initial settle before analysis window
CHECKPOINT_EVERY = 16    # save checkpoint every N characters

# ── Encoding: binary mode ──
N_BINARY_CARRIERS = 7    # 7 bits → 128 chars

# ── Encoding: sparse K-hot ──
SPARSE_K = 4             # excite 4 of N modes → C(N,4) >> 128

# ── ESN config ──
ESN_HIDDEN = 200
ESN_SPECTRAL = 0.9
ESN_INPUT_SCALE = 0.1
ESN_LEAK = 0.9
RIDGE_ALPHA = 10.0

# ── Sequence task config ──
SEQ_LENGTH = 4
N_SEQUENCES = 3000

# ── Fixture resonance exclusion ──
FIXTURE_FREQ_HZ = 6700.0
FIXTURE_GUARD_HZ = 200.0  # exclude 6500–6900 Hz


# ══════════════════════════════════════════════════════════════════════
# Audio helpers (same as plate_census_kronos.py / plate_multitone_kronos.py)
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
    """Load full census JSON, return raw dict."""
    with open(census_path) as f:
        return json.load(f)


def get_plate_modes(census: dict, plate_id: str, relay_key: str | None = None,
                    exclude_fixture: bool = True) -> list[dict]:
    """Extract sorted mode list for a plate/relay path from census."""
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
        available = list(results.keys())
        raise RuntimeError(
            f"No modes for plate {plate_id}. Available: {available}")

    # Sort by frequency
    peaks = sorted(peaks, key=lambda p: p["freq_hz"])

    # Exclude fixture resonance (~6700 Hz)
    if exclude_fixture:
        lo = FIXTURE_FREQ_HZ - FIXTURE_GUARD_HZ
        hi = FIXTURE_FREQ_HZ + FIXTURE_GUARD_HZ
        peaks = [p for p in peaks if not (lo <= p["freq_hz"] <= hi)]

    return peaks


def get_all_relay_modes(census: dict, plate_ids: list[str],
                        exclude_fixture: bool = True) -> dict:
    """Get modes for all relay paths across target plates.

    Returns: {relay_key: [peak_dicts]} where relay_key = "pid_rxlabel"
    """
    all_modes = {}
    for pid in plate_ids:
        relays = PLATE_RELAYS[pid]
        for relay_ch, rx_label in relays:
            rkey = f"{pid}_{rx_label}" if len(relays) > 1 else pid
            try:
                modes = get_plate_modes(census, pid, relay_key=rkey,
                                        exclude_fixture=exclude_fixture)
                all_modes[rkey] = modes
                pname = PLATE_NAMES.get(pid, pid)
                print(f"  Plate {pname} RX-{rx_label}: "
                      f"{len(modes)} modes (relay {relay_ch})")
            except RuntimeError as e:
                print(f"  WARNING: {e}")
    return all_modes


# ══════════════════════════════════════════════════════════════════════
# Encoding strategies
# ══════════════════════════════════════════════════════════════════════

def build_encoding_singletone(n_modes: int) -> dict:
    """Single-tone encoding: char c excites mode c (offset to skip weak modes).

    Maps ASCII 0–127 → modes[offset..offset+127].
    Offset skips lowest-frequency modes (often weakest / most coupled).
    """
    if n_modes < N_ASCII:
        raise ValueError(f"Need ≥{N_ASCII} modes for single-tone, have {n_modes}")

    # Skip the first few weak modes; center the alphabet in the mode range
    offset = min(10, (n_modes - N_ASCII) // 2)
    mapping = {}
    for c in range(N_ASCII):
        mapping[c] = [offset + c]  # list of mode indices to excite

    return {"name": "singletone", "mapping": mapping, "offset": offset,
            "n_active": 1, "description": f"1-of-{n_modes} (offset={offset})"}


def build_encoding_binary(n_modes: int) -> dict:
    """7-bit binary encoding: char c → bit mask over 7 carrier modes.

    Selects 7 well-separated modes as carriers. Each ASCII char's 7-bit
    representation activates the corresponding carriers.
    Char 0 (NUL) has all bits off → silence → captured as noise baseline.
    """
    if n_modes < N_BINARY_CARRIERS:
        raise ValueError(f"Need ≥{N_BINARY_CARRIERS} modes, have {n_modes}")

    # Pick 7 carriers evenly spaced across the mode spectrum
    indices = np.linspace(5, n_modes - 5, N_BINARY_CARRIERS, dtype=int)
    carrier_indices = indices.tolist()

    mapping = {}
    for c in range(N_ASCII):
        active = []
        for bit in range(N_BINARY_CARRIERS):
            if (c >> bit) & 1:
                active.append(carrier_indices[bit])
        mapping[c] = active

    return {"name": "binary", "mapping": mapping,
            "carrier_indices": carrier_indices,
            "n_carriers": N_BINARY_CARRIERS,
            "description": f"7-bit over modes {carrier_indices}"}


def build_encoding_sparse(n_modes: int, k: int = SPARSE_K) -> dict:
    """Sparse K-hot encoding: char c → unique K-of-N mode subset.

    C(N, K) >> 128 for reasonable N and K=4.  Assigns subsets by ranking
    modes by magnitude (strongest first) and using combinatorial indexing.
    """
    if math.comb(n_modes, k) < N_ASCII:
        raise ValueError(
            f"C({n_modes},{k})={math.comb(n_modes, k)} < {N_ASCII}")

    # Generate all C(n,k) subsets, take first 128
    all_subsets = list(combinations(range(n_modes), k))
    # Shuffle with fixed seed to spread across mode space
    rng = np.random.default_rng(42)
    subset_indices = rng.permutation(len(all_subsets))[:N_ASCII]

    mapping = {}
    for c in range(N_ASCII):
        mapping[c] = list(all_subsets[subset_indices[c]])

    return {"name": f"sparse_k{k}", "mapping": mapping, "k": k,
            "description": f"{k}-of-{n_modes} (C={math.comb(n_modes, k)})"}


# ══════════════════════════════════════════════════════════════════════
# Waveform generation
# ══════════════════════════════════════════════════════════════════════

def make_drive_waveform(mode_freqs: list[float], active_indices: list[int],
                        duration_s: float, sample_rate: int) -> np.ndarray:
    """Build a multitone TX waveform exciting only the specified mode indices.

    Returns float32 column vector for sd.playrec().
    If active_indices is empty, returns silence (captures noise baseline).
    """
    n_samples = int(sample_rate * duration_s)
    t = np.arange(n_samples) / sample_rate

    if not active_indices:
        # Silence — captures the noise baseline
        return np.zeros((n_samples, 1), dtype=np.float32)

    sig = np.zeros(n_samples, dtype=np.float64)
    rng = np.random.default_rng(12345)  # fixed phases for reproducibility
    for idx in active_indices:
        freq = mode_freqs[idx]
        phi = rng.uniform(0, 2 * np.pi)
        sig += np.sin(2 * np.pi * freq * t + phi)

    peak = np.max(np.abs(sig))
    if peak > 0:
        sig *= DRIVE_AMPLITUDE / peak

    return sig.astype(np.float32).reshape(-1, 1)


# ══════════════════════════════════════════════════════════════════════
# Feature extraction
# ══════════════════════════════════════════════════════════════════════

def extract_features(rx: np.ndarray, sample_rate: int,
                     readout_freqs: list[float],
                     settle_samples: int) -> np.ndarray:
    """Extract magnitude vector at readout frequencies from RX signal.

    Returns: 1-D array of length len(readout_freqs).
    """
    # Discard settle, analyze capture window
    rx_capture = rx[settle_samples:]
    if len(rx_capture) < 64:
        return np.zeros(len(readout_freqs))

    # Window + FFT (4× zero-pad for smooth interpolation)
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


# ══════════════════════════════════════════════════════════════════════
# Calibration: drive every ASCII char, capture spectral response
# ══════════════════════════════════════════════════════════════════════

def calibrate(args):
    """Drive all 128 ASCII characters through each encoding, capture features."""
    from relay_mux import RelayMux

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Audio setup
    device_idx = find_audio_device(args.device)
    dev_info = sd.query_devices(device_idx)
    sample_rate = detect_sample_rate(device_idx)

    # Census
    census = load_census(args.census)
    plate_ids = args.plates.split(",") if args.plates else ["5"]

    all_relay_modes = get_all_relay_modes(census, plate_ids)
    if not all_relay_modes:
        print("ERROR: No modes found for any target plate.")
        sys.exit(1)

    # Use first relay path as primary (for mode count / encoding design)
    primary_key = list(all_relay_modes.keys())[0]
    primary_modes = all_relay_modes[primary_key]
    n_modes = len(primary_modes)
    mode_freqs = [p["freq_hz"] for p in primary_modes]

    # All readout frequencies = union of all modes across all relay paths
    all_readout_freqs = sorted(set(
        p["freq_hz"]
        for modes in all_relay_modes.values()
        for p in modes
    ))

    print(f"\n{'=' * 70}")
    print(f"  ASCII RESERVOIR CALIBRATION (v5)")
    print(f"  Device: {dev_info['name']} @ {sample_rate} Hz")
    print(f"  Primary path: {primary_key} ({n_modes} modes)")
    print(f"  Readout frequencies: {len(all_readout_freqs)}")
    print(f"  Characters: {N_ASCII} (full ASCII)")
    print(f"  Reps per char: {N_CALIB_REPS}")
    print(f"  Capture: {CALIB_DURATION_S}s ({CALIB_SETTLE_S}s settle)")
    print(f"{'=' * 70}")

    # Build all three encodings
    encodings = {}
    try:
        encodings["singletone"] = build_encoding_singletone(n_modes)
        print(f"  Singletone: {encodings['singletone']['description']}")
    except ValueError as e:
        print(f"  Singletone: SKIPPED ({e})")

    encodings["binary"] = build_encoding_binary(n_modes)
    print(f"  Binary: {encodings['binary']['description']}")

    try:
        encodings["sparse"] = build_encoding_sparse(n_modes)
        print(f"  Sparse: {encodings['sparse']['description']}")
    except ValueError as e:
        print(f"  Sparse: SKIPPED ({e})")

    # Open hardware
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"\n  Relay mux on {mux.port}")

    settle_samples = int(sample_rate * CALIB_SETTLE_S)
    n_relay_paths = len(all_relay_modes)
    total_captures = 0
    t0 = time.time()

    # Data structure: {encoding_name: {relay_key: {char_int: {"reps": [...], "mean": [...]}}}}
    calib_data = {enc_name: {rkey: {} for rkey in all_relay_modes}
                  for enc_name in encodings}

    # For efficiency, all encodings share the same readout → capture once,
    # extract features per-encoding.  But different encodings drive different
    # tones, so we must capture separately per encoding.

    for enc_name, enc in encodings.items():
        print(f"\n{'─' * 70}")
        print(f"  ENCODING: {enc_name} — {enc['description']}")
        print(f"{'─' * 70}")

        t0_enc = time.time()

        for char_idx in range(N_ASCII):
            active_indices = enc["mapping"][char_idx]
            char_label = repr(chr(char_idx)) if 32 <= char_idx < 127 else f"0x{char_idx:02X}"

            # Build TX waveform
            tx = make_drive_waveform(
                mode_freqs, active_indices,
                CALIB_DURATION_S, sample_rate)

            # Capture from each RX path
            for rkey, rmodes in all_relay_modes.items():
                relay_ch = None
                for pid in plate_ids:
                    for ch, rx_label in PLATE_RELAYS[pid]:
                        expected_key = (f"{pid}_{rx_label}"
                                        if len(PLATE_RELAYS[pid]) > 1 else pid)
                        if expected_key == rkey:
                            relay_ch = ch
                            break
                    if relay_ch is not None:
                        break

                if relay_ch is None:
                    continue

                readout_freqs = [p["freq_hz"] for p in rmodes]
                reps_mags = []

                mux.select(relay_ch)
                time.sleep(0.02)  # brief settle after relay switch

                for rep in range(N_CALIB_REPS):
                    rx = playrec_capture(tx, sample_rate, device_idx)
                    mags = extract_features(rx, sample_rate, readout_freqs,
                                            settle_samples)
                    reps_mags.append(mags.tolist())
                    total_captures += 1

                mean_mags = np.mean(reps_mags, axis=0).tolist()

                calib_data[enc_name][rkey][char_idx] = {
                    "char": chr(char_idx) if 32 <= char_idx < 127 else None,
                    "active_modes": active_indices,
                    "active_freqs": [mode_freqs[i] for i in active_indices],
                    "mean": mean_mags,
                    "reps": reps_mags,
                }

            # Progress
            if (char_idx + 1) % CHECKPOINT_EVERY == 0 or char_idx == N_ASCII - 1:
                elapsed = time.time() - t0_enc
                rate = total_captures / (time.time() - t0) if time.time() > t0 else 1
                remaining_chars = N_ASCII - char_idx - 1
                remaining_caps = remaining_chars * N_CALIB_REPS * n_relay_paths
                eta = remaining_caps / rate if rate > 0 else 0
                print(f"    [{enc_name} {char_idx+1:3d}/{N_ASCII}] "
                      f"{char_label:>8s}  modes={active_indices}  "
                      f"{total_captures} captures  ~{eta:.0f}s remaining")

            # Checkpoint
            if (char_idx + 1) % (CHECKPOINT_EVERY * 4) == 0:
                _save_checkpoint(calib_data, encodings, all_relay_modes,
                                 sample_rate, timestamp, char_idx + 1)

    mux.off()
    mux.close()

    elapsed_total = time.time() - t0
    print(f"\n  Calibration complete: {total_captures} captures in "
          f"{elapsed_total:.0f}s ({total_captures/elapsed_total:.1f} cap/s)")

    # Save full calibration
    save_path = _save_calibration(calib_data, encodings, all_relay_modes,
                                  mode_freqs, sample_rate, census, timestamp)
    print(f"  Saved: {save_path.name}")
    return save_path


def _save_checkpoint(calib_data, encodings, all_relay_modes,
                     sample_rate, timestamp, n_chars_done):
    """Save incremental checkpoint (without reps to save space)."""
    ckpt = {
        "timestamp": timestamp,
        "checkpoint": True,
        "n_chars_done": n_chars_done,
        "encodings": {name: {k: v for k, v in enc.items() if k != "mapping"}
                      for name, enc in encodings.items()},
    }
    path = RESULTS_DIR / f"esn_v5_ascii_checkpoint_{timestamp}.json"
    with open(path, "w") as f:
        json.dump(ckpt, f, indent=1)


def _save_calibration(calib_data, encodings, all_relay_modes,
                      mode_freqs, sample_rate, census, timestamp):
    """Save full calibration with all reps."""
    save = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "v5_ascii",
        "n_chars": N_ASCII,
        "n_reps": N_CALIB_REPS,
        "sample_rate": sample_rate,
        "capture_duration_s": CALIB_DURATION_S,
        "settle_s": CALIB_SETTLE_S,
        "drive_amplitude": DRIVE_AMPLITUDE,
        "mode_freqs": mode_freqs,
        "relay_paths": {rkey: [p["freq_hz"] for p in modes]
                        for rkey, modes in all_relay_modes.items()},
        "encodings": {},
        "data": {},
    }
    for enc_name, enc in encodings.items():
        save["encodings"][enc_name] = {
            k: v for k, v in enc.items() if k != "mapping"
        }
        save["encodings"][enc_name]["mapping"] = {
            str(c): indices for c, indices in enc["mapping"].items()
        }

    # Store data with string keys (JSON requires string keys)
    for enc_name in calib_data:
        save["data"][enc_name] = {}
        for rkey in calib_data[enc_name]:
            save["data"][enc_name][rkey] = {
                str(c): v for c, v in calib_data[enc_name][rkey].items()
            }

    path = RESULTS_DIR / f"esn_v5_ascii_{timestamp}.json"
    with open(path, "w") as f:
        json.dump(save, f, indent=1)
    return path


# ══════════════════════════════════════════════════════════════════════
# Feature engineering
# ══════════════════════════════════════════════════════════════════════

def _interaction_expand(x, max_degree=2):
    """Polynomial interaction expansion up to given degree."""
    n = len(x)
    terms = list(x)
    for d in range(2, max_degree + 1):
        for combo in combinations(range(n), d):
            t = 1.0
            for idx in combo:
                t *= x[idx]
            terms.append(t)
    return np.array(terms)


def build_features(calib_data: dict, enc_name: str, relay_keys: list[str],
                   poly_degree: int = 0) -> list[np.ndarray]:
    """Build normalized feature vectors for all 128 ASCII chars.

    For each char: concatenate mean magnitudes across all relay paths,
    baseline-subtract (char 0 = silence), log1p, z-score.
    Optionally add polynomial interaction terms.

    Returns: list of 128 feature vectors.
    """
    enc_data = calib_data[enc_name]

    # Collect raw mean vectors per char
    raw_vecs = []
    for c in range(N_ASCII):
        parts = []
        for rkey in relay_keys:
            rdata = enc_data[rkey]
            if str(c) in rdata:
                parts.append(np.array(rdata[str(c)]["mean"]))
            elif c in rdata:
                parts.append(np.array(rdata[c]["mean"]))
            else:
                raise KeyError(f"Missing char {c} in {enc_name}/{rkey}")
        raw_vecs.append(np.concatenate(parts))

    # Baseline subtraction (char 0 = NUL = silence or minimal drive)
    baseline = raw_vecs[0].copy()

    feats = []
    for v in raw_vecs:
        f = np.log1p(np.maximum(v - baseline, 0))
        feats.append(f)

    # Z-score normalization
    arr = np.array(feats)
    mu = arr.mean(axis=0)
    sigma = arr.std(axis=0) + 1e-8
    feats_norm = [(f - mu) / sigma for f in feats]

    # Polynomial expansion
    if poly_degree >= 2:
        feats_norm = [_interaction_expand(f, max_degree=poly_degree)
                      for f in feats_norm]

    return feats_norm


# ══════════════════════════════════════════════════════════════════════
# ESN
# ══════════════════════════════════════════════════════════════════════

class ESN:
    def __init__(self, input_dim, hidden_dim=ESN_HIDDEN,
                 spectral_radius=ESN_SPECTRAL, input_scale=ESN_INPUT_SCALE,
                 leak=ESN_LEAK, seed=42):
        rng = np.random.default_rng(seed)
        self.hidden_dim = hidden_dim
        self.leak = leak
        self.W_in = rng.standard_normal((hidden_dim, input_dim)) * input_scale
        W = rng.standard_normal((hidden_dim, hidden_dim))
        rho = np.max(np.abs(np.linalg.eigvals(W)))
        self.W_rec = W * (spectral_radius / rho) if rho > 0 else W

    def run_sequence(self, feat_seq):
        h = np.zeros(self.hidden_dim)
        for x in feat_seq:
            h = (1 - self.leak) * h + self.leak * np.tanh(
                self.W_in @ x + self.W_rec @ h)
        return h

    def collect_states(self, all_seqs):
        return np.array([self.run_sequence(s) for s in all_seqs])


def ridge_multiclass(H_tr, H_te, y_tr, y_te, n_classes, alpha=RIDGE_ALPHA):
    Hb_tr = np.column_stack([H_tr, np.ones(len(H_tr))])
    Hb_te = np.column_stack([H_te, np.ones(len(H_te))])
    d = Hb_tr.shape[1]
    Y_oh = np.zeros((len(y_tr), n_classes))
    for i, c in enumerate(y_tr):
        Y_oh[i, c] = 1.0
    W = np.linalg.solve(Hb_tr.T @ Hb_tr + alpha * np.eye(d), Hb_tr.T @ Y_oh)
    scores = Hb_te @ W
    preds = np.argmax(scores, axis=1)
    acc = float(np.mean(preds == y_te))
    return acc, preds, scores


def ridge_binary(H_tr, H_te, y_tr, y_te, alpha=RIDGE_ALPHA):
    Hb_tr = np.column_stack([H_tr, np.ones(len(H_tr))])
    Hb_te = np.column_stack([H_te, np.ones(len(H_te))])
    d = Hb_tr.shape[1]
    w = np.linalg.solve(Hb_tr.T @ Hb_tr + alpha * np.eye(d),
                        Hb_tr.T @ y_tr.astype(np.float64))
    preds = (Hb_te @ w > 0.5).astype(int)
    acc = float(np.mean(preds == y_te))
    return acc, preds


# ══════════════════════════════════════════════════════════════════════
# Software baselines
# ══════════════════════════════════════════════════════════════════════

def sw_onehot(c: int) -> np.ndarray:
    """One-hot encoding: 128-dimensional."""
    v = np.zeros(N_ASCII, dtype=np.float64)
    v[c] = 1.0
    return v


def sw_binary(c: int) -> np.ndarray:
    """7-bit binary encoding: 7-dimensional, ±1 centered."""
    return np.array([(c >> b) & 1 for b in range(7)], dtype=np.float64) * 2 - 1


def sw_poly(c: int, degree: int = 4) -> np.ndarray:
    """Polynomial expansion of 7-bit binary representation."""
    bits = sw_binary(c)
    return _interaction_expand(bits, max_degree=degree)


# ══════════════════════════════════════════════════════════════════════
# Experiment 1: Direct 128-class classification (no sequence memory)
# ══════════════════════════════════════════════════════════════════════

def run_direct_classification(calib_data: dict, relay_keys: list[str]):
    """Classify 128 ASCII characters from single spectral snapshots.

    No ESN needed — just linear readout on features.
    Uses leave-one-rep-out cross-validation within the N_CALIB_REPS captures.
    """
    print(f"\n{'═' * 80}")
    print("  EXPERIMENT 1: DIRECT 128-CLASS CLASSIFICATION")
    print(f"  (linear readout, leave-one-rep-out over {N_CALIB_REPS} reps)")
    print(f"{'═' * 80}")

    results = {}

    for enc_name in calib_data:
        enc_data = calib_data[enc_name]

        # Build per-rep feature matrices
        # Shape: (128, N_CALIB_REPS, feature_dim)
        all_reps = []
        for c in range(N_ASCII):
            char_reps = []
            for rep_idx in range(N_CALIB_REPS):
                parts = []
                for rkey in relay_keys:
                    rdata = enc_data[rkey]
                    entry = rdata.get(str(c), rdata.get(c))
                    if entry and rep_idx < len(entry["reps"]):
                        parts.append(np.array(entry["reps"][rep_idx]))
                    else:
                        parts.append(np.zeros(1))
                char_reps.append(np.concatenate(parts))
            all_reps.append(char_reps)

        # Baseline: char 0, mean across reps
        baseline = np.mean(all_reps[0], axis=0)

        # Normalize: log1p(baseline-subtracted), z-score
        all_feats = []  # (128, n_reps, dim)
        for c in range(N_ASCII):
            rep_feats = []
            for rep_idx in range(N_CALIB_REPS):
                f = np.log1p(np.maximum(
                    np.array(all_reps[c][rep_idx]) - baseline, 0))
                rep_feats.append(f)
            all_feats.append(rep_feats)

        # Flatten for z-score computation
        flat = np.array([f for char_feats in all_feats
                         for f in char_feats])
        mu = flat.mean(axis=0)
        sigma = flat.std(axis=0) + 1e-8

        for c in range(N_ASCII):
            for r in range(N_CALIB_REPS):
                all_feats[c][r] = (all_feats[c][r] - mu) / sigma

        feat_dim = len(all_feats[0][0])

        # Leave-one-rep-out cross-validation
        fold_accs = []
        all_preds = []
        all_true = []

        for hold_out_rep in range(N_CALIB_REPS):
            X_tr, y_tr, X_te, y_te = [], [], [], []
            for c in range(N_ASCII):
                for r in range(N_CALIB_REPS):
                    if r == hold_out_rep:
                        X_te.append(all_feats[c][r])
                        y_te.append(c)
                    else:
                        X_tr.append(all_feats[c][r])
                        y_tr.append(c)

            X_tr = np.array(X_tr)
            X_te = np.array(X_te)
            y_tr = np.array(y_tr)
            y_te = np.array(y_te)

            acc, preds, _ = ridge_multiclass(
                X_tr, X_te, y_tr, y_te, n_classes=N_ASCII)
            fold_accs.append(acc)
            all_preds.extend(preds.tolist())
            all_true.extend(y_te.tolist())

        mean_acc = float(np.mean(fold_accs))
        std_acc = float(np.std(fold_accs))

        # Per-class accuracy
        all_preds = np.array(all_preds)
        all_true = np.array(all_true)
        per_class = np.zeros(N_ASCII)
        for c in range(N_ASCII):
            mask = all_true == c
            if mask.sum() > 0:
                per_class[c] = float(np.mean(all_preds[mask] == c))

        # Confusion matrix summary: top-5 confused pairs
        from collections import Counter
        confusions = Counter()
        for t, p in zip(all_true, all_preds):
            if t != p:
                confusions[(int(t), int(p))] += 1
        top_confused = confusions.most_common(10)

        results[enc_name] = {
            "mean_acc": mean_acc,
            "std_acc": std_acc,
            "fold_accs": fold_accs,
            "feat_dim": feat_dim,
            "per_class_acc": per_class.tolist(),
            "n_perfect_classes": int(np.sum(per_class == 1.0)),
            "n_zero_classes": int(np.sum(per_class == 0.0)),
            "top_confused": [
                {"true": int(t), "pred": int(p), "count": cnt,
                 "true_char": chr(t) if 32 <= t < 127 else f"0x{t:02X}",
                 "pred_char": chr(p) if 32 <= p < 127 else f"0x{p:02X}"}
                for (t, p), cnt in top_confused
            ],
        }

        print(f"\n  {enc_name:>12s}: {mean_acc:6.1%} ± {std_acc:.1%}  "
              f"(dim={feat_dim}, "
              f"{results[enc_name]['n_perfect_classes']}/128 perfect, "
              f"{results[enc_name]['n_zero_classes']}/128 zero)")

        # Show top confusions
        if top_confused:
            print(f"    Top confusions:")
            for (t, p), cnt in top_confused[:5]:
                tc = chr(t) if 32 <= t < 127 else f"0x{t:02X}"
                pc = chr(p) if 32 <= p < 127 else f"0x{p:02X}"
                print(f"      '{tc}' → '{pc}' ({cnt}×)")

    # Software baselines for comparison
    print(f"\n  {'─' * 60}")
    print(f"  SOFTWARE BASELINES (same ridge regression, no hardware)")

    for sw_name, sw_func in [
        ("sw_onehot_128", lambda c: sw_onehot(c)),
        ("sw_binary_7", lambda c: sw_binary(c)),
        ("sw_poly4_7bit", lambda c: sw_poly(c, 4)),
        ("sw_poly7_7bit", lambda c: sw_poly(c, 7)),
    ]:
        # Software features don't have per-rep variation, so we test:
        # Can a perfect (noise-free) encoding separate 128 classes?
        # This is a sanity check — with N_CALIB_REPS identical copies,
        # performance should be 100% for complete bases.
        feats = [sw_func(c) for c in range(N_ASCII)]
        dim = len(feats[0])

        # Use same train/test split as a single fold
        rng = np.random.default_rng(42)
        indices = rng.permutation(N_ASCII)
        n_train = int(0.75 * N_ASCII)
        tr_idx = indices[:n_train]
        te_idx = indices[n_train:]

        X_tr = np.array([feats[i] for i in tr_idx])
        X_te = np.array([feats[i] for i in te_idx])
        y_tr = tr_idx
        y_te = te_idx

        acc, _, _ = ridge_multiclass(X_tr, X_te, y_tr, y_te, N_ASCII)
        results[sw_name] = {"mean_acc": acc, "feat_dim": dim}
        print(f"  {sw_name:>16s}: {acc:6.1%}  (dim={dim})")

    return results


# ══════════════════════════════════════════════════════════════════════
# Experiment 2: Sequence reversal with full ASCII alphabet
# ══════════════════════════════════════════════════════════════════════

def run_sequence_reversal(calib_data: dict, relay_keys: list[str]):
    """ESN sequence reversal: reverse a sequence of 4 ASCII tokens.

    Uses the calibrated per-char feature vectors as input to an ESN,
    trains readout to predict the reversed sequence.
    """
    print(f"\n{'═' * 80}")
    print("  EXPERIMENT 2: SEQUENCE REVERSAL (ESN)")
    print(f"  Sequences: {N_SEQUENCES} × {SEQ_LENGTH} ASCII tokens")
    print(f"  ESN: hidden={ESN_HIDDEN}, sr={ESN_SPECTRAL}, "
          f"leak={ESN_LEAK}, iscale={ESN_INPUT_SCALE}")
    print(f"{'═' * 80}")

    rng = np.random.default_rng(42)
    sequences = rng.integers(0, N_ASCII, size=(N_SEQUENCES, SEQ_LENGTH))
    reversed_seqs = sequences[:, ::-1].copy()
    n_train = int(0.75 * N_SEQUENCES)

    results = {}

    # Test each encoding + software baselines
    all_feature_sets = {}

    # Plate features (mean across reps)
    for enc_name in calib_data:
        try:
            feats = build_features(calib_data, enc_name, relay_keys)
            all_feature_sets[f"plate_{enc_name}"] = feats
        except Exception as e:
            print(f"  WARNING: {enc_name} features failed: {e}")

    # Software baselines
    all_feature_sets["sw_onehot"] = [sw_onehot(c) for c in range(N_ASCII)]
    all_feature_sets["sw_binary"] = [sw_binary(c) for c in range(N_ASCII)]
    all_feature_sets["sw_poly4"] = [sw_poly(c, 4) for c in range(N_ASCII)]
    all_feature_sets["sw_poly7"] = [sw_poly(c, 7) for c in range(N_ASCII)]

    print(f"\n  {'Feature Set':>25s} {'dim':>5s}  "
          f"{'--- 128-class accuracy by position ---':^48s}  {'mean':>6s}")
    print(f"  {'-' * 90}")

    for fs_name, feats in all_feature_sets.items():
        dim = len(feats[0])

        # Build feature sequences
        all_f = [[feats[int(t)] for t in seq] for seq in sequences]
        esn = ESN(input_dim=dim)
        H_tr = esn.collect_states(all_f[:n_train])
        H_te = esn.collect_states(all_f[n_train:])

        pos_accs = []
        for pos in range(SEQ_LENGTH):
            y_tr = reversed_seqs[:n_train, pos]
            y_te = reversed_seqs[n_train:, pos]
            acc, _, _ = ridge_multiclass(H_tr, H_te, y_tr, y_te,
                                         n_classes=N_ASCII)
            pos_accs.append(acc)

        mean_acc = float(np.mean(pos_accs))
        results[fs_name] = {
            "dim": dim, "pos_accs": pos_accs, "mean_acc": mean_acc
        }

        pa = pos_accs
        print(f"  {fs_name:>25s} {dim:5d}  "
              f"{pa[0]:6.1%} {pa[1]:6.1%} {pa[2]:6.1%} {pa[3]:6.1%}  "
              f"{mean_acc:6.1%}")

    # Verdict
    print(f"\n  {'─' * 60}")
    plate_keys = [k for k in results if k.startswith("plate_")]
    sw_keys = [k for k in results if k.startswith("sw_")]

    if plate_keys:
        best_plate = max(plate_keys, key=lambda k: results[k]["mean_acc"])
        bp = results[best_plate]
        print(f"  Best plate: {best_plate} → {bp['mean_acc']:.1%}")

    if sw_keys:
        best_sw = max(sw_keys, key=lambda k: results[k]["mean_acc"])
        bs = results[best_sw]
        print(f"  Best software: {best_sw} → {bs['mean_acc']:.1%}")

    if plate_keys and sw_keys:
        diff = bp["mean_acc"] - bs["mean_acc"]
        if diff > 0.02:
            print(f"  ★ PLATE BEATS SOFTWARE by {diff:+.1%}")
        elif diff > -0.02:
            print(f"  ≈ PLATE AND SOFTWARE TIED (Δ = {diff:+.1%})")
        else:
            print(f"  ✗ SOFTWARE WINS by {-diff:+.1%}")

    return results


# ══════════════════════════════════════════════════════════════════════
# Experiment 3: Discrimination analysis
# ══════════════════════════════════════════════════════════════════════

def run_discrimination_analysis(calib_data: dict, relay_keys: list[str]):
    """Pairwise L2 distance matrix between all 128 ASCII spectral signatures.

    Reports: mean/min inter-class distance, nearest-neighbor accuracy,
    t-SNE visualization coords.
    """
    print(f"\n{'═' * 80}")
    print("  EXPERIMENT 3: DISCRIMINATION ANALYSIS")
    print(f"{'═' * 80}")

    results = {}

    for enc_name in calib_data:
        try:
            feats = build_features(calib_data, enc_name, relay_keys)
        except Exception as e:
            print(f"  WARNING: {enc_name} failed: {e}")
            continue

        X = np.array(feats)  # (128, dim)

        # Pairwise L2 distances
        # Use broadcasting: D[i,j] = ||X[i] - X[j]||
        diffs = X[:, np.newaxis, :] - X[np.newaxis, :, :]
        D = np.sqrt(np.sum(diffs ** 2, axis=2))

        # Set diagonal to inf for nearest-neighbor
        np.fill_diagonal(D, np.inf)

        # Nearest-neighbor accuracy
        nn_preds = np.argmin(D, axis=1)
        # In a classification setting, NN is trivially the closest other point.
        # For "accuracy" here: is the nearest neighbor a different class? Always.
        # What we really want: leave-one-out NN accuracy from reps.

        # Instead: compute statistics
        min_dist = float(np.min(D))
        mean_dist = float(np.mean(D[D < np.inf]))
        min_gap_per_class = [float(np.min(D[i])) for i in range(N_ASCII)]

        # Closest pairs
        flat_idx = np.argsort(D.ravel())
        top_close = []
        seen = set()
        for idx in flat_idx[:20]:
            i, j = divmod(idx, N_ASCII)
            if i >= j:
                continue
            pair = (int(i), int(j))
            if pair not in seen:
                seen.add(pair)
                ci = chr(i) if 32 <= i < 127 else f"0x{i:02X}"
                cj = chr(j) if 32 <= j < 127 else f"0x{j:02X}"
                top_close.append({
                    "chars": (ci, cj), "dist": float(D[i, j])
                })
            if len(top_close) >= 5:
                break

        results[enc_name] = {
            "feat_dim": X.shape[1],
            "min_dist": min_dist,
            "mean_dist": mean_dist,
            "median_min_gap": float(np.median(min_gap_per_class)),
            "worst_gap": float(np.min(min_gap_per_class)),
            "top_close_pairs": top_close,
        }

        print(f"\n  {enc_name:>12s}: dim={X.shape[1]}")
        print(f"    Min pairwise distance: {min_dist:.4f}")
        print(f"    Mean pairwise distance: {mean_dist:.4f}")
        print(f"    Median NN gap: {results[enc_name]['median_min_gap']:.4f}")
        print(f"    Worst NN gap: {results[enc_name]['worst_gap']:.4f}")
        print(f"    Closest pairs:")
        for p in top_close:
            print(f"      '{p['chars'][0]}' ↔ '{p['chars'][1]}': {p['dist']:.4f}")

    return results


# ══════════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════════

def run_experiment(args):
    """Load calibration and run all classification experiments."""
    # Load calibration
    calib_path = args.calibration
    if not calib_path:
        # Find latest
        calib_files = sorted(RESULTS_DIR.glob("esn_v5_ascii_*.json"))
        calib_files = [f for f in calib_files if "checkpoint" not in f.name]
        if not calib_files:
            print("ERROR: No calibration file found. Run 'calibrate' first.")
            sys.exit(1)
        calib_path = str(calib_files[-1])

    print(f"\n  Loading calibration: {Path(calib_path).name}")
    with open(calib_path) as f:
        saved = json.load(f)

    calib_data = saved["data"]
    relay_keys = list(saved["relay_paths"].keys())

    print(f"  Encodings: {list(calib_data.keys())}")
    print(f"  Relay paths: {relay_keys}")
    print(f"  Mode freqs: {len(saved['mode_freqs'])}")

    # Run all experiments
    all_results = {}

    all_results["direct_128class"] = run_direct_classification(
        calib_data, relay_keys)

    all_results["discrimination"] = run_discrimination_analysis(
        calib_data, relay_keys)

    all_results["sequence_reversal"] = run_sequence_reversal(
        calib_data, relay_keys)

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = RESULTS_DIR / f"esn_v5_ascii_results_{timestamp}.json"

    # Convert numpy types for JSON
    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2, default=convert)

    print(f"\n  Results saved: {results_path.name}")

    # ── Final summary ──
    print(f"\n{'═' * 80}")
    print("  FINAL SUMMARY")
    print(f"{'═' * 80}")

    dc = all_results["direct_128class"]
    for enc_name in [k for k in dc if k.startswith(("singletone", "binary", "sparse"))]:
        r = dc[enc_name]
        print(f"  {enc_name:>16s}: {r['mean_acc']:6.1%} ± {r.get('std_acc', 0):.1%}  "
              f"({r['feat_dim']}d, "
              f"{r.get('n_perfect_classes', '?')}/128 perfect)")

    sr = all_results["sequence_reversal"]
    for k in sr:
        r = sr[k]
        print(f"  seq_{k:>20s}: {r['mean_acc']:6.1%}  ({r['dim']}d)")

    return all_results


def run_full(args):
    """Calibrate then experiment in one go."""
    calib_path = calibrate(args)
    args.calibration = str(calib_path)
    return run_experiment(args)


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Full-ASCII Reservoir Computing (ESN v5)")
    sub = parser.add_subparsers(dest="command", required=True)

    # calibrate
    p_cal = sub.add_parser("calibrate", help="Drive all 128 chars, capture spectra")
    p_cal.add_argument("port", help="Arduino serial port")
    p_cal.add_argument("--device", default="KRONOS", help="Audio device name hint")
    p_cal.add_argument("--census", required=True, help="Path to census JSON")
    p_cal.add_argument("--plates", default="5", help="Comma-separated plate IDs")
    p_cal.add_argument("--reps", type=int, default=N_CALIB_REPS)

    # experiment
    p_exp = sub.add_parser("experiment", help="Run classification from saved calibration")
    p_exp.add_argument("--calibration", help="Path to calibration JSON (default: latest)")

    # full
    p_full = sub.add_parser("full", help="Calibrate + experiment in one pipeline")
    p_full.add_argument("port", help="Arduino serial port")
    p_full.add_argument("--device", default="KRONOS", help="Audio device name hint")
    p_full.add_argument("--census", required=True, help="Path to census JSON")
    p_full.add_argument("--plates", default="5", help="Comma-separated plate IDs")
    p_full.add_argument("--reps", type=int, default=N_CALIB_REPS)
    p_full.add_argument("--calibration", default=None)

    args = parser.parse_args()

    if hasattr(args, "reps") and args.reps:
        # Override module-level default
        globals()["N_CALIB_REPS"] = args.reps

    if args.command == "calibrate":
        calibrate(args)
    elif args.command == "experiment":
        run_experiment(args)
    elif args.command == "full":
        run_full(args)


if __name__ == "__main__":
    main()
