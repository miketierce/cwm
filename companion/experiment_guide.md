# CWM Macro-Scale Experiment Guide

**Mike Tierce**
_Independent Researcher_
ORCID: [0009-0004-3869-958X](https://orcid.org/0009-0004-3869-958X)
Repository: [github.com/miketierce/cwm](https://github.com/miketierce/cwm)

**Companion to:**

- **Paper I:** "Coherent Wave Memory: Wave-Based Storage and Computation in Acoustic Glass Resonators"
- **Paper II:** "Advanced Encoding and Rewritability Techniques for Coherent Wave Memory"

---

## About This Document

This companion document contains the complete macro-scale experiment guide, full-scale illustration plates, and printable data worksheets for reproducing the Coherent Wave Memory (CWM) prototype experiments described in Section 4 of Paper I.

The guide is self-contained: every component is listed with a direct purchase link, every procedure is numbered for reproducibility, and every known failure mode includes a tested mitigation. A middle school science teacher with no acoustics background should be able to build the prototype, complete all experiments, and contribute publishable data within a single school week. See Section 4 of Paper I for the theoretical context behind each measurement.

_All quantitative claims are computed from first-principles simulation code (48 modules, 2,253 automated tests, all passing) and independently validated by finite element analysis. No curve fitting, no adjusted parameters, no post-hoc corrections. Repository: github.com/miketierce/cwm._

---

## Appendix D: Macro-Scale Experiment Guide

_This appendix provides step-by-step instructions for replicating the macro-scale prototype experiments of Section 4 of Paper I. The guide is designed to be self-contained: every component is listed with a direct purchase link, every procedure is numbered for reproducibility, and every known failure mode includes a tested mitigation. A middle school science teacher with no acoustics background should be able to build the prototype, complete all experiments, and contribute publishable data within a single school week. See Section 4 of Paper I for the theoretical context behind each measurement._

**The glass harmonica connection.** Every experiment in this appendix is a direct descendant of a musical instrument that predates the transistor by centuries. A glass harmonica—tuned wineglasses played by rubbing a wet finger around the rim—demonstrates every principle of CWM in audible form: glass resonators with eigenfrequencies set by geometry, mass perturbation tuning via water level, continuous-wave excitation via stick-slip friction, and spectral readout by the human ear. In 1761, Benjamin Franklin attended a glass harmonica concert in London and built an improved version: the _glass armonica_, which mounted the bowls on a rotating spindle so a performer could vary finger pressure, position, and contact duration in real time. Same glass, same physics, same resonant modes—but now reconfigurable. This appendix walks the same path: Experiments 1–6 build and characterize a fixed resonator (the harmonica); Experiment 7 demonstrates continuous-wave precision readout (bowing vs. ringing); Experiment 8 demonstrates rewritable encoding with water drops (the armonica); and Experiments 9–11 demonstrate packed-array operations—associative recall, nearest-neighbor search, and in-situ Boolean computation. Experiments 12–14 demonstrate real-world applications: a password vault, visual image search, and a content-addressable lookup table—each leveraging polysemic readout to multiply effective capacity by 4×.

### D.1 Complete Bill of Materials

The core BOM from Paper I §4.2 is expanded below with recommended quantities (extras for breakage and controls), supplier links, and additional items needed for failure-mode mitigations. All prices are approximate as of 2026 and may vary.

**Table D.1: Core Components**

| #   | Component                               | Specification                                                     | Qty     | Est. Cost        | Amazon Link                                                                                             |
| --- | --------------------------------------- | ----------------------------------------------------------------- | ------- | ---------------- | ------------------------------------------------------------------------------------------------------- |
| 1   | Borosilicate glass stirring rods        | 6 mm dia × 150 mm (5.9″), rounded ends, Boro 3.3                  | 15-pack | ~\$8             | [PATIKIL 15 Pcs, 5.9″ × 6 mm](https://www.amazon.com/dp/B0F93VD85L?tag=cwmt-20)                         |
| 2   | Borosilicate glass stirring rods (alt.) | 6 mm dia × 200 mm (7.9″), Boro 3.3—cut to 150 mm if needed        | 10-pack | ~\$9             | [EISCO 10PK, 7.9″ × 6 mm](https://www.amazon.com/dp/B07DKPF1RT?tag=cwmt-20)                             |
| 3   | Piezoelectric discs with leads          | 25 mm dia, PZT ceramic, pre-soldered 4″ wire leads                | 15-pack | ~\$7             | [E-outstanding 15 PCS](https://www.amazon.com/dp/B08R581G3H?tag=cwmt-20) (labelled 10 mm; actual 25 mm) |
| 4   | Piezoelectric discs (alt.)              | 25 mm dia, PZT, bare discs (solder leads yourself)                | 10-pack | ~\$6             | [uxcell 10 Pcs](https://www.amazon.com/dp/B07RK2V1P2?tag=cwmt-20) (labelled 10 mm; actual 25 mm)        |
| 5   | USB oscilloscope + waveform generator   | PicoScope 2204A, 10 MHz BW, 2-ch, built-in AWG, PS7 software      | 1       | ~\$192           | [PicoScope 2204A](https://www.amazon.com/dp/B00GZMRZ3M?tag=cwmt-20)                                     |
| 6   | Cyanoacrylate glue (super glue)         | Medium viscosity, precision tip, gel formula                      | 1–2     | ~\$5–\$10        | [Loctite Ultra Gel Control, 4 g](https://www.amazon.com/dp/B00ELV2D0Y?tag=cwmt-20)                      |
| 7   | Moldable silicone putty earplugs        | Mack's Pillow Soft, moldable silicone putty (perturbation masses) | 1 pack  | ~\$9             | [Mack's Pillow Soft, 8 Pair](https://www.amazon.com/dp/B00SYEHC64?tag=cwmt-20)                          |
| 8   | BNC cables (male–male, 50 Ω)            | 1 m length, for Picoscope connection                              | 2–4     | ~\$10–\$20       | Included with PicoScope kit; 4 recommended for multi-rod experiments (Exps 9–14)                        |
|     | **Core materials (without scope)**      |                                                                   |         | **~\$38–\$54**   |                                                                                                         |
|     | **Core materials (with PicoScope)**     |                                                                   |         | **~\$230–\$246** |                                                                                                         |

**Table D.2: Mitigation and Measurement Accessories**

| #   | Component                              | Purpose (failure mode addressed)                                                                   | Qty            | Est. Cost      | Source                                                                                                  |
| --- | -------------------------------------- | -------------------------------------------------------------------------------------------------- | -------------- | -------------- | ------------------------------------------------------------------------------------------------------- |
| 9   | Cardboard (from any box)               | Rod-support dividers for insulated box (FM 1: anchor loss)                                         | 2 pieces       | free           | Any shipping box or cereal box                                                                          |
| 10  | Digital thermometer, 0.1 °C resolution | Thermal drift monitoring (FM 3)                                                                    | 1              | ~\$12          | Any kitchen/lab thermometer with 0.1 °C readout                                                         |
| 11  | Insulated shipping box with foam liner | Thermal enclosure (FM 3: drift isolation); interior ≥ 7″ × 5.5″ × 6.5″ (see dimension guide below) | 1              | ~\$10          | [CH-BOX Small Insulated Box, 7.1″ × 6.2″ × 10″ outer](https://www.amazon.com/dp/B0BJ21YFNN?tag=cwmt-20) |
| 12  | Milligram precision scale (0.001 g)    | Weighing perturbation masses                                                                       | 1              | ~\$20          | Amazon search: "milligram scale 0.001g"                                                                 |
| 13  | Metric ruler, mm scale                 | Positioning masses along rod                                                                       | 1              | ~\$3           | Any school supply                                                                                       |
| 14  | Isopropyl alcohol, 91 %+               | Cleaning glass rods before assembly                                                                | 1 bottle       | ~\$4           | Any pharmacy                                                                                            |
| 15  | Safety glasses                         | Eye protection (glass rods can snap)                                                               | 1 per person   | ~\$3           | Any hardware store                                                                                      |
| 16  | Masking tape                           | PZT alignment jig (FM 2: centering)                                                                | 1 roll         | ~\$4           | Any hardware store                                                                                      |
| 17  | Fine-tip permanent marker              | Marking positions on rod                                                                           | 1              | ~\$2           | Any office supply                                                                                       |
| 18  | Soft lint-free cloth                   | Handling and cleaning glass                                                                        | several        | ~\$2           | Any store                                                                                               |
| 19  | Acetone (nail polish remover)          | Emergency super-glue skin-bond release                                                             | 1 small bottle | ~\$3           | Any pharmacy                                                                                            |
| 20  | Plastic transfer pipettes (3 mL)       | Placing water drops for Exp. 8 (rewritability)                                                     | 1 pack         | ~\$4           | Amazon search: "plastic transfer pipettes"                                                              |
| 21  | Small bowl of water                    | CW excitation via wet finger (Exp. 7)                                                              | —              | free           | Tap water                                                                                               |
| 22  | Hollow punch set (5–13 mm)             | Clean 7 mm pinholes in cardboard dividers                                                          | 1 set          | ~\$10          | [Jmuiiu 8 Pcs, 5–13 mm](https://www.amazon.com/dp/B0C6JSMSS8?tag=cwmt-20)                               |
| 23  | Assorted sandpaper (120–3000 grit)     | _(Optional)_ Lapping rounded rod ends flat for PZT bond                                            | 1 pack         | ~\$7           | [3M Assorted Grit Sandpaper, 5-pack](https://www.amazon.com/gp/product/B001449TPS?tag=cwmt-20)          |
|     | **Accessories subtotal**               |                                                                                                    |                | **~$77–$84**   |                                                                                                         |
|     | **Grand total (without scope)**        |                                                                                                    |                | **~$116–$131** |                                                                                                         |
|     | **Grand total (with PicoScope)**       |                                                                                                    |                | **~$308–$323** |                                                                                                         |

**Table D.3: Relay Multiplexer Kit (Topology B, optional)**

For per-rod readout with 4–8 rods, the relay multiplexer kit adds a second PZT per rod and an Arduino-controlled relay to switch individual sense PZTs onto Channel A. No soldering required — all connections use screw terminals, DuPont jumper wires, and twist splices.

| #   | Component                          | Specification                                                     | Qty    | Est. Cost | Amazon Link                                                              |
| --- | ---------------------------------- | ----------------------------------------------------------------- | ------ | --------- | ------------------------------------------------------------------------ |
| 24  | 8-channel relay module             | 5V opto-isolated, screw terminals, high/low trigger               | 1      | ~\$11     | [VOGURTIME 8-ch](https://www.amazon.com/dp/B07XM5GVWJ?tag=cwmt-20)       |
| 25  | Arduino Nano clone (CH340)         | Type-C USB, ATmega328P; powers relay + provides GPIO              | 1      | ~\$10     | [AITRIP 2-pack](https://www.amazon.com/dp/B0B42GRG15?tag=cwmt-20)        |
| 26  | DuPont jumper wires (F-to-F)       | 40-pin, 10 cm; connects Arduino to relay header pins              | 1 pack | ~\$5      | [40pcs F-to-F](https://www.amazon.com/dp/B0BRTKTV64?tag=cwmt-20)         |
| 27  | Stranded silicone wire (26 AWG)    | 6-color, 32.8 ft each; extends PZT leads to relay screw terminals | 1 set  | ~\$11     | Amazon search: "26 AWG stranded silicone wire 6 colors"                  |
| 28  | Electrical tape                    | Secures twist-splice wire joints                                  | 1 roll | ~\$2      | Any hardware store                                                       |
| 29  | Precision screwdriver set          | Small flathead for relay screw terminals                          | 1 set  | ~\$6      | [11 Pcs Set](https://www.amazon.com/dp/B0FLDH6FF4?tag=cwmt-20)           |
| 30  | Extra PZT discs with leads (10 mm) | Second PZT per rod (drive end); 15-pack                           | 1 pack | ~\$7      | [E-outstanding 15 PCS](https://www.amazon.com/dp/B08R581G3H?tag=cwmt-20) |
|     | **Relay kit subtotal**             |                                                                   |        | **~$52**  |                                                                          |

**Table D.4: 2D Plate Extension (Experiments 15–16)**

For the Chladni plate experiments, replace rods with a fused-quartz glass plate. The plate reuses your existing PZT discs, BNC cables, and PicoScope from the core BOM. All items below are add-ons.

| #   | Component                    | Specification                                           | Qty    | Est. Cost   | Amazon Link                                                                      |
| --- | ---------------------------- | ------------------------------------------------------- | ------ | ----------- | -------------------------------------------------------------------------------- |
| 31  | Fused-quartz plate (primary) | 100 × 100 × 1 mm, Lab UV-Vis grade, both faces polished | 1      | ~\$16       | [Optical Glass, Square Quartz](https://www.amazon.com/dp/B0DWZTGBK8?tag=cwmt-20) |
| 32  | Fused-quartz plate (budget)  | 50 × 50 × 1 mm, industrial grade                        | 1      | ~\$13       | [Optical Glass, 50×50×1mm](https://www.amazon.com/dp/B0F1YVNTMD?tag=cwmt-20)     |
| 33  | Fused-quartz slide (test)    | 75 × 25 × 1 mm, microscope slide format                 | 1      | ~\$10       | [MUHWA Fused Quartz Slide](https://www.amazon.com/dp/B07ZYT3DJ6?tag=cwmt-20)     |
| 34  | Foam / felt corner pads      | Small adhesive pads, ~10 mm, for plate corner supports  | 1 pack | ~\$4        | Amazon search: "small self adhesive felt pads 10mm"                              |
|     | **Plate kit subtotal**       | _(pick one plate + pads)_                               |        | **~$17–20** |                                                                                  |

> **Which plate to buy?** Start with the 100 × 100 × 1 mm fused-quartz plate (#31) — it has the most modes (52 below 20 kHz) and a $16 price point. If budget is tight, the 50 × 50 mm plate (#32) at $13 still gives 11 modes and demonstrates the 2D principle. The microscope slide (#33) is a cheap test piece for practicing edge PZT bonding before committing to the larger plate. You DO NOT need to buy all three — any one will work for Experiments 15–16.

> **Why fused quartz?** Fused quartz (SiO₂) has 10× the quality factor ($Q = 100{,}000$) and 6× lower thermal expansion ($\alpha = 0.55$ ppm/K) compared to the borosilicate glass used for rods ($Q = 10{,}000$, $\alpha = 3.3$ ppm/K). This means sharper resonance peaks, more resolvable modes, and greater thermal stability — exactly the properties that matter for CWM encoding.

> **Budget note.** Most schools already own an oscilloscope with FFT capability and a function generator—if so, skip item 5 and the core materials cost is just ~\$38. For labs without a scope, we recommend the PicoScope 2204A (\$192), which provides both the waveform generator (transmit) and the digitizer (receive) in one USB device with free cross-platform software (PS7). Any oscilloscope with ≥200 kHz bandwidth and a separate function generator will also work. The 15 glass rods and 15 PZT discs provide enough spares for multiple student groups, breakage, and control experiments. One kit serves an entire class.

> **Computer requirement.** Experiments 6 and 9–14 require a laptop or desktop computer with Python 3.10+ and the repository's dependencies (`pip install -r requirements.txt`). The computer runs the analysis scripts and, for Experiments 12–14, the **CWM Lab** unified web interface (`tools/cwm_lab.py`). CWM Lab combines the password vault, image search, and content-addressable memory demos into a single browser-based UI with built-in face recognition, a hardware proof panel, and automatic PicoScope detection. It runs entirely locally—no internet required. The standalone CLI tools (`cwm_vault.py`, `cwm_image_search.py`, `cwm_cam.py`) remain available as alternatives. All tools include a simulation mode for testing without hardware.

> **Enclosure dimension guide.** The insulated box must be large enough to hold 150 mm glass rods horizontally with room for PZT leads and BNC cables on both ends (Topology B), and wide enough for a single-row array of rods at 30 mm spacing. If sourcing your own box, use these minimum interior dimensions:
>
> | Axis                  | Minimum interior | Purpose                                                          |
> | --------------------- | ---------------- | ---------------------------------------------------------------- |
> | **Length** (rod axis) | 8″ / 203 mm      | 150 mm rod + 15 mm PZT/cable clearance each end + 11.5 mm margin |
> | **Width**             | 6″ / 152 mm      | 4 rods at 30 mm spacing + 22.5 mm margin each side (fits CH-BOX) |
> | **Height**            | 3″ / 76 mm       | Single-row: rod diameter + notch depth + clearance above         |
>
> The recommended CH-BOX (item 11) has interior dimensions of 9″ × 6.5″ × 5.5″ (228 × 165 × 140 mm), which comfortably fits a single row of 4 rods at 30 mm spacing (Template T.2A). For 6 rods, use 25 mm spacing (Template T.2B — still fits CH-BOX). For 8 rods at 25 mm spacing you need a wider enclosure (min 225 mm interior width). Orient the rods along the 9″ dimension. Any insulated container meeting these minimums will work—an insulated shipping box, a picnic cooler, or even a cardboard box lined with 1″ foam board.

### D.2 Safety Notes

⚠️ **Glass hazard.** Borosilicate rods can snap if bent or dropped. Always wear safety glasses when handling rods. Dispose of broken glass in a rigid sharps container, never a trash bag.

⚠️ **Cyanoacrylate (super glue).** Bonds skin instantly. Keep acetone (nail polish remover) on hand to dissolve accidental skin bonds. Work in a ventilated area. Supervise younger students closely during the gluing step.

⚠️ **Hearing.** The fundamental mode (17.7 kHz) is near the upper limit of human hearing. Some students may hear a faint whine during high-amplitude excitation. This is harmless at the drive levels used here (\<1 V), but if anyone reports discomfort, reduce the AWG amplitude to 0.1 V.

### D.2a PicoScope Quick-Start Guide

This section walks you through setting up the PicoScope 2204A from unboxing to first measurement. If you are using a different oscilloscope and function generator, adapt these steps to your equipment — the key parameters (frequencies, amplitudes, FFT settings) are the same.

#### Step 1: Install PS7

Download PicoScope 7 (PS7) from [picotech.com/downloads](https://www.picotech.com/downloads). It is free, requires no license key, and runs on Windows, macOS, and Linux. Install and launch PS7 before plugging in the hardware.

#### Step 2: Connect the Hardware

1. Plug the PicoScope 2204A into any USB port on your computer. PS7 should detect it automatically — you will see "PicoScope 2204A" in the bottom status bar.
2. Connect a BNC cable from **Channel A** to your transmit/receive PZT disc. For Experiments 1–8 (single rod), a single BNC cable carries both the AWG drive signal and the received signal using a **BNC T-connector**: one arm to the AWG output, one arm to Channel A input, and the stem to the PZT leads. The PicoScope kit includes a T-connector; if not, any 50 Ω BNC T-adapter works.
3. Set the probe attenuation to **1×** in PS7 (click the Channel A label → Probe → 1:1). Do not use a 10× oscilloscope probe — the PZT connects directly via BNC.

#### Step 3: Default Channel Settings

Use these settings for Channel A at the start of every experiment, then adjust per the experiment table below:

| Setting       | Value   | Where in PS7                           |
| ------------- | ------- | -------------------------------------- |
| **Coupling**  | AC      | Click Channel A label → Coupling → AC  |
| **Range**     | ±200 mV | Click Channel A label → Range → 200 mV |
| **Probe**     | 1×      | Click Channel A label → Probe → 1:1    |
| **Bandwidth** | Full    | Leave at default (no bandwidth limit)  |

> **Why AC coupling?** The PZT generates a small DC offset when stressed by the glue bond. AC coupling blocks this offset and shows only the acoustic signal.

#### Step 4: AWG (Signal Generator) Basics

Open the signal generator panel: **Tools → Signal Generator** (or click the waveform icon in the toolbar). Key controls:

| Control       | What it does                                                                           |
| ------------- | -------------------------------------------------------------------------------------- |
| **Wave Type** | Sine, Square, Triangle, or **Arbitrary** (for imported CSV files)                      |
| **Frequency** | Set the drive frequency (e.g. 17700 Hz for the fundamental mode)                       |
| **Amplitude** | Peak-to-peak voltage. Start at **0.5 Vpp** for most experiments. Never exceed 2.0 Vpp. |
| **Sweep**     | For frequency sweeps (chirps): enable Sweep, set Start/Stop frequencies and Sweep Time |
| **Trigger**   | For burst mode: Trigger Source → "Scope" or "Manual", Shots = 1, Cycles = 1            |

#### Step 5: FFT / Spectrum View

Many experiments require a frequency-domain view. To enable it:

1. Click the **Spectrum** tab at the top of the main view (next to the Scope tab), or go to **View → Spectrum**.
2. Set the FFT window to **Hanning** (click the spectrum settings gear → Window → Hanning). This gives the best frequency resolution for narrow peaks.
3. Set the number of bins to **≥ 16,384** (spectrum settings → Bins). More bins = finer frequency resolution. For a 500 kS/s sample rate, 16,384 bins gives ~0.03 Hz per bin — more than enough to resolve the ~1.77 Hz linewidth of the rod.
4. The x-axis shows frequency (Hz), the y-axis shows amplitude (dBV or linear mV). Click the y-axis label to toggle between them.

#### Step 6: Exporting Data

To save a waveform or spectrum as a CSV file for later analysis:

1. **File → Save As** (or Ctrl+S / Cmd+S).
2. Choose **CSV** format.
3. For spectrum data, make sure you are on the Spectrum tab when saving — PS7 saves whichever view is active.
4. Saved files go into your chosen folder. The repository analysis scripts expect `.csv` files in `data/raw/`.

#### PicoScope Settings Quick Reference

The table below gives recommended PS7 settings for each experiment type. Set the AWG first, then configure the channel and trigger.

**Table D.2a: PicoScope Settings by Experiment**

| Experiment             | AWG Mode                         | AWG Freq / Sweep     | AWG Amp | Ch A Range | Timebase   | Trigger                        | View     |
| ---------------------- | -------------------------------- | -------------------- | ------- | ---------- | ---------- | ------------------------------ | -------- |
| **Exp 1** Tap test     | OFF                              | —                    | —       | ±50 mV     | 1 ms/div   | Ch A, 5 mV rising, Auto        | Scope    |
| **Exp 2a** Ring-down   | Sine, Triggered: 1 shot, 1 cycle | 17,700 Hz            | 0.5 Vpp | ±500 mV    | 50 ms/div  | Ch A, 50 mV rising, **Single** | Scope    |
| **Exp 2b** Bandwidth   | Sweep: 17,000 → 18,500 Hz, 2 s   | —                    | 0.2 Vpp | ±200 mV    | —          | Auto                           | Spectrum |
| **Exp 3** Mode comb    | Sweep: 1,000 → 200,000 Hz, 1 s   | —                    | 0.5 Vpp | ±500 mV    | —          | Auto                           | Spectrum |
| **Exp 4** Thermal      | Same as Exp 3 (quick snapshot)   | —                    | 0.5 Vpp | ±500 mV    | —          | Auto                           | Spectrum |
| **Exp 5** Perturbation | Same as Exp 3                    | —                    | 0.5 Vpp | ±500 mV    | —          | Auto                           | Spectrum |
| **Exp 6** Recall       | Arbitrary → import `query_X.csv` | 1 MS/s               | 0.4 Vpp | ±200 mV    | —          | Auto                           | Spectrum |
| **Exp 7** CW readout   | Sine, Continuous                 | Measured f₁ ± 0.1 Hz | 0.2 Vpp | ±200 mV    | 100 ms/div | Auto (free-run)                | Scope    |
| **Exps 8–14**          | Per experiment instructions      | —                    | Per exp | ±200 mV    | —          | Auto                           | Spectrum |

> **Note on ±500 mV range.** When using a BNC T-connector, the AWG output feeds directly into Channel A — so the channel "sees" the full drive voltage. Use ±500 mV for 0.5 Vpp drive to prevent clipping. For lower-amplitude experiments (0.2 Vpp), ±200 mV is sufficient.

#### Importing AWG Waveforms (Experiments 6, 9–14)

The repository includes pre-computed multi-tone query waveforms for the packed-array experiments. To load them into PS7:

1. Navigate to `data/results/awg/` in the repository. You will find `query_A.csv`, `query_B.csv`, `query_C.csv`, and `query_D.csv`.
2. In PS7: **Tools → Signal Generator → Wave Type → Arbitrary → Import**.
3. Select the desired CSV file. PS7 loads the normalized waveform (±1 values).
4. Set **Amplitude** to ~0.40 Vpp and **Sample Rate** to 1 MS/s.
5. Set **Mode** to Continuous, then click **Start**.

To regenerate waveforms with custom parameters (different putty mass, rod length, etc.):

```bash
PYTHONPATH=. python tools/awg_waveform.py --all
```

### D.2b CWM Lab Experiment Wizard

The **Experiment Wizard** inside CWM Lab automates PicoScope configuration, waveform capture, spectral analysis, and community result submission from one browser panel. It eliminates the need to manually set PicoScope 7 parameters — every setting from Table D.2a is pre-loaded and applied with one click.

#### Starting the Wizard

1. **Launch CWM Lab** (if not already running):

```bash
cd /path/to/cwm
source .venv/bin/activate
PYTHONPATH=. python tools/cwm_lab.py --port 8200
```

2. Open **http://localhost:8200** in any browser.
3. The **🔬 Experiments** tab opens by default showing the Experiment Wizard with scope status, preset selector, and capture controls.

If a PicoScope 2204A is connected via USB, the status strip shows **🟢 PicoScope Connected**. Otherwise it shows **🟡 No PicoScope — Simulation mode**, and captures will use synthetic data computed from Rayleigh perturbation theory.

#### Step 1 — Select an Experiment

Choose a preset from the dropdown. Each preset corresponds to a PicoScope configuration from Table D.2a:

| Preset          | Experiment                     | AWG Mode          | View             |
| --------------- | ------------------------------ | ----------------- | ---------------- |
| **exp01**       | Exp 1 – Mode Persistence (Tap) | OFF               | Scope + Spectrum |
| **exp02a**      | Exp 2a – Ring-Down Decay       | Sine (1 shot)     | Scope + Spectrum |
| **exp02b**      | Exp 2b – Bandwidth / SNR       | Sweep 17–18.5 kHz | Spectrum         |
| **exp03**       | Exp 3 – Mode Comb              | Sweep 1–200 kHz   | Spectrum         |
| **exp04**       | Exp 4 – Thermal Stability      | Sweep 1–200 kHz   | Spectrum         |
| **exp05**       | Exp 5 – Perturbation           | Sweep 1–200 kHz   | Spectrum         |
| **exp06**       | Exp 6 – Recall (Arbitrary)     | Load CSV          | Spectrum         |
| **exp07**       | Exp 7 – CW Readout             | Sine (continuous) | Scope + Spectrum |
| **exp_generic** | Exps 8–14                      | Sweep 1–200 kHz   | Spectrum         |

#### Step 2 — Configure

Click **Configure**. The wizard opens the PicoScope handle and applies all settings automatically:

- Channel A voltage range and coupling
- Trigger source, threshold, direction, and auto-trigger delay
- AWG waveform type, frequency, amplitude, and shot count

A summary strip confirms the active configuration: experiment name, AWG mode, voltage range, and whether hardware or simulation is active.

#### Step 3 — Capture

Click **Capture**. The wizard runs a block capture (3,968 samples at 1 MS/s for the ps2000 2204A), averages if configured, then computes the FFT and detects spectral peaks. Results appear immediately:

- **Waveform canvas** — time-domain voltage vs. time (µs)
- **Spectrum canvas** — FFT magnitude (dB) vs. frequency (kHz) with peak markers and noise floor
- **Peak table** — detected peaks sorted by frequency, with SNR and resolution metadata

You can click **Capture** again to re-acquire without reconfiguring. This is useful for Experiments 4 (thermal — capture at different temperatures) and 5 (perturbation — capture before and after adding mass).

#### Step 4 — Export to Community Firebase

After capturing, the **Export to Community** section appears. To contribute your results to the shared CWM research database:

1. **Select the target experiment** from the dropdown (e.g. "Exp 1 – Mode Persistence").
2. **Fill in rod details** — material (default: Borosilicate glass), length (mm), diameter (mm). Captured peak frequencies are auto-populated into the submission.
3. Optionally add a **nickname**, **location**, and **notes** describing your setup.
4. Click **🚀 Export to Community Firebase**.

The wizard authenticates anonymously with the CWM Firebase project, then submits your results through the server-validated endpoint. The data appears in the community aggregation at [coherent-wave-memory.web.app](https://coherent-wave-memory.web.app). Rate-limited to 5 submissions per minute.

> **No account required.** Export uses Firebase anonymous authentication — you do not need a Google account or any credentials. Each session gets a unique anonymous UID for rate limiting and attribution.

> **Offline mode.** If the internet is unavailable, the capture data is still saved locally in `data/results/lab/captures/` as JSON files. You can export later when connectivity returns.

#### Closing the Scope

Click **Close Scope** when finished to release the PicoScope handle. This is important if you want to switch to PicoScope 7 software, or if another application needs USB access to the device. The wizard automatically closes the scope when the CWM Lab server shuts down.

#### Multi-Rod Setup (Experiments 9–14)

The packed-array experiments drive **all rods simultaneously** and read the **aggregate response** — this is the physical parallel search that defines CWM. You do not need a separate scope channel per rod.

There are two supported topologies: **Topology A** uses one PZT per rod (simpler build) and **Topology B** uses two PZTs per rod with a relay multiplexer (enables per-rod energy measurement). Topology A works for all experiments; Topology B is recommended for 4+ rods and required for calibrated per-rod readout.

---

**Topology A — Shared single-PZT bus (simplest):**

1. Twist or solder all PZT "hot" leads (red wires) together. Do the same for all ground leads (black wires). A small terminal strip or screw-terminal block keeps this tidy.
2. Connect the bundled leads to a single BNC cable. Use a BNC T-connector so the bundle connects to both the AWG output and Channel A input — the same topology as single-rod experiments, just with more PZTs on the wire.
3. When you drive a query waveform, every rod receives it. The rod whose stored pattern best matches resonates most strongly, dominating the aggregate signal on Channel A. Off-resonance rods contribute negligible amplitude. This is associative recall happening in the physics.

> **Electrical note.** Each PZT is ~28 nF. Ten in parallel = 280 nF (impedance ~32 Ω at 17.7 kHz). The AWG's 600 Ω output drives this easily. The parallel capacitance does not degrade signal quality — it is equivalent to a single larger transducer.

---

**Topology B — Two PZTs per rod with relay multiplexer (recommended for 4+ rods):**

This topology separates the drive path from the sense path using two PZTs on each rod and an 8-channel relay module to read each rod individually. No soldering is required — all connections use screw terminals, DuPont jumper wires, twist splices, and electrical tape.

**Additional materials for Topology B:**

| Component                                | Purpose                                    | Est. Cost |
| ---------------------------------------- | ------------------------------------------ | --------- |
| 8-ch relay module (5V, opto-isolated)    | Switches individual sense PZTs onto Ch A   | ~$11      |
| Arduino Nano clone (CH340, Type-C USB)   | Powers relay + provides GPIO for switching | ~$10      |
| DuPont jumper wires (F-to-F, 40-pack)    | Connects Arduino pins to relay headers     | ~$5       |
| Stranded silicone wire (26 AWG, 6-color) | Extends short PZT leads to relay terminals | ~$11      |
| Electrical tape                          | Secures twist-splice wire joints           | ~$2       |
| Precision screwdriver set                | For relay screw terminals                  | ~$6       |
| Extra PZT discs (15-pack)                | Second PZT per rod (drive end)             | ~$7       |

**Build procedure:**

1. **Attach two PZTs per rod.** Glue one PZT to each end of every rod (per Experiment 1 procedure). Label one end "Drive" and the other end "Sense" with masking tape.

2. **Wire the drive PZTs.** Twist all drive PZT hot leads together, and all drive PZT ground leads together. Connect the bundle to the PicoScope AWG output via a BNC-to-alligator cable. All rods receive the same drive signal simultaneously.

3. **Extend the sense PZT leads.** The PZT leads (~4 inches) are too short to reach the relay module. For each sense PZT:
   - Cut a 12–18 inch length of 26 AWG stranded wire.
   - Strip ~½ inch from each end. The silicone insulation strips easily with scissors — nick it and pull.
   - Twist the PZT lead around the stripped extension wire for ~1 cm. Wrap the joint with electrical tape.
   - Use a consistent color code: e.g. red for hot, black for ground.

4. **Connect sense wires to the relay module.** Each relay channel has three screw terminals: **COM** (common), **NO** (normally open), and **NC** (normally closed). For each rod:
   - Run the hot extension wire into the **COM** terminal of that rod's relay channel. Tighten the screw.
   - Run the ground extension wire to a shared ground bus (twist all sense grounds together and connect to the BNC cable ground via alligator clip).

5. **Wire the relay outputs to Channel A.** Connect all **NO** terminals together (twist or terminal strip) and run to the PicoScope Channel A BNC-to-alligator cable (hot lead). When a relay activates, it connects that rod's sense PZT to Channel A; all others are disconnected.

6. **Connect the Arduino to the relay module.**
   - Use DuPont female-to-female jumper wires to connect Arduino digital pins D2–D9 to the relay module's IN1–IN8 header pins.
   - Connect Arduino **5V** pin to relay module **VCC** and Arduino **GND** to relay module **GND**.
   - Connect the Arduino to your computer via USB-C cable.

7. **Upload the relay controller firmware.** CWM Lab communicates with the Arduino over USB serial to select which relay is active. Upload the sketch from `tools/relay_controller/relay_controller.ino` using the Arduino IDE:
   - Install the Arduino IDE (free) and select Board: "Arduino Nano" and Port: the CH340 serial port.
   - Open `tools/relay_controller/relay_controller.ino` and click Upload.
   - The sketch listens for single-character commands ('0'–'7' to activate a relay, 'x' to deactivate all).

**Topology B wiring diagram:**

```
                    ┌──────────────────────────────────────┐
                    │         8-Channel Relay Module        │
  Arduino Nano      │  IN1  IN2  IN3  ...  IN8             │
  D2─────────────── │──IN1                                 │
  D3─────────────── │──IN2                                 │
  D4─────────────── │──IN3                                 │
  ...               │  ...                                 │
  5V─────────────── │──VCC                                 │
  GND────────────── │──GND                                 │
                    │                                      │
                    │  COM1  NO1  COM2  NO2  ...           │
                    │   │     │    │     │                  │
                    └───┼─────┼────┼─────┼─────────────────┘
                        │     │    │     │
            Rod 1 Sense─┘     │    │     │
            Rod 2 Sense───────┼────┘     │
                              │          │
                              └────┬─────┘
                                   │ (all NO terminals joined)
                                   │
                              Ch A input
                           (BNC alligator)

  AWG output ──── All Drive PZTs in parallel
                  (BNC alligator → twisted bundle)
```

> **Why two PZTs?** With a single shared PZT bus (Topology A), the AWG drive signal appears directly on Channel A, masking the rod's acoustic response. Separating drive and sense PZTs onto opposite ends of each rod provides ~20 dB of isolation. The relay then lets you read each rod individually, enabling calibrated per-rod energy measurement and eliminating coupling-strength bias between rods.

---

**Per-rod diagnostic (optional, Topology A only):**

To verify which rod is responding (useful the first time through Experiment 9), you can temporarily connect **Channel B** to a single rod's PZT while Channel A reads the aggregate:

- **Channel A:** All PZTs in parallel (aggregate response via T-connector + AWG).
- **Channel B:** One rod's PZT only (individual response). Configure identically to Channel A (AC coupling, same range, 1× probe).
- Swap the Channel B cable between rods to confirm the matching rod dominates.

### D.3 Experiment 1 — Building the Resonator

**Objective:** Assemble a functioning glass-rod acoustic resonator and verify electrical connectivity.

**Time:** 30 minutes active + 24 hours glue cure.

**Materials:** Items 1 or 2, 3 or 4, 6, 9, 16, 18 from the BOM. Optional: item 23 (sandpaper) if your rods have rounded ends on both sides.

**Procedure:**

1. **Clean the rod.** Wipe one glass rod with isopropyl alcohol and a soft cloth. Allow 2 minutes to dry completely. Finger oils dampen vibrations measurably.

2. _(Optional)_ **Lap one end flat.** If both ends of your rod are rounded (fire-polished), the PZT disc won't bond well to a convex surface. Place a sheet of 220-grit sandpaper on a flat surface (a glass plate, granite tile, or kitchen countertop works well). Hold the rod vertical and sand the end in a figure-8 pattern with light, even pressure and a few drops of water as lubricant. After 2–3 minutes the end should be visibly flat across the full 6 mm diameter. Finish with 400-grit for a smooth bond surface. Wipe clean with alcohol. If your rods already have one flat end, skip this step—use the flat end for the PZT.

3. **Build the cardboard rod mount inside the insulated box.** Cut two rectangles of flat cardboard to 165 × 140 mm (6.5″ × 5.5″)—sized to slot snugly inside the insulated box (item 11). See Template T.1 at the end of this guide for a printable 1:1 cutting pattern. For **single-rod experiments (Topology A):** using the 7 mm hollow punch from the kit (item 22), punch a clean hole through each rectangle at the same height, centered on the cardboard—sized just large enough for the 6 mm rod to pass through with minimal contact. The rod slides horizontally through the aligned pinholes and should hang freely with no hard clamping. For **multi-rod or Topology B experiments:** cut U-shaped notches (7 mm wide × 10 mm deep) from the top edge of each divider instead of punching pinholes. This lets you drop rods in from above—essential when PZTs are glued to both ends and putty has been applied, making it impossible to slide rods through holes. Printable notch templates are provided at the end of this guide (Templates T.2A/B/C). Drop both dividers into the box standing upright, spaced 75 mm apart—this places each support at $L/4$ and $3L/4$ from one end (37.5 mm and 112.5 mm for a 150 mm rod). These positions are the exact displacement nodes of the second longitudinal mode—the acoustic "stems" of the rod. Position the first divider so that the PZT disc and its leads protrude out one end of the box for easy cable connection. Cut a small notch in the box lid above the PZT end for BNC cable and thermometer wire routing. A wine glass rings because you hold it by the stem, a vibrational node where energy cannot escape; the same physics governs your rod mount (see Failure Mode 6 and Section 7).

> **Why cardboard?** The support material matters far less than the support _position_. At a true displacement node, the rod surface has zero displacement—no energy can transfer to the support regardless of what the support is made of. This is the same reason a wine glass doesn't care whether its stem is crystal, ceramic, or plastic: the stem is at a node, so the resonance is indifferent to the stem's material properties. The acoustic impedance mismatch between glass ($Z \approx 1.2 \times 10^7$ Pa·s/m) and cardboard ($Z \approx 10^4$–$10^5$ Pa·s/m) means that even at positions with residual displacement, ~99.9% of acoustic energy is reflected at the glass–cardboard interface rather than transmitted. The contact area is just a thin ring around the pinhole edge—much less than a foam V-notch cradle—further limiting energy transfer. In practice, cardboard pinholes at the correct nodal positions yield Q values within 5% of foam cradles, while offering three advantages: (1) the dividers slot into the box walls, providing rigid, repeatable positioning without tape or rubber bands; (2) they are free; and (3) they naturally partition the box interior into isolated chambers for multi-rod array experiments—something foam cannot do.
>
> **One caution:** if the pinhole or notch is too tight, it clamps the rod and creates exactly the hard-contact damping you're trying to avoid. Pinholes and notches should be just loose enough that the rod passes through or drops in with no binding. The 7 mm hollow punch (item 22) produces a clean hole 1 mm larger than the rod—ideal clearance. For U-notches, use scissors or a craft knife to cut a 7 mm wide slot from the top edge to 10 mm depth; a semicircular bottom is ideal but a flat-bottomed slot works too. See the Diagnostic Test in Failure Mode 6 below for a quantitative check.

4. **Center the PZT disc (critical).** Use the centering guide from Template T.4: cut out one 25 mm paper disc, lay it on the rod end, and align the blue circle with the rod edge. The red crosshair marks exact center. Alternatively, cut two small strips of masking tape (~12 mm each) and adhere them in a cross-hair pattern centered on the flat end face of the rod. The 25 mm PZT disc will overhang the 6 mm rod by 9.5 mm on each side—this is normal and does not affect performance. Only the 6 mm contact area couples acoustic energy. An off-center bond excites transverse and torsional modes that pollute the spectrum (Failure Mode 2).

5. **Apply glue sparingly.** Place one tiny drop of cyanoacrylate—smaller than a pinhead, less than 0.5 mm in diameter—at the center of the cross-hair. _Less is more:_ excess glue adds mass and viscoelastic damping that destroys the quality factor (Failure Mode 1).

6. **Attach the PZT disc.** Press the flat face of the 25 mm PZT disc onto the glued spot, centering the rod within the disc so the overhang is uniform all around (~9.5 mm). Hold firm, even pressure for 30 seconds. Gently peel away the tape cross-hair strips (or paper guide).

7. **Cure.** Set the assembly aside in the insulated box mount for a full 24 hours. Cyanoacrylate reaches full bond strength overnight; rushing produces a weak, lossy joint.

8. **Connectivity check.** Connect the PZT leads to the PicoScope Channel A input via a BNC adapter or clip leads. Set the scope to AC coupling, 1 mV/div, 1 ms/div timebase. Gently tap the free end of the rod with a fingernail. You should see a decaying burst of oscillation on screen. If no signal appears: check wire connections, ensure the PZT is not cracked, and try a firmer tap.

> **⚙️ Failure Mode 1 — PZT/Epoxy Boundary Damping (Low Q)**
>
> The glue joint and PZT disc add mass and internal friction at the rod end, potentially reducing Q from the intrinsic material value (~10,000) to below 100 if done carelessly.
>
> - Use the _absolute minimum_ glue: one drop smaller than a pinhead.
> - Ensure the cured glue layer is thin (\<0.1 mm). A thick glue layer acts as a lossy viscoelastic coupling that absorbs acoustic energy each cycle.
> - Build a second "control" rod with _no_ PZT attached—excite it by tap only and record its ring-down via a nearby microphone or laser vibrometer (if available). Comparing Q values between the two rods isolates the damping contribution of the PZT joint.
> - If Q is unacceptably low (\<500 after Experiment 2), scrape off the PZT with a razor blade, clean the end face with alcohol, and re-glue with a smaller drop.

> **⚙️ Failure Mode 6 — Support-Point Energy Drain (the Glass Harp Lesson)**
>
> A wine glass rings brilliantly because you hold it by the stem—a point of zero vibrational displacement (a node) for the rim's flexural modes. Energy cannot leak through a point that isn't moving. Press your finger against the rim itself and the tone dies instantly: the support is now at an antinode, and your finger becomes an acoustic drain.
>
> The same physics governs your rod mount. For a free-free rod vibrating in its $n$-th longitudinal mode, the displacement pattern is $u(x) = \cos(n\pi x/L)$. The displacement nodes—the "stems"—occur at:
>
> | Mode    | Node positions           |
> | ------- | ------------------------ |
> | $n = 1$ | $L/2$ (center)           |
> | $n = 2$ | $L/4$ and $3L/4$         |
> | $n = 3$ | $L/6$, $L/2$, and $5L/6$ |
>
> The recommended support positions at $L/4$ and $3L/4$ (step 2) are the exact nodes of mode 2, and they produce only 50% of peak displacement for mode 1—a good all-round compromise for multi-mode measurements.
>
> If your Q values are lower than expected despite a clean PZT bond:
>
> - **Verify support positions.** Measure from one end: 37.5 mm and 112.5 mm for a 150 mm rod. Mark the positions with a fine-tip marker before cutting notches or punching pinholes.
> - **Try midpoint mounting.** For mode-1-only measurements, a single divider at $L/2 = 75$ mm is the ideal node and will maximize Q for the fundamental. (This sacrifices mode 2, which has an antinode there.)
> - **Check notch/pinhole size.** The slot or hole should be just large enough for the rod to sit in without binding. Too tight and the cardboard clamps the rod, draining energy. Too loose and the rod rattles.
> - **Upgrade to fishing line.** Loop a thin monofilament line around the rod at the node position and tension it between two fixed posts. This gives near-zero contact area and mimics the knife-edge mounts used in precision metrology. Students who have played a glass harp will immediately feel the analogy: the taut line is the stem.
> - **Diagnostic test.** Place the rod so one support is at the center ($L/2$) and measure Q for mode 1. Then reposition to $L/4$ and remeasure. If Q changes by more than 20%, your notches are too tight or making hard contact—widen them slightly or use fishing line.

---

### D.4 Experiment 2 — Measuring the Quality Factor

**Objective:** Determine Q via two independent methods (ring-down and bandwidth) and confirm the resonator is material-loss-limited.

**Time:** 45 minutes.

**Materials:** Assembled resonator from Exp. 1, PicoScope 2204A, BNC cable, insulated box mount.

**Procedure:**

1. **Set up.** Place the resonator in the insulated box mount on a stable surface (no vibration from HVAC, foot traffic, etc.). Connect the PZT leads to both the PicoScope AWG output (waveform generator) and Channel A input. A BNC T-connector works, or simply share the two PZT leads between the AWG and scope clips.

2. **Impulse excitation.** In the PicoScope software (PS7, free download), configure the AWG to output a single 1-cycle burst at 17,700 Hz with 0.5 V amplitude. Set Channel A to trigger on the rising edge. Set the timebase to 50 ms/div so the display shows ~500 ms of data.

3. **Capture the ring-down.** Trigger the burst and record the decaying sinusoidal waveform. The oscillation frequency should be near 17.7 kHz; the amplitude should decay smoothly.

4. **Measure τ (time constant).** The envelope follows $A(t) = A_0 \, e^{-t/\tau}$. Identify the initial peak amplitude $A_0$, then find the time $t$ at which the envelope has dropped to $A_0/e \approx 0.368 \times A_0$. That time is τ. Alternatively, use PicoScope's cursor measurements to read the 1/e point directly.

5. **Calculate Q from ring-down:**

$$Q_{\text{ringdown}} = \pi \, f_1 \, \tau$$

For example: $f_1 = 17{,}700$ Hz, $\tau = 180$ ms gives $Q = \pi \times 17{,}700 \times 0.180 = 10{,}006$.

6. **Cross-check via bandwidth method.** Switch PicoScope to spectrum (FFT) mode. Drive the rod with a slow linear frequency sweep (chirp) from 17,000 Hz to 18,500 Hz over 2 seconds at 0.2 V amplitude. In the FFT view, locate the resonance peak. Measure the full width at half-maximum power (the −3 dB bandwidth, $\Delta f_{3\text{dB}}$—the frequency span where the peak drops to 70.7% of its maximum amplitude, or −3 dB from the peak). Calculate:

$$Q_{\text{bandwidth}} = \frac{f_1}{\Delta f_{3\text{dB}}}$$

7. **Compare the two Q values.** They should agree within 10%. Record all results in Worksheet D.1.

> **⚙️ Failure Mode 4 — Piezoelectric Self-Resonance Masking**
>
> A 10 mm PZT disc has its own radial resonance, typically at 200–300 kHz—well above the glass rod's fundamental (17.7 kHz). However, some disc types have a thickness resonance at lower frequencies that can overlap with glass-rod harmonics.
>
> To identify PZT artifacts:
>
> - _Before_ gluing (during your next build), hold a bare PZT disc by its leads in free air and tap it gently. Record the FFT spectrum—these are PZT-only resonances.
> - After assembly, compare the full spectrum against the PZT-only spectrum. Any peak that appears in both is a PZT artifact, not a glass eigenmode.
> - True glass-rod longitudinal modes are evenly spaced at $\Delta f = v_{\text{bar}}/(2L) \approx 17{,}700$ Hz. PZT resonances do _not_ follow this comb pattern. Any peak that falls off the comb by more than 1% is suspect.

<div class="worksheet-header">
<h4>Worksheet D.1 — Quality Factor Measurement</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy per rod. Record ring-down and bandwidth Q values for comparison.</p>
</div>

| Parameter                           | Rod 1                                         | Rod 2 | Rod 3 |
| ----------------------------------- | --------------------------------------------- | ----- | ----- |
| Date / Time                         | <span class="ex">15 Mar 2026, 14:30</span>    |       |       |
| Experimenter                        | <span class="ex">A. Student</span>            |       |       |
| Room temperature (°C)               | <span class="ex">22.3</span>                  |       |       |
| Rod length L (mm)                   | <span class="ex">150.2</span>                 |       |       |
| Rod diameter d (mm)                 | <span class="ex">6.01</span>                  |       |       |
| Glue amount (tiny / small / medium) | <span class="ex">tiny</span>                  |       |       |
| Measured f₁ (Hz)                    | <span class="ex">17,693</span>                |       |       |
| Predicted f₁ = 5,315/(2L) (Hz)      | <span class="ex">17,694</span>                |       |       |
| Ring-down τ (ms)                    | <span class="ex">168</span>                   |       |       |
| **Q (ring-down) = πf₁τ**            | <span class="ex">9,335</span>                 |       |       |
| −3 dB bandwidth Δf₃dB (Hz)          | <span class="ex">1.9</span>                   |       |       |
| **Q (bandwidth) = f₁/Δf₃dB**        | <span class="ex">9,312</span>                 |       |       |
| Two methods agree within 10%? (Y/N) | <span class="ex">Y ✓</span>                   |       |       |
| Notes                               | <span class="ex">Clean bond, thin glue</span> |       |       |

**Expected results.** Q should fall in the range 1,000–10,000. Values near 10,000 indicate excellent construction (material-loss-limited). Values below 500 suggest excessive glue, poor PZT centering, or a hard contact point on the mount—rebuild with corrections per the Failure Mode 1 mitigation above. A control rod with no PZT (tap-excited) should yield Q near 10,000, confirming the intrinsic glass value.

---

### D.5 Experiment 3 — Mapping the Mode Spectrum

**Objective:** Identify the longitudinal eigenmode comb and distinguish real modes from transverse/torsional artifacts.

**Time:** 45 minutes.

**Materials:** Assembled resonator, PicoScope, BNC cable, insulated box mount.

**Procedure:**

1. **Configure the chirp.** Set the PicoScope AWG to output a linear frequency sweep from 1 kHz to 200 kHz over 1 second at 0.5 V amplitude.

2. **Capture the response.** Record Channel A during the chirp with FFT mode enabled. Use a Hanning window and at least 16,384 FFT points for ~1 Hz frequency resolution.

3. **Identify the mode comb.** Longitudinal modes appear as evenly spaced peaks at:

| Mode _n_ | Predicted frequency          |
| -------- | ---------------------------- |
| 1        | 17,717 Hz                    |
| 2        | 35,434 Hz                    |
| 3        | 53,150 Hz                    |
| 4        | 70,867 Hz                    |
| 5        | 88,584 Hz                    |
| 6        | 106,301 Hz                   |
| 7        | 124,018 Hz                   |
| _n_      | $n \times 5{,}315 / (2L)$ Hz |

4. **Mark confirmed modes.** On the FFT display (or in a screenshot), mark each peak that falls within ±0.5% of a predicted comb frequency. These are your confirmed longitudinal eigenmodes.

5. **Catalog spurious peaks.** Any peaks that do _not_ fall on the comb are either: (a) transverse or torsional modes (Failure Mode 2), (b) PZT self-resonances (Failure Mode 4), or (c) electrical noise (harmonics of 60 Hz mains). Note their frequencies.

6. **Count confirmed modes** above the noise floor and record in Worksheet D.2.

> **⚙️ Failure Mode 2 — Transverse/Torsional Spectrum Pollution**
>
> If the PZT disc is not centered on the rod axis, it applies an off-axis force that excites bending and torsional modes in addition to the desired longitudinal modes. These appear as extra peaks _between_ the longitudinal comb lines.
>
> Mitigations:
>
> - **Verify centering.** If spurious peaks are within 10 dB of the longitudinal peaks, remove the PZT and re-glue with better centering (see Exp. 1, step 3).
> - **Software filter.** Export the FFT data (PicoScope can save .csv files) and discard all peaks more than ±500 Hz from the predicted comb frequencies.
> - **Rotation test.** Rotate the rod 90° in the cardboard pinholes and re-measure. Longitudinal modes (which depend only on length) will not shift. Transverse modes (which depend on the rod's cross-sectional geometry) will shift because the cross-section is never perfectly circular. Any peak that moves under rotation is not longitudinal.

<div class="worksheet-header">
<h4>Worksheet D.2 — Mode Spectrum Map</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy per rod. Log predicted vs. measured frequencies for all confirmed longitudinal modes.</p>
</div>

| Mode _n_                                | Predicted fₙ (Hz) | Measured fₙ (Hz)                | Δf = meas − pred (Hz)        | Amplitude (dB)              | Confirmed?                               |
| --------------------------------------- | ----------------- | ------------------------------- | ---------------------------- | --------------------------- | ---------------------------------------- |
| 1                                       | 17,717            | <span class="ex">17,693</span>  | <span class="ex">−24</span>  | <span class="ex">−22</span> | <span class="ex">Y</span>                |
| 2                                       | 35,434            | <span class="ex">35,388</span>  | <span class="ex">−46</span>  | <span class="ex">−28</span> | <span class="ex">Y</span>                |
| 3                                       | 53,150            | <span class="ex">53,081</span>  | <span class="ex">−69</span>  | <span class="ex">−35</span> | <span class="ex">Y</span>                |
| 4                                       | 70,867            | <span class="ex">70,775</span>  | <span class="ex">−92</span>  | <span class="ex">−43</span> | <span class="ex">Y</span>                |
| 5                                       | 88,584            | <span class="ex">88,466</span>  | <span class="ex">−118</span> | <span class="ex">−52</span> | <span class="ex">Y</span>                |
| 6                                       | 106,301           | <span class="ex">106,160</span> | <span class="ex">−141</span> | <span class="ex">−63</span> | <span class="ex">Y</span>                |
| 7                                       | 124,018           |                                 |                              |                             | Y / N                                    |
| Spurious 1                              | —                 | <span class="ex">24,330</span>  | —                            | <span class="ex">−58</span> | type: <span class="ex">transverse</span> |
| Spurious 2                              | —                 |                                 | —                            |                             | type: **\_\_**                           |
| Spurious 3                              | —                 |                                 | —                            |                             | type: **\_\_**                           |
| **Total confirmed longitudinal modes:** |                   | <span class="ex">6</span>       |                              |                             |                                          |

**Expected results.** 5–10 clean longitudinal modes should be visible within the PicoScope's 10 MHz bandwidth. The first 2–3 modes will have the highest amplitude. Measured frequencies should match predictions within ±0.5%. If your rod is 200 mm instead of 150 mm, recalculate: $f_1 = 5{,}315/(2 \times 0.200) = 13{,}288$ Hz.

---

### D.6 Experiment 4 — Thermal Stability Characterization

**Objective:** Quantify how room-temperature fluctuations shift mode frequencies, and establish a stable measurement protocol for perturbation experiments.

**Time:** 90 minutes (mostly waiting for equilibration).

**Materials:** Assembled resonator, PicoScope, digital thermometer, insulated box with cardboard dividers.

**Background.** Borosilicate glass has a thermal expansion coefficient of ~3.3 × 10⁻⁶ /°C and a temperature coefficient of elastic modulus of ~−100 ppm/°C. The net frequency sensitivity is approximately:

$$\frac{\Delta f}{f} \approx -50 \text{ ppm/°C}$$

For $f_1 = 17{,}700$ Hz, this predicts $\Delta f \approx -0.9$ Hz per °C of temperature change.

**Procedure:**

1. **Open-air baseline.** Place the resonator in the insulated box mount on a lab bench _with the lid off_. Place the thermometer probe within 2 cm of the rod. Every 5 minutes for 30 minutes, record f₁ (using the bandwidth method from Exp. 2—a quick FFT snapshot) and the temperature. Do not touch the setup or breathe on it.

2. **Thermal perturbation.** Breathe warm air directly onto the rod for 10 seconds, or place a cup of warm water (~50 °C) 20 cm away. Resume recording f₁ and temperature every 2 minutes until the frequency returns to within 0.5 Hz of its initial value. Note the recovery time.

3. **Insulated baseline.** The resonator is already mounted inside the insulated box. Close the lid. Thread the BNC cable and thermometer wire through a small notch cut in the lid. Repeat the 30-minute baseline: record f₁ and temperature every 5 minutes.

4. **Calculate the temperature coefficient.** Plot f₁ versus temperature for both the open-air and insulated datasets. The slope $\Delta f / \Delta T$ is your measured temperature coefficient. Compare to the predicted −0.9 Hz/°C.

5. **Record results** in Worksheet D.3.

> **⚙️ Failure Mode 3 — Thermal Drift Swamping Perturbation Encoding**
>
> A 1 °C temperature change shifts modes by ~0.9 Hz—comparable to a small putty perturbation. If thermal drift is not controlled, perturbation signals drown in noise.
>
> Mitigations:
>
> - **Always use the insulated enclosure** for Experiments 5 and 6. This alone reduces drift by 10–50×.
> - **Equilibrate 30 minutes** before starting perturbation experiments.
> - **Use differential measurement.** Thermal drift shifts _all_ modes by the same fractional amount (−50 ppm/°C). A localized mass perturbation shifts each mode by a _different_ amount (proportional to $\sin^2(n\pi x/L)$). Track the _pattern_ of relative shifts, not absolute frequencies. This is your strongest discriminant.
> - **Bracket measurements.** Take a "before" spectrum immediately before applying putty, and an "after" spectrum within 60 seconds. Over such short intervals, thermal drift is negligible.
> - **Record temperature at every measurement point** so post-hoc correction is possible.

<div class="worksheet-header">
<h4>Worksheet D.3 — Thermal Stability Log</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy per thermal stability run. Track frequency drift vs. temperature over time.</p>
</div>

| Time (min)                            | Temp (°C)                                        | f₁ (Hz)                                  | Δf from t = 0 (Hz)           | Environment                       |
| ------------------------------------- | ------------------------------------------------ | ---------------------------------------- | ---------------------------- | --------------------------------- |
| 0                                     | <span class="ex">22.3</span>                     | <span class="ex">17,693.2</span>         | 0.0                          | <span class="ex">Insulated</span> |
| 5                                     | <span class="ex">22.3</span>                     | <span class="ex">17,693.1</span>         | <span class="ex">−0.1</span> | <span class="ex">Insulated</span> |
| 10                                    | <span class="ex">22.4</span>                     | <span class="ex">17,693.0</span>         | <span class="ex">−0.2</span> | <span class="ex">Insulated</span> |
| 15                                    | <span class="ex">22.4</span>                     | <span class="ex">17,692.9</span>         | <span class="ex">−0.3</span> | <span class="ex">Insulated</span> |
| 20                                    | <span class="ex">22.4</span>                     | <span class="ex">17,693.0</span>         | <span class="ex">−0.2</span> | <span class="ex">Insulated</span> |
| 25                                    | <span class="ex">22.4</span>                     | <span class="ex">17,693.0</span>         | <span class="ex">−0.2</span> | <span class="ex">Insulated</span> |
| 30                                    | <span class="ex">22.4</span>                     | <span class="ex">17,693.0</span>         | <span class="ex">−0.2</span> | <span class="ex">Insulated</span> |
| _(thermal perturbation applied)_      | <span class="ex">hand near enclosure 30 s</span> |                                          |                              |                                   |
| 32                                    | <span class="ex">22.8</span>                     | <span class="ex">17,692.6</span>         | <span class="ex">−0.6</span> | <span class="ex">Open</span>      |
| 34                                    | <span class="ex">23.1</span>                     | <span class="ex">17,692.3</span>         | <span class="ex">−0.9</span> | <span class="ex">Open</span>      |
| 36                                    | <span class="ex">23.0</span>                     | <span class="ex">17,692.4</span>         | <span class="ex">−0.8</span> | <span class="ex">Open</span>      |
| 38                                    | <span class="ex">22.8</span>                     | <span class="ex">17,692.6</span>         | <span class="ex">−0.6</span> | <span class="ex">Open</span>      |
| 40                                    | <span class="ex">22.6</span>                     | <span class="ex">17,692.8</span>         | <span class="ex">−0.4</span> | <span class="ex">Open</span>      |
| **Measured Δf/ΔT:**                   |                                                  | <span class="ex">**−0.85 Hz/°C**</span>  |                              |                                   |
| **Predicted (−0.9 Hz/°C):**           |                                                  | <span class="ex">agrees within 6%</span> |                              |                                   |
| **Recovery time after perturbation:** |                                                  | <span class="ex">**~8 min**</span>       |                              |                                   |

**Expected results.** The open-air drift rate will depend on your HVAC system—typically 0.5–5 Hz over 30 minutes. Inside the insulated enclosure, drift should be \<0.5 Hz over 30 minutes, which is small enough to resolve putty perturbation shifts of 1–10 Hz.

---

### D.7 Experiment 5 — Perturbation Encoding

**Objective:** Write data to the rod by applying silicone putty masses and verify that measured frequency shifts match Rayleigh perturbation theory.

**Time:** 60 minutes.

**Materials:** Assembled resonator (inside insulated enclosure), PicoScope, silicone putty, milligram scale, ruler, fine-tip marker.

**Background.** The Rayleigh perturbation formula predicts that a small mass $\delta m$ placed at position $x$ along a rod of total mass $M$ and length $L$ shifts the $n$-th mode frequency by:

$$\frac{\Delta f_n}{f_n} = -\frac{\delta m}{2M} \sin^2\!\left(\frac{n \pi x}{L}\right)$$

The key insight is that _different modes shift by different amounts_ depending on where the mass sits relative to each mode's antinodes. This position-dependent pattern of shifts is the "spectral fingerprint"—the basis of data encoding.

**Procedure:**

1. **Prepare putty pellets.** Pinch off small pieces of silicone putty and roll them into balls approximately 1 mm in diameter. Weigh each on the milligram scale and record the mass (target: 0.05–0.5 mg). Prepare 3–5 pellets of varied sizes.

2. **Mark positions.** Using the ruler and fine-tip marker, mark reference positions on the rod at 25%, 33%, 50%, 67%, and 75% of the rod length from the PZT end (i.e., at 37.5, 50.0, 75.0, 100.0, and 112.5 mm for a 150 mm rod).

3. **Record the unperturbed spectrum.** Drive the rod with a chirp and capture the FFT. Record the frequencies of modes 1–5 in Worksheet D.4 under "Before."

4. **Apply one putty pellet.** Press it onto the rod at a marked position $x$. The putty should adhere by its own tackiness—no glue needed. Record the pellet mass and position.

5. **Record the perturbed spectrum.** Immediately re-drive and capture the FFT. Record mode frequencies under "After." Calculate the shift $\Delta f_n$ for each mode.

6. **Compare to theory.** Calculate the predicted $\Delta f_n / f_n$ for each mode using the Rayleigh formula above. Weigh the rod itself to get $M$ (typically ~6 g for a 150 mm × 6 mm borosilicate rod, density 2,230 kg/m³).

7. **Repeat with different positions.** Move the putty to a different marked position and re-measure. The fingerprint should change: modes whose antinodes are near the new putty position shift most; modes with nodes near the putty barely shift.

8. **Verify reversibility.** Peel off the putty and re-measure the spectrum. Frequencies should return to the unperturbed values within the thermal drift tolerance established in Experiment 4.

> **⚙️ Failure Mode 5 — Non-Linear Acoustic Coupling**
>
> At high drive amplitudes, acoustic energy leaks between modes via non-linear elastic coupling, smearing the spectral fingerprint and reducing discrimination.
>
> Mitigations:
>
> - **Keep drive amplitude ≤ 0.5 Vpp.** This keeps the rod well within the linear regime.
> - **Verify linearity.** Measure mode amplitudes at 0.25 V, 0.50 V, and 1.00 V. Plot amplitude vs. drive voltage. The relationship should be linear (doubling voltage doubles response amplitude). If doubling drive voltage increases any mode's amplitude by more than 2.2× (exceeding the linear 2.0× by more than 10%), you have entered the non-linear regime—reduce the drive.
> - **Listen for audible ringing.** If you can clearly hear the rod vibrating (a high-pitched whine), the amplitude is too high. Reduce AWG output until the sound is barely perceptible or inaudible.

<div class="worksheet-header">
<h4>Worksheet D.4 — Perturbation Encoding Data</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy per perturbation trial. Record before/after mode frequencies and compare to Rayleigh predictions.</p>
</div>

|                                  | Trial info                    |
| -------------------------------- | ----------------------------- |
| **Trial #**                      | <span class="ex">1</span>     |
| **Putty pellet mass δm (mg)**    | <span class="ex">0.8</span>   |
| **Position x (mm from PZT end)** | <span class="ex">75.0</span>  |
| **Position x/L (fraction)**      | <span class="ex">0.500</span> |
| **Rod mass M (g)**               | <span class="ex">9.52</span>  |
| **Rod length L (mm)**            | <span class="ex">150.2</span> |
| **Temperature (°C)**             | <span class="ex">22.4</span>  |

| Mode _n_ | fₙ before (Hz)                   | fₙ after (Hz)                    | Δfₙ measured (Hz)            | Δfₙ/fₙ meas. (ppm)          | Δfₙ/fₙ predicted (ppm)      | Error (%)                 |
| -------- | -------------------------------- | -------------------------------- | ---------------------------- | --------------------------- | --------------------------- | ------------------------- |
| 1        | <span class="ex">17,693.2</span> | <span class="ex">17,692.5</span> | <span class="ex">−0.7</span> | <span class="ex">−40</span> | <span class="ex">−42</span> | <span class="ex">5</span> |
| 2        | <span class="ex">35,388.1</span> | <span class="ex">35,388.0</span> | <span class="ex">−0.1</span> | <span class="ex">−3</span>  | <span class="ex">0</span>   | <span class="ex">—</span> |
| 3        | <span class="ex">53,081.0</span> | <span class="ex">53,078.8</span> | <span class="ex">−2.2</span> | <span class="ex">−41</span> | <span class="ex">−42</span> | <span class="ex">2</span> |
| 4        | <span class="ex">70,775.3</span> | <span class="ex">70,775.2</span> | <span class="ex">−0.1</span> | <span class="ex">−1</span>  | <span class="ex">0</span>   | <span class="ex">—</span> |
| 5        | <span class="ex">88,466.1</span> | <span class="ex">88,462.4</span> | <span class="ex">−3.7</span> | <span class="ex">−42</span> | <span class="ex">−42</span> | <span class="ex">1</span> |

_After removing putty:_

| Mode _n_ | fₙ recovered (Hz)                | Δf from original (Hz)        | Recovered within ±0.5 Hz? |
| -------- | -------------------------------- | ---------------------------- | ------------------------- |
| 1        | <span class="ex">17,693.1</span> | <span class="ex">−0.1</span> | <span class="ex">Y</span> |
| 2        | <span class="ex">35,388.0</span> | <span class="ex">−0.1</span> | <span class="ex">Y</span> |
| 3        | <span class="ex">53,080.9</span> | <span class="ex">−0.1</span> | <span class="ex">Y</span> |
| 4        | <span class="ex">70,775.2</span> | <span class="ex">−0.1</span> | <span class="ex">Y</span> |
| 5        | <span class="ex">88,466.0</span> | <span class="ex">−0.1</span> | <span class="ex">Y</span> |

**Expected results.** Mode shifts should match Rayleigh predictions within 5%. The mode whose antinode is nearest the putty position will shift most; modes with nodes near the putty will barely shift. Frequencies should recover fully after putty removal. If the match is poor (\>10% error), verify that the putty mass is small compared to the rod mass ($\delta m / M \ll 1$) and that the temperature has not drifted during the measurement.

---

### D.8 Experiment 6 — Associative Recall Demonstration

**Objective:** Show that the rod physically distinguishes between matching and non-matching query patterns—the basis of CWM's O(1) nearest-neighbor search.

**Time:** 60 minutes.

**Materials:** Assembled resonator, PicoScope, silicone putty, ruler, insulated box mount, insulated enclosure.

**Procedure:**

1. **Create Pattern A.** Apply two putty pellets at the quarter-points of the rod: $x = L/4 = 37.5$ mm and $x = 3L/4 = 112.5$ mm. Record the resulting spectral fingerprint—the frequencies of modes 1–5 in their shifted positions.

2. **Build the query signal.** In the PicoScope AWG, create a multi-tone waveform composed of the five shifted frequencies from Pattern A's fingerprint. Set each tone to equal amplitude (0.1 V per tone). This is "Query A."

   _Software shortcut:_ Run `python tools/awg_waveform.py --pattern A` from the repository root. This computes Pattern A's Rayleigh-shifted frequencies and exports a ready-to-import CSV file (`query_A.csv`). In PicoScope 7: Tools → Signal Generator → Wave Type → Arbitrary → Import → select the CSV → set Amplitude to the value printed by the script (~0.40 Vpp) and Sample Rate to 1 MS/s. For all four patterns at once, use `--all`. Run with `--help` for additional options (custom putty mass, rod length, number of modes).

3. **Measure the matched response.** Drive the rod with Query A. The rod contains Pattern A, so the query _matches_ the stored pattern. Record the peak response amplitude in dB from the FFT.

4. **Create Pattern B.** Remove Pattern A's putty. Apply two pellets at the third-points: $x = L/3 = 50$ mm and $x = 2L/3 = 100$ mm. Record Pattern B's fingerprint.

5. **Drive with Query A (mismatched).** Replay Query A—the waveform built from Pattern A's frequencies. The rod now contains Pattern B, so the query does _not_ match. Record the peak response amplitude. It should be significantly lower than in step 3.

6. **Drive with Query B (matched).** Build a new multi-tone waveform from Pattern B's frequencies. Drive the rod with this Query B. The rod now matches, so the response should be strong. Record the amplitude.

7. **Calculate the discrimination margin.** The difference in dB between the matched response and the best non-matched response is the discrimination margin. A margin ≥15 dB means the correct match produces ≥30× more power than the closest incorrect match.

8. **Record results** in Worksheet D.5.

<div class="worksheet-header">
<h4>Worksheet D.5 — Associative Recall Discrimination</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy per discrimination test. Log response amplitudes for matched vs. unmatched query patterns.</p>
</div>

| Pattern stored on rod | Query driven           | Peak response (dB)          | Match? |
| --------------------- | ---------------------- | --------------------------- | ------ |
| Pattern A             | Query A (matching)     | <span class="ex">−22</span> | ✓      |
| Pattern B             | Query A (non-matching) | <span class="ex">−44</span> | ✗      |
| Pattern B             | Query B (matching)     | <span class="ex">−23</span> | ✓      |

| Metric                                             | Value                             |
| -------------------------------------------------- | --------------------------------- |
| **Discrimination margin (matched − non-matched):** | <span class="ex">**21 dB**</span> |
| **Power ratio (10^(margin/10)):**                  | <span class="ex">**126×**</span>  |
| **Sufficient for reliable detection? (≥15 dB)**    | <span class="ex">Y ✓</span>       |

**Expected results.** The discrimination margin should be 15–25 dB, meaning the matching pattern produces 30–300× more acoustic power than a non-matching pattern. If the margin is below 10 dB, check that (a) the two putty patterns are placed at genuinely different positions, (b) the drive amplitude is in the linear regime (≤0.5 V per tone), and (c) the query frequencies accurately match the stored pattern's measured frequencies.

---

### D.9 Experiment 7 — CW Precision Readout (Bowing vs. Ringing)

**Objective:** Demonstrate that continuous-wave (CW) excitation with lock-in detection yields higher SNR than impulse readout—and experience the difference physically by "bowing" the rod with a wet finger, just as a glass harmonica is played.

**Time:** 60 minutes.

**Materials:** Assembled resonator, PicoScope, BNC cable, insulated box mount, insulated enclosure, small bowl of water.

**Background.** Experiments 1–6 use impulse readout: strike the rod, listen to it ring down, measure the FFT. This is fast (one ringdown time $\tau \approx 180$ ms) but limited in SNR—the measurement window is fixed at $\tau$, and all the noise within the bandwidth $\sim 1/\tau$ contributes. An alternative is CW readout: drive the rod continuously at a single mode frequency and measure the steady-state response. A lock-in detection technique—multiplying the response by the drive signal and averaging—rejects all noise outside a narrow bandwidth $\sim 1/(2T_{\text{int}})$. The SNR gain over impulse is:

$$\text{Gain (dB)} = 10\log_{10}\!\left(\frac{T_{\text{int}}}{\tau}\right)$$

At $T_{\text{int}} = 1$ s: +7.5 dB. At $T_{\text{int}} = 10$ s: +17.5 dB. At $T_{\text{int}} = 60$ s: +25.2 dB (see Figure 15 in the Illustration Plates). This is the same physics that makes a glass harmonica so expressive: the performer's sustained finger contact provides continuous energy input, allowing the bowl to reach full amplitude and sustain it indefinitely—something a single tap cannot do.

**Part A: Electronic CW Readout**

1. **Set the CW drive.** Configure the PicoScope AWG to output a _continuous_ sine wave at your rod's measured $f_1$ from Experiment 2. Set amplitude to 0.2 V. Let it run—do not stop it.

2. **Wait for ring-up.** The rod's amplitude builds exponentially with the same time constant $\tau$ as the ring-down. After $3\tau \approx 540$ ms, the rod has reached 95% of its steady-state amplitude. Wait at least 1 second.

3. **Capture a 1-second record.** In PicoScope, set the timebase to capture exactly 1 second of Channel A data. Save the raw waveform (.csv export).

4. **Software lock-in detection.** In a spreadsheet or Python script, perform the lock-in calculation:
   - Generate a reference signal: $\text{ref}(t) = \sin(2\pi f_1 t)$.
   - Multiply the captured signal by the reference: $\text{product}(t) = \text{signal}(t) \times \text{ref}(t)$.
   - Average the product over the 1-second window. This is the lock-in output—proportional to the mode amplitude, with all out-of-band noise rejected.
   - Record the lock-in amplitude as $A_{\text{CW,1s}}$.

5. **Repeat with 10-second capture.** Extend the AWG run and capture 10 seconds. Repeat the lock-in calculation. Record $A_{\text{CW,10s}}$.

6. **Compare to impulse.** From Experiment 2, you have the impulse ring-down peak amplitude $A_{\text{impulse}}$. Calculate the SNR improvement:

$$\text{Gain (dB)} = 20\log_{10}\!\left(\frac{A_{\text{CW}}}{A_{\text{impulse}}}\right)$$

Expected: ~7.5 dB for 1-second CW, ~17.5 dB for 10-second CW.

**Part B: Bowing the Rod (the Glass Harmonica Experiment)**

This part requires no electronics—just your hands and ears (plus the PZT to record what happens).

7. **Wet your finger.** Dip one finger in the bowl of water. You want a thin, even film of moisture—not dripping wet.

8. **Bow the rod.** With the PicoScope recording on Channel A (long timebase, ~5 seconds), run your wet finger firmly and steadily along the length of the rod, maintaining even pressure. The finger creates stick-slip friction that excites the rod's longitudinal modes, exactly as a wet finger on a wineglass rim excites its radial modes. You should hear a faint singing tone and see a sustained oscillation on the PicoScope screen.

9. **Compare the waveform.** The bowed response should show sustained, roughly constant-amplitude oscillation for as long as your finger maintains contact—in contrast to the exponentially decaying impulse ring-down from Experiment 2. _This is the glass harmonica in action._

10. **Measure bowed frequency.** Switch to FFT mode while bowing. The dominant peak should fall at or near $f_1$. The excitation is broadband (stick-slip friction contains many frequencies), so you may also see modes 2 and 3 responding.

11. **Record results** in Worksheet D.6.

<div class="worksheet-header">
<h4>Worksheet D.6 — CW Readout Comparison</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy per CW session. Compare impulse ring-down vs. continuous-wave lock-in readout.</p>
</div>

| Measurement                                                           | Value                                                        |
| --------------------------------------------------------------------- | ------------------------------------------------------------ |
| Impulse ring-down peak amplitude $A_{\text{impulse}}$ (mV)            | <span class="ex">12.3</span>                                 |
| CW lock-in amplitude, 1 s ($A_{\text{CW,1s}}$) (mV)                   | <span class="ex">28.4</span>                                 |
| CW lock-in amplitude, 10 s ($A_{\text{CW,10s}}$) (mV)                 | <span class="ex">91.2</span>                                 |
| **Gain (1 s): 20·log₁₀($A_{\text{CW,1s}}$ / $A_{\text{impulse}}$)**   | <span class="ex">**7.3 dB**</span>                           |
| **Gain (10 s): 20·log₁₀($A_{\text{CW,10s}}$ / $A_{\text{impulse}}$)** | <span class="ex">**17.4 dB**</span>                          |
| Expected gain (1 s): 7.5 dB                                           | <span class="ex">Y ✓</span>                                  |
| Expected gain (10 s): 17.5 dB                                         | <span class="ex">Y ✓</span>                                  |
| Wet-finger bowing: sustained oscillation observed?                    | <span class="ex">Y ✓</span>                                  |
| Bowed frequency (Hz)                                                  | <span class="ex">17,694</span>                               |
| Bowed duration (s)                                                    | <span class="ex">3.2</span>                                  |
| Notes on bowing technique                                             | <span class="ex">Slow steady stroke, 2nd attempt best</span> |

**Expected results.** The electronic CW gains should match predictions within ±3 dB (measurement noise, PZT coupling variability, and frequency drift all widen the tolerance). The wet-finger bowing should produce sustained oscillation at $f_1$ lasting as long as the finger maintains contact—typically 2–5 seconds per stroke. Students who have played a glass harp will find this immediately intuitive.

> **Why this matters.** Experiments 1–6 demonstrate CWM as a _rung bell_—impulse excitation, finite-duration readout. This experiment demonstrates CWM as a _bowed string_—continuous excitation, arbitrarily long integration, progressively higher precision. The two-phase readout architecture proposed in §2.3 combines both: ring the bell (fast, broadband) to find the answer, then bow the string (slow, precise) to read it exactly.

---

### D.10 Experiment 8 — Rewritable Encoding with Water Drops

**Objective:** Demonstrate rewritable spectral encoding using water drops as removable mass perturbations—the transition from glass harmonica (fixed tuning) to Franklin's armonica (reconfigurable).

**Time:** 45 minutes.

**Materials:** Assembled resonator, PicoScope, plastic transfer pipettes, water, insulated box mount, insulated enclosure, ruler, fine-tip marker, digital thermometer.

**Background.** In a glass harmonica, each bowl's pitch is set by its geometry—grind it to a specific diameter and thickness, and the frequency is fixed forever. But adding water to a bowl lowers its pitch by increasing the effective vibrating mass. The performer cannot change the glass, but _can_ change the water level. This is precisely the Rayleigh perturbation mechanism: water at position $x$ shifts mode $n$ by an amount proportional to $\sin^2(n\pi x/L)$. Unlike putty (Experiment 5), water evaporates—making the perturbation _rewritable_. This experiment demonstrates the harmonica-to-armonica transition: write a pattern with water, read the shifted spectrum, let it evaporate (erase), write a different pattern, and confirm the spectrum changes.

**Procedure:**

1. **Prepare.** Place the resonator horizontally in the insulated box mount inside the insulated enclosure. Equilibrate for 15 minutes with the thermometer monitoring temperature. Ensure the rod surface is clean and dry.

2. **Record the unperturbed spectrum (Pattern 0).** Chirp the rod and record the FFT. Log frequencies of modes 1–5.

3. **Write Pattern 1.** Using a transfer pipette, place one small water drop (~2 mm diameter, ~4 µL) at the rod midpoint ($x = L/2 = 75$ mm). The water should sit as a bead on the glass surface. Record the time.

4. **Read Pattern 1.** Immediately chirp the rod and record the FFT. Log the shifted mode frequencies. Note: mode 1 (which has an antinode at $L/2$) should shift the most. Mode 2 (which has a _node_ at $L/2$) should shift the least—confirming position-dependent encoding.

5. **Erase Pattern 1.** Gently blot the water drop with a lint-free cloth, or simply wait 3–5 minutes for it to evaporate. Re-measure the spectrum and confirm frequencies return to within ±0.5 Hz of Pattern 0.

6. **Write Pattern 2.** Place a water drop at $x = L/4 = 37.5$ mm. Immediately read the spectrum. The pattern of mode shifts should be _different_ from Pattern 1—mode 2 (antinode at $L/4$) now shifts strongly, while mode 1 shifts less than before.

7. **Erase Pattern 2.** Remove the water and confirm spectral recovery.

8. **Write Pattern 3 (two drops).** Place drops at both $L/4$ and $3L/4$. The resulting shift pattern is distinct from both Pattern 1 and Pattern 2.

9. **Record results** in Worksheet D.7.

<div class="worksheet-header">
<h4>Worksheet D.7 — Rewritable Water-Drop Encoding</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy per rewritability session. Track spectra across write / erase / rewrite cycles.</p>
</div>

| Mode _n_ | f (Pattern 0)                    | f (Pattern 1: $L/2$)             | Δf₁ (Hz)                      | f (Pattern 2: $L/4$)             | Δf₂ (Hz)                     | f (Pattern 3: $L/4 + 3L/4$)      | Δf₃ (Hz)                      |
| -------- | -------------------------------- | -------------------------------- | ----------------------------- | -------------------------------- | ---------------------------- | -------------------------------- | ----------------------------- |
| 1        | <span class="ex">17,693.2</span> | <span class="ex">17,689.5</span> | <span class="ex">−3.7</span>  | <span class="ex">17,691.3</span> | <span class="ex">−1.9</span> | <span class="ex">17,689.5</span> | <span class="ex">−3.7</span>  |
| 2        | <span class="ex">35,388.1</span> | <span class="ex">35,388.0</span> | <span class="ex">−0.1</span>  | <span class="ex">35,380.7</span> | <span class="ex">−7.4</span> | <span class="ex">35,373.2</span> | <span class="ex">−14.9</span> |
| 3        | <span class="ex">53,081.0</span> | <span class="ex">53,069.9</span> | <span class="ex">−11.1</span> | <span class="ex">53,075.4</span> | <span class="ex">−5.6</span> | <span class="ex">53,069.9</span> | <span class="ex">−11.1</span> |
| 4        | <span class="ex">70,775.3</span> | <span class="ex">70,775.2</span> | <span class="ex">−0.1</span>  | <span class="ex">70,775.2</span> | <span class="ex">−0.1</span> | <span class="ex">70,775.2</span> | <span class="ex">−0.1</span>  |
| 5        | <span class="ex">88,466.1</span> | <span class="ex">88,447.5</span> | <span class="ex">−18.6</span> | <span class="ex">88,456.8</span> | <span class="ex">−9.3</span> | <span class="ex">88,447.5</span> | <span class="ex">−18.6</span> |

| Verification                                                    | Result                      |
| --------------------------------------------------------------- | --------------------------- |
| Pattern 0 recovered after erasing Pattern 1? (±0.5 Hz)          | <span class="ex">Y ✓</span> |
| Pattern 0 recovered after erasing Pattern 2? (±0.5 Hz)          | <span class="ex">Y ✓</span> |
| Pattern 1 and Pattern 2 are spectrally distinguishable?         | <span class="ex">Y ✓</span> |
| Pattern 3 is distinct from both Pattern 1 and Pattern 2?        | <span class="ex">Y ✓</span> |
| **Total distinct patterns written and read in this experiment** | <span class="ex">3</span>   |

**Expected results.** Water drops are lighter than putty pellets, so frequency shifts will be smaller—typically 0.2–2 Hz per mode, depending on drop volume. The thermal enclosure is essential here to keep drift below the perturbation signal. The key observation is that the three patterns produce three _different_ spectral fingerprints, and that erasing (removing water) fully recovers the baseline—demonstrating the write/read/erase cycle. If shifts are too small to resolve, use larger drops or a more sensitive frequency measurement (CW lock-in from Experiment 7 provides higher precision).

> **The Franklin insight.** This experiment turns the glass rod into a primitive armonica. The glass itself never changes—only the water does. You have just demonstrated the separation principle described in Paper II §3: the rod is optimized for resonance quality (Q), and the "write medium" (water) is a separate, removable layer. Franklin would recognize this immediately: same glass, different tuning, reconfigurable.

---

### D.11 Experiment 9 — Packed-Array Associative Recall

**Objective:** Show that a multi-rod array can identify a stored pattern from a noisy or partial query—the physical basis of CWM's content-addressable memory.

**Time:** 90 minutes.

**Materials:** 3–4 assembled resonators (from Experiment 1), PicoScope, silicone putty, ruler, insulated box with cardboard dividers (single-row template T.2A), insulated enclosure, masking tape, fine-tip marker.

**Background.** In Experiment 6 you demonstrated that a single rod distinguishes between matching and non-matching queries. This experiment scales the principle to a packed array: multiple rods, each storing a different perturbation pattern, are queried simultaneously. The rod whose stored fingerprint best matches the query produces the strongest acoustic response—a physical implementation of associative recall. The entire search completes in one acoustic propagation cycle (~3.8 µs at MEMS scale), regardless of how many rods are in the array.

Mathematically, this is equivalent to a Hopfield network (§2.3): each rod is a "neuron," the perturbation-defined spectrum is its "weight vector," and the query is the input state. The rod with the highest inner product with the query wins—and that inner product is computed by wave interference, not by a processor.

**Procedure:**

1. **Build the array.** Assemble 3–4 rods, each with its PZT disc, into the multi-rod mount using cardboard dividers inside the insulated box. Label them Rod A, B, C, D. Equilibrate for 15 minutes.

2. **Write distinct patterns.** Apply unique putty configurations to each rod:
   - **Rod A:** Two pellets at $L/4$ (37.5 mm) and $3L/4$ (112.5 mm).
   - **Rod B:** Two pellets at $L/3$ (50 mm) and $2L/3$ (100 mm).
   - **Rod C:** One pellet at $L/2$ (75 mm).
   - **Rod D (if using 4 rods):** Two pellets at $L/5$ (30 mm) and $4L/5$ (120 mm).

3. **Record each fingerprint.** Chirp each rod individually and record the FFT peak frequencies for modes 1–5. These are the "stored patterns."

4. **Build queries.** For each rod, create a multi-tone waveform from its five shifted mode frequencies (same procedure as Experiment 6, step 2). Label these Query A, B, C, D.

   _Software shortcut:_ `python tools/awg_waveform.py --all` generates all four query waveforms (CSV + WAV) in one step. Import each into the PicoScope AWG as described in Experiment 6.

5. **Parallel query test.** Wire all rods' PZTs in parallel (see "Multi-Rod Setup" in Section D.2a) and drive the array with Query A. The aggregate FFT on Channel A shows the combined response — the matching rod's peaks will dominate. Record the peak response amplitude. To verify which rod is responding, optionally connect Channel B to individual rods one at a time while driving all rods on the parallel bus.

6. **Record the discrimination matrix.** Repeat step 5 for Query B, Query C, and Query D. Fill in Worksheet D.8.

7. **Verify correct identification.** For each query, the target rod (the one whose pattern matches the query) should produce the highest response. Check that all four diagonal entries in the discrimination matrix are the highest in their row.

8. **Test with noisy queries.** Detune one of Query A's five frequencies by +5% to simulate a noisy or partial query. Drive all rods and check whether Rod A still wins (it should, because 4 of 5 frequencies still match). Increase the detuning and observe when recall fails.

<div class="worksheet-header">
<h4>Worksheet D.8 — Packed-Array Associative Recall</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy per array configuration. Log each rod's response amplitude (dB) when driven by each query pattern.</p>
</div>

| Query driven ↓ / Rod response → | Rod A (dB)                      | Rod B (dB)                      | Rod C (dB)                      | Rod D (dB)                      | Best match                      |
| ------------------------------- | ------------------------------- | ------------------------------- | ------------------------------- | ------------------------------- | ------------------------------- |
| Query A                         | <span class="ex">**−22**</span> | <span class="ex">−41</span>     | <span class="ex">−38</span>     | <span class="ex">−44</span>     | <span class="ex">Rod A ✓</span> |
| Query B                         | <span class="ex">−40</span>     | <span class="ex">**−23**</span> | <span class="ex">−39</span>     | <span class="ex">−43</span>     | <span class="ex">Rod B ✓</span> |
| Query C                         | <span class="ex">−37</span>     | <span class="ex">−42</span>     | <span class="ex">**−21**</span> | <span class="ex">−40</span>     | <span class="ex">Rod C ✓</span> |
| Query D                         | <span class="ex">−43</span>     | <span class="ex">−39</span>     | <span class="ex">−41</span>     | <span class="ex">**−24**</span> | <span class="ex">Rod D ✓</span> |

| Metric                                             | Value                             |
| -------------------------------------------------- | --------------------------------- |
| **Mean diagonal (matched) amplitude (dB):**        | <span class="ex">**−22.5**</span> |
| **Mean off-diagonal (mismatched) amplitude (dB):** | <span class="ex">−40.6</span>     |
| **Mean discrimination margin (dB):**               | <span class="ex">**18.1**</span>  |
| **All diagonal entries are row maxima? (Y/N)**     | <span class="ex">Y ✓</span>       |
| **Noisy query (5% detune): correct recall? (Y/N)** | <span class="ex">Y ✓</span>       |

**Expected results.** The discrimination matrix should show a clear diagonal: each query produces 15–25 dB more power at its target rod than at any other. If using only 2 PicoScope channels (one for the shared drive, one for readout), you can drive all rods via a Y-cable from the AWG and read each rod's response sequentially—the key physics is that the rod's resonant response depends only on whether its modes align with the drive frequencies, not on how many other rods are present.

> **Why this works.** Each rod is a physical matched filter. The query contains frequencies $\{f_1', f_2', \ldots, f_5'\}$. If those frequencies match Rod A's resonances, Rod A rings loudly; Rod B's resonances are at different frequencies, so it barely responds. The ratio of matched-to-mismatched response is the discrimination margin. In a MEMS array with 9,380 modes per rod and 1,294 stored patterns, this same principle extends to massively parallel associative search in a single acoustic cycle.

---

### D.12 Experiment 10 — Nearest-Neighbor Search

**Objective:** Demonstrate that the rod array naturally performs nearest-neighbor search: when the query is an interpolation between two stored patterns, the closest matching rod produces the strongest response, and the transition point occurs at the midpoint.

**Time:** 60 minutes.

**Materials:** Packed array from Experiment 9 (at least 2 patterned rods), PicoScope.

**Background.** Nearest-neighbor search is the foundation of classification, recommendation, and similarity-based retrieval. In a conventional system, finding the closest match in a database of $M$ items requires $O(M)$ distance computations (or $O(\log M)$ with tree indexing). In a CWM array, it takes one acoustic propagation cycle regardless of $M$.

The test: construct a query that sits "between" two stored patterns. At the exact midpoint, the query should be equidistant from both, and the best match should transition from one rod to the other.

**Procedure:**

1. **Select two rods.** Use Rod A and Rod B from Experiment 9, with their distinct putty patterns in place.

2. **Build the endpoint queries.** You already have Query A (5 tones at Rod A's mode frequencies) and Query B (5 tones at Rod B's mode frequencies) from Experiment 9.

3. **Create interpolated queries.** For each mode $n$ (1–5), compute a blended frequency:

$$f_n(\alpha) = (1 - \alpha) \cdot f_n^{(A)} + \alpha \cdot f_n^{(B)}$$

Build 5 interpolated queries at $\alpha = 0.0, 0.25, 0.50, 0.75, 1.0$. (The first and last are just Query A and Query B.)

4. **Drive and measure.** For each interpolated query, drive both rods simultaneously and record each rod's response amplitude.

5. **Plot the crossover.** Plot Rod A's and Rod B's response as a function of $\alpha$. The curves should cross near $\alpha = 0.5$. Record the actual crossover point.

6. **Record results** in Worksheet D.9.

<div class="worksheet-header">
<h4>Worksheet D.9 — Nearest-Neighbor Search Crossover</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy. Record response amplitudes across the interpolation sweep to verify crossover near α = 0.5.</p>
</div>

| α (interpolation) | Rod A response (dB)             | Rod B response (dB)             | Best match                    |
| ----------------- | ------------------------------- | ------------------------------- | ----------------------------- |
| 0.00 (= Query A)  | <span class="ex">**−22**</span> | <span class="ex">−41</span>     | <span class="ex">Rod A</span> |
| 0.25              | <span class="ex">**−26**</span> | <span class="ex">−35</span>     | <span class="ex">Rod A</span> |
| 0.50              | <span class="ex">−31</span>     | <span class="ex">**−30**</span> | <span class="ex">Rod B</span> |
| 0.75              | <span class="ex">−37</span>     | <span class="ex">**−25**</span> | <span class="ex">Rod B</span> |
| 1.00 (= Query B)  | <span class="ex">−42</span>     | <span class="ex">**−23**</span> | <span class="ex">Rod B</span> |

| Metric                                           | Value                            |
| ------------------------------------------------ | -------------------------------- |
| **Crossover α (where best match switches A→B):** | <span class="ex">**0.50**</span> |
| **Expected crossover:**                          | 0.50                             |
| **Crossover error (actual − expected):**         | <span class="ex">0.00</span>     |

**Expected results.** The crossover should occur near $\alpha = 0.5$ (within ±0.15). At the crossover, both rods respond at roughly equal amplitude. Away from the crossover, the nearer rod dominates by 10–20 dB. This demonstrates that the rods' acoustic responses naturally rank by similarity to the query—exactly the behavior needed for nearest-neighbor search.

> **O(1) scaling.** The key observation: you could add 100 more rods to the array, and the search would still take the same amount of time—one acoustic cycle. Each rod evaluates its own match score simultaneously and independently. This is why CWM claims O(1) nearest-neighbor search: the computation time is set by the speed of sound in glass, not by the number of candidates.

---

### D.13 Experiment 11 — In-Situ Boolean Computation via Mode Superposition

**Objective:** Demonstrate that Boolean operations (AND, OR, XOR) can be computed in a single acoustic cycle by superposing two perturbation patterns' spectral responses and applying amplitude thresholds—zero additional hardware required.

**Time:** 60 minutes.

**Materials:** 2 assembled resonators with distinct perturbation patterns (from Experiment 9), PicoScope, BNC Y-adapter or alligator-clip junction.

**Background.** CWM's modes are linear oscillators: when two signals are applied simultaneously, the resulting amplitude at each frequency is the _sum_ of the individual amplitudes. If Pattern A encodes bit "1" at mode 3 (high amplitude) and Pattern B encodes bit "0" at mode 3 (low amplitude), the combined amplitude at mode 3 is high + low = medium. The combined amplitudes across all modes fall into three natural clusters:

| A bit | B bit | Combined level | AND | OR  | XOR |
| ----- | ----- | -------------- | --- | --- | --- |
| 0     | 0     | Low            | 0   | 0   | 0   |
| 0     | 1     | Medium         | 0   | 1   | 1   |
| 1     | 0     | Medium         | 0   | 1   | 1   |
| 1     | 1     | High           | 1   | 1   | 0   |

- **AND** = high cluster only (both bits = 1)
- **OR** = medium + high (at least one bit = 1)
- **XOR** = medium cluster only (exactly one bit = 1)

All three operations are computed from the same superposition—only the threshold changes. This is firmware, not hardware.

**Procedure:**

1. **Prepare two "binary-patterned" rods.** Using two rods from the packed array, define a coarse binary encoding across modes 1–5:
   - **Rod A "binary pattern":** Place putty at positions that shift modes 1, 3, and 5 strongly (call these bits = 1) and leave modes 2 and 4 minimally affected (bits = 0). Record which modes shift and by how much.
   - **Rod B "binary pattern":** Place putty at positions that shift modes 1, 2, and 4 (bits = 1) and leave modes 3 and 5 minimally affected (bits = 0).

   The resulting binary representations are:
   - Rod A: 1 0 1 0 1
   - Rod B: 1 1 0 1 0

2. **Measure individual spectra.** Chirp each rod separately. Record the peak amplitude at each mode frequency.

3. **Superpose the responses.** Drive both rods simultaneously with a broadband chirp. On the PicoScope FFT, you will see peaks at all mode frequencies. At each mode, the combined amplitude reflects the sum of both rods' contributions.

4. **Classify each mode.** For each mode 1–5, categorize the combined amplitude:
   - **Low** (both rods' bits = 0): the weakest combined peaks.
   - **Medium** (one rod's bit = 1, the other = 0): intermediate amplitude.
   - **High** (both rods' bits = 1): the strongest combined peaks.

5. **Extract Boolean results.** Apply the three threshold rules:
   - **AND (Rod A ∧ Rod B):** Only modes where combined amplitude is in the "High" cluster → expected result: 1 0 0 0 0 (only mode 1).
   - **OR (Rod A ∨ Rod B):** Modes in "Medium" or "High" cluster → expected result: 1 1 1 1 1 (all modes).
   - **XOR (Rod A ⊕ Rod B):** Modes in "Medium" cluster only → expected result: 0 1 1 1 1 (modes 2–5).

6. **Record results** in Worksheet D.10.

<div class="worksheet-header">
<h4>Worksheet D.10 — Boolean Computation via Mode Superposition</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Print one copy. Record individual and combined mode amplitudes, then extract Boolean operation results using threshold classification.</p>
</div>

| Mode _n_ | Rod A amp (dB)              | A bit | Rod B amp (dB)              | B bit | Combined amp (dB)           | Cluster                        | AND                       | OR                        | XOR                       |
| -------- | --------------------------- | ----- | --------------------------- | ----- | --------------------------- | ------------------------------ | ------------------------- | ------------------------- | ------------------------- |
| 1        | <span class="ex">−24</span> | 1     | <span class="ex">−25</span> | 1     | <span class="ex">−18</span> | <span class="ex">High</span>   | <span class="ex">1</span> | <span class="ex">1</span> | <span class="ex">0</span> |
| 2        | <span class="ex">−42</span> | 0     | <span class="ex">−26</span> | 1     | <span class="ex">−25</span> | <span class="ex">Medium</span> | <span class="ex">0</span> | <span class="ex">1</span> | <span class="ex">1</span> |
| 3        | <span class="ex">−23</span> | 1     | <span class="ex">−40</span> | 0     | <span class="ex">−22</span> | <span class="ex">Medium</span> | <span class="ex">0</span> | <span class="ex">1</span> | <span class="ex">1</span> |
| 4        | <span class="ex">−41</span> | 0     | <span class="ex">−24</span> | 1     | <span class="ex">−23</span> | <span class="ex">Medium</span> | <span class="ex">0</span> | <span class="ex">1</span> | <span class="ex">1</span> |
| 5        | <span class="ex">−22</span> | 1     | <span class="ex">−43</span> | 0     | <span class="ex">−21</span> | <span class="ex">Medium</span> | <span class="ex">0</span> | <span class="ex">1</span> | <span class="ex">1</span> |

| Verification                                                            | Result                        |
| ----------------------------------------------------------------------- | ----------------------------- |
| **AND computed correctly? (compare to truth table)**                    | <span class="ex">Y ✓</span>   |
| **OR computed correctly?**                                              | <span class="ex">Y ✓</span>   |
| **XOR computed correctly?**                                             | <span class="ex">Y ✓</span>   |
| **Number of modes used:**                                               | <span class="ex">5</span>     |
| **Cluster separation (High − Medium gap in dB):**                       | <span class="ex">5 dB</span>  |
| **Cluster separation (Medium − Low gap in dB):**                        | <span class="ex">15 dB</span> |
| **All three Boolean operations extracted from a single superposition?** | <span class="ex">Y ✓</span>   |

**Expected results.** With distinct perturbation patterns, the three amplitude clusters should be separated by ≥5 dB. AND is the most demanding (smallest cluster gap), while OR is the most forgiving. If cluster separation is too small, use larger putty masses to increase the amplitude contrast between "1" and "0" bits. The simulation in `exp08_boolean_compute.py` confirms ≥90% fidelity across all three operations at contrast ratios of 1.5:1 or better.

> **One superposition, three answers.** The superposed spectrum is computed by physics in a single acoustic cycle. The Boolean operation is selected _afterwards_ in firmware—by choosing where to place the threshold. No new hardware, no new measurement, no extra time. This is what the paper means by "the physics _is_ the computation."

---

### D.14 Experiment 12 — Acoustic Password Vault (Polysemic Packed Array)

**Objective:** Demonstrate a hardware security device that stores and authenticates multiple passwords in parallel using a packed glass rod array, with polysemic readout quadrupling the effective password capacity. Your laptop replaces the CMOS readout ASIC, performing exactly the same FFT → correlation → decision logic that a production chip would execute at microsecond speed.

**Time:** 90 minutes (plus enrollment time for additional passwords).

**Materials:** 4–10 assembled resonators with distinct perturbation patterns, PicoScope 2204A, BNC cables, laptop with Python 3.10+.

**Background.** Each rod's spectral fingerprint is determined by the physical mass distribution of its putty perturbations—a pattern that cannot be copied without disassembling the rod. This is a _physically unclonable function_ (PUF): the password is not stored digitally; it _is_ the geometry of the glass. Polysemic readout (Paper II §2.5) partitions the FFT mode spectrum into $C = 4$ independent subsets, each reading an orthogonal projection of the same perturbation. One physical rod stores four independent passwords.

**How polysemic works at macro scale.** Consider modes 1–20 of a single rod. Partition them into four contiguous spectral bands:

- **Channel 0:** modes 1–5 (low-frequency band)
- **Channel 1:** modes 6–10 (mid-low band)
- **Channel 2:** modes 11–15 (mid-high band)
- **Channel 3:** modes 16–20 (high-frequency band)

Each band samples a different frequency range of the rod's response. Because the Rayleigh perturbation shift $\Delta f_n / f_n = -(\Delta m / 2M) \sin^2(n\pi x/L)$ oscillates differently across each band, the shift vectors are naturally orthogonal. Higher bands also experience stronger thermoelastic damping and different PZT coupling, further decorrelating the channels.

**Procedure:**

> **Recommended: CWM Lab web UI.** Experiments 12–14 are easiest to run through the CWM Lab unified interface, which provides a browser-based UI for all three demos (vault, image search, CAM). Start the server:
>
> ```bash
> PYTHONPATH=. python tools/cwm_lab.py --port 8200
> ```
>
> Then open **http://localhost:8200** in any browser. CWM Lab auto-detects whether a PicoScope is connected and switches between hardware measurement and Rayleigh simulation accordingly. The startup banner shows `Mode: HARDWARE (PicoScope 2204A)` or `Mode: SIMULATION (Rayleigh)`. No internet is required—everything runs locally.
>
> The CLI commands below are the equivalent terminal-only workflow for users who prefer command-line tools.

1. **Prepare the packed array.** Assemble 4 rods, each with a unique putty pattern. Label them Rod 1 through Rod 4. Mount them in the insulated box using the packed-array template (T.2). Attach PZT discs to all rods; connect each PZT to the PicoScope via BNC (use one channel per rod, swapping cables between enrollment and verification steps if your PicoScope has only 2 channels).

2. **Enroll credentials.**

   **Via CWM Lab (recommended):** Open the browser UI at `http://localhost:8200`. Enter a username and passphrase, select a rod number and perturbation pattern, then click **Register**. CWM Lab drives the rod (or simulates it), computes the FFT across modes 1–20, splits the spectrum into 4 polysemic channels, and saves the channel fingerprint as the credential template. Repeat for additional users/rods. The UI shows each user's assigned rod, channel, and mode numbers.

   **Via CLI (alternative):**

   ```bash
   PYTHONPATH=. python tools/cwm_vault.py enroll --rod 1
   ```

   The tool drives a broadband chirp via the PicoScope AWG, captures the rod's response, computes the FFT across modes 1–20, and splits the spectrum into 4 polysemic channels. Each channel's amplitude vector is saved as a credential template. Repeat for all rods. This creates up to **16 passwords** (4 rods × 4 channels).

3. **Assign passwords to credentials.** In CWM Lab, credentials are assigned at registration (each username maps to a rod/channel). In the CLI workflow, each template gets a label (e.g., "email", "bank", "laptop", "VPN"). The mapping is stored locally in `data/results/vault_db.json` (CLI) or `data/results/lab/users.json` (CWM Lab).

4. **Authenticate.**

   **Via CWM Lab:** Enter the username and passphrase, then click **Authenticate**. The UI shows the Pearson correlation against the enrolled template, the pass/fail decision, the rod and channel used, and the discrimination margin. Optionally click **Hardware Proof Panel** to inspect the full spectral state (per-rod frequency tables, cross-correlation heatmaps, and the pipeline steps).

   **Via CLI (alternative):**

   ```bash
   PYTHONPATH=. python tools/cwm_vault.py verify --label email
   ```

   The tool looks up which rod and channel the label maps to, drives the appropriate query waveform, captures the response, computes the FFT for that channel's mode subset, and correlates against the enrolled template. If the correlation exceeds the threshold (default 0.85), authentication succeeds.

5. **Test attack scenarios** (CWM Lab or CLI):
   - **Wrong rod:** Swap in a different rod. Correlation should drop below threshold.
   - **Wrong channel:** Query the correct rod but decode a different polysemic channel. Correlation should be near zero (polysemic isolation).
   - **Rod removed:** Physically remove a rod from the array. That credential ceases to exist—there is nothing to hack.
   - **Slightly detuned query:** Add ±2% frequency noise to the query. Test whether the correlation margin holds (it should with 15–25 dB discrimination).

6. **Record results** in Worksheet D.11.

| Verification                                       | Result |
| -------------------------------------------------- | ------ |
| **Number of rods enrolled:**                       |        |
| **Total credentials (rods × 4 channels):**         |        |
| **Correct authentications (out of 16 attempts):**  |        |
| **False accepts (wrong rod accepted):**            |        |
| **False accepts (wrong channel accepted):**        |        |
| **Discrimination margin (dB) at correct match:**   |        |
| **Correlation at correct match (best):**           |        |
| **Correlation at wrong rod (worst):**              |        |
| **Correlation at wrong channel, same rod:**        |        |
| **Noisy query still authenticated? (Y/N at ±2%):** |        |
| **Rod-removal kills credential? (Y/N):**           |        |

**Expected results.** Correct-channel authentication should achieve correlation > 0.90. Wrong-rod and wrong-channel correlations should be < 0.20. The polysemic isolation (same rod, different channel) is the key demonstration—it proves that one physical rod genuinely stores four independent credentials, not four variations of the same one.

> **Why this matters.** A CWM chip in a USB dongle could replace YubiKeys and FIDO tokens. The password isn't stored digitally anywhere—it's encoded as the physical mass distribution of the glass. There's nothing to extract with a logic analyser, nothing to clone without nanometre-precision lithography, and nothing to hack remotely. A 2026 study demonstrated that femtosecond laser-written borosilicate waveguides outperform silicon for coherent quantum receivers (Peri et al., _Advanced Photonics_ 2026)—their photonic domain, our acoustic one, the same substrate advantage.

---

### D.15 Experiment 13 — Acoustic Image Search (Nearest-Neighbor Visual Retrieval)

**Objective:** Encode a library of images as spectral fingerprints across a packed rod array, then demonstrate that querying with a new image finds the closest visual match—in parallel, across all rods, in one acoustic cycle. This is the core operation behind edge AI vision systems (drone inspection, face recognition), demonstrated at macro scale.

**Time:** 90 minutes (plus image library preparation).

**Materials:** 4–10 assembled resonators with distinct perturbation patterns, PicoScope 2204A, laptop with Python 3.10+, a set of 16–40 reference images (provided as a sample library in `data/image_search/` or use your own).

**Background.** Every image can be reduced to a compact feature vector via a perceptual hash—a short numeric fingerprint that captures the image's visual essence. Two visually similar images produce similar hashes; two dissimilar images produce different hashes. The CWM image search tool maps each hash to a set of perturbation-shift targets, uses each rod's polysemic channels to store multiple image fingerprints, and finds the closest match by acoustic correlation.

**How the mapping works.** A perceptual hash reduces an image to a vector of $N$ values (typically 8–64 dimensions). The tool maps each hash dimension to a target frequency shift at one mode—larger hash values map to larger shifts. The resulting target vector becomes the "ideal query" for that image. At enrollment, we measure each rod's actual fingerprint across all polysemic channels and assign images to the rod/channel combination whose actual fingerprint most closely matches the image's target vector.

**Procedure:**

1. **Prepare the image library.** Collect 16+ reference images (JPEG or PNG). The tool accepts any images—corrosion patterns, faces, product photos, symbols—whatever your demonstration scenario requires. For the CLI workflow, place them in `data/image_search/library/`.

2. **Enroll the library:**

   **Via CWM Lab (recommended):** Open `http://localhost:8200`, register a user (if not already), then drag-and-drop images onto the upload area—or click to browse. Each image is perceptual-hashed (average hash, 64 bits), mapped to the best-matching rod/channel slot, and enrolled automatically. The UI shows the rod/channel assignment and remaining capacity.

   **Via CLI (alternative):**

   ```bash
   PYTHONPATH=. python tools/cwm_image_search.py enroll \
       --library data/image_search/library/ \
       --rods 4 --channels 4
   ```

   The tool:
   - Computes a perceptual hash for each image (average hash, 64 bits)
   - Measures each rod's spectral fingerprint across 4 polysemic channels (via PicoScope chirp-and-capture if `--live` flag is set, or from saved templates)
   - Maps each image to the rod/channel with the best fingerprint match
   - Stores the assignment in `data/results/image_db.json`

3. **Query with a new image:**

   **Via CWM Lab (recommended):** Click the **Webcam Search** button to open a live camera feed and match faces or objects in real time. Or drag a query image onto the upload area—the UI displays the best match, correlation score, rod/channel assignment, and a thumbnail of the matched library image.

   **Via CLI (alternative):**

   ```bash
   PYTHONPATH=. python tools/cwm_image_search.py query \
       --image data/image_search/query/test_photo.jpg
   ```

   The tool computes the query image's perceptual hash, generates the corresponding multi-tone query waveform, and—if running with PicoScope—drives the array and captures responses. In simulation mode (default, no hardware required), it computes the expected correlation against all enrolled fingerprints.

   Output:

   ```
   Query: test_photo.jpg
   Best match: library/corrosion_004.jpg (Rod 2, Channel 1)
   Correlation: 0.937
   Runner-up: library/corrosion_007.jpg (Rod 3, Channel 0) at 0.412
   Margin: 7.2 dB
   ```

4. **Run the ranked retrieval test.** Query with each library image to verify self-retrieval:

   ```bash
   PYTHONPATH=. python tools/cwm_image_search.py test --library data/image_search/library/
   ```

   The tool queries each image against the full library and reports:
   - **Rank-1 accuracy**: percentage of images that retrieve themselves as the top match
   - **Mean discrimination margin** (dB)
   - **Confusion pairs**: which images are hardest to distinguish

5. **Record results** in Worksheet D.12.

| Verification                                  | Result |
| --------------------------------------------- | ------ |
| **Library size (images):**                    |        |
| **Number of rods used:**                      |        |
| **Effective capacity (rods × 4 channels):**   |        |
| **Rank-1 self-retrieval accuracy (%):**       |        |
| **Mean discrimination margin (dB):**          |        |
| **Worst-case margin (dB):**                   |        |
| **Number of confusion pairs (<5 dB margin):** |        |
| **Query time (per image):**                   |        |

**Expected results.** With well-chosen images (visually distinct), rank-1 accuracy should be 100% for up to 16 images (4 rods × 4 polysemic channels). Discrimination margins of 10–20 dB are typical. Visually similar images (e.g., two photos of the same scene with different lighting) will show reduced margins—this is correct physics, not a failure.

> **O(1) visual search.** Adding a hundred more rods to the array does not increase the search time—every rod evaluates its match in parallel. At MEMS scale, a 1 cm³ module would search 142,000 stored images in 3.8 µs. This experiment demonstrates that the physics works at macro scale; the MEMS chip scales the speed and density.

---

### D.16 Experiment 14 — Acoustic Content-Addressable Memory (CAM Lookup Table)

**Objective:** Demonstrate a content-addressable lookup table where acoustic queries retrieve stored key→value pairs by spectral correlation. This is the purest demonstration of CWM replacing TCAM/CAM hardware used in network routers, intrusion detection systems, and database accelerators.

**Time:** 60 minutes.

**Materials:** 4–10 assembled resonators, PicoScope 2204A, laptop with Python 3.10+.

**Background.** A content-addressable memory (CAM) is a lookup table that you search by _content_ rather than by address. You present a key, and the CAM returns the matching value—in parallel, across all entries, in one cycle. Traditional CAMs use specialised SRAM circuits (TCAMs) that consume significant power. CWM performs the same operation acoustically: each rod/channel stores one key→value entry, and the query waveform acts as the key.

**How it works.** Each rod's perturbation pattern defines a spectral fingerprint—this is the "key." The "value" is an arbitrary data payload associated with that fingerprint in a lookup table stored on the laptop. When a query waveform is driven into the array, the rod whose fingerprint best matches the query responds most strongly. The laptop identifies the winning rod/channel and returns the associated value.

**Procedure:**

1. **Define the lookup table.** Create entries mapping keys to values. The keys are spectral fingerprints (determined by each rod's putty pattern); the values can be anything—DNS hostnames, routing prefixes, threat signatures, codebook entries.

   Example table (4 rods × 4 polysemic channels = 16 entries):

   | Rod | Channel | Key (fingerprint) | Value                |
   | --- | ------- | ----------------- | -------------------- |
   | 1   | 0       | auto-enrolled     | 192.168.1.1          |
   | 1   | 1       | auto-enrolled     | 10.0.0.1             |
   | 1   | 2       | auto-enrolled     | dns.google (8.8.8.8) |
   | 1   | 3       | auto-enrolled     | gateway.local        |
   | 2   | 0       | auto-enrolled     | THREAT:MIRAI         |
   | ... | ...     | ...               | ...                  |

2. **Enroll the table:**

   **Via CWM Lab (recommended):** The CWM Lab server automatically initialises all rod fingerprints at startup (4 rods × 4 channels = 16 slots). Each registered user occupies one slot, effectively creating a CAM entry where the _key_ is the spectral fingerprint and the _value_ is the user record. To enroll explicit key→value entries, use the CLI tool below.

   **Via CLI (alternative):**

   ```bash
   PYTHONPATH=. python tools/cwm_cam.py enroll --rods 4 --table data/cam/routing_table.csv
   ```

   The tool chirps each rod, captures the full fingerprint across all polysemic channels, and associates each channel with a table row. The key is the measured fingerprint; the value is the user-provided data field.

3. **Query by key:**

   ```bash
   PYTHONPATH=. python tools/cwm_cam.py lookup --rod 2 --channel 0
   ```

   Or, for a content-addressed search (present a query waveform and let the array find the match):

   ```bash
   PYTHONPATH=. python tools/cwm_cam.py search --query-pattern A
   ```

   The tool drives the query, captures all rod responses, identifies the winner by highest correlation, and returns the associated value:

   ```
   Query matched: Rod 1, Channel 0 (correlation: 0.962)
   Value: 192.168.1.1
   Lookup time: 42 ms (laptop) → 3.8 µs at MEMS scale
   ```

4. **Test error tolerance.** Corrupt the query by adding ±5% frequency noise:

   ```bash
   PYTHONPATH=. python tools/cwm_cam.py search --query-pattern A --noise 0.05
   ```

   The correct entry should still win (demonstrating nearest-neighbor error correction).

5. **Test partial-key lookup.** Query with only a subset of mode frequencies (e.g., modes 1–3 out of 1–5):

   ```bash
   PYTHONPATH=. python tools/cwm_cam.py search --query-pattern A --modes 3
   ```

   With fewer modes the margin shrinks, but the correct entry should still be the top match.

6. **Record results** in Worksheet D.13.

| Verification                                | Result |
| ------------------------------------------- | ------ |
| **Table size (entries):**                   |        |
| **Number of rods used:**                    |        |
| **Effective capacity (rods × 4 channels):** |        |
| **Correct lookups (out of N attempts):**    |        |
| **Mean correlation at correct match:**      |        |
| **Mean correlation at best wrong match:**   |        |
| **Discrimination margin (dB):**             |        |
| **Noisy query correct? (Y/N at ±5%):**      |        |
| **Partial-key correct? (Y/N at 3 modes):**  |        |
| **Lookup time (ms, laptop):**               |        |

**Expected results.** With 4 rods × 4 channels = 16 CAM entries, all lookups should return the correct value. Noisy queries (±5%) should succeed with reduced margin. Partial-key queries (3 of 5 modes) should usually succeed but may fail for closely-spaced fingerprints. The key metric is the discrimination margin: ≥10 dB means reliable lookup; <5 dB indicates the table is near capacity.

> **From laptop to line card.** Your laptop performs the same FFT → correlate → lookup pipeline that a CMOS readout ASIC would execute. At MEMS scale, a 1 cm³ CWM CAM module would hold 142,000 × 4 = 568,000 entries and complete a full-table search in 3.8 µs at < 5 W. Current TCAMs peak at ~64K entries per chip at 15+ W.

---

### D.16a Experiment 15 — 2D Plate Mode Survey (Chladni Extension)

**Objective:** Measure the bending-mode spectrum of a fused-quartz plate with edge-coupled PZTs and confirm the predicted 9–11× mode-count gain over the 1D rod baseline.

**Time:** 60–90 minutes (including PZT bonding cure time).

**Materials:**

| Item               | Specification                      | Source (ASIN)    |
| ------------------ | ---------------------------------- | ---------------- |
| Fused-quartz plate | 100 × 100 × 1 mm, Lab UV-Vis grade | B0DWZTGBK8 ($16) |
| PZT discs × 2      | 10 mm with leads (from core BOM)   | B08R581G3H       |
| Cyanoacrylate      | Thin-viscosity (from core BOM)     | B0DT14TGDY       |
| Foam pads × 4      | Small adhesive felt/foam, ~10 mm   | —                |
| PicoScope 2204A    | (from core BOM)                    | B00GZMRZ3M       |
| BNC cables × 2     | (from core BOM)                    | B07RGPHFR3       |

_Cheaper alternatives:_ 50 × 50 × 1 mm industrial-grade plate (B0F1YVNTMD, $13) gives 11 modes; MUHWA fused-quartz microscope slide 75 × 25 × 1 mm (B07ZYT3DJ6, $10) gives 7 modes — useful as a quick first test of edge bonding.

**Background.** The 1D rod supports only ~5 bending modes below 20 kHz. A 2D plate supports $(n,m)$ mode pairs: $f_{nm} = \frac{\pi}{2}\sqrt{\frac{D}{\rho h}}\left[\left(\frac{n}{a}\right)^2 + \left(\frac{m}{b}\right)^2\right]$, where $D = Eh^3/12(1-\nu^2)$ is the flexural rigidity. For a 100 × 100 × 1 mm fused-quartz plate, this yields ~52 bending modes below 20 kHz — a 10.8× gain.

Fused quartz also has 10× the material $Q$ of borosilicate glass ($Q_\text{mat} = 100{,}000$ vs $10{,}000$) and 6× lower thermal expansion ($\alpha = 0.55$ ppm/K vs $3.3$ ppm/K), meaning each mode is sharper and more thermally stable.

**Edge-coupled PZT topology.** Gluing the PZT disc to the 1 mm plate edge rather than the flat face:

```
    Drive PZT (10 mm disc, centered on edge)
    ↓
    ┌──────────P──────────┐
    │                     │
    │    × putty (x,y)    │  100 × 100 × 1 mm fused quartz
    │                     │
    └──────────P──────────┘
               ↑
    Sense PZT (opposite edge, at a/3 = 33 mm from corner)

    [○] foam pad at each corner
```

- **Contact area:** ~1 mm × 8 mm chord of the 10 mm disc = ~8 mm².
- **Mass loading:** ~0.5 g on a 22 g plate = 2% (vs 26% for the rod).
- **Advantage:** Edge position breaks all symmetries → excites all four mode families (SS, SA, AS, AA). The flat face remains clear for putty placement and visual inspection.

**Procedure:**

1. **Clean the plate.** Wipe with 91% isopropyl alcohol. Handle by edges only.

2. **Bond drive PZT.** Apply a thin line of cyanoacrylate along the bottom edge at the center (50 mm from each corner). Press the PZT disc so its face is perpendicular to the plate face, with 1 mm of the disc contacting the glass edge. The disc will extend ~4.5 mm below the plate on each side. Hold for 30 seconds; let cure for 5 minutes.

3. **Bond sense PZT.** Repeat on the opposite (top) edge at **a/3 = 33 mm** from the left corner. This asymmetric placement maximizes the number of excited modes (38/52 vs 28/52 at center). Offset the sense PZT from the drive to break symmetry.

4. **Mount on foam pads.** Place four small foam or felt pads in a square pattern and rest the plate on its corners. The foam should be soft enough that it doesn't clamp the plate — you want minimal contact at the nodal-like corners. Place inside styrofoam cooler if available.

5. **Connect PicoScope.**
   - Ch A → Sense PZT (BNC → alligator clips → PZT leads).
   - AWG out → Drive PZT (BNC → alligator clips → PZT leads).

6. **Capture bare-plate tap spectrum.**

   ```bash
   PYTHONPATH=. python tools/cwm_picoscope.py capture --label plate_bare
   ```

   Gently flick the plate edge with a fingernail (not near a PZT). Record the FFT. Count visible peaks above the noise floor.

7. **Run AWG frequency sweep** (if using stepped-dwell identifier):

   ```bash
   PYTHONPATH=. python tools/awg_stepped_dwell_id.py --plate-mode
   ```

   The script sweeps from 400 Hz to 20 kHz, dwelling at each resonance. Record the mode list and SNR for each peak.

8. **Measure Q factor.** Tap once and record the time-domain waveform. Measure the −60 dB decay time $t_{60}$. Compute $Q = \pi f t_{60}$.

9. **Record results** in the worksheet below.

| Measurement                                | Value |
| ------------------------------------------ | ----- |
| **Plate dimensions (a × b × h mm):**       |       |
| **Plate material:**                        |       |
| **PZT mounting (edge/face):**              |       |
| **Drive PZT position (mm from corner):**   |       |
| **Sense PZT position (mm from corner):**   |       |
| **Number of modes detected (bare plate):** |       |
| **Fundamental f(1,1) (Hz):**               |       |
| **Predicted f(1,1) (Hz):**                 |       |
| **SNR of strongest mode (dB):**            |       |
| **Q factor (best mode):**                  |       |
| **Mean mode spacing (Hz):**                |       |
| **Min mode spacing (Hz):**                 |       |
| **FFT resolution (Hz):**                   |       |
| **All modes resolved? (Y/N):**             |       |
| **Mode count ratio vs rod baseline:**      |       |

**Expected results.** For 100 × 100 × 1 mm fused quartz: ~30–52 modes below 20 kHz (simply-supported predicts 52; real boundary conditions will reduce this). Fundamental at ~530 Hz. Q should be 100–1,000 on a bare plate (limited by support pads and epoxy). SNR ≥ 40 dB. Mode spacing ~355 Hz mean, well above the 24.2 Hz FFT resolution.

**Predicted mode spectrum** (simply-supported, fused quartz):

| Mode (n,m) | Frequency (Hz) | Degenerate with |
| ---------- | -------------- | --------------- |
| (1,1)      | 529            | —               |
| (1,2)      | 1,323          | (2,1)           |
| (2,2)      | 2,116          | —               |
| (1,3)      | 2,645          | (3,1)           |
| (2,3)      | 3,439          | (3,2)           |
| (1,4)      | 4,182          | (4,1)           |
| (3,3)      | 4,703          | —               |
| (2,4)      | 4,976          | (4,2)           |
| (3,4)      | 6,201          | (4,3)           |
| (1,5)      | 6,879          | (5,1)           |

> **Why fused quartz?** Borosilicate stirring rods work for the 1D experiments. But for the 2D plate extension, fused quartz's 10× higher $Q$ and 6× lower thermal expansion translate to sharper, more stable peaks. This is the same material used in MEMS resonators and gravitational-wave detector optics.

---

### D.16b Experiment 16 — 2D Perturbation Encoding on a Plate

**Objective:** Demonstrate that a putty pellet placed at position $(x, y)$ on the plate face produces a unique spectral fingerprint via the 2D sensitivity function $\sin^2(n\pi x/a)\cdot\sin^2(m\pi y/b)$.

**Time:** 45–60 minutes.

**Materials:** Same plate setup from Experiment 15 (PZTs already bonded); silicone putty; milligram scale; grid template or ruler.

**Preparation.** Print or draw a grid on paper, place under the glass plate (the plate is transparent). Mark positions at $a/6$ intervals in both axes — this gives a 5 × 5 grid of 25 possible putty positions.

**Procedure:**

1. **Capture bare-plate baseline.** Record the mode spectrum with no putty (from Experiment 15, or re-capture).

2. **Place putty at position (a/3, b/3).** Roll a ~50 mg pellet of silicone putty and press gently onto the plate face at position (33, 33) mm from the bottom-left corner. Ensure flat contact with the glass.

3. **Capture perturbed spectrum.**

   ```bash
   PYTHONPATH=. python tools/cwm_picoscope.py capture --label plate_putty_33_33
   ```

4. **Record shifts.** Compare each peak frequency to the bare-plate baseline. Compute fractional shift $\Delta f/f$ for every mode.

5. **Repeat at 3–5 positions:**
   - **(a/3, b/3)** = (33, 33) mm — away from edges/center, good sensitivity
   - **(a/2, b/2)** = (50, 50) mm — plate center, maximal for (odd,odd) modes
   - **(a/3, b/φ)** = (33, 62) mm — golden-ratio y, maximally irrational spacing
   - **(a/4, 3b/4)** = (25, 75) mm — near corner, tests edge sensitivity
   - **(2a/3, b/3)** = (67, 33) mm — mirror of first position, tests symmetry

6. **Look for degeneracy splitting.** At center position (50, 50), the degenerate pairs (n,m)/(m,n) are NOT broken (both indices see the same sin² value). At (33, 62), the asymmetric position should split some degenerate pairs into two distinct peaks — count how many pairs split.

7. **Attempt position recovery.** Given only the spectral fingerprint (list of shifted frequencies), can you determine which grid position the putty was at? The 2D sin² model predicts that each grid position produces a unique pattern. Use:

   ```bash
   PYTHONPATH=. python tools/plate_position_decode.py --spectrum data/results/plate_putty_33_62.csv
   ```

8. **Record results** in the worksheet below.

| Putty Position (x, y) mm | Mass (g) | Modes Shifted | Max Δf/f (%) | Pairs Split | Unique Fingerprint? |
| ------------------------ | -------- | ------------- | ------------ | ----------- | ------------------- |
| (33, 33)                 |          |               |              |             |                     |
| (50, 50)                 |          |               |              |             |                     |
| (33, 62)                 |          |               |              |             |                     |
| (25, 75)                 |          |               |              |             |                     |
| (67, 33)                 |          |               |              |             |                     |

**Expected results.** Each position should shift a different subset of modes. Positions with irrational ratios (like $b/\varphi$) should affect the most modes. Degenerate pair splitting should occur at any position where $x \neq y$. The center position (50, 50) should show the MOST shift for (1,1), (3,3), (5,5) etc. modes but NO degeneracy splitting (because $\sin^2(n\pi/2) = \sin^2(m\pi/2)$ when $x=y$ at center).

The key result: 2D encoding gives $\sim N^2$ distinguishable positions vs $\sim N$ for a 1D rod.

---

<div class="worksheet-header">
<h4>D.17 — Consolidated Experiment Log</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Photocopy this page for each student group or session. Attach completed Worksheets D.1–D.13.</p>
</div>

| Field                                          | Entry                                                                                                                                           |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Experimenter name(s)**                       |                                                                                                                                                 |
| **Date**                                       |                                                                                                                                                 |
| **School / Institution**                       |                                                                                                                                                 |
| **Rod serial # (label each rod)**              |                                                                                                                                                 |
| **Rod length L (mm)**                          |                                                                                                                                                 |
| **Rod diameter d (mm)**                        |                                                                                                                                                 |
| **Rod mass M (g)**                             |                                                                                                                                                 |
| **PZT disc serial #**                          |                                                                                                                                                 |
| **PicoScope model & serial**                   |                                                                                                                                                 |
| **Room temperature at start (°C)**             |                                                                                                                                                 |
| **Relative humidity (%)**                      |                                                                                                                                                 |
| **Rod mount type**                             |                                                                                                                                                 |
| **Thermal enclosure used? (Y/N)**              |                                                                                                                                                 |
| **Experiments completed (circle)**             | 1 &ensp; 2 &ensp; 3 &ensp; 4 &ensp; 5 &ensp; 6 &ensp; 7 &ensp; 8 &ensp; 9 &ensp; 10 &ensp; 11 &ensp; 12 &ensp; 13 &ensp; 14 &ensp; 15 &ensp; 16 |
| **Best Q measured**                            |                                                                                                                                                 |
| **Number of confirmed longitudinal modes**     |                                                                                                                                                 |
| **Best discrimination margin (dB)**            |                                                                                                                                                 |
| **CW lock-in gain at 10 s (dB)**               |                                                                                                                                                 |
| **Wet-finger bowing successful? (Y/N)**        |                                                                                                                                                 |
| **Water-drop patterns written & erased**       |                                                                                                                                                 |
| **Array recall: all diagonals correct? (Y/N)** |                                                                                                                                                 |
| **NN crossover α (expected 0.50):**            |                                                                                                                                                 |
| **Boolean ops all correct? (Y/N)**             |                                                                                                                                                 |
| **Vault: all credentials verified? (Y/N)**     |                                                                                                                                                 |
| **Image search rank-1 accuracy (%)**           |                                                                                                                                                 |
| **CAM lookup accuracy (%)**                    |                                                                                                                                                 |
| **Anomalies or unexpected observations**       |                                                                                                                                                 |

---

### D.18 Troubleshooting Guide

| Symptom                                            | Likely cause                                                             | Fix                                                                                                                         |
| -------------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| No signal when tapping rod                         | Broken PZT lead or bad BNC connection                                    | Inspect and re-solder PZT leads; verify BNC cable continuity with a multimeter                                              |
| Q \< 100                                           | Excessive glue (thick viscoelastic layer)                                | Remove PZT, clean end face, re-glue with a smaller drop; cure 24 hours                                                      |
| Q \< 500                                           | PZT too large, or rod touching a hard surface                            | Ensure cardboard pinholes are sized to the rod with no clamping; try 5 mm PZT disc                                          |
| Many peaks between expected modes                  | Off-center PZT exciting transverse modes                                 | Remove PZT, re-glue centered using tape cross-hair; or filter FFT to comb frequencies only                                  |
| f₁ much higher or lower than 17,700 Hz             | Rod length ≠ 150 mm                                                      | Recalculate: $f_1 = 5{,}315 / (2L)$. A 200 mm rod gives f₁ = 13,288 Hz; a 125 mm rod gives f₁ = 21,260 Hz                   |
| Mode frequencies drifting over minutes             | Temperature fluctuation                                                  | Use insulated enclosure; equilibrate 30 min; record temperature at each data point                                          |
| Putty won't stick to rod                           | Surface too smooth or too dry                                            | Knead putty between fingers for 10 s; clean rod with isopropyl alcohol to remove oils                                       |
| FFT shows 60/120/180 Hz peaks                      | Electrical mains noise pickup                                            | Use shorter BNC cables; move away from power strips and monitors; ensure PicoScope is USB-powered (not near wall adapter)   |
| Response identical for all query patterns          | Drive amplitude in non-linear regime                                     | Reduce AWG amplitude to ≤ 0.5 Vpp; verify linearity per Exp. 5 procedure                                                    |
| A strong peak appears that is not on the mode comb | PZT self-resonance                                                       | Compare against bare-PZT spectrum (see Exp. 2 FM 4 mitigation); flag and exclude from analysis                              |
| Rayleigh prediction error \> 10%                   | Putty mass too large relative to rod, or position measurement inaccurate | Use smaller putty (\<0.1 mg); measure position to ±0.5 mm; weigh rod precisely                                              |
| CW lock-in gain much less than expected            | AWG frequency not precisely at mode peak; PZT coupling asymmetric        | Fine-tune AWG frequency in 0.1 Hz steps while watching lock-in amplitude; ensure firm PZT bond                              |
| No sustained tone when bowing with wet finger      | Finger too dry, too wet, or pressure too light                           | Re-wet finger to a thin film; apply firm, steady pressure; move slowly (1–2 cm/s); try rosined cloth as alternative         |
| Water drop slides off rod immediately              | Rod surface too smooth or tilted                                         | Ensure rod is perfectly horizontal; use smaller drops (~2 mm); lightly breathe on the surface to create a condensation film |
| Water-drop frequency shifts too small to resolve   | Drop too small relative to rod mass                                      | Use larger drops (up to ~5 mm diameter); or use CW lock-in (Exp. 7) for higher frequency resolution                         |

---

### D.19 Contributing Your Data

We invite all experimenters—students, teachers, hobbyists, and researchers—to submit their results. Community data from diverse rod lengths, diameters, glass types, and environments will strengthen the empirical foundation of CWM and accelerate the transition from macro prototype to MEMS fabrication.

#### Option A: Submit via CWM Lab Experiment Wizard (Recommended)

If you are using CWM Lab with the Experiment Wizard (§D.2b), you can export results directly from the capture interface:

1. Open the Experiment Wizard and capture your data (see §D.2b for the full walkthrough).
2. In the **Export to Community** section, select the target experiment, fill in rod details and optional metadata.
3. Click **🚀 Export to Community Firebase**. The wizard authenticates anonymously and submits your results through the server-validated endpoint. No account required.

Captured peaks, SNR, and noise floor values are auto-populated from the most recent capture. The data appears immediately at [coherent-wave-memory.web.app](https://coherent-wave-memory.web.app).

#### Option B: Submit Online

You can also contribute through the CWM project website at [coherent-wave-memory.web.app/experiment](https://coherent-wave-memory.web.app/experiment). The site provides a guided submission form for each experiment:

1. Navigate to **coherent-wave-memory.web.app/experiment** in any web browser.
2. Select the experiment you completed from the experiment tabs at the top.
3. Fill in the data fields (frequency measurements, Q values, temperature, etc.). Fields marked with an asterisk are required; all others are optional.
4. Optionally add a nickname (e.g. "Ms. Rivera's 8th Grade"), location, and free-text notes about your setup or observations.
5. Upload photos or short videos of your setup using the drag-and-drop upload area (up to 5 files, 20 MB each).
6. Click **Submit Results**. Your data is saved anonymously and appears immediately in the **Community Results** section below the form, alongside submissions from other experimenters worldwide.

No account is required. You can submit results for as many experiments as you like. The community results panel shows summary statistics (number of submissions, mean values) and individual result cards — a live, growing dataset that validates the physics across diverse setups.

#### Option C: Submit via GitHub

For advanced users who want to contribute raw data files:

1. Photograph or scan your completed Worksheets D.1–D.13 and the Experiment Log (D.17).
2. Export raw PicoScope waveform files (.psdata or .csv) for each experiment.
3. Submit via pull request to the project repository at [github.com/miketierce/cwm](https://github.com/miketierce/cwm) in the `data/community/` directory. Include your Experiment Log as the commit message or PR description.

#### Option D: Email

Alternatively, email data files and scanned worksheets to the corresponding author.

Every data point matters. A middle school classroom measuring Q = 3,000 on a 200 mm rod constrains the same physics as a university lab measuring Q = 9,000 on a 150 mm rod—and the diversity of rod geometries and construction techniques is itself scientifically valuable. Unexpected results (low Q, spurious modes, anomalous thermal coefficients) are _especially_ welcome: they reveal failure modes that improve the guide for the next experimenter.

---

### D.20 Software Tools

The repository includes software tools that automate waveform generation and data processing for the experiments described in this guide. All tools run from the repository root and require only Python 3.10+ with the dependencies listed in `requirements.txt`.

#### CWM Lab — Unified Experiment UI (`tools/cwm_lab.py` + `tools/cwm_lab.html`)

**CWM Lab is the recommended interface for Experiments 12–14.** It provides a single browser-based UI that combines the password vault, image search, and content-addressable memory demos with built-in face recognition, a hardware proof panel, and automatic PicoScope detection. Everything runs locally—no internet required.

**Quick start:**

```bash
git clone https://github.com/miketierce/cwm.git
cd cwm
pip install -r requirements.txt
PYTHONPATH=. python tools/cwm_lab.py --port 8200
```

Then open **http://localhost:8200** in any browser.

**Startup banner:**

```
CWM Lab running at http://localhost:8200
  Mode:  SIMULATION (Rayleigh)       ← or HARDWARE (PicoScope 2204A)
  Array: 4 rods × 4 channels = 16 slots
  Data:  data/results/lab
```

CWM Lab automatically detects whether a PicoScope 2204A is connected via USB. If found, it uses real FFT-based spectral measurement; otherwise it falls back to deterministic Rayleigh perturbation simulation. The mode is displayed in the startup banner and in the browser's Hardware Proof Panel.

**Features:**

| Feature                                  | Description                                                                                                                                                                                                                                                                                                                 |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Password vault** (Exp. 12)             | Register users with a rod/pattern assignment; authenticate by spectral correlation. Each rod supports 4 polysemic channels = 4 independent credentials.                                                                                                                                                                     |
| **Image search** (Exp. 13)               | Drag-and-drop images to enroll a library. Each image is perceptual-hashed (64-bit average hash) and assigned to the best-matching rod/channel. Query by uploading an image or using the live webcam.                                                                                                                        |
| **Face recognition**                     | Enroll a face selfie during registration; authenticate by webcam face scan. Demonstrates CWM-backed biometric matching.                                                                                                                                                                                                     |
| **Content-addressable memory** (Exp. 14) | All rod fingerprints are pre-computed at startup. Each registered user is a CAM entry (key = spectral fingerprint, value = user record). The proof panel shows the full lookup table state.                                                                                                                                 |
| **Hardware Proof Panel**                 | Collapsible panel showing per-rod spectra (bar charts), rod cross-correlation matrix (heatmap), user cross-correlation, pipeline steps, and raw JSON—proving the physics to skeptics.                                                                                                                                       |
| **PicoScope auto-detect**                | If `picosdk` is installed and a PicoScope 2204A is connected, all measurements switch to real hardware. Otherwise, Rayleigh simulation is used with deterministic jittered perturbations.                                                                                                                                   |
| **Experiment Wizard** (Exps. 1–14)       | One-click PicoScope configuration from Table D.2a presets. Captures waveform + FFT spectrum, detects peaks, computes SNR, and exports results to the community Firebase database. See §D.2b.                                                                                                                                |
| **CIM Demo** (💻 tab)                    | Compute-in-memory playground: store 16-bit patterns as eigenmode amplitudes, run Hopfield associative recall with adjustable noise, Boolean logic (AND/OR/XOR via superposition), and inner-product operations — all computed by wave-interference physics.                                                                 |
| **Quantum Bridge** (⚛️ tab)              | Five interactive demos mapping quantum-computing capabilities to CWM classical equivalents: (1) classical superposition, (2) non-destructive QND readout, (3) O(1) parallel search vs Grover, (4) room-temperature coherence vs qubit decoherence, (5) eigenmode orthogonality matrix. Runs on real hardware or simulation. |

**Command-line options:**

| Option   | Default | Description                 |
| -------- | ------- | --------------------------- |
| `--port` | `8200`  | HTTP server port            |
| `--rods` | `4`     | Number of rods in the array |

**API endpoints** (for programmatic use or testing):

| Method | Path                       | Description                                                                    |
| ------ | -------------------------- | ------------------------------------------------------------------------------ |
| `GET`  | `/`                        | Serves the web UI (`cwm_lab.html`)                                             |
| `POST` | `/api/register`            | Register a new user (username, passphrase, rod_id, pattern)                    |
| `POST` | `/api/authenticate`        | Authenticate (username, passphrase → correlation score)                        |
| `POST` | `/api/enroll-image`        | Enroll an image (username, name, image as base64)                              |
| `POST` | `/api/query-image`         | Query for nearest image match (username, image as base64)                      |
| `POST` | `/api/enroll-face`         | Enroll a face selfie (username, image as base64)                               |
| `POST` | `/api/face-auth`           | Authenticate via face scan (image as base64)                                   |
| `GET`  | `/api/proof`               | Full physics state: rod spectra, cross-correlations, pipeline, hardware status |
| `GET`  | `/api/users`               | List registered users                                                          |
| `GET`  | `/api/faces`               | List users with enrolled faces                                                 |
| `GET`  | `/api/library/{user}`      | List a user's enrolled images                                                  |
| `GET`  | `/api/scope/status`        | PicoScope connection status, driver, current config                            |
| `GET`  | `/api/scope/presets`       | Experiment wizard preset definitions (Table D.2a)                              |
| `POST` | `/api/scope/configure`     | Configure scope for an experiment (`preset_id`, optional `pattern_name`)       |
| `POST` | `/api/scope/capture`       | Block capture + FFT spectrum + peak detection                                  |
| `POST` | `/api/scope/close`         | Release PicoScope handle                                                       |
| `POST` | `/api/scope/export`        | Submit results to community Firebase (`experiment_id`, `data`, metadata)       |
| `POST` | `/api/qcb/multi-capture`   | N consecutive captures for QND readout stability tests                         |
| `POST` | `/api/qcb/parallel-search` | Parallel matched-filter search across all rods and patterns                    |

**Data files:** `data/results/lab/users.json` (user database), `data/results/lab/images_{user}.json` (per-user image libraries), `data/results/lab/captures/` (saved experiment captures).

**Experiments that use this tool:**

- **Experiment 12** (Acoustic Password Vault) — Registration, authentication, and attack testing.
- **Experiment 13** (Acoustic Image Search) — Image enrollment, query, webcam search, face recognition.
- **Experiment 14** (Acoustic CAM) — Rod fingerprint inspection via the Proof Panel.

#### PicoScope Hardware Driver (`tools/cwm_picoscope.py`)

Drop-in hardware measurement module that replaces Rayleigh simulation with real PicoScope 2204A spectral measurements. Used automatically by CWM Lab when a PicoScope is detected.

**Prerequisites:** Install the Pico Technology SDK from [picotech.com](https://www.picotech.com/downloads) and the Python wrapper:

```bash
pip install picosdk
```

**Standalone usage:**

```bash
# Check if a PicoScope is connected
PYTHONPATH=. python tools/cwm_picoscope.py --check

# Measure a rod's spectral fingerprint
PYTHONPATH=. python tools/cwm_picoscope.py --measure --rod 1 --pattern A
```

**How it works:**

1. Opens the PicoScope 2204A via USB (`picosdk.ps2000a`)
2. Configures Channel A at ±500 mV DC coupling for PZT readout
3. Loads the pre-generated AWG waveform for the selected pattern (`data/results/awg/query_{A,B,C,D}.csv`)
4. Drives the AWG at 2 Vpp, waits 50 ms for settling
5. Captures 8192 samples at 1 MS/s, averaged over 4 acquisitions for SNR
6. Applies a Hanning window, computes the FFT (`numpy.fft.rfft`)
7. Finds the 20 peak frequencies nearest to each expected mode (with parabolic interpolation for sub-bin accuracy)
8. Subtracts the Rayleigh-predicted baseline → frequency shifts = fingerprint

The returned dict (`{perturbed_hz, shift_hz, fingerprint}`) is format-identical to the simulation path, so all downstream logic (channel extraction, correlation, auth, image search, proof panel) works unchanged.

**Experiments that use this tool:**

- All experiments that use CWM Lab or the CLI tools, when a PicoScope is connected.

#### AWG Waveform Generator (`tools/awg_waveform.py`)

Generates multi-tone query waveforms for the PicoScope 2204A's arbitrary waveform generator. The tool computes Rayleigh-shifted mode frequencies from first-principles physics (no manual frequency entry required) and exports ready-to-import files.

**Prerequisites:**

```bash
git clone https://github.com/miketierce/cwm.git
cd cwm
pip install -r requirements.txt
```

**Basic usage:**

```bash
# Generate Query A (Pattern A: quarter-points L/4 + 3L/4)
PYTHONPATH=. python tools/awg_waveform.py --pattern A

# Generate all four query waveforms (A, B, C, D)
PYTHONPATH=. python tools/awg_waveform.py --all

# Custom putty mass and rod geometry
PYTHONPATH=. python tools/awg_waveform.py --pattern A --mass 1.2 --rod-length 120

# Specify output directory
PYTHONPATH=. python tools/awg_waveform.py --all --output data/results/awg

# Show all options
PYTHONPATH=. python tools/awg_waveform.py --help
```

**Output files** (per pattern):

| File          | Format                           | Purpose                                                         |
| ------------- | -------------------------------- | --------------------------------------------------------------- |
| `query_A.csv` | Single-column CSV, normalised ±1 | Import into PicoScope 7 → Signal Generator → Arbitrary → Import |
| `query_A.wav` | 16-bit PCM WAV, 1 MS/s           | Alternative import or use with picosdk Python wrappers          |

**Loading into PicoScope 7:**

1. Open PicoScope 7 → **Tools → Signal Generator**.
2. Set **Wave Type** → **Arbitrary**.
3. Click **Import** → select the generated CSV file (e.g. `query_A.csv`).
4. Set **Amplitude** to the value printed by the script (typically ~0.40 Vpp for 5 tones × 0.1 V).
5. Set **Sample Rate** to **1 MS/s**.
6. Click **Start**. The AWG now outputs the multi-tone query continuously.

**Command-line options:**

| Option              | Default | Description                                                      |
| ------------------- | ------- | ---------------------------------------------------------------- |
| `--pattern`, `-p`   | `A`     | Named pattern: A (L/4+3L/4), B (L/3+2L/3), C (L/2), D (L/5+4L/5) |
| `--all`             | —       | Generate waveforms for all four patterns                         |
| `--modes`, `-m`     | `5`     | Number of modes in the query                                     |
| `--amplitude`, `-a` | `0.1`   | Per-tone amplitude in volts                                      |
| `--mass`            | `0.8`   | Putty pellet mass in mg (per pellet)                             |
| `--rod-length`      | `150`   | Rod length in mm                                                 |
| `--rod-diameter`    | `6`     | Rod diameter in mm                                               |
| `--output`, `-o`    | `.`     | Output directory                                                 |

**How it works:** The tool uses the Rayleigh perturbation formula ($\Delta f_n / f_n = -(\Delta m / 2M) \sin^2(n\pi x / L)$) to compute how each pattern's putty pellets shift the first $N$ mode frequencies. It then synthesises a composite waveform by summing equal-amplitude sinusoids at those shifted frequencies into an 8192-sample buffer at 1 MS/s — designed to loop seamlessly on the PicoScope 2204A's AWG.

**Experiments that use this tool:**

- **Experiment 6** (Associative Recall) — Step 2: build Query A.
- **Experiment 9** (Packed-Array Recall) — Step 4: build Queries A–D.
- **Experiment 10** (Nearest-Neighbor Search) — Step 2: build endpoint queries.

#### Acoustic Password Vault (`tools/cwm_vault.py`)

Enrolls glass rods as physically unclonable credentials and authenticates passwords via spectral correlation. Each rod stores 4 independent credentials via polysemic readout (contiguous spectral bands of 5 modes each).

**Basic usage:**

```bash
# Enroll a rod with named credential labels
PYTHONPATH=. python tools/cwm_vault.py enroll --rod 1 --labels email bank laptop vpn

# Enroll all 4 rods
for i in 1 2 3 4; do
  PYTHONPATH=. python tools/cwm_vault.py enroll --rod $i
done

# Verify a credential
PYTHONPATH=. python tools/cwm_vault.py verify --label email

# Verify with noise injection (attack test)
PYTHONPATH=. python tools/cwm_vault.py verify --label email --noise 0.05

# Show all enrolled credentials
PYTHONPATH=. python tools/cwm_vault.py status
```

**Command-line options (enroll):**

| Option         | Default | Description                                            |
| -------------- | ------- | ------------------------------------------------------ |
| `--rod`        | —       | Rod number (1–10), required                            |
| `--pattern`    | auto    | Perturbation pattern (A/B/C/D); auto-cycles if omitted |
| `--labels`     | auto    | Four space-separated credential labels                 |
| `--mass`       | `0.8`   | Putty mass in mg per pellet                            |
| `--rod-length` | `150`   | Rod length in mm                                       |

**Command-line options (verify):**

| Option        | Default | Description                                   |
| ------------- | ------- | --------------------------------------------- |
| `--label`     | —       | Credential label to verify, required          |
| `--noise`     | `0`     | Noise σ to inject (simulates drift or attack) |
| `--wrong-rod` | off     | Print wrong-rod correlation matrix            |

**Output files:** `data/results/vault_db.json` — enrolled templates and label→rod/channel mappings.

**Experiments that use this tool:**

- **Experiment 12** (Acoustic Password Vault) — Steps 2–5.

#### Acoustic Image Search (`tools/cwm_image_search.py`)

Maps images to spectral fingerprints via perceptual hashing, then retrieves the closest visual match by correlating 64-bit hash vectors. Each rod/channel stores one image; the packed array searches all images in parallel.

**Basic usage:**

```bash
# Enroll an image library (simulation mode if no images present)
PYTHONPATH=. python tools/cwm_image_search.py enroll \
    --library data/image_search/library/ --rods 4 --channels 4

# Query with a new image
PYTHONPATH=. python tools/cwm_image_search.py query \
    --image data/image_search/query/test_photo.jpg

# Run self-retrieval accuracy test
PYTHONPATH=. python tools/cwm_image_search.py test \
    --library data/image_search/library/
```

**Command-line options (enroll):**

| Option       | Default | Description                                    |
| ------------ | ------- | ---------------------------------------------- |
| `--library`  | —       | Path to directory of JPEG/PNG images, required |
| `--rods`     | `4`     | Number of rods in the array                    |
| `--channels` | `4`     | Polysemic channels per rod                     |

**Output files:** `data/results/image_db.json` — image→rod/channel assignments and hash vectors.

**Experiments that use this tool:**

- **Experiment 13** (Acoustic Image Search) — Steps 2–4.

#### Acoustic CAM Lookup Table (`tools/cwm_cam.py`)

Demonstrates a content-addressable memory where spectral queries retrieve stored key→value pairs. Supports direct lookup, content-addressed search, noisy queries, and partial-key queries.

**Basic usage:**

```bash
# Enroll with demo values (4 rods × 4 channels = 16 entries)
PYTHONPATH=. python tools/cwm_cam.py enroll --rods 4

# Enroll from a CSV file (last column = value)
PYTHONPATH=. python tools/cwm_cam.py enroll --rods 4 --table data/cam/routing_table.csv

# Direct lookup by rod/channel
PYTHONPATH=. python tools/cwm_cam.py lookup --rod 1 --channel 0

# Content-addressed search by pattern
PYTHONPATH=. python tools/cwm_cam.py search --query-pattern A

# Search with noise (error tolerance test)
PYTHONPATH=. python tools/cwm_cam.py search --query-pattern A --noise 0.05

# Partial-key search (3 of 5 modes)
PYTHONPATH=. python tools/cwm_cam.py search --query-pattern A --modes 3
```

**Command-line options (search):**

| Option            | Default | Description                             |
| ----------------- | ------- | --------------------------------------- |
| `--query-pattern` | —       | Named pattern (A/B/C/D), required       |
| `--noise`         | `0`     | Noise σ to inject into query            |
| `--modes`         | `5`     | Number of modes (partial-key if < 5)    |
| `--verbose`       | off     | Print all entries ranked by correlation |

**Output files:** `data/results/cam_db.json` — enrolled fingerprints and key→value associations.

**Experiments that use this tool:**

- **Experiment 14** (Acoustic CAM) — Steps 2–5.

#### PDF Builder (`tools/md2pdf.py`)

Converts the experiment guide (or the main paper) from Markdown to a book-quality PDF via HTML + Chromium. Handles duplex pagination, landscape illustration plates, portrait 1:1-scale templates, and automatic recto-start enforcement.

```bash
# Build the experiment guide PDF
PYTHONPATH=. python tools/md2pdf.py companion/experiment_guide.md

# Build the paper
PYTHONPATH=. python tools/md2pdf.py paper/cwm_core.md

# HTML-only (for debugging layout issues)
PYTHONPATH=. python tools/md2pdf.py companion/experiment_guide.md --html-only
```

Requires: `playwright` (with Chromium installed via `playwright install chromium`), `markdown`, `pypdf`.

---

_All quantitative claims computed from first-principles simulation code (48 modules, 2,253 automated tests, all passing) and independently validated by finite element analysis. No curve fitting, no adjusted parameters, no post-hoc corrections. Repository: github.com/miketierce/cwm._

---

## Illustration Plates

_The following pages present experiment-relevant figures at full landscape scale for detailed examination. For the complete set of all 16 figures (including MEMS design, scaling, and fabrication plates), see Paper I._

<div class="plate-page">
<img src="figures/fig1_architecture.svg" alt="Plate 1: CWM Architecture"/>
<p><strong>Figure 1.</strong> CWM architecture overview. <em>Left:</em> A glass resonator stores data as mass perturbations that shift eigenmode frequencies. <em>Center:</em> The spectral domain shows mode peaks before (solid) and after (dashed) perturbation — each pattern is a unique spectral fingerprint. <em>Right:</em> Driving an array with a query spectrum, the best-matching rod produces the largest response — a physical O(1) nearest-neighbor search. <em>Bottom:</em> Unlike von Neumann architectures, CWM unifies storage and computation in the same physical process.</p>
</div>

<div class="plate-page">
<img src="figures/fig3_eigenmode_encoding.svg" alt="Plate 2: Eigenmode Encoding"/>
<p><strong>Figure 3.</strong> Eigenmode encoding. <em>(a)</em> Standing wave mode shapes for modes n = 1, 2, 3, … N within a glass rod — each mode is an independent information channel at a distinct frequency. <em>(b)</em> Perturbation effect: adding mass at a specific position shifts each mode frequency by a different amount (Rayleigh perturbation formula), creating a unique spectral fingerprint that encodes the perturbation's position and mass.</p>
</div>

<div class="plate-page">
<img src="figures/fig7_weight_pruning.svg" alt="Plate 3: Synaptic Pruning for Associative Recall"/>
<p><strong>Figure 7.</strong> Synaptic pruning optimization. <em>(a)</em> Weight matrix before and after pruning: entries below threshold θ are zeroed, removing inter-pattern crosstalk while preserving dominant pattern-encoding weights. <em>(b)</em> Recall accuracy vs. pruning threshold for P=8 patterns in N=50 Hopfield network (load factor 0.16). Optimal pruning at θ* = 0.055 achieves +10.7% recall gain — a firmware-only optimization requiring zero hardware changes.</p>
</div>

<div class="plate-page">
<img src="figures/fig8_compute_in_memory.svg" alt="Plate 4: In-Situ Boolean Computation"/>
<p><strong>Figure 8.</strong> In-situ Boolean computation via mode superposition. Two stored patterns (A, B) are superposed; the combined amplitude distribution is decoded into XOR (90.6% fidelity), AND (96.9%), and OR (93.8%) using amplitude thresholds — all from a single readout cycle. This provides 3× throughput vs. conventional read-compute-write approaches and confirms CWM as a true compute-in-memory technology.</p>
</div>

<div class="plate-page">
<img src="figures/fig11_prototype_spectrum.svg" alt="Plate 5: Prototype Eigenmode Spectrum"/>
<p><strong>Figure 11.</strong> Eigenmode frequency comb of the 150 mm borosilicate prototype. <em>(a)</em> Unperturbed spectrum (blue solid) shows a clean comb at 17.7 kHz spacing. After 0.1 mg putty perturbation (red dashed), each mode shifts by a different Δfₙ depending on the putty position relative to that mode's antinode — the spectral fingerprint of the perturbation. <em>(b)</em> Zoomed view of modes 2–4 showing Lorentzian peak profiles and position-dependent shift magnitudes. Mode 3 shifts most (putty at antinode); mode 4 barely shifts (putty near node). Measured shifts match Rayleigh predictions to within 2%.</p>
</div>

<div class="plate-page">
<img src="figures/fig12_ringdown.svg" alt="Plate 6: Ring-down and Q Measurement"/>
<p><strong>Figure 12.</strong> Q-factor measurement of the macro prototype. <em>(a)</em> Ring-down waveform of the fundamental mode (17.7 kHz) after impulse excitation: the exponential envelope decays with τ = 180 ms, giving Q = πf₁τ = 10,000. <em>(b)</em> Bandwidth method: the −3 dB linewidth of the Lorentzian resonance peak is Δf₃dB = 1.77 Hz, independently confirming Q = f₁/Δf₃dB = 10,000. Both methods agree that the prototype is material-loss-limited, not electronics-limited — the USB oscilloscope is not the bottleneck.</p>
</div>

<div class="plate-page">
<img src="figures/fig13_recall_discrimination.svg" alt="Plate 7: Associative Recall Discrimination"/>
<p><strong>Figure 13.</strong> Associative recall demonstration. <em>(a)</em> Response amplitudes for an 8-pattern array when queried with the P4 spectrum: the matching pattern responds at 28 dB, 15 dB above the best non-matching pattern (P6 at 13 dB), providing a 30× power margin. <em>(b)</em> Cross-correlation matrix for four stored fingerprints confirms near-orthogonality: diagonal entries = 1.00, maximum off-diagonal = 0.21 (−13.6 dB). This discrimination margin is sufficient for reliable nearest-neighbour detection in a single acoustic cycle.</p>
</div>

<div class="plate-page">
<img src="figures/fig15_cw_readout.svg" alt="Plate 8: Continuous-Wave Readout Gain"/>
<p><strong>Figure 15.</strong> CW readout SNR gain vs. integration time. Lock-in detection at the mode frequency rejects all out-of-band noise, yielding gain = 10 log₁₀(T_int / τ). At 1 s: +7.5 dB; at 10 s: +17.5 dB; at 60 s: +25.2 dB over impulse ring-down. This is the electronic equivalent of a glass harmonica performer's sustained bow — continuous energy input builds the resonator to full amplitude.</p>
</div>

<div class="plate-page">
<img src="figures/fig16_two_phase_readout.svg" alt="Plate 9: Two-Phase Readout Architecture"/>
<p><strong>Figure 16.</strong> Two-phase readout architecture. Phase 1 (broadband chirp) excites all modes simultaneously for rapid spectral fingerprinting. Phase 2 (narrowband CW lock-in) targets individual modes for high-precision frequency measurement. Combining both phases gives the best of both worlds: fast pattern identification followed by precision characterization — the same impulse-then-sustain strategy a glass harmonica performer uses intuitively.</p>
</div>

---

## Printable Divider Templates

_The following pages provide 1:1-scale templates. Print at 100% scale (no fit-to-page) and verify the calibration ruler before tracing. Assembly instructions follow each set of templates._

<div class="template-page">
<img src="figures/template_single_rod.svg" alt="Template T.1: Single-Rod Divider"/>
</div>

<div class="template-instructions">
<h3>Template T.1 — Single-Rod Divider Instructions</h3>
<p>Cut two rectangles of flat cardboard to <strong>165 mm × 140 mm</strong> (6.5″ × 5.5″) — sized to slot snugly inside the CH-BOX insulated shipping box (item 11). If using a different enclosure, measure its interior cross-section and cut the cardboard to match. The dividers should fit firmly against all four walls with no gaps.</p>
<ol>
<li>Print the facing template page at 100% scale (no fit-to-page). Verify the calibration ruler measures exactly 50 mm with a physical ruler.</li>
<li>Cut out the template along the dashed line. Tape it to cardboard and trace the outline, including the ⊙ crosshair position.</li>
<li>Punch a 7 mm hole at the ⊙ crosshair using the hollow punch from the kit (item 22). The hole should be centered in the rectangle so the rod passes through the middle of the box.</li>
<li>Cut <strong>TWO</strong> identical dividers. Drop them into the box standing upright, spaced <strong>75 mm apart</strong>. This places each support at L/4 and 3L/4 for a 150 mm rod — the exact displacement nodes of mode 2. The rod slides horizontally through the aligned pinholes.</li>
</ol>
<p>The first divider should be positioned so the PZT disc and leads protrude out one end of the box for cable connection. Cut a small notch in the box lid above this end for BNC cable and thermometer wire routing.</p>
<p>For different rod lengths, recalculate: support spacing = L/2, each support at L/4 from the nearer end.</p>
</div>

<div class="template-page">
<img src="figures/template_single_row_1x4.svg" alt="Template T.2A: Single-Row Divider (4 rods)"/>
</div>

<div class="template-page">
<img src="figures/template_single_row_1x6.svg" alt="Template T.2B: Single-Row Divider (6 rods)"/>
</div>

<div class="template-page">
<img src="figures/template_single_row_1x8.svg" alt="Template T.2C: Single-Row Divider (8 rods)"/>
</div>

<div class="template-instructions">
<h3>Templates T.2A / T.2B / T.2C — Single-Row Divider Instructions</h3>
<p>The three preceding templates provide 1:1-scale U-notch patterns for packed-array experiments: 1×4 (4 rods, Experiments 9–11, 30 mm spacing), 1×6 (6 rods, 25 mm spacing), or 1×8 (8 rods, 25 mm spacing, requires wider enclosure). Rods drop into the notches from above — essential when PZTs are glued to both ends (Topology B) and putty has been applied, making it impossible to slide rods through holes. Each notch creates an isolated acoustic chamber between the two dividers — the same architecture proposed for MEMS CWM arrays.</p>
<p><strong>T.2A (1×4):</strong> Cut each divider to <strong>165 mm × 140 mm</strong> (6.5″ × 5.5″) to fit the CH-BOX (item 11). 30 mm spacing provides 5 mm clearance between adjacent 25 mm PZT discs. <strong>T.2B (1×6):</strong> Same divider size, 25 mm spacing — use with 10 mm PZTs (Topology B). <strong>T.2C (1×8):</strong> Cut a wider divider (<strong>210 mm × 90 mm</strong>) — does not fit in a standard CH-BOX; use a larger enclosure.</p>
<ol>
<li>Print the template page for your chosen layout at 100% scale (no fit-to-page). Verify the calibration ruler measures exactly 50 mm.</li>
<li>Cut out the template along the dashed line. Tape it to cardboard and trace, marking all U-notch positions along the top edge.</li>
<li>Cut each U-notch from the top edge: 7 mm wide × 10 mm deep. Use scissors or a craft knife. A semicircular bottom is ideal, but a flat-bottomed slot works too. The rod should sit snugly in the notch with no hard clamping.</li>
<li>Cut <strong>TWO</strong> identical dividers. Drop them into the box 75 mm apart. Drop rods into the aligned notches from above — each rod should rest freely with no binding.</li>
</ol>
<p>The single-row layout ensures rods can be installed and removed without disassembling the array — critical when PZTs protrude from both ends and putty must not be disturbed. For Topology A (single PZT per rod, 25 mm discs), use T.2A with 30 mm spacing. For Topology B (10 mm PZTs on both ends), T.2B and T.2C use 25 mm spacing with ample clearance.</p>
</div>

<div class="template-page">
<img src="figures/template_perturbation_guide.svg" alt="Template T.3: Perturbation Placement Guide"/>
</div>

<div class="template-instructions">
<h3>Template T.3 — Perturbation Placement Guide Instructions</h3>
<p>Lay the glass rod directly on the printed page, flush against the left end-stop, to transfer exact putty positions for each experiment pattern.</p>
<ol>
<li>Place your 150 mm glass rod in the blue channel, flush against the left end-stop.</li>
<li>Red ⊕ crosshairs mark exact putty placement positions. Transfer marks to the rod with a fine-tip pen.</li>
<li>Remove rod, knead a small putty pellet, and press it onto each marked position.</li>
</ol>
<p><strong>Patterns:</strong> A (quarter-points, Experiments 5/9), B (third-points, Experiments 6/9), C (midpoint, Experiments 6/8/9), D (fifth-points, Experiment 9). The combined reference ruler at the bottom shows all positions with color-coded markers.</p>
<p><em>Rod spec: 6 mm dia × 150 mm borosilicate (PATIKIL B0D1NCM4R4). Perturbation mass: Mack's Pillow Soft silicone putty.</em></p>
</div>

<div class="template-page">
<img src="figures/template_pzt_centering.svg" alt="Template T.4: PZT Disc Centering Guide"/>
</div>

<div class="template-instructions">
<h3>Template T.4 — PZT Disc Centering Guide Instructions</h3>
<p>This page provides 12 cut-out centering guides at 1:1 scale. Each guide shows the exact center of the 10 mm PZT disc and the 6 mm rod end, making it easy to align the disc on the rod before gluing.</p>
<ol>
<li>Print the facing template page at 100% scale (no fit-to-page). Verify the calibration ruler measures exactly 50 mm with a physical ruler.</li>
<li>Cut out one centering guide along the <strong>grey dashed circle</strong> (the 10 mm PZT disc outline).</li>
<li>Lay the paper disc on the flat end of your glass rod. Align the <strong>blue circle</strong> (6 mm rod outline) with the rod's edge — the red crosshair and center dot mark the exact center of the rod face.</li>
<li>Place one tiny drop of cyanoacrylate (<strong>&lt; 0.5 mm diameter</strong>) on the red center dot.</li>
<li>Remove the paper guide. Press the PZT disc face-down onto the rod end, centering it so 2 mm of PZT overhangs the rod uniformly all around.</li>
<li>Hold firm, even pressure for 30 seconds. Cure 24 hours before use.</li>
</ol>
<p>Accurate centering ensures that the PZT drives <strong>only longitudinal modes</strong>. An off-center disc excites transverse and torsional modes that pollute the measured spectrum — see Failure Mode 2 in Experiment 1 for diagnostics and mitigation.</p>
<p>6 guides per sheet (25 mm discs): enough for a full class kit with spares. Reprint as needed.</p>
</div>

---

## Printable Worksheets

_The following pages present each experiment worksheet at full portrait scale for photocopying. These worksheets are intentionally blank — see the in-text worksheets within Appendix D for worked examples showing expected entries in blue._

<div class="worksheet-plate">
<h4>Worksheet D.1 — Quality Factor Measurement</h4>
<p class="ws-inst">Photocopy this page. Fill in one column per rod tested.</p>
<table>
<thead><tr><th style="width:40%">Parameter</th><th>Rod 1</th><th>Rod 2</th><th>Rod 3</th></tr></thead>
<tbody>
<tr><td>Date / Time</td><td></td><td></td><td></td></tr>
<tr><td>Experimenter</td><td></td><td></td><td></td></tr>
<tr><td>Room temperature (°C)</td><td></td><td></td><td></td></tr>
<tr><td>Rod length L (mm)</td><td></td><td></td><td></td></tr>
<tr><td>Rod diameter d (mm)</td><td></td><td></td><td></td></tr>
<tr><td>Glue amount (tiny / small / medium)</td><td></td><td></td><td></td></tr>
<tr><td>Measured f₁ (Hz)</td><td></td><td></td><td></td></tr>
<tr><td>Predicted f₁ = 5,315/(2L) (Hz)</td><td></td><td></td><td></td></tr>
<tr><td>Ring-down τ (ms)</td><td></td><td></td><td></td></tr>
<tr><td><strong>Q (ring-down) = πf₁τ</strong></td><td></td><td></td><td></td></tr>
<tr><td>−3 dB bandwidth Δf₃dB (Hz)</td><td></td><td></td><td></td></tr>
<tr><td><strong>Q (bandwidth) = f₁/Δf₃dB</strong></td><td></td><td></td><td></td></tr>
<tr><td>Two methods agree within 10%? (Y/N)</td><td></td><td></td><td></td></tr>
<tr><td>Notes</td><td></td><td></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.2 — Mode Spectrum Map</h4>
<p class="ws-inst">Photocopy this page. Predicted frequencies are for a 150 mm rod — recalculate if your rod differs.</p>
<table>
<thead><tr><th>Mode <em>n</em></th><th>Predicted fₙ (Hz)</th><th>Measured fₙ (Hz)</th><th>Δf (Hz)</th><th>Amplitude (dB)</th><th>Confirmed?</th></tr></thead>
<tbody>
<tr><td>1</td><td>17,717</td><td></td><td></td><td></td><td>Y / N</td></tr>
<tr><td>2</td><td>35,434</td><td></td><td></td><td></td><td>Y / N</td></tr>
<tr><td>3</td><td>53,150</td><td></td><td></td><td></td><td>Y / N</td></tr>
<tr><td>4</td><td>70,867</td><td></td><td></td><td></td><td>Y / N</td></tr>
<tr><td>5</td><td>88,584</td><td></td><td></td><td></td><td>Y / N</td></tr>
<tr><td>6</td><td>106,301</td><td></td><td></td><td></td><td>Y / N</td></tr>
<tr><td>7</td><td>124,018</td><td></td><td></td><td></td><td>Y / N</td></tr>
<tr><td>Spurious 1</td><td>—</td><td></td><td>—</td><td></td><td>type: ___</td></tr>
<tr><td>Spurious 2</td><td>—</td><td></td><td>—</td><td></td><td>type: ___</td></tr>
<tr><td>Spurious 3</td><td>—</td><td></td><td>—</td><td></td><td>type: ___</td></tr>
<tr><td><strong>Total confirmed:</strong></td><td></td><td></td><td></td><td></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.3 — Thermal Stability Log</h4>
<p class="ws-inst">Photocopy this page. Record temperature and frequency at each time point.</p>
<table>
<thead><tr><th>Time (min)</th><th>Temp (°C)</th><th>f₁ (Hz)</th><th>Δf from t=0 (Hz)</th><th>Environment</th></tr></thead>
<tbody>
<tr><td>0</td><td></td><td></td><td>0.0</td><td>Open / Insulated</td></tr>
<tr><td>5</td><td></td><td></td><td></td><td>Open / Insulated</td></tr>
<tr><td>10</td><td></td><td></td><td></td><td>Open / Insulated</td></tr>
<tr><td>15</td><td></td><td></td><td></td><td>Open / Insulated</td></tr>
<tr><td>20</td><td></td><td></td><td></td><td>Open / Insulated</td></tr>
<tr><td>25</td><td></td><td></td><td></td><td>Open / Insulated</td></tr>
<tr><td>30</td><td></td><td></td><td></td><td>Open / Insulated</td></tr>
<tr><td><em>(perturbation applied)</em></td><td></td><td></td><td></td><td></td></tr>
<tr><td>32</td><td></td><td></td><td></td><td>Open</td></tr>
<tr><td>34</td><td></td><td></td><td></td><td>Open</td></tr>
<tr><td>36</td><td></td><td></td><td></td><td>Open</td></tr>
<tr><td>38</td><td></td><td></td><td></td><td>Open</td></tr>
<tr><td>40</td><td></td><td></td><td></td><td>Open</td></tr>
<tr><td><strong>Measured Δf/ΔT:</strong></td><td></td><td><strong>___ Hz/°C</strong></td><td></td><td></td></tr>
<tr><td><strong>Predicted (−0.9 Hz/°C):</strong></td><td></td><td></td><td></td><td></td></tr>
<tr><td><strong>Recovery time:</strong></td><td></td><td><strong>___ min</strong></td><td></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.4 — Perturbation Encoding Data</h4>
<p class="ws-inst">Photocopy this page. Use one sheet per putty-placement trial.</p>
<table>
<thead><tr><th style="width:50%">Parameter</th><th>Value</th></tr></thead>
<tbody>
<tr><td><strong>Trial #</strong></td><td></td></tr>
<tr><td><strong>Putty pellet mass δm (mg)</strong></td><td></td></tr>
<tr><td><strong>Position x (mm from PZT end)</strong></td><td></td></tr>
<tr><td><strong>Position x/L (fraction)</strong></td><td></td></tr>
<tr><td><strong>Rod mass M (g)</strong></td><td></td></tr>
<tr><td><strong>Rod length L (mm)</strong></td><td></td></tr>
<tr><td><strong>Temperature (°C)</strong></td><td></td></tr>
</tbody>
</table>
<br>
<table>
<thead><tr><th>Mode</th><th>fₙ before (Hz)</th><th>fₙ after (Hz)</th><th>Δfₙ (Hz)</th><th>Δfₙ/fₙ meas (ppm)</th><th>Δfₙ/fₙ pred (ppm)</th><th>Error %</th></tr></thead>
<tbody>
<tr><td>1</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>2</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>3</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>4</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>5</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
</tbody>
</table>
<br>
<p><em>After removing putty:</em></p>
<table>
<thead><tr><th>Mode</th><th>fₙ recovered (Hz)</th><th>Δf from original (Hz)</th><th>Recovered ±0.5 Hz?</th></tr></thead>
<tbody>
<tr><td>1</td><td></td><td></td><td>Y / N</td></tr>
<tr><td>2</td><td></td><td></td><td>Y / N</td></tr>
<tr><td>3</td><td></td><td></td><td>Y / N</td></tr>
<tr><td>4</td><td></td><td></td><td>Y / N</td></tr>
<tr><td>5</td><td></td><td></td><td>Y / N</td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.5 — Associative Recall Discrimination</h4>
<p class="ws-inst">Photocopy this page. Record matched and non-matched query responses.</p>
<table>
<thead><tr><th>Pattern stored on rod</th><th>Query driven</th><th>Peak response (dB)</th><th>Match?</th></tr></thead>
<tbody>
<tr><td>Pattern A</td><td>Query A (matching)</td><td></td><td>✓</td></tr>
<tr><td>Pattern B</td><td>Query A (non-matching)</td><td></td><td>✗</td></tr>
<tr><td>Pattern B</td><td>Query B (matching)</td><td></td><td>✓</td></tr>
</tbody>
</table>
<br>
<table>
<thead><tr><th style="width:60%">Metric</th><th>Value</th></tr></thead>
<tbody>
<tr><td><strong>Discrimination margin (matched − non-matched):</strong></td><td>___ dB</td></tr>
<tr><td><strong>Power ratio (10^(margin/10)):</strong></td><td>___×</td></tr>
<tr><td><strong>Sufficient for reliable detection? (≥15 dB)</strong></td><td>Y / N</td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.6 — CW Readout Comparison</h4>
<p class="ws-inst">Photocopy this page. Compare impulse and continuous-wave readout performance.</p>
<table>
<thead><tr><th style="width:65%">Measurement</th><th>Value</th></tr></thead>
<tbody>
<tr><td>Impulse ring-down peak amplitude (mV)</td><td></td></tr>
<tr><td>CW lock-in amplitude, 1 s (mV)</td><td></td></tr>
<tr><td>CW lock-in amplitude, 10 s (mV)</td><td></td></tr>
<tr><td><strong>Gain (1 s) (dB)</strong></td><td></td></tr>
<tr><td><strong>Gain (10 s) (dB)</strong></td><td></td></tr>
<tr><td>Expected gain (1 s): 7.5 dB — within ±3 dB?</td><td>Y / N</td></tr>
<tr><td>Expected gain (10 s): 17.5 dB — within ±3 dB?</td><td>Y / N</td></tr>
<tr><td>Wet-finger bowing: sustained oscillation?</td><td>Y / N</td></tr>
<tr><td>Bowed frequency (Hz)</td><td></td></tr>
<tr><td>Bowed duration (s)</td><td></td></tr>
<tr><td>Notes on bowing technique</td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.7 — Rewritable Water-Drop Encoding</h4>
<p class="ws-inst">Photocopy this page. Record spectra for each water-drop pattern and verify full recovery.</p>
<table>
<thead><tr><th>Mode</th><th>f (Pat. 0)</th><th>f (Pat. 1: L/2)</th><th>Δf₁</th><th>f (Pat. 2: L/4)</th><th>Δf₂</th><th>f (Pat. 3: L/4+3L/4)</th><th>Δf₃</th></tr></thead>
<tbody>
<tr><td>1</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>2</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>3</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>4</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>5</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
</tbody>
</table>
<br>
<table>
<thead><tr><th style="width:70%">Verification</th><th>Result</th></tr></thead>
<tbody>
<tr><td>Pattern 0 recovered after erasing Pattern 1? (±0.5 Hz)</td><td>Y / N</td></tr>
<tr><td>Pattern 0 recovered after erasing Pattern 2? (±0.5 Hz)</td><td>Y / N</td></tr>
<tr><td>Pattern 1 and Pattern 2 spectrally distinguishable?</td><td>Y / N</td></tr>
<tr><td>Pattern 3 distinct from both Pattern 1 and Pattern 2?</td><td>Y / N</td></tr>
<tr><td><strong>Total distinct patterns written and read</strong></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.8 — Packed-Array Associative Recall</h4>
<p class="ws-inst">Photocopy this page. Record query vs. rod responses for the full discrimination matrix.</p>
<table>
<thead><tr><th>Rod pattern</th><th>Query A (dB)</th><th>Query B (dB)</th><th>Query C (dB)</th><th>Query D (dB)</th></tr></thead>
<tbody>
<tr><td>Rod 1 (Pattern A)</td><td></td><td></td><td></td><td></td></tr>
<tr><td>Rod 2 (Pattern B)</td><td></td><td></td><td></td><td></td></tr>
<tr><td>Rod 3 (Pattern C)</td><td></td><td></td><td></td><td></td></tr>
<tr><td>Rod 4 (Pattern D)</td><td></td><td></td><td></td><td></td></tr>
</tbody>
</table>
<br>
<table>
<thead><tr><th style="width:60%">Metric</th><th>Value</th></tr></thead>
<tbody>
<tr><td><strong>All diagonal entries highest in row? (Y/N)</strong></td><td></td></tr>
<tr><td><strong>Minimum discrimination margin (dB)</strong></td><td></td></tr>
<tr><td><strong>Maximum off-diagonal correlation</strong></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.9 — Nearest-Neighbor Search Crossover</h4>
<p class="ws-inst">Photocopy this page. Record responses at each interpolation step.</p>
<table>
<thead><tr><th>α</th><th>Rod A response (dB)</th><th>Rod B response (dB)</th><th>Winner</th></tr></thead>
<tbody>
<tr><td>0.00</td><td></td><td></td><td></td></tr>
<tr><td>0.10</td><td></td><td></td><td></td></tr>
<tr><td>0.20</td><td></td><td></td><td></td></tr>
<tr><td>0.30</td><td></td><td></td><td></td></tr>
<tr><td>0.40</td><td></td><td></td><td></td></tr>
<tr><td>0.50</td><td></td><td></td><td></td></tr>
<tr><td>0.60</td><td></td><td></td><td></td></tr>
<tr><td>0.70</td><td></td><td></td><td></td></tr>
<tr><td>0.80</td><td></td><td></td><td></td></tr>
<tr><td>0.90</td><td></td><td></td><td></td></tr>
<tr><td>1.00</td><td></td><td></td><td></td></tr>
</tbody>
</table>
<br>
<table>
<thead><tr><th style="width:60%">Metric</th><th>Value</th></tr></thead>
<tbody>
<tr><td><strong>Crossover α (expected 0.50)</strong></td><td></td></tr>
<tr><td><strong>Margin at α = 0.00 (dB)</strong></td><td></td></tr>
<tr><td><strong>Margin at α = 1.00 (dB)</strong></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.10 — Boolean Computation via Mode Superposition</h4>
<p class="ws-inst">Photocopy this page. Record decoded bits for each Boolean operation.</p>
<table>
<thead><tr><th>Mode</th><th>A amplitude</th><th>B amplitude</th><th>A+B amplitude</th><th>XOR bit</th><th>AND bit</th><th>OR bit</th></tr></thead>
<tbody>
<tr><td>1</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>2</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>3</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>4</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>5</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
</tbody>
</table>
<br>
<table>
<thead><tr><th style="width:60%">Metric</th><th>Value</th></tr></thead>
<tbody>
<tr><td><strong>XOR fidelity (%)</strong></td><td></td></tr>
<tr><td><strong>AND fidelity (%)</strong></td><td></td></tr>
<tr><td><strong>OR fidelity (%)</strong></td><td></td></tr>
<tr><td><strong>All three > 90%? (Y/N)</strong></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.11 — Acoustic Password Vault</h4>
<p class="ws-inst">Photocopy this page. Record enrollment and verification results for polysemic vault.</p>
<table>
<thead><tr><th style="width:60%">Verification</th><th>Result</th></tr></thead>
<tbody>
<tr><td><strong>Number of rods enrolled</strong></td><td></td></tr>
<tr><td><strong>Total credentials (rods × 4 channels)</strong></td><td></td></tr>
<tr><td><strong>Correct authentications (out of N attempts)</strong></td><td></td></tr>
<tr><td><strong>False accepts (wrong rod accepted)</strong></td><td></td></tr>
<tr><td><strong>False accepts (wrong channel accepted)</strong></td><td></td></tr>
<tr><td><strong>Discrimination margin (dB) at correct match</strong></td><td></td></tr>
<tr><td><strong>Correlation at correct match (best)</strong></td><td></td></tr>
<tr><td><strong>Correlation at wrong rod (worst)</strong></td><td></td></tr>
<tr><td><strong>Correlation at wrong channel, same rod</strong></td><td></td></tr>
<tr><td><strong>Noisy query still authenticated? (Y/N at ±2%)</strong></td><td></td></tr>
<tr><td><strong>Rod-removal kills credential? (Y/N)</strong></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.12 — Acoustic Image Search</h4>
<p class="ws-inst">Photocopy this page. Record image library enrollment and retrieval results.</p>
<table>
<thead><tr><th style="width:60%">Verification</th><th>Result</th></tr></thead>
<tbody>
<tr><td><strong>Library size (images)</strong></td><td></td></tr>
<tr><td><strong>Number of rods used</strong></td><td></td></tr>
<tr><td><strong>Effective capacity (rods × 4 channels)</strong></td><td></td></tr>
<tr><td><strong>Rank-1 self-retrieval accuracy (%)</strong></td><td></td></tr>
<tr><td><strong>Mean discrimination margin (dB)</strong></td><td></td></tr>
<tr><td><strong>Worst-case margin (dB)</strong></td><td></td></tr>
<tr><td><strong>Number of confusion pairs (&lt;5 dB margin)</strong></td><td></td></tr>
<tr><td><strong>Query time (per image)</strong></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Worksheet D.13 — Acoustic CAM Lookup Table</h4>
<p class="ws-inst">Photocopy this page. Record content-addressable memory lookup results.</p>
<table>
<thead><tr><th style="width:60%">Verification</th><th>Result</th></tr></thead>
<tbody>
<tr><td><strong>Table size (entries)</strong></td><td></td></tr>
<tr><td><strong>Number of rods used</strong></td><td></td></tr>
<tr><td><strong>Effective capacity (rods × 4 channels)</strong></td><td></td></tr>
<tr><td><strong>Correct lookups (out of N attempts)</strong></td><td></td></tr>
<tr><td><strong>Mean correlation at correct match</strong></td><td></td></tr>
<tr><td><strong>Mean correlation at best wrong match</strong></td><td></td></tr>
<tr><td><strong>Discrimination margin (dB)</strong></td><td></td></tr>
<tr><td><strong>Noisy query correct? (Y/N at ±5%)</strong></td><td></td></tr>
<tr><td><strong>Partial-key correct? (Y/N at 3 modes)</strong></td><td></td></tr>
<tr><td><strong>Lookup time (ms, laptop)</strong></td><td></td></tr>
</tbody>
</table>
</div>

<div class="worksheet-plate">
<h4>Consolidated Experiment Log</h4>
<p class="ws-inst">Photocopy this page for each student group or session. Attach completed Worksheets D.1–D.13.</p>
<table>
<thead><tr><th style="width:50%">Field</th><th>Entry</th></tr></thead>
<tbody>
<tr><td><strong>Experimenter name(s)</strong></td><td></td></tr>
<tr><td><strong>Date</strong></td><td></td></tr>
<tr><td><strong>School / Institution</strong></td><td></td></tr>
<tr><td><strong>Rod serial #</strong></td><td></td></tr>
<tr><td><strong>Rod length L (mm)</strong></td><td></td></tr>
<tr><td><strong>Rod diameter d (mm)</strong></td><td></td></tr>
<tr><td><strong>Rod mass M (g)</strong></td><td></td></tr>
<tr><td><strong>PZT disc serial #</strong></td><td></td></tr>
<tr><td><strong>PicoScope model &amp; serial</strong></td><td></td></tr>
<tr><td><strong>Room temperature at start (°C)</strong></td><td></td></tr>
<tr><td><strong>Relative humidity (%)</strong></td><td></td></tr>
<tr><td><strong>Rod mount type</strong></td><td></td></tr>
<tr><td><strong>Thermal enclosure used? (Y/N)</strong></td><td></td></tr>
<tr><td><strong>Experiments completed (circle)</strong></td><td>1 &ensp; 2 &ensp; 3 &ensp; 4 &ensp; 5 &ensp; 6 &ensp; 7 &ensp; 8 &ensp; 9 &ensp; 10 &ensp; 11 &ensp; 12 &ensp; 13 &ensp; 14</td></tr>
<tr><td><strong>Best Q measured</strong></td><td></td></tr>
<tr><td><strong>Number of confirmed longitudinal modes</strong></td><td></td></tr>
<tr><td><strong>Best discrimination margin (dB)</strong></td><td></td></tr>
<tr><td><strong>CW lock-in gain at 10 s (dB)</strong></td><td></td></tr>
<tr><td><strong>Wet-finger bowing successful? (Y/N)</strong></td><td></td></tr>
<tr><td><strong>Water-drop patterns written &amp; erased</strong></td><td></td></tr>
<tr><td><strong>Array recall: all diagonals correct? (Y/N)</strong></td><td></td></tr>
<tr><td><strong>NN crossover α (expected 0.50):</strong></td><td></td></tr>
<tr><td><strong>Boolean ops all correct? (Y/N)</strong></td><td></td></tr>
<tr><td><strong>Vault: all credentials verified? (Y/N)</strong></td><td></td></tr>
<tr><td><strong>Image search rank-1 accuracy (%)</strong></td><td></td></tr>
<tr><td><strong>CAM lookup accuracy (%)</strong></td><td></td></tr>
<tr><td><strong>Anomalies or unexpected observations</strong></td><td></td></tr>
</tbody>
</table>
</div>
