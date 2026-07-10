---
id: DATA-008
title: D1 post-run collector
status: done
priority: high
requires_hardware: false
serves_demo: D1/D5
created: 2026-07-05
last_updated: 2026-07-05

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ACTIVE_BUILD.md
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/tasks/done/DATA-006_DATA_FLYWHEEL_PIPELINE_RUNNER.md
  - docs/tasks/done/TRAIN-002_TRAINING_EXPERIMENT_REGISTRY.md

allowed_paths:
  - scripts/collect_d1_postrun.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_postrun_collector.py
  - quality_tests/test_d1_field_kit.py
  - quality_tests/test_message_hub_server.py
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/STATUS.md
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/tasks/done/DATA-008_D1_POSTRUN_COLLECTOR.md

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - deploying to the VPS or touching GitLab
  - training or evaluating a model, integrating a runner, or producing model artifacts
  - copying candidate DBs, raw candidate records, private coordinates, raw payloads, runtime JSONL logs, or private training endpoints
  - claiming location accuracy, battery life, GNSS acceptance, product readiness, model metrics, footprint, latency, or power impact
---

# Goal

Serve D1/D5: make the normal post-field step one repeatable local command that
collects D1 review evidence and refreshes the data-flywheel/training handoff
state without touching hardware or exposing private raw data.

# Acceptance Criteria

- [x] A single collector command can compose the D1 Web/API gate, power curve,
      D1 demo report, data-flywheel pipeline, dataset manifest, training
      experiment plan, and a bounded post-run summary.
- [x] The collector can still write an explainable summary when power analysis
      or data-flywheel work is intentionally skipped.
- [x] The D1 field kit uses the collector as the recommended after-run command
      while retaining individual component commands for troubleshooting.
- [x] FIELD-004 documents the shorter after-run workflow.
- [x] Focused tests and repository validation pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_postrun_collector quality_tests.test_d1_field_kit quality_tests.test_message_hub_server.MessageHubHttpTests.test_get_api_requires_token_when_auth_is_enabled -v
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
  `quality_tests/test_message_hub_server.py`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/STATUS.md`,
  `docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md`, and this packet.
- Validation: focused D1 post-run collector, D1 field-kit, and isolated
  Message Hub auth tests passed (7 tests); `python -m py_compile
  scripts\collect_d1_postrun.py scripts\prepare_d1_field_kit.py` passed;
  `python scripts\context_lint.py` passed; `git diff --check` passed; full
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed (420
  tests).
- Remaining risks: the collector does not create training-ready data by itself;
  it records `needs_recordings`, `needs_review`, or TRAIN-002 blocker states
  until explicitly named recordings are ingested, reviewed, and exported. It
  does not sync summaries to the VPS; the existing explicit deploy/sync command
  remains separate.
