# FT-3P: Path-Sum Validation and Relational-Compute Fast Track

**Status:** OPEN / revised execution protocol  
**Parent:** PR #16 — K_eff versus readout complexity  
**Evidence note:** `docs/PATH_SUM_FT0_EXISTING_DATA_NOTE.md`  
**Reference:** Wen et al., *Direct experimental test of Feynman's path integral postulates with single photons*, Science Advances 12, eaeh1011 (2026), DOI: 10.1126/sciadv.aeh1011.

## 1. What changed

Historical CWM data already provide substantial evidence that:

- two coherent TX paths on one plate interfere strongly;
- selected phase sweeps follow a simple first-harmonic interference law;
- three independently controlled TX paths mutually interfere in one RX response;
- a 3-path trigonometric model fits the measured phase surface well enough to make "does multipath interference exist?" the wrong next question.

Therefore FT-3P is no longer primarily a discovery experiment.

The new question is:

> **Can the already-demonstrated coherent elastic path sum be frozen across sessions, survive matched electrical controls, and be engineered into increasingly useful relational computation while receiver/readout cost stays approximately fixed?**

This is a stricter and more commercially relevant target.

## 2. Claim boundary

CWM may test a classical-wave **sum-over-paths computation pattern**.

Do not claim:

- quantum superposition;
- a Feynman path integral;
- single-phonon computation;
- equal-amplitude quantum histories;
- phase equal to classical action divided by hbar.

Allowed description if fresh controls succeed:

> A classical elastic network coherently sums multiple controlled propagation contributions before readout, and the resulting interference can implement stable relational functions.

## 3. Existing prior

The detailed retrospective evidence is in `docs/PATH_SUM_FT0_EXISTING_DATA_NOTE.md`.

The most relevant priors are:

1. June 3 E9: ~98.9% mean destructive suppression across five modes with 180-degree optimum.
2. June 21 selected 2-path sweeps: strong cosine-law behavior at qualified frequencies.
3. June 21 3-path run: three mutually interfering TX paths on one plate, one RX, full 2-D phase grid, R^2=0.922, with the 2<->3 cross-term ~83% of the strongest pairwise term.
4. Ch-B same-frequency referencing later reduced phase scatter substantially at qualified frequencies.

These are **priors**, not substitutes for fresh later-session/electrical controls.

## 4. Two different scaling questions

FT-3P must not equate internal path count with K_eff.

### 4.1 Dimensional scaling

The original PR #16 target remains:

```
K_eff = independently useful, reproducible held-out output dimension
```

A one-scalar detector can still have K_eff near 1 even if many internal paths contributed.

### 4.2 Relational-computation compression

For P coherent paths:

```
Y = |sum_j a_j|^2
```

contains self-terms plus pairwise cross-terms.

The maximum number of pairwise terms is:

```
P(P-1)/2
```

This is **not** automatically useful computation and **not** automatically independent information.

It is a physical interaction budget.

FT-3P will therefore also track:

```
supported_interaction_terms
relational_tasks_passed
readout_features
receive_channels
adc_conversions
acquisition_window
digital_ops_after_capture
calibration_trials
calibration_bytes
```

The second scaling thesis is:

> **Useful relational work performed before readout grows faster than the receiver/readout burden.**

This can be interesting even if K_eff itself grows slowly.

## 5. Hardware

Use one plate, one RX, and 2-4 independently phase-controlled TX PZTs.

Primary architecture:

```
TX1 --\
TX2 ---\
TX3 ----> fixed plate H ----> one RX ----> Ch A
TX4 ---/
        \
         source references / loopback as available
```

Hold fixed as P increases whenever possible:

- one RX PZT;
- one Ch-A acquisition;
- same sample rate;
- same samples/query;
- same acquisition window;
- same scope range;
- same preprocessing;
- same decision complexity for the primary comparison.

Record commanded phase and amplitude for every TX.

Use Ch B / reference routing to characterize source phase and reject common instrumentation jitter. If all simultaneous electrical references cannot be recorded in one shot, preregister the loopback/reference procedure used to qualify them.

## 6. Measurement correction

Some historical tools used a summed FFT-magnitude statistic and called it "energy."

Fresh FT-3P work should instead save raw waveforms and explicitly distinguish:

- complex demodulated RX voltage/amplitude;
- magnitude;
- squared magnitude / power-like statistic when defined;
- true energy only if the integration/calibration justifies the term.

Do not reuse historical "energy cancellation" wording without defining the quantity.

## 7. FT-3P-1 — frozen two-path prediction

This replaces "prove that two paths interfere."

### Training session A

At a qualified carrier frequency:

1. measure TX-A alone;
2. measure TX-B alone;
3. estimate complex path responses:
   ```
   Y_A = H_A X_A
   Y_B = H_B X_B
   ```
4. freeze all calibration and model parameters.

For simultaneous drive:

```
Y_pred(phi) = Y_A + exp(i phi) Y_B
```

### Held session B

After power-down and preferably later-day restart:

- do not retune phase offsets or thresholds;
- repeat the same phase sweep;
- compare measured complex response with the frozen prediction.

Primary metrics:

- complex normalized RMSE;
- phase error;
- magnitude error;
- destructive-null location shift;
- constructive/destructive contrast;
- coherent-model advantage over incoherent magnitude/power addition.

Advance if the frozen coherent model remains materially predictive and beats the incoherent baseline.

## 8. FT-3P-2 — matched controls

Run the same phase program through:

1. GLASS;
2. source-reference only;
3. ELECTRICAL_ONLY;
4. LOOPBACK;
5. QUIET where relevant.

The goal is not to prove that source phase contains no information—it obviously does.

The goal is to establish whether the **mapping from source relationships to the chosen RX decision variable** depends on the physical H in the claimed way.

Required analysis:

- GLASS transfer response;
- Ch-B/reference response;
- control-path response;
- whether the same threshold/function is reproduced without the plate.

A path-sum compute claim advances only if the GLASS behavior is not explained by the electrical control path.

## 9. FT-3P-3 — frozen relational gate

Use two bits encoded only in relative phase:

```
bit 0 -> phase 0
bit 1 -> phase pi
```

States:

```
00 : (+,+)
01 : (+,-)
10 : (-,+)
11 : (-,-)
```

Target relation:

```
same phase     -> class 1
opposite phase -> class 0
```

Each individual TX maintains constant amplitude.

Therefore the primary scalar RX decision should depend on the **relationship between the two contributions**, not on single-path magnitude.

### Required tests

Score the frozen rule on:

- TX-A alone;
- TX-B alone;
- source references only;
- ELECTRICAL_ONLY;
- GLASS combined response.

Initial engineering target:

```
GLASS held-session balanced accuracy >= 95%
```

while individual-path magnitude and matched electrical-only controls fail the same criterion.

This does **not** claim electronics cannot compute XNOR/parity.

It asks whether H performs the relational physical sum before the receiver.

## 10. FT-3P-4 — freeze the known three-path structure

The historical three-path data already suggest:

```
Y(phi2,phi3)
  ~ b0
  + pair(1,2)
  + pair(1,3)
  + pair(2,3)
```

Fresh test:

### Session A

Fit the 7-term phase-surface model.

Freeze:

- carrier;
- TX amplitudes;
- path gains;
- phase offsets;
- coefficients;
- preprocessing.

### Session B

Measure a new 2-D phase grid without retraining.

Report:

- held-session R^2;
- normalized RMSE;
- persistence of each pairwise term;
- especially the 2<->3 term;
- null-location shift;
- controls.

Advance if the three mutual interactions remain predictive on the later session.

## 11. FT-3P-5 — four-path extension

Only after the three-path frozen test passes.

Use four coherent TX contributions into the same plate.

The ideal linear-interference model contains:

```
C(4,2) = 6
```

pairwise cross-terms.

Do not merely fit a large model and declare success.

Require:

1. training-only coefficient estimation;
2. held-session prediction;
3. support for the expected pairwise phase-difference terms;
4. fixed RX/acquisition budget;
5. matched controls.

Track how many of the six expected interactions are reproducibly supported.

## 12. FT-3P-6 — relational-compute scaling frontier

For:

```
P = 1, 2, 3, 4
```

hold the primary RX budget fixed.

At each P report:

### Physical structure

```
possible_pairwise_terms = P(P-1)/2
supported_interaction_terms
held_model_error
```

### Useful task result

```
relational_tasks_attempted
relational_tasks_passed
best held-session balanced accuracy
abstention/error
```

### Dimensional result

```
K_eff,rank
K_eff,task
```

### Receiver cost

```
receive_channels
adc_conversions
samples/query
acquisition_window
digital_ops_after_capture
calibration_trials
calibration_bytes
system_energy_j when measured
```

The key plots are now two separate frontiers:

```
K_eff vs readout burden
```

and

```
useful relational task/interaction complexity vs readout burden
```

Do not combine them into one metric unless a later preregistered definition is justified.

## 13. What counts as a strong result

### GREEN-A — dimensional scaling

Held-session K_eff rises while a major readout-cost axis stays fixed or grows materially slower.

### GREEN-B — computation compression

K_eff may remain small, but increasing P produces more reproducible relational structure or more useful relational tasks while:

- RX count remains fixed;
- acquisition remains fixed;
- post-capture digital decision complexity remains small;
- calibration burden does not grow proportionally.

GREEN-B is a distinct success mode, not a consolation prize.

### YELLOW

Coherent multipath interference is stable, but useful relational complexity does not increase or requires proportional calibration/readout growth.

### RED

Any of:

- later-session phase surface cannot be predicted without retuning;
- electrical-only controls reproduce the claimed result;
- path coefficients drift enough to require full re-enrollment;
- adding paths produces no additional useful relational structure;
- calibration/readout cost grows as fast as or faster than useful task complexity.

## 14. Why this matters for H design

If GREEN-B survives, future H should be engineered as a **propagation graph**, not just a high-mode-count resonator.

Candidate structures include:

- branches;
- reflectors;
- phase delays;
- coupled resonators;
- scattering junctions;
- phononic boundaries;
- path-length asymmetries.

The design objective becomes:

> Arrange path amplitudes and phases so useful relations constructively interfere and unwanted relations cancel before readout.

That is more specific than "maximize resonance count."

## 15. Data format

Create:

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

Minimum trial fields:

```
trial_id
session_id
path_state
device_id
frequency_hz
active_tx_count
tx1_phase_rad
tx2_phase_rad
tx3_phase_rad
tx4_phase_rad
tx1_command_amp
tx2_command_amp
tx3_command_amp
tx4_command_amp
rx_complex_real
rx_complex_imag
rx_magnitude
target_relation
split
valid
invalid_reason
```

Save raw Ch-A time series and all available electrical reference channels.

## 16. Execution order

Shortest useful path:

```
historical evidence already in repo
    -> frozen later-session 2-path prediction
    -> matched electrical controls
    -> frozen relational gate
    -> frozen 3-path model
    -> 4-path extension
    -> dimensional + relational scaling frontiers
```

Do not spend time re-proving a same-session two-path cosine unless needed as a hardware sanity check.

## 17. Bottom line

The path-sum branch is now testing:

> **Can a stable physical H turn growing internal coherent interaction structure into useful relational computation before a nearly fixed-cost receiver?**

That is the open question the existing lab data actually supports.
