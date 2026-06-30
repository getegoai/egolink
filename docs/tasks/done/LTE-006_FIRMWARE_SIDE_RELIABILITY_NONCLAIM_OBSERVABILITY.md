---
id: LTE-006
title: Firmware-Side Reliability Non-Claim Observability
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-005_LTE_RELIABILITY_GATE_BASELINE.md
  - docs/tasks/done/OBS-004_RELIABILITY_OBSERVABILITY_BASELINE.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/LTE-006_FIRMWARE_SIDE_RELIABILITY_NONCLAIM_OBSERVABILITY.md
  - firmware/mqtt_heartbeat/README.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - scripts/validate_lte_reliability_gate.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_lte_reliability_gate.py

out_of_scope:
  - flashing firmware without explicit operator confirmation
  - claiming USB-Free hardware runtime validation
  - VPS deployment or GitLab changes
  - changing raw-frame framing or required protocol fields
  - implementing store-forward cache durability
  - claiming reconnect recovery, long LTE stability, battery/power behavior,
    enclosure behavior, GNSS acceptance, or product readiness
---

# LTE-006 Firmware-Side Reliability Non-Claim Observability

## Goal

Connect OBS-004's reliability observability surface to the current firmware
raw LTE `location_observation` path while preserving the Walking Skeleton
boundary: explain the missing pieces, do not claim they are solved.

## Acceptance

- [x] Firmware raw KV `location_observation` reports current LTE network
      observability fields: `network_mode`, `network_rssi`, `network_state`,
      and `network_last_error`.
- [x] Firmware raw KV reports explicit cache non-claim fields:
      `cache_state=not_enabled`, `cache_source_status=unverified`, and
      `cache_last_drop_reason=cache_not_enabled`.
- [x] LTE-005 distinguishes cache non-claim fields from concrete
      cache/drop-message evidence.
- [x] The LTE wire payload remains raw-frame/KV, not JSON.
- [x] Focused tests protect firmware strings and gate classification.
- [x] ESP-IDF build passes without flashing.

## Evidence

- Firmware payload fields:
  `network_mode=LTE`, `network_rssi`, `network_state`,
  `network_last_error`, `cache_state=not_enabled`,
  `cache_source_status=unverified`, and
  `cache_last_drop_reason=cache_not_enabled`.
- LTE-005 gate behavior:
  `cache_state=not_enabled` produces `cache_capability_not_enabled` and keeps
  `G6_RECONNECT_CACHE_OBSERVABILITY` at `WARN` until concrete cache/drop
  counters or store-forward state are observed.
- Focused tests:
  `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_lte_reliability_gate -v`
  passed with 18 tests.
- LTE-005 smoke over the existing LOC-005A export:
  `python scripts\validate_lte_reliability_gate.py --input reports\field_validation\loc005a-source-states-20260630-001\test_run_export.json --output-dir reports\lte_reliability\loc005a-source-states-20260630-001-lte006-smoke --json`
  returned expected `WARN`; cache/drop-message evidence remains absent in that
  old export.
- ESP-IDF guarded build:
  `powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-lte006-reliability-nonclaim -TestRunId lte006-reliability-nonclaim-20260630-001 -BuildDir build_lte006_reliability_nonclaim -EnableSim7670Gnss -EnableSim7670LocationObservation -Build -Json`
  passed and generated
  `firmware/mqtt_heartbeat/build_lte006_reliability_nonclaim/egolink_mqtt_heartbeat.bin`
  (`300496` bytes). The script reported `flash_intentionally_not_run=true`.
- Repository gates:
  `python scripts/context_lint.py` PASS; `git diff --check` PASS;
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` PASS with
  313 tests.

## Completion Boundary

LTE-006 is a firmware/static-build observability increment. It does not flash
hardware, run a USB-Free validation, deploy to the VPS, implement durable
offline cache, prove reconnect recovery, prove long LTE stability, prove
battery/power behavior, or make any product-readiness claim.
