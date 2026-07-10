---
id: LOC-003
title: Location Memory Gate
status: completed
created_at: 2026-06-30
completed_at: 2026-06-30
---

# LOC-003 Location Memory Gate

## Goal

Add the first VPS-side location memory and active belief gate so a later GNSS
no-fix attempt remains explainable instead of erasing the last useful
calibration.

This keeps the KR-001 Walking Skeleton alive:

```text
location_report or location_observation
-> Message Hub stores original message/raw frame
-> derived location_memory
-> derived active location_belief
-> Web/API and test-run export
```

## Context

- `docs/CONTEXT_INDEX.md`
- `docs/development/DEV_FLOW.md`
- `docs/development/PROTOCOL.md`
- `docs/development/LOCATION_ENGINE.md`
- `docs/current/ROADMAP_EGOLINK_P0.md`
- `docs/current/KEY_RELEASES.md`
- `docs/tasks/done/LOC-002_LOCATION_OBSERVATION_CONTRACT_BASELINE.md`
- `docs/tasks/done/LTE-004_RAW_LTE_REQUEST_LOCATION_THIN_SLICE.md`
- `server/message_hub.py`
- `scripts/validate_location_memory_gate.py`

## Allowed Paths

- `server/message_hub.py`
- `scripts/validate_location_memory_gate.py`
- `quality_tests/test_message_hub_server.py`
- `quality_tests/test_message_hub_dashboard.py`
- `quality_tests/test_location_memory_gate.py`
- `docs/development/PROTOCOL.md`
- `docs/development/LOCATION_ENGINE.md`
- `docs/current/ROADMAP_EGOLINK_P0.md`
- `docs/current/KEY_RELEASES.md`
- `docs/current/key_releases/KR-002_LOCATION_MEMORY_GATE.json`
- `docs/tasks/TASK_TREE.md`
- `docs/tasks/done/LOC-003_LOCATION_MEMORY_GATE.md`

## Out Of Scope

- Firmware changes or flashing.
- New hardware commands.
- Long LTE stability or reconnect testing.
- Real firmware-side cell, Wi-Fi, IMU, or power fusion.
- Product GNSS acceptance, enclosure acceptance, battery/power acceptance, or
  final personal-place model acceptance.

## Implementation

- Message Hub now creates a persistent `location_memory` table.
- `location_observation` with `location_belief` updates the memory state,
  radius, confidence, source, and reason.
- `location_report fix=true` creates a `Fine` GNSS calibration memory.
- A later `location_report fix=false` records `last_no_fix` but preserves the
  prior valid memory instead of overwriting it with unknown state.
- `/api/state` device rows expose `location_memory`.
- `observability.location_memory` exposes the preserved memory summary.
- `observability.location_belief` now derives an active `Predicted` state when
  the latest report is no-fix but a prior memory exists.
- Test-run export rebuilds the same derived memory/belief summary from the
  run messages.
- Dashboard shows memory state, memory update time, and memory reason.
- `scripts/validate_location_memory_gate.py` can seed a synthetic device and
  verify the memory-backed no-fix behavior without hardware or USB runtime.

## Validation

- `python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard quality_tests.test_location_memory_gate -v`:
  PASS, 18 tests.
- `python -m py_compile server/message_hub.py scripts/validate_location_memory_gate.py`:
  PASS.
- `python scripts\context_lint.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
  287 tests.
- `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-002_LOCATION_MEMORY_GATE.json --json`:
  PASS.
- VPS deploy to `203.0.113.10:8790`: PASS; `egolink-message-hub.service`
  restarted active without touching GitLab.
- VPS synthetic gate:
  `python scripts\validate_location_memory_gate.py --hub-url http://203.0.113.10:8790 --device-id ego-link-r0-location-memory-gate --test-run-id location-memory-gate-kr002-20260630 --output-dir reports\location_memory\location-memory-gate-kr002-20260630 --json`:
  PASS; active belief `Predicted`, memory `Fine`, latest report no-fix.

## Completion Boundary

LOC-003 is a server/Web/API gate and a small rule baseline. It does not claim
final multi-source fusion, firmware-side source collection, real outdoor GNSS
acceptance, LTE long-run stability, product power behavior, or product
readiness. It makes future failures more explainable and gives KR-002 a
versioned gate to rerun.
