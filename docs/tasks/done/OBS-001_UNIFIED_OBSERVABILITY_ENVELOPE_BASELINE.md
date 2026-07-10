---
id: OBS-001
title: Unified Observability Envelope Baseline
status: completed
created_at: 2026-06-28
completed_at: 2026-06-28
---

# OBS-001 Unified Observability Envelope Baseline

## Goal

Make Message Hub failures explainable before USB-Free long stability, LTE,
power, or enclosure tests.

## Context

- `docs/CONTEXT_INDEX.md`
- `docs/development/PROTOCOL.md`
- `docs/development/FIELD_TEST.md`
- `docs/current/ROADMAP_EGOLINK_P0.md`
- `shared/contracts/message_hub_status.schema.json`
- `shared/contracts/message_hub_event.schema.json`
- `server/message_hub.py`

## Allowed Paths

- `server/message_hub.py`
- `shared/contracts/message_hub_status.schema.json`
- `shared/contracts/message_hub_event.schema.json`
- `quality_tests/test_message_hub_server.py`
- `quality_tests/test_message_hub_dashboard.py`
- `quality_tests/test_message_hub_contracts.py`
- `docs/development/PROTOCOL.md`
- `docs/development/FIELD_TEST.md`
- `docs/current/STATUS.md`
- `docs/tasks/TASK_TREE.md`
- `docs/tasks/done/OBS-001_UNIFIED_OBSERVABILITY_ENVELOPE_BASELINE.md`

## Out Of Scope

- Firmware behavior changes.
- LTE data transport.
- Long-running stability tests.
- Hardware flashing or serial capture.
- New location-memory tables or a belief engine.

## Implementation

- `/api/state` device rows now include `observability`.
- test-run export now includes `observability_summary`.
- Dashboard renders transport, transport error, runtime reset, boot identity,
  command state, power, cell, GNSS reason, and reason codes.
- Status and event schemas now list optional observability groups:
  `boot_id`, `uptime_s`, `transport`, `runtime`, `command`, `power`, `gnss`,
  `cell`, and event-side `location_belief`.

The implementation is additive. Existing `egolink.p0.v1` status, event,
command, ACK, and error messages remain valid.

## Deployment Evidence

- The updated Message Hub was redeployed to the operator VPS as
  `egolink-message-hub.service`.
- `/health` returned `ok=true`.
- Authenticated `/api/state` returned three devices.
- The current connectivity-node row included `observability`; the smoke output
  did not print bearer tokens or exact coordinates.
- Existing GitLab on the VPS was not modified.

## Validation

- `python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_contracts -v`:
  PASS, 15 tests.
- `python scripts/context_lint.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS,
  238 tests.

## Remaining Risks

- OBS-001 improves server/Web explainability, but older firmware still reports
  only the fields it already knows.
- LTE registration, LTE HTTP uplink, LTE command polling, power accuracy,
  product battery behavior, and enclosure GNSS remain separate gates.
