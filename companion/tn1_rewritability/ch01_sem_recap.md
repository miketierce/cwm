## 1. SEM Architecture in Brief

_This section summarizes the Spectral Eigenmode Memory architecture established in the companion paper [1]. Readers familiar with [1] may skip to Section 2._

### 1.1 Core Idea

SEM stores data in the _acoustic eigenmode spectrum_ of a solid glass resonator. A glass rod vibrates at a set of natural frequencies—its eigenmodes—each an independent information channel. Mass perturbations on the rod's surface shift each eigenfrequency by a different amount (via the Rayleigh perturbation formula), creating a unique _spectral fingerprint_. To read, excite the rod with a broadband pulse and measure the frequency spectrum. To search an array of rods, drive them all with a query spectrum: the rod whose stored fingerprint best matches the query resonates most strongly—a nearest-neighbor search executed by wave physics in one acoustic propagation cycle (~3.6 µs), with no processor, no memory bus, and no software.

The $n$-th longitudinal eigenmode has frequency $f_n = nv/(2L)$, where $v$ is the speed of sound and $L$ is the rod length. The maximum number of thermally stable modes depends only on the material and temperature stability:

$$n_{\max} = \left\lfloor \frac{1}{2\alpha \,\Delta T} \right\rfloor$$

For borosilicate glass ($\alpha = 3.3 \times 10^{-6}$/K) at $\pm 1$ K: $n_{\max} = 9{,}380$ modes. This number is independent of rod length—a 150 mm prototype rod and a 1 mm MEMS rod support the same mode count.

### 1.2 Key Numbers

The companion paper validates the following from first-principles simulation (33 modules, 959 automated tests):

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

SEM's read/search operation is mathematically a Hopfield associative memory [2, 3]. The weight matrix is the physics of the eigenmode spectrum. The capacity limit is:

$$P_{\max} \approx 0.138\,N$$

for $< 1\%$ bit-error rate, where $N$ is the number of modes. For $N = 9{,}380$: $P_{\max} \approx 1{,}294$ patterns per rod. The companion paper further showed that synaptic pruning (zeroing weak weights) improves recall accuracy by +10.7% at high load factors [1, §10.1], and that null-space multiplexing adds +60% bonus capacity with zero hardware changes [1, §10.4].

### 1.5 The Missing Piece

As presented in the companion paper, SEM is read-only memory: perturbation patterns are fixed at fabrication by lithographic mass deposition. The rod is a "sonic telescope"—factory-pointed at a target and forever locked on. This is sufficient for applications like content-addressable memory, acoustic fingerprint matching, and edge inference, where the stored patterns are fixed at manufacturing time.

But many applications require reconfigurability. A fraud detection system needs new patterns as new attack vectors emerge. A signals-intelligence matcher needs to update its library as threats evolve. Even the simplest embedded device needs occasional firmware updates.

The question this technical note addresses is: _can the telescope become an instrument?_ Can we make SEM reconfigurable without destroying the physics that makes it work?

---
