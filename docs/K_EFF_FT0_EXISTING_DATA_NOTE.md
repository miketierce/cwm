# FT-0 Existing-Data Note: Stronger K_eff Outcome Hypothesis

**Status:** retrospective / hypothesis-forming only  
**Purpose:** use committed measurements to sharpen the fast-track hypothesis before new hardware capture.

This note does not upgrade any CWM claim. The existing datasets lack the complete held-session + Ch B + electrical-only structure required by PR #16.

## 1. Existing measurements that matter

### A. Four-output H matrix: full geometric rank, low effective rank

`data/results/h_matrix/multi_plate_enrollment_20260603_171950.json` contains a measured 27 x 4 response matrix from 27 selected frequencies across four plate/position channels.

Saved SVD:

- singular values: 14.355M, 3.099M, 2.368M, 1.508M
- condition number: 9.52
- entropy effective rank: 1.418
- geometric rank: 4

Interpretation: more than one independent direction is measurable, but the response is strongly dominated by the first direction. Raw channel count or geometric rank therefore overstates useful dimensionality.

### B. Physical three-tone Pong capture preserves a high-dimensional response

`data/results/pong/pong_multitone_data_20260620_225626.npz` is a real-hardware capture (`dry_run=false` in the paired model file). It contains 256 states, three simultaneously encoded drive-frequency variables, and 42 saved response features: 30 mode amplitudes, three direct-drive amplitudes, and nine intermodulation/harmonic features.

A retrospective standardized covariance analysis of the saved feature matrix gives these **same-session representation upper bounds**:

| feature set | entropy effective rank | stable rank | components for 90% variance |
|---|---:|---:|---:|
| 30 mode amplitudes | 21.98 | 4.55 | 24 |
| 9 intermod/harmonic features | 7.51 | 3.75 | 7 |
| all 42 features | 29.00 | 5.39 | 31 |

These are not held-session `K_eff` values. They show only that the measured response occupies more than one covariance dimension in this session.

### C. Eight simultaneous binary components were highly distinguishable in the April calibration

`data/results/lab/plate_exps/esn_v4_L2_20260413_221433.json` is especially relevant to the fixed-budget question.

The acquisition drove eight modal frequencies simultaneously with binary ON/OFF amplitudes, measured one Ch-A receive path, extracted the same eight readout frequencies from one capture, and saved all 256 possible 8-bit patterns with six physical repetitions per pattern. Each repetition used the same capture length and receiver hardware regardless of how many bits were ON.

A retrospective four-fold **held-token-combination** test was performed. Thresholds for each bit were fit from training token combinations only, using that bit's corresponding measured output-frequency amplitude, then scored on physical repetitions of unseen token combinations.

| plate | mean bit accuracy | exact 8-bit token accuracy | held physical rep predictions |
|---|---:|---:|---:|
| D | 100.000% | 100.000% | 1,536 |
| E | 99.951% | 99.674% | 1,536 |

This is our strongest existing evidence that the bench can preserve **at least eight simultaneously multiplexed binary distinctions in one fixed receiver acquisition** within a session.

However, it is **not yet evidence that the glass contributes eight useful computational dimensions**. Ch B was disabled in this historical experiment, and the presence/absence of each input tone is itself an easy-to-read property of the source spectrum. An electrical-only frequency analyzer could plausibly solve the same identity task.

So the result strengthens the instrumentation hypothesis while sharpening the control requirement:

> **The bench can already carry an 8-way binary multiplexed alphabet at fixed acquisition cost; FT-1/FT-3 must determine how many useful output distinctions are added by H beyond what the input/electrical reference already contains.**

The original acquisition used `N_SAMPLES=8064`, `SAMPLE_RATE=781250 Hz`, and four averaged FFT captures per saved repetition. Those acquisition settings were fixed across the 256 binary patterns.

### D. Task-useful dimension is much smaller than covariance rank

A retrospective four-fold linear-ridge decode was run against the same saved NPZ, using the **30 mode amplitudes only** to recover the three simultaneously encoded drive-frequency variables.

| encoded variable | levels | CV R^2 | nearest-level accuracy | naive chance |
|---|---:|---:|---:|---:|
| input 1 | 8 | -0.230 | 15.6% | 12.5% |
| input 2 | 8 | 0.136 | 16.4% | 12.5% |
| input 3 | 4 | 0.715 | 61.3% | 25.0% |
| all three exactly | 8 x 8 x 4 | -- | 2.0% | 0.39% |

Adding the saved intermodulation/harmonic features did not materially rescue inputs 1 or 2 with this simple decoder.

This is the most important FT-0 observation:

> **A response matrix can have high apparent representation rank while supporting only about one strongly recoverable task direction for a particular encoding/readout.**

That is why PR #16 must track both `K_eff,rank` and `K_eff,task`.

### E. The physical three-tone task showed only a modest same-session gain

The paired real-hardware model `pong_model_multitone_20260620_225626.json` reports:

- modes-only intercept: 58.2%
- all-features intercept: 62.9%
- stationary baseline: 56.25%
- random baseline: 37.61%

This is not a strong compute result. It is consistent with the decode above: the three-tone response contains structure, but the chosen task/encoding did not turn most of that structure into useful independent information.

### F. Dense simultaneous excitation is already physically feasible

The lab record includes a broadband experiment driving **3,793 tones simultaneously** over 200-95,000 Hz in one acquisition strategy. That demonstrates that highly multiplexed excitation/capture is physically feasible on the bench. It does **not** establish thousands of useful dimensions.

For the fast track, this means FT-3 is an instrumentation-feasible question rather than a speculative future setup.

### G. Existing multi-tone interaction warns against assuming independence

The lab record also reports a strong multi-tone interaction: a mode response recorded around 4.6M when driven alone fell to about 0.766M with seven other tones active.

Regardless of mechanism, that observation says the useful scaling hypothesis should not assume `K_eff = number of driven tones`. Dense tone count may eventually reduce separability.

### H. Existing recall data suggest redundancy, but are not clean K_eff evidence

`data/results/pong/recall_enroll_20260629_120542.npz` and the saved offline reanalysis use a 240-feature representation with 212 modal features.

The saved reanalysis reports graceful random mode dropout:

- 0% dropout: 87.97%
- 50% dropout: 85.08%
- 90% dropout: 82.50%
- 95% dropout: 82.11%

and a random-feature readout curve:

- 8 features: 51.64%
- 16 features: 59.30%
- 32 features: 65.55%
- 64 features: 73.83%

However, prior audit work identified normalization/reference choices that can materially inflate modes-only recall. Therefore this dataset should guide FT-2 ablations, not serve as proof that K_eff already scales.

## 2. Stronger outcome hypothesis

The existing data argue against the naive hypothesis that every additional simultaneous tone contributes another useful independent dimension.

A better hypothesis is:

> **For a fixed TX/RX and fixed acquisition budget, a sparse query set selected to excite independent directions of the measured transfer function will show an initial regime in which held-session task-useful dimensionality increases with simultaneous query dimension while receiver cost remains approximately fixed, followed by saturation as modal correlation/inter-tone interaction dominates.**

In other words: `N inputs: 1 -> 2 -> 4 -> 8 -> ...`; `K_eff,task`: rises initially, then saturates; RX channels, ADC samples, and acquisition window remain fixed for the primary comparison.

The useful result is the **initial fixed-cost growth regime**. Infinite linear scaling is not required.

## 3. Why query selection is now central

The June 20 raw capture says the physical response has many covariance dimensions but the original three-axis frequency encoding did not align two of its three task variables with easily recoverable mode-space directions.

Therefore FT-1/FT-2 should not choose tones only because they are strong resonances.

Candidate queries should maximize a training-only criterion such as:

- high repeatability;
- high Ch A / Ch B transfer stability;
- low pairwise response correlation;
- large training separation;
- low electrical-only separability.

The goal is to choose **orthogonal/usefully distinct questions**, not merely loud questions.

## 4. Sharper preregistered near-term test

### H-A: representation

Using training sessions only, select 2-4 queries whose GLASS response vectors are weakly correlated and stable. On a later held session require `K_eff,rank > 1`, GLASS effective/stable rank materially above ELECTRICAL_ONLY, and no clipping/reference failure.

### H-B: useful parallel task dimension

Construct 1-, 2-, and 4-component query conditions using the selected queries. Keep one RX PZT, one Ch A/Ch B acquisition, sample rate, sample count, and acquisition window fixed.

Require at least **two independently decodable binary distinctions** in the N=4 condition using a frozen simple readout. Initial engineering target: each binary distinction >=95% held-session balanced accuracy while Ch B-only / ELECTRICAL_ONLY fail the same criterion.

### H-C: fixed-cost growth

Advance the scaling thesis if `K_eff,task(N=4) > K_eff,task(N=1)` while receive-channel count is unchanged and ADC samples/query and acquisition window remain approximately fixed, and the gain survives the later-session freeze.

### H-D: saturation is acceptable

If N=8 adds little or harms performance because of interaction/correlation, record the saturation point. A measured optimum such as N*=4 would still be useful if one fixed physical acquisition performs several reliable distinctions in parallel.

## 5. What FT-0 can and cannot tell us

The committed raw/vector data are sufficient to justify this expectation:

> **CWM likely has multiple measurable physical response dimensions, but useful dimensions depend strongly on encoding/readout alignment and may saturate well below raw mode count.**

They are not sufficient to establish held-session K_eff, K_eff versus Ch B, fixed-budget scaling, cross-device scaling, or end-to-end energy advantage. Those require FT-1 through FT-6.

## 6. Reproducibility

`tools/k_eff_ft0_existing.py` reproduces the retrospective rank and three-input linear-decode diagnostics from the June 20 physical multitone NPZ.

The script intentionally labels the result hypothesis-forming and does not emit a validated K_eff claim.
