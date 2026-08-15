---
id: OPS-003
title: Suppress AMap coordinate-convert access logs
status: active
priority: high
requires_hardware: false
serves_demo: D2-D5
created: 2026-08-15
last_updated: 2026-08-15

context:
  - docs/AGENTS.md
  - docs/product/NORTH_STAR.md
  - docs/CONTEXT_INDEX.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/operations/VPS_RUNBOOK.md
  - docs/tasks/active/OPS-002_EGO_DOMAIN_HTTPS.md
  - scripts/ops/nginx/ego.example.invalid.conf
  - quality_tests/AGENTS.md
  - quality_tests/test_vps_https_config.py

allowed_paths:
  - docs/tasks/active/OPS-003_AMAP_COORDINATE_LOG_PRIVACY.md
  - docs/operations/VPS_RUNBOOK.md
  - scripts/ops/nginx/ego.example.invalid.conf
  - quality_tests/test_vps_https_config.py

out_of_scope:
  - Message Hub, Web, firmware, protocol, storage, database, or credential changes
  - reading, copying, reporting, or deleting historical access logs or private coordinates
  - changing TLS, certificates, proxy headers, cookies, upstream routing, or unrelated virtual hosts
  - disabling access logs for any route other than the exact AMap coordinate-convert path
  - VPS deployment or Nginx reload
---

# Goal

Prevent private coordinate query strings from entering Nginx access logs while
preserving the exact AMap coordinate-conversion request and all existing HTTPS,
redirect, proxy, cookie, and header behavior.

# Acceptance Criteria

- [x] Both the HTTP redirect and HTTPS proxy virtual hosts disable access logs
      only for exact `/_AMapService/v3/assistant/coordinate/convert` requests;
      query strings do not change exact-location matching.
- [x] The HTTPS exact location sends the original URI and query string to the
      same loopback upstream with the same proxy version, headers, upgrade
      behavior, and timeouts as the existing catch-all proxy.
- [x] The HTTP exact location preserves the existing HTTPS redirect target and
      status, and all other routes continue to inherit normal access logging.
- [x] Focused tests protect exact scoping and unchanged proxy/TLS/security
      behavior; tracked configuration passes an available `nginx -t` syntax
      check without deployment.
- [x] Context lint and diff checks pass; no logs, coordinates, credentials, or
      private evidence are read or committed.

# Validation Commands

```powershell
python -m unittest quality_tests.test_vps_https_config -v
python scripts/context_lint.py
git diff --check
```

Before deployment, stage the tracked virtual host outside `/etc/nginx`, include
it from a temporary minimal Nginx root configuration, and run `nginx -t` against
that temporary configuration. Do not print rendered request logs or runtime
environment values.

# Completion Evidence

- Changed files: this packet, the final EgoLink Nginx virtual-host template,
  the focused HTTPS configuration tests, and the VPS operations runbook.
- Implementation commit: `4c4d7fe` (`fix(ops): suppress AMap coordinate access
  logs [D2]`).
- Test result: focused HTTPS configuration tests passed `7/7`; full repository
  verification passed `672/672`; context lint and scoped diff checks passed.
- Nginx syntax result: the tracked virtual host was included from a temporary
  root configuration supplied to the VPS's installed Nginx; `nginx -t`
  reported syntax OK and a successful configuration test. Temporary files
  were removed afterward.
- A separately authorized release installed the exact virtual-host change and
  reloaded Nginx once after the new Message Hub was healthy. The production
  virtual-host SHA-256 is
  `68a961b46fd189c53d20e5538256080090889de79b6d69224d3f3724e28924b5`;
  the root-only rollback snapshot is
  `/var/backups/egolink/web006-ops003-20260815T111245Z`.
- The rendered Nginx diff added only the two exact coordinate-convert blocks;
  proxy/redirect behavior, headers, upstream, timeouts, TLS, cookies, and all
  other virtual hosts remained unchanged. Final `nginx -t`, public HTTPS and
  redirect gates, cookie forwarding, and a no-coordinate provider probe
  passed. Nginx and the application reported no new warning/error entries, and
  automatic application restart count remained zero.
- No historical access log was read, copied, reported, or deleted during
  validation. Remaining risks: this exact rule does not cover historical logs,
  an upstream CDN/load balancer, application/provider logs, alternate or
  trailing-slash paths, or coordinates deliberately sent over plaintext HTTP
  before the redirect; normal Dashboard traffic uses HTTPS. Disabling the
  route's access log also removes its per-request Nginx status and volume
  diagnostics.
