#!/usr/bin/env python3
"""Analyze harmonic ladders and IM landing pads for NARMA-10."""
import json
from itertools import combinations
from random import sample, seed

d = json.load(open("data/results/lab/plate_exps/plate_census_cross_20260418_142222.json"))

# Build deduped cluster list
all_modes = {}
for key in d["results"]:
    for p in d["results"][key]["peaks"]:
        f = p["freq_hz"]
        if f not in all_modes:
            all_modes[f] = {}
        all_modes[f][key] = p["magnitude"]

freqs = sorted(all_modes.keys())
clusters = []
for f in freqs:
    if not clusters or abs(f - clusters[-1]) / max(f, clusters[-1]) > 0.015:
        clusters.append(f)
    else:
        if max(all_modes[f].values()) > max(all_modes.get(clusters[-1], {0: 0}).values()):
            clusters[-1] = f

cluster_set = set(clusters)
print(f"{len(clusters)} frequency clusters")


def im_score(tones, cset, tol=0.02):
    hits = 0
    pairs = 0
    for i in range(len(tones)):
        for j in range(i + 1, len(tones)):
            fi, fj = tones[i], tones[j]
            for im in [fi + fj, fj - fi]:
                pairs += 1
                for cf in cset:
                    if abs(im - cf) / max(im, cf) < tol:
                        hits += 1
                        break
    return hits, pairs


# Highlight major ladders
print("\n=== Major harmonic ladders ===")
for name, ladder in [
    ("11.4k", [11425, 34550, 45000, 56200, 68200, 78800, 89400]),
    ("16.0k", [16000, 31600, 47800, 65100, 78800, 95000]),
    ("15.1k", [15100, 29900, 45000, 62000, 73500, 89400]),
    ("19.0k", [19000, 37000, 56200, 76200, 95000]),
    ("23.9k", [23900, 47800, 70800, 95000]),
]:
    h, t = im_score(ladder, cluster_set)
    print(f"  {name} base ({len(ladder)} tones): {h}/{t} IM hits ({h/t*100:.0f}%)")

# Candidate 10-tone sets
print("\n=== Candidate 10-tone sets ===")
candidates = {
    "11.4k ladder + strong fills": [11425, 19000, 29200, 34550, 45000, 49600, 56200, 68200, 78800, 89400],
    "multi-ladder spread": [11425, 16000, 23900, 34550, 45000, 47800, 58500, 68200, 78800, 89400],
    "max multi-rx modes": [19000, 23900, 29900, 37000, 45000, 49600, 51500, 58500, 70800, 78800],
    "11.4k+15.1k interlocked": [11425, 15100, 29900, 34550, 45000, 56200, 62000, 73500, 78800, 89400],
}
for name, tones in candidates.items():
    h, t = im_score(tones, cluster_set)
    n_rx_total = sum(len(all_modes.get(f, {})) for f in tones)
    print(f"  {name}: {h}/{t} IM hits ({h/t*100:.0f}%), rx_coverage={n_rx_total}")

# Random search over strong modes
strong = [19000, 23900, 29200, 29900, 34550, 37000, 45000, 47800, 49600,
          51500, 56200, 58500, 68200, 70800, 78800, 86900, 89400]
best_score = 0
best_set = None
seed(42)
for _ in range(100000):
    s = sorted(sample(strong, 10))
    h, t = im_score(s, cluster_set)
    if h > best_score:
        best_score = h
        best_set = s

print(f"\n  Best of 100k random (strong modes): {best_score}/{t} IM hits ({best_score/t*100:.0f}%)")
print(f"    Tones: {[f/1000 for f in best_set]}k")

# Also search including weaker modes for ladder coverage
all_strong = sorted(cluster_set)
best2_score = 0
best2_set = None
seed(123)
for _ in range(100000):
    s = sorted(sample(all_strong, min(10, len(all_strong))))
    h, t = im_score(s, cluster_set)
    if h > best2_score:
        best2_score = h
        best2_set = s

print(f"  Best of 100k random (all clusters): {best2_score}/{t} IM hits ({best2_score/t*100:.0f}%)")
print(f"    Tones: {[f/1000 for f in best2_set]}k")
