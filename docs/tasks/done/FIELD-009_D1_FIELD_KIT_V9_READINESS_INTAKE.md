---
id: FIELD-009
title: D1 3-4h field kit v9 readiness and intake closure
status: done
priority: high
requires_hardware: false
serves_demo: D1
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DEV_FLOW.md
  - docs/current/ACTIVE_BUILD.md
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/tasks/done/DATA-025_D1_POSTRUN_LABELING_INTAKE_BINDING.md

allowed_paths:
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_field_kit.py
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/current/STATUS.md
  - docs/tasks/done/FIELD-009_D1_FIELD_KIT_V9_READINESS_INTAKE.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, sending Message Hub commands, or deploying to the VPS
  - reading or exposing `d1_field_samples.jsonl`, raw payloads, private coordinates, candidate DBs, or feature rows
  - changing firmware, protocol, public APIs, model behavior, training behavior, or field acceptance gates
  - making location accuracy, battery-life, GNSS, LTE stability, calling/SMS, model, or product-readiness claims
---

# Goal

Serve D1: refresh the generated outdoor field kit for the next 3-4h run so
post-run evidence closes into D1 training-readiness and labeling-intake queues.

# Acceptance Criteria

- [x] The field kit version advances and lists D1 training-readiness plus
      labeling-intake as expected post-run artifacts.
- [x] The runbook, checklist, and operator notes tell the operator how to see
      those bounded review queues after returning.
- [x] The curated VPS sync command includes the existing summary switches for
      D1 readiness and D1 labeling intake without copying raw samples.
- [x] Focused tests cover the new kit surface.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_field_kit -v
python -m py_compile scripts\prepare_d1_field_kit.py
python scripts\context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/prepare_d1_field_kit.py`,
  `quality_tests/test_d1_field_kit.py`,
  `docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md`,
  `docs/current/STATUS.md`, generated progress-board files, and this packet.
- Validation: focused field-kit tests passed (4 tests);
  `python -m py_compile scripts\prepare_d1_field_kit.py` passed;
  `python scripts\context_lint.py` passed; `git diff --check` passed with
  generated-file CRLF warnings only; full `scripts\verify.ps1` passed
  (474 tests).
- Remaining risks: this is a no-hardware kit refresh. The next 3-4h outdoor
  result still depends on the device, SIM/LTE coverage, GNSS placement, power
  setup, and the operator actually running or post-collecting evidence.
