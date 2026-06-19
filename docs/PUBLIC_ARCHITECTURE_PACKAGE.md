# CWM Public Architecture Package and Full-Potential Roadmap

**Date:** 2026-06-19
**Scope:** synthesis across the research repo, academic paper versions, lab diaries, experiments, simulations, hardware notes, public website, and book manuscript.

## Evidence Rule

The project can stay ambitious only if every forward claim is labeled. Use this chain:

MEASURED -> DERIVED -> SIMULATED -> PROJECTED -> OPEN -> KILLED

For "quantum-like," use only the physically grounded meaning: classical wave non-separability, interference, phase relationships, mode coupling, high-dimensional state representation, and contextuality-style tests. Do not imply entanglement, quantum speedup, loophole-free Bell tests, or room-temperature quantum computation.

## Repository Audit Summary

### Research repo: wcfoma

The research repo has a strong internal evidence record but needs public navigation. The current structure already separates major domains: [paper/](../paper/), [docs/](.), [data/](../data/), [experiments/](../experiments/), [simulations/](../simulations/), [tools/](../tools/), [companion/](../companion/), [patent/](../patent/), and [archive/](../archive/). The public risk is not lack of material. It is that old speculative claims, active measured claims, and future architecture claims sit close together.

The paper arc is clear:

| Phase   | Character                                                               | Public interpretation                                        |
| ------- | ----------------------------------------------------------------------- | ------------------------------------------------------------ |
| v9      | Ferrofluid, quantum, ZIM, dilatancy, broad speculative architecture     | Historical, not current                                      |
| v10     | Glass pivot after ferrofluid phase diffusion killed the first substrate | Key methodological pivot                                     |
| v11-v17 | Scaling, MEMS design, advanced encoding, many simulated extensions      | Useful theory and provenance, not current measurement claims |
| v18     | Patent anchor                                                           | Frozen, do not edit or move                                  |
| v19     | Lab data plus overbroad computation and CHSH framing                    | Transitional draft                                           |
| v19r    | Measurement-scoped paper: fused-silica spectral fingerprinting          | Current canonical science                                    |

### Public site: cwm-site

The site already has strong public engagement assets: interactive mode exploration, spectrum-write demonstrations, a lab page, experiment worksheets, a developments feed, and a scrollytelling roadmap. Its main risk is stale or under-labeled numbers when the paper, book, and site are not updated together.

### Book repo: cwm-book

The book is the broad narrative layer. It is valuable for public engagement, but it carries older scaling and benchmark language that should be labeled inline as PROJECTED or SIMULATED where no device exists yet. The appendices are especially useful as verification assets: simulation catalogue, experiment guide, hypothesis ledger, and glossary.

## Strongest Scientific Model

CWM at the current bench scale is best described as:

> A coherent acoustic spectral transformer: a glass resonator maps drive vectors into stable, geometry-specific spectral features through a fixed physical transfer matrix H. Digital code currently performs classification and decision-making on those features.

This model is strong because it does not require unsupported claims. It includes the measured wins and the measured failures:

| Component                | Current status                                  | Interpretation                                                             |
| ------------------------ | ----------------------------------------------- | -------------------------------------------------------------------------- |
| Eigenmode spectrum       | MEASURED                                        | 7-15 resolvable modes on plates, 30-350 kHz, high SNR                      |
| Acoustic signal path     | MEASURED / pending formal current-topology null | Multiple nulls support acoustic origin; E-W1 closes the final topology gap |
| Amplitude encoding       | MEASURED                                        | 8 levels across 4 modes, 4,096 zero-error states in one session            |
| Classification           | MEASURED                                        | 80/80 in one session; cross-session validation still needed                |
| Spatial non-separability | MEASURED with caveats                           | Classical frequency x space structure, not quantum entanglement            |
| Temporal reservoir       | KILLED at bench                                 | Decay time is far shorter than update/capture timing                       |
| Plate-as-computer claim  | KILLED / reframed                               | Current plate is a feature front-end, not a standalone computer            |
| MEMS reservoir           | PROJECTED                                       | Physics-motivated path if Q, rank, and symbol rate gates pass              |
| Parametric Ising         | PROJECTED / frontier                            | Only after MEMS parametric threshold is measured                           |

## Two Bottlenecks

| Bottleneck    | Current number                               | Consequence                                                          | Unlock                                               |
| ------------- | -------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------------- |
| Readout rank  | Two receivers, rank 2 H                      | ML/attention experiments cannot distinguish physical H from random H | Optical scan or >=8 readout channels                 |
| Time constant | tau = Q/(pi f), about 1-4 ms loaded on bench | Temporal reservoir fails at current update rate                      | MEMS Q, vacuum, high symbol rate, faster acquisition |

These are engineering walls, not proof that the architecture is impossible. But until they are broken, public claims should stay with fingerprinting, sensing, pedagogy, and physical feature extraction.

## Claim-Evidence-Risk Table

| Claim                                                             | Status                                      | Evidence                                            | Risk                                                   | Next reducer                         |
| ----------------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------ | ------------------------------------ |
| Fused-silica plates produce stable acoustic spectral fingerprints | MEASURED                                    | [paper/v19r.md](../paper/v19r.md), daily diaries    | Single-session classification still dominates headline | E-W2 / WL-A5 cross-session run       |
| Signal structure is acoustic, not electrical                      | MEASURED with one pending topology closeout | PZT-lifted null, tape/glue null, spatial contrast   | Current Pico NCO topology needs formal lifted null     | E-W1 / WL-A1                         |
| 4,096 amplitude states are distinguishable                        | MEASURED                                    | T3.4 diary and v19r                                 | One-session calibration, decoder-dependent             | All-decoder table and repeat session |
| Frequency x space non-separability is real                        | MEASURED, classical                         | E1 multi-pair CHSH, fixed-angle reanalysis path     | Overinterpretation as quantum claim                    | Keep Qian-Eberly classical framing   |
| Perturbation write/read is viable on plates                       | OPEN                                        | Rod/older perturbation evidence and Rayleigh theory | Formal plate E3 not complete                           | WL-A2 / E3                           |
| Acoustic PUF is a practical use case                              | PLAUSIBLE                                   | Unique fingerprints, stability data                 | Needs multi-device, cross-day reliability              | WL-B3 plus WL-A5                     |
| Multi-mode mass/position sensor is practical                      | PLAUSIBLE                                   | Rayleigh mechanism, mode-shift theory               | Needs measured position-dependent shift vectors        | WL-A2 then WL-B4                     |
| Rank-N physical projection can aid ML                             | PROJECTED                                   | H matrix measured, rank problem diagnosed           | Rank 2 makes H absorbable/random-equivalent            | WL-B1 optical readout                |
| MEMS temporal reservoir is feasible                               | PROJECTED                                   | tau scaling and literature Q                        | No fabricated CWM MEMS die                             | D1 design, D3 reservoir test         |
| Phononic parametric Ising machine                                 | SPECULATIVE BUT TESTABLE                    | Mathieu/parametric precedent                        | No threshold measured; may need high Q or cryo         | MEMS pump at 2f gate                 |

## Highest-Value Use Cases

| Rank | Use case                             | Why it matters                                                     | Evidence maturity                                | Public value                          |
| ---- | ------------------------------------ | ------------------------------------------------------------------ | ------------------------------------------------ | ------------------------------------- |
| 1    | Acoustic PUF                         | Unique physical identity from manufacturing variance               | MEASURED seed, needs cross-session/multi-device  | Security, identity, easy story        |
| 2    | Multi-mode perturbation sensor       | Mass and position map into mode-shift vectors                      | OPEN but strongly physical                       | Scientific instrument and education   |
| 3    | Classical non-separability kit       | Shows CHSH-style classical wave correlations on a desk             | MEASURED in lab, replication pending             | Public engagement centerpiece         |
| 4    | Physical random-projection front-end | Uses H as an analog feature map                                    | MEASURED rank 2, useful only after rank increase | Neuromorphic/unconventional computing |
| 5    | MEMS acoustic reservoir              | Solves the bench time-constant wall if Q and rate gates pass       | PROJECTED                                        | Research-grade frontier               |
| 6    | Phononic parametric optimizer        | Same glass could become memory, feature map, and spin-like network | PROJECTED frontier                               | High impact if gated results pass     |

## Configuration Space

| Axis       | Near-term configurations                             | Longer horizon                                                  | Measurement needed                 |
| ---------- | ---------------------------------------------------- | --------------------------------------------------------------- | ---------------------------------- |
| Material   | Fused silica plates, borosilicate rods               | Vacuum-packaged fused silica/quartz MEMS                        | Intrinsic Q without PZT loading    |
| Geometry   | 100 mm and 25 mm plates                              | 1 mm plate or rod, phononic isolation, transducer arrays        | Mode density and coupling maps     |
| Excitation | Pico NCO square wave, PicoScope/AWG history          | AlN thin-film drive, multi-tone DAC                             | Drive linearity and heating budget |
| Readout    | 2 PZT receivers through relay mux                    | Optical scan, quadrant photodiode, 8-16 AlN receivers           | Rank and SNR                       |
| Encoding   | Frequency, amplitude, spatial receiver, perturbation | Phase gates, parametric bistability, lithographic perturbations | Decoder sensitivity and stability  |
| Control    | Host Python plus Pico/relay                          | FPGA/ASIC shadow registers                                      | End-to-end latency and energy      |

## Roadmap

### Phase 0: Public Cleanup and Evidence Packaging

**Goal:** Make the repository navigable without altering historical evidence.

**Actions:** create a top-level index, claim-status table, and this public architecture package. Keep old paper versions in the archive. Add maturity labels to site/book copy as they are revised.

**Success:** a new reader can identify current claims, killed claims, open gates, and canonical files within minutes.

### Phase A: Validation Closeout

**Required experiments:** E-W1/WL-A1 current-topology PZT-lifted null, E-W3 fixed-angle CHSH reanalysis, E-W4 all-decoder table, E-W5 Q fitting, E-W2/WL-A5 cross-session discrimination.

**Missing data:** formal Pico NCO null, cross-day classification, robust Q fits, complete decoder sensitivity.

**Success:** v19r can be submitted with no blurred provenance. If any gate fails, the paper narrows rather than expands.

### Phase B: Bench Ceiling and Public Demonstrations

**Required experiments:** WL-A2 E3 perturbation encoding, WL-B1 optical readout, WL-B2 F10 redistribution matrix, WL-B3 PUF study, WL-B4 position inference, WL-B5 CHSH kit validation.

**Success:** at least two near-term papers become possible: PUF, perturbation sensor, or classical non-separability kit. Optical readout either breaks rank 2 or is explicitly killed.

### Phase C: Scientific Package and Outreach

**Deliverables:** v19r paper, replication guide, killed-claims page, public kit page, claim maturity legend across site/book/readmes.

**Success:** the public contribution is not only the device idea, but the falsification method: what worked, what failed, and what must be measured next.

### Phase D: MEMS Design and Fabrication Path

**Required files:** MEMS design study, mode/Q scaling model, AlN transducer layout, thermal-noise and energy budget, fabrication partner notes.

**Experiments:** fabricated die Q, rank-N response, temporal reservoir at kHz symbol rates, physical H versus random H at rank 8-16.

**Success:** Q >= 10^4 target or a documented lower-Q pivot; reservoir memory capacity MC >= 3 at practical symbol rates.

### Phase E: Frontier Gates

**Only after Phase D:** parametric pumping at 2f, bistable phase-state measurement, small Ising/QUBO test, contextuality/GHZ-style classical DOF tests.

**Success:** publish a gated frontier result or a negative result with clear boundary conditions. Do not sell this phase as current capability.

## Recommended Public Repository Structure

The current structure is mostly sound. The safest public-facing reorganization is additive first, then mechanical moves later.

### Implemented now

| File                                                             | Purpose                                         |
| ---------------------------------------------------------------- | ----------------------------------------------- |
| [../INDEX.md](../INDEX.md)                                       | Top-level reading path and maturity legend      |
| [../paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md)           | Claim/evidence/risk index for paper and roadmap |
| [PUBLIC_ARCHITECTURE_PACKAGE.md](PUBLIC_ARCHITECTURE_PACKAGE.md) | Public-facing roadmap and synthesis             |

### Recommended next, when the worktree is clean

| Change                                                                                | Reason                                                           |
| ------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Move daily diaries to `docs/diary/` and keep [LAB_DIARY.md](LAB_DIARY.md) as an index | Reduces docs clutter without losing history                      |
| Create `docs/KILLED_HYPOTHESES.md`                                                    | Makes falsification visible as a trust asset                     |
| Split [simulations/](../simulations/) into core and sidebar/narrative groups          | Avoids mixing peer-reviewable physics with speculative analogies |
| Organize [tools/](../tools/) into bench, analysis, diagnostics, archived              | Makes replication less intimidating                              |
| Standardize `data/raw/YYYY-MM-DD_session/` and `data/results/<campaign>/`             | Improves provenance and reproducibility                          |
| Refresh [HARDWARE.md](../HARDWARE.md) after each bench topology change                | Prevents stale wiring from becoming false evidence               |

## Canonical Public References

| Role                   | Canonical file                                                                   |
| ---------------------- | -------------------------------------------------------------------------------- |
| Current paper          | [../paper/v19r.md](../paper/v19r.md)                                             |
| Patent anchor          | [../paper/v18.md](../paper/v18.md)                                               |
| Experiment plan        | [../paper/BUILD_AND_EXPERIMENT_PLAN.md](../paper/BUILD_AND_EXPERIMENT_PLAN.md)   |
| Reviewer-gap worklist  | [../paper/EXPERIMENT_WORKLIST_v19r.md](../paper/EXPERIMENT_WORKLIST_v19r.md)     |
| Full roadmap           | [ROADMAP_FULL_POTENTIAL.md](ROADMAP_FULL_POTENTIAL.md)                           |
| Full worklist          | [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md)                         |
| Processor architecture | [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) |
| Daily evidence record  | [LAB_DIARY.md](LAB_DIARY.md) plus daily diaries in [docs/](.)                    |
| Companion guide        | [../companion/experiment_guide.md](../companion/experiment_guide.md)             |

## Claims Needing Stronger Evidence Before Public or Academic Presentation

| Claim                                          | Required evidence                                                                    |
| ---------------------------------------------- | ------------------------------------------------------------------------------------ |
| Plate stores writable data                     | E3 perturbation shifts > 3 sigma, position-dependent, reversible                     |
| Practical PUF                                  | Multi-device inter/intra statistics plus cross-session reliability                   |
| General compute logic                          | Demonstrated physical nonlinearity or a clearly external digital control layer       |
| Temporal reservoir                             | kHz-rate input/output with tau-matched memory, not current bench loop                |
| MEMS density or speed advantage                | Fabricated die measurements and system-level energy, including ADC/control           |
| Quantum-like capabilities                      | Classical-wave language, fixed protocols, falsifiers, and no quantum hardware claims |
| Competitive claims against photonic processors | Architecture-level comparison only unless device metrics are measured                |

## Best Public Narrative

CWM should be presented as an evidence-first research program at the edge of acoustic information processing. The honest center is not "a glass computer already exists." It is this:

> A cheap fused-silica resonator has already shown stable, high-SNR, multi-mode acoustic fingerprints; classical non-separable wave structure; and a clear path to sensing, PUFs, public education, and MEMS-scale physical feature maps. The next experiments decide whether the same architecture can become writable memory, temporal reservoir computing, or parametric phononic optimization.

That story preserves the frontier without stepping into sci-fi.
