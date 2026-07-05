---
id: DATA-007
title: Training experiment dashboard visibility
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
  - docs/tasks/done/TRAIN-002_TRAINING_EXPERIMENT_REGISTRY.md

allowed_paths:
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_d1_field_kit.py
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-007_TRAINING_EXPERIMENT_DASHBOARD_VISIBILITY.md

out_of_scope:
  - training or evaluating a model
  - integrating a GPU runner, training server, or private endpoint
  - copying raw candidate records, candidate DB files, runtime JSONL logs, raw payloads, or private coordinates
  - changing firmware, Message Hub ingest contracts, OTA, or on-device inference
  - claiming model accuracy, false-positive rate, latency, footprint, or power impact
---

# Goal

Serve D5: make the latest TRAIN-002 experiment plan visible through the Message
Hub API and Dashboard, and make curated experiment summaries syncable without
copying private training data.

# Acceptance Criteria

- [x] Authenticated `/api/state` includes a bounded `training_experiment`
      summary.
- [x] `/api/v1/training-experiments/latest` returns the same latest bounded
      summary.
- [x] Dashboard HTML includes a `Training Experiments` panel with runner
      handoff, dataset readiness, planned metrics, gates, and next step.
- [x] The deploy script can explicitly sync only
      `training_experiment_plan.json/.md` summaries.
- [x] D1 field kit post-run dashboard sync includes the new curated-summary
      switch.
- [x] Focused tests and syntax checks pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server quality_tests.test_d1_field_kit -v
python -m py_compile server\message_hub.py scripts\prepare_d1_field_kit.py
$errors = $null; [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw scripts\deploy_message_hub_vps.ps1), [ref]$errors) | Out-Null; if ($errors.Count) { $errors | Format-List *; exit 1 }
python scripts/context_lint.py
git diff --check
```

# Completion Evidence

- Changed files: `server/message_hub.py`,
  `scripts/deploy_message_hub_vps.ps1`, `scripts/prepare_d1_field_kit.py`,
  `quality_tests/test_message_hub_dashboard.py`,
  `quality_tests/test_message_hub_server.py`,
  `quality_tests/test_d1_field_kit.py`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/STATUS.md`, and this packet.
- Validation: focused Message Hub Dashboard/API/D1 field-kit tests passed (43
  tests); `python -m py_compile server\message_hub.py
  scripts\prepare_d1_field_kit.py` passed; PowerShell parser check for
  `scripts\deploy_message_hub_vps.ps1` passed; `python scripts\context_lint.py`
  passed; `git diff --check` passed with the existing CRLF warning for the
  touched PowerShell script; full `scripts\verify.ps1` passed (418 tests).
- Deployment: `scripts\deploy_message_hub_vps.ps1 -HostName 203.0.113.10
  -SshKey $HOME\.ssh\egolink_vps_ed25519 -Public
  -IncludeFieldReportSummaries -IncludeDataFlywheelSummaries
  -IncludeTrainingExperimentSummaries` completed, restarted
  `egolink-message-hub.service`, and did not touch GitLab. Smoke after deploy:
  `/health` returned `ok=true`, unauthenticated `/api/state` returned `401`,
  authenticated `/api/state` included
  `training_experiment.status=blocked_dataset_not_ready` with
  `reason=candidate_store_missing`, and Dashboard HTML contained `Training
  Experiments` plus `trainingExperimentPanel`.
- Remaining risks: the public VPS Dashboard will not show this new panel until
  reviewed recording data is ingested, reviewed, and registered into a
  runner-ready experiment plan; DATA-007 does not train/evaluate a model,
  integrate a runner, or claim measured model metrics.
