---
id: DATA-006
title: Data flywheel pipeline runner
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-05
last_updated: 2026-07-05

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/tasks/done/DATA-005_CANDIDATE_REVIEW_QUEUE.md
  - docs/tasks/done/TRAIN-001_DATASET_EXPERIMENT_HANDOFF.md

allowed_paths:
  - scripts/run_data_flywheel_pipeline.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_training_candidate_store.py
  - quality_tests/test_d1_field_kit.py
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/STATUS.md
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/tasks/done/DATA-006_DATA_FLYWHEEL_PIPELINE_RUNNER.md
  - docs/generated/

out_of_scope:
  - training or evaluating a model
  - integrating a GPU runner or real training server
  - scanning runtime folders by default
  - copying raw candidate records, candidate DB files, raw payloads, private coordinates, or runtime JSONL logs
  - changing firmware, public contracts, Message Hub ingest, or on-device inference
  - claiming model accuracy, false-positive rate, latency, footprint, or power impact
---

# Goal

Serve D5: give field/post-run work one repeatable command that ingests named
session recordings, refreshes data-flywheel status, and exports the bounded
dataset handoff manifest without exposing raw records or starting training.

# Acceptance Criteria

- [x] The pipeline can run with no recording directory and report
      `needs_recordings` without scanning runtime folders.
- [x] The pipeline can ingest explicitly named recordings and report
      `needs_review` while preserving bounded summaries only.
- [x] The pipeline can export a ready dataset handoff manifest after candidates
      pass DATA-005 review gates.
- [x] The D1 field kit post-run data step uses the pipeline runner.
- [x] Focused tests and repository validation pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_candidate_store quality_tests.test_d1_field_kit -v
python scripts/context_lint.py
python -m py_compile scripts\run_data_flywheel_pipeline.py scripts\prepare_d1_field_kit.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/run_data_flywheel_pipeline.py`,
  `scripts/prepare_d1_field_kit.py`,
  `quality_tests/test_training_candidate_store.py`,
  `quality_tests/test_d1_field_kit.py`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/STATUS.md`,
  `docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md`, and this packet.
- Validation: focused candidate-store and D1 field-kit tests passed (21 tests);
  `python scripts/context_lint.py` passed; `python -m py_compile
  scripts\run_data_flywheel_pipeline.py scripts\prepare_d1_field_kit.py`
  passed; `git diff --check` passed with CRLF warnings only for generated
  progress-board files; full `scripts\verify.ps1` passed (412 tests).
- Remaining risks: no reviewed default local candidate store exists until real
  or selected recordings are ingested and reviewed; DATA-006 does not train or
  evaluate a model, integrate a training server, deploy on-device inference, or
  claim model metrics, footprint, or power impact.
