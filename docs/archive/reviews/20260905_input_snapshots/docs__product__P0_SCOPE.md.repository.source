---
document_status: authoritative
last_verified: 2026-08-23
verified_by: codex
---

# P0 Scope

## Authority Boundary

This document is authoritative for Productization Sprint 1 and the evidence
scope of the sellable first-generation P0. It conforms to
[EGO_MASTER_CONTEXT.md](EGO_MASTER_CONTEXT.md), ADR-0008 and ADR-0011. Current
development-board results may satisfy engineering milestones but must never be
promoted into final PCB/BOM or product claims without representative-product
validation.

## Current Evidence Architecture

P0 uses a dual-development-board plus PC Development Bridge integration architecture.

- `wearable_node`: ESP32-S3-Touch-AMOLED-2.06, responsible for QMI8658 IMU, audio path validation, screen, touch, speaker, and user interaction.
- `connectivity_node`: Waveshare ESP32-S3-SIM7670G-4G, responsible for SIM7670G 4G, GNSS, camera, TF/cache capability validation, and communication expansion.
- PC Development Bridge: serial bridge, event bus, ContextRouter/Safety Kernel host, recording, replay, time sync, and debug dashboard.

The final P0 product target is not two ESP32 development boards. Product A0
converges the verified requirements into one screenless EgoCore architecture.

## In Scope

- `P0-LOC`: rule-driven `Location Engine v0` using GNSS, LTE/cell, IMU
  mobility, last-trusted location/time, battery and honest uncertainty;
- configurable `Sensor Policy v0` with `STABLE`, `MOVING`,
  `LOCATION_UNCERTAIN`, `SOS`, and `LOW_BATTERY` policy modes;
- field timeline recording, deterministic policy replay and configuration
  comparison;
- `P0-CALL`: microphone/speaker hardware loop, a bounded PC-bridged LTE-data
  voice PoC, then a PC/USB-free embedded media path on one independently
  powered integrated prototype; the bridge is learning evidence, not Gate
  completion;
- `P0-SOS`: physical button -> local durable event/feedback -> location
  priority -> guardian notification -> Ego Call;
- minimal Guardian surface needed to see location/SOS/call truth, without
  requiring polished consumer UI;
- versioned messages, explicit real/mock/source labels, privacy boundaries,
  quality inspection, and replay;
- parallel product A0 audio/power/RF/antenna/BOM and China pre-compliance work.

## Out Of Scope

- Formal Ego Base implementation.
- Learned multi-source location fusion on the P0 critical path.
- General state understanding, fall/anomaly model release, camera AI, visual
  decision loops, AI voice, recording or continuous media capture.
- Polished complete App, contact-management UX or multi-party calling before
  the minimum Guardian client and real voice path work.
- PSTN, public SIP gateway, SMS dispatch or native VoLTE release behavior.
- Adding new sensors merely to expand P0 scope; camera is limited to stable
  power control, one authorized still and truthful trigger/time metadata when
  separately exercised.
- Claiming production enclosure, power, RF, waterproofing, acoustics,
  compliance, BOM or ergonomics before representative evidence exists.
- Board-to-board UART as a current P0 requirement.

## P0 Acceptance Direction

The practical P0 acceptance loop is:

```text
take the device out for a representative day
-> Guardian continuously sees honest location state
-> device and Guardian can call each other over LTE data
-> long-press SOS immediately escalates location and human contact
-> the complete event/policy/call timeline can be replayed
```

All three capability Gates (`P0-LOC`, `P0-CALL`, `P0-SOS`) must pass. L2-AI
may improve the result but cannot compensate for or block a missing P0 Gate;
L3 remains outside this Sprint.
