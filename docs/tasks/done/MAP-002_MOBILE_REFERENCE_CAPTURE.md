---
id: MAP-002
title: Mobile local-only D2 reference capture
status: done
priority: high
requires_hardware: false
serves_demo: D2
created: 2026-07-11
completed: 2026-07-11

context:
  - docs/product/NORTH_STAR.md
  - docs/tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md
  - docs/tasks/active/MAP-001_D2_D5_MAP_EVIDENCE_VIEW.md
  - docs/hardware/FIELD_GNSS_ACCEPTANCE_PROTOCOL.md

allowed_paths:
  - server/
  - scripts/
  - quality_tests/
  - docs/current/
  - docs/development/
  - docs/hardware/
  - docs/tasks/
  - docs/generated/
---

# MAP-002 Mobile Reference Capture

This task serves D2; D2 is the lowest unfinished mainline Demo. It removes
phone-side paper/JSON timestamp work from the pending reference-point run.

## Acceptance

- [x] Dashboard links to a responsive `/d2-reference-capture` page.
- [x] Page records run metadata, three reference environments, cold/warm
      attempt windows, and strict 5+5 progress.
- [x] Page exports the existing FIELD-003 manifest shape.
- [x] Coordinates remain in browser `localStorage`; no server write API,
      device command, serial action, or firmware action exists.
- [x] Browser single-fix reference is labelled partial and rejected by the
      strict FIELD-003 analyzer.
- [x] Focused server/Dashboard/GNSS tests and full verification pass.

## Evidence

- Implementation: `server/message_hub.py`,
  `scripts/analyze_gnss_acceptance.py`, `scripts/prepare_d2_field_kit.py`
- Tests: `quality_tests/test_message_hub_dashboard.py`,
  `quality_tests/test_message_hub_server.py`,
  `quality_tests/test_gnss_acceptance_analysis.py`
- Local HTTP smoke: `http://127.0.0.1:8891/d2-reference-capture` returned 200;
  rendered JavaScript parsed successfully
- Validation: 77 focused Dashboard/server/GNSS/field-kit tests PASS;
  `context_lint` PASS; full `scripts/verify.ps1` PASS with 548 tests
- Browser visual result: not run because no in-app browser instance was
  available; no screenshot or visual-overlap claim is made
- VPS deployment: PASS after verified ED25519 key authentication and a fix for
  Windows CRLF in the remote Bash script. Message Hub health, Dashboard link,
  route HTTP 200, and live JavaScript syntax checks pass; existing GitLab was
  untouched.
- Post-deploy observer: Message Hub and history are available; field readiness
  is `not_ready` because the device's periodic upload is stale, not because of
  the deployment.
- Hardware result: not applicable
