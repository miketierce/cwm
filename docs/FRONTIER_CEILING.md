# CWM Frontier Ceiling and Experimental Ladder

**Date:** 2026-06-19
**Purpose:** Define the maximum physically defensible ceiling of the coherent wave memory architecture and the precise experimental ladder that unlocks it. Lean into the capabilities that exist only when computation is done _in the physics itself_, and bind every frontier claim to a mechanism and a falsifier.

**Relationship to existing docs:** This builds on, and does not replace, [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) (the stack), [ROADMAP_FULL_POTENTIAL.md](ROADMAP_FULL_POTENTIAL.md) (the phased plan), [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md) (the bench specs), [PUBLIC_ARCHITECTURE_PACKAGE.md](PUBLIC_ARCHITECTURE_PACKAGE.md) (the public synthesis), and [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md) (the claim ledger). Where those are already correct, this document points to them rather than restating them.

**Evidence rule:** every line is labeled or phrased so its maturity is obvious — MEASURED, DERIVED, SIMULATED, PROJECTED, OPEN, KILLED. "Quantum-like" means only classical-wave structure (non-separability, interference, phase, mode coupling, high-dimensional state). It never means entanglement, quantum speedup, or quantum hardware.

**Discipline that earns the ambition:** every frontier capability below carries a kill criterion. That is exactly what lets the project aim at the ceiling without becoming fiction. A claim with a falsifier attached is a hypothesis; a claim without one is a wish.

---

## 1. Reconciliation Notes (cross-repo claim check)

Cross-checking quantitative claims across the paper, diaries, site, and book surfaced the following.

### Resolved / consistent (no action needed)

- Core measured numbers are consistent across [../paper/v19r.md](../paper/v19r.md), [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md), the June diaries, and the site stats band: 7–15 modes, 42–56 dB SNR, 80/80 classification at 193σ, 4,096 states (8 levels × 4 modes), CHSH S = 2.73 fixed / 2.83 optimized, 0.22% drift over 16.5M cycles, loaded Q = 150–743.

### Inconsistency found: cross-domain hypothesis ledger count

The ledger has grown over time, and three snapshots are in circulation:

| Count                                  | Where                                                                                                                                             | Status                  |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| **99 tested, 67 confirmed, 32 killed** | book `manuscript/app_c_hypothesis_ledger`, `cwm_core.html`, `v18.html`, site homepage, site email templates, `archive/tmp/readme_pre_20260611.md` | **CANONICAL (current)** |
| 87 tested, 51 confirmed, 36 killed     | [../paper/cwm_advanced.md](../paper/cwm_advanced.md) abstract and [../paper/README.md](../paper/README.md) description of it                      | EARLIER SNAPSHOT        |
| 80 tested, 54 confirmed, 26 killed     | book `rewrite/` draft, `BOOK_PLAN.md`, archived `v15–v17`                                                                                         | OLDEST SNAPSHOT         |

**Fixed in this pass (safe, living planning docs):**

- `cwm-book/BOOK_PLAN.md` updated to the canonical 99/67/32.
- `cwm-book/rewrite/app_c_hypothesis_ledger.md` already carries a status note pointing to the canonical ledger (added previously).

**Left as-is, flagged here (paper content, not silently editable):**

- [../paper/cwm_advanced.md](../paper/cwm_advanced.md) states 87/51/36. That is the companion paper's own earlier snapshot; [../paper/README.md](../paper/README.md) accurately describes that file. **Action for a future paper revision:** reconcile `cwm_advanced.md` to the canonical 99/67/32, or add an explicit "as of vX" date to each ledger so the snapshots stop competing.
- The book `rewrite/` chapters (`ch10`, `ch15`) still cite 80/18-sidebars. They belong to a superseded draft already flagged at its ledger; leave until that draft is either promoted or archived.

### Code-hygiene note (not a public claim)

- Several simulation modules still default to a ferrofluid constant (`C_FERROFLUID`) inherited from the pre-glass era — e.g. [../simulations/capacity.py](../simulations/capacity.py), [../simulations/mathieu_parametric.py](../simulations/mathieu_parametric.py). The glass results override it in practice, but the defaults should be migrated to glass-first values so a casual reader of the code does not mistake the substrate. Tracked here, not blocking.

---

## 2. The Compute-With-Physics Thesis

CWM's real differentiator is not that it is a slower analog of a digital chip. It is that **one piece of glass is simultaneously the sensor, the memory, the fingerprint, the feature map, and part of the computation** — and the math is performed by the wave equation, not emulated by transistors.

> Interference performs the dot products. The eigenspectrum is the memory. Manufacturing variance is the identity. Perturbation is the write. Modal decay is the temporal state. Phase relationships are the coherent channel. All of it happens in parallel, in one substrate, at room temperature, at the speed of sound.

Every other architecture _separates_ these functions across different physical devices and pays bandwidth, energy, and latency to move state between them. CWM's ceiling is defined by how many of these functions can be collapsed into the same resonant medium without destroying any of them. That is the bet. Sections 3–4 push it to the limit; Section 5 is how we find out if the bet pays.

---

## 3. Physics-Native Capabilities, Pushed to the Ceiling

Each capability below is stated at its strongest defensible end-state, with the mechanism, where it could beat conventional silicon/photonics, the bottleneck that gates it, and the result that kills the claim.

### 3.1 Interference as physical matrix math

- **Ceiling:** a rank-N acoustic transfer matrix `H` computes `y = Hx` for an N-wide input in a single acoustic settling time, with the multiply-accumulate performed by wave superposition rather than digital MACs. At MEMS scale: ~1 nJ per projection (DERIVED/PROJECTED), ~1 µs settling, with N set by transducer count.
- **Mechanism:** linear superposition of eigenmodes; the measured `H` maps drive amplitudes to readout amplitudes ([../simulations/interference.py](../simulations/interference.py), PFU-1).
- **Where it could win:** energy-per-projection and in-situ operation on physical (acoustic/vibration) inputs that would otherwise need to be digitized first.
- **Bottleneck gate:** B1 (rank). At rank 2, `H` is absorbable by a trained linear layer and is indistinguishable from random (MEASURED — L3 train-through-H).
- **Falsifier:** WL-D3.2 — if energy-per-inference at rank 16 is not below an equivalent digital matmul, the physical-projection advantage is closed and `H` becomes a curiosity, not a compute primitive.

### 3.2 The eigenspectrum as high-dimensional memory and associative search

- **Ceiling:** a single device stores and searches >10^5 templates by spectral overlap, returning the best match in one propagation cycle (~3.8 µs read at MEMS scale, DERIVED). Capacity scales multiplicatively across modes × levels × phases × spots × devices.
- **Mechanism:** matched-filter overlap computed by interference; argmax over physical response (PFU-2). MEASURED today at 4,096 states / 100% / 193σ in one session.
- **Where it could win:** content-addressable / associative recall without a von Neumann fetch loop; the comparison is the physics.
- **Bottleneck gate:** B1 for true parallel multi-template readout; cross-session stability for it to be a device property.
- **Falsifier:** WL-A5 — cross-session accuracy < 95% means the "memory" is a session artifact, not stored state.

### 3.3 Perturbation-encoded non-volatile state — surface and volumetric

- **Ceiling (surface):** a mass/coating pattern writes a k-dimensional, position-encoded, physically persistent eigenfrequency-shift vector — a non-volatile register requiring no power to retain (PFU-4).
- **Ceiling (volumetric, the real frontier):** femtosecond laser inscription writes density perturbations _inside_ the glass volume, turning a 2D surface register into a 3D mode-tensor memory. The generalized Rayleigh formula handles volumetric Δρ identically to surface Δm ([../simulations/volumetric_inscription.py](../simulations/volumetric_inscription.py), SIMULATED). This is the same physics behind 5D optical storage, applied to acoustic eigenmodes.
- **Mechanism:** Rayleigh perturbation, Δf_n/f_n = −½ ∫Δρ|u_n|²dV / ∫ρ₀|u_n|²dV.
- **Where it could win:** write-once archival/identity memory with extreme retention and radiation tolerance; 3D density of addressable perturbation sites.
- **Bottleneck gate:** B1 (need rank to read the higher-dimensional shift vector); fabrication for volumetric write.
- **Falsifier:** WL-A2/E3 — surface shifts < 3σ at 10 mg, or not position-dependent, kills the write claim at macro; volumetric falsifier is R² < 0.99 between volumetric and surface sensitivity profiles (H-V1).

### 3.4 Volatile modal dynamics as a temporal reservoir

- **Ceiling:** the natural ring-down and interference of high-Q modes _is_ the reservoir — a physical recurrent network for real-time temporal signals (speech, vibration, anomaly), at micro-watt power.
- **Mechanism:** τ = Q/(πf); at MEMS Q = 10^4 and f = 10 MHz, τ ≈ 320 µs, giving usable memory at 3–10 kHz symbol rates (PROJECTED).
- **Where it could win:** edge time-series inference where the dynamics are free because they are the substrate's own physics.
- **Bottleneck gate:** B2 (the Q·f time constant). At bench, τ ≈ 1–4 ms with an ~8 Hz update loop — temporal memory is real but inaccessible (MEASURED NEGATIVE).
- **Falsifier:** WL-D3.1 — memory capacity MC < 3 at ≥3 kHz on a fabricated die kills acoustic reservoir computing at MEMS scale.

### 3.5 Classical "quantum-like" information structure

- **Ceiling:** a $50, room-temperature, solid-state platform that reproduces the _mathematical structure_ of quantum information across frequency × space × phase degrees of freedom — non-separability (CHSH/GHZ), contextuality (KCBS), and interference-based amplitude amplification (Grover-analog over an N-dimensional classical wave space).
- **Mechanism:** Qian–Eberly classical non-separability; phase-coherent interference. MEASURED today at CHSH S = 2.83.
- **Where it could win:** the clearest cheap classical testbed for quantum formalism; an honest bridge to _real_ quantum acoustics (the identical high-Q-mode-in-low-loss-dielectric architecture is a quantum platform at ~10 mK, Chu et al. 2017).
- **Bottleneck gate:** phase control quality (B1-adjacent for multi-DOF readout).
- **Falsifier:** fixed-angle S < 2.0, or tri-partite witness below the separable bound, reduces these to descriptive geometry. **Hard line:** no entanglement, no speedup, no loophole claims — S = 2√2 from a classical plate is a statement about DOF non-separability, full stop.

### 3.6 Parametric mode network as a room-temperature Ising/optimization fabric

- **Ceiling:** N parametrically pumped modes become N Ising spins (0/π bistable phase states); engineered inter-mode coupling J_ij encodes a QUBO/MaxCut instance; the network relaxes to low-energy configurations — a room-temperature, micro-watt phononic coherent Ising machine that is also per-die unique (optimizer + PUF in one device).
- **Mechanism:** Mathieu/Floquet parametric instability; gain ≥ 10 dB at ε < 0.1 in the first tongue ([../simulations/mathieu_parametric.py](../simulations/mathieu_parametric.py), SIMULATED). Precedents: NTT optical CIM, Toshiba SBM, Goto KPO.
- **Where it could win:** room-temperature operation and physical uniqueness versus cryogenic or laser-table optical CIMs; compactness and power versus oscillator Ising machines.
- **Bottleneck gate:** B2 — parametric threshold needs Q ≳ 5×10³, i.e. MEMS/vacuum.
- **Falsifier:** WL-D3.3 — no oscillation at max safe drive for Q ≈ 10^4 pushes the Ising arc to Q > 10^5 (cryo/crystalline) or kills the room-temperature version.

### 3.7 Substrate unity — the capability no separated architecture has

- **Ceiling:** a single fabricated die that is at once the sensor, the non-volatile identity, the associative memory, the analog feature map, and the optimization fabric — with no data movement between those functions because they are the same modes of the same glass.
- **Mechanism:** all five functions are different read/write modalities on one eigenspectrum (Section 6 of the architecture doc; the multiplexing capacity law N_modes × N_levels × N_phases × N_spots × N_devices).
- **Where it could win:** this is the thesis. The win is not any single function beating a specialist chip; it is collapsing five chips into one physical object and deleting the interconnect.
- **Bottleneck gate:** B1 and B2 together, plus nonlinear switching (Section 5 ladder, rungs R3–R7).
- **Falsifier:** if every function individually loses to a specialist on its own axis _and_ substrate unity adds no system-level energy/latency win, the unity thesis reduces to elegance without advantage. The decisive test is a system-level J/op and latency comparison at MEMS scale, not any single-function benchmark.

---

## 4. The Two Bottlenecks Are the Master Variables

Every ceiling in Section 3 reduces to two numbers. This is the single most important strategic fact in the program.

| Capability                               | Gated by B1 (rank)  | Gated by B2 (Q·f / τ) | Breakable?                           |
| ---------------------------------------- | ------------------- | --------------------- | ------------------------------------ |
| Interference matrix math (3.1)           | ✔ primary           | —                     | Engineering (optical/array readout)  |
| Associative memory (3.2)                 | ✔                   | —                     | Engineering                          |
| Perturbation write, surface+volume (3.3) | ✔ (read rank)       | —                     | Engineering + fab                    |
| Temporal reservoir (3.4)                 | partial             | ✔ primary             | Engineering (MEMS Q, faster capture) |
| Quantum-like structure (3.5)             | partial (multi-DOF) | —                     | Engineering                          |
| Parametric Ising (3.6)                   | —                   | ✔ primary             | Engineering (MEMS Q ≥ 5×10³)         |
| Substrate unity (3.7)                    | ✔                   | ✔                     | Both, plus nonlinearity              |

**B1 — readout rank.** Two receivers ⇒ rank-2 `H`. Below rank ~8 the physical computation is real but invisible (absorbable by trained layers). Unlock: non-contact optical readout or an N-element transducer array.

**B2 — the Q·f time constant.** τ = Q/(πf). At bench, τ ≈ 1–4 ms against an ~8 Hz loop — temporal computation and parametric thresholds are out of reach. Unlock: MEMS + vacuum (Q ≥ 10^4) where the _same physics_ gives usable memory and parametric gain.

**Both are engineering walls, not physics walls.** That sentence is the difference between a fundable frontier and science fiction. The ladder in Section 5 is ordered to hit these two walls as early and cheaply as possible.

---

## 5. The Experimental Ladder to Fully Actualized Hardware

> **No-fab embodiment:** the entire ladder below can be walked at desk/briefcase scale using a plate array instead of a MEMS die — see [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md). The array breaks B1 (optical readout) and B2 (FPGA streaming + vacuum/Q-control) electronically rather than by miniaturization.

Ordered so each rung unlocks the next frontier capability. Each rung lists the gate it opens. Bench-accessible rungs come first because they are cheap and they de-risk everything above them.

| Rung | Experiment (worklist ID)               | Mechanism tested                                  | Success criterion                              | Kill criterion                               | Unlocks                             | Where               |
| ---- | -------------------------------------- | ------------------------------------------------- | ---------------------------------------------- | -------------------------------------------- | ----------------------------------- | ------------------- |
| R0   | Signal-path null (WL-A1/E-W1)          | Acoustic vs electrical origin on current topology | Lifted/coupled < 1% all modes                  | > 5% ⇒ re-isolate, halt                      | Trust in every spectral claim       | BENCH now           |
| R1   | Perturbation write E3 (WL-A2)          | Rayleigh surface mass→shift, position-coded       | > 3σ at ≥10 mg, position-dependent, reversible | < 3σ at 10 mg ⇒ write dead at macro          | 3.3 surface memory, 3.2 sensing     | BENCH now           |
| R2   | Cross-session + all-decoder (WL-A5/A3) | Fingerprint is a device property                  | ≥95% cross-day; multiple decoders >95%         | <95% ⇒ PUF session-local                     | 3.2 memory, PUF use case            | BENCH now           |
| R3   | Rank-N optical readout (WL-B1)         | Break B1 with non-contact N-spot scan             | SNR ≥20 dB, effective rank ≥6                  | <20 dB after 2 wk ⇒ fall back to micro-PZT   | 3.1 matrix math, 3.7 unity          | BENCH next          |
| R4   | F10 redistribution matrix (WL-B2)      | Is macro mode-coupling genuinely nonlinear?       | Hot spots survive harmonic/IM nulls            | Explained by harmonics/IM ⇒ close F10        | Possible **bench** nonlinear switch | BENCH next          |
| R5   | Coherent phase switch (WL-B9)          | Phase-controlled constructive/destructive gate    | Clean ON/OFF contrast                          | No contrast ⇒ defer to MEMS                  | Stage-2 linear gate                 | BENCH               |
| R6   | Volumetric write study (S21 sim → fab) | 3D laser-inscribed density perturbation           | Volumetric/surface sensitivity R² ≥ 0.99       | R² < 0.99 ⇒ surface-only                     | 3.3 volumetric memory ceiling       | SIM now / fab later |
| R7   | MEMS design study (WL-D1)              | Q, mode, rank, energy budget on paper             | Q ≥ 10^4 modeled with error bars               | Model Q < 10^3 floor ⇒ rescope               | Gates all MEMS rungs                | DESIGN now          |
| R8   | MEMS Q + rank (WL-D fab)               | Realize B1+B2 unlock in silicon                   | Q ≥ 10^4, rank ≥ 8 measured                    | Q < 10^3 ⇒ niche-only pivot                  | 3.1, 3.4, 3.7                       | MEMS                |
| R9   | MEMS temporal reservoir (WL-D3.1)      | τ-matched memory at kHz symbol rate               | MC ≥ 3 at ≥3 kHz                               | MC < 3 ⇒ reservoir dead, publish negative    | 3.4 reservoir                       | MEMS                |
| R10  | Nonlinear gate + latch (WL-D4/D3.3)    | Duffing IM gate; parametric 0/π latch             | Working AND + persistent latch                 | No bistability at safe drive ⇒ Q>10^5 needed | Stage-3/4 logic                     | MEMS                |
| R11  | Parametric Ising N-spin (WL-E1/E2)     | Coupled bistable phase network solves QUBO        | Correct ground states on small instances       | No threshold ⇒ hand to cryo community        | 3.6 optimizer, 3.7 unity            | MEMS                |

**Reading the ladder:** R0–R6 are bench/sim and cheap (the architecture doc's BOM is ~$200–300 for the bench-accessible phases). They decide whether the surface memory, sensing, rank, nonlinearity, and volumetric-write claims survive _before_ any fabrication spend. R7 is a publishable paper with no fab dependency. R8–R11 are the MEMS payoff and require a fabrication partner.

---

## 6. Highest-Leverage Experiments (where uncertainty collapses fastest)

If forced to rank by uncertainty-reduction per dollar:

1. **R1 / E3 perturbation write.** Single most informative bench experiment. It simultaneously decides the write mechanism, the sensor use case, and the Rayleigh foundation under the whole architecture. Cheap. Do it first after R0.
2. **R3 optical readout.** The single highest-leverage _hardware_ upgrade. Breaking rank-2 is the precondition for interference-as-compute (3.1), true associative parallelism (3.2), and the unity thesis (3.7). < $100.
3. **R4 F10 resolution.** A coin-flip with enormous payoff: if the April-24 redistribution is genuine nonlinearity, a compute primitive exists _at bench scale_ and the MEMS dependency for switching weakens. One focused week.
4. **R8 MEMS Q.** The number that decides B2 for real. Everything temporal and parametric rides on Q ≥ 10^4 in vacuum-packaged silica.
5. **R10/R11 parametric threshold.** The gate to the entire frontier (logic + optimization). The first proof is not a big optimizer — it is one mode pumped at 2f showing a stable 0/π state.

---

## 7. Fully Realized Hardware (the end-state device)

Assuming the ladder succeeds, the actualized device is:

```
Fused-silica MEMS phononic processor die
  - 1 mm × 1 mm × ~50 µm resonant plate/membrane (modes ~3.5–35 MHz)
  - AlN thin-film transducer array, 8–16 elements (native rank-N drive + readout)
  - Phononic-crystal anchor isolation (literature Q·f up to 10^13–10^14 in silica/quartz)
  - Wafer-level vacuum packaging (Q ≥ 10^4)
  - Lithographic + laser-inscribed perturbation sites (surface ROM + volumetric 3D write)
  - CMOS control die (flip-chip): A-DAC, A-ADC, threshold layer, shadow registers, FFT/correlator
```

**Capabilities at full actualization (all PROJECTED, gated by Section 5):**

| Function            | End-state spec                                                                       | Status path  |
| ------------------- | ------------------------------------------------------------------------------------ | ------------ |
| Identity (PUF)      | Per-die unique spectral fingerprint, reliability >95%                                | R2 → R8      |
| Non-volatile memory | Surface + volumetric perturbation register, indefinite retention, radiation-tolerant | R1 → R6 → R8 |
| Associative search  | >10^5 templates, ~µs match                                                           | R2 → R3 → R8 |
| Analog feature map  | rank-8–16 H, ~1 nJ/projection                                                        | R3 → R8      |
| Temporal reservoir  | MC ≥ 3 at 3–10 kHz, µW power                                                         | R7 → R9      |
| Optimization        | Room-temperature N-spin phononic Ising                                               | R10 → R11    |
| Substrate unity     | All of the above on one die, no interconnect                                         | R8 → R11     |

This is the one-sentence ceiling: **a room-temperature piece of engineered glass whose memory, identity, input transform, temporal dynamics, and optimization are all the same modes — programmed by drive, written by perturbation, read by interference.**

---

## 8. Competitive Landscape

CWM should not be sold as a CPU, a memory chip, or a quantum computer. It occupies an unusual and defensible middle.

| Field                                 | CWM position at full actualization                                                              |
| ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| CMOS CPU/GPU                          | Not a speed competitor. A co-processor / in-sensor front-end.                                   |
| DRAM / NAND / PCM / ReRAM             | Not bulk memory. A spectral identity + associative + write-once register.                       |
| Photonic processors (e.g. Akhetonics) | Slower, but cheaper, room-temperature, physically unclonable, writable post-fab, robust.        |
| Memristor analog AI                   | Lower density/speed, but more stable as a physical feature map and natively coupled to sensing. |
| MEMS resonant sensors                 | A major extension: a multi-mode spectral state space, not a single resonance.                   |
| Physical reservoir computing          | Directly competitive for edge temporal signals if R9 passes.                                    |
| Optical coherent Ising machines       | Slower, but room-temperature, compact, micro-watt, per-die unique.                              |
| Quantum computers                     | Not a competitor. A classical analog/bridge platform; only quantum at mK in a different regime. |
| Hardware PUFs                         | Strongly competitive: a richer, cheaper, physically-rooted fingerprint.                         |

**Where CWM wins** is precisely where physics gives something silicon buys expensively: physical unclonability, multi-mode sensing, in-substrate feature extraction, room-temperature optimization, and substrate unity. **Where it does not pretend to win:** general-purpose digital compute, high-throughput AI training, commodity storage, precision numerics, universal quantum computation.

---

## 9. The Bold Thesis and the Evidence Ladder Beneath It

The fundable, defensible, ambitious framing:

> **CWM is a phononic substrate where one piece of glass is simultaneously the sensor, the memory, the fingerprint, the feature map, and the computer — performing its core operations in the physics of wave interference at room temperature.**

That thesis is allowed to be bold _because_ every rung beneath it has a number, a mechanism, and a kill criterion (Section 5). The near-term public and grant posture leads with the measured base (fingerprinting, non-separability, sensing) and presents the full processor as the contingent frontier — not the premise a reviewer must accept on page one. See [PUBLIC_ARCHITECTURE_PACKAGE.md](PUBLIC_ARCHITECTURE_PACKAGE.md) §"Best Public Narrative" and [ROADMAP_FULL_POTENTIAL.md](ROADMAP_FULL_POTENTIAL.md) §10 decision calendar.

---

## 10. Canonical References and Evidence Gaps

**Canonical public references:** [../paper/v19r.md](../paper/v19r.md) (measured science), [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md) (claim ledger), [ROADMAP_FULL_POTENTIAL.md](ROADMAP_FULL_POTENTIAL.md) (plan), [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md) (bench specs), [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) (stack), this document (ceiling + ladder).

**Claims that need stronger evidence before public or academic presentation** (mirrors and extends [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md)):

| Claim                             | Required evidence                                                         | Rung        |
| --------------------------------- | ------------------------------------------------------------------------- | ----------- |
| Plate stores writable memory      | E3 surface shifts >3σ, position-coded, reversible                         | R1          |
| Fingerprint is a device property  | Cross-session + multi-device PUF metrics                                  | R2          |
| Interference beats digital matmul | Rank ≥8 readout + J/inference comparison                                  | R3 → R8     |
| Volumetric 3D memory              | Volumetric/surface sensitivity R² ≥ 0.99, then fab                        | R6          |
| Macro nonlinear switching         | F10 survives harmonic/IM nulls                                            | R4          |
| Temporal reservoir                | MC ≥ 3 at ≥3 kHz on a die                                                 | R9          |
| Room-temperature phononic Ising   | Parametric threshold + correct small-instance ground states               | R10–R11     |
| Substrate-unity advantage         | System-level J/op and latency win at MEMS scale                           | R8 → R11    |
| Quantum-like beyond CHSH          | Pre-registered GHZ/KCBS/Grover analogs with classical resource accounting | WL-C1/C2/C3 |

**The standing rule:** aim at the ceiling, attach a falsifier to every rung, and let each "no" become a published negative result and a documented pivot. That is how the project stands at the edge of the possible with enough rigor that others can follow.
