Deep Peer Review of the Coherent Wave Memory Manuscript
Evidentiary basis and executive conclusion
This assessment is grounded in the claim set supplied in the request and in the public CWM repository artifacts available for inspection: multiple paper drafts (v18, cwm_core, cwm_advanced), a public rewrite memorandum for a future v19, and result directories covering plate census, Q-factor, discrimination, multilevel encoding, reservoir classification, ringdown stability, temporal memory, quantum-bridge analysis, and lab nearest-neighbor and associative-recall runs.

My bottom-line judgment is that the manuscript, as described, would not survive a hard peer review at any of the ambitious target venues, and would still be very vulnerable even at lower-tier physics or applied-instrumentation journals. The central reason is not that the core idea is obviously impossible. It is that the evidentiary chain is too weak, too internally inconsistent, and too rhetorically overextended for the claims being made. The repository itself acknowledges a dominant signal-path confound on the bench, an “INCONCLUSIVE” phase-inclusive non-separability/tomography result, a failed temporal reservoir benchmark on actual hardware, and the need to relabel at least one headline SNR number from “measured” to “derived thermodynamic ceiling.”

A narrow paper on stable spectral fingerprinting in piezo-read glass resonators under explicitly quantified electrical feedthrough could eventually become publishable. The present manuscript sounds like it is trying to publish, all at once, an acoustic memory paper, a physical-computing paper, a classical-nonseparability paper, and a MEMS roadmap. In its current form, that breadth is a liability, not a strength.

Fatal issues and likely reviewer objections
Signal-path attribution
Fatal issue. The largest single threat to publication is the bench-path confound. The repo’s own rewrite instructions say the May 26 hardware campaign established a signal path that was about 88% electrical feedthrough and 12% acoustic in the shared-PZT breadboard topology, and it explicitly says that this confound must be disclosed wherever recall, Boolean, and encoding results are discussed. The same memo says temporal-memory results do not survive this confound and should be disclosed as failures that quantify a coupling limit, not as architecture successes.

A skeptical reviewer will immediately ask whether the reported spectral fingerprints are primarily properties of the glass resonator or of the wiring, switching, electronics, and shared transduction path. If the answer is “some of both,” then the paper must quantitatively decompose them and prove that its headline results survive the decomposition. If that decomposition is not centered in the main text, this is a desk-rejection risk.

A realistic objection would read like this: “The authors have not demonstrated that the reported classification and recall behavior arises predominantly from acoustic storage or acoustic mode physics, rather than direct electrical cross-talk and instrumentation artifacts. Without a convincing signal-path decomposition, the central memory claim remains unestablished.”

CHSH and non-separability
Fatal issue. The CHSH/concurrence material is the second-largest rejection trigger. The public t5_2_chsh_optimal_pair result uses a mode-pair selection method explicitly labeled frequency_sweep_max_contrast, then reports S_optimal = 2.827380287..., S_theory_max = 2.827380287..., and a bootstrap sigma_above_2 of about 231,303, which is a giant red flag rather than a badge of rigor. That statistic is so large that it almost advertises non-independence, over-conditioning, or deterministic resampling of a fitted object rather than uncertainty on a physically repeated Bell-style test.

The deeper problem is that the repo’s own phase-inclusive tomography result is not clean. In e2_complex_tomography, the magnitude-only reconstruction gives near-unity concurrence and S_optimal ≈ 2.827, but the complex reconstruction gives concurrence ≈ 0.924 with a very wide 95% CI, S_optimal ≈ 2.303 with a CI spanning values well below 2, flags phase_stable: false, and ends with verdict: "INCONCLUSIVE". A hard reviewer will not let the manuscript foreground the magnitude-only near-Tsirelson number while relegating the phase-inclusive failure to a caveat.

The classical-optics literature does support a narrow and defensible claim that local degrees of freedom of a single classical field can be non-separable in a way that is formally analogous to entanglement. Spreeuw’s 1998 paper drew that boundary explicitly; Qian and Eberly framed classical polarization states in entanglement language; and Kagalwala and coauthors used Bell-type measures in classical optical coherence as a resource/structure diagnostic rather than as quantum nonlocality. But all of that literature cuts against overclaiming. It supports a careful classical non-separability interpretation, not a headline-grabbing Bell-violation narrative about a glass plate.

A realistic reviewer objection would be: “The manuscript fails to establish a robust phase-resolved non-separability result in the acoustic domain. The CHSH-like statistic is presented on an optimized mode pair and appears to be derived from a fitted state representation with essentially vanishing bootstrap uncertainty; meanwhile the phase-inclusive reconstruction is explicitly inconclusive. This is not publication-quality evidence for the claimed physical phenomenon.”

Where the computation actually is
Fatal issue. Much of the manuscript appears to blur together three very different things: a physical front-end that generates a spectrum, a digital decoder that classifies that spectrum, and a simulated architecture study. That blur will not survive review.

The clearest example is Boolean computation. The public exp08_boolean_compute.py is explicitly marked SIMULATED, and its own docstring says the claim tested there is only a computational validation of thresholded superposition logic. The bench Boolean result file is not a direct in-material AND/OR/XOR demonstration on arbitrary superposed states; it is a classification result over 16 enrolled 4-bit patterns. Its perfect scores come from raw_diag and log_diag, while broader cross-mode methods fall to the 64–82.5% range. That means the success depends strongly on a particular decoder choice, and the “computation” is at least partly in the post-processing.

The same issue appears in associative recall and nearest-neighbor search. The public exp06_associative_recall.py and exp07_nearest_neighbor.py are also explicitly labeled SIMULATED, and both are framed as spectral-correlation engines over stored fingerprints. The lab nearest-neighbor JSON then shows a software score table, a winner, a true_nearest, and a correctness decision. That is an enrollment-and-scoring pipeline with a physical front-end, not an unambiguous demonstration that the physical object itself is performing a content-addressable computation in the strong sense likely implied by the manuscript.

The reservoir claim is even weaker on bench hardware. The t3_3_reservoir result shows perfect static four-class classification using amplitude-only features and a trainable readout, but the actual temporal NARMA10 probes t3_3b and t3_3c are both marked FAIL; in one case the best NRMSE is worse than the input baselines, and in the other the file explicitly states has_memory: false. A reservoir-computing reviewer will view that as dispositive.

A realistic reviewer objection would be: “The manuscript does not demonstrate physical computation in the strong sense claimed. What is shown is primarily spectral feature generation followed by digital enrollment, thresholding, correlation scoring, and linear classification. The temporal benchmark that would actually support a reservoir-computing claim fails on hardware.”

Provenance and labeling
Major to fatal issue. The manuscript is highly vulnerable on provenance and labeling discipline. The rewrite memo states, in unusually blunt language, that v19 must never let a derived or projected quantity wear the word “measured,” and it specifically identifies the 98.5 dB SNR as a thermodynamic bound rather than an instrument reading. The same memo says the real bench SNR is 42–55 dB on plate hardware and 34 dB mean / 75 dB max on the rod bench. It also says the previously cited Q = 10,000 macro-prototype value was a material-Q reference, not a bench measurement, and that the measured plate Q was 2,759 in the cited campaign.

That warning matters because the public artifacts already show provenance ambiguity. The inspected plate census file reports 7 detected modes, not 27, and the public t1_1_qfactor output reports fitted_Q ≈ 2275 with a very low r_squared ≈ 0.077. The gap between “intrinsic Q,” “loaded Q,” and “bench-measured fitted Q” is not yet handled with the precision a reviewer would require. If the manuscript claims 27 resolvable modes with loaded Q of 152–241 and intrinsic Q of about 2759, it must provide a transparent mapping from each number to its exact dataset, fitting model, and loading condition.

A realistic reviewer objection would be: “The manuscript repeatedly crosses the boundary between measured, derived, modeled, and projected quantities. The result is a numerically impressive but evidentially unstable narrative. The authors must provide a rigorous provenance table for every headline number.”

Stability and retention claims
Major issue. The endurance/stability story is publishable only if stated precisely. The public t4_2_ringdown result spans 137.5 minutes of monitoring and 16.5 million cycles, but it reports an average fitted half-life of about 25.6 minutes and a maximum half-life of about 53 minutes. That supports a statement about multi-session or multi-hour operational monitoring, but not a strong statement about multi-hour passive retention unless the manuscript distinguishes re-excitation endurance from stored-state persistence. Reviewers will notice that distinction.

A realistic reviewer objection would be: “The endurance data are useful, but the manuscript appears to conflate monitoring duration, cycle endurance, and passive memory retention. Those are different quantities and must not be merged rhetorically.”

Panel-specific objections
Panel role Likely objection Severity
Nature Physics reviewer “The only potentially high-concept physics claim is classical non-separability, but the phase-complete evidence is inconclusive and conceptually downstream of established classical-optics literature.” Fatal
Physical Review Letters reviewer “There is no single sharp result here. The manuscript bundles confounded experiments, speculative scaling, and a fragile CHSH narrative into one overfull package.” Fatal
Nature Electronics reviewer “This is not an electronics paper in its current form. There is no integrated device, no credible system benchmark, and no demonstrated electronics-compatible implementation.” Fatal
MEMS fabrication specialist “The MEMS section is a roadmap, not evidence. Packaging, anchor loss, process variation, thermal drift, and cross-talk are all hand-waved.” Major
Nonlinear dynamics reviewer “Most of the demonstrated computation appears to ride on linear spectral separation and digital decoding. Where is the experimentally verified useful nonlinearity?” Major
Reservoir computing expert “Static four-class separation is not reservoir computing. The temporal benchmark fails, and the hardware even reports no memory in a key probe.” Fatal
Statistical methods reviewer “The paper inflates certainty with repeated measures, tuned feature sets, optimized mode pairs, and near-deterministic bootstraps.” Fatal
Scientific editor “The manuscript is not yet editorially coherent. It contains multiple publishable fragments, but the present aggregate is too risky to send out without heavy triage.” Fatal

Statistical audit
Independence and confidence
The manuscript’s repeated 100% numbers will attract skepticism, not admiration, unless the statistical design is made watertight. In plate_discrim, the public file shows 4 modes, 20 trials per class, and a perfect 80/80 confusion matrix. That is enough to show the states are strongly separable under that exact protocol, but it is not enough to establish robust generalization, because the observations are repeated measures from the same device, same enrolled classes, same environment, and apparently the same measurement session. A naïve binomial interval would look impressive, but the effective sample size is almost certainly much smaller than 80 because the measurements are not independent draws from a changing population.

The boolean results show another statistical fragility. The bench file covers 16 patterns with 10 repetitions, and the perfect result depends on choosing raw_diag or log_diag; several other reasonable feature pipelines land dramatically lower, including template residual and full cross-mode variants in the mid-60s to low-80s percent. That is not a catastrophic result, but it means the manuscript cannot honestly compress the analysis to “100% Boolean logic.” It has to say “100% under a specific decoder choice that effectively exploits diagonal feature dominance.”

The multilevel results are likewise more brittle than a headline claim suggests. The public file shows perfect amplitude-only per-mode discrimination at 8 levels, but amplitude-plus-phase performance collapses to roughly 24–25%, and the phase_b block reports 0.00625 accuracy over 256 patterns and 1,280 observations. That is not a small caveat. It means the architecture is not robustly exploiting phase as an additional clean information-bearing degree of freedom in the current implementation. Any capacity claim that multiplies levels across modes must therefore be treated carefully, because the independence assumption is doing a great deal of work.

Selection effects and inflated significance
The most inflated significance claim in the entire manuscript is the CHSH story. The public file shows that the reported result comes from an optimized pair selected by a max-contrast sweep, then assigns a bootstrap sigma_above_2 of more than 231,000 with a microscopic standard deviation on S. That is not believable as a meaningful uncertainty estimate on a physical witness. It reflects a resampling distribution over an already-fit and highly conditioned object, not the true uncertainty of a protocol that ought to be sensitive to drift, calibration, basis choice, and mode-pair selection.

The tomography file makes the fragility even clearer. The magnitude-only result looks nearly perfect, but the complex result has wide confidence intervals, a negative-to-neutral bootstrap comparison interval on the concurrence difference, and phase_stable: false. This is exactly the kind of discrepancy that a methods reviewer would describe as a garden of forking paths: one can choose magnitude-only versus complex reconstruction, optimized angles versus fixed settings, selected mode pair versus broad panel, and then report the best-looking statistic.

I would therefore flag the manuscript for inflated significance claims, selection bias, repeated-measure dependence, and decoder/feature-set multiplicity. Reviewers may not accuse the authors of p-hacking in those words, but they will almost certainly say that the uncertainty quantification is not commensurate with the rhetoric.

Statistical judgment
The statistics are good enough to support a narrow statement that some bench protocols produce highly separable and repeatable spectral classes. They are not good enough to support broad claims of general-purpose acoustic computation, high-confidence CHSH-style non-separability, or system-level capacity. In publication terms, the statistical layer is presently questionable to inadequate, depending on which claim is being evaluated.

Physics audit
Resonator and modal physics
The basic resonator physics is the strongest part of the manuscript. It is entirely plausible that a fused-silica plate driven and read piezoelectrically will exhibit reproducible resonant structure and that perturbations or spatial readout choices will generate distinct spectral fingerprints. The public repo does show real resonant features, real Q estimates, and stable class separation. That core physical premise is not pseudoscientific.

What is not yet publication-ready is the metrology discipline around that premise. Publicly visible artifacts point to at least three different Q narratives: a public fitted value around 2275 with poor fit quality, a rewrite memo stating the plate campaign measured 2759, and earlier manuscript language that apparently used 10,000 as a macro reference even though the memo now says that was not a bench measurement at all. That kind of slippage is survivable in a lab notebook and fatal in a paper.

Thermodynamic and scaling arguments
On the physics, the thermodynamic arguments are not obviously wrong, but they are at extreme risk of being misused. The rewrite memo correctly says the 98.5 dB SNR figure is a thermodynamic bound, not a measurement, and that real plate measurements were much lower. That is exactly how such quantities should be handled: as ceilings, not accomplishments. The problem is that once those ceilings are fed into Shannon estimates, density estimates, and energy-per-operation projections, the manuscript begins to read like a performance paper even though the relevant numbers are not yet performance measurements.

So the right judgment is this: the thermodynamic and scaling arguments are plausible as upper-bound theory, correct only if labeled derived/projected, and incorrect if rhetorically merged with the bench data.

Non-separability formalism
The underlying formalism is not nonsense. Classical non-separability between local degrees of freedom is well established in optics, and Bell-type figures of merit have been used there as diagnostics of local structure or coherence, not as evidence of quantum nonlocality. On that narrow point, the manuscript is standing on legitimate conceptual ground.

But a reviewer will separate formal legitimacy from experimental adequacy. Here, the formalism is legitimate, while the implementation remains weak: optimized pair selection, magnitude-only success, phase-inclusive inconclusiveness, and unstable phase are all severe problems. So my judgment is:

Resonator and modal-encoding physics: plausible
Thermodynamic noise ceilings as theory: correct if explicitly derived
Acoustic CHSH-like non-separability witness on current data: questionable
Any implication of Bell violation, Tsirelson-style significance, or quantum-adjacent interpretation: incorrect
Physics judgment
If the manuscript were judged only on whether a glass plate can host stable resonant fingerprints and whether those fingerprints can be exploited as a measurement basis, the physics would likely pass. If it is judged on whether it has cleanly demonstrated an acoustic analogue of classical entanglement with computational significance, the answer is no on current evidence. The physics is therefore mixed: the substrate physics is credible; the claimed higher-order implications are not yet.

Computation and MEMS audit
Computation audit
The actual computation, in the present evidence base, occurs mostly in the digital pipeline after spectral capture. The hardware contributes a physical projection into a frequency-space feature domain. The decisive steps are then FFT extraction, enrollment, template/correlation scoring, threshold selection, and supervised readout.

That is clearest in the Boolean and nearest-neighbor results. The bench Boolean file shows that perfect performance comes from diagonal-feature methods, not the more global cross-mode decoders; the nearest-neighbor machinery explicitly uses correlation scores, winners, and true-distance comparisons; and the top-level associative-recall and nearest-neighbor experiment scripts are marked SIMULATED and cast the task as spectral correlation against stored fingerprints. This is much closer to signal classification / lookup / content-addressable scoring than to autonomous, materially embedded computation.

The reservoir case is even more decisive. Physical reservoir computing is generally understood to require a nonlinear dynamical system with useful fading memory and a trainable readout. The tutorial literature emphasizes that distinction, and existing mechanical/MEMS reservoir demonstrations clear it by solving genuine temporal tasks. In CWM, the public hardware does not. Static classification succeeds; temporal NARMA probes fail; and one file says has_memory: false. A reservoir-computing expert will therefore conclude that the current bench behaves as a feature extractor, not as a validated reservoir computer.

My computation judgment is therefore:

Actual computation demonstrated: limited, task-specific, decoder-assisted
Signal classification demonstrated: yes
Post-processing classification: yes, unequivocally
Lookup/content-addressable behavior: partially, but heavily software-mediated
Physical computing in the strong sense: not yet established
MEMS audit
The MEMS roadmap is the weakest technically mature part of the package. Not because high-Q MEMS piezo resonators are impossible — they are not. Current literature shows that thin-film piezo-on-silicon resonators can achieve very high anchor-Q with aggressive phononic-crystal engineering, and entirely separate groups have already demonstrated mechanical physical reservoir computing in MEMS or drum-resonator systems. The field bar is real.

But that prior art cuts both ways. It proves that the field knows how hard these devices are. Anchor loss, packaging, electrode parasitics, vacuum level, transduction strength, process spread, frequency matching, thermal coefficients, and cross-talk are the real story. The CWM manuscript, as described, appears to treat these as downstream engineering details that will be solved by scaling, even though the macro bench still has a dominant electrical-feedthrough problem. That is not a fabrication argument. It is an aspiration. The repo’s own memo effectively says as much when it frames MEMS as the place where coupling engineering might eventually be fixed.

My MEMS judgment is therefore:

Fabrication assumptions: incomplete
Q-factor budget: partly plausible, insufficiently demonstrated
Manufacturability: speculative
Packaging assumptions: weak
Thermal assumptions: weak to absent
Projected performance: highly speculative
Literature and prior-art audit
The manuscript needs a much tighter literature spine. At minimum, it should explicitly cite the classical non-separability literature that defines the conceptual boundary it is trying to inhabit: Spreeuw (1998) on classical analogies of entanglement; Qian and Eberly (2011) on classical polarization states in entanglement language; Kagalwala et al. on Bell-type measures in classical optical coherence; and later review/conference literature on classical entanglement theory and applications. Without those citations, the acoustic CHSH section will look either unaware or evasive.

It also needs stronger context on physical reservoir computing. A skeptical reviewer will know that mechanical reservoir computing is already an established research track, including delay-coupled nonlinear electromechanical MEMS and more recent coupled drum-resonator platforms, along with tutorials that carefully define what it means for a physical system to “compute” rather than merely evolve and then be decoded digitally. That literature raises the bar for CWM; it does not lower it.

The same is true for the MEMS projection. If the manuscript headlines a modeled MEMS Q of about 9,097 as though that were the difficult part, MEMS reviewers will push back. The hard part is not writing down a plausible Q. It is showing the complete package — mode design, anchor-loss management, parasitic control, packaging, thermal stability, readout SNR, and reproducibility — on a fabricated device. The current literature on thin-film piezo resonators and anchor-loss suppression needs to be cited precisely because it demonstrates how much engineering sits between a macro glass plate and a publishable MEMS platform.

The strongest prior demonstrations are therefore cleaner than this manuscript in the very domains it wants to claim: classical non-separability has deeper and more mature experimental foundations in optics, and mechanical reservoir computing already has sharper task-level demonstrations in MEMS. That means the novelty here is narrower than the manuscript likely suggests. The strongest novelty is not “entanglement-like computation” or “first mechanical reservoir.” It is the specific use of glass-resonator spectral fingerprints as a computing-and-memory substrate. That is novel enough to be interesting. It is not novel enough to justify overclaiming.

One more literature risk is self-inflicted. The repo’s own rewrite memo warns that a companion book should not be cited as scientific evidence and that sensational narrative elements must be kept out of the paper. That is correct editorial advice. If the manuscript leans on that material, reviewers will interpret it as a credibility problem, not flavor text.

Publication risk and editorial disposition
Publication risk matrix
Issue Severity Probability reviewer notices Probability of rejection
Signal-path confound not centered Fatal 95% 90%
CHSH / concurrence overinterpretation Fatal 95% 90%
Software decoding presented as physical computation Fatal 90% 85%
Reservoir claim contradicted by failed temporal hardware tests Fatal 90% 85%
Measured / derived / projected numbers mixed together Fatal 85% 80%
Mode-count and Q provenance ambiguity Major 80% 65%
Statistical inflation and non-independence Major 90% 75%
MEMS performance projections not experimentally grounded Major 85% 70%
Stability language stronger than retention evidence Major 70% 50%
Manuscript scope too broad for evidence quality Fatal 95% 90%

Journal suitability
Journal Estimate Why
Physical Review Letters Reject No single sharply validated result; too many speculative branches; fatal evidence issues
Physical Review Applied Reject Device/application claim not yet anchored by causal proof or credible system benchmark
Applied Physics Letters Reject Could become an APL-style short result if radically narrowed, but not in current form
Nature Physics Reject Conceptual overreach, weak phase-complete evidence, and no clear new fundamental physics
Nature Electronics Reject No integrated MEMS/electronics platform, no competitive benchmark, no fabrication result
Microsystems & Nanoengineering Reject MEMS device not built; section reads as roadmap rather than nano/microfabrication paper
Journal of Applied Physics Major Revision Only if reduced to conservative resonator-physics and spectral-fingerprint claims
Scientific Reports Major Revision Only if CHSH, MEMS, and broad computing claims are removed and confounds are foregrounded

Manuscript triage
The manuscript’s strongest publishable claim is not “wave-based general-purpose computing,” “classical entanglement in glass,” or “MEMS-scale competitive architecture.” It is far more modest:

A piezo-driven fused-silica resonator exhibits stable, highly separable spectral fingerprints that can support enrollment-based classification and retrieval under controlled protocols, with a quantified but serious electrical-feedthrough confound on the current breadboard platform.

The weakest claim is the CHSH/concurrence package as a headline result. The accessible public evidence simply does not support that claim at publication quality, because the phase-inclusive reconstruction is inconclusive and the statistics are visibly over-conditioned.

The claims that should be removed from the main text are:

any Bell-adjacent or Tsirelson-adjacent rhetoric beyond a very cautious classical non-separability note,
any implication that benchmark reservoir computing has been demonstrated on hardware,
any broad comparison to mainstream digital memory density or energy unless every number is explicitly marked projected/modeled,
any phrase suggesting that Boolean logic is demonstrated “in the resonator” rather than in a resonator-plus-decoder system.
The claims that should be pushed to supplementary material are the Shannon-capacity ceilings, thermodynamic SNR bounds, MEMS density projections, and most of the architecture-roadmap material. Those are useful, but right now they dilute rather than strengthen the empirical story.

The most sensible restructuring is to split the work into three separate papers:

Experimental resonator paper: spectral fingerprints, Q reporting, confound decomposition, repeatability, and a very conservative classification result.
Classical non-separability note: only after phase-stable complex tomography exists and only with explicitly anti-quantum-overclaim framing.
Modeled MEMS architecture paper: device design, anchor-loss budgeting, packaging assumptions, and projected operating regime — clearly marked as modeled/projected.
Trying to publish all three stories in one manuscript is presently making all three weaker.

Final verdict
Metric Score
Scientific Credibility Score 38
Experimental Rigor Score 30
Publication Readiness Score 16
Novelty Score 61
Risk of Reviewer Rejection 94

Final recommendation: Not Publishable

The justification is straightforward. The manuscript’s core experimental platform is not obviously unphysical, and some of the measured separability results are genuinely interesting. But the paper, as described, does not clear the publication bar because its strongest claims are exactly the ones with the weakest evidentiary footing. The signal path is dominantly electrical on the current bench; the CHSH/concurrence narrative collapses under phase-inclusive scrutiny; the hardware reservoir claim is contradicted by failed temporal tests; and the repository itself acknowledges that several headline quantities need to be relabeled from measured to derived or projected. That combination is precisely what causes skeptical referees to recommend rejection.

If a scientific editor sent this manuscript out unchanged, I would expect at least two fatal reviews and one review recommending total reframing. In other words: the work may contain a publishable nucleus, but this manuscript, in its current claimed form, would very likely not survive peer review.
