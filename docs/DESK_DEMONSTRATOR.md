# CWM Desk / Briefcase Demonstrator — Phononic Array Build Spec

**Date:** 2026-06-20
**Status:** Build specification. Hardware tiers labeled by what they demonstrate. Capability claims inherit the maturity labels (MEASURED / SIMULATED / PROJECTED / OPEN) from [FRONTIER_CEILING.md](FRONTIER_CEILING.md) and [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md).

**Companion documents:** [FRONTIER_CEILING.md](FRONTIER_CEILING.md) (the ceiling + R0–R11 ladder), [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md) (experiment specs + base BOM #1–#15), [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) (the PFU stack this hardware runs).

**Step-by-step bench protocol for every phase below:** [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md) — concrete, repeatable, shareable procedures in worklist style (objective, procedure, agent prompt, success/kill, data path, safety).

**Reuse-first / buy-nothing iteration path:** [DESK_DEMONSTRATOR_SCRAPPY.md](DESK_DEMONSTRATOR_SCRAPPY.md) — how to prove and iterate every phase on owned + junk-drawer gear (PicoScope, Pico NCO, relay mux, cassette, salvaged optics) before committing to the BOM.

**Slide deck — projected capabilities + processor/frontier connection:** [DESK_DEMONSTRATOR_PRESENTATION.md](DESK_DEMONSTRATOR_PRESENTATION.md) — presenter-ready deck mapping each desk capability to its PFU and frontier rung, with the honest MEMS gap.

**⚠️ Wave-Native Design Principle.** The glass is a smooth, low-dimensional analog **kernel + content-addressable memory**, not a von Neumann machine — design demos for the wave-native form, not the first silicon algorithm. Proven dualities (MEASURED 2026-06): track/integrate not predict/branch; nearest-**centroid** not ridge **regression** (T3.4 4096 states 100% vs ridge 0.55%); encode by **amplitude of a fixed mode** not **frequency position** (8 levels/mode @ 100σ vs ~2 levels/axis); **factor** the state; keep collision modes (select by repeatability×separability); make the **Gram matrix** diagonal-dominant. Full table in [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md).

---

## 1. The Core Idea

The desk demonstrator is not a scale model of a chip waiting for fabrication to become useful. It is a **working associative / hyperdimensional computer** that reaches general compute today — using glass plates as a permanent physical codebook, the crossbar as an address bus, and interference + threshold as the computational primitive.

### Why the desk rig isn't "the chip minus density"

A MEMS chip's engineering advantages (density, speed, energy) are real and worth pursuing. But the desk array has a **computational** advantage that doesn't require fabrication: **the plate array IS a program.** Each plate's eigenmode spectrum is unique, permanent, and read-only — determined by its geometry at manufacture. The array is a physical lookup table with permanent entries, addressed by the crossbar, computed over by wave interference. This is general compute via the associative/HD path (see [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) §7A).

### Two computational models on one hardware

| Model                               | What the glass does                                                                        | What electronics does                                                  | Q requirement | Desk-achievable?                                |
| ----------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- | ------------- | ----------------------------------------------- |
| **Associative / HD (primary path)** | Interference = vector operation; spectrum = permanent memory; resonance = binary threshold | Address routing (crossbar); 1-bit decision (threshold comparator)      | Any Q         | **Yes — all stages**                            |
| **Gradient / Kernel (Level 3)**     | Full N-dim response = physical kernel evaluation; array = neural hidden layer              | Learned readout weights (one dot product); optional iteration feedback | Any Q         | **Yes — classification, regression, inference** |
| Von Neumann (MEMS frontier)         | Nonlinear gate; parametric latch; self-sustaining cascade                                  | Sequencing only                                                        | ≥ 10⁴         | Stages 1–2 only                                 |

The desk rig walks the associative path first (Phases 0–4A, Parts A–C for discrete logic, Part D for gradient/kernel inference). The Von Neumann path (Phases 7–8) is the MEMS science goal, pursued in parallel where vacuum + Q-control enables it.

### The two bottlenecks (still real, still broken at desk)

A MEMS chip's only real advantages over the current bench are that it **breaks the two bottlenecks**:

- **B1 — readout rank.** Two PZT receivers give a rank-2 transfer matrix. The MEMS die breaks this with a per-die transducer array.
- **B2 — the Q·f time constant.** τ = Q/(πf) is too short relative to the bench's ~8 Hz capture loop. The MEMS die breaks this with high Q and high f.

**Both bottlenecks can be broken at desk scale without fabrication** — by rebuilding the _instrument_ around the glass instead of shrinking the glass:

- B1 is broken by **optical readout + a plate array** (many points, many plates → high-rank H natively).
- B2 is broken by a **fast continuous FPGA I/O loop** (kHz streaming lock-in, not block-mode capture) and, where high Q is needed, a **bell-jar vacuum + electronic Q-control**.

What the desk array **cannot** show is the engineering payoff — Gbit/cm³ density, MHz–GHz clocks, fJ/op energy, monolithic integration. Those are exactly what fabrication is for. This split is the strategic point: **the desk array demonstrates every physical _principle_ and computational _primitive_ of the MEMS device, which is precisely the de-risking artifact that makes a MEMS fabrication grant fundable.**

### Why an array, not one plate

The MEMS "chip" was always an array — the density projections come from packing millions of resonators (see [FRONTIER_CEILING.md](FRONTIER_CEILING.md) §"Density Ceiling" discussion). So a **tiled, row/column-addressed transducer array is the faithful scale model of the real device** (§3.2), where a single plate only ever proves the unit cell.

**What shrinks vs. what's scaffolding.** The faithful, shrinkable part is the **addressing topology** — a transducer crossbar that scales unchanged from cm to µm (an M×N array needs only M+N address lines at any pitch). The optical readout we use during bring-up is **not** part of the array: the chip reads electrically via integrated transduction, so the laser/galvo has no MEMS counterpart and is deleted at scale. Build the crossbar (§3.2) as the architecture; use the optics (§3.4) only to cross-check the physics.

| Level         | Physical object         | Role                                                                                                                                                 |
| ------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Unit cell** | one slide / 25 mm plate | one Phononic Functional Unit (PFU): sensor + memory + fingerprint + feature-map + compute                                                            |
| **The array** | a rack of plates        | the **processor** — many PFUs in parallel = the machine; also the **program** (each plate's spectrum is one codebook entry in the associative model) |

You already built the seed of this: the **5-plate fused-silica cassette** (lab diary 2026-04-12, plates A–E on shelves, TX/RX PZTs, relay-muxed). This spec is that idea done properly and encapsulated in a case.

Several headline claims are **more convincing on an array** because the array is their native substrate:

| Property                             | On one plate                                  | On the array (better)                                                                                                                                                                            |
| ------------------------------------ | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **General compute (HD/associative)** | limited to single-plate interference          | **the full codebook: interference + threshold + address selection = complete compute cycle across the array. The array IS the computer.**                                                        |
| Associative search / CAM             | templates in one plate's modes                | one template per plate; broadcast query on shared drive; matching plate rings loudest → **parallel nearest-neighbor search in one acoustic cycle. The array IS the content-addressable memory.** |
| Multi-device PUF                     | one fingerprint                               | the rack literally is WL-B3: inter-plate vs intra-plate Hamming distance is measured across the cartridge                                                                                        |
| Temporal reservoir                   | one reservoir                                 | coupled plates = wider/deeper reservoir, diverse timescales                                                                                                                                      |
| Parametric Ising                     | N modes-as-spins on one plate, hard to couple | each plate/fork = one spin; programmable inter-plate coupling = the J matrix (this is how NTT/Toshiba CIMs actually work)                                                                        |
| Rank-N interference (B1)             | limited by points on one plate                | each plate adds independent modes → block-structured high-rank H natively                                                                                                                        |

**In the associative model, the array advantage is fundamental:** each plate is one entry in the codebook. More plates = larger program / deeper state space. With N plates, $2^N$ addressable configurations exist. 16 plates → 65,536 states. The array isn't just "more capacity" — it's an exponentially richer computational substrate.

---

## 2. System Architecture

```
  BRIEFCASE / PELICAN CASE (fully self-contained)
  ┌──────────────────────────────────────────────────────────────┐
  │  ┌──────────────── PLATE RACK (card cage) ─────────────────┐  │
  │  │  ║P1║ ║P2║ ║P3║ ║P4║ ║P5║ ║P6║ ║P7║ ║P8║   (swappable)  │  │  ← slides / 25mm plates
  │  │   on nodal foam tips · optional coupling jumpers between  │  │     on nodal mounts
  │  │   adjacent slots · shared TX drive rail along the back    │  │
  │  └────────────────────────────────────────────────────────┘  │
  │                          ▲ drive            ▼ vibration         │
  │  ┌──────────── OPTICAL READOUT HEAD ─────────────────────┐    │
  │  │  650nm laser → galvo mirror → sweeps across rack       │    │  ← N virtual channels
  │  │  reflected beam → knife edge → photodiode (or PD array)│    │     (time- or space-mux)
  │  └────────────────────────────────────────────────────────┘    │
  │                          │ analog                                │
  │  ┌──────────── THE BRAIN: FPGA lock-in board ───────────┐      │
  │  │  multi-tone drive · parallel lock-in demod ·          │      │  ← Red Pitaya / Moku
  │  │  real-time feedback (Q-control, parametric pump) ·     │      │     breaks B2
  │  │  kHz streaming acquisition                            │      │
  │  └────────────────────────────────────────────────────────┘    │
  │  [Pico NCO]   [relay mux]   [preamp/TIA bank]   [host SBC/USB]  │  ← owned + addressing
  │  ┌──── optional: small acrylic bell jar over rack ───────┐     │
  │  │  + diaphragm pump  → recovers intrinsic Q → Ising path │     │  ← high-Q upgrade
  │  └────────────────────────────────────────────────────────┘    │
  │  [linear PSU / battery]   [fused IEC inlet]   [cooling vents]   │  ← power
  └──────────────────────────────────────────────────────────────┘
```

Four functional blocks: **substrate** (the plate rack), **drive** (Pico NCO + FPGA generators), **readout** (optical head + preamps), **brain** (FPGA lock-in + host). Vacuum and coupling backplane are upgrades, not required for the minimum build.

> The single-layer rack drawn above is the starting point. To resemble the **packed MEMS die**, the substrate becomes a **3D stack of crossbar planes** on nodal standoffs with a vertical "TSV" ribbon bus and `(layer, row, col)` addressing — see §3.2. Only the electrical crossbar can read a stack (inner planes are optically occluded), which is exactly why the chip reads electrically.

### Subsystem Roles & Why Each Exists

The readout/addressing layer has one **MEMS-faithful primary** — the transducer crossbar (§3.2), which shrinks unchanged to the chip — and one **bring-up cross-check**, the optical chain, which has no MEMS counterpart and is deleted at scale. Several phases use both.

| Subsystem                              | What it does                                                                                              | Why it exists / why nothing else covers it                                                                                                                                                                                                          |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Plate rack (substrate)**             | Hosts the transducer crossbar; each plate/cell = one PFU                                                  | The array IS the processor; nodal mounting preserves intrinsic Q that contact PZTs would mask                                                                                                                                                       |
| **Red Pitaya (the brain)**             | Generates drive, demodulates readout (lock-in), closes real-time feedback loops, streams envelopes at kHz | **Breaks B2.** Replaces signal-gen + lock-in + PID + digitizer in one FPGA. Lock-in is a matched filter, so it preserves weak modes the killed raw-FFT capture lost. The kHz loop makes the volatile modal state (temporal memory) finally readable |
| **Optical chain** (laser + galvo + PD) | Non-contact readout at many steered spatial points                                                        | **Bring-up cross-check — does not shrink.** Proves rank-N without bonding a grid and unmasks intrinsic Q; but the chip reads electrically, so the laser/galvo is deleted at MEMS scale. Validate with it, then hand off to the crossbar             |
| **Relay mux** (contact PZT path)       | Electrical addressing: selects which plate/PZT connects to the input; routes drive                        | **Scrappy stand-in for the crosspoint switch.** Does the crossbar's (row, col) selection slowly with owned gear until the MT8816/ADG2128 is wired; per-plate drive isolation for null tests; the safety net if optical SNR < 20 dB                  |
| **Pico NCO**                           | High-frequency carrier source (30–350 kHz)                                                                | Drives modes above the Red Pitaya's most convenient baseband range; owned, already validated                                                                                                                                                        |
| **Vacuum + Q-control** (upgrade)       | Removes gas damping; velocity feedback synthesizes high effective Q                                       | Reaches the Q ≥ 5×10³ regime the parametric/Ising demos need without fabrication                                                                                                                                                                    |
| **Coupling backplane** (upgrade)       | Programmable inter-plate J (electronic, via the FPGA)                                                     | Turns an uncoupled memory bank into a coupled reservoir / Ising network; software-programmable J beats fixed acoustic bridges                                                                                                                       |

**One-line mental model:** the **crossbar** is the MEMS-faithful body (row/col addressing that shrinks, §3.2); the **Red Pitaya** is the brain (drive + demod + feedback, breaks B2, §3.3); the **optical chain** is throwaway bring-up scaffolding (proves rank-N, then deleted at scale, §3.4); the **relay mux** is the scrappy stand-in for the crosspoint switch.

> The crossbar (§3.2) is the primary, MEMS-faithful readout-and-addressing layer. The optical chain is bring-up test equipment, not part of the array.

---

## 3. Subsystems

### 3.1 Substrate — the tiled plate array

The substrate is the macro stand-in for the resonant die: glass plate(s) that **host the transducer crossbar (§3.2)**. It is the _resonator_, not the readout.

- **Plates:** microscope slides (≈ 75 × 25 × 1 mm) or your 25 × 25 × 1 mm fused-silica plates — thin, mode-rich, ~$0.07 each. A single larger panel tiled with a transducer grid is the closest analog to a tiled die; a rack of separate plates is the modular, swappable version.
- **Mount:** three-point nodal foam tips (recovers the intrinsic Q that corner-glued PZT loading masks — June data: loaded Q 150–743 vs ringdown hints of 7k–60k). Plates sit on edge at ~10 mm pitch, or flat on a backplane for the tiled-panel build.
- **Two cartridge types** (the multiplexing design, §5, depends on which):
  - **Diversified cartridge** — plates deliberately detuned (different thicknesses or small tuning masses) so each occupies its own frequency band. Enables single-capture frequency-division readout. Use for compute/memory/reservoir/Ising demos.
  - **Identical cartridge** — nominally identical plates; rely on manufacturing variance + crossbar/relay addressing to tell them apart. Use for the **PUF** demo (WL-B3), where identical-by-design is the point.

### 3.2 Crossbar transducer array — the MEMS-faithful core (breaks B1, and it shrinks)

This is the **primary architecture** and the part that actually models the MEMS device. The MEMS "integrated AlN array, row/column addressed" is, stripped to essentials, a **passive-matrix transducer crossbar**: a grid of low-mass piezo cells on a resonant substrate, top electrodes bussed into **rows**, bottom electrodes into **columns**, so any cell (i, j) is addressed by selecting row i + column j. Same topology as a ReRAM array, an ultrasound phased array, or a touchscreen — and it is **scale-invariant**: an M×N array needs only **M + N** address lines whether the pitch is 1 µm or 1 cm. Reproduce the crossbar and you reproduce the device; the optical scaffold (§3.4) is deleted at MEMS scale because integrated transduction already gives low-mass multipoint readout.

**The mass problem this solves.** Contact PZT discs load the plate — that _is_ the rank-2 / Q-masking bottleneck (B1). At MEMS scale thin-film AlN is negligible mass, so the problem vanishes. The desk-faithful low-mass analog is **PVDF piezo film** (BOM DD20): a 28–110 µm metallized polymer sheet, cuttable and screen-printable into electrode grids — the cheap macro analog of thin-film AlN. Where strong per-cell _drive_ is needed, light PZT cells substitute (PVDF is a great low-mass sensor, a weak actuator).

**The crossbar switch.** A crosspoint-switch IC (MT8816 8×16, or ADG2128; BOM DD21) _is literally a row/column-addressed analog crossbar in a chip_ — the desk model of the on-die address electrodes. Set an (i, j) address on a few digital lines and it connects that cell to your TX/RX. It replaces the relay mux with something that (a) scales, (b) switches in microseconds, and (c) is itself the scale model of the address decode.

```
DESK MACRO CROSSBAR  (one resonant panel, transducer grid, row/col addressed)

        col0  col1  col2  col3      ← bottom electrodes / column bus
          │     │     │     │
  row0 ──▓▓────▓▓────▓▓────▓▓──     each ▓▓ = PVDF (or light PZT) cell on a shared plate
          │     │     │     │
  row1 ──▓▓────▓▓────▓▓────▓▓──     address cell (i,j):  drive row i · sense col j
          │     │     │     │
  row2 ──▓▓────▓▓────▓▓────▓▓──     ↑ top electrodes bussed into rows
          │     │     │     │
  row3 ──▓▓────▓▓────▓▓────▓▓──
          │     │     │     │
       ┌──┴─────┴─────┴─────┴──┐
       │  CROSSPOINT SWITCH IC  │   ← MT8816 / ADG2128 = programmable row×col matrix
       └───────────┬────────────┘
            address │ (a few digital lines from Arduino/FPGA)
       drive: PicoScope AWG / Pico NCO → row bus    sense: preamp → PicoScope/Red Pitaya ← col bus
```

**Cell-for-cell mapping (why it is faithful, not a metaphor):**

| MEMS device                       | Desk macro model                         | Scales?           |
| --------------------------------- | ---------------------------------------- | ----------------- |
| Resonant membrane / tiled die     | one glass panel (or tiled slides)        | —                 |
| AlN thin-film cell                | PVDF film patch (or light PZT)           | mass ✓            |
| Row/column electrodes             | printed row/col buses on the film        | ✓                 |
| On-die address decode             | MT8816 / ADG2128 crosspoint switch       | ✓                 |
| Drive electronics                 | PicoScope AWG / Pico NCO on row bus      | ✓                 |
| Sense electronics                 | preamp + PicoScope/Red Pitaya on col bus | ✓                 |
| Through-silicon vias (3D)         | ribbon/pin column bus between panels     | ✓                 |
| M×N array → **M+N** address lines | identical wiring count                   | ✓ scale-invariant |

**Drive/sense split** (mirror the MEMS options):

- _Shared drive + array sense_ — one element (or a shaker) drives the whole panel; the grid _senses_ the mode field at N points → rank-N readout, low mass, **electrically**. This is what the laser fan did, in a form that shrinks. Best for rank-N feature maps and reservoirs.
- _Per-cell drive + sense_ — each cell both drives and senses (true PMUT), addressed via the crosspoint switch. Needed for the independent-resonator CAM/PUF array.

**3D stacking — the packed-array model (do this to resemble the MEMS die).** A single crossbar plane is one die. Stack several planes and you have the desk-scale analog of a packed/stacked-die array — and this is where the crossbar earns its place decisively, because **only electrical readout survives a stack**: inner planes are optically occluded, so the laser cannot see them, but the crosspoint switch reaches every cell at any depth. The 3D packed array is fundamentally an electrically-addressed structure — exactly why MEMS uses integrated transduction and why the optics (§3.4) is desk-only scaffolding.

The build:

- **Planes:** each is one finished crossbar (glass plate + PVDF/PZT cell grid + row/col buses). Build and census them flat first (Phase 0), then stack.
- **Acoustic isolation between planes (the critical constraint):** the planes must not rigidly touch, or they couple and you lose the independent-layer model. Mount each plane on **nodal-point standoffs** (foam/sorbothane pads at the 0.224 L / 0.776 L nodal lines) carried on **threaded nylon rods at the corners**, outside the active area. Compliant point contact at nodes = each plane rings freely. This is the §3.1 nodal-mount principle extended vertically.
- **Vertical bus = the TSV analog:** an IDC **ribbon / pin-header bus** runs up the stack carrying the shared row/column lines. Each plane's crossbar taps the same vertical buses; a **layer-select** stage (the owned relay mux, or a second crosspoint IC) enables one plane at a time.
- **Address = `(layer, row, col)`:** layer-select picks the plane, then it's an ordinary M×N crossbar within that plane. **Still scale-invariant:** L planes add only a layer-select (≈ log₂L decode lines or L enables) on top of the shared M+N — the same wiring economy as 3D NAND / stacked crossbar memory.

```
   ┌───────────────┐  layer 2  ▓▓▓▓▓▓   ── nodal standoffs ──┐
   │ corner nylon  │  layer 1  ▓▓▓▓▓▓   ── nodal standoffs ──┤ shared row/col
   │ rods (4×)     │  layer 0  ▓▓▓▓▓▓   ── base ─────────────┘ ribbon bus = "TSVs"
   └───────────────┘            │   │
                     layer-select (relay / 2nd crosspoint) → drive/sense
   address a cell:  (layer, row, col)      buried planes: electrical-only (optics occluded)
```

**Two stack modes (tie to §3.7):**

- **Isolated stack** — nodal standoffs, planes independent → a denser **packed memory-bank / multi-PUF** array, the faithful analog of stacked independent dies.
- **Coupled stack** — deliberate compliant coupling between planes (a controlled bridge at an antinode, or electronic feedback layer→layer) → a genuine **3D reservoir / Ising network** with a vertical coupling dimension. The frontier build.

**Honest limits:** passive-matrix sneak paths cap clean arrays at ~8×8–16×16 per plane (read one row at a time, or rely on the crosspoint switch's isolation; large arrays need active addressing, same as real crossbar memories); inter-plane acoustic isolation is the make-or-break mechanical tolerance (sloppy standoffs = uncontrolled coupling); PVDF is a weak driver (favor shared-drive/array-sense, or PZT for per-cell drive); pitch is not µm (you model addressing topology and 3D packing, _not_ density — density stays a MEMS-only metric, per [FRONTIER_CEILING.md](FRONTIER_CEILING.md)).

### 3.3 The brain — FPGA lock-in instrument (the keystone, breaks B2)

This single board collapses four subsystems into one and is what makes temporal computation possible at desk scale:

- multi-tone **drive generation** (replaces/augments the Pico NCO),
- multichannel **lock-in demodulation** (matched-filter readout — sidesteps the killed raw-audio-capture failure, which lost information; lock-in preserves it),
- **real-time feedback** (electronic Q-control, PLL, parametric pump),
- **streaming acquisition** at kHz, so the drive→read loop runs faster than τ and τ/T_symbol ≈ 1.

Two options:

| Board                          | Why                                                                            | Cost                 |
| ------------------------------ | ------------------------------------------------------------------------------ | -------------------- |
| **Red Pitaya STEMlab 125-14**  | open-source, 2× fast ADC/DAC + FPGA, free PyRPL lock-in/PID suite, scriptable  | ~$400–550            |
| **Liquid Instruments Moku:Go** | turnkey lock-in + PID + spectrum + arbitrary-waveform instruments, less coding | ~$600+ (edu pricing) |

> **Note on Q-control direction:** your own ledger killed _active Q-boost at MEMS scale_ (H-B3, feedback-oscillation risk). At **desk scale the opposite is true** — a fast FPGA controlling a slow kHz mechanical resonator has large loop-delay margin, so velocity-feedback Q-synthesis is _easier_ here than on a die. This is one place the desk rig genuinely beats MEMS.

### 3.4 Optical readout — bring-up characterization tool (does not shrink)

Non-contact optical readout is **bring-up test equipment, not part of the array.** It removes receive-side PZT mass entirely, so it is the cleanest way to _prove_ rank-N and unmask intrinsic Q at desk scale — an independent cross-check on the crossbar (§3.2) that needs no transducer grid bonded yet. But it has **no MEMS counterpart**: the chip reads electrically via integrated transduction, so the laser/galvo is deleted at scale. Validate the physics with it, then let the crossbar carry the architecture. This is WL-B1 scaled from 1 plate to a rack.

- **Light:** 650 nm laser diode module (worklist BOM #1).
- **Channelization, two ways:**
  - **Galvo-scanned single beam** (efficient, cheap): one laser + one mirror galvo sweeps the beam across all plates and readout points → N _time-multiplexed_ virtual channels at kHz scan rates (far faster than relay switching).
  - **Photodiode array** (simultaneous): one BPW34 (BOM #2) per readout point → FPGA multichannel ADC → true _simultaneous_ rank-N. Channel-limited by ADC inputs.
  - **Best efficiency:** combine with frequency-diversified plates (§5) so a **single wideband pickup reads the whole array in one capture**.
- **Conversion:** knife-edge (razor half-occluding the reflected beam, BOM #5) turns plate deflection into intensity modulation → transimpedance amp → FPGA/scope. Escalation to quadrant PD (BOM #3) only if knife-edge SNR < 20 dB.

### 3.5 Drive & addressing

- **Drive:** Pico NCO (owned) for the carrier set, FPGA/AWG for multi-tone / parametric pump / phase-locked pairs, applied to the crossbar **row** bus.
- **Addressing (scale-faithful):** the **crosspoint switch** (§3.2) is the primary, MEMS-faithful address layer — (row, col) selection that maps 1:1 to on-die electrodes. The **relay mux** (owned) is the scrappy stand-in for the same job. **FPGA parallel lock-in** adds frequency selection; the **diversified cartridge** adds single-capture separation. See §5.

### 3.6 Vacuum + Q-control (high-Q / Ising upgrade)

- Small acrylic **bell jar** + **diaphragm vacuum pump** over the whole rack. Removing gas damping recovers much of the intrinsic Q (cheapest single step toward the parametric regime). Covers the array, not one plate.
- Combined with electronic Q-control (§3.3), this is the desk path toward the parametric threshold that the MEMS roadmap otherwise gates behind fabrication (WL-D3.3 / roadmap G7).

### 3.7 Coupling backplane — uncoupled vs coupled

The single design decision that determines what the array computes:

```
  UNCOUPLED  (memory bank / CAM / multi-PUF)      COUPLED  (reservoir / Ising)
  [P1][P2][P3][P4]                                [P1]~[P2]~[P3]~[P4]
   └── shared drive bus ──┘                         programmable J couplers
   each plate independent                           cross-plate modes emerge
   simplest to build & debug                        richer, harder, the frontier
```

- **Build uncoupled first** — each plate debuggable in isolation, cartridges swappable.
- **Two coupling axes:** _in-plane_ (plate↔plate within a layer) and _vertical_ (layer↔layer in the 3D stack, §3.2). The vertical axis is what makes the stacked build a true 3D network rather than independent memory planes.
- **Add coupling as an upgrade.** Two coupler types:
  - _Acoustic bridges_ — coffee-stirrer sticks / foam between adjacent plates or planes (BOM #13). Cheap, finicky, fixed.
  - _Electronic coupling_ — read plate/plane _i_, feed back into the drive of plate/plane _j_ via the FPGA. **Fully programmable J in software** — this is the right way to build the Ising coupler and to make the reservoir's coupling matrix sweepable, and it extends naturally to the `(layer, row, col)` 3D address.

### 3.8 Power & enclosure ("fully encapsulated")

- **Enclosure:** Pelican-style case (e.g., 1510/1520) or a small rack case; laser-cut acrylic/ply internal frame holding the card cage, optical head on a rigid sub-plate, and an electronics shelf.
- **Power:** fused IEC inlet → linear bench PSU (±9–12 V analog rails, +5 V logic) for low-noise analog, or a battery bank for portable demos. Keep analog and switching grounds separated (the project's recurring EMI lesson — twisted pairs, AGND returns).
- **Vibration:** sorbothane feet under the card cage; the case itself is the isolation enclosure.

### 3.9 Control interface & self-containment (one API, one box)

Everything above is hardware. This is how an operator _talks to it_ — and the design rule is: **the operator never touches the underlying boards. They issue one instruction; an orchestrator drives every transport beneath it.**

**The orchestrator (one process, one API).** A single host package (`tools/cwm_desk/`, the formalization of the architecture doc's Level-4 host API) owns every transport — Red Pitaya (SCPI/PyRPL), crosspoint switch (GPIO), Pico NCO (USB serial), PicoScope (USB, legacy) — and exposes the **PFU instruction set** ([CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) §3): `EXCITE`, `MEASURE`, `PROJECT`, `MATCH`, `FINGERPRINT`, `THRESHOLD`, `OPTIMIZE`. The desk rig runs the _same instruction set as the eventual processor_ — that is the connection, not a coincidence.

**What "broadcast a query" actually is** (the CAM demo, Phase 4) — one call, `cwm.match(query)`:

1. **A-DAC:** the query vector → a multi-tone drive waveform (the query's spectral fingerprint).
2. **Broadcast:** that waveform plays on the **shared TX rail** → all plates driven in parallel, one acoustic cycle.
3. **A-ADC:** one FDM capture reads every plate's response at once (§5).
4. **Score + argmax:** normalized overlap per plate → the match index + margin.

No per-plate scripting — the parallelism is the physics, and the API hides the devices.

**Control surfaces (cleanest first):**

| Surface                | What it is                                                                                                                                                                            | Best for                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **Local web UI**       | FastAPI/Flask served by the embedded host; buttons Enroll / Match / Write / Fingerprint / Run-Demo + live spectra and argmax plots; reachable from any browser on the case's own WiFi | demos, the self-contained appliance           |
| **CLI**                | `cwm match --query …`, `cwm fingerprint`, `cwm write …` — the same calls, scripted                                                                                                    | reproducible runs; the protocol agent-prompts |
| **One-button autorun** | a physical button / touchscreen tile runs a scripted sequence onto an onboard display                                                                                                 | unattended booth mode                         |

**Self-containment tiers:**

| Tier                        | Host                                                                                                    | External needs                | One-line                                    |
| --------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------- | ------------------------------------------- |
| **A — Tethered (bring-up)** | laptop over USB/Ethernet                                                                                | a laptop                      | simplest; the dev config                    |
| **B — Embedded core**       | Raspberry Pi 5 _inside_ the case (DD19) running orchestrator + web UI; case serves its own WiFi hotspot | any browser                   | one power cord in, everything else internal |
| **C — Appliance**           | embedded Pi + lid touchscreen (DD26) + run button (DD27), web UI in kiosk mode                          | power only (battery optional) | turn it on, it runs                         |

**Device consolidation — the clean build is two active boards, not five.** The bring-up pile (laptop + Red Pitaya + Pico NCO + Arduino relay mux + PicoScope) collapses:

- **Red Pitaya = the brain:** 2 DAC out (drive), 2 ADC in (sense), FPGA (lock-in/feedback), and its **GPIO drives the crosspoint address lines directly**. It runs Linux and _can_ be the host too; the safe split keeps the Pi as host and the Red Pitaya as instrument.
- **Crosspoint switch (§3.2) replaces the Arduino relay mux** for addressing — no separate USB device.
- **PicoScope becomes optional** (the Red Pitaya digitizes); kept only as the scrappy/legacy capture path.
- **Pico NCO retained only** for carriers above the Red Pitaya's convenient range, or in the scrappy build.

Clean self-contained appliance = **Pi 5 (host + web UI) + Red Pitaya (brain + crosspoint GPIO) + crossbar array + power, in one case, driven from one browser.**

> **Status:** the orchestrator is a near-term _software_ deliverable, not yet built — the architecture doc lists today's host API as "ad-hoc scripts in tools/ + notebooks/." Formalizing `tools/cwm_desk/` (drivers → PFU instructions → web UI) is the single cleanest software task that makes the rig demoable by a non-builder.

---

## 4. Property → Mechanism → Rung Map

Every MEMS _principle_ mapped to how the desk array shows it and which [FRONTIER_CEILING.md](FRONTIER_CEILING.md) rung / worklist ID it corresponds to.

| MEMS property                                    | Desk-array mechanism                                                                              | Maturity                                  | Rung / WL           |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------- | ----------------------------------------- | ------------------- |
| **General compute (associative/HD)**             | interference + resonant threshold + crossbar LUT cascade (§7A); array = codebook, no gates needed | ARCHITECTURAL (desk-achievable)           | §7A / Phase 4A      |
| **Physical kernel / neural inference (Level 3)** | full gradient response = kernel evaluation; learned readout = classification/regression (§7B)     | ARCHITECTURAL (desk-achievable)           | §7B / Phase 4A-D    |
| Rank-N interference matrix math                  | **crossbar array-sense** (rank-N electrically — shrinks); optical readout as bring-up cross-check | OPEN (rank-2 MEASURED)                    | R3 / WL-B1          |
| Eigenspectrum memory + associative search (CAM)  | one template per plate, broadcast query, argmax response                                          | MEASURED at rank-2; array native          | R2 / WL-B3          |
| Surface perturbation write/read/erase            | wax putty on a plate (owned)                                                                      | OPEN                                      | R1 / WL-A2          |
| Volumetric 3D write                              | diode/fiber engraving laser inscribes density sites in a plate                                    | SIMULATED (S21)                           | R6                  |
| Temporal reservoir                               | FPGA kHz streaming envelope, coupled plates                                                       | PROJECTED (bench-negative; desk-unlocked) | R9 / WL-D3.1-analog |
| Quantum-like non-separability                    | phase-locked drive + 2-point readout; extend to 3-DOF                                             | MEASURED (CHSH S=2.83)                    | R5 / WL-C1          |
| Parametric Ising                                 | vacuum + Q-control + 2f pump + electronic J coupling                                              | PROJECTED                                 | R10–R11 / WL-E1/E2  |
| Substrate unity                                  | one host runs the PFU instruction set across the whole rack                                       | the thesis                                | R8→R11              |

The one genuinely hard property is **parametric Ising** (needs high Q). Three desk paths, in order of cost-efficiency:

1. **Vacuum + nodal mount + electronic Q-control** on the existing plates.
2. A **quartz-tuning-fork module** — 32.768 kHz watch/AFM forks are ~$0.30 each, Q ≈ 10⁴ in air and 10⁵–10⁶ in vacuum. Parametrically pump and electronically couple several forks → a coherent oscillator Ising machine. Breaks the "single substrate" unity story but is the cheapest, highest-Q route to _proving the Ising spin primitive specifically_.
3. **Both:** prove spin physics on forks, then show it survives on plates.

---

## 5. The Multiplexing Design (the addressing problem)

N plates × M modes × K readout points is more channels than you can ADC directly. Four primitives, the first one MEMS-faithful:

1. **Crossbar (row/column) addressing** (crosspoint switch — the scale-faithful primary): select cell (i, j) by row i + col j. M×N cells, M+N lines, any pitch — identical to the on-die address scheme. The relay mux is the owned scrappy stand-in.
2. **Spatial mux** (relay mux — owned): one plate/point at a time. Simple, slow; the degenerate 1-D case of the crossbar.
3. **Frequency mux** (diversified cartridge): drive all plates, one wideband capture sees everything — **only works if plates occupy different bands**.
4. **FPGA parallel lock-in** (Red Pitaya): demodulate many reference frequencies simultaneously.

**The efficient answer:** address the array with the **crossbar** (the thing that shrinks), and overlay **frequency-division** on the diversified cartridge so one capture + FPGA parallel lock-in reads many cells at once. Reserve the **identical cartridge + crossbar addressing** for the PUF demo, where identical-by-design is the experiment.

---

## 6. Bill of Materials

Numbering is `DD#` to stay self-contained; items reused from the worklist BOM are noted as "WL #". Prices approximate, June 2026. **Owned (do not buy):** PicoScope 2204A, Pico H NCO, relay mux, Board A/D preamps, plates I/H + 25 mm plate, installed PZTs, wax putty.

Link conventions follow the worklist BOM (stable vendor + search-style links; verify exact SKUs — listings change).

### Tier 0 — already owned (reuse)

Pico NCO · relay mux · PicoScope · preamps · existing plates/PZTs · wax putty · CA glue.

### Tier 1 — Desk Minimum (~$750–1,050)

Proves: crossbar (row/column) addressing, rank-N interference, associative memory/CAM, temporal reservoir, non-separability, surface write.

| #    | Item                                                                           | For                   | Qty          | Est.      | Source (verify SKU)                                                                                                                                                                                                        |
| ---- | ------------------------------------------------------------------------------ | --------------------- | ------------ | --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DD1  | Red Pitaya STEMlab 125-14 (FPGA lock-in brain)                                 | B2, readout, feedback | 1            | ~$450     | [redpitaya.com](https://redpitaya.com) · [Mouser — Red Pitaya](https://www.mouser.com/c/?q=red%20pitaya)                                                                                                                   |
| DD2  | 650 nm laser diode module, 5 mW, TTL                                           | optical readout       | 1 (+1 spare) | ~$9 ea    | [Adafruit #1054](https://www.adafruit.com/product/1054) (= WL #1)                                                                                                                                                          |
| DD3  | Galvo scanner set (laser-show class, ±20°)                                     | scan beam across rack | 1            | ~$100–150 | search ["galvo scanner 30k laser show"](https://www.amazon.com/s?k=galvanometer+scanner+laser+30k) · lab-grade: [Thorlabs GVS012](https://www.thorlabs.com/thorproduct.cfm?partnumber=GVS012) (only if budget galvo fails) |
| DD4  | Si photodiode BPW34 (knife-edge / array)                                       | optical readout       | 8            | ~$1 ea    | [Digi-Key — BPW34](https://www.digikey.com/en/products/result?keywords=BPW34) (= WL #2)                                                                                                                                    |
| DD5  | Transimpedance amp parts (OPA2134 / OPA380, 100 kΩ, 10 pF)                     | PD front-end          | 1 set        | ~$15      | [Digi-Key — OPA2134](https://www.digikey.com/en/products/result?keywords=OPA2134)                                                                                                                                          |
| DD6  | Microscope slides (borosilicate, bulk) — diversified + identical cartridges    | substrate array       | 1–2 packs    | ~$8/72    | [Amazon — glass microscope slides](https://www.amazon.com/s?k=borosilicate+microscope+slides)                                                                                                                              |
| DD7  | PZT discs 10 mm (per-plate drive)                                              | drive coupling        | 10–20        | ~$1–2 ea  | [Digi-Key — 7BB-20-6L0](https://www.digikey.com/en/products/result?keywords=7BB-20-6L0) (= WL #6)                                                                                                                          |
| DD8  | Card-cage frame (laser-cut acrylic / 3D-printed slots) + nodal foam            | plate rack            | 1            | ~$25      | local laser-cut / print; foam = WL #13                                                                                                                                                                                     |
| DD9  | Articulating arms / posts (laser + galvo + PD mounts)                          | optics mounting       | 2–3          | ~$15 ea   | [Amazon — articulating magic arm clamp](https://www.amazon.com/s?k=articulating+magic+arm+clamp) (= WL #4)                                                                                                                 |
| DD10 | Multichannel USB audio interface, 8-in, 192 kHz (reservoir envelope streaming) | temporal demo         | 1            | ~$250     | search ["Behringer UMC1820"](https://www.amazon.com/s?k=behringer+umc1820) or [MOTU](https://motu.com/products)                                                                                                            |
| DD11 | Wiring, twisted-pair, AGND bus, connectors, breadboard                         | integration           | 1            | ~$30      | on hand / hardware store                                                                                                                                                                                                   |

**Crossbar add-on (Tier 1 core — the MEMS-faithful architecture, §3.2):**

| #    | Item                                                                    | For                 | Qty     | Est.      | Source (verify SKU)                                                                                                                                                                  |
| ---- | ----------------------------------------------------------------------- | ------------------- | ------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| DD20 | PVDF piezo film sheet (metallized, 28–110 µm) — low-mass crossbar cells | crossbar array (B1) | 1 sheet | ~$20–50   | search ["PVDF piezo film sheet"](https://www.amazon.com/s?k=PVDF+piezoelectric+film+sheet) · [TE piezo film sensors](https://www.te.com/en/products/sensors/piezo-film-sensors.html) |
| DD21 | Crosspoint analog switch IC (MT8816 8×16, or ADG2128) + breakout        | crossbar addressing | 1–2     | ~$5–12 ea | [Digi-Key — MT8816](https://www.digikey.com/en/products/result?keywords=MT8816) · [Digi-Key — ADG2128](https://www.digikey.com/en/products/result?keywords=ADG2128)                  |

**3D-stack add-on (packed-array model — stack several crossbar planes, §3.2):**

| #    | Item                                                                 | For                            | Qty     | Est.      | Source (verify SKU)                                                                                       |
| ---- | -------------------------------------------------------------------- | ------------------------------ | ------- | --------- | --------------------------------------------------------------------------------------------------------- |
| DD22 | Nylon threaded rod + standoff/nut kit (corner pillars, non-resonant) | stack frame                    | 1 kit   | ~$12      | search ["nylon threaded rod standoff kit M3"](https://www.amazon.com/s?k=nylon+standoff+threaded+rod+kit) |
| DD23 | Sorbothane / foam pads (nodal-point isolators between planes)        | inter-plane acoustic isolation | 1 sheet | ~$10      | search ["sorbothane pad sheet"](https://www.amazon.com/s?k=sorbothane+pad+sheet) (foam = WL #13)          |
| DD24 | IDC ribbon cable + 2.54 mm headers (vertical row/col "TSV" bus)      | stack interconnect             | 1 set   | ~$10      | search ["IDC ribbon cable kit 2.54mm headers"](https://www.amazon.com/s?k=idc+ribbon+cable+kit+2.54mm)    |
| DD25 | Layer-select: reuse owned relay mux, or 2nd crosspoint IC (= DD21)   | (layer, row, col) addressing   | 1       | $0 / ~$10 | owned, or [Digi-Key — MT8816](https://www.digikey.com/en/products/result?keywords=MT8816)                 |

**Self-contained control add-on (the "one box, one browser" appliance, §3.9):**

| #    | Item                                                                  | For                         | Qty | Est.    | Source (verify SKU)                                                                                                                                                                     |
| ---- | --------------------------------------------------------------------- | --------------------------- | --- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DD26 | Touchscreen for the lid (e.g. 7" HDMI/DSI) — onboard UI in kiosk mode | appliance control surface   | 1   | ~$60–90 | [Raspberry Pi Touch Display](https://www.raspberrypi.com/products/raspberry-pi-touch-display/) · search ["7 inch HDMI touchscreen"](https://www.amazon.com/s?k=7+inch+hdmi+touchscreen) |
| DD27 | Momentary run button + GPIO ribbon (crosspoint address + button)      | autorun + crosspoint wiring | 1   | ~$8     | search ["momentary push button panel mount"](https://www.amazon.com/s?k=momentary+push+button+panel+mount) + GPIO ribbon (on hand)                                                      |

> The embedded host itself is **DD19** (Tier 2). Add DD26–DD27 only for the fully self-contained appliance (Tier C, §3.9); Tier B (embedded core + bring-your-own browser) needs neither.

### Tier 2 — Briefcase Full (adds ~$1,300–2,500 → total ~$2,000–3,500)

Adds: vacuum/Q-control (high-Q regime), volumetric 3D write, parametric Ising fork module, full encapsulation.

| #    | Item                                                             | For                 | Qty     | Est.      | Source (verify SKU)                                                                                                                             |
| ---- | ---------------------------------------------------------------- | ------------------- | ------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| DD12 | Acrylic bell jar + 1/4-stage diaphragm vacuum pump               | recover intrinsic Q | 1       | ~$200–300 | [Amazon — vacuum chamber + pump kit](https://www.amazon.com/s?k=vacuum+chamber+diaphragm+pump+kit)                                              |
| DD13 | Quartz tuning forks 32.768 kHz (Ising spin module, high-Q)       | parametric Ising    | 10      | ~$0.30 ea | [Digi-Key — 32.768kHz tuning fork crystal](https://www.digikey.com/en/products/result?keywords=32.768khz+tuning+fork+crystal)                   |
| DD14 | Diode/fiber engraving laser module (volumetric inscription)      | 3D write (S21)      | 1       | ~$300–500 | search ["diode engraving laser module 5W"](https://www.amazon.com/s?k=diode+laser+engraver+module+5w) — eye-safety enclosure required           |
| DD15 | Second Red Pitaya or Moku:Go (more channels / feedback headroom) | scale-up            | 1       | ~$450–600 | [redpitaya.com](https://redpitaya.com) · [liquidinstruments.com Moku:Go](https://www.liquidinstruments.com/products/hardware-platforms/mokugo/) |
| DD16 | Precision resistor network (programmable-J fallback, 1 kΩ ±0.1%) | Ising coupling      | 1 strip | ~$5       | [Digi-Key — 1k 0.1% resistor](https://www.digikey.com/en/products/result?keywords=1k+0.1%25+resistor) (= WL #15)                                |
| DD17 | Pelican-style case + laser-cut internal frame, sorbothane feet   | encapsulation       | 1       | ~$150–250 | [Amazon — Pelican 1510/1520](https://www.amazon.com/s?k=pelican+1510+case)                                                                      |
| DD18 | Linear PSU (±12 V / +5 V) or battery bank + fused IEC inlet      | power               | 1       | ~$60–120  | [Amazon — linear bench power supply](https://www.amazon.com/s?k=linear+bench+power+supply)                                                      |
| DD19 | Host single-board computer (Raspberry Pi 5 / mini-PC) + display  | orchestration       | 1       | ~$80–150  | [Raspberry Pi](https://www.raspberrypi.com/products/raspberry-pi-5/)                                                                            |

> **Laser safety:** the engraving laser (DD14) and even the 650 nm pointer (DD2) require a closed, interlocked optical enclosure inside the case and appropriate eyewear. Do not operate the volumetric-write laser open-air. Treat DD14 as Class 4 unless the module's datasheet proves otherwise.

> **Link-rot warning:** search-style links are stable; exact listings change. Verify before buying — FPGA board revision, galvo angle/speed, true _line-in_ (not mic) on the audio interface, slide flatness, and fork frequency tolerance.

---

## 7. Build Phases (each tied to a worklist rung)

> **Full step-by-step procedures:** [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md) gives each phase below as a complete bench protocol (DD-P0 through DD-P10) with numbered steps, verification checks, agent prompts, success/kill criteria, data paths, and safety notes.

| Phase  | Build step                                                             | Unlocks                                | Rung / WL         | Tier  |
| ------ | ---------------------------------------------------------------------- | -------------------------------------- | ----------------- | ----- |
| 0      | Cartridge build + crossbar grid + per-cell census                      | baseline + addressing                  | R0 / §3.2         | 1     |
| 1      | Crossbar array-sense rank-N (+ optical cross-check)                    | rank-N (B1)                            | R3 / WL-B1        | 1     |
| 2      | Wire Red Pitaya as drive + parallel lock-in; kHz streaming loop        | temporal memory (B2)                   | R9 base           | 1     |
| 3      | Diversified cartridge + single-capture FDM readout                     | array addressing                       | R3 / §5           | 1     |
| 4      | CAM demo: one template/plate, broadcast query, argmax                  | associative search                     | R2 / WL-B3        | 1     |
| **4A** | **Hybrid logic / HD compute: interference + threshold + cascaded LUT** | **general compute (associative path)** | **§7A**           | **1** |
| 5      | Surface write (wax putty) across plates                                | write/read/erase                       | R1 / WL-A2        | 1     |
| 6      | Identical cartridge + addressing → PUF metrics                         | multi-device PUF                       | R2 / WL-B3        | 1     |
| 6B     | Non-separability (CHSH) + coherent phase switch                        | quantum-like                           | R5 / WL-C1, WL-B9 | 1     |
| 7      | Bell jar + electronic Q-control                                        | high-Q regime                          | toward R10        | 2     |
| 8      | Parametric pump + electronic J coupling (plates or forks)              | Ising spins                            | R10–R11 / WL-E1-2 | 2     |
| 9      | Volumetric laser write into a plate                                    | 3D memory                              | R6                | 2     |
| S      | Stack crossbar planes — (layer, row, col) packed array                 | 3D packing fidelity                    | R8 / §3.2         | 2     |
| 10     | Integrate under one host running the PFU instruction set               | substrate unity                        | R8→R11            | 2     |

**The associative path (Phases 0–4A) proves general compute with zero MEMS dependencies.** Phases 5–6B add storage and non-separability demos. Phases 7–10 + S are the MEMS-science upgrades (Von Neumann path + high-Q regime).

---

## 8. What This Demonstrator Can and Cannot Show

**Can demonstrate (the primary claim — general compute via the associative/HD path):** a working hyperdimensional computer that uses wave interference as the compute primitive, plate spectra as permanent memory, and the crossbar as an address bus — reaching general logic (Boolean operations, cascaded LUTs, FSM) at desk scale without any MEMS dependency. The array IS the processor AND the program.

**Can also demonstrate (every scientific principle of the MEMS device):** rank-N interference matrix math, associative/content-addressable search across an array, surface and volumetric writes, a working temporal reservoir, CHSH-style classical non-separability, and — best case — a parametric phononic spin network. All on glass you already own, orchestrated by one host, for roughly the price of a laptop.

**Cannot demonstrate (these need fabrication):** Gbit/cm³ density, MHz–GHz clock rates, fJ/op energy efficiency, monolithic integration, all-acoustic Von Neumann logic (Stages 3–6 without electronic threshold). These are _product_ metrics or _pure-acoustic_ science goals — the desk array proves the architecture and the computational model, which is precisely the evidence that justifies the spend to chase them.

> The demonstrator converts "trust our scaling laws" into "watch it compute — now fund the shrink." It is the bridge artifact between the validated bench and the MEMS grant.

---

## 9. Honest Risks

| Risk                                              | Mitigation                                                          |
| ------------------------------------------------- | ------------------------------------------------------------------- |
| Calibration is N× (each plate needs its mode map) | scriptable auto-census per slot; budget bench time                  |
| Identical plates overlap in frequency             | diversified cartridge for compute demos; relay/galvo for PUF        |
| Acoustic coupling bridges are finicky             | prefer **electronic** (FPGA feedback) coupling — programmable J     |
| Plate-to-plate Q spread (seen June: H vs I)       | diversify deliberately; budget for it in identical-plate demos      |
| Channel count explodes past ~16 plates            | pick a target array size; design the backplane/ADC for it           |
| EMI between drive and readout                     | twisted pairs, AGND returns, optical readout removes the worst path |
| Laser safety (DD2, DD14)                          | interlocked enclosure inside the case; eyewear; never open-air      |

---

## 10. Cross-References

- Capability ceiling and falsifiers: [FRONTIER_CEILING.md](FRONTIER_CEILING.md)
- Experiment specs, kill criteria, base BOM #1–#15: [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md)
- The PFU instruction set this hardware executes: [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md)
- Claim maturity ledger: [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md)
- Prior physical seed (5-plate fused-silica cassette, 2026-04-12 entry): [LAB_DIARY.md](LAB_DIARY.md)
- DOOM demo (first-person maze on glass — stacked-scrappy or 32-plate FDM): [DESK_DEMONSTRATOR_DOOM.md](DESK_DEMONSTRATOR_DOOM.md)
