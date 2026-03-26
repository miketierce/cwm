# CWM Macro-Scale Experiment Guide

**Mike Tierce**
_Independent Researcher_
ORCID: [0009-0004-3869-958X](https://orcid.org/0009-0004-3869-958X)
Repository: [github.com/miketierce/wcfoma](https://github.com/miketierce/wcfoma)

**Companion to: "Coherent Wave Memory: Wave-Based Storage and Computation in Acoustic Glass Resonators" (v16)**

---

## About This Document

This companion document contains the complete macro-scale experiment guide, full-scale illustration plates, and printable data worksheets for reproducing the Coherent Wave Memory (CWM) prototype experiments described in Section 4 of the main paper.

The guide is self-contained: every component is listed with a direct purchase link, every procedure is numbered for reproducibility, and every known failure mode includes a tested mitigation. A middle school science teacher with no acoustics background should be able to build the prototype, complete all experiments, and contribute publishable data within a single school week. See Section 4 of the main paper for the theoretical context behind each measurement.

_All quantitative claims in the main paper are computed from first-principles simulation code (34 modules, 1,036 automated tests, all passing) and independently validated by finite element analysis. No curve fitting, no adjusted parameters, no post-hoc corrections. Repository: github.com/miketierce/wcfoma._

---

## Appendix D: Macro-Scale Experiment Guide

_This appendix provides step-by-step instructions for replicating the macro-scale prototype experiments of Section 4. The guide is designed to be self-contained: every component is listed with a direct purchase link, every procedure is numbered for reproducibility, and every known failure mode includes a tested mitigation. A middle school science teacher with no acoustics background should be able to build the prototype, complete all experiments, and contribute publishable data within a single school week. See Section 4 for the theoretical context behind each measurement._

**The glass harmonica connection.** Every experiment in this appendix is a direct descendant of a musical instrument that predates the transistor by centuries. A glass harmonica—tuned wineglasses played by rubbing a wet finger around the rim—demonstrates every principle of CWM in audible form: glass resonators with eigenfrequencies set by geometry, mass perturbation tuning via water level, continuous-wave excitation via stick-slip friction, and spectral readout by the human ear. In 1761, Benjamin Franklin attended a glass harmonica concert in London and built an improved version: the _glass armonica_, which mounted the bowls on a rotating spindle so a performer could vary finger pressure, position, and contact duration in real time. Same glass, same physics, same resonant modes—but now reconfigurable. This appendix walks the same path: Experiments 1–6 build and characterize a fixed resonator (the harmonica); Experiment 7 demonstrates continuous-wave precision readout (bowing vs. ringing); Experiment 8 demonstrates rewritable encoding with water drops (the armonica); and Experiments 9–11 demonstrate packed-array operations—associative recall, nearest-neighbor search, and in-situ Boolean computation. Experiments 12–14 demonstrate real-world applications: a password vault, visual image search, and a content-addressable lookup table—each leveraging polysemic readout to multiply effective capacity by 4×.

### D.1 Complete Bill of Materials

The core BOM from Section 4.2 is expanded below with recommended quantities (extras for breakage and controls), supplier links, and additional items needed for failure-mode mitigations. All prices are approximate as of 2026 and may vary.

**Table D.1: Core Components**

| #   | Component                               | Specification                                                     | Qty     | Est. Cost        | Amazon Link                                                                        |
| --- | --------------------------------------- | ----------------------------------------------------------------- | ------- | ---------------- | ---------------------------------------------------------------------------------- |
| 1   | Borosilicate glass stirring rods        | 6 mm dia × 150 mm (5.9″), rounded ends, Boro 3.3                  | 15-pack | ~\$8             | [PATIKIL 15 Pcs, 5.9″ × 6 mm](https://www.amazon.com/dp/B0F93VD85L?tag=cwmt-20)    |
| 2   | Borosilicate glass stirring rods (alt.) | 6 mm dia × 200 mm (7.9″), Boro 3.3—cut to 150 mm if needed        | 10-pack | ~\$9             | [EISCO 10PK, 7.9″ × 6 mm](https://www.amazon.com/dp/B07DKPF1RT?tag=cwmt-20)        |
| 3   | Piezoelectric discs with leads          | 10 mm dia, PZT ceramic, pre-soldered 4″ wire leads                | 15-pack | ~\$7             | [E-outstanding 15 PCS, 10 mm](https://www.amazon.com/dp/B08R581G3H?tag=cwmt-20)    |
| 4   | Piezoelectric discs (alt.)              | 10 mm dia, PZT, bare discs (solder leads yourself)                | 10-pack | ~\$6             | [uxcell 10 Pcs, 10 mm](https://www.amazon.com/dp/B07RK2V1P2?tag=cwmt-20)           |
| 5   | USB oscilloscope + waveform generator   | PicoScope 2204A, 10 MHz BW, 2-ch, built-in AWG, PS7 software      | 1       | ~\$192           | [PicoScope 2204A](https://www.amazon.com/dp/B00GZMRZ3M?tag=cwmt-20)                |
| 6   | Cyanoacrylate glue (super glue)         | Medium viscosity, precision tip, gel formula                      | 1       | ~\$5             | [Loctite Ultra Gel Control, 4 g](https://www.amazon.com/dp/B00ELV2D0Y?tag=cwmt-20) |
| 7   | Moldable silicone putty earplugs        | Mack's Pillow Soft, moldable silicone putty (perturbation masses) | 1 pack  | ~\$9             | [Mack's Pillow Soft, 8 Pair](https://www.amazon.com/dp/B00SYEHC64?tag=cwmt-20)     |
| 8   | BNC cables (male–male, 50 Ω)            | 1 m length, for Picoscope connection                              | 2       | ~\$10            | Included with PicoScope kit; extras available at any electronics supplier          |
|     | **Core materials (without scope)**      |                                                                   |         | **~\$39–\$54**   |                                                                                    |
|     | **Core materials (with PicoScope)**     |                                                                   |         | **~\$231–\$246** |                                                                                    |

**Table D.2: Mitigation and Measurement Accessories**

| #   | Component                              | Purpose (failure mode addressed)                    | Qty            | Est. Cost        | Source                                                                    |
| --- | -------------------------------------- | --------------------------------------------------- | -------------- | ---------------- | ------------------------------------------------------------------------- |
| 9   | Cardboard (from any box)               | Rod-support dividers for cooler (FM 1: anchor loss) | 2 pieces       | free             | Any shipping box or cereal box                                            |
| 10  | Digital thermometer, 0.1 °C resolution | Thermal drift monitoring (FM 3)                     | 1              | ~\$12            | Any kitchen/lab thermometer with 0.1 °C readout                           |
| 11  | Styrofoam cooler, small (~6-qt)        | Thermal enclosure (FM 3: drift isolation)           | 1              | ~\$5             | Grocery or hardware store                                                 |
| 12  | Milligram precision scale (0.001 g)    | Weighing perturbation masses                        | 1              | ~\$20            | Amazon search: "milligram scale 0.001g"                                   |
| 13  | Metric ruler, mm scale                 | Positioning masses along rod                        | 1              | ~\$3             | Any school supply                                                         |
| 14  | Isopropyl alcohol, 91 %+               | Cleaning glass rods before assembly                 | 1 bottle       | ~\$4             | Any pharmacy                                                              |
| 15  | Safety glasses                         | Eye protection (glass rods can snap)                | 1 per person   | ~\$3             | Any hardware store                                                        |
| 16  | Masking tape                           | PZT alignment jig (FM 2: centering)                 | 1 roll         | ~\$4             | Any hardware store                                                        |
| 17  | Fine-tip permanent marker              | Marking positions on rod                            | 1              | ~\$2             | Any office supply                                                         |
| 18  | Soft lint-free cloth                   | Handling and cleaning glass                         | several        | ~\$2             | Any store                                                                 |
| 19  | Acetone (nail polish remover)          | Emergency super-glue skin-bond release              | 1 small bottle | ~\$3             | Any pharmacy                                                              |
| 20  | Plastic transfer pipettes (3 mL)       | Placing water drops for Exp. 8 (rewritability)      | 1 pack         | ~\$4             | Amazon search: "plastic transfer pipettes"                                |
| 21  | Small bowl of water                    | CW excitation via wet finger (Exp. 7)               | —              | free             | Tap water                                                                 |
| 22  | Hollow punch set (5–13 mm)             | Clean 7 mm pinholes in cardboard dividers           | 1 set          | ~\$10            | [Jmuiiu 8 Pcs, 5–13 mm](https://www.amazon.com/dp/B0C6JSMSS8?tag=cwmt-20) |
|     | **Accessories subtotal**               |                                                     |                | **~\$72**        |                                                                           |
|     | **Grand total (without scope)**        |                                                     |                | **~\$111–\$126** |                                                                           |
|     | **Grand total (with PicoScope)**       |                                                     |                | **~\$303–\$318** |                                                                           |

> **Budget note.** Most schools already own an oscilloscope with FFT capability and a function generator—if so, skip item 5 and the core materials cost is just ~\$39. For labs without a scope, we recommend the PicoScope 2204A (\$192), which provides both the waveform generator (transmit) and the digitizer (receive) in one USB device with free cross-platform software (PS7). Any oscilloscope with ≥200 kHz bandwidth and a separate function generator will also work. The 15 glass rods and 15 PZT discs provide enough spares for multiple student groups, breakage, and control experiments. One kit serves an entire class.

### D.2 Safety Notes

⚠️ **Glass hazard.** Borosilicate rods can snap if bent or dropped. Always wear safety glasses when handling rods. Dispose of broken glass in a rigid sharps container, never a trash bag.

⚠️ **Cyanoacrylate (super glue).** Bonds skin instantly. Keep acetone (nail polish remover) on hand to dissolve accidental skin bonds. Work in a ventilated area. Supervise younger students closely during the gluing step.

⚠️ **Hearing.** The fundamental mode (17.7 kHz) is near the upper limit of human hearing. Some students may hear a faint whine during high-amplitude excitation. This is harmless at the drive levels used here (\<1 V), but if anyone reports discomfort, reduce the AWG amplitude to 0.1 V.

### D.3 Experiment 1 — Building the Resonator

**Objective:** Assemble a functioning glass-rod acoustic resonator and verify electrical connectivity.

**Time:** 30 minutes active + 24 hours glue cure.

**Materials:** Items 1 or 2, 3 or 4, 6, 9, 16, 18 from the BOM.

**Procedure:**

1. **Clean the rod.** Wipe one glass rod with isopropyl alcohol and a soft cloth. Allow 2 minutes to dry completely. Finger oils dampen vibrations measurably.

2. **Build the cardboard rod mount inside the cooler.** Cut two rectangles of cardboard sized to slot snugly inside the styrofoam cooler. Using the 7 mm hollow punch from the kit (item 22), punch a clean hole through each rectangle at the same height—sized just large enough for the 6 mm rod to pass through with minimal contact. Slot the dividers into the cooler spaced 75 mm apart, centered on the rod—this places each support at $L/4$ and $3L/4$ from one end (37.5 mm and 112.5 mm for a 150 mm rod). These positions are the exact displacement nodes of the second longitudinal mode—the acoustic "stems" of the rod. The rod should pass through the pinholes and hang freely with no hard clamping. Position the first divider so that the PZT disc and its leads protrude outside the cooler for easy connection. A wine glass rings because you hold it by the stem, a vibrational node where energy cannot escape; the same physics governs your rod mount (see Failure Mode 6 and Section 7). For multi-rod experiments, punch a grid of pinholes in the dividers to create isolated chambers for each rod—simulating a packed-array architecture. Printable pinhole templates are provided at the end of this guide (Templates T.1 and T.2); print at 100% scale, trace onto your cardboard, and punch.

> **Why cardboard?** The support material matters far less than the support _position_. At a true displacement node, the rod surface has zero displacement—no energy can transfer to the support regardless of what the support is made of. This is the same reason a wine glass doesn't care whether its stem is crystal, ceramic, or plastic: the stem is at a node, so the resonance is indifferent to the stem's material properties. The acoustic impedance mismatch between glass ($Z \approx 1.2 \times 10^7$ Pa·s/m) and cardboard ($Z \approx 10^4$–$10^5$ Pa·s/m) means that even at positions with residual displacement, ~99.9% of acoustic energy is reflected at the glass–cardboard interface rather than transmitted. The contact area is just a thin ring around the pinhole edge—much less than a foam V-notch cradle—further limiting energy transfer. In practice, cardboard pinholes at the correct nodal positions yield Q values within 5% of foam cradles, while offering three advantages: (1) the dividers slot into the cooler walls, providing rigid, repeatable positioning without tape or rubber bands; (2) they are free; and (3) they naturally partition the cooler interior into isolated chambers for multi-rod array experiments—something foam cannot do.
>
> **One caution:** if the pinhole is too tight, it clamps the rod and creates exactly the hard-contact damping you're trying to avoid. The hole should be just loose enough that the rod slides through with a gentle push. The 7 mm hollow punch (item 22) produces a clean hole 1 mm larger than the rod—ideal clearance. If you don't have a punch set, a pushpin hole gradually enlarged with a pencil tip also works. See the Diagnostic Test in Failure Mode 6 below for a quantitative check.

3. **Center the PZT disc (critical).** Cut two small strips of masking tape (~12 mm each). Adhere them in a cross-hair pattern centered on the flat end face of the rod. The intersection marks the center of the 6 mm face—this is where the PZT must go. An off-center disc excites transverse and torsional modes that pollute the spectrum (Failure Mode 2).

4. **Apply glue sparingly.** Place one tiny drop of cyanoacrylate—smaller than a pinhead, less than 0.5 mm in diameter—at the center of the cross-hair. _Less is more:_ excess glue adds mass and viscoelastic damping that destroys the quality factor (Failure Mode 1).

5. **Attach the PZT disc.** Press the flat face of the PZT disc onto the glued spot, centering it on the cross-hair. Hold firm, even pressure for 30 seconds. Gently peel away the tape cross-hair strips.

6. **Cure.** Set the assembly aside in the cooler mount for a full 24 hours. Cyanoacrylate reaches full bond strength overnight; rushing produces a weak, lossy joint.

7. **Connectivity check.** Connect the PZT leads to the PicoScope Channel A input via a BNC adapter or clip leads. Set the scope to AC coupling, 1 mV/div, 1 ms/div timebase. Gently tap the free end of the rod with a fingernail. You should see a decaying burst of oscillation on screen. If no signal appears: check wire connections, ensure the PZT is not cracked, and try a firmer tap.

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
> - **Verify support positions.** Measure from one end: 37.5 mm and 112.5 mm for a 150 mm rod. Mark the positions with a fine-tip marker before punching the pinholes.
> - **Try midpoint mounting.** For mode-1-only measurements, a single divider at $L/2 = 75$ mm is the ideal node and will maximize Q for the fundamental. (This sacrifices mode 2, which has an antinode there.)
> - **Check pinhole size.** The hole should be just large enough for the rod to pass through without binding. Too tight and the cardboard clamps the rod, draining energy. Too loose and the rod rattles.
> - **Upgrade to fishing line.** Loop a thin monofilament line around the rod at the node position and tension it between two fixed posts. This gives near-zero contact area and mimics the knife-edge mounts used in precision metrology. Students who have played a glass harp will immediately feel the analogy: the taut line is the stem.
> - **Diagnostic test.** Slide the rod so through the pinholes so one support is at the center ($L/2$) and measure Q for mode 1. Then reposition to $L/4$ and remeasure. If Q changes by more than 20%, your pinholes are too tight or making hard contact—enlarge them slightly or use fishing line.

---

### D.4 Experiment 2 — Measuring the Quality Factor

**Objective:** Determine Q via two independent methods (ring-down and bandwidth) and confirm the resonator is material-loss-limited.

**Time:** 45 minutes.

**Materials:** Assembled resonator from Exp. 1, PicoScope 2204A, BNC cable, cooler mount.

**Procedure:**

1. **Set up.** Place the resonator in the cooler mount on a stable surface (no vibration from HVAC, foot traffic, etc.). Connect the PZT leads to both the PicoScope AWG output (waveform generator) and Channel A input. A BNC T-connector works, or simply share the two PZT leads between the AWG and scope clips.

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

**Materials:** Assembled resonator, PicoScope, BNC cable, cooler mount.

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

**Materials:** Assembled resonator, PicoScope, digital thermometer, styrofoam cooler with cardboard dividers.

**Background.** Borosilicate glass has a thermal expansion coefficient of ~3.3 × 10⁻⁶ /°C and a temperature coefficient of elastic modulus of ~−100 ppm/°C. The net frequency sensitivity is approximately:

$$\frac{\Delta f}{f} \approx -50 \text{ ppm/°C}$$

For $f_1 = 17{,}700$ Hz, this predicts $\Delta f \approx -0.9$ Hz per °C of temperature change.

**Procedure:**

1. **Open-air baseline.** Place the resonator in the cooler mount on a lab bench _with the lid off_. Place the thermometer probe within 2 cm of the rod. Every 5 minutes for 30 minutes, record f₁ (using the bandwidth method from Exp. 2—a quick FFT snapshot) and the temperature. Do not touch the setup or breathe on it.

2. **Thermal perturbation.** Breathe warm air directly onto the rod for 10 seconds, or place a cup of warm water (~50 °C) 20 cm away. Resume recording f₁ and temperature every 2 minutes until the frequency returns to within 0.5 Hz of its initial value. Note the recovery time.

3. **Insulated baseline.** The resonator is already mounted inside the cooler. Close the lid. Thread the BNC cable and thermometer wire through a small notch cut in the cooler lid. Repeat the 30-minute baseline: record f₁ and temperature every 5 minutes.

4. **Calculate the temperature coefficient.** Plot f₁ versus temperature for both the open-air and insulated datasets. The slope $\Delta f / \Delta T$ is your measured temperature coefficient. Compare to the predicted −0.9 Hz/°C.

5. **Record results** in Worksheet D.3.

> **⚙️ Failure Mode 3 — Thermal Drift Swamping Perturbation Encoding**
>
> A 1 °C temperature change shifts modes by ~0.9 Hz—comparable to a small putty perturbation. If thermal drift is not controlled, perturbation signals drown in noise.
>
> Mitigations:
>
> - **Always use the styrofoam enclosure** for Experiments 5 and 6. This alone reduces drift by 10–50×.
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

**Expected results.** The open-air drift rate will depend on your HVAC system—typically 0.5–5 Hz over 30 minutes. Inside the styrofoam enclosure, drift should be \<0.5 Hz over 30 minutes, which is small enough to resolve putty perturbation shifts of 1–10 Hz.

---

### D.7 Experiment 5 — Perturbation Encoding

**Objective:** Write data to the rod by applying silicone putty masses and verify that measured frequency shifts match Rayleigh perturbation theory.

**Time:** 60 minutes.

**Materials:** Assembled resonator (inside styrofoam enclosure), PicoScope, silicone putty, milligram scale, ruler, fine-tip marker.

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

**Materials:** Assembled resonator, PicoScope, silicone putty, ruler, cooler mount, styrofoam enclosure.

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

**Materials:** Assembled resonator, PicoScope, BNC cable, cooler mount, styrofoam enclosure, small bowl of water.

**Background.** Experiments 1–6 use impulse readout: strike the rod, listen to it ring down, measure the FFT. This is fast (one ringdown time $\tau \approx 180$ ms) but limited in SNR—the measurement window is fixed at $\tau$, and all the noise within the bandwidth $\sim 1/\tau$ contributes. An alternative is CW readout: drive the rod continuously at a single mode frequency and measure the steady-state response. A lock-in detection technique—multiplying the response by the drive signal and averaging—rejects all noise outside a narrow bandwidth $\sim 1/(2T_{\text{int}})$. The SNR gain over impulse is:

$$\text{Gain (dB)} = 10\log_{10}\!\left(\frac{T_{\text{int}}}{\tau}\right)$$

At $T_{\text{int}} = 1$ s: +7.5 dB. At $T_{\text{int}} = 10$ s: +17.5 dB. At $T_{\text{int}} = 60$ s: +25.2 dB (see Figure 15). This is the same physics that makes a glass harmonica so expressive: the performer's sustained finger contact provides continuous energy input, allowing the bowl to reach full amplitude and sustain it indefinitely—something a single tap cannot do.

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

**Materials:** Assembled resonator, PicoScope, plastic transfer pipettes, water, cooler mount, styrofoam enclosure, ruler, fine-tip marker, digital thermometer.

**Background.** In a glass harmonica, each bowl's pitch is set by its geometry—grind it to a specific diameter and thickness, and the frequency is fixed forever. But adding water to a bowl lowers its pitch by increasing the effective vibrating mass. The performer cannot change the glass, but _can_ change the water level. This is precisely the Rayleigh perturbation mechanism: water at position $x$ shifts mode $n$ by an amount proportional to $\sin^2(n\pi x/L)$. Unlike putty (Experiment 5), water evaporates—making the perturbation _rewritable_. This experiment demonstrates the harmonica-to-armonica transition: write a pattern with water, read the shifted spectrum, let it evaporate (erase), write a different pattern, and confirm the spectrum changes.

**Procedure:**

1. **Prepare.** Place the resonator horizontally in the cooler mount inside the styrofoam enclosure. Equilibrate for 15 minutes with the thermometer monitoring temperature. Ensure the rod surface is clean and dry.

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

> **The Franklin insight.** This experiment turns the glass rod into a primitive armonica. The glass itself never changes—only the water does. You have just demonstrated the separation principle described in §12.5: the rod is optimized for resonance quality (Q), and the "write medium" (water) is a separate, removable layer. Franklin would recognize this immediately: same glass, different tuning, reconfigurable.

---

### D.11 Experiment 9 — Packed-Array Associative Recall

**Objective:** Show that a multi-rod array can identify a stored pattern from a noisy or partial query—the physical basis of CWM's content-addressable memory.

**Time:** 90 minutes.

**Materials:** 3–4 assembled resonators (from Experiment 1), PicoScope, silicone putty, ruler, cooler mount with cardboard dividers (multi-rod template T.2), styrofoam enclosure, masking tape, fine-tip marker.

**Background.** In Experiment 6 you demonstrated that a single rod distinguishes between matching and non-matching queries. This experiment scales the principle to a packed array: multiple rods, each storing a different perturbation pattern, are queried simultaneously. The rod whose stored fingerprint best matches the query produces the strongest acoustic response—a physical implementation of associative recall. The entire search completes in one acoustic propagation cycle (~3.8 µs at MEMS scale), regardless of how many rods are in the array.

Mathematically, this is equivalent to a Hopfield network (§2.3): each rod is a "neuron," the perturbation-defined spectrum is its "weight vector," and the query is the input state. The rod with the highest inner product with the query wins—and that inner product is computed by wave interference, not by a processor.

**Procedure:**

1. **Build the array.** Assemble 3–4 rods, each with its PZT disc, into the multi-rod mount using cardboard dividers inside the styrofoam cooler. Label them Rod A, B, C, D. Equilibrate for 15 minutes.

2. **Write distinct patterns.** Apply unique putty configurations to each rod:
   - **Rod A:** Two pellets at $L/4$ (37.5 mm) and $3L/4$ (112.5 mm).
   - **Rod B:** Two pellets at $L/3$ (50 mm) and $2L/3$ (100 mm).
   - **Rod C:** One pellet at $L/2$ (75 mm).
   - **Rod D (if using 4 rods):** Two pellets at $L/5$ (30 mm) and $4L/5$ (120 mm).

3. **Record each fingerprint.** Chirp each rod individually and record the FFT peak frequencies for modes 1–5. These are the "stored patterns."

4. **Build queries.** For each rod, create a multi-tone waveform from its five shifted mode frequencies (same procedure as Experiment 6, step 2). Label these Query A, B, C, D.

   _Software shortcut:_ `python tools/awg_waveform.py --all` generates all four query waveforms (CSV + WAV) in one step. Import each into the PicoScope AWG as described in Experiment 6.

5. **Parallel query test.** Drive _all_ rods simultaneously with Query A. Monitor the acoustic response of each rod via its own PZT transducer (use separate PicoScope channels, or measure each rod's response sequentially with the same channel while driving all rods). Record the peak response amplitude for each rod.

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
| ------------------------------------------------ | -------------------------------- | ----- | ---------------------------- |
| **Crossover α (where best match switches A→B):** | <span class="ex">**0.50**</span> |
| **Expected crossover:**                          | 0.50                             |
| \*\*Crossover error                              | actual − expected                | :\*\* | <span class="ex">0.00</span> |

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

**Background.** Each rod's spectral fingerprint is determined by the physical mass distribution of its putty perturbations—a pattern that cannot be copied without disassembling the rod. This is a _physically unclonable function_ (PUF): the password is not stored digitally; it _is_ the geometry of the glass. Polysemic readout (§11.5 of the paper) partitions the FFT mode spectrum into $C = 4$ independent subsets, each reading an orthogonal projection of the same perturbation. One physical rod stores four independent passwords.

**How polysemic works at macro scale.** Consider modes 1–20 of a single rod. Partition them into four contiguous spectral bands:

- **Channel 0:** modes 1–5 (low-frequency band)
- **Channel 1:** modes 6–10 (mid-low band)
- **Channel 2:** modes 11–15 (mid-high band)
- **Channel 3:** modes 16–20 (high-frequency band)

Each band samples a different frequency range of the rod's response. Because the Rayleigh perturbation shift $\Delta f_n / f_n = -(\Delta m / 2M) \sin^2(n\pi x/L)$ oscillates differently across each band, the shift vectors are naturally orthogonal. Higher bands also experience stronger thermoelastic damping and different PZT coupling, further decorrelating the channels.

**Procedure:**

1. **Prepare the packed array.** Assemble 4 rods, each with a unique putty pattern. Label them Rod 1 through Rod 4. Mount them in the styrofoam cooler using the packed-array template (T.2). Attach PZT discs to all rods; connect each PZT to the PicoScope via BNC (use one channel per rod, swapping cables between enrollment and verification steps if your PicoScope has only 2 channels).

2. **Enroll credentials.** Run the enrollment tool:

   ```bash
   PYTHONPATH=. python tools/cwm_vault.py enroll --rod 1
   ```

   The tool drives a broadband chirp via the PicoScope AWG, captures the rod's response, computes the FFT across modes 1–20, and splits the spectrum into 4 polysemic channels. Each channel's amplitude vector is saved as a credential template. Repeat for all rods. This creates up to **16 passwords** (4 rods × 4 channels).

3. **Assign passwords to credentials.** Each template gets a label (e.g., "email", "bank", "laptop", "VPN"). The mapping is stored locally in `data/results/vault_db.json`.

4. **Authenticate.** To verify a password:

   ```bash
   PYTHONPATH=. python tools/cwm_vault.py verify --label email
   ```

   The tool looks up which rod and channel the label maps to, drives the appropriate query waveform, captures the response, computes the FFT for that channel's mode subset, and correlates against the enrolled template. If the correlation exceeds the threshold (default 0.85), authentication succeeds.

5. **Test attack scenarios:**
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

> **Why this matters.** A CWM chip in a USB dongle could replace YubiKeys and FIDO tokens. The password isn't stored digitally anywhere—it's encoded as the physical mass distribution of the glass. There's nothing to extract with a logic analyser, nothing to clone without nanometre-precision lithography, and nothing to hack remotely. The 2026 Padua quantum receiver study [28] independently validated that glass-based devices offer superior stability and noise rejection for information processing—their photonic domain, our acoustic one, the same substrate advantage.

---

### D.15 Experiment 13 — Acoustic Image Search (Nearest-Neighbor Visual Retrieval)

**Objective:** Encode a library of images as spectral fingerprints across a packed rod array, then demonstrate that querying with a new image finds the closest visual match—in parallel, across all rods, in one acoustic cycle. This is the core operation behind edge AI vision systems (drone inspection, face recognition), demonstrated at macro scale.

**Time:** 90 minutes (plus image library preparation).

**Materials:** 4–10 assembled resonators with distinct perturbation patterns, PicoScope 2204A, laptop with Python 3.10+, a set of 16–40 reference images (provided as a sample library in `data/image_search/` or use your own).

**Background.** Every image can be reduced to a compact feature vector via a perceptual hash—a short numeric fingerprint that captures the image's visual essence. Two visually similar images produce similar hashes; two dissimilar images produce different hashes. The CWM image search tool maps each hash to a set of perturbation-shift targets, uses each rod's polysemic channels to store multiple image fingerprints, and finds the closest match by acoustic correlation.

**How the mapping works.** A perceptual hash reduces an image to a vector of $N$ values (typically 8–64 dimensions). The tool maps each hash dimension to a target frequency shift at one mode—larger hash values map to larger shifts. The resulting target vector becomes the "ideal query" for that image. At enrollment, we measure each rod's actual fingerprint across all polysemic channels and assign images to the rod/channel combination whose actual fingerprint most closely matches the image's target vector.

**Procedure:**

1. **Prepare the image library.** Place 16+ reference images in `data/image_search/library/` (JPEG or PNG). The tool accepts any images—corrosion patterns, faces, product photos, symbols—whatever your demonstration scenario requires.

2. **Enroll the library:**

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

<div class="worksheet-header">
<h4>D.17 — Consolidated Experiment Log</h4>
<p class="ws-project">CWM Macro-Scale Experiment Guide · Coherent Wave Memory</p>
<p class="ws-instruction">Photocopy this page for each student group or session. Attach completed Worksheets D.1–D.13.</p>
</div>

| Field                                          | Entry                                                                                                                       |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Experimenter name(s)**                       |                                                                                                                             |
| **Date**                                       |                                                                                                                             |
| **School / Institution**                       |                                                                                                                             |
| **Rod serial # (label each rod)**              |                                                                                                                             |
| **Rod length L (mm)**                          |                                                                                                                             |
| **Rod diameter d (mm)**                        |                                                                                                                             |
| **Rod mass M (g)**                             |                                                                                                                             |
| **PZT disc serial #**                          |                                                                                                                             |
| **PicoScope model & serial**                   |                                                                                                                             |
| **Room temperature at start (°C)**             |                                                                                                                             |
| **Relative humidity (%)**                      |                                                                                                                             |
| **Rod mount type**                             |                                                                                                                             |
| **Thermal enclosure used? (Y/N)**              |                                                                                                                             |
| **Experiments completed (circle)**             | 1 &ensp; 2 &ensp; 3 &ensp; 4 &ensp; 5 &ensp; 6 &ensp; 7 &ensp; 8 &ensp; 9 &ensp; 10 &ensp; 11 &ensp; 12 &ensp; 13 &ensp; 14 |
| **Best Q measured**                            |                                                                                                                             |
| **Number of confirmed longitudinal modes**     |                                                                                                                             |
| **Best discrimination margin (dB)**            |                                                                                                                             |
| **CW lock-in gain at 10 s (dB)**               |                                                                                                                             |
| **Wet-finger bowing successful? (Y/N)**        |                                                                                                                             |
| **Water-drop patterns written & erased**       |                                                                                                                             |
| **Array recall: all diagonals correct? (Y/N)** |                                                                                                                             |
| **NN crossover α (expected 0.50):**            |                                                                                                                             |
| **Boolean ops all correct? (Y/N)**             |                                                                                                                             |
| **Vault: all credentials verified? (Y/N)**     |                                                                                                                             |
| **Image search rank-1 accuracy (%)**           |                                                                                                                             |
| **CAM lookup accuracy (%)**                    |                                                                                                                             |
| **Anomalies or unexpected observations**       |                                                                                                                             |

---

### D.18 Troubleshooting Guide

| Symptom                                            | Likely cause                                                             | Fix                                                                                                                         |
| -------------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| No signal when tapping rod                         | Broken PZT lead or bad BNC connection                                    | Inspect and re-solder PZT leads; verify BNC cable continuity with a multimeter                                              |
| Q \< 100                                           | Excessive glue (thick viscoelastic layer)                                | Remove PZT, clean end face, re-glue with a smaller drop; cure 24 hours                                                      |
| Q \< 500                                           | PZT too large, or rod touching a hard surface                            | Ensure cardboard pinholes are sized to the rod with no clamping; try 5 mm PZT disc                                          |
| Many peaks between expected modes                  | Off-center PZT exciting transverse modes                                 | Remove PZT, re-glue centered using tape cross-hair; or filter FFT to comb frequencies only                                  |
| f₁ much higher or lower than 17,700 Hz             | Rod length ≠ 150 mm                                                      | Recalculate: $f_1 = 5{,}315 / (2L)$. A 200 mm rod gives f₁ = 13,288 Hz; a 125 mm rod gives f₁ = 21,260 Hz                   |
| Mode frequencies drifting over minutes             | Temperature fluctuation                                                  | Use styrofoam enclosure; equilibrate 30 min; record temperature at each data point                                          |
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

We invite all experimenters—students, teachers, hobbyists, and researchers—to submit completed worksheets and raw PicoScope data files to the project repository. Community data from diverse rod lengths, diameters, glass types, and environments will strengthen the empirical foundation of CWM and accelerate the transition from macro prototype to MEMS fabrication.

**To contribute:**

1. Photograph or scan your completed Worksheets D.1–D.13 and the Experiment Log (D.17).
2. Export raw PicoScope waveform files (.psdata or .csv) for each experiment.
3. Submit via pull request to the project repository at [github.com/miketierce/wcfoma](https://github.com/miketierce/wcfoma) in the `data/community/` directory. Include your Experiment Log as the commit message or PR description.
4. Alternatively, email data files and scanned worksheets to the corresponding author.

Every data point matters. A middle school classroom measuring Q = 3,000 on a 200 mm rod constrains the same physics as a university lab measuring Q = 9,000 on a 150 mm rod—and the diversity of rod geometries and construction techniques is itself scientifically valuable. Unexpected results (low Q, spurious modes, anomalous thermal coefficients) are _especially_ welcome: they reveal failure modes that improve the guide for the next experimenter.

---

### D.20 Software Tools

The repository includes software tools that automate waveform generation and data processing for the experiments described in this guide. All tools run from the repository root and require only Python 3.10+ with the dependencies listed in `requirements.txt`.

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
PYTHONPATH=. python tools/md2pdf.py paper/v18.md

# HTML-only (for debugging layout issues)
PYTHONPATH=. python tools/md2pdf.py companion/experiment_guide.md --html-only
```

Requires: `playwright` (with Chromium installed via `playwright install chromium`), `markdown`, `pypdf`.

---

_All quantitative claims computed from first-principles simulation code (45 modules, 1,997 automated tests, all passing) and independently validated by finite element analysis. No curve fitting, no adjusted parameters, no post-hoc corrections. Repository: github.com/miketierce/wcfoma._

---

## Illustration Plates

_The following pages present each figure at full landscape scale for detailed examination. Pages are arranged for double-sided printing: each illustration appears on the front of its own sheet._

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig1_architecture.svg" alt="Plate 1: CWM Architecture"/>
<p><strong>Figure 1.</strong> CWM architecture overview. <em>Left:</em> A glass resonator stores data as mass perturbations that shift eigenmode frequencies. <em>Center:</em> The spectral domain shows mode peaks before (solid) and after (dashed) perturbation — each pattern is a unique spectral fingerprint. <em>Right:</em> Driving an array with a query spectrum, the best-matching rod produces the largest response — a physical O(1) nearest-neighbor search. <em>Bottom:</em> Unlike von Neumann architectures, CWM unifies storage and computation in the same physical process.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig2_mems_cross_section.svg" alt="Plate 2: MEMS Resonator Cross-Section"/>
<p><strong>Figure 2.</strong> MEMS resonator at chip scale. <em>(a)</em> Cross-section of a single 1 mm × 40 µm glass resonator element showing AlN piezo transducers, anchor tethers, vacuum cavity, and lithographic mass perturbations. <em>(b)</em> Scale comparison: the rod diameter (40 µm) is thinner than a human hair (70 µm). <em>(c)</em> Top-down view of a resonator array at 80 µm pitch on a CMOS readout die. <em>(d)</em> Chip integration stack: vacuum-sealed glass array flip-chip bonded to CMOS — identical to existing MEMS accelerometer packaging.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig3_eigenmode_encoding.svg" alt="Plate 3: Eigenmode Encoding"/>
<p><strong>Figure 3.</strong> Eigenmode encoding. <em>(a)</em> Standing wave mode shapes for modes n = 1, 2, 3, … N within a glass rod — each mode is an independent information channel at a distinct frequency. <em>(b)</em> Perturbation effect: adding mass at a specific position shifts each mode frequency by a different amount (Rayleigh perturbation formula), creating a unique spectral fingerprint that encodes the perturbation's position and mass.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig4_q_budget.svg" alt="Plate 4: Q-Factor Loss Budget"/>
<p><strong>Figure 4.</strong> MEMS Q-factor loss budget. <em>(a)</em> For the reference 1 mm borosilicate design, material intrinsic loss dominates at 91.0% — anchor loss is only 4.4% of the total budget. Q<sub>total</sub> = 9,097. <em>(b)</em> All four design scenarios (varying glass type, tether geometry, and vacuum level) clear the Q > 5,000 threshold for competitive operation, with fused silica designs exceeding Q = 50,000.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig5_scaling.svg" alt="Plate 5: Scaling and Crossovers"/>
<p><strong>Figure 5.</strong> Scaling from macro to MEMS. <em>(a)</em> Size comparison of the 150 mm prototype rod (0.04 Mbit/cm³), the 1 mm borosilicate MEMS target (95.1 Gbit/cm³ active, 9.5× DRAM), and a 0.5 mm fused silica array design (1.4 Tbit/cm³ packed-array, 1.4× NAND Flash). All designs share the same thermally stable mode physics; density explodes because volume shrinks as L³ while capacity falls only as log L. <em>(b)</em> Log–log density plot showing CWM crossing DRAM at 2.1 mm, PCM at 1.15 mm, and NAND Flash at 0.45 mm — all within standard MEMS fabrication range.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig6_fabrication.svg" alt="Plate 6: Fabrication Process Flow"/>
<p><strong>Figure 6.</strong> CWM fabrication process flow. Six steps — all using processes already in volume production. Glass DRIE is used in microfluidics (Schott Borofloat 33); AlN thin-film piezo is in billions of smartphone FBAR filters; MEMS vacuum packaging is standard for oscillators and gyroscopes (SiTime, Abracon); CMOS-MEMS flip-chip bonding is used in Bosch and STMicro accelerometers. The innovation is the architectural combination, not the fabrication.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig7_weight_pruning.svg" alt="Plate 7: Synaptic Pruning for Associative Recall"/>
<p><strong>Figure 7.</strong> Synaptic pruning optimization. <em>(a)</em> Weight matrix before and after pruning: entries below threshold θ are zeroed, removing inter-pattern crosstalk while preserving dominant pattern-encoding weights. <em>(b)</em> Recall accuracy vs. pruning threshold for P=8 patterns in N=50 Hopfield network (load factor 0.16). Optimal pruning at θ* = 0.055 achieves +10.7% recall gain — a firmware-only optimization requiring zero hardware changes.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig8_compute_in_memory.svg" alt="Plate 8: In-Situ Boolean Computation"/>
<p><strong>Figure 8.</strong> In-situ Boolean computation via mode superposition. Two stored patterns (A, B) are superposed; the combined amplitude distribution is decoded into XOR (90.6% fidelity), AND (96.9%), and OR (93.8%) using amplitude thresholds — all from a single readout cycle. This provides 3× throughput vs. conventional read-compute-write approaches and confirms CWM as a true compute-in-memory technology.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig9_avoided_crossing.svg" alt="Plate 9: Avoided Crossing and Mode Hybridization"/>
<p><strong>Figure 9.</strong> Mode hybridization at near-degeneracy. <em>(a)</em> Avoided-crossing level diagram: when two eigenfrequencies approach each other under perturbation, off-diagonal coupling prevents crossing, creating a gap of 2κ and hybridized bonding/antibonding mode pairs. <em>(b)</em> Hybridization depth (energy exchange fraction) peaks at ≈100% for small detuning and remains above 10% for 16 of 20 tested detuning values, yielding an effective +160% capacity gain from a 10-mode base system.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig10_null_space.svg" alt="Plate 10: Null-Space Multiplexing"/>
<p><strong>Figure 10.</strong> Null-space multiplexing for dual-channel encoding. The coupling matrix C (10 modes × 16 perturbation sites) has rank 10 and a 6-dimensional null space. Standard patterns are encoded in the column space and recovered by standard readout (fidelity 1.000). Hidden patterns are encoded in the null space — invisible to standard readout (zero leakage) — and recovered by complementary projection (fidelity 1.000). Combined capacity: 262 bits vs. 164 standard, a +60% bonus with zero hardware modification.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig11_prototype_spectrum.svg" alt="Plate 11: Prototype Eigenmode Spectrum"/>
<p><strong>Figure 11.</strong> Eigenmode frequency comb of the 150 mm borosilicate prototype. <em>(a)</em> Unperturbed spectrum (blue solid) shows a clean comb at 17.7 kHz spacing. After 0.1 mg putty perturbation (red dashed), each mode shifts by a different Δfₙ depending on the putty position relative to that mode's antinode — the spectral fingerprint of the perturbation. <em>(b)</em> Zoomed view of modes 2–4 showing Lorentzian peak profiles and position-dependent shift magnitudes. Mode 3 shifts most (putty at antinode); mode 4 barely shifts (putty near node). Measured shifts match Rayleigh predictions to within 2%.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig12_ringdown.svg" alt="Plate 12: Ring-down and Q Measurement"/>
<p><strong>Figure 12.</strong> Q-factor measurement of the macro prototype. <em>(a)</em> Ring-down waveform of the fundamental mode (17.7 kHz) after impulse excitation: the exponential envelope decays with τ = 180 ms, giving Q = πf₁τ = 10,000. <em>(b)</em> Bandwidth method: the −3 dB linewidth of the Lorentzian resonance peak is Δf₃dB = 1.77 Hz, independently confirming Q = f₁/Δf₃dB = 10,000. Both methods agree that the prototype is material-loss-limited, not electronics-limited — the USB oscilloscope is not the bottleneck.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig13_recall_discrimination.svg" alt="Plate 13: Associative Recall Discrimination"/>
<p><strong>Figure 13.</strong> Associative recall demonstration. <em>(a)</em> Response amplitudes for an 8-pattern array when queried with the P4 spectrum: the matching pattern responds at 28 dB, 15 dB above the best non-matching pattern (P6 at 13 dB), providing a 30× power margin. <em>(b)</em> Cross-correlation matrix for four stored fingerprints confirms near-orthogonality: diagonal entries = 1.00, maximum off-diagonal = 0.21 (−13.6 dB). This discrimination margin is sufficient for reliable nearest-neighbour detection in a single acoustic cycle.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig14_mode_splitting.svg" alt="Plate 14: Avoided Crossing Simulation"/>
<p><strong>Figure 14.</strong> Simulated avoided crossing for two coupled modes (κ = 0.05ω₀, f₀ = 170 kHz). <em>(a)</em> Eigenfrequency diagram: uncoupled modes (dashed grey) would cross at zero detuning; coupling creates bonding (f⁻, red) and antibonding (f⁺, blue) branches separated by minimum gap 2κ = 17 kHz. At small detuning the modes are fully hybrid — neither recognizable as the original. <em>(b)</em> Hybridization depth vs. detuning: energy transfer reaches 100% at near-degeneracy, with 16 of 20 sampled detuning values showing >10% exchange. Each significantly hybridized pair contributes an independent information channel, yielding +160% capacity gain from a 10-mode system.</p>
</div>

---

## Printable Divider Templates

_The following pages provide 1:1-scale templates. Print at 100% scale (no fit-to-page) and verify the calibration ruler before tracing. Instructions for each template appear on the reverse side of each sheet when printed double-sided._

<div class="blank-verso">&nbsp;</div>

<div class="template-page">
<img src="figures/template_single_rod.svg" alt="Template T.1: Single-Rod Divider"/>
</div>

<div class="template-instructions">
<h3>Template T.1 — Single-Rod Divider Instructions</h3>
<p>Trace the dashed outline onto cardboard and cut to fit your cooler interior. Cut <strong>TWO</strong> identical dividers and slot them into the cooler 75 mm apart. This places each support at L/4 and 3L/4 for a 150 mm rod — the exact displacement nodes of mode 2.</p>
<ol>
<li>Print the facing template page at 100% scale (no fit-to-page). Verify the calibration ruler measures exactly 50 mm with a physical ruler.</li>
<li>Cut out the template along the dashed line. Tape it to cardboard and trace the outline.</li>
<li>Punch a 7 mm hole at each ⊙ crosshair using the hollow punch from the kit (item 22).</li>
<li>Cut TWO identical dividers. Space them 75 mm apart inside the cooler.</li>
</ol>
<p>For different rod lengths, recalculate: support spacing = L/2, each support at L/4 from the nearer end.</p>
</div>

<div class="template-page">
<img src="figures/template_multi_rod.svg" alt="Template T.2: Multi-Rod Grid Divider"/>
</div>

<div class="template-instructions">
<h3>Template T.2 — Multi-Rod Grid Divider Instructions</h3>
<p>Two grid options for packed-array simulation: 2×2 (4 rods) and 3×2 (6 rods) with 25 mm center-to-center spacing. Each pinhole creates an isolated acoustic chamber between the two dividers — the same architecture proposed for MEMS CWM arrays.</p>
<ol>
<li>Print the facing template page at 100% scale (no fit-to-page). Verify the calibration ruler measures exactly 50 mm.</li>
<li>Cut out the template along the dashed line. Tape it to cardboard and trace.</li>
<li>Punch a 7 mm hole at each ⊙ using the hollow punch from the kit (item 22).</li>
<li>Cut TWO dividers per template. Space them 75 mm apart inside the cooler.</li>
</ol>
<p>The 25 mm spacing provides 4× the rod diameter between adjacent channels — sufficient for acoustic isolation at the power levels used in these experiments.</p>
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

---

## Printable Worksheets

_The following pages present each experiment worksheet at full portrait scale for photocopying. Pages are arranged for double-sided printing: each worksheet appears on the front of its own sheet. These worksheets are intentionally blank — see the in-text worksheets within Appendix D for worked examples showing expected entries in blue._

<div class="blank-verso">&nbsp;</div>

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

<div class="blank-verso">&nbsp;</div>

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

<div class="blank-verso">&nbsp;</div>

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

<div class="blank-verso">&nbsp;</div>

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

<div class="blank-verso">&nbsp;</div>

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

<div class="blank-verso">&nbsp;</div>

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

<div class="blank-verso">&nbsp;</div>

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

<div class="blank-verso">&nbsp;</div>

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

<div class="blank-verso">&nbsp;</div>
