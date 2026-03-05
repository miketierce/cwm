# WCFOMA — Wave-Coherent Field-Oriented Memory Architecture

**A falsification-first research project testing whether information can be stored, computed on, and secured as resonant wave configurations in physical media.**

[![Status: Phase 0 — Computational Validation](https://img.shields.io/badge/Status-Phase%200%20Computational%20Validation-blue)]()
[![Paper: v9](<https://img.shields.io/badge/Paper-v9%20(Jan%202026)-green>)]()

## What Is This?

WCFOMA proposes that if memory is physically a field, computation should operate by reshaping that field directly — unifying memory, computation, and security in a single physical substrate. The architecture uses:

- **Resonant eigenmodes** in ferrofluid/granular media as analog memory
- **Wave interference** for computation (associative recall, pattern matching)
- **Granular dilatancy** for passive, power-free mechanical security
- **Zero-index metamaterials (ZIMs)** for enhanced mode stability
- **Optional quantum correlations** for verification (not required for core operation)

The paper projects 10–100× energy efficiency improvements over von Neumann architectures for AI workloads, with Tb/cm³ storage densities. **This repo exists to rigorously test those claims.**

## Project Philosophy

> We're either going to disprove this or find something useful along the way.

Every claim in the paper is tagged as DEMONSTRATED, PROPOSED, PROJECTED, or SIMULATED. This repo implements a **kill-criterion framework** — each experiment has explicit thresholds that, if not met, indicate the approach is unviable. Negative results are valuable and publishable.

## Repository Structure

```
wcfoma/
├── paper/                      # The paper and addenda
│   └── v9.md                   # Canonical paper (do not modify)
├── simulations/                # Core physics simulation modules
│   ├── common.py               # Shared parameters, constants, utilities
│   ├── resonator_1d.py         # 1D damped oscillator model
│   ├── resonator_3d.py         # 3D FDTD wave solver
│   ├── helmholtz_2d.py         # 2D Helmholtz eigenvalue solver (ENZ cavities)
│   └── thermal.py              # Mode crowding & thermal drift analysis
├── experiments/                # Structured experiment runners
│   ├── exp01_mode_persistence.py
│   ├── exp02_zim_damping.py
│   ├── exp03_dilatancy_tamper.py
│   ├── exp04_thermal_stability.py
│   └── exp05_geometry_invariance.py
├── analysis/                   # Visualization & data analysis
│   ├── plotting.py             # Publication-quality figure generation
│   ├── comparison.py           # Claims validation tables
│   └── export.py               # CSV/JSON data export
├── notebooks/                  # Interactive Jupyter notebooks
│   ├── 01_claims_validation.ipynb    # Run all experiments, full validation
│   ├── 02_1d_resonator.ipynb         # Interactive 1D parameter explorer
│   └── 03_thermal_analysis.ipynb     # Thermal drift sensitivity sweeps
├── prototypes/                 # Hardware prototype documentation
│   ├── prototype_a/            # Macro-scale ferrofluid resonator (< $1k)
│   ├── prototype_b/            # Micro-scale fiber-integrated cells
│   └── zim_designs/            # 3D-printable ZIM structure files
├── data/                       # Experimental data (raw + processed)
│   ├── raw/
│   └── results/
├── docs/                       # Project documentation
│   ├── ROADMAP.md              # Phased research roadmap with kill criteria
│   ├── CONTRIBUTING.md         # How to contribute
│   └── PROTOCOLS.md            # Experiment protocols
├── tests/                      # Unit tests for simulation code
├── requirements.txt
├── pyproject.toml
└── readme.md
```

## Quick Start

```bash
# Clone and install
git clone https://github.com/miketierce/wcfoma.git
cd wcfoma
pip install -e ".[dev]"

# Run the claims validation dashboard
jupyter lab notebooks/01_claims_validation.ipynb

# Or run individual experiments from the command line
python -m experiments.exp01_mode_persistence
python -m experiments.exp03_dilatancy_tamper
python -m experiments.exp04_thermal_stability
```

## Current Status: Phase 0

We are systematically validating every quantitative claim in the paper through simulation before investing in hardware.

| Claim                      | Paper Value  | Status     |
| -------------------------- | ------------ | ---------- |
| ZIM coherence extension    | ~2×          | 🔬 Testing |
| 1D frequency drift (γ=0.5) | ~33%         | 🔬 Testing |
| 3D frequency drift (γ=0.3) | ~7%          | 🔬 Testing |
| Max modes without ZIM      | ~41          | 🔬 Testing |
| Max modes with ZIM         | ~322         | 🔬 Testing |
| Storage density (ZIM)      | ~3.22 Tb/cm³ | 🔬 Testing |
| Geometry invariance        | <1% shift    | 🔬 Testing |
| Energy per operation       | fJ range     | 🔬 Testing |

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full phased roadmap including kill criteria.

- **Phase 0** (Now): Computational validation — reproduce and stress-test paper simulations
- **Phase 1** (Mid 2026): Advanced simulation — Meep FDTD, multiphysics, realistic materials
- **Phase 2** (2026-2027): Benchtop Prototype A — macro-scale ferrofluid resonator
- **Phase 3** (2027-2028): Micro-scale arrays with fiber optic integration
- **Phase 4** (2029+): Domain-specific AI accelerator (if warranted)

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md). We especially need:

- **Simulation validation** — Run the notebooks, report discrepancies
- **Literature verification** — Help fix the flagged citation issues
- **Material science expertise** — Ferrofluid acoustics, ZIM fabrication
- **Theoretical analysis** — Derive the ZIM damping factor from first principles
- **Healthy skepticism** — Every challenged assumption makes the work stronger

## Citation

```bibtex
@article{tierce2026wcfoma,
  title={Wave-Coherent Field-Oriented Memory Architecture for Sustainable, Secure, In-Memory Intelligence},
  author={Tierce, Mike},
  year={2026},
  note={Preprint, independent research}
}
```

## License

MIT — Use freely, cite fairly.
