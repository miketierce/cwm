## 2. The Rewritability Question

### 2.1 Telescope vs. Instrument

Consider two ways to think about a SEM rod:

**The telescope model.** A rod is manufactured with a fixed perturbation pattern and deployed as a matched filter for that pattern. It is a detector, not a programmable device. You "point" the telescope by choosing which rod to read, not by changing what any rod stores. An array of 1,000 rods is a library of 1,000 fixed filters—like a radio telescope array where each dish is permanently aimed at a different star.

**The instrument model.** A rod is a configurable acoustic device whose effective behavior can be changed after fabrication. It is a pipe organ, not a telescope—the same pipes can play different music depending on which stops are pulled and which keys are pressed. Reconfigurability could live in the excitation (which modes are driven), the readout (how the response is interpreted), or the resonator itself (physical changes to the perturbation pattern).

The companion paper presents SEM exclusively in telescope mode. This is the conservative, validated position: the physics works, the numbers are solid, and fixed-pattern applications (CAM, fingerprint matching, edge inference) are commercially significant.

But the instrument model is more interesting—and, as we will show, more physically accessible than it first appears.

### 2.2 Five Candidate Architectures

Brainstorming from first principles, we identified five candidate paths to rewritability. Each represents a different point on the hardware-modification spectrum:

1. **Replaceable rod cartridges.** Physically swap rods. Equivalent to swapping an EPROM chip—rewritable at the system level, not the device level. Trivially implementable but limited to coarse-grained updates.

2. **Reset-coat-rebaseline.** Chemically strip the perturbation layer, recoat, re-measure. Rewritable in the sense that a whiteboard is rewritable—possible, but slow and destructive.

3. **Binary perturbation sites.** Pre-fabricate discrete docking sites on the rod; each site has a MEMS switch that toggles a small mass between coupled (touching the rod) and decoupled (lifted off). Like RF MEMS switches, which already operate at GHz frequencies in 5G front-ends.

4. **Multi-shell resonator.** High-Q glass core surrounded by a thin writable shell (polymer, phase-change material, magnetostrictive film). The shell perturbs modes without killing the core's Q. Analogous to how a violin string's overtone spectrum depends on the rosin coating, not just the steel core.

5. **Firmware-defined virtual rewriting.** Don't change the rod at all. Change what you _ask_ it and how you _listen_. Different excitation patterns and readout projections make the same physical rod behave like different logical devices.

Architectures 1 and 2 are mechanical and chemical operations—important for system-level design but not interesting physics questions. We set them aside.

Architectures 3, 4, and 5 are testable with existing simulation infrastructure. They map to our three experimental tracks:

| Track | Architecture                       | Hardware change              | Rewrite speed                                         | Experiments |
| ----- | ---------------------------------- | ---------------------------- | ----------------------------------------------------- | ----------- |
| A     | Firmware-defined virtual rewriting | None                         | Nanoseconds (firmware load)                           | H7, H8, H9  |
| B     | Binary perturbation sites          | MEMS switches on rod surface | Microseconds (electrostatic latch)                    | H10, H11    |
| C     | Multi-shell resonator              | Thin-film writable coating   | Milliseconds–seconds (phase change, magnetostriction) | H12, H13    |

### 2.3 The Central Constraint

All three tracks must satisfy the same constraint: **rewriting must not destroy Q.**

The companion paper's Q-factor analysis [1, §6] established that the total quality factor of a 1 mm MEMS glass resonator is $Q_{\text{total}} = 9{,}110$, with material intrinsic loss ($Q_{\text{mat}} = 10{,}000$) as the dominant mechanism. The 5-mechanism loss budget is:

$$\frac{1}{Q_{\text{total}}} = \frac{1}{Q_{\text{mat}}} + \frac{1}{Q_{\text{anchor}}} + \frac{1}{Q_{\text{TED}}} + \frac{1}{Q_{\text{surface}}} + \frac{1}{Q_{\text{gas}}}$$

Any rewrite mechanism adds a new loss term. Track A avoids this entirely (firmware changes don't add loss). Tracks B and C add physical structures that contribute to $1/Q_{\text{surface}}$ or introduce new loss channels. The experiments in Sections 4 and 5 quantify these penalties and determine the operating envelope where $Q > 5{,}000$—the threshold below which SEM loses its competitive advantage.

### 2.4 Experimental Approach

All seven experiments are implemented in the simulation module `simulations/rewritability.py`, tested by 68 automated tests in `tests/test_rewritability.py`, and reproducible via:

```python
from simulations.rewritability import run_all_rewritability
results = run_all_rewritability(verbose=True)
```

Each experiment produces a result dataclass with a boolean `verdict` field indicating whether the hypothesis is confirmed, along with all intermediate quantities needed to reproduce and extend the analysis. The experiments build on the existing simulation infrastructure (34 modules, 1,036 tests from the companion paper) and import directly from the Hopfield recall, interference, and Q-model modules.

---
