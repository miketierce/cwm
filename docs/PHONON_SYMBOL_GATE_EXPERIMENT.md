# Phonon Symbol Gate: Hardware, Data, and Experiment Program

**Status:** OPEN / protocol only  
**Purpose:** test whether a fixed CWM assembly can implement a repeatable, physics-backed input/output mapping with adequate separation to behave as a small physical symbol gate.

## 1. The abstraction being tested

This program does **not** claim that phonics and phonons are the same scientific field. The useful common abstraction is narrower:

```
symbol/intention -> encoded vibration -> physical channel -> measured vibration -> decoded symbol
```

For speech, biology supplies the encoder, acoustic channel, sensor, and learned decoder. For CWM, the experiment supplies those pieces explicitly.

The proposed CWM primitive is:

```
query q_i -> fixed physical assembly H -> response y_i -> fixed readout g(y_i) -> symbol s_j
```

The central claim under test is not memory from ringdown. It is that a fixed assembly can perform a repeatable driven transformation whose outputs can be assigned discrete meanings by a fixed contract.

A measured decay time is not required.

## 2. What would count as a "phonon gate"

A useful gate requires more than seeing resonance peaks.

For a finite input alphabet Q = {q0, q1, ... qN}, define an output statistic z = g(y).

A gate exists operationally if:

1. the same allowed input repeatedly produces the same output class within tolerance;
2. different allowed inputs produce output distributions with adequate decision margin;
3. a decoder frozen before the test classifies held-out trials and later sessions;
4. the mapping is not reproduced by the electrical path alone;
5. the mapping survives defined nuisance variation, or the required calibration burden is explicitly measured.

This is a **physical input/output primitive**. Semantic meaning is assigned externally. The glass does not need to "understand" a symbol.

## 3. Competing hypotheses

### H0 — electronics / measurement artifact

The apparent mapping is explained by the drive chain, scope timing, gain, clipping, FFT choices, or another non-glass path. Removing or bypassing the glass preserves the classification.

### H1 — device-specific driven physical gate

A fixed glass/PZT assembly implements a reproducible transfer function. A finite standardized query alphabet produces separable outputs across repeats and later sessions.

### H2 — calibrated interchangeable gate

Nominally equivalent devices implement the same logical mapping after a bounded factory calibration.

### H3 — hardware-standardized gate

Nominally equivalent devices implement the same logical mapping with one fixed query/readout specification and little or no per-device calibration.

The program should stop at the highest hypothesis actually supported.

## 4. Existing hardware to reuse

Use the validated bench described in `HARDWARE.md`:

```
PicoScope AWG
    |
Board D drive buffer
    |
TX PZT
    |
glass / resonator under test
    |
RX PZT
    |
Board A preamp
    |
PicoScope Ch A  = acoustic/plate response

Drive bus tee
    |
PicoScope Ch B  = simultaneous electrical reference
```

The Ch B reference is mandatory for the primary complex-transfer measurements. The existing `tools/phase_census_chb.py` method computes:

```
H(f) = Z_A(f) / Z_B(f)
```

which cancels common drive phase and capture-time jitter at driven frequencies.

### Recommended additions

These additions are useful but should not block the first run:

- temperature sensor attached near the resonator but mechanically isolated from the active region;
- fixture ID / torque or clamp-position record;
- removable electrical loopback/self-test route;
- repeatable plate registration marks;
- second nominally identical resonator assembly for the cross-device phase.

No new high-voltage or exotic hardware is required for the first gate test.

## 5. Measurement states and controls

Every session must contain all of these states.

| State | Meaning | Purpose |
|---|---|---|
| GLASS | normal TX -> glass -> RX path | candidate physical gate |
| LOOPBACK | drive presented to both scope channels | scope/reference floor |
| ELECTRICAL_ONLY | TX drive active while acoustic path is mechanically interrupted or RX is isolated, with wiring unchanged where practical | feedthrough/background control |
| QUIET | drive off | noise floor |
| REASSEMBLED | same glass after a controlled remount/restart | calibration burden |
| DEVICE_B | second nominally equivalent assembly | cross-device transfer |

The exact ELECTRICAL_ONLY implementation must be documented in the manifest. It is not acceptable to silently change multiple parts of the signal chain.

## 6. Phase A — characterize before defining the alphabet

Do not choose logical encodings first and then search for confirming frequencies.

Perform a preregistered characterization sweep over a hardware-safe range already demonstrated by the bench.

For each candidate frequency:

- capture Ch A and Ch B simultaneously;
- save raw time-domain samples for both channels;
- calculate complex transfer `H = Za/Zb`;
- repeat at least 20 independent acquisitions;
- record clipping, full-scale utilization, SNR, magnitude CV, and phase circular SD;
- repeat the sweep in at least three independent sessions, including one power cycle.

The sweep produces a **candidate map**, not yet a gate.

### Candidate-selection rule

Select candidate queries using training sessions only.

A frequency or multitone query is eligible if:

- Ch B does not clip;
- Ch A does not clip;
- response exceeds a preregistered SNR floor;
- within-query repeatability is acceptable;
- separation from at least one other query is larger than repeat variability;
- the same separation is not present in ELECTRICAL_ONLY.

Freeze the selected query set before collecting the final evaluation data.

## 7. Phase B — build the smallest possible alphabet

Start with a binary alphabet.

```
Q0 -> expected output class Y0
Q1 -> expected output class Y1
```

The transmitter only needs the standard definitions of Q0 and Q1. It does not need a live catalogue of every resonance.

Use equalized drive power where possible so the gate cannot be solved by trivial input amplitude.

### Query forms

Test in this order:

1. single fixed-frequency tones;
2. two-tone queries with fixed relative phase;
3. multitone queries generated from a frozen query table;
4. optional temporal/rhythm queries only after the static driven gate is characterized.

The first success criterion should be deliberately small: one physical binary operation with a fixed decoder.

## 8. Phase C — freeze the readout

Two readouts should be evaluated.

### C1. Full complex-transfer baseline

Use a small vector of selected complex `H(f)` values. This is the high-information reference.

### C2. Minimal physical readout

Reduce the readout to the smallest useful statistic, for example:

- one magnitude;
- one phase;
- one weighted sum of magnitudes;
- one RMS/envelope measurement from a multitone response.

The stronger result is not merely high classification accuracy. It is a useful decision with **less readout burden**.

The readout rule must be frozen before the held-out test.

## 9. Phase D — blinded held-out gate test

Generate randomized, blinded query order.

Minimum recommended dataset per session:

- 2 query classes initially;
- >= 100 trials/class/session;
- >= 3 independent sessions;
- at least one complete power cycle between sessions;
- at least one remount/re-registration session;
- LOOPBACK, ELECTRICAL_ONLY, and QUIET controls interleaved.

Do not tune thresholds on the final session.

Primary metrics:

- balanced accuracy;
- confusion matrix;
- false-positive / false-negative rates;
- output-margin distribution;
- within-class coefficient of variation;
- between-class effect size;
- abstention/UNKNOWN rate if confidence thresholding is used.

Report raw counts as well as percentages.

### Suggested initial gate

Advance H1 if all are true:

- held-session balanced accuracy >= 95%;
- each class has >= 5 standard deviations of separation in the frozen scalar readout **or** an equivalently preregistered margin metric;
- ELECTRICAL_ONLY performance is near chance and materially worse than GLASS;
- no clipping or invalid-reference condition explains class membership;
- the result reproduces after a power cycle.

These thresholds are engineering targets, not established field standards.

## 10. Phase E — nuisance boundaries

Once the gate works in a stationary session, deliberately measure its boundaries.

Change one factor at a time:

- temperature;
- drive amplitude;
- mount/remount;
- TX/RX coupling pressure if controllable;
- cable reconnect;
- power cycle;
- day/session;
- query order.

For each factor, estimate:

- how far the output centroid moves;
- whether class ordering changes;
- whether fixed thresholds still work;
- whether Ch B normalization removes the change;
- how much recalibration is required.

This is the experiment that converts "always returns Y" into an honest specification:

> for input Q, under operating envelope E, the device returns output class Y with measured error rate p.

## 11. Phase F — cross-device standardization

Use a second nominally equivalent assembly.

Run three decoder conditions:

1. **zero-calibration:** use Device A query/readout definition unchanged on Device B;
2. **small calibration:** allow only a fixed number of calibration trials per class;
3. **full retraining:** upper-bound control.

This separates three product architectures:

- unique device + enrollment;
- standardized device + factory calibration;
- true interchangeable gate.

For MEMS commercialization, H2 is already potentially useful. H3 is stronger but is not required to justify continued development.

## 12. Data that must be saved

Raw data is required. Summary JSON alone is insufficient.

Each run should produce:

```
data/results/phonon_gate/<session_id>/
    manifest.json
    trials.csv
    raw/
        <trial_id>.npz
    derived/
        transfer_vectors.npz
        gate_metrics.json
```

### Raw NPZ per trial

Required arrays:

- `ch_a_raw` — raw ADC samples from acoustic channel;
- `ch_b_raw` — raw ADC samples from electrical reference;
- `time_s` or enough timing metadata to reconstruct it.

Optional arrays:

- generated/query waveform samples;
- environmental sensor samples.

### trials.csv required columns

```
trial_id
session_id
device_id
geometry_id
fixture_id
path_state
query_id
blind_label
order_index
timestamp
drive_rms_command
temperature_c
ch_a_clip
ch_b_clip
valid
invalid_reason
```

### manifest.json required fields

The schema is defined in `schemas/phonon_gate_manifest.schema.json`.

At minimum record:

- git commit;
- operator;
- complete hardware IDs;
- plate dimensions/material;
- PZT IDs and positions;
- amplifier configuration;
- scope ranges/sample rate/sample count;
- Ch B wiring;
- fixture/mount description;
- query definitions;
- control implementation;
- preregistered thresholds;
- calibration policy;
- randomization seed.

## 13. Separation analysis

For every frozen query q_i, estimate the held-out output distribution p(z | q_i).

For binary scalar outputs define:

```
margin = |mean(z0) - mean(z1)| / sqrt((var(z0) + var(z1))/2)
```

Also report nonparametric overlap and empirical classification error. Do not rely on one metric alone.

For vector outputs:

- standardize using training data only;
- fit the simplest decoder first;
- compare against nearest-centroid and logistic/linear baselines;
- freeze preprocessing and decoder;
- evaluate complete held-out sessions.

No normalization step may use features that would be unavailable in the intended device.

## 14. Electrical-reference analysis

Ch B is not "cheating"; it is instrumentation that helps estimate the driven transfer function.

But the experiment must separately answer:

1. Does Ch B improve measurement stability?
2. Does Ch B itself carry enough query information to solve the task without glass?
3. Does the ratio `Za/Zb` reveal additional separation that disappears in ELECTRICAL_ONLY?

Therefore every classifier must be evaluated on:

- Ch A only;
- Ch B only;
- complex `Za/Zb`;
- GLASS versus ELECTRICAL_ONLY.

A claimed physical-gate advantage requires the glass-bearing condition to add useful information beyond Ch B alone.

## 15. Pre-enrollment sweeps and the hardware standard

The pre-enrollment sweep can answer:

> Which queries make this physical distinction easiest to read?

It cannot, by itself, establish a universal hardware standard.

The progression is:

```
one-device sweep
    -> frozen device-specific alphabet
    -> cross-session repeatability
    -> second-device test
    -> bounded calibration
    -> manufacturing specification
```

A future specification could define:

- permitted query frequencies/waveforms;
- query amplitude and tolerance;
- required transfer/output bands;
- environmental operating envelope;
- allowed calibration procedure;
- decision thresholds;
- test vectors for factory acceptance.

At that point the transmitter can send Q_i because the **hardware contract** says what output range Y_i must produce.

## 16. "Phonics / phonons" research framing

The research-worthy connection is an information abstraction, not etymology:

- symbols can be encoded into structured vibrations;
- a physical medium transforms those vibrations;
- a receiver measures the transformed signal;
- meaning appears only when a stable codebook or decision rule maps the measured state to a symbol.

The CWM question is whether part of that mapping can be embodied in a passive/low-power acoustic transfer function strongly enough to become a useful physical primitive.

A careful public phrase would be:

> CWM investigates whether engineered phononic transfer functions can implement repeatable physical symbol mappings, analogous at an information-system level to encoding and decoding structured sound.

Do not claim that phonics is a branch of phononics or that the glass itself possesses semantic understanding.

## 17. Relationship to other CWM work

This experiment is deliberately upstream of several open programs:

- `docs/PHYSICALLY_WRITTEN_TEMPLATE_BANK_WORKLIST.md`: asks whether physical compatibility can collapse to a simple scalar response.
- PR #8 linear representation transfer: asks whether representations remain alignable across sessions/devices.
- PR #10 USB appliance: supplies the eventual device interface.
- PR #11 geometry-as-physical-encoding: asks whether geometry can improve separability.
- PR #13 rhythm/transient observability: tests temporal query structure without assuming known decay.

The phonon-gate program should establish the simplest stable driven primitive before invoking memory, generation, or temporal persistence.

## 18. Deliverables

### PG-0 — instrumentation qualification
- Ch B loopback self-test.
- clipping/SNR report.
- electrical-only control.

### PG-1 — one-device characterization
- raw dual-channel sweep data.
- candidate-query ranking generated from training sessions only.

### PG-2 — frozen binary gate
- two queries;
- fixed readout;
- blinded held-session evaluation.

### PG-3 — operating envelope
- power cycle, remount, temperature, and amplitude perturbations.

### PG-4 — second-device transfer
- zero-calibration, small-calibration, full-retraining comparison.

### PG-5 — readout reduction
- determine the smallest receiver/readout that preserves the gate margin.

## 19. Stop / advance rules

**Advance toward a phonon-gate claim** only if PG-2 reproduces with held-session data and the glass-bearing response beats electrical-only controls.

**Advance toward a hardware-standard claim** only if PG-4 demonstrates cross-device operation with bounded calibration.

**Advance toward MEMS implementation** only after the logical operation, operating envelope, and readout burden are quantified. MEMS manufacturability is an engineering path, not evidence that the macro prototype already satisfies the gate specification.

**Stop or reframe** if:

- Ch B alone explains the mapping;
- output classes collapse on held sessions;
- required calibration is effectively full re-enrollment every session;
- simple electronic filtering achieves the same operation at lower burden with no compensating CWM advantage.

## 20. First bench session checklist

1. Photograph and identify current wiring.
2. Record device/fixture/PZT IDs.
3. Run Ch B loopback self-test.
4. Capture QUIET.
5. Capture ELECTRICAL_ONLY.
6. Capture GLASS characterization sweep with raw A/B saved.
7. Repeat the selected subset after a complete power cycle.
8. Do **not** choose final logical queries until the training data are closed.
9. Commit raw data or a cryptographic manifest pointing to the raw archive before analyzing the blinded evaluation session.
10. Freeze query/readout configuration and randomization seed before PG-2.

That sequence gives us the shortest defensible path from the current observation — "this input seems to return this output" — to a measured physical gate specification.
