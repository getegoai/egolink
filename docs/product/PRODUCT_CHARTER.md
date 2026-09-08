---
document_status: authoritative
decision_updated: 2026-09-05
last_verified: 2026-08-23
verified_by: codex
---

# Product Charter

## Authority Boundary

This charter owns the sellable first-generation P0 promise and non-claims.
The screenless modular EgoCore requirements and release evidence remain defined
in [EGO_MASTER_CONTEXT.md](EGO_MASTER_CONTEXT.md), ADR-0008 and ADR-0011.
Current development boards are evidence vehicles for this P0; they do not
freeze or prove the sales-product PCB, enclosure, BOM, ingress, endurance, RF,
audio, waterproofing, or compliance behavior.

Ego Link is the wearable/mobile companion node for Project EGO.

The P0 product is a reliable safety locator and family-contact device. It is
not a standalone brain, phone replacement, cloud-AI product, general camera-AI
platform, or finished mass-production design.

## Product Role

- Wearable sensing and user confirmation node.
- Low-friction safety interaction surface.
- Remote communication and location evidence entry point.
- Development bridge into the larger EGO ecosystem.

Long-term complex memory, multimodal understanding, and broader coordination belong with Ego Base. During P0, the PC Development Bridge is only a development bridge and observer, not the formal Ego Base and not a product dependency.

## Current Product Promise

P0 must pass all three user-facing capability Gates:

- `P0-LOC`: a guardian opens the minimum Guardian client and sees the best
  current explainable location, update age, source, confidence and uncertainty;
- `P0-CALL`: the guardian can call the device and the device can initiate a
  stable two-way full-duplex Ego Call over LTE data;
- `P0-SOS`: a qualified long physical-button press immediately signals input
  recognition, attempts durable SOS recording, location escalation, Guardian
  notification and Ego Call with independent honest storage/delivery/session
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

[ADR-0014](../architecture/adr/ADR-0014-runtime-convergence.md) and
[P0-CONVERGENCE-20260905](../tasks/active/P0-CONVERGENCE-20260905.md) prioritize
bounded device Location -> authenticated secure transport -> Guardian, with
real bidirectional CALL/embedded-bearer work in parallel, then physical SOS and
recovery. T0/T1 do not globally block isolated S or finite single-source live
proof; concurrent-ingress/reboot commitments remain required for the product.

Local state advances independently from outbound persistence failure, with
explicit degradation. Recognized input, stored event, server receipt, terminal
notice and human acknowledgement are never interchangeable. Healthy storage must durably retain the original SOS event; storage failure
counts as reliability degradation and cannot pass the normal durable-event
acceptance. Normal delivery keeps write-before-send and exact authenticated ACK.
Recovery does not reopen
ended calls. These decisions do not advance `P0-LOC`, `P0-CALL` or `P0-SOS`
from `NOT_RUN`, and do not authorize real hardware/network experiments.

## Non-Claims

P0 does not claim:

- production fall/anomaly/context-understanding accuracy;
- AI location fusion or learned Sensor Policy readiness;
- camera understanding or camera-dependent safety;
- public emergency dispatch, PSTN, SMS, or native VoLTE;
- polished complete consumer App, multi-party calling, AI voice or recording;
- final enclosure, battery life, power, RF, waterproofing, acoustics, BOM,
  compliance or wearable ergonomics before their measured Gates pass.
