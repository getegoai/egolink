---
id: TRAIN-003
title: Training-run preflight
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
  - docs/tasks/done/TRAIN-002_TRAINING_EXPERIMENT_REGISTRY.md
  - docs/tasks/done/DATA-009_SYNTHETIC_SCENARIO_GENERATOR.md

allowed_paths:
  - scripts/run_training_experiment_preflight.py
  - quality_tests/test_training_experiment_preflight.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/current/STATUS.md
  - docs/tasks/done/TRAIN-003_TRAINING_RUN_PREFLIGHT.md

out_of_scope:
  - training or evaluating a model
  - integrating a GPU runner, real training server, private endpoint, model registry, or OTA path
  - producing model weights, model cards, measured metrics, model artifacts, or release claims
  - exporting raw candidate records, DB files, raw payloads, private coordinates, or runtime JSONL logs
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
  - claiming model accuracy, false-positive rate, latency, footprint, power impact, or product readiness
---

# Goal

Serve D5: add a bounded training-run preflight contract after TRAIN-002 so the
project can check whether a dataset/experiment handoff is ready for a future
local or GPU runner without starting training or producing model claims.

# Acceptance Criteria

- [x] A CLI can consume an explicitly named TRAIN-002
      `training_experiment_plan.json` plus TRAIN-001
      `training_dataset_manifest.json`.
- [x] Blocked experiment plans, not-ready manifests, empty datasets,
      incomplete bounded records, and synthetic records without explicit
      acknowledgement produce explainable blocked statuses.
- [x] `--allow-synthetic` can make synthetic-only data pass preflight only for
      dry-run integration.
- [x] Reports include split, label, source-status, required-field, and runner
      readiness summaries without exposing raw records, candidate DBs, private
      paths, runtime logs, private endpoints, model artifacts, or measured
      metrics.
- [x] Focused tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_experiment_preflight quality_tests.test_training_experiment_registry
python -m py_compile scripts\run_training_experiment_preflight.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/run_training_experiment_preflight.py`,
  `quality_tests/test_training_experiment_preflight.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`,
  `docs/current/STATUS.md`, and this packet.
- Local dry-run evidence: `reports/training_runs/train003-local-smoke-20260705/`
  from the DATA-009 reviewed synthetic dataset/experiment with
  `--allow-synthetic --require-ready`.
- Validation: focused TRAIN-003/TRAIN-002 tests passed (7 tests);
  `python -m py_compile scripts\run_training_experiment_preflight.py` passed;
  `python scripts\context_lint.py` passed; `git diff --check` passed; full
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed (427
  tests).
- Remaining risks: TRAIN-003 is still preflight-only. Real training, measured
  metrics, model artifact production, model-card generation, server
  integration, footprint/power measurement, shadow-mode deployment, and release
  gates remain future tasks.
