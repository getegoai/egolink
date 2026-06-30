---
id: REL-005
title: KR-004 Promotion Review
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30
completed: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json
  - docs/development/DEV_FLOW.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/tasks/done/REL-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE_RELEASE_GATE.md
  - docs/tasks/done/ALG-002_EALE_P0_DATASET_COVERAGE_EVALUATION.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-005_KR004_PROMOTION_REVIEW.md

out_of_scope:
  - firmware changes or flashing
  - sending hardware control commands
  - changing live device wire protocol or raw-frame profile
  - changing DATA-001 sample schema
  - changing Message Hub runtime behavior
  - training or shipping a learned model
  - claiming GNSS acceptance, cell-only positioning, positioning accuracy, LTE stability, reconnect recovery, battery/power behavior, or product readiness
  - modifying GitLab or unrelated VPS services
---

# REL-005 KR-004 Promotion Review

## Goal

Promote KR-004 from release candidate to released engineering key version after
the explicit post-candidate review evidence exists:

```text
REL-004 release-candidate gate
-> ALG-002 DATA-001/EALE-P0 coverage review
-> KR-004 released engineering key version
```

## Result

Completed. KR-004 is recorded as released engineering key version
`0.1.0-key-release-004`.

## Evidence

- Release index: `docs/current/KEY_RELEASES.md`.
- Release manifest:
  `docs/current/key_releases/KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json`.
- REL-004 release-candidate packet:
  `docs/tasks/done/REL-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE_RELEASE_GATE.md`.
- ALG-002 coverage packet:
  `docs/tasks/done/ALG-002_EALE_P0_DATASET_COVERAGE_EVALUATION.md`.
- KR-004 gate report:
  `reports/key_releases/KR-004/release_gate_report.json` and
  `reports/key_releases/KR-004/release_gate_report.md`.
- ALG-002 coverage report:
  `reports/location_fusion_eale/loc005a-source-states-20260630-001/eale_p0_dataset_report.json`
  and
  `reports/location_fusion_eale/loc005a-source-states-20260630-001/eale_p0_dataset_report.md`.

## Promotion Review

- KR-004 gate: pass.
- ALG-002 report: `warn`, acceptable for release review.
- Release-review support: `true`.
- Model-training readiness: `false`.
- Fine candidates: `0`.
- Retained failure windows: `1`.
- Current location state remains `Unknown` / `no_precise_fix`.
- VPS current-run key-release status after deploy: `KR-004` / `released` /
  `0.1.0-key-release-004`.

This promotes the explainable evidence baseline, not a positioning system. The
retained failure window is part of the value of KR-004: a no-fix location
attempt is now preserved, surfaced, and reviewable instead of disappearing
into a blind failure.

## Validation

- `python scripts\run_key_release_gate.py --manifest docs\current\key_releases\KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json --json`
  passed after promotion.
- `python scripts\evaluate_eale_p0_dataset.py --dataset-dir reports\location_fusion_datasets\loc005a-source-states-20260630-001 --output-dir reports\location_fusion_eale\loc005a-source-states-20260630-001 --json`
  passed with `result.status=warn`.
- `python -m unittest quality_tests.test_key_release_gate quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard quality_tests.test_eale_p0_dataset_evaluation -v`
  passed with 30 tests.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  307 tests.
- `git diff --check` passed.
- VPS smoke after manifest deployment:
  - public `/health` returned `ok=true`;
  - unauthenticated `/api/state` returned HTTP 401;
  - authenticated `/api/state.current_run.key_release` returned `KR-004` /
    `released` / `0.1.0-key-release-004`;
  - authenticated `/api/state.current_run.eale_p0` remained `Unknown` /
    `no_precise_fix`, dataset window `failure_window`, and
    `training_allowed=false`;
  - existing GitLab service remained active.

## Boundary

REL-005 is a release-status promotion only. It does not change firmware,
hardware state, raw-frame payload shape, public device wire protocol, DATA-001
schema, Message Hub runtime behavior, learned model behavior, GNSS behavior,
LTE stability, reconnect behavior, battery/power behavior, or product
readiness.
