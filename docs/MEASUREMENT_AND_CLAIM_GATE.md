# FT-M: Measurement and Claim Gate

**Status:** OPEN / required measurement protocol, not a new experimental result.  
**Added:** 2026-10-09.  
**Parent:** PR #16, classical K_eff and relational-compute fast track.  
**Applies to:** FT-1 through FT-6 and FT-3P. These requirements take precedence over conflicting shorthand in earlier fast-track notes. Historical data and original analysis outputs remain unchanged.

**Receiver-reduction addendum (2026-10-13):** [Task-evidence retention](TASK_EVIDENCE_READOUT_RETENTION.md) specifies the FT-2/FT-4/FT-5 comparison of full observations, offline statistics and actual reduced receivers. It includes the relative-entropy literature entry, analytical examples and reusable citation records without adding a gravity or quantum-hardware dependency.

## 1. Decision

Keep the immediate objective classical: determine whether a repeatable physical transfer function performs a useful task with a favorable readout and whole-system cost.

The levitated-oscillator literature adds a measurement lesson, not a requirement to build optical levitation hardware. Characterize the transfer function, uncertainty, phase reference and drift before reducing the receiver. Neither a large concurrence nor an optimized CHSH-like number is a fast-track acceptance metric.

A measured ringdown time is not a prerequisite for the driven classical experiments. Adequate phase stability over the declared acquisition and between training/test sessions must nevertheless be demonstrated when the proposed operation depends on phase.

## 2. New literature entry: what it establishes and what transfers

**Q. Deplano, A. Pontin, F. Marino and F. Marin, "Stationary entanglement of a levitated oscillator with an optical field," Science 394, 113 (2026). DOI: [10.1126/science.aeh1375](https://doi.org/10.1126/science.aeh1375).**

Primary accessible version: [arXiv:2602.03456v2](https://arxiv.org/html/2602.03456v2); [version history and journal reference](https://arxiv.org/abs/2602.03456). Record v1 submission (2026-02-03) and v2 revision (2026-03-19) separately from the October news coverage. Do not substitute a news date for a priority or first-publication date.

The study concerns center-of-mass motion of a levitated silica nanosphere coupled to propagating light, not internal sound modes of a supported glass plate. It combines cooling/stabilization with an entangling interaction and phase-sensitive, quantum-noise-calibrated covariance measurements. Room-temperature surroundings do not mean the relevant motion is thermally uncontrolled. The accessible v2 reports a minimum partially transposed symplectic eigenvalue of 0.918 +/- 0.029 with additional systematic uncertainty +/- 0.02; its convention places the separability boundary at 1. This number is version-specific and is not comparable to CWM's normalized-matrix concurrence. See main-text experimental procedure, data analysis and results sections, and Supplementary Sections II.6, III.1 and V.

**CWM application (proposed):** document reference channels, preserve complex measurements, separate statistical/systematic errors and distinguish a fitted explanation from independently tested predictions.

**Not established for CWM:** quantum entanglement, quantum advantage, a manufacturing route for the current plate, or a computing advantage. No numerical performance is transferred between platforms.

## 3. Repository evidence boundary

Audit anchors below are pinned to main commit `c6f08ff95b03438c8f99b43086f86ebc1cf54c68`.

- [E1 acquisition and analysis](https://github.com/miketierce/cwm/blob/c6f08ff95b03438c8f99b43086f86ebc1cf54c68/tools/e1_multi_pair_chsh.py): `capture_dual`, `run_chsh_pair`, `S_chsh_real` and `optimize_S` show magnitude acquisition, row/Frobenius normalization and software-generated projections/angle optimization.
- [E1 saved result](https://github.com/miketierce/cwm/blob/c6f08ff95b03438c8f99b43086f86ebc1cf54c68/data/results/quantum_bridge/e1_multi_pair_chsh_20260602_165503.json): first selected pair reports concurrence 0.9990934 and optimized S 2.8271453. These are derived descriptors of the normalized response, not independent physical Bell settings.
- [E2 saved result](https://github.com/miketierce/cwm/blob/c6f08ff95b03438c8f99b43086f86ebc1cf54c68/data/results/quantum_bridge/e2_complex_tomography_20260602_170330.json): complex concurrence 0.9237424 with 95% interval [0.1981842, 0.9990388], `phase_stable=false`, verdict `INCONCLUSIVE`. Keep that verdict; do not replace it with the more precise magnitude-only result.
- [Manuscript discussion](https://github.com/miketierce/cwm/blob/c6f08ff95b03438c8f99b43086f86ebc1cf54c68/paper/v19r.md): Sections 6.1-6.3 distinguish spatial-spectral structure, optimized-angle descriptors and complex-tomography uncertainty.
- [Separate quantum roadmap](QUANTUM_TRANSITION_ROADMAP.md): an exploratory program with its own physical preparation, control and witness requirements, not an advancement stage automatically unlocked by this fast track.

The supported classical observation is that the measured receiver pattern changes with frequency and is not described by one frequency-independent spatial response times a scalar gain. A nonfactorizable magnitude matrix is useful structural evidence. It is not complete coherent-state tomography and cannot certify quantum entanglement.

Nonseparability of a constructed classical amplitude matrix, coherent interference, reliable task performance, quantum-state entanglement and quantum computational advantage are distinct claims. Do not use evidence for one as certification of another.

## 4. FT-M0: channel-role and synchronization qualification

Every session must declare physical roles rather than relying on letters such as Ch A and Ch B.

| Configuration | Ch A | Ch B | What it measures |
| --- | --- | --- | --- |
| Historical June 2 E1/E2 | NW acoustic RX through preamp | NE acoustic RX direct | Two spatial acoustic responses; NOT an electrical-only control |
| Single-RX transfer measurement | Acoustic RX | Electrical source tap | A driven transfer estimate, subject to reference SNR and gain calibration |
| Two-RX spatial transfer mapping | Acoustic RX1 | Acoustic RX2 | Needs a separate qualified source/phase reference for the intended complex measurement |

Two channels cannot simultaneously record two RX signals plus an independent electrical reference. Choose and document extra acquisition hardware or a phase-coherent sequential protocol whose stability is measured. Never label sequential acquisition simultaneous, and count its extra time, samples and reference checks.

For multiple same-frequency transmitters, a summed electrical reference may itself cancel. It must not be the sole denominator or phase reference near its null. Use separately verified source references, a stable common phase reference, or a qualified coherent-source procedure. Before/after loopback checks support but do not prove within-run source stability; unresolved drift makes the coherent test inconclusive.

Record the tap location relative to buffers/PZT loading. `Za/Zb` includes uncalibrated receive gain, reference attenuation and other electronics; call it an end-to-end transfer unless de-embedded. Do not short independent drive outputs together to obtain a reference. Any summing network must isolate sources and remain within documented electrical limits.

**Gate:** topology, channel gains/delays, source coherence, reference SNR, clipping and sampling settings are qualified against limits frozen before held-out capture.

## 5. FT-M1: preserve the information needed to audit the result

Save per-acquisition raw samples, before averaging, for every recorded channel. Preserve physical sample rate and sample count; zero-padding does not create extra measurements or improve physical frequency resolution.

The session manifest must include:

- source commit, acquisition-script hash, firmware revision and `physical` versus `synthetic` provenance;
- device/fixture IDs, PZT roles/positions, wiring photograph or diagram hash, channel roles and gain/calibration IDs;
- reference mode (`simultaneous_electrical`, `coherent_external`, `qualified_sequential`, or `none`) and verification method;
- actual sample rate, samples per channel, enabled channel count, repetitions, averaging policy and settled-drive delay;
- commanded AND measured source quantities where available, voltage-unit convention (peak or RMS), window/demodulation method;
- temperature, power cycles, remounts and reconnects;
- train/test session IDs, randomization seed, thresholds, exclusion policy and allowed-calibration policy frozen before evaluation;
- raw-file hashes, exclusions with reasons, and identification of unavailable quantities. Missing data is not zero.

Preserve complex Fourier/demodulated coefficients before taking magnitudes, normalizing or averaging. For multiple coherent acquisitions, align phase to the declared reference; do not average arbitrary oscilloscope phases and call the result a state.

Distinguish voltage magnitude, squared voltage and calibrated power/energy. Squared voltage is not automatically acoustic energy. A summed FFT-magnitude statistic must not be relabeled as power.

**Gate:** retained captures and metadata suffice to reproduce the measured statistic and distinguish physical acquisition from synthetic demonstrations. Summary-only historical files remain exploratory.

## 6. FT-M2: freeze a transfer-plus-uncertainty model

Use `y = H x + epsilon` as the linear starting point, with an explicit acquisition definition and stated operating envelope. Estimate training residual covariance across channels/frequencies and separate within-session noise from session-level drift. Do not attribute every residual to glass physics.

Report calibrated raw and normalized results side by side. Fit preprocessing on training data or use an independently measured operational reference available at inference. Per-input row normalization can rebalance a response and raise concurrence without increasing recoverable signal or computing benefit; it must not hide gain drift, weak channels or unavailable calibration.

Preselect modes, thresholds and confidence criteria on training/qualification data. Randomize input order. Keep a complete later session locked; power cycling and remounting are distinct perturbations and must be reported separately. A recalibrated secondary score may be reported only alongside the untouched zero-retuning score and its calibration cost.

For phase, use circular statistics and a preregistered amplitude/reference-SNR threshold. Phase near a true cancellation null is ill-conditioned: score the complex residual or magnitude instead of demanding a stable phase angle at zero amplitude. Count the samples excluded from any phase-only metric.

For coherent versus incoherent predictions, compare BOTH on the same magnitude observable or BOTH on the same squared-magnitude observable with the same normalization. Also report complex error separately. Comparing coherent complex NRMSE directly to incoherent magnitude NRMSE is not a fair model-selection test.

Do not fit a seven-term surface to the held-out data and call that prediction. A free trigonometric fit is descriptive; prediction from independently characterized path gains and a physically constrained sum is stronger. Positive cross-terms alone do not locate the interaction in the glass rather than in electrical mixing/readout.

**Gate:** frozen predictions remain within declared tolerances across the held session, with residuals, block/session uncertainty and systematic calibration sensitivity reported. Extra FFT bins or overlapping windows are not independent experimental replications.

## 7. FT-M3: causal controls and task utility are different tests

**Causal controls:** quiet, loopback, matched electrical-only/background and a mechanically changed or interrupted path with electronics preserved as closely as possible. Train control baselines on their own training data as well as applying the frozen glass decoder. A glass-trained threshold failing on an electrical path is not sufficient attribution; it may merely be a gain mismatch. Conversely, electrically reproducing an operation does not prove the GLASS run was feedthrough.

**Task baselines:** source-only decoding, a conventional analog summing/filtering circuit and a simple digital implementation. Each gets a fair, disclosed training budget. Full access to the input can reveal the target relation; the glass is not required to create information missing from X. The intended advantage is useful transformation at lower cost for the required accuracy.

For `|sum(h_j*x_j)|^2`, an efficient digital baseline sums P complex contributions then takes one magnitude square: O(P), not O(P^2). Counting the expanded pairwise terms does not establish a quadratic speedup. One magnitude observation also does not independently reveal every pairwise term.

Document input encoder, source, transducer, reference, settle time, averaging, acquisition, detector, decoder and calibration costs. Fixed RX count alone is not fixed system cost. Detector nonlinearities such as envelope extraction/thresholding belong in the system boundary even when the elastic medium is linear.

**Gate:** make two separate decisions: (a) acoustic contribution supported, unsupported or inconclusive; (b) measured task/cost improvement supported, absent or unmeasured. K_eff or concurrence alone cannot pass (b).

## 8. FT-M4: reduce the receiver only after measurement qualification

Proceed through the existing ladder: full complex response, selected observables, envelope/scalar statistic, low-bit decision. Freeze each candidate receiver on training data and test it later. Record what information is intentionally discarded and the corresponding change in accuracy, abstention, latency and total cost.

A candidate scalar predicate can pass even if output dimension remains one. A dimensional-scaling claim requires independently recoverable output dimensions under the stated receiver budget. Neither path count nor the number of fitted functions is a substitute.

**Task-evidence retention:** follow [the FT-2/FT-4 addendum](TASK_EVIDENCE_READOUT_RETENTION.md). Declare a task, full-observation baseline, noninferiority margin, absolute error target, confidence/sample plan and cost criterion before testing. Learn candidate statistics only on training data and score complete later sessions. A scalar linear score can be sufficient under the stated equal-covariance Gaussian model; a phase-equality task may instead need a magnitude-based statistic. Neither analytical example establishes a physical CWM implementation.

Distinguish offline compression of full captures from an actual reduced receiver. Only the latter can demonstrate acquisition savings, after accounting for its source/reference/detector/ADC/calibration chain. Optional KL or likelihood diagnostics supplement task errors and uncertainty; they do not certify capacity, prove exact sufficiency from finite data, or replace the measured cost comparison. The gravity paper is recorded as conceptual motivation only; classical information theory supplies the applicable analysis.

## 9. Tooling and outcome status

The existing `tools/path_sum_interference_analyze.py` is exploratory: it pools individual-path rows without enforcing held-session isolation and compares complex and magnitude errors as if they were the same objective. Do not use its `coherent_model_better` field as an FT-M acceptance decision. `tools/k_eff_frontier.py` summarizes supplied values; it does not validate K_eff or experimental provenance. This documentation update does not claim those tools have been upgraded.

Before certification, implement and test: explicit disjoint train/test sessions, grouping by device/topology/frequency, invalid-row and nonfinite-data rejection, reference-SNR checks, and like-for-like model errors. Until then, record results as exploratory or perform a separately audited analysis satisfying this gate.

**GREEN-CLASSICAL:** a frozen task result passes causal controls and the preregistered accuracy/cost comparison.  
**QUALIFIED-NO-ADVANTAGE:** reliable acoustic operation, no measured comparative benefit yet.  
**INCONCLUSIVE:** reference, calibration, raw data or held-session requirements are missing.  
**QUANTUM:** not a possible outcome of this protocol.

## 10. Scope and next bench sequence

No change to public-site claims, patent files, historical lab data or previous result labels is authorized by this note. The quantum roadmap remains separate; a future quantum experiment needs a specified joint state, physical preparation/control, calibrated quantum noise and an appropriate witness with uncertainty. Cooling the laboratory to cryogenic temperature is not a universal requirement; increasing classical matrix concurrence is not a shortcut.

Next sequence:

1. Restore and document the exact TX/RX/reference topology; qualify gain, delay, phase and clipping.
2. Collect matched single-path, combined-path and control captures, retaining raw complex information.
3. Freeze transfer, noise model, task and decoder on training sessions.
4. Power down and evaluate a complete later session without retuning.
5. Reduce the receiver and compare full-system cost at the same accuracy.

The question remains whether the physical H is useful. This gate makes the answer interpretable without requiring a quantum claim or a measured decay time.
