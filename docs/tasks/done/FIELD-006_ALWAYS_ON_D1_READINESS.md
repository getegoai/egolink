---
id: FIELD-006
title: Always-on D1 field readiness
status: done
priority: high
requires_hardware: false
serves_demo: D1
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DEV_FLOW.md
  - docs/current/ACTIVE_BUILD.md
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/tasks/done/DATA-004_DATA_FLYWHEEL_CONTROL_PLANE.md

allowed_paths:
  - server/message_hub.py
  - quality_tests/test_message_hub_dashboard.py
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/tasks/done/FIELD-006_ALWAYS_ON_D1_READINESS.md
  - docs/current/STATUS.md
  - docs/generated/

out_of_scope:
  - changing firmware, protocol ingest, or hardware configuration
  - sending Message Hub commands or 4G-board serial commands
  - changing model behavior or training pipelines
  - claiming GNSS accuracy, battery life, calling/SMS, or product readiness
---

# Goal

Serve D1: make the VPS Message Hub continuously usable as the normal field
preflight, so the founder can open the Web Dashboard and see whether fresh D1
periodic data is enough to leave for a field run.

# Acceptance Criteria

- [x] `/api/state` includes a bounded `d1_link.field_readiness` summary.
- [x] The Web Dashboard shows a first-glance `Field Ready` state with reason,
      freshness thresholds, and operator action.
- [x] FIELD-004 says the normal preflight is checking the always-on Web
      Dashboard; companion scripts are for recording/debug/post-run evidence.
- [x] Focused tests and repository validation pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard -v
python scripts/context_lint.py
python -m py_compile server\message_hub.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `server/message_hub.py`,
  `quality_tests/test_message_hub_dashboard.py`,
  `docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md`,
  `docs/current/STATUS.md`, generated progress-board files, and this packet.
- Validation: focused dashboard tests passed (13 tests); `python -m py_compile
  server\message_hub.py` passed; `python scripts/context_lint.py` passed;
  `git diff --check` passed; full `scripts\verify.ps1` passed (401 tests).
- Deployment: `scripts/deploy_message_hub_vps.ps1 -Public
  -IncludeFieldReportSummaries -IncludeDataFlywheelSummaries` deployed to
  `203.0.113.10:8790`, restarted `egolink-message-hub.service`, and did not
  modify GitLab. The service is systemd `enabled` and active.
- Smoke evidence: `/health` returned `ok=true`; unauthenticated `/api/state`
  returned `401`; Dashboard HTML contained `Field Ready`,
  `d1FieldReadyBadge`, `field_readiness`, `Ready Reason`, and `D1 Link
  Through`; authenticated `/api/state` showed
  `ego-link-r1-connectivity-001` with `field_readiness.state=ready`,
  `reason=fresh_periodic_upload`, `freshness_s=16`,
  `operator_action=go_test`, and latest upload at
  `2026-07-04T13:18:41.428617+00:00`.
- Remaining risks: readiness is only a live-link freshness preflight. The
  2-3 hour outdoor run and long power baseline are still operator/hardware
  work; no GNSS accuracy, battery life, calling/SMS, model readiness, or product
  readiness is claimed.
