## 6. Architecture Synthesis

### 6.1 Three Tracks, One Architecture

The preceding experiments were organized into three tracks for clarity of exposition, but they are not alternatives—they are layers. Each track operates at a different level of the system stack:

| Layer    | Track            | Mechanism                           | Cost to implement           | Rewrite speed          | Degrees of freedom           |
| -------- | ---------------- | ----------------------------------- | --------------------------- | ---------------------- | ---------------------------- |
| 3 (top)  | A — Firmware     | DSP projection, subsetting, masking | Zero (software)             | Instantaneous          | Continuous (float weights)   |
| 2 (mid)  | B — Binary sites | MEMS electrostatic latches          | Moderate (12–20 switches)   | $\sim 10\ \mu\text{s}$ | Discrete ($2^{N_s}$ states)  |
| 1 (base) | C — Shell        | Conformal writable coating          | High (thin-film deposition) | Material-dependent     | Continuous (thickness/phase) |

These layers compose naturally. A rod with a writable shell (Layer 1), binary perturbation sites (Layer 2), and firmware-defined readout masks (Layer 3) has _multiplicative_ configurability:

$$
\text{Total configurations} = N_\text{shell} \times 2^{N_s} \times N_\text{firmware}
$$

where $N_\text{shell}$ is the number of distinguishable shell states (continuous, but quantized by readout noise), $2^{N_s}$ is the binary-site configuration count, and $N_\text{firmware}$ is the number of firmware-selectable virtual devices. Even conservatively: $10 \times 2^{12} \times 4 = 163{,}840$ distinct rod configurations from a single physical device.

### 6.2 The Separation Principle

A key architectural insight emerges from these results: **the resonator material and the write mechanism are separable**.

In conventional memory (DRAM, flash, MRAM), the storage medium and the write mechanism are the same material—the ferroelectric, the floating gate, the magnetic tunnel junction. The material's write properties (coercive field, endurance, retention) are inextricable from its read properties (polarization, threshold voltage, tunnel magnetoresistance).

In the SEM architecture, the glass rod is the _read medium_ (its eigenmodes encode information), but it need not be the _write medium_. Writing can happen:

- **Externally** (firmware): no physical change to the rod at all.
- **At the surface** (binary sites): reversible mechanical contacts that do not alter the bulk glass.
- **In a shell** (writable coating): a distinct material layer with its own physics, optimized independently for write properties.

This separation has a profound practical consequence: the glass rod can be optimized purely for Q (material purity, surface finish, anchor isolation) without any compromises for write/erase cycling. The write mechanism is a separate design problem with separate materials constraints.

### 6.3 Combined Capability Table

| Hypothesis | Track | Metric                           | Value  | Practical meaning                                      |
| ---------- | ----- | -------------------------------- | ------ | ------------------------------------------------------ |
| H7         | A     | Virtual devices per rod          | 4      | 4× storage density, zero hardware cost                 |
| H8         | A     | Independent sub-bands            | 4 of 4 | Each sub-band is a full Hopfield memory                |
| H9         | A     | Firmware masks working           | 4 of 7 | Amplitude-weighting masks succeed; zero-out masks fail |
| H10        | B     | Bits per rod (12 sites)          | 7.6    | $2^{7.6} \approx 193$ distinguishable states           |
| H11        | B     | Min sites for Hopfield           | 4      | Binary sites are associative-memory-compatible         |
| H12        | C     | Max actuators at $Q > 5\text{k}$ | 256    | Track B is Q-safe with enormous margin                 |
| H13        | C     | Max shell at $Q > 5\text{k}$     | 100 nm | 0.34% frequency shift ≈ multi-linewidth tuning         |

### 6.4 Recommended Development Path

Based on the combined results, we recommend a staged development path that follows the layer stack from top (lowest cost) to bottom (highest capability):

**Stage 0: Baseline (v16 architecture, no rewriting)**

- Fixed perturbation pattern, one Hopfield memory per rod.
- Capacity: $\sim 1{,}294$ patterns per rod [1, §10.4].
- This is the glass acoustic resonator described in v16.

**Stage 1: Firmware virtual rewriting**

- Add multi-projection partitioning to the ASIC readout pipeline.
- No hardware changes to the rod or MEMS die.
- Gain: 4× effective devices per rod (H7), independent sub-band memories (H8).
- Effective capacity: $\sim 5{,}176$ patterns per rod.
- Timeline: implementable in first ASIC tapeout.

**Stage 2: Binary perturbation sites**

- Add 12–20 electrostatic MEMS latches to the die, positioned near rod surface.
- Q penalty: $< 0.5\%$ (H12).
- Gain: $2^{12}$ = 4,096 physical configurations, each with its own spectral fingerprint (H10).
- Combined with Stage 1 firmware: $4{,}096 \times 4 = 16{,}384$ addressable states.
- Timeline: second-generation MEMS die.

**Stage 3: Writable shell**

- Deposit 50–100 nm Parylene C or magnetostrictive film before rod mounting.
- Q penalty: stays above 5,000 at $Q_d \geq 200$ (H13).
- Gain: continuous analog tuning of perturbation landscape.
- Combined with Stages 1–2: effectively unlimited reconfigurability.
- Timeline: requires thin-film process development; third-generation device.

Each stage is independently valuable and backward-compatible with the previous one. A Stage 1 device is a Stage 0 device with a firmware upgrade. A Stage 2 device is a Stage 1 device with added MEMS switches. A Stage 3 device is a Stage 2 device with a shell coating. No stage requires redesigning the previous one.

### 6.5 What "Rewritable" Means for SEM

It is worth being precise about what rewritability buys.

The original SEM architecture (v16) stores information in a fixed perturbation pattern. The perturbation is applied once during fabrication—metal dots, laser ablation marks, focused ion beam implants—and never changed. The device is a ROM: high density, high reliability, zero write energy, but static.

Rewritability transforms this ROM into a reconfigurable memory:

- **At the firmware level** (Track A), it becomes a content-addressable memory (CAM) that can be reprogrammed in software to "see" different subsets of the stored data. This is analogous to changing the SQL query on a database without changing the data.

- **At the binary-site level** (Track B), it becomes a PROM/EEPROM analogue: the physical state of the rod can be switched between $2^{N_s}$ configurations, each storing different data. Endurance depends on the MEMS switch lifetime ($> 10^9$ cycles for commercial RF MEMS [4]).

- **At the shell level** (Track C), it becomes a fully rewritable medium: the perturbation landscape can be continuously tuned, erased, and rewritten. Endurance depends on the shell material (Parylene: effectively unlimited; phase-change: $\sim 10^6$–$10^{12}$ cycles depending on material [5]).

The telescope has become an instrument.

---
