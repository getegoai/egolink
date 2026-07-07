---
id: MODEL-DEVICE-001
title: Tiny Safety Model v0 local train/export loop
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
  - shared/contracts/model_input.schema.json
  - shared/contracts/model_output.schema.json

allowed_paths:
  - model_lab/safety_companion/src/tiny_safety_model.py
  - model_lab/safety_companion/training/train_tiny_safety_model.py
  - model_lab/safety_companion/export/export_tiny_safety_model.py
  - model_lab/safety_companion/training/README.md
  - model_lab/safety_companion/export/README.md
  - model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/
  - quality_tests/test_tiny_safety_model.py
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/current/STATUS.md
  - docs/tasks/done/MODEL-DEVICE-001_TINY_SAFETY_MODEL_V0.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - firmware changes, flashing, serial capture, hardware commands, or device deployment
  - changing shared public contracts or protocol fields
  - cloud inference, hosted AI dependencies, or training-server integration
  - training on private field samples without explicit labeling/privacy/consent gates
  - claiming production fall detection, real-world accuracy, latency, footprint, power, or release readiness
---

# Goal

Serve D4-D5: create the first local Tiny Safety Model v0 train/export loop that
can produce a small deployable artifact from synthetic integration data without
replacing deterministic safety rules.

# Acceptance

- [x] A deterministic tiny model can infer `normal`, `uncertain`,
      `needs_check`, or `possible_risk` from bounded `model_input` features.
- [x] A local training script writes JSON artifact, Markdown model card,
      SHA256 file, and JSONL synthetic eval rows under `model_artifacts/`.
- [x] A local export script writes a C header, test vectors, export report, and
      SHA256 file for a future firmware task.
- [x] Tests prove SOS/cancel stay outside model control, synthetic data is
      marked dry-run only, and no model deployment/power/accuracy claim is made.

# Evidence

- Model artifact:
  `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/tiny_safety_model.json`
- Model card:
  `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/tiny_safety_model_card.md`
- Synthetic eval rows:
  `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/tiny_safety_eval.jsonl`
- Firmware handoff header:
  `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/export/tiny_safety_model.h`
- Export report:
  `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/export/tiny_safety_model_export.json`

# Validation

- `python -m unittest quality_tests.test_tiny_safety_model -v` passed, 3 tests.
- `python -m py_compile model_lab\safety_companion\src\tiny_safety_model.py model_lab\safety_companion\training\train_tiny_safety_model.py model_lab\safety_companion\export\export_tiny_safety_model.py`
  passed.
- `python scripts/context_lint.py` passed.
- `git diff --check` passed with CRLF/LF warnings only for generated progress
  board files.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed, 496
  tests.

# Completion Notes

The generated artifact is synthetic-only and dry-run only. It reports synthetic
holdout accuracy for integration sanity, not real-world model performance. A
future firmware task must integrate the C constants, run device-side inference,
and measure latency/RAM/flash/power before any deployment claim.
