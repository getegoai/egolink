---
id: FIELD-001B
title: FW-002B USB-Free SIM7670G GNSS AT Validation
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
  - docs/tasks/done/FW-002B_SIM7670G_FIRMWARE_GNSS_AT_BACKEND.md

allowed_paths:
  - docs/current/
  - docs/hardware/
  - docs/tasks/
  - firmware/mqtt_heartbeat/
  - quality_tests/
  - scripts/
  - reports/field_validation/

out_of_scope:
  - claiming real GNSS fix or real coordinates
  - claiming SIM7670G LTE data transport
  - changing pin assignments or board wiring assumptions
  - toggling unknown modem power/reset GPIOs
  - long serial captures
  - erasing flash
  - claiming battery accuracy, camera, audio, storage, or product power behavior
  - storing real VPS passwords, bearer tokens, Wi-Fi secrets, or private logs
---

# Problem

FW-002B added a build-verified SIM7670G firmware GNSS UART/AT backend, but it
still needed a real USB-Free hardware run to prove the backend could participate
in the VPS Message Hub `request_location -> location_report -> ACK` loop after
flashing.

# Expected Result

Flash the connectivity node with FW-002B, disconnect USB after independent
power is confirmed, then validate through the VPS Message Hub that
`request_location` produces a firmware-side SIM7670G GNSS AT `location_report`
and an ACK.

# Acceptance Criteria

- [x] Operator reconnects USB only for flashing.
- [x] FW-002B is flashed to the connectivity node on the named port.
- [x] Operator confirms independent power and USB disconnected before runtime
      validation.
- [x] VPS receives a fresh heartbeat from FW-002B fix1.
- [x] Message Hub queues `request_location`.
- [x] Firmware uploads `location_report`.
- [x] `location_report` includes `source=sim7670g_firmware_gnss`,
      `gnss_source=sim7670g_uart_at`, `gnss_driver=uart_at`,
      `gnss_query_ok=true`, `fix=false`, and `gnss_state=no_fix`.
- [x] Firmware ACKs the command.
- [x] JSON and Markdown evidence reports are written under ignored
      `reports/field_validation/`.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw002b_sim7670_gnss_firmware quality_tests.test_fw002_gnss_scaffold quality_tests.test_mqtt_heartbeat_firmware -v
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName <operator-vps> -FwVersion 0.1.0-fw002b-sim7670-gnss-fix1 -TestRunId fw002b-fix1-gnss-r1-20260627-163246 -BuildDir build_fw002b_gnss -PrepareBuild -EnableSim7670Gnss -Json
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName <operator-vps> -FwVersion 0.1.0-fw002b-sim7670-gnss-fix1 -TestRunId fw002b-fix1-gnss-r1-20260627-163246 -BuildDir build_fw002b_gnss -EnableSim7670Gnss -Flash -FlashPort COM4 -IUnderstandFlashWritesFirmware -Json
python scripts\validate_fw002_location_loop.py --hub http://<operator-vps>:8790 --device-id ego-link-r1-connectivity-001 --test-run-id fw002b-fix1-gnss-r1-20260627-163246 --timeout-sec 180 --poll-interval-sec 5 --json
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Board: `connectivity-node-001`, Waveshare ESP32-S3-SIM7670G-4G.
- Firmware image:
  `firmware/mqtt_heartbeat/build_fw002b_gnss/egolink_mqtt_heartbeat.bin`.
- Firmware version: `0.1.0-fw002b-sim7670-gnss-fix1`.
- Device ID: `ego-link-r1-connectivity-001`.
- Flash path: `COM4`; ESP32-S3 detected, MAC `02:00:00:00:00:03`, image hash
  verification passed, hard reset completed.
- Runtime connection path: `independent_power_usb_disconnected`, confirmed by
  the operator before validation.
- Test run ID: `fw002b-fix1-gnss-r1-20260627-163246`.
- Evidence path:
  - `reports/field_validation/fw002b-fix1-gnss-r1-20260627-163246/field_validation_report.md`
  - `reports/field_validation/fw002b-fix1-gnss-r1-20260627-163246/field_validation_report.json`
  - `reports/field_validation/fw002b-fix1-gnss-r1-20260627-163246/test_run_export.json`

# Decisions

- The first FW-002B hardware validation attempt used firmware
  `0.1.0-fw002b-sim7670-gnss` and test run
  `fw002b-gnss-r1-20260627-155211`. The device reached the VPS and uploaded
  status/sensor messages, but `request_location` command `cmd-000005` remained
  `pending` and no `location_report` appeared.
- The command path was patched by increasing the command-poll task stack to
  `COMMAND_POLL_TASK_STACK_SIZE=12288`, because the command handler combines
  command polling, JSON parsing, a large location payload, and SIM7670G AT
  response buffers.
- This task accepts `no_fix` only as firmware GNSS driver bring-up evidence.
  It is not R2 real-GNSS acceptance.

# Completion Evidence

- Changed files:
  - `docs/current/ACTIVE_BUILD.md`
  - `docs/current/STATUS.md`
  - `docs/hardware/BOARD_MATRIX.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/FIELD-001B_FW002B_USB_FREE_SIM7670_GNSS_AT_VALIDATION.md`
  - `firmware/mqtt_heartbeat/main/app_main.c`
  - `quality_tests/test_fw002b_sim7670_gnss_firmware.py`
- Build and flash result:
  - `scripts\run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670Gnss`: PASS.
  - `scripts\run_fw001_hw_r1.ps1 -Flash -FlashPort COM4`: PASS.
  - ESP32-S3 was detected, bootloader/app/partition table writes completed,
    hashes were verified, and hard reset completed.
- Hardware result:
  - `scripts\validate_fw002_location_loop.py`: PASS.
  - Message Hub health returned `ok=true`.
  - Fresh heartbeat observed: status `seq=57`.
  - Command queued: `request_location`, command ID `cmd-000006`.
  - Location report observed: event `seq=58`, `source=sim7670g_firmware_gnss`,
    `gnss_source=sim7670g_uart_at`, `gnss_driver=uart_at`,
    `gnss_query_ok=true`, `fix=false`, `gnss_state=no_fix`,
    `raw_command=AT+CGPSINFO`.
  - ACK observed: `seq=59`, status `ok`.
- Validation result:
  - `python -m unittest quality_tests.test_fw002b_sim7670_gnss_firmware quality_tests.test_fw002_gnss_scaffold quality_tests.test_mqtt_heartbeat_firmware -v`: PASS, 14 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
    230 tests.
- Remaining risks:
  - Real GNSS fix and real coordinates remain unverified.
  - SIM7670G LTE data transport remains unverified for the Message Hub path.
  - Battery/charging accuracy, camera, audio, storage, and product power
    behavior remain unverified by this task.
