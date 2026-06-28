---
id: FW-002A
title: GNSS Command/Telemetry Scaffold
status: completed
priority: high
requires_hardware: false
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
  - docs/tasks/done/FW-001-HW_REAL_DEVICE_USB_FREE_HEARTBEAT_VALIDATION.md

allowed_paths:
  - docs/current/
  - docs/development/
  - docs/tasks/
  - firmware/mqtt_heartbeat/
  - quality_tests/
  - scripts/
  - server/

out_of_scope:
  - flashing firmware
  - erasing flash
  - opening serial ports or starting serial captures
  - changing pin assignments or board wiring assumptions
  - implementing SIM7670G AT/GNSS hardware control
  - claiming real GNSS fix, LTE module control, battery accuracy, camera,
    audio, storage, or product power validation
  - storing real VPS passwords, bearer tokens, Wi-Fi secrets, or private logs
---

# Problem

R1 proved the real device can run USB-Free through the VPS Message Hub, but R2
GNSS work still needed a product-like command/telemetry path. The old GNSS
evidence came from a PC-side USB AT probe, which cannot serve as the outdoor
USB-Free acceptance path.

# Expected Result

Add a narrow FW-002A scaffold so the Message Hub can queue `request_location`,
firmware can upload one explicit `location_report`, and validation tooling can
prove the command/telemetry/ACK loop before a real SIM7670G GNSS driver is
integrated.

# Acceptance Criteria

- [x] `request_location` is documented as a P0 Message Hub command.
- [x] Firmware HTTP mode recognizes `request_location`.
- [x] Firmware uploads a `location_report` event before ACKing the command.
- [x] The scaffold report explicitly uses `fix=false`,
      `source_status=unverified`, and `gnss_state=driver_not_integrated`.
- [x] Host validation can queue `request_location`, wait for
      `location_report`, wait for ACK, and export JSON/Markdown evidence.
- [x] Dashboard field state shows fix, satellites, HDOP, and source status.
- [x] Default MQTT and HTTP Message Hub builds still pass.
- [x] No real hardware flash or USB-disconnected run is performed by this task.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw002_gnss_scaffold -v
python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_validation -v
python -m unittest quality_tests.test_fw001_hw_config -v
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build
powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName <operator-vps> -FwVersion 0.1.0-fw002-location-scaffold -TestRunId fw002-location-build-smoke -BuildDir build_fw002_location -Build -Json
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Board: not run in this task.
- Firmware image: build-verified only at
  `firmware/mqtt_heartbeat/build_fw002_location/egolink_mqtt_heartbeat.bin`.
- Connection path: not applicable; no flashing or hardware runtime validation.
- Evidence path: generated only when the operator flashes FW-002A and runs
  `scripts/validate_fw002_location_loop.py` against real hardware.

# Decisions

- `driver_not_integrated` is a scaffold state, not a real GNSS result.
- `fix=false` must be explicit so the Dashboard and report never confuse
  no-fix/no-driver with missing data.
- Real SIM7670G GNSS control remains a later firmware task and must preserve
  the `location_report` envelope.

# Completion Evidence

- Changed files:
  - `docs/development/PROTOCOL.md`
  - `docs/development/FIELD_TEST.md`
  - `docs/current/STATUS.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/FW-002A_GNSS_COMMAND_TELEMETRY_SCAFFOLD.md`
  - `firmware/mqtt_heartbeat/README.md`
  - `firmware/mqtt_heartbeat/main/Kconfig.projbuild`
  - `firmware/mqtt_heartbeat/main/app_main.c`
  - `quality_tests/test_fw001_hw_config.py`
  - `quality_tests/test_fw002_gnss_scaffold.py`
  - `quality_tests/test_message_hub_dashboard.py`
  - `quality_tests/test_message_hub_server.py`
  - `scripts/deploy_message_hub_vps.ps1`
  - `scripts/prepare_fw001_hw_config.ps1`
  - `scripts/validate_fw002_location_loop.py`
  - `server/message_hub.py`
- Validation result:
  - `python -m unittest quality_tests.test_fw002_gnss_scaffold -v`: PASS, 3 tests.
  - `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_validation -v`: PASS, 7 tests.
  - `python -m unittest quality_tests.test_fw001_hw_config -v`: PASS, 3 tests.
  - `python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v`: PASS, 8 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 222 tests.
  - Default MQTT ESP-IDF build: PASS, app binary size `0xd91b0`.
  - HTTP Message Hub ESP-IDF build: PASS, app binary size `0xdc3f0`, build dir `build_fw002_location`.
  - VPS redeploy: PASS, `egolink-message-hub.service` active and `/health` returned `ok=true`.
  - VPS deployment hygiene: PASS, deploy package now excludes `server/runtime`,
    remote app runtime directory is absent, and the service database remains in
    `/var/lib/egolink-message-hub/message_hub.db`.
- Remaining risks:
  - FW-002A was not flashed to real hardware in this build-scaffold task;
    subsequent USB-Free hardware validation is tracked separately as
    `FIELD-001A`.
  - Real GNSS fix, SIM7670G LTE/GNSS control, battery/charging accuracy,
    camera, audio, storage, and product power behavior remain unverified.
