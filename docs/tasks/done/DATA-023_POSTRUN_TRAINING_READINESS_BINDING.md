---
id: DATA-023
title: D1 post-run training-readiness binding
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
  - docs/tasks/done/DATA-019_POSTRUN_FIELD_OBSERVATION_BINDING.md
  - docs/tasks/done/DATA-022_D1_TRAINING_READINESS_VISIBILITY.md

allowed_paths:
  - scripts/collect_d1_postrun.py
  - quality_tests/test_d1_postrun_collector.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-023_POSTRUN_TRAINING_READINESS_BINDING.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading `d1_field_samples.jsonl` contents into summaries
  - changing firmware, protocol, Message Hub API behavior, model behavior, or device deployment
  - exposing exact coordinates, raw payloads, feature rows, targets, candidate DBs, private endpoints, or model artifacts
  - training/evaluating a model, measuring model footprint/power, or making release claims
---

# Goal

Serve D5: include DATA-022 D1 real-data training-readiness status in the normal
D1 post-run collector, so one post-field command shows whether the run can
enter labeling/privacy review before training handoff.

# Acceptance Criteria

- [x] `scripts/collect_d1_postrun.py` schema is bumped to
      `egolink.d1_postrun_collection.v0.6`.
- [x] When a field-observation report/status summary exists, the collector
      writes a DATA-022 readiness report and includes a `training_readiness`
      component.
- [x] The post-run artifact list includes `d1_training_readiness`.
- [x] Missing field-observation evidence makes `training_readiness` skipped
      explainably.
- [x] The collector preserves no-hardware/no-command/no-firmware/no-training
      boundaries.
- [x] Focused collector tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_postrun_collector -v
python -m py_compile scripts\collect_d1_postrun.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/collect_d1_postrun.py`,
  `quality_tests/test_d1_postrun_collector.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/STATUS.md`, generated progress board files, and this packet.
- Local collector behavior: focused tests verify a post-run with a D1
  field-observation report includes `training_readiness.status=
  ready_for_labeling_review`, keeps `ready_for_training_handoff=false` and
  `training_allowed=false`, and writes a bounded `d1_training_readiness.json`
  artifact.
- Remaining risks: DATA-023 does not add labeling UI, consent/privacy review,
  real training-candidate export, model training/evaluation, on-device
  deployment, model footprint/power measurement, or release gates.
