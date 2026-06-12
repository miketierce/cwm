# CWM — Coherent Wave Memory

**Physics validation of wave-interference information processing in glass acoustic resonators.**

CWM investigates how much information can be encoded in, and recovered from, the acoustic eigenmode spectrum of solid glass resonators — and how far the interference structure of those modes can be pushed toward physical computation. The program is **falsification-first**: every claim is either backed by bench measurement, labeled as a model projection with error bars, or published on our kill list.

**Current paper (canonical):** _Spectral Fingerprinting in Piezo-Driven Fused-Silica Plate Resonators_ (v19r) — see [paper/](paper/).
**Forward plan:** [docs/ROADMAP_FULL_POTENTIAL.md](docs/ROADMAP_FULL_POTENTIAL.md).

## What Is Measured (bench hardware, fused-silica plates, 2026)

| Result                              | Value                                                                         | Evidence                         |
| ----------------------------------- | ----------------------------------------------------------------------------- | -------------------------------- |
| Resolved acoustic modes             | 7–15 per plate (30–350 kHz) at 42–56 dB SNR                                   | Frequency sweeps, Pico NCO drive |
| Acoustic (not electrical) origin    | PZT-lifted null = 0% feedthrough; spatial contrast 49–60:1; tape-vs-glue null | 3 independent null tests         |
| Spectral fingerprint classification | 100% (80/80 trials), 193σ inter-class separation, single session              | Nearest-centroid decoder         |
| Multi-level encoding                | 8 levels × 4 modes = 4,096 states (12 bits), zero error                       | Min 9σ level separation          |
| Frequency×space non-separability    | CHSH S = 2.73 (fixed-angle) to 2.83 (optimized), 5/5 mode pairs               | Qian–Eberly classical framework  |
| Spectral stability                  | 0.22% drift over 16.5M cycles; 0.65% over 3.5 h                               | Endurance monitoring             |
| Loaded Q-factor                     | 150–743 (PZT-loaded; intrinsic Q higher but masked)                           | Lorentzian bandwidth fits        |

## What Is _Not_ Claimed

This project previously made broader claims that did not survive validation or peer review. They are retracted, documented, and preserved — transparency about dead ends is part of the method:

- **The plate does not compute** (at macro scale). Boolean logic, associative recall, and nearest-neighbor results are produced by digital decoders operating on spectral features; the plate is a linear spectral transformer.
- **Temporal reservoir computing fails at bench.** Mode decay (τ ≈ 1–4 ms loaded) is ~100× shorter than the achievable drive-update interval. NARMA-10 fails in all three attempted configurations. This is an engineering wall the MEMS roadmap addresses, not a hidden success.
- **No quantum claims.** The CHSH result demonstrates classical non-separability of degrees of freedom — a geometric property of plate eigenmodes — not entanglement.
- **MEMS density projections** (Gbit/cm³-class figures from earlier paper versions) are model extrapolations, not measurements, and live only in the roadmap with explicit assumptions.
- **Killed outright:** ferrofluid substrates (phase diffusion), cymatics–script correlation, audio-interface capture, phase-channel encoding at bench, and ~36 of 87 modeled extension hypotheses. Kill mechanisms are documented in the companion papers.

## Why It Still Matters

The two failures above reduce to two numbers — readout rank (2 receivers) and the Q·f time constant — and both are engineering limits, not physics limits. The near-term scientific products are real today:

1. **Acoustic PUFs** — manufacturing variance gives every plate a unique, stable spectral fingerprint.
2. **Multi-mode perturbation sensing** — Rayleigh frequency shifts encode mass _and position_ across the mode spectrum.
3. **A $50 classical non-separability demo** — anyone can measure Tsirelson-bound CHSH correlations on a desk; full replication protocol ships with the paper.
4. **MEMS-scale reservoir & parametric computation** — the validated scaling path where τ, Q, and transducer count all move in our favor. See the [roadmap](docs/ROADMAP_FULL_POTENTIAL.md).

## Repository Structure

```
wcfoma/
├── paper/              # Canonical paper (v19r) + BUILD_AND_EXPERIMENT_PLAN (E1–E8)
├── docs/               # Lab diaries, ROADMAP_FULL_POTENTIAL, protocols
├── simulations/        # 48 physics simulation modules
├── tests/              # 2,253 automated tests
├── experiments/        # Standalone simulation experiments (exp01–exp11)
├── tools/              # Bench drivers (PicoScope, Pico NCO, relay mux) + 160 experiment scripts
├── data/               # Raw captures and results (data/results/lab/ = bench data)
├── notebooks/          # 12 Jupyter analysis notebooks
├── analysis/           # Plotting, comparison, export
├── companion/          # Replication guides, wiring guides, TN1 rewritability
├── prototypes/         # Rod and plate prototype designs
├── patent/             # U.S. Provisional No. 64/023,264 (filed 2026-03-31)
└── archive/            # All prior paper versions (v9–v19) and original corpus
```

## Quick Start

```bash
git clone https://github.com/miketierce/cwm.git
cd cwm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -q          # run all 2,253 tests
```

## CWM Lab

Interactive browser-based experiment platform. Connects to a PicoScope 2204A and the glass resonator bench; falls back to deterministic Rayleigh simulation when no hardware is attached.

```bash
source .venv/bin/activate
PYTHONPATH=. python tools/cwm_lab.py --port 8200
# open http://localhost:8200
```

Tabs: **Experiments** (guided capture wizard with Firebase export), **CIM Demo** (spectral pattern store/recall playground — decoder-based, see honesty note above), **Quantum Bridge** (classical-wave analogs of quantum-information demos), **Auth Demo** (spectral-correlation authentication).

## Key Tools

```bash
# Multi-tone AWG waveform generation (PicoScope 2204A)
PYTHONPATH=. python tools/awg_waveform.py --pattern A

# Markdown → duplex PDF (paper / guides)
PYTHONPATH=. python tools/md2pdf.py paper/v19r.md
```

## Reproducing the CHSH Result

Requirements: any resonant plate or rod (loaded Q > 100), two PZT pickups at different positions, a dual-channel scope, a signal generator, and ~20 lines of Python. The effect is a geometric property of Chladni patterns — any plate whose modes have different spatial distributions at two measurement points yields S > 2. See the companion experiment guide in [companion/](companion/).

## Citation

```bibtex
@article{tierce2026cwm,
  title   = {Spectral Fingerprinting in Piezo-Driven Fused-Silica
             Plate Resonators},
  author  = {Tierce, William Michael},
  year    = {2026},
  note    = {v19r. U.S. Provisional Patent Application No. 64/023,264}
}
```

## Patent

U.S. Provisional Patent Application No. 64/023,264 — Filed 31 March 2026.

## License

This work is shared for research and educational purposes. See individual files for specific terms.
