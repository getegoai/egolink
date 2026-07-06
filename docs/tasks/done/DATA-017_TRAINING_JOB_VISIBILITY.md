---
id: DATA-017
title: Training job visibility
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
  - docs/tasks/done/TRAIN-008_TRAINING_JOB_PLAN.md
  - docs/tasks/done/DATA-015_TRAINING_HANDOFF_VISIBILITY.md

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
  - docs/tasks/done/DATA-017_TRAINING_JOB_VISIBILITY.md

out_of_scope:
  - training or evaluating a real model
  - configuring, calling, or storing private training-server endpoints
  - integrating a GPU runner, model registry, or OTA path
  - serving or syncing `training_feature_rows.jsonl` row contents
  - exposing raw candidate records, DB files, raw payloads, private coordinates, runtime JSONL logs, or private endpoints
  - producing model weights, model cards, measured footprint, measured latency, measured power, device deployment, or release claims
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
  - deploying to the VPS unless explicitly requested
---

# Goal

Serve D5: make the latest TRAIN-008 training job plan visible in the Web
Dashboard and API so future runner/server queue readiness can be monitored
without opening report files.

# Acceptance Criteria

- [x] `/api/state` includes a bounded `training_job_plan` summary.
- [x] `/api/v1/training-jobs/latest` returns the latest bounded job-plan
      summary.
- [x] The Dashboard renders a `Training Job Plan` panel with status, source
      handoff, dataset/feature summaries, model plan, runner queue state,
      planned metrics, gates, next step, and report paths.
- [x] Missing or unreadable job-plan reports produce explainable
      `not_available` summaries.
- [x] Deploy packaging has an explicit `-IncludeTrainingJobSummaries` switch
      that copies only `training_job_plan.json/.md` and does not copy
      feature-row JSONL, candidate DBs, runtime JSONL logs, raw records,
      private endpoints, model artifacts, or measured power/footprint data.
- [x] Focused Web/API tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
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
- Local UI/API behavior: the Dashboard contains `Training Job Plan` and
  `trainingJobPlanPanel`; `/api/state` and
  `/api/v1/training-jobs/latest` can load bounded summaries from
  `reports/training_jobs/**/training_job_plan.json`.
- Deployment packaging: `-IncludeTrainingJobSummaries` copies only
  `training_job_plan.json/.md`; feature-row JSONL and raw/private/model
  artifacts stay local unless a later task explicitly changes that boundary.
- Remaining risks: DATA-017 was not deployed to the VPS in this run. It is
  visibility only; real runner/server integration, local/GPU training, model
  artifact production, model-card generation, footprint/power measurement,
  shadow-mode deployment, and release gates remain future tasks.
