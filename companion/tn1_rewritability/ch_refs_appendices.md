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
