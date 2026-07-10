---
id: MODEL-DEVICE-004
title: Tiny Safety firmware CLI validator
status: done
priority: high
requires_hardware: optional
serves_demo: D5
created: 2026-07-07
last_updated: 2026-07-07

context:
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/ACTIVE_BUILD.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/safety/SAFETY_CONTRACT.md
  - docs/tasks/done/MODEL-DEVICE-001_TINY_SAFETY_MODEL_V0.md
  - docs/tasks/done/MODEL-DEVICE-002_TINY_SAFETY_FIRMWARE_HARNESS.md
  - docs/tasks/done/MODEL-DEVICE-003_TINY_SAFETY_FIRMWARE_CLI_LOOP.md

allowed_paths:
  - scripts/validate_tiny_safety_firmware_cli.py
  - quality_tests/test_tiny_safety_firmware_cli_validator.py
  - docs/current/STATUS.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/tasks/done/MODEL-DEVICE-004_TINY_SAFETY_FIRMWARE_CLI_VALIDATOR.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - flashing firmware by default or changing firmware behavior
  - changing shared contracts, protocol fields, pin assignments, or board configuration
  - mapping model output to SMS, calls, dispatch, or external escalation
  - changing deterministic SOS, cancel, privacy, power, or Safety Kernel rules
  - training a new model, reading private field samples, deploying to VPS, or claiming accuracy/power
---

# Goal

Serve D5: add a safe host-side validator that can later verify a flashed
MODEL-DEVICE-003 firmware image over the serial CLI and preserve evidence.

# Expected Result

A script can run in no-hardware dry-run mode, replay fixture logs, or, with an
explicit hardware guard, send `safety tiny ...` commands to a bounded serial
session and write JSON/Markdown evidence.

# Acceptance Criteria

- [x] Default invocation does not open a serial port or contact hardware.
- [x] Serial mode requires both `--port` and `--i-understand-serial-hardware`.
- [x] Fixture/serial parsing checks `TINY_SAFETY_STATUS`, `TINY_SAFETY_SELFTEST`,
      and all `TINY_SAFETY_DEMO` labels.
- [x] Reports include non-claims: no flash, no real SMS/call/dispatch, no
      field accuracy, latency, RAM, flash, or power claim.
- [x] Focused tests cover dry-run, guard failure, passing fixture, and failing
      fixture behavior.

# Validation Commands

```powershell
python -m unittest quality_tests.test_tiny_safety_firmware_cli_validator -v
python scripts/context_lint.py
git diff --check
```

Run full verify because a new validation script and task-visible behavior are
added:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Optional, not performed by default.
- Future runtime evidence must identify board, port, firmware image or commit,
  timestamp, command list, and evidence path.

# Completion Evidence

- Changed files:
  - `scripts/validate_tiny_safety_firmware_cli.py`
  - `quality_tests/test_tiny_safety_firmware_cli_validator.py`
  - `docs/current/STATUS.md`
  - `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
  - `docs/tasks/done/MODEL-DEVICE-004_TINY_SAFETY_FIRMWARE_CLI_VALIDATOR.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
- Test result:
  - `python -m unittest quality_tests.test_tiny_safety_firmware_cli_validator -v`: PASS, 6 tests.
  - `python scripts/context_lint.py`: PASS.
  - `git diff --check`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 508 tests.
- Hardware result: not performed; no board contacted, no firmware flashed, no
  serial command sent by default.
- Remaining risks:
  - The validator has not yet been run against a flashed physical board.
  - No runtime latency, RAM, flash delta, or power measurement is claimed.
  - Synthetic-only labels are integration evidence, not real-world safety accuracy.
