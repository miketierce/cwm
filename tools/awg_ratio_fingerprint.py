#!/usr/bin/env python3
"""
AWG resonance-ratio fingerprinting.

For each enrolled rod, drive AWG at each of its enrolled frequencies AND
at midpoint (off-resonance) frequencies. Compute the on/off ratio at each.
If rods have distinct ratio profiles, we can discriminate them even through
feedthrough.

Also: test ALL 4 rods' enrolled frequencies as drive points, measure response
on Ch A (which carries Rods 2,3,4 sense PZTs). A rod whose peaks are
physically present should show higher ratios than a rod that isn't connected
to Ch A.
"""
import ctypes
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from picosdk.ps2000 import ps2000

USERS = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "users.json"
with open(USERS) as f:
    db = json.load(f)

handle = ps2000.ps2000_open_unit()
if handle <= 0:
    print(f"FATAL: handle={handle}")
    sys.exit(1)
print(f"Scope opened (handle={handle})\n")

try:
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B OFF

    def measure_at(freq_hz, n_avg=12, settle_s=0.25):
        """Drive AWG at freq_hz, return avg FFT magnitude at that freq."""
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
        )
        time.sleep(settle_s)
        magnitudes = []
        for _ in range(n_avg):
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
            ov = ctypes.c_int16()
            n = ps2000.ps2000_get_values(
                handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                None, None, ctypes.byref(ov), N_SAMPLES
            )
            if n > 0:
                raw = np.array(buf_a[:n], dtype=np.float64)
                windowed = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft = np.abs(np.fft.rfft(windowed, n=nfft))
                freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bin_hz = freq_axis[1] - freq_axis[0]
                target_bin = int(round(freq_hz / bin_hz))
                lo = max(0, target_bin - 3)
                hi = min(len(fft) - 1, target_bin + 3)
                magnitudes.append(float(np.max(fft[lo:hi + 1])))
        return np.mean(magnitudes) if magnitudes else 0.0

    # Collect enrolled frequencies for all rods
    rods = {}
    for rid in sorted(db["rods"].keys()):
        r = db["rods"][rid]
        if r.get("enrolled"):
            rods[rid] = r["perturbed_hz"][:10]

    print(f"Enrolled rods: {list(rods.keys())}")
    for rid, peaks in rods.items():
        print(f"  Rod {rid}: {[round(f, 1) for f in peaks]}")

    # Build a common set of test frequencies: all rod peaks + midpoints
    all_peaks = set()
    for peaks in rods.values():
        for f in peaks:
            all_peaks.add(round(f, 1))
    all_peaks = sorted(all_peaks)

    # Also build off-resonance references at midpoints between consecutive peaks
    off_freqs = []
    for i in range(len(all_peaks) - 1):
        mid = (all_peaks[i] + all_peaks[i + 1]) / 2
        # Only add if it's not too close to any peak (>3% away)
        too_close = any(abs(mid - p) / p < 0.03 for p in all_peaks)
        if not too_close:
            off_freqs.append(mid)

    print(f"\n{len(all_peaks)} on-resonance freqs, {len(off_freqs)} off-resonance freqs")

    # Measure at all off-resonance points first (baseline transfer function)
    print("\nMeasuring off-resonance baseline...")
    off_mags = {}
    for f in off_freqs:
        mag = measure_at(f, n_avg=8, settle_s=0.15)
        off_mags[f] = mag
        sys.stdout.write(".")
        sys.stdout.flush()
    print()

    # Build interpolated baseline: for any freq, estimate feedthrough from
    # nearest off-resonance measurements
    off_sorted = sorted(off_mags.keys())
    off_vals = [off_mags[f] for f in off_sorted]

    def baseline_at(freq_hz):
        """Interpolate feedthrough baseline at freq_hz."""
        if freq_hz <= off_sorted[0]:
            return off_vals[0]
        if freq_hz >= off_sorted[-1]:
            return off_vals[-1]
        for i in range(len(off_sorted) - 1):
            if off_sorted[i] <= freq_hz <= off_sorted[i + 1]:
                frac = (freq_hz - off_sorted[i]) / (off_sorted[i + 1] - off_sorted[i])
                return off_vals[i] + frac * (off_vals[i + 1] - off_vals[i])
        return off_vals[-1]

    # Measure at each rod's enrolled peaks
    print("\nMeasuring on-resonance for each rod's peaks...")
    rod_ratios = {}  # rod_id -> list of (freq, ratio)
    rod_mags = {}    # rod_id -> list of (freq, on_mag, off_mag, ratio)

    for rid, peaks in rods.items():
        print(f"\n  Rod {rid}:")
        ratios = []
        details = []
        for j, f in enumerate(peaks):
            on_mag = measure_at(f, n_avg=12, settle_s=0.2)
            off_mag = baseline_at(f)
            ratio = on_mag / off_mag if off_mag > 0 else 0
            ratios.append(ratio)
            details.append((f, on_mag, off_mag, ratio))

            marker = "***" if ratio > 2 else "* " if ratio > 1.5 else "  "
            print(f"    f{j+1:2d}={f:8.1f} Hz | on={on_mag:10.0f} off={off_mag:10.0f} | "
                  f"ratio={ratio:5.2f} {marker}")

        rod_ratios[rid] = ratios
        rod_mags[rid] = details
        resonant = sum(1 for r in ratios if r > 1.5)
        strong = sum(1 for r in ratios if r > 2.0)
        print(f"    Summary: {strong} strong (>2x), {resonant} weak (>1.5x) "
              f"resonances out of {len(peaks)}")

    # Cross-scoring: for each rod, compute the "resonance fingerprint"
    # (ratio profile) when driven at each OTHER rod's peaks
    print("\n\n=== CROSS-ROD DISCRIMINATION ===")
    print("Drive at Rod X's peaks, measure on Ch A, compute ratio profile.")
    print("Ch A carries Rods 2,3,4. Rod 1 is on Ch B (disabled).")
    print()

    # For each rod's enrolled peaks, we already have the on-resonance measurement.
    # Now measure at OTHER rods' peaks to see if they respond differently.
    cross_matrix = {}  # (test_rod, driven_peaks_rod) -> mean_ratio

    for driven_rid, driven_peaks in rods.items():
        # We already measured these — they're in rod_mags
        pass

    # The ratio profiles we already have tell the story:
    # When driving at Rod X's peaks, how does Ch A respond?
    # If Rod X is physically on Ch A, its ratios should be higher.
    print("Rod   | Mean Ratio | Max Ratio | >1.5x | >2x | Note")
    print("------|------------|-----------|-------|-----|-----")
    for rid in sorted(rods.keys()):
        ratios = rod_ratios[rid]
        mean_r = np.mean(ratios)
        max_r = np.max(ratios)
        n_15 = sum(1 for r in ratios if r > 1.5)
        n_20 = sum(1 for r in ratios if r > 2.0)
        on_chA = "Ch A (sense)" if rid in ["2", "3", "4"] else "Ch B (disabled)"
        print(f"Rod {rid} | {mean_r:10.2f} | {max_r:9.2f} | {n_15:5d} | {n_20:3d} | {on_chA}")

    # Key question: do Rods 2,3,4 (on Ch A) show HIGHER ratios than Rod 1
    # (on Ch B, which is disabled)?
    chA_ratios = []
    chB_ratios = []
    for rid, ratios in rod_ratios.items():
        if rid in ["2", "3", "4"]:
            chA_ratios.extend(ratios)
        else:
            chB_ratios.extend(ratios)

    print(f"\nCh A rods (2,3,4) mean ratio: {np.mean(chA_ratios):.3f}")
    print(f"Ch B rod (1) mean ratio:      {np.mean(chB_ratios):.3f}")

    if np.mean(chA_ratios) > np.mean(chB_ratios) * 1.2:
        print("\n>>> Ch A rods show MORE resonance than Ch B rod — mechanical signal detected!")
        print("    The ratio profile may be usable as a fingerprint.")
    elif np.mean(chA_ratios) > np.mean(chB_ratios):
        print("\n>>> Slight difference — borderline mechanical signal.")
    else:
        print("\n>>> No channel difference — feedthrough dominates all rods equally.")

    # Within Ch A rods: can we tell Rod 2 from Rod 3 from Rod 4?
    print("\n\n=== INTER-ROD DISCRIMINATION (Ch A only) ===")
    for rid in ["2", "3", "4"]:
        if rid not in rod_ratios:
            continue
        ratios = rod_ratios[rid]
        best_idx = np.argmax(ratios)
        best_f = rods[rid][best_idx]
        print(f"  Rod {rid}: best ratio {ratios[best_idx]:.2f} at f{best_idx+1}={best_f:.1f} Hz")
        print(f"    Full profile: {[round(r, 2) for r in ratios]}")

finally:
    try:
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("\nScope closed.")
