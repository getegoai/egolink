---
title: LTE HTTP Uplink Thin-Slice
task_id: LTE-002
status: active
last_verified: 2026-06-28
context:
  - docs/current/ACTIVE_BUILD.md
  - docs/current/STATUS.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/LTE-001B_USB_FREE_LTE_STATUS_OBSERVATION.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md
  - scripts/run_fw001_hw_r1.ps1
allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/active/LTE-002_LTE_HTTP_UPLINK_THIN_SLICE.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/Kconfig.projbuild
  - firmware/mqtt_heartbeat/components/sim7670_gnss/include/sim7670_gnss.h
  - firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_gnss.c
  - firmware/mqtt_heartbeat/main/app_main.c
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/run_fw001_hw_r1.ps1
  - scripts/validate_lte_http_probe.py
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_fw001_hw_runner.py
  - quality_tests/test_fw002b_sim7670_gnss_firmware.py
  - quality_tests/test_lte_http_probe_validation.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
---

# LTE-002 LTE HTTP Uplink Thin-Slice

## Goal

Send at least one Message Hub telemetry event from the ESP32-S3 through the
SIM7670G LTE HTTP stack with Wi-Fi disabled for the run. The event should make
`transport.type=lte` visible in `/api/state` and preserve LTE/cell context so
HTTP failures are not confused with GNSS, Web, or command-loop failures.

## Scope

- Add an opt-in firmware mode:
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED`.
- Reuse the existing SIM7670G UART AT backend and LTE status query.
- Skip Wi-Fi initialization, device registration over Wi-Fi, command polling,
  heartbeat task, and sensor task while the LTE HTTP probe mode is enabled.
- POST a compact `event_type=lte_http_probe` telemetry event to the existing
  VPS Message Hub `/telemetry` endpoint through SIM7670G AT HTTP commands.
- Upload additive `transport`, `cell`, `lte`, and `lte_http` evidence when the
  LTE POST reaches the Message Hub.
- Add a Message Hub-side validator that requires fresh LTE telemetry,
  `transport.type=lte`, matching firmware/test-run IDs, and a successful HTTP
  probe result.

## Out Of Scope

- Do not implement LTE command polling or ACK; that is `LTE-003`.
- Do not run a long LTE stability or reconnect gate.
- Do not replace the default MQTT path or the existing Wi-Fi HTTP development
  path.
- Do not claim battery, charging, power, enclosure GNSS, or product LTE
  acceptance.
- Do not modify GitLab or unrelated VPS services.

## Operator Actions Required

1. Connect the connectivity node back to USB.
2. Confirm the flash port explicitly, expected currently `COM4`.
3. After flashing, connect independent power and disconnect USB.
4. Confirm USB-Free runtime before validation starts.

## Acceptance

- Firmware builds with SIM7670G LTE status and LTE HTTP probe enabled.
- The flashed device runs without USB as a runtime data path.
- Wi-Fi is disabled by firmware mode during the LTE HTTP probe.
- The VPS Message Hub receives a fresh `lte_http_probe` event for the expected
  `test_run_id`.
- `/api/state` derives `observability.transport.type=lte`.
- The validation report records LTE/cell state, HTTP status, and evidence
  paths under ignored `reports/field_validation/`.

## Known Boundary

If the SIM7670G HTTP stack fails before any request reaches the VPS, the VPS
cannot receive that failure detail over the same failed path. In that case the
validator must fail explicitly as "no fresh LTE telemetry reached Message Hub"
and keep LTE-001B `LTE_READY` status evidence as the preceding readiness
context.

## Build Evidence

- Firmware version: `0.1.0-lte002-lte-http-probe`
- Test run ID: `lte002-lte-http-probe-20260628-141656`
- Build directory:
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe/egolink_mqtt_heartbeat.bin`
- Build result: PASS through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670Gnss -EnableSim7670LteHttpProbe`.
- Flash result: PASS on `COM4`; ESP32-S3 detected, bootloader/app/partition
  table written, hashes verified, hard reset completed.
- Flash evidence:
  `reports/field_validation/lte002-lte-http-probe-20260628-141656/flash_report.md`
- Runtime validation: not run; requires independent power and USB disconnected.

## Validation So Far

- `python -m unittest quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner quality_tests.test_fw002b_sim7670_gnss_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_lte_http_probe_validation -v`
  passed with 31 tests.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  253 tests.

## Validation Attempt 1

- Firmware version: `0.1.0-lte002-lte-http-probe`
- Test run ID: `lte002-lte-http-probe-20260628-141656`
- Connection path: independent power, USB disconnected, operator-confirmed.
- Evidence:
  `reports/field_validation/lte002-lte-http-probe-20260628-141656/lte_http_probe_report.json`
- Result: FAIL.
- Started at: `2026-06-28T06:30:38.364317+00:00`
- Completed at: `2026-06-28T06:34:41.148585+00:00`
- Failure: no fresh `lte_http_probe` telemetry reached the Message Hub.
- VPS state remained on the prior LTE-001B fix1 Wi-Fi message lineage:
  `observability.transport.type=mock_4g_over_wifi` and firmware
  `0.1.0-lte001b-observe-fix1`.
- Interpretation: LTE-002 did not reach the VPS over SIM7670G HTTP. The first
  fix candidate adds a bounded LTE readiness wait before AT HTTP POST so the
  module has time to re-register and activate PDP after independent-power boot.

## Fix1 Candidate

- Firmware version: `0.1.0-lte002-lte-http-probe-fix1`
- Test run ID: `lte002-lte-http-probe-fix1-20260628-143631`
- Change: wait up to `CONFIG_EGOLINK_SIM7670_LTE_HTTP_READY_WAIT_SEC=120`
  seconds, polling every `CONFIG_EGOLINK_SIM7670_LTE_HTTP_READY_POLL_SEC=5`
  seconds, for SIM7670G LTE status to report `LTE_READY` before attempting
  HTTP.
- Build directory:
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix1/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix1/egolink_mqtt_heartbeat.bin`
- Build result: PASS through
  `scripts/run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670Gnss -EnableSim7670LteHttpProbe`.
- Flash result: not run; requires explicit operator confirmation.
- Runtime validation: not run; requires independent power and USB disconnected.
