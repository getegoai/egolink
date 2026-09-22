---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-09-16
verified_by: founder/codex
decision_adr: ../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md
---

# EgoLink Current Execution Baseline

## Product outcome and decision

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
records the founder's 9/19 direction and 9/22 implementation assignment:
active ego-state estimation, reliable location as the user entry point,
strong privacy/local-first, parallel minimal Ego Base and native cellular
primary calling. RTC is optional fallback. This decision changes no evidence
date or Gate result.

| Gate | Required result | Current state |
|---|---|---|
| `P0-LOC` | Representative reliable location, source/age/uncertainty and honest degradation | `NOT_RUN` |
| `P0-CALL` | Native outgoing/incoming calls and stable two-way audio on representative integrated hardware | `NOT_RUN` |
| `P0-SOS` | Physical input, prompt feedback, durable-event attempt, location/alert and independent primary cellular call attempt | `NOT_RUN` |

All three and cross-cutting power, reliability, RF, acoustic/water,
security/privacy, China compliance and NPI assurance are required for sale.
Camera and Base are not fourth capability Gates. Advanced learned L2/L3 and
complete private Base AI do not become new launch blockers. Truthfulness of
the already implemented rule-state path is current engineering acceptance.

## Current ownership and WIP

| Work stream | Owner / current packet | Boundary and next consumer |
|---|---|---|
| Single-board collection, recovery, routes and D2/FIELD | Gemini / P0-CONVERGENCE-20260905 | Actual Wi-Fi/LTE transition, same-record/photo recovery, short independent-power carry, then FIELD-020; preserve ADR-0015 |
| Decision, current image, task management and state truth | Codex / ALIGN-STATE-010, completed offline | Source `3a0728058` and named verification; independent state DEVICE packaging, no acquisition, sensor-policy, camera or transport behavior changes |
| Native cellular product route | CALL-030 then HW-022 and CALL-031, queued | Exact modem/firmware/operator/audio feasibility, then representative native product loop; no implicit live call authority |
| Private endpoint | BASE-010, queued parallel development | Authorized/synthetic Session -> private persistence -> event-time replay/report -> explicit lifecycle |
| Product hardware and China readiness | HW-021 parked; COMPLIANCE-010 queued | Conditional design/evidence intake can proceed when assigned; no inferred procurement or sent inquiry |

A queued, parked, evidence-wait or acceptance-review packet is not active
implementation WIP. LOC-021/OPS-004/OUTBOX-010 are reusable integration assets
with unresolved product evidence, not competing writers. A lane has at most
one integration-sized implementation packet. Codex and Gemini use isolated
worktrees and one reviewed merge owner for shared files/contracts. Codex may
change only ego-state packaging in collection_main; Gemini owns acquisition,
modem/camera/transport, profiles and field execution. See the
[handoff](CODEX_GEMINI_HANDOFF_20260922.md) and
[task tree](../tasks/TASK_TREE.md) for operational assignment.

CALL-020 and CALL-021 remain paused RTC assets, and full SOS remains paused in
the field milestone. CALL-010 basic endpoint evidence is retained; it is not
native calling or representative acoustic acceptance. No work here resumes
old RTC runtime or adds AMOLED/PC forwarding to the single-board field path.

## Immediate bounded order

1. Codex completed authority/current-evidence and existing rule-state
   truth repair under ALIGN-STATE-010, with offline acceptance. Missing, stale, future, partial, invalid or mock
   evidence cannot become confident normal state. Retain boot/source time and
   explicit DEVICE-to-canonical/API projections; regression exercises real
   rendering and invalid inputs. Unflashed source stays separate from the last
   reported running image.
2. Gemini binds one candidate to source/config/image and existing evidence.
   Reuse completed manual/timed/browser results only within their exact
   identity/scope; do not rerun them merely because an old next-step list is
   stale. Close full-outage persistence, same-file/ID pending-photo restart
   recovery, quota/corruption/loss truth and controlled actual Wi-Fi/LTE
   transition before independent-power short carry and FIELD-020.
3. Reuse FIELD-003/D2/session/replay/D5 tooling for reference-point fix rate,
   TTFF, median/P90 error, continuity/latency and failure accounting. Pose or
   pocket orientation may explain a no-fix hypothesis; causal claims need a
   controlled comparison. Partial riding tracks are not representative P0-LOC.
4. Independently dispatch BASE-010 and CALL-030 only within their bounded
   packets. Feed native-call and measured Camera/power/resource inputs into
   HW-021 and the conditional compliance inquiry. External wait blocks only
   dependants. No new infrastructure or advanced model displaces these consumers.

## Dependency graph

```text
Gemini single-board recovery + actual routes + short carry
    -> D2/reference evidence -> FIELD-020 -> P0-LOC evidence

Codex ALIGN-STATE-010 -> honest compatible rule-state consumer
BASE-010 -> minimum user-controlled private Session endpoint (parallel)

CALL-030 native feasibility -> HW-021 design -> HW-022 prototype
CALL-030 + HW-022 -> CALL-031 native product loop -> P0-CALL evidence
LOC-021 + CALL-031 + OUTBOX-010 -> SOS-010 -> P0-SOS evidence
HW-022 + LOC-021 + CALL-031 + SOS-010 -> PWR-020

FIELD-020 + CALL-031 + SOS-010 + OUTBOX-010 + OPS-004 + PWR-020
 + HW-022 + COMPLIANCE-010 + RF/acoustic/water/security/privacy/NPI
 -> P0-RELEASE-010
```

The arrows name dependencies, not simultaneous dispatch. FIELD-020 and SOS
converge at release review; neither is a global permission gate for independent
work. HW-021 can prepare unrelated design inputs before CALL-030 closes; its
final native-audio/bearer decisions need that evidence. BASE-010 does not
introduce a fourth release Gate; actual private-data ownership/lifecycle must
still satisfy the existing security/privacy assurance requirement.

## Target data path and engineering transition

Device operational state/local spool -> bounded authenticated relay ->
user-controlled Base private history/replay/report -> authorized Guardian.
Cloud reachability/signaling/temporary buffering is separate from that private
endpoint. Each buffer declares purpose, access, quota, expiry, destination,
ACK and deletion/verification semantics. Relay receipt, Base receipt and human
acknowledgement are distinct; preserve the only pending copy until its declared
durable ACK boundary is satisfied.

The current collector/VPS observation and media stores remain an authorized
bounded engineering transition. They do not prove local-first storage,
encryption at rest or complete lifecycle enforcement. Existing authorization
and retention apply. No data is migrated/deleted or service deployed by this
alignment; a future reversible migration requires backup, identity/quantity
reconciliation, rollback and explicit scope.

## Retained safety and evidence invariants

- Device Location/Sensor Policy owns minimum offline operational state;
  source-event time, boot identity, quality and mock lineage survive replay.
- One modem owner; exact authenticated durable ACK; no insecure HTTP fallback
  or disabled certificate/hostname validation to meet a schedule.
- Queue/storage failure does not freeze local aging or recognized SOS feedback.
  Stored, received, call-connected and human-noticed outcomes remain separate.
- Critical event identity/recovery is bounded. Settled events and ended/expired
  calls do not resurrect. ADR-0014's T0/T1 or reviewed equivalent requirements
  remain for the claimed concurrent product recovery; finite single-source
  engineering proof does not globally wait for them.
- Camera cannot improve/veto/delay a Location/SOS conclusion. Consent, default-
  off timed capture, quota and separate capture/save/upload truth remain.
- Build, PC reference, schema, unit test and AT initialization are not hardware,
  audio, field or product evidence. Current-board acoustics need real external
  audio hardware; never substitute a driver log for two-way speech.

Exact running/candidate identities and live successes/failures belong only in
[ACTIVE_BUILD](ACTIVE_BUILD.md), [STATUS](STATUS.md),
[BOARD_MATRIX](../hardware/BOARD_MATRIX.md) and named evidence. The replaced
long runtime chronology is preserved in the
[source archive](../archive/decisions/20260922/README.md); it is not current WIP.
Hardware, SIM/call traffic, capture and deployment require their applicable
bounded operator scope; already authorized actions do not need repeated consent.
