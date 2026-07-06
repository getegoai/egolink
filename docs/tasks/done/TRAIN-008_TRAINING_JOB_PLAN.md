---
id: TRAIN-008
title: Training job plan dry-run
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
  - docs/tasks/done/TRAIN-007_TRAINING_HANDOFF_BUNDLE.md
  - docs/tasks/done/DATA-016_POSTRUN_HANDOFF_COLLECTOR.md

allowed_paths:
  - scripts/create_training_job_plan.py
  - quality_tests/test_training_job_plan.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/current/STATUS.md
  - docs/tasks/done/TRAIN-008_TRAINING_JOB_PLAN.md

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - deploying to the VPS or touching GitLab
  - configuring, calling, or storing private training-server endpoints
  - training or evaluating a real model, integrating a GPU runner, model registry, or OTA path
  - copying feature-row JSONL contents, candidate DBs, raw records, private coordinates, raw payloads, or runtime JSONL logs
  - producing model weights, model cards, model artifacts, measured footprint, measured latency, measured power, device deployment, or release claims
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
---

# Goal

Serve D5: create a bounded training job plan from a TRAIN-007 handoff bundle so
a future runner/server can consume an explicit queue intent without starting
training.

# Acceptance Criteria

- [x] A CLI consumes an explicitly named `training_handoff_bundle.json`.
- [x] Ready reviewed handoffs write `ready_for_runner_queue` job plans with
      source hash, dataset/feature summaries, model plan, runner profile,
      planned metrics, gates, and non-claims.
- [x] Synthetic handoffs require explicit acknowledgement and remain dry-run
      only.
- [x] Blocked handoffs do not enter the runner queue.
- [x] The job plan does not expose feature-row contents, private endpoints, raw
      records, model artifacts, measured metrics, or release claims.
- [x] Focused tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_job_plan -v
python -m py_compile scripts\create_training_job_plan.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/create_training_job_plan.py`,
  `quality_tests/test_training_job_plan.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/current/STATUS.md`, and this
  packet.
- Focused validation passed for ready reviewed handoff, synthetic
  acknowledgement, and blocked-handoff cases.
- Remaining risks: TRAIN-008 still does not integrate a real runner/server or
  train a model. Real reviewed field/session volume, local/GPU training, model
  cards, artifact registry, footprint/power measurement, shadow-mode
  deployment, and release gates remain future work.
