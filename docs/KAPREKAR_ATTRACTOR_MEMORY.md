# Kaprekar Attractor Memory for CWM

**Status:** Proposed experiment roadmap  
**Evidence level:** OPEN / protocol  
**Purpose:** Use Kaprekar's constant (6174) as a compact, auditable benchmark for CWM associative recall, recursive state transitions, fixed-point detection, noisy-query correction, spectral pages, and hybrid working memory.

## 1. Why Kaprekar's routine is useful

For a four-digit decimal number containing at least two distinct digits:

1. Sort its digits descending.
2. Sort its digits ascending.
3. Subtract the smaller number from the larger.
4. Repeat.

Most valid starting states converge to the fixed point 6174, while four-equal-digit states collapse to 0000.

Example:

```text
3524
5432 - 2345 = 3087
8730 - 0378 = 8352
8532 - 2358 = 6174
7641 - 1467 = 6174
```

The important feature is not the number 6174 itself. The useful abstraction is:

```text
many initial states
  -> repeated deterministic transformation
  -> stable attractor
```

That makes the routine a small finite-state dynamical system with a known transition graph, short trajectories, exact expected outputs, and a clear fixed point.

## 2. CWM-relevant framing

The immediate proposal is not that the current acoustic bench physically sorts decimal digits and performs subtraction by itself.

The realistic near-term architecture is hybrid:

```text
small digital controller:
  encodes state, performs control flow, optionally computes or validates transition

CWM:
  stores or recalls state cards / transition cards / attractor classes

small RAM:
  holds current state, iteration count, confidence, and error flags
```

This is analogous to a cartridge architecture:

```text
CWM ROM:
  fixed transition or state library

RAM/register:
  current iterative state

controller:
  queries memory and feeds the recalled output back as the next input
```

The main research question is:

> Can CWM act as a physical associative transition memory that recursively traverses a known state graph toward a stable attractor, including under partial, noisy, or degraded queries?

## 3. What this benchmark can test

Kaprekar provides one testbed for several existing CWM research directions:

- content-addressable recall;
- partial-query completion;
- recursive state evolution;
- trajectory recall;
- fixed-point detection;
- error accumulation across repeated queries;
- self-correction through attractor convergence;
- mode-dropout tolerance;
- spectral page addressing;
- hybrid working-memory semantics;
- ROM plus writable-state architecture.

## 4. State graph

Represent every four-digit string from `0000` through `9999`, preserving leading zeros.

Define the transition function:

```text
K(s) = descending_digits(s) - ascending_digits(s)
```

Each state has exactly one outgoing edge.

Generate metadata for every state:

```text
current_state
next_state
terminal_state
steps_to_terminal
valid_6174_basin
trajectory
permutation_class
repeated_digit_class
```

This produces a complete ground-truth graph for validation.

## 5. Proposed experiment ladder

### Level 0: Software ground truth

Create the complete transition table and verify:

- all valid starting states;
- fixed points;
- convergence steps;
- maximum trajectory length;
- handling of leading zeros;
- four-equal-digit collapse to zero.

No physical claim is made at this level.

### Level 1: State recognition

Encode a four-digit state into the existing CWM input scheme and ask the readout to identify the current state or its permutation class.

Questions:

- Can the system distinguish nearby states?
- Does it generalize across repeats/sessions?
- What happens when one digit or feature block is missing?

### Level 2: One-step transition recall

Query with current state `s`; retrieve `K(s)`.

Possible implementations:

1. direct card lookup;
2. nearest transition-card recall;
3. class-based lookup using permutation equivalence;
4. spectral-page lookup where one page identifies state and another returns next state.

Primary metric:

```text
one-step exact transition accuracy
```

Secondary metrics:

```text
digit-wise accuracy
numeric distance from correct next state
confidence margin
incorrect-attractor risk
```

### Level 3: Recursive convergence

Feed the recalled next state back into the system repeatedly:

```text
s0 -> s1 -> s2 -> ... -> 6174
```

Measure:

- percentage of valid starting states reaching 6174;
- exact trajectory accuracy;
- mean number of incorrect intermediate transitions;
- final-attractor accuracy;
- extra iterations caused by errors;
- oscillation or wrong-cycle rate.

This tests recursive error accumulation, not just isolated classification.

### Level 4: Noisy and partial-query convergence

Inject corruption at each iteration:

```text
missing digit
incorrect digit
missing feature block
Gaussian feature noise
mode dropout
frequency-band dropout
readout-channel dropout proxy
```

Questions:

- Does the recalled trajectory still reach the correct attractor?
- Can a wrong intermediate state re-enter the correct basin?
- Does CWM provide more graceful degradation than software/direct-wire baselines?

### Level 5: Frequency-addressed operations

Use spectral pages as operation addresses:

```text
Page 1: recognize current state
Page 2: retrieve next state
Page 3: identify final attractor
Page 4: classify steps remaining
Page 5: fixed-point / error state detection
```

This tests:

```text
frequency/tone/page = operation address
state pattern = query
CWM response = stored result
```

### Level 6: Working-memory emulator

Implement explicit memory semantics:

```text
ADDRESS
READ
MODIFY / TRANSITION
WRITE-BACK TO CURRENT-STATE REGISTER
READ AGAIN
HALT AT FIXED POINT
```

The first implementation may use virtual writing or electronic state for the current register. A later version can test physical rewrite.

### Level 7: Physical attractor path

Long-term only: introduce feedback, thresholding, state-dependent excitation, or physical rewritability so the resonator/controller loop autonomously settles into a stable physical state.

Do not claim this from a linear kernel demonstration alone.

## 6. Required baselines

Every CWM result should be compared with:

1. exact dictionary lookup;
2. software nearest-neighbor lookup;
3. raw input plus linear readout;
4. direct-wire features plus same readout;
5. software random projection/kernel plus same readout;
6. CWM features plus same readout.

The benchmark is only scientifically useful if CWM contributes something beyond an unnecessarily complicated lookup table.

Potential meaningful advantages:

- better partial-query completion;
- graceful degradation under missing features;
- lower physical readout cost in a future implementation;
- compact frequency-addressed transition pages;
- robust basin recovery after noisy intermediate states.

## 7. Encoding options

### Option A: Digit channels

Encode each digit as one tone/amplitude channel.

```text
D1, D2, D3, D4
```

Advantages:

- transparent;
- easy to mask individual digits;
- directly supports partial-query experiments.

### Option B: One-hot digit blocks

Use ten channels per position.

Advantages:

- clear categorical encoding;
- easy error analysis.

Disadvantages:

- 40 input dimensions;
- may exceed current clean-input capacity without multiplexing.

### Option C: Compact binary/state embedding

Encode state as a compact vector or learned embedding before querying CWM.

Advantages:

- lower input dimension;
- easier compatibility with existing tools.

Disadvantages:

- weakens the claim that the physical substrate directly stores the symbolic structure.

### Option D: Permutation-class encoding

Since the Kaprekar step depends on the digit multiset rather than original order, store permutation classes rather than all 10,000 ordered strings.

Advantages:

- dramatically reduces card count;
- tests whether CWM can exploit structured equivalence classes.

This is likely the best first physical experiment.

## 8. Proposed scripts

```text
tools/kaprekar_graph.py
tools/kaprekar_encode.py
tools/kaprekar_recall_benchmark.py
tools/kaprekar_recursive_recall.py
tools/kaprekar_spectral_pages.py
```

### `tools/kaprekar_graph.py`

Responsibilities:

- generate the full transition graph;
- preserve leading zeros;
- identify terminal states and steps;
- export JSON/CSV fixtures;
- include automated correctness tests.

### `tools/kaprekar_recall_benchmark.py`

Responsibilities:

- load stored/CWM features;
- compare one-step transition recall across baselines;
- evaluate exact and digit-wise metrics;
- write result JSON.

### `tools/kaprekar_recursive_recall.py`

Responsibilities:

- recursively feed recalled outputs back as queries;
- inject configured noise/dropout per iteration;
- measure final-attractor and trajectory success;
- save individual traces for debugging.

## 9. Suggested data layout

```text
data/generated/kaprekar/transition_table.json
data/generated/kaprekar/transition_table.csv
data/results/kaprekar/<timestamp>/one_step_results.json
data/results/kaprekar/<timestamp>/recursive_results.json
data/results/kaprekar/<timestamp>/traces.csv
```

## 10. Suggested result schema

```json
{
  "experiment": "kaprekar_recursive_recall",
  "source": "transition_table.json",
  "method": "cwm_glass_all",
  "split": "leave_one_repeat_out",
  "noise": {
    "sigma": 1.0,
    "digit_mask_probability": 0.25,
    "mode_dropout": 0.5
  },
  "metrics": {
    "one_step_exact_accuracy": 0.91,
    "full_trajectory_exact_accuracy": 0.72,
    "final_6174_rate": 0.94,
    "wrong_cycle_rate": 0.01,
    "mean_extra_steps": 0.8
  }
}
```

## 11. Strong success definition

A strong result would show:

- exact ground-truth transition graph;
- reproducible one-step recall;
- recursive traversal to 6174;
- final-attractor success remains high under partial/noisy queries;
- fair software, direct-wire, and random-kernel baselines;
- simple readout;
- saved traces and result files;
- no hidden digital correction that trivially forces the correct trajectory.

The most interesting positive finding would be:

> CWM has lower one-step accuracy than exact lookup but higher attractor recovery under degraded queries because its associative recall maps corrupted states back into the correct basin.

That would demonstrate error-correcting convergence rather than ordinary table lookup.

## 12. Falsifiers and kill criteria

Stop or narrow the work if:

1. CWM fails to beat simple software nearest-neighbor under any partial/noisy condition.
2. Recursive accuracy collapses after only one or two steps.
3. Digital correction, not CWM, is responsible for convergence.
4. The exact lookup baseline is so cheap that no physical advantage is plausible.
5. Spectral pages cannot isolate operations or state subsets.
6. Results only work on enrolled repeats and fail held-out state classes.
7. The benchmark becomes a symbolic-computation claim unsupported by the physical operation.

If these occur, retain Kaprekar only as an educational/demo workload.

## 13. Relationship to current CWM claims

This protocol does not establish autonomous nonlinear attractor dynamics in glass.

It tests whether current or future CWM can serve as:

```text
physical associative ROM
transition-card memory
frequency-addressed microcode store
hybrid phononic working memory
```

The controller may still perform sequencing and state-register updates.

Do not claim that the resonator independently sorts digits or subtracts numbers unless a future physical implementation actually performs those operations.

## 14. Immediate next steps

1. Implement and test `tools/kaprekar_graph.py`.
2. Determine the number of unique permutation classes and transition cards.
3. Build a software-only recursive recall baseline with controlled error injection.
4. Test whether attractor convergence corrects intermediate errors.
5. Map the reduced state/card set onto existing CWM feature capacity.
6. Run offline CWM replay if suitable raw matrices are available.
7. Only then design a dedicated physical encoding/bench capture.
8. Consider spectral-page separation for state recognition, transition recall, and fixed-point detection.

## 15. Recommended framing

Careful framing:

> Kaprekar's routine provides a deterministic attractor-memory benchmark for testing whether CWM can recall and recursively traverse stored state transitions under partial and noisy queries.

Avoid:

- claiming 6174 is a special physical constant;
- claiming CWM performs arbitrary arithmetic;
- claiming autonomous attractor dynamics from a controller-assisted loop;
- presenting digital sequencing as acoustic computation;
- equating a successful demo with general-purpose computing.

## 16. Summary

Kaprekar's constant is useful to CWM because it supplies a complete, compact, exact state-transition problem with a stable attractor.

The near-term CWM opportunity is:

```text
query state
  -> associative transition recall
  -> feedback as next query
  -> repeated traversal
  -> stable attractor
```

If the system remains convergent under missing or corrupted queries, it would connect CWM's existing partial-query recall work to a clearer recursive-memory and working-memory demonstration.