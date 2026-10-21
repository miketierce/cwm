# Task-evidence retention during receiver reduction

**Status:** OPEN / protocol and analytical examples only. No new CWM measurement or demonstrated advantage.  
**Added:** 2026-10-13.  
**Parent:** PR #16, [K_eff fast track](K_EFF_FAST_TRACK.md).  
**Applies to:** FT-2 readout ablation, FT-3P relational decisions, FT-4 receiver reduction and FT-5 frozen later-session testing. This is an addition to those steps, not a new hardware branch. [FT-M](MEASUREMENT_AND_CLAIM_GATE.md) remains the prerequisite.  
**Citation records:** [task_evidence_readout.bib](references/task_evidence_readout.bib). The references below supplement the [literature map](PHYSICAL_COMPUTING_LITERATURE_MAP.md).

## 1. The engineering hypothesis

> For one declared task, a frozen CWM operator plus a physically realizable small receiver can retain the required decision performance of a richer measurement while reducing a specified whole-system cost relative to a fair conventional implementation.

This is not a hypothesis that glass creates information, that every task has an inexpensive scalar receiver, or that classical correlations certify quantum entanglement. A smaller feature vector computed after acquiring the full waveform is only an offline readout candidate.

Keep three quantities separate: independent output dimension K_eff, task-relevant statistical distinguishability, and the cost of physically obtaining the decision. A low-dimensional output may serve a task well without increasing K_eff.

## 2. Literature entry and limits

**Motivation only: Dorau and Much, "From Quantum Relative Entropy to the Semiclassical Einstein Equations," Physical Review Letters 136, 091602 (2026), DOI [10.1103/lmq8-nsty](https://doi.org/10.1103/lmq8-nsty).** Publisher date: 2026-03-02. First preprint: 2025-10-28; consulted version: [arXiv:2510.24491v3](https://arxiv.org/html/2510.24491v3), revised 2026-03-03. [Version history](https://arxiv.org/abs/2510.24491). Record these separately from October news coverage.

This is a theoretical quantum-field/spacetime argument, not an acoustic-computing experiment. For specified field states near a horizon, the authors relate relative entropy to energy flux and, assuming the Bekenstein-Hawking entropy-area relation, recover semiclassical gravitational equations. It motivates asking what distinctions an observation preserves; it supplies neither a CWM device model nor evidence for CWM performance. Do not transfer its horizon, gravity or quantum claims to the plate.

**Applicable analysis:** classical detection and information theory. Polyanskiy and Wu [R2] supply the data-processing framework; Stanford's LDA notes [R3] give the common-covariance classification model. The worked examples below are analytical consequences of stated models, not new results of the gravity paper or the CWM bench.

## 3. Information accounting

Let S be the task label, X the encoded physical input, Y the full qualified receiver observation, and Z a reduced statistic. Conditional on frozen calibration, if S -> X -> Y -> Z is a Markov chain, then [R2]:

$$I(S;Z) \leq I(S;Y) \leq I(S;X).$$

For the same class-independent stochastic processing K applied to two observation distributions P and Q, relative entropy also contracts:

$$D_{KL}(PK\|QK) \leq D_{KL}(P\|Q).$$

These results do not prohibit an efficient physical processor. They prohibit claiming new information merely from deterministic processing. The useful question is how cheaply the required evidence becomes accessible.

The conditions matter. A physical replacement receiver can change noise, loading and bandwidth; it is not automatically a post-processing Z=g(Y) of a separately recorded laboratory waveform. Compare its performance experimentally, not by assuming the same Markov chain across different hardware configurations. Include any operational reference or side information in the observation and cost boundary. Do not give the reduced receiver hidden access to labels or test-session calibration.

KL divergence is directional, uses a declared logarithm base, and is not an accuracy percentage or an effective-rank measure. A single analog scalar is not a single bit: its usable precision, bandwidth and noise count. A final b-bit report contains at most b bits of mutual information about S, even if the internal analog statistic is richer.

## 4. Worked example: when one scalar is sufficient

Assume a real-valued full observation, or a real vector formed by stacking real and imaginary components:

$$Y|S=s \sim \mathcal N(\mu_s,\Sigma), \qquad s\in\{0,1\},$$

where the common covariance Sigma is positive definite and the means/covariance are known. This is a model assumption, not a measured property of CWM. Let delta=mu_1-mu_0, and define:

$$w=\Sigma^{-1}\delta, \qquad Z=w^T Y, \qquad d^2=\delta^T\Sigma^{-1}\delta.$$

The log likelihood ratio is:

$$\log\frac{p(Y|1)}{p(Y|0)}=w^TY-\tfrac12(\mu_1+\mu_0)^Tw.$$

Thus Z retains the likelihood ratio for this pair of hypotheses. Its class means differ by d^2 and its common variance is d^2. For d^2>0, using natural logarithms:

$$D_{KL}(P^Y_1\|P^Y_0)=\tfrac12d^2
=\frac{(d^2)^2}{2d^2}=D_{KL}(P^Z_1\|P^Z_0).$$

If delta=0, both divergences are zero and there is no class distinction in this model. With a fixed prior and decision cost, thresholding Z yields the same optimal binary decision as the full Y, but generally discards confidence and does not preserve the full KL divergence.

This example does not establish an inexpensive physical implementation of w. A high-rate ADC followed by a digital weighted sum is the conventional baseline. A CWM benefit requires a physically realizable operator/readout that obtains the needed score with a measured advantage.

In data analysis, estimate covariance and weights on training data only. Use regularization selected within training data when needed, report its effect, and do not claim exact sufficiency from an estimated regularized model. Different covariances, multiple classes, nonlinear responses or multimodal distributions require separate treatment.

## 5. Counterexample: a mean-based score can miss the phase relation

For an ideal phase-compensated, balanced two-path system:

$$y=a s_1+a s_2, \qquad s_j\in\{-1,+1\}.$$

With both equal-sign input states equally represented, the same-sign class takes values +2a and -2a; the opposite-sign class takes value zero. Both class means are zero. A mean-difference linear statistic therefore misses this ideal relation.

The squared magnitude instead gives:

$$z=|y|^2=\begin{cases}4|a|^2,&s_1=s_2,\\0,&s_1\ne s_2.\end{cases}$$

This is an illustrative algebraic limit, not an observed noiseless gate. The elastic path provides the sum; magnitude/square-law detection and thresholding are parts of the receiver and cost boundary. Use independently characterized path compensation, preserve all four input states in evaluation, and test gain imbalance, reference uncertainty, drift and noise. Do not demand a stable phase angle at a near-zero response.

The practical lesson is to select a statistic for the declared relation rather than maximize variance, resonance count, concurrence or a single mean-separation score.

## 6. FT-2 addition: select and freeze candidate statistics

Before opening the held-out session:

1. Declare the target F(X), allowed input encoding, class distribution, operating envelope and physical query budget. Freeze the task rather than choosing whichever relation fits the test data.
2. Specify the full-observation baseline, a modest candidate receiver set, minimum acceptable task performance, allowable performance loss and claimed resource benefit. Include class-specific error limits where false positives and negatives have different costs.
3. Select features, covariance regularization, normalization, weighting, quantization and decision thresholds using training sessions or nested training folds only. Keep entire test sessions separate; use held input combinations as an additional test, not a replacement for session holdout.
4. Compare full complex features, selected features, a linear score where justified, and relation-appropriate magnitude/envelope scores. A fixed-size candidate set limits post-hoc selection.
5. Report paired held-session performance of each frozen candidate. Confidence intervals must respect repeated captures within blocks/sessions; FFT bins, overlapping windows and averages are not independent replications.

An offline candidate is promising when its performance is noninferior to the qualified full-observation decoder within a preregistered margin, while also meeting an absolute task requirement. The full-observation decoder is an empirical baseline, not a proven Bayes-optimal upper bound. Record an apparent reduced-model improvement as such; finite-sample regularization can improve a fitted classifier without creating information.

## 7. FT-4/FT-5 addition: test actual receiver replacement

Separate these implementations in every report:

| Implementation | What was physically obtained | Permitted conclusion |
| --- | --- | --- |
| Full digital baseline | Full raw observation and conventional decoder | Reference task performance and cost |
| Offline compression | Full observation, then software statistic | Candidate statistic; no acquisition saving |
| Hardware-constrained simulation | Model with measured kernel/noise/drift | Simulated feasibility only |
| Physical reduced receiver | Measured output of the actual smaller signal chain | Hardware task/cost claim if controls pass |

For the physical reduced receiver, repeat matched queries under the same external input conditions and a declared reference policy. Randomize/interleave implementation comparisons where possible, or disclose when measurements are sequential rather than paired. Evaluate a complete later session without retuning. Document loading changes when laboratory probes are added or removed.

Count encoding, drive, transduction, reference generation, settling, all acquisitions/averaging, analog weighting/detection, ADC precision, digital operations, calibration and idle power. Record which measurements require the laboratory scope for validation versus which would be required at inference. Do not remove their cost by assertion. Compare with conventional analog filtering/summing and an efficient digital implementation given the same task inputs; source-only success is allowed.

Use the existing FT-M distinction between acoustic attribution controls and task/cost baselines. Do not claim attribution merely because a glass-trained threshold fails on a differently scaled electrical path. A noninferior task score with lower measured cost is the objective, not a higher KL estimate by itself.

## 8. Metrics and optional divergence diagnostics

Primary: confusion counts, balanced accuracy, false-positive/negative rates, abstention and coverage, per-session results, uncertainty, latency and measured resource costs. Evaluate every frozen candidate on the same eligible test population. Treat abstention consistently; do not improve accuracy by silently dropping hard trials.

For balanced accuracy, define the paired difference Delta=BA_reduced-BA_full. Before testing, choose the noninferiority margin m and confidence procedure. Require the lower confidence bound for Delta to exceed -m, the reduced receiver to meet the separate absolute task target, and the preregistered cost-benefit criterion to pass. Fix sample size/stopping rules in advance. Insufficient precision gives INCONCLUSIVE, not acceptance. Generalization across days requires multiple independent sessions; many captures from one day do not establish it.

KL or likelihood diagnostics are optional. Declare distribution assumptions, estimation method, direction and units; fit density models on training data and validate them. Do not use unstable high-dimensional density estimates as evidence of capacity. A held-out log-likelihood-ratio average computed with fitted densities is an estimated diagnostic, not the exact population KL divergence.

Only for a justified common observation chain with finite positive denominator may one report:

$$\eta_{KL}=D_{KL}(P^Z_1\|P^Z_0)/D_{KL}(P^Y_1\|P^Y_0).$$

At the population level this ratio is at most one under the conditions in Section 3. Do not use it when the denominator is zero, near zero or poorly estimated; report uncertainty and model checks. Values above one from estimates prompt an estimation/model/chain audit, not a claim of information creation. It is neither K_eff nor a universal measure of retained meaning. A task can meet its decision requirements without preserving all of its input's KL divergence.

## 9. Records to retain

Alongside the FT-M manifest, save a `readout_retention.json` record with:

- task and input-distribution IDs; source commit, raw-data hashes and physical/synthetic provenance;
- device/topology, train/validation/test session IDs, held-input-combination IDs and actual pairing scheme;
- frozen full and reduced decoder/statistic definitions and hashes; candidate-selection policy and model assumptions;
- implementation kind: `full_digital`, `offline_compression`, `hardware_constrained_simulation` or `physical_reduced`;
- scalar/feature count separately from ADC precision, reference channels, sample count and averaging;
- class confusion counts, abstentions, coverage and per-session uncertainty;
- preregistered noninferiority margin, absolute task threshold, sample/stopping plan and cost criterion;
- measured versus projected resource values, unmeasured fields as null, and increased costs alongside savings;
- optional divergence diagnostics with direction, log base, estimator, uncertainty and applicability checks.

This record is a protocol specification, not an implemented or validated schema/analyzer. No existing frontier-tool flag certifies these requirements. Retention conclusions must remain separate from K_eff fields so one good scalar decision is not relabeled as many independent dimensions.

## 10. Interpretation and immediate scope

- **Promising offline candidate:** frozen reduced statistic retains held-session performance; hardware cost advantage remains untested.
- **Qualified physical retention:** actual reduced receiver preserves required task performance under FT-M controls; comparative benefit still separately assessed.
- **GREEN-B:** physical retention plus the preregistered measured task/cost benefit over fair alternatives. This does not imply new physics, quantum advantage or novelty.
- **INCONCLUSIVE:** missing references, raw data, valid splits, confidence or cost measurements.
- **Negative result for this receiver/task:** a qualified test shows unacceptable loss or no specified cost benefit. This does not reject all acoustic computing.

Use existing per-trial datasets only to shortlist statistics when provenance allows. Do not infer historical phase, reference signals or later sessions that were never saved. This addition does not alter old data, patent documents, website claims, firmware or existing result labels, and does not authorize a gravity/quantum-hardware experiment. No bench data were reanalyzed in preparing it.

## References and citation roles

**[R1] Conceptual motivation only.** P. Dorau and A. Much, Physical Review Letters 136, 091602 (2026), [DOI 10.1103/lmq8-nsty](https://doi.org/10.1103/lmq8-nsty). [Accessible v3](https://arxiv.org/html/2510.24491v3). Supports the description of the theoretical gravity paper, not CWM performance or the receiver derivations.

**[R2] Applicable information-theory reference.** Y. Polyanskiy and Y. Wu, "Strong Data-Processing Inequalities for Channels and Bayesian Networks," in Convexity and Concentration, IMA Volumes in Mathematics and its Applications 161, 211-249 (2017), [DOI 10.1007/978-1-4939-7005-6_7](https://doi.org/10.1007/978-1-4939-7005-6_7). [Author preprint v4](https://arxiv.org/html/1508.06025v4), dated 2016-07-28; [MIT publication record](https://dspace.mit.edu/entities/publication/47c8e0bc-4dff-436f-a2f4-e091e5095bf4). In particular, Section 2.1 treats divergence and mutual-information contraction. This is established classical theory, not a CWM novelty claim.

**[R3] Model assumptions and detection baseline.** Stanford University, STATS 202, [Linear Discriminant Analysis](https://web.stanford.edu/class/stats202/notes/Classification/LDA.html), institutional course notes, accessed 2026-10-13. Supports Gaussian/common-covariance classification and the linear discriminant. The equality and phase counterexample in Sections 4-5 are worked algebra under their explicitly stated assumptions, not measured CWM results.
