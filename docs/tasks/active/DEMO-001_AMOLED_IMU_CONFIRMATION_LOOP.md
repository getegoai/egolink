---
id: DEMO-001
title: AMOLED IMU Confirmation Loop
status: active
priority: high
requires_hardware: true
created: 2026-06-26
last_updated: 2026-06-26

context:
  - docs/CONTEXT_INDEX.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/architecture/SYSTEM_OVERVIEW.md
  - docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md
  - firmware/AGENTS.md
  - pc_simulator/AGENTS.md

allowed_paths:
  - firmware/amoled_safety_demo/main/app_main.c
  - pc_simulator/board_bridge.py
  - pc_simulator/live_safety_demo.py
  - docs/tasks/active/DEMO-001_AMOLED_IMU_CONFIRMATION_LOOP.md

out_of_scope:
  - real GNSS/4G integration
  - audio validation
  - stability hardening
  - formal IMU product acceptance
  - model training
  - broad hardware-boundary framework work
---

# Problem

The project has transitioned to a Demo-first/minimum visible prototype priority (Demo v0.1). To establish the core safety loop, we need to connect physical sensor input with visual user confirmation on a single wearable device, bridged to a local monitoring environment. Currently, individual pieces exist—such as QMI8658 static readings, raw MQTT status updates, and a standalone visual amoled_safety_demo firmware—but they are not connected into an integrated active confirmation loop.

# Expected Result

A cohesive end-to-end Demo v0.1 confirmation flow using a single ESP32-S3-Touch-AMOLED-2.06 board and a PC:
1. Physical IMU jolts/taps register on the wearable board and trigger an impact/fall candidate.
2. The PC Bridge receives and normalizes this candidate event.
3. The PC Bridge sends a downstream query command (`ask_user`) to the wearable board.
4. The wearable board AMOLED screen prompts the user with: "检测到异常，你现在安全吗？"
5. The user interacts via screen touch (tapping "SAFE" or "HELP" buttons).
6. The wearable board returns the touch selection back to the PC Bridge, which maps the touch outcomes to the canonical product choices `safe` / `needs_help` (mapping firmware serial payloads such as `help` to the canonical `needs_help` outcome).
7. The PC Bridge generates a complete safety event record combining the raw IMU trigger context, downstream prompt timing, and the final touch-confirmed outcome, utilizing mock/PC-simulated location data for GNSS/4G coordinates.

# Acceptance Criteria

- [ ] Physical movement or tap on the ESP32-S3-Touch-AMOLED-2.06 board triggers an impact/fall candidate event.
- [ ] PC Bridge receives, decodes, and normalizes the candidate event from the wearable board.
- [ ] PC Bridge transmits an `ask_user` instruction to the wearable board.
- [ ] Wearable board displays the query: "检测到异常，你现在安全吗？" (or a visual equivalent layout with touch buttons).
- [ ] Screen touch detection captures user tap on "SAFE" or "HELP", returning a versioned JSON `user_confirmation` payload via serial, with the PC Bridge mapping the raw serial values (like `help`) to the canonical product outcomes (`safe` / `needs_help`).
- [ ] PC Bridge receives the user's touch decision and records a final, cohesive safety event record (such as in an event log or JSONL) with precise timestamps.
- [ ] GNSS/4G evidence within the safety event record is successfully mock or PC-side simulated; real SIM7670G cellular/GPS activation is completely bypassed for v0.1.

# Validation Commands

```powershell
# Runs repository context and documentation linting
python scripts/context_lint.py

# Performs general static repository verification
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1

# Live hardware verification and PC Bridge scripts are manual/planned during implementation:
# Example: python pc_simulator/pc_bridge.py --demo-mode
```

# Hardware Validation

- Board: ESP32-S3-Touch-AMOLED-2.06
- Firmware commit: unknown / unverified
- Connection: USB CDC / JTAG Serial to PC
- Expected output:
  - Successful QMI8658 initialization and WHOAMI read.
  - Serial JSON stream showing raw accelerometer peaks exceeding candidate thresholds.
  - Prompt "检测到异常，你现在安全吗？" rendered using LVGL.
  - Touch interaction logs outputting correct `user_confirmation` values (with raw serial outputs like `safe` or `help` mapped to the canonical `safe` / `needs_help` outcomes).
  - Recorded PC bridge event log contains structured safety records.
- Evidence path: unknown / unverified

# Decisions

- **Single-board scope for v0.1**: Bypassed dual-board UART/cellular integration to achieve a rapid, tangible demo-first loop using only the AMOLED board.
- **Mock GNSS/4G details**: Bypassed real cellular network registration to avoid indoor no-fix and network latency during Demo v0.1 validation.
- **Unified PC recording**: Relied on the PC-side development bridge to compile the final safety event record.

# Completion Evidence

- Changed files:
- Test result:
- Hardware result:
- Remaining risks: