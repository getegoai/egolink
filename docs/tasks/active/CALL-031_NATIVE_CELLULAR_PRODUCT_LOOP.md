---
id: CALL-031
title: Native cellular primary product loop
status: active
execution_state: queued
owner: unassigned
priority: high
lane: B
depends_on:
  - CALL-030
  - HW-022
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
  - docs/tasks/active/CALL-031_NATIVE_CELLULAR_PRODUCT_LOOP.md
out_of_scope:
  - implementation outside a reviewed dispatch amendment
  - hardware I/O, purchases, deployment, real data migration/deletion or external contact without task-specific authority
  - changing any Gate from NOT_RUN without its representative acceptance
---

# Goal

Prove authorized inbound and outbound native cellular calling on one identified,
independently powered audio-capable integrated prototype. RTC remains optional;
it cannot substitute for primary-path acceptance.

# Acceptance

- [ ] Device and authorized contact can initiate, answer and terminate calls with real full-duplex sound.
- [ ] The product run uses independent power and no PC/USB runtime dependency; authorized contacts, acoustics, RF coexistence and privacy evidence are included in the product review.
- [ ] Weak network, unreachable contact, reject/busy, timeout, cancellation, identity and recovery states are honest and bounded.
- [ ] Location/SOS can make progress and ended/expired calls do not resurrect across replay/reboot.
- [ ] Image/config/operator/audio/power evidence and measured call setup/reachability/quality are reviewed before P0-CALL changes from NOT_RUN.

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
