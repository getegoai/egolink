---
id: WEB-005
title: Manual Dashboard refresh and selected trusted trajectory
status: active
priority: high
requires_hardware: false
serves_demo: D2-D5
created: 2026-08-15
last_updated: 2026-08-15

context:
  - docs/AGENTS.md
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/development/DEV_FLOW.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/tasks/active/WEB-004_AMAP_LIVE_LOCATION_MAP.md
  - server/message_hub.py
  - quality_tests/AGENTS.md
  - quality_tests/test_message_hub_dashboard.py

allowed_paths:
  - docs/tasks/active/WEB-005_MANUAL_REFRESH_TRAJECTORY_SELECTION.md
  - server/message_hub.py
  - quality_tests/test_message_hub_dashboard.py

out_of_scope:
  - firmware, hardware control, device commands, or data collection
  - Message Hub storage schema, ingest protocol, authentication, or retention changes
  - a new history API, arbitrary date-range queries, route inference, or geofencing
  - plaintext credentials, private coordinates, tokens, or runtime logs in Git
  - DNS, TLS, Nginx, ports, or database restoration
---

# Goal

Stop the Dashboard from replacing interactive DOM every three seconds. Keep one
initial load plus an explicit manual refresh, and let the operator select trusted
recent location samples whose chronological connections are rendered on the
provider map and local fallback.

# Acceptance Criteria

- [ ] No timer or recurring background refresh mutates the Dashboard. Initial
      load, token save, device selection, and an explicit `刷新数据` action may
      request state deliberately.
- [ ] Opening details, focusing a control, scrolling a list, or panning/zooming
      the map is not interrupted merely because time passes.
- [ ] The recent trusted-point panel lists the bounded 24-point window with
      checkboxes plus select-all, clear, and follow-latest controls. Selection
      remains page-local and is isolated per device.
- [ ] Selected points are sorted by trusted server timestamp, never checkbox
      click order. Zero points draw no line, one point is a sample only, and two
      or more adjacent samples may form straight segments.
- [ ] A gap longer than ten minutes, invalid/reversed time, or an unselected
      intermediate sample breaks a segment. The UI states that connections are
      straight lines between selected samples and are not an inferred route.
- [ ] The selected endpoint is labelled `所选终点`; current, stale, no-fix, and
      last-known position semantics remain separate and honest.
- [ ] Only eligible WGS-84 trusted points are selectable or sent to AMap. The
      selection is not stored in localStorage, a URL, logs, or the database.
- [ ] Focused tests, full repository verification, context lint, Python compile,
      diff checks, and an authenticated browser interaction check pass before
      deployment.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard -v
python -m py_compile server\message_hub.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check
```

# Deployment Boundary

- Take a root-only SQLite-consistent database backup plus reports, code, unit,
  environment, and hashes before deploying the committed source.
- Preserve the existing runtime environment, listener, Nginx, TLS, database,
  and report data; this task changes only Dashboard source.
- On failure, restore code and unit only. Never restore the live database for a
  UI rollback.

# Completion Evidence

- Pending implementation, validation, commit, deployment, and browser review.

