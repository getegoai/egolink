---
id: D1-002
title: Outdoor field kit with AMOLED companion
status: done
priority: medium
requires_hardware: false
serves_demo: D1
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/tasks/done/AMOLED-004_VISIBLE_D1_STATUS_DISPLAY.md

allowed_paths:
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_d1_field_kit.py
  - docs/current/
  - docs/hardware/BOARD_MATRIX.md
  - docs/tasks/
  - docs/generated/

out_of_scope:
  - changing firmware
  - contacting hardware or Message Hub from the generator
  - sending Message Hub commands
  - dialing calls, sending SMS, or probing live phone/SMS AT commands
  - claiming GNSS fix, location accuracy, battery life, calling, SMS, or product readiness
---

# Problem

After the AMOLED sidecar became visible, the operator needs one field kit that
shows the right preflight, live companion, and post-run report commands for a
multi-hour D1 outdoor run.

# Expected Result

The offline D1 field kit includes a visible AMOLED companion path, read-only
preflight/review commands, post-run evidence composition, and explicit
calling/SMS non-claim boundaries.

# Acceptance Criteria

- [x] Field kit manifest includes preflight Web/API, AMOLED visible-status, live
      companion, and post-run report commands.
- [x] Generated runbook/checklist explain the single companion command for an
      outdoor walk and where the evidence lands.
- [x] Voice calling and SMS remain documented as unverified/not implemented.
- [x] Generator remains offline-only: no hardware contact, no Message Hub
      contact, no firmware flash, no secrets persisted.
- [x] Focused tests, context lint, full verify, progress board, and diff check
      pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_field_kit -v
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\build_progress_board.py
```

# Completion Evidence

- Changed files: `scripts/prepare_d1_field_kit.py`,
  `quality_tests/test_d1_field_kit.py`, `docs/hardware/BOARD_MATRIX.md`,
  `docs/current/STATUS.md`, and this task packet.
- Test result: focused `quality_tests.test_d1_field_kit` passed, and
  `python scripts/context_lint.py` passed. `python scripts/build_progress_board.py`
  regenerated the board with `done=81`. Full `scripts\verify.ps1` passed with
  387 tests. `git diff --check` reported no errors.
- Hardware result: no hardware was contacted by the generator. A current kit
  was generated at `reports/d1_field/d1-outdoor-kit-20260704/`, with
  `sidecar.status_command=display_status`, `amoled_port=COM9`,
  `voice_calling=unverified_not_implemented`, and
  `sms=unverified_not_implemented`. Token value check reported no token in the
  generated kit.
- Remaining risks: the kit prepares commands only. Long outdoor runtime,
  GNSS fix, location accuracy, battery life, calling, SMS, and product
  readiness remain unverified until separate hardware evidence exists.
