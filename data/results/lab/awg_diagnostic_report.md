# AWG Diagnostic Report — Pre-Teardown 4-Rod Rig

**Date:** 2025-07-05
**Hardware:** PicoScope 2204A, ps2000 driver, macOS ARM64
**Wiring:** AWG OUT → 4× drive PZTs (parallel), Ch A → 3× sense PZTs (Rods 2,3,4), Ch B → Rod 1 sense PZT

## Executive Summary

**AWG-driven rod identification does not work with the current PZT hardware.**
The 2 Vpp signal through 600 Ω cannot deliver enough mechanical energy through
PZT disc transducers to excite detectable bending modes in 6 mm glass rods.
The measured signal is almost entirely electrical feedthrough, not mechanical resonance.

## Tests Performed

### 1. Stepped-Dwell Resonance Test (`awg_stepped_dwell.py`)

Drove AWG at each of Rod 1's 10 enrolled frequencies, measured response,
compared to off-resonance midpoint frequencies.

| Metric                | Value                       |
| --------------------- | --------------------------- |
| **Best on/off ratio** | 4.14× at 2355 Hz            |
| **Clear resonances**  | 2 of 10 peaks (>2×)         |
| **Mean on/off ratio** | 0.34 (off-resonance HIGHER) |

The feedthrough transfer function peaks at ~2 kHz (31.5M magnitude) and drops
1000× by 5.7 kHz, completely masking rod resonance signatures.

### 2. Burst-and-Ringdown Test (`awg_burst_ringdown.py`)

Drove AWG for 20–500 ms, turned off, captured free decay.

| Config                           | Ringdown RMS | Noise RMS | SNR      | Enrolled Found |
| -------------------------------- | ------------ | --------- | -------- | -------------- |
| All configs                      | 112–132      | 130       | 2.9–3.1× | **0/10**       |
| Deep avg (20 reps, 100 ms burst) | —            | —         | 3.9×     | **0/10**       |
| Single-freq dwell + ringdown     | —            | —         | 1.0–2.7× | **0/10**       |

**Zero detectable rod vibration after AWG excitation.**

### 3. AWG Turn-Off Timing (`awg_final_diag.py`)

| State            | RMS (ADC)  | Peak Hz | SNR    |
| ---------------- | ---------- | ------- | ------ |
| AWG ON @ 1833 Hz | 2,422      | 1,841   | 1,351× |
| AWG "OFF" +0 ms  | **29,813** | **484** | 408×   |
| AWG "OFF" +50 ms | **29,805** | **484** | 391×   |

**Critical bug:** `ps2000_set_sig_gen_built_in(handle, 0, 0, ...)` does NOT
silence the AWG. It produces a massive ~2.7 V pp parasitic at 484 Hz that
persists until the scope is closed. This corrupted ALL ringdown measurements.

### 4. Dual-Channel Bug

Enabling Ch B (`ps2000_set_channel(handle, 1, True, ...)`) freezes all
subsequent captures — they return identical stale data regardless of AWG
state, frequency, or physical tapping. **Ch B must remain disabled.**

### 5. AWG Pulse (Arbitrary Waveform)

Sharp pulses (1–64 samples) at 100 Hz repetition → **SNR 1.7–1.9× (noise floor)**

### 6. High-Average Sweep

| Averages | SNR   | Blind Peaks | Enrolled Found | Rod 1 Score | Rod 4 Score |
| -------- | ----- | ----------- | -------------- | ----------- | ----------- |
| 4        | 3.5×  | 0           | 0/10           | —           | —           |
| 100      | 99.6× | 1           | 2/10           | 33.4%       | 31.6%       |
| 200      | 88.5× | 1           | 2/10           | 39.7%       | 36.0%       |

With 100+ averages, the spectrum shows the feedthrough transfer function shape
(peak at ~2 kHz), not rod resonances. Only 1 blind peak detected. Scores too
close between rods for reliable identification.

### Voltage Comparison

| Excitation         | Sense PZT Voltage (pp) | SNR                   | Enrolled Found |
| ------------------ | ---------------------- | --------------------- | -------------- |
| Fingernail tap     | ~800 mV                | **1,422×**            | **18/20**      |
| AWG sine @ 1833 Hz | 234 mV                 | 1,351× (feedthrough!) | 2/10           |
| AWG ringdown       | ≤54 mV (=noise)        | **1.0×**              | **0/10**       |

## Root Cause

The PZT disc transducers (typical 27 mm buzzers) have extremely low
electromechanical coupling to bending modes of thick glass rods:

- **Force**: A PZT buzzer at 2 V produces ~µN of force. A fingernail flick
  delivers ~10⁴× more impulse.
- **Coupling**: Putty contact is lossy; radial PZT modes couple poorly to
  rod bending modes.
- **Impedance**: The 600 Ω AWG output into capacitive PZT loads (~nF)
  delivers negligible current at low frequencies.

The measured response on Ch A is **electrical feedthrough** (capacitive/
inductive coupling between drive and sense PZTs through shared wiring and
rod surface), not mechanical vibration.

## What Works

- **Tap mode**: 1,422× SNR, 18/20 peaks, 63 dB — reliable and fast
- **AWG sweep ON Ch A only**: produces detectable feedthrough with shape
  influenced by the rig, but cannot discriminate between rods

## Recommendations for Autonomous Excitation

1. **High-voltage PZT amplifier** (50–200 V, low impedance) — increases
   force by 25–100× and power by 625–10,000×
2. **Stack PZT actuator** — higher force, better low-frequency response
3. **Electromagnetic tapper** — solenoid or relay clicking against rod
4. **Speaker driver** — voice coil pressed against rod body
5. **Compressed air pulse** — non-contact impulse

For the current pre-teardown: **all 6 tests are already complete** using
tap mode. No AWG fix is needed for the existing data.
