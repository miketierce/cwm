# CWM Quantum Transition: Preliminary Existing-Data Results

**Status:** PRELIMINARY / CLASSICAL BOUNDS. No quantum state or quantum witness was measured.

## Result Summary

| Question | Preliminary result | Meaning |
| --- | --- | --- |
| Does a classical phase model explain the saved sweeps? | 18 sweeps; median leave-one-phase-out first-harmonic R2 0.791 (training R2 0.839) | Quantifies the classical interference null; not a quantum witness |
| Is nonlinearity resolved at the tested macro drive? | Maximum positive standardized excess 1.46 sigma; 0 products at or above 3 sigma | No detected intermodulation; K remains unidentifiable |
| What rank is visible now? | H shape 26 x 2; entropy-effective rank 1.049 | Two-channel ceiling; rank-8 still requires new hardware |
| How close is the best measured mode to the 300 K bare Qf screen? | f=117.73 kHz, Q=511.0, Qf/(kBT/h)=9.625e-06 | A measured classical baseline, not a MEMS quantum projection |
| Does higher Q help the classical parametric threshold? | epsilon_min falls from 0.937% at measured median Q to 0.020% at Q=1e4 | Useful for a classical latch; does not solve thermal occupation |

## 1. Classical Phase Null (QT-0B Precursor)

Across 18 saved phase-energy sweeps, the median fitted first-harmonic R2 is 0.839; leave-one-phase-out prediction gives 0.791. The fraction with cross-validated R2 >= 0.8 is 50.0%.

The worst sweep is 70.0 kHz with leave-one-out R2 -0.077; the median second-harmonic improvement is 0.052. The simple null therefore describes much, but not all, of the archive. Weak modulation, source distortion, or multimode terms must be tested before interpreting residuals.

This is evidence about model adequacy only. The archive contains phase-energy grids and spectra, not the raw phase-referenced voltage records needed to close QT-0B.

## 2. Macro Nonlinearity Bound (QT-1C Precursor)

The controlled dual-tone files contain 46 standardized IM comparisons. The largest positive excess is 1.46 sigma, the largest absolute deviation is 1.87 sigma, and none reaches 3 sigma. The earlier noise-ratio scan peaks at 1.37 times its local noise floor.

The standardized values use the AWG-only or f1-only single-tone floor according to the source experiment; the machine-readable summary preserves that reference for every comparison. Because no uncorrected comparison reaches 3 sigma, a multiple-comparison correction cannot create a detection. This supports a linear macro-substrate null at the tested settings, but the dataset has no calibrated effect-size or power bound. It does not measure a Duffing coefficient or K because displacement calibration and a drive-power sweep are absent.

## 3. Readout Rank Bound (QT-1B Precursor)

The simultaneous H matrix has two receiver columns. Its raw singular-value condition number is 10.96, algebraic rank is 2, and entropy-effective rank is 1.049. After column-gain normalization, the entropy-effective rank is 1.159.

No reanalysis of these two channels can establish rank 8; additional independent receivers are required.

## 4. Thermal and Coupling Envelope (QT-0C)

The ten-mode June 3 bandwidth dataset has median loaded Q 213.4 and maximum Q 511.0. The best measured Qf screen ratio is 9.625e-06.

The generated JSON includes the full 280-320 K, 3.5-35 MHz, Q=1e4-1e6 coupling envelope for Cq=1.

### Representative 300 K coupling screen

At high temperature the thermal rate is nearly frequency-independent at fixed Q. The 10 MHz rows are representative of the 3.5-35 MHz band.

| Q | Gamma_Sigma / 2pi | Required g / 2pi at gamma_q / 2pi = 1 kHz | At 10 kHz | At 100 kHz |
| ---: | ---: | ---: | ---: | ---: |
| 1e+04 | 1250.20 MHz | 559.1 kHz | 1767.9 kHz | 5590.6 kHz |
| 1e+05 | 125.02 MHz | 176.8 kHz | 559.1 kHz | 1767.9 kHz |
| 1e+06 | 12.50 MHz | 55.9 kHz | 176.8 kHz | 559.1 kHz |

### Existing MEMS model proxy

| Scenario | Frequency | Modeled Q | Qf screen ratio | Remaining gap | Dominant loss |
| --- | ---: | ---: | ---: | ---: | --- |
| end_anchor | 2.880 MHz | 51038.1 | 2.352e-02 | 42.5x | Material (intrinsic) |
| nodal_isolated_anchor | 2.880 MHz | 66179.5 | 3.049e-02 | 32.8x | Material (intrinsic) |

The roadmap target is a 1 mm x 1 mm x 50 um plate. This rod model is a sensitivity proxy, not a prediction for the proposed die.

## 5. Classical Parametric Threshold (QT-1C Simulation)

| Scenario | Q | epsilon_min |
| --- | ---: | ---: |
| measured_loaded_q_median | 213.4 | 0.9370% |
| measured_loaded_q_max | 511.0 | 0.3914% |
| roadmap_classical_mems_target | 10000.0 | 0.0200% |
| rod_proxy_end_anchor (rod geometry; see Section 4 caveat) | 51038.1 | 0.0039% |
| rod_proxy_nodal_isolated (rod geometry; see Section 4 caveat) | 66179.5 | 0.0030% |

Higher Q sharply lowers the classical parametric threshold, but crossing it does not cool the mode or produce a nonclassical state.

Existing captures do not calibrate fractional stiffness modulation versus drive, so these thresholds cannot yet be converted into a required voltage or pump power.

## What Existing Data Cannot Answer

- No saved dataset contains a quantum subsystem, single-shot quantum outcomes, or a nonclassical mechanical-state witness.
- No calibrated displacement sweep supports an estimate of the single-quantum Kerr rate K.
- No qubit-mode coupling data support an estimate of g or measured quantum cooperativity Cq.
- No MEMS die exists yet, so MEMS Q, rank, heating, and transducer loading remain projected.
- The saved phase grids can test a deterministic interference model but cannot complete the stochastic raw-voltage null required by QT-0B.

## Reproduction

```bash
python3 tools/quantum_transition_preliminary.py
```

Machine-readable details are in `data/results/quantum_transition/preliminary_existing_data/summary.json`.
