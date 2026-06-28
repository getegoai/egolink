---
title: LTE HTTP Command Poll And ACK
task_id: LTE-003
status: active
last_verified: 2026-06-28
context:
  - docs/current/ACTIVE_BUILD.md
  - docs/current/STATUS.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/LTE-002_LTE_HTTP_UPLINK_THIN_SLICE.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md
  - scripts/run_fw001_hw_r1.ps1
allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/active/LTE-003_LTE_HTTP_COMMAND_POLL_ACK.md
  - firmware/mqtt_heartbeat/README.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/Kconfig.projbuild
  - firmware/mqtt_heartbeat/components/sim7670_gnss/include/sim7670_gnss.h
  - firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_gnss.c
  - firmware/mqtt_heartbeat/main/app_main.c
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/run_fw001_hw_r1.ps1
  - scripts/validate_lte_command_loop.py
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_fw001_hw_runner.py
  - quality_tests/test_lte_command_loop_validation.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
---

# LTE-003 LTE HTTP Command Poll And ACK

## Goal

Prove that the current Message Hub command queue can be polled by the
ESP32-S3 through the SIM7670G LTE HTTP stack, and that the device can ACK one
harmless command back through the same LTE HTTP path with USB disconnected at
runtime.

## Scope

- Add an opt-in firmware mode:
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED`.
- Keep Wi-Fi disabled while LTE command loop mode is enabled.
- Use SIM7670G AT HTTP `GET` for
  `/api/v1/devices/{device_id}/commands/poll`.
- Execute and ACK one harmless `set_report_interval` command.
- Include additive LTE transport evidence on the ACK payload so the validator
  can distinguish LTE ACK from the earlier Wi-Fi Message Hub path.
- Add a Message Hub-side validator that creates a test run, enqueues the
  harmless command, waits for the ACK, checks `transport.type=lte`, and writes
  evidence under ignored `reports/field_validation/`.

## Out Of Scope

- Do not run a long LTE stability or reconnect gate.
- Do not claim product LTE acceptance, reconnect recovery, battery, charging,
  product power behavior, or enclosure GNSS acceptance.
- Do not make `request_location` over LTE a required acceptance gate in this
  task; GNSS-over-LTE can follow after the basic command ACK link is proven.
- Do not replace the default MQTT path or the existing Wi-Fi HTTP development
  path.
- Do not modify GitLab or unrelated VPS services.

## Operator Actions Required

1. Connect the connectivity node back to USB.
2. Confirm the flash port explicitly, expected currently `COM4`.
3. After flashing, connect independent power and disconnect USB.
4. Confirm USB-Free runtime before validation starts.

## Acceptance

- Firmware builds with SIM7670G LTE status and LTE HTTP command loop enabled.
- The flashed device runs without USB as a runtime data path.
- Wi-Fi is disabled by firmware mode during LTE command polling.
- The Web/Message Hub command queue receives a harmless `set_report_interval`
  command for the expected `test_run_id`.
- The device polls the command over LTE HTTP and returns an ACK with
  `status=ok`.
- The stored ACK includes `transport.type=lte`, LTE HTTP poll/ACK status, and
  the expected firmware/test-run IDs.
- Duplicate local execution of the same command ID is avoided inside the
  LTE command loop; timeout and stale pending command states remain visible in
  the validator report and Message Hub command list.

## Validation Plan

- Focused unit tests for firmware static boundaries and the LTE-003 validator.
- `python scripts/context_lint.py`.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` if firmware or
  validation behavior changes.
- ESP-IDF build through the guarded runner before any flash request.

## Build Evidence So Far

- Firmware version: `0.1.0-lte003-command-loop`
- Test run ID: `lte003-command-loop-20260628-210214`
- Build directory: `firmware/mqtt_heartbeat/build_lte003_command_loop/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte003_command_loop/egolink_mqtt_heartbeat.bin`
- Build result: PASS through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670LteHttpCommandLoop`.
- Flash result: PASS on `COM4`; ESP32-S3 detected, bootloader/app/partition
  table written, hashes verified, and hard reset completed.
- Flash evidence:
  `reports/field_validation/lte003-command-loop-20260628-210214/flash_report.md`
- Runtime validation: not run. Requires independent power and USB disconnected
  after flashing.

## Validation So Far

- `python -m unittest quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_lte_command_loop_validation -v`
  passed with 28 tests.
- `python scripts/context_lint.py` passed after the task packet was opened.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  272 tests.
- `git diff --check` passed.
