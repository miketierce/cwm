#!/usr/bin/env python3
"""
Phase 1.6 Step 2: Broadband Mode Census

High-resolution CW sweep (25 Hz steps) across all 5 fused silica plates.
Builds a complete mode catalog for fingerprint enrollment (Step 3).

Reuses hardware abstractions from plate_q_measurement.py.
Saves full sweep data + detected peaks per plate.
"""
from __future__ import annotations

import ctypes
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# ── Paths ──
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

# Ensure DYLD_LIBRARY_PATH is set before any PicoSDK imports
import cwm_picoscope  # noqa: F401 — triggers _ensure_dyld_path()

LAB_DIR = TOOLS_DIR.parent / "data" / "results" / "lab"
RESULTS_DIR = LAB_DIR / "plate_exps"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ── Plate config ──
# Physical plate → pattern → relay channel(s)
# Plate 1 (A): relay 1 (NE-RX only)
# Plate 2 (B): relay 2 (NE-RX only)
# Plate 3 (G): relay 3 (NE-RX), relay 4 (NW-RX)
# Plate 4 (D): relay 5 (NE-RX), relay 6 (NW-RX)
# Plate 5 (F): relay 7 (NE-RX), relay 8 (NW-RX)
PLATE_IDS = ["5"]  # TEMP: re-sweep plate F only after wax removal
PLATE_NAMES = {"1": "A", "2": "B", "3": "G", "4": "D", "5": "F"}

# Map plate ID → list of (relay_channel, rx_label) for census sweeps
PLATE_RELAYS = {
    "1": [(1, "NE")],
    "2": [(2, "NE")],
    "3": [(3, "NE"), (4, "NW")],
    "4": [(5, "NE"), (6, "NW")],
    "5": [(7, "NE"), (8, "NW")],
}

# ── Sweep config ──
F_START = 200        # Hz
F_STOP = 100_000     # Hz
F_STEP = 25          # Hz  (4× finer than Step 1's 100 Hz)
N_AVG = 4            # averages per frequency point
SETTLE_S = 0.05      # settle time per step
SETTLE_RELAY_S = 0.10

# ── Peak detection ──
MIN_SNR_DB = 6.0     # lower threshold than Step 1 to catch weaker modes
MIN_PROMINENCE_DB = 3.0  # peak must stand 3 dB above neighbors


def _open_scope():
    from picosdk.ps2000 import ps2000
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V DC
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B off
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


def _capture_raw(handle):
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import TIMEBASE, N_SAMPLES
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
    if n > 0:
        return np.array(buf_a[:n], dtype=np.float64)
    return np.zeros(N_SAMPLES, dtype=np.float64)


def sweep_plate(handle, mux, plate_id: str, relay_ch: int | None = None,
                rx_label: str = "NE") -> list[dict]:
    """High-resolution CW sweep for one plate on a specific relay channel."""
    from picosdk.ps2000 import ps2000
    from cwm_picoscope import AWG_DRIVE_UVPP, SAMPLE_RATE

    ch = relay_ch if relay_ch is not None else int(plate_id)
    mux.select(ch)
    time.sleep(SETTLE_RELAY_S)

    freqs = np.arange(F_START, F_STOP + F_STEP, F_STEP)
    name = PLATE_NAMES[plate_id]
    n_pts = len(freqs)
    print(f"\n  Plate {name} (relay {ch}, RX-{rx_label}): sweep {F_START}–{F_STOP} Hz, "
          f"{F_STEP} Hz steps ({n_pts} pts)")

    sweep_data = []
    t0 = time.time()

    for i, freq in enumerate(freqs):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq), float(freq), 0.0, 0.0, 0, 0
        )
        time.sleep(SETTLE_S)

        mags = []
        phases = []
        for _ in range(N_AVG):
            raw = _capture_raw(handle)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            spectrum = np.fft.rfft(windowed, n=nfft)
            fft_mag = np.abs(spectrum)
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            tb = int(round(freq / bin_hz))
            lo = max(0, tb - 3)
            hi = min(len(fft_mag) - 1, tb + 3)
            peak_bin = lo + int(np.argmax(fft_mag[lo:hi + 1]))
            mags.append(float(fft_mag[peak_bin]))
            phases.append(float(np.angle(spectrum[peak_bin])))

        avg_mag = float(np.mean(mags))
        # Circular mean for phase
        avg_phase = float(np.arctan2(
            np.mean(np.sin(phases)), np.mean(np.cos(phases))
        ))
        phase_std = float(np.std(np.unwrap(phases)))

        sweep_data.append({
            "freq_hz": round(float(freq), 1),
            "magnitude": round(avg_mag, 1),
            "phase_rad": round(avg_phase, 4),
            "phase_std": round(phase_std, 4),
        })

        # Progress every 400 points (~10 kHz)
        if i % 400 == 0:
            elapsed = time.time() - t0
            pct = (i + 1) / n_pts * 100
            print(f"    {freq:7.0f} Hz: mag={avg_mag:10.0f}  "
                  f"[{pct:4.1f}% | {elapsed:.0f}s]")

    elapsed = time.time() - t0
    print(f"    Sweep complete: {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    return sweep_data


def detect_modes(sweep_data: list[dict]) -> list[dict]:
    """Detect resonance peaks with SNR and local prominence."""
    mags = np.array([s["magnitude"] for s in sweep_data])
    freqs = np.array([s["freq_hz"] for s in sweep_data])
    phases = np.array([s["phase_rad"] for s in sweep_data])
    phase_stds = np.array([s["phase_std"] for s in sweep_data])

    noise_floor = float(np.median(mags))
    if noise_floor <= 0:
        noise_floor = 1.0

    peaks = []
    for i in range(2, len(mags) - 2):
        # Must be a local max (check 2 neighbors each side for robustness)
        if not (mags[i] > mags[i - 1] and mags[i] > mags[i + 1]):
            continue

        snr_db = 20 * math.log10(mags[i] / noise_floor) if mags[i] > 0 else 0
        if snr_db < MIN_SNR_DB:
            continue

        # Local prominence: dB above min of nearest 4 neighbors
        local_min = min(mags[i - 2], mags[i - 1], mags[i + 1], mags[i + 2])
        if local_min > 0:
            prominence_db = 20 * math.log10(mags[i] / local_min)
        else:
            prominence_db = snr_db
        if prominence_db < MIN_PROMINENCE_DB:
            continue

        peaks.append({
            "freq_hz": float(freqs[i]),
            "magnitude": float(mags[i]),
            "snr_db": round(snr_db, 1),
            "prominence_db": round(prominence_db, 1),
            "phase_rad": round(float(phases[i]), 4),
            "phase_std": round(float(phase_stds[i]), 4),
        })

    peaks.sort(key=lambda p: p["magnitude"], reverse=True)
    return peaks


def analyze_mode_spacing(peaks: list[dict]) -> dict:
    """Compute mode density and spacing statistics."""
    if len(peaks) < 2:
        return {"n_modes": len(peaks)}

    freqs_sorted = sorted([p["freq_hz"] for p in peaks])
    spacings = [freqs_sorted[i + 1] - freqs_sorted[i]
                for i in range(len(freqs_sorted) - 1)]

    return {
        "n_modes": len(peaks),
        "freq_min_hz": freqs_sorted[0],
        "freq_max_hz": freqs_sorted[-1],
        "bandwidth_hz": freqs_sorted[-1] - freqs_sorted[0],
        "mean_spacing_hz": round(float(np.mean(spacings)), 1),
        "median_spacing_hz": round(float(np.median(spacings)), 1),
        "min_spacing_hz": round(float(np.min(spacings)), 1),
        "max_spacing_hz": round(float(np.max(spacings)), 1),
        "modes_per_khz": round(len(peaks) / ((freqs_sorted[-1] - freqs_sorted[0]) / 1000), 2),
    }


def run_mode_census(port: str) -> dict:
    """Main entry: high-resolution sweep on all 5 plates."""
    from relay_mux import RelayMux

    print("\n" + "=" * 70)
    print("  PHASE 1.6 STEP 2: BROADBAND MODE CENSUS")
    print("  25 Hz resolution, 200 Hz – 100 kHz")
    print("=" * 70)

    handle = _open_scope()
    mux = RelayMux(port=port)
    mux.open()
    print(f"  Relay mux connected on {mux.port}")

    all_results = {}
    t_start = time.time()

    for pid in PLATE_IDS:
        name = PLATE_NAMES[pid]
        relays = PLATE_RELAYS[pid]

        for relay_ch, rx_label in relays:
            # Result key: "1" for single-RX plates, "3_NE"/"3_NW" for dual-RX
            rkey = pid if len(relays) == 1 else f"{pid}_{rx_label}"

            print(f"\n{'─' * 70}")
            print(f"  PLATE {name} — RX-{rx_label} (relay {relay_ch})")
            print(f"{'─' * 70}")

            sweep_data = sweep_plate(handle, mux, pid, relay_ch, rx_label)
            peaks = detect_modes(sweep_data)
            stats = analyze_mode_spacing(peaks)

            print(f"  Detected {len(peaks)} modes (SNR > {MIN_SNR_DB} dB, "
                  f"prominence > {MIN_PROMINENCE_DB} dB)")
            if stats.get("modes_per_khz"):
                print(f"  Mode density: {stats['modes_per_khz']:.1f} modes/kHz "
                      f"({stats['freq_min_hz']:.0f}–{stats['freq_max_hz']:.0f} Hz)")
                print(f"  Spacing: mean {stats['mean_spacing_hz']:.0f} Hz, "
                      f"min {stats['min_spacing_hz']:.0f} Hz, "
                      f"max {stats['max_spacing_hz']:.0f} Hz")

            # Print top 20 modes
            print(f"\n  Top 20 modes:")
            print(f"    {'#':>3}  {'Freq (Hz)':>10}  {'Magnitude':>12}  "
                  f"{'SNR (dB)':>8}  {'Prom (dB)':>9}  {'Phase (rad)':>11}  {'σ_φ':>6}")
            for i, p in enumerate(peaks[:20]):
                print(f"    {i+1:3d}  {p['freq_hz']:10.1f}  {p['magnitude']:12.0f}  "
                      f"{p['snr_db']:8.1f}  {p['prominence_db']:9.1f}  "
                      f"{p['phase_rad']:11.4f}  {p['phase_std']:6.4f}")

            all_results[rkey] = {
                "plate_name": name,
                "plate_id": pid,
                "relay_ch": relay_ch,
                "rx_path": rx_label,
                "sweep_data": sweep_data,
                "peaks": peaks,
                "stats": stats,
            }

    # Cleanup
    mux.off()
    _close_scope(handle)

    elapsed = time.time() - t_start

    # Cross-plate comparison (iterate over all result keys)
    result_keys = sorted(all_results.keys())
    print(f"\n{'=' * 70}")
    print(f"  MODE CENSUS SUMMARY — {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"{'=' * 70}")
    print(f"  {'Key':<8} {'Plate':<6} {'RX':<4} {'Modes':<7} {'Range (kHz)':<16} "
          f"{'Density (/kHz)':<15} {'Min Δf (Hz)':<12} {'Top Mode (kHz)'}")
    print(f"  {'─'*8} {'─'*6} {'─'*4} {'─'*7} {'─'*16} {'─'*15} {'─'*12} {'─'*15}")

    for rkey in result_keys:
        r = all_results[rkey]
        s = r["stats"]
        top = r["peaks"][0]["freq_hz"] / 1000 if r["peaks"] else 0
        n = s["n_modes"]
        flo = s.get("freq_min_hz", 0) / 1000
        fhi = s.get("freq_max_hz", 0) / 1000
        density = s.get("modes_per_khz", 0)
        min_df = s.get("min_spacing_hz", 0)
        print(f"  {rkey:<8} {r['plate_name']:<6} {r['rx_path']:<4} {n:<7} "
              f"{flo:5.1f}–{fhi:5.1f} kHz  "
              f"{density:<15.1f} {min_df:<12.0f} {top:5.1f}")

    # Shared mode frequency analysis (use NE-RX per plate for cross-plate comparison)
    print(f"\n  Common mode frequencies (within ±50 Hz across plates, NE-RX):")
    ne_keys = [rkey for rkey in result_keys
               if all_results[rkey]["rx_path"] == "NE"]
    all_peak_freqs = {}
    for rkey in ne_keys:
        pid = all_results[rkey]["plate_id"]
        for p in all_results[rkey]["peaks"]:
            all_peak_freqs.setdefault(pid, []).append(p["freq_hz"])

    # Find frequencies that appear in 3+ plates
    ref_plate = PLATE_IDS[0]
    shared = []
    for f_ref in all_peak_freqs.get(ref_plate, []):
        count = 1
        matches = [f_ref]
        for pid in PLATE_IDS[1:]:
            for f_other in all_peak_freqs.get(pid, []):
                if abs(f_other - f_ref) <= 50:
                    count += 1
                    matches.append(f_other)
                    break
        if count >= 3:
            shared.append((round(float(np.mean(matches)), 1), count))

    shared.sort(key=lambda x: -x[1])
    for freq, cnt in shared[:15]:
        print(f"    {freq:8.1f} Hz — appears in {cnt}/{len(PLATE_IDS)} plates")

    print(f"\n  Comparison to rod campaign: rods had 13 modes in 1.8–33.7 kHz")

    # Save
    out_path = RESULTS_DIR / f"plate_census_{TIMESTAMP}.json"
    # Strip full sweep data for summary, save separately
    summary_results = {}
    for rkey, r in all_results.items():
        summary_results[rkey] = {
            "plate_name": r["plate_name"],
            "plate_id": r["plate_id"],
            "relay_ch": r["relay_ch"],
            "rx_path": r["rx_path"],
            "peaks": r["peaks"],
            "stats": r["stats"],
            "sweep_n_points": len(r["sweep_data"]),
        }

    save_data = {
        "experiment": "Phase 1.6 Step 2: Broadband Mode Census (dual-RX)",
        "timestamp": TIMESTAMP,
        "elapsed_s": round(elapsed, 1),
        "config": {
            "f_start": F_START, "f_stop": F_STOP, "f_step": F_STEP,
            "n_avg": N_AVG, "min_snr_db": MIN_SNR_DB,
            "min_prominence_db": MIN_PROMINENCE_DB,
            "plate_relays": {pid: [(ch, rx) for ch, rx in rl]
                             for pid, rl in PLATE_RELAYS.items()},
        },
        "results": summary_results,
    }
    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Summary saved: {out_path}")

    # Also save full sweep data (large file, separate)
    sweep_path = RESULTS_DIR / f"plate_census_sweeps_{TIMESTAMP}.json"
    sweep_save = {}
    for rkey, r in all_results.items():
        sweep_save[rkey] = {
            "plate_name": r["plate_name"],
            "plate_id": r["plate_id"],
            "relay_ch": r["relay_ch"],
            "rx_path": r["rx_path"],
            "sweep_data": r["sweep_data"],
        }
    with open(sweep_path, "w") as f:
        json.dump(sweep_save, f, indent=2, default=str)
    print(f"  Full sweep data: {sweep_path}")

    return save_data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python plate_mode_census.py <serial_port>")
        print("  e.g. python plate_mode_census.py /dev/cu.usbserial-11310")
        sys.exit(1)
    run_mode_census(sys.argv[1])
