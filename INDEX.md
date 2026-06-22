# CWM Repository Index

This repository is the public research apparatus for Coherent Wave Memory (CWM): papers, lab records, bench tools, simulations, data products, hardware notes, and replication material.

The shortest honest summary is this: the current bench proves a strong acoustic spectral-fingerprinting primitive in fused silica. The full processor architecture is a staged research program whose next gates are perturbation writing, cross-session stability, higher-rank readout, and MEMS-scale timing.

## Start Here

| Reader goal                            | First file                                                                       | Why                                                                          |
| -------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Current measured science               | [paper/v19r.md](paper/v19r.md)                                                   | Current measurement-scoped paper, post peer-review downscope                 |
| Claim-by-claim status                  | [paper/CLAIMS_STATUS.md](paper/CLAIMS_STATUS.md)                                 | Maps claims to evidence, gaps, risks, and reframes                           |
| Full public roadmap                    | [docs/PUBLIC_ARCHITECTURE_PACKAGE.md](docs/PUBLIC_ARCHITECTURE_PACKAGE.md)       | Public-facing synthesis across papers, diaries, data, site, and book         |
| Frontier ceiling + ladder              | [docs/FRONTIER_CEILING.md](docs/FRONTIER_CEILING.md)                             | Maximum defensible capability ceiling and the experiments that unlock it     |
| Desk demonstrator presentation         | [docs/DESK_DEMONSTRATOR_PRESENTATION.md](docs/DESK_DEMONSTRATOR_PRESENTATION.md) | Slide deck: projected desk capabilities mapped to PFUs and frontier rungs    |
| Desk / briefcase demonstrator          | [docs/DESK_DEMONSTRATOR.md](docs/DESK_DEMONSTRATOR.md)                           | No-fab phononic plate-array build that demonstrates the MEMS principles      |
| Desk demonstrator bench protocol       | [docs/DESK_DEMONSTRATOR_PROTOCOL.md](docs/DESK_DEMONSTRATOR_PROTOCOL.md)         | Step-by-step repeatable procedures for every build phase (DD-P0–DD-P10)      |
| Desk demonstrator scrappy path         | [docs/DESK_DEMONSTRATOR_SCRAPPY.md](docs/DESK_DEMONSTRATOR_SCRAPPY.md)           | Reuse-first / buy-nothing path to prove and iterate on owned + salvaged gear |
| DOOM demo (first-person maze on glass) | [docs/DESK_DEMONSTRATOR_DOOM.md](docs/DESK_DEMONSTRATOR_DOOM.md)                 | 32-plate kernel-rendered maze — Level 3 showcase, ~$68 beyond Phase 4A       |
| Full-potential experiment plan         | [docs/ROADMAP_FULL_POTENTIAL.md](docs/ROADMAP_FULL_POTENTIAL.md)                 | Phased roadmap with bottlenecks, use cases, and kill criteria                |
| Bench execution details                | [docs/FULL_POTENTIAL_WORKLIST.md](docs/FULL_POTENTIAL_WORKLIST.md)               | Copy-paste lab prompts, procedures, success criteria, BOM                    |
| Academic paper plan                    | [paper/BUILD_AND_EXPERIMENT_PLAN.md](paper/BUILD_AND_EXPERIMENT_PLAN.md)         | E1-E8 validation experiments for the paper path                              |
| Lab history                            | [docs/LAB_DIARY.md](docs/LAB_DIARY.md) and [docs/](docs/)                        | Chronological bench record and daily diaries                                 |
| Hardware state                         | [HARDWARE.md](HARDWARE.md)                                                       | Bench wiring, equipment, and troubleshooting notes                           |
| Replication/public guide               | [companion/experiment_guide.md](companion/experiment_guide.md)                   | Companion build and experiment material                                      |

## Claim Maturity Legend

| Label     | Meaning                                                      |
| --------- | ------------------------------------------------------------ |
| MEASURED  | Direct instrument result on built hardware                   |
| DERIVED   | Calculation from measured data or first-principles equations |
| SIMULATED | Tested in code, not yet shown on bench hardware              |
| PROJECTED | Extrapolated to an unbuilt configuration such as MEMS        |
| OPEN      | Important claim-gating experiment not yet completed          |
| KILLED    | Tested and rejected, preserved for transparency              |

Every public-facing statement should carry one of these labels explicitly or be phrased so the maturity level is obvious.

## Repository Map

| Path                         | Role                                                                    |
| ---------------------------- | ----------------------------------------------------------------------- |
| [paper/](paper/)             | Current paper, architecture companion papers, reviewer-driven worklists |
| [docs/](docs/)               | Roadmaps, daily lab diaries, protocols, representation hypotheses       |
| [data/](data/)               | Raw and processed experiment outputs where committed                    |
| [experiments/](experiments/) | Standalone simulation experiments                                       |
| [simulations/](simulations/) | Physics, capacity, scaling, and speculative analogy modules             |
| [tests/](tests/)             | Automated simulation/regression tests                                   |
| [tools/](tools/)             | Bench drivers, analysis scripts, Pico NCO, PicoScope, relay tooling     |
| [analysis/](analysis/)       | Plotting, comparison, and export helpers                                |
| [companion/](companion/)     | Replication guides, wiring guides, public-facing companion docs         |
| [patent/](patent/)           | Provisional patent material and index                                   |
| [archive/](archive/)         | Prior paper versions, original corpus, killed or superseded material    |

## Historical Material

Do not delete old claims or failed paths. The project is strongest when the record remains visible: ferrofluid, audio capture, phase-channel encoding, bench temporal reservoir computing, Boolean-compute framing, and several speculative analogies were either killed or reframed by later evidence.

When updating public material, prefer this hierarchy:

1. Lead with [paper/v19r.md](paper/v19r.md) for measured claims.
2. Use [paper/CLAIMS_STATUS.md](paper/CLAIMS_STATUS.md) to decide maturity labels.
3. Use [docs/PUBLIC_ARCHITECTURE_PACKAGE.md](docs/PUBLIC_ARCHITECTURE_PACKAGE.md) for roadmap and public narrative.
4. Keep [paper/v18.md](paper/v18.md) frozen as the patent anchor.
5. Treat older paper versions in [archive/paper_versions/](archive/paper_versions/) as provenance, not current claims.
