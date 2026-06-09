# Build & Experiment Plan: CWM Physics Validation Paper

## Paper Strategy

**Working title:** "Physics Validation and MEMS Design for Wave-Interference Content-Addressable Memory in Glass Resonators"

**Core contribution:** First experimental demonstration that eigenmode-spectral encoding in glass resonators satisfies the physics prerequisites for a parallel-search content-addressable memory, with a quantitative MEMS device design whose performance predictions are anchored in measured material parameters.

**What makes this publishable (vs. "we built a sensor"):**

1. We validate the WRITE mechanism (perturbation → frequency shift, Rayleigh formula)
2. We validate the READ mechanism (broadband drive → FFT → fingerprint retrieval)
3. We validate the SEARCH mechanism (template matching via spectral correlation)
4. We measure the transfer matrix that predicts MEMS-scale performance
5. We present a falsifiable MEMS design: "build this, expect these numbers"

**Honest framing:** The bench demonstrates all prerequisite physics _sequentially_. The architectural claim is that these operations compose into O(1) parallel search when fabricated as an array. That composition requires a MEMS device. The paper's scientific discipline is: clearly separate what's measured from what's predicted, anchor all predictions in measured parameters, and identify the specific fabrication assumptions.

---

## Hardware Build Requirements

### Phase 1: Bench Upgrades (No New Hardware Needed)

The current setup is sufficient for most validation experiments:

- Pico NCO (3-ch, 126 MHz PIO) ✓
- PicoScope 2204A (2-ch, 781 kHz) ✓
- OPA2134PA preamp (×11) ✓
- Fused silica plate 100×100×1mm ✓
- 4× PZT 20mm ✓
- Relay mux (8-ch) ✓
- Two plates already measured (Plate I, Plate H) ✓

### Phase 2: Perturbation Encoding Hardware (~$15)

**Critical for the WRITE validation:**

- **Weighed wax putty** — 50mg dots, measured on precision scale, removable
- Already in use in the lab (no purchase needed)
- Apply to plate surface at known positions (center, corner, quarter-point)
- Remove cleanly, verify modes return to baseline

**Perturbation mass:** 50mg on a 1.375g plate → Δm/m = 3.6% → expect ~1.8% frequency shift at antinodes.

### Phase 3: Multi-Element Demonstration (Optional, ~$50)

For a stronger paper, demonstrate simultaneous multi-rod operation:

- 4 glass rods already in the setup from April 8 work
- Wire them with separate TX PZTs driven simultaneously (Pico NCO has 3 channels)
- Combined RX: single receiver reads superposition of all rod responses
- This would demonstrate the PARALLEL SEARCH operation in hardware

**Whether to include this depends on time.** The paper is publishable without it if framed as "sequential validation of operations that compose in parallel at MEMS scale."

---

## Experiment Plan

### E1: PZT-Lifted Null Test on Pico NCO (30 min)

**Purpose:** Close signal-path attribution definitively.
**Status:** Data exists for May 27 (AD9833 topology). Need formal test on June 2+ Pico NCO config.

**Protocol:**

1. Drive at 4 modes (35840/54920/57037/97011 Hz), capture baseline FFTs
2. Physically lift TX PZT from plate (break acoustic contact but leave wires connected)
3. Re-drive, capture FFTs
4. Report: lifted_signal / coupled_signal ratio at each mode

**Success:** Ratio < 1% at all modes → confirms > 99% acoustic for current topology.

---

### E2: Q-Factor via Bandwidth Method (1 hour)

**Purpose:** Get reliable Q without problematic ringdown fitting.
**Problem:** Current ringdown has R² < 0.1. Alternative: measure the resonance 3-dB bandwidth directly.

**Protocol:**

1. Fine frequency sweep around each mode (±2 kHz in 10 Hz steps)
2. Plot magnitude vs. frequency → Lorentzian peak
3. Q = f₀ / Δf₃ᵈᴮ (bandwidth at half-power)
4. Repeat for 4 strongest modes
5. Fit Lorentzian curve: report R² for the fit

**Success:** Lorentzian fit R² > 0.95 at least 3 modes. This is a MUCH cleaner measurement than ringdown because we're fitting steady-state response, not a transient.

**Note:** We already HAVE fine sweep data from the Lorentzian kernel measurement! Check if `data/results/` contains the T5 fine-sweep data from June 2 that measured Q_loaded = 473.

---

### E3: Perturbation Encoding — Write Mechanism Validation (2 hours)

**Purpose:** Demonstrate that mass loading shifts eigenfrequencies as predicted by Rayleigh perturbation theory. This validates the WRITE mechanism that makes the architecture more than just a sensor.

**Protocol:**

1. Measure baseline mode spectrum (all modes, positions)
2. Place known mass m₁ at position x₁ (plate center)
3. Re-measure all modes → record frequency shifts Δf₁, Δf₂, ..., Δfₙ
4. Move mass to position x₂ (quarter-point)
5. Re-measure → different pattern of shifts
6. Place second mass at position x₃
7. Measure → yet another pattern

**Analysis:**

- Compare measured Δf/f to Rayleigh prediction: Δω/ω = -(Δm/2m_eff)·u²(x₀)
- Show that DIFFERENT positions create DIFFERENT shift patterns (the encoding principle)
- Show that the plate with perturbation has a distinct fingerprint from the bare plate

**Success:**

- Shifts detectable (> 3σ above measurement noise) for mass > 10mg
- Position-dependence confirmed (different positions → different shift patterns)
- Qualitative agreement with Rayleigh prediction (shift largest when mass at antinode)

**This is THE critical experiment for the paper.** Without it, the "memory" claim is theoretical.

---

### E4: Cross-Session Discrimination (3 days)

**Purpose:** Prove that spectral fingerprints are intrinsic properties of geometry, not session artifacts.

**Protocol:**

1. Day 1: Enroll baseline fingerprints (4 modes, 20 reps)
2. Day 2: Power cycle everything, re-measure, classify using Day 1 centroids
3. Day 3: Repeat

**Success:** Cross-session accuracy ≥ 95% with Wilson CI.

---

### E5: Multi-Element Associative Recall with Template Scoring (1 hour)

**Purpose:** Demonstrate that different physical resonators (rods or plates) produce distinguishable spectral fingerprints, and that template-based scoring correctly identifies which element is being queried.

**We already have this data!** April 8 rod experiments show:

- 4 rods, 4 patterns, template scoring: 100% accuracy, mean margin +5.26
- Nearest-neighbor with α-interpolation: 11/11 correct, Kendall τ = 1.0
- Multi-plate enrollment (June 3): 2 plates discriminated (cos_sim = 0.93)

**Additional experiment needed:** Repeat with Pico NCO on current plate topology to get data under the improved signal-path conditions. The April 8 data was on the old rod setup with AD9833 drive.

---

### E6: Content-Addressable Memory Operation (2 hours)

**Purpose:** Demonstrate the core architectural primitive: "drive with query → score against enrolled templates → identify best match."

**Protocol:**

1. Enroll N spectral templates (from H-matrix: N modes, each with characteristic amplitude pattern across channels)
2. Drive with each template's characteristic frequency pattern as query
3. Measure response at both channels
4. Score: cosine similarity between response vector and each enrolled template
5. Best match = highest score

**We already have this!** The CAM experiment (June 3) shows:

- 27 enrolled modes
- 100% exact retrieval accuracy
- Graceful degradation: 97.6% at 5% noise, 84.8% at 10% noise, 50% at 20% noise

**Gap:** This used the measured H-matrix for enrollment, then scored against it — effectively template matching in software. Need to distinguish: was the "query" a real physical drive, or was it a lookup against stored data?

**Additional needed:** Drive the plate at each enrolled frequency, capture real response, score against enrolled templates from a DIFFERENT session. This would prove: physical drive → physical response → correct identification.

---

### E7: Fixed-Angle CHSH Reanalysis (1 hour, no bench time)

**Purpose:** Remove selection-bias critique from non-separability measurement.

**Protocol:** Re-analyze existing E1 data with standard Bell angles (0°/22.5°/45°/67.5°).

---

### E8: All-Decoder Sensitivity Analysis (2 hours, no bench time)

**Purpose:** Show classification is not pipeline-dependent.

**Protocol:** Test multiple classifiers on existing discrimination data.

---

## MEMS Device Design Section

The paper includes a MEMS design section presenting:

1. **Reference device geometry** — 1mm × 40µm fused silica rod, AlN transduction, vacuum-packaged
2. **Q-factor model** — five-mechanism budget (material, anchor, TED, gas, surface) → Q_total = 9,097
3. **Performance predictions:**
   - Mode count: 9,380 (size-independent, from α, Q, ΔT)
   - Bits per rod: 119,126 (at 76.7 dB thermodynamic SNR)
   - Read latency: 3.8 µs (one acoustic cycle)
   - Write energy: 15 fJ/bit (physics-layer)
   - Array density: 17 Gbit/cm³ (at 80µm pitch)
4. **Reservoir computing prediction** — at step/τ = 0.00004, inter-step memory ≈ 1, NRMSE = 0.39 (simulated with measured H-matrix)
5. **Fabrication pathway** — all steps use volume MEMS processes

**Anchoring to measurements:**

- Q_material from bench ringdown/bandwidth (E2)
- H-matrix from June 2 measurement
- Mode count from census
- Perturbation sensitivity from E3
- Signal integrity from E1
- Endurance from E11 (16.5M cycles)

---

## Experiment Priority Matrix

| ID  | Experiment            | Validates               | Bench Time     | Critical?                       |
| --- | --------------------- | ----------------------- | -------------- | ------------------------------- |
| E1  | PZT-lifted null       | Signal integrity        | 30 min         | YES                             |
| E2  | Q via bandwidth       | Material parameter      | 1 hr           | YES                             |
| E3  | Perturbation encoding | Write mechanism         | 2 hr           | YES (paper's central novelty)   |
| E4  | Cross-session         | Stability / intrinsic   | 3 days         | HIGH                            |
| E5  | Multi-element recall  | Search mechanism        | 1 hr           | HIGH (or use existing rod data) |
| E6  | CAM with real drive   | Architecture primitive  | 2 hr           | MEDIUM                          |
| E7  | Fixed-angle CHSH      | Unbias non-separability | 0 (reanalysis) | MEDIUM                          |
| E8  | All-decoder           | Robustness              | 0 (reanalysis) | MEDIUM                          |

**Minimum viable paper:** E1 + E2 + E3 + existing rod/H-matrix data + MEMS model
**Strong paper:** All of E1–E6 + MEMS model + CHSH (downscoped)

---

## What This Paper Claims vs. What It Doesn't

### Claims (defensible):

- A glass resonator's eigenmode spectrum provides a stable, reproducible, high-SNR feature space
- Modes are spatially non-separable (different receivers see different projections)
- Mass perturbation creates predictable, position-dependent frequency shifts (encoding)
- Template matching against enrolled spectral fingerprints achieves perfect discrimination (search primitive)
- These operations compose, in principle, into an O(1) parallel search in an array
- A MEMS device with specified parameters would achieve [density, energy, latency]

### Does NOT claim:

- The plate "computes" (all current classification is digital)
- Temporal/reservoir computing works at bench (it doesn't — explicitly fails)
- The architecture is competitive today (it isn't — it needs MEMS fabrication)
- Any quantum phenomena

### The honest pitch:

"We've measured the transfer matrix of a glass resonator and shown it has the right properties (linearity, spatial diversity, stability, perturbability) to function as a physical inner-product engine for content-addressable memory. Here's exactly how to build the MEMS version and what performance to expect."

---

## Shopping List

| Item                                     | Purpose             | Est. Cost  |
| ---------------------------------------- | ------------------- | ---------- |
| 1mm neodymium disc magnets (50-pack)     | Perturbation masses | $8         |
| Precision tweezers                       | Placement           | $5         |
| Jeweler's wax or museum wax              | Temporary adhesion  | $5         |
| 0.1mg precision scale (if not available) | Mass verification   | $30        |
| **Total**                                |                     | **$18–48** |

Everything else is already in the lab.

---

## Timeline

| Day | Activities                                                |
| --- | --------------------------------------------------------- |
| 1   | E1 (null test) + E2 (bandwidth Q) + order magnets         |
| 2   | E4 Day 1 enrollment + E7/E8 reanalysis                    |
| 3   | Magnets arrive → E3 (perturbation encoding)               |
| 4   | E4 Day 2 cross-session + E5 (multi-element with Pico NCO) |
| 5   | E4 Day 3 + E6 (CAM validation)                            |
| 6-7 | Write paper (v20), generate figures                       |
| 8   | Review, PDF, submit                                       |
