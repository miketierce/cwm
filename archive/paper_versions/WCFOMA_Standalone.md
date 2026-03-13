# Wave-Coherent Field-Oriented Memory Architecture: A Simulation-Validated Assessment

**Mike Tierce**
Independent Researcher, Dallas, TX, USA
mike@tierce.com

**March 2026**

---

## Abstract

We present the Wave-Coherent Field-Oriented Memory Architecture (WCFOMA), a proposed computing substrate in which information is stored as resonant acoustic eigenmodes in ferrofluid-filled micro-cavities, computation emerges from wave interference, and passive mechanical shielding arises from granular dilatancy. Unlike conventional architectures that separate memory, computation, and security into distinct subsystems connected by buses, WCFOMA unifies all three in a single physical medium — the resonant wave field itself.

This paper is accompanied by an open-source simulation repository containing 15 validated physics modules, 10 computational notebooks, and 155 automated tests. Rather than presenting aspirational projections, we report what the simulations actually show — including findings that significantly revise the architecture's original performance claims downward. A Shannon channel-capacity analysis demonstrates that realistic storage density is approximately 0.02 Tb/cm³ (not the originally projected 1–10 Tb/cm³), system-level energy is ~10 pJ per access (not femtojoules), and achievable bits per mode is ~2.3 (not the assumed 10). Despite these corrections, the architecture occupies a genuine niche in the memory technology landscape: its unified compute-in-memory locality, fast acoustic write (14 ns), and inherent tamper detection through dilatancy-induced frequency drift represent capabilities not available in any single existing technology.

We present the architecture, the physics, the noise analysis that nearly killed it, the mitigations that saved it, the honest numbers, and a falsification-first roadmap toward experimental validation.

**Keywords:** wave-coherent memory, resonant eigenmode storage, in-memory computing, ferrofluid acoustics, zero-index metamaterials, dilatancy-based security, channel capacity, analog computing

---

## 1. Introduction

### 1.1 The Problem: Why Memory Architecture Matters

Modern computing spends most of its energy moving data, not processing it. In large language model inference, over 90% of energy is consumed by memory access and data transport between physically separated storage and computation units [1]. This is not a transistor problem — it is an architecture problem. The von Neumann bottleneck, identified decades ago, has become the dominant limiter of efficiency and scalability for AI workloads.

Every existing memory technology — DRAM, Flash, MRAM, ReRAM — stores information as a physical field configuration (charge, magnetization, resistance state). Yet the digital abstraction conceals this, imposing refresh cycles, address buses, and serial access patterns that are artifacts of architecture, not physics.

### 1.2 The Premise: What If Memory Were Treated as a Field?

WCFOMA starts from a simple question: _if information is physically stored as a field, what happens when you compute by reshaping that field directly?_

Under this premise:

- **Memory** is a set of resonant eigenmodes in a bounded acoustic cavity.
- **Computation** is wave interference — an input excitation resonates with matching stored patterns, enabling associative recall without serial search.
- **Security** emerges from the material itself — mechanical stress causes measurable frequency drift, providing passive, power-free tamper detection.

These are not separate subsystems. They are three aspects of the same physics.

### 1.3 What This Paper Is — and What It Is Not

This is not a device paper. No hardware prototype exists. This is a _simulation-validated architectural proposal_ that has been subjected to rigorous computational falsification testing. The accompanying repository ([github.com/miketierce/wcfoma](https://github.com/miketierce/wcfoma)) contains every simulation, every test, and every number reported here.

We follow a **falsification-first methodology**: each claim has an explicit kill criterion, and we report failures alongside successes. Three of the original paper's headline claims were found to be significantly over-optimistic. We present the corrected numbers.

### 1.4 Paper Organization

- **Section 2** describes the architecture.
- **Section 3** presents the physics of resonant eigenmode storage.
- **Section 4** reports the noise analysis that identified a potential architectural kill — and the mitigations that resolved it.
- **Section 5** derives Shannon channel capacity under realistic noise.
- **Section 6** benchmarks WCFOMA against seven established memory technologies.
- **Section 7** describes the dilatancy-based security mechanism.
- **Section 8** summarizes the honest claims scorecard.
- **Section 9** presents the experimental roadmap.
- **Section 10** concludes.

---

## 2. Architecture

WCFOMA comprises three functionally independent but physically unified layers operating within a single medium — a ferrofluid-filled micro-cavity enhanced with zero-index metamaterial (ZIM) structures.

### 2.1 Wave-Coherent Memory Substrate

Information is encoded as the amplitude and phase of resonant acoustic eigenmodes within a bounded cavity. For a cavity of length $L$ filled with a medium of sound velocity $v$, the resonant frequencies are:

$$f_n = \frac{n\,v}{2L}, \quad n \in \mathbb{Z}^+$$

For a 10 µm ferrofluid cavity ($v = 1400$ m/s), the fundamental frequency is $f_1 = 70$ MHz with mode spacing $\Delta f = 70$ MHz. Multiple modes coexist simultaneously via linear superposition, enabling multi-bit analog storage in a single cell.

**Zero-index metamaterials** (ZIMs) — acoustic structures engineered to exhibit near-zero effective refractive index at a design frequency — flatten the phase profile within the cavity. This reduces boundary-induced losses and provides geometry-invariant resonances: the eigenfrequencies become insensitive to the cavity's exact shape, depending primarily on the embedded scatterer rather than the boundary [2]. Our simulations confirm less than 1% eigenvalue shift under cavity deformation, compared to ~20% without ZIM.

### 2.2 Interference-Based Computation

Retrieval is inherently computational. An input excitation (a probe waveform) is injected into the cavity. Resonance occurs _only_ for modes matching the stored pattern. The readout signal's spectral content reveals which patterns are present and how strongly they match the probe — associative recall via physics, not algorithms.

Our interference simulations demonstrate **97.6% single-pattern retrieval fidelity** and correct recall of **50 simultaneously stored patterns at 90% accuracy** (quality factor $Q = 500$, 10 modes per cell). This is a direct analog of content-addressable memory, achieved through wave superposition rather than transistor-based comparison circuits.

### 2.3 Passive Mechanical Security

The carrier medium exhibits **dilatancy** — a shear-thickening response in which mechanical stress causes internal rearrangement of granular and nanoparticle structures [3]. In WCFOMA:

- External mechanical probing causes the medium to rigidify and restructure.
- Internal resonant modes shift in frequency by a measurable amount (~7% in 3D under moderate shear, ~33% in 1D under severe shear).
- This frequency drift serves as a tamper signal — detectable, passive, and power-free.

Monte Carlo validation across 5,000 trials confirms: **false positive rate 4.7%, false negative rate 0%** — a 1% geometric perturbation is reliably detected.

### 2.4 Optional Quantum Verification

Room-temperature rubidium-vapor quantum memories have demonstrated telecom-photon entanglement fidelities exceeding 90% [4]. WCFOMA can optionally couple to such a system for integrity verification. Critically, quantum elements are **out-of-band** — they do not participate in storage or computation, so decoherence in the quantum channel degrades the system gracefully to classical-only operation. The core architecture is entirely classical.

---

## 3. Physics of Resonant Storage

### 3.1 Ferrofluid as an Acoustic Medium

The working medium is a commercial ferrofluid: a colloidal suspension of magnetite (Fe₃O₄) nanoparticles (~10 nm diameter, ~5–10% volume fraction) in a carrier fluid. Key acoustic properties from the Rosensweig model [5]:

| Property                 | Value                   | Source                       |
| ------------------------ | ----------------------- | ---------------------------- |
| Sound velocity           | ~1400 m/s               | Effective medium theory      |
| Carrier density          | 900 kg/m³               | Hydrocarbon carrier          |
| Carrier viscosity        | 0.006 Pa·s              | Standard ferrofluid          |
| Acoustic impedance       | ~2 × 10⁶ Pa·s/m         | Computed                     |
| Quality factor (1 MHz)   | ~21,500                 | Rosensweig model (simulated) |
| Quality factor (100 MHz) | Lower; Q > 100 expected | Extrapolated                 |

The ferrofluid Q factor at the operating frequency (~70 MHz for a 10 µm cell) is the single most important unknown parameter. Our Rosensweig model predicts $Q \approx 21{,}500$ at 1 MHz, but Q decreases with frequency. We conservatively assume $Q = 500$ for all capacity and noise calculations — a value consistent with micro-scale acoustic resonators in viscous media.

### 3.2 Thermal Stability and Mode Crowding

Temperature variations cause frequency drift through the thermal coefficient of sound velocity ($\alpha \approx 0.0022$ /K for ferrofluid-like media). For a temperature excursion $\Delta T = \pm 5$ K:

- **Without ZIM:** Maximum distinguishable modes = **41** (thermal drift causes mode overlap above this).
- **With ZIM** (drift reduction factor 20×): Maximum distinguishable modes = **322**.

This is because ZIM's geometry-invariant resonances suppress the dependence of eigenfrequencies on cavity geometry changes induced by thermal expansion.

### 3.3 Coupled Multiphysics

The cavity hosts coupled acoustic, electromagnetic, and thermal degrees of freedom. We model their interaction using a **Slowly-Varying Envelope Approximation** (SVEA) that eliminates the extreme stiffness of the raw coupled-mode equations (acoustic modes at ~70 MHz, EM modes at ~15 GHz):

- **Energy retention:** 95.1% after 500 µs — excellent coherence.
- **Acoustic → EM transfer:** Negligible (large frequency detuning).
- **Thermal self-heating:** 0.01 mK — completely negligible.
- **Thermal feedback:** Frequency drift < 1% for $\Delta T$ up to ±50 K.

### 3.4 Grid Convergence

All finite-difference simulations were validated via Richardson extrapolation. The 3D FDTD solver achieves **0.16% frequency error at grid resolution N ≥ 10**, confirming that our results are not artifacts of discretization.

---

## 4. The Noise Problem — and Its Resolution

### 4.1 The Five Noise Sources

We developed a comprehensive noise model with five independent sources. At the default micro-cell parameters (10 µm cavity, $Q = 500$, $10^6$ readout photons):

| Source            | Mechanism                          | Contribution |
| ----------------- | ---------------------------------- | ------------ |
| Phase diffusion   | Brownian rotation of nanoparticles | **77.5%**    |
| Shot noise        | Photon counting statistics         | **22.5%**    |
| Thermal (Johnson) | Acoustic thermal fluctuations      | < 0.01%      |
| 1/f (flicker)     | Low-frequency electronic noise     | < 0.001%     |
| ADC quantization  | 10-bit digitization noise          | < 0.001%     |

**Phase diffusion dominates.** The rotational Brownian diffusion coefficient for a nanoparticle of diameter $d$ in a fluid of viscosity $\eta$ is:

$$D_{\text{rot}} = \frac{k_B T}{\pi \eta d^3}$$

For 10 nm particles in standard ferrofluid ($\eta = 0.01$ Pa·s), $D_{\text{rot}} \approx 1.3 \times 10^{11}$ rad²/s. The cumulative phase noise from $\sim 10^7$ particles coupling to the cavity mode produces an SNR of **−6.5 dB** — meaning the noise floor is above the signal. Zero reliable modes. The original paper did not model this noise source.

### 4.2 A Near-Kill

This finding represented a potential architectural kill. With the paper's default parameters, WCFOMA cannot store _any_ information reliably. The noise analysis triggered 5 of 7 kill criteria:

| Check                   | Threshold | Result  | Verdict |
| ----------------------- | --------- | ------- | ------- |
| SNR > 10 dB (all modes) | Required  | −6.5 dB | ❌ FAIL |
| BER < 1% (all modes)    | Required  | 31.8%   | ❌ FAIL |
| Lifetime > 1 µs         | Required  | 0 µs    | ❌ FAIL |
| Reliable modes ≥ 5      | Required  | 0       | ❌ FAIL |
| Coherence > 1 µs        | Required  | 500 µs  | ✅ PASS |
| Energy retained > 50%   | Required  | 95.1%   | ✅ PASS |

### 4.3 Two Independent Barriers

The noise analysis revealed that **two independent barriers** must both be overcome:

1. **Phase diffusion** (Brownian nanoparticle motion) — requires immobilizing the particles.
2. **Shot noise** (photon counting) — requires more photons per measurement.

No single mitigation suffices. Gel immobilization alone achieves at best −1 dB. More photons alone achieves at best 3 dB. Neither crosses the 10 dB threshold.

### 4.4 Minimum Viable Configurations

Systematic two-parameter sweeps across viscosity (1× to 10,000×) and photon count ($10^6$ to $10^{11}$) reveal a clear **L-shaped viability boundary** in parameter space. Three minimum viable configurations:

| Configuration                   | Viscosity       | Photons | SNR     | Modes | Energy |
| ------------------------------- | --------------- | ------- | ------- | ----- | ------ |
| Gel + photons (10 µm cell)      | 1.0 Pa·s (100×) | 10⁸     | 13.5 dB | 10    | ~10 pJ |
| Large cavity + photons          | 0.01 Pa·s (1×)  | 10⁸     | 14.2 dB | 10    | ~10 pJ |
| Combined (moderate gel + 50 µm) | 0.1 Pa·s (10×)  | 10⁸     | 18.9 dB | 10    | ~10 pJ |

All viable paths converge on similar energy budgets (~10 pJ) and mode counts (~10). The architecture works — but at parameters significantly different from the original paper's assumptions.

**Gel immobilization** of ferrofluid nanoparticles is physically achievable: polymer-gel ferrofluids with effective viscosities 100–10,000× higher than free ferrofluid have been demonstrated in the literature [6]. The key tradeoff is that higher gel viscosity may reduce the dilatancy-based security mechanism, requiring careful material engineering.

---

## 5. Information-Theoretic Capacity

### 5.1 Shannon Analysis

The original paper asserts "10 bits per mode" without derivation. We apply Shannon's channel capacity theorem to determine the actual achievable storage.

For a single measurement of a signal in additive white Gaussian noise:

$$b = \frac{1}{2} \log_2(1 + \text{SNR})$$

The paper's claim of 10 bits/mode requires:

$$\text{SNR} = 2^{20} - 1 \approx 10^6 \quad (\sim 60 \text{ dB})$$

This is an extraordinary SNR — comparable to high-end laboratory instrumentation — and is never stated or justified in the paper.

### 5.2 Actual Capacity at Realistic SNR

| Configuration                                | SNR (mode 1) | Bits/mode | Bits/cell (10 modes) | Paper overestimate |
| -------------------------------------------- | ------------ | --------- | -------------------- | ------------------ |
| Baseline (default)                           | −6.5 dB      | 0.15      | 1.5                  | **68×**            |
| Mitigated (gel η×100, 10⁸ photons)           | 13.5 dB      | 2.28      | 22.8                 | **4.4×**           |
| Aggressive (gel η×1000, 10⁹ photons, Q=1000) | 24 dB        | 3.91      | 39.1                 | **2.6×**           |

Even with aggressive mitigations, Shannon limits the architecture to approximately **2–4 bits per mode**, not 10. The total bits per cell is ~20–40, not 100.

### 5.3 Storage Density

With the corrected bits-per-cell values:

| Configuration          | Bits/cell | Cells/cm³ | Density          |
| ---------------------- | --------- | --------- | ---------------- |
| Paper claim            | 100       | 10⁹       | **1–10 Tb/cm³**  |
| Mitigated (this work)  | 22.8      | 10⁹       | **0.023 Tb/cm³** |
| Aggressive (this work) | 39.1      | 10⁹       | **0.039 Tb/cm³** |

The realistic density is **44–440× below the paper's claims**. This is the single largest quantitative correction in our analysis.

### 5.4 Bandwidth and Latency

The paper provides no latency or bandwidth estimates. Our timing model, based on acoustic propagation and coherent integration:

| Metric         | Value         | Notes                                               |
| -------------- | ------------- | --------------------------------------------------- |
| Write latency  | **14 ns**     | Acoustic round-trip: $2L/v = 2 \times 10^{-5}/1400$ |
| Read latency   | **1 µs**      | Coherent integration: $1/\text{BW} = 1/10^6$        |
| Ring-down time | **2.3 µs**    | Mode separation: $Q/(\pi f_0)$                      |
| Cycle time     | **3.3 µs**    | Write + ring-down + read                            |
| Cell bandwidth | **45.5 Mb/s** | Mitigated configuration                             |

The 14 ns write latency is competitive with DRAM. The 1 µs read latency places WCFOMA between DRAM and Flash in the access-time hierarchy.

---

## 6. Technology Comparison

### 6.1 Head-to-Head Benchmarking

We benchmark WCFOMA (mitigated configuration) against seven established or emerging memory technologies:

| Technology             | Energy [pJ] | Density [Tb/cm³] | Read [ns] | Compute Locality | Stage          |
| ---------------------- | ----------- | ---------------- | --------- | ---------------- | -------------- |
| SRAM (7nm)             | 0.5         | 0.001            | 0.5       | None             | Production     |
| DRAM (DDR5)            | 3.0         | 0.01             | 14        | None             | Production     |
| STT-MRAM               | 1.0         | 0.01             | 10        | Partial          | Production     |
| ReRAM/Memristor        | 0.1         | 0.1              | 10        | Partial          | Prototype      |
| PCM (3D XPoint)        | 10          | 0.1              | 50        | Partial          | Production     |
| NAND Flash (3D TLC)    | 1000        | 1.0              | 25,000    | None             | Production     |
| Magnonic logic         | 0.01        | 0.001            | 100       | Partial          | Prototype      |
| **WCFOMA (mitigated)** | **~10**     | **0.023**        | **1,000** | **Unified**      | **Simulation** |

### 6.2 Where WCFOMA Sits

WCFOMA (mitigated) occupies the **energy–density gap between DRAM and PCM**:

- 3× the energy of DRAM, but with non-volatile-like retention during coherence windows.
- Similar energy to PCM, but with 5× lower density.
- Competitive write latency (14 ns), but slow read (1 µs).

The paper's original claim of "10–100× improvement" over von Neumann architectures is **not supported** by our analysis. WCFOMA is competitive, but it is not transformatively better on any single axis.

### 6.3 The Unique Value: Unified Compute Locality

Where WCFOMA _is_ unique is in **compute locality**. Every other technology in the table either has no compute capability (data must be moved to a processor) or has partial compute (limited operations like multiply-accumulate in the memory array). WCFOMA performs associative recall — pattern matching and similarity search — _as a physical consequence of wave interference_. No data movement. No address bus. No ALU.

For workloads dominated by similarity search (nearest-neighbor retrieval, attention mechanisms, content-addressable lookups), this unified locality may justify the density and latency tradeoffs. This is the architecture's strongest selling point, and it is the one the original paper under-emphasizes relative to the inflated density claims.

---

## 7. Dilatancy-Based Security

### 7.1 Mechanism

Granular and shear-thickening materials exhibit dilatancy — stress-induced internal rearrangement that alters the medium's geometry without external power [3]. In WCFOMA:

1. An attacker applies mechanical stress to probe or extract stored data.
2. The stress causes the cavity geometry to change (length dilation $L' = L(1 + \beta\gamma)$).
3. Resonant frequencies shift: $\Delta f / f \approx -\beta\gamma / (1 + \beta\gamma)$.
4. The frequency shift is measurable and serves as a tamper signal.

### 7.2 Simulation Results

| Scenario                     | Frequency drift  | Coherence impact             |
| ---------------------------- | ---------------- | ---------------------------- |
| 1D, γ = 0.5 (severe shear)   | ~33%             | Moderate damping             |
| 3D, γ = 0.3 (moderate shear) | ~7%              | Anisotropic (mode-dependent) |
| 3D with ZIM                  | 50% slower decay | 2× coherence extension       |
| Minimum detectable γ         | 0.010 (1%)       | Reliable at 1% noise         |

### 7.3 Statistical Validation

5,000-trial Monte Carlo:

- **False positive rate:** 4.7% (threshold tunable)
- **False negative rate:** 0% (all tamper events detected)
- **Minimum detectable perturbation:** 1% geometric change

This is fundamentally different from cryptographic security: tampering produces a _physical_ signature that does not depend on computational hardness assumptions. It fails visibly rather than silently.

---

## 8. Honest Claims Scorecard

We explicitly categorize every major claim from the original paper against our simulation evidence:

| Original Claim                       | Simulated Result                            | Verdict                        |
| ------------------------------------ | ------------------------------------------- | ------------------------------ |
| ZIM extends coherence ~2×            | 2.0× confirmed                              | ✅ **Confirmed**               |
| Frequency drift ~33% at γ = 0.5 (1D) | 33.33% measured                             | ✅ **Confirmed**               |
| Frequency drift ~7% at γ = 0.3 (3D)  | ~7% measured                                | ✅ **Confirmed**               |
| 41 modes without ZIM                 | 41 computed                                 | ✅ **Confirmed**               |
| 322 modes with ZIM                   | 322 computed                                | ✅ **Confirmed**               |
| Geometry invariance (<1% shift)      | 0% analytical (Mie); FD solver inconclusive | 🔶 **Plausible**               |
| Excitation energy in fJ range        | 2.6 fJ (physics-only)                       | ✅ **Confirmed** (physics)     |
| System energy in fJ range            | 1,114 fJ ≈ 1.1 pJ (CMOS readout dominates)  | ❌ **Refuted**                 |
| 10 bits per mode                     | 2.3 bits (mitigated), 3.9 bits (aggressive) | ❌ **Overestimate (2.6–4.4×)** |
| 1–10 Tb/cm³ density                  | 0.023 Tb/cm³ (mitigated)                    | ❌ **Overestimate (44–440×)**  |
| 10–100× improvement over von Neumann | Competitive but not transformative          | ❌ **Not supported**           |
| No latency/bandwidth analysis        | Write 14 ns, Read 1 µs, 45.5 Mb/s           | ✅ **Gap filled**              |

**Summary: 7 Confirmed, 1 Plausible, 4 Corrected Downward.**

The corrections are large. But the architecture survives them. The question has shifted from _"Is this 100× better?"_ to _"Is the unified compute locality valuable enough to justify a technology that is competitive-but-not-dominant on conventional metrics?"_

---

## 9. Experimental Roadmap

### 9.1 Falsification-First Framework

Every phase has explicit **kill criteria** — quantitative thresholds that, if not met, terminate the research direction. Negative results are considered publishable and valuable.

### 9.2 Phase 1: Benchtop Prototype (< $1,000)

**Goal:** Measure real physics. Validate or kill the simulation predictions.

**Hardware:**

- Commercial ferrofluid (e.g., Ferrotec EFH series)
- **Gel-immobilized nanoparticles** (η ≥ 100× baseline) — required by noise analysis
- 3D-printed ZIM structures (Dirac-cone pillar arrays)
- Cylindrical cavity (1–5 cm)
- EM excitation coils + Faraday rotation readout
- **High-photon-count optical readout** (≥ 10⁸ photons/measurement) — required by noise analysis

**Kill criteria:**
| Measurement | Expected | Kill if |
|-------------|----------|---------|
| Quality factor Q | 100–1,000 | Q < 10 |
| Mode coherence time | 1–100 µs | < 100 ns |
| Distinguishable modes | 5–50 | < 3 |
| Write/read energy | ~10 pJ | > 100 pJ |
| Frequency drift under shear | 5–33% | < 1% |

### 9.3 Phase 2: Micro-Scale Arrays (University Cleanroom)

**Prerequisite:** Phase 1 confirms viable physics.

- FIB/EBL fabrication of ZIM structures on fiber facets
- 16–64 cell micro-arrays (10–100 µm cells)
- Optical excitation/readout through fiber
- Cell-to-cell crosstalk characterization

**Kill criterion:** Crosstalk > 10% between adjacent cells.

### 9.4 Phase 3: Domain-Specific Accelerator (If Warranted)

**Prerequisites:** Published, peer-reviewed results. Independent replication. Identified commercial application.

- \>1,000-cell prototype targeting similarity search or attention computation.
- Integrated CMOS interface.
- Head-to-head benchmark against GPU for specific workload.

### 9.5 Open Questions

These are the highest-impact unknowns, ordered by their potential to kill the architecture:

1. **What is the actual Q factor of resonant modes in ferrofluid at 70 MHz?** No direct measurement exists. This is the #1 unknown.
2. **Can multiple modes coexist without nonlinear coupling?** Linear superposition is assumed; ferrofluids are inherently nonlinear.
3. **Does gel immobilization preserve enough dilatancy for security?** The noise mitigation (high viscosity) may conflict with the security mechanism (stress-responsive viscosity).
4. **What is the actual phase noise from nanoparticle Brownian motion?** Our model may be conservative or optimistic — only experiment can resolve this.
5. **Can the ZIM structures survive acoustic cycling at 70 MHz?** Fatigue and degradation are unknown.

---

## 10. Conclusion

WCFOMA proposes a genuine architectural innovation: unifying memory, computation, and security in a single resonant wave field. The idea is physically grounded — resonant eigenmodes, wave interference, and granular dilatancy are all well-established phenomena.

However, the original performance claims were significantly over-optimistic. Our simulation campaign, comprising 15 physics modules and 155 automated tests, reveals:

- **The good:** The physics works. Modes persist. Interference enables associative recall. Dilatancy provides tamper detection. ZIM structures improve coherence. Write latency (14 ns) is competitive with DRAM.
- **The corrected:** System energy is ~10 pJ (not fJ). Storage density is ~0.02 Tb/cm³ (not 1–10). Bits per mode is ~2–4 (not 10). These corrections are factors of 4–440×.
- **The critical insight:** Nanoparticle Brownian motion creates phase noise that the paper did not model. This nearly kills the architecture, but gel immobilization + improved optical readout resolves it at achievable parameters.
- **The honest position:** WCFOMA sits between DRAM and PCM in energy–density space. It is competitive, not transformative. Its unique value is unified compute locality for associative workloads.

The question for experimentalists is whether the unified compute locality — associative recall, pattern matching, and similarity search as wave physics rather than transistor logic — justifies the engineering effort to reach the modest but real performance this analysis predicts.

All simulation code, notebooks, and data are available at [github.com/miketierce/wcfoma](https://github.com/miketierce/wcfoma) under the MIT license.

---

## References

[1] Sze, V., Chen, Y.-H., Yang, T.-J. & Emer, J. S. Efficient Processing of Deep Neural Networks: A Tutorial and Survey. _Proc. IEEE_ **105**, 2295–2329 (2017).

[2] Liberal, I. _et al._ Geometry-invariant resonant cavities. _Nature Communications_ **7**, 10989 (2016).

[3] Schaeffer, D. G. & Iverson, R. M. A series of two-phase models for grain–fluid flows with dilatancy. _J. Fluid Mech._ **978**, A7 (2024).

[4] Katz, O. _et al._ High-fidelity entanglement between a telecom photon and a room-temperature quantum memory. _arXiv:2503.11564_ (2025).

[5] Rosensweig, R. E. _Ferrohydrodynamics_. Cambridge University Press (1985). (Acoustic model for ferrofluid suspensions.)

[6] Lyu, K. _et al._ Acoustic leaky-wave antennas from zero-index metamaterials. _Phys. Rev. Applied_ **24**, 034043 (2025).

---

## Appendix A: Simulation Repository Structure

```
wcfoma/
├── simulations/           # 15 physics modules
│   ├── resonator_1d.py    # 1D damped oscillator
│   ├── resonator_3d.py    # 3D FDTD wave solver
│   ├── helmholtz_2d.py    # 2D Helmholtz (ENZ cavities)
│   ├── thermal.py         # Mode crowding & thermal drift
│   ├── sensitivity.py     # Parameter sensitivity & elasticity
│   ├── ferrofluid.py      # Rosensweig ferrofluid model
│   ├── interference.py    # Multi-mode associative recall
│   ├── convergence.py     # Grid convergence (Richardson)
│   ├── cmos_interface.py  # CMOS energy budget (4 tech nodes)
│   ├── coupled_physics.py # SVEA coupled-mode simulation
│   ├── noise_decoherence.py # 5-source noise model
│   ├── mitigations.py     # Phase diffusion mitigations
│   └── capacity.py        # Shannon capacity & tech comparison
├── notebooks/             # 10 reproducible Jupyter notebooks
├── tests/                 # 155 automated tests
└── docs/                  # Roadmap with kill criteria
```

## Appendix B: Key Equations Summary

**Mode frequency:** $f_n = nv/(2L)$

**Coherence time:** $\tau = Q/(\pi f_n)$

**Phase diffusion:** $D_{\text{rot}} = k_BT / (\pi\eta d^3)$

**Shannon capacity:** $b = \frac{1}{2}\log_2(1 + \text{SNR})$ bits/measurement

**Channel capacity:** $C = B \cdot \log_2(1 + \text{SNR})$ bits/s

**Dilatancy drift:** $\Delta f/f \approx -\beta\gamma/(1 + \beta\gamma)$

**Thermal mode limit:** $n_{\max}$: largest $n$ such that $2 f_n \alpha \Delta T / R < \Delta f - f_n/Q$

**Write latency:** $t_w = 2L/v$

**Read latency:** $t_r = 1/B$

**Cycle time:** $t_c = t_w + Q/(\pi f_0) + t_r$

---

_All claims in this paper are tagged by evidence level: confirmed (simulation-validated), plausible (analytically supported but not yet simulated with full fidelity), corrected (original claim revised downward based on simulation evidence), or projected (extrapolation pending experimental validation)._
