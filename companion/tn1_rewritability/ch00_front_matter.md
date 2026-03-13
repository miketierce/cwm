# Paths to Rewritability in Coherent Wave Memory

**Mike Tierce**
_Independent Researcher_
ORCID: [0009-0004-4483-5283](https://orcid.org/0009-0004-4483-5283)
Repository: [github.com/miketierce/wcfoma](https://github.com/miketierce/wcfoma)

**CWM Technical Note 1 — June 2025**
_Companion to: "Coherent Wave Memory: Wave-Based Storage and Computation in Acoustic Glass Resonators" (v16)_

---

## Abstract

Coherent Wave Memory (CWM) encodes information in the acoustic eigenmode spectrum of solid glass resonators and computes via wave interference. The companion paper [1] validates this architecture at macro scale (98.5 dB SNR, 9,380 thermally stable modes, 95.1 Gbit/cm³ projected MEMS density) and presents it as a read-only technology: data is written once by lithographic mass perturbation, read and searched by acoustic interference, and never altered.

This technical note asks the next question: _can CWM be made reconfigurable?_

We investigate seven engineering hypotheses across three tracks, each representing a different depth of hardware modification:

**Track A — Firmware-defined virtual rewriting** requires no physical changes to the resonator. By partitioning the coupling matrix's SVD basis into orthogonal subspaces, a single rod supports **4 independent virtual devices** with cross-talk below $3.5 \times 10^{-16}$. Mode-subset excitation yields **4 independent logical memories** from contiguous frequency bands. A library of spectral readout masks produces **4 firmware-selectable device configurations** from one physical rod.

**Track B — Binary perturbation sites** introduces discrete, toggleable mass-coupling points on the rod surface. With 12 binary sites, **193 of 200 sampled configurations** are spectrally distinguishable (7.6 bits of rewritable state). As few as **4 sites** suffice for reliable Hopfield associative recall, with capacity scaling as $N_{\text{sites}}^{0.27}$.

**Track C — Multi-shell resonator** models the Q-factor impact of adding physical rewrite hardware. MEMS electrostatic actuators impose only **0.48% Q penalty** at 16 switches, with up to **256 switches** before $Q$ drops below 5,000. A writable thin-film shell (Parylene, magnetostrictive, or phase-change material) can be **up to 100 nm thick** while maintaining $Q > 5{,}000$, providing 0.34% frequency-shift tuning range.

All seven hypotheses are confirmed by first-principles simulation (7 experiments, 68 automated tests, all passing). The results converge on a layered rewriting strategy: firmware-first virtual rewriting for immediate deployment on existing hardware, binary perturbation sites for moderate reconfigurability using commercial RF MEMS components, and writable shell coatings for continuous tunability in future device generations.

---
