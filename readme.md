# CWM — Coherent Wave Memory

**Wave-based storage and computation in acoustic glass resonators.**

CWM encodes information in the acoustic eigenmode spectrum of solid glass resonators and computes via wave interference. A mass perturbation pattern on a glass rod creates a unique spectral fingerprint; driving an array of rods with a query spectrum performs associative recall — a physical dot product at the speed of sound — in constant time.

## Key Results

| Metric                             | Value                              |
| ---------------------------------- | ---------------------------------- |
| Thermally stable modes             | 9,380 (borosilicate, ±1 K)         |
| Capacity per rod (1 mm MEMS)       | 15 KB (119,126 bits)               |
| Active density                     | 95.1 Gbit/cm³ (9.5× DRAM)          |
| Packed-array density (0.5 mm SiO₂) | 1.4 Tbit/cm³ (1.4× NAND Flash)     |
| Associative search latency         | 3.8 µs (100k patterns in parallel) |
| Write energy                       | 15 fJ/bit                          |
| Endurance                          | >10¹⁵ cycles                       |
| Macro prototype SNR                | 98.5 dB                            |

## Simulation Apparatus

The research is backed by a falsification-first computational framework:

- **48 simulation modules** in `simulations/`
- **2,253 automated tests** in `tests/`
- **99 hypotheses tested**: 67 confirmed, 32 killed (67.7% confirmation rate)
- **22 sidebars** — advanced encoding techniques and cross-domain investigations (§11 of the paper)

Every “confirmed” result passes automated regression tests. Every “killed” result is preserved with its kill mechanism documented.

## Repository Structure

```
cwm/
├── paper/              # Canonical paper (v18) + figures
│   ├── v18.md          # The definitive CWM paper
│   └── figures/
├── simulations/        # 48 physics simulation modules
├── tests/              # 2,253 automated tests
├── experiments/        # Standalone experiment scripts (exp01–exp05)
├── notebooks/          # 12 Jupyter analysis notebooks
├── analysis/           # Plotting, comparison, and export tools
├── companion/          # Experiment guide, letter to Scranton, TN1 rewritability
├── prototypes/         # Prototype designs (prototype_a, prototype_b, glass_rod)
├── data/               # Raw data and results
├── docs/               # SIDEBARS.md, ROADMAP.md, PROTOCOLS.md, CONTRIBUTING.md
├── tools/              # AWG waveform generator, md2pdf converters
└── archive/            # Old paper versions (v9–v15), original corpus, verification scripts
```

## Quick Start

```bash
git clone https://github.com/miketierce/cwm.git
cd cwm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -q          # run all 2,253 tests
```

## Tools

### AWG Waveform Generator

Generates multi-tone query waveforms for the PicoScope 2204A's arbitrary waveform generator. Computes Rayleigh-shifted mode frequencies from first principles and exports CSV and WAV files ready for import.

```bash
# Generate Query A (Pattern A: L/4 + 3L/4, 5 modes × 0.1 V)
PYTHONPATH=. python tools/awg_waveform.py --pattern A

# All four patterns at once
PYTHONPATH=. python tools/awg_waveform.py --all --output data/results/awg

# Custom rod geometry
PYTHONPATH=. python tools/awg_waveform.py --pattern A --mass 1.2 --rod-length 120
```

Import the generated CSV into PicoScope 7: Tools → Signal Generator → Arbitrary → Import. Set amplitude to the value printed by the script (~0.40 Vpp) and sample rate to 1 MS/s. See Section D.17 of the Experiment Guide for full instructions.

### PDF Builder

Converts the experiment guide or paper from Markdown to a book-quality duplex PDF.

```bash
PYTHONPATH=. python tools/md2pdf.py companion/experiment_guide.md
PYTHONPATH=. python tools/md2pdf.py paper/v18.md
```

## The Glass Rod Breakthrough

The critical insight: a borosilicate glass rod at MEMS scale (1 mm × 40 µm) supports 9,380 thermally stable eigenmodes — each an independent information channel. The mode count depends only on material Q and thermal expansion, not on rod length. Shrinking the rod increases density as 1/L² while capacity falls only as log(L). At 1 mm, CWM crosses DRAM density; at 0.45 mm, it crosses NAND Flash.

Every fabrication step borrows from an existing MEMS production line: glass DRIE (Schott Borofloat 33), AlN thin-film piezo (smartphone FBAR filters), MEMS vacuum packaging (SiTime oscillators), CMOS-MEMS flip-chip bonding (Bosch accelerometers). The innovation is the architectural combination, not the fabrication.

## Honest Assessment

CWM's strongest claims — mode count, Q factor, Rayleigh perturbation encoding, associative recall — are validated by 2,253 tests against first-principles physics. The weakest link is the gap between simulation and silicon: no MEMS device exists yet. The paper is transparent about this, killing 32 of 99 hypotheses and documenting every failure mechanism.

## Citation

```bibtex
@article{tierce2026cwm,
  title   = {Coherent Wave Memory: Wave-Based Storage and Computation
             in Acoustic Glass Resonators},
  author  = {Tierce, William Michael},
  year    = {2026},
  note    = {v18, 48 simulation modules, 2,253 automated tests,
             99 hypotheses (67 confirmed, 32 killed).
             U.S. Provisional Patent Application No. 64/023,264}
}
```

## Patent

U.S. Provisional Patent Application No. 64/023,264 — Filed 31 March 2026.

## License

This work is shared for research and educational purposes. See individual files for specific terms.
