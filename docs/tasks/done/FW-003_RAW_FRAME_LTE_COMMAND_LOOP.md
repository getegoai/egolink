---
id: FW-003
title: Raw Frame LTE Command Loop
status: completed
priority: high
requires_hardware: true
created: 2026-06-29
last_updated: 2026-06-29

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/STATUS.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/PROTO-002_RAW_FRAME_TRANSPORT_CONTRACT.md
  - docs/tasks/active/LTE-003_LTE_HTTP_COMMAND_POLL_ACK.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md
  - shared/contracts/message_hub_raw_frame_record.schema.json

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/FW-003_RAW_FRAME_LTE_COMMAND_LOOP.md
  - docs/tasks/active/LTE-003_LTE_HTTP_COMMAND_POLL_ACK.md
  - firmware/mqtt_heartbeat/README.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/include/sim7670_gnss.h
  - firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_gnss.c
  - firmware/mqtt_heartbeat/main/app_main.c
  - server/message_hub.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_mqtt_heartbeat_firmware.py

out_of_scope:
  - firmware flashing without explicit operator confirmation
  - USB-Free runtime validation before a build-verified image exists
  - changing GitLab or unrelated VPS services
  - removing existing JSON APIs or Wi-Fi development paths
  - long LTE stability, reconnect, battery, enclosure, or GNSS acceptance
---

# FW-003 Raw Frame LTE Command Loop

## Goal

Move the LTE-003 command poll/ACK firmware path from JSON command bodies to
PROTO-002 HTTP-carried raw frames. The firmware should poll
`/commands/poll.raw`, verify the `EGLK/1` frame length and CRC32, parse compact
key/value command payloads, and ACK through `/ack.raw`.

## Scope

- Keep `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED` as the opt-in
  firmware mode.
- Keep Wi-Fi disabled while this command-loop mode is enabled.
- Add SIM7670G AT HTTP helpers for raw GET and raw POST without removing the
  existing JSON helpers used by diagnostics and earlier slices.
- Build a raw ACK frame that preserves firmware version, test-run ID, LTE HTTP
  poll status, command parse status, and duplicate-execution evidence.
- Keep Message Hub JSON command/ACK views as derived compatibility state.

## Acceptance

- [x] Focused firmware and server tests pass.
- [x] `python scripts/context_lint.py` passes.
- [x] `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passes if
      behavior changes.
- [x] ESP-IDF guarded prepare/build passes with LTE HTTP command loop enabled.
- [x] Flash happens only after the operator explicitly confirms the COM port.
- [x] USB-Free runtime validation passes with independent power and USB
      disconnected.

## Hardware Validation Plan

- Board: Waveshare ESP32-S3-SIM7670G-4G connectivity node.
- Firmware image:
  `firmware/mqtt_heartbeat/build_fw003_raw_command_loop/egolink_mqtt_heartbeat.bin`
  (`286176` bytes).
- Firmware version: `0.1.0-fw003-raw-command-loop`.
- Test run ID: `fw003-raw-command-loop-20260629-175608`.
- Flash port: `COM4`, after explicit operator confirmation.
- Connection path: USB serial flashing through CH343 ESP32 console on COM4;
  runtime validation still requires independent power with USB disconnected.
- Evidence path:
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/flash_report.md`.

## Validation Notes

- `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_message_hub_server -v`
  passed with 24 tests.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  278 tests.
- `git diff --check` passed.
- Guarded ESP-IDF prepare/build passed with LTE HTTP command loop enabled.
- The VPS Message Hub was redeployed after raw ACK derived LTE evidence was
  added. Public smoke `fw003-raw-derived-smoke-20260629-175946` created
  `cmd-000016`, fetched an `EGLK/1 type=command` frame, posted a raw ACK with
  `parse_result.status=ok`, updated the command to `ok`, and derived
  `ack.transport.type=lte`, `ack.lte_http.phase=command_ack`, and
  `ack.lte_http.poll_status_code=200`.
- Flash on `COM4` passed: ESP32-S3 detected, bootloader/app/partition table
  written, hashes verified, and hard reset completed.
- USB-Free runtime validation passed after independent-power cold boot with USB
  disconnected. Validator created `cmd-000017` (`set_report_interval`) and
  observed raw-frame ACK `seq=5` with `transport.type=lte`,
  `lte_http.phase=command_ack`, `lte_http.poll_reason_code=LTE_HTTP_OK`,
  `lte_http.poll_status_code=200`, `lte_http.poll_action_elapsed_ms=450`,
  `command.parse_status=raw_command_selected`, `command.command_count=1`, and
  command status `ok`.
- Runtime evidence files:
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/lte_command_loop_report.json`,
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/lte_command_loop_report.md`,
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/device_state.json`,
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/commands.json`, and
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/test_run_export.json`.

## Completion Boundary

FW-003 validates the USB-Free Message-First raw command/ACK loop only. It does
not validate long LTE stability, reconnect recovery, GNSS-over-LTE,
battery/power behavior, enclosure behavior, or product readiness.
