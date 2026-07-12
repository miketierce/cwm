# Distributed-Mode Hardware Validation Worklist

**Prepared:** 2026-07-11
**Target:** Next session with the CWM array, NCO, and PicoScope connected
**Primary question:** Does the distributed modal code remain useful when failures and incomplete queries are physical rather than software masks?

---

## 1. Claim Boundary

The saved June 29 enrollment supports three offline findings:

1. Modal features carry information not present in the four direct readout bins.
2. Software removal of up to 90% of modal features produces graceful degradation.
3. Eleven overlapping random 64-mode banks recover 11-15 percentage points over one random 64-mode bank under 0-90% software mode masking.

Those results do **not** yet establish:

- tolerance to a physically disconnected receiver;
- completion of information physically absent from the drive query;
- cross-session transfer without re-enrollment;
- an energy or latency advantage for the software ensemble;
- literal holographic storage; or
- the behavior of an engineered phononic band-gap structure.

This worklist tests the first three boundaries and measures the fourth. A band-gap device requires a separate elastic-wave/FEM design program.

---

## 2. Hardware Configuration to Freeze

Use the June 28/29 array unless a deviation is documented in the session manifest:

- 15 NCO TX channels, F1-F15;
- Plate A -> amplifier -> Plate B cascade on F1-F4;
- Plate C on F5-F8;
- small plates on F9-F15;
- PicoScope Ch A = summed RX bus through the working preamp;
- PicoScope Ch B = summed NCO drive reference;
- one 4.7 kOhm summing resistor per Ch-A RX branch;
- fixed June 29 readout frequencies from `recall_enroll_20260629_120542.npz`.

### Critical inventory discrepancy

The current repository disagrees about the number of Ch-A RX branches:

- `direct_wire_census.py` prints seven RX PZTs;
- the June 28 topology and June 29 diary imply six Ch-A branches (B-G), with Plate A's three RX PZTs feeding the cascade amplifier instead;
- the June 29 diary explicitly says `6 x 4.7k summing`.

Do not hard-code seven. At session start, label every physical Ch-A summing branch `R1...RN`, record its plate/PZT, and use the observed count `N` in all conditions.

---

## 3. Frozen Analysis Protocol

Freeze these choices before seeing new results.

| Item | Frozen choice |
| --- | --- |
| Historical enrollment | `data/results/pong/recall_enroll_20260629_120542.npz` |
| Historical census | `data/results/direct_wire_census/direct_wire_census_20260628_220731.json` |
| Frequency grid | 212 unique frequencies stored in the historical enrollment |
| Validation | Leave one explicit repeat out; never infer repeat from row order in new captures |
| Normalization | Per-capture mean normalization, then training-fold standardization |
| Primary output | Landing accuracy within +/-1 row (`padh // 2`) |
| Secondary outputs | Exact landing, exact state, calibration gap, Ch-A SNR, Ch-B drive level |
| Ensemble | 11 overlapping random banks, 64 modes per bank, seed `20260711` |
| Comparators | Full surviving bank, one random 64-mode bank, contiguous banks, disjoint random banks, direct driven bins |
| No tuning rule | Do not select banks, frequencies, thresholds, or normalization from test conditions |

### Reference controls

| Control | Exact landing | Tolerant landing |
| --- | ---: | ---: |
| Constant-label baseline | 14.5% | 42.6% |
| Bayes optimum from physical `x+y` only | 65.6% | 87.5% |
| Bayes optimum from `x+y+vx` only | 69.5% | 87.5% |
| Bayes optimum from `x+y+vy` only | 65.6% | 87.5% |
| June 29 modes-only full-bank replay | 65.4% | 94.1% |
| June 29 modes-only 64-mode ensemble | 55.8% | 90.5% |

The visible-variable Bayes values are controls, not device targets. If an omitted-variable query exceeds its information ceiling after a long `Foff` flush and randomized order, first suspect residual drive, order leakage, or a decoder bug.

---

## 4. Software Preparation Before the Bench

Complete these tasks without hardware so bench time is used only for capture.

- [ ] Create `data/config/distributed_mode_validation_v1.json` containing:
  - the 212 fixed frequencies in Hz;
  - the 11 fixed 64-mode banks as frequency lists;
  - contiguous and disjoint comparator banks;
  - a deterministic 64-state panel with 8 states per landing class and balanced `vx/vy` where possible;
  - randomized state order for each repeat;
  - attenuation conditions and receiver-mask labels.
- [ ] Add a dual-channel capture harness, proposed name `tools/recall_hardware_validation.py`.
- [ ] Add a cross-condition analyzer, proposed name `tools/physical_dropout_analyze.py`.
- [ ] Dry-run both tools against the June 29 NPZ and verify that the unchanged condition reproduces the existing metrics.
- [ ] Print a one-page bench sheet with receiver labels, condition order, and checkboxes.

### Required capture schema

Each saved NPZ/JSON pair must contain:

```text
X_rx                 fixed-frequency Ch-A features
X_ref                Ch-B reference features at every driven tone
state_id             0..255
x, y, vx, vy, landing
repeat_id            explicit, independent of row order
condition_id
rx_mask              connected R labels
drive_scale_db       one value per axis
omitted_axes
freqs_hz
capture_timestamp_s
noise_floor_rx
noise_floor_ref
navg, settle_s, foff_flush_s
git_commit, git_dirty
hardware_manifest_path
```

Save the averaged Ch-A and Ch-B spectra when storage permits. Fixed-bin features alone are insufficient to diagnose an unexpected frequency shift after a physical intervention.

---

## 5. Session Order

| Order | ID | Priority | Experiment | Approx. bench time |
| ---: | --- | --- | --- | ---: |
| 1 | DV-00 | Must | Inventory, photograph, and freeze topology | 15 min |
| 2 | DV-01 | Must | Bring-up verification and fresh census | 35-45 min |
| 3 | DV-02 | Must | Cross-session full enrollment | 15-25 min |
| 4 | DV-03 | Must | Physical RX dropout | 45-75 min |
| 5 | DV-04 | Must analysis | Frozen overlapping-bank evaluation | No extra capture |
| 6 | DV-05 | High | Physical drive attenuation | 20-30 min |
| 7 | DV-06 | Must | Physically omitted query axes | 20-30 min |
| 8 | DV-07 | Must | Restore all RX and recapture baseline panel | 10 min |
| 9 | DV-08 | Optional | One-hour restored-topology soak | 60 min unattended |

Core session: about 3 hours. DV-08 can run unattended after all topology changes are complete.

---

## 6. Detailed Protocols

### DV-00: Hardware Inventory and Manifest

**Purpose:** Make every intervention reversible and remove the six-versus-seven receiver ambiguity.

**Procedure**

1. Power down or issue `Foff` before touching the summing bus.
2. Label each Ch-A branch `R1...RN` at its 4.7 kOhm summing resistor.
3. Record plate, PZT location, wire color, and measured resistance to the summing node.
4. Photograph the full array, Ch-A summing bus, Ch-B reference tap, and cascade gain resistors.
5. Record whether each cascade `Rg2` is 10 kOhm linear or 1 kOhm clip configuration.
6. Record battery voltages, preamp gain setting, PicoScope ranges, NCO firmware/status string, ambient temperature, and serial port.
7. Store as `data/results/distributed_mode_hw/<session>/hardware_manifest.json`.

**Gate:** Do not continue until every branch can be removed and restored unambiguously.

---

### DV-01: Bring-Up and Fresh Census

**Purpose:** Confirm that the new session starts from a state comparable to June 29.

**Commands**

```bash
python3 tools/cascade_verify.py --quick

python3 tools/direct_wire_census.py \
  --start 30000 --stop 350000 --step 500 --navg 8 \
  --tx F1,F2,F3,F4,F5,F6,F7,F8,F9,F10,F11,F12,F13,F14,F15 \
  --force --keep-collisions --repeat-passes 2
```

**Record**

- per-channel Ch-B drive SNR;
- per-channel Ch-A RX SNR;
- Block-B phase modulation;
- detected mode count and unique fixed-grid coverage;
- mode repeatability;
- Ch-A/Ch-B noise floors.

**Go/no-go**

- GO: all 15 TX channels report `OK`, median repeatability >= 0.90, and at least 180 of the 212 historical frequencies remain above the registered SNR threshold.
- CONDITIONAL: one non-axis TX channel is weak but F1, F2, F4, F5 and every RX branch pass. Continue but mark the session degraded.
- STOP: any state-encoding channel F1/F2/F4/F5 fails, the Ch-B reference is absent, or the restored RX bus cannot reproduce its baseline response.

The 180-frequency threshold is a comparability gate, not a claim threshold. If the spectrum has shifted rather than disappeared, save raw spectra before changing hardware.

---

### DV-02: Cross-Session Full Enrollment

**Purpose:** Determine whether June 29 templates transfer to a new session without re-enrollment.

**Capture**

- all RX branches connected;
- all four axes physically driven;
- fixed historical frequency grid;
- 256 states x 5 repeats;
- `navg=24`, `settle=0.04 s`;
- randomize state order separately inside each repeat;
- save explicit repeat IDs and Ch-B reference measurements.

Fallback capture command if the new harness is not ready:

```bash
python3 tools/recall_enroll_save.py \
  --repeats 5 --navg 24 --settle 0.04 \
  --census data/results/direct_wire_census/direct_wire_census_20260628_220731.json
```

The fallback lacks Ch-B capture and randomized ordering, so label it as compatibility-only.

**Analyses**

1. New-session leave-one-repeat-out recall.
2. June-29 templates -> new-session queries with no labeled recalibration.
3. June-29 templates -> new queries after only per-capture normalization.
4. New-session templates -> June-29 queries to test directionality.

**Decision bands for tolerant landing**

- GREEN cross-session transfer: >=80% and no more than 10 points below new-session re-enrollment.
- YELLOW: 60-79% or a 10-25 point calibration gap.
- RED: <=55% or more than a 25 point calibration gap.

If within-session recall is high but transfer is red, describe the system as enrollment-dependent, not session-stable.

---

### DV-03: Physical RX Dropout

**Purpose:** Test whether a fixed full-topology enrollment survives actual receiver-branch failures.

**Primary rule:** Analyze every fault condition against the untouched DV-02 templates first. Re-enrollment under the faulted topology is a secondary diagnostic.

**State panel**

- frozen 64-state panel;
- 3 repeats per condition;
- `navg=16`;
- same randomized order seed across conditions;
- all four drive axes present.

**Condition sequence**

1. `ALL_START`
2. Leave-one-out conditions `LOO_R1...LOO_RN`, in randomized branch order.
3. Insert an `ALL_CHECK` condition after every two or three manual changes.
4. Nested masks preserving plate/band diversity:
   - `NESTED_N_MINUS_2`
   - `NESTED_HALF`
   - `NESTED_ONE`
5. `ALL_END`

For expected `N=6`, the nested sequence is 6 -> 4 -> 3 -> 1. If the inventory finds a different `N`, preserve approximately the same fractions.

**At every manual change**

1. Stop capture and issue `Foff`.
2. Disconnect at the labeled summing resistor; do not remove or move the PZT.
3. Verify continuity for connected branches and open circuit for removed branches.
4. Capture a 10-second no-drive baseline.
5. Capture the state panel.
6. Restore only according to the preregistered condition list.

**Analyses**

- fixed full-topology templates -> faulted queries (primary fault-tolerance result);
- within-condition templates -> held-out repeat (recalibrated capacity);
- full bank, frozen ensemble, single bank, contiguous, disjoint, direct-bin baseline;
- fixed-frequency coverage, spectral shift, Ch-A SNR, and Ch-B stability;
- leave-one-out contribution by physical receiver branch.

**Success criteria**

- Worst leave-one-out condition loses <10 tolerant-accuracy points from `ALL_START`.
- `NESTED_HALF` retains >=80% of `ALL_START` tolerant accuracy with fixed templates.
- Frozen ensemble beats the mean single 64-mode bank by >=8 points at two or more physical fault levels.
- `ALL_END` returns within 5 points of `ALL_START`.

**Interpretation rules**

- Fixed-template pass = physical fault tolerance.
- Fixed-template fail but within-condition pass = recalibratable sensing, not fault tolerance.
- Both fail = the physical intervention destroyed useful state information or changed loading too strongly.
- `ALL_END` failure = session drift or an unrecovered wiring change; do not attribute intervening differences solely to dropout.

---

### DV-04: Frozen Overlapping-Bank Evaluation

**Purpose:** Validate the positive offline ensemble result under physical faults.

This requires no additional capture. Apply the frozen banks to DV-02 and DV-03.

**Primary comparisons**

1. Eleven overlapping random 64-mode banks vs one random 64-mode bank.
2. Overlapping banks vs contiguous and disjoint banks with equal per-bank feature budgets.
3. Ensemble vs full surviving bank.
4. Ensemble mode-read budget, wall-clock decoder time, and estimated ADC/FFT cost.

**Falsifier:** If the overlapping vote does not beat a single equal-budget bank by 8 points under any physical fault level, the offline gain does not transfer and the ensemble architecture should not be prioritized.

**Important limit:** A software vote is not plate-native voting. Report its digital operations and energy separately from acoustic propagation.

---

### DV-05: Physical Drive Attenuation

**Purpose:** Replace synthetic feature-space noise with controlled reduction of the actual acoustic query.

**Conditions**

- all axes at calibrated baseline;
- all axes scaled by -3, -6, and -12 dB in fundamental amplitude;
- each axis individually scaled by -6 and -12 dB while the others remain at baseline;
- restore baseline after every four attenuation conditions.

Use the measured NCO duty-cycle law rather than multiplying duty directly:

$$
d' = \frac{1000}{\pi}\arcsin\left(a\sin\left(\pi d/1000\right)\right),
$$

where $a=10^{\mathrm{dB}/20}$ and $d$ is the original permille duty setting. Respect the firmware minimum duty and log clipping.

**Capture**

- frozen 64-state panel x 3 repeats;
- all RX branches connected;
- Ch B enabled and saved for every query;
- random state order;
- fixed DV-02 templates for primary analysis.

**Success criteria**

- Ch B confirms requested amplitude within +/-1 dB.
- At -6 dB common attenuation, the ensemble retains >=80% of baseline tolerant accuracy.
- Any claimed glass advantage is compared with direct driven bins and a dimension-matched digital baseline.

Do not add synthetic standardized-space noise to the primary physical-attenuation result.

---

### DV-06: Physically Omitted Query Variables

**Purpose:** Determine whether the earlier software-masked result was readout completion or genuine completion of physically absent drive information.

**Conditions**

1. `FULL_QUERY`: x, y, vx, vy driven.
2. `OMIT_VX`: x, y, vy driven; F1 off.
3. `OMIT_VY`: x, y, vx driven; F2 off.
4. `OMIT_VX_VY`: x, y driven; F1 and F2 off.
5. Optional severe controls: `X_ONLY` and `Y_ONLY`.

**Leakage controls**

- issue `Foff` for at least 100 ms before every omitted-axis query;
- randomize state order independently for each repeat;
- verify omitted carriers are absent on Ch B;
- run a short-flush secondary condition only to measure residual-ringdown/order leakage;
- never use the omitted true variables in normalization, bank selection, or decoder calibration.

**Analyses**

- fixed full-state templates -> physically partial queries;
- visible-variable Bayes classifier;
- direct-bin, full modal, and overlapping-bank decoders;
- prediction entropy over the full-state templates, not only top-1 accuracy.

**Interpretation**

- Meeting the visible-variable Bayes optimum shows the device preserves all information physically supplied.
- Falling below it measures representation mismatch caused by missing drives.
- Exceeding the Bayes ceiling after a long flush is not immediately a success; investigate residual carriers, sequence leakage, duplicated captures, or persistent physical state.
- Unless a persistent writable state is independently demonstrated, do not say the passive plate reconstructed a velocity that was never supplied.

This experiment is a claim-clarification gate even if the result is negative.

---

### DV-07: Restore and End-of-Session Baseline

**Purpose:** Prove reversibility of the manual fault interventions and measure session drift.

1. Restore all RX branches using the DV-00 manifest and continuity measurements.
2. Confirm the same Ch-A summing resistance and Ch-B reference level.
3. Run `cascade_verify.py --quick`.
4. Recapture the frozen 64-state panel x 3 repeats at baseline drive.
5. Compare `ALL_START`, all inserted `ALL_CHECK` captures, and `ALL_END`.

**Pass:** `ALL_END` is within 5 tolerant-accuracy points, 3 dB median mode magnitude, and 10% mode coverage of `ALL_START`.

If this fails, flag all condition effects as confounded until the wiring or drift source is resolved.

---

### DV-08: Optional Restored-Topology Soak

**Purpose:** Check whether the cross-session/physical-fault decoder remains stable after a session of rewiring.

- all RX restored;
- no synthetic query noise;
- 60 minutes;
- frozen 64-state panel sampled repeatedly;
- log full-bank, ensemble, single-bank, direct-bin accuracy, Ch-A noise, Ch-B drive, and temperature every minute.

This replaces the earlier noise-injected soak with a physically grounded stability trace.

---

## 7. Result Matrix and Decisions

| Observation | Conclusion | Next action |
| --- | --- | --- |
| Cross-session transfer passes; physical dropout passes; ensemble gain persists | Strong support for distributed-mode, fault-tolerant CAM readout | Repeat on another day and another physical array |
| Within-session passes; cross-session transfer fails | Enrollment-dependent physical feature map | Develop calibration/alignment before applications |
| Fixed templates fail under RX dropout; re-enrollment succeeds | Topology is recalibratable but not fault tolerant | Drop fault-tolerance claim; study fast recalibration |
| Full bank survives but ensemble gain disappears | Distributed code is useful; overlapping voting is not | Use full-bank decoder or redesign bank allocation |
| Random overlapping banks beat contiguous/disjoint under physical faults | Coupled distributed architecture favored | Optimize bank size/voter count on a separate validation session |
| Physical omission reaches only visible-variable Bayes limit | Readout completion, not missing-input reconstruction | State claim precisely; pursue writable/persistent memory separately |
| Physical omission exceeds Bayes after long flush | Possible persistence or leakage | Repeat with blinded order, longer flush, carrier monitor, and independent script |
| Restored baseline does not recover | Hardware drift/intervention confound | Repair and repeat before publishing fault curves |

---

## 8. Minimum Publishable Package

Do not update public claims until all items below exist:

- [ ] Hardware manifest with labeled RX branches and photographs.
- [ ] Fresh census and verification JSON.
- [ ] Full cross-session enrollment NPZ with Ch-B reference.
- [ ] Physical RX dropout NPZ/JSON and restored-baseline control.
- [ ] Physical attenuation NPZ/JSON.
- [ ] Physical omitted-query NPZ/JSON with long-flush control.
- [ ] Frozen-bank configuration file.
- [ ] Analysis script and machine-readable result JSON.
- [ ] Figure: accuracy vs connected RX fraction.
- [ ] Figure: ensemble vs full/single/contiguous/disjoint under physical faults.
- [ ] Figure: cross-session calibration gap.
- [ ] Figure: physical query omission vs visible-variable Bayes control.
- [ ] Claim ledger update separating offline masking, physical sensor failure, and physical input omission.

---

## 9. Explicitly Deferred

The following should not consume this hardware session:

- digital mode masking alone (already completed offline);
- more additive standardized-feature noise sweeps;
- NARMA reruns on the unchanged d3 data;
- claims about engineered band gaps from frequency-bin deletion or statistical orthogonalization;
- bank-size optimization on the same physical-fault session used for evaluation.

After the frozen experiment passes, use a separate session to optimize bank size, voter count, plate topology, and receiver placement. Keep optimization and validation data separate.