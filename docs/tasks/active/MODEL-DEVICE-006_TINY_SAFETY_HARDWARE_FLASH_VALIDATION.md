---
id: MODEL-DEVICE-006
title: Tiny Safety hardware flash validation
status: active
priority: high
requires_hardware: true
serves_demo: D5
created: 2026-07-07
last_updated: 2026-07-07

context:
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/DEV_FLOW.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/safety/SAFETY_CONTRACT.md
  - docs/tasks/done/MODEL-DEVICE-005_TINY_SAFETY_DEVICE_LOOP_RUNNER.md

allowed_paths:
  - firmware/mqtt_heartbeat/
  - scripts/
  - quality_tests/
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/tasks/active/MODEL-DEVICE-006_TINY_SAFETY_HARDWARE_FLASH_VALIDATION.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - mapping model output to real SMS, calls, dispatch, or external escalation
  - changing shared contracts, public protocol fields, pin assignments, or board identity
  - training a new model or reading private field samples
  - claiming real-world model accuracy, latency, RAM, flash, power, battery life, GNSS accuracy, or product readiness
  - touching VPS GitLab or deploying unrelated server changes
---

# Goal

Serve D5 by building the Tiny Safety D1 firmware image, flashing it to the
connectivity node only with an explicit guarded command, and collecting bounded
hardware evidence that the `safety tiny ...` CLI runs on the board.

# Acceptance Criteria

- [x] Build the MODEL-DEVICE-005 D1 Tiny Safety firmware image.
- [ ] Identify the connectivity-node ESP32 console port without relying on a
      hardcoded COM port.
- [ ] If the board/port identity is clear, flash only the connectivity node
      with the guarded `-IUnderstandFlashWritesFirmware` command.
- [ ] Run bounded serial Tiny Safety CLI validation after flash, or record why
      it is blocked/deferred.
- [ ] Run a short post-flash read-only D1 Web/API or observer check, or record
      why it is blocked/deferred.
- [ ] Record board, port, firmware image/version, commit, timestamp, evidence
      path, validation commands, and non-claims.

# Validation Commands

```powershell
python -m unittest quality_tests.test_tiny_safety_device_loop quality_tests.test_tiny_safety_firmware_cli_validator -v
python scripts/context_lint.py
git diff --check
```

Run full verify if tracked source, script, contract, or firmware behavior is
changed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- User confirmed they can cooperate with hardware on 2026-07-07.
- Flashing still must use the guarded command and must target the identified
  connectivity-node ESP32 console, not the AMOLED board.
- Runtime product evidence remains USB-Free/Web-based; serial evidence is only
  debug/flash validation.

# Progress Evidence

- 2026-07-07 build-only pass:
  - Command: `scripts\run_fw001_hw_r1.ps1 ... -PrepareBuild -Json`
  - Firmware version: `0.1.0-model-device-006-tiny-safety-hw`
  - Test run ID: `MODEL-DEVICE-006-hw-20260707-d1`
  - Binary:
    `firmware/mqtt_heartbeat/build_model_device_006_tiny_safety/egolink_mqtt_heartbeat.bin`
  - Binary size: `321248` bytes
  - SHA-256:
    `4061161F59CB1F7056633E5316FE020E9EDA6C9042ED8643C880512A30DCDDAE`
  - Build features: SIM7670G GNSS, LTE status, LTE HTTP command loop,
    location observation, D1 periodic location, MAX17048 power, Tiny Safety CLI.
- 2026-07-07 port enumeration:
  - Present ports: `COM1`, `COM3`, `COM9`.
  - `COM9` is `USB\VID_303A&PID_1001`, matching the Espressif USB
    Serial/JTAG class used by the AMOLED board in current bench notes.
  - No CH343/connectivity-node ESP32 console or SIM7670G USB AT ports were
    enumerated during a 3-minute poll, so flash is deferred to avoid writing
    the AMOLED board.
- Current hardware result: `blocked_waiting_for_connectivity_node_usb_data_port`.
- Non-claims: no firmware flash, serial Tiny Safety validation, USB-Free D1
  Web check, latency/RAM/flash/power measurement, model accuracy, GNSS
  accuracy, battery-life, call/SMS, or release-readiness claim is made by the
  build-only pass.
