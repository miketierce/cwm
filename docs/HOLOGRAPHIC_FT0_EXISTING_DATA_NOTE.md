# Holographic-Like / Partial-View FT-0 Existing-Data Note

**Status:** retrospective hypothesis-forming evidence only  
**Parent:** downstream of merged PR #16  
**Reproducible analysis:** `tools/holographic_ft0_existing.py`

## 1. Question

The word **holographic** is used here only as a motivating analogy.

The immediate experimental question is narrower:

> **Is task-relevant identity redundantly distributed across CWM's spectral and spatial response such that a partial view can recover the same state even when the analog view itself is incomplete or different?**

This is distinct from a stronger field-reconstruction claim:

> Can a known coherent reference be used to reconstruct a complex CWM response from a simpler measured interference observable?

The existing archive can inform the first question. It does not yet answer the second.

Do not treat either question as quantum holography.

---

## 2. Existing Representation Hypothesis already anticipated this

`docs/REPRESENTATION_HYPOTHESIS.md` proposed that CWM identity might be encoded in distributed relational structure rather than one privileged mode or receiver.

Two historical observations were especially relevant:

- E26: 2 of 10 selected peaks were sufficient for 4/4 rod identification.
- Plate spatial census / dual-receiver work: spatially separated PZTs observe different modal projections.

RH-02 explicitly proposed random subspace retention as a test of "holographic-like redundancy."

The present note tightens that idea using data collected since that document was written and a new exhaustive retrospective analysis of the E36 raw response matrix.

---

## 3. FT-0A — E26 adaptive partial-query recall

Source:

`data/results/lab/additional_exps/additional_20260409_171342.json`

Historical result:

| K queried peaks | accuracy |
|---:|---:|
| 1 / 10 | 50% (2/4) |
| 2 / 10 | 100% (4/4) |
| 3–10 / 10 | 100% (4/4) |

This is useful but weaker than it first appears.

The acquisition code in `tools/additional_experiments.py::exp_partial_query_recall` first measures the full set of candidate peaks for each query rod, ranks them by measured magnitude, and then tests that rod's strongest K peaks.

Therefore E26 establishes:

> A very small **adaptively selected** spectral subset can preserve the four-way identification task in that same-session experiment.

It does **not** establish:

- arbitrary/random subset robustness;
- blind partial-aperture recovery;
- later-session retention;
- field reconstruction from a fragment.

This distinction motivates reusing E36, whose saved raw matrix allows arbitrary subset enumeration after the fact.

---

## 4. FT-0B — exhaustive arbitrary mode-index subsets from E36

Sources:

- `data/results/lab/additional_exps/additional_20260411_105304.json`
- `data/results/lab/users.json`
- original scoring implementation: `tools/additional_experiments.py::exp_null_control`

E36 saved a full 4-query × 4-sense-rod × 10-query-peak response tensor.

The new retrospective analysis keeps the original E36 scoring rule:

- frequency matching tolerance: 3%;
- expected response contribution: `+3 × magnitude fraction`;
- unexpected response contribution: `-1 × magnitude fraction`.

Instead of using all 10 peaks, `tools/holographic_ft0_existing.py` enumerates **every combination of K peak indices** and reruns the four-way identity decision.

### Result

| K modes retained | subsets tested | mean accuracy | subsets with 4/4 correct | subsets ≥75% correct | median mean margin | worst mean margin |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 65.0% | 10.0% | 70.0% | 0.530 | -0.697 |
| 2 | 45 | 68.3% | 20.0% | 64.4% | 0.916 | -0.890 |
| 3 | 120 | 80.0% | 36.7% | 85.0% | 1.445 | -0.186 |
| 4 | 210 | **92.0%** | **68.6%** | **99.5%** | 2.057 | **+0.542** |
| 5 | 252 | **95.1%** | **80.6%** | **100%** | 2.742 | **+1.320** |
| 6 | 210 | 97.6% | 90.5% | 100% | 3.372 | +2.117 |
| 7 | 120 | 98.8% | 95.0% | 100% | 4.010 | +2.928 |
| 8 | 45 | 99.4% | 97.8% | 100% | 4.610 | +3.799 |
| 9 | 10 | 100% | 100% | 100% | 5.231 | +4.804 |
| 10 | 1 | 100% | 100% | 100% | 5.946 | +5.946 |

### Why this is more interesting than E26

E26 showed that the strongest two modes selected after a full measurement were enough.

E36 says something different:

> By K=4, **68.6% of all possible four-mode subsets** recover all four identities, 99.5% recover at least three of four, and even the worst four-mode subset has a positive average correct-class margin.

By K=5:

> 80.6% of all subsets recover all four identities and every subset recovers at least three of four.

This is consistent with **distributed task redundancy** rather than one unique magic set of modes.

### Important limits

This remains weak evidence for the word "holographic."

The E36 result is:

- same-session;
- only four identities;
- retrospective;
- based on enrolled query peak indices rather than a spatial aperture;
- evaluated using a scoring rule that knows the enrollment frequency sets;
- not a reconstruction of the missing spectrum or physical field;
- not evidence that *every* fragment contains the whole.

The safe hypothesis is:

> **Task identity is distributed redundantly across the measured spectral response.**

The unsafe claim is:

> "Any piece of the glass contains the complete information."

The latter has not been tested.

---

## 5. FT-0C — E8 gives a spatial version of the same clue

Source:

`data/results/quantum_bridge/e8_compute_basis_20260602_183334.json`

E8 drove two modes and measured them simultaneously at two spatially separated acoustic receivers:

- Ch A: NW receiver through ×11 preamp;
- Ch B: NE receiver direct.

Four input states were tested:

`00, 01, 10, 11`.

Both spatial receivers decoded all four states with 100% same-session accuracy.

But their analog views differed materially. For pattern `11`:

```
receiver A: f1/f2 = 0.2011
receiver B: f1/f2 = 0.3608
ratio-of-ratios = 0.5572
```

So:

> Two different spatial projections of the same plate response contained enough information to recover the same discrete input state.

That is useful evidence for **redundant spatial access**.

### Correction to older interpretation

The historical E8 JSON stores:

`"total_bits": 4.0`

and older notes sometimes describe two bits per receiver as four total bits.

That is not justified if both receivers decode the **same** two-bit state.

For this research direction, the stronger interpretation is actually the more conservative one:

> E8 demonstrates two spatially different analog views that redundantly preserve the same two-bit task identity.

It does not demonstrate four independent bits of information.

### Limits

E8 still does not establish a holographic field:

- only two receiver positions;
- receiver-specific thresholds;
- very high SNR;
- same session;
- no blind receiver removal;
- no frozen cross-position decoder;
- no reconstruction of an omitted spatial field.

---

## 6. FT-0D — the completed FT-1 campaign changes how the hypothesis must be tested

Sources:

- `data/results/k_eff/FT1-S1/`
- `data/results/k_eff/FT1-S2/`
- `data/results/k_eff/FT1-S3/`
- `docs/lab_diary_20261027.md`
- `data/results/k_eff/handling_20261027/`

FT-1 was completed after PR #16 merged.

Its preregistered S1–S3 outcome remains **INCONCLUSIVE** under the original scoring rules.

However, a post hoc diagnosis found that many nominal harmonic comparisons were 15–52 Hz mismatched because the NCO's actual period is quantized.

At matched frequencies, the exploratory reanalysis reported:

- within-session superposition median error: **1.2–2.0%**;
- held-out S1+S2 → S3 error: **7–8%**;
- loopback floor: roughly **0.8–1.6%**.

This does not rewrite the preregistered outcome. It shows that a stable-session transfer is approximately linear and predictable, while later-session error is strongly affected by motion of the physical transfer function.

### Transfer stability findings relevant to partial-view tests

The handling/stability campaign found approximately:

- CH2 complex H sweep-to-sweep floor: ~0.8–0.9%;
- CH1 level floor: ~0.4%;
- undisturbed 4.5 h drift: ~1.5% CH2, ~0.8% CH1;
- overnight temperature dependence: ~2.1%/°C CH2 and ~1.2%/°C CH1 using the NCO die temperature as a proxy;
- 8/10 qualified mode windows showed roughly +24 to +90 ppm/°C mode-frequency coefficients;
- handling/pin/breadboard actions can produce multi-percent, mode-dependent changes.

FT-1 also measured GLASS response well above ELECTRICAL_ONLY in aggregate:

| Session | path F1 median GLASS/ELECTRICAL_ONLY | path F2 |
|---|---:|---:|
| S1 | 36.85 dB | 37.03 dB |
| S2 | 33.42 dB | 33.01 dB |
| S3 | 30.62 dB | 29.18 dB |

### Consequence

A future partial-view experiment must not ask only whether a subset works once.

It must ask:

> **Does a frozen partial view preserve task identity across sessions at least as well as the full view, under measured fixture and temperature variation?**

This is potentially more interesting than demanding the full analog waveform remain unchanged.

A holographic-like distributed representation could be useful precisely if:

```
full H changes
but
task identity from multiple partial views remains stable.
```

That is an empirical question, not something the current data establishes.

---

## 7. Two hypotheses should remain separate

### H-PV — distributed partial-view task identity

> For a frozen CWM encoding and task, multiple independently chosen partial spectral and/or spatial observations retain the same task-relevant identity with graceful degradation as observed aperture decreases.

Primary measurements:

- task accuracy;
- margin;
- abstention;
- fraction of random subsets passing;
- later-session retention;
- performance versus fraction of spectral/spatial aperture.

This is the hypothesis for which the archive already provides a positive prior.

### H-REF — reference-assisted complex reconstruction

> A known coherent acoustic reference can convert an unknown complex CWM response into a simpler interference observable from which amplitude/phase or the task-relevant statistic can be reconstructed with lower receiver burden.

This is motivated by digital holography, but the current archive does **not** test it directly.

It requires fresh data with:

- a known coherent reference path;
- controlled relative phase;
- raw reference and response measurements;
- held-session reconstruction;
- like-for-like conventional complex-readout baseline.

Do not infer H-REF from E8 or E36.

---

## 8. Proposed prior for a fresh test

The retrospective data supports preregistering a bounded prediction rather than starting from "anything might happen."

For spectral partial views, a reasonable first plate experiment can test:

```
aperture fraction:
100%, 75%, 50%, 40%, 30%, 20%
```

with subsets selected independently of the held-out session.

A strong result would be:

1. multiple random/fixed subsets at ≤50% spectral aperture retain a preregistered task accuracy/margin;
2. the result survives complete later sessions without subset or threshold retuning;
3. a frequency-shuffle/null control destroys the advantage;
4. partial-view performance degrades gracefully rather than depending on one privileged mode;
5. spatially separated receivers show the same task identity from materially different analog projections.

Do **not** preregister "100% accuracy with four modes" from E36 as an expected plate result. The rod experiment is a prior, not a transfer guarantee.

---

## 9. What would elevate the claim

### Level 0 — redundancy

Different subsets contain overlapping information.

Already suggested by E26/E36.

### Level 1 — distributed task identity

Random/fixed partial views repeatedly recover the same task state, including held sessions.

**This is the next target.**

### Level 2 — cross-view reconstruction

A model trained on one set of views predicts/reconstructs omitted views or the full response from another view.

Not established.

### Level 3 — reference-assisted complex reconstruction

A coherent reference enables recovery of a complex response from a simpler measured interference observable with a measured receiver advantage.

Not established.

### Level 4 — engineered holographic operator

The physical medium is deliberately designed so spatial/spectral fragments implement a useful reconstruction or task with favorable scaling/cost.

Long-term only.

The project should use the term **holographic-like** no higher than the demonstrated level and prefer the operational term **distributed partial-view representation** in claims.

---

## 10. Decision from FT-0

**Proceed to a new downstream PR.**

Reason:

- merged PR #16 established measurement, held-session and readout-cost discipline;
- E26/E36/E8 provide real but incomplete evidence for distributed partial-view identity;
- FT-1 supplies the stability/control framework needed to test it correctly;
- reference-assisted reconstruction is a logically separate fresh experiment;
- the hypothesis is now specific enough to kill.

The next PR should therefore test:

> **Does CWM preserve useful state identity across deliberately incomplete spectral and spatial views, and can a coherent reference later turn that distributed response into a cheaper complex readout?**
