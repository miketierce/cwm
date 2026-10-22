# CWM Neural Dynamical System Benchmark

**Status:** Proposed experiment outline  
**Evidence level:** OPEN / protocol  
**Purpose:** Test whether CWM can support a memristor-comparison style claim: a physical memory / physical kernel substrate that helps reconstruct or forecast a dynamical system under partial, noisy, or missing observations.

This protocol is intentionally skeptical. It does not assume CWM is a compute-in-memory chip. It asks whether the physics already demonstrated in the repository can be organized into a benchmark that is close enough to neural dynamical system reconstruction to justify deeper MEMS-scale work.

## 1. Motivation

Recent external work on phase-change memristor neural-dynamical-system chips highlights a useful comparison point: device-native physical state can act as a computational weight, and dense physical arrays can accelerate iterative dynamical-system reconstruction.

CWM is not a memristor crossbar. The current bench is a classical acoustic / phononic system with macro-scale plates, PZT drive/readout, scope capture, FFT features, and software readout. However, the repository contains several ingredients that make a controlled comparison worth testing:

- physical modal fingerprints;
- write / rewritability paths, including firmware-defined virtual rewriting, binary perturbation sites, and writable-shell concepts;
- high-dimensional acoustic kernels;
- partial-query associative recall;
- mode-dropout tolerance;
- phase/interference primitives;
- trajectory / future-state recall experiments;
- explicit direct-wire and software baselines.

The goal is to determine whether CWM has a credible path toward **physical dynamical-system reconstruction** rather than another isolated classification demo.

## 2. Central hypothesis

A CWM resonator or plate array can provide a useful physical feature map for dynamical-system reconstruction when the input query is partial, noisy, or missing components.

The strongest acceptable claim would be:

> A CWM acoustic kernel improves reconstruction or forecasting of a dynamical system versus direct-wire and software baselines under controlled partial-observation / noisy-query conditions, using a deliberately simple readout.

The claim is not:

- CWM is a quantum computer;
- CWM has already matched a phase-change memristor chip;
- the macro bench is a finished compute-in-memory device;
- digital software is irrelevant;
- acoustic CWM beats GPUs at current bench scale.

## 3. Required baselines

Every reported result must include the following baselines:

1. **Raw input + linear readout**  
   The minimal baseline: current observed state variables directly into ridge / logistic / linear readout.

2. **Direct-wire features + same readout**  
   Electrical/reference path or synthetic direct features with the same dimensionality where possible.

3. **Software random kernel + same readout**  
   Random Fourier features, random projection, ESN-style reservoir, or other cheap software kernel matched for feature count.

4. **CWM acoustic kernel + same readout**  
   Identical train/test split and identical readout complexity.

5. **Ablations**  
   Mode dropout, feature shuffling, plate-off / drive-off null, and session-split tests.

A CWM result is not considered meaningful unless it beats at least the direct-wire baseline under the stated partial/noisy condition and is not explained by leakage, target alignment bugs, or decoder overfitting.

## 4. Candidate tasks

### Task A: Lorenz attractor reconstruction

**Purpose:** Standard nonlinear dynamical-system benchmark with known state variables.

**Input:** partial observation, e.g. x(t) only or x(t), y(t) with z(t) hidden.  
**Target:** reconstruct hidden coordinate or forecast x(t + delta).  
**Metric:** normalized RMSE, R2, and forecast horizon before error exceeds threshold.  
**Reason to use:** small, reproducible, no biological-data dependency.

### Task B: Mackey-Glass / NARMA sequence prediction

**Purpose:** Compare against reservoir-computing literature.

**Input:** scalar time series.  
**Target:** next-step or multi-step prediction.  
**Metric:** NMSE / NRMSE.  
**Reason to use:** established benchmark; exposes whether current CWM is only a spatial/spectral kernel or has useful temporal memory.

### Task C: Pong transition reconstruction

**Purpose:** Use the repo's strongest existing trajectory-recall thread.

**Input:** partial Pong state: position only, position + heading, noisy / missing velocity, or dropout-corrupted query.  
**Target:** landing zone, next state, or intercept decision.  
**Metric:** accuracy, top-k accuracy, calibration of predicted distribution, and performance under noise/dropout.  
**Reason to use:** closest to existing CWM future-by-recall experiments.

### Task D: Toy neural oscillator / cortical state reconstruction

**Purpose:** Bridge toward the external neural-dynamical-system claim without overreaching.

**Input:** synthetic low-dimensional neural oscillator or coupled Wilson-Cowan-style states.  
**Target:** reconstruct hidden population activity or next-state vector.  
**Metric:** RMSE, correlation, classification of regime transitions.  
**Reason to use:** closer to brain reconstruction while still controlled.

## 5. Experimental phases

### Phase 0: Software-only sanity check

Before hardware, implement the full benchmark pipeline using stored data or synthetic kernels.

**Success criterion:** the evaluation code correctly detects leakage, target-shift errors, train/test contamination, and baseline failures.

**Failure interpretation:** if the software benchmark is unstable or easy to cheat, do not run hardware.

### Phase 1: Replay existing CWM captures

Use committed result files where possible, especially high-dimensional kernel captures, Pong training results, and partial-query/dropout experiments.

**Success criterion:** reproduce the strongest existing claims from committed data with one command and produce a single comparison table.

**Failure interpretation:** if committed data cannot reproduce the claims, mark them as non-publication-ready.

### Phase 2: Fresh single-session hardware run

Run one task end-to-end on the current bench after hardware health is restored.

**Minimum targets:**

- CWM > direct-wire under partial/noisy query;
- CWM > raw input + linear readout;
- software random kernel included;
- feature count and readout complexity reported;
- all nulls included.

**Failure interpretation:** if CWM only wins with a complex decoder or contaminated split, the result is not evidence for physical computation.

### Phase 3: Cross-session repeatability

Repeat the best task across at least three separate sessions with re-mount / re-power / re-baseline where practical.

**Success criterion:** CWM advantage survives all three sessions within a predeclared tolerance.

Suggested threshold:

- at least +10 percentage points accuracy over direct-wire for classification-style tasks; or
- at least 20% relative error reduction for regression-style tasks; or
- clearly better graceful degradation under 50-90% feature dropout.

**Failure interpretation:** single-session advantage is likely calibration/decode artifact.

### Phase 4: Write / virtual-rewrite extension

Repeat the task under two or more CWM states:

- firmware-defined virtual rewrite / readout mask;
- physical perturbation state, if available;
- alternate plate / cartridge / mass state;
- future binary perturbation site if built.

**Success criterion:** the same substrate can be reconfigured to solve two different dynamical mappings, with clear state identity and no hidden retraining advantage.

**Failure interpretation:** CWM remains a fixed physical feature map, not a compute-in-memory candidate.

## 6. Measurement requirements

Each run must save:

- raw captures or sufficient processed spectra to reproduce features;
- exact hardware configuration;
- drive frequencies, amplitudes, phases, and capture settings;
- train/test split seed;
- readout model and hyperparameters;
- baseline outputs;
- null-test outputs;
- energy / latency estimate if available;
- result JSON and plots.

Do not report only final accuracy.

## 7. Metrics

### Classification metrics

- accuracy;
- balanced accuracy;
- top-k accuracy;
- confusion matrix;
- calibration / entropy where path-sum distributions are used;
- noise and dropout curves.

### Regression / reconstruction metrics

- RMSE / NRMSE;
- R2;
- Pearson correlation;
- forecast horizon;
- error vs. noise level;
- error vs. missing-observation percentage.

### Hardware / system metrics

- capture time;
- FFT/readout time;
- estimated acoustic drive energy;
- electrical drive/readout overhead;
- number of modes/features used;
- feature stability across session;
- null / feedthrough measurements.

## 8. Kill criteria

Stop or reframe the experiment if any of the following occur:

1. CWM does not beat direct-wire or software-kernel baselines under any fair partial/noisy condition.
2. CWM only wins with a complex digital decoder while simple readout fails.
3. Performance disappears under cross-session testing.
4. Advantage depends on target leakage, target alignment bugs, or train/test contamination.
5. Null tests show electrical feedthrough explains the features.
6. Hardware overhead dominates so completely that no MEMS-relevant path can be stated.
7. Write/virtual-rewrite states cannot change the mapping without full software retraining.

## 9. Strong success definition

A strong result would look like this:

- one benchmark task selected before the run;
- three independent sessions;
- CWM acoustic kernel beats direct-wire and raw-input baselines under partial/noisy query;
- software random kernel included and honestly compared;
- simple readout only;
- nulls pass;
- saved data and scripts reproduce the table;
- optional: two written / virtually rewritten CWM states solve distinct mappings.

This would not prove MEMS compute-in-memory. It would justify the next memo section: what MEMS unit cell would preserve the useful operation while reducing I/O overhead.

## 10. Relationship to compute-in-memory

For this benchmark to support a compute-in-memory path, the final analysis must explicitly answer:

1. What physical state stores the useful mapping?
2. What operation is performed by acoustic physics rather than software?
3. How much digital decoding remains?
4. What would become smaller, faster, or lower-power at MEMS scale?
5. What would still be worse than memristors, SRAM + ADC + DSP, or conventional analog circuits?

If those questions cannot be answered after the benchmark, the result should be published only as a physical feature-map / acoustic kernel result, not as compute-in-memory.

## 11. Proposed first implementation

Start with the lowest-risk version:

**Task:** Pong transition reconstruction or Lorenz hidden-state reconstruction.  
**Features:** existing 767-mode kernel if reproducible; otherwise fresh CWM spectra.  
**Readout:** ridge regression or logistic regression only.  
**Baselines:** raw, direct-wire, software random kernel, CWM.  
**Stressors:** Gaussian query noise, partial observation, mode dropout.  
**Primary claim:** graceful degradation / partial-query completion, not broad denoising superiority.  
**Secondary claim:** reconfigurable mapping only if virtual-write or physical-write state is included.

## 12. Expected outcomes

### If positive

CWM earns a more focused next step:

> acoustic physical-kernel dynamical reconstruction, with MEMS compute-in-memory still conditional on a credible writable unit cell.

### If mixed

CWM should publish the partial-query / acoustic-kernel result and stop comparing itself to neural compute-in-memory chips until a device-level write/read primitive exists.

### If negative

CWM should pivot away from compute-in-memory toward sensing, PUFs, acoustic fingerprinting, educational wave-computing, or other applications where a physical feature map is sufficient.

## 13. Repo follow-up checklist

- Add a runnable tool, e.g. `tools/cwm_dynamical_benchmark.py`.
- Add a result schema under `data/results/dynamical_benchmark/`.
- Add a short reproduction section to the lab diary when first run completes.
- Update `paper/CLAIMS_STATUS.md` only after the benchmark has measured results.
- Do not update public claims from this protocol alone.
