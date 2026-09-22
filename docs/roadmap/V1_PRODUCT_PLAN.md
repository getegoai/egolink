---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: founder/codex
---

# EgoLink V1 Product Plan

## Current product baseline

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
records the founder's 9/19 active ego-state/local-first direction and 9/22
implementation instruction. Reliable location is the user-facing entry point;
Ego Base develops in parallel as the minimum user-controlled private endpoint;
native cellular calling is primary and RTC is optional fallback.

| Gate | Required result | Current state |
|---|---|---|
| `P0-LOC` | Reliable representative location, source/age/uncertainty and honest no-fix/degradation | `NOT_RUN` |
| `P0-CALL` | Native outgoing/incoming calls and measured stable two-way audio on representative hardware | `NOT_RUN` |
| `P0-SOS` | Physical SOS, prompt local recognition, durable-event attempt, location/alert and independent native call attempt | `NOT_RUN` |

The three capabilities and product assurance remain necessary for sale.
Screenless people-first modular EgoCore, A0-to-A1, measured 48-hour guard power,
critical-event durability, acoustic/water, RF/body, security/privacy, compliance
and NPI ownership remain. No new fourth capability Gate is introduced.

## Feature and consumer map

| Capability | Reusable assets | Next bounded consumer |
|---|---|---|
| Reliable location | LOC/POLICY/REPLAY reference, device/Guardian assets, existing field/session tools | Gemini single-board recovery/routes/short carry -> D2 reference metrics -> FIELD-020 |
| Honest deterministic ego-state | Existing firmware/reference estimator and DEVICE/store/API/Web path | Codex ALIGN-STATE-010 validity, age, boot/order, mock lineage and explicit compatible contracts; no accuracy claim from a score |
| Native cellular primary | Existing driver source and historical audio bench evidence, each limited to its own scope | CALL-030 feasibility -> HW-021/HW-022 -> CALL-031 representative native loop |
| Physical SOS | Safety Kernel, dormant input/orchestration and OUTBOX/Guardian evidence | Later LOC-021 + OUTBOX-010 + CALL-031 -> SOS-010; current full physical run paused |
| Private data and history | Existing bounded collection/session/replay services | BASE-010 private ingest/persistence/replay/report/lifecycle; no automatic VPS migration |
| Power and health | Device telemetry, PWR-001 tools and named runs | Product PWR-020 on representative integrated LOC/native-CALL/SOS load |
| Guardian explanation | Existing location/SOS and DevBench surfaces | Accurate source/age/unknown/error/call state; polished UX/geofence/contact expansion later |
| Advanced data/AI | Existing DATA/TRAIN/session/label/replay pipeline | Consented real data, offline baseline/comparison, Shadow Mode; signed evaluated model updates later |

Rule-state truth is current engineering acceptance of existing behavior.
Advanced learned L2/L3, general fall/context understanding, Camera AI and full
Base private-model capability are non-blocking growth, not prerequisites
invented by the active-ego-state goal. A SHA-256 digest or local_priority flag
is not encryption, confidence calibration or proof of private storage.

## Current execution and dependencies

The current scheduler is
[FIRST_LAUNCH_EXECUTION](../current/FIRST_LAUNCH_EXECUTION.md), with operational
ownership in [TASK_TREE](../tasks/TASK_TREE.md) and named packets.

- Gemini: P0-CONVERGENCE single-board recovery, actual Wi-Fi/LTE transition,
  short independently powered carry and D2/FIELD-020. Preserve source identity,
  Camera consent and same-file/ID recovery; no AMOLED/PC forwarding dependency.
- Codex: ALIGN-STATE-010 authority/current-image/backlog and bounded rule-state
  truth/contract/API/Web repair completed offline (source `3a0728058`). No acquisition, transport, camera, sensor-policy
  or firmware-profile changes under that packet.
- Queued parallel consumers: CALL-030, BASE-010 and qualified compliance intake.
  HW-021/LOC-021/OPS-004/OUTBOX-010 are parked reusable work, not four hidden
  active writers. Dispatch one integration-sized packet per assigned lane.
- Paused: CALL-020/021 RTC and full SOS in the current field milestone. Their
  evidence is retained; they are not automatically native-call tasks.

```text
single-board recovery/routes/short carry -> D2/FIELD-020 -> P0-LOC evidence
CALL-030 + HW-021 -> HW-022 -> CALL-031 -> P0-CALL evidence
LOC-021 + OUTBOX-010 + CALL-031 -> SOS-010 -> P0-SOS evidence
HW-022 + LOC-021 + CALL-031 + SOS-010 -> PWR-020
FIELD-020 + CALL-031 + SOS-010 + OUTBOX-010 + OPS-004 + PWR-020
 + HW-022 + COMPLIANCE-010 + product assurance -> P0-RELEASE-010
parallel: BASE-010; current rule-state truth; independent design/compliance inputs
```

HW-021 can proceed on unrelated conditional design inputs while native-call
feasibility is pending. Field/SOS later converge at release; neither creates a
global serial permission chain. Shared contracts/files have one owner and a
reviewed integration boundary across isolated worktrees.

## Milestone exit families

### M1: Measured reliable collection and location

One identified candidate preserves failures, event time, ordinary/photo quota,
strict ACK and recovery across declared routes. Short independent-power carry
precedes representative FIELD-020. D2 records fix rate, TTFF, median/P90
reference error and uncertainty/coverage limits; D5 consumes that real evidence.
PWR-001 development measurements inform but do not replace PWR-020's 48-hour
representative guard result. A partial ride or one fix cannot pass P0-LOC.

### M2: Native voice and physical safety

CALL-030 establishes the exact modem/firmware/operator/audio design inputs;
CALL-031 on HW-022 proves native outgoing/incoming setup, answer/cancel/hangup,
stable two-way audio, failure/recovery, authorization and concurrent power/RF.
AT ready, dial submitted, connected and heard are distinct. Skip acoustics on
an unprovided microphone/speaker path; an RTC/PC loop cannot substitute.

SOS recognizes input immediately, attempts durable recording and independently
starts priority location, Guardian alert and native call. Storage or network
failure is visible; no model, fresh-GNSS wait, Base or RTC can suppress local
help. Recovery cannot resurrect ended calls or settled alerts. Human
acknowledgement remains distinct from transport/phone connection.

### M3: Private endpoint and honest state

BASE-010 first proves private Session receipt/persistence/replay/report and
retention/export/deletion with authorized or synthetic data. Cloud has only
reachability/signaling/bounded temporary relay responsibilities; the existing
VPS collector is an authorized engineering transition, not completed local-
first storage or encryption. Migration requires backup, identity/ACK/retry
reconciliation, recovery and separately scoped execution; no existing data is
erased by this plan. Complete Base AI remains later growth.

Current rule-state engineering exit includes explicit unknown/invalid/stale/
mock behavior, canonical projection compatibility, boot/order/replay and real
Web rendering regression. Learned-model accuracy and general safety claims
need labelled evaluation and do not follow from green unit tests.

### M4: Reviewable A0 and China readiness

HW-021 exact candidates, schematic/BOM/net/power/RF/audio/Camera/mechanical
constraints and independent review feed HW-022. Current boards are evidence
vehicles, not a frozen product BOM. Native cellular primary replaces the old
reserve-only requirement; G0V-VOLTE-RESERVE retains historical evidence value.
COMPLIANCE-010 needs named qualified written scope/configuration conclusions;
a NOT_SENT inquiry is not waiting_external. No purchase/fabrication follows
from this plan.

### M5: EVT, DVT, certification and pilot

Representative A1 hardware re-runs applicable location/native-CALL/SOS and
power/reliability/water/acoustic/RF/privacy/compliance/NPI evidence. Enclosure,
body loading, mounting, occlusion acquisition/recovery and actual battery are
part of acceptance. No product claim is inherited from a development build.

## Retained backlog and non-goals

Old numeric waves, DATA/TRAIN tooling inventories and RTC-first dependency
chains are retained in the [exact source snapshot](../archive/decisions/20260922/README.md),
original done/active packets and task tree; they do not schedule current WIP.
MODEL-001/PROD-001 remain paused references until a bounded successor is needed.
MODEL-001 measurements remain pending: runtime RAM/latency, inference energy
and comparable MCU evidence cannot be inferred from static footprint or builds.
Measured deterministic Safety Kernel resource/power fit remains a hardware
selection gate; advanced-model benchmarks do not block the three P0 capability
Gates. Current rule-state truth still requires the engineering acceptance above.
History/geofence UX, learned mobility/known-place models, richer assistants,
LoRa/LE Audio and scenario variants remain later evidence-driven work.

No screen/touch product requirement, continuous raw audio/video, unconsented
training, self-operated public PSTN/SIP gateway, public emergency dispatch or
overseas launch scope is introduced. Native telephone contact with authorized
contacts is now core; its implementation remains unverified until measured.
R0-R4/KR tools remain reusable evidence families, not substitute release Gates.
