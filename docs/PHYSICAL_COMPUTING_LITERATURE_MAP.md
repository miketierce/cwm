# Physical-Computing Literature and Claim Map

**Status:** living research note  
**Primary use:** preserve external references that materially shape CWM hypotheses, experiments, architecture, or claim boundaries.  
**Related execution PR:** #16 — K_eff and relational compute vs readout complexity

This document is intentionally not a conventional bibliography.

Every reference should answer four questions:

1. **What mechanism did the cited work actually demonstrate?**
2. **What does that teach or validate for CWM?**
3. **What does it NOT establish for CWM?**
4. **What experiment, architecture, or claim should change because of it?**

When adding a new paper, prefer the primary publication, record the DOI and publication date, and separate experimental results from simulation/system-level modeling.

---

## 1. Core architecture map

The emerging CWM architecture can be separated into layers:

```
physical input / encoded query
        |
        v
+-------------------------+
| fast physical transform |
|        H or H(S)        |
+-------------------------+
        |
        v
+-------------------------+
| compressed / relational |
|        readout Y        |
+-------------------------+
        |
        v
+-------------------------+
| optional persistent     |
| state / adaptation S    |
+-------------------------+
```

Relevant literature now falls into several categories:

- **integrated phononic transform H**
- **acoustic interference / relational logic**
- **path-sum / coherent-amplitude structure**
- **persistent programmable state S**
- **stateful/neuromorphic physical comparators**
- **physical-device -> hardware-constrained software co-design**
- **alternative tunable/stateful media**

The CWM fast track is currently concentrated on:

```
fixed H
  +
frequency/path parallelism
  +
compressed relational readout
```

before attempting persistent programmability or adaptive state.

---

# 2. Integrated nonlinear phononic computing

## Ji et al. — synthetic-domain phononic computing

**Citation**

Jun Ji, Zichen Xi, Joseph G. Thomas, et al.,  
"Synthetic-domain computing and neural networks using lithium niobate integrated nonlinear phononics,"  
*Nature Electronics* 8, 698-708 (2025).  
Published 25 August 2025.  
DOI: https://doi.org/10.1038/s41928-025-01436-9

### Demonstrated mechanism

An integrated lithium-niobate phononic device encodes vectors and matrices concurrently across multiple frequency dimensions within a **single nonlinear acoustic device**.

The work demonstrates:

- single-device frequency-domain parallelism;
- matrix operations;
- intrinsic phononic nonlinearity;
- device-aware neural-network operation;
- four-class classification with reported 98.2% accuracy;
- temperature characterization up to 192 C.

### What it teaches CWM

This strongly validates the general proposition that:

```
one physical phononic device
  -> multiple frequency dimensions
  -> parallel useful transformation
```

is a serious integrated-computing architecture.

It also supports PR #15/#16 emphasis on **work per device / work per propagation**, rather than one resonator = one transistor.

The paper explicitly identifies device-to-device variation as a scaling problem and uses many frequency dimensions in one device as part of the solution. That aligns directly with the CWM hypothesis that useful dimensionality should be extracted from one H before multiplying physical cells.

### What it does NOT establish for CWM

It does not show that:

- CWM glass has useful K_eff;
- CWM path interference provides a workload advantage;
- CWM readout complexity grows sublinearly;
- CWM's specific physical-symbol-gate architecture is novel;
- bulk glass is the correct scaled medium.

### CWM consequence

Treat integrated lithium-niobate phononics as a **credible downstream platform**, not as proof of the current bench.

The fast-track experiment should determine whether the CWM abstraction contributes something beyond generic frequency-domain matrix computing.

---

# 3. Classical acoustic analog computing and logic prior art

## Zuo et al. — acoustic analog computing metasurfaces

**Citation**

Shuyu Zuo, Qi Wei, Ye Tian, Ying Cheng, Xiaojun Liu,  
"Acoustic analog computing system based on labyrinthine metasurfaces,"  
*Scientific Reports* 8, 10103 (2018).  
Published 4 July 2018.  
DOI: https://doi.org/10.1038/s41598-018-27741-2

### Demonstrated mechanism

Designed acoustic metasurfaces shape amplitude and phase to implement mathematical transfer functions. The paper numerically demonstrates an acoustic system for solving nth-order ordinary differential equations using Fourier-transform and spatial-filter blocks.

### What it teaches CWM

The broad proposition:

> design an acoustic transfer function H so the physics performs a mathematical operation

is established prior art.

CWM should not claim novelty merely for "using acoustics as analog computation" or "designing H to perform an operation."

### CWM consequence

Novelty, if any, must lie in narrower architecture such as:

- specific encoding/readout relationship;
- fixed-cost multiplexing;
- held-session standardized mapping;
- path/frequency relational-compute compression;
- calibration architecture;
- programmable/tunable implementation;
- workload-specific advantage.

---

## Wang et al. — binary-phase passive acoustic logic

**Citation**

Yin Wang, Jian-ping Xia, Hong-xiang Sun, Shou-qi Yuan, et al.,  
"Binary-phase acoustic passive logic gates,"  
*Scientific Reports* 9, 8355 (2019).  
Published 7 June 2019.  
DOI: https://doi.org/10.1038/s41598-019-44769-0

### Demonstrated mechanism

Subwavelength passive acoustic waveguides use **linear acoustic interference** and binary phase manipulation to realize:

- OR;
- NOT;
- AND;
- XOR;
- XNOR;
- NOR;
- NAND;
- a more complex composite logic relation.

The XNOR implementation uses interference and a fixed pressure threshold.

### What it teaches CWM

This is particularly important for FT-3P.

It means CWM cannot claim novelty simply because:

```
phase-coded acoustic paths
  -> interference
  -> threshold
  -> XNOR/parity-like output
```

has already been demonstrated.

### What it does NOT eliminate

The CWM question can still be different if it demonstrates:

- one reusable physical H supporting many relations;
- measured growth of relational complexity at fixed RX cost;
- simultaneous frequency + path-domain parallelism;
- later-session frozen calibration;
- adaptable/programmed relational transfer functions;
- workload-level compute/readout advantage.

### CWM consequence

The FT-3P two-bit XNOR experiment is a **control/qualification primitive**, not a novelty result.

Its purpose is to verify our apparatus and establish cross-session/control discipline before moving to richer path relationships.

---

# 4. Sum-over-paths structural analogy

## Wen et al. — experimental test of Feynman path-integral postulates

**Citation**

DOI: https://doi.org/10.1126/sciadv.aeh1011  
*Science Advances* (2026).

### Demonstrated mechanism

The experiment reconstructs a large number of possible single-photon paths and tests the coherent summation of complex quantum probability amplitudes associated with those paths.

The cited experiment uses a discretized multi-stage construction with:

```
17^5 = 1,419,857
```

possible paths.

### What it teaches CWM

The useful connection is structural rather than quantum:

```
many allowed contributions
  -> coherent complex sum
  -> one observable
```

A classical elastic plate likewise produces an aggregate result from many propagation/modal contributions.

This motivated the explicit **path-space parallelism** branch in PR #16.

### Claim boundary

CWM must not describe its current room-temperature PZT/glass apparatus as:

- a quantum path-integral computer;
- a single-phonon system;
- a test of Feynman's quantum postulates.

The valid language is:

> classical elastic coherent path summation

or:

> a classical-wave analogue of a sum-over-paths computation pattern.

### CWM consequence

Historical CWM data already show two- and three-path interference.

The remaining useful question is not "do paths interfere?" but:

> Can increasingly rich path relationships be made stable, programmable, and useful before a nearly fixed-cost receiver?

See:

- `docs/PATH_SUM_INTERFERENCE_FAST_TRACK.md`
- `docs/PATH_SUM_FT0_EXISTING_DATA_NOTE.md`

---

# 5. Persistent physical state / programmable H

## Qi et al. — wafer-scale sliding-ferroelectric rBN memory

**Citation**

Jiajie Qi, Tian Gu, Jingfang Tu, et al.,  
"Single-crystal rhombohedral boron nitride wafers for integrated sliding ferroelectric memory,"  
*Nature Nanotechnology* (2026).  
Published 29 September 2026.  
DOI: https://doi.org/10.1038/s41565-026-02280-4

### Demonstrated mechanism

The work reports reproducible 4-inch single-crystal rhombohedral boron nitride wafers and rBN-based FeFET memory with:

- nanosecond-scale switching;
- >2 x 10^9 endurance cycles;
- projected 10-year non-volatility;
- ~10^6 on/off ratios in arrays;
- operation at 30 nm channel length.

### What it teaches CWM

This paper is relevant primarily to a **future programmable-state layer**, not to the current fixed-H fast track.

If a persistent material state S can modulate a phononic/acoustic transfer function:

```
Y = H(S) X
```

then a wave processor could potentially retain its programmed configuration without continuous bias.

### What it does NOT establish

The paper does not show:

- rBN as a useful acoustic computing medium;
- ferroelectric polarization changing a CWM-like phononic H;
- a nonvolatile phononic weight;
- coupling between rBN state and our intended wave operator.

The missing engineering derivative is essentially:

```
dH_acoustic / dS_ferroelectric != 0
```

with useful magnitude, stability, and energy.

### CWM consequence

Do not add rBN to current FT-1 through FT-6 hardware.

Track it as a candidate future **STATE -> H programming interface** only after a useful fixed H is established.

---

# 6. Physical relational comparator + hardware-derived system model

## Cho et al. — triboelectric-gated neuromorphic tactile device

**Citation**

Hanseong Cho, Seoyeon Park, Youngmin Lee, Sejoon Lee,  
"Self-Powered Flexible Triboelectric-Gated Ion-Gel Transistor for Neuromorphic Tactile Sensing and Human Activity Recognition,"  
*Advanced Materials* 38, e20540 (2026).  
First published 9 March 2026.  
DOI: https://doi.org/10.1002/adma.202520540

### Demonstrated mechanism

A P(VDF-TrFE)-based triboelectric nanogenerator directly drives a graphene-channel ion-gel transistor.

The device demonstrates:

- mechanical-stimulus-driven synaptic response;
- multiple decay regimes (~70 ms, 0.2-0.45 s, >2 s);
- spike-rate-dependent plasticity;
- frequency-dependent potentiation/depression;
- a parity point when pre/post spike rates match;
- behavior described by the authors as an analog frequency comparator.

For the human-activity-recognition result, experimentally measured LTP/LTD/device kernels were fitted and used in a **software single-layer perceptron simulation**. The reported >88% HAR result is therefore hardware-constrained system modeling, not a 384-synapse fully physical classifier.

### What it teaches CWM — lesson 1: relational output can be the primitive

The important abstraction is:

```
two physical streams
  -> device dynamics evaluate their relationship
  -> small analog state/output
```

The value is not necessarily high-dimensional output.

A one-dimensional observable may encode a useful relationship such as:

```
f_pre < f_post
f_pre = f_post
f_pre > f_post
```

This is directly relevant to PR #16's distinction between:

```
K_eff scaling
```

and:

```
relational-compute compression
```

### What it teaches CWM — lesson 2: build a primitive library

Do not test only "capacity."

Candidate physical relation operators include:

| encoded variables | physical relation | possible compact output |
|---|---|---|
| phase phi1, phi2 | phase equality/difference | match / no-match |
| frequency f1, f2 | frequency separation/order | near / far or sign |
| amplitude A1, A2 | amplitude ratio | greater / less |
| ports i, j | spatial compatibility | compatible / not |
| time t1, t2 | interval/window relation | inside / outside |
| P coherent paths | weighted relational score | scalar score/class |

These should eventually be compared by:

```
useful relational work
----------------------
readout + digital ops + energy
```

rather than K_eff alone.

### What it teaches CWM — lesson 3: hardware-constrained software co-design

The paper provides a useful development pattern:

```
measure physical primitive
  -> fit measured device kernel
  -> insert measured kernel/noise into software workload
  -> test system-level usefulness
  -> fabricate/scale only if justified
```

CWM should adopt this explicitly.

After FT-3/FT-3P produce a measured H, relational kernel, noise model, and drift model, build **hardware-constrained software benchmarks** before proposing many-cell fabrication.

Reporting language should distinguish:

> "A software model constrained by measured CWM hardware achieved X"

from:

> "The physical CWM device performed X."

### What it teaches CWM — lesson 4: sensor-compute fusion

Their mechanical stimulus directly generates the signal that drives the neuromorphic device.

This supports a potentially strong CWM commercial direction:

```
physical vibration/event
  -> engineered H
  -> compact relation/class/score
```

instead of:

```
sensor
  -> high-rate ADC
  -> full waveform
  -> DSP
  -> feature extraction
  -> classifier
```

The most defensible CWM advantage may ultimately come from reducing conversion/data-movement cost by performing useful physical transformation **before full digitization**.

### What it does NOT establish for CWM

It does not show:

- acoustic/phononic path computing;
- our glass acting as stateful memory;
- a CWM frequency comparator;
- a CWM learning rule;
- scalable CWM hardware.

It supports architecture/methodology, not CWM performance.

### CWM consequence

Add a future **Physical Relation Operators** track after the core FT-3P controls.

Do not interrupt the current frozen-H experiments to add stateful materials.

---

# 7. Stateful/tunable medium precedent

## Crepaldi et al. — ferrofluid in-memory computing

**Citation**

Marco Crepaldi, Charanraj Mohan, Erik Garofalo, Andrew Adamatzky, Konrad Szacilowski, Alessandro Chiolerio,  
"Experimental Demonstration of In-Memory Computing in a Ferrofluid System,"  
*Advanced Materials* 35, 2211406 (2023).  
First published 15 March 2023.  
DOI: https://doi.org/10.1002/adma.202211406

### Demonstrated mechanism

A water-based Fe3O4 ferrofluid is electrically programmed using quasi-DC signals and interrogated at RF.

The authors report:

- memristive behavior;
- short- and long-term information storage;
- plasticity;
- digit classification;
- physical reservoir-computing experiments.

### What it teaches CWM

A physical medium can combine:

```
state
+
dynamics
+
readout
```

without conventional solid-state crossbar architecture.

This remains useful precedent for a possible future:

```
Y = H(X; S)
```

where S is an intentionally controllable material state.

### What it does NOT establish

It does not establish ferrofluid as the correct CWM medium, nor that magnetic tunability will improve our acoustic H.

### CWM consequence

Treat ferrofluid as a **future tunable/stateful-medium experimental family**, not as a replacement for the fixed glass fast track.

---

# 8. Working synthesis

The literature now suggests a layered architecture rather than one miracle material:

```
                PROGRAM / STATE
                     |
                     v
              +-------------+
              |     S       |
              | ferro/state |
              +-------------+
                     |
                     v
physical X -> +-------------+ -> compact Y
              |    H(S)     |
              | wave/path   |
              | transform   |
              +-------------+
                     |
                     v
                threshold /
                low-bit ADC
```

Possible specialization:

- **phononic structure:** fast transform;
- **path/frequency interference:** relational computation;
- **ferroelectric/magnetic/stateful layer:** persistent configuration/adaptation;
- **CMOS:** routing, exact state, regeneration, memory, software.

The current experiment should remain narrower:

```
prove useful fixed H
  -> prove later-session stability
  -> prove controls
  -> quantify K_eff and relational work vs readout
  -> only then introduce programmable state
```

---

# 9. Literature-derived experimental backlog

These are not all immediate experiments.

## Near-term — PR #16

1. frozen later-session H;
2. Ch-B/electrical-only controls;
3. spectral K_eff frontier;
4. path relational-compute frontier;
5. minimal readout;
6. 3-path freeze then 4-path extension.

## Next layer — workload co-design

After a primitive passes:

1. extract measured H/kernel;
2. capture measured noise and session drift;
3. simulate real workloads using those measured constraints;
4. compare to conventional sensor + DSP/MCU baseline;
5. identify one workload where physical preprocessing is advantageous.

Candidate classes:

- matched filtering;
- vibration/anomaly detection;
- RF pattern recognition;
- sensor fusion;
- correlation/template matching;
- relational threshold tasks.

## Later — programmable/stateful H

Only after fixed-H usefulness:

1. identify state variable S;
2. demonstrate reproducible H(S);
3. measure programming energy/time;
4. measure retention;
5. measure number of useful H states;
6. test whether state programming changes relational/K_eff frontier.

---

# 10. Citation and claim hygiene for future papers

For every new external paper added here, record:

```
title
authors
journal
year
publication date
DOI
mechanism
experimental vs simulation status
what it supports
what it does not support
which CWM experiment/claim it changes
```

Before using a paper in a patent, grant, or manuscript:

1. verify the primary source;
2. distinguish publication date from received/accepted date;
3. inspect whether the claimed result was physical hardware, simulation, or hardware-derived software modeling;
4. avoid citing classification accuracy as a physical-device result if inference was simulated;
5. avoid using "quantum" language for classical coherent-wave phenomena;
6. search earlier prior art before treating a recently discovered paper as the first demonstration;
7. preserve dated CWM repo commits and experimental records separately from literature discovery dates.

The purpose of this file is not to prove CWM novelty.

It is to ensure that CWM's eventual claims are **narrower, better sourced, and harder to fool ourselves about**.
