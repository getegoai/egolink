---
id: D1-001
title: D1 link-through baseline
status: active
priority: high
requires_hardware: true
serves_demo: D1
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md

allowed_paths:
  - server/
  - pc_simulator/
  - scripts/
  - docs/current/
  - docs/tasks/
  - docs/generated/
  - quality_tests/
---

# Goal

Serve D1: make the 4G-board chain visible end to end: battery-powered board
collects GNSS/cell/IMU/power, uploads by LTE, server gives a location estimate,
and the Dashboard shows it.

# Acceptance

- [ ] `/api/state` exposes a D1-ready location estimate summary from the latest
      `location_report` / `location_observation`.
- [ ] Dashboard shows the latest D1 location estimate/map surface and upload
      freshness without claiming accuracy.
- [ ] A no-hardware test fixture proves the Web/API path using synthetic or
      existing bounded evidence.
- [ ] Operator instructions exist for the battery-powered 4G-board D1 run.
- [ ] `python scripts/context_lint.py` and `powershell -ExecutionPolicy Bypass
      -File scripts\verify.ps1` pass.

# Progress

- alignment (2026-07-04, codex): opened D1 as the current North Star task and
  paused non-D1 work so execution serves the current demo.
- Validation: `python scripts/context_lint.py` PASS; `python -m unittest
  quality_tests.test_progress_board quality_tests.test_model_footprint_assessment_doc -v`
  PASS; `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` PASS
  (355 tests).
