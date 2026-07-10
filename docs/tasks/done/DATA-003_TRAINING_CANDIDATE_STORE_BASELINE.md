---
id: DATA-003
title: Training candidate store baseline
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/MODEL_FOOTPRINT_ASSESSMENT.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md

allowed_paths:
  - pc_simulator/training_candidate_store.py
  - scripts/build_training_candidate_store.py
  - quality_tests/test_training_candidate_store.py
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-003_TRAINING_CANDIDATE_STORE_BASELINE.md
  - docs/generated/

out_of_scope:
  - training a model
  - marking records training-ready
  - changing firmware, public contracts, or Message Hub ingest
  - copying raw private payloads into committed artifacts
---

# Goal

Serve D5: create the first local SQLite training-candidate store from existing
session recordings, annotations, and quality gates.

# Acceptance Criteria

- [x] A local store module writes bounded candidate records from a session
      recording and annotation.
- [x] Candidate records keep source refs, labels, privacy, consent, quality,
      split, and lineage fields.
- [x] `training_allowed` remains false until a later review gate.
- [x] CLI can build the store from one or more recording directories.
- [x] Focused tests and context validation pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_candidate_store -v
python scripts/context_lint.py
git diff --check
```

# Completion Evidence

- Changed files: `pc_simulator/training_candidate_store.py`,
  `scripts/build_training_candidate_store.py`,
  `quality_tests/test_training_candidate_store.py`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/STATUS.md`, and this task packet.
- Validation: `python -m unittest quality_tests.test_training_candidate_store
  -v` passed (4 tests); `python scripts/context_lint.py` passed; `python -m
  py_compile pc_simulator\training_candidate_store.py
  scripts\build_training_candidate_store.py` passed; `git diff --check`
  passed; `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`
  passed (394 tests).
- Remaining risks: the store is local-only, no promotion UI exists, and
  records are not training-ready until a future consent/privacy/quality/split
  review task promotes them.
