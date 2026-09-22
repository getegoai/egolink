---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
---

# P0 Scope

## Authority Boundary

This document is authoritative for Productization Sprint 1 and the evidence
scope of the sellable first-generation P0. It conforms to
[EGO_MASTER_CONTEXT.md](EGO_MASTER_CONTEXT.md), ADR-0008 and [ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md). Current
development-board results may satisfy engineering milestones but must never be
promoted into final PCB/BOM or product claims without representative-product
validation.

## Current Evidence Architecture

Under [ADR-0015](../architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md),
the current A-line evidence architecture uses one identified Waveshare
ESP32-S3-SIM7670G-4G connectivity node plus only its necessary existing
external IMU, Camera, power source and LTE/GNSS antennas. It owns GNSS, Cell/
LTE, IMU and available power observations, Location Engine/Sensor Policy,
bounded persistent collection, actual Wi-Fi/LTE uplink with controlled route
transition, and authorized still capture/upload.

The ESP32-S3-Touch-AMOLED-2.06 remains a later Ego Call/B-line bench asset. It
does not supply A-line IMU, display, power, storage or forwarding and is not
part of this field acceptance. A PC may build, configure and review evidence,
but cannot be a field runtime or forwarding dependency. Existing dual-board
and PC-bridge results remain historical evidence rather than current topology.

The final P0 product target is not two ESP32 development boards. Product A0
converges the verified requirements into one screenless EgoCore architecture.

## In Scope

- `P0-LOC`: rule-driven `Location Engine v0` using GNSS, LTE/cell, IMU
  mobility, last-trusted location/time, battery and honest uncertainty;
- configurable `Sensor Policy v0` with `STABLE`, `MOVING`,
  `LOCATION_UNCERTAIN`, `SOS`, and `LOW_BATTERY` policy modes;
- field timeline recording, deterministic policy replay and configuration
  comparison;
- current-candidate ordinary-observation upload over actual Wi-Fi and LTE,
  including a controlled transition with exact pending/ACK/duplicate/loss truth;
- current milestone Camera closure on that same connectivity node: one
  authorized expiring Web capture and default-off bounded local timed capture,
  separate JPEG/metadata persistence, real-LTE upload, bounded engineering VPS verification
  and existing-Web preview/export with explicit failure and backlog state;
- `P0-CALL`: CALL-030 native-cellular modem/firmware/operator/audio feasibility,
  HW-022 representative hardware, then CALL-031 PC/USB-free outgoing/incoming
  calls and stable two-way audio; RTC remains auxiliary and its old packets paused;
- `P0-SOS`: qualified physical button -> recognized-input feedback and durable
  event attempt -> independent location priority, Guardian notification and an independent
  primary cellular Ego Call attempt; queue/storage degradation remains explicit;
- minimal Guardian surface needed to see location/SOS/call truth, without
  requiring polished consumer UI;
- versioned messages, explicit real/mock/source labels, privacy boundaries,
  quality inspection, and replay;
- current deterministic ego-state truth and DEVICE/canonical/API/Web contract
  compatibility under ALIGN-STATE-010; missing/stale/future/mock/invalid input
  must not become confident normal or safe state;
- BASE-010 minimum private Session endpoint, persistence/replay/report and
  retention/export/deletion design in parallel, without a fourth capability Gate;
- parallel product A0 audio/power/RF/antenna/BOM and China pre-compliance work.

## Bounded runtime convergence

[ADR-0015](../architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md)
retains Gemini's immediate collection evidence order under ADR-0016: combined single-board Location/raw
collection/Camera, Web one-shot LTE proof, timed persistence/recovery, a short
independently powered carry test and then FIELD-020. CALL-020, CALL-021 and full
physical SOS are paused for this milestone, while their final Gate obligations
remain. Camera is a milestone requirement, not a new product Gate or decision
source.

[ADR-0014](../architecture/adr/ADR-0014-runtime-convergence.md) permits an
explicitly selected current-boot/single-source live Location profile reusing
LOC-021 A-S and concrete authenticated secure transport. It is separate from
legacy and the original offline S image. T0/T1 are not global prerequisites for
this finite engineering proof or independent S smoke; concurrent SOS/IMU
ordering, checkpoint, exact tombstone and no-output replay commitments still
apply before that product composition is enabled or recovery is claimed.

The native successor CALL-031 product acceptance requires
independently powered representative hardware without PC/USB media/control,
and physical SOS/recovery integrates through the retained Location and CALL
seams. Queue/storage failure must not
silently freeze local state or suppress recognized-input feedback; stored and
delivered claims remain evidence-bound. No HTTP downgrade, disabled certificate
validation, new sensor or production pin/BOM change is implied. All three P0
Gates retain `NOT_RUN`; hardware, SIM traffic, recording and external notices
require a valid bounded experiment authorization.

## Out Of Scope

- Full Ego Base private-AI product and advanced model stack; the minimum
  BASE-010 private endpoint is in scope for parallel development.
- Learned multi-source location fusion on the P0 critical path.
- Advanced learned/general state understanding, fall/anomaly model release, camera AI, visual
  decision loops, AI voice, audio recording, video streaming or continuous
  media capture.
- Polished complete App, contact-management UX or multi-party calling before
  the minimum Guardian client and real voice path work.
- A self-operated public PSTN/SIP gateway, public emergency dispatch or SMS.
  Native cellular voice is the primary P0-CALL product requirement, still unverified.
- Adding new sensors merely to expand P0 scope; unbounded, unconsented,
  publicly stored or training-enabled Camera collection remains prohibited.
  The current milestone permits only its named manual/timed still boundary.
- Claiming production enclosure, power, RF, waterproofing, acoustics,
  compliance, BOM or ergonomics before representative evidence exists.
- Board-to-board UART as a current P0 requirement.

## P0 Acceptance Direction

The practical P0 acceptance loop is:

```text
take the device out for a representative day
-> Guardian continuously sees honest location state
-> device and authorized contact call each other through native cellular voice
-> long-press SOS immediately escalates location and human contact
-> the complete event/policy/call timeline can be replayed
```

All three capability Gates (`P0-LOC`, `P0-CALL`, `P0-SOS`) must pass. L2-AI
may improve the result but cannot compensate for or block a missing P0 Gate;
advanced learned L3 remains non-blocking. Current rule-state truth is an
engineering obligation, not a model-accuracy Gate. Public-cloud receipt, Base
receipt and human acknowledgement stay separate; existing VPS collection is
authorized bounded engineering transition, not completed local-first storage.
This task authorizes no deployment or migration/deletion of private data.
