---
id: TRAIN-004
title: Training feature manifest export
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
  - docs/tasks/done/TRAIN-003_TRAINING_RUN_PREFLIGHT.md
  - docs/tasks/done/DATA-009_SYNTHETIC_SCENARIO_GENERATOR.md

allowed_paths:
  - scripts/export_training_feature_manifest.py
  - quality_tests/test_training_feature_manifest.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/current/STATUS.md
  - docs/tasks/done/TRAIN-004_TRAINING_FEATURE_MANIFEST.md

out_of_scope:
  - training or evaluating a model
  - integrating a GPU runner, real training server, private endpoint, model registry, or OTA path
  - generating MotionNet tensors or raw IMU/audio/image feature payloads
  - producing model weights, model cards, measured metrics, model artifacts, or release claims
  - exporting raw candidate records, DB files, raw payloads, private coordinates, or runtime JSONL logs
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
  - claiming model accuracy, false-positive rate, latency, footprint, power impact, or product readiness
---

# Goal

Serve D5: add a bounded feature-manifest handoff after TRAIN-003 so a future
local/GPU training runner can consume stable JSONL rows without pulling from
Dashboard state, runtime logs, candidate databases, or raw recordings.

# Acceptance Criteria

- [x] A CLI can consume an explicitly named TRAIN-001
      `training_dataset_manifest.json` plus TRAIN-003
      `training_run_preflight.json`.
- [x] Preflight-not-ready, dataset-not-ready, source mismatch, empty datasets,
      incomplete bounded records, and synthetic records without explicit
      acknowledgement produce explainable blocked statuses.
- [x] `--allow-synthetic` can make synthetic-only records produce feature rows
      only as dry-run runner-integration evidence.
- [x] Feature rows keep labels under `target`, keep manifest-summary features
      under `features`, and include no raw recordings, raw payloads, candidate
      DB paths, runtime JSONL logs, private endpoints, model artifacts, or
      measured model metrics.
- [x] Focused tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_feature_manifest
python -m py_compile scripts\export_training_feature_manifest.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/export_training_feature_manifest.py`,
  `quality_tests/test_training_feature_manifest.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/current/STATUS.md`, and this
  packet.
- Local dry-run evidence:
  `reports/training_features/train004-local-smoke-20260705/` from the DATA-009
  reviewed synthetic dataset plus TRAIN-003 preflight with
  `--allow-synthetic --require-ready`.
- Smoke result: `status=ready_for_synthetic_feature_dry_run`,
  `feature_rows.row_count=4`, `feature_rows.feature_scope=
  manifest_summary_features`, and `checks.label_leakage_guard=
  target_separated_from_features`.
- Validation: `python -m unittest quality_tests.test_training_feature_manifest`
  passed (4 tests); `python -m py_compile
  scripts\export_training_feature_manifest.py` passed; `python
  scripts\context_lint.py` passed; `git diff --check` passed; full
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed (434
  tests).
- Remaining risks: TRAIN-004 is still a bounded handoff only. Real feature
  extraction from raw IMU windows, local/GPU training, measured metrics, model
  artifact production, model-card generation, server integration,
  footprint/power measurement, shadow-mode deployment, and release gates remain
  future tasks.
