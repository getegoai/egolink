---
id: DATA-020
title: Synthetic training-chain smoke runner
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
  - docs/tasks/done/DATA-009_SYNTHETIC_SCENARIO_GENERATOR.md
  - docs/tasks/done/DATA-018_POSTRUN_JOB_PLAN_COLLECTOR.md

allowed_paths:
  - scripts/run_synthetic_training_chain.py
  - quality_tests/test_synthetic_training_chain.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-020_SYNTHETIC_TRAINING_CHAIN_SMOKE.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - changing firmware, protocol, public contracts, Dashboard/API behavior, or VPS deployment
  - exposing candidate DB paths, raw recordings, raw candidate records, private coordinates, feature-row contents, private endpoints, or runtime logs
  - training or evaluating a real model, integrating a GPU runner, model registry, or OTA path
  - producing model weights, model cards, model artifacts, measured footprint, measured latency, measured power, device deployment, or release claims
---

# Goal

Serve D5: keep the no-hardware data/model plumbing executable from synthetic
capture through TRAIN-008 job planning while real field evidence is pending.

# Acceptance Criteria

- [x] A single local command generates synthetic-only recordings, runs explicit
      synthetic review, and reruns the data-flywheel pipeline to a reviewed
      dataset handoff.
- [x] The command continues through TRAIN-003 preflight, TRAIN-004 feature
      manifest, TRAIN-005 runner dry-run, TRAIN-006 baseline eval, TRAIN-007
      handoff bundle, and TRAIN-008 job plan.
- [x] The final summary reports bounded statuses, counts, dry-run gates, and
      artifact refs only.
- [x] Synthetic outputs remain dry-run only and cannot support hardware,
      product, power, or real model-performance claims.
- [x] Focused unit coverage verifies the chain and raw-export boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_synthetic_training_chain -v
python -m py_compile scripts\run_synthetic_training_chain.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/run_synthetic_training_chain.py`,
  `quality_tests/test_synthetic_training_chain.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/STATUS.md`, generated progress board files, and this packet.
- Local smoke evidence:
  `reports/synthetic_training_chain/data020-dev-smoke-20260706/synthetic_training_chain.json`
  produced `status=synthetic_training_chain_complete` and final job-plan
  `status=synthetic_runner_queue_dry_run_only`.
- Remaining risks: DATA-020 is not field evidence and does not train a real
  model. Outdoor D1/D3 data, long power baselines, real model training,
  footprint/power measurement, device shadow mode, and release gates remain
  separate tasks.
