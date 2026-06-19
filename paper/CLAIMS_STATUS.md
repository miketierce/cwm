# CWM Claims Status

This table is the current public claim ledger for the measurement paper and forward architecture. It should be checked before updating the README, website, book, or paper abstract.

## Status Key

| Label     | Meaning                                                   |
| --------- | --------------------------------------------------------- |
| MEASURED  | Direct result on built hardware                           |
| DERIVED   | Computed from measured data or first-principles equations |
| SIMULATED | Verified in software only                                 |
| PROJECTED | Extrapolated to an unbuilt configuration                  |
| OPEN      | Claim-gating experiment still required                    |
| KILLED    | Tested and rejected or reframed                           |

## Current Measured Claims

| Claim                                                     | Status                                      | Evidence                                                                                                                                           | Risk or gap                                                    | Public framing                                                        |
| --------------------------------------------------------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------- |
| Fused-silica plates support resolvable acoustic modes     | MEASURED                                    | [v19r.md](v19r.md), [../docs/lab_diary_20260602.md](../docs/lab_diary_20260602.md), [../docs/lab_diary_20260604.md](../docs/lab_diary_20260604.md) | Mode count depends on threshold, topology, and readout loading | "7-15 resolvable modes in current plates"                             |
| Signal structure is acoustic in origin                    | MEASURED, pending current-topology closeout | PZT-lifted null in corrected topology, tape-vs-glue null, spatial contrast                                                                         | Formal Pico NCO lifted null still needed                       | "Acoustic origin supported by null tests; E-W1 closes final topology" |
| 4-mode binary patterns classify at 100%                   | MEASURED                                    | [v19r.md](v19r.md)                                                                                                                                 | Single-session data; repeated-measures concern                 | "100% within-session classification; cross-session test pending"      |
| 8 levels x 4 modes gives 4,096 zero-error states          | MEASURED                                    | [v19r.md](v19r.md), [../docs/lab_diary_20260527.md](../docs/lab_diary_20260527.md)                                                                 | Calibration and decoder dependence                             | "12-bit within-session amplitude encoding"                            |
| Frequency x space non-separability gives CHSH-style S > 2 | MEASURED, classical                         | [v19r.md](v19r.md), [../docs/lab_diary_20260602.md](../docs/lab_diary_20260602.md)                                                                 | Avoid quantum overclaiming and optimized-angle inflation       | "Classical DOF non-separability, not entanglement"                    |
| Spectral fingerprints are stable over many cycles         | MEASURED                                    | [v19r.md](v19r.md), [../docs/lab_diary_20260603.md](../docs/lab_diary_20260603.md)                                                                 | Cross-day stability still needed for PUF                       | "16.5M-cycle endurance with low drift"                                |
| Loaded Q is in the hundreds on the current plate bench    | MEASURED                                    | [../docs/lab_diary_20260605.md](../docs/lab_diary_20260605.md)                                                                                     | PZT loading masks intrinsic Q                                  | "Loaded Q = 150-743, intrinsic Q not yet isolated"                    |

## Open Gates

| Gate                   | Experiment                                        | Why it matters                                              | Success criterion                                                  |
| ---------------------- | ------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------ |
| Signal-path closeout   | E-W1 / WL-A1 PZT-lifted null on Pico NCO topology | Removes the last topology-specific feedthrough objection    | Lifted/coupled < 1% at all standard modes                          |
| Cross-session validity | E-W2 / WL-A5                                      | Turns fingerprinting from session demo into device property | >=95% cross-session accuracy                                       |
| WRITE mechanism        | E3 / WL-A2 perturbation encoding                  | Decides whether "memory" and position sensing are earned    | Shift > 3 sigma at >=10 mg, position-dependent, reversible         |
| Decoder robustness     | E-W4 / WL-A3                                      | Avoids cherry-picking critique                              | Multiple pipelines >95% or honest dependency statement             |
| Intrinsic Q and rank   | WL-B1 optical readout                             | Breaks PZT loading and rank-2 bottleneck                    | SNR >=20 dB, effective rank >=6                                    |
| F10 anomaly            | WL-B2 redistribution matrix                       | Decides whether macro nonlinear mode coupling exists        | Hot spots classified as artifact, harmonic/IM, or genuine coupling |

## Projected Claims and Falsifiers

| Claim                          | Basis                                                    | Required measurement                                      | Falsifier                                                                              |
| ------------------------------ | -------------------------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Acoustic PUF                   | Manufacturing variance plus stable spectral fingerprints | Multi-device inter/intra Hamming distance and reliability | Cross-session accuracy <95% or inter-device variation comparable to intra-device drift |
| Multi-mode perturbation sensor | Rayleigh mass-loading shifts are position-dependent      | E3 plus grid position inference                           | Shifts <3 sigma or no distinguishable position vector                                  |
| Rank-N physical feature map    | More spatial channels reveal a higher-rank H             | Optical or MEMS readout with >=8 channels                 | Physical H indistinguishable from random at rank 16 unless energy wins                 |
| MEMS temporal reservoir        | tau = Q/(pi f) can match kHz symbol rates at high Q      | Fabricated die, kHz I/O, NARMA/spoken-digit tests         | Memory capacity MC < 3 at >=3 kHz                                                      |
| Parametric Ising optimizer     | Pumped acoustic modes may form bistable phase states     | Parametric threshold and controlled coupling              | No oscillation at safe drive for Q around 10^4                                         |

## Reframed or Killed Claims

| Earlier claim                                        | Current status    | Public replacement                                                                      |
| ---------------------------------------------------- | ----------------- | --------------------------------------------------------------------------------------- |
| Ferrofluid CWM substrate                             | KILLED            | Solid glass only                                                                        |
| Plate performs Boolean computation at bench          | KILLED / reframed | Digital decoder computes Boolean labels from spectral features                          |
| Bench temporal reservoir computing                   | KILLED            | Current bench is spatial/spectral; temporal memory is MEMS-gated                        |
| Phase channel as robust bench data encoding          | KILLED at bench   | Phase is useful for classical non-separability and future controlled interference tests |
| Macro plate is a standalone computer                 | KILLED / reframed | Plate is a physical feature-extraction front-end                                        |
| Room-temperature quantum hardware                    | KILLED as framing | Classical wave analogs only                                                             |
| MEMS density, speed, and endurance as measured facts | PROJECTED         | Scaling-law projections pending fabricated device                                       |
