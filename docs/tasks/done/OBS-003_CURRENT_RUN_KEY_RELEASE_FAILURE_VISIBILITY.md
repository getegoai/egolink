---
id: OBS-003
title: Current Run Key Release Failure Visibility
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md
  - docs/development/FIELD_TEST.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/tasks/done/OBS-001_UNIFIED_OBSERVABILITY_ENVELOPE_BASELINE.md
  - docs/tasks/done/OBS-002_RAW_FRAME_DASHBOARD_OBSERVABILITY.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/development/PROTOCOL.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/OBS-003_CURRENT_RUN_KEY_RELEASE_FAILURE_VISIBILITY.md
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_message_hub_dashboard.py

out_of_scope:
  - firmware behavior changes
  - flashing firmware or sending hardware control commands
  - changing raw-frame profile or public device wire protocol
  - creating a new key release
  - exposing raw private payload bytes in the Dashboard
  - modifying GitLab or unrelated VPS services
  - long LTE stability, battery/power, enclosure, or product-readiness claims
---

# OBS-003 Current Run Key Release Failure Visibility

## Goal

Make every runnable version demonstrable from Web/API/report surfaces by
showing current run context, key-release or unreleased/baseline state,
command/ACK chain, raw evidence, derived location, and failure reason.

## Acceptance

- [x] `/api/state` includes top-level `current_run`.
- [x] `current_run` includes current test run, device, firmware, key-release
      context, command/ACK summary, raw-frame summary, location summary,
      failure summary, and evidence counts.
- [x] Test-run export includes top-level `run_context`.
- [x] `observability_summary` includes `failure_summary`.
- [x] Dashboard renders a `Run Context` panel.
- [x] Key-release manifests are available in the VPS deploy package so the
      server can identify exact matches or the latest released baseline.
- [x] Focused Message Hub server/dashboard tests pass.

## Implementation

- Added server-side helpers in `server/message_hub.py` to derive:
  - `current_run` for `/api/state`;
  - `run_context` for `/api/v1/test-runs/{test_run_id}/export`;
  - `failure_summary` for report/export consumers.
- Added key-release manifest loading from `docs/current/key_releases/*.json`.
  Exact current-run matches use manifest `firmware_test_run_id` or
  `firmware_version`; otherwise the server marks the run as `unreleased` and
  reports the latest released baseline when manifests are present.
- Added Dashboard `Run Context` fields: Current Run, Key Release, Baseline,
  Firmware, Run Device, Command Chain, Raw Evidence, Derived Location, Failure
  State, Failure Reason, and Evidence Counts.
- Updated `scripts/deploy_message_hub_vps.ps1` to include
  `docs/current/key_releases` in the Message Hub package.

## Validation

- `python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard -v`
  passed with 20 tests.
- `python scripts/context_lint.py` passed.
- `git diff --check` passed with only the existing PowerShell line-ending
  warning for `scripts/deploy_message_hub_vps.ps1`.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  300 tests.
- VPS deploy smoke:
  - `egolink-message-hub.service` restarted and stayed `active`.
  - Public `/health` returned `ok=true`.
  - Public `/` returned HTTP 200 and contained the Run Context fields.
  - Unauthenticated `/api/state` returned HTTP 401.
  - Authenticated `/api/state.current_run` reported
    `loc005a-source-states-20260630-001` as `unreleased`, baseline `KR-003`,
    command/ACK `cmd-000024` as `ok`, raw-frame parse status `ok`, and
    failure reason `GNSS_NO_FIX`.
  - Existing GitLab service remained active.

## Boundaries

- This is a Server-Web/report visibility increment only.
- It does not change firmware behavior, hardware state, device wire protocol,
  raw private payload redaction, LTE stability, GNSS behavior, battery/power
  behavior, enclosure behavior, or product readiness.
