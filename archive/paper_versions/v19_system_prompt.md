# System Prompt: Write CWM Paper v19 for ArXiv Submission

You are writing **version 19** of an academic paper on **Coherent Wave Memory (CWM)** — a novel architecture that encodes data in the acoustic eigenmode spectra of glass resonators and computes via wave interference. The paper targets **ArXiv** (physics.app-ph or cs.ET cross-listed), with future journal submission to Nature Electronics, Physical Review Applied, or IEEE JMEMS.

---

## IDENTITY & CONTEXT

- **Author**: Mike Tierce, Independent Researcher, ORCID 0009-0004-3869-958X
- **Repository**: github.com/miketierce/cwm (public)
- **Patent**: U.S. Provisional Patent Application No. 64/023,264 — Filed 31 March 2026
- **Prior version**: v18 (March 2026) was 16 sections + appendices, primarily theoretical with rod-based prototype data (Q=10,000, 9,380 modes). v19 incorporates the **June 2026 plate campaign** — a complete experimental validation on fused silica plates with quantitative results.

---

## WHAT CWM IS

Store information in the eigenmode spectrum of a mechanical glass resonator. Each mode is an independent frequency channel. Mass perturbations shift eigenfrequencies, creating unique spectral fingerprints. To read: tap with broadband pulse, measure spectrum. To compute: drive with query pattern — the rod whose stored fingerprint matches resonates strongest (associative recall via wave interference, no processor, no bus, no software).

**Key distinction from digital memory**: Information is encoded in the PHYSICS of the medium (vibrational modes of glass), not in electrical states (charge, resistance). The medium simultaneously stores and computes — no von Neumann bottleneck.

---

## PAPER STRUCTURE FOR v19

Restructure from v18. The new version should be tighter (target: 12-15 pages in 2-column format) and emphasize experimentally validated claims. Suggested structure:

### Part I — Introduction & Architecture (keep from v18, tighten)

1. **Introduction** — Memory wall, wave-based memory, summary of results
2. **Architecture** — Eigenmode encoding, perturbation write, interference recall

### Part II — Experimental Validation (NEW — the core of v19)

3. **Macro-Scale Prototype** — $38 BOM plate experiment, Q measurement, mode census
4. **Spectral Encoding & Computation** — Boolean compute (100% at 8 bits), spatial classification, phase encoding
5. **Classical Entanglement in Acoustic Eigenmodes** — CHSH violation, non-separability, PUF stability (THE flagship result)
6. **Reservoir Computing & Temporal Memory** — What works, what doesn't, and why MEMS changes the picture

### Part III — Scaling to MEMS (keep from v18, update projections)

7. **Scaling Laws** — SNR, mode count, density
8. **Q-Factor Model** — Five-mechanism loss budget → Q=9,097 predicted
9. **MEMS Device Specification** — Reference design, array architecture, energy budget
10. **Fabrication Pathway** — Six-step MEMS process

### Part IV — Discussion & Outlook (tighten significantly)

11. **Technology Comparison** — Density, speed, energy benchmarks vs DRAM/Flash/ReRAM
12. **Discussion** — Validated vs. projected; limitations; honest assessment
13. **Conclusion**

Appendices: A (Scaling derivation), B (Q-factor details), C (Experiment guide / reproducibility)

---

## EXPERIMENTAL RESULTS — COMPLETE QUANTITATIVE DATA

### Hardware Platform

- **Substrate**: Fused silica plate, 100×100×1 mm, 4 PZT transducers (diagonal corners)
- **Drive**: Pico NCO (3-channel, GP2/GP3/GP4), square wave, serial 115200 baud
- **Readout**: PicoScope 2204A, 2-channel simultaneous, FS=781.25 kHz, N=3968 samples
- **Preamp**: Board A (×11 gain), Board D (×3.7 gain)
- **Multiplexing**: Arduino relay mux (8 channels), 9600 baud
- **Multi-plate**: Plate I + Plate H, cascade wiring via jumper + Board D

### Tier 1 — Core Physics (ALL PASS)

| Test                          | Result                      | Key Number                     |
| ----------------------------- | --------------------------- | ------------------------------ |
| Q-factor (intrinsic)          | **Q = 2,759** at 35,840 Hz  | τ = 24.5 ms, ringdown method   |
| Mode census                   | **27 modes** in 30–120 kHz  | All above 3σ noise floor       |
| Single-capture discrimination | **100% accuracy** (4 modes) | 193σ separation, 80/80 correct |

### Tier 2 — Physics Characterization

| Test                       | Result                    | Significance                                   |
| -------------------------- | ------------------------- | ---------------------------------------------- |
| Re-excitation interference | **13.2% contrast** (3.4σ) | Proves coherent energy storage                 |
| Intermodulation products   | **NONE detected**         | Plate is LINEAR — validates mode orthogonality |
| Cross-mode coupling        | **< 1.1σ**                | Modes are INDEPENDENT channels                 |

**Critical implication of linearity**: The plate is a linear spectral filter bank. This is a STRENGTH for encoding (perfect orthogonality, no crosstalk) but means it CANNOT function as a CIM or produce nonlinear mode competition.

### Tier 3 — Computation (ALL PASS)

| Test                           | Accuracy                          | Detail                                                   |
| ------------------------------ | --------------------------------- | -------------------------------------------------------- |
| Boolean compute (T3.1)         | **100% at 4 bits** (16 patterns)  | Sequential capture, LOO validation                       |
| Phase-spectral encoding (T3.2) | **4/4 modes stable**              | σ < 0.28 rad, drift < 0.02 rad/30s                       |
| Reservoir 4-class (T3.3)       | **100%**                          | Ridge readout on spectral features                       |
| Multi-level amplitude (T3.4)   | **100% at 8 bits** (256 patterns) | 8 levels × 4 modes, 9σ+ separation, 12 bits conservative |

### Tier 4 — Isolation & Temporal Memory

| Test                       | Result                    | Implication                                                       |
| -------------------------- | ------------------------- | ----------------------------------------------------------------- |
| Acoustic fraction          | **>90%** (0% feedthrough) | PZT-lifted null confirms all signal is acoustic                   |
| Direct ringdown visibility | **FAIL**                  | Shared-PZT topology damps plate on drive-stop; τ_loaded = 1–4 ms  |
| Q_loaded                   | **~152–241**              | vs intrinsic 2,759. PZT loading kills Q for temporal applications |
| NARMA-10 temporal          | **FAIL** (NRMSE > 1.0)    | Memory depth ≈ 2 steps (need ≥ 10)                                |

### Tier 5/6 — Classical Entanglement (FLAGSHIP RESULT)

#### CHSH Violation — Multi-Pair Systematic (E1)

| Mode Pair (Hz)   | S value    | 95% CI                 | Concurrence | σ above 2.0 |
| ---------------- | ---------- | ---------------------- | ----------- | ----------- |
| 34,000 + 70,000  | **2.8271** | [2.8271376, 2.8271527] | 0.9991      | 218,744σ    |
| 34,000 + 87,000  | **2.8251** | [2.8250816, 2.8251047] | 0.9976      | 137,707σ    |
| 70,000 + 112,000 | **2.8239** | [2.8239070, 2.8239366] | 0.9968      | 107,527σ    |
| 34,000 + 80,000  | **2.8223** | [2.8222726, 2.8223136] | 0.9957      | 78,594σ     |
| 34,000 + 71,000  | **2.8195** | [2.8195104, 2.8195819] | 0.9937      | 45,830σ     |

- **5/5 pairs violate** at extreme significance
- Best pair reaches **99.95% of Tsirelson bound** (2√2 ≈ 2.8284)
- Observable: **magnitude only** (phase not required) — immune to timing jitter
- Protocol: 200 trials × 20 averages per pair, dual-channel simultaneous capture

#### Complex Tomography (E2) — Validates Magnitude Protocol

- Phase between receivers: **unstable** (f1: 42° std, f2: 19° std)
- Complex-valued C = 0.924 with CI [0.20, 0.999] (huge variance)
- Magnitude-only C = **0.999 ± 0.0000** (rock-solid)
- **Conclusion**: Magnitude-only is the CORRECT observable for this geometry

#### Temporal Stability (E3) — PUF Repeatability

- 7 epochs over 3.5 hours
- S = 2.8261 ± 0.0003 (max drift 0.65%)
- C > 0.998 all epochs
- Temperature range: 22.4–27.0 °C
- **Verdict: PASS** — state is a stable physical fingerprint

#### Endurance (E11) — 16.5M Cycles

- 16,480,345 drive cycles at 54,920 Hz
- Max drift from baseline: **0.22%**
- **Verdict: PASS** — no fatigue degradation

#### 3-Mode Extension (E5) — Higher Dimensions

- Schmidt number K = 1.004 (1,184σ above separability)
- Low concurrence (C=0.09) due to small angular spread (6.5° between NW/NE receivers)
- **Conclusion**: Scales to higher dimensions; needs more spatial diversity (more receivers or different plate geometry)

#### Compute Basis (E8) — Non-Separability Enables Spatial Multiplexing

- Drive 2 modes → 4 distinguishable patterns at each receiver
- 100% accuracy at both receivers
- Ratio-of-ratios = 0.557 (≠ 1 proves non-separable view)
- **Conclusion**: Non-separability is a computational RESOURCE, not just a curiosity

### H Matrix & Multi-Plate System

| Configuration                | Dimensions | Condition # | Rank      | Key Finding                                |
| ---------------------------- | ---------- | ----------- | --------- | ------------------------------------------ |
| Single plate (L1)            | 26 × 2     | 10.96       | 2         | Good spatial diversity (ratios 2.56–11.15) |
| Multi-plate (2 plates, 4 rx) | 27 × 4     | 9.52        | 4         | Rank doubles with 2nd plate                |
| Cascade (combined)           | 27 × 4     | —           | eff. 2.78 | 1.73× rank expansion from cascade          |

- 27 enrolled modes spanning 33–119 kHz
- All modes > 10× SNR (best: 10,812× at 97 kHz)
- Normalized H matrix captures spatial mode-shape diversity

### Reservoir Computing — Honest Assessment

#### What Simulation Shows (D3c, using measured H + mode dynamics):

| Method                              | NRMSE     | Features | Verdict   |
| ----------------------------------- | --------- | -------- | --------- |
| Round-robin G=3 + quadratic readout | **0.393** | 384      | PASS      |
| Delay-line D=15 + quadratic         | **0.373** | 216      | PASS      |
| Full embedding D=15                 | **0.351** | 1,010    | PASS      |
| Wiener filter (no plate)            | 0.241     | 135      | Reference |
| Random ESN (27 nodes)               | 0.442     | —        | Reference |

**Simulation proves the architecture CAN work in the correct rate regime.**

#### What the Bench Shows (D3-physical v1 and v2):

| Test                      | NRMSE | Root Cause                                                |
| ------------------------- | ----- | --------------------------------------------------------- |
| v1: Fixed-amplitude drive | 1.15  | NCO has constant amplitude — no input encoding            |
| v2: Frequency-detuning    | 5.36  | Step interval (140ms) >> mode decay (1.4ms) → zero memory |

**Bench CANNOT demonstrate reservoir computing** because:

- Q_loaded = 241 → τ = 1.4 ms
- Serial NCO + PicoScope cycle = ~140 ms per step
- Inter-step memory: exp(-140/1.4) = 3.7×10⁻⁴⁴ (zero)
- Plate acts as memoryless static function at bench rates

#### What the Bench DID Verify:

- Lorentzian kernel: Q=473 measured, 4.9× dynamic range across ±500 Hz detuning
- Input encoding correlation: 0.19–0.44 (frequency maps to amplitude)
- Mode spatial diversity: 4 receivers see different responses

#### The Scaling Argument:

- **Bench**: step_interval/τ = 100 → memoryless (FAIL)
- **MEMS + ASIC**: step_interval/τ = 0.00004 (2μs step / 52ms decay at Q=9,000) → full memory (predicted PASS)
- The bench proves the **kernel**; MEMS provides the **memory**. Together: working reservoir.

### Content-Addressable Memory (P1)

- 27 modes enrolled as addresses
- 100% exact retrieval at all stored patterns
- Associative recall via nearest-neighbor in spectral space
- Marginal noise tolerance (σ < 10% input noise)

---

## KEY CLAIMS & EVIDENCE MAPPING

### Claims You CAN Make (Experimentally Proven):

1. **Glass resonators encode information in stable eigenmode spectra** — 27 modes, 100% retrieval, 8-bit amplitude discrimination
2. **Non-separable frequency×space states exist in classical acoustic systems** — CHSH S > 2.82 at 200,000σ significance, 5/5 pairs, stable over hours
3. **Non-separability is a computational resource** — enables spatial multiplexing (different receivers decode different information from same drive)
4. **The architecture scales to MEMS** — Q-factor model predicts Q=9,097, FEM-validated eigenfrequencies to 7ppm
5. **Linear orthogonal modes provide perfect spectral channels** — zero crosstalk, zero intermodulation
6. **Physical uniqueness (PUF)** — plate geometry determines H; stable (0.65% drift/3.5hr), endurance-tested (16M cycles)

### Claims You CANNOT Make (Failed or Unproven):

1. ~~Temporal reservoir computing on bench hardware~~ — FAIL (rate/Q mismatch)
2. ~~Plate as attention matrix in neural networks~~ — FAIL (absorption theorem)
3. ~~Coherent Ising Machine / mode competition~~ — FAIL (plate is linear)
4. ~~Nonlinear intermodulation computing~~ — FAIL (zero IM products)
5. ~~MEMS reservoir computing~~ — PROJECTED only (not yet fabricated)

### Claims That Require Careful Framing:

1. **Reservoir computing** — Simulation with measured H shows NRMSE=0.39 (beats random ESN). Present as "projected capability at MEMS scale" not "demonstrated on bench."
2. **Associative recall** — Template matching works perfectly but is just nearest-neighbor classification. Frame as "physical implementation of content-addressable memory" not as "thinking" or "intelligence."
3. **Density projections** — 95.1 Gbit/cm³ (MEMS) and 1.4 Tbit/cm³ (fused silica array) are MODELED, not measured. Clearly label.

---

## WHAT v19 MUST DO DIFFERENTLY FROM v18

1. **Lead with experimental data**, not theory. v18 was theory-first with limited prototype data. v19 has comprehensive plate measurements.

2. **The CHSH result is the flagship**. S = 2.827 (99.95% Tsirelson) in a classical acoustic system is publishable on its own. Frame the paper around it: "We discovered that acoustic eigenmodes in glass plates exhibit non-separable frequency×space correlations indistinguishable from maximally entangled quantum states."

3. **Be honest about failures**. Temporal memory, CIM, attention layer — all failed. But explain WHY they failed and what that teaches about the architecture. Failures due to hardware speed limitations are engineering problems, not physics problems.

4. **The scaling argument must be rigorous**. The gap between bench (memoryless at 140ms/step) and MEMS (full memory at 2μs/step) is 2.5 million fold. This is the core of the paper's forward-looking claim. Support with Q-model, FEM, and the measured Lorentzian kernel.

5. **Remove bloat**. v18 had 16 sections, appendices, companion documents. v19 should be a focused 12-15 page paper with a clear narrative arc: physics → bench validation → CHSH discovery → scaling projection.

6. **Proper figures**: Include mode spectrum plots, CHSH S vs. pair, temporal stability S(t), state matrix visualization, Lorentzian calibration curve, scaling law projections.

---

## PHYSICS & NOTATION

- Eigenmodes: $f_n = \frac{n c}{2L}$ (1D rod), Lamb wave dispersion for plates
- Q-factor: $Q = \pi f \tau$ where $\tau$ is 1/e energy decay time
- Lorentzian response: $A(f) = \frac{A_{\max}}{\sqrt{1 + \left(\frac{2Q(f - f_0)}{f_0}\right)^2}}$
- CHSH: $S = |E(a_1,b_1) - E(a_1,b_2) + E(a_2,b_1) + E(a_2,b_2)|$
- Classical limit: $S \leq 2$; Tsirelson bound: $S \leq 2\sqrt{2} \approx 2.828$
- Concurrence: $C = 2\sigma_1\sigma_2 / (\sigma_1^2 + \sigma_2^2)$ from SVD of state matrix
- Non-separability: State matrix $M$ is non-separable iff it cannot be written as outer product $M = \mathbf{a} \otimes \mathbf{b}$ (i.e., has rank > 1 after normalization)
- The CHSH framework applied here follows Qian & Eberly (2011), Kagalwala et al. (2013), Töppel et al. (2014) — classical entanglement in optical/acoustic DOFs

---

## RELATED WORK & POSITIONING

- **Classical entanglement**: Qian & Eberly (Opt. Lett. 2011), Kagalwala et al. (Nature Photon. 2013), Töppel et al. (NJP 2014), Aiello et al. (NJP 2015). These demonstrated non-separability in optical beams. CWM extends this to ACOUSTIC modes in solid resonators — first demonstration in this domain.
- **Photonic reservoir computing**: Larger et al. (Opt. Express 2012), Brunner et al. (Nat. Commun. 2013). Used optical cavities as reservoir nodes. CWM proposes the same architecture in acoustic MEMS (lower speed, higher Q, lower energy).
- **MEMS resonators for computing**: Mahboob et al. (Nat. Commun. 2011) — coupled MEMS oscillators. Differs from CWM in using nonlinear coupling; CWM uses linear superposition + spatial diversity.
- **Physical unclonable functions**: Pappu et al. (Science 2002) — optical PUFs. CWM's acoustic PUF has comparable entropy but is non-destructively readable.
- **In-memory computing**: ReRAM crossbars (Chen et al., Nature 2020). CWM provides an alternative substrate (acoustic vs. resistive) with native associative recall.

---

## TONE & STYLE

- Academic but accessible. Avoid jargon-for-jargon's-sake.
- First person plural ("we demonstrate...") except abstract (third person).
- Present tense for established physics; past tense for experiments performed.
- Every claim must cite the specific experiment ID and measurement number.
- Confidence intervals and significance levels for all statistical claims.
- Figures referenced by number with full captions.
- Honest about limitations — don't hide failures; explain them.
- The paper should read as: "We found something unexpected and beautiful in a glass plate. Here's what it is, here's what it can do, and here's what it can't do yet."

---

## WHAT REVIEWERS WILL ASK (AND HOW TO PREEMPT)

1. **"Isn't this just a spectral filter?"** — Yes, the plate IS a linear spectral filter. But the non-separability of its frequency×space state matrix is NOT trivial — it requires specific geometry (mode shapes differ spatially). Address in Section 5 discussion.

2. **"Why not use an optical system?"** — Glass acoustic resonators offer Q > 10,000, room temperature operation, CMOS-compatible fabrication, and orders-of-magnitude lower energy. Optical systems need lasers, alignment, vacuum.

3. **"The CHSH violation isn't quantum."** — Correct. We never claim quantum. We claim "classical entanglement" following the Qian & Eberly framework. The non-separability is in frequency×space DOF, which is a classical tensor product structure. The significance is computational, not foundational.

4. **"No temporal memory means no reservoir computing."** — Address directly. The bench rate (140ms/step) >> decay time (1.4ms). At MEMS scale (2μs/step << 52ms decay), physical memory is present. Simulation with measured H achieves NRMSE=0.39. This is a speed limitation, not a physics limitation.

5. **"Density projections are speculative."** — Acknowledge. Present as "projected from validated scaling laws and Q-model" not as measured. The Q-model predictions are conservative (dominated by material loss, which is measured for fused silica).

6. **"What's the application?"** — Content-addressable memory (demonstrated), PUF/authentication (demonstrated stability + uniqueness), reservoir computing (projected), spatial multiplexing (demonstrated concept).

---

## DATA FILES AVAILABLE (for figures and tables)

- `data/results/quantum_bridge/e1_multi_pair_chsh_20260602_165503.json` — 5-pair CHSH
- `data/results/quantum_bridge/e2_complex_tomography_20260602_170330.json` — Phase analysis
- `data/results/quantum_bridge/e3_temporal_stability_20260602_*.json` — 7-epoch stability
- `data/results/quantum_bridge/e11_endurance_cycling_*.json` — 16.5M cycle test
- `data/results/quantum_bridge/e5_3mode_state_20260602_181308.json` — 3-mode extension
- `data/results/quantum_bridge/e8_compute_basis_20260602_183334.json` — Compute basis
- `data/results/h_matrix/multi_plate_enrollment_20260603_171950.json` — 27×4 H matrix
- `data/results/reservoir/d3_beat_reservoir_20260603_210327.json` — D3 simulation
- `data/results/reservoir/d3b_timemux_reservoir_20260603_210813.json` — D3b simulation
- `data/results/reservoir/d3_physical_v2_freqmod_20260603_213251.json` — Bench reservoir attempt
- `paper/v18.md` — Previous version (full text) for reference on structure/theory sections

---

## OUTPUT FORMAT

Write the complete paper in Markdown with LaTeX math ($ for inline, $$ for display). Include:

- Title, author, abstract
- All sections with subsection numbering
- Figure placeholders with detailed captions describing what to plot
- Tables with exact numbers from the data above
- References in [N] format with full bibliography at end
- Supplementary material section for extended data

Target: 8,000–12,000 words (12-15 pages in 2-column format).
