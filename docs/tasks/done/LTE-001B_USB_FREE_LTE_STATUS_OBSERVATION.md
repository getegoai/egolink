---
title: USB-Free LTE Status Observation
task_id: LTE-001B
status: done
last_verified: 2026-06-28
---

# LTE-001B USB-Free LTE Status Observation

## Goal

Flash an LTE-status observability firmware built from the LTE-001A baseline and
validate that a real USB-disconnected device reports SIM7670G LTE state to the
VPS Message Hub and Dashboard. The expected outcome is not LTE data transport
yet; it is a diagnosable LTE status result such as `LTE_READY`,
`LTE_NOT_REGISTERED`, `LTE_PDP_INACTIVE`, or `LTE_AT_UNREACHABLE`.

## Context

- `docs/current/ACTIVE_BUILD.md`
- `docs/current/STATUS.md`
- `docs/development/LTE_TRANSPORT.md`
- `docs/tasks/done/LTE-001A_LTE_REGISTRATION_CELL_OBSERVABILITY_BASELINE.md`
- `firmware/mqtt_heartbeat/README.md`
- `scripts/run_fw001_hw_r1.ps1`
- `scripts/validate_lte_observability.py`

## Allowed Paths

- `docs/current/STATUS.md`
- `docs/current/ACTIVE_BUILD.md`
- `docs/hardware/BOARD_MATRIX.md`
- `docs/tasks/TASK_TREE.md`
- `docs/tasks/active/LTE-001B_USB_FREE_LTE_STATUS_OBSERVATION.md`
- `docs/tasks/done/LTE-001B_USB_FREE_LTE_STATUS_OBSERVATION.md`
- `firmware/mqtt_heartbeat/main/app_main.c`
- `scripts/validate_lte_observability.py`
- `quality_tests/test_mqtt_heartbeat_firmware.py`
- `quality_tests/test_lte_observability_validation.py`
- `quality_tests/test_platform_imu_firmware.py`

## Out Of Scope

- Do not implement LTE HTTP transport in this task.
- Do not disable Wi-Fi as the runtime data path in this task.
- Do not set `transport.type=lte`.
- Do not claim DNS, HTTP, command polling, ACK, battery, charging, power, or
  long-run LTE stability acceptance.
- Do not modify GitLab or unrelated VPS services.

## Operator Actions Required

1. Connect the connectivity node back to USB.
2. Confirm the flash port explicitly, expected currently `COM4`.
3. After flashing, connect independent power and disconnect USB.
4. Confirm USB-Free runtime before validation starts.

## Flash Evidence

- Firmware version: `0.1.0-lte001b-observe`
- Test run ID: `lte001b-observe-20260628-130400`
- Build directory: `firmware/mqtt_heartbeat/build_lte001b_observe/`
- Binary: `firmware/mqtt_heartbeat/build_lte001b_observe/egolink_mqtt_heartbeat.bin`
- Flash port: `COM4`
- Flash result: ESP32-S3 detected, image written, hashes verified, hard reset
  completed.
- Runtime result: pending USB-Free validation after independent power and USB
  disconnected.

## Validation Attempt 1

- Observation ID: `lte001b-observe-20260628-130400`
- Connection path: independent power, USB disconnected, operator-confirmed.
- Evidence:
  `reports/field_validation/lte001b-observe-20260628-130400/lte_observability_report.json`
- Result: FAIL.
- VPS observed new firmware registration with `fw_version=0.1.0-lte001b-observe`,
  but no fresh status/heartbeat from the new test run.
- Last stored status remained `fw002c-resetdiag-fix3-20260628-093000`, and
  `observability.lte.reason_code` remained `unknown`.
- Interpretation: the new firmware reached the Message Hub register path, but
  did not complete the LTE-enabled status heartbeat path.

## Fix1 Candidate

- Firmware version: `0.1.0-lte001b-observe-fix1`
- Test run ID: `lte001b-observe-fix1-20260628-131739`
- Build directory: `firmware/mqtt_heartbeat/build_lte001b_observe_fix1/`
- Binary:
  `firmware/mqtt_heartbeat/build_lte001b_observe_fix1/egolink_mqtt_heartbeat.bin`
- Change: move LTE observation fragments out of heartbeat/sensor task stack and
  raise heartbeat/sensor task stack sizes to 12288 bytes.
- Build result: PASS.
- Flash result: PASS on `COM4`; ESP32-S3 detected, image written, hashes
  verified, hard reset completed.
- Runtime result: PASS after independent power and USB disconnected.

## Validation Attempt 2

- Observation ID: `lte001b-observe-fix1-20260628-131739`
- Connection path: independent power, USB disconnected, operator-confirmed.
- Evidence:
  `reports/field_validation/lte001b-observe-fix1-20260628-131739/lte_observability_report.json`
- Result: PASS.
- Started at: `2026-06-28T05:57:00.901907+00:00`
- Completed at: `2026-06-28T05:57:07.298088+00:00`
- Firmware version: `0.1.0-lte001b-observe-fix1`
- Test run ID: `lte001b-observe-fix1-20260628-131739`
- LTE reason: `LTE_READY`
- LTE driver: `sim7670g_uart_at`
- SIM state: `READY`
- Registration state: `registered_home`
- APN/PDP: `configured` / `active`
- Assigned IP: observed as present in the validation report.
- RAT/cell: `LTE` / `180571649`
- Signal: RSSI `-90`, RSRP `-97`, RSRQ `-7`, SINR `28`.

## Planned Commands

Build/flash after explicit operator confirmation:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 `
  -HostName 203.0.113.10 `
  -FwVersion 0.1.0-lte001b-observe-fix1 `
  -TestRunId lte001b-observe-fix1-20260628-131739 `
  -BuildDir build_lte001b_observe_fix1 `
  -PrepareBuild `
  -EnableSim7670Gnss `
  -EnableSim7670LteStatus `
  -Flash `
  -FlashPort COM4 `
  -IUnderstandFlashWritesFirmware `
  -Json
```

Validate only after the operator confirms independent power and USB
disconnected:

```powershell
$env:EGOLINK_MESSAGE_HUB_TOKEN = (Get-Content -LiteralPath server\runtime\vps_message_hub_token.txt -Raw).Trim()
python scripts\validate_lte_observability.py `
  --hub http://203.0.113.10:8790 `
  --device-id ego-link-r1-connectivity-001 `
  --observation-id lte001b-observe-fix1-20260628-131739 `
  --expected-fw-version 0.1.0-lte001b-observe-fix1 `
  --expected-test-run-id lte001b-observe-fix1-20260628-131739 `
  --timeout-sec 240 `
  --poll-interval-sec 5 `
  --json
```

## Acceptance

- The device reports firmware version `0.1.0-lte001b-observe-fix1`.
- The latest status message carries the expected test-run ID.
- `/api/state` exposes `observability.lte`.
- `observability.lte.reason_code` is one of the known `LTE_*` reason codes.
- Evidence is written under ignored `reports/field_validation/`.

Result: accepted for LTE status observability.

## Boundary

`LTE_READY` is a modem status observation, not proof of LTE HTTP. Non-ready
reason codes are acceptable LTE-001B evidence when they identify the blocked
stage. LTE HTTP uplink remains `LTE-002`.
