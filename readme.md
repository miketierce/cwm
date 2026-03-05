# WCFOMA — Wave-Coherent Field-Oriented Memory Architecture

**A falsification-first research project testing whether information can be stored, computed on, and secured as resonant wave configurations in physical media.**

[![Status: Phase 1 In Progress](https://img.shields.io/badge/Status-Phase%201%20In%20Progress-blue)]()
[![Claims: 7 Confirmed · 1 Plausible · 1 Refuted](https://img.shields.io/badge/Claims-7%20Confirmed%20·%201%20Plausible%20·%201%20Refuted-orange)]()
[![Tests: 70 Passing](https://img.shields.io/badge/Tests-70%20Passing-success)]()
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
│   ├── thermal.py              # Mode crowding & thermal drift analysis
│   ├── sensitivity.py          # Parameter sensitivity sweeps & elasticity
│   ├── ferrofluid.py           # Ferrofluid material model (Rosensweig)
│   ├── interference.py         # Multi-mode interference & associative recall
│   ├── convergence.py          # Grid convergence study (Richardson extrapolation)
│   ├── cmos_interface.py       # CMOS energy budget model (4 tech nodes)
│   └── meep_fdtd.py            # MIT Meep FDTD scaffolding (Phase 1)
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
│   ├── 01_claims_validation.ipynb    # Full validation dashboard (8✓ 1~ 0✗)
│   ├── 02_1d_resonator.ipynb         # Interactive 1D parameter explorer
│   ├── 03_thermal_analysis.ipynb     # Thermal drift sensitivity sweeps
│   ├── 04_sensitivity_analysis.ipynb # Parameter elasticity & risk assessment
│   ├── 05_interference_recall.ipynb  # Multi-mode associative recall demo
│   ├── 06_ferrofluid_characterization.ipynb  # Ferrofluid material properties
│   └── 07_convergence_energy_mc.ipynb # Grid convergence, CMOS energy, MC tamper
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
├── tests/                      # Unit & integration tests (70 passing)
│   ├── test_simulations.py     # Phase 0 simulation tests
│   ├── test_phase1.py          # Phase 1a module tests
│   └── test_phase1b.py         # Phase 1b module tests
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

## Current Status: Phase 1 In Progress

Claims validation complete (7 confirmed, 1 plausible, 1 refuted). Advanced simulation underway.

| Claim                      | Paper Value  | Simulated            | Status                    |
| -------------------------- | ------------ | -------------------- | ------------------------- |
| ZIM coherence extension    | ~2×          | 2.00×                | ✅ Confirmed              |
| 1D frequency drift (γ=0.5) | ~33%         | 33.33%               | ✅ Confirmed              |
| 3D frequency drift (γ=0.3) | ~7%          | ~7%                  | ✅ Confirmed              |
| Max modes without ZIM      | ~41          | 41                   | ✅ Confirmed              |
| Max modes with ZIM         | ~322         | 322                  | ✅ Confirmed              |
| Storage density (ZIM)      | ~3.22 Tb/cm³ | 3.22 Tb/cm³          | ✅ Confirmed              |
| Geometry invariance        | <1% shift    | 0% (analytical)      | 🔶 Plausible              |
| Energy per operation       | fJ range     | **1114 fJ ≈ 1.1 pJ** | ⚠️ Refuted (system-level) |
| Excitation > thermal       | E >> k_BT    | 100× k_BT            | ✅ Confirmed              |

> **Critical finding (Phase 1b):** The cavity physics IS fJ-scale (excitation = 2.6 fJ), but the CMOS readout interface — primarily the ADC at 1000 fJ — pushes total system energy to ~1.1 pJ. This is still 10-100× below DRAM, but the paper's "fJ" headline needs qualification. See [notebook 07](notebooks/07_convergence_energy_mc.ipynb) and [ROADMAP.md](docs/ROADMAP.md) for mitigation strategies.

> **Key risk:** Ferrofluid Q factor remains unmeasured. Sensitivity analysis shows cell length L has the largest elasticity (−2.35). See [notebook 04](notebooks/04_sensitivity_analysis.ipynb) for the full risk assessment.

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
