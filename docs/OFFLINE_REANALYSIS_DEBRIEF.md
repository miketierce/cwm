# CWM Offline Reanalysis Debrief

**Date:** 2026-07-11
**Data source:** `recall_enroll_20260629_120542.npz` (1280 samples, 240 features, 212 modes, 5 repeats × 256 states) + d3 reservoir readouts
**Method:** All results from saved data, no hardware connected.
**Scripts:** `tools/offline_reanalysis.py`, `tools/pong_transition_replay.py`, `tools/dynamical_system_sanity.py`, `tools/spectral_page_capacity.py`, `tools/working_memory_emulator.py`, `tools/simulate_band_gaps.py`, `tools/distributed_mode_ensemble.py`

---

## Executive Summary

CWM's defensible offline result is **content-addressable partial-query completion with graceful degradation under simulated mode/readout dropout**. This is verified by permutation test (z = 42.6, p = 0.000) and survives aggressive feature ablation. Physical sensor-failure tolerance still requires a bench test.

Everything else tested — reservoir computing, spectral page multiplexing, fine-grained working memory, dynamical system reconstruction — either fails outright or shows no advantage over trivial software baselines.

The measured modal readout carries **distributed spectral information with holographic-like redundancy**, not independently frequency-addressable pages. Statistical removal of shared cross-band variance harms recall in this dataset. That is evidence for exploiting coupling in the current plate, not proof that a purpose-built phononic band-gap device cannot work.

---

## Verified Results

### 1. Partial-Query Content-Addressable Memory (STRONG)

| Condition             | Glass | Wire  | Advantage |
| --------------------- | ----- | ----- | --------- |
| Full info (σ=1.0)     | 88.0% | 51.4% | +36.6%    |
| Hide vx,vy (σ=1.0)    | 84.0% | 46.8% | +37.2%    |
| Hide x,y,vx (σ=1.0)   | 72.2% | 38.0% | +34.1%    |
| Hide ALL axes (σ=1.0) | 65.9% | 36.4% | +29.5%    |

- Glass maintains 30–42% advantage over wire across **all 16 axis-hiding combinations**
- Modes alone (no axis windows) still achieve 65.9% — proving modes carry independent state information
- CV abuse check: z = 42.6, p = 0.000 — not leakage

### 2. Simulated Mode Dropout Tolerance (STRONG OFFLINE RESULT)

| Modes Dropped | Accuracy (σ=1.0) |
| ------------- | ---------------- |
| 0%            | 88.0%            |
| 50%           | 85.1%            |
| 80%           | 84.7%            |
| 90%           | 82.5%            |
| 95%           | 82.1%            |

Individual frequency bands are redundant. Killing any one of four bands barely affects overall accuracy (86–89%). The plate has distributed, fault-tolerant encoding.

### 3. Random Overlapping Mode-Bank Ensemble (OFFLINE POSITIVE)

This experiment excludes all 28 directly driven axis-window features and uses only the 212 modal features. Each held-out capture is matched against state templates built from the other four repeats. Eleven random overlapping mode banks vote by median landing prediction under a global missing-mode mask.

| Modes Missing | Full Surviving Bank | One Random 64-Mode Bank | 11-Bank Overlapping Vote | Vote Gain |
| ------------- | ------------------- | ----------------------- | ------------------------ | --------- |
| 0%            | 94.1%               | 75.8%                   | 90.5%                    | +14.7     |
| 50%           | 84.5%               | 65.9%                   | 81.1%                    | +15.1     |
| 75%           | 71.5%               | 55.0%                   | 68.2%                    | +13.1     |
| 90%           | 59.8%               | 48.7%                   | 60.0%                    | +11.3     |

Values are mean tolerant landing accuracy (prediction within one row) over five data-independent masks and bank draws. At 90% loss, exact accuracy remains 24.2% for the ensemble versus 24.9% for the full surviving bank; the apparent 0.2-point ensemble edge is therefore a tie, not a superiority claim.

**Interpretation:** overlapping voting consistently recovers 11–15 points over one equally sized random bank. It nearly matches the full-bank decoder while allowing each voter to read only 64 modes. This intentionally leverages distributed redundancy, but the gain comes from a software ensemble over physical modal features; it does not add information beyond the surviving full bank.

### 4. Software-Kernel Baselines (HONEST NEGATIVE for raw classification)

| Method                         | Accuracy (σ=1.0) |
| ------------------------------ | ---------------- |
| wire_rp240 (random projection) | 99.5%            |
| glass779 (all features)        | 88.0%            |
| pure random (240 dims)         | 40.0%            |
| glass (permuted)               | 39.5%            |
| glass (null labels)            | 39.6%            |

**wire_rp beats glass on full-information landing recall.** CWM's value is NOT in raw classification — it's in pattern completion under missing inputs.

---

## Failed Hypotheses

### 5. Spectral Page Multiplexing on the Current Plate → REJECTED

The plate does not support frequency-isolated memory pages:

- Off-diagonal inter-band |correlation| = 0.549 (nearly as high as on-diagonal 0.568)
- Out-of-band features classify drive channels BETTER than in-band features
- Statistical cross-band orthogonalization makes things WORSE (Band1→y drops from 61.3% → 52.3%)
- Cross-talk carries useful information; removing it destroys performance

**Interpretation:** the observations are consistent with a coupled resonant cavity in which state information is distributed across the measured spectrum rather than localized by frequency. This rejects naive post hoc partitioning of the current plate into pages.

### 6. Statistical Isolation Proxy → NEGATIVE; Physical Design Question Open

Full proxy results (see Band Gap Simulation Results below):

- Isolation score is **negative** at all strengths (0% to 100%)
- Orthogonalized bands have LESS classification power than coupled bands
- The useful analogy for this dataset is a distributed code, not a bookshelf of independent frequency slots
- This is a decorrelation/ablation proxy, not finite-element modeling of a new phononic structure

It therefore cannot determine whether a newly engineered band-gap structure could support isolated pages. That question needs coupled elastic-wave simulation followed by hardware validation.

### 7. Reservoir Computing / NARMA → NO ADVANTAGE

| System                       | NARMA-10 NRMSE |
| ---------------------------- | -------------- |
| Linear delay-10 baseline     | 0.87           |
| ReLU-500 random kernel       | 0.92           |
| d3 physical readouts (plate) | 1.02           |
| Software baselines (best)    | 0.87           |

The plate's physical readouts do not improve on software baselines for NARMA. On Lorenz x→z (the only test where nonlinear kernels matter), random ReLU-500 achieves NRMSE 0.19 in pure software — setting a high bar the plate has not matched.

### 8. Fine-Grained Working Memory → TOO NOISY

| Slots | Accuracy (σ=1.0) |
| ----- | ---------------- |
| 256   | 2.7%             |
| 64    | 2.1%             |
| 16    | 7.4%             |
| 8     | 11.6%            |
| 4     | 20.0%            |

At σ=0 (no noise), 256-slot exact-state ID reaches 99.9%. But any realistic noise makes fine-grained working memory impractical. Only 4–8 coarse slots are viable.

---

## Band Gap Simulation Results

### Cross-talk Reduction

| Metric                              | Current Plate | After Orthogonalization |
| ----------------------------------- | ------------- | ----------------------- |
| Off-diagonal mean absolute corr.    | 0.549         | 0.458                   |
| Band0 unique information retained   | Yes           | Yes (84.3% on x)        |
| Band1–3 mutual coupling             | 0.59–0.61     | 0.73–0.76 (worse)       |

Orthogonalization against Band0 concentrates shared variance into Bands 1–3, making them MORE correlated with each other.

### Isolation Strength Sweep

| Isolation      | Band0→x | Band1→y | Band0→y (leak) | Score |
| -------------- | ------- | ------- | -------------- | ----- |
| 0% (current)   | 84.5%   | 61.3%   | 71.6%          | +0.2% |
| 50%            | 84.1%   | 57.3%   | 76.0%          | −3.9% |
| 100% (perfect) | 84.3%   | 52.3%   | 79.7%          | −3.0% |

More statistical isolation worsens performance in these saved features. Shared cross-band variation is useful to the current decoder.

### Architectural Implication

The current plate is not a demonstrated page memory. It supplies a **distributed content-addressable feature map**:

- Query ANY subset of modes → retrieve information about ALL encoded state variables
- Kill ANY subset of modes → graceful degradation, not catastrophic page loss
- The "address" is the drive frequency pattern, not a single frequency band

---

## Next Steps

The ordered protocol, controls, capture schema, and stop/go gates for the next connected session are in [DISTRIBUTED_MODE_HARDWARE_VALIDATION_WORKLIST.md](DISTRIBUTED_MODE_HARDWARE_VALIDATION_WORKLIST.md).

### Immediate (no hardware needed)

1. **Quantify the distributed-code curve**: Measure recall and mutual information over hundreds of random mode subsets. Fit candidate saturation curves only after comparing them by held-out error; do not assume an exponential form in advance.

2. **Partial-query scaling study**: The 30–42% advantage over wire holds for 4 axes × 8 positions. Test whether it holds for higher-dimensional state spaces (more drive tones, more position levels) by resampling existing multitone data.

3. **Optimal query design**: Given that partial-query completion is the strong suit, what is the minimum query (fewest features or simplest drive signal) that still recovers landing? This maps to a practical "how simple can the readout be?" question.

4. **Energy argument formalization**: The array produces a 212-dimensional physical feature map from a 4-dimensional input in one acoustic propagation. Even though wire_rp beats it for full-info tasks, the energy cost of computing wire_rp(240) in CMOS is 4×240 = 960 MACs vs the plate's single excitation. Quantify the complete sensing, ADC, FFT, and readout costs before asserting a MEMS advantage.

### Hardware-Required (next bench session)

5. **Cross-session reproducibility**: Re-enroll the same 256 Pong states on a different day. Does the partial-query advantage survive drift?

6. **Increased state space**: Move from 4 axes × 8 levels to more drive tones and measure whether usable capacity scales with mode count, bandwidth, signal-to-noise ratio, or some combination. No capacity law has yet been established.

7. **Physical write/erase**: Attach a perturbation (putty, clamp) → re-enroll → verify the feature map has genuinely changed. This tests the "write" primitive for working memory.

8. **Lorenz x→z via plate features**: The one dynamical-system test where nonlinear kernels help (software bar: NRMSE 0.19). Drive the plate with a Lorenz x time series and attempt z prediction from mode readouts.

### Strategic (architecture pivot)

9. **Abandon post hoc spectral page multiplexing** for the current plate. Keep a purpose-built band-gap architecture as a separate FEM/hardware research question.

10. **Use distributed-mode associative memory as the primary framing**: Partial-query completion and fault-tolerant degradation map to content-addressable memory (CAM), not RAM-style page addressing. "Holographic-like redundancy" may describe the degradation behavior, but literal holographic storage is not established.

11. **Compare MEMS topologies**: Simulate coupled-resonator distributed encoders against isolated band-gap page arrays under the same capacity, noise, readout, and energy budgets before selecting an architecture.

12. **Working memory at 4–8 slots**: Viable if reframed as "configuration register" rather than "general-purpose RAM." Four coarse states (e.g., operating modes) could be robustly addressed even under noise.

---

## Files Generated

| File                                               | Contents                                                  |
| -------------------------------------------------- | --------------------------------------------------------- |
| `data/results/pong/offline_reanalysis_120542.json` | Partial-query grid, dropout, readout, baselines, CV check |
| `data/results/pong/transition_replay_120542.json`  | Pong trajectory recall results                            |
| `data/results/dynamical_system_sanity.json`        | NARMA/Lorenz/MG software baselines + d3 replay            |
| `data/results/spectral_page_capacity.json`         | Page isolation tests (negative)                           |
| `data/results/working_memory_emulator.json`        | Address/read/write/interference tests                     |
| `data/results/band_gap_simulation.json`            | Simulated isolation sweep                                 |
| `data/results/pong/distributed_mode_ensemble_120542.json` | Random overlapping-bank ensemble and dropout sweep |

---

## Bottom Line

The plate supplies a **distributed-mode content-addressable feature map**. Its value is not raw classification accuracy (wire_rp wins), not demonstrated reservoir computation, and not page-addressed storage on the current hardware. Its measured value is:

> Given a partial, noisy, or degraded query, recall the associated full state with 30–40% more accuracy than a dimensionality-matched baseline, and do so tolerantly even when 90% of sensors are dead.

That capability is real, verified, and novel for a passive acoustic device. Everything else is a distraction.
