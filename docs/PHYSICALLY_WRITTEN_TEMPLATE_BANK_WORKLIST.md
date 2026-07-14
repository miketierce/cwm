# Physically Written Template Bank Worklist

**Prepared:** July 13, 2026
**Purpose:** Carry the measured perturbation/mass-site mechanism through reversible programming, physical template matching, a multi-cell template bank, and a Wheel-style partial-query demonstration.
**Current status:** E3 measured position-dependent mass-loaded spectra. A repeatable write/erase/rewrite cell, physical match score, and multi-template bank remain OPEN.

**Related evidence and protocols:** [E3 comparison data](../data/results/lab/25mm_plate/e3/e3_comparison_analysis.json), [existing P8 protocol](WORKLIST.md), [Wheel-of-Fortune exploration](WHEEL_OF_FORTUNE_EXPLORATION.md), [June 30 readout fault](lab_diary_20260630.md), and [physical query-omission worklist](DISTRIBUTED_MODE_HARDWARE_VALIDATION_WORKLIST.md).

This worklist answers one narrow question:

> Can mass patterns physically program CWM resonators so that a partial query produces a larger or smaller fixed scalar match score in the compatible programmed cell than in incompatible cells?

The experiment must separate four effects that are easy to conflate:

```text
intrinsic plate identity
mass-pattern identity
query identity
software decoder behavior
```

The first three are physical. The fourth may select a winner, but it must not create the match after the fact.

---

## 1. Evidence and Claim Boundary

### 1.1 What is already measured

The June 5 E3 run on the 25 mm fused-silica plate measured one bare state, three 50 mg mass positions, and a final bare state. The saved comparison reports:

- three distinct position-dependent shift vectors;
- mean pairwise separation of 769 Hz in the five stable mode-channel dimensions;
- only 5 of 10 mode-channel pairs stable within 500 Hz;
- separation only 1.8 times the measured baseline drift;
- several high-frequency mode fits affected by mode hopping or large baseline movement.

This supports **physical perturbation encoding**. It does not yet support a robust rewritable template bank.

The historical E3 report's approximate separation-versus-drift ratio is 1.8, below this worklist's future `separation_ratio >=3` gate. These ratios are not identically estimated: TB-G2 uses independent rewrite distributions, which E3 did not collect. As a rough feasibility bound only, if shifts scaled linearly and drift stayed fixed, moving from 1.8 to 3 would require about `3/1.8 = 1.67x` more shift, or approximately 83 mg instead of 50 mg. Equivalently, the same 50 mg response would require a 40% drift reduction. Neither extrapolation is assumed valid: larger masses may cause mode hopping or Q loss. TB-03 tests `50/75/100 mg`, fixture disturbance, and drift before the longer codebook campaign begins.

### 1.2 Informed simulation prior (July 13)

The reproducible [simulation report](../data/results/template_bank_simulation/report.md) and [machine-readable results](../data/results/template_bank_simulation/summary.json) use the raw E3 sweeps and existing 2D plate model. They establish priors, not evidence:

- the unsmoothed E3 NW replay produces a diagonal three-pattern/three-query power matrix with a 4.63 diagonal/off-diagonal mean ratio;
- this is circularly favorable because each query uses peaks from the same single capture;
- under 25% power-gain CV, exact-peak and `+/-25 Hz` comb queries remain above 80% only to about 28 Hz total per-band rewrite jitter;
- a same-session robustness-optimized query remains above 80% to about 112 Hz in simulation, but must be recomputed on training rewrites and frozen before test rewrites;
- no tested scenario with independent per-mode rewrite-response CV >=5% reaches an 80% probability of passing TB-G2, even at 100 mg;
- simulated TB-G2 crossings require response CV <=2.5% plus approximately: 50 mg at 25% of the E3 drift proxy, 75 mg at 50%, or 100 mg at 75%;
- a symmetric four-corner site layout is degenerate in the uncertain square-plate mode ensemble;
- historical Plate I/H data show different RX positions within one plate vary at least as much as crossing between plates, so matched PZT topology and per-cell bare references are mandatory;
- with eight captures per rewrite, minimum rewrite blocks are approximately 9/14/23/32 for rewrite-level ICC `0.10/0.25/0.50/0.75`.

The stronger hypothesis carried into the bench is:

> Direct mass-written energy matching is plausible, but repeatable response and frequency stability are the immediate bottlenecks. Reduce and measure those before increasing template count.

### 1.3 Claim ladder

| Level | Claim                                  | Required evidence                                                                                             |
| ----- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| 0     | Mass perturbation changes the spectrum | E3, MEASURED                                                                                                  |
| 1     | Reversible physical write              | Repeated `bare -> pattern -> bare` recovery with uncertainty                                                  |
| 2     | Repeatable template state              | Independently reconstructed pattern gives the same shift/response distribution across cycles and days         |
| 3a    | Physics-generated discriminability     | One globally frozen digital scalar extracted from the physical response ranks compatible template-query pairs |
| 3b    | Direct physical match scalar           | One multitone query produces a directly measurable total RMS/envelope score with no per-tone FFT weighting    |
| 4     | Physical template bank                 | Multiple cells retain different templates and a common query selects the compatible cell                      |
| 5     | Rewritable physical bank               | Swapping mass patterns changes logical identity; identity follows pattern rather than cell                    |
| 6     | Physical associative completion        | A reduced physical query selects the full compatible template and handles ambiguity/unknowns correctly        |
| 7     | MEMS template array                    | Lithographic/reconfigurable sites reproduce Levels 1-6 at measured chip-scale energy and latency              |

### 1.4 Language rule

- If patterns can be read but query compatibility is computed from pattern-specific centroids in software, say **physically written memory with digital matching**.
- If one globally frozen digital scalar ranks compatible responses, say **physics-generated discriminability with frozen digital readout**.
- Say **physical template matching** only after one multitone excitation produces a directly observable total output-energy/envelope scalar that ranks templates without per-tone digital composition.
- If the same result survives physically omitted query components, say **physical associative completion**.
- Do not say attractor memory unless feedback or nonlinear dynamics actually drive the state toward a stored pattern.
- Do not say parallel bank if cells are read one at a time through a relay.

---

## 2. Master Gates

| Gate   | Question                                                            | Pass requirement                                                            | Failure action                                                   |
| ------ | ------------------------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| TB-G0  | Is the readout safe and trustworthy?                                | No board fault; acoustic null and baseline recovery pass                    | Stop all powered work                                            |
| TB-G1  | Is a write reversible?                                              | At least 4/5 cycles pass write and erase criteria                           | Treat as write-once or sensing only                              |
| TB-G2  | Are pattern states repeatable?                                      | Four-pattern leave-cycle-out accuracy >=95%; separation ratio >=3           | Reduce pattern count/mass uncertainty or stop bank claim         |
| TB-G3  | Is the encoding compositional enough?                               | At least three independent site-mode channels with monotonic level response | Shorten codeword or use whole-pattern noncompositional templates |
| TB-G4a | Does the response contain a frozen-scalar-extractable match signal? | Digital scalar top-1 >=80%, >=15 points above controls, margin >3 SD        | Memory exists; matching remains pattern-specific/digital         |
| TB-G4b | Does one query produce a direct physical scalar?                    | Multitone total RMS/envelope top-1 >=80%, no per-tone FFT weights           | Keep Level 3a only; no direct physical-match claim               |
| TB-G5  | Does logical identity follow the written pattern?                   | Pattern-follow accuracy >=80% after cyclic swaps                            | Intrinsic plate PUF dominates; no rewritable bank claim          |
| TB-G6  | Does a physically partial query complete?                           | >=80% unique-clue match and >=10 points over wire                           | Keep full-query matching only                                    |
| TB-G7  | Can unknown queries be rejected?                                    | AUROC >=0.90; false-known <=10% at 90% known recall                         | Forced-choice CAM only; external validity gate required          |
| TB-G8  | Is rewriting durable?                                               | >=100 cycles with <10-point match loss and no Q collapse                    | Limited-endurance or one-time-programmable framing               |

No later phase proceeds when its controlling gate fails.

---

## 3. Hardware and Safety Freeze

### Current blocking fault

The June 30 diary records a shorted/overheated RX board with burning smell and a dead common Ch-A readout path. The board was disconnected. **Do not re-power it until the fault is located and corrected.** Existing captured results remain valid, but new template-bank measurements are blocked by TB-G0.

TB-00 may require multiple sessions and replacement parts or a clean preamp rebuild. Its calendar estimate is not a promise to repair a burned board in one sitting.

### Preferred proof hardware

| Stage                   | Preferred device                                          | Reason                                                                |
| ----------------------- | --------------------------------------------------------- | --------------------------------------------------------------------- |
| Reversible cell         | 25 x 25 x 1 mm fused-silica plate used in E3              | Existing bare/A/B/C data and large mass sensitivity                   |
| Site/mass tensor        | Same 25 mm plate                                          | Removes inter-device variance                                         |
| Sequential cross-matrix | Same 25 mm plate, independently rewritten                 | Tests pattern-query interaction without plate PUF confound            |
| Multi-cell bank         | Minimum three, target four matched-geometry plates/slides | Separates cell identity from written pattern identity                 |
| Wheel demonstrator      | Four-cell proof first; eight cells only after TB-G5       | Current noisy working-memory evidence supports only 4-8 coarse states |

Use one RX path per active cell. A summed RX bus cannot identify which template won. Relay-selected readout is acceptable for the first bank proof but must be labeled **time-multiplexed**.

The E3 plate was later rewired for phase-interference experiments and may no longer have the original dedicated RX topology. TB-00 must verify or restore at least one working RX before selecting it. Do not assume the June 5 relay 5/6 wiring still exists.

The current inventory does not establish three spectrally matched, independently readable cells. Do not buy or prepare a bank until TB-G4b passes on one cell. TB-29 then defines the matched-cell procurement/build package.

### Materials

- wax putty from the E3 protocol, not hardened silicone support putty;
- 0.001 g scale;
- printed placement grid fixed to the plate reference frame;
- non-marring placement/removal tool;
- camera or phone for a top-down image after every write;
- Pico NCO, PicoScope, known-good preamp/readout, and existing TX/RX PZTs;
- temperature probe or logger, required for every valid write/erase block;
- after TB-G4b only: matched same-lot cells, identical PZTs/adhesive/templates, and independent or relay-selected RX paths per TB-29.

### Placement tolerances

- mass target: `target +/- 1 mg`;
- site center: `+/- 0.5 mm` for the 25 mm plate, `+/- 1 mm` for 100 mm plates;
- photograph every pattern before capture;
- never reshape or divide a dot during a cycle without reweighing it;
- do not alter supports, PZT bonds, wiring, gain, or plate orientation between bare and written captures.
- hold temperature within `+/- 1 C` during each bare/write/erase block; invalidate and repeat a block outside that range.

---

## 4. Data and Analysis Contract

All results go under:

```text
data/results/template_bank/<experiment_id>/<timestamp>/
```

Every capture set contains a JSON manifest and NPZ/raw sweep data.

### Required manifest fields

```text
experiment_id
timestamp
git_commit, git_dirty
operator
plate_id, geometry, PZT map
support/fixture description
readout path and gain
NCO channels, frequencies, amplitudes, phases
mass_dot_id, measured_mass_mg
site_id, target_xy_mm, observed_xy_mm
pattern_id, codeword
query_id, visible_positions, omitted_positions
cycle_id, repeat_id, session_id
temperature_C
frequency grid, averages, settle time
raw-data paths
```

Pattern labels must be randomized to coded IDs before peak fitting and mode assignment. Decode labels only after the accepted-mode table and scalar scores are saved. Temperature is mandatory, not optional.

### Frequency-shift state

For stable modes, define the written shift vector

$$
\Delta \mathbf f_p = \mathbf f_p - \mathbf f_{bare}.
$$

Estimate baseline covariance `Sigma_bare` from repeated bare captures, then use the regularized Mahalanobis distance

$$
D_p^2 = \Delta \mathbf f_p^T(\Sigma_{bare}+\lambda I)^{-1}\Delta \mathbf f_p.
$$

Also report raw shifts in Hz and linewidth units. Never report only a classifier score.

### Repeatability and separation

For each pattern:

- `intra95`: 95th percentile distance between independent rewrites of the same pattern;
- `inter_min`: minimum distance between different pattern centroids;
- `separation_ratio = inter_min / intra95`.

TB-G2 requires `separation_ratio >= 3` and leave-one-cycle-out pattern accuracy >=95%.

### Prospective mode and sample rules

- Freeze the candidate mode list from TB-02 bare data before applying mass.
- A mode that destabilizes under load is a reported failure; do not silently replace it after viewing pattern labels.
- Validate the mode tracker with injected shifts spanning `0.25-10` linewidths before TB-03. Require >=95% identity recovery and <5% false reassignment over the planned shift range.
- Every accuracy gate reports a Wilson interval or block bootstrap that preserves rewrite-cycle and session dependence.
- Use [the informed simulation report](../data/results/template_bank_simulation/report.md) for initial sample planning. With eight captures per rewrite and an 80% target against a 65% control, the approximate minimum is 9 rewrite blocks at rewrite-level ICC 0.10, 14 at ICC 0.25, 23 at ICC 0.50, and 32 at ICC 0.75.
- TB-21/TB-22 start with at least nine independent rewrites and adapt upward after TB-10 estimates rewrite-level ICC. Repeated FFT averages within one capture are not independent trials.

### Frozen digital score and direct physical scalar

TB-G4a uses one global digital scalar form, frozen before the test set. The initial candidate is normalized energy at the visible query tones:

$$
S_{ij}=\frac{1}{|V_j|}\sum_{k\in V_j}
\log\left(\frac{P_i(f_{jk})+\epsilon}{N_i(f_{jk})+\epsilon}\right),
$$

where cell `i` contains template `i`, query `j` supplies visible tones `V_j`, `P` is measured response power, and `N` is the cell's pump-off noise. Use one global orientation: either the match is maximum energy or minimum notch energy. Do not choose orientation separately for each pattern.

This score is computed from digitized FFT bins. Passing TB-G4a proves that the physical response contains query-dependent discriminability under a frozen digital readout; it does not make the score itself analog or autonomous.

TB-G4b instead uses the directly measurable time-domain output energy from one multitone query,

$$
E_{ij}=\frac{1}{T}\int_0^T v_i^2(t)\,dt,
$$

or an equivalent globally fixed envelope/RMS voltage. The PicoScope may digitize `v(t)` to validate this scalar, but no per-tone FFT bins, logs, signs, or learned weights may be combined. A later analog RMS/envelope detector can implement the same operation without an ADC.

Pattern-specific centroids, logistic models, or per-cell fitted weights are secondary diagnostics. They cannot pass TB-G4a or TB-G4b.

---

## 5. Phase 0 - Restore Trustworthy Measurement

### TB-00 - RX Board Recovery and Topology Manifest

**Objective:** Restore a safe, reproducible acoustic readout before touching template claims.

**Procedure:**

1. Keep the failed board unpowered during cold inspection.
2. Identify and photograph the overheated/shorted component or replace the board with a known-good readout.
3. Verify rail isolation and correct component polarity before connecting a plate.
4. Power only the repaired/known-good path and verify expected supply behavior.
5. Label every TX, RX, summing resistor, relay route, and plate.
6. Save `hardware_manifest.json` plus overview photographs.

**Required data:** cold resistance checks, supply readings, noise-only scope capture, signal-path diagram, plate/PZT map.

**Pass TB-G0a:** no heat, smell, rail collapse, clipping, or unexplained DC output during a 10-minute no-plate soak.

**Kill:** any renewed heating or rail short. Disconnect immediately; do not continue troubleshooting live.

**Time:** one or more repair sessions. **Hardware:** owned parts if serviceable; replacement OPA2134/passives or a clean known-good preamp may be required.

---

### TB-01 - Acoustic Origin and Baseline-Recovery Check

**Objective:** Prove that the recovered channel measures the plate rather than electrical feedthrough.

**Procedure:**

1. Select three strong modes spanning the intended band.
2. Capture 20 repeats in the coupled state.
3. Lift or mechanically decouple the active RX PZT without changing electrical wiring; capture 20 repeats.
4. Re-seat it identically; capture 20 repeats.
5. Run pump-off and no-glass electrical controls.

**Pass TB-G0b:** lifted/coupled response <1% on all three modes; re-seated baseline recovers within 5%; coupled SNR >=20.

**Kill:** lifted/coupled >5%, failure to recover baseline, or unexplained drive-correlated signal in the no-glass path.

**Data path:** `data/results/template_bank/TB-01/`
**Time:** 30-45 minutes after TB-00.

---

### TB-02 - Bare-State Stability Budget

**Objective:** Measure the noise and drift that every write must beat.

**Procedure:**

1. Freeze the plate, fixture, PZT routes, gain, and sweep grid.
2. Capture ten bare fine sweeps at 2-minute spacing.
3. Leave untouched for 30 minutes; capture five more.
4. Repeat five captures after a complete power-cycle without moving the plate.
5. Fit mode centers and linewidths with fit-quality flags.
6. Log temperature continuously and report frequency-temperature slopes where the span permits.
7. Before mass loading, blind the labels and validate the frozen mode tracker using copies of the bare spectra with injected shifts of `0.25, 0.5, 1, 3, and 10` measured linewidths plus synthetic neighboring peaks.

**Required outputs:** per-mode center SD, linewidth, Q, fit residual, covariance matrix, power-cycle offset, and accepted stable-mode list.

**Pass:** at least six stable mode-channel dimensions with fit `R2 >= 0.95` and no baseline excursion above one linewidth.

**Redirect:** if only three to five dimensions survive, continue with a shorter code. Fewer than three stable dimensions stops the present plate.

**Data path:** `data/results/template_bank/TB-02/`
**Time:** about one hour, partly unattended.

---

### TB-03 - E3 Feasibility and Fixture-Disturbance Gate

**Objective:** Determine cheaply whether the measured E3 separation can reach TB-G2 before running the full site/mass tensor.

**Procedure:**

1. Use only the prospectively frozen TB-02 modes and tracker.
2. At E3 site A and one second candidate site, run five randomized **touch-only** trials: approach and contact the marked location with the placement tool but deposit no mass.
3. Run independently rebuilt `50, 75, and 100 mg` dots at site A, three placements per mass, with a verified bare state between placements.
4. Repeat the most promising mass at the second site.
5. Record Q, linewidth, mode-hop rate, temperature, placement error, write distance, and erase recovery.
6. Do not drop a loaded mode after viewing its pattern label. Report prospective-list and exploratory replacement-list results separately.
7. Measure rewrite-response CV across independent placements and compare with the simulation's `2.5%` and `5%` sensitivity thresholds. This is a prediction check, not an added pass criterion.

**Pass:** at least one mass `<=100 mg` gives `separation_ratio >=3` between the two sites, write distance >3 baseline SD, Q loss <30%, mode-hop rate <10%, clean erase, and touch-only captures inside the 95% bare region.

**Redirect / kill:**

- touch-only shifts exceed one baseline SD: fix the fixture/placement process before continuing;
- 75/100 mg improves separation but causes mode hopping or Q loss: try the 100 mm plate or lower-drift readout, not still more mass;
- no tested condition reaches ratio 3: stop TB-11 through TB-42 on this geometry. Retain E3 as perturbation sensing/encoding evidence and evaluate a different plate or optical readout.

**Data path:** `data/results/template_bank/TB-03/`
**Time:** one focused session.

---

## 6. Phase 1 - Close the Reversible Write Primitive

### TB-10 - P8 Write-Erase-Rewrite Closeout

**Objective:** Replace the one-pass E3 sequence with independent repeated write cycles.

**Pattern:** use the lowest-mass condition that passed TB-03, at the strongest prospectively stable site. Site A `(8.3, 8.3) mm` is the initial candidate, not a guaranteed choice.

**Procedure:**

1. Capture three bare sweeps.
2. Place the weighed dot using the printed guide; photograph; capture three sweeps.
3. Remove the dot without touching the fixture; wait two minutes; capture three bare sweeps.
4. Repeat steps 1-3 for five cycles, rebuilding the dot placement independently each time.
5. On cycle 5, rewrite site A a second time after an intervening different-site write.

**Primary metrics:** write Mahalanobis distance, shift in linewidth units, erase residual, same-pattern intra-cycle distance, Q change.

**Pass TB-G1:**

- written state >3 baseline SD in vector distance on 5/5 cycles;
- at least 4/5 erase states fall inside the 95% bare-state region;
- no stable mode has erase residual >1 SD on more than one cycle;
- rewritten A is closer to prior A cycles than to the intervening pattern.

**Fail interpretation:**

- write passes, erase fails: one-time/limited-endurance physical programming;
- write varies strongly with placement: placement process, not resonator physics, is the bottleneck;
- Q falls >30%: dot/support damping overwhelms the encoding benefit.

**Data path:** `data/results/template_bank/TB-10/`
**Time:** 2-3 hours.

---

### TB-11 - Mass Dose and Position Sensitivity Tensor

**Objective:** Find site-mode-mass channels that can encode symbols rather than only unique whole-pattern fingerprints.

**Design:** active-learning site screen followed by four selected sites x three mass levels (`10, 25, 50 mg`) x three independent placements, with a bare capture between every placement.

**Procedure:**

1. Screen the E3 A/B/C sites plus the simulation's uncertainty-robust candidates at approximately `(13.1,12.2)`, `(13.7,16.6)`, `(19.4,3.9)`, and `(3.1,19.2) mm`, using one independently built dot at the TB-03 passing mass. Verify PZT/adhesive clearance first; if a candidate is blocked, record the exclusion rather than silently moving it.
2. Treat those novel sites as out-of-sample tests of the 2D sensitivity ensemble. Score predictions before using their measurements to update the model.
3. Select four empirical sites that maximize repeatable separation while retaining at least two out-of-sample/model-challenging positions.
4. For each selected site and mass, run `bare -> written -> bare` in randomized order.
5. Track the TB-02 stable modes only; flag mode hops rather than relabeling them after seeing results.
6. Fit the sensitivity tensor

$$
T_{m,s,l}=f_m(s,l)-f_m(bare).
$$

7. Test monotonicity with mass and position specificity for every mode.

**Pass condition:** at least three site-mode assignments have:

- shift >3 baseline SD at 25 mg;
- monotonic median shift over 10/25/50 mg;
- assigned-site sensitivity at least twice the RMS sensitivity to the other candidate sites;
- erase recovery passing TB-G1.

**Redirect:**

- three assignments: use three-symbol-position codewords;
- two assignments: limit the first bank to two-position templates;
- no selective assignments but whole patterns remain distinct: proceed only to noncompositional template states; Wheel branch stops.

**Data path:** `data/results/template_bank/TB-11/`
**Time:** two sessions.

---

### TB-12 - Four-Pattern Independent Rewrite Codebook

**Objective:** Demonstrate four logical states that can be rebuilt from bare without relying on one continuous measurement sequence.

**Pattern design:** choose four patterns before capture. Keep total mass equal within `+/- 2 mg` so a decoder cannot classify total mass alone. Require pairwise pattern Hamming distance >=2 over the selected sites.

**Procedure:**

1. Generate a randomized schedule containing each pattern five times.
2. Start every trial from a TB-G1-qualified bare state.
3. Rebuild the pattern from weighed dots; photograph; capture three sweeps.
4. Remove all dots and verify bare recovery before the next trial.
5. Repeat the full schedule on another day using the same frozen mode list.

**Analysis:** raw shift-vector nearest centroid, regularized Mahalanobis centroid, and one linear classifier as a diagnostic. Use leave-one-cycle-out and leave-one-day-out validation.

**Pass TB-G2:**

- leave-one-cycle-out accuracy >=95%;
- leave-one-day-out accuracy >=80% without retuning modes;
- `separation_ratio >= 3`;
- shuffled pattern labels return chance;
- total mass alone is no better than 35% for four classes.

**Kill:** fewer than three patterns survive at >=80% leave-day-out accuracy. Keep physical sensing/write, stop the template-codebook claim for this geometry.

**Data path:** `data/results/template_bank/TB-12/`
**Time:** two half-day sessions.

---

### TB-13 - Multi-Site Composition and Ghost Test

**Objective:** Determine whether multiple sites form a usable code or an inseparable global perturbation.

**Procedure:**

1. Measure every selected single-site/single-level state.
2. Before measuring multi-site states, reserve at least four balanced combinations that are not used to fit or select the additive model.
3. Measure the frozen multi-site TB-12 patterns and the held-out combinations in randomized coded order.
4. Predict each multi-site shift vector by adding its single-site vectors.
5. Compare prediction with measurement on held-out combinations, modes, and rewrite cycles. Report model degrees of freedom and prediction intervals.
6. Analyze spectrally close mode pairs separately; do not fold mode hopping into additive residual noise.
7. After every multi-dot pattern, erase and test for residual ghost shifts.

**Metrics:** additive-model `R2`, per-mode residual in linewidths, mode-hop rate, pattern accuracy from assigned channels only versus all modes, erase-ghost vector.

**Pass TB-G3:** at least three assigned channels, held-out-combination additive-model `R2 >= 0.8`, no systematic residual above one linewidth, and no erase ghost above one baseline SD.

**Redirect:** if patterns classify but `R2 < 0.8`, call them **whole-pattern physical templates**. Do not claim independent symbol sites or compositional completion.

**Data path:** `data/results/template_bank/TB-13/`
**Time:** one session plus analysis.

---

## 7. Phase 2 - Test Matching, Not Just Fingerprinting

### TB-20 - Freeze Query Frequencies and the Scalar Score

**Objective:** Compile each written pattern into a query tone set without using test cycles.

**Procedure:**

1. Use only TB-11/TB-12 training cycles to select stable query frequencies.
2. For a compositional encoding, assign one stable mode to each symbol position and one frequency to each mass level.
3. For a whole-pattern encoding, select four frequencies that maximize minimum training separation while enforcing at least one held-out validation mode.
4. Freeze query bundles, tone amplitudes, visible-position rules, score orientation, normalization, and abstention threshold in `data/config/template_bank_v1.json`.
5. Generate a shuffled-query and random-frequency control set of equal size.
6. Include the simulation's robustness-optimized frequency proposal as one preregistered candidate, but recompute it from training rewrites only. The E3 same-session candidate is a hypothesis, not a frozen test query.

**No-tuning rule:** no frequency, weight, sign, or threshold changes after TB-21 test captures begin.

**Pass:** four query bundles with at least two frequencies each, all inside stable readout regions and separated from electrical spurs.

**Redirect:** if only one whole-pattern signature per template is available, full-query matching may continue; partial-symbol claims stop.

**Data path:** `data/config/template_bank_v1.json` and `data/results/template_bank/TB-20/`.

---

### TB-21 - Sequential Template x Query Discriminability Matrix

**Objective:** Test whether a written pattern and its query produce a physical response from which one globally frozen digital scalar can extract compatibility.

**Procedure:**

1. Independently write pattern `P1`.
2. Apply frozen queries `Q1...Q4` in randomized order, at least 16 independent captures each.
3. Capture response power at every visible query tone plus the full spectrum.
4. Erase, verify bare, and repeat for `P2...P4`.
5. Repeat the complete 4 x 4 matrix over at least nine independent rewrite cycles, then increase to the adaptive requirement derived from the TB-10 ICC estimate. Maintain at least eight captures per pair per rewrite.
6. Run the same query matrix on the bare plate and no-glass electrical path.
7. Add random equal-total-mass patterns that are not in the codebook and test them with all frozen queries.
8. Keep pattern IDs blinded through mode tracking, scalar computation, and acceptance/rejection decisions.

**Primary result:** the 4 x 4 scalar matrix `S_ij` from the globally frozen energy/notch score.

**Controls:** shuffled query labels, random frequencies, equal-total-power queries, bare plate, no-glass path, random equal-total-mass positions, fixture-touch nulls, and pattern-specific digital centroid decoder reported separately.

**Pass TB-G4a:**

- correct pattern is top-1 for >=80% of query repeats;
- accuracy exceeds the strongest bare/no-glass/random-mass control by >=15 points;
- every diagonal score exceeds the strongest off-diagonal score by >3 pooled capture-noise SD, or the globally frozen notch score is lower by the same margin;
- shuffled labels return chance;
- no-glass and bare controls do not reproduce diagonal dominance;
- a single score orientation works for every pattern.
- the block-bootstrap 95% interval for top-1 accuracy excludes the strongest control accuracy.

**Interpretation:** passing TB-G4a establishes physics-generated query discriminability under a frozen digital readout. It does not yet establish a directly physical scalar or analog comparator.

**Decisive failure:** patterns remain classifiable from their full spectra, but the scalar matrix is not diagonal. Conclusion: mass sites store physical states, but the current response does not expose a simple query-compatible score.

**Data path:** `data/results/template_bank/TB-21/`
**Time:** one long session.

---

### TB-22 - Direct Multitone Physical-Scalar Test

**Objective:** Test whether one multitone query yields a directly observable total RMS/envelope score that ranks compatible patterns without per-tone FFT composition.

**Procedure:**

1. On each written pattern, measure every query tone separately.
2. Drive the same visible tones simultaneously through a validated combiner or independent TX channels.
3. Hold total RMS drive equal between sequential and multitone conditions.
4. Scan for harmonics and intermodulation outside the query set.
5. Prefer a fixed post-`Foff` ringdown window so direct electrical feedthrough is absent: drive for a fixed interval, issue `Foff`, and integrate the first preregistered ringdown window. If timing/SNR makes ringdown unusable, use driven-state RMS only with coupled/lifted and no-glass subtraction reported alongside it.
6. Compute only total time-domain RMS/energy or one fixed-band analog envelope. Do not combine individual tone bins.
7. Compare this direct scalar with the TB-21 digital score and labels.
8. Repeat at least eight captures per pattern-query pair over at least nine rewrite cycles, then increase rewrite blocks according to the TB-10 ICC estimate.

**Pass TB-G4b:** direct-scalar top-1 >=80%, >=15 points above bare/no-glass/random-mass controls, compatible margin >3 SD, agreement with TB-21 labels >=95%, and every IM product below 3 SD of the no-glass control.

**Redirect:** if TB-21 passes but TB-22 fails, retain **physics-generated discriminability with frozen digital readout**. Do not claim a direct physical match scalar or one-propagation physical matching.

**Safety:** validate any electrical combiner on a dummy load before connecting NCO outputs together. Never hard-short output channels.

**Data path:** `data/results/template_bank/TB-22/`
**Time:** one session.

---

### TB-23 - Physically Omitted Components on One Rewritten Cell

**Objective:** Replace post-capture feature masking with a physically incomplete input.

**Procedure:**

1. For each query, generate all one-component-omitted and selected two-component-omitted versions by setting those physical drive tones to zero.
2. Recapture the response; never derive a partial query by deleting FFT bins from a full-query capture.
3. Test unique, ambiguous, and invalid partial queries separately.
4. Report top-1, top-k compatible-set coverage, margin, and abstention.
5. Treat the output as the selected full template identity and its stored metadata. Do not claim that the plate regenerates the omitted electrical tone.

**Pass:** one-omission top-1 >=80%; two-omission compatible-set coverage >=80%; invalid-query AUROC >=0.90.

**Interpretation:** this passes a sequential-cell **reduced-cue recognition** primitive. The omitted drive is genuinely absent from the query, but the hardware does not regenerate its waveform; the controller returns the identity and metadata of the compatible full stored template. Call it associative completion only when that full template identity is the declared output and ambiguity/unknown gates pass.

**Data path:** `data/results/template_bank/TB-23/`
**Time:** one session.

---

## 8. Phase 3 - Multi-Cell Physical Template Bank

### TB-29 - Matched-Cell Qualification and Build Package

**Objective:** Establish whether existing cells can support a controlled bank and define a small BOM only if they cannot.

**Procedure:**

1. Inventory all same-geometry cells currently owned, including the 100 mm plates and small slides/plates. Record dimensions, bare mass, thickness, PZT layout, adhesive, support, and wiring.
2. Group candidates by geometry and readout topology; do not mix different bands merely to reach a desired bank width.
3. Use unpowered photographs and historical censuses to rank candidates before new bonding.
4. If at least three existing cells cannot be made topology-matched without damaging validated hardware, prepare a same-lot build package for four cells: identical substrate blanks, one TX and one RX PZT each, identical adhesive mass/placement, identical supports, relay or independent RX routes, and one spare.
5. Prefer the geometry that passed TB-03/TB-G4b. The E3 history alone does not force the bank to use 25 mm cells if a 100 mm cell has better stable separation.

**Pass:** a documented three-cell minimum/four-cell target set with common query band, common PZT topology, independent addressability, and estimated build cost/time.

**Stop rule:** no purchase or irreversible rebonding before TB-G4b passes on one cell.

**Data path:** `data/results/template_bank/TB-29/` plus `data/config/template_bank_cells_v1.json`.

---

### TB-30 - Matched-Cell Inventory and Bare Confound

**Objective:** Select cells for which intrinsic PUF differences can be measured and controlled.

**Procedure:**

1. Inventory every available plate/slide by dimensions, mass, PZT count/position, support, and usable modes.
2. Select at least three cells with the closest geometry and readout topology.
3. Capture repeated bare responses to every frozen query.
4. Quantify how accurately cell identity can be predicted before any mass pattern is written.
5. Freeze each cell's own bare direct-scalar vector and drift distribution. Define the calibrated write contrast as `C_ij = E_written,ij - E_bare,ij` or the globally chosen sign-reversed notch equivalent.
6. Report both raw `E_ij` and calibrated `C_ij`. Calibration parameters come only from bare/training blocks and remain frozen through TB-32.

**Required output:** bare cell x query matrix, Q/mode table, cell-identity accuracy, and normalization plan.

**Pass:** minimum three cells with >=3 common usable query channels, SNR >=20, and bare drift low enough that the projected written contrast exceeds 3 SD on every cell.

**Caveat:** high bare cell-identity accuracy is expected. It is not failure, but it makes TB-32 pattern swapping mandatory.

**Data path:** `data/results/template_bank/TB-30/`.

---

### TB-31 - First Time-Multiplexed Written Bank

**Objective:** Place one frozen template on each cell and query the bank with the same absolute-frequency physical input.

**Procedure:**

1. Write `P1...PN`, one pattern per cell, where `N >= 3`.
2. Broadcast or sequentially reproduce the identical absolute frequencies, amplitudes, phases, and timing on every cell.
3. Read cells separately through relay selection or independent channels; do not use an inseparable summed RX bus.
4. Randomize cell read order and query order.
5. Repeat ten times per query and on a second day.
6. As a diagnostic only, run a cell-calibrated variant in which query frequencies are expressed as offsets from each cell's own bare modes. This may establish a calibrated time-multiplexed bank, but it cannot pass the common-query bank gate.

**Primary result:** query x cell matrices for raw direct scalar `E_ij` and frozen per-cell bare-referenced contrast `C_ij`. Report the TB-G4a digital score only as a diagnostic.

**Pass:** the common absolute-frequency query gives compatible pattern top-1 >=80% on `C_ij`, >=15 points above raw bare-cell identity, direct-wire, and random-mass comparators, with compatible contrast >3 SD and second-day loss <10 points.

**Language:** relay-selected cells that pass the common-query gate are a **time-multiplexed physical template bank**. If only cell-relative queries work, say **calibrated time-multiplexed template bank**. Parallel bank language requires simultaneous independent scores.

**Data path:** `data/results/template_bank/TB-31/`.

---

### TB-32 - Pattern/Cell Crossover

**Objective:** Prove that logical identity follows the written mass pattern rather than intrinsic plate identity.

**Procedure:**

1. Save the complete TB-31 bank matrix.
2. Erase every cell and verify its own bare recovery.
3. Cyclically permute patterns: cell 1 receives the old cell 2 pattern, cell 2 receives cell 3, and so on.
4. Repeat the bank query with all score definitions frozen.
5. Run a second independent permutation.
6. Reference every written response to that cell's own frozen/current bare block according to the TB-30 rule; never compare an absolute resonance from one cell with another cell's bare spectrum.
7. Include the raw direct scalar, bare-referenced contrast, and a mixed-effects model with pattern, cell, rewrite cycle, and session terms.

**Primary metrics:** pattern-follow accuracy, cell-follow accuracy, difference-in-differences score, erase residual, and mixed pattern/cell variance components.

**Pass TB-G5:**

- logical label follows the new pattern on >=80% of query repeats;
- the old cell label is no better than 50% for a three/four-cell bank;
- pattern-follow advantage over cell-follow exceeds 3 bootstrap standard errors;
- pattern effect exceeds the residual cell effect in the preregistered mixed-effects analysis;
- both permutations pass.

**Failure:** if winners remain tied to cells, the bank is reading plate PUF identity. Keep the PUF claim; reject rewritable logical-template identity.

**Data path:** `data/results/template_bank/TB-32/`
**Time:** two sessions.

---

### TB-33 - Simultaneous Independent Readout (Optional Scaling Gate)

**Objective:** Replace relay scanning with one score per cell in one query interval.

**Requirements:** one independent RX/amplifier/ADC channel per cell or a calibrated analog winner network. A summed bus is insufficient.

**Pass:** simultaneous winner agrees with TB-31 sequential winner >=95%, no channel contributes >-30 dB into another cell's readout, and latency is independent of bank size over the tested cells.

**Language unlocked:** **parallel physical template bank** for the measured width only.

---

## 9. Phase 4 - Mass-Written Wheel Demonstrator

### TB-40 - Compile Eight Balanced Codewords

**Objective:** Build an eight-template codebook whose identity cannot be reduced to total mass.

**Preferred compositional encoding:** four written positions with three qualified mass levels. Select eight codewords from the available level combinations such that:

- pairwise Hamming distance >=2;
- total mass is equal within `+/- 2 mg`, or total mass is balanced across labels;
- each level appears equally often at each position where possible;
- the bank contains unique one-blank clues, unique two-blank clues, and deliberate ambiguous clues;
- codeword selection is frozen before test capture.

If TB-G3 supports fewer than four independent positions, shrink the codeword length. Do not fill missing dimensions with software-only symbols.

**Deliverable:** `data/config/template_bank_wheel_v1.json`, placement sheets, query-tone table, clue classes, and frozen train/calibration/test split.

---

### TB-41 - Four-Template Wheel Pilot

**Objective:** Run the complete protocol at the smallest credible bank width before building eight cells.

**Conditions:** full query, every one-blank query, selected two-blank queries, ambiguous clues, valid-unenrolled queries, invalid drive patterns, noise-only, and no-glass null.

**Baselines:** Hamming lookup, direct wire, no-glass electrical path, equal-dimensional random projection, and post-capture masking.

**Sampling:** at least nine independent bank rewrites/configurations across two sessions, increased to 14/23/32 if the TB-10 rewrite-level ICC is approximately 0.25/0.50/0.75; at least eight captures of each clue per bank configuration. Report rewrite/session-block bootstrap intervals. Repeat the entire pilot under at least three symbol-to-mass/frequency mappings frozen before each session.

The blank is a physically reduced cue, not a regenerated symbol. Completion means that the bank returns the compatible **full stored codeword identity** from the visible subset. Ambiguous clues must return a compatible set/top-k result; invalid clues must abstain.

**Pass TB-G6/TB-G7:**

- unique physical-clue completion >=80%;
- > =10-point advantage over direct wire under matched noise;
- ambiguous-clue compatible-set coverage >=90%;
- unknown AUROC >=0.90;
- false-known <=10% at 90% known recall;
- physical omission outperforms or matches post-capture masking without leakage;
- result survives a symbol-to-mass/frequency remapping.

**Kill:** direct wire/Hamming/random projection matches the plate, or OOD remains at chance. Retain the written-template demo but not physical associative completion.

**Data path:** `data/results/template_bank/TB-41/`.

---

### TB-42 - Eight-Template Wheel Bank

**Prerequisites:** TB-G0 through TB-G7 and eight sufficiently matched cells, or a fabricated array with eight independently read cells.

Repeat TB-41 at width eight. Add:

- bank-width scaling at 2/4/8 templates;
- accuracy versus clue ambiguity;
- energy and latency versus bank width;
- cell failure and one-template rewrite tests;
- second-operator placement replication.

**Pass:** TB-41 gates remain satisfied at width eight and total physical score-generation energy/latency is reported against digital Hamming lookup.

**No advantage rule:** a successful human-readable demo is not an accelerator claim unless whole-system energy or latency wins under a fair comparator.

---

## 10. Phase 5 - Rewrite Endurance and MEMS Handoff

### TB-50 - Rewrite Endurance

**Objective:** Measure whether repeated physical programming degrades the cell or placement interface.

**Procedure:** alternate two maximally separated patterns for 100 write/erase cycles. Run a full verification block at cycles `0, 1, 2, 5, 10, 20, 50, 100`.

**Metrics:** match accuracy, shift-vector drift, erase residual, Q, linewidth, placement time, dot mass loss, and visible surface residue.

**Pass TB-G8:** <10-point match-accuracy loss, Q loss <20%, no monotonically growing erase ghost, and at least 95/100 verified writes.

**Redirect:**

- residue accumulates but logical matching survives: limited-endurance removable programming;
- matching fails but geometry remains stable: placement/tooling bottleneck;
- Q degrades irreversibly: stop removable-dot endurance and move to fabricated fixed templates.

**Data path:** `data/results/template_bank/TB-50/`.

---

### TB-51 - Retention and Environment

**Objective:** Separate template retention from temperature and fixture drift.

**Procedure:** leave one pattern written and read at `0, 10, 30, 60, 120 minutes`, then next day. Record temperature. Repeat one short block after a controlled small temperature change if safe.

**Pass:** pattern remains correctly matched at every point; score margin remains >3 SD; compensation parameters are learned from calibration data only.

**Data path:** `data/results/template_bank/TB-51/`.

---

### TB-60 - MEMS Encoding Specification

**Objective:** Translate only the encoding that passed the macro gates into a fabricable cell.

**Required outputs:**

- cell geometry and stable mode set;
- site-mode sensitivity matrix with uncertainty;
- fixed versus reconfigurable mass-site choice;
- lithographic mass dimensions for each symbol level;
- AlN TX/RX placement and expected rank;
- predicted template-query score matrix;
- fabrication tolerance Monte Carlo;
- package pressure/Q budget;
- per-query drive/readout energy and latency;
- eight-cell and larger-bank routing/readout plan;
- on-die reference cells and bare controls.

**Fabrication gate:** simulated pattern-follow accuracy >=90% across process tolerances, predicted scalar margin >=6 SD, and no dependence on a cell-specific digital decoder.

**Reconfigurable options, in increasing difficulty:**

1. fixed lithographic mass pattern per cell: ROM/template bank;
2. electrostatic or MEMS-contact mass sites: rewritable bank;
3. phase-change or movable proof masses: multi-level rewrite;
4. femtosecond inscription: permanent volumetric templates.

Do not require rewritability in the first die if a fixed eight-template ROM array can test the physical match architecture more cleanly.

---

## 11. Ordered Execution Calendar

| Order | Experiment                          |         Bench time | Decision produced                           |
| ----: | ----------------------------------- | -----------------: | ------------------------------------------- |
|     1 | TB-00 RX recovery                   |          1 session | Safe to measure or blocked                  |
|     2 | TB-01 acoustic/null check           |             45 min | Trustworthy signal path                     |
|     3 | TB-02 bare stability                |                1 h | Stable feature list and covariance          |
|     4 | TB-03 E3 feasibility                |          1 session | Continue this geometry or stop early        |
|     5 | TB-10 P8 closeout                   |              2-3 h | Reversible versus write-once                |
|     6 | TB-11 site/mass tensor              |         2 sessions | Number of usable symbol channels            |
|     7 | TB-12 four-pattern codebook         |         2 sessions | Repeatable templates or not                 |
|     8 | TB-13 composition test              |          1 session | Compositional versus whole-pattern encoding |
|     9 | TB-20 query compiler                |           analysis | Frozen digital/direct score design          |
|    10 | TB-21 discriminability matrix       |      multi-session | Frozen digital score or memory-only         |
|    11 | TB-22 direct scalar                 |      multi-session | Physical matching or digital readout only   |
|    12 | TB-23 omitted-input test            |          1 session | Reduced-cue recognition primitive           |
|    13 | TB-29/30 matched-cell qualification |     analysis/build | Controlled bank hardware                    |
|    14 | TB-31 three-cell bank               |         2 sessions | Time-multiplexed bank                       |
|    15 | TB-32 pattern crossover             |         2 sessions | Pattern identity versus plate PUF           |
|    16 | TB-41 four-template Wheel           |      multi-session | Completion and abstention                   |
|    17 | TB-50/51 endurance/retention        |          multi-day | Rewrite specification                       |
|    18 | TB-42/TB-60 scale/fabricate         | gated/new hardware | Eight-cell demonstrator and MEMS handoff    |

TB-03 is the earliest kill decision: it prevents a long campaign on a geometry that remains at E3's approximate 1.8x separation. TB-21 decides whether the response contains a simple frozen-score match signal. TB-22 decides whether one query produces a direct physical scalar. TB-32 decides whether logical identity follows the mass pattern rather than the cell PUF.

---

## 12. Proposed Tools

| Tool                                | Role                                                                     |
| ----------------------------------- | ------------------------------------------------------------------------ |
| `tools/template_write_capture.py`   | Guided bare/write/erase capture with manifest and photographs            |
| `tools/template_shift_analyze.py`   | Mode tracking, covariance, Mahalanobis distance, recovery, repeatability |
| `tools/template_codebook_design.py` | Balanced equal-mass pattern and clue selection                           |
| `tools/template_query_compile.py`   | Freeze mode/frequency assignments and scalar score                       |
| `tools/template_query_matrix.py`    | Capture sequential pattern x query matrix                                |
| `tools/template_bank_bench.py`      | Multi-cell query/read schedule and relay/channel control                 |
| `tools/template_bank_analyze.py`    | Pattern/cell crossover, partial-query, OOD, bootstrap CIs                |

Every tool must support `--dry-run`, fixed seeds, explicit repeat/session IDs, and machine-readable JSON output. Capture tools must never infer pattern labels from measurement order.

---

## 13. Final Decision Matrix

| Observed outcome                        | Defensible conclusion                                                |
| --------------------------------------- | -------------------------------------------------------------------- |
| E3 shifts repeat, erase fails           | Physically programmed, limited-endurance/write-once state            |
| Patterns repeat, cross-matrix fails     | Rewritable physical memory; matching remains digital                 |
| TB-21 cross-matrix passes, TB-22 fails  | Physics-generated discriminability with frozen digital readout       |
| TB-22 direct scalar passes              | Direct physical template matching on one sequentially rewritten cell |
| Multi-cell bank passes, crossover fails | Cell PUF bank, not rewritable logical templates                      |
| Crossover passes                        | Rewritable physical template bank                                    |
| Full queries pass, physical blanks fail | Physical exact-match bank only                                       |
| Partial clues pass, OOD fails           | Forced-choice physical CAM                                           |
| Partial clues and OOD pass              | Physical associative completion for the measured codebook            |
| Eight-cell energy/latency also wins     | Candidate physical CAM accelerator                                   |

The central discipline is simple: mass sites count as physically written templates once they repeat. They count as a physical associative memory only when the written hardware itself contributes a query-dependent match score and the logical identity follows the pattern when that pattern moves to another cell.
