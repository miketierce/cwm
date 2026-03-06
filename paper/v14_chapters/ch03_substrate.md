---

## 3. Substrate Selection

### 3.1 Ferrofluid: A Dead End Worth Explaining

Our first choice of substrate was ferrofluid—a colloidal suspension of magnetite (Fe₃O₄) nanoparticles, typically 10 nm in diameter, coated with a surfactant and suspended in a carrier oil. Ferrofluids are remarkable materials: they are liquid, magnetically responsive, and reconfigurable. Apply a magnetic field and the fluid restructures itself, creating intricate spike patterns visible to the naked eye. The appeal for SEM was obvious—a reconfigurable acoustic medium would enable read-_write_ memory, not just ROM. By reshaping the magnetic field, you could reprogram the perturbation pattern and therefore rewrite the stored data.

We built a detailed coupled-physics simulation of ferrofluid acoustics, modeling both the magnetization dynamics (Langevin alignment of nanoparticle magnetic moments in an applied field) and the acoustic propagation (pressure waves in the colloidal suspension). The simulation revealed a fatal problem.

**The problem is Brownian rotation.** Each magnetite nanoparticle is ~10 nm across and suspended in a liquid carrier. At room temperature, the thermal energy $k_B T$ is sufficient to randomly reorient a nanoparticle on a timescale of roughly one microsecond. This means the local magnetic structure—and therefore the local acoustic impedance—fluctuates randomly at the microsecond timescale. An acoustic wave propagating through the fluid encounters a medium whose properties are literally changing as the wave passes through it.

Our simulation quantified this: **77.5% phase diffusion per microsecond**. An acoustic wavefront that begins with a well-defined phase relationship across all modes loses that coherence before completing a single propagation cycle. The eigenmode spectrum—the foundation of SEM's information encoding—dissolves into thermal noise before you can measure it.

This is not an engineering problem that can be solved with better magnetic field design or lower temperature. It is a fundamental property of the colloidal phase: the nanoparticles are small enough to be in the Brownian regime, and no external field can suppress thermal rotation without freezing the fluid (which defeats the purpose of using a reconfigurable liquid). Ferrofluid is a dead end for spectral eigenmode memory.

We present this failure explicitly because it illustrates an important design constraint: **SEM requires a substrate with negligible phase diffusion over the readout timescale.** This immediately rules out any liquid or colloidal medium, and any solid-state medium with significant acoustic attenuation at the operating frequencies.

### 3.2 Glass: Zero Phase Diffusion

Solid glass has the property we need. Acoustic waves in glass propagate with extraordinary fidelity: the material quality factor $Q_{\text{mat}}$ of borosilicate glass exceeds 10,000, and fused silica exceeds 100,000 [11, 12]. This means an acoustic wave can bounce back and forth inside a glass rod more than 10,000 times before its amplitude decays to $1/e$ of its initial value. Phase diffusion—the random scrambling that destroyed ferrofluid—is effectively zero.

Why is glass so different from ferrofluid? Because the atoms in glass are locked in an amorphous but _rigid_ network. There are no free-floating particles to reorient. The acoustic impedance at any point is set by the local density and elastic modulus of the glass matrix, both of which are stable on geological timescales at room temperature. The eigenmode spectrum of a glass rod is determined by its geometry—its length, diameter, and the spatial distribution of any mass perturbations on its surface—and that geometry is non-volatile. It persists without power, without refresh, without maintenance.

The speed of sound in borosilicate glass is 5,640 m/s—roughly 16 times the speed of sound in air. In fused silica, it is 5,960 m/s. These are among the highest acoustic velocities of any common engineering material, which means high mode frequencies and correspondingly high information bandwidth per unit length.

The choice of glass also brings practical advantages for fabrication. Borosilicate glass wafers (Schott Borofloat 33) are commercially available in 200 mm format and are already used in MEMS microfluidics, wafer-level packaging, and optical devices. The processing infrastructure exists. Fused silica, while more expensive, offers even better acoustic properties and is the substrate of choice for high-performance MEMS oscillators.
