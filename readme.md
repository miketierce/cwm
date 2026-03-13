# CWM — Coherent Wave Memory

**Wave-based storage and computation in acoustic glass resonators.**

CWM encodes information in the acoustic eigenmode spectrum of solid glass resonators and computes via wave interference. A mass perturbation pattern on a glass rod creates a unique spectral fingerprint; driving an array of rods with a query spectrum performs associative recall — a physical dot product at the speed of sound — in constant time.

## Key Results

| Metric | Value |
|--------|-------|
| Thermally stable modes | 9,380 (borosilicate, ±1 K) |
| Capacity per rod (1 mm MEMS) | 15 KB (119,126 bits) |
| Active density | 95.1 Gbit/cm³ (9.5× DRAM) |
| Packed-array density (0.5 mm SiO₂) | 1.4 Tbit/cm³ (1.4× NAND Flash) |
| Associative search latency | 3.8 µs (100k patterns in parallel) |
| Write energy | 15 fJ/bit |
| Endurance | >10¹⁵ cycles |
| Macro prototype SNR | 98.5 dB |

## Simulation Apparatus

The research is backed by a falsification-first computational framework:

- **44 simulation modules** in `simulations/`
- **1,909 automated tests** in `tests/`
- **80 hypotheses tested**: 54 confirmed, 26 killed (67.5% confirmation rate)
- **22 advanced encoding techniques** (§11 of the paper)
- **16 historical/physical analogies** — Tesla, Chladni, Békésy, Franklin, Leibniz, Gabor, Zeeman, Kepler, Boltzmann, Gor’kov, Fabry–Pérot, Shannon–Nyquist, Mathieu–Floquet, Coronal Seismology, Gauge Geometry, Scranton–Dogon

Every “confirmed” result passes automated regression tests. Every “killed” result is preserved with its kill mechanism documented.

## Repository Structure

```
cwm/
├── paper/              # Canonical paper (v16) + figures
│   ├── v16.md          # 1,950 lines — the definitive CWM paper
│   └── figures/
├── simulations/        # 44 physics simulation modules
├── tests/              # 1,909 automated tests
├── experiments/        # Standalone experiment scripts (exp01–exp05)
├── notebooks/          # 12 Jupyter analysis notebooks
├── analysis/           # Plotting, comparison, and export tools
├── companion/          # Experiment guide, letter to Scranton, TN1 rewritability
├── prototypes/         # Prototype designs (prototype_a, prototype_b, glass_rod)
├── data/               # Raw data and results
├── docs/               # SIDEBARS.md, ROADMAP.md, PROTOCOLS.md, CONTRIBUTING.md
├── tools/              # md2pdf converters
└── archive/            # Old paper versions (v9–v15), original corpus, verification scripts
```

## Quick Start

```bash
git clone https://github.com/miketierce/cwm.git
cd cwm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -q          # run all 1,909 tests
```

## The Glass Rod Breakthrough

The critical insight: a borosilicate glass rod at MEMS scale (1 mm × 40 µm) supports 9,380 thermally stable eigenmodes — each an independent information channel. The mode count depends only on material Q and thermal expansion, not on rod length. Shrinking the rod increases density as 1/L² while capacity falls only as log(L). At 1 mm, CWM crosses DRAM density; at 0.45 mm, it crosses NAND Flash.

Every fabrication step borrows from an existing MEMS production line: glass DRIE (Schott Borofloat 33), AlN thin-film piezo (smartphone FBAR filters), MEMS vacuum packaging (SiTime oscillators), CMOS-MEMS flip-chip bonding (Bosch accelerometers). The innovation is the architectural combination, not the fabrication.

## Honest Assessment

CWM’s strongest claims — mode count, Q factor, Rayleigh perturbation encoding, associative recall — are validated by 1,909 tests against first-principles physics. The weakest link is the gap between simulation and silicon: no MEMS device exists yet. The paper is transparent about this, killing 26 of 80 hypotheses and documenting every failure mechanism.

## Citation

```bibtex
@article{tierce2026cwm,
  title   = {Coherent Wave Memory: Wave-Based Storage and Computation
             in Acoustic Glass Resonators},
  author  = {Tierce, William Michael},
  year    = {2026},
  note    = {v16, 44 simulation modules, 1,909 automated tests,
             80 hypotheses (54 confirmed, 26 killed)}
}
```

## License

This work is shared for research and educational purposes. See individual files for specific terms.
