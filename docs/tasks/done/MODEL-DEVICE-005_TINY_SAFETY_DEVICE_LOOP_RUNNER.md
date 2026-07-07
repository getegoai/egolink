---
id: MODEL-DEVICE-005
title: Tiny Safety device loop runner
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
  - docs/tasks/done/MODEL-DEVICE-004_TINY_SAFETY_FIRMWARE_CLI_VALIDATOR.md

allowed_paths:
  - scripts/prepare_tiny_safety_device_loop.py
  - quality_tests/test_tiny_safety_device_loop.py
  - docs/current/STATUS.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/tasks/done/MODEL-DEVICE-005_TINY_SAFETY_DEVICE_LOOP_RUNNER.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - flashing firmware by default or changing firmware/model behavior
  - opening serial ports, sending serial commands, or contacting hardware by default
  - changing shared contracts, protocol fields, pin assignments, or board configuration
  - mapping model output to SMS, calls, dispatch, or external escalation
  - changing deterministic SOS, cancel, privacy, power, or Safety Kernel rules
  - training a new model, reading private field samples, deploying to VPS, or claiming accuracy/power
---

# Goal

Serve D5: turn the MODEL-DEVICE-001 through MODEL-DEVICE-004 local artifacts
into a repeatable operator-visible device-loop package for the next hardware
stage.

# Expected Result

A no-hardware script writes a JSON/Markdown run plan under
`reports/tiny_safety_device_loop/` with exact commands for build, optional
explicit flash, guarded serial Tiny Safety CLI validation, and USB-Free D1 Web
review after flashing.

# Acceptance Criteria

- [x] Default invocation does not open serial ports, flash firmware, contact
      hardware, read secrets, contact the VPS, or run commands.
- [x] The plan includes the D1 periodic-location firmware build command with
      Tiny Safety CLI support and MAX17048/SIM7670 feature switches.
- [x] The plan includes an explicit flash command guarded by
      `-Flash -FlashPort <COMx> -IUnderstandFlashWritesFirmware`.
- [x] The plan includes the guarded serial validator command using
      `scripts\validate_tiny_safety_firmware_cli.py` and
      `--i-understand-serial-hardware`.
- [x] The plan includes post-flash USB-Free Web/API and short observer commands
      so model-device evidence can be checked without serial runtime evidence.
- [x] Reports include evidence paths and non-claims: no default flash, no real
      SMS/call/dispatch, no model accuracy, no latency/RAM/flash/power claim.
- [x] Focused tests cover default scope, command guards, and non-claim
      boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_tiny_safety_device_loop -v
python scripts/context_lint.py
git diff --check
```

Run full verify because a new task-visible planner script is added:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Optional and not performed by default.
- Any later hardware evidence must identify board, firmware commit or image,
  connection path, port when serial is used, timestamp, command list, and
  evidence path.

# Completion Evidence

- Changed files:
  - `scripts/prepare_tiny_safety_device_loop.py`
  - `quality_tests/test_tiny_safety_device_loop.py`
  - `docs/current/STATUS.md`
  - `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
  - `docs/tasks/done/MODEL-DEVICE-005_TINY_SAFETY_DEVICE_LOOP_RUNNER.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
- Generated sample plan:
  - `reports/tiny_safety_device_loop/MODEL-DEVICE-005-plan-20260707/tiny_safety_device_loop_plan.json`
  - `reports/tiny_safety_device_loop/MODEL-DEVICE-005-plan-20260707/TINY_SAFETY_DEVICE_LOOP_RUNBOOK.md`
  - `reports/tiny_safety_device_loop/MODEL-DEVICE-005-plan-20260707/TINY_SAFETY_OPERATOR_NOTES.md`
- Test result:
  - `python -m unittest quality_tests.test_tiny_safety_device_loop -v`: PASS, 4 tests.
  - `python scripts/context_lint.py`: PASS.
  - `git diff --check`: PASS; reported CRLF normalization warnings for generated
    progress-board files only.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 512 tests.
- Hardware result: not performed; no board contacted, no firmware flashed, no
  serial port opened, no VPS contacted by the planner.
- Remaining risks:
  - The plan has not yet been used to build, flash, or validate a physical
    board.
  - No runtime latency, RAM, flash delta, power, or field accuracy measurement
    is claimed.

# Builder Prompt

```text
Read docs/tasks/active/MODEL-DEVICE-005_TINY_SAFETY_DEVICE_LOOP_RUNNER.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this
packet's context. Do only this task; obey allowed_paths and out_of_scope.
Create a no-hardware plan generator for the Tiny Safety device-loop stage.
Do not flash, open serial ports, contact hardware, contact the VPS, train a
model, change firmware/model behavior, or claim accuracy/power. Run validation
commands before finishing and return changed files, validation output, evidence
paths, unresolved decisions, and risks.
```
