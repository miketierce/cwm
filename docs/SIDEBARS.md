# Historical Sidebar Research Tracker

## Purpose

Each sidebar explores parallels between a historical figure's work and SEM physics.
The goal is **not** to claim ancestry — it is to identify **testable engineering
hypotheses** that the parallel suggests, implement simulations, and either confirm
or kill each hypothesis with quantitative evidence. Every sidebar must produce at
least one simulation module with automated tests, and every confirmed result must
survive integration into the paper without regressing existing tests.

## Quality Gates (apply to every sidebar)

| Gate                             | Criterion                                                                                                                                 | Enforced by   |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------- |
| **G1 — Hypothesis registration** | All hypotheses written as falsifiable H-statements with kill criteria _before_ writing code                                               | This document |
| **G2 — No speculation in paper** | Paper text cites only simulation results + the mathematical identity that underlies them; historical context is confined to §14.2 bullets | Code review   |
| **G3 — Zero regression**         | Full test suite passes before and after integration (`pytest` exit 0, count ≥ previous)                                                   | CI / manual   |
| **G4 — Reproducibility**         | Every experiment accepts an RNG seed and produces identical output on re-run                                                              | Seed tests    |
| **G5 — Kill honesty**            | Failed hypotheses are documented here with "KILLED" status and a one-line reason — not silently dropped                                   | This document |

---

## Progress Dashboard

| Sidebar | Figure               | Module                   | Tests | Hypotheses               | Status      |
| ------- | -------------------- | ------------------------ | ----- | ------------------------ | ----------- |
| **S1**  | Spare / Mace         | `spare_mace.py`          | 62    | H1–H6: 6/6 confirmed     | ✅ Complete |
| **S2**  | Scranton / Dogon     | `scranton_dogon.py`      | 62    | H7–H12: 6/6 confirmed    | ✅ Complete |
| **S3**  | Tesla                | `tesla_phase.py`         | 50    | H-T1–T4: 4/4 confirmed   | ✅ Complete |
| **S4**  | Chladni              | `chladni_plates.py`      | 69    | H-C1–C4: 4/4 confirmed   | ✅ Complete |
| **S5**  | Békésy               | `bekesy_cochlea.py`      | 68    | H-B1–B4: 1/4 confirmed   | ✅ Complete |
| **S6**  | Franklin (Rosalind)  | `franklin_phase.py`      | 69    | H-F1–F4: 0/4 confirmed   | ✅ Complete |
| **S7**  | Leibniz              | `leibniz_binary.py`      | 73    | H-L1–H-L4: 3/4 confirmed | ✅ Complete |
| **S8**  | Gabor                | `gabor_holographic.py`   | 77    | H-G1–G4: 1/4 confirmed   | ✅ Complete |
| **S9**  | Zeeman (Scranton)    | `zeeman_splitting.py`    | 75    | H-Z1–Z4: 4/4 confirmed   | ✅ Complete |
| **S10** | Kepler (Scranton)    | `kepler_harmonic.py`     | 74    | H-K1–K4: 2/4 confirmed   | ✅ Complete |
| **S11** | Boltzmann (Scranton) | `boltzmann_timescale.py` | —     | H-Bt1–Bt4: 0/4 pending   | 📋 Planned  |
| **S12** | Gor'kov (Scranton)   | `gorkov_radiation.py`    | —     | H-ARF1–ARF4: 0/4 pending | 📋 Planned  |

**Running totals:** 36 modules · 1185 tests · test count must only go up.

---

## S4 — Ernst Chladni (1756–1827): 2D Plate Eigenmode Memory

### Core insight

Chladni's sand-on-plate experiments are **sensitivity maps**: sand collects
at nodal lines (zero displacement = zero perturbation sensitivity). The
SEM sensitivity function sin²(nπx/L) is the 1D version of what Chladni
visualized in 2D. Extending SEM from rods to membranes could unlock
quadratically more modes.

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                                                                 | Kill criterion                                                   | Builds on                |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------ |
| **H-C1** | A 2D plate of the same material and footprint as a 1D rod supports ≥ 4× more thermally-stable eigenmodes, because mode indices $(n,m)$ scale as $n_{\max}^2$ vs $n_{\max}$.                                                                                                                               | Mode count < 2× 1D rod                                           | §2.1 n_max formula       |
| **H-C2** | Plate eigenmodes cluster into symmetry families (nodal-line topology classes) that can be read out independently, enabling a 2D analogue of polysemic readout (§11.5) with ≥ 3 independent channels.                                                                                                      | Fewer than 2 separable symmetry families                         | §11.5 polysemic readout  |
| **H-C3** | Perturbation sensitivity at point $(x,y)$ on a plate depends on the **local curvature** of the nearest nodal line, giving a 2D sensitivity function that generalizes sin²(nπx/L). The optimal perturbation placement on a plate requires a fundamentally different strategy than 1D golden-ratio spacing. | 2D optimal placement is within 5% of naïve grid → no new insight | §7 site optimization     |
| **H-C4** | Square plates have degenerate mode pairs $(n,m)/(m,n)$ that split under asymmetric perturbation. This 2D degeneracy splitting produces ≥ 2× the avoided-crossing information bonus of the 1D case (+160%, §11.3).                                                                                         | 2D hybridization bonus < 1D bonus                                | §11.3 mode hybridization |

### Implementation plan

| Step | Task                                                                                                             | Artifact     | Status                  |
| ---- | ---------------------------------------------------------------------------------------------------------------- | ------------ | ----------------------- |
| C-1  | Review `helmholtz_2d.py` — assess whether it can be extended to plate eigenproblems or if a new solver is needed | Design notes | ✅ Done                 |
| C-2  | Implement `simulations/chladni_plates.py` with 4 experiment functions + dataclass results                        | Module       | ✅ Done                 |
| C-3  | Write `tests/test_chladni_plates.py` — target ≥ 40 tests                                                         | Test file    | ✅ Done (69 tests)      |
| C-4  | Run experiments, tune parameters until all 4 confirm or are honestly killed                                      | Results      | ✅ Done (4/4 confirmed) |
| C-5  | Update `simulations/__init__.py` (Phase 9a)                                                                      | Package      | ✅ Done                 |
| C-6  | Add §11.8 or new subsection to paper (if confirmed) + §14.2 historical bullet                                    | Paper        | ✅ Done                 |
| C-7  | Run full test suite — must exceed 680 with zero failures                                                         | Regression   | ✅ Done (749 tests)     |
| C-8  | Regenerate both PDFs                                                                                             | Deliverable  | ✅ Done                 |

### External data sources (for validation, not curve-fitting)

- Chladni's original frequency tables (1787, _Entdeckungen über die Natur des Klanges_)
- COMSOL Multiphysics benchmarks for rectangular/circular plate eigenfrequencies
- MEMS microphone membrane eigenfrequency literature (Knowles, InvenSense datasheets)
- Structural acoustics modal analysis datasets (aircraft panel testing)

### Key equations to validate

- Rectangular plate eigenfrequencies: $f_{nm} = \frac{1}{2}\sqrt{\frac{D}{\rho h}}\left[\left(\frac{n}{a}\right)^2 + \left(\frac{m}{b}\right)^2\right]$
- Kirchhoff plate 2D sensitivity function (the generalization of sin²)
- Degeneracy condition: square plate, $f_{nm} = f_{mn}$ when $a = b$

---

## S5 — Georg von Békésy (1899–1972, Nobel 1961): Cochlear Eigenmode Memory

### Core insight

The cochlea is a **biological SEM device**: a tapered resonant cavity that maps
eigenfrequencies to spatial positions along the basilar membrane. Evolution has
optimized eigenmode-based information encoding for ~200 million years. The
cochlea's logarithmic frequency mapping, active amplification (outer hair cells
as Q-boosters), and noise rejection strategies may suggest better SEM designs.

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                   | Kill criterion                                   | Builds on                    |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ---------------------------- |
| **H-B1** | A tapered rod (continuously varying cross-section) achieves higher mode density than a uniform rod of the same length, because the local wave speed varies and modes compress toward the thin end — the cochlear "tonotopic" effect.                        | Tapered mode count ≤ uniform mode count          | §2.1, §6 scaling             |
| **H-B2** | Logarithmic frequency spacing (cochlea-like) improves associative recall noise tolerance compared to the uniform linear spacing of a constant-cross-section rod, because log spacing allocates more resolution to low-frequency modes where SNR is highest. | Log-spaced recall accuracy ≤ linear-spaced       | §11 recall, interference.py  |
| **H-B3** | Active Q-boosting — feeding energy into selected modes (analogous to outer hair cell motility) — can compensate for anchor loss at MEMS scale, raising effective Q above the passive limit predicted by the 5-mechanism model (§7).                         | Active Q_eff < 1.5× passive Q                    | §7 Q-factor, mems_q_model.py |
| **H-B4** | The cochlea's critical-band masking (frequency-dependent noise rejection) maps onto an optimal **windowing function** for SEM's FFT readout that outperforms the rectangular window currently assumed.                                                      | Cochlear window SNR gain < 1 dB over rectangular | §8.4 readout, cw_readout.py  |

### Implementation plan

| Step | Task                                                                                                            | Artifact     | Status                       |
| ---- | --------------------------------------------------------------------------------------------------------------- | ------------ | ---------------------------- |
| B-1  | Literature review: basilar membrane mechanics, tonotopic mapping, outer hair cell amplification, critical bands | Design notes | ✅ Done                      |
| B-2  | Implement `simulations/bekesy_cochlea.py` with 4 experiment functions                                           | Module       | ✅ Done                      |
| B-3  | Write `tests/test_bekesy_cochlea.py` — target ≥ 40 tests                                                        | Test file    | ✅ 68 tests                  |
| B-4  | Run experiments, confirm or kill                                                                                | Results      | ✅ 1/4 confirmed, 3/4 killed |
| B-5  | Update `simulations/__init__.py` (Phase 9b)                                                                     | Package      | ✅ Done                      |
| B-6  | Paper integration: §11.9 subsection + §14.2 bullet + abstract (viii) + §11.6 item 8                             | Paper        | ✅ Done                      |
| B-7  | Full regression suite — must exceed prior count                                                                 | Regression   | ✅ 817 pass, 31 s            |
| B-8  | Regenerate PDFs                                                                                                 | Deliverable  | ✅ Done                      |

### External data sources

- Greenwood frequency-position function: $f = A(10^{ax} - k)$ with published constants
- Basilar membrane stiffness gradient data (Békésy 1960, von Békésy & Rosenblith)
- Otoacoustic emission (OAE) databases — direct measurement of cochlear eigenfrequencies
- Cochlear implant electrode-frequency allocation maps (Cochlear Ltd, MED-EL)
- Critical bandwidth measurements (Zwicker 1961, Moore & Glasberg 1983)

### Key equations to validate

- Tapered-rod eigenfrequencies (WKB approximation for non-uniform waveguide)
- Greenwood function fit to basilar membrane data
- Active Q-boosting energy budget: $P_{\text{active}} = \omega E_{\text{stored}} / (Q_{\text{target}} - Q_{\text{passive}})$

---

## S6 — Rosalind Franklin (1920–1958): Phase Retrieval and Spectral Inversion

### Core insight

X-ray crystallography measures diffraction **intensities** (amplitudes squared)
but loses **phases** — the "phase problem." Crystallographers spent decades
developing algorithms to recover lost phase information from amplitude-only
data. SEM's readout is also an FFT of the rod's response; the Tesla sidebar
showed that phase carries independent information (§11.7). Franklin's domain
offers phase-retrieval algorithms that may improve SEM's noise tolerance and
enable reconstruction of the perturbation pattern from readout data (the
**inverse problem**).

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                                                                                                | Kill criterion                                            | Builds on                            |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------ |
| **H-F1** | Applying crystallographic **direct methods** (Hauptman–Karle tangent formula) to SEM readout data recovers perturbation positions from amplitude-only spectra with ≥ 80% accuracy, even when phase information is unavailable.                                                                                                           | Reconstruction accuracy < 50%                             | §11.7 phase encoding, tesla_phase.py |
| **H-F2** | **Patterson function** analysis (autocorrelation of the spectrum) reveals inter-site distances without phase, enabling partial decoding of the perturbation pattern. The number of recoverable distance constraints scales as $K(K-1)/2$ for $K$ sites.                                                                                  | Fewer than $K$ independent distance constraints recovered | §7 site optimization                 |
| **H-F3** | Iterative phase retrieval (Gerchberg–Saxton / hybrid input-output) converges to the correct perturbation pattern from amplitude-only FFT data within 100 iterations for patterns with ≤ 20 sites.                                                                                                                                        | Non-convergence or > 1000 iterations for trivial cases    | §11.7 H-T1, H-T2                     |
| **H-F4** | The **molecular replacement** technique (using a known reference pattern to bootstrap phase estimates for an unknown pattern) maps onto SEM's associative recall: using stored patterns as "search models" to phase the readout. This produces measurably better recall accuracy than the current amplitude-only or complex dot product. | MR-recall accuracy ≤ complex recall (H-T2)                | §11.7 H-T2, interference.py          |

### Implementation plan

| Step | Task                                                                                           | Artifact     | Status            |
| ---- | ---------------------------------------------------------------------------------------------- | ------------ | ----------------- |
| F-1  | Literature review: direct methods, Patterson function, Gerchberg-Saxton, molecular replacement | Design notes | ✅                |
| F-2  | Implement `simulations/franklin_phase.py` with 4 experiment functions                          | Module       | ✅                |
| F-3  | Write `tests/test_franklin_phase.py` — target ≥ 40 tests                                       | Test file    | ✅ 69             |
| F-4  | Run experiments, confirm or kill                                                               | Results      | ✅ 0/4            |
| F-5  | Update `simulations/__init__.py` (Phase 9c)                                                    | Package      | ✅                |
| F-6  | Paper integration (§11.10 + §14.2 + §11.6 item 9)                                              | Paper        | ✅                |
| F-7  | Full regression suite                                                                          | Regression   | ✅ 886 pass, 31 s |
| F-8  | Regenerate PDFs                                                                                | Deliverable  | ✅                |

### Experiment results

| ID       | Verdict    | Key metric                                                                  |
| -------- | ---------- | --------------------------------------------------------------------------- |
| **H-F1** | **KILLED** | Reconstruction 45.8% (<80%); DM recall 16%; phase error 86.1° (near-random) |
| **H-F2** | **KILLED** | 0/15 inter-site distances recovered; Patterson peaks at wrong positions     |
| **H-F3** | **KILLED** | Did not converge: 200 iterations, error 0.809 (threshold: <100 iterations)  |
| **H-F4** | **KILLED** | MR recall 96.5% = amplitude-only 96.5% < complex 99.0%                      |

**Root cause:** SEM's $\sin^2(n\pi x/L)$ sensitivity encoding is algebraically incompatible with the Fourier-based encoding ($e^{2\pi i n x}$) that crystallographic phase-retrieval algorithms require.

### External data sources

- Protein Data Bank (PDB): 200,000+ solved crystal structures with known phases
- International Tables for Crystallography, Vol. A (symmetry operations)
- Hauptman & Karle, "Solution of the Phase Problem" (Nobel 1985)
- Gerchberg–Saxton algorithm convergence benchmarks (optics literature)
- CCP4 software suite documentation (phase retrieval implementations)

### Key equations to validate

- Patterson function: $P(\mathbf{u}) = \sum_h |F_h|^2 e^{2\pi i \mathbf{h} \cdot \mathbf{u}}$
- Tangent formula: $\tan \phi_h = \frac{\sum_k |E_k E_{h-k}| \sin(\phi_k + \phi_{h-k})}{\sum_k |E_k E_{h-k}| \cos(\phi_k + \phi_{h-k})}$
- Gerchberg–Saxton iteration: alternating real-space and Fourier-space constraints
- SEM-adapted molecular replacement merit function

---

## S7 — Gottfried Wilhelm Leibniz (1646–1716): Binary Encoding and Monadic Compression

### Core insight

Leibniz invented binary arithmetic (1679) after studying the I Ching's 64
hexagrams — 6-bit binary codes used for 3,000+ years. His monadology (1714)
proposed that each indivisible "monad" reflects the entire universe from its
own perspective — a philosophical eigenmode (each mode encodes the full cavity
geometry). The I Ching connection extends the Dogon sidebar: another ancient
civilization independently encoding information in compact combinatorial
symbols. The binary-arithmetic connection asks whether SEM's continuous-valued
eigenmode encoding benefits from quantization, error correction, or
combinatorial codebook design.

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                                                  | Kill criterion                                        | Builds on                         |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------- | --------------------------------- |
| **H-L1** | Quantizing eigenmode readout values to binary (1-bit per mode) retains ≥ 70% of the associative recall accuracy of continuous-valued readout, because Hopfield recall is robust to binarization. This maps Leibniz's insight: binary is sufficient for computation.                        | Binary recall < 50% of continuous                     | §11.1 pruning, hopfield_recall.py |
| **H-L2** | Applying **Gray coding** to the quantized eigenmode values (so that adjacent perturbation levels differ by only 1 bit) improves noise tolerance by ≥ 20% compared to natural binary, because single-bit errors map to minimum-distance perturbation changes.                               | Gray-coded noise tolerance ≤ natural binary           | §8.4, capacity.py                 |
| **H-L3** | The **monadic property** — that each eigenmode's response encodes information about the _entire_ perturbation pattern, not just local perturbations — enables error correction: any $n_{\max}/2$ modes suffice to reconstruct the full pattern (analogous to Reed–Solomon erasure coding). | Reconstruction from $n_{\max}/2$ modes < 50% accuracy | §2.1 eigenmode encoding           |
| **H-L4** | An I Ching–inspired **hexagram codebook** (64 codewords of 6-bit patterns) achieves better energy efficiency than dense encoding for small-payload applications (sensor IDs, authentication tokens), because the sparse combinatorial code tolerates higher noise per bit.                 | Hexagram codebook error rate > dense code at same SNR | semantic_mapping.py               |

### Implementation plan

| Step | Task                                                                                                                 | Artifact     | Status                     |
| ---- | -------------------------------------------------------------------------------------------------------------------- | ------------ | -------------------------- |
| L-1  | Literature review: binary vs continuous Hopfield, Gray codes, Reed-Solomon for analog systems, I Ching combinatorics | Design notes | ✅                         |
| L-2  | Implement `simulations/leibniz_binary.py` with 4 experiment functions                                                | Module       | ✅                         |
| L-3  | Write `tests/test_leibniz_binary.py` — target ≥ 40 tests                                                             | Test file    | ✅ 73 tests                |
| L-4  | Run experiments, confirm or kill                                                                                     | Results      | ✅ 3/4 confirmed, 1 killed |
| L-5  | Update `simulations/__init__.py` (Phase 9d)                                                                          | Package      | ✅                         |
| L-6  | Paper integration: §11.11 subsection + §14.2 bullet + abstract (x) + §11.6 item 10                                   | Paper        | ✅                         |
| L-7  | Full regression suite                                                                                                | Regression   | ✅ 959 pass                |
| L-8  | Regenerate PDFs                                                                                                      | Deliverable  | ✅                         |

### Experiment results

| ID       | Verdict       | Key metric                                                                                   |
| -------- | ------------- | -------------------------------------------------------------------------------------------- |
| **H-L1** | **CONFIRMED** | Binary Hamming recall 87.5% vs continuous L2 100%; retention 87.5% ≥ 70%                     |
| **H-L2** | **KILLED**    | Same fingerprint set; improvement −8.4% (Gray ≈ natural); Gray is bijection → identical sets |
| **H-L3** | **CONFIRMED** | Full 100%, half (N/2) 100%, quarter (N/4) 100%; min modes for ≥50% = K = 8                   |
| **H-L4** | **CONFIRMED** | Hexagram error 0.513 < dense error 0.668; 6-site binary beats 3-site 4-level                 |

**Root cause (H-L2 kill):** Gray code is a bijection on {0,…,n−1}, so natural and Gray codebooks enumerate the _same set_ of mass patterns — they just assign different symbol labels to the same codewords. Since the ML decoder operates in fingerprint space (L2 nearest-neighbour), the symbol-to-codeword mapping is invisible: both produce identical fingerprint sets and therefore identical average error rates.

### External data sources

- I Ching hexagram tables (King Wen sequence, binary mapping)
- Gray code error-rate benchmarks (communications engineering literature)
- Reed–Solomon coding theory (Berlekamp 1968, standard references)
- Binary Hopfield network literature (Amit, Gutfreund & Sompolinsky 1985)
- Sparse coding efficiency results (compressed sensing, Donoho 2006)

### Key equations to validate

- Binary Hopfield capacity: $P_{\max} \approx N / (2 \ln N)$ (Amit et al.)
- Gray code Hamming distance: adjacent values differ by exactly 1 bit
- Reed–Solomon minimum distance: $d = n - k + 1$ for $(n, k)$ code
- Sparse code SNR advantage: $\text{SNR}_{\text{gain}} = 10 \log_{10}(N/K)$ dB for $K$-of-$N$ code

---

## S8 — Dennis Gabor (1900–1979, Nobel 1971): Holographic Distributed Memory

### Core insight

Gabor invented holography (1948) and proposed holographic associative memories
(1969). When information is distributed across a medium via wave interference,
the system acquires four structural properties: shift tolerance, graceful
degradation under partial loss, a bandwidth-determined capacity ceiling, and
a predictable crosstalk envelope between stored patterns. SEM already exhibits
the first group of holographic properties (distributed encoding, interference
recall, multiplexing). This sidebar tests whether the _quantitative_ predictions
from holographic theory (Gabor, Kogelnik, Leith & Upatnieks) hold for SEM's
sin²-based encoding.

**Critical constraint — the Franklin kill (S6):** SEM's sin²(nπx/L) encoding
is algebraically incompatible with Fourier-based phase-retrieval algorithms
(4:0 kill in S6). **None of the hypotheses below use Fourier-phase-retrieval
methods.** They test _structural_ properties of holographic systems — shift
tolerance, degradation scaling, bandwidth utilization, and crosstalk envelopes —
which depend on distributed wave encoding, not on the specific basis functions.

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                                                                                         | Kill criterion                                                                                | Builds on                               |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | --------------------------------------- |
| **H-G1** | **Shift-tolerant recall.** When the query pattern is spatially shifted by δ (all perturbation sites displaced), the recall score R(δ) tracks the autocorrelation of the sin²(nπx/L) sensitivity kernel. SEM should exhibit a measurable "shift-tolerance width" Δ_s ≈ L/(2n_max).                                                 | R(δ) shows no structure (flat/random), OR autocorrelation width deviates > 2× from prediction | §2.3 recall, hopfield_recall.py         |
| **H-G2** | **Sub-aperture degradation curve.** Reconstruction accuracy from K of N modes follows a smooth, monotonically increasing function of K/N. Holographic aperture theory (Leith & Upatnieks 1964) predicts linear scaling: accuracy ∝ K/N.                                                                                           | Accuracy vs. K/N is non-monotonic OR best fit R² < 0.7                                        | §11.11 H-L3, leibniz_binary.py          |
| **H-G3** | **Bandwidth utilization ceiling.** A bandwidth-limited capacity ceiling N_BW can be computed from total spectral range and per-mode linewidth. Each capacity-enhancing technique (polysemic, null-space, phase-spectral) should increase the utilization ratio η = P_eff / N_BW monotonically.                                    | η does NOT increase monotonically with added techniques                                       | §11.6 combined capacity                 |
| **H-G4** | **Crosstalk selectivity envelope.** Kogelnik's (1969) coupled-wave theory predicts inter-hologram crosstalk follows sinc² as a function of spectral separation. Two SEM patterns in mode subsets with fractional overlap Ω should have crosstalk C(Ω) following a smooth envelope (sinc², Gaussian, or linear fit with R² ≥ 0.7). | Crosstalk vs. overlap has no smooth fit (R² < 0.7 for sinc², Gaussian, and linear)            | §11.5 polysemic (one data point: 0.003) |

### Implementation plan

| Step | Task                                                                                         | Artifact     | Status                     |
| ---- | -------------------------------------------------------------------------------------------- | ------------ | -------------------------- |
| G-1  | Literature review: Gabor 1948/1969, van Heerden 1963, Kogelnik 1969, Psaltis & Brady 1990    | Design notes | ✅                         |
| G-2  | Implement `simulations/gabor_holographic.py` with 4 experiment functions + dataclass results | Module       | ✅                         |
| G-3  | Write `tests/test_gabor_holographic.py` — target ≥ 40 tests                                  | Test file    | ✅ 77 tests                |
| G-4  | Run experiments, confirm or kill                                                             | Results      | ✅ 1/4 confirmed, 3 killed |
| G-5  | Update `simulations/__init__.py` (Phase 9e)                                                  | Package      | ✅                         |
| G-6  | Paper integration: §11.12 + §14.2 historical bullet                                          | Paper        | ✅                         |
| G-7  | Full regression suite — must exceed 959                                                      | Regression   | ✅ 1036 pass               |
| G-8  | Regenerate PDFs                                                                              | Deliverable  | ✅                         |

### External data sources (for validation, not curve-fitting)

- Gabor, D. "A New Microscopic Principle" (Nature, 1948) — original holography
- Gabor, D. "Associative Holographic Memories" (IBM J. Res. Dev., 1969)
- Van Heerden, P. "Theory of Optical Information Storage in Solids" (Appl. Opt., 1963)
- Kogelnik, H. "Coupled Wave Theory for Thick Hologram Gratings" (Bell Syst. Tech. J., 1969)
- Leith, E. & Upatnieks, J. "Wavefront Reconstruction with Diffused Illumination" (JOSA, 1964)
- Psaltis, D. & Brady, D. "Optical Information Processing Based on Associative-Memory" (Appl. Opt., 1990)
- Mok, F. "Angle-Multiplexed Storage of 5000 Holograms in LiNbO₃" (Opt. Lett., 1993) — M/#

### Key equations to validate

- Shift-tolerance kernel: $R(\delta) \propto \sum_{n} \int_0^L \sin^2(n\pi x/L)\,\sin^2(n\pi(x+\delta)/L)\,dx$
- Sub-aperture SNR (holographic linear model): $\text{acc}(K) \propto K/N$
- Holographic bandwidth: $N_{\text{BW}} = \sum_{n=1}^{N} Q_n$ (total Q-factor × mode count)
- Kogelnik selectivity: $\eta(\Delta\nu) \propto \text{sinc}^2(\Delta\nu / \delta\nu)$

### Cross-sidebar interactions

| Interaction                                          | Sidebars  | Nature                                                                     |
| ---------------------------------------------------- | --------- | -------------------------------------------------------------------------- |
| Degradation curve extends monadic reconstruction     | S8 × S7   | H-G2 sweeps full K curve; H-L3 sampled at 3 points                         |
| Crosstalk envelope validates polysemic orthogonality | S8 × S2   | H-G4 tests full overlap range; S2 measured disjoint-only (0.003)           |
| Bandwidth ceiling contextualizes capacity gains      | S8 × S1–3 | H-G3 frames polysemic/null-space/phase as fractions of holographic ceiling |
| Franklin kill constrains hypotheses                  | S8 × S6   | No Fourier-phase algorithms; structural properties only                    |

---

## Recommended Execution Order

The sidebars have **dependency chains** — later ones build on earlier results:

```
S4 (Chladni) ──────────────────────────┐
  └─ 2D plate modes                     │
                                        ├── All feed into paper §11 and §14.2
S5 (Békésy) ───────────────────────────┤
  └─ tapered geometry, active Q         │
                                        │
S6 (Franklin) ─── depends on S3 ───────┤
  └─ phase retrieval extends            │
     tesla_phase.py results             │
                                        │
S7 (Leibniz) ─── depends on S1, S2 ───┤
  └─ binary/combinatorial encoding      │
     extends hopfield + semantic work   │
                                        │
S8 (Gabor) ─── depends on S1–S7 ──────┤
  └─ holographic structural props       │
                                        │
S9 (Zeeman) ─── depends on S1, S4 ────┤
  └─ splitting extends avoided-crossing │
     and degeneracy-splitting results   │
                                        │
S10 (Kepler) ─── depends on S2, S8 ───┤
  └─ harmonic ratios extend polysemic   │
     partitioning and bandwidth ceiling │
                                        │
S11 (Boltzmann) ─── depends on S5 ────┤
  └─ timescale hierarchy extends        │
     thermal + decoherence models       │
                                        │
S12 (Gor'kov) ─── depends on S1, S4 ──┘
  └─ radiation force placement extends
     site optimization and Chladni
     trapping; sin(2kz) identity
```

**Completed order: S4 → S5 → S6 → S7 → S8 → S9 → S10 (all ✅)**
**Next: S11 → S12**

Rationale (S9–S12):

1. **S9 (Zeeman)** is the highest-physics-value Scranton sidebar: it directly
   extends S1 avoided-crossing and S4 degeneracy-splitting with new quantitative
   predictions (g-factor analogy, selection rules, nonlinear regime). No new
   mathematical framework needed — just perturbation theory extensions.
2. **S10 (Kepler)** builds on S2 polysemic channel partitioning and S8 bandwidth
   ceiling. Needs stable crosstalk and capacity results from prior sidebars.
3. **S11 (Boltzmann)** is the most theoretical sidebar (partition functions,
   timescale hierarchies). Benefits from all physics sidebars being stable first.
4. **S12 (Gor'kov)** depends on S1 site optimization and S4 Chladni sensitivity
   maps, but also benefits from Zeeman multi-site geometry (S9) being complete.
   The $\sin(2kz)$ identity was discovered during S12 scoping — this is the
   deepest mathematical connection between SEM and an external physics domain.
   Execution after S9 allows Bjerknes force (H-ARF3) to test against Zeeman
   splitting data (H-Z4).

---

## Cross-Sidebar Interaction Matrix

Some results from one sidebar may affect another. Track known interactions:

| Interaction                                | Sidebars  | Nature                                                                                                      |
| ------------------------------------------ | --------- | ----------------------------------------------------------------------------------------------------------- |
| 2D plate phase encoding                    | S4 × S3   | Chladni plate modes have 2D phase structure; Tesla's phase independence (H-T1) may generalize               |
| Cochlear windowing + polysemic readout     | S5 × S2   | Békésy's critical bands may optimize Scranton's sub-channel partitioning                                    |
| Phase retrieval + phase encoding           | S6 × S3   | Franklin's algorithms directly extend Tesla's phase results                                                 |
| Binary quantization + pruning              | S7 × S1   | Leibniz's binarization is an extreme form of Spare/Mace's pruning                                           |
| Tapered rod + Chladni sensitivity          | S5 × S4   | Non-uniform geometry appears in both; shared sensitivity-function math                                      |
| Monadic reconstruction + polysemic readout | S7 × S2   | Each mode encoding the whole pattern (Leibniz) parallels each sub-channel encoding independently (Scranton) |
| Splitting extends avoided crossing         | S9 × S1   | Zeeman g-factor analogy generalises spare_mace hybridisation depth into a predictive ratio                  |
| Splitting extends 2D degeneracy            | S9 × S4   | Zeeman selection rules parallel Chladni's (n,m)/(m,n) structural degeneracy splitting                       |
| Harmonic partitioning + polysemic          | S10 × S2  | Kepler's consonant grouping is an alternative to Scranton's uniform sub-channel split                       |
| Consonance + bandwidth ceiling             | S10 × S8  | Kepler ratios may improve Gabor's bandwidth utilization η by reducing cross-channel leakage                 |
| Timescale hierarchy + thermal drift        | S11 × S5  | Boltzmann's decade-spacing prediction extends Békésy's active Q-boosting timescale model                    |
| Partition function + capacity weighting    | S11 × S8  | Boltzmann weighting provides a thermodynamic foundation for Gabor's bandwidth ceiling N_BW                  |
| Cascade reddening + mode coupling          | S11 × S1  | Boltzmann energy cascade tests whether spare_mace coupling drives spectral reddening                        |
| Gor'kov placement vs golden-ratio          | S12 × S1  | Radiation-force maxima compete with/extend golden-ratio site optimization from spare_mace                   |
| Radiation force = Chladni trapping         | S12 × S4  | Gor'kov force in 2D is the physical mechanism underlying Chladni's sand-at-nodal-lines observation          |
| Phase encoding at gradient peaks           | S12 × S3  | Tesla phase encoding is strongest at sensitivity-gradient maxima — the same positions Gor'kov force peaks   |
| Bjerknes ↔ Zeeman multi-site geometry      | S12 × S9  | Bjerknes inter-site coupling (H-ARF3) parallels Zeeman multi-site field geometry (H-Z4)                     |
| Contrast factor vs partition weighting     | S12 × S11 | Acoustic contrast Φ offers a physics-based alternative to Boltzmann partition-function weighting            |
| Optimal placement + bandwidth utilisation  | S12 × S8  | Gor'kov-placed sites may improve Gabor's bandwidth utilisation ratio η (H-G3)                               |

---

## Killed Hypotheses Log

_Record every hypothesis that fails its kill criterion. This is as scientifically
valuable as confirmations — it maps the boundary of what the physics supports._

| Hypothesis | Sidebar | Date       | Kill reason                                                                      | Insight gained                                                                                                                                |
| ---------- | ------- | ---------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **H-K1**   | S10     | 2025-07-11 | Consonant crosstalk 0.677 vs uniform 0.730 = only 7.4% reduction (threshold 30%) | sin² basis orthogonality trumps musical consonance — harmonic ratios govern perception, not encoding                                          |
| **H-K2**   | S10     | 2025-07-11 | Consonance-weighted recall 0.792 vs baseline 0.883 = −10.4% (threshold +15%)     | Consonance weighting injects structured noise into Hopfield energy landscape; mode-pair information content is independent of frequency ratio |

---

## Completed Sidebars Reference

### S1 — Spare/Mace (Phase 5)

- **Module:** `simulations/spare_mace.py` (873 lines, 6 experiments)
- **Tests:** `tests/test_spare_mace.py` (62 tests)
- **Paper:** §11.1–11.4, §14.2 bullet
- **Key result:** SVD pre-decomposition, pruning, compute-in-memory, avoided crossings, null-space

### S2 — Scranton/Dogon (Phase 7b)

- **Module:** `simulations/scranton_dogon.py` (1029 lines, 6 experiments)
- **Tests:** `tests/test_scranton_dogon.py` (62 tests)
- **Paper:** §11.5, §14.2 bullet
- **Key result:** Polysemic readout +297% capacity, multi-channel spectral decoding

### S3 — Tesla (Phase 8)

- **Module:** `simulations/tesla_phase.py` (~750 lines, 4 experiments)
- **Tests:** `tests/test_tesla_phase.py` (50 tests)
- **Paper:** §11.7, §14.2 bullet
- **Key result:** Phase independence +84%, complex recall 12× margin, acoustic read ~free, scale invariance confirmed

### S9 — Zeeman (Phase 9f)

- **Module:** `simulations/zeeman_splitting.py` (~400 lines, 4 experiments)
- **Tests:** `tests/test_zeeman_splitting.py` (75 tests)
- **Paper:** §11.13, §14.2 bullet, §11.6 item 12
- **Key result:** 4/4 confirmed — g-factor splitting ratio (R² = 1.0000), selection-rule channel constraints (55.2% significant), quadratic Zeeman nonlinearity (R² = 0.9998), multi-site geometry scaling (all K exceed 2K threshold)

### S10 — Kepler (Phase 9g)

- **Module:** `simulations/kepler_harmonic.py` (~700 lines, 4 experiments)
- **Tests:** `tests/test_kepler_harmonic.py` (74 tests)
- **Paper:** §11.14, §14.2 bullet, §11.6 item 13
- **Key result:** 2/4 confirmed — octave equivalence (mean r = 0.657, error detection 70.8%), harmonic capacity scaling (log R² = 0.675 vs linear R² = 0.298, C ≈ 1.055 ln N). 2/4 killed — diatonic partitioning (7.4% crosstalk reduction, threshold 30%), consonance-weighted recall (−10.4% accuracy, threshold +15%)

---

## S9 — Zeeman Splitting (Scranton Observation 1): Perturbation-Induced Level Splitting

### Core insight

The Zeeman effect (1896) splits atomic spectral lines when an external magnetic
field is applied: degenerate energy levels separate into distinct sub-levels,
with splitting patterns governed by quantum numbers and selection rules. Laird
Scranton's observation that "creational energetics" involves "the splitting of
a thing into two things" maps directly onto SEM's mode hybridisation physics:
when an external perturbation (mass loading) is applied to a cavity with
near-degenerate eigenmode pairs, frequency splitting occurs analogous to the
Zeeman effect. The spare_mace avoided-crossing experiment (§11.3) demonstrated
+160% capacity from hybridisation; the chladni degeneracy-splitting experiment
(H-C4) showed 2D structural degeneracy. This sidebar extends both with
quantitative predictions grounded in Zeeman physics: g-factor-like splitting
ratios, selection rules that constrain which modes interact, nonlinear
(quadratic) splitting at strong perturbation, and multi-site "field" geometry
effects.

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                                                                                 | Kill criterion                                                              | Builds on                                  |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------ |
| **H-Z1** | **Anomalous splitting ratio.** Perturbation-induced frequency splitting of near-degenerate mode pairs follows a ratio structure analogous to quantum Zeeman g-factors: $\Delta f / f_0 = g_{\text{eff}} \cdot \varepsilon$, where $g_{\text{eff}}$ depends on mode indices. Splitting is linear for $\varepsilon < 0.05$. | Splitting ratio deviates > 50% from linear prediction over weak-field range | §11.3 avoided crossing, spare_mace.py      |
| **H-Z2** | **Selection-rule channel count.** Under single-site perturbation, only mode pairs satisfying a selection rule ($\|n - m\| \leq \Delta n_{\max}$) show significant splitting (> linewidth). This constrains usable split channels, analogous to the quantum rule $\Delta m_J = 0, \pm 1$.                                  | > 80% of ALL mode pairs split significantly (no selection rule observed)    | §11.3, noise_decoherence.py                |
| **H-Z3** | **Quadratic Zeeman at strong perturbation.** At large perturbation ($\varepsilon > 0.1$), splitting deviates from linear: $\Delta f = g_{\text{eff}} \varepsilon + \alpha \varepsilon^2$. The quadratic coefficient $\alpha$ is predictable from the mode coupling matrix.                                                | Splitting remains linear ($R^2 > 0.99$) even at $\varepsilon = 0.3$         | spare_mace.py avoided crossing             |
| **H-Z4** | **Multi-site field geometry.** The total number of resolvable split pairs scales with perturbation site count $K$ and spatial arrangement. $K$ optimally-placed sites resolve $\geq 2K$ split pairs, analogous to complex magnetic field geometries creating richer Zeeman patterns.                                      | Split-pair count $< K$ for optimally-placed sites                           | §7 site optimization, site_optimization.py |

### Implementation plan

| Step | Task                                                                                             | Artifact     | Status           |
| ---- | ------------------------------------------------------------------------------------------------ | ------------ | ---------------- |
| Z-1  | Literature review: Zeeman effect, g-factors, selection rules ΔmJ, quadratic Zeeman, Paschen-Back | Design notes | ✅               |
| Z-2  | Implement `simulations/zeeman_splitting.py` with 4 experiment functions + dataclass results      | Module       | ✅               |
| Z-3  | Write `tests/test_zeeman_splitting.py` — target ≥ 40 tests                                       | Test file    | ✅ 75 tests      |
| Z-4  | Run experiments, confirm or kill each hypothesis                                                 | Results      | ✅ 4/4 confirmed |
| Z-5  | Update `simulations/__init__.py` (Phase 9f)                                                      | Package      | ✅               |
| Z-6  | Paper integration: §11.13 subsection + §14.2 historical bullet + §11.6 item 12                   | Paper        | ✅               |
| Z-7  | Full regression suite — must exceed 1036                                                         | Regression   | ✅ 1111 pass     |
| Z-8  | Regenerate PDFs                                                                                  | Deliverable  | ✅               |

### Experiment results

| ID       | Verdict       | Key metric                                                                                                                       |
| -------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------- | --- | --------------------------------- |
| **H-Z1** | **CONFIRMED** | Mean linear R² = 1.0000 across all mode pairs; g_eff correlation with predicted = 1.0000                                         |
| **H-Z2** | **CONFIRMED** | 240/435 pairs significant (55.2%); selection rule Δn_max = 28 constrains usable channels                                         |
| **H-Z3** | **CONFIRMED** | Linear R² = 0.9735 (< 0.99 threshold), quadratic R² = 0.9998;                                                                    | α   | = 1.157 confirms nonlinear regime |
| **H-Z4** | **CONFIRMED** | All K = 1..10 exceed 2K threshold; best K = 1 ratio = 35.00×; multi-site geometry monotonically increases resolvable split pairs |

### External data sources (for validation, not curve-fitting)

- Zeeman, P. "On the Influence of Magnetism on the Nature of the Light Emitted by a Substance" (Phil. Mag., 1897)
- Condon, E. & Shortley, G. _The Theory of Atomic Spectra_ (Cambridge, 1935) — g-factor tables
- NIST Atomic Spectra Database — measured Zeeman splitting patterns for alkali metals
- Scranton, L. _The Science of the Dogon_ (2006) — creational splitting observations
- Spare_mace avoided-crossing experiment results (§11.3, +160% capacity)
- Chladni degeneracy-splitting results (H-C4, 2D structural degeneracy)

### Key equations to validate

- Linear Zeeman splitting: $\Delta f_{nm} = g_{\text{eff}}(n,m) \cdot \varepsilon \cdot f_0$
- Effective g-factor: $g_{\text{eff}}(n,m) = 4 |\sin^2(n\pi x_p) - \sin^2(m\pi x_p)|$ (single-site perturbation)
- Selection rule: significant splitting only when $|n - m| \leq \Delta n_{\max}(Q)$
- Quadratic correction: $\Delta f = g_{\text{eff}} \varepsilon + \alpha_{nm} \varepsilon^2$, where $\alpha_{nm} \propto \kappa^2 / \delta f_0$
- Multi-site splitting count: $N_{\text{split}}(K) \geq 2K$ for golden-ratio site placement

### Cross-sidebar interactions

| Interaction                              | Sidebars | Nature                                                                          |
| ---------------------------------------- | -------- | ------------------------------------------------------------------------------- |
| Splitting extends avoided crossing       | S9 × S1  | Zeeman g-factor generalises hybridisation depth into a predictive ratio         |
| Splitting extends 2D degeneracy          | S9 × S4  | Selection rules parallel Chladni (n,m)/(m,n) structural splitting               |
| Multi-site geometry uses site optimizer  | S9 × S7a | Optimal perturbation site placement feeds into multi-site Zeeman field geometry |
| Resolvability uses decoherence criterion | S9 × S5  | Mode resolvability (splitting > linewidth) relies on Q-factor from Békésy H-B3  |

---

## S10 — Kepler Harmonic Resonance Ratios (Scranton Observation 2): Musical Consonance in Mode Spectra

### Core insight

Kepler's _Harmonices Mundi_ (1619) described planetary orbital ratios as musical
consonances — harmonic relationships between oscillation frequencies that form
small-integer ratios. SEM's eigenmode spectrum $f_n = nc/(2L)$ is inherently
harmonic: all modes are exact integer multiples of the fundamental. Kepler's
insight suggests that these harmonic relationships can be _exploited_: consonant
mode pairs (simple ratios like 2:1, 3:2, 5:3) may provide superior sub-channel
partitioning for polysemic readout, and the octave structure (factor-of-2
redundancy) may enable error detection. Scranton's reference to "harmonic
resonance" in creational energetics directly parallels Kepler's planetary music.

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                                                | Kill criterion                                                         | Builds on                                      |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ---------------------------------------------- |
| **H-K1** | **Diatonic partitioning.** Partitioning the eigenmode spectrum into consonant groups (based on simple integer frequency ratios: octaves 2:1, fifths 3:2, fourths 4:3) produces polysemic sub-channels with $\geq 30\%$ lower inter-channel crosstalk than uniformly-spaced partitioning. | Consonant partitioning crosstalk $\geq$ uniform partitioning crosstalk | §11.5 polysemic, scranton_dogon.py             |
| **H-K2** | **Consonance-weighted recall.** Weighting recall contributions by the consonance of each mode pair (inversely proportional to ratio complexity: $w_{nm} = 1 / (n + m)$ for mode ratio $n:m$) improves noise tolerance by $\geq 15\%$ over uniform weighting.                             | Consonance weighting degrades recall accuracy vs. uniform weighting    | interference.py, hopfield_recall.py            |
| **H-K3** | **Octave equivalence.** Modes separated by a factor of 2 in frequency carry partially redundant spatial information (same nodal structure at different scales). Octave-paired mode fingerprints correlate with $r > 0.5$; this redundancy enables single-error detection.                | Octave-pair correlation $< 0.3$                                        | §2.1 eigenmode encoding                        |
| **H-K4** | **Harmonic series capacity scaling.** The information per additional mode decreases as $\sim 1/n$ for the $n$-th harmonic, so total capacity from $N$ harmonics scales as $\sim \ln(N)$. This matches Kepler's logarithmic perception and Békésy's cochlear frequency mapping.           | Capacity scales linearly with no diminishing returns                   | capacity.py, convergence.py, bekesy_cochlea.py |

### Implementation plan

| Step | Task                                                                                                          | Artifact     | Status                       |
| ---- | ------------------------------------------------------------------------------------------------------------- | ------------ | ---------------------------- |
| K-1  | Literature review: Kepler Harmonices Mundi, musical consonance, ratio complexity, harmonic series convergence | Design notes | ✅                           |
| K-2  | Implement `simulations/kepler_harmonic.py` with 4 experiment functions                                        | Module       | ✅                           |
| K-3  | Write `tests/test_kepler_harmonic.py` — target ≥ 40 tests                                                     | Test file    | ✅ 74 tests                  |
| K-4  | Run experiments, confirm or kill                                                                              | Results      | ✅ 2/4 confirmed, 2/4 killed |
| K-5  | Update `simulations/__init__.py` (Phase 9g)                                                                   | Package      | ✅                           |
| K-6  | Paper integration: §11.14 subsection + §14.2 bullet + §11.6 item 13                                           | Paper        | ✅                           |
| K-7  | Full regression suite                                                                                         | Regression   | ✅ 1185 pass                 |
| K-8  | Regenerate PDFs                                                                                               | Deliverable  | ✅                           |

### Experiment results

| ID       | Verdict       | Key metric                                                                                                                    |
| -------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **H-K1** | **KILLED**    | Consonant crosstalk 0.677 vs uniform 0.730 = 7.4% reduction (threshold ≥30%); sin² orthogonality trumps musical consonance    |
| **H-K2** | **KILLED**    | Consonance-weighted recall 0.792 vs baseline 0.883 = −10.4% (threshold +15%); structured noise breaks Hopfield energy balance |
| **H-K3** | **CONFIRMED** | Mean octave-pair correlation r = 0.657 > 0.5 (min 0.403, max 0.969); error detection rate 70.8%                               |
| **H-K4** | **CONFIRMED** | Log R² = 0.675 > linear R² = 0.298; C ≈ 1.055 ln N + 2.97; marginal 1/n fit R² = 0.805; capacity saturates beyond ~16 modes   |

### External data sources

- Kepler, J. _Harmonices Mundi_ (1619) — planetary orbital ratio tables
- Helmholtz, H. _On the Sensations of Tone_ (1863) — consonance and roughness theory
- Plomp, R. & Levelt, W. "Tonal Consonance and Critical Bandwidth" (JASA, 1965)
- Scranton, L. birthday observations on "harmonic resonance" in creational energetics
- Musical interval frequency ratios (just intonation): unison 1:1, octave 2:1, fifth 3:2, fourth 4:3, major third 5:4, minor third 6:5

### Key equations to validate

- Consonance rating: $C(n, m) = 1 / (n + m)$ for reduced ratio $n:m$
- Diatonic mode partitioning: assign mode $k$ to channel $j$ where $k/2^j$ is closest to a consonant ratio
- Octave correlation: $r = \text{corr}(\text{fp}_n, \text{fp}_{2n})$ where fp is the sensitivity column
- Capacity scaling: $\mathcal{C}(N) = \sum_{n=1}^N I_n \approx \sum_{n=1}^N c/n = c \cdot H_N \approx c \cdot \ln N$

---

## S11 — Boltzmann Timescale Hierarchy (Scranton Observation 3): Statistical Mechanics of Mode Populations

### Core insight

Boltzmann's statistical mechanics reveals that complex systems exhibit
hierarchical timescales: fast microscopic fluctuations → intermediate
relaxation → slow macroscopic equilibration. SEM's eigenmode system similarly
spans timescales from fast acoustic oscillations ($\sim$ MHz) through mode
ring-down ($\tau = Q / \pi f$, $\sim$ ms) to thermal drift ($\sim$ s).
Scranton's observation about "nested timescales in creational processes" maps
onto this hierarchy. Boltzmann's partition function $Z = \sum_n e^{-E_n/k_BT}$
may provide a natural weighting scheme for mode contributions to capacity, and
the timescale separation predicts optimal readout windows.

### Hypotheses

| ID        | Statement                                                                                                                                                                                                                                                                                                  | Kill criterion                                                     | Builds on                                    |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------- |
| **H-Bt1** | **Decade spacing universality.** SEM's three characteristic timescales — oscillation period $T_{\text{osc}} = 1/f$, ring-down time $\tau = Q/(\pi f)$, and thermal drift period $T_{\text{th}}$ — are separated by approximately one decade each, a universal property predictable from $Q$ and $f$ alone. | Timescale ratios deviate $> 3\times$ from predicted decade spacing | §6 scaling, thermal.py, noise_decoherence.py |
| **H-Bt2** | **Spectral reddening cascade.** Energy injected at high-frequency modes cascades to lower modes through nonlinear coupling, with the cascade spectrum following a power law $f^{-\beta}$ where $\beta \in [1, 2]$. This imposes a fundamental limit on high-mode information retention time.               | No measurable energy transfer between modes ($\beta < 0.5$)        | coupled_physics.py, noise_decoherence.py     |
| **H-Bt3** | **Optimal readout window.** An optimal readout time $t^*$ exists after excitation, balancing mode establishment (needs $t > 1/\Delta f$) against decoherence ($\text{SNR} \propto e^{-t/\tau}$). The Boltzmann-optimal $t^* = \tau \cdot \ln(Q/\pi)$.                                                      | Readout accuracy is monotonic with time (no optimum exists)        | §8.4 readout, cw_readout.py                  |
| **H-Bt4** | **Partition function capacity.** Weighting mode contributions by the Boltzmann factor $\exp(-h f_n / k_B T_{\text{eff}})$ (where $T_{\text{eff}}$ is an effective noise temperature) predicts usable capacity more accurately ($R^2 > 0.9$) than uniform weighting or $Q$-only weighting.                  | Boltzmann weighting $R^2 <$ $Q$-only weighting $R^2$               | capacity.py, thermal.py                      |

### Implementation plan

| Step | Task                                                                                                                 | Artifact     | Status |
| ---- | -------------------------------------------------------------------------------------------------------------------- | ------------ | ------ |
| Bt-1 | Literature review: Boltzmann partition function, timescale separation, energy cascade, Kolmogorov turbulence analogy | Design notes |        |
| Bt-2 | Implement `simulations/boltzmann_timescale.py` with 4 experiment functions                                           | Module       |        |
| Bt-3 | Write `tests/test_boltzmann_timescale.py` — target ≥ 40 tests                                                        | Test file    |        |
| Bt-4 | Run experiments, confirm or kill                                                                                     | Results      |        |
| Bt-5 | Update `simulations/__init__.py` (Phase 9h)                                                                          | Package      |        |
| Bt-6 | Paper integration: §11.15 subsection + §14.2 bullet + §11.6 item 14                                                  | Paper        |        |
| Bt-7 | Full regression suite                                                                                                | Regression   |        |
| Bt-8 | Regenerate PDFs                                                                                                      | Deliverable  |        |

### External data sources

- Boltzmann, L. "Weitere Studien über das Wärmegleichgewicht" (1872) — H-theorem, partition function
- Kolmogorov, A. "The Local Structure of Turbulence" (1941) — energy cascade power law
- Scranton, L. birthday observations on "nested timescales" in creational energetics
- SEM thermal drift measurements: α ≈ 0.0022 /K (paper §5)
- Q-factor database: MEMS resonators 500–50,000 (mems_q_model.py)
- Mode lifetime measurements: τ = Q/(πf) from noise_decoherence.py experiments

### Key equations to validate

- Timescale hierarchy: $T_{\text{osc}} \ll \tau_{\text{ringdown}} \ll T_{\text{thermal}}$
- Ring-down time: $\tau = Q / (\pi f)$
- Cascade power law: $E(f) \propto f^{-\beta}$, $\beta \in [1, 2]$
- Optimal readout: $t^* = \tau \cdot \ln(Q / \pi)$
- Partition function: $Z = \sum_{n=1}^{N} \exp(-h f_n / k_B T_{\text{eff}})$
- Boltzmann-weighted capacity: $\mathcal{C}_B = \sum_n p_n \cdot I_n$ where $p_n = e^{-hf_n/k_BT_{\text{eff}}} / Z$

### Cross-sidebar interactions

| Interaction                                | Sidebars | Nature                                                                       |
| ------------------------------------------ | -------- | ---------------------------------------------------------------------------- |
| Timescale maps onto active Q model         | S11 × S5 | Békésy's active Q-boosting shifts the ring-down timescale                    |
| Partition function contextualises capacity | S11 × S8 | Boltzmann Z is a thermodynamic foundation for Gabor's bandwidth ceiling N_BW |
| Cascade reddening tests mode coupling      | S11 × S1 | Energy cascade requires the coupling matrix from spare_mace                  |
| Readout window uses CW readout model       | S11 × S3 | Optimal t\* balances Tesla's phase-spectral readout against decoherence      |

---

## S12 — Lev Gor'kov (1929–2016): Acoustic Radiation Force and Optimal Site Placement

### Core insight

Gor'kov's acoustic radiation force theory (1962) predicts where particles
collect in a standing-wave field: the primary radiation force is
$F_{\text{pr}} \propto \sin(2kz)$, driving objects to either pressure nodes or
antinodes depending on an acoustic contrast factor $\Phi(\tilde\kappa, \tilde\rho)$
that encodes material properties. SEM's eigenmode sensitivity function
$\sin^2(n\pi x/L)$ has a spatial gradient:

$$\frac{\partial}{\partial x}\sin^2\!\bigl(\tfrac{n\pi x}{L}\bigr) = \frac{n\pi}{L}\sin\!\bigl(\tfrac{2n\pi x}{L}\bigr)$$

This is **mathematically identical** to the Gor'kov radiation-force spatial
pattern $F_{\text{pr}} \propto \sin(2kz)$ with $k = n\pi/L$. The implication is
profound: locations where perturbation sensitivity changes most rapidly
(maximum gradient of $\sin^2$) correspond exactly to the positions where
acoustic radiation forces are strongest. The standing-wave physics that governs
SEM eigenmode encoding is the _same_ standing-wave physics that governs
Gor'kov particle trapping.

This sidebar tests whether Gor'kov-optimised site placement (at $\sin(2kz)$
maxima/minima) outperforms golden-ratio placement, whether the acoustic
contrast factor predicts optimal perturbation material pairings, whether
Bjerknes inter-particle forces predict hybridisation coupling (§11.3), and
whether node vs antinode placement enables dual-axis encoding.

**Critical constraint — the Franklin kill (S6):** None of these hypotheses
invoke Fourier-phase-retrieval methods. They test acoustic-force structural
predictions applied to SEM's $\sin^2$ encoding framework.

### Hypotheses

| ID         | Statement                                                                                                                                                                                                                                                                                                                                                                                                                           | Kill criterion                                                                | Builds on                                      |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------- |
| **H-ARF1** | **Gor'kov-optimised placement.** Placing perturbation sites at maxima of $\|\sin(2n\pi x/L)\|$ (gradient peaks of the sensitivity function) yields ≥ 10% higher fingerprint distinguishability than golden-ratio placement, because these locations maximise mode-dependent sensitivity variation — exactly as Gor'kov radiation forces maximise particle displacement at the same spatial positions.                               | Gor'kov placement fingerprint distinguishability < golden-ratio placement     | §7 site optimization, site_optimization.py     |
| **H-ARF2** | **Acoustic contrast factor predicts materials.** The Gor'kov acoustic contrast factor $\Phi(\tilde\kappa, \tilde\rho) = \frac{5\tilde\rho - 2}{2\tilde\rho + 1} - \tilde\kappa$ predicts which perturbation material pairs produce the largest eigenfrequency shifts: high-$\Phi$ materials (dense, incompressible) create stronger perturbations. Ranking by $\Phi$ correlates $r > 0.7$ with ranking by measured frequency shift. | $\Phi$-ranking correlation with measured shift ranking $r < 0.5$              | §5 materials, forced_oscillation.py            |
| **H-ARF3** | **Bjerknes force predicts hybridisation coupling.** The secondary Bjerknes force between two nearby perturbation sites (inter-particle radiation force) is attractive when both are in-phase and repulsive when anti-phase. This predicts which site pairs produce the strongest avoided crossings in §11.3: Bjerknes-attractive pairs show $\geq 2\times$ the hybridisation splitting of Bjerknes-repulsive pairs.                 | Bjerknes-attractive pairs show $< 1.2\times$ the splitting of repulsive pairs | §11.3 hybridisation, spare_mace.py             |
| **H-ARF4** | **Dual-axis encoding.** Perturbation sites at $\sin^2$ nodes (zero sensitivity, maximum gradient) and antinodes (maximum sensitivity, zero gradient) encode complementary information: node sites are sensitive to mass-spring coupling (gradient-dominated), antinode sites to mass loading (amplitude-dominated). Using both axes increases fingerprint entropy by $\geq 20\%$ over single-axis (antinode-only) placement.        | Dual-axis entropy gain < 10% over antinode-only                               | §2.1 eigenmode encoding, sensitivity functions |

### Implementation plan

| Step  | Task                                                                                                                     | Artifact     | Status |
| ----- | ------------------------------------------------------------------------------------------------------------------------ | ------------ | ------ |
| ARF-1 | Literature review: Gor'kov 1962, Bruus 2012 review, King 1934, Yosioka & Kawasima 1955, Bjerknes forces, acoustophoresis | Design notes |        |
| ARF-2 | Implement `simulations/gorkov_radiation.py` with 4 experiment functions + dataclass results                              | Module       |        |
| ARF-3 | Write `tests/test_gorkov_radiation.py` — target ≥ 40 tests                                                               | Test file    |        |
| ARF-4 | Run experiments, confirm or kill each hypothesis                                                                         | Results      |        |
| ARF-5 | Update `simulations/__init__.py` (Phase 9i)                                                                              | Package      |        |
| ARF-6 | Paper integration: §11.16 subsection + §14.2 historical bullet + §11.6 item 15                                           | Paper        |        |
| ARF-7 | Full regression suite — must exceed prior count                                                                          | Regression   |        |
| ARF-8 | Regenerate PDFs                                                                                                          | Deliverable  |        |

### External data sources (for validation, not curve-fitting)

- Gor'kov, L. P. "On the forces acting on a small particle in an acoustical field in an ideal fluid" (Soviet Physics — Doklady, 1962)
- Bruus, H. "Acoustofluidics 7: The acoustic radiation force on small particles" (Lab Chip, 2012) — modern review
- King, L. V. "On the acoustic radiation pressure on spheres" (Proc. R. Soc. Lond. A, 1934) — rigid sphere limit
- Yosioka, K. & Kawasima, Y. "Acoustic radiation pressure on a compressible sphere" (Acustica, 1955) — contrast factor derivation
- Settnes, M. & Bruus, H. "Forces acting on a small particle in an acoustical field" (Phys. Rev. E, 2012) — viscous corrections
- Scranton, L. observations on standing-wave organisation in creational energetics
- SEM site-optimization results (§7, golden-ratio baseline)

### Key equations to validate

- Gor'kov primary radiation force: $F_{\text{pr}} = 4\pi\,\Phi(\tilde\kappa, \tilde\rho)\,a^3\,k\,E_{\text{ac}}\sin(2kz)$
- Acoustic contrast factor: $\Phi = \frac{5\tilde\rho - 2}{2\tilde\rho + 1} - \tilde\kappa$, where $\tilde\rho = \rho_p/\rho_f$, $\tilde\kappa = \kappa_p/\kappa_f$
- Gradient identity: $\frac{\partial}{\partial x}\sin^2(n\pi x/L) = \frac{n\pi}{L}\sin(2n\pi x/L) \equiv F_{\text{pr}}$ spatial pattern
- Secondary Bjerknes force: $F_B \propto -\frac{\partial}{\partial d}\langle V_1(t) V_2(t) \rangle$ (volume oscillations of two bodies)
- Fingerprint entropy: $H = -\sum_i p_i \log_2 p_i$ over discretised fingerprint bins
- Dual-axis sensitivity: node site $\propto |\partial\sin^2/\partial x|$, antinode site $\propto \sin^2$

### Cross-sidebar interactions

| Interaction                                          | Sidebars  | Nature                                                                                         |
| ---------------------------------------------------- | --------- | ---------------------------------------------------------------------------------------------- |
| Gradient placement extends site optimisation         | S12 × S1  | Gor'kov $\sin(2kz)$ placement competes with/extends golden-ratio placement from spare_mace     |
| Radiation force predicts Chladni trapping            | S12 × S4  | Gor'kov force in 2D is the mechanism underlying Chladni's sand-at-nodal-lines observation      |
| Tesla phase at gradient peaks                        | S12 × S3  | Phase encoding (S3) is strongest where sensitivity gradient is maximum — the Gor'kov maxima    |
| Bjerknes force predicts hybridisation strength       | S12 × S9  | Bjerknes inter-site coupling parallels Zeeman multi-site field geometry (H-Z4)                 |
| Contrast factor extends Boltzmann material weighting | S12 × S11 | Acoustic contrast $\Phi$ provides a physics-based alternative to Boltzmann partition weighting |
| Bandwidth utilisation at optimal sites               | S12 × S8  | Gor'kov-placed sites may improve Gabor's bandwidth utilisation ratio $\eta$ (H-G3)             |
