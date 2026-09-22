---
document_status: authoritative
last_verified: 2026-08-23
verified_by: founder/codex
---

# ADR-0012: Productization Sprint 1 Freezes the Sellable P0

- Status: accepted
- Date: 2026-08-23
- Decision owner: founder
- Scope: P0 release Gates, Location Engine ownership, Sensor Policy, voice PoC,
  SOS composition, and scope exclusions

## Subsequent decision — 2026-09-22

[ADR-0016](ADR-0016-local-first-ego-state-cellular-primary.md) records the founder's 2026-09-19 decision and
2026-09-22 migration instruction. It partially supersedes RTC-primary/native-
reserve wording, defers no longer the minimal private Base endpoint, and admits
bounded rule-state truth work. Three P0 Gate names, evidence obligations,
local safety, source time, exact ACK and the current single-board field scope
remain; CALL-020/021 and full SOS are not automatically resumed. The text
below is the original dated decision, not a new current-state report.

## Context

EgoLink has enough GNSS, LTE, IMU, Message Hub, field-evidence and contract
scaffolding to stop exploring every possible sensor/model direction at once.
The next phase must assemble a sellable first product instead of expanding
multi-source learning, camera AI, anomaly detection and context understanding.

Two existing architecture boundaries need an explicit migration rather than a
silent reinterpretation:

- ADR-0004/EALE-P0 made the first estimator a server-side derived layer. The
  product now also needs a small device-owned operational state and policy so
  it can preserve last trusted location and act during network loss.
- ADR-0011 selects controlled RTC as the product communications direction, but
  the first hardware/network milestone should prove real LTE-data voice without
  forcing browser-grade WebRTC into the ESP32-S3 proof.

## Decision

### 1. Exact P0 capability Gates

A P0 capability release requires all three Gates to be `PASS`:

| Gate | Capability | Required product outcome |
| --- | --- | --- |
| `P0-LOC` | Reliable Location | Guardian sees the best current explainable location or honest degraded state across declared scenarios. |
| `P0-CALL` | Ego Call | Device and Guardian can initiate stable, authorized, two-way full-duplex voice over LTE data with honest failure/recovery state. |
| `P0-SOS` | physical-SOS loop | Long press causes immediate local feedback/durable event, location escalation, Guardian alert and Ego Call attempt. |

All three are necessary, not sufficient, for sale. Power, reliability,
waterproof/acoustic, RF, privacy/security, China compliance and NPI assurance
still have to pass for the representative product.

`L2-AI` is best effort and non-blocking. `L3` context/event understanding is
outside the first-launch critical path.

### 2. Location Engine v0 ownership

The product uses two explicit layers:

```text
device Location Engine v0 + Sensor Policy v0
-> versioned observation/state output
-> server mirror, timeline, replay, comparison and Guardian view
```

The device owns the minimum operational state needed to act offline:

- `mobility_state`, `gnss_state`, `lte_state`;
- `last_trusted_location`, `last_trusted_time`;
- current `location_belief`, accuracy, confidence, source and uncertainty;
- `battery_state` and `sensor_policy_state`;
- GNSS attempt/backoff and action lineage.

The server remains the evidence, replay, comparison and richer-estimation
surface. It does not become the only owner of the device's current safety
state. Existing EALE-P0 server evidence and public belief states remain valid.

### 3. State layers do not mix

- Public `location_belief.state` stays `Fine | Coarse | Predicted | Unknown`.
- `mobility_state` stays separate (`stationary`, `moving`, later more detail).
- Sensor Policy v0 exposes `STABLE`, `MOVING`, `LOCATION_UNCERTAIN`, `SOS`, and
  `LOW_BATTERY` as readable effective policy states.
- `battery_state` is also retained independently so low battery is not erased
  during SOS. Effective priority is `SOS` over `LOW_BATTERY` over normal
  location policy.
- ADR-0003 `L0..L4` remains a compatibility/engineering scheduler level:
  `STABLE -> L0/L1`, `MOVING -> L2`, `LOCATION_UNCERTAIN -> L3`, `SOS -> L4`;
  `LOW_BATTERY` applies restricted budgets without disabling SOS.

### 4. Policy is configured and replayed

Intervals, IMU rates, GNSS acquisition timeout, no-fix retry/backoff,
uncertainty growth, low-battery behavior and SOS overrides are versioned
configuration, not unexplained constants spread through firmware.

Initial values are conservative engineering defaults, not product-optimal
claims. Field sessions must be replayable under another configuration so
location availability/uncertainty and sensor-action counts can be compared
before changing release policy.

### 5. Ego Call proof sequence

The call work proceeds in three bounded proofs because the current development
boards split accepted audio and LTE/GNSS capability:

1. `CALL-010`: prove microphone -> device audio path -> speaker locally on the
   exact development hardware.
2. `CALL-020`: use an explicitly labelled PC/USB development media bridge to
   prove continuous two-way audio over the actual SIM/LTE data interface and a
   bounded relay/Guardian client. This is `pc_side_verified` PoC evidence only.
3. `CALL-021`: remove PC and USB from media, control and runtime evidence on an
   independently powered integrated prototype before `P0-CALL` can pass.

PCM/ADPCM/Opus with a bounded UDP or WebSocket transport may be used for this
engineering proof. It is not automatically the final P0 RTC architecture,
does not turn Message Hub into a media proxy, and cannot by itself mark
`P0-CALL` as `PASS`. Provider/RTC, identity, encryption, weak-network,
acoustic, power and operations evidence still close the product Gate.

### 6. SOS composes existing contracts

`SOS-010` reuses the accepted safety-event contract and persistent priority
outbox. It does not invent another SOS record. The order is local durable
record/feedback first, then immediate last-trusted location upload, elevated
GNSS/LTE policy, Guardian notification and Ego Call request with independent
truthful states.

### 7. Explicit scope exclusions

Productization Sprint 1 does not add new sensor dependencies, learned
multi-source fusion, general anomaly/risk models, camera-to-AI decisions,
visual understanding, a polished complete App, AI voice, recording, PSTN or
native VoLTE.

Camera remains an optional experimental observation source only: stable power
on/off, one authorized still, event time and `trigger_reason`. It cannot make
or veto a P0 decision.

Hardware architecture and China pre-compliance proceed in parallel. HW-020 is
only the interface baseline; HW-021 must freeze an exact buildable design and
HW-022 must produce the integrated prototype used by CALL-021. Audio is a core
BOM/interface requirement; camera/AI remain compatibility growth paths.

## Supersession

This ADR partially supersedes ADR-0004 only where that decision makes the
server the sole live owner of P0 operational location state. ADR-0004's
rule-first estimator, conservative source semantics, privacy and server replay
remain accepted.

It refines ADR-0003 by adding readable Productization Sprint 1 policy states
and a low-battery modifier/priority rule; it does not merge policy state with
public location belief.

It refines ADR-0011 by inserting a transport-agnostic real voice PoC before
final RTC selection. ADR-0011's controlled-service product direction,
authorization, privacy, honest state and no-PSTN boundary remain accepted.

It partially supersedes ADR-0002's and ADR-0008's older first-launch wording
that made learned anomaly/proactive check-in, camera or native VoLTE release
dependencies. Their on-device growth budget, screenless modular product,
privacy/local-safety principles, audio hardware and A0-to-A1 discipline remain
accepted; those broader capabilities now sit outside Sprint 1's three Gates.

## Immediate Task Chain

```text
LOC-020 -> POLICY-010 -> REPLAY-010 -> LOC-021 -> FIELD-020 ----+
                                             |                  |
CALL-010 -> CALL-020 ------------------+      +-> SOS-010 -------+-> release
HW-020 -> HW-021 -> HW-022 ------------+-> CALL-021 --^
OUTBOX-010 -----------------------------------------^

HW-022 + LOC-021 + CALL-021 + SOS-010 -> PWR-020

FIELD-020 + SOS-010 + OUTBOX-010 + OPS-004 + PWR-020 + HW-022
    + COMPLIANCE-010 + product acoustic/RF/water/NPI evidence
    -> P0-RELEASE-010
```

L2 models may consume FIELD/REPLAY outputs later. They do not enter this
critical chain. FIELD-020 and SOS-010 advance independently and meet only at
the final release review; neither is a serial prerequisite for the other.

## Related Documents

- [North Star](../../product/NORTH_STAR.md)
- [Master Context](../../product/EGO_MASTER_CONTEXT.md)
- [P0 Scope](../../product/P0_SCOPE.md)
- [Current execution](../../current/FIRST_LAUNCH_EXECUTION.md)
- [Location Engine](../../development/LOCATION_ENGINE.md)
- [Ego Call](../../development/EGO_CALL.md)
