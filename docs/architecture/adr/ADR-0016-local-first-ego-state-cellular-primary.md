---
document_status: accepted_decision
decision_updated: 2026-09-22
reviewed_at: 2026-09-22
authority_basis: founder_decision_20260919_and_implementation_instruction_20260922
implementation_status: in_progress
---

# ADR-0016: Local-First Ego-State and Native Cellular Primary Calling

- Status: accepted
- Decision date: 2026-09-19; migration authorized: 2026-09-22
- Decision owner: founder
- Scope: product roles, communications priority, private-data destination and current engineering acceptance

## Authority and conflict resolution

The founder's [2026-09-19 North Star decision](../../product/NORTH_STAR.md)
defines active ego-state estimation, strong privacy/local-first operation,
parallel Ego Base development and native cellular primary calling. On
2026-09-22 the founder explicitly assigned Codex to complete that decision
alignment and rule-state truth repair under
[ALIGN-STATE-010](../../tasks/done/ALIGN-STATE-010_DECISION_AND_STATE_TRUTH.md),
while Gemini owns single-board recovery, route switching and D2/FIELD work.
This accepted ADR records those existing instructions; acceptance is not
inferred from an automated test, a code change or an agent's recommendation.

The conflict was concrete: ADR-0011/0012 selected RTC first and native voice
reserve, while current plans deferred Ego Base and treated VPS storage as the
working endpoint. The following replacements resolve that conflict explicitly.
Exact pre-edit sources and the clause migration map are preserved in the
[named archive](../../archive/decisions/20260922/README.md).

## 1. Product goal and unchanged release structure

EgoLink is a wearable active ego-state estimation and guarding system.
Reliable location is its most direct user-facing entry point and evidence
anchor. Device state, observations, inferences and user outcomes remain
distinct; an experimental classification is not a proven safety conclusion.

| Gate | Current acceptance meaning | Current state |
|---|---|---|
| `P0-LOC` | Representative reliable location with source, age, uncertainty and honest degradation | `NOT_RUN` |
| `P0-CALL` | Authorized native cellular outgoing/incoming calls and measured stable two-way audio on representative integrated hardware through CALL-030/HW-022/CALL-031 | `NOT_RUN` |
| `P0-SOS` | Physical SOS, immediate recognized-input feedback, durable-event attempt, location escalation, Guardian alert and independent primary cellular call attempt | `NOT_RUN` |

All three must pass, together with power, reliability, RF, acoustics/water,
security/privacy, China compliance and NPI assurance. Screenless modular
EgoCore, people-first use, A0-to-A1 development and measured 48-hour guard
endurance remain. Camera and Ego Base are not fourth capability Gates.
Advanced learned L2/L3 models, broad context understanding and complete Base
private-AI capability are not new mandatory first-launch gates.

## 2. Native cellular primary, RTC optional fallback

The primary route is device -> supported cellular voice network -> authorized
contact, in both call directions, using the exact modem/firmware/operator
combination proven by evidence. Native VoLTE or another supported voice mode
must be verified; this decision does not imply a CS fallback exists on LTE-only
hardware or a particular operator. RTC over LTE data/Guardian remains an
optional auxiliary route and cannot substitute for primary P0-CALL acceptance.
No self-operated public PSTN/SIP gateway or public emergency-dispatch service
is introduced. Ordinary authorized cellular telephone contact is in scope.

Registration, AT driver initialization, dialing, ringing, connection and
audible two-way speech are separate results. P0-CALL requires incoming and
outgoing setup, answer/cancel/hangup, accurate failure/termination state,
bounded recovery, access policy and measured audio/power/RF/privacy behavior
without a PC/USB runtime dependency. `G0V-VOLTE-RESERVE` remains a historical
design/evidence label; reserve viability no longer satisfies the primary call
obligation. Existing CALL-020/021 RTC packets stay paused until explicitly
rescheduled; they are not silently renamed as native-call implementations.

The current connectivity board has no accepted microphone/speaker application
path. Skip its acoustic loop without the required external audio hardware.
Do not infer a working call from its linked cellular AT component. Physical
SOS uses an independent native-call attempt; fresh GNSS, AI, Base, RTC or
cloud availability cannot veto local recognition or the allowed help attempts.

## 3. Private endpoint and bounded transition

Develop Ego Base in parallel as the user-controlled physical endpoint for
private history and the heavier computation that cannot fit on the wearable.
Its first bounded engineering slice, BASE-010, is authenticated ingest of an authorized
or synthetic Session, private persistence, event-time replay/reporting and
explicit retention/export/deletion behavior. Full private models, training
and multimodal inference remain later increments. A development PC may host
that experiment, but is not thereby a finished Base product or a wearable
field-runtime dependency.

Target responsibilities are device operational state and bounded local spool;
Base private history/replay/derived reports; cloud reachability, signaling and
bounded forwarding. A cloud buffer must declare purpose, permitted data,
access owner, byte/count quota, retention/expiry, delivery destination and
deletion/verification behavior. Cloud receipt, private endpoint receipt and
human acknowledgement are separate. Do not delete the only pending copy
before the declared durable ACK boundary; changes to that boundary require a
reviewed contract and recovery migration.

The existing collector/VPS database and private media service are an authorized
bounded engineering transition, not evidence that local-first storage or
encryption at rest is implemented. Existing consent, retention and access
limits continue; missing lifecycle controls remain named gaps. This ADR
authorizes no production deployment, credential change, private-data migration
or deletion. Prepare a separate reversible migration with verified backup,
identity reconciliation and recovery before changing the endpoint or erasing
existing data. SHA-256 integrity values and `local_priority` labels do not
prove encryption, user-controlled storage or data-policy enforcement.

## 4. Rule-state truth is current engineering acceptance

The implemented deterministic ego-state path is now an engineering consumer
to validate, not merely future L3 work. Its firmware, reference estimator,
DEVICE projection, canonical contracts, storage/API and Web must agree on
validity, source identity/time, mock lineage and unknown/unsupported results.
Missing, stale, future, partial or invalid evidence must not become confident
normal, stationary, worn, safe or precise-location claims. Boot/order/replay
rules must prevent stale state resurrection; restored state retains its age.

Use explicit versioned projection when compact device telemetry differs from
the canonical estimate. Reject or expose invalid payloads without inventing a
valid projection. Test the actual UI rendering and invalid-input paths, not
only source strings. Scores remain experimental until calibrated against
labelled evidence; hashes prove only their specified integrity scope.
Rule outputs cannot initiate or veto unapproved safety actions. This is
truthfulness of existing behavior, not a new learned-model release Gate.

## 5. Execution and retained invariants

Gemini continues ADR-0015's single-board recovery/actual Wi-Fi-LTE transition,
short independent-power carry and D2/FIELD-020 evidence. Codex owns decision,
current-state/backlog alignment and bounded ego-state truth/contracts.
Shared acquisition, modem, camera, transport, sensor-policy and profile files
remain under explicit ownership; state packaging changes are integrated at a
reviewed boundary. HW-021 and COMPLIANCE-010 retain the new native-call requirements. CALL-030
feasibility feeds HW-021/HW-022; CALL-031 owns the representative native loop
after CALL-030 and HW-022, and supplies the later SOS/PWR/release consumers.
Old RTC dependency edges must not be dispatched as primary-call requirements.

ADR-0010 source-event time and bounded persistence, ADR-0012 device operational
ownership, and ADR-0014 local degradation, exact authenticated ACK, one modem
owner, prompt SOS recognition and no resurrection of ended calls remain.
ADR-0015 single-board/Camera scope remains; its VPS endpoint is transitional
under section 3. CALL-020/021 and full SOS remain paused in the field milestone.

## Partial supersession and validation

| Prior clause | Replacement / retained boundary |
|---|---|
| ADR-0011 sections 3-4/12; ADR-0012 sections 5/7: RTC primary and native-voice exclusion | Section 2: primary native cellular, optional RTC; no self-operated public gateway; three Gate names retained |
| ADR-0011 native reserve; derived hardware/roadmap RTC prerequisites | Native voice is part of P0-CALL; reserve evidence retained but insufficient; exact SKU/operator/audio remain unverified |
| ADR-0014 first-launch LTE-data wording and immediate CALL schedule | Section 2 plus current lane ownership; all timing, durability, degraded SOS and recovery invariants retained |
| ADR-0015 scope freeze where it would exclude current rule-state truth work | Section 4 permits bounded validation/repair; single-board field scope and CALL/SOS pause remain |
| VPS as long-term endpoint; Base-only-later plans | Section 3: parallel minimal Base endpoint, explicit bounded cloud transition; no automatic data deletion |

Before acceptance of implementation, run focused behavioral regressions,
repository verification and context lint. No document edit advances evidence
dates or a P0 Gate. Hardware, SIM/call traffic, real-scene capture and deployment
continue under their applicable explicit bounded operator scope.
