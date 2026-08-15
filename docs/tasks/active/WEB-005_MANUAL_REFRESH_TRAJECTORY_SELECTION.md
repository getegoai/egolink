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

- [x] No timer or recurring background refresh mutates the Dashboard. Initial
      load, token save, device selection, and an explicit `刷新数据` action may
      request state deliberately.
- [x] Opening details, focusing a control, scrolling a list, or panning/zooming
      the map is not interrupted merely because time passes.
- [x] The recent trusted-point panel lists the bounded 24-point window with
      checkboxes plus select-all, clear, and follow-latest controls. Selection
      remains page-local and is isolated per device.
- [x] Selected points are sorted by trusted server timestamp, never checkbox
      click order. Zero points draw no line, one point is a sample only, and two
      or more adjacent samples may form straight segments.
- [x] A gap longer than ten minutes, invalid/reversed time, or an unselected
      intermediate sample breaks a segment. The UI states that connections are
      straight lines between selected samples and are not an inferred route.
- [x] The selected endpoint is labelled `所选终点`; current, stale, no-fix, and
      last-known position semantics remain separate and honest.
- [x] Only eligible WGS-84 trusted points are selectable or sent to AMap. The
      selection is not stored in localStorage, a URL, logs, or the database.
- [x] Focused tests, full repository verification, context lint, Python compile,
      and diff checks pass before deployment; an authenticated browser
      interaction check passes immediately after deployment.

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

- Implementation commit: `c2ac2a7` (`feat(web): add manual trajectory selection
  [D2]`), limited to `server/message_hub.py` and the focused Dashboard test.
- `python -m unittest quality_tests.test_message_hub_dashboard -v`: 51/51 PASS.
  Dashboard plus Message Hub server focused regression: 102/102 PASS.
- `python -m py_compile server/message_hub.py`: PASS. Independent source review
  found no remaining trajectory, current/last-known, selection-race, or privacy
  blocker.
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: 659/659 PASS.
  `python scripts/context_lint.py` and `git diff --check`: PASS.
- Deployment completed on 2026-08-15 from committed source `c2ac2a7`. The
  production source SHA-256 is
  `42e7f71432549eba371d434712a97408b1ec46a5e377d849e3463d7f10855f95`.
  The root-only rollback snapshot is
  `/var/backups/egolink/web005-retry-20260815T090121Z`; its manifest, code and
  report archives, SQLite-consistent backup, and `quick_check` passed.
- The final deployment health gate reached ready in 353 ms. Message Hub and
  Nginx were active, `NRestarts=0`, the compatibility listener remained on
  `0.0.0.0:8790`, public health returned 200, unauthenticated state returned
  401, authenticated state returned 200, and the post-start journal window had
  no application warning or error. Runtime environment, Nginx, unit content,
  live database, and reports were preserved.
- An authenticated Chrome check verified the Chinese Dashboard, visible AMap
  base map, successful WGS-84 to GCJ-02 conversion, and the 24-point trusted
  selection. More than seven seconds across two former refresh intervals did
  not replace the DOM, close an open detail, change the selection, or redraw
  the map. The explicit refresh action updated state and re-enabled itself.
- Browser interaction covered zero selected points (no trajectory but the
  independent last-known marker remained), one point (sample only), all 24
  points, and removal of a middle point (two visible segments). Switching to a
  second device and back restored the first device's manual selection; a hard
  reload reset it to follow-latest, confirming page-memory-only storage. No
  AMap `TypeError`, provider, proxy, or application console error appeared;
  unrelated extension message-channel errors were excluded.
- Four earlier deploy attempts each performed a deploy/rollback pair because
  the release harness used an unreachable VPS hairpin probe, checked the
  nonexistent `health.status` field instead of `health.ok`, or required an
  unavailable `sqlite3` CLI. The final corrected deployment added one start,
  for nine manual starts in total; automatic restart count remained zero. Each
  rollback restored code and unit only. The live database was never restored.
