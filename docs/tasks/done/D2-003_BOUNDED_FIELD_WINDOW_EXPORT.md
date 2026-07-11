---
id: D2-003
title: Bounded device and time-window field export
status: done
priority: high
requires_hardware: false
serves_demo: D2
created: 2026-07-11
completed: 2026-07-11

context:
  - docs/product/NORTH_STAR.md
  - docs/tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md
  - docs/tasks/active/D5-001_LOCATION_DATA_FLYWHEEL_MAINLINE.md
  - docs/development/FIELD_TEST.md
  - docs/development/VPS_MESSAGE_HUB.md

allowed_paths:
  - server/
  - scripts/
  - quality_tests/
  - docs/current/
  - docs/development/
  - docs/tasks/
  - docs/generated/
---

# D2-003 Bounded Field Window Export

This task serves D2; the current lowest unfinished mainline Demo is D2. It is
a direct D2 blocker because the fixed firmware test run had accumulated tens
of thousands of historical records and did not isolate one reference outing.

## Acceptance

- [x] Export one authenticated device over an explicit ISO-8601 server receive
      time window without writing server or device state.
- [x] Enforce a 48-hour maximum window, bounded per-collection row limit, and
      explicit truncation/complete metadata.
- [x] Keep raw-frame bytes redacted in the export response.
- [x] Let the D2 -> D5 pipeline read `started_at` and `ended_at` from the field
      manifest and reject device mismatches, placeholders, and truncation.
- [x] Keep the legacy named test-run export available for existing tooling.
- [x] Generate the new device-window post-run command in the D2 field kit.
- [x] Focused tests, context lint, and full repository verification pass.

## Evidence

- Implementation: `server/message_hub.py`,
  `scripts/run_location_d2_d5_pipeline.py`,
  `scripts/prepare_d2_field_kit.py`
- Tests: `quality_tests/test_message_hub_server.py`,
  `quality_tests/test_location_d2_d5_pipeline.py`,
  `quality_tests/test_d2_field_kit.py`
- Focused validation: 45 tests PASS
- Full validation: `scripts/context_lint.py` PASS and
  `scripts/verify.ps1` PASS with 551 tests
- Hardware result: not required; no serial, flash, command, or device action
- Privacy boundary: exact field coordinates remain only in authenticated,
  ignored runtime evidence and are not copied into static Dashboard summaries
- Remaining field dependency: first real FIELD-003 reference-point manifest
  and matching bounded export still need founder collection and D2 review
