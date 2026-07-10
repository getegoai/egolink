---
id: DATA-024
title: D1 labeling/privacy intake visibility
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
  - docs/tasks/done/DATA-022_D1_TRAINING_READINESS_VISIBILITY.md
  - docs/tasks/done/DATA-023_POSTRUN_TRAINING_READINESS_BINDING.md

allowed_paths:
  - scripts/build_d1_labeling_intake.py
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/test_d1_labeling_intake.py
  - quality_tests/test_message_hub_dashboard.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-024_D1_LABELING_INTAKE_VISIBILITY.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading D1 sample JSONL contents or exposing exact coordinates
  - writing candidate DBs, raw candidate records, feature rows, or targets
  - changing firmware, protocol, device behavior, hardware setup, or VPS GitLab
  - training/evaluating/deploying a model or making release claims
---

# Goal

Serve D5: surface a bounded D1 labeling/privacy intake queue from DATA-022
readiness so real field runs can wait for labels, consent, privacy, and split
review before any candidate-store write.

# Acceptance Criteria

- [x] `scripts/build_d1_labeling_intake.py` writes
      `egolink.d1_labeling_intake.v0.1` JSON/Markdown from a D1 readiness
      report.
- [x] Ready D1 reports become `pending_human_review` intake items; not-ready
      reports do not enter the queue.
- [x] Message Hub `/api/state`, `/api/v1/d1-labeling-intake/latest`, and the
      Dashboard can show the latest bounded intake summary.
- [x] VPS deploy packaging can include only `d1_labeling_intake.json/.md`.
- [x] Tests verify private coordinates, raw payloads, sample JSONL paths,
      feature rows, targets, candidate DBs, and training claims are not exposed.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_labeling_intake quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
python -m py_compile scripts\build_d1_labeling_intake.py server\message_hub.py
python scripts\context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/build_d1_labeling_intake.py`,
  `server/message_hub.py`, `scripts/deploy_message_hub_vps.ps1`,
  `quality_tests/test_d1_labeling_intake.py`,
  `quality_tests/test_message_hub_dashboard.py`, route docs, generated
  progress board files, and this packet.
- Focused behavior: tests cover ready and not-ready intake reports plus
  Dashboard/API redaction for D1 intake summaries.
- Remaining risks: DATA-024 does not implement the actual labeling UI,
  consent/privacy workflow, split-review workflow, candidate-store write,
  model training, model evaluation, model deployment, or power/footprint
  measurement.
