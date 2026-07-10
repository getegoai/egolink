---
id: DATA-030
title: D1 labeling decision template and post-run binding
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
  - docs/tasks/done/DATA-028_D1_LABELING_REVIEW_PACKET.md
  - docs/tasks/done/DATA-029_D1_LABELING_REVIEW_PACKET_VISIBILITY.md

allowed_paths:
  - scripts/build_d1_labeling_decision_template.py
  - scripts/collect_d1_postrun.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_labeling_decision_template.py
  - quality_tests/test_d1_postrun_collector.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-030_D1_LABELING_DECISION_TEMPLATE.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading or exposing sample JSONL rows, raw payloads, exact coordinates, reviewer-private fields, feature rows, targets, candidate DBs, private endpoints, or model artifacts
  - marking items reviewed, applying review decisions, writing candidate DBs, creating training samples, training/evaluating models, measuring model footprint/power, deploying inference, or making release claims
  - contacting hardware, flashing firmware, sending Message Hub commands, or deploying to the VPS
---

# Goal

Serve D5: turn the bounded D1 labeling review packet into a fillable decision
template that can be completed before any explicit review-application or
candidate-store promotion task.

# Acceptance Criteria

- [x] A local command builds `d1_labeling_decision_template.json/.md` from a
      bounded `d1_labeling_review_packet.json`.
- [x] The template lists operator label, privacy review, training consent,
      split plan, and candidate decision fields for each packet item.
- [x] The template keeps selected decisions empty and candidate/training gates
      false.
- [x] The D1 post-run collector writes and summarizes the template after review
      packet generation.
- [x] The D1 field kit expects the decision-template artifact for the next 3-4h
      run.
- [x] Focused tests protect privacy, private-review-field, and non-training
      boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_labeling_decision_template quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit -v
python -m py_compile scripts\build_d1_labeling_decision_template.py scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/build_d1_labeling_decision_template.py`,
  `scripts/collect_d1_postrun.py`, `scripts/prepare_d1_field_kit.py`,
  focused tests, `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/current/STATUS.md`, generated progress-board files, and this packet.
- Validation:
  - `python -m unittest quality_tests.test_d1_labeling_decision_template quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit -v`
    passed, 9 tests.
  - `python -m py_compile scripts\build_d1_labeling_decision_template.py scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py`
    passed.
  - `python scripts/context_lint.py` passed.
  - `git diff --check` passed.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed, 486
    tests.
- Remaining risks: this is a fillable template layer only. Applying decisions
  to candidate-store records, human labeling UI, training-server integration,
  model training, footprint/power measurement, and on-device deployment remain
  future work.
