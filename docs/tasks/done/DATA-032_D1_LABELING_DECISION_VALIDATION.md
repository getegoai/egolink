---
id: DATA-032
title: D1 labeling decision template validation
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-07
last_updated: 2026-07-07

context:
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/tasks/done/DATA-030_D1_LABELING_DECISION_TEMPLATE.md
  - docs/tasks/done/DATA-031_D1_LABELING_DECISION_TEMPLATE_VISIBILITY.md

allowed_paths:
  - scripts/validate_d1_labeling_decision_template.py
  - scripts/collect_d1_postrun.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_labeling_decision_validation.py
  - quality_tests/test_d1_postrun_collector.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-032_D1_LABELING_DECISION_VALIDATION.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading sample JSONL rows, raw payloads, exact coordinates, private operator notes, feature rows, targets, candidate DBs, private endpoints, or model artifacts
  - applying decisions, writing candidate DBs, creating training samples, training/evaluating models, measuring model footprint/power, deploying inference, or making release claims
  - contacting hardware, flashing firmware, sending Message Hub commands, deploying to the VPS, or modifying GitLab
---

# Goal

Serve D5: validate filled D1 labeling decision templates before any explicit
candidate-store promotion task.

# Acceptance Criteria

- [x] `scripts/validate_d1_labeling_decision_template.py` writes bounded
      `d1_labeling_decision_validation.json/.md` reports.
- [x] Missing selected values produce `needs_decisions`; invalid selected
      values produce `invalid_decisions`.
- [x] Fully approved operator/privacy/consent/split/candidate selections are
      marked ready for a future candidate-promotion task without writing a DB.
- [x] The D1 post-run collector binds the validation report after generating a
      decision template.
- [x] Field kit v16 expects the validation artifact.
- [x] Focused tests protect private data and non-training boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_labeling_decision_validation quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit -v
python -m py_compile scripts\validate_d1_labeling_decision_template.py scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: new validation script and tests, post-run collector, D1 field
  kit, data-flywheel plan, status note, generated progress board, and this
  packet.
- Validation:
  - `python -m unittest quality_tests.test_d1_labeling_decision_validation quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit -v`
    passed, 11 tests.
  - `python -m py_compile scripts\validate_d1_labeling_decision_template.py scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py`
    passed.
  - `python scripts/context_lint.py` passed.
  - `git diff --check` passed with CRLF/LF warnings only for generated progress
    board files.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed, 493
    tests.
- Remaining risks: Web/API visibility for the validation report, human-friendly
  labeling UI, explicit candidate-store promotion, training-server integration,
  model training, footprint/power measurement, and on-device deployment remain
  future work.
