---
document_status: authoritative
last_verified: 2026-06-26
verified_by: codex
---

# Architecture Decision Records

Use this directory for durable architecture decisions.

## ADR Template

```markdown
# ADR-000N: Title

- Status: proposed | accepted | superseded
- Date: YYYY-MM-DD
- Deciders:

## Context

## Decision

## Consequences

## Links
```

Add or update an ADR when changing topology, protocols, persistence formats, model contracts, hardware authority, or product dependencies.

## Current first-launch decisions

- [ADR-0011](ADR-0011-first-launch-reliable-location-ego-call-sos.md): accepted first-launch capabilities and communications route.
- [ADR-0012](ADR-0012-p0-productization-sprint-1.md): accepted device state ownership and P0 scope.
- [ADR-0013](ADR-0013-call020-single-usb-phase-handoff.md): proposed single-USB CALL proof; unchanged by runtime convergence.
- [ADR-0014](ADR-0014-runtime-convergence.md): accepted on 2026-09-05; bounded runtime integration, independent local state and durability, recognized SOS feedback, scoped recovery.

ADR-0014's decision date is not a hardware or test `last_verified` date.
