# CWM — The Water Cooler Summary

*Updated: 21 October 2026. Evidence base: lab diaries through 30 June 2026 and repo state at 13 July 2026. Supersedes the 24 April version (pre-preamp), archived at `archive/tmp/WATER_COOLER_SUMMARY_pre_preamp_20260424.md`. Claim-by-claim status lives in [paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md).*

---

## What Is It? (The 30-Second Version)

A thin plate of glass rings with a set of pitches that is unique to that plate. We drive it with ultrasound, listen to which pitches ring and how loudly, and use that response as a **physical fingerprint** and a **physical feature map**: a rich, noise-tolerant code that digital software can read, match against, and complete from partial information.

No transistors in the glass. Nothing to program. The glass is passive; the "memory" is its vibration structure.

Our April claim, that the plate is a chip and a hard drive at once, did **not** survive validation. What survived is narrower and better tested.

---

## How Does It Work? (The Cocktail Party Version)

Drop a rock in a swimming pool and the ripples bounce off the walls into a pattern that depends on the pool's shape. A glass plate does the same thing with sound too high to hear (30-350 kHz).

- **Drive:** a Raspberry Pi Pico generates up to 15 tones (8 phase-coherent) and sends them into tiny piezo discs glued to the plate.
- **Listen:** other piezo discs pick up the vibration. A preamp (x11, later x48) lifts it to something the PicoScope can digitize.
- **Read:** an FFT shows which of the plate's resonances rang. Together they form the plate's spectrum.
- **Write:** adding a small mass (putty) shifts the resonances measurably. Electronic write/erase works through interference between two drive tones.

---

## What Changed Since April

| Then (24 Apr) | Now |
|---|---|
| Signal too weak, "waiting for a $5 preamp" | Preamp built. Every receive channel reads 24-32x above the noise floor; the 15-channel census finds **767 usable modes** (was 173) |
| AD9833 DDS boards as the frequency source | Both boards died on 2 June (breadboard ground faults). Replaced by the Pico NCO |
| Summary claimed compute, 100% Boolean logic, 17,170x energy | Audited on 1 May, then rewritten. See "What We Retracted" |
| Plan: prove temporal memory for reservoir computing | Bench result negative; moved to the MEMS roadmap |
| One big paper | Narrowed paper (v19r): *Spectral Fingerprinting in Piezo-Driven Fused-Silica Plate Resonators* |

---

## What Have We Actually Proven?

### Measured on the bench (high confidence)

| What | Result | What it means |
|---|---|---|
| Resolvable acoustic modes | 7-15 per plate at 42-56 dB SNR; 767 in the 15-channel array census | Each plate has a rich spectrum |
| Signal is acoustic, not wiring | Zero feedthrough with the PZT lifted; 49-60:1 spatial contrast; tape-vs-glue null | It is the glass ringing |
| Fingerprint classification | 100% (80/80), 193 sigma separation, single session | Plates are distinguishable |
| Multilevel encoding | 8 levels x 4 modes = 4,096 states with zero error (12 bits), single session | The spectrum carries real bits |
| Stability | 0.22% drift over 16.5M cycles; 0.65% over 3.5 h | Stable enough to be a fingerprint |
| Loaded Q | 150-743 (bandwidth method) | Modes ring for milliseconds, not hundreds of ms |
| Interference | Two drives on one plate cancel the response by 99.5%, reversibly. Three paths sum with a measured cross-term (R² 0.92) | The glass genuinely adds waves |
| Null readout | Reading the cancellation null identified 1-of-5 stored phases 100% under common-mode gain noise (chance 20%) | A robust way to read phase-encoded states |
| Classical non-separability | CHSH-style S = 2.73 (fixed angle) to 2.83 (optimized), 5/5 mode pairs | A geometric property of plate modes; **not** entanglement |

### Measured offline on saved captures (suggestive, needs live bench confirmation)

| What | Result | Caveat |
|---|---|---|
| Partial-query completion | Glass 84-92% vs direct wire 47-59% at sigma = 1 | Captures were driven with all inputs; hidden variables were masked in software, so this is not a physically incomplete query |
| Graceful degradation | Only about 5 points lost with 90% of modes zeroed | Same offline caveat |
| Where glass loses | A clean, full-information query: a wire plus lookup wins (100% vs 97%) | Glass only helps when the query is noisy or partial |

---

## What We Retracted or Killed

- **"The plate computes."** Boolean logic and recall were done by digital decoders reading spectral features. The plate is a linear spectral transformer. Plates reached 66.5% on Boolean tasks, not 100% (the 100% was on rods).
- **Temporal reservoir computing.** NARMA-10 fails in all three attempted configurations. The 0.171 NMSE result was a hybrid: the plate gave a spatial kernel and a software ESN did all the temporal work.
- **17,170x energy advantage.** A theoretical projection that was never measured. Not claimed.
- **Q = 7,687-33,960.** Ringdown fits were poor (R² < 0.18). Bandwidth Q is 34-743.
- **Intermodulation / nonlinear mixing.** The April 11-product result did not replicate under controlled tests: 46 comparisons peaked at 1.46 sigma, and the two-tone test gave IMD3 near -27 dBc (consistent with noise). The preamp chain never railed, and the cascade measured linear. Treat the glass as linear until shown otherwise.
- **Phase as a bench data channel.** Absolute phase was not usable; only relative phase between co-driven tones works.
- **Also killed:** ferrofluid substrates, cymatics-script correlation (3 of 4 hypotheses killed on 1 May), audio-interface capture, "room-temperature quantum hardware".

The project's own kill rate is about a third of hypotheses. That is the method working.

---

## Where the Hardware Stands

- Drive side (Pico NCO, 15 tones): healthy.
- Receive and preamp board: **faulted on 30 June.** All 15 channels went dead, then the board overheated and was disconnected. Repair status is unknown and no newer measurement was found. It must not be re-powered until it is cold-inspected.
- Test suite: 2,253 tests; one known failing (`test_mems_q_model.py`, expects 5 Q components, implementation has 6).

---

## What's Next

| Step | Why it matters |
|---|---|
| Safe recovery of the receive board (TB-00) | Gate for all powered work |
| Physically rewrite and re-read a stored pattern (P8 / template-bank worklist) | The memory claim is only earned by a closed physical write-erase-rewrite loop; E3 putty shifts are one-way and only 5 of 10 mode channels reversed |
| Cross-session fingerprint test (>=95%) | Turns a session demo into a device property (PUF) |
| Physical incomplete-query test (Wheel-of-Fortune protocol) | Confirms partial-query completion without software masking |
| Optical readout | Breaks the rank-2 readout limit |
| MEMS plate | Raises Q and shortens decay for temporal memory, if the scaling holds |

---

## Why Should Anyone Care?

Near-term, in rough order of confidence:

1. **Acoustic PUF.** Every plate has a unique, stable fingerprint. Spectral PUFs are not new on their own; fingerprint plus content-addressable recall in one substrate is the fresher combination.
2. **Multi-mode perturbation sensor.** Mass-loading shifts many modes at once and encodes mass and position.
3. **A $50 desk demo of classical non-separability** that anyone can replicate.
4. **Random-projection front-end** for noisy or partial inputs.

Longer-term and unproven: a MEMS-scale reservoir or parametric computer. It is a projection and not a measurement. Fused silica's radiation and temperature tolerance are material properties, and not yet measured on our devices.

### The Honest Caveat

In April we said "Wright brothers phase: the engine is too quiet." The engine is now loud enough, and what we learned is that the aircraft we described was not the one we built. We have a well-controlled measurement platform, a stable fingerprint, real interference, and a clear kill list. We do not have a computer, a reservoir, or a quantum anything.

---

## The One-Liner

**A glass plate has a stable, unique ultrasonic fingerprint that carries 12 bits, supports wave interference, and tolerates dropout. We know exactly where that stops.**

---

## Want to Go Deeper?

- Claim ledger: [paper/CLAIMS_STATUS.md](../paper/CLAIMS_STATUS.md)
- Paper: `paper/v19r.md`
- Forward plan: [ROADMAP_FULL_POTENTIAL.md](ROADMAP_FULL_POTENTIAL.md)
- Latest bench record: [lab_diary_20260630.md](lab_diary_20260630.md)
- Template-bank worklist: [PHYSICALLY_WRITTEN_TEMPLATE_BANK_WORKLIST.md](PHYSICALLY_WRITTEN_TEMPLATE_BANK_WORKLIST.md)
- Book manuscript: `cwm-book/manuscript/`
- Live demo: `cwm-site`
