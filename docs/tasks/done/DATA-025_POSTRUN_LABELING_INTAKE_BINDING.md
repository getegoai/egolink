---
id: DATA-025
title: D1 post-run labeling-intake binding
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
  - docs/tasks/done/DATA-023_POSTRUN_TRAINING_READINESS_BINDING.md
  - docs/tasks/done/DATA-024_D1_LABELING_INTAKE_VISIBILITY.md

allowed_paths:
  - scripts/collect_d1_postrun.py
  - quality_tests/test_d1_postrun_collector.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-025_POSTRUN_LABELING_INTAKE_BINDING.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading D1 sample JSONL contents or exposing exact coordinates
  - writing candidate DBs, labels, feature rows, targets, or model artifacts
  - changing firmware, protocol, device behavior, hardware setup, or VPS GitLab
  - training/evaluating/deploying a model or making release claims
---

# Goal

Serve D5: include DATA-024 D1 labeling/privacy intake in the normal D1
post-run collector so one post-field command shows which real run is waiting
for labels, privacy, consent, and split review.

# Acceptance Criteria

- [x] `scripts/collect_d1_postrun.py` schema is bumped to
      `egolink.d1_postrun_collection.v0.7`.
- [x] When D1 training-readiness output exists, the collector writes a
      `labeling_intake` component and `d1_labeling_intake` artifact.
- [x] Missing readiness evidence makes `labeling_intake` skipped explainably.
- [x] The collector preserves no-JSONL, no-candidate-DB, no-training,
      no-firmware, no-hardware-command, and no-release-claim boundaries.
- [x] Focused collector tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_postrun_collector -v
python -m py_compile scripts\collect_d1_postrun.py
python scripts\context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/collect_d1_postrun.py`,
  `quality_tests/test_d1_postrun_collector.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/STATUS.md`, generated progress board files, and this packet.
- Focused collector tests verify ready post-run output includes
  `labeling_intake.status=pending_human_review` and a bounded
  `d1_labeling_intake.json` artifact, while missing readiness evidence skips
  the component explainably.
- Remaining risks: DATA-025 does not implement labeling UI, consent/privacy
  workflow, split-review workflow, candidate-store write, model
  training/evaluation, model deployment, or model footprint/power measurement.
