---
document_status: authoritative
last_verified: 2026-08-23
verified_by: codex
---

# Ego Link P0 Development Flow

Ego Link P0 uses a USB-Free, VPS Message-First, Demo-Driven, Contract-First
Walking Skeleton flow:

```text
device or simulator -> Public VPS Message Hub -> Web Dashboard
                    <- command queue / ack <-
```

This document is the development-flow baseline for new P0 work. The existing
GitHub Flow and task mechanics remain in `WORKFLOW.md`; this file defines the
product-facing order in which work should be shaped.

## Productization Sprint 1 Overlay

[ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md) and
[`FIRST_LAUNCH_EXECUTION.md`](../current/FIRST_LAUNCH_EXECUTION.md) control the
current execution order. The USB-Free/VPS/R0-R4 material below remains a
reusable engineering method and evidence lineage; it is not a global serial
permission chain.

The current user-capability Gates are:

| Gate | Current state |
|---|---|
| `P0-LOC` | `NOT_RUN` |
| `P0-CALL` | `NOT_RUN` |
| `P0-SOS` | `NOT_RUN` |

Work runs in four independent swimlanes—Location, Call/SOS,
Reliability/Security/Power, and A0/China readiness—with one integration-sized
WIP item per lane. Cross-lane work may proceed concurrently; two builders must
not edit the same shared path at the same time. A blocked operator, supplier or
external-evidence dependency blocks only its descendants.

Sprint 1 remains contract-first and event-time-first:

- the device owns Location Engine v0/Sensor Policy v0 operational state;
- the server mirrors, derives, replays and compares without replacing source
  event time with receive/ingest order;
- call media stays outside Message Hub telemetry;
- physical SOS composes the accepted safety event and persistent priority
  outbox;
- learned fusion, continuous-IMU estimators and camera/context work are
  data/replay-first L2/L3 work and do not block the P0 skeleton.

A green build, fixture, simulator, schema or PC bridge is evidence for its
named slice only. It does not change a P0 Gate from `NOT_RUN`, and no work in
this flow claims PSTN, SMS, public emergency dispatch or native VoLTE.

## Core Principles

- **USB-Free:** USB is for flashing, temporary debugging, and post-failure log
  export. Formal runtime, version acceptance, and field-test evidence must not
  depend on USB serial.
- **VPS Message-First:** Real devices, PC Simulator, and Web Dashboard connect
  through the Public VPS Message Hub for product-like operation.
- **Demo-Driven:** Every version must keep a demonstrable end-to-end loop. Do
  not spend long periods improving only internal modules with no visible loop.
- **Contract-First:** Message fields, protocol versions, and compatibility rules
  are defined before firmware, server, web, or simulator code consumes changes.
- **Walking Skeleton:** Build the thinnest complete loop first, then strengthen
  one layer at a time.

## Version Tracks

| Track | Owns | Near-term versions |
|---|---|---|
| Server-Web | VPS service, storage, command queue, Web Dashboard, test reports | S0-S4 |
| Firmware | boot, network, telemetry, GNSS, command ACK, reconnect, cache | F0-F6 |
| Protocol | envelopes, fields, topics/APIs, compatibility, error semantics | P0.1-P0.4 |

Track changes may be developed independently, but each accepted milestone must
attach to a demonstrable loop and named evidence boundary. Historical R0-R4
lineage remains in `../current/ROADMAP_EGOLINK_P0.md`; current Sprint 1 work
instead attaches to `P0-LOC`, `P0-CALL`, `P0-SOS` or a named cross-cutting
assurance Gate.

## R0-R4 Route

- R0: VPS + PC Simulator pure simulated loop.
- R1: real hardware loop without real GNSS, using fixed or mock location.
- R2: real GNSS outdoor loop with USB disconnected.
- R3: field reliability loop with reconnect, cache, and diagnostics.
- R4: product-demo loop with device list, map, history, commands, ACK, and
  exported field-test report.

Each version must define:

- goal;
- inputs and expected outputs;
- involved modules;
- allowed paths and explicitly forbidden paths;
- Definition of Done;
- validation commands and evidence paths.

## Task Naming

Use versioned task names instead of vague requests:

- `PROTO-001 Freeze P0.1 message envelope`
- `SERVER-001 Implement VPS message service minimal loop`
- `WEB-001 Implement device-status dashboard`
- `SIM-001 Connect PC Simulator to VPS loop`
- `FW-001 Implement USB-Free heartbeat`
- `FW-002 Implement real GNSS telemetry`
- `FIELD-001 Run USB-Free outdoor GNSS field test`
- `RELIABILITY-001 Add reconnect, cache, and diagnosis`

The source draft used `ENG-002` for this flow baseline, but that ID already
exists in the repository task tree. The implemented baseline is tracked as
`ENG-005 P0 Dev Flow Baseline`.

## Cross-Layer Change Rule

Do not rename protocol fields, topic shapes, command semantics, hardware
capability labels, or public data contracts inside a feature task unless the
task explicitly includes the matching Protocol track change. When protocol work
is needed, update `PROTOCOL.md` and, when machine-readable contracts are added,
`../../shared/contracts/` first.

## Related Documents

- VPS service boundary: `VPS_MESSAGE_HUB.md`
- P0 message protocol: `PROTOCOL.md`
- USB-Free field testing: `FIELD_TEST.md`
- Near-term roadmap: `../current/ROADMAP_EGOLINK_P0.md`
- Architecture decision: `../architecture/adr/ADR-0001-usb-free-vps-message-hub.md`
- Productization decision: `../architecture/adr/ADR-0012-p0-productization-sprint-1.md`
- Current execution graph: `../current/FIRST_LAUNCH_EXECUTION.md`
- Git and task mechanics: `WORKFLOW.md`
