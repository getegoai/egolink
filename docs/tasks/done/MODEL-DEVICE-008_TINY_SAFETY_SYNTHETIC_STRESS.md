---
id: MODEL-DEVICE-008
title: Tiny Safety synthetic stress evaluation
status: done
priority: high
requires_hardware: false
serves_demo: D4-D5
created: 2026-07-07
last_updated: 2026-07-07

context:
  - docs/product/NORTH_STAR.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/safety/SAFETY_CONTRACT.md
  - docs/tasks/done/MODEL-DEVICE-001_TINY_SAFETY_MODEL_V0.md
  - docs/tasks/done/MODEL-DEVICE-007_TINY_SAFETY_STATIC_FOOTPRINT.md

allowed_paths:
  - model_lab/safety_companion/evaluation/
  - model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/evaluation/
  - quality_tests/test_tiny_safety_synthetic_stress.py
  - docs/current/STATUS.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/tasks/active/MODEL-DEVICE-008_TINY_SAFETY_SYNTHETIC_STRESS.md
  - docs/tasks/done/MODEL-DEVICE-008_TINY_SAFETY_SYNTHETIC_STRESS.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - changing model behavior, thresholds, labels, schemas, contracts, or artifacts used for inference
  - training on private, field, or candidate-store samples
  - claiming real-world accuracy, fall detection quality, runtime RAM, latency, power, or release readiness
  - flashing firmware, opening serial ports, contacting hardware, or sending device commands
  - mapping model output to real SMS, calls, dispatch, or external escalation
---

# Goal

Serve D4-D5 by stress-testing the existing MODEL-DEVICE-001 Tiny Safety v0
artifact against a deterministic synthetic boundary matrix and producing a
reviewable hard-case report for future labeling/model iteration.

# Acceptance Criteria

- [x] A no-hardware evaluator generates deterministic synthetic boundary cases
      and compares model predictions to a transparent synthetic oracle.
- [x] The report includes case counts, synthetic agreement rate, confusion
      matrix, low-confidence cases, disagreement examples, label priorities,
      and non-claim boundaries.
- [x] The report clearly states synthetic agreement is not real-world accuracy.
- [x] Focused tests cover deterministic case generation, report shape, and
      non-claim boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_tiny_safety_synthetic_stress -v
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
  - `model_lab/safety_companion/evaluation/evaluate_tiny_safety_synthetic_stress.py`
  - `model_lab/safety_companion/evaluation/README.md`
  - `quality_tests/test_tiny_safety_synthetic_stress.py`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/evaluation/tiny_safety_synthetic_stress.json`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/evaluation/tiny_safety_synthetic_stress.md`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/evaluation/sha256.txt`
  - `docs/current/STATUS.md`
  - `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
- Synthetic stress report:
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/evaluation/tiny_safety_synthetic_stress.md`
  - Cases: `540`.
  - Synthetic agreement: `365 / 540` (`0.675926`).
  - Low-confidence cases: `523`.
  - Low-margin cases: `331`.
  - Labeling priority: `uncertain` first, with 141 synthetic disagreements,
    237 low-confidence cases, and 202 low-margin cases.
- Test result:
  - `python -m unittest quality_tests.test_tiny_safety_synthetic_stress -v`:
    PASS, 3 tests.
- Hardware result: not contacted; no flash, serial command, runtime
  measurement, power measurement, VPS command, field/private data read, model
  training, or model behavior change was performed.
- Remaining risks:
  - Synthetic oracle agreement is not real-world accuracy.
  - Hard cases require human review and real labeled data before training use.
  - Runtime RAM, latency, power, and release readiness remain unmeasured.
