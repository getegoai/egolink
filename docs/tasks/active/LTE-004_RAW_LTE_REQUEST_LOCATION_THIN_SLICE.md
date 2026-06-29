---
id: LTE-004
title: Raw LTE Request Location Thin Slice
status: completed
priority: high
requires_hardware: true
created: 2026-06-29
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/FIELD_TEST.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/FW-003_RAW_FRAME_LTE_COMMAND_LOOP.md
  - docs/tasks/done/RAW-LTE-REPEAT-001_SHORT_USB_FREE_RAW_LTE_REPEAT.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md
  - shared/contracts/message_hub_raw_frame_record.schema.json

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/active/LTE-004_RAW_LTE_REQUEST_LOCATION_THIN_SLICE.md
  - docs/tasks/active/LTE-003_LTE_HTTP_COMMAND_POLL_ACK.md
  - docs/tasks/done/RAW-LTE-REPEAT-001_SHORT_USB_FREE_RAW_LTE_REPEAT.md
  - firmware/mqtt_heartbeat/README.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - server/message_hub.py
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/run_fw001_hw_r1.ps1
  - scripts/validate_lte_command_loop.py
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_fw001_hw_runner.py
  - quality_tests/test_lte_command_loop_validation.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_mqtt_heartbeat_firmware.py

out_of_scope:
  - flashing firmware without explicit operator confirmation
  - long LTE stability or reconnect testing
  - product LTE acceptance
  - product GNSS acceptance or final enclosure/mounting GNSS comparison
  - battery, charging, power, camera, audio, or storage acceptance
  - modifying GitLab or unrelated VPS services
---

# LTE-004 Raw LTE Request Location Thin Slice

## Goal

Extend the proven FW-003 raw LTE command/ACK loop from one harmless
`set_report_interval` command to one product-relevant `request_location`
command:

```text
Web/VPS command queue
-> LTE HTTP raw command frame
-> firmware queries GNSS backend or explicit no-fix scaffold
-> LTE HTTP raw event frame for location_report
-> server stores raw frame first and derives Web/API location_report
-> LTE HTTP raw ACK
```

This is the next Walking Skeleton step after RAW-LTE-REPEAT-001. It keeps raw
frames as the device/server wire truth and treats JSON as the server/Web
derived view.

## Acceptance

- [x] Message Hub derives `location_report` fields from `EGLK/1 type=event`
      key/value raw frames while retaining raw payload bytes.
- [x] Firmware raw LTE command loop accepts `request_location` in addition to
      `set_report_interval`.
- [x] Firmware uploads a raw-frame `location_report` over SIM7670G LTE HTTP
      before ACKing `request_location`.
- [x] Host validator can require a matching `location_report` and LTE ACK for
      the same command ID.
- [x] Focused firmware/server/validator tests pass.
- [x] `python scripts/context_lint.py` passes.
- [x] `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passes if
      behavior changes.
- [x] ESP-IDF guarded prepare/build passes before any flash request.
- [x] USB-Free runtime validation passes for raw LTE
      `request_location -> location_report -> ACK`.

## Build And Deploy Evidence

- VPS Message Hub deployed to `203.0.113.10:8790` on 2026-06-29 without
  touching GitLab.
- VPS raw-location smoke:
  `lte004-vps-raw-location-smoke-20260629-133701`; derived
  `event_type=location_report`, `fix=false`, `gnss_state=no_fix`,
  `transport.type=lte`, and
  `location_request_cmd_id=cmd-smoke-000001`.
- Firmware build:
  `0.1.0-lte004-raw-lte-location` /
  `lte004-raw-lte-location-20260629-213717`.
- Binary:
  `firmware/mqtt_heartbeat/build_lte004_raw_lte_location/egolink_mqtt_heartbeat.bin`
  (`296112` bytes).
- Validation:
  focused firmware/server/validator/runner tests: 36 passed;
  `python scripts/context_lint.py`: PASS;
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: 282 tests OK;
  `git diff --check`: PASS;
  guarded ESP-IDF prepare/build: PASS.

## Hardware Plan

- Firmware version target: `0.1.0-lte004-raw-lte-location`.
- Test run ID: `lte004-raw-lte-location-20260629-213717`.
- Build dir target: `build_lte004_raw_lte_location`.
- Flash port: `COM4`; flashed after explicit operator confirmation on
  2026-06-30.
- Runtime validation: independent power with USB disconnected, operator
  confirmed and completed on 2026-06-30.

## Flash Evidence

- Board probe: `reports/board_validation/20260630-075007/probe.md`.
- Flash report:
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/flash_report.md`.
- Source/app commit: `1b1fd3a`.
- Result: PASS; ESP32-S3 detected, bootloader/app/partition table written,
  hashes verified, hard reset completed.
- Boundary: flash evidence only; runtime evidence is recorded below.

## Runtime Evidence

- Validator:
  `scripts/run_fw001_hw_r1.ps1` with `-Validate`,
  `-LteCommandName request_location`, and `-RequireLteLocationReport`.
- Result: PASS.
- Command: `cmd-000020` / `request_location`.
- Location report: `seq=30`, raw frame `loc-cmd-000020`,
  `transport.type=lte`, `lte_http.phase=location_report`,
  `source=sim7670g_firmware_gnss`, `source_status=unverified`,
  `gnss_query_ok=true`, `gnss_state=no_fix`, `fix=false`, and
  `location_request_cmd_id=cmd-000020`.
- ACK: `seq=31`, `transport.type=lte`, `lte_http.phase=command_ack`,
  `LTE_HTTP_OK` / HTTP `200`, `poll_action_elapsed_ms=560`,
  `command.parse_status=raw_command_selected`, command status `ok`, and ACK
  status `ok`.
- Evidence:
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/lte_command_loop_report.json`,
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/lte_command_loop_report.md`,
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/device_state.json`,
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/commands.json`,
  and
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/test_run_export.json`.

## Completion Boundary

LTE-004 proves only a bounded raw LTE `request_location -> location_report ->
ACK` thin-slice. A no-fix report is acceptable for this transport slice if the
failure is explicit. It does not validate outdoor GNSS real-fix performance,
long LTE stability, reconnect recovery, battery/power behavior, enclosure
behavior, or product readiness.
