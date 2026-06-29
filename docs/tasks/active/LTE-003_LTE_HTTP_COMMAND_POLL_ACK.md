---
title: LTE HTTP Command Poll And ACK
task_id: LTE-003
status: active
last_verified: 2026-06-29
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

## Fix1 Runtime Attempt

- Firmware version: `0.1.0-lte003-command-loop-fix1`
- Test run ID: `lte003-command-loop-fix1-20260628-223454`
- Validator mode: reused existing pending `cmd-000013` through
  `--existing-command-id cmd-000013`.
- Evidence:
  `reports/field_validation/lte003-command-loop-fix1-20260628-223454/lte_command_loop_report.json`
- Result: FAIL.
- Validator started at: `2026-06-28T23:38:11.832669+00:00`
- Validator completed at: `2026-06-28T23:44:13.137142+00:00`
- Command: `cmd-000013`, `set_report_interval`.
- Failure: command remained `pending`; no ACK was received.
- The test-run export contained 37 `lte_http_command_diag` messages from
  `2026-06-28T23:25:04.981401+00:00` to
  `2026-06-28T23:30:02.130747+00:00`, before the validator wait window. This
  shows the fix1 image booted after flash, reached LTE readiness, and posted
  diagnostic telemetry, but it does not prove the later USB-Free validation
  window had an active command loop.
- Diagnostic summary: one `phase=ready` event and 36 `phase=poll_no_ack`
  events. Latest diagnostic event had `fw_version=0.1.0-lte003-command-loop-fix1`,
  `lte.reason_code=LTE_READY`, `transport.type=lte`,
  `lte_http.poll_status_code=200`, `lte_http.poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_FAILED`.
- Interpretation: fix1 turned the prior silent failure into an explainable
  failure. The command poll HTTP action reached the Message Hub and received a
  200 response body, but firmware failed to read/parse the SIM7670G
  `HTTPREAD` response. The immediate suspect is the component
  `AT_RESPONSE_BUFFER_SIZE=512`, which is smaller than the observed poll body
  length plus SIMCom `HTTPREAD` framing.

## Fix2 Direction

- Increase the SIM7670 AT response buffer from `512` to `1536` bytes so
  command-poll `HTTPREAD` can hold the observed 592-byte response body plus
  SIMCom framing.
- Keep `lte_http_command_task` at `16384` stack from fix1.
- Require a cold boot with USB disconnected after flashing fix2 so the command
  loop runs during the USB-Free validation window.

## Fix2 Build Evidence

- Firmware version: `0.1.0-lte003-command-loop-fix2`
- Test run ID: `lte003-command-loop-fix2-20260629-074709`
- Build directory: `firmware/mqtt_heartbeat/build_lte003_command_loop_fix2/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix2/egolink_mqtt_heartbeat.bin`
- Binary size: `291440` bytes.
- Build result: PASS through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670LteHttpCommandLoop`.
- Build config confirmed
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`,
  `CONFIG_EGOLINK_FW_VERSION="0.1.0-lte003-command-loop-fix2"`, and
  `CONFIG_EGOLINK_TEST_RUN_ID="lte003-command-loop-fix2-20260629-074709"`.
- Focused LTE/firmware tests passed with 24 tests before build.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  274 tests.
- `git diff --check` passed.
- Flash result: PASS on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
- Flash evidence:
  `reports/field_validation/lte003-command-loop-fix2-20260629-074709/flash_report.md`
- USB-Free runtime validation: FAIL as recorded in the fix2 runtime attempt.

## Fix2 Runtime Attempt

- Firmware version: `0.1.0-lte003-command-loop-fix2`
- Test run ID: `lte003-command-loop-fix2-20260629-074709`
- Validator mode: reused existing pending `cmd-000013` through
  `--existing-command-id cmd-000013`.
- Connection path: independent power, USB disconnected, operator-confirmed,
  with a cold reboot in that state before validation.
- Evidence:
  `reports/field_validation/lte003-command-loop-fix2-20260629-074709/lte_command_loop_report.json`
- Result: FAIL.
- Validator started at: `2026-06-28T23:58:07.293905+00:00`
- Validator completed at: `2026-06-29T00:04:07.563167+00:00`
- Command: `cmd-000013`, `set_report_interval`.
- Failure: command remained `pending`; no ACK was received.
- The test-run export contained 51 `lte_http_command_diag` messages from
  `2026-06-28T23:55:12.777828+00:00` to
  `2026-06-29T00:02:30.235865+00:00`.
- Diagnostic summary: two `phase=ready` events and 49 `phase=poll_no_ack`
  events. The latest diagnostic event had
  `fw_version=0.1.0-lte003-command-loop-fix2`, `seq=37`,
  `lte_http.poll_status_code=200`, `lte_http.poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_FAILED`.
- Interpretation: fix2 confirms the image boots, LTE is usable, diagnostics
  reach the VPS over SIM7670G LTE HTTP, and `/commands/poll` returns HTTP 200
  with a body. Increasing `AT_RESPONSE_BUFFER_SIZE` to `1536` did not resolve
  the command-body read path. The next useful firmware increment should make
  `AT+HTTPREAD` wait with the longer HTTP action timeout and split this failure
  into AT-read versus JSON-body parse reason codes.

## Fix3 Direction

- Use `CONFIG_EGOLINK_SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS` for the
  command-poll `AT+HTTPREAD` call in `sim7670_lte_http_get_json`.
- Replace the single `LTE_HTTP_READ_FAILED` result for HTTP 2xx command polls
  with:
  - `LTE_HTTP_READ_AT_FAILED` when the `AT+HTTPREAD` command does not return a
    usable AT response.
  - `LTE_HTTP_READ_BODY_PARSE_FAILED` when `AT+HTTPREAD` returns but the JSON
    body cannot be extracted.
- Keep acceptance strict: LTE-003 still passes only when the command is ACKed
  with `transport.type=lte`, `lte_http.phase=command_ack`, and
  `poll_reason_code=LTE_HTTP_OK`.

## Fix6 Build Evidence

- Firmware version: `0.1.0-lte003-command-loop-fix6`
- Test run ID: `lte003-command-loop-fix6-20260629-160859`
- Source fix commit: `c1a90a0`
- Flashed repo/app version: `8d7395f`
- Build directory: `firmware/mqtt_heartbeat/build_lte003_command_loop_fix6/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix6/egolink_mqtt_heartbeat.bin`
- Binary size: `292512` bytes.
- Build result: PASS through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670LteHttpCommandLoop`.
- Build config confirmed
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`,
  `CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=1`,
  `CONFIG_EGOLINK_FW_VERSION="0.1.0-lte003-command-loop-fix6"`, and
  `CONFIG_EGOLINK_TEST_RUN_ID="lte003-command-loop-fix6-20260629-160859"`.
- Focused LTE/firmware tests passed with 24 tests.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  274 tests.
- `git diff --check` passed.
- Flash result: PASS on `COM4` after explicit operator confirmation.
- Flash evidence:
  `reports/field_validation/lte003-command-loop-fix6-20260629-160859/flash_report.md`
- USB-Free runtime validation: FAIL as recorded in the fix6 runtime attempt.

## Fix6 Runtime Attempt

- Firmware version: `0.1.0-lte003-command-loop-fix6`
- Test run ID: `lte003-command-loop-fix6-20260629-160859`
- Validator mode: reused existing pending `cmd-000013` through
  `--existing-command-id cmd-000013`.
- Connection path: independent power, USB disconnected, operator-confirmed.
- Evidence:
  `reports/field_validation/lte003-command-loop-fix6-20260629-160859/lte_command_loop_report.json`
- Result: FAIL.
- Validator started at: `2026-06-29T08:31:32.859080+00:00`
- Validator completed at: `2026-06-29T08:37:33.374450+00:00`
- Command: `cmd-000013`, `set_report_interval`.
- Failure: command remained `pending`; no ACK was received.
- The test-run export contained 37 `lte_http_command_diag` messages from
  `2026-06-29T08:18:30.645153+00:00` to
  `2026-06-29T08:23:32.840189+00:00`.
- Diagnostic summary: one `phase=ready` event and 36 `phase=poll_no_ack`
  events. Latest diagnostic event had `fw_version=0.1.0-lte003-command-loop-fix6`,
  `lte.reason_code=LTE_READY`, registration `registered_home`, assigned IP
  `10.75.55.162`, `transport.type=lte`, `lte_http.poll_status_code=200`,
  `lte_http.poll_data_len=592`, `lte_http.poll_reason_code=LTE_HTTP_OK`, and
  empty `command.last_cmd_id`.
- Interpretation: fix6 advanced the blocker from HTTPREAD body extraction to
  command extraction/ACK. LTE, VPS, HTTPACTION, and HTTPREAD body capture are
  healthy enough to return `LTE_HTTP_OK`, but the firmware still does not select
  and ACK a command from the polled body.
- Fix7 direction: add command parser diagnostics such as parse status and
  command count, and increase the bounded poll window so validation is less
  dependent on catching the boot-time command-loop window.
- Keep acceptance strict: LTE-003 still passes only when the command is ACKed
  with `transport.type=lte`, `lte_http.phase=command_ack`, and
  `poll_reason_code=LTE_HTTP_OK`.

## Fix5 Build Evidence

- Firmware version: `0.1.0-lte003-command-loop-fix5`
- Test run ID: `lte003-command-loop-fix5-20260629-154839`
- Source/build app commit: `729c78b`
- Build directory: `firmware/mqtt_heartbeat/build_lte003_command_loop_fix5/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix5/egolink_mqtt_heartbeat.bin`
- Binary size: `291872` bytes.
- Build result: PASS through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670LteHttpCommandLoop`.
- Build config confirmed
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`,
  `CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=1`,
  `CONFIG_EGOLINK_FW_VERSION="0.1.0-lte003-command-loop-fix5"`, and
  `CONFIG_EGOLINK_TEST_RUN_ID="lte003-command-loop-fix5-20260629-154839"`.
- Focused LTE/firmware tests passed with 24 tests.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  274 tests.
- `git diff --check` passed.
- Flash result: PASS on `COM4` after explicit operator confirmation.
- Flashed repo/app version: `efc9848`
- Flash evidence:
  `reports/field_validation/lte003-command-loop-fix5-20260629-154839/flash_report.md`
- USB-Free runtime validation: FAIL as recorded in the fix5 runtime attempt.

## Fix5 Runtime Attempt

- Firmware version: `0.1.0-lte003-command-loop-fix5`
- Test run ID: `lte003-command-loop-fix5-20260629-154839`
- Validator mode: reused existing pending `cmd-000013` through
  `--existing-command-id cmd-000013`.
- Connection path: independent power, USB disconnected, operator-confirmed.
- Evidence:
  `reports/field_validation/lte003-command-loop-fix5-20260629-154839/lte_command_loop_report.json`
- Result: FAIL.
- Validator started at: `2026-06-29T07:58:34.971916+00:00`
- Validator completed at: `2026-06-29T08:04:36.479750+00:00`
- Command: `cmd-000013`, `set_report_interval`.
- Failure: command remained `pending`; no ACK was received.
- The test-run export contained 37 `lte_http_command_diag` messages from
  `2026-06-29T07:54:20.574708+00:00` to
  `2026-06-29T07:59:29.170356+00:00`.
- Diagnostic summary: one `phase=ready` event and 36 `phase=poll_no_ack`
  events. The latest diagnostic event had
  `fw_version=0.1.0-lte003-command-loop-fix5`, `seq=37`,
  `lte.reason_code=LTE_READY`, `lte.registration_state=registered_home`,
  assigned IP `10.75.55.162`, `lte_http.poll_status_code=200`,
  `lte_http.poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_BODY_PARSE_FAILED`.
- Interpretation: fix5 did not prove LTE command polling/ACK. Falling through
  from positional HTTPREAD to bare HTTPREAD did not change the runtime failure:
  the firmware still reaches LTE, reaches the VPS, receives a 200 poll
  response, and gets an AT-level HTTPREAD response, but it still does not
  capture an extractable JSON body.

## Fix6 Direction

- Add an HTTPREAD-specific UART collection path that does not return as soon
  as the generic AT helper sees `OK`; it should keep reading until the JSON
  body is captured or the HTTP action timeout expires.
- Keep acceptance strict: LTE-003 still passes only when the command is ACKed
  with `transport.type=lte`, `lte_http.phase=command_ack`, and
  `poll_reason_code=LTE_HTTP_OK`.

## Fix3 Build Evidence

- Firmware version: `0.1.0-lte003-command-loop-fix3`
- Test run ID: `lte003-command-loop-fix3-20260629-081529`
- Fix3 code-change commit: `e79e4de`
- Initial build app version before flash: `e79e4de`
- Flashed build app version after the guarded flash re-ran CMake at HEAD:
  `79a12c8`
- Build directory: `firmware/mqtt_heartbeat/build_lte003_command_loop_fix3/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix3/egolink_mqtt_heartbeat.bin`
- Binary size: `291488` bytes.
- Build result: PASS through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670LteHttpCommandLoop`.
- Build config confirmed
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`,
  `CONFIG_EGOLINK_FW_VERSION="0.1.0-lte003-command-loop-fix3"`, and
  `CONFIG_EGOLINK_TEST_RUN_ID="lte003-command-loop-fix3-20260629-081529"`.
- Focused LTE/firmware tests passed with 24 tests before commit.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  274 tests.
- `git diff --check` passed.
- Flash result: PASS on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
- Flash started at: `2026-06-29T00:22:01.0021679Z`
- Flash completed at: `2026-06-29T00:22:36.3004908Z`
- Flash evidence:
  `reports/field_validation/lte003-command-loop-fix3-20260629-081529/flash_report.md`
- USB-Free runtime validation: FAIL as recorded in the fix3 runtime attempt.

## Fix3 Runtime Attempt

- Firmware version: `0.1.0-lte003-command-loop-fix3`
- Test run ID: `lte003-command-loop-fix3-20260629-081529`
- Validator mode: reused existing pending `cmd-000013` through
  `--existing-command-id cmd-000013`.
- Connection path: independent power, USB disconnected, operator-confirmed,
  with a cold reboot in that state before validation.
- Evidence:
  `reports/field_validation/lte003-command-loop-fix3-20260629-081529/lte_command_loop_report.json`
- Result: FAIL.
- Validator started at: `2026-06-29T00:26:51.247061+00:00`
- Validator completed at: `2026-06-29T00:32:53.249979+00:00`
- Command: `cmd-000013`, `set_report_interval`.
- Failure: command remained `pending`; no ACK was received.
- The test-run export contained 59 `lte_http_command_diag` messages from
  `2026-06-29T00:22:45.045416+00:00` to
  `2026-06-29T00:31:02.529394+00:00`.
- Diagnostic summary: two `phase=ready` events and 57 `phase=poll_no_ack`
  events. The latest diagnostic event had
  `fw_version=0.1.0-lte003-command-loop-fix3`, `seq=37`,
  `lte_http.poll_status_code=200`, `lte_http.poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_AT_FAILED`.
- Interpretation: fix3 did not prove LTE command polling/ACK. It did prove the
  failure is narrower than before: the device boots the fix3 image, LTE and
  VPS telemetry work, and `/commands/poll` reaches HTTP 200 with a 592-byte
  body, but the firmware does not get a usable `AT+HTTPREAD` response.

## Fix4 Direction

- Do not continue with timeout-only retries; fix3 already used the longer LTE
  HTTP action timeout for `AT+HTTPREAD`.
- Add a SIM7670G HTTPREAD strategy that can try bounded positional reads such
  as `AT+HTTPREAD=0,<data_len>` for command-poll GET responses.
- Keep raw command/response data out of normal telemetry, but expose enough
  reason detail to distinguish `AT+HTTPREAD` returning `ERROR`, timing out,
  or returning data without a JSON body.
- Keep acceptance strict: LTE-003 still passes only when the command is ACKed
  with `transport.type=lte`, `lte_http.phase=command_ack`, and
  `poll_reason_code=LTE_HTTP_OK`.

## Fix4 Build Evidence

- Firmware version: `0.1.0-lte003-command-loop-fix4`
- Test run ID: `lte003-command-loop-fix4-20260629-084350`
- Source/build app commit: `c8e1f59`
- Build directory: `firmware/mqtt_heartbeat/build_lte003_command_loop_fix4/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix4/egolink_mqtt_heartbeat.bin`
- Binary size: `291872` bytes.
- Build result: PASS through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670LteHttpCommandLoop`.
- Build config confirmed
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`,
  `CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=1`,
  `CONFIG_EGOLINK_FW_VERSION="0.1.0-lte003-command-loop-fix4"`, and
  `CONFIG_EGOLINK_TEST_RUN_ID="lte003-command-loop-fix4-20260629-084350"`.
- Focused LTE/firmware tests passed with 24 tests before and after the
  compile-order amend.
- `python scripts/context_lint.py` passed before and after the amend.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  274 tests before the amend; the amend only added a C `static` forward
  declaration needed by the ESP-IDF compiler.
- `git diff --check` passed.
- Flash result: PASS on `COM4` after explicit operator confirmation.
- Flashed repo/app version: `b4eaa44`
- Flash evidence:
  `reports/field_validation/lte003-command-loop-fix4-20260629-084350/flash_report.md`
- USB-Free runtime validation: FAIL as recorded in the fix4 runtime attempt.

## Fix4 Runtime Attempt

- Firmware version: `0.1.0-lte003-command-loop-fix4`
- Test run ID: `lte003-command-loop-fix4-20260629-084350`
- Validator mode: reused existing pending `cmd-000013` through
  `--existing-command-id cmd-000013`.
- Connection path: independent power, USB disconnected, operator-confirmed.
- Evidence:
  `reports/field_validation/lte003-command-loop-fix4-20260629-084350/lte_command_loop_report.json`
- Result: FAIL.
- Validator started at: `2026-06-29T07:38:00.750934+00:00`
- Validator completed at: `2026-06-29T07:44:00.985827+00:00`
- Command: `cmd-000013`, `set_report_interval`.
- Failure: command remained `pending`; no ACK was received.
- The test-run export contained 37 `lte_http_command_diag` messages from
  `2026-06-29T07:33:18.286132+00:00` to
  `2026-06-29T07:38:27.035179+00:00`.
- Diagnostic summary: one `phase=ready` event and 36 `phase=poll_no_ack`
  events. The latest diagnostic event had
  `fw_version=0.1.0-lte003-command-loop-fix4`, `seq=37`,
  `lte.reason_code=LTE_READY`, `lte.registration_state=registered_home`,
  assigned IP `10.75.55.162`, `lte_http.poll_status_code=200`,
  `lte_http.poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_BODY_PARSE_FAILED`.
- Interpretation: fix4 did not prove LTE command polling/ACK, but it changed
  the failure from `LTE_HTTP_READ_AT_FAILED` to
  `LTE_HTTP_READ_BODY_PARSE_FAILED`. The firmware now reaches LTE, reaches the
  VPS, receives a 200 poll response, and gets past the positional HTTPREAD AT
  command, but it still does not extract a JSON body to execute and ACK the
  command.

## Fix5 Direction

- When `AT+HTTPREAD=0,<data_len>` returns `OK` but does not yield an
  extractable JSON body, continue to the bare `AT+HTTPREAD` fallback instead
  of immediately returning `LTE_HTTP_READ_BODY_PARSE_FAILED`.
- Keep acceptance strict: LTE-003 still passes only when the command is ACKed
  with `transport.type=lte`, `lte_http.phase=command_ack`, and
  `poll_reason_code=LTE_HTTP_OK`.
