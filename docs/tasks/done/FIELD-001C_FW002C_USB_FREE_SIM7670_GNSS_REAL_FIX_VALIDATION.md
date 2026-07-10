---
id: FIELD-001C
title: FW-002C USB-Free SIM7670G GNSS Real-Fix Validation
status: completed
priority: high
requires_hardware: true
created: 2026-06-28
last_updated: 2026-06-28

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/FIELD_TEST.md
  - docs/development/PROTOCOL.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - firmware/AGENTS.md
  - docs/tasks/done/RELIABILITY-001B_FW002C_USB_FREE_RESET_DIAGNOSTICS_VALIDATION.md

allowed_paths:
  - docs/current/
  - docs/development/
  - docs/hardware/
  - docs/tasks/
  - firmware/mqtt_heartbeat/
  - quality_tests/
  - reports/field_validation/

out_of_scope:
  - claiming SIM7670G LTE data transport
  - claiming battery accuracy or product power behavior
  - claiming final enclosure or final mounting GNSS acceptance
  - changing pin assignments or board wiring assumptions
  - flashing firmware without explicit operator intent
  - storing exact coordinates in current status docs
  - storing real VPS passwords, bearer tokens, Wi-Fi secrets, or private logs
---

# Problem

FW-002B proved firmware-side SIM7670G UART/AT no-fix diagnostics, and
RELIABILITY-001B made the FW-002C reset-diagnostics image stable enough for
field use. The next field gate was to prove a real `fix=true` GNSS report over
the USB-Free VPS Message Hub path.

# Expected Result

With the board on independent power and USB disconnected, place the GNSS antenna
near a window or outdoor sky view, issue `request_location` through the VPS
Message Hub, and accept the run only when the firmware reports `fix=true` with
parsed coordinates and `source_status=observed` or `verified`.

# Acceptance Criteria

- [x] Flashing is performed only after explicit operator confirmation.
- [x] Runtime validation uses independent power with USB disconnected.
- [x] Validation uses the VPS Message Hub command queue, not USB serial.
- [x] The device ACKs the `request_location` command.
- [x] The device uploads a `location_report` with `fix=true`.
- [x] Latitude and longitude fields are present in the saved evidence.
- [x] Fixed coordinates use `source_status=observed` or `verified`.
- [x] Evidence is written under ignored `reports/field_validation/`.

# Hardware Runs

## FW-002C fix2 window no-fix

- Firmware version: `0.1.0-fw002c-resetdiag-fix2`.
- Test run ID: `fw002c-resetdiag-fix2-20260627-182430`.
- Runtime connection path: `independent_power_usb_disconnected`.
- Evidence:
  - `reports/field_validation/fw002c-fix2-window-gnss-retry1-20260627-195000/field_validation_report.md`
- Result: FAIL.
- Summary: command/report/ACK path worked, but `fix=false` and
  `gnss_state=no_fix`.

## FW-002C fix2 window fixed but unaccepted metadata

- Firmware version: `0.1.0-fw002c-resetdiag-fix2`.
- Test run ID: `fw002c-resetdiag-fix2-20260627-182430`.
- Runtime connection path: `independent_power_usb_disconnected`.
- Evidence:
  - `reports/field_validation/fw002c-fix2-window-gnss-fix-unverified-20260628-092703/field_validation_report.md`
- Result: FAIL.
- Summary: command `cmd-000010`, `location_report seq=6920`, ACK `seq=6921`,
  `fix=true`, `gnss_state=fix`, and latitude/longitude fields present, but
  fixed coordinates were labeled `source_status=unverified`.

## FW-002C fix3 accepted real-fix run

- Board: `connectivity-node-001`, Waveshare ESP32-S3-SIM7670G-4G.
- Flash port: `COM4`, after explicit operator confirmation.
- Firmware version: `0.1.0-fw002c-resetdiag-fix3`.
- Test run ID: `fw002c-resetdiag-fix3-20260628-093000`.
- Runtime connection path: `independent_power_usb_disconnected`.
- Evidence:
  - `reports/field_validation/fw002c-fix3-window-gnss-20260628-093811/field_validation_report.md`
  - `reports/field_validation/fw002c-fix3-window-gnss-retry1-20260628-093946/field_validation_report.md`
  - `reports/field_validation/fw002c-fix3-window-gnss-retry1-20260628-093946/field_validation_report.json`
  - `reports/field_validation/fw002c-fix3-window-gnss-retry1-20260628-093946/test_run_export.json`
- Result: PASS on retry.
- Summary: the first fix3 request returned `gnss_state=at_unreachable` while
  the SIM7670G AT path was not ready. After a one-minute wait, the retry passed:
  fresh heartbeat `seq=30`, command `cmd-000012`, `location_report seq=31`,
  ACK `seq=33`, `fix=true`, `gnss_state=fix`,
  `source=sim7670g_firmware_gnss`, `source_status=observed`,
  `gnss_source=sim7670g_uart_at`, `gnss_driver=uart_at`, and
  `gnss_query_ok=true`.

# Firmware Fix

FW-002C fix3 changes the SIM7670G GNSS backend so parsed fixed coordinates use
`source_status=observed`; no-fix and unreachable states remain
`source_status=unverified`.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw002_gnss_scaffold quality_tests.test_fw002b_sim7670_gnss_firmware -v
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-fw002c-resetdiag-fix3 -TestRunId fw002c-resetdiag-fix3-20260628-093000 -BuildDir build_fw002c_resetdiag -PrepareBuild -EnableSim7670Gnss -Json
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-fw002c-resetdiag-fix3 -TestRunId fw002c-resetdiag-fix3-20260628-093000 -BuildDir build_fw002c_resetdiag -EnableSim7670Gnss -Flash -FlashPort COM4 -IUnderstandFlashWritesFirmware -Json
python scripts\validate_fw002_location_loop.py --hub http://203.0.113.10:8790 --device-id ego-link-r1-connectivity-001 --test-run-id fw002c-resetdiag-fix3-20260628-093000 --output-dir reports\field_validation\fw002c-fix3-window-gnss-retry1-20260628-093946 --timeout-sec 180 --poll-interval-sec 5 --require-fix
python scripts\context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files:
  - `docs/current/ACTIVE_BUILD.md`
  - `docs/current/STATUS.md`
  - `docs/development/PROTOCOL.md`
  - `docs/hardware/BOARD_MATRIX.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/FIELD-001C_FW002C_USB_FREE_SIM7670_GNSS_REAL_FIX_VALIDATION.md`
  - `firmware/mqtt_heartbeat/README.md`
  - `firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_gnss.c`
  - `quality_tests/test_fw002_gnss_scaffold.py`
  - `quality_tests/test_fw002b_sim7670_gnss_firmware.py`
  - `scripts/validate_fw002_location_loop.py`
- Build result:
  - FW-002C resetdiag fix3 build: PASS.
  - Firmware image:
    `firmware/mqtt_heartbeat/build_fw002c_resetdiag/egolink_mqtt_heartbeat.bin`.
- Hardware validation result:
  - FW-002C resetdiag fix3 USB-Free `--require-fix`: PASS on retry.
- Final validation result:
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
    237 tests.

# Remaining Risks

- The run validates GNSS fix over the Wi-Fi HTTP VPS Message Hub path; it does
  not prove SIM7670G LTE data transport.
- Battery accuracy, product power behavior, camera/GNSS/LTE product capability,
  and final enclosure/mounting GNSS acceptance remain unverified.
- Exact coordinates are retained only in ignored evidence exports, not copied
  into current status documents.
