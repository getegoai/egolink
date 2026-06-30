---
id: ALG-001
title: Server Derived EALE-P0 Location Belief
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/DATA-001_LOCATION_FUSION_DATASET_BASELINE.md
  - docs/tasks/done/ALG-000_LOCATION_FUSION_ALGORITHM_DESIGN.md
  - docs/tasks/done/LOC-005A_FIRMWARE_SIDE_OBSERVATION_SOURCE_STATES.md
  - docs/tasks/done/OBS-003_CURRENT_RUN_KEY_RELEASE_FAILURE_VISIBILITY.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/development/PROTOCOL.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/ALG-001_SERVER_DERIVED_LOCATION_BELIEF.md
  - server/message_hub.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_message_hub_dashboard.py

out_of_scope:
  - firmware behavior changes
  - flashing firmware or sending hardware control commands
  - changing device wire protocol or raw-frame profile
  - training or shipping a learned model
  - claiming cell-only positioning or product positioning accuracy
  - creating a new key release
  - modifying GitLab or unrelated VPS services
---

# ALG-001 Server Derived EALE-P0 Location Belief

## Goal

Add an optional server-side EALE-P0 derived belief view for the current
Message Hub run so Web/API/report consumers can see why the location state is
`Fine`, `Coarse`, `Predicted`, or `Unknown` without changing firmware or the
device wire protocol.

## Acceptance

- [x] `/api/state.current_run.eale_p0` includes derived `location_belief`,
      normalized evidence, and dataset-window readiness.
- [x] Test-run export `run_context.eale_p0` carries the same derived view.
- [x] `observability_summary.eale_p0` carries the same EALE-P0 summary for
      report consumers.
- [x] Dashboard Run Context renders EALE-P0 state, reason, failure reason,
      dataset window, training flag, and quality flags.
- [x] Cell/LTE evidence does not create a precise position by itself.
- [x] Wi-Fi, IMU, and power source-state slots are represented as evidence and
      quality flags, not inferred capabilities.

## Implementation

- Added EALE-P0 helper functions in `server/message_hub.py`.
- EALE-P0 currently produces a conservative derived belief:
  - trusted GNSS fix can produce `Fine`;
  - last-known memory plus GNSS no-fix can produce `Predicted`;
  - cell/LTE-only evidence remains `Unknown` with an explanatory reason;
  - missing reports, parse failures, pending commands, and no-fix evidence
    remain dataset candidates rather than being hidden.
- Added dataset-window readiness metadata with sample type, lineage counts,
  blockers, warnings, and `training_allowed=false` until privacy and labels are
  explicit.

## Validation

- `python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard -v`
  passed with 21 tests during implementation.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  301 tests.
- `git diff --check` passed.
- VPS deploy smoke passed: public `/health` returned `ok=true`, public `/`
  contained EALE-P0 fields, unauthenticated `/api/state` returned HTTP 401,
  authenticated `/api/state.current_run.eale_p0` reported the LOC-005A run as
  `Unknown` / `no_precise_fix`, dataset window `failure_window` /
  `candidate_with_warnings`, and existing GitLab remained active.

## Boundaries

- This is a Server-Web/report visibility increment only.
- It does not change firmware, hardware state, raw-frame payload shape, public
  device wire protocol, DATA-001 sample schema, learned model behavior, key
  release status, GNSS behavior, LTE stability, battery/power behavior, or
  product readiness.
