---
id: DATA-026
title: D1 labeling queue index and post-run binding
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/tasks/done/DATA-024_D1_LABELING_INTAKE_VISIBILITY.md
  - docs/tasks/done/DATA-025_POSTRUN_LABELING_INTAKE_BINDING.md

allowed_paths:
  - scripts/summarize_d1_labeling_queue.py
  - scripts/collect_d1_postrun.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_labeling_queue.py
  - quality_tests/test_d1_postrun_collector.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/current/STATUS.md
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/tasks/done/DATA-026_D1_LABELING_QUEUE_INDEX.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading or exposing `d1_field_samples.jsonl`, raw payloads, private coordinates, feature rows, targets, candidate DBs, or model artifacts
  - writing candidate DBs, creating training samples, training/evaluating models, measuring model footprint/power, or deploying inference
  - contacting hardware, opening serial ports, flashing firmware, sending Message Hub commands, or deploying to the VPS
  - changing firmware, protocol, public APIs, model behavior, training behavior, or release gates
---

# Goal

Serve D5: make D1 post-run labeling/privacy work visible as a bounded queue
before any candidate-store write or model training step.

# Acceptance Criteria

- [x] A local command scans bounded `d1_labeling_intake` summaries and writes a
      compact JSON/Markdown queue index.
- [x] The queue shows pending labels, privacy review, consent decision, split
      plan, sample counts, GNSS-fix flag, and blockers without private details.
- [x] The D1 post-run collector writes and summarizes the queue after labeling
      intake succeeds.
- [x] The D1 field kit expects the queue artifact for the next 3-4h field run.
- [x] Focused tests protect privacy and post-run wiring.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_labeling_queue -v
python -m unittest quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit -v
python -m py_compile scripts\summarize_d1_labeling_queue.py scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/summarize_d1_labeling_queue.py`,
  `scripts/collect_d1_postrun.py`, `scripts/prepare_d1_field_kit.py`,
  focused tests, `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/current/STATUS.md`,
  `docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md`, generated
  progress-board files, and this packet.
- Validation: focused queue tests passed (2 tests); focused post-run/field-kit
  tests passed (7 tests); `python -m py_compile` passed for the new queue,
  post-run collector, and field-kit scripts; `python scripts/context_lint.py`
  passed; `git diff --check` passed with generated-file CRLF warnings only;
  full `scripts\verify.ps1` passed (476 tests).
- Remaining risks: this is a queue/index layer only. Human labeling UI,
  candidate-store promotion, real training-server integration, model training,
  footprint/power measurement, and on-device deployment remain future work.
