# Wave-Gate Scaling Roadmap

**Status:** OPEN / architecture + measurement plan  
**Purpose:** define what a scalable CWM-like wave gate would have to accomplish before comparing it with transistor-based computing, and turn the current glass bench into a measured path toward a microfabricated implementation.

---

## 1. The architectural shift

The current bench asks whether a physical wave system can implement a repeatable input/output transformation:

```
X -> H -> Y
```

PR #14 sharpens that into a physical symbol-gate question: can a fixed assembly map a standardized query to a reproducible output class?

The scaling question is different:

> **What form of H remains useful when the physical structure is made small enough, dense enough, isolated enough, and reproducible enough to integrate many such operations?**

The target is **not**:

> one acoustic resonator = one transistor.

A transistor is extraordinarily useful because it combines locality, gain/nonlinearity, state restoration, fan-out, reproducibility, and manufacturability.

A wave system may justify itself only if one physical propagation performs a transformation that would otherwise require many electronic operations.

The central scaling hypothesis is therefore:

```
one engineered wave transform H
    -> many useful coupled input/output relationships
    -> useful work per propagation that exceeds a one-gate comparison
```

---

## 2. What must scale

A wave gate becomes a candidate integrated primitive only when all of these are quantified.

### 2.1 Wavelength / physical size

For a propagating mode,

```
lambda = v / f
```

where:

- `v` is the relevant phase velocity;
- `f` is operating frequency;
- `lambda` is wavelength.

The present kHz glass bench is intentionally macroscopic. It should be treated as a physics emulator, not as a final density demonstration.

Moving toward MHz/GHz operation can reduce characteristic wave dimensions by orders of magnitude, but wavelength alone does not determine usable cell pitch.

The actual pitch is:

```
pitch = k_pitch * lambda
```

where `k_pitch` absorbs confinement, transducer, isolation, electrode, routing, and fabrication overhead.

### 2.2 Confinement and crosstalk

Neighboring cells cannot be useful if their fields are inseparable.

A scalable H requires measured:

- same-cell transfer;
- nearest-neighbor transfer;
- next-nearest-neighbor transfer;
- spectral leakage;
- substrate leakage;
- electrical feedthrough;
- package-mediated coupling.

The relevant metric is not merely Q. It is how much unwanted neighboring activity changes the frozen output decision.

### 2.3 Addressability

The architecture needs a way to ask one operation a question without accidentally asking all operations the same question.

Possible addressing dimensions include:

- physical port;
- frequency;
- phase;
- spatial mode;
- time slot;
- bias state;
- geometry / device identity.

Frequency multiplexing is particularly important for CWM because one structure may expose multiple useful dimensions without multiplying physical cells.

### 2.4 Regeneration / thresholding

A linear transfer function can transform and separate signals, but long cascades require restoration.

An integrated wave architecture must identify where the equivalent of a decision boundary lives:

```
Y < T -> logical 0
Y >= T -> logical 1
```

Possible implementations:

1. intrinsic material nonlinearity;
2. nonlinear mechanical/acoustic element;
3. tunable/bistable physical state;
4. piezoelectric wave-to-electronic threshold followed by electronic re-drive;
5. hybrid CMOS + wave cell.

A hybrid implementation is not a failure. The engineering question is whether H performs enough useful work to justify the conversion boundary.

### 2.5 Cascadability and fan-out

The output of one stage must be usable by a later stage:

```
X -> H1 -> Y1 -> interface -> H2 -> Y2
```

Measure:

- output signal level;
- interface energy;
- re-drive energy;
- latency;
- fan-out;
- accumulated error;
- need for recalibration.

### 2.6 Reproducibility across devices

The final question is not whether one specimen has a rich transfer function.

It is whether nominally equivalent devices provide:

- the same logical mapping directly;
- the same mapping after bounded calibration; or
- only device-specific mappings requiring full enrollment.

These are different product architectures and must not be conflated.

### 2.7 Readout burden

A structure that produces a 1,000-dimensional response but requires an expensive high-resolution ADC and large FFT for every operation may lose its physical advantage in the interface.

For each candidate H record:

- number of physical drive ports;
- number of sensed ports;
- number of frequency bins;
- ADC bits/sample;
- samples/query;
- digital operations/query;
- calibration storage;
- conversion energy.

PR #14's minimal-readout experiment is therefore a direct scaling experiment.

---

## 3. The correct comparison metric

Do not compare CWM with CMOS using resonator count versus transistor count.

Track at least four independent metrics.

### 3.1 Physical cell density

```
D_cell = 1 / pitch^2
```

for a planar square-pitch estimate.

This is a geometric ceiling, not a product density.

### 3.2 Effective independent transform dimension

Let `K_eff` be the number of independently useful input/output degrees of freedom that survive:

- held-session testing;
- crosstalk controls;
- nuisance variation;
- frozen decoding;
- intended readout constraints.

Do not substitute measured mode count for `K_eff`.

### 3.3 Useful transform throughput

A first architecture-level quantity is:

```
T_transform = D_cell * K_eff * query_rate
```

with units of effective transform-dimensions per area per second.

This is still not equivalent to transistor operations. It is a platform metric for comparing wave implementations with one another.

### 3.4 Useful transform efficiency

Track:

```
eta_transform = K_eff / E_system
```

per query, where `E_system` includes:

- waveform generation;
- drive amplifier;
- transduction;
- sensing;
- analog front end;
- ADC;
- digital readout;
- threshold/regeneration;
- calibration/refresh amortization where required.

The long-term comparison should be workload-level energy, latency, area, and accuracy—not an isolated physics-layer energy.

---

## 4. One H may represent many relationships

The key reason to pursue waves is parallel physical superposition.

For a linearized operating regime:

```
Y = H X
```

where H may be a matrix rather than a scalar.

If one cell reliably exposes N useful inputs and M useful outputs, the physical propagation embodies an N-to-M relationship simultaneously.

This does **not** mean every matrix element counts as an independent digital operation. Correlations, rank deficiency, readout cost, and noise reduce the effective dimensionality.

Therefore measure:

```
rank_eff(H)
```

under realistic noise and readout constraints.

The useful scaling question becomes:

> **How large can rank_eff(H) become per physical footprint, per joule, while remaining reproducible and addressable?**

That is more meaningful for CWM than "how many resonances exist?"

---

## 5. Candidate forms of H

This roadmap is material-agnostic. Candidate media/platforms should be scored using the same schema.

### 5.1 Fixed linear / weakly nonlinear resonator

Examples include the present glass system and future microfabricated resonators.

Strengths:

- stable mapping;
- straightforward characterization;
- potentially high spectral dimensionality.

Main open problem:

- whether readout and regeneration erase the system advantage.

### 5.2 Engineered phononic structure

Geometry intentionally controls propagation, confinement, mode coupling, and spectral response.

Strengths:

- H can be designed instead of merely discovered;
- spatial isolation and bandgaps may improve integration;
- geometry can encode useful transformations.

This connects directly to PR #11.

### 5.3 Piezoelectric thin-film acoustic device

Candidate material families include AlN/AlScN and thin-film lithium-niobate systems.

Why they are interesting:

- direct electrical-to-acoustic transduction;
- microfabrication;
- high-frequency operation;
- existing acoustic-device manufacturing ecosystem.

No candidate material should be selected from literature alone. The eventual platform must win the CWM-specific scorecard.

### 5.4 Tunable wave medium

A bias parameter changes H:

```
Y = H(theta) X
```

where `theta` could be field, strain, temperature, boundary condition, or material state.

This enables one physical structure to expose multiple transfer functions.

Tunability is valuable only if:

- switching energy is acceptable;
- state is stable long enough;
- states are reproducible;
- changing H does not destroy isolation;
- control complexity remains bounded.

### 5.5 Hybrid wave + CMOS primitive

The wave structure performs a high-dimensional transform; electronics perform thresholding, routing, regeneration, and control.

This is currently the default practical architecture unless experiments demonstrate that a fully physical cascade is superior.

---

## 6. Existing paper projections become targets, not evidence

`paper/cwm_core.md` contains projected MEMS density, mode count, energy, cost, and fabrication numbers.

For this roadmap, those values are **not accepted as established device performance**.

They should be treated as prior design hypotheses until each depends on measured or foundry-confirmed inputs.

In particular, do not use these as evidence in a funding/commercial claim until revalidated:

- projected modes per MEMS rod;
- bits per mode / bits per rod;
- packed density;
- read/write energy;
- associative-recall energy;
- per-die manufacturing cost;
- crosstalk assumptions;
- fabrication yield;
- claim that a specific process is immediately volume-ready.

The new scaling program replaces "project from macro physics" with:

```
measure primitive
-> quantify effective dimension
-> measure interface burden
-> model scaled geometry
-> obtain fabrication constraints
-> prototype
-> compare end-to-end
```

---

## 7. Work packages

### WG-0 — establish the physical symbol gate

Dependency: PR #14.

Goal:

- demonstrate a frozen Q -> H -> Y mapping;
- beat Ch B/electrical-only controls;
- reproduce across sessions;
- reduce readout to the smallest stable statistic.

**Gate:** no scaling claim advances without a reproducible driven primitive.

---

### WG-1 — measure effective dimensionality of the current glass H

Use existing and new raw captures.

For a fixed operating condition:

1. construct the measured complex transfer matrix across allowed drive/readout channels;
2. split complete sessions into training and held-out sets;
3. compute singular values using training data only;
4. estimate effective rank under measured noise;
5. test whether retained dimensions reproduce held-out;
6. repeat with restricted readout budgets.

Report:

- raw matrix dimensions;
- singular spectrum;
- effective rank versus SNR threshold;
- held-session effective rank;
- effective rank per receiver channel;
- effective rank per measured frequency.

**Question:** does one propagation genuinely provide multiple independent useful relationships?

---

### WG-2 — multiplexing / simultaneous-query test

Drive multiple allowed inputs simultaneously.

Compare:

```
measured multi-input Y
```

against:

```
sum of independently measured single-input responses
```

Measure:

- superposition error;
- inter-channel crosstalk;
- decoding accuracy;
- maximum simultaneous query count;
- readout growth with query count.

Linear superposition is a valid useful result. Nonlinearity must be measured rather than assumed.

**Gate:** show that multiplexing increases useful work faster than it increases readout burden.

---

### WG-3 — threshold / regeneration architecture

Implement two paths.

#### WG-3A: hybrid threshold

```
wave H -> minimal analog readout -> comparator -> clean digital state
```

Measure total energy/latency.

#### WG-3B: physical nonlinear threshold

Only if a candidate nonlinear/tunable element is available.

Compare the complete systems.

**Gate:** identify a credible way to cascade at least two physical transforms without uncontrolled error growth.

---

### WG-4 — confinement benchmark

Build or simulate two neighboring H cells with realistic coupling, then validate experimentally when hardware exists.

Metrics:

- desired response;
- neighbor-induced response;
- isolation in dB;
- logical-error change from active neighbor;
- dependence on spacing;
- dependence on frequency;
- electrical versus mechanical crosstalk.

**Gate:** derive a measured or conservatively modeled `k_pitch` for density estimates.

---

### WG-5 — cross-device transfer

Dependency: PR #8 and PR #14.

For at least two nominally equivalent devices, compare:

1. zero calibration;
2. bounded calibration;
3. full enrollment.

Record calibration samples, bytes, compute, and time.

**Gate:** determine whether the architecture is device-specific, factory-calibrated, or interchangeable.

---

### WG-6 — candidate-platform scorecard

Every proposed MEMS/phononic medium must populate `schemas/wave_gate_candidate.schema.json`.

Required categories:

- wave type;
- phase/group velocity range used for calculation;
- candidate operating band;
- transduction;
- expected confinement mechanism;
- tunability/nonlinearity;
- proposed cell dimensions;
- proposed pitch;
- measured/literature/foundry provenance for each input;
- unresolved fabrication risks.

Run `tools/wave_gate_scaling.py` to generate only geometric/wavelength-derived quantities.

Do not mix derived quantities with measured performance.

---

### WG-7 — foundry / fabrication reality check

Before a custom mask:

- select 2–3 candidate platforms;
- obtain actual design-rule constraints;
- ask about minimum acoustic feature sizes;
- electrode routing;
- release/suspension limits;
- packaging;
- wafer stack;
- yield;
- minimum order / prototype cost;
- available PDK or reference resonator.

Update the candidate records with source and date.

**Gate:** retire candidates whose proposed H cannot be fabricated with a plausible prototype path.

---

### WG-8 — first micro-scale test structure

Do not fabricate a full "CWM chip."

Fabricate the smallest structure that tests the scaling assumption:

- one reference cell;
- one H cell;
- one neighboring aggressor cell;
- electrical loopback/reference structures;
- multiple spacings;
- multiple transducer geometries.

Primary outputs:

- transfer matrix;
- isolation;
- process variation;
- calibration burden;
- readout energy;
- repeatability.

---

### WG-9 — workload comparison

Only after WG-8.

Choose one task where one wave transform plausibly replaces multiple electronic operations.

Examples:

- fixed template/matched-filter decision;
- low-dimensional sensor fusion;
- frequency-multiplexed classification;
- physically structured feature projection.

Compare end-to-end against:

- sensor + MCU/DSP;
- equivalent analog filter/bank;
- simple CMOS/digital implementation.

Measure:

- accuracy;
- latency;
- joules/query;
- area including interface;
- calibration;
- idle power;
- lifetime drift.

A scalable wave architecture needs a workload win, not merely a novel device.

---

## 8. Quantitative design sheet

For each candidate, record:

```
v_wave
f_operating
lambda
k_pitch
pitch
ideal_cells_per_mm2
K_eff
query_rate
drive_energy
sense_energy
conversion_energy
regen_energy
calibration_energy_amortized
isolation_db
held_session_error
cross_device_error
calibration_samples
```

Derived values:

```
lambda = v_wave / f_operating
pitch = k_pitch * lambda
D_cell = 1 / pitch^2
T_transform = D_cell * K_eff * query_rate
E_system = drive + sense + conversion + regen + calibration_amortized
eta_transform = K_eff / E_system
```

The provided calculator intentionally computes only transparent geometric and bookkeeping quantities.

---

## 9. Success ladder

### Tier 0 — macro physical transform
One repeatable glass Q -> H -> Y mapping.

### Tier 1 — multiplexed transform
One structure demonstrates `K_eff > 1` under held-session controls.

### Tier 2 — cascadable hybrid primitive
Two stages operate with measured regeneration/interface cost.

### Tier 3 — bounded-pitch architecture
Measured/supported confinement gives a credible integrated cell pitch.

### Tier 4 — cross-device architecture
Equivalent logical mapping transfers with bounded calibration.

### Tier 5 — microfabricated H
A fabricated device reproduces the intended transform and isolation.

### Tier 6 — workload advantage
End-to-end energy/latency/area is competitive for one bounded task.

Do not jump from Tier 0 to transistor-density comparisons.

---

## 10. Falsifiers

This direction should be narrowed or stopped if:

- `K_eff` collapses to ~1 once held-session/noise controls are applied;
- useful dimensions require proportionally equal ADC/readout cost;
- neighboring-cell crosstalk forces pitch so large that density loses relevance;
- every stage requires full digital reconstruction before the next H;
- cross-device variation requires full per-device retraining;
- conversion/regeneration energy dominates the workload;
- a conventional sensor + filter/MCU implementation wins decisively with no compensating advantage.

These are valuable outcomes because they tell us what H cannot be.

---

## 11. Near-term execution order

1. Complete the PR #14 binary physical-gate experiment.
2. Run WG-1 effective-rank analysis on raw dual-channel data.
3. Run WG-2 simultaneous-query/superposition tests.
4. Implement WG-3A with an intentionally simple comparator/readout.
5. Define the first candidate-platform JSON records.
6. Use the scaling calculator to explore wavelength/pitch envelopes without treating them as product claims.
7. Begin foundry conversations only after the required H and readout are known.
8. Design a three-cell test structure: reference, H cell, neighbor aggressor.

---

## 12. Research framing

The broad program can be stated as:

> CWM investigates whether engineered wave transfer functions can provide dense, repeatable physical transformations whose useful information-processing work per propagation justifies their interface and fabrication cost.

The key phrase is **work per propagation**.

The wave system does not need to beat CMOS at being a transistor. It needs an H for which the physics performs a sufficiently rich transform that CMOS would otherwise spend meaningful area, time, or energy computing.

That is the scaling thesis to test.
