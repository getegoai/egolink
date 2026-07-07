---
id: MODEL-DEVICE-003
title: Tiny Safety firmware CLI closed loop
status: done
priority: high
requires_hardware: false
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
  - shared/embedded/safety_model_contract.h
  - docs/tasks/done/MODEL-DEVICE-001_TINY_SAFETY_MODEL_V0.md
  - docs/tasks/done/MODEL-DEVICE-002_TINY_SAFETY_FIRMWARE_HARNESS.md

allowed_paths:
  - firmware/mqtt_heartbeat/main/app_main.c
  - quality_tests/test_safety_model_firmware.py
  - quality_tests/test_tiny_safety_firmware_harness.py
  - docs/current/STATUS.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/tasks/done/MODEL-DEVICE-003_TINY_SAFETY_FIRMWARE_CLI_LOOP.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - flashing firmware or contacting hardware
  - changing shared contracts, protocol fields, pin assignments, or board configuration
  - mapping model output to SMS, calls, dispatch, or external escalation
  - changing deterministic SOS, cancel, privacy, power, or Safety Kernel rules
  - training a new model, reading private field samples, deploying to VPS, or claiming accuracy/power
---

# Goal

Serve D5: make the MODEL-DEVICE-001 Tiny Safety artifact observable from the
firmware serial CLI after flashing, while keeping it dry-run and candidate-only.

# Expected Result

The `mqtt_heartbeat` firmware exposes tiny safety status, self-test, and demo
prediction commands through the existing bounded safety CLI.

# Acceptance Criteria

- [x] `safety tiny status` reports harness/model identity and dry-run scope.
- [x] `safety tiny selftest` runs the exported synthetic test-vector check.
- [x] `safety tiny demo ...` reports candidate labels for normal/uncertain/
      needs_check/possible_risk and `safety_rule_required` for SOS.
- [x] Tests prove the CLI does not introduce real SMS/call/dispatch behavior.
- [x] ESP-IDF build passes without flashing or contacting hardware.

# Validation Commands

```powershell
python -m unittest quality_tests.test_safety_model_firmware quality_tests.test_tiny_safety_firmware_harness -v
python scripts/context_lint.py
git diff --check
```

Run full verify because firmware code changes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Not required and not performed.
- Future flash/runtime evidence must identify board, port, firmware commit or
  image, timestamp, commands, and evidence path.

# Completion Evidence

- Changed files:
  - `firmware/mqtt_heartbeat/main/app_main.c`
  - `quality_tests/test_safety_model_firmware.py`
  - `quality_tests/test_tiny_safety_firmware_harness.py`
  - `docs/current/STATUS.md`
  - `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
  - `docs/tasks/done/MODEL-DEVICE-003_TINY_SAFETY_FIRMWARE_CLI_LOOP.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
- Test result:
  - `python -m unittest quality_tests.test_safety_model_firmware quality_tests.test_tiny_safety_firmware_harness -v`: PASS, 11 tests.
  - `python scripts/context_lint.py`: PASS before and after task close.
  - `git diff --check`: PASS with CRLF warnings for generated progress-board files.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 502 tests.
  - ESP-IDF build: PASS for `firmware/mqtt_heartbeat`, generated `build/egolink_mqtt_heartbeat.bin` size `0xda8d0`; build only, no flash.
- Hardware result: not performed; no board contacted, no firmware flashed, no serial command sent.
- Remaining risks:
  - CLI has not run on a physical board yet.
  - No runtime latency, RAM, flash delta attribution, or power measurement is claimed.
  - Synthetic-only candidate labels are integration evidence, not real-world safety accuracy.
