# WCFOMA — Wave-Coherent Field-Oriented Memory Architecture

**A falsification-first research project testing whether information can be stored, computed on, and secured as resonant wave configurations in physical media.**

[![Status: Phase 4 Original Corpus Recovery](https://img.shields.io/badge/Status-Phase%204%20Corpus%20Recovery-blue)]()
[![Claims: 7 Confirmed · 1 Plausible · 4 Overestimates](https://img.shields.io/badge/Claims-7%20Confirmed%20·%201%20Plausible%20·%204%20Overestimates-orange)]()
[![Device Families: 3 Identified](https://img.shields.io/badge/Device%20Families-3%20Identified-blueviolet)]()
[![Tests: 211 Passing](https://img.shields.io/badge/Tests-211%20Passing-success)]()
[![Paper: v9](<https://img.shields.io/badge/Paper-v9%20(Jan%202026)-green>)]()

## What Is This?

WCFOMA proposes that if memory is physically a field, computation should operate by reshaping that field directly — unifying memory, computation, and security in a single physical substrate. The architecture uses:

- **Resonant eigenmodes** in ferrofluid/granular media as analog memory
- **Wave interference** for computation (associative recall, pattern matching)
- **Granular dilatancy** for passive, power-free mechanical security
- **Zero-index metamaterials (ZIMs)** for enhanced mode stability
- **Optional quantum correlations** for verification (not required for core operation)

The paper projects 10–100× energy efficiency improvements over von Neumann architectures for AI workloads, with Tb/cm³ storage densities. **This repo exists to rigorously test those claims.**

### Three Device Families

Phase 4 archaeology of the original research corpus (~140 files across 7 scales) revealed that WCFOMA spans **three distinct device families** — only the weakest was modeled in Phases 0–3:

| Family                     | Substrate               | Write Mechanism                | Read Mechanism            | TRL | Density Potential       |
| -------------------------- | ----------------------- | ------------------------------ | ------------------------- | --- | ----------------------- |
| **Ferrofluid Acoustic**    | Nanoparticle suspension | Acoustic/magnetic excitation   | Optical (Faraday)         | 2–3 | 0.02 Tb/cm³ (mitigated) |
| **Ferroelectric Photonic** | HZO/BaTiO₃ on SiN MZI   | Voltage pulse (coercive field) | Optical (interferometric) | 4–5 | 1–10 Tb/cm³             |
| **Magnonic Spin-Wave**     | YIG thin film           | RF antenna excitation          | Inductive/BLS             | 3–4 | 0.1–1 Tb/cm³            |

Phase 4 modules recover substrate-independent computation (Hopfield/Ising recall) and the most experimentally grounded variant (ferroelectric photonic), plus two mechanisms that attack the ferrofluid's core weakness (phase diffusion): photothermal viscosity gating and forced-oscillation selective write/erase.

## Project Philosophy

> We're either going to disprove this or find something useful along the way.

Every claim in the paper is tagged as DEMONSTRATED, PROPOSED, PROJECTED, or SIMULATED. This repo implements a **kill-criterion framework** — each experiment has explicit thresholds that, if not met, indicate the approach is unviable. Negative results are valuable and publishable.

## Repository Structure

```
wcfoma/
├── paper/                      # The paper and addenda
│   └── v9.md                   # Canonical paper (do not modify)
├── simulations/                # Core physics simulation modules (19)
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
│   ├── coupled_physics.py      # Coupled acoustic/EM/thermal SVEA simulation
│   ├── noise_decoherence.py    # 5-source noise budget & mode lifetime analysis
│   ├── mitigations.py          # Phase diffusion mitigation analysis
│   ├── capacity.py             # Shannon capacity & technology comparison
│   ├── meep_fdtd.py            # MIT Meep FDTD scaffolding (Phase 1)
│   ├── hopfield_recall.py      # Hopfield/Ising associative recall (Phase 4)
│   ├── ferroelectric_photonic.py # Ferroelectric photonic MZI cell (Phase 4)
│   ├── photothermal_gating.py  # Photothermal viscosity gating (Phase 4)
│   └── forced_oscillation.py   # Forced-oscillation selective write/erase (Phase 4)
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
│   ├── 07_convergence_energy_mc.ipynb # Grid convergence, CMOS energy, MC tamper
│   ├── 08_coupled_decoherence.ipynb   # Coupled physics & noise/decoherence analysis
│   ├── 09_mitigation_analysis.ipynb   # Phase diffusion mitigation strategies
│   ├── 10_capacity_scaling_comparison.ipynb  # Shannon capacity, scaling laws, tech comparison
│   └── 11_phase4_original_corpus_recovery.ipynb  # Phase 4: 3 device families, Hopfield recall, ferroelectric photonic, photothermal gating, forced oscillation
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
├── tests/                      # Unit & integration tests (211 passing)
│   ├── test_simulations.py     # Phase 0 simulation tests (18)
│   ├── test_phase1.py          # Phase 1a module tests (29)
│   ├── test_phase1b.py         # Phase 1b module tests (23)
│   ├── test_phase2.py          # Phase 2 coupled/noise tests (32)
│   ├── test_mitigations.py     # Phase 2b mitigation tests (26)
│   ├── test_capacity.py        # Phase 3 capacity/comparison tests (27)
│   └── test_phase4.py          # Phase 4 corpus recovery tests (56)
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

## Current Status: Phase 4 Original Corpus Recovery

Phases 0–3 focused exclusively on the ferrofluid acoustic variant, identifying serious SNR limitations (phase diffusion dominant at 77.5%). Phase 4 performed an archaeology of the original research corpus (~140 files across 7 scales), discovering that WCFOMA spans **three distinct device families**. Four new simulation modules recover the most promising dropped ideas.

### Phase 4 Modules

| Module                      | What It Does                                                | Key Finding                                                                                                                               |
| --------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `hopfield_recall.py`        | Substrate-independent Hopfield/Ising associative recall     | Binary/trinary networks, capacity α_c ≈ 0.138, optical interference recall — computation works regardless of which device family hosts it |
| `ferroelectric_photonic.py` | HZO/BaTiO₃ ferroelectric on SiN Mach-Zehnder interferometer | 10⁵ endurance cycles, 10-year retention, >30 dB extinction — the most experimentally grounded WCFOMA variant (TRL 4–5)                    |
| `photothermal_gating.py`    | Laser-driven viscosity gating via Arrhenius heating         | Directly attacks phase diffusion: η×10⁴ increase at ΔT=40K in agarose gel, spatial selectivity with 2× beam-waist confinement             |
| `forced_oscillation.py`     | Frequency-selective mode addressing via forced oscillation  | Selective write with <1% cross-talk at Q≥50, multi-mode addressing, three erase strategies with energy budgets                            |

### Claims Validation (Phases 0–3, unchanged)

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

> **🔴 CRITICAL (Phase 2):** Nanoparticle Brownian phase diffusion dominates the noise budget at **77.5%**, producing **SNR = −6.5 dB** and **0 reliable modes** at default micro-cell (10 µm)³ parameters. The paper does not model this noise source. **However, mitigation analysis (notebook 09) shows the architecture IS viable** with gel immobilization (η×100) + improved optical readout (≥10⁸ photons), achieving SNR > 13 dB and 10 reliable modes at ~10 pJ total energy. See [ROADMAP.md](docs/ROADMAP.md) for full analysis.

> **📊 Phase 3 — Shannon Capacity (notebook 10):** The paper's "10 bits/mode" requires 60 dB SNR — never stated or justified. At mitigated SNR (13.5 dB), Shannon gives **2.3 bits/mode** (4.4× overestimate). Density drops from paper's 1–10 Tb/cm³ to **0.023 Tb/cm³** (44–439× below). WCFOMA sits between DRAM and PCM in energy–density space — competitive but NOT the "10–100× improvement" claimed. The "unified" compute locality remains the architecture's unique value proposition.

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full phased roadmap including kill criteria.

- **Phase 0** (Complete): Computational validation — reproduce and stress-test paper simulations
- **Phase 1** (Complete): Advanced simulation — multiphysics, realistic materials, convergence studies
- **Phase 2** (Complete): Noise & decoherence — phase diffusion identified as dominant noise source (77.5%)
- **Phase 3** (Complete): Shannon capacity — quantified gap between claims and reality (2.3 bits/mode mitigated)
- **Phase 4** (Complete): Original corpus recovery — 3 device families, 4 new modules, substrate-independent computation
- **Phase 5** (Next): Benchtop prototype — macro-scale ferrofluid resonator OR ferroelectric photonic MZI cell
- **Phase 6** (Future): Micro-scale arrays with fiber optic integration
- **Phase 7** (2029+): Domain-specific AI accelerator (if warranted)

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
