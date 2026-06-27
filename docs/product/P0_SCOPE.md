---
document_status: authoritative
last_verified: 2026-06-26
verified_by: codex
---

# P0 Scope

## Current Architecture Form

P0 uses a dual-development-board plus PC Development Bridge integration architecture.

- `wearable_node`: ESP32-S3-Touch-AMOLED-2.06, responsible for QMI8658 IMU, audio path validation, screen, touch, speaker, and user interaction.
- `connectivity_node`: Waveshare ESP32-S3-SIM7670G-4G, responsible for SIM7670G 4G, GNSS, camera, TF/cache capability validation, and communication expansion.
- PC Development Bridge: serial bridge, event bus, ContextRouter/Safety Kernel host, recording, replay, time sync, and debug dashboard.

The final product target is not two ESP32 development boards. The long-term target is one low-power MCU or AI MCU plus cellular module and required sensors.

## In Scope

- Versioned `hello` discovery for both nodes.
- No hardcoded COM port assumptions in product-facing tooling.
- Shared versioned message protocol.
- Real and mock data coexisting with explicit source labels.
- QMI8658 data collection and engineering calibration evidence.
- AMOLED `ask_user` display and touch confirmation.
- SIM7670G 4G/GNSS/camera capability evidence through staged probes.
- Session recording, quality inspection, and replay.

## Out Of Scope

- Formal Ego Base implementation.
- Cloud service dependency.
- Mobile app.
- Production enclosure.
- Production power optimization.
- Real emergency dialing, SMS, or dispatch.
- Final MotionNet/AudioGate/VisionGate training acceptance.
- Board-to-board UART as a current P0 requirement.

## P0 Acceptance Direction

The practical P0 acceptance loop is:

```text
motion candidate
-> PC Bridge receives event
-> user confirmation on AMOLED
-> request location/evidence from connectivity path
-> complete safety event record
-> replay without boards
```
