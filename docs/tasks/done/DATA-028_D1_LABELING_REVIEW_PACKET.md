---
id: DATA-028
title: D1 labeling review packet and post-run binding
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
  - docs/tasks/done/DATA-026_D1_LABELING_QUEUE_INDEX.md
  - docs/tasks/done/DATA-027_D1_LABELING_QUEUE_VISIBILITY.md

allowed_paths:
  - scripts/build_d1_labeling_review_packet.py
  - scripts/collect_d1_postrun.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_labeling_review_packet.py
  - quality_tests/test_d1_postrun_collector.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-028_D1_LABELING_REVIEW_PACKET.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading or exposing sample JSONL rows, raw payloads, exact coordinates, feature rows, targets, candidate DBs, private endpoints, or model artifacts
  - marking items reviewed, writing candidate DBs, creating training samples, training/evaluating models, measuring model footprint/power, deploying inference, or making release claims
  - contacting hardware, flashing firmware, sending Message Hub commands, or deploying to the VPS
---

# Goal

Serve D5: turn the bounded D1 labeling queue into a human-review work packet
that can be filled before any candidate-store promotion or model training.

# Acceptance Criteria

- [x] A local command builds `d1_labeling_review_packet.json/.md` from a
      bounded `d1_labeling_queue.json`.
- [x] The packet lists required decision slots for operator label, privacy
      review, training consent, split plan, and candidate decision.
- [x] The packet keeps training and candidate-write gates false.
- [x] The D1 post-run collector writes and summarizes the packet after queue
      generation.
- [x] The D1 field kit expects the packet artifact for the next 3-4h run.
- [x] Focused tests protect privacy and non-training boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_labeling_review_packet quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit -v
python -m py_compile scripts\build_d1_labeling_review_packet.py scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/build_d1_labeling_review_packet.py`,
  `scripts/collect_d1_postrun.py`, `scripts/prepare_d1_field_kit.py`,
  focused tests, `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/current/STATUS.md`, generated progress-board files, and this packet.
- Validation:
  - `python -m unittest quality_tests.test_d1_labeling_review_packet quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit -v`
    passed, 9 tests.
  - `python -m py_compile scripts\build_d1_labeling_review_packet.py scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py`
    passed.
  - `python scripts/context_lint.py` passed.
  - `git diff --check` passed with line-ending warnings only for generated
    progress-board files.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed, 481
    tests.
- Remaining risks: this is a review work-packet layer only. Applying decisions
  to candidate-store records, human labeling UI, training-server integration,
  model training, footprint/power measurement, and on-device deployment remain
  future work.
