# Linear Representation Transfer: CWM Research Worklist

**Status:** OPEN HYPOTHESIS / EXPERIMENT PLAN  
**Purpose:** Determine whether CWM's distributed acoustic representation is useful precisely because it is a structured, redundant, approximately low-dimensional physical feature map that can be aligned, reconstructed, and transferred using inexpensive linear mathematics.

## Motivation

Recent CWM work has increasingly supported a conservative description of the current plate as a distributed classical acoustic feature map rather than a demonstrated nonlinear reservoir. That result should not automatically be treated as a limitation. Recent work on representation transfer in AI systems provides a useful architectural analogy: large internal representations can sometimes be translated between systems with simple linear mappings when the underlying information geometry is shared.

This document does **not** claim that CWM and neural-network KV caches implement the same mechanism. The external work is inspiration for a falsifiable CWM question:

> Are CWM modal representations across missing channels, sessions, and physical resonators related by sufficiently simple transformations that a small linear adapter can recover a common logical state space?

If yes, CWM would not require perfectly identical physical spectra. A future device could combine an individual physical transfer function with a lightweight calibration map into a standardized representation.

## Core hypothesis

Let a CWM measurement be a modal feature vector

`x in R^M`

where M may be much larger than the intrinsic dimension of the encoded physical state.

### H-LR1: Low-dimensional structure

The measured modal vector occupies a substantially lower-dimensional subspace/manifold than its raw feature count suggests while retaining useful state information.

### H-LR2: Linear recoverability under channel loss

A full modal representation can be approximated from a subset of channels using a regularized linear map, and this reconstruction preserves useful recall/classification information.

### H-LR3: Cross-session linear alignment

Day-to-day drift changes the measured coordinates more than the underlying information. A small calibration set can learn a linear map from a new session into an older enrolled representation sufficiently well to reuse the old decoder/templates without full re-enrollment.

### H-LR4: Cross-device linear alignment

Different resonators exposed to equivalent inputs may produce different raw spectra but compatible information spaces. A lightweight linear adapter may translate one device's representation into another device's enrolled logical space.

This is the most consequential and least established hypothesis.

## Claim boundaries

A successful result would support terms such as:

- distributed physical representation
- physical feature map
- redundant modal embedding
- linearly alignable representation
- cross-session calibration
- cross-device representation transfer

It would **not** by itself establish:

- quantum information processing
- holographic memory
- nonlinear reservoir computing
- compute-in-memory
- general-purpose computing
- an energy advantage over electronics

Those require independent evidence.

---

# Work package LR-1 — Intrinsic dimensionality

**Hardware:** none; use existing datasets first.

## Question

How many independent dimensions are required to explain the useful information in the measured modal representation?

## Method

1. Assemble the cleanest existing dataset containing the broad modal vector and known ground-truth states.
2. Split train/test before fitting transforms.
3. Standardize features using training statistics only.
4. Compute SVD/PCA on training data.
5. Report cumulative explained variance and effective rank.
6. Project held-out samples onto k components for a sweep of k.
7. Run the same fixed downstream task/decoder at each k.
8. Repeat with randomized labels and shuffled-feature controls.

## Required outputs

- singular-value spectrum
- cumulative explained variance
- k for 90%, 95%, 99% variance
- recall/classification score vs k
- confidence intervals over repeated splits
- comparison with raw M-feature performance

## Success criterion

Useful performance remains close to the full representation at a substantially smaller k. Do not define 'substantially' after seeing the data; record both compression ratio and performance loss.

## Failure interpretation

If performance collapses rapidly as dimensionality is reduced, the observed dropout robustness may arise from a different mechanism than a compact shared latent representation.

---

# Work package LR-2 — Missing-mode linear reconstruction

**Hardware:** none initially.

## Question

Can surviving modal channels reconstruct missing channels well enough to preserve the logical state?

## Method

For dropout fractions including 25%, 50%, 75%, 90%, and 95%:

1. Select surviving channels without looking at test labels.
2. Fit ridge regression on training samples:

   `X_surviving W ~= X_full`

3. Reconstruct held-out full modal vectors.
4. Evaluate both reconstruction quality and downstream task performance.
5. Compare against using the surviving modes directly.
6. Repeat over many random channel masks.
7. Separately test structured dropout (contiguous frequency bands, sensor loss, high-Q-only loss, low-Q-only loss).

## Baselines

- surviving modes directly
- mean imputation
- nearest-neighbor imputation
- PCA reconstruction
- nonlinear MLP reconstruction (diagnostic only)
- shuffled correspondence negative control

## Metrics

- normalized RMSE / R^2 per feature and globally
- cosine similarity of reconstructed vs true modal vector
- downstream recall/classification accuracy
- calibration-set size
- multiply-add count and memory cost of W

## Strong result

Linear reconstruction materially improves downstream performance over direct use of surviving channels, especially under severe or structured dropout.

## Important null

If direct surviving-mode recall equals or beats reconstruction, the redundancy is still useful but the linear reconstruction layer adds no value.

---

# Work package LR-3 — Cross-session representation alignment

**Hardware:** new repeat session using the same physical setup.

## Question

Can a new session be mapped into an old enrolled coordinate system without re-enrolling the full memory?

## Experimental design

### Session A

- perform a complete enrollment
- save raw data, environmental metadata, drive settings, frequency axis, gain settings, decoder/templates, and exact preprocessing
- freeze the Session-A decoder before Session B

### Session B

Without modifying Session-A enrollment:

1. reproduce the same state/query protocol
2. collect calibration pairs for a deliberately limited subset of known states
3. collect a separate blinded evaluation set
4. apply nuisance normalization before learning the adapter
5. fit a ridge/linear map from B to A using calibration pairs only
6. transform blinded Session-B measurements into Session-A space
7. run the frozen Session-A decoder/templates

## Calibration sweep

Test at least 5, 10, 20, 50 calibration observations/states where dataset size permits. Report exact sample counts and state coverage.

## Nuisance-removal ablation

Evaluate combinations of:

- global gain normalization
- frequency-axis alignment
- temperature compensation
- phase/reference alignment where available
- no correction

The goal is to avoid forcing W to learn known nuisance transformations unnecessarily.

## Baselines

A. frozen Session-A decoder directly on raw Session B  
B. simple normalization only  
C. linear B->A adapter + frozen Session-A decoder  
D. full Session-B re-enrollment / retraining (upper practical baseline)  
E. direct-wire/electronic baseline where the experiment permits it

## Primary success criterion

C substantially closes the performance gap between A and D using a calibration set much smaller than a full re-enrollment.

Report the entire calibration-size/performance curve rather than choosing one favorable point.

## Stronger result

A fixed adapter learned from a small calibration set remains useful across additional later sessions without refitting.

## Failure interpretation

If W requires nearly complete re-enrollment, high model capacity, or frequent refitting, the representation is not practically transferable by the proposed mechanism.

---

# Work package LR-4 — Cross-plate / cross-device alignment

**Hardware:** two physically distinct resonators measured under equivalent query/state protocols.

## Question

Can Device B's physical representation be translated into Device A's enrolled logical representation?

## Protocol

1. Freeze Device A enrollment and decoder.
2. Present matched physical states/queries to A and B using as identical a protocol as practical.
3. Preserve paired observations and environmental metadata.
4. Use a small paired calibration subset to fit B->A.
5. Hold out entire states/query conditions where possible, not merely repeated samples.
6. Transform blinded Device-B measurements.
7. Decode them using only Device A's frozen memory/decoder.

## Critical controls

- shuffled A/B pairings
- random linear matrix of matched scale
- direct Device-B decoding without transfer
- full Device-B enrollment
- simple per-channel normalization
- test whether performance comes primarily from explicit digital state variables rather than acoustic modes

## Success tiers

**Tier 0 — fail:** no useful transfer above controls.  
**Tier 1 — calibration:** transfer works only for observed calibration states.  
**Tier 2 — interpolation:** transfer generalizes to held-out combinations within the trained state domain.  
**Tier 3 — state generalization:** transfer preserves useful decoding on entire held-out logical states or conditions.  
**Tier 4 — adapter reuse:** one adapter remains useful across sessions/environmental changes without refitting.

Tier 2+ is the interesting result. Tier 3+ would materially strengthen a standardized-device/MEMS architecture thesis.

---

# Work package LR-5 — Common logical CWM space

Only begin after LR-3 and LR-4 show positive evidence.

Instead of treating Device A as the canonical target, learn a compact canonical representation z:

`x_device -> z -> task`

Compare:

1. device-specific decoders
2. pairwise device adapters
3. each device mapped into one shared low-dimensional space

Evaluate whether adapter size grows approximately with each device rather than quadratically with device pairs.

A practical architecture would look like:

`physical resonator -> lightweight calibration -> canonical CWM representation -> simple decoder`

For PUF/security applications, preserve the unnormalized/raw device representation separately; successful logical calibration must not be confused with physical clonability.

---

# Work package LR-6 — Complexity, energy, and latency accounting

No architectural claim is useful without including the electronics required to obtain it.

For every successful configuration record or estimate transparently:

- number of driven channels
- number of sensed channels
- ADC samples/conversions
- DAC operations
- acquisition duration
- preprocessing operations
- adapter parameters
- adapter multiply-adds
- decoder operations
- CPU/device used for analysis
- physical drive energy where measurable
- sensor/readout energy where measurable

Compare against:

- direct wire / direct sensors + same decoder
- sensors + DSP feature extraction
- raw features + software linear projection
- conventional nearest-neighbor/classifier implementation

A physical representation that requires expensive acquisition plus a large digital adapter may be scientifically interesting but does not establish a low-power computing advantage.

---

# Statistical and leakage requirements

All work packages must follow these rules:

1. Fit normalization, PCA, ridge coefficients, feature selection, and hyperparameters on training/calibration data only.
2. Preserve a truly held-out evaluation set.
3. Where repeated measurements of one state exist, split by state/session/group when random row splitting could leak near-duplicates.
4. Pre-register primary metrics and thresholds before final hardware evaluation.
5. Report negative results and all tested calibration sizes/dropout levels.
6. Save machine-readable results alongside plots.
7. Record random seeds and exact source-data hashes/paths.

---

# Recommended implementation tools

Create small reusable analysis tools rather than one-off notebooks where possible:

- `tools/analyze_intrinsic_dimension.py`
- `tools/test_linear_mode_reconstruction.py`
- `tools/fit_session_adapter.py`
- `tools/fit_device_adapter.py`
- `tools/evaluate_canonical_space.py`

Each should accept explicit input/output paths and emit JSON plus CSV summaries. Plots are secondary artifacts; the numerical result must remain machine readable.

Suggested common outputs:

```json
{
  "experiment_id": "LR-3",
  "source_dataset": "...",
  "train_groups": [],
  "test_groups": [],
  "preprocessing": {},
  "adapter": {"type": "ridge", "alpha": 0.0},
  "baselines": {},
  "metrics": {},
  "seed": 0
}
```

Do not hard-code the present modal count; tools should discover feature dimensions from the data/configuration.

---

# Decision matrix

| Result | Interpretation | Next action |
|---|---|---|
| Low intrinsic dimension + no transfer | redundant local representation, device/session-specific | investigate drift physics; do not claim standardizable representation |
| Missing-mode reconstruction only | useful redundancy/error tolerance | pursue robust sensing/readout use cases |
| Cross-session transfer | calibration burden may be manageable | repeat across days/temperature/mounting |
| Cross-device interpolation | evidence for compatible physical information spaces | expand device count and test canonical representation |
| Cross-device held-state generalization | strong architecture result | begin MEMS-relevant transduction/device study |
| Adapter complexity approaches full digital model | little systems advantage | reframe as physical sensing/feature-map research |
| Direct electronic baseline dominates | no compute advantage shown | retain only scientifically distinct sensing/PUF results |

---

# Falsifiers / stop conditions

This direction should be weakened or abandoned if repeated controlled experiments show that:

1. apparent low dimensionality disappears under leakage-free held-state evaluation;
2. linear reconstruction does not improve severe/structured dropout performance;
3. cross-session adapters require near-complete re-enrollment;
4. cross-device adapters memorize calibration states but fail held-state/generalization tests;
5. alignment requires nonlinear models large enough to perform the task directly;
6. adapter/calibration burden grows faster than the value gained from the physical substrate;
7. cheap direct sensors/electronics produce an equal or better representation under fair noise, missing-data, energy, and latency conditions.

A negative result is useful: it constrains CWM to a device-specific physical feature map rather than a transferable computing architecture.

---

# Immediate execution order

## Priority 1 — existing data, no hardware

1. **LR-1:** intrinsic dimensionality and task accuracy vs rank.
2. **LR-2:** linear missing-mode reconstruction, including structured dropout.
3. Audit existing datasets for multiple sessions/devices that may permit retrospective LR-3/LR-4 analysis.

## Priority 2 — next bench session

4. **LR-3:** deliberately paired cross-session acquisition with frozen old enrollment.
5. Capture environmental and signal-path metadata needed to separate drift from representation change.

## Priority 3 — after LR-3 succeeds

6. **LR-4:** matched two-device acquisition and blind cross-device transfer.
7. Only after repeatable LR-4 Tier 2+ evidence, begin LR-5 canonical-space and MEMS-standardization work.

---

# Publication-quality question

The strongest scientifically defensible target is not:

> 'CWM performs complicated computation because it has many modes.'

It is:

> **Can a passive acoustic system create a distributed, fault-tolerant physical representation whose logical information is preserved across channel loss, time, and distinct resonators through only lightweight linear calibration?**

That question is narrower, testable, compatible with the current classical framing, and has clear negative outcomes.

## External inspiration note

This worklist was motivated in part by recent reporting on NVIDIA research showing that internal representations between related AI models can sometimes be transferred using simple linear mappings rather than full recomputation. That result is an architectural analogy and methodological inspiration only. It is not evidence for CWM. The primary evidence for every CWM claim must come from CWM measurements and fair physical/electronic baselines.