---
id: MAP-003
title: Browser-local D2 reference overlay
status: done
priority: high
requires_hardware: false
serves_demo: D2
created: 2026-07-11
completed: 2026-07-11

context:
  - docs/product/NORTH_STAR.md
  - docs/tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md
  - docs/tasks/done/MAP-001_D2_D5_MAP_EVIDENCE_VIEW.md

allowed_paths:
  - server/
  - quality_tests/
  - docs/current/
  - docs/tasks/
  - docs/generated/
---

# MAP-003 Local Reference Overlay

This task serves D2; the lowest unfinished mainline Demo is D2. It directly
removes the map-review gap while real FIELD-003 data collection is unavailable.

## Acceptance

- [x] Load a bounded FIELD-003 JSON manifest from the Dashboard without a
      server upload endpoint.
- [x] Overlay valid reference points with the server trajectory in no-key mode.
- [x] Reject files over 256 KiB, more than 16 points, invalid coordinates, and
      active-device mismatches.
- [x] Persist only a compact browser-local review object and allow explicit
      overlay clearing without deleting capture-page data.
- [x] Keep provider availability non-blocking and preserve no-accuracy claims.
- [x] Focused tests, context lint, and full verification pass.

## Evidence

- Implementation: `server/message_hub.py`
- Tests: `quality_tests/test_message_hub_dashboard.py`
- Focused validation: 73 Dashboard and Message Hub tests PASS
- Full validation: `scripts/context_lint.py` PASS and `scripts/verify.ps1`
  PASS with 552 tests
- Local HTTP: Dashboard and `/health` served on `127.0.0.1:8892`
- JavaScript checks: inline script compiled; behavior check over two fixture
  reference points passed and rejected blank coordinates
- VPS deployment: service active; live HTML markers and inline JavaScript
  compile check PASS; no reference-point upload route is present
- Visual boundary: in-app browser unavailable; no screenshot or responsive
  visual-overlap claim
- Hardware result: not required; no serial, flash, command, or device action
