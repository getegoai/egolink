---
id: FW-001-HW-PREP
title: R1 USB-Free Validation Kit
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
  - firmware/mqtt_heartbeat/README.md

allowed_paths:
  - docs/current/
  - docs/tasks/
  - docs/development/
  - firmware/mqtt_heartbeat/
  - quality_tests/
  - scripts/
  - server/
  - shared/contracts/

out_of_scope:
  - flashing firmware
  - erasing flash
  - long serial captures
  - changing pin assignments or board wiring assumptions
  - SIM7670G AT/GNSS control changes
  - real GNSS, LTE, battery, camera, audio, or product power validation claims
  - storing real VPS IPs, passwords, bearer tokens, Wi-Fi secrets, or private device logs
---

# Problem

FW-001 can build an opt-in HTTP Message Hub firmware path, but the next real
R1 hardware run still needs repeatable host-side validation tooling and
field-test evidence wiring before the operator flashes and disconnects USB.

# Expected Result

The repository provides a repeatable R1 validation kit that can create a
message-hub test run, observe a fresh real-device heartbeat, queue one harmless
command, wait for a firmware ACK, and write a local evidence report. Firmware
can optionally include a `test_run_id` in status, telemetry, and ACK messages so
server exports can bind messages to a field run.

# Acceptance Criteria

- [x] Message Hub test-run export route matches the documented API.
- [x] Test-run export includes matching command history as well as messages.
- [x] Firmware HTTP mode can include a non-empty configured `test_run_id` in
      status, telemetry, and ACK messages.
- [x] Host-side validation script creates a test run, waits for fresh
      heartbeat/status, sends a harmless command, waits for ACK, and writes
      JSON/Markdown evidence.
- [x] Tests protect the validation script and server export behavior.
- [x] No real secrets or private logs are committed.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_server quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_validation quality_tests.test_message_hub_contracts -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Board: not run in this task.
- Firmware commit or image: not flashed in this task.
- Connection path: not applicable; this task prepares R1 validation tooling.
- Evidence path: generated only when the operator runs the validation script
  against real hardware.

# Completion Evidence

- Changed files:
  - `docs/tasks/done/FW-001-HW-PREP_R1_USB_FREE_VALIDATION_KIT.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/current/STATUS.md`
  - `firmware/mqtt_heartbeat/README.md`
  - `firmware/mqtt_heartbeat/main/Kconfig.projbuild`
  - `firmware/mqtt_heartbeat/main/app_main.c`
  - `firmware/mqtt_heartbeat/sdkconfig.vps_http.defaults.example`
  - `quality_tests/test_fw001_hw_validation.py`
  - `quality_tests/test_message_hub_contracts.py`
  - `quality_tests/test_message_hub_server.py`
  - `quality_tests/test_mqtt_heartbeat_firmware.py`
  - `scripts/validate_fw001_hw_loop.py`
  - `server/message_hub.py`
  - `shared/contracts/message_hub_ack.schema.json`
  - `shared/contracts/message_hub_command.schema.json`
  - `shared/contracts/message_hub_error.schema.json`
  - `shared/contracts/message_hub_status.schema.json`
- Validation result:
  - `python -m unittest quality_tests.test_message_hub_server quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_validation quality_tests.test_message_hub_contracts -v`: PASS, 17 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 210 tests.
  - Default MQTT ESP-IDF build: PASS, `egolink_mqtt_heartbeat.bin` size `0xd91b0`.
  - HTTP Message Hub opt-in ESP-IDF build: PASS, `egolink_mqtt_heartbeat.bin` size `0xdbee0`.
  - VPS redeploy: PASS, `egolink-message-hub.service` restarted and active on
    `0.0.0.0:8790`; `/health` returned `ok=true`.
  - VPS export route smoke: PASS, a temporary `deploy-route-smoke-*` test run
    was created and exported through `/api/v1/test-runs/{test_run_id}/export`.
- Remaining risks:
  - This task did not flash firmware or run the device on independent power.
  - R1 hardware acceptance still requires operator-approved flashing and a
    real USB-disconnected run.
  - HTTP mode remains HTTP-only and should move behind HTTPS or a tunnel before
    longer public field trials.
  - Real GNSS, LTE module control, battery, camera, audio, and product power
    behavior remain unverified by this task.
