# FT-3P Existing-Data Evidence Note

**Status:** retrospective / hypothesis-forming  
**Parent:** PR #16 — K_eff versus readout complexity  
**Purpose:** record what the existing CWM bench has already established about coherent path interference so fresh experiments do not repeat solved questions.

## 1. What is already strongly supported

### 1.1 Two-path destructive interference is repeatable on the bench

The June 3 E9 phase-cancellation experiment used two coherent TX paths into the same plate.

Across five measured modes:

| frequency | destructive suppression |
|---:|---:|
| 35,840 Hz | 99.1% |
| 54,920 Hz | 98.4% |
| 70,000 Hz | 99.1% |
| 85,000 Hz | 99.1% |
| 97,011 Hz | 98.7% |

Saved lab summary:

- mean suppression: 98.9% +/- 0.3%;
- optimum destructive phase: 180 degrees for all five modes;
- write -> erase -> write recovery: 99.7%.

Source: `docs/lab_diary_20260603.md` and `data/results/phase_cancellation/e9_phase_cancellation_20260603_195303.json`.

This is already strong evidence that coherent two-path cancellation exists in the physical apparatus.

### 1.2 Selected two-path phase sweeps are well described by a first-harmonic interference law

The existing retrospective summary at:

`data/results/quantum_transition/preliminary_existing_data/summary.json`

reanalyzes 18 physical phase sweeps.

Across all 18 sweeps:

- median first-harmonic R^2: 0.839;
- median leave-one-out first-harmonic R^2: 0.791;
- 50% of sweeps reached leave-one-out R^2 >= 0.8.

Selected operating points were much stronger:

| frequency | leave-one-out R^2 |
|---:|---:|
| 54.92 kHz | ~0.9995 in the cleanest run |
| 91 kHz | ~0.9537 |
| 97.011 kHz | ~0.9213 |

Bad operating points also exist, including 70 kHz and 321 kHz.

Conclusion:

> Coherent interference is not uniformly clean across modes. Mode/path selection is an engineering variable, not a nuisance to average away.

### 1.3 Three mutually interfering paths were already measured

The June 21 three-path experiment used three independently phase-controlled TX PZTs on one 25 mm plate and one RX at 91 kHz.

Saved confirmed run:

`data/results/phase_interference/three_path_20260621_154927.json`

The measured 12 x 12 phase grid was fit to:

```
E(phi2, phi3) =
    b0
  + b1 cos(phi2) + b2 sin(phi2)
  + b3 cos(phi3) + b4 sin(phi3)
  + b5 cos(phi2-phi3) + b6 sin(phi2-phi3)
```

Measured pairwise terms:

| interaction | fitted strength |
|---|---:|
| 1<->2 | 59,961 |
| 1<->3 | 25,007 |
| 2<->3 | 50,064 |

The 2<->3 cross-term was ~83% of the strongest pairwise interaction and requires TX2 and TX3 to participate coherently in the same measured response.

The full fit gave:

```
R^2 = 0.922
```

and a deep measured minimum relative to the maximum.

A preceding run at lower averaging already showed:

```
R^2 = 0.874
```

with a strong 2<->3 term.

Conclusion:

> The open question is no longer whether more than two controlled elastic paths can mutually interfere on the bench. They already have.

### 1.4 Phase reference instrumentation is now better than in some historical runs

Later Ch-B reference work showed that simultaneous same-frequency referencing can reduce measured phase scatter substantially.

The lab diary records an improved configuration with approximately:

```
raw phase scatter       ~1.82 rad
referenced phase scatter ~0.18 rad
```

or roughly:

```
~104 degrees -> ~10 degrees
```

at qualified driven frequencies.

This makes fresh cross-session path-sum measurements better instrumented than some of the original interference runs.

## 2. What the old experiments do NOT establish

The historical data do not yet establish:

1. later-day frozen prediction without retuning;
2. matched ELECTRICAL_ONLY controls;
3. that the glass creates information not trivially present in source phase;
4. that path count implies `K_eff = path count`;
5. that a one-scalar output exposes all internal pairwise interactions independently;
6. a cross-device standardized path gate;
7. an end-to-end energy or latency advantage.

These are the actual remaining questions.

## 3. Important measurement correction

Some historical tools named a summed FFT-magnitude statistic `energy`.

That quantity is useful as a monotonic response statistic but is not rigorously physical energy.

Fresh FT-3P work should record and analyze:

- complex demodulated voltage/amplitude;
- squared magnitude/power-like quantities only when explicitly defined;
- raw time-series waveforms;
- electrical references.

Do not reuse old "energy cancellation" wording without defining the measured quantity.

## 4. What the historical evidence predicts

### FT-3P-A: coherent two-path model

Prior expectation: **likely pass at selected modes**.

Reason:

- deep physical nulls already measured;
- selected phase sweeps have high held-phase-point predictive fit;
- same-frequency reference phase is measurable.

The fresh value is cross-session frozen validation + controls, not first demonstration.

### FT-3P-B: two-bit relational decision

Prior expectation: **likely within-session, unknown cross-session**.

Reason:

- null location is a sharp and robust measured feature;
- historical cancellation-match runs preserved null-based identification under large common-mode gain perturbations.

The fresh value is proving that the relationship remains readable after a power cycle/later day and is not reproduced by matched electrical-only controls.

### FT-3P-C: 3/4-path computational compression

Prior expectation: **physically plausible, scaling unknown**.

Reason:

- three mutual pairwise terms were measured in one scalar response;
- the 3-path phase surface is already well described by the expected pairwise trigonometric structure.

Unknown:

- whether additional paths remain phase-stable;
- whether useful task complexity grows;
- whether readout/calibration burden grows more slowly;
- where coupling imbalance/saturation begins.

## 5. Two different scaling prizes

The historical data strongly motivate separating two concepts.

### A. Independent output dimensionality

This remains the original PR #16 quantity:

```
K_eff
```

A path does not count as a new K_eff dimension merely because it contributes internally.

A one-scalar detector can still have:

```
K_eff = 1
```

even if many paths produced that scalar.

### B. Relational computation compression

For P coherent paths:

```
Y = |sum_j a_j|^2
```

expands into self-terms plus pairwise cross-terms.

The number of possible pairwise physical interactions is:

```
P(P-1)/2
```

Examples:

| paths P | possible pairwise terms |
|---:|---:|
| 2 | 1 |
| 3 | 3 |
| 4 | 6 |
| 8 | 28 |
| 16 | 120 |

This does **not** mean all terms are independently readable.

It means the physical observable can depend on a growing number of relationships before the signal reaches the receiver.

Therefore FT-3P should track separately:

```
supported_interaction_terms
relational_tasks_passed
readout_features
receive_channels
adc_conversions
acquisition_window
digital_ops_after_capture
calibration_burden
```

The stronger path-sum thesis is:

> Useful relational computation performed before readout grows faster than the external readout burden.

That can be valuable even when K_eff itself does not grow proportionally with path count.

## 6. Updated experimental priority

Do not spend the next run merely reproducing another same-session two-path phase cosine.

Priority order:

1. **Frozen later-session two-path prediction**
   - characterize paths in session A;
   - power down;
   - predict session B phase sweep without retuning.

2. **Matched electrical controls**
   - GLASS;
   - source-reference only;
   - ELECTRICAL_ONLY;
   - LOOPBACK.

3. **Frozen relational gate**
   - same/opposite phase or another preregistered binary relation;
   - scalar/minimal readout;
   - >=95% held-session balanced accuracy target.

4. **Three-path held-session validation**
   - freeze the 7-term model from training session(s);
   - predict a later-session phase grid;
   - confirm the 2<->3 interaction remains.

5. **Four-path extension**
   - only after the 3-path later-session result survives controls.

6. **Scaling frontier**
   - compare P=1,2,3,4 at fixed RX/acquisition cost;
   - report both K_eff and relational-computation metrics.

## 7. Decision interpretation

A result can now be valuable in two different ways.

### GREEN-A: dimensional scaling

Held-session K_eff increases faster than readout burden.

### GREEN-B: computation compression

K_eff may remain small, but increasing P creates increasingly rich, reproducible relational functions that can be decoded with approximately fixed receiver/acquisition complexity.

### YELLOW

Coherent path interference is stable but relational task complexity does not increase or requires proportional calibration/readout growth.

### RED

Later-session phase geometry is not stable, electrical-only controls reproduce the result, or useful relational behavior requires full re-enrollment every session.

## 8. Bottom line

The old data shift FT-3P from:

> "Do multiple paths coherently interfere?"

to:

> **"Can the already-demonstrated coherent path sum be frozen, controlled, and engineered into increasingly useful relational computation before a fixed-cost receiver?"**

That is the best next question supported by the current evidence.
