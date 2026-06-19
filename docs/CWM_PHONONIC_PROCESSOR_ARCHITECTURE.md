# CWM Phononic Processor Architecture

**Version:** 1.0 — June 2026
**Status:** Design document. Every claim labeled MEASURED / DERIVED / PROJECTED.
**Companion documents:** [ROADMAP_FULL_POTENTIAL.md](ROADMAP_FULL_POTENTIAL.md), [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md)

**Governing rule (inherited from roadmap):** Every claim bounded by (a) the wave equation and Rayleigh perturbation theory, (b) measured Q-factors and energy budgets, (c) at least one peer-reviewed precedent. Every tier of the architecture stack carries the same kill discipline as the experiment worklist.

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

This is a multi-year research program. The honest current claim is:

> **CWM is today a phononic functional-unit architecture (Stages 1–2 partially). It can reach general-purpose phononic logic (Stage 6) if nonlinear acoustic switching and parametric latching are demonstrated at MEMS scale.**

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
| Composable phononic logic                             | NOT DEMONSTRATED                                             |
| General-purpose phononic CPU                          | NOT DEMONSTRATED — requires Stages 2–6                       |
| Quantum speedup                                       | NOT CLAIMED — all effects are classical DOF non-separability |

The architecture is honest. The plate does not compute autonomously. The decoder and control core do. The plate provides a physical operator — the H matrix projection, the fingerprint, the Rayleigh encoder — that is physically analog, thermally stable, manufacturing-unique, low-energy, and writable. That is a real and valuable thing, even before Stage 2.

---

## 10. Document History

| Date       | Change                                                                                                                                                                                                                         |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 2026-06-17 | v1.0 created. Structure: data representation, memory hierarchy, instruction set (L0–L3), six PFUs, control stack, cross-domain composition, path to general-purpose logic (Stages 1–6), fabrication path, honest claims table. |
