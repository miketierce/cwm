# K_eff Fast Track: Does Useful Physical Dimension Outrun Readout Complexity?

**Status:** OPEN / execution protocol  
**Goal:** answer one question as quickly and defensibly as possible:

> **As the physical transform H is asked to carry more useful information, does effective useful dimension K_eff increase faster than the receiver/readout burden required to recover it?**

This is a focused execution path downstream of the physical-symbol-gate idea (PR #14) and the broader wave-gate scaling roadmap (PR #15).

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

The core test is whether K_eff keeps increasing while one or more of these costs stay flat or increase more slowly.

---

## 2. What K_eff means here

K_eff is **not**:

- total resonant mode count;
- matrix width;
- PCA component count from one session;
- classifier feature count;
- number of labels;
- number of frequencies scanned.

For this program, a dimension only counts toward K_eff if it survives all of the following:

1. discovered/fit on training sessions only;
2. distinguishable above measured noise;
3. reproducible on a held-out session;
4. not explained by Ch B/electrical-only controls;
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

Report both. Do not force them to agree.

---

## 3. Primary scaling claim under test

The strongest fast-track result would be:

> Increasing simultaneous physical query dimensionality produces increasing held-out K_eff while ADC conversions/query, acquisition window, receiver count, or digital decision complexity remain approximately fixed.

A weaker but still interesting result is:

> K_eff increases faster than total measured readout cost over a bounded operating range.

A null result is:

> Every extra useful physical dimension requires roughly proportional readout growth.

A negative result is:

> K_eff saturates or collapses before readout burden becomes advantageous.

---

## 4. Physical bench setup

The fast track should begin with the existing validated CWM bench, not new hardware.

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

The critical scaling constraint is that the **receiver hardware remains fixed while simultaneous input dimensionality increases**.

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

### 4.4 Ch B electrical reference

Ch B remains part of the measurement instrumentation:

```
Z_B = simultaneously measured injected electrical drive
Z_A = simultaneously measured received plate response
H(f) = Z_A(f) / Z_B(f)
```

For driven frequencies, the simultaneous ratio helps remove common drive phase/capture timing variation.

Ch B must also be analyzed as a competing predictor. A useful GLASS result requires information beyond what Ch B alone provides.

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

Document exactly how ELECTRICAL_ONLY is implemented. Do not change several unrelated parts of the signal chain at once.

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

A result resembling:

| simultaneous inputs | RX PZTs | ADC samples | acquisition window | held-out K_eff |
|---:|---:|---:|---:|---:|
| 1 | 1 | 3072 | fixed | 1 |
| 2 | 1 | 3072 | fixed | ~2 |
| 4 | 1 | 3072 | fixed | >2 |
| 8 | 1 | 3072 | fixed | still increasing |

would be qualitatively different from a result where ADC samples, time, or receivers rise proportionally with K_eff.

The values above illustrate the desired measurement structure only; they are not predicted results.

### 4.8 Near-term hardware additions

Useful but non-blocking:

1. rigid/repeatable plate fixture;
2. temperature sensor near the plate;
3. repeatable loopback/control routing.

Do not delay FT-0 for any of these, and do not delay FT-1 if the existing fixture can be documented reproducibly.

---

## 5. Experimental sequence

### FT-0 — retrospective ceiling from existing committed data

**No new hardware.**

Use the best committed raw/vector datasets that preserve individual trials.

For each eligible dataset:

1. identify physically measured features only;
2. separate Ch A / Ch B / derived H features;
3. split by session/time when possible;
4. compute singular spectrum on training data;
5. estimate held-out stable rank;
6. run feature/readout ablations:
   - 1
   - 2
   - 4
   - 8
   - 16
   - 32
   - all available
7. record task performance and K_eff at each budget.

Purpose:

- establish whether the existing data already show saturation;
- identify promising frequency/channel subsets;
- define the smallest fresh experiment worth running.

**Advance if:** at least one dataset suggests K_eff > 1 after held-out/noise controls.

**Do not claim scaling from FT-0 alone** if session pairing/raw controls are incomplete.

Retrospective findings and the current stronger hypothesis are documented in `docs/K_EFF_FT0_EXISTING_DATA_NOTE.md`. In particular, the April L=2 dataset shows that eight simultaneous binary tone components can be distinguished from one fixed Ch-A acquisition with near-perfect same-session held-token accuracy. Because those input identities are also present in the source spectrum and historical Ch B was disabled, treat this as evidence of **multiplexing feasibility**, not evidence that the glass adds useful computation.

Therefore fresh FT-1/FT-3 scoring must separate:

1. information already readable directly from X / Ch B;
2. information present only or more cheaply in the transformed glass response Y;
3. the readout burden required to obtain each.

The fast-track scaling claim advances only on item 2.

---

### FT-1 — fresh full-map multi-session capture

Use the PR #14 dual-channel hardware discipline.

Minimum:

- GLASS;
- ELECTRICAL_ONLY;
- LOOPBACK;
- QUIET;
- simultaneous Ch A and Ch B;
- raw time-domain data;
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

For every trial record:

- query definition;
- active tones;
- relative phases;
- drive level;
- Ch A raw samples;
- Ch B raw samples;
- clipping;
- temperature if available;
- acquisition duration;
- sample count.

FT-1 creates the reference full-information dataset.

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

For each R report:

- K_eff,rank;
- K_eff,task;
- balanced accuracy / reconstruction error;
- Ch B-only result;
- ELECTRICAL_ONLY result;
- acquisition window;
- ADC conversions;
- digital operations;
- calibration bytes.

This produces the first empirical frontier:

```
K_eff(R)
```

Important: feature selection and normalization must be frozen from training sessions.

---

### FT-3 — simultaneous multiplexing at fixed acquisition budget

This is the decisive physical-parallelism experiment.

Build query sets containing:

```
N = 1, 2, 4, 8, ... simultaneous tones/components
```

while holding as much of the receiver budget fixed as physically possible:

- same receive transducer count;
- same Ch A/Ch B capture;
- same acquisition duration;
- same sample rate;
- same number of ADC samples;
- same or bounded digital decision path.

Equalize total programmed input energy or explicitly record how it changes.

For each N:

1. measure single-component responses;
2. measure simultaneous response;
3. compare to linear-superposition prediction;
4. calculate held-session K_eff;
5. calculate output error/crosstalk;
6. calculate readout burden.

A linear result is valid. The question is parallel useful dimensionality, not mandatory nonlinearity.

**Key plot:**

```
x-axis: readout burden
y-axis: held-out K_eff
series: N simultaneous physical inputs
```

If N rises while acquisition/readout stays nearly fixed and K_eff rises, this is the first strong evidence for useful physical parallelism.

---

### FT-3P — coherent path-sum interference

Companion protocol: `docs/PATH_SUM_INTERFERENCE_FAST_TRACK.md`.

FT-3 varies simultaneous **spectral** inputs at fixed receiver cost. FT-3P tests a second source of physical parallelism: **spatial/path interference**.

The smallest setup uses two independently phase-controlled TX PZTs on the same plate and one fixed RX. It asks:

1. whether the simultaneous complex RX response is predicted by the coherent sum of individually characterized TX-to-RX paths;
2. whether constructive/destructive interference can produce a relational output (e.g. same-phase vs opposite-phase) that is not available from either individual path magnitude alone;
3. whether useful held-session dimensionality increases as controlled path count grows while RX hardware/acquisition remain fixed.

This is explicitly a **classical elastic-wave** experiment. It must not be described as a quantum Feynman path integral or single-phonon computation.

Advance only if the coherent model predicts later-session combined responses, electrical-only controls do not explain the effect, and the resulting relational readout contributes useful K_eff at fixed or sublinear readout burden.

---

### FT-4 — minimal-readout decision ladder

Take the best FT-3 condition and deliberately simplify the receiver.

Test:

1. full complex transfer vector;
2. selected magnitudes/phases;
3. weighted scalar;
4. RMS/envelope;
5. comparator / threshold only.

At each stage measure:

- K_eff,task;
- error rate;
- abstention rate;
- readout conversions;
- digital operations;
- latency.

The desirable direction is:

```
receiver complexity decreases
while
K_eff remains useful
```

This is more commercially meaningful than maximizing raw spectral dimensionality.

---

### FT-5 — later-session freeze

Freeze:

- query set;
- waveform parameters;
- feature selection;
- normalization;
- decoder;
- thresholds.

Power down.

Repeat the best FT-3/FT-4 experiment on a later day.

No parameter tuning before scoring.

This determines whether the frontier is a property of H rather than a same-session calibration artifact.

---

### FT-6 — second-device checkpoint

Only after FT-5.

Repeat the best condition on Device B under:

1. zero new calibration;
2. small bounded calibration;
3. full retraining.

Record exactly how much calibration is needed to recover the frontier.

This separates:

- one-off laboratory H;
- calibrated hardware primitive;
- standardized hardware primitive.

---

## 6. Quantifying "grows faster"

There is no single honest scalar definition of readout complexity, so report the frontier against each primary cost axis.

For a cost C:

```
efficiency(C) = K_eff / C
```

and marginal efficiency:

```
Delta K_eff / Delta C
```

For positive values across multiple operating points, optionally fit:

```
K_eff = a * C^alpha
```

on a log-log plot.

Interpretation:

- `alpha < 1`: useful dimension grows sublinearly with that readout cost;
- `alpha ~= 1`: approximately proportional;
- `alpha > 1`: superlinear over the measured range.

Do **not** call `alpha > 1` a universal scaling law from a small range.

The strongest practical result may instead be a **fixed-cost multiplexing regime** where C is approximately constant while K_eff increases.

---

## 7. Primary readout-cost axes

At minimum produce separate plots for:

### A. ADC burden

```
K_eff vs ADC conversions/query
```

### B. acquisition time

```
K_eff vs acquisition_window_s
```

### C. receiver hardware

```
K_eff vs physical_receive_channels
```

### D. digital decision burden

```
K_eff vs digital_ops/query
```

### E. calibration burden

```
K_eff vs calibration_bytes
K_eff vs calibration_trials
```

### F. energy

When instrumentation permits:

```
K_eff vs joules/query
```

Do not substitute drive-only energy for end-to-end system energy.

---

## 8. Required controls

Every frontier point must identify whether the same result exists in:

- GLASS;
- Ch B only;
- ELECTRICAL_ONLY;
- LOOPBACK where applicable;
- a software linear-transform baseline;
- a conventional filter-bank / selected-bin baseline where applicable.

The physical system is interesting only if its transform contributes useful structure beyond the electrical reference.

---

## 9. Fast-track decision gates

### GREEN — accelerate wave-gate work

All of the following:

- K_eff > 1 on held-out later-session data;
- K_eff increases with simultaneous physical query dimension;
- at least one major readout-cost axis grows materially slower than K_eff, or remains approximately fixed;
- electrical-only/Ch B controls do not explain the gain;
- minimal readout retains a meaningful fraction of the gain.

### YELLOW — useful physical transform, weak scaling advantage

- stable K_eff > 1;
- but readout burden grows approximately proportionally.

Interpret as a sensing/filtering/analog-transform result unless another workload advantage emerges.

### RED — stop scaling claims

Any of:

- held-out K_eff collapses to ~1;
- apparent rank is dominated by electrical-only structure;
- useful dimension disappears after leakage-safe normalization;
- simultaneous queries require proportional or worse acquisition/readout growth with no compensating workload advantage;
- later-session freeze fails without full re-enrollment.

A RED result does not invalidate the physical-symbol-gate or sensing directions.

---

## 10. Minimal machine-readable result

Each evaluated operating point should emit one row containing at least:

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

The result schema is defined in `schemas/k_eff_frontier.schema.json`.

---

## 11. Tooling

`tools/k_eff_frontier.py` consumes the machine-readable frontier CSV and reports:

- K_eff/readout efficiency by cost axis;
- marginal K_eff per marginal cost;
- optional log-log exponent alpha when enough positive points exist;
- the best measured operating point for each axis;
- explicit warnings where a cost is constant or data are insufficient.

It does not infer K_eff from raw signals. K_eff must come from the controlled analysis described above.

---

## 12. Execution order

The shortest path is:

```
FT-0 existing data
  -> FT-1 fresh full-map capture
  -> FT-2 readout-ablation frontier
  -> FT-3 simultaneous multiplexing at fixed acquisition
  -> FT-4 minimal receiver
  -> FT-5 later-day freeze
  -> FT-6 second device
```

Do not detour into MEMS fabrication before FT-5.

The result we want to know first is simple:

> **Does the physics give us more independently useful transformation than we have to pay to read back out?**
