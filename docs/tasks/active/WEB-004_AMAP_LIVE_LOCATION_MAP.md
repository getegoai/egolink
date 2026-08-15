---
id: WEB-004
title: AMap live location view with runtime-only credentials
status: active
priority: high
requires_hardware: false
serves_demo: D2-D5
created: 2026-08-12
last_updated: 2026-08-15

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
- [x] A post-`f46b052` authenticated browser session visibly renders provider
      tiles and the correct current/last-known marker semantics across at least
      two refresh cycles without a new console error.

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
- Follow-up repair: commit `f46b052` corrected the deployed proxy response for
  AMap coordinate-conversion JSONP. The provider returned executable
  `callback(...)` content, but the proxy had labelled it `application/json`
  while also sending `X-Content-Type-Options: nosniff`; browsers therefore
  rejected the conversion script and repeatedly exposed the local fallback.
  The repair upgrades only canonical AMap JSONP responses with one bounded,
  syntactically valid callback and a safe upstream media type to
  `application/javascript`. JSON without a callback remains JSON, HTML and
  malformed callbacks fail closed, and `no-store`, `nosniff`, signed proxy
  cookies, fixed upstream hosts, and exact path allowlists remain unchanged.
  It also makes half-initialized maps retryable and de-duplicates identical
  conversion and overlay work across the three-second Dashboard refresh.
- Follow-up validation: Dashboard/server tests passed `98/98`; full repository
  verification passed `654/654`; `py_compile`, context lint, and diff checks
  passed. The committed source was backed up and deployed once from
  `/var/backups/egolink/web004-mapfix-20260814T092722Z`; local and deployed
  `server/message_hub.py` both had SHA-256
  `599c504a4c0c5957858e80edf650315d868de7f7995efde4b5eecc0cd88d38a1`.
  The root-only snapshot passed its SHA-256 manifest check and its SQLite copy
  passed read-only `PRAGMA quick_check=ok`.
  The service remained active/running with zero restarts, health returned 200,
  and the state API retained its 401/200 unauthenticated/authenticated boundary.
  A 2026-08-14 17:43 CST read-only smoke replayed actual post-deploy SDK
  requests: five initialization requests and one coordinate-conversion request
  returned HTTP 200, `application/javascript`, `nosniff`, `no-store`, valid
  callback JSONP, and provider success (`status=1`, `infocode=10000`). Message
  Hub and Nginx remained active, `nginx -t` passed, and no application- or
  Nginx-related warning/error appeared in the bounded 15-minute review.
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
- Field evidence after the original deployment: corrected firmware
  `0.1.0-fw005-gnss-correctness` produced 120 eligible fixed reports during a
  bounded 2026-08-14 field export. The map may therefore render a bounded
  verified trajectory (at most 24 points). When the newest report is `no_fix`,
  the most recent trusted point is explicitly `Predicted / Last known`, never a
  current GNSS fix. No private coordinate value is copied into this packet.
- Chinese trajectory release: commit `22a174b` reorganized the first screen as
  `位置与历史轨迹`, made Chinese the primary visible language, and added a
  bounded recent-history view. The provider and local fallback both draw at
  most 24 trusted WGS-84 fixes, break lines across gaps longer than ten
  minutes, and distinguish the start, intermediate history, current fix,
  stale fix, and last-known endpoint. A newer `no_fix` event cannot evict the
  older trusted window or relabel its endpoint as current. The summary shows
  trusted-point count, drawable segment count, start/end times, duration,
  source, and the eight most recent point timestamps without exposing raw
  coordinates in this packet.
- Chinese trajectory validation: the final focused Dashboard/server suite
  passed `101/101`; full repository verification passed `657/657`; the
  relevant trajectory/no-fix fixtures passed `54/54`; `py_compile`, context
  lint, and diff checks passed. Desktop and 390 x 844 authenticated Chrome
  reviews visibly showed AMap tiles, `24 / 最多 24` trusted points, one
  drawable segment, start/end timing, and `最后可信位置` for the stale predicted
  state. The map remained visible after a seven-second wait covering two
  three-second refresh cycles, and final console filtering returned no
  `TypeError` or AMap warning/error.
- Chinese trajectory deployment: the root-only pre-release snapshot is
  `/var/backups/egolink/web004-zh-trajectory-20260815T035840Z`. Its manifest,
  code/reports archives, SQLite backup, and read-only `quick_check` passed.
  Deployed `server/message_hub.py` SHA-256 is
  `67d642022c05bf141cf700c938102961c1bcb0ea99dc879073f83c42c7ab959c`,
  matching commit `22a174b`. Message Hub and Nginx are active with zero
  automatic restarts; HTTPS and the compatibility endpoint return health 200,
  the state API retains its 401/200 authentication boundary, AMap init and
  conversion return provider success, the environment file is unchanged, and
  the post-restart warning window is empty. The standard deployment briefly
  rewrote the unit to loopback-only; the snapshot unit was restored without
  changing the new code, database, reports, environment, Nginx, or TLS. This
  required two bounded manual service starts and left the compatibility
  listener at its prior `0.0.0.0:8790` setting.
- Remaining risks: this is deliberately a recent trusted-point window, not a
  complete daily or multi-day route service. Time-range history needs a
  separate bounded, paginated API task. The public port 8790 remains an HTTP
  firmware-compatibility endpoint, so this is still not a production security
  claim. AMap is a third-party script and receives only eligible coordinates
  used for the provider view; production still needs ingress migration/origin
  isolation, consent enforcement, and provider-console quota/origin
  restrictions.

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
