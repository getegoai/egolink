---
id: LTE-010
title: Reconnect Store-Forward Gate Baseline
status: completed
priority: high
requires_hardware: false
created: 2026-07-01
last_updated: 2026-07-01

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-009_RAW_POST_RETRY_FAULT_INJECTION.md
  - quality_tests/AGENTS.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/LTE-010_RECONNECT_STORE_FORWARD_GATE_BASELINE.md
  - scripts/validate_lte_reconnect_store_forward_gate.py
  - quality_tests/test_lte_reconnect_store_forward_gate.py

out_of_scope:
  - flashing firmware
  - running USB-Free hardware validation
  - VPS deployment or GitLab changes
  - changing live firmware behavior, raw-frame framing, or Message Hub runtime behavior
  - claiming reconnect recovery, durable store-forward, long LTE stability,
    battery/power behavior, enclosure behavior, GNSS acceptance, or product readiness
---

# LTE-010 Reconnect Store-Forward Gate Baseline

## Goal

Create a reusable offline gate that prevents the project from treating
visibility fields as reconnect or durable store-forward proof. LTE-010 reads an
existing Message Hub `test_run_export.json` and classifies whether the export
contains enough evidence for the next R3 reliability step.

```text
existing test_run_export.json
-> LTE runtime/raw evidence
-> reconnect attempt count + reason
-> network/LTE/HTTP failure reason
-> later successful LTE ACK after reconnect evidence
-> observed store-forward queue/drop/age evidence
```

## Acceptance

- [x] Add `scripts/validate_lte_reconnect_store_forward_gate.py`.
- [x] Gate PASS requires a concrete reconnect attempt, visible failure reason,
      post-reconnect LTE ACK, and observed store-forward queue/drop/age
      evidence.
- [x] Gate WARN when an export is explainable but does not exercise reconnect
      or durable store-forward behavior.
- [x] Gate FAIL when reconnect or store-forward is claimed without enough
      evidence.
- [x] Validate the current LTE-009 export as expected `WARN`, not PASS.
- [x] Add focused unit tests for WARN, PASS, and FAIL paths.

## Evidence

- Gate script:
  `scripts/validate_lte_reconnect_store_forward_gate.py`.
- Focused tests:
  `quality_tests/test_lte_reconnect_store_forward_gate.py`.
- LTE-009 baseline export check:
  `reports/lte_reconnect_store_forward/lte009-raw-post-retry-fault-20260701-001/`.

## Validation

- `python -m unittest quality_tests.test_lte_reconnect_store_forward_gate -v`:
  PASS, 5 tests.
- `python scripts\validate_lte_reconnect_store_forward_gate.py --input reports\field_validation\lte009-raw-post-retry-fault-20260701-001\test_run_export.json --output-dir reports\lte_reconnect_store_forward\lte009-raw-post-retry-fault-20260701-001 --json`:
  expected `WARN`, with `G1_LTE_RUNTIME_CHAIN=PASS`,
  reconnect gates `NOT_OBSERVED`, and `G5_STORE_FORWARD_EVIDENCE=WARN`
  because only `volatile_outbox` evidence is present.

## Completion Boundary

LTE-010 is a non-hardware offline gate baseline. It does not implement modem
reconnect recovery, durable local storage, queue replay, firmware changes, VPS
runtime changes, long LTE stability, GNSS acceptance, battery/power behavior,
enclosure behavior, learned model behavior, or product readiness.
