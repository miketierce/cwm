#!/usr/bin/env python3
"""
Fast PicoScope-only census: 100 Hz steps, 2 averages.
~25 min for all 8 relay paths (vs 3.2h at default 25 Hz / 4 avg).

Also saves sweep data for full spectral analysis.
"""
import sys, time, json
from pathlib import Path
from datetime import datetime

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

# Override the slow defaults BEFORE importing
import plate_mode_census as census
census.F_STEP = 100       # 100 Hz steps (4× faster than 25 Hz)
census.N_AVG = 2          # 2 averages (vs 4)
census.SETTLE_S = 0.03    # slightly faster settle

# Re-run with modified parameters
if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-11310"

    n_points = (census.F_STOP - census.F_START) // census.F_STEP
    est_per_relay = n_points * (census.SETTLE_S + 0.04) * census.N_AVG
    est_total = est_per_relay * 8

    print(f"Fast PicoScope Census")
    print(f"  {census.F_START}–{census.F_STOP} Hz, {census.F_STEP} Hz steps ({n_points} pts)")
    print(f"  {census.N_AVG} averages, {census.SETTLE_S}s settle")
    print(f"  Estimated: {est_per_relay:.0f}s/relay, {est_total:.0f}s total (~{est_total/60:.0f} min)")
    print()

    result = census.run_mode_census(port)
    print(f"\nDone. Results in data/results/lab/plate_exps/")
