# CWM as Classical Phononic Working Memory

**Status:** Proposed framing, architecture note, and experiment roadmap  
**Evidence level:** OPEN / architecture + protocol  
**Purpose:** Reframe the next CWM research question around frequency-addressed classical phononic working memory rather than a standalone acoustic computer.

This document is motivated by recent research using mechanical resonators as working-memory elements in a quantum-computing architecture. That work is not evidence that CWM is quantum, and CWM should not borrow quantum claims from it. The useful lesson is architectural:

> Mechanical resonators can be treated as first-class information-storage components, with processing and memory assigned to different physical subsystems.

For CWM, the corresponding question is:

> Can a classical acoustic or phononic resonator provide addressable, persistent or reconfigurable working-memory states that a small electronic processor can query, update, and reuse?

This is narrower than claiming that the present glass bench is a computer. It is also more aligned with what the current evidence can support and what the next experiments can test.

---

## 1. Recommended framing

### 1.1 Primary framing

Use:

> **CWM is a candidate classical phononic working-memory architecture based on frequency-addressed resonant modes, physical perturbation states, and associative recall.**

Alternative compact framing:

> **frequency-addressed phononic working memory**

### 1.2 Supporting framing

CWM may combine several functions:

```text
physical state storage
+ frequency-addressed page selection
+ acoustic feature transformation
+ associative retrieval
+ small electronic controller/readout
```

### 1.3 Avoid

Do not describe CWM as:

- a quantum computer;
- quantum memory;
- room-temperature quantum hardware;
- a general-purpose standalone processor;
- a proven compute-in-memory chip;
- a replacement for conventional RAM;
- a demonstrated MEMS technology before fabrication.

### 1.4 Key distinction

The external mechanical-memory architecture stores quantum states in resonant modes. CWM is classical and currently concerns one or more of the following:

```text
modal transfer functions
spectral fingerprints
physical perturbation states
frequency-addressed pages
stored template responses
trajectory/state cards
```

The mathematical or architectural resemblance does not erase the physical distinction.

---

## 2. Why “working memory” may be a better research target

Previous CWM discussions often asked whether the resonator itself could become the processor. That sets an unnecessarily broad bar.

A more focused architecture separates roles:

```text
small MCU / processor
        |
        | address, query, update command
        v
CWM phononic memory
        |
        | recalled page / physical response
        v
small digital readout and controller
```

This architecture can still be scientifically useful if the mechanical memory offers one or more of:

- compact multi-mode storage;
- frequency-addressed access;
- associative recall from partial queries;
- natural coupling to mechanical or acoustic sensors;
- low-energy passive retention or readout;
- high tolerance to missing modes or damaged sensors;
- object-bound identity or tamper sensitivity;
- reusable trajectory/state libraries.

The processor does not have to disappear. The research question is whether the resonator performs enough storage, selection, matching, or state transformation to justify its presence.

---

## 3. Memory vocabulary for CWM

CWM should use more precise terminology.

### 3.1 Mode address

A resonant frequency, frequency band, tone bundle, phase configuration, or mode identifier used to select a memory slot or page.

### 3.2 Memory state

The physical or logical state associated with the selected mode/page. Candidate states include:

- mass perturbation;
- local stiffness change;
- boundary-condition change;
- stress or strain state;
- writable shell/coating state;
- binary MEMS perturbation state;
- virtual excitation/readout projection;
- stored response template.

### 3.3 Memory content

What the state represents, for example:

- a class/template;
- a calibration profile;
- a trajectory segment;
- a next-state distribution;
- a physical identity;
- a sensor condition;
- a stored response page.

### 3.4 Read

Apply an address/query and measure the resonator response.

### 3.5 Write

Change the physical or logical state so a later query returns a different response.

### 3.6 Modify

Transform an existing stored state into another state, either physically or through a controlled virtual-page mapping.

### 3.7 Working memory

A memory used repeatedly during an active task, allowing address, retrieve, modify, write-back, and repeated retrieval.

---

## 4. Current CWM evidence relevant to working memory

The present bench should be described conservatively.

### Relevant measured or partially measured ingredients

- stable acoustic spectral fingerprints;
- high-dimensional linear physical kernel behavior;
- associative/content-addressable recall;
- partial-query completion;
- tolerance to heavy feature/mode dropout;
- two-path and three-path classical interference;
- trajectory/future-state recall experiments;
- repeated operation over a multi-hour soak;
- physical perturbation and rewritability work in earlier experiments and notes.

### Important limitations

- the current glass plate is not a standalone computer;
- most classification and decoding remain digital;
- present temporal reservoir claims were killed/reframed at the macro bench;
- the strongest physical write mechanism still needs a modern, publication-grade reversible demonstration under current criteria;
- frequency-addressed pages and bounded page cross-talk remain open;
- a MEMS unit cell has not been fabricated;
- readout, ADC/FFT, calibration, and control overhead have not been shown to beat conventional electronics.

### Honest current statement

> The present CWM bench demonstrates a classical acoustic feature map and associative-recall substrate. It motivates, but does not yet establish, a frequency-addressed phononic working-memory device.

---

## 5. Proposed architecture

### 5.1 Functional block diagram

```text
input or sensor state
        |
        v
query encoder / address generator
        |
        v
CWM resonator or resonator array
        |
        v
compact readout / page detector
        |
        v
MCU or application controller
        |
        +---- optional modify/write command ----+
                                                |
                                                v
                                      CWM state update mechanism
```

### 5.2 Division of labor

#### CWM performs

- physical storage or fixed-template retention;
- spectral page selection;
- physical feature transformation;
- interference/matching;
- partial-query associative response;
- optional trajectory/state retrieval.

#### Electronics perform

- page addressing;
- thresholding or compact decoding;
- control flow;
- write pulse or actuator control;
- task-level decisions;
- error correction and calibration.

The architecture is only compelling if the CWM block reduces energy, memory movement, readout complexity, latency, or sensor burden compared with a purely electronic implementation.

---

## 6. Primary experiment: CWM Working Memory Emulator

**Experiment ID:** CWM-WM1  
**Evidence target:** architecture demonstration first; physical-memory claim later.

### 6.1 Objective

Demonstrate explicit working-memory semantics:

```text
address
-> retrieve page
-> modify page
-> write/update page
-> retrieve modified page
-> repeat
```

The first version may use virtual rewriting to validate the architecture. Later versions must replace virtual state changes with physical perturbation or MEMS-relevant state changes.

### 6.2 Phase A: software and stored-data emulator

Use existing captured CWM matrices if available.

Represent several pages using:

- frequency bands;
- mode subsets;
- projection masks;
- tone bundles;
- stored page labels.

Operations:

1. address page A;
2. retrieve its stored class/trajectory/card;
3. apply a deterministic modification rule;
4. write the modified logical state to a new virtual projection/page;
5. retrieve again;
6. verify that page B and other pages are unchanged.

#### Metrics

- read fidelity;
- update fidelity;
- page cross-talk;
- number of update cycles;
- error accumulation;
- simple-readout complexity;
- reproducibility from saved data.

#### Success criterion

At least four pages should support repeated address/retrieve/modify/write-back cycles with:

```text
read accuracy >= 95%
update accuracy >= 90%
non-addressed page corruption <= 5%
```

These thresholds are provisional and should be predeclared in the runnable protocol.

#### Interpretation

A positive result validates working-memory architecture and software orchestration only. It does not establish physical writable memory.

### 6.3 Phase B: virtual rewrite on the bench

Use one physical resonator/array with multiple excitation/readout projections.

Procedure:

1. enroll page states;
2. select page by frequency/tone/projection;
3. read page;
4. change virtual page mapping;
5. read updated mapping;
6. verify page isolation;
7. repeat across power cycles and sessions.

#### Success criterion

The same physical substrate must behave as multiple selectable logical memories without changing hardware.

#### Interpretation

This demonstrates reconfigurable logical memory, not persistent physical write.

### 6.4 Phase C: physical write/read/erase loop

Use a reversible physical perturbation:

- controlled mass placement/removal;
- water/drop perturbation where appropriate;
- magnetic or mechanical actuator;
- MEMS-like binary contact/lift mechanism;
- stiffness/boundary-state actuator;
- writable coating or material-state proxy.

Procedure:

```text
baseline state S0
write S1
read S1
write S2 or erase to S0
read S2/S0
repeat N cycles
```

#### Required measurements

- state separability in sigma;
- position dependence;
- reversibility;
- retention time;
- write energy;
- write latency;
- read latency;
- endurance/cycle count;
- cross-session repeatability;
- effect on Q and mode rank.

#### Minimum success criterion

- each state separated by more than 3 sigma;
- at least three distinguishable states, including erase/baseline;
- at least 100 repeat cycles without monotonic degradation;
- cross-session read accuracy at least 95%;
- measurable retention after power removal;
- no unacceptable Q collapse.

### 6.5 Phase D: state modification without full digital re-enrollment

Test whether an existing page can be modified and re-read without rebuilding the complete digital decoder.

This is a crucial gate. If every write requires a full software retraining/enrollment pass, the device is closer to a reconfigurable sensor than practical working memory.

#### Success criterion

A compact calibration/update procedure should be enough to recognize the new state.

---

## 7. Experiment: frequency-addressed memory slots

**Experiment ID:** CWM-WM2

### Objective

Test the memory model:

```text
many resonant modes
-> many addresses
-> one state or page per address/band
```

### Method

1. partition measured modes into candidate slots/pages;
2. assign one page or state family to each slot;
3. query by tone/band;
4. record correct-page response;
5. query neighboring addresses;
6. calculate cross-talk matrix;
7. increase page count until fidelity fails.

### Metrics

- number of usable slots/pages;
- page fidelity;
- cross-talk;
- bandwidth per slot;
- address guard band;
- drift sensitivity;
- capacity scaling with additional plates/readout channels;
- effect of collisions and band diversity.

### Success criterion

At least three independently addressable pages with bounded cross-talk must be demonstrated before using “frequency-addressed memory” as a measured public claim.

---

## 8. Experiment: physical working memory for state trajectories

**Experiment ID:** CWM-WM3

### Objective

Demonstrate that CWM can store and retrieve trajectory segments or state transitions rather than only static labels.

### Candidate tasks

- Pong path segments;
- Lorenz attractor state transitions;
- Mackey-Glass sequences;
- toy neural oscillator states;
- drone vibration-state transitions;
- motion-heading cards.

### Memory representation

A page/card stores:

```text
current state signature
+ next-state pointer or distribution
+ confidence/weight
```

### Operations

1. query current partial state;
2. retrieve matching trajectory card;
3. retrieve next-state card;
4. optionally update weight/state;
5. repeat through a short sequence.

### Baselines

- software nearest-neighbor table;
- direct-wire features;
- software random kernel;
- small electronic lookup table;
- CWM physical features with identical readout.

### Success criterion

CWM must provide a measurable advantage under partial observations, missing features, or mode dropout. Clean closed-deck recall alone is insufficient to claim a dynamical-memory advantage.

### Preferred public wording if positive

> CWM supports physical associative retrieval of stored trajectory states under partial query.

Avoid “predicts the future” unless tested on genuinely unseen trajectories and fair forecasting baselines.

---

## 9. Experiment: processor-memory interface

**Experiment ID:** CWM-WM4

### Objective

Measure the real cost of querying CWM from a small processor.

### Required timing decomposition

```text
address generation
DAC/NCO setup
physical ring-up or propagation
capture
analog readout
ADC
FFT or compact detector
decision
optional write/update
```

### Required energy decomposition

```text
drive energy
actuator/write energy
preamplifier/readout energy
ADC/DAC energy
MCU/FFT energy
calibration overhead
idle/retention energy
```

### Baselines

Compare the same task against:

- MCU + SRAM lookup;
- flash/EEPROM lookup;
- accelerometer/DSP classifier where applicable;
- software kNN;
- small neural model;
- random projection + linear readout.

### Success criterion

CWM must demonstrate or credibly project an advantage for a specific task after all peripheral overhead is included.

A resonator-only energy number is not sufficient.

---

## 10. MEMS roadmap

### 10.1 Candidate unit-cell concepts

#### A. Beam or membrane resonator

- frequency-addressed modes;
- piezoelectric drive/readout;
- local perturbation or stress state;
- compact and fabrication-accessible;
- risk: limited independent modes and cross-talk.

#### B. Phononic crystal defect cavity

- localized addressable modes;
- engineered page isolation;
- strong geometry control;
- risk: fabrication precision, packaging, and calibration.

#### C. SAW/BAW-style delay or cavity device

- mature transduction concepts;
- useful temporal memory;
- risk: whether it offers unique CWM storage rather than standard filtering.

#### D. Binary perturbation-site resonator

- physical write by contact/lift or stiffness switching;
- natural discrete states;
- risk: actuator loss, endurance, routing, and Q penalty.

#### E. Writable-shell resonator

- continuous or multi-level tuning;
- possible phase-change, magnetostrictive, ferroelectric, or polymer state;
- risk: retention, repeatability, material loss, and write energy.

### 10.2 MEMS gating questions

1. What physical variable stores the state?
2. How is it written and erased?
3. How is a mode/page addressed?
4. How many independent pages survive fabrication variation?
5. What is the readout circuit?
6. What is the total energy including converters?
7. How much calibration is needed?
8. Does the state persist without power?
9. Can the state be modified without full retraining?
10. What task beats conventional electronics?

### 10.3 No-go rule

Do not proceed to expensive fabrication unless the macro/intermediate bench has demonstrated:

- repeatable page addressing;
- physical write/read/erase;
- bounded cross-talk;
- cross-session stability;
- a task-level advantage under a fair baseline;
- a credible interface and power budget.

---

## 11. Suggested scripts and artifacts

### Proposed scripts

```text
tools/cwm_working_memory_emulator.py
tools/cwm_page_address_test.py
tools/cwm_write_cycle_test.py
tools/cwm_trajectory_memory.py
tools/cwm_interface_budget.py
```

### Proposed data layout

```text
data/results/working_memory/<timestamp>/
  config.json
  raw_or_features.npz
  page_reads.json
  write_cycles.csv
  crosstalk_matrix.json
  timing_budget.json
  energy_budget.json
  summary.json
```

### Required metadata

- hardware topology;
- resonator/plate/rod identity;
- page addresses;
- write state and mechanism;
- capture parameters;
- decoder/readout model;
- random seeds;
- session/date/temperature;
- null tests;
- baseline configurations.

---

## 12. Claim ladder

### Level 0 — Architecture emulator

> A software-controlled CWM dataset can emulate address/read/modify/write-back semantics.

This is not a physical memory claim.

### Level 1 — Virtual phononic memory

> One physical resonator supports multiple selectable logical memory pages through excitation/readout projections.

This is reconfigurable logical memory, not physical state storage.

### Level 2 — Physical rewritable state

> A reversible physical perturbation stores distinguishable states that survive power removal and repeated readout.

This earns a classical physical-memory claim.

### Level 3 — Frequency-addressed working memory

> Multiple physical states/pages are independently addressed, retrieved, modified, and written back with bounded cross-talk.

This earns the working-memory framing.

### Level 4 — Task advantage

> CWM working memory improves a real task under fair latency, energy, robustness, or sensor-burden comparison.

This earns an application claim.

### Level 5 — MEMS demonstration

> A fabricated MEMS device preserves the memory operation and advantage.

This earns a MEMS technology claim.

---

## 13. Falsifiers and kill criteria

Reframe or stop the working-memory path if:

1. no reversible physical state can be read reliably across sessions;
2. page cross-talk grows too quickly with page count;
3. each write requires complete digital retraining;
4. retention is too short for the target application;
5. write/erase destroys Q or useful rank;
6. readout electronics dominate energy and latency;
7. SRAM/flash + MCU beats CWM on every fair benchmark;
8. useful behavior is only fixed feature extraction, not addressable memory;
9. physical writes cannot be distinguished from mounting/drift artifacts;
10. MEMS implementation requires unrealistic precision, packaging, or calibration.

A negative result does not erase the acoustic-feature-map or PUF/sensor work. It only rejects the stronger working-memory framing.

---

## 14. Recommended next-step sequence

### Priority 1 — Offline working-memory emulator

Use already captured data to implement page addressing, read, modify, write-back, and cross-talk accounting.

Purpose:

- validate terminology and interfaces;
- expose whether pages are truly independent;
- define file formats and metrics;
- avoid unnecessary bench work.

### Priority 2 — Reproduce physical rewrite under current standards

Run a controlled reversible perturbation experiment with modern signal-path controls.

Purpose:

- connect earlier write/rewritability evidence to the current claim ledger;
- measure retention and repeatability;
- distinguish memory state from mounting artifact.

### Priority 3 — Three-page physical memory demo

Combine page addressing and physical write/read states.

Purpose:

- establish the smallest credible phononic working-memory demonstration.

### Priority 4 — Trajectory-state memory benchmark

Use Pong, Lorenz, neural oscillator, or drone vibration trajectories.

Purpose:

- determine whether working memory helps a dynamical task.

### Priority 5 — Full power/latency/interface budget

Purpose:

- decide whether MEMS investment has an engineering basis.

---

## 15. Publication path

### Paper A: architecture and measured macro demonstration

Possible title:

> **Frequency-Addressed Classical Phononic Working Memory in a Multi-Mode Acoustic Resonator**

Required evidence:

- physical write/read/erase;
- multiple addresses/pages;
- bounded cross-talk;
- retention and endurance;
- simple readout;
- fair electronic baseline.

### Paper B: associative trajectory memory

Possible title:

> **Physical Associative Working Memory for Partial-State Trajectory Retrieval Using Acoustic Resonators**

Required evidence:

- trajectory/state-card task;
- partial-query advantage;
- cross-session repeats;
- direct-wire and software-kernel baselines;
- no future-prediction overclaim.

### Paper C: MEMS design study

Possible title:

> **Design Requirements for a MEMS Frequency-Addressed Phononic Working-Memory Device**

Required evidence:

- measured macro parameters;
- explicit unit cell;
- total interface/energy budget;
- fabrication tolerances;
- falsifiable scaling model.

---

## 16. Public-language guidance

### Preferred

- classical phononic working memory;
- frequency-addressed resonant modes;
- associative state retrieval;
- physical memory candidate;
- virtual and physical rewriting;
- trajectory-state memory;
- resonator-plus-controller architecture;
- projected MEMS path.

### Avoid

- quantum memory;
- acoustic qubit;
- room-temperature quantum computing;
- standalone acoustic CPU;
- proven compute-in-memory;
- processor-free general computation;
- GPU replacement;
- measured MEMS density/speed before fabrication.

---

## 17. Summary

The useful lesson from mechanical-resonator working-memory research is architectural, not quantum.

CWM should ask:

```text
Can a classical resonator provide
addressable modes/pages,
reversible physical states,
associative retrieval,
and repeated read/modify/write-back
for a small electronic controller?
```

The proposed sequence is:

```text
offline working-memory emulator
-> controlled physical rewrite
-> three-page addressable memory
-> trajectory-state benchmark
-> full energy/latency/interface budget
-> MEMS go/no-go
```

If successful, CWM's strongest contribution may be neither an acoustic computer nor a conventional ROM. It may be:

> **a classical frequency-addressed phononic working-memory architecture for embedded physical systems.**
