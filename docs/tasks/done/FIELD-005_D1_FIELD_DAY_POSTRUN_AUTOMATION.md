---
id: FIELD-005
title: D1 field-day post-run automation
status: done
priority: high
requires_hardware: false
serves_demo: D1
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/tasks/active/PWR-001_POWER_TELEMETRY_24H_BATTERY_BASELINE.md
  - docs/tasks/done/DATA-004_DATA_FLYWHEEL_CONTROL_PLANE.md
  - docs/current/ACTIVE_BUILD.md

allowed_paths:
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_field_kit.py
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/current/STATUS.md
  - docs/tasks/done/FIELD-005_D1_FIELD_DAY_POSTRUN_AUTOMATION.md
  - docs/generated/

out_of_scope:
  - contacting hardware
  - flashing firmware
  - sending Message Hub commands
  - changing firmware, protocol, model behavior, or server ingest
  - claiming location accuracy, battery life, 24h PWR-001 pass, or product readiness
---

# Goal

Serve D1: make the 2026-07-05 outdoor/long-run workflow easier to execute and
review by adding post-run data-flywheel and Dashboard-summary sync steps to the
field kit.

# Acceptance Criteria

- [x] Field kit includes post-run Data Flywheel status generation.
- [x] Field kit includes Dashboard summary sync with both field and data
      flywheel curated summaries.
- [x] FIELD-004 post-run commands mention the same summary sync path.
- [x] Focused tests and context validation pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_field_kit -v
python scripts/context_lint.py
python -m py_compile scripts\prepare_d1_field_kit.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/prepare_d1_field_kit.py`,
  `quality_tests/test_d1_field_kit.py`,
  `docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md`,
  `docs/current/STATUS.md`, generated progress-board files, and this packet.
- Runtime artifact: generated an offline 2026-07-05 kit at
  `reports/d1_field/FIELD-004-d1-outdoor-20260705/` with runbook, checklist,
  notes template, and manifest. This artifact is local evidence and is not
  committed.
- Validation: focused D1 field-kit tests passed (4 tests);
  `python -m py_compile scripts\prepare_d1_field_kit.py` passed;
  `python scripts/context_lint.py` passed; `git diff --check` passed; full
  `scripts\verify.ps1` passed.
- Remaining risks: the 2026-07-05 field run itself is still operator/hardware
  work; no GNSS accuracy, battery life, 24h PWR-001 pass, calling/SMS, or
  product readiness is claimed by this helper.
