---
id: DATA-019
title: Post-run field-observation binding
status: done
priority: medium
requires_hardware: false
serves_demo: D1
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/development/FIELD_TEST.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/tasks/done/FIELD-006_D1_OBSERVER_LIVE_STATUS.md
  - docs/tasks/done/DATA-018_POSTRUN_JOB_PLAN_COLLECTOR.md

allowed_paths:
  - scripts/collect_d1_postrun.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_postrun_collector.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-019_POSTRUN_FIELD_OBSERVATION_BINDING.md

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - changing the Message Hub API, firmware, protocol, field acceptance gates, or power/location claims
  - copying field-observer sample JSONL contents, raw payloads, candidate DBs, private coordinates, or runtime JSONL logs into the summary
  - deploying to the VPS or touching GitLab
  - training or evaluating a real model, integrating a GPU runner, model registry, or OTA path
  - producing model weights, model cards, model artifacts, measured footprint, measured latency, measured power, device deployment, or release claims
---

# Goal

Serve D1: make the normal D1 post-run summary point at the field-observation
evidence that was collected during the outdoor run.

# Acceptance Criteria

- [x] `scripts/collect_d1_postrun.py` can bind an explicit or same-run local
      `d1_field_observation_report.json`.
- [x] If the final report is not present but the live status snapshot exists,
      the summary records the running observer state and latest sample metadata.
- [x] Missing observation evidence remains explainable and does not block the
      rest of the post-run summary.
- [x] The D1 field kit recommended post-run command passes the expected
      observation report/status paths.
- [x] Focused collector/field-kit tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit -v
python -m py_compile scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/collect_d1_postrun.py`,
  `scripts/prepare_d1_field_kit.py`,
  `quality_tests/test_d1_postrun_collector.py`,
  `quality_tests/test_d1_field_kit.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`, `docs/current/STATUS.md`,
  and this packet.
- Focused validation passed: collector tests cover missing observation evidence
  as explainable skipped state and explicit report/status binding in a ready
  training-chain run.
- Remaining risks: DATA-019 does not make field evidence a product acceptance
  claim. Outdoor GNSS, LTE stability, power baseline, model training,
  deployment, and release gates still require separate reviewed evidence.
