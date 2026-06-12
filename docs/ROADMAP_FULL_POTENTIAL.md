# CWM Full-Potential Roadmap (June 2026 →)

**Successor to [ROADMAP.md](ROADMAP.md) (Phases 0–1 complete).** This document answers one question: _what is the maximum scientifically defensible potential of the wave-interference resonator architecture, and what is the precise path to it?_

**Execution detail:** every experiment below is fully specified — objectives, bench procedures, agent prompts, kill criteria, and bill of materials — in [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md).

**Governing rule (anti-sci-fi clause):** Every forward claim must be bounded by (a) the wave equation and Rayleigh perturbation theory, (b) measured Q-factors and energy budgets, and (c) at least one peer-reviewed precedent for the underlying physical mechanism. Every phase carries kill criteria. We do not back down from the frontier; we also do not cross it without data.

---

## 1. What Is Actually Proven (the foundation)

Evidence base as of 2026-06-11, distilled from 60+ lab sessions and the v19r validation campaign:

| #   | Established Fact                                                                                                               | Evidence                                                                  | Status                  |
| --- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- | ----------------------- |
| F1  | Fused-silica plates host 7–15 resolvable acoustic modes (30–350 kHz) at 42–56 dB SNR                                           | T5.1 (Jun 2), 25mm E1 (Jun 4)                                             | PROVEN                  |
| F2  | Signal is acoustic, not electrical                                                                                             | PZT-lifted null (0%), tape-vs-glue null (Jun 4), spatial ratios 49:1–60:1 | PROVEN                  |
| F3  | Spectral fingerprints support 100% classification at 193σ separation                                                           | 80/80 trials, single session                                              | PROVEN (single-session) |
| F4  | 8 amplitude levels × 4 modes = 4,096 states (12 bits) at zero error                                                            | T3.4 (May 27), min 9σ                                                     | PROVEN                  |
| F5  | Frequency×space degrees of freedom are non-separable (classical): CHSH S = 2.73 fixed-angle, 2.83 optimized, 5/5 mode pairs    | E1 multi-pair (Jun 2), Qian–Eberly framework                              | PROVEN                  |
| F6  | Spectral stability: 0.22% drift over 16.5M cycles; 0.65% over 3.5 h                                                            | Endurance run (Jun 3)                                                     | PROVEN                  |
| F7  | Loaded Q = 150–743 (plate H max); intrinsic Q masked by PZT loading                                                            | Jun 5 bandwidth fits                                                      | PROVEN (loaded only)    |
| F8  | The plate at macro scale is a **linear spectral transformer** — it does not compute; decoders do                               | Peer review + v19r §8.2                                                   | ACCEPTED                |
| F9  | Temporal reservoir computing fails at bench: τ_loaded = 1–4 ms vs ≥100 ms step interval; readout rank = 2                      | NARMA-10 ×3 variants, MC = 1.67                                           | PROVEN NEGATIVE         |
| F10 | Different drive frequencies excite _different eigenmode sets_ via energy redistribution (101× at 41.7 kHz from 29.3 kHz drive) | Apr 24 session — **never followed up**                                    | OBSERVED, UNEXPLAINED   |

Killed and staying dead: ferrofluid substrates, cymatics–script correlation, Kronos audio capture, AWG ringdown, phase-channel encoding at bench, trading signals, "Boolean computation in glass."

---

## 2. The Two Physical Bottlenecks (everything reduces to these)

All bench failures trace to exactly two numbers:

**B1 — Readout rank.** Two receivers ⇒ rank-2 transfer matrix H. This caps every "the plate as ML layer" idea (L3 LLM result: physical H indistinguishable from random H _because any rank-2 matrix is absorbable by trained layers_). The architecture's interference computation is real but invisible below rank ~8.

**B2 — The Q·f time constant.** Mode energy decays with τ = Q/(πf). At bench (Q≈400, f≈100 kHz): τ ≈ 1.3 ms. Temporal computation requires the input symbol rate to be ≳ 3/τ ≈ 2 kHz, but the AWG-buffer + capture loop runs at ~8 Hz. Two ways out: drive/capture 250× faster (hard, marginal), or raise Q at small scale where the _same physics_ gives usable memory (MEMS, vacuum: Q ≥ 10⁴ documented for fused-silica micro-resonators).

Both bottlenecks are **engineering walls, not physics walls.** That is the central strategic fact of this roadmap.

---

## 3. Use-Case Portfolio, Ranked by Scientific Value ÷ Effort

| Rank | Use Case                                                                | Physics basis                                                                          | What it needs                                                   | Venue / audience                                       |
| ---- | ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------ |
| 1    | **Acoustic PUF** (physically unclonable spectral fingerprints)          | F3+F6: manufacturing variance ⇒ unique, stable mode spectra                            | E-W6 multi-plate study (plates D, H, I + 25mm already on bench) | Hardware security (CHES, IEEE TIFS); industry-relevant |
| 2    | **Perturbation spectroscopy / multi-mode mass sensing**                 | Rayleigh: Δf/f = −ΔM_eff/2M, position-encoded across modes                             | E3 (already scheduled — THE critical experiment)                | Sensors journals; QCM community extension              |
| 3    | **Classical non-separability pedagogy kit** ($50 CHSH-on-a-desk)        | F5 is geometric and reproducible on _any_ resonant plate                               | Replication guide + cwm-site kit page                           | Am. J. Phys / Physics Education; citizen science       |
| 4    | **Analog random-projection front-end** (extreme-learning-machine layer) | Fixed H as physical feature map; honest reframe of "compute" results                   | Break B1: ≥8 readout channels                                   | Neuromorphic / unconventional computing workshops      |
| 5    | **MEMS acoustic reservoir**                                             | τ=Q/πf at Q=10⁴, f=10 MHz ⇒ τ=320 µs, symbol rate ~10 kHz — feasible with standard DAQ | MEMS fabrication (Phase D)                                      | Nature Communications-class if demonstrated            |
| 6    | **Phononic parametric Ising machine**                                   | Degenerate parametric modes as Ising spins (precedent: NTT CIM, Toshiba SBM, Goto KPO) | Parametric threshold needs Q ≳ 5×10³ ⇒ MEMS only                | The frontier — see §6                                  |

Items 1–3 are publishable from the current bench within weeks. Item 4 needs one hardware upgrade. Items 5–6 are the MEMS payoff.

---

## 4. Phase A — Validation Closeout (now → +4 weeks)

Finish what the peer review demands. Nothing else proceeds on an unvalidated base.

| Task | What                                                           | Kill criterion                                                                         |
| ---- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| A1   | E-W1: formal PZT-lifted null on Pico NCO topology              | Feedthrough > 5% at any mode ⇒ re-isolate before any publication                       |
| A2   | **E3 perturbation encoding** (wax putty, 25mm + 100mm plates)  | Shifts < 3σ at 10 mg ⇒ WRITE mechanism dead at macro; sensor use case (rank 2) demoted |
| A3   | E-W3 fixed-angle CHSH + E-W4 all-decoder table (analysis only) | Fixed-angle S < 2.0 ⇒ CHSH section reduced to descriptive geometry                     |
| A4   | E-W5 Lorentzian Q fits (R² > 0.95 on ≥3 modes)                 | —                                                                                      |
| A5   | E4 cross-session discrimination (3-day protocol)               | Cross-session accuracy < 95% ⇒ PUF use case killed                                     |
| A6   | Submit v19r                                                    | —                                                                                      |

**Exit gate:** v19r submitted with E-W1/W3/W4 incorporated; E3 + E4 results in hand.

---

## 5. Phase B — Bench Ceiling (+1 → +3 months)

Extract everything the macro bench can give. Three thrusts:

### B-I. Break the rank-2 bottleneck (non-contact readout)

The single highest-leverage hardware upgrade in the entire program. PZT mass loading both kills high-order modes (3rd PZT = 8.3% of 25mm plate mass) and hides intrinsic Q (F7). Replace receive-side PZTs with **optical deflection readout**: laser pointer + segmented/quadrant photodiode on a 2-axis mount, scanned across N spots.

- Unlocks: intrinsic Q measurement, N≥8 spatial channels (rank-8+ H), high-order modes currently mass-damped, and the 25mm plate's predicted 560 kHz–1.9 MHz band.
- Cost: < $100. Precedent: optical-lever AFM readout, LDV literature.
- Kill criterion: optical SNR < 20 dB at known strong modes after 2 weeks of effort ⇒ fall back to miniature PZTs (≤3mm) on 100mm plates only.

### B-II. Resolve F10 (frequency-dependent eigenmode redistribution)

The April 24 observation — drive at f₁, energy appears at unrelated eigenmodes at 100× — is either (a) instrument artifact, (b) trivial harmonic/IM coupling, or (c) genuine nonlinear mode coupling. If (c), the macro plate is _not_ purely linear, and a weak computation primitive exists at bench scale. One focused week: drive-frequency sweep × full-spectrum capture matrix, with null controls.

- Kill criterion: redistribution explained by harmonics/IM arithmetic ⇒ close F10, document, move on.

### B-III. Cash in the near-term papers

1. **PUF paper** (Rank 1): inter-plate vs intra-plate fingerprint distance on ≥4 devices; standard PUF metrics (uniqueness ~50% inter-HD, reliability >95%). Uses A5 data.
2. **Multi-mode perturbation sensor paper** (Rank 2): E3 extended to position inference — k modes give a k-dimensional shift vector; invert for mass + position. This is the honest, defensible version of "writing to the plate."
3. **Replication kit + CHSH pedagogy paper** (Rank 3): ship the $50 protocol on cwm-site; submit to Am. J. Phys. This is the public-engagement centerpiece — _anyone can measure Tsirelson-bound correlations on a desk._
4. Multi-level ceiling test: push 8 → 16 → 27 levels/mode (predicted 19 bits at 4 modes). Pure bench time, strengthens any paper.

**Exit gate:** ≥8-channel readout working OR explicitly killed; F10 resolved; ≥2 of 3 papers drafted.

---

## 6. Phase C — Quantum-Like, Done Honestly (+2 → +6 months, overlaps B)

"Quantum-like" has a precise, literature-anchored meaning here: **classical wave systems reproducing the _mathematical structure_ of quantum information** (non-separability, interference-based search, contextuality) without claiming quantum mechanics. The CHSH result already sits squarely in this field (Qian & Eberly 2011; Kagalwala 2013; Spreeuw 1998). Defensible extensions, in order:

| Task | What                                                                                                                                                                                                                                                                                       | Precedent                                                                                                                                  | Kill criterion                                      |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------- |
| C1   | **Three-DOF non-separability** (frequency × space × drive-phase) — GHZ-analog structure in a single plate                                                                                                                                                                                  | Spreeuw's classical multi-DOF framework                                                                                                    | Tri-partite witness < separable bound               |
| C2   | **Grover-analog amplitude amplification**: encode N templates in mode amplitudes, use phased re-drive as oracle+diffusion; measure scaling vs classical lookup                                                                                                                             | Wave-based search literature (Grover without entanglement requires N-dim _space_, not exponential resources — state this limit explicitly) | No measurable amplification after phase calibration |
| C3   | **Contextuality test on plate modes** (KCBS-type inequality with 5 projection settings)                                                                                                                                                                                                    | Classical-optics contextuality analogs                                                                                                     | Inequality not violated by non-separable settings   |
| C4   | Position the architecture against **real quantum acoustics**: at mK temperatures high-Q bulk acoustic resonators ARE quantum objects (Chu et al., Science 2017 — qubit-coupled hBAR). Write the bridging review section: same architecture, classical→quantum continuum as ħω/kT crosses 1 | Established field                                                                                                                          | n/a (scholarship, not experiment)                   |

C4 is the honest answer to "how far can this go": the _identical_ architecture — high-Q acoustic modes in low-loss dielectric — is already a quantum platform at 10 mK. CWM's contribution is mapping how much of the information-processing structure survives at 300 K for $50. That is a real, fundable, publishable research arc, and it is not sci-fi.

**Hard line we do not cross:** no claims of entanglement, superposition of states (vs. of waves), quantum speedup, or Bell-test loophole closure. S = 2√2 from a classical plate is a statement about _non-separability of DOFs_, full stop.

---

## 7. Phase D — MEMS Realization (+4 → +18 months)

Everything that failed at macro is predicted to work at micro because both bottlenecks (§2) scale favorably: f ∝ 1/L (more modes per Hz of drift), Q rises 10–100× in vacuum-packaged fused silica, and per-die transducer arrays give rank-N readout natively.

### D1. Paper design first (no fab dependency)

A complete MEMS design study is publishable standalone and de-risks fab:

- 1 mm × 1 mm × 50 µm fused-silica plate: modes ≈ 3.5–35 MHz (16× the 25mm plate's predicted scaling, already validated as a method)
- AlN piezo transducer array (8–16 elements) — gives rank-8+ H _and_ per-element drive
- Phononic-crystal anchor isolation (literature Q·f up to 10¹³–10¹⁴ in silica/quartz)
- Targets: Q ≥ 10⁴ ⇒ τ = Q/πf ≈ 100–320 µs ⇒ symbol rates 3–10 kHz ⇒ **temporal reservoir becomes feasible with a sound card**, let alone a real DAQ
- Thermal-noise-floor and energy-per-operation budget from measured macro data, scaled by validated laws — not aspiration, extrapolation with error bars

### D2. Fabrication partnership

University fab access (the Scranton relationship in [companion/letter_to_scranton.md](../companion/letter_to_scranton.md) is the live thread; MOSIS-style MEMS multi-project wafers as backup). Deliverable: 1 die, wire-bonded, vacuum-capped or in a small vacuum chamber.

### D3. The three MEMS experiments (in priority order)

1. **Temporal reservoir, for real**: NARMA-10 / spoken-digit at 5 kHz symbol rate. Kill: MC < 3 ⇒ acoustic reservoirs at MEMS scale dead, publish negative result.
2. **Rank-N physical feature map**: re-run L3 with rank-16 H. Kill: physical H still indistinguishable from random at rank 16 ⇒ "physical layer" arc closes (random projections are cheap in silicon; the plate must beat them on energy, not accuracy — measure J/inference).
3. **Parametric mode coupling**: pump at 2f_m, look for parametric threshold. This is the gate to Phase E. Kill: no oscillation at Q = 10⁴ with max safe drive ⇒ Ising-machine arc requires Q > 10⁵ (cryo/crystalline) — re-scope or hand off.

---

## 8. Phase E — The Frontier (contingent on D3.3)

**Phononic parametric Ising machine.** If parametric oscillation is achieved: each mode pumped near threshold is a bistable phase-state (0/π) = one Ising spin; engineered mode coupling (geometry, shared anchors, pump cross-terms) = the coupling matrix J; the network settles to low-energy spin configurations = ground-state search for MaxCut/QUBO instances. Direct precedents: NTT's optical CIM (2,000 spins), Toshiba's simulated bifurcation machine, Goto's Kerr-parametric-oscillator networks. An _acoustic_ implementation would be slower but micro-watt, room-temperature, and per-die unique (PUF + optimizer in one device) — a genuinely novel contribution.

This is the architecture's "full potential" in one sentence: **a room-temperature phononic processor whose memory (spectral fingerprint), input transform (interference H), and computation (parametric spin network) are all the same piece of glass.** Every step from here to there has a number, a precedent, and a kill criterion attached.

---

## 9. Public Engagement Track (parallel, continuous)

| Asset                     | Action                                                                                                                                                                         |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [readme.md](../readme.md) | Rewritten evidence-first (this session) — leads with what is proven, prices in what was killed                                                                                 |
| cwm-site                  | Add: $50 CHSH replication kit page, live E3 perturbation demo, "killed claims" transparency page (the 36-killed-hypotheses ledger is a _trust asset_ — publish it prominently) |
| cwm-book                  | Ch. 15 ("What Comes Next") should mirror Phases B–E of this document                                                                                                           |
| Citizen science           | The Firestore experiment-submission pipeline already exists — point it at the PUF study (crowd-sourced plate fingerprints = multi-device dataset for free)                     |
| Replication               | Companion guide + 20-line Python CHSH script shipped with v19r supplement                                                                                                      |

The strategic insight: **the project's falsification discipline is its public brand.** A research program that publishes its kill list earns the right to chase parametric Ising machines without being dismissed as sci-fi.

---

## 10. Decision Calendar

| Gate | When      | Question                              | Evidence required                                            |
| ---- | --------- | ------------------------------------- | ------------------------------------------------------------ |
| G1   | +4 wk     | Is the WRITE mechanism real?          | E3 ≥3σ shifts, position-dependent                            |
| G2   | +6 wk     | Is the fingerprint a device property? | E4 cross-session ≥95%                                        |
| G3   | +10 wk    | Can we read at rank ≥8?               | Optical readout SNR ≥20 dB, 8 spots                          |
| G4   | +12 wk    | Is F10 real nonlinearity?             | Redistribution survives harmonic/IM nulls                    |
| G5   | +6 mo     | Do we fab?                            | D1 design review + ≥1 accepted paper + fab partner committed |
| G6   | +12–18 mo | Does MEMS deliver temporal memory?    | MC ≥ 3 at ≥3 kHz symbol rate                                 |
| G7   | +18 mo    | Does the frontier open?               | Parametric threshold crossed at Q = 10⁴                      |

Each "no" produces a published negative result and a documented pivot — exactly as Phases 0–1 did.
