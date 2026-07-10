---
id: DATA-031
title: D1 labeling decision template Web/API visibility
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/tasks/done/DATA-030_D1_LABELING_DECISION_TEMPLATE.md

allowed_paths:
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-031_D1_LABELING_DECISION_TEMPLATE_VISIBILITY.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading or exposing sample JSONL rows, raw payloads, exact coordinates, private operator notes, reviewer-private fields, feature rows, targets, candidate DBs, private endpoints, or model artifacts
  - marking items reviewed, applying review decisions, writing candidate DBs, creating training samples, training/evaluating models, measuring model footprint/power, deploying inference, or making release claims
  - contacting hardware, flashing firmware, sending Message Hub commands, or deploying to the VPS
---

# Goal

Serve D5: make the bounded D1 labeling decision template visible in the
Message Hub API and Dashboard so post-run decision-entry work is visible before
any review-application or candidate-store promotion task.

# Acceptance Criteria

- [x] `/api/state` includes a compact `d1_labeling_decision_template` summary.
- [x] `/api/v1/d1-labeling-decision-template/latest` returns the latest compact
      decision template.
- [x] Dashboard renders a `D1 Labeling Decision Template` panel with decision
      progress and non-training gates.
- [x] The VPS deploy helper has an explicit decision-summary switch that copies
      only `d1_labeling_decision_template.json/.md`.
- [x] Field kit post-run sync includes the decision-summary switch.
- [x] Focused tests protect privacy, private-note, and non-training boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server quality_tests.test_d1_field_kit -v
python -m py_compile server\message_hub.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `server/message_hub.py`,
  `scripts/deploy_message_hub_vps.ps1`, `scripts/prepare_d1_field_kit.py`,
  focused dashboard/server endpoint/field-kit tests,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`, `docs/current/STATUS.md`,
  generated progress-board files, and this packet.
- Validation:
  - `python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server quality_tests.test_d1_field_kit -v`
    passed, 71 tests.
  - `python -m py_compile server\message_hub.py scripts\prepare_d1_field_kit.py`
    passed.
  - `python scripts/context_lint.py` passed.
  - `git diff --check` passed with a line-ending warning only for
    `scripts/deploy_message_hub_vps.ps1`.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed, 489
    tests.
- Remaining risks: this is visibility only. Human labeling UI, applying review
  decisions to candidate-store records, training-server integration, model
  training, footprint/power measurement, and on-device deployment remain
  future work.
