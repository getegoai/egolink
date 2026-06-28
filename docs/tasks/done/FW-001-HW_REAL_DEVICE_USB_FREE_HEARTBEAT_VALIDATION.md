---
id: FW-001-HW
title: Real Device USB-Free Heartbeat Validation
status: completed
priority: high
requires_hardware: true
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md
  - docs/development/FIELD_TEST.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - firmware/AGENTS.md
  - docs/tasks/done/FW-001_FIRMWARE_MESSAGE_HUB_HTTP_CLIENT_BASELINE.md
  - docs/tasks/done/FW-001-HW-PREP_R1_USB_FREE_VALIDATION_KIT.md
  - docs/tasks/done/FW-001-HW-CONFIG_R1_LOCAL_CONFIG_AND_BUILD.md
  - docs/tasks/done/FW-001-HW-RUNNER_R1_GUARDED_HARDWARE_RUNNER.md

allowed_paths:
  - docs/current/
  - docs/hardware/
  - docs/tasks/
  - reports/field_validation/

out_of_scope:
  - firmware logic changes
  - protocol or schema changes
  - changing pin assignments or board wiring assumptions
  - erasing flash
  - long serial captures
  - SIM7670G AT/GNSS control changes
  - claiming real GNSS fix, LTE module control, battery accuracy, camera,
    audio, storage, or product power validation
  - storing real VPS passwords, bearer tokens, Wi-Fi secrets, or private logs
---

# Problem

The Walking Skeleton needed a real connectivity-node proof that did not depend
on a USB cable at runtime. FW-001 and the host-side preparation tasks had
already created the opt-in HTTP Message Hub firmware, local ignored VPS config,
build artifact, guarded runner, and validation script. The remaining risk was
whether the real board could boot on independent power, reach the operator VPS
Message Hub, publish a fresh heartbeat, receive a command, and ACK it after USB
was disconnected.

# Expected Result

Flash the R1 connectivity node with the local ignored HTTP Message Hub firmware
image, then validate the USB-Free Message Hub path through the operator VPS
using only server-side observation after the operator confirms independent
power and USB disconnect.

# Acceptance Criteria

- [x] Firmware flashing is explicitly operator-confirmed and uses a named port.
- [x] The validation run starts only after the operator confirms independent
      power and USB disconnected.
- [x] Message Hub `/health` is reachable during the run.
- [x] A fresh status heartbeat is observed for the expected device and test
      run.
- [x] The server queues one harmless `set_report_interval` command.
- [x] The firmware ACKs that command through the Message Hub.
- [x] JSON and Markdown evidence reports are written under the ignored
      field-validation report directory.
- [x] Tracked docs do not store real tokens, passwords, Wi-Fi secrets, or
      private device logs.

# Validation Commands

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName <operator-vps> -TestRunId fw001-hw-r1-20260627-133813 -Flash -FlashPort COM4 -IUnderstandFlashWritesFirmware -Json
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName <operator-vps> -TestRunId fw001-hw-r1-20260627-133813 -Validate -OperatorConfirmedIndependentPower -OperatorConfirmedUsbDisconnected -Json
python scripts/context_lint.py
```

# Hardware Validation

- Board: `connectivity-node-001`, Waveshare ESP32-S3-SIM7670G-4G.
- Firmware image: `firmware/mqtt_heartbeat/build_fw001_hw/egolink_mqtt_heartbeat.bin`.
- Firmware version: `0.1.0-fw001-hw-r1`.
- Device ID: `ego-link-r1-connectivity-001`.
- Flash path: `COM4`; ESP32-S3 detected and image hash verification passed.
- Runtime connection path: `independent_power_usb_disconnected`, confirmed by
  the operator before validation.
- Test run ID: `fw001-hw-r1-20260627-133813`.
- Evidence path:
  - `reports/field_validation/fw001-hw-r1-20260627-133813/field_validation_report.md`
  - `reports/field_validation/fw001-hw-r1-20260627-133813/field_validation_report.json`
  - `reports/field_validation/fw001-hw-r1-20260627-133813/test_run_export.json`

# Decisions

- USB remains a flashing and emergency-debug path only; runtime acceptance for
  this milestone is based on the Message Hub observation path.
- This task validates the Wi-Fi HTTP Message Hub link, not SIM7670G LTE data
  transport.
- Mock payload fields emitted by the firmware remain explicitly mock and are
  not upgraded to real GNSS, battery, or modem evidence by this task.

# Completion Evidence

- Changed files:
  - `docs/current/ACTIVE_BUILD.md`
  - `docs/current/STATUS.md`
  - `docs/hardware/BOARD_MATRIX.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/FW-001-HW_REAL_DEVICE_USB_FREE_HEARTBEAT_VALIDATION.md`
- Flash result:
  - `scripts\run_fw001_hw_r1.ps1 -Flash -FlashPort COM4`: PASS.
  - ESP32-S3 was detected, bootloader/app/partition table writes completed,
    hashes were verified, and hard reset completed.
- Hardware result:
  - `scripts\run_fw001_hw_r1.ps1 -Validate ...`: PASS.
  - Message Hub health returned `ok=true`.
  - Fresh heartbeat observed: status `seq=7`.
  - Command queued: `set_report_interval`, command ID `cmd-000003`.
  - ACK observed: status `ok`, ACK `seq=8`.
- Validation result:
  - `python scripts/context_lint.py`: PASS.
- Remaining risks:
  - GNSS fix, SIM7670G LTE module control, real battery/charging data, camera,
    audio, storage, and product power behavior are not validated by FW-001-HW.
  - The firmware transport is still HTTP for the P0 field-test skeleton and
    should move behind HTTPS or a tunnel before longer public trials.
