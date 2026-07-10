---
id: REL-002
title: Explainable LTE Location Observation Release Gate
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/KEY_RELEASES.md
  - docs/development/DEV_FLOW.md
  - docs/development/FIELD_TEST.md
  - docs/tasks/done/LOC-004A_REAL_CELL_LOCATION_OBSERVATION.md
  - docs/tasks/done/FIELD-002_USB_FREE_REBOOT_AWARE_COMMAND_VALIDATOR.md
  - docs/tasks/done/FIELD-002A_REBOOT_AWARE_VALIDATOR_USB_FREE_SMOKE.md

allowed_paths:
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-003_EXPLAINABLE_LTE_LOCATION_OBSERVATION.json
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-002_EXPLAINABLE_LTE_LOCATION_OBSERVATION_RELEASE_GATE.md

out_of_scope:
  - firmware changes or flashing
  - new hardware runtime validation
  - changing Message Hub, Web, protocol, or public contracts
  - modifying GitLab or unrelated VPS services
  - long LTE stability, reconnect, battery, power, enclosure, or product readiness
---

# REL-002 Explainable LTE Location Observation Release Gate

## Goal

Publish the next Ego Link P0 engineering key release after KR-001 by freezing
the explainable USB-Free LTE location observation baseline:

```text
request_location
-> raw LTE location_report
-> raw LTE location_observation
-> raw LTE ACK
-> reboot-aware field validator can arm and reconcile one command
```

## Result

Completed. KR-003 is recorded as
`USB-Free Explainable LTE Location Observation Walking Skeleton`, release
version `0.1.0-key-release-003`.

## Evidence

- Release index: `docs/current/KEY_RELEASES.md`.
- Release manifest:
  `docs/current/key_releases/KR-003_EXPLAINABLE_LTE_LOCATION_OBSERVATION.json`.
- Gate script: `scripts/run_key_release_gate.py`.
- Gate report:
  `reports/key_releases/KR-003/release_gate_report.json` and
  `reports/key_releases/KR-003/release_gate_report.md`.
- LOC-004A task packet:
  `docs/tasks/done/LOC-004A_REAL_CELL_LOCATION_OBSERVATION.md`.
- FIELD-002 tooling packet:
  `docs/tasks/done/FIELD-002_USB_FREE_REBOOT_AWARE_COMMAND_VALIDATOR.md`.
- FIELD-002A hardware smoke packet:
  `docs/tasks/done/FIELD-002A_REBOOT_AWARE_VALIDATOR_USB_FREE_SMOKE.md`.

## Validation

- `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-003_EXPLAINABLE_LTE_LOCATION_OBSERVATION.json --json`
  PASS: 7 gates, 19 evidence items, 4 required commits, no errors, no
  warnings.
- `python scripts\context_lint.py`
- `git diff --check`

Prior implementation gates already ran:

- `python -m unittest quality_tests.test_lte_command_loop_validation quality_tests.test_fw001_hw_runner -v`
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`

## Boundary

KR-003 is an engineering key release. It proves the bounded USB-Free raw LTE
`request_location -> location_report -> location_observation -> ACK` loop and
the reboot-aware validator workflow. It does not prove GNSS fix, cell-only
positioning, learned location memory, long LTE stability, reconnect recovery,
battery/power behavior, enclosure behavior, or product readiness.
