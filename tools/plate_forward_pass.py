#!/usr/bin/env python3
"""
Plate Forward Pass — Physical Matrix-Vector Multiply (E10)

Proves that the plate physically implements y = H · x by:
  1. Characterizing the transfer matrix H: drive each mode solo,
     read response at all mode frequencies → one column of H per drive.
  2. Driving the plate with random multi-tone amplitude vectors x
     (using the PicoScope ARB waveform generator).
  3. Comparing physical readout y_meas to digital prediction y_pred = H · x.
  4. Computing R² and RMSE across N_TRIALS random inputs.

If R² > 0.95, the plate IS a matrix multiplier — the physics IS the
computation.  The transfer matrix H is the plate's "weight matrix."

This is the hardware companion to experiments/exp10_forward_pass.py.

Usage:
  PYTHONPATH=. python tools/plate_forward_pass.py --all-plates --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_forward_pass.py --plate 5 --n-trials 30
  PYTHONPATH=. python tools/plate_forward_pass.py --dry-run
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

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import cwm_picoscope  # noqa: F401
from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux
from firestore_submit import firebase_anon_auth, submit_experiment, print_result

# ── Configuration ─────────────────────────────────────────────────────

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

N_AVG = 8            # averages per measurement
SETTLE_S = 0.15      # settle time for AWG
SETTLE_RELAY_S = 0.10


# ── Scope helpers (shared with plate_reservoir_demo.py) ───────────────

def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    print("  PicoScope opened (Ch A ±1V DC)")
    return handle


def _close_scope(handle):
    from picosdk.ps2000 import ps2000
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("  PicoScope closed")


def _capture_fft(handle) -> tuple[np.ndarray, np.ndarray]:
    """Run one block capture, return (freq_axis, fft_magnitude)."""
    from picosdk.ps2000 import ps2000

    ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
    t0 = time.time()
    while ps2000.ps2000_ready(handle) == 0:
        time.sleep(0.002)
        if time.time() - t0 > 2:
            break
    buf_a = (ctypes.c_int16 * N_SAMPLES)()
    buf_b = (ctypes.c_int16 * N_SAMPLES)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), N_SAMPLES
    )
    if n <= 0:
        nfft = N_SAMPLES * 4
        return np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE), np.zeros(nfft // 2 + 1)
    raw = np.array(buf_a[:n], dtype=np.float64)
    windowed = raw * np.hanning(len(raw))
    nfft = len(raw) * 4
    fft_mag = np.abs(np.fft.rfft(windowed, n=nfft))
    freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
    return freq_axis, fft_mag


def _extract_magnitudes(freq_axis, fft_mag, target_freqs):
    """Extract peak magnitudes at target frequencies from FFT."""
    bin_hz = freq_axis[1] - freq_axis[0]
    mags = np.zeros(len(target_freqs))
    for j, f in enumerate(target_freqs):
        tb = int(round(f / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(fft_mag) - 1, tb + 3)
        mags[j] = float(np.max(fft_mag[lo:hi + 1]))
    return mags


def _drive_single_tone(handle, freq_hz: float, drive_uvpp: int = AWG_DRIVE_UVPP):
    """Set AWG to single tone."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, drive_uvpp, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)


def _drive_multitone(handle, freqs_hz, amplitudes, drive_uvpp=AWG_DRIVE_UVPP,
                     fixed_f_rep=None):
    """Drive multiple frequencies with specified relative amplitudes via ARB.

    freqs_hz: list of frequencies
    amplitudes: list of relative amplitudes (0.0 to 1.0)
    fixed_f_rep: if set, use this f_rep for all drives (ensures consistent
                 frequency landing between characterization and measurement).

    Returns (peak_factor, actual_freqs_hz) where actual_freqs_hz are the
    true frequencies driven (quantized to f_rep grid).
    """
    from picosdk.ps2000 import ps2000

    if not freqs_hz:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
        time.sleep(SETTLE_S)
        return 1.0, []

    arb_len = 4096
    if fixed_f_rep is not None:
        f_rep = fixed_f_rep
    else:
        max_freq = max(freqs_hz)
        f_rep = max(10.0, math.ceil(max_freq / (arb_len // 2 - 10)))
    delta_phase = int(f_rep * (2**32) / 48_000_000)
    if delta_phase < 1:
        delta_phase = 1

    buf_signal = np.zeros(arb_len, dtype=np.float64)
    actual_freqs = []
    for f_target, amp in zip(freqs_hz, amplitudes):
        k = round(f_target / f_rep)
        if k < 1 or k > arb_len // 2:
            actual_freqs.append(0.0)
            continue
        actual_freqs.append(k * f_rep)
        phase = 2 * np.pi * k * np.arange(arb_len) / arb_len
        buf_signal += amp * np.sin(phase)

    peak_factor = np.max(np.abs(buf_signal))
    if peak_factor > 0:
        buf_signal /= peak_factor
    else:
        peak_factor = 1.0
    arb_u8 = ((buf_signal * 127) + 128).clip(0, 255).astype(np.uint8)
    arb_buf = (ctypes.c_uint8 * arb_len)(*arb_u8.tolist())

    ps2000.ps2000_set_sig_gen_arbitrary(
        handle, 0, drive_uvpp,
        delta_phase, delta_phase,
        0, 0,
        arb_buf, arb_len, 0, 0
    )
    time.sleep(SETTLE_S)
    return peak_factor, actual_freqs


def _measure_response(handle, readout_freqs):
    """Average N_AVG FFT captures, return magnitudes at readout freqs."""
    all_mags = []
    for _ in range(N_AVG):
        freq_axis, fft_mag = _capture_fft(handle)
        mags = _extract_magnitudes(freq_axis, fft_mag, readout_freqs)
        all_mags.append(mags)
    return np.mean(all_mags, axis=0)


def _awg_off(handle):
    """Turn AWG off."""
    from picosdk.ps2000 import ps2000
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
    )
    time.sleep(SETTLE_S)


# ── Enrollment loader ────────────────────────────────────────────────

def _load_plate_modes(plate_id: str) -> list[float]:
    """Load enrolled mode frequencies from latest census."""
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        raise FileNotFoundError("No census file. Run plate_mode_census.py first.")
    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]
    if plate_id not in census or not census[plate_id].get("peaks"):
        raise ValueError(f"Plate {plate_id} not found in census")
    return [p["freq_hz"] for p in census[plate_id]["peaks"]]


# ── E10 Protocol ─────────────────────────────────────────────────────

def characterize_transfer_matrix(handle, mode_freqs, readout_freqs=None,
                                  fixed_f_rep=None):
    """Measure the plate's transfer matrix H.

    H[i, j] = response at readout_freq[i] when driving mode_freq[j].
    Each column is a single-tone drive + broadband FFT readout.

    fixed_f_rep: ARB frequency resolution — all drives use the same f_rep
                 to ensure every frequency lands on the same grid point,
                 regardless of which tones are active.

    Returns H as (n_readout, n_drive) matrix.
    """
    if readout_freqs is None:
        readout_freqs = mode_freqs
    n_drive = len(mode_freqs)
    n_readout = len(readout_freqs)
    H = np.zeros((n_readout, n_drive))

    for j, drive_f in enumerate(mode_freqs):
        _drive_multitone(handle, [drive_f], [1.0], fixed_f_rep=fixed_f_rep)
        H[:, j] = _measure_response(handle, readout_freqs)

    _awg_off(handle)
    return H


def run_forward_pass(handle, mux, plate_id: str,
                     n_trials: int = 20,
                     n_readout_modes: int = None,
                     seed: int = 42) -> dict:
    """Run the E10 forward-pass equivalence experiment on one plate.

    Steps:
      1. Characterize H via single-tone drives
      2. Measure noise floor (AWG off)
      3. Drive with n_trials random amplitude vectors via ARB
      4. Compare y_meas to y_pred = H · x
      5. Report R² and RMSE
    """
    name = PLATE_NAMES.get(plate_id, plate_id)
    print(f"\n{'=' * 65}")
    print(f"  FORWARD PASS E10 — Plate {name}")
    print(f"  Trials: {n_trials}")
    print(f"{'=' * 65}")

    mode_freqs = _load_plate_modes(plate_id)
    n_modes = len(mode_freqs)
    # Use top-N modes if requested
    if n_readout_modes is not None and n_readout_modes < n_modes:
        mode_freqs = mode_freqs[:n_readout_modes]
        n_modes = n_readout_modes
    print(f"  Plate {name}: {n_modes} modes")
    print(f"  Frequencies: {[f'{f/1000:.1f} kHz' for f in mode_freqs]}")

    mux.select(int(plate_id))
    time.sleep(SETTLE_RELAY_S)

    # Compute fixed f_rep so all drives (single and multi) use same frequency grid
    arb_len = 4096
    max_mode_freq = max(mode_freqs)
    fixed_f_rep = max(10.0, math.ceil(max_mode_freq / (arb_len // 2 - 10)))

    # Show actual vs enrolled frequencies
    actual_mode_freqs = [round(f / fixed_f_rep) * fixed_f_rep for f in mode_freqs]
    max_drift_hz = max(abs(a - e) for a, e in zip(actual_mode_freqs, mode_freqs))
    print(f"  ARB f_rep: {fixed_f_rep:.0f} Hz, max freq drift: {max_drift_hz:.0f} Hz")

    # ── Step 1: Characterize transfer matrix via ARB single-tone ──
    print(f"\n  Step 1: Measuring transfer matrix H ({n_modes}×{n_modes}) via ARB...")
    t0 = time.time()
    H = characterize_transfer_matrix(handle, mode_freqs, fixed_f_rep=fixed_f_rep)
    h_time = time.time() - t0
    print(f"  H captured in {h_time:.1f}s")

    # H stays in RAW (linear) space — superposition y = H·x holds in linear space
    # Log-space analysis done AFTER prediction

    # Diagonal dominance check (log scale for display)
    H_log = np.log1p(H)
    diag = np.diag(H_log)
    off_diag_max = np.max(H_log - np.diag(diag))
    print(f"  H diagonal (log): mean={np.mean(diag):.2f}, min={np.min(diag):.2f}")
    print(f"  H off-diagonal max (log): {off_diag_max:.2f}")
    print(f"  Diagonal dominance ratio: {np.mean(diag) / (off_diag_max + 1e-8):.1f}×")

    # ── Step 2: Noise floor (AWG off) ──
    print(f"\n  Step 2: Measuring noise floor...")
    _awg_off(handle)
    noise_raw = _measure_response(handle, mode_freqs)
    noise_mean = float(np.mean(noise_raw))
    print(f"  Noise floor: mean={noise_mean:.1f} (raw), "
          f"{np.mean(np.log1p(noise_raw)):.3f} (log)")

    # ── Step 3: Random multi-tone trials ──
    print(f"\n  Step 3: Running {n_trials} random multi-tone trials...")
    rng = np.random.default_rng(seed)

    # Generate amplitude vectors: mix of sparse and dense
    X_inputs = []
    for i in range(n_trials):
        if i < n_trials // 3:
            # Sparse: 1-2 active tones
            x = np.zeros(n_modes)
            n_active = rng.integers(1, min(3, n_modes) + 1)
            active = rng.choice(n_modes, n_active, replace=False)
            x[active] = rng.uniform(0.3, 1.0, n_active)
        elif i < 2 * n_trials // 3:
            # Medium: 50% active
            x = np.zeros(n_modes)
            n_active = max(1, n_modes // 2)
            active = rng.choice(n_modes, n_active, replace=False)
            x[active] = rng.uniform(0.2, 1.0, n_active)
        else:
            # Dense: all tones, random amplitudes
            x = rng.uniform(0.1, 1.0, n_modes)
        X_inputs.append(x)

    Y_predicted = []
    Y_measured = []
    trial_details = []

    t0 = time.time()
    for i, x in enumerate(X_inputs):
        active_mask = x > 0.01
        active_freqs = [mode_freqs[j] for j in range(n_modes) if active_mask[j]]
        active_amps = [x[j] for j in range(n_modes) if active_mask[j]]

        if active_freqs:
            peak_factor, _ = _drive_multitone(handle, active_freqs, active_amps,
                                              fixed_f_rep=fixed_f_rep)
        else:
            _awg_off(handle)
            peak_factor = 1.0

        # Physical measurement (raw space)
        y_meas_raw = _measure_response(handle, mode_freqs)

        # Digital prediction in RAW space:
        # Each tone's effective amplitude = a_j / peak_factor (ARB normalization)
        # Superposition: y_pred_raw = H_raw @ (x / peak_factor)
        x_effective = x / peak_factor
        y_pred_raw = H @ x_effective

        # Subtract noise floor from both (baseline correction)
        y_meas_corr = np.maximum(y_meas_raw - noise_raw, 0)
        y_pred_corr = np.maximum(y_pred_raw - noise_raw, 0)

        # Compare in log space (matches physical intuition — dB-like)
        y_meas_log = np.log1p(y_meas_corr)
        y_pred_log = np.log1p(y_pred_corr)

        Y_predicted.append(y_pred_log)
        Y_measured.append(y_meas_log)

        # Per-trial R²
        ss_res = np.sum((y_meas_log - y_pred_log) ** 2)
        ss_tot = np.sum((y_meas_log - np.mean(y_meas_log)) ** 2)
        r2 = 1 - ss_res / (ss_tot + 1e-12)
        rmse = float(np.sqrt(np.mean((y_meas_log - y_pred_log) ** 2)))
        n_active = int(np.sum(active_mask))

        # Also compute raw Pearson correlation
        if np.std(y_meas_log) > 0 and np.std(y_pred_log) > 0:
            trial_corr = float(np.corrcoef(y_pred_log, y_meas_log)[0, 1])
        else:
            trial_corr = 0.0

        trial_details.append({
            "trial": i,
            "n_active": n_active,
            "r_squared": round(r2, 4),
            "rmse": round(rmse, 4),
            "correlation": round(trial_corr, 4),
            "peak_factor": round(peak_factor, 4),
        })

        if (i + 1) % 5 == 0:
            elapsed = time.time() - t0
            eta = (n_trials - i - 1) * elapsed / (i + 1)
            print(f"    [{i+1}/{n_trials}] R²={r2:.3f}, corr={trial_corr:.3f}, "
                  f"active={n_active}, pf={peak_factor:.2f}, "
                  f"{elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

    trial_time = time.time() - t0
    _awg_off(handle)
    mux.off()

    # ── Step 4: Aggregate statistics ──
    Y_pred_all = np.array(Y_predicted)
    Y_meas_all = np.array(Y_measured)

    # Global R² (across all trials and modes)
    ss_res_global = np.sum((Y_meas_all - Y_pred_all) ** 2)
    ss_tot_global = np.sum((Y_meas_all - np.mean(Y_meas_all)) ** 2)
    r2_global = 1 - ss_res_global / (ss_tot_global + 1e-12)

    # Per-trial statistics
    r2_values = np.array([t["r_squared"] for t in trial_details])
    rmse_values = np.array([t["rmse"] for t in trial_details])
    corr_values = np.array([t["correlation"] for t in trial_details])

    # Per-mode R²
    r2_per_mode = []
    for j in range(n_modes):
        y_p = Y_pred_all[:, j]
        y_m = Y_meas_all[:, j]
        ss_r = np.sum((y_m - y_p) ** 2)
        ss_t = np.sum((y_m - np.mean(y_m)) ** 2)
        r2_per_mode.append(1 - ss_r / (ss_t + 1e-12))

    # Global correlation
    corr = float(np.corrcoef(Y_pred_all.ravel(), Y_meas_all.ravel())[0, 1])

    # By sparsity category
    sparse_trials = [t for t in trial_details if t["n_active"] <= 2]
    medium_trials = [t for t in trial_details
                     if 2 < t["n_active"] < n_modes]
    dense_trials = [t for t in trial_details
                    if t["n_active"] >= n_modes - 1]

    sparse_r2 = np.mean([t["r_squared"] for t in sparse_trials]) if sparse_trials else float('nan')
    medium_r2 = np.mean([t["r_squared"] for t in medium_trials]) if medium_trials else float('nan')
    dense_r2 = np.mean([t["r_squared"] for t in dense_trials]) if dense_trials else float('nan')

    sparse_corr = np.mean([t["correlation"] for t in sparse_trials]) if sparse_trials else float('nan')
    medium_corr = np.mean([t["correlation"] for t in medium_trials]) if medium_trials else float('nan')
    dense_corr = np.mean([t["correlation"] for t in dense_trials]) if dense_trials else float('nan')

    # ── Print results ──
    print(f"\n  ── Results: Plate {name} ──")
    print(f"  Transfer matrix H: {n_modes}×{n_modes}")
    print(f"  Trials: {n_trials} ({trial_time:.1f}s)")
    print(f"  ")
    print(f"  Global R²:       {r2_global:.4f}")
    print(f"  Mean trial R²:   {np.mean(r2_values):.4f} ± {np.std(r2_values):.4f}")
    print(f"  Global corr:     {corr:.4f}")
    print(f"  Mean trial corr: {np.mean(corr_values):.4f} ± {np.std(corr_values):.4f}")
    print(f"  Mean RMSE:       {np.mean(rmse_values):.4f}")
    print(f"  ")
    print(f"  By sparsity:         R²        Corr")
    print(f"    Sparse (1-2):  {sparse_r2:>8.4f}   {sparse_corr:>8.4f}")
    print(f"    Medium (~50%): {medium_r2:>8.4f}   {medium_corr:>8.4f}")
    print(f"    Dense (all):   {dense_r2:>8.4f}   {dense_corr:>8.4f}")
    print(f"  ")
    print(f"  Per-mode R²:")
    for j in range(n_modes):
        print(f"    Mode {j} ({mode_freqs[j]/1000:.1f} kHz): "
              f"R² = {r2_per_mode[j]:.4f}")
    print(f"  ")
    verdict = "PASS" if r2_global > 0.95 else \
              "MARGINAL" if r2_global > 0.80 else "FAIL"
    print(f"  VERDICT: {verdict} (threshold: R² > 0.95)")

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plate_name": name,
        "plate_id": plate_id,
        "n_modes": n_modes,
        "n_trials": n_trials,
        "r2_global": round(r2_global, 4),
        "r2_mean": round(float(np.mean(r2_values)), 4),
        "r2_std": round(float(np.std(r2_values)), 4),
        "correlation": round(corr, 4),
        "rmse_mean": round(float(np.mean(rmse_values)), 4),
        "r2_sparse": round(sparse_r2, 4),
        "r2_medium": round(medium_r2, 4),
        "r2_dense": round(dense_r2, 4) if not np.isnan(dense_r2) else None,
        "r2_per_mode": [round(r, 4) for r in r2_per_mode],
        "noise_floor_mean_raw": round(noise_mean, 2),
        "h_diag_mean_log": round(float(np.mean(diag)), 4),
        "h_capture_time_s": round(h_time, 1),
        "trial_time_s": round(trial_time, 1),
        "mode_freqs_hz": mode_freqs,
        "verdict": verdict,
        "transfer_matrix_log": H_log.tolist(),
        "trial_details": trial_details,
    }

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Plate forward pass — physical matrix-vector multiply (E10)"
    )
    parser.add_argument(
        "--plate", type=str, default="5",
        help="Plate relay ID (1-5, default: 5 = Plate E)"
    )
    parser.add_argument(
        "--all-plates", action="store_true",
        help="Run on all 5 plates sequentially"
    )
    parser.add_argument(
        "--n-trials", type=int, default=20,
        help="Number of random multi-tone trials per plate (default: 20)"
    )
    parser.add_argument(
        "--port", type=str, default="/dev/cu.usbserial-11310",
        help="Serial port for relay mux"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Don't submit to Firestore"
    )
    args = parser.parse_args()

    plate_ids = sorted(PLATE_NAMES.keys()) if args.all_plates else [args.plate]

    handle = _open_scope()
    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {mux.port}")

    results = []
    try:
        for pid in plate_ids:
            result = run_forward_pass(
                handle, mux, pid,
                n_trials=args.n_trials,
            )
            results.append(result)
    finally:
        _close_scope(handle)
        mux.close()

    # ── Save & submit ──
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    token = None

    for result in results:
        name = result["plate_name"]
        save_path = LAB_DIR / f"forward_pass_{name}_{TIMESTAMP}.json"
        with open(save_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Saved: {save_path}")

        if not args.dry_run:
            print("  Submitting to Firestore...")
            try:
                if token is None:
                    token = firebase_anon_auth()
                data = {
                    "plate_name": name,
                    "n_modes": result["n_modes"],
                    "n_trials": result["n_trials"],
                    "r2_global": result["r2_global"],
                    "r2_mean": result["r2_mean"],
                    "correlation": result["correlation"],
                    "rmse_mean": result["rmse_mean"],
                    "verdict": result["verdict"],
                }
                notes = (
                    f"E10 Forward Pass: Plate {name}, "
                    f"R²={result['r2_global']:.4f}, "
                    f"corr={result['correlation']:.4f}, "
                    f"verdict={result['verdict']}."
                )
                r = submit_experiment(token, "exp-forward-pass", data, notes=notes)
                print_result(r)
            except Exception as e:
                print(f"  ✗ Submission failed: {e}")

    if len(results) > 1:
        print(f"\n{'=' * 65}")
        print(f"  SUMMARY — FORWARD PASS E10")
        print(f"{'=' * 65}")
        print(f"  {'Plate':<8} {'Modes':>5} {'R² global':>10} {'R² mean':>10} "
              f"{'Corr':>8} {'Verdict':>10}")
        print(f"  {'-' * 55}")
        for r in results:
            print(f"  {r['plate_name']:<8} {r['n_modes']:>5} "
                  f"{r['r2_global']:>10.4f} {r['r2_mean']:>10.4f} "
                  f"{r['correlation']:>8.4f} {r['verdict']:>10}")

        r2s = [r['r2_global'] for r in results]
        cors = [r['correlation'] for r in results]
        print(f"  {'Mean':<8} {'':<5} "
              f"{sum(r2s)/len(r2s):>10.4f} {'':<10} "
              f"{sum(cors)/len(cors):>8.4f}")

        combined_path = LAB_DIR / f"forward_pass_all_{TIMESTAMP}.json"
        with open(combined_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"  Combined: {combined_path}")


if __name__ == "__main__":
    main()
