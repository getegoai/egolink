---
id: MODEL-DEVICE-006
title: Tiny Safety hardware flash validation
status: done
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
  - docs/tasks/done/MODEL-DEVICE-006_TINY_SAFETY_HARDWARE_FLASH_VALIDATION.md
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
- [x] Identify the connectivity-node ESP32 console port without relying on a
      hardcoded COM port.
- [x] If the board/port identity is clear, flash only the connectivity node
      with the guarded `-IUnderstandFlashWritesFirmware` command.
- [x] Run bounded serial Tiny Safety CLI validation after flash, or record why
      it is blocked/deferred.
- [x] Run a short post-flash read-only D1 Web/API or observer check, or record
      why it is blocked/deferred.
- [x] Record board, port, firmware image/version, commit, timestamp, evidence
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
- 2026-07-07 after operator reconnected the 4G board:
  - Board probe report:
    `reports/board_validation/20260707-202343/probe.md`.
  - Probe result: `esp32_ch343_serial_present=FAIL`,
    `sim7670_usb_serial_present=FAIL`, `sim7670_rndis_adapter_present=FAIL`,
    and `sim7670_at_identity=FAIL`.
  - A follow-up 5-minute port poll saw `COM9` disappear, leaving only `COM1`
    and `COM3`; no connectivity-node USB device was enumerated.
  - Flash remains deferred because no safe connectivity-node target port is
    visible.
- 2026-07-07 after operator replug attempt 2:
  - Board probe report:
    `reports/board_validation/20260707-210839/probe.md`.
  - Probe again reported no CH343 ESP32 console, no SIM7670G USB serial ports,
    no RNDIS adapter, and no AT identity.
  - ESP-IDF `esptool` identity check on the only USB serial port, `COM9`,
    returned ESP32-S3 MAC `02:00:00:00:00:01` in USB-Serial/JTAG mode.
  - This does not match the connectivity-node MAC recorded in current build
    evidence (`02:00:00:00:00:03`), so `COM9` is not accepted as the 4G board
    flash target.
- 2026-07-07 cold boot after the operator reseated the 4G board:
  - Board probe report:
    `reports/board_validation/20260707-coldboot-after-flash/20260707-213153/probe.md`.
  - Connectivity-node target identified as CH343 ESP32 console `COM4`
    (`USB\VID_1A86&PID_55D3`) with SIM7670G USB serial ports `COM5`-`COM8`.
  - SIM7670G AT identity passed on `COM6` and `COM7` with model
    `SIM7670G-MNGV`, `CPIN READY`, CSQ `20,0`, registered=true, and
    attached=true.
  - Guarded flash to `COM4` completed earlier in this hardware session after
    the port identity matched the connectivity-node MAC `02:00:00:00:00:03`.
    The flashed firmware app version observed on boot is commit `cf5b4a6`.
- 2026-07-07 post-flash serial Tiny Safety CLI validation:
  - Report:
    `reports/tiny_safety_firmware_cli/MODEL-DEVICE-006-hw-20260707-serial-cli-transcript2/tiny_safety_cli_report.md`.
  - Result: `pass`; 8 guarded `safety tiny ...` commands were written to
    `COM4`, all required markers were observed, model identity matched
    `MODEL-DEVICE-001-tiny-safety-v0-20260707`, synthetic selftest passed,
    and SOS/cancel remained `safety_rule_required`.
- 2026-07-07 controlled reset capture after the cold boot:
  - Metadata:
    `reports/board_validation/20260707-model-device-006-reset-log/capture_meta.json`.
  - Log:
    `reports/board_validation/20260707-model-device-006-reset-log/com4_reset_capture.log`.
  - Capture action: bounded reset/log capture only; no additional flash or
    configuration change was performed.
  - Boot log observed `MESSAGE_HUB_BOOT`, `SAFETY_MODEL_INIT_OK`, LTE ready
    with `registered_home`/PDP active, command diagnostic POST HTTP 200,
    `LTE_HTTP_LOCATION_RAW_POST_DONE` HTTP 200, and
    `LTE_HTTP_LOCATION_OBSERVATION_RAW_POST_DONE` HTTP 200.
- 2026-07-07 post-reset Web/API and observer evidence:
  - Web/API report:
    `reports/d1_web_api/MODEL-DEVICE-006-hw-20260707-post-flash-web/d1_web_api_report.md`.
  - Final observer report:
    `reports/d1_field_observation/MODEL-DEVICE-006-hw-20260707-after-reset-observer/d1_field_observation_report.md`.
  - Server state after reset showed firmware
    `0.1.0-model-device-006-tiny-safety-hw`, test run ID
    `MODEL-DEVICE-006-hw-20260707-d1`, fresh LTE command diagnostics, and raw
    D1 periodic `location_report`/`location_observation` frames with matching
    firmware/test-run IDs.
  - Observer result: `PASS`, 3/3 samples, max freshness 67 s, latest device
    upload advanced to `2026-07-07T13:41:28.438646+00:00`, raw POST success
    delta `2`, and raw POST failure delta `0`.
- Current hardware result:
  `done_tiny_safety_firmware_flashed_and_short_web_observed`.
- Non-claims: this task does not claim real-world model accuracy, latency, RAM,
  flash delta, GNSS accuracy, battery life, long LTE stability, product
  readiness, real SMS/call/dispatch/external escalation, or final power
  behavior.
