---
id: DATA-016
title: Post-run handoff collector
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
  - docs/tasks/done/DATA-014_POSTRUN_TRAINING_CHAIN.md
  - docs/tasks/done/TRAIN-007_TRAINING_HANDOFF_BUNDLE.md
  - docs/tasks/done/DATA-015_TRAINING_HANDOFF_VISIBILITY.md

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
  - docs/tasks/done/DATA-016_POSTRUN_HANDOFF_COLLECTOR.md

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - deploying to the VPS or touching GitLab
  - configuring, calling, or storing private training-server endpoints
  - training or evaluating a real model, integrating a GPU runner, model registry, or OTA path
  - copying feature-row JSONL contents, candidate DBs, raw records, private coordinates, raw payloads, or runtime JSONL logs
  - producing model weights, model cards, model artifacts, measured footprint, measured latency, measured power, device deployment, or release claims
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
---

# Goal

Serve D5: make the normal D1 post-run collector continue through TRAIN-007 so
reviewed post-field datasets can produce a bounded training handoff bundle from
one local after-run command.

# Acceptance Criteria

- [x] `scripts/collect_d1_postrun.py` runs TRAIN-007 after TRAIN-006 when the
      DATA-006 pipeline is ready for training handoff.
- [x] The post-run `training_chain` summary includes a `handoff_bundle`
      component with status, handoff id, training-server integration state,
      dry-run state, and report path.
- [x] The collector keeps skipped/not-ready cases explainable and still writes
      a summary when no dataset handoff is ready.
- [x] The D1 field kit v7 records the new expected handoff output and the
      curated `-IncludeTrainingHandoffSummaries` sync switch.
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
  verifies TRAIN-003 through TRAIN-006, and verifies TRAIN-007
  `ready_for_training_server_handoff` plus a written
  `training_handoff_bundle.json`.
- Remaining risks: DATA-016 still does not train a model or integrate a real
  runner/server. Real field/session volume, richer feature extraction,
  local/GPU training, model cards, artifact registry, footprint/power
  measurement, shadow-mode deployment, and release gates remain future work.
