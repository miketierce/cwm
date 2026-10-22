**Rhythm and transient observability — proposed CWM experiment**

September 20, 2026. Status: OPEN experiment design. No new hardware measurements. Starting assumption: a trustworthy direct acoustic decay time has not been established in the reviewed record. This protocol must not depend on one.

**Question.** Can controlled pulse timing produce a reproducible acoustic response that distinguishes recent input histories? First establish which transients the apparatus can observe. Then distinguish a driven rhythm response, residual physical state, ordinary linear filtering, and any departure requiring further investigation.

The motivation is the audible rhythm of a periodically excited fan. That observation does not identify its mechanism or establish anything about CWM. Overlapping tones and linear interference are possible; useful nonlinear mode interaction remains a separate question. A rhythm result need not be nonlinear to be useful.

**What the existing record actually says.** Review anchor: main `c6f08ff95b03438c8f99b43086f86ebc1cf54c68`.

| Record | Observation | Consequence for this experiment |
| --- | --- | --- |
| [April 13 pulsed tests](LAB_DIARY.md#2026-04-13--pulsed-ringdown--cross-plate-routing) | Post-drive readout did not recover a reliable pattern signal. Drive loading/switching was suspected, not isolated as a proven cause. | A null does not establish zero mechanical decay time. |
| [v19r section 4.2](../paper/v19r.md#42-q-factor) | Three nominally successful ringdown fits have R² of 0.038–0.077. The paper acknowledges unreliable estimates. | Do not choose timing from their fitted Q or decay values. |
| [June 3 direct E10 output](../data/results/temporal/e10_ringdown_memory_20260603_195359.json) | Output says PASS, but all reported per-mode R² values are below 0.02. Nominal decay times extend far beyond the roughly 40.6 ms capture duration. | The success label is not evidence of a validated decay measurement. |
| [June 3 bandwidth E10 output](../data/results/temporal/e10_qfactor_memory_20260603_200902.json) | The method is frequency-domain bandwidth; decay values are computed from Q and frequency. | These are model-derived estimates, not directly observed decay curves. |
| [Current E10 implementation](../tools/e10_ringdown_memory.py) | Despite its filename, the current script measures frequency-domain bandwidth and explicitly avoids serial-latency-limited ringdown capture. | Identify method and revision, not just the filename. |
| [June 2 gap-encoded ring-up](../data/results/narma10_ringup/narma10_ringup_20260602_223135.json) | Variable requested gaps were already tested. The sequence benchmark failed; this was not a successful clean rhythm-memory demonstration. | This proposal refines an existing temporal direction rather than claiming a wholly untouched idea. |

The usual isolated, lightly damped linear-mode relation is amplitude-envelope time constant τA = Q/(πf0). An energy-envelope constant is half that value. A bandwidth estimate relies on its model and loading conditions; it does not establish the free response after switching into a different electrical termination. A sum of modal time constants is not a demonstrated information capacity.

**Stage 0 — recover and characterize the measurement path.**

- Confirm the present RX-board condition. The [June 30 incident](lab_diary_20260630.md) records overheating and disconnection; inspect and resolve that fault before repowering if no subsequent repair has occurred.
- Select one plate, one TX, one RX, and fixed mounting. Save a wiring diagram, supply settings, drive amplitude, receiver gain, input impedance, firmware, and acquisition settings. Avoid receiver mux switching during a trial.
- Generate the complete burst sequence in deterministic hardware or a preloaded waveform. Host USB commands can arm/run a trial but must not schedule individual short gaps.
- Record the actual drive waveform at the TX terminals, or a characterized electrical monitor, together with the receiver. Use a common clock/trigger or measure their relative timing. An NCO command acknowledgement is not evidence of when physical excitation stopped.
- Capture continuously across the final drive edge with pretrigger samples. Verify actual sample rate, analog bandwidth, clipping, timing jitter, switch transient, recovery/blanking interval, and any gaps between blocks. A high nominal sample rate does not eliminate an unrecorded interval.
- Specify the off-state: zero output with connected source, high impedance, or another termination. They are different experiments. Do not interchange them between calibration and rhythm trials.

Deliverable: a timing trace showing the last electrical drive edge and the earliest trustworthy RX sample, plus baseline noise and electrical recovery traces. If the current setup cannot provide this, stop the post-drive claim and document the minimum acquisition/trigger change needed. Hardware availability is unverified; this is a capability requirement, not a shopping list.

**Stage 1 — detect a post-drive response without assuming τ.**

1. Select a driven response from a fresh sweep. Apply one short, reproducible tone burst with recorded carrier phase and envelope. Capture before, during, and after excitation. Explore burst duration in a pilot without using final evaluation data.
2. Acquire matched controls: no excitation; an electrical dummy/reference with documented impedance limitations; and a mechanical-coupling change while retaining wiring as closely as practical. No single control perfectly preserves every electrical condition. Look for convergent evidence, and restore/repeat the original configuration.
3. Compare receiver traces after the *observed* final drive edge and after the established electronic recovery interval. Repeat at two non-clipping amplitudes and in independent acquisition blocks. Record terminal drive after nominal shutoff to detect residual excitation.
4. Inspect raw waveforms before fitting. A bandpass, lock-in, or smoothing filter can manufacture an apparent tail. Apply the identical processing to controls and characterize filter impulse response. Avoid acausal filtering across the drive-off edge for the primary detection claim.
5. Start with post-edge windows supported by the actual apparatus, not multiples of an assumed decay time. A possible exploratory set spans tens of microseconds through tens of milliseconds; only include windows with adequate carrier sampling, validated bandwidth, and known recovery. Record which early intervals are unobservable. Extend capture if a response persists at the end.

Before final data collection, use separate pilot/control data to fix a detection statistic, analysis bands/windows, and false-positive threshold. Account for searching many frequencies and windows. A proposed discovery gate is a control-calibrated family-wise false-positive rate of at most 1%, reproduced in at least three independently restarted acquisition blocks and responsive to the mechanical control. This is an experimental design choice, not an established CWM performance claim.

Record one of these outcomes:

| Outcome | Permitted interpretation | Next step |
| --- | --- | --- |
| Timing/recovery obscures the relevant interval | Measurement is inconclusive | Improve observability; do not fit a decay constant |
| No response distinguishable from controls in the accessible interval | No detectable tail under these conditions and sensitivity | Report noise/detection limit and dead time; consider Stage 3B |
| Repeatable acoustically attributable tail, without a valid single exponential | A transient is observable; one τ is not established | Use the empirical waveform and a detection window |
| Repeatable tail with a supported decay model | Direct decay estimate for this mode/topology and stated model | Report uncertainty; use it to inform timing |

Non-detection alone does not give an upper bound on τ: the initial acoustic amplitude may be unknown or the signal may be masked. Any bound requires explicit amplitude, noise, recovery, and model assumptions. Never report τ = 0 merely because a fit failed.

**Stage 2 — characterize the tail only if detected.**

Separate narrowband modal envelopes when resolvable; distinguish beating from loss of energy. Fit an amplitude model with an appropriate noise/background treatment, specify units and fitting interval, inspect residuals, and compare plausible alternative models. Require informative amplitude change across the observed interval, bounded uncertainty, and stability to reasonable window changes. R² alone is not a pass criterion. Do not report a precise long lifetime from an almost flat, short record.

Save an empirical impulse/burst response even when an exponential fit is inappropriate. It can predict later linear responses without a single decay constant. Cross-check against independently measured bandwidth only for compatible loading and a justified modal model. Disagreement is diagnostic, not a reason to select the more attractive value.

**Stage 3A — test history in a shared quiet interval, if Stage 1 passes.**

Use four identical bursts and compare silent-gap orders:

| Pattern | Gaps between successive bursts |
| --- | --- |
| A | s, 3s, 2s |
| B | 3s, s, 2s |

Both have the same burst count, programmed energy, total duration, first/last burst times, and final gap. Their final two bursts occur at the same times; an earlier burst differs. Keep burst envelope and starting carrier phase controlled, and verify actual drive traces/energy. The primary decision window begins after the same final burst and validated receiver recovery. It must not include the differing earlier drive or data leaked by acausal filtering.

Choose s from validated timing resolution and the *observed transient support*, without requiring τ. Sweep from overlapping-response conditions to intervals where history should no longer be detectable. A slow-gap negative control must use an empirically adequate reset interval, not an assumed multiple of τ. Randomize trial order and check for carryover between trials.

Primary question: can the same fixed, simple decoder distinguish A and B from the shared quiet interval on held-out acquisition blocks and a later session? Split by independently acquired blocks/sessions before feature selection. Do not count adjacent frames as independent repetitions. Preregister trial count using pilot variance and a desired confidence interval; use balanced classes and report confidence intervals and a permutation test respecting experimental blocks.

Compare the full acoustic readout with a small readout, the electrical control, and a measured linear-system prediction. Charge for every reference channel used in normalization. Timing labels, filenames, acquisition order, or recorded pattern IDs must never enter decoder features.

**Stage 3B — driven rhythm response when a free tail remains unobservable.**

Rhythm can still be tested during excitation: apply periodic burst trains or amplitude modulation and compare reproducible responses at different rates and gap patterns. Capture actual input and RX simultaneously, compare with electrical controls, and vary/reset carrier phase deliberately rather than accidentally. Predefine a representation metric and test new sessions.

This tests driven temporal filtering or modulation sensitivity. Identifying a rhythm while its timing is present in the input is not evidence of retained information after excitation. A gap-dependent recovery transient is not automatically a free ringdown measurement. A useful driven effect can justify further work even if Stage 3A remains inaccessible, but its claim must stay at that level.

**Stage 4 — identify mechanism and practical value.**

Construct a linear prediction by summing appropriately shifted/scaled copies of the independently measured single-burst response. Validate the model on other amplitudes and timings, hold out the rhythm evaluation trials, and keep the measurement topology fixed. Include electronics/filter response in the accounting.

- Agreement supports ordinary linear temporal filtering. That may be useful, but does not establish nonlinear computation.
- A discrepancy first triggers checks for timing errors, residual drive, clipping, source loading, filter artifacts, and drift. It is not by itself proof of acoustic nonlinearity.
- Quiet-window classification that survives controls supports distinguishable recent histories in the measured system. It does not establish long-term storage or arbitrary sequence processing.
- Compare against direct electrical acquisition and a simple digital/analog filter at comparable task error and acquisition burden before claiming a physical advantage. A software decoder observing the entire input rhythm is an especially strong baseline; the plate does not gain credit merely for re-encoding an already known sequence.

**Required record for every stage.** Store raw simultaneous drive/RX traces, actual timestamps, sample/trigger metadata, clipping flags, termination and wiring, carrier phase/envelope, temperature/mounting notes, control type, session/block IDs, code/firmware revisions, processing settings, and all trials including failures. Separate requested timing from measured timing and direct measurements from derived values. Save an execution command and claim-to-output table with each result.

Advance from observability to rhythm only when the relevant gate passes. If the tail remains hidden, report that limitation and pursue only the explicitly driven experiment. Do not promote the existing weak decay fits or bandwidth-derived estimates to measured free-decay evidence in the grant narrative.
