# Desk Demonstrator — Bench Protocol (All Phases)

**Companion to [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md).** This is the concrete, repeatable, shareable build-and-measure protocol for the phononic plate-array demonstrator. Every phase is written in the [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md) style: objective, prerequisites, materials, numbered procedure, verification checks, agent prompt, success/kill criteria, data path, and time. A third party with the BOM and these pages should be able to reproduce every result.

**ID convention:** `DD-P<phase>` (Desk Demonstrator, Phase n). Cross-references to ladder rungs (R0–R11) in [FRONTIER_CEILING.md](FRONTIER_CEILING.md) and worklist IDs (WL-\*) noted per entry.

**Maturity labels** (inherited): MEASURED / SIMULATED / PROJECTED / OPEN. Build steps are deterministic; measurement _outcomes_ carry the label of the claim they test.

**⚠️ Wave-Native Design Principle.** Before running any phase: the glass is a smooth, low-dimensional analog **kernel + content-addressable memory**, not a von Neumann machine. The first silicon algorithm usually fails. Proven dualities (MEASURED 2026-06): track/integrate not predict/branch; nearest-**centroid** not ridge **regression** (T3.4 4096 states 100% vs ridge 0.55%); encode by **amplitude of a fixed mode** not **frequency position** (8 levels/mode @ 100σ vs ~2 levels/axis); **factor** the state; keep collision modes; make the **Gram matrix** diagonal-dominant. Full table in [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md).

---

## Standing Desk-Rig Config (verify before every session)

- **Host:** Raspberry Pi 5 or mini-PC (BOM DD19), Python 3.11+, repo checked out, `PYTHONPATH=.`
- **Control surface:** all phases run through the one orchestrator API (`cwm.excite/measure/project/match/fingerprint/…`, the PFU instruction set), not raw per-device commands — see [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md) §3.9. Agent prompts below are the CLI form of those calls; a local web UI is the demo form.
- **FPGA brain — Red Pitaya STEMlab 125-14 (BOM DD1):** Ethernet to host LAN; static IP recommended (e.g. `192.168.1.100`). SCPI server on TCP:5000, or PyRPL API. Verify: `ping 192.168.1.100` then `redpitaya_scpi.scpi('192.168.1.100')` returns an ID string.
- **Pico NCO (owned):** `/dev/cu.usbmodem113301`, 115200 baud — `F1:<freq>`..`F4:<freq>`, `Foff`, `PHASE:<deg>`, `SWEEP:<start>,<stop>,<step>,<dwell_ms>`. Used as the high-frequency carrier source (30–350 kHz) where the Red Pitaya's baseband range is awkward.
- **Relay mux (owned):** `/dev/cu.usbserial-11310` — `RelayMux.open()` then `.select(N)`. The scrappy stand-in for the crosspoint switch's (row, col) job until the crosspoint IC is wired.
- **Crossbar / crosspoint switch (scale-faithful addressing, BOM DD21):** MT8816/ADG2128 selects cell (row, col) on a few digital lines; maps 1:1 to the MEMS on-die address scheme (M×N cells, M+N lines, any pitch). This is the primary, shrinkable addressing layer (§3.2 of the build spec).
- **Optical readout (bring-up cross-check only):** 650 nm laser (DD2) + galvo (DD3) + BPW34 PD (DD4) → transimpedance amp (DD5) → Red Pitaya IN1 (or PicoScope ChA). Validates rank-N independently of the crossbar; has **no MEMS counterpart** and is deleted at scale.
- **Grounding:** single-point star ground; analog (±12 V) and logic (+5 V) returns joined only at the PSU. Twisted-pair every signal run with its own ground return (the project's recurring −33 dB EMI lesson).
- **Data convention:** `data/results/desk/<DD-Pn>/<YYYYMMDD_HHMMSS>/` — raw captures (`.npz`), fitted results (`.json`), a `manifest.yaml` (plate IDs, temperatures, firmware versions, git SHA), and a session `notes.md`.

**Global safety:** 650 nm laser (DD2) and the engraving laser (DD14) require a closed, interlocked optical enclosure and eyewear rated for the wavelength. Never operate the volumetric-write laser (DD14, treat as Class 4) open-air. Vacuum work (DD12): acrylic bell jars can implode — use a rated chamber, stand clear on first pump-down, never pressurize.

---

## Phase 0 — Cartridge Fabrication & Mode Census _(prerequisite for all phases; rung R0)_

**Objective:** Build the two plate cartridges (diversified + identical) on the **row/column transducer crossbar** — the MEMS-faithful addressing layer (§3.2 of the build spec) — and produce a verified per-cell mode map. Nothing downstream is repeatable without this baseline. **Status outcome:** MEASURED (census is a direct reading).

**Prerequisites:** none. First build step.

**Materials:** slides (DD6), PZT discs (DD7), card-cage frame + nodal foam (DD8), CA glue (WL #12), isopropyl + swabs, fine-tip multimeter, label maker / paint pen.

**Procedure — cartridge build:**

1. **Clean** every slide: isopropyl both faces, lint-free wipe, air-dry. Handle by edges only thereafter.
2. **Build the diversified cartridge (8 plates).** Deliberately separate each plate's mode comb so the array is frequency-division-multiplexable (§5 of the demonstrator doc):
   - Option A (preferred): source slides in graded thicknesses (e.g. 0.8 / 1.0 / 1.2 mm) — modes scale ∝ thickness.
   - Option B: identical slides, each with a small tuning mass (a measured dot of CA glue or a 5–20 mg PZT offcut) at a fixed corner, mass stepped per plate.
   - Label plates `D1…D8`, record the differentiator (thickness or tuning mass) in `manifest.yaml`.
3. **Build the identical cartridge (8 plates).** Same nominal slide, same PZT position, same glue protocol — the goal is for them to differ _only_ by manufacturing variance (this is the PUF substrate). Label `I1…I8`.
4. **Bond one drive PZT per plate.** Pre-solder leads to each 10 mm PZT (DD7). Apply a thin, full CA coat; place at a corner ≥3 mm from the edges; 24 h cure. Mark the bonded face.
5. **Nodal mount.** A free–free thin plate has flexural nodal lines near 0.224 L and 0.776 L from each end. Cut foam tips (WL #13) and set the card-cage slots so each plate rests on its nodal lines, not its antinodes — this preserves intrinsic Q. Plates stand on edge at ~10 mm pitch.
6. **Wire the drive rail.** All plate-drive PZT hot leads → a shared TX bus along the cage back; grounds → the star ground. (Broadcast drive is what makes the CAM demo a single-shot parallel search.)
7. **Continuity check.** Verify every PZT: hot-to-rail continuity, no hot-to-ground short. Record DC resistance per plate.

**Procedure — mode census (run per plate, both cartridges):**

8. Select one plate/cell via the **crosspoint switch (row, col)** — the scale-faithful address path — or the relay mux as the owned stand-in. Drive a coarse sweep with the Pico NCO: `SWEEP:5000,200000,200,40` (5–200 kHz, 200 Hz steps, 40 ms dwell). Capture the cell response (the optical cross-check arrives in Phase 1).
9. Identify peaks ≥10 dB over the local noise floor. Record `f₀`, amplitude, and a coarse Q (peak/−3 dB width) for the top 10 modes.
10. Repeat for all 16 plates. Save each as `data/results/desk/DD-P0/<plate_id>/census.json`.
11. **Diversified-cartridge acceptance:** confirm the 8 plates' strongest modes occupy _distinguishable_ bands (no two top-modes within 2× the −3 dB width). If two collide, re-tune the offending plate (more/less tuning mass).

**Verification checks:**

- Each plate shows ≥7 resolvable modes in 5–200 kHz (matches the project's 7–15 baseline).
- Diversified cartridge: top modes are band-separated (acceptance above).
- Identical cartridge: top modes nominally overlap (that is correct — variance shows up in fine structure, resolved in Phase 6).

**Agent prompt:**

> Run the desk-rig Phase 0 census. For the cell I name (crosspoint row,col — or relay stand-in), drive a coarse sweep 5–200 kHz at 200 Hz steps via the Pico NCO and capture the cell response. Extract the top 10 peaks (f₀, amplitude, coarse Q = f₀/Δf₋₃dB). Save to data/results/desk/DD-P0/<plate_id>/census.json with a manifest (slide thickness or tuning mass, PZT resistance, ambient temperature, git SHA). After all 8 plates of a cartridge, build a band-occupancy chart and, for the diversified cartridge, flag any two plates whose strongest modes fall within 2× linewidth.

**Success:** all 16 plates censused; diversified cartridge band-separated; identical cartridge built to one nominal spec. **Kill:** none — census is characterization; a plate with <5 modes is simply retired from the cartridge.

**Data path:** `data/results/desk/DD-P0/`. **Time:** 1 day build + 1 day census (16 × ~15 min).

---

## Phase 1 — Rank-N Readout: Crossbar Array-Sense (primary) + Optical Cross-Check _(rung R3; extends WL-B1)_

**Objective:** Break the rank-2 bottleneck (B1) at desk scale. The **primary, MEMS-faithful path** is the crossbar array-sense (low-mass transducer grid, read electrically via the crosspoint switch — exactly how the chip does it). The **optical scan is an independent cross-check** that proves rank-N without bonding a grid and has no MEMS counterpart. **Status outcome:** OPEN (rank-2 is MEASURED; rank ≥6 is the target).

**Prerequisites:** Phase 0 complete (need known modes to aim at).

**Materials:** crossbar grid (PVDF DD20 or light PZT) + crosspoint switch (DD21); cross-check optics — laser (DD2), galvo + driver (DD3), BPW34 (DD4), TIA parts (DD5), arms/posts (DD9), razor blade + alignment grid (WL #5).

**Primary path — crossbar array-sense (scale-faithful):**

**Build the crossbar sense grid (one-time fabrication):**

1a. **Column buses (bottom):** lay parallel self-adhesive copper-tape strips across the plate underside at the cell pitch (~10 mm) — the column electrodes. Bring each to an edge pad.
1b. **Piezo layer:** place the sense cells at each row×column intersection. Two builds — _low-mass (faithful):_ PVDF film (DD20) **cut into column strips** (or pre-patterned electrode film) so the bottom metallization forms isolated columns; _robust (simplest):_ a grid of small light-PZT discs, one per intersection. A continuous unpatterned PVDF sheet will short all columns — strip or pattern it.
1c. **Row buses (top):** lay perpendicular copper-tape strips over the piezo layer — the row electrodes. Each row×column overlap is now one sense cell.
1d. **Wire to the crosspoint (DD21):** row pads → crosspoint X-lines, column pads → Y-lines (MT8816 8×16 or ADG2128). To read cell (i, j): connect row i to the sense preamp and column j to virtual ground; park unselected lines at ground to suppress passive-matrix sneak paths. Address lines driven from the Arduino/FPGA.
1e. **Continuity + isolation check:** confirm each cell's row–column capacitance is present and adjacent-cell coupling is >10× lower. Record the cell map in `manifest.yaml`.

**Measure rank:** 2. **Shared drive + array sense:** drive the whole plate from one element; sense each grid cell (i, j) by selecting it on the crosspoint switch → preamp → PicoScope/Red Pitaya. 3. For each driven mode, capture the cell-by-cell amplitude over the grid → assemble the **cell×mode** matrix H. SVD; count singular values above 1% of σ₁ → effective rank. 4. Confirm the cell-amplitude pattern tracks the mode shape (antinodes high, nodes low). This is the electrical, shrinkable rank-N readout.

**Independent cross-check — optical (does not shrink):**

**Procedure — single-point validation first (do not skip):**

1. Mount the laser on an arm at ~45° incidence to plate `D1`, spot on a known antinode (between the nodal lines). Mount the BPW34 in the reflected path.
2. Fix a razor blade half-occluding the reflected beam at the PD (knife-edge): plate deflection → beam walk → intensity modulation.
3. Build the TIA: spare OPA2134 half (DD5), Rf = 100 kΩ, Cf = 10 pF → Red Pitaya IN1.
4. Drive `D1` at its strongest census mode. Confirm a peak at the drive frequency that **vanishes on two nulls**: (a) beam blocked (optical null), (b) drive off (acoustic null). Both must collapse to noise floor — this proves the signal is true optical-acoustic, not pickup.
5. If knife-edge SNR < 20 dB after alignment, escalate to the quadrant PD (BOM #3).

**Procedure — galvo multi-point scan:**

6. Insert the galvo so the beam can be steered across all 8 plates and to ≥3 points per plate (24+ addressable spots). Calibrate the angle→position map: command a known voltage, mark where the spot lands on the printed grid taped behind the rack; build a lookup table.
7. **Time-multiplexed acquisition:** for each commanded spot, settle (≥1 ms), capture, step. A full 24-spot pass at kHz galvo settling takes well under a second — far faster than relay switching.
8. For one plate, capture the response at all its spots while driving one mode; confirm the spot-amplitude pattern matches that mode's shape (antinodes bright, nodes dark). This is the physical sanity check that you are reading the mode field, not an artifact.

**Procedure — rank measurement (the actual deliverable):**

9. Across N spots × M modes, assemble the spot×mode amplitude matrix H. Compute its SVD; count singular values above 1% of σ₁ → effective rank.
10. Compare mode count and Q (Lorentzian fits) against the Phase 0 contact-PZT census — optical readout should reveal modes the PZT mass was damping, and higher Q.

**Verification checks:** both nulls collapse to noise; spot pattern tracks mode shape; effective rank ≥6.

**Agent prompt:**

> Validate rank-N two ways. PRIMARY (crossbar): drive the plate shared; sense each grid cell via the crosspoint switch; build the cell×mode H, SVD it, report effective rank (1% of σ₁). CROSS-CHECK (optical): (1) single point — report mode-bin SNR for beam-blocked, drive-off, and live; (2) galvo scan — spot-amplitude map vs predicted mode shape; (3) spot×mode H rank. Compare crossbar rank to optical rank and to the DD-P0 census (Lorentzian Q + mode count). Save to data/results/desk/DD-P1/.

**Success:** crossbar cell×mode H reaches **effective rank ≥6**; optical cross-check agrees (SNR ≥20 dB, both nulls clean, ≥24 spots, equal-or-better mode count/Q). **Kill:** both the crossbar grid and the optical scan stay ≤ rank-2 after effort ⇒ neither path delivers independent channels at desk scale; document and defer true rank-N to MEMS.

**Data path:** `data/results/desk/DD-P1/`. **Time:** 2–3 sessions build/align + 1 scan session. **Safety:** laser enclosure + eyewear.

---

## Phase 2 — FPGA Streaming Lock-In Loop _(breaks B2; base for R9)_

**Objective:** Replace the ~8 Hz block-capture loop with a continuous kHz lock-in stream so τ/T_symbol ≈ 1 and the volatile modal tier becomes accessible — the prerequisite for temporal computation. **Status outcome:** MEASURED (loop rate is a direct timing measurement).

**Prerequisites:** Phase 1 (optical readout into Red Pitaya IN1).

**Materials:** Red Pitaya (DD1), PyRPL or SCPI, optical head from Phase 1.

**Procedure:**

1. Configure the Red Pitaya as a multi-channel lock-in: OUT1 drives a carrier at a chosen mode `f_m`; two IQ demodulators reference `f_m` and return in-phase/quadrature → amplitude+phase envelope at baseband.
2. Set demod bandwidth ≈ 3/τ for the mode under test (τ from Phase 0/1 Q). Verify the envelope responds within one τ to a drive step (toggle OUT1 amplitude, watch the envelope rise/fall time).
3. **Loop-rate measurement:** stream the envelope continuously to the host; measure sustained sample-to-host rate. Target ≥1 kHz effective symbol rate (vs the ~8 Hz block loop).
4. **Multi-mode:** instantiate one IQ demodulator per strong mode (up to the board's logic budget); confirm independent envelopes per mode under simultaneous multi-tone drive (no cross-talk beyond Phase 0 linearity).
5. Log a continuous 60 s stream; confirm no dropped samples and stable phase lock (σ_phase < project's 0.28 rad bench figure).

**Verification checks:** envelope step-response ≈ τ; sustained loop ≥1 kHz; phase lock stable over 60 s.

**Agent prompt:**

> Stand up the Red Pitaya streaming lock-in. Drive plate D1 at f_m on OUT1; demodulate with an IQ block at f_m (bandwidth ≈ 3/τ). Measure: (a) envelope rise/fall time vs a drive-amplitude step — should ≈ τ; (b) sustained envelope sample rate to host over 60 s — report mean and dropped-sample count; (c) phase-lock stability (σ_phase). Then add demodulators for the next two strong modes and confirm independent envelopes under simultaneous drive. Save streams + timing to data/results/desk/DD-P2/.

**Success:** sustained ≥1 kHz loop; envelope tracks τ; phase σ < 0.28 rad; independent per-mode envelopes. **Kill:** loop cannot exceed ~100 Hz sustained ⇒ temporal demos (Phase 8 reservoir) blocked; document the bottleneck (host I/O vs FPGA) and escalate to a second board or on-FPGA buffering.

**Data path:** `data/results/desk/DD-P2/`. **Time:** 1–2 sessions.

---

## Phase 3 — Diversified Cartridge, Single-Capture FDM Readout _(array addressing)_

**Objective:** Read the whole 8-plate array in one capture by frequency-division multiplexing — the efficient addressing that makes the array a processor, not a serial scanner. **Status outcome:** MEASURED.

**Prerequisites:** Phases 0 (diversified cartridge, band-separated), 1, 2.

**Procedure:**

1. Load the diversified cartridge `D1…D8`. From the Phase 0 census, assign each plate its band and pick one strong "tag" mode per plate.
2. Broadcast a multi-tone drive on the shared TX rail exciting all 8 tag modes simultaneously (Pico NCO + Red Pitaya OUT, or a composed waveform).
3. With a single optical pickup (one galvo spot positioned to see several plates, or a wide-field PD), capture one wideband spectrum.
4. Demodulate all 8 tag bands in parallel (Phase 2 lock-in bank). Confirm each plate's amplitude is recovered cleanly from the one capture.
5. **Crosstalk test:** drive only `D3`; confirm the other 7 bands stay at baseline (< 2σ). Repeat per plate — builds the 8×8 isolation matrix.
6. **Addressing benchmark:** time a full 8-plate readout via (a) relay switching vs (b) single-capture FDM. Record the speedup.

**Verification checks:** all 8 plates recovered in one capture; off-band crosstalk < 2σ; FDM materially faster than relay.

**Agent prompt:**

> Validate single-capture FDM on the diversified cartridge. Broadcast the 8 tag-mode tones; take one wideband capture; demodulate all 8 bands and report recovered amplitude per plate. Then drive each plate alone and report the 8×8 crosstalk matrix (off-diagonal in σ). Time a full array read by relay vs FDM. Save to data/results/desk/DD-P3/.

**Success:** 8/8 plates separated in one capture; off-diagonal crosstalk < 2σ; FDM ≥5× faster than relay. **Kill:** bands cannot be separated (crosstalk > 5σ) ⇒ insufficient diversification; re-tune cartridge or fall back to relay/galvo time-mux (documented constraint, not a failure).

**Data path:** `data/results/desk/DD-P3/`. **Time:** 1 session.

---

## Phase 4 — Content-Addressable Memory (Parallel Associative Search) _(rung R2; the headline demo)_

**Objective:** Store one template per plate; broadcast a query; the matching plate rings loudest — parallel nearest-neighbor search in one acoustic cycle. The array _is_ the CAM. **Status outcome:** MEASURED at rank-2 single-plate; OPEN as a multi-plate parallel demo.

**Prerequisites:** Phases 0–3.

**Procedure:**

1. **Enroll:** for each plate `D1…D8`, define its stored template as its tag-mode amplitude signature (its Phase 0 fingerprint). Record the enrolled template set.
2. **Query:** compose a drive whose spectral content matches one target plate's template (e.g. target `D5`). Broadcast on the shared rail.
3. **Single-shot readout:** one FDM capture (Phase 3). Score each plate by overlap (normalized dot product) between its response and the query.
4. **Argmax:** the highest-scoring plate is the match. Confirm it is the target. Record the margin (top score vs runner-up, in σ).
5. **Sweep:** repeat for all 8 plates as target, and for noisy queries (10%, 20% amplitude noise). Build the 8×8 confusion matrix and a margin-vs-noise curve.
6. **Capacity probe:** add near-duplicate templates (two plates tuned close) and find where margin collapses.

**Verification checks:** correct argmax for all 8 clean queries; graceful margin degradation with noise; one-capture operation (no per-plate serial readout).

**Agent prompt:**

> Run the array CAM demo. Enroll D1–D8 templates from their DD-P0 fingerprints. For each target plate, broadcast a matching query, take one FDM capture, score all plates by normalized overlap, and report argmax + margin (σ). Sweep all 8 targets and noise levels 0/10/20%. Output the confusion matrix and margin-vs-noise curve to data/results/desk/DD-P4/.

**Success:** 8/8 correct argmax at 0% noise; ≥6/8 at 10%; clear margin ranking. **Kill:** argmax no better than chance, or requires serial per-plate readout ⇒ the array is a memory bank but not a single-shot CAM; report as sequential search.

**Data path:** `data/results/desk/DD-P4/`. **Time:** 1–2 sessions.

---

## Phase 4A — Hybrid Logic / HD Compute _(general compute via associative path; architecture §7A)_

**Objective:** Demonstrate general compute at desk scale using the associative/HD architecture: wave interference as the compute primitive, the plate array as a physical codebook (permanent ROM), the crossbar as an address bus, and the FPGA threshold as the 1-bit decision layer. No MEMS dependencies. No gates, latches, or signal cascading through the medium. **Status outcome:** ARCHITECTURAL → DEMONSTRATED.

**Prerequisites:** Phases 0–4 (need crossbar + census + CAM working).

**Materials:** existing crossbar array (DD20/21), Red Pitaya (DD1), diversified cartridge (8 plates censused). No new BOM items.

**Conceptual framing (read before building):**

The compute model is NOT "build gates and latch them." It is:

1. Each plate's eigenmode spectrum is a permanent, read-only entry in a physical lookup table.
2. Computation = interference on selected plates → FPGA threshold → result selects which plate(s) to address next.
3. No signal ever "passes through" a gate chain. Each drive is fresh from the DAC at full power.
4. Q limits only clock speed (ring-up time), not cascade depth.
5. Storage is the plate's existence — no write, no refresh, no power.

**Procedure — Part A: Boolean gates via spectral interference:**

1. **AND gate.** Select plate D1 via crossbar. Drive mode $f_1$ (encodes input A) and mode $f_2$ (encodes input B) simultaneously. Read a cell at a location where both mode shapes have antinodes (identify from the Phase 0/1 mode-shape map). The cell responds strongly only when BOTH modes are driven (constructive overlap). FPGA threshold: output = 1 iff response > T (calibrated between "one mode" and "both modes" amplitudes). Record the truth table:

   | A (f₁ driven) | B (f₂ driven) | Cell amplitude | Threshold output |
   | ------------- | ------------- | -------------- | ---------------- |
   | 0             | 0             | noise          | 0                |
   | 1             | 0             | moderate       | 0                |
   | 0             | 1             | moderate       | 0                |
   | 1             | 1             | high           | 1                |

2. **OR gate.** Same setup, lower threshold T' (set between "neither mode" and "one mode" amplitudes). Output = 1 iff either or both modes driven.

3. **NOT gate.** Drive mode $f_1$ continuously as a reference. Input = additional drive at anti-phase (π offset). Destructive interference drops amplitude below threshold → output = 0 when input = 1. (Alternatively: FPGA simply inverts the threshold comparator output.)

4. **Verification:** run all four truth-table entries for AND, OR; both entries for NOT. Confirm clean separation (≥ 3σ between the threshold and both sides).

**Procedure — Part B: Cascaded LUT (multi-step computation):**

5. **Two-gate cascade.** Gate 1 (AND) on plate D1 produces a thresholded result (0 or 1). The FPGA maps that result to a crossbar address:
   - Result = 1 → select plate D3 (drive its modes → read response)
   - Result = 0 → select plate D5 (drive its modes → read response)

   This is a single IF/THEN/ELSE executed in glass: the interference decides, the crossbar routes. Each stage is at full DAC power — no signal decay.

6. **Three-stage LUT cascade.** Chain: plate D1 (compute) → threshold → selects D3 or D5 → compute on selected plate → threshold → selects D2 or D7 → read final result. This is a 3-deep decision tree with 8 possible paths — entirely determined by the physical spectra of the plates in the array.

7. **Verify unlimited depth.** Run a 5-stage and 10-stage cascade. Confirm that SNR at stage N is identical to stage 1 (because each drive is fresh). Plot threshold margin vs stage number — it should be flat. This is the definitive proof that Q does not limit cascade depth.

**Procedure — Part C: Full compute cycle (Von Neumann equivalent):**

8. **Fetch:** read the "instruction" from the codebook by exciting plate D1 and measuring its strongest mode index → this IS the opcode (mode 1 = ADD, mode 2 = SUB, etc. — the mapping is arbitrary and defined in software).

9. **Execute:** based on the opcode, the FPGA selects the "operand plates" (e.g., D3 and D4), drives them simultaneously, reads the interference result → this IS the arithmetic (the physical overlap encodes the operation).

10. **Store:** the result maps to an address (threshold → binary → select plate D_result). That plate's pre-existing spectrum IS the "stored" answer. No write needed — the glass already embodies it.

11. **Loop:** the stored plate's strongest mode encodes the next opcode. Repeat.

12. **Demonstrate:** program a 2-bit adder or a simple 4-state FSM as a cascade of plate selections. Run it, record the sequence of plate addresses visited and the final result.

**Verification checks:**

- AND/OR truth tables have ≥ 3σ separation at threshold
- Cascade depth 5 and 10 show flat margin (no degradation)
- 2-bit adder produces correct sums for all 4 input pairs (00+00, 01+01, 10+10, 11+01)
- FSM visits correct state sequence for a given input pattern

**Agent prompt:**

> Run the HD compute demo (Phase 4A). Part A: demonstrate AND, OR, NOT gates on plate D1 using dual-mode interference + FPGA threshold. For AND: drive modes f₁, f₂ together and separately; read cell response; confirm truth table with ≥3σ separation. Part B: cascade — use the AND result (0/1) to select between plates D3/D5 via crossbar, then compute on the selected plate and threshold again. Run 1-, 3-, 5-, and 10-stage cascades; plot margin vs depth. Part C: program and run a 2-bit adder as a plate-selection cascade. Save all results to data/results/desk/DD-P4A/.

**Success:** (1) All Boolean truth tables correct at ≥ 3σ; (2) margin vs cascade depth is flat (no Q-limited degradation); (3) 2-bit adder correct for all inputs. **Kill:** threshold margin at depth 1 is < 2σ ⇒ cell placement doesn't resolve mode overlap cleanly enough; requires finer spatial mapping or different cell/mode pairing.

**Data path:** `data/results/desk/DD-P4A/`. **Time:** 2–3 sessions.

### Part D: Gradient Mode — Physical Kernel Machine (Level 3, architecture §7B)

**Objective:** Demonstrate that the full N-dimensional response gradient (not just argmax) constitutes a physical kernel evaluation, enabling classification, regression, interpolation, and iterative dynamics — a neural inference engine on glass.

**Conceptual framing:** Parts A–C threshold the response into discrete bits (Level 2). Part D keeps the **full amplitude vector** across all plates — the continuous similarity landscape. One broadcast → one capture → N real-valued kernel outputs. That's the expensive step in any kernel method, done physically in one cycle.

**Procedure — Part D1: capture and characterize the gradient:**

13. **Baseline gradient map.** Define 8 "canonical queries" (one matched to each plate's tag mode). For each query, broadcast and capture the FULL response of ALL 8 plates (not just the target). Record the 8×8 **kernel matrix** $K_{ij} = \text{response of plate } j \text{ to query } i$. This matrix IS the physical Gram matrix of the codebook.

14. **Gradient structure.** Verify that $K$ is:
    - Diagonal-dominant (each plate responds most to its own query) — confirms §7A argmax works.
    - Off-diagonal values are NOT zero — confirms spectral overlap exists, i.e., the gradient carries information.
    - Roughly symmetric ($K_{ij} \approx K_{ji}$) — confirms the kernel is well-behaved.
    - Rank ≥ 6 (SVD of $K$) — confirms the plates span a high-dimensional feature space.

15. **Interpolation test.** Construct a query that is a 50/50 mix of plate D1's and plate D3's tag modes. Broadcast. Confirm the gradient peaks at both D1 and D3 with comparable amplitudes, and that the response is NOT just argmax(D1) — the gradient encodes "between D1 and D3."

**Procedure — Part D2: kernel regression (learn a function on the gradient):**

16. **Training set.** Define a target function over the 8 queries: e.g., $t = [0, 1, 1, 0, 1, 0, 0, 1]$ (arbitrary binary labels for a classification task) or $t = [0.1, 0.4, 0.9, ...]$ (regression targets).

17. **Collect kernel responses.** For each of M training queries (the 8 canonical + 8 mixed queries = 16 total), broadcast and capture the 8-plate gradient → assemble $\mathbf{Y} \in \mathbb{R}^{16 \times 8}$.

18. **Solve readout weights.** Compute $\mathbf{w} = (\mathbf{Y}^T\mathbf{Y} + \lambda I)^{-1}\mathbf{Y}^T\mathbf{t}$ (ridge regression, $\lambda = 0.01$). Store $\mathbf{w}$ (8 floats).

19. **Test inference.** For 8 NEW queries (unseen mixes, noise-perturbed versions):
    - Broadcast → capture gradient $\mathbf{y}$
    - Compute $\hat{t} = \mathbf{w}^T \mathbf{y}$
    - Compare $\hat{t}$ to ground truth.
    - Report classification accuracy (binary) or RMSE (regression).

20. **Multi-task.** Train a SECOND weight vector $\mathbf{w}_2$ for a different task (e.g., "is the query in the top half of the frequency range?"). Show the SAME kernel evaluation serves BOTH tasks — only $\mathbf{w}$ changes.

**Procedure — Part D3: iterative dynamics (Hopfield retrieval):**

21. **Corrupt a query.** Take plate D5's tag mode, add 30% noise (random amplitude perturbation on each frequency component).

22. **Iterate.** Broadcast the corrupted query → capture gradient → normalize to unit sum → USE the gradient AS the next drive vector (i.e., drive each plate at its response amplitude from the previous cycle). Repeat for 10 cycles.

23. **Convergence.** Plot the gradient vector at each cycle. Confirm it converges (Euclidean distance between successive gradients → 0). Confirm the fixed point peaks at D5 — the system "cleaned up" the noisy query and recovered the correct plate.

24. **Convergence speed.** Report cycles-to-convergence (defined as $\|\mathbf{y}_{t+1} - \mathbf{y}_t\| < 0.01$). Typical: 3–8 cycles.

**Verification checks:**

- Kernel matrix K is diagonal-dominant, rank ≥ 6, approximately symmetric
- Interpolation query produces proportional responses (not argmax collapse)
- Regression RMSE on unseen queries < 0.2 (on [0,1] targets)
- Classification accuracy ≥ 87% (7/8 correct on unseen queries)
- Multi-task: same kernel, different $\mathbf{w}$, both tasks correct
- Hopfield iteration converges in ≤ 10 cycles and recovers correct plate from 30% noise

**Agent prompt:**

> Run Part D (gradient mode). D1: broadcast 8 canonical queries (one per plate tag mode) and capture ALL 8 plates' responses for each → build the 8×8 kernel matrix K. Report SVD rank, diagonal dominance, symmetry. D2: train a ridge-regression readout on 16 queries (8 canonical + 8 mixed), test on 8 unseen queries, report accuracy. D3: corrupt plate D5's query with 30% noise, iterate (gradient → normalize → re-drive) for up to 10 cycles, report convergence curve and whether it recovers D5. Save to data/results/desk/DD-P4A/gradient/.

**Success:** (1) K is rank ≥ 6, diagonal-dominant, symmetric within 10%; (2) classification ≥ 87% on unseen queries; (3) Hopfield converges in ≤ 10 cycles and recovers correct plate at ≥ 30% noise. **Kill:** K has rank ≤ 2 (plates are spectrally degenerate — the codebook is too small / too similar) ⇒ diversify the cartridge further, or add plates.

**Data path:** `data/results/desk/DD-P4A/gradient/`. **Time:** 1–2 sessions (after Parts A–C working).

---

## Phase 5 — Surface Perturbation Write/Read/Erase _(rung R1; mirrors WL-A2)_

**Objective:** Demonstrate the write mechanism — a mass dot shifts a plate's modes by a position-coded, reversible amount (Rayleigh). **Status outcome:** OPEN.

**Prerequisites:** Phases 0–2 (need fine-frequency tracking).

**Materials:** wax putty (owned), precision scale (WL #9), one diversified plate.

**Procedure:**

1. Weigh 3 putty dots: 10, 25, 50 mg (record exact). Choose one plate `D4`.
2. Baseline: fine-sweep the top 8 modes (±2 kHz, 10 Hz steps) ×5 for per-mode σ. Optical readout (Phase 1) preferred — no added receive mass.
3. Apply 50 mg at plate center. Re-sweep. Track each mode's Δf by Lorentzian fit.
4. Remove; re-sweep; confirm return to baseline (< 0.5σ residual).
5. Repeat at corner and quarter-point positions — confirm **different positions give different shift vectors**.
6. Dose–response at center: 25 mg then 10 mg.
7. Compare measured Δf/f against Rayleigh prediction Δf/f = −½ ΔM_eff/M using mode shapes.

**Verification checks:** shifts > 3σ at ≥10 mg; position-distinguishable shift vectors; clean reversal.

**Agent prompt:**

> Run the desk surface-write protocol on D4. Baseline fine-sweep (top 8 modes, ±2 kHz/10 Hz, ×5) via optical readout; then for each placement I announce (50 mg center / removed / 50 mg corner / 50 mg quarter / 25 mg center / 10 mg center) re-sweep and fit Δf per mode. Report Δf vs baseline σ, position-distinguishability of shift vectors, reversal residual, and Rayleigh comparison. Save to data/results/desk/DD-P5/.

**Success:** > 3σ shifts at ≥10 mg; position-coded; reversible; Rayleigh-consistent. **Kill:** < 3σ at 10 mg ⇒ write mechanism not demonstrable at this scale; demote to 50 mg+ sensing or to MEMS lithographic write.

**Data path:** `data/results/desk/DD-P5/`. **Time:** 2–3 h.

---

## Phase 6 — Identical Cartridge → PUF Metrics _(rung R2; mirrors WL-B3)_

**Objective:** Across nominally identical plates, show each has a unique, stable spectral fingerprint — standard PUF uniqueness/reliability/uniformity. **Status outcome:** OPEN (single-device fingerprinting MEASURED; multi-device metrics pending).

**Prerequisites:** Phases 0 (identical cartridge), 1, 2.

**Procedure:**

1. Load identical cartridge `I1…I8` (addressed by relay/galvo — they share bands by design).
2. Per plate: full fine census ×3, then a power-cycle, then a 3rd census (intra-device repeatability).
3. Define a binary fingerprint: mode-presence bits + quantized frequency offsets.
4. Compute inter-device fractional Hamming distance (uniqueness, target ~50%), intra-device HD (reliability, target <5%), and bit uniformity (~50%).
5. Cross-acceptance: query each plate against every other's template (all 56 ordered pairs); count false accepts.
6. Optional: re-census after 24 h / temperature change for drift.

**Verification checks:** inter-HD 40–60%; intra-HD <5%; zero cross-acceptance.

**Agent prompt:**

> Run the desk PUF study on I1–I8. For each plate: fine census ×3 → power cycle → census. Build binary fingerprints (mode presence + quantized offsets). Report inter-device and intra-device fractional Hamming distances, uniformity, and the 56-pair false-accept/false-reject table. Save to data/results/desk/DD-P6/ with a uniqueness histogram.

**Success:** inter-HD 40–60%, intra-HD <5%, zero cross-acceptance. **Kill:** inter-device frequencies match within intra-device variation ⇒ fingerprints geometry-dominated, not variance-dominated; salvage as serial-number ID only.

**Data path:** `data/results/desk/DD-P6/`. **Time:** 1 session/plate + 1 analysis day.

---

## Phase 6B — Classical Non-Separability & Coherent Phase Switch _(rung R5; mirrors WL-C1 / WL-B9)_

**Objective:** Reproduce the classical "quantum-like" results on the array: (a) frequency×space non-separability (CHSH-style S > 2, already MEASURED at S = 2.83 on the bench) and (b) a coherent phase switch (phase-controlled constructive/destructive gating, WL-B9). **Status outcome:** MEASURED (CHSH) → extended (3-DOF and phase switch are OPEN).

**Prerequisites:** Phases 0, 1 (two readout points). Phase-locked drive via Pico NCO `PHASE:` (two FPGA DACs are nicer but not required).

**Materials:** two phase-locked drive channels (Pico NCO GP2+GP3 via `PHASE:`, or two FPGA DACs); two readout points (crossbar cells or optical spots).

**Procedure — non-separability (CHSH):**

1. Pick a plate and two strong modes f1, f2; two readout positions (e.g. NW, NE cells).
2. Build the frequency×space intensity matrix: for each (mode, position) capture amplitude (and phase if available).
3. Compute the CHSH-analog S with **fixed** Bell angles (0°/22.5°/45°/67.5°) — no optimization.
4. Report S per mode-pair with bootstrap CI.

**Procedure — coherent phase switch (WL-B9):**

5. Drive mode A from two phase-locked sources; sweep relative phase 0→360° in 10° steps.
6. At each phase capture mode-A amplitude; report contrast = max/min (constructive vs destructive).
7. **Null:** lift/detune one drive source; re-sweep; confirm the contrast is acoustic interference, not electrical summing (acoustic contrast must exceed the electrical-null contrast by >5×).

**Verification checks:** fixed-angle S > 2 on ≥1 mode-pair with CI clear of 2; phase-switch contrast > 5× over the electrical null.

**Agent prompt:**

> Run the desk non-separability + phase-switch demo. (1) CHSH: build the frequency×space matrix for 2 modes × 2 readout points; compute fixed-angle S with bootstrap CI. (2) Phase switch: drive mode A from two phase-locked sources, sweep relative phase 0–360°, report amplitude-vs-phase and contrast = max/min; run the lifted-source null. Save to data/results/desk/DD-P6B/.

**Success:** fixed-angle S > 2 (CI clear of 2); phase-switch contrast > 5× over null. **Kill:** S < 2 fixed-angle ⇒ describe as geometry only (no inequality language); no phase contrast ⇒ coherent switch deferred to MEMS.

**Data path:** `data/results/desk/DD-P6B/`. **Time:** 1 session (CHSH reuses the existing WL-A3 analysis path).

---

## Phase 7 — Vacuum + Electronic Q-Control _(toward rung R10)_

**Objective:** Reach the high-Q regime the parametric demos need, by removing gas damping (vacuum) and synthesizing effective Q via velocity feedback. **Status outcome:** PROJECTED (Q-boost at desk scale is plausible and easier than at MEMS scale — large loop-delay margin).

**Prerequisites:** Phases 1, 2 (optical readout + fast feedback loop).

**Materials:** bell jar + diaphragm pump (DD12), Red Pitaya PID/feedback.

**Procedure — vacuum:**

1. Place one plate + its optical readout under the bell jar (or the whole rack if it fits). Feed the laser through a window; keep the PD inside or use a window pass.
2. Measure intrinsic Q (ringdown or Lorentzian) at atmosphere, then at successive pump-downs. Plot Q vs pressure; expect Q to rise as gas damping falls.

**Procedure — electronic Q-control:**

3. Close a velocity-feedback loop in the Red Pitaya: read the mode envelope (Phase 2), phase-shift +90°, feed back into OUT1 drive with adjustable gain.
4. Positive feedback cancels damping → synthesized higher effective Q; negative → damping (useful for fast reset). Sweep gain; measure effective Q via ringdown at each setting.
5. **Stability guard:** approach self-oscillation slowly; the loop must stay below the oscillation threshold for Q-boost (above it = an oscillator, which is Phase 8's tool, not this one). Log the gain margin.

**Verification checks:** Q rises monotonically with vacuum; Q-control gives controllable effective Q with a measured stability margin.

**Agent prompt:**

> Characterize Q vs pressure and Q vs feedback gain on the bell-jar plate. (1) Ringdown Q at atmosphere and ≥3 vacuum levels — plot Q vs pressure. (2) Close the +90° velocity-feedback loop; sweep gain; report effective Q per gain and the gain margin to self-oscillation. Save to data/results/desk/DD-P7/.

**Success:** vacuum raises Q toward ≥5×10³; Q-control adds controllable boost with a documented stability margin. **Kill:** Q stays < 5×10³ even in vacuum + boost, and the loop self-oscillates before useful boost ⇒ parametric Ising (Phase 8) needs the quartz-fork module (DD13) instead of plates.

**Data path:** `data/results/desk/DD-P7/`. **Time:** 2–3 sessions. **Safety:** vacuum implosion risk — rated chamber, stand clear on first pump-down.

---

## Phase 8 — Parametric Pump + Programmable Coupling (Phononic Ising) _(rungs R10–R11; mirrors WL-E1/E2)_

**Objective:** Drive modes (or forks) above the parametric threshold so each becomes a bistable 0/π phase state (a spin); couple them with a programmable J; show the network relaxes to low-energy configurations of a small QUBO/MaxCut. **Status outcome:** PROJECTED — the frontier rung.

**Prerequisites:** Phase 7 (high Q). Fork module (DD13) is the fallback high-Q substrate.

**Procedure — single spin first:**

1. Pick a high-Q mode `f_m` (plate in vacuum, or a tuning fork). Pump at 2·f_m, ramp amplitude slowly.
2. Watch for the parametric threshold knee: a sub-harmonic response appears at `f_m` that settles to one of two phases (0 or π), flipping randomly between runs. That bistability **is** one spin.
3. Map threshold vs Q; confirm it matches the Mathieu prediction (gain ≥10 dB at ε<0.1 in the first tongue).

**Procedure — coupled network:**

4. Build ≥4 spins (4 forks or 4 high-Q modes). Implement **electronic coupling** in the Red Pitaya: read spin i's phase, weight by J_ij, inject into spin j's pump — fully programmable J in software (preferred over physical bridges).
5. Encode a small known MaxCut/QUBO instance in J. Initialize randomly; pump all spins above threshold; let the network settle; read out the phase configuration.
6. Repeat ×100 from random starts; histogram the solutions; compare the most frequent configuration to the known ground state.

**Verification checks:** single-spin bistability with a clean threshold; coupled network settles to the correct ground state above chance.

**Agent prompt:**

> Run the phononic Ising protocol. (1) Single spin: pump a high-Q mode at 2f, ramp amplitude, report the threshold knee and 0/π phase-flip statistics over 50 runs. (2) Build a 4-spin network with electronic J coupling encoding a named MaxCut instance; run 100 random-start settles; histogram phase configurations and report ground-state hit rate vs chance. Save to data/results/desk/DD-P8/.

**Success:** stable 0/π bistability at threshold; 4-spin network hits the known ground state well above chance. **Kill:** no parametric threshold at max safe drive even at high Q ⇒ Ising arc needs Q > 10⁵ (cryo/crystalline); publish distance-to-threshold and hand off.

**Data path:** `data/results/desk/DD-P8/`. **Time:** multi-session. **Safety:** high-amplitude drive — watch PZT/am, thermal.

---

## Phase 9 — Volumetric Laser Write _(rung R6; tests S21 simulation)_

**Objective:** Write a density perturbation _inside_ the glass with a focused laser and read the resulting eigenfrequency shift — turning the 2D surface register into a 3D mode-tensor memory. **Status outcome:** SIMULATED (S21) → OPEN at bench.

**Prerequisites:** Phases 1, 2 (read shifts), Phase 5 (surface-write baseline for comparison).

**Materials:** engraving laser (DD14) in an interlocked enclosure, a sacrificial plate.

**Procedure:**

1. Baseline fine census of a sacrificial plate.
2. Focus the laser to a point inside the glass volume (not the surface); make a single controlled inscription (lowest energy that produces a measurable change — start Type I densification regime).
3. Re-census; fit Δf per mode.
4. Inscribe additional sites at different depths/positions; confirm each adds a position-coded shift, and that volumetric sensitivity follows the same sin² profile as surface mass (H-V1, R² ≥ 0.99 target).
5. Compare write resolution and shift magnitude to the Phase 5 surface result.

**Verification checks:** measurable Δf from an internal site; volumetric/surface sensitivity profiles agree (R² ≥ 0.99).

**Agent prompt:**

> Run the volumetric-write test on the sacrificial plate. Baseline census; after each laser inscription I announce (depth/position), re-census and fit Δf per mode. Report shift magnitude vs inscription energy, position-coding, and the volumetric-vs-surface sensitivity R². Save to data/results/desk/DD-P9/.

**Success:** internal inscription produces > 3σ position-coded shifts; volumetric sensitivity matches surface (R² ≥ 0.99). **Kill:** no measurable shift at safe laser energy, or R² < 0.99 ⇒ volumetric write not demonstrable at desk scale; keep surface-only.

**Data path:** `data/results/desk/DD-P9/`. **Time:** 2–3 sessions. **Safety:** DD14 is Class 4 — interlocked enclosure, eyewear, fume extraction; never open-air.

---

## Phase 10 — Full Integration: One Host, the PFU Instruction Set _(rungs R8→R11; substrate unity)_

**Objective:** Run all functions from one host through the CWM instruction set ([CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) §3) across the same rack — sensor, memory, fingerprint, feature map, optimizer in one orchestrated demonstrator. **Status outcome:** the integration thesis; each underlying function carries its own phase's label.

**Prerequisites:** all prior phases that passed their gate.

**Procedure:**

1. Wrap each phase's routine as a Level-2 instruction: `FINGERPRINT()` (P6), `PROJECT(x)` (P1/P3), `MATCH(q)` (P4), `PERTURB_READ()` (P5), `RESERVOIR(stream)` (P2 envelope), `OPTIMIZE(J)` (P8).
2. Build a single host script that runs a scripted demo: enroll → fingerprint → write → read → search → (optional) optimize, on the same loaded cartridge, logging every step.
3. **Repeatability run:** execute the full sequence 10× from a cold start; confirm deterministic outcomes (within each function's measured margin).
4. Produce a single timestamped report bundling all phase results + the manifest — the shareable artifact.

**Verification checks:** the full sequence runs unattended end-to-end; results reproduce across 10 cold starts.

**Agent prompt:**

> Run the integrated desk demonstrator. Execute the scripted sequence FINGERPRINT → PERTURB_WRITE → PERTURB_READ → MATCH (and OPTIMIZE if Phase 8 passed) on the loaded cartridge, 10× from cold start. Report per-step success against each phase's criterion and overall determinism. Bundle everything into data/results/desk/DD-P10/report/ with the manifest and git SHA.

**Success:** end-to-end sequence reproduces across 10 runs within each function's margin. **Kill:** none — integration surfaces which functions are robust and which need rework; that map is the deliverable.

**Data path:** `data/results/desk/DD-P10/`. **Time:** 1–2 sessions once prior phases pass.

---

## Phase S — 3D Stack Assembly (optional; the packed-array model) _(§3.2 of the build spec)_

**Objective:** Stack several finished crossbar planes into a 3D `(layer, row, col)` array — the desk-scale analog of stacked/packed MEMS dies. Run any plane-level phase (P3/P4/P6/P8) on the stack to show the architecture survives 3D packing. **Status outcome:** the underlying phase keeps its own label; stacking adds packing-topology fidelity, not a new physics claim.

**Prerequisites:** ≥2 planes built and censused flat (Phase 0). Crosspoint/relay addressing working (Phase 1 primary path).

**Procedure — assembly:**

1. Mount each plane on **nodal-point standoffs** (sorbothane/foam pads, DD23, at the 0.224 L / 0.776 L nodal lines) carried on **corner nylon rods** (DD22), outside the active area. Planes must not rigidly touch.
2. Run the **vertical IDC ribbon bus** (DD24) up the stack: shared row/col lines tapped by every plane; a **layer-select** stage (owned relay mux or 2nd crosspoint, DD25) enables one plane at a time.
3. Address test: select each `(layer, row, col)` in turn; confirm you reach the intended cell and read its census modes (planes were characterized flat in P0 — frequencies should match within drift).

**Procedure — isolation check (the make-or-break test):**

4. Drive one plane at a strong mode; capture the **adjacent planes'** response. Off-layer leakage must be low (target < 2σ above baseline) → confirms **isolated stack** (independent layers = packed memory model).
5. If you instead _want_ a **coupled stack** (3D reservoir/Ising), add a deliberate compliant bridge or electronic layer→layer feedback and _measure_ the inter-plane coupling rather than letting it be accidental.

**Verification checks:** every `(layer, row, col)` addressable; per-plane census frequencies preserved within drift; inter-plane leakage characterized (low for isolated; measured/controlled for coupled).

**Agent prompt:**

> Bring up the 3D stack. For each (layer, row, col) I name, select it via the layer-select + crosspoint and report the cell's top modes vs its flat DD-P0 census. Then the isolation matrix: drive each plane at a strong mode and report adjacent-plane leakage (σ above baseline) as an L×L matrix. Save to data/results/desk/DD-PS/ with the stack manifest (layer order, standoff type, bus map).

**Success:** full (layer,row,col) addressability; census preserved; isolated-stack leakage < 2σ (or, for the coupled build, a clean measured coupling constant). **Kill:** none — a stack that couples uncontrollably is a mounting-tolerance result; tighten standoffs or switch to the coupled-stack interpretation and measure it.

**Data path:** `data/results/desk/DD-PS/`. **Time:** 1 session assembly + 1 session characterization.

---

## Phase Dependency Map

```
P0 Census ──┬─ P1 Rank-N (crossbar + optical) ──┬─ P2 FPGA loop ──┬─ P3 FDM ── P4 CAM ── P4A HD Compute
            │                                 │                 │                           │
            │                                 │                 │                    (general compute ✓)
            │                                 │                 └─ (P2) ── P8 Ising ◄── P7 Vacuum/Q
            ├─ P5 Surface write ────────────┘                 │
            ├─ P6 PUF (identical cartridge) ────────────────┤
            ├─ P6B Non-separability + phase switch ───────┘
            ├─ P9 Volumetric write (needs P1,P2,P5)
            └─ Phase S 3D stack (≥2 planes) ──────────┐
                                   all passing ──► P10 Integration
```

**The primary (associative/HD) path to general compute: P0 → P1 → P2 → P3 → P4 → P4A.** This is 6 phases, zero MEMS dependencies, and proves general logic at desk scale via interference + threshold + crossbar routing.

Remaining Desk Minimum phases (P5, P6, P6B) add write/read, PUF, and non-separability — valuable science, but not required for the general-compute claim. The high-Q frontier (**P7 → P8**) and volumetric memory (**P9**) are the Briefcase-Full / Von Neumann upgrades; **Phase S** stacks the crossbar planes into the packed-array 3D model; then **P10** integrates whatever passed.

---

## Repeatability Checklist (attach to every shared dataset)

- [ ] `manifest.yaml`: plate IDs + differentiators, cartridge type, ambient T/humidity, all firmware/driver versions, git SHA, BOM revision.
- [ ] Raw captures (`.npz`) retained, not just fitted results.
- [ ] Null controls recorded where applicable (beam-blocked, drive-off, mass-removed).
- [ ] Per-mode σ from ≥5 baseline repeats before any claim of a shift.
- [ ] Pass/fail stated against the printed success/kill criterion, not eyeballed.
- [ ] Calibration tables (galvo angle→position, per-mode f₀/Q) included.
- [ ] Session `notes.md` with anything that deviated from this protocol.

---

## Cross-References

- Build spec, subsystems, BOM: [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md)
- Capability ceiling, rungs R0–R11, falsifiers: [FRONTIER_CEILING.md](FRONTIER_CEILING.md)
- Macro-bench experiment specs (WL-\*) and base BOM #1–#15: [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md)
- Instruction set executed by Phase 10: [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md)
- Claim maturity ledger: [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md)
