# Prototype A: Macro-Scale Ferrofluid Resonator

## Overview

This is the first physical prototype described in WCFOMA paper Section 4.1. It serves as a visual and quantitative validation of wave-coherent memory at macro scale.

## Specifications

| Parameter           | Value                               | Notes                       |
| ------------------- | ----------------------------------- | --------------------------- |
| Medium              | Commercial ferrofluid + STF carrier | e.g., Ferrotec EFH-1        |
| Cavity geometry     | Cylindrical, 1-5 cm diameter        | Start with 2 cm             |
| Excitation          | EM coils, 10-500 kHz                | 100-500 turns, 0.1-1 A peak |
| Readout (primary)   | Faraday rotation                    | HeNe laser + polarizer      |
| Readout (secondary) | Inductive pickup                    | Sense coil wound on cavity  |
| ZIM structures      | 3D-printed pillar arrays            | Dirac-cone design           |
| Temperature control | Peltier + PID                       | ±0.5 K stability            |
| Total cost target   | < $1,000                            |                             |

## Bill of Materials

### Fluids

- [ ] Ferrotec EFH-1 ferrofluid (100 mL)
- [ ] Shear-thickening fluid (cornstarch suspension or commercial STF)
- [ ] Mixing containers, syringes

### Cavity

- [ ] Cylindrical chamber (acrylic or aluminum, 2 cm ID × 3 cm length)
- [ ] End caps with optical windows (BK7 or fused silica)
- [ ] O-ring seals

### Excitation

- [ ] Magnet wire (26-30 AWG, ~100 m)
- [ ] Coil former / bobbin
- [ ] Function generator (1 Hz - 1 MHz, e.g., Rigol DG1022Z)
- [ ] Audio amplifier or coil driver

### Readout

- [ ] HeNe laser module (632.8 nm, 1 mW)
- [ ] Polarizer pair (film or Glan-Thompson)
- [ ] Photodiode (e.g., Thorlabs FDS100)
- [ ] Transimpedance amplifier
- [ ] Oscilloscope (e.g., Rigol DS1054Z)

### ZIM

- [ ] 3D printer access (SLA preferred for fine features)
- [ ] Design files for Dirac-cone pillar array (see `prototypes/zim_designs/`)

### Environmental

- [ ] Peltier module + heatsink
- [ ] PID temperature controller (e.g., Inkbird)
- [ ] Thermistors (NTC 10K)
- [ ] Enclosure (foam-lined box)

## Assembly Sequence

1. Print ZIM structures; verify feature dimensions under microscope
2. Machine or 3D-print cavity; install optical windows
3. Wind excitation coils (calculate turns for target field strength)
4. Mix ferrofluid with STF carrier (ratio TBD from viscosity tests)
5. Fill cavity, insert ZIM structures, seal
6. Mount on optical breadboard with laser + readout optics
7. Connect excitation coils to function generator
8. Install temperature control (Peltier on cavity wall)
9. Calibrate: sweep frequency, identify resonance peaks in air-filled cavity
10. Fill with ferrofluid mixture, repeat frequency sweep

## Measurement Plan

See `docs/PROTOCOLS.md` for general protocols. Specific to Prototype A:

1. **Mode identification**: Frequency sweep 10-500 kHz, record Faraday rotation angle and inductive pickup amplitude
2. **Coherence time**: Pulse excitation, measure ring-down time
3. **Multi-mode**: Excite two frequencies simultaneously, verify independence
4. **Shear response**: Apply controlled compression, measure frequency shift
5. **Temperature sweep**: ±5 K, measure frequency drift per K
6. **ZIM comparison**: Repeat all measurements with/without ZIM structures
