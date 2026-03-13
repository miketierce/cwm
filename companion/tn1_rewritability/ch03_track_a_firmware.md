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
