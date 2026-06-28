---
id: WEB-001
title: Message Hub Dashboard Baseline
status: completed
priority: high
requires_hardware: false
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/FIELD_TEST.md
  - docs/current/ROADMAP_EGOLINK_P0.md

allowed_paths:
  - docs/current/
  - docs/tasks/
  - quality_tests/
  - server/

out_of_scope:
  - firmware behavior changes
  - pc_simulator behavior changes
  - protocol schema changes
  - VPS deployment
  - hardware validation
---

# Problem

The initial message-hub page was only a thin engineering view. R0/R1 field work
needs the Web surface to show online/stale status, GNSS summary, command state,
and last error without relying on serial logs.

# Expected Result

The Message Hub dashboard exposes a more useful field-observation baseline and
the state API includes recent commands.

# Acceptance Criteria

- [x] Dashboard shows device online/stale/offline state.
- [x] Dashboard shows latest GNSS/position summary when available.
- [x] Dashboard shows command status.
- [x] Dashboard shows last error summary.
- [x] `/api/state` includes recent commands.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Board: not applicable.
- Firmware commit or image: not applicable.
- Connection path: not applicable.
- Evidence path: not applicable.

# Completion Evidence

- Changed files:
  - `docs/tasks/done/WEB-001_MESSAGE_HUB_DASHBOARD_BASELINE.md`
  - `quality_tests/test_message_hub_dashboard.py`
  - `server/message_hub.py`
- Validation result:
  - `python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server quality_tests.test_message_hub_client -v`: PASS, 8 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS, 204 tests.
- Remaining risks:
  - This is still a minimal built-in page, not a full product UI.
  - Map rendering and report export remain later R2/R4 work.
