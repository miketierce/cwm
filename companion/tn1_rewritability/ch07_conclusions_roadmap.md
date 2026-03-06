## 7. Conclusions and Roadmap Impact

### 7.1 Summary of Findings

This technical note investigated whether the Spectral Eigenmode Memory architecture—originally conceived as a read-only device—could support physical rewritability without sacrificing its defining advantage: ultra-high Q-factor acoustic resonance.

Seven hypotheses were tested across three architectural tracks:

| Track            | Hypotheses | Confirmed | Key result                                                                        |
| ---------------- | ---------- | --------- | --------------------------------------------------------------------------------- |
| A — Firmware     | H7, H8, H9 | 3/3       | 4 virtual devices per rod; amplitude-weighting masks work, zero-out masks fail    |
| B — Binary sites | H10, H11   | 2/2       | 7.6 bits rewritable state from 12 MEMS switches; Hopfield-compatible from 4 sites |
| C — Multi-shell  | H12, H13   | 2/2       | 256 actuators at $Q > 5\text{k}$; 100 nm writable shell with 0.34% tuning range   |

**All seven hypotheses confirmed.** The SEM architecture admits rewritability at every level of the system stack, from pure firmware to physical material modification.

### 7.2 The Central Insight

The experiments revealed a design principle that was not obvious before this investigation:

> **The separation principle.** In SEM, the read medium (glass rod eigenmodes) and the write mechanism (firmware projection, MEMS switches, or shell coating) are independent subsystems. The rod can be optimized purely for Q without compromising write/erase cycling, because writing happens _around_ the rod, not _in_ it.

This is fundamentally different from every other memory technology, where read and write are coupled through the same physical mechanism (charge trapping in flash, magnetization in MRAM, polarization in FeRAM). The separation principle is what makes SEM's rewritability path viable despite the constraints of acoustic resonance.

### 7.3 Impact on the v14 Roadmap

The parent paper [1] proposed a five-phase development roadmap. This technical note's findings affect three of the five phases:

**Phase 1 (Single-rod demonstrator):** No change. The first prototype validates the baseline read-only architecture.

**Phase 2 (Multi-rod array):** Add firmware virtual rewriting (Track A). The ASIC readout pipeline should implement multi-projection partitioning (H7) and mode-subset addressing (H8). This is a software feature—no hardware changes to the MEMS die.

**Phase 3 (Packaged module):** Evaluate binary perturbation sites (Track B). The second-generation MEMS die should include provisions for 12–20 electrostatic latch sites. This requires layout changes but no new process steps (electrostatic latches use the same thin-film metal and oxide layers already in the MEMS process).

**Phase 4 (Write/erase capability):** This phase was originally speculative. The results in this note provide a concrete implementation plan:

- Stage 1: Parylene C shell (passive, applied at packaging).
- Stage 2: Magnetostrictive film (active, externally controllable).
- Stage 3: Phase-change shell (fully rewritable, with endurance limits).

**Phase 5 (Product):** The staged rewriting architecture means that "product" is not a single SKU but a family: ROM (Stage 0), firmware-reconfigurable (Stage 1), MEMS-switchable (Stage 2), and fully rewritable (Stage 3). Each serves a different market segment and price point.

### 7.4 What Remains Unknown

This investigation was conducted entirely in simulation. Several questions can only be answered by experiment:

1. **Latch Q in practice.** H12 models actuators as localized lossy regions. Real MEMS latches have moving parts, air gaps, and contact mechanics that may introduce loss mechanisms not captured by the volume-fraction model.

2. **Shell adhesion.** Parylene C adheres well to glass, but the acoustic coupling between shell and rod depends on the interface quality. A delaminated shell would reduce perturbation efficiency without reducing Q loss.

3. **Binary-site cross-talk.** H10 assumes independent site contributions (linear coupling matrix). Real perturbation sites may interact through evanescent acoustic fields, reducing the effective bit count.

4. **Write endurance.** The simulation does not model fatigue, creep, or material degradation. MEMS switch lifetime data [4] suggests $> 10^9$ cycles is achievable, but this must be verified in the SEM-specific geometry.

5. **Readout noise floor.** The distinguishability threshold ($\delta > 0.1$) in H10 assumes a specific noise floor. The actual noise depends on the CMOS readout circuit, the piezoelectric transducer coupling, and the ADC resolution.

### 7.5 Reproducibility

All experiments described in this note are implemented in the open-source SEM simulation framework:

- **Module:** `simulations/rewritability.py` (1,174 lines, 7 experiments)
- **Tests:** `tests/test_rewritability.py` (68 tests, all passing)
- **Integration:** `run_all_rewritability(verbose=True)` reproduces all results

The complete simulation stack (22 modules, 433 tests) is available in the project repository. Every number in this paper is produced by running the corresponding experiment function with default parameters.

---
