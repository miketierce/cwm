# FT-3P: Path-Sum Validation and Relational-Compute Fast Track

**Status:** OPEN / revised execution protocol; no new measurements.  
**Parent:** PR #16.  
**Required prerequisite:** [FT-M: Measurement and Claim Gate](MEASUREMENT_AND_CLAIM_GATE.md).  
**Historical evidence:** [Path-sum FT-0 note](PATH_SUM_FT0_EXISTING_DATA_NOTE.md).  
**Literature:** [Physical-computing map](PHYSICAL_COMPUTING_LITERATURE_MAP.md) and FT-M's Deplano et al. entry, DOI `10.1126/science.aeh1375`.

## 1. Objective and claim boundary

Test whether a controlled classical elastic path sum can predict later-session measurements and implement a useful relational task before a compact receiver.

Earlier phase sweeps and the June 21 three-source data provide hypothesis-forming evidence. They do not remove the need for properly defined observables, source references, electrical attribution and held-session validation. A same-session cosine is a sanity check rather than the main research objective.

The Science Advances reference, DOI `10.1126/sciadv.aeh1011`, motivates a structural analogy: many coherent contributions combine into an observable. It does not turn this bench into a quantum path-integral experiment. Similarly, the levitated-oscillator work concerns a quantum mechanical-optical joint state, not proof that CWM's frequency-space matrix is quantum entangled.

Allowed claim after appropriate controls: a classical elastic network combines controlled contributions before detection and supports the declared relational operation. Do not claim single-phonon operation, quantum entanglement, a Bell-test violation or quantum computational advantage from this protocol.

## 2. Keep three outcomes separate

1. **Physical attribution:** is the measured effect dependent on the acoustic path rather than explained by the source/wiring/readout alone?
2. **Dimensional result:** how many independently useful outputs survive the declared receiver budget and later-session tests?
3. **Task advantage:** does the complete implementation outperform the simplest fair alternative at the required accuracy?

P coherent contributions can generate P(P-1)/2 pairwise terms in a squared-magnitude expansion. These are not independent measured outputs, independently programmable weights or a digital-complexity lower bound. An electronic baseline can sum P complex numbers and take one magnitude square in O(P) work. Benchmark that implementation, not a deliberately expanded O(P^2) calculation.

A successful single-score predicate may have one output dimension. Supported interference terms characterize the mechanism; they do not by themselves establish useful computation or K_eff scaling.

## 3. Hardware and reference configuration

Use one fixed plate, one RX and initially two phase-controlled TX PZTs. Extend to three/four only after qualification.

```
phase-coherent sources -> separately driven TX1, TX2[, TX3, TX4]
                                      |
                                 fixed plate H
                                      |
                                  one RX -> Ch A

qualified electrical/phase reference -> Ch B or additional documented channel
```

Fix RX, fixture, scope range, physical sampling rate, samples/capture and acquisition window for the main comparison. Record source and reference overhead as the number of TX channels increases.

**Ch B is a role assignment, not a guarantee.** Historical E1/E2 used it as a second acoustic receiver. It cannot simultaneously perform that role and provide an independent electrical reference. Document the choice, extra hardware or coherent sequential procedure and its cost.

At a common carrier, a summed electrical reference may destructively interfere. Do not divide RX by that sum near a null. Use a stable reference and independently qualified source phasors, or record individual sources with suitable instrumentation. Recheck reference stability before/after runs and quantify unobserved within-run uncertainty. Never short source outputs together to create a tap.

Keep inactive transducer termination/loading unchanged when characterizing individual paths. Disabling a drive can otherwise change H itself. Record buffer/tap positions, load impedances, gain/phase calibration, source amplitudes, phase commands and measured phase verification.

## 4. Measurement definitions

Retain raw per-acquisition voltage samples and complex demodulated coefficients before magnitude conversion, averaging or normalization. Declare whether phasor amplitudes are RMS or peak.

Use:

- `z`: complex demodulated receiver voltage;
- `abs(z)`: voltage magnitude;
- `abs(z)^2`: squared-voltage statistic under the stated convention;
- physical power/energy only with the required impedance/transduction calibration.

Historical sums of FFT magnitudes must not be interpreted directly as energy. Reproduce those statistics for historical comparison, but keep them separate from fresh calibrated observables. Fit/model comparisons must use the same observable on both sides.

Complex phase is unreliable near zero amplitude. Predefine the reference/SNR mask for phase-error summaries, retain all valid complex/magnitude data, and report excluded counts. A cancellation null is not a requirement for a stable phase angle at zero.

## 5. FT-3P-1: frozen prediction from individual paths

### Training/qualification

Define a common phase frame. At the chosen carrier, estimate end-to-end complex coefficients h_j using the measured source phasors x_j, with receiver and source-reference calibration recorded:

```
z_pred = sum_j h_j * x_j
```

For unit fixed-amplitude sources, two paths reduce to `z_pred(phi) = h_A + exp(i*phi)*h_B`. Do not apply this reduced formula if source amplitudes or phase origins vary without accounting for them.

Measure individual paths and matched controls. Freeze carrier, gains, phase offsets, preprocessing, thresholds, uncertainty model and allowed operational reference procedure before the evaluation session.

### Held-session evaluation

Power down and restart on a later day. Initially use 16 relative-phase points over a full cycle and at least 20 independent acquisitions/point, with randomized order. Use measured source references only under the frozen policy; no fitting of new h_j from test RX data.

Primary outputs:

- complex normalized error and its block/session uncertainty;
- magnitude and squared-magnitude error;
- phase error on the preregistered valid subset;
- null-location drift, contrast and reference validity;
- performance before any optional recalibration.

Compare coherent `abs(sum h_j*x_j)^2` with incoherent `sum abs(h_j*x_j)^2` using the same squared-magnitude loss. Alternatively compare their square roots against measured magnitude. Report complex error separately, because the incoherent model has no corresponding phase prediction.

**Advance:** frozen prediction is within preregistered tolerances and outperforms the applicable baseline on the same observable. A fresh fit to the evaluation sweep is descriptive, not a pass.

## 6. FT-3P-2: attribution and equivalent-computation controls

Run GLASS, source-reference measurements, ELECTRICAL_ONLY/background, LOOPBACK and QUIET. Change or interrupt mechanical coupling with electronics/loading preserved as closely as possible and document unavoidable changes.

Evaluate both the fixed glass decoder on controls AND control-specific decoders trained only on control training data. A threshold mismatch is not proof of an acoustic contribution.

Separately evaluate a conventional summing/filtering or digital implementation of the declared function. Full source phases already encode the input bits; source-only decoding is allowed to succeed. The objective is not information creation, but a useful acoustic transformation with a measured implementation benefit.

An equivalent electrical circuit working does not establish that the GLASS measurement was feedthrough. An acoustic control passing does not establish that the glass is the cheaper implementation. Report those decisions independently.

## 7. FT-3P-3: frozen phase-equality gate

Start with a two-bit qualification task, not a novelty claim. Encode each bit as phase 0 or pi relative to a fixed, pre-calibrated path offset.

If `h_A` and `h_B` differ in phase or gain, select safe source amplitudes/offsets on training data so the effective contributions are comparable. Their required compensation is part of calibration, not a free property of the glass.

```
00 -> same relative phase
11 -> same relative phase
01 -> opposite relative phase
10 -> opposite relative phase
```

For matched effective contributions, a magnitude or squared-magnitude statistic can distinguish equality from inequality with one frozen threshold. Test all four input states with balanced randomized trials; do not select only favorable combinations.

Engineering target: at least 95% balanced accuracy on the held session, with per-class counts, uncertainty, abstention and calibration cost reported. Include individual-TX magnitude controls, reference-only processing and the attribution/computational baselines above. Set adequate trial counts and statistical acceptance rules before acquisition; a nominal percentage without its uncertainty is insufficient.

Success qualifies a relational primitive. It does not show that electronics cannot compute equality, or that acoustic XNOR is new.

## 8. FT-3P-4: three-path validation

Use the historical 91 kHz / three-TX configuration only after current fixture/source qualification; the old frequency is a candidate, not a universal standard.

Training model:

```
z = h1*x1 + h2*x2 + h3*x3
```

Its squared magnitude produces self-terms and pairwise phase-difference terms. A free seven-term trigonometric fit to a grid is a useful diagnostic, but does not automatically satisfy the consistency constraints of one coherent phasor sum. Preserve the physical coefficient constraints and compare with independently characterized paths where possible.

Freeze the model and predict the entire later-session phase grid without coefficient/phase retuning. Report held-session error, residuals and interaction stability with uncertainty. For a purported 2<->3 term, compare with a model omitting that interaction and appropriate source/control measurements; fitted coefficient size alone neither localizes the interaction nor establishes its significance.

**Advance:** the physical model predicts qualified later measurements within the declared operating envelope. No fixed-phase slice of a three-source grid may be labeled a true two-source control unless the third source was disabled with matched termination.

## 9. FT-3P-5: four-path extension

Only after three-path qualification. Four sources create up to six pairwise terms, but share the constraints of four complex path coefficients. Use training-only path characterization and held-session prediction rather than granting every cross-term an arbitrary independent weight.

Account for the added drive ports, source power, synchronization and calibration even when the RX capture remains unchanged. Stop at the largest controlled system the existing coherent-source hardware can actually support; do not infer coherence across unqualified source blocks.

## 10. FT-3P-6: scaling and workload decision

For P=1,2,3,4, retain one RX and a fixed primary capture budget where possible. At each P record:

| Category | Record |
| --- | --- |
| Physical model | Path count, actual source phasors, supported interactions, held-model error, noise/drift and controls |
| Useful task | Frozen target function, all tested input classes, accuracy, abstention and confidence intervals |
| Output dimensions | K_eff estimates under the declared receiver, or explicitly unmeasured |
| Receiver | Signal/reference channels, samples/capture, all repetitions, acquisition/settle/reconfiguration time |
| Whole system | Source, transducer, detector, conversion, digital processing and amortized calibration costs |
| Baselines | Equivalent O(P) complex-sum implementation and relevant analog/filtering alternative |

Produce separate dimensional and task/cost frontiers. A growing number of supported pairwise terms is a mechanism diagnostic, not the vertical axis of a claimed computational speedup. Comparing more tasks is meaningful only when their difficulty, resources and evaluation are defined consistently.

**GREEN-A:** independent useful output increases with sublinear/fixed readout cost under qualified testing; comparative workload advantage remains a separate claim.  
**GREEN-B:** a frozen relational task has the preregistered comparative accuracy/cost benefit, even with a scalar output.  
**YELLOW:** useful acoustic behavior but no demonstrated comparative advantage.  
**INCONCLUSIVE:** missing references, provenance, calibrated observables or held-session controls.  
**RED:** a qualified test rejects the stated operation/scaling hypothesis.  
**Quantum:** not tested here.

## 11. Data and analysis readiness

Use the existing layout:

```
data/results/path_sum/<session_id>/
    manifest.json
    trials.csv
    raw/
    derived/
        individual_paths.json
        phase_sweep.json
        relational_gate.json
        multi_path_model.json
        scaling_frontier.csv
```

Keep trial_id, session_id, path_state, device_id, carrier, enabled TX set, commanded amplitudes/phases, available measured source phasors, RX real/imaginary voltage, target relation, split, validity and exclusion reason. FT-M adds calibration IDs, phase-reference method, physical/synthetic provenance, file hashes, averaging, channel roles and exact sampling settings.

The existing `path_sum_interference_analyze.py` does not yet enforce this protocol. Its pooled calibration and cross-observable `coherent_model_better` comparison are not acceptance criteria. Before using it for certification, implement/test disjoint sessions, grouping, validity/reference checks and like-for-like errors, or use a separately audited compliant analysis. This PR's measurement revision is documentation, not a claim that those code changes or new bench runs are complete.

## 12. Execution order and longer-term relevance

```
historical triage -> FT-M qualification
 -> frozen two-path prediction + matched controls
 -> frozen equality gate
 -> frozen physically constrained three-path model
 -> four-path extension
 -> dimensional and comparative task/cost frontiers
```

Interleave controls from the first fresh capture. Calibrate once on training sessions, then score later data before any recalibration. Reduce the receiver only after the richer measurement establishes what it can safely discard.

A later engineered propagation graph may use branches, delays, reflectors or coupled resonators to create useful transformations. That remains a design hypothesis. This protocol first asks whether the present classical H earns a useful implementation role without claiming quantum behavior or requiring a measured decay time.
