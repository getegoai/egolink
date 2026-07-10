---
id: LTE-005
title: LTE Reliability Gate Baseline
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/FIELD_TEST.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/OBS-003_CURRENT_RUN_KEY_RELEASE_FAILURE_VISIBILITY.md
  - docs/tasks/done/LOC-005A_FIRMWARE_SIDE_OBSERVATION_SOURCE_STATES.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/development/FIELD_TEST.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/LTE-005_LTE_RELIABILITY_GATE_BASELINE.md
  - scripts/validate_lte_reliability_gate.py
  - quality_tests/test_lte_reliability_gate.py

out_of_scope:
  - firmware behavior changes
  - flashing firmware or sending hardware commands
  - VPS runtime behavior changes or deployment
  - changing raw-frame profile, public protocol fields, or Message Hub schema
  - claiming long LTE stability, reconnect recovery, battery/power behavior,
    enclosure behavior, or product readiness
---

# LTE-005 LTE Reliability Gate Baseline

## Goal

Turn the current LTE/reconnect/stability discussion into a reusable offline
release gate before any long field run:

```text
existing Message Hub test_run_export.json
-> command lifecycle visibility
-> stale/pending and failure-reason visibility
-> duplicate execution guard visibility
-> LTE transport/reason-code evidence
-> raw-frame retention evidence
-> reconnect/cache/sequence observability gaps
-> JSON/Markdown gate report
```

This task is intentionally non-hardware. It creates the gate that makes later
hardware runs explainable; it does not run a new physical stability test.

## Acceptance

- [x] Add an offline LTE reliability gate script.
- [x] Gate reads existing Message Hub `test_run_export.json`.
- [x] Gate fails on missing LTE transport evidence, missing raw-frame
      retention, unexplained stale pending command, or repeated command
      execution without duplicate prevention.
- [x] Gate warns when reconnect/cache/stale behavior is not exercised instead
      of claiming product stability.
- [x] Gate writes JSON and Markdown reports.
- [x] Focused tests cover KR-004-shaped evidence, stale pending explanation,
      duplicate-execution risk, and CLI report writing.
- [x] Run the gate over the current LOC-005A export.

## Implementation

- New script:
  `scripts/validate_lte_reliability_gate.py`.
- New tests:
  `quality_tests/test_lte_reliability_gate.py`.
- The gate statuses are:
  - `PASS`: behavior is present and explainable;
  - `WARN`: evidence is partial or a behavior was not exercised;
  - `NOT_OBSERVED`: the export does not include that scenario;
  - `FAIL`: the export would make the next run unsafe or blind to interpret.
- The gate checks:
  - command `cmd_id`, status, timestamps, and ACK visibility;
  - stale/pending command explanation;
  - `command.command_count` and
    `duplicate_local_execution_prevented`;
  - `transport.type=lte` plus LTE/HTTP reason codes;
  - no-fix/failure reason visibility;
  - reconnect/reset and cache/drop-message observability;
  - raw-frame hash/length/CRC retention;
  - sequence reset or duplicate visibility.

## Evidence

- LOC-005A offline gate command:
  `python scripts\validate_lte_reliability_gate.py --input reports\field_validation\loc005a-source-states-20260630-001\test_run_export.json --output-dir reports\lte_reliability\loc005a-source-states-20260630-001 --json`.
- LOC-005A offline gate result: `WARN`.
- Report paths:
  `reports/lte_reliability/loc005a-source-states-20260630-001/lte_reliability_gate_report.json`
  and
  `reports/lte_reliability/loc005a-source-states-20260630-001/lte_reliability_gate_report.md`.
- Meaning of the current `WARN`:
  - command lifecycle, LTE transport, LTE/HTTP reason codes, duplicate guard
    fields, no-fix explanation, and raw-frame retention are visible;
  - cache/drop-message observability is not present in the current export;
  - message sequence reset/duplicate behavior is visible and should be planned
    into the later long-run gate;
  - no long LTE stability or product readiness claim is made.

## Validation

- `python -m unittest quality_tests.test_lte_reliability_gate -v`: PASS,
  4 tests.
- `python -m unittest quality_tests.test_lte_reliability_gate quality_tests.test_lte_command_loop_validation -v`:
  PASS, 13 tests.
- `python scripts/context_lint.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
  311 tests.
- `git diff --check`: PASS.

## Completion Boundary

LTE-005 is offline gate tooling only. It does not flash firmware, contact
hardware, send Message Hub commands, deploy to the VPS, change protocol fields,
or prove reconnect recovery, long LTE stability, battery/power behavior,
enclosure behavior, or product readiness.
