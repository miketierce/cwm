## 5. Track C — Multi-Shell Resonator

Track C addresses the most ambitious rewriting mechanism: physically tuning the rod itself by coating it with a thin "writable shell" whose mechanical properties can be externally controlled. Where Track A rewrites in software and Track B toggles discrete MEMS contacts, Track C continuously modulates the surface boundary condition—the closest analogue to a read/write disk surface.

Before we can evaluate shell feasibility, we must first answer a prerequisite question: _What is the Q-factor cost of putting anything on the rod surface?_

### 5.1 H12: Actuator Q Penalty

**Hypothesis.** MEMS electrostatic actuators can be added to the rod surface for binary-site switching (Track B) or shell control without reducing Q below the 5,000 minimum required for reliable spectral readout.

**Setup.** We model each actuator as a localized high-loss region on the rod surface: an electrostatic electrode pad with a characteristic footprint ($100\ \mu\text{m}^2$), thickness ($200\ \text{nm}$), and material Q ($Q_\text{act} = 500$—a conservative value for thin-film gold or aluminum on oxide). The actuator contributes additional loss:

$$
\frac{1}{Q_\text{actuator}} = \frac{N_\text{act} \cdot A_\text{act} \cdot t_\text{act}}{V_\text{rod} \cdot Q_\text{act}}
$$

This is added to the existing 5-mechanism loss budget (material, anchor, thermoelastic, surface, gas damping) from the baseline MEMS Q model [1, §6]. We sweep $N_\text{act}$ from 0 to 256 and find the maximum count that keeps $Q_\text{total} > 5{,}000$.

**Results.**

| Actuators ($N_\text{act}$) | Total Q | Penalty (%) |
| -------------------------- | ------- | ----------- |
| 0 (baseline)               | 9,506   | —           |
| 4                          | 9,495   | 0.12        |
| 8                          | 9,483   | 0.24        |
| 16                         | 9,460   | 0.48        |
| 32                         | 9,415   | 0.96        |
| 64                         | 9,327   | 1.88        |
| 128                        | 9,158   | 3.66        |
| 256                        | 8,838   | 7.03        |

- **Baseline Q:** 9,506
- **Q with 16 actuators:** 9,460 (0.48% penalty)
- **Actuator loss fraction:** 0.48% of total loss budget
- **Maximum actuators for $Q > 5{,}000$:** 256
- **Verdict: ✅ CONFIRMED**

**Interpretation.** The actuator loss is negligible. At 16 actuators (enough for Track B binary sites), the penalty is under half a percent. Even at 256 actuators—an absurdly large count for a 1 mm rod—the Q remains above 8,800, well over the 5,000 threshold. This is because the actuator volume ($N_\text{act} \times A_\text{act} \times t_\text{act}$) is tiny compared to the rod volume ($\pi r^2 L \approx 1.26 \times 10^{-12}\ \text{m}^3$). The surface-area fraction of 16 actuators is $\sim 0.013\%$ of the rod's lateral surface.

This result has two implications:

1. **Track B is Q-safe.** Binary perturbation sites with electrostatic latches can be added freely—12 sites add less than 0.4% loss.
2. **Track C is feasible.** We have thermal budget to spare for a writable shell, provided the shell material's own Q is not too low.

### 5.2 H13: Writable Shell Q Budget

**Hypothesis.** A thin writable shell can be deposited on the rod without reducing Q below 5,000, provided the shell thickness and material Q are within an identifiable design window.

**Concept.** The "writable shell" is a thin conformal coating whose acoustic properties can be externally modulated. Candidate materials include:

| Material                      | Shell $Q_d$ | Control mechanism                                          |
| ----------------------------- | ----------- | ---------------------------------------------------------- |
| Parylene C                    | 100–300     | Controllable deposition thickness                          |
| Terfenol-D (magnetostrictive) | 50–200      | Applied magnetic field changes elastic modulus             |
| GST / VO₂ (phase-change)      | 20–100      | Thermal/electrical switching between amorphous/crystalline |
| PDMS (polymer)                | 10–50       | UV cross-linking, solvent swelling                         |

The shell contributes additional loss proportional to its volume fraction:

$$
\frac{1}{Q_\text{shell}} = \frac{4\, t_\text{shell}}{d_\text{rod}} \cdot \frac{1}{Q_d}
$$

where the factor $4t/d$ is the volume fraction of a thin cylindrical shell ($t \ll d/2$). We sweep $t_\text{shell}$ from 1 to 1,000 nm and $Q_d$ from 10 to 5,000, computing the total Q at each grid point.

**Setup.** Baseline Q from the same 5-mechanism model as H12 ($Q_0 = 9{,}506$). Add shell loss to the total loss budget. Compute the $Q = 5{,}000$ contour in the $(t_\text{shell}, Q_d)$ plane. For the practical reference case (Parylene C, $Q_d = 200$), find the maximum allowable shell thickness.

**Results.**

**Q = 5,000 boundary (representative points):**

| Shell thickness (nm) | Minimum $Q_d$ |
| -------------------- | ------------- |
| 5                    | 10            |
| 10                   | 10            |
| 20                   | 20            |
| 50                   | 50            |
| 100                  | 200           |
| 200                  | 500           |

- **Maximum shell at $Q_d = 200$ (Parylene C):** 100 nm
- **Frequency shift at 100 nm:** 0.34% ($\Delta f / f \approx \frac{1}{2} \cdot m_\text{shell}/m_\text{rod}$)
- **Boundary points mapped:** 8
- **Verdict: ✅ CONFIRMED**

**Interpretation.** The Q budget carves out a clear design window. For a high-Q shell material like Parylene C ($Q_d \approx 200$), the rod can accommodate up to 100 nm of conformal coating while keeping $Q > 5{,}000$. This is thin—but it is enough:

1. **Frequency shift range.** The 100 nm Parylene shell shifts the fundamental frequency by $\sim 0.34\%$. Across 9,380 modes spanning $\sim 5\ \text{GHz}$ bandwidth, this corresponds to $\sim 17\ \text{MHz}$ of tuning range—far exceeding the $\sim 0.5\ \text{MHz}$ mode linewidth at $Q = 10{,}000$. The shell can shift modes by many linewidths, which is what "writing" means.

2. **The thickness–Q tradeoff is smooth.** There is no cliff edge. At 50 nm ($Q_d = 200$), the total Q is still above 7,000. Designers can tune the operating point along this curve depending on how much rewritability vs. readout fidelity they need.

3. **Phase-change materials are marginal but possible.** GST/VO₂ ($Q_d \sim 50$) limits the shell to $\sim 20$ nm. This may be sufficient for binary write/erase, but not for analog tuning. Magnetostrictive films ($Q_d \sim 100$–$200$) sit in the sweet spot: remotely controllable via applied field, with adequate Q budget for 50–100 nm layers.

### 5.3 Track C Summary

| Experiment | Question                           | Answer                                    | Implication                                         |
| ---------- | ---------------------------------- | ----------------------------------------- | --------------------------------------------------- |
| H12        | Does adding actuators kill Q?      | No—256 actuators still give $Q > 8{,}800$ | Tracks B and C are Q-feasible                       |
| H13        | How thick can a writable shell be? | Up to 100 nm at $Q_d = 200$               | 0.34% frequency shift; multi-linewidth tuning range |

Track C's writable shell is the highest-capability rewriting mechanism—it provides continuous, analog control over the perturbation landscape—but it also demands the most from fabrication. The 100 nm Parylene window is tight. The next section synthesizes all three tracks into a layered architecture that starts with firmware (zero fabrication cost), adds binary sites (modest MEMS complexity), and optionally includes a shell (advanced fabrication) as a third degree of freedom.

---
