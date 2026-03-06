---

## 7. MEMS Device Specification

### 7.1 Reference Design

The following table defines the baseline MEMS SEM device. Every parameter is either derived from the scaling analysis (Sections 5–6) or chosen to match established MEMS fabrication capabilities.

| Parameter        | Value                              | Rationale                                        |
| ---------------- | ---------------------------------- | ------------------------------------------------ |
| Material         | Borosilicate (Schott Borofloat 33) | Commercially available MEMS wafers               |
| Rod length       | 1 mm                               | Above DRAM crossover, within MEMS fab range      |
| Rod diameter     | 40 µm                              | Aspect ratio 25:1 (demonstrated in glass DRIE)   |
| Aspect ratio     | 25:1                               | Within current Bosch/Schott capability           |
| Tether width     | 2 µm                               | Standard lithographic feature size               |
| Tether thickness | 2 µm                               | Matched to width for symmetric cross-section     |
| Tether length    | 20 µm                              | 10× tether width for acoustic isolation          |
| Transducer       | AlN thin-film piezo (500 nm)       | In volume production for FBAR filters            |
| Vacuum level     | 0.1 Pa                             | Standard MEMS packaging (gyroscopes, oscillators) |
| Operating temp   | 25 ± 1 °C                          | Room temperature, modest stability requirement   |

### 7.2 Per-Rod Performance

| Parameter         | Value                             |
| ----------------- | --------------------------------- |
| Modes             | 9,380                             |
| SNR (fundamental) | 47 dB (1 mm)                      |
| Bits per mode     | 7.8 (1 mm) – 16.4 (macro)         |
| Bits per rod      | ~73,164 (conservative 7.8 b/mode) |
| Hopfield patterns | 1,294                             |
| Read time         | 3.6 µs                            |
| Write energy      | 16 fJ/bit                         |

The read time of 3.6 µs is set by the acoustic round-trip time: sound at 5,640 m/s traverses a 1 mm rod in ~0.18 µs, and resolving the full spectrum requires approximately 20 round-trips ($20 \times 0.18 = 3.6$ µs). This is comparable to Flash read latency (~25 µs) and far faster than the seconds-scale access time of archival storage.

### 7.3 Array Architecture

At 80 µm pitch (2× rod diameter) and 1.1 mm layer spacing (rod length + 100 µm clearance):

| Parameter          | Value                                       |
| ------------------ | ------------------------------------------- |
| Rods per cm²       | 15,625                                      |
| Layers per cm      | ~9                                          |
| Rods per cm³       | ~140,000                                    |
| **Total capacity** | **~120,000 bits/rod × 140,000 = 16.8 Gbit** |
| **Density**        | **95.5 Gbit/cm³**                           |

### 7.4 Energy Budget

| Operation       | Energy        | Notes               |
| --------------- | ------------- | -------------------- |
| Write (1 mode)  | 31.4 fJ       | $k_B T \times$ SNR  |
| Write (per bit) | 1.9 fJ        | 31.4 fJ / 16.4 b    |
| Write (per rod) | 16 fJ/bit avg | Including overhead   |
| Read (FFT)      | ~1 pJ/rod     | On-chip CMOS FFT     |
| Search (array)  | ~0.1 nJ       | Parallel excitation  |

---

## 8. Fabrication Pathway

Every step in the SEM fabrication process is borrowed from an existing MEMS production line. We emphasize this because it is the difference between "interesting physics demonstration" and "buildable device." No new materials, no new equipment, no new process chemistry.

### 8.1 Process Flow

**Step 1 — Glass wafer preparation.** Start with 200 mm Schott Borofloat 33 wafers (500 µm thick). These wafers are commercially available from Schott, Plan Optik, and others, and are already used in MEMS microfluidics, wafer-level packaging, and optical devices. The wafers are polished to optical flatness—important for subsequent lithography.

**Step 2 — Deep reactive ion etch (DRIE).** Etch the rod arrays into the glass wafer at 25:1 aspect ratio using SF₆/C₄F₈ chemistry (the Bosch process adapted for glass). This is the most geometrically demanding step: we need 40 µm wide, 1 mm deep trenches separating the rods, with 2 µm tether features connecting each rod to the frame. Glass DRIE at these dimensions has been demonstrated by Schott, Corning, and multiple MEMS foundries for microfluidic channels and through-glass vias. The 40 µm rod diameter and 2 µm tether dimensions are within current capability, though at the aggressive end—our risk assessment (Section 8.3) addresses this.

**Step 3 — Mass perturbation patterning.** Deposit and pattern thin-film metal dots (Au, ~50 nm thick) at lithographically defined positions on each rod. This is a standard lift-off process: spin photoresist, expose through a mask, develop, deposit gold by evaporation, strip the resist. Each dot's position and mass determine the rod's spectral fingerprint—this step is the "write" operation, performed once at fabrication. Different masks encode different data.

**Step 4 — AlN piezoelectric transducer.** Sputter 500 nm of aluminium nitride (AlN) on each rod's end face, patterned with top and bottom electrodes. AlN thin-film piezoelectric transduction is in volume production for smartphone bulk acoustic wave (BAW/FBAR) filters—more than 10 billion units shipped as of 2024 [14, 15]. The process is mature, the supply chain is established, and the performance specifications are well-characterized.

**Step 5 — Vacuum packaging.** Seal the rod arrays in a wafer-level vacuum package at 0.1 Pa using glass frit bonding or Au-Sn eutectic bonding. This is the same packaging technology used in MEMS oscillators (SiTime—shipped >2 billion units), MEMS gyroscopes (Bosch, STMicro), and MEMS accelerometers. Getter materials (typically Ti or Zr thin films) inside the package absorb residual outgassing to maintain vacuum over the device lifetime.

**Step 6 — CMOS integration.** Flip-chip bond the vacuum-sealed glass array onto a CMOS readout die. The CMOS die contains per-rod amplifiers, an FFT engine, a pattern-matching correlator, and a digital interface (SPI or I²C). This is the same integration approach used in Bosch and STMicro MEMS accelerometers and Avago/Broadcom FBAR filters: the MEMS structure is fabricated on one wafer, the CMOS on another, and the two are bonded face-to-face.

<div class="sem-thumb">
<img src="figures/fig6_fabrication.svg" alt="Figure 6: Fabrication process flow"/>
<p><strong>Figure 6.</strong> Six-step fabrication process using established MEMS production techniques. The innovation is the architectural combination, not the fabrication.</p>
</div>

### 8.2 Bill of Materials (MEMS, at volume)

| Component                       | Estimated cost |
| ------------------------------- | -------------- |
| Glass wafer (200 mm)            | \$50           |
| DRIE processing                 | \$200/wafer    |
| AlN deposition                  | \$100/wafer    |
| Vacuum packaging                | \$150/wafer    |
| CMOS readout die                | \$5/die        |
| Assembly + test                 | \$3/die        |
| **Per die (10,000 dies/wafer)** | **~\$0.06**    |

At scale, a single SEM die costs less than a capacitor.

### 8.3 Risk Assessment

| Risk                              | Impact | Mitigation                                      | Residual |
| --------------------------------- | ------ | ----------------------------------------------- | -------- |
| DRIE aspect ratio < 25:1          | High   | Reduce to 15:1 (still viable)                   | Medium   |
| AlN piezo coupling too weak       | High   | Switch to PZT; thicker film                     | Low      |
| Vacuum degradation over time      | Medium | Getter materials (standard)                     | Low      |
| Mode coupling at high $n$         | Medium | Use only lower modes; accept reduced $n_{\max}$ | Low      |
| Thermal management in arrays      | Low    | On-chip TEC; duty cycling                       | Low      |
| Cross-talk between adjacent rods† | Medium | Isolation trenches; pitch > 3$d$                | Low      |

† Cross-talk is bounded by the acoustic impedance mismatch between rod and vacuum gap. At 0.1 Pa, the impedance ratio exceeds 10⁷:1.

<div class="sem-thumb">
<img src="figures/fig2_mems_cross_section.svg" alt="Figure 2: MEMS resonator cross-section"/>
<p><strong>Figure 2.</strong> MEMS resonator cross-section showing AlN piezo transducers, anchor tethers, vacuum cavity, and lithographic perturbation masses.</p>
</div>

---

## 9. Technology Comparison

### 9.1 Density, Speed, Energy

| Technology            | Density (Gbit/cm³) | Read time  | Write energy  | Endurance | Associative? |
| --------------------- | ------------------ | ---------- | ------------- | --------- | ------------ |
| SRAM                  | 0.5                | <1 ns      | ~1 fJ/bit     | Unlimited | No           |
| DRAM                  | 10                 | ~10 ns     | ~3 pJ/bit     | Unlimited | No           |
| NAND Flash            | 1,000              | ~25 µs     | ~10 pJ/bit    | 10³–10⁵   | No           |
| PCM                   | 64                 | ~100 ns    | ~10 pJ/bit    | 10⁸–10⁹   | No           |
| ReRAM                 | 100                | ~10 ns     | ~1 pJ/bit     | 10⁶–10¹²  | Partial†     |
| **SEM (1 mm)**        | **95.5**           | **3.6 µs** | **16 fJ/bit** | **>10¹⁵** | **Native**   |
| **SEM (0.5 mm SiO₂)** | **1,394**          | **3.6 µs** | **~8 fJ/bit** | **>10¹⁵** | **Native**   |

† ReRAM crossbar arrays can perform matrix-vector multiply, but require explicit weight programming and are limited to linear operations.

### 9.2 SEM's Unique Position

Every technology in the table above stores data as an electrical state and computes by moving that data to a separate processor. SEM does neither. It stores data as geometry (the perturbation pattern) and computes by physics (wave interference). This is not a marketing distinction—it has concrete engineering consequences:

- **Non-volatility without charge retention.** Flash and PCM lose data when charge leaks or crystals relax. SEM's perturbation pattern is a physical structure; it persists as long as the glass exists.
- **Endurance without wear.** Flash endurance is limited by oxide breakdown from repeated tunnelling. DRAM endurance is limited by capacitor dielectric fatigue. SEM's acoustic oscillation is elastic and reversible—the glass experiences stress levels billions of times below its fracture threshold.
- **Computation without data movement.** ReRAM computes in the crossbar, but you still have to program the weights. SEM's weights are the physics—they were set at fabrication and never need updating for the associative recall to work.

### 9.3 The Computation Advantage

The comparison table understates SEM's advantage for search workloads. Traditional architectures must read data, transfer it to a processor, and execute a comparison algorithm. For a 100,000-pattern nearest-neighbor search:

- **CPU**: ~10 ms (sequential scan)
- **GPU**: ~0.1 ms (parallel dot products)
- **SEM**: ~3.6 µs (single acoustic propagation cycle, all patterns in parallel)

SEM is 28× faster than a GPU and 2,800× faster than a CPU for this workload, at a fraction of the power.

### 9.4 What SEM Is Not

SEM is not a general-purpose replacement for SRAM, DRAM, or Flash. It is optimized for:

- Content-addressable memory (associative lookup)
- Pattern matching and classification
- Nearest-neighbor search
- Hopfield-type associative recall
- Applications where search latency and energy dominate the system budget

It is not suitable for random byte-addressable read/write (use DRAM), high-speed cache (use SRAM), or applications requiring >10⁸ write cycles to the same physical location (perturbation patterns are fixed at fabrication, as in mask ROM).

### 9.5 Disruption Scenarios

We identify five scenarios where SEM's unique property combination creates strategic advantage:

1. **Associative search at the edge.** A 1 cm³ SEM module performs 280,000 associative lookups per second at <5 W. This enables real-time pattern matching in drones, satellites, and IoT devices where GPU co-processors are too heavy, hot, or expensive.

2. **Radiation-hard memory for space.** Glass resonators are intrinsically immune to single-event upsets (no charge states to flip). A 1 cm³ module stores 17 Gbit of radiation-hard memory—250× JWST's entire memory system—without shielding.

3. **Biometric authentication.** Voiceprint, fingerprint, and facial-feature matching are nearest-neighbor problems. A SEM chip in a phone performs 1,294-template matching in 3.6 µs at ~100 µW—enabling always-on biometric security with negligible battery impact.

4. **Network intrusion detection.** Deep packet inspection at 100 Gbps requires matching packet signatures against thousands of threat patterns. SEM's parallel associative recall handles this natively; TCAM solutions cost 50–100× more per lookup.

5. **DNA sequence matching.** Short-read alignment is a massive nearest-neighbor search. A SEM array could perform Smith-Waterman-equivalent scoring at acoustic speed, potentially replacing GPU clusters in sequencing pipelines.
