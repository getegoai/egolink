---
document_status: authoritative
last_verified: 2026-06-26
verified_by: codex
---

# System Overview

## Current P0 Topology

```text
wearable_node
  ESP32-S3-Touch-AMOLED-2.06
  QMI8658 / audio path / display / touch
  USB to PC

connectivity_node
  ESP32-S3-SIM7670G-4G
  SIM7670G / GNSS / camera / TF-cache capability
  USB to PC

PC Development Bridge
  device discovery
  serial relay
  event bus
  ContextRouter / Safety Kernel
  data recording and replay
  debug dashboard
```

## Architectural Principles

- Business logic depends on abstractions and versioned messages, not raw USB, COM ports, Wi-Fi, SIM7670G AT details, GNSS, camera, IMU, or board-specific APIs.
- PC is a development bridge only.
- Mock, stub, PC-side probe, and real firmware evidence may coexist only when source labels are explicit.
- Safety-critical behavior uses deterministic rules; it must not depend on an LLM decision.

## Current Minimum Safety Loop

```text
motion candidate
-> ask_user command
-> AMOLED prompt
-> user_confirmation
-> request_location
-> location_report
-> safety_event recording
-> quality gate
-> replay
```

See `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md` for detailed dual-board bridge design.
