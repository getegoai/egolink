---
id: D2-002
title: D2 reference-point field-run automation
status: done
priority: high
requires_hardware: false
serves_demo: D2
created: 2026-07-11
completed: 2026-07-11

context:
  - docs/product/NORTH_STAR.md
  - docs/tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md
  - docs/tasks/active/FIELD-003_OUTDOOR_GNSS_ACCEPTANCE.md
  - docs/hardware/FIELD_GNSS_ACCEPTANCE_PROTOCOL.md

allowed_paths:
  - scripts/
  - quality_tests/
  - docs/development/
  - docs/hardware/
  - docs/current/
  - docs/tasks/
  - docs/generated/
  - reports/
---

# D2-002 Reference Field-Run Automation

This task serves D2; D2 is the lowest unfinished mainline Demo. It directly
removes manual field-manifest and post-run export assembly from FIELD-003.

## Acceptance

- [x] Generate a strict three-environment, five-cold/five-warm manifest.
- [x] Generate a concise runbook and checklist without contacting hardware,
      the VPS, serial ports, or token values.
- [x] Fetch a named Message Hub test-run export read-only during post-run.
- [x] Preserve the raw export only under bounded `reports/gnss/` evidence.
- [x] Continue through existing D2 baseline and D5 review intake in one CLI.
- [x] Reject ambiguous local/remote input combinations and keep tokens out of
      reports and command output.
- [x] Focused tests, context lint, and full repository verification pass.

## Evidence

- Implementation: `scripts/prepare_d2_field_kit.py`,
  `scripts/run_location_d2_d5_pipeline.py`
- Tests: `quality_tests/test_d2_field_kit.py`,
  `quality_tests/test_location_d2_d5_pipeline.py`
- Validation: 10 focused D2/FIELD tests PASS; `context_lint` PASS; full
  `scripts/verify.ps1` PASS with 545 tests
- Operator artifact: `reports/d2_field/D2-001-reference-20260711-ready/`
- VPS smoke: existing firmware test-run ID registered as export metadata;
  read-only export returned 39,745 messages and 8,548 raw frames
- Hardware result: not run; FIELD-003 real measurements remain pending
- Non-claim: this is field automation, not GNSS accuracy or product acceptance
