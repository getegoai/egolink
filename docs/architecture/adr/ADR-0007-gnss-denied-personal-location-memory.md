---
document_status: proposed
last_verified: 2026-08-14
verified_by: codex
owner: founder
---

# ADR-0007: GNSS-Denied Personal Location Memory

- Status: proposed
- Date: 2026-08-12
- Deciders: founder and codex

## Context

GNSS can be unavailable or unreliable near the body, inside a bag or building,
in urban canyons, and around RF or mechanical interference. Longer GNSS waits
cannot guarantee a fix and consume power. EgoLink must remain useful without
presenting an old or inferred coordinate as current truth.

EALE-P0 already defines `Fine`, `Coarse`, `Predicted`, and `Unknown` beliefs;
ADR-0003 separates active sensor scheduling from those beliefs; ADR-0004 keeps
P0 fusion rule/statistics based and personal memory local by default. This
proposed ADR combines those decisions into a GNSS-denied product strategy
without changing their contracts; founder review is required before it becomes
an accepted architecture decision.

ADR-0008 supersedes the prior Air780EGH/nRF54LM20B/no-third-radio V1 Pro
topology and reopens the screenless EgoLink Core A0/A1 radio decision.
ESP32-S3 Wi-Fi remains useful in the current engineering vehicle, but
production Wi-Fi/BLE parts, antenna topology, power, coexistence, privacy, and
behavior are `unverified`; production location behavior must not silently
depend on either one. The proposed memory strategy must work with GNSS,
cellular evidence, motion/time context, and explicit uncertainty even when no
optional proximity anchor is available.

## Proposed Decision

Adopt the following location pipeline:

```text
trusted anchors
-> personal place and route memory
-> current cell/BLE/motion/barometer/time evidence
-> bounded Top-K hypotheses
-> Fine | Coarse | Predicted | Unknown belief
-> uncertainty-driven active sensing
```

### Precise anchors, coarse anchors, and personal memory

- Only quality-gated direct positioning evidence may establish a `Fine`
  coordinate anchor. An explicitly confirmed bounded place, or optional
  future EgoBase/guardian-phone BLE evidence with authenticated identity,
  fresh observation time, and proximity bounds, may support `Coarse`; it
  cannot silently promote itself to coordinate precision. EgoBase is not yet
  built and the guardian phone app is outside P0, so neither is a V1 runtime
  dependency until separately implemented and verified.
- Every anchor records source, time, quality, scope, and lineage.
- Repeated anchored observations may form personal place nodes and route
  segments. Cell transitions, privacy-reviewed radio fingerprints, motion,
  barometric change, time pattern, and travel duration are supporting
  evidence, not independent truth.
- A single cell observation, IMU window, time pattern, or unverified radio
  scan cannot create exact coordinates or a trusted place.
- Product long-term memory lives on the device or local EgoBase by default.
  Server retention requires explicit consent, purpose limitation,
  minimization, deletion semantics, and a defined retention period.

### Bounded hypotheses and public beliefs

- The estimator may retain a small ranked set of hypotheses such as
  `place_A`, `place_B`, `route_A_B_segment_2`, or `unresolved`. Opaque local
  identifiers are the default. Semantic names require explicit owner or
  guardian labelling and access control. Every
  hypothesis carries score, age, bounded area or place identity, reasons, and
  evidence references.
- A Top-K score is an internal rank, not a calibrated probability, unless a
  later calibration task proves that interpretation.
- Top-K is internal evidence bookkeeping, not a list of user-facing precise
  dots. The public result remains one of EALE's four states:
  - `Fine`: fresh quality-gated direct positioning evidence;
  - `Coarse`: a known place or bounded area supported by memory;
  - `Predicted`: a recent trusted anchor or route hypothesis with explicit
    age and expanding uncertainty;
  - `Unknown`: insufficient, stale, or conflicting evidence.
- Belief uncertainty must grow with time and motion. A stale coordinate must
  never be rendered as current location; transition to `Unknown` is valid.

### Active sensing

- The ADR-0003 scheduler uses belief uncertainty, safety risk, motion, power,
  and rule-derived GNSS-bad context to choose bounded GNSS attempts, optional
  verified BLE scans, cellular observations, upload cadence, or a low-power
  hold.
- Known poor acquisition contexts should avoid repeated identical GNSS work.
  Emergency state `L4` may spend more power and collect denser evidence.
- Sensing decisions and belief outputs remain separate and independently
  explainable.

### Rules first, AI as a constrained improvement

- P0 starts with explainable lookup, clustering, transition statistics,
  thresholds, conservative decay, and optional sequence decoding. It does not
  train a model merely to label the system as AI.
- ADR-0004 still approves only IMU motion state as a learned-model candidate;
  it must remain in shadow mode until its existing gates pass. Source
  reliability, GNSS acquisition probability, and sensing-value models are
  post-P0 research ideas only. They require a later founder-reviewed ADR and
  task before they may affect belief or scheduling policy.
- Learned components do not directly regress latitude/longitude. A future
  learned known-place or route-progress component requires a separate task and
  founder-reviewed decision if it changes the ADR-0004 P0 boundary.

### Training and evaluation boundary

- Training candidates require explicit consent, privacy review, tamper-evident
  lineage metadata for retained consented evidence, labels,
  participant/household/session/device/place/time-block split controls, and a
  model or generator version. Deletion or consent revocation removes personal
  payloads and invalidates downstream training eligibility.
- Synthetic data can test tooling but cannot establish product performance.
- Evaluation must include GNSS-masked replay over real anchored sessions and
  measure belief availability, true-position coverage by the displayed
  radius/area, known-place false positives, time to `Unknown`, and sensing
  energy. Rendering an old point as current has a zero-tolerance gate.

## Consequences

- EgoLink can give useful place, area, or route-progress evidence during GNSS
  denial without pretending it has a precise fix.
- Personalization becomes a location asset while privacy and local ownership
  stay part of the architecture.
- The ESP32 Wi-Fi path may validate algorithms and collect consented evidence,
  but V1 release behavior must work with GNSS, cellular memory, QMI8658 motion,
  BMP390 context, and explicit uncertainty. Optional BLE anchors may improve
  `Coarse` evidence only after their product path is implemented and verified;
  production Wi-Fi likewise requires later verification and approval.
- PCB, antenna, enclosure, worn-state, and bag-state RF validation remain
  necessary. Software resilience reduces dependence on GNSS; it does not make
  antenna performance optional.

## Links

- `../../development/LOCATION_ENGINE.md`
- `ADR-0003-low-power-location-state-machine.md`
- `ADR-0004-p0-rule-location-and-transitional-vps-memory.md`
- `ADR-0008-egolink-core-product-direction-reset.md`
- `../../roadmap/V1_PRODUCT_PLAN.md`
- `../../product/EGO_MASTER_CONTEXT.md`
