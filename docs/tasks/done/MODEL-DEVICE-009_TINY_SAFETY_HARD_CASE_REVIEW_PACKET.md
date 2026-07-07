---
id: MODEL-DEVICE-009
title: Tiny Safety hard-case review packet
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
  - docs/tasks/done/MODEL-DEVICE-008_TINY_SAFETY_SYNTHETIC_STRESS.md

allowed_paths:
  - model_lab/safety_companion/evaluation/
  - model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/label_review/
  - quality_tests/test_tiny_safety_hard_case_review.py
  - docs/current/STATUS.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/tasks/active/MODEL-DEVICE-009_TINY_SAFETY_HARD_CASE_REVIEW_PACKET.md
  - docs/tasks/done/MODEL-DEVICE-009_TINY_SAFETY_HARD_CASE_REVIEW_PACKET.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - changing model behavior, thresholds, labels, schemas, contracts, or artifacts used for inference
  - training on synthetic, private, field, or candidate-store samples
  - writing reviewed labels, training-allowed records, or dataset manifests
  - claiming real-world accuracy, fall detection quality, runtime RAM, latency, power, or release readiness
  - flashing firmware, opening serial ports, contacting hardware, or sending device commands
  - mapping model output to real SMS, calls, dispatch, or external escalation
---

# Goal

Serve D4-D5 by turning the MODEL-DEVICE-008 synthetic stress hard cases into a
bounded human-review packet that can feed future labeling work without being
mistaken for a reviewed training dataset.

# Acceptance Criteria

- [x] A no-hardware exporter consumes the synthetic stress report and writes a
      deterministic review manifest plus JSONL review records.
- [x] Each review record preserves source lineage, model prediction, synthetic
      oracle label, priority reasons, bounded synthetic features, and an empty
      human-review slot.
- [x] The manifest states that records are synthetic-only, unreviewed,
      training-disallowed, and not real-world accuracy evidence.
- [x] Focused tests cover deterministic export, non-claim boundaries, and CLI
      file generation.

# Validation Commands

```powershell
python -m unittest quality_tests.test_tiny_safety_hard_case_review -v
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
  - `model_lab/safety_companion/evaluation/export_tiny_safety_hard_case_review.py`
  - `model_lab/safety_companion/evaluation/README.md`
  - `quality_tests/test_tiny_safety_hard_case_review.py`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/label_review/tiny_safety_hard_case_review_manifest.json`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/label_review/tiny_safety_hard_case_review_records.jsonl`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/label_review/tiny_safety_hard_case_review.md`
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/label_review/sha256.txt`
  - `docs/current/STATUS.md`
  - `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
- Review packet:
  - `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/label_review/tiny_safety_hard_case_review.md`
  - Review set: `MODEL-DEVICE-009-tiny-safety-hardcase-review-20260707`.
  - Records exported: `24`.
  - Expected synthetic labels: `uncertain=24`.
  - Predicted labels: `needs_check=20`, `normal=4`.
  - Priority reasons: `low_confidence=24`, `low_margin=24`,
    `synthetic_oracle_disagreement=24`.
- Test result:
  - `python -m unittest quality_tests.test_tiny_safety_hard_case_review -v`:
    PASS, 3 tests.
  - `python -m unittest quality_tests.test_tiny_safety_hard_case_review quality_tests.test_tiny_safety_synthetic_stress -v`:
    PASS, 6 tests.
  - `python scripts/context_lint.py`: PASS.
  - `git diff --check`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 523
    tests.
- Hardware result: not contacted; no flash, serial command, runtime
  measurement, power measurement, VPS command, field/private data read, model
  training, reviewed labels, or model behavior change was performed.
- Remaining risks:
  - Records are synthetic review fixtures, not reviewed labels.
  - Synthetic oracle labels are triage hints, not training targets.
  - A future real-data labeling UI/store still needs privacy, consent,
    reviewer identity, split policy, and training-export gates.
  - Runtime RAM, latency, power, and release readiness remain unmeasured.
