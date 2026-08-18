---
document_status: authoritative
last_verified: 2026-08-18
verified_by: codex
owner: founder
---

# ADR-0010: Asynchronous Observations, Event-time Reconstruction and Store-and-Forward

- Status: accepted
- Date: 2026-08-18
- Decider: founder
- Scope: A-line sensor acquisition, time reconstruction and intermittent-network retention

## Context

The first A-line field-session plan coupled progress to a synchronized
GNSS/LTE/IMU/Camera capture. Real probes showed that the sensors have different
physical cadences, power constraints and clock evidence. Requiring them to
sample together on the device made Camera and cross-source synchronization
artificial prerequisites for the first GNSS-blackout experiment.

The current firmware also has reconnect/failover, a bounded current-boot retry
and reboot-aware identity, but these are not durable Store-and-Forward. The
volatile outbox drops a failed raw frame after its immediate retry budget, and
the historical LTE-011 switch emits test-shaped fields without implementing a
persistent queue or reboot replay. Those facts must not be promoted into a
durability claim.

## Decision

### Independent asynchronous acquisition

GNSS, LTE, IMU and Camera run independently according to their physical
cadence, power policy and trigger policy. The device is not required to issue
a common capture trigger or produce simultaneous samples.

The device responsibility is:

```text
Sense -> Timestamp -> Persist -> Upload
```

Every observation preserves a stable record identity, device and boot scope,
source, source-local sequence, capture monotonic time, capture UTC when known,
the original sensor timestamp when present, timestamp source/quality, status
and payload. Missing time stays missing with a reason; server receive or ingest
time is retained separately and is never relabelled as capture time.

The existing A0 normalized fields such as `timestamp_monotonic_ns`,
`timestamp_utc`, `source_timestamp`, `receive_timestamp_utc` and
`ingest_timestamp_utc` remain valid. This ADR does not itself change a public
wire or schema contract.

### Server-side event-time reconstruction

The VPS responsibility is:

```text
Ingest -> Align -> Replay -> Fuse -> Learn -> Evaluate
```

Within one boot, source monotonic time preserves order. Named UTC anchors map a
boot clock into event time with recorded provenance and uncertainty. The VPS
orders observations by reconstructed capture/event time, not network arrival
time. When clock evidence is insufficient or uncertainty intervals overlap,
cross-source order is `unavailable` or `ambiguous`; the system retains
same-source order and does not invent precision.

Clock alignment is therefore required for trustworthy cross-source reasoning,
but simultaneous device-side sampling is not.

### Bounded persistent Store-and-Forward

Each uploadable observation is written to a finite local persistent queue
before transmission. A queued record survives restart, retains its original
capture time and identity, and is deleted only after a positive VPS
acknowledgement. Upload retries reuse that identity so the VPS can process the
observation idempotently. Capacity, overflow/drop reason, retry, flush and
oldest-record-age counters remain observable. Network recovery drains the
queue without changing event time.

The first implementation should reuse the existing raw-frame, boot identity,
retry and link-recovery paths and add only the smallest persistent queue and
idempotency behavior needed. It must not introduce a broker or a new complex
messaging subsystem.

### Current experiment profile

The active milestone is `FT-001B — First Replayable Asynchronous GNSS+IMU
Session`:

- GNSS and IMU are the minimum required sources;
- LTE is opportunistic;
- Camera and manual events are optional;
- Camera absence does not block `EXP-A1-000`;
- unavailable LTE or IMU position baselines remain legitimate results.

The existing full four-source A-R0 contracts remain usable as a later
structural-review profile. They are no longer the entry condition for FT-001B,
and `field_eligible=false` under that stricter profile does not invalidate an
otherwise honest engineering Replay.

## Consequences

- `FIELD-AI-001` is superseded by `FT-001B`.
- Existing data may support GNSS-only same-source Replay while LTE/IMU
  cross-source ordering remains unavailable; outputs must say so.
- A server-receive timestamp can bound an export or contribute to an explicitly
  uncertain estimate, but cannot become source event time or Ground Truth.
- Current volatile retry, failover and LTE-011 test evidence do not satisfy the
  persistent Store-and-Forward decision.
- Camera automatic capture remains desirable but is not a prerequisite for the
  first GNSS blackout smoke and must not trigger a large firmware refactor now.
- A-R0 remains `0/8`; architecture acceptance, code, fixtures and partial
  sessions do not pass any evidence Gate.

## Superseded Assumptions

This ADR supersedes only the following conflicting assumptions in ADR-0009,
the initial A-line baseline and pre-2026-08-18 A0 task text:

- one synchronized four-source Session is required before the first smoke;
- Camera or manual events are mandatory for FT-001B;
- one simultaneous common sensor anchor is the only acceptable model for
  reconstructing event time.

It does not supersede the AI v0.1 belief-estimation flow, A0 task numbering,
evidence-driven Gate rules, privacy boundaries or the prohibition on fabricated
measurements.

## Links

- [Current A-line execution context](../../current/EGO_LINK_AI_CURRENT_CONTEXT.md)
- [A-line AI baseline](../../current/EGO_LINK_A_LINE_AI_CONTEXT.md)
- [ADR-0009](ADR-0009-ai-v0-1-belief-estimation-baseline.md)
- [Unified timestamp](../../development/UNIFIED_TIMESTAMP.md)
- [Field Session schema](../../development/FIELD_SESSION_SCHEMA.md)
- [FT-001B task](../../tasks/active/FT-001B_FIRST_REPLAYABLE_ASYNC_GNSS_IMU_SESSION.md)
