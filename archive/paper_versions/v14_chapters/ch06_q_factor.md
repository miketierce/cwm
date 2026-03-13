---

## 6. MEMS Q-Factor Analysis

The scaling analysis of Section 5 shows that smaller rods are denser. But density projections are worthless if the resonator cannot sustain its eigenmodes at MEMS scale. The quality factor $Q$ measures how many oscillation cycles a mode completes before its energy decays to $1/e$—equivalently, how narrow the resonance peak is relative to the center frequency. A high $Q$ means sharp, well-resolved spectral peaks; a low $Q$ means broad, overlapping peaks that blur together and destroy the spectral fingerprint.

For CWM to work at MEMS scale, we need $Q$ high enough that adjacent eigenmodes remain individually resolvable. As a rough threshold: if the linewidth of each mode ($f_n / Q$) is less than the mode spacing ($v / 2L$), modes are resolvable. This gives $Q > n_{\max}$, or $Q > 9{,}380$ for borosilicate. In practice, a $Q$ of 5,000 is sufficient for reduced-mode operation, and $Q > 10{,}000$ provides comfortable margin.

The macro prototype achieves $Q > 10{,}000$ because the rod is large and the mounting losses are small. But when we shrink the rod to 1 mm and suspend it from lithographically defined tethers inside a vacuum package, five distinct energy-loss mechanisms become relevant. Each mechanism converts some fraction of the rod's acoustic energy into heat, radiation, or other non-useful forms. We model each one independently and combine them.

### 6.1 Material Intrinsic Loss ($Q_{\text{mat}}$)

**What it is.** Even in a perfectly mounted, perfectly isolated resonator floating in a perfect vacuum, acoustic energy still decays. The reason is internal friction within the glass itself. As the rod vibrates—compressing and expanding along its length thousands of times per second—the atoms in the glass matrix do not respond instantaneously. The amorphous network has a distribution of relaxation times: some atomic rearrangements are fast (picoseconds), others are slow (nanoseconds). When the vibration period falls near one of these relaxation times, energy is absorbed and converted to heat. This is the acoustic analogue of hysteresis loss in a magnetic material: the material's response lags behind the driving force, and the lag dissipates energy.

**How large it is.** For borosilicate glass, the material quality factor $Q_{\text{mat}}$ ranges from 8,000 to 15,000 depending on the specific composition and thermal history of the glass. We use 10,000 as a conservative baseline [11, 12]. This means the glass itself converts 1/10,000 of the mode energy to heat per oscillation cycle.

**Why it matters.** Material loss sets the _ceiling_ on the total $Q$: no matter how perfectly we design the tethers, eliminate gas damping, and polish the surface, the total $Q$ can never exceed $Q_{\text{mat}}$. For borosilicate, this ceiling is 10,000. For fused silica, it is 100,000—ten times higher, because fused silica's simpler amorphous structure has fewer internal relaxation pathways.

### 6.2 Anchor Loss ($Q_{\text{anchor}}$)

**What it is.** A MEMS resonator must be physically attached to something—it cannot float in space. In our design, the glass rod is suspended by thin tethers that connect it to the surrounding substrate (the silicon or glass frame of the MEMS die). These tethers are mechanical connections, and mechanical connections transmit vibration. When the rod vibrates, some of the acoustic energy travels down the tethers and into the substrate, where it propagates away and is eventually absorbed. This lost energy is "anchor loss."

An everyday analogy: hold a tuning fork in the air, and it rings for minutes. Press its base firmly against a wooden table, and it goes silent in seconds. The table is an acoustic drain—vibration energy flows from the fork through the contact point and into the table, where the much larger mass absorbs it. The MEMS tethers are the contact point; the substrate is the table.

**How we minimize it.** The anchor loss model [13, 17] gives:

$$Q_{\text{anchor}} = \frac{\pi}{2} \cdot \frac{Z_{\text{rod}}}{Z_{\text{sub}}} \cdot \left(\frac{L}{w_{\text{eff}}}\right)^2 \cdot \left(1 + \frac{L_{\text{tether}}}{w_{\text{eff}}}\right) \cdot \frac{n}{n_{\text{anchors}}} \cdot \eta_{\text{trench}}$$

Each factor in this formula represents a design lever:

- **Impedance ratio** $Z_{\text{rod}}/Z_{\text{sub}}$: The acoustic impedance $Z = \rho v$ measures how "heavy" a medium is acoustically. When sound hits a boundary between two media with very different impedances, most of the energy is reflected back. A glass rod ($Z \approx 1.26 \times 10^7$ kg/m²s) attached to a glass substrate of the same material has an impedance ratio of 1:1, which would be bad—energy flows freely. But the tethers are much thinner than the rod, so the _effective_ impedance seen at the rod-tether junction is much lower, creating a partial reflection.

- **Aspect ratio squared** $(L/w_{\text{eff}})^2$: The tethers have effective cross-section $w_{\text{eff}} = \sqrt{w \cdot t}$ where $w = 2$ µm and $t = 2$ µm, giving $w_{\text{eff}} = 2$ µm. The rod length is 1 mm. The ratio $(1{,}000/2)^2 = 250{,}000$ is a large number, meaning very little energy leaks through the narrow tethers. Think of it this way: the rod is like a wide river, and the tethers are like two drinking straws connecting it to the ocean. Very little water flows through straws.

- **Tether length factor** $(1 + L_{\text{tether}}/w_{\text{eff}})$: Longer tethers provide more acoustic isolation, because the wave must travel farther (and attenuate more) before reaching the substrate. With $L_{\text{tether}} = 20$ µm and $w_{\text{eff}} = 2$ µm, this factor is 11.

- **Mode number** $n / n_{\text{anchors}}$: Higher modes have shorter wavelengths, meaning more of the wave's displacement pattern cancels at the attachment points. Higher modes leak _less_, not more.

- **Isolation trench** $\eta_{\text{trench}} = 3$: An etched gap surrounding the tether base acts as an acoustic mirror, reflecting energy back into the rod. This is standard practice in high-$Q$ MEMS resonators.

For the reference design (1 mm × 40 µm rod, 2 µm × 2 µm × 20 µm tethers, 2 anchor points, with isolation trenches): $Q_{\text{anchor}} = 215{,}711$.

**Why it matters.** Anchor loss is the mechanism most sensitive to MEMS geometry—it depends on tether dimensions, attachment positions, and trench design. Many MEMS resonator designs are _dominated_ by anchor loss, which has led to a widespread assumption that miniaturization kills $Q$. Our analysis shows the opposite: with properly designed tethers, anchor loss contributes only **4.2% of the total loss budget**. The bottleneck is the glass itself, not the suspension.

### 6.3 Thermoelastic Damping ($Q_{\text{TED}}$)

**What it is.** When a rod vibrates longitudinally, it alternately compresses and expands along its length. Compression raises the local temperature (adiabatic heating); expansion lowers it. These temperature variations set up thermal gradients across the rod's cross-section. Heat flows from hot regions to cold regions, and this heat flow is irreversible—it converts mechanical energy to thermal energy. This mechanism is called thermoelastic damping (TED), first analyzed by Zener in 1937 [19] and later refined by Lifshitz and Roukes for MEMS structures.

**The Debye relaxation picture.** TED is strongest when the vibration period matches the thermal relaxation time of the rod—the time it takes heat to diffuse across the cross-section. The thermal relaxation time is $\tau_D = d^2 / (\pi^2 \kappa)$, where $d$ is the rod diameter and $\kappa$ is the thermal diffusivity of the glass. When $\omega \tau_D \approx 1$ (vibration period ~ relaxation time), the temperature gradients have just enough time to partially equilibrate during each cycle, extracting maximum energy. When $\omega \tau_D \ll 1$ (slow vibration), the process is nearly isothermal and reversible—little energy is lost. When $\omega \tau_D \gg 1$ (fast vibration), the process is nearly adiabatic—temperature gradients don't have time to equilibrate, and again little energy is lost. Maximum damping occurs at the crossover.

**For our design.** Glass has low thermal conductivity ($\kappa \approx 4.6 \times 10^{-7}$ m²/s for borosilicate), so the thermal relaxation time for a 40 µm rod is $\tau_D = (40 \times 10^{-6})^2 / (\pi^2 \times 4.6 \times 10^{-7}) \approx 3.5 \times 10^{-4}$ s, corresponding to a crossover frequency of ~450 Hz. Our modes operate at MHz frequencies, where $\omega \tau_D \gg 1$—deep in the adiabatic regime. The Zener/Lifshitz-Roukes formula (Appendix B) gives $Q_{\text{TED}} = 9{,}500{,}000$.

**Why it matters.** TED is negligible. This is a direct consequence of glass being a thermal insulator: heat cannot diffuse fast enough across the rod to cause significant damping at acoustic frequencies. For silicon resonators (which have ~300× higher thermal diffusivity), TED is often the dominant loss mechanism—one of several reasons glass is a better substrate for CWM than silicon.

### 6.4 Gas Damping ($Q_{\text{gas}}$)

**What it is.** A vibrating rod in a gas environment loses energy to the surrounding gas molecules. Each time a gas molecule strikes the rod's surface, it exchanges momentum and carries away a tiny amount of the rod's kinetic energy. At atmospheric pressure, the number of molecular collisions per second is enormous (roughly $10^{23}$ per cm² per second for air at 1 atm), and the cumulative energy loss can dominate all other mechanisms.

At the molecular level, gas damping in MEMS devices operates in one of two regimes. At high pressure (mean free path much smaller than the rod-to-wall gap), the gas behaves as a viscous fluid, and damping follows the Navier-Stokes equations ("squeeze-film damping"). At low pressure (mean free path much larger than the gap), individual molecules bounce independently between the rod and the cavity walls ("molecular-flow damping" or "free-molecular damping"). MEMS vacuum packages operate in the low-pressure regime.

**For our design.** At the standard MEMS packaging pressure of 0.1 Pa (about one-millionth of atmospheric pressure), the mean free path of residual gas molecules is ~70 mm—orders of magnitude larger than the rod-to-wall gap. We are firmly in the free-molecular regime. The damping force is proportional to pressure: lower pressure means less damping.

At 0.1 Pa: $Q_{\text{gas}} = 96{,}417$. At 0.01 Pa (achievable with getter materials): $Q_{\text{gas}}$ exceeds $10^6$, making gas damping truly negligible.

**Why it matters.** Gas damping is the one loss mechanism we can almost completely eliminate by engineering: evacuate the package. MEMS vacuum packaging at 0.01–0.1 Pa is a mature technology used in billions of MEMS gyroscopes, accelerometers, and oscillators. This is not a research challenge; it is a purchasing decision.

### 6.5 Surface Loss ($Q_{\text{surface}}$)

**What it is.** The surface of any real material is different from its bulk interior. For glass, the top few nanometers of surface are a damaged, hydrated, and/or reconstructed layer with different mechanical properties—higher internal friction, lower elastic modulus—compared to the pristine bulk glass beneath. This surface layer participates in the rod's vibration and contributes its own (higher) dissipation to the overall $Q$.

The effect is analogous to painting a high-quality bell with a thick layer of rubber: the rubber is lossy, and even a thin coat degrades the ring. The thinner the coat relative to the bell's wall thickness, the less it matters.

**The model.** For a cylindrical rod with diameter $d$ and a surface defect layer of thickness $\delta$ having its own quality factor $Q_d$:

$$\frac{1}{Q_{\text{surface}}} = \frac{4\delta}{d} \cdot \frac{1}{Q_d}$$

The factor $4\delta/d$ is the volume fraction of the defect layer (surface area × $\delta$, divided by total volume). With $\delta = 5$ nm (typical for polished glass), $Q_d = 1{,}000$ (conservatively low for amorphous surface damage), and $d = 40$ µm: $Q_{\text{surface}} = 40{,}000 / (4 \times 5 \times 10^{-3}) = 196{,}000$ (see Appendix B for the full derivation).

**Why it matters.** Surface loss matters more for smaller rods, because the surface-to-volume ratio increases as $1/d$. For our 40 µm rod, surface loss contributes 4.7% of the total budget—small but not negligible. For a 10 µm rod, it would contribute ~19%, becoming a significant factor. This sets a practical lower bound on rod diameter: below roughly 20 µm, surface loss begins to dominate unless the surface quality is improved (e.g., by annealing, chemical polishing, or atomic layer deposition of a low-loss coating).

### 6.6 Combined Q-Factor Budget

The five mechanisms are independent (they drain energy through different physical channels), so their loss rates add:

$$\frac{1}{Q_{\text{total}}} = \frac{1}{Q_{\text{mat}}} + \frac{1}{Q_{\text{anchor}}} + \frac{1}{Q_{\text{TED}}} + \frac{1}{Q_{\text{gas}}} + \frac{1}{Q_{\text{surface}}}$$

For the reference 1 mm borosilicate design:

| Mechanism              | $Q$       | Loss fraction |
| ---------------------- | --------- | ------------- |
| Material               | 10,000    | **91.1%**     |
| Surface loss           | 196,000   | 4.7%          |
| Anchor loss            | 215,711   | **4.2%**      |
| Gas damping            | 96,417    | ~0%           |
| TED                    | 9,500,000 | ~0%           |
| **$Q_{\text{total}}$** | **9,110** | 100%          |

The result is striking: **material intrinsic loss accounts for 91.1% of all energy dissipation.** The MEMS geometry—the tethers, the vacuum package, the surface—contributes less than 9% combined. In other words, the MEMS resonator preserves 91% of the bulk material's quality factor. Miniaturization does not destroy performance; it barely dents it.

**Anchor loss—the mechanism that dominates many MEMS resonator designs—is only 4.2% of our budget.** This is because we use thin, long tethers with isolation trenches, and because a longitudinal-mode rod is intrinsically well-isolated (the vibration is along the rod axis, while the tethers attach from the side, creating a geometric mismatch that reflects most energy back into the rod).

The $Q_{\text{total}} = 9{,}110$ is comfortably above the $Q > 5{,}000$ threshold for reduced-mode CWM operation, and within 9% of the material ceiling. Improving $Q_{\text{mat}}$ (by using fused silica, $Q_{\text{mat}} = 100{,}000$) would improve $Q_{\text{total}}$ nearly proportionally—see Section 11.3.

<div class="cwm-thumb">
<img src="figures/fig4_q_budget.svg" alt="Figure 4: Q-factor loss budget"/>
<p><strong>Figure 4.</strong> Q-factor loss budget for the reference 1 mm borosilicate design. Material intrinsic loss dominates; anchor loss is only 4.2%.</p>
</div>
