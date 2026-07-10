---
id: TRAIN-005
title: Local training runner dry-run
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
  - docs/tasks/done/TRAIN-004_TRAINING_FEATURE_MANIFEST.md
  - docs/tasks/done/DATA-011_TRAINING_FEATURE_VISIBILITY.md

allowed_paths:
  - scripts/run_training_runner_dry_run.py
  - quality_tests/test_training_runner_dry_run.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/current/STATUS.md
  - docs/tasks/done/TRAIN-005_LOCAL_RUNNER_DRY_RUN.md

out_of_scope:
  - training or evaluating a model
  - integrating a GPU runner, real training server, private endpoint, model registry, or OTA path
  - generating MotionNet tensors or raw IMU/audio/image feature payloads
  - producing model weights, model cards, measured metrics, model artifacts, or release claims
  - exporting raw candidate records, DB files, raw payloads, private coordinates, or runtime JSONL logs
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
---

# Goal

Serve D5: add a bounded local runner-input dry-run after TRAIN-004 so the
future training runner contract can be validated from feature manifests and
JSONL rows without starting real model training.

# Acceptance Criteria

- [x] A CLI can consume an explicitly named TRAIN-004
      `training_feature_manifest.json` plus `training_feature_rows.jsonl`.
- [x] Not-ready feature manifests, unreadable rows, row-count/feature-set
      mismatches, incomplete bounded rows, target-label leakage, and synthetic
      rows without explicit acknowledgement produce explainable blocked
      statuses.
- [x] `--allow-synthetic` can complete a synthetic runner dry-run only as
      integration evidence.
- [x] Reports include split, label, source-status, feature-group, row-count,
      leakage, synthetic-policy, and runner-input summaries without exposing
      raw records, candidate DBs, private paths, runtime logs, private
      endpoints, model artifacts, or measured metrics.
- [x] Focused tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_runner_dry_run
python -m py_compile scripts\run_training_runner_dry_run.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/run_training_runner_dry_run.py`,
  `quality_tests/test_training_runner_dry_run.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/current/STATUS.md`, and this
  packet.
- Local dry-run evidence:
  `reports/training_runner_dry_runs/train005-local-smoke-20260705/` from the
  TRAIN-004 synthetic feature set with `--allow-synthetic --require-ready`.
- Smoke result: `status=synthetic_runner_dry_run_complete`,
  `feature_rows.actual_row_count=4`, `feature_rows.row_count_matches=true`,
  `checks.target_leakage_guard=pass`, `checks.synthetic_row_policy=
  acknowledged`, and measured metrics remain `not_run`.
- Validation: `python -m unittest quality_tests.test_training_runner_dry_run`
  passed (5 tests); `python -m py_compile
  scripts\run_training_runner_dry_run.py` passed; `python
  scripts\context_lint.py` passed; `git diff --check` passed; full
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed (442
  tests).
- Remaining risks: TRAIN-005 is still runner-input validation only. Real
  feature extraction from raw IMU windows, local/GPU training, measured
  metrics, model artifact production, model-card generation, server
  integration, footprint/power measurement, shadow-mode deployment, and release
  gates remain future tasks.
