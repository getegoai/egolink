---
id: LTE-011-fix1
title: LTE-011 Observation Payload Margin
status: completed
priority: high
requires_hardware: false
created: 2026-07-02
last_updated: 2026-07-02

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-011_RECONNECT_STORE_FORWARD_EVIDENCE_TEST_MODE.md
  - firmware/AGENTS.md
  - quality_tests/AGENTS.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/tasks/done/LTE-011_FIX1_OBSERVATION_PAYLOAD_MARGIN.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - quality_tests/test_mqtt_heartbeat_firmware.py

out_of_scope:
  - flashing firmware
  - running USB-Free hardware validation
  - VPS deployment or GitLab changes
  - changing raw-frame framing, command semantics, or public protocol fields
  - implementing real modem reconnect recovery
  - implementing durable local storage or queue replay
  - claiming reconnect recovery, durable store-forward, long LTE stability,
    battery/power behavior, enclosure behavior, GNSS acceptance, or product readiness
---

# LTE-011 Fix1 Observation Payload Margin

## Goal

Fix the LTE-011 USB-Free failure where `cmd-000032` reached the device,
`location_report` uploaded, and LTE ACK uploaded, but raw LTE
`location_observation` failed before POST with
`location_observation_payload_truncated`.

## Runtime Failure Evidence

The LTE-011 base image produced an explainable FAIL under
`lte011-reconnect-store-forward-test-20260702-001`:

- command: `cmd-000032`;
- device path: independent power, USB disconnected, operator-confirmed reboot;
- raw LTE `location_report`: frame `loc-cmd-000032`, `seq=2`,
  `fix=false`, `gnss_state=no_fix`;
- raw LTE ACK: `seq=4`, `status=error`, `LTE_HTTP_OK` / HTTP `200`;
- missing frame: raw LTE `location_observation`;
- firmware drop reason: `location_observation_payload_truncated`;
- evidence path:
  `reports/field_validation/lte011-reconnect-store-forward-test-20260702-001/`.

## Change

- Increased only the raw LTE `location_observation` local payload buffer from
  `1750` bytes to `2050` bytes.
- Increased only the matching raw-frame buffer from `2100` bytes to `2400`
  bytes.
- Kept raw-frame/KV payload shape, command semantics, retry behavior, and
  public protocol fields unchanged.

## Evidence

- Firmware version/test run:
  `0.1.0-lte011-reconnect-store-forward-test-fix1` /
  `lte011-reconnect-store-forward-test-fix1-20260702-001`.
- Build artifact:
  `firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test_fix1/egolink_mqtt_heartbeat.bin`
  (`302528` bytes).

## Validation

- `python -m unittest quality_tests.test_mqtt_heartbeat_firmware -v`:
  PASS, 13 tests.
- `powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-lte011-reconnect-store-forward-test-fix1 -TestRunId lte011-reconnect-store-forward-test-fix1-20260702-001 -BuildDir build_lte011_reconnect_store_forward_test_fix1 -EnableSim7670Gnss -EnableReconnectStoreForwardTest -Build -Json`:
  PASS, `flash_intentionally_not_run=true`.

## Completion Boundary

LTE-011 fix1 is a build-verified firmware margin fix only. It does not prove
USB-Free runtime pass, LTE-010 gate pass, real modem reconnect recovery,
durable store-forward, queue replay, long LTE stability, GNSS acceptance,
power behavior, enclosure behavior, model behavior, or product readiness.
