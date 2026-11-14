# Doppler-inspired harmonic-warp replay: FT-0 evidence note

**Date:** 2026-11-14  
**Status:** EXPLORATORY / retrospective transfer-function replay / NOT fresh hardware / NOT preregistered confirmation  
**Branch:** `experiment/holographic-partial-view` (PR #17)

**Reproduce:**

```bash
node tools/doppler_ft0_existing.mjs
```

**Output:** `data/results/doppler/doppler_ft0_20261114.json`

## The question

Could a CWM resonator respond to a structured harmonic input whose frequencies shift together (a **Doppler-inspired frequency warp**), and can that response identify the shift or preserve a useful identity?

**Important distinction:** this is a replay of recorded, frequency-dependent plate responses. No source/receiver was in motion. No continuously accelerated signal was captured, and no three-tone shifted waveform was freshly presented to the plate for this test.

## Data boundary

Historical October FT-1 S1/S2/S3, **181 commanded grid frequencies spaced 500 Hz apart**, 30–120 kHz:

- `data/results/k_eff/FT1-S1/derived/summary.json`
- `data/results/k_eff/FT1-S2/derived/summary.json`
- `data/results/k_eff/FT1-S3/derived/summary.json`

Use S1+S2 arithmetic mean complex transfer H as the frozen digital reference; S3 is the held-out physical transfer-map session.

Conditions are `GLASS`, `LOOPBACK`, `ELECTRICAL_ONLY` on F1 and F2 drive paths. **F1/F2 are different paths into one plate, not two trained standalone responders.**

Model eight nominal fundamentals 31, 32, ..., 38 kHz and five shifts to the fundamental (-1000, -500, 0, +500, +1000 Hz). All harmonic components move together:

```text
[f0, 2 f0, 3 f0]
  -> [f0 + d, 2(f0 + d), 3(f0 + d)]
```

There are 8 bases x 5 offsets x 2 paths = 80 synthesized scenarios **per condition**, not independent physical test trials.

Predict each component using its separately recorded H(f). Candidate digital templates are compared with normalized squared residual after fitting one nuisance complex gain, which discounts a global amplitude/phase shift. This is a matched **digital** search using already digitized transfer measurements, not a measurement of in-glass template selection.

## Results

### Exact replay of the held S3 transfer function

| Condition | Identify shift with true path known (3 harmonics) | Identify path **without** shift compensation | Identify both path and shift by searching all templates |
| --- | ---: | ---: | ---: |
| GLASS | **80/80 (100%)** | **46/80 (57.5%)** | **78/80 (97.5%)** |
| LOOPBACK | 78/80 (97.5%) | 44/80 (55.0%) | 78/80 (97.5%) |
| ELECTRICAL_ONLY | 51/80 (63.8%) | 47/80 (58.8%) | 41/80 (51.3%) |

Chance for five shifts given the path is 20%; chance for the joint path x shift decision is 10%. These chance labels apply to the idealized balanced candidate set, not to arbitrary real-world Doppler tasks.

The striking control result: the **LOOPBACK also predicts the shift nearly perfectly without synthetic noise**. The headline 100% replay result is therefore **not** by itself evidence for a glass-specific computing primitive.

The blind path result is especially instructive: **identity is not naturally invariant to a 500–1000 Hz shift under this fixed-template rule**. Most of the recovery comes from explicitly searching shifted templates in software.

### Response-shape sensitivity

The metric is the square root of normalized complex least-squares residual between three-harmonic response vectors, after fitting a common complex gain. It is a dimensionless shape mismatch (0 = same shape, near 1 = very different).

| Condition | Median S1 -> S3 at same frequency | Median +500 Hz fundamental shift within S3 | Shift mismatch / session mismatch |
| --- | ---: | ---: | ---: |
| GLASS | 0.0878 | **0.8289** | **9.45x** |
| LOOPBACK | 0.00142 | 0.00668 | 4.71x |
| ELECTRICAL_ONLY | 0.1382 | 0.1019 | 0.74x |

Sixteen base/path pairs contribute to each median. They are not statistically independent because they share the same transfer-map sessions and overlapping frequencies.

At the tested offsets, the measured glass transfer response changes *much more* than its median S1-to-S3 shape drift, consistent with a useful physical frequency discriminator. However, large shape response does not establish a superior frequency sensor without a matched conventional baseline and actual detection/error/resource metrics.

### Noise-stress replay (models, not physical repeats)

The script also injects independent Gaussian amplitude and phase jitter into S3's mean H at each harmonic. Fifty pseudo-random perturbations per 80 modeled scenarios = **4,000 synthetic perturbations per condition per noise level**.

| Noise condition | GLASS joint path+shift | LOOPBACK joint path+shift | ELECTRICAL_ONLY joint path+shift |
| --- | ---: | ---: | ---: |
| Modeled from S3's recorded per-frequency CV and phase scatter | 97.5% | 92.4% | 25.2% |
| Matched 0.5% relative amplitude and 0.005 rad phase Gaussian jitter | **97.5%** | **49.4%** | 51.7% |

The controlled perturbation stresses **shape-margin robustness**, not end-to-end system energy or performance under real motion. The equal-noise case is not the measured operating noise of each condition; electronic-only controls had much poorer RX SNR, and this must not be hidden.

### Harmonic count and readout

The replay also compares two versus three harmonic observations and magnitude-only versus complex (phase-inclusive) templates. Three complex components improve modeled resolution, but there is no evidence yet that these responses can be reduced to a cheaper physical output rather than digitizing all three components.

## Critical caveats

1. **No actual Doppler.** This is synthetic *common fractional frequency motion*, which is one aspect of the Doppler effect. No physical relative velocity, time-varying propagation path, or continuously moving transmitter was present.
2. **No demonstrated physical recognition.** Shift selection and label inference are computed by an offline digital search of H templates.
3. **The source already knows the commanded frequency.** A practical sensor benchmark must hide unknown frequency movement from the scorer and compare against available source information, analog frequency discrimination, and efficient digital estimators.
4. **Grid limits.** S1–S3 record command frequencies every 500 Hz. Do **not** extrapolate this model to 5–50 Hz offsets, high-acceleration curves, or fractional shifts without fresh high-resolution measurements.
5. **NCO harmonic mismatch.** Original FT-1 had up to 15–52 Hz mismatch between harmonic frequencies and separately commanded harmonically related grid points. The model uses nominal grid positions. Its simultaneous-harmonic interpretation is therefore only approximate. See `docs/lab_diary_20261027.md` and `docs/lab_diary_20261028.md`.
6. **No new physical captures.** Three-harmonic vectors combine previously **separately measured** transfer points; simultaneous drive/cross-talk, intermodulation, aliasing and settling under a moving query need bench testing.
7. **Not a clean full-system comparison.** Neither analog competitors nor drive energy, detector count, ADC traffic or calibration overhead were measured for this task.
8. **One held session.** S3 is held out computationally, but this retrospective model does not satisfy the forward RR-1 / FT-M multiple-session acceptance gates. FT-1 itself was originally **INCONCLUSIVE**, and stays so.

### Correction to an attractive historical claim

E24, `tools/additional_experiments.py::exp_freq_offset_tolerance`, logged 4/4 rods recognized even at +/-10% offsets. Its candidate scoring compares each **original enrolled query frequency** `freq_nom` to candidate enrollment peaks, rather than comparing the shifted actual query frequency `freq_query`. This makes the purported frequency-tolerance result unsuitable as evidence of physical Doppler/offset robustness. Future use of E24 must explicitly flag this problem; it cannot be used to confirm this hypothesis.

## Decision

**GO (research priority):** a carefully designed *bench* investigation of frequency-shift sensitivity and whether physical harmonic relationships can support a compact score.

**HOLD:** unqualified "Doppler-invariant vibe recognition", "Doppler compute primitive", "more efficient than a digital receiver", or any orbital-compute claim.

**Potential strategic pivot:** the near-term glass response appears more naturally suited to **detecting** frequency motion than automatically ignoring it.

## RR-DOP-1: next fresh experiment (proposal, not a finished preregistration)

1. **Task:** decide between at least two non-identical harmonic query families with an **unknown common shift**; separately estimate shift magnitude/sign. Define how source information and identity are prevented from leaking through the test harness.
2. **Input:** use clock-qualified exact harmonic carrier generation, randomized/interleaved shifts in fine increments (including <500 Hz) over a predeclared region that does not alias. Save the actual applied reference frequency, not merely nominal NCO grid label.
3. **Physical test:** present simultaneous three-tone packets to the plate, then a time-varying frequency-warp packet. Include GLASS, LOOPBACK, ELECTRICAL_ONLY, QUIET, alternate source orientation and fixed template controls.
4. **Held sessions:** freeze the physical configuration, templates, score and any allowed calibration before at least three later sessions including a power cycle. Report plate/fixture temperature and mode drift.
5. **Baselines:** source-only, conventional analog bandpass / heterodyne / resonator bank, fair digital frequency estimator or matched-filter bank, and full H readout.
6. **Primary outputs:** blind identity accuracy, shift-estimation error in Hz, false positives, coverage, class margins, temperature drift, and confidence intervals grouped by independent session.
7. **Cost boundary:** include TX/reference/control/readout, actual ADC sample rate and bit depth, latency, energy per eligible decision and calibration overhead. A compact physical compatibility score must be **measured**, not inferred by offline FFT.
8. **Go/kill:** reject a glass-specific advantage if electrical/loopback/conventional analog processing matches the qualified task under the same conditions, or if claimed compact readout still requires hidden full-band acquisition. A good passive frequency sensor alone may still merit separate publication.
9. **External escalation:** remain E0/E1 until the existing `docs/EXTERNAL_STRATEGIC_ESCALATION_GATE.md` demands are met.

**Next action:** freeze a detailed RR-DOP-1 acquisition plan before physically testing it. The retrospective replay alone does not justify selecting a pass/fail threshold from post hoc performance.
