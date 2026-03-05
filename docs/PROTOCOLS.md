# Experiment Protocols

This document describes the standard protocols for running WCFOMA experiments, both computational and (future) physical.

---

## Computational Experiment Protocol

### Before Running

1. Ensure dependencies are installed: `pip install -r requirements.txt`
2. Review the experiment's docstring for:
   - Research question
   - Hypothesis
   - Methodology
   - Claims being tested
   - Current status (SIMULATED / DEMONSTRATED)

### Running an Experiment

```bash
# Run individual experiment
python -m experiments.exp01_mode_persistence

# Or use the Jupyter notebooks for interactive exploration
jupyter lab notebooks/
```

### Recording Results

Every experiment run should produce:

1. **Console summary** — Pass/fail against paper claims
2. **Data export** — CSV/JSON in `data/results/`
3. **Figures** — Saved to `analysis/figures/`
4. **Claims table update** — Update `analysis/comparison.py` with measured values

### Result Categories

| Category         | Meaning                                                           |
| ---------------- | ----------------------------------------------------------------- |
| **CONFIRMED**    | Measured value within 20% of paper claim                          |
| **PLAUSIBLE**    | Measured value within 50% of paper claim; needs better resolution |
| **INCONCLUSIVE** | Measurement uncertainty too large to decide                       |
| **REFUTED**      | Measured value outside paper claim by > 50%, reproducibly         |

---

## Future Physical Experiment Protocol (Phase 2+)

### Lab Safety

- Ferrofluid stains permanently — wear gloves and use containment trays
- Shear-thickening fluids can jam unexpectedly — use controlled dispensing
- Laser safety: Class 2 or below for initial Faraday rotation readout
- Standard electronics safety for coil drivers

### Measurement Standards

- Temperature controlled to ±0.5 K during measurement
- Vibration-isolated optical bench for Faraday rotation
- At least 5 repeat measurements per data point
- Calibration against known cavity (air-filled, calculated Q)

### Data Management

- Raw data in `data/raw/YYYY-MM-DD_expNN/`
- Processed data in `data/results/`
- Lab notebook entries in `data/lab_notes/`
- Photos/videos in `data/media/`
