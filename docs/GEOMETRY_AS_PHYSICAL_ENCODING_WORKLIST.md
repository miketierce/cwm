# Geometry as Physical Encoding — CWM Research Worklist

## Status

**OPEN — research inspiration and experimental program only.**

This document does not change any CWM claim from OPEN to MEASURED. It is motivated in part by recent work on high-aspect-ratio flat optical fiber (HARFF), where changing the geometry of an otherwise familiar wave-guiding material creates unusually strong and direction-dependent mechanical/optical responses. That external work is evidence that geometry can be an engineered transduction variable; it is **not** evidence for CWM memory or computation.

Reference starting points:

- New Atlas, “Flat optical fiber design has superior sensing capabilities” (2026): https://newatlas.com/materials/flat-optical-fiber-design-superior-sensing-capabilities/
- Nature Communications paper linked by the article: https://doi.org/10.1038/s41467-026-74486-y

---

## Why this matters to CWM

The current CWM hardware program has largely asked what information can be recovered from the naturally occurring modal structure of plates, rods, and attached transducers.

The HARFF result suggests a stronger engineering question:

> **Instead of accepting the resonator geometry and discovering what representation it gives us, can we deliberately design geometry so that desired physical variables map into maximally distinguishable, redundant, and calibratable modal representations?**

This changes the design philosophy from:

```text
fabricate / obtain resonator
        ↓
measure modes
        ↓
discover useful representation
```

toward:

```text
define desired representation
        ↓
define desired sensitivities / invariances
        ↓
design geometry and boundary conditions
        ↓
fabricate resonator
        ↓
measure whether physics implements the target map
```

This is compatible with the existing CWM inverse-design/MEMS direction, but gives it a more concrete experimental target.

---

# External result: what is actually relevant

The cited flat-fiber work changes the cross-sectional geometry of conventional silica fiber from approximately circular to a high-aspect-ratio rectangular form.

The important architectural observations for CWM are:

1. **Geometry creates anisotropy.** A structure can respond differently depending on the direction of applied strain or bending.
2. **Geometry can amplify mechanically induced changes in an observable wave response.** The useful signal does not have to come from a new material.
3. **One physical element can carry multiple observables.** Optical transmission plus mechanically induced changes can support sensing without adding a separate sensing material.
4. **Mechanical sensitivity can be deliberately shaped.** What would normally be treated as packaging sensitivity can become the sensing mechanism.
5. **Cross-sectional geometry is a design variable, not merely packaging.**

CWM should test analogous principles acoustically rather than assuming they transfer.

---

# Core CWM hypothesis

> **OPEN HYPOTHESIS — The geometry and boundary conditions of a CWM resonator can be deliberately engineered to produce a distributed modal representation with selected sensitivities, selected invariances, and greater recoverability than an unoptimized resonator of similar material and scale.**

This is stronger than saying geometry changes resonance frequencies; that is already expected physics.

The meaningful CWM claim would require geometry to improve a defined information-processing metric such as:

- class/state separability,
- partial-query recovery,
- robustness to receiver dropout,
- useful intrinsic dimensionality,
- cross-session alignment,
- cross-device linear transfer,
- sensitivity to a desired perturbation,
- invariance to an undesired perturbation,
- or acquisition efficiency.

---

# Key idea: engineer sensitivity and invariance separately

A commercially useful physical representation should not simply be “very sensitive.”

For machine-health sensing, for example, we may want:

```text
HIGH sensitivity:
  bearing defect
  imbalance
  crack / looseness

LOW sensitivity:
  ambient temperature
  mounting torque
  electronics gain
  harmless orientation change
```

The geometry program should therefore optimize a ratio such as:

```text
useful state separation
-----------------------
nuisance-induced drift
```

rather than maximizing raw spectral change.

This is a direct bridge between geometry engineering and the linear-representation-transfer program.

---

# GE-1 — Controlled geometry census

## Question

How strongly do simple macroscopic geometry changes alter CWM representation quality?

## Hardware

Create a family of resonators from the same or closely controlled material with systematic geometry variation. Candidate shapes:

- square plate,
- rectangular plate,
- high-aspect-ratio strip,
- tapered strip,
- notched plate,
- asymmetric plate,
- plate with one or more slots,
- locally mass-loaded plate,
- plate with controlled clamp geometry.

Where practical, hold constant:

- material batch,
- thickness,
- total mass,
- transducer type,
- transducer placement,
- excitation amplitude,
- acquisition electronics.

## Measurements

For every geometry record:

- resonance census,
- Q distribution,
- mode density,
- channel correlation,
- effective rank / PCA spectrum,
- state classification,
- partial-query completion,
- simulated and physical channel dropout,
- repeatability across sessions.

## Success criterion

At least one engineered geometry must outperform the plain reference geometry on a preregistered representation metric without merely increasing SNR or total signal amplitude.

## Falsifier

After SNR normalization and equivalent acquisition budget, simple geometry variation does not produce repeatable improvement in representation quality.

---

# GE-2 — Directional / anisotropic encoding

## Inspiration

The flat-fiber result is particularly interesting because high aspect ratio makes mechanical response direction-dependent.

## CWM question

Can an intentionally anisotropic resonator encode perturbation direction more cleanly than a symmetric resonator?

## Protocol

Apply nominally equal perturbations along controlled axes:

- +X / -X,
- +Y / -Y,
- diagonal directions,
- optionally torsional or bending axes.

Compare a symmetric plate with a high-aspect-ratio or otherwise anisotropic geometry.

## Metrics

- directional confusion matrix,
- angular decoding error,
- pairwise representation distance,
- robustness under partial receiver loss,
- held-angle interpolation.

## Strong result

The anisotropic geometry yields greater directional separability or lower angular error at equal input amplitude and acquisition budget.

## Important control

Do not count trivial amplitude differences alone as distributed encoding. Repeat after global amplitude normalization and with magnitude-only / phase-aware comparisons where appropriate.

---

# GE-3 — Geometry-coded sensor fusion

## Question

Can one mechanical body encode multiple simultaneous physical variables into separable modal directions?

Candidate variables:

- force magnitude,
- force location,
- force direction,
- added mass,
- clamp state,
- temperature,
- damage state.

## Experiment

Construct a factorial dataset varying at least two controlled variables independently.

Train lightweight linear decoders for each variable and test held-out combinations.

Example:

```text
training:
  force X + mass A
  force X + mass B
  force Y + mass A

held out:
  force Y + mass B
```

## Why this matters

Successful held-combination decoding would support the idea that the physical representation contains partially separable latent factors rather than only memorized compound fingerprints.

## Falsifier

Performance collapses on unseen combinations and nearest-template matching explains the apparent multi-variable decoding.

---

# GE-4 — Sensitivity / invariance co-design

## Question

Can geometry increase sensitivity to a target variable while suppressing nuisance variables?

## Protocol

Choose one target perturbation and at least two nuisance perturbations.

Example:

```text
target: controlled added mass / defect
nuisance 1: temperature
nuisance 2: mounting torque
```

For each candidate geometry measure:

- target-state separation,
- within-state nuisance drift,
- cross-session drift,
- linear recalibration burden.

Define before testing a composite score such as:

```text
median target separation / median nuisance displacement
```

## Strong result

An engineered geometry produces a materially larger target/nuisance ratio than the reference geometry and retains the improvement in a later session.

---

# GE-5 — Sparse-readout geometry

## Commercial motivation

The current research platform can measure many frequencies/channels, but a commercial CWM device cannot rely on an expensive measurement stack unless the application justifies it.

## Question

Can geometry concentrate useful information into a smaller observable subset without destroying distributed robustness?

## Protocol

For each geometry sweep:

- receiver count,
- selected frequency count,
- acquisition time,
- decoder accuracy,
- partial-query accuracy.

Find Pareto-optimal points for:

```text
accuracy vs receivers
accuracy vs frequency samples
accuracy vs acquisition time
```

## Strong result

An engineered geometry reaches the reference system's performance with materially fewer measured channels/frequencies.

This would be commercially more important than simply producing more modes.

---

# GE-6 — Geometry and linear representation transfer

## Question

Can devices have deliberately different raw spectra while sharing an easily alignable logical representation?

This directly extends LR-4.

Fabricate nominally identical examples of the best geometry and independently characterize each one.

Test:

```text
Device A raw modal space
        ↓
small linear calibration
        ↓
canonical representation
        ↑
small linear calibration
        ↑
Device B raw modal space
```

## Compare

- plain reference geometry,
- optimized geometry.

## Metrics

- calibration sample count,
- retained held-state accuracy,
- regression residual,
- canonical-space separation,
- cross-device dropout robustness.

## High-value outcome

The optimized geometry is not necessarily spectrally identical across devices, but requires less calibration or retains more logical information after alignment.

That would support designing resonators for **manufacturable representational equivalence**, rather than impossible spectral identity.

---

# GE-7 — Geometry and ring-down computation

## Question

Can geometry engineer modal decay constants so that ring-down improves representation quality after drive removal?

This connects to the existing dissipative temporal-filter hypothesis.

Design candidate structures intended to create:

- long-lived desired modes,
- rapidly decaying nuisance modes,
- or deliberately separated Q populations.

Sample representation quality at multiple post-drive delays.

Measure:

- within-state distance over time,
- between-state distance over time,
- recall accuracy over time,
- unknown-state rejection over time.

## Desired behavior

```text
immediately after drive-off:
  desired + nuisance modes

later:
  nuisance modes preferentially decay
  desired state structure remains
```

## Critical control

Apparent improvement must not be explained solely by convergence to one universal high-Q mode.

---

# GE-8 — Geometry-written ROM / identity

## Question

Can deliberate geometric features encode stable physical information distinguishable from manufacturing variation?

Candidate perturbations:

- laser-cut or machined notches,
- patterned holes,
- local mass deposits,
- controlled edge features,
- patterned damping patches.

## Protocol

Fabricate multiple nominal copies of multiple geometry codes.

The decoder must distinguish:

1. geometry code across devices, and
2. individual device identity within a geometry code.

This separates two possible information layers:

```text
intentional geometry
      ↓
logical ROM / product type

manufacturing microvariation
      ↓
individual physical identity / PUF candidate
```

## Claim boundary

Stable geometric identification is not by itself proof of secure PUF behavior.

---

# GE-9 — Inverse-design pilot

Only begin after GE-1 through GE-5 identify a metric that geometry can improve repeatably.

## Goal

Move from hand-designed geometry to optimization.

Possible loop:

```text
parameterized geometry
        ↓
FEM / reduced simulation
        ↓
predicted modal features
        ↓
representation objective
        ↓
optimizer
        ↓
candidate geometry
        ↓
fabricate + measure
```

Potential objective functions:

- maximize target/nuisance separation ratio,
- maximize effective rank subject to SNR constraint,
- maximize dropout robustness,
- minimize required readout channels,
- maximize cross-device alignability,
- shape Q/decay distribution.

Do not optimize generic “complexity” or mode count without an application-linked objective.

---

# Implications for MEMS

If these experiments are positive, future CWM MEMS design should not merely shrink the current square plate.

The resonator geometry itself becomes part of the algorithm.

A future design stack could be:

```text
application requirement
    ↓
required sensitivity + invariance
    ↓
representation objective
    ↓
resonator geometry
    ↓
transducer geometry / placement
    ↓
modal / ring-down response
    ↓
lightweight calibration
    ↓
canonical CWM representation
```

This could support application-specific CWM structures analogous to application-specific analog front ends.

---

# Implications for the CWM USB appliance

The USB appliance roadmap should keep the physical resonator replaceable.

Recommended architecture:

```text
host
 ↓ USB
controller / acquisition service
 ↓
interchangeable CWM resonator
```

The appliance should record a `geometry_id` and calibration version with every run.

That would allow the same software interface to compare:

- plain plates,
- anisotropic plates,
- notched resonators,
- future MEMS devices,

without changing host semantics.

Suggested future `STATUS` fields:

```json
{
  "geometry_id": "...",
  "device_id": "...",
  "calibration_id": "...",
  "representation_version": "..."
}
```

This is a design recommendation, not a claim that these geometries are equivalent today.

---

# Commercial implications if positive

Positive results would strengthen several existing commercial paths:

### Machine health

Design a resonator to amplify defect-related mechanical signatures while suppressing temperature/mounting nuisance variation.

### Structural health

Make boundary-condition sensitivity intentionally directional or location-specific.

### Robotics / tactile sensing

Use geometry to encode force location, direction, and magnitude in one mechanical body.

### Sparse always-on sensing

Engineer the resonator so useful state information is observable through a small readout budget.

### MEMS physical representation engines

Design the mechanical transfer function for a target latent representation rather than accepting whatever modal space fabrication happens to produce.

The commercial claim still requires full-system comparison against conventional sensors and electronics.

---

# What this article does NOT establish for CWM

The external flat-fiber work does not demonstrate:

- acoustic memory,
- associative recall,
- computation in CWM,
- CWM energy advantage,
- spectral page memory,
- writable CWM states,
- nonlinear reservoir computing,
- quantum behavior,
- or that flat geometry is optimal for CWM.

The transferable lesson is narrower and useful:

> **Wave-bearing structures can be deliberately shaped so that geometry changes what physical information becomes observable. CWM should test whether resonator geometry can similarly be designed around representation quality rather than treated as a fixed container for modes.**

---

# Recommended order

1. **GE-1:** simple controlled geometry census.
2. **GE-2:** directional anisotropy test.
3. **GE-4:** target-vs-nuisance sensitivity test.
4. **GE-5:** sparse-readout test.
5. **GE-3:** multi-variable held-combination decoding.
6. **GE-6:** cross-device alignment of promising geometry.
7. **GE-7:** engineered decay/Q test.
8. **GE-8:** geometry-coded ROM/identity.
9. **GE-9:** inverse design only after a useful metric is demonstrably geometry-sensitive.

---

# Decision gate

Advance geometry engineering toward MEMS only if a deliberately modified geometry produces a repeatable advantage over a matched plain reference on at least one application-relevant metric after controlling for SNR, signal amplitude, acquisition budget, and data leakage.

A particularly valuable result would be:

> **An engineered resonator preserves the same associative-state accuracy with fewer receivers/frequencies while simultaneously improving target-to-nuisance separation and remaining linearly alignable across nominally identical devices.**

That result would connect three currently separate CWM threads — distributed representation, linear transfer, and commercial readout efficiency — into a single hardware design principle.