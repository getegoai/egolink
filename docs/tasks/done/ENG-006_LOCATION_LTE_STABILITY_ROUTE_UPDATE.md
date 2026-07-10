---
id: ENG-006
title: Location / LTE / Stability Route Update
status: completed
created_at: 2026-06-28
completed_at: 2026-06-28
---

# ENG-006 Location / LTE / Stability Route Update

## Source Plan Note

The planning draft `docs/EGO_LINK_P0_TASK_PLAN_LOCATION_LTE_STABILITY.md`
uses `ENG-003` for this work. The current task tree already has `ENG-003`
completed as Legacy Archive Review, so this task is tracked as `ENG-006` to
avoid reusing an ID while preserving the user's requested intent.

## Goal

Update the project route after FW-002C resetdiag fix3 USB-Free GNSS real-fix
evidence. The next stage is observable-first development, not a blind long
stability run.

## Context

- `docs/CONTEXT_INDEX.md`
- `docs/current/STATUS.md`
- `docs/current/ACTIVE_BUILD.md`
- `docs/current/ROADMAP_EGOLINK_P0.md`
- `docs/development/DEV_FLOW.md`
- `docs/development/FIELD_TEST.md`
- `docs/development/PROTOCOL.md`
- `docs/EGO_LINK_P0_TASK_PLAN_LOCATION_LTE_STABILITY.md`

## Allowed Paths

- `docs/current/STATUS.md`
- `docs/current/PROJECT_SNAPSHOT.md`
- `docs/current/ROADMAP_EGOLINK_P0.md`
- `docs/tasks/TASK_TREE.md`
- `docs/development/FIELD_TEST.md`
- `docs/development/LOCATION_ENGINE.md`
- `docs/development/LTE_TRANSPORT.md`
- `docs/development/PROTOCOL.md`
- `docs/CONTEXT_INDEX.md`
- `docs/tasks/done/ENG-006_LOCATION_LTE_STABILITY_ROUTE_UPDATE.md`

## Out Of Scope

- Firmware flashing.
- Long stability runs.
- LTE data transport execution.
- Public protocol field removal or renaming.
- Claims about battery, enclosure, LTE, or product power behavior.

## Result

The roadmap now sequences:

```text
R2.1 observability completion gate
-> R2.2 short USB-Free baseline stability gate
-> R2.3 SIM7670G LTE data transport thin-slice
-> R2.4 LTE command loop gate
-> R2.5 multi-source location observation and memory MVP
-> R3.0 LTE long-run and reconnect gate
-> R3.1 independent-power and battery accuracy gate
-> R3.2 enclosure / mounting GNSS gate
```

New development baselines:

- `docs/development/LOCATION_ENGINE.md`
- `docs/development/LTE_TRANSPORT.md`

## Validation

- `python scripts/context_lint.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS,
  238 tests.

## Remaining Risks

- The route update does not validate LTE, long-run stability, battery accuracy,
  power behavior, or enclosure GNSS performance.
- `OBS-001` is required before longer field testing so future failures are
  diagnosable from VPS/Web evidence.
