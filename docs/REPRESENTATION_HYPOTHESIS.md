# The Representation Hypothesis

**Date:** 2026-04-17
**Status:** HYPOTHESIS — awaiting experimental discrimination
**Prerequisite data:** Rod campaigns (38 experiments), Plate campaigns (Exps 1–7), Kronos census

---

## 1. Hypothesis Statement

> **CWM is a physical embedding mechanism that maps physical state into a modal representation in which identity is preserved under transformations that ordinarily destroy discriminability.**

More precisely: a glass resonator performs a geometry-sensitive projection of boundary conditions into a latent manifold whose stable relational structure survives partial observation, sensor repositioning, weighting variation, crosstalk, instrument swap, and substrate change.

### Operational Definitions

**Identity.** Throughout this document, _identity_ means: the label or equivalence class that remains nearest-neighbor stable under a specified family of transformations. It is not object identity in a metaphysical sense — it is the empirical fact that an object's representation stays closer to itself than to any other enrolled object, even after the measurement conditions change. Where precision matters, we distinguish:

- _Object identity_ — the enrolled label (plate A, plate B, etc.)
- _Configuration identity_ — the specific boundary-condition state (perturbation placement, coupling geometry)
- _Neighborhood preservation_ — the weaker property that relative distances between representations are maintained under transformation

**Latent manifold.** Here _latent manifold_ refers to a lower-dimensional structure inferred empirically from: (a) stable low-dimensional embeddings (PCA and nonlinear), (b) subspace-projection robustness of classification, and (c) cross-channel transfer of discriminability. It is a testable claim, not an assumption — RH-02 and RH-05 are designed to determine whether this structure exists or whether the data is simply high-dimensional without concentrated geometric organization.

This is distinct from — and potentially upstream of — all current working interpretations:

| Current Interpretation             | What It Explains                       | What It Leaves Unexplained                             |
| ---------------------------------- | -------------------------------------- | ------------------------------------------------------ |
| Physical Unclonable Function (PUF) | Manufacturing uniqueness               | Why identity survives destructive transforms           |
| Reservoir Computing                | Fixed nonlinear basis → linear readout | Why identity remains stable across altered projections |
| Spectral Fingerprint Classifier    | Discrimination in frequency domain     | Why degradation pathways fail to destroy it            |
| Mode-Addressable Memory            | Independent bits via independent modes | The relational geometry between modes                  |

**The hypothesis proposes that all four are downstream effects of a single deeper primitive: invariant-preserving embedding of physical state.**

---

## 2. Evidentiary Basis

### 2.1 Observed Facts

| #   | Observation                                  | Source            | Quantification                            |
| --- | -------------------------------------------- | ----------------- | ----------------------------------------- |
| F1  | Discrimination survives −3.9 dB crosstalk    | Rod E34           | 100% accuracy, 7+ sessions                |
| F2  | K=2 of 10 peaks → 100% recall                | Rod E34           | 20% partial query, no degradation         |
| F3  | Weight ratio variation 0.5×–10× → 100%       | Rod E34           | Reversed weights also 100%                |
| F4  | NE/NW PZTs share ~10% of modes on same plate | Plate census      | Jaccard ≈ 0.10–0.20                       |
| F5  | Perturbation location encodes; mass doesn't  | Rod perturbation  | Random re-perturbation ≈ baseline         |
| F6  | Shuffled enrollment → 0%                     | Rod E34           | Permutation destroys identity             |
| F7  | Lock-in SNR +13 dB above linear prediction   | Rod lock-in       | +30.5 dB measured vs +17.5 dB predicted   |
| F8  | Mode count: 13 (1D rod) → 180 (2D plate)     | Census comparison | Combinatorial, not linear, scaling        |
| F9  | Modes are linear and independent             | Plate Exp 6       | No real combination tones (H only passes) |
| F10 | 5/5 authentication at 83–91% margins         | Plate Exp 4       | No environmental control, no isolation    |

### 2.2 Unexplained Residue

These observations resist explanation by any single current interpretation:

| #   | Residue                                      | Why It's Strange                                                                                                                                                                                                      |
| --- | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | **Robustness under destructive transforms**  | Crosstalk, partial query, weight permutation, sensor position change should each independently degrade a fingerprint. Together they should obliterate it. They don't.                                                 |
| R2  | **Near-orthogonal views preserve identity**  | Two PZT positions seeing 90% different modes yet both correctly identifying the same plate implies the identity lives in relational structure, not in specific mode values.                                           |
| R3  | **Geometry-driven dimensionality explosion** | 13 → 180 modes is not just "more bits." Jaccard decreases (plates more distinguishable), margins increase, partial queries still work. Each new mode adds a dimension to the embedding, not just a bit to an address. |
| R4  | **Location over mass**                       | The medium decomposes the spatial pattern of boundary conditions into mode-specific coefficients — a physical spatial Fourier transform.                                                                              |
| R5  | **Excess SNR as coherence selectivity**      | The resonator may act as a matched filter: amplifying signals coherent with eigenmodes, rejecting incoherent noise. Not passive sensing — active signal conditioning.                                                 |

### 2.3 Clustering of Residue

All five residues converge on one theme: **the medium performs a geometry-sensitive projection into a latent manifold where identity is encoded as stable relational structure.**

### 2.4 Null Explanations to Falsify

Before claiming latent-manifold structure, we must rule out three simpler explanations that could produce similar-looking robustness:

| #   | Null Hypothesis                      | Mechanism                                                                                                                                                                                            | Which RH Experiments Attack It                                                                        |
| --- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| N1  | **High-dimensional redundancy only** | Identity survives because enough duplicated information remains after any partial damage. No geometric structure required — just a very long signature with massive repetition.                      | RH-02 (if $d_{eff} \approx N_{modes}$, redundancy wins), RH-05 (if shuffled modes still authenticate) |
| N2  | **Channel-specific fingerprinting**  | Each sensing path (NE vs NW, mag vs phase) has its own stable-but-separate signature. Apparent cross-channel invariance is really repeated within-channel separability, not shared latent structure. | RH-01 (if cross-channel transfer fails, N2 wins), RH-03 (if held-out objects fail in learned basis)   |
| N3  | **Simple resonator physics only**    | Q-limited filtering, modal density, and standard matched-filter gain fully explain the observations. No representation-level claim is needed beyond conventional acoustics.                          | RH-06 (if $G_{eff}$ tracks Q within ±3 dB), RH-04 (if no smooth orbits — just physics doing physics)  |

**The representation hypothesis is only supported if all three nulls are weakened.** If any single null fully explains the data, the simpler explanation wins.

---

## 3. Core Research Question

> **What transformation group leaves identity approximately invariant in CWM modal space?**

Sub-questions:

1. What transformations preserve nearest-neighbor identity?
2. What is the intrinsic dimensionality of the identity-bearing manifold?
3. Are different sensing channels observing one shared latent manifold or unrelated signatures?
4. Do unseen objects inhabit the same manifold geometry?

---

## 4. Experiments

### 4.1 Naming Convention

Experiments in this series are prefixed **RH** (Representation Hypothesis), numbered RH-01 through RH-07.

---

### RH-01: Cross-Measure Transfer

**Question:** Does identity live in a specific measured channel, or in a deeper shared geometry?

**Method:**

1. Enroll all 5 plates using magnitude-only spectra (discard phase).
2. Test identification using phase-only spectra (discard magnitude).
3. Repeat with reversed roles.
4. Enroll using NE PZT position; test using NW PZT position.
5. Enroll using Kronos; test using PicoScope (if available) or vice versa.

**Metric:** Authentication accuracy and margin under cross-channel conditions.

**Predicted Outcomes:**

| Result                        | Interpretation                                                                                              |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Cross-channel accuracy > 80%  | **Strong support.** Identity is not channel-bound. Shared latent geometry confirmed.                        |
| Cross-channel accuracy 40–80% | **Moderate support.** Partial invariance — some structure transfers, some is channel-specific.              |
| Cross-channel accuracy < 40%  | **Refutation.** Identity is bound to specific observables. Current "fingerprint" interpretation sufficient. |

**Kill criterion:** If ALL cross-channel tests score < 30%, the representation hypothesis adds nothing to plain fingerprinting.

---

### RH-02: Intrinsic Dimensionality

**Question:** What is the effective dimension of the modal manifold supporting identity?

**Method:**

1. Collect full census vectors (180+ modes × magnitude + phase) for all 5 plates, both PZT positions, multiple repetitions (≥10 per condition).
2. Compute PCA; determine components for 90%, 95%, 99% variance explained.
3. Compute participation ratio: $PR = (\sum \lambda_i)^2 / \sum \lambda_i^2$
4. Estimate local intrinsic dimension via nearest-neighbor methods (e.g., MLE of Levina & Bickel 2004).
5. Test clustering stability under random subspace projections (random 50% of modes, repeat 100×).
6. **Nonlinear structure check:** Compare PCA dimensionality to geodesic-aware methods (Isomap or diffusion maps). If the manifold is curved rather than globally linear, PCA will overestimate the required dimensions. Compute neighborhood preservation score: for each point, measure what fraction of its k=5 nearest neighbors in the full space remain among its k=5 nearest neighbors in the reduced embedding. Compare this score between PCA and Isomap at matched dimensionality.

**Metric:** Effective dimension $d_{eff}$, participation ratio, subspace-projection classification stability, PCA vs. geodesic neighborhood preservation ratio.

**Predicted Outcomes:**

| Result                                                                            | Interpretation                                                                                                                                |
| --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| $d_{eff} \ll N_{modes}$ (e.g., 10–30 out of 180)                                  | **Strong support.** Modes are redundant projections of a lower-dimensional manifold. The manifold is the thing, not the modes.                |
| $d_{eff} \approx N_{modes}$                                                       | **Refutation of manifold hypothesis.** Each mode carries independent identity information. System is simply high-dimensional, not structured. |
| Subspace projection stability > 90% at 50% mode retention                         | **Strong support.** Confirms holographic-like redundancy — any substantial subset contains the identity.                                      |
| Subspace projection stability < 50% at 50% mode retention                         | **Weak/refute.** Identity is distributed uniformly, no concentrated structure.                                                                |
| Geodesic method preserves neighborhoods significantly better than PCA at same $d$ | **Supports curved manifold.** The latent structure is locally low-dimensional but globally nonlinear — more interesting than a flat subspace. |
| PCA ≈ geodesic neighborhood preservation                                          | **Flat manifold.** Structure is approximately linear. PCA is sufficient; no hidden curvature.                                                 |

**Kill criterion:** If $d_{eff} > 0.8 \times N_{modes}$ AND subspace stability < 60%, the manifold hypothesis is unsupported.

---

### RH-03: Cross-Object Generalization Geometry

**Question:** Do unseen objects inhabit the same representational geometry, or does each require a new basis?

**Method:**

1. Enroll plates A, B, G, D (4 plates). Compute PCA basis from these 4.
2. Project plate H into the learned basis. Measure reconstruction error.
3. Perform leave-one-out: enroll 4, project the 5th. Repeat for all 5.
4. Measure inter-plate distances in the shared PCA space.
5. Compare to distances in full mode space — is the geometry preserved under projection?

**Metric:** Reconstruction error of held-out plate in learned basis; distance-rank preservation (Spearman correlation of pairwise distances).

**Predicted Outcomes:**

| Result                                                                                 | Interpretation                                                                                                                                                                                                                       |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Reconstruction error of held-out plate < 2× enrolled plates' residual                  | **Supports shared representational subspace.** New objects are compressible in the same linear basis. Necessary but not sufficient for shared manifold.                                                                              |
| Reconstruction error 2–5× enrolled                                                     | **Moderate.** Subspace exists but is not fully generalizable — may need more training objects.                                                                                                                                       |
| Reconstruction error > 5× enrolled                                                     | **Refutation.** Each object has idiosyncratic structure. Not a shared subspace.                                                                                                                                                      |
| Distance-rank Spearman ρ > 0.9 between full-space and reduced-space pairwise distances | **Supports shared manifold geometry (stronger claim).** Not just compressibility — the relational structure between objects is preserved under projection. This distinguishes true manifold membership from mere reconstructability. |
| Distance-rank Spearman ρ < 0.5                                                         | **Refutation of shared geometry.** Objects may compress into a common basis without preserving their relative relationships — shared subspace without shared manifold.                                                               |

**Kill criterion:** If held-out reconstruction is consistently > 5× and rank correlation < 0.5, there is no shared representational geometry.

---

### RH-04: Controlled Transform Orbits

**Question:** Do known physical transformations trace smooth, structured orbits in modal space?

**Method:**

1. Fix one plate (e.g., plate A).
2. Systematically vary one parameter at a time:
   - Sensor position: 5 positions along one edge (if fixture allows)
   - Coupling pressure: 3 levels (light, normal, firm)
   - Drive amplitude: 4 levels (0, −6, −12, −18 dB)
   - Perturbation location: 5 positions on plate surface (putty dot)
   - Partial mode masking: retain top 50%, 30%, 20%, 10% of modes
3. For each variation sequence, compute the trajectory in PCA space.
4. Measure: path smoothness (total arc length / endpoint distance), curvature consistency, return-to-origin after removing perturbation.

**Metric:** Orbit smoothness ratio, curvature statistics, reversibility score.

**Predicted Outcomes:**

| Result                                                            | Interpretation                                                                                                                                                         |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Smooth orbits (smoothness ratio < 2.0) for ≥3 transform types     | **Strong support.** Transformations act as structured group operations on the representation. This is the mathematical doorway to characterizing the invariance group. |
| Smooth for 1–2 types, chaotic for others                          | **Partial support.** Some transforms are geometrically structured; others are not. The invariance group is smaller than hoped.                                         |
| All orbits chaotic (smoothness ratio > 5.0)                       | **Refutation.** Transforms do not act smoothly. Robustness may be due to redundancy rather than geometric invariance.                                                  |
| Perturbation orbits reversible (return < 10% of outward distance) | **Strong support for write/erase.** The manifold has a well-defined "home position" per object.                                                                        |

**Kill criterion:** If no transform type produces smooth orbits AND reversibility score > 50% of outward distance, the geometric-invariance interpretation is not supported.

---

### RH-05: Redundancy vs. Invariance Discrimination

**Question:** Is the observed robustness due to (a) extreme redundancy in a high-dimensional space, or (b) genuine geometric invariance of a lower-dimensional structure?

**Method:**

1. **Redundancy test:** Randomly shuffle mode labels within each plate's spectrum. Re-run authentication. If accuracy holds, the system is using statistical density, not geometric structure.
2. **Structured dropout:** Remove modes in spatially contiguous bands (e.g., all modes 3000–5000 Hz) vs. random dropout of same count. Compare degradation profiles.
3. **Synthetic manifold probe:** Generate synthetic "plates" by sampling random points in the PCA subspace found in RH-02. Test whether these synthetic plates are as discriminable as real ones. If yes, the manifold alone carries identity. If no, there is additional structure outside the manifold.

**Metric:** Authentication accuracy under structured vs. random dropout; discriminability of synthetic manifold samples.

**Predicted Outcomes:**

| Result                                                                    | Interpretation                                                                                                                |
| ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Shuffled modes → accuracy drops to chance                                 | **Supports geometry.** Mode ordering (i.e., frequency-space structure) carries the identity, not just statistical properties. |
| Shuffled modes → accuracy still high                                      | **Supports redundancy.** Identity lives in aggregate statistics, not in relational structure. Weaker claim.                   |
| Contiguous band removal degrades faster than random removal of same count | **Supports geometry.** Specific frequency regions carry disproportionate structural information.                              |
| Contiguous ≈ random degradation                                           | **Supports redundancy.** Information uniformly distributed.                                                                   |
| Synthetic manifold points discriminable                                   | **Strong manifold support.** The low-dimensional embedding itself carries identity structure.                                 |

**Kill criterion:** If shuffled modes still authenticate at > 80% AND contiguous = random dropout, the representation hypothesis reduces to "it's just a high-dimensional fingerprint with redundancy."

---

### RH-06: Matched-Filter Gain Characterization

**Question:** Is the +13 dB SNR excess evidence of eigenstructure-matched gain not fully explained by conventional Q scaling?

**Method:**

1. Drive plate at each of its known resonant modes with CW tone.
2. Simultaneously inject broadband noise at calibrated levels.
3. Measure output SNR at resonant frequency vs. off-resonance.
4. Compute effective filter gain: $G_{eff} = SNR_{on-resonance} - SNR_{off-resonance}$
5. Compare $G_{eff}$ to theoretical Q-limited gain: $G_{theory} = 10 \log_{10}(Q)$
6. Repeat for modes with different Q values to establish $G_{eff}$ vs. Q relationship.

**Metric:** $G_{eff}$, slope of $G_{eff}$ vs. $\log(Q)$, residual gain unexplained by Q alone.

**Predicted Outcomes:**

| Result                                                       | Interpretation                                                                                                                                                                           |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| $G_{eff}$ tracks Q linearly on log scale (slope ≈ 1.0)       | **Explained by Q.** The SNR excess is just high-Q filtering. Useful but conventional.                                                                                                    |
| $G_{eff}$ exceeds Q prediction by > 6 dB consistently        | **Supports coherence-selective amplification beyond Q.** The resonator exhibits eigenstructure-matched gain not explained by simple resonant filtering. Representation-level phenomenon. |
| $G_{eff}$ varies across modes on same plate independent of Q | **Interesting anomaly.** Some modes are "better matched" than others — suggests geometric selectivity beyond simple Q.                                                                   |

**Kill criterion:** If $G_{eff}$ tracks Q within ±3 dB across all modes, the SNR excess is fully explained by conventional resonator physics.

---

### RH-07: Approximate Local Symmetry Characterization

**Question:** Can the observed identity-preserving transforms be approximated by a low-dimensional local transformation family with group-like properties?

Note: the goal here is not to prove a full Lie group acts on the representation. It is to determine whether the transforms that preserve identity have _any_ algebraic regularity — closure, invertibility, low generator count — or whether they are unstructured.

**Method:**

1. Using the orbit data from RH-04, compute the linear transformation (rotation + scaling) that best maps each perturbed state back to baseline.
2. Collect all such transformations into a set.
3. Test approximate group properties:
   - Closure: does composing two transforms yield another approximately in the set? (measure residual)
   - Inverse: does each transform have an approximate inverse in the set?
   - Identity: is the unperturbed state a fixed point?
4. Estimate the dimensionality of the transformation family (number of independent generators via SVD of the transformation set).
5. If closure and inverse errors are small, characterize the local structure: does it resemble a known low-dimensional group (rotation, scaling, affine)?

**Metric:** Group closure error, inverse error, generator count, transformation family dimension.

**Predicted Outcomes:**

| Result                                                                                           | Interpretation                                                                                                                                                            |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Transforms form an approximate local family (closure error < 10%) with dimension $d_G < d_{eff}$ | **Strong result.** Identity-preserving transforms have characterizable algebraic structure. The "smallest strange property" is not random robustness — it has regularity. |
| Transforms are approximately linear (rotation-like) but don't close under composition            | **Moderate support.** There's geometric regularity but not full group structure. Local invariance without global symmetry.                                                |
| Transforms are unstructured (no closure, no inverse, high generator count)                       | **Refutation of algebraic interpretation.** Robustness may be topological (large basins of attraction) rather than algebraic (symmetry group).                            |

**Kill criterion:** If closure error > 50% for all transform pairs AND generator dimensionality ≈ $d_{eff}$, there is no useful local symmetry structure.

---

## 5. Execution Priority

| Priority | Experiment                              | Rationale                                                                                                         | Dependencies                            |
| -------- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| 1        | **RH-02** (Intrinsic Dimensionality)    | Foundational — all other experiments need to know the effective dimension. Purely computational on existing data. | Census data (exists)                    |
| 2        | **RH-05** (Redundancy vs. Invariance)   | Discriminates the two main alternative explanations. Mostly computational.                                        | Census data + auth data (exists)        |
| 3        | **RH-01** (Cross-Measure Transfer)      | Most direct test of the core hypothesis. Requires existing data parsed by channel.                                | Census data split by mag/phase (exists) |
| 4        | **RH-03** (Cross-Object Generalization) | Tests platform potential. Computational on existing data.                                                         | Census data (exists)                    |
| 5        | **RH-04** (Transform Orbits)            | Requires new hardware runs with systematic variation.                                                             | Hardware + Exp 13 protocol              |
| 6        | **RH-06** (Matched-Filter Gain)         | Requires new hardware measurements.                                                                               | Hardware + controlled noise injection   |
| 7        | **RH-07** (Approximate Local Symmetry)  | Depends on RH-04 data. Most mathematically ambitious.                                                             | RH-04 results                           |

---

## 6. Decision Gates

### Gate A: After RH-02 + RH-05 (computational, ~1 day)

| Outcome                                                                 | Decision                                                                                                                             |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| $d_{eff} < 0.3 \times N_{modes}$ AND shuffled-mode accuracy drops > 30% | Proceed with full RH program. Manifold exists and carries geometric structure.                                                       |
| $d_{eff} > 0.8 \times N_{modes}$ AND shuffled = unshuffled              | Abandon representation hypothesis. System is a conventional high-dimensional fingerprint. Return to engineering-focused experiments. |
| Mixed results                                                           | Proceed with RH-01 and RH-03 for additional discrimination.                                                                          |

### Gate B: After RH-01 + RH-03 (computational, ~1 day)

| Outcome                                                       | Decision                                                                                        |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Cross-channel transfer > 60% AND held-out reconstruction < 3× | Commit to hardware experiments RH-04 through RH-07. Write up preliminary findings.              |
| Cross-channel < 30% OR reconstruction > 5×                    | Representation hypothesis is too weak to justify further hardware investment in this direction. |

### Gate C: After RH-04 + RH-07 (hardware + analysis, ~1 week)

| Outcome                                                                      | Decision                                                                                                                                          |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Smooth orbits in ≥3 transform types AND approximate local symmetry structure | **Major result.** Write paper on "Invariant Embedding in Acoustic Resonators." This is the publishable physics claim.                             |
| Smooth orbits but no algebraic regularity                                    | **Useful result.** Topological robustness confirmed. Pivot to engineering exploitation (fault detection, auth) with stronger theoretical backing. |
| No smooth orbits                                                             | Representation hypothesis refuted at the algebraic level. CWM is robust-but-conventional.                                                         |

---

## 7. Relationship to Existing Experiments

| Existing Experiment                                  | Role in RH Program                                                              |
| ---------------------------------------------------- | ------------------------------------------------------------------------------- |
| Plate Census (180 modes × 5 plates × 2 positions)    | **Primary data source** for RH-02, RH-03, RH-05                                 |
| Exp 4 (Authentication)                               | **Baseline metric** — any RH-derived method must match or exceed 83–91% margins |
| Exp 7 (Write-Read)                                   | **Sanity check** for RH-04 reversibility                                        |
| Exp 8 (Ringdown Q)                                   | **Input to** RH-06 matched-filter analysis                                      |
| Exp 13 (Perturbation)                                | **Prototype for** RH-04 controlled transform orbits                             |
| Rod E34 (crosstalk, partial query, weight variation) | **Historical evidence** — F1, F2, F3 in the evidentiary table                   |

---

## 8. Companion Series: Temporal Persistence (TP)

The RH experiments probe the _geometry_ of the representation. A companion series probes its _temporal stability_ — because the viability of CWM reduces to a question of how the substrate "lives in time."

Glasses occupy a unique position: frozen disorder provides both the complexity for rich modal embedding and relaxation times (years to geological) that far exceed any practical readout interval. The TP series tests whether that temporal stability is real and sufficient.

### TP-01: Short-Term Spectral Drift

**Question:** How stable is the modal fingerprint over minutes-to-hours?

**Method:** Census plate D every 15 minutes for 8 hours. No perturbation or physical contact between measurements. Compute per-mode frequency drift, amplitude drift, and phase drift as fraction of mode bandwidth.

**Predicted outcome:** Drift < 0.1% of mode bandwidth per hour (glass relaxation is geological).

**Kill criterion:** If modes drift by more than one linewidth per hour, long-term memory is not viable without environmental control.

**RH connection:** Establishes the temporal baseline for RH-04 orbit measurements — disambiguates geometry from drift.

---

### TP-02: Day-Scale Fingerprint Persistence

**Question:** Is the plate's spectral identity the same tomorrow as today?

**Method:** Full census now, 24h later, 72h later. Same plate, relay, drive parameters. Compute authentication score of Day-N census against Day-0 enrollment. Log ambient temperature for correlation.

**Predicted outcome:** Auth score > 80% at 72h.

**Kill criterion:** If auth score < 50% at 24h, the fingerprint is session-specific, not material-specific.

**RH connection:** If fingerprint persists, the representation is a material property (supports RH over N1-redundancy).

---

### TP-03: Thermal Sensitivity Characterization

**Question:** What is the temperature coefficient of the modal representation?

**Method:** Census at ambient → warm plate ~5°C above ambient → census → cool to ambient → census. Track per-mode frequency shift per degree C.

**Predicted outcome:** Frequency shift ~1–10 ppm/°C (fused silica CTE is 0.55 ppm/°C; PZT coupling adds sensitivity). Modes should shift uniformly in frequency, preserving inter-mode relationships.

**Key question:** Does temperature shift the representation _along_ the manifold (preserving identity) or _off_ the manifold (destroying it)?

**Kill criterion:** If inter-mode spacing changes by > 5% across a 5°C range, the representation is thermally fragile.

**RH connection:** Temperature sweeps are a specific transformation whose orbit structure (RH-04) and symmetry properties (RH-07) can be characterized. If thermal variation produces a smooth orbit in PCA space, that's strong support for geometric invariance.

---

### TP-04: Post-Perturbation Relaxation Timescale

**Question:** After removing a perturbation, how quickly and completely does the spectrum return to baseline?

**Method:** Baseline census → apply putty → census → remove putty → census at +0s, +1min, +5min, +30min, +2h. Track return trajectory in PCA space.

**Predicted outcome:** Return to within 5% of baseline within seconds (elastic glass recovery). Possible slow tail from residual contamination.

**Significance:** If return is fast and complete, write/erase is clean. If there is hysteresis (slow tail), the glass retains memory of perturbation — path sensitivity (connects to hypothesis candidate #3: history-dependent encoding).

**RH connection:** The return trajectory is an orbit whose smoothness and completeness directly test RH-04 geometric structure.

---

### TP–RH Integration

| TP Experiment      | Attacks Null                                           | RH Dependency                  |
| ------------------ | ------------------------------------------------------ | ------------------------------ |
| TP-01 (drift)      | N3 (if stability exceeds thermal-expansion prediction) | Required baseline for RH-04    |
| TP-02 (day-scale)  | N1 (material property, not measurement artifact)       | Validates RH-05 interpretation |
| TP-03 (thermal)    | N3 (orbit structure goes beyond simple physics)        | Feeds RH-04 + RH-07            |
| TP-04 (relaxation) | N3 (hysteresis implies path sensitivity)               | Feeds RH-04                    |

---

## 9. What Success Looks Like

If the representation hypothesis survives Gates A, B, and C, and the TP series confirms temporal stability, the project's framing shifts from:

> "CWM is a hardware platform for classification/authentication/memory"

to:

> "Glass resonators perform physics-native kernel embedding — they convert physical relational structure into a robust latent coordinate system whose invariance group can be characterized."

That is a different category of claim. It would mean CWM is not better at any one task, but rather that it creates a representation in which many tasks become geometrically trivial. The applications (PUF, fault detection, memory) would then be understood as downstream consequences of the embedding, not as the fundamental capability.

---

## 10. Gate A Outcome (2026-04-18)

**Status: MIXED — leaning NEGATIVE for the geometric-manifold form.**

### Summary of Results

| Experiment                                  | Key Metric                     | Result                    | Verdict                                           |
| ------------------------------------------- | ------------------------------ | ------------------------- | ------------------------------------------------- |
| RH-02: Intrinsic Dimensionality             | d_eff(95%) / N_features        | 0.001–0.02 (rank-limited) | INCONCLUSIVE — artifact of N_samples ≪ N_features |
| RH-02: Eigenvalue spectrum                  | Scree-plot shape               | Flat (PR ≈ N-1)           | NO low-dimensional concentration                  |
| RH-05: Shuffle mode labels                  | NN preservation                | **100% ± 0%**             | **REDUNDANCY**, not geometric invariance          |
| RH-05: Contiguous vs random dropout         | Δ accuracy                     | -5% to -13%               | Slight geometric signal, mostly redundancy        |
| RH-01: Cross-channel transfer               | Mag-only / phase-only plate ID | 0–12% (chance)            | Neither channel carries identity alone            |
| RH-01: Cross-position clustering            | NE↔NW distance vs inter-plate  | Comparable                | No position-invariant identity                    |
| RH-03: Cross-run relay identification       | NN matching                    | 1/8 = 12%                 | **Cross-session identity FAILS**                  |
| RH-03: Separation ratio (intra/inter relay) | Distance ratio                 | 0.94–0.95                 | Same relay is MORE distant across runs            |

### Key Finding

**Shuffling frequency-bin labels preserves 100% of nearest-neighbor identity.** This means the NN structure is determined entirely by aggregate statistics (total energy, peak count, magnitude distribution) — not by which specific frequencies carry energy. Identity, to the extent it exists within a session, is a spectral histogram fingerprint, not a geometric manifold.

### Gate A Decision Logic

Per the original criteria:

- d_eff < 0.3 × N_modes AND shuffled accuracy drops > 30% → **PROCEED**
- d_eff > 0.8 × N_modes AND shuffled = unshuffled → **ABANDON**

**Observed:** d_eff was rank-limited (uninformative), and shuffled NN = 100% (no drop). **The shuffle test alone satisfies the ABANDON condition for the geometric-manifold hypothesis.**

### What Survives

The TP experiments, hardware experiments (Exps 8–13), and PUF/authentication applications are unaffected. The negative result applies specifically to the geometric-manifold interpretation — not to CWM's engineering utility.

---

## 11. The Sentence on the Whiteboard (Revised)

> _CWM is a broadband spectral fingerprinting system whose within-session robustness comes from aggregate energy distribution rather than geometric embedding. The Representation Hypothesis, in its geometric-manifold form, is not supported by the data. The temporal stability and physical unclonable properties may still make it valuable — and the TP series will determine whether that value extends across sessions._

The work above determined that the original sentence deserved _may not be_ rather than _is_.
