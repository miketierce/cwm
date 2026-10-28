# Spectral Page Multiplexing for CWM

**Status:** Proposed roadmap and experiment protocol  
**Evidence level:** OPEN / architecture + protocol  
**Purpose:** Translate wavelength-multiplexed diffractive optical storage into a CWM-native acoustic/phononic next step: frequency-addressed passive wave recall.

This document is motivated by recent work on wavelength-multiplexed diffractive optical storage, where a fixed passive optical structure is optimized so different illumination wavelengths reconstruct different stored output patterns. The CWM-relevant abstraction is not optical storage itself. The relevant abstraction is:

```text
fixed physical wave object
+ wavelength/frequency-addressed query
+ many stored outputs/pages
+ passive parallel wave propagation
+ learned/optimized geometry
```

For CWM, the corresponding architecture is:

```text
fixed or writable acoustic/phononic structure
+ acoustic frequency/tone/phase-addressed query
+ many stored spectral pages
+ passive modal/interference response
+ learned/optimized perturbation geometry
```

This is a better fit for CWM than trying to imitate phase-change memristor crossbars directly. Memristors store electrical conductance weights. CWM's native strengths are acoustic modes, spectral identity, interference, and physical fingerprints. Spectral page multiplexing asks whether those native strengths can be organized into a memory architecture.

---

## 1. Core idea

A CWM plate or array should not be treated only as:

```text
one plate = one fuzzy fingerprint
```

Instead, test whether it can become:

```text
one acoustic object = many frequency-addressed memory pages
```

A **spectral page** is a frequency band, tone bundle, or phase/frequency query configuration that selects one stored mapping from the same physical object.

Examples:

```text
Page A: 40-60 kHz band -> Pong landing recall
Page B: 60-80 kHz band -> heading recall
Page C: 80-100 kHz band -> identity/key recall
Page D: multi-tone phase pattern -> cancellation/comparator response
```

The key claim to test is:

> Changing the acoustic query frequency/tone set selects a different stored page with low cross-talk between pages.

---

## 2. Why this matters for CWM

CWM's current evidence base is strongest around:

- acoustic modal fingerprints;
- high-dimensional physical kernels;
- content-addressable recall;
- partial-query completion;
- mode-dropout tolerance;
- phase/interference primitives;
- write / rewritability paths;
- array-design work around band diversity and collisions.

Spectral page multiplexing connects those into a clearer memory story:

```text
write once / configure once:
  set the structure, perturbation pattern, plate geometry, PZT placement, or virtual page projection

read many:
  query by frequency, tone bundle, phase pattern, or band

output:
  stored card, mapping, class, trajectory, or nearest state
```

This may be more CWM-native than a memristor-style story because it does not require each cell to behave like an electrical conductance weight. It requires the acoustic object to behave like a passive frequency-addressed wave memory.

---

## 3. Relationship to previous CWM directions

### 3.1 Difference from generic feature extraction

Generic CWM feature extraction:

```text
input -> plate -> FFT feature vector -> digital decoder
```

Spectral page multiplexing:

```text
address frequency/page -> plate -> page-specific output response
```

The second is closer to memory because the query frequency/tone is an address, not just a measured feature.

### 3.2 Difference from memristor compute-in-memory

Memristor CIM:

```text
physical state = conductance
query = voltage/current
operation = weighted electrical response
array = dense crossbar
```

CWM spectral page memory:

```text
physical state = modal geometry / perturbation / boundary / spectral response
query = acoustic frequency/tone/phase
operation = modal filtering / interference / recall
array = resonator, plate bank, or phononic structure
```

The comparison point is not identical device physics. The comparison point is whether physical state participates in the readout enough to reduce digital lookup or software-only computation.

### 3.3 Relationship to existing CWM write/rewritability

CWM page state could be implemented by several write/configure mechanisms:

1. **Fixed geometry / write-once perturbation**  
   Page structure is fabricated or manually set and then read many times.

2. **Physical perturbation write**  
   Mass/stiffness/boundary changes shift page responses.

3. **Virtual writing / firmware-defined pages**  
   The physical object is unchanged, but excitation and readout masks select different logical pages.

4. **MEMS future path**  
   Binary perturbation sites, writable shells, defect modes, or tunable phononic cells implement page states.

The initial test can use virtual pages and existing data. The stronger claim requires physical or MEMS-relevant page state.

---

## 4. Definitions

### Spectral page

A subset of the CWM response addressed by one of:

- frequency band;
- drive tone;
- tone bundle;
- relative phase pattern;
- plate identity;
- TX/RX geometry;
- readout projection mask.

### Page fidelity

Accuracy or reconstruction quality when the correct page is queried.

### Page cross-talk

Incorrect activation or recall of a non-addressed page.

### Page capacity

Number of pages that can be addressed with acceptable fidelity and cross-talk.

### Page bandwidth

Frequency range required to support one page.

### Page isolation

Degree to which page features are independent of neighboring page features.

---

## 5. First offline experiment: spectral page capacity from existing data

**Goal:** Determine whether existing captured CWM data already contains frequency-addressable pages.

**Input data:** preferred files on the lab computer:

```text
data/results/pong/recall_enroll_20260629_120542.npz
data/results/pong/recall_analysis_120542.json
data/results/pong/recall_sweep_20260629_005907.json
data/results/direct_wire_census/direct_wire_census_20260628_220731.json
```

Any `recall_enroll_*.npz` with frequency metadata can be used.

### Method

1. Load the saved feature matrix `X`, labels, state variables, and mode frequencies.
2. Separate axis/driven windows from modal features.
3. Partition modal features into frequency bands:
   - equal-width bands;
   - equal-feature-count bands;
   - natural clusters/gaps;
   - collision-aware bands, if metadata exists.
4. Treat each band as a candidate page.
5. For each candidate page, train/evaluate simple readouts on one target mapping.
6. Measure cross-talk by applying the page readout to other page features or mismatched labels.
7. Repeat with partial queries and mode dropout.

### Candidate page assignments

Start simple:

```text
Page 1: landing recall
Page 2: x/y state recall
Page 3: velocity sign recall
Page 4: heading / trajectory class
```

Alternative: one target, many pages:

```text
Band A -> landing recall
Band B -> landing recall
Band C -> landing recall
```

This estimates how many independent pages exist before trying different tasks per page.

### Metrics

- page accuracy;
- page cross-talk matrix;
- number of usable pages;
- accuracy vs. number of bands;
- feature count per page;
- stability under feature dropout;
- partial-query completion per page;
- frequency separation vs. page isolation.

### Success criterion

At least 3 frequency bands/pages should independently recover useful target information above raw/direct-wire baselines, with measurable cross-talk below a predeclared threshold.

Suggested initial threshold:

```text
page fidelity >= 70% on Pong-style recall task
cross-talk <= 30% relative activation into non-addressed page
```

These thresholds are placeholders and should be adjusted after reproduction of the June 29 baseline.

### Failure interpretation

If all useful information is spread globally and no band/page works independently, spectral page multiplexing is not supported by existing data. CWM may still be a global physical kernel, but not a page-addressed memory.

---

## 6. First hardware experiment: 3-6 acoustic pages

**Goal:** Show that different acoustic queries select different mappings from the same physical object/array.

### Minimal setup

- one verified plate or existing array;
- same RX path;
- same FFT/readout pipeline;
- 3-6 selected drive frequencies or tone bundles;
- one page target per frequency/band.

### Candidate page design

```text
Page A: low band -> landing class
Page B: mid band -> velocity sign
Page C: high band -> x/y position class
```

or, more conservatively:

```text
Page A/B/C: same target mapping, different independent frequency pages
```

The second version tests page capacity before task diversity.

### Procedure

1. Select page frequencies/bands from direct-wire census or prior high-SNR modes.
2. For each page, enroll repeated captures for all states.
3. Train a simple page-specific readout.
4. Query each page with the correct frequency/tone set.
5. Query mismatched pages to estimate cross-talk.
6. Repeat after re-power/re-baseline if possible.

### Required baselines

- raw axis/driven features;
- direct-wire features;
- full-bank CWM features;
- random frequency-band partitions;
- software random projection with matched feature count.

### Success criterion

CWM should show address-dependent recall:

```text
correct page query -> high fidelity
wrong page query -> lower fidelity / predictable cross-talk
```

If all pages behave identically, frequency is not functioning as an address.

---

## 7. Geometry / perturbation optimization path

The optical analogy uses optimized diffractive geometry. CWM should eventually move from discovering random modes to designing page structure.

Macro-scale options:

- adhesive dots;
- small brass/tape masses;
- foil patches;
- clamps or boundary changes;
- edge damping;
- PZT placement changes;
- mass-tuned slide cartridges;
- symmetry-broken patches.

MEMS-scale analogs:

- phononic crystal defects;
- localized acoustic cavities;
- tunable stiffness/mass sites;
- etched perturbation patterns;
- writable shell coatings;
- binary MEMS perturbation switches;
- surface acoustic wave / bulk acoustic wave structures.

### Optimization objective

Given target page mappings, optimize physical or virtual parameters to maximize:

```text
page fidelity - lambda * cross-talk - mu * loss/damping - nu * feature count overhead
```

Initial implementation can be software-only using captured matrices and simulated perturbation masks.

---

## 8. Proposed new scripts

### `tools/spectral_page_capacity.py`

Offline analysis from saved `recall_enroll_*.npz`.

Responsibilities:

- load modal features and frequency metadata;
- partition modes into candidate pages;
- evaluate per-page recall;
- compute page cross-talk matrix;
- write result JSON.

### `tools/spectral_page_bench.py`

Hardware enrollment/query tool for page-addressed experiments.

Responsibilities:

- select drive bands/tone bundles;
- enroll page-specific captures;
- save page dataset;
- run first-pass page readout;
- output page-fidelity and cross-talk report.

### `tools/spectral_page_optimize.py`

Optional optimizer for perturbation/page design.

Responsibilities:

- simulate or search page partitions;
- optimize band assignments;
- optionally use captured matrices to estimate which modes belong together;
- suggest frequencies/tone sets for the next bench run.

---

## 9. Suggested result schema

```json
{
  "script": "tools/spectral_page_capacity.py",
  "source_npz": "data/results/pong/recall_enroll_20260629_120542.npz",
  "timestamp": "YYYYMMDD_HHMMSS",
  "partition_method": "equal_feature_count",
  "n_pages": 4,
  "pages": [
    {
      "page_id": "P1",
      "freq_min_hz": 40000,
      "freq_max_hz": 65000,
      "n_features": 50,
      "target": "landing",
      "accuracy": 0.78
    }
  ],
  "cross_talk_matrix": [[1.0, 0.22], [0.18, 1.0]],
  "baselines": {
    "raw": 0.50,
    "wire4": 0.47,
    "software_random_kernel": 0.70,
    "full_bank": 0.84
  },
  "notes": []
}
```

---

## 10. Relationship to MEMS compute-in-memory

Spectral page multiplexing does not by itself prove compute-in-memory.

It does, however, define a CWM-native memory architecture:

```text
frequency address -> physical wave object -> stored response page
```

For MEMS, the unit-cell question becomes:

> Can a phononic structure store many frequency-addressed pages with low loss, stable addressing, and low-overhead readout?

This is more natural for CWM than asking whether an acoustic resonator can imitate a memristor conductance cell.

A possible MEMS path:

```text
phononic slab / beam / plate
+ engineered defect modes
+ tunable or written perturbations
+ acoustic/electrical bus
+ frequency-addressed page readout
```

Key MEMS gates:

- page isolation survives fabrication variation;
- page count scales with mode density;
- readout overhead does not erase benefit;
- writable/tunable perturbations do not kill Q;
- pages can be addressed without excessive calibration;
- crosstalk remains bounded as page count grows.

---

## 11. Kill criteria

Stop or reframe this path if:

1. Existing data shows no useful frequency-local pages.
2. Full-bank features work but every band/page alone fails.
3. Page cross-talk is too high to support addressing.
4. Software random features match or beat page-multiplexed CWM at equal feature count.
5. Hardware page selection is dominated by electrical feedthrough or drive amplitude artifacts.
6. Page capacity does not improve with band diversity or engineered perturbation.
7. MEMS projections require unrealistic Q, fabrication precision, or calibration.

If these occur, CWM should remain framed as a global acoustic feature map, not spectral memory.

---

## 12. Strong success definition

A strong first result would show:

- at least 3 independently addressable acoustic pages;
- page fidelity above direct-wire and raw baselines for a selected task;
- cross-talk matrix showing meaningful page isolation;
- stability across repeated captures;
- saved data and script reproduction;
- simple readout only;
- no update to public claims until reproduced.

A stronger second result would add:

- physical perturbation or virtual-write configuration changes page behavior;
- geometry/patch/tone optimization improves page isolation;
- cross-session repeatability;
- mode dropout and partial-query robustness within pages.

---

## 13. Immediate next actions

1. Add `tools/spectral_page_capacity.py` for offline analysis.
2. Run it on the saved Pong recall matrix if available locally.
3. Determine whether existing mode bands behave like independent pages.
4. If yes, design a 3-6 page bench test.
5. If no, test whether engineered perturbation or virtual masks can create page separation.
6. Only after measured success, update `paper/CLAIMS_STATUS.md` with a new OPEN/MEASURED entry.

---

## 14. Public framing if successful

Careful framing:

> CWM demonstrates frequency-addressed acoustic page recall: a fixed classical resonator/array can support multiple addressable spectral pages with measurable fidelity and cross-talk.

Avoid:

- optical-equivalent capacity claims;
- thousands of pages without measurement;
- quantum language;
- GPU/memristor-style speedup claims;
- compute-in-memory claims unless physical state, addressing, and low-overhead readout are demonstrated.

---

## 15. Summary

The optical wavelength-multiplexed storage result suggests an important CWM next step:

```text
frequency should become an address, not just a feature.
```

CWM should test whether one acoustic object can store many spectral pages and recall them by frequency/tone/phase query. If successful, this creates a clearer CWM-native memory path:

```text
frequency-addressed passive wave memory
```

That path uses CWM's existing strengths: modes, spectra, interference, physical fingerprints, and potential perturbation-based writing.
