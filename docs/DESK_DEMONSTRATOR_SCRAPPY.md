# Desk Demonstrator — The Scrappy Path (Reuse-First Build & Iterate)

**Companion to [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md) (the polished build) and [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md) (the shareable, repeatable procedures).**

This document is deliberately **not** the repeatability protocol. Its job is the opposite: get a working briefcase-array prototype on the desk **as fast and as cheaply as possible**, reusing gear you already own and junk-drawer substitutes, so you can **prove and iterate** the ideas before spending on the polished, shareable rig. Results from this path are for _your_ iteration — when a result is solid enough to publish or share, you re-run it under the clean protocol with calibrated parts.

**The governing rule:** buy nothing until a scrappy version proves the idea is worth the spend. Every BOM purchase in the polished doc should be _earned_ by a scrappy result first.

**⚠️ Wave-Native Design Principle.** Before iterating any demo: the glass is a smooth, low-dimensional analog **kernel + CAM**, not a von Neumann machine. The first silicon algorithm you reach for usually fails. Proven dualities (MEASURED 2026-06): track/integrate not predict/branch; nearest-**centroid** not ridge **regression** (T3.4 4096 states 100% vs ridge 0.55%); encode by **amplitude of a fixed mode** not **frequency position** (8 levels/mode @ 100σ vs ~2 levels/axis); **factor** the state; keep collision modes; make the **Gram matrix** diagonal-dominant. Full table in [FULL_POTENTIAL_WORKLIST.md](FULL_POTENTIAL_WORKLIST.md).

---

## 1. How This Path Differs

|             | Scrappy path (this doc)                   | Polished path ([protocol](DESK_DEMONSTRATOR_PROTOCOL.md)) |
| ----------- | ----------------------------------------- | --------------------------------------------------------- |
| Goal        | Prove/iterate fast, cheap                 | Repeatable, shareable, publishable                        |
| Gear        | Owned + salvaged + junk-drawer            | Specified BOM with verified SKUs                          |
| Readout     | PicoScope block capture, software lock-in | FPGA streaming lock-in (Red Pitaya)                       |
| Calibration | "good enough to see the effect"           | logged, reproducible, manifest-tracked                    |
| Data        | scratch notes, quick plots                | `data/results/desk/` with manifests                       |
| When to use | first contact with every phase            | once the scrappy version works                            |

**Use scrappy to answer "does this work at all?" Use the protocol to answer "can someone else reproduce it?"**

---

## 2. What You Already Own → Role in the Array

Everything here is confirmed on the bench (see [../HARDWARE.md](../HARDWARE.md) and the lab-hardware notes). Reuse it all.

| Owned gear                                                             | Normal job       | Role in the scrappy demonstrator                                                                                                                           |
| ---------------------------------------------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PicoScope 2204A** (2-ch, 781 kS/s, built-in AWG, 3968-sample buffer) | scope + AWG      | **The brain stand-in.** AWG drives; 2 channels digitize; software lock-in in Python on captured blocks. Covers every _non-streaming_ phase (P0,1,3,4,5,6). |
| **Pico NCO** (Raspberry Pi Pico H, 4-ch PIO, GP2–GP5)                  | multi-tone drive | Carrier source for the 30–350 kHz modes; 4 simultaneous tones; `PHASE:` for the interference/CHSH and parametric work.                                     |
| **Arduino relay mux** (8-ch)                                           | channel select   | **Spatial addressing** of plates/readout points — funnels many channels into the PicoScope's 2 inputs; per-plate isolation for null tests.                 |
| **Board A preamp** (×11, OPA2134, _spare half free_)                   | RX gain          | Preamp for contact PZTs **and** the transimpedance amp for the photodiode (the spare OPA2134 half: Rf=100 kΩ, Cf=10 pF).                                   |
| **Board D buffer** (3.69×, OPA2134)                                    | drive boost      | Boost AWG/NCO drive into the TX PZTs when broadcast across a rack needs more amplitude.                                                                    |
| **Plates I, H (100 mm), 25 mm, + 5-plate cassette (A–E)**              | resonators       | **The array seed.** The April cassette is already a relay-muxed multi-plate rack — start there before building a new card cage.                            |
| **PZT discs (installed) + spares**                                     | TX/RX            | Per-plate drive; contact-RX fallback when optical SNR is poor.                                                                                             |
| **MCP4921 DACs (×2, 12-bit SPI)**                                      | amplitude set    | Per-mode amplitude levels (the 8-level encoding) without tying up the AWG.                                                                                 |
| **Kronos USB audio (192 kHz, 2-in/2-out)**                             | audio I/O        | **Baseband envelope streaming** for a poor-man's temporal demo — stream the _demodulated_ envelope (kHz-scale), not the raw modes.                         |
| **Wax putty + (any) milligram scale**                                  | perturbation     | Surface write (P5) with zero new parts.                                                                                                                    |
| **Breadboards, OPA2134 spares, passives**                              | glue             | TIA, summing, threshold comparator, coupling networks.                                                                                                     |

**Already-specced optical gear** (from [../prototypes/prototype_a/README.md](../prototypes/prototype_a/README.md)): a HeNe laser module (632.8 nm) and a Thorlabs FDS100 photodiode appear in the prototype parts list. If you have these on hand, they are _better_ than the budget 650 nm diode + BPW34 — use them for the scrappy optical readout.

---

## 3. Junk-Drawer Substitutions (buy-nothing alternatives)

For each polished-BOM item, the scrappy substitute that proves the same thing. Upgrade only when the substitute's limit is what's blocking you.

| Polished BOM                 | Scrappy substitute (reuse / salvage / cheap)                                                                                                                  | What you lose                          | Good enough for                             |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | ------------------------------------------- |
| Red Pitaya FPGA (DD1)        | **Owned PicoScope** + Python software lock-in                                                                                                                 | real-time feedback; kHz streaming loop | P0,1,3,4,5,6 fully; P2/P7/P8 only partially |
| 650 nm laser module (DD2)    | **Any laser pointer** ($3) or owned HeNe; even a laser level                                                                                                  | beam quality, stability                | rank-N readout, mode-shape imaging          |
| Galvo scanner (DD3)          | **Hand-moved laser on an articulating arm** to marked spots; or a **hobby servo + mirror** ($4) for 1D scan; or a **phone/webcam** imaging the reflected spot | scan speed (manual = minutes, not ms)  | proving rank ≥6 (slowly)                    |
| BPW34 photodiode (DD4)       | **Salvaged photodiode** (from an old mouse/printer/remote), **phototransistor**, **small solar cell**, or **LDR** (slow)                                      | bandwidth, linearity                   | seeing the mode peak vs nulls               |
| Quadrant PD (DD3-esc)        | **4 cheap photodiodes** in a square, or a **webcam** doing centroid tracking                                                                                  | precision                              | spot-position sensing                       |
| Transimpedance amp (DD5)     | **Spare OPA2134 half on Board A** (owned)                                                                                                                     | nothing — same circuit                 | all optical readout                         |
| Card cage (DD8)              | **Existing 5-plate cassette**, **cardboard + foam**, or **3D-print/laser-cut** if available                                                                   | rigidity, repeatability                | first array runs                            |
| Microscope slides (DD6)      | **Slides you have**, or scavenged thin glass (cover glass, picture-frame glass cut down)                                                                      | thickness control                      | census, CAM, PUF iteration                  |
| Multichannel audio IF (DD10) | **Owned Kronos USB audio** (2-ch) for envelope streaming                                                                                                      | channel count                          | 1–2 mode temporal sketch                    |
| Vacuum chamber + pump (DD12) | **Food-saver vacuum jar + hand brake-bleeder pump**, or a **mason jar + fridge-compressor**                                                                   | vacuum depth, stability                | first Q-vs-pressure curve                   |
| Quartz forks (DD13)          | **Watch/clock crystals** salvaged from dead electronics (32.768 kHz)                                                                                          | matched specs                          | single-spin parametric test                 |
| Engraving laser (DD14)       | **defer entirely** — volumetric write is not a scrappy-iteration target                                                                                       | —                                      | (skip until polished)                       |
| Pelican case (DD17)          | **Any toolbox / cardboard box / open frame**                                                                                                                  | portability, looks                     | bench iteration                             |
| Linear PSU (DD18)            | **Owned bench supply / wall-warts / 9 V batteries** (already used for Board D)                                                                                | noise                                  | everything early                            |
| Host SBC (DD19)              | **Your laptop**                                                                                                                                               | —                                      | everything                                  |

**Crossbar add-on substitutions (the MEMS-faithful core, see DESK_DEMONSTRATOR.md §3.2):**

| Polished BOM               | Scrappy substitute                                                                                                      | What you lose                            | Good enough for                    |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- | ---------------------------------- |
| PVDF film (DD20)           | Salvaged PVDF from a **piezo contact mic / "knock sensor" / piezo greeting-card** element; or a grid of light PZT discs | uniformity, clean electrode patterning   | crossbar bring-up, rank-N sense    |
| Crosspoint switch (DD21)   | **Owned relay mux** as the (row, col) stand-in; or a **CD4051/CD4067 analog mux** (~$1)                                 | switching speed, true crossbar isolation | small (≤8×8) arrays                |
| 3D stack frame (DD22–DD24) | **Cardboard/foam-core spacers** on bamboo skewers or bolts; **jumper-wire** vertical bus; foam pads at nodes            | rigidity, clean isolation                | first stacked (layer,row,col) demo |

---

## 4. Phase-by-Phase: Scrappy Achievability

What each protocol phase looks like on the scrappy path, what degrades, and the **upgrade trigger** — the result that justifies buying the polished part.

### P0 — Census · **fully scrappy**

Owned PicoScope AWG sweep + cell readout addressed by the **relay mux** (the scrappy crosspoint stand-in — the scale-faithful (row, col) path). Software peak-find in Python.

- **Reuse:** PicoScope, Pico NCO, relay mux, cassette plates.
- **Limit:** none worth upgrading for. Census is census.

### P1 — Rank-N readout / crossbar (scale-faithful) + optical cross-check · **scrappy proves it**

**Scale-faithful path (the one that shrinks):** a salvaged-PVDF (or light-PZT) cell grid on one plate, row/col bussed, addressed by the **owned relay mux** (or a ~$1 CD4051 mux) as the crosspoint stand-in — drive shared, sense each cell, build the cell×mode matrix, SVD for rank. **Optical cross-check (slow, no MEMS counterpart):** laser pointer on an arm, salvaged photodiode + knife edge → spare OPA2134 TIA → PicoScope ChA; move the spot **by hand** to 8 marked positions; build the spot×mode matrix; SVD. Use the optics only to confirm the crossbar's rank independently.

- **Reuse:** owned relay mux (crosspoint stand-in), Board A spare op-amp, owned laser/HeNe, PicoScope.
- **Limit:** manual optical scan is minutes per pass; salvaged PVDF electrode grid is fiddly to pattern.
- **Upgrade trigger:** crossbar rank ≥6 reproducibly → buy the **crosspoint IC (DD21)** for fast (row,col) addressing; if you also want the live optical check, buy the **galvo (DD3)**.

### P2 — Fast loop / temporal · **the one phase scrappy can't fully do**

The PicoScope block loop is ~8 Hz — exactly the B2 bottleneck. You _can_ sketch it: drive a burst, capture the ring-down envelope once, demodulate offline; or stream a single mode's envelope through the **Kronos audio** at kHz to show the envelope evolving.

- **Reuse:** PicoScope (ring-down capture), Kronos (envelope stream).
- **Limit:** no real-time closed loop; no live reservoir.
- **Upgrade trigger:** if the offline ring-down shows usable τ structure → buy the **Red Pitaya (DD1)**; this is the single purchase that unlocks temporal computation.

### P3 — FDM single-capture readout · **scrappy with care**

Detune your scrappy plates (different slide thicknesses / tuning masses), drive all tags, one PicoScope capture, software-demod each band.

- **Reuse:** PicoScope, Pico NCO multi-tone.
- **Limit:** software demod of many bands from a 3968-sample block is coarse.
- **Upgrade trigger:** clean band separation but coarse amplitudes → Red Pitaya parallel lock-in.

### P4 — CAM / associative search · **fully scrappy, high-impact**

One template per cassette plate; broadcast a query via AWG; one capture; score overlap; argmax. This is the headline demo and it runs entirely on owned gear.

- **Reuse:** cassette, PicoScope, relay mux.
- **Limit:** none for proving it; speed only.

### P4A — Hybrid logic / HD compute · **fully scrappy, the general-compute proof**

Extends P4 into actual general logic: interference on two modes → threshold (software comparator on FFT bin) → result selects next plate (relay mux). Boolean AND/OR/NOT via dual-mode overlap, then cascaded LUT by chaining plate selections. No new hardware at all — it's the same sweep/capture + a threshold + relay-mux routing. The proof that Q doesn't limit cascade depth is: run 5–10 stages and confirm flat margin. See architecture §7A.

- **Reuse:** cassette, Pico NCO, relay mux, PicoScope, Python.
- **New parts:** none. Firmware/software only.
- **Limit:** clock speed (~250 Hz on relay mux; faster with crosspoint switch DD21). The cascade depth itself is unlimited.

### P5 — Surface write · **fully scrappy**

Wax putty + scale + fine sweep. Identical to WL-A2, zero new parts.

### P6 — PUF · **fully scrappy**

Identical cassette plates (or matched slides), relay-addressed, ×3 census + power cycle, Hamming-distance metrics in Python.

- **Reuse:** cassette, relay mux, PicoScope.

### P6B — Non-separability + phase switch · **fully scrappy**

CHSH is already MEASURED on owned gear (S = 2.83) — re-run on the array with two NCO channels (`PHASE:`) into two readout points; fixed-angle S in Python (same path as WL-A3). Phase switch: sweep relative phase, report contrast.

- **Reuse:** Pico NCO (phase-locked), relay mux, PicoScope.
- **Limit:** none for the CHSH re-run; the 3-DOF extension wants the FPGA.

### P7 — Vacuum + Q-control · **half scrappy**

Vacuum: food-saver jar + hand pump gives a first Q-vs-pressure curve. Q-control feedback: hard without the FPGA, but you can demo _passive_ Q recovery from vacuum alone.

- **Reuse:** owned plates, optical readout.
- **Upgrade trigger:** Q rises usefully under jar vacuum → invest in a real **pump (DD12)** and the **Red Pitaya** for active Q-control.

### P8 — Parametric / Ising · **scrappy single-spin only**

Pump a salvaged quartz fork (or high-Q plate mode) at 2f with the Pico NCO; watch for the 0/π bistability knee. One spin, by hand.

- **Reuse:** Pico NCO (2f pump), salvaged watch crystals, PicoScope.
- **Limit:** programmable multi-spin J coupling needs the FPGA.
- **Upgrade trigger:** a clean single-spin threshold → buy the **Red Pitaya** for electronic J coupling and the multi-spin network.

### P9 — Volumetric write · **skip on scrappy**

Defer entirely. Not an iteration target without the laser and safety enclosure.

### P10 — Integration · **scrappy dry-run**

Script the owned-gear phases (P0,1,3,4,5,6) into one laptop demo to feel the substrate-unity story before polishing.

---

## 5. The Minimum Scrappy Rig (probably ~$0–50)

If the prototype optical parts and a milligram scale are on hand, the first working array prototype can cost essentially nothing beyond glue and slides:

```
Owned: PicoScope 2204A + Pico NCO + relay mux + Board A/D + cassette plates + PZTs + putty + Kronos + laptop
Salvage: laser pointer, photodiode/phototransistor, watch crystals, vacuum jar
Buy (maybe): a pack of microscope slides (~$8), CA glue (~$5)
```

That rig runs **P0, P1 (slow), P3, P4, P5, P6, P6B** — i.e. rank-N readout, content-addressable search, surface write, PUF, and classical non-separability, the entire near-term scientific claim set — before a single BOM purchase.

**Scrappy control surface:** start with a **single Python script** that wraps the owned drivers (`pico_nco`, `relay_mux`, `picoscope`) and exposes the PFU calls (`match`, `fingerprint`, `write`) — the seed of `tools/cwm_desk/`. The web UI and embedded host (DESK_DEMONSTRATOR.md §3.9) come later; on the scrappy rig the laptop CLI is the whole interface, and "broadcast a query" is one `match()` call that plays the query waveform on the shared rail and scores one capture.

---

## 6. Scrappy → Polished Upgrade Triggers (when to spend)

Spend only when a scrappy result earns it:

| Scrappy result that earns it                | Buy                                                                  | Unlocks                                                  |
| ------------------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------- |
| Hand-scanned rank ≥6, reproducible          | Galvo (DD3)                                                          | fast, live rank-N readout                                |
| Offline ring-down shows usable τ            | **Red Pitaya (DD1)**                                                 | temporal reservoir, real-time feedback, multi-spin Ising |
| Band separation works but amplitudes coarse | Red Pitaya                                                           | clean parallel lock-in                                   |
| Q rises under jar vacuum                    | Real pump (DD12)                                                     | parametric regime                                        |
| Single-spin 0/π threshold seen              | Red Pitaya + forks                                                   | programmable Ising network                               |
| A result worth sharing                      | calibrated parts + run the [protocol](DESK_DEMONSTRATOR_PROTOCOL.md) | repeatability / publication                              |

The **Red Pitaya is the one keystone purchase** — almost every "real-time" upgrade trigger points to it. Everything else can stay scrappy or owned for a long time.

---

## 7. Honest Limits of the Scrappy Path

- **No real-time loop.** The PicoScope block mode is the ~8 Hz B2 bottleneck. Temporal reservoir and active Q-control are _sketchable_ but not _demonstrable_ until the FPGA arrives. Don't claim them from scrappy data.
- **Uncalibrated readout.** Salvaged photodiodes/LDRs have unknown bandwidth and linearity — fine for "the peak is there and the nulls kill it," not for absolute amplitude claims.
- **Manual scanning is slow and drifts.** Hand-positioned spots won't give repeatable rank numbers session-to-session; treat scrappy rank as existence-proof, re-measure under the protocol for a number you'd share.
- **Scrappy results are for iteration, not publication.** The moment a result matters, re-run it under [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md) with logged manifests. Keep the two worlds separate so a junk-drawer artifact never leaks into a shared dataset.

---

## 8. Scrappy Game Demo: Pong on Glass (Level 3 kernel showcase)

**The pitch:** "You're playing Pong against 8 glass plates. Their natural vibrations evaluate the game state and decide where to put the paddle. The glass is thinking."

**What the glass does:** kernel regression — (ball_x, ball_y, velocity) → paddle_y. One broadcast query, one capture, one dot product = one game-AI decision.

**Hardware:** the existing 8-plate cassette with 3 RX PZTs each (24 total readout channels), driven by the Pico NCO, captured by PicoScope. **$0 new parts.**

### 8.1 Architecture summary

**Direct-wire configuration (preferred — no relay switching during gameplay):**

All RX PZTs wire in parallel to one preamp input → PicoScope chA. Multi-tone drive + single FFT extracts all mode amplitudes in one capture. Relays are only used during census (to characterize plates individually); removed from the signal path for gameplay.

```
 PLAYER (keyboard)       BALL PHYSICS (Python)      GLASS AI (kernel)
      │                         │                         │
  paddle_y_left          ball state update          paddle_y_right
      │                         │                         │
      └─────────── web UI (browser canvas) ──────────────┘
                         │
            query = encode(ball_x, ball_y, ball_vx, ball_vy)
                         │
                         ▼
              Pico NCO → shared TX bus → all 8 plates vibrate
                         │
              ALL RX PZTs wired direct to preamp → PicoScope chA
                         │
              ONE FFT capture → extract amplitudes at all known mode freqs
                         │
              gradient y = [y₁, y₂, ..., y_k]  (k = usable modes, ~37)
                         │
              paddle_y_right = w · y  (one dot product, k floats)
```

**Signal path:** PZTs (parallel) → preamp → PicoScope chA. No relay contacts, no switching transients, shortest possible analog path. Lower noise floor than relay-muxed configuration.

### 8.2 Why it works on existing gear

| Resource     | What you have                          | What Pong needs                                          |
| ------------ | -------------------------------------- | -------------------------------------------------------- |
| Plates       | 8 in cassette (diversified, 3 RX each) | 8 plates (sufficient — function is simple)               |
| Relay boards | 16 + 8 = 24 channels                   | **Not needed during gameplay** — only for initial census |
| Pico NCO     | multi-tone drive                       | Encodes game state as tone amplitudes                    |
| PicoScope    | FFT capture (chA)                      | One capture per frame (direct-wire, no mux)              |
| Preamp       | Board A/D                              | Sums all PZTs → clean signal to PicoScope                |
| Host         | laptop + Python                        | Game loop, physics, display, readout weights             |
| Display      | browser                                | Canvas: ball + two paddles                               |

**Frame rate (direct-wire):** 1 capture (10 ms) + processing (5 ms) = **15 ms per frame ≈ 66 fps.** Real-time Pong with no relay switching. The glass AI responds in one acoustic cycle.

**Why eliminate the relay?** During gameplay you never need to isolate a single plate. The FFT separates responses spectrally — that's what Q-factor isolation gives you for free. The relay only adds contact resistance (~0.1–1 Ω per contact, variable) and switching transients. Removing it gives a cleaner, faster, simpler signal path.

### 8.3 Step-by-step build (worklist format)

#### Step 1 — Census (relay-isolated, one-time characterization)

**Objective:** Identify all usable mode frequencies across the cassette. This step uses relays to characterize each plate individually. After census, relays are removed from the signal path.

**Procedure:**

1. Connect the 8-plate cassette (lab diary 2026-04-12 configuration) with relays in circuit.
2. For each of the 24 channels (relay 1–24), drive a broadband sweep via Pico NCO (5–200 kHz, 200 Hz steps, 40 ms dwell).
3. Capture and record all mode peaks per channel (frequency, amplitude, Q estimate).
4. Build the mode map: list of (plate_id, rx_position, frequency, amplitude, Q) for all detected modes.
5. Identify usable modes: peak amplitude > 10 dB above noise floor, Q > 50, no harmonic conflicts.
6. Check for collisions: any two modes within 500 Hz of each other (mode-width at Q=200) → flag as ambiguous.

**Success:** ≥ 30 non-colliding usable modes identified across the 8 plates.
**Time:** 1 hour.

#### Step 2 — Direct-wire and validate multi-tone readout

**Objective:** Remove relays from signal path; confirm multi-tone FFT resolves all modes simultaneously.

**Procedure:**

1. Disconnect relay mux from RX path.
2. Wire all RX PZTs in parallel to preamp input (solder or screw-terminal bus bar → preamp → PicoScope chA).
3. Drive a multi-tone burst containing ALL usable mode frequencies from the census (k tones, ~37 expected).
4. Capture single FFT (PicoScope block mode, 10 ms window, 100 Hz bin resolution).
5. Extract amplitude at each known mode frequency bin.
6. Compare to single-plate baselines from Step 1:
   - Each mode amplitude within ±3 dB of its relay-isolated value → PASS
   - Check for IMD products at f₁±f₂ bins → must be < -30 dB relative to signal

**Success:** ≥ 80% of modes match relay-isolated baselines within ±3 dB; no significant IMD.
**Kill:** Widespread amplitude loss or IMD products within 10 dB of signal → capacitive loading issue or nonlinearity. Fix: add buffer op-amp (~$2), or reduce to fewer PZTs per bus (use relays to create 2–3 port groups instead of one).
**Time:** 1 hour.

**After this step, relays stay disconnected for all remaining steps.** The direct-wire path is the gameplay path.

#### Step 3 — Build the kernel matrix K (direct-wire, multi-tone)

**Objective:** Characterize the gradient structure of the array on the simplified direct-wire path.

**Procedure:**

1. Define 8 "canonical queries" — one per plate, each driving that plate's strongest tag mode at a fixed reference amplitude via the Pico NCO.
2. For each canonical query $q_j$ (j = 1..8):
   a. Drive via shared TX bus (single tone).
   b. Capture ONE FFT on direct-wire chA → extract amplitude at ALL k usable mode frequencies.
   c. Record as row $j$ of K ∈ ℝ⁸ˣᵏ (where k ≈ 37).
3. Expand: define 16 "interpolated queries" (blends of two canonical queries — multi-tone, 50/50 amplitudes). Capture response for each → K_blend ∈ ℝ¹⁶ˣᵏ.
4. Full K = vertcat(K_short, K_blend) ∈ ℝ²⁴ˣ³⁷.
5. SVD: confirm rank ≥ 8, report condition number.
6. Heatmap visualization: confirm structure and smooth gradients.

**Success:** K has rank ≥ 8, condition number < 50, no dead rows.
**Kill:** rank < 4 ⇒ insufficient spectral diversity; plates too similar.
**Time:** 30 minutes (24 queries × 1 capture each × 15 ms = sub-second data collection; rest is scripting).

#### Step 3 — Define the Pong game

**Objective:** Implement ball physics and player input in Python.

**Procedure:**

1. Create `tools/cwm_desk/pong.py`:

```python
import numpy as np

class PongGame:
    COURT_W, COURT_H = 8, 8  # grid units

    def __init__(self):
        self.ball_x, self.ball_y = 4, 4
        self.ball_vx, self.ball_vy = 1, 1  # +1 or -1
        self.paddle_left = 4   # player (0–7)
        self.paddle_right = 4  # glass AI (0–7)
        self.score_left = 0
        self.score_right = 0

    def state_vector(self):
        """Encode game state as 4 values normalized to [0, 1]."""
        return np.array([
            self.ball_x / (self.COURT_W - 1),
            self.ball_y / (self.COURT_H - 1),
            (self.ball_vx + 1) / 2,   # 0 or 1
            (self.ball_vy + 1) / 2,   # 0 or 1
        ])

    def step(self):
        """Advance ball one cell. Handle bounces and scoring."""
        # Bounce off top/bottom walls
        next_y = self.ball_y + self.ball_vy
        if next_y < 0 or next_y >= self.COURT_H:
            self.ball_vy *= -1
            next_y = self.ball_y + self.ball_vy

        # Advance
        self.ball_x += self.ball_vx
        self.ball_y = next_y

        # Left wall: check player paddle
        if self.ball_x < 0:
            if abs(self.ball_y - self.paddle_left) <= 1:
                self.ball_vx = 1  # bounce
                self.ball_x = 0
            else:
                self.score_right += 1
                self._reset_ball()

        # Right wall: check glass paddle
        if self.ball_x >= self.COURT_W:
            if abs(self.ball_y - self.paddle_right) <= 1:
                self.ball_vx = -1  # bounce
                self.ball_x = self.COURT_W - 1
            else:
                self.score_left += 1
                self._reset_ball()

    def _reset_ball(self):
        self.ball_x, self.ball_y = 4, 4
        self.ball_vx = 1 if np.random.rand() > 0.5 else -1
        self.ball_vy = 1 if np.random.rand() > 0.5 else -1
```

2. Test standalone: run 100 steps with random paddle inputs → confirm scoring works.

**Success:** game logic runs, ball bounces, scores increment.
**Time:** 30 minutes.

#### Step 4 — Define the state → query encoder

**Objective:** Map Pong game state (4 values) to a Pico NCO drive waveform.

**Procedure:**

1. The state vector is 4 floats in [0, 1]. Encode as drive amplitudes on 4 of the plates' tag modes:
   - ball_x → amplitude on plate 1's tag mode
   - ball_y → amplitude on plate 2's tag mode
   - ball_vx → amplitude on plate 3's tag mode
   - ball_vy → amplitude on plate 4's tag mode
2. Drive waveform = multi-tone: `NCO F1:<f_plate1> AMP:<ball_x>`, etc. (or use PicoScope AWG for a true multi-tone burst).
3. If the Pico NCO can only drive one frequency at a time: use time-division — drive each tone sequentially for ~5 ms each (total ~20 ms per query). This reduces frame rate slightly but works.
4. Alternative (simpler): encode state as a SINGLE frequency by mapping the 4D state to a 1D index → frequency. E.g., state index = ball_x × 64 + ball_y × 8 + ball_vx × 2 + ball_vy → one of 256 frequency values (each a unique drive tone). Simpler but wastes the multi-tone advantage.

**Recommended approach for scrappy:** single-tone encoding (option 4). Define 256 evenly spaced frequencies across the bandwidth (e.g., 30–150 kHz in 470 Hz steps). Each game state maps to one frequency. Broadcast that frequency → each plate responds based on how close it is to one of its modes.

**Success:** 256 distinct queries defined; spot-check 10 → confirm different states produce different gradient responses.
**Time:** 1 hour.

#### Step 5 — Generate training targets (optimal paddle positions)

**Objective:** Compute what the glass AI SHOULD do for every game state.

**Procedure:**

1. For each of 256 possible states (ball_x 0–7, ball_y 0–7, ball_vx ±1, ball_vy ±1):
   - Simulate the ball forward in time until it reaches the right wall (x = 7)
   - Record where it arrives (y coordinate at the right wall)
   - That's the optimal paddle_y: **intercept the ball where it will be**
2. Store as target vector t ∈ ℝ²⁵⁶ (normalized to [0, 1], representing paddle_y / 7).
3. Spot-check: ball at (6, 3) moving right → target ≈ 3. Ball at (0, 7) moving right with vy=-1 → target ≈ 0 (bounces down during transit).

```python
def compute_optimal_paddle(state):
    """Simulate ball forward to right wall, return y-intercept."""
    x, y, vx, vy = state
    if vx < 0:
        # Ball moving away — predict when it returns
        # Simplification: aim for center (fallback)
        return y  # or 4 (center)
    while x < 7:
        x += vx
        y += vy
        if y < 0: y, vy = -y, -vy
        if y > 7: y, vy = 14 - y, -vy
    return y
```

**Success:** 256 targets computed, all in [0, 7], visually sensible.
**Time:** 15 minutes.

#### Step 6 — Collect physical kernel responses (training data)

**Objective:** For each of 256 game states, broadcast the encoded query and capture the multi-mode gradient (direct-wire, one FFT per state).

**Procedure:**

1. Script the full collection loop:
   ```python
   K = len(usable_modes)  # ~37 from census
   Y = np.zeros((256, K))
   for idx in range(256):
       state = index_to_state(idx)
       query_freq = encode_state_to_frequency(state)
       pico_nco.drive(query_freq, amplitude=REFERENCE)
       time.sleep(0.010)  # one capture window
       fft = picoscope.capture_fft()  # single FFT, direct-wire chA
       for m, mode_freq in enumerate(usable_modes):
           Y[idx, m] = extract_amplitude(fft, mode_freq)
   ```
2. Total time: 256 states × 15 ms (drive + capture) = **~4 seconds.** No relay switching.
3. Normalize Y: zero-mean, unit-variance per column.
4. Check: SVD of Y → effective rank. Must be ≥ 6 for Pong to work.

**Success:** Y collected (256 × k), rank ≥ 6, no NaN/dead modes.
**Kill:** rank < 4 ⇒ modes are too correlated; plates lack diversity.
**Time:** 15 minutes (mostly scripting; capture itself is 4 seconds).

#### Step 7 — Train the readout weight vector

**Objective:** Learn w such that w · y ≈ optimal paddle_y.

**Procedure:**

1. Ridge regression:
   ```python
   from sklearn.linear_model import Ridge
   model = Ridge(alpha=0.01)
   model.fit(Y, targets)
   w = model.coef_  # shape: (K,) where K ≈ 37
   bias = model.intercept_
   ```
2. Evaluate on training data:
   - Predicted: ŷ = Y @ w + bias
   - RMSE: sqrt(mean((ŷ - targets)²))
   - Target RMSE < 1.0 (within 1 grid cell of optimal — the paddle has ±1 tolerance anyway)
3. Cross-validate: leave out 32 random states, train on 224, predict on held-out 32. Report CV RMSE.
4. Visualize: scatter plot of predicted vs actual paddle position. Should cluster along diagonal.

**Success:** RMSE < 1.0 on training, < 1.5 on cross-validation (paddle within ±1 cell of optimal).
**Kill:** RMSE > 3.0 (paddle essentially random) ⇒ kernel doesn't resolve the state space; try multi-tone encoding instead of single-tone.
**Time:** 10 minutes.

#### Step 8 — Wire the game loop (real-time play)

**Objective:** Close the loop: human plays left paddle, glass plays right paddle, ball moves.

**Procedure:**

1. Create the main game loop in `tools/cwm_desk/pong_live.py`:

```python
import time
import numpy as np
from pong import PongGame

game = PongGame()
display = WebUI()  # serves canvas via local Flask/FastAPI

while True:
    t0 = time.time()

    # 1. Read player input
    key = display.poll_input()  # W/S or arrow keys
    if key == 'UP' and game.paddle_left > 0:
        game.paddle_left -= 1
    elif key == 'DOWN' and game.paddle_left < 7:
        game.paddle_left += 1

    # 2. Glass AI: query → single FFT → gradient → paddle decision
    state = game.state_vector()
    query_freq = encode_state_to_frequency(state)
    pico_nco.drive(query_freq)
    time.sleep(0.010)  # capture window

    fft = picoscope.capture_fft()  # ONE capture, direct-wire chA
    gradient = np.array([
        extract_amplitude(fft, f) for f in usable_modes
    ])  # shape: (K,) where K ≈ 37

    paddle_target = np.clip(w @ gradient + bias, 0, 7)
    game.paddle_right = int(round(paddle_target))

    # 3. Advance ball
    game.step()

    # 4. Render
    display.draw(game)

    # 5. Frame pacing (~66 fps target = 15 ms/frame)
    elapsed = time.time() - t0
    time.sleep(max(0, 0.015 - elapsed))
```

2. Web UI: minimal HTML5 canvas (8×8 grid, ball = dot, paddles = 3-cell bars, score at top).
3. Run and play. Confirm the glass paddle tracks the ball reasonably.

**Success:** glass paddle intercepts the ball ≥ 60% of the time it reaches the right wall.
**Time:** 2 hours (mostly UI polish).

#### Step 9 — Difficulty modes and adaptive play

**Objective:** Show the glass can play at different skill levels and learn from you.

**Procedure:**

1. **Easy mode:** add noise to gradient before applying w: `paddle_target = w @ (gradient + 0.3 * np.random.randn(24)) + bias`. Glass makes occasional mistakes.
2. **Hard mode:** use the optimal w (from Step 7). Glass plays near-perfectly.
3. **Adaptive mode (the showcase):**
   - Record the player's paddle_y for each state during 20 rallies
   - Train a SECOND weight vector w_player: `w_player = ridge(Y[observed_states], player_paddle_positions)`
   - Now the glass can PREDICT your moves: `predicted_player_y = w_player @ gradient`
   - Display the prediction alongside the actual player position → "The glass knows where you'll go"
4. **Mirror mode (creepy):** the glass plays AS you (using w_player instead of w_optimal). You're playing against your own ghost.

**Success:** adaptive mode predicts player within ±1 cell after 20 rallies.
**Time:** 1 session.

#### Step 10 — Polish for demo

**Objective:** Make it presentable.

1. Title screen in web UI: "PONG ON GLASS — CWM Level 3 Kernel Demo"
2. Stats overlay: "Glass AI accuracy: 73%", "Kernel dimension: 37", "Plates: 8", "Decision time: 15 ms", "66 fps"
3. Mode selector: Easy / Hard / Adaptive / Mirror
4. The demo script:

> "You're playing Pong. Your opponent is 8 glass plates."
>
> "Each frame, the game state — where the ball is, how fast it's moving — gets turned into a sound wave. That sound hits all 8 plates simultaneously. Each plate vibrates differently depending on how well the sound matches its natural resonances. One microphone hears ALL the plates at once — their vibration amplitudes at 37 different frequencies form a 'gradient': a smooth landscape of similarities."
>
> "One dot product later — 15 milliseconds — the glass has decided where to put its paddle. No if-statements. No lookup table. No switching. The glass evaluated the game state by physics, and the decision fell out of the gradient. 66 times per second."
>
> "Watch — it wins. The glass has been trained to play optimally. But here's the real trick: after 20 rallies, it can predict WHERE YOU will move before you move. Same hardware, different readout weights. The glass learned your style."

### 8.3.11 Bonus games (same hardware, different weights)

**Simon (memory test):** Glass plays a sequence of tones (light LEDs in web UI). Player repeats. Glass encodes the history as a multi-tone query → gradient → next-tone-in-sequence via readout. Train on all permutations of length 4–8. Retrain time: 2 minutes.

**20 Questions:** Player thinks of one of 24 items (mapped to 24 channels). Glass asks yes/no questions by driving different query tones. Each answer refines the gradient. After 5–6 questions, glass guesses the item (argmax on refined gradient). No retraining needed — just threshold the gradient.

**Why these matter:** same 24-dim kernel, same w·y readout pattern, completely different cognitive tasks. Demonstrates that the glass is a general-purpose inference substrate, not a Pong-specific trick.

### 8.5 Total effort estimate

| Step                                    | Time            | New parts |
| --------------------------------------- | --------------- | --------- |
| 1. Census (relay-isolated, one-time)    | 1 h             | $0        |
| 2. Direct-wire + multi-tone validation  | 1 h             | $0        |
| 3. Kernel matrix K (direct-wire)        | 30 min          | $0        |
| 4. Pong game logic                      | 30 min          | $0        |
| 5. State→query encoder                  | 1 h             | $0        |
| 6. Training targets                     | 15 min          | $0        |
| 7. Physical data collection (4 seconds) | 15 min          | $0        |
| 8. Train readout (ridge)                | 10 min          | $0        |
| 9. Game loop (live, 66 fps)             | 2 h             | $0        |
| 10. Difficulty/adaptive                 | 1 session       | $0        |
| 11. Polish + demo script                | 1 session       | $0        |
| **Total**                               | **~2 sessions** | **$0**    |

**Critical path:** Steps 1–2 (census + direct-wire validation). If multi-tone readout resolves cleanly on direct-wire, the rest is pure scripting with a 4-second data collection step.

---

### 8.4 Spectral port multiplexing — stacking plates per relay channel

#### The reframe

Stop thinking of relays as "plate selectors." A relay channel is a **spectral port** — it has some set of responsive frequencies determined by whichever plates are wired to it. You don't care which plate produced a resonance. You only need: "at frequency F, port C responds with amplitude A."

This applies to **both** computation levels:

- **HD (Level 2):** drive a tag frequency → read which port responds → address = (port, frequency). More plates per port = more tags per port = larger vocabulary.
- **Kernel (Level 3):** drive multiple tones → capture one FFT per port → extract amplitude at each tone → kernel_dim = N_ports × N_tones. More plates per port = more interesting tones to drive = higher kernel dimension per port WITHOUT additional relay switches.

The relay only moves you between ports. **Within a port, spectral orthogonality (Q-factor) provides 40–60 dB of isolation for free.** The physics does what the relay used to do.

#### Why more-plates-per-port works (both paths)

Wire n plates to one relay channel. Each plate contributes ~5 distinct modes in the working bandwidth (30–150 kHz). The Q-factor (≈ 200) means each mode occupies ~500 Hz at center frequency. That port now has n × 5 usable resonances.

Drive one specific frequency F₇ (which is one plate's mode):

- That plate responds 40–60 dB above the off-resonance floor
- Other plates on the same port: effectively silent at F₇
- Other ports (different plates): also silent at F₇

For multi-tone readout: drive ALL k usable frequencies simultaneously in one burst → capture ONE FFT → extract k amplitudes. No relay switching within a port. **One port, one capture, k features.**

#### Corrected collision math

- Usable bandwidth: 120 kHz (30–150 kHz)
- Mode width at Q ≈ 200: ~500 Hz average
- Available non-overlapping spectral slots per port: 120,000 / 500 = **~240 slots**
- With n modes randomly placed per port, expected intra-port collisions ≈ n² / (2 × 240)

| Plates per port | Modes total (5/plate) | Expected collisions | Usable modes surviving | Efficiency                |
| --------------- | --------------------- | ------------------- | ---------------------- | ------------------------- |
| 4               | 20                    | 0.8                 | ~19                    | 95%                       |
| 8               | 40                    | 3.3                 | ~37                    | 92%                       |
| 16              | 80                    | 13                  | ~67                    | 84%                       |
| 24              | 120                   | 30                  | ~90                    | 75%                       |
| 48              | 240                   | 120                 | ~120                   | 50% (spectral saturation) |

**The real cap is at ~48 plates/port** (where you've filled the spectral space), not 3–4. At 8 plates/port you're still at 92% efficiency. Diminishing returns are gentle until ~24 plates/port.

#### The frame rate revolution

The bottleneck was never codebook size — it was relay switching time. Stacking eliminates relay switches by concentrating information in fewer ports:

```
Frame time = N_ports × (relay_settle + capture_time)
           = P × 15 ms

Kernel dimension = usable_modes_per_port × P
                 (multi-tone drive + single-FFT extraction)
```

| Config        | Ports (P) | Plates/port | Modes/port | Kernel dim                 | Frame time | FPS    |
| ------------- | --------- | ----------- | ---------- | -------------------------- | ---------- | ------ |
| Current (1:1) | 24        | 1           | 5          | 120 (but single-tone → 24) | 360 ms     | 3      |
| Light stack   | 8         | 3           | ~14        | 112                        | 120 ms     | 8      |
| Heavy stack   | 4         | 8           | ~37        | 148                        | 60 ms      | 16     |
| Dense stack   | 2         | 16          | ~67        | 134                        | 30 ms      | **33** |
| Single port   | 1         | 8           | ~37        | 37                         | 15 ms      | **66** |

**Single port with 8 plates: 37-dim kernel at 66 fps from ONE relay position.** No relay switching during gameplay. The relay only moves at setup (to select the active port) — or not at all.

#### Multi-tone readout: the enabling trick

Previously each relay position yielded one amplitude (single-tone query). Multi-tone readout changes the economics:

1. Drive k frequencies simultaneously (composite waveform via AWG or Pico NCO multi-tone mode)
2. Capture one FFT (PicoScope block mode, same 10 ms window)
3. Extract amplitude at each of k frequency bins → k features from ONE capture

This means kernel_dim = k per port — not 1 per port. With 8 plates on a port providing 37 usable modes, you get a **37-dimensional kernel from one relay position, one capture.**

For the DOOM demo (needs 32+ kernel dim for 8 column heights): a single port with 8 plates provides 37 dimensions. **DOOM runs at 66 fps with zero relay switching.**

#### What matters: where stacking helps each path

|                                     | HD (Level 2 — tag lookup)                                          | Kernel (Level 3 — gradient regression)                   |
| ----------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------- |
| **Single-tone, 1 plate/port (old)** | 1 tag per port, 24 ports = 24 vocabulary                           | 1 feature per port, 24 features                          |
| **Single-tone, stacked**            | k tags per port (drive any one tag) → vocabulary = k × P           | Still 1 feature per capture (response at the query freq) |
| **Multi-tone, stacked**             | All k tags readable in one FFT → codebook verification in one shot | k features per port per capture → kernel_dim = k × P     |

**Multi-tone + stacking benefits BOTH paths equally.** The only situation where 1:1 plate-per-channel wins is parallel ADC/FDM hardware where relay switching doesn't exist — making the stacking irrelevant (not harmful, just unnecessary).

#### Where it breaks down

1. **Inter-port collisions (HD path):** Two different ports sharing a mode at the same frequency → ambiguous tag. Census catches this; exclude colliding frequencies from the global HD vocabulary. Stacking INCREASES this risk (more modes globally → more chances of cross-port collision). Mitigation: assign plates to ports to MAXIMIZE spectral distance between ports.
2. **Intermodulation distortion (multi-tone):** Driving many tones simultaneously can create spurious peaks at sum/difference frequencies (f₁ + f₂, 2f₁ - f₂, etc.) that land on other modes' bins. At the low drive amplitudes used here (mV range, linear regime), IMD should be < -40 dBc. Needs bench validation.
3. **Capacitive loading:** Each PZT adds ~1–2 nF. At 8 plates/port (~12 nF), preamp bandwidth rolls off above ~150 kHz. Fine for the working band. At 16+ plates/port, consider a buffer amplifier (~$2 op-amp).
4. **FFT bin resolution:** To resolve modes separated by 500 Hz, you need capture windows ≥ 2 ms (1/500 Hz). Current PicoScope block mode at 10 ms gives 100 Hz resolution — more than sufficient.

#### Procedure: census-based port assignment

No separate enrollment per plate is needed. **The census IS the enrollment:**

1. **Sweep each port** (however many plates are wired to it) across the full bandwidth (30–150 kHz, 100 Hz steps).
2. **Find all peaks** (local maxima > 10 dB above noise floor). Each peak = one usable mode for that port.
3. **Check for cross-port collisions:** if two ports both have a peak within one mode-width (f/Q ≈ 500 Hz) of the same frequency, mark that frequency as ambiguous — don't use it as a tag for either port.
4. **Assign vocabularies:** codebook = all non-ambiguous (port, frequency) pairs.
5. **Check harmonics:** for each mode at f, verify no other port has a mode at 2f, 3f, 4f, 5f (within one mode-width). Flag if so.

You never need to know individual plate identity. The spectral port is the fundamental addressing unit.

#### Practical validation (zero spend, existing hardware)

On the existing 8-plate cassette with 24 relay channels:

1. Pick 2 plates known to have non-overlapping spectra (from prior census).
2. Wire both PZT outputs to one preamp input (parallel — both on relay channel 1).
3. Sweep that port. Confirm you see BOTH plates' peaks — distinct, no smearing, no amplitude loss.
4. Drive a multi-tone burst (both plates' tag modes simultaneously) → capture single FFT → confirm both peaks resolve at expected amplitudes (±3 dB of single-plate baselines).
5. If (4) passes: IMD is low enough. The principle is validated for multi-tone readout.
6. Scale: wire 4 plates to one port. Repeat. This gives you the real capacity ceiling of your specific glass + preamp chain.

**Expected result:** 2-plate port shows 2× the peaks, each retaining its amplitude and Q. Multi-tone drive produces no significant intermodulation products in adjacent bins.

#### Impact on game demos

| Demo          | Original assumption     | With stacking + multi-tone                     | Change                                 |
| ------------- | ----------------------- | ---------------------------------------------- | -------------------------------------- |
| Pong (kernel) | 24 ports, 1 tone, 3 fps | 2 ports × 37 modes = 74-dim, 30 ms, **33 fps** | From turn-based to real-time           |
| DOOM (kernel) | 32 plates, FDM, 125 fps | 1 port × 37 modes = 37-dim, 15 ms, **66 fps**  | Scrappy path achieves DOOM without FDM |
| HD lookup     | 24 tags (1 per port)    | 24 ports × 37 modes = **888 tags**             | 37× vocabulary expansion               |

**DOOM is now achievable on the existing relay hardware** — 8 plates on one port, multi-tone drive, single-FFT readout. The "32 plates + FDM" path becomes the LUXURY option, not the prerequisite.

---

## 9. Cross-References

- Polished build spec + BOM: [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md)
- Repeatable, shareable procedures: [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md)
- Capability ceiling + rungs: [FRONTIER_CEILING.md](FRONTIER_CEILING.md)
- Owned bench hardware detail: [../HARDWARE.md](../HARDWARE.md)
- Prior physical seed (5-plate cassette, 2026-04-12 entry): [LAB_DIARY.md](LAB_DIARY.md)
- Already-specced optical parts (HeNe, FDS100): [../prototypes/prototype_a/README.md](../prototypes/prototype_a/README.md)
- DOOM (32-plate expansion): [DESK_DEMONSTRATOR_DOOM.md](DESK_DEMONSTRATOR_DOOM.md)
- Architecture (§7B — gradient/kernel): [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md)
