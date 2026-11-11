# Resonance Recognition Architecture

**Status:** hypothesis + experiment design  
**Parent research thread:** PR #17 — distributed partial-view representation and reference-assisted reconstruction  
**Foundation:** merged PR #16 measurement/readout discipline

## 1. Core idea

The current CWM direction should not assume that useful computation requires assigning symbolic meaning to individual modes:

```
mode f1 = bit 0
mode f2 = bit 1
...
```

A potentially stronger architecture is:

> **A structured physical query is presented to one or more configured resonant operators, and the useful answer is encoded in how strongly each operator physically matches that query.**

The working abstraction is:

```
query pattern x
   -> physical operator H_theta
   -> compact response score s
```

with

```
y = H_theta x
s = g(y)
```

where:

- `x` may encode frequency, phase, amplitude, timing and spatial source;
- `theta` is the physical configuration that defines the operator;
- `g` is a frozen low-dimensional readout such as magnitude, energy, phase relation or another qualified statistic.

The computation is then a **physical compatibility test**, not necessarily a symbolic bitwise transform.

---

## 2. "Dueling pianos" interpretation

A useful intuition is:

> one system "plays" a structured question; another system has been configured so that some questions make it respond more strongly or coherently than others.

For multiple responders:

```
                -> H_A -> s_A
query x --------> H_B -> s_B
                -> H_C -> s_C
```

A classification-like decision can be:

```
winner = argmax_k s_k
```

This is not automatically a new computational primitive; it overlaps conceptually with matched filters, correlators and associative memories.

The CWM engineering question is narrower:

> Can a physical resonant operator expose the task-relevant compatibility score before paying the cost of full high-dimensional acquisition and digital comparison?

The answer must be established by matched electronic baselines and whole-system cost accounting.

---

## 3. Why this fits the existing evidence

### 3.1 E26: small selected subsets can preserve identity

Historical E26 showed 4-way rod identification reaching 4/4 correct using only the two strongest selected peaks out of ten.

Claim boundary:

- this supports partial-query task retention;
- it does not show reconstruction of the omitted eight features;
- the peaks were adaptively selected after a full measurement, so it is not blind arbitrary-subset evidence.

### 3.2 E36 retrospective subset frontier: identity is not confined to one privileged mode

PR #17's retrospective enumeration of all saved E36 mode-index subsets found:

| modes retained | mean 4-way accuracy | subsets with 4/4 correct |
|---:|---:|---:|
| 1 / 10 | 65.0% | 10.0% |
| 2 / 10 | 68.3% | 20.0% |
| 3 / 10 | 80.0% | 36.7% |
| 4 / 10 | 92.0% | 68.6% |
| 5 / 10 | 95.1% | 80.6% |
| 6 / 10 | 97.6% | 90.5% |
| 7 / 10 | 98.8% | 95.0% |
| 8 / 10 | 99.4% | 97.8% |
| 9 / 10 | 100% | 100% |
| 10 / 10 | 100% | 100% |

This is exploratory, same-session evidence.

It supports the hypothesis that **task identity is distributed across multiple spectral views**.

It does not establish that the glass performs completion, that arbitrary missing measurements are reconstructable, or that the effect survives a held session.

### 3.3 E8: different spatial views can preserve the same state

Historical E8 found that two spatially separated receiver positions both decoded the same four two-bit states correctly while their analog response ratios differed materially.

The useful interpretation is:

> different physical projections can retain the same task identity.

Do not reinterpret this as additional independent bits.

### 3.4 FT-1: full analog H can move while some structure remains predictable

The October 2026 FT-1 campaign showed that the complete complex transfer is sensitive to session, temperature and handling.

After identifying the frequency-grid mismatch, exploratory exact-frequency analysis found roughly:

- 1.2–2.0% median within-session superposition error;
- 7–8% held-out S1+S2 -> S3 error;
- a loopback floor around 0.8–1.6%.

These numbers do not prove resonance recognition.

They motivate the more useful question:

> Does the **task-level compatibility ordering** survive changes that move the detailed analog transfer?

That is a stronger engineering target than demanding point-by-point invariance of H.

---

## 4. Recognition is not reconstruction

These must remain distinct.

### Recognition

A partial or transformed observation is enough to choose the correct configured responder:

```
argmax_k s_k = correct class
```

### Reconstruction

The omitted/full response can be predicted:

```
Y_partial -> Y_full
```

Recognition can work even when reconstruction is impossible.

Therefore:

> a successful partial-query classifier is not evidence that the medium "filled in" missing modes.

This distinction is mandatory in all future CWM reporting.

---

## 5. RR-1 — competitive physical responder test

### Question

Can two or more physically distinct configured operators classify **families of related queries**, rather than merely recognize one exact calibration waveform?

### Minimal architecture

```
                    -> responder H_A -> score s_A
frozen query x ----->
                    -> responder H_B -> score s_B
```

The responders may initially be:

- two physical resonators/plates;
- two deliberately different boundary/load configurations of one plate measured in separate frozen runs;
- two distinct registered propagation paths if they truly implement different H and not merely different software labels.

A later programmable H is optional and not required for the first test.

### Query family

Use at least two classes with multiple exemplars per class.

Within each class vary at least one nuisance parameter that should **not** change identity, for example:

- amplitude;
- small frequency offset;
- one omitted component;
- controlled phase perturbation;
- small timing shift.

Do not train and test on identical exact waveforms only.

### Freeze

Training sessions determine:

- responder configuration;
- query encoding;
- score definition;
- normalization;
- threshold / argmax rule;
- any allowed calibration.

Then freeze all of them.

### Held-session primary endpoint

On a later/power-cycled session with no retuning:

```
argmax_k s_k
```

must recover the declared class.

Report:

- balanced accuracy / exact accuracy;
- winner margin;
- confusion matrix;
- abstention if used;
- session-to-session shift of every score;
- full-H drift beside task-level drift.

### Required baselines

1. source-only digital classifier from the same commanded input;
2. direct digital matched filter/correlation using the same measured receiver data;
3. simple electronic/filter-bank baseline where practical;
4. ELECTRICAL_ONLY / LOOPBACK artifact controls;
5. randomized responder labels;
6. randomized query labels.

A physical recognition result is interesting only if the resonant operator contributes information or cost reduction beyond source/electrical leakage.

---

## 6. RR-2 — partial-query recognition frontier

After RR-1 works, reduce the query before it reaches the physical operator.

Examples:

- remove frequency components;
- mask spatial drive ports;
- omit pulses;
- reduce phase constraints.

For aperture fraction `q`, measure:

```
P(correct responder | q)
```

and the distribution of winner margins.

This directly connects the resonance-recognition architecture to HP-1.

Strong evidence would be:

- multiple independently frozen partial queries retain the same winner;
- performance degrades gracefully rather than depending on one privileged component;
- the same behavior survives a later session;
- randomized/enrollment controls collapse.

Again, this is **distributed recognition**, not necessarily reconstruction.

---

## 7. RR-3 — responder competition versus full digital readout

The architecture becomes practically interesting only if a small physical output is sufficient.

Compare:

### Full digital path

```
sensor / RX
 -> high-rate waveform
 -> FFT / feature extraction
 -> template or classifier
 -> answer
```

### Physical compatibility path

```
query / physical signal
 -> configured resonant operator
 -> one/few score observables
 -> argmax / threshold
```

Track:

- ADC conversions;
- ADC bits;
- sample count;
- acquisition time;
- digital operations;
- calibration bytes/trials;
- source/reference hardware;
- number of physical responders;
- energy when measurable;
- task accuracy and margin.

The claim target is not "physics computed it."

The claim target is:

> **the physical compatibility architecture obtains the same required answer at a measurable systems advantage.**

---

## 8. RR-4 — programmable responder H(theta)

Only after fixed responders pass.

Introduce a controllable state `theta`:

```
Y = H(theta) X
```

Possible future control mechanisms include:

- programmable electrical loading of a piezo boundary;
- MEMS geometry/boundary changes;
- electrostatic or piezoelectric tuning;
- ferroelectric/resistive persistent state;
- other qualified tunable materials.

Required demonstration:

1. at least two reproducible H states;
2. frozen state selection changes the intended task response;
3. state change is larger than drift and control variation;
4. programming cost/latency is measured;
5. retention is measured separately from query execution.

Do not call a change in source weighting a programmable physical H unless the physical operator itself changes.

---

## 9. RR-5 — mutually coupled "dueling pianos"

This is a later research branch and is **not supported by current evidence**.

Instead of one-way query -> responder:

```
system A <-> system B
```

allow each system's response to affect the other:

```
x_(t+1) = F_A(x_t, y_t)
y_(t+1) = F_B(y_t, x_t)
```

Potential computational observables include:

- synchronization;
- phase locking;
- cancellation;
- stable attractor selection;
- failure to lock;
- convergence time.

This would move CWM from a fixed physical matched operator toward a coupled dynamical computer.

It should not be attempted until RR-1/RR-3 establish that one-way physical compatibility scoring is reproducible and useful.

---

## 10. Falsifiers

The resonance-recognition interpretation is weakened if:

- correct identity requires one privileged exact frequency or path;
- performance disappears under small nuisance variation;
- held-session ordering changes unless thresholds/configuration are retuned;
- the same answer is fully explained by source-only information;
- ELECTRICAL_ONLY reproduces the responder ordering;
- full digital matched filtering is simpler and cheaper at matched accuracy;
- partial-query performance is no better than what ordinary redundant features predict.

A failure here does not invalidate CWM as a fixed filter or transform.

---

## 11. Relationship to the "holographic" hypothesis

The useful intersection is:

```
distributed representation
      +
partial access
      +
physical compatibility score
```

A stronger holographic-like interpretation requires more:

- multiple partial views preserve task identity;
- omitted views are predictably related or reconstructable;
- reference-assisted reconstruction works where claimed;
- the property survives later sessions and controls.

Do not use the word "holographic" merely because a small query can identify a responder.

---

## 12. Near-term execution order

```
HP-1 partial-view held-session test
  -> RR-1 two-responder physical compatibility
  -> RR-2 partial-query responder frontier
  -> RR-3 receiver/system-cost comparison
  -> HP-3 omitted-view reconstruction (separate claim)
  -> HP-4 reference-assisted reconstruction
  -> RR-4 programmable H
  -> RR-5 coupled dynamical responders
```

The immediate experiment is intentionally modest:

> **Can the same frozen family of incomplete queries make the correct one of two physical responders win on a later session, without retuning?**


---

## 13. External strategic escalation gate

A successful RR experiment does not automatically justify a transformative-compute or orbital-compute claim.

Use:

[EXTERNAL_STRATEGIC_ESCALATION_GATE.md](EXTERNAL_STRATEGIC_ESCALATION_GATE.md)

The maturity ladder is:

- **E0** — internal / exploratory;
- **E1** — publishable physical result;
- **E2** — qualified compute primitive;
- **E3** — strategic hardware result with a measured whole-system advantage;
- **E4** — orbital / high-impact escalation after scaling, orbital-overhead and replication gates pass.

For E3, the preregistered strategic threshold requires either:

- at least **10x measured improvement on one mission-relevant whole-system metric**, or
- at least **3x measured improvement on two independent primary metrics**,

at matched task quality with complete system costs counted.

For E4, the advantage must additionally survive a space-relevant system model and retain at least a **2x net mission-critical advantage** (or a quantified enabling property), plus second-device/fresh-analysis replication and adversarial baseline review.

These are escalation thresholds, not claims about current CWM performance.

Current status at creation: **E0 / exploratory**.
