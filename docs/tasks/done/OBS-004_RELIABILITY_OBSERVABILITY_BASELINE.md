---
id: OBS-004
title: Reliability Observability Baseline
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/development/DEV_FLOW.md
  - docs/development/PROTOCOL.md
  - docs/development/FIELD_TEST.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-005_LTE_RELIABILITY_GATE_BASELINE.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/development/PROTOCOL.md
  - docs/development/FIELD_TEST.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/OBS-004_RELIABILITY_OBSERVABILITY_BASELINE.md
  - server/message_hub.py
  - shared/contracts/message_hub_event.schema.json
  - shared/contracts/message_hub_status.schema.json
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_message_hub_dashboard.py

out_of_scope:
  - firmware behavior changes or flashing
  - VPS deployment
  - changing required protocol fields or raw-frame framing
  - long LTE stability, reconnect recovery, cache durability, battery/power,
    enclosure, GNSS acceptance, or product-readiness claims
---

# OBS-004 Reliability Observability Baseline

## Goal

Make reconnect/cache/drop-message evidence first-class in Message Hub exports
and Web visibility before the project starts long LTE reliability testing:

```text
firmware/simulator status, event, ACK, or raw-frame KV
-> optional reliability.network/cache fields
-> Message Hub raw/message storage
-> observability.reliability
-> run_context.reliability
-> Dashboard reconnect/cache rows
-> LTE-005 can detect real evidence when firmware reports it
```

## Acceptance

- [x] Message Hub accepts optional `reliability.network` and
      `reliability.cache` groups on JSON messages.
- [x] Raw-frame KV payloads can derive the same reliability structure.
- [x] `/api/state`, test-run export, and current-run context expose the
      derived reliability group.
- [x] Dashboard displays reconnect/error and cache queue/drop fields.
- [x] Status/event schemas allow the additive `reliability` object.
- [x] Current LOC-005A export remains `WARN` under LTE-005 until real
      cache/drop-message evidence exists.

## Field Shape

Recommended JSON shape:

```json
{
  "reliability": {
    "network": {
      "mode": "LTE",
      "rssi": -89,
      "reconnect_count": 2,
      "last_error": "LTE_RECONNECT_TIMEOUT",
      "last_reconnect_reason": "pdp_reactivate",
      "state": "reconnecting"
    },
    "cache": {
      "queued_message_count": 3,
      "dropped_message_count": 1,
      "last_drop_reason": "cache_full",
      "oldest_message_age_ms": 42000,
      "state": "store_forward"
    }
  }
}
```

Raw-frame KV uses normalized keys such as `network_reconnect_count`,
`network_last_error`, `network_last_reconnect_reason`,
`cache_queued_message_count`, `cache_dropped_message_count`,
`cache_last_drop_reason`, and `cache_oldest_message_age_ms`.

## Validation

- `python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard quality_tests.test_lte_reliability_gate quality_tests.model_contract.test_contract_schemas -v`:
  PASS, 31 tests.
- `python scripts\validate_lte_reliability_gate.py --input reports\field_validation\loc005a-source-states-20260630-001\test_run_export.json --output-dir reports\lte_reliability\loc005a-source-states-20260630-001-obs004-smoke`:
  `WARN`, expected because the existing LOC-005A export still lacks real
  cache/drop-message evidence.
- `python scripts/context_lint.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
  312 tests.
- `git diff --check`: PASS.

## Completion Boundary

OBS-004 is a server/Web/contract visibility baseline only. It does not change
firmware runtime behavior, send hardware commands, deploy to the VPS, prove
long LTE stability, prove reconnect recovery, prove cache durability, or make
any product-readiness claim.
