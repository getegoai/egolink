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

- [x] `/api/state` exposes a D1-ready location estimate summary from the latest
      `location_report` / `location_observation`.
- [x] Dashboard shows the latest D1 location estimate/map surface and upload
      freshness without claiming accuracy.
- [x] A no-hardware test fixture proves the Web/API path using synthetic or
      existing bounded evidence.
- [x] Operator instructions exist for the battery-powered 4G-board D1 run.
- [x] `python scripts/context_lint.py` and `powershell -ExecutionPolicy Bypass
      -File scripts\verify.ps1` pass.

# Operator Runbook

Use this only when the operator intends to run the 4G board on independent
battery power.

1. Start or confirm the Message Hub target that the firmware will upload to.
2. Confirm the 4G board is powered by battery, not by USB power, before
   counting D1 power evidence.
3. Let the board run long enough to send periodic `location_report` or
   `location_observation` uploads with GNSS/cell/IMU/power fields.
4. Open the Dashboard and check the `D1 Link Through` panel: D1 status,
   map surface, upload freshness, GNSS evidence, Cell/LTE evidence, IMU
   evidence, Power evidence, Upload Success, Location Uploads, Power Curve,
   and Power Delta must be visible.
5. Record the evidence path, board identity, firmware version or image, power
   source, start/end timestamp, and whether the map surface is coordinate,
   memory-coordinate, estimate-without-coordinate, or waiting for upload.
6. Do not record D1 as a location-accuracy pass, battery-life pass, GNSS
   acceptance, or 24h power pass unless a later task explicitly verifies that.

# Progress

- alignment (2026-07-04, codex): opened D1 as the current North Star task and
  paused non-D1 work so execution serves the current demo.
- Web/API baseline (2026-07-04, codex): `/api/state` now exposes per-device
  `d1_link`, Dashboard renders `D1 Link Through` with a map surface and upload
  freshness, and a synthetic no-hardware location-observation fixture covers
  the path.
- D1 metrics baseline (2026-07-04, codex): `d1_link` now derives
  `uplink_metrics` and `power_curve` from recent device messages, including
  raw POST success/failure counters when present, server-received location
  event count, power sample count, and voltage/SoC deltas. Dashboard exposes
  these without claiming battery life.
- Validation (2026-07-04, codex): focused message-hub tests PASS;
  `python scripts/context_lint.py` PASS; `python scripts/build_progress_board.py`
  PASS; `git diff --check` PASS; full `scripts\verify.ps1` PASS (356 tests).
- Validation (2026-07-04, codex): `python scripts/context_lint.py` PASS;
  `python -m unittest quality_tests.test_message_hub_server
  quality_tests.test_message_hub_dashboard -v` PASS; `python
  scripts/build_progress_board.py` PASS; `git diff --check` PASS;
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` PASS
  (356 tests).
- Validation: `python scripts/context_lint.py` PASS; `python -m unittest
  quality_tests.test_progress_board quality_tests.test_model_footprint_assessment_doc -v`
  PASS; `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` PASS
  (355 tests).
