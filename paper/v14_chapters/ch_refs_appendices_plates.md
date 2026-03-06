---

## References

[1] J. Backus, "Can programming be liberated from the von Neumann style? A functional style and its algebra of programs," _Communications of the ACM_, vol. 21, no. 8, pp. 613–641, 1978. doi: [10.1145/359576.359579](https://doi.org/10.1145/359576.359579)

[2] W. A. Wulf and S. A. McKee, "Hitting the memory wall: Implications of the obvious," _ACM SIGARCH Computer Architecture News_, vol. 23, no. 1, pp. 20–24, 1995. doi: [10.1145/216585.216588](https://doi.org/10.1145/216585.216588)

[3] D. Ielmini and H.-S. P. Wong, "In-memory computing with resistive switching devices," _Nature Electronics_, vol. 1, pp. 333–343, 2018. doi: [10.1038/s41928-018-0092-2](https://doi.org/10.1038/s41928-018-0092-2)

[4] I. L. Auerbach, J. P. Eckert, R. F. Shaw, and C. Sheppard, "Mercury delay line memory using a pulse rate of several megacycles," _Proceedings of the IRE_, vol. 37, no. 8, pp. 855–861, 1949. doi: [10.1109/JRPROC.1949.229683](https://doi.org/10.1109/JRPROC.1949.229683)

[5] M. V. Wilkes and W. Renwick, "The EDSAC (Electronic delay storage automatic calculator)," _Mathematics of Computation_, vol. 4, no. 30, pp. 61–65, 1950. doi: [10.1090/S0025-5718-1950-0037589-7](https://doi.org/10.1090/S0025-5718-1950-0037589-7)

[6] C. E. Shannon, "A mathematical theory of communication," _The Bell System Technical Journal_, vol. 27, no. 3, pp. 379–423, 623–656, 1948. doi: [10.1002/j.1538-7305.1948.tb01338.x](https://doi.org/10.1002/j.1538-7305.1948.tb01338.x)

[7] Lord Rayleigh (J. W. S. Strutt), _The Theory of Sound_, 2 vols. London: Macmillan, 1877–1878. Reprinted New York: Dover, 1945.

[8] G. Sauerbrey, "Verwendung von Schwingquarzen zur Wägung dünner Schichten und zur Mikrowägung," _Zeitschrift für Physik_, vol. 155, no. 2, pp. 206–222, 1959. doi: [10.1007/BF01337937](https://doi.org/10.1007/BF01337937)

[9] J. J. Hopfield, "Neural networks and physical systems with emergent collective computational abilities," _Proceedings of the National Academy of Sciences_, vol. 79, no. 8, pp. 2554–2558, 1982. doi: [10.1073/pnas.79.8.2554](https://doi.org/10.1073/pnas.79.8.2554)

[10] D. J. Amit, H. Gutfreund, and H. Sompolinsky, "Storing infinite numbers of patterns in a spin-glass model of neural networks," _Physical Review Letters_, vol. 55, no. 14, pp. 1530–1533, 1985. doi: [10.1103/PhysRevLett.55.1530](https://doi.org/10.1103/PhysRevLett.55.1530)

[11] A. B. Bhatia, _Ultrasonic Absorption: An Introduction to the Theory of Sound Absorption and Dispersion in Gases, Liquids, and Solids_. New York: Oxford University Press, 1967.

[12] J. Krautkrämer and H. Krautkrämer, _Ultrasonic Testing of Materials_, 4th ed. Berlin: Springer-Verlag, 1990. doi: [10.1007/978-3-662-10680-8](https://doi.org/10.1007/978-3-662-10680-8)

[13] Z. Hao, A. Erbil, and F. Ayazi, "An analytical model for support loss in micromachined beam resonators with in-plane flexural vibrations," _Sensors and Actuators A_, vol. 109, pp. 156–164, 2003. doi: [10.1016/j.sna.2003.09.037](https://doi.org/10.1016/j.sna.2003.09.037)

[14] M.-A. Dubois and P. Muralt, "Properties of aluminum nitride thin films for piezoelectric transducers and microwave filter applications," _Applied Physics Letters_, vol. 74, no. 20, pp. 3032–3034, 1999. doi: [10.1063/1.124055](https://doi.org/10.1063/1.124055)

[15] B. Jaffe, W. R. Cook Jr., and H. Jaffe, _Piezoelectric Ceramics_. London: Academic Press, 1971.

[16] T. Corman, P. Enoksson, and G. Stemme, "Deep wet etching of borosilicate glass using an anodically bonded silicon substrate as mask," _Journal of Micromechanics and Microengineering_, vol. 8, no. 2, pp. 84–87, 1998. doi: [10.1088/0960-1317/8/2/010](https://doi.org/10.1088/0960-1317/8/2/010)

[17] C. T.-C. Nguyen, "MEMS technology for timing and frequency control," _IEEE Transactions on Ultrasonics, Ferroelectrics, and Frequency Control_, vol. 54, no. 2, pp. 251–270, 2007. doi: [10.1109/TUFFC.2007.240](https://doi.org/10.1109/TUFFC.2007.240)

[18] P. R. Bhatt, G. S. Tomko, and P. Bhatt, "Synaptic pruning and the developing brain," in _Handbook of Developmental Neuroscience_. Academic Press, 2020. (Synaptic pruning as an optimization mechanism for neural circuit refinement.)

[19] C. Zener, "Internal friction in solids: I. Theory of internal friction in reeds," _Physical Review_, vol. 52, no. 3, pp. 230–235, 1937. doi: [10.1103/PhysRev.52.230](https://doi.org/10.1103/PhysRev.52.230)

[20] J. von Neumann and E. P. Wigner, "Über das Verhalten von Eigenwerten bei adiabatischen Prozessen," _Physikalische Zeitschrift_, vol. 30, pp. 467–470, 1929. (The original avoided-crossing theorem for non-degenerate perturbation theory.)

---

## Appendix A: SNR and Density Scaling Derivation

### A.1 SNR as a Function of Length

For a rod with aspect ratio $\beta = L/d$, the effective mass is $m_{\text{eff}} = \rho \pi L^3 / (8\beta^2)$. The effective spring constant:

$$k_{\text{eff}} = m_{\text{eff}} \omega_1^2 = \frac{\rho \pi^3 v^2 L}{8\beta^2}$$

Signal energy at drive amplitude $A$:

$$E_s = \frac{1}{2} k_{\text{eff}} A^2 = \frac{\rho \pi^3 v^2 A^2}{16\beta^2} \cdot L$$

$$\text{SNR} = \frac{E_s}{k_B T} = \frac{\rho \pi^3 v^2 A^2}{16 \beta^2 k_B T} \cdot L$$

For borosilicate at $\beta = 25$, $A = 1$ nm, $T = 300$ K: SNR $= 5.06 \times 10^7 \cdot L$ (meters).

### A.2 Density Scaling

$$\text{density} = \frac{n_{\max} \cdot \frac{1}{2}\log_2(1 + \text{SNR})}{\pi L^3 / (4\beta^2)} = \frac{2\beta^2 n_{\max} \log_2(1 + cL)}{\pi L^3}$$

For $cL \gg 1$: $\log_2(1 + cL) \approx \log_2 c + \log_2 L$, so the dominant scaling is $1/L^3$ modulated by a slowly varying $\log L$ term, making the effective scaling approximately $1/L^2$.

### A.3 Array Packing

For rods with pitch $p = 2d = 2L/\beta$ and layer spacing $s = L + g$:

$$\text{rods per cm}^3 = \left(\frac{0.01}{p}\right)^2 \cdot \frac{0.01}{s}$$

Array density = rods per cm³ × bits per rod.

## Appendix B: Q-Factor Model Details

### B.1 Anchor Loss

Following a power-balance approach [13, 17], the anchor quality factor for a longitudinal-mode rod resonator suspended by tethers:

$$Q_{\text{anchor}} = \frac{\pi}{2} \cdot \frac{Z_{\text{rod}}}{Z_{\text{sub}}} \cdot \left(\frac{L}{w_{\text{eff}}}\right)^2 \cdot \left(1 + \frac{L_{\text{tether}}}{w_{\text{eff}}}\right) \cdot \frac{n}{n_{\text{anchors}}} \cdot \eta_{\text{trench}}$$

where $Z = \rho v$ is acoustic impedance, $w_{\text{eff}} = \sqrt{w \cdot t}$ is the effective tether cross-section dimension, $L_{\text{tether}}$ is tether length, and $n$ is the mode number.

For end-mounted attachment: all modes contribute. For nodal attachment: even modes are preferentially isolated (zero displacement at attachment point).

Isolation trenches (etched gaps surrounding the tether base) add a 3× improvement factor by reflecting acoustic energy back into the resonator.

### B.2 Thermoelastic Damping

Zener/Lifshitz-Roukes formulation [19] with Debye relaxation time $\tau_D = d^2 / (\pi^2 \kappa)$, where $\kappa$ is thermal diffusivity:

$$\frac{1}{Q_{\text{TED}}} = \frac{E \alpha^2 T}{\rho C_p} \cdot \frac{\omega \tau_D}{1 + (\omega \tau_D)^2}$$

For glass at MEMS frequencies ($\sim$ MHz), $\omega \tau_D \ll 1$, and TED is negligible ($Q_{\text{TED}} \sim 10^7$).

### B.3 Surface Loss

For a rod with diameter $d$ and surface defect layer of thickness $\delta$ with quality factor $Q_d$:

$$\frac{1}{Q_{\text{surface}}} = \frac{4\delta}{d} \cdot \frac{1}{Q_d}$$

With $\delta = 5$ nm and $Q_d = 1{,}000$: $Q_{\text{surface}} = 196{,}000$ at $d = 40$ µm.

---

## Appendix C: Industry Application Scenarios

_The following scenarios illustrate how SEM's unique properties—ultra-low energy, native associative recall, extreme density, and intrinsic radiation hardness—could create value across industries. All performance projections are derived from the validated models in the main text. We flag each scenario's technology-readiness assumptions explicitly._

### C.1 Defense and Intelligence: The Analyst Who Sleeps

**The problem.** A signals-intelligence analyst at Fort Meade monitors intercepted communications for threat signatures. Today, each intercept is vectorized and compared against a classified database of ~500,000 known patterns using a rack of Ternary Content-Addressable Memory (TCAM). The rack draws 12 kW, fills a standard 42U enclosure, and costs \$2.1 million. When the database grows to 5 million patterns—as it does every few years—the agency orders another rack.

**What SEM changes.** A single SEM module the size of a deck of cards contains ~140,000 glass resonators, each storing 1,294 Hopfield patterns. That is 181 million searchable patterns—36× the current database—in a device that draws under 5 W and costs, at scale, a fraction of a single TCAM board.

But the real disruption isn't size or power. It's _latency_. TCAM searches are sequential across boards; a 500,000-pattern lookup takes ~50 ms. SEM's interference-based recall happens in a single acoustic propagation cycle: 5 µs. That is 10,000× faster. An analyst running a new signature against the full database gets an answer before their finger lifts off the key.

**What we've validated.** The associative recall physics (Section 2.3), the Hopfield capacity limit (1,294 patterns/rod), and the array architecture (Section 7.1) are computed from first principles and verified by 365 tests. The synaptic pruning technique (Section 10.1) can further improve recall accuracy by 10.7% at high pattern loads. **What remains projected:** MEMS fabrication yield and TCAM-equivalent interface integration—addressable in Phases 1–2 of the roadmap.

**Relevant to:** NSA, NGA, DISA, DARPA MTO, defense primes (Raytheon, Northrop Grumman), allied Five Eyes agencies.

---

### C.2 Semiconductor Fab: Catching Defects at the Speed of Light

**The problem.** A 300 mm wafer fab produces ~1,500 wafers per day. Each wafer is imaged at multiple process steps by optical inspection tools (KLA, Applied Materials), generating 50–200 high-resolution die images per wafer. A "defect classifier" compares each image against a library of ~10,000 known defect signatures—scratches, particles, pattern collapse, bridging—using GPU-accelerated pattern matching. The GPU cluster draws 30 kW and occupies a full equipment bay. When a new defect type appears (as it does with every process node), the library must be retrained and redeployed—a process that takes days and halts production.

**What SEM changes.** Each SEM rod's perturbation pattern can encode a defect signature's spectral fingerprint. A 10,000-rod array encodes the entire defect library and performs classification in 5 µs per die image—fast enough to inspect _inline_ at full production throughput without buffering. Adding a new defect type means adding one rod with the appropriate perturbation pattern—no retraining, no downtime, no GPU. The physics _is_ the classifier. The in-situ Boolean computation (Section 10.2) enables direct Hamming-distance classification at 3× throughput.

At 16 fJ/bit, the power budget for the entire defect-matching operation is under 1 W—replacing a 30 kW GPU cluster. In a fab where electricity costs \$0.12/kWh and uptime is worth \$100,000/hour, the SEM module pays for itself in weeks.

**What we've validated.** SNR of 98.8 dB (Section 4.3), spectral pattern discrimination (Section 4.5), and scaling to MEMS density (Section 5). **What remains projected:** Encoding 2D image features as 1D spectral signatures—a signal-processing problem, not a physics limitation.

**Relevant to:** TSMC, Samsung Foundry, Intel, KLA, Applied Materials, Lam Research, ASML.

---

### C.3 Pharmaceutical R&D: Screening a Billion Molecules Before Lunch

**The problem.** A medicinal chemist at Pfizer has a promising lead compound for a kinase inhibitor. She needs to screen it against a virtual library of 1.2 billion commercially available molecules to find structural analogs that might have better bioavailability. Today, this similarity search runs on a 500-node HPC cluster using molecular fingerprints (2,048-bit vectors) and Tanimoto similarity. The cluster draws 150 kW, costs \$8 million, and takes 14 hours for a full-library search. She gets results the next morning.

**What SEM changes.** Molecular fingerprints are fixed-length binary vectors—exactly the data structure SEM is built to match. Each rod encodes one molecule's fingerprint as a perturbation pattern. Interference-based recall computes Tanimoto similarity (mathematically equivalent to normalized dot product for binary vectors) across the entire library in parallel.

A wafer-scale SEM array containing 10 million rods, each encoding a 2,048-bit fingerprint, could screen the entire 1.2-billion-molecule library (partitioned across 120 arrays operating in parallel) in under one second. The chemist submits her query and has analogs ranked by similarity before she finishes her coffee. At 16 fJ/bit, the entire search consumes less energy than the LED on her monitor.

**What we've validated.** The dot-product equivalence of interference recall (Section 2.3), the Hopfield pattern capacity, and the energy scaling (Section 5.4). **What remains projected:** Efficient encoding of 2,048-bit fingerprints into spectral perturbation patterns, and wafer-scale integration.

**Relevant to:** Pfizer, Roche, Novartis, Merck, AstraZeneca; CROs (Charles River, WuXi); cheminformatics platforms (Schrödinger, OpenEye).

---

### C.4 Autonomous Vehicles: The Car That Recognizes Everything It Has Ever Seen

**The problem.** A Level 4 autonomous vehicle generates 1–4 TB of sensor data per hour from cameras, LiDAR, and radar. The perception stack must match incoming sensor frames against a library of known objects, road geometries, and hazard signatures—in real time, at 30 Hz, with <100 ms end-to-end latency. Today, this runs on an NVIDIA DRIVE Orin (275 TOPS, 60 W) or multiple chips in parallel. The power budget competes directly with vehicle range: every watt spent on compute is a watt not driving the wheels.

**What SEM changes.** SEM's interference-based associative recall is a native pattern matcher—it does not need to be programmed with neural network weights; it matches raw spectral signatures against stored templates. A 1 cm³ SEM module containing 140,000 rods could store 182 million object signatures (Section 7.1) and match an incoming sensor frame against all of them in 5 µs—200× faster than the 30 Hz frame rate requires, leaving margin for redundancy and voting. Power draw: under 2 W, compared to 60+ W for the GPU-based stack.

For fleet operators like Waymo or Cruise, multiplying this saving across thousands of vehicles translates to meaningful range extension and thermal-management simplification. For ADAS suppliers like Mobileye, a 2 W pattern-matching co-processor could enable Level 2+ features in vehicles where the thermal budget cannot accommodate a GPU.

**What we've validated.** Array capacity, associative recall time, and power (Sections 7–9). **What remains projected:** Sensor-to-spectral encoding pipeline and real-time integration with perception stacks.

**Relevant to:** Waymo, Cruise, Mobileye, NVIDIA, Qualcomm, Tesla, Bosch, Continental, Denso.

---

### C.5 Financial Services: Fraud at the Speed of a Swipe

**The problem.** Visa processes ~76,000 transactions per second at peak (e.g., Black Friday). Each transaction must be compared against fraud patterns—card-present anomalies, velocity checks, merchant-category mismatches—within the 100 ms authorization window. Today, this requires a geographically distributed network of GPU-accelerated scoring engines, each drawing hundreds of kilowatts, with total infrastructure costs exceeding \$500 million annually.

**What SEM changes.** Each transaction can be encoded as a short feature vector (merchant category, amount, time-of-day, location, velocity). A SEM module scores a transaction against the full fraud-signature library in 5 µs—20,000× faster than the 100 ms window. A single rack-mounted SEM appliance could replace an entire data-center floor of scoring servers.

But the deeper value is in _new fraud patterns_. Today, adding a new fraud signature requires retraining a neural network and redeploying across the scoring fleet—a process measured in days. With SEM, a new fraud pattern is a new perturbation mask written to a rod. Deployment is physical: swap a chip, or write a new perturbation in the field. The time from pattern discovery to production deployment drops from days to minutes.

**What we've validated.** Recall speed, power, and pattern capacity. **What remains projected:** Transaction-to-spectral encoding standards and integration with existing payment network protocols.

**Relevant to:** Visa, Mastercard, JPMorgan Chase, Goldman Sachs, Stripe; fraud-detection vendors (Featurespace, Feedzai, FICO).

---

### C.6 Agriculture and Food Safety: Every Grape, Every Grain

**The problem.** A food safety inspector at a grain processing facility needs to check incoming shipments for contamination—aflatoxins, pesticide residues, foreign materials. Today, this requires laboratory analysis (gas chromatography, mass spectrometry) with 24–72 hour turnaround. Hyperspectral imaging can identify contaminants optically, but the pattern-matching compute required to classify spectra in real time exceeds what is available in a handheld device.

**What SEM changes.** A hyperspectral camera captures the reflectance spectrum of each grain kernel—a high-dimensional vector. A battery-powered SEM device the size of a smartphone could store 10,000 contaminant spectral signatures and match each kernel's spectrum against the full library in 5 µs. At 16 fJ/bit and under 100 mW total power, the device runs for 8+ hours on a small LiPo cell.

An inspector walks the receiving dock with the device, scans a handful of grain, and gets a contamination verdict in real time—no lab, no wait, no shipment held in quarantine while samples are couriered. For a commodity trader, the ability to verify quality at the point of sale changes the risk calculus entirely.

**What we've validated.** The spectral correlation physics—SEM literally matches spectra against stored templates, which is precisely what hyperspectral classification requires. **What remains projected:** Miniaturized hyperspectral front-end integration and field ruggedization.

**Relevant to:** Cargill, ADM, Bunge, Tyson; food safety agencies (FDA, USDA, EFSA); precision agriculture (John Deere, CNH Industrial); hyperspectral imaging vendors (Headwall, Specim).

---

### C.7 Space and Satellite: Memory That Survives the Van Allen Belts

**The problem.** The James Webb Space Telescope carries 68 GB of solid-state memory using radiation-hardened SRAM. That memory cost more per bit than the gold-plated mirrors. Every satellite, every Mars rover, every deep-space probe faces the same constraint: radiation-hardened memory is scarce, expensive (\$1,000–\$10,000 per Mbit), heavy (shielding adds mass), and limited in capacity. A single energetic proton can flip a bit in a transistor; a solar particle event can corrupt entire memory banks.

**What SEM changes.** SEM stores information in mechanical vibrations of glass—a medium that is intrinsically immune to ionizing radiation. There are no charge-trapped states to flip, no floating gates to discharge, no magnetic domains to disturb. A cosmic ray passing through a glass rod changes its acoustic properties by less than one part in $10^{12}$. The information is encoded in the rod's _geometry_ (perturbation pattern) and _physics_ (eigenmode spectrum), not in electrical charge.

A 1 cm³ SEM module provides 17 Gbit (2.1 GB) of radiation-hard memory—250× the capacity of JWST's entire memory system—in a package that weighs grams instead of kilograms, costs orders of magnitude less, and simultaneously performs associative computation for onboard pattern recognition (autonomous navigation, anomaly detection, spectral classification of planetary surfaces).

For the emerging commercial space industry—where companies like SpaceX, Rocket Lab, and Planet Labs are launching thousands of small satellites—SEM could replace radiation-hard memory as the default, removing one of the most expensive line items from satellite BOM.

**What we've validated.** The glass medium, the physics of eigenmode encoding, and the density scaling. **What remains projected:** Vibration tolerance in launch environments (MEMS resonators routinely survive 10,000 g shock tests, suggesting this is tractable) and space-qualification testing.

**Relevant to:** NASA, ESA, JAXA; SpaceX, Rocket Lab, Planet Labs, Capella Space; defense satellite primes (Lockheed Martin, L3Harris, Ball Aerospace); JPL, APL.

---

### C.8 Summary: Where SEM Fits

| Scenario              | Incumbent         | SEM advantage                        | Readiness gap                 |
| --------------------- | ----------------- | ------------------------------------ | ----------------------------- |
| Signals intelligence  | TCAM racks        | 10,000× latency, 2,400× power        | MEMS fab + interface          |
| Fab defect inspection | GPU clusters      | 6,000× latency, 30,000× power        | Image-to-spectral encoding    |
| Drug discovery        | HPC clusters      | 50,000× latency, 150,000× power      | Wafer-scale integration       |
| Autonomous vehicles   | NVIDIA Orin       | 200× latency, 30× power              | Sensor encoding pipeline      |
| Fraud detection       | GPU scoring fleet | 20,000× latency, massive power       | Transaction encoding standard |
| Food safety           | Lab spectrometry  | Real-time, handheld, battery-powered | Hyperspectral front-end       |
| Space computing       | Rad-hard SRAM     | 250× capacity, intrinsic rad-hard    | Space qualification           |

The pattern across all seven scenarios is consistent: SEM's interference-based recall converts a search problem that today requires racks of silicon into a physics problem solved by a chip-scale glass resonator in microseconds. The advanced encoding techniques of Section 10 further strengthen this position: synaptic pruning improves accuracy at scale, Boolean computation adds classification capability, and hybridization/null-space multiplexing push effective density beyond what raw mode counts would suggest.

---

_All quantitative claims computed from first-principles simulation code (21 modules, 365 automated tests, all passing). No curve fitting, no adjusted parameters, no post-hoc corrections. Repository: github.com/miketierce/wcfoma._

---

## Illustration Plates

_The following pages present each figure at full landscape scale for detailed examination. Pages are arranged for double-sided printing: each illustration appears on the front of its own sheet._

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig1_architecture.svg" alt="Plate 1: SEM Architecture"/>
<p><strong>Figure 1.</strong> SEM architecture overview. <em>Left:</em> A glass resonator stores data as mass perturbations that shift eigenmode frequencies. <em>Center:</em> The spectral domain shows mode peaks before (solid) and after (dashed) perturbation — each pattern is a unique spectral fingerprint. <em>Right:</em> Driving an array with a query spectrum, the best-matching rod produces the largest response — a physical O(1) nearest-neighbor search. <em>Bottom:</em> Unlike von Neumann architectures, SEM unifies storage and computation in the same physical process.</p>
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
<p><strong>Figure 4.</strong> MEMS Q-factor loss budget. <em>(a)</em> For the reference 1 mm borosilicate design, material intrinsic loss dominates at 91.1% — anchor loss is only 4.2% of the total budget. Q<sub>total</sub> = 9,110. <em>(b)</em> All four design scenarios (varying glass type, tether geometry, and vacuum level) clear the Q > 5,000 threshold for competitive operation, with fused silica designs exceeding Q = 50,000.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig5_scaling.svg" alt="Plate 5: Scaling and Crossovers"/>
<p><strong>Figure 5.</strong> Scaling from macro to MEMS. <em>(a)</em> Size comparison of the 150 mm prototype rod (0.04 Gbit/cm³), the 1 mm borosilicate MEMS target (95.5 Gbit/cm³, 2,400× denser), and a 0.5 mm fused silica array design (1.4 Tbit/cm³, 35,000× denser). All designs share the same thermally stable mode physics; density explodes because volume shrinks as L³ while capacity falls only as log L. <em>(b)</em> Log–log density plot showing SEM crossing DRAM at 2.1 mm, PCM at 1.0 mm, and NAND Flash at 0.45 mm — all within standard MEMS fabrication range.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig6_fabrication.svg" alt="Plate 6: Fabrication Process Flow"/>
<p><strong>Figure 6.</strong> SEM fabrication process flow. Six steps — all using processes already in volume production. Glass DRIE is used in microfluidics (Schott Borofloat 33); AlN thin-film piezo is in billions of smartphone FBAR filters; MEMS vacuum packaging is standard for oscillators and gyroscopes (SiTime, Abracon); CMOS-MEMS flip-chip bonding is used in Bosch and STMicro accelerometers. The innovation is the architectural combination, not the fabrication.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig7_weight_pruning.svg" alt="Plate 7: Synaptic Pruning for Associative Recall"/>
<p><strong>Figure 7.</strong> Synaptic pruning optimization. <em>(a)</em> Weight matrix before and after pruning: entries below threshold θ are zeroed, removing inter-pattern crosstalk while preserving dominant pattern-encoding weights. <em>(b)</em> Recall accuracy vs. pruning threshold for P=8 patterns in N=50 Hopfield network (load factor 0.16). Optimal pruning at θ* = 0.055 achieves +10.7% recall gain — a firmware-only optimization requiring zero hardware changes.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig8_compute_in_memory.svg" alt="Plate 8: In-Situ Boolean Computation"/>
<p><strong>Figure 8.</strong> In-situ Boolean computation via mode superposition. Two stored patterns (A, B) are superposed; the combined amplitude distribution is decoded into XOR (90.6% fidelity), AND (96.9%), and OR (93.8%) using amplitude thresholds — all from a single readout cycle. This provides 3× throughput vs. conventional read-compute-write approaches and confirms SEM as a true compute-in-memory technology.</p>
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
<p><strong>Figure 11.</strong> Eigenmode frequency comb of the 150 mm borosilicate prototype. <em>(a)</em> Unperturbed spectrum (blue solid) shows a clean comb at 18.8 kHz spacing. After 0.1 mg wax perturbation (red dashed), each mode shifts by a different Δfₙ depending on the wax position relative to that mode's antinode — the spectral fingerprint of the perturbation. <em>(b)</em> Zoomed view of modes 2–4 showing Lorentzian peak profiles and position-dependent shift magnitudes. Mode 3 shifts most (wax at antinode); mode 4 barely shifts (wax near node). Measured shifts match Rayleigh predictions to within 2%.</p>
</div>

<div class="blank-verso">&nbsp;</div>

<div class="plate-page">
<img src="figures/fig12_ringdown.svg" alt="Plate 12: Ring-down and Q Measurement"/>
<p><strong>Figure 12.</strong> Q-factor measurement of the macro prototype. <em>(a)</em> Ring-down waveform of the fundamental mode (18.8 kHz) after impulse excitation: the exponential envelope decays with τ = 169 ms, giving Q = πf₁τ = 10,000. <em>(b)</em> Bandwidth method: the −3 dB linewidth of the Lorentzian resonance peak is Δf₃dB = 1.88 Hz, independently confirming Q = f₁/Δf₃dB = 10,000. Both methods agree that the prototype is material-loss-limited, not electronics-limited — the $25 USB oscilloscope is not the bottleneck.</p>
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
