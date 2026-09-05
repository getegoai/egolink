---
document_status: authoritative
last_verified: 2026-08-23
verified_by: codex
---

# Safety Contract

P0 safety behavior is deterministic, local-first and evidence-first. Under
[ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md), the
physical-SOS product Gate is `P0-SOS`; its current state is `NOT_RUN`.

## Required Properties

- Safety-critical actions must not depend on an LLM decision.
- A physical SOS long press must immediately create local feedback and a
  durable `safety_event` before any network attempt. It must not wait for AI,
  camera, a fresh GNSS fix, Guardian acknowledgement or a successful call.
- A user confirmation prompt must produce an explicit `safe`, `needs_help`, `no_response`, or equivalent recorded outcome.
- Location, network, image, audio, IMU, and model evidence must identify whether the source is real firmware, PC-side probe, mock, replay, or unknown.
- SOS reuses the accepted `safety_event` contract and persistent priority
  outbox. It does not create a second emergency-event truth record.
- The last trusted location is uploaded immediately with source event time,
  age, confidence and uncertainty; elevated GNSS/LTE sensing then proceeds
  independently and must not fabricate a fresher coordinate.
- Guardian delivery/acknowledgement and Ego Call request/signaling/media are
  independent truthful states. `pending`, `failed`, `reconnecting` and
  unavailable states remain visible instead of being collapsed into success.
- Event ordering follows source event time plus boot-scoped monotonic and
  clock-mapping lineage. Receive/ingest time cannot substitute for missing
  source time; ambiguous ordering is retained and surfaced.
- Ego Call and a bounded Guardian alert are in P0 scope. PSTN, SMS and public
  emergency-service dispatch are explicitly out of scope for Sprint 1.
- Every safety event record should be replayable without attached boards.

## Physical SOS Composition

```text
physical long press
-> durable local safety_event + local feedback
-> priority outbox
-> upload last trusted location
-> elevate GNSS/LTE policy
-> Guardian alert state
-> Ego Call request/call state
-> event-time replay and product evidence
```

The branches after the local durable record may proceed concurrently and fail
independently. Low battery can reduce normal sensing budgets but cannot disable
SOS. Camera and learned models may add labelled observations later; they can
neither make nor veto the P0 decision.

## Reusable Historical Loop

The earlier
`motion candidate -> ask_user -> user_confirmation -> request_location -> safety_event`
loop remains a useful deterministic simulator/interaction fixture. It is not
physical-SOS evidence and does not gate the ADR-0012 Sprint 1 chain.

No current schema, simulator replay, build result or PC fixture is evidence
that `P0-SOS` has passed. Passing requires the named representative physical,
durability, outage/reboot, Guardian, location and Ego Call evidence.
