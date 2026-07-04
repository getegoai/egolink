---
id: TRAIN-001
title: Dataset and experiment handoff manifest
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/tasks/done/DATA-005_CANDIDATE_REVIEW_QUEUE.md

allowed_paths:
  - pc_simulator/training_candidate_store.py
  - scripts/export_training_dataset_manifest.py
  - quality_tests/test_training_candidate_store.py
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/current/STATUS.md
  - docs/tasks/done/TRAIN-001_DATASET_EXPERIMENT_HANDOFF.md
  - docs/generated/

out_of_scope:
  - training a model
  - integrating a real training server or GPU runner
  - exporting raw candidate records, DB files, raw payloads, private coordinates, or runtime JSONL logs
  - changing firmware, Message Hub ingest, protocol contracts, or on-device inference
  - claiming model accuracy, false-positive rate, latency, footprint, or power impact
---

# Goal

Serve D5: export reviewed, training-allowed candidates into a bounded
dataset/experiment handoff manifest that a later training runner can consume
without copying raw records or starting any model training.

# Acceptance Criteria

- [x] Export refuses or reports not-ready when no reviewed training candidates
      exist.
- [x] Export includes only `reviewed_training_candidate` records with
      `training_allowed=true`.
- [x] Manifest preserves lineage, split, label, privacy, and quality summaries
      without raw candidate records or private payloads.
- [x] Focused tests and repository validation pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_candidate_store -v
python scripts/context_lint.py
python -m py_compile pc_simulator\training_candidate_store.py scripts\export_training_dataset_manifest.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `pc_simulator/training_candidate_store.py`,
  `scripts/export_training_dataset_manifest.py`,
  `quality_tests/test_training_candidate_store.py`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/STATUS.md`, generated progress board files, and this packet.
- Validation: focused candidate-store tests passed (14 tests);
  `python scripts/context_lint.py` passed; `python -m py_compile
  pc_simulator\training_candidate_store.py scripts\export_training_dataset_manifest.py`
  passed using a temporary pycache directory because Windows locked the default
  pycache file; `git diff --check` passed; full `scripts\verify.ps1` passed
  (409 tests).
- Local evidence: `scripts/export_training_dataset_manifest.py --dataset-id
  train001-local-handoff-20260704 --generated-at
  2026-07-04T14:05:00+00:00 --json` wrote
  `reports/training_datasets/train001-local-handoff-20260704/` with
  `status=not_ready`, `reason=candidate_store_missing`, and
  `eligible_records=0`, which is expected until reviewed recordings are
  ingested.
- Remaining risks: no reviewed candidate records exist in the default local
  store yet; TRAIN-001 does not train/evaluate a model, integrate a GPU/training
  server, deploy on-device inference, or claim model metrics, footprint, or
  power impact.
