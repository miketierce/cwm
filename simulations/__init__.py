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
#
# Phase 9a — Chladni-informed 2D plate eigenmode memory:
#   chladni_plates        - 4 experiments: plate mode scaling, symmetry partition,
#                           2D placement optimization, degeneracy splitting
#
# Phase 9b — Békésy cochlear eigenmode memory (1 confirmed, 3 killed):
#   bekesy_cochlea        - 4 experiments: tapered mode density (killed), log-spacing
#                           recall (killed), active Q-boosting (confirmed), cochlear
#                           window (killed)
#
# Phase 9c — Franklin-informed phase retrieval (0 confirmed, 4 killed):
#   franklin_phase        - 4 experiments: direct methods / tangent formula (killed),
#                           Patterson function (killed), Gerchberg-Saxton / HIO (killed),
#                           molecular replacement (killed)
#
# Phase 9d — Leibniz-informed binary encoding (3 confirmed, 1 killed):
#   leibniz_binary        - 4 experiments: binary quantisation of recall (confirmed),
#                           Gray coding (killed), monadic reconstruction (confirmed),
#                           hexagram codebook (confirmed)
#
# Phase 9e — Gabor holographic distributed memory:
#   gabor_holographic     - 4 experiments: shift-tolerant recall, sub-aperture
#                           degradation, bandwidth ceiling, crosstalk envelope
#
# Phase 9f — Zeeman perturbation-induced level splitting:
#   zeeman_splitting      - 4 experiments: anomalous splitting ratio, selection-rule
#                           channel count, quadratic Zeeman, multi-site field geometry
#
# Phase 9g — Kepler harmonic resonance ratios:
#   kepler_harmonic       - 4 experiments: diatonic partitioning (killed), consonance-
#                           weighted recall (killed), octave equivalence (confirmed),
#                           harmonic capacity scaling (confirmed)
#
# Phase 9h — Boltzmann timescale hierarchy & mode populations:
#   boltzmann_timescale   - 4 experiments: decade spacing universality (confirmed),
#                           spectral reddening cascade (killed), optimal readout
#                           window (killed), partition function capacity (killed)
#
# Phase 9i — Gor'kov acoustic radiation force & optimal site placement:
#   gorkov_radiation      - 4 experiments: Gor'kov-optimised placement (killed),
#                           acoustic contrast factor (confirmed), Bjerknes
#                           hybridisation (killed), dual-axis encoding (killed)
#
# Phase 9j — Fabry-Pérot acoustic cavity finesse:
#   fabry_perot_cavity    - 4 experiments: finesse-Q equivalence (confirmed),
#                           Airy peak shape (killed), scanning readout (killed),
#                           end-condition engineering (confirmed)
#
# Phase 9k — Shannon–Nyquist channel capacity & optimal mode allocation:
#   shannon_capacity      - 4 experiments: waterfilling gain (killed),
#                           Nyquist 2K minimum (confirmed), capacity
#                           utilisation (confirmed), mutual information (killed)
#
# Phase 9l — Mathieu–Floquet parametric mode amplification:
#   mathieu_parametric    - 4 experiments: parametric gain (confirmed),
#                           mode selectivity (confirmed), stability boundary
#                           (confirmed), parametric + CW readout (confirmed)
#
# Phase 9m — Coronal seismology: astrophysical validation:
#   coronal_seismology    - 7 experiments: rational-position degeneracy (confirmed),
#                           mode-family independence (confirmed), logarithmic
#                           capacity ceiling (confirmed), P₁/2P₂ correlation
#                           (killed), footpoint finesse (confirmed), perturbation
#                           scaling (confirmed), optimal probe spacing (confirmed)
