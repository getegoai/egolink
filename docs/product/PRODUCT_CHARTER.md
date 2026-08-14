---
document_status: authoritative
last_verified: 2026-08-14
verified_by: codex
---

# Product Charter

## Authority Boundary

This charter owns the current P0 development promise and non-claims. The
current sales-product direction, screenless modular EgoCore requirements, and
product release gates are defined in [EGO_MASTER_CONTEXT.md](EGO_MASTER_CONTEXT.md)
and ADR-0008. P0 remains an evidence vehicle and does not freeze or prove the
sales-product PCB, enclosure, component slate, VoLTE, camera, ingress, or
endurance behavior.

Ego Link is the wearable/mobile companion node for Project EGO.

The P0 product direction is an AI-assisted active safety locator and companion entry point, not a standalone brain, phone replacement, cloud AI product, or final mass-production wearable.

## Product Role

- Wearable sensing and user confirmation node.
- Low-friction safety interaction surface.
- Remote communication and location evidence entry point.
- Development bridge into the larger EGO ecosystem.

Long-term complex memory, multimodal understanding, and broader coordination belong with Ego Base. During P0, the PC Development Bridge is only a development bridge and observer, not the formal Ego Base and not a product dependency.

## Current Product Promise

P0 should prove that the system can:

- observe or synthesize a safety candidate;
- ask the user whether they are safe;
- capture user confirmation;
- refresh location or communication evidence;
- create a complete replayable safety event record.

Product-demo and field-test evidence must obey
`docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md`: no raw audio/image retention
by default, no unredacted private coordinates in current docs or generated
summaries, no raw Wi-Fi BSSID retention, and no training use without explicit
consent and privacy review.

## Non-Claims

P0 does not claim:

- production fall-detection accuracy;
- real emergency dispatch;
- real calling or SMS workflow;
- final enclosure, battery, power, or wearable ergonomics;
- final model architecture or training readiness.
