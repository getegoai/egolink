---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
---

# Product Charter

## Authority Boundary

This charter owns the sellable first-generation P0 promise and non-claims.
The screenless modular EgoCore requirements and release evidence remain defined
in [EGO_MASTER_CONTEXT.md](EGO_MASTER_CONTEXT.md), ADR-0008 and [ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md).
Current development boards are evidence vehicles for this P0; they do not
freeze or prove the sales-product PCB, enclosure, BOM, ingress, endurance, RF,
audio, waterproofing, or compliance behavior.

Ego Link is the wearable/mobile companion node for Project EGO.

The P0 product is a wearable active ego-state and family-guarding device, with
reliable location as the direct user entry point. It is
not a standalone brain, phone replacement, cloud-AI product, general camera-AI
platform, or finished mass-production design.

## Product Role

- Wearable sensing and user confirmation node.
- Low-friction safety interaction surface.
- Remote communication and location evidence entry point.
- Development bridge into the larger EGO ecosystem.

Develop the minimum user-controlled Ego Base endpoint in parallel under BASE-010:
authorized Session ingest, private persistence, replay/report and lifecycle.
Full private AI remains later growth, not a fourth first-launch Gate. A PC may
host an engineering experiment but is not thereby the formal Base or a wearable
field-runtime dependency. The device safety plane works without Base/cloud/AI.

## Current Product Promise

P0 must pass all three user-facing capability Gates:

- `P0-LOC`: a guardian opens the minimum Guardian client and sees the best
  current explainable location, update age, source, confidence and uncertainty;
- `P0-CALL`: the guardian can call the device and the device can initiate a
  stable two-way full-duplex native cellular Ego Call on the exact supported
  modem/firmware/operator and integrated audio hardware; RTC is optional fallback;
- `P0-SOS`: a qualified long physical-button press immediately signals input
  recognition, attempts durable SOS recording, location escalation, Guardian
  notification and an independent primary cellular call attempt with honest storage/delivery/session
  states. Storage failure must be visible and cannot silence local help.

The minimum first-generation user story is therefore: know where the device
is, speak in either direction, and press SOS to establish location plus human
contact. A P0 release is forbidden unless all three Gates are `PASS`.

Product-demo and field-test evidence must obey
`docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md`: no raw audio/image retention
by default, no unredacted private coordinates in current docs or generated
summaries, no raw Wi-Fi BSSID retention, and no training use without explicit
consent and privacy review.

## Current implementation unit

[ADR-0015](../architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md)
and [P0-CONVERGENCE-20260905](../tasks/active/P0-CONVERGENCE-20260905.md)
retain Gemini's independently operating SIM7670G evidence work under ADR-0016:
Location and raw observations, bounded persistent backlog, authorized still
capture, actual Wi-Fi/LTE ordinary-observation upload and controlled transition,
real-LTE photo upload, bounded authorized engineering VPS storage and existing-Web viewing, followed by
FIELD-020. AMOLED and board-to-board forwarding are not dependencies of this
A-line evidence run. CALL-020, CALL-021 and full physical SOS are paused for
separate follow-up; their evidence remains. CALL-030 native feasibility feeds
HW-022, then CALL-031 owns the representative native product loop; old RTC
packets do not substitute for it.

Camera is a delivery requirement for this engineering milestone, not a fourth
sellable-P0 Gate and not a Camera-AI or Camera-dependent safety promise.
[ADR-0014](../architecture/adr/ADR-0014-runtime-convergence.md) still governs
the retained local-failure, timing, ownership and recovery invariants where the
newer decision does not replace execution order. T0/T1 do not globally block
isolated S or finite single-source live proof; concurrent-ingress/reboot
commitments remain required for the product.

Local state advances independently from outbound persistence failure, with
explicit degradation. Recognized input, stored event, server receipt, terminal
notice and human acknowledgement are never interchangeable. Healthy storage must durably retain the original SOS event; storage failure
counts as reliability degradation and cannot pass the normal durable-event
acceptance. Normal delivery keeps write-before-send and exact authenticated ACK.
Recovery does not reopen
ended calls. These decisions do not advance `P0-LOC`, `P0-CALL` or `P0-SOS`
from `NOT_RUN`, and do not authorize real hardware/network experiments.

Codex owns ALIGN-STATE-010 decision/current-state/backlog and existing rule-state
truth repair. Missing/stale/future/mock/invalid input must not create confident
normal state; DEVICE/canonical/API/Web projections require explicit compatible
contracts and regression. This is engineering acceptance, not demonstrated
activity/fall accuracy. Gemini recovery/route/D2/FIELD work continues independently.

The target private endpoint is Ego Base; cloud buffers declare purpose, quota,
expiry, access, destination and ACK/deletion behavior. Existing VPS storage does
not prove local-first implementation or encryption. This alignment authorizes no
private-data migration/deletion; preserve existing consent and retention limits.

## Non-Claims

P0 does not claim:

- production fall/anomaly/context-understanding accuracy;
- AI location fusion or learned Sensor Policy readiness;
- camera understanding or camera-dependent safety;
- public emergency dispatch, a self-operated public PSTN/SIP gateway, or SMS;
- native voice availability, audio quality or operator compatibility before measured P0-CALL evidence;
- polished complete consumer App, multi-party calling, AI voice or recording;
- final enclosure, battery life, power, RF, waterproofing, acoustics, BOM,
  compliance or wearable ergonomics before their measured Gates pass.
