# Historical Sidebar Research Tracker

## Purpose

Each sidebar explores parallels between a historical figure's work and CWM physics.
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

| Sidebar | Figure                | Module                     | Tests | Hypotheses                 | Status      |
| ------- | --------------------- | -------------------------- | ----- | -------------------------- | ----------- |
| **S1**  | Spare / Mace          | `spare_mace.py`            | 62    | H1–H6: 6/6 confirmed       | ✅ Complete |
| **S2**  | Scranton / Dogon      | `scranton_dogon.py`        | 62    | H7–H12: 6/6 confirmed      | ✅ Complete |
| **S3**  | Tesla                 | `tesla_phase.py`           | 50    | H-T1–T4: 4/4 confirmed     | ✅ Complete |
| **S4**  | Chladni               | `chladni_plates.py`        | 69    | H-C1–C4: 4/4 confirmed     | ✅ Complete |
| **S5**  | Békésy                | `bekesy_cochlea.py`        | 68    | H-B1–B4: 1/4 confirmed     | ✅ Complete |
| **S6**  | Franklin (Rosalind)   | `franklin_phase.py`        | 69    | H-F1–F4: 0/4 confirmed     | ✅ Complete |
| **S7**  | Leibniz               | `leibniz_binary.py`        | 73    | H-L1–H-L4: 3/4 confirmed   | ✅ Complete |
| **S8**  | Gabor                 | `gabor_holographic.py`     | 77    | H-G1–G4: 1/4 confirmed     | ✅ Complete |
| **S9**  | Zeeman (Scranton)     | `zeeman_splitting.py`      | 75    | H-Z1–Z4: 4/4 confirmed     | ✅ Complete |
| **S10** | Kepler (Scranton)     | `kepler_harmonic.py`       | 74    | H-K1–K4: 2/4 confirmed     | ✅ Complete |
| **S11** | Boltzmann (Scranton)  | `boltzmann_timescale.py`   | 96    | H-Bt1–Bt4: 1/4 confirmed   | ✅ Complete |
| **S12** | Gor'kov (Scranton)    | `gorkov_radiation.py`      | 115   | H-ARF1–ARF4: 1/4 confirmed | ✅ Complete |
| **S13** | Irrational Prediction | `irrational_prediction.py` | 77    | H-IR1–IR4: 4/4 confirmed   | ✅ Complete |
|         |                       |                            |       |                            |             |
| **S14** | Fabry & Pérot         | `fabry_perot_cavity.py`    | 90    | H-FP1–FP4: 2/4 confirmed   | ✅ Complete |
| **S15** | Shannon & Nyquist     | `shannon_capacity.py`      | 72    | H-SN1–SN4: 2/4 confirmed   | ✅ Complete |
| **S16** | Mathieu & Floquet     | `mathieu_parametric.py`    | 77    | H-PM1–PM4: 4/4 confirmed   | ✅ Complete |
| **S17** | Coronal Seismology    | `coronal_seismology.py`    | 109   | H-CS1–CS7: 6/7 confirmed   | ✅ Complete |
| **S18** | Gauge Geometry        | `gauge_geometry.py`        | 88    | H-GG1–GG5: 3/5 confirmed   | ✅ Complete |

**Running totals (completed):** 44 modules · 1909 tests · 84 hypotheses (54 confirmed, 30 killed)
**S1–S18 complete.**

---

## S4 — Ernst Chladni (1756–1827): 2D Plate Eigenmode Memory

### Core insight

Chladni's sand-on-plate experiments are **sensitivity maps**: sand collects
at nodal lines (zero displacement = zero perturbation sensitivity). The
CWM sensitivity function sin²(nπx/L) is the 1D version of what Chladni
visualized in 2D. Extending CWM from rods to membranes could unlock
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

The cochlea is a **biological CWM device**: a tapered resonant cavity that maps
eigenfrequencies to spatial positions along the basilar membrane. Evolution has
optimized eigenmode-based information encoding for ~200 million years. The
cochlea's logarithmic frequency mapping, active amplification (outer hair cells
as Q-boosters), and noise rejection strategies may suggest better CWM designs.

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                   | Kill criterion                                   | Builds on                    |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ---------------------------- |
| **H-B1** | A tapered rod (continuously varying cross-section) achieves higher mode density than a uniform rod of the same length, because the local wave speed varies and modes compress toward the thin end — the cochlear "tonotopic" effect.                        | Tapered mode count ≤ uniform mode count          | §2.1, §6 scaling             |
| **H-B2** | Logarithmic frequency spacing (cochlea-like) improves associative recall noise tolerance compared to the uniform linear spacing of a constant-cross-section rod, because log spacing allocates more resolution to low-frequency modes where SNR is highest. | Log-spaced recall accuracy ≤ linear-spaced       | §11 recall, interference.py  |
| **H-B3** | Active Q-boosting — feeding energy into selected modes (analogous to outer hair cell motility) — can compensate for anchor loss at MEMS scale, raising effective Q above the passive limit predicted by the 5-mechanism model (§7).                         | Active Q_eff < 1.5× passive Q                    | §7 Q-factor, mems_q_model.py |
| **H-B4** | The cochlea's critical-band masking (frequency-dependent noise rejection) maps onto an optimal **windowing function** for CWM's FFT readout that outperforms the rectangular window currently assumed.                                                      | Cochlear window SNR gain < 1 dB over rectangular | §8.4 readout, cw_readout.py  |

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
data. CWM's readout is also an FFT of the rod's response; the Tesla sidebar
showed that phase carries independent information (§11.7). Franklin's domain
offers phase-retrieval algorithms that may improve CWM's noise tolerance and
enable reconstruction of the perturbation pattern from readout data (the
**inverse problem**).

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                                                                                                | Kill criterion                                            | Builds on                            |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------ |
| **H-F1** | Applying crystallographic **direct methods** (Hauptman–Karle tangent formula) to CWM readout data recovers perturbation positions from amplitude-only spectra with ≥ 80% accuracy, even when phase information is unavailable.                                                                                                           | Reconstruction accuracy < 50%                             | §11.7 phase encoding, tesla_phase.py |
| **H-F2** | **Patterson function** analysis (autocorrelation of the spectrum) reveals inter-site distances without phase, enabling partial decoding of the perturbation pattern. The number of recoverable distance constraints scales as $K(K-1)/2$ for $K$ sites.                                                                                  | Fewer than $K$ independent distance constraints recovered | §7 site optimization                 |
| **H-F3** | Iterative phase retrieval (Gerchberg–Saxton / hybrid input-output) converges to the correct perturbation pattern from amplitude-only FFT data within 100 iterations for patterns with ≤ 20 sites.                                                                                                                                        | Non-convergence or > 1000 iterations for trivial cases    | §11.7 H-T1, H-T2                     |
| **H-F4** | The **molecular replacement** technique (using a known reference pattern to bootstrap phase estimates for an unknown pattern) maps onto CWM's associative recall: using stored patterns as "search models" to phase the readout. This produces measurably better recall accuracy than the current amplitude-only or complex dot product. | MR-recall accuracy ≤ complex recall (H-T2)                | §11.7 H-T2, interference.py          |

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

**Root cause:** CWM's $\sin^2(n\pi x/L)$ sensitivity encoding is algebraically incompatible with the Fourier-based encoding ($e^{2\pi i n x}$) that crystallographic phase-retrieval algorithms require.

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
- CWM-adapted molecular replacement merit function

---

## S7 — Gottfried Wilhelm Leibniz (1646–1716): Binary Encoding and Monadic Compression

### Core insight

Leibniz invented binary arithmetic (1679) after studying the I Ching's 64
hexagrams — 6-bit binary codes used for 3,000+ years. His monadology (1714)
proposed that each indivisible "monad" reflects the entire universe from its
own perspective — a philosophical eigenmode (each mode encodes the full cavity
geometry). The I Ching connection extends the Dogon sidebar: another ancient
civilization independently encoding information in compact combinatorial
symbols. The binary-arithmetic connection asks whether CWM's continuous-valued
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
a predictable crosstalk envelope between stored patterns. CWM already exhibits
the first group of holographic properties (distributed encoding, interference
recall, multiplexing). This sidebar tests whether the _quantitative_ predictions
from holographic theory (Gabor, Kogelnik, Leith & Upatnieks) hold for CWM's
sin²-based encoding.

**Critical constraint — the Franklin kill (S6):** CWM's sin²(nπx/L) encoding
is algebraically incompatible with Fourier-based phase-retrieval algorithms
(4:0 kill in S6). **None of the hypotheses below use Fourier-phase-retrieval
methods.** They test _structural_ properties of holographic systems — shift
tolerance, degradation scaling, bandwidth utilization, and crosstalk envelopes —
which depend on distributed wave encoding, not on the specific basis functions.

### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                                                                                         | Kill criterion                                                                                | Builds on                               |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | --------------------------------------- |
| **H-G1** | **Shift-tolerant recall.** When the query pattern is spatially shifted by δ (all perturbation sites displaced), the recall score R(δ) tracks the autocorrelation of the sin²(nπx/L) sensitivity kernel. CWM should exhibit a measurable "shift-tolerance width" Δ_s ≈ L/(2n_max).                                                 | R(δ) shows no structure (flat/random), OR autocorrelation width deviates > 2× from prediction | §2.3 recall, hopfield_recall.py         |
| **H-G2** | **Sub-aperture degradation curve.** Reconstruction accuracy from K of N modes follows a smooth, monotonically increasing function of K/N. Holographic aperture theory (Leith & Upatnieks 1964) predicts linear scaling: accuracy ∝ K/N.                                                                                           | Accuracy vs. K/N is non-monotonic OR best fit R² < 0.7                                        | §11.11 H-L3, leibniz_binary.py          |
| **H-G3** | **Bandwidth utilization ceiling.** A bandwidth-limited capacity ceiling N_BW can be computed from total spectral range and per-mode linewidth. Each capacity-enhancing technique (polysemic, null-space, phase-spectral) should increase the utilization ratio η = P_eff / N_BW monotonically.                                    | η does NOT increase monotonically with added techniques                                       | §11.6 combined capacity                 |
| **H-G4** | **Crosstalk selectivity envelope.** Kogelnik's (1969) coupled-wave theory predicts inter-hologram crosstalk follows sinc² as a function of spectral separation. Two CWM patterns in mode subsets with fractional overlap Ω should have crosstalk C(Ω) following a smooth envelope (sinc², Gaussian, or linear fit with R² ≥ 0.7). | Crosstalk vs. overlap has no smooth fit (R² < 0.7 for sinc², Gaussian, and linear)            | §11.5 polysemic (one data point: 0.003) |

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

**Completed order: S4 → S5 → S6 → S7 → S8 → S9 → S10 → S11 → S12 → S13 → S14 → S15 → S16 → S17 (all ✅)**

Rationale (S13–S16):

1. **S13 (Rayleigh)** is highest priority: quantifies second-order perturbation
   error discovered by S9 Zeeman. Bounds every capacity claim in the paper.
   No new physics framework — extends existing perturbation theory.
2. **S14 (Fabry-Pérot)** formalises etalon physics the rod already exhibits.
   Benefits from Rayleigh bounds (S13) constraining mode linewidth predictions.
3. **S15 (Shannon)** requires stable capacity numbers from S13 bounds and
   finesse model from S14 to compute meaningful utilisation ratios.
4. **S16 (Mathieu-Floquet)** is the most experimental sidebar — parametric
   amplification modifies Q and linewidth, so benefits from all prior sidebars.

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
   deepest mathematical connection between CWM and an external physics domain.
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

| Hypothesis | Sidebar | Date       | Kill reason                                                                      | Insight gained                                                                                                                                        |
| ---------- | ------- | ---------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **H-K1**   | S10     | 2025-07-11 | Consonant crosstalk 0.677 vs uniform 0.730 = only 7.4% reduction (threshold 30%) | sin² basis orthogonality trumps musical consonance — harmonic ratios govern perception, not encoding                                                  |
| **H-K2**   | S10     | 2025-07-11 | Consonance-weighted recall 0.792 vs baseline 0.883 = −10.4% (threshold +15%)     | Consonance weighting injects structured noise into Hopfield energy landscape; mode-pair information content is independent of frequency ratio         |
| **H-Bt2**  | S11     | 2025-07-12 | 0% energy transfer between modes, β = 0.000 (threshold 0.5)                      | Nonlinear coupling χ ~ 10⁻⁶ is too weak by orders of magnitude; CWM modes are effectively isolated oscillators, not a coupled thermodynamic bath      |
| **H-Bt3**  | S11     | 2025-07-12 | Readout accuracy monotonically decreasing, no optimum exists                     | At room temperature hf ≪ kBT for all MHz modes; Boltzmann weights collapse to uniform; optimal strategy is simply "measure as early as possible"      |
| **H-Bt4**  | S11     | 2025-07-12 | R²_Boltzmann = 0.0001 < R²_Q-only = 1.0000 (Boltzmann < Q-only)                  | At 300 K, exp(−hf/kT) ≈ 1 for all modes; capacity is determined entirely by SNR ∝ Q/f; thermodynamic populations are irrelevant at CWM temperatures   |
| **H-ARF1** | S12     | 2025-07-13 | Gor'kov placement −98.9% vs golden-ratio (cond 1.2×10¹⁵ vs 4.0)                  | Gradient-peak clustering produces near-singular sensitivity matrices; golden-ratio spacing enforces quasi-orthogonality that gradient-peak sites lack |
| **H-ARF3** | S12     | 2025-07-13 | Bjerknes ratio 1.01× (threshold 2×)                                              | Phase-based coupling direction (attractive/repulsive) has no measurable effect on hybridisation splitting magnitude; coupling is geometry-dominated   |
| **H-ARF4** | S12     | 2025-07-13 | Dual-axis entropy −13.7% (threshold +20%)                                        | Node sites have zero sin² amplitude → zero eigenfrequency shift → redundant with noise; complementary encoding requires non-zero baseline sensitivity |
| **H-FP2**  | S14     | 2026-03-13 | Both R² = 0.9998, advantage ≈ 0 (indistinguishable at high finesse)              | At high finesse, Airy and Lorentzian are asymptotically identical near peaks; the distinction only matters at moderate finesse (F < 50)               |
| **H-FP3**  | S14     | 2026-03-13 | Scanning SNR −13 dB vs impulse (time-division penalty exceeds lock-in gain)      | Sequential mode scanning divides measurement time by N; parallel broadband detection captures all modes simultaneously with higher net SNR            |
| **H-SN1**  | S15     | 2026-03-13 | Waterfilling gain 1.2% (threshold 2%)                                            | Mode-dependent SNR variation is modest (SNR_n = SNR_0/n); uniform allocation is near-optimal because the waterfilling gain requires steeper SNR decay |
| **H-SN4**  | S15     | 2026-03-13 | MI ≈ 0.15 bits/mode everywhere, n_max = 0 (all modes below 0 dB in full model)   | Full five-source noise model is conservative; n_max formula overestimates usable modes when shot/thermal/1f/phase/quantisation all included           |

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

### S11 — Boltzmann (Phase 9h)

- **Module:** `simulations/boltzmann_timescale.py` (~530 lines, 4 experiments)
- **Tests:** `tests/test_boltzmann_timescale.py` (96 tests)
- **Paper:** §11.15, §11.6 item 14
- **Key result:** 1/4 confirmed — decade-separated timescale universality (100% of 96 conditions satisfy T_osc ≪ τ ≪ T_th, mean τ/T_osc = 3,076, mean T_th/τ = 4,533,816). 3/4 killed — spectral reddening (0% energy transfer, β = 0.000), optimal readout window (monotonic decay, no optimum), partition-function capacity (R²_Boltzmann = 0.0001, R²_Q-only = 1.0000). Kill mechanism: at 300 K, hf ≪ kBT for all MHz modes → Boltzmann ≈ uniform.

### S12 — Gor'kov (Phase 9i)

- **Module:** `simulations/gorkov_radiation.py` (~980 lines, 4 experiments)
- **Tests:** `tests/test_gorkov_radiation.py` (115 tests)
- **Paper:** §11.16, §14.2 bullet, §11.6 item 15
- **Key result:** 1/4 confirmed — acoustic contrast factor Φ(κ̃,ρ̃) perfectly predicts material ranking (Spearman ρ = 1.000, Pearson r = 1.000). 3/4 killed — Gor'kov placement (−98.9% vs golden-ratio, condition number 1.2×10¹⁵), Bjerknes hybridisation (ratio 1.01×, threshold 2×), dual-axis entropy (−13.7%, threshold +20%). Kill mechanism: gradient-peak sites cluster → near-singular matrix; node sites have zero sin² amplitude → zero signal.

### S14 — Fabry-Pérot (Phase 9j)

- **Module:** `simulations/fabry_perot_cavity.py` (~500 lines, 4 experiments)
- **Tests:** `tests/test_fabry_perot_cavity.py` (90 tests)
- **Paper:** §11.17, §14.2 bullet, §11.6 item 16
- **Key result:** 2/4 confirmed — finesse-Q equivalence within 5.1% via self-consistent R_eff (H-FP1), end-condition engineering gives 7,922× linewidth variation across 6 materials (H-FP4). 2/4 killed — Airy ≈ Lorentzian at high finesse (both R² = 0.9998, H-FP2), scanning readout −13 dB vs broadband impulse (time-division penalty, H-FP3). Kill mechanism: high-finesse limit makes Airy/Lorentzian indistinguishable; sequential scanning loses to parallel broadband detection.

### S15 — Shannon/Nyquist (Phase 9k)

- **Module:** `simulations/shannon_capacity.py` (~340 lines, 4 experiments)
- **Tests:** `tests/test_shannon_capacity.py` (72 tests)
- **Paper:** §11.18, §14.2 bullet, §11.6 item 17
- **Key result:** 2/4 confirmed — Nyquist 2K minimum strict at finite SNR (10× error reduction K→2K, H-SN2), uniform allocation achieves 98.8% of waterfilling optimum (H-SN3). 2/4 killed — waterfilling gain only 1.2% (threshold 2%, H-SN1), full noise model places all modes below MI threshold (n_max = 0, H-SN4). Kill mechanism: SNR variation too modest for waterfilling advantage; five-source noise model is conservative.

### S16 — Mathieu/Floquet (Phase 9l)

- **Module:** `simulations/mathieu_parametric.py` (~350 lines, 4 experiments)
- **Tests:** `tests/test_mathieu_parametric.py` (77 tests)
- **Paper:** §11.19, §14.2 bullet, §11.6 item 18
- **Key result:** 4/4 confirmed — parametric gain 12.0 dB at ε = 0.003 with 166× less power than Békésy feedback (H-PM1), neighbour-mode crosstalk 0.0004 dB at selectivity 133× (H-PM2), analytic stability boundary within 9.3% of numerical (H-PM3), parametric + CW compound improvement 12.0 dB (H-PM4). Strongest positive result since Zeeman (S9, also 4:0).

---

## S9 — Zeeman Splitting (Scranton Observation 1): Perturbation-Induced Level Splitting

### Core insight

The Zeeman effect (1896) splits atomic spectral lines when an external magnetic
field is applied: degenerate energy levels separate into distinct sub-levels,
with splitting patterns governed by quantum numbers and selection rules. Laird
Scranton's observation that "creational energetics" involves "the splitting of
a thing into two things" maps directly onto CWM's mode hybridisation physics:
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
small-integer ratios. CWM's eigenmode spectrum $f_n = nc/(2L)$ is inherently
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
relaxation → slow macroscopic equilibration. CWM's eigenmode system similarly
spans timescales from fast acoustic oscillations ($\sim$ MHz) through mode
ring-down ($\tau = Q / \pi f$, $\sim$ ms) to thermal drift ($\sim$ s).
Scranton's observation about "nested timescales in creational processes" maps
onto this hierarchy. Boltzmann's partition function $Z = \sum_n e^{-E_n/k_BT}$
may provide a natural weighting scheme for mode contributions to capacity, and
the timescale separation predicts optimal readout windows.

### Hypotheses

| ID        | Statement                                                                                                                                                                                                                                                                                                  | Kill criterion                                                     | Builds on                                    |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------- |
| **H-Bt1** | **Decade spacing universality.** CWM's three characteristic timescales — oscillation period $T_{\text{osc}} = 1/f$, ring-down time $\tau = Q/(\pi f)$, and thermal drift period $T_{\text{th}}$ — are separated by approximately one decade each, a universal property predictable from $Q$ and $f$ alone. | Timescale ratios deviate $> 3\times$ from predicted decade spacing | §6 scaling, thermal.py, noise_decoherence.py |
| **H-Bt2** | **Spectral reddening cascade.** Energy injected at high-frequency modes cascades to lower modes through nonlinear coupling, with the cascade spectrum following a power law $f^{-\beta}$ where $\beta \in [1, 2]$. This imposes a fundamental limit on high-mode information retention time.               | No measurable energy transfer between modes ($\beta < 0.5$)        | coupled_physics.py, noise_decoherence.py     |
| **H-Bt3** | **Optimal readout window.** An optimal readout time $t^*$ exists after excitation, balancing mode establishment (needs $t > 1/\Delta f$) against decoherence ($\text{SNR} \propto e^{-t/\tau}$). The Boltzmann-optimal $t^* = \tau \cdot \ln(Q/\pi)$.                                                      | Readout accuracy is monotonic with time (no optimum exists)        | §8.4 readout, cw_readout.py                  |
| **H-Bt4** | **Partition function capacity.** Weighting mode contributions by the Boltzmann factor $\exp(-h f_n / k_B T_{\text{eff}})$ (where $T_{\text{eff}}$ is an effective noise temperature) predicts usable capacity more accurately ($R^2 > 0.9$) than uniform weighting or $Q$-only weighting.                  | Boltzmann weighting $R^2 <$ $Q$-only weighting $R^2$               | capacity.py, thermal.py                      |

### Implementation plan

| Step | Task                                                                                                                 | Artifact     | Status  |
| ---- | -------------------------------------------------------------------------------------------------------------------- | ------------ | ------- |
| Bt-1 | Literature review: Boltzmann partition function, timescale separation, energy cascade, Kolmogorov turbulence analogy | Design notes | ✅      |
| Bt-2 | Implement `simulations/boltzmann_timescale.py` with 4 experiment functions                                           | Module       | ✅      |
| Bt-3 | Write `tests/test_boltzmann_timescale.py` — target ≥ 40 tests                                                        | Test file    | ✅ 96   |
| Bt-4 | Run experiments, confirm or kill                                                                                     | Results      | ✅ 1/4  |
| Bt-5 | Update `simulations/__init__.py` (Phase 9h)                                                                          | Package      | ✅      |
| Bt-6 | Paper integration: §11.15 subsection + §11.6 item 14                                                                 | Paper        | ✅      |
| Bt-7 | Full regression suite                                                                                                | Regression   | ✅ 1281 |
| Bt-8 | Regenerate PDFs                                                                                                      | Deliverable  | ✅      |

### Experiment results

| ID        | Verdict      | Key metric                                                                | Kill/confirm mechanism                                                   |
| --------- | ------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **H-Bt1** | ✅ Confirmed | 100% decade-spaced (96/96), mean τ/T_osc = 3,076, mean T_th/τ = 4,533,816 | Universal property of high-Q glass acoustics; Q ≥ 10³ guarantees margins |
| **H-Bt2** | ❌ Killed    | 0% energy transfer, β = 0.000 (threshold 0.5)                             | χ ~ 10⁻⁶ too weak; modes are isolated oscillators, not coupled bath      |
| **H-Bt3** | ❌ Killed    | Monotonic decay from 1.000 → 0.000, no local maximum                      | hf ≪ kBT → Boltzmann = uniform; optimal strategy is "measure ASAP"       |
| **H-Bt4** | ❌ Killed    | R²_Boltzmann = 0.0001, R²_Q-only = 1.0000                                 | At 300 K, exp(−hf/kT) ≈ 1; capacity governed by Q/f (mechanical SNR)     |

### External data sources

- Boltzmann, L. "Weitere Studien über das Wärmegleichgewicht" (1872) — H-theorem, partition function
- Kolmogorov, A. "The Local Structure of Turbulence" (1941) — energy cascade power law
- Scranton, L. birthday observations on "nested timescales" in creational energetics
- CWM thermal drift measurements: α ≈ 0.0022 /K (paper §5)
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
that encodes material properties. CWM's eigenmode sensitivity function
$\sin^2(n\pi x/L)$ has a spatial gradient:

$$\frac{\partial}{\partial x}\sin^2\!\bigl(\tfrac{n\pi x}{L}\bigr) = \frac{n\pi}{L}\sin\!\bigl(\tfrac{2n\pi x}{L}\bigr)$$

This is **mathematically identical** to the Gor'kov radiation-force spatial
pattern $F_{\text{pr}} \propto \sin(2kz)$ with $k = n\pi/L$. The implication is
profound: locations where perturbation sensitivity changes most rapidly
(maximum gradient of $\sin^2$) correspond exactly to the positions where
acoustic radiation forces are strongest. The standing-wave physics that governs
CWM eigenmode encoding is the _same_ standing-wave physics that governs
Gor'kov particle trapping.

This sidebar tests whether Gor'kov-optimised site placement (at $\sin(2kz)$
maxima/minima) outperforms golden-ratio placement, whether the acoustic
contrast factor predicts optimal perturbation material pairings, whether
Bjerknes inter-particle forces predict hybridisation coupling (§11.3), and
whether node vs antinode placement enables dual-axis encoding.

**Critical constraint — the Franklin kill (S6):** None of these hypotheses
invoke Fourier-phase-retrieval methods. They test acoustic-force structural
predictions applied to CWM's $\sin^2$ encoding framework.

### Hypotheses

| ID         | Statement                                                                                                                                                                                                                                                                                                                                                                                                                           | Kill criterion                                                                | Builds on                                      |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------- |
| **H-ARF1** | **Gor'kov-optimised placement.** Placing perturbation sites at maxima of $\|\sin(2n\pi x/L)\|$ (gradient peaks of the sensitivity function) yields ≥ 10% higher fingerprint distinguishability than golden-ratio placement, because these locations maximise mode-dependent sensitivity variation — exactly as Gor'kov radiation forces maximise particle displacement at the same spatial positions.                               | Gor'kov placement fingerprint distinguishability < golden-ratio placement     | §7 site optimization, site_optimization.py     |
| **H-ARF2** | **Acoustic contrast factor predicts materials.** The Gor'kov acoustic contrast factor $\Phi(\tilde\kappa, \tilde\rho) = \frac{5\tilde\rho - 2}{2\tilde\rho + 1} - \tilde\kappa$ predicts which perturbation material pairs produce the largest eigenfrequency shifts: high-$\Phi$ materials (dense, incompressible) create stronger perturbations. Ranking by $\Phi$ correlates $r > 0.7$ with ranking by measured frequency shift. | $\Phi$-ranking correlation with measured shift ranking $r < 0.5$              | §5 materials, forced_oscillation.py            |
| **H-ARF3** | **Bjerknes force predicts hybridisation coupling.** The secondary Bjerknes force between two nearby perturbation sites (inter-particle radiation force) is attractive when both are in-phase and repulsive when anti-phase. This predicts which site pairs produce the strongest avoided crossings in §11.3: Bjerknes-attractive pairs show $\geq 2\times$ the hybridisation splitting of Bjerknes-repulsive pairs.                 | Bjerknes-attractive pairs show $< 1.2\times$ the splitting of repulsive pairs | §11.3 hybridisation, spare_mace.py             |
| **H-ARF4** | **Dual-axis encoding.** Perturbation sites at $\sin^2$ nodes (zero sensitivity, maximum gradient) and antinodes (maximum sensitivity, zero gradient) encode complementary information: node sites are sensitive to mass-spring coupling (gradient-dominated), antinode sites to mass loading (amplitude-dominated). Using both axes increases fingerprint entropy by $\geq 20\%$ over single-axis (antinode-only) placement.        | Dual-axis entropy gain < 10% over antinode-only                               | §2.1 eigenmode encoding, sensitivity functions |

### Implementation plan

| Step  | Task                                                                                                                     | Artifact     | Status  |
| ----- | ------------------------------------------------------------------------------------------------------------------------ | ------------ | ------- |
| ARF-1 | Literature review: Gor'kov 1962, Bruus 2012 review, King 1934, Yosioka & Kawasima 1955, Bjerknes forces, acoustophoresis | Design notes | ✅      |
| ARF-2 | Implement `simulations/gorkov_radiation.py` with 4 experiment functions + dataclass results                              | Module       | ✅      |
| ARF-3 | Write `tests/test_gorkov_radiation.py` — target ≥ 40 tests                                                               | Test file    | ✅ 115  |
| ARF-4 | Run experiments, confirm or kill each hypothesis                                                                         | Results      | ✅ 1/4  |
| ARF-5 | Update `simulations/__init__.py` (Phase 9i)                                                                              | Package      | ✅      |
| ARF-6 | Paper integration: §11.16 subsection + §14.2 historical bullet + §11.6 item 15                                           | Paper        | ✅      |
| ARF-7 | Full regression suite — must exceed prior count                                                                          | Regression   | ✅ 1396 |
| ARF-8 | Regenerate PDFs                                                                                                          | Deliverable  | ✅      |

### External data sources (for validation, not curve-fitting)

- Gor'kov, L. P. "On the forces acting on a small particle in an acoustical field in an ideal fluid" (Soviet Physics — Doklady, 1962)
- Bruus, H. "Acoustofluidics 7: The acoustic radiation force on small particles" (Lab Chip, 2012) — modern review
- King, L. V. "On the acoustic radiation pressure on spheres" (Proc. R. Soc. Lond. A, 1934) — rigid sphere limit
- Yosioka, K. & Kawasima, Y. "Acoustic radiation pressure on a compressible sphere" (Acustica, 1955) — contrast factor derivation
- Settnes, M. & Bruus, H. "Forces acting on a small particle in an acoustical field" (Phys. Rev. E, 2012) — viscous corrections
- Scranton, L. observations on standing-wave organisation in creational energetics
- CWM site-optimization results (§7, golden-ratio baseline)

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

### Experiment results

| ID         | Verdict      | Key metric                                                      | Kill/confirm mechanism                                                                       |
| ---------- | ------------ | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **H-ARF1** | ❌ Killed    | −98.9% vs golden-ratio (cond 1.2×10¹⁵ vs 4.0)                   | Gradient-peak sites cluster near mode-dependent positions → near-singular sensitivity matrix |
| **H-ARF2** | ✅ Confirmed | Spearman ρ = 1.000, Pearson r = 1.000, perfect material ranking | Acoustic contrast Φ(κ̃,ρ̃) monotonically predicts eigenfrequency shift magnitude               |
| **H-ARF3** | ❌ Killed    | Bjerknes ratio 1.01× (threshold 2×)                             | Phase-based coupling direction has no measurable effect on splitting; geometry dominates     |
| **H-ARF4** | ❌ Killed    | Dual-axis entropy −13.7% (threshold +20%)                       | Node sites have zero sin² amplitude → zero shift signal → redundant noise, not complement    |

---

## Proposed Future Sidebars

_The twelve planned sidebars (S1–S12) are complete. The following proposals
emerged from a comprehensive review of the confirmed/killed patterns across all
52 hypotheses and the unexplored physics surrounding the CWM architecture.
They target three strategic gaps: (a) fundamental limits the current model
assumes but hasn't rigorously bounded, (b) practical readout mechanisms not yet
explored, and (c) the information-theoretic ceiling that contextualizes all
capacity claims._

_Execution is optional. Each proposal is registered here with hypotheses and
kill criteria per quality gate G1 so that if any are pursued, the same
falsification discipline applies._

---

### S13 — Lord Rayleigh (1842–1919): Higher-Order Perturbation Theory and Variational Bounds

#### Core insight

The paper's entire perturbation model rests on Rayleigh's **first-order**
formula (§5.3): $\Delta\omega_n/\omega_n = -\frac{1}{2}\int\Delta m\,u_n^2
/ \int m\,u_n^2$. This is exact only for infinitesimally small perturbations.
S9-Zeeman proved that second-order effects are experimentally significant: at
perturbation strength $\varepsilon > 0.1$, the quadratic fit ($R^2 = 0.9998$)
dramatically outperforms the linear fit ($R^2 = 0.9735$), and the quadratic
coefficient $\alpha_{nm}$ is predictable from the coupling matrix. Yet the
paper's capacity projections, site-optimization algorithms, and fingerprint
distinguishability claims all use the first-order model.

Rayleigh's own _Theory of Sound_ (1877) provides the tools to go further:
the Rayleigh quotient $\omega^2 \leq R[u] = \int u''^2 / \int u^2$ gives
**variational upper bounds** on eigenfrequencies, and the second-order
perturbation expansion includes cross-mode coupling terms that could either
improve or degrade fingerprint quality depending on geometry. Testing these
would bound the error of every capacity claim in the paper and predict the
regime where multi-site configurations break the linear model.

**Why this feels fruitful:** S9's quadratic Zeeman result is the clearest
evidence that the first-order model has measurable limitations. Rayleigh's
variational framework is the natural next step—and it's the same author
whose first-order formula is already the paper's bedrock.

#### Hypotheses

| ID       | Statement                                                                                                                                                                                                                                                              | Kill criterion                                                                               | Builds on                           |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ----------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ---------------------- |
| **H-R1** | **Second-order improvement.** Including the second-order Rayleigh perturbation correction $\Delta\omega^{(2)}_n \propto \sum_{m \neq n}                                                                                                                                | \langle u_m                                                                                  | \Delta m                            | u_n \rangle | ^2 / (\omega_n^2 - \omega_m^2)$ reduces eigenfrequency prediction error by $\geq 10\%$ at $\varepsilon = 0.1$. | Improvement $< 3\%$ at $\varepsilon = 0.1$ | §5.3 Rayleigh, S9 H-Z3 |
| **H-R2** | **Variational bounds.** The Rayleigh-Ritz method with a 3-term trial function gives eigenfrequency bounds that are $\geq 20\%$ tighter than the first-order perturbation prediction for multi-site ($K \geq 3$) configurations.                                        | Ritz bounds $\leq 5\%$ tighter than first-order                                              | §7 site optimization, spare_mace.py |
| **H-R3** | **Nonlinear fingerprint bonus.** The second-order perturbation term creates mode-dependent nonlinear shifts that _increase_ fingerprint distinguishability at $\varepsilon > 0.05$ by $\geq 15\%$ compared to the linear-only model.                                   | Distinguishability improvement $< 5\%$ or negative (nonlinearity hurts)                      | §2.2, site_optimization.py          |
| **H-R4** | **Cross-mode coupling threshold.** Off-diagonal perturbation terms (coupling between modes $n$ and $m$) are negligible ($< 1\%$ of diagonal shift) below a threshold $\varepsilon_c$ that depends on mode spacing. For golden-ratio placement, $\varepsilon_c > 0.05$. | Cross-mode coupling $> 5\%$ of diagonal even at $\varepsilon = 0.01$ (no safe linear regime) | S9 H-Z1, S9 H-Z2                    |

#### Implementation plan

| Step | Task                                                                                                                                                                   | Artifact     | Status     |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | ---------- |
| R-1  | Literature review: _Theory of Sound_ Ch. V–VI, Courant-Hilbert Vol. I §5, second-order perturbation theory for mechanical systems                                      | Design notes | ⬜ Planned |
| R-2  | Implement `simulations/rayleigh_variational.py` with 4 experiment functions: second-order correction, Rayleigh-Ritz bounds, nonlinear fingerprint, cross-mode coupling | Module       | ⬜ Planned |
| R-3  | Write `tests/test_rayleigh_variational.py` — target $\geq$ 40 tests                                                                                                    | Test file    | ⬜ Planned |
| R-4  | Run experiments, confirm or kill                                                                                                                                       | Results      | ⬜ Planned |
| R-5  | Paper integration if warranted                                                                                                                                         | Paper        | ⬜ Planned |

#### External data sources

- Rayleigh, J. W. S. _The Theory of Sound_, Vol. I, Ch. V–VI (1877) — variational principles, perturbation expansion
- Courant, R. & Hilbert, D. _Methods of Mathematical Physics_, Vol. I, §5–6 — eigenvalue perturbation, minimax theorem
- Morse, P. & Ingard, K. _Theoretical Acoustics_ (1968) — second-order acoustic perturbation
- S9 experiment data: quadratic Zeeman coefficient $\alpha_{nm} = 1.157$ at strong perturbation

#### Key equations to validate

- Second-order correction: $\Delta\omega_n^{(2)} = \sum_{m \neq n} \frac{|\langle u_m | \hat{V} | u_n \rangle|^2}{\omega_n^2 - \omega_m^2}$
- Rayleigh quotient: $\omega_n^2 \leq R[u_{\text{trial}}] = \frac{\langle u_{\text{trial}} | \hat{H} | u_{\text{trial}} \rangle}{\langle u_{\text{trial}} | u_{\text{trial}} \rangle}$
- Cross-mode coupling matrix: $V_{nm} = \int_0^L \Delta m(x)\, u_n(x)\, u_m(x)\, dx$
- Nonlinear fingerprint metric: $D^{(2)} = \|f^{(2)}_A - f^{(2)}_B\| / \|f^{(1)}_A - f^{(1)}_B\|$

#### Cross-sidebar interactions

| Interaction                               | Sidebars  | Nature                                                                            |
| ----------------------------------------- | --------- | --------------------------------------------------------------------------------- |
| Quantifies quadratic regime discovered by | S13 × S9  | Zeeman proved nonlinearity exists; Rayleigh quantifies its impact on fingerprints |
| Tightens bounds used by site optimiser    | S13 × S1  | spare_mace site placement currently uses first-order model                        |
| Error bounds for material ranking         | S13 × S12 | Gor'kov contrast factor prediction accuracy at higher perturbation strengths      |
| Variational bounds contextualise capacity | S13 × S8  | Gabor bandwidth ceiling gains a rigorous lower/upper bound from Rayleigh-Ritz     |

---

### S14 — Charles Fabry (1867–1945) & Alfred Pérot (1863–1925): Acoustic Cavity Finesse and Mode Resolution

#### Core insight

CWM's glass rod is an acoustic **Fabry-Pérot etalon**: a bounded cavity in
which standing waves form through repeated reflection at the rod ends. The
analogy is not metaphorical—it is the same wave physics in a different medium.

The Fabry-Pérot interferometer's resolving power $\mathcal{R} = m \mathcal{F}$
(mode order × finesse) determines how many spectral features can be
distinguished within the instrument's bandwidth. For CWM, the finesse
$\mathcal{F} = \pi \sqrt{R_{\text{end}}} / (1 - R_{\text{end}})$ connects
end-reflection coefficient to mode linewidth: $\delta f = \text{FSR} /
\mathcal{F}$, where $\text{FSR} = v / (2L)$ is the free spectral range
(identical to CWM's mode spacing). This provides an independent derivation
of $n_{\max}$ from interferometric principles.

More practically: the Fabry-Pérot scanning technique—sweeping a narrow-band
probe across the spectrum—is the interferometric analogue of CW lock-in readout
(§8.4). Fabry-Pérot theory predicts optimal scanning rate, peak shape (Airy
function vs. Lorentzian), and the trade-off between spectral resolution and
measurement time. This connects CWM to the precision metrology community
(optical frequency combs, laser stabilisation, gravitational wave detection)
where etalon physics has been refined for decades.

**Why this feels fruitful:** The rod already IS a Fabry-Pérot cavity. The
connection is exact, not analogical. This sidebar would import quantitative
engineering tools from the most mature branch of precision measurement.

#### Hypotheses

| ID        | Statement                                                                                                                                                                                                                                                                                                 | Kill criterion                                                                                      | Builds on                         |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------- |
| **H-FP1** | **Finesse-Q equivalence.** The acoustic finesse $\mathcal{F}$ computed from rod-end reflection coefficients predicts the mode linewidth $\delta f = f_n / Q$ to within $\pm 10\%$, providing an independent consistency check on the Q-factor model.                                                      | Finesse-predicted linewidth deviates $> 25\%$ from Q-based linewidth                                | §7 Q-factor, noise_decoherence.py |
| **H-FP2** | **Airy peak shape.** Spectral peaks near rod-end mode orders follow the Airy function $I(\nu) \propto [1 + F \sin^2(\pi\nu / \text{FSR})]^{-1}$ more accurately than Lorentzian ($R^2_{\text{Airy}} > R^2_{\text{Lorentz}}$), with measurable asymmetry at high mode numbers due to dispersion.           | Both fits $R^2 > 0.98$ with $< 1\%$ difference (indistinguishable) or Lorentzian is strictly better | §5.5 dispersion, cw_readout.py    |
| **H-FP3** | **Scanning readout enhancement.** Swept-frequency CW readout (Fabry-Pérot scanning) achieves $\geq 3$ dB better mode discrimination SNR than broadband impulse readout at equivalent total measurement time, because scanning concentrates energy in a narrow spectral window.                            | Scanning SNR $< 1$ dB improvement over broadband impulse                                            | §8.4 CW readout, cw_readout.py    |
| **H-FP4** | **End-condition engineering.** Impedance-matching the rod ends (acoustic quarter-wave transformer) can tune the effective reflection coefficient $R_{\text{end}}$ from 0.99 (high Q, narrow peaks) to 0.5 (low Q, broad peaks), trading mode resolution for readout bandwidth by a factor $\geq 3\times$. | End-condition tuning produces $< 1.5\times$ linewidth variation                                     | §7.2 anchor loss                  |

#### Implementation plan

| Step | Task                                                                                                                        | Artifact     | Status |
| ---- | --------------------------------------------------------------------------------------------------------------------------- | ------------ | ------ |
| FP-1 | Literature review: Fabry-Pérot interferometry, acoustic etalons, Airy function, finesse–Q relationship in acoustic cavities | Design notes | ✅     |
| FP-2 | Implement `simulations/fabry_perot_cavity.py` with 4 experiment functions                                                   | Module       | ✅     |
| FP-3 | Write `tests/test_fabry_perot_cavity.py` — target $\geq$ 40 tests                                                           | Test file    | ✅ 90  |
| FP-4 | Run experiments, confirm or kill                                                                                            | Results      | ✅ 2/4 |
| FP-5 | Paper integration if warranted                                                                                              | Paper        | ✅     |

#### External data sources

- Fabry, C. & Pérot, A. "Sur les franges des lames minces argentées" (Ann. Chim. Phys., 1899) — original etalon theory
- Born, M. & Wolf, E. _Principles of Optics_, Ch. 7 (1959) — Fabry-Pérot resolving power
- Yariv, A. _Optical Electronics_ (1985) — finesse, free spectral range, scanning techniques
- Kippenberg, T. et al. "Microresonator-based optical frequency combs" (Science, 2011) — modern precision metrology
- Acoustic resonator Q measurement standards (IEEE 1139, Vig 1999)

#### Key equations to validate

- Acoustic finesse: $\mathcal{F} = \frac{\pi \sqrt{R_{\text{end}}}}{1 - R_{\text{end}}}$
- Free spectral range: $\text{FSR} = v_{\text{bar}} / (2L)$ (identical to CWM mode spacing)
- Mode linewidth: $\delta f = \text{FSR} / \mathcal{F} \equiv f_n / Q$ (consistency check)
- Airy function: $I(\nu) = \frac{I_0}{1 + F \sin^2(\pi \nu / \text{FSR})}$ where $F = (2\mathcal{F}/\pi)^2$
- Resolving power: $\mathcal{R} = m \mathcal{F}$ for mode order $m$

#### Cross-sidebar interactions

| Interaction                                | Sidebars | Nature                                                                         |
| ------------------------------------------ | -------- | ------------------------------------------------------------------------------ |
| Linewidth connects to Q-factor model       | S14 × S5 | Békésy active Q-boosting changes finesse; FP theory predicts the new linewidth |
| Scanning readout extends CW lock-in        | S14 × S3 | Tesla phase encoding measured via Fabry-Pérot scanning rather than broadband   |
| Resolving power bounds mode discrimination | S14 × S9 | Zeeman splitting must exceed FP linewidth to be resolvable                     |
| End-condition engineering affects anchor Q | S14 × S7 | Anchor loss model (§7.2) is the acoustic analogue of mirror reflectivity loss  |

#### Experiment results

| ID        | Verdict      | Key metric                              | Kill/confirm mechanism                                                                   |
| --------- | ------------ | --------------------------------------- | ---------------------------------------------------------------------------------------- |
| **H-FP1** | ✅ Confirmed | Fractional error 5.1% (threshold 25%)   | Self-consistent R_eff = 0.9997 gives F ≈ Q; multiple loss mechanisms limit Q below end-R |
| **H-FP2** | ❌ Killed    | Both R² = 0.9998, advantage ≈ 0.000000  | High-finesse Airy ≈ Lorentzian to order (δν/FSR)⁴; indistinguishable in CWM regime       |
| **H-FP3** | ❌ Killed    | Scanning −13 dB vs impulse              | Time-division penalty (t_dwell = T/N) exceeds lock-in gain; broadband captures all modes |
| **H-FP4** | ✅ Confirmed | Linewidth ratio 7,922× (threshold 1.5×) | Glass/air R = 0.9999 to glass/steel R = 0.35; finesse from 2.9 to 22,816                 |

---

### S15 — Claude Shannon (1916–2001) & Harry Nyquist (1889–1976): Channel Capacity and Optimal Mode Allocation

#### Core insight

CWM is functionally a **multi-channel communication system**: $N$ independent
modes, each with mode-dependent SNR. The paper computes capacity as
$\sum_n \frac{1}{2} \log_2(1 + \text{SNR}_n)$ using equal allocation — each
mode is treated identically. But Shannon's waterfilling theorem proves this
is suboptimal whenever modes have different noise levels.

For CWM, mode-dependent noise arises from multiple sources: higher modes have
broader linewidths ($\delta f_n = f_n / Q \propto n$), thermal drift affects
high modes more ($\Delta f_n^{\text{th}} = f_n \alpha \Delta T \propto n$),
and readout transducer sensitivity varies with frequency. The waterfilling
solution allocates more readout power to high-SNR modes and less (or zero) to
modes below a threshold — potentially leaving some high-$n$ modes unused
entirely.

The Nyquist dimension completes the picture: how many modes must be measured
to faithfully reconstruct $K$ perturbation sites? Leibniz H-L3 showed that
$K$ modes suffice for perfect reconstruction, but the information-theoretic
minimum is $2K$ (Nyquist rate for the perturbation pattern's spatial bandwidth).
The gap between these tells us how much redundancy the sin² basis provides.

**Why this feels fruitful:** The paper uses Shannon's name (bits per mode at
Shannon limit) but never applies his optimization theorem. Waterfilling is
the missing piece that connects the SNR model (§4.3, Appendix A) to
information-theoretically optimal readout — and it's the natural companion
to Gabor's bandwidth ceiling (S8 H-G3).

#### Hypotheses

| ID        | Statement                                                                                                                                                                                                                                                                                                                | Kill criterion                                                                         | Builds on                             |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- | ------------------------------------- |
| **H-SN1** | **Waterfilling capacity gain.** Shannon's waterfilling algorithm, applied to CWM's mode-dependent SNR profile, improves total channel capacity by $\geq 5\%$ over uniform allocation, by concentrating readout power on low-$n$ (high-SNR) modes and cutting off modes above a noise-limited threshold $n_{\text{cut}}$. | Waterfilling gain $< 2\%$ (uniform allocation is near-optimal)                         | §4.3 SNR, Appendix A, capacity.py     |
| **H-SN2** | **Nyquist mode minimum.** Faithful reconstruction of $K$ perturbation sites requires $\geq 2K$ measured modes (acoustic Nyquist rate), not the $K$ modes suggested by Leibniz H-L3. The discrepancy arises because H-L3 assumed noiseless readout; at realistic SNR, the $2K$ minimum is strict.                         | $K$ modes suffice even at SNR $< 40$ dB (Leibniz H-L3 holds in the noisy regime)       | S7 H-L3, hopfield_recall.py           |
| **H-SN3** | **Capacity utilisation ratio.** CWM's current (uniform) capacity achieves $\geq 85\%$ of the Shannon limit for its SNR profile, confirming that the simple model in the paper is a close approximation despite being suboptimal.                                                                                         | Utilisation $< 70\%$ (significant room for improvement, undermining paper's claims)    | §1.3 capacity table, capacity.py      |
| **H-SN4** | **Mutual information per mode.** The mutual information $I(X_n; Y_n)$ between the stored pattern and readout for mode $n$ exceeds 0.5 bits/mode for $n \leq n_{\max}/2$ and falls below 0.1 bits/mode for $n > n_{\max}$, confirming that the $n_{\max}$ formula correctly identifies the usable mode range.             | $I(X_n; Y_n) > 0.5$ bits/mode persists beyond $n_{\max}$ (usable modes extend further) | §2.1 $n_{\max}$, noise_decoherence.py |

#### Implementation plan

| Step | Task                                                                                                                     | Artifact     | Status      |
| ---- | ------------------------------------------------------------------------------------------------------------------------ | ------------ | ----------- |
| SN-1 | Literature review: Shannon channel capacity, waterfilling theorem, MIMO capacity, Nyquist rate for parametric estimation | Design notes | ✅ Complete |
| SN-2 | Implement `simulations/shannon_capacity.py` with 4 experiment functions                                                  | Module       | ✅ Complete |
| SN-3 | Write `tests/test_shannon_capacity.py` — 72 tests                                                                        | Test file    | ✅ Complete |
| SN-4 | Run experiments, confirm or kill                                                                                         | Results      | ✅ Complete |
| SN-5 | Paper integration: §11.18, §14.2 bullet, §11.6 item 17, counts updated                                                   | Paper        | ✅ Complete |

#### Experiment results

| ID        | Verdict      | Key metric                              | Kill/confirm mechanism                                                                    |
| --------- | ------------ | --------------------------------------- | ----------------------------------------------------------------------------------------- |
| **H-SN1** | ❌ Killed    | Waterfilling gain 1.2% (threshold 2%)   | Mode-dependent SNR variation too modest; uniform ≈ optimal at SNR_0/n with α=1            |
| **H-SN2** | ✅ Confirmed | Error ratio K/2K = 10× (K=5)            | Aliasing from unmeasured modes K+1..2K dominates; Nyquist 2K minimum strict at finite SNR |
| **H-SN3** | ✅ Confirmed | Utilisation η_C = 98.8% (threshold 85%) | Complement of H-SN1: small waterfilling gain ↔ high uniform utilisation                   |
| **H-SN4** | ❌ Killed    | MI ≈ 0.15 bits/mode, n_max = 0          | Five-source noise model is conservative; all modes below 0 dB SNR at default parameters   |

#### External data sources

- Shannon, C. "A Mathematical Theory of Communication" (Bell Syst. Tech. J., 1948) — channel capacity theorem
- Cover, T. & Thomas, J. _Elements of Information Theory_ (1991) — waterfilling, MIMO capacity
- Nyquist, H. "Certain Topics in Telegraph Transmission Theory" (Trans. AIEE, 1928)
- Telatar, E. "Capacity of Multi-Antenna Gaussian Channels" (European Trans. Telecomm., 1999) — MIMO waterfilling
- Gabor S8 bandwidth ceiling result: $\eta$ monotonically increasing with technique count

#### Key equations to validate

- Channel capacity: $C = \sum_{n=1}^{N} \frac{1}{2}\log_2(1 + P_n / N_n)$ where $P_n$ is allocated power, $N_n$ is noise
- Waterfilling: $P_n = \max(\mu - N_n, 0)$ where $\mu$ is the water level (Lagrange multiplier)
- Capacity utilisation: $\eta_C = C_{\text{uniform}} / C_{\text{waterfilling}}$
- Nyquist mode count: $N_{\min} \geq 2K$ for $K$ perturbation sites at finite SNR
- Mutual information: $I(X_n; Y_n) = \frac{1}{2}\log_2(1 + \text{SNR}_n)$ per mode

#### Cross-sidebar interactions

| Interaction                                       | Sidebars  | Nature                                                                         |
| ------------------------------------------------- | --------- | ------------------------------------------------------------------------------ |
| Waterfilling vs Boltzmann weighting               | S15 × S11 | S11 killed Boltzmann weighting; Shannon provides the correct optimal weighting |
| Capacity utilisation contextualises Gabor ceiling | S15 × S8  | S8 H-G3 showed $\eta$ monotonic; Shannon quantifies absolute efficiency        |
| Nyquist minimum extends monadic reconstruction    | S15 × S7  | Leibniz H-L3 showed $K$ modes suffice noiseless; Nyquist adds noise floor      |
| Mode cutoff connects to Rayleigh bounds           | S15 × S13 | Rayleigh variational bounds predict which modes carry reliable information     |

---

### S16 — Émile Mathieu (1835–1890) & Gaston Floquet (1847–1920): Parametric Mode Amplification

#### Core insight

Békésy's active Q-boosting (S5, H-B3) used feedback energy injection — a
servo loop that senses mode amplitude and drives accordingly. A fundamentally
different amplification mechanism exists: **parametric amplification**, where
the cavity's effective stiffness is modulated at twice the natural frequency
($2f_n$), pumping energy into mode $n$ without any sensing or feedback.

The governing equation is Mathieu's:
$\ddot{x} + (\omega_n^2 + \varepsilon \cos 2\omega_n t)\, x = 0$. Floquet
theory predicts **stability tongues** in the $(\omega, \varepsilon)$ plane:
parameter regions where the modulation amplifies (unstable) or damps (stable)
specific modes. Inside the first instability tongue, amplitude grows
exponentially at rate $\gamma \propto \varepsilon \omega_n / (4Q)$.

This is not speculative engineering — MEMS parametric amplifiers are
commercially deployed in gyroscopes (Analog Devices ADXRS, ST
Microelectronics), where parametric drive at $2\omega$ provides 10–30 dB of
mode-selective gain. The mechanism maps directly onto CWM: a piezoelectric
transducer modulating rod stress at $2f_n$ pumps energy into mode $n$ while
leaving neighbouring modes unaffected.

**Why this feels fruitful:** S5 confirmed that active Q-boosting works
(2× $Q$, +89% modes), but the feedback mechanism is complex. Parametric
amplification achieves the same goal (mode-selective gain) with simpler
hardware (open-loop drive at $2f$), and MEMS parametric amplifiers are proven
technology. The Mathieu/Floquet framework also predicts failure modes
(instability boundaries) that constrain the safe operating regime — critical
for a memory device that must be stable.

#### Hypotheses

| ID        | Statement                                                                                                                                                                                                                                                                                 | Kill criterion                                                                          | Builds on                      |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------ |
| **H-PM1** | **Parametric gain.** Modulating rod stress at $2f_n$ with depth $\varepsilon < 0.1$ amplifies mode $n$ by $\geq 10$ dB within the first Mathieu instability tongue, at a pump power comparable to Békésy's active Q-boosting (femtowatts per mode).                                       | Gain $< 3$ dB at $\varepsilon = 0.1$ (parametric mechanism too weak in acoustic regime) | S5 H-B3, bekesy_cochlea.py     |
| **H-PM2** | **Mode selectivity.** Parametric drive at $2f_n$ produces $< 1$ dB gain at neighbouring modes $f_{n \pm 1}$, because the instability tongue width $\Delta\omega \propto \varepsilon \omega_n / (2Q)$ is narrower than the mode spacing $\text{FSR} = v/(2L)$ for $Q > 100$.               | Cross-mode gain $> 3$ dB at neighbouring modes (selectivity insufficient)               | §2.1 mode spacing              |
| **H-PM3** | **Stability boundary prediction.** The Mathieu stability chart predicts the maximum safe modulation depth $\varepsilon_{\max}$ (onset of parametric oscillation) to within $\pm 20\%$ of numerically computed threshold for CWM rod parameters.                                           | Predicted $\varepsilon_{\max}$ deviates $> 50\%$ from numerical threshold               | noise_decoherence.py           |
| **H-PM4** | **Parametric + CW readout.** Combining parametric amplification of mode $n$ with CW lock-in readout at $f_n$ achieves $\geq 6$ dB better SNR than CW readout alone at equivalent total integration time, because the parametric pump coherently adds energy at the measurement frequency. | Combined SNR improvement $< 2$ dB over CW alone (pump noise dominates the gain)         | §8.4 CW readout, cw_readout.py |

#### Implementation plan

| Step | Task                                                                                                                                          | Artifact     | Status      |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | ----------- |
| PM-1 | Literature review: Mathieu equation, Floquet theory, MEMS parametric amplifiers (Rugar & Grütter 1991, Karabalin et al. 2009)                 | Design notes | ✅ Complete |
| PM-2 | Implement `simulations/mathieu_parametric.py` with 4 experiment functions: gain vs $\varepsilon$, selectivity, stability chart, CW+parametric | Module       | ✅ Complete |
| PM-3 | Write `tests/test_mathieu_parametric.py` — 77 tests                                                                                           | Test file    | ✅ Complete |
| PM-4 | Run experiments, confirm or kill                                                                                                              | Results      | ✅ Complete |
| PM-5 | Paper integration: §11.19, §14.2 bullet, §11.6 item 18, counts updated                                                                        | Paper        | ✅ Complete |

#### Experiment results

| ID        | Verdict      | Key metric                                  | Kill/confirm mechanism                                                                            |
| --------- | ------------ | ------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **H-PM1** | ✅ Confirmed | Gain 12.0 dB at ε = 0.003 (threshold 10 dB) | G = 1/(1−εQ/2) = 4.0×; pump power 0.055 fW vs Békésy 9.1 fW (166× cheaper)                        |
| **H-PM2** | ✅ Confirmed | Neighbour gain 0.0004 dB (threshold 1 dB)   | Tongue width 525 kHz vs FSR 70 MHz; selectivity ratio 133×; Lorentzian roll-off of Mathieu tongue |
| **H-PM3** | ✅ Confirmed | Deviation 9.3% (threshold 20%)              | ε_predicted = 0.00400 vs ε_numerical = 0.00441; first-order Floquet theory is accurate            |
| **H-PM4** | ✅ Confirmed | Improvement 12.0 dB (threshold 6 dB)        | Parametric G² compounds with CW averaging; CW 33.4 dB + parametric 12.0 dB = 45.5 dB              |

#### External data sources

- Mathieu, É. "Mémoire sur le mouvement vibratoire d'une membrane" (J. Math. Pures Appl., 1868) — Mathieu equation
- Floquet, G. "Sur les équations différentielles linéaires à coefficients périodiques" (Ann. Sci. ENS, 1883) — Floquet theory
- Rugar, D. & Grütter, P. "Mechanical parametric amplification and thermomechanical noise squeezing" (PRL, 1991) — first MEMS parametric amplifier
- Karabalin, R. et al. "Parametric nanomechanical amplification at very high frequency" (Nano Lett., 2009) — MHz-scale parametric gain
- Turner, K. et al. "Five parametric resonances in a microelectromechanical system" (Nature, 1998) — stability tongues in MEMS
- Analog Devices ADXRS gyroscope parametric drive documentation

#### Key equations to validate

- Mathieu equation: $\ddot{x} + (\omega_n^2 + \varepsilon\omega_n^2 \cos 2\omega_n t)\, x = 0$
- Parametric gain rate: $\gamma = \varepsilon\omega_n / 4 - \omega_n / (2Q)$ (onset when $\gamma > 0$, i.e., $\varepsilon > 2/Q$)
- Instability tongue width: $\Delta\omega / \omega_n \approx \varepsilon / 2$ at first tongue
- Threshold modulation depth: $\varepsilon_{\min} = 2/Q$ (minimum pump for amplification)
- Parametric SNR gain: $G_{\text{par}} = (1 - \varepsilon Q / 2)^{-1}$ below threshold

#### Cross-sidebar interactions

| Interaction                                           | Sidebars  | Nature                                                                               |
| ----------------------------------------------------- | --------- | ------------------------------------------------------------------------------------ |
| Parametric vs feedback amplification                  | S16 × S5  | Békésy used feedback; Mathieu uses open-loop pump — complementary mechanisms         |
| Stability boundaries constrain readout                | S16 × S14 | Fabry-Pérot scanning must stay below Mathieu instability threshold                   |
| Mode-selective gain enhances Zeeman splitting readout | S16 × S9  | Parametric amplification of split mode pairs could improve splitting measurement SNR |
| Pump power budget extends energy analysis             | S16 × S3  | Tesla phase readout energy budget gains a parametric amplification term              |

---

### S17 — Coronal Seismology: Astrophysical Validation of Standing-Wave Information Theory

#### Historical figure

**Solar coronal seismology** as a field, founded by Uchida (1970), Roberts, Edwin & Benz (1984), and Nakariakov et al. (1999). This sidebar differs from all preceding ones: instead of importing physics into CWM, it **exports CWM's mathematical predictions to the astrophysical system where the same eigenmode physics already operates at stellar scales**. Solar coronal loops are bounded plasma cavities with discrete MHD eigenmodes — the same sensitivity matrix, the same perturbation theory, the same eigenfrequency readout that CWM uses in glass.

#### Relevance to CWM

If CWM's results are truly substrate-independent (as the paper claims), they must hold in any bounded standing-wave cavity with harmonic eigenmodes. Coronal seismology is the most mature natural test case: decades of published eigenfrequency observations from SDO/AIA, TRACE, Hinode, and Parker Solar Probe. Validating CWM's predictions against nature — not against our own simulations — constitutes a qualitatively different class of evidence.

#### Hypotheses

| ID        | Hypothesis                                             | Metric                                                            | Kill criterion                                       |
| --------- | ------------------------------------------------------ | ----------------------------------------------------------------- | ---------------------------------------------------- |
| **H-CS1** | Rational-position inversion degeneracy                 | Condition number of seismological inversion matrix                | κ does NOT peak at rational fractions of loop length |
| **H-CS2** | Multi-mode-family diagnostic independence              | Cross-correlation between kink, sausage, longitudinal diagnostics | Cross-correlation > 0.3 (channels not independent)   |
| **H-CS3** | Logarithmic capacity ceiling                           | Recoverable parameters vs. observed harmonic count                | Does not follow $C \approx a \ln N + b$              |
| **H-CS4** | Published P₁/2P₂ anomalies correlate with conditioning | Spearman ρ between period-ratio deviation and predicted κ         | ρ < 0.5 or p > 0.05                                  |
| **H-CS5** | Footpoint impedance maps to Fabry–Pérot finesse        | Ratio Q_finesse / Q_damping                                       | Ratio outside [0.5, 2.0]                             |
| **H-CS6** | Perturbation scaling linearity                         | Linear R² of δω/ω vs ε for ε < 0.1                                | R² < 0.99 (nonlinear response)                       |
| **H-CS7** | Irrational probe spacing maximises inversion accuracy  | Inversion RMS: golden-ratio vs equispaced vs random               | Golden-ratio NOT superior                            |

#### Implementation plan

| Step | Task                                                                                                         | Artifact     | Status  |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------ | ------- |
| CS-1 | Literature review: Nakariakov & Verwichte (2005), Roberts et al. (1984), SDO/AIA observational data catalogs | Design notes | ✅ Done |
| CS-2 | Implement `simulations/coronal_seismology.py` — 7 experiments (H-CS1–CS7), MHD eigenmode basis               | Module       | ✅ Done |
| CS-3 | Write `tests/test_coronal_seismology.py` — 109 tests                                                         | Test file    | ✅ Done |
| CS-4 | Run experiments against synthetic MHD data and published coronal loop observations                           | Results      | ✅ Done |
| CS-5 | Integrate into paper v15.md (§11.20, TOC, §14.2)                                                             | Paper        | ✅ Done |

#### External data sources

- Nakariakov, V.M. & Verwichte, E. (2005), "Coronal Waves and Oscillations," Living Reviews in Solar Physics, 2(3)
- Nakariakov, V.M. & Ofman, L. (2001), "Determination of the coronal magnetic field by coronal loop oscillations," A&A 372 L53
- SDO/AIA EUV oscillation catalogs (publicly available)
- Duckenfield et al. (2018), "Detection of the second harmonic of decay-less kink oscillations"

#### Key equations to validate

- MHD kink mode frequency: $\omega_K = \sqrt{2k_z^2 B^2 / \mu(\rho_i + \rho_e)}$
- Sausage mode frequency: $\omega_S = \sqrt{k_z^2 B^2 / \mu\rho_e}$
- Period ratio anomaly: $P_1/2P_2$ deviation from 1.0 reflects density stratification — CWM predicts this deviation correlates with sensitivity-matrix conditioning
- CWM sensitivity matrix transferred to MHD: $S_{nk} = \sin^2(n\pi x_k / L)$ where $x_k$ are density perturbation positions along the coronal loop

#### Cross-sidebar interactions

| Interaction                                                      | Sidebars  | Nature                                                                                 |
| ---------------------------------------------------------------- | --------- | -------------------------------------------------------------------------------------- |
| Rationality test transfers to plasma                             | S17 × S13 | The $\sin^2$ periodicity proof applies to any harmonic standing-wave system            |
| Polysemic readout predicts multi-mode diagnostic independence    | S17 × S2  | Scranton's polysemic principle predicts kink/sausage/longitudinal channel independence |
| Logarithmic ceiling constrains seismological information content | S17 × S10 | Kepler's capacity ceiling applies to coronal harmonic spectra                          |
| Fabry-Pérot finesse describes coronal loop cavity                | S17 × S14 | End-condition engineering = footpoint impedance mismatch in coronal loops              |
| Gor'kov force analog: dusty plasma equilibria                    | S17 × S12 | Force-optimal positions in dusty plasma are information-degenerate (S12 prediction)    |

#### Experiment results

| ID        | Hypothesis                                | Key metric                                          | Verdict      |
| --------- | ----------------------------------------- | --------------------------------------------------- | ------------ |
| **H-CS1** | Rational-position inversion degeneracy    | κ_rational / κ_irrational ≈ 10¹³                    | ✅ CONFIRMED |
| **H-CS2** | Multi-mode-family diagnostic independence | Mean cross-correlation = 0.29 (< 0.3)               | ✅ CONFIRMED |
| **H-CS3** | Logarithmic capacity ceiling              | R²_log = 0.71 > R²_lin = 0.33                       | ✅ CONFIRMED |
| **H-CS4** | Published P₁/2P₂ ↔ conditioning           | Spearman ρ = −0.238, p = 0.44                       | ❌ KILLED    |
| **H-CS5** | Footpoint Fabry–Pérot finesse             | Q_finesse / Q_damping = 0.92                        | ✅ CONFIRMED |
| **H-CS6** | Perturbation scaling linearity            | Linear R² = 0.9997                                  | ✅ CONFIRMED |
| **H-CS7** | Irrational probe spacing supremacy        | Golden RMS = 0.020 vs equispaced 0.409 (20× better) | ✅ CONFIRMED |

**Totals:** 6 confirmed, 1 killed out of 7 hypotheses.

**H-CS4 kill reason:** Using a gravitational density profile ρ(z) ∝ exp(−ε·sin πz) that correctly models footpoint-heavy coronal stratification (producing P₁/2P₂ < 1.0 as observed), with per-loop harmonic counts N(L) scaling with loop length (2–4 overtones), no statistically significant correlation between P₁/2P₂ deviation and sensitivity-matrix condition number (ρ = −0.238, p = 0.44). The interaction between stratification strength ε and the independently varying harmonic count disrupts any monotonic ε → κ relationship.

#### Completed reference

- **Module:** `simulations/coronal_seismology.py` (~530 lines, 7 experiments)
- **Tests:** `tests/test_coronal_seismology.py` (109 tests, all passing)
- **Paper:** v15.md §11.20, TOC entry, §11.6 item 19, §14.2 bullet
- **Registration:** `__init__.py` Phase 9m, `common.py` 43/1821
- **Commit:** pending

---

### S18 — Gauge Geometry: Fiber-Bundle Structure of the Sensitivity Matrix

#### Historical figure / tradition

**Yang–Mills gauge theory** and the fiber-bundle formalism developed by Yang & Mills (1954), Atiyah & Bott (1983), Donaldson (1983), and Uhlenbeck (1982). Eric Weinstein's Harvard dissertation (1992, under Raoul Bott) extended self-dual Yang–Mills equations beyond dimension four, demonstrating that gauge-geometric structures are not special to a single dimensionality — a principle directly relevant to CWM's dimensional tower (1D rod → 2D plate → 3D cavity). This sidebar tests whether the well-established mathematical toolkit of gauge theory (connections, curvature, holonomy, topological invariants) provides quantitative predictions for CWM's sensitivity-matrix physics.

#### Relevance to CWM

CWM's Rayleigh perturbation formula $\partial f_n / \partial m(x) \propto \sin^2(n\pi x/L)$ defines a map from **parameter space** (perturbation positions and masses) to **frequency space** (eigenmode shifts). In gauge-geometric language, this is a **connection on a fiber bundle**: the base manifold is the configuration space of perturbation positions, the fiber is the space of spectral fingerprints, and the sensitivity matrix is the connection form. The curvature of this connection, its holonomy around closed loops, and its topological invariants (rank, winding numbers) should produce testable predictions about inversion conditioning, information capacity, and dimensional scaling. If CWM's physics has genuine gauge-geometric structure, these predictions quantify it; if not, the analogy is decorative.

#### Hypotheses

| ID        | Hypothesis                                                       | Metric                                                              | Kill criterion                                                              |
| --------- | ---------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| **H-GG1** | Curvature of sensitivity connection predicts conditioning        | Correlation of ‖F‖² (Yang-Mills functional) with κ(S)               | R² < 0.5 between curvature norm and condition number                        |
| **H-GG2** | Information capacity is a gauge invariant                        | Capacity under mode permutation, SVD rotation, position translation | Capacity changes by > 1% under any gauge transformation                     |
| **H-GG3** | 1D sensitivity formulas arise from 2D by dimensional reduction   | Exact recovery of 1D κ and capacity from 2D reduction               | Relative error > 5% between reduced 2D and direct 1D results                |
| **H-GG4** | Rank of sensitivity matrix is a topological invariant            | Piecewise constancy of rank under smooth position deformation       | Rank changes at > 5% of tested positions (not just rational points)         |
| **H-GG5** | Holonomy of sensitivity connection is non-trivial and predictive | Correlation of tr(H) with enclosed curvature (Ambrose-Singer)       | H = I always (trivial holonomy), or R² < 0.5 between holonomy and curvature |

#### Implementation plan

| Step | Task                                                                                            | Artifact     | Status  |
| ---- | ----------------------------------------------------------------------------------------------- | ------------ | ------- |
| GG-1 | Literature review: gauge theory fundamentals, fiber bundles, connections, Yang-Mills functional | Design notes | ✅ Done |
| GG-2 | Implement `simulations/gauge_geometry.py` — 5 experiments (H-GG1–GG5)                           | Module       | ✅ Done |
| GG-3 | Write `tests/test_gauge_geometry.py` — 88 tests                                                 | Test file    | ✅ Done |
| GG-4 | Run experiments: 3 confirmed, 2 killed                                                          | Results      | ✅ Done |
| GG-5 | Integrate into paper v15.md (§11.21, TOC, §14.2)                                                | Paper        | ✅ Done |

#### Results

| ID        | Verdict       | Key metric                                                       |
| --------- | ------------- | ---------------------------------------------------------------- |
| **H-GG1** | **KILLED**    | R² = 0.03 — curvature and conditioning are orthogonal functions  |
| **H-GG2** | **CONFIRMED** | Permutation Δ = 0.0000%, rotation Δ = 0.0000% — exact invariance |
| **H-GG3** | **CONFIRMED** | κ error = 0.0000%, capacity error = 0.0000% — exact reduction    |
| **H-GG4** | **CONFIRMED** | 0.00% rank changes across 500 smooth positions                   |
| **H-GG5** | **KILLED**    | Mean ‖H − I‖ = 1.66 (non-trivial), but R² = 0.35 < 0.5           |

**Tally: 3 confirmed, 2 killed (3:2)**

Commit: pending

#### Key equations to validate

- Connection 1-form: $A_{nk}(x) = \sin^2(n\pi x_k / L)$ (the sensitivity matrix IS the connection)
- Curvature tensor: $F_{nk,j} = \partial A_{nk} / \partial x_j = 2n\pi/L \cdot \sin(n\pi x_j/L) \cos(n\pi x_j/L)$
- Yang-Mills functional: $\|F\|^2 = \sum_{n,k,j} F_{nk,j}^2$
- Holonomy matrix: $H = \prod_i M_i$ where $M_i$ are transition matrices along a closed path
- Dimensional reduction: $S^{1D}_{n}(x) = \int_0^b S^{2D}_{nm}(x,y)\,dy$

#### Cross-sidebar interactions

| Interaction                                                         | Sidebars  | Nature                                                                                      |
| ------------------------------------------------------------------- | --------- | ------------------------------------------------------------------------------------------- |
| Curvature reinterprets condition number from S13                    | S18 × S13 | Golden-ratio optimality may correspond to curvature minimisation (Yang-Mills minimum)       |
| Gauge invariance formalises SVD rewriting freedom from §12          | S18 × §12 | Virtual rewriting partitions are gauge orbits of the sensitivity connection                 |
| Dimensional reduction connects Chladni 2D to rod 1D                 | S18 × S4  | The 9.1× mode scaling factor should emerge from the reduction formula                       |
| Topological rank invariant relates to Shannon capacity              | S18 × S15 | Shannon capacity may be expressible in terms of topological invariants (Chern class analog) |
| Holonomy around rational positions relates to Weyl equidistribution | S18 × S13 | Rational positions are "topology-changing" points where rank drops (gauge singularities)    |
