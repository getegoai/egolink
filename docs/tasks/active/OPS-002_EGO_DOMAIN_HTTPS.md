---
id: OPS-002
title: Official ego.example.invalid HTTPS entry and always-visible AMap canvas
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
  - docs/operations/VPS_RUNBOOK.md
  - docs/architecture/adr/ADR-0001-usb-free-vps-message-hub.md
  - docs/tasks/active/WEB-004_AMAP_LIVE_LOCATION_MAP.md
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/AGENTS.md
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py

allowed_paths:
  - docs/tasks/active/OPS-002_EGO_DOMAIN_HTTPS.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/operations/VPS_RUNBOOK.md
  - scripts/ops/nginx/ego.example.invalid.bootstrap.conf
  - scripts/ops/nginx/ego.example.invalid.conf
  - scripts/ops/certbot/10-egolink-nginx-reload.sh
  - scripts/deploy_message_hub_vps.ps1
  - server/message_hub.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_vps_https_config.py

out_of_scope:
  - firmware, hardware control, device commands, or data collection
  - Message Hub protocol, storage schema, historical coordinates, or database restoration
  - credentials, private coordinates, certificate private keys, tokens, or VPS logs in Git
  - changes to GitLab, unrelated virtual hosts, SSH policy, or other VPS services
  - closing public port 8790 or migrating the current firmware uplink endpoint
---

# Goal

Make `https://ego.example.invalid/` the official human-facing Dashboard entry,
terminate TLS in Nginx, and show the AMap base canvas even while the device has
no new trusted GNSS fix, without drawing an old or unverified marker.

# Acceptance Criteria

- [ ] Public DNS for `ego.example.invalid` resolves to the intended VPS without a
      conflicting address; ports 80 and 443 reach the existing Nginx instance.
- [ ] A narrowly scoped Nginx virtual host redirects HTTP to HTTPS and proxies
      HTTPS to `127.0.0.1:8790`, preserving host, client-address, scheme, and
      upgrade headers without modifying unrelated virtual hosts.
- [ ] A publicly trusted certificate for exactly `ego.example.invalid` is installed;
      renewal scheduling, the tracked deploy hook, and a renewal dry run are
      verified.
- [ ] The Dashboard's AMap cookie is HTTPS-only, and the AMap base canvas loads
      when configured even if no verified point exists; that state contains no
      location marker and retains the explicit no-fix/pre-correction warning.
- [ ] HTTP redirect, TLS hostname/expiry, `/health`, unauthenticated/authenticated
      API boundaries, AMap proxy, service state, and Nginx error log smoke checks
      pass at the domain.
- [ ] An authenticated browser review at `https://ego.example.invalid/` visibly
      confirms the provider canvas and honest no-location state.
- [ ] Nginx/app snapshots and an exact rollback path exist before deployment;
      failure does not restore or mutate the live SQLite database.
- [ ] Focused tests, full verification, context lint, and diff checks pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_vps_https_config quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
python -m py_compile server\message_hub.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check
```

# Deployment And Rollback Boundary

- Snapshot the current Nginx rendered configuration, target virtual-host file,
  Message Hub source/unit/environment metadata, and service state before change.
- Install the HTTP-only bootstrap virtual host first, validate with `nginx -t`,
  then request the certificate through its bounded ACME webroot.
- Replace only the EgoLink virtual host with the tracked HTTPS configuration,
  validate again, and reload Nginx. Do not restart GitLab or restore the live DB.
- If any post-change gate fails, restore (or remove, if newly created) only the
  target virtual-host file and any changed Message Hub source/unit snapshot;
  validate and reload Nginx. Keep the issued certificate for later reuse.

# Completion Evidence

- Changed files:
- Validation result:
- Deployment result:
- Browser result:
- Snapshot/rollback path:
- Remaining risks:
