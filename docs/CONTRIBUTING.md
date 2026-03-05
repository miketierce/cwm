# Contributing to WCFOMA

Thank you for your interest in the Wave-Coherent Field-Oriented Memory Architecture project.

## Project Philosophy

This is a **falsification-first** research project. We are rigorously testing whether WCFOMA's theoretical claims hold under increasing levels of scrutiny — from simplified simulations through benchtop prototypes. Negative results are valuable and publishable.

## How to Contribute

### 1. Run and Validate Simulations

- Clone the repo, install dependencies (`pip install -r requirements.txt`)
- Run the experiment notebooks in `notebooks/`
- Report whether your results match the paper's claims
- File issues for discrepancies

### 2. Improve Simulations

- Increase grid resolution (N≥20) for convergence studies
- Add realistic material models (ferrofluid dispersion, temperature dependence)
- Implement full FDTD with Meep or similar
- Add nonlinear coupling between modes

### 3. Literature Verification

- Help verify/correct the citations flagged in [ROADMAP.md](docs/ROADMAP.md)
- Find relevant papers on ferrofluid acoustics, ZIM fabrication, or granular dilatancy
- Identify prior art that supports or contradicts specific claims

### 4. Prototype Design

- Contribute to Prototype A BOM and assembly instructions
- Design 3D-printable ZIM structures
- Propose readout circuit designs
- Share experience with ferrofluid handling

### 5. Theoretical Analysis

- Derive the ZIM damping reduction factor from first principles
- Analyze nonlinear mode coupling in ferrofluids
- Model thermal noise effects on mode distinguishability
- Develop information-theoretic bounds on storage density

## Code Standards

- Python 3.10+
- Type hints on all public functions
- Docstrings with parameter descriptions
- Experiments should be reproducible from a single function call
- Use `dataclass` for result containers
- Plots should be publication-quality (see `analysis/plotting.py` style guide)

## Filing Issues

Use labels:

- `simulation` — Computational modeling issues
- `experiment` — Physical experiment design
- `theory` — Theoretical analysis
- `citation` — Reference verification
- `kill-criterion` — A result that challenges viability
- `actualization` — A result that supports viability

## Paper Versions

The canonical paper is in `paper/v9.md`. Do not modify it directly — it represents the published state. Proposed revisions should be discussed in issues first.
