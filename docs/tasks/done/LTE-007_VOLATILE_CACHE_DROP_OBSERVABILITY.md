---
id: LTE-007
title: Volatile Cache Drop Observability
status: completed
priority: high
requires_hardware: false
created: 2026-07-01
last_updated: 2026-07-01

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-005_LTE_RELIABILITY_GATE_BASELINE.md
  - docs/tasks/done/OBS-004_RELIABILITY_OBSERVABILITY_BASELINE.md
  - docs/tasks/done/LTE-006_FIRMWARE_SIDE_RELIABILITY_NONCLAIM_OBSERVABILITY.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/KEY_RELEASES.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/LTE-007_VOLATILE_CACHE_DROP_OBSERVABILITY.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_lte_reliability_gate.py

out_of_scope:
  - flashing firmware without explicit operator confirmation
  - claiming USB-Free hardware runtime validation
  - VPS deployment or GitLab changes
  - changing raw-frame framing or required protocol fields
  - implementing durable store-forward cache
  - claiming reconnect recovery, long LTE stability, battery/power behavior,
    enclosure behavior, GNSS acceptance, or product readiness
---

# LTE-007 Volatile Cache Drop Observability

## Goal

Move the reliability path one step beyond LTE-006's cache non-claim by making
the firmware report concrete, volatile outbox send/drop counters in the raw LTE
`location_observation` and ACK payloads.

This is still not store-forward. The firmware can now explain whether the
current boot attempted, succeeded, failed, or dropped LTE raw-frame posts, but
it does not retain unsent frames across reboot or network outage.

## Acceptance

- [x] Firmware tracks raw LTE POST attempt, success, failure, and drop counts
      for the current boot.
- [x] Firmware reports `cache_state=volatile_outbox`,
      `cache_source_status=observed`, `cache_queued_message_count=0`,
      `cache_dropped_message_count`, `cache_oldest_message_age_ms=0`, and
      `cache_last_drop_reason`.
- [x] Firmware reports `network_raw_post_attempt_count`,
      `network_raw_post_success_count`, and
      `network_raw_post_failure_count`.
- [x] Raw LTE `location_observation` and raw LTE ACK payloads carry the same
      volatile reliability counters.
- [x] LTE-005 treats observed volatile queue/drop counters as cache/drop
      observability evidence while preserving the no-durability boundary.
- [x] The LTE wire payload remains raw-frame/KV, not JSON.
- [x] Focused tests, guarded ESP-IDF build, and full regression tests pass
      without flashing.

## Evidence

- Firmware counters:
  `lte_raw_outbox_record_post_result`, `lte_raw_outbox_record_drop`, and
  `lte_raw_outbox_snapshot`.
- Raw KV fields:
  `network_raw_post_attempt_count`,
  `network_raw_post_success_count`,
  `network_raw_post_failure_count`, `cache_state=volatile_outbox`,
  `cache_source_status=observed`, `cache_queued_message_count=0`,
  `cache_dropped_message_count`, `cache_oldest_message_age_ms=0`, and
  `cache_last_drop_reason`.
- Focused tests:
  `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_lte_reliability_gate -v`
  PASS, 19 tests.
- ESP-IDF guarded build:
  `powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-lte007-volatile-cache-observe -TestRunId lte007-volatile-cache-20260701-001 -BuildDir build_lte007_volatile_cache_observe -EnableSim7670Gnss -EnableSim7670LocationObservation -Build -Json`
  passed and generated
  `firmware/mqtt_heartbeat/build_lte007_volatile_cache_observe/egolink_mqtt_heartbeat.bin`
  (`301056` bytes). The script did not flash hardware.
- Full regression:
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` PASS,
  315 tests.
- Formatting:
  `git diff --check` PASS.

## Completion Boundary

LTE-007 is a firmware/static-build observability increment. It does not flash
hardware, run a USB-Free validation, deploy to the VPS, implement durable
offline cache, prove reconnect recovery, prove long LTE stability, prove
battery/power behavior, or make any product-readiness claim.
