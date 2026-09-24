# FT-3P: Coherent Path-Sum Interference Test

**Status:** OPEN / fast-track sub-experiment  
**Parent:** PR #16 — K_eff versus readout complexity  
**Reference:** Wen et al., *Direct experimental test of Feynman's path integral postulates with single photons*, Science Advances 12, eaeh1011 (2026), DOI: 10.1126/sciadv.aeh1011.

## 1. Why this belongs in the K_eff fast track

The path-integral paper reconstructs more than 1.4 million possible photon paths and verifies that the observable quantum result comes from the coherent sum of their complex probability amplitudes.

CWM must **not** claim that its room-temperature glass/PZT apparatus performs a quantum Feynman path integral.

The useful architectural analogy is classical:

```
input
  -> many allowed elastic propagation routes / modes
  -> coherent complex superposition
  -> small physical readout
```

For a driven elastic system, a useful representation is:

```
Y(omega) = H(omega) X(omega)
```

with the measured transfer function understood as the aggregate of many modal/path contributions.

This matters directly to PR #16 because K_eff asks how much independently useful structure survives that enormous internal wavefield into a fixed-size receiver interface.

The fast-track question becomes:

> Can deliberately controlled elastic paths interfere so that one fixed RX measurement computes a useful output that is not present in any single path alone?

If yes, this is a concrete physical mechanism by which internal path multiplicity could create useful work per propagation.

## 2. Claim boundary

Allowed claim if successful:

> A classical elastic wave network performs coherent path summation: separately characterized path responses predict the simultaneous response as a complex amplitude sum, and useful output classes can be produced by constructive/destructive interference.

Do **not** claim:

- quantum superposition;
- single-phonon behavior;
- a Feynman path integral;
- equal-amplitude path postulates;
- phase equal to classical action divided by hbar.

The experiment is a classical-wave analogue of the **sum-over-paths computation pattern**, not a quantum-foundations experiment.

## 3. Smallest physical setup

Use two independently phase-controlled TX PZTs coupled to the **same** fixed plate and one fixed RX PZT.

```
                       phase-controlled source A
                              |
                           TX-A PZT
                              \
                               \
                                v
                     +-------------------+
                     |                   |
                     |    GLASS PLATE    |
                     |        H          |----> RX PZT -> preamp -> Ch A
                     |                   |
                     +-------------------+
                                ^
                               /
                              /
                           TX-B PZT
                              |
                       phase-controlled source B
```

Requirements:

- TX-A and TX-B must have independent phase control at the same carrier frequency.
- RX position and fixture remain fixed.
- Same acquisition window/sample rate/sample count for all conditions.
- Record the commanded phase of each source.
- Record electrical references for both sources if hardware permits; otherwise measure/qualify source phase in a loopback calibration immediately before/after the run.

The existing multi-channel NCO work can be reused if it provides deterministic relative phase. If not, use one coherent multi-channel source or a dual-channel arbitrary-waveform source.

## 4. FT-3P-A — prove coherent complex summation

Choose one stable carrier frequency f where both TX-A -> RX and TX-B -> RX paths have adequate SNR.

Measure separately:

```
Y_A = H_A X_A
Y_B = H_B X_B
```

using complex demodulation / lock-in amplitude at f.

Then drive both simultaneously with relative phase phi:

```
X_A = A exp(i 0)
X_B = A exp(i phi)
```

Prediction from individual path characterization:

```
Y_pred(phi) = Y_A + exp(i phi) Y_B
```

Measure:

```
Y_meas(phi)
```

for a phase sweep, initially:

```
phi = 0, 22.5, 45, ..., 337.5 degrees
```

with >=20 repeats/phase.

Primary metrics:

- complex normalized RMSE between Y_meas and Y_pred;
- phase error;
- magnitude error;
- constructive-interference gain;
- destructive-interference depth;
- repeatability across a second session.

Advance if a frozen individual-path model predicts the simultaneous phase sweep within preregistered tolerance materially better than an incoherent power-addition model.

This is the core evidence that the **physical medium is summing complex path amplitudes**.

## 5. FT-3P-B — answer exists only in interference

After FT-3P-A succeeds, use a deliberately simple two-bit phase code.

Encode:

```
bit 0 -> phase 0
bit 1 -> phase pi
```

for each TX.

The four input states are:

```
00 : (+,+)
01 : (+,-)
10 : (-,+)
11 : (-,-)
```

Each individual TX has constant amplitude for all four states. Therefore a magnitude-only measurement of TX-A alone or TX-B alone contains no information about whether the two bits are equal.

The combined plate response is:

```
Y = s_A H_A + s_B H_B
```

where s_A,s_B are +1 or -1.

If H_A and H_B are selected/truncated so their relevant components interfere strongly, a scalar magnitude can separate:

```
same phase:     00 / 11
opposite phase: 01 / 10
```

This implements a physical parity-equivalence / XNOR-like decision.

The desired property is:

> The answer is a property of the **relationship between paths**, not the magnitude carried by either individual path.

### Controls

Evaluate the same frozen decision on:

1. TX-A alone;
2. TX-B alone;
3. electrical source references only;
4. ELECTRICAL_ONLY path state;
5. GLASS combined response.

A meaningful physical-interference result requires:

- individual-path magnitude accuracy near chance for the parity/equality target;
- GLASS combined-response accuracy >=95% held-session balanced accuracy;
- electrical-only control not explaining the same separation;
- thresholds frozen before the held session.

The source phases themselves trivially encode the two bits, so this is **not** a claim that electronics cannot compute parity. It tests whether the medium performs the relational sum before the receiver.

## 6. FT-3P-C — grow controlled path count

Only after the two-path test is clean.

Extend to 3 and 4 independently driven spatial TX paths into the same H:

```
Y = sum_j H_j X_j
```

Hold fixed:

- one RX PZT;
- one capture;
- sample rate;
- sample count;
- acquisition window.

For P = 1,2,3,4 controlled paths measure:

- number of phase-coded relations that remain held-session decodable;
- K_eff,task;
- K_eff,rank;
- ADC burden;
- receiver count;
- digital readout burden;
- coherent-model prediction error.

This becomes a direct companion to FT-3:

```
number of internal controlled paths
        vs
useful dimension at fixed RX cost
```

## 7. Relationship to the Science Advances paper

Wen et al. use a propagator-based method to reconstruct amplitudes for 17^5 = 1,419,857 possible single-photon paths and test Feynman's two quantum path-integral postulates.

The CWM experiment borrows only the structural idea:

```
many possible contributions
  -> complex coherent summation
  -> one observable result
```

The physical meanings differ:

| Science Advances experiment | CWM FT-3P |
|---|---|
| single-photon probability amplitudes | classical elastic complex amplitudes |
| quantum propagators | measured acoustic transfer paths |
| Feynman phase/action relation | ordinary propagation/modal phase |
| quantum probability | electrical measurement of RX vibration |
| tests quantum postulates | tests coherent physical path summation |

This distinction must remain explicit in papers, grant material, and repo documentation.

## 8. Why this could matter for H design

If FT-3P works, future H does not need to be viewed only as a bank of resonant frequencies.

It can be designed as a **propagation graph**.

A microfabricated structure could deliberately include:

- branches;
- reflectors;
- delay paths;
- coupled resonators;
- scattering junctions;
- phononic bandgap boundaries;
- phase-shifting sections.

The design goal becomes:

> Arrange path amplitudes and phases so desired output classes constructively interfere and undesired classes cancel.

That is a more specific engineering target than "maximize mode count."

## 9. Data format

Create:

```
data/results/path_sum/<session_id>/
    manifest.json
    trials.csv
    raw/
    derived/
        individual_paths.json
        phase_sweep.json
        parity_result.json
```

Minimum trial fields:

```
trial_id
session_id
path_state
tx_a_enabled
tx_b_enabled
frequency_hz
tx_a_phase_rad
tx_b_phase_rad
tx_a_command_amp
tx_b_command_amp
rx_complex_real
rx_complex_imag
rx_magnitude
rx_phase_rad
valid
invalid_reason
```

Save raw Ch-A time series and all available source-reference channels.

## 10. Stop / advance rules

### Advance from FT-3P-A if

- individual-path complex responses predict simultaneous response;
- coherent model clearly outperforms incoherent power addition;
- phase sweep reproduces on a later session.

### Advance from FT-3P-B if

- a frozen scalar or very small readout classifies the relational target >=95% on a held session;
- neither individual path magnitude alone contains the answer;
- electrical-only controls do not explain the separation.

### Advance toward engineered path networks if

- increasing controlled path count raises held-out K_eff or relational task capacity while RX hardware/acquisition remains fixed.

### Stop/reframe if

- combined response is not predictable from coherent summation;
- phase drift destroys later-session operation;
- electrical feedthrough dominates;
- useful path count grows only with proportional readout growth.

## 11. Connection back to PR #16

FT-3 asks whether simultaneous **spectral queries** increase K_eff at fixed readout cost.

FT-3P asks whether simultaneous **spatial/path contributions** can do the same through coherent interference.

Together they test two distinct sources of physical parallelism:

```
frequency-space parallelism
+
path-space parallelism
```

The fast-track scaling thesis becomes stronger only if one or both produce useful held-session dimensions beyond what the electrical source/reference already makes trivially available.
