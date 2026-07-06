---
id: DATA-014
title: Post-run training-chain collector
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/tasks/done/DATA-008_D1_POSTRUN_COLLECTOR.md
  - docs/tasks/done/TRAIN-006_SYNTHETIC_BASELINE_EVAL.md
  - docs/tasks/done/DATA-013_TRAINING_BASELINE_EVAL_VISIBILITY.md

allowed_paths:
  - scripts/collect_d1_postrun.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_postrun_collector.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-014_POSTRUN_TRAINING_CHAIN.md

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - deploying to the VPS or touching GitLab
  - training or evaluating a real model, integrating a GPU runner, private training server, model registry, or OTA path
  - copying candidate DBs, raw candidate records, private coordinates, raw payloads, runtime JSONL logs, or feature-row JSONL to the Dashboard
  - producing model weights, model cards, model artifacts, measured footprint, measured latency, measured power, or release claims
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
---

# Goal

Serve D5: let the normal D1 post-run collector continue from a ready
DATA-006/TRAIN-002 handoff through TRAIN-003, TRAIN-004, TRAIN-005, and
TRAIN-006, so post-field evidence can immediately show whether the dataset is
ready for the next training-runner step.

# Acceptance Criteria

- [x] `scripts/collect_d1_postrun.py` keeps writing a bounded summary when no
      dataset handoff is ready, with `training_chain.status=skipped`.
- [x] When the DATA-006 pipeline returns `ready_for_training_handoff`, the
      collector writes TRAIN-003 preflight, TRAIN-004 feature manifest/rows,
      TRAIN-005 runner dry-run, and TRAIN-006 baseline-eval reports under the
      normal local report roots.
- [x] The training chain keeps `model_training_started=false`,
      `model_evaluation_started=false`, and `model_artifact_written=false` in
      the post-run summary.
- [x] The D1 field kit v6 records the new expected TRAIN-003..006 outputs and
      curated summary sync switches without copying feature-row JSONL or model
      artifacts.
- [x] Focused collector/field-kit tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit -v
python -m py_compile scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/collect_d1_postrun.py`,
  `scripts/prepare_d1_field_kit.py`,
  `quality_tests/test_d1_postrun_collector.py`,
  `quality_tests/test_d1_field_kit.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/current/STATUS.md`, and this
  packet.
- Focused validation passed for the collector and field kit. The ready-handoff
  test builds a reviewed local candidate store, runs the post-run collector,
  and verifies TRAIN-003 `ready_for_training_runner`, TRAIN-004
  `ready_for_feature_runner`, TRAIN-005 `ready_for_runner_execution`, and
  TRAIN-006 `baseline_eval_complete`.
- Remaining risks: DATA-014 still does not train a model or integrate a real
  runner. Real field/session volume, richer feature extraction, local/GPU
  training, model cards, artifact registry, footprint/power measurement,
  shadow-mode deployment, and release gates remain future work.
