---
id: FIELD-001A
title: FW-002A USB-Free Location Scaffold Validation
status: completed
priority: high
requires_hardware: true
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/FIELD_TEST.md
  - docs/development/PROTOCOL.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - firmware/AGENTS.md
  - docs/tasks/done/FW-002A_GNSS_COMMAND_TELEMETRY_SCAFFOLD.md

allowed_paths:
  - docs/current/
  - docs/hardware/
  - docs/tasks/
  - quality_tests/
  - scripts/
  - reports/field_validation/

out_of_scope:
  - implementing SIM7670G AT/GNSS firmware control
  - claiming real GNSS fix or real coordinates
  - claiming SIM7670G LTE data transport
  - changing pin assignments or board wiring assumptions
  - long serial captures
  - erasing flash
  - claiming battery accuracy, camera, audio, storage, or product power behavior
  - storing real VPS passwords, bearer tokens, Wi-Fi secrets, or private logs
---

# Problem

FW-002A added a build-verified `request_location` scaffold, but it still needed
a real USB-Free hardware run to prove the command/telemetry path on the
connectivity node after flashing.

# Expected Result

Flash the connectivity node with FW-002A, disconnect USB after independent
power is confirmed, then validate through the VPS Message Hub that
`request_location` produces one explicit no-fix `location_report` and an ACK.

# Acceptance Criteria

- [x] Operator reconnects USB only for flashing.
- [x] FW-002A is flashed to the connectivity node on the named port.
- [x] Operator confirms independent power and USB disconnected before runtime
      validation.
- [x] VPS receives a fresh heartbeat from FW-002A.
- [x] Message Hub queues `request_location`.
- [x] Firmware uploads `location_report`.
- [x] `location_report` includes `fix=false`,
      `source_status=unverified`, and
      `gnss_state=driver_not_integrated`.
- [x] Firmware ACKs the command.
- [x] JSON and Markdown evidence reports are written under ignored
      `reports/field_validation/`.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName <operator-vps> -FwVersion 0.1.0-fw002-location-scaffold -TestRunId fw002-location-r1-20260627-150515 -BuildDir build_fw002_location -PrepareBuild -Flash -FlashPort COM4 -IUnderstandFlashWritesFirmware -Json
python scripts\validate_fw002_location_loop.py --hub http://<operator-vps>:8790 --device-id ego-link-r1-connectivity-001 --test-run-id fw002-location-build-smoke --timeout-sec 180 --poll-interval-sec 5 --json
```

# Hardware Validation

- Board: `connectivity-node-001`, Waveshare ESP32-S3-SIM7670G-4G.
- Firmware image:
  `firmware/mqtt_heartbeat/build_fw002_location/egolink_mqtt_heartbeat.bin`.
- Firmware version: `0.1.0-fw002-location-scaffold`.
- Device ID: `ego-link-r1-connectivity-001`.
- Flash path: `COM4`; ESP32-S3 detected, MAC `02:00:00:00:00:03`, image hash
  verification passed, hard reset completed.
- Runtime connection path: `independent_power_usb_disconnected`, confirmed by
  the operator before validation.
- Test run ID: `fw002-location-build-smoke`.
- Evidence path:
  - `reports/field_validation/fw002-location-build-smoke/field_validation_report.md`
  - `reports/field_validation/fw002-location-build-smoke/field_validation_report.json`
  - `reports/field_validation/fw002-location-build-smoke/test_run_export.json`

# Decisions

- This task accepts `driver_not_integrated` only as scaffold evidence. It is
  not R2 real-GNSS acceptance.
- The first validation attempt used the intended test run
  `fw002-location-r1-20260627-150515`, but the running firmware reported the
  older `fw002-location-build-smoke` ID because the existing ESP-IDF build
  directory kept a stale `sdkconfig`. The validation was rerun against the
  actual firmware `test_run_id`, and the prepare script now removes stale
  build-dir `sdkconfig` before build.

# Completion Evidence

- Changed files:
  - `docs/current/ACTIVE_BUILD.md`
  - `docs/current/STATUS.md`
  - `docs/hardware/BOARD_MATRIX.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/FIELD-001A_FW002A_USB_FREE_LOCATION_SCAFFOLD_VALIDATION.md`
  - `docs/tasks/done/FW-002A_GNSS_COMMAND_TELEMETRY_SCAFFOLD.md`
  - `quality_tests/test_fw001_hw_config.py`
  - `quality_tests/test_fw001_hw_runner.py`
  - `scripts/prepare_fw001_hw_config.ps1`
  - `scripts/run_fw001_hw_r1.ps1`
- Flash result:
  - `scripts\run_fw001_hw_r1.ps1 -PrepareBuild -Flash -FlashPort COM4`: PASS.
  - ESP32-S3 was detected, bootloader/app/partition table writes completed,
    hashes were verified, and hard reset completed.
- Hardware result:
  - `scripts\validate_fw002_location_loop.py`: PASS.
  - Message Hub health returned `ok=true`.
  - Fresh heartbeat observed: status `seq=3`.
  - Command queued: `request_location`, command ID `cmd-000004`.
  - Location report observed: event `seq=4`, `fix=false`,
    `gnss_state=driver_not_integrated`, `source_status=unverified`.
  - ACK observed: `seq=5`, status `ok`.
- Validation result:
  - `python -m unittest quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner -v`: PASS, 9 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 223 tests.
- Remaining risks:
  - The test run ID is named `fw002-location-build-smoke` because the first
    FW-002A image reused a stale build-dir sdkconfig. The runner/build tooling
    is fixed for future clean field IDs, but this task did not reflash a second
    FW-002A image after USB was disconnected.
  - Real GNSS fix, SIM7670G LTE/GNSS control, battery/charging accuracy,
    camera, audio, storage, and product power behavior remain unverified.
