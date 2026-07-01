---
id: LTE-008
title: Bounded Raw POST Retry Observability
status: completed
priority: high
requires_hardware: true
created: 2026-07-01
last_updated: 2026-07-01

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-007_VOLATILE_CACHE_DROP_OBSERVABILITY.md
  - firmware/AGENTS.md
  - quality_tests/AGENTS.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/LTE-008_BOUNDED_RAW_POST_RETRY_OBSERVABILITY.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/Kconfig.projbuild
  - firmware/mqtt_heartbeat/main/app_main.c
  - server/message_hub.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_lte_reliability_gate.py

out_of_scope:
  - flashing firmware without explicit operator confirmation
  - modifying GitLab or unrelated VPS services
  - changing raw-frame framing or required protocol fields
  - implementing durable store-forward cache
  - claiming reconnect recovery, long LTE stability, battery/power behavior,
    enclosure behavior, GNSS acceptance, or product readiness
---

# LTE-008 Bounded Raw POST Retry Observability

## Goal

Move from LTE-007's volatile send/drop visibility to one bounded recovery
behavior: a failed raw-frame LTE HTTP POST may be retried once within the same
boot before the message is counted as dropped.

This is still not durable store-forward. The retry is immediate and
current-boot only; a reboot may reset counters and no unsent frame is retained
across power loss.

## Acceptance

- [x] Firmware exposes
      `CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_RETRY_MAX`, defaulting to one
      retry for the raw LTE command-loop path.
- [x] Raw LTE `location_report`, `location_observation`, and ACK uploads share
      one bounded POST helper.
- [x] Raw POST attempt/success/failure counters count individual HTTP POST
      attempts.
- [x] Drop accounting is final-outcome based: `cache_dropped_message_count`
      increments after frame-build failure or after all bounded retry attempts
      fail.
- [x] Raw LTE `location_observation` and ACK payloads include
      `cache_retry_policy=single_retry_current_boot`,
      `cache_retry_attempt_count`, `cache_retry_success_count`, and
      `cache_retry_failure_count`.
- [x] Message Hub derives retry fields into `reliability.cache`.
- [x] Dashboard exposes Cache Retry in current-run and latest-field-state
      views.
- [x] The LTE wire payload remains raw-frame/KV, not JSON.
- [x] Focused tests and guarded ESP-IDF build pass without flashing.
- [x] `COM4` flash passes after explicit operator confirmation.

## Evidence

- Firmware retry helper:
  `lte_raw_outbox_post_raw_with_retry`,
  `lte_raw_outbox_record_post_result`, `lte_raw_outbox_record_retry_result`,
  and `lte_raw_outbox_record_drop`.
- Raw KV fields:
  `cache_retry_policy=single_retry_current_boot`,
  `cache_retry_attempt_count`, `cache_retry_success_count`, and
  `cache_retry_failure_count`.
- Message Hub/Web:
  `server/message_hub.py` derives retry fields into `reliability.cache` and
  renders Cache Retry in the Dashboard.
- VPS/Web deployment:
  Message Hub/Web was redeployed to `203.0.113.10:8790` without modifying
  GitLab. Public `/health` returned `ok=true`, unauthenticated `/api/state`
  returned HTTP 401, the public Dashboard HTML contained `Cache Retry`,
  `egolink-message-hub.service` remained `active`, and the existing GitLab
  service remained `active`.
- Focused tests:
  `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard quality_tests.test_lte_reliability_gate -v`
  PASS, 42 tests.
- ESP-IDF guarded build:
  `powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-lte008-bounded-raw-retry -TestRunId lte008-bounded-raw-retry-20260701-001 -BuildDir build_lte008_bounded_raw_retry -EnableSim7670Gnss -EnableSim7670LocationObservation -Build -Json`
  passed and generated
  `firmware/mqtt_heartbeat/build_lte008_bounded_raw_retry/egolink_mqtt_heartbeat.bin`
  (`301824` bytes). The script did not flash hardware.
- Flash:
  `reports/field_validation/lte008-bounded-raw-retry-20260701-001/flash_report.md`
  records `COM4` flash PASS for ESP32-S3 QFN56 rev v0.2, MAC
  `02:00:00:00:00:03`, app size `301824` bytes, and verified bootloader/app/
  partition hashes.
- USB-Free runtime attempt 1:
  `reports/field_validation/lte008-bounded-raw-retry-20260701-001/` records
  FAIL for `cmd-000029`. The device selected the raw `request_location`
  command, uploaded raw LTE `location_report seq=4`, and ACKed over LTE
  (`seq=6`, `LTE_HTTP_OK` / HTTP `200`), but command/ACK status is `error`
  because raw LTE `location_observation` payload construction was truncated.
  The ACK retained useful reliability evidence:
  `cache_state=volatile_outbox`,
  `cache_retry_policy=single_retry_current_boot`, raw POST `1/1/0`,
  `cache_dropped_message_count=1`, and
  `cache_last_drop_reason=location_observation_payload_truncated`.
- LTE-008 fix1 build:
  optional long Wi-Fi/IMU/power reason lines were removed from raw LTE
  `location_observation` to preserve source/evidence status, belief,
  network, cache, and retry fields while keeping the payload within the
  existing compact buffer. Focused firmware/LTE tests passed with 20 tests.
  Guarded ESP-IDF build passed with firmware
  `0.1.0-lte008-bounded-raw-retry-fix1`, test run
  `lte008-bounded-raw-retry-fix1-20260701-001`, binary
  `firmware/mqtt_heartbeat/build_lte008_bounded_raw_retry_fix1/egolink_mqtt_heartbeat.bin`
  (`301680` bytes). After the fix1 code/docs update,
  `python scripts/context_lint.py` passed, `git diff --check` passed, and full
  `scripts/verify.ps1` passed with 316 tests. The fix1 image was subsequently
  flashed as recorded below.
- LTE-008 fix1 flash:
  `reports/field_validation/lte008-bounded-raw-retry-fix1-20260701-001/flash_report.md`
  records `COM4` flash PASS for firmware
  `0.1.0-lte008-bounded-raw-retry-fix1` at commit `194ee86`. `esptool.py`
  detected ESP32-S3 QFN56 rev v0.2, MAC `02:00:00:00:00:03`, wrote
  bootloader, app (`301680` bytes), and partition table, verified hashes, and
  completed hard reset.

## Completion Boundary

LTE-008 is a firmware/server-Web observability and bounded retry increment
with COM4 flash evidence and one explainable USB-Free runtime failure. Fix1 is
build-verified and flashed, but not USB-Free runtime validated. This task does
not prove successful USB-Free runtime behavior, modify GitLab, implement
durable offline cache, prove reconnect recovery, prove long LTE stability,
prove battery/power behavior, prove GNSS acceptance, or make any
product-readiness claim.
