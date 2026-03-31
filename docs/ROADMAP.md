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

| Task                      | Tool/Method                              | Success Metric                                    | Status                                                    |
| ------------------------- | ---------------------------------------- | ------------------------------------------------- | --------------------------------------------------------- |
| Full FDTD with Meep       | [MIT Meep](https://meep.readthedocs.io/) | Validate geometry invariance claim                | 🟡 Scaffolded (`simulations/meep_fdtd.py`)                |
| Multiphysics coupling     | SVEA coupled-mode ODE                    | Acoustic + thermal coupling modeled correctly     | ✅ Done (`simulations/coupled_physics.py`, notebook 08)   |
| Multi-mode interference   | Beam propagation method                  | Demonstrate associative recall in simulation      | ✅ Done (`simulations/interference.py`, notebook 05)      |
| CMOS interface modeling   | Component-level energy budget            | Viable readout SNR at projected energy budget     | ✅ Done (`simulations/cmos_interface.py`, notebook 07)    |
| Grid convergence          | FD + Richardson extrapolation            | Discretization error < 1%                         | ✅ Converged at N≥10 (`simulations/convergence.py`)       |
| Sensitivity analysis      | Parameter sweeps                         | Identify high-risk assumptions                    | ✅ Done (`simulations/sensitivity.py`, notebook 04)       |
| Monte Carlo tamper        | Statistical validation                   | FPR < 10%, FNR < 5%                               | ✅ Done — FPR 4.7%, FNR 0% (exp03, notebook 07)           |
| Claims auto-validation    | Programmatic pipeline                    | All claims auto-populated from experiments        | ✅ Done (`analysis/comparison.py`)                        |

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

| Status    | Count | Details                                                                     |
| --------- | ----- | --------------------------------------------------------------------------- |
| CONFIRMED | 8     | ZIM coherence, 1D/3D drift, modes ±ZIM, density scaling, excitation energy, interference recall, tamper detection, grid convergence |
| PLAUSIBLE | 1     | Geometry invariance (needs Meep or COMSOL)                                  |
| QUALIFIED | 1     | Energy: physics-layer fJ confirmed; system-level ~1 pJ (now documented in paper §8.5) |

#### Remaining Phase 1 Priorities

1. 🔴 Install Meep → resolve geometry invariance (PLAUSIBLE → CONFIRMED/REFUTED)

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

| Claim                | Verdict (ferrofluid) | Detail                                          |
| -------------------- | -------------------- | ----------------------------------------------- |
| ~10 bits/mode        | ❌ OVERESTIMATE      | 2.3 b/mode mitigated (ferrofluid SNR too low)   |
| ~1 Tb/cm³ density    | ❌ OVERESTIMATE      | 0.023 Tb/cm³ (ferrofluid noise-limited)          |
| fJ per operation     | ❌ REFUTED           | ~10 pJ system-level in ferrofluid configuration  |
| Reconfigurable media | ❌ KILLED            | Phase diffusion destroys coherence in any liquid |

**Verdict: Ferrofluid is a dead end.** Solid glass eliminates phase diffusion entirely (§3.2).

</details>

---

## Phase 2: MEMS Proof-of-Concept (2026–2027)

### Goal

Fabricate a single borosilicate glass MEMS resonator (1–5 mm) with thin-film piezo transduction and validate the core physics at chip scale. This is the paper's §15 Phase 1.

### Key Measurements

| Measurement                         | Expected (from model) | Kill Criterion               |
| ----------------------------------- | --------------------- | ---------------------------- |
| Quality factor $Q$                  | ~9,097 (modeled §7)   | < 1,000                      |
| Thermally stable mode count         | 9,380 (derived §2.1)  | < 100 resolvable modes       |
| SNR (fundamental, 1 mm)             | 76.7 dB (projected §6)| < 40 dB                      |
| Perturbation frequency shift        | Per Rayleigh formula   | < 50% of predicted shift     |
| Thin-film piezo transduction        | Efficient coupling     | No detectable signal         |
| Cross-talk (adjacent rods, 80 µm)   | < 1% (modeled)        | > 10%                        |

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

| Priority | Issue                             | Action                                                        |
| -------- | --------------------------------- | ------------------------------------------------------------- |
| HIGH     | Nat. Comm. 16, 3586 mismatch      | Replace with specific glass acoustic Q measurement paper      |
| HIGH     | J. Phys. D 55, 25301 unverifiable | Find/verify actual ZIM mode packing paper or replace          |
| MEDIUM   | Adv. Materials incomplete         | Add specific article/DOI                                      |
| MEDIUM   | Nat. Comp. Sci. vague             | Specify article                                               |
| MEDIUM   | APL 127, 020501 volume/year error | Correct to actual magnonic memory paper                       |
| LOW      | Addendum refs [1]-[6] vague       | Add full bibliographic details                                |
| LOW      | Irrelevant quantum refs           | Remove or justify relevance                                   |

---

## Historical Sidebar Research

Sidebars explore structural parallels between historical figures' work and CWM
physics, generating testable engineering hypotheses. Each sidebar produces a
simulation module, automated tests, and (if confirmed) paper integration.

**Full tracker:** [`docs/SIDEBARS.md`](SIDEBARS.md)

| Sidebar | Figure | Status |
|---------|--------|--------|
| S1 | Spare / Mace | ✅ Complete (6/6 confirmed) |
| S2 | Scranton / Dogon | ✅ Complete (6/6 confirmed) |
| S3 | Tesla | ✅ Complete (4/4 confirmed) |
| S4 | Chladni — 2D plate eigenmodes | ⬜ Not started |
| S5 | Békésy — cochlear eigenmode memory | ⬜ Not started |
| S6 | Franklin (Rosalind) — phase retrieval | ⬜ Not started |
| S7 | Leibniz — binary encoding / monadic compression | ⬜ Not started |

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
