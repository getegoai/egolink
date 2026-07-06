---
id: TRAIN-006
title: Synthetic baseline evaluation
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
  - docs/tasks/done/TRAIN-004_TRAINING_FEATURE_MANIFEST.md
  - docs/tasks/done/TRAIN-005_LOCAL_RUNNER_DRY_RUN.md

allowed_paths:
  - scripts/run_training_baseline_eval.py
  - quality_tests/test_training_baseline_eval.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/current/STATUS.md
  - docs/tasks/done/TRAIN-006_SYNTHETIC_BASELINE_EVAL.md

out_of_scope:
  - training MotionNet, AudioGate, VisionGate, or learned ContextRouter
  - integrating a GPU runner, real training server, private endpoint, model registry, or OTA path
  - producing model weights, model cards, model artifacts, measured footprint, measured latency, or measured power
  - treating synthetic metrics as product performance, release evidence, false-positive rates, or power claims
  - exporting raw feature rows, raw candidate records, DB files, raw payloads, private coordinates, or runtime JSONL logs
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
---

# Goal

Serve D5: add the first bounded baseline-evaluation report after TRAIN-005 so
metrics plumbing can be exercised from TRAIN-004 feature rows without training
or shipping a model.

# Acceptance Criteria

- [x] A CLI consumes explicitly named TRAIN-004 `training_feature_manifest.json`,
      TRAIN-004 `training_feature_rows.jsonl`, and TRAIN-005
      `training_runner_dry_run.json`.
- [x] Not-ready feature manifests, not-ready runner dry-runs, unreadable rows,
      row-count/feature-set mismatches, incomplete bounded rows, target-label
      leakage, and synthetic rows without explicit acknowledgement produce
      explainable blocked statuses.
- [x] `--allow-synthetic` can produce aggregate baseline metrics only as
      synthetic integration evidence.
- [x] Reports include aggregate split, label, risk-type, candidate-type,
      source-status, baseline-metric, gate, and non-claim summaries without
      exposing raw rows or private paths.
- [x] Reports keep model training, artifact, card, server, registry, device
      deployment, footprint, latency, and power gates unrun/not produced.
- [x] Focused tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_baseline_eval -v
python -m py_compile scripts\run_training_baseline_eval.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/run_training_baseline_eval.py`,
  `quality_tests/test_training_baseline_eval.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/current/STATUS.md`, and this
  packet.
- Local smoke evidence:
  `reports/training_baseline_evals/train006-local-smoke-20260706/` from the
  TRAIN-004 synthetic feature set and TRAIN-005 runner dry-run with
  `--allow-synthetic --require-ready`.
- Smoke result: `status=synthetic_baseline_eval_complete`,
  `metrics.scope=synthetic_integration_only`, `checks.target_leakage_guard=pass`,
  `checks.synthetic_row_policy=acknowledged`, candidate-type/risk baseline
  `4/4`, and majority-label baseline `1/4`.
- Remaining risks: TRAIN-006 is still synthetic-only metrics plumbing. Real
  reviewed field/session data, raw IMU-window feature extraction, local/GPU
  training, model artifact production, model-card generation, training-server
  integration, footprint/power measurement, shadow-mode deployment, and release
  gates remain future tasks.
