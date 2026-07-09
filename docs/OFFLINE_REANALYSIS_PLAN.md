# Offline Reanalysis Plan for Captured CWM Data

**Status:** Proposed protocol  
**Evidence level:** OPEN / analysis plan  
**Purpose:** Define useful no-bench analyses that can be run from already captured CWM data, especially the Pong recall/enrollment matrices and direct-wire census files.

This document is meant to be used from the lab computer or any machine that has the raw `data/results/` files. It does not require the CWM bench to be powered on unless a listed file is missing and must be recaptured.

## 1. Why this exists

The current strongest CWM claim is not broad denoising superiority. The defensible claim from the June 29 correction is narrower:

> CWM behaves as a content-addressable physical feature map that can complete partial queries and tolerate heavy mode / sensor dropout.

The goal of this plan is to stress-test that claim using existing saved data before spending more bench time or making stronger public claims.

## 2. Required local files

Check whether these files exist locally before running new hardware:

```text
data/results/pong/recall_enroll_20260629_120542.npz
data/results/pong/recall_analysis_120542.json
data/results/pong/recall_sweep_20260629_005907.json
data/results/pong/recall_soak_20260629_011327.csv
data/results/direct_wire_census/direct_wire_census_20260628_220731.json
```

Any `data/results/pong/recall_enroll_*.npz` file can be used as the primary source for offline recall analysis. The exact timestamp does not have to match if the file contains the expected arrays.

## 3. Existing scripts to start from

### `tools/recall_enroll_save.py`

Captures and saves the raw feature matrix for later offline analysis. This script requires the bench.

Expected saved arrays include:

- `X`: captured feature matrix;
- `L`: landing labels;
- `GI`: state index;
- `xs`, `ys`, `vx`, `vy`: state variables;
- `land`: landing lookup;
- `freqs`: mode frequencies;
- `driven`: driven-bin indices;
- `nw`, `naxes`, `repeats`, `navg`, `padh`: metadata.

### `tools/recall_analyze.py`

Runs offline analysis from a saved `recall_enroll_*.npz` matrix. It already covers:

- fair-dimensionality wire baseline;
- partial-query test with `vx,vy` hidden;
- mode-dropout test;
- leave-one-repeat-out evaluation.

Use this as the baseline reproduction command:

```bash
python3 tools/recall_analyze.py data/results/pong/recall_enroll_20260629_120542.npz
```

If using a newer or different file:

```bash
python3 tools/recall_analyze.py data/results/pong/recall_enroll_<timestamp>.npz
```

## 4. First objective: reproduce the June 29 correction

Before adding new analysis, reproduce the known correction table.

Expected qualitative result:

- redundant/equal-dimensional wire should beat glass under iid additive feature noise;
- glass should still beat wire on partial-query completion when velocity components are hidden;
- glass should retain high accuracy under heavy random mode dropout.

If the existing scripts cannot reproduce those three qualitative findings, stop and debug before adding any new claims.

## 5. Offline experiments to add

### Experiment A: Partial-query grid

**Question:** Is the partial-query advantage robust, or does it only appear for the specific `vx,vy` hidden case?

Run a grid of hidden variables:

```text
hide x
hide y
hide vx
hide vy
hide x + y
hide x + vx
hide x + vy
hide y + vx
hide y + vy
hide vx + vy
hide random 25/50/75% of state-axis windows
```

For each mask, compare:

- raw axis-only features;
- wire4;
- wire random-projection baseline;
- glass all features;
- glass modes only;
- glass top-k modes, if justified.

**Success criterion:** glass wins specifically when hidden variables are physically encoded in the modal response, not just because of feature count or decoder behavior.

**Failure interpretation:** if only one handpicked mask works, the claim should be narrowed to that mask and not generalized as content-addressable completion.

### Experiment B: Mode importance and structured dropout

**Question:** Does graceful degradation survive realistic mode loss, or only random individual-mode masking?

Test dropout by:

```text
random individual modes
strongest modes first
weakest modes first
frequency bands
contiguous frequency blocks
per-drive / per-plate group if metadata exists
high-SNR modes only
low-SNR modes only
collision vs non-collision groups if metadata exists
```

**Success criterion:** the model should degrade gracefully under plausible physical loss patterns, not only under random independent feature masking.

**Failure interpretation:** if losing one band or one drive group collapses performance, the array needs band diversity or redundant plate design before stronger claims.

### Experiment C: Small-readout stress test

**Question:** Does CWM require a large digital decoder, or does a small/simple readout recover the useful signal?

Compare:

```text
nearest centroid
kNN with k=1,3,5
ridge regression / logistic regression
linear SVM if available
tiny MLP only as an upper-bound, not a main claim
```

Keep splits identical across methods.

**Success criterion:** the core claim should survive with nearest-neighbor, nearest-centroid, or simple linear readout.

**Failure interpretation:** if only complex models work, frame the system as a sensor + software pipeline rather than physical compute-in-memory.

### Experiment D: Software-kernel baselines

**Question:** Is glass providing structure beyond generic high-dimensional expansion?

Compare CWM features against:

```text
random projection of raw state
random Fourier features
polynomial features
redundant replicated wire features with noise averaging
ESN-style synthetic reservoir, if available
```

Match feature count where possible.

**Success criterion:** CWM should win under at least one physically meaningful condition that a cheap software kernel does not already solve.

**Failure interpretation:** if software random features match or beat glass across all tests, CWM’s contribution is hardware/sensing only, not compute.

### Experiment E: Transition / dynamical-system replay

**Question:** Can the existing Pong dataset be treated as a dynamical-system reconstruction task?

Targets:

```text
current features -> landing
current features -> next y
current partial features -> landing distribution
current partial features -> intercept decision
```

Stressors:

```text
noise
hidden velocity
mode dropout
held-out positions
held-out velocity signs
held-out state blocks
```

**Success criterion:** CWM should improve future-state recall under partial observation.

**Failure interpretation:** if CWM only recalls a closed deck and fails held-out structure, call it associative lookup, not general dynamical reconstruction.

### Experiment F: Cross-validation abuse check

**Question:** Are the results dependent on easy splits?

Run:

```text
leave-one-repeat-out
leave-one-state-out neighborhood split
held-out x columns
held-out y rows
held-out velocity signs
blocked split by acquisition order if timestamps exist
random labels sanity check
feature shuffling sanity check
```

**Success criterion:** the result survives stricter splits appropriate to the claim.

**Failure interpretation:** if the result collapses except under leave-one-repeat-out, public framing should be limited to enrolled-card recall.

## 6. Proposed new scripts

Add these scripts if they do not already exist:

```text
tools/partial_query_grid.py
tools/recall_mode_ablation.py
tools/software_kernel_baselines.py
tools/pong_transition_replay.py
tools/recall_split_stress.py
```

Each script should:

- accept a `recall_enroll_*.npz` path;
- write a result JSON under `data/results/pong/offline_reanalysis/`;
- print a compact summary table;
- use fixed random seeds;
- include method names, split definitions, and masks in the output JSON.

## 7. Suggested result schema

Use a structure like:

```json
{
  "source_npz": "data/results/pong/recall_enroll_20260629_120542.npz",
  "script": "tools/partial_query_grid.py",
  "timestamp": "YYYYMMDD_HHMMSS",
  "split": "leave_one_repeat_out",
  "methods": ["wire4", "wire_rp", "glass_all", "glass_modes"],
  "conditions": [
    {
      "name": "hide_vx_vy",
      "mask": {"x": true, "y": true, "vx": false, "vy": false},
      "sigma": 1.0,
      "results": {
        "wire4": 47.0,
        "glass_all": 84.0
      }
    }
  ],
  "notes": []
}
```

## 8. Hardware not required

These can be done entirely offline from saved matrices:

```text
partial-query masks
feature/mode dropout
software-kernel baselines
readout-model comparisons
stricter train/test splits
transition replay from stored labels
random-label and feature-shuffle nulls
```

## 9. Hardware still required

Do not claim these from offline reanalysis alone:

```text
physical noise injection
drive attenuation or EMI robustness
physical RX-channel dropout
new cross-session recapture
physical write / erase / rebaseline cycle
feedthrough null on current topology
temperature drift beyond the existing soak
energy and latency measurement
MEMS-relevant transduction
optical readout validation
nonlinear cascade validation
```

The offline dropout test is a proxy for dead modes. It is not the same as physically unplugging or killing an RX path.

## 10. Decision rule after offline work

After the offline reanalysis, choose one of these paths:

### Continue to hardware

Only if CWM shows a robust advantage on partial-query completion or graceful degradation after fair software and direct-wire baselines.

### Narrow the claim

If CWM only wins for enrolled-card recall, frame it as:

> enrolled acoustic content-addressable recall under partial query.

### Pivot away from compute-in-memory

If software kernels and redundant wire baselines match or beat CWM under all fair tests, frame CWM as sensing / fingerprinting / PUF / education rather than compute-in-memory.

## 11. First lab-computer checklist

When back at the lab computer:

1. Confirm the required result files exist.
2. Run:

```bash
python3 tools/recall_analyze.py data/results/pong/recall_enroll_20260629_120542.npz
```

3. Save the printed output and generated JSON.
4. If reproduction passes, implement `tools/partial_query_grid.py` first.
5. Then implement `tools/recall_mode_ablation.py`.
6. Commit result JSONs separately from scripts.
7. Update the lab diary with both positive and negative outcomes.
8. Do not update `paper/CLAIMS_STATUS.md` until at least one offline result is reproduced from committed data.

## 12. Minimum useful outcome

The minimum useful offline result is a table answering:

```text
When a state variable is missing, does the acoustic kernel recover the correct future better than fair direct-wire and software-kernel baselines?
```

If yes, the next hardware session should physically test the same missing-variable/dead-sensor story.

If no, the next hardware session should not chase the neural dynamical-system benchmark until the feature-map advantage is better defined.
