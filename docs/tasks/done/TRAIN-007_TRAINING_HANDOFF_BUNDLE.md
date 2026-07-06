---
id: TRAIN-007
title: Training handoff bundle
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
  - docs/tasks/done/DATA-014_POSTRUN_TRAINING_CHAIN.md
  - docs/tasks/done/TRAIN-006_SYNTHETIC_BASELINE_EVAL.md

allowed_paths:
  - scripts/build_training_handoff_bundle.py
  - quality_tests/test_training_handoff_bundle.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/current/STATUS.md
  - docs/tasks/done/TRAIN-007_TRAINING_HANDOFF_BUNDLE.md

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - deploying to the VPS or touching GitLab
  - configuring, calling, or storing private training-server endpoints
  - training or evaluating a real model, integrating a GPU runner, model registry, or OTA path
  - copying feature-row JSONL contents, candidate DBs, raw records, private coordinates, raw payloads, or runtime JSONL logs
  - producing model weights, model cards, model artifacts, measured footprint, measured latency, measured power, or release claims
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
---

# Goal

Serve D5: create one bounded local handoff bundle that a future training runner
or training server can consume from explicit refs and hashes, without copying
training rows or starting model training.

# Acceptance Criteria

- [x] A CLI consumes explicitly named dataset, TRAIN-003 preflight, TRAIN-004
      feature manifest/rows, TRAIN-005 runner dry-run, and TRAIN-006 baseline
      eval reports.
- [x] The bundle records input refs, sha256 hashes, byte counts, row counts,
      component statuses, source matching, synthetic policy, gates, and next
      step.
- [x] Row-count mismatch, source mismatch, not-ready inputs, and synthetic
      inputs without explicit acknowledgement produce explainable blocked
      statuses.
- [x] Synthetic inputs can build only a dry-run handoff when explicitly
      acknowledged.
- [x] The bundle does not copy feature-row JSONL contents, raw records, private
      endpoints, model artifacts, model cards, or measured model claims.
- [x] Focused tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_handoff_bundle -v
python -m py_compile scripts\build_training_handoff_bundle.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/build_training_handoff_bundle.py`,
  `quality_tests/test_training_handoff_bundle.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/current/STATUS.md`, and this
  packet.
- Focused validation passed for ready real-input, synthetic-acknowledgement,
  and feature-row mismatch cases.
- Remaining risks: TRAIN-007 still does not integrate a real training server
  or runner. Real reviewed field/session volume, richer feature extraction,
  local/GPU training, model cards, artifact registry, footprint/power
  measurement, shadow-mode deployment, and release gates remain future work.
