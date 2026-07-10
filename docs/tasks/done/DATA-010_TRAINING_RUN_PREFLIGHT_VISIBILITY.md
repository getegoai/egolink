---
id: DATA-010
title: Training-run preflight visibility
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
  - docs/tasks/done/TRAIN-003_TRAINING_RUN_PREFLIGHT.md
  - docs/tasks/done/DATA-007_TRAINING_EXPERIMENT_DASHBOARD_VISIBILITY.md

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
  - docs/tasks/done/DATA-010_TRAINING_RUN_PREFLIGHT_VISIBILITY.md

out_of_scope:
  - deploying to the VPS or touching GitLab
  - training or evaluating a model
  - integrating a GPU runner, real training server, private endpoint, model registry, or OTA path
  - copying candidate DBs, raw records, raw payloads, private coordinates, runtime JSONL logs, model weights, or model artifacts
  - changing firmware, Message Hub ingest contracts, public protocols, OTA, or on-device inference
  - claiming model accuracy, false-positive rate, latency, footprint, power impact, or product readiness
---

# Goal

Serve D5: make the latest TRAIN-003 runner-preflight status visible through the
Message Hub Web/API so the operator can see whether the data/model handoff is
blocked, dry-run only, or ready for a future runner without reading raw report
directories.

# Acceptance Criteria

- [x] `/api/state` includes a bounded `training_run_preflight` summary.
- [x] `/api/v1/training-runs/latest` returns the same bounded latest summary.
- [x] Dashboard renders a `Training Run Preflight` panel with status, dataset,
      experiment, synthetic gate, required-field checks, runner readiness,
      measured metrics still `not_run`, gates, next step, and report path.
- [x] Missing reports return explainable `not_available` state.
- [x] Deploy packaging has an explicit `-IncludeTrainingRunSummaries` switch
      that copies only `training_run_preflight.json/.md`.
- [x] Focused tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server.MessageHubHttpTests.test_state_api_and_training_run_route_include_latest_preflight quality_tests.test_message_hub_server.MessageHubHttpTests.test_state_api_and_training_experiment_route_include_latest_plan quality_tests.test_message_hub_server.MessageHubHttpTests.test_get_api_requires_token_when_auth_is_enabled
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
  `docs/current/ROADMAP_EGOLINK_P0.md`,
  `docs/current/STATUS.md`, and this packet.
- Validation: focused Web/API tests passed (20 tests); `python -m py_compile
  server\message_hub.py` passed; PowerShell parser check for
  `scripts\deploy_message_hub_vps.ps1` passed; `python scripts\context_lint.py`
  passed; `git diff --check` passed; full
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed (430
  tests).
- Remaining risks: DATA-010 is local visibility only in this run; the VPS was
  not deployed. Real runner integration, measured metrics, model artifacts,
  model-card generation, server integration, footprint/power measurement,
  shadow-mode deployment, and release gates remain future tasks.
