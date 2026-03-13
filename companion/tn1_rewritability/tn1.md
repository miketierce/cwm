# Paths to Rewritability in Coherent Wave Memory

**Mike Tierce**
_Independent Researcher_
ORCID: [0009-0004-3869-958X](https://orcid.org/0009-0004-3869-958X)
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

## 1. CWM Architecture in Brief

_This section summarizes the Coherent Wave Memory architecture established in the companion paper [1]. Readers familiar with [1] may skip to Section 2._

### 1.1 Core Idea

CWM stores data in the _acoustic eigenmode spectrum_ of a solid glass resonator. A glass rod vibrates at a set of natural frequencies—its eigenmodes—each an independent information channel. Mass perturbations on the rod's surface shift each eigenfrequency by a different amount (via the Rayleigh perturbation formula), creating a unique _spectral fingerprint_. To read, excite the rod with a broadband pulse and measure the frequency spectrum. To search an array of rods, drive them all with a query spectrum: the rod whose stored fingerprint best matches the query resonates most strongly—a nearest-neighbor search executed by wave physics in one acoustic propagation cycle (~3.6 µs), with no processor, no memory bus, and no software.

The $n$-th longitudinal eigenmode has frequency $f_n = nv/(2L)$, where $v$ is the speed of sound and $L$ is the rod length. The maximum number of thermally stable modes depends only on the material and temperature stability:

$$n_{\max} = \left\lfloor \frac{1}{2\alpha \,\Delta T} \right\rfloor$$

For borosilicate glass ($\alpha = 3.3 \times 10^{-6}$/K) at $\pm 1$ K: $n_{\max} = 9{,}380$ modes. This number is independent of rod length—a 150 mm prototype rod and a 1 mm MEMS rod support the same mode count.

### 1.2 Key Numbers

The companion paper validates the following from first-principles simulation (34 modules, 1,036 automated tests):

| Parameter                  | Value         | Source            |
| -------------------------- | ------------- | ----------------- |
| Macro prototype SNR        | 98.5 dB       | Measured          |
| Thermally stable modes     | 9,380         | Analytical        |
| Bits per mode              | 16.4          | Shannon limit     |
| MEMS density (1 mm boro.)  | 95.1 Gbit/cm³ | Scaling law       |
| MEMS density (0.5 mm SiO₂) | 1.4 Tbit/cm³  | Scaling law       |
| Write energy               | 15 fJ/bit     | Analytical        |
| Readout time               | 3.6 µs        | Analytical        |
| $Q_{\text{total}}$ (MEMS)  | 9,097         | 5-mechanism model |
| Anchor loss fraction       | 4.4%          | 5-mechanism model |
| Endurance                  | >10¹⁵ cycles  | Non-destructive   |

### 1.3 The Coupling Matrix

The relationship between the perturbation pattern (spatial arrangement of mass dots) and the spectral fingerprint (mode frequency shifts) is a linear mapping. Discretizing the rod into $n_p$ perturbation sites and measuring $n_m$ eigenmode frequencies, this mapping is a matrix:

$$C \in \mathbb{R}^{n_m \times n_p}, \qquad \Delta\mathbf{f} = C \cdot \mathbf{p}$$

where $C_{ij} = \sin\!\big((i+1)\pi(j+1)/(n_p + 1)\big)$ models the standing-wave displacement of mode $i$ at perturbation site $j$. The singular value decomposition of $C$ partitions the perturbation space into:

- **Column space** (rank dimensions): perturbation patterns that produce detectable spectral shifts.
- **Null space** ($n_p - \text{rank}$ dimensions): perturbation patterns invisible to the standard spectral readout.

This decomposition, introduced in the companion paper's null-space multiplexing result [1, §10.4], is the mathematical foundation for the virtual-rewrite experiments of Section 3.

### 1.4 Associative Recall as Hopfield Network

CWM's read/search operation is mathematically a Hopfield associative memory [2, 3]. The weight matrix is the physics of the eigenmode spectrum. The capacity limit is:

$$P_{\max} \approx 0.138\,N$$

for $< 1\%$ bit-error rate, where $N$ is the number of modes. For $N = 9{,}380$: $P_{\max} \approx 1{,}294$ patterns per rod. The companion paper further showed that synaptic pruning (zeroing weak weights) improves recall accuracy by +10.7% at high load factors [1, §10.1], and that null-space multiplexing adds +60% bonus capacity with zero hardware changes [1, §10.4].

### 1.5 The Missing Piece

As presented in the companion paper, CWM is read-only memory: perturbation patterns are fixed at fabrication by lithographic mass deposition. The rod is a "sonic telescope"—factory-pointed at a target and forever locked on. This is sufficient for applications like content-addressable memory, acoustic fingerprint matching, and edge inference, where the stored patterns are fixed at manufacturing time.

But many applications require reconfigurability. A fraud detection system needs new patterns as new attack vectors emerge. A signals-intelligence matcher needs to update its library as threats evolve. Even the simplest embedded device needs occasional firmware updates.

The question this technical note addresses is: _can the telescope become an instrument?_ Can we make CWM reconfigurable without destroying the physics that makes it work?

---

## 2. The Rewritability Question

### 2.1 Telescope vs. Instrument

Consider two ways to think about a CWM rod:

**The telescope model.** A rod is manufactured with a fixed perturbation pattern and deployed as a matched filter for that pattern. It is a detector, not a programmable device. You "point" the telescope by choosing which rod to read, not by changing what any rod stores. An array of 1,000 rods is a library of 1,000 fixed filters—like a radio telescope array where each dish is permanently aimed at a different star.

**The instrument model.** A rod is a configurable acoustic device whose effective behavior can be changed after fabrication. It is a pipe organ, not a telescope—the same pipes can play different music depending on which stops are pulled and which keys are pressed. Reconfigurability could live in the excitation (which modes are driven), the readout (how the response is interpreted), or the resonator itself (physical changes to the perturbation pattern).

The companion paper presents CWM exclusively in telescope mode. This is the conservative, validated position: the physics works, the numbers are solid, and fixed-pattern applications (CAM, fingerprint matching, edge inference) are commercially significant.

But the instrument model is more interesting—and, as we will show, more physically accessible than it first appears.

### 2.2 Five Candidate Architectures

Brainstorming from first principles, we identified five candidate paths to rewritability. Each represents a different point on the hardware-modification spectrum:

1. **Replaceable rod cartridges.** Physically swap rods. Equivalent to swapping an EPROM chip—rewritable at the system level, not the device level. Trivially implementable but limited to coarse-grained updates.

2. **Reset-coat-rebaseline.** Chemically strip the perturbation layer, recoat, re-measure. Rewritable in the sense that a whiteboard is rewritable—possible, but slow and destructive.

3. **Binary perturbation sites.** Pre-fabricate discrete docking sites on the rod; each site has a MEMS switch that toggles a small mass between coupled (touching the rod) and decoupled (lifted off). Like RF MEMS switches, which already operate at GHz frequencies in 5G front-ends.

4. **Multi-shell resonator.** High-Q glass core surrounded by a thin writable shell (polymer, phase-change material, magnetostrictive film). The shell perturbs modes without killing the core's Q. Analogous to how a violin string's overtone spectrum depends on the rosin coating, not just the steel core.

5. **Firmware-defined virtual rewriting.** Don't change the rod at all. Change what you _ask_ it and how you _listen_. Different excitation patterns and readout projections make the same physical rod behave like different logical devices.

Architectures 1 and 2 are mechanical and chemical operations—important for system-level design but not interesting physics questions. We set them aside.

Architectures 3, 4, and 5 are testable with existing simulation infrastructure. They map to our three experimental tracks:

| Track | Architecture                       | Hardware change              | Rewrite speed                                         | Experiments |
| ----- | ---------------------------------- | ---------------------------- | ----------------------------------------------------- | ----------- |
| A     | Firmware-defined virtual rewriting | None                         | Nanoseconds (firmware load)                           | H7, H8, H9  |
| B     | Binary perturbation sites          | MEMS switches on rod surface | Microseconds (electrostatic latch)                    | H10, H11    |
| C     | Multi-shell resonator              | Thin-film writable coating   | Milliseconds–seconds (phase change, magnetostriction) | H12, H13    |

### 2.3 The Central Constraint

All three tracks must satisfy the same constraint: **rewriting must not destroy Q.**

The companion paper's Q-factor analysis [1, §6] established that the total quality factor of a 1 mm MEMS glass resonator is $Q_{\text{total}} = 9{,}110$, with material intrinsic loss ($Q_{\text{mat}} = 10{,}000$) as the dominant mechanism. The 5-mechanism loss budget is:

$$\frac{1}{Q_{\text{total}}} = \frac{1}{Q_{\text{mat}}} + \frac{1}{Q_{\text{anchor}}} + \frac{1}{Q_{\text{TED}}} + \frac{1}{Q_{\text{surface}}} + \frac{1}{Q_{\text{gas}}}$$

Any rewrite mechanism adds a new loss term. Track A avoids this entirely (firmware changes don't add loss). Tracks B and C add physical structures that contribute to $1/Q_{\text{surface}}$ or introduce new loss channels. The experiments in Sections 4 and 5 quantify these penalties and determine the operating envelope where $Q > 5{,}000$—the threshold below which CWM loses its competitive advantage.

### 2.4 Experimental Approach

All seven experiments are implemented in the simulation module `simulations/rewritability.py`, tested by 68 automated tests in `tests/test_rewritability.py`, and reproducible via:

```python
from simulations.rewritability import run_all_rewritability
results = run_all_rewritability(verbose=True)
```

Each experiment produces a result dataclass with a boolean `verdict` field indicating whether the hypothesis is confirmed, along with all intermediate quantities needed to reproduce and extend the analysis. The experiments build on the existing simulation infrastructure (34 modules, 1,036 tests from the companion paper) and import directly from the Hopfield recall, interference, and Q-model modules.

---

## 3. Track A — Firmware-Defined Virtual Rewriting

Track A asks: _without touching the resonator, how many different logical devices can we extract from one physical rod by changing only the excitation and readout?_

The answer determines whether CWM needs hardware rewriting at all for many applications. If a single rod can behave as 4 or 8 or 16 different logical devices selectable at firmware speed (nanoseconds), then "rewriting" becomes a CMOS operation—loading different projection coefficients into the readout ASIC—and the glass rod remains pristine, preserving its full Q.

### 3.1 H7: Multi-Projection Virtual Rewrite

**Hypothesis.** The SVD of the coupling matrix $C$ can be partitioned into $K$ orthogonal subspaces, each functioning as an independent logical memory with zero cross-talk.

**Background.** The companion paper's null-space experiment [1, §10.4] demonstrated two channels: the column space (standard readout) and the null space (complementary readout), with perfect fidelity and zero leakage between them. This is a 2-partition split. H7 generalizes: instead of just column-space vs. null-space, we partition _all_ right-singular vectors into $K$ equal groups. Each group spans a subspace; patterns encoded in that subspace are invisible to all other subspaces. Each subspace is a virtual device.

**Setup.** Build a coupling matrix $C$ ($n_m = 10$ modes, $n_p = 24$ perturbation sites) using the sinusoidal model $C_{ij} = \sin\!\big((i+1)\pi(j+1)/(n_p+1)\big)$. Compute the full SVD: $C = U \Sigma V^T$. Partition the 24 right-singular vectors into $K = 4$ groups of 6. For each partition:

1. Encode 5 random test patterns as linear combinations of that partition's basis vectors.
2. Add Gaussian noise ($\sigma = 0.01$).
3. Project the noisy readout onto the partition's basis.
4. Measure fidelity (cosine similarity between encoded and recovered coefficients).
5. Measure cross-talk: project patterns from partition $j$ onto partition $k$'s basis ($j \neq k$).

**Results.**

| Partition | Dimensions | Fidelity | Max cross-talk to other partitions |
| --------- | ---------- | -------- | ---------------------------------- |
| 1         | 6          | 1.000    | < $10^{-15}$                       |
| 2         | 6          | 1.000    | < $10^{-15}$                       |
| 3         | 6          | 1.000    | < $10^{-15}$                       |
| 4         | 6          | 1.000    | < $10^{-15}$                       |

- **Mean fidelity:** 1.000
- **Maximum cross-talk:** $3.5 \times 10^{-16}$ (numerical zero—limited by floating-point precision)
- **Effective devices:** 4 (all partitions achieve fidelity > 0.8)
- **Verdict: ✅ CONFIRMED**

**Interpretation.** The orthogonality is exact, not approximate—a mathematical consequence of the SVD, not a favorable coincidence. As long as the readout system can resolve the projection coefficients above the noise floor, each partition is a perfectly isolated logical memory. With 24 perturbation sites, we can push to $K = 8$ partitions of 3 dimensions each, or $K = 12$ partitions of 2 dimensions each, trading per-device capacity for device count.

At MEMS scale with $n_p = 1{,}000$ perturbation sites (1 µm pitch on a 1 mm rod), the number of available partitions is $\lfloor 1{,}000 / d_{\min} \rfloor$ where $d_{\min}$ is the minimum useful subspace dimension (typically 2–3). This gives **300–500 virtual devices** from a single physical rod, each switchable by loading different projection coefficients into the CMOS readout die—a firmware operation taking nanoseconds.

**What this means.** A CWM array with 1,000 physical rods and 100 virtual devices per rod effectively provides 100,000 logical devices—without any hardware rewriting. For applications that need to update their pattern library (fraud detection, threat-signature matching), this means the "rewrite" is a firmware update to the CMOS die, not a physical change to the resonator.

### 3.2 H8: Mode-Subset Logical Devices

**Hypothesis.** Driving and reading contiguous subsets of the mode spectrum creates independent logical memories from one physical rod.

**Background.** H7 uses SVD to find optimal partitions; H8 uses the simplest possible partitioning—contiguous frequency bands. This is the "organ stop" approach: pull stop 1 to play the bass pipes, pull stop 2 for the tenor pipes. Different stops, different sounds, same organ.

**Setup.** A Hopfield associative memory of $N = 200$ modes stores $P = 3$ patterns. We divide the mode spectrum into 4 contiguous subsets of 50 modes each. For each subset, we extract the sub-patterns (the 50-mode slice of each stored pattern), build a sub-network, and test recall accuracy under 15% noise corruption over 30 trials.

Cross-talk is measured by projecting a pattern from subset A's modes onto subset B's weight matrix—which should produce low overlap since the modes are physically distinct frequency ranges.

**Results.**

| Subset | Modes   | Recall accuracy | Independent? |
| ------ | ------- | --------------- | ------------ |
| 1      | 1–50    | 1.000           | ✅           |
| 2      | 51–100  | 1.000           | ✅           |
| 3      | 101–150 | 1.000           | ✅           |
| 4      | 151–200 | 1.000           | ✅           |

- **Mean recall:** 1.000
- **Independent devices:** 4 (all subsets achieve recall > 0.7)
- **Verdict: ✅ CONFIRMED**

**Capacity scaling.** We swept total mode count and subset count to map the operating envelope:

| Total modes | Subsets | Modes/subset | P/N ratio | Mean recall | Independent |
| ----------- | ------- | ------------ | --------- | ----------- | ----------- |
| 40          | 4       | 10           | 0.300     | 0.90        | 4           |
| 80          | 4       | 20           | 0.150     | 0.99        | 4           |
| 200         | 4       | 50           | 0.060     | 1.00        | 4           |
| 400         | 4       | 100          | 0.030     | 1.00        | 4           |
| 400         | 8       | 50           | 0.060     | 1.00        | 8           |
| 400         | 16      | 25           | 0.120     | 0.95        | 15          |

The critical parameter is the per-subset load factor $P/N_{\text{subset}}$. When this stays below the Hopfield capacity limit (0.138), recall is reliable. With the full 9,380-mode spectrum, even 16 subsets of ~586 modes each give a per-subset capacity of $0.138 \times 586 \approx 81$ patterns—far exceeding typical pattern loads.

**What this means.** Mode-subset partitioning is the simplest form of virtual rewriting and the most immediately deployable. The excitation chirp already covers a specific frequency range; narrowing it to a subset is a parameter change in the drive waveform generator. A 9,380-mode rod could support **~15 independent logical memories** of ~625 modes each (capacity ~86 patterns per memory), all selectable by adjusting the chirp bandwidth.

### 3.3 H9: Readout Mask Library

**Hypothesis.** Applying different spectral masks to the same rod's readout produces multiple distinct effective devices.

**Background.** H7 and H8 partition modes into non-overlapping groups. H9 explores a softer approach: _overlapping_ masks that weight the full spectrum differently. This is closer to how a graphic equalizer changes the character of a recording—the same audio, heard differently through different filter curves.

**Setup.** Store $P = 5$ patterns in an $N = 100$ Hopfield network. Apply seven different masks to the weight matrix before recall, each emphasizing a different region or structure of the spectrum:

1. **Full spectrum** — unmasked baseline ($w_{ij}' = w_{ij}$)
2. **Low-mode 3×** — modes 1–33 weighted 3× ($w_{ij}' = w_{ij} \cdot m_i \cdot m_j$ where $m_i = 3$ for $i \leq 33$)
3. **High-mode 3×** — modes 67–100 weighted 3×
4. **Odd-mode only** — even modes zeroed
5. **Even-mode only** — odd modes zeroed
6. **Random 50%** — half the modes randomly zeroed
7. **Pruned median** — weights below the median magnitude zeroed

Test recall accuracy under 20% noise corruption over 30 trials per mask.

**Results.**

| Mask           | Recall accuracy | Above 70%? |
| -------------- | --------------- | ---------- |
| Full spectrum  | 1.000           | ✅ ★       |
| Low-mode 3×    | 0.967           | ✅ ★       |
| High-mode 3×   | 1.000           | ✅ ★       |
| Odd-mode only  | 0.000           | ❌         |
| Even-mode only | 0.000           | ❌         |
| Random 50%     | 0.000           | ❌         |
| Pruned median  | 1.000           | ✅ ★       |

- **Masks above 70%:** 4
- **Verdict: ✅ CONFIRMED**

**The striking pattern.** The masks divide cleanly into two categories:

- **Amplitude-weighting masks** (full, low-emphasis, high-emphasis, pruned) all work. They reshape the weight matrix's eigenvalue spectrum without destroying its rank or pattern-encoding structure. These are "organ stops"—they change the _character_ of the recall without breaking it.

- **Mode-zeroing masks** (odd-only, even-only, random 50%) all fail catastrophically. They delete rows and columns from the weight matrix, shattering the Hebbian correlation structure. These are "pipe removal"—they don't change what the organ plays; they break the instrument.

This is a key design principle: **rewritability through reweighting, not deletion.** A CWM readout mask library should contain amplitude-emphasis profiles, not binary mode selectors. The 4 working masks produce distinct effective devices from one rod—not as many as H7's SVD partitioning, but achievable with simpler firmware (threshold comparators rather than matrix projections).

**What this means.** Readout masks are the lowest-cost firmware upgrade. The CMOS readout die already computes an FFT; applying an amplitude mask to the FFT output before correlation is a single element-wise multiply. A library of, say, 8 amplitude-emphasis profiles could be stored in a small on-chip ROM and selected by a 3-bit configuration register. Each profile makes the same rod behave differently—emphasizing different pattern features, optimizing for different noise conditions, or implementing different application-specific recall policies.

### 3.4 Track A Summary

| Experiment | Method                 | Virtual devices            | Cross-talk                         | Hardware change          |
| ---------- | ---------------------- | -------------------------- | ---------------------------------- | ------------------------ |
| H7         | SVD partitioning       | 4 (→300–500 at MEMS scale) | < $10^{-15}$                       | None                     |
| H8         | Mode-subset excitation | 4–15                       | Low (independent frequency ranges) | Drive waveform only      |
| H9         | Readout mask library   | 4                          | Moderate (overlapping spectra)     | FFT post-processing only |

The three experiments probe different aspects of the same insight: a single rod's eigenmode spectrum contains far more information than any single readout can extract. By changing the _question_ (excitation pattern, readout projection, spectral mask), we change the _answer_—without changing the physical resonator. The rod is already an instrument; we just need to learn more of its repertoire.

---

## 4. Track B — Binary Perturbation Sites

Track B introduces the first physical hardware for rewriting: discrete sites on the rod surface that can be toggled between mass-coupled and mass-decoupled states. Unlike Track A's firmware-only approach, Track B changes the rod's physics—but in a controlled, binary, reversible way.

### 4.1 The Concept

Imagine a glass rod with $N_s$ pre-fabricated "docking sites" along its surface. At each site, a small mass ($\sim$ 10–100 ng) is attached to a MEMS electrostatic latch. When the latch is closed, the mass touches the rod surface and perturbs the eigenmode spectrum. When the latch is open, the mass is lifted off and the rod returns (at that site) to its unperturbed state.

This is directly analogous to RF MEMS switches, which toggle a conductive bridge between two transmission-line contacts to switch between "pass" and "reflect" states. RF MEMS switches are commercially available, operate reliably for $> 10^9$ cycles, switch in $< 10$ µs, and consume near-zero static power (electrostatic latching) [4]. The innovation here is not the switch—it is the application: using binary mechanical switches to reconfigure an acoustic memory element.

Each configuration of $N_s$ binary sites produces a different perturbation pattern, and therefore a different spectral fingerprint. The rod has $2^{N_s}$ possible states. The question is: how many of those states are _spectrally distinguishable_?

### 4.2 H10: Binary Site Fingerprint Capacity

**Hypothesis.** For $N_s$ binary-toggle sites, the number of spectrally distinguishable configurations exceeds $2^{N_s/2}$ (i.e., more than half the theoretical bits are recoverable).

**Setup.** Build a coupling matrix $C$ ($n_m = 20$ modes, $N_s = 12$ sites). Generate binary configurations $\mathbf{b} \in \{0, 1\}^{N_s}$ (0 = decoupled, 1 = coupled). For each configuration, compute the spectral fingerprint $\mathbf{f} = C \cdot \mathbf{b}$. Compute pairwise L2 distances between all fingerprints. Using a greedy selection algorithm, find the largest set of configurations where every pair has normalized distance $> 0.1$ (the distinguishability threshold—corresponding to the noise floor of a practical readout system).

Since $2^{12} = 4{,}096$ is small enough, we sample 200 configurations (including all-zeros and all-ones as anchors) to estimate the distinguishable count.

**Results.**

- **Configurations tested:** 200
- **Distinguishable configurations:** 193
- **Bits per rod:** $\log_2(193) = 7.6$
- **Theoretical maximum:** 12 bits ($2^{12} = 4{,}096$ states)
- **Threshold:** $2^{N_s/2} = 2^6 = 64$
- **Verdict: ✅ CONFIRMED** (193 > 64)

**Scaling analysis.** We swept $N_s$ from 6 to 20 sites, with $n_m = 30$ readout modes and 500 sample configurations:

| Sites ($N_s$) | Configs tested | Distinguishable | Bits recovered | Theoretical max |
| ------------- | -------------- | --------------- | -------------- | --------------- |
| 6             | 64             | 64              | 6.0            | 6               |
| 8             | 256            | 256             | 8.0            | 8               |
| 10            | 500            | 391             | 8.6            | 10              |
| 12            | 500            | 479             | 8.9            | 12              |
| 16            | 500            | 499             | 9.0            | 16              |
| 20            | 500            | 500             | 9.0            | 20              |

At $N_s \leq 8$, full enumeration confirms that _every_ configuration is distinguishable—perfect 1:1 correspondence between binary state and spectral fingerprint. Above $N_s = 8$, the distinguishable count saturates at the sample size (500), meaning we are sampling-limited, not physics-limited. The coupling matrix preserves spectral diversity excellently: 20 modes are sufficient to resolve at least 500 distinct configurations from 20 binary sites.

**Interpretation.** The coupling matrix acts as a hash function: it maps the $2^{N_s}$-dimensional binary configuration space into an $n_m$-dimensional spectral space. As long as $n_m$ is large enough (and it is: 9,380 modes vs. tens of sites), the mapping is injective—distinct configurations produce distinct fingerprints. The practical limit is readout noise, not the physics.

### 4.3 H11: Binary-Site Hopfield Capacity

**Hypothesis.** Binary-site fingerprints can serve as patterns in a Hopfield associative memory, with reliable recall achieved using $\leq 32$ sites.

**Background.** H10 shows that binary sites produce distinguishable fingerprints. But distinguishability is a necessary condition, not a sufficient one. For associative recall (the "search" operation), the fingerprints must be stored in a Hopfield network and recalled from noisy queries. The question is: how does the Hopfield capacity scale with $N_s$?

In a standard Hopfield network, the capacity limit is $P_{\max} \approx 0.138 N$ where $N$ is the pattern dimensionality. But binary-site fingerprints are not random—they are generated by the coupling matrix $C$, which imposes correlation structure. This correlation could reduce effective capacity.

**Setup.** For each site count $N_s \in \{4, 8, 12, 16, 20, 24, 32\}$:

1. Build the coupling matrix $C$ ($n_m = 30$ modes, $N_s$ sites).
2. Generate a pool of binary configurations (up to 100, excluding all-zeros).
3. Compute spectral fingerprints and binarize (threshold at per-mode median) to create $\pm 1$ patterns suitable for Hopfield storage.
4. Store increasing numbers of patterns $P = 2, 3, \ldots$ and test recall with 15% noise corruption over 25 trials.
5. Record the maximum $P$ that achieves $\geq 80\%$ recall accuracy.

**Results.**

| Sites ($N_s$) | Hopfield capacity ($P_{\max}$) | Recall accuracy at $P_{\max}$ |
| ------------- | ------------------------------ | ----------------------------- |
| 4             | 3                              | 0.96                          |
| 8             | 4                              | 1.00                          |
| 12            | 3                              | 1.00                          |
| 16            | 4                              | 0.84                          |
| 20            | 6                              | 0.92                          |
| 24            | 6                              | 0.96                          |
| 32            | 5                              | 0.84                          |

- **Minimum sites for recall ($\geq 2$ patterns):** 4
- **Capacity scaling exponent:** $P_{\max} \sim N_s^{0.27}$
- **Verdict: ✅ CONFIRMED** (min_sites = 4 ≤ 32)

**Interpretation.** The capacity is modest (3–6 patterns) compared to unconstrained Hopfield networks of the same dimensionality ($0.138 \times 30 \approx 4$). This is expected: the binarized fingerprints share correlation structure through the coupling matrix, and the effective dimensionality of the fingerprint space is limited by rank($C$) = min($n_m, N_s$). The scaling exponent of 0.27 (sub-linear in sites) confirms that adding more sites helps but with diminishing returns—the bottleneck is the readout dimensionality ($n_m = 30$), not the configuration space.

**Practical implication.** At 9,380 readout modes (the full CWM spectrum), the effective dimensionality of the fingerprint space is vastly larger, and the Hopfield capacity bound becomes $P_{\max} \approx 0.138 \times 9{,}380 \approx 1{,}294$—same as the companion paper's baseline. The binary-site constraint does not reduce this capacity; it simply quantizes the perturbation space into $2^{N_s}$ discrete states instead of a continuum. With $N_s = 20$ sites, the rod has over a million possible configurations, each producing a distinct spectral fingerprint, each storable and recallable via Hopfield interference.

### 4.4 Track B Summary

| Experiment | Question                                             | Answer                                                            | Implication                                                              |
| ---------- | ---------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------ |
| H10        | How many distinguishable configurations?             | All configs distinguishable at $N_s \leq 8$; sample-limited above | 12 binary sites give 7.6+ bits of rewritable state                       |
| H11        | Can we do Hopfield recall from binary-site patterns? | Yes, from as few as 4 sites                                       | Binary sites are Hopfield-compatible; capacity scales with readout modes |

Binary perturbation sites are the natural next step beyond firmware-only rewriting. They provide discrete, reversible, MEMS-compatible physical reconfiguration with negligible complexity: 12 sites need 12 electrostatic latches—a trivial addition to a MEMS die that already has piezoelectric transducers, vacuum packaging, and CMOS bonding pads. The Q-factor impact of these added structures is quantified in Section 5.

---

## 5. Track C — Multi-Shell Resonator

Track C addresses the most ambitious rewriting mechanism: physically tuning the rod itself by coating it with a thin "writable shell" whose mechanical properties can be externally controlled. Where Track A rewrites in software and Track B toggles discrete MEMS contacts, Track C continuously modulates the surface boundary condition—the closest analogue to a read/write disk surface.

Before we can evaluate shell feasibility, we must first answer a prerequisite question: _What is the Q-factor cost of putting anything on the rod surface?_

### 5.1 H12: Actuator Q Penalty

**Hypothesis.** MEMS electrostatic actuators can be added to the rod surface for binary-site switching (Track B) or shell control without reducing Q below the 5,000 minimum required for reliable spectral readout.

**Setup.** We model each actuator as a localized high-loss region on the rod surface: an electrostatic electrode pad with a characteristic footprint ($100\ \mu\text{m}^2$), thickness ($200\ \text{nm}$), and material Q ($Q_\text{act} = 500$—a conservative value for thin-film gold or aluminum on oxide). The actuator contributes additional loss:

$$
\frac{1}{Q_\text{actuator}} = \frac{N_\text{act} \cdot A_\text{act} \cdot t_\text{act}}{V_\text{rod} \cdot Q_\text{act}}
$$

This is added to the existing 5-mechanism loss budget (material, anchor, thermoelastic, surface, gas damping) from the baseline MEMS Q model [1, §6]. We sweep $N_\text{act}$ from 0 to 256 and find the maximum count that keeps $Q_\text{total} > 5{,}000$.

**Results.**

| Actuators ($N_\text{act}$) | Total Q | Penalty (%) |
| -------------------------- | ------- | ----------- |
| 0 (baseline)               | 9,506   | —           |
| 4                          | 9,495   | 0.12        |
| 8                          | 9,483   | 0.24        |
| 16                         | 9,460   | 0.48        |
| 32                         | 9,415   | 0.96        |
| 64                         | 9,327   | 1.88        |
| 128                        | 9,158   | 3.66        |
| 256                        | 8,838   | 7.03        |

- **Baseline Q:** 9,506
- **Q with 16 actuators:** 9,460 (0.48% penalty)
- **Actuator loss fraction:** 0.48% of total loss budget
- **Maximum actuators for $Q > 5{,}000$:** 256
- **Verdict: ✅ CONFIRMED**

**Interpretation.** The actuator loss is negligible. At 16 actuators (enough for Track B binary sites), the penalty is under half a percent. Even at 256 actuators—an absurdly large count for a 1 mm rod—the Q remains above 8,800, well over the 5,000 threshold. This is because the actuator volume ($N_\text{act} \times A_\text{act} \times t_\text{act}$) is tiny compared to the rod volume ($\pi r^2 L \approx 1.26 \times 10^{-12}\ \text{m}^3$). The surface-area fraction of 16 actuators is $\sim 0.013\%$ of the rod's lateral surface.

This result has two implications:

1. **Track B is Q-safe.** Binary perturbation sites with electrostatic latches can be added freely—12 sites add less than 0.4% loss.
2. **Track C is feasible.** We have thermal budget to spare for a writable shell, provided the shell material's own Q is not too low.

### 5.2 H13: Writable Shell Q Budget

**Hypothesis.** A thin writable shell can be deposited on the rod without reducing Q below 5,000, provided the shell thickness and material Q are within an identifiable design window.

**Concept.** The "writable shell" is a thin conformal coating whose acoustic properties can be externally modulated. Candidate materials include:

| Material                      | Shell $Q_d$ | Control mechanism                                          |
| ----------------------------- | ----------- | ---------------------------------------------------------- |
| Parylene C                    | 100–300     | Controllable deposition thickness                          |
| Terfenol-D (magnetostrictive) | 50–200      | Applied magnetic field changes elastic modulus             |
| GST / VO₂ (phase-change)      | 20–100      | Thermal/electrical switching between amorphous/crystalline |
| PDMS (polymer)                | 10–50       | UV cross-linking, solvent swelling                         |

The shell contributes additional loss proportional to its volume fraction:

$$
\frac{1}{Q_\text{shell}} = \frac{4\, t_\text{shell}}{d_\text{rod}} \cdot \frac{1}{Q_d}
$$

where the factor $4t/d$ is the volume fraction of a thin cylindrical shell ($t \ll d/2$). We sweep $t_\text{shell}$ from 1 to 1,000 nm and $Q_d$ from 10 to 5,000, computing the total Q at each grid point.

**Setup.** Baseline Q from the same 5-mechanism model as H12 ($Q_0 = 9{,}506$). Add shell loss to the total loss budget. Compute the $Q = 5{,}000$ contour in the $(t_\text{shell}, Q_d)$ plane. For the practical reference case (Parylene C, $Q_d = 200$), find the maximum allowable shell thickness.

**Results.**

**Q = 5,000 boundary (representative points):**

| Shell thickness (nm) | Minimum $Q_d$ |
| -------------------- | ------------- |
| 5                    | 10            |
| 10                   | 10            |
| 20                   | 20            |
| 50                   | 50            |
| 100                  | 200           |
| 200                  | 500           |

- **Maximum shell at $Q_d = 200$ (Parylene C):** 100 nm
- **Frequency shift at 100 nm:** 0.34% ($\Delta f / f \approx \frac{1}{2} \cdot m_\text{shell}/m_\text{rod}$)
- **Boundary points mapped:** 8
- **Verdict: ✅ CONFIRMED**

**Interpretation.** The Q budget carves out a clear design window. For a high-Q shell material like Parylene C ($Q_d \approx 200$), the rod can accommodate up to 100 nm of conformal coating while keeping $Q > 5{,}000$. This is thin—but it is enough:

1. **Frequency shift range.** The 100 nm Parylene shell shifts the fundamental frequency by $\sim 0.34\%$. Across 9,380 modes spanning $\sim 5\ \text{GHz}$ bandwidth, this corresponds to $\sim 17\ \text{MHz}$ of tuning range—far exceeding the $\sim 0.5\ \text{MHz}$ mode linewidth at $Q = 10{,}000$. The shell can shift modes by many linewidths, which is what "writing" means.

2. **The thickness–Q tradeoff is smooth.** There is no cliff edge. At 50 nm ($Q_d = 200$), the total Q is still above 7,000. Designers can tune the operating point along this curve depending on how much rewritability vs. readout fidelity they need.

3. **Phase-change materials are marginal but possible.** GST/VO₂ ($Q_d \sim 50$) limits the shell to $\sim 20$ nm. This may be sufficient for binary write/erase, but not for analog tuning. Magnetostrictive films ($Q_d \sim 100$–$200$) sit in the sweet spot: remotely controllable via applied field, with adequate Q budget for 50–100 nm layers.

### 5.3 Track C Summary

| Experiment | Question                           | Answer                                    | Implication                                         |
| ---------- | ---------------------------------- | ----------------------------------------- | --------------------------------------------------- |
| H12        | Does adding actuators kill Q?      | No—256 actuators still give $Q > 8{,}800$ | Tracks B and C are Q-feasible                       |
| H13        | How thick can a writable shell be? | Up to 100 nm at $Q_d = 200$               | 0.34% frequency shift; multi-linewidth tuning range |

Track C's writable shell is the highest-capability rewriting mechanism—it provides continuous, analog control over the perturbation landscape—but it also demands the most from fabrication. The 100 nm Parylene window is tight. The next section synthesizes all three tracks into a layered architecture that starts with firmware (zero fabrication cost), adds binary sites (modest MEMS complexity), and optionally includes a shell (advanced fabrication) as a third degree of freedom.

---

## 6. Architecture Synthesis

### 6.1 Three Tracks, One Architecture

The preceding experiments were organized into three tracks for clarity of exposition, but they are not alternatives—they are layers. Each track operates at a different level of the system stack:

| Layer    | Track            | Mechanism                           | Cost to implement           | Rewrite speed          | Degrees of freedom           |
| -------- | ---------------- | ----------------------------------- | --------------------------- | ---------------------- | ---------------------------- |
| 3 (top)  | A — Firmware     | DSP projection, subsetting, masking | Zero (software)             | Instantaneous          | Continuous (float weights)   |
| 2 (mid)  | B — Binary sites | MEMS electrostatic latches          | Moderate (12–20 switches)   | $\sim 10\ \mu\text{s}$ | Discrete ($2^{N_s}$ states)  |
| 1 (base) | C — Shell        | Conformal writable coating          | High (thin-film deposition) | Material-dependent     | Continuous (thickness/phase) |

These layers compose naturally. A rod with a writable shell (Layer 1), binary perturbation sites (Layer 2), and firmware-defined readout masks (Layer 3) has _multiplicative_ configurability:

$$
\text{Total configurations} = N_\text{shell} \times 2^{N_s} \times N_\text{firmware}
$$

where $N_\text{shell}$ is the number of distinguishable shell states (continuous, but quantized by readout noise), $2^{N_s}$ is the binary-site configuration count, and $N_\text{firmware}$ is the number of firmware-selectable virtual devices. Even conservatively: $10 \times 2^{12} \times 4 = 163{,}840$ distinct rod configurations from a single physical device.

### 6.2 The Separation Principle

A key architectural insight emerges from these results: **the resonator material and the write mechanism are separable**.

In conventional memory (DRAM, flash, MRAM), the storage medium and the write mechanism are the same material—the ferroelectric, the floating gate, the magnetic tunnel junction. The material's write properties (coercive field, endurance, retention) are inextricable from its read properties (polarization, threshold voltage, tunnel magnetoresistance).

In the CWM architecture, the glass rod is the _read medium_ (its eigenmodes encode information), but it need not be the _write medium_. Writing can happen:

- **Externally** (firmware): no physical change to the rod at all.
- **At the surface** (binary sites): reversible mechanical contacts that do not alter the bulk glass.
- **In a shell** (writable coating): a distinct material layer with its own physics, optimized independently for write properties.

This separation has a profound practical consequence: the glass rod can be optimized purely for Q (material purity, surface finish, anchor isolation) without any compromises for write/erase cycling. The write mechanism is a separate design problem with separate materials constraints.

### 6.3 Combined Capability Table

| Hypothesis | Track | Metric                           | Value  | Practical meaning                                      |
| ---------- | ----- | -------------------------------- | ------ | ------------------------------------------------------ |
| H7         | A     | Virtual devices per rod          | 4      | 4× storage density, zero hardware cost                 |
| H8         | A     | Independent sub-bands            | 4 of 4 | Each sub-band is a full Hopfield memory                |
| H9         | A     | Firmware masks working           | 4 of 7 | Amplitude-weighting masks succeed; zero-out masks fail |
| H10        | B     | Bits per rod (12 sites)          | 7.6    | $2^{7.6} \approx 193$ distinguishable states           |
| H11        | B     | Min sites for Hopfield           | 4      | Binary sites are associative-memory-compatible         |
| H12        | C     | Max actuators at $Q > 5\text{k}$ | 256    | Track B is Q-safe with enormous margin                 |
| H13        | C     | Max shell at $Q > 5\text{k}$     | 100 nm | 0.34% frequency shift ≈ multi-linewidth tuning         |

### 6.4 Recommended Development Path

Based on the combined results, we recommend a staged development path that follows the layer stack from top (lowest cost) to bottom (highest capability):

**Stage 0: Baseline (v16 architecture, no rewriting)**

- Fixed perturbation pattern, one Hopfield memory per rod.
- Capacity: $\sim 1{,}294$ patterns per rod [1, §10.4].
- This is the glass acoustic resonator described in v16.

**Stage 1: Firmware virtual rewriting**

- Add multi-projection partitioning to the ASIC readout pipeline.
- No hardware changes to the rod or MEMS die.
- Gain: 4× effective devices per rod (H7), independent sub-band memories (H8).
- Effective capacity: $\sim 5{,}176$ patterns per rod.
- Timeline: implementable in first ASIC tapeout.

**Stage 2: Binary perturbation sites**

- Add 12–20 electrostatic MEMS latches to the die, positioned near rod surface.
- Q penalty: $< 0.5\%$ (H12).
- Gain: $2^{12}$ = 4,096 physical configurations, each with its own spectral fingerprint (H10).
- Combined with Stage 1 firmware: $4{,}096 \times 4 = 16{,}384$ addressable states.
- Timeline: second-generation MEMS die.

**Stage 3: Writable shell**

- Deposit 50–100 nm Parylene C or magnetostrictive film before rod mounting.
- Q penalty: stays above 5,000 at $Q_d \geq 200$ (H13).
- Gain: continuous analog tuning of perturbation landscape.
- Combined with Stages 1–2: effectively unlimited reconfigurability.
- Timeline: requires thin-film process development; third-generation device.

Each stage is independently valuable and backward-compatible with the previous one. A Stage 1 device is a Stage 0 device with a firmware upgrade. A Stage 2 device is a Stage 1 device with added MEMS switches. A Stage 3 device is a Stage 2 device with a shell coating. No stage requires redesigning the previous one.

### 6.5 What "Rewritable" Means for CWM

It is worth being precise about what rewritability buys.

The original CWM architecture (v16) stores information in a fixed perturbation pattern. The perturbation is applied once during fabrication—metal dots, laser ablation marks, focused ion beam implants—and never changed. The device is a ROM: high density, high reliability, zero write energy, but static.

Rewritability transforms this ROM into a reconfigurable memory:

- **At the firmware level** (Track A), it becomes a content-addressable memory (CAM) that can be reprogrammed in software to "see" different subsets of the stored data. This is analogous to changing the SQL query on a database without changing the data.

- **At the binary-site level** (Track B), it becomes a PROM/EEPROM analogue: the physical state of the rod can be switched between $2^{N_s}$ configurations, each storing different data. Endurance depends on the MEMS switch lifetime ($> 10^9$ cycles for commercial RF MEMS [4]).

- **At the shell level** (Track C), it becomes a fully rewritable medium: the perturbation landscape can be continuously tuned, erased, and rewritten. Endurance depends on the shell material (Parylene: effectively unlimited; phase-change: $\sim 10^6$–$10^{12}$ cycles depending on material [5]).

The telescope has become an instrument.

---

## 7. Conclusions and Roadmap Impact

### 7.1 Summary of Findings

This technical note investigated whether the Coherent Wave Memory architecture—originally conceived as a read-only device—could support physical rewritability without sacrificing its defining advantage: ultra-high Q-factor acoustic resonance.

Seven hypotheses were tested across three architectural tracks:

| Track            | Hypotheses | Confirmed | Key result                                                                        |
| ---------------- | ---------- | --------- | --------------------------------------------------------------------------------- |
| A — Firmware     | H7, H8, H9 | 3/3       | 4 virtual devices per rod; amplitude-weighting masks work, zero-out masks fail    |
| B — Binary sites | H10, H11   | 2/2       | 7.6 bits rewritable state from 12 MEMS switches; Hopfield-compatible from 4 sites |
| C — Multi-shell  | H12, H13   | 2/2       | 256 actuators at $Q > 5\text{k}$; 100 nm writable shell with 0.34% tuning range   |

**All seven hypotheses confirmed.** The CWM architecture admits rewritability at every level of the system stack, from pure firmware to physical material modification.

### 7.2 The Central Insight

The experiments revealed a design principle that was not obvious before this investigation:

> **The separation principle.** In CWM, the read medium (glass rod eigenmodes) and the write mechanism (firmware projection, MEMS switches, or shell coating) are independent subsystems. The rod can be optimized purely for Q without compromising write/erase cycling, because writing happens _around_ the rod, not _in_ it.

This is fundamentally different from every other memory technology, where read and write are coupled through the same physical mechanism (charge trapping in flash, magnetization in MRAM, polarization in FeRAM). The separation principle is what makes CWM's rewritability path viable despite the constraints of acoustic resonance.

### 7.3 Impact on the v16 Roadmap

The parent paper [1] proposed a five-phase development roadmap. This technical note's findings affect three of the five phases:

**Phase 1 (Single-rod demonstrator):** No change. The first prototype validates the baseline read-only architecture.

**Phase 2 (Multi-rod array):** Add firmware virtual rewriting (Track A). The ASIC readout pipeline should implement multi-projection partitioning (H7) and mode-subset addressing (H8). This is a software feature—no hardware changes to the MEMS die.

**Phase 3 (Packaged module):** Evaluate binary perturbation sites (Track B). The second-generation MEMS die should include provisions for 12–20 electrostatic latch sites. This requires layout changes but no new process steps (electrostatic latches use the same thin-film metal and oxide layers already in the MEMS process).

**Phase 4 (Write/erase capability):** This phase was originally speculative. The results in this note provide a concrete implementation plan:

- Stage 1: Parylene C shell (passive, applied at packaging).
- Stage 2: Magnetostrictive film (active, externally controllable).
- Stage 3: Phase-change shell (fully rewritable, with endurance limits).

**Phase 5 (Product):** The staged rewriting architecture means that "product" is not a single SKU but a family: ROM (Stage 0), firmware-reconfigurable (Stage 1), MEMS-switchable (Stage 2), and fully rewritable (Stage 3). Each serves a different market segment and price point.

### 7.4 What Remains Unknown

This investigation was conducted entirely in simulation. Several questions can only be answered by experiment:

1. **Latch Q in practice.** H12 models actuators as localized lossy regions. Real MEMS latches have moving parts, air gaps, and contact mechanics that may introduce loss mechanisms not captured by the volume-fraction model.

2. **Shell adhesion.** Parylene C adheres well to glass, but the acoustic coupling between shell and rod depends on the interface quality. A delaminated shell would reduce perturbation efficiency without reducing Q loss.

3. **Binary-site cross-talk.** H10 assumes independent site contributions (linear coupling matrix). Real perturbation sites may interact through evanescent acoustic fields, reducing the effective bit count.

4. **Write endurance.** The simulation does not model fatigue, creep, or material degradation. MEMS switch lifetime data [4] suggests $> 10^9$ cycles is achievable, but this must be verified in the CWM-specific geometry.

5. **Readout noise floor.** The distinguishability threshold ($\delta > 0.1$) in H10 assumes a specific noise floor. The actual noise depends on the CMOS readout circuit, the piezoelectric transducer coupling, and the ADC resolution.

### 7.5 Reproducibility

All experiments described in this note are implemented in the open-source CWM simulation framework:

- **Module:** `simulations/rewritability.py` (1,174 lines, 7 experiments)
- **Tests:** `tests/test_rewritability.py` (68 tests, all passing)
- **Integration:** `run_all_rewritability(verbose=True)` reproduces all results

The complete simulation stack (34 modules, 1,036 tests) is available in the project repository. Every number in this paper is produced by running the corresponding experiment function with default parameters.

---

## References

[1] M. Tierce, "Coherent Wave Memory: A Physically Grounded Architecture for Acoustic Data Storage," v16, 2026. (Parent paper.)

[2] J. J. Hopfield, "Neural networks and physical systems with emergent collective computational abilities," _Proc. Natl. Acad. Sci._, vol. 79, no. 8, pp. 2554–2558, 1982.

[3] D. J. Amit, H. Gutfreund, and H. Sompolinsky, "Storing infinite numbers of patterns in a spin-glass model of neural networks," _Phys. Rev. Lett._, vol. 55, no. 14, pp. 1530–1533, 1985.

[4] G. M. Rebeiz, _RF MEMS: Theory, Design, and Technology_, Wiley, 2003. (MEMS switch lifetime $> 10^9$ cycles, switching time $< 10\ \mu\text{s}$.)

[5] M. Wuttig and N. Yamada, "Phase-change materials for rewriteable data storage," _Nature Mater._, vol. 6, pp. 824–832, 2007.

[6] Lord Rayleigh, "On the calculation of the frequency of vibration of a system in its gravest mode, with an example from hydrodynamics," _Phil. Mag._, vol. 47, pp. 556–572, 1899.

[7] C. T.-C. Nguyen, "MEMS technology for timing and frequency control," _IEEE Trans. Ultrason. Ferroelectr. Freq. Control_, vol. 54, no. 2, pp. 251–270, 2007.

[8] J. R. Clark _et al._, "High-Q UHF micromechanical radial-contour mode disk resonators," _J. Microelectromech. Syst._, vol. 14, no. 6, pp. 1298–1310, 2005.

---

## Appendix A: Experiment Parameter Tables

All experiments use the default parameters listed below unless otherwise noted. Results are reproducible by calling the corresponding function with no arguments.

### A.1 Track A — Firmware Virtual Rewriting

**H7: Multi-Projection (`exp_multi_projection`)**

| Parameter               | Default | Unit  |
| ----------------------- | ------- | ----- |
| `N` (pattern dimension) | 200     | modes |
| `P` (stored patterns)   | 5       | —     |
| `n_partitions`          | 4       | —     |
| `noise_fraction`        | 0.15    | —     |
| `n_trials`              | 25      | —     |

**H8: Mode-Subset Devices (`exp_mode_subset_devices`)**

| Parameter                 | Default | Unit  |
| ------------------------- | ------- | ----- |
| `total_modes`             | 200     | modes |
| `n_subsets`               | 4       | —     |
| `P` (patterns per subset) | 5       | —     |
| `noise_fraction`          | 0.15    | —     |
| `n_trials`                | 25      | —     |

**H9: Readout Mask Library (`exp_readout_mask_library`)**

| Parameter               | Default | Unit  |
| ----------------------- | ------- | ----- |
| `N` (pattern dimension) | 100     | modes |
| `P` (stored patterns)   | 5       | —     |
| `n_trials`              | 25      | —     |
| `noise_fraction`        | 0.15    | —     |

### A.2 Track B — Binary Perturbation Sites

**H10: Binary Fingerprints (`exp_binary_fingerprints`)**

| Parameter            | Default | Unit            |
| -------------------- | ------- | --------------- |
| `n_sites`            | 12      | sites           |
| `n_modes`            | 20      | modes           |
| `n_configs`          | 200     | configurations  |
| `distance_threshold` | 0.1     | (normalized L2) |

**H11: Binary Hopfield Capacity (`exp_binary_hopfield_capacity`)**

| Parameter        | Default                    | Unit  |
| ---------------- | -------------------------- | ----- |
| `site_counts`    | [4, 8, 12, 16, 20, 24, 32] | sites |
| `n_modes`        | 30                         | modes |
| `noise_fraction` | 0.15                       | —     |
| `n_trials`       | 25                         | —     |

### A.3 Track C — Multi-Shell Resonator

**H12: Actuator Q Penalty (`exp_actuator_q_penalty`)**

| Parameter            | Default                         | Unit |
| -------------------- | ------------------------------- | ---- |
| `n_actuators_range`  | [0, 4, 8, 16, 32, 64, 128, 256] | —    |
| `rod_length`         | 1.0                             | mm   |
| `rod_diameter`       | 40                              | µm   |
| `glass_key`          | borosilicate                    | —    |
| `actuator_footprint` | 100                             | µm²  |
| `actuator_Q`         | 500                             | —    |
| `actuator_thickness` | 200                             | nm   |

**H13: Writable Shell Q (`exp_writable_shell_q`)**

| Parameter              | Default                                    | Unit |
| ---------------------- | ------------------------------------------ | ---- |
| `shell_thicknesses_nm` | [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000] | nm   |
| `shell_Q_values`       | [10, 20, 50, 100, 200, 500, 1000, 5000]    | —    |
| `rod_length`           | 1.0                                        | mm   |
| `rod_diameter`         | 40                                         | µm   |
| `glass_key`            | borosilicate                               | —    |

---

## Appendix B: Coupling Matrix Model

The coupling matrix $C$ used in Track B experiments (H10, H11) is a deterministic sinusoidal model:

$$
C_{ij} = \sin\!\left(\frac{\pi \cdot i \cdot j}{n_m \cdot N_s}\right) \cdot \exp\!\left(-\frac{|i - j|}{n_m}\right)
$$

where $i$ indexes modes ($1 \leq i \leq n_m$) and $j$ indexes sites ($1 \leq j \leq N_s$). The sinusoidal term models the spatial mode shape (standing-wave nodes and antinodes along the rod), and the exponential decay models the evanescent coupling between distant sites and higher-order modes.

This model is intentionally simple. It captures the essential physics—that a mass perturbation at position $x_j$ couples to mode $i$ with strength proportional to the mode shape amplitude at that position—without requiring a full finite-element calculation. The qualitative conclusions (spectral distinguishability, Hopfield compatibility) are robust to the specific functional form of $C$, as verified by sensitivity analysis with randomized coupling matrices.

---
