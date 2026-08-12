---
id: FW-006
title: Deploy the FW-005 GNSS correctness image to the connectivity node
status: active
priority: high
requires_hardware: true
serves_demo: D2-D5
created: 2026-08-12
last_updated: 2026-08-12

context:
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/development/DEV_FLOW.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/tasks/active/FW-005_SIM7670_GNSS_COORDINATE_RESPONSE_CORRECTNESS.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_gnss.c
  - quality_tests/AGENTS.md

allowed_paths:
  - docs/tasks/active/FW-006_GNSS_CORRECTNESS_HARDWARE_UPDATE.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - firmware/mqtt_heartbeat/build_*
  - firmware/mqtt_heartbeat/sdkconfig.*.local
  - reports/

out_of_scope:
  - firmware source or protocol changes
  - flash erase, NVS erase, modem configuration, APN changes, or device commands
  - repeated flashing, indefinite serial monitoring, or field acceptance claims
  - VPS deployment, Dashboard changes, or historical database mutation
---

# Goal

Build a clean, identifiable FIELD-011-compatible image containing FW-005 and
replace the current connectivity-node image once on COM3.

# Acceptance Criteria

- [ ] A clean ESP-IDF 5.4.2 build retains the verified FIELD-011 LTE/GNSS/QMI
      profile and records exact bootloader/partition/app hashes.
- [ ] Exactly one COM3 flash writes the three normal image regions without
      erase-flash or NVS overwrite, and esptool verifies every write.
- [ ] One bounded 20-second startup capture shows the expected app identity,
      real QMI8658 probe/idle-stop, and no panic, brownout, or reset loop.
- [ ] Current-build documentation records the new image honestly; corrected
      coordinate parsing is not claimed as hardware-verified until a later
      complete GNSS fix response is observed.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw002b_sim7670_gnss_firmware quality_tests.test_sim7670_gnss_probe quality_tests.test_sim7670_gnss_parser -v
python scripts\context_lint.py
git diff --check
```

# Hardware Validation

- Board: connectivity-node-001, Waveshare ESP32-S3-SIM7670G-4G, PCB revision unknown
- Connection: CH343 ESP32 console COM3
- Operator authorization: update the attached device firmware
- Limits: one flash and one 20-second startup capture; stop on heat, smell,
  disconnect loop, write verification failure, panic, brownout, or reset loop
- Evidence path: `reports/firmware_validation/FW-006-20260812-001/`

# Completion Evidence

- Build/image:
- Flash/startup:
- Remaining risks:

# Builder Prompt

```text
Read docs/tasks/active/FW-006_GNSS_CORRECTNESS_HARDWARE_UPDATE.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md,
quality_tests/AGENTS.md, this packet, and its context entries. Rebuild the
existing FIELD-011 profile from committed FW-005, flash COM3 exactly once, and
capture exactly one bounded 20-second startup log. Obey allowed_paths and
out_of_scope; never erase flash/NVS or change modem settings. Return exact image
hashes, hardware evidence paths, validation results, and remaining risks.
```
