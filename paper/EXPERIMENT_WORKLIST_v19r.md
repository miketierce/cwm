# Experiment Worklist for v19r

**Purpose:** Close evidentiary gaps identified in the peer review audit before submission.
**Priority:** Ordered by criticality to the paper's core claims.

---

## E-W1: PZT-Lifted Null Test on Pico NCO Hardware (CRITICAL)

**Gap:** No formal null test exists on the current (June 2) Pico NCO topology. The 88% feedthrough figure is from the obsolete v3 breadboard (shared ground bus, May 26). The May 27 null test proved 0% feedthrough after physical separation, and spatial ratios (49:1, 55:1) on June 2 provide strong indirect evidence — but a direct measurement would be bulletproof.

**Protocol:**

1. Current Pico NCO configuration (crimped DuPont, 220Ω, no shared breadboard)
2. Drive at 4 standard modes (35,840 / 54,920 / 57,037 / 97,011 Hz)
3. Capture baseline FFT (PZT coupled to plate)
4. Physically lift TX PZT from plate surface (break acoustic contact)
5. Re-drive same modes, capture FFT
6. Compare: lifted signal should be at noise floor (< 2× noise)

**Success criterion:** Lifted/coupled ratio < 1% at all 4 modes (i.e., >99% acoustic)

**Time estimate:** 30 minutes bench time

**Paper impact:** Centers signal-path attribution definitively. Closes Fatal Issue #1.

---

## E-W2: Cross-Session Discrimination (Independence Test) (HIGH)

**Gap:** The reviewer notes that all pattern-discrimination trials were collected in a single session. This creates repeated-measures dependence and inflates significance.

**Protocol:**

1. Run standard 4-mode binary discrimination (4 patterns × 20 reps)
2. Repeat on 3 different days (different ambient temperatures, power cycles)
3. Cross-validate: train on Day 1 centroids, test on Day 2 & 3 captures
4. Report cross-session accuracy separately from within-session

**Success criterion:** Cross-session accuracy ≥ 95% (with Wilson CI)

**Time estimate:** 3 sessions × 15 min = 45 min spread over 3 days

**Paper impact:** Addresses independence assumption. If cross-session still 100%, claim is much stronger. If degraded, report honestly with temperature-dependence analysis.

---

## E-W3: Fixed-Angle CHSH Protocol (No Optimization) (HIGH)

**Gap:** The reviewer correctly notes that numerically optimizing CHSH angles creates selection bias — the optimizer finds the angles that maximize S, which inflates the result. A fixed-angle protocol (e.g., standard Bell angles: 0°, 22.5°, 45°, 67.5°) applied without post-hoc selection is more credible.

**Protocol:**

1. Use the 5 mode pairs from E1
2. Apply FIXED standard Bell angles (not optimized): a₁=0°, a₂=45°, b₁=22.5°, b₂=67.5°
3. Compute S from these fixed projections
4. Report both: optimized S (as upper bound) and fixed-angle S (as unbiased estimate)
5. Also report the phase-inclusive complex-tomography result honestly (C=0.924 with huge CI)

**Success criterion:** Fixed-angle S > 2.0 (separability violation confirmed without optimization)

**Time estimate:** Re-analysis of existing E1 data (no new acquisition needed — just re-compute with fixed angles)

**Paper impact:** Addresses selection-bias critique. Even if fixed-angle S is lower (e.g., 2.5), the non-separability claim survives.

---

## E-W4: All-Decoder Sensitivity Analysis (MEDIUM)

**Gap:** Only the best-performing decoder pipeline is reported. The reviewer asks: how many feature extraction / classification pipelines were tried? Report ALL of them.

**Protocol:**

1. Take existing multilevel and binary discrimination data
2. Test multiple classifiers: nearest-centroid (Mahalanobis), kNN, SVM, logistic regression, random forest, naive peak threshold
3. Test multiple feature sets: raw FFT magnitude, peak heights only, peak ratios, phase-included, envelope-only
4. Report accuracy for ALL combinations in a table (not just the best)

**Success criterion:** Multiple pipelines achieve >95% accuracy (proves robustness, not cherry-picking)

**Time estimate:** 2 hours analysis code (no bench time)

**Paper impact:** Addresses "you only show the best decoder" critique. Shows classification is easy across many methods.

---

## E-W5: Q-Factor Measurement with Proper Fitting (MEDIUM)

**Gap:** All existing Q measurements have R² < 0.1 (0.077 best). The reviewer correctly identifies this as "not a fit" — the exponential decay model doesn't explain the data well.

**Protocol:**

1. New ringdown measurements at 4 modes
2. Use Pico NCO square wave (not AWG) for drive
3. Longer capture window (200ms+ post-excitation)
4. Fit with multiple models: single exponential, double exponential, stretched exponential
5. Report R² for each model; select based on AIC/BIC
6. Average over ≥ 5 trials with uncertainty

**Success criterion:** Best-fit model R² > 0.9, or honestly report that ringdown envelope is not clean exponential (and explain why — multimode beating, PZT loading transient, etc.)

**Time estimate:** 1 hour bench time + 1 hour analysis

**Paper impact:** Either validates Q claim properly or leads to honest restatement ("loaded Q" with caveats)

---

## E-W6: Multi-Plate Fingerprint Uniqueness (LOW - for PUF claim)

**Gap:** All data is from a single plate. PUF claims require demonstrating that different plates produce distinguishably different fingerprints.

**Protocol:**

1. Acquire 1-2 additional fused silica plates (same spec: 100×100×1mm)
2. Run standard mode census on each
3. Run 4-mode binary discrimination across plates (enroll plate A, reject plate B)
4. Quantify inter-plate separation (should be >> intra-plate variation)

**Success criterion:** Inter-plate mode frequencies differ by > 10× intra-plate trial variation

**Time estimate:** Need to order plates (days); 1 hour bench per plate

**Paper impact:** Strengthens PUF claim, but not essential for core paper (can be flagged as future work)

---

## Summary Priority

| ID   | Experiment                   | Priority | New Data?        | Time    |
| ---- | ---------------------------- | -------- | ---------------- | ------- |
| E-W1 | PZT-lifted null (Pico NCO)   | CRITICAL | Yes              | 30 min  |
| E-W2 | Cross-session discrimination | HIGH     | Yes              | 3 days  |
| E-W3 | Fixed-angle CHSH             | HIGH     | No (re-analysis) | 1 hour  |
| E-W4 | All-decoder sensitivity      | MEDIUM   | No (re-analysis) | 2 hours |
| E-W5 | Q-factor proper fitting      | MEDIUM   | Yes              | 2 hours |
| E-W6 | Multi-plate PUF              | LOW      | Yes              | Days    |

**Minimum viable for v19r submission:** E-W1 + E-W3 + E-W4 (one bench session + analysis)
**Ideal for strong submission:** E-W1 through E-W5
