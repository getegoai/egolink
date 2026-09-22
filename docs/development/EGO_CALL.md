---
document_status: legacy_rtc_engineering_baseline
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
source_task: CALL-001
---

# Ego Call Legacy RTC Minimum Architecture

## Purpose

This document preserves the CALL-001 RTC session/control contract between one
EgoCore and an authorized Guardian App over LTE data and managed RTC. Under
[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md),
the first-launch P0-CALL route is native cellular voice through CALL-030 and
CALL-031; RTC is optional and CALL-020/021 remain paused. The RTC state machine
below does not define native modem call states or resume the old task chain.
The project does not operate a public PSTN/SIP gateway.

This baseline freezes boundaries and truthful state semantics. It does not
select an RTC vendor or claim device audio, mobile-app, weak-network, or
hardware acceptance.

## Component Boundary

```text
EgoCore -- authenticated signaling --> Call Control/API <-- authenticated signaling -- Guardian App
EgoCore <================ managed encrypted RTC media ======================> Guardian App
   |                              |
   +-- Message Hub event/context -+-- replayable state/event record
```

- Call Control owns authorization, session creation, idempotency, short-lived
  RTC credentials, state transitions, retry bounds, and session audit events.
- The RTC service owns media traversal and relay. Media does not pass through
  Message Hub, and Message Hub must not become an audio proxy.
- Message Hub may carry a call request, a bounded call-state event, an SOS
  reference, and a `location_belief` reference. It must not carry RTC secrets,
  raw SDP/ICE payloads, or unrestricted precise-location copies.
- Guardian App shows remote truth: request received, ringing, connected,
  reconnecting, ended, or failed. Local device feedback is separate and may
  precede remote delivery.

## Identity And Authorization

- A call session binds exactly one `device_id` and one authorized
  `guardian_id`; the binding is checked server-side for every state-changing
  request. After revocation, CALL-001 allows only trusted Call Control to write
  a terminal `failed/binding_revoked` closeout; it cannot advance the session to
  ringing, connected, or recovered.
- Device and guardian authenticate independently. A bearer token, RTC token,
  SDP offer, ICE candidate, or private key is never stored in the session
  event contract or normal logs.
- Session creation uses a caller-generated idempotency key. Repeating the same
  request returns the same session; it must not ring twice.
- RTC credentials are audience-, session-, role-, and expiry-bound. Credential
  lifetime is shorter than session-retention lifetime.
- Revocation of the guardian/device binding prevents new sessions. The
  emergency behavior of an already connected session remains an explicit
  product-policy decision and must be tested before launch.

## State Machine

Each persisted record is one monotonic session transition defined by
`shared/contracts/ego_call_session.schema.json`.

| From | Allowed next state | Meaning |
|---|---|---|
| none | `requested` | Call Control durably accepted one idempotent request. |
| `requested` | `ringing`, `failed`, `ended` | Guardian notification is pending/visible, or setup terminates honestly. |
| `ringing` | `connected`, `failed`, `ended` | Both endpoints joined media, or the attempt terminates. |
| `connected` | `reconnecting`, `ended`, `failed` | Media was live, then degrades or terminates. |
| `reconnecting` | `connected`, `ended`, `failed` | Media recovers within the retry bound or terminates. |
| `ended`, `failed` | none | Terminal; a retry creates a new session ID. |

`ringing` is not proof that a human saw or heard the call. `connected` requires
both authenticated endpoints and an RTC media-ready signal. A timeout,
authorization rejection, exhausted reconnect budget, provider failure, or
technical `setup_timeout` ends as `failed` with a bounded reason code. User
decline/hang-up and a bounded unanswered ring (`no_answer`) end as `ended`;
exact reason taxonomy is contract-versioned.

State events are append-only and ordered by `(session_id, sequence)`. Replayed
events with the same `event_id`/idempotency key are deduplicated. A lower or
conflicting sequence fails closed instead of rewriting history.

## SOS Composition

The following is the historical CALL-001 fixture composition, retained to
explain its existing ordering contract; it is not the current SOS dispatcher.
Current product SOS gives immediate recognition feedback independently of
storage success, attempts durable recording, declares storage degradation,
and independently attempts the available native cellular primary route under
ADR-0016. RTC fixture steps cannot impose an RTC or persistence dependency on
that primary attempt. Manual SOS never waits for a fresh GNSS fix or AI:

1. The device immediately persists the local SOS event and starts local
   feedback.
2. In parallel it uploads the best current `location_belief` reference,
   elevates GNSS/location policy, notifies authorized guardians, and requests
   Ego Call.
3. Each remote step reports its own state. Local acceptance is not presented
   as remote delivery, ringing, connection, or guardian acknowledgement.
4. A newer location belief belongs to the existing location/safety event
   contract and does not mutate the original SOS record. CALL v0 carries a
   snapshot reference into the call session but does not invent a second
   location-update event type. Stale last-known state eventually degrades to
   `Unknown` under the location contract.
5. AI may add context or recommend an action, but cannot cancel manual SOS,
   forge delivery, or synthesize call success.

The CALL-001 in-memory fixture proves the ordering rule and honest remote call
state only. Its local SOS trace is explicitly non-contract and non-durable.
Durable local safety-event persistence/replay must reuse the accepted safety
event contract plus the ADR-0010 priority outbox in a separate task.

## Retry And Failure Policy

- Session creation and state writes use bounded exponential retry with stable
  idempotency. Retry limits and deadlines are configuration with observability,
  not hidden infinite loops.
- Media loss enters `reconnecting` only after the RTC client detects loss; a
  bounded reconnect deadline resolves to `connected`, `ended`, or `failed`.
- If signaling is unavailable, critical device events enter the persistent
  priority outbox planned by ADR-0010. Media itself is never stored there.
- App background-notification delivery, app foreground readiness, signaling
  reachability, and RTC media health are separate metrics.
- Every failure has a bounded machine reason plus an operator-safe display
  message. Logs redact identities where possible and never record credentials.

## Location Context Boundary

The call contract carries only a reference containing belief ID, state,
observation time, age, and uncertainty radius. Coordinates remain in the
authorized location service and are fetched under guardian policy. This avoids
copying precise location into every call log and keeps location retention
independent from call audit retention.

`Fine`, `Coarse`, and `Predicted` must remain distinguishable. Missing or
expired information is `Unknown`; a call UI must not draw a stale precise point
as current.

`age_ms` is an event-time snapshot. When CALL-001 carries the same belief into
a later call transition, it preserves belief identity/state/radius and
recomputes age from `observed_at_utc`; it never freezes a fresh-looking age for
the lifetime of a long call. Only the authenticated device or Safety Kernel may
introduce a location belief in this fixture; a guardian, Call Control, or RTC
adapter cannot forge or replace one.

## Privacy And Retention

- Call metadata retention is bounded and policy-owned. The v0 contract caps a
  declared retention at 30 days; the actual launch value remains a founder and
  compliance decision.
- Audio recording is off by default. Enabling it later requires an explicit
  consent reference, visible product behavior, a retention/deletion policy,
  and a separate review.
- Debug exports use pseudonymous identifiers and exclude credentials, media,
  raw signaling, and unrestricted coordinates.
- Guardian access, account recovery, deletion/export SLA, minor/elder consent,
  and lawful-basis wording remain product/compliance gates.

## Vendor Decision Criteria

Do not select a production RTC provider from feature lists alone. A bounded
comparison must measure mainland-China reachability, setup latency, loss/jitter
recovery, TURN/relay dependence, SDK/device fit, TLS and media encryption,
regional data handling, credential controls, observability, outage behavior,
pricing at expected minutes/concurrency, support, exit/export path, and the
ability to run deterministic PC fixtures without production credentials.

The first PC loop may use an in-process fake signaling/media readiness adapter.
It proves state, authorization, idempotency, failure, and replay semantics only;
it cannot prove production audio or network quality.

In the CALL-001 fixture, endpoint actors may assert only their own local/remote
hang-up or decline actions. `call_control` alone may assert notification,
timeout and internal authorization/control outcomes; `rtc_adapter` alone may
assert media ready/lost/recovered and provider/network outcomes. These are
pre-authenticated fixture contexts, not production credentials, and prevent a
device or guardian from forging `ringing` or `connected` state.

The persisted `asserted_by` role/reference is credential-free audit context.
The schema binds reason codes to asserting roles, while the fixture also checks
trusted subject references, session identity, monotonic timestamps, location
age consistency, and idempotent replay. Production service identities and
credential verification remain outside this PC fixture.

## CALL-001 Exit Split

- Architecture and transition contract: defined here and in the JSON Schema.
- Deterministic PC/browser call-session fixture: implemented and under review;
  it validates state, authorization, idempotency, failure and replay without
  production credentials.
- Durable SOS safety-event persistence/replay: not claimed by CALL-001; must
  reuse the accepted safety-event contract and priority outbox.
- Production RTC vendor, Guardian mobile app, RTC device audio, three-network
  weak-signal tests, privacy approval, and RTC operations remain `unverified`.
  These are separate optional-RTC acceptance needs; native P0-CALL acceptance
  belongs to CALL-031 and cannot borrow this fixture's evidence.
