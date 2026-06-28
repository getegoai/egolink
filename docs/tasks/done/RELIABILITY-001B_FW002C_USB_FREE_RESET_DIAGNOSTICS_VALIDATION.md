---
id: RELIABILITY-001B
title: FW-002C USB-Free Reset Diagnostics Validation
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
  - docs/tasks/done/RELIABILITY-001A_USB_FREE_STABILITY_OBSERVER_RESET_DIAGNOSTICS.md

allowed_paths:
  - docs/current/
  - docs/hardware/
  - docs/tasks/
  - firmware/mqtt_heartbeat/
  - quality_tests/
  - reports/field_validation/

out_of_scope:
  - claiming reconnect or long-run reliability acceptance
  - claiming outdoor GNSS fix or real coordinates
  - claiming SIM7670G LTE data transport
  - claiming battery accuracy or product power behavior
  - changing pin assignments or board wiring assumptions
  - flashing firmware without explicit operator intent
  - sending downlink commands during the stability observer run
  - storing real VPS passwords, bearer tokens, Wi-Fi secrets, or private logs
---

# Problem

RELIABILITY-001A detected a FW-002B sequence regression while the connectivity
node was running USB-Free. The next step was to flash the FW-002C
reset-diagnostics image, observe reset metadata over the VPS Message Hub, and
fix any firmware issue that blocked a short USB-Free stability gate.

# Expected Result

Run FW-002C reset diagnostics on the real connectivity node without USB as a
runtime dependency, diagnose the observed reset cause through message payloads,
and produce a passing short observation-only stability run.

# Acceptance Criteria

- [x] Flashing is performed only after explicit operator confirmation.
- [x] USB-Free validation uses independent power with USB disconnected.
- [x] Stability observation reads only the VPS Message Hub and does not enqueue
      commands.
- [x] FW-002C status and `sensor_sample` messages include `reset_reason` and
      persistent `boot_count`.
- [x] A failed reset-diagnostics observation is preserved as evidence when it
      exposes a real firmware issue.
- [x] A fixed image passes a 120-second observation with no sequence
      regressions.

# Hardware Runs

## FW-002C resetdiag fix1

- Board: `connectivity-node-001`, Waveshare ESP32-S3-SIM7670G-4G.
- Flash port: `COM4`, after explicit operator confirmation.
- Firmware version: `0.1.0-fw002c-resetdiag-fix1`.
- Test run ID: `fw002c-resetdiag-fix1-20260627-180758`.
- Runtime connection path: `independent_power_usb_disconnected`.
- Observation ID: `stability-fw002c-resetdiag-fix1-20260627-181600`.
- Result: FAIL.
- Evidence path:
  - `reports/field_validation/stability-fw002c-resetdiag-fix1-20260627-181600/stability_observation_report.md`
  - `reports/field_validation/stability-fw002c-resetdiag-fix1-20260627-181600/stability_observation_report.json`
  - `reports/field_validation/stability-fw002c-resetdiag-fix1-20260627-181600/observed_messages.json`
  - `reports/field_validation/stability-fw002c-resetdiag-fix1-20260627-181600/device_snapshots.json`
- Finding: 120-second observation saw 51 messages and 10 sequence regressions.
  Reset diagnostics showed repeated `reset_reason=panic`; `boot_count` advanced
  from 41 to 81, with most boots publishing only `status seq=1` and sometimes
  `sensor_sample seq=2`.

## FW-002C resetdiag fix2

- Board: `connectivity-node-001`, Waveshare ESP32-S3-SIM7670G-4G.
- Flash port: `COM4`, after explicit operator confirmation.
- Firmware version: `0.1.0-fw002c-resetdiag-fix2`.
- Test run ID: `fw002c-resetdiag-fix2-20260627-182430`.
- Runtime connection path: `independent_power_usb_disconnected`.
- Observation ID: `stability-fw002c-resetdiag-fix2-20260627-183100`.
- Result: PASS.
- Evidence path:
  - `reports/field_validation/stability-fw002c-resetdiag-fix2-20260627-183100/stability_observation_report.md`
  - `reports/field_validation/stability-fw002c-resetdiag-fix2-20260627-183100/stability_observation_report.json`
  - `reports/field_validation/stability-fw002c-resetdiag-fix2-20260627-183100/observed_messages.json`
  - `reports/field_validation/stability-fw002c-resetdiag-fix2-20260627-183100/device_snapshots.json`
- Observation summary: 120 seconds, 15 messages, 11 status messages, 4
  `sensor_sample` events, `seq` from 11 to 25, `seq_regressions=0`, max message
  gap 11.547434 seconds, final last-seen age 6.563391 seconds.
- Latest reset diagnostics in the passing run: `reset_reason=poweron`,
  `boot_count=171`.

# Firmware Fix

The FW-002C fix1 observation exposed a runtime `panic` loop after status and
sensor publication started. The likely stack-pressure source was the 1280-byte
heartbeat status payload allocated on the heartbeat task stack while the HTTP
publish path also uses local stack objects. FW-002C fix2 moves the heartbeat
payload to static storage and uses `HEARTBEAT_TASK_STACK_SIZE=6144`.

# Validation Commands

```powershell
python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_platform_imu_firmware -v
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-fw002c-resetdiag-fix2 -TestRunId fw002c-resetdiag-fix2-20260627-182430 -BuildDir build_fw002c_resetdiag -PrepareBuild -EnableSim7670Gnss -Json
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-fw002c-resetdiag-fix2 -TestRunId fw002c-resetdiag-fix2-20260627-182430 -BuildDir build_fw002c_resetdiag -EnableSim7670Gnss -Flash -FlashPort COM4 -IUnderstandFlashWritesFirmware -Json
python scripts\validate_message_hub_stability.py --hub http://203.0.113.10:8790 --device-id ego-link-r1-connectivity-001 --observation-id stability-fw002c-resetdiag-fix2-20260627-183100 --duration-sec 120 --poll-interval-sec 5 --min-messages 5 --max-last-seen-age-sec 45 --max-message-gap-sec 35 --expected-fw-version 0.1.0-fw002c-resetdiag-fix2 --expected-message-test-run-id fw002c-resetdiag-fix2-20260627-182430 --json
python scripts\context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files:
  - `docs/current/ACTIVE_BUILD.md`
  - `docs/current/STATUS.md`
  - `docs/hardware/BOARD_MATRIX.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/RELIABILITY-001A_USB_FREE_STABILITY_OBSERVER_RESET_DIAGNOSTICS.md`
  - `docs/tasks/done/RELIABILITY-001B_FW002C_USB_FREE_RESET_DIAGNOSTICS_VALIDATION.md`
  - `firmware/mqtt_heartbeat/main/app_main.c`
  - `quality_tests/test_mqtt_heartbeat_firmware.py`
- Build result:
  - FW-002C resetdiag fix2 build: PASS.
  - Firmware image:
    `firmware/mqtt_heartbeat/build_fw002c_resetdiag/egolink_mqtt_heartbeat.bin`.
- Hardware validation result:
  - FW-002C resetdiag fix1 USB-Free observation: FAIL, repeated panic resets
    detected through reset diagnostics.
  - FW-002C resetdiag fix2 USB-Free observation: PASS, no sequence regression
    during the 120-second window.
- Final validation result:
  - `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_platform_imu_firmware -v`: PASS, 15 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
    234 tests.

# Remaining Risks

- This is a short R3 preflight stability gate, not reconnect or long-run
  reliability acceptance.
- The passing run used Wi-Fi HTTP to the VPS Message Hub; SIM7670G LTE data
  transport remains unverified.
- Outdoor real GNSS fix, real coordinates, battery accuracy, and product power
  behavior remain unverified.
