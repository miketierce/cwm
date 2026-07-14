# Written Template Bank: Informed Simulation Results

**Status:** DATA-CALIBRATED SENSITIVITY STUDY. These are not rewrite-cycle measurements or template-bank evidence.

## Stronger Hypothesis

> The E3 mass patterns can support a direct multitone energy matcher, but exact-peak queries and rewrite states are stability-limited. A robustness-optimized query may tolerate about 100 Hz frequency jitter, while the strict rewrite gate still requires roughly 2.5% response variability and a 2-4x reduction of the E3 endpoint-drift proxy. Stability control matters more immediately than template count.

The suite tests six parts of that hypothesis: E3/Rayleigh consistency, direct-energy replay, rewrite feasibility, uncertainty-robust site placement, multi-cell/readout confounding, and independent sample requirements.

## 1. E3 Drift and Rayleigh Audit

After linear interpolation between the two bare captures, 2 of 15 stable-channel shifts remain more than +50 Hz, and 0 remain more than +150 Hz. Pure point-mass Rayleigh loading predicts non-positive shifts for an isolated correctly tracked mode.

After requiring the simply-supported mode frequency to lie within 30% of the measured channel, the best sin-squared fit has median R2 about zero of 0.828; 5 of 5 channels exceed R2=0.5. Unconstrained fits are much more optimistic because they can select frequency-incompatible modes. With only three sites, several assignments remain ambiguous.

**Interpretation:** E3 is compatible with low-order 2D Rayleigh sensitivity after a broad frequency constraint, but three sites cannot identify the mode map or test out-of-sample prediction. Mode tracking, fixture disturbance, and drift remain live alternatives. New sites must be treated as model-validation data, not merely more training points.

## 2. Measured-Curve Direct Match

The NW channel supplies three prospectively usable bands (56, 86, and 91 kHz). Using each E3 pattern's measured peak frequencies as its three-tone query gives:

```text
[[321.2  86.1  83. ]
 [  4.1 110.4  20.1]
 [ 54.8  54.7 269.4]]
```

The unsmoothed measured matrix is diagonal in the one-pass replay: row accuracy 100.0%, column accuracy 100.0%, and diagonal/off-diagonal mean ratio 4.63. Smoothed curves are used only for robustness simulation.

This is optimistic because query frequencies and response curves came from the same capture. Monte Carlo replay with 25% power-gain CV gives these largest **total per-band** rewrite-jitter SD values that retain at least 80% gain-calibrated bank accuracy. The model decomposes each value into a common cell shift plus an independent per-band term at half that common SD:

| Query design | Maximum total per-band jitter SD at >=80% |
| --- | ---: |
| exact_peak | 28 Hz |
| peak_comb_25hz | 28 Hz |
| robust_optimized_50hz | 112 Hz |

Exact-peak and +/-25 Hz comb simulations use unsmoothed measured curves. The robustness-optimized design uses the same 1.41-bin Gaussian blur used during its 50 Hz design-jitter optimization. Its apparent advantage is therefore a proposal to validate on frozen independent rewrites, not a fair measured win over the other queries.

The optimized query frequencies proposed for a 50 Hz design-jitter model are:

```text
[[56250. 87900. 91000.]
 [55250. 88250. 91900.]
 [56600. 88950. 90800.]]
```

These frequencies are a preregistration candidate for independent rewrites, not a measured improvement.

## 3. Rewrite Feasibility Envelope

At the scenario labeled current proxy (50 mg, full E3 endpoint-drift proxy, 10% placement CV), median separation ratio is 1.21, mean leave-one-out accuracy is 99.4%, and TB-G2 pass probability is 0.0%.
At 75 mg with the drift proxy halved and 10% placement CV, median ratio is 1.61, mean accuracy is 99.9%, and pass probability is 0.0%.

Because E3 contains no rewrite repeats, these probabilities are sensitivity envelopes. The most useful output is which combination of mass, drift reduction, and placement CV crosses the gate, not the probability itself.

Scenarios reaching at least 80% simulated TB-G2 pass probability:

| Drift proxy retained | Response CV | Minimum mass |
| ---: | ---: | ---: |
| 10.0% | 1.0% | 25 mg |
| 10.0% | 2.5% | 25 mg |
| 25.0% | 1.0% | 50 mg |
| 25.0% | 2.5% | 50 mg |
| 50.0% | 1.0% | 75 mg |
| 50.0% | 2.5% | 75 mg |
| 75.0% | 1.0% | 100 mg |
| 75.0% | 2.5% | 100 mg |

No tested scenario with response CV of 5% or greater reaches an 80% gate probability, even at 100 mg. This response-CV parameter is independent per mode and is not a millimeter placement error; the separate site-layout model propagates spatially correlated position jitter. In this envelope, repeatable response is the harder constraint than mass.

## 4. Site-Layout Ensemble

The theoretical search evaluated 5000 four-site layouts against four unresolved low-order mode assignments and six equal-mass two-of-four codewords. The regular corner-grid score is 0.00 noise-standardized distance.

Top proposed layout:

```text
{
  "positions_mm": [
    [
      13.110912464188,
      12.211998435602345
    ],
    [
      13.694361255653059,
      16.57962318009659
    ],
    [
      19.446481984252685,
      3.8944942179784072
    ],
    [
      3.064791141516068,
      19.221558047187063
    ]
  ],
  "worst_assignment_nominal_min_distance_sigma": 5.18014854844126,
  "placement_jitter_0_5mm_p10_min_distance_sigma": 3.1946909441125064,
  "placement_jitter_0_5mm_median_min_distance_sigma": 4.372092732545715
}
```

Placement tolerance for that candidate:

| Placement SD | P10 distance | Probability distance >=3 SD |
| ---: | ---: | ---: |
| 0.10 mm | 4.52 | 100.0% |
| 0.25 mm | 3.71 | 100.0% |
| 0.50 mm | 3.31 | 98.0% |
| 1.00 mm | 1.97 | 62.8% |

This layout is low-confidence because the simple Rayleigh model is weakly calibrated. Its role is to choose informative TB-11 measurement sites, not to define a final codebook.

## 5. Multi-Cell and Receiver Confound

In the historical Plate I/H enrollment, the mean standardized cross-plate receiver distance divided by the within-plate different-receiver distance is 0.864 over all sweep points and 0.886 over detected modes.

A ratio below one means receiver-position/topology differences were at least as large as cross-plate differences in that capture. The archive therefore cannot supply a clean intrinsic-cell variance model. TB-29/TB-32 must use matched PZT topology and each cell's own bare reference.

## 6. Independent Rewrite Count

| Assumed true accuracy | Minimum independent trials whose expected Wilson lower bound exceeds 65% |
| ---: | ---: |
| 80.0% | 40 |
| 85.0% | 25 |
| 90.0% | 17 |

If each rewrite has eight repeated captures, the approximate rewrite blocks needed for an 80% gate are:

| Rewrite-level intraclass correlation | Required rewrite blocks |
| ---: | ---: |
| 0.10 | 9 |
| 0.25 | 14 |
| 0.50 | 23 |
| 0.75 | 32 |

Repeated captures within one mass placement are clustered. Estimate rewrite-level intraclass correlation during TB-10 and adapt later sample counts; eight rewrites are enough only if clustering is low.

## Bench Predictions

1. **Model audit:** touch-only and bare repeats will explain some apparent positive shifts; new sites will distinguish a real 2D sensitivity map from three-point overfitting.
2. **Direct matching:** exact-peak three-tone queries will be diagonal immediately after calibration but likely fail beyond about 25 Hz rewrite jitter; the optimized query may extend that to about 100 Hz.
3. **Primary bottleneck:** mass does not compensate for response CV above about 5% in the strict rewrite-separation model.
4. **Best intervention:** reduce drift 2-4x and rewrite-response variation to about 2.5% before expanding from three patterns to four/eight templates.
5. **Site design:** use the proposed robust sites as active-learning measurements; 0.5 mm placement error remains close to or below the 3 SD gate in the model.

## What Would Falsify the Stronger Hypothesis

- Independent rewrite SD remains above 50 Hz after temperature/fixture controls and no robust query reaches 80%.
- The direct RMS/ringdown matrix loses its diagonal after using frozen frequencies on independently rebuilt patterns.
- Touch-only trials reproduce the written-pattern separation.
- TB-11 measurements disagree with every plausible 2D sensitivity assignment and no empirical site map is repeatable.
- Drift reduction, not mass, fails to improve simulated and measured separation in the predicted direction.

## Reproduction

```bash
python3 tools/template_bank_hypothesis_sim.py
```

Machine-readable details are in `data/results/template_bank_simulation/summary.json`.
