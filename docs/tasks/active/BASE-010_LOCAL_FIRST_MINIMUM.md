---
id: BASE-010
title: Minimum user-controlled private data endpoint
status: active
execution_state: queued
owner: unassigned
priority: high
lane: C
depends_on: []
serves_gate: G8-SECURITY-PRIVACY
requires_hardware: false
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
  - docs/tasks/active/BASE-010_LOCAL_FIRST_MINIMUM.md
out_of_scope:
  - implementation outside a reviewed dispatch amendment
  - hardware I/O, purchases, deployment, real data migration/deletion or external contact without task-specific authority
  - changing any Gate from NOT_RUN without its representative acceptance
---

# Goal

Implement the smallest Ego Base engineering endpoint: authorized evidence reaches
user-controlled storage and can be queried/replayed. Define the relay-only cloud
transition and explicit retention/deletion. Start with synthetic data; this is not
full private-model training or a fourth product Gate.

# Acceptance

- [ ] Versioned state/evidence is stored at a named user-controlled endpoint and retains source identity/time.
- [ ] Relay byte/time limits, offline behavior, authenticated receipt and retry are defined and tested.
- [ ] Relay acceptance and durable Base receipt are distinct; do not delete the sole retained copy before the destination has durably acknowledged it. Report/export preserves provenance and reports missing evidence.
- [ ] Access isolation, encryption claims, retention, deletion and failure states match actual behavior; no fixed flag substitutes for protection.
- [ ] Wearable minimum local safety continues when Base/relay is unavailable; no real-data migration/deletion or deployment is inferred.

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
