---
id: FIELD-006
title: D1 observer live status snapshot
status: done
priority: medium
requires_hardware: false
serves_demo: D1
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/development/FIELD_TEST.md
  - docs/current/ACTIVE_BUILD.md
  - docs/tasks/done/FIELD-005_D1_OBSERVER_INCREMENTAL_SAMPLES.md

allowed_paths:
  - scripts/observe_d1_field_run.py
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_field_observer.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/FIELD_TEST.md
  - docs/current/STATUS.md
  - docs/tasks/done/FIELD-006_D1_OBSERVER_LIVE_STATUS.md

out_of_scope:
  - changing the Message Hub API, firmware, protocol, field acceptance gates, or power/location claims
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - changing the currently running observer process
---

# Goal

Serve D1: make future long D1 Web/API observations easier to monitor by
writing a bounded live status snapshot while the observer is still polling.

# Acceptance Criteria

- [x] `scripts/observe_d1_field_run.py` writes
      `d1_field_observation_status.json` at startup, after each sample, and at
      completion.
- [x] The live status includes running/completed state, sample counts, latest
      successful sample metadata, latest seq/freshness, and final report paths.
- [x] The field kit records the live status file in expected outputs.
- [x] Existing observer behavior and non-claim boundaries remain unchanged.
- [x] Focused observer and field-kit tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_field_observer quality_tests.test_d1_field_kit -v
python -m py_compile scripts\observe_d1_field_run.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/observe_d1_field_run.py`,
  `scripts/prepare_d1_field_kit.py`,
  `quality_tests/test_d1_field_observer.py`,
  `quality_tests/test_d1_field_kit.py`, `docs/development/FIELD_TEST.md`,
  `docs/current/STATUS.md`, and this packet.
- Focused validation passed: observer tests cover the existing CLI/report path
  and a two-sample fake fetch loop that verifies the status file is `running`
  after the first sample and `completed` after the final report.
- Remaining risks: this change affects future observer runs only. The D1
  observer process that was already running before this task keeps its existing
  output behavior.
