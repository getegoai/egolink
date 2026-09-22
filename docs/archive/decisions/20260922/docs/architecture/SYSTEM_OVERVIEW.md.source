---
document_status: authoritative
decision_updated: 2026-09-09
last_verified: 2026-08-23
verified_by: codex
---

# System Overview

## Productization Sprint 1 System

[ADR-0012](adr/ADR-0012-p0-productization-sprint-1.md) freezes the sellable P0
around three capability Gates. Their current state is evidence truth, not a
progress estimate:

| Gate | Capability | Current state |
|---|---|---|
| `P0-LOC` | Reliable Location | `NOT_RUN` |
| `P0-CALL` | Ego Call | `NOT_RUN` |
| `P0-SOS` | physical-SOS loop | `NOT_RUN` |

The target product topology is:

```text
EgoLink device
  physical SOS + local feedback + durable priority outbox
  device Location Engine v0 + Sensor Policy v0
  microphone / codec / speaker path
  LTE data transport
        |
        +-> bounded event/status service -> Guardian alert/location surface
        +-> controlled RTC service ------> Guardian two-way voice
        +-> evidence mirror/timeline/replay/comparison
```

The device owns the minimum operational location and safety state required to
act offline. The server owns a versioned mirror, event-time timeline, replay,
comparison and richer *derived* estimation; it is not the sole live owner of
the device's current state. Telemetry receive/ingest time must never replace a
source event time or boot-scoped monotonic lineage.

Ego Call media is separate from Message Hub telemetry. The Message Hub is not
a media proxy. Sprint 1 excludes PSTN, SMS, public emergency dispatch and
native VoLTE as launch dependencies. Native VoLTE remains a separately
measured A0 migration reserve.

## Current A-Line Evidence Topology

[ADR-0015](adr/ADR-0015-single-4g-board-camera-field-milestone.md) makes the
current A-line milestone a single-connectivity-board evidence run:

```text
connectivity-node-001
  ESP32-S3-SIM7670G-4G
  GNSS / Cell-LTE / external QMI8658A / available power
  historically observed OV5640 candidate
  bounded ordinary-observation and JPEG persistence
        |
        +-> actual Wi-Fi and LTE upload + controlled route transition
        +-> authenticated command / exact ACK
        +-> durable private VPS photo + observation storage
        +-> authorized existing Web control / preview / query / export
```

This diagram is the current responsibility and acceptance boundary, not a claim
that the combined firmware has been flashed or run. The Camera and external IMU
must be reidentified and their shared pin/bus/resource behavior verified on the
actual assembly. The one-shot photo proof must use real LTE; ordinary
observations must also traverse actual Wi-Fi and LTE and survive a controlled
transition with honest pending, retry, duplicate and loss accounting. AMOLED,
board-to-board forwarding and PC runtime/forwarding are not part of this A-line
run. CALL-020, CALL-021 and full physical SOS are paused, while their source and
final product obligations remain.

## Retained Historical Dual-Board/PC Evidence Topology

```text
wearable_node
  ESP32-S3-Touch-AMOLED-2.06
  QMI8658 / candidate audio path / display / touch
  USB to PC

connectivity_node
  ESP32-S3-SIM7670G-4G
  SIM7670G / GNSS / candidate camera and TF-cache paths
  USB to PC

PC Development Bridge
  device discovery
  serial relay
  event bus
  ContextRouter / Safety Kernel
  data recording and replay
  debug dashboard
```

This dual-board/PC topology is retained historical development evidence, not
the current A-line or target product architecture. Board names do not prove
audio, sustained LTE voice, camera, battery, RF, enclosure or product behavior.
If the paused CALL lane later resumes, `CALL-020` may use a PC/USB media bridge
only under its own reviewed scope; that result is at most `pc_side_verified`
and cannot pass `P0-CALL`.

## Architectural Principles

- Business logic depends on abstractions and versioned messages, not raw USB, COM ports, Wi-Fi, SIM7670G AT details, GNSS, camera, IMU, or board-specific APIs.
- PC is a development bridge only.
- Mock, stub, PC-side probe, and real firmware evidence may coexist only when source labels are explicit.
- Safety-critical behavior uses deterministic rules; it must not depend on an LLM decision.
- Public location belief (`Fine | Coarse | Predicted | Unknown`), mobility,
  Sensor Policy, battery and transport/call state remain separate dimensions.
- Physical SOS persists and gives local feedback before network delivery; AI,
  camera, low battery, network loss or an unavailable RTC service cannot veto
  it.
- Learned location/context work is data- and replay-first, non-blocking L2/L3
  work until a later accepted decision promotes measured capability.

## Sellable P0 User Loop

```text
Guardian reads honest location state
             +
Guardian and device establish authorized two-way Ego Call
             +
physical SOS long press
-> durable local safety_event + local feedback
-> immediate upload of last trusted location
-> elevated GNSS/LTE policy
-> independent Guardian alert and Ego Call request states
-> replayable event-time evidence
```

The historical motion-candidate/AMOLED/PC loop remains reusable engineering
evidence. It is not a substitute for, or a blocker ahead of, the three P0
capability Gates.

See `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md` for the retained
historical dual-board bridge design; it does not override ADR-0015.
