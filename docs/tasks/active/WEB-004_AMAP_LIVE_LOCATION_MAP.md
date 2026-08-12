---
id: WEB-004
title: AMap live location view with runtime-only credentials
status: active
priority: high
requires_hardware: false
serves_demo: D2-D5
created: 2026-08-12
last_updated: 2026-08-12

context:
  - docs/AGENTS.md
  - docs/product/NORTH_STAR.md
  - docs/CONTEXT_INDEX.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/done/WEB-003_FOUNDER_DASHBOARD_CLARITY.md
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/AGENTS.md
  - quality_tests/test_message_hub_dashboard.py

allowed_paths:
  - .gitignore
  - docs/tasks/active/WEB-004_AMAP_LIVE_LOCATION_MAP.md
  - docs/development/VPS_MESSAGE_HUB.md
  - server/.env.example
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py

out_of_scope:
  - firmware, hardware control, device commands, or data collection
  - Message Hub storage schema, ingest protocol, authentication, or retention changes
  - plaintext map credentials, raw private coordinates, tokens, or logs in Git
  - historical coordinate mutation, accuracy claims, geofencing, or route inference
  - GitLab, firewall, ports, DNS, TLS, or database restoration
---

# Goal

Replace the Dashboard's local coordinate sketch with a direct, readable AMap
view while keeping location age/source uncertainty explicit and credentials out
of Git.

# Acceptance Criteria

- [x] The selected device's valid location and bounded trajectory render on an
      AMap canvas; WGS-84 device coordinates use AMap's documented GPS
      conversion before display.
- [x] Live fix, historical/estimated position, no-fix, stale data, and provider
      failure are visually distinct; a historical point is never labelled as
      the current location.
- [x] The browser receives the JavaScript API key but never the securityJsCode;
      the latter is appended only by a fixed same-origin server proxy.
- [x] Missing provider configuration falls back to the existing local map
      without breaking Dashboard refresh or exposing credentials.
- [x] Key name `test`, runtime variable names, deployment location, source
      restrictions, and rotation procedure are documented; no real credential
      value or credential-derived identifier is tracked.
- [x] Focused tests, full verification, context lint, diff check, and a local
      browser visual check pass.
- [x] A clean committed build is backed up and deployed to the existing VPS,
      and passes health/auth/map-marker/provider smoke checks; failure restores
      code/unit only and does not restore the live database.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
python -m py_compile server\message_hub.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check
```

# Deployment Boundary

- Configure real values only in ignored local runtime state and VPS
  `/etc/egolink-message-hub.env` (`0600`).
- Take an SQLite-consistent database backup plus reports, code, and unit
  snapshots before one deployment/restart.
- Smoke-test service state, health, auth boundary, source hash, map DOM/config,
  and upstream proxy without recording coordinates or credentials.
- On failure, restore only code/unit and restart. Do not restore the database.

# Completion Evidence

- Changed files: `.gitignore`, `server/.env.example`, `server/message_hub.py`,
  `scripts/deploy_message_hub_vps.ps1`, `docs/development/VPS_MESSAGE_HUB.md`,
  and the two focused Message Hub test modules. Commits `f19ee1d` and
  `aaed7d6` keep the main implementation and release-smoke hardening separate.
- Test result: the final HTTPS/Dashboard/server regression passed `103/103`;
  full repository verification passed `654/654`; `py_compile`, context lint, and
  diff checks passed. The live Chrome review confirmed the field-first layout,
  stable selected device, authenticated refresh, collapsed diagnostics, and
  explicit pre-correction-coordinate warning.
- Deployment result: a pre-release SQLite-consistent database backup plus
  reports/code/unit/environment snapshots passed hash and archive checks at
  `/var/backups/egolink/web004-20260812-211402`. The Message Hub was restarted
  with the committed map implementation. Bounded corrective deployments are
  recorded by `b7e721c`, `2e91387`, `40d9556`, and `15f4dd8`, including the
  observed SDK-init path and JSONP response-type fixes. Final source hash
  matched the local committed file; service state was active/running with zero
  restarts or error-journal entries; health was HTTP 200, unauthenticated state
  was 401, authenticated state was 200, and the signed same-origin coordinate
  proxy returned provider `OK` with `no-store` and `nosniff`.
- Remaining risks: the current corrected firmware has not produced a new
  verified GNSS fix. The deployed view therefore hides all pre-correction and
  lineage-less coordinates instead of drawing a misleading marker; the first
  real AMap point and bounded trajectory still require a new FW-006 fix. The
  human-facing Dashboard is now available at `https://ego.example.invalid/`; the
  public port 8790 remains an HTTP firmware-compatibility endpoint, so this is
  still not a production security claim. AMap is a third-party script and
  receives only eligible coordinates used for the provider view; production
  still needs ingress migration/origin isolation, consent enforcement, and
  provider-console quota/origin restrictions.

# Builder Prompt

```text
Read docs/tasks/active/WEB-004_AMAP_LIVE_LOCATION_MAP.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md,
quality_tests/AGENTS.md, this packet, and its context entries. Implement the
smallest secure AMap-backed selected-device map; obey allowed_paths and
out_of_scope. Never place real credentials or private coordinates in Git or
logs. Run all declared validation commands and return changed files, validation
results, deployment evidence, and remaining risks. Do not update STATUS or move
the packet to done.
```
