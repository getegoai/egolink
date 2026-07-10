---
id: WEB-002A
title: Dashboard Latest Location And Auth Visibility
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
  - docs/current/STATUS.md
  - docs/tasks/done/WEB-001_MESSAGE_HUB_DASHBOARD_BASELINE.md
  - docs/tasks/done/FIELD-001A_FW002A_USB_FREE_LOCATION_SCAFFOLD_VALIDATION.md

allowed_paths:
  - docs/current/
  - docs/tasks/
  - quality_tests/
  - server/

out_of_scope:
  - firmware behavior changes
  - protocol schema changes
  - hardware flashing or validation
  - changing VPS GitLab
  - storing real VPS passwords, bearer tokens, Wi-Fi secrets, or private logs
---

# Problem

After FIELD-001A, the VPS API contained real USB-Free device messages, but the
Dashboard could still look empty or misleading when the browser did not have a
bearer token or when a newer `sensor_sample` replaced the latest generic
telemetry after a `location_report`.

# Expected Result

The Web Dashboard should make auth failures visible and keep the latest
`location_report` available as field-state evidence even after newer non-location
telemetry arrives.

# Acceptance Criteria

- [x] `/api/state` device rows include `latest_location`, derived from the most
      recent `event_type=location_report` message for that device.
- [x] `latest_location` survives later `sensor_sample` telemetry without a
      database schema migration.
- [x] Dashboard field state prefers `latest_location` for GNSS/fix/source
      fields when available.
- [x] Dashboard panels show a visible API auth state on 401 instead of appearing
      blank.
- [x] Updated Message Hub is redeployed to the VPS without touching existing
      GitLab.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Board: not applicable.
- Firmware commit or image: not applicable.
- Connection path: not applicable.
- Evidence path: not applicable.

# VPS Verification

- Service: `egolink-message-hub.service`.
- Public health endpoint: `/health` returned `ok=true`.
- Auth boundary: unauthenticated `/api/state` returned HTTP 401.
- Authenticated `/api/state` returned device data, including
  `ego-link-r1-connectivity-001` on firmware
  `0.1.0-fw002-location-scaffold`.
- Authenticated device state showed latest generic telemetry as
  `sensor_sample` and `latest_location` as `location_report seq=4`,
  `fix=false`, `gnss_state=driver_not_integrated`,
  `source_status=unverified`.

# Completion Evidence

- Changed files:
  - `docs/current/STATUS.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/WEB-002A_DASHBOARD_LATEST_LOCATION_AUTH_VISIBILITY.md`
  - `quality_tests/test_message_hub_dashboard.py`
  - `quality_tests/test_message_hub_server.py`
  - `server/message_hub.py`
- Validation result:
  - `python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard -v`: PASS, 9 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 224 tests.
- Remaining risks:
  - The Dashboard still uses the P0 built-in polling UI, not the later R4 map
    and report surface.
  - Real GNSS fix and SIM7670G GNSS/LTE firmware control remain unverified.
