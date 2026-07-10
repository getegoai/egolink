---
id: MODEL-DEVICE-007
title: Tiny Safety static footprint report
status: done
priority: high
requires_hardware: false
serves_demo: D4-D5
created: 2026-07-07
last_updated: 2026-07-07

context:
  - docs/product/NORTH_STAR.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/modeling/MODEL_FOOTPRINT_ASSESSMENT.md
  - docs/tasks/done/MODEL-DEVICE-001_TINY_SAFETY_MODEL_V0.md
  - docs/tasks/done/MODEL-DEVICE-006_TINY_SAFETY_HARDWARE_FLASH_VALIDATION.md

allowed_paths:
  - model_lab/safety_companion/evaluation/
  - model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/assessment/
  - quality_tests/test_tiny_safety_static_footprint.py
  - docs/current/STATUS.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/tasks/active/MODEL-001_MODEL_FOOTPRINT_ASSESSMENT.md
  - docs/tasks/active/MODEL-DEVICE-007_TINY_SAFETY_STATIC_FOOTPRINT.md
  - docs/tasks/done/MODEL-DEVICE-007_TINY_SAFETY_STATIC_FOOTPRINT.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - changing model behavior, thresholds, labels, schemas, or artifacts used for inference
  - training on private or field samples
  - flashing firmware, opening serial ports, sending hardware commands, or contacting hardware
  - claiming runtime RAM, latency, power, real-world accuracy, MotionNet acceptance, or release readiness
  - selecting a production MCU or replacing PROD-001 `TBD(MODEL-001)` values
---

# Goal

Serve D4-D5 by turning the existing MODEL-DEVICE-001 Tiny Safety v0 artifact
and MODEL-DEVICE-006 build output into a bounded static footprint report.

# Acceptance Criteria

- [x] A no-hardware evaluator reads the existing Tiny Safety artifact/export
      files and writes JSON/Markdown static footprint evidence.
- [x] The report includes model identity/hash, feature/class counts, parameter
      count, estimated constant bytes, simple operation counts, optional
      firmware app bytes, source status, known gaps, and evidence level.
- [x] Missing runtime RAM, latency, and energy fields remain `unknown` rather
      than inferred from static files.
- [x] The report states that Tiny Safety v0 is not MotionNet acceptance
      evidence and cannot replace MODEL-001/PROD-001 measured gates.
- [x] Focused tests cover the evaluator and non-claim boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_tiny_safety_static_footprint -v
python scripts/context_lint.py
git diff --check
```

Run full verify if shared behavior is affected:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Not required; this task must not contact hardware.

# Progress Evidence

- Changed files:
  - `model_lab/safety_companion/evaluation/assess_tiny_safety_static_footprint.py`
  - `model_lab/safety_companion/evaluation/README.md`
  - `quality_tests/test_tiny_safety_static_footprint.py`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/assessment/tiny_safety_static_footprint.json`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/assessment/tiny_safety_static_footprint.md`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/assessment/sha256.txt`
  - `docs/current/STATUS.md`
  - `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
  - `docs/tasks/active/MODEL-001_MODEL_FOOTPRINT_ASSESSMENT.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
- Static footprint report:
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/assessment/tiny_safety_static_footprint.md`
  - Evidence level: `L2_build_verified_static_partial`
  - Model: `MODEL-DEVICE-001-tiny-safety-v0-20260707` /
    `0.1.0-synthetic-dry-run`
  - Static metrics: 14 features, 4 classes, 60 parameters, 834 estimated C
    constant bytes, 56 score multiplies, 56 score adds, 4 confidence `expf`
    calls.
  - Local firmware build context: `321248` app bytes when
    `firmware/mqtt_heartbeat/build_model_device_006_tiny_safety/egolink_mqtt_heartbeat.bin`
    is present.
- Test result:
  - `python -m unittest quality_tests.test_tiny_safety_static_footprint -v`:
    PASS, 3 tests.
- Hardware result: not contacted; no flash, serial command, runtime
  measurement, power measurement, or VPS command was performed by this task.
- Remaining risks:
  - Runtime RAM, latency, energy, and model static delta are still unknown.
  - This is not MotionNet-class acceptance evidence.
  - MODEL-001 MCU comparison and PROD-001 budget values remain blocked on
    measured evidence.
