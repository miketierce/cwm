#!/usr/bin/env python3
"""
AWG ratio-profile identification: can we tell which rod is which
by driving at each rod's enrolled peaks and measuring resonance ratios?

Strategy:
  1. Measure feedthrough baseline at off-resonance frequencies
  2. For each candidate rod C, drive at C's enrolled peaks and measure ratios
  3. The ACTUAL rod present should show ratio > 1 at its own peaks
     and ratio ≈ 1 at other rods' peaks (feedthrough only)
  4. Score: sum(ratio - 1) for peaks that belong to each rod

This is a CROSS-SCORING matrix: for each set of driven frequencies,
which rod's enrolled peaks show the most resonance?
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
    sys.exit(f"FATAL: handle={handle}")
print(f"Scope opened (handle={handle})\n")

try:
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)

    def measure_at(freq_hz, n_avg=12, settle_s=0.2):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, AWG_DRIVE_UVPP, 0,
            float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
        )
        time.sleep(settle_s)
        mags = []
        for _ in range(n_avg):
            ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
            t_ms = ctypes.c_int32()
            ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
            t0 = time.time()
            while ps2000.ps2000_ready(handle) == 0:
                time.sleep(0.002)
                if time.time() - t0 > 2:
                    break
            a = (ctypes.c_int16 * N_SAMPLES)()
            b = (ctypes.c_int16 * N_SAMPLES)()
            ov = ctypes.c_int16()
            n = ps2000.ps2000_get_values(handle, ctypes.byref(a), ctypes.byref(b),
                                          None, None, ctypes.byref(ov), N_SAMPLES)
            if n > 0:
                raw = np.array(a[:n], dtype=np.float64)
                w = raw * np.hanning(len(raw))
                nfft = len(raw) * 4
                fft = np.abs(np.fft.rfft(w, n=nfft))
                freq_ax = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
                bh = freq_ax[1]
                tb = int(round(freq_hz / bh))
                lo = max(0, tb - 3)
                hi = min(len(fft) - 1, tb + 3)
                mags.append(float(np.max(fft[lo:hi + 1])))
        return np.mean(mags) if mags else 0.0

    # Get all enrolled rods
    rods = {}
    for rid in sorted(db["rods"].keys()):
        r = db["rods"][rid]
        if r.get("enrolled"):
            rods[rid] = r["perturbed_hz"][:10]

    # Collect ALL unique peak frequencies across all rods
    all_freqs = {}
    for rid, peaks in rods.items():
        for j, f in enumerate(peaks):
            all_freqs[f] = (rid, j)
    unique_freqs = sorted(all_freqs.keys())

    # Build off-resonance baseline
    print("Building feedthrough baseline...")
    off_points = []
    for i in range(len(unique_freqs) - 1):
        mid = (unique_freqs[i] + unique_freqs[i + 1]) / 2
        too_close = any(abs(mid - f) / f < 0.03 for f in unique_freqs)
        if not too_close:
            off_points.append(mid)

    # Add some reference points at extremes
    off_points = [500.0] + off_points + [15000.0]
    off_mags = {}
    for f in off_points:
        off_mags[f] = measure_at(f, n_avg=8, settle_s=0.15)
        sys.stdout.write(".")
        sys.stdout.flush()
    print(f" ({len(off_mags)} points)")

    off_sorted = sorted(off_mags.keys())
    off_vals = [off_mags[f] for f in off_sorted]

    def baseline(freq_hz):
        if freq_hz <= off_sorted[0]:
            return off_vals[0]
        if freq_hz >= off_sorted[-1]:
            return off_vals[-1]
        for i in range(len(off_sorted) - 1):
            if off_sorted[i] <= freq_hz <= off_sorted[i + 1]:
                frac = (freq_hz - off_sorted[i]) / (off_sorted[i + 1] - off_sorted[i])
                return off_vals[i] + frac * (off_vals[i + 1] - off_vals[i])
        return off_vals[-1]

    # Measure at EVERY enrolled frequency
    print("\nMeasuring at all enrolled frequencies...")
    on_mags = {}
    for f in unique_freqs:
        on_mags[f] = measure_at(f, n_avg=12, settle_s=0.2)
        rid, j = all_freqs[f]
        bl = baseline(f)
        ratio = on_mags[f] / bl if bl > 0 else 0
        marker = "***" if ratio > 2 else "* " if ratio > 1.5 else ""
        print(f"  {f:8.1f} Hz (Rod {rid} f{j+1:2d}) | ratio={ratio:5.2f} {marker}")

    # Build the cross-scoring matrix
    print("\n\n========================================")
    print("  CROSS-SCORING IDENTIFICATION MATRIX")
    print("========================================")
    print("\nFor each rod, sum the resonance ratios at its OWN enrolled peaks.")
    print("The rod with the highest sum at a frequency set = best match.\n")

    # For each "query" rod (the rod whose peaks we use as drive freqs),
    # score all rods by their resonance at those drive freqs
    header = "Query Rod |"
    for rid in sorted(rods.keys()):
        header += f" Rod {rid} score |"
    header += " Winner"
    print(header)
    print("-" * len(header))

    winners = []
    for query_rid in sorted(rods.keys()):
        query_peaks = rods[query_rid]
        scores = {}
        for target_rid in sorted(rods.keys()):
            target_peaks = rods[target_rid]
            # For each target peak, find if it's close to any query peak
            # and if so, what's its ratio
            total_ratio = 0.0
            n_close = 0
            for tf in target_peaks:
                # Find nearest query peak
                nearest_qf = min(query_peaks, key=lambda qf: abs(qf - tf))
                if abs(nearest_qf - tf) / tf < 0.05:
                    # This target peak is near a query peak
                    bl = baseline(nearest_qf)
                    ratio = on_mags.get(nearest_qf, 0) / bl if bl > 0 else 0
                    total_ratio += max(ratio - 1, 0)
                    n_close += 1
            scores[target_rid] = total_ratio

        winner = max(scores, key=scores.get)
        winners.append(winner == query_rid)
        row = f"  Rod {query_rid}    |"
        for tid in sorted(rods.keys()):
            sc = scores[tid]
            mark = " <<" if tid == winner else ""
            row += f"     {sc:5.2f}{mark}  |"
        row += f"  Rod {winner}" + (" ✓" if winner == query_rid else " ✗")
        print(row)

    print(f"\nCorrect: {sum(winners)}/{len(winners)}")

    # Alternative scoring: just use the sum of ratios at each rod's own peaks
    print("\n\n========================================")
    print("  DIRECT RATIO-SUM IDENTIFICATION")
    print("========================================")
    print("\nDrive at ALL 40 enrolled frequencies. For each rod, sum ratios")
    print("at its own peaks. Highest sum = most resonant rod.\n")

    rod_scores = {}
    for rid, peaks in rods.items():
        total = 0.0
        detail = []
        for f in peaks:
            bl = baseline(f)
            ratio = on_mags.get(f, 0) / bl if bl > 0 else 0
            total += max(ratio - 1, 0)
            detail.append(ratio)
        rod_scores[rid] = total
        print(f"  Rod {rid}: sum(ratio-1)={total:6.2f}  "
              f"profile=[{', '.join(f'{r:.2f}' for r in detail)}]")

    winner = max(rod_scores, key=rod_scores.get)
    print(f"\n  Winner: Rod {winner} (highest resonance sum)")
    print(f"  Ch A rods: {', '.join(f'Rod {r}={rod_scores[r]:.2f}' for r in ['2', '3', '4'])}")
    print(f"  Ch B rod:  Rod 1={rod_scores['1']:.2f}")

    # Can we discriminate BETWEEN Ch A rods?
    print("\n\n========================================")
    print("  PAIRWISE DISCRIMINATION (Ch A rods)")
    print("========================================\n")

    for r1 in ["2", "3", "4"]:
        for r2 in ["2", "3", "4"]:
            if r1 >= r2:
                continue
            # Drive at Rod r1's peaks: what ratio does Rod r2 see?
            p1 = rods[r1]
            p2 = rods[r2]

            # Rod r1's peaks: ratios
            r1_sum = sum(max(on_mags.get(f, 0) / baseline(f) - 1, 0)
                         for f in p1 if baseline(f) > 0)
            # Rod r2's peaks: ratios
            r2_sum = sum(max(on_mags.get(f, 0) / baseline(f) - 1, 0)
                         for f in p2 if baseline(f) > 0)

            # How many of r1's peaks are near r2's peaks?
            overlap = 0
            for f1 in p1:
                for f2 in p2:
                    if abs(f1 - f2) / f1 < 0.05:
                        overlap += 1
                        break

            print(f"  Rod {r1} vs Rod {r2}: "
                  f"scores={r1_sum:.2f} vs {r2_sum:.2f}, "
                  f"overlap={overlap}/10, "
                  f"separable={'YES' if abs(r1_sum - r2_sum) > 1.0 else 'MARGINAL' if abs(r1_sum - r2_sum) > 0.3 else 'NO'}")

finally:
    try:
        ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("\nScope closed.")
