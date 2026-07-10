---
id: DATA-002
title: Data flywheel pipeline spec
status: completed
priority: high
requires_hardware: false
created: 2026-07-04
last_updated: 2026-07-04
completed: 2026-07-04

context:
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/development/LOCATION_DATASET.md
  - docs/safety/SAFETY_CONTRACT.md
  - shared/contracts/

allowed_paths:
  - docs/development/
  - docs/product/
  - docs/roadmap/
  - docs/current/
  - docs/tasks/
  - docs/generated/
  - quality_tests/

out_of_scope:
  - collecting real private user data
  - enabling training from product-demo or field-test evidence by default
  - enabling raw audio or raw image retention by default
  - changing firmware logic, pin assignments, or hardware configuration
  - changing public wire protocol or shared machine-readable contracts
  - training MotionNet, AudioGate, VisionGate, or any other learned model
  - implementing server model rollout or device OTA
  - implementing guardian accounts, mobile app, calling, SMS, or dispatch
---

# Problem

V1 names the data flywheel as a core dependency for on-device AI companion
work, but the project only had DATA-001 location-fusion dataset exports and a
product-demo privacy boundary. There was no current specification that ties
session ingest, consent, privacy classes, confirmation-derived labels,
training-candidate storage, split leakage, deletion handling, and later
server/device update review into one governed pipeline.

# Expected Result

Create a narrow DATA-002 specification that can guide M1-002 session recorder,
M1-005 labeling, M1-006 collection protocol, MODEL-001 footprint assessment,
and future MotionNet work without collecting new private data or claiming that
training or OTA is implemented.

# Acceptance Criteria

- [x] A current document defines the DATA-002 pipeline from session/test-run
      evidence to reviewed training-candidate records.
- [x] The spec carries forward the product-demo privacy defaults:
      `training_allowed=false`, `raw_audio_allowed=false`, and
      `raw_image_allowed=false`.
- [x] Candidate records require consent, privacy class, retention/deletion,
      lineage, quality, labels, and split-leakage fields.
- [x] The spec states that Dashboard state is not a training source by itself.
- [x] The spec keeps model training and server/device OTA as future work, not
      implemented behavior.
- [x] A focused quality test protects the documented boundaries.
- [x] `python scripts/context_lint.py` passes; run full verify if behavior,
      code, or contracts change.

# Validation Commands

```powershell
python -m unittest quality_tests.test_data_flywheel_pipeline_doc -v
python scripts/context_lint.py
git diff --check
```

# Hardware Validation

- Not applicable. This is a documentation and quality-test task.

# Decisions

- DATA-002 is a pipeline contract, not a data collection run.
- Product-demo and V1 field-test records remain non-training data by default.
- OTA model delivery remains planned but not implemented by this task.
- Founder/legal review still owns final consent wording, retention limits, and
  deletion policy.

# Completion Evidence

- review1 (2026-07-04, codex): created the DATA-002 pipeline specification and
  a focused document test for privacy/training/OTA boundaries.
- Changed files:
  - `docs/development/DATA_FLYWHEEL_PIPELINE.md`
  - `docs/tasks/done/DATA-002_DATA_FLYWHEEL_PIPELINE_SPEC.md`
  - `docs/roadmap/V1_PRODUCT_PLAN.md`
  - `docs/development/LOCATION_DATASET.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/current/STATUS.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
  - `quality_tests/test_data_flywheel_pipeline_doc.py`
- Test result:
  - `python -m unittest quality_tests.test_data_flywheel_pipeline_doc -v`:
    PASS (4 tests).
  - `python scripts/context_lint.py`: PASS.
  - `python scripts/build_progress_board.py`: PASS
    (`active=3`, `done=76`).
  - `git diff --check`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS
    (351 tests).
- Hardware result: not applicable.
- Remaining risks:
  - This is an engineering pipeline specification, not a legal compliance
    certification.
  - No real data collection, labeling tool, model training, model registry,
    server rollout, or device OTA path is implemented.

# Builder Prompt

```text
Read docs/tasks/active/DATA-002_DATA_FLYWHEEL_PIPELINE_SPEC.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
in this packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Produce a current DATA-002 pipeline specification that ties
session evidence to consented, privacy-reviewed training-candidate records.
Do not collect private data, train a model, change firmware or protocol, or
implement OTA. Run the validation commands before finishing and return changed
files, validation output, evidence paths, unresolved decisions, and risks.
```
