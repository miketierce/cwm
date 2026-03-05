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

| Task                      | Tool/Method                              | Success Metric                                | Status                                                           |
| ------------------------- | ---------------------------------------- | --------------------------------------------- | ---------------------------------------------------------------- |
| Full FDTD with Meep       | [MIT Meep](https://meep.readthedocs.io/) | Validate Q > 10³ in ferrofluid-like media     | 🟡 Scaffolded (`simulations/meep_fdtd.py`)                       |
| Multiphysics coupling     | COMSOL or custom                         | Shear + EM + thermal coupled correctly        | ⬜ Not started                                                   |
| Ferrofluid material model | Literature + fitting                     | Accurate dispersion relation v(ω, T, B)       | ✅ Done (`simulations/ferrofluid.py`, notebook 06)               |
| Multi-mode interference   | Beam propagation method                  | Demonstrate associative recall in simulation  | ✅ Done (`simulations/interference.py`, notebook 05)             |
| CMOS interface modeling   | SPICE + analog frontend                  | Viable readout SNR at projected energy budget | ⬜ Not started                                                   |
| Scale grid to N≥20        | HPC / GPU compute                        | Discretization error < 1%                     | 🟡 FD convergence study built (`meep_fdtd.fd_convergence_study`) |
| Sensitivity analysis      | Parameter sweeps                         | Identify high-risk assumptions                | ✅ Done (`simulations/sensitivity.py`, notebook 04)              |
| Grid convergence          | FD + Meep comparison                     | Error < 1% at operating resolution            | 🟡 FD done, Meep pending                                         |

### Kill Criteria

- Realistic Q factor < 100 in ferrofluid media → mode lifetime insufficient
- Multi-mode interference produces < 50% retrieval accuracy → computation model fails
- Energy per operation exceeds pJ (enters DRAM territory) → no efficiency advantage

### Actualization Signals

- Q > 500 in realistic media model → publish advanced simulation paper
- Associative recall works at > 80% accuracy → file provisional patent on interference compute
- Energy confirmed at fJ scale → begin prototype planning

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
