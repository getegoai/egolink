---
id: FW-001
title: Firmware Message Hub HTTP Client Baseline
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
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md

allowed_paths:
  - .gitignore
  - docs/current/
  - docs/tasks/
  - firmware/mqtt_heartbeat/
  - quality_tests/

out_of_scope:
  - flashing firmware
  - long serial captures
  - pin assignment changes
  - SIM7670G AT/GNSS control changes
  - protocol field changes
  - public server API changes
  - real GNSS, battery, camera, audio, or power validation claims
  - storing real VPS IPs, passwords, bearer tokens, or private device logs
---

# Problem

R1 needs connectivity-node firmware that can report status to the VPS Message
Hub without using USB serial as the runtime dependency. Before a hardware field
smoke run, the repository needed a buildable firmware path for that transport.

# Expected Result

`firmware/mqtt_heartbeat` keeps the existing local MQTT smoke path by default
and adds an opt-in HTTP Message Hub mode for boot registration, heartbeat,
telemetry upload, command polling, and ACK.

# Acceptance Criteria

- [x] Existing MQTT mode remains the default.
- [x] HTTP Message Hub mode is opt-in via Kconfig.
- [x] HTTP mode posts register/status/telemetry messages using
      `egolink.p0.v1`.
- [x] HTTP mode polls command queue and ACKs pending commands.
- [x] Firmware docs describe R1 boundaries and do not claim real GNSS.
- [x] Tests protect the new firmware contract.
- [x] Default MQTT build passes.
- [x] HTTP Message Hub opt-in build passes.

# Validation Commands

```powershell
python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_platform_power_firmware quality_tests.test_platform_imu_firmware -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build_fw001_http -D "SDKCONFIG=build_fw001_http/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.vps_http.defaults.example" build
```

# Hardware Validation

- Board: not run in this task.
- Firmware commit or image: build artifacts only, not flashed.
- Connection path: not applicable; runtime acceptance remains pending.
- Evidence path: not applicable.

# Completion Evidence

- Changed files:
  - `.gitignore`
  - `docs/current/STATUS.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/FW-001_FIRMWARE_MESSAGE_HUB_HTTP_CLIENT_BASELINE.md`
  - `firmware/mqtt_heartbeat/README.md`
  - `firmware/mqtt_heartbeat/main/CMakeLists.txt`
  - `firmware/mqtt_heartbeat/main/Kconfig.projbuild`
  - `firmware/mqtt_heartbeat/main/app_main.c`
  - `firmware/mqtt_heartbeat/sdkconfig.vps_http.defaults.example`
  - `quality_tests/test_mqtt_heartbeat_firmware.py`
- Validation result:
  - `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_platform_power_firmware quality_tests.test_platform_imu_firmware -v`: PASS, 19 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS, 207 tests.
  - Default MQTT ESP-IDF build: PASS, `egolink_mqtt_heartbeat.bin` size `0xd9170`.
  - HTTP Message Hub opt-in ESP-IDF build: PASS, `egolink_mqtt_heartbeat.bin` size `0xdbea0`.
- Remaining risks:
  - The firmware was not flashed or run on hardware in this task.
  - Real device USB-Free heartbeat and command ACK still require an
    operator-approved flash and field smoke run.
  - HTTP mode is still HTTP-only and should move behind HTTPS or a tunnel
    before longer public field trials.
  - The bearer token is a local build-time Kconfig value for now; real values
    must stay in ignored local sdkconfig files.
  - GNSS, LTE module control, battery, camera, audio, and product power
    behavior remain unverified by this task.
