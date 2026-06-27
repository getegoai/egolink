---
document_status: authoritative
last_verified: 2026-06-26
verified_by: codex
---

# Safety Contract

P0 safety behavior is deterministic and evidence-first.

## Required Properties

- Safety-critical actions must not depend on an LLM decision.
- A user confirmation prompt must produce an explicit `safe`, `needs_help`, `no_response`, or equivalent recorded outcome.
- Location, network, image, audio, IMU, and model evidence must identify whether the source is real firmware, PC-side probe, mock, replay, or unknown.
- Emergency dispatch, real calling, SMS, and external escalation are out of scope until a later task explicitly adds them.
- Every safety event record should be replayable without attached boards.

## Current P0 Loop

```text
motion candidate
-> ask_user
-> user confirmation
-> request location/evidence
-> safety event record
-> replay and quality gate
```
