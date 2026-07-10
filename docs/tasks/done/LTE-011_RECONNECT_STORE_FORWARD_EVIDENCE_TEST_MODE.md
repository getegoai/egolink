---
id: LTE-011
title: Reconnect Store-Forward Evidence Test Mode
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
  - docs/tasks/done/LTE-010_RECONNECT_STORE_FORWARD_GATE_BASELINE.md
  - firmware/AGENTS.md
  - quality_tests/AGENTS.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/LTE-011_RECONNECT_STORE_FORWARD_EVIDENCE_TEST_MODE.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/Kconfig.projbuild
  - firmware/mqtt_heartbeat/main/app_main.c
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/run_fw001_hw_r1.ps1
  - server/message_hub.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_fw001_hw_runner.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_message_hub_dashboard.py

out_of_scope:
  - flashing firmware
  - running USB-Free hardware validation
  - VPS deployment or GitLab changes
  - changing raw-frame framing or command semantics
  - implementing real modem reconnect recovery
  - implementing durable local storage or queue replay
  - claiming reconnect recovery, durable store-forward, long LTE stability,
    battery/power behavior, enclosure behavior, GNSS acceptance, or product readiness
---

# LTE-011 Reconnect Store-Forward Evidence Test Mode

## Goal

Add a default-off, explicit test mode that can produce the evidence shape
required by the LTE-010 reconnect/store-forward offline gate without changing
normal product runtime behavior.

```text
raw LTE request_location loop
-> location_report
-> location_observation carries reconnect/store-forward evidence fields
-> ACK carries post-reconnect recovery/cache flush evidence fields
-> LTE-010 can evaluate the resulting export
```

## Acceptance

- [x] Firmware Kconfig adds a default-off LTE-011 reconnect/store-forward
      evidence test switch.
- [x] Build/runner scripts expose the switch explicitly and keep it disabled by
      default.
- [x] Raw LTE `location_observation` and ACK payloads can include additive
      `network_reconnect_*` and `cache_flush_*` fields when the switch is
      enabled.
- [x] Message Hub raw KV derivation preserves cache flush counters in
      `reliability.cache`.
- [x] Focused tests protect the default-off boundary and additive field
      derivation.
- [x] Validation runs without firmware flash, hardware runtime validation, VPS
      deployment, or GitLab changes.

## Evidence

- Firmware switch:
  `CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST`.
- Build/runner switch:
  `-EnableReconnectStoreForwardTest`.
- Build artifact:
  `firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test/egolink_mqtt_heartbeat.bin`
  (`302496` bytes).
- Firmware version/test run:
  `0.1.0-lte011-reconnect-store-forward-test` /
  `lte011-reconnect-store-forward-test-20260702-001`.

## Validation

- `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard -v`:
  PASS, 51 tests.
- `powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-lte011-reconnect-store-forward-test -TestRunId lte011-reconnect-store-forward-test-20260702-001 -BuildDir build_lte011_reconnect_store_forward_test -EnableSim7670Gnss -EnableReconnectStoreForwardTest -Build -Json`:
  PASS, `flash_intentionally_not_run=true`.
- `python scripts\context_lint.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 324
  tests.
- `git diff --check`: PASS with Windows line-ending warnings only.

## Completion Boundary

LTE-011 only creates a build-time evidence test mode and server-side additive
field derivation. A passing build or unit test does not prove real reconnect
recovery, durable store-forward, queue replay, long LTE stability, GNSS
acceptance, power behavior, enclosure behavior, model behavior, or product
readiness.
