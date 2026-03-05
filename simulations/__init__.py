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
