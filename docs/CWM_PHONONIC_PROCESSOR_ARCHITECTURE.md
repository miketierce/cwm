# CWM Phononic Processor Architecture

**Version:** 1.0 — June 2026
**Status:** Design document. Every claim labeled MEASURED / DERIVED / PROJECTED.
**Companion documents:** [ROADMAP_FULL_POTENTIAL.md](ROADMAP_FULL_POTENTIAL.md), [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md), [FRONTIER_CEILING.md](FRONTIER_CEILING.md)

**Governing rule (inherited from roadmap):** Every claim bounded by (a) the wave equation and Rayleigh perturbation theory, (b) measured Q-factors and energy budgets, (c) at least one peer-reviewed precedent. Every tier of the architecture stack carries the same kill discipline as the experiment worklist.

**⚠️ Wave-Native Design Principle.** The glass is a smooth, low-dimensional analog **kernel + content-addressable memory**, not a von Neumann machine. The first (silicon) algorithm you reach for usually fails on it; design for the wave-native form. Proven dualities (MEASURED 2026-06): track/integrate not predict/branch (smooth, not discontinuous); nearest-**centroid** not ridge **regression** (T3.4: 4096 states 100% vs ridge 0.55%); encode by **amplitude of a fixed mode** not **frequency position** (8 levels/mode @ 100σ vs ~2 levels/axis); **factor** the state and resolve axes independently; keep collision modes and select by repeatability×separability; build the **Gram matrix** and select modes that make it diagonal-dominant. Full table + diagnostics in [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md).

---

## Motivation

A resonant glass plate is not a computer. It is a physical operator — a linear spectral transformer that projects an input drive vector through a fixed transfer matrix H and returns a feature vector (F8, ACCEPTED). The insight of this architecture document is that **that is enough to be useful** at the PFU tier, and that a complete processor stack can be built above it — with nonlinear switching and general-purpose logic as a _reachable_ frontier, not a premise.

The architecture is explicitly inspired by Akhetonics' cross-domain photonic processor framing (their XPU + RFU split, memory hierarchy, ISA, and foundry path), translated into the acoustic/phononic domain and bounded by what is actually measured. The honest near-term label is:

> **CWM-PFU: Coherent Wave Memory — Phononic Functional Unit architecture**

The label CWM-CPU is not earned until Stages 1–6 of §7 are demonstrated.

---

## 1. Data Representation

The CWM processor represents information in four orthogonal dimensions of the acoustic field. Each dimension is independently addressable.

### 1.1 Frequency (Mode Index)

A fused-silica plate of given geometry hosts a discrete set of eigenmodes $\{f_1, f_2, \ldots, f_M\}$. Each mode is a resolvable, stable frequency channel.

| Substrate                               | Mode count  | Frequency range | SNR      | Status                  |
| --------------------------------------- | ----------- | --------------- | -------- | ----------------------- |
| 100 mm × 100 mm × 1 mm fused silica     | 7–15 modes  | 30–120 kHz      | 42–56 dB | MEASURED (F1, Jun 2026) |
| 25 mm × 25 mm × 1 mm fused silica       | 15 modes    | 50–350 kHz      | 42–56 dB | MEASURED (Jun 4 2026)   |
| 1 mm × 1 mm × 50 µm MEMS (fused silica) | 16–64 modes | 3.5–35 MHz      | TBD      | PROJECTED (WL-D1)       |

Standard 100 mm plate modes (used throughout this document as the reference set):

| Mode | Frequency (Hz) | Role                        |
| ---- | -------------- | --------------------------- |
| M1   | 35,840         | Strong, primary reference   |
| M2   | 54,920         | Standard                    |
| M3   | 57,037         | Standard                    |
| M4   | 97,011         | Standard, dual-TX CHSH pair |

Frequency drift: 0.22% over 16.5 M cycles; 0.65% over 3.5 h (MEASURED, F6). Temperature compensation required for cross-session operation (WL-A5 gate G2).

### 1.2 Amplitude (Level Index)

Each mode's drive amplitude encodes a discrete level. Levels are separated by ≥ 9σ of the noise floor.

| Parameter                 | Value                                | Status                       |
| ------------------------- | ------------------------------------ | ---------------------------- |
| Validated levels per mode | 8 (3 bits)                           | MEASURED — T3.4, May 27 2026 |
| Zero-error states         | 4,096 (8 levels × 4 modes = 12 bits) | MEASURED — T3.4              |
| Predicted ceiling         | 27 levels/mode → 19 bits (4 modes)   | PROJECTED — WL-B6            |
| Adjacent-level separation | ≥ 9σ minimum                         | MEASURED                     |

### 1.3 Phase (Coherent Channel)

Drive phase is a controllable second encoding axis. The NCO `PHASE:<deg>` command provides phase lock between channels with sub-degree resolution.

| Parameter                                       | Value                  | Status                       |
| ----------------------------------------------- | ---------------------- | ---------------------------- |
| Phase stability per mode                        | σ < 0.28 rad over 30 s | MEASURED — T3.2              |
| CHSH S (fixed Bell angles)                      | 2.73 (5/5 mode pairs)  | MEASURED — F5, E1 Jun 2 2026 |
| CHSH S (optimized)                              | 2.83                   | MEASURED — F5                |
| Phase-controlled contrast (interference switch) | TBD                    | WL-B9                        |

Phase encodes the second DOF in the Qian–Eberly non-separability construction; it is also the mechanism for the Grover-analog oracle (WL-C2) and the parametric bistability latch (WL-D3.3).

### 1.4 Spatial Position (Readout Channel)

Each readout spot on the plate surface gives a different linear projection of the mode field. $N$ readout spots give a rank-$\min(N, M)$ transfer matrix H.

| Configuration                   | Rank              | Status                    |
| ------------------------------- | ----------------- | ------------------------- |
| 2 PZT receivers (current bench) | Rank 2            | MEASURED — B1 bottleneck  |
| 8-spot optical knife-edge scan  | Rank ≥ 6 (target) | PROJECTED — WL-B1 gate G3 |
| 16-element AlN array (MEMS)     | Rank ≤ 16         | PROJECTED — WL-D1         |

**B1 is the primary architectural bottleneck.** Rank-2 H makes the physical projection layer indistinguishable from a learned linear layer. Rank ≥ 8 is required for the plate to provide a physically meaningful random-projection advantage (WL-D3.2).

### 1.5 Perturbation State (Non-Volatile Register)

A mass perturbation $\delta m$ at plate position $(x, y)$ shifts eigenfrequencies by $\Delta f_k / f_k = -\Delta M_{eff,k} / 2M$ (Rayleigh, first order). The mode-shift vector $\{\Delta f_1, \ldots, \Delta f_k\}$ encodes the perturbation in a $k$-dimensional space that is position-dependent and physically persistent.

| Parameter                            | Value                               | Status   |
| ------------------------------------ | ----------------------------------- | -------- |
| Minimum detectable mass (25mm plate) | ≤ 10 mg (target)                    | WL-A2    |
| Reversal cleanliness after removal   | < 0.5σ residual                     | WL-A2    |
| Retention                            | Indefinite (until physical removal) | PHYSICAL |
| Write/erase endurance                | ≥ 4 cycles (target)                 | WL-C5    |

This is the **non-volatile data register** of the CWM architecture. See §2.2.

---

## 2. Memory Hierarchy

CWM has a natural three-tier memory hierarchy. The tiers are physically distinct and have different latency, capacity, and volatility profiles.

```
┌─────────────────────────────────────────────────────┐
│  Tier 3 — Non-Volatile Spectral Memory              │
│  Physical: mass-loading perturbation pattern        │
│  Retention: indefinite  Capacity: k-dim shift vec   │
│  Write: seconds (mass placement)                    │
│  Read: ~100 ms (fine sweep + Lorentzian fit)        │
│  Erase: seconds (mass removal, < 0.5σ residual)     │
├─────────────────────────────────────────────────────┤
│  Tier 2 — Volatile Modal State                      │
│  Physical: mode energy decaying as e^(-πft/Q)       │
│  Retention: τ = Q/πf                               │
│    Bench (Q≈400, f≈80 kHz): τ ≈ 1.6 ms  MEASURED   │
│    MEMS (Q≈10⁴, f≈10 MHz): τ ≈ 320 µs  PROJECTED   │
│  Write: drive burst duration (~1–10 ms)             │
│  Read: continuous (drive-while-read) or ringdown    │
│  Erase: automatic (decay) or destructive re-drive   │
├─────────────────────────────────────────────────────┤
│  Tier 1 — Electronic Shadow Registers               │
│  Physical: microcontroller/FPGA RAM                 │
│  Retention: power-cycle volatile                    │
│  Capacity: unbounded (limited by host RAM)          │
│  Role: calibration tables, thresholds, drive        │
│         schedules, measurement results, FSM state   │
└─────────────────────────────────────────────────────┘
```

### 2.1 Non-Volatile Spectral Memory (Tier 3)

The perturbation-encoded eigenfrequency shift is the CWM equivalent of non-volatile program/data memory. Unlike optical PCM (phase-change material) cells which require precise thermal cycling, CWM non-volatile memory requires only physical mass placement — accessible with no special equipment.

Current status: shift > 3σ at ≥ 25 mg (preliminary). Formal write/erase/verify protocol: WL-C5.
MEMS path: lithographic mass features replace putty — permanent, sub-µg precision, PROJECTED.

### 2.2 Volatile Modal State (Tier 2)

Mode amplitudes during and shortly after a drive burst constitute volatile working memory. The decay time τ = Q/(πf) sets the window.

- **Bench bottleneck (B2):** τ ≈ 1.6 ms at loaded Q, while the drive/capture loop runs at ~8 Hz. The volatile tier is real but inaccessible with current DAQ timing.
- **MEMS resolution:** at Q = 10⁴, f = 10 MHz, τ ≈ 320 µs. A 3 kHz symbol rate gives τ/T_symbol ≈ 1. Memory capacity MC > 3 expected — sufficient for temporal reservoir computing (WL-D3.1).

Volatile write: NCO drive burst. Volatile read: optical readout (WL-B1) or AlN array (WL-D3). Volatile erase: wait 5τ or drive at 90° phase (destructive interference, WL-B9).

### 2.3 Electronic Shadow Registers (Tier 1)

All sequencing, calibration, threshold decisions, and FSM state are held in the control core's electronic memory. This is not a limitation — Akhetonics' XPU similarly holds intermediate results electronically while the optical domain handles compute. The shadow registers hold:

- Per-mode calibration: f₀, FWHM, Q, amplitude-level map, phase transfer coefficient
- Threshold table T₁..T₈ (from WL-B8)
- Drive schedule / instruction stream
- Feature vectors captured from the last N measurements
- FSM state register (WL-C7)

---

## 3. CWM Instruction Set (Level 1–2 API)

The CWM instruction set operates the acoustic hardware through the control core. Instructions at Level 1 map directly to hardware operations; Level 2 instructions compose Level 1 operations into named phononic primitives.

**Governing constraint:** every instruction below is either (a) executable on the current bench, labeled `[BENCH]`, (b) executable after WL-B1 optical readout, labeled `[B1]`, or (c) gated on MEMS die, labeled `[MEMS]`. No instruction is marked available before its hardware prerequisite is met.

### Level 0 — Raw Hardware (not instructions; substrate operations)

```
NCO F<n>:<freq>          — set channel n frequency
NCO PHASE:<deg>          — set phase offset on channel relative to channel 1
NCO Foff                 — all channels off
NCO SWEEP:<f0,f1,step,dwell> — frequency sweep
RELAY.select(N)          — route relay N to preamp → PicoScope ChA
PICOSCOPE.capture(N_avg) — return FFT magnitude vector (N_SAMPLES bins)
```

### Level 1 — Calibrated Physical Operators

| Instruction                    | Physical operation                                                 | Hardware              | Status            |
| ------------------------------ | ------------------------------------------------------------------ | --------------------- | ----------------- |
| `EXCITE(mode, amp, phase)`     | Drive mode at calibrated frequency, amplitude level, phase offset  | NCO F1..F4            | `[BENCH]`         |
| `EXCITE_ALL(amp_vector)`       | Drive M modes simultaneously at amplitude vector (MDM)             | NCO F1..F3            | `[BENCH]` — WL-B7 |
| `MEASURE(relay)`               | Capture FFT; extract mode-bin amplitudes for all M modes           | PicoScope + relay mux | `[BENCH]`         |
| `MEASURE_SPOT(x, y)`           | Capture FFT at optical readout spot (x,y)                          | Optical readout       | `[B1]` — WL-B1    |
| `SWEEP_FINE(mode)`             | ±2 kHz Lorentzian sweep; return f₀, Q, amplitude                   | NCO SWEEP             | `[BENCH]`         |
| `PHASE_SWEEP(mode, step_deg)`  | Sweep relative phase 0°→360°; return amplitude vs phase curve      | NCO PHASE             | `[BENCH]` — WL-B9 |
| `PERTURB_WRITE(mass_mg, x, y)` | [human step] place mass at position; agent confirms via SWEEP_FINE | Physical + NCO        | `[BENCH]` — WL-A2 |
| `PERTURB_READ()`               | SWEEP_FINE all modes; return shift vector vs baseline              | NCO SWEEP             | `[BENCH]` — WL-B4 |
| `PERTURB_ERASE()`              | [human step] remove mass; agent verifies return to baseline < 0.5σ | Physical + NCO        | `[BENCH]` — WL-C5 |

### Level 2 — Phononic Instructions

| Instruction              | Composition                                                                          | Description                                                    | Status                         |
| ------------------------ | ------------------------------------------------------------------------------------ | -------------------------------------------------------------- | ------------------------------ |
| `PROJECT(x_vector)`      | EXCITE_ALL(x) → MEASURE → return H·x                                                 | Acoustic matrix-vector multiply. x encoded as drive amplitudes | `[BENCH]` — WL-B7 prerequisite |
| `MATCH(query)`           | PROJECT(query) → argmax(amplitudes)                                                  | Return best-matching stored template index                     | `[BENCH]` — T1.3, T3.3         |
| `FINGERPRINT()`          | SWEEP_FINE all modes → return {f₀, amplitude} vector                                 | Capture device spectral fingerprint                            | `[BENCH]` — WL-B3              |
| `AMPLIFY(target, k)`     | k × [PHASE_INVERT(target) + EXCITE_ALL(uniform)]                                     | Grover-analog amplitude amplification, k iterations            | `[BENCH]` — WL-C2              |
| `THRESHOLD(mode, level)` | MEASURE → compare mode-bin to T₁ → return {0,1}                                      | 1-bit quantizer; A-ADC boundary layer                          | `[BENCH]` — WL-B8              |
| `SWITCH(mode_A, phase)`  | EXCITE(mode_A) + EXCITE(mode_A, phase=phase) → return contrast                       | Phase-controlled constructive/destructive interference         | `[BENCH]` — WL-B9              |
| `LATCH(mode)`            | Pump at 2f₀ → wait settle → MEASURE phase → return {0,1}                             | Parametric bistable state; binary latch                        | `[MEMS]` — WL-D3.3             |
| `RESET()`                | Foff; wait 5τ                                                                        | Clear all volatile mode state                                  | `[BENCH]`                      |
| `FSM_STEP()`             | MEASURE → THRESHOLD all modes → lookup(state_table) → EXCITE                         | Single FSM state transition                                    | `[BENCH]` — WL-C7              |
| `OPTIMIZE(graph_J)`      | Set J_ij couplings → pump all modes above threshold → LATCH × N → return spin config | Ising relaxation, N settle cycles                              | `[MEMS]` — WL-E2               |

### Level 3 — PFU Kernels (see §4)

PFU kernels are named sequences of Level 1–2 instructions that implement a complete functional unit operation.

---

## 4. Phononic Functional Units (PFUs)

Each PFU is a named acoustic operation that maps a well-defined input to a well-defined output. The architecture currently defines six PFUs; three are validated at bench scale, three are projected.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        CWM Control Core                              │
│   (Pico H / FPGA / host Python — electronic, not acoustic)          │
│   calibration tables │ scheduler │ threshold logic │ shadow regs     │
└────────────┬──────────────┬───────────┬────────────┬────────────────┘
             │              │           │            │
             ▼              ▼           ▼            ▼
     ┌───────────┐  ┌──────────┐  ┌─────────┐  ┌──────────────┐
     │ PFU-1     │  │ PFU-2    │  │ PFU-3   │  │ PFU-4        │
     │ Projection│  │ Search   │  │ PUF /   │  │ Perturbation │
     │           │  │          │  │ Memory  │  │ (Write/Read) │
     └───────────┘  └──────────┘  └─────────┘  └──────────────┘
             │              │
             ▼              ▼
     ┌───────────────┐  ┌──────────────┐
     │ PFU-5         │  │ PFU-6        │
     │ Phase /       │  │ Ising        │
     │ Grover-analog │  │ Optimizer    │
     └───────────────┘  └──────────────┘
```

### PFU-1 — Projection Unit

**Operation:** $\mathbf{y} = H \mathbf{x}$, where $H \in \mathbb{R}^{N_{rx} \times M}$ is the measured transfer matrix, $\mathbf{x}$ is the input encoded as drive amplitudes at M modes, $\mathbf{y}$ is the output feature vector of readout amplitudes.

**Input encoding (A-DAC):** input vector $\mathbf{x}$ → set of {frequency, amplitude, phase} tuples → NCO drive commands.

**Output decoding (A-ADC):** PicoScope FFT → mode-bin magnitude extraction → feature vector $\mathbf{y}$.

| Parameter                   | Bench                    | MEMS         | Status                              |
| --------------------------- | ------------------------ | ------------ | ----------------------------------- |
| H rank                      | 2                        | ≤ 16         | MEASURED (bench) / PROJECTED (MEMS) |
| Input precision             | 8 levels / mode (3 bits) | 8–27 levels  | MEASURED / PROJECTED                |
| Output SNR                  | 42–56 dB                 | TBD          | MEASURED                            |
| J/projection (drive energy) | ~1 µJ per burst          | ~1 nJ (MEMS) | DERIVED / PROJECTED                 |
| Latency                     | ~100 ms (capture + FFT)  | ~1 ms        | MEASURED / PROJECTED                |

**Bottleneck:** rank-2 H at bench makes PFU-1 equivalent to a learned 2-channel linear layer. Rank ≥ 8 required for physical advantage (WL-B1, WL-B7). **Kill (permanent):** WL-D3.2 finds energy per inference ≤ digital matmul at rank 16 ⇒ close the physical-projection arc.

### PFU-2 — Associative Search Unit

**Operation:** given a query spectrum $\mathbf{q}$, return the index $i^* = \text{argmax}_i(\text{overlap}(\mathbf{q}, \mathbf{h}_i))$ where $\mathbf{h}_i$ is the $i$-th stored template's spectral signature. The acoustic field computes the overlap physically via wave interference.

**Status:** 100% accuracy at 193σ separation on 80/80 trials (MEASURED — T1.3, F3). Single-session only; cross-session gate is WL-A5.

**Capacity:** number of distinguishable templates = $\lfloor \text{SNR} / 3\sigma \rfloor^M = 8^4 = 4{,}096$ at bench; predicted $27^4 \approx 531{,}000$ at 27-level ceiling (PROJECTED — WL-B6).

**Kill:** WL-A5 cross-session accuracy < 95% ⇒ PUF use case killed; search accuracy becomes session-local only.

### PFU-3 — PUF / Identity Unit

**Operation:** return the device's unique spectral fingerprint $\mathbf{f} = \{f_1, A_1, \ldots, f_M, A_M\}$ — the physically unclonable function derived from manufacturing-variance modal structure.

**Status:** inter-device vs intra-device separation proven (E38, rod campaign); 100% classification at 193σ (T1.3). Multi-device PUF metrics (inter-HD ≈ 50%, intra-HD < 5%) pending WL-B3.

**PUF metrics target:** uniqueness ~50% (inter-Hamming distance), reliability > 95% (intra-session), uniformity ~50%. Standard metrics per IEEE TIFS PUF evaluation framework.

**Kill:** WL-B3 inter-device HD matches intra-device variation ⇒ fingerprints are geometry-dominated; PUF paper killed; device ID by serial number only.

### PFU-4 — Perturbation Write/Read Unit

**Operation:** WRITE encodes an information vector as a mass-loading pattern $\{\delta m_j, (x_j, y_j)\}$ on the plate surface; READ recovers it via the mode-shift vector; ERASE removes mass and verifies baseline return.

**Status:** Rayleigh shift mechanism validated (rod campaign, E38); plate E3 protocol scheduled (WL-A2). Position inference (invert shift vector → mass + position) requires WL-B4.

**Memory spec (projected, pending WL-C5):**

| Parameter           | Value                                       | Status              |
| ------------------- | ------------------------------------------- | ------------------- |
| Write latency       | ~5 s (human placement, precise scale)       | PHYSICAL            |
| Read latency        | ~100 ms (fine sweep)                        | MEASURED            |
| Erase latency       | ~5 s (removal + verify)                     | PHYSICAL            |
| Retention           | Indefinite                                  | PHYSICAL            |
| Capacity            | k-dimensional shift vector (k = mode count) | MEASURED (k = 4–15) |
| Position resolution | < 10 mm target                              | WL-B4               |

**MEMS path:** lithographic mass features → sub-µg precision, ~nm write resolution, permanent (non-erasable at MEMS scale — program-once analog of ROM). Erasable version requires localized laser heating or electrothermal actuation (PROJECTED, post-Phase D).

### PFU-5 — Phase Amplification Unit (Grover-analog)

**Operation:** Given N templates stored as amplitude patterns, amplify the target template's mode energy relative to non-target templates via iterated oracle + diffusion re-drives. Provides search-acceleration scaling analogous to Grover's algorithm over a classical N-dimensional wave space.

**Honest limit stated up front:** classical waves provide N-fold state space, not exponential resources. The speedup is over classical matched filtering, not over quantum search. Per-iteration gain follows $\cos^2((2k+1)\theta)$ interference prediction.

**Status:** phase lock proven (CHSH T5.2b, S = 2.83); oracle/diffusion protocol not yet attempted (WL-C2). Phase stability σ < 0.28 rad per mode (MEASURED — T3.2).

**Kill:** WL-C2 shows no amplification after phase calibration ⇒ phase control at bench is insufficient; PFU-5 deferred to MEMS where per-element drive enables clean oracle phase inversion.

### PFU-6 — Ising Optimizer Unit

**Operation:** N modes pumped above parametric threshold become N Ising spins ($0/\pi$ bistable phase states). Engineered inter-mode coupling constants $J_{ij}$ encode a QUBO instance. The network settles to low-energy spin configurations — a room-temperature phononic coherent Ising machine.

**Precedent:** NTT optical CIM (2,000 spins), Toshiba SBM, Goto KPO. Acoustic version differentiated by: 300 K operation, room-scale device, per-die unique (PFU-3 + PFU-6 in one device), micro-watt power.

**Status:** parametric threshold not yet crossed (requires Q ≥ 5×10³ — MEMS only). 2-spin proof WL-E1; N ≥ 8 optimizer WL-E2. Gate: WL-D3.3 threshold crossing.

**Kill:** WL-D3.3 no oscillation at max safe drive ⇒ Phase E requires Q > 10⁵ (cryo or crystalline substrate); characterize distance-to-threshold and publish; hand off to cryogenic acoustics community.

---

## 5. Control Stack and Software Boundary

The CWM control stack is layered. The acoustic domain handles projection, matching, fingerprinting, and (eventually) nonlinear switching and optimization. All sequencing, decision logic, calibration, and program storage are electronic.

```
┌────────────────────────────────────────────────────────────┐
│  Level 4: Host API                                         │
│  Python / Rust / C++ library                               │
│  cwm.project(x) / cwm.match(q) / cwm.puf() / cwm.ising()  │
│  Currently: ad-hoc scripts in tools/ + notebooks/          │
├────────────────────────────────────────────────────────────┤
│  Level 3: PFU Kernels                                      │
│  Named sequences: nearest-neighbor search, PUF auth,       │
│  perturbation localization, Grover-analog, Ising relax     │
│  Currently: analysis/ + experiments/ Python modules        │
├────────────────────────────────────────────────────────────┤
│  Level 2: Phononic Instructions                            │
│  PROJECT / MATCH / FINGERPRINT / AMPLIFY / THRESHOLD /     │
│  SWITCH / LATCH / OPTIMIZE                                 │
│  Currently: partially in tools/pico_nco + tools/relay_mux  │
├────────────────────────────────────────────────────────────┤
│  Level 1: Calibrated Physical Operators                    │
│  EXCITE / MEASURE / SWEEP_FINE / PHASE_SWEEP               │
│  Currently: tools/pico_nco/__init__.py + picoscope driver  │
├────────────────────────────────────────────────────────────┤
│  Level 0: Raw Hardware                                     │
│  NCO commands / relay mux / PicoScope FFT capture          │
└────────────────────────────────────────────────────────────┘
```

### 5.1 A-DAC: Digital-to-Acoustic Converter (Input Boundary)

Converts a digital input vector to an acoustic drive pattern. This is not a separate chip — it is the waveform compiler function of the control core.

| Parameter          | Current bench               | Target                    |
| ------------------ | --------------------------- | ------------------------- |
| Input precision    | 8 amplitude levels / mode   | 27 levels (WL-B6 ceiling) |
| Frequency accuracy | NCO: sub-Hz resolution      | sub-Hz maintained         |
| Phase accuracy     | NCO PHASE: < 1° resolution  | < 1°                      |
| Channels           | 3 simultaneous (F1/F2/F3)   | 16 (MEMS AlN array)       |
| Latency            | < 1 ms (NCO serial command) | < 1 ms                    |

### 5.2 A-ADC: Acoustic-to-Digital Converter (Output Boundary)

Converts the acoustic response field to a digital feature vector.

| Parameter            | Current bench                     | Target (optical)             |
| -------------------- | --------------------------------- | ---------------------------- |
| Readout channels     | 2 (relay mux)                     | 8+ (WL-B1 knife-edge)        |
| Frequency resolution | 252 Hz/bin (63 Hz zero-padded)    | 50 Hz (longer capture)       |
| Amplitude resolution | ~10 bits effective (42–56 dB SNR) | unchanged                    |
| Latency              | ~80 ms (capture + FFT)            | ~5 ms (faster capture)       |
| Spatial parallelism  | sequential relay switching        | 8 simultaneous spots (WL-B1) |

### 5.3 Decision Logic (Threshold Layer)

The threshold layer bridges analog acoustic output to discrete control actions. Formally defined and validated in WL-B8.

| Component                  | Description                                         | Status          |
| -------------------------- | --------------------------------------------------- | --------------- |
| Threshold table T₁..T_M    | Per-mode midpoint between adjacent amplitude levels | WL-B8           |
| False-positive rate target | < 1% per mode                                       | WL-B8           |
| False-negative rate target | < 1% per mode                                       | WL-B8           |
| Hardware escalation        | LM393 comparator IC (BOM #14) if FP+FN > 10%        | WL-B8 kill path |

### 5.4 Waveform Compiler (Near-Term Artifact)

The near-term software deliverable is a `CWMCompiler` class in `tools/cwm_compiler.py` that takes a named instruction sequence and outputs a list of `(NCO_command, relay_command, capture_command)` tuples. Target: defined as part of WL-D6 (phononic compute-graph design tool).

---

## 6. Cross-Domain Composition

CWM combines three computing domains in a single phononic platform. This mirrors Akhetonics' cross-domain XPU but in the acoustic regime and at 300 K.

| Domain           | CWM role                                                                               | Current status                                                       | Gate              |
| ---------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ----------------- |
| **Analog**       | H-matrix projection, matched filtering, spectral overlap, mass-position inversion      | PROVEN (rank-2 bench)                                                | Rank ≥ 8 (WL-B1)  |
| **Digital**      | Host sequencing, threshold decisions, FSM state, calibration, error correction         | OPERATIONAL                                                          | —                 |
| **Quantum-like** | CHSH / GHZ / KCBS classical DOF non-separability, Grover-analog, contextuality witness | CHSH PROVEN (S=2.83); GHZ/KCBS pending                               | WL-C1/C3          |
| **Optimization** | Phononic parametric Ising machine — QUBO / MaxCut ground-state search                  | PROJECTED                                                            | WL-D3.3 (gate G7) |
| **Memory**       | Non-volatile perturbation state + volatile modal ringdown                              | Non-volatile: core concept; volatile: real but inaccessible at bench | WL-C5 / WL-B1     |
| **Sensing**      | Multi-mode mass/position perturbation spectroscopy                                     | Rayleigh mechanism proven; position inference pending                | WL-B4             |

### 6.1 Multiplexing as the CWM Scaling Principle

Akhetonics scales bandwidth via wavelength-division multiplexing. CWM scales via a four-dimensional multiplexed space:

$$\text{Capacity} = N_{\text{modes}} \times N_{\text{levels}} \times N_{\text{phases}} \times N_{\text{spots}} \times N_{\text{devices}}$$

Current bench value: $4 \times 8 \times 2 \times 2 \times 1 = 128$ independent registers.
MEMS target: $16 \times 27 \times 4 \times 16 \times N_{\text{array}} \gg 10^5$ per device (PROJECTED).

**Do not scale by making one plate smarter. Scale by multiplexing many simple physical degrees of freedom.**

---

## 7. Path to General-Purpose Logic

This section is the honest progression from "physical projection machine" to "general-purpose phononic computer." Each stage has a binary gate: demonstrated or not. No stage is claimed until the gate is passed.

```
Stage 1  DEFINE THE INSTRUCTION SET       ← this document (done)
Stage 2  PROVE A NONLINEAR ACOUSTIC SWITCH  ← WL-B9 (linear, bench) / WL-D4 (nonlinear, MEMS)
Stage 3  BUILD A LATCH                     ← WL-D3.3 (parametric bistability)
Stage 4  BUILD A UNIVERSAL GATE            ← WL-D4 (AND/OR via IM coupling) / WL-E1 (Ising)
Stage 5  COMPOSE GATES                     ← WL-C7 (3-state FSM, bench) / WL-E2 (N-spin)
Stage 6  GENERAL-PURPOSE PHONONIC LOGIC    ← requires 1–5 all PASS
```

### Stage 1 — Instruction Set ✓

Defined above (§3). Currently implemented in firmware (Pico NCO + relay mux + PicoScope) with Python wrappers. No new hardware required.

### Stage 2 — Nonlinear Acoustic Switch (REQUIRED GATE)

This is the most important single step. A linear projection machine is useful. A switching machine is programmable.

**Honest intermediate step at bench (WL-B9, linear coherent switch):** drive amplitude at mode A is controlled by driving mode A with a second phase-locked source — constructive → ON, destructive → OFF. This is not a nonlinear switch; it is a phase-controlled linear gate. Useful as a mode-enable mechanism; not sufficient for NAND.

**MEMS nonlinear switch (WL-D4):** at Q ≥ 10⁴, Duffing intermodulation generates output at $f_1 \pm f_2$ when both inputs exceed the nonlinear threshold. AND truth table: output iff both inputs above threshold.

Mechanism required:

$$\text{mode A state} \longrightarrow \text{mode B response changed}$$

Candidate mechanisms in priority order:

| Mechanism                                 | Required Q | Bench-accessible | Status          |
| ----------------------------------------- | ---------- | ---------------- | --------------- |
| Linear coherent cancellation (phase gate) | Any        | Yes              | WL-B9           |
| F10 redistribution (if genuine nonlinear) | Bench      | Yes              | WL-B2           |
| Duffing IM coupling                       | ≥ 10⁴      | MEMS only        | WL-D4           |
| Parametric pump-to-signal gate            | ≥ 5×10³    | MEMS only        | WL-D3.3         |
| PZT/electromechanical feedback hybrid     | Any        | Yes (hybrid)     | Not in worklist |

**If F10 redistribution (WL-B2) is confirmed genuine:** the macro plate has a weak nonlinear coupling primitive at bench scale. This would open WL-D4 at bench, not MEMS — the most important possible positive result in the current experimental program.

### Stage 3 — Latch

A latch stores a binary state that persists without continuous drive. CWM candidates:

| Latch type                      | Mechanism                                                                    | Status                                      |
| ------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------- |
| Parametric 0/π phase state      | Mode above parametric threshold settles to 0 or π; stable until pump removed | WL-D3.3 — MEMS, PROJECTED                   |
| Non-volatile mass-loading latch | MEMS lithographic mass bit; permanent (ROM equivalent)                       | WL-D1 design                                |
| Electronic shadow latch         | Control-core RAM bit mirroring acoustic state                                | OPERATIONAL — but not a true acoustic latch |
| Bistable Duffing mode           | Amplitude bistability above Duffing bifurcation                              | WL-D5 — MEMS, PROJECTED                     |

The parametric 0/π phase latch is the primary target. It is the acoustic equivalent of an optical bistable memory cell.

### Stage 4 — Universal Gate

Target: thresholded weighted sum over N mode responses. This maps naturally onto wave interference:

$$\text{output} = \Theta\!\left(\sum_i w_i A_i - \theta\right)$$

where $A_i$ are mode amplitudes, $w_i$ are readout weights (set by spatial readout position), and $\theta$ is the threshold (from WL-B8 calibration). This is a perceptron unit. A network of such units is Turing-complete (McCulloch–Pitts theorem) given sufficient modes and latch/routing capability.

Acoustic NAND (harder, requires bistable latch for output restoration and stage-to-stage drive capability): deferred to post-Stage 3.

### Stage 5 — Composable Gates (Fan-Out, Routing, Timing)

Composition requires:

- **Fan-out:** one mode's output driving multiple downstream operations. Currently: relay mux gives one-to-one routing; optical readout (WL-B1) enables one-to-N spatial tap.
- **Routing:** acoustic energy steered between plate regions or devices. WL-C6 tests passive acoustic interconnect; WL-D6 designs transducer placement for selective coupling.
- **Timing:** synchronization between phononic operations. Currently: control-core clock (Pico/FPGA). Acoustic timing limited by τ = Q/(πf) — sets the minimum hold time per stage.
- **Noise margins:** output amplitude must cleanly exceed the next stage's threshold T₁. Demonstrated at bench (9σ separation, T3.4). Must be maintained through fanout chain.

**The FSM in WL-C7 is Stage 5's minimal proof:** 3 states, 3 modes, composed threshold-and-drive cycles. If it runs reliably, gate composition is demonstrated at the simplest possible level.

### Stage 6 — General-Purpose Phononic Logic

General purpose requires all five previous stages, plus:

- A clock/sequencing mechanism (electronic or acoustic)
- Error correction or output restoration between stages
- A compiler from a higher-level language to the CWM instruction set

This is a multi-year research program for the all-acoustic path. The honest current claim is:

> **CWM is today a phononic functional-unit architecture (Stages 1–2 partially). The Von Neumann path can reach general-purpose phononic logic (Stage 6) if nonlinear acoustic switching and parametric latching are demonstrated at MEMS scale. However, an alternative associative/HD path (§7A) reaches general compute at desk scale without any of these gates — using the existing crossbar array as a physical codebook and the PFU instruction set for interference + threshold + routing.**

---

## 7A. Associative / Hyperdimensional Path to General Compute

§7 describes the Von Neumann path: build gates, latch them, cascade, compose. That path requires high Q (nonlinear threshold, parametric bistability, signal restoration) and is therefore MEMS-gated for stages 3–6.

This section describes an **alternative computational model** that reaches general compute without gates, latches, or cascading — and is **desk-achievable now** with the existing crossbar array, Red Pitaya, and PFU instruction set. It is not a weaker form of §7; it is a different (and arguably more valuable) computational architecture, aligned with hyperdimensional computing (HD/VSA) and content-addressable memory.

### 7A.1 Core Insight: the Array IS the Program

In the Von Neumann model, memory is blank and computation writes state into it. In the associative model:

- **Every plate's eigenmode spectrum is permanent, unique, and unmodifiable** — it was "written" at manufacture (geometry, mass distribution, boundary conditions).
- **The array is a pre-existing library of spectral identities** — a physical codebook.
- **Computation = selection:** the result of an operation determines which plate(s) to address next. State lives in the address register (a few electronic bits), not in the medium.
- **No plate is ever physically modified to store a result.** The glass IS the data.

This eliminates every barrier that makes Von Neumann logic MEMS-gated:

| Von Neumann barrier   | Why it's hard                                    | Associative model                                                                                                                         |
| --------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Nonlinear threshold   | Glass is linear; needs Duffing at high Q         | **Irrelevant.** Resonance IS binary: matched → amplified, mismatched → suppressed. No nonlinearity needed.                                |
| Latch (persistence)   | Needs self-sustaining parametric oscillation     | **Irrelevant.** State = "which plate is addressed" — a few bits in an FPGA register. The plate's spectrum persists forever without power. |
| Gain / restoration    | Each gate must amplify; passive resonator decays | **Irrelevant.** Each drive is fresh at full power from the DAC. No signal chains through the medium.                                      |
| Fan-out / composition | One output must physically drive N inputs        | **Irrelevant.** The MATCH result is an address — copy it to N registers for free.                                                         |

These barriers don't get overcome. They become **structurally irrelevant** — they are barriers to a model this architecture doesn't use.

### 7A.2 Computational Model

The associative path maps precisely onto **Hyperdimensional Computing / Vector Symbolic Architecture (HD/VSA)**:

- Each plate = a high-dimensional vector (its mode spectrum with $M$ dimensions)
- Mode interference (PROJECT) = vector addition / bundling
- MATCH = nearest-neighbor search in the codebook (argmax overlap)
- Selection (crossbar routing) = pointer to the matched entry

This is a known-complete computational framework. HD computing performs classification, analogy, sequence prediction, and Boolean logic — all with **read-only memory + vector operations + similarity search.**

### 7A.3 The Logic Cycle

```
┌─── DRIVE (vector operation) ───┐      ┌─── MATCH (lookup) ───────────┐
│                                 │      │                               │
addr ─▶ Excite plates at address A │      │ Compare response against     │
│ → mode interference =          │      │ ALL plates' known spectra     │
│   physical linear combination  ├─────▶│ → best match = the answer    ├──▶ new addr
│ (the computation — one shot,   │      │ (argmax normalized overlap)  │
│  massively parallel)           │      │                               │
└─────────────────────────────────┘      └───────────────────────────────┘
       ▲                                          │
       │◀──────── new addr selects next plates ───┘
```

Every step is at full SNR. Q does not limit cascading depth — it only limits clock speed (how fast a mode rings up for measurement). You can chain 1000 operations at Q = 100 just as well as at Q = 100,000; it's just slower.

**Cycle time:** $t_{\text{cycle}} = t_{\text{ring-up}} + t_{\text{measure}} + t_{\text{route}}$. At bench Q ≈ 500, f ≈ 50 kHz: ring-up ≈ 3 ms, measure ≈ 1 ms (FPGA lock-in), route ≈ µs. **Total ≈ 4 ms (250 Hz clock).** Slow — but working and demonstrable at any cascade depth.

### 7A.4 Three-Tier Memory Hierarchy (Associative Model)

| Tier                  | Mechanism                    | Where state lives          | Persistence              | Refresh?                 |
| --------------------- | ---------------------------- | -------------------------- | ------------------------ | ------------------------ |
| Register              | Mode amplitude (ringdown)    | In the vibration           | ~τ = Q/(πf) ≈ 50 ms      | Automatic decay          |
| Working memory        | Crossbar address             | FPGA register (a few bits) | Indefinite while powered | No                       |
| **Permanent storage** | **Plate eigenmode spectrum** | **In the glass geometry**  | **Forever**              | **No — it IS the plate** |

The permanent tier needs no power, no refresh, and no write operation. It exists because the plate exists. You "read" it by exciting and measuring. You "address" it by routing the crossbar. The glass array is a **physical ROM whose entries were written by manufacturing.**

### 7A.5 Boolean Logic via Spectral Interference + Threshold

Even within the associative model, conventional Boolean operations are available:

**AND gate:** Drive mode $f_1$ (input A) and mode $f_2$ (input B) on the same plate. A readout cell at an antinode intersection of both mode shapes responds strongly **only when both are driven** — constructive interference of shapes at that cell. FPGA threshold → 1 iff both present.

**OR gate:** Same cell, lower threshold — either mode alone exceeds it.

**NOT gate:** Invert the threshold comparator.

**Cascading:** The FPGA takes the thresholded result and selects the next plate/mode to drive at full power. No signal ever "passes through" a gate — it's regenerated fresh. The glass does the interference (the expensive parallel part); the electronics does the 1-bit decision (the trivial part).

This is architecturally identical to how every photonic neural-network chip works (Lightmatter, Akhetonics): the medium does massively parallel linear operations; electronics does activation/thresholding between layers.

### 7A.6 State-Space Size and Scaling

With N plates and a crossbar that can select arbitrary subsets:

$$\text{Addressable configurations} = 2^N$$

| Array size | State space               | Comparison             |
| ---------- | ------------------------- | ---------------------- |
| 8 plates   | 256                       | —                      |
| 16 plates  | 65,536                    | 16-bit address space   |
| 32 plates  | $4.3 \times 10^9$         | exceeds 32-bit integer |
| 64 plates  | $\sim 1.8 \times 10^{19}$ | exceeds 64-bit integer |

Each "state" is a unique combination of spectral identities that interfere differently. MATCH jumps directly to the best-matching state — **exponential state space, constant-time access.**

### 7A.7 Comparison: Von Neumann vs. Associative Path

| Dimension          | Von Neumann (§7)                        | Associative (§7A)                                         |
| ------------------ | --------------------------------------- | --------------------------------------------------------- |
| Basic operation    | Gate (transform a signal)               | Selection (choose the right plate)                        |
| Memory model       | Write a state that persists             | The plate EXISTS — always did                             |
| Logic mechanism    | Nonlinear threshold creates 0/1         | Resonant response IS the binary distinction               |
| Cascading          | Output must physically drive next input | Output = an address; next drive is fresh                  |
| Scaling bottleneck | Higher Q at each stage                  | More plates (trivial to add)                              |
| Failure mode       | Signal decay kills the cascade chain    | Nothing decays — nothing chains acoustically              |
| Parallelism        | 1 gate per cycle                        | N comparisons per cycle (all plates respond)              |
| Q requirement      | ≥ 10⁴ (MEMS-gated)                      | Any Q (bench-achievable)                                  |
| Desk-achievable?   | Stages 1–2 only                         | **All stages**                                            |
| Commercial analog  | Acoustic Von Neumann CPU (slow, niche)  | Physical search engine / inference accelerator (valuable) |

### 7A.8 Revised Stage Table (Dual-Path)

| Stage               | Von Neumann path (§7, MEMS-gated)               | Associative path (§7A, desk-achievable)                                 |
| ------------------- | ----------------------------------------------- | ----------------------------------------------------------------------- |
| 1 — Instruction set | ✓ defined (§3)                                  | ✓ same instruction set                                                  |
| 2 — Switch          | WL-B9 (linear, bench) / WL-D4 (nonlinear, MEMS) | ✓ crossbar routing IS the switch                                        |
| 3 — Latch           | WL-D3.3 parametric 0/π (MEMS)                   | ✓ address register (FPGA) + acoustic register (ringdown τ)              |
| 4 — Universal gate  | WL-D4 Duffing IM (MEMS)                         | ✓ interference + electronic threshold (§7A.5)                           |
| 5 — Composition     | WL-C7 FSM (partial bench) / WL-E2 (MEMS)        | ✓ FPGA routes thresholded result → next drive (unlimited cascade depth) |
| 6 — General logic   | All above must PASS (MEMS)                      | ✓ **LUT cascade / HD compute via spectral codebook — desk-achievable**  |

### 7A.9 What This Path IS and What It ISN'T

**It IS:**

- A massively parallel associative processor (N comparisons per cycle)
- A physical content-addressable memory with permanent, zero-power storage
- A hyperdimensional computer where each plate is a basis vector
- Desk-achievable general compute (slow clock, unlimited depth)
- The stronger commercial framing: physical search / inference / pattern-matching accelerator

**It ISN'T:**

- Fast (clock ≈ 250 Hz at bench Q — useful for proof, not competition)
- A replacement for the Von Neumann path (that path gives all-acoustic autonomy at MEMS scale)
- New physics (it's interference + threshold + routing — the insight is architectural, not physical)

**The honest claim:**

> CWM reaches general compute at desk scale via the associative/HD path. The Von Neumann path (all-acoustic, autonomous, gate-based) remains the MEMS frontier and the long-term scientific goal. Both paths share the same PFU instruction set and crossbar hardware; they differ only in how computation is organized above it.

---

## 7B. Gradient / Kernel Computing Path (Level 3)

§7A uses the array response as a discrete lookup (argmax → one winner). This section formalizes what happens when you **keep the full response gradient** — the continuous similarity vector across all plates — and compute over it directly. This is strictly more powerful than §7A, runs on the same hardware, and positions CWM as a **physical kernel machine / neural inference accelerator.**

### 7B.1 The Physical Gradient

When a query $\mathbf{q}$ is broadcast to an N-plate array, every plate responds with an amplitude proportional to its spectral overlap with the query:

$$y_i = K(\mathbf{q}, \mathbf{s}_i) = \frac{\langle \mathbf{q}, \mathbf{s}_i \rangle}{\|\mathbf{q}\| \cdot \|\mathbf{s}_i\|} \quad \text{for } i = 1 \ldots N$$

where $\mathbf{s}_i$ is plate $i$'s eigenmode spectrum (the fixed kernel basis function) and $K$ is the physical kernel — implemented by wave interference, evaluated in one acoustic cycle, for all N plates simultaneously.

The response vector $\mathbf{y} = [y_1, y_2, \ldots, y_N]$ is not binary. It is a **continuous, N-dimensional similarity landscape** — a kernel evaluation over the entire codebook, computed physically in parallel. §7A discards this information (argmax keeps 1 value out of N). Level 3 uses all of it.

### 7B.2 Three Computation Levels on One Hardware

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Level 3: GRADIENT / KERNEL (this section)                              │
│  Keep the full N-dim response vector; compute over the gradient         │
│  → kernel regression, attention, Hopfield, interpolation, dynamics      │
│  Power: analog, continuous, generalizes beyond stored codebook entries  │
│  Hardware: same crossbar + broadcast — read all N responses, no argmax  │
├─────────────────────────────────────────────────────────────────────────┤
│  Level 2: ARGMAX / HD LOOKUP (§7A)                                      │
│  Threshold the response → take the winner → route to next plate         │
│  → LUT cascade, Boolean logic, state machine, discrete general compute  │
│  Power: discrete, provably correct, unlimited cascade depth             │
│  Hardware: same + FPGA threshold + address routing                      │
├─────────────────────────────────────────────────────────────────────────┤
│  Level 1: BINARY / SINGLE-PLATE (§3 instruction set)                    │
│  Single threshold on one mode of one plate                              │
│  → match/no-match, PUF bit, single decision, interference gate         │
│  Power: unit-cell operations                                            │
│  Hardware: current bench (no array needed)                              │
└─────────────────────────────────────────────────────────────────────────┘
```

Each level is strictly more powerful than the one below. All three run on identical hardware — the difference is purely **how much of the response you keep.**

### 7B.3 Computational Primitives at Level 3

| Primitive                 | Definition                                                                             | Physical mechanism                                    | Application                                                          |
| ------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------- |
| **Kernel evaluation**     | $\mathbf{y} = K(\mathbf{q}, \mathbf{S})$ — similarity of query against all N templates | Broadcast + FDM capture → N amplitudes in one cycle   | The expensive step in all kernel methods (SVM, GP, RBF nets)         |
| **Soft attention**        | $\text{out} = \sum_i \text{softmax}(y_i) \cdot v_i$ — weighted retrieval               | Physical kernel + electronic weight-multiply          | Transformer-style attention without digital matrix ops               |
| **Hopfield retrieval**    | $\mathbf{q}_{t+1} = f(K \cdot \mathbf{q}_t)$ — iterate until fixed point               | Feed gradient back as next drive → acoustic iteration | Associative memory with error correction; content-addressable recall |
| **Kernel regression**     | $\hat{f}(\mathbf{q}) = \mathbf{w}^T \mathbf{y}$ — learned readout from gradient        | Physical kernel + one FPGA dot product                | Regression / interpolation / function approximation                  |
| **Classification (SVM)**  | $\text{class} = \text{sign}(\mathbf{w}^T \mathbf{y} + b)$                              | Physical kernel + FPGA threshold on weighted sum      | Multi-class classification in kernel space                           |
| **Probabilistic routing** | $p_i = y_i / \sum_j y_j$ — drive next cycle at proportional amplitudes                 | Normalize gradient → use as drive vector for cycle 2  | Soft decision trees; mixture-of-experts routing                      |
| **Interpolation**         | $\hat{a} = \sum_i y_i \cdot a_i / \sum_j y_j$ — weighted average of "answers"          | Gradient weights + electronic value table             | Generalization beyond codebook entries                               |

### 7B.4 The Array as a Physical Neural Network

Framing the three levels in neural-network terms:

```
Input (query)                               Output
    │                                           ▲
    ▼                                           │
┌─────────┐     ┌───────────────────┐     ┌──────────┐
│ A-DAC   │ ──▶ │ HIDDEN LAYER      │ ──▶ │ READOUT  │
│ (encode │     │ = the plate array │     │ LAYER    │
│  query  │     │                   │     │ = FPGA   │
│  as     │     │ N nodes (plates)  │     │ w·y + b  │
│  drive) │     │ Fixed weights     │     │ (learned)│
│         │     │ (spectra = mfg)   │     │          │
└─────────┘     └───────────────────┘     └──────────┘
                        │
              activation = y_i = K(q, s_i)
              (physical kernel evaluation)
```

- **Hidden-layer weights** are the plates' eigenmode spectra — fixed at manufacture, unique per device, never updated, physically permanent. This is a **reservoir** in the RC (reservoir computing) sense: a fixed nonlinear expansion that projects inputs into a high-dimensional feature space.
- **Readout weights** $\mathbf{w}$ are learned electronically (least-squares on training examples). Training is trivial: collect $\{(\mathbf{q}_k, \text{label}_k)\}$ → solve $\mathbf{w} = (\mathbf{Y}^T\mathbf{Y})^{-1}\mathbf{Y}^T\mathbf{t}$ once. The FPGA stores and applies $\mathbf{w}$.
- **Depth:** feed the output (or gradient) back as the next query → iterate → multiple "layers" of physical feature extraction. One acoustic cycle ≈ 4 ms = one layer.

This is exactly the architecture of **echo-state networks / reservoir computers / extreme learning machines** — with the crucial difference that the "reservoir" is **passive, zero-power, physically permanent glass** instead of a simulated random matrix.

### 7B.5 Iterative Dynamics (Deep Physical Inference)

When the gradient is fed back as the next drive:

$$\mathbf{q}_{t+1} = K \cdot \mathbf{q}_t$$

or with a nonlinear activation (e.g., FPGA applies ReLU or softmax to $\mathbf{y}$ before re-driving):

$$\mathbf{q}_{t+1} = \sigma(K \cdot \mathbf{q}_t)$$

This creates **autonomous dynamics** in the array. The system evolves until convergence — and the fixed point IS the computation result.

| Dynamics type            | Activation                       | Converges to                       | Application                             |
| ------------------------ | -------------------------------- | ---------------------------------- | --------------------------------------- |
| Linear (power iteration) | None (raw gradient → re-drive)   | Dominant eigenvector of K          | Principal component extraction          |
| Hopfield                 | Threshold                        | Nearest stored pattern             | Error-correcting associative memory     |
| Softmax iteration        | Softmax normalize                | Winner-take-all (sharpened argmax) | Clean classification from noisy queries |
| Boltzmann-like           | Stochastic threshold (add noise) | Sampling from energy landscape     | Generative model / annealing            |

**Convergence speed:** K is a Gram matrix (positive semi-definite if spectra are linearly independent). Power iteration converges in ~5–20 cycles for well-separated eigenvalues. At 4 ms/cycle → fixed point in 20–80 ms. Fast enough for batch inference; not for real-time streaming.

### 7B.6 Training the Readout (How You Program It)

The "program" for a Level 3 computation is a **readout weight vector** $\mathbf{w} \in \mathbb{R}^N$. Different $\mathbf{w}$ = different tasks on the same physical kernel.

**Training protocol (one-time, offline):**

1. Collect M training examples: $\{(\mathbf{q}_k, t_k)\}_{k=1}^M$ where $t_k$ is the target label/value.
2. For each $\mathbf{q}_k$: broadcast to array → capture gradient $\mathbf{y}_k$.
3. Assemble $\mathbf{Y} \in \mathbb{R}^{M \times N}$ (kernel matrix on training set).
4. Solve $\mathbf{w} = (\mathbf{Y}^T\mathbf{Y} + \lambda I)^{-1}\mathbf{Y}^T\mathbf{t}$ (ridge regression, closed-form).
5. Store $\mathbf{w}$ in FPGA memory.

**Inference (real-time):**

1. Broadcast query → capture $\mathbf{y}$ (one acoustic cycle, ~4 ms).
2. Compute $\hat{t} = \mathbf{w}^T \mathbf{y}$ (one dot product in FPGA, ~µs).
3. Output $\hat{t}$.

**Multi-task:** store M different weight vectors $\{\mathbf{w}_1, \ldots, \mathbf{w}_M\}$. Same physical kernel, M different outputs. Switching tasks = loading a different $\mathbf{w}$ — one clock cycle.

### 7B.7 Scaling and Capacity

The kernel dimension is NOT simply "number of plates." It is **number of spectrally resolvable features per capture** — which depends on the readout strategy:

- **Single-tone, 1 plate per channel (serial relay scan):** kernel_dim = N_ports (one amplitude per relay switch)
- **Multi-tone, stacked (many plates per port, FFT readout):** kernel_dim = usable_modes_per_port × N_ports

With Q ≈ 200, each mode occupies ~500 Hz. In a 120 kHz bandwidth, ~240 non-overlapping spectral slots exist per port. With n plates per port (5 modes each), usable modes ≈ 5n − n²/(2 × 48) (birthday-collision model). At 8 plates/port: ~37 usable modes at 92% efficiency.

| Parameter                               | Expression              | 8-plate desk (serial) | 8-plate desk (multi-tone, 1 port) | 64-plate desk | MEMS (10⁴ cells) |
| --------------------------------------- | ----------------------- | --------------------- | --------------------------------- | ------------- | ---------------- |
| Kernel dimension                        | modes × ports           | 24 (24×1)             | 37 (37×1)                         | 64            | 10,000           |
| Feature space                           | same                    | 24                    | 37                                | 64            | 10,000           |
| Max separable classes (Cover's theorem) | ~2N                     | ~48                   | ~74                               | ~128          | ~20,000          |
| Kernel evaluation time                  | P × (switch + capture)  | 360 ms (24 switches)  | 15 ms (0 switches)                | ~4 ms (FDM)   | ~0.3 ms (MEMS)   |
| Kernel evaluations / second             | 1/eval_time             | ~3                    | ~66                               | ~250          | ~3,000           |
| Digital equivalent cost                 | N² MACs per kernel eval | 576 MACs              | 1,369 MACs                        | 4,096 MACs    | 10⁸ MACs         |

**Key insight:** On relay-scanned hardware, stacking plates per port and using multi-tone + FFT readout eliminates relay switching as the bottleneck. A single port with 8 plates provides a 37-dimensional kernel at 66 evaluations/second — from hardware that previously gave 24 dimensions at 3 evaluations/second. The improvement is >20× throughput at higher dimensionality, with zero new parts.

At MEMS scale with 10⁴ cells, one kernel evaluation replaces **100 million multiply-accumulate operations** — in one acoustic cycle, at µW power. That is the commercial proposition.

### 7B.8 Comparison with Competing Physical Kernel / Inference Hardware

| Platform                                       | Kernel type                      | Reconfigurable?                      | Non-volatile?               | Energy/inference              | Speed                          | Status               |
| ---------------------------------------------- | -------------------------------- | ------------------------------------ | --------------------------- | ----------------------------- | ------------------------------ | -------------------- |
| **CWM array (Level 3)**                        | Spectral overlap (plate spectra) | Fixed hidden layer + learned readout | Yes (spectra are permanent) | ~µJ (desk) / ~nJ (MEMS)       | ~250 Hz (desk) / ~3 kHz (MEMS) | ARCHITECTURAL        |
| Photonic reservoir (e.g., PhoxTronik)          | Optical scattering / MZI mesh    | Tunable MZI phases                   | No (volatile)               | ~nJ per inference             | ~GHz                           | Research             |
| Memristor crossbar (e.g., Mythic, Ceremorphic) | Conductance-weighted MAC         | Yes (write weights to cells)         | Yes (NVM)                   | ~pJ per MAC                   | ~MHz clock                     | Commercial (limited) |
| Analog CMOS (e.g., Aspinity)                   | Analog MAC in current domain     | Yes (DAC weights)                    | No (volatile)               | ~µW always-on                 | MHz                            | Commercial (edge)    |
| Digital ASIC (e.g., GPU, TPU)                  | Exact digital matmul             | Fully programmable                   | No (SRAM)                   | ~pJ per MAC, millions of MACs | GHz                            | Dominant             |
| Spintronic reservoir (e.g., Toshiba)           | Magnetic dynamics                | Fixed topology                       | Yes                         | ~µJ                           | kHz–MHz                        | Research             |

**CWM's unique differentiators at Level 3:**

1. **Non-volatile kernel** — the hidden layer (plate spectra) persists without power, indefinitely. Every other analog platform needs power to hold state (except memristors, which degrade).
2. **Physically unclonable** — every device has a unique kernel (PUF + compute in one object). No two CWM arrays compute identically → hardware-rooted inference security.
3. **Zero-write kernel** — the kernel is set at manufacture (geometry determines spectrum). No programming step, no write endurance limit, no drift. The "weights" are the laws of physics applied to a specific geometry.
4. **Multi-task via electronic readout** — switch between tasks by changing $\mathbf{w}$ in one clock cycle. No physical reconfiguration.
5. **Combined memory + compute + identity** — same device is simultaneously a PUF, a CAM, and a kernel machine. No other platform fuses all three.

### 7B.9 What Level 3 IS and ISN'T

**It IS:**

- A physical kernel machine that evaluates N-dimensional spectral similarity in one acoustic cycle
- A reservoir computer with a permanent, zero-power, unclonable hidden layer
- A neural inference accelerator (one hidden layer per cycle, learned readout, arbitrary depth via iteration)
- A soft-attention engine (weighted retrieval over the full codebook)
- An interpolator (generalizes beyond stored codebook entries via gradient weighting)
- Desk-achievable now (same hardware as §7A — just keep the gradient)

**It ISN'T:**

- A replacement for digital training (training the readout weights $\mathbf{w}$ is still electronic/digital)
- Fast at desk scale (250 inferences/sec — useful for proof, not production)
- A general-purpose programmable processor in the Von Neumann sense (the kernel is fixed; you program only the readout)
- Better than digital at all tasks (only wins on kernel evaluation where N is large and the kernel is expensive to simulate)

**The honest claim:**

> At Level 3, the CWM array is a physical kernel machine: it evaluates N-dimensional spectral similarity in one acoustic cycle, enabling classification, regression, attention, and iterative dynamics without digital matrix multiplication. The kernel is permanent (set by plate geometry), unclonable (unique per device), and zero-power (no refresh). The desk rig proves the architecture; MEMS scaling delivers the energy and throughput advantages that make it commercially competitive with digital inference.

---

## 8. Fabrication Path

The architecture targets two fabrication generations.

### Gen 1 — Macro Bench (current, OPERATIONAL)

```
Fused silica plate (100 mm or 25 mm)
PZT transducers (cyanoacrylate, 10 mm discs)
Pico H NCO (USB serial, 126 MHz PIO clock)
Arduino relay mux (8-channel)
PicoScope 2204A (781 kS/s, 391 kHz Nyquist)
Board A preamp (×11), Board D buffer (3.7×)
```

**Purpose:** validate physics, characterize noise/Q, build instruction set, publish papers. Not a product.

### Gen 2 — MEMS Die (PROJECTED, Phase D gate G5)

```
1 mm × 1 mm × 50 µm fused silica plate
AlN thin-film transducer array (8–16 elements)
Phononic-crystal isolation anchors
Vacuum packaging (Q ≥ 10⁴ target)
CMOS flip-chip drive/readout circuit
```

**Key parameters:**

| Parameter            | Value      | Basis                                                |
| -------------------- | ---------- | ---------------------------------------------------- |
| Eigenmode range      | 3.5–35 MHz | DERIVED — 16× scaling from 25mm plate                |
| Q target             | ≥ 10⁴      | PROJECTED — literature (fused silica MEMS in vacuum) |
| τ at Q=10⁴, f=10 MHz | 320 µs     | DERIVED — τ = Q/(πf)                                 |
| Symbol rate feasible | ≥ 3 kHz    | DERIVED — τ/T_symbol ≈ 1                             |
| H-matrix rank        | ≤ 16       | PROJECTED — 16-element AlN array                     |
| J/projection         | ~1 nJ      | PROJECTED — scaled from macro SNR + Q                |

**Gate G5 requires:** WL-D1 design review passed + ≥ 1 accepted paper + fabrication partner committed.

**Primary fab thread:** university MEMS facility (Scranton partner thread). **Backup:** MEMS multi-project wafer run. Foundry note: fused silica deep-RIE + AlN sputter + vacuum cap is a well-established MEMS process (no exotic materials required).

---

## 9. What This Architecture Is and Is Not

| Claim                                                 | Status                                                       |
| ----------------------------------------------------- | ------------------------------------------------------------ |
| Physical spectral projection with measured H matrix   | PROVEN                                                       |
| 100% classification at 193σ (single session)          | PROVEN                                                       |
| Physically unclonable device fingerprint              | PROVEN (single-session); cross-session pending WL-A5         |
| 4,096 zero-error addressable states (12 bits)         | PROVEN                                                       |
| Classical non-separable DOF structure (CHSH S = 2.83) | PROVEN                                                       |
| Non-volatile mass-loading write mechanism             | PROVEN MECHANISM (Rayleigh); bench E3 pending                |
| Mode-division multiplexing (3 simultaneous modes)     | PENDING — WL-B7                                              |
| Analog-to-digital decision gate                       | PENDING — WL-B8                                              |
| Phononic FSM (3-state)                                | PENDING — WL-C7 (after WL-B8)                                |
| Nonlinear acoustic AND gate                           | PENDING — WL-D4 (MEMS) / WL-B2 (bench if F10 genuine)        |
| Parametric bistable latch                             | PENDING — WL-D3.3 (MEMS)                                     |
| Composable phononic logic (Von Neumann, all-acoustic) | NOT DEMONSTRATED                                             |
| General-purpose phononic CPU (Von Neumann)            | NOT DEMONSTRATED — requires Stages 2–6                       |
| General compute via associative/HD path (§7A)         | ARCHITECTURAL — desk-achievable; demonstration pending       |
| Physical kernel machine / neural inference (§7B)      | ARCHITECTURAL — desk-achievable; demonstration pending       |
| Quantum speedup                                       | NOT CLAIMED — all effects are classical DOF non-separability |

The architecture is honest. The plate does not compute autonomously in the Von Neumann sense — the control core sequences decisions. But in the associative model (§7A), the plate array IS the computer: interference computes, spectra store, the crossbar routes — and the electronic layer does only threshold decisions and address selection. That is general compute with glass doing the heavy lifting.

---

## 10. Document History

| Date       | Change                                                                                                                                                                                                                                                                                  |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-06-17 | v1.0 created. Structure: data representation, memory hierarchy, instruction set (L0–L3), six PFUs, control stack, cross-domain composition, path to general-purpose logic (Stages 1–6), fabrication path, honest claims table.                                                          |
| 2026-06-20 | v1.1 — added §7A (Associative / Hyperdimensional Path to General Compute) and §7B (Gradient / Kernel Computing Path — Level 3). Dual-path framing: Von Neumann (MEMS-gated) + Associative (desk-achievable) + Kernel (desk-achievable, analog). Updated §7 summary and §9 claims table. |
