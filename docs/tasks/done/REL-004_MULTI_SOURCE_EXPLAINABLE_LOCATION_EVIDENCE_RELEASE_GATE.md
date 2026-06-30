---
id: REL-004
title: Multi-Source Explainable Location Evidence Release Gate
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/KEY_RELEASES.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/key_releases/KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json
  - docs/development/DEV_FLOW.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/DATA-001_LOCATION_FUSION_DATASET_BASELINE.md
  - docs/tasks/done/ALG-000_LOCATION_FUSION_ALGORITHM_DESIGN.md
  - docs/tasks/done/LOC-005A_FIRMWARE_SIDE_OBSERVATION_SOURCE_STATES.md
  - docs/tasks/done/OBS-003_CURRENT_RUN_KEY_RELEASE_FAILURE_VISIBILITY.md
  - docs/tasks/done/ALG-001_SERVER_DERIVED_LOCATION_BELIEF.md

allowed_paths:
  - docs/current/KEY_RELEASES.md
  - docs/current/STATUS.md
  - docs/current/key_releases/KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE_RELEASE_GATE.md
  - scripts/run_key_release_gate.py
  - quality_tests/test_key_release_gate.py

out_of_scope:
  - firmware behavior changes
  - flashing firmware or sending hardware control commands
  - changing device wire protocol or raw-frame profile
  - promoting KR-004 from release_candidate to released
  - training or shipping a learned model
  - claiming product readiness, positioning accuracy, cell-only positioning,
    LTE stability, reconnect recovery, GNSS acceptance, or battery/power
    behavior
  - modifying GitLab or unrelated VPS services
---

# REL-004 Multi-Source Explainable Location Evidence Release Gate

## Goal

Create the KR-004 release-candidate gate for the current explainable
multi-source location evidence path:

```text
LOC-005A source states
-> OBS-003 current run/failure visibility
-> ALG-001 EALE-P0 derived belief
-> DATA-001 dataset-window readiness
```

## Acceptance

- [x] KR-004 manifest exists under `docs/current/key_releases/`.
- [x] `scripts/run_key_release_gate.py` supports JSON evidence assertions.
- [x] KR-004 manifest asserts LOC-005A runtime evidence values.
- [x] KR-004 manifest asserts authenticated current-run EALE-P0 values.
- [x] KR-004 gate report is generated under `reports/key_releases/KR-004/`.
- [x] VPS Message Hub current run identifies as `KR-004` /
      `release_candidate`.
- [x] Existing GitLab service remains active.

## Validation

- `python -m unittest quality_tests.test_key_release_gate -v` passed with
  6 tests.
- `python -m unittest quality_tests.test_key_release_gate quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard -v`
  passed with 27 tests.
- `python scripts\run_key_release_gate.py --manifest docs\current\key_releases\KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json --json`
  passed.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  304 tests.
- `git diff --check` passed.
- KR-004 gate report paths:
  - `reports/key_releases/KR-004/release_gate_report.json`
  - `reports/key_releases/KR-004/release_gate_report.md`
- VPS smoke after manifest deployment:
  - public `/health` returned `ok=true`;
  - unauthenticated `/api/state` returned HTTP 401;
  - authenticated `/api/state.current_run.key_release.release_id` returned
    `KR-004`;
  - current run remained `Unknown` / `no_precise_fix`, dataset window
    `failure_window` / `candidate_with_warnings`, and
    `training_allowed=false`.

## Boundaries

- KR-004 remains a release candidate, not a released engineering key version.
- This task adds a release gate only. It does not change firmware, hardware,
  raw-frame wire format, DATA-001 schema, model behavior, or product claims.
