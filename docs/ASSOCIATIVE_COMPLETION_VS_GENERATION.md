# Associative Completion Versus Generation in CWM

**Status:** Proposed thesis and experiment roadmap  
**Evidence level:** OPEN / interpretation + protocol  
**Purpose:** Distinguish CWM's measured partial-query completion from token generation, define where the two ideas overlap, and specify experiments that can determine whether CWM performs retrieval, interpolation, trajectory traversal, or any genuinely generative operation.

---

## 1. Central thesis

The current CWM result is best described as:

> Given a partial, noisy, or degraded query, the distributed acoustic feature map helps retrieve the associated enrolled state.

That is **associative completion**.

It is not yet evidence that CWM:

- generates novel states;
- predicts unconstrained future states;
- synthesizes outputs not represented in the enrollment set;
- implements next-token probability estimation;
- autonomously traverses a learned sequence;
- performs language-model-like inference.

The important scientific question is not whether associative completion and token generation are unrelated. They are related forms of inference from incomplete context. The question is:

> Does CWM only select among enrolled states, or can its distributed physical response support interpolation, transition recall, or iterative convergence beyond nearest-template lookup?

This document defines experiments to answer that question.

---

## 2. Wheel-of-Fortune analogy

A Wheel-of-Fortune puzzle such as:

```text
C _ M P U T _ R
```

can be solved by several mechanisms:

1. **Exact memory retrieval**  
   Recall the familiar word `COMPUTER` from prior experience.

2. **Associative pattern completion**  
   Use the visible letters and word shape to select the closest compatible stored word.

3. **Statistical generation**  
   Evaluate many possible completions according to learned language probabilities.

4. **Rule-based constraint solving**  
   Apply spelling, grammar, and puzzle constraints.

The current CWM evidence most closely resembles mechanism 2.

The physical system does not appear to invent arbitrary new symbols. It maps a degraded query into a high-dimensional distributed response from which the closest enrolled state can be recovered.

That may still be valuable. Associative completion is the core operation behind:

- content-addressable memory;
- error-correcting recall;
- nearest-state recognition;
- partial sensor reconstruction;
- degraded-signal identification;
- attractor-style convergence when combined with feedback.

---

## 3. Comparison with token generation

### 3.1 Autoregressive token generation

A language model estimates a distribution such as:

```text
P(next token | prior context)
```

The selected token may participate in a sequence never seen verbatim during training. The output is produced from a learned statistical model over many examples, not necessarily by retrieving one exact stored sentence.

### 3.2 Current CWM operation

The current CWM pipeline is closer to:

```text
partial physical query
  -> distributed modal response
  -> similarity/readout
  -> closest compatible enrolled state or label
```

The output domain is generally fixed by the enrollment set and decoder labels.

### 3.3 Overlap

Both systems can complete missing information.

Both can be framed as conditional inference:

```text
observed context -> inferred missing state
```

But the evidence requirements differ:

- Retrieval requires identifying a known state from partial evidence.
- Interpolation requires recovering a meaningful unseen state between enrolled states.
- Generation requires producing a valid output outside the enrolled state set.
- Sequence generation requires repeatedly producing valid transitions without collapsing under accumulated error.

---

## 4. A four-level capability ladder

### Level 1: Enrolled-state retrieval

```text
partial query -> one of the enrolled states
```

This is supported by current partial-query results, subject to physical bench validation.

### Level 2: Robust associative completion

```text
partial/noisy query -> correct enrolled state despite missing evidence
```

This is the strongest current framing. The saved-data analysis reports a large advantage over the simple wire baseline across all tested hidden-axis combinations and graceful degradation under simulated mode dropout.

### Level 3: Interpolation or structured inference

```text
query from an unseen but meaningful intermediate state
  -> decoded intermediate value or correct continuous estimate
```

This is not established.

### Level 4: Generative or recursive state evolution

```text
current state -> novel next state -> feed back -> valid sequence
```

This is not established. Existing Pong trajectory replay shows rapid multi-step degradation and therefore sets a difficult baseline for recursive generation claims.

---

## 5. Working hypotheses

### H1: Nearest-template hypothesis

CWM only improves the geometry of nearest-neighbor retrieval. It does not create information beyond the enrollment set.

Prediction:

- unseen intermediate queries collapse to the nearest enrolled template;
- decoded outputs are quantized to trained states;
- novel target reconstruction is poor;
- recursive feedback accumulates errors quickly.

### H2: Physical interpolation hypothesis

The distributed modal response varies smoothly enough that unseen intermediate states can be decoded accurately from neighboring enrolled states.

Prediction:

- held-out intermediate states are recovered as intermediate values;
- performance exceeds ordinary nearest-neighbor retrieval;
- simple linear readout is sufficient;
- interpolation survives cross-session testing.

### H3: Attractor-correction hypothesis

CWM does not generate novel states directly, but repeated associative recall can correct corrupted states and converge toward a stable enrolled attractor.

Prediction:

- intermediate transitions may contain errors;
- final-attractor success remains high;
- modest corruption can be corrected by repeated recall;
- performance is better measured by basin arrival than exact path fidelity.

### H4: Distributed transition-memory hypothesis

CWM can encode a useful mapping from a current state to a stored next state, allowing a controller to traverse a fixed state graph.

Prediction:

- one-step transitions are reliable;
- multi-step traversal is possible with periodic correction or digital state stabilization;
- outputs remain within the enrolled graph;
- no novel state synthesis is required.

### H5: Physical generative hypothesis

Superposition among modal responses produces meaningful outputs not explicitly enrolled.

Prediction:

- held-out outputs can be decoded without being present as templates;
- blended queries yield structured, reproducible novel states;
- results exceed software interpolation and random-kernel baselines;
- the effect survives strict controls and physical replication.

This is the strongest and least supported hypothesis.

---

## 6. Experiment A: Exact retrieval versus interpolation

**Question:** When queried between two enrolled states, does CWM retrieve one endpoint or represent the intermediate state?

### Dataset design

Create a one-dimensional ordered state variable with levels such as:

```text
0, 1, 2, 3, 4, 5, 6, 7
```

Enroll only alternating levels:

```text
0, 2, 4, 6
```

Hold out:

```text
1, 3, 5, 7
```

Alternative continuous targets:

- mass position;
- drive amplitude;
- phase offset;
- simulated object angle;
- Pong coordinate;
- vibration severity;
- ultrasonic range.

### Methods

Compare:

1. nearest enrolled state;
2. linear interpolation in raw input space;
3. direct-wire features + ridge regression;
4. software random projection + ridge regression;
5. CWM features + ridge regression;
6. CWM nearest-template recall.

### Metrics

- mean absolute error;
- RMSE;
- percentage of predictions equal to an endpoint;
- monotonicity;
- calibration curve;
- cross-session transfer.

### Interpretation

- Endpoint collapse supports retrieval only.
- Accurate intermediate estimates support physical interpolation.
- CWM must beat fair software and wire baselines to justify a physical advantage.

---

## 7. Experiment B: Novel combination test

**Question:** Can CWM infer a combination of attributes that was never enrolled?

### Factorial design

Use two independent variables:

```text
shape: A, B, C
position: 1, 2, 3
```

Enroll most combinations but hold out selected pairs:

```text
A1, A2, A3
B1, B2
C1, C3
```

Hold out:

```text
B3, C2
```

Equivalent CWM-native variables could be:

- x position and velocity sign;
- mass location and mass level;
- drive frequency and phase;
- obstacle class and range;
- vibration fault type and RPM.

### Test

Query the held-out combinations and decode both factors independently.

### Success criterion

CWM recovers both attributes for unseen combinations better than nearest-template and matched software baselines.

### Failure interpretation

If output maps to the closest enrolled combination, CWM is performing associative retrieval rather than compositional generation.

---

## 8. Experiment C: Wheel-of-Fortune completion benchmark

**Question:** Can CWM complete structured symbolic patterns from missing elements, and is that completion retrieval or generalization?

### Dataset

Start with a constrained symbol vocabulary, not natural language.

Examples:

```text
ABCD
ABCE
ABDE
ACDE
BCDE
```

Mask one or more positions:

```text
A_CE
_BDE
AC__
```

A later version could use:

- small word lists;
- command tokens;
- drone operating-state codes;
- error/status codes;
- fixed transition labels.

### Conditions

1. Test words present in enrollment.
2. Test valid words absent from enrollment but constructible from known subpatterns.
3. Test invalid/nonexistent patterns.

### Outcomes

- Correct known-word completion demonstrates associative memory.
- Correct unseen valid completion suggests compositional inference.
- Forced selection of a known word for every invalid pattern reveals nearest-template bias.

### Required baselines

- exact lookup;
- Hamming-distance nearest neighbor;
- n-gram or Markov model;
- software random features;
- direct-wire features;
- CWM features.

---

## 9. Experiment D: One-step transition memory

**Question:** Can CWM retrieve the next state in a fixed transition graph?

### Candidate graphs

- Kaprekar state transitions;
- simplified Pong trajectories;
- finite-state machine;
- drone fault-state progression;
- cyclic Gray-code sequence;
- cellular automaton neighborhoods.

### Architecture

```text
current state
  -> CWM query
  -> recalled next-state label
  -> digital register stores next state
```

The controller may perform addressing and feedback. CWM is tested as a physical transition ROM, not as an autonomous processor.

### Metrics

- one-step exact accuracy;
- tolerant state accuracy;
- transition confusion matrix;
- unseen-query behavior;
- noise and dropout robustness;
- readout complexity.

---

## 10. Experiment E: Recursive trajectory traversal

**Question:** Does repeated CWM-assisted transition recall remain on a valid trajectory?

### Procedure

1. Select a starting state.
2. Query CWM for the next state.
3. Feed the decoded state back as the next query.
4. Continue to a fixed point or maximum horizon.

### Metrics

- exact trajectory accuracy;
- valid-edge rate;
- final-attractor success;
- time to divergence;
- recovery after one injected error;
- state entropy over time;
- cycle/fixed-point frequency.

### Key distinction

For attractor systems, the strongest metric may be:

```text
Does the sequence eventually reach the correct basin/fixed point?
```

rather than:

```text
Was every intermediate transition exact?
```

This is especially important for the Kaprekar benchmark.

---

## 11. Experiment F: Blended-query response

**Question:** Does physical superposition create a meaningful blended or novel output?

### Procedure

1. Enroll states A and B.
2. Construct controlled mixtures of their query signals:

```text
q(alpha) = alpha * q_A + (1-alpha) * q_B
```

3. Sweep `alpha` from 0 to 1.
4. Measure the physical response and decoded output.

### Possible outcomes

- abrupt switch from A to B: categorical associative retrieval;
- smooth decoded transition: interpolation;
- unstable/unstructured output: no useful generative behavior;
- reproducible third-state response: possible emergent mixed state requiring further controls.

### Controls

- software linear mixture;
- random projection;
- direct-wire mixture;
- shuffled feature labels;
- repeated physical captures;
- cross-session replication.

---

## 12. Experiment G: Unknown-state and abstention test

A generative or associative system must distinguish between incomplete known states and truly unknown inputs.

### Test classes

1. degraded version of an enrolled state;
2. interpolation between enrolled states;
3. valid unseen state;
4. physically unrelated out-of-distribution query;
5. noise-only/null query.

### Metrics

- confidence/calibration;
- abstention accuracy;
- false-known rate;
- entropy or distance margin;
- unknown-state detection.

A system that maps every input to the nearest card is useful as CAM but should not be framed as generative inference.

---

## 13. Relationship to the latest offline results

The current evidence strongly supports distributed partial-query completion and simulated dropout tolerance.

It does not support:

- spectral page isolation on the current plate;
- fine-grained 256-slot working memory under noise;
- reservoir-computing advantage;
- long-horizon Pong trajectory generation;
- raw-classification superiority over dimensionality-matched software expansion.

Therefore the immediate testing priority should be:

1. verify partial-query completion physically;
2. test interpolation using held-out continuous states;
3. test one-step transition recall;
4. test final-attractor convergence;
5. only then investigate novel-state generation.

---

## 14. Recommended first implementation

### Phase 1: Offline interpolation replay

Use existing Pong or multitone data if intermediate state levels are available.

Hold out alternating state levels and compare continuous reconstruction across:

```text
raw/direct-wire
software random projection
CWM modal features
nearest-template recall
```

### Phase 2: Controlled bench interpolation

Capture a simple continuous physical variable:

```text
mass position across a rod/plate
or
drive amplitude/phase sweep
```

Enroll sparse levels and test held-out intermediate levels.

### Phase 3: Transition ROM

Use a small deterministic graph with 8–32 states. Avoid thousands of fine-grained addresses on the current plate.

### Phase 4: Recursive attractor test

Use Kaprekar permutation classes, a compact finite-state attractor, or another graph with known basins.

### Phase 5: Blended-query experiment

Only after interpolation and transition behavior are understood.

---

## 15. Suggested scripts

```text
tools/interpolation_holdout_test.py
tools/compositional_holdout_test.py
tools/symbol_completion_benchmark.py
tools/transition_memory_benchmark.py
tools/recursive_attractor_replay.py
tools/blended_query_sweep.py
tools/unknown_state_abstention.py
```

Each script should:

- accept saved NPZ/JSON data;
- use fixed random seeds;
- preserve explicit repeat/session IDs;
- compare identical splits across methods;
- save machine-readable result JSON;
- report both exact and tolerant metrics;
- include leakage and shuffled-label controls.

---

## 16. Suggested result schema

```json
{
  "experiment": "interpolation_holdout",
  "source": "data/results/.../capture.npz",
  "held_out_states": [1, 3, 5, 7],
  "methods": {
    "nearest_template": {
      "mae": 0.8,
      "endpoint_collapse_rate": 0.91
    },
    "wire_ridge": {
      "mae": 0.4
    },
    "software_random_kernel": {
      "mae": 0.3
    },
    "cwm_ridge": {
      "mae": 0.25
    }
  },
  "split": "leave_one_repeat_out",
  "notes": []
}
```

---

## 17. Claim language by outcome

### If retrieval only is supported

> CWM provides distributed physical associative completion of enrolled states under partial or degraded queries.

### If interpolation is supported

> CWM's distributed modal response supports reconstruction of held-out intermediate states using a simple readout.

### If transition recall is supported

> CWM acts as a physical associative transition memory for a fixed state graph.

### If attractor convergence is supported

> Repeated CWM-assisted associative recall can recover a stable enrolled attractor from corrupted intermediate states.

### If novel-state synthesis is supported

Use stronger language only after strict controls:

> CWM produces reproducible structured responses corresponding to valid states absent from the enrollment set.

Do not call this token generation unless the system is actually trained and evaluated as a conditional sequence model.

---

## 18. Falsifiers and kill criteria

Reframe or stop the generative thesis if:

1. held-out states always collapse to nearest enrolled templates;
2. software linear/random kernels match or beat CWM on interpolation;
3. apparent novel states disappear under strict session splits;
4. blended-query responses are explained by linear electrical feedthrough;
5. recursive trajectories diverge faster than trivial software baselines;
6. final-attractor success is no better than ordinary nearest-neighbor lookup;
7. unknown inputs are confidently misclassified as enrolled states;
8. complex digital decoders are required to create the apparent generative effect.

A negative result remains useful: it would establish CWM as robust CAM rather than a generative substrate.

---

## 19. Strategic implication

Associative completion is not a lesser result merely because it is not token generation.

For embedded physical systems, robust completion can be the valuable operation:

```text
missing sensor channels
partial vibration signature
incomplete ultrasonic echo
degraded landmark embedding
damaged modal readout
```

CWM may be most useful where the desired output is a known physical state that must be recovered despite incomplete evidence.

The generative question should be tested because it defines the ceiling of the architecture, not because CWM needs to imitate a language model to be valuable.

---

## 20. Bottom line

The current thesis is:

> CWM presently behaves like a distributed physical Wheel-of-Fortune solver for enrolled physical states: incomplete evidence can be completed into a compatible known state.

The next scientific question is:

> Can that physical completion generalize to unseen intermediate states, compositional combinations, fixed transition graphs, or attractor convergence?

The experiment ladder in this document separates those capabilities cleanly and prevents associative retrieval from being mislabeled as generation.
