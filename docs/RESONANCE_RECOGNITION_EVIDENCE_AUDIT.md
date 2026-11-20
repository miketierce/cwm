# Resonance Recognition Evidence Audit

**Status:** retrospective hypothesis-forming review  
**Parent:** PR #17  
**Date:** 2026-11-11

## Question

What does the existing repository already tell us about two increasingly strong versions of the "dueling pianos" idea?

### Version 1 — call-and-response / resonance recognition

A structured query is applied to a configured physical operator and a compact response score identifies compatibility:

```
query x -> H_theta -> score s
```

With multiple responders, the candidate decision is `argmax_k s_k`.

### Version 2 — mutually coupled "dueling pianos"

Two physical systems affect one another bidirectionally until a dynamical observable emerges:

```
A <-> B
```

Possible observables include phase locking, synchronization, cancellation, attractor selection, failure to lock, and convergence time.

The archive contains substantially more evidence for Version 1 than Version 2.

---

## Evidence for Version 1

### E26 — partial query

Source: `data/results/lab/additional_exps/additional_20260409_171342.json`

Historical four-way rod identification:

- K=1 of 10 selected peaks: 50% (2/4)
- K=2 of 10: 100% (4/4)
- K=3..10: 100%

This is adaptive top-K, same-session evidence. It supports small-query recognition but not arbitrary-subset robustness or reconstruction.

### E36 — arbitrary subset frontier

Source: `data/results/lab/additional_exps/additional_20260411_105304.json` plus PR #17 retrospective enumeration.

Using every combination of saved mode indices:

| K retained | mean 4-way accuracy | subsets 4/4 correct |
|---:|---:|---:|
| 1 | 65.0% | 10.0% |
| 2 | 68.3% | 20.0% |
| 3 | 80.0% | 36.7% |
| 4 | 92.0% | 68.6% |
| 5 | 95.1% | 80.6% |
| 6 | 97.6% | 90.5% |
| 7 | 98.8% | 95.0% |
| 8 | 99.4% | 97.8% |
| 9 | 100% | 100% |
| 10 | 100% | 100% |

This is consistent with distributed task redundancy: recognition is not confined to one privileged mode.

The original E36 controls also found correct scoring 4/4, shuffled enrollment 0/4, and random scoring mean accuracy 22.5% (near the 25% four-way chance level). These controls are useful context but do not make the subset frontier a held-session result.

### E8 — distinct spatial views preserve the same task

Source: `data/results/quantum_bridge/e8_compute_basis_20260602_183334.json`.

Two spatially separated receivers each decoded all four two-bit states at 100% in the same session, with no disagreements.

For state `11`, their measured f1/f2 ratios were materially different:

- receiver A: 0.2011
- receiver B: 0.3608
- ratio-of-ratios: 0.5572

This supports redundant spatial access to task identity. It does not prove extra independent bits or full-field reconstruction.

### E9 — phase relation collapses into a strong scalar contrast

Source: `data/results/phase_cancellation/e9_phase_cancellation_20260603_195303.json`.

Across five tested modes:

- mean erase depth: 98.87%
- maximum erase depth: 99.10%
- optimum destructive phase: 180 degrees
- mean write->erase->write recovery: 99.72%

This is directly relevant to resonance recognition because a relational variable (relative phase) is converted by the physical path into a large amplitude contrast that can be read with a simple observable.

It is not evidence that the plate learns or that a full classifier is implemented physically.

### Three-path phase interference — richer relational response before readout

Source: `data/results/phase_interference/three_path_20260621_154927.json`.

At 91 kHz, the saved three-path run reported:

- 7-term coherent interference fit R^2 = 0.9216
- path-pair terms I12 = 59,961; I13 = 25,007; I23 = 50,064
- 3-path cancellation = 97.19%

The large 2<->3 term demonstrates that multiple externally controlled paths can interact in the shared physical field before the one-receiver readout.

This is strong precedent for relational scoring, but it remains externally driven open-loop interference.

### FT-1 — task invariance is a better target than waveform invariance

Sources: FT1-S1/S2/S3 results and October 2026 lab diaries.

The controlled campaign showed that detailed complex H can move across sessions and handling:

- S1->S2 median complex change about 3%
- S2->S3 about 10%
- post-hoc exact-frequency analysis found roughly 1.2-2.0% median within-session superposition error and 7-8% held-out error
- GLASS response remained roughly 29-37 dB above ELECTRICAL_ONLY in median across sessions

This does not establish recognition invariance. It tells us what the fresh recognition experiment should measure: whether the frozen winner/decision survives even when the detailed analog response moves.

---

## Evidence adjacent to Version 2

### P6 physical cascade — feed-forward chaining exists

Sources: `docs/lab_diary_20260603.md`, `docs/WORKLIST.md`.

The archive records a physical Plate I -> Plate H cascade with:

- all 27 tested modes propagating through the cascade
- 1.73x measured rank expansion

This shows that one physical wave system can feed another and change the resulting representation.

It is the closest existing hardware precursor to coupled multi-node CWM, but it is **feed-forward**, not a feedback loop.

### Three-path interference — shared-field interaction exists

The three-path result proves simultaneous paths can interact coherently in one medium. It does not show that one resonator's output changes another resonator's future state.

### What the archive does NOT contain

The original worklist explicitly left the most relevant dynamical tests undone:

- T5.4 phase-sweep hysteresis: not started
- T5.5 synchronization threshold: blocked
- T5.3 directional/nonreciprocal coupling: blocked in that campaign

No saved result located in this review establishes:

- spontaneous synchronization between two resonators;
- bidirectional closed-loop coupling;
- self-selected phase locking;
- an attractor created by mutual feedback;
- convergence to a task answer without externally imposing the phases.

Therefore Version 2 remains a proposed architecture, not a result.

---

## Current evidence verdict

| Architecture | Evidence level | What the archive supports |
|---|---|---|
| Version 1: call-and-response resonance recognition | **Promising / test now** | distributed partial-query identity, multiple spatial views, strong phase-relation contrast, multi-path relational interference |
| Version 2: true mutually coupled dueling pianos | **Precursor only** | feed-forward cascade and shared-field interference; no closed-loop synchronization/attractor evidence yet |

The strongest new working thesis is:

> **CWM may be more naturally tested as a physical recognizer of relationships than as a device where individual modes represent individual symbols.**

The shortest decisive Version-1 experiment remains RR-1: freeze two physical responders, use families of nonidentical queries, and test later-session `argmax(s_A, s_B)` with no retuning.

Only after RR-1 survives controls should a Version-2 experiment close the loop with bounded coupling and explicitly test for synchronization/phase-locking/attractor behavior against an open-loop control.
