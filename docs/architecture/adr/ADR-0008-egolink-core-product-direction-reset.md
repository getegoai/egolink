---
document_status: authoritative
last_verified: 2026-08-23
verified_by: codex
owner: founder
---

# ADR-0008: Adopt the Screenless Modular EgoLink Core Product Direction

- Status: accepted
- Date: 2026-08-14
- Decision owner: founder
- Scope: current sales-product direction; no current-board or protocol change

## 2026-08-23 ADR-0011 / ADR-0012 Integration

[ADR-0011](ADR-0011-first-launch-reliable-location-ego-call-sos.md) and
[ADR-0012](ADR-0012-p0-productization-sprint-1.md) supersede this ADR's first-
launch sequencing where it made native VoLTE, camera or broad on-device AI a
release requirement. The sellable P0 is Reliable Location + LTE-data Ego Call
+ physical SOS. Native VoLTE is a hardware reserve; camera is an optional
experimental still interface; anomaly, proactive check-in and context models
are non-blocking L2/L3 work. The screenless modular EgoCore direction, audio as
core hardware, product-owned safety state, privacy, A0-to-A1 method and measured
48-hour target remain accepted. Historical clauses and the supersession matrix
below are retained as the 2026-08-14 decision record, not current Sprint 1
dispatch authority.

## Context

The founder supplied the v2.0 draft at `docs/EGO_MASTER_CONTEXT.md` as the
updated definition for the current product and explicitly directed that it
become the project baseline. It was normalized and evidence-corrected as v2.1
at `docs/product/EGO_MASTER_CONTEXT.md` without changing the founder's product
pivot. Its direction differs materially from the V1 Pro watch path accepted in
ADR-0005 and ADR-0006:

- the product is a screenless waterproof functional core, carried by an
  interchangeable cradle and cosmetic skin rather than a display-led watch;
- native bidirectional VoLTE is a first-generation product requirement instead
  of an ordinary-phone non-goal;
- an event-triggered environment camera is part of the first-generation sensor
  requirement rather than omitted from the product;
- the first custom board is a deliberately debuggable architecture A0 before
  product-size compression, not a direct four-layer form-factor EVT board.

The supplied draft also named a new component slate. Those names have not yet
passed official-document, sample, model-footprint, power, RF, acoustic,
sourcing, lifecycle, or hardware validation gates. Accepting the product pivot
does not make those candidate capabilities verified and does not freeze a
production BOM.

The current ESP32-S3 + SIM7670G development board has real D2/D5/FIELD evidence
and active work. It remains the software, data, transport, and fault-injection
vehicle while the product PCB, enclosure, and component path proceed in
parallel.

## Decision

1. `docs/product/EGO_MASTER_CONTEXT.md` is the authoritative entry point for
   the current sales-product direction, system roles, first-generation product
   requirements, modular EgoCore architecture, release gates, and NPI asset
   ownership.
2. The current sales product requires a screenless, independently sealed and
   waterproof, attachment-form-neutral `EgoCore`, release-gated `Cradle`
   attachments and optional non-structural `EgoSkin` shells. Waterproofing is a
   requirement, not a verified capability. Each Cradle must pass its load,
   drop, detachment and carry-form gates before release. People-first active
   safety is the launch scenario; a pet product is a later platform variant.
3. Native bidirectional VoLTE across the three target mainland China operators,
   physical SOS, 4G data, resilient positioning,
   two logical microphone paths, speaker, six-axis motion sensing,
   event-triggered camera capture, local TinyML, bounded event storage,
   vibration/status feedback, battery management, and capless USB-C are
   first-generation product requirements. None is a verified product
   capability until its named release gate passes.
4. The on-device AI companion remains a V1/core-product differentiator per
   ADR-0002. Minimal local candidate detection, confirmation/interaction, and
   proactive check-in stay on the first-generation path; richer general
   assistant behavior can follow later.
5. Product hardware develops through a debuggable custom A0 followed by a
   product-size, enclosure-integrated A1. The product form, A0/A1 architecture,
   and evidence gates are frozen; the final body size, PCB outline, battery,
   target ingress rating, production construction, and most BOM parts remain
   open.
6. `ESP32-S3-PICO-1-N8R8` is accepted only as the A0 engineering starting
   point. It is not the production MCU freeze.
7. `ML307A-GSLN`, BMI270, the named microphones, speaker, amplifier, camera
   class, storage, power-path parts, fuel gauge, haptic driver, USB-C
   receptacle, antennas, battery, and construction processes remain candidate
   or unknown. They cannot enter a frozen schematic, production claim, or
   purchase order until their explicit gates pass. A replacement or fallback
   remains allowed when evidence fails.
8. ADR-0005 and ADR-0006 are superseded for the current sales-product route.
   Their history and reusable evidence principles remain in the repository,
   but their V1 Pro platform, OLED, camera exclusion, ordinary-call exclusion,
   sensor population, form factor, and BOM no longer control new design or
   procurement.
9. `V1_PRO_FORM_FACTOR_BASELINE.md`, its drawing, and
   `V1_PRO_EVT_PROCUREMENT_BASELINE.md` become superseded historical references.
   No new tooling, schematic, or procurement may rely on them as current
   authority.
10. Current development-board firmware, Message Hub/Web services, protocols,
    schemas, evidence, and active D2/D5/FIELD tasks are unchanged. Their facts
    remain owned by `ACTIVE_BUILD.md`, `BOARD_MATRIX.md`, current task packets,
    and machine-readable contracts.
11. P0 continues to prove the thin safety/location/data loop under
    `PRODUCT_CHARTER.md` and `P0_SCOPE.md`. The master product baseline is a
    release target, not a claim that P0 already implements calls, camera,
    waterproofing, endurance, final form, or production hardware.
12. Privacy remains fail-closed: raw audio/image persistence is off by default;
    training is false by default; precise position is restricted; any
    retention, upload, or training needs purpose, consent, duration,
    deletion/revocation, and privacy review.
13. A measured typical guard-mode endurance of at least 48 hours is a
    production-release hard gate. It may be claimed only on representative
    battery, enclosure, antenna, firmware, model and operator configurations;
    this ADR is not evidence that the gate has passed.
14. Public location output must carry source, age and uncertainty and degrade
    honestly through `Fine`, `Coarse`, `Predicted` and `Unknown`. A stale or
    inferred point must never be presented as a current precise fix, and
    `Unknown` is the correct result when evidence is insufficient. Personal
    place/route memory and Top-K hypotheses remain governed by proposed
    ADR-0007 until separately accepted and implemented.
15. `safe`, `needs_help` and `no_response` remain screen-independent historical
    semantics for an optional L2/L3 user-confirmation loop. ADR-0012 removes
    that loop from the Sprint 1 P0 critical path. This ADR does not redefine
    wire/schema enum spellings; any future adapter must preserve and explicitly
    map the machine-readable contract values.
16. "Always available" safety and AI means that a low-power wake and local
    policy path remains available; it does not authorize continuous full-rate
    sensing. A generative or language model must never be the sole authorizer
    for physical SOS, a confirmed user request, no-response escalation or
    another mandatory safety action.
17. ADR-0012 supersedes ADR-0002/this ADR wherever learned on-device AI was a
    first-launch requirement. Deterministic local P0 policy and reliability
    remain mandatory; model/data quality, local-compute and graceful no-LTE
    principles continue as non-blocking L2/L3 engineering constraints.

## Supersession Matrix

| Prior authority | Superseded scope | Retained value |
| --- | --- | --- |
| ADR-0002 (partial) | Display/touch interaction assumption, VPS as default heavy personal-compute/training tier, ambiguous `always-on sensing` wording, and learned-AI launch blocking (superseded by ADR-0012) | Deterministic local safety decisions, data/model evidence gates for future promotion, local-compute discipline and graceful no-LTE degradation |
| ADR-0005 | Frozen nRF54LM20B/Air780EGH platform and associated V1 Pro BOM | Historical tradeoffs, measurable power/model/sourcing gates |
| ADR-0006 | OLED/data-first-no-phone/no-camera product direction, sensor and battery population | Honest reachability language, privacy/data minimization, measured ingress and power gates |
| `V1_PRO_FORM_FACTOR_BASELINE.md` and drawing | Watch envelope, OLED, four-layer PCB, 900 mAh bay, no-camera layout | Historical mechanical/RF test thinking |
| `V1_PRO_EVT_PROCUREMENT_BASELINE.md` | Buy-now and BOM list for the superseded V1 Pro | Historical sourcing and authorized-channel discipline |
| `V1_PRODUCT_PLAN.md` hardware/product-form clauses | V1 Pro watch assumptions and related M4 procurement exit | D2/D5, reliability, guardian UX, AI/data and evidence sequencing |

## Consequences

- The team has one explicit current sales-product direction while current
  development-board work can continue without churn.
- Existing V1 Pro purchases, if any, are evaluation assets only; the old list
  must not trigger new purchasing.
- A new A0 schematic/BOM/AVL and form-factor program must be created through
  narrow tasks after candidate evidence is collected.
- VoLTE, camera, waterproofing, modular mechanics, power, RF, acoustics,
  endurance, certification, privacy UX, and manufacturing are now explicit
  release risks rather than assumed capabilities.
- The 48-hour guard target remains a measured production gate, not a claim.
- Product-direction changes of this scale require a later founder-accepted ADR
  and synchronized authority updates; ordinary implementation fixes do not.

## Reconsideration Triggers

- `G0-VOICE` cannot identify any China-market modem/SKU/firmware with a viable
  documented and measured three-operator VoLTE/audio path.
- The screenless interaction fails user confirmation, SOS recovery, privacy,
  or accessibility testing.
- Event-camera value does not justify its privacy, power, optical, mechanical,
  or certification cost.
- The modular waterproof core cannot meet RF, acoustic, ingress, thermal,
  wearability, reliability, or serviceability gates.
- The A0 engineering platform cannot fit the required models, peripherals,
  power budget, or production migration path.

## Related Documents

- [Master product context](../../product/EGO_MASTER_CONTEXT.md)
- [North star](../../product/NORTH_STAR.md)
- [P0 product charter](../../product/PRODUCT_CHARTER.md)
- [P0 scope](../../product/P0_SCOPE.md)
- [On-device AI decision](ADR-0002-v1-ondevice-ai-companion-core.md)
- [Superseded V1 Pro hardware decision](ADR-0005-v1-pro-production-hardware-baseline.md)
- [Superseded V1 Pro peripheral decision](ADR-0006-v1-pro-product-peripheral-revision.md)
