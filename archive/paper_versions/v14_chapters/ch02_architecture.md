---

## 2. Architecture

### 2.1 Eigenmode Encoding

The fundamental question for any memory technology is: how many independent bits can you store in a given physical volume? For CWM, the answer depends on two quantities: how many independent modes the resonator supports, and how much information each mode can carry.

**Mode count.** A glass rod of length $L$ supports longitudinal eigenmodes at frequencies $f_n = nv/(2L)$, where $v$ is the speed of sound and $n = 1, 2, 3, \ldots$ Not all of these modes are usable. The rod also expands and contracts thermally, and this thermal expansion shifts eigenfrequencies. If the thermal frequency shift of a mode exceeds the spacing between adjacent modes, those modes blur together and cannot be independently resolved.

The thermal frequency shift for mode $n$ is $\Delta f_n^{\text{thermal}} = f_n \cdot \alpha \cdot \Delta T$, where $\alpha$ is the coefficient of thermal expansion and $\Delta T$ is the temperature range. The spacing between adjacent modes is constant: $\Delta f = v/(2L)$. Requiring the thermal shift to be less than the mode spacing gives:

$$f_n \cdot \alpha \cdot \Delta T < \frac{v}{2L} \quad \Longrightarrow \quad n < \frac{1}{2\alpha \,\Delta T}$$

The maximum number of thermally stable modes is therefore:

$$n_{\max} = \left\lfloor \frac{1}{2\alpha \,\Delta T} \right\rfloor$$

Notice what is _not_ in this formula: the rod length $L$. The mode count depends only on the material's thermal expansion coefficient and the operating temperature range. A 150 mm rod and a 1 mm rod made of the same glass, operating at the same temperature stability, support the same number of modes. For borosilicate glass ($\alpha = 3.3 \times 10^{-6}$/K) at $\pm 1$ K: $n_{\max} = \lfloor 1/(2 \times 3.3 \times 10^{-6} \times 1) \rfloor = 9{,}380$ modes. This number will reappear throughout the paper—it is the bedrock on which all capacity projections rest.

**Bits per mode.** Each mode is an independent oscillator whose amplitude can be measured with a signal-to-noise ratio determined by the thermal noise floor. Shannon's channel capacity theorem [6] tells us the maximum information per measurement:

$$b = \frac{1}{2}\log_2(1 + \text{SNR})$$

At the measured SNR of 98.8 dB (which corresponds to a linear ratio of $7.6 \times 10^9$): $b = 16.4$ bits per mode. This is a hard upper bound set by thermodynamics—no amount of clever signal processing can extract more information from a single mode measurement at this noise level.

**Total capacity per rod.** With 9,380 modes at 16.4 bits each: $9{,}380 \times 16.4 = 153{,}832$ bits, or about 19 kilobytes per rod. At MEMS scale (1 mm rod, reduced SNR of 47 dB giving 7.8 bits/mode): $9{,}380 \times 7.8 = 73{,}164$ bits, or about 9 kilobytes per rod. These are modest numbers for a single rod—the power of CWM comes from dense arrays and from the fact that every rod simultaneously stores _and_ computes.

<div class="cwm-thumb">
<img src="figures/fig3_eigenmode_encoding.svg" alt="Figure 3: Eigenmode encoding and perturbation effect"/>
<p><strong>Figure 3.</strong> Standing-wave mode shapes (left) and perturbation-induced frequency shifts that create unique spectral fingerprints (right).</p>
</div>

### 2.2 Perturbation Encoding (Write)

Writing data to a CWM rod means creating a spatial pattern of mass perturbations on its surface. Each perturbation pattern produces a unique spectral fingerprint—a set of frequency shifts across all modes—via the Rayleigh perturbation formula (Section 1.2).

The physics of why this works is worth dwelling on. Consider a rod vibrating in mode $n = 3$. This mode has three half-wavelengths along the rod's length: three antinodes (points of maximum displacement) and two internal nodes (points of zero displacement). Now place a small mass at the position of the second antinode. This mass must be accelerated back and forth as the rod vibrates, which requires extra force and therefore _lowers_ the resonant frequency of mode 3. But the same mass, placed at the same position, sits near a _node_ of mode 2 (which has only two half-wavelengths). Mode 2 barely moves at that position, so the mass barely affects mode 2's frequency.

This position-dependent sensitivity is the key to information encoding. A mass at position $x_1$ creates one pattern of shifts $\{\Delta f_1, \Delta f_2, \ldots\}$. A mass at position $x_2$ creates a different pattern. Two masses at $x_1$ and $x_2$ create yet another pattern (the shifts superpose linearly for small perturbations). The space of possible perturbation patterns—and therefore the space of possible spectral fingerprints—is vast.

At MEMS scale, perturbations are lithographic: thin-film metal dots (typically gold, ~50 nm thick) deposited at precise positions during fabrication, or laser-trimmed post-fabrication. The perturbation pattern is fixed at manufacture, making CWM a form of read-only memory (ROM)—but a ROM where every stored word participates in associative computation.

The energy required to write one mode—meaning, to bring it to a measurable amplitude—is set by the thermal noise floor:

$$E_{\text{write}} = k_B T \cdot \text{SNR}$$

At 300 K and 98.8 dB SNR: $E_{\text{write}} = 4.14 \times 10^{-21} \times 7.6 \times 10^9 = 31.4$ fJ per mode, or $31.4 / 16.4 \approx 1.9$ fJ/bit. For comparison, DRAM write energy is ~3 pJ/bit—over 1,500× higher.

### 2.3 Interference Recall (Read / Compute)

The read and compute operations in CWM are the same physical process: wave interference. This unification—storage and computation in a single physical act—is what distinguishes CWM from in-memory computing approaches that still separate the storage medium from the compute mechanism.

**Simple read.** To read a single rod's stored data, drive it with a broadband pulse (a chirp sweeping through the mode frequency range, or a short impulse containing all frequencies). The rod rings at its eigenfrequencies. A piezoelectric transducer picks up the vibration; an FFT extracts the frequency spectrum; the set of peak positions and amplitudes is the stored fingerprint. This is a conventional spectral measurement, identical in principle to how a quartz crystal microbalance [8] measures mass loading.

**Associative recall.** The more powerful operation is parallel search. Given an array of $M$ rods, each storing a different perturbation pattern, and a query pattern we wish to match:

1. Encode the query as a spectral signature: a set of frequency components $\{Q_1, Q_2, \ldots, Q_N\}$.
2. Drive _all_ rods simultaneously with this signature.
3. Each rod responds with amplitude proportional to the inner product of its stored pattern and the query:

$$R_j = \sum_{n=1}^{N} A_n^{(j)} Q_n$$

4. The rod with the largest $|R_j|$ is the best match.

This is a matched filter implemented in acoustic hardware. The rod is the filter; the query is the input signal; the response amplitude is the match score. The entire $M$-rod search completes in one acoustic propagation cycle—the time it takes sound to traverse the rod, typically 1–5 µs. The computation time is independent of the number of rods, because they all respond simultaneously.

Mathematically, this is a Hopfield associative memory [9]. The "weight matrix" is not programmed into a crossbar—it _is_ the physics of each rod's eigenmode spectrum. The Amit–Gutfreund–Sompolinsky capacity limit [10] gives the maximum number of patterns that can be reliably recalled (at $< 1\%$ bit-error rate) from a single rod:

$$P_{\max} \approx 0.138\,N$$

For $N = 9{,}380$ modes: $P_{\max} \approx 0.138 \times 9{,}380 \approx 1{,}294$ patterns per rod. (The more conservative Hopfield bound $P_{\max} \approx N/(2\ln N) \approx 512$ assumes zero error tolerance; the AGS bound allows a small error floor correctable by the synaptic pruning of Section 10.1.)

<div class="cwm-thumb">
<img src="figures/fig1_architecture.svg" alt="Figure 1: CWM architecture overview"/>
<p><strong>Figure 1.</strong> CWM architecture: eigenmode encoding (left), spectral fingerprinting (center), and array-wide associative recall via wave interference (right).</p>
</div>

### 2.4 Architecture Summary

| Function | Mechanism                           | Analogue                             |
| -------- | ----------------------------------- | ------------------------------------ |
| Write    | Mass perturbation → frequency shift | ROM programming                      |
| Read     | Broadband excitation → FFT          | Addressed read                       |
| Search   | Drive with query → max responder    | Content-addressable memory           |
| Compute  | Wave superposition                  | Dot-product / matched filter         |
| Store    | Eigenmode spectrum                  | Non-volatile (geometric, not charge) |
