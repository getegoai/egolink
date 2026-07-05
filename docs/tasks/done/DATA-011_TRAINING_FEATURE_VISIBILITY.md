---
id: DATA-011
title: Training feature manifest visibility
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
  - docs/tasks/done/DATA-010_TRAINING_RUN_PREFLIGHT_VISIBILITY.md

allowed_paths:
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-011_TRAINING_FEATURE_VISIBILITY.md

out_of_scope:
  - training or evaluating a model
  - integrating a GPU runner, real training server, private endpoint, model registry, or OTA path
  - serving or syncing `training_feature_rows.jsonl` row contents
  - generating MotionNet tensors or raw IMU/audio/image feature payloads
  - producing model weights, model cards, measured metrics, model artifacts, or release claims
  - exposing raw candidate records, DB files, raw payloads, private coordinates, or runtime JSONL logs
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
  - deploying to the VPS unless explicitly requested
---

# Goal

Serve D5: make the latest TRAIN-004 feature-manifest handoff visible in the Web
Dashboard and API so the data-to-training chain can be monitored without
opening local report folders or exposing JSONL row contents.

# Acceptance Criteria

- [x] `/api/state` includes a bounded `training_feature_manifest` summary.
- [x] `/api/v1/training-features/latest` returns the latest bounded feature
      manifest summary.
- [x] The Dashboard renders a `Training Feature Manifest` panel with status,
      row count, feature scope, source matching, target-boundary guard,
      synthetic policy, gates, next step, and report paths.
- [x] Missing or unreadable feature manifests produce explainable
      `not_available` summaries.
- [x] Deploy packaging has an explicit `-IncludeTrainingFeatureSummaries`
      switch that copies only `training_feature_manifest.json/.md` and does not
      copy `training_feature_rows.jsonl`, candidate DBs, runtime JSONL logs, raw
      records, private endpoints, model artifacts, or measured metrics.
- [x] Focused Web/API tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server
python -m py_compile server\message_hub.py
$errors=$null; [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw scripts\deploy_message_hub_vps.ps1), [ref]$errors) | Out-Null; if ($errors -and $errors.Count) { exit 1 }
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `server/message_hub.py`,
  `scripts/deploy_message_hub_vps.ps1`,
  `quality_tests/test_message_hub_dashboard.py`,
  `quality_tests/test_message_hub_server.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/current/STATUS.md`, and this
  packet.
- Local UI/API behavior: the Dashboard contains `Training Feature Manifest`
  and `trainingFeatureManifestPanel`; `/api/state` and
  `/api/v1/training-features/latest` can load bounded summaries from
  `reports/training_features/**/training_feature_manifest.json`.
- Deployment packaging: `-IncludeTrainingFeatureSummaries` copies only
  `training_feature_manifest.json/.md`; JSONL feature rows remain local unless
  a later task explicitly changes that boundary.
- Validation: focused Web/API tests passed (45 tests); `python -m py_compile
  server\message_hub.py` passed; PowerShell parser check for
  `scripts\deploy_message_hub_vps.ps1` passed; `python scripts\context_lint.py`
  passed; `git diff --check` passed; full
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed (437
  tests).
- Remaining risks: DATA-011 was not deployed to the VPS in this run. It is
  visibility only; real feature extraction from raw IMU windows, local/GPU
  training, measured metrics, model artifact production, model-card generation,
  server integration, footprint/power measurement, shadow-mode deployment, and
  release gates remain future tasks.
