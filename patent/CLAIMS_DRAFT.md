# CWM Draft Claims (Reference Only)

**These claims are NOT required for the provisional filing.** They are a working draft to help a patent attorney understand the intended scope when converting to a non-provisional utility application. Do NOT include this file in the provisional mailing unless you want to — it cannot hurt, but the specification (v18.pdf) is sufficient on its own.

---

## Independent Claims

### Claim 1 — Apparatus (The Device)

An acoustic memory device, comprising:

(a) a glass resonator having a longitudinal axis and supporting a plurality of acoustic eigenmodes;

(b) a plurality of perturbation masses disposed at predetermined positions along the longitudinal axis, wherein the perturbation masses modify the eigenfrequencies of the acoustic eigenmodes to encode a spectral fingerprint representing stored information;

(c) a piezoelectric transducer coupled to the resonator and configured to excite a broadband acoustic stimulus encompassing the plurality of eigenmodes; and

(d) a readout circuit configured to:
  (i) measure a frequency-domain response of the resonator to the broadband stimulus,
  (ii) compare the measured frequency-domain response to a query pattern, and
  (iii) generate an associative recall signal indicating a degree of match between the stored spectral fingerprint and the query pattern.

### Claim 2 — Method (Associative Recall)

A method for content-addressable memory access, comprising:

(a) providing a glass resonator supporting N acoustic eigenmodes, wherein perturbation masses at predetermined positions along the resonator encode a stored data pattern as shifts in eigenfrequencies of the N eigenmodes;

(b) exciting the resonator with a broadband acoustic stimulus;

(c) measuring a spectral response of the resonator in the frequency domain;

(d) computing a correlation between the measured spectral response and a query spectral pattern; and

(e) outputting a match signal when the correlation exceeds a predetermined threshold.

### Claim 3 — Array Architecture

A memory system comprising:

(a) an array of glass resonators, each resonator supporting a plurality of acoustic eigenmodes and each encoding a distinct spectral fingerprint via perturbation masses disposed along its longitudinal axis;

(b) a shared excitation circuit configured to simultaneously drive all resonators in the array with a broadband acoustic stimulus;

(c) individual piezoelectric readout transducers coupled to each resonator; and

(d) a parallel comparison circuit configured to identify the resonator in the array whose spectral response most closely matches a query input, thereby performing a parallel nearest-neighbour search across all stored patterns in a single acoustic cycle.

---

## Dependent Claims (Key Extensions)

### Claim 4 — Polysemic Readout (depends on Claim 1 or 2)

The device/method of claim [1/2], wherein the readout circuit is further configured to partition the N eigenmodes into C non-overlapping subsets, each subset defining an independent readout channel, and to extract C independent data projections from a single resonator, whereby the information capacity is multiplied by a factor of approximately C.

### Claim 5 — In-Situ Boolean Computation (depends on Claim 3)

The system of claim 3, wherein the excitation circuit is configured to simultaneously drive two or more resonators, and the comparison circuit is configured to extract a Boolean function of the stored patterns from constructive and destructive interference in the combined spectral response, thereby performing logic operations without transferring data to a separate processor.

### Claim 6 — Synaptic Pruning (depends on Claim 1 or 2)

The device/method of claim [1/2], wherein the readout circuit applies a weight vector to the measured spectral response, wherein weight values below a pruning threshold are set to zero, reducing the dimensionality of the comparison and improving discrimination between stored patterns.

### Claim 7 — Mode Hybridization (depends on Claim 1)

The device of claim 1, wherein at least two perturbation masses are positioned to produce near-degeneracy between two eigenmodes, resulting in an avoided crossing that generates two hybrid modes with a measurable frequency splitting, thereby encoding additional information in the splitting magnitude.

### Claim 8 — Null-Space Multiplexing (depends on Claim 1 or 2)

The device/method of claim [1/2], wherein the readout circuit performs singular value decomposition on the spectral response matrix and extracts information encoded in null-space components that are orthogonal to the primary perturbation pattern, thereby increasing storage capacity beyond the primary channel.

### Claim 9 — Binary Perturbation Sites (depends on Claim 1)

The device of claim 1, further comprising electrostatic MEMS latches at a plurality of perturbation sites along the resonator, each latch switchable between an engaged state coupling a perturbation mass to the resonator and a disengaged state decoupling the perturbation mass, thereby enabling reprogrammable data encoding without replacing the resonator.

### Claim 10 — Firmware Virtual Rewriting (depends on Claims 1 and 4)

The device of claim 4, wherein different mode subsets are assigned to different logical data words, and the readout circuit is reconfigured via firmware to select among the mode subsets, thereby providing virtual rewritability without physical modification of the perturbation masses.

### Claim 11 — Multi-Shell Resonator (depends on Claim 1)

The device of claim 1, further comprising a conformal shell layer coating the resonator, the shell layer having an analogue-tunable acoustic impedance, wherein modifying properties of the shell layer modifies the eigenfrequencies so as to rewrite the stored spectral fingerprint.

### Claim 12 — MEMS Fabrication (depends on Claim 1)

The device of claim 1, wherein:

(a) the glass resonator is a borosilicate or fused silica beam having a length between 100 micrometres and 10 millimetres, fabricated by deep reactive ion etching of a glass wafer;

(b) the perturbation masses are thin-film metallic deposits patterned by photolithography; and

(c) the piezoelectric transducer is a thin-film aluminium nitride (AlN) layer deposited on the resonator surface.

---

## Claim Strategy Notes for Attorney

1. **Claim 1** is the broadest apparatus claim. It should survive prior art on individual MEMS resonators because no prior art combines perturbation-encoded eigenmode storage with interference-based associative recall in a glass acoustic resonator.

2. **Claim 3** (array + parallel search) is the system-level commercial claim. This is what a CWM chip actually is. It captures the "all rods searched in one acoustic cycle" advantage.

3. **Claim 4** (polysemic readout) is the highest-value technique claim. It produces a +297% capacity gain and is not obvious from existing MEMS resonator literature. It was inspired by Dogon polysemic symbol encoding (documented in the paper, §11.5), which makes it difficult to argue obviousness from the acoustic MEMS prior art alone.

4. **Claims 9–11** cover the three rewritability tracks. Even if only one succeeds in hardware, having provisional coverage on all three preserves optionality.

5. **VitalID** (Rutgers, 2025) uses skull vibrations as a biometric identifier. It shares the underlying physics (geometry → vibrational spectrum → identifier) but targets a completely different application (biometric authentication vs. data storage). It does not anticipate any of these claims. However, if you later want to patent a CWM-based biometric system, VitalID would be relevant prior art in that narrow overlap.

6. The **public GitHub repo and website** constitute your own prior disclosures. Under 35 U.S.C. § 102(b)(1)(A), your own public disclosures do not count as prior art against you if you file within one year of first disclosure. Confirm the earliest commit date and ensure filing happens within that window.
