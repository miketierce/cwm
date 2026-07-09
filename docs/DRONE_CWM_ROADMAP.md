# Drone CWM Roadmap

**Status:** Proposed roadmap and experiment protocol  
**Evidence level:** OPEN / architecture + protocol  
**Purpose:** Define a realistic path for testing whether CWM/phononic memory can improve drone sensing, stability recognition, obstacle-signature matching, or low-power physical recall.

This document does not claim that CWM can replace a flight controller, SLAM system, camera stack, GPS, IMU fusion, or motor-control loop. It frames CWM as a possible **physical recall coprocessor** or **phononic sensor-memory front end** for specific enrolled states.

The central question is:

> Can a CWM or MEMS-phononic device recognize useful drone-relevant physical states with less power, weight, latency, or sensor burden than a conventional microcontroller/DSP baseline?

---

## 1. Game cartridge analogy: CWM as fixed template memory plus small writable state

A classic cartridge system is a useful analogy, but only if the parts are separated correctly.

```text
ROM:
  fixed game code, maps, sprites, text, rules

SRAM / EEPROM / Flash:
  writable save progress

battery:
  keeps SRAM alive on older cartridges

mapper / memory-bank controller:
  selects which ROM bank is visible to the console
```

A GameBoy game generally did not save progress by rewriting the ROM. The ROM stored fixed content. Save progress lived in separate writable memory inside the same cartridge.

A CWM drone module could follow the same pattern:

```text
CWM ROM / spectral cartridge:
  fixed physical templates, pages, signatures, or recall cards

small electronic memory:
  calibration, mission state, recent observations, new labels

flight controller:
  queries the CWM module and decides action
```

This is important because a read-only or write-once CWM device can still be useful if it stores a library of physical templates that are queried many times during flight.

---

## 2. What CWM should not try to replace

CWM should not be framed as a standalone drone brain.

Do not claim replacement of:

```text
flight controller
PID/motor loop
IMU integration
GPS/navigation stack
visual SLAM
optical flow pipeline
modern object detection
radio navigation
safety-critical autonomy stack
```

CWM's realistic role is narrower:

```text
sensor signal
  -> CWM/phononic feature map or spectral page query
  -> nearest known state / obstacle signature / vibration signature
  -> normal flight controller chooses action
```

The CWM module is a recall/reflex layer, not the pilot.

---

## 3. Why drones are a plausible CWM target

Drones are physical vibrating systems moving through a physical environment. That matters because phonons and acoustic resonators are naturally sensitive to:

```text
vibration
strain
impact
motor/prop signatures
frame looseness
payload shift
acoustic reflections
ultrasonic returns
wind buffeting
structural damage
mechanical boundary changes
```

A purely optical comparison misses this point. CWM is not expected to beat cameras at images. Its best chance is to recognize physical/mechanical/acoustic states that already live in matter.

The most defensible value proposition is:

> CWM could be a low-power physical recall layer for drone state recognition, not a general-purpose vision engine.

---

## 4. Candidate drone roles

### 4.1 Vibration-state recognition

This is the most CWM-native drone application.

Candidate classes:

```text
normal hover
unbalanced prop
slightly damaged prop
badly damaged prop
loose arm
loose motor mount
payload shift
battery looseness
bearing wear
wind/gust buffeting
frame crack proxy
landing/touchdown signature
```

CWM role:

```text
frame vibration -> phononic response -> nearest enrolled state card
```

Why this is promising:

- the signal is already mechanical;
- acoustic/phononic structures can couple directly to it;
- low-dimensional state classification may be enough;
- early warning can matter more than full reconstruction;
- damage/tamper sensitivity is a feature, not a nuisance.

### 4.2 Ultrasonic/proximity obstacle signatures

A CWM module could classify acoustic returns rather than process full images.

Candidate classes:

```text
open air
flat wall
corner
pole
branch cluster
wire/fence proxy
soft vegetation
ground reflection
near-ceiling reflection
moving obstacle proxy
```

CWM role:

```text
ultrasonic ping/return -> CWM spectral page/query -> obstacle class or avoid-risk card
```

This is obstacle avoidance as signature matching, not full scene understanding.

### 4.3 Visual landmark or target-template matching

The early face/image-search direction suggests CWM may support template matching. For drones, the safer near-term version is not person recognition or broad surveillance. It is known-object / known-marker matching.

Candidate classes:

```text
landing pad marker
charging dock marker
warehouse aisle marker
inspection target
known asset label
fiducial-like symbol
known gate/window/door template
```

CWM role:

```text
camera -> small feature extractor -> CWM template lookup -> known landmark/target ID
```

CWM would not consume raw high-resolution video. It would match compact embeddings or features.

### 4.4 Fallback reflex cards

A CWM cartridge could store reflex-like safety states:

```text
vibration pattern A -> reduce throttle / land soon
proximity pattern B -> back off
wind/gust pattern C -> stabilize
payload-shift pattern D -> limit acceleration
unknown/high-risk pattern E -> return/land
```

These outputs should be advisory to the flight controller, not direct motor commands.

---

## 5. Claim ladder

### Level 0: Offline replay only

Use saved data or synthetic drone-like data to test analysis code and baselines.

Claim:

> The evaluation pipeline works and catches leakage/baseline problems.

### Level 1: Bench physical-state classifier

Use a benchtop motor/prop/frame rig or vibration table to create repeatable classes.

Claim:

> CWM features classify enrolled drone-relevant vibration states under controlled conditions.

### Level 2: Robustness advantage

Test sensor dropout, noise, partial queries, and degraded signals.

Claim:

> CWM provides graceful degradation or partial-state recall beyond a fair baseline.

### Level 3: Low-power/latency estimate

Measure or estimate energy and latency against microcontroller/DSP baselines.

Claim:

> A MEMS/phononic implementation has a credible lower-power path for the specific task.

### Level 4: Closed-loop advisory demo

CWM output informs a non-safety-critical flight-controller decision on a test rig or tethered drone.

Claim:

> CWM can act as an advisory recall/reflex layer.

### Level 5: MEMS device path

Define or fabricate a MEMS phononic unit with enough page/state capacity and low-overhead readout.

Claim:

> MEMS CWM is plausible for embedded drone modules.

Do not skip levels.

---

## 6. Experiment 1: vibration cards

**Purpose:** Test the most CWM-native drone task: recognizing mechanical/vibration states.

### Setup options

Start without a flying drone.

Possible rigs:

```text
small brushless motor mounted to plate/frame
propeller with guard or no prop for safety
cheap drone arm/frame segment
vibration motor
speaker/shaker
phone/IMU as reference sensor
CWM plate or rod mounted to frame
```

### Classes

Initial classes should be simple and safe:

```text
motor off
normal motor low RPM
normal motor high RPM
added imbalance mass
loose mount
payload shift proxy
frame damping change
simulated crack/loose joint proxy
```

### Data collection

For each class:

- capture CWM spectra/features;
- capture direct accelerometer/IMU baseline if possible;
- repeat across multiple sessions;
- vary RPM or drive level;
- include off/null captures.

### Baselines

```text
accelerometer FFT + kNN
accelerometer FFT + linear classifier
raw sensor features + random projection
software random kernel
CWM features + same classifier
CWM partial/dropout features + same classifier
```

### Metrics

- accuracy / balanced accuracy;
- confusion matrix;
- noise/dropout curve;
- session-to-session stability;
- capture latency;
- estimated energy;
- false negative rate for fault states.

### Success criterion

CWM should beat at least one fair conventional baseline under a condition that matters:

```text
partial sensor loss
low SNR
mode dropout
unknown RPM interpolation
damage/fault class separation
```

If CWM only matches a cheap accelerometer classifier while being heavier or more complex, this path is weak.

---

## 7. Experiment 2: ultrasonic obstacle cards

**Purpose:** Test obstacle-signature matching without claiming full visual obstacle avoidance.

### Setup

Use a fixed ultrasonic transmitter/receiver or speaker/mic setup with controlled objects.

Objects/classes:

```text
open air
flat wall
corner
pole/dowel
tree-branch proxy
wire/fence proxy
soft foam/cloth
floor/ground reflection
moving object proxy
```

### CWM role

The CWM device can be used in two possible ways:

1. as a passive/active acoustic feature map for return signatures;
2. as a stored template matcher after a compact acoustic feature extractor.

### Baselines

```text
raw echo FFT + kNN
simple time-of-flight threshold
software random projection
small microcontroller classifier
CWM features + same readout
```

### Success criterion

CWM must improve class recall, ambiguity handling, or robustness to partial/noisy returns.

This experiment should be framed as:

> obstacle-signature matching

not:

> complete obstacle avoidance

---

## 8. Experiment 3: visual landmark/template matching

**Purpose:** Convert the old face/image-search intuition into a drone-relevant test without overclaiming.

### Input

Use compact embeddings rather than raw camera frames.

Candidate inputs:

```text
small grayscale marker images
edge/histogram features
tiny CNN embedding
ORB/AprilTag-like descriptor
manual low-dimensional feature vector
```

### Targets

```text
landing pad marker
charging dock marker
inspection target
fiducial-like sign
known asset label
known window/door/gate template
```

### CWM role

```text
image embedding -> CWM query -> nearest stored landmark card
```

### Baselines

```text
nearest-neighbor in software
random projection + kNN
small classical CV descriptor
small CNN embedding + linear readout
CWM physical/kernel features + same readout
```

### Success criterion

CWM must show a benefit under limited compute, missing features, noisy embeddings, or few-shot/template matching.

If it only replicates a normal nearest-neighbor lookup with more hardware, this is not a strong drone path.

---

## 9. Experiment 4: reflex-card advisory loop

**Purpose:** Test whether a CWM classifier can feed useful advisory state to a controller.

### Safe closed-loop environment

Start with:

```text
simulator
bench motor rig
tethered drone
prop-off test rig
fan/wind tunnel proxy
```

Do not start with free flight.

### Advisory outputs

```text
normal
warning
reduce acceleration
land soon
obstacle-risk high
unknown state
```

### Requirement

The flight controller or simulator must remain in charge. CWM output is advisory only.

### Success criterion

CWM advisory state must reduce a measurable risk or improve classification/response time versus baseline.

---

## 10. Hardware vs offline requirements

### Can be done offline first

```text
replay saved CWM features with drone-like labels
simulate vibration classes
simulate ultrasonic returns
build evaluation scripts
compare readouts and baselines
stress-test missing features / dropout
```

### Requires bench hardware

```text
actual motor/vibration captures
actual ultrasonic returns
physical CWM mounting effects
sensor dropout by unplugging RX/drive paths
physical noise/EMI/RPM variation
energy and latency measurement
cross-session repeatability
```

### Requires future MEMS or specialized hardware

```text
low-power integrated phononic readout
MEMS CWM spectral cartridge
on-drone weight/power validation
rugged packaging
temperature/vibration/environmental qualification
```

---

## 11. MEMS path for drone module

A plausible MEMS CWM drone module would not be a standalone computer. It would be a small recall cartridge.

Possible architecture:

```text
sensor input / acoustic bus / vibration coupling
  -> MEMS phononic resonator array
  -> frequency-addressed spectral pages
  -> compact electrical readout
  -> tiny MCU / flight controller advisory signal
```

Candidate MEMS structures:

```text
phononic crystal defect cavities
beam or membrane resonators
SAW/BAW delay-line style structures
localized acoustic cavities
binary perturbation sites
writable shell coatings
piezoelectric AlN transducers
```

MEMS success gates:

- enough page/state capacity for the target task;
- stable operation across temperature and vibration;
- low-overhead readout;
- package survives drone environment;
- power is below a microcontroller/DSP baseline;
- module weight is justified by performance gain;
- calibration burden is acceptable.

---

## 12. Power and weight benchmark

CWM is worth pursuing for drones only if a credible power/weight benefit exists.

Compare against:

```text
accelerometer + MCU classifier
ultrasonic module + MCU classifier
optical-flow sensor
tiny CNN on microcontroller/NPU
software random projection + kNN
standard DSP pipeline
```

Measure or estimate:

```text
sensor power
actuation/drive power
readout power
ADC/DAC cost
compute power
latency
mass
calibration time
failure modes
```

A positive classification result without a power/weight path is not enough for drones.

---

## 13. Safety and framing limits

Avoid framing around autonomous targeting, person recognition, or weapons use.

Use safer technical framing:

```text
known landmark matching
landing-pad recognition
inspection target matching
obstacle-signature classification
vibration-state monitoring
fault detection
reflex advisory layer
```

Do not claim flight safety impact until tested in a controlled system.

---

## 14. Kill criteria

Stop or reframe this path if:

1. Accelerometer + MCU beats CWM on vibration-state tasks at lower power/weight.
2. Ultrasonic/DSP baselines beat CWM on obstacle signatures with simpler hardware.
3. CWM advantage disappears across sessions or mounting changes.
4. CWM requires too much digital decoding to justify a physical-memory claim.
5. Sensor/capture overhead dominates any MEMS projection.
6. Results depend on narrow enrolled classes and fail modest interpolation.
7. CWM cannot show a robust advantage under partial/noisy/missing-sensor conditions.
8. Physical write/spectral-page mechanisms do not improve task performance.

If these occur, drone work should pivot to educational/demo use or PUF/identity sensing rather than performance improvement.

---

## 15. First runnable roadmap

### Step 1: offline design

Create scripts:

```text
tools/drone_vibration_sim.py
tools/drone_cwm_replay.py
tools/drone_baseline_compare.py
```

Use simulated vibration classes and existing CWM matrices to validate the evaluation pipeline.

### Step 2: bench vibration cards

Build a safe motor/vibration rig and capture 5-8 classes.

Output:

```text
data/results/drone_vibration/<timestamp>/features.npz
data/results/drone_vibration/<timestamp>/results.json
docs/lab_diary_<date>.md update
```

### Step 3: fair baseline comparison

Run the same classifier families on:

```text
accelerometer features
raw electrical/wire features
software random kernels
CWM acoustic features
```

### Step 4: stress tests

Run:

```text
feature dropout
sensor dropout
noise injection
RPM interpolation
mounting perturbation
cross-session repeat
```

### Step 5: decision

If CWM wins under meaningful stress conditions, proceed to ultrasonic obstacle cards.

If not, stop drone performance framing.

---

## 16. Minimum publishable result

A narrow but useful publication-style result would be:

> A classical acoustic CWM resonator provides a physical feature map for drone-relevant vibration-state recognition, with graceful degradation under missing features/sensor dropout compared against accelerometer/DSP and software-kernel baselines.

This would not prove drone autonomy, obstacle avoidance, or MEMS compute-in-memory. It would justify the next hardware/MEMS step.

---

## 17. Summary

The drone path is plausible only if CWM is used where phonons matter:

```text
mechanical vibration
acoustic returns
physical state signatures
tamper/damage sensitivity
low-power template recall
```

The best first target is not general vision. It is:

```text
vibration-state recall -> ultrasonic obstacle signatures -> known landmark/template matching -> advisory reflex cards
```

If these experiments produce positive results against fair baselines, CWM could have a credible path as a lightweight phononic recall cartridge for drones. If not, the drone direction should be dropped or reframed as a demo rather than a performance technology.
