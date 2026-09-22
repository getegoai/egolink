---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
---

# Ego Link P0 Development Flow

Ego Link uses a local-first, Demo-Driven, Contract-First Walking Skeleton.
The current collection/VPS flow is an authorized bounded engineering transition:

```text
device or simulator -> Public VPS Message Hub -> Web Dashboard
                    <- command queue / ack <-
```

This document is the development-flow baseline for new P0 work. The existing
GitHub Flow and task mechanics remain in `WORKFLOW.md`; this file defines the
product-facing order in which work should be shaped.

## Current product and implementation flow

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md) and
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
- the private Base endpoint mirrors, derives, replays and compares without
  replacing source event time with receive/ingest order; the VPS transition
  must declare purpose, access, quota, expiry and lifecycle. Missing controls
  remain implementation gaps, not completed privacy guarantees;
- native cellular is the primary call route, with optional RTC fallback;
  Message Hub telemetry is not native call media;
- physical SOS composes the accepted safety event and persistent priority
  outbox;
- existing rule-state truth and explicit DEVICE/canonical/API/Web compatibility
  are current engineering acceptance, including missing/stale/mock/invalid input;
- advanced learned fusion and camera/context models remain data/replay-first
  non-blocking L2/L3; complete Base AI is not a new capability Gate.

A green build, fixture, simulator, schema or PC bridge is evidence for its
named slice only. It does not change a P0 Gate from `NOT_RUN`, and no work claims
working native voice from AT initialization alone. A self-operated public
PSTN/SIP gateway, SMS and public emergency dispatch remain out of scope.

## Core Principles

- **USB-Free:** USB is for flashing, temporary debugging, and post-failure log
  export. Formal runtime, version acceptance, and field-test evidence must not
  depend on USB serial.
- **Local-First:** BASE-010 develops the minimum user-controlled private
  Session endpoint in parallel. Public cloud is reachability/signaling/bounded
  relay; engineering VPS receipt is not Base receipt or completed privacy.
  Preserve existing private data; migration/deletion needs its own scope.
- **Demo-Driven:** Every version must keep a demonstrable end-to-end loop. Do
  not spend long periods improving only internal modules with no visible loop.
- **Contract-First:** Message fields, protocol versions, and compatibility rules
  are defined before firmware, server, web, or simulator code consumes changes.
- **Walking Skeleton:** Build the thinnest complete loop first, then strengthen
  one layer at a time.

## Current ownership

Gemini owns single-board recovery, actual Wi-Fi/LTE switching and D2/FIELD-020.
Codex ALIGN-STATE-010 owns decision/current-state/task alignment and rule-state
truth. Shared collection_main edits are limited to the assigned packaging seam;
acquisition/modem/camera/transport/profile changes stay with Gemini. Contract
changes have one integrator and consumers adopt the accepted version.

CALL-030 native feasibility feeds HW-021/HW-022 and CALL-031 representative
product calling; old CALL-020/021 RTC packets remain paused. BASE-010 and A0/
compliance are parallel queued work, not automatic WIP. See the current
execution graph and each packet for dispatch, evidence and operator scope.

## Version Tracks

| Track | Owns | Near-term versions |
|---|---|---|
| Server-Web | Private endpoint plus bounded transition service, contracts/API/Web and reports | S0-S4 |
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
