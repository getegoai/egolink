---
id: WEB-006
title: Paginated searchable all-location history
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
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/tasks/active/WEB-004_AMAP_LIVE_LOCATION_MAP.md
  - docs/tasks/active/WEB-005_MANUAL_REFRESH_TRAJECTORY_SELECTION.md
  - server/message_hub.py
  - quality_tests/AGENTS.md
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py

allowed_paths:
  - docs/tasks/active/WEB-006_PAGINATED_LOCATION_HISTORY.md
  - server/message_hub.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py

out_of_scope:
  - firmware, hardware control, device commands, or data collection
  - Message Hub ingest protocol, authentication, retention, or existing data mutation
  - arbitrary payload/full-text search, coordinate search, route inference, or geofencing
  - storing selections, filters, coordinates, tokens, private device data, or runtime logs in Git
  - DNS, TLS, Nginx, ports, deployment, or database restoration
execution_state: acceptance_review
owner: director
reviewed_at: 2026-09-22
---

# Goal

Let an authenticated operator browse every stored location report and location
observation for the selected device through bounded pagination and safe
metadata filters. All matching records remain visible, while only trusted
WGS-84 fixes can be selected across pages and drawn chronologically alongside
the existing 24-point quick view.

# Public Contract And Privacy Boundary

- Add authenticated read-only
  `POST /api/v1/devices/{device_id}/locations/search`. Its JSON body accepts
  only a bounded page size, an opaque continuation cursor, optional inclusive
  server-received time bounds, optional exact sequence number, and fixed
  event-type/trust enums. Coordinates and arbitrary search strings are rejected.
- Results list every matching stored location report/observation in the frozen
  snapshot. Only AMap-eligible WGS-84 points already accepted by the corrected-
  firmware trust rule contain coordinates and are selectable. Raw payloads,
  tokens, Wi-Fi/cell identifiers, and unrelated messages are never returned.
- The exact `0.1.0-fw007-lte-wifi-failover` image identifier joins the existing
  corrected-parser allowlist because FW-007 inherits that parser in the same
  tested source slice. This is not a prefix/version-range relaxation and does
  not claim GNSS accuracy or product acceptance. FW-007's separate bounded
  SIM-absent Wi-Fi failover pass does not itself validate its coordinates.
- Keyset pagination is newest-first, deterministic by database message ID, and
  capped at 100 returned records, 2,000 inspected location rows, and a bounded
  8 MB stored-payload byte inspection budget per request. A single stored
  payload above 64 KiB is not loaded into application memory or echoed; its row
  remains reachable as bounded, unselectable metadata.
  The first request freezes a per-device maximum-message snapshot anchor;
  continuation cursors carry that anchor and advance past every inspected row,
  so concurrent ingest cannot duplicate or skip older results. Sparse matches
  remain traversable without an unbounded request. `exhausted=true` is the only
  end-of-history signal; a short or empty page alone is not.
- Search and pagination values travel in the authenticated JSON body, not in a
  URL. Neither the API nor the Dashboard writes coordinates, filters, cursors,
  or selected points to logs, URLs, localStorage, or the database.

# Acceptance Criteria

- [x] The history API rejects unauthenticated calls, unknown devices, unknown
      fields, invalid cursors/times/enums, coordinate-like search fields, and
      page sizes outside 1-100.
- [x] Every stored location report/observation matching the declared metadata
      filters is reachable exactly once by following `next_cursor`; ordering is
      stable across equal timestamps, and sparse matches cannot terminate
      traversal early. Old-firmware, no-fix, and observation rows expose only
      bounded safe metadata and never coordinates or an enabled checkbox.
- [x] The Chinese Dashboard keeps the existing bounded 24-point quick selector
      and adds an explicit full-history browser with time/sequence/type search,
      next/previous page controls, loading/empty/error/exhausted states, and no
      recurring refresh.
- [x] Selections survive next/previous/search navigation in page memory and are
      isolated per device. Search changes clear page navigation but do not
      silently discard already selected points; an explicit clear action does.
- [x] Selected history points and quick-view points are de-duplicated, sorted
      by trusted server time, and rendered with the existing current/last-known
      marker distinction and ten-minute trajectory-gap rule. No route or
      accuracy claim is introduced. A page may return at most 100 records, one
      AMap conversion request contains at most 40 points, and the UI explicitly
      enforces/displays both a 200-unique-history-record selection limit and a
      200-point merged map render limit.
- [x] Focused Dashboard/server tests, Python compile, full verification,
      context lint, and diff checks pass. Deployment and browser validation are
      left to a separate release step.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
python -m py_compile server\message_hub.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts/context_lint.py
git diff --check
```

# Completion Evidence

- Implementation commit: `ca2b482` (`feat(web): add paginated location
  history [D2]`). The companion coordinate-log privacy deployment is commit
  `4c4d7fe` under OPS-003.
- `python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -q`:
  PASS, 113 tests.
- `python -m py_compile server\message_hub.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 672 tests.
- `python scripts/context_lint.py`: PASS.
- `git diff --check`: PASS.
- A separately authorized release deployed the committed source to
  `https://ego.example.invalid/`. The production `message_hub.py` SHA-256 is
  `7f9ef64d3819615f2ef1cc22ed9fc49e8a6f7ea8d2abf8537748ed3c9b49a982`.
  The root-only release snapshot is
  `/var/backups/egolink/web006-ops003-20260815T111245Z`; its SQLite backup
  passed `quick_check`. The live database was not restored or modified by the
  release.
- Live service gates passed: public health and HTTPS redirect, authenticated
  and unauthenticated state behavior, authenticated history pagination and
  filters, bounded response fields, `Cache-Control: no-store`, unchanged
  `0.0.0.0:8790` compatibility listener, `NRestarts=0`, and no new application
  or Nginx warning/error entries in the release window.
- The first activation smoke used an over-broad serialized-response assertion
  and produced a false negative. The protection rollback restored only code
  and the EgoLink virtual host. After the assertion was replaced with a
  structured-field check, the final activation passed. The release therefore
  used three manual application restarts in total (first activation,
  protection rollback, and final activation); the final activation itself used
  one restart, and automatic restart count remained zero.
- Authenticated Chrome validation passed against the final deployment: the
  first two pages each showed 50 records; the trusted/selectable filter showed
  34 selectable records in the inspected snapshot; two cross-page records
  remained selected and rendered while AMap stayed `ready`; after eight
  seconds the page, filters, selection, and map state were unchanged; the
  browser console contained no application or AMap errors; and the page URL
  contained no filters, cursors, or coordinates.
- No token, coordinate, private device identifier, raw payload, or private
  browser evidence was committed. Selection remains page-memory only and is
  cleared by a hard reload.

Do not move this task to done or update `docs/current/STATUS.md` from the
builder role.
