---
id: FW-002B
title: SIM7670G Firmware GNSS AT Backend
status: completed
priority: high
requires_hardware: false
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - firmware/AGENTS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/DEV_FLOW.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/FW-002A_GNSS_COMMAND_TELEMETRY_SCAFFOLD.md

allowed_paths:
  - docs/current/
  - docs/development/
  - docs/hardware/
  - docs/tasks/
  - firmware/mqtt_heartbeat/
  - quality_tests/
  - scripts/

out_of_scope:
  - flashing firmware
  - USB-disconnected hardware validation
  - claiming outdoor GNSS fix
  - using SIM7670G LTE data transport
  - toggling unknown modem power/reset GPIOs
  - changing message protocol version
  - storing real VPS passwords, bearer tokens, Wi-Fi secrets, or private logs
---

# Problem

FW-002A proved the `request_location -> location_report -> ACK` Message Hub
path, but the firmware still reported `driver_not_integrated`. The next
walking-skeleton increment needs firmware-side SIM7670G GNSS querying behind
the same message contract before a USB-Free outdoor field run can validate real
fix behavior.

# Expected Result

Add an opt-in SIM7670G UART/AT GNSS backend to the connectivity-node firmware.
When enabled, `request_location` should query the SIM7670G module and upload a
diagnosable `location_report` with `source=sim7670g_firmware_gnss`,
`gnss_driver=uart_at`, no-fix/fix state, and bounded raw AT evidence.

# Acceptance Criteria

- [x] Default MQTT firmware behavior remains unchanged.
- [x] SIM7670G GNSS backend is Kconfig opt-in and defaults off.
- [x] Backend uses explicit Waveshare UART defaults: UART1, RX GPIO17,
      TX GPIO18, 115200 baud.
- [x] Backend sends bounded AT queries and parses `CGNSSINFO` / `CGPSINFO`
      coordinate responses.
- [x] `request_location` keeps the same `location_report` envelope.
- [x] Disabled/default path still preserves the FW-002A scaffold fallback.
- [x] Build helper and guarded runner can enable the FW-002B config without
      printing or storing runtime secrets.
- [x] Default ESP-IDF build passes.
- [x] HTTP + SIM7670G GNSS opt-in ESP-IDF build passes.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner quality_tests.test_fw002b_sim7670_gnss_firmware quality_tests.test_fw002_gnss_scaffold quality_tests.test_mqtt_heartbeat_firmware -v
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build build
powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-fw002b-sim7670-gnss -TestRunId fw002b-build-smoke -BuildDir build_fw002b_gnss -EnableSim7670Gnss -Build -Json
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Board: not exercised in this task.
- Firmware image:
  `firmware/mqtt_heartbeat/build_fw002b_gnss/egolink_mqtt_heartbeat.bin`.
- Firmware version: `0.1.0-fw002b-sim7670-gnss`.
- Connection path: not applicable; no flash or runtime validation was run.
- Evidence path: build output only; no field report.

# Completion Evidence

- Changed files:
  - `docs/current/ACTIVE_BUILD.md`
  - `docs/current/STATUS.md`
  - `docs/development/PROTOCOL.md`
  - `docs/hardware/BOARD_MATRIX.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/FW-002B_SIM7670G_FIRMWARE_GNSS_AT_BACKEND.md`
  - `firmware/mqtt_heartbeat/README.md`
  - `firmware/mqtt_heartbeat/components/sim7670_gnss/`
  - `firmware/mqtt_heartbeat/main/CMakeLists.txt`
  - `firmware/mqtt_heartbeat/main/app_main.c`
  - `firmware/mqtt_heartbeat/sdkconfig.vps_http.defaults.example`
  - `quality_tests/test_fw001_hw_config.py`
  - `quality_tests/test_fw001_hw_runner.py`
  - `quality_tests/test_fw002_gnss_scaffold.py`
  - `quality_tests/test_fw002b_sim7670_gnss_firmware.py`
  - `scripts/prepare_fw001_hw_config.ps1`
  - `scripts/run_fw001_hw_r1.ps1`
  - `scripts/validate_fw002_location_loop.py`
- Validation result:
  - FW-002B focused unit tests: PASS, 23 tests.
  - Default ESP-IDF build: PASS, app binary size `0xd91b0`.
  - HTTP + SIM7670G GNSS opt-in ESP-IDF build: PASS, app binary size
    `0xe1f50`.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
    229 tests.
- Remaining risks:
  - The FW-002B image was not flashed in this task.
  - UART access to the SIM7670G from firmware remains unverified on hardware.
  - Outdoor real GNSS fix remains unverified.
  - SIM7670G LTE data transport remains unverified for the Message Hub path.
