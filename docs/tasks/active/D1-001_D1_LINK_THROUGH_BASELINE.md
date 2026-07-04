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
- [x] A run-specific D1 outdoor field kit can generate operator runbook,
      checklist, notes template, and post-run evidence commands without
      touching hardware or secrets.
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
- D1 Web/API gate (2026-07-04, codex): added
  `scripts/validate_d1_web_api.py`, a read-only report gate for `/health`,
  `/api/state`, and Dashboard D1 markers. It checks location estimate/map
  surface, upload metrics, power curve, required evidence components, and
  non-claim boundaries without sending commands or touching hardware.
- D1 demo report builder (2026-07-04, codex): added
  `scripts/build_d1_demo_report.py` to compose an existing D1 Web/API gate
  report plus an optional PWR-001 measured power report into a one-page D1
  evidence report. It stays `WARN` until measured power evidence is supplied
  and does not contact hardware or claim location accuracy/battery life.
- D1 outdoor field kit (2026-07-04, codex): added
  `scripts/prepare_d1_field_kit.py` to generate a run-specific manifest,
  runbook, checklist, and operator-notes template for a multi-hour D1 outdoor
  shakedown. It reuses the guarded FW-001 hardware runner, marks flash and
  command-sending steps as explicit operator actions, sets short-run power
  analysis to the requested duration, and does not read secrets, contact
  hardware, flash firmware, send commands, deploy code, or modify GitLab.
- D1 VPS Web deploy (2026-07-04, codex): deployed the current Message Hub/Web
  to `203.0.113.10:8790` without touching GitLab. Read-only gate
  `d1-live-after-deploy-20260704` PASS confirms the live Dashboard has the
  `D1 Link Through` panel and `/api/state` exposes `d1_link`; current device
  data is stale from 2026-07-02 and has no latitude/longitude yet, so this is
  Web readiness rather than a new hardware positioning pass.
- Validation (2026-07-04, codex): D1 field-kit/report-chain focused tests
  PASS; `python scripts/context_lint.py` PASS; `python
  scripts/build_progress_board.py` PASS; `git diff --check` PASS; full
  `scripts\verify.ps1` PASS (369 tests).
- Validation (2026-07-04, codex): D1 gate/message-hub focused tests PASS;
  `python scripts/context_lint.py` PASS; `python scripts/build_progress_board.py`
  PASS; `git diff --check` PASS; full `scripts\verify.ps1` PASS (359 tests).
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
