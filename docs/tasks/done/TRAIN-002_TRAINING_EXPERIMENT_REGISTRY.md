---
id: TRAIN-002
title: Training experiment registry
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
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/tasks/done/TRAIN-001_DATASET_EXPERIMENT_HANDOFF.md
  - docs/tasks/done/DATA-006_DATA_FLYWHEEL_PIPELINE_RUNNER.md

allowed_paths:
  - scripts/register_training_experiment.py
  - scripts/run_data_flywheel_pipeline.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_training_experiment_registry.py
  - quality_tests/test_training_candidate_store.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/STATUS.md
  - docs/tasks/done/TRAIN-002_TRAINING_EXPERIMENT_REGISTRY.md

out_of_scope:
  - training or evaluating a model
  - integrating a GPU runner or real training server
  - producing model weights, model cards, measured metrics, or release claims
  - exporting raw candidate records, DB files, raw payloads, private coordinates, or runtime JSONL logs
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
  - claiming model accuracy, false-positive rate, latency, footprint, or power impact
---

# Goal

Serve D5: register a bounded training experiment plan from the TRAIN-001
dataset manifest so the future training runner has an audited handoff point
with readiness, gates, planned metrics, and non-claims.

# Acceptance Criteria

- [x] A CLI can consume a dataset manifest and write
      `training_experiment_plan.json/.md`.
- [x] Not-ready manifests produce explicit blocked experiment statuses without
      exposing raw records or local source paths.
- [x] Ready manifests produce `ready_for_runner` only when eligible reviewed
      records exist.
- [x] DATA-006 pipeline reports include the experiment plan artifact and keep
      the existing no-runtime-scan boundary.
- [x] The D1 field kit records the expected post-run experiment-plan output.
- [x] Focused tests and repository validation pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_experiment_registry quality_tests.test_training_candidate_store quality_tests.test_d1_field_kit -v
python -m py_compile scripts\register_training_experiment.py scripts\run_data_flywheel_pipeline.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/register_training_experiment.py`,
  `scripts/run_data_flywheel_pipeline.py`, `scripts/prepare_d1_field_kit.py`,
  `quality_tests/test_training_experiment_registry.py`,
  `quality_tests/test_training_candidate_store.py`,
  `quality_tests/test_d1_field_kit.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/STATUS.md`, and this packet.
- Validation: focused registry/candidate-store/D1 field-kit tests passed (24
  tests); `python -m py_compile scripts\register_training_experiment.py
  scripts\run_data_flywheel_pipeline.py scripts\prepare_d1_field_kit.py`
  passed; `python scripts\context_lint.py` passed; `git diff --check` passed;
  full `scripts\verify.ps1` passed (415 tests).
- Remaining risks: no reviewed default local candidate store exists until real
  or selected recordings are ingested and reviewed; TRAIN-002 does not train or
  evaluate a model, integrate a training server, produce model weights, deploy
  on-device inference, or claim model metrics, footprint, or power impact.
