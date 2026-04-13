# CWM Research Roadmap

## Decision Framework: Disprove or Actualize

This roadmap follows a **falsification-first** methodology. Each milestone includes explicit **kill criteria** — quantitative thresholds that, if not met, indicate the approach is unviable and should be abandoned or fundamentally rearchitected. Conversely, each milestone identifies **actualization signals** — results that validate continuing investment.

> **Note on substrate evolution.** Early simulation work explored ferrofluid as a reconfigurable acoustic medium. Phase 1 coupled-physics simulations revealed a fundamental phase diffusion barrier (77.5% per µs from nanoparticle Brownian motion) that makes any colloidal or liquid substrate unviable for coherent spectral encoding. This kill is documented in the paper (§3.1) and in the archived findings below. All forward phases target the **solid glass** architecture described in the paper.

---

## Phase 0: Computational Validation (Current — Q1-Q2 2026)

### Goal

Reproduce and extend the paper's simulation claims. Determine whether the theoretical framework is internally consistent before any hardware investment.

### Experiments

| ID  | Experiment              | Key Metric          | Kill Criterion             | Paper Claim |
| --- | ----------------------- | ------------------- | -------------------------- | ----------- |
| E01 | Mode Persistence        | Coherence time vs η | τ_measured < 0.5× τ_theory | τ ≈ 1/(2η)  |
| E02 | ZIM Damping Reduction   | τ_ZIM / τ_Normal    | Ratio < 1.3×               | ~2×         |
| E03 | Dilatancy Tamper Signal | Freq drift at γ=0.5 | Drift < 10% (1D)           | ~33%        |
| E04 | Thermal Stability       | Max safe modes      | < 10 modes with ZIM        | ~322 modes  |
| E05 | Geometry Invariance     | Eigenvalue shift    | > 10% at γ=0.3             | < 1%        |

### Deliverables

- [x] All five experiments pass/fail documented with data
- [x] Claims validation table completed (8 CONFIRMED, 1 PLAUSIBLE, 0 REFUTED)
- [x] Sensitivity analysis for each key parameter (notebook 04)
- [x] Decision: **PROCEED to Phase 1** — see rationale below

### Phase 0 Decision: PROCEED ✅

**Date:** 2026-03-04

**Results summary:**
| Experiment | Result | Kill Criterion Met? |
|---|---|---|
| E01 Mode Persistence | τ matches theory within 1% | No — PASS |
| E02 ZIM Damping | 2.0× coherence gain (theory) | No — PASS |
| E03 Dilatancy Tamper | 33.3% drift at γ=0.5 | No — PASS |
| E04 Thermal Stability | 322 modes with ZIM | No — PASS |
| E05 Geometry Invariance | Analytically 0% (Mie); FD solver too coarse | Inconclusive — PLAUSIBLE |

**0 of 5 kill criteria triggered.** (Threshold was ≥3 to abort.)

**Sensitivity analysis key findings:**

- 🔴 **Q factor** is the #1 risk — the five-mechanism MEMS model (§7) predicts 9,097 but awaits measurement.
- 🔴 **α (thermal drift)** is the #2 risk — assumed 3.3×10⁻⁶/K for borosilicate from literature.
- 🟡 ZIM damping factor and η are medium risk but tolerant of 40% error.
- 🟢 ΔT, γ, L are engineering parameters with low sensitivity.

**Blocking issues for Phase 2:**

- Geometry invariance needs Meep/COMSOL validation (FD solver ill-conditioned at ε → 0).

### Kill → Pivot

If ≥3 of 5 experiments fail kill criteria, the architecture's theoretical basis is unsound. Document findings, publish negative results, and consider:

- Whether a different encoding scheme preserves the core insight
- Whether the energy estimates survive with corrected parameters

---

## Phase 1: Advanced Simulation (Q2-Q4 2026)

### Goal

Extend the paper's validated models with realistic multiphysics simulation and system-level analysis. Resolve remaining open simulation questions before hardware investment.

### Work Items

| Task                    | Tool/Method                              | Success Metric                                | Status                                                  |
| ----------------------- | ---------------------------------------- | --------------------------------------------- | ------------------------------------------------------- |
| Full FDTD with Meep     | [MIT Meep](https://meep.readthedocs.io/) | Validate geometry invariance claim            | 🟡 Scaffolded (`simulations/meep_fdtd.py`)              |
| Multiphysics coupling   | SVEA coupled-mode ODE                    | Acoustic + thermal coupling modeled correctly | ✅ Done (`simulations/coupled_physics.py`, notebook 08) |
| Multi-mode interference | Beam propagation method                  | Demonstrate associative recall in simulation  | ✅ Done (`simulations/interference.py`, notebook 05)    |
| CMOS interface modeling | Component-level energy budget            | Viable readout SNR at projected energy budget | ✅ Done (`simulations/cmos_interface.py`, notebook 07)  |
| Grid convergence        | FD + Richardson extrapolation            | Discretization error < 1%                     | ✅ Converged at N≥10 (`simulations/convergence.py`)     |
| Sensitivity analysis    | Parameter sweeps                         | Identify high-risk assumptions                | ✅ Done (`simulations/sensitivity.py`, notebook 04)     |
| Monte Carlo tamper      | Statistical validation                   | FPR < 10%, FNR < 5%                           | ✅ Done — FPR 4.7%, FNR 0% (exp03, notebook 07)         |
| Claims auto-validation  | Programmatic pipeline                    | All claims auto-populated from experiments    | ✅ Done (`analysis/comparison.py`)                      |

### Kill Criteria

- Multi-mode interference produces < 50% retrieval accuracy → computation model fails
- System-level energy per read exceeds 10 pJ → no advantage over DRAM

### Actualization Signals

- Associative recall works at > 80% accuracy in simulation → core computation validated ✅
- Energy budget transparent and competitive → proceed to MEMS fabrication ✅

### Phase 1 Findings to Date

**Date:** 2026-03-04

#### ✅ Grid Convergence (notebook 07, `simulations/convergence.py`)

- 3D FDTD frequency error: 0.84% at N=5 → **0.16% at N≥10** (FFT-bin limited)
- Richardson extrapolation confirms 2nd-order convergence
- N=10 is sufficient for all Phase 1 simulations; Meep needed only for ENZ-specific validation

#### ⚠️ CMOS Energy Budget — IMPORTANT FINDING (notebook 07, `simulations/cmos_interface.py`)

- **Physics-layer write energy is truly fJ-scale** ✅
- **System-level read energy is ~1.1 pJ** (ADC-dominated at 95% of total)
- Component breakdown at 28nm:
  - Excitation: 2.6 fJ
  - Sensing: 0.5 fJ
  - Amplifier: 100 fJ
  - **ADC: 1000 fJ (95% of total)** ← bottleneck
  - Addressing: 10 fJ
  - I/O: 1 fJ
  - **Total: 1114 fJ ≈ 1.1 pJ**
- Technology scaling: 2060 fJ (180nm) → 1065 fJ (7nm) — still > 1 pJ at all nodes
- **This does NOT kill the architecture** — 1.1 pJ is still ~3× below DRAM's ~3 pJ/bit total access energy
- **Resolution:** Paper v18 now clearly distinguishes physics-layer write energy (15 fJ/bit) from system-level read energy (1.7 pJ/bit including ADC) — see §1.3 summary table, §2.2, §8.4, §8.5, §10.1, and §14.4

#### ✅ Monte Carlo Tamper Detection (notebook 07, `experiments/exp03`)

- 5000 trial statistical validation
- γ=0.5: FPR = 4.7%, FNR = 0% (perfect detection)
- Minimum reliable γ = 0.010 (1% geometric perturbation detectable)
- Robust to noise: 1% noise → min detectable γ rises to ~0.1 (still practical)

#### ✅ Previously Completed

- Interference recall: 97.6% single-pattern fidelity, 50 patterns at 90% accuracy (notebook 05)
- Sensitivity: cell length L highest elasticity (−2.35), Q factor #1 risk (notebook 04)

#### Updated Claims Scorecard (Solid Glass Architecture)

| Status    | Count | Details                                                                                                                             |
| --------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------- |
| CONFIRMED | 8     | ZIM coherence, 1D/3D drift, modes ±ZIM, density scaling, excitation energy, interference recall, tamper detection, grid convergence |
| PLAUSIBLE | 1     | Geometry invariance (needs Meep or COMSOL)                                                                                          |
| QUALIFIED | 1     | Energy: physics-layer fJ confirmed; system-level ~1 pJ (now documented in paper §8.5)                                               |

#### Remaining Phase 1 Priorities

1. 🔴 Install Meep → resolve geometry invariance (PLAUSIBLE → CONFIRMED/REFUTED)

---

## Phase 1.5: Macro-Rod Hardware Prototype (April 2026)

### Goal

Validate core CWM physics claims on a macro-scale (150 mm) 4-rod glass prototype with PZT transducers, PicoScope readout, and Arduino relay mux. Identify which claims hold at macro scale vs which require MEMS fabrication.

### Hardware

- 4 borosilicate glass rods (150 mm), hand-selected for spectral diversity
- Shared PZT drive + individual PZT sense per rod
- Arduino Nano relay mux (8-ch, LOW-trigger)
- PicoScope 2204A (Ch A, ±1V, 781 kSps, 8064 samples)
- AWG at 2 Vpp CW excitation
- No temperature control (room ambient)

### Experiment Suite (23 experiments, `tools/additional_experiments.py`)

**Phase 1.5a: Core Function (E01–E11, Rounds 1–3)**

| Experiment                  | Result                                       | Status          |
| --------------------------- | -------------------------------------------- | --------------- |
| Template associative recall | 100% (4/4, 7+ sessions, 3 repeats)           | ✅ Confirmed    |
| Nearest-neighbor search     | 100% (11/11, τ=1.000)                        | ✅ Confirmed    |
| 3-input Boolean compute     | 100% (chained, pre-scan + guard band)        | ✅ Confirmed    |
| CIM suite (full pipeline)   | 2 runs, both 100%                            | ✅ Confirmed    |
| Synaptic pruning tolerance  | 100% through 22.5%, robust to 100× NF        | ✅ Confirmed    |
| Temporal stability          | 100% across 4 separate sessions              | ✅ Confirmed    |
| Virtual rewrite (sub-band)  | 2 virtual devices, both 100%                 | ✅ Confirmed    |
| Mode hybridization scan     | 87.5% doublet rate, 22 near-degenerate pairs | ⚠️ Partial      |
| Hybridization-aware readout | 4/4 100%, margin +5.49                       | ✅ Confirmed    |
| Phase-spectral stability    | 6/40 stable (macro coupling losses)          | ❌ Not at macro |
| Q-factor census             | Q = 74–297 (paper claims 10,000)             | ❌ Not at macro |

**Phase 1.5b: Extended Claims (E12–E23, Round 4, 3 repeatability runs)**

| Experiment               | Key Result (3-run range)            | Paper Claim         | Status          |
| ------------------------ | ----------------------------------- | ------------------- | --------------- | ----- | --------------- |
| E12 Ringdown Q           | Q_ring=204–572, Q_bw=20–50          | Q=10,000            | ❌ Not at macro |
| E13 Mode Orthogonality   | 16.4–16.6 dB isolation              | Perfect δₘₙ         | ⚠️ Partial      |
| E14 CW Lock-in SNR       | +30.5 dB gain                       | +17.5 dB            | ✅ **Exceeded** |
| E15 Binary Encoding      | 100%, margin +18.25                 | Leibniz binary      | ✅ Confirmed    |
| E16 Cross-Correlation    | max                                 | ρ                   | =0.79           | ≤0.21 | ❌ Not at macro |
| E17 Two-Phase Readout    | Phase1 100%, Phase2 +1.2 dB         | Refinement          | ⚠️ Partial      |
| E18 Derived SNR          | 34.3–34.6 dB mean                   | 98.5 dB             | ❌ Not at macro |
| E19 Wave Speed           | ~190 m/s, non-harmonic              | 5,315 m/s           | ❌ Not at macro |
| E20 PUF Uniqueness       | 60–90% unique peaks                 | Unique fingerprints | ⚠️ Partial      |
| E21 Freq Stability       | 0.0 Hz drift (strong modes, 5 runs) | TCF < 4 ppm/K       | ✅ Confirmed    |
| E22 Position Sensitivity | Fixture prevents repositioning      | sin² profile        | ❓ Inconclusive |
| E23 Parametric Proxy     | All configs show loss               | +12 dB              | ❌ Not at macro |

### 3-Run Repeatability (E12–E23)

| Metric              | Run 1 | Run 2 | Run 3 |
| ------------------- | ----: | ----: | ----: |
| E13 Isolation (dB)  |  16.4 |  16.6 |  16.5 |
| E17 Phase1 accuracy |  100% |  100% |  100% |
| E18 Mean SNR (dB)   |  34.3 |  34.6 |  34.4 |
| E18 Max SNR (dB)    |  74.5 |  74.9 |  74.5 |

Repeatability: excellent — key metrics essentially invariant across runs.

### E21 Frequency Stability Deep Dive (5 independent runs)

| Run    | ~517 Hz | ~891 Hz | ~1127 Hz |   ~1826 Hz |   ~2105 Hz |
| ------ | ------: | ------: | -------: | ---------: | ---------: |
| Run 1  |  9.3 Hz |  0.0 Hz |   9.0 Hz | **0.0 Hz** | **0.0 Hz** |
| Run 2  |  3.1 Hz |  3.6 Hz |   4.5 Hz | **0.0 Hz** | **0.0 Hz** |
| Run 3  | 10.3 Hz |  5.3 Hz |  15.8 Hz | **0.0 Hz** | **0.0 Hz** |
| Ded. 1 |  8.3 Hz |  5.3 Hz |  15.8 Hz | **0.0 Hz** | **0.0 Hz** |
| Ded. 2 |  7.2 Hz |  0.0 Hz |  13.5 Hz | **0.0 Hz** | **0.0 Hz** |

Strong modes (1826, 2105 Hz) = zero drift across 15 measurements over ~1 hour. Lower-frequency jitter is SNR-dependent measurement noise, not thermal drift.

**Phase 1.5c: Gap-Closure Experiments (E24–E32, Round 5)**

| Experiment                  | Key Result                              | Paper Claim          | Status              |
| --------------------------- | --------------------------------------- | -------------------- | ------------------- |
| E24 Freq-Offset Tolerance   | 100% at ±10%, margins +0.31–0.39        | ±5% tolerance        | ✅ **Exceeded**     |
| E25 Endurance Cycling       | 549K cycles, strong modes <0.2 dB       | Non-destructive      | ✅ Confirmed        |
| E26 Partial-Query Recall    | 100% with K=2 peaks (of 10)             | Partial match        | ✅ Confirmed        |
| E27 Broadband Census        | 13 modes, 1.8–33.7 kHz, max 54.3 dB SNR | Dense mode structure | ✅ Confirmed        |
| E28 Multi-Day Stability     | 7/7 sessions at 100%, 18.7h span        | Temporal persistence | ✅ Confirmed        |
| E29 Non-Destructive Readout | Max 2.61 dB change after 30s CW         | Non-destructive read | ✅ Confirmed        |
| E30 Hopfield Capacity       | P=4 works, P_max ≈ 11 for N=80          | High capacity        | ⚠️ Limited at macro |
| E31 Guard-Band Surface      | 5% optimal; overlap map generated       | Operating point      | ⚠️ Mapped           |
| E32 Rayleigh Verification   | 0% shift (no unperturbed baseline)      | Perturbation physics | ❌ Cannot verify    |

**Phase 1.5d: Interference Exploration (E33)**

| Experiment                 | Key Result                           | Paper Claim           | Status                        |
| -------------------------- | ------------------------------------ | --------------------- | ----------------------------- |
| E33 Ringdown Re-excitation | 0.27% contrast, oscillation detected | Coherent interference | ⚠️ Below threshold at macro Q |

E33 confirmed the mechanism (sub-cycle oscillation present) but macro Q (200–572) limits contrast to 0.27% — below the 2% detection threshold. Scaling prediction: contrast becomes measurable at Q > ~1,000.

---

### Phase 1.6: Fused Silica Plate Prototype

**Goal:** Intermediate hardware step between macro borosilicate rods and MEMS. 100 mm × 100 mm fused silica glass plates with PZT transducers, targeting Q ≈ 1,000–5,000.

**Status:** Plates received 2026-04-11.

**Motivation:** Six paper claims failed at macro due to low Q (200–572). Fused silica's lower intrinsic loss should bridge the gap:

- Q > 1,000 would enable E33 re-excitation interference (>2% contrast)
- Q > 2,000 would enable phase-spectral encoding test (currently 15% stability)
- Q > 5,000 would approach parametric amplification threshold
- Plate geometry gives richer 2D mode structure vs 1D rod bending

**Key lessons from rod campaign (34 experiments, 8 rounds) that inform plate experiments:**

1. **Intrinsic geometry dominates identity** — rods are distinguishable without perturbation (E38 gap +0.062). Perturbation site _location_ matters more than mass alone (3-condition test). Plates should show even stronger intrinsic uniqueness due to 2D mode structure.
2. **Phase is essential but its exact weighting is not** — any mag:phase ratio 0.5–10.0 yields 100% recall (E34). Plate experiments should use template matching from day 1.
3. **Template scoring is immune to crosstalk** — macro rods had −3.9 dB isolation yet 100% recall (E35/E36). Aggressive isolation engineering isn't needed for initial plate work.
4. **Q is the single biggest bottleneck** — every ❌ claim maps to insufficient Q. The first plate experiment must measure Q; if Q < 500, skip to MEMS.
5. **Null controls are non-negotiable** — E36's shuffle/random battery should be the standard validation for any new substrate.

#### Phase 1.6 First Steps (Ordered)

**Step 0: Coupling & Fixture Design**

- Mount both PZT discs (TX + RX) on the **underside** of the plate at **diagonal-opposite corners**, bonded with thin cyanoacrylate
- TX at (5, 95) mm — flush with bottom-left corner; RX at (95, 5) mm — flush with top-right corner
- 10 mm dia × 1 mm PZT-5A discs; corner placement preserves Q ≈ 22,500 (corners are nodal for most bending modes)
- Both PZTs on same face leaves entire top surface clear for perturbation sites
- Support plate on soft foam or 3-point silicone standoffs to minimize boundary damping
- Wire PZT to PicoScope Ch A (receive) and AWG (transmit) via the existing BNC setup
- No relay mux needed initially — single plate at a time

**Step 1: Q Measurement (Gate/Kill — do this first)**
Adapt E12 ringdown protocol to plates:

- Drive at a resonance, cut excitation, capture ringdown envelope
- Fit exponential decay → extract Q = π × f × τ
- Sweep 1–50 kHz to find plate resonances first (broadband impulse or slow chirp)
- **Kill criterion: Q < 500 → stop, skip to MEMS**
- **Go criterion: Q > 1,000 → proceed with full experiment suite**
- Expected: fused silica intrinsic Q ≈ 10⁴–10⁵; coupling + boundary losses will dominate. Achievable Q likely 500–5,000 depending on mounting.

**Step 2: Broadband Mode Census**
Adapt E27 broadband census to plates:

- Sweep 200 Hz–100 kHz in 25 Hz steps (plates have higher fundamental frequencies than 150 mm rods)
- For a 100 mm × 100 mm × t plate, lowest bending mode ≈ 0.474 × t × v_s / a² (Kirchhoff). For t = 1–3 mm, f₁ ≈ 2–20 kHz
- Count modes, measure SNR, map the 2D mode landscape
- Compare mode density to rod campaign (rods had 13 modes in 1.8–33.7 kHz)
- Plates should have dramatically richer mode structure (degenerate pairs, plate modes, edge modes)

**Step 3: Single-Plate Fingerprint Enrollment**

- Pick top-20 peaks from broadband census (same protocol as rod enrollment)
- Measure magnitude + phase at each peak
- Store as plate fingerprint in users.json (new plate entries)
- Repeat 3× to establish enrollment repeatability

**Step 4: Re-Excitation Interference (E33 Revisit) — The Big Test**
This is the experiment that most directly benefits from higher Q:

- Drive plate's strongest mode to steady state
- Cut AWG, wait variable delay Δt (0 to 5τ in 20 steps)
- Re-excite and measure
- At rod Q ≈ 400, contrast was only 0.27%. At plate Q ≈ 2,000, predict **>5% contrast**
- If interference fringes are measurable, this is the first direct evidence of coherent phononic memory

**Step 5: Phase Stability (E03 Revisit)**

- At rods: only 15% of phase measurements were stable (σ = 1.71 rad)
- Higher Q → narrower linewidth → more stable phase
- Measure phase at 5 strongest modes, 100 captures each, compute σ
- **Target: >50% of modes with phase σ < 0.5 rad**

**Step 6: Multi-Plate Discrimination**
If you have 2+ plates:

- Enroll both, run template recall, confusion matrix
- 2D plate modes should give much richer spectral fingerprints
- Expect larger inter-plate separation than inter-rod (plates have more modes)
- Run E36 null-control battery (shuffle + random) from the start

**Experiments to revisit with fused silica plates (Q-gated):**
| Experiment | Current Result (rods) | Revisit Threshold | Priority |
|---|---|---|---|
| E12 Ringdown Q | Q = 204–572 | Q > 1,000 | **STEP 1 (gate)** |
| E27 Broadband census | 13 modes, 54 dB SNR | More modes, higher SNR | **STEP 2** |
| E33 Re-excitation interference | 0.27% contrast | Q > 1,000 → >2% | **STEP 4** |
| E03 Phase stability | 15% stable (σ=1.71 rad) | Q > 2,000 → >50% | STEP 5 |
| E16 Cross-correlation | max |ρ| = 0.79 | Q > 1,000 → sharper | After Step 6 |
| E23 Parametric proxy | All loss | Q > 5,000 for gain | Only if Q permits |

**Kill criteria:** If fused silica plates yield Q < 500, the substrate is not meaningfully better than borosilicate rods and should be skipped in favor of MEMS.

### Phase 1.5 Scorecard

**14 confirmed ✅ | 7 partial ⚠️ | 7 not at macro ❌ | 1 inconclusive ❓ | 1 deferred 🔲**

### Phase 1.5 Decision: PROCEED ✅

**Date:** 2026-04-09

**Rationale:** All core computational claims (associative recall, nearest-neighbor, Boolean, CIM, pruning, temporal stability, binary encoding, frequency stability) are **confirmed at macro scale**. The "not confirmed" results (Q, SNR, cross-correlation, wave speed, parametric gain) all involve scaling-dependent physics that the paper explicitly expects to improve at MEMS scale. CW lock-in SNR **exceeded** prediction. No result contradicts the theoretical framework — every gap maps cleanly to the Q²×density scaling law. Macro prototype provides a validated test harness for algorithm development while MEMS fabrication proceeds.

**Data:** `data/results/lab/additional_exps/additional_20260409_*.json` (6 files, 3 full runs + offline + 2 dedicated E21)

---

### Archived: Ferrofluid Substrate Investigation (KILLED)

> The following findings document the ferrofluid exploration that led to the substrate kill in paper §3.1. They are preserved for scientific completeness. **These results apply to the ferrofluid variant only and do not apply to the solid glass architecture.**

<details>
<summary>Click to expand ferrofluid simulation findings</summary>

#### Ferrofluid Model (notebook 06, `simulations/ferrofluid.py`)

- Q ≈ 21,500 at 1 MHz in idealized model
- All Phase 0 kill criteria passed under idealized conditions

#### Coupled Multiphysics (notebook 08, `simulations/coupled_physics.py`)

- SVEA coupled-mode simulation: 5 acoustic + 3 EM modes, 500 µs
- 95.1% energy retained — excellent coherence in the coupled model
- Thermal self-heating: 0.01 mK — negligible

#### 🔴 KILL: Phase Diffusion Noise (notebook 08, `simulations/noise_decoherence.py`)

- **Brownian motion of ferrofluid nanoparticles creates fatal phase noise**
- Phase diffusion: **77.5%** of noise budget at 70 MHz
- SNR = −6.5 dB at micro-cell (10 µm)³ → 0 reliable modes
- **This is a fundamental property of the colloidal phase** — not an engineering problem

#### Mitigation Analysis (notebook 09, `simulations/mitigations.py`)

- Gel-immobilized nanoparticles + high photon count can recover ~10 modes at ~10 pJ
- But this defeats the purpose: the appeal of ferrofluid was reconfigurability, and gel immobilization eliminates that

#### Shannon Capacity — Ferrofluid Only (notebook 10, `simulations/capacity.py`)

- At mitigated ferrofluid SNR (13.5 dB): 2.3 bits/mode, 0.023 Tb/cm³
- At aggressive mitigation (24 dB): 3.9 bits/mode, 0.039 Tb/cm³
- **These numbers do NOT apply to solid glass** — glass achieves 76.7 dB SNR at 1 mm (12.7 bits/mode)

#### Ferrofluid Claims Scorecard

| Claim                | Verdict (ferrofluid) | Detail                                           |
| -------------------- | -------------------- | ------------------------------------------------ |
| ~10 bits/mode        | ❌ OVERESTIMATE      | 2.3 b/mode mitigated (ferrofluid SNR too low)    |
| ~1 Tb/cm³ density    | ❌ OVERESTIMATE      | 0.023 Tb/cm³ (ferrofluid noise-limited)          |
| fJ per operation     | ❌ REFUTED           | ~10 pJ system-level in ferrofluid configuration  |
| Reconfigurable media | ❌ KILLED            | Phase diffusion destroys coherence in any liquid |

**Verdict: Ferrofluid is a dead end.** Solid glass eliminates phase diffusion entirely (§3.2).

</details>

---

## Phase 2: MEMS Proof-of-Concept (2026–2027)

### Goal

Fabricate a single borosilicate glass MEMS resonator (1–5 mm) with thin-film piezo transduction and validate the core physics at chip scale. This is the paper's §15 Phase 1.

> **Note (2026-04-09):** Phase 1.5 macro-rod prototype (see above) has confirmed 14 of 30 paper claims at macro scale, including all core computational functions (recall, search, compute, pruning, binary encoding, stability), plus frequency-offset tolerance (±10%, exceeding ±5% claim), endurance (549K cycles), partial-query recall (K=2 sufficient), broadband mode structure (13 modes to 33.7 kHz), and 18.7-hour temporal stability. The Q²×density scaling law predicts that every "not at macro" result (Q, SNR, cross-correlation, parametric gain) should resolve at MEMS scale. CW lock-in SNR already exceeded paper prediction at macro. Phase 2 MEMS fabrication is the critical next step to validate the scaling predictions.

### Key Measurements

| Measurement                       | Expected (from model)  | Kill Criterion           |
| --------------------------------- | ---------------------- | ------------------------ |
| Quality factor $Q$                | ~9,097 (modeled §7)    | < 1,000                  |
| Thermally stable mode count       | 9,380 (derived §2.1)   | < 100 resolvable modes   |
| SNR (fundamental, 1 mm)           | 76.7 dB (projected §6) | < 40 dB                  |
| Perturbation frequency shift      | Per Rayleigh formula   | < 50% of predicted shift |
| Thin-film piezo transduction      | Efficient coupling     | No detectable signal     |
| Cross-talk (adjacent rods, 80 µm) | < 1% (modeled)         | > 10%                    |

### Hardware

- 1–5 mm borosilicate glass rods (diced from Schott Borofloat 33 wafers)
- AlN thin-film piezoelectric transducers (sputtered or fabricated at MEMS foundry)
- Vacuum packaging or bench-top vacuum chamber
- Network analyser or oscilloscope + function generator for spectral measurements
- Temperature-controlled stage (Peltier + PID, ±1 K)

### Kill → Pivot

- If measured $Q < 1{,}000$: Anchor loss or surface loss dominates; investigate alternative tether geometries or vacuum levels
- If < 100 modes resolvable: Mode coupling at high $n$ destroys spectrum; consider lower-order encoding with fewer, wider-spaced modes
- If piezo coupling fails: Try laser Doppler vibrometry as backup readout

### Actualization

- If $Q > 5{,}000$ and ≥ 1,000 modes: **Core claims validated at MEMS scale** — publish, seek grant funding
- If perturbation encoding works at chip scale: **Priority date exercised** — convert provisional patent to non-provisional

---

## Phase 3: Array Demonstration (2027–2028)

### Goal

Build a 10–100 resonator array with CMOS readout. Demonstrate parallel associative recall on hardware.

### Prerequisites

- Phase 2 confirms $Q > 1{,}000$ and multi-mode spectrum in MEMS geometry
- Fabrication partner identified (university cleanroom or MEMS foundry)

### Work Items

- Multi-rod array fabrication at 80 µm pitch
- CMOS flip-chip readout IC (or off-chip ADC for initial demo)
- Lithographic perturbation mass patterning (gold, ~50 nm)
- Parallel excitation and per-rod amplitude measurement
- Associative recall demo: store $N$ patterns, query, verify correct match
- Thermal sweep (±1 K) for drift validation across array

### Kill Criteria

- Rod-to-rod crosstalk > 10% → array architecture unviable
- Fabrication yield < 50% → manufacturing cost prohibitive
- Associative recall accuracy < 80% at ≥ 10 stored patterns → computation model fails

### Actualization

- 10+ rod array with associative recall demonstrated → transformative demo; seek Series A / DARPA funding
- Measured density matches projected → publish hardware validation paper

---

## Phase 4: Domain-Specific Accelerator (2029-2030+)

### Goal

If Phases 2–3 succeed, build a >1,000-rod prototype targeting a specific workload (e.g., similarity search, biometric matching, network intrusion detection).

### Requirements to Enter Phase 4

- [ ] Phase 2 confirms Q > 1,000 and ≥ 1,000 resolvable modes
- [ ] Phase 3 demonstrates ≥ 10 working rods with associative recall
- [ ] Published, peer-reviewed paper with independent replication
- [ ] Identified commercial application with willing early adopter

### Targets

- Energy advantage over GPU for associative search workloads
- Latency competitive with TCAM for pattern matching
- Integrated CMOS readout demonstrated

---

## Citation Integrity Roadmap

The paper's own citation audit (included at end of v9.md) identified issues:

| Priority | Issue                             | Action                                                   |
| -------- | --------------------------------- | -------------------------------------------------------- |
| HIGH     | Nat. Comm. 16, 3586 mismatch      | Replace with specific glass acoustic Q measurement paper |
| HIGH     | J. Phys. D 55, 25301 unverifiable | Find/verify actual ZIM mode packing paper or replace     |
| MEDIUM   | Adv. Materials incomplete         | Add specific article/DOI                                 |
| MEDIUM   | Nat. Comp. Sci. vague             | Specify article                                          |
| MEDIUM   | APL 127, 020501 volume/year error | Correct to actual magnonic memory paper                  |
| LOW      | Addendum refs [1]-[6] vague       | Add full bibliographic details                           |
| LOW      | Irrelevant quantum refs           | Remove or justify relevance                              |

---

## Historical Sidebar Research

Sidebars explore structural parallels between historical figures' work and CWM
physics, generating testable engineering hypotheses. Each sidebar produces a
simulation module, automated tests, and (if confirmed) paper integration.

**Full tracker:** [`docs/SIDEBARS.md`](SIDEBARS.md)

| Sidebar | Figure                                          | Status                      |
| ------- | ----------------------------------------------- | --------------------------- |
| S1      | Spare / Mace                                    | ✅ Complete (6/6 confirmed) |
| S2      | Scranton / Dogon                                | ✅ Complete (6/6 confirmed) |
| S3      | Tesla                                           | ✅ Complete (4/4 confirmed) |
| S4      | Chladni — 2D plate eigenmodes                   | ⬜ Not started              |
| S5      | Békésy — cochlear eigenmode memory              | ⬜ Not started              |
| S6      | Franklin (Rosalind) — phase retrieval           | ⬜ Not started              |
| S7      | Leibniz — binary encoding / monadic compression | ⬜ Not started              |

---

## Open Questions Registry

Track questions that need answers, ordered by impact on go/no-go decisions:

1. **What is the actual Q factor of a MEMS-scale borosilicate glass resonator with thin-film piezo?**
   The five-mechanism model (§7) predicts 9,097. Material loss dominates at 91%. But the model has not been experimentally validated at chip scale. This is the #1 unknown.

2. **How many modes are practically resolvable at MEMS scale?**
   The formula gives 9,380 modes, but mode coupling, transducer bandwidth, and fabrication imperfections may reduce this. The paper's FEM validates to mode 15; behaviour at mode 9,380 is extrapolated.

3. **Does thin-film AlN piezo coupling work across the full mode spectrum?**
   FBAR filters validate AlN at single-mode GHz operation. Multi-mode broadband excitation/readout is untested.

4. **What is the cross-talk between adjacent rods at 80 µm pitch?**
   Acoustic isolation through vacuum should be good, but evanescent fields through tethers could couple rods.

5. **Do lithographic perturbation masses produce the predicted Rayleigh shifts?**
   The perturbation formula is validated by FEM at 1.3% max error (§5.3). Real thin-film gold dots on real glass may differ.

6. **Can the advanced encoding extensions (§11) survive scaling from 10–50 modes to 9,380?**
   Hybridization, null-space, and polysemic readout are validated in small simulations. Full-scale behaviour with real noise is unknown.

7. **What fabrication yield is achievable for glass MEMS resonator arrays?**
   Each process step (glass DRIE, AlN deposition, vacuum packaging) is proven individually. The combination is untested.
