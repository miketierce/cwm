# Distributed Partial-View Representation and Reference-Assisted Reconstruction

**Status:** OPEN / downstream experimental protocol  
**Parent:** merged PR #16 — K_eff and relational compute vs readout complexity  
**FT-0 evidence:** [HOLOGRAPHIC_FT0_EXISTING_DATA_NOTE.md](HOLOGRAPHIC_FT0_EXISTING_DATA_NOTE.md)  
**Measurement prerequisite:** [MEASUREMENT_AND_CLAIM_GATE.md](MEASUREMENT_AND_CLAIM_GATE.md)

## 1. Why this is a separate fast track

Merged PR #16 established the measurement discipline required to ask whether a physical CWM transform is useful across sessions and under reduced readout.

Existing CWM data now support a narrower question that was already anticipated in the Representation Hypothesis:

> **Does useful state identity remain recoverable from deliberately incomplete spectral or spatial views of the same physical response?**

A second, related but distinct question is:

> **Can a known coherent reference convert an unknown complex CWM response into a simpler interference observable from which the relevant complex response or task statistic can be reconstructed?**

These questions deserve a downstream PR because:

1. PR #16 is merged and should remain the measurement/readout foundation.
2. The partial-view hypothesis has retrospective evidence strong enough to make a fresh test falsifiable.
3. Reference-assisted reconstruction requires new acquisition conditions and should not be inferred from the partial-view result.
4. "Holographic" has established meanings in optics and acoustics; the CWM claim must be operational and narrower.

Use **distributed partial-view representation** as the default engineering term.

Use **holographic-like** only as an analogy and only at the demonstrated level.

---

## 2. Claim ladder

### Level 0 — spectral/spatial redundancy

Different subsets contain overlapping task information.

Historical E26/E36/E8 are consistent with this level.

### Level 1 — distributed partial-view task identity

Multiple independently chosen partial views recover the same frozen task state on held sessions.

This is the first fresh target.

### Level 2 — cross-view prediction / reconstruction

A partial view predicts omitted measurements or a defined full-view representation on held sessions.

This is stronger than classification redundancy.

### Level 3 — reference-assisted complex reconstruction

A calibrated coherent reference enables recovery of a complex response or sufficient task statistic from a simpler measured interference observable.

### Level 4 — engineered holographic operator

Geometry is deliberately designed so partial physical views or reference interference provide a useful reconstruction/task advantage at favorable system cost.

Do not skip levels in claims.

---

## 3. Two independent hypotheses

### H-PV — distributed partial-view identity

For task `T`, full response `Y`, and partial observation `Y_S` over subset `S`:

> There exists a nontrivial range of spectral or spatial aperture fractions `|S| / |Y| < 1` for which a decoder frozen on training sessions preserves the required held-session task performance across many independently selected subsets.

The important quantity is not one lucky subset.

Measure the distribution:

```
P(task passes | aperture fraction)
```

A useful distributed representation should degrade gracefully as aperture shrinks rather than collapse whenever one privileged feature disappears.

### H-REF — reference-assisted reconstruction

Let the unknown complex response be:

```
U = A * exp(i * theta)
```

and a known coherent reference be:

```
R * exp(i * phi)
```

For a square-law observable:

```
I(phi) = |U + R * exp(i * phi)|^2
```

Four phase settings can isolate the two quadratures:

```
I(0) - I(pi) = 4 * Re(U * R*)
I(pi/2) - I(3pi/2) = 4 * Im(U * R*)
```

where `R*` denotes the complex conjugate of the reference. After reference calibration, these are sufficient to reconstruct `U` up to the declared calibration convention.

This is ordinary coherent interferometry / phase-shifting holographic logic. It is not quantum.

The CWM engineering question is not whether the algebra works. It is whether the physical implementation is:

- stable;
- accurate;
- cheaper/simpler for the intended task;
- compatible with the CWM transfer;
- competitive with direct complex acquisition.

Four sequential magnitude measurements are **not automatically cheaper** than one direct complex measurement. Count them honestly.

---

## 4. HP-0 — retrospective evidence

Run:

```bash
python tools/holographic_ft0_existing.py \
  --output data/results/holographic_ft0_existing.json
```

The output is exploratory and should reproduce:

- E26 adaptive top-K partial-query result;
- E36 exhaustive arbitrary mode-index subset frontier;
- E8 dual-spatial-view task redundancy;
- FT-1 measurement/stability context.

Do not modify historical result labels.

---

## 5. HP-1 — fresh spectral partial-view frontier

### Question

Does task identity survive **preselected incomplete spectral views** on later sessions?

### Hardware

Use the qualified FT-M fixture/reference setup.

Start with one TX and one RX. Spatial aperture is not needed for HP-1.

### Task

Choose one bounded state-identification task before capture.

Prefer a task with:

- at least 8 states if feasible;
- balanced classes;
- enough repetitions for confidence intervals;
- no task definition chosen after seeing test-session results.

The state may be a fixed multitone/amplitude code or another physically justified encoding. Do not use a task whose answer is trivially a software label attached after measurement.

### Full view

Define a fixed candidate mode/bin set (M) using training/qualification data only.

### Partial views

Before held-session scoring, freeze multiple subsets at aperture fractions such as:

```
100%, 75%, 50%, 40%, 30%, 20%
```

At each fraction use:

1. several random subsets;
2. one training-selected high-quality subset;
3. one deliberately low-quality/noise-matched subset where useful.

Do not select subsets from held-session performance.

### Metrics

For each subset:

- balanced accuracy or exact-state accuracy;
- confusion matrix;
- margin / calibrated confidence;
- abstention and coverage;
- calibration bytes/trials;
- ADC samples and frequency bins actually required;
- later-session performance;
- performance loss relative to full view.

Aggregate by aperture fraction:

- median task score;
- lower quantile;
- fraction of subsets passing the task gate;
- worst qualified subset;
- calibration burden distribution.

### Preliminary gate

A strong Level-1 result requires a preregistered aperture fraction at or below 50% where:

- a substantial fraction of independently frozen subsets pass the absolute task threshold;
- the same subsets remain within the declared noninferiority margin on complete later sessions;
- success is not attributable to ELECTRICAL_ONLY or source-only leakage;
- random label/enrollment controls collapse toward chance.

The exact pass fraction and task threshold must be set before fresh test data.

---

## 6. HP-2 — spatial partial-view / multi-view identity

### Question

Do materially different spatial projections of the plate preserve the same task identity?

Historical E8 suggests this is plausible but is only two positions, same-session, receiver-specific thresholding.

### Minimum design

Use at least three registered receive positions if hardware permits.

If only two simultaneous scope channels are available:

- either use additional synchronized acquisition hardware;
- or use a qualified sequential protocol whose phase/transfer stability is measured.

Do not call sequential measurements simultaneous.

For each receiver `r_j`, measure `Y_j(f)`.

### Tests

#### A. Receiver-specific decoders

Train/freeze one decoder per receiver.

This asks whether each spatial view independently contains enough task information.

#### B. Shared decoder

Use identical normalization/decoder parameters across receiver positions when physically meaningful.

This is a stronger invariance test.

#### C. Cross-view transfer

Train on one receiver or receiver subset and score another without retraining.

This asks whether the task representation is shared or merely separately decodable.

#### D. Receiver subset dropout

For an array/multi-position map, score all fixed receiver subsets.

Report performance versus spatial aperture fraction.

### Nulls

- shuffled receiver labels;
- shuffled frequency coordinates;
- ELECTRICAL_ONLY;
- LOOPBACK;
- physically interrupted/mechanically changed path where practical.

### Interpretation

Receiver-specific success = redundant spatial access.

Shared/cross-view success = stronger invariant representation.

Neither result alone proves reconstruction of the full spatial field.

---

## 7. HP-3 — omitted-view reconstruction

Classification can succeed from redundant cues without reconstructing missing measurements.

Therefore test reconstruction separately.

### Spectral version

Train a mapping from subset (Y_S) to omitted features (Y_{ar S}) using training sessions only.

Evaluate complete held sessions.

Metrics:

- normalized complex RMSE;
- magnitude error;
- phase error only above a preregistered amplitude/reference-SNR floor;
- correlation is secondary, not sufficient by itself;
- simple baseline: per-feature training mean;
- linear/ridge baseline;
- full conventional digital model baseline.

### Spatial version

Predict one receiver's complex response from another receiver or subset.

A positive result indicates shared structure, but may still be ordinary low-rank correlation.

Compare against:

- low-rank PCA/ridge;
- shuffled frequency coordinate;
- unrelated-device/plate baseline where available.

### Strong result

Omitted-view prediction materially beats trivial/low-rank baselines on later sessions without receiver-specific retuning.

Do not call good classification accuracy "full reconstruction."

---

## 8. HP-4 — reference-assisted complex reconstruction

Only after source/reference stability is qualified under FT-M.

### Hardware concept

```
query TX/path --------\
                       > fixed plate H ----> one RX ----> magnitude/power-like detector
reference TX/path ----/
```

The reference path must have known/qualified amplitude and relative phase.

### Phase program

For each frozen query:

```
0
pi/2
pi
3pi/2
```

Measure the same defined observable at every phase.

Reconstruct the quadratures using the difference pairs.

### Required baselines

1. direct complex acquisition of the same RX signal;
2. reference-only;
3. query-only;
4. ELECTRICAL_ONLY / loopback where applicable;
5. reconstruction with deliberately randomized reference phase.

### Metrics

- complex reconstruction NRMSE;
- magnitude error;
- phase error above SNR floor;
- later-session zero-retuning error;
- number of captures;
- ADC precision/channel count;
- reference hardware cost;
- phase-programming time;
- analog detector cost;
- calibration trials/bytes;
- total latency/energy when measurable.

### Acceptance

A physics result:

> reference interference reconstructs the qualified complex response within a preregistered error.

An engineering advantage additionally requires:

> the resulting implementation meets the task at a measured lower cost or other declared benefit than direct complex acquisition.

Do not infer an advantage merely because the reconstruction uses a scalar detector.

---

## 9. HP-5 — joint partial-view + reference test

Only after HP-1/2 and HP-4 independently work.

Ask whether the reference makes a partial view more informative or cheaper to recover.

Examples:

- recover a task from one spatial receiver using reference phase instead of full complex ADC;
- reconstruct omitted spectral coordinates from a reference-assisted partial view;
- compare aperture required for a fixed task with and without the reference.

This is where a genuine CWM-specific "holographic readout" architecture might emerge.

---

## 10. FT-1 lessons that are mandatory here

The October 2026 FT-1 campaign established that cross-session transfer variation can dominate prediction.

Therefore every HP experiment must:

- use the corrected exact-frequency/NCO grid;
- preserve raw captures;
- record a plate-local temperature sensor when available;
- constrain/anchor fixture and PZT lead motion;
- distinguish power cycle from remount/handling;
- report between-session change of the full transfer beside partial-view task performance;
- score zero-retuning primary results before any recalibrated secondary result.

If the full H drifts while the task survives, that is potentially **supporting evidence for invariant distributed representation**.

If partial-view task success tracks the same drift and collapses, the simpler fingerprint explanation wins.

---

## 11. Primary falsifiers

### H-PV is weakened or killed if

- performance depends on one or two privileged modes rather than many independent subsets;
- random/fixed subsets collapse much faster than expected from ordinary feature redundancy;
- later-session success requires selecting a new subset;
- success disappears under leakage-safe source/electrical controls;
- cross-view success is explained entirely by identical feedthrough.

### H-REF is weakened or killed if

- reference phase/amplitude cannot be held or measured accurately enough;
- reconstructed complex response does not beat a magnitude-only baseline for the declared task;
- four-phase acquisition costs more without another measurable benefit;
- direct complex acquisition is simpler/faster/less energy at matched task performance;
- electrical-only interference reproduces the apparent acoustic reconstruction.

A killed "holographic" track does not invalidate CWM's ordinary filter/transform uses.

---

## 12. Literature and claim boundary

### Biphoton digital holography

D. Zia et al., "Interferometric imaging of amplitude and phase of spatial biphoton states," *Nature Photonics* 17, 1009–1016 (2023). DOI: 10.1038/s41566-023-01272-3.

The paper uses coincidence imaging of a superposition of unknown and reference biphoton states to recover spatial amplitude and phase. It motivates the reference-assisted measurement pattern.

It does **not** establish a CWM mechanism or quantum behavior in glass.

### Acoustic holography prior art

K. Melde et al., "Holograms for acoustics," *Nature* 537, 518–522 (2016). DOI: 10.1038/nature19755.

Acoustic holography and wavefront reconstruction are established prior art.

Therefore CWM must not claim novelty for:

- using sound to form a hologram;
- reconstructing an acoustic field from interference in general;
- using a coherent reference in acoustic measurement in general.

Any eventual CWM novelty claim must be narrower and tied to the specific distributed representation, physical operator, encoding, calibration, partial-view task or readout architecture.

---

## 13. Shortest useful execution order

```
HP-0 reproduce retrospective subset frontier
  -> HP-1 fresh spectral partial-view held-session test
  -> HP-2 spatial multi-view identity
  -> HP-3 omitted-view reconstruction
  -> HP-4 reference-assisted complex reconstruction
  -> HP-5 joint partial-view/reference architecture
```

Do not start with a large spatial scan or invoke "holographic memory" as a measured property.

The first decisive fresh question is:

> **When we deliberately hide half of the spectral view before the test session, does the frozen partial view still know what state the full measurement knows?**
