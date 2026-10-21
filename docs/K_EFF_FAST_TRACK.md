# K_eff Fast Track: Does Useful Physical Dimension Outrun Readout Complexity?

**Status:** OPEN / execution protocol  
**Goal:** answer one question as quickly and defensibly as possible:

> **As the physical transform H is asked to carry more useful information or perform richer relational work, does useful physical output or computation increase faster than the receiver/readout burden required to recover the answer?**

This is a focused execution path downstream of the physical-symbol-gate idea (PR #14) and the broader wave-gate scaling roadmap (PR #15).

**Required before fresh acceptance testing:** [FT-M: Measurement and Claim Gate](MEASUREMENT_AND_CLAIM_GATE.md). This adds explicit channel roles, phase-reference qualification, raw-data provenance, transfer-plus-noise modeling and like-for-like controls. It distinguishes our classical nonseparability results from quantum entanglement and takes precedence over conflicting shorthand in earlier evidence notes. It is a measurement prerequisite, not a quantum-hardware detour.

---

## 1. Why this is the fast-track question

A resonator can have many modes and still be commercially uninteresting if every additional useful dimension requires:

- one more sensor,
- one more ADC channel,
- proportionally more samples,
- proportionally more FFT bins,
- proportionally more digital post-processing,
- or complete re-enrollment.

Raw mode count is therefore not the quantity of interest.

The useful quantity is:

```
K_eff = number of independent, reproducible, held-out useful dimensions
```

measured under the actual intended readout constraint.

The competing quantity is **readout burden**.

Do not compress readout burden into a single number too early. Record separately:

- physical receive channels;
- ADC conversions/query;
- samples/query;
- measured frequency bins/query;
- digital multiply/add count;
- bytes of calibration state;
- acquisition window;
- joules/query when measurable.

The primary dimensional test is whether K_eff keeps increasing while one or more of these costs stay flat or increase more slowly.

A second, distinct test now exists for coherent path-sum experiments:

> Can the physical medium evaluate increasingly rich **relationships among inputs before readout**, while the receiver remains approximately fixed?

Do not merge these into one quantity. A one-scalar output may still have K_eff near 1 while embodying a useful many-path relational computation. Count source, reference, transduction and calibration costs separately; a fixed receiver does not imply a fixed whole-system budget.

---

## 2. What K_eff means here

K_eff is **not**:

- total resonant mode count;
- matrix width;
- PCA component count from one session;
- classifier feature count;
- number of labels;
- number of frequencies scanned;
- concurrence, an optimized CHSH-like score, or a count of pairwise interference terms.

For this program, a dimension only counts toward K_eff if it survives all of the following:

1. discovered/fit on training sessions only;
2. distinguishable above measured noise;
3. reproducible on a held-out session;
4. acoustic contribution qualified by matched controls, separately from source-only task decoding;
5. available under the stated readout budget;
6. not created by normalization leakage.

Two complementary estimates are required.

### 2.1 Spectral/representation K_eff

Build the measured transfer matrix H from frozen query/readout definitions.

Estimate training singular values and compare them with:

- within-session noise;
- between-session variation;
- electrical-only singular spectrum.

Count dimensions that remain above the preregistered stability/noise threshold on held-out sessions.

Call this:

```
K_eff,rank
```

### 2.2 Task K_eff

Use a deliberately simple family of independent physical symbol distinctions.

For N simultaneously available distinctions, require a frozen decoder and held-session performance target.

Call the largest N satisfying the target:

```
K_eff,task
```

Report both. Do not force them to agree. A deterministic H need not create information missing from X; the possible advantage is making the required answer available at lower measured cost.

---

### 2.3 Literature / claim map

External work that changes the fast-track hypothesis or claim boundary is tracked in:

- [Physical-computing literature map](PHYSICAL_COMPUTING_LITERATURE_MAP.md).
- [FT-M literature and measurement update](MEASUREMENT_AND_CLAIM_GATE.md), including Deplano et al., Science (2026), DOI `10.1126/science.aeh1375`, and the distinction between classical spatial-spectral nonseparability and quantum mechanical-optical entanglement.

Use these files for:

- phononic single-device parallelism;
- acoustic analog-computing prior art;
- passive acoustic logic prior art;
- classical/quantum path-sum and entanglement claim boundaries;
- persistent-state materials;
- physical relational comparators;
- hardware-constrained software co-design;
- future tunable/stateful media.

The literature map is intentionally tied to experiments rather than being a bibliography-only file. The separate [quantum-transition roadmap](QUANTUM_TRANSITION_ROADMAP.md) is not a dependency of this classical fast track.

---

## 3. Primary scaling claim under test

The strongest fast-track dimensional result would be:

> Increasing simultaneous physical query dimensionality produces increasing held-out K_eff while ADC conversions/query, acquisition window, receiver count, or digital decision complexity remain approximately fixed.

A weaker but still interesting result is:

> K_eff increases faster than total measured readout cost over a bounded operating range.

A null result is:

> Every extra useful physical dimension requires roughly proportional readout growth.

A negative result is:

> K_eff saturates or collapses before readout burden becomes advantageous.

A separate relational-task result can be useful with one scalar output. It must be compared with the simplest equivalent implementation at matched accuracy, not credited with computational complexity from an expanded mathematical expression alone.

---

## 4. Physical bench setup

The fast track should begin with the existing bench, requalified under FT-M, not new quantum hardware.

### 4.1 Signal path

```
                         QUERY / X
                            |
                   PicoScope AWG / DDS
                multitone N = 1,2,4,8...
                            |
                            +----------------------------+
                            |                            |
                       Board D                       Scope Ch B
                     drive buffer                  electrical tap
                            |                       reference X
                            v
                         TX PZT
                            |
                            v
                 +---------------------+
                 |                     |
                 |     GLASS PLATE     |
                 |         H           |
                 |                     |
                 +---------------------+
                            |
                            v
                         RX PZT
                            |
                         Board A
                          preamp
                            |
                            v
                       Scope Ch A
                   physical response Y
```

The critical scaling constraint is that the **receiver hardware remains fixed while simultaneous input dimensionality increases**. The diagram is a proposed configuration, not a declaration that historical data used this wiring. Record any tap or buffer change.

For FT-3:

```
N=1 tone  -> same TX -> same glass -> same RX -> same Ch A/Ch B capture
N=2 tones -> same TX -> same glass -> same RX -> same Ch A/Ch B capture
N=4 tones -> same TX -> same glass -> same RX -> same Ch A/Ch B capture
N=8 tones -> same TX -> same glass -> same RX -> same Ch A/Ch B capture
```

Do not add RX transducers as N increases for the primary fast-track experiment. Additional receivers can be studied later as a separate cost axis.

### 4.2 Mechanical fixture

Use one repeatable fixture that records and constrains:

- plate identity and orientation;
- support points;
- TX PZT position and orientation;
- RX PZT position and orientation;
- coupling/pressure method;
- cable routing;
- fixture ID.

Mark the plate and fixture so the assembly can be restored after a power-down/remount. A later-session failure should not be ambiguous between physical transfer drift and a 2-3 mm placement change.

### 4.3 Environment

Record at minimum:

- temperature near the resonator;
- session timestamp;
- power-cycle status;
- remount/reconnect status.

Temperature compensation is not required initially. The purpose is to discover whether temperature is part of the operating envelope of H.

### 4.4 Ch B role and electrical reference

In the proposed single-RX transfer configuration:

```
Z_B = simultaneously measured electrical drive at the declared tap
Z_A = simultaneously measured received response through the declared receive chain
H_end_to_end(f) = Z_A(f) / Z_B(f)
```

For driven frequencies with adequate reference SNR, the simultaneous ratio helps remove common drive phase/capture timing variation. De-embed gain, phase delay and reference attenuation before calling it a substrate-only transfer function.

**Historical E1/E2 used Ch B as the second acoustic receiver, not as an electrical reference.** Do not combine these configurations or retroactively credit E1/E2 with an electrical control. Two RX channels plus a reference need additional instrumentation or a qualified sequential protocol, with its extra cost recorded.

For coherent same-frequency multi-TX tests, a summed reference can itself cancel; it is not a safe denominator near a null. Follow FT-M0. Source-only decoding is a fair task baseline, not a requirement that X contain no information about the answer.

### 4.5 Required path states

Each fresh session should include reproducible versions of:

```
GLASS
  TX -> physical resonator -> RX

LOOPBACK
  drive presented to both measurement channels
  establishes instrumentation/reference floor

ELECTRICAL_ONLY
  drive/electronics active while the meaningful acoustic path is interrupted
  as cleanly as practical

QUIET
  drive off
```

Document exactly how ELECTRICAL_ONLY is implemented. Do not change several unrelated parts of the signal chain at once. Separate attribution controls from a conventional circuit intentionally implementing the same function.

### 4.6 What simultaneous inputs mean

For N=4, for example, one TX emits a composite waveform:

```
X(t) =
  A1 sin(2 pi f1 t + phi1)
+ A2 sin(2 pi f2 t + phi2)
+ A3 sin(2 pi f3 t + phi3)
+ A4 sin(2 pi f4 t + phi4)
```

All components enter H at the same time and the same RX records the resulting waveform in one acquisition window.

The primary parallelism test is **not** four sequential measurements of f1...f4.

### 4.7 Fixed-budget rule for FT-3

As N increases, hold fixed whenever physically possible:

- one TX PZT;
- one RX PZT;
- two scope channels (A response, B reference);
- sample rate;
- samples/channel;
- acquisition window;
- scope ranges;
- preprocessing path.

Record any quantity that cannot remain fixed.

Illustrative measurement structure only, not predicted results:

| simultaneous inputs | RX PZTs | samples/channel/capture | acquisition window | held-out K_eff |
|---:|---:|---:|---:|---:|
| 1 | 1 | 3072 | fixed | 1 |
| 2 | 1 | 3072 | fixed | ~2 |
| 4 | 1 | 3072 | fixed | >2 |
| 8 | 1 | 3072 | fixed | still increasing |

Two enabled channels at 3072 samples each require 6144 ADC conversions per capture, before any repetition/averaging. Count reference channels, all captures and any sequential interrogation in the total cost. Zero-padding adds no physical samples.

### 4.8 Near-term hardware additions

Useful but non-blocking for retrospective work:

1. rigid/repeatable plate fixture;
2. temperature sensor near the plate;
3. repeatable loopback/control routing.

Do not delay FT-0 for these. Fresh acceptance testing does require a documented, qualified fixture/reference configuration under FT-M.

---

## 5. Experimental sequence

### FT-0 — retrospective ceiling from existing committed data

**No new hardware.**

Use the best committed raw/vector datasets that preserve individual trials.

For each eligible dataset:

1. identify physically measured features and exclude synthetic/dry-run records;
2. identify actual channel roles before separating acoustic, reference and derived H features;
3. split by session/time when possible;
4. compute singular spectrum on training data;
5. estimate held-out stable rank;
6. run feature/readout ablations at 1, 2, 4, 8, 16, 32 and all available features;
7. record task performance and K_eff at each budget, or label the result exploratory where the data cannot establish K_eff.

Purpose:

- establish whether the existing data already show saturation;
- identify promising frequency/channel subsets;
- define the smallest fresh experiment worth running.

**Advance if:** at least one dataset suggests K_eff > 1 after held-out/noise controls, or supports a bounded relational-task hypothesis worth fresh qualification.

**Do not claim scaling from FT-0 alone** if session pairing/raw controls are incomplete.

Retrospective findings are documented in `docs/K_EFF_FT0_EXISTING_DATA_NOTE.md`. The April L=2 dataset suggests that eight simultaneous binary tone components can be distinguished from one fixed Ch-A acquisition with near-perfect same-session held-token accuracy. Because those input identities are also present in the source spectrum and historical Ch B was disabled, treat this as **multiplexing feasibility**, not proof that glass adds useful computation.

Fresh FT-1/FT-3 scoring must separate information already readable from X, what the physical H does to it, and the cost of recovering the required answer in each implementation.

### FT-M — qualify the measurement before accepting a new result

Run [the measurement and claim gate](MEASUREMENT_AND_CLAIM_GATE.md): channel-role/synchronization qualification, retained raw captures, frozen transfer-plus-uncertainty model, matched causal/task controls, and only then readout reduction.

This gate does not require quantum noise calibration or a measured decay constant for the current classical task. It requires the measurements necessary to substantiate the actual claim.

---

### FT-1 — fresh full-map multi-session capture

Use the PR #14 hardware discipline with the FT-M clarifications.

Minimum:

- GLASS, ELECTRICAL_ONLY, LOOPBACK and QUIET;
- simultaneous response and qualified reference for the primary transfer measurement;
- raw per-acquisition time-domain data before averaging;
- >= 3 independent sessions;
- >= 1 full power cycle;
- same frozen candidate frequency grid;
- >= 20 repeats/point/session.

Save:

```
data/results/k_eff/<session_id>/
    manifest.json
    trials.csv
    raw/
    derived/
```

For every trial record query definition, active tones, relative phases, drive level, raw recorded channels, clipping, reference validity, temperature if available, acquisition duration and sample count. FT-M defines required provenance, calibration and exclusion metadata.

FT-1 creates the reference full-information dataset. Save complex coefficients before magnitude conversion or normalization.

---

### FT-2 — readout-ablation frontier

Using FT-1 training sessions only, rank/select readout features.

Evaluate held-out performance at budgets:

```
R = 1, 2, 4, 8, 16, 32, ...
```

where R is separately instantiated as:

- number of frequency bins;
- number of scalar readout statistics;
- number of ADC samples where feasible.

For each R report K_eff,rank, K_eff,task, balanced accuracy/reconstruction error, source-only and electrical-control results, acquisition window, total ADC conversions, digital operations and calibration bytes.

This produces the empirical frontier:

```
K_eff(R)
```

Feature selection and normalization must be frozen from training sessions. Preserve raw and normalized analyses side by side so normalization cannot hide physical drift or an operationally unavailable reference.

---

### FT-3 — simultaneous multiplexing at fixed acquisition budget

Build query sets containing:

```
N = 1, 2, 4, 8, ... simultaneous tones/components
```

while holding as much of the receiver budget fixed as physically possible:

- same receive transducer count;
- same response/reference capture;
- same acquisition duration;
- same sample rate;
- same number of ADC samples;
- same or bounded digital decision path.

Equalize total programmed input energy or explicitly record how it changes. Track per-tone signal-to-noise ratio and clipping as well as total drive level.

For each N:

1. measure single-component responses;
2. measure simultaneous response;
3. compare to a frozen linear-superposition prediction;
4. calculate held-session K_eff;
5. calculate output error/crosstalk;
6. calculate readout and whole-system burden.

A linear result is valid. The question is useful parallel dimensionality, not mandatory nonlinearity.

**Key plot:**

```
x-axis: readout burden
y-axis: held-out K_eff
series: N simultaneous physical inputs
```

If N rises at nearly fixed acquisition cost and K_eff rises, that supports parallel acquisition within the measured range. Computational advantage additionally needs the task/cost comparison; ordinary multiplexing alone does not establish it.

---

### FT-3P — frozen path-sum / relational-compute branch

Companion protocol: `docs/PATH_SUM_INTERFERENCE_FAST_TRACK.md`.  
Historical evidence: `docs/PATH_SUM_FT0_EXISTING_DATA_NOTE.md`.  
Required qualification: [FT-M](MEASUREMENT_AND_CLAIM_GATE.md).

Historical bench data support a coherent-interference hypothesis, including a three-path phase surface fitted with pairwise terms. They do not close source-reference, observable-definition or matched-control gaps. Use a short same-session sweep as a sanity check, not as the main new claim.

The unresolved sequence is:

1. freeze a two-path complex model in session A and predict session B without retuning;
2. run GLASS, source-reference, ELECTRICAL_ONLY and LOOPBACK controls;
3. demonstrate a frozen relational decision such as phase equality with a minimal RX readout;
4. freeze and physically validate the three-path model across sessions;
5. extend to four paths only after three-path qualification;
6. build separate `K_eff vs readout burden` and `useful relational task vs readout burden` frontiers.

For P coherent paths, a squared-magnitude expansion contains up to:

```
P(P-1)/2
```

pairwise terms, but these are neither independent output dimensions nor an electronic operation-count lower bound. The equivalent digital computation can form the P-term complex sum directly and square its magnitude. Use that efficient O(P) baseline, not a deliberately expanded O(P^2) calculation.

Track K_eff, supported interaction terms, relational tasks passed, RX/reference channels, ADC conversions, acquisition window, post-capture digital operations and calibration burden separately.

Potential results:

- **dimensional scaling:** held-session independently recoverable output grows at sublinear/fixed readout cost;
- **relational-task advantage:** a small output gives a useful decision with a measured advantage against equivalent implementations.

This remains a **classical elastic-wave** program. It does not test a quantum Feynman path integral or certify quantum entanglement.

---

### FT-3R — physical relation operator backlog

This is a **future operator-library track**, not a reason to interrupt FT-3/FT-3P controls.

The Advanced Materials 2026 triboelectric/ion-gel work (DOI `10.1002/adma.202520540`) motivates low-dimensional physical relationship operators; see the literature map for its mechanism and experimental/modeling boundary.

After FT-3P establishes a stable controlled primitive, candidate CWM relations include phase difference, frequency proximity/order, amplitude ratio, spatial compatibility, temporal window membership and a weighted coherent score. These are hypotheses, not established CWM capabilities. For example, a beat-envelope magnitude by itself loses the sign of a frequency difference.

For each operator, compare useful task performance against readout, digital operations, calibration and energy. Do not count an operator as additional K_eff unless it yields an independently recoverable output dimension.

Development pattern:

```
measure physical H / kernel
  -> fit hardware-constrained model
  -> run software workload with measured noise/drift
  -> compare to conventional baseline
  -> fabricate/scale only if justified
```

Any system-level software result must be reported as **hardware-constrained modeling**, not as a task physically executed by the plate.

---

### FT-4 — minimal-readout decision ladder

After FT-M qualification, take the best FT-3/FT-3P condition and simplify the receiver:

1. full complex transfer vector;
2. selected magnitudes/phases;
3. weighted scalar;
4. RMS/envelope;
5. comparator / threshold only.

At each stage measure K_eff,task, error, abstention, readout conversions, digital operations and latency. Count the envelope detector/comparator as part of the implementation.

The desirable direction is lower receiver complexity while the required task performance survives. Freeze each candidate readout before scoring its held session.

---

### FT-5 — later-session freeze

Freeze query set, waveform parameters, reference/calibration policy, feature selection, normalization, model, decoder and thresholds.

Power down and repeat the best FT-3/FT-3P/FT-4 experiment on a later day. No parameter tuning before primary scoring. Report a remount separately from a power cycle.

Any allowed recalibration is a separately labeled secondary result with samples, time and storage counted. This determines whether the measured frontier survives beyond the session used to construct it.

---

### FT-6 — second-device checkpoint

Only after FT-5.

Repeat the best condition on Device B under:

1. zero new calibration;
2. small bounded calibration;
3. full retraining.

Record exactly how much calibration is needed to recover the frontier. Distinguish a one-off laboratory H, a calibrated primitive and a standardized primitive.

---

## 6. Quantifying "grows faster"

There is no single honest scalar definition of readout complexity. Report the frontier separately for each primary cost C:

```
efficiency(C) = K_eff / C
marginal efficiency = Delta K_eff / Delta C
```

For enough positive, comparable operating points, optionally fit:

```
K_eff = a * C^alpha
```

Interpret alpha below, near or above 1 as sublinear, approximately proportional or superlinear growth only over the measured range. Do not infer a universal scaling law from a small range or pool unlike devices, tasks, sessions or calibration policies into one slope.

A fixed-cost regime should be reported directly, not forced into a log-log exponent. Include other costs that increase while the chosen axis stays fixed.

---

## 7. Primary readout-cost axes

Produce separate K_eff frontiers against:

- ADC conversions/query across every enabled signal/reference channel and repetition;
- acquisition window and total query latency, including settle/reconfiguration time;
- physical receive channels;
- digital decision operations/query;
- calibration bytes and trials;
- joules/query, when measured.

Do not substitute drive-only energy for whole-system energy. Report relational task accuracy/cost separately from dimensional K_eff.

---

## 8. Required controls

Every frontier point must identify GLASS, source-only, ELECTRICAL_ONLY, LOOPBACK where applicable, a software linear-transform baseline and a conventional filter-bank/summing implementation where applicable.

**Attribution:** does the claimed response depend on the acoustic path after controlling electronics and source behavior?

**Utility:** is the same required answer obtained with lower measured cost or another declared benefit than fair alternatives?

These are different questions. Train a control-specific baseline on its own training data in addition to applying the glass decoder. Failure of a glass-trained threshold on a control path is not enough to establish attribution, and success of a well-designed electronic comparator is not proof of electrical feedthrough in the glass measurement. See FT-M3.

---

## 9. Fast-track decision gates

All acceptance decisions first require FT-M measurement qualification.

### GREEN-A — dimensional result

Held-session K_eff exceeds 1 and increases with simultaneous input dimension while at least one readout-cost axis grows materially slower or remains fixed. Acoustic attribution is supported; all other changing costs and comparative task performance are disclosed. This is not automatically a workload-level advantage.

### GREEN-B — relational-task result

A frozen low-dimensional decision survives later sessions and causal controls, and demonstrates the preregistered accuracy/cost benefit against the simplest equivalent implementations. Extra fitted cross-terms alone do not pass this gate.

### YELLOW — qualified physical operation, no demonstrated advantage

The transform or relational task is stable, but costs grow proportionally or the comparative benefit is absent/unmeasured. Continue only for a specified sensing, filtering or other bounded application.

### INCONCLUSIVE — measurement prerequisites missing

Missing phase reference, raw captures, topology provenance, valid controls or held-session scoring prevents acceptance. Do not silently convert missing evidence into a physical failure or success.

### RED — current scaling hypothesis fails under qualified testing

Examples include held-session useful dimensions collapsing, the proposed operation disappearing with leakage-safe processing, no advantage after full resource accounting, or a frozen mapping requiring full re-enrollment each session. This narrows the tested architecture, not all acoustic computing.

No fast-track result is a quantum-entanglement result.

---

## 10. Minimal machine-readable result

Each evaluated operating point should emit at least:

```
experiment_id
session_group
device_id
path_state
simultaneous_inputs
readout_features
receive_channels
adc_conversions
acquisition_window_s
digital_ops
calibration_bytes
calibration_trials
system_energy_j
k_eff_rank
k_eff_task
heldout_metric
heldout_metric_value
electrical_control_value
valid
notes
```

The frontier schema is `schemas/k_eff_frontier.schema.json`; it also includes optional path/relational metrics. FT-M defines the accompanying raw-data, channel-role, calibration, provenance and uncertainty manifest. Schema validity alone is not experimental acceptance. Mark unmeasured metrics explicitly rather than entering zero.

---

## 11. Tooling

`tools/k_eff_frontier.py` summarizes supplied frontier values: efficiency, marginal efficiency and optional log-log slopes. It does not infer or validate K_eff from raw signals. Compare like-for-like groups, not every CSV row indiscriminately.

`tools/k_eff_ft0_existing.py` and `tools/k_eff_ft0_binary.py` remain exploratory historical diagnostics.

`tools/path_sum_interference_analyze.py` is not yet a held-session acceptance tool. In its current form it does not enforce the required splits and compares different error observables. FT-M Section 9 records the required fixes/tests. Do not use its `coherent_model_better` flag to pass this protocol.

This documentation revision does not claim those analyzer changes are implemented or that new bench tests were run.

---

## 12. Execution order

```
FT-0 existing-data triage
  -> FT-M measurement qualification
  -> FT-1 fresh full-map capture
  -> FT-2 readout-ablation frontier
  -> FT-3 simultaneous spectral multiplexing
  -> FT-3P frozen path-sum / relational-compute branch
  -> FT-4 minimal receiver
  -> FT-5 later-day freeze
  -> FT-6 second device
```

Held-session checks are required within each claimed result, not postponed until every exploratory experiment is complete. For FT-3P, use a same-session cosine only as a sanity check before frozen predictions and controls.

Do not detour into MEMS fabrication or levitated quantum hardware before the classical task is qualified.

> **Does the physics give us either more independently useful output, or a useful relational answer at lower total cost, than the simplest fair alternatives?**
