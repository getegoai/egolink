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
- Runtime validation: failed twice with independent power and USB disconnected.
  `cmd-000013` remained pending and no LTE-003 messages reached the Message
  Hub.

## Validation So Far

- `python -m unittest quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_lte_command_loop_validation -v`
  passed with 28 tests.
- `python scripts/context_lint.py` passed after the task packet was opened.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  272 tests.
- `git diff --check` passed.

## Validation Attempt 1

- Firmware version: `0.1.0-lte003-command-loop`
- Test run ID: `lte003-command-loop-20260628-210214`
- Connection path: independent power, USB disconnected, operator-confirmed.
- Evidence:
  `reports/field_validation/lte003-command-loop-20260628-210214/lte_command_loop_report.json`
- Result: FAIL.
- Started at: `2026-06-28T13:52:07.704903+00:00`
- Completed at: `2026-06-28T13:58:13.028117+00:00`
- Command: `cmd-000013`, `set_report_interval`.
- Failure: command remained `pending`; no ACK was received, no ACK transport
  evidence existed, and the test-run export contained zero messages.
- VPS state still showed the prior LTE-002 fix5 `lte_http_probe` as latest
  telemetry and did not show a fresh LTE-003 message during the validation
  window.
- Interpretation: LTE-003 has not passed runtime validation. The next lowest
  risk retry is to keep the pending command and power-cycle the independently
  powered device with USB disconnected, then run the validator in
  `--existing-command-id cmd-000013` mode. This tests whether the first failure
  was caused by the bounded boot-time command loop completing before the
  command was queued.

## Validator Update After Attempt 1

- `scripts/validate_lte_command_loop.py` now supports
  `--existing-command-id` so a pending command can be reused across a manual
  independent-power reboot without enqueueing another command.
- `python scripts/context_lint.py` passed.
- `python -m unittest quality_tests.test_lte_command_loop_validation -v`
  passed with 4 tests.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  273 tests after the validator update.
- `git diff --check` passed.

## Validation Attempt 2

- Firmware version: `0.1.0-lte003-command-loop`
- Test run ID: `lte003-command-loop-20260628-210214`
- Connection path: independent power, USB disconnected, operator-confirmed.
- Operator action before retry: independent-power cold reboot with USB still
  disconnected.
- Validator mode: reused existing pending `cmd-000013` through
  `--existing-command-id cmd-000013`.
- Evidence:
  `reports/field_validation/lte003-command-loop-20260628-210214/lte_command_loop_report_attempt2_existing_cmd.json`
- Result: FAIL.
- Started at: `2026-06-28T14:21:51.694056+00:00`
- Completed at: `2026-06-28T14:27:53.800834+00:00`
- Command: `cmd-000013`, `set_report_interval`.
- Failure: command remained `pending`; no ACK was received, no ACK transport
  evidence existed, and the test-run export contained zero messages.
- VPS device state still showed the prior LTE-002 fix5 `lte_http_probe` as
  latest telemetry with `server_received_at=2026-06-28T12:37:04.490795+00:00`
  and `fw_version=0.1.0-lte002-lte-http-probe-fix5`.
- Interpretation: the failure is not a Web display issue and is no longer
  explained by the command being queued after an already-completed boot-time
  command loop. The LTE-003 firmware image did not produce any fresh LTE-003
  Message Hub traffic during the USB-Free retry window. The next useful step is
  USB-attached bounded firmware console diagnosis on `COM4` to identify whether
  the device is booting the expected image, reaching LTE readiness, issuing
  HTTP GET `/commands/poll`, or failing before/inside the SIM7670G HTTP path.

## Fix1 Direction

- Add compact `lte_http_command_diag` telemetry posted through SIM7670G LTE
  HTTP before and after command polling so a USB-Free run can distinguish
  image boot/LTE-ready, poll failure, poll-empty, and ACK-missing states.
- Increase `lte_http_command_task` stack from `12288` to `16384` to preserve
  margin around the `response[2048]`, cJSON parse, and SIM7670G AT HTTP call
  path.
- Keep acceptance strict: diagnostic telemetry is not a substitute for an ACK;
  LTE-003 still passes only when `cmd-000013` or a fresh harmless command is
  ACKed with `transport.type=lte` and `lte_http.phase=command_ack`.

## Fix1 Build Evidence

- Firmware version: `0.1.0-lte003-command-loop-fix1`
- Test run ID: `lte003-command-loop-fix1-20260628-223454`
- Build directory: `firmware/mqtt_heartbeat/build_lte003_command_loop_fix1/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix1/egolink_mqtt_heartbeat.bin`
- Build result: PASS through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670LteHttpCommandLoop`.
- Build config confirmed
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`,
  `CONFIG_EGOLINK_FW_VERSION="0.1.0-lte003-command-loop-fix1"`, and
  `CONFIG_EGOLINK_TEST_RUN_ID="lte003-command-loop-fix1-20260628-223454"`.
- `python scripts/context_lint.py` passed.
- `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner quality_tests.test_lte_command_loop_validation -v`
  passed with 29 tests.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  273 tests.
- `git diff --check` passed.
- Flash result: PASS on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
- Flash evidence:
  `reports/field_validation/lte003-command-loop-fix1-20260628-223454/flash_report.md`
- USB-Free runtime validation: not run yet. Requires independent power and USB
  disconnected.
