# WCFOMA Simulations Package
# Wave-Coherent Field-Oriented Memory Architecture
#
# Submodules:
#   resonator_1d      - 1D damped oscillator model of ZIM-packed resonant chamber
#   resonator_3d      - 3D FDTD finite-difference wave solver
#   helmholtz_2d      - 2D Helmholtz eigenvalue solver (geometry-invariant cavities)
#   thermal           - Mode crowding and thermal drift analysis
#   sensitivity       - Parameter sensitivity sweeps & elasticity
#   ferrofluid        - Ferrofluid material model (Rosensweig)
#   interference      - Multi-mode interference & associative recall
#   convergence       - Grid convergence study (Richardson extrapolation)
#   cmos_interface    - CMOS energy budget model (4 tech nodes)
#   coupled_physics   - Coupled multiphysics (acoustic/EM/thermal)
#   noise_decoherence - Noise sources & decoherence analysis
#   mitigations       - Phase diffusion mitigation analysis
#   capacity          - Information-theoretic capacity & tech comparison
#   meep_fdtd         - MIT Meep FDTD scaffolding
#   common            - Shared parameters, constants, and utilities
#
# Phase 4 — Original-corpus-derived modules:
#   hopfield_recall       - Hopfield/Ising associative recall (substrate-independent)
#   ferroelectric_photonic - Ferroelectric MZI photonic cell model
#   photothermal_gating   - Photothermal viscosity gating for ferrofluid
#   forced_oscillation    - Forced-oscillation selective write/erase
#
# Phase 5 — Glass acoustic resonator (garage-scale prototype):
#   glass_resonator       - Glass rod eigenmode memory + perturbation encoding
#   mems_q_model          - 5-mechanism Q-factor prediction for MEMS resonators
#   spare_mace            - SPARE/MACE occult-to-engineering hypothesis experiments
#
# Phase 6 — Rewritability (telescope → instrument):
#   rewritability         - 7 experiments: virtual rewrite, binary sites, multi-shell
#
# Phase 7 — Site optimization & semantic mapping:
#   site_optimization     - Perturbation site placement, sensitivity matrix, layout optimizer
#   semantic_mapping      - Meaning-to-perturbation projection, codebooks, similarity preservation
#
# Phase 7b — Scranton–Dogon polysemic encoding:
#   scranton_dogon        - 6 experiments from Dogon cosmological symbol parallels
#
# Phase 8 — Tesla-informed phase-spectral encoding:
#   tesla_phase           - 4 experiments: phase independence, phase-enhanced recall,
#                           Q-multiplication energy asymmetry, scale invariance
