---
id: OBS-002
title: Raw Frame Dashboard Observability
status: completed
priority: high
requires_hardware: false
created: 2026-06-29
last_updated: 2026-06-29

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/PROTO-002_RAW_FRAME_TRANSPORT_CONTRACT.md
  - docs/tasks/done/FW-003_RAW_FRAME_LTE_COMMAND_LOOP.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/OBS-002_RAW_FRAME_DASHBOARD_OBSERVABILITY.md
  - server/message_hub.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py

out_of_scope:
  - firmware flashing
  - hardware validation
  - changing GitLab or unrelated VPS services
  - exposing raw private payload bytes in the Dashboard
  - long LTE stability, reconnect, GNSS, battery, or power acceptance
---

# OBS-002 Raw Frame Dashboard Observability

## Goal

Make the Message Hub Web Dashboard show the current raw-frame path clearly:
recent frame direction/type, parse status, derived message type, frame ID,
and receive time. This gives the operator a visible effect for the FW-003
raw-frame Walking Skeleton without exposing raw private payload bytes.

## Acceptance

- [x] Dashboard HTML includes a Raw Frames panel.
- [x] `/api/state` raw frame records remain redacted.
- [x] The Raw Frames panel shows parse status and derived message type.
- [x] Focused dashboard/server tests pass.
- [x] `python scripts/context_lint.py` passes.
- [x] `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passes if
      behavior changes.
- [x] VPS deployment smoke confirms `/api/state` still exposes redacted
      `raw_frames` behind bearer auth.

## Validation Notes

- Focused tests passed:
  `python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v`
  with 15 tests.
- Full verification passed:
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` with 279 tests.
- `python scripts/context_lint.py` passed after task path cleanup.
- `git diff --check` passed.
- VPS deployment restarted `egolink-message-hub.service` on `0.0.0.0:8790`
  without touching GitLab.
- VPS smoke:
  - `/` returned HTTP 200 and included the Raw Frames panel.
  - unauthenticated `/api/state` returned HTTP 401.
  - authenticated `/api/state` returned HTTP 200 with 8 redacted raw frames.
  - latest raw frame was `cmd-000017`, `parse_result.status=ok`,
    `derived_message_type=ack`, and `raw_payload.data_redacted=true`.

## Completion Boundary

This task improves observability only. It does not validate another hardware
run, LTE stability, reconnect behavior, GNSS-over-LTE, battery/power behavior,
or product readiness.
