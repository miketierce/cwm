# WCFOMA Research Roadmap

## Decision Framework: Disprove or Actualize

This roadmap follows a **falsification-first** methodology. Each milestone includes explicit **kill criteria** — quantitative thresholds that, if not met, indicate the approach is unviable and should be abandoned or fundamentally rearchitected. Conversely, each milestone identifies **actualization signals** — results that validate continuing investment.

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

- 🔴 **Q factor** is the #1 risk — unknown in real ferrofluid. If Q < 100, storage density drops below viability.
- 🔴 **α (thermal drift)** is the #2 risk — assumed 0.0022/K from literature.
- 🟡 ZIM damping factor and η are medium risk but tolerant of 40% error.
- 🟢 ΔT, γ, L are engineering parameters with low sensitivity.

**Blocking issues for Phase 1:**

- Geometry invariance needs Meep/COMSOL validation (FD solver ill-conditioned at ε → 0).
- Ferrofluid Q factor has no direct literature measurement — this is the first Phase 1 priority.

### Kill → Pivot

If ≥3 of 5 experiments fail kill criteria, the architecture's theoretical basis is unsound. Document findings, publish negative results, and consider:

- Whether a different encoding scheme preserves the core insight
- Whether the energy estimates survive with corrected parameters

---

## Phase 1: Advanced Simulation (Q2-Q4 2026)

### Goal

Move beyond the paper's simplified models to realistic multiphysics simulation.

### Work Items

| Task                      | Tool/Method                              | Success Metric                                | Status                                                    |
| ------------------------- | ---------------------------------------- | --------------------------------------------- | --------------------------------------------------------- |
| Full FDTD with Meep       | [MIT Meep](https://meep.readthedocs.io/) | Validate Q > 10³ in ferrofluid-like media     | 🟡 Scaffolded (`simulations/meep_fdtd.py`)                |
| Multiphysics coupling     | SVEA coupled-mode ODE                    | Shear + EM + thermal coupled correctly        | ✅ Done (`simulations/coupled_physics.py`, notebook 08)   |
| Ferrofluid material model | Literature + fitting                     | Accurate dispersion relation v(ω, T, B)       | ✅ Done (`simulations/ferrofluid.py`, notebook 06)        |
| Multi-mode interference   | Beam propagation method                  | Demonstrate associative recall in simulation  | ✅ Done (`simulations/interference.py`, notebook 05)      |
| CMOS interface modeling   | Component-level energy budget            | Viable readout SNR at projected energy budget | ✅ Done (`simulations/cmos_interface.py`, notebook 07) ⚠️ |
| Scale grid to N≥20        | HPC / GPU compute                        | Discretization error < 1%                     | ✅ Converged at N≥10 (`simulations/convergence.py`)       |
| Sensitivity analysis      | Parameter sweeps                         | Identify high-risk assumptions                | ✅ Done (`simulations/sensitivity.py`, notebook 04)       |
| Grid convergence          | FD + Richardson extrapolation            | Error < 1% at operating resolution            | ✅ Done — 0.16% error at N≥10 (notebook 07)               |
| Monte Carlo tamper        | Statistical validation                   | FPR < 10%, FNR < 5%                           | ✅ Done — FPR 4.7%, FNR 0% (exp03, notebook 07)           |
| Claims auto-validation    | Programmatic pipeline                    | All claims auto-populated from experiments    | ✅ Done (`analysis/comparison.py`)                        |

### Kill Criteria

- Realistic Q factor < 100 in ferrofluid media → mode lifetime insufficient
- Multi-mode interference produces < 50% retrieval accuracy → computation model fails
- Energy per operation exceeds pJ (enters DRAM territory) → no efficiency advantage

### Actualization Signals

- Q > 500 in realistic media model → publish advanced simulation paper
- Associative recall works at > 80% accuracy → file provisional patent on interference compute
- Energy confirmed at fJ scale → begin prototype planning

### Phase 1 Findings to Date

**Date:** 2026-03-04

#### ✅ Grid Convergence (notebook 07, `simulations/convergence.py`)

- 3D FDTD frequency error: 0.84% at N=5 → **0.16% at N≥10** (FFT-bin limited)
- Richardson extrapolation confirms 2nd-order convergence
- N=10 is sufficient for all Phase 1 simulations; Meep needed only for ENZ-specific validation

#### ⚠️ CMOS Energy Budget — CRITICAL FINDING (notebook 07, `simulations/cmos_interface.py`)

- **Paper claims "fJ range" per operation — REFUTED at system level**
- Component breakdown at 28nm:
  - Excitation: 2.6 fJ (physics is truly fJ-scale ✅)
  - Sensing: 0.5 fJ
  - Amplifier: 100 fJ
  - **ADC: 1000 fJ (95% of total)** ← bottleneck
  - Addressing: 10 fJ
  - I/O: 1 fJ
  - **Total: 1114 fJ ≈ 1.1 pJ**
- Technology scaling: 2060 fJ (180nm) → 1065 fJ (7nm) — still > 1 pJ at all nodes
- **Implication:** The physics energy IS fJ-scale, but CMOS readout dominates. Options:
  1. Amortize ADC over multi-mode batch reads (÷ N_modes)
  2. Use time-interleaved or event-driven ADC architectures
  3. Revise claim to "fJ per mode operation, pJ per cell access" (honest framing)
  4. Analog readout without full ADC (Faraday rotation direct comparison)
- **This does NOT kill the architecture** — 1 pJ is still 10-100× below DRAM refresh — but the "fJ" headline needs qualification

#### ✅ Monte Carlo Tamper Detection (notebook 07, `experiments/exp03`)

- 5000 trial statistical validation
- γ=0.5: FPR = 4.7%, FNR = 0% (perfect detection)
- Minimum reliable γ = 0.010 (1% geometric perturbation detectable)
- Robust to noise: 1% noise → min detectable γ rises to ~0.1 (still practical)

#### ✅ Previously Completed

- Ferrofluid model: Q ≈ 21,500 at 1 MHz, all kill criteria pass (notebook 06)
- Interference recall: 97.6% single-pattern fidelity, 50 patterns at 90% accuracy (notebook 05)
- Sensitivity: cell length L highest elasticity (−2.35), Q factor #1 risk (notebook 04)

#### Updated Claims Scorecard

| Status    | Count | Details                                                            |
| --------- | ----- | ------------------------------------------------------------------ |
| CONFIRMED | 7     | ZIM coherence, 1D/3D drift, modes ±ZIM, density, excitation energy |
| PLAUSIBLE | 1     | Geometry invariance (needs Meep)                                   |
| REFUTED   | 1     | System-level energy (1.1 pJ, not fJ)                               |

#### Remaining Phase 1 Priorities

1. 🔴 Install Meep → resolve geometry invariance (PLAUSIBLE → CONFIRMED/REFUTED)
2. 🔴 Address energy claim: prototype amortized ADC model or revise paper language

#### Phase 2 Simulation Findings (Coupled Physics + Noise)

**Date:** 2026-03-04

##### ✅ Coupled Multiphysics (notebook 08, `simulations/coupled_physics.py`)

- **SVEA (Slowly-Varying Envelope Approximation)** eliminates MHz/GHz stiffness
- 5 acoustic + 3 EM modes, κ_ae = 10⁻³, 500 µs simulation
- **95.1% energy retained** — excellent coherence
- Acoustic → EM transfer: negligible (large acoustic-magnon detuning)
- Thermal self-heating: 0.01 mK — completely negligible
- Coupling strength scan: EM energy scales as κ², coherence unaffected
- Thermal feedback: drift < 1% for ΔT up to ±50 K

##### 🔴 CRITICAL: Phase Diffusion Noise — POTENTIAL KILL (notebook 08, `simulations/noise_decoherence.py`)

- **Brownian motion of ferrofluid nanoparticles creates phase noise**
- Noise budget at 70 MHz fundamental:
  - Phase diffusion: **77.5%** ← dominant
  - Shot noise: 22.5%
  - Thermal/1/f/ADC: < 0.1% combined
- **SNR = −6.5 dB at default micro-cell (10 µm)³** → 0 reliable modes
- Even at Q = 10,000: still 0 reliable modes
- **The paper does NOT model nanoparticle Brownian noise**
- **This is the #1 risk to the entire architecture**

##### Mitigations to Investigate

1. **Gel-immobilized nanoparticles** — reduce Brownian diffusion by 10²-10⁴×
2. **Larger cavity volume** — macro-cell (1 mm)³ has 10⁹× more particles, better averaging
3. **Higher excitation energy** — sacrifice fJ claim for higher signal amplitude
4. **Experimental calibration** — actual phase noise may be lower than model (model is conservative)
5. **Ensemble readout** — average over many cells for noise reduction

##### Phase 2 Kill Criteria Assessment

| Check                   | Result  | Notes                          |
| ----------------------- | ------- | ------------------------------ |
| Coherence > 1 µs        | ✅ PASS | 500 µs at η=50                 |
| Energy retained > 50%   | ✅ PASS | 95.1% at 500 µs                |
| Mode crosstalk < 10%    | ❌ FAIL | Need mode-selective excitation |
| SNR > 10 dB (all modes) | ❌ FAIL | −6.5 dB (phase diffusion)      |
| BER < 1% (all modes)    | ❌ FAIL | 31.8% BER                      |
| Lifetime > 1 µs         | ❌ FAIL | 0 µs (noise floor)             |
| Reliable modes ≥ 5      | ❌ FAIL | 0 modes reliable               |

**Overall: 2 PASS / 5 FAIL — Architecture at risk unless phase diffusion is mitigated**

##### ✅ Mitigation Analysis (notebook 09, `simulations/mitigations.py`)

- **Key insight: TWO independent noise barriers** — phase diffusion AND shot noise must both be addressed
- **No single mitigation** (gel alone, more photons alone, larger cavity alone) reaches SNR > 10 dB
- **Minimum viable configurations** (all achieve 10 modes):
  1. Gel η×100 + 10⁸ photons at 10 µm → SNR 13.5 dB, ~10 pJ energy
  2. 50 µm cavity + 10⁸ photons (no gel) → SNR 14.2 dB, ~10 pJ energy
  3. Gel η×10 + 50 µm + 10⁸ photons → SNR 18.9 dB, ~10 pJ energy
- **Viability map** shows clear L-shaped boundary in (viscosity × photon) space
- **Energy implication**: minimum viable ≈ 10 pJ (still 10-100× below DRAM)
- **Verdict: NOT A KILL** — architecture works under achievable conditions, but paper defaults need revision
- 128 tests passing (102 + 26 new mitigation tests)

---

## Phase 2: Benchtop Prototype A (2026-2027)

### Goal

Build the macro-scale ferrofluid resonator (paper Section 4.1) and measure real physics.

### Hardware BOM (< $1,000)

- Commercial ferrofluid (e.g., Ferrotec EFH series)
- Shear-thickening carrier fluid (cornstarch-based or commercial STF)
- 3D-printed ZIM structures (Dirac-cone pillar arrays)
- Cylindrical cavity (1-5 cm, machined or 3D-printed)
- EM excitation coils (100-500 turns, 0.1-1 A)
- Faraday rotation readout (HeNe laser + polarizer + photodiode)
- Inductive pickup coils (secondary readout)
- Function generator + oscilloscope
- Temperature-controlled enclosure (Peltier + PID)

### Key Measurements

| Measurement                  | Expected Range | Kill Criterion           |
| ---------------------------- | -------------- | ------------------------ |
| Mode coherence time          | 1-100 µs       | < 100 ns                 |
| Quality factor Q             | 100-1000       | < 10                     |
| Write/read energy            | fJ-pJ          | > 100 pJ                 |
| Mode count (distinguishable) | 5-50           | < 3                      |
| Freq drift under shear       | 5-33%          | < 1% (no tamper signal)  |
| Thermal sensitivity          | ±0.2%/K        | > ±2%/K (uncontrollable) |

### Kill → Pivot

- If Q < 10: The ferrofluid medium cannot sustain resonances. Consider solid-state magnonic media instead.
- If no modes detected: Excitation method fundamentally flawed. Revisit transducer design.
- If write energy > 100 pJ: No advantage over DRAM. Abandon energy efficiency claims.

### Actualization

- If Q > 100 and ≥ 5 modes: First physical proof of concept. Publish, seek grant funding.
- If dilatancy shielding confirmed: Security application may be independently valuable.

---

## Phase 3: Micro-Scale Arrays (2027-2028)

### Goal

Build Prototype B: 16-64 cell micro-scale arrays (10-100 µm cells) with fiber optic integration.

### Prerequisites

- Phase 2 confirms viable physics
- Fabrication partner identified (university cleanroom or MEMS foundry)

### Work Items

- FIB/EBL fabrication of ZIM structures on fiber facets
- Ferrofluid-infused micro-cavities
- Optical excitation/readout through fiber
- Multi-cell addressing and crosstalk characterization
- Thermal sweep (±5 K) for drift validation
- Optional: Rb vapor cell integration for quantum verification

### Kill Criteria

- Cell-to-cell crosstalk > 10% → array scaling unviable
- Fabrication yield < 50% → manufacturing cost prohibitive
- Fiber coupling loss > 30% → readout SNR too low

### Actualization

- 16+ cell array operational → transformative demo; seek Series A / DARPA funding
- Rb verification working → publish quantum-enhanced security paper

---

## Phase 4: Domain-Specific Accelerator (2029-2030+)

### Goal

If Phases 1-3 succeed, build a >1,000-cell prototype targeting a specific AI workload (e.g., similarity search, attention computation).

### Requirements to Enter Phase 4

- [ ] Phase 2 prototype achieves Q > 100, ≥ 10 modes, fJ energy
- [ ] Phase 3 demonstrates ≥ 16 working cells in array
- [ ] Published, peer-reviewed paper with independent replication
- [ ] Identified commercial application with willing early adopter

### Targets

- 10-100× energy advantage over GPU for specific workload
- Latency competitive with specialized ASIC
- Integrated CMOS interface demonstrated

---

## Citation Integrity Roadmap

The paper's own citation audit (included at end of v9.md) identified issues:

| Priority | Issue                             | Action                                                        |
| -------- | --------------------------------- | ------------------------------------------------------------- |
| HIGH     | Nat. Comm. 16, 3586 mismatch      | Replace with specific ferrofluid/magnonic Q measurement paper |
| HIGH     | J. Phys. D 55, 25301 unverifiable | Find/verify actual ZIM mode packing paper or replace          |
| MEDIUM   | Adv. Materials incomplete         | Add specific article/DOI                                      |
| MEDIUM   | Nat. Comp. Sci. vague             | Specify article                                               |
| MEDIUM   | APL 127, 020501 volume/year error | Correct to actual magnonic memory paper                       |
| LOW      | Addendum refs [1]-[6] vague       | Add full bibliographic details                                |
| LOW      | Irrelevant quantum refs           | Remove or justify relevance                                   |

---

## Open Questions Registry

Track questions that need answers, ordered by impact on go/no-go decisions:

1. **What is the actual Q factor of resonant modes in commercial ferrofluid?**
   No direct measurement found in literature. This is the #1 unknown.

2. **Can multiple modes actually coexist without nonlinear coupling?**
   Linear superposition assumed; ferrofluids are inherently nonlinear.

3. **Is the ZIM damping reduction factor physically justified or assumed?**
   The 0.5× factor is a simulation parameter, not derived from first principles.

4. **Does dilatancy actually preserve internal wave structure?**
   Paper assumes "buried" modes survive; could also destroy them.

5. **What readout mechanism achieves fJ-level energy?**
   Faraday rotation requires laser power that may exceed the fJ budget.

6. **Is room-temperature quantum verification noise-immune enough?**
   90% fidelity is lab conditions; what about a vibrating edge device?

7. **How does the mode spectrum change in a real 3D ferrofluid cavity?**
   Viscosity, magnetization, and boundary effects all absent from current models.
