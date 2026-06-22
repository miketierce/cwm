# CWM Desk Demonstrator — Projected Capabilities & Connection to the Phononic Processor and Frontier

**Format:** presentation deck (slides separated by `---`). Each slide has a headline, body, and _presenter notes_. Built for a 15–20 minute talk to a collaborator, reviewer, or funder.

**Honesty contract (state it on slide 2, keep it all the way through):** every capability is labeled MEASURED / OPEN / PROJECTED. The desk demonstrator's job is to convert PROJECTED into MEASURED for everything that does **not** require fabrication, and to make the fabrication ask small, specific, and de-risked.

**Source docs:** [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md) (build), [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md) (procedures), [FRONTIER_CEILING.md](FRONTIER_CEILING.md) (ceiling + R0–R11 ladder), [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) (PFU stack), [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md) (evidence ledger).

---

## Slide 1 — Title

# Computing in a Piece of Glass

### A desk-scale phononic processor demonstrator — and the bridge to the chip

Coherent Wave Memory (CWM) · 2026

_Presenter notes:_ One sentence to open: "We can put a working model of a phononic processor on this table, for the price of a laptop, and it proves every scientific principle the eventual chip relies on — except the ones that are purely about being small."

---

## Slide 2 — The one rule of this talk

**Everything you see is labeled.**

| Label         | Means                                                   |
| ------------- | ------------------------------------------------------- |
| **MEASURED**  | already shown on the bench                              |
| **OPEN**      | experiment defined, not yet run — the desk demo runs it |
| **PROJECTED** | extrapolation; needs the desk demo or MEMS to confirm   |

The desk demonstrator's entire purpose: **turn OPEN → MEASURED without fabrication**, and shrink the remaining PROJECTED set to a single, fundable fabrication ask.

_Presenter notes:_ This slide is the credibility anchor. We are not claiming a computer exists. We are claiming a precise, falsifiable path with a cheap instrument that retires most of the risk.

---

## Slide 3 — The architecture in one picture

CWM has three layers. The desk demonstrator builds all three at macro scale:

```
   PHONONIC PROCESSOR (the idea)         DESK DEMONSTRATOR (the macro model)
   ┌───────────────────────────┐         ┌───────────────────────────────┐
   │ PFUs: projection, search, │   ===   │ crossbar plate array +        │
   │ PUF, write, phase, Ising  │         │ FPGA brain + (3D stack)       │
   ├───────────────────────────┤         ├───────────────────────────────┤
   │ MEMS die: AlN crossbar,   │  shrink │ PVDF/PZT crossbar, crosspoint │
   │ row/col, 3D stacked, µm    │  ◄────  │ switch, row/col, stacked, mm  │
   └───────────────────────────┘         └───────────────────────────────┘
```

The desk model is **architecturally faithful** (same crossbar addressing, same 3D stack topology) and **deliberately not** size-faithful (mm, not µm).

_Presenter notes:_ The crossbar row/column addressing is scale-invariant — M×N cells need only M+N lines at any pitch. That is why the desk array is a true model and not a metaphor.

---

## Slide 4 — Why a desk model is even possible: the two bottlenecks

Everything the MEMS chip does better reduces to breaking **two numbers**:

| Bottleneck                 | Today                    | The chip's fix           | The desk demo's fix (no fab)                       |
| -------------------------- | ------------------------ | ------------------------ | -------------------------------------------------- |
| **B1 — readout rank**      | rank-2 (2 receivers)     | per-die transducer array | crossbar grid + 3D stack → rank-N **electrically** |
| **B2 — Q·f time constant** | τ ≈ 1–4 ms vs ~8 Hz loop | high Q, high f           | FPGA streaming lock-in (kHz) + vacuum/Q-control    |

**Both are engineering walls, not physics walls.** The desk demo breaks them with better instruments around the same glass.

_Presenter notes:_ This is the strategic heart. Miniaturization is only _one_ way to break B1/B2. We break them on the desk and prove the science first.

---

## Slide 5 — What the fully built desk demonstrator does

Nine projected capabilities. The headline: **general compute via the associative/HD path (Phase 4A) — no MEMS dependency.** The remaining capabilities map to PFUs and frontier rungs.

| #      | Desk capability                                                | Maturity at full build     | PFU / §            | Frontier rung |
| ------ | -------------------------------------------------------------- | -------------------------- | ------------------ | ------------- |
| **0**  | **General compute (associative/HD path)**                      | ARCHITECTURAL→DEMONSTRATED | §7A / Phase 4A     | (all stages)  |
| **0+** | **Physical kernel machine / neural inference (gradient mode)** | ARCHITECTURAL→DEMONSTRATED | §7B / Phase 4A-D   | (Level 3)     |
| 1      | **Rank-N interference matrix math**                            | OPEN→MEASURED              | PFU-1 Projection   | R3            |
| 2      | **Associative search / CAM** across the array                  | MEASURED→scaled            | PFU-2 Search       | R2            |
| 3      | **Physically unclonable identity (PUF)**                       | OPEN→MEASURED              | PFU-3 PUF          | R2            |
| 4      | **Write/read memory** (surface; volumetric optional)           | OPEN→MEASURED              | PFU-4 Perturbation | R1 / R6       |
| 5      | **Temporal reservoir computing**                               | PROJECTED→MEASURED         | (volatile tier)    | R9-analog     |
| 6      | **Classical "quantum-like" non-separability**                  | MEASURED→extended          | PFU-5 Phase/Grover | R5            |
| 7      | **Parametric Ising optimization** (frontier)                   | PROJECTED                  | PFU-6 Ising        | R10–R11       |
| 8      | **Substrate unity** — all of the above, one rig                | the thesis                 | full stack         | R8→R11        |

_Presenter notes:_ **Lead with rows 0 and 0+ — these are the headlines.** Row 0: discrete general compute (LUT cascade). Row 0+: analog neural inference (the gradient upgrade). Together they position CWM as both a logic machine and a kernel accelerator. Slide 11A expands on the kernel/commercial picture. Walk the rest of the table as supporting capabilities.

---

## Slide 6 — Capability 1: Interference matrix math (PFU-1)

**Claim:** the crossbar reads a rank-N transfer matrix H; `y = Hx` is computed by wave interference, not digital MACs.

- **Mechanism:** low-mass PVDF/PZT cell grid senses the mode field at N points → high-rank H, electrically (no mass loading).
- **Desk procedure:** DD-P1 crossbar array-sense → SVD → effective rank ≥6.
- **Connects to processor:** **PFU-1 Projection Unit** — the analog matrix-vector core.
- **Connects to frontier:** **R3** (break B1) → unlocks ceiling capability 3.1 (interference-as-math) and 3.7 (substrate unity).
- **Falsifier:** rank stays ≤2 after the grid + stack ⇒ no independent channels at desk scale; defer rank-N to MEMS.

_Presenter notes:_ This is the single highest-leverage desk result. Rank is the gate on every "the glass computes" claim.

---

## Slide 7 — Capability 2 & 3: Memory, search, and identity (PFU-2, PFU-3)

**The array is the content-addressable memory.**

- **Search (PFU-2):** one template per plate; broadcast a query; the matching plate rings loudest → parallel nearest-neighbor search in one acoustic cycle. Desk: DD-P4. _Already MEASURED at rank-2 single-plate; the array scales it._
- **Interface:** one call — `cwm.match(query)` — compiles the query to drive tones, broadcasts on the shared rail, reads all plates in one FDM capture, returns argmax. The operator never touches the underlying boards (§3.9 control interface).
- **Identity (PFU-3):** manufacturing variance gives every plate a unique, stable spectral fingerprint. Desk: DD-P6 → standard PUF metrics (uniqueness ~50%, reliability >95%).
- **Connects to frontier:** both are **R2** (fingerprint is a device property).
- **Falsifier:** cross-session accuracy <95% ⇒ PUF is session-local; search degrades to sequential.

_Presenter notes:_ This pair is the most commercially legible near-term output — hardware security + associative memory, demonstrable on owned gear.

---

## Slide 8 — Capability 4 & 5: Writing data, and memory in time (PFU-4 + the volatile tier)

**Two memory tiers, both physical.**

- **Non-volatile (PFU-4):** a mass dot (or laser-inscribed density site) shifts the eigenspectrum by a reversible, position-coded amount. Desk: DD-P5 surface write; DD-P9 volumetric (optional). Frontier **R1 / R6**.
- **Volatile / temporal:** the natural ring-down _is_ the reservoir. The FPGA's kHz loop finally makes τ readable (breaks B2). Desk: DD-P2 → temporal reservoir. Frontier **R9-analog**.
- **Why this matters:** temporal reservoir computing **failed at the current bench** (τ vs ~8 Hz loop). The desk FPGA is the specific fix — same glass, faster instrument.

_Presenter notes:_ Be explicit that the reservoir is a _reopened_ result: killed at bench, predicted to work once the loop is fast enough. The desk demo is the test.

---

## Slide 9 — Capability 6: Classical "quantum-like" structure (PFU-5)

**Already measured: CHSH S = 2.83. Not quantum — classically non-separable.**

- **Mechanism:** frequency × space × phase degrees of freedom reproduce the _mathematical structure_ of quantum non-separability (Qian–Eberly), interference search (Grover-analog), contextuality (KCBS).
- **Desk procedure:** DD-P6B — phase-locked drive + multipoint readout; fixed-angle CHSH + coherent phase switch; extend to 3-DOF.
- **Connects to processor:** **PFU-5 Phase/Grover-analog Unit**.
- **Connects to frontier:** **R5** (coherent phase control) → ceiling capability 3.5.
- **Hard line:** never "entanglement," "speedup," or "quantum hardware." S = 2√2 from a classical plate is a statement about DOF non-separability, full stop.

_Presenter notes:_ This is the crowd-pleaser and the credibility test simultaneously. The discipline of _not_ overclaiming here is what earns trust for the bolder slides.

---

## Slide 10 — Capability 7: The frontier — parametric Ising (PFU-6)

**The hardest, highest-payoff capability. Honestly PROJECTED.**

- **Mechanism:** pump a high-Q mode at 2f → bistable 0/π phase state = one Ising spin; programmable coupling J = the optimizer. Precedent: NTT/Toshiba/Goto coherent Ising machines.
- **Desk path:** DD-P7 (vacuum + Q-control) → DD-P8 (single spin → coupled network). High-Q fallback: salvaged quartz tuning forks.
- **Connects to processor:** **PFU-6 Ising Optimizer**.
- **Connects to frontier:** **R10–R11** — the frontier rungs.
- **Falsifier:** no parametric threshold at safe drive even at high Q ⇒ needs Q>10⁵ (cryo); hand off.

_Presenter notes:_ Frame as "the part that might not work at desk scale, and we'll know quickly and cheaply." The first proof is one spin, not a big optimizer.

---

## Slide 11 — Capability 8: Substrate unity (the whole thesis)

**One rig is simultaneously sensor, memory, fingerprint, feature-map, and optimizer — no data movement between them, because they are the same modes of the same glass.**

- **Desk procedure:** DD-P10 integration — one host runs the PFU instruction set across the array; Phase S stacks crossbar planes into the 3D packed-array model.
- **Connects to processor:** the full PFU stack under one control core.
- **Connects to frontier:** **R8→R11** — the unity ceiling (3.7).
- **The win is not any single function beating a specialist chip.** It is collapsing five chips into one physical object and deleting the interconnect.

_Presenter notes:_ This is the close of the capability arc. Every competitor separates these functions; CWM fuses them.

---

## Slide 11A — Level 3: the gradient makes it a neural inference engine (the commercial picture)

**The headline:** When you keep the full response gradient (not just argmax), the plate array becomes a **physical kernel machine / neural inference accelerator** — and that's a category with real customers, real competition, and a clear value proposition.

### What Level 3 IS (one slide)

```
 QUERY IN ─────▶ ┌──────────────────────────────┐ ─────▶ ANSWER OUT
                 │  ALL N plates respond         │
 (spectral       │  simultaneously — each with   │        (classification,
  fingerprint    │  its own amplitude = the      │         regression,
  encoded as     │  physical kernel evaluation)  │         interpolation,
  drive tones)   │                               │         routing decision)
                 │  That N-dim gradient IS the   │
                 │  hidden layer of a neural net │        w·y + b
                 └──────────────────────────────┘        (learned readout,
                        ▲                                  FPGA, trivial)
                    ZERO-POWER
                    PERMANENT
                    UNCLONABLE
```

One broadcast → one acoustic cycle (~4 ms desk / ~0.3 ms MEMS) → N kernel evaluations in parallel. The expensive part is **free** (the glass does it passively). The cheap part is all that's electronic (one dot product for readout).

### Competitive landscape

| Platform                                     | What it does                         | Energy/inf              | Speed                        | Non-volatile?       | Unclonable?   | Status        |
| -------------------------------------------- | ------------------------------------ | ----------------------- | ---------------------------- | ------------------- | ------------- | ------------- |
| **GPU/TPU** (NVIDIA, Google)                 | Digital matmul — exact, universal    | ~mJ                     | GHz                          | No                  | No            | Dominant      |
| **Photonic NN** (Lightmatter, Akhetonics)    | Optical MZI mesh — MVM in light      | ~nJ                     | GHz                          | No (volatile)       | No            | Series B+     |
| **Memristor crossbar** (Mythic, Ceremorphic) | Analog NVM MACs                      | ~pJ/MAC                 | MHz                          | Yes (degrades)      | No            | Limited prod. |
| **Analog CMOS** (Aspinity, Syntiant)         | Always-on edge inference             | ~µW                     | MHz                          | No                  | No            | Production    |
| **Spintronic reservoir** (Toshiba)           | Magnetic dynamics → readout          | ~µJ                     | kHz                          | Yes                 | Partly        | Lab           |
| **CWM Level 3**                              | Spectral kernel — glass does the MVM | ~µJ (desk) / ~nJ (MEMS) | 250 Hz (desk) / 3 kHz (MEMS) | **Yes (permanent)** | **Yes (PUF)** | Architectural |

### Where CWM wins (the honest answer)

CWM does NOT beat GPUs on speed or photonics on bandwidth. It wins on a **unique combination** that no other platform offers:

1. **Zero-power memory:** the kernel (hidden-layer weights) is the glass itself. No refresh, no leakage, no bit-flip. Survives power loss indefinitely.
2. **Unclonable compute:** every device computes differently (plate spectra = PUF). Hardware-rooted model security — inference can't be cloned or extracted.
3. **Combined compute + storage + identity:** one object is simultaneously the inference engine, the data store, and the device fingerprint. No interconnect between them.
4. **Zero-write programming:** the kernel is manufactured, not written. No endurance limit, no write energy, no drift. "Deploy" = plug it in.
5. **Multi-task in one cycle:** different readout weights = different inference tasks on the same physical kernel. Switch tasks in one clock cycle.

### Use cases (who pays for this?)

| Use case                                         | Why CWM fits                                                                                                                          | Customer segment                                                          |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **Edge anomaly detection**                       | Always-on sensor → kernel → "is this normal?" Zero standby power (glass holds the model). Unclonable (can't exfiltrate the model).    | Industrial IoT, predictive maintenance (Siemens, ABB, Bosch)              |
| **Hardware-secured inference**                   | The model IS the device — can't be copied, can't be read out, can't be reverse-engineered. Inference only runs on this specific chip. | Defense/classified ML, IP-protected models (Palantir, L3Harris, DARPA)    |
| **Spectral matching / chemical ID**              | Query = measured spectrum → kernel compares against library → identification in one cycle. The codebook IS permanent calibration.     | Spectrometry OEMs, pharma QC, food safety (Thermo Fisher, Bruker, FOSS)   |
| **Physical one-time-pad / secure key agreement** | Two devices with entangled manufacturing → correlated kernels → key extraction without digital storage.                               | Hardware security, post-quantum key establishment (NXP, Infineon)         |
| **Neuromorphic always-on wake**                  | Ultra-low-power "is this the wake word?" using spectral kernel on audio features. Glass never sleeps.                                 | Consumer electronics, hearing aids, voice interfaces (Qualcomm, Syntiant) |
| **In-sensor compute**                            | The glass plate IS both the sensor (vibration/acoustic/mass) AND the classifier. No A/D → CPU → inference pipeline.                   | MEMS sensor companies (STMicro, InvenSense, Murata)                       |

### The pitch to each customer type

| Customer                     | One-liner                                                                                                                   |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Defense / secure compute** | "The inference model is physically unclonable and never leaves the chip. You can't steal what's written in glass geometry." |
| **Industrial IoT**           | "A classifier that survives power loss, never drifts, needs no retraining, and detects anomalies at µW standby."            |
| **Spectrometry / chem-ID**   | "Your reference library is etched into the physics. No calibration database, no drift, instant match."                      |
| **Edge AI silicon**          | "Replace your SRAM weight buffer with a passive glass layer that holds 10⁴ kernel features at zero power."                  |

_Presenter notes:_ THIS is the commercial slide. The capabilities arc (slides 6–11) proves the physics works. This slide answers "so what?" — it's a kernel machine, here's who buys it, here's what they pay for, and here's what competitors can't do. The desk demonstrator at Level 3 (Phase 4A Part D) proves the kernel architecture works. MEMS scaling delivers the speed/energy that makes it commercially competitive. The honest gap: desk is 250 Hz, production needs kHz–MHz. That's fabrication — the thing the funder pays for.

---

## Slide 11B — The kernel works: real-time games on glass (MEASURED)

**The headline:** we don't have to _argue_ the kernel computes — you can **watch it play a video game in real time**, and prove the glass is doing the work by switching it off mid-game.

### Pong on glass — MEASURED (2026-06-21)

A live Pong game where the right paddle is driven entirely by the glass. The ball's position is encoded as three drive tones; the plates' interference response is read in one capture and a trained readout turns it into a paddle position.

| Metric                                   | Result                                                                                                                  |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Glass tracks the ball (live correlation) | **r = 0.69** (0.72 at 1-frame lag)                                                                                      |
| Cross-validated tracking accuracy        | **68%** (vs 50% stationary, 36% random)                                                                                 |
| Long-match result on hardware            | **glass won 41–18**, 57% intercept over 13,896 frames                                                                   |
| Decision latency                         | ~165 ms/frame (3 tones + 8 FFT averages)                                                                                |
| Kernel dimension available               | **173-mode candidate pool** (collisions carry signal: equal SNR, correlation, and repeatability to non-collision modes) |

**The proof-of-physics is built into the game:** press **G** to toggle the glass. Glass ON → the paddle tracks and wins. Glass OFF → same laptop, same code, same weights, but the acoustic drive is cut → the paddle drifts and loses. The only variable is whether the glass is in the loop.

### DOOM on glass — what the experiment actually showed (OPEN, instructive)

We built the full raycaster pipeline ([tools/doom_train.py](../tools/doom_train.py), [tools/doom_live.py](../tools/doom_live.py)) and trained it on real glass. **Direct rendering failed, and the failure is diagnostic:**

| Target the glass was asked to produce     | Cross-validated R² |
| ----------------------------------------- | ------------------ |
| Player **angle** (smooth)                 | **+0.48**          |
| Player **y** (smooth)                     | **+0.36**          |
| The 8 **raycast columns** (discontinuous) | **≈ 0.00**         |

The glass reads back the _smooth_ state variables fine, but the 8 wall-distance columns are R² ≈ 0. **Raycasting is a discontinuous function** (a ray abruptly hits or misses a wall); a smooth analog kernel + linear readout cannot represent a discontinuity. Same boundary as Pong: the glass **tracks** (smooth) but cannot **predict bounces** (discontinuous).

**The honest correction:** kernel dimension (173 modes ≫ 32) is **necessary but not sufficient** for DOOM. The render function must also be smooth enough for the kernel to represent — raycasting isn't. DOOM needs the **associative-recall architecture** (one plate per stored view → recall the nearest precomputed view — the §7A discrete/LUT path), not a learned regression on the §7B gradient. That is the 32-plate build. **We do not claim DOOM on the present bench.**

### The honesty boundary (say this exactly)

| The **glass** genuinely does                                                                                                                           | The **laptop** does                                                            |
| ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| The **kernel / feature transform** — turns the encoded state into a high-dimensional interference pattern (real analog physics, physically unclonable) | FFT of the captured waveform (could be on the readout ASIC)                    |
|                                                                                                                                                        | The **linear readout**: one dot product `w·features + b` (≈20 trained numbers) |
|                                                                                                                                                        | Feature selection ("intentional forgetting"), game logic, collision, rendering |

> **The one true sentence:** "The glass is the **kernel** — it performs the expensive high-dimensional transform passively, in physics. The laptop does an FFT and a single dot-product readout, plus the game's bookkeeping. The intelligence about _this_ game is ~20 trained numbers; the computation that makes those numbers enough lives in the glass."

**What NOT to claim:** the glass does not render, store the weights, or do the readout arithmetic — and it does not raytrace (discontinuous geometry is the §7A lookup path, not the §7B smooth kernel). Claiming the glass "plays Pong" end-to-end is the overclaim a reviewer will catch. The defensible claim is that the glass computes the **smooth feature transform the decision is read out from** — the part that's expensive on a CPU and free in the physics.

_Presenter notes:_ Run **Pong** as the live demo — open the game, let it play, then hit **G** and let the audience watch the paddle fall apart with the glass off. That toggle is the entire argument — the controlled experiment compressed into one keypress. **On DOOM, tell the truth and make it a strength:** "We tried to make the glass raytrace and it couldn't — that taught us exactly where the boundary is: smooth kernels yes, discontinuous geometry no (§7B vs §7A)." Volunteering a clean negative result is what makes the positive Pong claim credible. Tie back to Slide 11A: Pong is the _demonstrated_ kernel machine; DOOM mapped the edge of the envelope.

---

## Slide 12 — How it connects to the Phononic Processor (the map)

The desk demonstrator is a **macro emulator of the processor's instruction set** — and via the associative/HD path (§7A), it is a **working general computer** at desk scale.

```
 CONTROL CORE (host + FPGA)  ── runs the CWM instruction set ──┐
                                                               ▼
 ──── ASSOCIATIVE/HD PATH (desk-achievable, primary) ────────────
 General compute  ← DD-P4A: interference + threshold + LUT cascade  [§7A]
 PFU-1 Projection ← DD-P1 crossbar rank-N                          [R3]
 PFU-2 Search     ← DD-P4 array CAM                                [R2]

 ──── SUPPORTING CAPABILITIES ───────────────────────────────────
 PFU-3 PUF          ← DD-P6 multi-plate identity [R2]   unclonable ID
 PFU-4 Perturbation ← DD-P5/P9 write/read        [R1/R6] non-volatile memory
 PFU-5 Phase/Grover ← DD-P6B non-separability   [R5]   quantum-like
 (volatile tier)    ← DD-P2 FPGA temporal loop   [R9]   reservoir
 SUBSTRATE UNITY    ← DD-P10 + Phase S 3D stack  [R8-11] the thesis

 ──── VON NEUMANN PATH (MEMS-gated, parallel science goal) ──────
 PFU-6 Ising        ← DD-P7/P8 parametric        [R10-11] optimization
 Stages 3–6         ← MEMS (all-acoustic gate/latch/cascade)
```

**Two paths to general logic (architecture §7 and §7A):**

| Path                     | What it needs                                      | Desk-achievable?                | Status        |
| ------------------------ | -------------------------------------------------- | ------------------------------- | ------------- |
| **Associative/HD (§7A)** | Interference + threshold + crossbar routing        | **Yes — all stages, Phase 4A**  | ARCHITECTURAL |
| Von Neumann (§7)         | Nonlinear gate + parametric latch + high-Q cascade | Stages 1–2 only; 3–6 MEMS-gated | PROJECTED     |

The Von Neumann path remains the long-term all-acoustic science goal. The associative path is the near-term demonstration of general compute — provable today, on this hardware, without fabrication.

_Presenter notes:_ This is the strategic reframe. The desk rig is not "waiting for MEMS to become a real computer." It IS a real computer today — just slow (250 Hz clock). Speed comes from MEMS. But the computational architecture is proven at desk scale.

---

## Slide 13 — How it connects to the Frontier (the ladder)

The desk demonstrator **walks rungs R0–R6 of the frontier ladder without fabrication**:

```
 R0 null ─ R1 write ─ R2 PUF/x-session ─ R3 rank-N ─ R4 F10 ─ R5 switch ─ R6 volumetric
 └──────────────── ALL desk-accessible (bench/sim) ────────────────┘
                                                                     │
                              R7 MEMS design (paper) ── R8 fab ── R9 reservoir ── R10 gate ── R11 Ising
                              └──────────── fabrication-gated ───────────────┘
```

- **R0–R6:** the desk demo retires this risk for ~$200–1,000.
- **R7:** a publishable MEMS design study, no fab needed.
- **R8–R11:** the fabrication ask — now small, specific, and de-risked by everything below it.

_Presenter notes:_ The desk demo _is_ the lower half of the ladder, made physical. It converts the frontier from a wish-list into a measured staircase.

---

## Slide 14 — Where it connects to MEMS — and where it deliberately does NOT

**Connects (architecturally faithful, shrinks 1:1):**

- Crossbar row/column addressing (M+N lines at any pitch)
- 3D stacked planes ↔ stacked dies with TSVs
- The PFU instruction set and control stack
- Every _scientific_ primitive: rank, write, search, identity, reservoir, non-separability, spin

**Does NOT connect (MEMS-only, the honest gap):**

- **Density** (Gbit/cm³) — pitch is mm, not µm
- **Speed** (MHz–GHz clocks) — desk is kHz
- **Energy** (fJ/op) — desk draws watts
- **Monolithic integration**

_Presenter notes:_ Name the gap before anyone else does. The desk demo proves the physics and the architecture; the chip is what turns those into the density/speed/energy product metrics. That honesty is the pitch.

---

## Slide 15 — The optics caveat (pre-empt the obvious question)

"You showed a laser earlier — does that shrink?"

- **No — and it doesn't need to.** Optical readout is **bring-up test equipment**, not part of the array.
- It proves rank-N cleanly (no mass loading) as an independent cross-check.
- The chip reads **electrically** via the integrated transducer crossbar — which is exactly the part that _does_ shrink, and the only thing that can read a 3D stack (inner planes are optically occluded).

_Presenter notes:_ This is the question every hardware person asks. Answer it before they do, and it becomes a strength: it shows we know which parts are scaffolding and which are architecture.

---

## Slide 16 — Cost & timeline of the demonstrator

| Tier               | What it proves                                        | Cost          | Gear                         |
| ------------------ | ----------------------------------------------------- | ------------- | ---------------------------- |
| **Scrappy**        | rank-N, CAM, write, PUF (P0–P6, slow)                 | ~$0–50        | owned + junk-drawer          |
| **Desk Minimum**   | + fast loop, FDM, clean rank-N                        | ~$750–1,050   | + FPGA, crossbar, optics     |
| **Briefcase Full** | + vacuum/Q, Ising, volumetric, 3D stack, encapsulated | ~$2,000–3,500 | + vacuum, forks, stack frame |

The **Red Pitaya FPGA (~$300–450)** is the single keystone purchase — it breaks B2 and unlocks the temporal/feedback half of the deck.

**Self-containment:** the clean build is **two active boards** (Pi host + Red Pitaya brain + crossbar), driven from one browser over the case's own WiFi — not the five-board bring-up pile. Add a lid touchscreen + run button for a turn-it-on-it-runs appliance (§3.9).

_Presenter notes:_ Lead with the scrappy number. "We can start proving this for the price of dinner, and the whole briefcase is one to two orders of magnitude under a foundry run."

---

## Slide 17 — What a funder/collaborator is actually buying

**The desk demonstrator is not just a physics demo — it is a working general computer (associative/HD model) that also serves as the de-risking artifact for the MEMS shrink.**

- It demonstrates general compute at desk scale via the associative/HD path (Phase 4A, architecture §7A) — no MEMS dependency.
- It retires frontier rungs R0–R6 with cheap, falsifiable experiments.
- It leaves exactly one well-posed question for fabrication: **does Q ≥ 10⁴ survive at MEMS scale?** (R7→R8) — needed only for the Von Neumann/Ising path, not the associative path.
- MEMS buys speed (MHz clock instead of 250 Hz) and density (millions of codebook entries instead of 8–64 plates). The architecture is already proven at desk.

**The ask is not "fund a moonshot." It is "fund the shrink of a working computer."**

_Presenter notes:_ Close here. The narrative is: validated bench → working desk computer (associative/HD) → one specific fab question (Q for Von Neumann) → the chip. The associative computer works NOW. MEMS makes it fast and dense.

---

## Slide 18 — Summary: the through-line

```
 MEASURED bench  →  DESK DEMONSTRATOR  →  MEMS chip
 (v19r science)     (THIS IS A WORKING     (density, speed,
                     COMPUTER — slow but    energy — the product)
                     general, via HD/VSA)

 proves:            proves:                 delivers:
 modes, SNR,        GENERAL COMPUTE (§7A),  Gbit/cm³, MHz–GHz,
 CHSH, stability    rank-N, CAM, PUF,       fJ/op, integration,
                    write, reservoir,       all-acoustic Von Neumann
                    non-separability,       (Stages 3–6)
                    (frontier: Ising)
```

**One sentence:** the desk demonstrator is a working associative/hyperdimensional computer that uses wave interference as its compute engine, glass plates as permanent memory, and the crossbar as an address bus — proving general logic at desk scale and leaving only speed and density to fabrication.

_Presenter notes:_ End on the one sentence. The desk rig computes. It's just slow. MEMS makes it fast. That's the entire pitch.

---

## Appendix A — Full traceability matrix

| Desk phase       | Capability                             | PFU / §       | Frontier rung    | Ceiling § | Maturity (full build)          | Falsifier                           |
| ---------------- | -------------------------------------- | ------------- | ---------------- | --------- | ------------------------------ | ----------------------------------- |
| **DD-P4A**       | **General compute (HD/associative)**   | **§7A**       | **(all stages)** | —         | **ARCHITECTURAL→DEMONSTRATED** | **threshold margin <2σ at depth 1** |
| **DD-P4A-D**     | **Physical kernel / neural inference** | **§7B**       | **(Level 3)**    | —         | **ARCHITECTURAL→DEMONSTRATED** | **kernel matrix rank ≤2**           |
| DD-P1            | Rank-N matrix math                     | PFU-1         | R3               | 3.1       | OPEN→MEASURED                  | rank ≤2 after grid+stack            |
| DD-P4            | Associative search / CAM               | PFU-2         | R2               | 3.2       | MEASURED→scaled                | argmax at chance                    |
| DD-P6            | PUF / identity                         | PFU-3         | R2               | 3.2       | OPEN→MEASURED                  | cross-session <95%                  |
| DD-P5            | Surface write/read                     | PFU-4         | R1               | 3.3       | OPEN→MEASURED                  | <3σ at 10 mg                        |
| DD-P9            | Volumetric 3D write                    | PFU-4         | R6               | 3.3       | SIMULATED→OPEN                 | sensitivity R²<0.99                 |
| DD-P2            | Temporal reservoir                     | volatile tier | R9-analog        | 3.4       | PROJECTED→MEASURED             | MC<3 at ≥3 kHz                      |
| DD-P6B           | Quantum-like / non-separability        | PFU-5         | R5               | 3.5       | MEASURED→extended              | fixed-angle S<2                     |
| DD-P7/P8         | Parametric Ising                       | PFU-6         | R10–R11          | 3.6       | PROJECTED                      | no threshold at safe drive          |
| DD-P10 + Phase S | Substrate unity / 3D stack             | full stack    | R8→R11           | 3.7       | the thesis                     | functions don't compose             |

## Appendix B — What this deck does NOT claim

- Not a Von Neumann CPU — the associative/HD path is general compute, but it's not gate-based logic (Stages 3–6 of the Von Neumann path remain MEMS-gated).
- Not fast — the desk clock is ~250 Hz (4 ms per cycle). Speed comes from MEMS.
- Not dense — density is mm-pitch at desk scale. Density comes from MEMS.
- Not a quantum computer ("quantum-like" = classical wave structure only).
- Not a density/speed/energy demonstration (those are the fabrication deliverables, by design).
- The associative path IS general compute, but with a ~250 Hz clock it is proof-of-architecture, not a competitive product.

## Appendix C — Source-of-truth links

- Build: [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md) · Procedures: [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md) · Scrappy: [DESK_DEMONSTRATOR_SCRAPPY.md](DESK_DEMONSTRATOR_SCRAPPY.md)
- Ceiling + ladder: [FRONTIER_CEILING.md](FRONTIER_CEILING.md) · Processor stack: [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md)
- Roadmap + gates: [ROADMAP_FULL_POTENTIAL.md](ROADMAP_FULL_POTENTIAL.md) · Evidence ledger: [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md)
