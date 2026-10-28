#!/usr/bin/env python3
"""Exact-harmonic grid for the Oct 28 pilot (preregistered in docs/lab_diary_20261028.md section 5).

NCO periods are whole 126 MHz clock cycles. A drive whose period P divides by n has its n-th harmonic exactly on
the NCO frequency of the command n*d, since round(C/(n*d)) = P/n. So:
  - each FT-1 drive point f0 in 30-40 kHz moves to the nearest command d whose period divides by 6 (2f and 3f),
    and each in 40.5-60 kHz to the nearest whose period divides by 2 (2f only);
  - the targets 2d (and 3d below 40 kHz) replace the FT-1 points within 250 Hz of them;
  - every other FT-1 point in 60-120 kHz stays.
The frozen FT-1 superposition rule (H at the grid point n*d predicts the harmonic of the drive at d) then compares
identical frequencies at every point. Writes xgrid_pilot.json in the capture tool's grid format.

    python3 data/results/k_eff/xgrid_20261028/make_grid.py
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

C = 126_000_000
OUT = Path(__file__).resolve().parent / 'xgrid_pilot.json'


def period(f: int) -> int:
    return round(C / f)


def main():
    base = list(range(30_000, 120_001, 500))
    drives, targets = {}, {}
    for f0 in range(30_000, 60_001, 500):
        k = 6 if f0 <= 40_000 else 2
        d = round(C / (k * round(C / f0 / k)))
        assert period(d) % k == 0
        drives[f0] = d
        for n in ((2, 3) if f0 <= 40_000 else (2,)):
            assert period(n * d) * n == period(d), (f0, d, n)
            targets[n * d] = (n, d)
    grid = set(drives.values()) | set(targets)
    grid |= {g for g in base if g > 60_000 and all(abs(g - t) >= 250 for t in targets)}
    grid = sorted(grid)
    # every drive's harmonic and its target's own NCO frequency agree exactly (in whole clock periods)
    assert all(C * n / period(d) == C / period(n * d) for n, d in targets.values())
    frozen = {'spec': 'exact-harmonic pilot: FT-1 30-60 kHz drives moved to periods divisible by 6 (<=40 kHz) or 2; '
                      'targets 2d, 3d replace FT-1 points within 250 Hz', 'freqs_hz': grid, 'n': len(grid),
              'sha256': hashlib.sha256(json.dumps(grid).encode()).hexdigest(),
              'frozen_utc': datetime.now(timezone.utc).isoformat()}
    OUT.write_text(json.dumps(frozen, indent=1) + '\n')
    nudge = [abs(C / period(d) - C / period(f0)) for f0, d in drives.items()]
    print(f"{len(grid)} points; {len(drives)} drives moved by at most {max(nudge):.1f} Hz (median {sorted(nudge)[len(nudge) // 2]:.1f}); "
          f"{len(targets)} exact targets; sha256 {frozen['sha256'][:16]}")


if __name__ == '__main__':
    main()
