---
id: REL-008
title: KR-006 Raw POST Retry Fault Injection Release
status: completed
priority: high
requires_hardware: false
created: 2026-07-01
last_updated: 2026-07-01

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-008_BOUNDED_RAW_POST_RETRY_OBSERVABILITY.md
  - docs/tasks/done/LTE-009_RAW_POST_RETRY_FAULT_INJECTION.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/key_releases/KR-006_RAW_POST_RETRY_FAULT_INJECTION.json
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-008_KR006_RAW_POST_RETRY_FAULT_RELEASE.md

out_of_scope:
  - flashing firmware
  - running USB-Free hardware validation
  - VPS deployment or GitLab changes
  - changing firmware, protocol fields, raw-frame framing, or Message Hub runtime behavior
  - claiming reconnect recovery, cache durability, long LTE stability,
    battery/power behavior, enclosure behavior, GNSS acceptance, or product readiness
---

# REL-008 KR-006 Raw POST Retry Fault Injection Release

## Goal

Promote the LTE-009 controlled raw POST fail-once runtime proof into a released
engineering key version:

```text
LTE-008 fix1 bounded current-boot raw POST retry
-> LTE-009 first raw location_report POST retained as injected_failure
-> same raw frame retried and derived as location_report
-> raw location_observation exposes retry counters
-> ACK completes command over LTE
-> KR-006 release gate
```

KR-006 freezes a retry-fault evidence slice, not a general reliability or
store-forward claim.

## Acceptance

- [x] Add a machine-readable KR-006 manifest under
      `docs/current/key_releases/`.
- [x] Bind KR-006 to LTE-008 fix1 and LTE-009 implementation/runtime evidence.
- [x] Verify the LTE-009 runtime report shows USB-Free independent-power
      operation, command success, raw retry status `ok`, one retained
      `injected_failure`, and one retry-derived `location_report`.
- [x] Verify the raw-frame export retains the failed raw frame with
      `RAW_POST_FAIL_ONCE_INJECTED` and later retains the same frame payload as
      a successful derived `location_report`.
- [x] Preserve all non-claims around durable cache, reconnect recovery, long
      LTE stability, GNSS acceptance, power behavior, and product readiness.

## Evidence

- Manifest:
  `docs/current/key_releases/KR-006_RAW_POST_RETRY_FAULT_INJECTION.json`.
- LTE-009 task:
  `docs/tasks/done/LTE-009_RAW_POST_RETRY_FAULT_INJECTION.md`.
- LTE-009 build:
  `firmware/mqtt_heartbeat/build_lte009_raw_post_retry_fault/egolink_mqtt_heartbeat.bin`
  (`301776` bytes).
- LTE-009 flash:
  `reports/field_validation/lte009-raw-post-retry-fault-20260701-001/flash_report.md`.
- LTE-009 USB-Free runtime:
  `reports/field_validation/lte009-raw-post-retry-fault-20260701-001/`.
- Runtime command: `cmd-000031` / `request_location`.
- Retained failed raw frame: `loc-cmd-000031`,
  `parse_result.status=injected_failure`,
  `parse_result.error_code=RAW_POST_FAIL_ONCE_INJECTED`.
- Retry-derived raw frame: same `loc-cmd-000031` payload hash, accepted as
  `parse_result.status=ok` and derived as `location_report seq=27`.
- Runtime location observation: raw frame `obs-cmd-000031`, `seq=28`,
  LTE `reason_code=LTE_READY`, cell ID `180571649`, assigned IP
  `10.13.10.229`, `location_belief.state=Unknown`,
  `retry_policy=single_retry_current_boot`, retry counters `1/1/0`, and raw
  POST counters `2/1/1`.
- Runtime ACK: raw frame `cmd-000031`, `seq=29`, status `ok`,
  `LTE_HTTP_OK` / HTTP `200`, retry counters `1/1/0`, and raw POST counters
  `3/2/1`.
- KR-006 gate report:
  `reports/key_releases/KR-006/release_gate_report.json` and
  `reports/key_releases/KR-006/release_gate_report.md`.

## Validation

- `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-006_RAW_POST_RETRY_FAULT_INJECTION.json --json`:
  PASS.
- `python scripts/context_lint.py`: PASS.
- `git diff --check`: PASS.

Previously completed LTE-009 validation bound by this release:

- Focused server/firmware/script tests: PASS, 47 tests.
- Focused validator/runner tests: PASS, 16 tests.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
  319 tests.
- Guarded ESP-IDF build: PASS.
- COM4 flash after explicit operator confirmation: PASS.
- USB-Free runtime after independent power and USB disconnect: PASS.

## Completion Boundary

KR-006 is now a released engineering key version for the controlled raw POST
retry fault-injection slice. It proves one command-scoped injected first-POST
failure, raw retention, retry-derived event creation, observation retry
counters, and ACK over SIM7670G LTE. It does not prove reconnect recovery,
durable offline cache, long LTE stability, GNSS acceptance, battery accuracy,
charging, product power behavior, enclosure behavior, learned model behavior,
or product readiness.
