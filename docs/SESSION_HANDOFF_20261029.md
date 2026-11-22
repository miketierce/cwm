# Session handoff — Oct 29, 2026 (Plate D, before teardown)

> **Read this first in a fresh session.** It covers where the bench is, what was learned today, the rules we work
> under, and what comes next. Details live in `docs/lab_diary_20261029.md` (§1–15) and `docs/WORKLIST.md` (O3, O5).
> Last commit at handoff: `29d0699` (main, not pushed).

---

## 1. Working rules (standing)

- **Commits:** only with the user's approval. Never push; the user pushes. Report the hash and "not pushed".
  End messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Leave a blank line after the subject.
- **Roles:** the user does all wiring and physical changes and reports each one in a short message. Claude runs the
  NCO and scope, analyses the data, and keeps the dated lab diary (`docs/lab_diary_YYYYMMDD.md`). Give the user
  plain-language summaries. Use they/them for the user.
- **Preregistration discipline:** before any data, write the diary section (question, design, scoring, predictions,
  outcomes). Append a `prereg` event with SHA-256 hashes of the diary and every script involved to the test folder's
  `log.jsonl`. Amendments are allowed only before data, as a dated "Amendment (HH:MM, before any data)" block with a
  `prereg_amendment` log event. Recheck the hashes before scoring. Label post-hoc analysis as post hoc, and never
  turn a failed preregistered gate into a pass after the fact; rerun under a new preregistration instead (as in §12).
- **Frozen tools:** `tools/k_eff_ft1_capture.py` (sha256 `05f3c36c…`) and `tools/k_eff_ft1_superposition.py`
  (`cce97f35…`) must stay unchanged. New tests import from them rather than editing them.
- **Raw data:** goes in `data/raw/k_eff/<test>/` (gitignored), with metadata and logs in `data/results/k_eff/<test>/`.
  After each test, back up the raw data as a tar in iCloud (`~/Library/Mobile Documents/com~apple~CloudDocs/CWM_backups/k_eff/`),
  verify it against the capture-time hashes, and note the backup in the diary.
- **Shell:** use absolute paths and avoid `cd`. In zsh, don't start an `echo` argument with `=`.

## 2. Bench state at handoff (22:15, Oct 29)

- **Plate D:** 100×100×1 mm fused silica, 22 g, vertical in a foam enclosure. Untouched since the O5 runs. **Teardown is planned for Oct 30.**
- **Transducers** (10 mm PZT-5A, cyanoacrylate bond):
  - RX at top centre → OPA2134 ×48 preamp → **Ch A**.
  - TX1 at bottom centre on NCO CH1 (GP2), through 220 Ω.
  - TX2 in the SW corner on NCO CH2 (GP3), through 220 Ω. **Ch B is on the TX2 junction** (PZT side of the 220 Ω).
  - Spare NE/NW PZTs present but unconnected. A dummy RX PZT exists for ELECTRICAL_ONLY.
  - **Measured terminal capacitance: ≥ 4.1 nF** (about 650 Ω at 60 kHz), not the nominal 1.2 nF (§11, §14).
- **Pico NCO:** firmware **v2.1** (`tools/pico_nco/main.py`, sha256 `84c9a2c1…`, commit `00185b6`), port `/dev/cu.usbmodem113401`.
  - **State:** off, with pins driven LOW (`IDLE:LOW`), and CH2 at duty 100‰.
  - **Flashing:** `.venv/bin/mpremote cp main.py :main.py`, then reset. The v2.0 backup was in the session scratchpad, and v2.0 is also in git history.
  - **Commands:** `F1:`/`F2:<Hz>`, `A<ch>:<‰>`, `PH1:`/`PH2:` (`A` and `PH` are stored only when all channels are off), `Foff` (stop, pins driven LOW), **`Fz`** (stop, pins high-Z; replies `DDS:Z`), `STATUS` (now with `IDLE:Z|LOW`), and `TEMP`. CH2 replies `DDS2:<f>`.
  - **Latencies:** on a HIGH pin, `Foff` drives it LOW about 0.13 ms after the PIO stop. `Fz` releases the pins about 0.20 ms (0.14–0.33) after it.
- **PicoScope 2204A:** 8-bit, timebase 7 = 781.25 kS/s. With both channels on, the maximum block is **3968 samples per channel** (8064 needs one channel). There is no streaming. Both channels run at ±5 V for ringdowns (39 mV per step).
- **Also on the bench:** the 16-relay board and Nano (`tools/relay_mux.py`), unused today.

## 3. What Oct 29 established

| Test | Diary | Outcome |
|---|---|---|
| **O3: direct ringdown and ring-up** | §1–4 | Passed. Ringdown 9/10 modes and ring-up 8/10 within 20% of τ = Q/πf₀. Ringdowns run a median 9% short of the linewidth. Doublets near 90.5 and 97 kHz. Q from clean ringdowns ≈ 170–640. |
| **Two-TX null ringdown** | §5–8 | A receiver null is not a modal null. At 58.5 kHz (−44 dB null) the plate still rang at 47%, with two components (τ 0.90 and 2.21 ms). At 90.6 kHz: two modes 44 Hz apart. Superposition held within 2%. |
| **O5: TX termination** (Part A + confirmatory rerun) | §9–15 | Confirmed **small**. τ_open/τ_grounded median 1.065 (−1% to +15% over 4 modes), reproduced to within 0.01. Opening the TXs raises the free-decay frequency by 21–40 Hz (218–439 ppm), reversibly. Part A's gate failed only because it assumed 1.2 nF. |

**Conclusions carried forward:**
- **Q is mechanical.** Electrical loading through the TX terminations is minor. The May "intrinsic Q ≈ 2,000–2,760" (fits with R² < 0.1) is ruled out for the terminations. The remaining suspects are PZT material and bond loss and the supports (Part C).
- **The circuit (BVD) estimate from junction voltages** (`termination_20261029/bvd_o3.py`) gets the reactive effects right (frequency shift, Ch B ratio) but overestimates the loss share by about 2×. Prediction P3 based on it failed.
- **Interference "erase" changes the readout, not the glass.** The rewritable layer sits in drive settings and readout.
- **CAM recheck (earlier today):** the June 29 partial-query result did not hide vx and vy. The dropout floor came from the axis windows, and a fair digital baseline beats the glass.

## 4. Next steps

**Tomorrow (Oct 30), after the teardown:**
1. **Part C, support loss.** Ringdown with the plate out of the foam on minimal supports or free-hanging (the May 1 design: nylon at the nodal points, about 22% in from the edges), with the PZT leads kept connected. Compare it with the in-foam grounded τ, window by window.
   - **Needs a new preregistration before any data.** Reuse `termination_20261029/term_capture.py` with a new `--setup` label. `score_term.compare_setups` gives the grounded-τ ratio against the first run.
   - **Note:** the grounded-only comparison is what matters; the `Fz` arm can stay as a repeat of O5. The confirmation threshold of 3 in `score_term.py` is wrong for this plate; use `score_confirm.py`'s 1.3 plus the discharge check.
   - **Wiring needed:** Ch A on the preamp, and Ch B on the TX2 junction, as now.
2. **Mass write (WL-A2 / FRONTIER R1, the top open gate)** once the plate is reachable:
   - **Doses and positions:** wax putty at 10, 25 and 50 mg, at 3–4 positions, in a bare/write/bare cycle.
   - **Readout:** f₀/τ shifts by zoom fits plus O3 ringdowns. Pass: a shift above 3σ at ≥ 10 mg that is position-dependent and reversible.
   - **Folds in:** TB-G1/G2 (`PHYSICALLY_WRITTEN_TEMPLATE_BANK_WORKLIST.md`), sidebar S9 (doublet splitting), and REPRESENTATION TP-04 (post-perturbation relaxation).
   - **Needs:** wax (not hardened silicone), a 0.001 g scale, a placement grid, and photos.
   - **Thermometer context:** undisturbed 5–13 ppm, handling tens of ppm, about 1000 ppm per 50 mg (earlier estimate).
3. **Optional, if the spare PZT leads are reachable:** a resistor of about 1/(ωC0) across a spare. Recompute it with the measured 4.1 nF (≈ 400–650 Ω, not 1.5 kΩ) to test electrical shunt damping. It needs its own preregistration.

**Offline backlog:**
- F10 / WL-B2 redistribution from the FT-1 raw spectra.
- O4: the ±1.5 kHz doublet sweeps (recorded on Oct 27, not yet analysed).
- WL-A1 / WL-A4 closeouts.
- FT-2 ablation.
- **Correct any docs that still use "1.2 nF, about 2 kΩ at 60 kHz" for these PZTs.**

**Pending on the user:**
- **O9, the NSF Phase I deadline (Nov 4):** check status (`docs/nsf-november-2026-application` branch).
- **O11, the fixture rework** (isolated chamber, relay-switched RX live/dummy, fixed supports, anchored leads). When the user reports the rebuild, the work is: relay control (Nano and `relay_mux.py`, or Pico firmware), relay qualification (feedthrough in both positions), the handling test, and a new preregistered FT-1 repeat series.

**Skip** (from the review of all prior work): NARMA/O6 on this bench, FT-2+/FT-3P before the rework, parametric schemes (Q too low), cross-session or multi-plate PUF, E4/T5.4/T5.5.

## 5. Reusable methods and gotchas

- **Ringdown capture** (`data/results/k_eff/ringdown_20261029/ring_capture.py`, imported by later tests):
  - **Ring-up:** a Ch B rising trigger at 1 V with 10% pre-trigger.
  - **Ringdown:** a free-running block with the stop command sent after an adaptive delay; the stop is located on Ch B as the last pulse plus half a period. Kept if it lies 0.5–2.0 ms into the 5.08 ms block.
  - **Scope start offset:** −7.8 to −7.9 ms when a ring-up block precedes the ringdown; +2.87 ms (wider spread) without one. The adaptive delay copes either way. The O3 delay settled at 9.05 ms (default `--delay-ms`).
- **Scoring** (`score_ring.py`):
  - **Envelope:** 0.4 ms Hann at the drive frequency.
  - **Fits:** ringdown z = D e^{st} from 0.3 ms after the stop; ring-up z = C + D e^{st}.
  - **Fit end:** the larger of 5× QUIET noise and 3 ADC steps (117 mV at ±5 V).
  - **Usable:** R² ≥ 0.9.
- **Raw arrays:** `ring_A`/`ring_B` may be int16 (or int8 × 256). Always convert with `x.astype(int32) * (256 if int8 else 1) * mv_per_count`.
- **TX junction after the stop:** grounded, it rings at 26–50 mV (TX2's own motional current through 220 Ω), well above the 2.5 mV floor. When open, a stop that catches the pin HIGH leaves the PZT at about 3.3 V, discharging through Ch B's 1 MΩ (τ ≈ 4.1 ms). That gives a direct capacitance measurement.
- **Zoom fits:** `overnight_20261026/fit_zoom.py`. The 97 kHz window's fit is often unusable (doublet), so the drive falls back to the zoom peak. 106 kHz sits right at the R² cut.
- **Windows:** F2 is 73.5, 90.5, 97, 105, 106 and 116.5 kHz. F1 is 45, 58.5, 90.5, 97, 99.5 and 103 kHz.

## 6. File map

- **Diaries:** `docs/lab_diary_20261029.md` (today, §1–15). Earlier this month: `docs/lab_diary_20261021.md` (Plate D build), `…1023` (linearity), and `…1026`–`…1028` (FT-1 sessions S1–S3, overnight stability, range test, handling map, harmonic-grid pilot).
- **Plans:** `docs/WORKLIST.md` (O1–O11; O3 and O5 marked done), `docs/FULL_POTENTIAL_WORKLIST.md` (WL-A/B), `docs/FRONTIER_CEILING.md` (ladder R0–R5), `docs/K_EFF_FAST_TRACK.md`, `paper/CLAIMS_STATUS.md`.
- **Today's tests:** `data/results/k_eff/ringdown_20261029/`, `nullring_20261029/` and `termination_20261029/`.
  - In the termination folder: `term_capture.py`, `score_term.py`, `score_confirm.py`, `bvd_o3.py`, `posthoc_term.py`, and their result JSONs.
- **iCloud backups (today):** `CWM_ringdown_raw_20261029.tar`, `CWM_nullring_raw_20261029.tar` and `CWM_termination_raw_20261029.tar`.
- **Full session transcript** (for exact past outputs): `~/.claude/projects/-Users-Mike-Code-wcfoma/80491414-4e96-4862-9296-2746cc4c42bf.jsonl`.
