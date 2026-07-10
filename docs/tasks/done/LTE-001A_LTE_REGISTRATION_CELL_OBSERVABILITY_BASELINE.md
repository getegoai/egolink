---
title: LTE Registration Cell Observability Baseline
task_id: LTE-001A
status: done
last_verified: 2026-06-28
---

# LTE-001A LTE Registration Cell Observability Baseline

## Goal

Make SIM7670G LTE readiness explainable before attempting LTE data transport.
The system should be able to distinguish AT unreachable, SIM not ready, not
registered, not attached, PDP inactive, and LTE-ready states from normal
Message Hub and Dashboard evidence.

## Scope

- Add an opt-in firmware LTE status query path:
  `CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED`.
- Reuse the existing SIM7670G UART AT backend instead of creating a parallel
  serial stack.
- Upload optional `cell` and `lte` objects in heartbeat/status and
  `sensor_sample` messages.
- Extend Message Hub observability and Dashboard rendering for LTE
  registration, SIM, APN/PDP, assigned-IP, signal, and reason-code state.
- Extend protocol schemas and development docs for optional `lte` fields.

## Evidence

- Firmware component:
  `firmware/mqtt_heartbeat/components/sim7670_gnss/`
- Firmware payload integration:
  `firmware/mqtt_heartbeat/main/app_main.c`
- Config and guarded runner switches:
  `scripts/prepare_fw001_hw_config.ps1`,
  `scripts/run_fw001_hw_r1.ps1`
- Message Hub observability and Dashboard:
  `server/message_hub.py`
- Contracts:
  `shared/contracts/message_hub_status.schema.json`,
  `shared/contracts/message_hub_event.schema.json`
- Docs:
  `docs/development/PROTOCOL.md`,
  `docs/development/LTE_TRANSPORT.md`,
  `docs/current/STATUS.md`

## Validation

- `python -m unittest quality_tests.test_fw002b_sim7670_gnss_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_contracts -v`
  passed.
- `python -m unittest quality_tests.test_platform_imu_firmware -v` passed after
  the sensor payload buffer and task stack assertions were updated for the LTE
  observation fragment.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` passed with 245
  tests.
- ESP-IDF build passed through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670Gnss -EnableSim7670LteStatus`
  for firmware version `0.1.0-lte001a-observe`, test run
  `lte001a-build-20260628-124145`, producing
  `firmware/mqtt_heartbeat/build_lte001a_observe/egolink_mqtt_heartbeat.bin`.
  Flash and runtime validation were intentionally not run.
- The updated Message Hub was redeployed to the VPS without touching GitLab.
  `/health` returned `ok=true`; authenticated `/api/state` returned four
  devices and the current connectivity node row had `observability.lte`.

## Boundary

This task is build/static verified only. It does not flash hardware, run
USB-Free hardware validation, disable Wi-Fi, set `transport.type=lte`, prove
SIM7670G DNS/HTTP, or validate LTE command polling and ACK over the cellular
data path.

## Follow-Up

- `LTE-001B`: flash an LTE-status image and run a bounded USB-Free observation
  to capture real SIM7670G LTE registration/cell evidence.
- `LTE-002`: send one Message Hub telemetry message over SIM7670G LTE HTTP with
  Wi-Fi disabled for the run.
- `LTE-003`: poll command and ACK over SIM7670G LTE HTTP without changing
  command semantics.
