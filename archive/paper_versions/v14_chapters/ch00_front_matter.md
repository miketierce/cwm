# Coherent Wave Memory: Wave-Based Storage and Computation in Acoustic Glass Resonators

**Mike Tierce**
_Independent Researcher_
ORCID: [0009-0004-4483-5283](https://orcid.org/0009-0004-4483-5283)
Repository: [github.com/miketierce/wcfoma](https://github.com/miketierce/wcfoma)

**Version 14 — June 2025**

---

## Abstract

Every memory technology in production today—SRAM, DRAM, Flash, PCM, ReRAM—stores information as an electrical state: a charge on a capacitor, a resistance across a junction, electrons trapped on a floating gate. Reading means sensing that electrical state. Computing means moving it somewhere else and operating on it with logic gates. The separation between storage and computation—the von Neumann bottleneck—is not a software problem; it is baked into the physics of how we encode data.

This paper describes a different encoding. Instead of charge or resistance, we store information in the _acoustic eigenmode spectrum_ of a solid glass resonator—the set of natural frequencies at which a glass rod vibrates. A mass perturbation applied to the rod's surface shifts each eigenmode frequency by a different amount, creating a unique spectral fingerprint. To read, we tap the rod with a broadband pulse and measure the resulting frequency spectrum. To search, we drive an array of rods with a query pattern: the rod whose stored fingerprint best matches the query resonates most strongly—a nearest-neighbor computation performed by wave interference in microseconds, with no processor, no memory bus, and no software.

We call this architecture **Coherent Wave Memory (CWM)**.

The core physics is validated at macro scale. A prototype built from a \$63 borosilicate glass rod achieves **98.8 dB signal-to-noise ratio** (thermal-noise-limited) and supports **9,380 thermally stable eigenmodes**—independent frequency channels that each carry 16.4 bits of information at the Shannon limit. Scaling analysis, verified by 365 automated tests across 21 first-principles simulation modules, projects that a 1 mm MEMS resonator achieves **95.5 Gbit/cm³** storage density (10× DRAM), rising to **1.4 Tbit/cm³** in fused silica arrays (1.4× NAND Flash), with **16 fJ/bit** write energy (190× below DRAM) and **native associative recall** in 3.6 µs.

A five-mechanism Q-factor model addresses the central question of MEMS viability—whether the quality factor that makes macro-scale resonance work survives miniaturization. It does: $Q_{\text{total}} = 9{,}110$, with anchor loss (the mechanism most sensitive to geometry) contributing only 4.2% of the loss budget. The dominant loss is the glass itself, not the MEMS structure.

Beyond the core architecture, we present four advanced encoding techniques that require no hardware changes—only firmware-level signal processing on the CMOS readout die: **(i)** synaptic weight pruning improves associative recall accuracy by 10.7%; **(ii)** in-situ Boolean computation (XOR, AND, OR) from mode superposition at >90% fidelity with 3× throughput; **(iii)** avoided-crossing mode hybridization creates bonus information channels yielding up to +160% capacity gain; and **(iv)** null-space multiplexing recovers hidden degrees of freedom invisible to standard readout, adding +60% bonus capacity.

The entire fabrication pathway uses established MEMS processes in volume production today: glass deep reactive ion etching, aluminium nitride thin-film piezoelectric transduction, wafer-level vacuum packaging, and CMOS flip-chip bonding. What remains is the MEMS demonstration itself—building the device and measuring it.
