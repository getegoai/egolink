---
id: DATA-021
title: Synthetic training-chain visibility
status: done
priority: medium
requires_hardware: false
serves_demo: D5
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/tasks/done/DATA-020_SYNTHETIC_TRAINING_CHAIN_SMOKE.md
  - docs/tasks/done/DATA-017_TRAINING_JOB_VISIBILITY.md

allowed_paths:
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-021_SYNTHETIC_TRAINING_CHAIN_VISIBILITY.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - deploying to the VPS unless explicitly requested
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - changing firmware, public contracts, ingest protocol, OTA, or on-device inference behavior
  - exposing raw recordings, candidate DB paths, raw candidate records, feature-row contents, private endpoints, runtime logs, or model artifacts
  - training or evaluating a real model, integrating a GPU runner, model registry, or OTA path
  - producing model weights, model cards, measured footprint, measured latency, measured power, device deployment, or release claims
---

# Goal

Serve D5: make the latest synthetic DATA/TRAIN smoke status visible in the
Web Dashboard and API while preserving the synthetic-only and no-claim
boundaries.

# Acceptance Criteria

- [x] `/api/state` includes a bounded `synthetic_training_chain` summary.
- [x] `/api/v1/synthetic-training-chains/latest` returns the same bounded
      latest summary.
- [x] The Dashboard renders a `Synthetic Training Chain` panel with status,
      scenarios, counts, data-flywheel states, TRAIN-003..008 component
      statuses, scope flags, next step, and report path.
- [x] Missing or unreadable reports return explainable `not_available`
      summaries.
- [x] Deploy packaging has an explicit
      `-IncludeSyntheticTrainingChainSummaries` switch that copies only
      `synthetic_training_chain.json/.md`.
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
  `docs/current/STATUS.md`, generated progress board files, and this packet.
- Local UI/API behavior: the Dashboard contains `Synthetic Training Chain` and
  `syntheticTrainingChainPanel`; `/api/state` and
  `/api/v1/synthetic-training-chains/latest` can load bounded summaries from
  `reports/synthetic_training_chain/**/synthetic_training_chain.json`.
- Deployment packaging: `-IncludeSyntheticTrainingChainSummaries` copies only
  `synthetic_training_chain.json/.md`; raw recordings, candidate DBs,
  feature-row JSONL, private endpoints, runtime logs, and model artifacts stay
  local unless a later task explicitly changes that boundary.
- Remaining risks: DATA-021 was not deployed to the VPS in this run. It is
  visibility only; real field data, training runner/server integration,
  model artifacts, model cards, footprint/power measurement, shadow-mode
  deployment, and release gates remain future tasks.
