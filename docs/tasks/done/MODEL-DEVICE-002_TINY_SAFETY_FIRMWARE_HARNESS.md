---
id: MODEL-DEVICE-002
title: Tiny Safety firmware dry-run harness
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
  - shared/contracts/model_input.schema.json
  - shared/contracts/model_output.schema.json
  - shared/embedded/safety_model_contract.h
  - model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/export/tiny_safety_model.h
  - model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/export/tiny_safety_test_vectors.json

allowed_paths:
  - firmware/mqtt_heartbeat/components/safety_model/
  - quality_tests/test_safety_model_firmware.py
  - quality_tests/test_tiny_safety_firmware_harness.py
  - docs/current/STATUS.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/tasks/done/MODEL-DEVICE-002_TINY_SAFETY_FIRMWARE_HARNESS.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - flashing firmware or contacting hardware
  - changing SOS, cancel, privacy, power, or external escalation rules
  - sending SMS, placing calls, dispatching, or triggering real safety actions
  - changing shared contracts, protocol fields, pin assignments, or board configuration
  - training a new model, reading private field samples, deploying to VPS, or claiming real-world accuracy/power
---

# Goal

Serve D5: connect the MODEL-DEVICE-001 Tiny Safety C export to the existing
firmware safety-model component as a dry-run inference harness.

# Expected Result

Firmware code can extract the tiny feature vector, run linear inference against
the generated C constants, and self-check the exported synthetic test vectors
without changing the existing deterministic safety model behavior.

# Acceptance Criteria

- [x] The firmware safety-model component exposes a tiny dry-run API that
      returns only candidate state labels and scores.
- [x] The API uses the generated MODEL-DEVICE-001 C constants as the source of
      truth.
- [x] The dry-run path does not map tiny model output to real calls, SMS,
      dispatch, or external escalation.
- [x] A focused quality test checks the C constants, firmware API boundaries,
      and exported test-vector consistency.
- [x] Documentation states this is firmware harness integration only, not a
      flashed image, measured footprint, power result, or release claim.

# Validation Commands

```powershell
python -m unittest quality_tests.test_tiny_safety_firmware_harness quality_tests.test_safety_model_firmware -v
python scripts/context_lint.py
git diff --check
```

Run full verify because firmware and behavior-adjacent code changes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Not required and not performed.
- Future flashing must identify board, port, firmware commit or image, timestamp,
  and evidence path.

# Decisions

- Keep `safety_model_evaluate()` as the current deterministic mock/rule baseline.
- Add the learned tiny model only as an explicit dry-run harness until measured
  footprint, latency, RAM, flash, power, and Safety Kernel integration gates exist.

# Completion Evidence

- Changed files:
  - `firmware/mqtt_heartbeat/components/safety_model/CMakeLists.txt`
  - `firmware/mqtt_heartbeat/components/safety_model/include/safety_model.h`
  - `firmware/mqtt_heartbeat/components/safety_model/tiny_safety_harness.c`
  - `quality_tests/test_safety_model_firmware.py`
  - `quality_tests/test_tiny_safety_firmware_harness.py`
  - `docs/current/STATUS.md`
  - `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
  - `docs/tasks/done/MODEL-DEVICE-002_TINY_SAFETY_FIRMWARE_HARNESS.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
- Test result:
  - `python -m unittest quality_tests.test_tiny_safety_firmware_harness quality_tests.test_safety_model_firmware -v`: PASS, 10 tests.
  - `python scripts/context_lint.py`: PASS before and after task close.
  - `git diff --check`: PASS with CRLF warnings for generated progress-board files.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 501 tests.
  - ESP-IDF build: PASS for `firmware/mqtt_heartbeat`, generated `build/egolink_mqtt_heartbeat.bin` size `0xd9740`; build only, no flash.
- Hardware result: not performed; no board contacted, no firmware flashed, no serial command sent.
- Remaining risks:
  - Tiny harness has not run on hardware.
  - No runtime latency, RAM, flash delta, or power measurement is claimed.
  - Synthetic-only labels are integration evidence, not real-world safety accuracy.
