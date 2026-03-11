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

| Sidebar | Figure              | Module              | Tests | Hypotheses               | Status      |
| ------- | ------------------- | ------------------- | ----- | ------------------------ | ----------- |
| **S1**  | Spare / Mace        | `spare_mace.py`     | 62    | H1–H6: 6/6 confirmed     | ✅ Complete |
| **S2**  | Scranton / Dogon    | `scranton_dogon.py` | 62    | H7–H12: 6/6 confirmed    | ✅ Complete |
| **S3**  | Tesla               | `tesla_phase.py`    | 50    | H-T1–T4: 4/4 confirmed   | ✅ Complete |
| **S4**  | Chladni             | `chladni_plates.py` | 69    | H-C1–C4: 4/4 confirmed   | ✅ Complete |
| **S5**  | Békésy              | `bekesy_cochlea.py` | 68    | H-B1–B4: 1/4 confirmed   | ✅ Complete |
| **S6**  | Franklin (Rosalind) | `franklin_phase.py` | 69    | H-F1–F4: 0/4 confirmed   | ✅ Complete |
| **S7**  | Leibniz             | `leibniz_binary.py` | 73    | H-L1–H-L4: 3/4 confirmed | ✅ Complete |

**Running totals:** 33 modules · 959 tests · test count must only go up.

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
S7 (Leibniz) ─── depends on S1, S2 ───┘
  └─ binary/combinatorial encoding
     extends hopfield + semantic work
```

**Recommended order: S4 → S5 → S6 → S7**

Rationale:

1. **S4 (Chladni)** opens a new device geometry (2D membranes) — the highest-value
   scientific question because it could change the hardware roadmap.
2. **S5 (Békésy)** extends geometry further (tapered cavities) and introduces
   bio-inspired noise rejection — high value, independent of S4.
3. **S6 (Franklin)** builds directly on S3 (Tesla) phase results and needs those
   results stable before extending them with phase-retrieval algorithms.
4. **S7 (Leibniz)** is the most "firmware-level" sidebar (binary quantization,
   codebooks) and benefits from having all the physics sidebars stable first.

---

## Cross-Sidebar Interaction Matrix

Some results from one sidebar may affect another. Track known interactions:

| Interaction                                | Sidebars | Nature                                                                                                      |
| ------------------------------------------ | -------- | ----------------------------------------------------------------------------------------------------------- |
| 2D plate phase encoding                    | S4 × S3  | Chladni plate modes have 2D phase structure; Tesla's phase independence (H-T1) may generalize               |
| Cochlear windowing + polysemic readout     | S5 × S2  | Békésy's critical bands may optimize Scranton's sub-channel partitioning                                    |
| Phase retrieval + phase encoding           | S6 × S3  | Franklin's algorithms directly extend Tesla's phase results                                                 |
| Binary quantization + pruning              | S7 × S1  | Leibniz's binarization is an extreme form of Spare/Mace's pruning                                           |
| Tapered rod + Chladni sensitivity          | S5 × S4  | Non-uniform geometry appears in both; shared sensitivity-function math                                      |
| Monadic reconstruction + polysemic readout | S7 × S2  | Each mode encoding the whole pattern (Leibniz) parallels each sub-channel encoding independently (Scranton) |

---

## Killed Hypotheses Log

_Record every hypothesis that fails its kill criterion. This is as scientifically
valuable as confirmations — it maps the boundary of what the physics supports._

| Hypothesis   | Sidebar | Date | Kill reason | Insight gained |
| ------------ | ------- | ---- | ----------- | -------------- |
| _(none yet)_ |         |      |             |                |

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
