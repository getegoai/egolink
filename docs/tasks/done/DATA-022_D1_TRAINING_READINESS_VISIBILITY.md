---
id: DATA-022
title: D1 real-data training-readiness visibility
status: done
priority: medium
requires_hardware: false
serves_demo: D5
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/tasks/done/DATA-021_SYNTHETIC_TRAINING_CHAIN_VISIBILITY.md

allowed_paths:
  - scripts/assess_d1_training_readiness.py
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/test_d1_training_readiness.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-022_D1_TRAINING_READINESS_VISIBILITY.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading `d1_field_samples.jsonl` contents into summaries
  - exposing exact coordinates, raw payloads, feature rows, targets, candidate DBs, or private endpoints
  - changing firmware, protocol, data contracts, model behavior, OTA, or device deployment
  - training/evaluating a model, producing model artifacts/cards, measuring model footprint/power, or making release claims
---

# Goal

Serve D5: make it visible whether a real D1 field-observation summary is ready
to enter labeling/privacy review before any training-candidate handoff.

# Acceptance Criteria

- [x] A local command reads a bounded D1 field-observation report/status summary
      and writes `d1_training_readiness.json/.md`.
- [x] The report shows capture, transport, location, sensor, privacy, label,
      split, model, and release-claim gates.
- [x] The report can mark a real D1 capture `ready_for_labeling_review` while
      keeping `ready_for_training_handoff=false` and `training_allowed=false`.
- [x] `/api/state` includes a bounded `d1_training_readiness` summary.
- [x] `/api/v1/d1-training-readiness/latest` returns the same bounded latest
      summary.
- [x] The Dashboard renders a `D1 Training Readiness` panel.
- [x] Deploy packaging has an explicit
      `-IncludeD1TrainingReadinessSummaries` switch that copies only
      `d1_training_readiness.json/.md`.
- [x] Focused tests pass and protect privacy/non-claim boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_training_readiness quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
python -m py_compile server\message_hub.py scripts\assess_d1_training_readiness.py
$errors=$null; [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw scripts\deploy_message_hub_vps.ps1), [ref]$errors) | Out-Null; if ($errors -and $errors.Count) { exit 1 }
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/assess_d1_training_readiness.py`,
  `server/message_hub.py`, `scripts/deploy_message_hub_vps.ps1`,
  `quality_tests/test_d1_training_readiness.py`,
  `quality_tests/test_message_hub_dashboard.py`,
  `quality_tests/test_message_hub_server.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/STATUS.md`, generated progress board files, and this packet.
- Local smoke:
  `reports/d1_training_readiness/data022-local-smoke-20260706/d1_training_readiness.json`
  reported `ready_for_labeling_review`,
  `ready_for_training_handoff=false`, and `training_allowed=false` over the
  short D1 return-link field observation.
- Web/API behavior: the Dashboard contains `D1 Training Readiness` and
  `d1TrainingReadinessPanel`; `/api/state` and
  `/api/v1/d1-training-readiness/latest` can load bounded summaries from
  `reports/d1_training_readiness/**/d1_training_readiness.json`.
- Deployment packaging: `-IncludeD1TrainingReadinessSummaries` copies only
  `d1_training_readiness.json/.md`; sample JSONL, exact coordinates, raw
  payloads, feature rows, targets, candidate DBs, private endpoints, runtime
  logs, and model artifacts stay local unless a later task explicitly changes
  that boundary.
- Remaining risks: DATA-022 was not deployed to the VPS in this run. It is a
  readiness/visibility bridge only; labeling UI, consent/privacy workflow,
  real training-candidate export, runner/server integration, on-device model
  deployment, model footprint/power measurement, and release gates remain
  future tasks.
