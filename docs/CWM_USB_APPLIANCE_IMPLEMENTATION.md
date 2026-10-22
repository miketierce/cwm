# CWM USB Appliance Implementation Roadmap

## Status

**OPEN — implementation roadmap and experimental specification.**

This document does not promote any OPEN CWM hypothesis to MEASURED. Its purpose is to force the existing research into a complete, externally usable appliance and determine exactly which memory-like semantics the physical system can support.

## Objective

Build the smallest complete CWM appliance that a normal host computer can use through a conventional digital interface.

The first milestone is deliberately modest:

> A USB-connected CWM demonstrator can enroll a small set of physical states, query them, return a state plus confidence, survive process/device restart where the underlying state permits it, recalibrate, report health, and expose failures explicitly.

The goal is not capacity. The goal is a complete system.

```text
physical CWM substrate
        ↓
actuation + sensing
        ↓
acquisition / feature extraction
        ↓
calibration + decoder
        ↓
small controller/service
        ↓
USB serial protocol
        ↓
ordinary host computer
```

## Why this implementation matters

Research prototypes can hide important costs in notebooks, manually selected files, offline classifiers, and experiment-specific setup. An appliance cannot.

A complete device forces explicit answers to:

- What exactly is written or enrolled?
- What persists without drive power?
- What persists only because digital metadata was saved?
- Does a read disturb the physical state?
- Can the system restore a disturbed state?
- How much calibration is required?
- What happens when confidence is low?
- How many measurements and channels are actually required?
- What are latency and energy per operation?
- Which functions are performed by physics and which by software?

## Memory taxonomy

Do not call all forms of persistence simply "memory." Record them separately.

### CWM-ROM

Information fixed by geometry, material, permanent perturbations, fabrication, or other effectively permanent physical properties.

### CWM-PERSISTENT

Information represented by a deliberately writable and reversible physical configuration that survives removal of drive power.

**OPEN until demonstrated.**

### CWM-WORKING

Transient state represented by excitation, ring-down, temporary boundary conditions, or another state that decays or must be refreshed.

### DIGITAL-METADATA

Labels, templates, calibration matrices, decoder parameters, configuration, and experiment metadata stored conventionally.

A successful appliance must report which category is responsible for every claimed retained state.

## MVP definition

Target an intentionally small logical state space: initially **4–8 states**, expandable only after reliability is characterized.

The MVP must support:

1. `STATUS`
2. `CALIBRATE`
3. `ENROLL <id>`
4. `QUERY`
5. `LIST`
6. `DELETE <id>` where the implementation supports logical deletion
7. `READ <id>` where direct addressed recall is meaningful
8. `HEALTH`
9. `RESET`
10. `EXPORT_DIAGNOSTICS`

Optional only after semantics are demonstrated:

- `WRITE_PHYSICAL <id>`
- `RESTORE <id>`
- `REFRESH <id>`

Do not emulate unsupported physical operations in software while presenting them as CWM operations.

## Interface

### Phase 1 transport

Use USB CDC/serial or an equivalent simple host-visible transport. Avoid implementing USB mass storage initially because filesystem semantics would obscure the experimental question.

Human-readable commands are acceptable for v0:

```text
STATUS
CALIBRATE
ENROLL 03
QUERY
HEALTH
```

Example response:

```json
{
  "operation": "QUERY",
  "state": "03",
  "confidence": 0.91,
  "unknown": false,
  "latency_ms": 37.2,
  "calibration_id": "...",
  "physical_channels": 4,
  "features_used": 32
}
```

Machine-readable responses are required even if a CLI also prints friendly text.

## Architecture rule: expose boring semantics

The host should not need to understand modal physics.

Internally the implementation may involve drive synthesis, PZTs, ADCs, spectral measurements, linear calibration, nearest-template recall, or another validated decoder. Externally it should expose a small stable contract.

The adapter/controller is allowed to compensate for physical peculiarities. That is normal system architecture, not cheating, provided the division of labor is measured and documented.

## Implementation phases

### AP-0 — Freeze the semantics

Before new hardware work, document for the current setup:

- what constitutes a physical state,
- what constitutes enrollment,
- what a query physically does,
- which data are stored digitally,
- whether the physical substrate changes during enrollment,
- whether it changes during query,
- expected persistence class,
- decoder and calibration dependencies.

**Deliverable:** `results/appliance/ap0_semantics.json` plus a short debrief.

**Stop condition:** if the proposed demonstration is only a conventional digital lookup keyed by a plate measurement, label it as such and redesign before claiming a memory appliance.

### AP-1 — Deterministic headless acquisition

Extract the minimum acquisition path from notebooks/scripts into a repeatable command-line or service entry point.

Requirements:

- no manual frequency selection during a run,
- fixed acquisition configuration,
- fixed preprocessing,
- timestamps,
- hardware IDs,
- calibration ID,
- raw-data retention,
- explicit error codes.

Target API concept:

```text
acquire() -> raw measurement
encode(raw, calibration) -> representation
query(representation, enrollment) -> state/confidence/unknown
```

**Pass:** 100 consecutive automated acquisitions complete without manual intervention and produce schema-valid results.

### AP-2 — Minimal logical memory service

Implement a small service around the frozen decoder.

Enrollment record should contain at minimum:

```json
{
  "state_id": "03",
  "created_at": "...",
  "representation": [],
  "physical_configuration": {},
  "calibration_id": "...",
  "persistence_class": "DIGITAL-METADATA",
  "provenance": {}
}
```

The persistence field is mandatory so a digital template cannot silently become a claim of physically written memory.

**Pass:** enroll and query 4–8 states through the service with held-out repeated acquisitions and explicit UNKNOWN rejection.

### AP-3 — USB host interface

Wrap the service in a USB-accessible controller or bridge.

Preferred progression:

1. existing host computer + USB-visible serial process,
2. microcontroller/SBC bridge if necessary,
3. embedded MCU only after workload size is known.

Provide a reference host CLI:

```text
cwm status
cwm calibrate
cwm enroll 03
cwm query
cwm health
cwm diagnostics export
```

**Pass:** a second computer with no experiment notebook can install/run the host client and perform the documented workflow.

### AP-4 — Restart and persistence matrix

Test every state category across increasingly severe restart conditions:

1. restart host process,
2. reboot host,
3. power-cycle controller,
4. remove drive excitation,
5. power-cycle all electronics,
6. disconnect/reconnect the physical CWM module,
7. wait defined retention intervals.

For every test distinguish:

- physical state retained,
- calibration retained digitally,
- enrollment retained digitally,
- full re-enrollment required.

Produce a matrix rather than a binary "nonvolatile" claim.

**Pass criteria:** none predetermined. This experiment classifies the architecture.

### AP-5 — Read-disturb / destructive-read experiment

Test whether repeated queries alter the state or its representation.

For each enrolled physical configuration:

1. establish baseline,
2. issue 1, 10, 100, and 1000 repeated queries where practical,
3. record representation drift,
4. record confidence and error rate,
5. compare against matched elapsed-time no-read controls.

Metrics:

- cosine/Euclidean representation drift,
- state accuracy,
- confidence drift,
- modal amplitude/frequency drift,
- temperature,
- elapsed time.

The no-read control is required to separate read disturbance from ordinary temporal drift.

### AP-6 — Restore/refresh experiment

Run only if AP-5 finds meaningful read disturbance or if CWM-WORKING state naturally decays.

Compare:

```text
READ × N
```

against:

```text
READ → RESTORE/REFRESH → READ → RESTORE/REFRESH ...
```

Measure whether restoration improves state retention and quantify:

- restoration latency,
- restoration energy,
- residual error,
- endurance,
- accumulated drift.

A successful restore cycle may be architecturally useful even if reads are destructive.

### AP-7 — Partial-query appliance demonstration

The appliance should demonstrate the capability most aligned with current CWM evidence: recovery of a known state from incomplete evidence.

Test physical omissions where possible, not only software masking.

For each enrolled state:

- full query,
- one omitted query axis,
- multiple omitted axes where physically meaningful,
- receiver dropout,
- attenuation/noise,
- unknown state.

Return both state and confidence.

**Critical control:** compare against the best simple electronic/software baseline using the same surviving observations.

### AP-8 — Reduce the readout burden

The research system may use far more frequencies/channels than a product can tolerate.

Sweep:

- feature count,
- frequency count,
- receiver count,
- acquisition duration,
- ADC resolution where possible.

Goal: find the smallest readout that preserves useful recall.

Do not optimize only accuracy. Record latency and energy.

### AP-9 — Appliance benchmark

Freeze the final v0 protocol and run an unattended benchmark.

Minimum target:

- >= 1000 query operations,
- multiple process restarts,
- at least one full electronics power cycle,
- repeated calibration checks,
- known-state and unknown-state trials,
- physical dropout trials,
- complete error log.

Report:

- accuracy,
- unknown rejection,
- p50/p95/p99 latency,
- operations between failures,
- recalibration frequency,
- energy per operation where measurable,
- physical vs digital state responsibility.

## Required baselines

The appliance must be compared against conventional alternatives, not only against degraded versions of itself.

At minimum:

1. direct electronic/raw-feature nearest-template lookup,
2. ridge/logistic linear decoder,
3. low-dimensional PCA/SVD representation where applicable,
4. conventional sensor + MCU/DSP estimate or implementation for the target workload.

The question is not whether CWM can work. It is whether the physical substrate contributes useful behavior beyond what a simpler system already provides.

## Suggested repository structure

```text
cwm/
├── appliance/
│   ├── protocol/
│   ├── service/
│   ├── acquisition/
│   └── cli/
├── firmware/
│   └── usb_bridge/
├── schemas/
│   └── appliance_result.schema.json
├── results/
│   └── appliance/
└── docs/
    └── CWM_USB_APPLIANCE_IMPLEMENTATION.md
```

Adapt to existing repo conventions rather than creating duplicate infrastructure.

## Versioned protocol concept

Every request/response should carry a protocol version once the interface stabilizes.

Example:

```json
{
  "protocol": "cwm-appliance/0.1",
  "request_id": "...",
  "command": "QUERY"
}
```

Responses must distinguish at least:

- `OK`,
- `UNKNOWN`,
- `LOW_CONFIDENCE`,
- `CALIBRATION_REQUIRED`,
- `HARDWARE_ERROR`,
- `ACQUISITION_ERROR`.

Never force a known-state answer when the evidence is insufficient.

## Observability

Every operation should log enough information to reproduce failures:

- firmware/software commit,
- hardware identifier,
- plate/device identifier,
- calibration identifier,
- enrollment identifier,
- timestamp,
- temperatures if available,
- acquisition settings,
- physical channels available,
- feature count,
- raw-data path/hash,
- predicted state,
- confidence,
- latency,
- error status.

## Energy accounting

The appliance is the right place to begin honest end-to-end energy measurement.

Count separately:

- waveform generation,
- actuator/driver energy,
- analog frontend,
- ADC/acquisition,
- controller/host processing,
- calibration,
- restore/refresh if required.

Report both joules/query and average power for any always-on mode.

A passive physical transform is not commercially "free" if extracting it requires an expensive measurement chain.

## Demonstration ladder

### Demo 0 — Host-only API

Existing hardware, automated service, no notebook.

### Demo 1 — USB CWM cartridge

A normal laptop connects by USB and can calibrate, enroll, query, and inspect health.

### Demo 2 — Restartable cartridge

The device survives documented restart/power-cycle conditions and accurately reports which state was physically versus digitally retained.

### Demo 3 — Partial-query cartridge

A visibly incomplete physical query still retrieves an enrolled state better than the frozen baseline.

### Demo 4 — Embedded controller

Move calibration/readout/decoder onto a small controller if resource measurements justify it.

### Demo 5 — MEMS precursor

Only after the interface and workload are stable should the same logical contract be targeted by smaller hardware.

## Success tiers

### Tier 1 — Complete research appliance

A second computer can operate the system through USB without notebooks or manual experiment intervention.

### Tier 2 — Robust associative appliance

It retrieves enrolled states under controlled physical omissions/dropout and rejects unknowns.

### Tier 3 — Persistent/refreshable physical state

A deliberately written physical configuration survives or can be restored according to measured semantics. This tier remains OPEN until physical writable-state experiments support it.

### Tier 4 — Product-relevant appliance

The system shows a measurable robustness, energy, latency, channel-count, or integration advantage over a credible conventional baseline.

## Kill / redirect criteria

Redirect the appliance effort if any of the following persists after controlled investigation:

- the physical substrate contributes no measurable benefit over direct electronic features,
- calibration overhead dominates normal use,
- small environmental changes require full re-enrollment,
- physical query completion disappears when omissions are implemented in hardware,
- readout energy/latency overwhelms the physical-compute benefit,
- the system cannot reject unknown states safely,
- or apparent persistence is entirely conventional digital template storage while being presented as physical memory.

A negative result should narrow CWM's role rather than be hidden.

## Immediate implementation checklist

1. Inventory the current acquisition and decoder path.
2. Write AP-0 semantics JSON/debrief.
3. Select 4–8 frozen states for the appliance benchmark.
4. Freeze preprocessing and decoder versions.
5. Create the headless `acquire → encode → query` path.
6. Add machine-readable result schemas.
7. Implement `STATUS`, `CALIBRATE`, `ENROLL`, `QUERY`, and `HEALTH` first.
8. Add USB serial transport and host CLI.
9. Run restart/persistence matrix.
10. Run read-disturb versus no-read control.
11. Run physical partial-query/dropout trials.
12. Reduce frequencies/channels while tracking accuracy, energy, and latency.
13. Run the >=1000-query unattended appliance benchmark.
14. Publish a debrief that labels every result MEASURED or OPEN.

## Guiding principle

> **First make the complete machine work. Optimize density later.**

The most useful next milestone is not a theoretical capacity projection. It is a small CWM device whose physical role, digital support, persistence, failure modes, and external interface are explicit enough that another person can plug it into a computer and reproduce the result.