#!/usr/bin/env python3
"""Quick analysis of flash census results."""
import json
import numpy as np
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "data/results/lab/plate_exps/plate_census_kronos_flash_20260415_211405.json"

with open(path) as f:
    data = json.load(f)

print("=" * 70)
print("  FULL CENSUS RESULTS — MODE INVENTORY")
print("=" * 70)
print()

plate_modes = {}
plate_freqs = {}
plate_mags = {}

results = data["results"]
for key in results:
    entry = results[key]
    plate = entry["plate_name"]
    rx = entry["rx_path"]
    modes = entry["peaks"]
    n = len(modes)
    freqs = [m["freq_hz"] for m in modes]
    mags = [m["magnitude"] for m in modes]
    snrs = [m["snr_db"] for m in modes]

    label = f"{plate}_{rx}"
    plate_modes[label] = set(freqs)
    plate_freqs[label] = freqs
    plate_mags[label] = mags

    print(f"  Plate {plate} ({rx}): {n} modes, {min(freqs):.0f}–{max(freqs):.0f} Hz")
    print(f"    Top 5 freqs: {', '.join(f'{f:.0f} Hz' for f in freqs[:5])}")
    print(f"    Mean SNR: {np.mean(snrs):.1f} dB, Max SNR: {max(snrs):.1f} dB")
    print(f"    Mean mag: {np.mean(mags):.4f}, Max mag: {max(mags):.4f}")
    print()

# Cross-plate uniqueness
print("=" * 70)
print("  CROSS-PLATE MODE UNIQUENESS")
print("=" * 70)
print()

labels = list(plate_modes.keys())
header = f"  {'Label':<12} {'Modes':>5}  {'Unique':>6}  {'% Unique':>8}  {'Shared':>6}"
print(header)
print("  " + "-" * 50)

for i, lab in enumerate(labels):
    s = plate_modes[lab]
    others = set()
    for j, olab in enumerate(labels):
        if i != j:
            others |= plate_modes[olab]
    unique = s - others
    shared = s & others
    pct = 100 * len(unique) / len(s) if len(s) > 0 else 0
    print(f"  {lab:<12} {len(s):>5}  {len(unique):>6}  {pct:>7.1f}%  {len(shared):>6}")

# Pairwise Jaccard
print()
print("=" * 70)
print("  PAIRWISE JACCARD SIMILARITY (mode frequency overlap)")
print("=" * 70)
print()

# Compact labels
short = [l.replace("RX-", "") for l in labels]
print(f"  {'':>12}", end="")
for s in short:
    print(f" {s:>8}", end="")
print()

for i, lab_i in enumerate(labels):
    print(f"  {short[i]:>12}", end="")
    for j, lab_j in enumerate(labels):
        si = plate_modes[lab_i]
        sj = plate_modes[lab_j]
        jacc = len(si & sj) / len(si | sj) if len(si | sj) > 0 else 0
        print(f" {jacc:>8.3f}", end="")
    print()

# Same-plate NE vs NW
print()
print("=" * 70)
print("  SAME-PLATE NE vs NW (dual-PZT plates G, D, H)")
print("=" * 70)
print()

dual_plates = ["G", "D", "H"]
for p in dual_plates:
    ne_key = f"{p}_RX-NE"
    nw_key = f"{p}_RX-NW"
    if ne_key in plate_modes and nw_key in plate_modes:
        ne = plate_modes[ne_key]
        nw = plate_modes[nw_key]
        shared = ne & nw
        jacc = len(shared) / len(ne | nw) if len(ne | nw) else 0
        print(f"  Plate {p}: NE={len(ne)} modes, NW={len(nw)} modes")
        print(f"    Shared: {len(shared)}, NE-only: {len(ne - nw)}, NW-only: {len(nw - ne)}")
        print(f"    Jaccard: {jacc:.3f}")
        print()

# 6700 Hz mode across all plates (appears to be dominant everywhere)
print("=" * 70)
print("  6700 Hz MODE ACROSS ALL PLATES")
print("=" * 70)
print()
print(f"  {'Label':<12} {'Magnitude':>10} {'SNR (dB)':>10} {'Phase':>10}")
print("  " + "-" * 45)

for key in data["results"]:
    entry = data["results"][key]
    plate = entry["plate_name"]
    rx = entry["rx_path"]
    label = f"{plate}_{rx}"
    for m in entry["peaks"]:
        if m["freq_hz"] == 6700.0:
            print(f"  {label:<12} {m['magnitude']:>10.4f} {m['snr_db']:>10.1f} {m['phase_rad']:>10.4f}")
            break

# Total mode count
total = sum(len(plate_modes[l]) for l in labels)
all_freqs = set()
for l in labels:
    all_freqs |= plate_modes[l]
print()
print(f"  Total mode observations: {total}")
print(f"  Unique frequencies across all plates: {len(all_freqs)}")
print(f"  Average modes per relay: {total / len(labels):.0f}")
print()

# Mode density comparison
print("=" * 70)
print("  MODE DENSITY RANKING")
print("=" * 70)
print()
densities = []
for key in data["results"]:
    entry = data["results"][key]
    plate = entry["plate_name"]
    rx = entry["rx_path"]
    label = f"{plate}_{rx}"
    freqs = sorted([m["freq_hz"] for m in entry["peaks"]])
    if len(freqs) >= 2:
        bw = (freqs[-1] - freqs[0]) / 1000  # kHz
        density = len(freqs) / bw if bw > 0 else 0
        densities.append((label, len(freqs), density, bw))

densities.sort(key=lambda x: -x[2])
print(f"  {'Label':<12} {'Modes':>5} {'Density':>10} {'BW (kHz)':>10}")
print("  " + "-" * 40)
for label, n, d, bw in densities:
    print(f"  {label:<12} {n:>5} {d:>9.1f}/kHz {bw:>9.1f}")
