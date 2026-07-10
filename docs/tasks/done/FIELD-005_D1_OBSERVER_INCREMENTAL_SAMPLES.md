---
id: FIELD-005
title: D1 observer incremental samples
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
  - docs/tasks/done/DATA-008_D1_POSTRUN_COLLECTOR.md

allowed_paths:
  - scripts/observe_d1_field_run.py
  - quality_tests/test_d1_field_observer.py
  - docs/development/FIELD_TEST.md
  - docs/current/STATUS.md
  - docs/tasks/done/FIELD-005_D1_OBSERVER_INCREMENTAL_SAMPLES.md

out_of_scope:
  - changing the Message Hub API, firmware, protocol, field acceptance gates, or power/location claims
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - changing the currently running observer process
---

# Goal

Serve D1: make future long D1 Web/API observations easier to monitor by
writing each sample to `d1_field_samples.jsonl` as soon as it is collected,
instead of waiting until the observer exits.

# Acceptance Criteria

- [x] `scripts/observe_d1_field_run.py` initializes the samples JSONL at the
      start of a run and appends every sample immediately after collection.
- [x] The final report still writes `d1_field_observation_report.json/.md` and
      records `sample_write_mode=incremental_jsonl`.
- [x] Existing observer behavior and non-claim boundaries remain unchanged.
- [x] Focused observer tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_field_observer -v
python -m py_compile scripts\observe_d1_field_run.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/observe_d1_field_run.py`,
  `quality_tests/test_d1_field_observer.py`, `docs/development/FIELD_TEST.md`,
  `docs/current/STATUS.md`, and this packet.
- Focused validation passed: observer tests cover the existing CLI/report path
  and a new two-sample fake fetch loop that verifies the first sample exists in
  `d1_field_samples.jsonl` before the second fetch begins.
- Remaining risks: this change affects future observer runs only. The D1
  observer process that was already running before this task keeps the old
  end-of-run sample write behavior.
