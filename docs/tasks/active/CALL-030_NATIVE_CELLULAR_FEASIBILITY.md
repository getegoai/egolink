---
id: CALL-030
title: Native cellular feasibility and audio interface
status: active
execution_state: queued
owner: unassigned
priority: high
lane: B
depends_on: []
serves_gate: P0-CALL
requires_hardware: true
created: 2026-09-22
last_updated: 2026-09-22
context:
  - docs/CONTEXT_INDEX.md
  - docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/current/ACTIVE_BUILD.md
  - shared/contracts/
allowed_paths:
  - docs/tasks/active/CALL-030_NATIVE_CELLULAR_FEASIBILITY.md
out_of_scope:
  - implementation outside a reviewed dispatch amendment
  - hardware I/O, purchases, deployment, real data migration/deletion or external contact without task-specific authority
  - changing any Gate from NOT_RUN without its representative acceptance
---

# Goal

Name the exact modem, firmware, operator/SIM and audio interface needed for the
primary native cellular path. Preserve CALL-020/021 as paused RTC research assets.
The current audio-less connectivity board cannot prove acoustic closure.

# Acceptance

- [ ] Official/exact-board capability inputs and unknowns are traceable; no capability is inferred from the board name.
- [ ] AT ready/configuration failure, dial/answer/hangup/cancel and contact authorization have a bounded offline plan and executable acceptance cases.
- [ ] Audio/power/RF inputs and measured or explicitly unknown budgets are handed to HW-021/HW-022.
- [ ] A separately authorized signal-only probe, if performed, is separated from full-duplex audio evidence.

# Dispatch and validation

Queued, not assigned implementation WIP. At dispatch, assign the owner, exact
implementation/evidence paths and bounded experiment scope; reuse current
components and preserve Gemini's acquisition/recovery/field path.

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion evidence

NOT_RUN. Planning creates no hardware, privacy implementation or product evidence.

# Builder Prompt

Read this packet and its context. Prepare one bounded implementation slice and
its allowed paths before editing source. Keep hardware/data/remote operations
inside their explicit task scope and record truth separately from predictions.
