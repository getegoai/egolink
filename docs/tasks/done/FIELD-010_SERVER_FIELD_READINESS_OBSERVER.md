---
id: FIELD-010
title: Server field readiness observer
status: done
priority: high
requires_hardware: false
serves_demo: D2
created: 2026-07-10
completed: 2026-07-10

context:
  - docs/product/NORTH_STAR.md
  - docs/development/FIELD_TEST.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md
  - docs/tasks/active/D5-001_LOCATION_DATA_FLYWHEEL_MAINLINE.md

allowed_paths:
  - scripts/observe_field_readiness.py
  - quality_tests/test_field_readiness_observer.py
  - docs/development/FIELD_TEST.md
  - docs/current/STATUS.md
  - docs/current/progress_board_config.json
  - docs/generated/
  - docs/tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md
  - docs/tasks/active/D5-001_LOCATION_DATA_FLYWHEEL_MAINLINE.md
  - docs/tasks/done/FIELD-010_SERVER_FIELD_READINESS_OBSERVER.md

out_of_scope:
  - contacting serial hardware, flashing firmware, erasing flash, or sending Message Hub commands
  - deploying to the VPS or changing GitLab
  - changing firmware, protocol fields, model behavior, training behavior, or Dashboard API contracts
  - exposing raw private coordinates, raw payload bytes, tokens, or private device logs
  - claiming GNSS acceptance, product location accuracy, LTE long-run stability, battery life, model performance, or product readiness
---

# Goal

Serve D2/D5: make the server-side field-test surface checkable before and
during unattended outdoor sessions.

# Acceptance Criteria

- [x] A read-only command checks Message Hub health, `/api/state`, Dashboard
      HTML markers, target-device freshness, D1 field readiness, map status,
      Field Test Results, and D5 data-flywheel summaries.
- [x] The command supports one-shot preflight and long-duration polling with an
      incremental JSONL sample stream and bounded JSON/Markdown report.
- [x] Reports are written under `reports/field_readiness/<run-id>/`.
- [x] The command reads auth from environment or the ignored local token file
      without writing secrets into reports.
- [x] Focused tests prove it does not enqueue commands and fails explainably
      when the target device is missing.

# Validation Commands

```powershell
python -m unittest quality_tests.test_field_readiness_observer -v
python -m py_compile scripts\observe_field_readiness.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/observe_field_readiness.py`,
  `quality_tests/test_field_readiness_observer.py`,
  `docs/development/FIELD_TEST.md`, `docs/current/STATUS.md`,
  `docs/current/progress_board_config.json`, D2/D5 active task notes, generated
  progress board, and this packet.
- Focused tests cover PASS on fresh server/Dashboard state, explainable FAIL
  for a missing target device, and long-window upload progress detection.
- Remaining risks: this is a server-side readiness observer only. The first
  real D2 FIELD-003 reference-point run and post-run D2/D5 analysis remain
  pending operator outdoor evidence.
