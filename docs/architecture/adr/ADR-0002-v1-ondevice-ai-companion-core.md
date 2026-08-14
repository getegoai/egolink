---
document_status: authoritative
last_verified: 2026-08-14
verified_by: codex
---

# ADR-0002: On-Device AI Companion Is the V1 Core; Edge-Cloud Hybrid Intelligence

- Status: accepted
- Date: 2026-07-03
- Decision owner: founder
- Drafted by: claude (project director role)

## Correction History

The first draft of this ADR (same day, never committed) recorded a
"traditional-first, server-side intelligence, on-device ML deferred to V2"
strategy. The founder explicitly retracted that statement on 2026-07-03:
**on-device AI capability — real-time interaction with the user and proactive
AI services — is one of the product's core differentiators and cannot be
deferred.** This ADR records the corrected decision.

## 2026-08-14 ADR-0008 Integration

[ADR-0008](ADR-0008-egolink-core-product-direction-reset.md) changes the current
sales product from the superseded display-led V1 Pro watch to a screenless
modular EgoLink Core and defines EgoBase as the intended user-controlled private
compute and long-term-memory tier. This integration note preserves the accepted
on-device AI requirement while aligning interaction and compute placement with
that newer product direction. It does not claim that EgoBase or the production
hardware already exists.

### Historical 2026-07-03 Decision Text

The accepted 2026-07-03 wording is preserved here for traceability. It placed
the confirmation loop on `display/touch/audio` and assigned heavy reasoning,
language-level services, location belief, model training and fleet learning to
the VPS. It also described device sensing as `always-on`. ADR-0008 partially
supersedes only those interaction-channel, compute-placement and power-wording
clauses: the current product is screenless, EgoBase is the intended private
heavy-compute/long-term-memory tier, the VPS is bounded and transitional, and
always-available safety does not mean full-rate continuous capture. The core
2026-07-03 decision that on-device AI is a launch-critical differentiator
remains accepted.

Original clauses:

> 1. On-device AI companion capability is a V1 launch requirement. The
> wearable runs latency-critical, always-available intelligence locally:
> motion anomaly candidate detection, the user confirmation/interaction loop
> (`display/touch/audio`), and proactive check-in behavior.
>
> 2. Intelligence is split edge-cloud, by latency and weight. Device-side:
> always-on sensing, lightweight models, real-time interaction and local safety
> decisions. Cloud-side (VPS): heavy reasoning and language-level companion
> services over LTE, location belief, model training and fleet learning.

## Context

- The product's identity is an "AI active-guardian locator": the wearable
  itself must sense, interact, and act in real time, not merely upload data
  for a cloud to interpret.
- The original migration route (`docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`,
  P1 stage) already placed MotionNet/AudioGate on the wearable node; this
  decision confirms that route rather than replacing it.
- Model maturity depends on the M1 data foundation, labeled real samples, and
  formal IMU product acceptance — so the on-device model track must be
  actively driven inside V1, not treated as a research sidetrack.
- The VPS Message Hub is already deployed and operated as a real production
  service during development.
- SIM7670G is a development-only module; a China Mobile 4G module is under
  business evaluation, and production module/MCU selection is gated by the
  PROD-001 mass-production requirements definition.

## Decision (as amended by ADR-0008 on 2026-08-14)

1. **On-device AI companion capability is a V1 launch requirement.** The
   wearable runs latency-critical, always-available intelligence locally:
   motion anomaly candidate detection (MotionNet track), the user
   confirmation/interaction loop (physical controls, audio, haptics and status
   light), and proactive check-in behavior. Historical development-board
   display/touch evidence remains useful but is not a current product
   requirement. Losing LTE must degrade, not eliminate, the AI experience.
2. **Intelligence is split edge-cloud, by latency and weight.** Device-side:
   low-power always-available wake and safety paths, duty-cycled sensing,
   lightweight models, real-time interaction and local safety decisions.
   "Always available" does not mean continuous full-rate sensor capture.
   EgoBase is the intended user-controlled tier for heavy reasoning, long-term
   personal memory, consented training, model evaluation and signed delivery.
   During P0 and migration, the VPS may provide transport, bounded temporary
   storage, location-belief services and explicitly authorized enhancement or
   training tools, but it is not a safety single point or the default long-term
   raw-data store. The split is an engineering boundary, not a fragmented user
   experience.
3. **The on-device model track is on the V1 critical path.** M1 data
   foundation completion (session recorder, labeling loop, collection
   protocol), formal IMU product acceptance, MotionNet v0.1 training, and a
   model footprint assessment (RAM/flash/latency/power per candidate MCU) are
   V1 blockers, scheduled and resourced as such.
4. **The data flywheel is the model-improvement mechanism from day one.**
   Field-test and production devices feed consented, privacy-classed
   sessions; guardian/user confirmations produce labels; models are retrained
   and shipped back via server-side updates and device OTA. Whether the
   learning progress is surfaced to users is a product presentation choice,
   TBD(founder), not an architecture requirement.
5. **Reliability work is unchanged and remains the foundation.** Transport,
   power, GNSS acceptance, and VPS operations gates (V1-M1) precede and
   carry the AI track; an AI companion on an unreliable device is not a
   product.
6. **Production hardware selection must budget for on-device AI.** The
   PROD-001 MCU evaluation treats inference capability (RAM/flash headroom,
   vector/NPU support, sleep-vs-inference power) as a first-class selection
   criterion, informed by the model footprint assessment.
7. **Generative or language models are advisory in safety-critical paths.**
   They must not be the sole authorizer for a physical SOS, a confirmed user
   request, a no-response timeout escalation, or another mandatory safety
   action. Deterministic policy and auditable evidence remain authoritative.
8. **Workflow decision (unchanged from the first draft):** the AutoDev
   autonomous loop and Dual Codex workflow are retired;
   `docs/development/DIRECTOR_WORKFLOW.md` is the active execution workflow.
9. **`docs/roadmap/V1_PRODUCT_PLAN.md` is the authoritative product
   sequencing document**, aligned with the on-device track of
   `P0_TO_PRODUCT_MIGRATION.md`.

## Consequences

- Firmware/platform effort covers both reliability (transport, power, GNSS)
  and the on-device inference/interaction runtime; the dual-board split
  (wearable node = sensing/interaction, connectivity node = LTE/GNSS) stays
  the development vehicle until PROD-001 converges hardware.
- FT-1 (first wearable field-test build) remains transport/power/GNSS
  focused and doubles as the M1 data-collection vehicle: every field run
  produces training-candidate sessions.
- Microphone and interaction hardware gaps (BOARD_MATRIX: mic
  `missing_or_unknown`) become V1-relevant procurement/validation items, not
  deferred concerns.
- Fall-detection and proactive-alert quality must still be honestly labeled
  (experimental until false-positive rates are measured on real data); the
  on-device AI claim does not suspend the repository's non-claim evidence
  rules.
